# -*- coding: utf-8 -*-
"""Контрольная модель на фикстуре формы панели (tests/fixtures/core_t): ветвь с квартальным проходом
капитала (docs/MODEL.md §17) — квартальный календарь дивидендов (М§5.7), рост, ограниченный капиталом
(М§4.13), делитель N_div (М§8.4), связь с объёмом (М§4.7), премии роста траекториями, постоянные прочие
активы и множитель плотности режима (М§4.3, §4.11), тест истории вида cap (М§5.2).

* Свойства контрольной модели (метка tact; ядро не нужно): тождества, свойства М§4.13.4, границы
  дивиденда и формула избытка, правило закрытого квартала (и квартал, покрытый строкой истории более
  позднего квартала), состояние якоря, инвариант экс-даты, три замыкания «цены правила» подменой одного
  пути; гейт знака стресса, печатаемая маржа, мир-опора κ, уровни после фазы роста, гейт сверки с окном
  фактов и уровень C/I цели книги — свой счёт при ключах книги, подставленных тестом.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста): полная книга фикстуры — в
  допусках М§17, числа гейта знака объёмных эффектов и набор нарушивших клеток гейта знака стресса, мир-опора
  κ и уровни после фазы роста при подставленных ключах; проекция на годовой календарь — ключи формы панели
  на годовой ветви.

Отказ «не поддержано» на книге фикстуры — провал, не пропуск.
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import importlib
import json
import math

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core_t"
DROP = object()
HOME = ("H", "norm", "mid")                 # клетка для расчётов одной клетки (вход теста)
TIGHT = ("M", "downturn", "strict")         # клетка со связывающим капиталом (М§17)


def t_book() -> dict:
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8"))


def t_facts() -> dict:
    return cm.c_facts_bundle(FIXTURE / "facts")


def put(tree: dict, dotted: str, value) -> dict:
    """Копия дерева с подменой одного пути (DROP — ключ снят)."""
    out = copy.deepcopy(tree)
    cur = out
    *head, last = dotted.split(".")
    for part in head:
        cur = cur[part]
    if value is DROP:
        cur.pop(last, None)
    else:
        cur[last] = value
    return out


def one_cell(book: dict, facts: dict, key=HOME, **kw):
    ctx = cm.c_control_context(book, facts, **kw)
    return ctx, cm.c_cell_annual(ctx, *key)


@pytest.fixture(scope="module")
def inputs():
    return t_book(), t_facts()


@pytest.fixture(scope="module")
def control(inputs):
    book, facts = inputs
    try:
        return cm.c_control_run(book, facts)
    except cm.ControlUnsupported as exc:
        pytest.fail(f"контрольная модель не считает ветвь формы панели: {exc}")


def _quarters(cell: dict) -> list[dict]:
    return [x for r in cell["rows"] for x in r["quarters"]]


# ============================================================================ форма и тождества


@pytest.mark.tact
def test_form_of_the_panel_is_computed_without_refusal(control):
    """Один тикер, двенадцать книг прямыми узлами, квартальный календарь, ограничение роста, делитель
    «размещённые»: все клетки посчитаны, DDM = RI в каждой, вероятности слоёв в сумме 1."""
    ctx = control["ctx"]
    assert control["quarterly"] and control["growth_rule"]["order"] == cm.ORDER_DIV_FIRST
    assert ctx["A"]["direct_books"] and len(ctx["B"]["nii"]["books"]) == 12 and len(ctx["loans"]) == 6
    assert not ctx["fv"] and all(r["fvc"] == 0.0 for c in control["cells"] for r in c["rows"])
    assert control["divisor"] == pytest.approx(ctx["A"]["N_iss"], rel=1e-15) and control["divisor"] > control["shares_out"]
    assert len(control["cells"]) == 36
    for c in control["cells"]:
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"])), (c["world"], c["regime"], c["scenario"])
    for ly in control["layers"].values():
        assert abs(ly["prob_sum"] - 1.0) <= 1e-12


@pytest.mark.tact
def test_identities_and_quarter_pass_close_the_year(control):
    """Тождества капитала, баланса и PBT по годам; квартальный проход кончает год на тех же капитале,
    RWA и нормативе, что годовая строка; план года сошёлся; сумма решений квартала — дивиденд года."""
    A = control["ctx"]["A"]
    for c in control["cells"]:
        bv_prev = A["BV"]
        for r in c["rows"]:
            assert math.isclose(bv_prev + r["ci"] - r["div"], r["bv"], rel_tol=1e-9)
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            pbt = (r["nii"] - r["llp"] - r["fvc"] + r["fees"] + r["ins"] + r["misc"] + r["fvr"]
                   + r["noncore"] - r["opex"] + r["one_off"])
            assert math.isclose(pbt, r["pbt"], rel_tol=1e-12, abs_tol=1e-9)
            assert math.isclose(sum(r["ci_q"]), r["ci"], rel_tol=1e-9, abs_tol=1e-9)
            last = r["quarters"][-1]
            assert math.isclose(last["bv"], r["bv"], rel_tol=1e-8)
            assert math.isclose(last["rwa"], r["rwa"], rel_tol=1e-8)
            assert abs(last["n20"] - r["n20"]) <= 1e-8 and abs(last["n11"] - r["n11"]) <= 1e-8
            assert r["plan_gap"] <= cm.PLAN_TOL and r["plan_turns"] < cm.FIT_ITER
            assert math.isclose(sum(x["div"] for x in r["quarters"]), r["div"], rel_tol=1e-7, abs_tol=1e-7)
            assert math.isclose(sum(amt for _, amt in r["div_list"]), r["div"], rel_tol=1e-12, abs_tol=1e-12)
            bv_prev = r["bv"]


# ============================================================================ рост, ограниченный капиталом (М§4.13.4)


@pytest.mark.tact
def test_binding_norm_sits_on_the_glided_requirement(control):
    """Свойство 1: в квартале с λ_min < λ* < 1 норматив связывающего равен требованию с глиссадой в
    допуске tol, второй — не ниже req* − tol. Ограничение меряет Н20.1 с прибылью периода."""
    rule = control["growth_rule"]
    seen = 0
    for c in control["cells"]:
        for x in _quarters(c):
            assert rule["lam_min"] - 1e-12 <= x["lam"] <= 1.0
            if rule["lam_min"] < x["lam"] < 1.0:
                gaps = (x["n20"] - x["req20_glide"], x["n11_star"] - x["req11_glide"])
                assert abs(min(gaps)) <= rule["tol"], (c["world"], c["regime"], c["scenario"], x["q"], gaps)
                assert max(gaps) >= -rule["tol"]
                seen += 1
            assert x["n11_star"] >= x["n11"] - 1e-12      # прибыль периода возвращается, убыток — нет
    assert seen, "на фикстуре капитал ни разу не связал рост"
    tight = cm.c_cell_of(control, *TIGHT)
    assert any(x["lam"] < 1.0 for x in _quarters(tight)), "в клетке (M, downturn, strict) рост не урезан"


@pytest.mark.tact
def test_requirement_glides_to_the_known_steps(control):
    """Требование с глиссадой (М§4.13.1): req* = max по h = 0…H (r(min(q + h, Q)) − h × δ) — пересчёт
    формулой теста; ступень минимума снята: прирост за квартал не больше δ; на конце сетки req* = req."""
    ctx, rule = control["ctx"], control["growth_rule"]
    B, anchor, last = ctx["B"], ctx["anchor"], ctx["Q"]

    def plain(s, k):
        y, q = cm.c_qper(anchor, k)
        fl = lambda which: cm.c_bnum(B, f"capital.minimum.{which}") + sum(           # noqa: E731
            cm.c_traj_at(cm.c_bget(B, f"capital.reg_scenarios.{s}.{x}"), y, q) for x in ("conservation", "sifi", "ccyb"))
        return (max(cm.c_bnum(B, "dividends.policy.threshold"), fl("n20_0") + cm.c_bnum(B, "capital.mgmt_buffer.n20_0")),
                fl("n1_1") + cm.c_bnum(B, "capital.mgmt_buffer.n1_1"))

    for c in control["cells"][:9:4] + [cm.c_cell_of(control, *TIGHT)]:
        s = c["scenario"]
        qs = _quarters(c)
        for prev, x in zip([None] + qs, qs):
            for j, key in enumerate(("req20_glide", "req11_glide")):
                want = max(plain(s, min(x["q"] + h, last))[j] - h * rule["glide"] for h in range(rule["ahead"] + 1))
                assert x[key] == pytest.approx(want, abs=1e-12)
                assert x[key] >= plain(s, x["q"])[j] - 1e-15
                if prev is not None:
                    assert x[key] - prev[key] <= rule["glide"] + 1e-12
        assert qs[-1]["req20_glide"] == pytest.approx(qs[-1]["req20"], abs=1e-15)
        assert qs[-1]["req11_glide"] == pytest.approx(qs[-1]["req11"], abs=1e-15)


@pytest.mark.tact
def test_book_stays_under_the_potential_path(inputs, control):
    """Свойство 5: при любом κ книга не выше потенциального пути; при κ = 0 отношение книги к
    потенциальному пути не возрастает. Навёрстывание — только при λ* = 1."""
    for c in control["cells"]:
        for r in c["rows"]:
            for b, level in r["books_end"].items():
                assert level <= r["potential_end"][b] * (1.0 + 1e-12)
            for x in r["quarters"]:
                assert x["catch_up"] == 0.0 or x["lam"] == 1.0
                assert x["loans"] <= x["loans_potential"] * (1.0 + 1e-12)
    book, facts = inputs
    _, cell = one_cell(put(book, "capital.growth_constraint.catch_up_rate", 0.0), facts, TIGHT)
    ratio = {b: 1.0 for b in cell["rows"][0]["books_end"]}
    for r in cell["rows"]:
        assert r["catch_up"] == 0.0
        for b, level in r["books_end"].items():
            now = level / r["potential_end"][b]
            assert now <= ratio[b] + 1e-12
            ratio[b] = now
    assert min(ratio.values()) < 1.0


@pytest.mark.tact
def test_growth_share_does_not_rise_with_the_requirement(inputs):
    """Свойство 2: λ* не растёт при росте требования — в первом квартале, где пути двух книг расходятся
    (дальше доля зависит от уже урезанного уровня)."""
    book, facts = inputs
    _, base = one_cell(book, facts, TIGHT)
    _, hard = one_cell(put(book, "capital.mgmt_buffer", {"n20_0": 0.025, "n1_1": 0.025}), facts, TIGHT)
    for a, b in zip(_quarters(base), _quarters(hard)):
        if abs(a["lam"] - b["lam"]) > 1e-9:
            assert b["lam"] < a["lam"]
            break
    else:
        pytest.fail("рост требования не изменил долю прироста ни в одном квартале")
    assert hard["rows"][-1]["loans"] < base["rows"][-1]["loans"]


@pytest.mark.tact
def test_three_closures_of_capital_by_one_path(inputs, control):
    """Три замыкания «цены правила» (М§14.5) — подменой одного пути: выключатель возвращает заданный
    рост (прочие поля объекта остаются числами), порядок growth_first уступает дивидендом."""
    book, facts = inputs
    _, off = one_cell(put(book, "capital.growth_constraint.enabled", False), facts, TIGHT)
    for r in off["rows"]:
        assert all(x["lam"] == 1.0 and x["catch_up"] == 0.0 for x in r["quarters"])
        assert r["cut_share"] == pytest.approx(0.0, abs=1e-12)
        assert r["req20_glide"] == r["req20"] and r["req11_glide"] == r["req11"]
    ctx_g, first = one_cell(put(book, "capital.growth_constraint.order", cm.ORDER_GROWTH_FIRST), facts, TIGHT)
    base = cm.c_cell_of(control, *TIGHT)
    for cell in (off, first):
        assert abs(cell["v_ddm"] - cell["v_ri"]) <= 1e-9 * max(1.0, abs(cell["v_ri"]))
    # growth_first: запас под дивиденд меряется при полном росте — дивиденд режется раньше роста
    cut_first = sum(d["cut"] for d in first["decisions_q"])
    cut_base = sum(d["cut"] for d in base["decisions_q"])
    assert cut_first >= cut_base and first["rows"][-1]["loans"] >= base["rows"][-1]["loans"] - 1e-6
    assert len({round(c["v_ri"], 6) for c in (off, first, base)}) == 3
    # книга без объекта — тот же заданный рост
    _, bare = one_cell(put(book, "capital.growth_constraint", DROP), facts, TIGHT)
    assert bare["v_ri"] == pytest.approx(off["v_ri"], rel=1e-12)


# ============================================================================ квартальные дивиденды (М§5.7)


@pytest.mark.tact
def test_dividend_bounds_and_excess_formula(control):
    """Инвариант dividend_bounds квартального режима и формула избытка (М§5.7.5): по решениям модели
    одного квартала Σ base_div ≤ max(0, headroom), Σ div ≤ max(0, headroom, headroom_final); избыток — только
    у решения за четвёртый квартал прибыли и только при λ* = 1."""
    B = control["ctx"]["B"]
    with_excess = 0
    for c in control["cells"]:
        by_q = collections.defaultdict(list)
        for d in c["decisions_q"]:
            assert d["dps"] >= 0.0 and d["deferred_after"] >= -1e-9
            if d["source"] == "policy":
                by_q[d["q"]].append(d)
        for ds in by_q.values():
            room, final = ds[0]["headroom"], ds[0]["headroom_final"]
            base_sum = sum(d["base_div"] for d in ds)
            assert base_sum <= max(0.0, room) + 1e-9
            assert sum(d["div"] for d in ds) <= max(0.0, room, final) + 1e-9
            for d in ds:
                if d["h"] != cm.QY or d["lam"] < 1.0:
                    assert d["excess"] == 0.0 and d["catch"] == 0.0
                else:
                    want = cm.c_excess_share(B, d["year"]) * max(0.0, final - base_sum - d["catch"])
                    assert d["excess"] == pytest.approx(want, rel=1e-12, abs=1e-12)
                    with_excess += d["excess"] > 0.0
                assert d["cut"] == (base_sum < sum(x["want"] for x in ds) - 1e-9)
    assert with_excess, "на фикстуре избыток капитала ни разу не выплачен"


@pytest.mark.tact
def test_open_quarter_is_deducted_once_under_any_lag_map(inputs, control):
    """Квартал прибыли вычитается из BV ровно один раз при любой карте лагов (М§5.7.2): закрытые до
    якоря кварталы решает факт (p_last), а не карта; записи реестра — в своих кварталах клетки."""
    book, facts = inputs
    anchor = control["ctx"]["anchor"]
    cal = control["ctx"]["divcal"]
    assert cm.c_qper(anchor, cal["p_last"]) == (2025, 4)
    opened = {e["period"] for e in cal["open"].values()}
    for lag in ({"1": 2, "2": 2, "3": 1, "4": 2}, 1, 4, {"1": 4, "2": 1, "3": 3, "4": 1}):
        ctx, cell = one_cell(put(book, "dividends.calendar.decision_lag_quarters", lag), facts)
        made = [d["period"] for d in cell["decisions_q"]]
        assert len(made) == len(set(made))
        assert all(cm.c_qidx(anchor, *cm.c_per_parse(per)) > ctx["divcal"]["p_last"] for per in made)
        assert set(made) == {e["period"] for e in ctx["divcal"]["open"].values()}
        assert {"2026Q1", "2026Q2"} <= set(made)                 # открыты по факту при любой карте
        total = sum(d["div"] for d in cell["decisions_q"])
        assert total == pytest.approx(sum(r["div"] for r in cell["rows"]), rel=1e-7)
        if lag == {"1": 2, "2": 2, "3": 1, "4": 2}:
            assert set(made) == opened
    # пример М§5.7.2: записи реестра — в 1-м и 2-м кварталах сетки, решения модели — во 2-м и 4-м
    cell = cm.c_cell_of(control, *HOME)
    by_per = {d["period"]: d for d in cell["decisions_q"]}
    assert [by_per[p]["q"] for p in ("2026Q1", "2026Q2", "2026Q3", "2026Q4")] == [1, 2, 2, 4]
    assert [by_per[p]["source"] for p in ("2026Q1", "2026Q2", "2026Q3")] == ["register", "register", "policy"]
    assert by_per["2026Q2"]["dps"] == pytest.approx(4.7, rel=1e-12)
    assert by_per["2026Q2"]["div"] == pytest.approx(4.7 * control["shares_out"] / 1000.0, rel=1e-12)


@pytest.mark.tact
def test_closed_quarter_is_decided_by_the_fact_not_by_the_map(inputs):
    """Решение, которое по карте лагов состоялось бы до якоря, а по факту принято после даты фактов, —
    открытый квартал: клетка вычитает его в первом квартале сетки (не «никогда»)."""
    book, facts = inputs
    late = copy.deepcopy(facts)
    for rec in late["dividends"]["history"]:
        if rec["period"] == "2025Q4":
            rec["decided_date"] = "2026-07-15"                    # собрание ушло за дату фактов
    ctx, cell = one_cell(book, late)
    assert cm.c_qper(ctx["anchor"], ctx["divcal"]["p_last"]) == (2025, 3)
    first = [d for d in cell["decisions_q"] if d["period"] == "2025Q4"]
    assert len(first) == 1 and first[0]["q"] == 1 and first[0]["source"] == "policy"
    # решение раньше карты и до якоря: квартал закрыт, второй раз не вычитается
    early = copy.deepcopy(facts)
    early["dividends"]["history"].append({"year": 2026, "period": "2026Q1", "dps": {"v": 4.6}, "decided_date": "2026-06-29",
                                          "pool_declared": {"v": 12.3}})
    early["dividends"]["history"] = [r for i, r in enumerate(early["dividends"]["history"])
                                     if not (r["period"] == "2026Q1" and r.get("decided_date") == "2026-07-30")]
    early["dividends"]["register_seed"] = [r for r in early["dividends"]["register_seed"] if r["period"] != "2026Q1"]
    ctx, cell = one_cell(book, early)
    assert cm.c_qper(ctx["anchor"], ctx["divcal"]["p_last"]) == (2026, 1)
    assert "2026Q1" not in {d["period"] for d in cell["decisions_q"]}
    # запись реестра за открытый квартал с решением не позже даты фактов — отказ: сначала правятся факты
    bad = copy.deepcopy(facts)
    bad["dividends"]["register_seed"][0]["decided_date"] = "2026-06-01"
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(book, bad)


NINE_MONTHS = ("2025Q1", "2025Q2", "2025Q3")       # кварталы прибыли, которые закрывает одна строка истории


def nine_months_facts(facts: dict) -> tuple[dict, dict]:
    """Два варианта фактов фикстуры: решение за 4-й квартал года ушло за дату фактов (год наполовину закрыт
    тремя строками истории) и то же с одной строкой «за девять месяцев» на ту же сумму (период — третий
    квартал; у первых двух кварталов своей строки нет)."""
    late = copy.deepcopy(facts)
    for rec in late["dividends"]["history"]:
        if rec["period"] == "2025Q4":
            rec["decided_date"] = "2026-07-15"
    parts = [r for r in late["dividends"]["history"] if r["period"] in NINE_MONTHS]
    nine = copy.deepcopy(late)
    nine["dividends"]["history"] = [r for r in nine["dividends"]["history"] if r["period"] not in NINE_MONTHS[:-1]]
    for rec in nine["dividends"]["history"]:
        if rec["period"] == NINE_MONTHS[-1]:
            rec["dps"] = sum(cm._c_nodeval(r["dps"]) for r in parts)
            rec["pool_declared"] = sum(cm._c_nodeval(r["pool_declared"]) for r in parts)
    return late, nine


@pytest.mark.tact
def test_quarter_covered_by_a_later_history_row_gives_zero(inputs):
    """DPS года прибыли с закрытыми кварталами (М§5.7.5): закрытый квартал без своей строки истории, покрытый
    строкой более позднего квартала (решение «за девять месяцев» — одна строка, период — последний из
    кварталов), даёт ноль: его дивиденд — в той строке. Год с одной строкой за девять месяцев даёт тот же
    DPS, что год с тремя строками на ту же сумму. Строка без числа DPS — отказ (null ≠ 0)."""
    book, facts = inputs
    late, nine = nine_months_facts(facts)
    ctx, three = one_cell(book, late)
    assert cm.c_qper(ctx["anchor"], ctx["divcal"]["p_last"]) == (2025, 3)
    parts = [r for r in late["dividends"]["history"] if r["period"] in NINE_MONTHS]
    assert len(parts) == 3
    ctx9, one = one_cell(book, nine)
    cal = ctx9["divcal"]
    assert cal["p_last"] == ctx["divcal"]["p_last"]
    covered = [cm.c_qidx(ctx9["anchor"], 2025, h) for h in (1, 2)]
    assert all(k not in cal["hist_dps"] and k < cal["p_last"] for k in covered)
    year3, year9 = three["decisions"][2025], one["decisions"][2025]
    assert set(year9["quarters"]) == set(year3["quarters"]) == {"2025Q4"}      # открыт только четвёртый квартал
    own = year9["quarters"]["2025Q4"]["dps"]
    assert year9["dps"] == pytest.approx(cm._c_nodeval(parts[0]["dps"]) + cm._c_nodeval(parts[1]["dps"])
                                         + cm._c_nodeval(parts[2]["dps"]) + own, rel=1e-12)
    assert year9["dps"] == pytest.approx(year3["dps"], rel=1e-12) and one["v_ri"] == three["v_ri"]
    assert year9["div"] == pytest.approx(year3["div"], rel=1e-12)
    # тест потолка политики читает суммы решений года: одна строка на ту же сумму — те же строки теста
    assert cm.c_dps_history_ctl(book, nine) == pytest.approx(cm.c_dps_history_ctl(book, late))
    empty = copy.deepcopy(nine)
    for rec in empty["dividends"]["history"]:
        if rec["period"] == "2025Q3":
            rec["dps"] = None                                     # строка есть, числа нет — не ноль
    with pytest.raises(cm.ControlInputError):
        one_cell(book, empty)


@pytest.mark.tact
def test_anchor_state_queues_the_declared_part_only(inputs, control):
    """Состояние якоря (М§5.7.4): объявленная часть остатка «дивиденды к выплате» идёт в очереди выплат
    и вычетов, постоянная — не выплачивается и в регуляторный капитал не возвращается."""
    book, facts = inputs
    payable = control["ctx"]["A"]["DP"]
    base = cm.c_cell_of(control, *HOME)
    assert control["ctx"]["divcal"]["perm"] == payable and control["ctx"]["divcal"]["queue0"] == []
    assert all(x["dp"] >= payable - 1e-12 for x in _quarters(base))
    part = 3.0                                                    # вход теста: объявлено за закрытый квартал
    queued = copy.deepcopy(facts)
    queued["balance"]["dividends_payable_declared"] = [{"period": "2025Q4", "amount": {"v": part}}]
    ctx, cell = one_cell(book, queued)
    cal = ctx["divcal"]
    assert cal["perm"] == pytest.approx(payable - part) and len(cal["queue0"]) == 1
    item = cal["queue0"][0]
    # карта лагов: квартал прибыли 2025Q4 (−2) — вычет и выплата в квартале 0 ⇒ выплата в 1-м квартале сетки,
    # вычет уже стоит в регуляторном капитале якоря
    assert item["pay"] == 1 and item["reg"] <= 0
    assert cm.c_dpreg_anchor(ctx["B"], ctx["A"]) == 0.0
    q1 = cell["rows"][0]["quarters"][0]
    assert q1["dp"] == pytest.approx(base["rows"][0]["quarters"][0]["dp"] - part, rel=1e-9)
    assert all(x["dp"] >= payable - part - 1e-12 for x in _quarters(cell))
    for wrong in ([{"period": "2026Q1", "amount": {"v": 1.0}}],                       # период не закрыт
                  [{"period": "2025Q4", "amount": {"v": 1.0}}] * 2,                   # период повторяется
                  [{"period": "2025Q4", "amount": {"v": payable + 1.0}}]):            # больше остатка
        broken = copy.deepcopy(facts)
        broken["balance"]["dividends_payable_declared"] = wrong
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(book, broken)


@pytest.mark.tact
def test_dividend_base_is_the_window_mean_with_facts(inputs, control):
    """База дивиденда — средняя прибыль окна (М§5.7.3): кварталы не позже якоря — факты, позже — ряд
    клетки; пул — доля × база на размещённые акции, уменьшение BV — на акции в обращении."""
    book, facts = inputs
    A, B = control["ctx"]["A"], control["ctx"]["B"]
    cell = cm.c_cell_of(control, *HOME)
    d = next(x for x in cell["decisions_q"] if x["period"] == "2026Q3")
    fact = [A["pnl"][p]["ni_shareholders"] for p in ("2025Q4", "2026Q1", "2026Q2")]
    own = cell["rows"][0]["ni_q"][(2026, 3)]
    assert d["base"] == pytest.approx((sum(fact) + own) / 4.0, rel=1e-12)
    share = cm.c_payout_share(B, 2026)
    assert d["want"] == pytest.approx(share * d["base"] * A["N_out"] / A["N_iss"], rel=1e-12)
    assert d["dps_policy"] == pytest.approx(share * d["base"] * 1000.0 / A["N_iss"], rel=1e-12)
    # окно в один квартал — база одного квартала (другой дивиденд)
    _, single = one_cell(put(book, "dividends.policy.base_window_quarters", 1), facts)
    d1 = next(x for x in single["decisions_q"] if x["period"] == "2026Q3")
    assert d1["base"] == pytest.approx(single["rows"][0]["ni_q"][(2026, 3)], rel=1e-12)
    # DPS года прибыли — сумма четырёх кварталов: открытые — решения клетки, закрытые — строки истории
    years = cell["decisions"]
    assert min(years) == 2026 and max(years) == control["years"][-1] - 1
    assert years[2026]["dps"] == pytest.approx(sum(x["dps"] for x in cell["decisions_q"] if x["year"] == 2026), rel=1e-12)
    assert set(years[2026]["quarters"]) == {"2026Q1", "2026Q2", "2026Q3", "2026Q4"}


@pytest.mark.tact
def test_shock_year_cancels_model_decisions_only(control):
    """Клетка (N, crisis, strict): решения модели в кварталах года шока отменены (источник crisis_skip),
    записи реестра — нет; разовый убыток — в своём квартале; множитель плотности режима снижает RWA."""
    shock = control["shock_year"]
    anchor = control["ctx"]["anchor"]
    c = cm.c_cell_of(control, "N", "crisis", "strict")
    in_shock = [d for d in c["decisions_q"] if cm.c_qper(anchor, d["q"])[0] == shock]
    assert in_shock and all(d["source"] == "crisis_skip" and d["div"] == 0.0 for d in in_shock)
    assert all(d["source"] != "crisis_skip" for d in c["decisions_q"] if cm.c_qper(anchor, d["q"])[0] != shock)
    assert all(not d["cut"] for d in in_shock)                       # отмена — не урезание капиталом
    row = c["rows"][control["years"].index(shock)]
    assert row["one_off"] < 0.0 and row["div"] == 0.0


# ============================================================================ делитель и мост (М§8.1, §8.4)


def _with_register(facts: dict, records: list) -> dict:
    out = copy.deepcopy(facts)
    out["dividends"]["register_seed"] = records
    return out


@pytest.mark.tact
def test_exdate_jump_is_dps_on_outstanding_over_the_divisor(inputs, control):
    """Инвариант экс-даты (М§8.4): перенос экс-даты записи на день сдвигает точку на −DPS × N_out / N_div;
    мост несёт обе записи реестра сразу, каждая — на акции в обращении."""
    book, facts = inputs
    n_out, n_div = control["shares_out"], control["divisor"]
    seed = facts["dividends"]["register_seed"]
    v = dt.date.fromisoformat(seed[1]["ex_date"])                    # экс-дата второй записи (2026Q2)
    moved = copy.deepcopy(seed)
    moved[1]["ex_date"] = (v + dt.timedelta(days=1)).isoformat()
    after = cm.c_control_context(book, facts, valuation_date=v.isoformat())
    before = cm.c_control_context(book, _with_register(facts, moved), valuation_date=v.isoformat())
    dps = float(seed[1]["dps"]["v"] if isinstance(seed[1]["dps"], dict) else seed[1]["dps"])
    # запись реестра клеток не меняет (дата решения та же): точка сдвигается только мостом, поэтому
    # скачок считается формулой цены на оценках слоёв одного прогона
    assert after["pending_amount"] == before["pending_amount"]

    def point(ctx):
        low, high = (cm.c_price_of(control["layers"][name]["v0"], ctx["bridge_amount"], ctx["gov"], n_div,
                                   ctx["pending_amount"]) for name in ("macro_neutral", "analytical"))
        return low + control["lam"] * (high - low)

    jump = point(after) - point(before)
    assert jump == pytest.approx(-dps * n_out / n_div, rel=1e-9)
    assert abs(jump) < dps                                           # не −DPS: делитель больше акций в обращении
    # в день экс-даты первой записи (2026Q1, вычтена в 1-м квартале сетки) мост несёт −DPS × N_out до конца квартала
    ex1 = dt.date.fromisoformat(seed[0]["ex_date"])
    mid = cm.c_control_context(book, facts, valuation_date=ex1.isoformat())
    d1 = float(seed[0]["dps"]["v"] if isinstance(seed[0]["dps"], dict) else seed[0]["dps"])
    assert mid["bridge_amount"] == pytest.approx(-d1 * n_out / 1000.0, rel=1e-12)
    assert mid["pending_amount"] == pytest.approx((d1 + dps) * n_out / 1000.0, rel=1e-12)
    # на дату книги (конец 1-го квартала сетки): первая запись вычтена и уже без права — моста нет;
    # вторая объявлена, но клетки вычтут её в конце 2-го квартала — она в D_pend
    assert control["bridge_amount"] == pytest.approx(0.0, abs=1e-12)
    assert control["pending_amount"] == pytest.approx(dps * n_out / 1000.0, rel=1e-12)


@pytest.mark.tact
def test_one_divisor_for_everything_per_share(inputs, control):
    """Цена и капитал на акцию — на одном делителе; сдвиг share_count_adj на x меняет цену в 1/(1 + x)
    раз и не меняет V0; без ключей делителя N_div = N_out."""
    book, facts = inputs
    x = 0.04                                                         # вход теста
    ctx = cm.c_control_context(put(book, "valuation.share_count_adj", x), facts)
    assert ctx["A"]["N_div"] == pytest.approx(control["divisor"] * (1.0 + x), rel=1e-15)
    for name, ly in control["layers"].items():
        price = cm.c_price_of(ly["v0"], ctx["bridge_amount"], ctx["gov"], ctx["A"]["N_div"], ctx["pending_amount"])
        assert price == pytest.approx(ly["price"] / (1.0 + x), rel=1e-12)
        assert ly["bv_per_share"] == pytest.approx(ly["bv_v"] * 1000.0 / control["divisor"], rel=1e-15)
    bare = put(put(book, "valuation.shares_basis", DROP), "valuation.share_count_adj", DROP)
    assert cm.c_control_context(bare, facts)["A"]["N_div"] == control["shares_out"]
    two = put(book, "meta.company.tickers", ["T", "TP"])
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(two, facts)


# ============================================================================ объёмы, связь с объёмом, RWA


@pytest.mark.tact
def test_volume_link_in_the_annual_form(inputs, control):
    """Связь с объёмом (М§4.7), годовая форма: при нулевых связях строки совпадают с формулами образца
    бит в бит; при связи 1 рост комиссий равен росту объёма плюс спред; рост объёма года якоря читает
    концы кварталов фактов."""
    book, facts = inputs
    zero = book
    for key in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link"):
        zero = put(zero, key, 0.0)
    bare = zero
    for key in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link", "volumes.link_base"):
        bare = put(bare, key, DROP)
    _, a = one_cell(zero, facts)
    _, b = one_cell(bare, facts)
    for ra, rb in zip(a["rows"], b["rows"]):
        assert (ra["fees_q"], ra["opex_q"], ra["ins_q"], ra["pbt"]) == (rb["fees_q"], rb["opex_q"], rb["ins_q"], rb["pbt"])
        assert ra["v_volume"] is None
    ctx, one = one_cell(put(book, "fees.volume_link", 1.0), facts)
    A, B = ctx["A"], ctx["B"]
    r0, p0 = one["rows"][0], ctx["periods"][0]
    hist = A["history"]
    ends = [hist["2025Q2"]["loans"], hist["2025Q3"]["loans"], hist["2025Q4"]["loans"]]
    prev = (ends[0] + ends[1]) / 2.0 + (ends[1] + ends[2]) / 2.0
    path = r0["loans_path"]
    assert path[0] == pytest.approx(sum(A["E0"][b] for b in ctx["loans"]), rel=1e-15)
    assert r0["v_volume"] == pytest.approx(sum((x + y) / 2.0 for x, y in zip(path, path[1:])) / prev - 1.0, rel=1e-12)
    for j, q in enumerate(p0["quarters"]):
        fact = A["pnl"][f"{p0['year'] - 1}Q{q}"]["fees_net"]
        spread = cm.c_traj_at(cm.c_bget(B, "fees.growth_vs_wages"), p0["year"], q)
        assert r0["fees_q"][j] / fact - 1.0 == pytest.approx(r0["v_volume"] + spread, abs=1e-12)
    # урезанный рост кредитов урезает и рост объёма: связь считается на объёмах шага
    tight = cm.c_cell_of(control, *TIGHT)
    _, free = one_cell(put(book, "capital.growth_constraint.enabled", False), facts, TIGHT)
    cut_year = next(i for i, r in enumerate(tight["rows"]) if r["lam_min"] < 1.0)
    assert tight["rows"][cut_year]["v_volume"] < free["rows"][cut_year]["v_volume"]
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(put(book, "opex.volume_link", 1.5), facts)


@pytest.mark.tact
def test_fixed_other_assets_do_not_grow(inputs, control):
    """Постоянные прочие активы (М§4.3, §4.11): не растут с кредитами, входят в RWA со своей плотностью;
    anchor-отношение прочих активов считается без них; без плотности при ненулевой сумме — отказ."""
    book, facts = inputs
    ctx = control["ctx"]
    A, B = ctx["A"], ctx["B"]
    fixed = A["OA_fixed"]
    assert fixed == facts["balance"]["other_assets_fixed"]["v"] > 0.0
    loans0 = sum(A["E0"][b] for b in ctx["loans"])
    ratio = cm.c_bnum(B, "volumes.other_assets_to_loans")
    assert ratio == pytest.approx((A["OA"] - fixed) / loans0, rel=1e-15)
    cell = cm.c_cell_of(control, *HOME)
    for r in cell["rows"]:
        assert r["oa"] == pytest.approx(ratio * r["loans"] + fixed, rel=1e-12)
    dens = cm.c_bget(B, "capital.rwa.density")
    assert ctx["rwa0"] == pytest.approx(
        sum(float(dens[b]) * A["E0"][b] for b in B["nii"]["books"] if b in dens)
        + float(dens["other_assets"]) * (A["OA"] - fixed) + float(dens["other_assets_fixed"]) * fixed, rel=1e-15)
    heavy = cm.c_control_context(put(book, "capital.rwa.density.other_assets_fixed", 1.0), facts)
    assert heavy["rwa0"] == pytest.approx(ctx["rwa0"] + fixed, rel=1e-12)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(put(book, "capital.rwa.density.other_assets_fixed", DROP), facts)
    # без ключа постоянных активов нет: прочие активы целиком растут с кредитами
    _, grown = one_cell(put(book, "volumes.other_assets_fixed", DROP), facts)
    assert grown["rows"][-1]["oa"] > cell["rows"][-1]["oa"]


@pytest.mark.tact
def test_regime_density_multiplier_scales_only_its_regime(inputs, control):
    """Множитель плотности режима (М§4.11): масштабирует RWA клеток своего режима и не трогает прочие;
    ключ года якоря держит остаток года якоря на единице."""
    book, facts = inputs
    bare = put(book, "regimes.crisis.rwa_density_mult", DROP)
    off = put(bare, "capital.growth_constraint.enabled", False)
    on = put(book, "capital.growth_constraint.enabled", False)
    for key, same in ((("H", "crisis", "mid"), False), (HOME, True)):
        _, a = one_cell(on, facts, key)
        _, b = one_cell(off, facts, key)
        if same:
            assert [r["rwa"] for r in a["rows"]] == [r["rwa"] for r in b["rows"]]
            continue
        shock = control["years"].index(control["shock_year"])
        mult = cm.c_traj_at(book["regimes"]["crisis"]["rwa_density_mult"], control["shock_year"], cm.QY)
        assert a["rows"][0]["rwa"] == b["rows"][0]["rwa"]                    # год якоря: множитель 1
        assert a["rows"][shock]["rwa"] < b["rows"][shock]["rwa"] and mult < 1.0
        # множитель стоит на всех RWA клетки: при том же балансе конца года RWA × M (баланс отличается
        # только через капитал — вычеты идут за RWA)
        assert a["rows"][shock]["rwa"] / b["rows"][shock]["rwa"] == pytest.approx(mult, rel=5e-3)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(put(book, "regimes.crisis.rwa_density_mult", {"2026": 1.0, "2027": 0.0, "LT": 1.0}), facts)


@pytest.mark.tact
def test_growth_premium_by_sector_and_guidance_year(inputs):
    """Премия роста словарём равных траекторий совпадает с числом (М§4.3); неполный словарь — отказ;
    год гайденса до якоря не срабатывает ни в одном квартале сетки."""
    book, facts = inputs
    flat = put(put(book, "volumes.loan_share_drift", 0.05), "volumes.funds_share_drift", 0.03)
    same = put(put(book, "volumes.loan_share_drift", {s: {"LT": 0.05} for s in cm.LOAN_SECTORS}),
               "volumes.funds_share_drift", {s: 0.03 for s in cm.FUND_SEGMENTS})
    _, a = one_cell(flat, facts)
    _, b = one_cell(same, facts)
    assert [r["loans"] for r in a["rows"]] == [r["loans"] for r in b["rows"]]
    assert a["v_ri"] == b["v_ri"]
    with pytest.raises(cm.ControlInputError):
        one_cell(put(book, "volumes.loan_share_drift", {"corporate": 0.1, "mortgage": 0.1}), facts)
    # премия читается только до share_drift_until
    ctx, cell = one_cell(put(book, "capital.growth_constraint.enabled", False), facts)
    until = int(cm.c_bnum(ctx["B"], "volumes.share_drift_until"))
    for p, r in zip(ctx["periods"], cell["rows"]):
        if p["year"] > until:
            g = (1.0 + r["m_q"]["cards"]) ** cm.QY - 1.0
            sector = cm.c_overlay_growth(ctx["B"], HOME[0], "credit_growth", "retail_other", p["year"])
            assert g == pytest.approx(sector, abs=1e-12)
    assert int(cm.c_bnum(ctx["B"], "volumes.guidance_year")) < ctx["periods"][0]["year"]
    with pytest.raises(cm.ControlInputError):                       # год гайденса внутри сетки при ограничении роста
        cm.c_control_context(put(book, "volumes.guidance_year", ctx["periods"][1]["year"]), facts)


# ============================================================================ тест истории и терминал


@pytest.mark.tact
def test_history_test_of_the_cap_kind(inputs, control):
    """Тест истории вида cap (М§5.2): неполный год — диагностика без вердикта, превышение в завершённом
    году — нарушение; база потолка — отчётная прибыль акционеров (dividends.years), не операционная."""
    book, facts = inputs
    assert control["history_test"] == cm.HIST_CAP
    rows = {h["year"]: h for h in control["dps_history"]}
    assert rows[2024]["ok"] is True and rows[2025]["ok"] is True and rows[2026]["ok"] is None
    assert rows[2026]["share"] > rows[2026]["cap"]                   # неполный год выше потолка — без отказа
    assert rows[2025]["ni_shareholders"] == facts["dividends"]["years"]["2025"]["ni_shareholders"]["v"]
    assert rows[2025]["pool"] == pytest.approx(sum(
        r["pool_declared"]["v"] for r in facts["dividends"]["history"] if r["year"] == 2025), rel=1e-12)
    low = cm.c_dps_history_ctl(put(book, "dividends.policy.cap", 0.2), facts)
    assert [h["ok"] for h in low] == [False, False, None]
    assert cm.c_dps_history_ctl(put(book, "dividends.policy.history_test", cm.HIST_NONE), facts) == []
    with pytest.raises(cm.ControlInputError):
        cm.c_dps_history_ctl(put(book, "dividends.policy.cap", DROP), facts)


@pytest.mark.tact
def test_terminal_excess_leaves_out_declared_not_yet_deducted(control):
    """Терминал (М§7): X_T считается без дивидендов, решённых в последних кварталах сетки и ещё не
    вычтенных из регуляторного капитала (DPreg_Q) — иначе они были бы розданы второй раз."""
    B = control["ctx"]["B"]
    mult = cm.c_bnum(B, "valuation.terminal.excess_capital_multiple")
    seen = 0
    for c in control["cells"]:
        last = c["rows"][-1]
        want = mult * min((last["n20"] - last["dpreg"] / last["rwa"] - last["req20"]) * last["rwa"],
                          (last["n11_star"] - last["dpreg"] / last["rwa"] - last["req11"]) * last["rwa"])
        assert c["x_t"] == pytest.approx(want, rel=1e-12, abs=1e-9)
        seen += last["dpreg"] > 0.0
        assert c["tv_ddm"] == pytest.approx(last["bv"] + c["tv_ri"], rel=1e-12)
    assert seen, "на фикстуре в последнем квартале сетки нет решения с вычетом за сеткой"


# ============================================================================ сверка с ядром (в момент теста)


def _core_modules():
    try:
        return importlib.import_module("model.book"), importlib.import_module("model.grid")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc})")


DIVIDEND_GROUPS = ("dps_q", "dps", "div")
CUT_ROWS_SHARE = 0.01       # строк дивиденда, которые держит только правило срезанного решения, — не больше этой доли
STRESS_KEY = {"loss_step": 60.0, "tol": 0.5}        # ключ гейта знака стресса — вход теста (млрд ₽)
MARGIN_KEY = {"target": 0.11, "tolerance": 0.001, "from_year": 2030}      # ключ гейта печатаемой маржи — вход теста


def held_by_cut_rule(rows: list[dict]) -> list[dict]:
    """Строки дивиденда, которые в допуске только по правилу решения, срезанного до запаса (М§17): по
    прежнему полу строки они были бы вне допуска."""
    return [r for r in rows if r.get("cut") and r["ok"]
            and not tcm.verdict(r["diff"], r["diff_rel"], r["tol"], r["tol_kind"], r["floor_plain"])]


@pytest.mark.tact
def test_cut_dividend_rows_take_the_ratio_tolerance(control):
    """Допуск дивиденда решения, срезанного до запаса (М§17): срезанный дивиденд равен запасу (N − req*) × RWA —
    малой разности, поэтому абсолютный пол строки — не меньше 0,3 п.п. × RWA квартала решения (у DPS — на
    акцию в обращении). Правило — только у строк дивиденда и только при срезанном решении; строка несёт
    допуск, по которому судится: вердикт следует из записанного. Ядро не нужно — заглушка из чисел
    контрольной модели."""
    n_out = control["shares_out"]
    rows = tcm.compare_with_core(tcm._stub_core(control, 1.0), control)
    by_what = {r["what"]: r for r in rows}
    marked = [r for r in rows if r.get("cut")]
    assert marked and {r["group"] for r in marked} <= set(DIVIDEND_GROUPS)
    cell = next(c for c in control["cells"] if any(d["cut"] for d in c["decisions_q"]))
    tag = "/".join((cell["world"], cell["regime"], cell["scenario"]))
    quarters = {x["q"]: x for r in cell["rows"] for x in r["quarters"]}
    seen = 0
    for d in cell["decisions_q"]:
        row = by_what[f"DPS за квартал {d['period']}, клетка {tag}"]
        if not d["cut"]:
            assert not row.get("cut")                               # решение не срезано — пол прежний
            continue
        want = max(row["floor_plain"], tcm.TOL_RATIO * quarters[d["q"]]["rwa"] * 1000.0 / n_out)
        assert row["cut"] and row["tol_abs"] == pytest.approx(want, rel=1e-12)
        tcm._assert_row_form(tcm._public(row))
        seen += 1
    assert seen
    # год: наибольший RWA кварталов срезанных решений года; строка «дивиденд года» — в млрд ₽
    cut_q = sorted(d["q"] for d in cell["decisions_q"] if d["cut"])
    year = cm.c_qper(control["ctx"]["anchor"], cut_q[0])[0]
    same_year = [q for q in cut_q if cm.c_qper(control["ctx"]["anchor"], q)[0] == year]
    div = by_what[f"{tcm.line_titles(control['ctx']['B'])['div']} {year}, клетка {tag}"]
    assert div["cut"] and div["tol_abs"] == pytest.approx(
        max(div["floor_plain"], tcm.TOL_RATIO * max(quarters[q]["rwa"] for q in same_year)), rel=1e-12)
    # расхождение между прежним полом и полом правила: строка срезанного решения — в допуске, прочие — нет
    d = next(x for x in cell["decisions_q"] if x["cut"])
    row = by_what[f"DPS за квартал {d['period']}, клетка {tag}"]
    assert row["tol_abs"] > row["floor_plain"]
    shift = (row["floor_plain"] + row["tol_abs"]) / 2.0
    stub = tcm._stub_core(control, 1.0)
    core_cell = stub.cell(*tag.split("/"))
    free = next(x for x in cell["decisions_q"] if not x["cut"] and x["dps"] > 0.0 and shift > tcm.TOL_LINE * (x["dps"] + shift))
    for dec in (d, free):
        core_cell.dps_q[dec["period"]] = dec["dps"] + shift
    again = {r["what"]: r for r in tcm.compare_with_core(stub, control)}
    assert again[f"DPS за квартал {d['period']}, клетка {tag}"]["ok"]
    assert not again[f"DPS за квартал {free['period']}, клетка {tag}"]["ok"]
    # срез, который видит только ядро, включает то же правило
    other = next(x for x in cell["decisions_q"] if not x["cut"] and x["source"] == "policy")
    core_cell.decisions = (tcm.SimpleNamespace(q=other["q"], cut=True, period=other["period"], year=other["year"]),)
    seen_by_core = {r["what"]: r for r in tcm.compare_with_core(stub, control)}
    assert seen_by_core[f"DPS за квартал {other['period']}, клетка {tag}"].get("cut")


@pytest.mark.ci_only
def test_control_matches_core_on_the_panel_form(inputs, control):
    """Полная книга фикстуры: строки сверки М§17, включая DPS кварталов прибыли, требование с глиссадой и
    рост кредитных книг, — в допусках; точное совпадение V0 слоёв — провал (общий код). Дивиденд решений,
    срезанных до запаса, сверяется по правилу М§17 (не больше 0,3 п.п. × RWA квартала решения): там дивиденд —
    малая разность, и модели расходятся на расхождение норматива квартала (годовая строка ОПУ с раскладкой
    прибыли по кварталам против квартальной ОПУ ядра). Только на этом правиле держится не больше 1 % строк."""
    book, _ = inputs
    book_mod, grid_mod = _core_modules()
    try:
        facts = book_mod.load_facts(FIXTURE / "facts")
        run = grid_mod.run_grid(book_mod.book_from_dict(book, facts=facts), facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу формы панели — сверять не с чем: {type(exc).__name__}: {str(exc)[:500]}")
    rows = tcm.compare_with_core(run, control)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    assert all(r["group"] in DIVIDEND_GROUPS for r in rows if r.get("cut"))
    assert len(held_by_cut_rule(rows)) <= CUT_ROWS_SHARE * len(rows), (len(held_by_cut_rule(rows)), len(rows))
    assert not tcm.exact_match(run, control), "V0 слоёв совпали с ядром до 1e-9 — общий код"
    assert getattr(run, "divisor", None) == pytest.approx(control["divisor"], rel=1e-12)


@pytest.mark.ci_only
def test_covered_quarter_matches_core(inputs):
    """Строка истории «за девять месяцев» у обеих моделей: квартал, покрытый строкой более позднего квартала,
    даёт ноль, и DPS года с такими кварталами у ядра и контрольной модели сходится (строка истории — факт,
    решение за открытый квартал — в допуске DPS квартала прибыли)."""
    import dataclasses
    book, facts = inputs
    _, nine = nine_months_facts(facts)
    book_mod, grid_mod = _core_modules()
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    core_facts = dataclasses.replace(core_facts, files={**core_facts.files, "dividends": nine["dividends"]})
    try:
        run = grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts), core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало факты со строкой «за девять месяцев»: {type(exc).__name__}: {str(exc)[:300]}")
    ctx, mine = one_cell(book, nine)
    core = run.cell(*HOME)
    year = int(NINE_MONTHS[-1][:4])
    history = sum(cm._c_nodeval(r["dps"]) for r in nine["dividends"]["history"] if r["period"] == NINE_MONTHS[-1])
    own = mine["decisions"][year]["quarters"][f"{year}Q4"]
    floor = tcm.DPS_Q_FLOOR_BV * abs(mine["rows"][0]["bv"]) * 1000.0 / ctx["A"]["N_out"]
    assert abs(core.dps_q[f"{year}Q4"] - own["dps"]) <= max(tcm.TOL_LINE * abs(own["dps"]), floor)
    assert core.dps[year] - core.dps_q[f"{year}Q4"] == pytest.approx(history, rel=1e-12)
    assert mine["decisions"][year]["dps"] - own["dps"] == pytest.approx(history, rel=1e-12)


@pytest.mark.ci_only
def test_volume_sign_numbers_match_core_on_the_panel_form(inputs, control):
    """Число гейта знака объёмных эффектов на книге фикстуры: сдвиг точки и сдвиги цен миров контрольной
    модели и ядра — в допуске 3 % модуля или 0,5 ₽, обе точки сравнения — как цена."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    run = grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts), core_facts)
    core, why = tcm.core_gate(run, "volume_sign_test")
    if core is None:
        pytest.fail(f"сверять не с чем: {why}")
    mine = cm.c_volume_sign(book, facts, control)
    bad = [r for r in tcm.gate_rows(core, mine) if not r["ok"]]
    assert not bad, "число гейта знака объёмных эффектов вне допуска:" + chr(10) + tcm._fail_lines(bad)


@pytest.mark.ci_only
def test_stress_sign_cells_match_core_on_the_panel_form(inputs, control):
    """Набор нарушивших клеток гейта знака стресса на книге фикстуры с ключом checks.stress_sign,
    подставленным тестом: ядро и контрольная модель называют одни и те же клетки и пары сценариев — во всех
    режимах, включая режим шока."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    if not hasattr(grid_mod, "stress_sign_test"):
        pytest.fail("в ядре нет model.grid.stress_sign_test: сверять набор нарушивших клеток не с чем")
    keyed = put(book, "checks.stress_sign", dict(STRESS_KEY))
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    run = grid_mod.run_grid(book_mod.book_from_dict(keyed, facts=core_facts), core_facts)
    core, _ = tcm.core_gate(run, "stress_sign_test")
    problems = tcm.stress_sign_mismatch(core, cm.c_stress_sign(keyed, facts, control),
                                        tcm.stress_band(control["divisor"]))
    assert not problems, "набор нарушивших клеток гейта знака стресса расходится:" + chr(10) + chr(10).join(problems)


# ============================================================================ гейт знака стресса и печатаемая маржа


@pytest.mark.tact
def test_stress_sign_of_the_control_model(inputs, control):
    """Гейт знака стресса (ключ книги checks.stress_sign: {loss_step, tol}, млрд ₽) — свой счёт контрольной
    модели, ключ подставлен тестом. (а) Убыток: в каждой клетке режима шока — разность стоимости при разовом
    убытке, увеличенном на loss_step, и стоимости книги; нарушение — разность больше tol. (б) Требование: в
    каждой паре «мир × режим» — по всем режимам, включая режим шока, — разность прибыли последнего года у
    сценария с более высоким требованием Н20.0 последнего года и сценария с более низким; нарушение — больше
    tol. Масса — вероятности точки нарушивших клеток, у пары — клетка более строгого сценария. Нет ключа —
    гейта нет. Знак чисел фикстуры тест не утверждает: нарушения он создаёт подменой прогона."""
    book, facts = inputs
    assert cm.c_stress_sign(put(book, "checks.stress_sign", DROP), facts, control) is None      # нет ключа — гейта нет
    keyed = put(book, "checks.stress_sign", dict(STRESS_KEY))
    out = cm.c_stress_sign(keyed, facts, control)
    ctx = control["ctx"]
    worlds, scen = ctx["worlds"], list(cm.c_bget(ctx["B"], "capital.reg_scenarios.ids"))
    regimes = list(cm.c_bget(ctx["B"], "regimes.ids"))
    assert cm.R_CRISIS in regimes and len(regimes) > 1
    assert out["loss"]["step"] == STRESS_KEY["loss_step"] and out["tol"] == STRESS_KEY["tol"]
    # (а) таблица — все клетки режима шока; число клетки — пересчёт одной клетки на книге с большим убытком
    assert [(x["world"], x["regime"], x["scenario"]) for x in out["loss"]["table"]] == [
        (w, cm.R_CRISIS, sc) for w in worlds for sc in scen]
    amount = float(book["regimes"][cm.R_CRISIS]["one_off_loss"]["amount"])
    assert amount < 0.0
    key = (worlds[-1], cm.R_CRISIS, scen[0])
    _, hit = one_cell(put(book, f"regimes.{cm.R_CRISIS}.one_off_loss.amount", amount - STRESS_KEY["loss_step"]), facts, key)
    row = next(x for x in out["loss"]["table"] if (x["world"], x["regime"], x["scenario"]) == key)
    assert row["dv"] == pytest.approx(hit["v_ri"] - cm.c_cell_of(control, *key)["v_ri"], rel=1e-12, abs=1e-9)
    year = control["years"].index(control["shock_year"])
    assert hit["rows"][year]["one_off"] == amount - STRESS_KEY["loss_step"]
    # (б) таблица — пары сценариев с разным требованием последнего года во всех режимах, включая режим шока
    req = {sc: cm.c_cell_of(control, worlds[0], regimes[0], sc)["rows"][-1]["req20"] for sc in scen}
    pairs = [(hi, lo) for hi in scen for lo in scen if req[hi] > req[lo]]
    assert pairs, "у сценариев фикстуры одно требование последнего года — пар нет"
    assert [(x["world"], x["regime"], x["stricter"], x["looser"]) for x in out["requirement"]["table"]] == [
        (w, r, hi, lo) for w in worlds for r in regimes for hi, lo in pairs]
    assert any(x["regime"] == cm.R_CRISIS for x in out["requirement"]["table"])
    for x in out["requirement"]["table"][::5]:
        hi, lo = (cm.c_cell_of(control, x["world"], x["regime"], x[k])["rows"][-1] for k in ("stricter", "looser"))
        assert hi["req20"] > lo["req20"] and x["d_profit"] == hi["ni_sh"] - lo["ni_sh"]
    # нарушившие — числа таблицы выше tol; масса — вероятности точки, сумма которых по сетке — 1
    weight = cm.c_point_mass(control)
    assert sum(weight.values()) == pytest.approx(1.0, abs=1e-12)
    lam = control["lam"]
    for name, share in (("macro_neutral", 1.0 - lam), ("analytical", lam)):
        assert share >= 0.0 and abs(control["layers"][name]["prob_sum"] - 1.0) <= 1e-12
    assert out["loss"]["cells"] == [x for x in out["loss"]["table"] if x["dv"] > out["tol"]]
    assert out["requirement"]["cells"] == [x for x in out["requirement"]["table"] if x["d_profit"] > out["tol"]]
    named = ({(x["world"], x["regime"], x["scenario"]) for x in out["loss"]["cells"]}
             | {(x["world"], x["regime"], x["stricter"]) for x in out["requirement"]["cells"]})
    assert out["mass"] == pytest.approx(sum(weight[k] for k in named), abs=1e-15) and out["ok"] == (not named)
    # порог выше любого числа — нарушений нет (числа таблиц от порога не зависят)
    tables = (out["loss"]["table"], out["requirement"]["table"])
    quiet = cm.c_stress_sign(put(book, "checks.stress_sign", {**STRESS_KEY, "tol": 1e9}), facts, control, tables=tables)
    assert quiet["ok"] and quiet["mass"] == 0.0 and quiet["max_excess"] == 0.0 and quiet["worlds"] == []
    assert quiet["loss"]["cells"] == [] and quiet["requirement"]["cells"] == []
    # нарушения — подменой чисел: стоимость одной клетки режима шока выросла, прибыль последнего года одной
    # клетки самого строгого сценария выше, чем у каждого более мягкого
    top = max(scen, key=lambda sc: req[sc])
    low_cell, rich_cell = (worlds[0], cm.R_CRISIS, scen[-1]), (worlds[-1], cm.R_CRISIS, top)
    bump = 1000.0                                                    # вход теста, млрд ₽
    forged_loss = [{**x, "dv": x["dv"] + bump} if (x["world"], x["regime"], x["scenario"]) == low_cell else x
                   for x in out["loss"]["table"]]
    forged_req = [{**x, "d_profit": x["d_profit"] + bump} if (x["world"], x["regime"], x["stricter"]) == rich_cell
                  else x for x in out["requirement"]["table"]]
    found = cm.c_stress_sign(keyed, facts, control, tables=(forged_loss, forged_req))
    assert not found["ok"]
    assert low_cell in {(x["world"], x["regime"], x["scenario"]) for x in found["loss"]["cells"]}
    mine = [x for x in found["requirement"]["cells"] if (x["world"], x["regime"], x["stricter"]) == rich_cell]
    assert {x["looser"] for x in mine} == {lo for hi, lo in pairs if hi == top}
    extra = {low_cell, rich_cell} - named                           # клетка пары входит в массу один раз
    assert found["mass"] == pytest.approx(out["mass"] + sum(weight[k] for k in extra), abs=1e-12)
    biggest = max([x["dv"] for x in forged_loss] + [x["d_profit"] for x in forged_req])
    assert found["max_excess"] == biggest > bump / 2.0
    assert {low_cell[0], rich_cell[0]} <= set(found["worlds"])
    for wrong in ({"loss_step": 60.0}, {"loss_step": 0.0, "tol": 0.5}, {"loss_step": 60.0, "tol": -1.0}):
        with pytest.raises(cm.ControlInputError):
            cm.c_stress_sign(put(book, "checks.stress_sign", wrong), facts, control)


@pytest.mark.tact
def test_printed_margin_of_the_modal_cell(inputs, control):
    """Печатаемая маржа после фазы роста (ключ книги checks.nim_lt, подставлен тестом): среднее годовых ЧПМ
    упр. базиса модальной клетки за годы from_year … последний год сетки. Годовая ЧПМ — ЧПД года к среднему
    пяти концов кварталов процентных активов (М§0.3): концы — из квартального прохода, конец года — тот же,
    что у годовой строки; в упр. базис — через мост. Нет ключа — значения нет."""
    ctx = control["ctx"]
    bare = dict(control)
    bare["ctx"] = {**ctx, "B": put(ctx["B"], "checks.nim_lt", DROP)}
    assert cm.c_printed_margin(bare) is None
    cell = cm.c_cell_of(control, *control["central"]["cell"])
    prev = ctx["tr"]["iea0"]
    for p, r in zip(ctx["periods"], cell["rows"]):
        assert r["iea_ends"][0] == prev and len(r["iea_ends"]) == p["n"] + 1
        assert r["iea_ends"][-1] == pytest.approx(r["iea_end"], rel=1e-8)
        assert r["iea_end"] == pytest.approx(r["loans"] + r["securities"] + r["liquidity"], rel=1e-12)
        if p["stub"]:
            assert r["nim_year"] is None
        else:
            assert r["nim_year"] == pytest.approx(r["nii"] / (sum(r["iea_ends"]) / (cm.QY + 1)), rel=1e-12)
        prev = r["iea_end"]
    keyed = dict(control)
    keyed["ctx"] = {**ctx, "B": put(ctx["B"], "checks.nim_lt", dict(MARGIN_KEY))}
    out = cm.c_printed_margin(keyed)
    years = [y for y in control["years"] if y >= MARGIN_KEY["from_year"]]
    assert sorted(out["by_year"]) == years and out["cell"] == control["central"]["label"]
    rows = {y: r for y, r in zip(control["years"], cell["rows"])}
    for y in years:
        assert out["by_year"][y] == cm.c_to_mgmt(ctx["A"], "nim", rows[y]["nim_year"])
    assert out["value"] == pytest.approx(sum(out["by_year"].values()) / len(years), rel=1e-15)
    assert out["ok"] == (abs(out["value"] - MARGIN_KEY["target"]) <= MARGIN_KEY["tolerance"])
    # строка сверки появляется только у книги с ключом; у заглушки ядра годовой ряд ЧПМ — базис движка
    stub = tcm._stub_core(control, 1.0)
    assert not any(r["what"] == tcm.MARGIN_WORDS for r in tcm.compare_with_core(stub, bare))
    row = next(r for r in tcm.compare_with_core(stub, keyed) if r["what"] == tcm.MARGIN_WORDS)
    assert row["ok"] and row["unit"] == tcm.U_PCT and row["core"] == pytest.approx(out["value"], rel=1e-12)
    late = dict(control)
    late["ctx"] = {**ctx, "B": put(ctx["B"], "checks.nim_lt", {**MARGIN_KEY, "from_year": control["years"][-1] + 1})}
    with pytest.raises(cm.ControlInputError):
        cm.c_printed_margin(late)


# ============================================================================ мир-опора κ и уровни после фазы роста


WINDOW_SPEC = {"from_year": 2030, "cor": [0.0, 1.0], "cir": [0.0, 1.0]}     # ключ гейта сверки с окном — вход теста


@pytest.mark.tact
def test_kappa_reference_world_on_the_panel_form(inputs, control):
    """Мир-опора κ на форме панели (ключ credit.kappa_reference_world, подставлен тестом): без ключа добавка —
    только вверх от мира N, с ключом — к названному миру с любым знаком; CoR клетки и кредитная маржа
    стационара несут её тем же правилом."""
    book, facts = inputs
    assert cm.c_kappa_world(control["ctx"]["B"]) is None or cm.c_kappa_world(control["ctx"]["B"]) in control["ctx"]["worlds"]
    tcm.kappa_reference_checks(book, facts, HOME[1], HOME[2])


@pytest.mark.tact
def test_levels_and_their_gates_on_the_panel_form(control):
    """Уровни после фазы роста на клетках формы панели — отношение ожидаемых агрегатов; гейт сверки с окном
    фактов и уровень C/I цели книги — при ключах, подставленных тестом."""
    tcm.levels_checks(control)
    tcm.window_backtest_checks(control)
    tcm.cir_level_checks(control)
    keyed = tcm.with_checks(control, **{tcm.WINDOW_KEY: dict(WINDOW_SPEC)})
    assert cm.c_levels(keyed)["from_year"] == WINDOW_SPEC["from_year"] and cm.c_window_backtest(keyed)["ok"]
    # строки сводки уровней — только у книги с ключом: на заглушке ядра из чисел самой модели они в допуске
    rows = tcm.level_rows(cm.c_window_backtest(keyed), cm.c_window_backtest(keyed))
    assert [r["what"] for r in rows] == [f"{tcm.LEVEL_WORDS}: {tcm.LEVEL_TITLES[x]}" for x in ("cor", "cir", "nim")]
    assert all(r["ok"] and r["unit"] == tcm.U_PCT and r["tol"] == tcm.TOL_RATIO for r in rows)
    assert not tcm.level_rows(None, cm.c_window_backtest(keyed))[0]["ok"]
    far = {x: v + 2.0 * tcm.TOL_RATIO for x, v in cm.c_levels(keyed)["mixes"][cm.LAYER_MARKET].items() if x != "by_year"}
    assert not any(r["ok"] for r in tcm.level_rows(far, cm.c_window_backtest(keyed)))


@pytest.mark.ci_only
def test_kappa_reference_world_matches_core_on_the_panel_form(inputs, control):
    """Мир-опора κ у обеих моделей на форме панели, ключ подставлен тестом (у книги с ключом — снят): вся сверка
    М§17 в допусках, разность годовой CoR клеток мира и мира-опоры — в 0,03 п.п., сдвиг точки между ветвями
    ключа у моделей один."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    other = tcm.other_kappa_branch(book)
    try:
        base = grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts), core_facts)
        run = grid_mod.run_grid(book_mod.book_from_dict(other, facts=core_facts), core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу формы панели с ключом мира-опоры κ: {type(exc).__name__}: {str(exc)[:500]}")
    ctl = cm.c_control_run(other, facts)
    rows = tcm.compare_with_core(run, ctl)
    if cm.c_kappa_world(ctl["ctx"]["B"]) is None:
        rows += tcm.kappa_spread_rows(run, ctl)
    assert any(r["group"] == "kappa" for r in rows)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    d_core, d_ctl = run.point - base.point, ctl["point"] - control["point"]
    assert d_core != 0.0 and abs(d_ctl - d_core) <= max(tcm.SIGN_TOL_REL * abs(d_core), tcm.SIGN_TOL_RUB), (d_core, d_ctl)


@pytest.mark.ci_only
def test_levels_match_core_on_the_panel_form(inputs, control):
    """Уровни после фазы роста на форме панели при ключах checks.window_backtest и checks.cir_lt.scope,
    подставленных тестом: узел уровней ядра и число его гейта C/I против своего счёта контрольной модели — в
    допуске отношений М§17."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    mod = tcm.core_levels_module()
    keyed = put(book, f"checks.{tcm.WINDOW_KEY}", dict(WINDOW_SPEC))
    goal = {**{k: v for k, v in book["checks"]["cir_lt"].items() if k != tcm.SCOPE_KEY}, tcm.SCOPE_KEY: cm.SCOPE_MARKET}
    keyed = put(keyed, "checks.cir_lt", goal)
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    try:
        run = grid_mod.run_grid(book_mod.book_from_dict(keyed, facts=core_facts), core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу формы панели с ключами уровней: {type(exc).__name__}: {str(exc)[:500]}")
    mine = tcm.with_checks(control, **{tcm.WINDOW_KEY: dict(WINDOW_SPEC), "cir_lt": goal})
    problems = tcm.levels_mismatch(mod.levels(run), cm.c_levels(mine))
    assert not problems, "уровни после фазы роста расходятся:" + chr(10) + chr(10).join(problems)
    rows = tcm.summary_level_rows(run, mine)
    assert len(rows) == 4 and all(r["ok"] for r in rows), tcm._fail_lines([r for r in rows if not r["ok"]])
    assert rows[-1]["what"] == tcm.CIR_GOAL_WORDS
    bare = tcm.with_checks(control, **{tcm.WINDOW_KEY: None, "cir_lt": None})
    assert tcm.summary_level_rows(run, bare) == []                  # нет ключей — строк уровней нет


LEVEL_KEY, TARGET_KEY = "nii.transmission.level_world", "nii.nim_lt_target_mgmt"
LEVEL_WORLD = "M"           # мир уровня ключа цели ЧПМ — вход теста (у книги фикстуры ключа нет)


def level_book(book: dict, control: dict, world: str = LEVEL_WORLD, shift: float = 0.0) -> dict:
    """Книга с ключом уровня: ключ цели ЧПМ — стационарный ЧПМ мира world прежнего решения (плюс shift), упр. базис."""
    A = control["ctx"]["A"]
    level = cm.c_to_mgmt(A, "nim", control["ctx"]["tr"]["nss"][world]) + shift
    return put(put(book, LEVEL_KEY, world), TARGET_KEY, level)


@pytest.mark.tact
def test_target_key_is_the_level_of_the_named_world(inputs, control):
    """Ключ уровня (nii.transmission.level_world, подставлен тестом): ключ цели ЧПМ — стационарный ЧПМ названного
    мира на составе якоря. Книга с ключом уровня и ключом цели, равным стационарному ЧПМ этого мира у прежнего
    решения, решается теми же сдвигами и сжатием; мир уровня, равный миру-опоре, — прежнее решение; при другой
    цели стационарный ЧПМ мира уровня равен ей, а на другой цели передачи он неподвижен."""
    book, _ = inputs
    A, tr = control["ctx"]["A"], control["ctx"]["tr"]
    ref_w = control["ctx"]["B"]["nii"]["transmission"]["reference_world"]
    if cm.c_bopt(control["ctx"]["B"], LEVEL_KEY) is None:
        assert tr["level_world"] == ref_w and tr["nss_level"] == tr["nss_ref"]
    same = cm.c_transmission_ctl(cm.c_resolve_anchor_keys(put(book, LEVEL_KEY, tr["level_world"]), A)[0], A)
    assert (same["sigma0"], same["sigma0_liab"], same["phi"]) == (tr["sigma0"], tr["sigma0_liab"], tr["phi"])
    for world in control["ctx"]["worlds"]:
        keyed = cm.c_resolve_anchor_keys(level_book(book, control, world), A)[0]
        got = cm.c_transmission_ctl(keyed, A)
        assert got["level_world"] == world and abs(got["nss_level"] - got["target_eng"]) <= 1e-12
        for name in ("sigma0", "sigma0_liab", "phi", "t_real", "delta0"):
            assert got[name] == pytest.approx(tr[name], abs=1e-12), (world, name)
        for w, v in tr["nss"].items():
            assert got["nss"][w] == pytest.approx(v, abs=1e-12), (world, w)
    moved = cm.c_transmission_ctl(cm.c_resolve_anchor_keys(level_book(book, control, shift=0.004), A)[0], A)
    assert moved["nss"][LEVEL_WORLD] == pytest.approx(tr["nss"][LEVEL_WORLD] + 0.004, abs=1e-12)
    assert moved["nss_level"] == pytest.approx(moved["target_eng"], abs=1e-12)
    assert moved["t_real"] == pytest.approx(tr["t_real"], abs=1e-12)
    # ось передачи: при другой цели передачи мир уровня неподвижен, мир-опора — нет
    t_star = cm.c_bnum(control["ctx"]["B"], "nii.transmission.target")
    if LEVEL_WORLD != ref_w:
        other = put(level_book(book, control), "nii.transmission.target", t_star + 0.05)
        held = cm.c_transmission_ctl(cm.c_resolve_anchor_keys(other, A)[0], A)
        assert held["nss"][LEVEL_WORLD] == pytest.approx(tr["nss"][LEVEL_WORLD], abs=1e-12)
        assert abs(held["nss"][ref_w] - tr["nss"][ref_w]) > 1e-4
        assert held["t_real"] == pytest.approx(t_star + 0.05, abs=1e-12)
    with pytest.raises(cm.ControlInputError):
        cm.c_transmission_ctl(cm.c_resolve_anchor_keys(put(book, LEVEL_KEY, "нет такого мира"), A)[0], A)


@pytest.mark.ci_only
def test_level_world_matches_core_on_the_panel_form(inputs, control):
    """Ключ уровня у обеих моделей на форме панели (подставлен тестом, цель сдвинута): вся сверка М§17 в
    допусках, стационарные ЧПМ миров — одно определение, сдвиг точки от смены цели у моделей один."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    core_facts = book_mod.load_facts(FIXTURE / "facts")
    keyed = level_book(book, control, shift=0.004)
    try:
        base = grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts), core_facts)
        run = grid_mod.run_grid(book_mod.book_from_dict(keyed, facts=core_facts), core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу формы панели с ключом уровня: {type(exc).__name__}: {str(exc)[:500]}")
    ctl = cm.c_control_run(keyed, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк" + chr(10) + tcm._fail_lines(bad)
    for w, v in ctl["transmission"]["nss"].items():
        assert abs(run.ctx.transmission.nss[w] - v) <= tcm.TOL_DERIVED, w
    assert run.ctx.transmission.level_world == ctl["transmission"]["level_world"] == LEVEL_WORLD
    d_core, d_ctl = run.point - base.point, ctl["point"] - control["point"]
    assert d_core != 0.0 and abs(d_ctl - d_core) <= max(tcm.SIGN_TOL_REL * abs(d_core), tcm.SIGN_TOL_RUB), (d_core, d_ctl)


# Годовая проекция книги фикстуры: ветви, которых ядро ещё не исполняет, выключены ключами (календарь —
# годовой, ограничение роста выключено); остальные ключи формы панели остаются.
PROJECTION_CALENDAR = {"agm_quarter": 2, "reg_deduction_quarter": 3, "payment_quarter": 3, "checkpoints": [3, 4]}
# Ветви формы панели, которые годовая проекция выключает (пути помощника потока ядра `support_core_t.OFF`).
ANNUAL_OFF = ("dividends.calendar", "capital.growth_constraint.enabled", "checks.growth_cut", "checks.step_dividend",
              "checks.cir_lt", "checks.wholesale_share", "checks.manual_overdue_days.capital_form",
              "valuation.sensitivities.buffer_pp")
NEAR_ZERO_VALUE = 0.10      # клетка «у нуля»: |V| меньше этой доли капитала на дату оценки


def projection(book: dict) -> dict:
    out = put(put(book, "dividends.calendar", PROJECTION_CALENDAR), "capital.growth_constraint.enabled", False)
    out = put(out, "dividends.policy.base_window_quarters", DROP)
    for key in ("growth_cut", "step_dividend", "cir_lt", "wholesale_share"):
        out["checks"].pop(key, None)
    out["checks"].get("manual_overdue_days", {}).pop("capital_form", None)
    out["valuation"]["sensitivities"].pop("buffer_pp", None)
    return out


# вне такта сервера: годовую ветвь книга репозитория не исполняет — её тесты на фикстуре идут в CI
def test_annual_branch_carries_the_panel_keys(inputs):
    """Ключи формы панели независимы от календаря: на годовой проекции книги контрольная модель идёт
    годовой ветвью (решение раз в год) с двенадцатью книгами, связью с объёмом, премиями по секторам,
    постоянными прочими активами, множителем режима и делителем «размещённые»."""
    book, facts = inputs
    plain = copy.deepcopy(facts)
    plain["dividends"]["register_seed"] = []                         # записи реестра фикстуры — по кварталам прибыли
    res = cm.c_control_run(projection(book), plain)
    assert not res["quarterly"] and res["growth_rule"] is None and res["divisor"] > res["shares_out"]
    for c in res["cells"]:
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        assert all("quarters" not in r and r["v_volume"] is not None for r in c["rows"])
        assert set(c["decisions"]) == set(range(res["years"][0], res["years"][-1]))


@pytest.mark.ci_only
def test_control_matches_core_on_the_annual_projection(inputs):
    """Сверка с ядром на годовой проекции книги фикстуры. Вне допусков М§17 допускаются только строки
    двух известных свойств годовой ветви на этой книге: дивиденд года при связывающем капитале (решение
    раз в год на годовом пробном проходе при росте портфеля на десятки процентов — сумма двух соседних лет
    при этом сходится) и клетки с оценкой у нуля, где относительный допуск не определён."""
    book, facts = inputs
    book_mod, grid_mod = _core_modules()
    # проекция — помощником потока ядра: календарь годовой, ограничение роста выключено, их гейты и
    # чувствительность запаса сняты; остальные ветви формы панели остаются как в книге фикстуры
    support = importlib.import_module("tests.support_core_t")
    data = support.plain_dict(on=tuple(k for k in support.OFF if k not in ANNUAL_OFF)
                              + (support.GUIDANCE_BRANCH, support.BANK_ROWS_BRANCH))
    plain = copy.deepcopy(facts)
    plain["dividends"]["register_seed"] = []
    ctl = cm.c_control_run(data, plain)
    try:
        core_facts = book_mod.load_facts(FIXTURE / "facts")
        core_book = book_mod.book_from_dict(data, facts=core_facts)
        v = dt.date.fromisoformat(str(data["meta"]["valuation_date"]))
        prices = {str(t): float(p) for t, p in data["meta"]["market_price"].items()}
        live = grid_mod.LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=())
        run = grid_mod.run_grid(core_book, core_facts, live)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало годовую проекцию книги формы панели: {type(exc).__name__}: {str(exc)[:500]}")
    assert not ctl["quarterly"] and ctl["growth_rule"] is None      # сверяется годовая ветвь, а не полная форма
    rows = tcm.compare_with_core(run, ctl)
    small = {"/".join((c["world"], c["regime"], c["scenario"])) for c in ctl["cells"]
             if abs(c["v_ri"]) < NEAR_ZERO_VALUE * c["bv_v"]}

    def known(r):
        if r["group"] in ("div", "dps"):
            return True
        return r["group"] in ("cell", "tv") and r["what"].split()[-1] in small

    bad = [r for r in rows if not r["ok"] and not known(r)]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк\n" + tcm._fail_lines(bad)
    assert sum(not r["ok"] for r in rows) <= 0.01 * len(rows)
    # дивиденды двух соседних лет при связывающем капитале сходятся в сумме
    by_cell = collections.defaultdict(dict)
    for r in rows:
        if r["group"] == "div" and r["core"] is not None:
            by_cell[r["what"].split()[-1]][r["what"]] = r
    for cell_rows in by_cell.values():
        core_sum = sum(r["core"] for r in cell_rows.values())
        ctl_sum = sum(r["control"] for r in cell_rows.values())
        assert ctl_sum == pytest.approx(core_sum, rel=tcm.TOL_LINE)
