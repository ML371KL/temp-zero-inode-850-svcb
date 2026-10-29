"""Выпуск при росте, ограниченном капиталом (фикстура `tests/fixtures/core_t`): узлы панели (П§2, §7 п. 15).

`capital.requirement` — нормативы смеси против требования с глиссадой; `capital.growth` — потенциальный и
фактический рост кредитных книг, доля урезанного, λ по кварталам; `capital.rule_price` — «цена правила» из таблиц
книги; `paths.fade` — путь ROE и роста капитала к терминалу; `history.three_profits` — мост «вся прибыль →
акционерам → операционная» из фактов; `fair_value.bank_first_line.rub_per_1pp_buffer` — чувствительность к запасу
капитала; флаги клеток и гейты роста. Выпуск книги без этих ключей узлов панели не несёт.
"""

from __future__ import annotations

import copy
import functools

import pytest

from model import book_results as BR
from model import payload as P
from model import uncertainty as U
from model.book import book_from_dict
from model.checks import FORM_GATES, check_gates
from model.grid import run_grid, sensitivity_overrides
from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained, sensitivity_rows
from tests.support_core_t import book_live, neutral_book, plain_book, plain_dict, t_dict, t_facts
from tests.support_core_t4 import KEYLESS_GATES

tact = pytest.mark.tact                      # быстрые тесты — в такте сервера; пересчёт полос — только в CI

GC = "capital.growth_constraint"
HISTORY = "dividends.policy.history_test"    # тест истории вида `cap`: формула «до копейки» читает поля первой формы
# Контракт П§7 п. 10 на форме Т: норматив смеси расходится с ожиданием нормативов клеток чуть больше допуска —
# находка прежних волн (решение за ведущим); к узлам панели не относится.
KNOWN = ("capital.mix.n20", "нарушены инварианты: payload_contract")


def _release(book, results=None):
    facts = t_facts()
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE, results=results)
    return rel, P.build_payload(rel)


@functools.lru_cache(maxsize=None)
def _full():
    """Быстрый выпуск полной книги фикстуры и таблица «цены правила» к нему (без медиан)."""
    book = neutral_book()
    run = run_grid(book, t_facts())
    table = {"book_version": str(book.get("meta.version")),
             "rule_price": BR.rule_price(book, t_facts(), run.ctx.live, run)}
    return _release(book, table) + (table,)


def _mix(rel) -> dict:
    run, lam = rel.run, rel.run.lam
    return {c.key: lam * run.layers["analytical"].prob[c.key] + (1 - lam) * run.layers["macro_neutral"].prob[c.key]
            for c in run.cells}


def _unknown(problems) -> list[str]:
    return [p for p in problems if not p.startswith(KNOWN)]


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_release_prints_the_ratios_against_the_glided_requirement():
    """`capital.requirement`: по первым кварталам сетки — нормативы смеси, Н20.1 с прибылью периода и требование
    с глиссадой и без неё (ожидания смеси заголовка); по сценариям и на концы лет — требование с глиссадой."""
    rel, d, _ = _full()
    assert not _unknown(contract(d))
    run, p = rel.run, _mix(rel)
    req = d["capital"]["requirement"]
    tl = run.ctx.timeline
    assert req["periods"] == [tl.period(q) for q in range(1, P.QUARTERS_SHOWN + 1)]
    gr = rel.book.get(GC)
    assert (req["lookahead_quarters"], req["glide_pp_per_quarter"]) == (gr["lookahead_quarters"], gr["glide_pp_per_quarter"])
    e = lambda name, q: sum(p[c.key] * c.quarters[name][q] for c in run.cells)  # noqa: E731
    for i, q in enumerate(range(1, P.QUARTERS_SHOWN + 1)):
        for name in ("req20_glide", "req11_glide", "req20", "req11"):
            assert req["mix"][name][i] == pytest.approx(e(name, q), abs=1e-6), (name, q)
        assert req["mix"]["req20_glide"][i] >= req["mix"]["req20"][i]
        # норматив смеси — в определении движка: E[K]/E[RWA] плюс ожидание аддитивного слагаемого клеток
        k = sum(p[c.key] * (c.quarters["k11"][q] + max(c.quarters["e_unaudited"][q], 0.0)) for c in run.cells)
        add = sum(p[c.key] * (c.quarters["n11_star"][q] - (c.quarters["k11"][q] + max(c.quarters["e_unaudited"][q], 0.0))
                              / c.quarters["rwa"][q]) for c in run.cells)
        assert req["mix"]["n11_star"][i] == pytest.approx(k / e("rwa", q) + add, abs=1e-6), q
        assert req["mix"]["n11_star"][i] >= req["mix"]["n11"][i]
        assert req["mix"]["n20"][i] == d["paths"]["quarters"][i]["n20"]
    for s in run.ctx.prep.scenarios:
        cell = run.cell("N", "norm", s)
        assert req["by_scenario"][s]["req20_glide"] == pytest.approx(
            [cell.quarters["req20_glide"][q] for q in range(1, P.QUARTERS_SHOWN + 1)], abs=1e-6)
    years = d["capital"]["years"]
    ends = [tl.index(f"{y}Q4") for y in years]
    assert req["years_mix"]["req11_glide"] == pytest.approx([e("req11_glide", q) for q in ends], abs=1e-6)
    assert len(req["years_mix"]["req20_glide"]) == len(years)


@tact
def test_release_prints_the_growth_the_capital_allows():
    """`capital.growth`: рост суммы кредитных книг смеси — потенциальный и фактический (год якоря — к факту конца
    прошлого года), доля урезанного, навёрстанное, наименьшая λ года, вероятность клеток с урезанным ростом;
    по сценариям — под весами «свой взгляд»; флаги клеток несут `growth_cut`."""
    rel, d, _ = _full()
    run, p = rel.run, _mix(rel)
    g = d["capital"]["growth"]
    tl = run.ctx.timeline
    years = g["years"]
    assert years == d["capital"]["years"] == list(run.cells[0].years)
    gr = rel.book.get(GC)
    assert (g["order"], g["min_growth_scale"], g["catch_up_rate"]) == (gr["order"], gr["min_growth_scale"], gr["catch_up_rate"])
    e = lambda name, q, prob=p: sum(prob[c.key] * c.quarters[name][q] for c in run.cells)  # noqa: E731
    base = t_facts().need("balance", f"history.{years[0] - 1}Q4.loans")
    p_an = run.layers["analytical"].prob
    for i, y in enumerate(years):
        end, prev = tl.index(f"{y}Q4"), tl.index(f"{y - 1}Q4")
        b_act, b_pot = (e("loans", prev), e("loans_potential", prev)) if prev >= 0 else (base, base)
        assert g["potential"][i] == pytest.approx(e("loans_potential", end) / b_pot - 1, abs=1e-6), y
        assert g["actual"][i] == pytest.approx(e("loans", end) / b_act - 1, abs=1e-6), y
        assert g["cut_share"][i] == pytest.approx(1 - e("loans", end) / e("loans_potential", end), abs=1e-6), y
        qs = [q for q in tl.quarters_of_year(y) if q >= 1]
        assert g["catch_up"][i] == pytest.approx(sum(e("catch_up", q) for q in qs), abs=0.006), y
        assert g["lam_min"][i] == pytest.approx(min(e("lam", q) for q in qs), abs=1e-6), y
        cut = sum(p_an[c.key] for c in run.cells if c.growth["lam_min"][i] < 1 - 1e-12)
        assert g["p_cut"][i] == pytest.approx(cut, abs=1e-6), y
        assert g["actual"][i] <= g["potential"][i] + 0.2 and 0 <= g["cut_share"][i] < 1
    assert max(g["cut_share"]) > 0.05 and max(g["p_cut"]) > 0.5 and sum(g["catch_up"]) > 0
    assert g["quarters"]["periods"] == d["capital"]["requirement"]["periods"]
    assert g["quarters"]["lam"] == pytest.approx([e("lam", q) for q in range(1, P.QUARTERS_SHOWN + 1)], abs=1e-6)
    for s in run.ctx.prep.scenarios:
        cells = [c for c in run.cells if c.scenario == s]
        mass = sum(p_an[c.key] for c in cells)
        es = lambda name, q: sum(p_an[c.key] * c.quarters[name][q] for c in cells) / mass  # noqa: E731
        q = tl.index(f"{years[2]}Q4")
        assert g["by_scenario"][s]["cut_share"][2] == pytest.approx(1 - es("loans", q) / es("loans_potential", q), abs=1e-6)
        assert g["by_scenario"][s]["actual"][2] == pytest.approx(
            es("loans", q) / es("loans", tl.index(f"{years[1]}Q4")) - 1, abs=1e-6)
    assert g["by_scenario"]["strict"]["cut_share"][3] > g["by_scenario"]["schedule"]["cut_share"][3]
    flags = {f for c in d["grid"]["cells"] for f in c["flags"]}
    assert "growth_cut" in flags and "growth_solver" not in flags
    for cell, c in zip(d["grid"]["cells"], run.cells):
        assert cell["flags"] == sorted(c.flags)


@tact
def test_gates_of_the_form_reach_the_release_with_their_corridors():
    """Гейты второй формы — в выпуске после общих, с заголовком и коридором книги; сообщения — словами."""
    rel, d, _ = _full()
    gates = d["checks"]["gates"]
    on = tuple(g for g in FORM_GATES if g not in KEYLESS_GATES)   # включены ключами фикстуры; прочие — нет
    assert tuple(g["name"] for g in gates[-len(on):]) == on
    by = {g["name"]: g for g in gates}
    book = rel.book
    assert by["growth_cut"]["corridor"]["value"] == book.get("checks.growth_cut")
    assert by["step_dividend"]["corridor"]["value"] == book.get("checks.step_dividend")
    assert by["cir_lt"]["corridor"]["value"] == book.get("checks.cir_lt")
    assert by["wholesale_share"]["corridor"]["value"] == list(book.get("checks.wholesale_share"))
    assert book.label("terms.lt_level") in by["cir_lt"]["corridor"]["text"]
    assert by["nim_lt"]["corridor"]["value"] == book.get("checks.nim_lt")
    for name in on:
        assert by[name]["title"] == P.gate_title(book, name) and by[name]["message"]
        assert by[name]["corridor"]["text"] and "{" not in by[name]["title"] + by[name]["corridor"]["text"]
    assert by["growth_cut"]["fired"] and by["growth_cut"]["cells"] == len(by["growth_cut"]["cell_list"]) or \
        by["growth_cut"]["cells"] > P.CELL_LIST_MAX
    data = t_dict()
    del data["checks"]["step_dividend"]                     # ключа допуска нет — гейт сравнивает только срез
    assert P._corridor(book_from_dict(data, facts=t_facts()), "step_dividend")["value"] is None


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_release_without_the_rule_has_no_growth_nodes():
    """Книга без ограничения роста: узлов требования, роста и «цены правила» нет, гейтов роста нет; путь к
    терминалу печатается у любой книги."""
    _, d = _release(plain_book((HISTORY,)))
    cap = d["capital"]
    assert not {"requirement", "growth", "rule_price"} & set(cap)
    assert not {"growth_cut", "step_dividend", "cir_lt", "wholesale_share"} & {g["name"] for g in d["checks"]["gates"]}
    assert "rub_per_1pp_buffer" not in d["fair_value"]["bank_first_line"]
    assert "fade" in d["paths"] and not {f for c in d["grid"]["cells"] for f in c["flags"]} & {"growth_cut", "growth_solver"}
    off = neutral_book().with_overrides({f"{GC}.enabled": False})
    _, d2 = _release(off)
    assert not {"requirement", "growth"} & set(d2["capital"])          # выключатель снимает узлы механизма


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_rule_price_node_is_read_from_the_tables_of_the_book():
    """`capital.rule_price` — таблица `rule_price` из таблиц книги: сборка выпуска её не пересчитывает; таблица
    другой версии книги, без строки замыкания книги или у книги без объекта ограничения роста — узла нет."""
    rel, d, table = _full()
    book = rel.book
    node = d["capital"]["rule_price"]
    assert [r["key"] for r in node["rows"]] == ["unconstrained", "dividend_first", "growth_first"]
    assert [r["current"] for r in node["rows"]] == [False, True, False]
    for row, src in zip(node["rows"], table["rule_price"]["rows"]):
        assert row["point"] == pytest.approx(src["point"], abs=0.005) and row["median"] is None
        assert row["capital_gap_mass"] == pytest.approx(src["capital_gap_mass"], abs=1e-6) and row["title"] == src["title"]
        assert set(row) == {"key", "title", "point", "median", "capital_gap_mass", "current"}
    assert P.rule_price_table(book, {**table, "book_version": "0.9"}) is None
    assert P.rule_price_table(book, {"book_version": table["book_version"]}) is None
    twice = copy.deepcopy(table)
    twice["rule_price"]["rows"][0]["current"] = True
    assert P.rule_price_table(book, twice) is None
    assert P.rule_price_table(plain_book(), table) is not None        # объект есть и у выключенного правила
    bare = plain_dict()
    del bare["capital"]["growth_constraint"]
    bare["valuation"]["uncertainty"]["axes"] = [a for a in bare["valuation"]["uncertainty"]["axes"]
                                                if not any(str(x).startswith(GC) for x in a["paths"])]
    assert P.rule_price_table(book_from_dict(bare, facts=t_facts()), table) is None
    # контракт: замыкание книги — ровно в одной строке
    broken = copy.deepcopy(d)
    broken["capital"]["rule_price"]["rows"][1]["current"] = False
    assert any("rule_price" in p for p in P._panel_problems(broken))
    _, plain = _release(neutral_book())                                # таблиц книги фикстуры в репозитории нет
    assert "rule_price" not in plain["capital"]


@tact
def test_contract_checks_the_lengths_of_the_panel_nodes():
    """П§7 п. 15: массивы `capital.requirement` и `capital.growth` — длины своих осей."""
    _, d, _ = _full()
    assert P._panel_problems(d) == []
    for path, word in ((("requirement", "mix", "n11_star"), "requirement"), (("growth", "p_cut"), "growth"),
                       (("growth", "quarters", "lam"), "growth.quarters"),
                       (("requirement", "years_mix", "req20_glide"), "years_mix")):
        broken = copy.deepcopy(d)
        node = broken["capital"]
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = node[path[-1]][:-1]
        assert any(word in p for p in P._panel_problems(broken)), path
        assert any(word in p for p in contract(broken))


@tact
def test_fade_path_goes_from_the_explicit_years_to_the_terminal():
    """`paths.fade`: ROE и рост капитала конца года по годам годового пути, ожидание стоимости капитала года,
    терминал — ROE до и после угасания, стоимость капитала и рост (смесь заголовка)."""
    rel, d, _ = _full()
    run, p = rel.run, _mix(rel)
    fade, annual = d["paths"]["fade"], d["paths"]["annual"]
    assert fade["years"] == [r["year"] for r in annual] and fade["roe"] == [r["roe"] for r in annual]
    tl, clock = run.ctx.timeline, run.ctx.clock
    bv = lambda q: sum(p[c.key] * c.quarters["bv"][q] for c in run.cells)  # noqa: E731
    hist = t_facts().need("balance", f"history.{fade['years'][0] - 1}Q4.bv_common")
    for i, y in enumerate(fade["years"]):
        end, prev = tl.index(f"{y}Q4"), tl.index(f"{y - 1}Q4")
        assert fade["bv_growth"][i] == pytest.approx(bv(end) / (bv(prev) if prev >= 0 else hist) - 1, abs=1e-6), y
        qs = tl.quarters_of_year(y)
        if qs[0] > clock.q0:                       # полный год после даты оценки: годовая ставка — произведение кварталов
            k = 0.0
            for c in run.cells:
                rate = 1.0
                for q in qs:
                    rate *= 1 + run.ctx.discounts[c.world].k[q]
                k += p[c.key] * (rate - 1)
            assert fade["k"][i] == pytest.approx(k, abs=1e-6), y
    assert all(0.05 < v < 0.5 for v in fade["k"])
    term = d["paths"]["terminal"]
    assert (fade["roe_t"], fade["k_t"], fade["g_t"], fade["fade"]) == (term["roe_t"], term["k_t"], term["g_t"], term["fade"])
    assert fade["roe_t_raw"] == pytest.approx(sum(p[c.key] * c.roe_t_raw for c in run.cells), abs=1e-6)
    assert fade["fade"] == rel.book.get("valuation.terminal.fade")
    assert set(fade) == {"years", "roe", "bv_growth", "k", "roe_t_raw", "roe_t", "k_t", "g_t", "fade"}


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_three_profits_bridge_comes_from_the_reported_rows_of_the_facts():
    """`history.three_profits`: вся прибыль → акционерам → операционная, по отчётным кварталам с узлами
    отчётных строк и блока исключённого; квартал без них в мост не входит; тождество — в контракте."""
    _, d, _ = _full()
    rows = d["history"]["three_profits"]
    pnl = t_facts().file("pnl_quarterly")["quarters"]
    with_block = sorted(p for p, q in pnl.items() if "reported" in q and "investment_block" in q)
    assert [r["period"] for r in rows] == with_block and 0 < len(rows) < len(pnl)
    for r in rows:
        q = pnl[r["period"]]
        assert r["ni_total"] == q["reported"]["ni"]["v"] and r["ni_nci"] == q["reported"]["ni_nci"]["v"]
        assert r["ni_shareholders"] == q["reported"]["ni_shareholders"]["v"]
        assert r["stake_effect"] == q["investment_block"]["adj_stake_sh"]["v"]
        assert r["debt_interest_effect"] == q["investment_block"]["adj_interest_sh"]["v"]
        assert r["ni_operating"] == q["ni_shareholders"]["v"]
        assert r["ni_operating"] == pytest.approx(r["ni_shareholders"] - r["stake_effect"] - r["debt_interest_effect"], abs=0.011)
        assert r["ni_total"] == pytest.approx(r["ni_shareholders"] + r["ni_nci"], abs=0.011)
    assert any(r["stake_effect"] for r in rows) and any(not r["stake_effect"] for r in rows)
    broken = copy.deepcopy(d)
    broken["history"]["three_profits"][-1]["stake_effect"] += 1.0
    assert any("three_profits" in p for p in P._panel_problems(broken))
    # факты без отчётных строк — узла нет
    import dataclasses
    facts = t_facts()
    data = copy.deepcopy(facts.files["pnl_quarterly"])
    for q in data["quarters"].values():
        q.pop("reported", None)
    bare = dataclasses.replace(facts, files={**facts.files, "pnl_quarterly": data})
    book = neutral_book()
    expl = explained(check_gates(run_grid(book, bare), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=bare, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    assert "three_profits" not in P.build_payload(rel)["history"]


def test_buffer_sensitivity_is_the_median_shift_per_one_point_of_the_buffer():
    """`rub_per_1pp_buffer`: сдвиг медианы оценщиком срединных прогонов при сдвиге запаса менеджмента обоих
    нормативов на `buffer_pp`, приведённый к 1 п.п.; только при ключе книги."""
    book, facts = neutral_book(), t_facts()
    live = book_live(book)
    x, rows = sensitivity_rows(book, facts, live, 6, workers=1)
    step = float(book.get("valuation.sensitivities.buffer_pp"))
    shifted = U.trial_book(x.book, sensitivity_overrides(x.book, "buffer"))
    other = x.rel.anchor.recompute(shifted)
    lam = x.run.lam
    expect = U.median_shift(x.rel.anchor.base.exact_centres(lam), other.exact_centres(lam), U.rank_window(x.book)) \
        * 0.01 / step
    row = next(r for r, grid_lam in zip(rows, P._lambda_grid(lam)) if abs(grid_lam - lam) < 1e-9)
    assert row["rub_per_1pp_buffer"] == pytest.approx(expect, abs=0.006) and row["rub_per_1pp_buffer"] < 0
    assert all("rub_per_1pp_buffer" in r for r in rows)
    assert "запас капитала" in P._buffer_words(book) and P._buffer_words(plain_book()) == ""
    fast = P._sens_at(P._Ctx(_full()[0]), lam)
    assert fast["rub_per_1pp_buffer"] is None and "rub_per_1pp_buffer" in fast
