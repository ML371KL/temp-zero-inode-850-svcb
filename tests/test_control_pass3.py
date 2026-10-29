# -*- coding: utf-8 -*-
"""Контрольная модель: ключи третьего прохода ядра Совкомбанка (core-pass3) своим счётом и правило ПОРОГ (Р4-16).

Ключи (методика — spec.yaml прохода, пример — tests/fixtures/core_pass3/example.json; копия примера методики):

* К-Т2 — терминал, сверенный с явными годами: год терминала по средней длине года (`valuation.terminal.year_basis`),
  ставка фондирования блока К-Т после выплаты избытка (`valuation.terminal.fixed_funding`), угасание по календарю
  (`valuation.terminal.fade_anchor_year`).
* К8 — неработающие деньги за своим драйвером (`volumes.cash_assets`, `capital.rwa.density.cash_assets`).
* К2б — смесь баз строки (`fees.volume_base`, `other.insurance_volume_base`: {mix: {имя: {share, base}}}).
* Правило ПОРОГ — строки за дискретным решением у порога не судятся (tests/test_control_model.py, reconcile).

Книга — фикстура формы панели (tests/fixtures/core_t) с ключами, подставленными тестом; пример — на остатках якоря книги
и фактов репозитория (их же читал пример методики). Без ключей контрольная модель считает бит в бит прежние числа —
это держит сводка (tests/independent_model.py на книге репозитория) и тесты «ключ нейтрален» ниже.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
    from tests import test_control_t as tct
    from tests import test_control_pass1 as tp1
    from tests import test_control_pass2 as tp2
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_t as tct                        # type: ignore[no-redef]
    import test_control_pass1 as tp1                    # type: ignore[no-redef]
    import test_control_pass2 as tp2                    # type: ignore[no-redef]

EXAMPLE = cm.ROOT / "tests" / "fixtures" / "core_pass3" / "example.json"
CELLS = tp2.CELLS
RETAIL = {"auto": 1.0, "mortgage": 1.0, "cash_loans": 1.0, "cards": 1.0}               # розничные книги (вход теста)
DEPOSITS = {"retail_current": 1.0, "retail_term": 1.0, "corp_term": 1.0, "corp_current": 1.0}
# Входы примера методики (example.py: К-Т2а — N/norm/mid года 2036 печати ядра p3 @ 98cd603; К-Т2б — N/norm/mid и
# H/norm/mid; К8 — прочие активы и плотности якоря; рост книг квартала — для тождества индексов К2б)
KT2A_IN = {"nii": 506.9768945069029, "llp": 127.16598770322082, "fvc": 0.0, "pbt_l": 288.0575404415721,
           "d_nii": -2.404796231285495}
KT2B_IN = {"m": 0.207, "f_a": 97.035, "y_bal": 0.07550438362233036, "c_wh": 0.08, "tau": 0.233, "nci": 0.048,
           "k_t": 0.14068574657230903, "hla": 38.5, "x_t": 171.7}
K8_IN = {"oa0": 549.592, "fa": 97.035, "w_oa": 1.0493, "w_c": 0.0672, "loans_x": 1.02, "deposits_x": 1.03}
GROW = {"auto": 1.03, "mortgage": 1.01, "cash_loans": 1.05, "cards": 1.04, "corp_loans": 1.02}


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


rel, close, cells_of, numbers, put = tp2.rel, tp2.close, tp2.cells_of, tp2.numbers, tp2.put


@pytest.fixture(scope="module")
def form():
    return tct.t_book(), tct.t_facts()


@pytest.fixture(scope="module")
def plain(form):
    return cells_of(*form)


@pytest.fixture(scope="module")
def hist(form):
    book, facts = form
    return tp1.history_books(book, facts)


@pytest.fixture(scope="module")
def anchor_books():
    """Книга и остатки якоря репозитория (их читал пример методики): книга с выведенными ключами, состояние якоря."""
    book, facts = tcm._inputs()
    A = cm.c_anchor_state(book, facts)
    B, _ = cm.c_resolve_anchor_keys(book, A)
    return book, facts, A, B


# ============================================================================ К-Т2 — терминал, сверенный с явными годами


@pytest.mark.tact
def test_kt2_example_by_own_code():
    """Пример К-Т2 своим кодом. а) ν_L = 365,2425 / 366, ψ = 365,2425 / 365, дневные строки, поправка
    (ν − 1)(DW + ΔNII*), база терминала и Y_X × ψ (1e-12); у невисокосного L ν = ψ (1e-15). б) N/norm/mid: минимум на
    постоянных активах M_F = (c_wh − y_bal) m / (1 − m) F_A и его доля в прежней стоимости фондирования; H/norm/mid —
    связан только после выплаты: H* = HLA / (1 − m), WT* = X_T − H* (1e-12). в) срок мира n_W из схождения с начала
    (1e-9 доли) и φ при s = 0, 1, 2 (1e-9); fade = 1 — φ = 1 при любом s."""
    e = example()
    a = e["K_T2a"]
    dw = KT2A_IN["nii"] - KT2A_IN["llp"] - KT2A_IN["fvc"]
    year = cm.c_terminal_year(a["days_L"], dw, KT2A_IN["d_nii"])
    assert rel(year["nu_l"], a["nu_L"]) <= 1e-15 and rel(year["psi"], a["psi"]) <= 1e-15
    assert rel(year["day_weighted_l"], a["day_weighted_L"]) <= 1e-12
    old = KT2A_IN["pbt_l"] + KT2A_IN["d_nii"]
    assert rel(old, a["pbt_terminal_base_old"]) <= 1e-12
    assert rel(year["adj"], a["adj"]) <= 1e-12 and rel(old + year["adj"], a["pbt_terminal_base_new"]) <= 1e-12
    assert rel(year["psi"] * a["y_x_old"], a["y_x_new"]) <= 1e-12
    leap_free = cm.c_terminal_year(365, dw, KT2A_IN["d_nii"])
    assert leap_free["nu_l"] == leap_free["psi"] == pytest.approx(a["non_leap_L_365"]["nu"], rel=1e-15)
    b = e["K_T2b"]
    v = KT2B_IN
    n = cm.c_funding_after_payout(x_t=v["x_t"], wt=1.0, h_star=0.0, y_bal=v["y_bal"], c_wh=v["c_wh"], m_liq=v["m"],
                                  f_a=v["f_a"])                       # N/norm/mid: минимум связан на конце Q (WT_Q > 0)
    assert n["bound_after_payout"] and n["y_m"] == v["c_wh"]
    assert rel(n["min_liquidity"], b["N_norm_mid"]["extra_pre_tax"]) <= 1e-12
    keep = (1.0 - v["tau"]) * (1.0 - v["nci"])
    assert rel(-n["min_liquidity"] * keep, b["N_norm_mid"]["d_I_F_after_tax"]) <= 1e-12
    assert rel(-n["min_liquidity"] * keep / v["k_t"], b["N_norm_mid"]["d_TV_fixed_part_w1"]) <= 1e-12
    h_star = v["hla"] / (1.0 - v["m"])
    h = cm.c_funding_after_payout(x_t=v["x_t"], wt=0.0, h_star=h_star, y_bal=v["y_bal"], c_wh=v["c_wh"],
                                  m_liq=v["m"], f_a=v["f_a"])
    assert rel(h_star, b["H_norm_mid"]["h_star"]) <= 1e-12
    assert rel(h["wt_after"], b["H_norm_mid"]["wt_after_payout"]) <= 1e-12
    assert h["bound_after_payout"] is b["H_norm_mid"]["bound_after_payout"] is True
    c = e["K_T2c"]
    for w in ("N", "H", "M"):
        node = c[w]
        n_w = cm.c_fade_years(0.5, node["k_T"], node["g_T"])
        assert rel(n_w, node["n_W"]) <= 1e-9, w
        for s in (0, 1, 2):
            assert rel(cm.c_fade_sum(n_w, node["k_T"], node["g_T"], s), node[f"phi_s{s}"]) <= 1e-9, (w, s)
        assert cm.c_fade_calendar(0.5, node["k_T"], node["g_T"], 0) == (0.5, None)
        assert cm.c_fade_calendar(1.0, node["k_T"], node["g_T"], 1) == (c["fade_1"]["phi_s1"], None)


@pytest.mark.tact
def test_kt2_fade_sum_is_the_reference_series():
    """φ(n, k, g, s) замкнутой суммой — ряд справочной формулы М§7 с началом s, просуммированный по членам до
    последнего положительного (1e-13); φ(s = 0) растёт по n к 1; φ(s) убывает по s; срок мира — корень (1e-12)."""
    k, g = 0.16, 0.06                                                    # входы теста
    x = (1.0 + g) / (1.0 + k)
    for n in (0.4, 1.0, 7.3, 15.0, 33.9):
        for s in (0, 1, 3, 8):
            terms = [max(0.0, 1.0 - (t - 1 + s) / n) * x ** (t - 1) for t in range(1, 200)]
            assert cm.c_fade_sum(n, k, g, s) == pytest.approx((k - g) / (1.0 + k) * sum(terms), rel=1e-13, abs=1e-15)
    assert cm.c_fade_sum(5.0, k, g, 0) < cm.c_fade_sum(10.0, k, g, 0) < cm.c_fade_sum(1e6, k, g, 0) < 1.0
    assert cm.c_fade_sum(1e6, k, g, 0) == pytest.approx(1.0, abs=1e-4)
    n = cm.c_fade_years(0.3, k, g)
    assert cm.c_fade_sum(n, k, g) == pytest.approx(0.3, abs=1e-12)
    assert [cm.c_fade_sum(n, k, g, s) for s in range(4)] == sorted((cm.c_fade_sum(n, k, g, s) for s in range(4)),
                                                                 reverse=True)
    assert cm.c_fade_years(1.0, k, g) == math.inf


def with_terminal(book: dict, **keys) -> dict:
    out = copy.deepcopy(book)
    out["valuation"]["terminal"].update(keys)
    return out


def test_kt2_neutral_values_are_bit_for_bit(form, plain):
    """calendar, binary и год-якорь = году L — прежние числа бит в бит (на форме панели с блоком К-Т и без него); без
    блока К-Т ставка фондирования не читается (даже неверная)."""
    book, facts = form
    _, cells0 = plain
    yl = cm.c_per_parse(book["meta"]["last_period"])[0]
    _, same = cells_of(with_terminal(book, year_basis="calendar", fade_anchor_year=yl, fixed_funding="nonsense"), facts)
    for key in CELLS:
        assert numbers(same[key]) == numbers(cells0[key]), key
        assert "terminal_year" not in same[key] and "terminal_fade" not in same[key]
    fixed_book, fixed_facts = tp1.fixed_form(book, facts)
    _, block = cells_of(tp1.with_lam(fixed_book, 0.0), fixed_facts)
    _, binary = cells_of(with_terminal(tp1.with_lam(fixed_book, 0.0), fixed_funding="binary"), fixed_facts)
    for key in CELLS:
        assert numbers(binary[key]) == numbers(block[key]), key
        assert "bound_after_payout" not in binary[key]["terminal_fixed"]


def test_kt2_mean_year_moves_only_the_terminal(form, plain):
    """Год терминала «средний год»: явные годы бит в бит; поправка PBT года L — (ν − 1)(ЧПД − резервы − FVC + ΔNII*),
    ν — по дням года L сетки фикстуры (2036 — високосный, ν < ψ); Y_X — ровно ψ × Y_X календарного года; NI_T+1 —
    тождество; TV_DDM − TV_RI = BV_Q и V_DDM = V_RI (1e-12). Невисокосный год L — ν = ψ. С К4 и блоком К-Т (λ_F = 0) —
    ΔNII* в поправке, стоимость стоящей доли ψ y_m D_F."""
    book, facts = form
    ctx0, cells0 = plain
    ctx, cells = cells_of(with_terminal(book, year_basis="mean"), facts)
    nci = cm.c_bnum(ctx["B"], "pnl.nci_share")
    days_l = ctx["periods"][-1]["days"]
    for key in CELLS:
        c, c0, last = cells[key], cells0[key], cells[key]["rows"][-1]
        assert numbers(c)[1] == numbers(c0)[1], key                     # явные годы — бит в бит
        year = c["terminal_year"]
        assert year["days_l"] == days_l and year["nu_l"] == cm.MEAN_YEAR / days_l < year["psi"]
        assert close(year["adj"], (year["nu_l"] - 1.0) * (last["nii"] - last["llp"] - last["fvc"]), 1e-12)
        assert close(c["y_x"], year["psi"] * c0["y_x"], 1e-12)
        assert close(c["ni_t1"], ((last["pbt"] + year["adj"]) * (1.0 + c["g_t"]) - c["y_x"]) * (1.0 - last["tau_eff"])
                     * (1.0 - nci), 1e-12)
        assert close(c["tv_ddm"] - c["tv_ri"], last["bv"], 1e-12) and abs(c["v_ddm"] / c["v_ri"] - 1.0) <= 1e-12
    leap_free = dict(ctx)
    leap_free["periods"] = [*ctx["periods"][:-1], {**ctx["periods"][-1], "days": 365}]
    key = CELLS[0]
    again = cm._c_value_cell(leap_free, dict(zip(("world", "regime", "scenario"), key)),
                             [dict(r) for r in cells[key]["rows"]], cells[key]["decisions"])
    assert again["terminal_year"]["nu_l"] == pytest.approx(again["terminal_year"]["psi"], rel=1e-15)
    fixed_book, fixed_facts = tp1.fixed_form(book, facts)
    calendar = tp2.with_stationary(tp1.with_lam(fixed_book, 0.0))
    _, cal = cells_of(calendar, fixed_facts)
    _, both = cells_of(with_terminal(calendar, year_basis="mean"), fixed_facts)
    keep_of = (1.0 - cm.c_bnum(calendar, "pnl.nci_share"))
    for key, c in both.items():
        last, blk, stat = c["rows"][-1], c["terminal_fixed"], c["terminal_stationary"]
        assert close(c["terminal_year"]["adj"], (c["terminal_year"]["nu_l"] - 1.0)
                     * (last["nii"] - last["llp"] - last["fvc"] + stat["d_nii_l"]), 1e-12)
        assert close(blk["carry"], c["terminal_year"]["psi"] * blk["y_m"] * blk["d_f"], 1e-12)
        keep = (1.0 - last["tau_eff"]) * keep_of
        old = cal[key]["terminal_fixed"]
        # I_F + стоимость стоящей доли после налога — купон инструментов, одинаковый в обоих годах терминала
        assert close(blk["i_f"] + blk["carry"] * keep, old["i_f"] + old["y_m"] * old["d_f"] * keep, 1e-12), key
        assert close(c["tv_ddm"] - c["tv_ri"], last["bv"], 1e-12), key


def test_kt2_balancing_funding_of_the_block(form):
    """Ставка фондирования блока К-Т по правилу балансирующих статей после выплаты избытка: признак «связан» — WT* > 0
    по X_T, H* и добору опта клетки; y_m — ставка опта при связанном, иначе смесь; M_F = (c_wh − y_bal) m / (1 − m) F_A
    (≥ 0 при c_wh ≥ y_bal) и 0 без связанности; I_F = −(y_m D_F + M_F)(1 − τ)(1 − nci) − купон (1e-12); не связан и
    добора нет — прежний блок (1e-14); TV_DDM − TV_RI = BV_Q. Связанный и свободный минимум — оба исхода: доля минимума
    ликвидности книги и поднятая (вход теста). Синтетика связанности: X_T > H* при WT_Q = 0 — связан; X_T < 0 — связан,
    только если добор больше −X_T."""
    book, facts = form
    fixed_book, fixed_facts = tp1.fixed_form(book, facts)
    seen = set()
    for m_min in (None, 0.3):                                            # доля минимума ликвидности — вход теста
        base = tp1.with_lam(fixed_book, 0.0)
        if m_min is not None:
            base["volumes"]["liquid_min_share"] = m_min
        ctx, bal = cells_of(with_terminal(base, fixed_funding="balancing"), fixed_facts)
        _, binary = cells_of(base, fixed_facts)
        m = cm.c_bnum(ctx["B"], "volumes.liquid_min_share")
        nci = cm.c_bnum(ctx["B"], "pnl.nci_share")
        for key, c in bal.items():
            blk, last = c["terminal_fixed"], c["rows"][-1]
            assert blk["f_a"] == ctx["oaf"] > 0.0
            want = cm.c_funding_after_payout(x_t=c["x_t"], wt=c["wt"], h_star=c["h_star"], y_bal=c["y_bal"],
                                             c_wh=last["c_wh_end"], m_liq=m, f_a=blk["f_a"])
            assert blk["bound_after_payout"] == want["bound_after_payout"] == (blk["wt_after"] > 0.0), key
            assert blk["y_m"] == (last["c_wh_end"] if blk["bound_after_payout"] else c["y_bal"]), key
            if blk["bound_after_payout"]:
                assert close(blk["min_liquidity"], (last["c_wh_end"] - c["y_bal"]) * m / (1.0 - m) * ctx["oaf"], 1e-12)
                assert (blk["min_liquidity"] >= 0.0) == (last["c_wh_end"] >= c["y_bal"])
            else:
                assert blk["min_liquidity"] == 0.0
            keep = (1.0 - last["tau_eff"]) * (1.0 - nci)
            cpn = blk["i_f"] + (blk["y_m"] * blk["d_f"] + blk["min_liquidity"]) * keep
            old = binary[key]["terminal_fixed"]
            assert close(cpn, old["i_f"] + old["y_m"] * old["d_f"] * keep, 1e-12), key    # купон после налога — тот же
            assert close(c["tv_ddm"] - c["tv_ri"], last["bv"], 1e-12)
            if not blk["bound_after_payout"] and c["wt"] == 0.0:
                assert c["v_ri"] == pytest.approx(binary[key]["v_ri"], rel=1e-14), key
            seen.add(blk["bound_after_payout"])
    assert seen == {True, False}, seen
    one = cm.c_funding_after_payout(x_t=50.0, wt=0.0, h_star=20.0, y_bal=0.05, c_wh=0.08, m_liq=0.2, f_a=10.0)
    assert one["bound_after_payout"] and one["wt_after"] == 30.0 and one["wt_z"] == 30.0
    assert one["min_liquidity"] == pytest.approx(0.03 * 0.2 / 0.8 * 10.0, rel=1e-15)
    free = cm.c_funding_after_payout(x_t=10.0, wt=0.0, h_star=20.0, y_bal=0.05, c_wh=0.08, m_liq=0.2, f_a=10.0)
    assert not free["bound_after_payout"] and free["min_liquidity"] == 0.0 and free["wt_z"] == -10.0
    for wt, bound in ((15.0, True), (5.0, False)):
        lack = cm.c_funding_after_payout(x_t=-10.0, wt=wt, h_star=0.0, y_bal=0.05, c_wh=0.08, m_liq=0.2, f_a=10.0)
        assert lack["bound_after_payout"] is bound and lack["wt_z"] == wt - 10.0


def test_kt2_fade_anchor_moves_only_the_multiplier(form):
    """Угасание по календарю: год-якорь раньше года L на s лет — множитель φ_W мира с началом s (срок мира — из
    множителя книги, схождение с начала); φ_W < fade и убывает по s; ROE'_T = k + φ_W max(ROE − k, 0) + min(ROE − k, 0);
    явные годы бит в бит; fade = 1 (книга фикстуры) — φ = 1 при любом s, числа бит в бит."""
    book, facts = form
    yl = cm.c_per_parse(book["meta"]["last_period"])[0]
    _, ones = cells_of(with_terminal(book, fade_anchor_year=yl - 2), facts)
    _, cells0 = cells_of(book, facts)
    for key in CELLS:
        assert ones[key]["terminal_fade"] == {"s": 2, "n": None, "phi": 1.0}
        assert ones[key]["v_ri"] == cells0[key]["v_ri"]
    half = with_terminal(book, fade=0.5)
    _, h0 = cells_of(half, facts)
    _, h1 = cells_of(with_terminal(half, fade_anchor_year=yl - 1), facts)
    _, h2 = cells_of(with_terminal(half, fade_anchor_year=yl - 2), facts)
    above = 0
    for key in CELLS:
        a, b, c = h0[key], h1[key], h2[key]
        assert numbers(b)[1] == numbers(a)[1], key
        phi1, phi2 = b["terminal_fade"]["phi"], c["terminal_fade"]["phi"]
        assert phi2 < phi1 < 0.5
        n_w = cm.c_fade_years(0.5, b["k_t"], b["g_t"])
        assert b["terminal_fade"]["n"] == n_w and phi1 == cm.c_fade_sum(n_w, b["k_t"], b["g_t"], 1)
        gap = b["roe_t_raw"] - b["k_t"]
        assert b["roe_t"] == pytest.approx(b["k_t"] + phi1 * max(gap, 0.0) + min(gap, 0.0), abs=1e-15)
        above += gap > 0.0
        assert abs(b["v_ddm"] / b["v_ri"] - 1.0) <= 1e-12
    assert above, "нет клетки с ROE_T выше k_T — угасание не проверено"


def extended(book: dict, years: int) -> dict:
    """Книга с явным участком длиннее на years лет (как проверка класса 3, ops/tools/class_checks.py): конец сетки —
    тот же квартал на years лет позже, новые полугодия траекторий миров — значением последнего полугодия."""
    out = copy.deepcopy(book)
    last = str(out["meta"]["last_period"])
    year, tail = int(last[:4]), last[4:]
    out["meta"]["last_period"] = f"{year + years}{tail}"
    for w in out["worlds"]["ids"]:
        for traj in out["worlds"][w].values():
            if isinstance(traj, dict) and f"{year}H2" in traj:
                for y in range(year + 1, year + years + 1):
                    traj[f"{y}H1"] = traj[f"{y}H2"] = traj[f"{year}H2"]
    return out


CLASS3_TOL, CLASS3_TWO = 0.05, 0.02          # класс 3: сдвиг продления на год и «два года против одного», ₽ (spec)


def test_kt2_class3_on_the_book_by_own_grid():
    """Класс 3 своей сеткой на книге репозитория (терминал К-Т2 а + б + в, год-якорь — год L книги): продление явных
    лет на год сдвигает низ, точку и верх не больше 0,05 ₽, второй год против первого — не больше 0,02 ₽; без К-Т2 тот же
    счёт находит экземпляр (високосный год L и окно угасания) — сдвиг низа больше 0,05 ₽."""
    book, facts = tcm._inputs()
    yl = cm.c_per_parse(book["meta"]["last_period"])[0]

    def ends(b):
        res = cm.c_control_run(b, facts)
        return res["low"], res["point"], res["high"]

    keyed = with_terminal(book, year_basis="mean", fixed_funding="balancing", fade_anchor_year=yl)
    base, one, two = ends(keyed), ends(extended(keyed, 1)), ends(extended(keyed, 2))
    shift = [b - a for a, b in zip(base, one)]
    again = [c - b for b, c in zip(one, two)]
    assert max(abs(x) for x in shift) <= CLASS3_TOL, shift
    assert max(abs(x) for x in again) <= CLASS3_TWO, again
    leap = sum(cm.c_q_len(yl, q) for q in range(1, cm.QY + 1)) > cm.DAYS_BASE
    if leap and not {"year_basis", "fade_anchor_year"} & set(book["valuation"]["terminal"]):
        plain = [b - a for a, b in zip(ends(book), ends(extended(book, 1)))]     # книга без К-Т2 — экземпляр виден
        assert abs(plain[0]) > CLASS3_TOL, plain


@pytest.mark.tact
def test_kt2_refusals(form):
    """Год терминала — calendar | mean; ставка фондирования — binary | balancing (при блоке К-Т); год-якорь — целое не
    позже года L. Иначе — отказ."""
    book, facts = form
    yl = cm.c_per_parse(book["meta"]["last_period"])[0]
    fixed_book, fixed_facts = tp1.fixed_form(book, facts)
    for bad in ({"year_basis": "average"}, {"year_basis": None}, {"year_basis": 1}, {"fade_anchor_year": yl + 1},
                {"fade_anchor_year": str(yl)}, {"fade_anchor_year": True}, {"fade_anchor_year": float(yl)}):
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_terminal(book, **bad), facts)
    for bad in ("both", None, 0):
        with pytest.raises(cm.ControlInputError, match="fixed_funding"):
            cm.c_control_context(with_terminal(tp1.with_lam(fixed_book, 0.0), fixed_funding=bad), fixed_facts)
    assert cm.c_control_context(with_terminal(book, fixed_funding=None), facts)["funding"] == cm.FUND_BINARY


# ============================================================================ К8 — неработающие деньги за своим драйвером


def with_cash(book: dict, amount, driver, density=0.05) -> dict:
    out = copy.deepcopy(book)
    out["volumes"]["cash_assets"] = {"amount": amount, "driver": copy.deepcopy(driver)}
    if density is not None:
        out["capital"]["rwa"]["density"]["cash_assets"] = density
    return out


@pytest.mark.tact
def test_k8_example_by_own_code(anchor_books):
    """Пример К8 на остатках якоря книги репозитория: c = C_0 / D_0 по депозитам, ρ' = ρ − C_0 / L_0, вырез плотности
    ω' = [ω (OA_0 − F_A) − ω_c C_0] / (OA_0 − F_A − C_0), RWA растущей части якоря тот же; квартал (кредиты × 1,02,
    депозиты × 1,03): деньги, прочие активы и RWA растущей части с деньгами (1e-12); драйвер «кредиты» — прежние прочие
    активы (1e-12)."""
    book, facts, A, B = anchor_books
    k8 = example()["K8"]
    keyed = with_cash(B, "anchor", DEPOSITS, K8_IN["w_c"])
    # плотность прочих активов — вход примера (ω = 1,0493 книги примера; у итоговой книги круга 12 — 1,0062): пример
    # методики считается своим кодом на своих входах, остатки якоря — книги репозитория (они у примера те же)
    keyed["capital"]["rwa"]["density"]["other_assets"] = K8_IN["w_oa"]
    rule = cm.c_cash_rule(keyed, A, keyed["nii"]["books"])
    assert rule["c0"] == k8["c0"] and rel(rule["d0"], k8["d0_deposits"]) <= 1e-12
    assert rel(rule["c"], k8["c_share_of_deposits"]) <= 1e-12
    rho = cm.c_bnum(B, "volumes.other_assets_to_loans")
    assert rel(rho, k8["rho_book"]) <= 1e-12 and rel(rho - rule["cut"], k8["rho_without_cash"]) <= 1e-12
    assert rel(rule["w_rest"], k8["w_oa_carved"]) <= 1e-12
    grow0, c0 = K8_IN["oa0"] - K8_IN["fa"], rule["c0"]
    assert rel(rule["w_rest"] * (grow0 - c0) + rule["w_cash"] * c0, K8_IN["w_oa"] * grow0) <= 1e-14
    loans0 = sum(A["E0"][b] for b in cm.c_bget(B, "nii.books") if B["nii"]["books"][b].get("sector"))
    l_q, d_q = loans0 * K8_IN["loans_x"], rule["d0"] * K8_IN["deposits_x"]
    cash = rule["c"] * d_q
    oa = (rho - rule["cut"]) * l_q + cash + K8_IN["fa"]
    q = k8["quarter"]
    assert rel(cash, q["cash"]) <= 1e-12 and rel(oa, q["oa_new"]) <= 1e-12
    assert rel(rule["w_rest"] * (oa - K8_IN["fa"] - cash) + rule["w_cash"] * cash, q["rwa_growing_new"]) <= 1e-12
    by_loans = cm.c_cash_rule(with_cash(B, "anchor", "loans", K8_IN["w_c"]), A, B["nii"]["books"])
    oa_loans = (rho - by_loans["cut"]) * l_q + by_loans["c"] * l_q + K8_IN["fa"]
    assert rel(oa_loans, q["oa_old"]) <= 1e-12


def test_k8_loans_driver_and_zero_amount_are_no_key(form, plain):
    """Драйвер «кредиты» и деньги якоря 0 — прежние клетки (прочие активы, RWA, капитал, стоимость; 1e-12); RWA якоря с
    ключом тот же (1e-12); плотность денег, равная плотности прочих активов, — плотность растущей части та же (1e-15);
    null у ключа — ключа нет (бит в бит)."""
    book, facts = form
    ctx0, cells0 = plain
    grow0 = ctx0["A"]["OA"] - ctx0["A"]["OA_fixed"]
    for amount, driver in ((0.3 * grow0, "loans"), (0.0, "funds")):                # входы теста
        ctx, cells = cells_of(with_cash(book, amount, driver), facts)
        assert ctx["rwa0"] == pytest.approx(ctx0["rwa0"], rel=1e-12)
        for key in CELLS:
            for name in ("v_ri", "tv_ri", "x_t"):
                assert rel(cells[key][name], cells0[key][name]) <= 1e-12, (key, name)
            for r, r0 in zip(cells[key]["rows"], cells0[key]["rows"]):
                for line in ("oa", "rwa", "bv", "liquidity", "nii", "n20"):
                    assert close(r[line], r0[line], 1e-12), (key, line)
    same = cm.c_control_context(with_cash(book, 0.3 * grow0, "funds", float(book["capital"]["rwa"]["density"]
                                                                            ["other_assets"])), facts)
    assert same["cash"]["w_rest"] == pytest.approx(float(book["capital"]["rwa"]["density"]["other_assets"]), rel=1e-15)
    nulled = copy.deepcopy(book)
    nulled["volumes"]["cash_assets"] = None
    _, cells = cells_of(nulled, facts)
    for key in CELLS:
        assert numbers(cells[key]) == numbers(cells0[key]), key


def test_k8_cash_follows_its_driver(form):
    """Драйвер «средства клиентов» (с ведомой книгой К6): деньги на концах лет — c × уровень драйвера (1e-12), прочие
    активы — (ρ − C_0 / L_0) × кредиты + деньги + постоянные (1e-12), RWA — с вырезом и плотностью денег; квартальный
    проход кончает год на тех же деньгах (1e-9); баланс сходится; деньги кварталов — c × драйвер квартала."""
    book, facts = form
    ctx0 = cm.c_control_context(book, facts)
    grow0 = ctx0["A"]["OA"] - ctx0["A"]["OA_fixed"]
    keyed = tp2.with_driven(with_cash(book, 0.3 * grow0, "funds"), link=0.6)
    ctx, cells = cells_of(keyed, facts)
    rule = ctx["cash"]
    funds_books = [cm.RETAIL_CURRENT, cm.RETAIL_TERM, *ctx["biz"]]
    assert set(rule["w"]) == set(funds_books) and tp2.DRIVEN in rule["w"]
    r_oa = cm.c_bnum(ctx["B"], "volumes.other_assets_to_loans")
    dens = ctx["dens"]
    w_oa, w_c, grow0 = float(dens["other_assets"]), float(dens["cash_assets"]), ctx["A"]["OA"] - ctx["oaf"]
    w_rest = (w_oa * grow0 - w_c * rule["c0"]) / (grow0 - rule["c0"])          # вырез плотности своим счётом
    assert rule["w_rest"] == pytest.approx(w_rest, rel=1e-12) and w_rest != w_oa
    for key, c in cells.items():
        for i, r in enumerate(c["rows"]):
            d_end = r["fr_path"][-1] + sum(r["nb_ends"][b][-1] for b in ctx["biz"])
            assert close(r["cash"], rule["c"] * d_end, 1e-12), key
            assert close(r["funds"], d_end, 1e-12)
            assert close(r["oa"], (r_oa - rule["cut"]) * r["loans"] + r["cash"] + ctx["oaf"], 1e-12)
            ends = {**r["books_end"], cm.SECURITIES: r["securities"], cm.LIQUIDITY: r["liquidity"]}
            books = sum(float(dens[b]) * ends[b] for b in ctx["books"] if b in dens)
            other = w_rest * (r["oa"] - ctx["oaf"] - r["cash"]) + w_c * r["cash"] + ctx["dens_oaf"] * ctx["oaf"]
            mult = cm.c_rwa_mult(ctx, key[1], ctx["periods"][i]["year"], cm.QY)
            assert close(r["rwa"], (books + other) * r["dn_end"] * r["xf_end"] * mult, 1e-12), key
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            assert close(r["quarters"][-1]["cash"], r["cash"], 1e-9), key
            for j, x in enumerate(r["quarters"]):
                assert x["cash"] > 0.0
    lam = [r["lam_min"] for c in cells.values() for r in c["rows"]]
    assert min(lam) < 1.0, "нет квартала с урезанным ростом — деньги на пути λ не проверены"


@pytest.mark.tact
def test_k8_refusals(form):
    """Отказы: драйвер iea, слово не из перечня, веса на балансирующей книге (круг через ликвидность), неизвестная книга,
    все веса 0, нет плотности денег, плотность < 0, деньги < 0, денег не меньше растущей части прочих активов,
    ρ − C_0 / L_0 < 0, плотность растущей части после выреза < 0, anchor без узла фактов, не объект; уровень драйвера
    на якоре 0."""
    book, facts = form
    ctx0 = cm.c_control_context(book, facts)
    grow0 = ctx0["A"]["OA"] - ctx0["A"]["OA_fixed"]
    amount = 0.3 * grow0
    bads = [with_cash(book, amount, "iea"), with_cash(book, amount, "deposits"),
            with_cash(book, amount, {cm.LIQUIDITY: 1.0}), with_cash(book, amount, {"no_such_book": 1.0}),
            with_cash(book, amount, {cm.RETAIL_TERM: 0.0}), with_cash(book, amount, "funds", density=None),
            with_cash(book, amount, "funds", density=-0.1), with_cash(book, -1.0, "funds"),
            with_cash(book, grow0, "funds"), with_cash(book, "anchor", "funds"),
            with_cash(book, amount, "funds", density=1e6)]
    small = with_cash(book, amount, "funds")
    small["volumes"]["other_assets_to_loans"] = 0.1 * amount / sum(
        ctx0["A"]["E0"][b] for b in ctx0["loans"])                       # ρ, меньший доли денег (вход теста)
    bads.append(small)
    odd = copy.deepcopy(book)
    odd["volumes"]["cash_assets"] = {"amount": amount}
    bads.append(odd)
    for b2 in bads:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b2, facts)
    zero_facts = copy.deepcopy(facts)
    zero_facts["balance"]["books"][cm.RETAIL_TERM] = {"v": 0.0}
    with pytest.raises(cm.ControlInputError, match="D_0"):
        cm.c_cash_rule(with_cash(ctx0["B"], amount, {cm.RETAIL_TERM: 1.0}), {**ctx0["A"], "E0": {
            **ctx0["A"]["E0"], cm.RETAIL_TERM: 0.0}}, ctx0["books"])


# ============================================================================ К2б — смесь баз строки


@pytest.mark.tact
def test_k2b_example_by_own_code(anchor_books):
    """Пример К2б на остатках якоря книги репозитория: компиляция смесей по остаткам якоря — комиссии {КБ 0,855,
    розница 0,145} и страхование {розница 0,5, все кредиты 0,5} — веса к наибольшему 1 (1e-12); прочтение «вес КБ 0,5» —
    доли L_0 / (R_0 + L_0); конец оси «все кредиты» — C_0 / L_0; тождество индексов на концах кварталов
    D_q / D_0 = Σ s_k D^k_q / D^k_0 — точно до 1e-15."""
    book, facts, A, B = anchor_books
    k2b = example()["K2b"]
    fees = cm.c_base_mix(B, {"mix": {"corporate": {"share": 0.855, "base": {"corp_loans": 1.0}},
                                     "retail": {"share": 0.145, "base": RETAIL}}}, "fees.volume_base", A["E0"])
    ins = cm.c_base_mix(B, {"mix": {"retail": {"share": 0.5, "base": RETAIL}, "loans": {"share": 0.5, "base": "loans"}}},
                        "other.insurance_volume_base", A["E0"])
    for spec, want in ((fees, k2b["fees_mix_weights"]), (ins, k2b["ins_mix_S_weights"])):
        top = max(spec["w"].values())
        assert set(spec["w"]) == set(want)
        for b, w in want.items():
            assert rel(spec["w"][b] / top, w) <= 1e-12, b
    E0 = A["E0"]
    loans = [b for b, sp in B["nii"]["books"].items() if sp.get("sector")]
    r0, l0, c0 = sum(E0[b] for b in RETAIL), sum(E0[b] for b in loans), E0["corp_loans"]
    assert max(rel(r0, k2b["anchor_R0"]), rel(l0, k2b["anchor_L0"]), rel(c0, k2b["anchor_C0"])) <= 1e-12
    assert rel(l0 / (r0 + l0), k2b["ins_S_share_equiv_of_L"]) <= 1e-12
    assert rel(c0 / l0, k2b["fees_axis_all_loans_s_corp"]) <= 1e-12
    Eq = {b: E0[b] * GROW.get(b, 1.0) for b in E0}

    def level(w, E):
        return sum(x * E[b] for b, x in w.items())
    lhs = level(fees["w"], Eq) / level(fees["w"], E0)
    rhs = 0.855 * Eq["corp_loans"] / c0 + 0.145 * level(RETAIL, Eq) / r0
    assert rel(lhs, rhs) <= 1e-15 and rel(lhs, k2b["index_identity"]["fees_lhs"]) <= 1e-12
    lhs_i = level(ins["w"], Eq) / level(ins["w"], E0)
    rhs_i = 0.5 * level(RETAIL, Eq) / r0 + 0.5 * sum(Eq[b] for b in loans) / l0
    assert rel(lhs_i, rhs_i) <= 1e-15 and rel(lhs_i, k2b["index_identity"]["ins_lhs"]) <= 1e-12


def with_mix(book: dict, line: str, mix: dict, **extra) -> dict:
    out = tp2.with_bases(book, **{line: {"mix": copy.deepcopy(mix)}}, **extra)
    return out


def test_k2b_single_component_and_compiled_dict(form, hist):
    """Смесь из одной компоненты {loans: 1} ≡ слову loans (1e-9: история кредитов — узлы loans против остатков книг) и ≡
    весам 1 на кредитных книгах (1e-12); смесь ≡ своему компилированному словарю, записанному в книгу (бит в бит);
    масштаб весов компоненты — те же веса (1e-12)."""
    book, _ = form
    facts = hist
    loans = {b: 1.0 for b, sp in book["nii"]["books"].items() if sp.get("sector")}
    one = {"all": {"share": 1.0, "base": "loans"}}
    _, by_word = cells_of(tp2.with_bases(book, fees="loans", ins="loans"), facts)
    _, by_weights = cells_of(tp2.with_bases(book, fees=loans, ins=loans), facts)
    ctx, by_mix = cells_of(with_mix(with_mix(book, "fees", one), "ins", one), facts)
    tp1.same_cells(by_mix, by_word, 1e-9)
    tp1.same_cells(by_mix, by_weights, 1e-12)
    two = {"corp": {"share": 0.7, "base": {"corp_loans": 1.0, "sme_loans": 1.0}},
           "retail": {"share": 0.3, "base": {b: 1.0 for b in ("cards", "cash_loans", "auto", "mortgage")}}}
    ctx2, mixed = cells_of(with_mix(book, "fees", two, links=(1.0, 0.5, 0.4)), facts)
    compiled = ctx2["line_base"]["fees"]["w"]
    _, written = cells_of(tp2.with_bases(book, fees=dict(compiled), links=(1.0, 0.5, 0.4)), facts)
    for key in CELLS:
        mine, theirs = numbers(mixed[key]), numbers(written[key])
        assert mine == theirs, key
    scaled = copy.deepcopy(two)
    scaled["corp"]["base"] = {b: 7.0 * w for b, w in scaled["corp"]["base"].items()}
    ctx3 = cm.c_control_context(with_mix(book, "fees", scaled, links=(1.0, 0.5, 0.4)), facts)
    for b, w in compiled.items():
        assert rel(ctx3["line_base"]["fees"]["w"][b], w) <= 1e-12, b


def test_k2b_guarantees_and_driven_book_read_the_mix(form, hist):
    """RWA гарантий (К5) и книга-обязательство (К6) читают ту же компилированную базу, что строка (одна функция): у К5
    словарь драйвера равен словарю базы комиссий; ведомая книга идёт за смесью страхования — на концах лет уровень
    базы к якорю = Σ s_k D^k / D^k_0 (1e-12); смесь страхования с компонентой funds (ведомая книга в ней) или iea
    (балансирующие книги) — отказ круга."""
    book, _ = form
    facts = hist
    two = {"corp": {"share": 0.6, "base": {"corp_loans": 1.0}},
           "retail": {"share": 0.4, "base": {b: 1.0 for b in ("cards", "cash_loans", "auto")}}}
    b2, f2 = tp2.with_guarantees(with_mix(book, "fees", two), facts, base={"mix": two}, link0=False)
    ctx = cm.c_control_context(b2, f2)
    assert ctx["guar"]["spec"] == ctx["line_base"]["fees"]
    ins = {"retail": {"share": 0.5, "base": {b: 1.0 for b in ("cards", "cash_loans", "auto", "mortgage")}},
           "loans": {"share": 0.5, "base": "loans"}}
    driven = tp2.with_driven(with_mix(book, "ins", ins), link=1.0)
    ctx, cells = cells_of(driven, facts)
    spec = ctx["driven"][tp2.DRIVEN]["spec"]
    assert spec == ctx["line_base"]["ins"]
    E0 = ctx["A"]["E0"]
    retail = [b for b in ("cards", "cash_loans", "auto", "mortgage")]
    for key, c in cells.items():
        for r in c["rows"]:
            ends = {**r["books_end"]}
            lhs = sum(w * ends[b] for b, w in spec["w"].items()) / sum(w * E0[b] for b, w in spec["w"].items())
            rhs = (0.5 * sum(ends[b] for b in retail) / sum(E0[b] for b in retail)
                   + 0.5 * sum(ends[b] for b in ctx["loans"]) / sum(E0[b] for b in ctx["loans"]))
            assert close(lhs, rhs, 1e-12), key
    for comp in ("funds", "iea"):
        bad = tp2.with_driven(with_mix(book, "ins", {"a": {"share": 0.5, "base": comp},
                                                     "b": {"share": 0.5, "base": "loans"}}), link=1.0)
        with pytest.raises(cm.ControlInputError, match="liability_drivers"):
            cm.c_control_context(bad, facts)


@pytest.mark.tact
def test_k2b_refusals(form, hist):
    """Отказы смеси: сумма долей не 1 (1e-9), доля вне [0; 1], компонента nominal, неизвестное слово или книга, все
    веса 0, смесь в смеси, пустая смесь, лишние поля, компонента не объект, уровень компоненты на якоре 0."""
    book, _ = form
    facts = hist
    ok = {"share": 0.5, "base": "loans"}
    bads = [{"a": ok, "b": {"share": 0.4, "base": "funds"}}, {"a": ok, "b": {"share": 1.5, "base": "funds"}},
            {"a": ok, "b": {"share": 0.5, "base": "nominal"}}, {"a": ok, "b": {"share": 0.5, "base": "assets"}},
            {"a": ok, "b": {"share": 0.5, "base": {"no_such_book": 1.0}}},
            {"a": ok, "b": {"share": 0.5, "base": {"corp_loans": 0.0}}},
            {"a": ok, "b": {"share": 0.5, "base": {"mix": {"x": {"share": 1.0, "base": "loans"}}}}},
            {}, {"a": ok, "b": 0.5}, {"a": ok, "b": {"share": 0.5, "base": "funds", "extra": 1}},
            {"a": ok, "b": {"share": None, "base": "funds"}}]
    for mix in bads:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(with_mix(book, "fees", mix, links=(1.0, 0.5, 0.4)), facts)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(tp2.with_bases(book, fees={"mix": {"a": {"share": 1.0, "base": "loans"}}, "w": 1},
                                            links=(1.0, 0.5, 0.4)), facts)
    ctx = cm.c_control_context(book, facts)
    with pytest.raises(cm.ControlInputError, match="D_0"):
        cm.c_base_mix(ctx["B"], {"mix": {"a": {"share": 1.0, "base": {"corp_loans": 1.0}}}}, "fees.volume_base",
                      {**ctx["A"]["E0"], "corp_loans": 0.0})
    within = {"a": {"share": 0.5 + 4e-10, "base": "loans"}, "b": {"share": 0.5, "base": "funds"}}
    assert cm.c_control_context(with_mix(book, "fees", within, links=(1.0, 0.5, 0.4)), facts)["line_base"]["fees"]


# ============================================================================ правило ПОРОГ (Р4-16)


@pytest.fixture(scope="module")
def keyed_run(form):
    """Прогон фикстуры со всеми ключами второго прохода (жетон, урезание роста, гарантии, опт, ведомая книга)."""
    return cm.c_control_run(*tp2.all_keys(*form))


def _flip_token(stub, ctl: dict, *, near: bool) -> tuple[str, dict]:
    """Жетон ядра в одной клетке — обратный контрольному: решение-носитель с уплаченным у контроля жетоном (у контроля z
    и need — вне порога) получает у ядра 0, запас ядра H_fl — у порога (near: z ядра = ε / 2) или далеко (10 ε)."""
    for c in ctl["cells"]:
        rwa = {x["q"]: x["rwa"] for r in c["rows"] for x in r["quarters"]}
        for d in c["decisions_q"]:
            if not d.get("token"):
                continue
            rule, eps = d["token_rule"], tcm.EPS_THRESHOLD * rwa[d["q"]]
            if abs(rule["h_floor"] - rule["model_base"] - rule["need"]) <= eps or rule["need"] <= eps:
                continue
            cell = stub.cell(c["world"], c["regime"], c["scenario"])
            hfl = rule["model_base"] + rule["need"] + (0.5 if near else 10.0) * eps
            cell.decisions = [type(x)(**{**vars(x), "token": 0.0, "headroom_floor": hfl, "source": "model",
                                         "base_div": rule["model_base"]}) if x.period == d["period"] else x
                              for x in cell.decisions]
            return "/".join((c["world"], c["regime"], c["scenario"])), d
    pytest.fail("на фикстуре нет уплаченного жетона вне порога у контрольной модели")


@pytest.mark.tact
def test_threshold_example():
    """Пример методики: ε = 0,3 п.п. × RWA квартала решения; z ядра +2,74 и контроля −0,12 — у порога; need 0,58 ≤ ε —
    у порога (случай need → 0)."""
    th = example()["threshold"]
    eps = tcm.EPS_THRESHOLD * 4270.0                                     # RWA квартала решения примера (вход)
    assert eps == pytest.approx(th["eps"], rel=1e-12)
    assert (abs(th["z_core"]) <= eps or abs(th["z_control"]) <= eps) is th["at_threshold"] is True
    assert (th["need_to_zero"]["need"] <= eps) is th["need_to_zero"]["at_threshold"]


def test_threshold_rule_on_a_stub_core(keyed_run):
    """Правило ПОРОГ на заглушке ядра из чисел контроля: без расхождений исключать нечего (все строки судятся, отчёт
    пуст); жетон ядра в одной клетке обратный, запас ядра у порога — признак и строки клетки с квартала решения (DPS,
    дивиденд, BV, нормативы, строки за λ — годов не раньше решения; X_T, Y_X, ROE'_T, TV, V_c) не судятся, отчёт их
    считает и печатает V_c рядом; слои, цена, мост — судятся всегда; запас далеко от порога — признак судится и
    красный. Урезание роста: исход года у ядра другой — строки за λ клетки с этого года не судятся."""
    ctl = keyed_run
    stub = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    rows, rep = tcm.reconcile(stub, ctl)
    assert rep["n_excluded"] == 0 and not rep["cells"] and all(r["ok"] for r in rows)
    n_all = len(rows)
    tag, d = _flip_token(stub, ctl, near=True)
    rows, rep = tcm.reconcile(stub, ctl)
    assert all(r["ok"] for r in rows), tcm._fail_lines([r for r in rows if not r["ok"]])
    assert rep["token"] > 0 and [c["cell"] for c in rep["cells"]] == [tag]
    assert rep["values"] and rep["values"][0]["cell"] == tag
    year = cm.c_qper(ctl["ctx"]["anchor"], d["q"])[0]
    dropped = [r for r in tcm.all_rows(stub, ctl) if r.get("cell") == tag]
    groups_out = {r["group"] for r in dropped} - {r["group"] for r in rows if r.get("cell") == tag}
    assert {"cell", "x_t", "y_x", "tv", "roe_t", "bb_s_price"} & {r["group"] for r in dropped} <= groups_out
    assert {"cell", "x_t", "tv", "roe_t"} <= groups_out
    # строки клетки с квартала решения (перечень — словами методики, а не константами правила): DPS, дивиденд, BV,
    # нормативы; строки за λ — RWA гарантий, опт, ведомая книга, рост баз строк; признак жетона
    dated = ("dps", "dps_q", "div", "bv", "n20", "n11", "token", "rwa_guar", "wholesale", "driven", "v_fees", "v_ins",
             "v_opex")
    left = [r for r in rows if r.get("cell") == tag and r["group"] in dated
            and not ((r.get("q") is not None and r["q"] < d["q"]) or (r.get("q") is None and r["year"] < year))]
    assert not left, [r["what"] for r in left][:5]
    assert {"rwa_guar", "wholesale", "driven"} <= {r["group"] for r in dropped if r.get("year", 0) >= year}
    assert any(r["group"] == "value" for r in rows) and len(rows) < n_all + 1
    assert rep["share"] <= tcm.THRESHOLD_SHARE_MAX
    far = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    _flip_token(far, ctl, near=False)
    rows, rep = tcm.reconcile(far, ctl)
    assert rep["token"] == 0
    assert [r["group"] for r in rows if not r["ok"]] == ["token"]
    cut = tcm._stub_core(ctl, 1.0 / 1.01, d_ratio=0.001)
    c = next(c for c in ctl["cells"] if any(r["lam_min"] < 1.0 for r in c["rows"]))
    i = next(i for i, r in enumerate(c["rows"]) if r["lam_min"] < 1.0)
    cell = cut.cell(c["world"], c["regime"], c["scenario"])
    cell.growth["lam_min"] = [1.0 if j == i else v for j, v in enumerate(cell.growth["lam_min"])]
    rows, rep = tcm.reconcile(cut, ctl)
    tag = "/".join((c["world"], c["regime"], c["scenario"]))
    assert rep["growth_cut"] > 0 and rep["cells"][0]["from"] == ctl["years"][i]
    left = {r["group"] for r in rows if r.get("cell") == tag and r.get("year", 0) >= ctl["years"][i]}
    assert not left & set(tcm.LAMBDA_GROUPS) and {"growth_actual", "cut_share", "bv", "rwa"} <= left


@pytest.mark.tact
def test_threshold_guard_and_never_excluded_rows():
    """Сторож правила: доля исключённых строк клеток больше 10 % — строка вне допуска; исключена вся группа строк —
    строка вне допуска; строки без клетки (передача, слои, цена, мост) правило не трогает."""
    rows = [tcm._row(f"строка {i}", tcm.U_BN, 1.0, 1.0, tcm.TOL_LINE, tcm.REL, group="nii") for i in range(20)]
    rows += [tcm._row("V0", tcm.U_BN, 1.0, 1.0, tcm.TOL_VALUE, tcm.REL, group="value"),
             tcm._row("x", tcm.U_BN, 1.0, 1.0, tcm.TOL_LINE, tcm.REL, group="x_t")]
    for i, r in enumerate(rows):
        if r["group"] != "value":
            r.update(cell="N/norm/mid" if i < 2 or r["group"] == "x_t" else "H/norm/mid", year=2030)
    rule = {"cell": "N/norm/mid", "reason": "token", "q": None, "year": 2028, "years": None, "from": 2028,
            "z_core": 1.0, "z_control": -1.0, "eps": 5.0, "groups": ("nii",), "whole": ("x_t",)}
    stub = type("S", (), {"cell": staticmethod(lambda w, r, s: type("C", (), {"v_ri": 1.0})())})()
    ctl = {"cells": [{"world": "N", "regime": "norm", "scenario": "mid", "v_ri": 1.0}]}
    kept, rep = tcm.apply_threshold(rows, [rule], stub, ctl)
    assert rep["n_excluded"] == 3 and rep["token"] == 3 and rep["whole_groups"] == ["x_t"]
    assert any(r["group"] == "value" for r in kept)
    guard = [r for r in kept if r["group"] == "threshold"]
    assert len(guard) == 2 and not guard[1]["ok"] and guard[1]["control"] == 0.0
    assert rep["share"] == pytest.approx(3 / 21) and not guard[0]["ok"]
    for r in guard:
        tcm._assert_row_form(tcm._public(r))
