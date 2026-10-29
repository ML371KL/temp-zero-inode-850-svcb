# -*- coding: utf-8 -*-
"""Контрольная модель: ключи второго прохода ядра Совкомбанка (core-pass2) — контрольные случаи своим счётом.

Ключи (методика — spec.yaml прохода, пример — tests/fixtures/core_pass2/example.json, точная арифметика):

* К3 — опт сверх структурной доли гасится при избытке ликвидности (`volumes.wholesale_structural_to_funds`).
* К7 — резерв по книгам: покрытие книги якоря × остаток книги (`credit.allowance_by_book`, факты
  `balance.allowance_books`).
* К5 — составляющая RWA гарантий, вырезанная из плотности книги, с драйвером — базой комиссий
  (`capital.rwa.guarantees`, факты `capital.guarantees`).
* К4 — терминал от стационарных ставок книг: ЧПД года L и ставки балансирующих за T — при ρ = 1
  (`valuation.terminal.stationary_rates`).
* К2 — база связи по строке (`fees.volume_base`, `other.insurance_volume_base`: loans | funds | iea | nominal | веса
  книг) и доли расходов на драйверах строк (`opex.line_shares`).
* К6 — книга-обязательство за драйвером строки (`volumes.liability_drivers`).
* К1 — жетон DPS в машине роста (`dividends.min_dps`).

Книга — фикстура формы панели (tests/fixtures/core_t) с ключами, подставленными тестом: ключей у неё нет, и
«без ключа — прежняя ветвь» держит сама сводка сверки (data/checks/control_model.json воспроизводится бит в бит).
Сверка с ядром на книге с ключами — строки compare_with_core (tests/test_control_model.py), они появляются только у
книги с ключом.
"""

from __future__ import annotations

import copy
import json
from fractions import Fraction

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
    from tests import test_control_t as tct
    from tests import test_control_pass1 as tp1
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_t as tct                        # type: ignore[no-redef]
    import test_control_pass1 as tp1                    # type: ignore[no-redef]

EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass2" / "example.json"
CELLS = (("H", "norm", "mid"), ("M", "downturn", "strict"), ("N", "crisis", "schedule"))   # клетки расчётов (вход теста)


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def ex(node) -> float:
    """Число примера: точная дробь записи {v, exact} → float (до последнего знака — через Fraction)."""
    if isinstance(node, dict) and "exact" in node:
        return float(Fraction(node["exact"]))
    if isinstance(node, dict) and "v" in node:
        return float(node["v"])
    return float(node)


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def cells_of(book: dict, facts: dict, keys=CELLS) -> tuple[dict, dict]:
    ctx = cm.c_control_context(book, facts)
    return ctx, {k: cm.c_cell_annual(ctx, *k) for k in keys}


def numbers(cell: dict) -> list:
    """Числа клетки для сравнения «бит в бит»: оценка, годовые строки, решения о дивиденде."""
    keys = ("v_ri", "v_ddm", "tv_ri", "x_t", "y_x", "roe_t")
    rows = [{k: v for k, v in r.items() if isinstance(v, (int, float, list, dict))} for r in cell["rows"]]
    return [[cell[k] for k in keys], rows, cell.get("decisions_q"), cell["decisions"]]


@pytest.fixture(scope="module")
def form():
    return tct.t_book(), tct.t_facts()


@pytest.fixture(scope="module")
def plain(form):
    """Клетки фикстуры как есть (ключей второго прохода нет)."""
    return cells_of(*form)


def put(book: dict, dotted: str, value) -> dict:
    return tct.put(book, dotted, value)


# ============================================================================ К3 — опт сверх структурной доли


def with_structural(book: dict, s) -> dict:
    out = copy.deepcopy(book)
    out["volumes"]["wholesale_structural_to_funds"] = s
    return out


@pytest.mark.tact
def test_k3_example_is_the_old_formula_with_base_s():
    """Пример k3: правило «полная база по якорю, затем гашение сверх s при избытке» равно формуле опта контрольной
    модели с базой s: E_wh = s × средства + max(0, la_min − la⁰ − s × средства) (1e-12) — в нехватке, избытке и
    большом избытке; в нехватке — тот же опт, что при доле якоря; в большом избытке — только структурная часть."""
    k3 = example()["k3"]
    funds, s, s_a = ex(k3["funds"]), ex(k3["s_structural"]), ex(k3["s_anchor"])
    for name, case in k3["cases"].items():
        la0, la_min = ex(case["la0_without_wh"]), ex(case["la_min"])
        mine = s * funds + max(0.0, la_min - (la0 + s * funds))
        old = s_a * funds + max(0.0, la_min - (la0 + s_a * funds))
        assert rel(mine, ex(case["wholesale_k3"])) <= 1e-12, name
        assert rel(old, ex(case["wholesale_old"])) <= 1e-12, name
        assert close(max(0.0, la_min - (la0 + s * funds)), ex(case["extra"]), 1e-12), name
    assert rel(s * funds, ex(k3["cases"]["big_surplus"]["wholesale_k3"])) <= 1e-12


def test_k3_is_the_book_with_the_share_s(form, plain):
    """К3(s) ≡ книга с volumes.wholesale_to_funds = s — бит в бит внутри контрольной модели (одна база опта в годовой
    строке и в квартальном проходе); s = доля якоря — прежние числа бит в бит."""
    book, facts = form
    ctx0, cells0 = plain
    s = round(ctx0["wtf"] * 0.6, 6)
    _, keyed = cells_of(with_structural(book, s), facts)
    _, booked = cells_of(put(book, "volumes.wholesale_to_funds", s), facts)
    for key in CELLS:
        assert numbers(keyed[key]) == numbers(booked[key]), key
        assert keyed[key]["v_ri"] != cells0[key]["v_ri"], key
    ctx1, same = cells_of(with_structural(book, ctx0["wtf"]), facts)
    assert ctx1["wtf"] == ctx1["wtf_anchor"] == ctx0["wtf"]
    for key in CELLS:
        assert numbers(same[key]) == numbers(cells0[key]), key


def test_k3_repays_above_the_structural_part(form, plain):
    """Опт конца года — структурная часть s × средства плюс часть по нужде (≥ 0); при свободной ликвидности над
    минимумом часть по нужде — ноль (гашение полное). Опт по нужде ниже, чем добор сверх доли якоря; терминал читает
    опт по нужде (WT_Q). Хотя бы в одном году клетки опт гасится."""
    book, facts = form
    ctx0, cells0 = plain
    s = ctx0["wtf"] * 0.5
    ctx, cells = cells_of(with_structural(book, s), facts)
    m = cm.c_bnum(ctx["B"], "volumes.liquid_min_share")
    freed = 0
    for key, c in cells.items():
        for r, r0 in zip(c["rows"], cells0[key]["rows"]):
            assert r["wholesale_extra"] >= 0.0
            assert close(r["wholesale"], s * r["funds"] + r["wholesale_extra"], 1e-12), key
            la = r["securities"] + r["liquidity"]
            if la > m * (r["assets"] - la) / (1.0 - m) * (1.0 + 1e-9):
                assert r["wholesale_extra"] == 0.0, key
                freed += 1
        assert c["wt"] == max(0.0, c["rows"][-1]["wholesale_extra"])
    assert freed, "ни в одном году ликвидность не свободна — гашение не проверено"


def test_k3_terminal_reads_the_need_part(form):
    """Минимум ликвидности поднят (вход теста), опт по нужде на конце сетки больше нуля: WT_Q терминала — опт сверх
    структурной части s × средства (не сверх доли якоря)."""
    book, facts = form
    tight = put(book, "volumes.liquid_min_share", 0.25)
    s = cm.c_control_context(tight, facts)["wtf"] * 0.5
    _, cells = cells_of(with_structural(tight, s), facts, keys=(("H", "norm", "mid"),))
    c = cells[("H", "norm", "mid")]
    last = c["rows"][-1]
    assert last["wholesale_extra"] > 0.0 and c["wt"] == last["wholesale_extra"]
    assert close(last["wholesale"], s * last["funds"] + c["wt"], 1e-12)


@pytest.mark.tact
def test_k3_refusals(form):
    """Отказы: s < 0, s больше доли опта якоря, не число (строка, null, логическое)."""
    book, facts = form
    anchor = cm.c_control_context(book, facts)["wtf"]
    for s in (-0.01, anchor * 1.01, "0.05", None, True):
        with pytest.raises(cm.ControlInputError, match="wholesale_structural_to_funds"):
            cm.c_control_context(with_structural(book, s), facts)
    assert cm.c_control_context(with_structural(book, 0.0), facts)["wtf"] == 0.0


# ============================================================================ К7 — резерв по книгам


ALLOW = {"cards": 120.0, "cash_loans": 90.0, "auto": 50.0, "mortgage": 10.0, "sme_loans": 20.0, "corp_loans": 50.0}


def with_allowance(book: dict, facts: dict, allow: dict | None = None, *, enabled=True) -> tuple[dict, dict]:
    """Фикстура с ключом credit.allowance_by_book и фактами резерва по книгам (вход теста; по умолчанию — покрытия
    розницы выше, чем у юрлиц и ипотеки, остаток вне книг 10 из 350)."""
    b2, f2 = copy.deepcopy(book), copy.deepcopy(facts)
    b2["credit"]["allowance_by_book"] = {"enabled": enabled}
    f2["balance"]["allowance_books"] = {b: {"v": v, "calc": "тест"} for b, v in (ALLOW if allow is None
                                                                                   else allow).items()}
    return b2, f2


@pytest.mark.tact
def test_k7_example_by_own_code():
    """Пример k7 своим кодом (1e-12): покрытие книги якоря, остаток вне книг, резерв на якоре = факт, резерв пути по
    составу (розница сжимается, юрлица и ипотека растут) и списания W = AL_прош + LLP − AL; равное покрытие — прежнее
    правило «доля якоря × кредиты»."""
    k7 = example()["k7"]
    books0 = {b: ex(v) for b, v in k7["books0"].items()}
    allow = {b: ex(v) for b, v in k7["allowance0_by_book"].items()}
    al0, llp = ex(k7["AL0"]), ex(k7["llp_quarter"])
    rule = cm.c_allowance_cov(books0, allow, al0, {})
    for b, v in k7["coverage"].items():
        assert rel(rule["cov"][b], ex(v)) <= 1e-12, b
    assert close(rule["resid"], ex(k7["residual"]), 1e-12)
    path = [books0, {**books0, "cash_loans": 250.0, "cards": 165.0, "corp_loans": 1850.0, "mortgage": 440.0}]
    prev = None
    for e, row in zip(path, k7["rows"]):
        ac = sum(e.values())
        al = cm.c_allowance_of(rule, e, ac)
        assert rel(al, ex(row["AL_k7"])) <= 1e-12 and rel(ac, ex(row["loans"])) <= 1e-12
        if prev is not None:
            assert rel(prev + llp - al, ex(row["writeoff_k7"])) <= 1e-12
        prev = al
    assert rel(cm.c_allowance_of(rule, books0, sum(books0.values())), al0) <= 1e-12
    flat = cm.c_allowance_cov(books0, {b: al0 / sum(books0.values()) * e for b, e in books0.items()}, al0, {})
    e1 = path[1]
    assert rel(cm.c_allowance_of(flat, e1, sum(e1.values())), al0 / sum(books0.values()) * sum(e1.values())) <= 1e-12


def test_k7_equal_coverage_is_the_anchor_share(form, plain):
    """Равное покрытие у всех книг (доля якоря) и нулевой остаток вне книг — прежнее правило: резерв, баланс, капитал
    и стоимость клеток до 1e-12 (относительно); выключатель false — прежние числа бит в бит."""
    book, facts = form
    ctx0, cells0 = plain
    loans = [b for b, sp in book["nii"]["books"].items() if sp.get("sector")]
    share = ctx0["A"]["AL"] / sum(ctx0["A"]["E0"][b] for b in loans)
    ctx, cells = cells_of(*with_allowance(book, facts, {b: share * ctx0["A"]["E0"][b] for b in loans}))
    assert abs(ctx["allow"]["resid"]) <= 1e-12 * ctx0["A"]["AL"]
    for key in CELLS:
        assert rel(cells[key]["v_ri"], cells0[key]["v_ri"]) <= 1e-12, key
        for r, r0 in zip(cells[key]["rows"], cells0[key]["rows"]):
            for line in ("al", "securities", "wholesale", "bv", "rwa", "ni_sh"):
                assert abs(r[line] - r0[line]) <= 1e-12 * max(1.0, abs(r0[line])), (key, line)
    off_ctx, off = cells_of(*with_allowance(book, facts, enabled=False))
    assert off_ctx["allow"] is None
    for key in CELLS:
        assert numbers(off[key]) == numbers(cells0[key]), key


def test_k7_allowance_follows_the_composition(form, plain):
    """С покрытиями книг: резерв на якоре — факт (1e-12); резерв конца каждого года — Σ покрытие × книга + остаток вне
    книг × кредиты / кредиты якоря (1e-12) и отличается от доли якоря, когда состав сдвигается; меньше резерва —
    больше чистых активов: баланс сходится (тождество активов и пассивов)."""
    book, facts = form
    ctx0, cells0 = plain
    ctx, cells = cells_of(*with_allowance(book, facts))
    rule = ctx["allow"]
    E0 = ctx["A"]["E0"]
    loans = list(rule["cov"])
    assert rel(cm.c_allowance_of(rule, E0, sum(E0[b] for b in loans)), ctx["A"]["AL"]) <= 1e-12
    r_al = cm.c_bnum(ctx["B"], "credit.allowance_ratio")
    moved = 0
    for key, c in cells.items():
        for r in c["rows"]:
            want = sum(rule["cov"][b] * r["books_end"][b] for b in loans) + rule["resid"] * r["loans_ac"] / rule["ac0"]
            assert rel(r["al"], want) <= 1e-12, key
            moved += abs(r["al"] / (r_al * r["loans_ac"]) - 1.0) > 1e-6
            assert rel(r["assets"], r["liabilities"]) <= 1e-9, key
    assert moved, "состав не сдвинул резерв ни в одном году"
    assert any(c["v_ri"] != cells0[k]["v_ri"] for k, c in cells.items())


@pytest.mark.tact
def test_k7_coverage_is_on_amortized_cost():
    """Покрытие книги — резерв к её кредитам по амортизированной стоимости (E − FV): у книги с долей кредитов по
    справедливой стоимости знаменатель меньше валового остатка; резерв книги = покрытие × (E − FV) на любом остатке."""
    rule = cm.c_allowance_cov({"a": 100.0, "b": 50.0}, {"a": 6.0, "b": 2.0}, 8.0, {"a": 0.25})
    assert rule["cov"]["a"] == 6.0 / 75.0 and rule["cov"]["b"] == 2.0 / 50.0 and rule["ac0"] == 125.0
    assert close(cm.c_allowance_of(rule, {"a": 200.0, "b": 50.0}, 200.0), 12.0 + 2.0, 1e-12)


@pytest.mark.tact
def test_k7_refusals(form):
    """Отказы: нет узла фактов или резерва кредитной книги, резерв < 0 или не меньше кредитов книги, остаток вне книг
    больше 5 % резерва якоря, выключатель не логический; выключено — ключ и факты не читаются."""
    book, facts = form
    first = next(iter(ALLOW))
    cases = [dict(ALLOW, **{first: -1.0}), dict(ALLOW, **{first: 1e6}), {b: v * 0.8 for b, v in ALLOW.items()},
             {b: v for b, v in ALLOW.items() if b != first}, dict(ALLOW, **{first: None})]
    for allow in cases:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(*with_allowance(book, facts, allow))
    b2, f2 = with_allowance(book, facts)
    f2["balance"].pop("allowance_books")
    with pytest.raises(cm.ControlInputError, match="allowance_books"):
        cm.c_control_context(b2, f2)
    with pytest.raises(cm.ControlInputError, match="enabled"):
        cm.c_control_context(*with_allowance(book, facts, enabled=None))
    b3, f3 = with_allowance(book, facts, {first: -1.0}, enabled=False)
    assert cm.c_control_context(b3, f3)["allow"] is None


# ============================================================================ К5 — RWA гарантий


GUAR_FACTS = {"nonfinancial": 300.0, "financial": 40.0}


def with_guarantees(book: dict, facts: dict, *, driver: str = "fees_base", base=None, ccf_nf: float = 0.5,
                    notional=None, carve: str = "corp_loans", enabled=True, link0: bool = True,
                    weight: float = 1.1) -> tuple[dict, dict]:
    """Фикстура с ключом capital.rwa.guarantees (вход теста): номиналы — узлы фактов capital.guarantees, CCF
    нефинансовых ccf_nf, финансовых 1, вес 1,1, вырез из corp_loans. base — база комиссий (ключ К2 fees.volume_base)
    для драйвера fees_base; link0 — связь комиссий с объёмом 0 (база читается только драйвером гарантий)."""
    b2, f2 = copy.deepcopy(book), copy.deepcopy(facts)
    b2["capital"]["rwa"]["guarantees"] = {
        "enabled": enabled, "notional": copy.deepcopy(notional or {"nonfinancial": "anchor", "financial": "anchor"}),
        "ccf": {"nonfinancial": ccf_nf, "financial": 1.0}, "weight": weight, "carve_from": carve, "driver": driver}
    if base is not None:
        b2["fees"]["volume_base"] = copy.deepcopy(base)
    if link0:
        b2["fees"]["volume_link"] = 0.0
    f2["capital"]["guarantees"] = {k: {"v": v, "src": "тест"} for k, v in GUAR_FACTS.items()}
    return b2, f2


@pytest.mark.tact
def test_k5_example_by_own_code():
    """Пример k5 своим кодом (1e-12): G_0 = (N_нф × CCF_нф + N_ф × CCF_ф) × вес, плотность после выреза, RWA якоря не
    меняется; путь G по драйверу «кредиты» (концы кварталов), RWA с ключом; драйвер = книга выреза ≡ RWA без ключа."""
    k5 = example()["k5"]
    v = {k: ex(x) for k, x in k5["inputs"].items()}
    corp = [v["e_corp0"], 1800.0, 1830.0, 1850.0]                        # путь примера (example.py, k5_example)
    total = [3157.45, 3200.0, 3290.0, 3380.0]
    dn = [1.0, 1.0, 0.99, 0.98]
    books = {"corp_loans": {"side": "asset", "sector": "corporate"}, "retail": {"side": "asset", "sector": "retail_other"}}
    dens = {"corp_loans": v["w_corp"], "retail": 0.0, "other_assets": 1.0}
    other = 2100.0                                                       # RWA прочих статей — прочие активы с плотностью 1
    E0 = {"corp_loans": corp[0], "retail": total[0] - corp[0]}
    A = {"E0": E0, "guarantees": {"nonfinancial": v["n_nf"], "financial": v["n_f"]}, "anchor": (2026, 2)}

    def rule_of(base):
        B = {"nii": {"books": books}, "fees": {"volume_base": base},
             "capital": {"rwa": {"guarantees": {"enabled": True, "notional": {"nonfinancial": "anchor", "financial": "anchor"},
                                                "ccf": {"nonfinancial": v["ccf_nf"], "financial": v["ccf_f"]},
                                                "weight": v["weight"], "carve_from": "corp_loans", "driver": "fees_base"}}}}
        return cm.c_guarantee_rule(B, A, books, dens, "loans")

    rule = rule_of("loans")
    assert rel(rule["g0"], ex(k5["G0"])) <= 1e-12 and rel(rule["w_carved"], ex(k5["w_carved"])) <= 1e-12
    geo = {"books": books, "dens": dens, "oaf": 0.0, "rwa_mult": {}}
    keyed = dict(geo, guar=rule)
    rwa0_old = cm._c_rwa_of(geo, None, 2026, 2, E0, other, 1.0, 1.0)
    assert rel(cm._c_rwa_of(keyed, None, 2026, 2, E0, other, 1.0, 1.0, guar=rule["g0"]), rwa0_old) <= 1e-12
    assert rel(rwa0_old, ex(k5["rwa0"])) <= 1e-12
    carved = rule_of({"corp_loans": 1.0})
    for q, row in enumerate(k5["rows"]):
        E = {"corp_loans": corp[q], "retail": total[q] - corp[q]}
        lvl = cm.c_base_level(rule["spec"], E, loans=list(books), biz=[], assets=list(books), nominal=1.0)
        g = rule["g0"] * lvl / rule["d0"]
        assert rel(g, ex(row["G"])) <= 1e-12, q
        assert rel(cm._c_rwa_of(keyed, None, 2026, 2, E, other, dn[q], 1.0, guar=g), ex(row["rwa_key"])) <= 1e-12, q
        old = cm._c_rwa_of(geo, None, 2026, 2, E, other, dn[q], 1.0)
        assert rel(old, ex(row["rwa_old"])) <= 1e-12, q
        g_c = carved["g0"] * cm.c_base_level(carved["spec"], E, loans=list(books), biz=[], assets=list(books),
                                             nominal=1.0) / carved["d0"]
        assert rel(cm._c_rwa_of(dict(geo, guar=carved), None, 2026, 2, E, other, dn[q], 1.0, guar=g_c), old) <= 1e-12


def test_k5_driver_on_the_carved_book_is_no_key(form):
    """Драйвер — сама книга выреза (веса {corp_loans: 1}): RWA якоря и RWA в каждом квартале прохода капитала, капитал и
    стоимость клеток — как без ключа (1e-12, относительно); RWA_0 равен (1e-12)."""
    book, facts = form
    base_book = put(book, "fees.volume_link", 0.0)
    ctx0, plain0 = cells_of(base_book, facts)
    ctx, cells = cells_of(*with_guarantees(book, facts, base={"corp_loans": 1.0}))
    assert rel(ctx["rwa0"], ctx0["rwa0"]) <= 1e-12
    for key in CELLS:
        assert rel(cells[key]["v_ri"], plain0[key]["v_ri"]) <= 1e-12, key
        for r, r0 in zip(cells[key]["rows"], plain0[key]["rows"]):
            assert rel(r["rwa"], r0["rwa"]) <= 1e-12 and rel(r["bv"], r0["bv"]) <= 1e-12, key
            for x, x0 in zip(r["quarters"], r0["quarters"]):
                assert rel(x["rwa"], x0["rwa"]) <= 1e-12, key


def test_k5_guarantees_follow_the_fees_base(form):
    """Драйвер — база комиссий «кредиты»: G конца года и каждого квартала прохода = G_0 × кредиты конца / кредиты якоря;
    ряд rwa_guar = G × дрейф × валютный индекс × множитель режима (у кризиса множитель есть — гарантии кризис не
    останавливает); годовая строка и последний квартал — одна G. RWA якоря и нормативы якоря те же; больше CCF — больше
    G_0 и меньше плотность книги выреза при том же RWA_0."""
    book, facts = form
    ctx0 = cm.c_control_context(book, facts)
    ctx, cells = cells_of(*with_guarantees(book, facts, base="loans"))
    gr = ctx["guar"]
    loans0 = sum(ctx["A"]["E0"][b] for b in ctx["loans"])
    assert gr["d0"] == loans0 and rel(ctx["rwa0"], ctx0["rwa0"]) <= 1e-12
    for key, c in cells.items():
        for p, r in zip(ctx["periods"], c["rows"]):
            assert rel(r["guar"], gr["g0"] * r["loans"] / loans0) <= 1e-12, key
            mult = cm.c_rwa_mult(ctx, key[1], p["year"], p["quarters"][-1])
            assert rel(r["rwa_guar"], r["guar"] * r["dn_end"] * r["xf_end"] * mult) <= 1e-12
            for j, x in enumerate(r["quarters"]):
                assert rel(x["guar"], gr["g0"] * x["loans"] / loans0) <= 1e-12, key
                assert rel(x["rwa_guar"], x["guar"] * r["dn_q"][j] * r["xf_q"][j]
                           * cm.c_rwa_mult(ctx, key[1], p["year"], p["quarters"][j])) <= 1e-12
            assert rel(r["quarters"][-1]["guar"], r["guar"]) <= 1e-9, key
    crisis = [c for k, c in cells.items() if k[1] == cm.R_CRISIS]
    assert crisis and any(cm.c_rwa_mult(ctx, cm.R_CRISIS, p["year"], 4) != 1.0 for p in ctx["periods"])
    more = cm.c_control_context(*with_guarantees(book, facts, base="loans", ccf_nf=0.9))
    assert more["guar"]["g0"] > gr["g0"] and more["guar"]["w_carved"] < gr["w_carved"]
    assert rel(more["rwa0"], ctx["rwa0"]) <= 1e-12


def test_k5_fees_line_and_nominal_drivers(form):
    """Драйвер fees_line — строка комиссий за четыре квартала (кварталы до якоря — факты): G_q = G_0 × Σ комиссий
    кварталов q−3…q / Σ четырёх кварталов до якоря включительно; драйвер — база «номинал»: G_q = G_0 × D^N_q, D^N — рост
    с зарплатами мира по четвертям года."""
    book, facts = form
    ctx, cells = cells_of(*with_guarantees(book, facts, driver="fees_line"))
    gr = ctx["guar"]
    y0, qa = ctx["anchor"]
    fact = [cm._c_fact_line(ctx["A"], "fees_net", *cm.c_qback((y0, qa), j)) for j in range(cm.QY)]
    assert rel(gr["d0"], sum(fact)) <= 1e-12
    for key, c in cells.items():
        fees = list(reversed(fact)) + [f for r in c["rows"] for f in r["fees_q"]]
        k = cm.QY - 1
        for r in c["rows"]:
            for j, x in enumerate(r["quarters"]):
                k += 1
                assert rel(x["guar"], gr["g0"] * sum(fees[k - 3:k + 1]) / gr["d0"]) <= 1e-12, (key, k)
    ctx, cells = cells_of(*with_guarantees(book, facts, base="nominal"))
    for key, c in cells.items():
        nom = 1.0
        for p, r in zip(ctx["periods"], c["rows"]):
            for j, x in enumerate(r["quarters"]):
                nom *= (1.0 + cm.c_world_quarter(ctx["B"], key[0], "wage_growth", p["year"], p["quarters"][j])) ** 0.25
                assert rel(x["guar"], ctx["guar"]["g0"] * nom) <= 1e-12, key


@pytest.mark.tact
def test_k5_refusals(form):
    """Отказы: книга выреза — не кредитная; гарантий больше RWA книги выреза; номинал < 0, CCF вне [0; 1], вес ≤ 0;
    anchor без узла фактов; неизвестный драйвер или база; нет поля; выключатель не логический; fees_line без четырёх
    кварталов комиссий до якоря. Выключено — ключ не читается."""
    book, facts = form
    bad = [with_guarantees(book, facts, carve="securities"), with_guarantees(book, facts, ccf_nf=1.0, weight=10.0),
           with_guarantees(book, facts, notional={"nonfinancial": -1.0, "financial": 0.0}),
           with_guarantees(book, facts, ccf_nf=1.2), with_guarantees(book, facts, weight=0.0),
           with_guarantees(book, facts, driver="corp_loans"), with_guarantees(book, facts, base="assets"),
           with_guarantees(book, facts, base={"no_such_book": 1.0}), with_guarantees(book, facts, enabled=None)]
    b2, f2 = with_guarantees(book, facts)
    f2["capital"].pop("guarantees")
    bad.append((b2, f2))
    b3, f3 = with_guarantees(book, facts)
    b3["capital"]["rwa"]["guarantees"].pop("weight")
    bad.append((b3, f3))
    b4, f4 = with_guarantees(book, facts, driver="fees_line")
    y0, qa = cm.c_per_parse(book["meta"]["anchor_period"])
    early = "{}Q{}".format(*cm.c_qback((y0, qa), 3))
    rows = f4["pnl_quarterly"]["quarters"]
    (rows.pop(early) if isinstance(rows, dict) else rows.remove(next(r for r in rows if r["period"] == early)))
    bad.append((b4, f4))
    for b, f in bad:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b, f)
    off = with_guarantees(book, facts, carve="securities", enabled=False)
    assert cm.c_control_context(*off)["guar"] is None


# ============================================================================ К4 — терминал от стационарных ставок


def with_stationary(book: dict, on=True) -> dict:
    return put(book, "valuation.terminal.stationary_rates", on)


def k4_path(inp: dict, quarters: int) -> list[tuple]:
    """Путь книги примера k4 по кварталам: (ставка, средний остаток) — подстройка к цели с ρ, рост остатка g за квартал."""
    y, e, rows = ex(inp["y0"]), ex(inp["e0"]), []
    for _ in range(quarters):
        e_new = e * (1.0 + ex(inp["g_q"]))
        y = y + ex(inp["rho"]) * (ex(inp["target"]) - y)
        rows.append((y, (e + e_new) / 2.0))
        e = e_new
    return rows


@pytest.mark.tact
def test_k4_example_by_own_code():
    """Пример k4 функцией c_stationary_gap (по пятёрке на квартал года L): ΔNII* и ЧПД года L по стационарным ставкам
    (1e-12); при продлении сетки на год вход терминала по стационарным ставкам растёт ровно с остатками, по лаговым —
    нет (разрыв класса 3); ρ = 1 — ΔNII* = 0; смесь балансирующих терминала — по целям."""
    k4 = example()["k4"]
    inp = k4["inputs"]
    dt, target = ex(inp["dt"]), ex(inp["target"])
    star = {}
    for name, nq in (("grid", 8), ("extended", 12)):
        last = k4_path(inp, nq)[-4:]
        d = cm.c_stationary_gap([(1.0, target, y, a, dt) for y, a in last])
        nii = sum(y * a * dt for y, a in last)
        node = k4["paths"][name]
        assert rel(d, ex(node["dNII_star"])) <= 1e-12 and rel(nii + d, ex(node["NII_star_L"])) <= 1e-12, name
        assert all(rel(y, ex(v)) <= 1e-12 for (y, _), v in zip(last, node["rates_L"])), name
        star[name] = (nii, nii + d)
    growth = ex(k4["growth_year"])
    assert rel(star["extended"][1], star["grid"][1] * growth) <= 1e-12
    assert rel(star["extended"][0] / (star["grid"][0] * growth) - 1.0, ex(k4["class3_gap_without_key"])) <= 1e-9
    one = dict(inp, rho={"v": 1.0})
    assert cm.c_stationary_gap([(1.0, target, y, a, dt) for y, a in k4_path(one, 8)[-4:]]) == 0.0
    yb = k4["y_balancing"]
    assert rel(0.45 * 0.08 + 0.55 * 0.07, ex(yb["stationary"])) <= 1e-12


def test_k4_changes_only_the_terminal(form, plain):
    """С ключом явные годы бит в бит те же (меняется только терминал); ΔNII* периода — Σ знак × (цель − ставка) × средний
    остаток × доля года, а ЧПД плюс ΔNII* — ЧПД по целям книг на тех же остатках (1e-9); терминал: PBT_L + ΔNII*_L,
    ставки балансирующих — цели года L (y*_bal — смесь бумаг и ликвидности, c*_wh — опт), лаговые — печать рядом;
    TV_DDM − TV_RI = BV_Q, V_DDM = V_RI. Без ключа печати стационара нет."""
    book, facts = form
    ctx0, cells0 = plain
    ctx, cells = cells_of(with_stationary(book), facts)
    B = ctx["B"]
    sec = cm.c_bnum(B, "volumes.securities_share_of_liquid")
    nci = cm.c_bnum(B, "pnl.nci_share")
    dia = cm.c_bnum(B, "nii.dia_rate")
    assets = [b for b, sp in B["nii"]["books"].items() if sp["side"] == cm.LOANS_SIDE]
    for key in CELLS:
        c, c0 = cells[key], cells0[key]
        assert "terminal_stationary" not in c0 and all("stationary" not in r for r in c0["rows"])
        for r, r0 in zip(c["rows"], c0["rows"]):
            assert {k: v for k, v in r.items() if k != "stationary"} == r0, key
        for p, r in zip(ctx["periods"], c["rows"]):
            st, dfac = r["stationary"], p["days"] / cm.DAYS_BASE
            sgn = {b: (1.0 if b in assets else -1.0) for b in st["avg"]}
            want = sum(sgn[b] * (st["targets"][b] - st["ybar"][b]) * st["avg"][b] * dfac for b in sgn)
            assert close(st["d_nii"], want, 1e-12)
            ovl = r["nii"] - r["nim_books"] * r["iea"] * dfac
            dia_amt = dia * (st["avg"][cm.RETAIL_CURRENT] + st["avg"][cm.RETAIL_TERM]) * dfac
            books_nii = sum(sgn[b] * st["ybar"][b] * st["avg"][b] * dfac for b in sgn)
            assert close(books_nii, r["nii"] - ovl + dia_amt, 1e-9), key
            at_targets = sum(sgn[b] * st["targets"][b] * st["avg"][b] * dfac for b in sgn)
            assert close(r["nii"] + st["d_nii"], at_targets - dia_amt + ovl, 1e-9), key
        last, stat = c["rows"][-1], c["terminal_stationary"]
        tg = last["stationary"]["targets"]
        assert stat["d_nii_l"] == last["stationary"]["d_nii"]
        assert stat["y_bal"] == sec * tg[cm.SECURITIES] + (1.0 - sec) * tg[cm.LIQUIDITY] == c["y_bal"]
        assert stat["c_wh"] == tg[cm.WHOLESALE]
        assert stat["y_bal_lagged"] == c0["y_bal"] and stat["c_wh_lagged"] == last["c_wh_end"]
        want_ni = ((last["pbt"] + stat["d_nii_l"]) * (1.0 + c["g_t"]) - c["y_x"]) * (1.0 - last["tau_eff"]) * (1.0 - nci)
        assert close(c["ni_t1"], want_ni, 1e-12)
        assert close(c["tv_ddm"] - c["tv_ri"], last["bv"]) and abs(c["v_ddm"] / c["v_ri"] - 1.0) <= 1e-9
        assert c["tv_ri"] != c0["tv_ri"]


def test_k4_full_adjustment_is_neutral(form):
    """ρ = 1 у всех книг — ставки на целях: ΔNII* = 0 в каждом периоде, ключ ничего не меняет (стоимость и терминал
    клеток до 1e-12, относительно)."""
    book, facts = form
    fast = copy.deepcopy(book)
    for sp in fast["nii"]["books"].values():
        sp["rho"] = 1.0
    _, a = cells_of(fast, facts)
    _, b = cells_of(with_stationary(fast), facts)
    for key in CELLS:
        assert all(r["stationary"]["d_nii"] == 0.0 for r in b[key]["rows"]), key
        for name in ("v_ri", "tv_ri", "y_x", "ni_t1"):
            assert rel(a[key][name], b[key][name]) <= 1e-12, (key, name)


def test_k4_fixed_block_reads_the_stationary_rates(form):
    """С блоком постоянных частей терминала (λ_F = 0): ставка дохода стоящей доли y_m — c*_wh при связанном минимуме
    ликвидности, иначе y*_bal, — цели года L, а не лаговые ставки. Связанность — в форме ключа книги (Р4-16,
    cm.c_forms): binary — опт по нужде на конце Q (WT_Q > 0), balancing (К-Т2б) — после выплаты избытка (WT* > 0)."""
    book, facts = form
    b2 = put(with_stationary(book), "valuation.terminal.fixed_growth_share", 0.0)
    for funding in (None, cm.FUND_BALANCING):
        b3 = b2 if funding is None else put(b2, "valuation.terminal.fixed_funding", funding)
        ctx, cells = cells_of(b3, facts)
        forms = cm.c_forms(ctx["B"])
        assert forms["funding"] == (funding or cm.FUND_BINARY)
        for key, c in cells.items():
            stat, blk = c["terminal_stationary"], c["terminal_fixed"]
            bound = blk["bound_after_payout"] if forms["funding"] == cm.FUND_BALANCING else c["wt"] > 0.0
            assert blk["y_m"] == (stat["c_wh"] if bound else stat["y_bal"]), key


@pytest.mark.tact
def test_k4_refusals(form):
    """Ключ — логическое: число, строка, null — отказ; false — прежний терминал."""
    book, facts = form
    for v in (1, "true", None):
        with pytest.raises(cm.ControlInputError, match="stationary_rates"):
            cm.c_control_context(with_stationary(book, v), facts)
    assert cm.c_control_context(with_stationary(book, False), facts)["stationary"] is False


# ============================================================================ К2 — база связи по строке


def with_bases(book: dict, *, fees=None, ins=None, shares=None, links=None) -> dict:
    """Фикстура с ключами К2 (вход теста): базы комиссий и страхования, доли расходов на драйверах строк; links —
    связи (комиссии, страхование, расходы) вместо книжных."""
    out = copy.deepcopy(book)
    if fees is not None:
        out["fees"]["volume_base"] = copy.deepcopy(fees)
    if ins is not None:
        out["other"]["insurance_volume_base"] = copy.deepcopy(ins)
    if shares is not None:
        out["opex"]["line_shares"] = dict(shares)
    if links is not None:
        out["fees"]["volume_link"], out["other"]["insurance_volume_link"], out["opex"]["volume_link"] = links
    return out


@pytest.fixture(scope="module")
def hist(form):
    """Факты фикстуры с остатками книг на концах кварталов до якоря, согласованными с узлами loans, iea, funds."""
    book, facts = form
    return tp1.history_books(book, facts)


@pytest.mark.tact
def test_k2_example_by_own_code():
    """Пример k2 своим кодом (1e-12): «номинал» — индекс к тому же кварталу, рост ровно зарплаты (связь 1 с ним = связь
    0 с любой базой); связь 1 со своей базой — строка растёт ровно за базой плюс корень; смесь расходов
    c_opex_mix — A^C по кварталам примера, на якоре A^C_0 = B^C_0, рост смеси в годовой форме (сумма кварталов 1…4 к
    кварталам −3…0); доля 0 и база комиссий = база расходов — прежний рост."""
    k2 = example()["k2"]
    bases = {name: {int(x): ex(v) for x, v in node.items()} for name, node in k2["bases"].items()}
    wage = {int(q): ex(v) for q, v in k2["wage"].items()}
    gvw = {int(q): ex(v) for q, v in k2["gvw"].items()}
    prev = {int(x): ex(v) for x, v in k2["fees_prev_year"].items()}
    for q in range(1, 5):
        assert rel(bases["nominal"][q] / bases["nominal"][q - 4] - 1.0, wage[q]) <= 1e-12
        for base in ("loans", "iea", "nominal"):
            v = bases[base][q] / bases[base][q - 4] - 1.0
            for link in ("1", "3/10", "0"):
                f = prev[q - 4] * (1.0 + wage[q] + gvw[q] + float(Fraction(link)) * (v - wage[q]))
                assert rel(f, ex(k2["fees"][f"{base}|link={link}"]["F"][str(q)])) <= 1e-12, (base, link, q)
        assert rel(ex(k2["fees"]["loans|link=1"]["F"][str(q)]),
                   prev[q - 4] * (1.0 + bases["loans"][q] / bases["loans"][q - 4] - 1.0 + gvw[q])) <= 1e-12
    s_f = ex(k2["opex_mix_share"])
    b_c = {x: 1.5 * bases["loans"][x] + 0.7 * (bases["iea"][x] - bases["loans"][x]) for x in bases["loans"]}
    for name, node in k2["opex_mix"].items():
        a = bases[name]
        mix = {x: cm.c_opex_mix({"fees": s_f}, b_c[x], b_c[0], {"fees": a[x]}, {"fees": a[0]}) for x in a}
        assert all(rel(mix[x], ex(node["A_C"][str(x)])) <= 1e-12 for x in a), name
        assert rel(mix[0], b_c[0]) <= 1e-12
        year = sum(mix[q] for q in range(1, 5)) / sum(mix[x] for x in range(-3, 1)) - 1.0
        want = (sum(ex(node["A_C"][str(q)]) for q in range(1, 5)) / sum(ex(node["A_C"][str(x)]) for x in range(-3, 1))
                - 1.0)
        assert rel(year, want) <= 1e-12, name
        same = {x: cm.c_opex_mix({"fees": s_f}, b_c[x], b_c[0], {"fees": b_c[x]}, {"fees": b_c[0]}) for x in a}
        zero = {x: cm.c_opex_mix({"fees": 0.0}, b_c[x], b_c[0], {"fees": a[x]}, {"fees": a[0]}) for x in a}
        for q in range(1, 5):
            for alt in (same, zero):
                assert rel(alt[q] / alt[q - 4], b_c[q] / b_c[q - 4]) <= 1e-12, name


def test_k2_base_equal_to_the_link_base_is_bit_for_bit(form, plain):
    """Своя база строки, равная volumes.link_base (у фикстуры — loans), — прежние числа бит в бит (одна функция роста);
    ключ при нулевой связи строки не читается (даже неверный)."""
    book, facts = form
    ctx0, cells0 = plain
    link_base = ctx0["link_base"]
    ctx, cells = cells_of(with_bases(book, fees=link_base, ins=link_base), facts)
    assert ctx["k2"]
    for key in CELLS:
        mine = numbers(cells[key])
        for r in mine[1]:
            for extra in ("v_fees", "vol_fees", "v_ins", "vol_ins"):
                r.pop(extra)
        assert mine == numbers(cells0[key]), key
    quiet = with_bases(book, fees="no_such_base", links=(0.0, 0.5, 0.4))
    assert cm.c_control_context(quiet, facts)["line_base"]["fees"] is None


def test_k2_nominal_is_link_zero(form):
    """База «номинал» у строки ≡ связь 0 той же строки: комиссии кварталов бит в бит, стоимость клеток — та же (рост
    «номинала» — рост зарплат каждого квартала, связь умножает ноль)."""
    book, facts = form
    _, a = cells_of(with_bases(book, fees="nominal", ins="nominal"), facts)
    _, b = cells_of(with_bases(book, links=(0.0, 0.0, book["opex"]["volume_link"])), facts)
    for key in CELLS:
        assert a[key]["v_ri"] == b[key]["v_ri"], key
        for ra, rb in zip(a[key]["rows"], b[key]["rows"]):
            assert ra["fees_q"] == rb["fees_q"] and ra["ins_q"] == rb["ins_q"], key


def test_k2_weights_are_the_old_bases(form, hist):
    """Веса 1 на кредитных книгах ≡ база loans, веса 1 на книгах процентных активов ≡ база iea (факты истории книг
    согласованы с узлами; строки, прибыль и стоимость клеток до 1e-9); веса × 7 — тот же рост (1e-12); связь 1 со своей
    базой — комиссии кварталов растут ровно за базой плюс корень (1e-12)."""
    book, _ = form
    facts = hist
    books = book["nii"]["books"]
    loans = {b: 1.0 for b, sp in books.items() if sp.get("sector")}
    assets = {b: 1.0 for b, sp in books.items() if sp["side"] == cm.LOANS_SIDE}
    for weights, kind in ((loans, "loans"), (assets, "iea")):
        _, a = cells_of(with_bases(book, fees=kind, ins=kind), facts)
        _, b = cells_of(with_bases(book, fees=weights, ins=weights), facts)
        tp1.same_cells(a, b, 1e-9)
        _, c = cells_of(with_bases(book, fees={k: 7.0 * v for k, v in weights.items()},
                                   ins={k: 7.0 * v for k, v in weights.items()}), facts)
        tp1.same_cells(b, c, 1e-12)
    ctx, one = cells_of(with_bases(book, fees=loans, links=(1.0, 0.5, 0.4)), facts)
    gvw = cm.c_bget(ctx["B"], "fees.growth_vs_wages")
    for key, c in one.items():
        fq = {(p["year"], q): r["fees_q"][j] for p, r in zip(ctx["periods"], c["rows"]) for j, q in enumerate(p["quarters"])}
        seen = 0
        for p, r in zip(ctx["periods"], c["rows"]):
            for j, q in enumerate(p["quarters"]):
                if (p["year"] - 1, q) in fq:
                    want = fq[(p["year"] - 1, q)] * (1.0 + r["v_fees"] + cm.c_traj_at(gvw, p["year"], q))
                    assert rel(r["fees_q"][j], want) <= 1e-12, (key, p["year"], q)
                    seen += 1
        assert seen


def test_k2_opex_shares(form, hist):
    """Доли расходов на драйверах строк: доля 0 — рост расходов прежний (1e-12); база комиссий = база расходов — тоже;
    своя база комиссий («номинал») с долей 0,2 меняет расходы, но не комиссии; печать смеси — v_opex и vol_opex."""
    book, _ = form
    facts = hist
    link_base = cm.c_control_context(book, facts)["link_base"]
    _, a = cells_of(book, facts)
    _, zero = cells_of(with_bases(book, shares={"fees": 0.0}), facts)
    _, same = cells_of(with_bases(book, fees=link_base, shares={"fees": 0.3}), facts)
    _, nom = cells_of(with_bases(book, fees="nominal"), facts)
    _, mix = cells_of(with_bases(book, fees="nominal", shares={"fees": 0.2}), facts)
    for key in CELLS:
        tp1.same_cells(a, zero, 1e-12)
        tp1.same_cells(a, same, 1e-12)
        for rn, rm in zip(nom[key]["rows"], mix[key]["rows"]):
            assert rn["fees_q"] == rm["fees_q"] and rn["opex"] != rm["opex"], key
            assert rm["vol_opex"] > 0.0 and "v_opex" in rm
        assert all("v_opex" not in r for r in a[key]["rows"])


@pytest.mark.tact
def test_k2_refusals(form, hist):
    """Отказы: база — неизвестное имя, null, пустой словарь, вес не книги, вес < 0, все веса 0; доли — сумма ≥ 1, доля
    вне [0; 1), неизвестная строка; нет конца квартала истории книги с весом — отказ входа."""
    book, facts = form
    first = next(iter(book["nii"]["books"]))
    for bad in ("assets", None, {}, {"no_such_book": 1.0}, {first: -1.0}, {first: 0.0}):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_bases(book, fees=bad) if bad is not None
                                 else put(book, "fees.volume_base", None), facts)
    for shares in ({"fees": 0.6, "insurance": 0.5}, {"fees": -0.1}, {"fees": 1.0}, {"opex": 0.1}):
        with pytest.raises(cm.ControlInputError, match="line_shares"):
            cm.c_control_context(with_bases(book, shares=shares), facts)
    with pytest.raises(cm.ControlInputError, match="books"):
        cells_of(with_bases(book, fees={first: 1.0}), facts, keys=CELLS[:1])
    assert cm.c_control_context(with_bases(book, shares={"fees": 0.5, "insurance": 0.6},
                                           links=(0.5, 0.5, 0.0)), facts)["line_shares"] is None


# ============================================================================ К6 — книга-обязательство за драйвером


DRIVEN = "corp_funds"            # средства клиентов-бизнеса фикстуры — ведомая книга теста


def with_driven(book: dict, line: str = "insurance", *, link=None, base=None, book_name: str = DRIVEN) -> dict:
    out = copy.deepcopy(book)
    out["volumes"]["liability_drivers"] = {book_name: line}
    key = "other.insurance_volume" if line == "insurance" else "fees.volume"
    head, name = key.split(".")
    if link is not None:
        out[head][f"{name}_link"] = link
    if base is not None:
        out[head][f"{name}_base"] = copy.deepcopy(base)
    return out


def wage_index(ctx: dict, world: str, upto: tuple) -> float:
    """Индекс зарплат мира от якоря до конца квартала upto: Π (1 + wage)^(1/4) (вход теста)."""
    out = 1.0
    for p in ctx["periods"]:
        for q in p["quarters"]:
            if (p["year"], q) > upto:
                return out
            out *= (1.0 + cm.c_world_quarter(ctx["B"], world, "wage_growth", p["year"], q)) ** 0.25
    return out


@pytest.mark.tact
def test_k6_example_by_own_code():
    """Пример k6 функцией c_driven_path (1e-12): связь 1 — ровно за драйвером, связь ½ — смесь, связь 0 — за индексом
    зарплат."""
    k6 = example()["k6"]
    wage, driver = [float(x) for x in k6["wage"]], [float(x) for x in k6["driver_end"]]
    for lam, want in k6["paths"].items():
        path = cm.c_driven_path({"lam": float(lam)}, float(k6["E0"]), driver, wage)
        assert all(rel(a, float(b)) <= 1e-12 for a, b in zip(path[1:], want)), lam
    one = cm.c_driven_path({"lam": 1.0}, float(k6["E0"]), driver, wage)
    assert rel(one[-1] / one[0], driver[-1] / driver[0]) <= 1e-12


def test_k6_driven_book_follows_its_driver(form):
    """Ведомая книга (средства бизнеса фикстуры за строкой страхования, база — кредиты): связь 0 — рост ровно с индексом
    зарплат мира, связь 1 — ровно за кредитами на концах периодов и кварталов прохода капитала (1e-12); база «номинал» —
    индекс зарплат при любой связи; книга остаётся в средствах клиентов (опт — от них), баланс сходится, квартальный
    проход кончает год на той же книге (1e-9)."""
    book, facts = form
    for link, base, kind in ((0.0, None, "wage"), (1.0, None, "loans"), (0.5, "nominal", "wage")):
        ctx, cells = cells_of(with_driven(book, link=link, base=base), facts)
        E0 = ctx["A"]["E0"]
        l0 = sum(E0[b] for b in ctx["loans"])
        assert ctx["driven"][DRIVEN]["lam"] == link
        for key, c in cells.items():
            for p, r in zip(ctx["periods"], c["rows"]):
                end = r["driven_end"][DRIVEN] / E0[DRIVEN]
                want = r["loans"] / l0 if kind == "loans" else wage_index(ctx, key[0], (p["year"], p["quarters"][-1]))
                assert rel(end, want) <= 1e-12, (link, key, p["year"])
                for x, q in zip(r["quarters"], p["quarters"]):
                    qw = x["loans"] / l0 if kind == "loans" else wage_index(ctx, key[0], (p["year"], q))
                    assert rel(x["driven"][DRIVEN] / E0[DRIVEN], qw) <= 1e-12, (link, key, p["year"], q)
                assert rel(r["quarters"][-1]["driven"][DRIVEN], r["driven_end"][DRIVEN]) <= 1e-9
                assert rel(r["assets"], r["liabilities"]) <= 1e-9
                assert close(r["wholesale"], ctx["wtf"] * r["funds"] + r["wholesale_extra"], 1e-12)


def test_k6_empty_map_is_no_key(form, plain):
    """Пустой словарь — ключа нет: прежние числа бит в бит."""
    book, facts = form
    _, cells0 = plain
    b2 = put(book, "volumes.liability_drivers", {})
    ctx, cells = cells_of(b2, facts)
    assert ctx["driven"] is None
    for key in CELLS:
        assert numbers(cells[key]) == numbers(cells0[key]), key


@pytest.mark.tact
def test_k6_refusals(form):
    """Отказы: книга — актив, балансирующая, пара средств физлиц или не книга; строка не insurance и не fees; база
    строки iea или funds (у фикстуры — подменой link_base), веса на балансирующих книгах или на самой книге (круг);
    null."""
    book, facts = form
    bad = [with_driven(book, book_name="cards"), with_driven(book, book_name=cm.WHOLESALE),
           with_driven(book, book_name=cm.RETAIL_TERM), with_driven(book, book_name="no_such_book"),
           with_driven(book, "opex"), with_driven(book, base="iea"), with_driven(book, base="funds"),
           with_driven(book, base={cm.SECURITIES: 1.0, "cards": 1.0}), with_driven(book, base={DRIVEN: 1.0}),
           put(with_driven(book, "fees"), "volumes.link_base", "funds"),
           put(book, "volumes.liability_drivers", None)]
    for b2 in bad:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b2, facts)
    ok = cm.c_control_context(with_driven(book, base={"cards": 1.0, cm.RETAIL_CURRENT: 2.0}), facts)
    assert ok["driven"][DRIVEN]["spec"]["kind"] == "weights"


# ============================================================================ К1 — жетон DPS в машине роста


def with_min_dps(book: dict, value=12.0) -> dict:
    return put(book, "dividends.min_dps", {"LT": value} if isinstance(value, (int, float)) else value)


TOKEN_FIELDS = ("token", "token_rule")


def without_token_fields(cell: dict) -> list:
    out = numbers(cell)
    out[2] = [{k: v for k, v in d.items() if k not in TOKEN_FIELDS} for d in out[2]]
    for r in out[1]:
        if "decisions_q" in r:
            r["decisions_q"] = [{k: v for k, v in d.items() if k not in TOKEN_FIELDS} for d in r["decisions_q"]]
    for y in out[3].values():
        y["quarters"] = {per: {k: v for k, v in d.items() if k not in TOKEN_FIELDS} for per, d in y["quarters"].items()}
    return out


@pytest.mark.tact
def test_k1_example_by_own_code():
    """Пример k1 функциями c_token_need и c_token_paid (1e-12): недостача года до жетона, запас есть — год выходит ровно
    на жетон; запаса мало — по правилу (жетона нет); убыток — m_Y = 0; тонкая прибыль — кап прибылью на размещённую
    акцию; избыток после жетона X = ε × max(0, H_fin − Div_base − жетон)."""
    k1 = example()["k1"]
    inp = k1["inputs"]
    n_iss, n_c, prior = ex(inp["n_iss"]), ex(inp["n_c"]), ex(inp["prior_dps"])
    shares = [ex(x["div"]) for x in k1["shares"]]
    div_base = ex(k1["div_base"])
    assert rel(sum(shares), div_base) <= 1e-12
    for name, case in k1["cases"].items():
        by = ex(inp["base_year"]) if name in ("room_ok", "room_short") else (-3.0 if name == "loss_year" else 0.5)
        h_floor = 5.0 if name == "room_short" else 10.0
        tok = cm.c_token_need(min_dps=ex(inp["min_dps"]), base_year=by, n_iss=n_iss, n_c=n_c, closed_dps=0.0,
                              prior_dps=prior, same_dps=sum(shares) * 1000.0 / n_c)
        token = cm.c_token_paid(tok["need"], h_floor, div_base)
        for mine, theirs in ((tok["m_Y"], "m_Y"), (tok["S_Y"], "S_Y"), (tok["need"], "need"), (token, "token")):
            assert close(mine, ex(case[theirs]), 1e-12), (name, theirs, mine)
        assert (token > 0.0) == case["paid"], name
        assert close(prior + (div_base + token) * 1000.0 / n_c, ex(case["dps_year"]), 1e-12), name
    ok = k1["excess_after_token"]
    token = ex(k1["cases"]["room_ok"]["token"])
    assert close(ex(ok["eps"]) * max(0.0, ex(ok["h_fin"]) - div_base - token), ex(ok["X"]), 1e-12)


def test_k1_zero_token_and_off_switch_are_bit_for_bit(form, plain):
    """min_dps ≡ 0 — числа клеток бит в бит (поля жетона — печать); ограничение роста выключено — ключ не читается
    (даже неверный); без ключа полей жетона нет."""
    book, facts = form
    _, cells0 = plain
    ctx, cells = cells_of(with_min_dps(book, 0.0), facts)
    assert ctx["min_dps"] == {"LT": 0.0}
    for key in CELLS:
        assert without_token_fields(cells[key]) == numbers(cells0[key]), key
        assert all("token" not in d for d in cells0[key]["decisions_q"])
        assert any("token_rule" in d for d in cells[key]["decisions_q"])
    free = put(with_min_dps(book, -1.0), "capital.growth_constraint.enabled", False)
    assert cm.c_control_context(free, facts)["min_dps"] is None


def token_years(cell: dict) -> dict:
    """Год прибыли → (жетон, правило жетона) решения-носителя (вход теста)."""
    return {d["year"]: (d["token"], d["token_rule"]) for d in cell["decisions_q"] if "token_rule" in d}


def test_k1_token_fills_the_year_and_respects_the_floor(form):
    """Год с жетоном: DPS года прибыли = m_Y (1e-12) — без догоняющей выплаты и избытка; жетон уплачен ⇒ запас над
    требованием без запаса менеджмента при наименьшей доле прироста покрывает базовый дивиденд модели и жетон, а после
    записи квартала норматив не ниже min(требование с глиссадой − tol, требование без запаса); отказ по полу — DPS по
    правилу; год убытка — m_Y = 0; год шока — носителя нет; границы дивиденда квартала: Σ дивидендов модели ≤ max(0,
    H_ref, H_fin) + жетон."""
    book, facts = form
    keys = CELLS + (("N", "crisis", "mid"),)
    ctx, cells = cells_of(with_min_dps(book, 12.0), facts, keys)
    B = ctx["B"]
    thr = cm.c_bnum(B, "dividends.policy.threshold")
    tol = ctx["growth"]["tol"]
    paid = refused = loss = 0
    for key, c in cells.items():
        quarters = {x["q"]: x for r in c["rows"] for x in r["quarters"]}
        for y, (token, rule) in token_years(c).items():
            year = c["decisions"].get(y)
            if token > 0.0:
                paid += 1
                assert rule["h_floor"] >= rule["model_base"] + token
                parts = list(year["quarters"].values())
                if all(d["catch"] == 0.0 and d["excess"] == 0.0 for d in parts):
                    assert close(year["dps"], rule["m_Y"], 1e-12), (key, y)
                d = next(x for x in c["decisions_q"] if x["year"] == y and "token_rule" in x)
                x = quarters[d["q"]]
                yq = cm.c_qper(ctx["anchor"], d["q"])
                req0_20 = max(thr, cm._c_floor(B, key[2], "n20_0", *yq))
                req0_11 = cm._c_floor(B, key[2], "n1_1", *yq)
                assert x["n20"] >= min(x["req20_glide"] - tol, req0_20) - 1e-12, (key, y)
                assert x["n11_star"] >= min(x["req11_glide"] - tol, req0_11) - 1e-12, (key, y)
            elif rule["need"] > 0.0:
                refused += 1
                assert rule["h_floor"] < rule["model_base"] + rule["need"]
            if rule["m_Y"] == 0.0:
                loss += 1
                assert token == 0.0
        for x in c["decisions_q"]:
            if x["source"] == "crisis_skip":
                assert "token_rule" not in x
            if "token_rule" in x:
                rule, ev = x["token_rule"], x["token_rule"]["eval"]
                yq = cm.c_qper(ctx["anchor"], x["q"])
                req0_20 = max(thr, cm._c_floor(B, key[2], "n20_0", *yq))
                assert ev["floor20"] == cm._c_floor(B, key[2], "n20_0", *yq)
                assert ev["floor11"] == cm._c_floor(B, key[2], "n1_1", *yq)
                want = min((ev["n20"] - req0_20) * ev["rwa"], (ev["n11_star"] - ev["floor11"]) * ev["rwa"])
                assert close(rule["h_floor"], want, 1e-12), (key, x["period"])
                # оценка запаса — при наименьшей доле прироста (у фикстуры λ_min = 0): растущие книги стоят на конце
                # прошлого квартала
                row = next(r for p, r in zip(ctx["periods"], c["rows"]) if p["year"] == yq[0])
                j = list(ctx["periods"][[p["year"] for p in ctx["periods"]].index(yq[0])]["quarters"]).index(yq[1])
                if ctx["growth"]["lam_min"] == 0.0 and all(v > 0.0 for v in row["m_q"].values()):
                    prev = quarters[x["q"] - 1]["loans"] if x["q"] - 1 in quarters else None
                    if prev is not None:
                        assert close(ev["loans"], prev, 1e-12), (key, x["period"])
                eps = cm.c_excess_share(B, x["year"])
                base_q = sum(d["base_div"] for d in c["decisions_q"] if d["q"] == x["q"] and d["source"] == "policy")
                if x["lam"] == 1.0:
                    want_x = eps * max(0.0, x["headroom_final"] - base_q - x["token"] - x["catch"])
                    assert close(x["excess"], want_x, 1e-12), (key, x["period"])
                if x["token"] > 0.0 and x["lam"] > ctx["growth"]["lam_min"]:
                    xq = quarters[x["q"]]
                    assert xq["n20"] >= xq["req20_glide"] - tol - 1e-9, (key, x["period"])
                    assert xq["n11_star"] >= xq["req11_glide"] - tol - 1e-9, (key, x["period"])
        for q, x in quarters.items():
            mine = [d for d in c["decisions_q"] if d["q"] == q and d["source"] == "policy"]
            if mine:
                bound = max(0.0, mine[0]["headroom"], mine[0]["headroom_final"]) + sum(d.get("token", 0.0) for d in mine)
                assert sum(d["div"] for d in mine) <= bound + 1e-9, (key, q)
    assert paid and loss, (paid, refused, loss)
    _, big = cells_of(with_min_dps(book, 60.0), facts, keys)
    assert any(t == 0.0 and r["need"] > 0.0 for c in big.values() for t, r in token_years(c).values()), "нет отказа по полу"


def test_k1_token_only_at_the_carrier_and_on_the_cell_shares(form):
    """Карта лагов, при которой решения за второй–четвёртый кварталы прибыли принимаются в одном квартале (как у книги
    Совкомбанка): жетон несёт только решение-носитель (четвёртый квартал прибыли), год с жетоном — ровно m_Y; с выкупом
    по цене мира недостача считается на акциях клетки после покупок квартала (N_c,q < N_out): DPS года — тот же m_Y."""
    book, facts = form
    lags = put(with_min_dps(book, 12.0), "dividends.calendar.decision_lag_quarters", {"1": 4, "2": 4, "3": 3, "4": 2})
    for b2 in (lags, tp1.with_buyback(lags)):
        ctx, cells = cells_of(b2, facts)
        paid = 0
        for key, c in cells.items():
            for d in c["decisions_q"]:
                if d.get("token") and "token_rule" not in d:
                    raise AssertionError((key, d["period"], "жетон не у носителя"))
            for y, (token, rule) in token_years(c).items():
                parts = list(c["decisions"][y]["quarters"].values())
                if token > 0.0 and all(d["catch"] == 0.0 and d["excess"] == 0.0 for d in parts):
                    paid += 1
                    assert close(c["decisions"][y]["dps"], rule["m_Y"], 1e-12), (key, y)
                    carrier_q = next(d["q"] for d in c["decisions_q"] if "token_rule" in d and d["year"] == y)
                    assert sum(d["q"] == carrier_q and d["source"] == "policy" for d in c["decisions_q"]) >= 2
        assert paid
        if ctx["bb"] is not None:
            n_of = {x["q"]: x["n_out"] for c in cells.values() for r in c["rows"] for x in r["quarters"]}
            assert any(n < ctx["A"]["N_out"] for n in n_of.values())


def test_k1_excess_after_the_token(form):
    """Избыток решения-носителя при λ* = 1 — за вычетом жетона: X = ε × max(0, H_fin − Div_base − жетон − догоняющая);
    в клетках с запасом (избыток с первого года прибыли, ввод за год — вход теста) жетон и избыток идут вместе, и DPS года
    — m_Y плюс избыток на акцию."""
    book, facts = form
    b2 = put(put(with_min_dps(book, 20.0), "dividends.excess.from_profit_year", 2026), "dividends.excess.ramp_years", 1)
    keys = (("N", "soft", "mid"), ("H", "soft", "schedule"))
    ctx, cells = cells_of(b2, facts, keys)
    both = 0
    for key, c in cells.items():
        for d in c["decisions_q"]:
            if "token_rule" not in d or d["lam"] != 1.0:
                continue
            base_q = sum(x["base_div"] for x in c["decisions_q"] if x["q"] == d["q"] and x["source"] == "policy")
            eps = cm.c_excess_share(ctx["B"], d["year"])
            assert close(d["excess"], eps * max(0.0, d["headroom_final"] - base_q - d["token"] - d["catch"]), 1e-12)
            if d["token"] > 0.0 and d["excess"] > 0.0:
                both += 1
                year = c["decisions"][d["year"]]
                extra = sum(x["excess"] + x["catch"] for x in year["quarters"].values()) * 1000.0 / ctx["A"]["N_out"]
                assert close(year["dps"], d["token_rule"]["m_Y"] + extra, 1e-12), (key, d["year"])
    assert both


def test_k1_more_min_dps_never_less_dividend(form):
    """Монотонность: больше min_dps — DPS года с жетоном у обоих счётов не меньше (жетон поднимает год до m_Y). Годы
    после жетона монотонности не обещают: уплаченный жетон уменьшает капитал, и при связывающем капитале дивиденд
    следующего года по правилу может быть ниже (M/downturn/strict фикстуры: 2028 год, −0,005 ₽)."""
    book, facts = form
    _, lo = cells_of(with_min_dps(book, 6.0), facts)
    _, hi = cells_of(with_min_dps(book, 12.0), facts)
    seen = 0
    for key in CELLS:
        tl, th = token_years(lo[key]), token_years(hi[key])
        for y, d in hi[key]["decisions"].items():
            if y in tl and y in th and tl[y][0] > 0.0 and th[y][0] > 0.0:
                assert d["dps"] >= lo[key]["decisions"][y]["dps"] - 1e-9, (key, y)
                seen += 1
    assert seen


def test_k1_memory_is_per_cell_path(form):
    """Память DPS по годам прибыли — у прохода клетки: повтор клетки на том же контексте и клетка, посчитанная после
    другой, дают те же числа."""
    book, facts = form
    ctx = cm.c_control_context(with_min_dps(book, 12.0), facts)
    first = cm.c_cell_annual(ctx, *CELLS[2])
    cm.c_cell_annual(ctx, *CELLS[0])
    again = cm.c_cell_annual(ctx, *CELLS[2])
    assert numbers(first) == numbers(again)


@pytest.mark.tact
def test_k1_refusals(form):
    """Отказы: значение < 0 (в том числе LT), строка, null; при выключенном ограничении роста или годовом календаре —
    ключ не читается."""
    book, facts = form
    for bad in (-0.1, {"2027": 0.35, "LT": -0.1}, "0.35", None, True):
        with pytest.raises(cm.ControlInputError, match="min_dps"):
            cm.c_control_context(with_min_dps(book, bad) if bad is not None else put(book, "dividends.min_dps", None),
                                 facts)
    assert cm.c_control_context(with_min_dps(book, {"2027": 0.5, "LT": 0.35}), facts)["min_dps"] is not None


# ============================================================================ сверка с ядром: строки ключей на заглушке


def all_keys(book: dict, facts: dict) -> tuple[dict, dict]:
    """Фикстура со всеми ключами второго прохода, которые уже считает контрольная модель."""
    b2, f2 = copy.deepcopy(book), copy.deepcopy(facts)
    b2 = with_structural(b2, cm.c_control_context(book, facts)["wtf"] * 0.5)
    b2, f2 = with_allowance(b2, f2)
    b2, f2 = with_guarantees(b2, f2, base="loans", link0=False)
    b2 = with_stationary(b2)
    b2 = with_bases(b2, ins="nominal", shares={"fees": 0.2})
    b2 = with_driven(b2)
    b2 = with_min_dps(b2, 12.0)
    return b2, f2


LEVEL_GROUPS = {"wholesale", "allowance", "rwa_guar", "d_nii_l", "driven"}
NEW_GROUPS = LEVEL_GROUPS | {"v_fees", "v_ins", "v_opex", "token", "token_dps"}


def test_reconciliation_rows_of_the_keys_on_a_stub_core(form):
    """Строки сверки ключей второго прохода появляются только у книги с ключами, несут форму П§2 и свой допуск:
    заглушка ядра из чисел контрольной модели (× 1/1,01, отношения + 0,001) — все строки в допуске; та же заглушка
    без полей ключей — строки «нет у ядра»; у книги без ключей групп ключей нет."""
    ctl = cm.c_control_run(*all_keys(*form))
    near = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    rows = tcm.compare_with_core(near, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, tcm._fail_lines(bad)
    groups = {r["group"] for r in rows}
    assert NEW_GROUPS <= groups, NEW_GROUPS - groups
    doc = tcm.checks_document(near, ctl, as_of="2026-10-21", commit=None)
    assert doc["all_ok"]
    for r in doc["rows"]:
        tcm._assert_row_form(r)
    far = tcm.compare_with_core(tcm._stub_core(ctl, 1.0 / 1.2), ctl)
    assert all(any(not r["ok"] for r in far if r["group"] == g) for g in LEVEL_GROUPS)    # рост баз масштаб не меняет
    bare = tcm._stub_core(ctl, 1.0)
    for key in {(c["world"], c["regime"], c["scenario"]) for c in ctl["cells"]}:
        cell = bare.cell(*key)
        for name in ("wholesale", "allowance", "rwa_guar", "vol_fees", "vol_ins", "vol_opex"):
            cell.quarters.pop(name, None)
        for name in ("terminal_stationary", "books", "decisions"):
            if hasattr(cell, name):
                delattr(cell, name)
    gone = [r for r in tcm.compare_with_core(bare, ctl) if r["group"] == "missing"]
    assert gone and all(not r["ok"] for r in gone)
    plain_run = cm.c_control_run(*form)
    assert not NEW_GROUPS & {r["group"] for r in tcm.compare_with_core(tcm._stub_core(plain_run, 1.0), plain_run)}
