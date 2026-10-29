"""Мутации ядра по ядрам машины с записью «мутант → пойман ли и какой проверкой».

    python ops/tools/pmut.py [-j N] [--shard K/N] [--only M01,M17,…] [--known [запись]] [--json файл]
                             [--timeout секунды] [--keep] [--verbose] [--full]
    python ops/tools/pmut.py --merge запись1 запись2 … [--json файл]
    python ops/tools/pmut.py --compare запись1 запись2
    python ops/tools/pmut.py --save-known запись

Механика — та же, что у теста `tests/test_core_mutations.py`, теми же функциями `tests/mutations.py`: копия
`model/` с одной правкой (`build_mutant`), проверки подпроцессом с копией первой в `sys.path`
(`run_checks_in`), потолок времени подпроцесса — как у теста. Окружение подпроцессов — то же, что ставит
тестам `tests/conftest.py`: git под потолком корня рабочей копии, пустой каталог состояния, полоса без пула,
без токена и клона данных. Решение «пойман» — правило теста: упала хотя бы одна проверка с именем без
подчёркивания; падение подготовки (`_setup`) и сбой подпроцесса (`_crash`) поимкой НЕ считаются.

Сам тест мутаций уже гоняет мутантов пулом подпроцессов (ядра − 1): на одной машине делёж на процессы
времени не убавляет. Инструмент нужен для другого:

* **запись** — исход каждого мутанта остаётся файлом (`--json`, без ключа — `var/pmut/<прогон>.json`):
  пойман ли, какими проверками и с каким текстом, сколько шёл. Ту же запись оставляет и сам тест, когда
  задана переменная `BANK_MUTATION_RECORD` (её ставит `ops/tools/ptest.py`: `var/ptest/<прогон>/mutants.json`);
  инструмент читает оба вида;
* **сбой — не поимка и не приговор:** мутант, чей подпроцесс упёрся в потолок времени или упал без итога
  (загруженная машина), перезапускается в конце один, без соседей; не дал итога и тогда — код 1 и строка
  «без решения». Каталог каждого мутанта и общий каталог состояния после прогона сверяются: проверки
  обязаны ничего в них не писать (иначе соседние мутанты влияли бы друг на друга);
* **шарды по индексу** (`--shard K/N`): мутанты с номером по порядку списка, дающим остаток K − 1 при делении
  на N, — для нескольких машин или заданий CI; записи шардов сводит `--merge` (все N шардов одного дерева,
  каждый мутант ровно один раз). Подлинное ядро проверяет первый шард;
* **быстрый круг по записи** (`--known`; без имени файла — `tests/mutations_known.json`): мутанту
  запускаются только те проверки, которые ловили его в записи (`python -m tests.mutations --check --only …`);
  хотя бы одна упала — пойман, ни одна — полный набор проверок этому мутанту (запись устарела). Мутант,
  которого в записи нет, идёт полным набором. Подлинное ядро в любом режиме проходит ВСЕ проверки.
  Приёмкой служит полный прогон — тест и CI; быстрый круг отвечает на вопрос «не потеряла ли правка ядра
  поимку» за минуты. `--save-known запись` переписывает `tests/mutations_known.json` из полной записи
  (мутант → имена поймавших проверок).

**Отпечаток дерева.** Запись несёт отпечаток дерева НА МОМЕНТ ПРОГОНА (sha256 по ядру, набору мутаций, опорам и
фикстурам проверок — `FINGERPRINT`): инструмент снимает его до первого мутанта, тест — когда пишет запись; при
чтении отпечаток не досчитывается (у записи прежней версии теста его нет — так и сказано). Дерево, менявшееся
во время прогона, названо в записи (`fingerprint_end`), и в запись поимок такая запись не идёт. `--known`
сверяет отпечаток записи поимок с деревом и говорит о расхождении; вердикт от этого не зависит (устаревшая
строка уводит мутанта в полный набор проверок), но запись пора обновить.

`--compare` сверяет две записи: те же мутанты, то же «пойман», те же проверки (у строки быстрого круга — среди
запускавшихся); тексты проверок сверяются после замены каталога мутанта и печатаются замечаниями.

**Запись поимок этого дерева.** `tests/mutations_known.json` пишет только `--save-known` из полной зелёной записи,
снятой на этом дереве. Пока записи нет (файл-заготовка без мутантов, статус «не замерено»), быстрый круг
ОТКАЗЫВАЕТ (код 2) и называет причину: запись поимок чужого дерева не подставляется.

**Короткий итог (PLAYBOOK §6).** На экран — шапка, предупреждения, каждый отказ целиком (не пойманный мутант с его
правкой, мутант без решения, след в каталоге, провал подлинного ядра с текстом проверки), счётчики против
ожидаемых и строка «итог: …». Строки мутантов по одному — в полный журнал рядом с записью (`<запись>.log`); на
экран — с `--verbose`. Ожидаемые счётчики полного набора мутантов (всего, убито, выжило) — `ops/expected_counts.json`
(узел `mutations`); меняются только отдельной правкой с причиной. Код возврата не 0 или счётчики не равны
ожидаемым — полный журнал печатается целиком (`--full` — всегда). Вердикт и код возврата от сверки счётчиков не
зависят: короткий итог не меняет итог проверки.

Коды возврата: 0 — подлинное ядро прошло все проверки, каждый мутант пойман, сбоев нет (`--compare` —
записи совпали); 1 — иначе; 2 — неверный вызов. Стандартная библиотека, без зависимостей.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OK, FAILED, USAGE = 0, 1, 2
SCHEMA = "mutation-record/1"
TEST_SCHEMA = "mutation-results/1"  # запись самого теста: итог каждой проверки (tests/test_core_mutations.py)
KNOWN_SCHEMA = "mutation-known/1"   # мутант → имена поймавших проверок (tests/mutations_known.json)
KNOWN = "tests/mutations_known.json"
EXPECTED = "ops/expected_counts.json"      # ожидаемые счётчики коротких итогов (PLAYBOOK §6): узел mutations
NOT_MEASURED = "не замерено"
RUNS = "var/pmut"                   # каталоги мутантов и записи прогонов (в git не идут)
ORIGINAL = "original"               # подлинное ядро в записи
ALL = "all"                         # запускались все проверки
TIMEOUT, CRASH, BUILD = "_timeout", "_crash", "_build"
RETRY = (TIMEOUT, CRASH)            # сбой среды, а не свойство мутанта: повтор без соседей
# Окружение подпроцессов — как у тестов (tests/conftest.py): имена без префикса банка (INTERFACES §8).
STATE_ENV, DATA_REPO_ENV, TOKEN_ENV, WORKERS_ENV = ("BANK_STATE_DIR", "BANK_DATA_REPO_DIR", "TINVEST_TOKEN",
                                                    "BANK_WORKERS")
# Файлы, от которых зависит запись: ядро, список мутантов с проверками, опоры проверок и их фикстуры.
FINGERPRINT = ("model/*.py", "tests/mutations.py", "tests/support_core*.py", "tests/fixtures/core*/**/*")


class Refused(Exception):
    """Неверный вызов или нет входов — код 2."""


def default_workers() -> int:
    """Подпроцессов одновременно — как у теста мутаций: ядра − 1, не больше 8."""
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def fingerprint(root: Path = ROOT) -> str:
    """Отпечаток дерева, на котором снята запись (sha256 по файлам `FINGERPRINT`; кэш байт-кода не в счёт)."""
    digest = hashlib.sha256()
    for mask in FINGERPRINT:
        for path in sorted(root.glob(mask)):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def known_note(known: dict, tree: str) -> str:
    """Чем отпечаток записи быстрого круга расходится с деревом; пусто — запись снята с этого дерева."""
    have = str(known.get("fingerprint") or "")
    if not have:
        return ("в записи быстрого круга нет отпечатка дерева — сверить её с деревом нельзя (запись прежней версии "
                "теста); обновить: приёмочный прогон и `pmut.py --save-known`")
    if have != tree:
        return (f"запись быстрого круга снята с ДРУГОГО дерева (отпечаток записи {have[:12]}, дерева {tree[:12]}): ядро, "
                "набор мутаций, опоры или фикстуры проверок с тех пор менялись. Вердикт от этого не зависит — устаревшая "
                "строка уводит мутанта в полный набор проверок, — но запись пора обновить: приёмочный прогон и "
                "`pmut.py --save-known`")
    return ""


def test_environment(state: Path) -> None:
    """Окружение прогона — то, в котором подпроцессы проверок идут под pytest (tests/conftest.py)."""
    from tests import support_git

    os.environ[support_git.CEILING_ENV] = support_git.session_ceiling()
    for name in (*support_git.REPO_ENV, DATA_REPO_ENV, TOKEN_ENV):
        os.environ.pop(name, None)
    os.environ[STATE_ENV] = str(state)
    os.environ[WORKERS_ENV] = "1"


def parse_shard(text: str | None) -> tuple[int, int]:
    if not text:
        return 1, 1
    found = re.fullmatch(r"(\d+)/(\d+)", text)
    if not found or not 1 <= int(found.group(1)) <= int(found.group(2)):
        raise Refused(f"--shard: ожидается K/N при 1 ≤ K ≤ N, получено «{text}»")
    return int(found.group(1)), int(found.group(2))


def chosen(mutations: list, *, shard: tuple[int, int] = (1, 1), only: list[str] | None = None) -> list:
    """Мутанты прогона: шард по номеру в списке (остаток K − 1 от деления на N) и, если названы, только они."""
    k, n = shard
    out = [m for i, m in enumerate(mutations) if i % n == k - 1]
    if only:
        unknown = sorted(set(only) - {m.id for m in mutations})
        if unknown:
            raise Refused(f"--only: нет мутантов {unknown}")
        out = [m for m in out if m.id in set(only)]
    return out


def judged(result: dict[str, str]) -> dict:
    """Итог набора проверок языком записи: пойман ли (правило теста), какими проверками, сбой."""
    by = {k: v for k, v in result.items() if v != "ok" and not k.startswith("_")}
    trouble = next((f"{k}: {v}" if v else k for k, v in result.items() if k.startswith("_")), None)
    return {"caught": bool(by), "by": by, "trouble": trouble, "checks": sum(1 for k in result if not k.startswith("_"))}


def _checks(target: Path | None, timeout: float, only: list[str] | None = None) -> dict[str, str]:
    """`run_checks_in` теста; потолок времени — сбой среды с именем, а не исключение."""
    from tests.mutations import run_checks_in

    try:
        return run_checks_in(target, timeout) if only is None else run_checks_in(target, timeout, only=only)
    except subprocess.TimeoutExpired:
        return {TIMEOUT: f"подпроцесс проверок шёл дольше {timeout:.0f} с"}


def one(mutation, work: Path, *, timeout: float, known: list[str] | None = None) -> dict:
    """Один мутант: копия ядра с правкой, проверки, строка записи. `known` — проверки, ловившие его в прежней
    записи (быстрый круг): упала хоть одна — пойман, ни одна — полный набор."""
    from tests.mutations import build_mutant

    started = time.monotonic()
    head = {"title": mutation.title, "path": mutation.path}
    try:
        target = build_mutant(mutation, work / mutation.id)
    except Exception as exc:  # noqa: BLE001 — строка-цель не найдена: мутант не собран, это не поимка
        return {**head, "caught": False, "by": {}, "trouble": f"{BUILD}: {type(exc).__name__}: {exc}"[:300],
                "checks": 0, "ran": ALL, "left": [], "seconds": round(time.monotonic() - started, 1), "attempts": 1}
    ran: str | list[str] = ALL
    row = None
    if known:
        row, ran = judged(_checks(target, timeout, only=sorted(known))), sorted(known)
        if not row["caught"] and not needs_retry(row):
            row, ran = None, ALL             # запись устарела: ни одна прежняя проверка не упала — полный набор
    if row is None:
        row = judged(_checks(target, timeout))
    left = sorted(p.name for p in target.iterdir() if p.name != "model")
    return {**head, **row, "ran": ran, "left": left, "seconds": round(time.monotonic() - started, 1), "attempts": 1}


def original(timeout: float) -> dict:
    """Подлинное ядро: все проверки обязаны пройти."""
    started = time.monotonic()
    row = judged(_checks(None, timeout))
    return {"ok": not row["by"] and not row["trouble"] and row["checks"] > 0, "failed": row["by"],
            "trouble": row["trouble"], "checks": row["checks"], "seconds": round(time.monotonic() - started, 1)}


def needs_retry(row: dict) -> bool:
    return str(row.get("trouble") or "").startswith(RETRY)


def words(row: dict) -> str:
    if row["caught"]:
        return f"пойман ({len(row['by'])}: {', '.join(sorted(row['by'])[:3])}{'…' if len(row['by']) > 3 else ''})"
    return "НЕ ПОЙМАН" + (f" — {row['trouble']}" if row["trouble"] else "")


def run(*, root: Path = ROOT, workers: int | None = None, shard: tuple[int, int] = (1, 1),
        only: list[str] | None = None, known: dict | None = None, timeout: float = 300.0, keep: bool = False,
        runs: Path | None = None, say=print, progress=None) -> dict:
    """Прогон мутантов шарда пулом подпроцессов; возвращает запись. `runs` — где завести каталог прогона
    (по умолчанию `var/pmut` рабочей копии). `progress` — куда идут строки мутантов по одному (по умолчанию —
    туда же, куда `say`; короткий итог командной строки кладёт их только в полный журнал)."""
    progress = progress or say
    from tests.mutations import MUTATIONS

    workers = workers or default_workers()
    tree = fingerprint(root)                 # отпечаток дерева — на момент прогона: до первого мутанта
    todo = chosen(list(MUTATIONS), shard=shard, only=only)
    with_original = shard[0] == 1 and not only
    work = (runs or root / RUNS) / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3))
    state = work / "state"
    state.mkdir(parents=True)
    test_environment(state)
    prior = {name: sorted(row["by"]) for name, row in (known or {}).get("mutants", {}).items() if row.get("by")}
    say(f"прогон {work.name}: мутантов {len(todo)} из {len(MUTATIONS)}"
        f" (шард {shard[0]}/{shard[1]}), подпроцессов {workers}, потолок {timeout:.0f} с"
        + (f"; быстрый круг по записи ({sum(1 for m in todo if m.id in prior)} мутантов в ней)" if known else ""))
    stale = known_note(known, tree) if known else ""
    if stale:
        say("ВНИМАНИЕ: " + stale)
    started = time.monotonic()
    rows: dict[str, dict] = {}
    core: dict | None = None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(one, m, work, timeout=timeout, known=prior.get(m.id)): m.id for m in todo}
        if with_original:
            jobs[pool.submit(original, timeout)] = ORIGINAL
        for done in as_completed(jobs):
            name, row = jobs[done], done.result()
            if name == ORIGINAL:
                core = row
                say("  подлинное ядро: " + (f"проверок {row['checks']}, все ok" if row["ok"] else
                                             f"НЕ ok: {row['failed'] or row['trouble']}") + f" за {row['seconds']:.0f} с")
                continue
            rows[name] = row
            progress(f"  {name}: {words(row)} за {row['seconds']:.0f} с [{len(rows)}/{len(todo)}]")
    # Сбой среды (потолок времени, падение подпроцесса без итога) — повтор по одному, без соседей.
    if core is not None and needs_retry(core):
        say(f"  подлинное ядро: повтор без соседей (первый раз: {core['trouble']})")
        core = original(timeout)
    for m in todo:
        if not needs_retry(rows[m.id]):
            continue
        first = rows[m.id]["trouble"]
        row = one(m, work, timeout=timeout, known=prior.get(m.id))
        row["attempts"], row["first_trouble"] = 2, first
        rows[m.id] = row
        say(f"  {m.id}: повтор без соседей — {words(row)} за {row['seconds']:.0f} с (первый раз: {first})")
    stray = sorted(p.name for p in state.iterdir())
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    record = {"schema": SCHEMA, "fingerprint": tree, "shard": f"{shard[0]}/{shard[1]}",
              "workers": workers, "timeout": timeout, "known": bool(known),
              "seconds": round(time.monotonic() - started, 1), "state_left": stray, ORIGINAL: core,
              "mutants": {m.id: rows[m.id] for m in todo}}
    if stale:
        record["known_note"] = stale
    after = fingerprint(root)
    if after != tree:                        # дерево правили на ходу: у записи нет одного дерева
        record["fingerprint_end"] = after
        say("ВНИМАНИЕ: дерево менялось во время прогона (отпечаток до и после не равны) — запись несёт отпечаток начала")
    return record


# ------------------------------------------------------------------ итог, сведение, сверка

def findings(record: dict) -> dict[str, list[str]]:
    """Что в записи не так: непойманные, без решения (сбой среды), следы в каталогах, подлинное ядро."""
    rows = record["mutants"]
    core = record.get(ORIGINAL)
    return {"missed": sorted((k for k, r in rows.items() if not r["caught"] and not needs_retry(r)), key=_order),
            "undecided": sorted((k for k, r in rows.items() if needs_retry(r)), key=_order),
            "left": sorted((k for k, r in rows.items() if r.get("left")), key=_order)
                    + (["каталог состояния"] if record.get("state_left") else []),
            "original": [] if core is None or core["ok"] else [str(core["failed"] or core["trouble"])]}


def verdict(record: dict, *, whole: bool = False) -> int:
    """0 — всё поймано и чисто; `whole` — запись обязана нести и итог подлинного ядра."""
    if any(findings(record).values()) or (whole and record.get(ORIGINAL) is None):
        return FAILED
    return OK


def final_line(record: dict) -> str:
    rows, bad, core = record["mutants"], findings(record), record.get(ORIGINAL)
    core_words = ("не проверялось" if core is None else f"{core['checks']} проверок ok" if core["ok"] else "ПРОВАЛ")
    return (f"итог: мутантов {len(rows)}, поймано {sum(1 for r in rows.values() if r['caught'])}, не поймано "
            f"{len(bad['missed'])}, без решения {len(bad['undecided'])}; подлинное ядро: {core_words}; "
            f"подпроцессов {record['workers']}; {record['seconds']:.0f} с")


def merge(records: list[dict]) -> dict:
    """Свести записи шардов одного дерева: все N шардов, каждый мутант ровно один раз."""
    if not records:
        raise Refused("--merge: нет записей")
    if len({r["fingerprint"] for r in records}) != 1:
        raise Refused("--merge: записи сняты с разных деревьев (отпечатки не равны)")
    shards = sorted(r["shard"] for r in records)
    n = int(shards[0].split("/")[1])
    if shards != sorted(f"{k}/{n}" for k in range(1, n + 1)):
        raise Refused(f"--merge: нужны все шарды 1/{n}…{n}/{n} по одному, получены {shards}")
    rows: dict[str, dict] = {}
    for record in records:
        twice = sorted(set(rows) & set(record["mutants"]), key=_order)
        if twice:
            raise Refused(f"--merge: мутанты в двух шардах: {twice[:5]}")
        rows.update(record["mutants"])
    first = next(r for r in records if r["shard"].startswith("1/"))
    return {"schema": SCHEMA, "fingerprint": first["fingerprint"], "shard": "1/1",
            "workers": max(r["workers"] for r in records), "timeout": first["timeout"],
            "known": any(r.get("known") for r in records), "seconds": round(sum(r["seconds"] for r in records), 1),
            "state_left": sorted({x for r in records for x in r.get("state_left", [])}),
            ORIGINAL: first.get(ORIGINAL), "mutants": dict(sorted(rows.items(), key=lambda kv: _order(kv[0])))}


def _order(name: str):
    digits = re.sub(r"\D", "", name)
    return (int(digits) if digits else 0, name)


def _plain(text: str) -> str:
    """Текст проверки без каталога прогона: путь копии мутанта у двух прогонов разный."""
    return re.sub(r"[^\s'\"]*[\\/](?:pmut|pytest-[\w.-]+)[\\/][^\s'\"]*", "<каталог мутанта>", str(text))


def compare(a: dict, b: dict) -> tuple[list[str], list[str]]:
    """(расхождения, замечания) двух записей. Расхождение — мутант только в одной записи целого набора, другое
    «пойман», другие проверки (у строки быстрого круга — среди запускавшихся), другой итог подлинного ядра.
    Замечание — тот же состав проверок, но другой текст; мутанты вне шарда второй записи не сверяются."""
    diffs: list[str] = []
    notes: list[str] = []
    if not a["fingerprint"] or not b["fingerprint"]:
        notes.append("отпечаток дерева есть не у обеих записей: с одного ли дерева они сняты, сказать нельзя")
    elif a["fingerprint"] != b["fingerprint"]:
        notes.append("записи сняты с разных деревьев (отпечатки не равны)")
    partial = a["shard"] != "1/1" or b["shard"] != "1/1"
    lonely = sorted(set(a["mutants"]) ^ set(b["mutants"]), key=_order)
    if partial:
        notes.append(f"одна из записей — шард: сверены общие мутанты ({len(set(a['mutants']) & set(b['mutants']))}), "
                     f"без пары — {len(lonely)}")
    else:
        diffs += [f"{name}: есть только в {'первой' if name in a['mutants'] else 'второй'} записи" for name in lonely]
    for name in sorted(set(a["mutants"]) & set(b["mutants"]), key=_order):
        x, y = a["mutants"][name], b["mutants"][name]
        if x["caught"] != y["caught"]:
            diffs.append(f"{name}: пойман {x['caught']} против {y['caught']} ({x['trouble']} / {y['trouble']})")
            continue
        scope = None
        for row in (x, y):
            if row["ran"] != ALL:
                scope = set(row["ran"]) if scope is None else scope & set(row["ran"])
        bx = {k: v for k, v in x["by"].items() if scope is None or k in scope}
        by = {k: v for k, v in y["by"].items() if scope is None or k in scope}
        if set(bx) != set(by):
            diffs.append(f"{name}: проверки только в первой {sorted(set(bx) - set(by))}, только во второй "
                         f"{sorted(set(by) - set(bx))}")
            continue
        changed = sorted(k for k in bx if bx[k] and by[k] and _plain(bx[k]) != _plain(by[k]))
        if changed:
            notes.append(f"{name}: другой текст у проверок {changed}")
    ca, cb = a.get(ORIGINAL), b.get(ORIGINAL)
    if ca is not None and cb is not None and (ca["ok"], ca["checks"], ca["failed"]) != (cb["ok"], cb["checks"],
                                                                                     cb["failed"]):
        diffs.append(f"подлинное ядро: {(ca['ok'], ca['checks'])} против {(cb['ok'], cb['checks'])}")
    return diffs, notes


def from_test(raw: dict, root: Path = ROOT) -> dict:
    """Запись самого теста (итог каждой проверки) — языком записи инструмента. Отпечаток дерева — тот, что тест
    записал в момент прогона; при чтении он не досчитывается (у записи прежней версии теста отпечатка нет)."""
    core = None
    if isinstance(raw.get(ORIGINAL), dict):
        row = judged(raw[ORIGINAL])
        core = {"ok": not row["by"] and not row["trouble"] and row["checks"] > 0, "failed": row["by"],
                "trouble": row["trouble"], "checks": row["checks"], "seconds": None}
    rows = {name: {"title": "", "path": "", **judged(result), "ran": ALL, "left": [], "seconds": None, "attempts": 1}
            for name, result in (raw.get("mutants") or {}).items()}
    return {"schema": SCHEMA, "fingerprint": str(raw.get("fingerprint") or ""), "shard": "1/1",
            "workers": raw.get("workers") or 0, "timeout": 300.0, "known": False, "seconds": raw.get("seconds") or 0.0,
            "state_left": [], ORIGINAL: core, "mutants": dict(sorted(rows.items(), key=lambda kv: _order(kv[0])))}


def from_known(raw: dict) -> dict:
    """Запись «мутант → имена поймавших проверок» — языком записи инструмента (для быстрого круга)."""
    rows = {name: {"title": "", "path": "", "caught": bool(names), "by": {k: "" for k in names}, "trouble": None,
                   "checks": len(names), "ran": sorted(names), "left": [], "seconds": None, "attempts": 1}
            for name, names in (raw.get("mutants") or {}).items()}
    return {"schema": SCHEMA, "fingerprint": raw.get("fingerprint") or "", "shard": "1/1", "workers": 0,
            "timeout": 300.0, "known": False, "seconds": 0.0, "state_left": [], ORIGINAL: None, "mutants": rows}


def known_of(record: dict) -> dict:
    """Полная запись → «мутант → имена поймавших проверок» (то, что хранит репозиторий)."""
    return {"schema": KNOWN_SCHEMA,
            "about": "Проверки, поймавшие каждого мутанта в последней полной записи (tests/mutations.py). По ним "
                     "`python ops/tools/pmut.py --known` гоняет быстрый круг; устаревшая строка не страшна — мутант "
                     "идёт полным набором проверок. Переписывает `python ops/tools/pmut.py --save-known запись`.",
            "fingerprint": record["fingerprint"],
            "mutants": {name: sorted(row["by"]) for name, row in sorted(record["mutants"].items(),
                                                                         key=lambda kv: _order(kv[0]))}}


def read_record(path: Path, root: Path = ROOT) -> dict:
    """Запись любого из трёх видов: инструмента, самого теста, «мутант → проверки»."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"запись {path} не читается: {exc}") from exc
    schema = raw.get("schema") if isinstance(raw, dict) else None
    if schema == SCHEMA:
        return raw
    if schema == TEST_SCHEMA:
        return from_test(raw, root)
    if schema == KNOWN_SCHEMA:
        return from_known(raw)
    raise Refused(f"{path}: это не запись мутаций ({SCHEMA}, {TEST_SCHEMA}, {KNOWN_SCHEMA})")


def expected_counts(root: Path = ROOT, key: str = "full") -> tuple[dict | None, str]:
    """Ожидаемые счётчики мутаций режима `key` из `ops/expected_counts.json` → (счётчики, пусто) или (None, почему
    сверки нет): файла нет, строки режима нет, не замерено."""
    path = root / EXPECTED
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, f"нет файла {EXPECTED}"
    row = (data.get("mutations") or {}).get(key)
    if not isinstance(row, dict):
        return None, f"в {EXPECTED} нет строки мутаций «{key}»"
    if data.get("status") == NOT_MEASURED or any(row.get(k) is None for k in ("total", "killed", "survived")):
        return None, f"ожидаемые счётчики НЕ ЗАМЕРЕНЫ ({EXPECTED}: статус «{data.get('status')}»)"
    return {k: int(row[k]) for k in ("total", "killed", "survived")}, ""


def counts_of(record: dict) -> dict[str, int]:
    """Счётчики записи: всего мутантов, убито (пойман по правилу теста), выжило (не пойман и не сбой среды), без
    решения (сбой среды и после повтора)."""
    bad = findings(record)
    rows = record["mutants"]
    return {"total": len(rows), "killed": sum(1 for r in rows.values() if r["caught"]),
            "survived": len(bad["missed"]), "undecided": len(bad["undecided"])}


def counts_line(record: dict, expected: dict | None, why: str) -> tuple[str, bool]:
    """Строка «счётчики против ожидаемых» и равны ли они (без ожидаемых — True: сверки нет, это сказано словами)."""
    got = counts_of(record)
    words = {"total": "всего", "killed": "убито", "survived": "выжило"}
    if expected is None:
        return ("мутации: " + ", ".join(f"{words[k]} {got[k]}" for k in words) + f", без решения {got['undecided']} — "
                f"сверки с ожидаемыми нет: {why}"), True
    same = all(got[k] == expected[k] for k in words) and not got["undecided"]
    return ("мутации: " + ", ".join(f"{words[k]} {got[k]} (ожидалось {expected[k]})" for k in words)
            + f", без решения {got['undecided']} — " + ("равны ожидаемым" if same else
            f"НЕ РАВНЫ ОЖИДАЕМЫМ ({EXPECTED}; меняются только отдельной правкой с причиной)")), same


def edit_words(name: str) -> str:
    """Правка мутанта словами: файл и «было → стало» (набор `tests/mutations.py`)."""
    try:
        from tests.mutations import MUTATIONS

        m = next(x for x in MUTATIONS if x.id == name)
    except (ImportError, StopIteration):
        return ""
    return f"{m.path}: «{m.find}» → «{m.replace}»"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    # до разбора аргументов: справка и отказы argparse тоже печатаются по-русски
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="pmut.py", description="мутации ядра по ядрам машины с записью исходов")
    ap.add_argument("-j", "--jobs", type=int, help="подпроцессов проверок одновременно (по умолчанию — как у теста)")
    ap.add_argument("--shard", metavar="K/N", help="только мутанты шарда K из N (по номеру в списке)")
    ap.add_argument("--only", help="только названные мутанты через запятую (M01,M17)")
    ap.add_argument("--known", nargs="?", const=ROOT / KNOWN, type=Path, metavar="ЗАПИСЬ",
                    help=f"быстрый круг: мутанту — проверки, ловившие его в записи (без имени — {KNOWN})")
    ap.add_argument("--timeout", type=float, default=300.0, help="потолок времени подпроцесса проверок, с (как у теста)")
    ap.add_argument("--json", type=Path, help="куда положить запись прогона или сведённую запись")
    ap.add_argument("--keep", action="store_true", help="не стирать каталоги мутантов")
    ap.add_argument("--verbose", action="store_true", help="строки мутантов по одному — и на экран (всегда — в журнал)")
    ap.add_argument("--full", action="store_true", help="напечатать полный журнал и при зелёном итоге")
    ap.add_argument("--merge", nargs="+", type=Path, metavar="ЗАПИСЬ", help="свести записи шардов в одну")
    ap.add_argument("--compare", nargs=2, type=Path, metavar="ЗАПИСЬ", help="сверить две записи")
    ap.add_argument("--save-known", type=Path, metavar="ЗАПИСЬ", help=f"переписать {KNOWN} из полной записи")
    args = ap.parse_args(argv)

    journal: list[str] = []                  # полный журнал прогона: строки экрана и строки мутантов по одному

    def say(line: str) -> None:
        journal.append(line)
        print(line, flush=True)

    def progress(line: str) -> None:
        journal.append(line)
        if args.verbose:
            print(line, flush=True)

    try:
        if args.compare:
            diffs, notes = compare(read_record(args.compare[0]), read_record(args.compare[1]))
            for line in notes:
                say(f"замечание: {line}")
            for line in diffs:
                say(f"расхождение: {line}")
            say(f"сверка записей: расхождений {len(diffs)}, замечаний {len(notes)}")
            return FAILED if diffs else OK
        if args.save_known:
            record = read_record(args.save_known)
            if record["shard"] != "1/1" or record.get("known") or verdict(record) != OK:
                raise Refused("--save-known: нужна полная зелёная запись всех мутантов (не шард и не быстрый круг)")
            if record.get("fingerprint_end"):
                raise Refused("--save-known: дерево менялось во время прогона этой записи — у неё нет одного дерева")
            _write(ROOT / KNOWN, known_of(record))
            say(f"записано: {KNOWN} (мутантов {len(record['mutants'])})")
            have, tree = str(record.get("fingerprint") or ""), fingerprint()
            if not have:                     # отпечаток записи поимок — записи, а не дерева в момент чтения
                say("ВНИМАНИЕ: в записи нет отпечатка дерева (снята прежней версией теста) — запись поимок сохранена без "
                    "отпечатка: быстрый круг скажет, что сверить её с деревом нельзя")
            elif have != tree:
                say(f"ВНИМАНИЕ: запись снята с другого дерева (отпечаток записи {have[:12]}, дерева {tree[:12]}) — запись "
                    "поимок несёт отпечаток записи, а не сегодняшнего дерева")
            return OK
        if args.merge:
            record = merge([read_record(path) for path in args.merge])
        else:
            if args.jobs is not None and args.jobs < 1:
                raise Refused("-j: число подпроцессов — от 1")
            if args.timeout <= 0:
                raise Refused("--timeout: положительное число секунд")
            only = [word.strip() for word in args.only.split(",") if word.strip()] if args.only else None
            known = None
            if args.known:
                if not args.known.exists():
                    raise Refused(f"нет записи поимок {args.known}: быстрого круга на этом дереве ещё нет — её пишет "
                                  "`pmut.py --save-known <запись>` из полной зелёной записи прогона мутаций этого дерева "
                                  "(`pmut.py` или тест мутаций в `ptest.py`)")
                known = read_record(args.known)
                if not known["mutants"]:
                    raise Refused(f"запись поимок {args.known} пуста ({NOT_MEASURED}): быстрый круг отказывает, пока "
                                  "полный прогон мутаций этого дерева не записан `pmut.py --save-known <запись>`")
            record = run(workers=args.jobs, shard=parse_shard(args.shard), only=only, known=known,
                         timeout=args.timeout, keep=args.keep, say=say, progress=progress)
    except Refused as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return USAGE
    out = args.json or ROOT / RUNS / (time.strftime("%Y%m%d-%H%M%S") + ".json")
    _write(out, record)
    bad = findings(record)
    for name in bad["missed"]:                # каждый отказ целиком: мутант, его правка, итог проверок
        row = record["mutants"][name]
        edit = edit_words(name)
        say(f"не пойман: {name} «{row['title']}»: {row['trouble'] or 'все проверки ok'}"
            + (f"\n  правка {edit}" if edit else ""))
    for name in bad["undecided"]:
        say(f"без решения: {name} — {record['mutants'][name]['trouble']} (сбой среды и после повтора без соседей)")
    for name in bad["left"]:
        say(f"след в каталоге: {name} — проверки пишут в каталог мутанта или состояния")
    for line in bad["original"]:
        say(f"подлинное ядро не прошло проверки: {line}")
    code = verdict(record, whole=not args.only and record["shard"].startswith("1/"))
    whole = record["shard"] == "1/1" and not args.only
    expected, why = expected_counts() if whole else (None, "прогон не всего набора (шард или --only)")
    line, same = counts_line(record, expected, why)
    say(line)
    say(f"запись: {out}")
    if record.get("known_note"):
        say("ВНИМАНИЕ: " + record["known_note"])
    log = out.with_suffix(".log")
    final = final_line(record)
    log.write_text("\n".join(journal + [f"полный журнал: {log}", final]) + "\n", encoding="utf-8", newline="\n")
    say(f"полный журнал: {log}")
    if code != OK or not same or args.full:
        reason = "по ключу --full" if code == OK and same else f"код {code}" + ("" if same else ", счётчики не равны ожидаемым")
        print(f"ПОЛНЫЙ ЖУРНАЛ ({reason}) — {log}:", flush=True)
        print("\n".join(journal[:-1]), flush=True)
    say(final)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
