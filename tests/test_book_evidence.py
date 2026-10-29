# -*- coding: utf-8 -*-
"""Доказательные листы книги Совкомбанка в дереве: вывод на ядре и листы приёмки `evidence/path/` (запись вывода с
книгой сверяют tests/test_book_template.py и tests/test_ops_rederive.py), бэктест маржи `evidence/nii/` (tests/
test_book_sheet_backtest_path.py), надстройка миров `evidence/worlds_bank/` (tests/test_book_worlds.py), сборка шаблона
`evidence/assemble/`. Здесь — свойства листов, общие для любой книги: в каталоге только листы книги, малые входы бэктеста
равны описи, ни в одном файле листов нет ответов брокерского API (файлом, таблицей или выпиской его полей); лист вывода
отвечает за ядро, которое встречает; лист предельной экономики роста повторяет свою запись на книге и фактах дерева.
Метка `tact` — у сверок без запуска полного вывода.

Тест писался под книгу образца (Т-Технологии) с её листами evidence/{regulation, capital, pnl, nii, regimes, market,
governance} — копиями листов калибровки образца с его числами. Листы сняты в медленном круге вместе с тестами их
воспроизведения, описи их малых входов и сверки с этапом 1 образца (как у ВТБ, 47a7917): у книги Совкомбанка листы
калибровки — в папке передачи (stage1/calib-*). Сняты и тесты записи вывода на ядре в форме образца (её числа сверяют
test_book_template.py и test_ops_rederive.py) и листа двух оснований маржи квартала после якоря (лист образца)."""
from __future__ import annotations

import json
import re

import pytest

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

# Признаки сырого ответа брокерского API (конверт запроса, заголовки, поля): в листах их быть не должно.
# Строки собраны из частей: сам тест — не «сырой ответ» для общего теста гигиены репозитория
T_RAW_MARKERS = ("x-rate" + "limit", "headers_" + "kept", "instrument" + "Id", "dividend" + "Net",
                 "recommendation" + "Date", "target" + "Price", '"na' + 'no"')
T_ANSWER_WORDS = tuple(a + b for a, b in (("dividend", "Net"), ("record", "Date"), ("lastBuy", "Date"), ("payment", "Date"),
                                          ("declared", "Date"), ("Get", "Dividends"), ("Instruments", "Service"),
                                          ("tinvest_", "samples")))
T_TABLE_COLUMN = re.compile(r"^t_[a-z_]+$")
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
PATH_SHEET = S.EVIDENCE / "path" / "derive_on_engine.py"
MARGINAL_SHEET = S.EVIDENCE / "path" / "marginal_loan.py"           # предельная экономика роста (устав §4)
MARGINAL_RECORD = S.EVIDENCE / "path" / "out" / "marginal_loan_out.json"
AREAS = ("assemble", "nii", "path", "worlds_bank")                     # листы книги Совкомбанка в дереве
WITH_README = ("nii", "path", "worlds_bank")                          # сборка шаблона описана в evidence/README.md
INVENTORIED = ("nii",)                                                 # малые входы с описью inputs/SOURCES.json


def _close_json(a, b, tol: float = 1e-9) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close_json(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close_json(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return a == b


def _close_text(a: str, b: str) -> bool:
    """Тексты равны; иначе — равны вне чисел, а числа расходятся не больше единицы последнего напечатанного знака
    (последний бит libm на другой платформе может сдвинуть округление печати)."""
    if a == b:
        return True
    if NUM.sub("#", a) != NUM.sub("#", b):
        return False
    for x, y in zip(NUM.findall(a), NUM.findall(b)):
        if x != y:
            dec = len(x.split(".")[1]) if "." in x and "e" not in x.lower() else 0
            if abs(float(x) - float(y)) > 10 ** -dec + 1e-12:
                return False
    return True


@pytest.mark.tact
def test_the_evidence_areas_are_the_sheets_of_the_book():
    """В каталоге листов — только листы книги Совкомбанка: вывод на ядре и листы приёмки, бэктест маржи, надстройка миров,
    сборка шаблона; у листов с запуском — README; листов книги-образца (evlib, extract_inputs) нет."""
    areas = sorted(p.name for p in S.EVIDENCE.iterdir() if p.is_dir() and p.name != "__pycache__")
    assert areas == sorted(AREAS)
    assert all((S.EVIDENCE / a / "README.md").is_file() for a in WITH_README)
    assert sorted(p.name for p in S.EVIDENCE.iterdir() if p.is_file()) == ["README.md"]
    readme = (S.EVIDENCE / "README.md").read_text(encoding="utf-8")
    assert all(f"`{a}/`" in readme for a in AREAS)


@pytest.mark.tact
def test_small_inputs_match_their_inventory():
    """Малые входы бэктеста маржи — те, что названы описью `inputs/SOURCES.json`: хэши совпадают, лишних файлов нет."""
    for area in INVENTORIED:
        base = S.EVIDENCE / area / "inputs"
        src = json.loads((base / "SOURCES.json").read_text(encoding="utf-8"))
        assert src["area"] == area and src["root"] == "$BANK_HANDOFF_DIR"
        listed = {f["path"]: f for f in src["files"]}
        on_disk = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()} - {"SOURCES.json"}
        assert on_disk == set(listed), (area, sorted(on_disk ^ set(listed)))
        for rel, f in listed.items():
            assert S.sha256_bytes((base / rel).read_bytes()) == f["sha256_input"], (area, rel)
            assert len(f["sha256_full"]) == 64 and 0 < f["rows_kept"] <= f["rows_total"], (area, rel)


@pytest.mark.tact
def test_evidence_carries_no_broker_api_answers():
    """Во входах, выходах, текстах и коде листов нет ответов брокерского API: ни файла ответа, ни имён его полей и
    методов, ни таблицы с колонками-полями ответа."""
    bad = []
    for p in S.EVIDENCE.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = p.relative_to(S.EVIDENCE).as_posix()
        bad += [(rel, w) for w in T_RAW_MARKERS + T_ANSWER_WORDS if w in text]
        if p.suffix == ".csv":
            head = text.splitlines()[0].lstrip("﻿").split(",") if text else []
            bad += [(rel, c) for c in head if T_TABLE_COLUMN.match(c.strip())]
    assert bad == []


@pytest.mark.tact
def test_the_path_sheet_answers_for_the_core_it_meets():
    """Лист вывода на ядре: пока ядро не исполняет ветви книги — код 2 и слова «нужна волна»; на готовом ядре шаги
    моста и уровня маржи печатают ключ книги — суждение, которое лист читает и не меняет."""
    done = S.run_script(PATH_SHEET, "--steps", "bridge,level", "--no-write")
    assert done.returncode in (0, 2), done.stdout + done.stderr
    if done.returncode == 2:
        assert "нужна волна" in done.stdout and "ядр" in done.stdout
        return
    key = re.search(r"nii\.nim_lt_target_mgmt: ([0-9.]+)", done.stdout)
    assert key and float(key.group(1)) == pytest.approx(S.template()["nii"]["nim_lt_target_mgmt"], abs=1e-4), done.stdout


def test_the_marginal_loan_sheet_reproduces_its_record(tmp_path):
    """Лист предельной экономики роста (устав §4; проверка, ключей не пишет) на книге и фактах дерева повторяет свою
    запись `out/marginal_loan_out.{json,txt}`: запись стоит на книге дерева (её версия и дата), а не на прежней."""
    out = tmp_path / "marginal_loan_out.json"
    done = S.run_script(MARGINAL_SHEET, "--out", str(out))
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    got, kept = json.loads(out.read_text(encoding="utf-8")), json.loads(MARGINAL_RECORD.read_text(encoding="utf-8"))
    for record in (got, kept):                     # сверка с файлом передачи — только при $BANK_HANDOFF_DIR: не часть записи
        record["segment"].pop("file_check", None)
    meta = S.template()["meta"]
    assert (kept["book_version"], kept["book_date"]) == (str(meta["version"]), str(meta["date"]))
    assert _close_json(got, kept, tol=1e-6)
    assert _close_text(out.with_suffix(".txt").read_text(encoding="utf-8"),
                       MARGINAL_RECORD.with_suffix(".txt").read_text(encoding="utf-8"))
    assert set(got["marginal"]["all_loans"]) == {"N", "H", "M"}
