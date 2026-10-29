"""Выпуск на форме Т, волна 1 (фикстура `tests/fixtures/core_t`): необязательные узлы выпуска.

Делитель в полях «на акцию» и в проверке формулы цены контракта (М§8.4), блок дивидендов по виду теста
истории выплат (М§5.2), оценка нормативов якоря (М§3.3), строки гайденса формы Т (М§14.2), поправка сторожа
заголовка на экс-дату при делителе «размещённые» (М§14.4). Выпуск книги без ключей формы Т этих узлов не несёт.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import timedelta

import pytest

from model import payload as P
from model.checks import check_gates
from model.grid import DividendRecord, LiveInputs, bank_language, run_grid
from tests.support_core2 import CONTROL_FIXTURE, TODAY, book_prices, explained, fast_release_payload, outputs
from tests.support_core_t import plain_book, t_facts

pytestmark = pytest.mark.tact

BASIS = "valuation.shares_basis"
HISTORY = "dividends.policy.history_test"
GUIDANCE = "checks.guidance_items"


def _release(book, facts=None, *, day=TODAY, register=None, previous=None):
    """Быстрый выпуск на книге формы Т с объяснёнными гейтами; `register` — строки реестра сборщиков (тогда
    сборка идёт с живыми входами на дату `day`), иначе — затравка реестра из фактов."""
    facts = facts or t_facts()
    if register is None:
        probe = run_grid(book, facts)
        expl = explained(check_gates(probe, today=day), today=day)
        rel = P.make_release(live=False, fast=True, today=day, book=book, facts=facts, explanations=expl, notes=[],
                             draws=4, control_model=CONTROL_FIXTURE)
    else:
        px = book_prices(book)
        recs = tuple(DividendRecord(year=r["year"], dps=r["dps"], status=r["status"],
                                    record_date=P.to_date(r["record_date"]), last_buy_date=P.to_date(r["last_buy_date"]),
                                    ex_date=P.to_date(r["ex_date"]), pay_date=P.to_date(r["pay_date"]),
                                    sources=tuple(r["sources"])) for r in register)
        probe = run_grid(book, facts, LiveInputs(valuation_date=day, prices=px, price_dates={t: day for t in px},
                                                 register=recs))
        expl = explained(check_gates(probe, today=day), today=day)
        out = outputs({t: [(day, px[t])] for t in px}, register=register)
        rel = P.make_release(live=True, fast=True, today=day, book=book, facts=facts, outputs=out, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE)
    rel.previous = previous
    return rel, P.build_payload(rel)


def _facts(file: str, change):
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


def _inv(d, name):
    return next(x for x in d["checks"]["invariants"] if x["name"] == name)


# ------------------------------------------------------------------ делитель в выпуске (М§8.4)


def test_release_prints_everything_per_share_on_the_divisor():
    """`meta.shares` несёт делитель, его базу и подпись; капитализация, капитал на акцию, мост и водопад
    «на акцию», капитал медианы из цены — на N_div; число акций в обращении и размещённых — прежние факты."""
    book = plain_book((BASIS, HISTORY))
    rel, d = _release(book)
    run, facts = rel.run, t_facts()
    n_div, n_out = run.divisor, run.shares_out
    shares = d["meta"]["shares"]
    assert (shares["divisor_mln"], shares["divisor_basis"], shares["divisor_label"]) == (
        n_div, "issued", book.label("basis.divisor"))
    assert shares["outstanding_mln"] == n_out and shares["issued_mln"] == facts.need("shares", "issued_total")
    assert shares["depositary_block_mln"] == facts.need("shares", "depositary_block")
    assert shares["economic_treasury_mln"] == facts.need("shares", "economic_treasury")
    assert shares["corporate_actions"] == [{"date": "2026-04-15", "kind": "split", "title": "Дробление акций 1:10",
                                            "factor": 10}]
    assert d["meta"]["basis_labels"] == {k: book.label(f"basis.{k}") for k in (
        "profit", "roe", "divisor", "dividend_issued", "dividend_outstanding")}
    # сумма дивиденда несёт код базы: реестр и ряды модели — размещённые акции, мост — акции в обращении
    assert d["dividends"]["amount_basis"] == "issued" and d["fair_value"]["bridge"]["amount_basis"] == "outstanding"
    for r in d["dividends"]["register"]:
        assert r["amount"] == pytest.approx(r["dps"] * facts.need("shares", "issued_total") / 1000, abs=0.006)
    for r in d["fair_value"]["bridge"]["rows"]:
        assert r["amount"] == pytest.approx(r["dps"] * n_out / 1000, abs=0.006)
    price = d["market"]["price"]
    assert d["market"]["cap"] == pytest.approx(price * n_div / 1000, abs=0.005) == d["market"]["cap_by_ticker"]["T"]
    bl = bank_language(run)
    assert d["market"]["multiples"]["bv_per_share"] == pytest.approx(bl["bv_v"] * 1000 / n_div, abs=0.005)
    assert d["market"]["multiples"]["pb"] == pytest.approx(price * n_div / 1000 / bl["bv_v"], abs=1e-4)
    bridge = d["fair_value"]["bridge"]
    assert run.bridge_amount != 0 and bridge["per_share"] == pytest.approx(run.bridge_amount * 1000 / n_div, abs=0.005)
    for row in d["layers"]["headline_mix"]["waterfall"]:
        assert row["per_share"] == pytest.approx(row["amount"] * 1000 / n_div, abs=0.006), row["key"]
    b = d["fair_value"]["bank_first_line"]
    g, pend = run.governance, run.pending_dividend
    unit = d["fair_value"]["headline"]["median"] * n_div / 1000 - run.bridge_amount - pend
    assert b["v_median"] == pytest.approx((unit / (1 - g) if unit > 0 else unit) + pend, abs=0.006)
    assert abs(n_div / n_out - 1) > 0.04                                     # делитель и акции в обращении различимы


# test_contract_checks_the_price_formula_on_the_divisor_of_the_release —
#     вне такта: `tests/test_core2_t_w1_release.py`


# test_exdate_invariant_of_the_release_expects_the_jump_on_the_divisor —
#     вне такта: `tests/test_core2_t_w1_release.py`


def _register_row(year, dps, ex, status="declared"):
    return {"year": year, "dps": dps, "status": status, "record_date": ex.isoformat(), "ex_date": ex.isoformat(),
            "last_buy_date": (ex - timedelta(days=1)).isoformat(), "pay_date": (ex + timedelta(days=15)).isoformat(),
            "decided_date": (ex - timedelta(days=15)).isoformat(), "sources": ["документ эмитента", "новость"]}


# test_jump_guard_takes_the_ex_date_off_per_valuation_share —
#     вне такта: `tests/test_core2_t_w1_release.py`


# ------------------------------------------------------------------ блок дивидендов по виду теста истории (М§5.2)


# test_dividend_block_follows_the_history_test_of_the_book —
#     вне такта: `tests/test_core2_t_w1_release.py`


def test_release_of_a_book_without_the_keys_of_the_second_form_has_no_new_nodes():
    """Книга без поведенческих ключей формы Т: в выпуске нет ни делителя, ни вида теста истории, ни оценки
    нормативов, ни новых гейтов и флагов; заголовки инвариантов — прежние. Подписи базиса — ключи любой книги."""
    rel, d = fast_release_payload(first_form=True)
    assert not {"divisor_mln", "divisor_basis", "divisor_label"} & set(d["meta"]["shares"])
    assert not {"history_test", "cap"} & set(d["dividends"]["policy"]) and "cap_check" not in d["dividends"]
    assert "estimated" not in d["capital"]["anchor"]
    assert [f["name"] for f in d["checks"]["flags"]] == list(P.FLAG_TITLES)
    assert [(i["name"], i["title"]) for i in d["checks"]["invariants"]] == [(n, P.INVARIANT_TITLES[n])
                                                                             for n in P.ORDER_INVARIANTS]
    assert not {g["name"] for g in d["checks"]["gates"]} & set(P.FORM_GATE_TITLES)
    assert d["meta"]["basis_labels"] == {k: rel.book.label(f"basis.{k}") for k in ("profit", "roe", "divisor")}
    assert len(d["dividends"]["formula_check"]) >= 2


# ------------------------------------------------------------------ оценка нормативов якоря (М§3.3)


# test_estimated_capital_anchor_reaches_the_release —
#     вне такта: `tests/test_core2_t_w1_release.py`


# test_roe_of_the_issuer_stands_next_to_the_roe_of_the_release —
#     вне такта: `tests/test_core2_t_w1_release.py`


# test_pending_deal_of_the_calendar_raises_the_flag —
#     вне такта: `tests/test_core2_t_w1_release.py`


# ------------------------------------------------------------------ строки гайденса формы Т (М§14.2)


def test_guidance_rows_of_the_t_form():
    """Строки по перечню книги: рост прибыли и дивиденда — факт с начала года к тем же кварталам прошлого года
    и путь года смеси заголовка к базе прошлого года; цель ROE эмитента — к его капиталу: факт печатается, путь
    модели в этом определении не считается, строка не сравнивается."""
    book = plain_book((HISTORY, GUIDANCE))
    rel, d = _release(book, register=[])
    facts, run = t_facts(), rel.run
    items = {i["key"]: i for i in d["guidance"]["items"]}
    assert list(items) == [it["key"] for it in book.get(GUIDANCE)]
    ni = lambda p: facts.need("pnl_quarterly", f"quarters.{p}.ni_shareholders")  # noqa: E731
    lam = run.lam
    mix = {c.key: lam * run.layers["analytical"].prob[c.key] + (1 - lam) * run.layers["macro_neutral"].prob[c.key]
           for c in run.cells}
    p_an = run.layers["analytical"].prob
    tl = run.ctx.timeline
    # рост операционной прибыли
    row = items["op_np_growth"]
    base = sum(ni(f"2025Q{h}") for h in (1, 2, 3, 4))
    year = ni("2026Q1") + ni("2026Q2") + sum(mix[c.key] * sum(c.quarters["ni_sh"][q] for q in tl.quarters_of_year(2026) if q >= 1)
                                              for c in run.cells)
    assert row["fact_periods"] == ["2026Q1", "2026Q2"]
    assert row["fact_ytd"] == pytest.approx((ni("2026Q1") + ni("2026Q2")) / (ni("2025Q1") + ni("2025Q2")) - 1, abs=1e-6)
    assert row["model_year"] == pytest.approx(year / base - 1, abs=1e-6)
    cells = {c.key: c.annual["ni_sh"][0] / base - 1 for c in run.cells}
    assert row["mass_outside"] == pytest.approx(sum(p_an[k] for k, v in cells.items() if v < 0.20), abs=1e-6)
    assert row["status"] == ("inside" if row["model_year"] >= 0.20 else "outside") and row["guidance"] == 0.20
    # рост дивиденда на акцию: решённые кварталы прибыли года к тем же кварталам прошлого года
    row = items["dps_growth"]
    assert row["fact_ytd"] == pytest.approx((4.60 + 4.70) / (3.30 + 3.50) - 1, abs=1e-6)
    dps_prev = 3.30 + 3.50 + 3.60 + 4.50
    assert row["model_year"] == pytest.approx(sum(mix[c.key] * c.dps[2026] for c in run.cells) / dps_prev - 1, abs=1e-6)
    assert row["mass_outside"] == pytest.approx(sum(p_an[c.key] for c in run.cells if c.dps[2026] / dps_prev - 1 < 0.20),
                                                abs=1e-6)
    assert "17,88" in row["scope_note"]
    # цель ROE эмитента — к операционному капиталу: ROE выпуска (к капиталу акционеров) с ней не сравнивается —
    # базисы не смешиваются; факт эмитента печатается, статус «неприменимо», массы нет
    row = items["roe_target"]
    assert row["model_year"] is None and row["kind"] == "point" and row["guidance"] == 0.30
    mq = lambda p: facts.need("mgmt_quarterly", f"quarters.{p}.roe")           # noqa: E731
    assert row["fact_ytd"] == pytest.approx((mq("2026Q1") + mq("2026Q2")) / 2, abs=1e-6)   # ROE эмитента, фактом
    assert row["status"] == "n/a" and row["mass_outside"] is None and row["required_rest"] is None
    annual = next(r for r in d["paths"]["annual"] if r["year"] == 2026)
    assert annual["roe"] is not None                              # ROE выпуска — своей строкой годового пути
    gate = next(g for g in d["checks"]["gates"] if g["name"] == "guidance_gap")
    assert "ROE" not in (gate["message"] or "")
    for key in ("nim", "cor_max", "cir"):
        assert items[key]["guidance"] is None and items[key]["status"] == "n/a" and items[key]["mass_outside"] is None
    assert d["guidance"]["src"] is not None                                   # источник — первый пункт с числом
