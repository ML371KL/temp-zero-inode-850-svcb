# -*- coding: utf-8 -*-
"""Контрольная модель: ключи первого прохода ядра Совкомбанка (core-pass1) — контрольные случаи своим счётом.

Ключи (методика — spec.yaml прохода, пример — tests/fixtures/core_pass1/example.json, точная арифметика):

* М7 — множители CoR по кредитным книгам (`credit.book_relative`): нормировка на составе якоря (пример m7), книжная
  форма с множителями сегментов — та же сегментная схема, равные множители — CoR без схемы, CoR на составе якоря
  (ряд cor_mix0) и гейт сверки с окном фактов на нём, отказы ключа.
* М13 — драйвер расходов, взвешенный по себестоимости книг (`opex.volume_weights`): пример m13 (история и годовая
  форма), веса 1 на процентных активах — база iea, веса кредитных книг — база loans, комиссии и страхование на своей
  базе, отказы ключа и входа.
* К-Т — постоянные в рублях части за концом сетки (`valuation.terminal.fixed_growth_share`, `fixed_parts`): пример
  terminal своим блоком, замкнутые формы, нейтральный актив, прежняя ветвь при λ_F = 1, тождество, линейность, входы
  блока из клетки, отказы.
* М3 — выкуп акций по цене мира (`dividends.buyback`): пример m3 рабочими функциями прохода, тождества клеток с
  выкупом, правило market и нулевой выкуп, знак цены покупки, путь от даты и цены книги, год шока, d^R записи реестра,
  неподвижная точка cell_value, отказы.

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
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_t as tct                        # type: ignore[no-redef]

EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass1" / "example.json"
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


def cells_of(book: dict, facts: dict, keys=CELLS) -> tuple[dict, dict]:
    ctx = cm.c_control_context(book, facts)
    return ctx, {k: cm.c_cell_annual(ctx, *k) for k in keys}


@pytest.fixture(scope="module")
def form():
    return tct.t_book(), tct.t_facts()


@pytest.fixture(scope="module")
def plain(form):
    """Прогон фикстуры как есть (ключей первого прохода нет)."""
    return cm.c_control_run(*form)


# ============================================================================ М7 — множители CoR по книгам


def loan_books(book: dict) -> dict:
    return {b: sp for b, sp in book["nii"]["books"].items() if sp.get("sector")}


def with_book_rel(book: dict, by_book: dict) -> dict:
    out = copy.deepcopy(book)
    out["credit"]["segment_relative"] = {"enabled": False, "corporate": None, "retail": None}
    out["credit"]["book_relative"] = {"enabled": True, "by_book": dict(by_book)}
    return out


@pytest.mark.tact
def test_m7_example_normalizes_on_the_anchor():
    """Пример m7 своим кодом: r̂ = r / Σ w r на составе якоря (факты Совкомбанка), Σ w r̂ = 1, книжная форма с
    множителями сегментов — множители сегментов, ось ипотеки — перенормировка по сырым значениям."""
    m7 = example()["m7"]
    anchor = {b: ex(v) for b, v in m7["anchor_ac"].items()}
    raw = {b: ex(v) for b, v in m7["raw"].items()}
    books = {b: {"side": "asset", "sector": "corporate" if b == "corp_loans" else "retail_other",
                 "cor_segment": "corporate" if b == "corp_loans" else "retail"} for b in anchor}

    def mult(by_book):
        B = {"nii": {"books": books}, "credit": {"segment_relative": {"enabled": False},
                                                   "book_relative": {"enabled": True, "by_book": by_book}}}
        return cm.c_book_cor_mult(B, {"E0": anchor}, {})

    hat = mult(raw)
    for b, v in m7["normalized"].items():
        assert rel(hat[b], ex(v)) <= 1e-12, (b, hat[b], ex(v))
    total = sum(anchor.values())
    assert abs(sum(anchor[b] / total * hat[b] for b in anchor) - 1.0) <= 1e-12
    seg = mult({b: 0.55 if b == "corp_loans" else 1.60 for b in anchor})
    for b, v in m7["segment_equivalence"]["book_form"].items():
        assert rel(seg[b], ex(v)) <= 1e-12, (b, seg[b], ex(v))
    for m, node in m7["mortgage_axis_renormalized"].items():
        axis = mult(dict(raw, mortgage=float(Fraction(m))))
        assert all(rel(axis[b], ex(v)) <= 1e-12 for b, v in node.items()), m
    # квартал примера: резервы при множителях книг и CoR на составе якоря
    q = m7["quarter"]
    llp = sum(hat[b] * ex(q["cor_cell"]) * ex(q["avg"][b]) * ex(q["dt"]) for b in anchor)
    assert rel(llp, ex(q["llp"])) <= 1e-12


def test_m7_book_form_of_segment_multipliers_is_the_segment_scheme(form):
    """Книжная форма с сырыми множителями сегментов (0,55 у книг сегмента corporate, 1,60 у розничных) — та же
    сегментная схема: резервы, FVC, капитал и стоимость клеток до 1e-9."""
    book, facts = form
    seg = copy.deepcopy(book)
    seg["credit"]["segment_relative"] = {"enabled": True, "corporate": 0.55, "retail": 1.60}
    by_book = {b: 0.55 if sp["cor_segment"] == "corporate" else 1.60 for b, sp in loan_books(book).items()}
    _, a = cells_of(seg, facts)
    _, b = cells_of(with_book_rel(book, by_book), facts)
    for key in CELLS:
        assert rel(a[key]["v_ri"], b[key]["v_ri"]) <= 1e-9, key
        for ra, rb in zip(a[key]["rows"], b[key]["rows"]):
            for line in ("llp", "fvc", "bv", "ni_sh", "rwa"):
                assert abs(ra[line] - rb[line]) <= 1e-9 * max(1.0, abs(ra[line])), (key, line)


def test_m7_equal_multipliers_are_no_scheme(form):
    """Все сырые множители равны — CoR как без схемы: резервы и стоимость клеток до 1e-12 (относительно)."""
    book, facts = form
    _, a = cells_of(book, facts)
    _, b = cells_of(with_book_rel(book, {x: 1.7 for x in loan_books(book)}), facts)
    for key in CELLS:
        assert rel(a[key]["v_ri"], b[key]["v_ri"]) <= 1e-12, key
        assert all(abs(r0["llp"] - r1["llp"]) <= 1e-12 * abs(r0["llp"]) for r0, r1 in zip(a[key]["rows"], b[key]["rows"]))


def test_m7_cor_on_the_anchor_mix_and_the_window_gate(form):
    """Ряд cor_mix0 — CoR клетки периода (путь + κ-добавка + отклонение A-P2u), резервы на составе якоря — та же CoR
    на кредитах по амортизированной стоимости; реализованная CoR смещается составом. Гейт сверки с окном фактов
    при ключе сверяет коридор с CoR на составе якоря, реализованная печатается рядом."""
    book, facts = form
    raw = {b: (0.4 if sp["sector"] == "mortgage" else 0.6 if sp["cor_segment"] == "corporate" else 2.5)
           for b, sp in loan_books(book).items()}
    b2 = with_book_rel(book, raw)
    b2.setdefault("checks", {})["window_backtest"] = {"from_year": 2031, "cor": [0.0, 1.0], "cir": [0.0, 1.0]}
    run = cm.c_control_run(b2, facts)
    hat = run["ctx"]["book_rel"]
    E0 = run["ctx"]["A"]["E0"]
    total = sum(E0[b] for b in hat)
    assert abs(sum(E0[b] / total * hat[b] for b in hat) - 1.0) <= 1e-12
    moved = 0
    for c in run["cells"]:
        for p, r in zip(run["ctx"]["periods"], c["rows"]):
            assert r["cor_mix0"] == r["cor"]
            assert rel(r["llp_mix0"], r["cor"] * r["loans_ac_avg"] * p["days"] / cm.DAYS_BASE) <= 1e-12
            assert all(r["cor_book"][b] == r["cor"] * hat[b] for b in hat)
            moved += abs(r["llp"] / r["llp_mix0"] - 1.0) > 1e-6
    assert moved, "множители книг не сдвинули резервы ни в одной клетке"
    window = cm.c_window_backtest(run)
    layer = cm.c_levels(run)["mixes"][cm.LAYER_MARKET]
    assert window["cor"] == layer["cor_mix0"] and window["cor_realized"] == layer["cor"]
    assert window["cor"] != window["cor_realized"]
    # коридор вокруг одной из двух CoR: вердикт следует CoR на составе якоря, а не реализованной
    for around, inside in ((layer["cor_mix0"], True), (layer["cor"], False)):
        lane = [around - 0.00001, around + 0.00001]
        gate = cm.c_window_backtest(tcm.with_checks(run, window_backtest={"from_year": 2031, "cor": lane,
                                                                          "cir": [0.0, 1.0]}))
        assert gate["ok"] == inside and (("cor" in gate["outside"]) != inside), (lane, gate)


@pytest.mark.tact
def test_m7_fair_value_book_on_the_sample_form():
    """Форма образца (кредиты по справедливой стоимости в книге с fv_share, годовая ветвь): доли якоря — кредиты по
    амортизированной стоимости (Σ w r̂ = 1 на них, не на валовых остатках); FVC книги с fv_share несёт её r̂ (при
    заданном пути кредитов строка FVC пропорциональна r̂ книги), равные множители — счёт без схемы."""
    sample = cm.ROOT / "tests" / "fixtures" / "core"
    book = json.loads((sample / "book.json").read_text(encoding="utf-8"))
    facts = cm.c_facts_bundle(sample / "facts")
    loans = loan_books(book)
    fv_book = next(b for b, sp in loans.items() if "fv_share" in sp)
    scen = book["capital"]["reg_scenarios"]["ids"]
    keys = ((book["worlds"]["ids"][0], "norm", scen[0]), (book["worlds"]["ids"][-1], "crisis", scen[-1]))
    ctx0, plain = cells_of(book, facts, keys)
    ctx1, equal = cells_of(with_book_rel(book, {b: 1.0 for b in loans}), facts, keys)
    ctx2, heavy = cells_of(with_book_rel(book, {b: (2.0 if b == fv_book else 1.0) for b in loans}), facts, keys)
    hat, fv, E0 = ctx2["book_rel"], ctx2["fv"], ctx2["A"]["E0"]
    assert fv_book in fv and fv[fv_book] > 0.0
    ac0 = {b: E0[b] * (1.0 - fv.get(b, 0.0)) for b in loans}
    assert abs(sum(ac0[b] / sum(ac0.values()) * hat[b] for b in loans) - 1.0) <= 1e-12
    seen = 0
    for key in keys:
        assert rel(plain[key]["v_ri"], equal[key]["v_ri"]) <= 1e-12
        for r0, r2 in zip(equal[key]["rows"], heavy[key]["rows"]):
            if r0["fvc"]:
                seen += 1
                assert rel(r2["fvc"], r0["fvc"] * hat[fv_book]) <= 1e-12, key
    assert seen and hat[fv_book] != 1.0


@pytest.mark.tact
def test_m7_refusals(form):
    """Отказы ключа: вместе с сегментной схемой; набор книг не равен кредитным книгам; множитель ≤ 0 или null;
    выключатель не логический."""
    book, facts = form
    loans = loan_books(book)
    good = {b: 1.0 for b in loans}
    both = with_book_rel(book, good)
    both["credit"]["segment_relative"] = {"enabled": True, "corporate": 0.55, "retail": 1.6}
    short = dict(good)
    short.pop(next(iter(short)))
    bad = [both, with_book_rel(book, short), with_book_rel(book, dict(good, securities=1.0)),
           with_book_rel(book, dict(good, **{next(iter(good)): 0.0})),
           with_book_rel(book, dict(good, **{next(iter(good)): None}))]
    odd = with_book_rel(book, good)
    odd["credit"]["book_relative"]["enabled"] = None
    bad.append(odd)
    for b2 in bad:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b2, facts)
    off = with_book_rel(book, short)
    off["credit"]["book_relative"]["enabled"] = False              # выключено — ключ не читается
    assert cm.c_control_context(off, facts)["book_rel"] is None


# ============================================================================ М13 — драйвер расходов по себестоимости книг


def history_books(book: dict, facts: dict) -> dict:
    """Факты с остатками книг на концах кварталов до якоря, согласованными с узлами истории: кредитные книги —
    долями якоря от loans, бумаги и ликвидность — долями якоря от iea − loans, средства клиентов — долями якоря от
    funds (опт — тем же темпом). Сумма кредитных книг равна loans, процентных активов — iea, средств клиентов — funds."""
    out = copy.deepcopy(facts)
    bal = out["balance"]
    E0 = {b: cm._c_nodeval(v) for b, v in bal["books"].items()}
    books = book["nii"]["books"]
    loans = [b for b, sp in books.items() if sp.get("sector")]
    liquid = [b for b, sp in books.items() if sp["side"] == cm.LOANS_SIDE and not sp.get("sector")]
    funds = [b for b, sp in books.items() if sp["side"] != cm.LOANS_SIDE and b != cm.WHOLESALE]
    l0, q0, f0 = (sum(E0[b] for b in group) for group in (loans, liquid, funds))
    anchor = book["meta"]["anchor_period"]
    for per, rec in bal["history"].items():
        if per >= anchor:
            continue
        val = {k: cm._c_nodeval(v) for k, v in rec.items()}
        rec["books"] = {**{b: {"v": E0[b] * val["loans"] / l0} for b in loans},
                        **{b: {"v": E0[b] * (val["iea"] - val["loans"]) / q0} for b in liquid},
                        **{b: {"v": E0[b] * val["funds"] / f0} for b in funds + [cm.WHOLESALE]}}
    return out


def with_weights(book: dict, weights: dict | None, *, base: str | None = None, link: float | None = None) -> dict:
    out = copy.deepcopy(book)
    if weights is not None:
        out["opex"]["volume_weights"] = dict(weights)
    if base is not None:
        out["volumes"]["link_base"] = base
    if link is not None:
        out["opex"]["volume_link"] = link
    return out


def same_cells(a: dict, b: dict, tol: float, lines=("opex", "fees", "ins", "pbt", "bv")) -> None:
    for key in a:
        assert rel(a[key]["v_ri"], b[key]["v_ri"]) <= tol, key
        for ra, rb in zip(a[key]["rows"], b[key]["rows"]):
            for line in lines:
                assert abs(ra[line] - rb[line]) <= tol * max(1.0, abs(ra[line])), (key, line, ra[line], rb[line])


@pytest.mark.tact
def test_m13_example_history_and_annual_form():
    """Пример m13 своим кодом: взвешенная база квартала до якоря — полусумма взвешенных концов фактов по книгам
    (x = −3…0 примера), рост года в годовой форме — сумма взвешенных средних четырёх кварталов к той же сумме прошлого
    года (1e-12)."""
    m13 = example()["m13"]
    ends = {b: [ex(v) for v in vals] for b, vals in m13["inputs"]["ends_x_minus4_to_4"].items()}
    w = {b: ex(v) for b, v in m13["inputs"]["weights"].items()}
    y = 2031                                            # год клетки x = 1…4; якорь — его прошлый четвёртый квартал
    hist = {f"{y - 2}Q4": {b: ends[b][0] for b in ends}}
    hist.update({f"{y - 1}Q{q}": {b: ends[b][q] for b in ends} for q in (1, 2, 3)})
    ctx = {"A": {"E0": {b: ends[b][4] for b in ends}, "history_books": hist}, "opex_w": w, "anchor": (y - 1, cm.QY)}
    base = {int(x): ex(v) for x, v in m13["weighted_base"].items()}
    for x in (-3, -2, -1, 0):
        q = x + cm.QY                                   # x = −3…0 — кварталы 1…4 года якоря
        pq, py = (q - 1, y - 1) if q > 1 else (cm.QY, y - 2)
        mine = (cm.c_weighted_end(ctx, py, pq) + cm.c_weighted_end(ctx, y - 1, q)) / 2.0
        assert rel(mine, base[x]) <= 1e-12, x
    now = sum(base[x] for x in (1, 2, 3, 4))
    v = cm.c_volume_growth_weighted(ctx, {"vend": {}}, y, (1, 2, 3, 4), now)
    assert rel(v, now / sum(base[x] for x in (-3, -2, -1, 0)) - 1.0) <= 1e-12
    scaled = dict(ctx, opex_w={b: 7.0 * x for b, x in w.items()})
    assert rel(cm.c_volume_growth_weighted(scaled, {"vend": {}}, y, (1, 2, 3, 4), 7.0 * now), v) <= 1e-12


def test_m13_unit_weights_on_interest_assets_are_the_iea_base(form):
    """Веса 1 на книгах процентных активов (факты истории согласованы с iea) — расходы, прибыль и стоимость клеток те
    же, что у базы связи iea без весов (1e-9); веса × 7 — тот же счёт (1e-12)."""
    book, facts = form
    facts = history_books(book, facts)
    assets = {b: 1.0 for b, sp in book["nii"]["books"].items() if sp["side"] == cm.LOANS_SIDE}
    _, a = cells_of(with_weights(book, None, base="iea"), facts)
    _, b = cells_of(with_weights(book, assets, base="iea"), facts)
    same_cells(a, b, 1e-9)
    _, c = cells_of(with_weights(book, {k: 7.0 * v for k, v in assets.items()}, base="iea"), facts)
    same_cells(b, c, 1e-12)
    for key in CELLS:
        for r in b[key]["rows"]:
            assert r["v_opex"] is not None and r["vol_opex"] > 0.0


def test_m13_loan_weights_are_the_loans_base(form):
    """Вес 1 у кредитных книг, 0 у прочих — расходы и стоимость клеток те же, что у базы связи loans (1e-9); вес 1 у
    книг средств клиентов (пассивы без опта) — счёт базы funds (комиссии и страхование без связи: их база другая)."""
    book, facts = form
    facts = history_books(book, facts)
    loans = {b: (1.0 if sp.get("sector") else 0.0) for b, sp in book["nii"]["books"].items()}
    _, a = cells_of(with_weights(book, None, base="loans"), facts)
    _, b = cells_of(with_weights(book, loans, base="loans"), facts)
    same_cells(a, b, 1e-9)
    alone = copy.deepcopy(book)
    alone["fees"]["volume_link"] = 0.0
    alone["other"]["insurance_volume_link"] = 0.0
    funds = {x: 1.0 for x, sp in book["nii"]["books"].items() if sp["side"] != cm.LOANS_SIDE and x != cm.WHOLESALE}
    _, c = cells_of(with_weights(alone, None, base="funds"), facts)
    _, d = cells_of(with_weights(alone, funds, base="loans"), facts)
    same_cells(c, d, 1e-9)


@pytest.mark.tact
def test_m13_fees_and_insurance_keep_their_base(form):
    """Ключ весов — суждение о расходах: при пути кредитов, заданном книгой (ограничение роста выключено), и базе связи
    loans комиссии и страхование бит в бит те же, расходы — другие; вес пассива меняет расходы (пассивы читаются)."""
    book, facts = form
    facts = history_books(book, facts)
    free = copy.deepcopy(book)
    free["capital"]["growth_constraint"]["enabled"] = False
    free["other"]["insurance_volume_link"] = 0.3
    mixed = {b: (2.0 if sp.get("sector") else 0.5) for b, sp in book["nii"]["books"].items()
             if sp["side"] == cm.LOANS_SIDE}
    _, a = cells_of(with_weights(free, None, base="loans"), facts)
    _, b = cells_of(with_weights(free, mixed, base="loans"), facts)
    liab = next(x for x, sp in book["nii"]["books"].items() if sp["side"] != cm.LOANS_SIDE)
    _, c = cells_of(with_weights(free, dict(mixed, **{liab: 3.0}), base="loans"), facts)
    for key in CELLS:
        for ra, rb, rc in zip(a[key]["rows"], b[key]["rows"], c[key]["rows"]):
            assert ra["fees_q"] == rb["fees_q"] and ra["ins_q"] == rb["ins_q"], key
            assert rb["opex"] != ra["opex"] and rc["opex"] != rb["opex"], key


@pytest.mark.tact
def test_m13_refusals_and_missing_history(form):
    """Отказы ключа: не книга nii.books, вес < 0 или null, все веса нулевые, ключ null; нет конца квартала истории книги
    с весом — отказ входа. При нулевой связи расходов с объёмом ключ не читается."""
    book, facts = form
    full = history_books(book, facts)
    first = next(iter(book["nii"]["books"]))
    for weights in ({"no_such_book": 1.0}, {first: -1.0}, {first: None}, {first: 0.0}, {}):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_weights(book, weights), full)
    nul = with_weights(book, None)
    nul["opex"]["volume_weights"] = None
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(nul, full)
    with pytest.raises(cm.ControlInputError, match="books"):
        cells_of(with_weights(book, {first: 1.0}), facts, keys=CELLS[:1])        # фактов по книгам нет
    holed = copy.deepcopy(full)
    per = sorted(p for p in holed["balance"]["history"] if "books" in holed["balance"]["history"][p])[0]
    holed["balance"]["history"][per]["books"].pop(first)
    with pytest.raises(cm.ControlInputError, match=first):
        cells_of(with_weights(book, {first: 1.0}), holed, keys=CELLS[:1])
    zero_link = with_weights(book, {"no_such_book": -1.0}, link=0.0)
    assert cm.c_control_context(zero_link, facts)["opex_w"] is None


# ============================================================================ терминал К-Т — постоянные в рублях части


def example_block(t: dict, lam=None, parts=cm.FIXED_PARTS) -> dict:
    """Блок терминала примера своим кодом: капитальная форма примера (избыток по Н20.0 и Н20.1 на RWA конца Q,
    DPreg и фонд 0, доход на избыток — ставка смеси) даёт X_T, j*, CI_T+1; блок — c_terminal_fixed. lam None или 1 —
    прежняя ветвь (тот же блок при λ_F = 1 — общая формула, сверяется с прежней строкой примера)."""
    v = {k: ex(x) for k, x in t.items() if not isinstance(x, bool)}
    k, pi = v["k_T"], v["pi"]
    g = (1.0 + pi) * (1.0 + v["real_growth"]) - 1.0
    x20 = v["BV_Q"] + v["AT1"] + v["T2_Q"] - v["kappa20"] * v["RWA_Q"]
    x11 = v["BV_Q"] - v["kappa11"] * v["RWA_Q"]
    x_t = min(x20, x11)
    binding = cm.BINDING_N20 if x20 <= x11 else cm.BINDING_N11
    keep = (1.0 - v["tau_eff"]) * (1.0 - v["nci"])
    ci_t1 = (v["PBT_L"] * (1.0 + g) - v["y_bal"] * x_t) * keep - v["CPN"] * (1.0 - v["tau_stat"])
    return cm.c_terminal_fixed(
        lam=1.0 if lam is None else lam, parts=parts, x_t=x_t, binding=binding, bv_q=v["BV_Q"], ci_t1=ci_t1, k=k, g=g,
        fade=v["fade"], kappa=v["kappa20"] if binding == cm.BINDING_N20 else v["kappa11"], r_f=v["R_F"],
        f_a=v["OA_fixed"], at1=v["AT1"], t2=v["T2_Q"], nci_amt=v["NCI"], dp_fix=v["DP_fix"],
        y_m=v["c_wh"] if v["WT_Q"] > 0 else v["y_bal"], cpn=v["CPN"], tau=v["tau_eff"], tau_stat=v["tau_stat"],
        nci=v["nci"], misc_l=v["MISC_L"] + v["NC_L"], pi=pi, label="пример")


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


@pytest.mark.tact
def test_terminal_example_by_own_code():
    """Пример terminal своим кодом до 1e-9: прежняя ветвь (λ_F = 1), λ_F = 0 и ½ — поля блока, TV_RI и TV_DDM, ROE
    бизнеса; тождество TV_DDM − TV_RI = BV_Q; цены частей и их сумма; линейность по λ_F."""
    tm = example()["terminal"]
    t = tm["inputs"]
    old = example_block(t)
    assert close(old["tv_ri"], ex(tm["old"]["TV_RI"])) and close(old["tv_ddm"], ex(tm["old"]["TV_DDM"]))
    pairs = {"F_K": "f_k", "D_F": "d_f", "I_F": "i_f", "m_L": "m_l", "B": "business_capital", "CI_B": "ci_business",
             "X_B": "x_b", "phi": "phi", "ROE_T": "roe_business", "ROE_T_faded": "roe_business_faded",
             "TV_RI": "tv_ri", "TV_DDM": "tv_ddm", "y_m": "y_m", "kappa": "kappa", "R_F": "r_f", "F_A": "f_a"}
    for lam, node in ((0.0, tm["lam_0"]), (0.5, tm["lam_half"])):
        mine = example_block(t, lam)
        for theirs, ours in pairs.items():
            assert close(mine[ours], ex(node[theirs])), (lam, theirs, mine[ours], ex(node[theirs]))
        assert mine["binding"] == node["j_star"]
        assert close(mine["tv_ddm"] - mine["tv_ri"], ex(t["BV_Q"]))
    for part, delta in tm["price_by_part_lam_0_minus_old"].items():
        assert close(example_block(t, 0.0, (part,))["tv_ri"] - old["tv_ri"], ex(delta)), part
    assert close(example_block(t, 0.0)["tv_ri"] - old["tv_ri"], ex(tm["all_parts"]))
    if tm["linear_in_lambda_checked"]:
        assert close(example_block(t, 0.5)["tv_ri"], (example_block(t, 0.0)["tv_ri"] + old["tv_ri"]) / 2.0)


@pytest.mark.tact
def test_terminal_closed_forms_and_neutral_asset():
    """Замкнутые формы при ROE_T < k_T (λ_F: 1 → 0) — только T2, только AT1, только постоянный актив, только строки в
    реальных рублях — числа примера до 1e-9; нейтральность: бездоходный актив A, оплаченный капиталом (κ ΔR_F = A),
    при λ_F = 0 не меняет TV_DDM, а TV_RI снижает ровно на A. Капитал бизнеса B ≤ 0 — отказ с меткой клетки."""
    tm = example()["terminal"]
    t = tm["inputs"]
    low = dict(t, PBT_L=150)
    zero = {"AT1": 0, "T2_Q": 0, "NCI": 0, "OA_fixed": 0, "R_F": 0, "MISC_L": 0, "CPN": 0}
    cases = {"a_T2_only": ("T2_Q",), "b_real_rubles_only": ("MISC_L",), "c_fixed_asset_only": ("OA_fixed", "R_F"),
             "d_AT1_only": ("AT1", "CPN")}
    for name, keep in cases.items():
        case = dict(low, **{k: v for k, v in zero.items() if k not in keep})
        delta = example_block(case, 0.0)["tv_ri"] - example_block(case)["tv_ri"]
        assert close(delta, ex(tm["closed_forms_roe_below_k"][name]["delta"])), name
    a = 50.0
    k20 = ex(t["kappa20"])
    neu = dict(t, OA_fixed=ex(t["OA_fixed"]) + a, R_F=ex(t["R_F"]) + a / k20, BV_Q=ex(t["BV_Q"]) + a,
               RWA_Q=ex(t["RWA_Q"]) + a / k20)
    base, moved = example_block(t, 0.0), example_block(neu, 0.0)
    assert close(moved["tv_ddm"], base["tv_ddm"]) and close(base["tv_ri"] - moved["tv_ri"], a)
    assert close(moved["tv_ddm"], ex(tm["neutral_asset"]["TV_DDM_lam0"]))
    with pytest.raises(cm.ControlInputError, match="пример"):
        example_block(dict(t, R_F=1e6), 0.0)


def fixed_form(book: dict, facts: dict) -> tuple[dict, dict]:
    """Фикстура с непустыми частями блока: постоянные прочие активы с плотностью, бессрочные инструменты с купоном
    (остальное — как у фикстуры: T2, неконтролирующие доли, постоянный остаток «дивиденды к выплате», «прочее»,
    пакет)."""
    b2, f2 = copy.deepcopy(book), copy.deepcopy(facts)
    b2["capital"]["rwa"]["density"]["other_assets_fixed"] = 1.0
    f2["balance"]["equity"]["at1"] = {"v": 20.0}
    f2["capital"]["at1"]["coupon_annual"] = {"v": 2.0}
    return b2, f2


KEEP = object()


def with_lam(book: dict, lam, parts=KEEP) -> dict:
    out = copy.deepcopy(book)
    out["valuation"]["terminal"]["fixed_growth_share"] = lam
    if parts is not KEEP:
        out["valuation"]["terminal"]["fixed_parts"] = parts
    return out


def test_terminal_block_on_the_panel_form(form):
    """На форме панели: λ_F = 1 — прежние числа бит в бит; при λ_F ∈ {0; ½} явные годы те же бит в бит (ключ — параметр
    оценки), TV_DDM − TV_RI = BV_Q и V_DDM = V_RI в каждой клетке, ROE терминала — ROE бизнеса; линейность по λ_F
    внутри одной ветви угасания."""
    book, facts = fixed_form(*form)
    _, plain = cells_of(book, facts)
    _, one = cells_of(with_lam(book, 1.0), facts)
    _, zero = cells_of(with_lam(book, 0.0), facts)
    _, half = cells_of(with_lam(book, 0.5), facts)
    for key in CELLS:
        assert one[key]["v_ri"] == plain[key]["v_ri"] and one[key]["tv_ri"] == plain[key]["tv_ri"]
        assert "terminal_fixed" not in one[key]
        for run in (zero, half):
            c = run[key]
            assert [r["bv"] for r in c["rows"]] == [r["bv"] for r in plain[key]["rows"]]
            assert close(c["tv_ddm"] - c["tv_ri"], c["rows"][-1]["bv"])
            assert abs(c["v_ddm"] / c["v_ri"] - 1.0) <= 1e-9
            blk = c["terminal_fixed"]
            assert c["roe_t"] == blk["roe_business_faded"] and c["roe_t_raw"] == blk["roe_business"]
            assert blk["r_f"] > 0.0 and blk["f_a"] > 0.0 and blk["m_l"] > 0.0
        same_branch = (zero[key]["terminal_fixed"]["x_b"] > 0.0) == (plain[key]["roe_t_raw"] > plain[key]["k_t"])
        if same_branch:
            assert close(half[key]["tv_ri"], (zero[key]["tv_ri"] + plain[key]["tv_ri"]) / 2.0)
    assert any(close(half[k]["tv_ri"], (zero[k]["tv_ri"] + plain[k]["tv_ri"]) / 2.0) for k in CELLS)


def test_terminal_inputs_of_the_cell(form):
    """Входы блока из клетки: F_A — постоянные прочие активы, R_F — их RWA конца года L (плотность × дрейф ×
    валютный индекс × множитель режима), κ — требование связывающего норматива − (поправка − вычет сценария) + вычеты
    якоря на RWA_0, AT1 и T2 конца Q — в капитале связывающего Н20.0, постоянные пассивы — неконтролирующие доли и
    постоянный остаток дивидендов к выплате, m_L — «прочее» и пакет года L после налога и доли меньшинства."""
    book, facts = fixed_form(*form)
    ctx, cells = cells_of(with_lam(book, 0.0), facts)
    # второй норматив связывает на терминале: требование Н20.1 поднято (вход теста)
    tight = with_lam(book, 0.0)
    tight["capital"]["mgmt_buffer"]["n1_1"] = tight["capital"]["mgmt_buffer"]["n1_1"] + 0.03
    ctx2, cells2 = cells_of(tight, facts)
    bound = {blk["binding"] for c in list(cells.values()) + list(cells2.values()) for blk in (c["terminal_fixed"],)}
    assert bound == {cm.BINDING_N20, cm.BINDING_N11}, bound
    check_terminal_inputs(ctx, cells)
    check_terminal_inputs(ctx2, cells2)


def check_terminal_inputs(ctx: dict, cells: dict) -> None:
    B, A = ctx["B"], ctx["A"]
    for key in cells:
        c = cells[key]
        blk, last = c["terminal_fixed"], c["rows"][-1]
        # j* — норматив с меньшим избытком конца Q без DPreg_Q (при равенстве — Н20.0)
        drop = last["dpreg"] / last["rwa"]
        x20, x11 = last["n20"] - drop - last["req20"], last["n11_star"] - drop - last["req11"]
        assert blk["binding"] == (cm.BINDING_N20 if x20 <= x11 else cm.BINDING_N11), key
        assert blk["f_a"] == ctx["oaf"]
        assert close(blk["r_f"], ctx["dens_oaf"] * ctx["oaf"] * last["dn_end"] * last["xf_end"])
        p = ctx["periods"][-1]
        s = key[2]
        j = blk["binding"]
        slot = "n20_0" if j == cm.BINDING_N20 else "n1_1"
        cap = "n20" if j == cm.BINDING_N20 else "n11"
        dp = cm.c_traj_at(cm.c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.{slot}"), p["year"], cm.QY)
        want = (last["req20" if j == cm.BINDING_N20 else "req11"] - (cm.c_bnum(B, f"capital.{cap}.gap_pp") - dp)
                + cm.c_bnum(B, f"capital.{cap}.deductions_anchor") / ctx["rwa0"])
        assert close(blk["kappa"], want)
        t2 = cm.c_traj_at(cm.c_bget(B, "capital.n20.t2"), p["year"], cm.QY)
        chi = 1.0 if j == cm.BINDING_N20 else 0.0
        assert close(blk["f_k"], blk["kappa"] * blk["r_f"] - chi * (A["AT1"] + t2))
        assert close(blk["d_f"], ctx["oaf"] - blk["f_k"] - A["AT1"] - (A["NCI"] + ctx["divcal"]["perm"]))
        keep = (1.0 - last["tau_eff"]) * (1.0 - cm.c_bnum(B, "pnl.nci_share"))
        assert close(blk["m_l"], (last["misc"] + last["noncore"]) * keep)


@pytest.mark.tact
def test_terminal_refusals(form):
    """Отказы ключей блока: λ_F вне [0; 1], null или не число; части — неизвестная, повтор, пустой список, null.
    Части проверяются и без λ_F; без λ_F блока нет."""
    book, facts = form
    for lam in (-0.1, 1.5, None, "0", True):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_lam(book, lam), facts)
    for parts in (["no_such_part"], ["real_rubles", "real_rubles"], [], None, "real_rubles"):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_lam(book, 0.0, parts), facts)
        bare = copy.deepcopy(book)
        bare["valuation"]["terminal"]["fixed_parts"] = parts
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(bare, facts)
    assert cm.c_control_context(book, facts)["term_fixed"] is None
    rule = cm.c_control_context(with_lam(book, 0, ["real_rubles"]), facts)["term_fixed"]
    assert rule == {"lam": 0.0, "parts": ("real_rubles",)}


# ============================================================================ сверка с ядром: строки ключей на заглушке


def all_keys(book: dict, facts: dict) -> tuple[dict, dict]:
    """Фикстура со всеми четырьмя ключами прохода (М7, М13, К-Т, М3) и фактами по книгам для М13."""
    b2, f2 = fixed_form(book, facts)
    f2 = history_books(b2, f2)
    raw = {b: (0.4 if sp["sector"] == "mortgage" else 0.6 if sp["cor_segment"] == "corporate" else 2.5)
           for b, sp in loan_books(b2).items()}
    b2 = with_book_rel(b2, raw)
    b2 = with_weights(b2, {b: (2.0 if sp.get("sector") else 0.5) for b, sp in b2["nii"]["books"].items()
                           if sp["side"] == cm.LOANS_SIDE})
    b2 = with_lam(with_buyback(b2), 0.0)
    b2["meta"]["labels"]["control"]["lines"][tcm.BUYBACK_LINE] = "выкуп акций"
    return b2, f2


def test_reconciliation_rows_of_the_keys_on_a_stub_core(form):
    """Строки сверки ключей прохода (N_T, S_c, выкуп за год; F_K, D_F, I_F; CoR на составе якоря; рост взвешенной базы
    расходов) появляются только у книги с ключами, несут форму П§2 и свой допуск: заглушка ядра из чисел контрольной
    модели (× 1/1,01, отношения + 0,001) — все строки в допуске; та же заглушка без полей ключей — строки «нет у ядра»;
    у книги без ключей групп ключей нет."""
    ctl = cm.c_control_run(*all_keys(*form))
    near = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    rows = tcm.compare_with_core(near, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, tcm._fail_lines(bad)
    groups = {r["group"] for r in rows}
    new = {"bb_n_t", "bb_s_price", "bb", "terminal_f_k", "terminal_d_f", "terminal_i_f", "cor_mix0", "v_opex"}
    assert new <= groups, new - groups
    doc = tcm.checks_document(near, ctl, as_of="2026-10-21", commit=None)
    assert doc["all_ok"]
    for r in doc["rows"]:
        tcm._assert_row_form(r)
    bare = tcm._stub_core(ctl, 1.0)
    for cell in {id(bare.cell(*k)): bare.cell(*k) for k in ((c["world"], c["regime"], c["scenario"]) for c in ctl["cells"])}.values():
        for name in ("n_t", "s_price", "terminal_fixed"):
            delattr(cell, name)
        for name in ("bb", "cor_mix0", "vol_opex"):
            cell.quarters.pop(name)
    gone = [r for r in tcm.compare_with_core(bare, ctl) if r["group"] == "missing"]
    assert gone and all(not r["ok"] for r in gone)
    plain = cm.c_control_run(*form)
    assert not new & {r["group"] for r in tcm.compare_with_core(tcm._stub_core(plain, 1.0), plain)}


# ============================================================================ М3 — выкуп акций по цене мира


def example_walk(m3: dict, *, rule: str = cm.BB_FORWARD, p_book: float | None = None, closed=None, amounts=None,
                 start: float | None = None, shock=()) -> tuple[list[dict], dict]:
    """Квартальный путь примера m3 рабочими функциями контрольной модели (c_bb_price, c_bb_shares, c_bb_forward):
    дивиденд квартала — DPS политики × акции клетки после покупок квартала; d_q — на внешнюю акцию."""
    inp = m3["inputs"]
    k = {int(q): ex(v) for q, v in inp["k_book"].items()}
    p_b = ex(inp["P_book"]) if p_book is None else p_book
    bb = {"rule": rule, "p_book": p_b, "qb": int(inp["qb"]), "k": {"W": k},
          "closed": {int(q): ex(v) for q, v in inp["closed_prices"].items()} if closed is None else closed,
          "dR": {int(q): ex(v) for q, v in inp["bridge_dps"].items()}}
    amt = {int(q): ex(v) for q, v in inp["amounts_bn"].items()} if amounts is None else amounts
    dps = {int(q): ex(v) for q, v in inp["dps_policy"].items()}
    n, p_plus, rows = ex(inp["N_out_0_mln"]), (p_b if start is None else start), []
    for q in sorted(amt):
        b = 0.0 if q in shock else amt[q]
        p_bar = cm.c_bb_price(bb, "W", q, p_plus)
        n = cm.c_bb_shares(n, b, p_bar, "пример", q)
        div = dps.get(q, 0.0) * n / 1000.0
        d_ext = div * 1000.0 / n
        p_plus = cm.c_bb_forward(bb, "W", q, p_plus, d_ext)
        rows.append({"q": q, "B": b, "P_bar": p_bar, "N_out": n, "Div": div, "d_ext": d_ext, "P_plus": p_plus})
    return rows, bb


def example_value(m3: dict, rows: list[dict]) -> float:
    """S примера рабочей функцией c_bb_share_value: дисконт от даты оценки примера (q0 = qb), DF_q = Π 1 / (1 + k)."""
    inp = m3["inputs"]
    k = {int(q): ex(v) for q, v in inp["k_valuation"].items()}
    d, items = 1.0, []
    for r in rows:
        if r["q"] < int(inp["q0"]):
            continue
        d = d / (1.0 + k[r["q"]])
        items.append((d, r["Div"], r["N_out"]))
    return cm.c_bb_share_value(items, d, ex(inp["TV_DDM_bn"]), rows[-1]["N_out"])


@pytest.mark.tact
def test_m3_example_by_own_walker():
    """Пример m3 рабочими функциями контрольной модели до 1e-9: цена покупок (закрытый квартал — closed_prices,
    квартал даты книги — середина оставшейся части, дальше — середина квартала от форварда), путь акций, дивиденд на
    акции клетки, форвард после d_q и d^R; S на оставшуюся акцию; правило market — N_T = N_0 − Σ 1000 B / P_b точно;
    без выкупа — S = V_DDM × 1000 / N_0; год шока снимает выкуп; дешевле покупка — выше S; неподвижная точка
    справочного правила cell_value."""
    m3 = example()["m3"]
    rows, _ = example_walk(m3)
    for mine, theirs in zip(rows, m3["rows"]):
        for key in ("B", "P_bar", "N_out", "Div", "d_ext", "P_plus"):
            assert close(mine[key], ex(theirs[key])), (mine["q"], key, mine[key], ex(theirs[key]))
    assert close(example_value(m3, rows), ex(m3["value"]["S"]))
    assert close(rows[-1]["N_out"], ex(m3["value"]["N_T"]))
    mkt, _ = example_walk(m3, rule=cm.BB_MARKET)
    n0 = ex(m3["inputs"]["N_out_0_mln"])
    total = sum(ex(v) for v in m3["inputs"]["amounts_bn"].values())
    assert mkt[-1]["N_out"] == pytest.approx(n0 - total * 1000.0 / ex(m3["inputs"]["P_book"]), rel=1e-12)
    assert close(example_value(m3, mkt), ex(m3["market_rule"]["value"]["S"]))
    zero, _ = example_walk(m3, amounts={q: 0.0 for q in range(1, 7)})
    assert close(example_value(m3, zero), ex(m3["zero_buyback"]["value"]["S"]))
    assert close(example_value(m3, zero) * n0 / 1000.0, ex(m3["zero_buyback"]["value"]["V_DDM"]))
    shock, _ = example_walk(m3, shock=(3, 4))
    for mine, theirs in zip(shock, m3["shock_skip_q3_q4"]["rows"]):
        assert close(mine["N_out"], ex(theirs["N_out"])) and close(mine["P_plus"], ex(theirs["P_plus"]))
    cheap, _ = example_walk(m3, p_book=9.0, closed={1: 10.5 * 0.9})
    assert example_value(m3, cheap) > example_value(m3, rows)
    assert close(example_value(m3, cheap), ex(m3["cheaper_price_raises_S"]["S_cheaper"]))
    p, turns = ex(m3["inputs"]["P_book"]), 0
    for turns in range(1, 31):
        s = example_value(m3, example_walk(m3, start=p)[0])
        if abs(s - p) <= 1e-12 * p:
            break
        p = s
    assert close(p, m3["cell_value_variant"]["P_start_fixed_point"]) and turns <= 30


AMOUNT = {"2026Q4": 3.0, "2027": 3.0, "2028": 3.0, "LT": 0.0, "LT_from": 2029}


def with_buyback(book: dict, rule: str = cm.BB_FORWARD, amount=None, **extra) -> dict:
    out = copy.deepcopy(book)
    out["dividends"]["buyback"] = {"enabled": True, "amount": copy.deepcopy(AMOUNT if amount is None else amount),
                                   "price": rule, **extra}
    return out


def flows(ctx: dict, cell: dict):
    """(DF(τ), Div, B, N_c,q) кварталов клетки после даты оценки — для тождеств оценки (вход теста)."""
    ck, df = ctx["clock"], ctx["disc"][cell["world"]]
    out = []
    for i in range(ck["p0"], len(ctx["periods"])):
        row = cell["rows"][i]
        divs = dict(row["div_list"])
        for j in range(len(row["bb_q"])):
            ta = ck["t_start"][i] + 0.25 * (j + 1)
            if ta > 0.0:
                out.append((df(ta), divs.get(j, 0.0), row["bb_q"][j], row["n_c_q"][j]))
    return out


@pytest.mark.tact
def test_m3_identities_in_the_cells(form):
    """Клетки формы панели с выкупом по форварду мира: V_DDM = V_RI (с выкупом); S × N_T / 1000 = V_DDM − PV(B) − Σ DF
    × DPS × (N_q − N_T) / 1000; BV = BV_прош + CI − Div − B по годам; CI без выкупа; акции не растут; закрытый к дате
    книги квартал — по closed_prices, квартал даты книги — от цены книги с половиной k мира; k — свой у мира."""
    book, facts = form
    ctx, cells = cells_of(with_buyback(book, amount=dict(AMOUNT, **{"2026Q3": 2.0}), closed_prices={"2026Q3": 300.0}),
                          facts)
    bb = ctx["bb"]
    assert bb["qb"] == 2 and bb["k"]["N"] != bb["k"]["M"]
    for key, c in cells.items():
        assert abs(c["v_ddm"] / c["v_ri"] - 1.0) <= 1e-9, key
        f = flows(ctx, c)
        n_t = c["n_t"]
        pv_b = sum(d * b for d, _, b, _ in f)
        sold = sum(d * div / n * (n - n_t) for d, div, _, n in f)        # DPS × (N_q − N_T) / 1000, DPS = Div × 1000 / N_q
        assert rel(c["s_price"] * n_t / 1000.0, c["v_ddm"] - pv_b - sold) <= 1e-9, key
        assert rel(pv_b, c["pv_bb"]) <= 1e-12 and c["v_price"] == c["s_price"] * ctx["A"]["N_out"] / 1000.0
        prev_bv, prev_n = ctx["A"]["BV"], ctx["A"]["N_out"]
        for r in c["rows"]:
            assert abs(r["bv"] - (prev_bv + r["ci"] - r["div"] - r["bb"])) <= 1e-9 * abs(r["bv"])
            assert abs(r["ci"] - (r["ni_sh"] - r["cpn_net"] + r["oci"] + r["om"])) <= 1e-9 * max(1.0, abs(r["ci"]))
            assert all(n <= prev_n for n in r["n_c_q"]) and r["n_c_q"] == sorted(r["n_c_q"], reverse=True)
            prev_bv, prev_n = r["bv"], r["n_c_q"][-1]
        # решения квартала — на акциях клетки после покупок квартала: пул × N_c,q / N_iss, запись реестра — DPS × N_c,q
        n_of = {x["q"]: x["n_out"] for r in c["rows"] for x in r["quarters"]}
        for d in c["decisions_q"]:
            n_q = n_of[d["q"]]
            assert close(d["want"], d["dps_policy"] * n_q / 1000.0, 1e-12), (key, d["period"])
            assert close(d["dps"], d["div"] * 1000.0 / n_q, 1e-12), (key, d["period"])
        assert any(d["source"] == "register" and d["q"] >= 1 for d in c["decisions_q"])
        assert any(n_of[d["q"]] < ctx["A"]["N_out"] for d in c["decisions_q"] if d["div"])
        first = c["rows"][0]
        assert first["p_bar_q"][0] == 300.0                                # закрытый квартал (k = 1 < q_b)
        assert first["p_bar_q"][1] == bb["p_book"] * (1.0 + bb["k"][key[0]][2] / 2.0)
        assert n_t < ctx["A"]["N_out"]


def test_m3_market_rule_and_zero_amount(form):
    """Правило market при постоянных B: N_T = N_0 − Σ 1000 B / P_b точно (1e-9) в каждой клетке; выкуп ≡ 0 при
    включённом ключе — те же клетки, что без ключа (капитал бит в бит, оценка в цене = V_RI до 1e-9)."""
    book, facts = form
    ctx, cells = cells_of(with_buyback(book, cm.BB_MARKET, amount=1.5), facts)
    want = ctx["A"]["N_out"] - ctx["Q"] * 1000.0 * 1.5 / ctx["bb"]["p_book"]
    assert all(rel(c["n_t"], want) <= 1e-9 for c in cells.values())
    _, plain = cells_of(book, facts)
    _, zero = cells_of(with_buyback(book, amount=0.0), facts)
    for key in CELLS:
        assert [r["bv"] for r in zero[key]["rows"]] == [r["bv"] for r in plain[key]["rows"]]
        assert zero[key]["v_ri"] == plain[key]["v_ri"] and zero[key]["n_t"] == ctx["A"]["N_out"]
        assert rel(zero[key]["v_price"], plain[key]["v_ri"]) <= 1e-9, key


def test_m3_cheaper_purchase_raises_the_value_per_share(form):
    """Дешевле цена покупки (цена книги × 0,9; закрытые кварталы — по ней же) при тех же прочих — выше S в каждой клетке."""
    book, facts = form
    _, base = cells_of(with_buyback(book), facts)
    cheap_book = with_buyback(book)
    main = cheap_book["meta"]["company"]["main_ticker"]
    cheap_book["meta"]["market_price"][main] = cheap_book["meta"]["market_price"][main] * 0.9
    _, cheap = cells_of(cheap_book, facts)
    assert all(cheap[k]["s_price"] > base[k]["s_price"] for k in CELLS)


def test_m3_path_ignores_live_inputs_and_shock_year_skips(form):
    """Форвард идёт от даты и цены книги: другая дата оценки не меняет путь акций и цен покупок (меняется только
    оценка); skip_in_shock_year снимает выкуп года шока в клетках кризиса и только в них."""
    book, facts = form
    b2 = with_buyback(book, amount={"2027": 3.0, "2028": 3.0, "LT": 0.0, "LT_from": 2029}, skip_in_shock_year=True)
    ctx, cells = cells_of(b2, facts)
    later = cm.c_control_context(b2, facts, valuation_date="2026-12-15")
    for key, c in cells.items():
        moved = cm.c_cell_annual(later, *key)
        assert [r["p_bar_q"] for r in moved["rows"]] == [r["p_bar_q"] for r in c["rows"]]
        assert [r["n_c_q"] for r in moved["rows"]] == [r["n_c_q"] for r in c["rows"]]
        assert moved["s_price"] != c["s_price"]
        for p, r in zip(ctx["periods"], c["rows"]):
            if p["year"] == ctx["shock_year"]:
                assert (sum(r["bb_q"]) == 0.0) == (key[1] == cm.R_CRISIS), (key, p["year"])
    assert any(k[1] == cm.R_CRISIS for k in CELLS) and any(k[1] != cm.R_CRISIS for k in CELLS)


@pytest.mark.tact
def test_m3_register_dividends_after_the_book_date_enter_the_forward(form):
    """d^R: DPS записи реестра закрытого квартала прибыли (вычтен из BV в якоре) с экс-датой позже даты книги вычитается
    из форварда в квартале экс-даты; запись с экс-датой до даты книги — нет."""
    book, facts = form
    f2 = copy.deepcopy(facts)
    seed = f2["dividends"]["register_seed"]
    closed = {"year": 2025, "period": "2025Q4", "label": "за 2025 год", "dps": {"v": 2.5}, "status": "declared",
              "decided_date": "2026-05-14", "record_date": "2026-11-10", "ex_date": "2026-11-10",
              "pay_date": "2026-11-24", "sources": ["фикстура теста"]}
    ctx = cm.c_control_context(with_buyback(book), dict(f2, dividends=dict(f2["dividends"], register_seed=seed + [closed])))
    assert ctx["bb"]["dR"] == {cm.c_qidx(ctx["anchor"], 2026, 4): 2.5}
    assert cm.c_control_context(with_buyback(book), facts)["bb"]["dR"] == {}


def test_m3_cell_value_rule_converges(form):
    """Справочное правило cell_value: P_s — неподвижная точка стоимости клетки на оставшуюся акцию на дату книги (до
    1e-9, не больше 30 оборотов); проверка — пересчёт S на часах даты книги по сошедшемуся пути."""
    book, facts = form
    ctx = cm.c_control_context(with_buyback(book, cm.BB_CELL), facts)
    c = cm.c_cell_annual(ctx, *CELLS[0])
    assert 1 <= c["bb_turns"] <= 30
    at_book = {**ctx, "clock": ctx["bb"]["clock_b"], "disc": ctx["bb"]["disc_b"]}
    s_book = cm._c_value_cell(at_book, c, c["rows"], c["decisions"])["s_price"]
    assert rel(s_book, c["bb_start"]) <= 1e-8
    assert c["rows"][0]["p_bar_q"][1] == c["bb_start"] * (1.0 + ctx["bb"]["k"][CELLS[0][0]][2] / 2.0)


@pytest.mark.tact
def test_m3_refusals(form):
    """Отказы: годовой календарь; нет amount или price; неизвестное правило; amount < 0; закрытая цена вне [first_period;
    q_b) или не больше нуля; skip_in_shock_year не логический; выключатель null; акций не осталось — с меткой клетки."""
    book, facts = form
    annual = with_buyback(book)
    annual["dividends"]["calendar"]["frequency"] = "annual"
    annual["capital"]["growth_constraint"]["enabled"] = False
    with pytest.raises(cm.ControlInputError, match="квартальн"):
        cm.c_control_context(annual, facts)
    bad = [with_buyback(book, amount=-1.0), with_buyback(book, "no_such_rule"),
           with_buyback(book, closed_prices={"2026Q4": 300.0}), with_buyback(book, closed_prices={"2026Q2": 300.0}),
           with_buyback(book, closed_prices={"2026Q3": 0.0}), with_buyback(book, skip_in_shock_year=None)]
    for key in ("amount", "price"):
        b2 = with_buyback(book)
        b2["dividends"]["buyback"].pop(key)
        bad.append(b2)
    null = with_buyback(book)
    null["dividends"]["buyback"]["enabled"] = None
    bad.append(null)
    for b2 in bad:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b2, facts)
    with pytest.raises(cm.ControlInputError, match="/".join(CELLS[0])):
        cells_of(with_buyback(book, amount=1e6), facts, keys=CELLS[:1])
    off = with_buyback(book, amount=-1.0)
    off["dividends"]["buyback"]["enabled"] = False
    assert cm.c_control_context(off, facts)["bb"] is None
