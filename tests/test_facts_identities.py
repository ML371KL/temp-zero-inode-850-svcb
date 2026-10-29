"""Факты Совкомбанка: тождества (data/facts/SCHEMA.md, раздел «Тождества»).

Баланс по 13 книгам; части прочих активов и обязательств; узлы, на которые раскладываются книги; капитал по строкам;
дивиденды к выплате — годовой календарь; концы кварталов истории — остатки книг; ставки книг и ЧПД квартала; строки
ОПУ в слотах ядра; нормативы банка соло и вычеты формы ядра; акции и делитель дивиденда; мосты упр. ↔ движок —
средние окна и значения движка из фактов; мост РСБУ; стоимость риска по книгам, ряд периметра и ряд «прочего».
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
LOANS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans")
ASSET_BOOKS = LOANS + ("securities", "liquidity")
LIAB_BOOKS = ("retail_current", "retail_term", "corp_term", "corp_current", "wholesale", "insurance_liab")
FUNDS = ("retail_current", "retail_term", "corp_term", "corp_current")
BOOKS = ASSET_BOOKS + LIAB_BOOKS
PNL_SUM = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net")
EPS = 1e-6


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def v(x):
    return x["v"] if isinstance(x, dict) else x


def anchor() -> str:
    return load("anchor")["period"]


def q_prev(p: str) -> str:
    y, k = int(p[:4]), int(p[-1])
    return f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"


# ------------------------------------------------------------------ баланс

def test_balance_identity_by_books():
    b = load("balance")
    sa = sum(v(b["books"][k]) for k in ASSET_BOOKS)
    sl = sum(v(b["books"][k]) for k in LIAB_BOOKS)
    ta = v(b["total_assets"])
    assert abs(sa - v(b["allowance_ac"]) + v(b["other_assets"]) - ta) < EPS
    assert abs(sl + v(b["other_liabilities"]) + v(b["dividends_payable"]) + v(b["equity"]["total"]) - ta) < EPS
    assert abs(v(b["total_liabilities"]) - (sl + v(b["other_liabilities"]) + v(b["dividends_payable"]))) < EPS
    assert abs(v(b["iea"]) - sa) < EPS and v(b["allowance_ac"]) > 0, "резерв — величиной"


def test_other_assets_and_liabilities_are_their_parts():
    b = load("balance")
    assert abs(v(b["other_assets"]) - sum(v(x) for x in b["other_assets_parts"].values())) < EPS
    assert abs(v(b["other_liabilities"]) - sum(v(x) for x in b["other_liabilities_parts"].values())) < EPS
    fixed = b["other_assets_fixed_parts"]
    assert set(fixed) == {"associates", "goodwill", "deferred_tax"}, "постоянные прочие активы (решения ведущего № 2, А1)"
    assert abs(v(b["other_assets_fixed"]) - sum(v(x) for x in fixed.values())) < EPS
    assert all(v(fixed[k]) == v(b["other_assets_parts"][k]) for k in fixed)
    assert 0 < v(b["other_assets_fixed"]) < v(b["other_assets"])
    nw = b["nonworking_money"]
    assert abs(v(nw["total"]) - sum(v(x) for k, x in nw.items() if k != "total")) < EPS
    assert v(b["other_assets_parts"]["nonworking_money"]) == v(nw["total"]), "неработающие деньги — в растущей части"


def test_books_equal_their_reference_nodes():
    """Книга = сумма узлов, на которые она раскладывается: бумаги, ликвидность (процентная часть), опт, четыре книги
    средств клиентов (вместе — строка ОФП), обязательства страховщиков."""
    b = load("balance")
    bk = {k: v(b["books"][k]) for k in BOOKS}
    s = b["securities"]
    assert abs(bk["securities"] - sum(v(s[k]) for k in ("fvoci_debt", "fvoci_repo", "ac", "ac_repo", "fvtpl_bonds"))) < EPS
    assert abs(bk["liquidity"] - sum(v(b["liquidity"][k]) for k in ("cash", "cbr", "due_from_banks"))) < EPS
    assert abs(bk["wholesale"] - sum(v(x) for x in b["wholesale"].values())) < EPS
    for k in FUNDS:
        assert v(b["funds"][k]) == bk[k], k
    assert abs(v(b["funds"]["total"]) - sum(bk[k] for k in FUNDS)) < EPS, "средства клиентов ОФП = четыре книги"
    assert v(b["insurance"]["contract_liabilities"]) == bk["insurance_liab"]
    assert v(b["loans_fvtpl"]) < bk["corp_loans"] and v(b["loans_sme_other"]) < bk["corp_loans"], "внутри корпоративной книги"
    assert abs(v(s["equity_other"]) - v(s["equity_fvtpl"]) - v(s["equity_fvoci"])) < EPS
    assert abs(v(b["other_assets_parts"]["equity_and_derivatives_fvtpl"]) - v(s["equity_fvtpl"]) - v(s["derivatives"])) < EPS


def test_equity_components():
    e = load("balance")["equity"]
    parts = ("share_capital", "other_contributions", "reval_buildings", "fvoci_reserve", "retained_earnings")
    assert abs(sum(v(e[k]) for k in parts) - v(e["bv_common"])) < EPS, "капитал без бессрочных = строки"
    assert abs(v(e["bv_common"]) + v(e["at1"]) + v(e["nci"]) - v(e["total"])) < EPS
    assert v(e["fvoci_reserve"]) == v(load("capital")["fvoci_reserve"])


def test_dividends_payable_is_the_annual_decision():
    """Годовой календарь (форма Сбера): дивиденды к выплате — строка примечания; на якоре — решение за год, принятое не
    позже якоря и выплаченное после; список по периодам — тот же дивиденд периодом четвёртого квартала."""
    b, d = load("balance"), load("dividends")
    a = load("anchor")["as_of"]
    unpaid = [h for h in d["history"] if h["decided_date"] <= a < h["pay_date"]]
    assert len(unpaid) == 1 and b["dividends_payable_year"] == unpaid[0]["year"]
    assert abs(v(b["dividends_payable"]) - unpaid[0]["pool_declared"]["v"]) < 1e-3
    declared = b["dividends_payable_declared"]
    assert [x["period"] for x in declared] == [unpaid[0]["period"]] == [f"{unpaid[0]['year']}Q4"]
    assert sum(v(x["amount"]) for x in declared) <= v(b["dividends_payable"]) + 1e-9


def test_prev_year_end_loans_by_segment():
    b = load("balance")
    pye = b["prev_year_end"]
    per = f"{pye['as_of'][:4]}Q4"
    books = b["history"][per]["books"]
    assert abs(v(pye["loans_corporate"]) - v(books["corp_loans"])) < 1e-9
    assert abs(v(pye["loans_retail"]) - sum(v(books[k]) for k in LOANS[:4])) < 1e-6
    assert abs(v(pye["loans_corporate"]) + v(pye["loans_retail"]) - v(b["history"][per]["loans"])) < 1e-6


def test_balance_history_books_give_the_history_rows():
    """Остатки книг на концах кварталов (М13): кредитные книги — loans, книги активов — iea; средства клиентов — не
    больше строки «средства клиентов» (без репо с клиентами)."""
    h = load("balance")["history"]
    for per, row in h.items():
        if "books" not in row:
            continue
        bk = {k: v(x) for k, x in row["books"].items()}
        if set(bk) == set(BOOKS):
            assert abs(sum(bk[k] for k in LOANS) - v(row["loans"])) < 2e-3, per
            assert abs(sum(bk[k] for k in ASSET_BOOKS) - v(row["iea"])) < 2e-3, per
            assert abs(bk["insurance_liab"] - v(row["insurance_liab"])) < 2e-3, per
        s = sum(bk[k] for k in FUNDS)
        assert s <= v(row["funds"]) + 2e-3 and v(row["funds"]) - s < 1.0, per
    a = h[anchor()]
    b = load("balance")
    assert v(a["bv_common"]) == v(b["equity"]["bv_common"]) and abs(v(a["iea"]) - v(b["iea"])) < EPS


# ------------------------------------------------------------------ ЧПД книг

def test_nii_books_close_equals_balance_and_open_equals_history():
    nb, b = load("nii_books"), load("balance")
    prev = b["history"][q_prev(anchor())]["books"]
    for k in BOOKS:
        row = nb["books"][k]
        assert row["balance_close"]["v"] == v(b["books"][k]), k
        assert row["balance_open"]["v"] == v(prev[k]), k
        assert abs(row["balance_avg"]["v"] - (row["balance_open"]["v"] + row["balance_close"]["v"]) / 2) < 1e-4, k


def test_nii_books_rates_and_total():
    """Ставка книги = проценты / средний остаток × 365/дни; проценты книг − страхование вкладов + вне книг = ЧПД
    движка квартала (с книгой обязательств страховщиков); ЧПД движка = ЧПД формы − финансовые расходы страхования."""
    nb = load("nii_books")
    days = nb["days"]["v"]
    for k, row in nb["books"].items():
        rate = row["interest_q"]["v"] / ((row["balance_open"]["v"] + row["balance_close"]["v"]) / 2) * 365 / days
        assert abs(rate - row["rate_anchor"]["v"]) < 1e-6, k
        assert row["interest_q"]["v"] > 0, f"{k}: проценты — величиной"
    ia = sum(nb["books"][k]["interest_q"]["v"] for k in ASSET_BOOKS)
    il = sum(nb["books"][k]["interest_q"]["v"] for k in LIAB_BOOKS)
    assert abs(ia - nb["interest_assets_q"]["v"]) < 1e-9 and abs(il - nb["interest_liabilities_q"]["v"]) < 1e-9
    assert abs(ia - il - nb["dia_q"]["v"] + nb["other_interest_net_q"]["v"] - nb["nii_q"]["v"]) < 1e-6
    row = load("pnl_quarterly")["quarters"][anchor()]
    assert nb["nii_q"]["v"] == row["nii"]["v"] and nb["nii_form_q"]["v"] == row["nii_form"]["v"]
    assert abs(nb["books"]["insurance_liab"]["interest_q"]["v"] + row["ins_finance_expense"]["v"]) < EPS
    iea = sum((nb["books"][k]["balance_open"]["v"] + nb["books"][k]["balance_close"]["v"]) / 2 for k in ASSET_BOOKS)
    assert abs(iea - nb["iea_avg"]["v"]) < 1e-3
    assert abs(nb["nii_q"]["v"] * 365 / days / iea - nb["nim_eng_q"]["v"]) < 1e-6
    cur = nb["books"]["retail_current"]["balance_close"]["v"]
    assert abs(cur / (cur + nb["books"]["retail_term"]["balance_close"]["v"]) - nb["current_share_anchor"]["v"]) < 1e-6
    assert nb["rates_carry_residual"] is False, "якорь книги — до первого перезаякоривания"


def test_key_average_of_the_anchor_quarter():
    """Ключевая квартала якоря: ряд исследования (три знака процента) и лист рынка (шесть знаков доли) — одна ставка."""
    nb, q = load("nii_books"), load("pnl_quarterly")["quarters"][anchor()]
    assert abs(nb["key_avg_anchor_q"]["v"] - q["key_avg"]["v"]) < 1e-5


# ------------------------------------------------------------------ ОПУ

def test_pnl_identities():
    p = load("pnl_quarterly")
    for per, r in p["quarters"].items():
        assert abs(sum(r[k]["v"] for k in PNL_SUM) - r["pbt"]["v"]) < EPS, per
        assert abs(r["pbt"]["v"] + r["tax"]["v"] - r["ni"]["v"]) < EPS, per
        assert abs(r["ni"]["v"] - r["ni_nci"]["v"] - r["ni_shareholders"]["v"]) < EPS, per
        assert abs(r["noncore_net"]["v"] - sum(x["v"] for x in r["noncore_parts"].values())) < EPS, per
        assert abs(r["nii"]["v"] - r["nii_form"]["v"] - r["ins_finance_expense"]["v"]) < EPS, per
        assert abs(r["insurance_net"]["v"] - r["insurance_net_form"]["v"] + r["ins_finance_expense"]["v"]) < EPS, per
        assert abs(r["fee_income"]["v"] + r["fee_expense"]["v"] + r["guarantee_provisions"]["v"] - r["fees_net"]["v"]) < 1e-5, per
        assert abs(r["ci_shareholders"]["v"] - r["ci_total"]["v"] + r["ni_nci"]["v"]) < EPS, per
        assert r["opex"]["v"] < 0 and r["llp_debt_fa"]["v"] < 0 and r["dia"]["v"] > 0, per


def test_years_are_the_sum_of_quarters():
    p = load("pnl_quarterly")
    for y, rec in p["years"].items():
        quarters = [k for k in p["quarters"] if k.startswith(y[:4])]
        if not y.isdigit():
            quarters = quarters[:{"Q1": 1, "H1": 2, "9M": 3}[y[4:]]]
        else:
            assert len(quarters) == 4, y
        for f in ("pbt", "tax", "ni", "ni_shareholders", "ni_nci"):
            assert abs(sum(p["quarters"][q][f]["v"] for q in quarters) - rec[f]["v"]) < 1e-5, f"{y}.{f}"


def test_reported_profit_of_the_dividend_years_is_the_ifrs_statement():
    p, d = load("pnl_quarterly"), load("dividends")
    for h in d["history"]:
        y = str(h["year"])
        if y in p["years"]:
            assert abs(h["ni_shareholders"]["v"] - p["years"][y]["ni_shareholders"]["v"]) < 1e-3, y
            assert abs(h["ni_total"]["v"] - p["years"][y]["ni"]["v"]) < 1e-3, y
    for y, rec in d["years"].items():
        key = y if rec["complete"] else next(k for k in p["years"] if k.startswith(y) and not k.isdigit())
        assert abs(rec["ni_shareholders"]["v"] - p["years"][key]["ni_shareholders"]["v"]) < EPS, y


def test_at1_coupons_by_quarter():
    """Купон бессрочных — мимо прибыли, через капитал: кварталы года якоря дают купон за период в capital.at1."""
    p, cap = load("pnl_quarterly")["quarters"], load("capital")["at1"]
    a = anchor()
    y, k = a[:4], int(a[-1])
    tag = {1: "3m", 2: "6m", 3: "9m", 4: "fy"}[k]
    assert abs(sum(p[f"{y}Q{i}"]["at1_coupon"]["v"] for i in range(1, k + 1)) - cap[f"coupon_{tag}{y}"]["v"]) < EPS
    for i in range(1, k + 1):
        assert p[f"{y}Q{i}"]["at1_coupon"]["v"] == cap[f"coupon_q{i}_{y}"]["v"]
    lo, hi = cap["coupon_annual"]["range"]
    assert lo <= cap["coupon_annual"]["v"] <= hi and cap["coupon_quarter"]["v"] in (1, 2, 3, 4)
    assert cap["amount"]["v"] == load("balance")["equity"]["at1"]["v"]


# ------------------------------------------------------------------ капитал

def test_capital_slots_of_the_bank_solo():
    """Слоты ядра — банк соло (формы 0409135 и 0409123 на первое число после квартала): n20_0 ← Н1.0, n1_1_bank ←
    Н1.2; уровни капитала банка складываются; RWA — капитал / норматив; Базель группы — справочно."""
    cap = load("capital")
    fd = cap["n20_0"]["as_of"]
    assert fd == cap["n1_1_bank"]["as_of"] == cap["bank_base_capital"]["as_of"] > load("anchor")["as_of"]
    assert cap["n20_0"]["value"]["v"] == cap["n1_0_bank"]["v"] == cap["basel"]["total_ratio"]["v"]
    assert cap["n1_1_bank"]["value"]["v"] == cap["n1_2_bank"]["v"] == cap["n20_2"]["v"]
    assert cap["n1_1_bank_h11"]["v"] == cap["basel"]["cet1_ratio"]["v"]
    assert cap["n1_1_bank_h11"]["v"] < cap["n1_2_bank"]["v"] < cap["n1_0_bank"]["v"]
    assert abs(cap["bank_base_capital"]["v"] + cap["bank_additional_capital"]["v"] - cap["bank_main_capital"]["v"]) < EPS
    assert cap["basel"]["cet1"]["v"] == cap["bank_base_capital"]["v"]
    assert abs(cap["bank_own_funds"]["v"] / cap["n1_0_bank"]["v"] - cap["basel"]["rwa"]["v"]) < 0.5
    last = cap["history"][-1]
    assert last["period"] == anchor() and last["n1_0"]["v"] == cap["n1_0_bank"]["v"]
    assert [m["date"] for m in cap["history_monthly"]] == sorted(m["date"] for m in cap["history_monthly"])
    assert cap["n20_0"]["min_with_buffers"]["v"] < cap["n20_0"]["value"]["v"]


def test_core_form_check_reproduces_the_bank_capital():
    """Справка потоку капитала: k20 = bv + dp − (1 − f)·R − ded20 + at1 + t2 при вычетах core_form_check даёт
    собственные средства банка; ключ deductions_anchor: anchor — bv − basel.cet1."""
    cap, b = load("capital"), load("balance")
    bv, dp, R = b["equity"]["bv_common"]["v"], b["dividends_payable"]["v"], b["equity"]["fvoci_reserve"]["v"]
    at1, t2, k20 = cap["at1"]["amount"]["v"], cap["t2_recognized"]["v"], cap["bank_own_funds"]["v"]
    cf = cap["core_form_check"]
    assert abs(bv + dp - R - cf["ded20_implied_f0"]["v"] + at1 + t2 - k20) < 1e-5
    assert abs(bv + dp - cf["ded20_implied_f1"]["v"] + at1 + t2 - k20) < 1e-5
    assert abs(bv - cap["basel"]["cet1"]["v"] - cf["ded20_anchor_formula"]["v"]) < 1e-5


def test_curve_and_reference_blocks():
    cap = load("capital")
    curve = cap["ofz_curve_anchor"]
    assert curve["as_of"] == load("anchor")["as_of"]
    xs = [curve[t]["v"] for t in ("1", "2", "3", "5", "10")]
    assert all(0.03 < x < 0.3 for x in xs)
    g = cap["basel_ifrs"]
    assert g["as_of"] <= load("anchor")["as_of"] and g["cet1"]["v"] is None
    assert abs(g["tier1"]["v"] + g["tier2"]["v"] - g["total_capital"]["v"]) < 1e-2
    assert abs(g["total_capital"]["v"] / g["rwa"]["v"] - g["total_ratio"]["v"]) < 1e-3
    assert cap["instruments"] and all(i["isin"] or i["instrument"] for i in cap["instruments"])


# ------------------------------------------------------------------ акции

def test_shares_arithmetic_and_the_dividend_divisor():
    """Выпущенные − в обращении = собственные (банк + страховая дочка); делитель дивиденда — выпущенные − собственные
    акции банка; сумма последнего решения = DPS × делитель."""
    sh, d = load("shares"), load("dividends")
    issued, out = sh["issued_total"]["v"], sh["outstanding_total"]["v"]
    assert sh["issued_ordinary"]["v"] == issued and sh["outstanding_ordinary"]["v"] == out
    assert abs(issued - out - sh["treasury_ordinary"]["v"]) < 1e-6
    assert abs(sh["treasury_ordinary"]["v"] - sh["treasury_bank_own"]["v"] - sh["treasury_subsidiary"]["v"]) < 1e-6
    assert abs(issued - sh["treasury_bank_own"]["v"] - sh["dividend_eligible"]["v"]) < 1e-6
    last = max(d["history"], key=lambda h: h["decided_date"])
    assert abs(last["dps"]["v"] * sh["dividend_eligible"]["v"] / 1000 - last["pool_declared"]["v"]) < 1e-5
    assert sh["economic_treasury"]["v"] == 0 and sh["par_value"]["v"] == 0.1


def test_corporate_actions_carry_the_share_counts():
    acts = load("shares")["corporate_actions"]
    assert [a["date"] for a in acts] == sorted(a["date"] for a in acts)
    issued = load("shares")["issued_total"]["v"]
    with_counts = [a for a in acts if "shares_after" in a]
    assert with_counts and with_counts[-1]["shares_after"]["v"] == issued, "последнее событие с числом акций — нынешний выпуск"
    for a in with_counts:
        if a["kind"] in ("issue", "cancellation"):
            assert a["shares_before"]["v"] != a["shares_after"]["v"], a["date"]


# ------------------------------------------------------------------ мосты

def test_bridge_values_are_window_means():
    """Значение моста — среднее разрыва по окну (ЧПМ — отношение engine_x4 / упр.; CoR и C/I — разность), n — число
    кварталов окна, sd — выборочное отклонение по окну."""
    b = load("bridge_mgmt_ifrs")
    for x in ("nim", "cor", "cir"):
        blk = b[x]
        lo, hi = blk["window"]
        gaps = [h["gap_x4" if x == "nim" else "gap"]["v"] for h in blk["history"] if lo <= h["period"] <= hi]
        assert len(gaps) == blk["n"]["v"], x
        assert abs(statistics.fmean(gaps) - blk["value"]["v"]) < 5e-6, x
        assert abs(statistics.stdev(gaps) - blk["sd"]["v"]) < 5e-6, x
        for h in blk["history"]:
            if h["mgmt"]["v"] is None:
                continue
            if x == "nim":
                assert abs(h["engine_x4"]["v"] / h["mgmt"]["v"] - h["gap_x4"]["v"]) < 2e-5, h["period"]   # узлы — 6 знаков
            else:
                assert abs(h["engine"]["v"] - h["mgmt"]["v"] - h["gap"]["v"]) < 5e-6, h["period"]


def test_bridge_engine_of_the_anchor_quarter_is_read_from_the_facts():
    """Значения движка квартала якоря — из тех же фактов: ЧПМ — ЧПД движка на средние процентные активы, CoR — резервы
    на средние кредитные книги, C/I — расходы на доход строк движка."""
    b, nb, bal = load("bridge_mgmt_ifrs"), load("nii_books"), load("balance")
    a = anchor()
    row = load("pnl_quarterly")["quarters"][a]
    days = nb["days"]["v"]
    eng = {x: next(h for h in b[x]["history"] if h["period"] == a) for x in ("nim", "cor", "cir")}
    assert abs(eng["nim"]["engine"]["v"] - nb["nim_eng_q"]["v"]) < 1e-6
    prev = bal["history"][q_prev(a)]["books"]
    loans_avg = (sum(v(prev[k]) for k in LOANS) + sum(v(bal["books"][k]) for k in LOANS)) / 2
    assert abs(eng["cor"]["engine"]["v"] - (-row["llp_debt_fa"]["v"] * 365 / days / loans_avg)) < 1e-6
    income = sum(row[k]["v"] for k in ("nii", "fees_net", "insurance_net", "misc_net"))
    assert abs(eng["cir"]["engine"]["v"] - (-row["opex"]["v"] / income)) < 1e-6
    m = load("mgmt_quarterly")["quarters"][a]
    for x in ("nim", "cor", "cir"):
        assert eng[x]["mgmt"]["v"] == m[x + "_exact"]["v"], x


def test_bridge_ras_nii():
    r, p = load("bridge_ras_ifrs"), load("pnl_quarterly")["quarters"]
    for q in r["nii"]["quarters"]:
        assert q["ifrs"]["v"] == p[q["period"]]["nii"]["v"]
        assert abs(q["ifrs"]["v"] / q["ras"]["v"] - q["ratio"]["v"]) < 1e-6
    ratios = [q["ratio"]["v"] for q in r["nii"]["quarters"]]
    assert abs(statistics.stdev(ratios[-6:]) - r["nii"]["sd"]["v"]) < 1e-6
    for q in r["quarters"]:
        assert q["ifrs_ni_sh"]["v"] == p[q["period"]]["ni_shareholders"]["v"]


# ------------------------------------------------------------------ гайденс, календарь, аналоги

def test_guidance_is_a_stub_with_reasons():
    g = load("guidance")
    assert g["year"] == int(anchor()[:4])
    assert all(n["v"] is None and len(n["calc"]) > 40 for n in g["items"].values())
    assert g["history"] and all(h["value"] is None and h["src"] for h in g["history"])


def test_calendar_events():
    c = load("calendar")
    ids = [e["id"] for e in c["events"]]
    assert len(ids) == len(set(ids))
    a = load("anchor")
    nxt = [e for e in c["events"] if e["kind"] == "ifrs" and e["covers"] == a["first_period"]]
    assert nxt and all(e["date"] > c["as_of"] for e in nxt), "событие отчёта МСФО следующего квартала"
    for e in c["events"]:
        if e.get("estimated"):
            assert e["earliest"] <= e["date"] <= e["latest"], e["id"]
        assert e["date"] >= c["as_of"], e["id"]


def test_peers():
    p = load("peers")
    tickers = [b["ticker"] for b in p["banks"]]
    assert p["subject_ticker"] not in tickers and len(tickers) == len(set(tickers))
    order = ["SBER", "VTBR", "T", "BSPB", "MBNK"]
    assert tickers == [t for t in order if t in tickers] + [t for t in tickers if t not in order]


# ------------------------------------------------------------------ узлы калибровки книги

def test_credit_products_weights_and_intensities():
    cp, b = load("credit_products"), load("balance")
    w = cp["anchor_weights"]
    total = sum(v(b["books"][k]) for k in LOANS)
    assert abs(sum(x["v"] for x in w.values()) - 1) < 1e-8
    for k in LOANS:
        assert abs(w[k]["v"] - v(b["books"][k]) / total) < 1e-8, k
    for p, q in cp["quarters"].items():
        if "total" not in q:
            continue
        assert abs(q["intensity"]["v"] - q["total"]["v"] / q["on_anchor"]["v"]) < 1e-6, p   # узлы — 9 знаков
        assert abs(q["on_anchor"]["v"] - sum(w[k]["v"] * q["cor_books"][k]["v"] for k in LOANS)) < 1e-8, p
    for name, x in cp["intensity"].items():
        lo, hi = sorted((x["databook"]["v"], x["ifrs"]["v"]))
        assert x["low"]["v"] == lo and x["high"]["v"] == hi and abs(x["mid"]["v"] - (lo + hi) / 2) < 1e-9, name
    for k, m in cp["m7_readings"].items():
        assert abs(m["mid"]["v"] - (m["min"]["v"] + m["max"]["v"]) / 2) < 1e-9, k


def test_perimeter_groups_centre_is_the_middle_of_the_ends():
    """Ряд периметра (класс 6): центр связки — середина её концов; строки окна ХКФ в сумме дают концы связки."""
    p = load("perimeter")
    for g, d in p["groups"].items():
        assert d["low"]["v"] <= d["centre"]["v"] <= d["high"]["v"] and abs(d["centre"]["v"] - (d["low"]["v"] + d["high"]["v"]) / 2) <= 0.0051, g
    hcf = [r for r in p["rows"] if r["entity"] == "hcf" and r["line"] == "opex_window"]
    assert abs(-sum(r["low"] for r in hcf) - p["groups"]["hcf"]["low"]["v"]) < 1e-6
    assert abs(-sum(r["high"] for r in hcf) - p["groups"]["hcf"]["high"]["v"]) < 1e-6
    lo, hi = p["window"]
    assert all(r["period"] <= hi for r in p["rows"]) and set(p["events"]) <= {r["period"] for r in p["rows"]}


def test_misc_window_series_in_anchor_prices():
    m = load("misc_window")
    qs = list(m["quarters"])
    assert qs[0] == "2023Q1" and qs[-1] == anchor() and m["quarters"][anchor()]["deflator"]["v"] == 1.0
    for q, r in m["quarters"].items():
        for x in ("sec", "fvr", "other"):
            nominal = r["other_core" if x == "other" else x]["v"]
            assert abs(nominal * r["deflator"]["v"] - r[x + "_real"]["v"]) < 2e-6, f"{q}.{x}"
    assert 0 < m["slope"]["y2023_2026"]["v"] < m["slope"]["R"]["v"] < 1
