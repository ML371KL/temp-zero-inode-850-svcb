"""ЦБ CreditOrgInfo: формы банковской группы 0409805, 0409803, 0409802 по регномеру головного банка.

Та же служба SOAP, что у форм банка (`indicators/cbr_forms.py`); регномер — `meta.company.cbr_regnum`
книги, перечень форм — `sources.yaml → cbr_group.forms`:

* `RegNumToIntCode` — внутренний код организации по регномеру (хранится в индексе);
* `GetPeriodsOfDocuments` — перечень отчётных периодов форм (`dt="202606"`); новый период — сигнал;
* `GetF805Xml` (раздел 1 — капитал, раздел 4 — нормативы), `Data803FXML`, `Data802FXML` — сами
  формы; дата запроса — первое число отчётного месяца.

**Формы нет — ответ тоже с кодом 200**: раздел 1 — одна пустая строка, раздел 4 — пустой элемент.
Признак «форма есть» — число в строке итога капитала (`000`) и в Н20.0 (у формы 803 — в строке
прибыли, у 802 — в любой строке), а не код ответа. **День первого появления** формы у источника
узнать негде: его пишет этот сборщик в день, когда форма впервые пришла с числами
(`cbr_group/index.json → first_seen`). Поэтому квартал, который уже кончился, запрашивается каждый
день, пока форма не появится, — и тогда, когда перечень периодов его ещё не называет. Первый
запуск историю не качает (история рядов — в `data/indicators/seed/`): прошлые периоды помечаются
известными без дня появления, качаются последние `RECHECK_PERIODS`.

Винтажи — как у форм банка: sha256 ответа, раз в неделю перекачка последних периодов; другой
ответ — новая точка ряда рядом с прежней. Заглушка сервиса (ответ без конверта SOAP) — отказ с
повтором, версией формы она не становится.

Ряды (период — квартал `2026Q2`): `cbr.f805.{n20_0, n20_1, n20_2}` — доли; `cbr.f805.{capital_total,
capital_base}`, `cbr.f803.{ni_ytd, nii_ytd}` — млрд ₽ (формы — в тыс. ₽), базис — банковская группа
по ЦБ. Форма 802 кладётся в сырой архив; рядов из неё нет. Ядру формы группы не передаются:
нормативы якоря ядро читает из фактов, свежая форма видна в рядах, плитках и событии календаря.

`estimate` — оценка нормативов группы до выхода формы: норматив банка (форма 0409135 на первое
число после квартала) плюс разность «группа − банк» на последнюю общую дату.

**Раскрытие приостановлено** (`cbr_group.suspended_since`: квартал, с которого ЦБ форм группы эмитента не
раскрывает — ответы с кодом 200 и без чисел): кончившийся квартал с этого и позже не ждётся и не запрашивается,
пока перечень периодов его не назовёт; назвал — форма вернулась, и квартал идёт обычным порядком. Деградации
«формы нет» по таким кварталам нет: её отсутствие — не отказ источника, а состояние раскрытия.
"""

from __future__ import annotations

import html as _html
import re
import sys
from datetime import date
from typing import Any, Mapping

from indicators import cbr_forms, http, periods
from indicators.sources import FAILED, Context, Result
from indicators.store import Store, point

URL = cbr_forms.URL
SOURCE = "cbr_group"
INDEX_FILE = "cbr_group/index.json"
FORMS = ("805", "803", "802")
RECHECK_PERIODS = 4
RECHECK_EVERY_DAYS = 7
THOUSAND_TO_BN = cbr_forms.THOUSAND_TO_BN
F805_CAPITAL = {"000": "capital_total", "102": "capital_base"}
F805_TOTAL = "000"
F805_NORMS = {"Н20.0": "n20_0", "Н20.1": "n20_1", "Н20.2": "n20_2"}
F805_KEY_NORM = "Н20.0"
F803_ROWS = {"27": "ni_ytd", "3": "nii_ytd"}      # раздел I: прибыль после налога, чистые процентные доходы
F803_KEY_ROW = "27"
F803_SECTION = "I"
# Норматив группы → норматив банка формы 0409135 для оценки до выхода формы.
BANK_NORMS = {"n20_0": "n1_0", "n20_1": "n1_1", "n20_2": "n1_2"}
NOTE_BEFORE_START = cbr_forms.NOTE_BEFORE_START


class GroupFormError(RuntimeError):
    """Ответ службы не разобран."""


# ------------------------------------------------------------------ периоды

def period_of(dt: str) -> str:
    """Отчётный период формы `202606` → квартал `2026Q2`."""
    year, month = int(dt[:4]), int(dt[4:6])
    return periods.quarter(year, (month - 1) // 3 + 1)


def dt_of(period: str) -> str:
    """Квартал `2026Q2` → отчётный период формы `202606`."""
    y, m = periods.parse_month(periods.quarter_months(period)[-1])
    return f"{y:04d}{m:02d}"


def request_stamp(dt: str) -> str:
    """Дата запроса формы группы — первое число отчётного месяца."""
    return f"{dt[:4]}-{dt[4:6]}-01T00:00:00"


# ------------------------------------------------------------------ запросы

def intcode_request(regnum: str) -> tuple[str, str]:
    return "RegNumToIntCode", f"<RegNumber>{regnum}</RegNumber>"


def periods_request(internal_code: str) -> tuple[str, str]:
    return "GetPeriodsOfDocuments", f"<InternalCode>{internal_code}</InternalCode>"


def form_requests(form: str, regnum: str, dt: str) -> list[tuple[str, str, str]]:
    """Запросы формы за период: [(имя части, операция, тело)]."""
    stamp = request_stamp(dt)
    if form == "805":
        return [(f"par{par}", "GetF805Xml",
                 f"<CredorgNumber>{regnum}</CredorgNumber><dateTime>{stamp}</dateTime><par>{par}</par>")
                for par in (1, 4)]
    if form in ("803", "802"):
        return [("doc", f"Data{form}FXML", f"<CredorgNumber>{regnum}</CredorgNumber><Dt>{stamp}</Dt>")]
    raise GroupFormError(f"неизвестная форма {form}")


# ------------------------------------------------------------------ разбор

def _text(body: bytes | str) -> str:
    return body.decode("utf-8") if isinstance(body, bytes) else body


def _attrs(tag: str) -> dict[str, str]:
    return {k: _html.unescape(v) for k, v in re.findall(r'([\w.]+)="([^"]*)"', tag)}


def _num(value: str | None) -> float | None:
    v = (value or "").strip().replace(",", ".")
    try:
        return float(v) if v else None
    except ValueError:
        return None


def parse_intcode(body: bytes | str) -> str:
    m = re.search(r"<RegNumToIntCodeResult>\s*(\d+)(?:\.0+)?\s*</RegNumToIntCodeResult>", _text(body))
    if m is None:
        raise GroupFormError("в ответе нет внутреннего кода организации")
    return m.group(1)


def parse_periods(body: bytes | str) -> dict[str, list[str]]:
    """Перечень отчётных периодов форм группы: {«805»: [«202503», «202506», …], …}. Ответ без единого
    периода формы 805 — не перечень (заглушка сервиса не должна читаться как «новых форм нет»)."""
    text = _text(body)
    out: dict[str, list[str]] = {}
    for form in FORMS:
        block = re.search(rf"<F{form}>(.*?)</F{form}>", text, re.S)
        out[form] = sorted(set(re.findall(r'\bdt="(\d{6})"', block.group(1)))) if block else []
    if not out[FORMS[0]]:
        raise GroupFormError("в ответе нет ни одного периода формы 0409805 — это не перечень периодов")
    return out


def parse_f805_capital(body: bytes | str) -> dict[str, float | None]:
    """Раздел 1 формы 805: код строки → итог, тыс. ₽ (пустая строка — формы нет: пустой словарь)."""
    out: dict[str, float | None] = {}
    for tag in re.findall(r"<fstr\b([^>]*)/?>", _text(body)):
        a = _attrs(tag)
        if a.get("fstr"):
            out[a["fstr"]] = _num(a.get("vsego"))
    return out


def parse_f805_norms(body: bytes | str) -> dict[str, float | None]:
    """Раздел 4 формы 805: норматив → фактическое значение, % (пустой раздел — пустой словарь)."""
    out: dict[str, float | None] = {}
    for tag in re.findall(r"<Item\b([^>]*)/?>", _text(body)):
        a = _attrs(tag)
        name = (a.get("NAME_NORM") or "").replace("H", "Н")      # латинская H в имени норматива — как кириллическая
        if name:
            out[name] = _num(a.get("FAKT_ZN"))
    return out


def parse_rows(body: bytes | str) -> dict[tuple[str, str], float | None]:
    """Строки форм 803 и 802: (раздел, код строки) → значение, тыс. ₽."""
    out: dict[tuple[str, str], float | None] = {}
    for tag in re.findall(r"<fstr\b([^>]*)/?>", _text(body)):
        a = _attrs(tag)
        if a.get("fstr"):
            out[(a.get("frazd") or "", a["fstr"])] = _num(a.get("vsego"))
    return out


def present(form: str, parts: Mapping[str, bytes]) -> tuple[bool, str]:
    """Есть ли форма в ответах: (да/нет, чего не хватает). Признак — числа, не код ответа."""
    if form == "805":
        capital = parse_f805_capital(parts["par1"]).get(F805_TOTAL)
        norm = parse_f805_norms(parts["par4"]).get(F805_KEY_NORM)
        if capital is None and norm is None:
            return False, ""
        if capital is None or norm is None:
            return False, "есть не всё: " + ("нет итога капитала" if capital is None else "нет Н20.0")
        return True, ""
    rows = parse_rows(parts["doc"])
    if form == "803":
        return rows.get((F803_SECTION, F803_KEY_ROW)) is not None, ""
    return any(v is not None for v in rows.values()), ""


def series_points(form: str, parts: Mapping[str, bytes]) -> dict[str, float | None]:
    """Точки рядов формы: {ряд: значение} (доли и млрд ₽)."""
    if form == "805":
        capital = parse_f805_capital(parts["par1"])
        norms = parse_f805_norms(parts["par4"])
        out = {f"cbr.f805.{key}": (None if capital.get(code) is None else capital[code] * THOUSAND_TO_BN)
               for code, key in F805_CAPITAL.items()}
        out.update({f"cbr.f805.{key}": (None if norms.get(name) is None else round(norms[name] / 100.0, 10))
                    for name, key in F805_NORMS.items()})
        return out
    if form == "803":
        rows = parse_rows(parts["doc"])
        return {f"cbr.f803.{key}": (None if rows.get((F803_SECTION, code)) is None
                                    else rows[(F803_SECTION, code)] * THOUSAND_TO_BN)
                for code, key in F803_ROWS.items()}
    return {}


def ingest(store: Store, form: str, dt: str, parts: Mapping[str, bytes], *, fetched_at: str, source: str) -> list[str]:
    """Точки рядов формы за период с моментом получения (винтаж). Возвращает ряды."""
    period = period_of(dt)
    touched = []
    for sid, value in series_points(form, parts).items():
        unit = "share" if ".n20_" in sid else "RUB bn"
        store.upsert(sid, [point(period, value, fetched_at=fetched_at, source=source)], unit=unit,
                     basis="regulatory" if unit == "share" else "group",
                     label=f"форма 0409{form} банковской группы: {sid.rsplit('.', 1)[-1]}")
        touched.append(sid)
    return touched


# ------------------------------------------------------------------ сбор

def load_index(store: Store) -> dict[str, Any]:
    return store.read_state(INDEX_FILE) or {"internal_code": None, "forms": {}}


def awaited(today: date) -> str:
    """Отчётный период последнего кончившегося квартала: его форму ждут и без строки в перечне."""
    return dt_of(periods.shift_quarter(periods.quarter_of(today), -1))


def _digest(parts: Mapping[str, bytes]) -> str:
    import hashlib  # noqa: PLC0415

    h = hashlib.sha256()
    for name in sorted(parts):
        h.update(parts[name])
    return h.hexdigest()


def collect(ctx: Context) -> Result:
    """Такт форм группы: перечень периодов, новые и ожидаемые периоды, раз в неделю — перекачка последних."""
    getter = ctx.getter or http.fetch
    sink = http.Sink(ctx.store, SOURCE)
    regnum = ctx.company["cbr_regnum"]
    forms = [str(f) for f in ((ctx.cfg.get(SOURCE) or {}).get("forms") or FORMS) if str(f) in FORMS]
    res = Result(name=SOURCE)
    index = load_index(ctx.store)
    index.setdefault("forms", {})
    try:
        if not index.get("internal_code") or index.get("regnum") != regnum:
            op, inner = intcode_request(regnum)
            index["internal_code"] = parse_intcode(http.soap(URL, op, inner, getter=getter, sink=sink,
                                                             name="intcode.xml").body)
            index["regnum"] = regnum
        op, inner = periods_request(index["internal_code"])
        listed = http.soap(URL, op, inner, getter=getter, sink=sink, name="periods.xml")
        listing = parse_periods(listed.body)
    except (http.FetchError, GroupFormError, UnicodeDecodeError) as exc:
        ctx.store.write_state(INDEX_FILE, index)
        res.status, res.detail = FAILED, f"перечень периодов форм группы — {exc}"
        res.retry = http.retryable(exc) or not isinstance(exc, http.FetchError)
        return res
    now = listed.fetched_at
    wait = awaited(ctx.today)
    suspended = str((ctx.cfg.get(SOURCE) or {}).get("suspended_since") or "") or None
    if suspended:
        res.data["suspended_since"] = suspended
    for form in forms:
        known: dict[str, Any] = index["forms"].setdefault(form, {})
        bootstrap = not known
        dates = listing.get(form) or []
        for dt in dates:
            if dt not in known:
                old = bootstrap and dt not in dates[-RECHECK_PERIODS:]
                known[dt] = {"first_seen": None, "fetched": None, "parsed": False,
                             **({"note": NOTE_BEFORE_START} if old else {}),
                             **({"bootstrap": True} if bootstrap and not old else {})}
        paused = lambda dt: bool(suspended) and period_of(dt) >= suspended and dt not in dates  # noqa: E731
        if wait not in known and (not dates or wait > dates[-1]) and not paused(wait):
            known[wait] = {"first_seen": None, "fetched": None, "parsed": False}
        queue = sorted(dt for dt, e in known.items() if not e.get("note") and not e.get("parsed") and not paused(dt))
        recent = [dt for dt in sorted(known)[-RECHECK_PERIODS:] if known[dt].get("parsed")]
        due = [dt for dt in recent if not known[dt].get("checked")
               or (ctx.today - date.fromisoformat(str(known[dt]["checked"])[:10])).days >= RECHECK_EVERY_DAYS]
        for dt in queue + due:
            entry = known[dt]
            words = f"форма 0409{form} группы за {period_of(dt)}"
            parts: dict[str, bytes] = {}
            moment = now
            try:
                for part, op, inner in form_requests(form, regnum, dt):
                    resp = http.soap(URL, op, inner, getter=getter, sink=sink, name=f"f{form}_{dt}_{part}.xml")
                    if not cbr_forms.is_service_document(resp.body):
                        raise GroupFormError(f"ответ — не документ сервиса (заглушка с кодом {resp.status})")
                    parts[part] = resp.body
                    moment = resp.fetched_at
                there, lack = present(form, parts)
            except http.FetchError as exc:
                res.degrade(f"{words}: {exc}", retry=http.retryable(exc))
                continue
            except (GroupFormError, UnicodeDecodeError) as exc:
                res.degrade(f"{words}: {exc}", retry=True)
                continue
            entry["fetched"] = moment
            if not there:
                if lack:
                    res.degrade(f"{words}: {lack}", retry=False)
                elif dt in dates and dt != wait:
                    res.degrade(f"{words}: период есть в перечне, а чисел в форме нет", retry=False)
                continue
            digest = _digest(parts)
            if entry.get("sha256") == digest and entry.get("parsed"):
                entry["checked"] = moment
                continue
            res.series += ingest(ctx.store, form, dt, parts, fetched_at=moment,
                                 source=f"cbr:0409{form}:{dt}:sha256:{digest[:12]}")
            if entry.get("parsed"):
                res.data.setdefault("revised", []).append(f"{form}:{dt}")
            elif not entry.pop("bootstrap", False):
                entry["first_seen"] = moment          # форма впервые пришла с числами при работающем сборщике
                res.data.setdefault("appeared", []).append(f"{form}:{period_of(dt)}")
            entry.update(parsed=True, sha256=digest, checked=moment)
    ctx.store.write_state(INDEX_FILE, index)
    return res


def first_seen(store: Store, form: str, period: str) -> str | None:
    """День первого появления формы за квартал по индексу сборщика (None — до запуска или ещё нет)."""
    entry = (load_index(store).get("forms", {}).get(form) or {}).get(dt_of(period)) or {}
    return entry.get("first_seen")


# ------------------------------------------------------------------ оценка до выхода формы

def estimate(store: Store, period: str, as_of: str | None = None) -> dict[str, dict[str, Any]]:
    """Нормативы группы за квартал до выхода формы: норматив банка на конец квартала (форма 0409135)
    плюс разность «группа − банк» на последнюю общую дату. {норматив: {value, bank_value, spread,
    spread_as_of}}; норматива банка или общей даты нет — норматив пропущен."""
    month = periods.quarter_months(period)[-1]
    out: dict[str, dict[str, Any]] = {}
    for group, bank in BANK_NORMS.items():
        g, b = store.load(f"cbr.f805.{group}"), store.load(f"cbr.f135.{bank}")
        if g is None or b is None:
            continue
        bank_now = b.value_as_of(month, as_of)
        if bank_now is None:
            continue
        common = [q for q in sorted(g.history(as_of), reverse=True)
                  if q < period and b.value_as_of(periods.quarter_months(q)[-1], as_of) is not None]
        if not common:
            continue
        q = common[0]
        spread = g.value_as_of(q, as_of) - b.value_as_of(periods.quarter_months(q)[-1], as_of)
        out[group] = {"value": round(bank_now + spread, 6), "bank_value": bank_now, "spread": round(spread, 6),
                      "spread_as_of": periods.quarter_end(q).isoformat()}
    return out


def main(argv: list[str] | None = None) -> int:
    """`python -m indicators.cbr_group <квартал>` — оценка нормативов группы до выхода формы."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or not periods.is_quarter(args[0]):
        print("нужен квартал вида 2026Q3", file=sys.stderr)
        return 64
    got = estimate(Store(), args[0])
    if not got:
        print(f"{args[0]}: оценки нет — нужен норматив банка на конец квартала и общая дата с формой группы")
        return 1
    for name, e in got.items():
        print(f"{name} {args[0]}: {e['value']:.4%} = банк {e['bank_value']:.4%} + разность {e['spread']:+.4%} "
              f"на {e['spread_as_of']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
