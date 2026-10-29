"""Расписание тактов: одна правка `ops/schedule.json` — и строки таймеров из неё.

    python ops/tools/schedule.py            таблица: такты в UTC и по Москве, расстояние до соседей
    python ops/tools/schedule.py --check    строки OnCalendar таймеров равны расписанию (код 1 — нет)
    python ops/tools/schedule.py --write    вписать строки OnCalendar в таймеры

`ops/schedule.json` — единственное место, где расписание пишется руками: время утреннего сбора и
суточного такта, минуты пересборки, окно дозора и его шаг, такты соседних панелей общего сервера и
наименьшее расстояние до них. Строки `OnCalendar` таймеров `ops/systemd/*-<такт>.timer` — производные:
их вписывает `--write`, равенство сверяют `--check` и `tests/test_ops_units.py`. Остальные строки
таймеров (разброс, точность, догон пропущенного запуска) расписанием не являются и живут в самих
файлах.

Окно дозора — `timers.release-watch.window_msk` с шагом `every_min`: первая проверка — в начале
окна, последняя — раньше его конца. Строк `OnCalendar` у дозора может быть несколько: запись systemd
«ЧЧ:ММ/шаг» считает минуты внутри часа, поэтому час, начатый не с первой минуты сетки, идёт своей
строкой.

Расписание, которое противоречит себе или подходит к такту соседней панели ближе, чем `gaps_min`,
инструмент называет строками «расписание: …» (код 1) и в таймеры не пишет: сначала правится оно само.

Расстояние сверяется не только между одноимёнными тактами (`distances`), но и накрест (`crossings`):
тяжёлые такты — сбор и суточный — держат своё расстояние до обоих тяжёлых тактов соседа (сбор, вставший
на суточный такт соседа, — та же встреча двух сборок); лёгкие проверки — пересборка и дозор — не садятся
на минуту лёгкой проверки соседа другого имени (пересборка на минуту чужого дозора, дозор на минуту
чужой пересборки) и на минуту своего тяжёлого такта. Лёгкая проверка соседа внутри своего тяжёлого окна
противоречием не считается. Блоки `gaps_min` и `neighbours` обязательны: без них расстояние не сверить
(у панели без соседей — пустой список `neighbours.panels`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEDULE = ROOT / "ops" / "schedule.json"
MODES = ("collect", "release-watch", "daily", "rebuild")
DAY = 24 * 60
HOUR = 60
DAYS = re.compile(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:\.\.(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))?")
CLOCK = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
ON_CALENDAR = re.compile(r"(?m)^(?:OnCalendar=.*\n)+")


class ScheduleError(ValueError):
    """Файл таймера не несёт строки, в которую пишется расписание."""


def load(path: Path | None = None) -> dict:
    return json.loads(Path(path or SCHEDULE).read_text(encoding="utf-8"))


def minutes(clock: str) -> int:
    """«ЧЧ:ММ» → минуты от полуночи."""
    m = CLOCK.fullmatch(str(clock))
    if m is None:
        raise ValueError(f"{clock!r} — время пишется как ЧЧ:ММ")
    return int(m.group(1)) * HOUR + int(m.group(2))


def clock(total: int) -> str:
    total %= DAY
    return f"{total // HOUR:02d}:{total % HOUR:02d}"


def _days(timer: dict) -> str:
    days = str(timer.get("days") or "")
    return f"{days} " if days else ""


# ------------------------------------------------------------------ производные

def watch_ticks(s: dict) -> list[int]:
    """Проверки дозора, минуты UTC от полуночи: от начала окна с шагом, раньше конца окна."""
    watch = s["timers"]["release-watch"]
    shift = int(s["msk_offset_hours"]) * HOUR
    start, end = (minutes(x) - shift for x in watch["window_msk"])
    return list(range(start, end, int(watch["every_min"])))


def watch_calendars(s: dict) -> list[str]:
    """Строки `OnCalendar` дозора. Час, чьи проверки идут до конца часа, — «ЧЧ:ММ/шаг»; последний час,
    оборванный концом окна, — перечнем минут; соседние часы с одной записью минут — «Ч1..Ч2»."""
    watch = s["timers"]["release-watch"]
    step = int(watch["every_min"])
    by_hour: dict[int, list[int]] = {}
    for tick in watch_ticks(s):
        by_hour.setdefault(tick // HOUR, []).append(tick % HOUR)
    spans: list[tuple[int, int, str]] = []
    for hour, mins in sorted(by_hour.items()):
        whole = mins == list(range(mins[0], HOUR, step))
        spec = f"{mins[0]:02d}/{step}" if whole and len(mins) > 1 else ",".join(f"{m:02d}" for m in mins)
        if spans and spans[-1][2] == spec and spans[-1][1] == hour - 1:
            spans[-1] = (spans[-1][0], hour, spec)
        else:
            spans.append((hour, hour, spec))
    return [f"{_days(watch)}*-*-* " + (f"{a:02d}" if a == b else f"{a:02d}..{b:02d}") + f":{spec}:00 UTC"
            for a, b, spec in spans]


def calendars(s: dict) -> dict[str, list[str]]:
    """Такт → строки `OnCalendar` его таймера."""
    timers = s["timers"]
    return {
        "collect": [f"{_days(timers['collect'])}*-*-* {timers['collect']['at_utc']}:00 UTC"],
        "release-watch": watch_calendars(s),
        "daily": [f"{_days(timers['daily'])}*-*-* {timers['daily']['at_utc']}:00 UTC"],
        "rebuild": ["*:" + ",".join(f"{int(m):02d}" for m in timers["rebuild"]["minutes"])],
    }


def _apart(a: int, b: int, cycle: int) -> int:
    """Расстояние между двумя отметками на круге длиной `cycle`."""
    d = abs(a - b) % cycle
    return min(d, cycle - d)


def distances(s: dict) -> list[tuple[str, str, int, int]]:
    """(такт, соседняя панель, расстояние в минутах, наименьшее допустимое) — по каждому известному такту соседа."""
    timers, gaps = s["timers"], s["gaps_min"]
    rebuild = [int(m) for m in timers["rebuild"]["minutes"]]
    period = rebuild[1] - rebuild[0] if len(rebuild) > 1 else HOUR
    step = int(timers["release-watch"]["every_min"])
    first = watch_ticks(s)[0]
    out = []
    for n in s["neighbours"]["panels"]:
        name = str(n["panel"])
        for mode, key in (("collect", "collect_utc"), ("daily", "daily_utc")):
            if n.get(key) is not None:
                out.append((mode, name, _apart(minutes(timers[mode]["at_utc"]), minutes(n[key]), DAY), int(gaps[mode])))
        if n.get("rebuild_minute") is not None:
            out.append(("rebuild", name, _apart(rebuild[0] % period, int(n["rebuild_minute"]) % period, period),
                        int(gaps["rebuild"])))
        if n.get("watch_minute") is not None:
            out.append(("release-watch", name, _apart(first % step, int(n["watch_minute"]) % step, step),
                        int(gaps["release-watch"])))
    return out


HEAVY = {"collect": ("collect_utc", "утреннего сбора"), "daily": ("daily_utc", "суточного такта")}


def _hour_marks(first: int, period: int) -> list[int]:
    """Минуты часа отметки с шагом `period`: 7 при шаге 15 → 7, 22, 37, 52."""
    return [m for m in range(HOUR) if m % period == first % period]


def _nearest(mine: list[int], theirs: list[int], cycle: int) -> int:
    return min(_apart(a, b, cycle) for a in mine for b in theirs)


def crossings(s: dict) -> list[tuple[str, str, str, int, int, str]]:
    """Расстояния накрест: (такт, слово о встречном такте, чей он, расстояние в минутах, наименьшее допустимое,
    ключ правила).

    * сбор и суточный такт — до суточного такта и сбора каждого соседа (`gaps_min.<такт>`);
    * пересборка — до минуты дозора соседа, дозор — до минуты пересборки соседа: не ближе меньшего из
      `gaps_min.rebuild` и `gaps_min.release-watch` (шаг чужой проверки считается равным своему — другого в
      записях нет);
    * пересборка и дозор — до минуты своего сбора и суточного такта: не на той же минуте."""
    timers, gaps = s["timers"], s["gaps_min"]
    rebuild = [int(m) for m in timers["rebuild"]["minutes"]]
    period = rebuild[1] - rebuild[0] if len(rebuild) > 1 else HOUR
    step = int(timers["release-watch"]["every_min"])
    ticks = watch_ticks(s)
    watch = sorted({t % HOUR for t in ticks})
    light = min(int(gaps["rebuild"]), int(gaps["release-watch"]))
    rule = "меньшее из gaps_min.rebuild и gaps_min.release-watch"
    out = []
    for n in s["neighbours"]["panels"]:
        name = f"панели «{n['panel']}»"
        for mode, other in (("collect", "daily"), ("daily", "collect")):
            key, words = HEAVY[other]
            if n.get(key) is not None:
                out.append((mode, words, name, _apart(minutes(timers[mode]["at_utc"]), minutes(n[key]), DAY),
                            int(gaps[mode]), f"gaps_min.{mode}"))
        if n.get("watch_minute") is not None:
            out.append(("rebuild", "проверки дозора", name,
                        _nearest(rebuild, _hour_marks(int(n["watch_minute"]), step), HOUR), light, rule))
        if n.get("rebuild_minute") is not None and watch:
            out.append(("release-watch", "пересборки", name,
                        _nearest(watch, _hour_marks(int(n["rebuild_minute"]), period), HOUR), light, rule))
    for mode, (_, words) in HEAVY.items():
        at = minutes(timers[mode]["at_utc"])
        out.append(("rebuild", words, "этой панели", _nearest(rebuild, [at % HOUR], HOUR), 1, "не на одной минуте"))
        if ticks:
            out.append(("release-watch", words, "этой панели", min(_apart(t, at, DAY) for t in ticks), 1,
                        "не на одной минуте"))
    return out


# ------------------------------------------------------------------ согласие расписания с собой

def findings(s: dict) -> list[str]:
    """Что в расписании противоречит ему самому или тактам соседей (пусто — всё сходится)."""
    out: list[str] = []
    timers = s.get("timers") or {}
    if set(timers) != set(MODES):
        return [f"timers: {sorted(timers)} — ожидались такты {', '.join(MODES)}"]
    shift = s.get("msk_offset_hours")
    if not (isinstance(shift, int) and not isinstance(shift, bool)):
        out.append(f"msk_offset_hours: {shift!r} — целое число часов")
    for mode in ("collect", "daily"):
        if CLOCK.fullmatch(str(timers[mode].get("at_utc"))) is None:
            out.append(f"timers.{mode}.at_utc: {timers[mode].get('at_utc')!r} — время пишется как ЧЧ:ММ")
    for mode in ("collect", "daily", "release-watch"):
        days = timers[mode].get("days")
        if days is not None and DAYS.fullmatch(str(days)) is None:
            out.append(f"timers.{mode}.days: {days!r} — дни недели как у systemd (Mon..Fri)")
    rebuild = timers["rebuild"].get("minutes")
    if not (isinstance(rebuild, list) and rebuild and all(isinstance(m, int) and not isinstance(m, bool)
                                                         and 0 <= m < HOUR for m in rebuild)
            and rebuild == sorted(set(rebuild))):
        out.append(f"timers.rebuild.minutes: {rebuild!r} — минуты часа по возрастанию, без повторов")
    else:
        gaps = {(b - a) % HOUR for a, b in zip(rebuild, rebuild[1:] + rebuild[:1])} if len(rebuild) > 1 else {0}
        if len(gaps) != 1:
            out.append(f"timers.rebuild.minutes: {rebuild} — шаг между проверками обязан быть одним и тем же")
    watch = timers["release-watch"]
    window, step = watch.get("window_msk"), watch.get("every_min")
    if not (isinstance(window, list) and len(window) == 2 and all(CLOCK.fullmatch(str(x)) for x in window)):
        out.append(f"timers.release-watch.window_msk: {window!r} — начало и конец окна как ЧЧ:ММ")
    elif not (isinstance(step, int) and not isinstance(step, bool) and step > 0 and HOUR % step == 0):
        out.append(f"timers.release-watch.every_min: {step!r} — делитель 60 (запись systemd считает минуты внутри часа)")
    elif isinstance(shift, int) and not isinstance(shift, bool):
        start, end = (minutes(x) - shift * HOUR for x in window)
        if not 0 <= start < end <= DAY:
            out.append(f"timers.release-watch.window_msk: {window} — окно лежит внутри одних суток UTC, начало раньше конца")
    if out:
        return out
    whole = lambda x: isinstance(x, int) and not isinstance(x, bool)  # noqa: E731
    gaps = s.get("gaps_min")
    if not (isinstance(gaps, dict) and all(whole(gaps.get(mode)) and gaps[mode] >= 0 for mode in MODES)):
        out.append(f"gaps_min: {gaps!r} — наименьшее расстояние в минутах до такта соседа, целым числом на каждый такт "
                   f"({', '.join(MODES)})")
    near = s.get("neighbours")
    panels = near.get("panels") if isinstance(near, dict) else None
    if not (isinstance(panels, list) and all(isinstance(n, dict) and n.get("panel") for n in panels)
            and near.get("checked_on")):
        out.append("neighbours: нет блока тактов соседних панелей общего сервера (checked_on — день сверки списка "
                   "таймеров, panels — список; у панели без соседей он пуст): без него расстояние не сверить")
        return out
    known = {"collect": "collect_utc", "daily": "daily_utc"}
    for n in panels:
        for mode, key in known.items():
            if n.get(key) is not None and CLOCK.fullmatch(str(n[key])) is None:
                out.append(f"neighbours: {n.get('panel')}: {key}: {n[key]!r} — время пишется как ЧЧ:ММ")
        for key in ("rebuild_minute", "watch_minute"):
            if n.get(key) is not None and not (whole(n[key]) and 0 <= n[key] < HOUR):
                out.append(f"neighbours: {n.get('panel')}: {key}: {n[key]!r} — минута часа целым числом или null")
    if out:
        return out
    for mode, name, apart, least in distances(s):
        if apart < least:
            out.append(f"{mode}: до такта панели «{name}» — {apart} мин, а нужно не меньше {least} "
                       f"(gaps_min.{mode}): сдвинуть такт или сверить список таймеров сервера")
    for mode, words, whose, apart, least, rule in crossings(s):
        if apart < least:
            out.append(f"{mode}: до {words} {whose} — {apart} мин, а нужно не меньше {least} ({rule}): "
                       f"сдвинуть такт или сверить список таймеров сервера")
    return out


# ------------------------------------------------------------------ производные строки файлов

def _timer_path(root: Path, mode: str) -> Path:
    found = sorted((root / "ops" / "systemd").glob(f"*-{mode}.timer"))
    if len(found) != 1:
        raise ScheduleError(f"таймер такта {mode!r}: ожидался один файл ops/systemd/*-{mode}.timer, найдено {len(found)}")
    return found[0]


def apply(s: dict, root: Path | None = None, *, write: bool = False) -> list[str]:
    """Расхождения строк `OnCalendar` таймеров с расписанием; с `write` — вписывает их. Таймер без
    строки `OnCalendar` или с двумя разнесёнными блоками таких строк — `ScheduleError`, не догадка."""
    root = Path(root or ROOT)
    out: list[str] = []
    for mode, lines in calendars(s).items():
        path = _timer_path(root, mode)
        text = path.read_bytes().decode("utf-8")
        blocks = ON_CALENDAR.findall(text)
        if len(blocks) != 1:
            raise ScheduleError(f"{path.name}: блоков строк «OnCalendar=» — {len(blocks)}, ожидался один")
        want = "".join(f"OnCalendar={line}\n" for line in lines)
        if blocks[0] != want:
            have = "; ".join(x.split("=", 1)[1] for x in blocks[0].splitlines())
            out.append(f"{path.name}: OnCalendar — {have}, по расписанию {'; '.join(lines)}")
            if write:
                path.write_bytes(ON_CALENDAR.sub(lambda _m: want, text, count=1).encode("utf-8"))
    return out


# ------------------------------------------------------------------ печать

def show(s: dict) -> str:
    timers, shift = s["timers"], int(s["msk_offset_hours"]) * HOUR
    ticks = watch_ticks(s)
    step = int(timers["release-watch"]["every_min"])
    rebuild = ", ".join(f":{int(m):02d}" for m in timers["rebuild"]["minutes"])
    rows = [("collect", "ежедневно", timers["collect"]["at_utc"], clock(minutes(timers["collect"]["at_utc"]) + shift)),
            ("release-watch", f"{timers['release-watch'].get('days', 'ежедневно')}, каждые {step} мин",
             f"{clock(ticks[0])}–{clock(ticks[-1])}", f"{clock(ticks[0] + shift)}–{clock(ticks[-1] + shift)}"),
            ("daily", timers["daily"].get("days", "ежедневно"), timers["daily"]["at_utc"],
             clock(minutes(timers["daily"]["at_utc"]) + shift)),
            ("rebuild", "каждый час", rebuild, "те же минуты")]
    lines = ["такт            когда                         UTC            по Москве"]
    lines += [f"{mode:<15} {when:<29} {utc:<14} {msk}" for mode, when, utc, msk in rows]
    lines += ["", "строки OnCalendar:"]
    for mode, cals in calendars(s).items():
        lines += [f"  {mode:<15} {line}" for line in cals]
    lines += ["", f"соседи общего сервера (список таймеров на {s['neighbours']['checked_on']}), расстояние в минутах:"]
    for mode, name, apart, least in distances(s):
        lines.append(f"  {mode:<15} {name:<10} {apart:>4}  (не меньше {least})")
    lines += ["", "накрест — до разноимённых тактов соседей и до своих тяжёлых тактов, минуты:"]
    for mode, words, whose, apart, least, _rule in crossings(s):
        lines.append(f"  {mode:<15} до {words} {whose:<18} {apart:>4}  (не меньше {least})")
    unknown = sorted({str(n["panel"]) for n in s["neighbours"]["panels"]
                      if n.get("rebuild_minute") is None or n.get("collect_utc") is None or n.get("daily_utc") is None})
    if unknown:
        lines.append(f"  нет в записях (сверить `systemctl list-timers` перед включением таймеров): минуты пересборки или "
                     f"такты панелей {', '.join(unknown)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="schedule.py", description="расписание тактов: таблица, сверка, запись в таймеры")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="сверить строки OnCalendar таймеров с расписанием (код 1 — расходятся)")
    mode.add_argument("--write", action="store_true", help="вписать строки OnCalendar в таймеры")
    ap.add_argument("--root", type=Path, default=ROOT, help="корень дерева (по умолчанию — этот репозиторий)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    s = load(args.root / "ops" / "schedule.json")
    wrong = findings(s)
    for line in wrong:
        print(f"расписание: {line}")
    if wrong:
        print("ops/schedule.json противоречит себе или тактам соседей — таймеры не трогаю")
        return 1
    if not (args.check or args.write):
        print(show(s))
        return 0
    try:
        diff = apply(s, args.root, write=args.write)
    except ScheduleError as exc:
        print(f"ОТКАЗ: {exc}")
        return 1
    for line in diff:
        print(("вписано — " if args.write else "расходится — ") + line)
    if args.write:
        print(f"готово: таймеров переписано — {len(diff)}" if diff else "готово: менять нечего")
        return 0
    print("строки таймеров равны расписанию" if not diff
          else "строки таймеров расходятся с расписанием: python ops/tools/schedule.py --write")
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
