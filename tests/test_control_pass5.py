# -*- coding: utf-8 -*-
"""Контрольная модель: ключ пятого прохода ядра Совкомбанка (core-pass5) своим счётом.

Ключ (решения ведущего № 6, Р6-1; методика — spec.yaml прохода 5, пример — tests/fixtures/core_pass5/example.json, копия
примера методики; фрагмент книги — tests/fixtures/core_pass5/book_keys_pass5.yaml, копия фрагмента методики):

* Р6-1 — доля неработающих денег К8 — параметр книги (`volumes.cash_assets.share`, `reserves`, `share_from`,
  `displaced_weight`): деньги якоря — факт; доля без ФОР идёт от доли якоря s_0 линейно по кварталам к доле книги s* до
  квартала share_from; ФОР — доля якоря R_0 / D_0; вычет из растущих прочих активов — c_k D_0 / L_0 (структура якоря);
  вытесненная (добавленная) часть прочих активов несёт в RWA слагаемое (1 − θ)(ω' − ω_c) δ_k L.

Без ключа и при share: anchor контрольная модель считает бит в бит прежние числа — это держит сводка
(tests/independent_model.py на книге репозитория) и тесты «ключ нейтрален» ниже. Сверка с ядром (метка ci_only) требует ядра
с проходом 5: нет ядра, его функции или ключа в схеме ядра — провал, не пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import importlib
import json

import pytest
import yaml

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
    from tests import test_control_pass2 as tp2
    from tests import test_control_pass4 as tp4
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_pass2 as tp2                    # type: ignore[no-redef]
    import test_control_pass4 as tp4                    # type: ignore[no-redef]

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass5"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass5.yaml"
CASH = "volumes.cash_assets"
DROP = object()

rel, close, numbers = tp2.rel, tp2.close, tp2.numbers


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def fragment_fields() -> dict:
    """Поля доли денег фрагмента книги методики (центр: s*, ФОР якоря, квартал доли книги, θ)."""
    frag = yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8"))
    node = frag["volumes"]["cash_assets"]
    return {k: node[k] for k in cm.CASH_SHARE_FIELDS}


def keyed(book: dict, **fields) -> dict:
    """Книга с полями доли денег: фрагмент методики (центр) с подменами fields; DROP — поле снято."""
    out = copy.deepcopy(book)
    node = out["volumes"]["cash_assets"]
    node.update(fragment_fields())
    for k, v in fields.items():
        if v is DROP:
            node.pop(k, None)
        else:
            node[k] = v
    return out


def plain(book: dict) -> dict:
    """Книга без полей доли денег (К8 прежний) и без осей на путях `volumes.cash_assets` (доля и θ — интеграция круга 6
    поставила ключ и две оси в книгу дерева; на пути оси вида value схема ядра требует числа: share: anchor на книге с осью
    доли — отказ схемы, а сверка share: anchor — с книгой без ключа)."""
    out = copy.deepcopy(book)
    for k in cm.CASH_SHARE_FIELDS:
        out["volumes"]["cash_assets"].pop(k, None)
    unc = out["valuation"]["uncertainty"]
    unc["axes"] = [a for a in unc["axes"] if not any(str(p).startswith("volumes.cash_assets.") for p in a["paths"])]
    return out


@pytest.fixture(scope="module")
def repo():
    book, facts = tcm._inputs()
    return plain(book), facts


@pytest.fixture(scope="module")
def centre(repo):
    """Контекст и клетки книги репозитория с полями доли денег в центре (s* = 0,0576, θ = 0,5, с 2026Q4)."""
    book, facts = repo
    ctl = cm.c_control_run(keyed(book), facts)
    return ctl["ctx"], {(c["world"], c["regime"], c["scenario"]): c for c in ctl["cells"]}


def rule_of(book: dict, facts: dict) -> tuple[dict, dict]:
    ctx = cm.c_control_context(book, facts)
    return ctx, ctx["cash"]


# ============================================================================ пример и путь


@pytest.mark.tact
def test_p5_example_by_own_code(repo):
    """Пример Р6-1 (example.json) на остатках якоря книги репозитория своим счётом: s_0, r, c_0, c*, C*_0, q_f, ρ′_0, ρ′*,
    ω' выреза на раскладке факта, ω_d = θ ω' + (1 − θ) ω_c, ω' выреза на раскладке книги (Д1, отвергнуто), скачок RWA шага
    при θ = 1; путь первых кварталов (s, c, ρ′, δ); кварталы примера (кредиты × 1,02, средства × 1,03): деньги, прочие
    активы, RWA прочих активов с ключом и без, при θ = 1 и θ = 0 (1e-12); θ — линейная смесь концов (1e-9)."""
    book, facts = repo
    ex = example()
    ctx, rule = rule_of(keyed(book), facts)
    p = rule["path"]
    B, A = ctx["B"], ctx["A"]
    f, bk, d = ex["facts"], ex["book"], ex["derived"]
    oaf = ctx["oaf"]
    assert rule["c0"] == f["C_0"] and p["r0"] == f["R_0_mandatory_reserves"] and oaf == f["F_A"]
    assert rel(rule["c0"] - p["r0"], f["M_0_money_ex_reserves"]) <= 1e-12
    assert rel(rule["d0"], f["D_0_funds_four_books"]) <= 1e-12 and rel(p["l0"], f["L_0"]) <= 1e-12
    assert A["OA"] == f["OA_0"] and rel(A["OA"] - oaf, f["growing_OA_0"]) <= 1e-12
    rho = cm.c_bnum(B, "volumes.other_assets_to_loans")
    dens = ctx["dens"]
    w_oa, w_c, w_oaf = float(dens["other_assets"]), float(dens["cash_assets"]), float(dens["other_assets_fixed"])
    assert rel(rho, bk["rho"]) <= 1e-12 and (w_oa, w_c, w_oaf) == (bk["omega_oa"], bk["omega_c"], bk["omega_oaf"])
    assert (p["s_star"], p["theta"]) == (bk["share"], bk["displaced_weight"])
    c_star = p["s_star"] + p["r"]
    grow0 = A["OA"] - oaf
    for got, want in ((p["s0"], d["s_0"]), (p["r"], d["r"]), (rule["c"], d["c_0"]), (c_star, d["c_star"]),
                      (c_star * rule["d0"], d["C_star_0"]), (rho - rule["cut"], d["rho_prime_0"]),
                      (rho - cm.c_cash_cut(rule, p["q_f"]), d["rho_prime_star"]),
                      (rule["w_rest"], d["omega_rest_fact_carve"]),
                      (p["theta"] * rule["w_rest"] + (1.0 - p["theta"]) * w_c, d["omega_d"]),
                      ((w_oa * grow0 - w_c * c_star * rule["d0"]) / (grow0 - c_star * rule["d0"]),
                       d["omega_rest_book_carve_D1_rejected"]),
                      (-(rule["w_rest"] - w_c) * (c_star - rule["c"]) * rule["d0"], d["rwa_jump_q1_if_step_theta1"])):
        assert rel(got, want) <= 1e-12, (got, want)
    assert p["q_f"] == d["q_from"] == cm.c_qidx(A["anchor"], *cm.c_per_parse(bk["share_from"]))
    for k, (label, pq) in enumerate(ex["path_first_quarters"].items()):
        assert cm.c_qper(A["anchor"], k) == cm.c_per_parse(label)
        c_k = cm.c_cash_c(rule, k)
        assert rel(c_k, pq["c"]) <= 1e-12 and rel(c_k - p["r"], pq["s"]) <= 1e-12
        assert rel(rho - cm.c_cash_cut(rule, k), pq["rho_prime"]) <= 1e-12
        assert abs((c_k - rule["c"]) * rule["d0"] / p["l0"] - pq["delta"]) <= 1e-15
    others = {th: rule_of(keyed(book, displaced_weight=th), facts)[1] for th in (0.0, 1.0)}
    for label, q in ex["quarters"].items():
        k = cm.c_qidx(A["anchor"], *cm.c_per_parse(label))
        assert k == q["q"]
        loans, funds = p["l0"] * q["loans_x"], rule["d0"] * q["funds_x"]
        c_k = cm.c_cash_c(rule, k)
        cash = c_k * funds
        oa = (rho - cm.c_cash_cut(rule, k)) * loans + cash + oaf
        cash_old = rule["c"] * funds
        oa_old = (rho - rule["cut"]) * loans + cash_old + oaf

        def rwa_other(r, oa_, cash_, disp):
            return r["w_rest"] * (oa_ - oaf - cash_) + r["w_cash"] * cash_ + w_oaf * oaf + (disp or 0.0)

        with_key = rwa_other(rule, oa, cash, cm.c_cash_disp(rule, k, loans))
        old = rwa_other(rule, oa_old, cash_old, None)
        th1 = rwa_other(others[1.0], oa, cash, cm.c_cash_disp(others[1.0], k, loans))
        th0 = rwa_other(others[0.0], oa, cash, cm.c_cash_disp(others[0.0], k, loans))
        for got, want in ((c_k - p["r"], q["share_ex_reserves"]), (c_k, q["c_q"]), (cash, q["cash"]),
                          (rho - cm.c_cash_cut(rule, k), q["rho_q"]), (oa, q["oa"]), (oa_old, q["oa_without_key"]),
                          (with_key, q["rwa_other_assets"]), (old, q["rwa_other_assets_without_key"])):
            assert rel(got, want) <= 1e-12, (label, got, want)
        for got, want in ((with_key - old, q["d_rwa_vs_without_key"]), (th1 - old, q["d_rwa_theta1"]),
                          (th0 - old, q["d_rwa_theta0"])):
            assert abs(got - want) <= 1e-12 * max(abs(old), 1.0), (label, got, want)
        assert cm.c_cash_disp(others[1.0], k, loans) is None
        assert rel(with_key, (th0 + th1) / 2.0) <= 1e-9                  # θ — линейная смесь концов


@pytest.mark.tact
def test_p5_path_by_own_code(repo):
    """Путь доли: c_0 = C_0 / D_0 (вычет якоря — C_0 / L_0); с квартала share_from — ровно доля книги s* + r; до него —
    между долей якоря и долей книги, монотонно; share_from — первый прогнозный квартал — шаг; слагаемого RWA нет при θ = 1
    и без поля, на якоре — ноль, линейно по (1 − θ); без поля share — прежний c во всех кварталах."""
    book, facts = repo
    _, rule = rule_of(keyed(book), facts)
    p = rule["path"]
    c_star = p["s_star"] + p["r"]
    assert cm.c_cash_c(rule, 0) == rule["c0"] / rule["d0"] and cm.c_cash_cut(rule, 0) == rule["cut"]
    assert rel(rule["c"], p["s0"] + p["r"]) <= 1e-15
    assert all(cm.c_cash_c(rule, k) == c_star for k in range(p["q_f"], 41))
    for k in range(1, p["q_f"]):
        assert min(rule["c"], c_star) < cm.c_cash_c(rule, k) < max(rule["c"], c_star)
    seq = [cm.c_cash_c(rule, k) for k in range(p["q_f"] + 1)]
    assert seq == sorted(seq) or seq == sorted(seq, reverse=True)
    yq = cm.c_qper(tuple(cm.c_per_parse(book["meta"]["anchor_period"])), 1)
    _, step = rule_of(keyed(book, share_from=f"{yq[0]}Q{yq[1]}"), facts)
    assert step["path"]["q_f"] == 1 and all(cm.c_cash_c(step, k) == c_star for k in range(1, 41))
    assert cm.c_cash_disp(rule, 0, 1000.0) == 0.0
    for th in (DROP, 1.0):
        _, r1 = rule_of(keyed(book, displaced_weight=th), facts)
        assert r1["path"]["k_disp"] is None and cm.c_cash_disp(r1, 5, 1000.0) is None
    d = {th: cm.c_cash_disp(rule_of(keyed(book, displaced_weight=th), facts)[1], 5, 1000.0) for th in (0.0, 0.25, 0.5)}
    assert rel(d[0.25], 0.75 * d[0.0]) <= 1e-12 and rel(d[0.5], 0.5 * d[0.0]) <= 1e-12
    assert rel(d[0.0], (rule["w_rest"] - rule["w_cash"]) * (c_star - rule["c"]) * rule["d0"] / p["l0"] * 1000.0) <= 1e-12
    _, old = rule_of(book, facts)
    assert old["path"] is None and all(cm.c_cash_c(old, k) == old["c"] and cm.c_cash_cut(old, k) == old["cut"]
                                       for k in range(0, 41))
    assert cm.c_cash_disp(old, 5, 1000.0) is None and cm.c_cash_disp(None, 5, 1000.0) is None


@pytest.mark.tact
def test_p5_balance_total_is_the_same_at_the_anchor_structure(repo):
    """При D / L якоря итог прочих активов OA = (ρ − c_k D_0 / L_0) L + c_k D + F_A = ρ L + F_A для любой доли и
    квартала (1e-12): доля меняет раскладку «деньги за средствами / прочее за кредитами», а не итог."""
    book, facts = repo
    for share in (0.0, 0.0453, 0.0576, 0.0695):
        ctx, rule = rule_of(keyed(book, share=share), facts)
        rho = cm.c_bnum(ctx["B"], "volumes.other_assets_to_loans")
        for k in range(0, 9):
            for x in (0.8, 1.0, 1.37):
                loans, funds = rule["path"]["l0"] * x, rule["d0"] * x
                oa = (rho - cm.c_cash_cut(rule, k)) * loans + cm.c_cash_c(rule, k) * funds + ctx["oaf"]
                assert close(oa, rho * loans + ctx["oaf"], 1e-12), (share, k, x)


# ============================================================================ прежняя ветвь и тождества


def run_numbers(ctl: dict) -> list:
    return [[ctl["point"], ctl.get("low"), ctl.get("high")]] + [numbers(c) for c in ctl["cells"]]


def test_p5_neutral_cases_are_bit_for_bit(repo):
    """share: anchor ≡ полей нет (прочие поля — ключ неактивного режима, ФОР anchor без узла фактов не читается) и
    θ = 1 ≡ поля displaced_weight нет — все клетки, точка, низ и верх бит в бит."""
    book, facts = repo
    base = run_numbers(cm.c_control_run(book, facts))
    no_node = copy.deepcopy(facts)
    no_node["balance"]["nonworking_money"].pop("mandatory_reserves")
    assert run_numbers(cm.c_control_run(keyed(book, share="anchor"), no_node)) == base
    th1 = run_numbers(cm.c_control_run(keyed(book, displaced_weight=1.0), facts))
    assert th1 == run_numbers(cm.c_control_run(keyed(book, displaced_weight=DROP), facts))
    assert th1 != base


def test_p5_theta0_step_is_the_book_carve(repo):
    """θ = 0 и share_from — первый прогнозный квартал ≡ прежний К8 с деньгами якоря c* D_0 (share: anchor): вырез на
    раскладке книги (класс 1: вытесненная часть весит как деньги — это и есть приближение k8w). Прочие активы, деньги,
    RWA, капитал, ЧПД, норматив и среднее небалансирующих активов по годам, стоимость всех клеток: при выключенном
    ограничении роста у обеих книг — до 1e-12; с ограничением — до 1e-9 (долю прироста контроль ищет делением отрезка до
    1e-9, и машинная разность двух форм одного числа сдвигает её в пределах этой точности; урезание есть во всех клетках
    книги), точка — до 1e-12. Среднее небалансирующих — среднее трапеций произведения «вычет × кредиты»: вычет × среднее
    кредитов на якорной части пути дал бы разницу (C_0 − c* D_0) / 2n."""
    book, facts = repo
    ctx, rule = rule_of(keyed(book), facts)
    yq = cm.c_qper(ctx["A"]["anchor"], 1)
    amount = (rule["path"]["s_star"] + rule["path"]["r"]) * rule["d0"]
    for off, tol in ((True, 1e-12), (False, 1e-9)):
        step = keyed(book, displaced_weight=0.0, share_from=f"{yq[0]}Q{yq[1]}")
        carve = copy.deepcopy(book)
        carve["volumes"]["cash_assets"].update(amount=amount, share="anchor")
        if off:
            step["capital"]["growth_constraint"]["enabled"] = carve["capital"]["growth_constraint"]["enabled"] = False
        mine, theirs = cm.c_control_run(step, facts), cm.c_control_run(carve, facts)
        assert rel(mine["point"], theirs["point"]) <= 1e-12, off
        for a, b in zip(mine["cells"], theirs["cells"]):
            key = (a["world"], a["regime"], a["scenario"], off)
            for name in ("v_ri", "tv_ri", "x_t"):
                assert close(a[name], b[name], tol), (name, key)
            for i, (ra, rb) in enumerate(zip(a["rows"], b["rows"])):
                for line in ("oa", "cash", "rwa", "bv", "liquidity", "nii", "n20", "assets_nb_avg"):
                    assert close(ra[line], rb[line], tol), (line, key, i)


def test_p5_rows_follow_the_path(centre):
    """Книга с ключом в центре, все клетки: доли на концах кварталов — функция квартала (одни во всех клетках, класс 2);
    деньги конца года — c_k × уровень драйвера; прочие активы — (ρ − c_k D_0 / L_0) кредиты + деньги + постоянные; RWA —
    с вырезом на раскладке факта и слагаемым вытесненной части под дрейфом, валютным индексом и множителем режима
    (1e-12); квартальный проход кончает год на тех же деньгах и RWA (1e-9); баланс сходится; переходное слагаемое
    c_k − c_Q — ноль с квартала share_from (класс 5)."""
    ctx, cells = centre
    rule, p = ctx["cash"], ctx["cash"]["path"]
    r_oa = cm.c_bnum(ctx["B"], "volumes.other_assets_to_loans")
    dens, oaf = ctx["dens"], ctx["oaf"]
    c_star = p["s_star"] + p["r"]
    shares = None
    for key, c in cells.items():
        mine = [r["cash_c"] for r in c["rows"]]
        shares = mine if shares is None else shares
        assert mine == shares, key                                          # класс 2: путь — доли, одни во всех клетках
        for i, r in enumerate(c["rows"]):
            per = ctx["periods"][i]
            k_end = cm.c_qidx(ctx["anchor"], per["year"], per["quarters"][-1])
            assert r["cash_c"][-1] == cm.c_cash_c(rule, k_end)
            d_end = sum(w * r["nb_ends"][b][-1] for b, w in rule["w"].items())
            assert close(r["cash"], r["cash_c"][-1] * d_end, 1e-12), key
            assert close(r["oa"], (r_oa - r["cash_c"][-1] * rule["d0"] / p["l0"]) * r["loans"] + r["cash"] + oaf, 1e-12)
            disp = (1.0 - p["theta"]) * (rule["w_rest"] - rule["w_cash"]) * (r["cash_c"][-1] - rule["c"]) \
                * rule["d0"] / p["l0"] * r["loans"]
            assert close(r["cash_disp"], disp, 1e-12)
            ends = {**r["books_end"], cm.SECURITIES: r["securities"], cm.LIQUIDITY: r["liquidity"]}
            books = sum((ctx["guar"]["w_carved"] if ctx.get("guar") and b == ctx["guar"]["carve"] else float(dens[b]))
                        * ends[b] for b in ctx["books"] if b in dens)
            other = (rule["w_rest"] * (r["oa"] - oaf - r["cash"]) + rule["w_cash"] * r["cash"]
                     + ctx["dens_oaf"] * oaf + (r.get("guar") or 0.0) + disp)
            mult = cm.c_rwa_mult(ctx, key[1], per["year"], per["quarters"][-1])
            assert close(r["rwa"], (books + other) * r["dn_end"] * r["xf_end"] * mult, 1e-12), key
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            assert close(r["quarters"][-1]["cash"], r["cash"], 1e-9), key
            assert close(r["quarters"][-1]["rwa"], r["rwa"], 1e-9), key
            if k_end >= p["q_f"]:
                assert r["cash_c"][-1] - c_star == 0.0                       # класс 5: переходное слагаемое снято
    first = shares[0]
    assert first[0] == rule["c"] and first[-1] == c_star and rule["c"] < first[1] < c_star
    assert all(x == c_star for row in shares[1:] for x in row)


def test_p5_cash_with_loans_and_anchor_is_no_key(repo):
    """Ловушка драйвера (вариант cash_with_loans): драйвер loans с share: anchor ≡ ключа К8 нет (1e-12); с числовой
    долей s* ляжет на кредиты — числа другие (подмена share: anchor в варианте нужна)."""
    book, facts = repo
    none = copy.deepcopy(book)
    none["volumes"]["cash_assets"] = None
    _, base = tp2.cells_of(none, facts)
    _, loans_anchor = tp2.cells_of(keyed(book, share="anchor", driver="loans"), facts)
    _, loans_share = tp2.cells_of(keyed(book, driver="loans"), facts)
    for key in tp2.CELLS:
        for name in ("v_ri", "tv_ri", "x_t"):
            assert rel(loans_anchor[key][name], base[key][name]) <= 1e-12, (key, name)
        assert rel(loans_share[key]["v_ri"], base[key]["v_ri"]) > 1e-6, key


# ============================================================================ отказы


@pytest.mark.tact
def test_p5_refusals(repo):
    """Отказы: доля не число в [0; 1) (≥ 1, < 0, строка, логическое, null); при числовой доле нет reserves или
    share_from; share_from — не квартал, квартал якоря или раньше, позже meta.last_period; reserves < 0 или не число;
    θ вне [0; 1] или не число; reserves, share_from, displaced_weight без share; ФОР больше денег якоря; ρ′* < 0 (с
    числами); reserves: anchor без узла фактов; лишнее поле. share: anchor — поля формы проверяются, но не читаются."""
    book, facts = repo
    anchor = book["meta"]["anchor_period"]
    after_last = cm.c_qper(cm.c_per_parse(book["meta"]["last_period"]), 1)
    bads = [keyed(book, share=1.0), keyed(book, share=-0.01), keyed(book, share="0.05"), keyed(book, share=True),
            keyed(book, share=None), keyed(book, reserves=DROP), keyed(book, share_from=DROP),
            keyed(book, share_from="2026-Q4"), keyed(book, share_from=2026), keyed(book, share_from=anchor),
            keyed(book, share_from="2020Q1"), keyed(book, share_from=f"{after_last[0]}Q{after_last[1]}"),
            keyed(book, reserves=-1.0), keyed(book, reserves="13.151"), keyed(book, displaced_weight=1.5),
            keyed(book, displaced_weight=-0.1), keyed(book, displaced_weight="half"),
            keyed(book, displaced_weight=True), keyed(book, reserves=1000.0), keyed(book, share=0.99),
            keyed(book, share="anchor", share_from="Q4"), keyed(book, share="anchor", displaced_weight=2.0)]
    for f in ("reserves", "share_from", "displaced_weight"):
        bads.append(keyed(book, share=DROP, **{k: DROP for k in ("reserves", "share_from", "displaced_weight")
                                                if k != f}))
    odd = keyed(book)
    odd["volumes"]["cash_assets"]["share_speed"] = 0.62
    bads.append(odd)
    for b in bads:
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(b, facts)
    with pytest.raises(cm.ControlInputError, match="ρ′"):
        cm.c_control_context(keyed(book, share=0.99), facts)
    c0 = rule_of(book, facts)[1]["c0"]
    with pytest.raises(cm.ControlInputError, match="больше денег якоря"):     # ρ′* при этом ФОР ещё ≥ 0 (вход теста)
        cm.c_control_context(keyed(book, reserves=1.1 * c0), facts)
    with pytest.raises(cm.ControlInputError, match="читается только при share"):
        cm.c_control_context(keyed(book, share=DROP, reserves=DROP, displaced_weight=DROP), facts)
    no_node = copy.deepcopy(facts)
    no_node["balance"]["nonworking_money"].pop("mandatory_reserves")
    with pytest.raises(cm.ControlInputError, match="mandatory_reserves"):
        cm.c_control_context(keyed(book), no_node)
    assert cm.c_control_context(keyed(book, reserves=13.151), no_node)["cash"]["path"]["r0"] == 13.151
    ok = cm.c_control_context(keyed(book, share="anchor"), no_node)["cash"]
    assert ok["path"] is None
    last = book["meta"]["last_period"]
    assert cm.c_control_context(keyed(book, share_from=last), facts)["cash"]["path"]["q_f"] == cm.c_qidx(
        cm.c_per_parse(anchor), *cm.c_per_parse(last))


# ============================================================================ сверка с ядром (ci_only)


def core_run(book: dict):
    return tcm.core_run_of(copy.deepcopy(book))


def reconcile_rows(book: dict, facts: dict):
    ctl = cm.c_control_run(book, facts)
    run = core_run(book)
    return run, ctl, tcm.compare_with_core(run, ctl)


def _fail(run, ctl, rows: list[dict]) -> None:
    """Сверка М§17 на ядре: строки вне допуска — только класс Р6-9 (`tcm.fail_off_rows`, Д16)."""
    tcm.fail_off_rows(run, ctl, rows)


# подмены одного поля книги с ключом: концы осей доли и θ, прежняя ветвь, глиссада к 2029Q4 — сверка М§17 без строк вне
# допуска на прототипе ядра; центр и шаг (share_from — первый прогнозный квартал) при θ = 0,5 — 3 строки класса Р6-9. На ядре
# p3 @ 48f3ca2 (книга круга 7) θ = 1 — те же 3 строки RWA гарантий M/downturn 2027–2028 (615,38 против 609,22, 1,00 %):
# известный красный Р8-9 (решения ведущего № 8; ops/expected_counts.json → known_failures)
AXIS_CASES = {"share_anchor": {"share": "anchor"}, "theta0": {"displaced_weight": 0.0},
              "theta1": {"displaced_weight": 1.0}, "share_low": {"share": 0.0453}, "share_high": {"share": 0.0695},
              "glide_2029": {"share_from": "2029Q4"}}
CUT_CLASS_CASES = {"centre": {}, "step": {"share_from": "2026Q3"}, "theta1": {"displaced_weight": 1.0}}


@pytest.mark.ci_only
def test_p5_control_matches_core_on_the_keyed_book(repo):
    """Книга с ключом в центре (s* = 0,0576, ФОР якоря, с 2026Q4, θ = 0,5): вся сверка М§17 в допусках, деньги конца года —
    машинная разность; V0 слоёв не совпадают до 1e-9.

    Проба на прототипе ядра методики (22.10.2026): вне допуска 3 строки из 14 618 — RWA гарантий конца 2027 (M/downturn/mid
    и strict) и 2028 (strict): 603,46 против 609,66 (1,02 % при допуске 1 %). Рост урезан капиталом в обеих моделях во
    всех кварталах 2027 года (λ_min = 0); во втором квартале 2027 года норматив Н20.0 при λ = 0 у ядра на требовании, у
    контроля — на 1 б.п. ниже (профиль прибыли квартала годовой строки): ядро растит кредиты на 0,7 %, контроль — нет;
    драйвер гарантий — кредиты юрлиц. Тот же класс, что книги угла (Р6-9; сторож —
    test_p5_keyed_book_rows_off_are_the_growth_cut_class); без ключа то же место даёт 0,32 %, при θ = 1 — 0,995 %. Деньги,
    RWA первых двух кварталов (до 2e-6) — одни у обеих моделей.

    ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 8, Р8-9; ops/expected_counts.json → known_failures): на ядре p3 @ 48f3ca2 (книга
    круга 7) — те же 3 строки RWA гарантий M/downturn 2027–2028, 610,91 против 604,63 (1,03 %) — класс урезанного роста
    Р6-9; сторож — test_p5_keyed_book_rows_off_are_the_growth_cut_class."""
    book, facts = repo
    run, ctl, rows = reconcile_rows(keyed(book), facts)
    cash = [r for r in rows if r.get("group") == "cash"]
    assert cash and max(abs(r["diff_rel"] or 0.0) for r in cash) <= 1e-12
    _fail(run, ctl, rows)
    assert not tcm.exact_match(run, ctl)


@pytest.mark.ci_only
@pytest.mark.parametrize("case", list(AXIS_CASES), ids=list(AXIS_CASES))
def test_p5_control_matches_core_at_the_ends(repo, case):
    """Книга с ключом и подменой одного поля (концы осей доли и θ, share: anchor, шаг, глиссада к 2029Q4): вся сверка
    М§17 в допусках; share: anchor — точка ядра и контроля те же, что без полей (бит в бит).

    [theta1] — ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 8, Р8-9): 3 строки RWA гарантий M/downturn 2027–2028, класс урезанного
    роста Р6-9 (сторож класса — test_p5_keyed_book_rows_off_are_the_growth_cut_class[theta1])."""
    book, facts = repo
    b = keyed(book, **AXIS_CASES[case])
    run, ctl, rows = reconcile_rows(b, facts)
    _fail(run, ctl, rows)
    if case == "share_anchor":
        assert ctl["point"] == cm.c_control_run(book, facts)["point"]
        assert run.point == core_run(book).point


@pytest.mark.ci_only
@pytest.mark.parametrize("case", list(CUT_CLASS_CASES), ids=list(CUT_CLASS_CASES))
def test_p5_keyed_book_rows_off_are_the_growth_cut_class(repo, case):
    """Строки сверки книги с ключом в центре, с шагом (share_from — первый прогнозный квартал) и при θ = 1 (известный
    красный Р8-9 test_p5_control_matches_core_at_the_ends[theta1]), вышедшие из допуска, —
    только класс Р6-9 (годовая форма контроля в клетках урезанного роста; tests/test_control_pass4.growth_cut_class): рост
    урезан капиталом в году строки у обеих моделей, фактический рост и доля урезанного роста клетки — в допусках, строка
    идёт за путём кредитов."""
    book, facts = repo
    run, ctl, rows = reconcile_rows(keyed(book, **CUT_CLASS_CASES[case]), facts)
    stray = tp4.growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
