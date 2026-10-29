# -*- coding: utf-8 -*-
"""Документы репозитория (README, справочник, решения, история, перенос, эксплуатация)
ссылаются на то, что есть: пути в `коде` существуют, команды называют настоящие
режимы, а публичный справочник не несёт доступов. Процедуры, которые исполняют
буквально и один раз, — установка на сервер и первый push (`ops/README.md` §5, §12) —
сверяются по шагам: порядок, проверки, приёмка. Журнал решений, история и журнал
переноса копии называют её состояние как есть и начинаются со дня копии."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.docs

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README" + ".md", "docs/MANUAL" + ".md", "docs/DECISIONS" + ".md", "docs/CHANGELOG" + ".md",
             "docs/PORTING" + ".md", "ops/README" + ".md")
TOP = ("model/", "indicators/", "ops/", "data/", "docs/", "tests/", "web/", "functions/", ".github/")
PATH = re.compile(r"`([^`\s]+)`")
# Выходы, которые выпускают ядро и сборка (коммитит интеграция или лежат в состоянии).
GENERATED = {"data/assumptions/results.json", "data/assumptions/run_output.txt"}


def _paths(text: str) -> set[str]:
    out = set()
    for token in PATH.findall(text):
        token = token.rstrip(".,;:")
        if not token.startswith(TOP) or any(c in token for c in "<>{}*[]|$"):
            continue
        out.add(token.split(":")[0])
    return out


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_path_named_in_a_document_exists(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    missing = sorted(p for p in _paths(text) - GENERATED if not (ROOT / p.rstrip("/")).exists())
    assert not missing, f"{name}: нет {missing}"


def test_the_manual_names_the_real_units_and_modes():
    text = (ROOT / "docs" / ("MANUAL" + ".md")).read_text(encoding="utf-8")
    units = {p.stem for p in (ROOT / "ops" / "systemd").glob("*.service")}
    for unit in units:
        assert unit in text, unit
    script = (ROOT / "ops" / "run.sh").read_text(encoding="utf-8")
    modes = re.search(r'^  collect\|([a-z|-]+)\) ;;$', script, re.M).group(1).split("|")
    for mode in ["collect", *modes]:
        assert mode in text, mode


def test_the_public_manual_keeps_access_values_out():
    """Доступы — «где искать», без значений: ни имени ключа, ни токена, ни адреса."""
    text = (ROOT / "docs" / ("MANUAL" + ".md")).read_text(encoding="utf-8")
    section = text.split("## 3.", 1)[1].split("\n## ", 1)[0]
    assert "справочник владельца" in section
    assert not re.search(r"(?i)token\s*=|ssh-ed25519|BEGIN [A-Z ]*KEY|\bt\.[A-Za-z0-9_-]{20,}", text)


def test_the_readme_lists_the_documents_that_exist():
    text = (ROOT / ("README" + ".md")).read_text(encoding="utf-8")
    listed = set(re.findall(r"`(docs/[A-Z-]+\.md)`", text))
    present = {f"docs/{p.name}" for p in (ROOT / "docs").glob("*" + ".md")}
    assert present <= listed, present - listed


# ------------------------------------------- установка на сервер и первый push

def _ops_readme() -> str:
    return (ROOT / "ops" / ("README" + ".md")).read_text(encoding="utf-8")


def _section(text: str, number: int) -> str:
    """Раздел `## N. …` документа до следующего раздела того же уровня."""
    return text.split(f"\n## {number}. ", 1)[1].split("\n## ", 1)[0]


def _steps(section: str) -> dict[int, str]:
    """Нумерованные шаги раздела: {номер: текст шага с его командами}."""
    parts = re.split(r"(?m)^(\d+)\. ", section)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


def _commands(text: str) -> str:
    """Только команды: содержимое блоков ```bash … ``` (пояснения вокруг — не команды)."""
    return "\n".join(re.findall(r"```bash\n(.*?)```", text, re.S))


@pytest.mark.tact
def test_the_install_steps_are_complete_and_ordered():
    """Установка исполняется буквально и один раз: шаги стоят в порядке «код → настройки →
    ключ → правила → ветка данных → проба → первый сбор → замер сборки и бюджет → юниты →
    первый выпуск → Pages данных → витрина и приёмка → таймеры → сторож и мост», и у каждого
    необратимого есть проверка. Шага распознавания у этой панели нет: документы эмитента — с
    текстовым слоем."""
    steps = _steps(_section(_ops_readme(), 5))
    order = ["git clone --single-branch --branch main", "/usr/local/etc/svcb-850/env", "Deploy keys",
             "rulesets", "ops/publish.py --init", "ops/tools/probe.py --pdf",
             "ops/run.sh collect", "ops/tools/measure.py", "/etc/systemd/system/", "svcb850-daily.service",
             "Settings → Pages", "pages deploy web --project-name tzi-850-svcb --branch main",
             "systemctl enable --now", "dash-watch"]
    assert sorted(steps) == list(range(1, len(order) + 1)), sorted(steps)
    for number, mark in enumerate(order, 1):
        assert mark in steps[number], (number, mark)
    for path in ("/srv/dash/repo-850-svcb", "/var/lib/svcb-850", "/usr/local/etc/svcb-850/env"):
        assert path in _section(_ops_readme(), 5), path
    section = _section(_ops_readme(), 5)
    assert "tesseract-ocr" not in _commands(section) and "--only" not in _commands(section), (
        "распознавание у этой панели не ставится и не проверяется")


def test_the_build_is_measured_by_hand_before_the_units_and_the_timers():
    """Потолок юнита ниже настоящего времени сборки убивает её на середине, а пересборка помнит
    коммит и не повторяется. Поэтому до первого выпуска через юнит и до включения таймеров: первый
    сбор руками (без цены сборка не выходит), сборка вне systemd при двух и четырёх процессах полосы
    с замером времени и памяти, числа — одной правкой бюджета и одной перегенерацией, то же число
    процессов — в env-файл, и только потом юниты. Шаг сторожа — владельца, не установки."""
    section = _section(_ops_readme(), 5)
    steps = _steps(section)
    order = ["ops/tools/probe.py --pdf", "ops/run.sh collect", "ops/tools/measure.py -- .venv/bin/python -m model.build_release",
             "python ops/tools/budgets.py --write", "/etc/systemd/system/", "systemctl start --wait svcb850-daily.service",
             "pages deploy web", "systemctl enable --now"]
    at = [section.find(mark) for mark in order]
    assert all(x >= 0 for x in at), [m for m, x in zip(order, at) if x < 0]
    assert at == sorted(at), "порядок: проба → первый сбор → замер → бюджет → юниты → выпуск → витрина → таймеры"
    # первый сбор — сам такт вне systemd: env-файл читает run.sh и токен отдаёт только сборщику брокера
    assert "sudo -u dash env ENV_FILE=/usr/local/etc/svcb-850/env bash /srv/dash/repo-850-svcb/ops/run.sh collect" in steps[7]
    assert "до первой сборки" in steps[7] and "вне systemd" in steps[7] and "systemctl" not in _commands(steps[7])
    # замер — вне systemd, при 2 и 4 процессах, сборка и набор тестов такта; ничего не публикуется
    measure = _commands(steps[8])
    assert "for n in 2 4; do" in measure and "ops850 env BANK_WORKERS=$n .venv/bin/python ops/tools/measure.py" in measure
    # выражение такта читается от имени конвейера; пустое выражение отдало бы pytest ВЕСЬ набор (с сетью и
    # тестом мутаций), поэтому замер тестов стоит под условием
    assert """TACT=$(sudo -u dash sed -n 's/^TACT_TESTS="\\(.*\\)"$/\\1/p' /srv/dash/repo-850-svcb/ops/run.sh)""" in measure
    assert '-m pytest -m "$TACT"' in measure and "systemctl" not in measure and "publish.py" not in measure
    guarded = [line for line in measure.splitlines() if '-m pytest -m "$TACT"' in line]
    assert len(guarded) == 1 and guarded[0].strip().startswith('if [ -n "$TACT" ]; then '), guarded
    assert 'else echo "ОТКАЗ: выражение такта не прочитано' in measure
    assert "до юнитов и до таймеров" in steps[8] and "ничего не публикует" in steps[8]
    # худший случай: время сборки зависит от цены — замер сборкой в памяти на цене у медианы, и бюджет стоит на нём
    worst = "ops850 env BANK_WORKERS=$W .venv/bin/python ops/tools/measure.py -- .venv/bin/python ops/tools/worst_build.py"
    assert worst in measure and measure.index("-m model.build_release") < measure.index(worst)
    worst_tool = (ROOT / "ops" / "tools" / "worst_build.py").read_text(encoding="utf-8")
    assert "худший случай: сборка не дольше " in worst_tool and "«худший случай: сборка не дольше N с»" in steps[8]
    flat = " ".join(steps[8].split())
    for word in ("`status: measured`", "`measured_on`", "`basis`", "`workers`", "`seconds.build`", "`memory`",
                 "`build_worst_s`", "`basis.server_factor`", "`basis.tact_server_factor`",
                 "снимаются", "зависит от цены", "tests/test_ops_units.py tests/test_ops_ci.py"):
        assert word in flat, word
    # какие замеры пишутся списком, а какие — одним числом: те же поля, что различает инструмент бюджета
    budget_tool = (ROOT / "ops" / "tools" / "budgets.py").read_text(encoding="utf-8")

    def named(constant: str) -> str:
        """Поля замера из кортежа инструмента словами текста: «`a`, `b` и `c`»."""
        fields = re.findall(r'"(\w+)"', re.search(rf"^{constant} = \(([^)]*)\)$", budget_tool, re.M).group(1))
        assert len(fields) == 3, (constant, fields)
        return "`{}`, `{}` и `{}`".format(*fields)

    assert f"Три замера — {named('MEASURED_MANY')} — пишутся числом или списком прогонов" in flat
    assert f"три других — {named('MEASURED_ONE')} — одним числом (наибольший из прогонов)" in flat
    # два процесса: окно перезапуска суточного такта короче суток — иначе слово инструмента, а не красный тест
    assert "**Выбор числа процессов.**" in steps[8] and "короче суток" in flat and "«бюджет: restart …»" in flat
    assert "бюджет: {line}" in budget_tool and 'f"restart: окно перезапуска такта' in budget_tool
    assert "BANK_WORKERS=<workers бюджета>" in measure and "'^BANK_WORKERS=[1-7]$'" in measure
    # цели названы числами: тесты такта — 270 с, сборка — 30 минут, выше 45 минут — решает ведущий
    assert "270 с (`tact_tests_target`)" in steps[8] and "30 минут (`build_target`" in steps[8]
    assert "45 минут" in steps[8] and "(`build_stop`)" in steps[8] and "решает ведущий" in steps[8]
    # цель рабочей машины — тоже числами бюджета: 15 минут в обычном случае, 25 — в худшем, при четырёх процессах
    assert "(`build_laptop_goal`)" in steps[8] and "15 минут в обычном случае и 25 минут в" in " ".join(steps[8].split())
    # строка замера в инструкции — та, что печатает инструмент
    tool = (ROOT / "ops" / "tools" / "measure.py").read_text(encoding="utf-8")
    for part in ("замер: ", " с; пик памяти дерева ", "наибольший", "процесс ", "; BANK_WORKERS=", "код команды "):
        assert part in tool and part.strip("; ") in flat, part
    # юниты ставятся из копии с числами замера; первый выпуск идёт уже под ними
    assert "из копии с числами шага 8" in steps[9] and "RuntimeMaxSec" in _commands(steps[9])
    assert "сверяются с замером шага 8" in steps[10]
    # режим каталога состояния: шаг 5 ставит 750, юнит держит его (без строки режима systemd вернул бы 0755)
    assert "-m 750 /var/lib/svcb-850" in steps[5] and "`StateDirectoryMode=0750`" in steps[5]
    assert "StateDirectoryMode=" in _commands(steps[9]) and "stat -c '%U:%G %a' /var/lib/svcb-850" in _commands(steps[10])
    assert steps[13].lstrip().startswith("**Таймеры** — последними")
    assert steps[14].lstrip().startswith("**Сторож и мост — делает владелец.**")
    assert "не входит в установку конвейера" in steps[14]
    assert not re.search(r"(?i)github|/srv/|/usr/local/etc|/var/lib", steps[14]), "без имён репозиториев и путей"
    # бюджет говорит то же: оценка названа оценкой, смена чисел — одной правкой и одной командой
    budget = _section(_ops_readme(), 9)
    for word in ("`status: estimate`", "python ops/tools/budgets.py --write", "одна правка файла и одна команда",
                 "`workers` бюджета", "раздел 5, шаг 8", "`status: measured`", "`basis.build_worst_s`",
                 "python ops/tools/worst_build.py", "`basis.tact_server_factor`", "`tact_tests_laptop_limit` (150 с)",
                 "`tact_tests_target` (270 с)", "30 минут (`build_target`", "45 минут (`build_stop`)",
                 "`build_laptop_goal` бюджета", "15 минут в обычном случае (`usual_s`)", "25 минут в худшем (`worst_s`)",
                 "«бюджет: restart …»"):
        assert word in " ".join(budget.split()), word
    assert "медленнее сервера" not in _ops_readme(), "раннер CI целью сервера не служит и медленнее него не назван"
    # числа целей в тексте — числа бюджета
    budgets = json.loads((ROOT / "ops" / "budgets.json").read_text(encoding="utf-8"))
    assert (budgets["tact_tests_target"], budgets["tact_tests_laptop_limit"], budgets["tact_tests_ci_ceiling"],
            budgets["build_target"] // 60, budgets["build_stop"] // 60) == (270, 150, 300, 30, 45)
    goal = budgets["build_laptop_goal"]
    assert (goal["workers"], goal["usual_s"] // 60, goal["worst_s"] // 60) == (4, 15, 25)
    assert "решение ведущего" not in _ops_readme(), "текст эксплуатации — о том, как есть, а не о том, кто решил"
    assert "Сбера без изменений" not in _ops_readme() and "по Ленте" not in _ops_readme()


def test_an_unreadable_history_of_the_data_branch_has_a_written_way_back():
    """Испорченный `history.json` ветки данных публикация не переписывает с нуля, а отказывает: текст отказа и
    способ вернуть файл (из прошлого коммита ветки, новым коммитом, без силы) названы в разделе диагностики."""
    section = _section(_ops_readme(), 10)
    source = (ROOT / "ops" / "publish.py").read_text(encoding="utf-8")
    assert "в ветке не читается" in source and "«ПУБЛИКАЦИЯ: history.json в ветке не читается" in section
    commands = _commands(section)
    assert "git checkout <коммит> -- history.json" in commands and "git push origin release" in commands
    assert "--force" not in commands and "push -f" not in commands


def test_the_install_never_overwrites_a_ready_env_file_and_keeps_the_token_out():
    """Готовый env-файл с токеном установка не перезаписывает (образец кладётся, только если
    файла нет); ручные команды слоя ops идут без токена — кроме пробы источников."""
    section = _section(_ops_readme(), 5)
    steps = _steps(section)
    assert "sudo test -e /usr/local/etc/svcb-850/env || \\" in steps[2]
    helper = re.search(r"^ops850\(\) \{.*\}$", section, re.M)
    assert helper, "нет помощника ops850"
    assert ". /usr/local/etc/svcb-850/env; set +a; unset TINVEST_TOKEN;" in helper.group(0)
    assert "ops850 .venv/bin/python ops/publish.py --init" in steps[5]
    with_token = [n for n, body in steps.items()
                  if re.search(r"\. /usr/local/etc/svcb-850/env; set \+a;\n\s+cd ", body)]
    assert with_token == [6], "с токеном — только проба источников"
    # Первый сбор и замер: такт читает env-файл сам (токен — только сборщику брокера), замер идёт помощником без токена.
    assert [n for n, body in steps.items() if "ENV_FILE=/usr/local/etc/svcb-850/env bash" in body] == [7]
    assert "ops850 env BANK_WORKERS=$n" in steps[8] and "TINVEST_TOKEN" not in steps[8]
    assert "значения не выводятся" in steps[2] and "cat /usr/local/etc/svcb-850/env" not in section
    # Токен один на четыре панели банков: строка переносится из env-файла соседней панели без вывода
    # значения, путь соседа в публичном тексте — подстановкой.
    assert 'grep -m1 "^TINVEST_TOKEN=" "$s" >> "$f"' in steps[2] and "без вывода значения" in steps[2]
    assert "chown root:dash" in steps[2] and "chmod 640" in steps[2]
    assert "Токен один на четыре панели банков" in steps[2] and 's="<env-файл соседней панели банков>"' in steps[2]


def test_the_install_checks_the_issuer_host_and_the_timers_of_the_neighbours():
    """Четвёртая панель банков на общем сервере: проба источников — остановка установки при отказе по эмитенту и
    оговорка, что проба написана под форму источников образца; перед включением таймеров расписание сверяется со
    всем списком таймеров сервера и с записью соседей в расписании."""
    steps = _steps(_section(_ops_readme(), 5))
    probe = " ".join(steps[6].split())
    for word in ("остановка установки до таймеров", "под форму источников образца", "исследование данных",
                 "`ops/schedule.json`, `neighbours`"):
        assert word in probe, word
    timers = " ".join(steps[13].split())
    for word in ("весь список `systemctl list-timers`", "четвёртая панель банков", "`python ops/tools/schedule.py`",
                 "`neighbours`", "потом таймеры"):
        assert word in timers, word
    schedule = json.loads((ROOT / "ops" / "schedule.json").read_text(encoding="utf-8"))
    assert len(schedule["neighbours"]["panels"]) >= 5 and (ROOT / "ops" / "tools" / "schedule.py").is_file()


def test_the_readme_names_the_schedule_of_the_one_file():
    """Времена тактов в тексте эксплуатации — те, что стоят в `ops/schedule.json` (единственное место расписания):
    таблица тактов раздела 3 называет время сбора и суточного такта, окно дозора в UTC и по Москве, минуты
    пересборки; раздел о выкладке — те же минуты пересборки."""
    schedule = json.loads((ROOT / "ops" / "schedule.json").read_text(encoding="utf-8"))
    timers, shift = schedule["timers"], schedule["msk_offset_hours"] * 60
    at = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])  # noqa: E731
    show = lambda minute: f"{minute // 60:02d}:{minute % 60:02d}"  # noqa: E731
    start, end = (at(x) for x in timers["release-watch"]["window_msk"])
    step = timers["release-watch"]["every_min"]
    last = start + (end - start - 1) // step * step
    section = _section(_ops_readme(), 3)
    rows = {line.split("`")[1]: line for line in section.splitlines() if line.startswith("| `svcb850-")}
    assert set(rows) == {f"svcb850-{mode}" for mode in ("collect", "release-watch", "daily", "rebuild")}
    assert f"| каждый день {timers['collect']['at_utc']} " in rows["svcb850-collect"]
    assert f"| будни {timers['daily']['at_utc']} " in rows["svcb850-daily"] and timers["daily"]["days"] == "Mon..Fri"
    minutes = "*:" + ",".join(f"{m:02d}" for m in timers["rebuild"]["minutes"])
    assert f"| `{minutes}` |" in rows["svcb850-rebuild"] and f"(`{minutes}`)" in _section(_ops_readme(), 7)
    watch = (f"| будни {show(start - shift)}–{show(last - shift)} каждые {step} минут "
             f"({show(start)}–{show(last)} МСК) |")
    assert watch in rows["svcb850-release-watch"], watch
    for word in ("`ops/schedule.json`", "python ops/tools/schedule.py --write", "python ops/tools/schedule.py --check",
                 "`neighbours`", "`gaps_min`", "«расписание: …»"):
        assert word in section, word


def test_the_units_step_checks_that_systemd_does_not_read_the_env_file():
    """Юниты env-файл не читают (решения В10, В20): шаг установки это проверяет, а текст
    объясняет, кто читает файл и кому достаётся секрет."""
    section = _section(_ops_readme(), 5)
    steps = _steps(section)
    assert "systemctl show -p EnvironmentFiles -p Environment svcb850-daily.service" in steps[9]
    assert "`EnvironmentFiles=` пуст" in steps[9]
    assert "Файл\n   читает `ops/run.sh`" in steps[2] and "сборщику T-Invest" in steps[2]
    assert "EnvironmentFile=" not in _commands(section), "команды установки не вписывают EnvironmentFile"


def test_the_pages_step_deploys_into_the_existing_project():
    """Проект Pages создаётся один раз (панель Cloudflare или API, не wrangler): шаг проверяет
    его списком проектов и только потом выкладывает витрину; ни ID аккаунта, ни токена
    Cloudflare в тексте нет."""
    step = _steps(_section(_ops_readme(), 5))[12]
    commands = _commands(step)
    assert commands.index("pages project list") < commands.index("pages deploy web --project-name tzi-850-svcb")
    assert "создаётся один раз" in step and "производственная ветка `main`" in step
    assert "pages project create" not in _commands(_ops_readme())


def test_the_install_is_accepted_by_the_verify_line_and_the_code_mark():
    """Приёмка установки — не по коду первого такта: строка «СВЕРКА: выпуск … — пройдена …»
    в журнале, `release.commit` = коммит кода, отметка `release.pushed` снята. Шаблон
    grep из инструкции совпадает со строкой, которую печатает публикация."""
    steps = _steps(_section(_ops_readme(), 5))
    assert "кончится кодом 8 с одной причиной" in steps[10] and "боевая дверь не подтвердила" in steps[10]
    acceptance = _commands(steps[12])
    grep = re.search(r"grep '(СВЕРКА: [^']+)'", acceptance)
    assert grep, acceptance
    assert "/var/lib/svcb-850/release.commit" in acceptance and "rev-parse HEAD" in acceptance
    assert "release.pushed" in acceptance
    # Текст экранов первого живого выпуска — той же проверкой, что CI гоняет на фикстуре.
    assert "node tests/web/web_release_text.mjs var/first-release.json" in acceptance
    assert (ROOT / "tests" / "web" / "web_release_text.mjs").is_file() and '`"failed": []`' in steps[12]
    source = (ROOT / "ops" / "publish.py").read_text(encoding="utf-8")
    printed = re.search(r'print\(f"(СВЕРКА: выпуск \{want_sha\[:12\]\} · \{want_pub\} — пройдена [^"]*)"', source)
    assert printed, "публикация не печатает строку удачной сверки"
    assert re.search(grep.group(1), printed.group(1)), (grep.group(1), printed.group(1))
    run_sh = (ROOT / "ops" / "run.sh").read_text(encoding="utf-8")
    assert "боевая дверь не подтвердила" in run_sh


def _tracked_top_level() -> set[str]:
    """Верхние пути дерева: отслеживаемые и ещё не добавленные (кроме игнорируемых) — тот же
    список, что у гигиены. Копия до первого коммита не отслеживает ничего, а процедура §12
    пишется именно для неё: `git add` обязан назвать всё, что лежит в дереве."""
    done = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                          cwd=str(ROOT), capture_output=True)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    names = [n for n in done.stdout.decode("utf-8").split("\0") if n]
    return {n.split("/", 1)[0] for n in names}


def test_the_first_push_procedure_is_literal():
    """Первый push необратим, поэтому §12 — команды целиком: ветка прежней истории,
    `checkout --orphan`, ОЧИСТКА ИНДЕКСА (после orphan он несёт дерево прежнего коммита),
    явные пути (все верхние каталоги дерева), коммит, remote, push одной ссылки."""
    commands = _commands(_section(_ops_readme(), 12))
    order = ["git branch local-history-svcb-850 main", "git checkout --orphan", "git read-tree --empty",
             "git add -- ", "git status --short", "git diff --cached --name-status --diff-filter=AD",
             "commit -q -m", "git branch -M main", "git rev-list --count main",
             "git remote add origin https://github.com/ML371KL/temp-zero-inode-850-svcb.git",
             "git push origin main", "git ls-remote origin"]
    at = [commands.find(mark) for mark in order]
    assert all(x >= 0 for x in at), [m for m, x in zip(order, at) if x < 0]
    assert at == sorted(at), "шаги не по порядку"
    assert "git rm " not in commands, (
        "`git rm --cached` на ветке-сироте отказывает, когда в дереве есть незакоммиченные правки, — индекс "
        "очищает `git read-tree --empty`")
    assert "git add -A" not in commands and "--all" not in commands.replace("# без --all", "")
    assert "--mirror" not in commands.replace("--mirror и тегов", "") and "push --force" not in commands
    joined = commands.replace("\\\n", " ")                     # команда с переносом строки — одна строка
    [line] = [x.strip() for x in joined.splitlines() if x.strip().startswith("git add -- ")]
    added = line[len("git add -- "):].split()
    assert {a.split("/", 1)[0] for a in added} == _tracked_top_level(), (
        "в `git add` §12 названы не все верхние пути дерева (или лишние)")
    assert "var/.gitkeep" in added and "var" not in added, "из var/ в репозитории — только .gitkeep"
    assert ".github/commit-emails.allow" in commands, "адрес автора — из списка, не литералом"


def test_the_first_push_is_accepted_before_and_after_the_commit():
    """До коммита — весь набор, набор сервера на четырёх будущих датах и личные слова с
    итогом «1 passed»; после — приёмка по ссылке `main` тремя проверками удалённого.
    Шаблоны удалённого лежат в папке передачи: в публичном тексте их нет. КАЖДАЯ
    КОМАНДА ПЕЧАТАЕТ ИТОГ: «зелёный на всех четырёх датах» и «оборвался на первой»
    обязаны различаться строкой, а не хвостом вывода; второй `-q` (первый — в
    pytest.ini) убрал бы итоговую строку pytest."""
    section = _section(_ops_readme(), 12)
    commands = _commands(section)
    assert "for d in 1 7 30 60; do" in commands and 'FAKE_TODAY=$(date -u -d "+$d days" +%F)' in commands
    for told in ('echo "весь набор, кроме теста истории ветки: код $?"',
                 'echo "набор сервера на сегодня + $d дн.: код $rc"',
                 'echo "ИТОГ: набор сервера зелёный на $green датах из 4"',
                 'echo "история ветки и гигиена дерева: код $?"'):
        assert told in commands, told
    assert "|| break" not in commands, "цикл дат проходит все четыре и печатает итог"
    history = "test_the_history_of_the_branch_never_carried_raw_tinvest_answers"
    assert f"--deselect tests/test_ops_ci.py::{history}" in commands
    assert f"def {history}(" in (ROOT / "tests" / "test_ops_ci.py").read_text(encoding="utf-8")
    runs = [line for line in commands.replace("\\\n", " ").splitlines() if "-m pytest" in line]
    assert len(runs) == 5, runs
    for line in runs:
        assert "--basetemp=var/pytest-push" in line, f"свой каталог временных файлов: {line}"
        assert not re.search(r"\s-q\b", line), f"второй -q убирает итоговую строку pytest: {line}"
    assert "ИТОГ: набор сервера зелёный на 4 датах из 4" in section
    assert "не запускается ничего другого" in section and "`tests/support_git.py`" in section
    assert "git rev-list --count main; git status --short | wc -l" in commands, "после прогонов приёмки — снова 1 и 0"
    assert "такт: N с из 300 (цель сервера — 270 с)" in section
    assert "Шаблоны приёмки — свои у каждой панели" in section and "Шаблоны панели-образца копии не годятся" in section
    assert """TACT=$(sed -n 's/^TACT_TESTS="\\(.*\\)"$/\\1/p' ops/run.sh)""" in commands
    assert commands.count("-rs -m archive tests/test_public_hygiene.py") == 2, "личные слова — до коммита и после"
    assert "«1 passed»" in section and "push не делать" in section
    for check in ('git ls-tree -r --name-only main -- $(cat "$A/removed-paths.txt")',
                  'git grep -n -E -f "$A/absent-patterns.txt" main',
                  """git grep -n -E -f "$A/source-urls.txt" main -- ':!data/'""",
                  'git grep -c -E -f "$A/source-urls.txt" main -- data/ | diff - "$A/source-urls.expected.txt"'):
        assert check in commands, check
    assert 'A="$H/private/push-acceptance"' in commands
    assert 'read -r -p "папка передачи (вне репозитория): " H' in commands, "путь к папке передачи в текст не вписан"
    assert "<папка передачи>" not in commands, "в командах §12 нет подстановок: они исполняются буквально"
    for leaked in ("interfax", "kommersant", "t.me/", "MGNT"):
        assert leaked not in section, f"шаблон удалённого в публичном тексте: {leaked}"


def test_the_decisions_state_what_is_and_is_not_deployed():
    """Журнал решений не утверждает несделанного: состояние названо как есть (выпуск сделан — с корневым коммитом,
    сервером, первым выпуском и таймерами; не сделан — так и сказано, без слов о выкладке), решения владельца,
    устава и ведущего датированы, значений доступов нет."""
    text = (ROOT / "docs" / ("DECISIONS" + ".md")).read_text(encoding="utf-8")
    owner = text.split("## Часть 1.", 1)[1].split("\n## Часть 2.", 1)[0]
    for word in ("21.10.2026", "28.10.2026", "публичные", "справочник владельца", "5,57 %", "T-Invest", "не обходим"):
        assert word in owner, word
    charter = text.split("## Часть 2.", 1)[1].split("\n## Часть 3.", 1)[0]
    for fork in [f"О{n}" for n in range(1, 8)]:                       # развилки владельца устава и их умолчания
        assert f"| {fork} |" in charter, fork
    lead = text.split("## Часть 3.", 1)[1].split("\n## Часть 4.", 1)[0]
    for n in range(1, 13):                                            # решения ведущего № 1–12 — строками таблицы
        assert f"| № {n} " in lead, n
    assert "Лист решения № 12" in lead and "устоялось" in lead
    state = text.split("## Часть 4.", 1)[1].split("\n## Открытые вопросы", 1)[0]
    deployed = ("на бою с", "одним корневым коммитом", "сверен через дверь витрины", "таймеры включены")
    if "на бою с" in state:                                           # выкладка была — названа целиком
        for word in deployed + ("не зарегистрирована",):
            assert word in state, word
    else:                                                             # выкладки не было — так и сказано
        assert "выпуска ещё нет" in state
        assert not any(word in state for word in ("сверен через дверь витрины", "таймеры включены")), state[:200]
    questions = text.split("\n## Открытые вопросы", 1)[1].lower()
    for word in ("докапитализац", "обучение режимов", "сторож", "умолчания ведущего"):
        assert word in questions, word
    headings = re.findall(r"^## Часть (\d+)\. .*?\((\d{2}\.\d{2}\.\d{4})\)", text, re.M)
    numbers = [int(n) for n, _ in headings]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 3, headings
    days = [tuple(reversed(day.split("."))) for _, day in headings]
    assert days == sorted(days), f"части журнала решений идут не по датам: {headings}"


def test_the_changelog_and_the_porting_journal_start_from_the_copy():
    """История начинается с создания копии, журнал переноса — со строки «копия создана с коммита …
    панели-образца»: от неё считается, какие исправления образца копия ещё не получила, а дыры общего
    слоя, найденные копией, записаны строками «Совкомбанк → …» (взятые у ВТБ — «ВТБ → Совкомбанк»). Журналы
    обоих образцов унаследованы разделами:
    второй панели банков (её строка копии и её строки «Т → Сбер») и первой."""
    changelog = (ROOT / "docs" / ("CHANGELOG" + ".md")).read_text(encoding="utf-8")
    records = re.findall(r"^## (\d{2}\.\d{2}\.\d{4}) — (.+)$", changelog, re.M)
    assert records and records[-1] == ("07.10.2026", "копия создана с коммита `1c0b904` Сбера"), records
    porting = (ROOT / "docs" / ("PORTING" + ".md")).read_text(encoding="utf-8")
    journal = porting.split("\n## 3. ", 1)[1]
    assert re.findall(r"^### (3\.\d)\. (.+)$", journal, re.M) == [
        ("3.1", "Журнал копии Совкомбанка"), ("3.2", "Унаследованный журнал Т (до коммита `456ff23`)"),
        ("3.3", "Унаследованный журнал Сбера (до коммита `1c0b904`)")]

    def rows_of(section: str) -> list[str]:
        return [line for line in section.splitlines() if line.startswith("| ") and not line.startswith(("| Дата", "|---"))]

    own = rows_of(journal.split("### 3.1.", 1)[1].split("\n### 3.2.", 1)[0])
    assert own and "копия создана с коммита `456ff23` панели Т-Технологий" in own[0], own[:1]
    assert own[0].rstrip().endswith("| Т → Совкомбанк | перенесено |")
    open_rows = [line for line in own if "| Совкомбанк → " in line]
    assert len(open_rows) >= 4 and all(line.rstrip().endswith("| открыто |") for line in open_rows), open_rows
    assert all(len(line.split(" | ")) == 5 for line in own), "строка журнала — дата, что, где, откуда → куда, статус"
    second = rows_of(journal.split("\n### 3.2.", 1)[1].split("\n### 3.3.", 1)[0])
    assert second and "копия создана с коммита `1c0b904` Сбера" in second[0], second[:1]
    assert len([line for line in second if "Т → Сбер" in line]) >= 4, "журнал второй панели унаследован"
    first = journal.split("\n### 3.3.", 1)[1]
    assert "«Лента» → Сбер" in first and "Сбер → банки-копии" in first, "журнал первой панели унаследован"
    head = porting.split("\n## 1. ", 1)[0]
    assert "`456ff23` панели Т-Технологий" in head and "`1c0b904` панели Сбера" in head


def test_the_manual_tells_what_expires_and_what_to_do():
    """Сроки данных — плашки, а не тревога: справочник называет три исхода сборки, флаги,
    что делать с каждым сроком, и режим перезаякоривания."""
    text = (ROOT / "docs" / ("MANUAL" + ".md")).read_text(encoding="utf-8")
    terms = text.split("### 10.9.", 1)[1].split("\n---", 1)[0]
    for word in ("`explanation_expiring`", "`policy_expired`", "`manual_input_overdue`", "`deadline`",
                 "gate_explanations.yaml", "data/facts/dividends.json", "`cbr_forecast`", "`worlds.source.curve_date`",
                 "**Календарь ближайших отказов сборки**", "**Проверка на любую дату**"):
        assert word in terms, word
    outcomes = text.split("### 4.3.", 1)[1].split("### 4.4.", 1)[0]
    assert all(word in outcomes for word in ("**отказ** (код 1)", "**тревога** (код 3", "**плашка** (код 0)"))
    assert "истекает через 30 дней или раньше, входы деградировали" not in text, "истекающее объяснение — не тревога"
    assert "Режим передачи ставки — `keep`" in text.split("### 10.4.", 1)[1].split("### 10.5.", 1)[0]


def _first_refusals() -> dict[str, date]:
    """Первый день отказа сборки по ближайшим срокам — вторым счётом, из тех же файлов, что читает сборка: календарь
    фактов, сроки ручных входов и дата кривой миров книги, сроки записей объяснений гейтов. Событие с оценочной
    датой отсчитывается от поздней границы окна; срок записи действует включительно."""
    book = yaml.safe_load((ROOT / "data" / "assumptions" / "assumptions.yaml").read_text(encoding="utf-8"))
    days, anchor = book["checks"]["manual_overdue_days"], str(book["meta"]["anchor_period"])
    curve = date.fromisoformat(str(book["worlds"]["source"]["curve_date"]))
    events = json.loads((ROOT / "data" / "facts" / "calendar.json").read_text(encoding="utf-8"))["events"]

    def start(event: dict) -> date:
        return date.fromisoformat(str(event["latest"] if event.get("estimated") is True else event["date"]))

    out = {}
    meetings = [start(e) for e in events if e.get("kind") == "cbr_forecast" and start(e) > curve]
    if meetings:
        out["worlds"] = min(meetings) + timedelta(days=int(days["worlds_after_cbr"]) + 1)
    reports = [e for e in events if e.get("kind") == "ifrs" and str(e.get("covers") or "") > anchor]
    if reports:
        out["ifrs"] = start(min(reports, key=lambda e: str(e["covers"]))) + timedelta(days=int(days["ifrs_fact"]) + 1)
    notes = yaml.safe_load((ROOT / "data" / "assumptions" / "gate_explanations.yaml").read_text(encoding="utf-8")) or {}
    until = [date.fromisoformat(str(note["valid_until"])) for note in notes.values()]
    if until:
        out["explanations"] = min(until) + timedelta(days=1)
    return out


def test_the_manual_dates_the_nearest_build_refusals():
    """Сроки ручных входов плашки не имеют, а отказавшая сборка называет только гейт: справочник обязан называть
    первый день отказа по каждому ближайшему сроку — миры после заседания Банка России, объяснения гейтов, отчёт
    МСФО — и что делать. Даты календаря справочника равны датам, сосчитанным из календаря фактов, книги и записей
    объяснений: сдвинулся срок в данных — правится и календарь. От «сегодня» тест не зависит."""
    text = (ROOT / "docs" / ("MANUAL" + ".md")).read_text(encoding="utf-8")
    terms = text.split("### 10.9.", 1)[1].split("\n---", 1)[0]
    block = terms.split("**Календарь ближайших отказов сборки**", 1)[1].split("**Проверка на любую дату**", 1)[0]
    rows = {m.group(1): line for line in block.splitlines() if (m := re.match(r"\| (\d{2}\.\d{2}\.\d{4}) \| ", line))}
    first = _first_refusals()
    assert set(first) == {"worlds", "ifrs", "explanations"}, first
    day = {name: value.strftime("%d.%m.%Y") for name, value in first.items()}
    # записи объяснений истекают в разные дни (запись ручных входов — раньше прочих): строка календаря — на каждый
    # день отказа; два срока в один день (отчёт МСФО и запись ручных входов) — одна строка
    notes_all = yaml.safe_load((ROOT / "data" / "assumptions" / "gate_explanations.yaml").read_text(encoding="utf-8")) or {}
    expiries = sorted({date.fromisoformat(str(n["valid_until"])) + timedelta(days=1) for n in notes_all.values()})
    dates = sorted(set(first.values()) | set(expiries))
    assert list(rows) == [d.strftime("%d.%m.%Y") for d in dates], (list(rows), day)
    worlds, notes, report = rows[day["worlds"]], rows[day["explanations"]], rows[day["ifrs"]]
    last = rows[expiries[-1].strftime("%d.%m.%Y")]
    for word in ("`worlds_after_cbr`", "раздел 10.5", "`manual_input_overdue`", "data/assumptions/gate_explanations.yaml",
                 "не дальше"):
        assert word in worlds, word
    assert "`valid_until`" in notes and "`manual_input_overdue`" in notes
    assert "`valid_until`" in last and "раздел 10.4" in last and "`guidance_gap`" in last
    assert "`ifrs_fact`" in report and "раздел 10.4" in report and "поздняя граница" in report
    # запись объяснения гейта ручных входов закрывает все его ветви: её срок — не дальше срока записей объяснений,
    # то есть раньше отказа по невнесённому отчёту
    limit = (first["explanations"] - timedelta(days=1)).strftime("%d.%m.%Y")
    assert f"сроком не дальше {limit}" in worlds and first["explanations"] <= first["ifrs"]
    table = terms.split("| Что истекает |", 1)[1].split("\n\n", 1)[0]
    [row] = [line for line in table.splitlines() if line.startswith("| Миры после заседания Банка России")]
    for word in ("`checks.manual_overdue_days.worlds_after_cbr`", "`cbr_forecast`", "`worlds.source.curve_date`",
                 "с 22-го дня", "кодом 1", "плашки заранее нет", "раздел 10.5", "не раньше дня заседания",
                 "не ставят дальше ближайшего срока другого ручного входа"):
        assert word in row, word
    book = yaml.safe_load((ROOT / "data" / "assumptions" / "assumptions.yaml").read_text(encoding="utf-8"))
    assert int(book["checks"]["manual_overdue_days"]["worlds_after_cbr"]) + 1 == 22, "«с 22-го дня» — число книги + 1"
    # проверка на любую дату — командой, которая есть: подмена «сегодня» доходит до сборки через каталог подмены
    probe = "FAKE_TODAY=ГГГГ-ММ-ДД PYTHONPATH=tests/fakedate_site python -B -m model.build_release --check --fast --book-only"
    assert probe in _commands(terms) and (ROOT / "tests" / "fakedate_site" / "sitecustomize.py").is_file()
    build = (ROOT / "model" / "build_release.py").read_text(encoding="utf-8")
    for flag in ("--check", "--fast", "--book-only"):
        assert f'"{flag}"' in build, flag
    # раздел о новой версии книги и мирах называет срок, журнал решений — тот же первый день отказа
    worlds_section = text.split("### 10.5.", 1)[1].split("### 10.6.", 1)[0]
    assert "**Срок миров.**" in worlds_section and "раздел 10.9" in worlds_section
    decisions = (ROOT / "docs" / ("DECISIONS" + ".md")).read_text(encoding="utf-8")
    questions = decisions.split("\n## Открытые вопросы", 1)[1]
    [asked] = [line for line in questions.splitlines() if line.startswith("| Пересборка миров семейства")]
    assert f"с {day['worlds']} без новой записи миров" in asked and f"не дальше {limit}" in asked
    version = book["meta"]["version"]
    assert "`manual_input_overdue`" in asked and f"действует запись, на которой стоит книга {version}, но не дольше" in asked
