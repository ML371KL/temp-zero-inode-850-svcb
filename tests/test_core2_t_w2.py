"""Живой реестр и выпуск при квартальном календаре дивидендов (фикстура `tests/fixtures/core_t`).

Реестр по периодам (М§5.7.6, §15.1): ключ записи — квартал прибыли, два правила годности квартального режима,
флаг `dividend_register` по открытым кварталам. Блок дивидендов выпуска (П§2): записи реестра, истории, экс-дат и
моста несут год прибыли и — необязательно — квартал прибыли и слова решения; `dividends.model[]` — по годам
прибыли, квартальный путь — `model_quarters[]`; ближайшая выплата — по периоду; строка лестницы с порогом 0 не
печатается; события выплаты — с идентификатором по периоду. Выпуск книги с годовым календарём этих узлов не несёт.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import date, timedelta

import pytest

from model import payload as P
from model.checks import check_gates
from model.grid import DividendRecord, LiveInputs, run_grid
from model.live import apply_live, check_register, register_gaps
from tests.support_core2 import CONTROL_FIXTURE, TODAY, book_prices, explained, fast_release_payload, outputs
from tests.support_core_t import neutral_book, plain_book, plain_dict, put, t_facts

tact = pytest.mark.tact                      # быстрые тесты — в такте сервера; тяжёлые сборки выпуска — только в CI

CAL = "dividends.calendar"
BASIS = "valuation.shares_basis"
HISTORY = "dividends.policy.history_test"
SOURCES = ["manual: протокол собрания", "news: сообщение о решении"]


def _row(period: str, dps: float, decided: str, record: str, pay: str, *, status: str = "declared",
         label: str | None = None, last_buy: str | None = None) -> dict:
    """Строка реестра сборщиков за квартал прибыли: экс-дата — день реестра."""
    day = date.fromisoformat(record)
    row = {"year": int(period[:4]), "period": period, "dps": dps, "status": status, "decided_date": decided,
           "record_date": record, "last_buy_date": last_buy or (day - timedelta(days=3)).isoformat(), "ex_date": record,
           "pay_date": pay, "sources": list(SOURCES)}
    if label:
        row["label"] = label
    return row


Q3 = _row("2026Q3", 4.80, "2026-10-05", "2026-10-16", "2026-10-30", label="за девять месяцев 2026 года")
Q4 = _row("2026Q4", 5.00, "2027-05-13", "2027-05-24", "2027-06-07")


def _facts(file: str, change):
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


def _record(r: dict) -> DividendRecord:
    day = lambda k: None if r.get(k) is None else P.to_date(r[k])  # noqa: E731
    return DividendRecord(year=int(r["year"]), dps=float(r["dps"]), status=r["status"], record_date=day("record_date"),
                          last_buy_date=day("last_buy_date"), ex_date=day("ex_date"), pay_date=day("pay_date"),
                          sources=tuple(r.get("sources") or ()), period=r.get("period"), label=r.get("label"),
                          decided_date=day("decided_date"))


def _release(book, facts=None, *, day=TODAY, register=None, previous=None, nowcast=None):
    """Быстрый выпуск на книге формы Т с объяснёнными гейтами. `register` — строки реестра сборщиков: сборка идёт
    с живыми входами на дату `day` (затравка фактов и принятые строки); без него — на затравке реестра из фактов."""
    facts = facts or t_facts()
    if register is None:
        probe = run_grid(book, facts)
        expl = explained(check_gates(probe, today=day), today=day)
        rel = P.make_release(live=False, fast=True, today=day, book=book, facts=facts, explanations=expl, notes=[],
                             draws=4, control_model=CONTROL_FIXTURE)
    else:
        px = book_prices(book)
        out = outputs({t: [(day, px[t])] for t in px}, register=register, nowcast=nowcast)
        live, _ = apply_live(book, facts, out, today=day, previous={})
        expl = explained(check_gates(run_grid(book, facts, live), today=day), today=day)
        rel = P.make_release(live=True, fast=True, today=day, book=book, facts=facts, outputs=out, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE)
    rel.previous = previous
    return rel, P.build_payload(rel)


def _mix(rel) -> dict:
    run, lam = rel.run, rel.run.lam
    return {c.key: lam * run.layers["analytical"].prob[c.key] + (1 - lam) * run.layers["macro_neutral"].prob[c.key]
            for c in run.cells}


def _inv(d, name):
    return next(x for x in d["checks"]["invariants"] if x["name"] == name)


def _flag(d, name):
    return next(f for f in d["checks"]["flags"] if f["name"] == name)


# ------------------------------------------------------------------ живой реестр по периодам (М§15.1)


@tact
def test_two_records_of_one_year_are_two_records():
    """Ключ записи — квартал прибыли: записи одного года прибыли в одну не сливаются и все доходят до прогона;
    решение собрания снимает рекомендацию своего квартала, а не чужого."""
    book, facts = neutral_book(), t_facts()
    px = book_prices(book)
    day = date(2026, 10, 14)
    hint = {**Q4, "status": "recommended", "decided_date": None, "sources": ["manual: рекомендация совета директоров"]}
    stale = {**Q3, "status": "recommended"}                   # рекомендация за 3К при уже принятом решении
    out = outputs({t: [(day, px[t])] for t in px}, register=[stale, Q3, hint])
    live, report = apply_live(book, facts, out, today=day, previous={})
    assert [(r["period"], r["status"]) for r in report.records] == [
        ("2026Q1", "paid"), ("2026Q2", "declared"), ("2026Q3", "declared"), ("2026Q4", "recommended")]
    assert [(r.period, r.dps, r.label) for r in live.register] == [
        ("2026Q1", 4.6, "за первый квартал 2026 года"), ("2026Q2", 4.7, "за полугодие 2026 года"),
        ("2026Q3", 4.8, "за девять месяцев 2026 года")]
    assert live.register[2].decided_date == date(2026, 10, 5) and not report.rejected and not report.alarms
    rec = report.flags["dividend_recommended"]
    assert rec["raised"] and rec["detail"] == book.label("register.recommended_item", dps=5.0, year=2026,
                                                         period="2026Q4", label=book.label("periods.4", year=2026))
    # годовой календарь: ключ — год прибыли; вторая запись года замещает первую (так считает образец)
    annual = plain_book()
    _, was = apply_live(annual, facts, out, today=day, previous={})
    assert [(r["status"], r["dps"]) for r in was.records] == [("declared", 4.8)]


@tact
def test_quarterly_rules_of_the_register():
    """При квартальном календаре объявленная запись без квартала прибыли не принимается; запись за открытый
    квартал с решением не позже даты фактов не принимается — сначала правятся факты; год прибыли записи — год её
    квартала. Отвергнутая запись — тревога живого входа словами книги."""
    book, facts = neutral_book(), t_facts()
    facts_date = date(2026, 6, 30)
    kw = dict(price=330.0, quarterly=True, closed_period="2025Q4", facts_date=facts_date)
    no_period = {k: v for k, v in Q3.items() if k not in ("period", "label")}
    early = _row("2026Q1", 4.6, "2026-06-25", "2026-07-06", "2026-07-20")
    closed = _row("2025Q4", 4.5, "2026-05-14", "2026-05-25", "2026-06-08", status="paid")
    wrong_year = {**Q3, "year": 2025}
    no_year = {k: v for k, v in Q3.items() if k != "year"}
    ok, bad = check_register([no_period, early, closed, wrong_year, no_year, Q4], **kw)
    assert [(r["period"], r["year"]) for r in ok] == [("2025Q4", 2025), ("2026Q3", 2026), ("2026Q4", 2026)]
    why = [r["reason"] for r in bad]
    assert why[0] == "нет квартала прибыли" and "сначала правятся факты" in why[1] and "не год квартала" in why[2]
    # рекомендация без квартала прибыли остаётся плашкой; при годовом календаре правил периода нет
    hint = {**no_period, "status": "recommended"}
    assert check_register([hint], **kw)[1] == []
    assert check_register([no_period, early], price=330.0)[1] == []
    px = book_prices(book)
    day = date(2026, 10, 14)
    out = outputs({t: [(day, px[t])] for t in px}, register=[no_period, early])
    live, report = apply_live(book, facts, out, today=day, previous={})
    assert [r.period for r in live.register] == ["2026Q1", "2026Q2"] and len(report.rejected) == 2      # затравка фактов
    words = book.label("register.rejected_item", reason="нет квартала прибыли", year=2026, period="",
                       label=book.label("periods.4", year=2026))
    assert words in report.alarms and report.degraded_flag
    assert any("за первый квартал 2026 года" in a and "сначала правятся факты" in a for a in report.alarms)


@tact
def test_register_flag_names_the_open_quarters_without_a_record():
    """Флаг `dividend_register`: открытый квартал прибыли без записи, у которого конец квартала решения по карте
    лагов раньше даты оценки; закрытые кварталы пропуском не бывают при любой карте; слова — из книги."""
    book, facts = neutral_book(), t_facts()
    seeds = [{"period": "2026Q1", "status": "paid"}, {"period": "2026Q2", "status": "declared"}]
    gap = lambda period, quarter, end: book.label(  # noqa: E731
        "register.gap_item", decision_quarter=quarter, end=end, year=int(period[:4]), period=period,
        label=book.label(f"periods.{period[-1]}", year=int(period[:4])))
    assert register_gaps(book, [], date(2026, 9, 30), facts) == []
    assert register_gaps(book, [], date(2026, 10, 1), facts) == [gap("2026Q1", "2026Q3", "2026-09-30")]
    assert "дивиденд за первый квартал 2026 года (решение ожидалось в квартале 2026Q3, конец 2026-09-30)" == gap(
        "2026Q1", "2026Q3", "2026-09-30")
    assert register_gaps(book, seeds, date(2026, 12, 31), facts) == []
    assert register_gaps(book, seeds, date(2027, 1, 5), facts) == [gap("2026Q3", "2026Q4", "2026-12-31")]
    assert register_gaps(book, seeds + [{"period": "2026Q3", "status": "recommended"}], date(2027, 1, 5), facts) == [
        gap("2026Q3", "2026Q4", "2026-12-31")]               # рекомендация записью решения не считается
    late = register_gaps(book, [], date(2027, 7, 1), facts)
    assert [g.split(" (")[0] for g in late] == [
        "дивиденд за первый квартал 2026 года", "дивиденд за полугодие 2026 года",
        "дивиденд за девять месяцев 2026 года", "дивиденд за 2026 год"]
    # карта с лагом 4: по карте решение за 4К прошлого года «впереди» — оно закрыто фактом и пропуском не станет
    data = plain_dict(on=(CAL,))
    put(data, "dividends.calendar.decision_lag_quarters", 4)
    from model.book import book_from_dict
    slow = book_from_dict(data, facts=facts)
    assert register_gaps(slow, [], date(2027, 1, 5), facts) == []
    assert [g.split(" (")[0] for g in register_gaps(slow, [], date(2027, 4, 1), facts)] == [
        "дивиденд за первый квартал 2026 года"]
    # флаг и тревога сборки: нет затравки реестра — срок решения за 1К прошёл
    bare = _facts("dividends", lambda d: d.update(register_seed=[]))
    rel, d = _release(book, bare, day=date(2026, 10, 14), register=[])
    flag = _flag(d, "dividend_register")
    assert flag["raised"] and flag["title"] == book.label("register.flag_title")
    assert flag["detail"] == book.label("register.flag_detail", gaps=gap("2026Q1", "2026Q3", "2026-09-30"))
    assert book.label("register.alert", detail=flag["detail"]) in P.alerts(rel, d)
    assert d["fair_value"]["jump_guard"]["unregistered_dividend"] > 0        # клетки вычли дивиденд модели сами


# ------------------------------------------------------------------ блок дивидендов выпуска (П§2)


@tact
def test_dividend_block_goes_by_profit_quarters():
    """Выпуск на затравке реестра фактов: параметры календаря, одна строка лестницы, записи реестра и истории с
    периодом и словами решения, годовой путь — суммой кварталов, квартальный путь, ближайшая выплата по периоду."""
    book, facts = neutral_book(), t_facts()
    rel, d = _release(book)
    run, dv = rel.run, d["dividends"]
    tl, cal, p_mix = run.ctx.timeline, run.ctx.prep.calendar, _mix(rel)
    n_iss, n_out = facts.need("shares", "issued_total"), facts.need("shares", "outstanding_total")
    assert P._dividend_problems(d) == []
    pol = dv["policy"]
    assert (pol["frequency"], pol["base_window_quarters"], pol["decision_lag_quarters"]) == (
        "quarterly", 4, {"1": 2, "2": 2, "3": 1, "4": 2})
    assert dv["formula_check"] == [] and [r["year"] for r in dv["cap_check"]] == [2024, 2025, 2026]
    # лестница: порога норматива у политики нет — одна строка, «выплата по политике»
    assert dv["ladder"] == [{"key": "policy", "title": book.label("dividends.ladder_residual_title"),
                             "condition": book.label("dividends.ladder_residual_condition"), "payout": 0.25,
                             "current": True}]
    reg = dv["register"]
    assert [(r["year"], r["period"], r["label"], r["decided_date"], r["status"]) for r in reg] == [
        (2026, "2026Q1", "за первый квартал 2026 года", "2026-07-30", "paid"),
        (2026, "2026Q2", "за полугодие 2026 года", "2026-10-01", "declared")]
    assert reg[1]["amount"] == pytest.approx(4.70 * n_iss / 1000, abs=0.006)
    hist = dv["history"]
    assert len(hist) == 8 and all(r["year"] == int(r["period"][:4]) and r["label"] for r in hist)
    assert (hist[0]["period"], hist[0]["dps"], hist[0]["dps_pre_split"], hist[0]["split_factor"]) == ("2024Q3", 9.25, 92.5, 10)
    assert hist[-1]["dps_pre_split"] is None and hist[-1]["split_factor"] == 1
    assert all(r["payout_ratio"] is None and r["ni_shareholders"] is None and r["dps_preferred"] is None for r in hist)
    # квартальный путь: открытые кварталы с решением в первых 14 кварталах сетки
    mq = dv["model_quarters"]
    assert [r["period"] for r in mq] == [o.period for o in cal.open if o.q <= P.QUARTERS_SHOWN]
    first, second, third = mq[0], mq[1], mq[2]
    assert (first["decision_period"], first["pay_period"], first["dps"], first["declared"]) == ("2026Q3", "2026Q3", 4.6, True)
    assert (second["decision_period"], second["dps_p10"], second["dps_p90"], second["p_cut"]) == ("2026Q4", 4.7, 4.7, 0.0)
    assert (third["period"], third["decision_period"], third["pay_period"], third["declared"]) == (
        "2026Q3", "2026Q4", "2027Q1", False)
    for r in mq[:6]:
        want = sum(p_mix[c.key] * c.dps_q[r["period"]] for c in run.cells)
        policy = sum(p_mix[c.key] * c.dps_policy_q[r["period"]] for c in run.cells)
        assert r["dps"] == pytest.approx(want, abs=6e-5) and r["dps_policy"] == pytest.approx(policy, abs=6e-5)
        assert r["amount"] == pytest.approx(want * n_iss / 1000, abs=0.006)
    crisis = sum(run.layers["analytical"].prob[c.key] for c in run.cells if c.regime == "crisis")
    assert mq[3]["period"] == "2026Q4" and mq[3]["p_zero"] >= crisis - 1e-6           # решение в год шока отменено
    # годовой путь — по годам прибыли: сумма кварталов года
    model = {r["year"]: r for r in dv["model"]}
    assert list(model) == list(cal.years) and model[2026]["pay_year"] == 2027 and model[2026]["declared"] is False
    by_period = {r["period"]: r for r in mq}
    for year in (2026, 2027, 2028):
        parts = [by_period[f"{year}Q{h}"] for h in (1, 2, 3, 4)]
        assert model[year]["dps"] == pytest.approx(sum(r["dps"] for r in parts), abs=3e-4)
        assert model[year]["dps_policy"] == pytest.approx(sum(r["dps_policy"] for r in parts), abs=3e-4)
        cut = sum(run.layers["analytical"].prob[c.key] for c in run.cells
                  if any(x.cut for x in c.decisions if x.year == year))
        assert model[year]["p_cut"] == pytest.approx(cut, abs=1e-6)
    assert model[2026]["amount"] == pytest.approx(model[2026]["dps"] * n_iss / 1000, abs=0.006)
    # ближайшая выплата — запись с ближайшей будущей экс-датой, по периоду
    ne = dv["next_expected"]
    assert (ne["year"], ne["period"], ne["label"], ne["status"], ne["dps"]) == (
        2026, "2026Q2", "за полугодие 2026 года", "declared", 4.7)
    assert ne["yield_period"] == "quarter" and ne["yield"]["T"] == pytest.approx(4.7 / 330.0, abs=1e-6)
    assert (ne["record_date"], ne["pay_date_est"], ne["last_buy_date"]) == ("2026-10-12", "2026-10-26", "2026-10-09")
    assert ne["dps_policy"] == second["dps_policy"] and ne["dps_mean"] == 4.7 and ne["p_cancel"] == 0.0
    q_reg = cal.periods["2026Q2"].q_reg
    assert ne["condition"]["n20_expected"] == pytest.approx(P._Ctx(rel).ratio(run.layers["analytical"].prob, "n20", q_reg),
                                                            abs=1e-6)
    # форвардная доходность — четыре квартала прибыли, начиная с ближайшей выплаты
    fwd = 4.7 + sum(by_period[p]["dps_policy"] for p in ("2026Q3", "2026Q4", "2027Q1"))
    assert d["market"]["multiples"]["dividend_yield_fwd"]["T"] == pytest.approx(fwd / 330.0, abs=2e-6)
    # клетки: первый DPS и годовой ряд — суммы кварталов прибыли года
    cell0, c0 = d["grid"]["cells"][0], run.cells[0]
    assert cell0["dps_first"] == pytest.approx(c0.dps[tl.anchor_year], abs=0.006) == pytest.approx(
        4.6 + 4.7 + c0.dps_q["2026Q3"] + c0.dps_q["2026Q4"], abs=0.006)
    assert d["paths"]["annual"][0]["dps"] == model[2026]["dps"]
    assert _inv(d, "exdate_jump")["ok"] and "запись за полугодие 2026 года" in _inv(d, "exdate_jump")["detail"]
    assert _inv(d, "dividend_bounds")["ok"] and _inv(d, "ddm_equals_ri")["ok"] and _inv(d, "bv_identity")["ok"]


def test_ex_dates_bridge_and_events_keep_the_period():
    """Экс-даты за год, строки моста и события выплаты — по записям: решения одного года прибыли в одно не
    сворачиваются; `in_bridge` — по ключу записи; событие выплаты — с идентификатором по периоду."""
    book, facts = neutral_book(), t_facts()
    day = date(2026, 10, 14)                                 # отсечка за 2К (12.10) прошла, за 3К (16.10) — впереди
    rel, d = _release(book, day=day, register=[Q3])
    n_out, n_div = rel.run.shares_out, rel.run.divisor
    ex = d["market"]["ex_dividend"]
    assert [(e["period"], e["year"], e["dps"]) for e in ex] == [
        ("2025Q3", 2025, 3.6), ("2025Q4", 2025, 4.5), ("2026Q1", 2026, 4.6), ("2026Q2", 2026, 4.7)]
    assert ex[-1]["label"] == "за полугодие 2026 года" and ex[-1]["date"] == "2026-10-12"
    # доходность за 12 месяцев — четыре последних объявленных квартала прибыли (с записью за 3К), а не экс-даты окна
    assert d["dividends"]["yield_ltm_periods"] == ["2025Q4", "2026Q1", "2026Q2", "2026Q3"]
    assert d["market"]["multiples"]["dividend_yield_ltm"]["T"] == pytest.approx((4.5 + 4.6 + 4.7 + 4.8) / 330.0, abs=1e-6)
    assert d["dividends"]["yield_ltm"] == d["market"]["multiples"]["dividend_yield_ltm"]
    rows = d["fair_value"]["bridge"]["rows"]
    assert [(r["period"], r["label"], r["deducted_on"], r["sign"]) for r in rows] == [
        ("2026Q1", "за первый квартал 2026 года", "2026-09-30", 0),
        ("2026Q2", "за полугодие 2026 года", "2026-12-31", -1),
        ("2026Q3", "за девять месяцев 2026 года", "2026-12-31", 0)]
    assert d["fair_value"]["bridge"]["amount"] == pytest.approx(-4.7 * n_out / 1000, abs=0.006)
    assert d["fair_value"]["bridge"]["pending_dividend"] == pytest.approx((4.7 + 4.8) * n_out / 1000, abs=0.006)
    assert [(r["period"], r["in_bridge"]) for r in d["dividends"]["register"]] == [
        ("2026Q1", False), ("2026Q2", True), ("2026Q3", False)]
    assert P._dividend_problems(d) == []                     # ближайшая выплата сверена с записью своего периода
    ne = d["dividends"]["next_expected"]
    assert (ne["period"], ne["status"], ne["dps"], ne["record_date"]) == ("2026Q3", "declared", 4.8, "2026-10-16")
    pays = [e for e in d["calendar"]["events"] if e["kind"] == "pay"]
    assert [(e["id"], e["title"]) for e in pays] == [("pay-2026Q2", "Выплата дивиденда за полугодие 2026 года"),
                                                    ("pay-2026Q3", "Выплата дивиденда за девять месяцев 2026 года")]
    est = next(e for e in d["calendar"]["events"] if e["kind"] == "dividend_decision")
    assert est["estimated"] is True and est["covers"] == "2026Q3" and est["earliest"] and est["latest"]
    deal = next(e for e in d["calendar"]["events"] if e["kind"] == "deal")
    assert deal["in_book"] is False
    inv = _inv(d, "exdate_jump")
    assert inv["ok"] and "запись за девять месяцев 2026 года" in inv["detail"]
    # сторож заголовка: между выпусками — одна экс-дата (2К), на акцию оценки — DPS × N_out / N_div
    _, before = _release(book, day=date(2026, 10, 9), register=[Q3])
    rel2, after = _release(book, day=day, register=[Q3], previous=before)
    jg = after["fair_value"]["jump_guard"]
    assert jg["exdate_adjustment"] == pytest.approx(4.7 * n_out / n_div, abs=0.006) and jg["reason"] == "within_limit"
    assert abs(jg["median_change"]) < 0.01 and abs(jg["v0_change"]) < 0.01
    # две экс-даты одного года прибыли между выпусками (1К — 10.08, 2К — 12.10): поправка — их сумма
    older = copy.deepcopy(before)
    older["meta"]["valuation_date"] = "2026-08-05"
    rel2.previous = older
    two, _ = P._jump_guard(P._Ctx(rel2), after["fair_value"]["headline"]["median"])
    assert two["exdate_adjustment"] == pytest.approx((4.6 + 4.7) * n_out / n_div, abs=0.006)
    # событие-оценка без окна контракт не принимает
    bad = copy.deepcopy(d)
    next(e for e in bad["calendar"]["events"] if e.get("estimated")).pop("latest")
    assert any("оценка даты" in p for p in P._format_problems(bad))


@tact
def test_next_payout_without_a_record_is_the_first_open_quarter_ahead():
    """Без записи ближайшая выплата — первый открытый квартал прибыли без записи, решение по которому не раньше
    квартала даты оценки; главная цифра — DPS политики этого квартала; риск отмены и срез — по его решению."""
    book = neutral_book()
    bare = _facts("dividends", lambda d: d.update(register_seed=[]))
    rel, d = _release(book, bare, day=date(2026, 10, 14), register=[])
    ne, mq = d["dividends"]["next_expected"], {r["period"]: r for r in d["dividends"]["model_quarters"]}
    assert rel.run.ctx.clock.q0 == 2
    assert (ne["period"], ne["status"], ne["year"], ne["label"]) == ("2026Q2", "model", 2026, "за полугодие 2026 года")
    assert ne["dps"] == ne["dps_policy"] == mq["2026Q2"]["dps_policy"] and ne["dps_mean"] == mq["2026Q2"]["dps"]
    assert ne["record_date"] is None and ne["record_date_est"] == "2026-10-12" and ne["yield_period"] == "quarter"
    assert ne["p_cancel"] == mq["2026Q2"]["p_zero"] and ne["condition"]["p_limited"] == mq["2026Q2"]["p_cut"]
    assert P._dividend_problems(d) == [] and mq["2026Q1"]["declared"] is False
    assert "синтетическая запись" in _inv(d, "exdate_jump")["detail"] and _inv(d, "exdate_jump")["ok"]
    fwd = sum(mq[p]["dps_policy"] for p in ("2026Q2", "2026Q3", "2026Q4", "2027Q1"))
    assert d["market"]["multiples"]["dividend_yield_fwd"]["T"] == pytest.approx(fwd / 330.0, abs=2e-6)


def test_history_and_annual_path_sum_the_decisions_of_the_year():
    """`history.annual[]`: DPS и доля выплат — суммой строк решений года; год без строки за четвёртый квартал
    прибыли — пусто. `paths.annual[].div_paid` года якоря: решения собраний, пришедшиеся на отчётные кварталы, —
    оттоком по акциям в обращении, плюс ожидание клеток на остаток года."""
    book, facts = neutral_book(), t_facts()
    rel, d = _release(book)
    n_iss, n_out = facts.need("shares", "issued_total"), facts.need("shares", "outstanding_total")
    annual = {r["year"]: r for r in d["history"]["annual"]}
    assert annual[2025]["dps"] == pytest.approx(3.30 + 3.50 + 3.60 + 4.50, rel=1e-12)
    pools = sum(r["pool_declared"]["v"] for r in facts.files["dividends"]["history"] if r["year"] == 2025)
    assert annual[2025]["payout"] == pytest.approx(pools / annual[2025]["ifrs"]["ni_sh"], abs=1e-6)
    assert annual[2024]["dps"] == pytest.approx(9.25 + 3.20, rel=1e-12)       # «за девять месяцев» и за год
    p_mix, tl = _mix(rel), rel.run.ctx.timeline
    ahead = sum(p_mix[c.key] * c.quarters["div"][q] for c in rel.run.cells for q in tl.quarters_of_year(2026) if q >= 1)
    decided = next(r for r in facts.files["dividends"]["history"] if r["period"] == "2025Q4")    # собрание 14.05.2026
    assert d["paths"]["annual"][0]["div_paid"] == pytest.approx(ahead + decided["pool_declared"]["v"] * n_out / n_iss,
                                                                abs=0.006)
    # год без решения за четвёртый квартал прибыли не завершён
    cut = _facts("dividends", lambda x: x.update(history=[r for r in x["history"] if r["period"] not in (
        "2025Q4", "2026Q1", "2026Q2")], register_seed=[]))
    _, short = _release(book, cut)
    row = next(r for r in short["history"]["annual"] if r["year"] == 2025)
    assert row["dps"] is None and row["payout"] is None
    assert next(r for r in short["history"]["annual"] if r["year"] == 2024)["dps"] == pytest.approx(12.45, rel=1e-12)


def test_nowcast_year_spreads_the_deviation_over_the_base_windows():
    """`nowcast.year` при квартальном календаре: без нау-каста DPS года равен DPS политики года точно; отклонение
    нау-каста открытого квартала входит в базы тех решений модели года, в окно которых этот квартал попадает:
    DPS года растёт на доля × отклонение × n / W на размещённую акцию."""
    book, facts = neutral_book(), t_facts()
    rel, plain = _release(book, day=TODAY, register=[])
    y = plain["nowcast"]["year"]
    model = next(r for r in plain["dividends"]["model"] if r["year"] == y["year"])
    assert y["dps"] == y["dps_model"] == model["dps_policy"] and y["dps_interval"] is None
    run, p_mix = rel.run, _mix(rel)
    bases = sum(p_mix[c.key] * sum(x.base for x in c.decisions if x.year == y["year"]) for c in run.cells)
    assert y["base"] == pytest.approx(bases, abs=0.006) and "сумма решений за кварталы прибыли" in y["note"]
    period = plain["nowcast"]["quarter"]["period"]
    expectation = plain["next_report"]["expectation"]["ni"]
    shift, rel_se, sigma = 0.04, 0.03, 0.06
    target = {"ras_estimate": 1.0, "bridge": 1.0, "ras_bridged": expectation * (1 + 2 * shift), "w": 0.5,
              "rel_std_error": rel_se, "sigma_ras": rel_se, "sigma_base": sigma, "basis": "ifrs", "equation": "тест"}
    nowcast = {"period": period, "ras": {"period": period, "targets": {"ni_q": target}, "months": [],
                                         "months_known": 2, "sigmas": {"base": sigma}, "version": "тест"}}
    _, d2 = _release(book, day=TODAY, register=[], nowcast=nowcast)
    t1, y2 = d2["nowcast"]["quarter"]["by_target"]["ni_q"], d2["nowcast"]["year"]
    deviation = t1["forecast"] - t1["expectation"]
    assert deviation == pytest.approx(expectation * shift, rel=1e-6)
    window = int(book.get("dividends.policy.base_window_quarters"))
    n_iss = facts.need("shares", "issued_total")
    hit = 2                                                  # решения модели за 3К и 4К: открытый квартал — в их окне
    assert period == "2026Q3" and [x.source for x in run.cells[0].decisions[:4]] == ["register", "register", "model", "model"]
    assert y2["dps_model"] == y["dps_model"]
    assert y2["dps"] - y["dps"] == pytest.approx(y["payout"] * deviation * hit / window * 1000 / n_iss, abs=2e-4)
    assert y2["base"] - y["base"] == pytest.approx(deviation * hit / window, abs=0.011)
    width = y["payout"] * t1["std_error"] * hit / window * 1000 / n_iss
    assert y2["dps_interval"] == pytest.approx([y2["dps"] - width, y2["dps"] + width], abs=2e-4)


# ------------------------------------------------------------------ годовой календарь: выпуск прежний


@tact
def test_release_with_the_annual_calendar_has_no_period_nodes():
    """Книга без ключа режима календаря: записи реестра, экс-дат и моста — без периода, квартального пути нет,
    лестница — ступень с порогом и остаток, ближайшая выплата — по году, события выплаты — с годом."""
    rel, d = fast_release_payload(first_form=True)
    dv = d["dividends"]
    assert "model_quarters" not in dv and not {"frequency", "base_window_quarters", "decision_lag_quarters"} & set(dv["policy"])
    assert [r["key"] for r in dv["ladder"]] == ["step1", "residual"] and dv["ladder"][-1]["payout"] is None
    assert not {"period", "label", "yield_period"} & set(dv["next_expected"])
    for rows in (dv["register"], dv["history"], d["market"]["ex_dividend"], d["fair_value"]["bridge"]["rows"]):
        assert not [r for r in rows if {"period", "label", "decided_date", "dps_pre_split", "split_factor"} & set(r)]
    years = [r["year"] for r in d["market"]["ex_dividend"]]
    assert len(years) == len(set(years))
    assert all(e["id"].split("-")[1].isdigit() for e in d["calendar"]["events"] if e["kind"] == "pay")
    assert all(c.dps_q == {} and c.dps_policy_q == {} and all(x.period is None for x in c.decisions) for c in rel.run.cells)
    assert d["market"]["multiples"]["dividend_yield_fwd"] == dv["next_expected"]["yield"]
    assert rel.run.ctx.prep.calendar is None


# ------------------------------------------------------------------ разложение между выпусками (М§16)


def test_snapshot_of_the_register_keeps_the_period_and_the_step_sees_a_new_record():
    """Снимок входов выпуска несёт записи реестра с кварталом прибыли, словами и днём решения — следующий выпуск
    восстанавливает их без потерь; шаг «реестр дивидендов» разложения — эффект появившейся записи квартала.
    Запись без периода в снимке новых полей не получает."""
    from model.attribution import attribute, register_from_dicts, register_to_dicts
    book, facts = neutral_book(), t_facts()
    day = date(2026, 10, 9)
    _, before = _release(book, day=day, register=[])
    rel, after = _release(book, day=day, register=[Q3], previous=before)
    snap = after["changes"]["snapshot"]["register"]
    assert [(r["period"], r.get("label"), r["decided_date"]) for r in snap] == [
        ("2026Q1", "за первый квартал 2026 года", "2026-07-30"), ("2026Q2", "за полугодие 2026 года", "2026-10-01"),
        ("2026Q3", "за девять месяцев 2026 года", "2026-10-05")]
    assert register_from_dicts(snap) == rel.live.register and register_to_dicts(rel.live.register) == snap
    assert [r["period"] for r in before["changes"]["snapshot"]["register"]] == ["2026Q1", "2026Q2"]
    plain = DividendRecord(year=2026, dps=4.8, status="declared", record_date=None, last_buy_date=None, ex_date=None,
                           pay_date=None, sources=("проверка",))
    assert set(register_to_dicts((plain,))[0]) == {"year", "dps", "status", "record_date", "last_buy_date", "ex_date",
                                                   "pay_date", "sources"}
    steps = {s.component: s for s in attribute(before, book, facts, rel.live, engine_commit=rel.engine_commit)}
    without = LiveInputs(valuation_date=day, prices=dict(rel.live.prices), price_dates=dict(rel.live.price_dates),
                         register=rel.live.register[:2])
    effect = rel.run.point - run_grid(book, facts, without).point
    assert abs(effect) > 0.01                                 # объявлено 4,80 ₽ вместо дивиденда модели за 3К
    assert steps["register"].point_rub == pytest.approx(effect, abs=1e-9) and steps["valuation_date"].point_rub == 0.0
    assert steps["register"].note == "записей: 2 → 3"
    row = next(r for r in after["changes"]["vs_previous"]["rows"] if r["component"] == "register")
    assert row["point_rub"] == pytest.approx(effect, abs=0.006)
