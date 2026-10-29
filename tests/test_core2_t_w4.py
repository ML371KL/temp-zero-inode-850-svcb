"""Выпуск на форме Т: узлы гейтов знака и цели маржи, связка в строках суждений, подписи и база суммы дивиденда.

Быстрый выпуск на фикстуре `tests/fixtures/core_t` с ключами гейтов (`tests/support_core_t4.py::GATE_KEYS`) и
осью-связкой: числа гейтов знака стоят узлами `checks.volume_sign` и `checks.stress_sign` и согласованы с
гейтами; печатаемая маржа модальной клетки — рядом с ключом цели и в строке обратного расчёта по нему; строка
связки печатается по первому пути и несёт полные концы; узел требования называет норматив, который сравнивает
правило роста; словарь терминов собран из всех ключей книги; коэффициент дробления — число при любом виде узла
фактов. У книги первой формы ни одного из этих узлов нет (П§2, §7).
"""

from __future__ import annotations

import copy
import dataclasses
import functools

import pytest

from model import payload as P
from model import uncertainty as U
from model.checks import check_gates, sign_numbers
from model.grid import printed_nim_lt, run_grid
from model.reverse import NIM_PATH
from tests import support_core_t3 as S
from tests import support_core_t4 as S4
from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained, fast_release_payload
from tests.support_core_t import neutral_book, t_facts

tact = pytest.mark.tact
# Контракт П§7 п. 10 на фикстуре формы Т: норматив смеси расходится с ожиданием нормативов клеток чуть больше
# допуска — свойство фикстуры (у книги допуск задаёт её ключ); к узлам этой волны не относится.
KNOWN = ("capital.mix.n20", "нарушены инварианты: payload_contract")


def _unknown(problems) -> list[str]:
    return [p for p in problems if not p.startswith(KNOWN)]


def _release(book, facts=None):
    facts = facts or t_facts()
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    return rel, P.build_payload(rel)


@functools.lru_cache(maxsize=None)
def _keyed():
    """Быстрый выпуск фикстуры с ключами трёх гейтов и осью-связкой в полосе."""
    axes = S4.fixture_axes() + [S4.BUNDLE]
    book = S.book_of(**{k.replace(".", "__"): v for k, v in S4.GATE_KEYS.items()},
                     **{"valuation__uncertainty__axes": axes})
    return _release(book)


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_release_carries_the_numbers_of_the_sign_gates():
    """`checks.volume_sign` и `checks.stress_sign` — числа гейтов центральной книги; сработал гейт ⇔ узел не `ok`;
    контракт ловит рассогласование узла с гейтом."""
    rel, d = _keyed()
    assert _unknown(contract(d)) == []
    numbers = sign_numbers(rel.run)
    assert rel.volume_sign is numbers["volume_sign"] and rel.stress_sign is numbers["stress_sign"]
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    vs, ss = d["checks"]["volume_sign"], d["checks"]["stress_sign"]
    assert vs["d_point"] == pytest.approx(numbers["volume_sign"]["d_point"], abs=0.006)
    assert vs["point_free"] - vs["point"] == pytest.approx(vs["d_point"], abs=0.02) and vs["tol"] == 0.0
    assert set(vs["d_world"]) == {"N", "H", "M"} and vs["growth_constraint_off"] is True
    assert gates["volume_sign"]["fired"] is (not vs["ok"]) and gates["volume_sign"]["mass"] in (0.0, 1.0)
    assert ss["loss"]["step"] == 60.0 and len(ss["requirement"]["cells"]) == len(numbers["stress_sign"]["requirement"]["cells"])
    assert set(ss["requirement"]["cells"][0]) == {"world", "regime", "stricter", "looser", "d_profit"}
    assert ss["mass"] == pytest.approx(numbers["stress_sign"]["mass"], abs=1e-6) == gates["stress_sign"]["mass"]
    assert gates["stress_sign"]["fired"] is (not ss["ok"]) and ss["max_excess"] > 0.5
    assert gates["stress_sign"]["cells"] == len({(c["world"], c["regime"], c["stricter"]) for c in ss["requirement"]["cells"]})
    for name in ("nim_lt", "volume_sign", "stress_sign"):
        assert gates[name]["title"] == P.gate_title(rel.book, name) and gates[name]["corridor"]["text"]
        assert gates[name]["corridor"]["value"] == rel.book.get(f"checks.{name}") and gates[name]["message"]
    broken = copy.deepcopy(d)
    broken["checks"]["stress_sign"]["ok"] = not ss["ok"]
    assert any("checks.stress_sign" in p for p in P._panel_problems(broken))
    broken = copy.deepcopy(d)
    broken["checks"]["volume_sign"]["ok"] = not vs["ok"]
    assert any("checks.volume_sign" in p for p in P._panel_problems(broken))


@tact
def test_release_prints_the_margin_of_the_modal_cell_next_to_the_target_key():
    """`nii.transmission.nim_lt_printed` — печатаемая маржа модальной клетки рядом с ключом цели; строка
    обратного расчёта по ключу цели несёт её же на книге (при корне — пусто: быстрая сборка поисков не делает)."""
    rel, d = _keyed()
    tr = d["nii"]["transmission"]
    printed = printed_nim_lt(rel.run)
    node = tr["nim_lt_printed"]
    assert node["value"] == pytest.approx(printed["value"], abs=1e-6) and node["cell"] == printed["cell"]
    assert (node["target"], node["tolerance"], node["from_year"]) == (0.1076, 0.001, 2030)
    assert node["to_year"] == d["grid"]["years"][-1] and tr["nim_lt_target_mgmt"] == rel.book.get(NIM_PATH)
    assert abs(node["value"] - tr["nim_lt_target_mgmt"]) > 1e-4          # ключ цели и печатаемая маржа — два числа
    rows = d["reverse_dcf"]["rows"]
    row = next(r for r in rows if NIM_PATH in r["paths"])
    assert row["printed_book"] == pytest.approx(printed["value"], abs=1e-9) and row["printed_solved"] is None
    assert all("printed_book" not in r for r in rows if r is not row)


@tact
def test_bundle_row_of_the_judgements_prints_its_first_path_and_carries_the_ends():
    """Строка связки в суждениях: значение и концы — первого пути, полные концы — `ends`; у прочих строк поля
    нет; связка несёт вклад в полосу."""
    rel, d = _keyed()
    rows = d["judgements"]["rows"]
    row = next(r for r in rows if r["kind"] == U.BUNDLE)
    first = S4.BUNDLE["paths"][0]
    assert row["paths"] == S4.BUNDLE["paths"] and row["unit"] == "pct" and row["in_band"] is True
    assert (row["book"], row["low"], row["high"]) == (rel.book.get(first), S4.BUNDLE["low"][first], S4.BUNDLE["high"][first])
    assert row["ends"]["low"] == S4.BUNDLE["low"] and row["ends"]["high"] == S4.BUNDLE["high"]
    assert row["ends"]["book"] == {p: rel.book.get(p) for p in S4.BUNDLE["paths"]}
    assert all("ends" not in r for r in rows if r is not row)
    assert any(c["name"] == S4.BUNDLE["name"] for c in d["fair_value"]["headline"]["contributions"])


@tact
def test_requirement_node_names_the_ratio_the_growth_rule_compares():
    """`capital.requirement`: с требованием правило роста сравнивает второй норматив с прибылью периода —
    `compare`; отчётный подписан справочным — `notes`; годовой узел несёт норматив с прибылью периода."""
    rel, d = _keyed()
    req = d["capital"]["requirement"]
    assert req["compare"] == {"n20": "n20", "n11": "n11_star"} and set(req["compare"].values()) <= set(req["mix"])
    assert set(req["notes"]) == {"n11_star", "n11"} and "справочно" in req["notes"]["n11"]
    assert "прибылью периода" in req["notes"]["n11_star"]
    star, years = req["years_mix"]["n11_star"], d["capital"]["years"]
    assert len(star) == len(years) and all(v is not None for v in star)
    reported = d["capital"]["mix"]["n11"]
    assert all(a >= b for a, b in zip(star, reported)) and any(a > b + 1e-4 for a, b in zip(star, reported))
    run, lam = rel.run, rel.run.lam
    p = {c.key: lam * run.layers["analytical"].prob[c.key] + (1 - lam) * run.layers["macro_neutral"].prob[c.key]
         for c in run.cells}
    q = run.ctx.timeline.index(f"{years[-1]}Q4")
    cap = lambda c: c.quarters["k11"][q] + max(c.quarters["e_unaudited"][q], 0.0)  # noqa: E731
    k = sum(p[c.key] * cap(c) for c in run.cells) / sum(p[c.key] * c.quarters["rwa"][q] for c in run.cells)
    add = sum(p[c.key] * (c.quarters["n11_star"][q] - cap(c) / c.quarters["rwa"][q]) for c in run.cells)
    assert star[-1] == pytest.approx(k + add, abs=1.5e-6)
    broken = copy.deepcopy(d)
    broken["capital"]["requirement"]["compare"]["n11"] = "n11_period"
    assert any("capital.requirement.compare" in x for x in P._panel_problems(broken))


@tact
def test_terms_dictionary_is_collected_from_every_term_of_the_book():
    """`meta.terms` — все ключи `meta.labels.terms` книги и имя строки вне основного бизнеса; слово отношения
    расходов к доходам в заголовках гейтов — термин книги."""
    rel, d = _keyed()
    book = rel.book
    terms = dict(book.get("meta.labels.terms"))
    assert {"lt_level", "profit_short", "cir", "roe_lt", "stake"} <= set(terms)
    assert d["meta"]["terms"] == {**terms, "noncore": book.label("control.lines.noncore")}
    own = S.book_of(**{"meta__labels__terms": {**terms, "noncore": "строка пакета", "payout_word": "выплата"}})
    assert P._terms(own)["noncore"] == "строка пакета" and P._terms(own)["payout_word"] == "выплата"
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    assert gates["cir_range"]["title"] == "C/I года вне коридора" and "C/I года" in gates["cir_range"]["message"]
    assert "C/I" in gates["cir_range"]["corridor"]["text"] and "CIR" not in str(gates["cir_range"])
    S4.refused(lambda: S.book_of(**{"meta__labels__terms": {**terms, "Плохой ключ": "слово"}}), "ключ термина")
    S4.refused(lambda: S.book_of(**{"meta__labels__terms": {"lt_level": "после фазы роста"}}), "profit_short")
    S4.refused(lambda: S.book_of(**{"meta__labels__terms": {**terms, "roe_lt": "ROE {year}"}}), "поле подстановки")


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_split_factor_is_a_number_whatever_the_node_of_the_facts():
    """`meta.shares.corporate_actions[].factor` — число: узел фактов `{v, src}` в выпуск целиком не уходит;
    контракт сверяет тип."""
    def node(data: dict) -> None:
        data["corporate_actions"][0]["factor"] = {"v": 10.0, "src": "решение о дроблении, фикстура"}

    facts = S4.facts_changed("shares", node)
    rel, d = _release(neutral_book(), facts)
    action = d["meta"]["shares"]["corporate_actions"][0]
    assert action["factor"] == 10.0 and isinstance(action["factor"], float) and "src" not in str(action)
    assert not [p for p in P._format_problems(d) if "factor" in p]
    broken = copy.deepcopy(d)
    broken["meta"]["shares"]["corporate_actions"][0]["factor"] = {"v": 10.0, "src": "узел факта"}
    assert any("corporate_actions" in p and "factor" in p for p in P._format_problems(broken))
    broken["meta"]["shares"]["corporate_actions"][0]["factor"] = True
    assert any("factor" in p for p in P._format_problems(broken))


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_yield_for_twelve_months_needs_four_declared_quarters():
    """Дивдоходность за 12 месяцев при квартальном календаре — по окну четырёх кварталов прибыли, которое
    кончается самым поздним кварталом с решением; история решений короче окна — значения нет."""
    rel, d = _release(neutral_book())
    assert d["dividends"]["yield_ltm_periods"] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert d["dividends"]["yield_ltm"]["T"] == pytest.approx((3.6 + 4.5 + 4.6 + 4.7) / 330.0, abs=1e-6)
    x = P._Ctx(rel)
    periods, rows = P._declared_quarters(x)
    assert [r["period"] for r in rows] == periods

    def short(data: dict) -> None:
        data["history"] = [r for r in data["history"] if r["period"] == "2025Q4"]

    facts = S4.facts_changed("dividends", short)
    fresh = dataclasses.replace(rel, facts=facts)
    assert P._declared_quarters(P._Ctx(fresh)) is None and P._yield_ltm(P._Ctx(fresh)) == {"T": None}
    # закрытый квартал окна без своей строки покрыт решением более позднего квартала: в сумме — ноль

    def hole(data: dict) -> None:
        data["history"] = [r for r in data["history"] if r["period"] != "2025Q4"]

    holed = dataclasses.replace(rel, facts=S4.facts_changed("dividends", hole))
    periods, rows = P._declared_quarters(P._Ctx(holed))
    assert periods == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"] and [r["period"] for r in rows] == [
        "2025Q3", "2026Q1", "2026Q2"]
    assert P._yield_ltm(P._Ctx(holed))["T"] == pytest.approx((3.6 + 4.6 + 4.7) / 330.0, abs=1e-6)


@tact
def test_first_form_release_has_no_nodes_of_the_wave():
    """Книга первой формы без новых ключей: узлов гейтов, печатаемой маржи, базы суммы дивиденда и окна
    доходности нет; словарь терминов и заголовки гейтов — прежние."""
    rel, d = fast_release_payload(first_form=True)
    assert not {"volume_sign", "stress_sign"} & set(d["checks"])
    assert "nim_lt_printed" not in d["nii"]["transmission"] and "requirement" not in d["capital"]
    assert "amount_basis" not in d["dividends"] and "amount_basis" not in d["fair_value"]["bridge"]
    assert "yield_ltm_periods" not in d["dividends"]
    assert set(d["meta"]["terms"]) == {"lt_level", "profit_short", "noncore"}
    assert set(d["meta"]["basis_labels"]) == {"profit", "roe", "divisor"}
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    assert not {"nim_lt", "volume_sign", "stress_sign"} & set(gates)
    assert gates["cir_range"]["title"] == "CIR года вне коридора" and "CIR" in gates["cir_range"]["corridor"]["text"]
    assert all("printed_book" not in r for r in d["reverse_dcf"]["rows"])
    assert all("ends" not in r for r in d["judgements"]["rows"])
