# -*- coding: utf-8 -*-
"""Какие тесты где идут: CI, документы и такт сервера.

Сторожа `.github/workflows/ci.yml` и `docs.yml` (триггеры, закреплённые
действия, гигиена истории, канон миров, замер такта, контракт выпуска; набор
тестов тремя частями без повторов — набор сервера, остальное, тест мутаций;
потолки заданий — из `ops/budgets.json`), история
ветки без сырых ответов T-Invest (условие первого push), сторож меток тестов
(объявлены в pytest.ini; `tact` и `ci_only` не вместе; тест, читающий документ
`*.md`, несёт метку `docs` или `tact`, иначе коммит из одних документов его не
увидит — docs.yml гоняет только `docs` и `tact`), сторож git в тестах (пишет только
помощник песочницы `tests/support_git.py`).
"""
from __future__ import annotations

import ast
import configparser
import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Признаки сырого ответа T-Invest — те же, что у гигиены дерева.
from tests.test_public_hygiene import T_COLLECTOR_CODE, T_MARKER_WORDS, _text, _tree
# Один счётчик меток на оба сторожа: метки модуля, класса, функции и имён-псевдонимов.
from tests.test_ops_tact_suite import collect_tests, selected

pytestmark = pytest.mark.ci_only

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
MD = "." + "md"          # без литерала «…md»: сторож читает и этот файл
BUILTIN_MARKS = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}
# Тесты без меток `docs` и `tact`, где имя документа встречается, но настоящий
# документ не читается: песочница git конвейера (имена условные), временные
# документы инструментов.
NOT_A_DOCUMENT_READ = {
    ("test_ops_run_sh.py", "test_the_rebuild_is_silent_until_the_counting_code_changes"),
    ("test_ops_tools.py", "test_render_check_on_a_tree"),
    ("test_ops_publish.py", "test_a_foreign_push_does_not_block_the_next_publish"),
    ("test_ops_publish.py", "test_sync_brings_the_clone_to_the_branch"),
}
# Отчёты инструментов, которые тест сам пишет во временный каталог: голое имя файла
# (с путём — уже документ репозитория, например справочник перезаякоривания в docs/).
# flags.md — запись запуска команды перевывода с меткой «flags» в каталоге записей теста (ops/tools/rederive.py).
TOOL_REPORTS = {"CANDIDATE", "REANCHOR", "flags"}
# Прямой вызов git в тестах — только читающие вопросы к самой рабочей копии. Всё, что
# пишет (init, commit, add, clone, push, reset, config …), идёт помощником песочницы.
GIT_READS_OF_THE_WORKING_COPY = {"ls-files", "log", "rev-parse", "rev-list", "check-attr", "check-ignore"}
GIT_HELPER = "support_git.py"


def _ci() -> dict:
    return yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))


def _docs() -> dict:
    return yaml.safe_load((WORKFLOWS / "docs.yml").read_text(encoding="utf-8"))


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def _step(job: dict, name: str) -> dict:
    [step] = [x for x in job["steps"] if x.get("name") == name]
    return step


def _budget_tool():
    """Инструмент бюджета `ops/tools/budgets.py` модулем."""
    spec = importlib.util.spec_from_file_location("budgets_for_ci", ROOT / "ops" / "tools" / "budgets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MUTATIONS = "tests/test_core_mutations.py"
PARTS = ("tact", "rest", "mutations")          # группы отбора: каждый тест — ровно в одной
MUTATION_SHARDS = 10                             # файл мутаций — матрицей частей mutations-1 … mutations-N (BANK_MUTATION_SHARD)
MATRIX = ("tact", "rest", *(f"mutations-{k}" for k in range(1, MUTATION_SHARDS + 1)))
FULL = "not network and not archive"


def _tact() -> str:
    return re.search(r'^TACT_TESTS="([^"]+)"$', (ROOT / "ops" / "run.sh").read_text(encoding="utf-8"),
                     re.M).group(1)


def test_every_code_push_and_pull_request_runs_the_full_suite():
    doc = _ci()
    on = doc[True]
    assert on["push"] == {"paths-ignore": ["**/*.md"]} and on["pull_request"] == {"paths-ignore": ["**/*.md"]}
    assert "future_days" in on["workflow_dispatch"]["inputs"]
    assert set(on) == {"push", "pull_request", "workflow_dispatch", "schedule"}, set(on)
    assert "pull_request_target" not in on
    assert doc["permissions"] == {"contents": "read"}
    assert all("permissions" not in j for j in doc["jobs"].values()), "права только на чтение"
    assert sorted(p.name for p in WORKFLOWS.glob("*.yml")) == ["ci.yml", "docs.yml"], "лишний workflow"
    assert set(doc["jobs"]) == {"tests", "release-contract"}
    job = doc["jobs"]["tests"]
    # Весь набор — частями одной матрицы, одновременно; красная часть остальные не отменяет. Файл мутаций — матрицей
    # частей: часть K/N гоняет мутантов с номером i mod N = K − 1, подлинное ядро — часть 1.
    rows = job["strategy"]["matrix"]["include"]
    assert [row["part"] for row in rows] == list(MATRIX)
    assert [row.get("shard") for row in rows[2:]] == [f"{k}/{MUTATION_SHARDS}" for k in range(1, MUTATION_SHARDS + 1)]
    assert all("shard" not in row for row in rows[:2])
    assert job["strategy"]["fail-fast"] is False and job["timeout-minutes"] == "${{ matrix.minutes }}"
    assert _step(job, "Тесты такта — замер времени")["if"] == "matrix.part == 'tact'"
    rest = _step(job, "Тесты вне набора такта")
    assert rest["if"] == "matrix.part == 'rest'"
    assert rest["run"] == f'python -m pytest -rs -m "$REST" --strict-markers --durations=25 --ignore={MUTATIONS}'
    mutations = _step(job, "Тест мутаций")
    assert mutations["if"] == "startsWith(matrix.part, 'mutations-')" and mutations["env"] == {"BANK_MUTATION_SHARD": "${{ matrix.shard }}"}
    assert mutations["run"] == f'python -m pytest -rs -m "$REST" --strict-markers --durations=5 {MUTATIONS}'
    assert (ROOT / MUTATIONS).is_file() and "def test_every_mutation_is_caught(" in (ROOT / MUTATIONS).read_text(encoding="utf-8")
    # Лёгкие сторожа дерева идут один раз — в части набора сервера.
    for name in ("Гигиена истории", "Бюджет тактов", "Переводы строк", "Синтаксис скриптов и юнитов"):
        assert _step(job, name)["if"] == "matrix.part == 'tact'", name
    assert _step(job, "Бюджет тактов")["run"] == "python -B ops/tools/budgets.py --check"
    assert _step(job, "Канон миров, машинная книга и числа документов")["if"] == (
        "matrix.part == 'tact' && env.FUTURE_DAYS == '0'")


def _expressions(future: bool) -> tuple[str, str]:
    """(выражение части tact, выражение частей rest и mutations) — так, как их собирает шаг «Набор части и
    дата прогона»: такт — из ops/run.sh, остальное — его дополнение; «в будущем» — без тестов сроков."""
    run = _step(_ci()["jobs"]["tests"], "Набор части и дата прогона")["run"]
    assert r"""tact=$(sed -n 's/^TACT_TESTS="\(.*\)"$/\1/p' ops/run.sh)""" in run
    assert 'echo "TACT=$tact" >> "$GITHUB_ENV"' in run and 'echo "REST=$rest" >> "$GITHUB_ENV"' in run
    [base] = re.findall(r'^rest="([^"$]*\(\$tact\))"$', run, re.M)
    [extra] = re.findall(r'^\s+rest="\$rest( and [a-z_ ]+)"$', run, re.M)
    tact = _tact()
    rest = base.replace("$tact", tact) + (extra if future else "")
    return tact, rest


@pytest.mark.parametrize("future", [False, True])
def test_every_test_runs_in_exactly_one_part_of_the_suite(future):
    """Три части CI не пересекаются и вместе дают весь набор: тест набора сервера идёт только в части tact,
    остальные — в rest, а тесты файла мутаций — в mutations (тот же отбор, другой путь). Повторного прогона
    набора такта нет. «В будущем» из набора уходят только тесты сроков."""
    tact, rest = _expressions(future)
    assert rest == f"{FULL} and not ({tact})" + (" and not deadline" if future else "")
    full = FULL + (" and not deadline" if future else "")
    counts = {part: 0 for part in PARTS}
    for path in _test_files():
        own = "mutations" if path.relative_to(ROOT).as_posix() == MUTATIONS else "rest"
        for name, marks, _ in collect_tests(path):
            parts = [part for part, hit in (("tact", selected(tact, marks)), (own, selected(rest, marks))) if hit]
            assert len(parts) == (1 if selected(full, marks) else 0), (path.name, name, sorted(marks), parts)
            for part in parts:
                counts[part] += 1
    assert all(counts.values()), f"пустая часть набора — pytest ответит кодом 5: {counts}"
    assert counts["mutations"] < 20 < counts["tact"] and counts["rest"] > 20, counts


@pytest.mark.parametrize("future", [False, True])
def test_the_tact_guard_follows_the_meaning_of_the_expression(future):
    """Сторож такта (запрет полной полосы) включается у набора сервера и молчит у «остального»: выражение
    «остального» несёт слова `not ci_only` внутри отрицаемой скобки, а тесты `ci_only` берёт — им полная
    полоса нужна. По подстроке сторож включился бы в обеих частях, и первый же прогон CI был бы красным."""
    from tests.conftest import _deselects_ci_only

    tact, rest = _expressions(future)
    assert _deselects_ci_only(tact) and _deselects_ci_only(f"({tact})")
    assert not _deselects_ci_only(rest) and not _deselects_ci_only(FULL) and not _deselects_ci_only("")
    assert selected(rest, {"ci_only"}) and not selected(tact, {"ci_only", "tact"})


def test_the_job_ceilings_come_from_the_budget():
    """Потолки заданий — не на глаз: (подготовка + время части набора на ноутбуке × поправка на раннер) ×
    запас, вверх до шага (`ops/budgets.json`, `ci`). Числа в файлах CI вписывает инструмент бюджета; формула
    здесь — второй раз. Потолок части с тестом мутаций покрывает его время на ноутбуке с поправкой на раннер."""
    budgets = json.loads((ROOT / "ops" / "budgets.json").read_text(encoding="utf-8"))
    ci = budgets["ci"]
    assert set(ci["laptop_seconds"]) == {*MATRIX, "release-contract", "docs"}
    expected = {part: math.ceil(round((ci["setup_s"] + seconds * ci["runner_factor"]) * ci["safety"] / 60
                                      / ci["round_to_min"], 9)) * ci["round_to_min"]
                for part, seconds in ci["laptop_seconds"].items()}
    doc = _ci()
    have = {row["part"]: row["minutes"] for row in doc["jobs"]["tests"]["strategy"]["matrix"]["include"]}
    have["release-contract"] = doc["jobs"]["release-contract"]["timeout-minutes"]
    have["docs"] = _docs()["jobs"]["docs"]["timeout-minutes"]
    assert have == expected, "после правки ops/budgets.json: python ops/tools/budgets.py --write"
    tool = _budget_tool()
    assert tool.ci_minutes(budgets) == expected and tool.apply(budgets, ROOT) == []
    assert ci["runner_factor"] >= 1.5 and ci["safety"] >= 1.5, "запас потолков заданий на раннер — не меньше полутора"
    if budgets["status"] == "estimate":
        # пока `basis` — замер ноутбука; после замера на сервере (шаг 8 установки) `basis` несёт время сервера,
        # и время части на ноутбуке с ним не сравнивается
        assert ci["laptop_seconds"]["tact"] >= budgets["basis"]["tact_tests_s"], "набор такта — не быстрее своего замера"
    assert tool.findings(budgets) == [], "бюджет противоречит себе: python ops/tools/budgets.py"
    assert all(5 <= minutes <= 180 for minutes in have.values()), have
    # шаг замера такта внутри своей части: потолок шага (секунды) меньше потолка задания
    assert budgets["tact_tests_ci_ceiling"] + ci["setup_s"] < have["tact"] * 60


def test_a_documents_only_commit_still_runs_docs_and_hygiene():
    doc = _docs()
    on = doc[True]
    assert on["push"] == {"paths": ["**/*.md"]} and on["pull_request"] == {"paths": ["**/*.md"]}
    assert doc["permissions"] == {"contents": "read"}
    runs = _runs(doc["jobs"]["docs"])
    assert 'python -m pytest -rs -m "(docs or tact) and not network and not archive" --strict-markers' in runs
    assert "python -B ops/tools/render_numbers.py --check" in runs
    assert "commit-emails.allow" in runs


def test_the_runs_keep_the_summary_line_of_pytest():
    """Тихий режим задан в pytest.ini (`-q`); второй `-q` в команде убрал бы итоговую
    строку «N passed in T s». Журнал CI и журнал такта обязаны её нести: по ней видно,
    сколько тестов прошло, и по ней меряется время набора сервера."""
    cfg = configparser.ConfigParser()
    cfg.read(ROOT / "pytest.ini", encoding="utf-8")
    assert cfg["pytest"]["addopts"].split()[0] == "-q"
    commands = _runs(_ci()["jobs"]["tests"]) + "\n" + _runs(_docs()["jobs"]["docs"])
    commands += "\n" + (ROOT / "ops" / "run.sh").read_text(encoding="utf-8")
    runs = [line.strip() for line in commands.splitlines()
            if "-m pytest" in line and not line.lstrip().startswith("#")]
    assert len(runs) == 6, runs          # три части набора CI, документы, такт сервера и его прогон «в будущем»
    quiet = [line for line in runs if re.search(r"\s-q\b", line)]
    assert not quiet, quiet


def test_ci_checks_the_world_canon_the_machine_book_and_the_numbers():
    runs = _runs(_ci()["jobs"]["tests"])
    for command in ("(cd data/assumptions && python -B worlds_recipe.py --check)",
                    "python -B data/assumptions/build_assumptions.py --check",
                    "python -B ops/tools/refresh_worlds.py --check",
                    "python -B ops/tools/render_numbers.py --check"):
        assert command in runs, command


def test_every_action_is_pinned_by_a_full_commit_sha():
    """Тег действия можно передвинуть задним числом, коммит — нет."""
    for path in (WORKFLOWS / "ci.yml", WORKFLOWS / "docs.yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in doc["jobs"].items():
            assert job["runs-on"] == "ubuntu-24.04", (path.name, name)
            for step in job["steps"]:
                if "uses" in step:
                    assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
        for line in path.read_text(encoding="utf-8").splitlines():
            if "uses:" in line:
                assert re.search(r"# v\d+\.\d+\.\d+$", line), f"{path.name}: нет тега в комментарии: {line}"


def test_the_python_of_ci_is_the_python_of_the_server():
    for path in (WORKFLOWS / "ci.yml", WORKFLOWS / "docs.yml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        versions = {step["with"]["python-version"] for job in doc["jobs"].values() for step in job["steps"]
                    if step.get("uses", "").startswith("actions/setup-python@")}
        assert versions == {"3.12"}, (path.name, versions)


def test_the_history_hygiene_step_reads_the_allowlist():
    """Шаг истории видит ВСЕ ветки (fetch-depth 0) и сверяет адреса со списком,
    который читает и tests/test_public_hygiene.py."""
    for doc, job in ((_ci(), "tests"), (_docs(), "docs")):
        steps = doc["jobs"][job]["steps"]
        assert steps[0]["uses"].startswith("actions/checkout@")
        assert steps[0]["with"] == {"fetch-depth": 0, "persist-credentials": False}
        runs = _runs(doc["jobs"][job])
        assert "git log --all --format='%H %ae %ce'" in runs and ".github/commit-emails.allow" in runs
    assert (ROOT / ".github" / "commit-emails.allow").exists()


def test_the_history_of_the_branch_never_carried_raw_tinvest_answers():
    """История публичного репозитория не чистится задним числом: всё, что было хоть в
    одном коммите ветки, после push видно всем и навсегда. Дерево проверяет гигиена
    (такт); здесь — история текущей ветки (то, что получит `git push origin main`):
    ни один её коммит не добавлял и не убирал признаков сырого ответа T-Invest.

    До первого push тест красный, пока ветка несёт первую сборку с сырыми ответами:
    первый push — одним свежим корневым коммитом (ops/README.md §12), прежняя
    история остаётся в локальной ветке, которая не пушится."""
    if subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=str(ROOT),
                      capture_output=True).returncode != 0:
        pytest.skip("в рабочей копии ещё нет коммитов — истории нет")
    bad = []
    for what, word in T_MARKER_WORDS.items():
        done = subprocess.run(["git", "log", "HEAD", "-i", f"-S{word}", "--format=%h", "--",
                               ".", f":(exclude,glob){T_COLLECTOR_CODE}"],
                              cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert done.returncode == 0, done.stderr
        bad += [f"{commit}: {what}" for commit in done.stdout.split()]
    assert not bad, ("в истории ветки — сырые ответы T-Invest; такую историю публиковать нельзя "
                     "(первый push — одним свежим корневым коммитом):\n" + "\n".join(sorted(set(bad))))


def test_the_tact_timing_step_uses_the_servers_selection():
    runs = _runs(_ci()["jobs"]["tests"])
    assert r"""sed -n 's/^TACT_TESTS="\(.*\)"$/\1/p' ops/run.sh""" in runs
    timing = _step(_ci()["jobs"]["tests"], "Тесты такта — замер времени")["run"]
    assert 'python -m pytest -m "($TACT)" --strict-markers --durations=0 -p no:cacheprovider' in timing
    assert runs.count('-m "($TACT)"') == 1, "набор сервера идёт в CI один раз"
    # Потолок шага — из бюджета (300 с), шаг краснеет сверх него; цель сервера (450 с) сверяет
    # замер на сервере, здесь время дольше цели — предупреждение.
    assert '["tact_tests_ci_ceiling"]' in runs and 'if [ "$spent" -gt "$ceiling" ]' in runs
    assert '["tact_tests_target"]' in runs and 'if [ "$spent" -gt "$target" ]' in runs
    failing = runs.split('if [ "$spent" -gt "$ceiling" ]', 1)[1].split("fi", 1)[0]
    warning = runs.split('if [ "$spent" -gt "$target" ]', 1)[1].split("fi", 1)[0]
    assert "::error::" in failing and "exit 1" in failing
    assert "::warning::" in warning and "exit" not in warning, "цель сервера на раннере — не отказ"
    assert 'echo "такт: $spent с из $ceiling (цель сервера — $target с)"' in runs
    budgets = json.loads((ROOT / "ops" / "budgets.json").read_text(encoding="utf-8"))
    assert (budgets["tact_tests_target"], budgets["tact_tests_ci_ceiling"]) == (450, 300)
    tact = _tact()
    assert tact.startswith("tact and "), "такт — белый список по метке tact"
    for excluded in ("not network", "not archive", "not docs", "not ci_only", "not deadline"):
        assert excluded in tact, excluded


def test_the_release_contract_is_built_in_memory():
    job = _ci()["jobs"]["release-contract"]
    assert _runs(job).strip().endswith("python -m model.build_release --check --fast --book-only")
    assert job["steps"][0]["with"] == {"persist-credentials": False}


def test_the_future_run_is_monthly_and_on_demand_and_moves_the_date():
    """Прогон «в будущем»: раз в месяц по расписанию (+180 дней, как у 850oa и
    «Ленты») и по кнопке; своя группа одновременности — расписание не отменяет push.
    Тесты сроков данных (`deadline`) в него не входят (MODEL §18): на будущей дате они
    красные по смыслу, а прогон, красный всегда, перестал бы быть сигналом."""
    doc = _ci()
    runs = _runs(doc["jobs"]["tests"])
    assert 'FAKE_TODAY=$(date -u -d "+${FUTURE_DAYS} days" +%F)' in runs
    # Дата и отбор «в будущем» ставятся одним шагом на все части: FAKE_TODAY — в окружение следующих шагов,
    # тесты сроков — вон из отбора (в набор сервера они и так не входят).
    choose = _step(doc["jobs"]["tests"], "Набор части и дата прогона")
    assert "if" not in choose, "шаг отбора идёт в каждой части"
    future = choose["run"].split('if [ "$FUTURE_DAYS" != 0 ]; then', 1)[1].split("\nfi\n", 1)[0]
    assert 'echo "FAKE_TODAY=$FAKE_TODAY" >> "$GITHUB_ENV"' in future and 'rest="$rest and not deadline"' in future
    assert _expressions(True)[1].endswith(" and not deadline") and "deadline" not in _expressions(False)[1].split("(")[0]
    assert runs.count("not deadline") == 1, "обычный прогон CI тесты сроков гоняет"
    assert doc[True]["schedule"] == [{"cron": "17 5 1 * *"}]
    days = "github.event_name == 'schedule' && '180' || inputs.future_days || '0'"
    assert doc["jobs"]["tests"]["env"]["FUTURE_DAYS"] == "${{ " + days + " }}"
    assert doc["concurrency"]["group"] == "ci-${{ github.ref }}-future${{ " + days + " }}"


def test_the_comments_about_the_future_run_match_the_schedule():
    """run.sh называет свой прогон «в будущем» дублем ежемесячного прогона CI с
    «сегодня» + 180 дней, плагин даты — «CI раз в месяц — весь набор с + 180»:
    так и стоит в ci.yml (1-го числа каждого месяца)."""
    doc = _ci()
    _, _, day, month, weekday = doc[True]["schedule"][0]["cron"].split()
    assert (day, month, weekday) == ("1", "*", "*"), "раз в месяц, 1-го числа"
    assert "'180'" in doc["jobs"]["tests"]["env"]["FUTURE_DAYS"]
    script = (ROOT / "ops" / "run.sh").read_text(encoding="utf-8")
    assert "ежемесячный прогон CI" in script and "«сегодня» + 180 дней" in script
    plugin = (ROOT / "tests" / "fakedate_plugin.py").read_text(encoding="utf-8")
    assert "CI раз в месяц — весь набор с + 180" in plugin
    server_days = re.search(r"^FUTURE_DAYS=\$\{SVCB_FUTURE_DAYS:-(\d+)\}$", script, re.M).group(1)
    assert f"«сегодня» + {server_days} дней" in plugin


def _declared_marks() -> set[str]:
    cfg = configparser.ConfigParser()
    cfg.read(ROOT / "pytest.ini", encoding="utf-8")
    return {line.split(":", 1)[0].strip() for line in cfg["pytest"]["markers"].splitlines()
            if line.strip() and not line.startswith((" ", "\t")) and ":" in line}


def _test_files() -> list[Path]:
    return sorted((ROOT / "tests").glob("test_*.py"))


def test_the_markers_are_declared_in_pytest_ini():
    """Метка мимо pytest.ini в CI — ошибка (`--strict-markers`); здесь она видна раньше."""
    declared = _declared_marks()
    assert {"tact", "docs", "ci_only", "network", "archive", "deadline"} <= declared, declared
    used = set()
    for path in _test_files():
        used |= {(m, path.name) for m in re.findall(r"pytest\.mark\.(\w+)", path.read_text(encoding="utf-8"))}
    unknown = sorted(f"{name}: {m}" for m, name in used if m not in declared | BUILTIN_MARKS)
    assert not unknown, unknown


def test_no_test_is_both_tact_and_ci_only():
    """Противоречивая пара меток: такт такой тест не возьмёт (`not ci_only`), а
    автор будет думать, что взял."""
    both = [f"{path.name}::{name}" for path in _test_files() for name, marks, _ in collect_tests(path)
            if {"tact", "ci_only"} <= marks]
    assert not both, both


def _names_a_document(value: str) -> bool:
    if not value.endswith(MD) or value.startswith("**"):      # «**.md» — маска путей CI
        return False
    return "/" in value or Path(value).stem not in TOOL_REPORTS


def test_every_test_that_reads_a_document_is_marked_docs():
    """Тест, читающий документ `*.md` репозитория, несёт метку `docs` или `tact` (на
    себе или на модуле): docs.yml гоняет `docs or tact`, и тест без обеих меток коммит
    из одних документов не прогонит — правка документа, которую он ловит, пройдёт
    непроверенной. Тест такта, читающий документ, идёт и на сервере (правила гигиены
    и запрет полей ответа API в документах — из таких)."""
    missing = []
    for path in _test_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = set()
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(c, ast.Constant) and isinstance(c.value, str) and _names_a_document(c.value)
                       for c in ast.walk(node)):
                    constants |= {t.id for t in targets if isinstance(t, ast.Name)}
        for name, marks, fn in collect_tests(path):
            if (path.name, fn.name) in NOT_A_DOCUMENT_READ or marks & {"docs", "tact"}:
                continue
            body = fn.body[1:] if ast.get_docstring(fn) else fn.body
            nodes = [n for stmt in body for n in ast.walk(stmt)]
            reads = any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and (_names_a_document(n.value) or n.value == "*" + MD) for n in nodes)
            reads = reads or any(isinstance(n, ast.Name) and n.id in constants for n in nodes)
            if reads:
                missing.append(f"{path.name}::{name}")
    assert not missing, "тесты читают документы без метки docs или tact: " + ", ".join(missing)


def _direct_git_calls(source: str) -> list[tuple[int, str]]:
    """(строка, команда) каждого списка аргументов, начинающегося с "git"; команда —
    первое слово-литерал без дефиса, «?» — если до неё стоит переменная."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, (ast.List, ast.Tuple)) and node.elts):
            continue
        first = node.elts[0]
        if not (isinstance(first, ast.Constant) and first.value == "git"):
            continue
        command = "?"
        for item in node.elts[1:]:
            if not (isinstance(item, ast.Constant) and isinstance(item.value, str)):
                break
            if not item.value.startswith("-"):
                command = item.value
                break
        found.append((node.lineno, command))
    return found


def test_git_in_the_tests_goes_through_the_sandbox_helper():
    """Ни один тест не пишет git-ом мимо помощника песочницы: коммит фикстуры из каталога,
    лишившегося `.git`, однажды лёг в ветку рабочей копии. Прямой вызов — только читающая
    команда над самой рабочей копией; команды оболочкой (`shell=True`) в тестах нет."""
    direct, shell = [], []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if path.name == GIT_HELPER:
            continue
        source = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        direct += [f"{name}:{line}: git {command}" for line, command in _direct_git_calls(source)
                   if command not in GIT_READS_OF_THE_WORKING_COPY]
        if re.search(r"shell\s*=\s*True", source) and path.name != Path(__file__).name:
            shell.append(name)
    assert not direct, ("git в тестах пишет только помощником tests/" + GIT_HELPER
                        + " (sandbox_git, sandbox_init, sandbox_clone):\n" + "\n".join(direct))
    assert not shell, f"команда оболочкой (shell=True) в тестах: {shell}"
    for user in ("test_ops_publish.py", "test_ops_run_sh.py"):
        text = (ROOT / "tests" / user).read_text(encoding="utf-8")
        assert "from tests.support_git import" in text and not _direct_git_calls(text), user


def test_the_git_guard_sees_a_writing_call():
    """Сторож ловит то, что должен: запись, команду после настроек, список с переменной
    на месте команды; чтение рабочей копии и строки документов не трогает."""
    writes = ('subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "код"], cwd=str(repo))\n'
              'subprocess.run(["git", "-c", "user.name=t", "commit", "-m", "x"])\n'
              'subprocess.run(["git", *args], cwd=cwd)\n'
              'subprocess.run(("git", "-C", str(repo), "reset", "--hard"))\n')
    assert [command for _, command in _direct_git_calls(writes)] == ["commit", "user.name=t", "?", "?"]
    assert not {c for _, c in _direct_git_calls(writes)} & GIT_READS_OF_THE_WORKING_COPY
    reads = ('subprocess.run(["git", "ls-files", "-z"], cwd=str(ROOT))\n'
             'subprocess.run(["git", "log", "HEAD", f"-S{word}"], cwd=str(ROOT))\n'
             'order = ["git branch local-history main", "git checkout --orphan"]\n'
             'case = ("git" + "@host:owner/repo.git", "owner/repo")\n')
    assert [command for _, command in _direct_git_calls(reads)] == ["ls-files", "log"]


CONTROL_CHARACTER = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def test_no_text_file_carries_a_control_character():
    """Управляющий символ в тексте — потерянная обратная косая: `\\b` в регулярке,
    записанный как U+0008, ничего не находит, и проверка с такой регуляркой зеленеет
    пустой. В текстовых файлах дерева (код, тесты, данные, документы) их нет; исключение —
    разрыв страницы в тексте, снятом с PDF (`*.pdf.txt`, фикстуры разбора документов эмитента)."""
    page_break, pdf_text = chr(12), ".pdf.txt"
    bad = []
    for name in _tree():
        text = _text(name)
        if text is None:
            continue
        bad += [f"{name}:{text.count(chr(10), 0, hit.start()) + 1}: U+{ord(hit.group()):04X}"
                for hit in CONTROL_CHARACTER.finditer(text)
                if not (hit.group() == page_break and name.endswith(pdf_text))]
    assert not bad, "управляющие символы в текстовых файлах (потерянная обратная косая?):\n" + "\n".join(bad)


def test_the_tact_whitelist_is_not_empty():
    """Белый список такта, который никого не пускает, — провал такта (код 5 pytest)."""
    tagged = [name for path in _test_files() for name, marks, _ in collect_tests(path)
              if "tact" in marks and not marks & {"network", "archive", "docs", "ci_only", "deadline"}]
    assert tagged, "ни одного теста такта"


def test_the_mutation_shards_cover_every_mutant_once(monkeypatch):
    """Части матрицы мутаций CI вместе гоняют каждого мутанта ровно один раз (правило pmut --shard); без переменной —
    весь набор; подлинное ядро — в части 1."""
    from tests import test_core_mutations as T
    from tests.mutations import MUTATIONS as ALL
    seen = []
    for k in range(1, MUTATION_SHARDS + 1):
        monkeypatch.setenv(T.SHARD_ENV, f"{k}/{MUTATION_SHARDS}")
        assert T.shard() == (k, MUTATION_SHARDS)
        seen += [m.id for m in T.shard_mutations()]
    assert sorted(seen) == sorted(m.id for m in ALL) and len(seen) == len(set(seen))
    monkeypatch.delenv(T.SHARD_ENV)
    assert T.shard() == (1, 1) and [m.id for m in T.shard_mutations()] == [m.id for m in ALL]
    for bad in ("0/10", "11/10", "x"):
        monkeypatch.setenv(T.SHARD_ENV, bad)
        try:
            T.shard()
        except ValueError:
            continue
        raise AssertionError(bad)
