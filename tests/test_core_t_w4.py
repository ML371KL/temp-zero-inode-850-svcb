"""Связка полосы, печатаемая маржа после фазы роста, гейты знака и обратный расчёт — тесты на фикстуре
`tests/fixtures/core_t`.

Проверки — тождества и закрытые формулы, выведенные из книги, фактов и рядов клетки независимо от кода ядра
(`tests/support_core_t4.py`; те же проверки зовёт мутационный набор): ось вида `bundle` — приращение к значению
книги, которое складывается со сдвигом оси вида `shift` на том же пути (М§10); печатаемая маржа модальной клетки
и гейт `nim_lt`; гейты знака `volume_sign` и `stress_sign` на построенных случаях; допуск гейта `payout_cap`
(М§14.2); закрытый квартал без своей строки истории (М§5.7.5); оба конца оси за проверяемым значением и корень
на краю отрезка поиска (М§11.2). Без своих ключей книги новых гейтов и узлов нет — и у книги первой формы.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest

from model import book_results as BR
from model import checks as C
from model.grid import NIM_LT, STRESS_SIGN, VOLUME_SIGN, LiveInputs, printed_nim_lt, run_grid
from tests import support_core_t3 as S
from tests import support_core_t4 as S4
from tests.support_core import fixture_book, fixture_facts, fixture_run
from tests.support_core_t import book_live, neutral_book, t_facts

tact = pytest.mark.tact                      # быстрые тесты — в такте сервера; гейты знака на построенных
#                                              случаях (сетки) и поиск корня на полосе — только в CI


# ------------------------------------------------------------------ связка (М§10)


@tact
def test_bundle_value_is_the_book_plus_the_share_of_the_way_to_its_end():
    S4.check_bundle_values()


@tact
def test_bundle_is_an_increment_that_adds_to_the_shift_axis_on_the_same_path():
    S4.check_bundle_adds_to_shift()


@tact
def test_bundle_at_zero_returns_the_book_bit_for_bit():
    S4.check_bundle_zero_is_the_book()


@tact
def test_bundle_refuses_a_path_shared_with_a_value_axis_a_dict_axis_or_another_bundle():
    S4.check_bundle_refusals()


def test_bundle_prints_as_a_value_axis_on_its_first_path():
    S4.check_bundle_prints()


@tact
def test_band_draw_with_a_bundle_is_the_grid_of_the_hand_made_book():
    S4.check_band_draw_with_bundle()


# ------------------------------------------------------------------ печатаемая маржа и гейты (М§14.2)


@tact
def test_printed_margin_is_the_mean_management_nim_of_the_modal_cell():
    S4.check_nim_lt()


def test_volume_sign_is_a_gate_fed_by_the_sign_test():
    S4.check_volume_sign_gate()


def test_stress_sign_gate_on_three_constructed_cases():
    S4.check_stress_sign()


@tact
def test_payout_cap_compares_with_the_tolerance_of_equality():
    S4.check_payout_cap_tolerance()


def test_sign_numbers_are_counted_once_per_book(monkeypatch):
    """Число гейта знака — центральной книги: повторная проверка той же книги на другом прогоне, другой дате и
    цене новых сеток не считает; другие факты — другое число."""
    calls: list[str] = []
    volume, stress = C.volume_sign_test, C.stress_sign_test
    monkeypatch.setattr(C, "volume_sign_test", lambda *a, **k: calls.append("volume") or volume(*a, **k))
    monkeypatch.setattr(C, "stress_sign_test", lambda *a, **k: calls.append("stress") or stress(*a, **k))
    book = S.book_of(**{"checks__volume_sign": {"tol": 0.0123}, "checks__stress_sign": {"loss_step": 61.0, "tol": 0.5}})
    facts, live = t_facts(), book_live(book)
    first = [f for f in C.check_gates(run_grid(book, facts, live)) if f.name in S4.SIGN_GATES]
    assert sorted(calls) == ["stress", "volume"] and [f.name for f in first] == list(S4.SIGN_GATES)
    later = LiveInputs(valuation_date=live.valuation_date + timedelta(days=9),
                       prices={t: p * 1.1 for t, p in live.prices.items()},
                       price_dates=dict(live.price_dates), register=())
    again = [f for f in C.check_gates(run_grid(book, facts, later)) if f.name in S4.SIGN_GATES]
    assert len(calls) == 2 and [(f.fired, f.mass, f.message) for f in again] == [(f.fired, f.mass, f.message) for f in first]
    other = dataclasses.replace(facts, files=dict(facts.files))           # другой объект фактов — число своё
    C.check_gates(run_grid(book, other, live))
    assert sorted(calls) == ["stress", "stress", "volume", "volume"]


@tact
def test_gates_of_the_wave_need_their_keys():
    """Без ключей книги гейтов нет — у книги первой формы и у формы Т без ключей; с ключами они стоят после
    прежних гейтов формы, в порядке перечня."""
    first = fixture_book()
    assert all(first.opt(k) is None for k in (NIM_LT, VOLUME_SIGN, STRESS_SIGN))
    names = [f.name for f in C.check_gates(fixture_run())]
    assert not {"nim_lt", *S4.SIGN_GATES} & set(names) and printed_nim_lt(fixture_run()) is None
    assert C.sign_numbers(fixture_run()) == {"volume_sign": None, "stress_sign": None}
    book = neutral_book()
    assert book.opt(NIM_LT) is not None and all(book.opt(k) is None for k in (VOLUME_SIGN, STRESS_SIGN))
    keyed = S.grid_of(**{k.replace(".", "__"): v for k, v in S4.GATE_KEYS.items()})
    gates = [f.name for f in C.check_gates(keyed) if f.kind == "gate"]
    assert gates[-3:] == ["nim_lt", "volume_sign", "stress_sign"] and tuple(gates) == tuple(
        g for g in C.GATE_ORDER if g in gates)
    at = C.FORM_GATES.index("nim_lt")
    assert C.FORM_GATES[at:at + 3] == ("nim_lt", "volume_sign", "stress_sign")
    assert not set(S4.KEYLESS_GATES) - set(S4.SIGN_GATES) & set(gates)       # сторожа уровней — при своих ключах


def test_book_tables_carry_the_nodes_of_the_gates_only_with_their_keys():
    """Таблицы книги: без ключей узлов нет и узел теста знака прежний; с ключами — печатаемая маржа рядом с
    ключом цели, число гейта знака объёмных эффектов с допуском и узел знака стресса, согласованные с гейтами."""
    first = fixture_book()
    res = BR.book_results(first, fixture_facts(), slow=False)
    assert not {"nim_lt", "stress_sign"} & set(res) and "tol" not in res["sign_test"]
    keyed = S.book_of(**{k.replace(".", "__"): v for k, v in S4.GATE_KEYS.items()})
    res = BR.book_results(keyed, t_facts(), slow=False)
    gates = [c["name"] for c in res["checks"] if c["kind"] == "gate"]
    assert gates[-3:] == ["nim_lt", "volume_sign", "stress_sign"]
    assert res["nim_lt"]["key"] == keyed.get("nii.nim_lt_target_mgmt") and res["nim_lt"]["target"] == 0.1076
    assert res["nim_lt"]["cell"] == res["central_cell"]["cell"]
    assert res["sign_test"]["tol"] == 0.0 and res["stress_sign"]["loss"]["step"] == 60.0
    by = {c["name"]: c for c in res["checks"]}
    assert by["volume_sign"]["fired"] is (not res["sign_test"]["ok"])
    assert by["stress_sign"]["fired"] is (not res["stress_sign"]["ok"])
    assert by["stress_sign"]["mass"] == pytest.approx(res["stress_sign"]["mass"], abs=1e-12)
    text = BR.render_run_output(BR.json.loads(BR.json.dumps(res, default=BR._default)), keyed)
    assert "печатаемая маржа после фазы роста" in text and "знак стресса" in text and "C/I" in text


# ------------------------------------------------------------------ дивиденды и обратный расчёт


@tact
def test_closed_quarter_without_its_own_history_row_gives_zero():
    S4.check_covered_quarter()


@tact
def test_both_ends_of_the_band_axis_follow_the_tested_value():
    S4.check_reverse_axis_follows()


@tact
def test_edge_rule_and_printed_margin_of_the_row_of_the_nim_target():
    S4.check_edge_rule_and_printed_margin()


def test_root_on_the_edge_of_the_search_segment_is_unreachable():
    S4.check_edge_root_is_unreachable()


# ------------------------------------------------------------------ схема и подписи книги


@tact
def test_schema_of_the_keys_of_the_wave():
    """Форма новых ключей (М прил. A): объекты гейтов — со всеми полями и в своих границах; подписи базы суммы
    дивиденда — только парой; подписи строк «цены правила» — только трёх замыканий; ключи — в перечне схемы."""
    from model.book_schema import KEYS
    for key in ("checks.nim_lt.target", "checks.nim_lt.tolerance", "checks.nim_lt.from_year", "checks.volume_sign.tol",
                "checks.stress_sign.loss_step", "checks.stress_sign.tol", "checks.payout_cap.tolerance",
                "valuation.reverse_dcf.axis_follow", "meta.labels.rule_price.unconstrained",
                "meta.labels.basis.dividend_issued", "meta.labels.terms.<term>"):
        assert key in KEYS, key
    S4.refused(lambda: S.book_of(**{"checks__nim_lt": {"target": 0.1, "tolerance": 0.001}}), "checks.nim_lt.from_year")
    S4.refused(lambda: S.book_of(**{"checks__nim_lt": {"target": 0.1, "tolerance": -0.001, "from_year": 2030}}),
               "checks.nim_lt.tolerance")
    S4.refused(lambda: S.book_of(**{"checks__volume_sign": {"tol": -1.0}}), "checks.volume_sign.tol")
    S4.refused(lambda: S.book_of(**{"checks__volume_sign": {"tol": 0.0, "step": 1}}), "незнакомый ключ")
    S4.refused(lambda: S.book_of(**{"checks__stress_sign": {"loss_step": 60.0}}), "checks.stress_sign.tol")
    S4.refused(lambda: S.book_of(**{"checks__payout_cap": {"tolerance": 1.5}}), "checks.payout_cap.tolerance")
    labels = S.book_of().get("meta.labels")
    one = {k: v for k, v in labels["basis"].items() if k != "dividend_outstanding"}
    S4.refused(lambda: S.book_of(**{"meta__labels__basis": one}), "только парой")
    S4.refused(lambda: S.book_of(**{"meta__labels__rule_price": {"free": "Свободный рост"}}), "незнакомый ключ")
    none = {k: v for k, v in labels["basis"].items() if not k.startswith("dividend_")}
    bare = S.book_of(**{"meta__labels__basis": none, "meta__labels__rule_price": {}})
    assert bare.label_or("rule_price.unconstrained", "слово кода") == "слово кода"
    assert bare.label_or("basis.profit", "слово кода") == labels["basis"]["profit"]


@tact
def test_release_takes_the_rule_price_from_the_book_tables_and_never_counts_it(monkeypatch):
    """«Цена правила» с медианами считается только в таблицах книги: сборка выпуска берёт таблицу из
    `results.json` своей версии книги и полосу под неё не пересчитывает (М§14.5)."""
    from model import payload as P
    from model import uncertainty as U
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained

    def forbidden(*_a, **_k):
        raise AssertionError("сборка выпуска пересчитывает «цену правила»")

    monkeypatch.setattr(BR, "rule_price", forbidden)
    monkeypatch.setattr(BR, "book_results", forbidden)
    bands: list[int] = []
    band = U.band
    monkeypatch.setattr(U, "band", lambda *a, **k: bands.append(1) or band(*a, **k))
    book, facts = neutral_book(), t_facts()
    table = {"book_version": str(book.get("meta.version")), "rule_price": {"rows": [
        {"key": k, "title": BR.RULE_TITLES[k], "point": 300.0 + i, "median": 290.0 + i, "capital_gap_mass": 0.0,
         "current": k == "dividend_first"} for i, k in enumerate(BR.RULE_TITLES)]}}
    expl = explained(C.check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE, results=table)
    rows = P.build_payload(rel)["capital"]["rule_price"]["rows"]
    assert [(r["key"], r["point"], r["median"]) for r in rows] == [
        (k, 300.0 + i, 290.0 + i) for i, k in enumerate(BR.RULE_TITLES)]
    assert rows[0]["title"] == book.label("rule_price.unconstrained") and len(bands) == 1     # одна полоса — заголовка
    assert not hasattr(P, "rule_price") and "book_results" not in P.make_release.__code__.co_names
