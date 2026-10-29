"""Быстрый выпуск на проекции формы Т (все исполняемые ветви включены) — на фикстуре `tests/fixtures/core_t`.

Сборка быстрого выпуска — секунды: в набор такта сервера эти тесты не входят (цель времени набора —
ops/budgets.json), идут в CI и в полном прогоне: проекция формы целиком и сценарии с одним-двумя выпусками на
изменённых фактах или реестре (делитель в формуле цены и в скачке экс-даты, сторож заголовка на экс-дате, тест
истории выплат, оценка нормативов якоря, ROE эмитента, сделка календаря). Узлы выпуска формы Т по одному, на общем
быстром выпуске, — в такте: `tests/test_core2_t_w1.py`.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import timedelta

import pytest

from model import payload as P
from model.grid import run_grid
from tests.support_core_t import neutral_book, plain_book, t_facts
from tests.test_core2_t_w1 import BASIS, HISTORY, _facts, _inv, _register_row, _release


def test_fast_release_on_the_projection_of_the_t_form():
    """Проекция формы Т (все исполняемые ветви включены) собирается в выпуск со схемой книги."""
    book = neutral_book()
    _, d = _release(book)
    assert d["schema"] == book.get("meta.schema") and d["dividends"]["formula_check"] == []
    assert d["meta"]["shares"]["divisor_basis"] == "issued" and len(d["grid"]["cells"]) == 36
    assert [p for p in P._point_problems(d) + P._dividend_problems(d) + P._bank_problems(d)] == []


def test_contract_checks_the_price_formula_on_the_divisor_of_the_release():
    """Формула цены М§8.2 в контракте сходится на `meta.shares.divisor_mln`; выпуск без поля сверяется на
    акциях в обращении — и на форме с делителем «размещённые» не сходится."""
    _, d = _release(plain_book((BASIS, HISTORY)))
    assert not [p for p in P._point_problems(d) if "М§8.2" in p]
    stripped = copy.deepcopy(d)
    del stripped["meta"]["shares"]["divisor_mln"]
    assert [p for p in P._point_problems(stripped) if "М§8.2" in p]
    _, base = _release(plain_book((HISTORY,)))                                 # ключ поправки делителя в книге есть
    shares = base["meta"]["shares"]
    assert shares["divisor_mln"] == shares["outstanding_mln"] and shares["divisor_basis"] == "outstanding"
    assert not [p for p in P._point_problems(base) if "М§8.2" in p]
    assert base["market"]["cap"] == pytest.approx(base["market"]["price"] * base["meta"]["shares"]["outstanding_mln"] / 1000,
                                                  abs=0.005)


def test_exdate_invariant_of_the_release_expects_the_jump_on_the_divisor():
    """Инвариант `exdate_jump`: ожидаемый скачок — −DPS × N_out / N_div; заголовок выбирает ключ делителя."""
    rel, d = _release(plain_book((BASIS, HISTORY)))
    inv = _inv(d, "exdate_jump")
    found = next(f for f in rel.extra_findings if f.name == "exdate_jump")
    k = rel.run.shares_out / rel.run.divisor
    assert inv["ok"] and inv["title"] == P.EXDATE_TITLE_DIVISOR and "на акцию оценки" in inv["detail"]
    assert found.detail["expected"] == pytest.approx(found.detail["dps"] * k, rel=1e-12)
    assert found.detail["jump"] == pytest.approx(-found.detail["expected"], rel=float(rel.book.get("checks.exdate_jump_tol")))
    assert abs(found.detail["jump"] + found.detail["dps"]) > float(rel.book.get("checks.exdate_jump_tol")) * found.detail["dps"]
    rel, base = _release(plain_book((HISTORY,)))
    inv = _inv(base, "exdate_jump")
    found = next(f for f in rel.extra_findings if f.name == "exdate_jump")
    assert inv["ok"] and inv["title"] == P.INVARIANT_TITLES["exdate_jump"] and "на акцию оценки" not in inv["detail"]
    assert found.detail["expected"] == found.detail["dps"]


def test_jump_guard_takes_the_ex_date_off_per_valuation_share():
    """Сторож заголовка: на экс-дате медиана падает на DPS × N_out / N_div — поправка на акцию оценки равна
    этому же числу, и сторож молчит; в деньгах поправка — DPS × N_out (М§14.4)."""
    book = plain_book((BASIS, HISTORY))
    tl = run_grid(book, t_facts()).ctx.timeline
    year = tl.anchor_year
    end = tl.end(tl.index(f"{year + 1}Q{book.get('dividends.calendar.agm_quarter')}"))
    ex, dps = end + timedelta(days=18), 20.0
    reg = [_register_row(year, dps, ex)]
    rel_a, a = _release(book, day=ex - timedelta(days=1), register=reg)
    rel_b, b = _release(book, day=ex, register=reg, previous=a)
    k = rel_b.run.shares_out / rel_b.run.divisor
    jg = b["fair_value"]["jump_guard"]
    assert jg["exdate_adjustment"] == pytest.approx(dps * k, abs=0.005) and abs(dps - dps * k) > 0.5
    assert jg["reason"] == "within_limit" and abs(jg["median_change"]) < 0.01 and abs(jg["v0_change"]) < 0.01
    amount = dps * rel_b.run.shares_out / 1000
    assert a["fair_value"]["bridge"]["amount"] == pytest.approx(amount, abs=0.01)
    assert jg["v0_agm_adjustment"] == pytest.approx(0.0, abs=0.02)            # мост прошлого выпуска − дивиденд экс-даты
    med = b["fair_value"]["headline"]["median"] - a["fair_value"]["headline"]["median"]
    assert med == pytest.approx(-dps * k, abs=0.3)


def test_dividend_block_follows_the_history_test_of_the_book():
    """Вид `cap`: `formula_check` пуст, выпуск несёт `cap_check` и параметры политики; контракт требует
    завершённого года без превышения. Вид `none`: ни формулы, ни строк потолка."""
    book = plain_book((HISTORY,))
    rel, d = _release(book)
    div = d["dividends"]
    assert div["formula_check"] == [] and div["policy"]["history_test"] == "cap" and div["policy"]["cap"] == 0.30
    rows = {r["year"]: r for r in div["cap_check"]}
    assert set(rows) == {2024, 2025, 2026} and set(rows[2025]) == {"year", "pool", "ni_shareholders", "share", "cap",
                                                                    "complete", "ok"}
    assert rows[2025]["pool"] == pytest.approx(39.932) and rows[2025]["share"] == pytest.approx(39.932 / 177.0, abs=1e-6)
    assert rows[2025]["ok"] is True and rows[2026]["ok"] is None and rows[2026]["complete"] is False
    inv = _inv(d, "dps_history")
    assert inv["ok"] and inv["title"] == P.HISTORY_TITLES["cap"] and "потолка политики" in inv["detail"]
    assert P._dividend_problems(d) == []
    gate = next(g for g in d["checks"]["gates"] if g["name"] == "payout_cap")
    assert gate["title"] == P.FORM_GATE_TITLES["payout_cap"] and gate["corridor"]["value"] == 0.30
    form = [g["name"] for g in d["checks"]["gates"] if g["name"] in P.FORM_GATE_TITLES]
    assert form == ["payout_cap"] and "потолок" in gate["corridor"]["text"]
    over = copy.deepcopy(d)
    over["dividends"]["cap_check"][1]["ok"] = False
    assert any("cap_check" in p for p in P._dividend_problems(over))
    extra = copy.deepcopy(d)
    extra["dividends"]["formula_check"] = [{"year": 2025, "ok": True}]
    assert any("formula_check" in p for p in P._dividend_problems(extra))
    off = book.with_overrides({HISTORY: "none"})
    _, none = _release(off)
    assert none["dividends"]["formula_check"] == [] and "cap_check" not in none["dividends"]
    assert none["dividends"]["policy"]["history_test"] == "none" and "cap" not in none["dividends"]["policy"]
    assert _inv(none, "dps_history")["title"] == P.HISTORY_TITLES["none"] and P._dividend_problems(none) == []
    assert not [g for g in none["checks"]["gates"] if g["name"] == "payout_cap"]


def test_estimated_capital_anchor_reaches_the_release():
    """Норматив якоря стоит оценкой: поле `capital.anchor.estimated`, подпись источника оценки и флаг
    `capital_estimated` — в конце списка, только поднятым; без оценки состав флагов прежний."""
    book = plain_book((HISTORY,))
    est = _facts("capital", lambda c: c["n1_1_bank"].update(estimated=True))
    _, d = _release(book, est)
    anchor = d["capital"]["anchor"]
    words = book.label("capital.anchor_src_estimated", date="30.06.2026")
    assert anchor["estimated"] is True and anchor["src"] == words != book.label("capital.anchor_src", date="30.06.2026")
    flags = d["checks"]["flags"]
    assert [f["name"] for f in flags] == list(P.FLAG_TITLES) + ["deal_pending", "capital_estimated"]
    assert flags[-1] == {"name": "capital_estimated", "title": P.RAISED_FLAG_TITLES["capital_estimated"],
                         "raised": True, "detail": words}
    _, base = _release(book)
    assert "estimated" not in base["capital"]["anchor"]
    assert base["capital"]["anchor"]["src"] == book.label("capital.anchor_src", date="30.06.2026")
    assert [f["name"] for f in base["checks"]["flags"]] == list(P.FLAG_TITLES) + ["deal_pending"]
    # слоты формы Т: второй норматив группы — в слоте `n1_1_bank`; нормативов банка соло в фактах нет
    assert base["capital"]["observed"]["n1_1"] == t_facts().need("capital", "n1_1_bank.value")
    assert base["capital"]["observed"]["n1_0"] is None and base["capital"]["observed"]["n1_2"] is None
    assert "n10_bank" not in base["capital"]["anchor"]
    assert base["capital"]["titles"]["n11"] == book.label("capital.n11")


def test_roe_of_the_issuer_stands_next_to_the_roe_of_the_release():
    """`history.ltm.roe_issuer`: операционная прибыль четырёх кварталов по якорь к среднему операционного
    капитала пяти концов кварталов — точные значения, а где их ещё нет — напечатанные; подпись — из книги. Нет
    любого из девяти чисел — узла нет."""
    book, facts = plain_book((HISTORY,)), t_facts()
    _, d = _release(book)
    q = lambda p, k: facts.need("mgmt_quarterly", f"quarters.{p}.{k}")         # noqa: E731
    profit = q("2025Q3", "op_np_exact") + q("2025Q4", "op_np_exact") + q("2026Q1", "op_np_exact") + q("2026Q2", "op_np")
    equity = (q("2025Q2", "op_equity") + sum(q(p, "op_equity_exact") for p in ("2025Q3", "2025Q4", "2026Q1", "2026Q2"))) / 5
    ltm = d["history"]["ltm"]
    assert ltm["roe_issuer"] == {"value": pytest.approx(profit / equity, abs=1e-6), "as_of": "2026-06-30",
                                 "label": book.label("basis.roe_issuer")}
    assert abs(ltm["roe_issuer"]["value"] - ltm["roe"]) > 1e-3               # два разных отношения
    assert q("2025Q3", "op_equity") != q("2025Q3", "op_equity_exact")         # точное значение — первым
    hole = _facts("mgmt_quarterly", lambda m: m["quarters"]["2025Q2"].pop("op_equity"))
    assert "roe_issuer" not in _release(book, hole)[1]["history"]["ltm"]
    bare = dataclasses.replace(facts, files={k: v for k, v in facts.files.items() if k != "mgmt_quarterly"})
    assert "roe_issuer" not in _release(book, bare)[1]["history"]["ltm"]


def test_pending_deal_of_the_calendar_raises_the_flag():
    """Событие календаря фактов вида `deal` с `in_book: false` — флаг `deal_pending` с названием и примечанием
    события, в конце списка и только поднятым; сделка, уже учтённая книгой, и календарь без сделок флага не дают."""
    book = plain_book((HISTORY,))
    _, d = _release(book)
    flag = d["checks"]["flags"][-1]
    event = next(e for e in t_facts().files["calendar"]["events"] if e["kind"] == "deal")
    assert flag == {"name": "deal_pending", "title": P.RAISED_FLAG_TITLES["deal_pending"], "raised": True,
                    "detail": f"{event['title']}: {event['note']}"}
    in_book = _facts("calendar", lambda c: [e.update(in_book=True) for e in c["events"] if e["kind"] == "deal"])
    assert [f["name"] for f in _release(book, in_book)[1]["checks"]["flags"]] == list(P.FLAG_TITLES)
    no_deal = _facts("calendar", lambda c: c.update(events=[e for e in c["events"] if e["kind"] != "deal"]))
    assert [f["name"] for f in _release(book, no_deal)[1]["checks"]["flags"]] == list(P.FLAG_TITLES)
