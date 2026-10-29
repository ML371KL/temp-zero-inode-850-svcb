"""Проверки девятого прохода ядра Совкомбанка (core-pass9): доля сжатия книги между мирами (Р11-1, ключ
`nii.books.<книга>.phi_share`), опт и слово funds на средствах клиентов (Р11-2, ключ `volumes.funds_scope`) и неконтролирующие
в реальных рублях (Р11-3, ключ `pnl.nci_real`). Все три ключа необязательны; нет ключа (и 0 у долей, all, clients без
активного К6) — прежняя ветвь кода, бит в бит.

Р11-1: ставка актива ref_W + s − φ_A [Φ_A](ref_W − ref_H) − share (ref_W − ref_H), пассива β ref_W + s + φ_L [Φ_L] X_W −
share (ref_W − ref_H) — в шаге (y_q = y_(q−1) + ρ (y*_q − y_(q−1))), цели ставки К4, стационаре Nss (пара ФЛ — каждая
книга своей долей), LT-спреде гейта пола; в мире-опоре H слагаемое — ноль; решатель замыкает T* через φ (T_real = T*);
наклон книги между мирами — 1 − φ_A [Φ_A] − share (актив), β + φ_L dX/dref − share (пассив).
Р11-2: база структурного опта WHB_q = s × средства клиентов без книг К6; якорь wholesale_to_funds = WH_0 / средства клиентов;
слово funds баз строк — на тех же книгах; тождество баланса — все книги средств.
Р11-3: NCI_q = nci_real(Y) / 4 × I_W,q, ni_sh = ni − NCI_q, доля НДУ 0; терминал NI_T+1 − NCI_L (1 + g), блок К-Т (часть
real_rubles) m_L = (misc_L + nc_L)(1 − τ) − NCI_L.

Одни и те же проверки зовут тесты (`tests/test_core_p9.py`) и мутационный набор (`tests/mutations.py`). Каждая — тождество,
закрытая формула своим счётом (ставки, Nss, LT-спред, наклоны, база опта, якорь — из книги и фактов, не функциями ядра) или
число примера методики (`tests/fixtures/core_pass9/example.json` — копия выхода `example.py` агента методики, notes/core-pass9;
значения долей книги — `book_keys_pass9.yaml`).
"""

from __future__ import annotations

import copy
import functools
import json
import sys
from fractions import Fraction as Fr
from pathlib import Path
from typing import Any

from tests import support_core_p3 as P3
from tests import support_core_p4 as P4
from tests import support_core_p6 as P6
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "core_pass9"
EXAMPLE, BOOK_KEYS = FIXTURE / "example.json", FIXTURE / "book_keys_pass9.yaml"
SHEET_NII = ROOT / "data" / "assumptions" / "evidence" / "nii"
SHEET_PATH = ROOT / "data" / "assumptions" / "evidence" / "path"
refused = P3.refused
SHARE, SCOPE, NCI = "phi_share", "volumes.funds_scope", "pnl.nci_real"
DRIVERS, LEVEL = "volumes.liability_drivers", "nii.transmission.level_world"
EX_BASE_POINT = 16.11195416818156            # точка книги дерева (p3 @ 6fb58aa) — без ключей прохода 9
# синтетические доли у всех 13 книг (пара ФЛ, опт и книга страховых — тоже): проверки формы, не числа книги
SYNTH = {"auto": 0.03, "mortgage": 0.05, "cash_loans": 0.30, "cards": 0.60, "corp_loans": -0.05, "securities": 0.02,
         "liquidity": 0.14, "retail_current": 0.07, "retail_term": 0.05, "corp_term": 0.04, "corp_current": 0.10,
         "wholesale": 0.20, "insurance_liab": 0.10}
NCI_LT = 4.82                                # вариант nci_real_rubles книги прохода (млрд ₽ в год в ценах якоря)
TOL = 1e-12


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def book_keys() -> dict[str, Any]:
    import yaml
    return yaml.safe_load(BOOK_KEYS.read_text(encoding="utf-8"))


def frag_shares() -> dict[str, float]:
    """Доли сжатия книг из фрагмента книги прохода (тип Б и Φ_A)."""
    return {b: float(v[SHARE]) for b, v in book_keys()["nii"]["books"].items()}


@functools.lru_cache(maxsize=None)
def _bank_data() -> dict[str, Any]:
    """Исходный словарь книги дерева без ключей прохода 9 (если поток книги их уже поставил)."""
    _, data = P4._real_book()
    out = copy.deepcopy(data)
    for spec in out["nii"]["books"].values():
        spec.pop(SHARE, None)
    (out.get("volumes") or {}).pop("funds_scope", None)
    (out.get("pnl") or {}).pop("nci_real", None)
    return out


@functools.lru_cache(maxsize=None)
def _bank_run(changes: tuple = ()) -> Any:
    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    from model.paths import set_path
    data = copy.deepcopy(_bank_data())
    for dotted, value in changes:
        if value == "__drop__":
            parent, _, leaf = dotted.rpartition(".")
            node = data
            for part in parent.split("."):
                node = node[part]
            node.pop(leaf, None)
            continue
        set_path(data, dotted, json.loads(value))
    facts = P4._real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts))


def bank(paths: dict[str, Any] | None = None, drop: tuple[str, ...] = (), **short: Any) -> Any:
    """Сетка книги дерева (`_bank_data`) с подменами: `paths` — {путь: значение}, `short` — `__` вместо точки; `drop` —
    пути, снятые с книги."""
    changes = {**(paths or {}), **{k.replace("__", "."): v for k, v in short.items()}}
    items = [(k, json.dumps(v)) for k, v in changes.items()] + [(k, "__drop__") for k in drop]
    return _bank_run(tuple(sorted(items)))


def shares(values: dict[str, float]) -> dict[str, float]:
    return {f"nii.books.{b}.{SHARE}": v for b, v in values.items()}


def _ex_point_tree() -> bool:
    return bank().point == EX_BASE_POINT


_same = P6._same


# ------------------------------------------------------------------ свой счёт стационара (не функциями ядра)


def _lt(book: Any, path: str) -> float:
    from model.paths import Trajectory
    from model.timeline import parse_period
    return Trajectory(book.get(path)).value(*parse_period(str(book.get("meta.last_period"))))


def own_stationary(run: Any) -> dict[str, Any]:
    """Ставки книг в стационаре каждого мира своим счётом (М§4.4 с долями Р11-1): опоры миров и спреды — значения
    траекторий книги в last_period; σ0_A, σ0_L, φ_A, φ_L — решения передачи прогона; X_W = Σ_Φ_A ω_b (ref_b,W − ref_b,H),
    ω — доли якоря книг Φ_A (факты). → {rates: {мир: {книга: ставка}}, ref, x, w (веса к ПА якоря)}."""
    ctx = run.ctx
    book, tr = ctx.book, ctx.transmission
    books = book.get("nii.books")
    facts = P4._real_facts()
    bal = {b: float(facts.file("balance")["books"][b]["v"]) for b in books}
    H = tr.reference_world
    ref = {w: {r: _lt(book, f"worlds.{w}.key_rate" if r == "key" else f"worlds.{w}.{r}")
               for r in ("key", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y")} for w in book.get("worlds.ids")}
    phi_a = [b for b in books if books[b]["side"] == "asset" and books[b].get("phi")]
    omega = {b: bal[b] / sum(bal[x] for x in phi_a) for b in phi_a}
    x = {w: sum(omega[b] * (ref[w][books[b]["ref"]] - ref[H][books[b]["ref"]]) for b in phi_a) for w in ref}
    rates: dict[str, dict[str, float]] = {}
    for w in ref:
        row = {}
        for b, spec in books.items():
            r, rh = ref[w][spec["ref"]], ref[H][spec["ref"]]
            s = _lt(book, f"nii.books.{b}.spread")
            sh = float(spec.get(SHARE, 0.0))
            if spec["side"] == "asset":
                s += tr.sigma0 if spec.get("lt_shift") else 0.0
                y = r + s - (tr.phi_assets * (r - rh) if spec.get("phi") else 0.0)
            else:
                s -= tr.sigma0_liab if spec.get("lt_shift") else 0.0
                y = float(spec["beta"]) * r + s + (tr.phi_liab * x[w] if spec.get("phi") else 0.0)
            row[b] = y - sh * (r - rh)
        rates[w] = row
    iea = sum(bal[b] for b in books if books[b]["side"] == "asset")
    return {"rates": rates, "ref": ref, "x": x, "w": {b: bal[b] / iea for b in books}, "H": H}


def own_nss(run: Any, own: dict[str, Any]) -> dict[str, float]:
    """Nss(W) «по книгам» своим счётом: Σ_актив w_b y_b − Σ_пассив вне пары w_b c_b − l_R (c* c_тек + (1 − c*) c_срок) −
    АСВ × l_R; c* = clip(c_ref − ψ (key_W − key_ref)) — ставки целей книг (с φ_A и φ_L; объём сжатия мира φ C_W от доли
    раскладки не зависит, поэтому сумма равна стационару решателя)."""
    book = run.ctx.book
    books = book.get("nii.books")
    rcs = book.get("nii.retail_current_share")
    lo, hi = (float(v) for v in rcs["bounds"])
    dia = float(book.get("nii.dia_rate"))
    rc, rt = "retail_current", "retail_term"
    w = own["w"]
    l_r = w[rc] + w[rt]
    out = {}
    for world, y in own["rates"].items():
        c = min(hi, max(lo, float(rcs["c_ref"]) - float(rcs["psi"]) * (own["ref"][world]["key"] - float(rcs["key_ref"]))))
        total = sum(w[b] * y[b] for b in books if books[b]["side"] == "asset")
        total -= sum(w[b] * y[b] for b in books if books[b]["side"] == "liability" and b not in (rc, rt))
        total -= l_r * (c * y[rc] + (1 - c) * y[rt]) + dia * l_r
        out[world] = total
    return out


# ------------------------------------------------------------------ без ключей и при нулях — бит в бит


def check_neutral_bank() -> None:
    """Книга дерева: доли 0 у всех 13 книг и funds_scope: all ≡ без ключей (точка, клетки, все ряды); funds_scope: clients
    без активного К6 ≡ без ключа (тот же выключенный К6); подготовка без ключей — пустые поля прохода 9. Точка книги дерева
    без ключей — число p3 @ 6fb58aa."""
    base = bank()
    p = base.ctx.prep
    assert p.phi_share == {} and p.funds_words is None and p.wh_corp is None and p.nci_q is None
    assert base.ctx.transmission.share_lt == {}
    zeros = bank({**shares({b: 0.0 for b in _bank_data()["nii"]["books"]}), SCOPE: "all"})
    _same(zeros, base)
    off = bank({DRIVERS: {}})
    _same(bank({DRIVERS: {}, SCOPE: "clients"}), off)


def check_neutral_fixture() -> None:
    """Фикстура `core_t` (Т-книга, без К6): доли 0 у всех книг, funds_scope all и clients (при checks.client_funds:
    clients — К6 нет, ключ неактивного режима) ≡ без ключей, бит в бит."""
    base = S.grid_of()
    names = list(S.book_of().get("nii.books"))
    zeros = {f"nii__books__{b}__phi_share": 0.0 for b in names}
    _same(S.grid_of(**zeros, volumes__funds_scope="all"), base)
    with_cf = S.grid_of(checks__client_funds="clients")
    _same(S.grid_of(checks__client_funds="clients", volumes__funds_scope="clients"), with_cf)


# ------------------------------------------------------------------ пример методики точными дробями


def _r(x: Fr) -> list:
    return [x.numerator, x.denominator, float(x)]


def check_example() -> None:
    """Пример методики (core9-spec, example.json) своим счётом точными дробями — и ядро на тех же входах: наклон «Халвы»
    1 − share, пассив β − share, Φ_A — Σ ω share = 0, пара ФЛ; якорь доли опта на книге дерева (с К6 и без) против
    дробей фактов; терминал с НДУ в рублях (NI_T+1, m_L блока К-Т, вклады в TV обеих форм) — функцией ядра."""
    ex = example()
    a = ex["A_phi_share"]
    ref = {"N": Fr(8, 100), "H": Fr(105, 1000), "M": Fr(17, 100)}
    s_c, sh = Fr(1729, 10000), Fr(658, 1000)
    y = {w: ref[w] + s_c - sh * (ref[w] - ref["H"]) for w in ref}
    assert {w: _r(v) for w, v in y.items()} == a["cards_rate"] and _r((y["M"] - y["N"]) / (ref["M"] - ref["N"])) == a["cards_slope"]
    beta, s_l, sh_l = Fr(969, 1000), Fr(-1097, 100000), Fr(1, 10)
    c = {w: beta * ref[w] + s_l - sh_l * (ref[w] - ref["H"]) for w in ref}
    assert {w: _r(v) for w, v in c.items()} == a["liab_rate"] and a["liab_slope"] == _r(beta - sh_l)
    w_cl, w_corp = Fr(6420, 100000), Fr(43680, 100000)
    om = {"cash_loans": w_cl / (w_cl + w_corp), "corp_loans": w_corp / (w_cl + w_corp)}
    aa = {"cash_loans": Fr(4486, 10000), "corp_loans": Fr(8468, 10000)}
    mean = sum(om[b] * (1 - aa[b]) for b in om)
    dev = {b: (1 - aa[b]) - mean for b in om}
    assert sum(om[b] * dev[b] for b in om) == 0 and {b: _r(v) for b, v in dev.items()} == a["phi_a_share"]
    assert _r(mean) == a["phi_a_mean_compression"]
    l_r, c_star = Fr(3, 10), Fr(1, 4)
    pair = {w: l_r * (c_star * (Fr(216, 1000) * ref[w] + Fr(3093, 100000))
                      + (1 - c_star) * (beta * ref[w] + s_l - Fr(5, 100) * (ref[w] - ref["H"]))) for w in ref}
    assert {w: _r(v) for w, v in pair.items()} == a["retail_pair_cost"]
    # ядро: наклон «Халвы» с долей книги — 1 − share (cards не в Φ_A); в мире H ставка без доли
    from model.nii import book_slopes
    run = bank(shares({"cards": 0.658}))
    slope = book_slopes(run.ctx.book, P4._real_facts(), run.ctx.transmission)
    assert abs(slope["cards"] - (1 - 0.658)) < TOL, slope["cards"]
    # Р11-2: якорь доли опта — дроби фактов (опт / средства клиентов; с К6 — прежняя доля)
    b = ex["B_funds_scope"]
    facts = P4._real_facts()
    books = facts.file("balance")["books"]
    wh = Fr(str(books["wholesale"]["v"]))
    clients = sum(Fr(str(books[x]["v"])) for x in ("retail_current", "retail_term", "corp_term", "corp_current"))
    k6 = Fr(str(books["insurance_liab"]["v"]))
    assert _r(wh / clients) == b["anchor_share_clients"] and _r(wh / (clients + k6)) == b["anchor_share_all"]
    assert abs(bank({SCOPE: "clients"}).ctx.book.get("volumes.wholesale_to_funds") - float(wh / clients)) < 1e-15
    assert abs(bank().ctx.book.get("volumes.wholesale_to_funds") - float(wh / (clients + k6))) < 1e-15
    s = Fr(969, 10000)
    assert _r(s * (Fr(2000) + Fr(1300))) == b["wh_base_clients"] and _r(s * (Fr(2000) + Fr(1300) + Fr(180))) == b["wh_base_all"]
    # Р11-3: терминал ядра на входах примера
    cc = ex["C_nci_real"]
    nci_l = Fr(482, 100) * Fr(3, 2)
    assert _r(Fr(482, 100) / 4 * Fr(23, 20)) == cc["nci_q"] and _r(Fr(30) - Fr(482, 100) / 4 * Fr(23, 20)) == cc["ni_sh"]
    plain, block = _terminal(0.0), _terminal(float(nci_l))
    assert abs(block["t1"].ni_t1 - cc["ni_t1"][2]) < 1e-9, (block["t1"].ni_t1, cc["ni_t1"])
    assert abs(block["kt"].fixed["m_l"] - cc["m_l"][2]) < 1e-12, block["kt"].fixed["m_l"]
    assert abs(plain["kt"].fixed["m_l"] - 15 * (1 - 0.23)) < 1e-12
    assert abs((block["kt"].tv_ri - plain["kt"].tv_ri) - cc["nci_tv_kt"][2]) < 1e-9
    assert abs((block["t1"].tv_ri - plain["t1"].tv_ri) - cc["nci_tv_as_t"][2]) < 1e-9
    for t in (*plain.values(), *block.values()):
        assert abs(t.tv_ddm - t.tv_ri - 1000.0) < 1e-9          # TV_DDM − TV_RI = BV_Q (избыток 0)


def _terminal(nci_l: float) -> dict[str, Any]:
    """Терминал ядра на входах примера: PBT_L 120, τ 0,23, g 0,07 (π 0,04), k 0,14, избыток 0 (множитель 0), BV_Q 1000;
    `t1` — без блока (λ_F = 1, НДУ растёт с g), `kt` — блок К-Т с одной частью real_rubles и λ_F = 0 («прочее» 15)."""
    from model.valuation import FixedInputs, terminal
    kw = dict(n20=0.12, req20=0.12, n11_star=0.10, req11=0.10, rwa=5000.0, bv_q=1000.0, pbt_last_year=120.0,
              y_balancing=0.1, c_wholesale=0.12, headroom=0.0, tau_eff=0.23, nci_share=0.0, coupon_annual=0.0,
              tau_stat=0.25, lt_inflation=0.04, real_growth=1.07 / 1.04 - 1, fade=1.0, multiple=0.0, k_t=0.14,
              nci_l=nci_l)
    fixed = FixedInputs(f_a=0.0, r_f=0.0, kappa20=0.0, kappa11=0.0, at1=0.0, t2=0.0, nci=0.0, dp_fix=0.0, misc_l=15.0,
                        nc_l=0.0)
    return {"t1": terminal(**kw), "kt": terminal(**kw, fixed=fixed, lam_f=0.0, parts=("real_rubles",))}


# ------------------------------------------------------------------ Р11-1: ставки, стационар, мир H, наклоны


def check_rates_bank() -> None:
    """Книга дерева с синтетическими долями у всех 13 книг: T_real = T*; цели ставок К4 в квартале Q каждого мира =
    стационар своим счётом (1e-12); LT-спред кредитных книг (гейт пола) = свой счёт; Nss «по книгам» = стационар решателя;
    наклоны book_slopes = (y_M − y_N) / (ref_M − ref_N) своим счётом; ставки клеток во всех кварталах — рекурсия
    y_q = y_(q−1) + ρ (y*_q − y_(q−1)) целей ставки ядра (одна форма доли в шаге и в цели)."""
    from model.cell import _Cell
    from model.nii import book_slopes
    run = bank(shares(SYNTH))
    ctx, tr = run.ctx, run.ctx.transmission
    assert ctx.prep.phi_share == SYNTH
    assert abs(tr.t_real - tr.t_target) < TOL, (tr.t_real, tr.t_target)
    own = own_stationary(run)
    books = ctx.book.get("nii.books")
    Q = ctx.timeline.Q
    for w in ctx.book.get("worlds.ids"):
        goal = _Cell(ctx, w, "norm", "mid").target_rates(Q)
        for b in books:
            assert abs(goal[b] - own["rates"][w][b]) < TOL, (w, b, goal[b], own["rates"][w][b])
        for b, row in tr.lt_spread.items():
            r = own["ref"][w][books[b]["ref"]]
            assert abs(row[w] - (own["rates"][w][b] - r)) < TOL, (w, b)
        for b, v in SYNTH.items():
            want = -v * (own["ref"][w][books[b]["ref"]] - own["ref"][own["H"]][books[b]["ref"]])
            assert abs(tr.share_lt[b][w] - want) < TOL, (w, b)
    nss = own_nss(run, own)
    for w, v in nss.items():
        assert abs(tr.nss[w] - v) < TOL, (w, tr.nss[w], v)
    slopes = book_slopes(ctx.book, P4._real_facts(), tr)
    for b, spec in books.items():
        d = own["ref"]["M"][spec["ref"]] - own["ref"]["N"][spec["ref"]]
        assert abs(slopes[b] - (own["rates"]["M"][b] - own["rates"]["N"][b]) / d) < 1e-10, b
    for c in run.cells:
        if c.regime != "norm":
            continue
        cell = _Cell(ctx, c.world, c.regime, c.scenario)
        for q in range(1, Q + 1):
            goal = cell.target_rates(q)
            for b, spec in books.items():
                prev, now = c.books[b]["rate"][q - 1], c.books[b]["rate"][q]
                want = prev + float(spec["rho"]) * (goal[b] - prev)
                assert abs(now - want) < 1e-12, (c.label, q, b, now, want)


def check_h_world() -> None:
    """Мир-опора H: без ключа уровня в мире N (уровень — в мире-опоре) клетки мира H бит в бит при любых долях — слагаемое
    доли в мире H — ноль, σ0 от долей не зависит; в мирах N и M ставки книг с долей меняются. С ключом уровня в мире N мир
    H меняется только через σ0 (законная связь transmission)."""
    plain, keyed = bank(drop=(LEVEL,)), bank(shares(SYNTH), drop=(LEVEL,))
    assert plain.ctx.transmission.sigma0 == keyed.ctx.transmission.sigma0
    for x, y in zip(plain.cells, keyed.cells):
        if x.world == "H":
            assert x.v_ri == y.v_ri and x.quarters == y.quarters, x.label
            assert all(x.books[b]["rate"] == y.books[b]["rate"] for b in x.books), x.label
        else:
            assert x.books["cards"]["rate"] != y.books["cards"]["rate"], x.label
    level = bank(shares(SYNTH))
    assert level.ctx.transmission.sigma0 != bank().ctx.transmission.sigma0


# ------------------------------------------------------------------ Р11-2: база опта, якорь, слово funds


def _client_books(book: Any) -> tuple[str, ...]:
    books = book.get("nii.books")
    drivers = set(map(str, book.opt(DRIVERS) or {}))
    return tuple(b for b in books if books[b]["side"] == "liability" and not books[b].get("balancing") and b not in drivers)


def _own_balance(run: Any, c: Any, q: int) -> float:
    """Активы − (все книги-пассивы + прочие пассивы + дивиденды к выплате + AT1 + НДУ якоря + капитал) — своим счётом."""
    af = run.ctx.prep.af
    books = run.ctx.book.get("nii.books")
    liab = sum(float(c.books[b]["balance"][q]) for b in books if books[b]["side"] == "liability")
    qq = c.quarters
    return float(qq["assets"][q]) - (liab + float(qq["other_liabilities"][q]) + float(qq["dp"][q]) + af.at1 + af.nci
                                     + float(qq["bv"][q]))


def check_funds_bank() -> None:
    """Книга дерева (К3 и К6) с funds_scope: clients: якорь доли опта = опт / средства клиентов (факты); книги слова funds
    подготовки — средства без К6; в каждой клетке и квартале опт − добор = s × средства клиентов (без книги К6) и тождество
    баланса своим счётом (все книги средств — пассивы); без ключа база — ряд funds (с К6)."""
    run, base = bank({SCOPE: "clients"}), bank()
    p, book = run.ctx.prep, run.ctx.book
    clients = _client_books(book)
    facts = P4._real_facts()
    bal = facts.file("balance")["books"]
    assert abs(book.get("volumes.wholesale_to_funds")
               - float(bal["wholesale"]["v"]) / sum(float(bal[b]["v"]) for b in clients)) < 1e-15
    assert p.funds_words == clients and p.wh_corp == tuple(b for b in clients if b not in p.roles.retail)
    assert "insurance_liab" not in clients and base.ctx.prep.funds_words is None
    for r, words in ((run, clients), (base, None)):
        s = r.ctx.prep.wh_to_funds
        for c in r.cells:
            for q in range(1, r.ctx.timeline.Q + 1):
                funds = (float(c.quarters["funds"][q]) if words is None
                         else sum(float(c.books[b]["balance"][q]) for b in words))
                got = float(c.quarters["wholesale"][q]) - float(c.quarters["wholesale_extra"][q])
                assert abs(got - s * funds) <= 1e-12 * max(1.0, abs(got)), (c.label, q, got, s * funds)
                assert abs(_own_balance(r, c, q)) <= 1e-9 * float(c.quarters["assets"][q]), (c.label, q)
                total = sum(float(c.books[b]["balance"][q]) for b in r.ctx.prep.roles.funds)
                assert abs(float(c.quarters["funds"][q]) - total) <= 1e-12 * total, (c.label, q)


def check_funds_words() -> None:
    """Слово funds баз строк под ключом (фикстура `core_t` с книгой К6 «средства юрлиц» за строкой страхования и базой
    комиссий funds): уровень якоря базы — средства без К6, ряд vol_fees клеток — полусумма концов средств без К6; без
    ключа — с книгой К6. Компонента смеси funds и драйвер денег К8 словом — те же книги (`funds_books`)."""
    from model.book import client_books, funds_books
    from model.cell import compile_mix
    keyed = P3.mix_run(**_t9(), volumes__funds_scope="clients", checks__client_funds="clients")
    plain = P3.mix_run(**_t9(), checks__client_funds="clients")
    for run, scoped in ((keyed, True), (plain, False)):
        p, book = run.ctx.prep, run.ctx.book
        assert p.driven, "фикстура без К6 — проверка пуста"
        words = _client_books(book) if scoped else p.roles.funds
        assert funds_books(p.roles, book) == words and client_books(p.roles, book) == _client_books(book)
        assert p.fees_line is not None and p.fees_line.kind == "funds"
        assert abs(p.fees_line.end0 - sum(p.af.balances[b] for b in words)) < 1e-9
        mix = compile_mix({"a": {"share": 1.0, "base": "funds"}}, "x", books=book.get("nii.books"), roles=p.roles,
                          balances=p.af.balances, funds=funds_books(p.roles, book))
        assert set(mix) == set(words)
        for c in run.cells:
            for q in range(1, run.ctx.timeline.Q + 1):
                own = sum(float(c.books[b]["balance"][q - 1]) + float(c.books[b]["balance"][q]) for b in words) / 2
                assert abs(float(c.quarters["vol_fees"][q]) - own) <= 1e-12 * own, (c.label, q, scoped)


def check_funds_memo_and_link_base() -> None:
    """Р11-2, экземпляры слова funds, которых книга дерева не трогает (проверка core9-verify), на фикстуре `core_t` с книгой
    К6 «средства юрлиц» за строкой страхования (база страхования — кредиты), драйвером денег К8 словом funds и базой
    связи объёма `volumes.link_base: funds`: (1) память стороны средств квартала (вторая доля прироста) — опт, добор,
    ликвидность, деньги и RWA те же, что без памяти, и опт − добор = s × средства клиентов без К6; (2) деньги К8 —
    C_0 / D_0 × D_q на средствах клиентов (конец квартала `base_end`); (3) история базы связи (x = 0) — конец якоря на
    средствах клиентов: без ключа она больше ровно на половину остатка книги К6 якоря; (4) база объёма квартала —
    полусумма концов средств клиентов (начало и конец)."""
    from model.cell import _Cell, initial_state
    common = dict(**P3.cash_keys(), volumes__liability_drivers={"corp_funds": "insurance"},
                  other__insurance_volume_base="loans", volumes__link_base="funds", checks__client_funds="clients")
    run = P3.t_run(**common, volumes__funds_scope="clients")
    plain = P3.t_run(**common)
    ctx, p = run.ctx, run.ctx.prep
    assert not p.memo_off and p.growth is not None and p.driven is not None and p.link_base == "funds"
    words = _client_books(ctx.book)
    assert "corp_funds" not in words and set(words) < set(p.roles.funds)
    d0 = sum(p.af.balances[b] for b in words)
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(p)
    memo: dict = {}
    cell.evaluate(st, 1, (), 1.0, memo=memo)
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    for name in ("wholesale", "wholesale_extra", "liquidity", "securities", "cash", "other_assets", "rwa", "funds"):
        assert second[name] == fresh[name], name
    for row in (second, fresh):
        clients = sum(row["_bal"][b] for b in words)
        assert abs(row["wholesale"] - row["wholesale_extra"] - p.wh_to_funds * clients) <= TOL * clients
        assert abs(row["cash"] - P3.T_CASH / d0 * clients) <= TOL * row["cash"]
    k6 = sum(p.af.balances[b] for b in p.roles.funds if b not in words)
    assert abs(plain.ctx.prep.hist_vol[0] - p.hist_vol[0] - k6 / 2) <= TOL * p.hist_vol[0]
    assert plain.ctx.prep.hist_vol[-1] == p.hist_vol[-1]
    cell = _Cell(ctx, "M", "norm", "mid")
    rows = cell.run(until=4)[0]
    prev = d0
    for q, row in enumerate(rows, start=1):
        now = sum(row["_bal"][b] for b in words)
        assert abs(cell.flows["vol"][q] - (prev + now) / 2) <= TOL * now, q
        prev = now


def _t9() -> dict[str, Any]:
    """Фикстура `core_t` прохода 8 (база комиссий — средства клиентов, книга К6 за строкой страхования) без κ и ρ."""
    from tests import support_core_p8 as P8
    keys = dict(P8.T_KEYS)
    keys.pop("opex__line_share_roots", None)
    keys.pop("volumes__liability_driver_roots", None)
    return keys


# ------------------------------------------------------------------ Р11-3: НДУ в рублях


def check_nci_bank() -> None:
    """Книга дерева с pnl.nci_real {LT: 4,82}: доля НДУ подготовки 0, НДУ квартала 4,82 / 4 в ценах якоря; в каждой клетке
    и квартале ni − ni_sh = НДУ квартала × индекс цен мира; вход терминала — доля 0 и NCI_L = Σ_(q ∈ L) НДУ квартала ×
    индекс; DDM = RI в каждой клетке (обе формы терминала)."""
    from model.cell import _Cell, cell_path
    run = bank({NCI: {"LT": NCI_LT}})
    ctx = run.ctx
    p, tl = ctx.prep, ctx.timeline
    assert p.nci_share == 0.0 and set(p.nci_q.values()) == {NCI_LT / 4}
    assert bank().ctx.prep.nci_share == float(_bank_data()["pnl"]["nci_share"])
    L = tl.year(tl.Q)
    idx = {w: _Cell(ctx, w, "norm", "mid").w.price_index for w in ctx.book.get("worlds.ids")}
    for c in run.cells:
        for q in range(1, tl.Q + 1):
            want = NCI_LT / 4 * idx[c.world][q]
            got = float(c.quarters["ni"][q]) - float(c.quarters["ni_sh"][q])
            assert abs(got - want) < 1e-12, (c.label, q, got, want)
        assert abs(c.v_ddm - c.v_ri) <= 1e-9 * abs(c.v_ri), c.label
    for w in ctx.book.get("worlds.ids"):
        term = cell_path(ctx, w, "norm", "mid").terminal
        nci_l = sum(NCI_LT / 4 * idx[w][q] for q in range(1, tl.Q + 1) if tl.year(q) == L)
        assert term["nci_share"] == 0.0 and abs(term["nci_l"] - nci_l) < 1e-12, (w, term.get("nci_l"), nci_l)
    assert "nci_l" not in cell_path(bank().ctx, "N", "norm", "mid").terminal


# ------------------------------------------------------------------ отказы схемы


def check_refusals() -> None:
    """Схема: доля |share| ≥ 1, null и не число — отказ; funds_scope вне перечня и null — отказ; clients при
    checks.client_funds ≠ clients — отказ (одно слово — две величины); nci_real null — отказ; ключи по отдельности — не
    отказ."""
    b0 = next(iter(S.book_of().get("nii.books")))
    S.book_of(**{f"nii__books__{b0}__phi_share": 0.5})
    S.book_of(**{f"nii__books__{b0}__phi_share": -0.5})
    for bad in (1.0, -1.0, 1.5, "x"):
        refused(lambda bad=bad: S.book_of(**{f"nii__books__{b0}__phi_share": bad}), f"nii.books.{b0}.phi_share")
    refused(lambda: S.book_of(**{f"nii__books__{b0}__phi_share": None}), "phi_share: null в читаемом пути")
    S.book_of(volumes__funds_scope="all")
    S.book_of(volumes__funds_scope="clients", checks__client_funds="clients")
    refused(lambda: S.book_of(volumes__funds_scope="clients"), "volumes.funds_scope = 'clients' при checks.client_funds")
    refused(lambda: S.book_of(volumes__funds_scope="clients", checks__client_funds="all"), "одна величина")
    refused(lambda: S.book_of(volumes__funds_scope="books"), "volumes.funds_scope")
    refused(lambda: S.book_of(volumes__funds_scope=None), "volumes.funds_scope: null в читаемом пути")
    S.book_of(pnl__nci_real={"LT": 1.0})
    refused(lambda: S.book_of(pnl__nci_real=None), "pnl.nci_real: null в читаемом пути")


# ------------------------------------------------------------------ листы: бэктест книг, вывод, §4, проверки классов


def _sheet(name: str, where: Path) -> Any:
    """Лист: копия мутанта (каталог запуска проверок — мутационный набор), иначе — дерево. Входы листа бэктеста — дерева."""
    from tests.support_book import load_module
    rel = where.relative_to(ROOT) / f"{name}.py"
    here = Path.cwd() / rel
    module = load_module(here if here.exists() else ROOT / rel, f"sheet9_{name}")
    if hasattr(module, "INPUTS"):
        module.INPUTS = ROOT / rel.parent / "inputs" / "stage1" / "calib" / "nii" / "backtest"
    return module


def check_sheet_backtest() -> None:
    """Лист бэктеста книг §5 1(б): механика на параметрах совместного подбора воспроизводит выход листа этапа 1 (ЧПМ модели
    и факта по кварталам окна, плечи) ровно; наклон каждой книги — функция ядра book_slopes (не совместный подбор); на книге
    дерева без долей — плечо L 1,004 п.п., с долями фрагмента книги наклоны книг типа Б — подбор; строки приёмки — 4 плеча."""
    from model.nii import book_slopes
    bt = _sheet("backtest_books", SHEET_NII)
    panel = bt.Panel()
    joint = {b: {k: float(panel.joint[b][k]) for k in ("a", "rho", "c")} for b in bt.BOOKS}
    nim = panel.nim_model(joint)
    assert all(nim[i] == panel.stage1["nim_model_joint"][p] for i, p in enumerate(panel.q))
    assert all(panel.nim[i] == panel.stage1["nim_actual_bank"][p] for i, p in enumerate(panel.q))
    legs = panel.legs(nim)
    assert all(legs[k]["max_abs"] * 100 == panel.stage1["legs_joint"][t]["max_abs_pp"] for k, (t, _) in bt.LEGS.items())
    facts = P4._real_facts()
    for run in (bank(), bank(shares(frag_shares()))):
        res = bt.backtest(run.ctx.book, facts)
        core = book_slopes(run.ctx.book, facts, run.ctx.transmission)
        assert all(res["slope_model"][b] == core[b] for b in bt.BOOKS)
        assert res["legs"]["L"]["max_abs"] != res["legs_joint"]["L"]["max_abs"]
        rows = bt.rows_of(res)
        assert len(rows) == 5 and [r["ok"] for r in rows[:4]] == [r["value"] <= bt.NORM for r in rows[:4]]
    keyed = bt.backtest(bank(shares(frag_shares())).ctx.book, facts)
    for b in ("cards", "liquidity", "mortgage", "auto", "securities"):
        assert abs(keyed["slope_model"][b] - keyed["slope_joint"][b]) < 5e-4, b
    if _ex_point_tree():
        assert round(bt.backtest(bank().ctx.book, facts)["legs"]["L"]["max_abs"] * 100, 3) == 1.004


def check_sheet_funds() -> None:
    """Лист вывода и лист §4 — «средства клиентов» функцией ядра client_books / funds_books (одна функция)."""
    from model.book import client_books, funds_books
    run = bank({SCOPE: "clients"})
    D = _sheet("derive_on_engine", SHEET_PATH)
    assert D.client_fund_books(run.ctx) == client_books(run.ctx.prep.roles, run.ctx.book) == _client_books(run.ctx.book)
    assert funds_books(run.ctx.prep.roles, run.ctx.book) == _client_books(run.ctx.book)
    assert funds_books(bank().ctx.prep.roles, bank().ctx.book) == bank().ctx.prep.roles.funds
    src = (SHEET_PATH / "marginal_loan.py").read_text(encoding="utf-8")
    assert "funds_books(roles, book)" in src and "funds_avg = sum(avg[b] for b in words)" in src


def check_class_slopes() -> None:
    """Проверки классов, класс 6 (Р11-1): на книге дерева без долей находки — книги типа Б и Φ_A с долей подбора ≠ 0
    (cards, liquidity, mortgage, cash_loans, corp_loans) и книги «ждёт решения»; с долями фрагмента книги — только книги
    «ждёт решения»; доля у книги не типа Б — находка."""
    C = _sheet_tool("class_checks")
    cfg = C.load_config(C.CONFIG)
    facts = P4._real_facts()

    def fired(run: Any, extra: dict | None = None) -> set[str]:
        node = copy.deepcopy(cfg)
        node.update(extra or {})
        chk = C.Check(6, "centres", "")
        C.class6_slopes(C.make_bench(run.ctx.book, facts, node), chk)
        return {f.split(":")[0].split(" ")[1] for f in chk.findings}

    # типы наклонов — по-русски, как таблица раздела А (интеграция круга 11): «ждёт» — тип ждёт решения ведущего
    pending = {b for b, v in cfg["book_slopes"]["books"].items() if v["type"] == "ждёт"}
    assert fired(bank()) >= {"cards", "liquidity", "mortgage", "cash_loans", "corp_loans"} | pending
    # доли книги дерева — фрагмент прохода и доли, поставленные книгой позже (поток fix11: опт 0,2477 — Р11-1, тип Б): с ними
    # находок нет, кроме «ждёт»; с одним фрагментом прохода — ещё книги типа Б, чью долю фрагмент не несёт
    _, data = P4._real_book()
    tree = {b: float(v[SHARE]) for b, v in data["nii"]["books"].items() if SHARE in v}
    assert fired(bank(shares(tree))) == pending
    assert fired(bank(shares(frag_shares()))) == pending | (set(tree) - set(frag_shares()))
    wrong = copy.deepcopy(cfg["book_slopes"])
    wrong["books"]["cards"]["type"] = "решение"
    assert "cards" in fired(bank(shares(frag_shares())), {"book_slopes": wrong})


def _sheet_tool(name: str) -> Any:
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"tool9_{name}", ROOT / "ops" / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
