"""Сборщик фактов Совкомбанка без папки передачи: якорь — из аргумента, состав — таблицами, функции — общие.

Квартал якоря приходит аргументом `--anchor` (по умолчанию — `data/facts/anchor.json`); даты, нарастающий итог, ряд
кварталов, документ отчёта и формы банка выводятся из него. В теле функций сборщика нет периодов и дат — они живут в
именованных параметрах начала файла; исключение — узлы калибровки книги, собранные на своём якоре (их окна —
свойство круга калибровки). Числа таблиц сборщика (числа якоря вне листов) равны узлам фактов. Файл отчёта квартала,
перепись форм-сканов и командная строка проверяются на закоммиченных фактах.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"

# Периоды и даты в строках кода: 2026Q2, 2Q2026, 6M2026, FY2025, 2026-06-30, 30.06.2026; годы.
PERIOD_RE = re.compile(r"(?<![\w.])(?:20\d\dQ[1-4]|[1-4]Q20\d\d|\d{1,2}M20\d\d|FY20\d\d|20\d\d-\d\d-\d\d|"
                       r"\d\d\.\d\d\.20\d\d)(?![\w])")
YEAR_RE = re.compile(r"(?<![\w.,/-])20[1-4]\d(?![\w,/-])")
# Узлы калибровки книги (стоимость риска по книгам, ряд периметра, ряд «прочего») собраны на своём якоре: окна и
# кварталы в них — свойства круга калибровки, а не якоря; на другом якоре сборщик их переносит.
CALIBRATION_FUNCTIONS = {"build_credit_products", "perimeter_rows", "build_perimeter", "build_misc_window"}


def builder():
    spec = importlib.util.spec_from_file_location("build_facts_under_test", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


B = builder()


def facts() -> dict[str, dict]:
    return {k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in B.BUILT}


# ------------------------------------------------------------------ якорь и выводимое из него

def test_anchor_derivations():
    a = B.Anchor("2026Q2")
    assert (a.date, a.open_date, a.prev_year_end, a.form_date) == ("2026-06-30", "2026-03-31", "2025-12-31", "2026-07-01")
    assert (a.ytd, a.ytd_prev, a.ytd_ru, a.q_ru, a.ru) == ("6M2026", "3M2026", "6М2026", "2К2026", "30.06.2026")
    assert (a.report_doc, a.open_doc, a.days, a.next) == ("2026Q2_ifrs_fs.pdf", "2026Q1_ifrs_fs.pdf", 91, "2026Q3")
    assert a.quarters[0] == B.PNL_FIRST and a.quarters[-1] == "2026Q2" and len(a.quarters) == 14
    q3 = B.Anchor("2026Q3")
    assert (q3.date, q3.ytd, q3.ytd_prev, q3.form_date, q3.report_doc, q3.days) == (
        "2026-09-30", "9M2026", "6M2026", "2026-10-01", "2026Q3_ifrs_fs.pdf", 92)
    q4 = B.Anchor("2026Q4")
    assert (q4.date, q4.ytd, q4.report_doc, q4.prev_year_end, q4.form_date) == (
        "2026-12-31", "FY2026", "FY2026_ifrs_fs.pdf", "2025-12-31", "2027-01-01")
    q1 = B.Anchor("2027Q1")
    assert (q1.open_date, q1.ytd, q1.ytd_prev, q1.prev_year_end, q1.open_doc) == (
        "2026-12-31", "3M2027", None, "2026-12-31", "FY2026_ifrs_fs.pdf")
    assert B.q_prev("2027Q1") == "2026Q4" and B.q_days("2026Q2") == 91 and B.q_days("2026Q1") == 90
    assert B.q_range("2025Q3", "2026Q2") == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert B.q_of_date("2026-06-30") == "2026Q2" and B.q_ru("2026Q2") == "2К2026" and B.qk("2026Q2") == "2026К2"
    for bad in ("2026-Q2", "26Q2", "2026Q5", ""):
        with pytest.raises(B.BuildError, match="якорь"):
            B.Anchor(bad)


def test_default_anchor_is_the_committed_one():
    assert B.default_anchor() == json.loads((FACTS / "anchor.json").read_text(encoding="utf-8"))["period"]


def test_builder_has_no_quarter_literals_outside_named_parameters():
    """В теле функций сборщика нет периодов, дат и лет: всё, что привязано к календарю, — именованный параметр начала
    файла или выводится из якоря (строки документации не в счёт; узлы калибровки книги — исключение)."""
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name in CALIBRATION_FUNCTIONS:
            continue
        doc = ast.get_docstring(fn, clean=False)
        for n in ast.walk(fn):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != doc:
                m = PERIOD_RE.search(n.value) or YEAR_RE.search(n.value)
                if m:
                    bad.append(f"{fn.name}:{n.lineno}: «{m.group(0)}»")
    assert not bad, "периоды и даты в теле функций: " + "; ".join(bad)


# ------------------------------------------------------------------ таблицы состава

def test_table_of_books_is_the_book_of_the_model():
    """13 книг сборщика — книги ЧПД книги модели (nii.books), тем же порядком и с теми же сторонами баланса."""
    book = yaml.safe_load((ROOT / "data" / "assumptions" / "assumptions.yaml").read_text(encoding="utf-8"))["nii"]["books"]
    assert tuple(book) == B.BOOKS
    assert [b for b in B.BOOKS if book[b]["side"] == "asset"] == list(B.ASSET_BOOKS)
    assert set(B.LOANS) | {"securities", "liquidity"} == set(B.ASSET_BOOKS) and B.INSURANCE_BOOK in B.LIAB_BOOKS
    assert set(B.FUNDS_BOOKS) < set(B.LIAB_BOOKS) and set(B.RETAIL_LOANS) < set(B.LOANS)


def test_table_of_interest_lines():
    """Проценты книг — столбцы листа процентов: у каждой книги, кроме книги страховщиков (её «проценты» — финансовые
    расходы страхования), свои строки, ни одна не стоит в двух книгах; проценты вне книг — отдельно."""
    assert set(B.INTEREST_LINES) == set(B.BOOKS) - {B.INSURANCE_BOOK}
    lines = [ln for ls in B.INTEREST_LINES.values() for ln in ls] + list(B.INTEREST_OUTSIDE)
    assert len(lines) == len(set(lines))
    assert all(ln.startswith("ii_") for b in B.ASSET_BOOKS for ln in B.INTEREST_LINES[b])
    assert all(ln.startswith("ie_") for b in B.LIAB_BOOKS if b != B.INSURANCE_BOOK for ln in B.INTEREST_LINES[b])


def test_tables_of_the_pnl_and_other_assets():
    assert set(B.PNL_SUM) <= set(B.PNL_SLOTS) and set(B.PNL_REPORTED_SLOTS) <= set(B.PNL_SLOTS)
    assert set(B.SLOT_SRC_LINES) == set(B.PNL_SLOTS)
    assert set(B.OTHER_ASSETS_FIXED) <= {k for k, _, _ in B.OTHER_ASSETS}
    f = facts()
    assert tuple(f["balance"]["other_assets_fixed_parts"]) == B.OTHER_ASSETS_FIXED
    assert tuple(f["balance"]["other_assets_parts"])[:len(B.OTHER_ASSETS)] == tuple(k for k, _, _ in B.OTHER_ASSETS)
    row = f["pnl_quarterly"]["quarters"][f["anchor"]["period"]]
    assert tuple(row)[:len(B.PNL_SLOTS)] == B.PNL_SLOTS


def test_numbers_of_the_builder_tables_are_the_facts():
    """Числа якоря вне листов (SHEET_GAPS, ALLOWANCE_BOOKS, GUARANTEES) — те же, что в узлах фактов, куда они легли."""
    f = facts()
    a = f["anchor"]["period"]
    g = B.SHEET_GAPS[a]
    bal, cap = f["balance"], f["capital"]
    pairs = {"allowance_ac": bal["allowance_ac"], "lease_gross": bal["lease_gross"],
             "fvtpl_derivatives": bal["securities"]["derivatives"], "fvoci_equity": bal["securities"]["equity_fvoci"],
             "fvtpl_floating_share": bal["securities"]["floating_share_fvtpl"],
             "insurance_reinsurance_assets": bal["insurance"]["reinsurance_assets_in_other"],
             "min_n1_0_with_buffers": cap["n20_0"]["min_with_buffers"]}
    for k, n in pairs.items():
        assert g[k][0] == n["v"], k
        assert n["src"].startswith(os.path.basename(g[k][1])), k
    assert [g["at1_coupon_annual_low"][0], g["at1_coupon_annual_high"][0]] == cap["at1"]["coupon_annual"]["range"]
    assert abs(g["allowance_retail"][0] + g["allowance_corporate"][0] - g["allowance_ac"][0]) < 1e-9
    assert abs(g["fvoci_gov_bonds"][0] + g["fvoci_corp_bonds"][0] + g["fvoci_dfa"][0] - bal["securities"]["fvoci_debt"]["v"]) < 1e-9
    for b, parts in B.ALLOWANCE_BOOKS[a].items():
        assert bal["allowance_books"][b]["v"] == round(sum(parts) / 1000, 3), b
    for k, (val, _) in B.GUARANTEES[a].items():
        assert cap["guarantees"][k]["v"] == round(val / 1000, 3), k
    for k, (val, doc, page) in g.items():
        assert isinstance(val, float) and isinstance(doc, str) and isinstance(page, str), k


def test_small_helpers():
    assert B.ru(6272.1) == "6 272,100" and B.ru(-0.5, 2) == "−0,50" and B.ru(54.21600000000001) == "54,216"
    assert B.d_ru("2026-10-12") == "12.10.2026" and B.dec_ru(0.10985) == "0,10985" and B.money_ru(7856117007.2) == "7 856 117 007,20"
    assert B.int_ru(22446048592) == "22 446 048 592" and B.fmt_mn(-1029221) == "(1 029 221)"
    assert B.null("причина") == {"v": None, "calc": "причина"} and B.node(1.0, "док", "как") == {"v": 1.0, "src": "док", "calc": "как"}
    assert B.est(2.0, "оценка", (1.0, 3.0)) == {"v": 2.0, "calc": "оценка", "estimated": True, "range": [1.0, 3.0]}
    assert B.r2_half_up(7.389 - 4.714) == 2.68
    assert B.body("nii_books", {"a": 1}).endswith("}") and B.body("balance", {"a": 1}).endswith("}\n")


# ------------------------------------------------------------------ файл отчёта квартала

def test_quarter_report_from_the_committed_facts():
    """Файл отчёта квартала: 13 книг с книгой страховщиков; годовой календарь дивиденда (год к выплате); бессрочные в
    капитале; нормативы банка соло без оценки; решение собрания квартала якоря — строкой dividend_decisions."""
    f = facts()
    r = B.report_from_facts(f, source="тест")
    assert r["schema"] == "quarter-report/1" and r["period"] == f["anchor"]["period"] and r["as_of"] == f["anchor"]["as_of"]
    assert tuple(r["balance"]["books"]) == B.BOOKS == tuple(r["interest"])
    b = r["balance"]
    assert b["dividends_payable_year"] == f["balance"]["dividends_payable_year"] and b["at1"] > 0
    assets = sum(b["books"][x] for x in B.ASSET_BOOKS) - b["allowance"] + b["other_assets"]
    claims = sum(b["books"][x] for x in B.LIAB_BOOKS) + b["other_liabilities"] + b["dividends_payable"] + b["bv_common"] + b["at1"] + b["nci"]
    assert abs(assets - claims) < 1e-6 and abs(assets - f["balance"]["total_assets"]["v"]) < 1e-6
    assert b["fvoci"] == f["balance"]["securities"]["fvoci_debt"]["v"] + f["balance"]["securities"]["fvoci_repo"]["v"]
    p = r["pnl"]
    assert abs(sum(p[k] for k in B.PNL_SUM) - p["pbt"]) < 2e-6 and "estimated" not in p
    c = r["capital"]
    assert c["n20_pre_dividend"] is True and c["estimated"] is False and "estimate" not in c
    assert c["n20_0"] == f["capital"]["n1_0_bank"]["v"] and c["n1_1_bank"] == f["capital"]["n1_2_bank"]["v"]
    assert c["basel_cet1"] == c["bank_base_capital"] == f["capital"]["bank_base_capital"]["v"]
    assert r["market"]["key_avg"] == f["nii_books"]["key_avg_anchor_q"]["v"] and set(r["market"]["ofz_curve"]) == {"1", "3", "5", "10"}
    m = f["mgmt_quarterly"]["quarters"][r["period"]]
    assert all(r["mgmt"][x] == m[x + "_exact"]["v"] for x in ("nim", "cor", "cir"))
    assert [d["period"] for d in r["dividend_decisions"]] == [f"{b['dividends_payable_year']}Q4"]
    assert r["dividend_decisions"][0]["decided_date"] <= r["as_of"] < r["dividend_decisions"][0]["record_date"]
    assert abs(sum(r["interest"][x] for x in B.ASSET_BOOKS) - sum(r["interest"][x] for x in B.LIAB_BOOKS) - r["dia"]
               + f["nii_books"]["other_interest_net_q"]["v"] - p["nii"]) < 1e-6


def test_quarter_report_refuses_what_does_not_add_up():
    r = B.report_from_facts(facts(), source="тест")
    for change, why in ((lambda x: x["balance"].__setitem__("other_assets", x["balance"]["other_assets"] + 10), "баланс"),
                        (lambda x: x["pnl"].__setitem__("misc_net", x["pnl"]["misc_net"] + 1), "ОПУ"),
                        (lambda x: x["balance"]["books"].pop("insurance_liab"), "balance.books.insurance_liab"),
                        (lambda x: x.pop("shares"), "shares"),
                        (lambda x: x["balance"].pop("dividends_payable_year"), "годовой календарь"),
                        (lambda x: x["balance"].__setitem__("dividends_payable_declared", [{"period": "2025Q4", "amount": 99.0}]),
                         "объявленные")):
        bad = copy.deepcopy(r)
        change(bad)
        with pytest.raises(B.BuildError, match=why):
            B.check_report(bad)


# ------------------------------------------------------------------ перепись форм-сканов

FORMS = """# перепись для теста
@doc 2026Q3_ifrs_fs.pdf p5 PL c1 2026Q3 3M
ii_eir 100
ii_oth 20
ie -50
dep_ins -2
nii 68
ecl -10
nii_after 58
fee_inc 15
fee_exp -3
nfc 12
fvtpl 1
op_inc 71
nb_rev 30
nb_cost -20
ins_fin -2
nb_net 8
reval 0
staff -20
ga -15
pbt 44
tax -9
np 35
np_sh 34
np_nci 1
oci 2
ci 37
@doc 2026Q3_ifrs_fs.pdf p6 BS c1 2026-09-30 pt
cash 10
loans_own 80
oth_a 10
assets 100
cust 70
liab 70
sh_cap 2
re 27
eq_sh 29
nci 1
equity 30
"""


def test_form_identities_of_a_transcription():
    blocks = B.parse_forms(FORMS, "тест")
    assert [(b["typ"], b["label"]) for b in blocks] == [("PL", "2026Q3"), ("BS", "2026-09-30")]
    ids = {name: (parts, total) for b in blocks for name, parts, total in B.form_identities(b)}
    assert set(ids) == {"nii", "nii_after", "nfc", "op_inc", "nb_net", "pbt", "np", "np_split", "ci", "assets", "liab",
                        "eq_sh", "equity", "balance"}
    assert all(abs(p - t) < 1e-9 for p, t in ids.values())
    broken = B.parse_forms(FORMS.replace("nii 68", "nii 69"), "тест")
    bad = {name for b in broken for name, parts, total in B.form_identities(b) if abs(parts - total) > B.FORMS_TOL}
    assert bad == {"nii", "nii_after"}
    with pytest.raises(B.BuildError, match="второй раз"):
        B.parse_forms(FORMS + "re 27\n", "тест")
    with pytest.raises(B.BuildError, match="заголовок"):
        B.parse_forms("@doc 2026Q3_ifrs_fs.pdf p5 PL\n", "тест")


def test_form_blocks_the_report_of_a_quarter_needs():
    assert B.expected_form_blocks(B.Anchor("2026Q3")) == [
        ("PL", "2026Q3", "3M"), ("PL", "2025Q3", "3M"), ("PL", "2026M9", "9M"), ("PL", "2025M9", "9M"),
        ("BS", "2026-09-30", "pt"), ("BS", "2025-12-31", "pt")]
    assert B.expected_form_blocks(B.Anchor("2026Q4"))[:2] == [("PL", "2026FY", "12M"), ("PL", "2025FY", "12M")]
    assert B.expected_form_blocks(B.Anchor("2027Q1")) == [("PL", "2027Q1", "3M"), ("PL", "2026Q1", "3M"),
                                                          ("BS", "2027-03-31", "pt"), ("BS", "2026-12-31", "pt")]


def test_cli_forms_checks_two_transcriptions(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text(FORMS, encoding="utf-8")
    b.write_text(FORMS, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"} | {"PYTHONIOENCODING": "utf-8"}
    run = lambda *x: subprocess.run([sys.executable, "-B", str(BUILDER), *x], cwd=ROOT, env=env, capture_output=True,   # noqa: E731
                                    text=True, encoding="utf-8")
    res = run("--forms", str(a), str(b))
    assert res.returncode == 0 and "перепись сходится" in res.stdout, res.stdout[-800:]
    b.write_text(FORMS.replace("fee_inc 15", "fee_inc 16").replace("nfc 12", "nfc 13"), encoding="utf-8")
    res = run("--forms", str(a), str(b))
    assert res.returncode == 1 and "fee_inc — 15.0 против 16.0" in res.stdout
    res = run("--forms", str(a), "--anchor", "2026Q3")
    assert res.returncode == 1 and "НЕТ блока" in res.stdout and "2026M9" in res.stdout


# ------------------------------------------------------------------ командная строка

def test_cli_report_from_ready_facts(tmp_path):
    """`--report ФАЙЛ --facts КАТАЛОГ` пишет отчёт квартала без папки передачи; чужой якорь — отказ."""
    out = tmp_path / "report.json"
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"} | {"PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, "-B", str(BUILDER), *a], cwd=ROOT, env=env, capture_output=True,   # noqa: E731
                                    text=True, encoding="utf-8")
    res = run("--report", str(out), "--facts", str(FACTS))
    assert res.returncode == 0, res.stderr[-1500:]
    got = json.loads(out.read_text(encoding="utf-8"))
    assert got == B.report_from_facts(facts(), source=got["source"]) and b"\r\n" not in out.read_bytes()
    res = run("--report", str(out), "--facts", str(FACTS), "--anchor", "2019Q1")
    assert res.returncode == 1 and "ПРОВАЛ" in res.stderr


def test_cli_without_handoff_dir_refuses(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"}
    for args in (("--out", str(tmp_path)), ("--plan", "--anchor", "2026Q3")):
        res = subprocess.run([sys.executable, "-B", str(BUILDER), *args], cwd=ROOT, env=env,
                             capture_output=True, text=True, encoding="utf-8")
        assert res.returncode == 1 and "BANK_HANDOFF_DIR" in res.stderr and not list(tmp_path.iterdir())


def test_cli_help_names_the_arguments():
    res = subprocess.run([sys.executable, "-B", str(BUILDER), "--help"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0
    for arg in ("--anchor", "--out", "--check", "--report", "--facts", "--plan", "--forms", "--expected"):
        assert arg in res.stdout, arg
