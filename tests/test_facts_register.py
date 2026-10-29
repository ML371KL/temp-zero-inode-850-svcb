"""Дивиденды Совкомбанка: история решений, запись реестра, политика (data/facts/dividends.json).

Годовой календарь (форма Сбера): одна строка истории на год прибыли, ключ — четвёртый квартал года; сумма решения —
DPS × акции в расчёте (выпущенные минус собственные акции банка), не DPS × выпущенные; рядом — прибыль года, купон
бессрочных и законная ставка налога; история до IPO — отдельным списком. Запись реестра — решение с экс-датой позже
якоря; закрыт ли год прибыли, решает дата решения строки истории.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
SOURCE_RE = re.compile(r"^(manual|news): \S")
RECORD_AFTER_DECISION = (10, 20)     # дней от решения собрания до даты реестра (политика, п. 4.6)
SVCB_ANCHOR = "2026Q2"


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def day(x: str) -> dt.date:
    return dt.date.fromisoformat(x)


def test_history_is_one_row_per_fiscal_year_keyed_by_the_fourth_quarter():
    d = load("dividends")
    years = [r["year"] for r in d["history"]]
    assert years == sorted(years) and len(years) == len(set(years))
    for r in d["history"]:
        assert r["period"] == f"{r['year']}Q4", r["year"]
        assert r["dps"]["v"] == r["dps_ordinary"]["v"] == r["dps_pre_split"]["v"] and r["split_factor"] == 1, r["year"]
        assert r["label"].startswith(f"за {r['year']} год"), r["year"]
        assert r["settlement"] == "T+1" and r["decided_by"], r["year"]


def test_pool_is_dps_times_the_shares_in_the_decision():
    """Сумма решения — DPS × акции в расчёте суммы (выпущенные − собственные акции банка): у решений с раскрытым
    числом акций — до рубля; доля выплаты — сумма к отчётной прибыли акционеров года."""
    for r in load("dividends")["history"]:
        if "eligible_shares" in r:
            assert abs(r["dps"]["v"] * r["eligible_shares"]["v"] / 1000 - r["pool_declared"]["v"]) < 1e-6, r["year"]
        assert abs(r["pool_declared"]["v"] / r["ni_shareholders"]["v"] - r["payout_shareholders"]["v"]) < 1e-6, r["year"]
        assert r["tax_statutory"]["v"] in (0.2, 0.25) and r["at1_coupon"]["v"] > 0, r["year"]
    sh = load("shares")
    last = max(load("dividends")["history"], key=lambda h: h["decided_date"])
    assert last["eligible_shares"]["v"] == sh["dividend_eligible"]["v"]


def test_decided_date_and_record_date_rule():
    """Реестр — 10–20 дней после решения; экс-дата = реестр (торги T+1); последний день покупки — рабочий день до
    реестра; выплата номинальным держателям — после реестра; решение — после конца года прибыли."""
    lo, hi = RECORD_AFTER_DECISION
    for r in load("dividends")["history"]:
        decided, record = day(r["decided_date"]), day(r["record_date"])
        where = str(r["year"])
        assert lo <= (record - decided).days <= hi, f"{where}: реестр не через 10–20 дней после решения"
        assert r["ex_date"] == r["record_date"], f"{where}: экс-дата"
        assert 1 <= (record - day(r["last_buy_date"])).days <= 3 and day(r["last_buy_date"]).weekday() < 5, where
        assert record < day(r["pay_date"]) <= record + dt.timedelta(days=18), f"{where}: срок выплаты"
        assert day(r["recommended_date"]) < decided and decided > dt.date(r["year"], 12, 31), where
        if r.get("pay_deadline_others"):
            assert day(r["pay_deadline_others"]) > day(r["pay_date"]), where


def test_sources_have_kind():
    d = load("dividends")
    for r in d["history"] + d["register_seed"]:
        assert r["sources"] and all(SOURCE_RE.match(s) for s in r["sources"]), r["period"]
        assert {s.split(":", 1)[0] for s in r["sources"]} == {"manual", "news"}, f"{r['period']}: документ и новость"
    for r in d["history"]:
        assert "sha256" in r["dps"]["src"] and "sha256" in r["pool_declared"]["src"], r["year"]


def test_register_seed_records():
    """Запись реестра — решение с экс-датой позже якоря; статус — по дню среза листов (выплачено / объявлено)."""
    d, a = load("dividends"), load("anchor")
    hist = {r["period"]: r for r in d["history"]}
    want = [r["period"] for r in d["history"] if r["ex_date"] > a["as_of"]]
    assert [r["period"] for r in d["register_seed"]] == want
    for r in d["register_seed"]:
        h = hist[r["period"]]
        for k in ("year", "label", "dps", "decided_date", "recommended_date", "record_date", "last_buy_date", "ex_date", "pay_date"):
            assert r[k] == h[k], f"{r['period']}.{k}: запись реестра расходится со строкой истории"
        assert r["status"] == ("paid" if r["pay_date"] <= d["snapshot"] else "declared"), r["period"]
    if a["period"] == SVCB_ANCHOR:
        got = [(r["period"], r["dps"]["v"], r["status"], r["record_date"]) for r in d["register_seed"]]
        assert got == [("2025Q4", 0.35, "paid", "2026-07-13")]
        assert "register_seed_note" in d


def test_policy_bounds_and_threshold():
    """Политика v2 (20.11.2023): 25–50 % чистой прибыли по МСФО не реже раза в год; потолок ядра — верх диапазона;
    порог — Н1.0 банка после выплаты не ниже 11,5 %; срока нет."""
    p = load("dividends")["policy"]
    assert (p["payout_low"]["v"], p["payout_high"]["v"], p["cap"]["v"], p["threshold"]["v"]) == (0.25, 0.5, 0.5, 0.115)
    assert p["frequency"] == "annual" and p["valid_until"]["v"] is None and p["approved"] == "2023-11-20"
    assert all("sha256" in p[k]["src"] for k in ("payout_low", "payout_high", "cap", "threshold"))
    assert re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) and p["doc"].endswith(".pdf")
    for r in load("dividends")["history"]:
        assert r["payout_shareholders"]["v"] < p["payout_low"]["v"], f"{r['year']}: выплата выше нижней границы политики"


def test_years_and_the_history_before_ipo():
    d, p = load("dividends"), load("pnl_quarterly")
    a = load("anchor")["period"]
    complete = [y for y, r in d["years"].items() if r["complete"]]
    assert complete == [str(y) for y in range(int(min(p["quarters"])[:4]), int(a[:4]))]
    open_ = d["years"][a[:4]]
    assert open_["complete"] is False and open_["through"] == a
    before = d["history_before"]
    assert before and all((r["dps"]["v"] > 0 and r["total"]["v"] > 0) == (r["kind"] != "none") for r in before)
    assert {r["kind"] for r in before} <= {"interim", "paid_in_year", "none"}
    assert all(int(str(r["year"])[:4]) <= min(h["year"] for h in d["history"]) for r in before)


# Отступление фактов от правила гигиены семейства: источник назван методом API брокера (лист решений этапа 1).
KNOWN_BROKER_WORDS = 7


def test_broker_calendar_is_only_a_check():
    d = load("dividends")
    assert "совпало" in d["broker_check"] and "T+1" in d["dates_rule"] and "10 рабочих дней" in d["dates_rule"]
    text = json.dumps(d, ensure_ascii=False)
    assert text.count("GetDividends") + text.count("declaredDate") <= KNOWN_BROKER_WORDS, "новые имена методов API в фактах"


def test_core_accepts_the_seed_records():
    """Правила годности записи реестра ядра принимают записи реестра как есть."""
    live = pytest.importorskip("model.live")
    check = getattr(live, "check_register", None)
    if check is None:
        pytest.skip("в ядре нет check_register")
    rows = [{k: (x.get("v") if isinstance(x, dict) and "v" in x else x) for k, x in rec.items()}
            for rec in load("dividends")["register_seed"]]
    params = inspect.signature(check).parameters
    ok, bad = check(rows, **({"price": 10.0} if "price" in params else {}))
    assert not bad, f"ядро отвергло записи реестра: {[(b.get('period'), b.get('reason')) for b in bad]}"
    assert len(ok) == len(rows)
