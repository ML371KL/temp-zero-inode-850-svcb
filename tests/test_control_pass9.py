# -*- coding: utf-8 -*-
"""Контрольная модель: ключи девятого прохода ядра Совкомбанка (core-pass9) своим счётом.

Ключи (решения ведущего № 11; методика — spec.yaml прохода 9, пример — tests/fixtures/core_pass9/example.json, копия
примера методики; фрагмент книги — tests/fixtures/core_pass9/book_keys_pass9.yaml, копия фрагмента методики; доли,
funds_scope и центр К3 фрагмента тест подставляет в книгу репозитория, пока она ключей не несёт; книгу с ключами тест
судит её же значениями):

* Р11-1 (`nii.books.<b>.phi_share`) — доля сжатия ставки книги к опоре между мирами: цель ставки −share (ref_W − ref_H)
  на обеих сторонах баланса (путь, стационар решателя, эффективный LT-спред, кредитная маржа, цель К4); наклон между
  мирами 1 − φ_A [Φ_A] − share у актива, β + φ_L dX/dref − share у пассива; в мире H слагаемое — ноль.
* Р11-2 (`volumes.funds_scope`: all | clients) — «средства клиентов» балансовой механики без ведомых книг К6: база
  структурного опта К3, якорь доли опта, слово funds баз строк и драйвера денег; строка баланса — все книги.
* Р11-3 (`pnl.nci_real`) — неконтролирующие в реальных рублях: NCI_q = nci_real / 4 × I_W,q, ni_sh = ni − NCI; терминал
  ni_T+1 − NCI_L (1 + g), блок К-Т с частью real_rubles — m_L = (misc + nc)(1 − τ) − NCI_L, налог блока (1 − τ).

Без ключей контрольная модель считает бит в бит прежние числа — это держит сводка (tests/independent_model.py на книге
репозитория: текст и JSON) и тест «ключ нейтрален» ниже. Сверка с ядром (метка ci_only) требует ядра с проходом 9 — нет
ядра, его функции или ключа в схеме ядра — провал, не пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import functools
import json
import math
import random
from fractions import Fraction as F

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

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass9"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass9.yaml"
SHARE = cm.PHI_SHARE
SCOPE = "volumes.funds_scope"
NCI = "pnl.nci_real"
K3 = "volumes.wholesale_structural_to_funds"
DRIVERS = "volumes.liability_drivers"
NCI_VARIANT = "nci_real_rubles"                          # вариант фрагмента: НДУ в рублях (Р11-3)
F4_HIGH, F4_OVER = 0.1477, 0.1478                        # флаг 4 методики: верх оси К3 — вниз до 4 знаков; 0,1478 — отказ

rel, numbers = tp2.rel, tp2.numbers


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def frac(node) -> F:
    """Число примера [числитель, знаменатель, float] → точная дробь."""
    return F(int(node[0]), int(node[1]))


def put(book: dict, dotted: str, value) -> dict:
    return tp2.put(book, dotted, value)


@functools.lru_cache(maxsize=None)
def _frag() -> dict:
    return yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8"))


def frag_shares() -> dict:
    return {b: float(v[SHARE]) for b, v in _frag()["nii"]["books"].items()}


def frag_nci():
    var = next(v for v in _frag()["valuation"]["reference_variants_new"] if v["id"] == NCI_VARIANT)
    return copy.deepcopy(var["overrides"][NCI])


def own_keys(book: dict) -> bool:
    """Книга репозитория уже несёт ключи прохода 9 (поток книги поставил доли и funds_scope)."""
    return (any(SHARE in sp for sp in book["nii"]["books"].values())
            or "funds_scope" in (book.get("volumes") or {}))


def plain(book: dict) -> dict:
    """Книга без ключей прохода 9 (поток книги может их уже нести): без долей сжатия, funds_scope и nci_real."""
    out = copy.deepcopy(book)
    for sp in out["nii"]["books"].values():
        sp.pop(SHARE, None)
    out["volumes"].pop("funds_scope", None)
    (out.get("pnl") or {}).pop("nci_real", None)
    return out


def keyed(book: dict, **paths) -> dict:
    """Книга с ключами Р11-1 и Р11-2: если книга репозитория их не несёт — доли, funds_scope и центр К3 фрагмента
    методики; подмены точечных путей paths (точки через «__»)."""
    if own_keys(book):
        out = copy.deepcopy(book)
    else:
        out = plain(book)
        for b, v in frag_shares().items():
            out["nii"]["books"][b][SHARE] = v
        out["volumes"]["funds_scope"] = _frag()["volumes"]["funds_scope"]
        out["volumes"]["wholesale_structural_to_funds"] = _frag()["volumes"]["wholesale_structural_to_funds"]
    for dotted, v in paths.items():
        out = put(out, dotted.replace("__", "."), v)
    return out


def with_nci(book: dict) -> dict:
    return put(book, NCI, frag_nci())


def tag(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def driven_book(book: dict) -> str:
    books = list(book["volumes"].get("liability_drivers") or {})
    assert len(books) == 1, books
    return books[0]


def anchor_tr(book: dict, facts: dict) -> tuple[dict, dict, dict]:
    """Передача книги без прогона клеток: (книга с выведенными ключами, якорь, решение передачи)."""
    A = cm.c_anchor_state(book, facts)
    B, _ = cm.c_resolve_anchor_keys(book, A)
    return B, A, cm.c_transmission_ctl(B, A)


@pytest.fixture(scope="module")
def repo():
    book, facts = tcm._inputs()
    return book, facts


@pytest.fixture(scope="module")
def keyed_run(repo):
    """Прогон книги с ключами Р11-1 и Р11-2 (доли пяти книг, средства клиентов без К6, центр К3 на клиентах)."""
    book, facts = repo
    return cm.c_control_run(keyed(book), facts)


# ============================================================================ пример (формула и правило)


@pytest.mark.tact
def test_p9_example_by_own_code():
    """Пример прохода 9 (example.json) своим счётом в точных дробях: (А) ставка «Халвы» в мирах N, H, M — опора + спред −
    c_share_term(доля, опора мира, опора H), наклон 1 − доля, в мире H — опора + спред; пассив — β − доля; Φ_A формой
    отклонения — ω, среднее сжатие, доли книг (Σ ω share = 0), доли фрагмента книги — те же до 4 знаков; пара средств ФЛ
    — доля у каждой книги пары при весах c*, 1 − c*. (Б) якорь доли опта на всех средствах и на клиентах, база опта и
    добор. (В) НДУ квартала и ni_sh; ni_T+1 функцией c_ni_t1 (обе формы — 1e-15); блок К-Т c_terminal_fixed с частью
    real_rubles: m_L = misc (1 − τ) − NCI_L, вклад НДУ в X_B — −NCI_L (1 + π) / (k − π) (w = 1), при λ_F = 1 — вклад
    −NCI_L (1 + g) / (k − g) (1e-12)."""
    ex = example()
    a = ex["A_phi_share"]
    ref = {"N": F(8, 100), "H": F(105, 1000), "M": F(17, 100)}
    s_cards, share = F(1729, 10000), F(658, 1000)
    y = {w: ref[w] + s_cards - cm.c_share_term(share, ref[w], ref["H"]) for w in ref}
    for w in ref:
        assert y[w] == frac(a["cards_rate"][w]), w
    assert y["H"] == ref["H"] + s_cards and cm.c_share_term(share, ref["H"], ref["H"]) == 0
    slope = (y["M"] - y["N"]) / (ref["M"] - ref["N"])
    assert slope == frac(a["cards_slope"]) == 1 - share
    beta, s_l, share_l = F(969, 1000), F(-1097, 100000), F(1, 10)
    c = {w: beta * ref[w] + s_l - cm.c_share_term(share_l, ref[w], ref["H"]) for w in ref}
    for w in ref:
        assert c[w] == frac(a["liab_rate"][w]), w
    assert (c["M"] - c["N"]) / (ref["M"] - ref["N"]) == frac(a["liab_slope"]) == beta - share_l
    w_cl, w_corp = F(6420, 100000), F(43680, 100000)
    om = {"cash_loans": w_cl / (w_cl + w_corp), "corp_loans": w_corp / (w_cl + w_corp)}
    a_hist = {"cash_loans": F(4486, 10000), "corp_loans": F(8468, 10000)}
    mean = sum(om[b] * (1 - a_hist[b]) for b in om)
    dev = {b: (1 - a_hist[b]) - mean for b in om}
    assert mean == frac(a["phi_a_mean_compression"]) and sum(om[b] * dev[b] for b in om) == 0
    shares = frag_shares()
    for b in om:
        assert om[b] == frac(a["phi_a_omega"][b]) and dev[b] == frac(a["phi_a_share"][b]), b
        assert round(float(dev[b]), 4) == shares[b], b                      # запись фрагмента — 4 знака
    l_r, c_star, sh_rc, sh_rt = F(3, 10), F(1, 4), F(0), F(5, 100)
    cost_rc = {w: F(216, 1000) * ref[w] + F(3093, 100000) - cm.c_share_term(sh_rc, ref[w], ref["H"]) for w in ref}
    cost_rt = {w: beta * ref[w] + s_l - cm.c_share_term(sh_rt, ref[w], ref["H"]) for w in ref}
    pair = {w: l_r * (c_star * cost_rc[w] + (1 - c_star) * cost_rt[w]) for w in ref}
    for w in ref:
        assert pair[w] == frac(a["retail_pair_cost"][w]), w
    noshare = l_r * (c_star * cost_rc["M"] + (1 - c_star) * (beta * ref["M"] + s_l))
    assert pair["M"] - noshare == frac(a["retail_pair_cost_M_minus_noshare"])
    # (Б) Р11-2: якорь доли опта и база опта
    b_ = ex["B_funds_scope"]
    wh, clients, k6 = F(478227, 1000), F(3236582, 1000), F(171110, 1000)
    assert wh / (clients + k6) == frac(b_["anchor_share_all"]) and wh / clients == frac(b_["anchor_share_clients"])
    s = F(969, 10000)
    base_cl = s * (F(2000) + F(1300))
    extra = max(F(0), F(900) - F(850))
    assert s * (F(2000) + F(1300) + F(180)) == frac(b_["wh_base_all"]) and base_cl == frac(b_["wh_base_clients"])
    assert base_cl + extra == frac(b_["wholesale_clients"]) and extra == frac(b_["extra"])
    # (В) Р11-3: НДУ квартала, ni_sh, терминал обеих форм
    cc = ex["C_nci_real"]
    nci_q = F(482, 100) / cm.QY * F(23, 20)
    assert nci_q == frac(cc["nci_q"]) and F(30) - nci_q == frac(cc["ni_sh"])
    tau, g, k, pi = 0.23, 0.07, 0.14, 0.04
    pbt_l, y_x, nci_l, misc_l = 120.0, 0.0, 4.82 * 1.5, 15.0
    assert rel(cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0, nci_l), float(frac(cc["ni_t1"]))) <= 1e-15
    assert cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0655) == (pbt_l * (1.0 + g) - y_x) * (1.0 - tau) * (1.0 - 0.0655)
    d_as_t = (cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0, nci_l) - cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0)) / (k - g)
    assert rel(d_as_t, float(frac(cc["nci_tv_as_t"]))) <= 1e-12             # λ_F = 1: НДУ растут с g
    blk = dict(lam=0.0, parts=cm.FIXED_PARTS, x_t=20.0, binding=cm.BINDING_N20, bv_q=500.0, k=k, g=g, fade=1.0,
               kappa=0.12, r_f=100.0, f_a=90.0, at1=10.0, t2=5.0, nci_amt=3.0, dp_fix=0.0, y_m=0.1, cpn=1.0, tau=tau,
               tau_stat=0.25, nci=0.0, misc_l=misc_l, pi=pi)
    ci_with = cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0, nci_l) - 1.0 * (1.0 - 0.25)
    ci_without = cm.c_ni_t1(pbt_l, g, y_x, tau, 0.0) - 1.0 * (1.0 - 0.25)
    with_ = cm.c_terminal_fixed(**blk, ci_t1=ci_with, nci_l=nci_l)
    without = cm.c_terminal_fixed(**blk, ci_t1=ci_without)
    assert rel(with_["m_l"], float(frac(cc["m_l"]))) <= 1e-15 and with_["nci_l"] == nci_l
    assert rel(with_["m_l"] * (1.0 + pi) / (k - pi), float(frac(cc["x_flow"]))) <= 1e-12
    assert rel(with_["ci_business"], without["ci_business"]) <= 1e-14        # w = 1: НДУ уходят из растущей части
    assert rel(with_["x_b"] - without["x_b"], float(frac(cc["nci_tv_kt"]))) <= 1e-12
    assert with_["tv_ddm"] - with_["tv_ri"] == pytest.approx(blk["bv_q"], rel=1e-14)
    # без части real_rubles НДУ остаются в CI_T+1 и растут с g (как misc этого варианта)
    no_real = dict(blk, parts=tuple(p for p in cm.FIXED_PARTS if p != cm.PART_REAL))
    a_ = cm.c_terminal_fixed(**no_real, ci_t1=ci_with, nci_l=nci_l)
    b2 = cm.c_terminal_fixed(**no_real, ci_t1=ci_without)
    assert a_["m_l"] == 0.0 and rel(a_["x_b"] - b2["x_b"], d_as_t) <= 1e-12


# ============================================================================ чтение ключей и отказы (контекст)


@pytest.mark.tact
def test_p9_keys_are_read_and_refused(repo):
    """Доля сжатия: не число (null, логическое, строка, список), |доля| ≥ 1, NaN — отказ; 0 — ключа нет (книги нет в
    словаре). funds_scope: null и значение не из перечня — отказ; all и clients без К6 — пусто (ключ неактивного режима);
    clients — ведомая книга К6. nci_real: null, не траектория, траектория без значений и с не-числом — отказ. Якорь доли
    опта при clients — опт / средства клиентов без К6 (пример (Б), 1e-12), без ключа — на всех средствах; центр К3 0,1477
    читается, 0,1478 — отказ (флаг 4: выше доли якоря на клиентах). При nci_real доля pnl.nci_share не читается: книга без
    неё считается, доля 0,5 вместо книжной — те же числа клетки (бит в бит)."""
    book, facts = repo
    base = plain(book)
    for bad in (None, True, "0.5", [0.1], 1.0, -1.0, 1.5, float("nan")):
        with pytest.raises(cm.ControlInputError, match=SHARE):
            cm.c_phi_shares(put(base, f"nii.books.cards.{SHARE}", bad))
    assert cm.c_phi_shares(put(base, f"nii.books.cards.{SHARE}", 0)) == {}
    assert cm.c_phi_shares(put(base, f"nii.books.cards.{SHARE}", 0.0)) == {}
    # доли книги с ключами: у книги, которая несёт ключи прохода 9 сама (`own_keys`, итоговая книга круга 12 — шесть книг,
    # с долей опта 0,2477 по Р11-1), — её доли (0 — книги нет в словаре), иначе — доли фрагмента методики
    want = ({b: float(sp[SHARE]) for b, sp in book["nii"]["books"].items() if float(sp.get(SHARE) or 0.0) != 0.0}
            if own_keys(book) else frag_shares())
    assert cm.c_phi_shares(base) == {} and want and cm.c_phi_shares(keyed(book)) == want
    for bad in (None, "Clients", 1, True, ["clients"]):
        with pytest.raises(cm.ControlInputError, match="funds_scope"):
            cm.c_funds_scope(put(base, SCOPE, bad))
    k6 = driven_book(base)
    assert cm.c_funds_scope(base) == [] and cm.c_funds_scope(put(base, SCOPE, "all")) == []
    assert cm.c_funds_scope(put(base, SCOPE, "clients")) == [k6]
    assert cm.c_funds_scope(put(put(base, SCOPE, "clients"), DRIVERS, {})) == []
    for bad in (None, "4.82", {}, {"LT": None}, {"LT": "x"}, True, {"2027Q5": 1.0}):
        with pytest.raises(cm.ControlInputError, match="nci_real"):
            cm.c_nci_real(put(base, NCI, bad))
    assert cm.c_nci_real(base) is None and cm.c_nci_real(with_nci(base)) == frag_nci()
    ex = example()["B_funds_scope"]
    A = cm.c_anchor_state(keyed(book), facts)
    B, derived = cm.c_resolve_anchor_keys(keyed(book), A)
    e0 = A["E0"]
    clients = e0[cm.RETAIL_CURRENT] + e0[cm.RETAIL_TERM] + sum(e0[b] for b in cm.c_client_funds(B["nii"]["books"])
                                                              if b != k6)
    assert rel(derived["volumes.wholesale_to_funds"], e0[cm.WHOLESALE] / clients) <= 1e-15
    assert rel(derived["volumes.wholesale_to_funds"], float(frac(ex["anchor_share_clients"]))) <= 1e-12
    _, d0 = cm.c_resolve_anchor_keys(base, cm.c_anchor_state(base, facts))
    assert rel(d0["volumes.wholesale_to_funds"], float(frac(ex["anchor_share_all"]))) <= 1e-12
    assert cm.c_wholesale_shares(put(B, K3, F4_HIGH))[0] == F4_HIGH
    with pytest.raises(cm.ControlInputError, match="wholesale_structural_to_funds"):
        cm.c_wholesale_shares(put(B, K3, F4_OVER))
    ctx = cm.c_control_context(with_nci(keyed(book)), facts)
    assert ctx["k6_out"] == [k6] and ctx["fund_biz"] == [b for b in ctx["biz"] if b != k6]
    assert ctx["nci_real"] == frag_nci()
    cell = ("H", "norm", "mid")
    nb = with_nci(keyed(book))
    b_none = copy.deepcopy(nb)
    b_none["pnl"].pop("nci_share")
    _, x = tp2.cells_of(b_none, facts, keys=(cell,))
    _, y = tp2.cells_of(put(nb, "pnl.nci_share", 0.5), facts, keys=(cell,))
    assert numbers(x[cell]) == numbers(y[cell])


@pytest.mark.tact
def test_p9_stationary_with_shares_at_every_book(repo):
    """Синтетические доли у всех 13 книг (пара средств ФЛ, опт, книга страховых, балансирующие): Nss «по книгам» = Nss
    решателя (1e-15), T_real = T* (1e-12: решатель замыкает φ при любых долях); наклон книги между мирами M и N — 1 − φ_A
    [Φ_A] − share у актива, β + φ_L dX/dref − share у пассива (1e-12); эффективный LT-спред = ставка книги − опора;
    кредитная маржа — с долями бумаг и ликвидности. Без мира уровня ставки мира H у двух наборов долей — бит в бит (σ0 тот
    же, слагаемое доли в H — ноль), с миром уровня N σ0 зависит от долей (законная связь transmission)."""
    book, facts = repo
    rng = random.Random(9)
    base = plain(book)
    books = base["nii"]["books"]
    sh1 = {b: round(rng.uniform(-0.3, 0.6), 4) for b in books}
    sh2 = {b: round(v / 2.0, 4) for b, v in sh1.items()}

    def with_shares(bk, shares):
        out = copy.deepcopy(bk)
        for b, v in shares.items():
            out["nii"]["books"][b][SHARE] = v
        return out

    B, A, tr = anchor_tr(with_shares(base, sh1), facts)
    assert tr["phi_shares"] == sh1
    t_star = cm.c_bnum(B, "nii.transmission.target")
    assert abs(tr["t_real"] - t_star) <= 1e-12
    ids = list(tr["nss"])
    for w in ids:
        assert abs(tr["nss_books"][w] - tr["nss"][w]) <= 1e-15, w
    ref_w = cm.c_bget(B, "nii.transmission.reference_world")

    def lt(w, ref):
        return cm.c_world_quarter(B, w, cm.c_ref_field(ref), *cm.c_per_parse(cm.c_bget(B, "meta.last_period")))

    om = tr["phi_weights"]
    dx = (sum(om[b] * (lt("M", books[b]["ref"]) - lt("N", books[b]["ref"])) for b in om))
    for b, sp in books.items():
        ref = cm.c_share_ref(b, sp)
        d_ref = lt("M", ref) - lt("N", ref)
        if sp["side"] == cm.LOANS_SIDE:
            want = 1.0 - (tr["phi_assets"] if sp.get("phi") else 0.0) - sh1[b]
        else:
            want = float(sp["beta"]) + (tr["phi_liab"] * dx / d_ref if sp.get("phi") else 0.0) - sh1[b]
        assert abs(tr["book_slopes"][b] - want) <= 1e-12, b
        if sp.get("sector"):
            for w in ids:
                assert abs(tr["book_rates_lt"][b][w] - lt(w, sp["ref"]) - tr["lt_spread"][b][w]) <= 1e-15, (b, w)
                assert abs(tr["share_lt"][b][w] + sh1[b] * (lt(w, sp["ref"]) - lt(ref_w, sp["ref"]))) <= 1e-15
    # кредитная маржа: доходность кредитов − смесь балансирующих (обе — ставки книг стационара с долями) − риск; риск (CoR
    # режима norm с κ-добавкой мира) от долей не зависит — тот же, что у книги без долей
    sec = cm.c_bnum(B, "volumes.securities_share_of_liquid")
    credit = [b for b, sp in books.items() if sp.get("sector")]
    e0 = A["E0"]
    yl, ql = cm.c_per_parse(cm.c_bget(B, "meta.last_period"))
    _, _, tr0 = anchor_tr(base, facts)

    def s_lt(b):
        return cm.c_traj_at(books[b]["spread"], yl, ql)

    for w in ids:
        yld = sum(e0[b] * tr["book_rates_lt"][b][w] for b in credit) / sum(e0[b] for b in credit)
        bal = sec * tr["book_rates_lt"][cm.SECURITIES][w] + (1.0 - sec) * tr["book_rates_lt"][cm.LIQUIDITY][w]
        yld0 = sum(e0[b] * (lt(w, books[b]["ref"]) + tr0["lt_spread"][b][w]) for b in credit) / sum(e0[b] for b in credit)
        bal0 = (sec * (lt(w, books[cm.SECURITIES]["ref"]) + s_lt(cm.SECURITIES))
                + (1.0 - sec) * (lt(w, books[cm.LIQUIDITY]["ref"]) + s_lt(cm.LIQUIDITY)))
        assert abs((yld - bal - tr["loan_margin"][w]) - (yld0 - bal0 - tr0["loan_margin"][w])) <= 1e-12, w
    # мир H: без мира уровня — бит в бит у двух наборов долей; с миром уровня N — σ0 от долей
    flat = copy.deepcopy(base)
    flat["nii"]["transmission"].pop("level_world", None)
    _, _, t1 = anchor_tr(with_shares(flat, sh1), facts)
    _, _, t2 = anchor_tr(with_shares(flat, sh2), facts)
    _, _, t0 = anchor_tr(flat, facts)
    assert t1["sigma0"] == t2["sigma0"] == t0["sigma0"] and t1["sigma0_liab"] == t2["sigma0_liab"]
    for b in books:
        assert t1["book_rates_lt"][b][ref_w] == t2["book_rates_lt"][b][ref_w], b
    if cm.c_bopt(base, "nii.transmission.level_world") not in (None, ref_w):
        _, _, l1 = anchor_tr(with_shares(base, sh1), facts)
        _, _, l0 = anchor_tr(base, facts)
        assert l1["sigma0"] != l0["sigma0"]


# ============================================================================ клетки (вне такта)


def test_p9_neutral_cases_are_bit_for_bit(repo):
    """Бит в бит с прогоном без ключей: доли 0 у всех 13 книг и funds_scope: all (точка, низ, верх, передача, 36 клеток);
    clients без К6 (liability_drivers пуст) — как та же книга без ключа (три клетки расчётов)."""
    book, facts = repo
    base = plain(book)
    zeros = put(copy.deepcopy(base), SCOPE, "all")
    for sp in zeros["nii"]["books"].values():
        sp[SHARE] = 0.0
    a, b = cm.c_control_run(base, facts), cm.c_control_run(zeros, facts)
    assert (a["point"], a["low"], a["high"]) == (b["point"], b["low"], b["high"])
    assert a["transmission"] == b["transmission"]
    for ca, cb in zip(a["cells"], b["cells"]):
        assert tag(ca) == tag(cb) and numbers(cb) == numbers(ca), tag(ca)
    off = put(base, DRIVERS, {})
    _, x = tp2.cells_of(off, facts)
    _, y = tp2.cells_of(put(off, SCOPE, "clients"), facts)
    for key in tp2.CELLS:
        assert numbers(y[key]) == numbers(x[key]), key


def test_p9_book_rates_in_cells(keyed_run):
    """В каждой клетке, периоде и книге цель ставки периода (К4: средняя цель кварталов) — своим счётом по кварталам:
    опора мира + спред − φ_A [Φ_A] (опора − опора H) − доля (опора − опора H) у актива; β опора + спред + φ_L X_W,q [Φ_L] −
    доля (опора − опора H) у пассива (1e-14). Последний год у книг с опорой «ключевая» без φ у пассива — ставка книги в
    стационаре мира (ключевая миров в 2036 году плоская; 1e-14)."""
    res = keyed_run
    ctx = res["ctx"]
    B, tr = ctx["B"], ctx["tr"]
    books = B["nii"]["books"]
    ref_w = cm.c_bget(B, "nii.transmission.reference_world")
    shr = tr["phi_shares"]
    om = tr["phi_weights"]
    seen = 0
    for c in res["cells"]:
        w = c["world"]
        for i, p in enumerate(ctx["periods"]):
            row = c["rows"][i]
            for b, sp in books.items():
                field = cm.c_ref_field(sp["ref"])
                tg = []
                for q in p["quarters"]:
                    rv = cm.c_world_quarter(B, w, field, p["year"], q)
                    rh = cm.c_world_quarter(B, ref_w, field, p["year"], q)
                    s = cm.c_spread_at(ctx, b, p["year"], q) - shr.get(b, 0.0) * (rv - rh)
                    if sp["side"] == cm.LOANS_SIDE:
                        tg.append(rv + s - (tr["phi_assets"] * (rv - rh) if sp.get("phi") else 0.0))
                    else:
                        x = sum(o * (cm.c_world_quarter(B, w, cm.c_ref_field(books[a]["ref"]), p["year"], q)
                                     - cm.c_world_quarter(B, ref_w, cm.c_ref_field(books[a]["ref"]), p["year"], q))
                                for a, o in om.items())
                        tg.append(float(sp["beta"]) * rv + s + (tr["phi_liab"] * x if sp.get("phi") else 0.0))
                want = sum(tg) / len(tg)
                got = row["stationary"]["targets"][b]
                assert abs(got - want) <= 1e-14, (tag(c), p["year"], b, got, want)
                seen += 1
        last = c["rows"][-1]["stationary"]["targets"]
        for b, sp in books.items():
            if sp["ref"] == "key" and not (sp["side"] != cm.LOANS_SIDE and sp.get("phi")):
                assert abs(last[b] - tr["book_rates_lt"][b][w]) <= 1e-14, (tag(c), b)
    assert seen == len(res["cells"]) * len(ctx["periods"]) * len(books)


def test_p9_wholesale_on_clients_and_balance(keyed_run):
    """Средства клиентов без книги К6 в каждой клетке и периоде: опт − добор = s × средства клиентов конца года (1e-12),
    средства клиентов = строка баланса «средства» − книга К6 (1e-12); при минимуме ликвидности, не связанном хотя бы на
    одном конце периода, средний опт — s × средняя средств клиентов + полусумма добора концов (1e-12; на якоре добор — опт
    якоря сверх s × средства клиентов якоря); тождество баланса (1e-9); квартальный проход
    кончает год на тех же RWA, что годовая строка (1e-9: база опта одна в обоих путях). Добор на якоре — опт якоря − s ×
    средства клиентов якоря > 0 (центр К3 ниже доли якоря)."""
    res = keyed_run
    ctx = res["ctx"]
    k6 = driven_book(ctx["B"])
    s = ctx["wtf"]
    e0 = ctx["A"]["E0"]
    cl0 = e0[cm.RETAIL_CURRENT] + e0[cm.RETAIL_TERM] + sum(e0[b] for b in ctx["fund_biz"])
    assert ctx["k6_out"] == [k6] and e0[cm.WHOLESALE] - s * cl0 > 0.0
    assert rel(ctx["wtf_anchor"], e0[cm.WHOLESALE] / cl0) <= 1e-15
    for c in res["cells"]:
        extra_prev = e0[cm.WHOLESALE] - s * cl0
        for i, r in enumerate(c["rows"]):
            assert rel(r["clients"], r["funds"] - r["driven_end"][k6]) <= 1e-12, (tag(c), i)
            assert rel(r["wholesale"] - r["wholesale_extra"], s * r["clients"]) <= 1e-12, (tag(c), i)
            if not (r["wholesale_extra"] > 0.0 and extra_prev > 0.0):
                # минимум ликвидности не связан хотя бы на одном конце: средний опт — s × средняя средств клиентов +
                # полусумма добора концов (добор начала первого периода — опт якоря сверх s × средства клиентов якоря)
                want = s * r["clients_avg"] + (extra_prev + r["wholesale_extra"]) / 2.0
                assert rel(r["wholesale_avg"], want) <= 1e-12, (tag(c), i)
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"], (tag(c), i)
            assert rel(r["quarters"][-1]["rwa"], r["rwa"]) <= 1e-9, (tag(c), i)
            extra_prev = r["wholesale_extra"]


def test_p9_nci_in_cells(repo):
    """НДУ в реальных рублях (вариант фрагмента, Р11-3) в трёх клетках расчётов: NCI_q = nci_real / 4 × индекс цен мира
    квартала (1e-15), ni − ni_sh = Σ NCI_q (1e-12), прибыль акционеров кварталов в сумме — ni_sh (1e-9); терминал: NCI_L
    — НДУ года L, ni_T+1 = c_ni_t1(PBT^T_L, g, Y_X, τ, 0, NCI_L) (1e-12), блок К-Т: m_L = (misc + nc)(1 − τ) − NCI_L
    (1e-12), TV_DDM − TV_RI = BV_Q (1e-12); при λ_F = 1 блока нет, НДУ растут с g той же формой c_ni_t1."""
    book, facts = repo
    nb = with_nci(keyed(book))
    traj = frag_nci()
    for lam_f in (None, 1.0):
        b2 = nb if lam_f is None else put(nb, "valuation.terminal.fixed_growth_share", lam_f)
        ctx, cells = tp2.cells_of(b2, facts)
        for key, c in cells.items():
            for p, r in zip(ctx["periods"], c["rows"]):
                yearly = cm.c_traj_mean(traj, p["year"], range(1, cm.QY + 1))
                for j, q in enumerate(p["quarters"]):
                    assert rel(r["nci_q"][j], yearly / cm.QY * r["idx_q"][j]) <= 1e-15, (key, p["year"], q)
                assert rel(r["ni"] - r["ni_sh"], sum(r["nci_q"])) <= 1e-12 and r["nci"] == sum(r["nci_q"])
                assert rel(sum(r["ni_q"].values()), r["ni_sh"]) <= 1e-9, (key, p["year"])
            last = c["rows"][-1]
            assert c["nci_l"] == last["nci"]
            pbt_t = last["pbt"] + (c["terminal_stationary"]["d_nii_l"] if "terminal_stationary" in c else 0.0)
            pbt_t += c["terminal_year"]["adj"] if "terminal_year" in c else 0.0
            ni_t1 = cm.c_ni_t1(pbt_t, c["g_t"], c["y_x"], last["tau_eff"], 0.0, c["nci_l"])
            assert rel(c["ni_t1"], ni_t1) <= 1e-12, key
            assert rel(c["tv_ddm"] - c["tv_ri"], last["bv"]) <= 1e-12, key
            if lam_f is None:
                t = c["terminal_fixed"]
                assert rel(t["m_l"], (last["misc"] + last["noncore"]) * (1.0 - last["tau_eff"]) - c["nci_l"]) <= 1e-12
            else:
                assert "terminal_fixed" not in c


# ============================================================================ сверка с ядром (ci_only)


def _cases(book: dict) -> dict:
    """Книги сверки с ключами прохода 9: центр (доли пяти книг, средства клиентов без К6, центр К3), только «Халва»,
    только К3 на клиентах, центр с НДУ в рублях."""
    base = plain(book)
    centre = keyed(book)
    cards = put(base, f"nii.books.cards.{SHARE}", frag_shares()["cards"])
    k3 = put(put(base, SCOPE, "clients"), K3, _frag()["volumes"]["wholesale_structural_to_funds"])
    return {"centre": centre, "cards": cards, "k3": k3, "nci": with_nci(centre)}


CASES = ("centre", "cards", "k3", "nci")


@pytest.mark.ci_only
@pytest.mark.parametrize("case", CASES, ids=CASES)
def test_p9_control_rows_off_are_the_growth_cut_class(repo, case):
    """Сверка М§17 книг с ключами прохода 9 (центр, только «Халва», только К3 на клиентах, центр с НДУ в рублях): строки
    вне допуска — только класс Р6-9 (tests/test_control_pass4.growth_cut_class), V0 слоёв не совпадают до 1e-9; передача
    (σ0, φ, φ_A, φ_L, T_real, T(W), пары, эффективные LT-спреды с долями, кредитная маржа миров) — в допуске 1e-6."""
    book, facts = repo
    b = _cases(book)[case]
    ctl = cm.c_control_run(b, facts)
    run = tcm.core_run_of(copy.deepcopy(b))
    rows = tcm.compare_with_core(run, ctl)
    stray = tp4.growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
    assert not tcm.exact_match(run, ctl)
