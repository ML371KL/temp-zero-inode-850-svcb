"""Факты Совкомбанка против папки передачи (маркер archive; в CI пропускается).

Сборщик воспроизводит data/facts байт в байт и печатает сверки без сбоев; sha256 каждого документа реестров
совпадает с файлом в папке передачи; файл отчёта квартала из сборки равен файлу из закоммиченных фактов; перечень
следующего квартала называет недостающие строки листов, а на якоре — пуст; перепись форм-сканов соседа сходится всеми
тождествами; узлы фактов равны строкам листов этапа 1.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"
BUILT = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends", "bridge_mgmt_ifrs",
         "bridge_ras_ifrs", "mgmt_quarterly", "guidance", "calendar", "peers", "credit_products", "perimeter", "misc_window")
# Сверки, которые сборщик обязан напечатать: слова из названия сверки.
CHECKS = ("баланс якоря: Σ книг активов − резерв + прочие активы = активы",
          "проценты книг − страхование вкладов + проценты вне книг = ЧПД движка",
          "ОПУ 2026Q2: pbt = Σ строк движка", "капитал: строки капитала = капитал без бессрочных",
          "акции: делитель дивиденда", "сумма решения = DPS × акции в расчёте", "мосты упр. ↔ движок",
          "ряд периметра = листу круга", "резерв по кредитным книгам", "nii_books: остатки книг на якоре = balance.books")

pytestmark = pytest.mark.archive


def handoff() -> Path:
    root = os.environ.get("BANK_HANDOFF_DIR")
    if not root or not Path(root).is_dir():
        pytest.skip("нет папки передачи (BANK_HANDOFF_DIR)")
    return Path(root)


def run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, BANK_HANDOFF_DIR=str(handoff()), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-B", str(BUILDER), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                          encoding="utf-8")


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def sheet(name: str) -> list[dict]:
    with open(handoff() / "stage1" / "facts" / "sheets" / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_builder_reproduces_facts_and_prints_the_checks(tmp_path):
    res = run("--out", str(tmp_path))
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    assert "СБОЙ" not in res.stdout and "пометка" not in res.stdout
    missing = [c for c in CHECKS if c not in res.stdout]
    assert not missing, f"сборщик не напечатал сверки: {missing}"
    diff = [n for n in BUILT if (tmp_path / f"{n}.json").read_bytes() != (FACTS / f"{n}.json").read_bytes()]
    assert not diff, f"пересборка расходится с data/facts: {diff}"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f"{n}.json" for n in BUILT)


def test_builder_check_mode(tmp_path):
    res = run("--check")
    assert res.returncode == 0 and "байт в байт" in res.stdout, res.stderr[-1500:]
    res = run("--check", "--out", str(tmp_path))          # пустой каталог: расхождение, файлы не пишутся
    assert res.returncode == 1 and "РАСХОЖДЕНИЕ" in res.stderr and not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", ("anchor", "calendar"))
def test_registry_sha256_matches_files(name):
    root = handoff()
    data = load(name)
    docs = data["documents"] if name == "anchor" else data["sources"]
    bad, checked = [], 0
    for d in docs:
        f = d.get("file")
        if not f:
            continue
        path = root / f
        if not path.is_file():
            bad.append(f"{d['key']}: нет файла {f}")
            continue
        checked += 1
        if hashlib.sha256(path.read_bytes()).hexdigest() != d["sha256"]:
            bad.append(f"{d['key']}: sha256 не совпал")
    assert not bad, "\n".join(bad)
    assert checked >= 0.9 * len(docs), f"{name}: у большинства документов нет файла в папке передачи"


def test_anchor_argument_reproduces_and_refuses_a_quarter_without_sheets(tmp_path):
    anchor = load("anchor")["period"]
    res = run("--anchor", anchor, "--out", str(tmp_path / "same"))
    assert res.returncode == 0, res.stderr[-1500:]
    assert (tmp_path / "same" / "balance.json").read_bytes() == (FACTS / "balance.json").read_bytes()
    res = run("--anchor", "2031Q4", "--out", str(tmp_path / "far"))
    assert res.returncode == 1 and "нет строки листа" in res.stderr and not (tmp_path / "far").exists()
    res = run("--anchor", "26Q2", "--out", str(tmp_path / "bad"))
    assert res.returncode == 1 and "якорь" in res.stderr


def test_report_from_the_build_equals_report_from_the_facts(tmp_path):
    a, b = tmp_path / "from-build.json", tmp_path / "from-facts.json"
    assert run("--out", str(tmp_path / "facts"), "--report", str(a)).returncode == 0
    assert run("--report", str(b), "--facts", str(FACTS)).returncode == 0
    ra, rb = json.loads(a.read_text(encoding="utf-8")), json.loads(b.read_text(encoding="utf-8"))
    ra.pop("source"), rb.pop("source")
    assert ra == rb


def test_plan_of_the_next_quarter_names_the_missing_rows():
    """Перечень квартала: на якоре фактов листы полны; на следующем квартале — недостающие строки листов (книги на
    конец квартала, ОПУ квартала, формы банка на первое число, проценты книг, числа вне листов) и шаги дня отчёта."""
    res = run("--plan", "--anchor", load("anchor")["period"])
    assert res.returncode == 0 and "листы полны" in res.stdout, res.stdout[-1500:]
    nxt = load("anchor")["first_period"]
    res = run("--plan", "--anchor", nxt)
    assert res.returncode == 1 and "листы не полны" in res.stdout
    out = res.stdout
    for want in ("books_balances.csv: auto TOTAL на", "pnl_composition.csv: nii за " + nxt, "capital_bank.csv: формы",
                 "interest_lines_quarterly.csv", "balance_history.csv: строка", "documents.csv:", "SHEET_GAPS",
                 "ALLOWANCE_BOOKS", "GUARANTEES", "mgmt_kpi.csv: nim или nim_exact за " + nxt, "--forms",
                 "перенесён из"):
        assert want in out, want


def test_neighbour_transcriptions_add_up():
    """Перепись форм-сканов соседа svcb-history (manual/*.txt) сходится всеми тождествами; перепись квартала якоря —
    полна (блоки ОПУ и ОФП отчёта якоря)."""
    manual = handoff() / "research" / "code" / "svcb-history" / "manual"
    files = sorted(manual.glob("m*.txt"))
    assert len(files) >= 20
    res = run("--forms", *map(str, files[:2]))
    assert res.returncode == 1 and "только в" in res.stdout, "две разные переписи — блоки только в одной"
    for f in files:
        res = run("--forms", str(f))
        assert res.returncode == 0, f.name + res.stdout[-800:]
    a = load("anchor")["period"]
    res = run("--forms", str(manual / f"m{a}.txt"), "--anchor", a)
    assert res.returncode == 0 and "недостаёт 0" in res.stdout, res.stdout[-1500:]


def test_facts_equal_the_rows_of_the_stage_sheets():
    """Сверка с листами этапа 1: книги якоря — итоги листа книг; строки ОПУ — лист состава слотов; нормативы — лист
    форм банка; решения о дивидендах — лист решений; акции — лист акций."""
    a = load("anchor")
    bal = load("balance")
    tot = {r["book"]: float(r["value_mn"]) / 1000 for r in sheet("books_balances.csv")
           if r["date"] == a["as_of"] and r["line"] == "TOTAL"}
    for b, n in bal["books"].items():
        assert abs(n["v"] - tot[b]) < 1e-9, b
    comp = {(r["period"], r["slot"]): float(r["value_mn"]) / 1000 for r in sheet("pnl_composition.csv")}
    for p, row in load("pnl_quarterly")["quarters"].items():
        for slot in ("nii", "fees_net", "llp_debt_fa", "insurance_net", "misc_net", "noncore_net", "opex", "pbt", "ni_shareholders"):
            assert abs(row[slot]["v"] - comp[(p, slot)]) < 1e-6, f"{p}.{slot}"
    cap = load("capital")
    form = {r["form_date"]: r for r in sheet("capital_bank.csv")}[cap["n20_0"]["as_of"]]
    assert cap["n20_0"]["value"]["v"] == float(form["n1_0"]) and cap["n1_1_bank"]["value"]["v"] == float(form["n1_2"])
    assert cap["bank_base_capital"]["v"] == float(form["base_bn"]) and cap["t2_recognized"]["v"] == float(form["t2_bn"])
    div = {int(r["fiscal_year"]): r for r in sheet("dividends.csv")}
    for h in load("dividends")["history"]:
        r = div[h["year"]]
        assert h["dps"]["v"] == float(r["dps"]) and h["record_date"] == r["record_date"], h["year"]
        assert abs(h["pool_declared"]["v"] - float(r["pool_declared_rub"]) / 1e9) < 1e-6, h["year"]
    shares = {(r["metric"], r["date"]): int(r["value"]) for r in sheet("shares.csv") if r["value"].isdigit()}
    sh = load("shares")
    assert sh["issued_total"]["v"] * 1e6 == pytest.approx(shares[("issued_total", a["as_of"])], abs=1)
    assert sh["outstanding_total"]["v"] * 1e6 == pytest.approx(shares[("outstanding_total", a["as_of"])], abs=1)
