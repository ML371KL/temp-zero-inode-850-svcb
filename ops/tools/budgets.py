"""Бюджет времени и памяти тактов: одна правка `ops/budgets.json` — и производные числа везде.

    python ops/tools/budgets.py            таблица: шаги, потолки юнитов, окна перезапуска, память, CI
    python ops/tools/budgets.py --check    производные числа в юнитах, run.sh и CI равны бюджету (код 1 — нет)
    python ops/tools/budgets.py --write    вписать производные числа в юниты, run.sh и файлы CI

`ops/budgets.json` — единственное место, где числа бюджета пишутся руками: время шагов такта на
сервере, запас, число процессов полосы, память, время частей набора тестов. Всё остальное из них
считается (формулы — поле `about` бюджета и функции ниже) и лежит строками в других файлах:

* юниты `ops/systemd/*-<такт>.service` — `RuntimeMaxSec`, `MemoryHigh`, `MemoryMax`; у тактов с
  перезапуском — `StartLimitIntervalSec`, `StartLimitBurst`, `RestartSec`, `RestartPreventExitStatus`;
* `ops/run.sh` — `LOCK_WAIT_SECONDS`, `COLLECT_RETRY_ATTEMPTS`, `COLLECT_RETRY_PAUSE`, `BUDGET_WORKERS`;
* `.github/workflows/*.yml` — потолки заданий CI (`minutes` частей набора, `timeout-minutes` заданий).

Порядок смены чисел (новый замер ноутбука после ускорения ядра, замер на сервере): правка
`ops/budgets.json` → `--write` → `python -m pytest tests/test_ops_units.py tests/test_ops_ci.py` →
коммит; на сервере юниты ставятся заново (ops/README.md §7).

Бюджет не ниже замера, на котором стоит (`basis`), — в обоих статусах; это проверяют `--check` и
тест. Сборка: верх замеров обычного случая и худшего (цена у медианы, `basis.build_worst_s`),
пересчитанный на число процессов бюджета. Тесты такта: замер набора, не дольше цели сервера
`tact_tests_target`. `status: estimate` — `basis` несёт замер ноутбука, и оба числа умножаются на
запас на сервер (`basis.server_factor` — сборка, `basis.tact_server_factor` — тесты), а сам набор
такта на ноутбуке не дольше `tact_tests_laptop_limit`. `status: measured` — `basis` несёт замер
сервера, запасов на сервер в нём нет. Замеры `basis`: `build_s`, `build_worst_s`, `memory_tree_mb` —
числом или списком прогонов; `memory_process_mb`, `tact_tests_s`, `tact_tests_memory_mb` — одним
числом (наибольший из прогонов).

Окно перезапуска такта короче суток: окно длиннее заперло бы и завтрашний запуск по таймеру. Бюджет,
у которого оно выходит за сутки (долгая сборка при малом числе процессов), противоречит себе —
строка «бюджет: restart …», производные числа не пишутся.

Цель времени сборки на рабочей машине — `build_laptop_goal` (обычный и худший случай при названном
числе процессов). Бюджету она не противоречит: пока замер рабочей машины в `basis` дольше цели,
инструмент печатает строку «ВНИМАНИЕ» (код прежний).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUDGETS = ROOT / "ops" / "budgets.json"
STATUSES = ("estimate", "measured")
MAX_WORKERS = 7                 # предел пула полосы у ядра: «ядра − 1, не больше 7»
DAY = 24 * 3600                 # окно перезапуска такта — короче суток
# Наименьший запас оценки с ноутбука на скорость ядра сервера: сборка (полоса пулом процессов) и набор
# тестов такта (один процесс). У замера с сервера этих полей нет.
ESTIMATE_FACTORS = {"server_factor": 2.0, "tact_server_factor": 1.5}
# Замеры `basis`: число или список чисел (несколько прогонов) — и просто числа.
MEASURED_MANY = ("build_s", "build_worst_s", "memory_tree_mb")
MEASURED_ONE = ("memory_process_mb", "tact_tests_s", "tact_tests_memory_mb")


class BudgetError(ValueError):
    """Бюджет противоречит себе или файл не несёт строки, в которую пишется число."""


def load(path: Path | None = None) -> dict:
    return json.loads(Path(path or BUDGETS).read_text(encoding="utf-8"))


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _many(value) -> list:
    """Замер из `basis` списком: одно число (один прогон) — список из него."""
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _span(values: list) -> str:
    """«535–542» или одно число — для печати замера."""
    low, high = min(values), max(values)
    return f"{low:g}" if low == high else f"{low:g}–{high:g}"


def _up(value: float, step: int) -> int:
    """Вверх до кратного `step`; хвост двоичной дроби (1.5 × 4 580 = 6 870,000…01) вверх не толкает."""
    return int(math.ceil(round(value / step, 9)) * step)


# ------------------------------------------------------------------ формулы

def ceilings(b: dict) -> tuple[dict[str, int], int]:
    """(такт → `RuntimeMaxSec`, ожидание замка). Потолок = сумма шагов × запас вверх до `round_to`;
    у тактов, ждущих замок, плюс ожидание = наибольший потолок держателей замка."""
    step = int(b["round_to"])

    def run(unit: str) -> int:
        return _up(sum(b["seconds"][name] for name in b["units"][unit]) * b["safety"], step)

    lock = max(run(unit) for unit in b["lock_holders"])
    return {unit: run(unit) + (lock if unit in b["lock_waiters"] else 0) for unit in b["units"]}, lock


def restart_windows(b: dict) -> dict[str, int]:
    """Такт с перезапуском → `StartLimitIntervalSec`: окно вмещает `burst` самых долгих прогонов с
    паузой и остановкой (systemd считает окно от первого старта и не двигает его)."""
    restart, step = b["restart"], int(b["round_to"])
    limits, _ = ceilings(b)
    return {unit: _up(restart["burst"] * (limits[unit] + restart["pause_s"] + restart["stop_s"]), step)
            for unit in restart["units"]}


def ci_minutes(b: dict) -> dict[str, int]:
    """Задание CI → потолок в минутах: (подготовка + время части на ноутбуке × `runner_factor`) × запас,
    вверх до `round_to_min`."""
    ci = b["ci"]
    return {part: _up((ci["setup_s"] + seconds * ci["runner_factor"]) * ci["safety"] / 60, int(ci["round_to_min"]))
            for part, seconds in ci["laptop_seconds"].items()}


def build_measurements(b: dict) -> list:
    """Замеры сборки из `basis`: обычный случай (`build_s`) и худший — на цене у медианы, когда на
    полной полосе уточняются все строки обратного расчёта (`build_worst_s`)."""
    basis = b["basis"]
    return _many(basis["build_s"]) + _many(basis.get("build_worst_s", []))


def scaled_build(b: dict) -> int:
    """Время сборки из замеров `basis`, пересчитанное на сервер: верх замеров обычного и худшего
    случая × процессы замера / процессы бюджета (полоса делится между процессами поровну) × запас
    на скорость ядра сервера `basis.server_factor` (нет поля — 1: замер уже с сервера)."""
    basis = b["basis"]
    return math.ceil(max(build_measurements(b)) * basis["workers"] / b["workers"]
                     * float(basis.get("server_factor", 1)))


def scaled_tact_tests(b: dict) -> int:
    """Время набора тестов такта из замера `basis`: замер × запас на скорость ядра сервера
    `basis.tact_server_factor` (нет поля — 1: замер уже с сервера). Набор идёт одним процессом —
    число процессов полосы его не делит."""
    basis = b["basis"]
    return math.ceil(basis["tact_tests_s"] * float(basis.get("tact_server_factor", 1)))


def scaled_tree_mb(b: dict) -> float:
    """Память дерева сборки при числе процессов бюджета: наибольший процесс + рабочие процессы
    замера, взятые пропорционально числу процессов."""
    basis = b["basis"]
    one, whole = float(basis["memory_process_mb"]), float(max(_many(basis["memory_tree_mb"])))
    return one + (whole - one) * b["workers"] / basis["workers"]


def memory_floor_mb(b: dict) -> int:
    """Наименьший `MemoryHigh`: наибольшее из памяти сборки и памяти набора такта × запас."""
    need = max(scaled_tree_mb(b), float(b["basis"].get("tact_tests_memory_mb") or 0.0))
    return math.ceil(need * b["safety"])


# ------------------------------------------------------------------ согласие бюджета с собой

def basis_shape(b: dict) -> list[str]:
    """Форма замера `basis`: каждое поле — положительное число (или список таких чисел), запасы на
    сервер — по статусу. Пусто — формулы бюджета считаются; иначе они не считаются вовсе."""
    basis, out = b["basis"], []
    for name in MEASURED_MANY:
        values = _many(basis.get(name, []))
        if not values:
            hint = (" — замер сборки на цене у медианы: python ops/tools/worst_build.py"
                    if name == "build_worst_s" else "")
            out.append(f"basis.{name}: замера нет{hint}")
        elif not all(_number(v) for v in values):
            out.append(f"basis.{name}: {basis[name]!r} — положительное число или список таких чисел")
    for name in MEASURED_ONE:
        if not _number(basis.get(name)):
            out.append(f"basis.{name}: {basis.get(name)!r} — положительное число")
    if not (isinstance(basis.get("workers"), int) and not isinstance(basis.get("workers"), bool)
            and 1 <= basis["workers"] <= MAX_WORKERS):
        out.append(f"basis.workers: {basis.get('workers')!r} — число процессов полосы при замере, от 1 до "
                   f"{MAX_WORKERS}")
    for name, least in ESTIMATE_FACTORS.items():
        value = basis.get(name)
        if b.get("status") == "measured":
            if value is not None:
                out.append(f"status measured: basis.{name} снимается — замер уже с сервера, запас на сервер "
                           "ему не нужен")
        elif not (_number(value) and value >= least):
            out.append(f"status estimate: basis.{name}: {value!r} — запас оценки с ноутбука на скорость ядра "
                       f"сервера, не меньше {least:g}")
    return out


def findings(b: dict) -> list[str]:
    """Что в бюджете противоречит ему самому или замеру, на котором он стоит (пусто — всё сходится)."""
    out: list[str] = []
    if b.get("status") not in STATUSES:
        out.append(f"status: {b.get('status')!r} — допустимы {', '.join(STATUSES)}")
    if b.get("status") == "measured":
        try:
            date.fromisoformat(str(b.get("measured_on")))
        except ValueError:
            out.append("status measured: measured_on — день замера на сервере (ГГГГ-ММ-ДД)")
    elif b.get("measured_on") is not None:
        out.append("status estimate: measured_on обязан быть null — замера на сервере ещё нет")
    shape = basis_shape(b)
    if shape:
        return out + shape
    seconds, retry = b["seconds"], b["collect_retry"]
    for unit, steps in b["units"].items():
        out += [f"units.{unit}: шага {name!r} нет в seconds" for name in steps if name not in seconds]
    repeats = (retry["attempts"] - 1) * (seconds["collect_morning"] + retry["pause_s"])
    if seconds["collect_retries"] != repeats:
        out.append(f"seconds.collect_retries: {seconds['collect_retries']} — обязан быть {repeats} "
                   "((attempts − 1) × (collect_morning + pause_s))")
    workers, basis = b["workers"], b["basis"]
    if not (isinstance(workers, int) and 1 <= workers <= min(MAX_WORKERS, int(b["server_cores"]))):
        out.append(f"workers: {workers!r} — целое от 1 до числа ядер сервера ({b['server_cores']}), не больше "
                   f"{MAX_WORKERS}")
        return out
    if seconds["build"] < scaled_build(b):
        out.append(f"seconds.build: {seconds['build']} — ниже замера: {max(build_measurements(b)):g} с на "
                   f"{basis['workers']} процессах (верх обычного и худшего случая) дают {scaled_build(b)} с на "
                   f"{workers} (запас на сервер × {basis.get('server_factor', 1)})")
    for name in ("tact_tests", "future_tests"):
        if seconds[name] < scaled_tact_tests(b):
            out.append(f"seconds.{name}: {seconds[name]} — ниже замера набора такта: {basis['tact_tests_s']} с "
                       f"дают {scaled_tact_tests(b)} с (запас на сервер × {basis.get('tact_server_factor', 1)})")
    if seconds["tact_tests"] > b["tact_tests_target"]:
        out.append(f"seconds.tact_tests: {seconds['tact_tests']} — дольше цели сервера tact_tests_target "
                   f"({b['tact_tests_target']} с): метка tact снимается с самых долгих тестов")
    if b["status"] == "estimate":
        if basis["tact_tests_s"] > b["tact_tests_laptop_limit"]:
            out.append(f"basis.tact_tests_s: {basis['tact_tests_s']} — набор такта на ноутбуке дольше предела "
                       f"tact_tests_laptop_limit ({b['tact_tests_laptop_limit']} с): метка tact снимается с "
                       "самых долгих тестов")
        if b["ci"]["laptop_seconds"]["tact"] < basis["tact_tests_s"]:
            out.append(f"ci.laptop_seconds.tact: {b['ci']['laptop_seconds']['tact']} — ниже замера набора такта "
                       f"на ноутбуке ({basis['tact_tests_s']} с)")
    goal = b.get("build_laptop_goal")
    if not (isinstance(goal, dict) and isinstance(goal.get("workers"), int) and not isinstance(goal["workers"], bool)
            and 1 <= goal["workers"] <= MAX_WORKERS and _number(goal.get("usual_s")) and _number(goal.get("worst_s"))
            and goal["usual_s"] <= goal["worst_s"]):
        out.append(f"build_laptop_goal: {goal!r} — цель времени сборки на рабочей машине: workers (от 1 до "
                   f"{MAX_WORKERS}), usual_s и worst_s — положительные числа, обычный случай не дольше худшего")
    if not any(line.startswith("units.") for line in out):
        for unit, window in restart_windows(b).items():
            if window >= DAY:
                out.append(f"restart: окно перезапуска такта {unit} — {window} с ({window / 3600:.1f} ч), не короче "
                           "суток: оно заперло бы и завтрашний запуск по таймеру. Окно = burst × (потолок такта + "
                           "пауза + остановка): с таким временем сборки нужно больше процессов полосы")
    memory = b["memory"]
    if memory["high_mb"] < memory_floor_mb(b):
        out.append(f"memory.high_mb: {memory['high_mb']} — ниже замера с запасом ({memory_floor_mb(b)} МБ при "
                   f"{workers} процессах)")
    if memory["max_mb"] <= memory["high_mb"]:
        out.append("memory.max_mb обязан быть выше memory.high_mb: между ними systemd замедляет, а не убивает")
    return out


def notes(b: dict) -> list[str]:
    """Что бюджету не противоречит, но требует решения: время сборки против цели (пусто — в цели)."""
    build, target, stop = b["seconds"]["build"], b["build_target"], b["build_stop"]
    if build > stop:
        return [f"сборка в бюджете {build} с — дольше {stop} с ({stop / 60:.0f} мин, build_stop): до включения "
                "таймеров решает ведущий (рычаги — ключи книги: строки обратного расчёта, уточняемые на полной "
                "полосе, число шагов уточнения, подвыборка, число прогонов полосы)"]
    if build > target:
        return [f"сборка в бюджете {build} с — дольше цели {target} с ({target / 60:.0f} мин, build_target)"]
    return []


def laptop_notes(b: dict) -> list[str]:
    """Замер рабочей машины против цели `build_laptop_goal` — обычный и худший случай, пересчитанные на число
    процессов цели (пусто — в цели). Только у оценки: у замера с сервера `basis` рабочую машину не несёт."""
    if b.get("status") != "estimate":
        return []
    goal, basis = b["build_laptop_goal"], b["basis"]
    out = []
    for name, key, words in (("build_s", "usual_s", "обычный случай"), ("build_worst_s", "worst_s", "худший случай")):
        spent = math.ceil(max(_many(basis[name])) * basis["workers"] / goal["workers"])
        if spent > goal[key]:
            out.append(f"сборка на рабочей машине, {words}: {spent} с при {goal['workers']} процессах — дольше цели "
                       f"{goal[key]:g} с ({goal[key] / 60:.0f} мин, build_laptop_goal.{key})")
    return out


# ------------------------------------------------------------------ производные строки файлов

def _unit_path(root: Path, unit: str) -> Path:
    found = sorted((root / "ops" / "systemd").glob(f"*-{unit}.service"))
    if len(found) != 1:
        raise BudgetError(f"юнит такта {unit!r}: ожидался один файл ops/systemd/*-{unit}.service, найдено {len(found)}")
    return found[0]


def derived(b: dict, root: Path | None = None) -> list[tuple[Path, str, str, str]]:
    """Строки, которые несут числа бюджета: (файл, имя, шаблон с группами «до» и «значение», значение)."""
    root = Path(root or ROOT)
    limits, lock = ceilings(b)
    windows, restart, memory = restart_windows(b), b["restart"], b["memory"]

    def key(name: str) -> str:
        return rf"(?m)^({re.escape(name)}=)(.*)$"

    out: list[tuple[Path, str, str, str]] = []
    for unit in b["units"]:
        path = _unit_path(root, unit)
        rows = {"RuntimeMaxSec": limits[unit], "MemoryHigh": f"{memory['high_mb']}M",
                "MemoryMax": f"{memory['max_mb']}M"}
        if unit in restart["units"]:
            rows.update({"StartLimitIntervalSec": windows[unit], "StartLimitBurst": restart["burst"],
                         "RestartSec": restart["pause_s"],
                         "RestartPreventExitStatus": " ".join(str(code) for code in restart["no_restart_codes"])})
        out += [(path, name, key(name), str(value)) for name, value in rows.items()]
    script = root / "ops" / "run.sh"
    retry = b["collect_retry"]
    for name, value in (("LOCK_WAIT_SECONDS", lock), ("COLLECT_RETRY_ATTEMPTS", retry["attempts"]),
                        ("COLLECT_RETRY_PAUSE", retry["pause_s"]), ("BUDGET_WORKERS", b["workers"])):
        out.append((script, name, key(name), str(value)))
    # Задание CI — часть набора в матрице (`- part: имя` и `minutes:` следом) или задание целиком
    # (`имя:` и его `timeout-minutes:`) в одном из файлов .github/workflows/.
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    texts = {path: path.read_bytes().decode("utf-8") for path in workflows}
    for part, minutes in ci_minutes(b).items():
        name = re.escape(part)
        patterns = (rf"(?m)^( +- part: {name}\n +minutes: )(\d+)$",
                    rf"(?m)^(  {name}:\n(?:(?!  \S).*\n)*?    timeout-minutes: )(\d+)$")
        found = [(path, pattern) for path in workflows for pattern in patterns if re.search(pattern, texts[path])]
        if len(found) != 1:
            raise BudgetError(f"задание CI {part!r}: ожидалось одно место в .github/workflows/*.yml, найдено {len(found)}")
        out.append((found[0][0], f"CI, задание {part}", found[0][1], str(minutes)))
    return out


def apply(b: dict, root: Path | None = None, *, write: bool = False) -> list[str]:
    """Расхождения производных строк с бюджетом; с `write` — вписывает значения. Строки, которой
    нет или которая повторяется, не угадывает — `BudgetError`."""
    texts: dict[Path, str] = {}
    changed: set[Path] = set()
    out: list[str] = []
    for path, name, pattern, value in derived(b, root):
        if path not in texts:
            if not path.exists():
                raise BudgetError(f"нет файла {path.name}")
            texts[path] = path.read_bytes().decode("utf-8")
        hits = re.findall(pattern, texts[path])
        if len(hits) != 1:
            raise BudgetError(f"{path.name}: строка «{name}» встречается {len(hits)} раз — ожидалась одна")
        have = hits[0][1]
        if have != value:
            out.append(f"{path.name}: {name} — {have}, по бюджету {value}")
            if write:
                texts[path] = re.sub(pattern, lambda m: m.group(1) + value, texts[path], count=1)
                changed.add(path)
    for path in sorted(changed):
        path.write_bytes(texts[path].encode("utf-8"))
    return out


# ------------------------------------------------------------------ печать

def show(b: dict) -> str:
    limits, lock = ceilings(b)
    windows = restart_windows(b)
    basis, memory = b["basis"], b["memory"]
    state = ("замер на сервере " + str(b["measured_on"]) if b["status"] == "measured"
             else "ОЦЕНКА до замера на сервере")
    server = "" if b["status"] == "measured" else f" (запас на сервер × {basis['server_factor']:g})"
    tact = "" if b["status"] == "measured" else (f" (предел ноутбука {b['tact_tests_laptop_limit']} с; запас на "
                                                 f"сервер × {basis['tact_server_factor']:g})")
    lines = [f"бюджет: {state}; основание — {basis['machine']}, {basis['measured_on']}",
             f"процессов полосы (BANK_WORKERS): {b['workers']} из {b['server_cores']} ядер сервера; запас × {b['safety']}",
             f"сборка: замер {_span(_many(basis['build_s']))} с, худший случай (цена у медианы) "
             f"{_span(_many(basis['build_worst_s']))} с на {basis['workers']} процессах → не меньше "
             f"{scaled_build(b)} с на {b['workers']}{server}; в бюджете {b['seconds']['build']} с; цель — "
             f"{b['build_target']} с, дольше {b['build_stop']} с решает ведущий",
             f"цель рабочей машины при {b['build_laptop_goal']['workers']} процессах: обычный случай — не дольше "
             f"{b['build_laptop_goal']['usual_s']:g} с, худший — не дольше {b['build_laptop_goal']['worst_s']:g} с",
             f"тесты такта: замер {basis['tact_tests_s']:g} с → не меньше {scaled_tact_tests(b)} с{tact}; в бюджете "
             f"{b['seconds']['tact_tests']} с; цель сервера — {b['tact_tests_target']} с",
             f"память: сборка ≈ {scaled_tree_mb(b):.0f} МБ на {b['workers']} процессах, набор такта "
             f"{basis.get('tact_tests_memory_mb') or '—'} МБ → MemoryHigh не меньше {memory_floor_mb(b)} МБ; "
             f"в бюджете MemoryHigh {memory['high_mb']} МБ, MemoryMax {memory['max_mb']} МБ",
             "", "такт            шаги, с    RuntimeMaxSec    окно перезапуска"]
    for unit, steps in b["units"].items():
        total = sum(b["seconds"][name] for name in steps)
        window = f"{windows[unit]} с ({windows[unit] / 3600:.1f} ч)" if unit in windows else "—"
        waits = " (с ожиданием замка)" if unit in b["lock_waiters"] else ""
        lines.append(f"{unit:<15} {total:>7}    {limits[unit]:>6} с ({limits[unit] / 60:.0f} мин){waits}    {window}")
    lines += ["", f"ожидание замка (LOCK_WAIT_SECONDS): {lock} с",
              "CI, потолки заданий: " + ", ".join(f"{part} — {minutes} мин" for part, minutes in ci_minutes(b).items())]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="budgets.py", description="бюджет тактов: таблица, сверка, запись производных")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="сверить производные числа с бюджетом (код 1 — расходятся)")
    mode.add_argument("--write", action="store_true", help="вписать производные числа в юниты, run.sh и файлы CI")
    ap.add_argument("--root", type=Path, default=ROOT, help="корень дерева (по умолчанию — этот репозиторий)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    b = load(args.root / "ops" / "budgets.json")
    wrong = findings(b)
    for line in wrong:
        print(f"бюджет: {line}")
    if wrong:
        print("ops/budgets.json противоречит себе или своему замеру — производные числа не трогаю")
        return 1
    for line in notes(b) + laptop_notes(b):
        print(f"ВНИМАНИЕ: {line}")
    if not (args.check or args.write):
        print(show(b))
        return 0
    try:
        diff = apply(b, args.root, write=args.write)
    except BudgetError as exc:
        print(f"ОТКАЗ: {exc}")
        return 1
    for line in diff:
        print(("вписано — " if args.write else "расходится — ") + line)
    if args.write:
        print(f"готово: вписано строк — {len(diff)}" if diff else "готово: менять нечего")
        return 0
    print("производные числа равны бюджету" if not diff
          else "производные числа расходятся с бюджетом: python ops/tools/budgets.py --write")
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
