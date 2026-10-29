"""Параллельный прогон набора тестов: части — как в CI, процессы — по ядрам машины.

    python ops/tools/ptest.py [-j N] [--skip часть[,часть…]] [--future ГГГГ-ММ-ДД] [--json файл]
                              [--save-durations] [--keep] [--full] [--plan]
    python ops/tools/ptest.py [-j N] [-m выражение] [--json файл] [--keep] [--full] [--plan] tests/test_<префикс>_*.py …
    python ops/tools/ptest.py --compare итог1 итог2

Без файлов — весь набор (приёмка перед push), теми же частями, что гоняет CI, и каждый тест идёт ровно
в одной из них:

1. `rest` — всё, чего нет в белом списке сервера (выражение — дополнение `TACT_TESTS` из `ops/run.sh`, как
   его собирает шаг CI «Набор части и дата прогона»): файлы тестов делятся на N процессов pytest, идущих
   одновременно. Делятся ФАЙЛЫ, а не тесты: дорогие кэши уровня процесса (книга, сетка фикстуры) считаются
   раз на файл, порядок тестов внутри файла — прежний. Балансировка — по замеренным длительностям файлов
   (`ops/ptest_durations.json`; файл без замера получает медиану): самый долгий файл кладётся в самый
   свободный процесс. Без `-j` процессов берётся по ядрам машины (ядра − 1, до 7), но не больше, чем нужно,
   чтобы часть шла не дольше своего самого долгого файла: лишние процессы её не ускорят.
2. `pools` — файлы, у которых свой пул процессов (полная полоса через фикстуру `parallel_band`, тест
   мутаций): по одному, каждому — вся машина. Рядом с соседями они делили бы ядра и упирались в потолки
   времени своих подпроцессов. Сюда же идут файлы из списка `alone` файла замеров: их тест в замеренном
   прогоне упёрся в потолок времени подпроцесса рядом с соседями.
3. `clocks` — файлы с часами (тест скорости сетки): одним процессом, без соседей — иначе время меряет
   загрузку машины, а не код.
4. `tact` — набор сервера (`TACT_TESTS`): ОДНИМ процессом и последним, как его гоняет сервер перед сборкой;
   время шага сверяется с пределом ноутбука из `ops/budgets.json` (`tact_tests_laptop_limit`) — дольше
   предела инструмент говорит строкой «ВНИМАНИЕ», код возврата от этого не меняется.

С файлами (или с `-m`) — целевой прогон потока: названные файлы тем же порядком (процессы, свои пулы, часы),
отбор — `-m` командной строки, без него — отбор `pytest.ini`; набор такта отдельным шагом не идёт.
Маски файлов инструмент раскрывает сам (PowerShell их не раскрывает).

Каждый процесс — обычный `python -m pytest <файлы>` со своим каталогом временных файлов
(`--basetemp=var/pytest-<случайное>-<ключ>`; имя короткое — пути песочниц git на Windows упираются в предел
длины): замок каталога и песочница git (`tests/conftest.py`, `tests/support_git.py`) работают как в
одиночном прогоне, общего каталога у процессов нет. Кэш pytest
(`.pytest_cache`) выключен — в него писали бы все процессы сразу. Журналы и машинные итоги процессов
(junit) — в `var/ptest/<прогон>/`; каталоги временных файлов после прогона стираются (`--keep` — оставить).
Тест мутаций оставляет там же запись «мутант → итог каждой проверки» (`mutants.json`; путь уходит ему
переменной `BANK_MUTATION_RECORD`) — её читает `ops/tools/pmut.py` (сверка записей, быстрый круг).

**Потолок времени под нагрузкой — не провал кода.** Тест части `rest`, упавший по потолку времени своего
подпроцесса (соседние процессы делят с ним ядра), перезапускается сразу после части один, без соседей, и в
итог идёт исход повтора; упал и один — красный. Потолок узнаётся только по ТИПУ исключения, как его пишет
pytest в junit-файл: сообщение провала начинается с `subprocess.TimeoutExpired:`, а трасса кончается строкой
«файл:строка: TimeoutExpired» (процессы идут с `--tb=long`). Слово в тексте другого исключения (обычное
утверждение с «TimeoutExpired» в сообщении, обёртка, `pytest.fail`) повтора не даёт: такой провал остаётся
провалом. Повторы названы в итоге обоими исходами — под соседями и одного (`retried`). Части `pools`,
`clocks` и `tact` идут без соседей и повтора не имеют. `--save-durations` запоминает файл такого теста в
списке `alone` — в следующих прогонах он идёт без соседей с самого начала.

**Состав сверяется в каждом прогоне, во всех режимах.** Рядом с первой частью идёт сбор без запуска
(`pytest --collect-only`, тем же отбором, что у одиночного прогона): множество тестов, прошедших по всем
процессам, обязано равняться собранному — ни потерянного теста, ни лишнего, ни теста в двух процессах.
Расхождение — код 1 со списком. Весь набор сверяется с одним сбором полного отбора; весь набор с пропущенной
частью (`--skip`) — со сбором оставшихся частей: «остального» по всему каталогу тестов без файлов пропущенных
частей и, если такт не пропущен, набора сервера (тест в файле, которого нет ни в одной части, потерян и
здесь); целевой прогон — со сбором вошедших в него файлов. Ключа, выключающего сверку, нет. Процесс pytest
без junit-файла — сбой прогона при любом коде возврата: pytest пишет junit и при пустом отборе (код 5).

**Чужой каталог временных файлов не стирается.** Процесс, которому pytest отказал по замку каталога
(`tests/conftest.py`: каталог занят живым прогоном — у двух прогонов совпал случайный ключ), — сбой прогона;
уборка такой каталог и его замок не трогает: они принадлежат соседу.

Итог — одна строка «итог: …» со счётом исходов по всем процессам, списком упавших тестов и временем
частей; `--json` — тот же итог файлом (исход каждого теста). `--future` — прогон «в будущем»: дата уходит
процессам переменной `FAKE_TODAY`, тесты сроков данных (`deadline`) из отбора уходят — как в CI.
`--save-durations` (только весь набор) переписывает `ops/ptest_durations.json` временами этого прогона.
`--compare` сверяет два итога — файл `--json` этого инструмента или junit-файл одиночного прогона
(`python -m pytest --junitxml=файл`): те же тесты, тот же исход каждого.

**Короткий итог (PLAYBOOK §6).** На экран — строки частей и процессов, каждый отказ ЦЕЛИКОМ (текст провала из
junit: сообщение и трасса), повторы, потерянные и лишние тесты, сбои процессов, счётчики против ожидаемых и строка
«итог: …». Полный журнал — `var/ptest/<прогон>/full.log` (журналы сбора и всех процессов подряд). Ожидаемые
счётчики — `ops/expected_counts.json` (узел `tests`, строка режима: `full`, `full --skip mutations` …; целевой прогон
сверяется только со сбором): собрано, прошло, пропущено, ожидаемо падает, упало, ошибок; если в прогоне шёл тест
мутаций — и счётчики мутаций по его записи (узел `mutations`). Упавшие сверяются и ПО ИМЕНАМ с известными красными
(узел `known_failures`, во всех режимах): упавший не из списка — «НОВЫЙ КРАСНЫЙ», известный, который шёл и не упал, —
«починен, переписать счётчики»; оба — расхождение, и при равных числах строка счётчиков — «НЕ РАВНЫ ОЖИДАЕМЫМ» (один
красный сменился другим). Счётчики меняются только отдельной правкой с причиной. Код возврата не 0 или счётчики
(числа или имена) не равны ожидаемым — полный журнал печатается целиком (`--full` — всегда).
Вердикт и код возврата от сверки счётчиков не зависят: короткий итог не меняет итог проверки. `--plan` — только
план прогона (части, процессы, файлы, сборы состава), ничего не запускается.

Коды возврата: 0 — всё зелёное (у `--compare` — итоги равны); 1 — есть упавшие тесты, процесс pytest не дал
итога, состав разошёлся со сбором или итоги не равны; 2 — неверный вызов; 5 — отбор пуст (как у pytest).
Стандартная библиотека, без зависимостей.
"""

from __future__ import annotations

import argparse
import configparser
import errno
import glob
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OK, FAILED, USAGE, EMPTY = 0, 1, 2, 5
SCHEMA = "ptest/1"
PYTEST_EMPTY = 5                    # код pytest «ни одного теста не выбрано»
DURATIONS = "ops/ptest_durations.json"
RUNS = "var/ptest"                  # журналы и junit прогонов (в git не идут)
KEEP_RUNS = 5                       # столько последних прогонов остаётся в var/ptest
KEEP_SECONDS = 24 * 3600            # и каждый прогон моложе суток: он может ещё идти
LEAST = 0.1                         # наименьший вес файла при дележе, с
REST, POOLS, CLOCKS, TACT = "rest", "pools", "clocks", "tact"
PARTS = (REST, POOLS, CLOCKS, TACT)
MUTATIONS = "mutations"             # слово для --skip: тест мутаций — один из файлов части pools
MUTATION_FILE = "tests/test_core_mutations.py"
MUTATION_RECORD_ENV = "BANK_MUTATION_RECORD"    # куда тест мутаций кладёт запись исходов (INTERFACES §8)
MUTATION_RECORD = "mutants.json"
EXPECTED = "ops/expected_counts.json"     # ожидаемые счётчики коротких итогов (PLAYBOOK §6)
NOT_MEASURED = "не замерено"
FULL_LOG = "full.log"                     # полный журнал прогона: сбор и все процессы подряд (пишет main)
COUNT_WORDS = {"collected": "собрано", "passed": "прошло", "skipped": "пропущено", "xfailed": "ожидаемо падает",
               "failed": "упало", "error": "ошибок"}
# Признаки в тексте файла тестов: свой пул процессов и свои часы. Файл с признаком идёт без соседей.
POOL_MARKS = ("parallel_band", "ThreadPoolExecutor", "ProcessPoolExecutor")
CLOCK_MARKS = ("perf_counter", "time.monotonic", "time.time()", "process_time")
# Исходы теста от лёгкого к тяжёлому: у теста с провалом и ошибкой разбора записывается тяжёлый.
OUTCOMES = ("passed", "xfailed", "skipped", "failed", "error")
PARTS_WORDS = {REST: "остальное", POOLS: "свои пулы", CLOCKS: "часы", TACT: "такт"}
TEST_ADDRESS = re.compile(r"\S+\.py::\S")
# Провал по потолку времени подпроцесса (под соседями — повтор без них) узнаётся по ТИПУ исключения, как его
# пишет pytest в junit-файл: голова сообщения провала — полное имя класса (у ошибки подготовки и уборки — после
# слов pytest «failed on setup with»), последняя строка трассы — «файл:строка: имя класса». Оба признака сразу:
# слова в тексте сообщения другого исключения повтора не дают.
CAP_TYPE = "subprocess.TimeoutExpired"
CAP_HEAD = re.compile(r'^(?:failed on (?:setup|teardown) with ")?' + re.escape(CAP_TYPE) + ":")
CAP_TAIL = re.compile(r":\d+: " + re.escape(CAP_TYPE.rsplit(".", 1)[-1]) + r"$")
ALONE = "rest-alone"                # метка процесса повтора
# Коды «замок у другого процесса» — те же, что у замка каталога временных файлов (tests/conftest.py).
LOCK_BUSY = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK}
FOREIGN = "каталог временных файлов {base} занят другим прогоном (его замок держит живой процесс) — не стёрт"
NO_COLLECT = ("--no-collect: ключа больше нет — состав сверяется со сбором в каждом прогоне (потерянный тест не "
              "должен давать зелёный итог)")


class Refused(Exception):
    """Неверный вызов или нет входов — код 2."""


# ------------------------------------------------------------------ отбор: выражения и файлы

def default_expression(root: Path = ROOT) -> str:
    """Отбор `pytest.ini` (`-m` из `addopts`) — то, что берёт `python -m pytest` без ключей."""
    cfg = configparser.ConfigParser()
    cfg.read(root / "pytest.ini", encoding="utf-8")
    words = shlex.split(cfg.get("pytest", "addopts", fallback=""))
    if "-m" not in words[:-1]:
        raise Refused("в pytest.ini нет отбора `-m` в addopts")
    return words[words.index("-m") + 1]


def tact_expression(root: Path = ROOT) -> str:
    """Выражение набора сервера — `TACT_TESTS` из `ops/run.sh` (то же чтение, что у шага CI)."""
    found = re.findall(r'^TACT_TESTS="([^"]+)"$', (root / "ops" / "run.sh").read_text(encoding="utf-8"), re.M)
    if len(found) != 1:
        raise Refused(f"TACT_TESTS в ops/run.sh: ожидалась одна строка, найдено {len(found)}")
    return found[0]


def rest_expression(full: str, tact: str, *, future: bool = False) -> str:
    """«Остальное» — дополнение набора сервера в полном отборе; «в будущем» — без тестов сроков."""
    return f"{full} and not ({tact})" + (" and not deadline" if future else "")


def test_files(root: Path = ROOT, patterns: list[str] | None = None) -> list[str]:
    """Файлы тестов путями от корня: все `tests/test_*.py` или названные (маски раскрываются здесь)."""
    if not patterns:
        return sorted(p.relative_to(root).as_posix() for p in (root / "tests").glob("test_*.py"))
    out: list[str] = []
    for pattern in patterns:
        at = pattern if os.path.isabs(pattern) else str(root / pattern)
        hits = sorted(glob.glob(at)) if any(c in pattern for c in "*?[") else [at]
        hits = [h for h in hits if Path(h).is_file()]
        if not hits:
            raise Refused(f"нет файла тестов: {pattern}")
        for hit in hits:
            try:
                name = Path(hit).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                raise Refused(f"файл вне репозитория: {pattern}") from None
            if name not in out:
                out.append(name)
    return sorted(out)


def classify(files: list[str], root: Path = ROOT, alone: tuple[str, ...] | list[str] = ()) -> dict[str, list[str]]:
    """Файлы по частям прогона: обычные (делятся на процессы), без соседей по одному (свой пул процессов или
    место в списке `alone` замеров), с часами."""
    out: dict[str, list[str]] = {REST: [], POOLS: [], CLOCKS: []}
    for name in files:
        text = (root / name).read_text(encoding="utf-8")
        if any(mark in text for mark in CLOCK_MARKS):
            out[CLOCKS].append(name)
        elif name in alone or any(mark in text for mark in POOL_MARKS):
            out[POOLS].append(name)
        else:
            out[REST].append(name)
    return out


# ------------------------------------------------------------------ балансировка по замерам

def load_durations(root: Path = ROOT) -> dict[str, dict[str, float]]:
    """Замеренные длительности файлов: имя → {"rest": с, "tact": с}; нет файла замеров — пусто."""
    path = root / DURATIONS
    if not path.exists():
        return {}
    return {name: {k: float(v) for k, v in row.items()}
            for name, row in json.loads(path.read_text(encoding="utf-8")).get("files", {}).items()}


def load_alone(root: Path = ROOT) -> list[str]:
    """Файлы, которым замеренный прогон велел идти без соседей (список `alone` файла замеров)."""
    path = root / DURATIONS
    if not path.exists():
        return []
    return [str(name) for name in json.loads(path.read_text(encoding="utf-8")).get("alone", [])]


def weights(files: list[str], durations: dict[str, dict[str, float]], *, with_tact: bool) -> dict[str, float]:
    """Вес файла для дележа: время его тестов «остального» (`with_tact` — вместе с тестами набора сервера:
    целевой прогон гоняет и их), но не меньше `LEAST` — и файл без выбранных тестов стоит процессу импорта;
    файл без замера получает медиану замеренных (новый файл не должен ни перевесить процесс, ни пройти даром)."""
    def of(row: dict[str, float]) -> float:
        return max(LEAST, row.get(REST, 0.0) + (row.get(TACT, 0.0) if with_tact else 0.0))

    known = {name: of(durations[name]) for name in files if name in durations}
    spare = statistics.median(known.values()) if known else 1.0
    return {name: known.get(name, spare) for name in files}


def split(files: list[str], weight: dict[str, float], n: int) -> list[list[str]]:
    """Делёж файлов на не больше чем `n` процессов: самый долгий файл — в самый свободный процесс (при
    равной занятости — туда, где меньше файлов); файлы равного веса — по имени. Пустых процессов нет; порядок
    файлов внутри процесса — по имени."""
    bins: list[tuple[float, list[str]]] = [(0.0, []) for _ in range(max(1, min(n, len(files))))]
    for name in sorted(files, key=lambda f: (-weight[f], f)):
        at = min(range(len(bins)), key=lambda i: (bins[i][0], len(bins[i][1]), i))
        bins[at] = (bins[at][0] + weight[name], bins[at][1] + [name])
    return [sorted(names) for _, names in bins if names]


# ------------------------------------------------------------------ процессы pytest

@dataclass
class Job:
    part: str
    label: str                         # имя журнала и junit-файла процесса
    files: list[str]                   # пусто — все файлы (набор такта)
    expression: str
    key: str = "x"                     # короткий ключ каталога временных файлов процесса
    returncode: int | None = None
    seconds: float = 0.0
    tests: dict[str, str] = field(default_factory=dict)        # тест → исход
    times: dict[str, float] = field(default_factory=dict)      # файл → секунды его тестов
    capped: set[str] = field(default_factory=set)              # тесты, упавшие по потолку времени подпроцесса
    again: bool = False                                        # повтор без соседей: его исходы заменяют прежние
    note: str = ""
    failures: dict[str, str] = field(default_factory=dict)     # тест → текст провала (сообщение и трасса junit)


def command(job: Job, run_dir: Path, basetemp: Path) -> list[str]:
    """Команда процесса: обычный pytest со своим каталогом временных файлов и машинным итогом. Стиль трассы
    закреплён (`--tb=long` — умолчание pytest): по её последней строке читается тип исключения провала."""
    return [sys.executable, "-m", "pytest", "-m", job.expression, "-rfE", "--tb=long", "-p", "no:cacheprovider",
            f"--basetemp={basetemp}", f"--junitxml={run_dir / (job.label + '.xml')}", *job.files]


def collect_command(expression: str, files: list[str], basetemp: Path) -> list[str]:
    """Сбор состава без запуска — тем же отбором, что у одиночного прогона."""
    return [sys.executable, "-m", "pytest", "--collect-only", "-m", expression, "-p", "no:cacheprovider",
            f"--basetemp={basetemp}", *files]


def junit_id(address: str) -> str:
    """Имя теста в junit-файле по его адресу pytest (`tests/test_x.py::Класс::тест[параметр]` →
    `tests.test_x.Класс::тест[параметр]`) — то же преобразование, что делает pytest."""
    path, bracket, params = address.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("\\", "/").replace("/", "."))
    return ".".join(names[:-1]) + "::" + names[-1] + bracket + params


def collected_files(text: str) -> dict[str, str]:
    """Тест → его файл из вывода `pytest --collect-only` (тихий режим pytest.ini: адрес теста на строку). Файл
    берётся из самого адреса — и у теста в подкаталоге он верен."""
    lines = (line.strip() for line in text.splitlines())
    return {junit_id(line): line.split("::", 1)[0].replace("\\", "/") for line in lines if TEST_ADDRESS.match(line)}


def read_collected(text: str) -> set[str]:
    """Тесты из вывода `pytest --collect-only`."""
    return set(collected_files(text))


def time_capped(node: ET.Element) -> bool:
    """Провал по потолку времени подпроцесса — по типу исключения в записи junit (`CAP_HEAD` и `CAP_TAIL`
    сразу), а не по словам в тексте провала."""
    lines = (node.text or "").rstrip().splitlines()
    return bool(CAP_HEAD.match(node.get("message") or "")) and bool(lines) and bool(CAP_TAIL.search(lines[-1].rstrip()))


def address(ident: str) -> str:
    """Адрес теста pytest по его имени в junit-файле — обратное к `junit_id` (файл — первые две части
    имени класса: тесты лежат прямо в `tests/`)."""
    owner, _, name = ident.partition("::")
    parts = owner.split(".")
    return "::".join(["/".join(parts[:2]) + ".py", *parts[2:], name])


def read_junit(path: Path) -> tuple[dict[str, str], dict[str, float], set[str]]:
    """(тест → исход, файл тестов → секунды, тесты с провалом по потолку времени подпроцесса) из junit-файла
    pytest. Тест назван `класс::имя` — как в отчёте pytest; у теста с двумя записями (провал и ошибка
    разбора) остаётся тяжёлый исход."""
    tests: dict[str, str] = {}
    times: dict[str, float] = {}
    capped: set[str] = set()
    for case in ET.parse(path).getroot().iter("testcase"):
        owner = case.get("classname") or ""
        ident = f"{owner}::{case.get('name')}"
        outcome = "passed"
        for child in case:
            if child.tag == "failure":
                seen = "failed"
            elif child.tag == "error":
                seen = "error"
            elif child.tag == "skipped":
                seen = "xfailed" if child.get("type") == "pytest.xfail" else "skipped"
            else:
                continue
            outcome = max(outcome, seen, key=OUTCOMES.index)
            if seen in ("failed", "error") and time_capped(child):
                capped.add(ident)
        tests[ident] = max(tests.get(ident, "passed"), outcome, key=OUTCOMES.index)
        name = "/".join(owner.split(".")[:2]) + ".py"
        times[name] = times.get(name, 0.0) + float(case.get("time") or 0.0)
    return tests, times, capped


def read_failures(path: Path) -> dict[str, str]:
    """Тест → текст его провала или ошибки из junit-файла pytest целиком: вид, сообщение и трасса (у теста с двумя
    записями — обе подряд). Тесты без провала сюда не входят."""
    out: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        ident = f"{case.get('classname') or ''}::{case.get('name')}"
        for child in case:
            if child.tag not in ("failure", "error"):
                continue
            text = f"[{child.tag}] {child.get('message') or ''}\n{(child.text or '').rstrip()}".rstrip()
            out[ident] = (out[ident] + "\n" + text) if ident in out else text
    return out


def held_by_another(path: Path) -> bool:
    """Занят ли каталог временных файлов живым прогоном pytest: его замок (`<каталог>.lock`, tests/conftest.py)
    держит другой процесс. Проба — тем же замком, не дожидаясь; свободный замок сразу отпускается."""
    lock = path.parent / (path.name + ".lock")
    if not lock.is_file():
        return False
    try:
        handle = open(lock, "r+b")
    except OSError:
        return True                              # файл замка не открыть — каталог не наш
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        return exc.errno in LOCK_BUSY
    finally:
        handle.close()
    return False


def _remove(path: Path) -> bool:
    """Стереть каталог временных файлов процесса и его замок; файлы только для чтения (объекты git
    песочниц) — тоже. Каталог, замок которого держит живой прогон, — чужой: не стирается ни он, ни его
    замок (False)."""
    def retry(function, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:
            pass

    if held_by_another(path):
        return False
    if path.exists():
        shutil.rmtree(path, onexc=retry)
    try:
        (path.parent / (path.name + ".lock")).unlink()
    except OSError:
        pass
    return True


def _stop(process: subprocess.Popen) -> None:
    """Остановить процесс pytest вместе с его подпроцессами (прерванный прогон)."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def basetemp_of(root: Path, run_dir: Path, key: str) -> Path:
    """Каталог временных файлов процесса: `var/pytest-<случайное прогона>-<ключ процесса>`."""
    return root / "var" / f"pytest-{run_dir.name.rsplit('-', 1)[-1]}-{key}"


def run_jobs(jobs: list[Job], run_dir: Path, *, root: Path = ROOT, env: dict | None = None, keep: bool = False,
             say=print) -> None:
    """Запустить процессы части одновременно и дождаться всех; итог каждого — в его записи."""
    env = dict(os.environ if env is None else env)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    live: list[tuple[Job, subprocess.Popen, Path, float, object]] = []
    try:
        for job in jobs:
            basetemp = basetemp_of(root, run_dir, job.key)
            log = open(run_dir / (job.label + ".log"), "wb")
            process = subprocess.Popen(command(job, run_dir, basetemp), cwd=str(root), env=env, stdout=log,
                                       stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            live.append((job, process, basetemp, time.monotonic(), log))
        waiting = list(live)
        while waiting:
            for item in list(waiting):
                job, process, basetemp, started, log = item
                if process.poll() is None:
                    continue
                waiting.remove(item)
                log.close()
                job.returncode, job.seconds = process.returncode, time.monotonic() - started
                junit = run_dir / (job.label + ".xml")
                if junit.exists():
                    try:
                        job.tests, job.times, job.capped = read_junit(junit)
                        job.failures = read_failures(junit)
                    except ET.ParseError as exc:     # процесс умер, не дописав итог
                        job.note = f"итог pytest не читается ({exc}), журнал — {job.label}.log"
                else:                                # и при коде 5: pytest пишет junit и при пустом отборе
                    job.note = f"нет итога pytest (код {job.returncode}), журнал — {job.label}.log"
                if not keep and not _remove(basetemp):
                    job.note = "; ".join(filter(None, [job.note, FOREIGN.format(base=basetemp.name)]))
                say(f"  {job.label}: {report_counts(count(job.tests))} за {job.seconds:.0f} с"
                    + (f" — {job.note}" if job.note else ""))
            if waiting:
                time.sleep(0.2)
    except BaseException:
        for _, process, basetemp, _, log in live:
            _stop(process)
            log.close()
            if not keep:
                _remove(basetemp)
        raise


# ------------------------------------------------------------------ итог

def count(tests: dict[str, str]) -> dict[str, int]:
    return {outcome: sum(1 for v in tests.values() if v == outcome) for outcome in OUTCOMES}


def report_counts(counts: dict[str, int]) -> str:
    shown = [f"{counts[o]} {o}" for o in OUTCOMES if counts[o]]
    return ", ".join(shown) if shown else "тестов нет"


def broken(job: Job) -> bool:
    """Процесс, которому нельзя верить: pytest не дал итога (нет junit-файла — при любом коде возврата) или
    кончился кодом сбоя (прерван, внутренняя ошибка, неверный вызов), а не кодом «есть упавшие»."""
    return bool(job.note) or job.returncode not in (0, 1, PYTEST_EMPTY)


def merge(jobs: list[Job]) -> tuple[dict[str, str], list[str], dict[str, list[str]]]:
    """(тест → исход по всем процессам; тесты, попавшие в два процесса, — дефект дележа; повторы без соседей:
    тест → [исход под соседями, исход повтора]). Исход повтора заменяет прежний."""
    tests: dict[str, str] = {}
    twice: list[str] = []
    retried: dict[str, list[str]] = {}
    for job in jobs:
        for ident, outcome in job.tests.items():
            if job.again:
                retried[ident] = [tests.get(ident, "нет"), outcome]
                tests[ident] = outcome
                continue
            if ident in tests:
                twice.append(ident)
            tests[ident] = max(tests.get(ident, "passed"), outcome, key=OUTCOMES.index)
    return tests, sorted(set(twice)), retried


def summary(jobs: list[Job], seconds: dict[str, float], *, workers: int, total: float, mode: str,
            expected: set[str] | None = None) -> dict:
    """Итог прогона. `expected` — состав одиночного прогона (сбор без запуска); None — не сверялся (сбор не
    удался — тогда прогон красный: причина в `broken`)."""
    tests, twice, retried = merge(jobs)
    bad = sorted(ident for ident, outcome in tests.items() if outcome in ("failed", "error"))
    return {"schema": SCHEMA, "mode": mode, "workers": workers, "seconds": round(total, 1),
            "parts": {part: round(spent, 1) for part, spent in seconds.items()},
            "counts": count(tests), "failed": bad, "twice": twice, "retried": retried,
            "collected": None if expected is None else len(expected),
            "lost": [] if expected is None else sorted(expected - set(tests)),
            "extra": [] if expected is None else sorted(set(tests) - expected),
            "broken": [f"{job.label}: {job.note or f'код pytest {job.returncode}'}" for job in jobs if broken(job)],
            "jobs": [{"part": job.part, "label": job.label, "files": job.files, "expression": job.expression,
                      "returncode": job.returncode, "seconds": round(job.seconds, 1), "counts": count(job.tests)}
                     for job in jobs],
            "tests": dict(sorted(tests.items())),
            "failures": failure_texts(jobs, bad)}


def failure_texts(jobs: list[Job], bad: list[str]) -> dict[str, str]:
    """Текст провала каждого упавшего теста — из процесса, чей исход пошёл в итог (у повтора — из повтора)."""
    texts: dict[str, str] = {}
    for job in jobs:
        for ident, text in job.failures.items():
            if job.again or ident not in texts:
                texts[ident] = text
    return {ident: texts.get(ident, "") for ident in bad}


def mode_key(*, whole: bool, skip: set[str] | frozenset = frozenset(), future: bool = False) -> str | None:
    """Строка режима в файле ожидаемых счётчиков: весь набор (`full`, с пропущенными частями и «в будущем» — свои
    строки); целевой прогон — None (сверяется только со сбором)."""
    if not whole:
        return None
    return "full" + (f" --skip {','.join(sorted(skip))}" if skip else "") + (" --future" if future else "")


def expected_counts(root: Path = ROOT, kind: str = "tests", key: str | None = "full") -> tuple[dict | None, str]:
    """Ожидаемые счётчики (`kind` — tests | mutations) строки режима `key` → (счётчики, пусто) или (None, почему
    сверки нет): целевой прогон, нет файла, нет строки, не замерено."""
    if key is None:
        return None, "целевой прогон: ожидаемых счётчиков нет, состав сверен со сбором"
    try:
        data = json.loads((root / EXPECTED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, f"нет файла {EXPECTED}"
    row = (data.get(kind) or {}).get(key)
    if not isinstance(row, dict):
        return None, f"в {EXPECTED} нет строки «{key}» ({kind})"
    if data.get("status") == NOT_MEASURED or any(v is None for v in row.values()):
        return None, f"ожидаемые счётчики НЕ ЗАМЕРЕНЫ ({EXPECTED}: статус «{data.get('status')}»)"
    return {k: int(v) for k, v in row.items()}, ""


def counts_of(result: dict) -> dict[str, int]:
    """Счётчики итога для сверки с ожидаемыми: собрано (сбор без запуска) и исходы по всем процессам."""
    return {"collected": result["collected"], **{k: result["counts"].get(k, 0) for k in OUTCOMES}}


def counts_line(got: dict, expected: dict | None, why: str, *, title: str, words: dict[str, str],
                names_same: bool = True) -> tuple[str, bool]:
    """Строка «счётчики против ожидаемых» и равны ли они (без ожидаемых — True: сверки нет, это сказано словами).
    `names_same` — упавшие по именам равны известным красным (`known_names`): числа равны, а имена нет — строка
    не «равны ожидаемым», а «НЕ РАВНЫ» (один красный сменился другим при том же счёте)."""
    if expected is None:
        return f"{title}: " + ", ".join(f"{w} {got.get(k)}" for k, w in words.items()) + f" — сверки с ожидаемыми нет: {why}", True
    same = all(got.get(k) == expected.get(k) for k in words)
    tail = ("равны ожидаемым" if same and names_same else
            ("числа равны, но упавшие не те, что в known_failures, — " if same else "")
            + f"НЕ РАВНЫ ОЖИДАЕМЫМ ({EXPECTED}; меняются только отдельной правкой с причиной)")
    return (f"{title}: " + ", ".join(f"{w} {got.get(k)} (ожидалось {expected.get(k)})" for k, w in words.items())
            + " — " + tail), same and names_same


def known_failures(root: Path = ROOT) -> tuple[dict[str, str] | None, str]:
    """Известные красные тесты файла ожидаемых (`known_failures`: адрес pytest → причина) → (словарь, пусто) или
    (None, почему сверки имён нет): нет файла, не замерено, узел не словарь."""
    try:
        data = json.loads((root / EXPECTED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, f"нет файла {EXPECTED}"
    if data.get("status") == NOT_MEASURED:
        return None, f"ожидаемые счётчики НЕ ЗАМЕРЕНЫ ({EXPECTED}: статус «{data.get('status')}»)"
    known = data.get("known_failures", {})
    if not isinstance(known, dict):
        return None, f"в {EXPECTED} узел known_failures — не словарь «адрес теста → причина»"
    return {str(k): str(v) for k, v in known.items()}, ""


def known_names(result: dict, known: dict[str, str] | None, why: str) -> tuple[list[str], bool]:
    """Упавшие тесты прогона против известных красных ПО ИМЕНАМ (не по числу) → (строки, равны ли). Упавший, которого
    нет в `known_failures`, — «НОВЫЙ КРАСНЫЙ»; известный красный, который в прогоне шёл и не упал, — «починен,
    переписать счётчики»; оба — расхождение. Известный, которого в прогоне нет (целевой прогон, пропущенная часть), не
    сверяется. Без списка (нет файла, не замерено) — сверки нет: при упавших это сказано словами."""
    bad = list(result["failed"])
    if known is None:
        return ([f"имена упавших не сверены с известными красными: {why}"] if bad else []), True
    ids = {junit_id(name): name for name in known}
    lines, same = [], True
    for ident in bad:
        if ident in ids:
            lines.append(f"известный красный: {ident} — {known[ids[ident]]}")
        else:
            lines.append(f"НОВЫЙ КРАСНЫЙ: {ident} — его нет в known_failures ({EXPECTED})")
            same = False
    for ident in sorted(ids):
        outcome = result["tests"].get(ident)
        if outcome is not None and outcome not in ("failed", "error"):
            lines.append(f"известный красный починен (исход {outcome}): {ident} — переписать счётчики и known_failures "
                         f"({EXPECTED}) отдельной правкой с причиной")
            same = False
    return lines, same


def mutation_counts(run_dir: Path) -> dict[str, int] | None:
    """Счётчики мутаций по записи теста мутаций этого прогона (`mutants.json`): всего, убито (упала проверка с
    именем без подчёркивания — правило теста), выжило; теста в прогоне не было — None."""
    try:
        data = json.loads((run_dir / MUTATION_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = data.get("mutants")
    if not isinstance(rows, dict):
        return None
    killed = sum(1 for res in rows.values() if any(v != "ok" and not k.startswith("_") for k, v in res.items()))
    return {"total": len(rows), "killed": killed, "survived": len(rows) - killed}


def write_full_log(run_dir: Path, jobs: list[Job]) -> Path:
    """Полный журнал прогона одним файлом: журналы сбора состава и всех процессов в порядке запуска."""
    parts = []
    for path in sorted(run_dir.glob("collect*.log")):
        parts.append(f"===== {path.name} =====\n" + path.read_text(encoding="utf-8", errors="replace"))
    for job in jobs:
        path = run_dir / (job.label + ".log")
        body = path.read_text(encoding="utf-8", errors="replace") if path.exists() else "(журнала нет)\n"
        parts.append(f"===== {job.label} ({PARTS_WORDS[job.part]}; код {job.returncode}; файлы: "
                     f"{' '.join(job.files) or 'весь отбор'}) =====\n" + body)
    target = run_dir / FULL_LOG
    target.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    return target


def shown(path: Path) -> str:
    """Путь для печати: от корня рабочей копии, а вне её — как есть."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def plan_lines(mode: str, steps: list[list[Job]], census: list, root: Path = ROOT) -> list[str]:
    """План прогона словами: шаги по очереди, процессы шага одновременно, файлы и вес по замерам, сборы состава."""
    durations = load_durations(root)
    out = [f"план: {'весь набор частями CI' if mode == 'full' else 'целевой прогон'}; шагов {len(steps)}, "
           f"процессов одновременно до {max((len(s) for s in steps), default=0)}"]
    for step in steps:
        part = step[0].part
        files = [name for job in step for name in job.files]
        weight = weights(files, durations, with_tact=mode != "full") if files else {}
        out.append(f"  {PARTS_WORDS[part]}: процессов {len(step)}")
        for job in step:
            load = sum(weight.get(name, 0.0) for name in job.files)
            out.append(f"    {job.label}" + (f" (~{load:.0f} с по замерам)" if job.files else "") + ": "
                       + (" ".join(job.files) if job.files else f"отбор «{job.expression}»"))
    for chosen, names, gone in census:
        out.append(f"  сбор состава: отбор «{chosen}»; файлов " + (str(len(names)) if names else "все")
                   + (f", без {len(gone)}" if gone else ""))
    return out


def verdict(result: dict) -> int:
    if result["broken"] or result["failed"] or result["twice"] or result["lost"] or result["extra"]:
        return FAILED
    return OK if sum(result["counts"].values()) else EMPTY


def final_line(result: dict) -> str:
    parts = ", ".join(f"{PARTS_WORDS[part]} {spent:.0f} с" for part, spent in result["parts"].items())
    word = {OK: "", FAILED: "ПРОВАЛ — ", EMPTY: "отбор пуст — "}[verdict(result)]
    census = ("состав не сверялся" if result["collected"] is None else
              f"состав равен сбору ({result['collected']})" if not (result["lost"] or result["extra"] or result["twice"])
              else f"СОСТАВ НЕ РАВЕН СБОРУ ({result['collected']})")
    again = ""
    if result.get("retried"):                # оба исхода: под соседями и одного
        pairs = [tuple(pair) for pair in result["retried"].values()]
        again = (f"; повторов без соседей — {len(pairs)} (" + "; ".join(
            f"под соседями {first}, один {final} — {pairs.count((first, final))}"
            for first, final in sorted(set(pairs))) + ")")
    return (f"итог: {word}{report_counts(result['counts'])}; тестов {sum(result['counts'].values())} за "
            f"{result['seconds']:.0f} с (процессов {result['workers']}; {parts}){again}; {census}")


def read_result(path: Path) -> dict[str, str]:
    """Тест → исход из итога этого инструмента (`--json`) или из junit-файла одиночного прогона pytest."""
    try:
        if path.suffix.lower() == ".xml":
            return read_junit(path)[0]
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ET.ParseError) as exc:
        raise Refused(f"итог {path} не читается: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Refused(f"{path}: это не итог прогона ({SCHEMA}) и не junit-файл")
    return dict(data["tests"])


def compare(a: dict[str, str], b: dict[str, str]) -> list[str]:
    """Расхождения двух итогов: тест только в одном из них или с другим исходом."""
    out = [f"только в первом: {ident} ({a[ident]})" for ident in sorted(set(a) - set(b))]
    out += [f"только во втором: {ident} ({b[ident]})" for ident in sorted(set(b) - set(a))]
    out += [f"исход {a[ident]} против {b[ident]}: {ident}" for ident in sorted(set(a) & set(b)) if a[ident] != b[ident]]
    return out


def save_durations(jobs: list[Job], root: Path = ROOT, retried: dict | None = None) -> Path:
    """Переписать замеры длительностей файлов временами этого прогона (весь набор). `retried` — тесты, упавшие
    по потолку времени подпроцесса рядом с соседями: их файлы пополняют список `alone` (сам он не сокращается —
    с ушедшей причиной строку убирают руками)."""
    alone = {name for name in load_alone(root) if (root / name).is_file()}
    alone |= {address(ident).split("::")[0] for ident in (retried or {})}
    files: dict[str, dict[str, float]] = {}
    for job in jobs:
        kind = TACT if job.part == TACT else REST
        for name, spent in job.times.items():
            row = files.setdefault(name, {REST: 0.0, TACT: 0.0})
            row[kind] = round(row[kind] + spent, 1)
    doc = {"about": "Замеренные длительности файлов тестов, секунды: rest — тесты вне набора сервера, tact — "
                    "тесты набора сервера. По ним ops/tools/ptest.py делит файлы на процессы; на исход тестов "
                    "числа не влияют. alone — файлы, чей тест упёрся в потолок времени подпроцесса рядом с "
                    "соседями: такой файл идёт без соседей (строку убирают руками). Переписывает "
                    "`python ops/tools/ptest.py --save-durations`.",
           "measured_on": time.strftime("%Y-%m-%d"), "alone": sorted(alone), "files": dict(sorted(files.items()))}
    path = root / DURATIONS
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def laptop_limit(root: Path = ROOT) -> float | None:
    """Предел времени набора такта на ноутбуке из бюджета тактов; нет поля — None."""
    try:
        return float(json.loads((root / "ops" / "budgets.json").read_text(encoding="utf-8"))["tact_tests_laptop_limit"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ------------------------------------------------------------------ прогон

def default_workers() -> int:
    """Процессов по умолчанию — как у полосы: ядра − 1, не больше 7."""
    return max(1, min(7, (os.cpu_count() or 2) - 1))


def enough(files: list[str], weight: dict[str, float], limit: int) -> int:
    """Наименьшее число процессов (не больше `limit`), при котором часть идёт не дольше своего самого долгого
    файла: больше процессов часть не ускорят, а ядра у соседей отнимут."""
    longest = max(weight[name] for name in files)
    for n in range(1, limit):
        loads = [sum(weight[name] for name in shard) for shard in split(files, weight, n)]
        if max(loads) <= longest * (1 + 1e-9):
            return n
    return limit


def plan(*, root: Path = ROOT, patterns: list[str] | None = None, expression: str | None = None,
         workers: int | None = None, skip: set[str] = frozenset(), future: bool = False
         ) -> tuple[str, list[list[Job]], list[tuple[str, list[str], list[str]]]]:
    """(режим, шаги, сборы состава): шаг — процессы, идущие одновременно; шаги идут по очереди. Сбор состава —
    (отбор, файлы, файлы вне состава): тесты, которые берёт одиночный pytest этим отбором на этих файлах (пусто —
    весь каталог тестов), кроме тестов названных файлов; весь прогон обязан равняться объединению сборов. Весь
    набор — один сбор полного отбора; весь набор с пропущенной частью — сбор «остального» по всему каталогу
    тестов без файлов пропущенных частей и, если такт не пропущен, сбор набора сервера; целевой прогон — сбор
    вошедших в него файлов. `workers` — число процессов «остального»; None — по ядрам машины, но не больше, чем
    нужно, чтобы часть шла не дольше своего самого долгого файла (`enough`)."""
    whole = not patterns and expression is None
    full = default_expression(root) + (" and not deadline" if future else "")
    named = test_files(root, patterns)
    files = classify(named, root, load_alone(root))
    if whole:
        tact = tact_expression(root)
        chosen = rest_expression(default_expression(root), tact, future=future)
    else:
        chosen = expression if expression is not None else full
    durations = load_durations(root)
    steps: list[list[Job]] = []
    if REST not in skip and files[REST]:
        weight = weights(files[REST], durations, with_tact=not whole)
        shards = split(files[REST], weight, workers or enough(files[REST], weight, default_workers()))
        steps.append([Job(REST, f"{REST}-{i + 1}", names, chosen, key=f"r{i + 1}") for i, names in enumerate(shards)])
    if POOLS not in skip:
        for i, name in enumerate(files[POOLS]):
            if name == MUTATION_FILE and MUTATIONS in skip:
                continue
            steps.append([Job(POOLS, f"{POOLS}-{i + 1}", [name], chosen, key=f"p{i + 1}")])
    if CLOCKS not in skip and files[CLOCKS]:
        steps.append([Job(CLOCKS, CLOCKS, files[CLOCKS], chosen, key="c")])
    if whole and TACT not in skip:
        steps.append([Job(TACT, TACT, [], f"({tact})", key="t")])
    if whole and not skip:
        census = [(full, [], [])]
    elif whole:                              # пропущена часть: состав — сбор оставшихся частей
        gone = sorted({name for part in (REST, POOLS, CLOCKS) if part in skip for name in files[part]}
                      | ({MUTATION_FILE} if MUTATIONS in skip else set()))
        census = [(chosen, [], gone)] + ([] if TACT in skip else [(f"({tact})", [], [])])
    else:                                    # целевой прогон: состав — файлы, которые в него вошли
        census = [(chosen, sorted(name for step in steps for job in step for name in job.files), [])]
    return ("full" if whole else "files"), steps, census


def _prune(runs: Path, now: float | None = None) -> None:
    """В var/ptest остаются последние прогоны: журналы копятся, а нужны только свежие. Каталог моложе суток
    не стирается никогда — он может принадлежать прогону, который ещё идёт (тест мутаций — больше часа)."""
    now = time.time() if now is None else now
    old = sorted((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)[:-KEEP_RUNS]
    for path in old:
        if now - path.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(path, ignore_errors=True)


def run(*, root: Path = ROOT, patterns: list[str] | None = None, expression: str | None = None,
        workers: int | None = None, skip: set[str] = frozenset(), future: str | None = None, keep: bool = False,
        say=print) -> tuple[dict, list[Job], Path]:
    """Весь прогон: шаги по очереди, итог словарём (`summary`), записи процессов и каталог журналов. Состав
    сверяется со сбором в каждом прогоне: сборы идут рядом с первой частью."""
    mode, steps, census = plan(root=root, patterns=patterns, expression=expression, workers=workers, skip=skip,
                               future=bool(future))
    if not steps:
        raise Refused("нечего запускать: все части пропущены или файлов нет")
    workers = max(len(step) for step in steps)          # столько процессов pytest идёт одновременно
    runs = root / RUNS
    run_dir = runs / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2))
    run_dir.mkdir(parents=True)
    _prune(runs)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env[MUTATION_RECORD_ENV] = str(run_dir / MUTATION_RECORD)
    if future:
        env["FAKE_TODAY"] = future
    say(f"прогон {run_dir.relative_to(root).as_posix()}: процессов {workers}"
        + (f"; «сегодня» = {future}" if future else ""))
    started = time.monotonic()
    seconds: dict[str, float] = {}
    done: list[Job] = []
    expected: set[str] | None = None
    trouble: list[str] = []
    census_runs: list[tuple[subprocess.Popen, Path, Path, set[str]]] = []      # процесс, журнал, каталог, файлы вне состава
    try:
        for i, (chosen, names, gone) in enumerate(census):
            census_temp = basetemp_of(root, run_dir, "x" if not i else f"x{i + 1}")
            census_log = run_dir / ("collect.log" if not i else f"collect-{i + 1}.log")
            with open(census_log, "wb") as log:
                census_runs.append((subprocess.Popen(collect_command(chosen, names, census_temp), cwd=str(root), env=env,
                                                     stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL),
                                    census_log, census_temp, set(gone)))
        for step in steps:
            part = step[0].part
            say(f"{PARTS_WORDS[part]}: " + (f"{len(step)} процессов, файлов {sum(len(j.files) for j in step)}"
                                             if len(step) > 1 else (step[0].files[0] if len(step[0].files) == 1
                                                                    else "один процесс")))
            at = time.monotonic()
            run_jobs(step, run_dir, root=root, env=env, keep=keep, say=say)
            done += step
            capped = sorted({ident for job in step for ident in job.capped}) if part == REST and len(step) > 1 else []
            if capped:                       # потолок времени под соседями — повтор одним процессом, без них
                say(f"повтор без соседей: тестов, упавших по потолку времени подпроцесса, — {len(capped)}")
                alone = Job(REST, ALONE, [address(ident) for ident in capped], step[0].expression, key="a",
                            again=True)
                run_jobs([alone], run_dir, root=root, env=env, keep=keep, say=say)
                done.append(alone)
            seconds[part] = seconds.get(part, 0.0) + time.monotonic() - at
        expected = set()
        for census_run, census_log, _, gone in census_runs:
            code = census_run.wait()
            if code in (0, PYTEST_EMPTY):
                found = collected_files(census_log.read_text(encoding="utf-8", errors="replace"))
                expected |= {ident for ident, name in found.items() if name not in gone}
            else:
                trouble.append(f"сбор состава: код pytest {code}, журнал — {census_log.name}")
    finally:
        for census_run, _, census_temp, _ in census_runs:
            _stop(census_run)
            _remove(census_temp)
    result = summary(done, seconds, workers=workers, total=time.monotonic() - started, mode=mode,
                     expected=None if trouble else expected)
    result["broken"] += trouble
    return result, done, run_dir


def main(argv: list[str] | None = None) -> int:
    # до разбора аргументов: справка и отказы argparse тоже печатаются по-русски
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="ptest.py", description="параллельный прогон набора тестов частями CI")
    ap.add_argument("files", nargs="*", help="файлы тестов или маски (без них — весь набор частями CI)")
    ap.add_argument("-j", "--jobs", type=int, help="процессов pytest одновременно (по умолчанию ядра − 1, до 7)")
    ap.add_argument("-m", dest="expression", help="отбор по меткам для целевого прогона (как у pytest)")
    ap.add_argument("--skip", default="", help="пропустить части: " + ", ".join((*PARTS, MUTATIONS)))
    ap.add_argument("--future", metavar="ДАТА", help="прогон «в будущем»: FAKE_TODAY и отбор без тестов сроков")
    ap.add_argument("--json", type=Path, help="записать итог (исход каждого теста) в файл")
    ap.add_argument("--save-durations", action="store_true", help=f"переписать {DURATIONS} временами прогона")
    ap.add_argument("--no-collect", action="store_true", help=argparse.SUPPRESS)       # ключ снят: отказ с причиной
    ap.add_argument("--keep", action="store_true", help="не стирать каталоги временных файлов процессов")
    ap.add_argument("--compare", nargs=2, type=Path, metavar="ИТОГ", help="сверить два итога (--json или junit)")
    ap.add_argument("--full", action="store_true", help="напечатать полный журнал и при зелёном итоге")
    ap.add_argument("--plan", action="store_true", help="только план прогона: части, процессы, файлы; ничего не запускать")
    args = ap.parse_args(argv)
    skip = {word.strip() for word in args.skip.split(",") if word.strip()}

    def say(line: str) -> None:
        print(line, flush=True)

    try:
        if args.compare:
            first, second = (read_result(path) for path in args.compare)
            diffs = compare(first, second)
            for line in diffs:
                say(f"расхождение: {line}")
            say(f"сверка итогов: тестов {len(first)} и {len(second)}, расхождений {len(diffs)}")
            return FAILED if diffs else OK
        if args.no_collect:
            raise Refused(NO_COLLECT)
        if skip - {*PARTS, MUTATIONS}:
            raise Refused(f"--skip: нет части {sorted(skip - {*PARTS, MUTATIONS})}; есть {', '.join((*PARTS, MUTATIONS))}")
        if args.jobs is not None and args.jobs < 1:
            raise Refused("-j: число процессов — от 1")
        if args.future and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.future):
            raise Refused("--future: дата вида ГГГГ-ММ-ДД")
        whole = not args.files and args.expression is None
        if args.save_durations and (not whole or skip or args.future):
            raise Refused("--save-durations: только весь набор на настоящей дате, без пропуска частей")
        if args.plan:
            mode, steps, census = plan(patterns=args.files, expression=args.expression, workers=args.jobs, skip=skip,
                                       future=bool(args.future))
            for line in plan_lines(mode, steps, census):
                say(line)
            return OK
        result, jobs, run_dir = run(patterns=args.files, expression=args.expression, workers=args.jobs, skip=skip,
                                    future=args.future, keep=args.keep, say=say)
    except Refused as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return USAGE
    except KeyboardInterrupt:
        print("прервано: процессы pytest остановлены, итога нет", file=sys.stderr)
        return FAILED
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    (run_dir / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    if args.json:
        args.json.write_text(text, encoding="utf-8", newline="\n")
    for ident in result["failed"]:           # каждый отказ целиком: сообщение и трасса из junit
        text = result["failures"].get(ident) or "(текста провала в junit нет — полный журнал ниже)"
        say(f"упал: {ident} ({result['tests'][ident]})\n" + "\n".join("    " + line for line in text.splitlines()))
    for ident, (first, final) in result["retried"].items():
        say(f"повтор без соседей: {ident} — под соседями {first} (потолок времени подпроцесса, {CAP_TYPE}), "
            f"один — {final}")
    for ident in result["twice"]:
        say(f"дважды: {ident} — тест попал в два процесса")
    for ident in result["lost"]:
        say(f"потерян: {ident} — одиночный прогон его берёт, а ни один процесс не взял")
    for ident in result["extra"]:
        say(f"лишний: {ident} — одиночный прогон его не берёт")
    for line in result["broken"]:
        say(f"сбой процесса: {line}")
    limit = laptop_limit()
    spent = result["parts"].get(TACT)
    if spent is not None and limit is not None and spent > limit:
        say(f"ВНИМАНИЕ: набор такта шёл {spent:.0f} с — дольше предела ноутбука {limit:.0f} с "
            "(ops/budgets.json, tact_tests_laptop_limit)")
    if args.save_durations:                  # упавший тест замерам не мешает; сбой процесса и неполный состав — мешают
        if result["broken"] or result["lost"] or result["extra"] or result["twice"]:
            say("длительности файлов не записаны: прогон неполон (сбой процесса или состав не равен сбору)")
        else:
            saved = save_durations(jobs, retried=result["retried"])
            say(f"длительности файлов записаны: {saved.relative_to(ROOT).as_posix()}")
    code = verdict(result)
    key = mode_key(whole=not args.files and args.expression is None, skip=skip, future=bool(args.future))
    expected, why = expected_counts(kind="tests", key=key)
    names, names_same = known_names(result, *known_failures())
    line, same = counts_line(counts_of(result), expected, why, title="счётчики тестов", words=COUNT_WORDS,
                             names_same=names_same)
    say(line)
    for name_line in names:
        say(name_line)
    same = same and names_same               # целевой прогон: числа не сверяются, имена — да
    mutants = mutation_counts(run_dir)
    if mutants is not None:
        m_expected, m_why = expected_counts(kind="mutations", key="full")
        m_line, m_same = counts_line(mutants, m_expected, m_why, title="мутации (запись теста в прогоне)",
                                     words={"total": "всего", "killed": "убито", "survived": "выжило"})
        say(m_line)
        same = same and m_same
    full = write_full_log(run_dir, jobs)
    say(f"журналы: {shown(run_dir)} (полный журнал — {shown(full)})")
    if code != OK or not same or args.full:
        reason = "по ключу --full" if code == OK and same else f"код {code}" + ("" if same else ", счётчики не равны ожидаемым")
        say(f"ПОЛНЫЙ ЖУРНАЛ ({reason}):")
        say(full.read_text(encoding="utf-8", errors="replace").rstrip())
    say(final_line(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
