# -*- coding: utf-8 -*-
"""Юниты systemd, бюджет времени и памяти, образец env-файла, .gitignore и .gitattributes.

Юниты ставятся на сервер побайтовыми копиями из `ops/systemd/`, поэтому их
свойства проверяются здесь, до установки: шаблон защиты панелей владельца,
политика перезапуска (тревога — код 8 — не повторяется ни у одного такта, провал
шага — повторяется в пределах окна `StartLimitIntervalSec`, выведенного из
бюджета), расписание (DESIGN §6.1) и потолки `RuntimeMaxSec`, посчитанные из
`ops/budgets.json` по одной формуле с `LOCK_WAIT_SECONDS` в `ops/run.sh`; память
юнитов, число процессов полосы, повтор сбора внутри утреннего такта и порог
сторожа объёма ветки данных — оттуда же.

Бюджет — единственное место, где его числа пишутся руками: производные строки
юнитов, `ops/run.sh` и файлов CI вписывает `ops/tools/budgets.py --write`. Формулы
здесь записаны второй раз, независимо от инструмента; сам инструмент проверяется
на копии дерева (одна правка бюджета — одна перегенерация). Бюджет не ниже
замера, на котором стоит (`basis`), — и с оценкой по замеру ноутбука, и с замером
сервера: проверки не зависят от статуса бюджета, а путь «замер на сервере»
(шаг 8 установки) пройден на копии дерева.

Быстрые (доли секунды) — в такте сервера (метка `tact` модуля): юниты, бюджеты и
env-файл проверяются и на том коде, который пересборка вот-вот опубликует;
тесты документов (`docs`) такт исключает выражением.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"
UNITS = OPS / "systemd"
MODES = ("collect", "release-watch", "daily", "rebuild")
REPO = "/srv/dash/repo-850-svcb"
ENV_PATH = "/usr/local/etc/svcb-850/env"
MSK_OFFSET_HOURS = 3

# INTERFACES §8: переменные, которые конвейер берёт из env-файла сервера. Ядро и
# индикаторы читают свои без префикса банка (BANK_*, решение ведущего 01.10.2026,
# C5); у переменных только эксплуатации — префикс банка (слой ops у банка свой).
CORE_VARIABLES = {"BANK_STATE_DIR", "BANK_DATA_REPO_DIR", "BANK_WORKERS"}
OPS_VARIABLES = CORE_VARIABLES | {
    "SVCB_REPO_DIR", "SVCB_VENV", "SVCB_PYTHON",
    "TINVEST_TOKEN", "SVCB_RELEASE_REMOTE", "SVCB_GIT_NAME", "SVCB_GIT_EMAIL", "SVCB_PUBLIC_URL",
    "SVCB_VERIFY_TIMEOUT", "SVCB_VERIFY_PAUSE", "SVCB_PUSH_BACKOFF",
    "SVCB_FUTURE_WEEKDAY", "SVCB_FUTURE_DAYS",
}
# Служебные: проба тревоги и метка перезапуска run.sh (не из env-файла), папка
# передачи (на сервере не задаётся), файл записи теста мутаций (ставит параллельный
# прогон ops/tools/ptest.py) и часть матрицы мутаций CI (ставит .github/workflows/ci.yml; INTERFACES §8).
SERVICE_VARIABLES = {"SVCB_SIMULATE_FAILURE", "SVCB_REEXEC", "BANK_HANDOFF_DIR", "BANK_MUTATION_RECORD",
                     "BANK_MUTATION_SHARD"}
VARIABLE = r"(?:SVCB|BANK)_[A-Z_]+"


def _unit(path: Path) -> dict[str, dict[str, list[str]]]:
    """Юнит как {секция: {ключ: [значения]}} — ключ может повторяться."""
    sections: dict[str, dict[str, list[str]]] = {}
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        key, _, value = line.partition("=")
        assert current is not None, f"{path.name}: {line!r} вне секции"
        current.setdefault(key.strip(), []).append(value.strip())
    return sections


def _one(unit: dict, section: str, key: str) -> str:
    values = unit.get(section, {}).get(key, [])
    assert len(values) == 1, f"{section}.{key}: {values}"
    return values[0]


def _budgets() -> dict:
    return json.loads((OPS / "budgets.json").read_text(encoding="utf-8"))


def _round_up(value: float, step: int) -> int:
    """Вверх до кратного шагу; девять знаков гасят хвост двоичной дроби произведения."""
    return math.ceil(round(value / step, 9)) * step


def _ceilings(b: dict | None = None) -> tuple[dict[str, int], int]:
    """Потолки юнитов и ожидание замка по ops/budgets.json (формула — поле about)."""
    b = b or _budgets()
    step = int(b["round_to"])

    def run(unit: str) -> int:
        return _round_up(sum(b["seconds"][k] for k in b["units"][unit]) * b["safety"], step)

    lock = max(run(u) for u in b["lock_holders"])
    return {u: run(u) + (lock if u in b["lock_waiters"] else 0) for u in b["units"]}, lock


def _restart_windows(b: dict | None = None) -> dict[str, int]:
    """Окно перезапуска юнитов с Restart по ops/budgets.json (формула — поле about)."""
    b = b or _budgets()
    r, step = b["restart"], int(b["round_to"])
    ceilings, _ = _ceilings(b)
    return {u: _round_up(r["burst"] * (ceilings[u] + r["pause_s"] + r["stop_s"]), step) for u in r["units"]}


def _tool():
    """Инструмент бюджета `ops/tools/budgets.py` модулем."""
    spec = importlib.util.spec_from_file_location("budgets_for_units", OPS / "tools" / "budgets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _publish():
    spec = importlib.util.spec_from_file_location("publish_for_units", OPS / "publish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_there_are_exactly_four_pairs_of_units():
    names = sorted(p.name for p in UNITS.iterdir())
    assert names == sorted(f"svcb850-{m}.{kind}" for m in MODES for kind in ("service", "timer"))
    for path in UNITS.iterdir():
        assert b"\r\n" not in path.read_bytes(), f"{path.name}: CRLF"


@pytest.mark.parametrize("mode", MODES)
def test_every_service_follows_the_panel_template(mode):
    unit = _unit(UNITS / f"svcb850-{mode}.service")
    memory = _budgets()["memory"]
    assert "Install" not in unit, "юнит запускает таймер; [Install] дал бы прогон при загрузке"
    expected = {
        "Type": "exec", "User": "dash", "Group": "dash",
        "WorkingDirectory": REPO,
        "ExecStart": f"/bin/bash {REPO}/ops/run.sh {mode}",
        "SyslogIdentifier": "svcb850", "StateDirectory": "svcb-850",
        # без режима systemd при каждом старте возвращает каталогу состояния 0755 (архив и журналы — всем)
        "StateDirectoryMode": "0750",
        "PrivateTmp": "yes", "ProtectSystem": "strict", "ProtectHome": "yes",
        "NoNewPrivileges": "yes", "ReadWritePaths": REPO,
        "MemoryHigh": f"{memory['high_mb']}M", "MemoryMax": f"{memory['max_mb']}M", "Nice": "10",
        "ExecStopPost": "-+/usr/local/sbin/dash-alert %n",
    }
    for key, value in expected.items():
        assert _one(unit, "Service", key) == value, key
    assert unit["Service"]["Environment"] == [f"ENV_FILE={ENV_PATH}", "PYTHONUNBUFFERED=1"]
    assert _one(unit, "Unit", "Wants") == "network-online.target"
    assert _one(unit, "Unit", "After") == "network-online.target"


def test_the_units_do_not_load_the_env_file_into_their_environment():
    """Токен T-Invest получает только процесс сборщика T-Invest (INTERFACES §8): env-файл
    читает сам run.sh и тут же снимает токен из окружения такта. `EnvironmentFile` в юните
    положил бы токен в окружение всего юнита — и такта, и моста тревог."""
    for mode in MODES:
        service = _unit(UNITS / f"svcb850-{mode}.service")["Service"]
        assert "EnvironmentFile" not in service, mode
        assert not any("TOKEN" in value for value in service.get("Environment", [])), mode
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    assert f"ENV_FILE=${{ENV_FILE:-{ENV_PATH}}}" in script, "путь юнита и умолчание run.sh — один файл"


def test_only_the_morning_tact_is_cut_off_from_the_deploy_key():
    """Утренний такт разбирает чужой HTML (PDF разбирает дозор) и ничего не публикует —
    ключ записи ему недоступен. Дозору, суточному такту и пересборке каталог нужен.
    Это наименьшие права, а не граница доверия (тот же пользователь пишет в код)."""
    for mode in MODES:
        hidden = _unit(UNITS / f"svcb850-{mode}.service")["Service"].get("InaccessiblePaths", [])
        if mode == "collect":
            assert hidden == ["/srv/dash/.ssh"]
        else:
            assert not any(".ssh" in h for h in hidden), mode


def test_the_restart_policy_repeats_failures_and_not_alarms():
    """Политика тревог (INTERFACES §6): тревога (8) не повторяется ни у одного такта —
    повтор её не снимет; провал шага (1) и занятый замок (75) повторяются у утреннего и
    суточного тактов. Дозор и пересборка не повторяются: их следующая проверка — через
    10–15 минут. Числа — из ops/budgets.json (restart), а не литералами теста."""
    restart = _budgets()["restart"]
    assert set(restart["units"]) == {"collect", "daily"}
    assert {8, 64, 78} <= set(restart["no_restart_codes"]), "тревога и ошибки настройки не повторяются"
    assert not {1, 75} & set(restart["no_restart_codes"]), "провал шага и занятый замок повторяются"
    for mode in restart["units"]:
        service = _unit(UNITS / f"svcb850-{mode}.service")["Service"]
        assert service["Restart"] == ["on-failure"], mode
        assert service["RestartSec"] == [str(restart["pause_s"])], mode
        prevent = [int(x) for x in _one({"Service": service}, "Service", "RestartPreventExitStatus").split()]
        assert prevent == restart["no_restart_codes"], mode

    for mode in set(MODES) - set(restart["units"]):
        service = _unit(UNITS / f"svcb850-{mode}.service")
        assert "Restart" not in service["Service"] and "RestartPreventExitStatus" not in service["Service"], mode
        assert "StartLimitIntervalSec" not in service["Unit"], mode


def test_the_restart_window_holds_every_allowed_start():
    """Окно systemd отсчитывается от первого старта и не скользит: отказ получает только
    старт сверх `StartLimitBurst` ВНУТРИ окна. Окно короче, чем burst прогонов с паузами,
    не ограничивает ничего — стойкий код 1 повторялся бы весь день (десятки полных сборов
    ЦБ, T-Invest, ISS и сборок на общем сервере). Поэтому окно выводится из потолка
    прогона, а не пишется на глаз."""
    restart, windows = _budgets()["restart"], _restart_windows()
    ceilings, _ = _ceilings()
    for mode, window in windows.items():
        unit = _unit(UNITS / f"svcb850-{mode}.service")["Unit"]
        assert unit["StartLimitBurst"] == [str(restart["burst"])], mode
        assert unit["StartLimitIntervalSec"] == [str(window)], (
            f"svcb850-{mode}.service: StartLimitIntervalSec обязан быть {window} по ops/budgets.json")
        longest = restart["burst"] * (ceilings[mode] + restart["pause_s"] + restart["stop_s"])
        assert window >= longest, (mode, "окно короче burst самых долгих прогонов")
        assert window < 24 * 3600, (mode, "окно длиннее суток заперло бы и завтрашний запуск по таймеру")
    assert restart["burst"] >= 2 and restart["stop_s"] >= 90, "stop_s — предел ExecStopPost (TimeoutStopSec)"


def _starts_within(run_s: int, pause_s: int, burst: int, window: int, horizon: int) -> int:
    """Сколько раз systemd запустит юнит за horizon секунд, если каждый прогон длится run_s
    и кончается кодом 1 (модель ratelimit: окно — от первого старта в нём, не скользит)."""
    starts, t, begin, count = 0, 0, None, 0
    while t < horizon:
        if begin is None or t - begin >= window:
            begin, count = t, 0
        if count >= burst:
            break                                   # start-limit-hit: юнит стоит до таймера
        count += 1
        starts += 1
        t += run_s + pause_s
    return starts


def test_a_persistent_failure_is_retried_at_most_burst_times_a_day():
    """Модель того, что было не так: при окне 1800 с прогон дольше ≈ 7 минут повторялся
    без предела. С окном из бюджета стойкий провал даёт не больше burst стартов при любой
    длительности прогона вплоть до потолка."""
    restart, windows = _budgets()["restart"], _restart_windows()
    ceilings, _ = _ceilings()
    day = 24 * 3600
    assert _starts_within(900, 180, 3, 1800, day) > 50, "модель обязана воспроизводить прежний дефект"
    for mode, window in windows.items():
        for run_s in (5, 60, 420, 900, 3000, ceilings[mode] + restart["stop_s"]):
            got = _starts_within(run_s, restart["pause_s"], restart["burst"], window, day)
            assert got <= restart["burst"], (mode, run_s, got)


def test_the_collect_retry_of_run_sh_follows_the_budget():
    """Повтор сбора внутри утреннего такта: число попыток и пауза в run.sh — из
    ops/budgets.json (collect_retry), а время повторов входит в потолок юнита."""
    b = _budgets()
    retry = b["collect_retry"]
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    assert re.findall(r"^COLLECT_RETRY_ATTEMPTS=(\d+)$", script, re.M) == [str(retry["attempts"])]
    assert re.findall(r"^COLLECT_RETRY_PAUSE=(\d+)$", script, re.M) == [str(retry["pause_s"])]
    assert 2 <= retry["attempts"] <= 5 and retry["pause_s"] >= 60
    assert b["seconds"]["collect_retries"] == (retry["attempts"] - 1) * (
        b["seconds"]["collect_morning"] + retry["pause_s"])
    assert "collect_retries" in b["units"]["collect"]
    assert all("collect_retries" not in steps for unit, steps in b["units"].items() if unit != "collect")


def test_the_data_branch_alarm_threshold_is_in_the_budget():
    """Сторож объёма ветки данных (INTERFACES §6): порог — 700 МБ при пределе сайта
    GitHub Pages 1 ГБ; `ops/publish.py` читает его из бюджета."""
    publish = _publish()
    assert _budgets()[publish.ALERT_KEY] == 700
    assert publish.alert_bytes(publish.Config(state_dir=ROOT / "var" / "state")) == 700 * 1024 * 1024
    assert publish.BUDGETS == OPS / "budgets.json"


def test_run_sh_ends_alarms_with_the_code_the_units_do_not_repeat():
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    finish = re.search(r"^finish\(\) \{(.*?)^\}", script, re.M | re.S).group(1)
    assert "exit 8" in finish and "ТРЕВОГА (код 8)" in finish and "готово:" in finish
    assert "ПРОВАЛ на шаге «$STEP»" in script


def _schedule() -> dict:
    return json.loads((OPS / "schedule.json").read_text(encoding="utf-8"))


def _schedule_tool():
    """Инструмент расписания `ops/tools/schedule.py` модулем."""
    spec = importlib.util.spec_from_file_location("schedule_for_units", OPS / "tools" / "schedule.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _calendars(s: dict | None = None) -> dict[str, list[str]]:
    """Строки `OnCalendar` тактов по ops/schedule.json — второй раз, независимо от инструмента: утренний сбор и
    суточный такт — одно время суток, пересборка — перечень минут часа; строки дозора читает `_ticks`."""
    timers = (s or _schedule())["timers"]
    days = lambda mode: f"{timers[mode]['days']} " if timers[mode].get("days") else ""  # noqa: E731
    return {"collect": [f"{days('collect')}*-*-* {timers['collect']['at_utc']}:00 UTC"],
            "daily": [f"{days('daily')}*-*-* {timers['daily']['at_utc']}:00 UTC"],
            "rebuild": ["*:" + ",".join(f"{m:02d}" for m in timers["rebuild"]["minutes"])]}


@pytest.mark.parametrize("mode,persistent", [("collect", "true"), ("daily", "true"), ("rebuild", None),
                                              ("release-watch", None)])
def test_the_timers_follow_the_schedule(mode, persistent):
    """Расписание пишется руками в одном месте — ops/schedule.json: строки `OnCalendar` таймеров равны ему
    (их вписывает `python ops/tools/schedule.py --write`). Утренний сбор — каждый день, суточный такт — по
    будням, пересборка — каждые 15 минут."""
    timer = _unit(UNITS / f"svcb850-{mode}.timer")
    tool, s = _schedule_tool(), _schedule()
    assert timer["Timer"]["OnCalendar"] == tool.calendars(s)[mode]
    if mode != "release-watch":
        assert timer["Timer"]["OnCalendar"] == _calendars(s)[mode]
    assert _one(timer, "Timer", "Unit") == f"svcb850-{mode}.service"
    assert timer["Timer"].get("Persistent", [None]) == [persistent]
    assert _one(timer, "Install", "WantedBy") == "timers.target"
    timers = s["timers"]
    assert "days" not in timers["collect"] and timers["daily"]["days"] == "Mon..Fri" == timers["release-watch"]["days"]
    minutes = timers["rebuild"]["minutes"]
    assert len(minutes) == 4 and all(b - a == 15 for a, b in zip(minutes, minutes[1:])), minutes


def _ticks(calendar: str) -> list[tuple[int, int]]:
    """Минуты срабатывания для вида `Mon..Fri *-*-* H[..H2]:MM/10:00 UTC` (часы UTC)."""
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d{2})(?:\.\.(\d{2}))?:(\d{2})/(\d+):00 UTC", calendar)
    assert m, calendar
    h1, h2 = int(m.group(1)), int(m.group(2) or m.group(1))
    return [(h, minute) for h in range(h1, h2 + 1) for minute in range(int(m.group(3)), 60, int(m.group(4)))]


def _watch_ticks() -> list[int]:
    """Проверки таймера дозора, минуты UTC от полуночи, — разбором его строк `OnCalendar`."""
    timer = _unit(UNITS / "svcb850-release-watch.timer")
    return sorted(h * 60 + m for c in timer["Timer"]["OnCalendar"] for h, m in _ticks(c))


def _covers(ticks: list[int], window: list[str], step: int = 10) -> bool:
    """Таймер покрывает окно (московское время): первая проверка — в начале окна, последняя — до его конца
    и не дальше шага от него, шаг ровный."""
    to_min = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:]) - MSK_OFFSET_HOURS * 60  # noqa: E731
    start, end = (to_min(x) for x in window)
    return (ticks[0] == start and ticks[-1] < end <= ticks[-1] + step
            and all(b - a == step for a, b in zip(ticks, ticks[1:])))


def test_the_release_watch_ticks_follow_the_window_of_the_schedule():
    """Окно дозора и его шаг — ops/schedule.json: первая проверка таймера — в начале окна, последняя — до его
    конца, шаг 10 минут. Строки таймера разбираются здесь сами, без инструмента."""
    s = _schedule()
    watch = s["timers"]["release-watch"]
    assert s["msk_offset_hours"] == MSK_OFFSET_HOURS and watch["every_min"] == 10
    ticks = _watch_ticks()
    assert _covers(ticks, watch["window_msk"]), (ticks, watch["window_msk"])
    assert ticks == _schedule_tool().watch_ticks(s)


def test_the_release_watch_ticks_cover_the_window_of_the_indicators():
    """Справочный ключ `schedule.watch_window_msk` настроек сборщиков называет то же окно, что расписание и
    таймер дозора: первая проверка — в начале окна, последняя — до его конца, шаг 10 минут."""
    cfg = yaml.safe_load((ROOT / "data" / "indicators" / "sources.yaml").read_text(encoding="utf-8"))
    window = cfg["schedule"]["watch_window_msk"]
    assert window == _schedule()["timers"]["release-watch"]["window_msk"], (
        "окно дозора в data/indicators/sources.yaml расходится с ops/schedule.json")
    assert _covers(_watch_ticks(), window), window


def test_the_schedule_keeps_its_distance_from_the_neighbours(tmp_path, capsys):
    """Сервер общий: расписание держит расстояние до тактов соседних панелей (ops/schedule.json → neighbours,
    gaps_min) — утренние сборы форм ЦБ не идут вплотную, суточные сборки не накладываются, пересборка и
    проверки дозора — на своих минутах. Расписание, подошедшее к соседу ближе, инструмент называет и в таймеры
    не пишет."""
    tool, s = _schedule_tool(), _schedule()
    assert tool.findings(s) == []
    gaps = s["gaps_min"]
    assert gaps["collect"] >= 25 and gaps["daily"] >= 25 and gaps["rebuild"] >= 2 and gaps["release-watch"] >= 1
    panels = s["neighbours"]["panels"]
    date.fromisoformat(s["neighbours"]["checked_on"])
    assert len(panels) >= 4 and len({n["panel"] for n in panels}) == len(panels)
    assert all(n["collect_utc"] and n["daily_utc"] for n in panels), "утренний и суточный такт соседа известны"
    seen = {(mode, name): (apart, least) for mode, name, apart, least in tool.distances(s)}
    assert all(apart >= least for apart, least in seen.values()), seen
    banks = [n for n in panels if n["watch_minute"] is not None]
    assert len(banks) >= 2, "проверки дозора соседних банков названы"
    # второй счёт расстояний — здесь, без инструмента
    at = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])  # noqa: E731
    ring = lambda a, b, cycle: min((a - b) % cycle, (b - a) % cycle)  # noqa: E731
    timers = s["timers"]
    for n in panels:
        for mode in ("collect", "daily"):
            assert seen[(mode, n["panel"])][0] == ring(at(timers[mode]["at_utc"]), at(n[f"{mode}_utc"]), 24 * 60)
        if n["rebuild_minute"] is not None:
            assert seen[("rebuild", n["panel"])][0] == ring(timers["rebuild"]["minutes"][0], n["rebuild_minute"], 15)
        if n["watch_minute"] is not None:
            assert seen[("release-watch", n["panel"])][0] == ring(_watch_ticks()[0] % 10, n["watch_minute"], 10)
    # такт на минутах соседа — противоречие расписания: названо словами, таймеры не тронуты
    root = _tree_copy(tmp_path)
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p.name != "schedule.json"]
    before = {p: p.read_bytes() for p in files}
    for mode, edit in (("collect", lambda x: x["timers"]["collect"].update(at_utc=banks[-1]["collect_utc"])),
                       ("daily", lambda x: x["timers"]["daily"].update(at_utc=banks[0]["daily_utc"])),
                       ("rebuild", lambda x: x["timers"]["rebuild"].update(
                           minutes=[banks[0]["rebuild_minute"] % 15 + 15 * k for k in range(4)])),
                       ("release-watch", lambda x: x["timers"]["release-watch"].update(
                           window_msk=[f"09:4{banks[0]['watch_minute'] % 10}", "14:00"]))):
        close = json.loads(json.dumps(s))
        edit(close)
        named = [line for line in tool.findings(close) if line.startswith(f"{mode}: до такта панели")]
        assert named and f"gaps_min.{mode}" in named[0], (mode, tool.findings(close))
        (root / "ops" / "schedule.json").write_text(json.dumps(close, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8", newline="\n")
        capsys.readouterr()
        assert tool.main(["--write", "--root", str(root)]) == 1 and tool.main(["--check", "--root", str(root)]) == 1
        told = capsys.readouterr().out
        assert told.count(f"расписание: {mode}: до такта панели") == 2 and "таймеры не трогаю" in told
        assert before == {p: p.read_bytes() for p in files}
    # негодная форма — строка «расписание: …», а не трассировка
    for path, bad in ((("timers", "collect", "at_utc"), "5:50"), (("timers", "daily", "days"), "будни"),
                      (("timers", "rebuild", "minutes"), [4, 19, 30, 49]), (("timers", "release-watch", "every_min"), 7),
                      (("timers", "release-watch", "window_msk"), ["14:00", "09:46"])):
        wrong = json.loads(json.dumps(s))
        node = wrong
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = bad
        assert any(line.startswith(".".join(path)) for line in tool.findings(wrong)), (path, tool.findings(wrong))


def test_the_schedule_keeps_off_the_minutes_of_differently_named_tacts(tmp_path, capsys):
    """Расстояние сверяется и накрест: сбор не встаёт на суточный такт соседа (и суточный — на сбор), пересборка —
    на минуту чужого дозора, дозор — на минуту чужой пересборки, лёгкая проверка — на минуту своего тяжёлого такта.
    Лёгкая проверка соседа внутри своего тяжёлого окна противоречием не считается. Расписание без блока расстояний
    или соседей — строка «расписание: …», а не трассировка."""
    tool, s = _schedule_tool(), _schedule()
    panels, timers = s["neighbours"]["panels"], s["timers"]
    cross = tool.crossings(s)
    assert all(apart >= least for _, _, _, apart, least, _ in cross), cross
    # второй счёт — здесь, без инструмента: минуты часа своих лёгких проверок против чужих и своих тактов
    at = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])  # noqa: E731
    ring = lambda a, b, cycle: min((a - b) % cycle, (b - a) % cycle)  # noqa: E731
    rebuild, step = timers["rebuild"]["minutes"], timers["release-watch"]["every_min"]
    period = rebuild[1] - rebuild[0]
    watch = sorted({t % 60 for t in _watch_ticks()})
    seen = {(mode, words, whose): apart for mode, words, whose, apart, _, _ in cross}
    for n in panels:
        whose = f"панели «{n['panel']}»"
        assert seen[("collect", "суточного такта", whose)] == ring(at(timers["collect"]["at_utc"]), at(n["daily_utc"]), 24 * 60)
        assert seen[("daily", "утреннего сбора", whose)] == ring(at(timers["daily"]["at_utc"]), at(n["collect_utc"]), 24 * 60)
        if n["watch_minute"] is not None:
            theirs = [m for m in range(60) if m % step == n["watch_minute"] % step]
            assert seen[("rebuild", "проверки дозора", whose)] == min(ring(a, b, 60) for a in rebuild for b in theirs)
        if n["rebuild_minute"] is not None:
            theirs = [m for m in range(60) if m % period == n["rebuild_minute"] % period]
            assert seen[("release-watch", "пересборки", whose)] == min(ring(a, b, 60) for a in watch for b in theirs)
    for mode, words in (("collect", "утреннего сбора"), ("daily", "суточного такта")):
        minute = at(timers[mode]["at_utc"]) % 60
        assert seen[("rebuild", words, "этой панели")] == min(ring(a, minute, 60) for a in rebuild) >= 1
        assert seen[("release-watch", words, "этой панели")] >= 1
    # такт на минуте разноимённого такта — противоречие расписания: названо словами, таймеры не тронуты
    banks = [n for n in panels if n["watch_minute"] is not None and n["rebuild_minute"] is not None]
    assert len(banks) >= 2
    own = at(timers["collect"]["at_utc"]) % 60
    cases = (
        ("collect", "до суточного такта панели", lambda x: x["timers"]["collect"].update(at_utc=banks[0]["daily_utc"])),
        ("daily", "до утреннего сбора панели", lambda x: x["timers"]["daily"].update(at_utc=panels[1]["collect_utc"])),
        ("rebuild", "до проверки дозора панели", lambda x: x["timers"]["rebuild"].update(
            minutes=[banks[0]["watch_minute"] % 15 + 15 * k for k in range(4)])),
        ("release-watch", "до пересборки панели", lambda x: x["timers"]["release-watch"].update(
            window_msk=[f"09:4{banks[-1]['rebuild_minute'] % 10}", "14:00"])),
        ("rebuild", "до утреннего сбора этой панели", lambda x: x["timers"]["rebuild"].update(
            minutes=[own % 15 + 15 * k for k in range(4)])),
    )
    root = _tree_copy(tmp_path)
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p.name != "schedule.json"]
    before = {p: p.read_bytes() for p in files}
    for mode, words, edit in cases:
        close = json.loads(json.dumps(s))
        edit(close)
        named = [line for line in tool.findings(close) if line.startswith(f"{mode}: {words}")]
        assert named and "0 мин" in named[0], (mode, words, tool.findings(close))
        assert not [line for line in tool.findings(close) if "до такта панели" in line and not line.startswith(mode)]
        (root / "ops" / "schedule.json").write_text(json.dumps(close, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8", newline="\n")
        capsys.readouterr()
        assert tool.main(["--write", "--root", str(root)]) == 1 and tool.main(["--check", "--root", str(root)]) == 1
        told = capsys.readouterr().out
        assert f"расписание: {mode}: {words}" in told and "таймеры не трогаю" in told
        assert before == {p: p.read_bytes() for p in files}
    # лёгкая проверка соседа внутри своего тяжёлого окна — не противоречие: сбор на минуте чужой пересборки годен
    inside = json.loads(json.dumps(s))
    hour = timers["collect"]["at_utc"][:2]
    inside["timers"]["collect"]["at_utc"] = f"{hour}:{banks[0]['rebuild_minute'] % 15 + 45:02d}"
    assert not [line for line in tool.findings(inside) if line.startswith("collect:")], tool.findings(inside)
    # расписание без блока — строка «расписание: …», а не трассировка; панель без соседей — пустой список
    for block in ("gaps_min", "neighbours"):
        bare = json.loads(json.dumps(s))
        del bare[block]
        assert [line.split(":")[0] for line in tool.findings(bare)] == [block], tool.findings(bare)
        (root / "ops" / "schedule.json").write_text(json.dumps(bare, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8", newline="\n")
        capsys.readouterr()
        assert tool.main(["--check", "--root", str(root)]) == 1 and tool.main(["--root", str(root)]) == 1
        assert capsys.readouterr().out.count(f"расписание: {block}:") == 2
    for bad in ({"panels": "нет"}, {"checked_on": s["neighbours"]["checked_on"], "panels": [{"collect_utc": "03:10"}]},
                {"panels": []}):
        assert tool.findings({**s, "neighbours": bad})[0].startswith("neighbours:"), bad
    wrong = json.loads(json.dumps(s))
    wrong["neighbours"]["panels"][-1]["watch_minute"] = "05"
    wrong["gaps_min"]["rebuild"] = 2.5
    assert [line.split(":")[0] for line in tool.findings(wrong)] == ["gaps_min", "neighbours"], tool.findings(wrong)
    alone = {**json.loads(json.dumps(s)), "neighbours": {"checked_on": s["neighbours"]["checked_on"], "panels": []}}
    assert tool.findings(alone) == [] and tool.distances(alone) == []
    assert {whose for _, _, whose, _, _, _ in tool.crossings(alone)} == {"этой панели"}
    assert before == {p: p.read_bytes() for p in files}


def test_one_edit_of_the_schedule_and_one_regeneration_move_the_timers(tmp_path, capsys):
    """Смена расписания — одна правка ops/schedule.json и одна команда: сверка до записи называет расхождения,
    запись меняет только строки `OnCalendar`, повторная запись ничего не меняет. Окно дозора, начатое не с первой
    минуты сетки часа, даёт две строки; оборванный концом окна час — перечень минут."""
    tool, s = _schedule_tool(), _schedule()
    assert tool.apply(s, ROOT) == [], "после правки ops/schedule.json: python ops/tools/schedule.py --write"
    assert tool.main(["--check"]) == 0 and tool.main([]) == 0
    table = capsys.readouterr().out
    assert "строки таймеров равны расписанию" in table and "по Москве" in table and "соседи общего сервера" in table
    root = _tree_copy(tmp_path)
    path = root / "ops" / "schedule.json"
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p != path]
    before = {p: p.read_bytes() for p in files}
    moved = json.loads(json.dumps(s))
    moved["timers"]["collect"]["at_utc"] = "06:25"
    moved["timers"]["daily"]["at_utc"] = "20:45"
    moved["timers"]["rebuild"]["minutes"] = [14, 29, 44, 59]
    moved["timers"]["release-watch"]["window_msk"] = ["10:13", "12:30"]
    assert tool.findings(moved) == []
    path.write_text(json.dumps(moved, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert tool.main(["--check", "--root", str(root)]) == 1
    told = capsys.readouterr().out
    assert told.count("расходится — ") == 4 and "python ops/tools/schedule.py --write" in told
    assert tool.main(["--write", "--root", str(root)]) == 0 and tool.main(["--check", "--root", str(root)]) == 0
    got = {mode: _unit(root / "ops" / "systemd" / f"svcb850-{mode}.timer")["Timer"]["OnCalendar"] for mode in MODES}
    assert got["collect"] == ["*-*-* 06:25:00 UTC"] and got["daily"] == ["Mon..Fri *-*-* 20:45:00 UTC"]
    assert got["rebuild"] == ["*:14,29,44,59"]
    # 10:13–12:30 МСК = 07:13–09:23 UTC: неполный первый час, целый час и час, оборванный концом окна
    assert got["release-watch"] == ["Mon..Fri *-*-* 07:13/10:00 UTC", "Mon..Fri *-*-* 08:03/10:00 UTC",
                                    "Mon..Fri *-*-* 09:03,13,23:00 UTC"]
    assert tool.watch_ticks(moved) == list(range(7 * 60 + 13, 9 * 60 + 24, 10))
    for p in files:
        if p.suffix != ".timer":
            assert p.read_bytes() == before[p], p.name
            continue
        keep = lambda raw: [x for x in raw.split(b"\n") if not x.startswith(b"OnCalendar=")]  # noqa: E731
        assert keep(p.read_bytes()) == keep(before[p]) and b"\r" not in p.read_bytes(), p.name
    snapshot = {p: p.read_bytes() for p in files}
    capsys.readouterr()
    assert tool.main(["--write", "--root", str(root)]) == 0 and "менять нечего" in capsys.readouterr().out
    assert snapshot == {p: p.read_bytes() for p in files}
    # таймер без строки OnCalendar — отказ с именем файла, а не молчаливый пропуск
    timer = root / "ops" / "systemd" / "svcb850-daily.timer"
    timer.write_bytes(timer.read_bytes().replace(b"OnCalendar=", b"OnBootSec="))
    with pytest.raises(tool.ScheduleError, match="svcb850-daily.timer"):
        tool.apply(moved, root)


def test_runtime_ceilings_are_computed_from_the_budget_file():
    """Потолок юнита — из бюджета, а не на глаз: потолок ниже настоящего времени
    убил бы такт на середине (урок 850oa)."""
    ceilings, _ = _ceilings()
    for mode in MODES:
        unit = _unit(UNITS / f"svcb850-{mode}.service")
        assert int(_one(unit, "Service", "RuntimeMaxSec")) == ceilings[mode], (
            f"svcb850-{mode}.service: RuntimeMaxSec обязан быть {ceilings[mode]} по ops/budgets.json")


def test_the_lock_wait_equals_the_longest_lock_holder():
    """Плановый такт ждёт замок столько, сколько пересборка или дозор со сборкой
    могут его держать."""
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    found = re.findall(r"^LOCK_WAIT_SECONDS=(\d+)$", script, re.M)
    assert found == [str(_ceilings()[1])]


def _many(value) -> list:
    """Замер бюджета списком: число (один прогон) или список чисел."""
    return list(value) if isinstance(value, list) else [value]


def _measured(b: dict | None = None) -> dict:
    """Бюджет после шага 8 установки (ops/README.md §5), собранный из бюджета файла: `status: measured`
    и день замера; в `basis` — замер сервера ОДНИМ ЧИСЛОМ на поле, как его печатает замер, и без запасов
    на сервер; время сборки, тестов такта и память — по замеру. Набор такта на сервере идёт дольше, чем
    на ноутбуке (`ci.laptop_seconds.tact`), худший случай сборки — дольше обычного."""
    m = json.loads(json.dumps(b or _budgets()))
    basis = m["basis"]
    slow = float(basis.pop("server_factor", 2))
    basis.pop("tact_server_factor", None)
    m["status"], m["measured_on"] = "measured", basis["measured_on"]
    basis["machine"] = "сервер панелей (4 ядра), ручной замер сборки вне systemd"
    scale = basis["workers"] / m["workers"]
    basis["workers"] = m["workers"]
    basis["build_s"] = math.ceil(max(_many(basis["build_s"])) * scale * slow / 2) + 7
    basis["build_worst_s"] = basis["build_s"] * 2 + 11
    basis["memory_tree_mb"] = max(_many(basis["memory_tree_mb"])) + 5
    basis["tact_tests_s"] = m["ci"]["laptop_seconds"]["tact"] + 20
    m["seconds"]["build"] = basis["build_worst_s"]
    m["seconds"]["tact_tests"] = basis["tact_tests_s"]
    m["seconds"]["future_tests"] = max(m["seconds"]["future_tests"], basis["tact_tests_s"])
    high = math.ceil(max(basis["memory_tree_mb"], basis["tact_tests_memory_mb"]) * m["safety"])
    m["memory"] = {"high_mb": high, "max_mb": high + 192}
    return m


def _both_statuses() -> list[dict]:
    """Бюджет файла и он же в другом статусе: проверки бюджета не зависят от того, какой из двух стоит в
    файле, — иначе шаг 8 установки (замер на сервере) красил бы набор сервера."""
    b = _budgets()
    assert b["status"] in ("estimate", "measured")
    return [b] if b["status"] == "measured" else [b, _measured(b)]


def _honest(b: dict) -> None:
    assert b["status"] in ("estimate", "measured")
    if b["status"] == "measured":
        date.fromisoformat(b["measured_on"])
        assert not {"server_factor", "tact_server_factor"} & set(b["basis"]), "замер сервера — без запасов на сервер"
    else:
        assert b["measured_on"] is None
        assert "ДО ЗАМЕРА НА СЕРВЕРЕ" in b["basis"]["machine"], "оценка названа оценкой там, где её читают"
    date.fromisoformat(b["basis"]["measured_on"])
    assert set(b["units"]) == set(MODES)
    assert set(b["lock_holders"]) == {"rebuild", "release-watch"}
    assert set(b["lock_waiters"]) == {"collect", "daily"}
    for unit, steps in b["units"].items():
        assert steps and all(s in b["seconds"] for s in steps), unit
    assert b["seconds"]["tact_tests"] <= b["tact_tests_target"] == 270, (
        "тесты такта дольше цели сервера: сократить белый список (метка tact)")
    assert b["tact_tests_laptop_limit"] == 150 < b["tact_tests_target"], "набор такта на ноутбуке — не дольше 150 с"
    assert b["tact_tests_target"] < b["tact_tests_ci_ceiling"] == 300, (
        "потолок шага CI — 300 с и выше цели сервера: время дольше цели шаг печатает предупреждением")
    assert (b["build_target"], b["build_stop"]) == (1800, 2700), "цель сборки — 30 минут; дольше 45 — решает ведущий"
    assert b["build_laptop_goal"] == {"workers": 4, "usual_s": 900, "worst_s": 1500}, (
        "цель рабочей машины при четырёх процессах: обычный случай — 15 минут, худший — 25")
    assert b["seconds"]["verify_timeout"] == _publish().VERIFY_TIMEOUT, "окно сверки одно"
    assert all("pip" in steps for steps in b["units"].values())
    assert all({"build", "tact_tests"} <= set(b["units"][u]) for u in ("daily", "rebuild", "release-watch"))
    assert "build" not in b["units"]["collect"], "утренний такт выпуск не собирает"


def test_the_budget_file_is_honest_about_itself():
    """Оценка названа оценкой, замер — замером; цели времени названы числами. Проверка проходит в обоих
    статусах бюджета."""
    for b in _both_statuses():
        _honest(b)


def _floors(b: dict) -> tuple[int, int, int]:
    """(сборка, тесты такта, `MemoryHigh`) — наименьшие числа бюджета по его замеру. Формулы — второй раз,
    независимо от инструмента: сборка — верх замеров обычного и худшего случая, пересчитанный на число
    процессов бюджета (полоса делится между процессами поровну); тесты такта — замер набора; у оценки с
    ноутбука оба числа — с запасом на скорость ядра сервера; память — наибольшее из памяти сборки при
    этом числе процессов и памяти набора тестов такта, с запасом бюджета."""
    basis, workers = b["basis"], b["workers"]
    assert isinstance(workers, int) and 1 <= workers <= min(b["server_cores"], 7), "пул полосы — не больше ядер и 7"
    assert 1 <= basis["workers"] <= 7 and min(_many(basis["build_s"])) > 0
    slow, slow_tests = float(basis.get("server_factor", 1)), float(basis.get("tact_server_factor", 1))
    if b["status"] == "estimate":
        assert slow >= 2 and slow_tests >= 1.5, "оценка с ноутбука — с запасом на сервер: сборка × 2, тесты × 1,5"
        assert basis["tact_tests_s"] <= b["tact_tests_laptop_limit"], "набор такта на ноутбуке дольше предела"
        assert b["ci"]["laptop_seconds"]["tact"] >= basis["tact_tests_s"], "набор такта в CI — не быстрее замера"
    else:
        assert (slow, slow_tests) == (1, 1), "замер сервера — без запасов на сервер"
    longest = max(_many(basis["build_s"]) + _many(basis["build_worst_s"]))
    build = math.ceil(longest * basis["workers"] / workers * slow)
    tests = math.ceil(basis["tact_tests_s"] * slow_tests)
    tree = basis["memory_process_mb"] + (
        max(_many(basis["memory_tree_mb"])) - basis["memory_process_mb"]) * workers / basis["workers"]
    return build, tests, math.ceil(max(tree, basis["tact_tests_memory_mb"]) * b["safety"])


def test_the_budget_is_not_below_the_measurement_it_stands_on():
    """Бюджет стоит на замере из `basis` и не может быть ниже него — и с оценкой по ноутбуку, и с замером
    сервера: время сборки, время тестов такта (не дольше цели сервера), `MemoryHigh`. Инструмент считает
    те же числа и называет каждое противоречие словами — в обоих статусах."""
    tool = _tool()
    for b in _both_statuses():
        build, tests, need = _floors(b)
        assert b["seconds"]["build"] >= build, f"сборка в бюджете ниже замера: нужно не меньше {build} с"
        assert tests <= b["seconds"]["tact_tests"] <= b["tact_tests_target"], (
            f"тесты такта: в бюджете не меньше {tests} с и не больше цели сервера")
        assert b["seconds"]["future_tests"] >= tests
        assert b["memory"]["high_mb"] >= need, f"MemoryHigh ниже замера с запасом: нужно не меньше {need} МБ"
        assert b["memory"]["max_mb"] > b["memory"]["high_mb"]
        assert tool.findings(b) == [], b["status"]
        assert (tool.scaled_build(b), tool.scaled_tact_tests(b), tool.memory_floor_mb(b)) == (build, tests, need)
        low = json.loads(json.dumps(b))
        low["seconds"]["build"], low["seconds"]["tact_tests"], low["memory"]["high_mb"] = build - 1, tests - 1, need - 1
        low["seconds"]["collect_retries"] += 1
        # день замера на сервере: у оценки его нет, у замера он обязателен — противоречие в обе стороны
        low["measured_on"] = b["basis"]["measured_on"] if b["status"] == "estimate" else None
        found = " | ".join(tool.findings(low))
        for word in ("seconds.build", "seconds.tact_tests", "memory.high_mb", "measured_on", "seconds.collect_retries"):
            assert word in found, (b["status"], word, found)
        assert tool.findings({**b, "workers": b["server_cores"] + 1})[0].startswith("workers:")
        over = json.loads(json.dumps(b))
        over["seconds"]["tact_tests"] = b["tact_tests_target"] + 1
        assert any("tact_tests_target" in line and "метка tact" in line for line in tool.findings(over)), b["status"]


def test_the_estimate_from_the_laptop_carries_the_server_allowances():
    """Правило оценки: бюджет тестов такта = замер ноутбука × 1,5 (сборки — × 2), набор такта на ноутбуке —
    не дольше предела, время части CI — не быстрее замера. Запас нельзя ни снять, ни занизить; у замера
    с сервера запасов нет, и оставленный запас инструмент называет."""
    tool, b = _tool(), _budgets()
    if b["status"] != "estimate":
        pytest.skip("в бюджете замер сервера: правила оценки с ноутбука к нему не относятся")
    basis = b["basis"]
    assert b["seconds"]["tact_tests"] >= math.ceil(basis["tact_tests_s"] * 1.5)
    for name, least in (("server_factor", 2), ("tact_server_factor", 1.5)):
        for value in (None, 1, least - 0.1):
            weak = json.loads(json.dumps(b))
            if value is None:
                del weak["basis"][name]
            else:
                weak["basis"][name] = value
            assert any(f"basis.{name}" in line and "status estimate" in line for line in tool.findings(weak)), (name, value)
        kept = _measured(b)
        kept["basis"][name] = basis[name]
        assert any(f"basis.{name}" in line and "снимается" in line for line in tool.findings(kept)), name
    slow = json.loads(json.dumps(b))
    slow["basis"]["tact_tests_s"] = b["tact_tests_laptop_limit"] + 1
    slow["seconds"]["tact_tests"] = slow["seconds"]["future_tests"] = b["tact_tests_target"]
    slow["ci"]["laptop_seconds"]["tact"] = slow["basis"]["tact_tests_s"] - 1
    found = " | ".join(tool.findings(slow))
    assert "tact_tests_laptop_limit" in found and "ci.laptop_seconds.tact" in found, found


def test_the_measurement_is_a_number_or_a_list_and_a_wrong_shape_is_named(capsys):
    """Замер печатает одно число на поле, несколько прогонов — список: бюджет принимает и то, и другое.
    Негодная форма (строка, пустой список, ноль) и пропавший замер худшего случая сборки — строка
    «бюджет: basis.…» и код 1, а не трассировка."""
    tool, b = _tool(), _budgets()
    one = json.loads(json.dumps(b))
    for name in ("build_s", "build_worst_s", "memory_tree_mb"):
        one["basis"][name] = max(_many(b["basis"][name]))
    assert tool.findings(one) == [] and (tool.scaled_build(one), tool.memory_floor_mb(one)) == (
        tool.scaled_build(b), tool.memory_floor_mb(b))
    assert "худший случай" in tool.show(one) and "RuntimeMaxSec" in tool.show(one)
    for name, bad in (("build_s", "950"), ("build_s", []), ("build_worst_s", 0), ("memory_tree_mb", [520, None]),
                      ("memory_process_mb", [200]), ("tact_tests_s", "175"), ("workers", 2.5)):
        wrong = json.loads(json.dumps(b))
        wrong["basis"][name] = bad
        assert any(line.startswith(f"basis.{name}:") for line in tool.findings(wrong)), (name, bad)
    missing = json.loads(json.dumps(b))
    del missing["basis"]["build_worst_s"]
    [line] = tool.findings(missing)
    assert line.startswith("basis.build_worst_s: замера нет") and "ops/tools/worst_build.py" in line
    assert (OPS / "tools" / "worst_build.py").is_file()
    # время сборки стоит на худшем случае, а не только на обычном
    worse = json.loads(json.dumps(b))
    worse["basis"]["build_worst_s"] = math.ceil(b["seconds"]["build"] * b["workers"] / b["basis"]["workers"]) + 1
    assert tool.scaled_build(worse) > b["seconds"]["build"] >= tool.scaled_build(b)
    assert any(line.startswith("seconds.build:") and "худшего случая" in line for line in tool.findings(worse))


def test_the_tool_names_a_build_longer_than_its_target(tmp_path, capsys):
    """Цель времени сборки названа числом в бюджете (30 минут) и порог решения ведущего — тоже (45 минут):
    сборка в бюджете дольше цели — строка «ВНИМАНИЕ», бюджету это не противоречит (код прежний)."""
    tool, b = _tool(), _budgets()
    fits = json.loads(json.dumps(b))
    fits["seconds"]["build"] = b["build_target"]
    assert tool.notes(fits) == []
    late = json.loads(json.dumps(b))
    late["seconds"]["build"] = b["build_target"] + 1
    [line] = tool.notes(late)
    assert "build_target" in line and "30 мин" in line and "решает ведущий" not in line
    late["seconds"]["build"] = b["build_stop"] + 1
    [line] = tool.notes(late)
    assert "build_stop" in line and "45 мин" in line and "решает ведущий" in line
    root = _tree_copy(tmp_path)
    slow = json.loads((root / "ops" / "budgets.json").read_text(encoding="utf-8"))
    slow["seconds"]["build"] = max(slow["seconds"]["build"], slow["build_stop"] + 60)
    (root / "ops" / "budgets.json").write_text(json.dumps(slow, ensure_ascii=False, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")
    assert tool.main(["--write", "--root", str(root)]) == 0 and tool.main(["--check", "--root", str(root)]) == 0
    assert capsys.readouterr().out.count("ВНИМАНИЕ: сборка в бюджете") == 2


def test_the_tool_names_a_laptop_build_longer_than_its_goal(capsys):
    """Цель времени сборки на рабочей машине — числа бюджета `build_laptop_goal`: обычный случай и худший при
    названном числе процессов. Замер `basis` дольше цели — строка «ВНИМАНИЕ» о своём случае, бюджету это не
    противоречит; замер пересчитывается на число процессов цели; у замера с сервера сверять нечего. Негодная
    форма цели — строка «бюджет: build_laptop_goal …»."""
    tool, b = _tool(), _budgets()
    if b["status"] != "estimate":
        assert tool.laptop_notes(b) == []
        pytest.skip("в бюджете замер сервера: замера рабочей машины в нём нет")
    goal = b["build_laptop_goal"]
    fits = json.loads(json.dumps(b))
    fits["basis"].update(workers=goal["workers"], build_s=[goal["usual_s"] - 1, goal["usual_s"]],
                         build_worst_s=goal["worst_s"])
    assert tool.laptop_notes(fits) == []
    late = json.loads(json.dumps(fits))
    late["basis"]["build_worst_s"] = goal["worst_s"] + 1
    [line] = tool.laptop_notes(late)
    assert "худший случай" in line and "build_laptop_goal.worst_s" in line and "25 мин" in line
    late["basis"]["build_s"] = goal["usual_s"] + 1
    usual, worst = tool.laptop_notes(late)
    assert "обычный случай" in usual and "build_laptop_goal.usual_s" in usual and "15 мин" in usual and "худший" in worst
    # замер при другом числе процессов пересчитывается на число процессов цели (полоса делится поровну)
    more = goal["workers"] + 2
    even = goal["usual_s"] * goal["workers"] // more            # при `more` процессах — ровно цель после пересчёта
    scaled = json.loads(json.dumps(fits))
    scaled["basis"].update(workers=more, build_s=even, build_worst_s=even)
    assert tool.laptop_notes(scaled) == []
    scaled["basis"]["build_s"] = even + 1
    assert [line.split(":")[0] for line in tool.laptop_notes(scaled)] == ["сборка на рабочей машине, обычный случай"]
    assert tool.laptop_notes(_measured(late)) == [], "у замера с сервера basis рабочую машину не несёт"
    # замер дольше цели бюджету не противоречит
    late["seconds"]["build"] = max(late["seconds"]["build"], tool.scaled_build(late))
    assert tool.findings(late) == []
    for bad in (None, {"workers": 4, "usual_s": 900}, {"workers": 0, "usual_s": 900, "worst_s": 1500},
                {"workers": 4, "usual_s": 1600, "worst_s": 1500}, {"workers": 4, "usual_s": "900", "worst_s": 1500}):
        wrong = json.loads(json.dumps(b))
        wrong["build_laptop_goal"] = bad
        assert any(line.startswith("build_laptop_goal:") for line in tool.findings(wrong)), bad
    assert tool.main(["--check"]) == 0
    told = capsys.readouterr().out
    assert told.count("ВНИМАНИЕ: сборка на рабочей машине") == len(tool.laptop_notes(b))
    assert f"цель рабочей машины при {goal['workers']} процессах" in tool.show(b)


def test_the_tool_names_a_restart_window_longer_than_a_day(tmp_path, capsys):
    """Окно перезапуска такта обязано быть короче суток — то же правило, что держит тест юнитов. Бюджет, у
    которого окно выходит за сутки (долгая сборка при малом числе процессов полосы), инструмент называет строкой
    «бюджет: restart …» и производных чисел не пишет: ветка «два процесса» шага 8 установки кончается словом
    инструмента, а не красным тестом на уже вписанных числах."""
    tool, b = _tool(), _budgets()
    day = 24 * 3600
    assert tool.DAY == day and all(window < day for window in tool.restart_windows(b).values())
    assert not any(line.startswith("restart:") for line in tool.findings(b))
    long = json.loads(json.dumps(b))
    while max(tool.restart_windows(long).values()) < day:
        long["seconds"]["build"] += 600
    edge = json.loads(json.dumps(long))
    edge["seconds"]["build"] -= 600
    assert not any(line.startswith("restart:") for line in tool.findings(edge)), "окно короче суток — не противоречие"
    named = [line for line in tool.findings(long) if line.startswith("restart:")]
    slow = sorted(unit for unit, window in tool.restart_windows(long).items() if window >= day)
    assert len(named) == len(slow) >= 1 and all(f"такта {unit} " in " ".join(named) for unit in slow), named
    assert "daily" in slow and "не короче суток" in named[0] and "больше процессов полосы" in named[0]
    # вдвое меньше процессов — вдвое дольше сборка: бюджет по своему замеру проходит ту же проверку
    two = json.loads(json.dumps(b))
    two["workers"] = max(1, b["workers"] // 2)
    two["seconds"]["build"] = max(two["seconds"]["build"], tool.scaled_build(two))
    over = max(tool.restart_windows(two).values()) >= day
    assert any(line.startswith("restart:") for line in tool.findings(two)) == over
    # на копии дерева: отказ с кодом 1, файлы не тронуты
    root = _tree_copy(tmp_path)
    path = root / "ops" / "budgets.json"
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p != path]
    before = {p: p.read_bytes() for p in files}
    path.write_text(json.dumps(long, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    capsys.readouterr()
    assert tool.main(["--write", "--root", str(root)]) == 1 and tool.main(["--check", "--root", str(root)]) == 1
    told = capsys.readouterr().out
    assert told.count("бюджет: restart: окно перезапуска такта") == 2 * len(slow) and "производные числа не трогаю" in told
    assert before == {p: p.read_bytes() for p in files}


def test_the_derived_numbers_follow_the_budget_file(capsys):
    """Производные строки юнитов, run.sh и файлов CI равны бюджету — сверка самим инструментом; число
    процессов полосы тактов — `workers` бюджета."""
    tool, b = _tool(), _budgets()
    assert tool.apply(b, ROOT) == [], "после правки ops/budgets.json: python ops/tools/budgets.py --write"
    assert tool.ceilings(b) == _ceilings(b) and tool.restart_windows(b) == _restart_windows(b)
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    assert re.findall(r"^BUDGET_WORKERS=(\d+)$", script, re.M) == [str(b["workers"])]
    assert "export BANK_WORKERS=$BUDGET_WORKERS" in script
    assert tool.main(["--check"]) == 0 and tool.main([]) == 0
    table = capsys.readouterr().out
    assert "производные числа равны бюджету" in table and "RuntimeMaxSec" in table
    assert ("ОЦЕНКА до замера на сервере" in table) == (b["status"] == "estimate")


def _tree_copy(tmp_path: Path) -> Path:
    """Копия того, что несёт числа бюджета и расписание: бюджет, расписание, юниты с таймерами, run.sh, файлы CI."""
    root = tmp_path / "tree"
    shutil.copytree(UNITS, root / "ops" / "systemd")
    shutil.copytree(ROOT / ".github" / "workflows", root / ".github" / "workflows")
    for name in ("budgets.json", "schedule.json", "run.sh"):
        shutil.copyfile(OPS / name, root / "ops" / name)
    return root


def _key(line: bytes) -> bytes:
    """Имя строки «ключ=значение» или «ключ: значение» — всё до первого разделителя."""
    return re.split(rb"[=:]", line.strip(), maxsplit=1)[0]


def test_one_edit_of_the_budget_and_one_regeneration_move_every_derived_number(tmp_path, capsys):
    """Смена чисел бюджета — одна правка `ops/budgets.json` и одна команда: новый замер сборки, другое
    число процессов и память расходятся по юнитам, `LOCK_WAIT_SECONDS` и `BUDGET_WORKERS` сами. Проверка
    до записи называет расхождения, повторная запись ничего не меняет, прочие строки файлов не тронуты."""
    tool = _tool()
    root = _tree_copy(tmp_path)
    path = root / "ops" / "budgets.json"
    b = json.loads(path.read_text(encoding="utf-8"))
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p != path]
    before = {p: p.read_bytes() for p in files}
    assert tool.main(["--check", "--root", str(root)]) == 0
    # новый замер: ядро ускорено втрое, считаем другим числом процессов, памяти нужно больше
    for name in ("build_s", "build_worst_s"):
        b["basis"][name] = [x // 3 for x in _many(b["basis"][name])]
    other = 2 if b["workers"] != 2 else 3          # не то число, что в файле: иначе BUDGET_WORKERS не расходится
    b["workers"] = other
    b["seconds"]["build"] = tool.scaled_build(b) + 5
    b["memory"] = {"high_mb": b["memory"]["high_mb"] + 64, "max_mb": b["memory"]["max_mb"] + 128}
    parts = [k for k in b["ci"]["laptop_seconds"] if k.startswith("mutations-")]   # матрица частей мутаций CI
    assert parts
    for part in parts:
        b["ci"]["laptop_seconds"][part] *= 2
    path.write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert tool.main(["--check", "--root", str(root)]) == 1
    told = capsys.readouterr().out
    for name in ("RuntimeMaxSec", "StartLimitIntervalSec", "MemoryHigh", "LOCK_WAIT_SECONDS", "BUDGET_WORKERS",
                 *(f"CI, задание {part}" for part in parts)):
        assert name in told, name
    assert tool.main(["--write", "--root", str(root)]) == 0 and tool.main(["--check", "--root", str(root)]) == 0
    ceilings, lock = _ceilings(b)
    windows = _restart_windows(b)
    for mode in MODES:
        unit = _unit(root / "ops" / "systemd" / f"svcb850-{mode}.service")
        assert int(_one(unit, "Service", "RuntimeMaxSec")) == ceilings[mode]
        assert _one(unit, "Service", "MemoryHigh") == f"{b['memory']['high_mb']}M"
        assert _one(unit, "Service", "MemoryMax") == f"{b['memory']['max_mb']}M"
        if mode in windows:
            assert unit["Unit"]["StartLimitIntervalSec"] == [str(windows[mode])]
    script = (root / "ops" / "run.sh").read_text(encoding="utf-8")
    assert re.findall(r"^LOCK_WAIT_SECONDS=(\d+)$", script, re.M) == [str(lock)]
    assert re.findall(r"^BUDGET_WORKERS=(\d+)$", script, re.M) == [str(other)]
    ci = yaml.safe_load((root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    minutes = {row["part"]: row["minutes"] for row in ci["jobs"]["tests"]["strategy"]["matrix"]["include"]}
    for part in parts:
        assert minutes[part] == tool.ci_minutes(b)[part] > tool.ci_minutes(_budgets())[part], part
    # правка — только в значениях производных строк: число строк и прочий текст файлов те же
    for p in files:
        old, new = before[p].split(b"\n"), p.read_bytes().split(b"\n")
        assert b"\r" not in p.read_bytes() and len(old) == len(new), p.name
        assert all(_key(x) == _key(y) for x, y in zip(old, new) if x != y), p.name
    snapshot = {p: p.read_bytes() for p in files}
    assert snapshot != before
    capsys.readouterr()
    assert tool.main(["--write", "--root", str(root)]) == 0 and "менять нечего" in capsys.readouterr().out
    assert snapshot == {p: p.read_bytes() for p in files}
    # бюджет ниже своего замера не перегенерируется: сначала правится он сам
    b["seconds"]["build"] = tool.scaled_build(b) - 1
    path.write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert tool.main(["--write", "--root", str(root)]) == 1 and "seconds.build" in capsys.readouterr().out
    assert snapshot == {p: p.read_bytes() for p in files}
    # строка, в которую пишется число, пропала — отказ с именем строки, а не молчаливый пропуск
    b["seconds"]["build"] = tool.scaled_build(b)
    (root / "ops" / "run.sh").write_text(script.replace("LOCK_WAIT_SECONDS=", "LOCK_WAIT="), encoding="utf-8",
                                         newline="\n")
    with pytest.raises(tool.BudgetError, match="LOCK_WAIT_SECONDS"):
        tool.apply(b, root)


def test_the_server_measurement_of_the_install_is_one_edit_and_one_regeneration(tmp_path, capsys):
    """Шаг 8 установки (ops/README.md §5) на копии дерева: в бюджет ложится замер сервера — `status:
    measured`, день замера, числа замера по одному на поле, без запасов на сервер; набор такта на сервере
    идёт дольше, чем на ноутбуке. Инструмент правку принимает, одна перегенерация расходит новые потолки,
    сверка зелёная, таблица называет замер, проверки бюджета проходят и на нём. Прочие строки файлов не
    тронуты, и слов о статусе, которые замер сделал бы неправдой, в юнитах и скрипте нет."""
    tool = _tool()
    root = _tree_copy(tmp_path)
    path = root / "ops" / "budgets.json"
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and p != path]
    before = {p: p.read_bytes() for p in files}
    m = _measured(json.loads(path.read_text(encoding="utf-8")))
    assert m["basis"]["tact_tests_s"] > m["ci"]["laptop_seconds"]["tact"], "сервер медленнее ноутбука — не противоречие"
    assert not isinstance(m["basis"]["build_s"], list) and not isinstance(m["basis"]["memory_tree_mb"], list)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert tool.findings(m) == []
    capsys.readouterr()
    assert tool.main(["--check", "--root", str(root)]) in (0, 1)
    assert "бюджет:" not in capsys.readouterr().out, "замер сервера бюджету не противоречит"
    assert tool.main(["--write", "--root", str(root)]) == 0 and tool.main(["--check", "--root", str(root)]) == 0
    capsys.readouterr()
    assert tool.main(["--root", str(root)]) == 0
    table = capsys.readouterr().out
    assert f"замер на сервере {m['measured_on']}" in table and "ОЦЕНКА" not in table and "запас на сервер" not in table
    _honest(m)
    build, tests, need = _floors(m)
    assert (m["seconds"]["build"], m["seconds"]["tact_tests"], m["memory"]["high_mb"]) == (build, tests, need)
    ceilings, lock = _ceilings(m)
    for mode in MODES:
        unit = _unit(root / "ops" / "systemd" / f"svcb850-{mode}.service")
        assert int(_one(unit, "Service", "RuntimeMaxSec")) == ceilings[mode]
        assert _one(unit, "Service", "MemoryHigh") == f"{need}M"
    script = (root / "ops" / "run.sh").read_text(encoding="utf-8")
    assert re.findall(r"^LOCK_WAIT_SECONDS=(\d+)$", script, re.M) == [str(lock)]
    for p in files:
        old, new = before[p].split(b"\n"), p.read_bytes().split(b"\n")
        assert len(old) == len(new) and all(_key(x) == _key(y) for x, y in zip(old, new) if x != y), p.name
        text = p.read_bytes().decode("utf-8")
        assert "ДО ЗАМЕРА" not in text and "ЭТО ОЦЕНКА" not in text, f"{p.name}: слова, верные только до замера"
    # полшага — статус сменили, а запас оценки оставили — инструмент называет, перегенерации нет
    half = json.loads(json.dumps(m))
    half["basis"]["server_factor"] = 2
    path.write_text(json.dumps(half, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert tool.main(["--write", "--root", str(root)]) == 1 and "basis.server_factor снимается" in capsys.readouterr().out
    # набор такта на сервере дольше цели — тоже противоречие бюджета: метка tact снимается с самых долгих тестов
    long = json.loads(json.dumps(m))
    long["basis"]["tact_tests_s"] = long["seconds"]["tact_tests"] = m["tact_tests_target"] + 5
    long["seconds"]["future_tests"] = max(long["seconds"]["future_tests"], long["basis"]["tact_tests_s"])
    assert [line.split(":")[0] for line in tool.findings(long)] == ["seconds.tact_tests"]


def _env_example() -> tuple[dict[str, str], set[str]]:
    """(активные строки KEY=value, имена в закомментированных строках `# KEY=`)."""
    active, commented = {}, set()
    for line in (OPS / "env.example").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"# ([A-Z][A-Z0-9_]+)=", line)
        if m:
            commented.add(m.group(1))
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            assert sep and key == key.strip() and re.fullmatch(r"[A-Z][A-Z0-9_]+", key), line
            active[key] = value
    return active, commented


def test_the_env_example_carries_names_only():
    """Образец — только имена (репозиторий публичный): ни одного значения, ни
    одного секрета; все переменные конвейера названы."""
    active, commented = _env_example()
    assert all(v == "" for v in active.values()), {k: v for k, v in active.items() if v}
    assert OPS_VARIABLES <= set(active) | commented, OPS_VARIABLES - set(active) - commented
    assert (set(active) | commented) <= OPS_VARIABLES, (set(active) | commented) - OPS_VARIABLES
    script = (OPS / "run.sh").read_text(encoding="utf-8")
    required = set(re.findall(rf'\[\[ -n \$\{{({VARIABLE}):-\}} \]\] \|\| \{{ echo "в \$ENV_FILE не задан', script))
    assert required == {"SVCB_REPO_DIR", "BANK_STATE_DIR"} and required <= set(active)
    for key in ("TINVEST_TOKEN", "SVCB_RELEASE_REMOTE", "SVCB_GIT_NAME", "SVCB_GIT_EMAIL", "BANK_WORKERS"):
        assert key in active, f"{key}: без строки оператор её не впишет"
    text = (OPS / "env.example").read_text(encoding="utf-8")
    assert "`workers` в ops/budgets.json" in text, "число процессов полосы — из бюджета, не на глаз"


def test_the_ops_code_reads_only_documented_variables():
    """Код ops, образец env-файла и юниты называют только переменные INTERFACES
    §8 (и служебные метки run.sh); имён ядра с префиксом банка
    (`SVCB_STATE_DIR`, `SVCB_DATA_REPO_DIR`, `SVCB_WORKERS`, `SVCB_HANDOFF_DIR`) нет."""
    files = [p for p in OPS.rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and (p.suffix in (".py", ".sh", ".service", ".timer", ".json") or p.name == "env.example")]
    used = {}
    for path in files:
        for name in re.findall(rf"\b({VARIABLE})\b", path.read_text(encoding="utf-8")):
            used.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
    allowed = OPS_VARIABLES | SERVICE_VARIABLES
    extra = {k: sorted(v) for k, v in used.items() if k not in allowed}
    assert not extra, extra
    for old in ("SVCB_" + name.split("_", 1)[1] for name in CORE_VARIABLES | {"BANK_HANDOFF_DIR"}):
        assert old not in used, old


@pytest.mark.parametrize("path,ignored", [
    ("payload.json", True), ("release/latest.json", True), ("out/report.json", True),
    ("port-check/work/x.py", True), ("indicators/journal.sqlite", True),
    ("report.pdf", True), ("data/facts/databook.xlsx", True), (".wrangler/cache/x", True),
    ("var/state/x.json", True), ("var/pytest-tmp/x", True), ("var/.gitkeep", False),
    ("tests/fixtures/ind/synthetic.pdf", False), ("ops/run.sh", False), (".venv/x", True),
])
def test_the_gitignore_keeps_state_primary_documents_and_wrangler_out(path, ignored):
    """Первичка, состояние и каталог wrangler (ID аккаунта, почта) не попадают в
    дерево даже по `git add` каталога; синтетические фикстуры — попадают."""
    done = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=str(ROOT))
    assert done.returncode in (0, 1), done
    assert (done.returncode == 0) == ignored, path


def test_shell_scripts_and_units_are_checked_out_with_lf():
    done = subprocess.run(["git", "check-attr", "eol", "--", "ops/run.sh", "ops/systemd/svcb850-daily.service"],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.count("eol: lf") == 2, done.stdout


@pytest.mark.docs
def test_the_ops_readme_names_codes_units_settings_and_commands():
    """ops/README.md — рабочий документ: коды юнита, юниты, настройки из образца,
    команды отката и выкладки витрины совпадают с кодом."""
    text = (OPS / "README.md").read_text(encoding="utf-8")
    for code in ("0", "1", "8", "64", "75", "78"):
        assert re.search(rf"^\| {code} \|", text, re.M), f"код {code} не описан"
    for mode in MODES:
        assert f"svcb850-{mode}" in text
    active, commented = _env_example()
    for key in set(active) | commented:
        assert key in text, f"{key} из ops/env.example не описан"
    assert "ops/run.sh rollback <sha" in text
    wrangler = re.search(r"npx wrangler@([\d.]+) pages deploy web --project-name tzi-850-svcb --branch main",
                         (ROOT / "wrangler.toml").read_text(encoding="utf-8")).group(1)
    assert f"npx wrangler@{wrangler} pages deploy web --project-name tzi-850-svcb --branch main" in text
    for line in ("готово:", "ТРЕВОГА (код 8)", "ПРОВАЛ на шаге"):
        assert line in text, line


@pytest.mark.docs
def test_the_interfaces_list_the_same_ops_variables():
    """Таблица INTERFACES §8 и образец env-файла называют одни и те же переменные."""
    text = (ROOT / "docs" / "INTERFACES.md").read_text(encoding="utf-8")
    section = text.split("## 8.", 1)[1].split("\n## ", 1)[0]
    named = set(re.findall(r"`((?:SVCB|BANK|TINVEST)_[A-Z_]+)`", section))
    assert OPS_VARIABLES | SERVICE_VARIABLES <= named, (OPS_VARIABLES | SERVICE_VARIABLES) - named
