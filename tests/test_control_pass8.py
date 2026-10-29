# -*- coding: utf-8 -*-
"""Контрольная модель: ключи восьмого прохода ядра Совкомбанка (core-pass8) своим счётом.

Ключи (решения ведущего № 10; методика — spec.yaml прохода 8, пример — tests/fixtures/core_pass8/example.json, копия
примера методики; фрагмент книги — tests/fixtures/core_pass8/book_keys_pass8.yaml, копия фрагмента методики; κ и ρ
формы строки фрагмента тест подставляет в книгу репозитория, пока она ключа не несёт; книгу с ключом тест судит её же κ
и ρ):

* Р10-5 (`volumes.line_link_form`: mixed | line) — франшиза строки в смеси базы расходов и книга К6 растут формой самой
  строки: g = c_link_growth(x, w, λ, r) = (1 + w + λ (x − 1 − w)) (1 + r) при корне множителем; франшиза Φ_q = Φ_(q−4)
  g(A_q / A_(q−4), w, λ, κ_q), Φ_x = A_x / A_0 (A — средние базы строки); К6 E_q = E_0 Ψ_q, Ψ_q = Ψ_(q−4) g(D_q / D_(q−4),
  w, λ, ρ_q), Ψ_x = D_x / D_0 (D — база строки на концах кварталов).
* Р10-6 (`checks.funds_cost_to_key.scope`: modal_cell | world_expectation) — число гейта мира — отношение ожиданий
  процентов и остатков книг средств по клеткам мира с весами P(r) P(s | r); модальная клетка печатается рядом.
* Р10-1 в числах гейтов (`checks.client_funds`: all | clients, ключ (3)) — «средства клиентов» гейтов и пути
  фондирования без книг К6.

Без ключей контрольная модель считает бит в бит прежние числа — это держит сводка (tests/independent_model.py на книге
репозитория: текст и JSON) и тесты «ключ нейтрален» ниже. Сверка с ядром (метка ci_only) требует ядра с проходом 8 — нет
ядра, его функции или ключа в схеме ядра — провал, не пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import functools
import json
import math
from fractions import Fraction

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

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass8"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass8.yaml"
# интеграция круга 10: книга репозитория несёт форму строки — «без ключа» нужны κ формы уровней и ρ цепи на той же книге
# (неподвижная точка листа без ключа формы; круг 12 — сухой перевывод r12mixed); κ и ρ книги — корни г/г формы строки
MIXED_BOOK = FIXTURES / "book_keys_mixed_r12.yaml"
FORM = "line_link_form"
KAPPA, RHO = "opex.line_share_roots", "volumes.liability_driver_roots"
DRIVERS = "volumes.liability_drivers"
LINK_I = "other.insurance_volume_link"
LINK_AXIS = LINK_I                                       # первый путь связки оси связи страхования (Р7-3)
BASE_AXIS = "other.insurance_volume_base.mix.corporate.share"   # первый путь связки оси базы страхования (Р5-1)
LAYER_M = "macro_neutral"
NEUTRAL_UNTIL = 2029                                     # κ и ρ — переход до 2029К4, с 2030 года 0
DROP = object()
# входы примера Р10-6 и строки страхования примера (example.py методики; в example.json — их итоги)
EX6_POST = {"soft": Fraction(3, 5), "norm": Fraction(2, 5)}
EX6_TABLE = {"soft": {"mid": Fraction(7, 10), "strict": Fraction(3, 10)},
             "norm": {"mid": Fraction(1, 2), "strict": Fraction(1, 2)}}
EX6_CELLS = {("soft", "mid"): (70, 1000), ("soft", "strict"): (66, 950), ("norm", "mid"): (80, 1010),
             ("norm", "strict"): (84, 990)}            # (проценты × дни, остатки × дни) за годы гейта
EX6_KEY = Fraction(1, 10)
EX_INS_HIST = {-3: 30, -2: 35, -1: 33, 0: 40}

rel, numbers = tp2.rel, tp2.numbers


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def fr(s) -> Fraction:
    return Fraction(s)


def get(book: dict, dotted: str):
    node = book
    for k in dotted.split("."):
        node = (node or {}).get(k)
    return node


@functools.lru_cache(maxsize=None)
def _frag() -> dict:
    return yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8"))


def own_keys(book: dict) -> bool:
    """Книга репозитория уже несёт форму строки (поток книги поставил κ и ρ, выведенные листом для неё)."""
    return (book.get("volumes") or {}).get(FORM) == "line"


def strip_paths(book: dict, heads) -> dict:
    """Книга без путей κ и ρ в связках осей (на концах — κ и ρ центра)."""
    out = copy.deepcopy(book)
    for ax in out["valuation"]["uncertainty"]["axes"]:
        if ax.get("kind") == cm.AXIS_BUNDLE and any(str(p).startswith(h + ".") for p in ax["paths"] for h in heads):
            ax["paths"] = [p for p in ax["paths"] if not any(str(p).startswith(h + ".") for h in heads)]
            for end in ("low", "high"):
                ax[end] = {k: v for k, v in ax[end].items() if not any(str(k).startswith(h + ".") for h in heads)}
    return out


def plain(book: dict) -> dict:
    """Книга без ключей прохода 8 (поток книги может их уже нести): без формы связи и ключей гейтов; κ и ρ — прежние
    ключи книги, а если книга несла форму строки (её κ и ρ — корни г/г) — κ формы уровней и ρ цепи на этой книге
    (фикстура MIXED_BOOK, интеграция круга 10)."""
    out = copy.deepcopy(book)
    if own_keys(book):
        mixed = yaml.safe_load(MIXED_BOOK.read_text(encoding="utf-8"))
        out["opex"]["line_share_roots"]["insurance"] = copy.deepcopy(mixed["opex"]["line_share_roots"]["insurance"])
        out["volumes"]["liability_driver_roots"]["insurance"] = copy.deepcopy(mixed["volumes"]["liability_driver_roots"]["insurance"])
    out["volumes"].pop(FORM, None)
    (out["checks"].get("funds_cost_to_key") or {}).pop("scope", None)
    out["checks"].pop("client_funds", None)
    # интеграция круга 11: funds_scope: clients (проход 9) схема пускает только с client_funds: clients — снимается вместе с ним
    out.get("volumes", {}).pop("funds_scope", None)
    _val = out.get("valuation") or {}
    if isinstance(_val.get("reference_variants"), list):
        _val["reference_variants"] = [v for v in _val["reference_variants"]
                                      if "volumes.funds_scope" not in (v.get("overrides") or {})]
    return out


def keyed(book: dict, form="line", **paths) -> dict:
    """Книга с ключом формы: если книга репозитория формы строки не несёт — κ и ρ страхования фрагмента методики (центр
    формы строки), пути κ и ρ в связках сняты (на концах — центр); подмены точечных путей paths (точки через «__»)."""
    out = copy.deepcopy(book)
    out["volumes"][FORM] = form
    if form == "line" and not own_keys(book):
        f = _frag()
        out["opex"]["line_share_roots"] = copy.deepcopy(f["opex"]["line_share_roots"])
        out["volumes"]["liability_driver_roots"] = copy.deepcopy(f["volumes"]["liability_driver_roots"])
        out = strip_paths(out, (KAPPA, RHO))
    for dotted, v in paths.items():
        out = tp2.put(out, dotted.replace("__", "."), v)
    return out


def gated(book: dict, scope=None, clients=None) -> dict:
    out = copy.deepcopy(book)
    if scope is not None:
        out["checks"]["funds_cost_to_key"]["scope"] = scope
    if clients is not None:
        out["checks"]["client_funds"] = clients
        if clients == "all":                          # круг 11: funds_scope: clients схема пускает только с client_funds: clients
            out.get("volumes", {}).pop("funds_scope", None)
    return out


def put(book: dict, dotted: str, value) -> dict:
    return tp2.put(book, dotted, value)


def at_end(book: dict, first: str, which: str) -> dict:
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0] == first)
    return cm.c_apply_overrides(book, dict(ax[which]))


def tag(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def driven_book(book: dict) -> str:
    books = [b for b, line in (book["volumes"].get("liability_drivers") or {}).items() if line == "insurance"]
    assert len(books) == 1, books
    return books[0]


def strip(cell_numbers: list, fields=("franchise_phi", "franchise_h", "funds_cost")) -> list:
    """Числа клетки без печати ключей (Φ, H, проценты книг средств, D ведомых книг)."""
    cell_numbers = copy.deepcopy(cell_numbers)
    for r in cell_numbers[1]:
        for f in fields:
            r.pop(f, None)
        for x in r.get("quarters") or []:
            x.pop("driven_level", None)
    return cell_numbers


def layer_p(ctl: dict, layer: str) -> dict:
    ctx = ctl["ctx"]
    lw = cm.c_layer_weights(ctx["B"])[layer]
    prs = cm.c_bget(ctx["B"], "joint.reg_prob_given_regime")
    return {tag(c): lw.get(c["world"], 0.0) * ctx["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]])
            for c in ctl["cells"]}


@pytest.fixture(scope="module")
def repo():
    book, facts = tcm._inputs()
    return book, facts


@pytest.fixture(scope="module")
def keyed_run(repo):
    """Прогон книги с формой строки в центре и ключами гейтов (ожидание мира, средства клиентов без К6)."""
    book, facts = repo
    base = book if own_keys(book) else keyed(plain(book))   # книга с формой строки — свои κ и ρ (интеграция круга 10)
    return cm.c_control_run(gated(base, "world_expectation", "clients"), facts)


# ============================================================================ пример (формула и правило)


def _chain(hist: dict, path: list, w: float, lam: float, roots: list, mult: bool = True) -> dict:
    """Индекс формы строки функцией c_link_growth: история B_x / B_0 (x = −3…0), дальше Φ_q = Φ_(q−4) g(B_q / B_(q−4))."""
    b0 = hist[0]
    B = {**hist, **{q + 1: v for q, v in enumerate(path)}}
    X = {x: hist[x] / b0 for x in range(-3, 1)}
    for q in range(1, len(path) + 1):
        X[q] = X[q - 4] * cm.c_link_growth(B[q] / B[q - 4], w, lam, roots[q - 1], mult)
    return X


@pytest.mark.tact
def test_p8_example_by_own_code():
    """Пример Р10-5 (example.json) своим счётом (1e-12): g обеих форм корня; франшиза формы строки Φ двух клеток; К6 —
    Ψ и E = E_0 Ψ; λ = ½, 1 и 0: при λ = 1, κ = 0 — Φ = A / A_0, при λ = 0 — Φ = H (c_franchise_h); строка страхования
    той же формой — Φ / INS одинаково в клетках (запись примера); правило κ на двух клетках (вероятности ½) своим счётом —
    κ примера, E[Φ] = E[A] / A_0 ровно до 1e-12."""
    ex = example()["R10_5"]
    lam, w = float(fr(ex["lam"])), float(fr(ex["wage"]))
    assert cm.c_link_growth(1.1, w, lam, -0.05, False) == pytest.approx(float(fr(ex["g_additive_example"])), rel=1e-15)
    assert cm.c_link_growth(1.1, w, lam, -0.05, True) == pytest.approx(float(fr(ex["g_multiplicative_example"])),
                                                                      rel=1e-15)
    f = ex["franchise"]
    hist = {int(k): float(fr(v)) for k, v in f["hist_A"].items()}
    cells = {k: [float(fr(x)) for x in v] for k, v in f["A"].items()}
    kap = [float(fr(x)) for x in f["kappa"]]
    n = len(kap)
    phi = {k: _chain(hist, v, w, lam, kap) for k, v in cells.items()}
    for k in cells:
        for q in range(1, n + 1):
            assert rel(phi[k][q], float(fr(f["phi_line_form"][k][str(q)]))) <= 1e-12, (k, q)
    # λ = 1 и κ = 0: Φ = A / A_0; λ = 0: Φ = H (номинальная часть Р8-6)
    one = _chain(hist, cells["c1"], w, 1.0, [0.0] * n)
    full = {**hist, **{q + 1: v for q, v in enumerate(cells["c1"])}}
    assert all(rel(one[q], full[q] / hist[0]) <= 1e-12 for q in range(1, n + 1))
    zero = _chain(hist, cells["c1"], w, 0.0, kap)
    h = {x: hist[x] / hist[0] for x in range(-3, 1)}
    for q in range(1, n + 1):
        h[q] = cm.c_franchise_h(h[q - 4], w, kap[q - 1])
        assert rel(zero[q], h[q]) <= 1e-15, q
    assert f["lambda0_equals_H"] is True and f["lambda1_kappa0_equals_A_over_A0"] is True
    # строка страхования той же формой с корнем r: Φ / INS одинаково в клетках
    r = [float(fr(x)) for x in f["line_root_r"]]
    for k, v in cells.items():
        a = {**hist, **{q + 1: x for q, x in enumerate(v)}}
        ins = {x: float(y) for x, y in EX_INS_HIST.items()}
        for q in range(1, n + 1):
            ins[q] = ins[q - 4] * cm.c_link_growth(a[q] / a[q - 4], w, lam, r[q - 1], True)
            assert rel(ins[q], float(fr(f["line_ins"][k][str(q)]))) <= 1e-12, (k, q)
            assert rel(phi[k][q] / ins[q], float(fr(f["phi_over_ins"][str(q)]))) <= 1e-12, (k, q)
    # правило κ (лист) на двух клетках с вероятностями ½: своим счётом
    X = {k: {x: hist[x] / hist[0] for x in range(-3, 1)} for k in cells}
    B = {k: {**hist, **{q + 1: x for q, x in enumerate(v)}} for k, v in cells.items()}
    for q in range(1, n + 1):
        eg = sum(0.5 * X[k][q - 4] * cm.c_link_growth(B[k][q] / B[k][q - 4], w, lam, 0.0, True) for k in X)
        ea = sum(0.5 * B[k][q] for k in X) / hist[0]
        kq = ea / eg - 1.0
        assert rel(kq, float(fr(f["kappa_rule_two_cells"][q - 1]))) <= 1e-12, q
        for k in X:
            X[k][q] = X[k][q - 4] * cm.c_link_growth(B[k][q] / B[k][q - 4], w, lam, kq, True)
        assert rel(sum(0.5 * X[k][q] for k in X), ea) <= 1e-12, q
    # К6: Ψ на концах, E = E_0 Ψ
    k6 = ex["k6"]
    hist_d = {int(k): float(fr(v)) for k, v in k6["hist_D"].items()}
    psi = _chain(hist_d, [float(fr(x)) for x in k6["D"]], w, lam, [float(fr(x)) for x in k6["rho"]])
    e0 = float(fr(k6["E0"]))
    for q in range(1, n + 1):
        assert rel(psi[q], float(fr(k6["psi"][str(q)]))) <= 1e-12, q
        assert rel(e0 * psi[q], k6["E_float"][str(q)]) <= 1e-12, q


@pytest.mark.tact
def test_p8_opex_mix_with_the_line_form():
    """Смесь базы расходов с франшизой формы строки — слагаемое s B^C_0 Φ без λ-слагаемых (c_opex_mix(…, phi)); при Φ =
    A / A_0 — прежняя смесь (1e-15); франшиза строки вне phi — прежнее слагаемое (бит в бит)."""
    import random
    rng = random.Random(8)
    for _ in range(200):
        shares = {"fees": rng.uniform(0.0, 0.4), "ins": rng.uniform(0.0, 0.4)}
        b_c, b0 = rng.uniform(1e2, 1e4), rng.uniform(1e2, 1e4)
        a = {"fees": rng.uniform(1.0, 5e3), "ins": rng.uniform(1.0, 5e3)}
        a0 = {"fees": rng.uniform(1.0, 5e3), "ins": rng.uniform(1.0, 5e3)}
        phi = rng.uniform(0.5, 3.0)
        old = cm.c_opex_mix(shares, b_c, b0, a, a0)
        got = cm.c_opex_mix(shares, b_c, b0, a, a0, None, {"ins": phi})
        want = (1.0 - sum(shares.values())) * b_c + shares["fees"] * b0 * a["fees"] / a0["fees"] + shares["ins"] * b0 * phi
        assert rel(got, want) <= 1e-14
        assert rel(cm.c_opex_mix(shares, b_c, b0, a, a0, None, {"ins": a["ins"] / a0["ins"]}), old) <= 1e-15
        assert cm.c_opex_mix(shares, b_c, b0, a, a0, None, {}) == old


@pytest.mark.tact
def test_p8_r10_6_example_by_own_code():
    """Пример Р10-6 своим счётом: P(r, s | w) = P(r) P(s | r) (запись примера), отношение ожиданий c_ratio_of_expectations
    — 3704/4955 ровно (1e-15), модальная клетка — 7/10; ожидание отношений (не форма гейта) — другое число."""
    ex = example()["R10_6"]
    probs = {k: float(EX6_POST[k[0]] * EX6_TABLE[k[0]][k[1]]) for k in EX6_CELLS}
    for k, p in probs.items():
        assert p == float(fr(ex["P(r,s|w)"]["/".join(k)])), k
    parts = {k: (float(n), float(d)) for k, (n, d) in EX6_CELLS.items()}
    ratio = cm.c_ratio_of_expectations(parts, probs) / float(EX6_KEY)
    assert rel(ratio, float(fr(ex["world_expectation_ratio"]))) <= 1e-15
    n, d = parts[("soft", "mid")]
    assert rel(n / d / float(EX6_KEY), float(fr(ex["modal_cell_ratio"]))) <= 1e-15
    mean = sum(probs[k] * parts[k][0] / parts[k][1] for k in parts) / float(EX6_KEY)
    assert rel(mean, ex["mean_of_ratios_NOT_gate_form"]) <= 1e-12 and abs(mean - ratio) > 1e-4


# ============================================================================ чтение ключей и отказы (контекст)


@pytest.mark.tact
def test_p8_keys_are_read_and_refused(repo):
    """Форма ключа связи — всегда, и в неактивном режиме (К6 снят, связь расходов 0): null, логическое, число, иная
    строка — отказ; mixed и нет ключа — прежние формы; line — франшиза формы строки и К6 формы строки при активном К6
    (без К6 — только франшиза). Ключи гейтов: scope и client_funds не из перечня (и null) — отказ; без них числа гейта не
    пишутся (keyed ложно)."""
    book, facts = repo
    base = plain(book)
    for bad in (None, True, 1, "Line", "mixed ", ["line"]):
        for extra in ({}, {"volumes__liability_drivers": {}}, {"opex__volume_link": 0.0}):
            with pytest.raises(cm.ControlInputError, match="line_link_form"):
                cm.c_control_context(keyed(base, form=bad, **extra), facts)
    ctx = cm.c_control_context(base, facts)
    assert ctx["line_form"] is False and ctx["k6_line"] is False and ctx["funds_keys"]["keyed"] is False
    mixed = cm.c_control_context(keyed(base, form="mixed"), facts)
    assert mixed["line_form"] is False and mixed["k6_line"] is False
    line = cm.c_control_context(keyed(base), facts)
    b = driven_book(base)
    assert line["line_form"] is True and line["k6_line"] is True
    d = line["driven"][b]
    assert d["d0"] > 0.0 and sorted(d["hist"]) == sorted(cm.c_qback(line["anchor"], j) for j in range(cm.QY))
    assert d["hist"][line["anchor"]] == d["d0"]
    off = cm.c_control_context(keyed(base, volumes__liability_drivers={}), facts)
    assert off["line_form"] is True and off["k6_line"] is False and off["share_nominal"] is not None
    for bad in (None, "world", True, 1):
        with pytest.raises(cm.ControlInputError, match="scope"):
            cm.c_control_context(put(base, "checks.funds_cost_to_key.scope", bad), facts)
        with pytest.raises(cm.ControlInputError, match="client_funds"):
            cm.c_control_context(put(base, "checks.client_funds", bad), facts)
    assert cm.c_funds_keys(gated(base, "world_expectation")) == {"scope": "world_expectation", "clients": False,
                                                                 "keyed": True}
    assert cm.c_funds_keys(gated(base, clients="clients")) == {"scope": "modal_cell", "clients": True, "keyed": True}
    assert cm.c_funds_keys(gated(base, clients="all"))["keyed"] is True


@pytest.mark.tact
def test_p8_k6_history_refusals(repo):
    """История D ведомой книги до якоря (x = −3…0) — концы фактов: нет конца квартала — отказ входа; D ≤ 0 — отказ."""
    book, facts = repo
    ctx = cm.c_control_context(keyed(plain(book)), facts)
    y, q = cm.c_qback(ctx["anchor"], 2)
    per = f"{y}Q{q}"
    for how in ("missing", "zero"):
        c2 = dict(ctx)
        c2["A"] = dict(ctx["A"])
        c2["driven"] = copy.deepcopy(ctx["driven"])
        for node in ("history", "history_books"):
            rec = dict(c2["A"].get(node) or {})
            if per in rec:
                rec[per] = None if how == "missing" else {k: 0.0 for k in rec[per]}
                if how == "missing":
                    rec.pop(per)
            c2["A"][node] = rec
        with pytest.raises(cm.ControlInputError, match="нет конца квартала" if how == "missing" else "≤ 0"):
            cm.c_driven_line_rule(c2)


# ============================================================================ клетки (вне такта)


def test_p8_neutral_cases_are_bit_for_bit(repo):
    """Бит в бит с прогоном без ключей: mixed (точка, низ, верх, 36 клеток); line в неактивных режимах — К6 снят и
    франшизы нет (доля страхования 0) — как та же книга без ключа (три клетки расчётов); scope modal_cell и client_funds
    all — числа клеток те же (печать процентов книг средств снята)."""
    book, facts = repo
    base = plain(book)
    a, b = cm.c_control_run(base, facts), cm.c_control_run(keyed(base, form="mixed"), facts)
    assert (a["point"], a["low"], a["high"]) == (b["point"], b["low"], b["high"])
    for ca, cb in zip(a["cells"], b["cells"]):
        assert tag(ca) == tag(cb) and numbers(cb) == numbers(ca), tag(ca)
    off = put(put(base, DRIVERS, {}), "opex.line_shares.insurance", 0.0)
    _, x = tp2.cells_of(off, facts)
    _, y = tp2.cells_of(keyed(off), facts)
    for key in tp2.CELLS:
        assert numbers(y[key]) == numbers(x[key]), key
    _, z = tp2.cells_of(gated(base, "modal_cell", "all"), facts)
    _, x0 = tp2.cells_of(base, facts)
    for key in tp2.CELLS:
        assert strip(numbers(z[key])) == strip(numbers(x0[key])), key
        assert any("funds_cost" in r for r in z[key]["rows"]) and not any("funds_cost" in r for r in x0[key]["rows"])


def test_p8_franchise_recursion_in_cells(keyed_run):
    """В каждой клетке и квартале франшиза формы строки: Φ = Φ того же квартала прошлого года × c_link_growth(A / A того
    же квартала прошлого года, рост зарплат мира клетки, λ, κ квартала, корень множителем) — 1e-12; A — средняя базы
    строки квартала (печать vol_ins: средняя периода на квартал), до якоря — полусумма концов фактов, Φ = A / A_0; с 2030
    года κ = 0. Франшиза действует: в 2026К3 Φ ≠ A / A_0."""
    ctx = keyed_run["ctx"]
    B, anchor = ctx["B"], ctx["anchor"]
    spec = ctx["line_base"]["ins"]
    a0 = cm.c_base_hist_avg(ctx, spec, *anchor)
    lam, traj = ctx["share_nominal"]["ins"]
    assert ctx["root_mult"] and spec["kind"] == cm.BASE_WEIGHTS      # вход теста: корень множителем, база — веса книг
    for c in keyed_run["cells"]:
        phi, a = {}, {}
        for i, p in enumerate(ctx["periods"]):
            row, y = c["rows"][i], p["year"]
            seq = row["franchise_phi"]["ins"]
            assert "franchise_h" not in row and len(seq) == p["n"]
            for j, q in enumerate(p["quarters"]):
                a[(y, q)] = row["vol_ins"]
                if (y - 1, q) > anchor:
                    back_a, back_phi = a[(y - 1, q)], phi[(y - 1, q)]
                else:
                    back_a = cm.c_base_hist_avg(ctx, spec, y - 1, q)
                    back_phi = back_a / a0
                root = cm.c_traj_at(traj, y, q)
                wage = cm.c_world_quarter(B, c["world"], "wage_growth", y, q)
                want = back_phi * (1.0 + wage + lam * (a[(y, q)] / back_a - 1.0 - wage)) * (1.0 + root)
                assert rel(seq[j], want) <= 1e-12, (tag(c), y, q)
                if y > NEUTRAL_UNTIL:
                    assert root == 0.0
                phi[(y, q)] = seq[j]
        assert abs(c["rows"][0]["franchise_phi"]["ins"][0] / (c["rows"][0]["vol_ins"] / a0) - 1.0) > 1e-4, tag(c)


def test_p8_k6_line_recursion_in_cells(keyed_run):
    """В каждой клетке и квартале квартального прохода капитала ведомая книга — E_0 × Ψ, Ψ = Ψ того же квартала прошлого
    года × c_link_growth(D_q / D того же квартала, рост зарплат мира клетки, λ, ρ квартала) — D — печать уровня базы строки
    на конце квартала (принятые остатки квартала), прошлый год — та же печать (до 1e-8: запись пути клетки — годовой путь,
    сходится с планом квартального прохода до 1e-9), до якоря — концы фактов, Ψ = D / D_0. Конец года квартального прохода
    — остаток книги годовой строки (1e-9). С 2030 года ρ = 0."""
    ctx = keyed_run["ctx"]
    B, anchor = ctx["B"], ctx["anchor"]
    b = driven_book(B)
    d = ctx["driven"][b]
    e0, d0 = ctx["A"]["E0"][b], d["d0"]
    seen, worst = 0, 0.0
    for c in keyed_run["cells"]:
        psi, lev = {}, {}
        for i, p in enumerate(ctx["periods"]):
            y, row = p["year"], c["rows"][i]
            for x, q in zip(row["quarters"], p["quarters"]):
                lev[(y, q)], psi[(y, q)] = x["driven_level"][b], x["driven"][b] / e0
                if (y - 1, q) > anchor:
                    back_d, back_psi = lev[(y - 1, q)], psi[(y - 1, q)]
                else:
                    back_d = d["hist"][(y - 1, q)]
                    back_psi = back_d / d0
                root = cm.c_traj_at(d["root"], y, q) if "root" in d else 0.0
                wage = cm.c_world_quarter(B, c["world"], "wage_growth", y, q)
                want = back_psi * (1.0 + wage + d["lam"] * (lev[(y, q)] / back_d - 1.0 - wage)) * (1.0 + root)
                worst = max(worst, rel(psi[(y, q)], want))
                assert rel(psi[(y, q)], want) <= 1e-8, (tag(c), y, q)
                if y > NEUTRAL_UNTIL:
                    assert root == 0.0
                seen += 1
            assert rel(row["quarters"][-1]["driven"][b], row["driven_end"][b]) <= 1e-9, (tag(c), y)
    assert seen == len(keyed_run["cells"]) * sum(p["n"] for p in ctx["periods"])


def test_p8_link_one_root_zero_is_the_base_and_continuity(repo):
    """Связь страхования 1 и корни 0: Φ = A / A_0 (1e-12; та же смесь, что без ключа Р8-6) и Ψ = D / D_0 (1e-12) в трёх
    клетках; стоимость клеток непрерывна по связи с ключом у 0 и у 1 (1e-8 относительно)."""
    book, facts = repo
    base = keyed(plain(book))
    zero_k = {k: (v if k == "LT_from" else 0.0) for k, v in base["opex"]["line_share_roots"]["insurance"].items()}
    zero_r = {k: (v if k == "LT_from" else 0.0) for k, v in base["volumes"]["liability_driver_roots"]["insurance"].items()}
    one = put(put(put(base, LINK_I, 1.0), KAPPA + ".insurance", zero_k), RHO + ".insurance", zero_r)
    ctx, cells = tp2.cells_of(one, facts)
    a0 = cm.c_base_hist_avg(ctx, ctx["line_base"]["ins"], *ctx["anchor"])
    b = driven_book(ctx["B"])
    d0, e0 = ctx["driven"][b]["d0"], ctx["A"]["E0"][b]
    for key, c in cells.items():
        for i, p in enumerate(ctx["periods"]):
            row = c["rows"][i]
            for j in range(p["n"]):
                assert rel(row["franchise_phi"]["ins"][j], row["vol_ins"] / a0) <= 1e-12, (key, p["year"], j)
            for x in row["quarters"]:
                assert rel(x["driven"][b] / e0, x["driven_level"][b] / d0) <= 1e-12, (key, p["year"])
    for lo, hi in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
        _, a = tp2.cells_of(put(base, LINK_I, lo), facts)
        _, c2 = tp2.cells_of(put(base, LINK_I, hi), facts)
        for key in tp2.CELLS:
            assert rel(a[key]["v_price"], c2[key]["v_price"]) <= 1e-8, (lo, key)


def test_p8_layer_m_franchise_and_book_stay_at_their_base(repo, keyed_run):
    """Слой «рыночные ставки как есть» до 2029 года: франшиза — Σ_q E_M[Φ_q] против Σ_q E_M[A_q] / A_0 за год (мера
    года: у контроля средняя базы — одна на квартал периода, а Φ несёт квартальный профиль истории — поквартально до 2 %,
    за год сходится) — до 2e-3 (замер 1,1e-3); смесь базы расходов с формой строки — та же, что без ключа (κ формы уровней
    книги), до 3e-4 (замер 1e-5); книга К6 — E_M[Ψ] против E_M[D] / D_0 на конце IV квартала — до 2e-3 (замер 5,6e-4; κ и
    ρ выведены листом на квартальных средних и концах ядра)."""
    book, facts = repo
    plain_run = cm.c_control_run(plain(book), facts)
    ctx = keyed_run["ctx"]
    pm = layer_p(keyed_run, LAYER_M)
    a0 = cm.c_base_hist_avg(ctx, ctx["line_base"]["ins"], *ctx["anchor"])
    b = driven_book(ctx["B"])
    d = ctx["driven"][b]
    e0 = ctx["A"]["E0"][b]
    worst = {"phi": 0.0, "mix": 0.0, "psi": 0.0}
    for i, p in enumerate(ctx["periods"]):
        if p["year"] > NEUTRAL_UNTIL:
            break
        ephi = sum(pm[tag(c)] * sum(c["rows"][i]["franchise_phi"]["ins"]) for c in keyed_run["cells"])
        ea = sum(pm[tag(c)] * c["rows"][i]["vol_ins"] * p["n"] for c in keyed_run["cells"]) / a0
        mk = sum(pm[tag(c)] * c["rows"][i]["vol_opex"] for c in keyed_run["cells"])
        mp = sum(pm[tag(c)] * c["rows"][i]["vol_opex"] for c in plain_run["cells"])
        epsi = sum(pm[tag(c)] * c["rows"][i]["quarters"][-1]["driven"][b] for c in keyed_run["cells"]) / e0
        ed = sum(pm[tag(c)] * c["rows"][i]["quarters"][-1]["driven_level"][b] for c in keyed_run["cells"]) / d["d0"]
        worst = {"phi": max(worst["phi"], abs(ephi / ea - 1.0)), "mix": max(worst["mix"], abs(mk / mp - 1.0)),
                 "psi": max(worst["psi"], abs(epsi / ed - 1.0))}
    assert worst["phi"] <= 2e-3 and worst["mix"] <= 3e-4 and worst["psi"] <= 2e-3, worst


def test_p8_funds_gate_and_funding_path_by_own_sums(keyed_run):
    """Число гейта стоимости средств (ожидание мира, средства клиентов без К6) — отношение ожиданий своими суммами по
    клеткам мира с P(r) P(s | r) (1e-12), модальная клетка рядом; область modal_cell — число модальной клетки; книги — без
    ведомой книги К6 (при all — с ней); ожидание отношений — другое число; масса — веса миров слоя «свой взгляд» над
    порогом. Путь фондирования — отношения ожидаемых остатков точки и остатки модальной клетки (1e-12), при clients — без
    книги К6, якорь — остатки якоря."""
    res = keyed_run
    ctx = res["ctx"]
    B = ctx["B"]
    b6 = driven_book(B)
    g = cm.c_funds_cost_to_key(res)
    assert g["scope"] == "world_expectation" and g["clients"] is True and b6 not in g["books"]
    idx = [i for i, p in enumerate(ctx["periods"]) if not p["stub"] and p["year"] >= g["from_year"]]
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")
    _, r_m, s_m = res["central"]["cell"]
    spread = 0.0
    for clients in (True, False):
        gg = cm.c_funds_cost_to_key(res, clients=clients)
        assert (b6 in gg["books"]) is (not clients)
        modal_scope = cm.c_funds_cost_to_key(res, scope="modal_cell", clients=clients)
        for w, x in gg["by_world"].items():
            num = den = mean = 0.0
            for c in res["cells"]:
                if c["world"] != w:
                    continue
                pr = res["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]])
                n = sum(c["rows"][i]["funds_cost"][bk][0] for i in idx for bk in gg["books"])
                dd = sum(c["rows"][i]["funds_cost"][bk][1] for i in idx for bk in gg["books"])
                num, den, mean = num + pr * n, den + pr * dd, mean + pr * n / dd
                if (c["regime"], c["scenario"]) == (r_m, s_m):
                    modal = n / dd
            key = sum(cm.c_world_quarter(B, w, "key_rate", y, q) * cm.c_q_len(y, q)
                      for y in range(gg["from_year"], gg["to_year"] + 1) for q in range(1, 5))
            key /= sum(cm.c_q_len(y, q) for y in range(gg["from_year"], gg["to_year"] + 1) for q in range(1, 5))
            assert rel(x["key"], key) <= 1e-12 and rel(x["ratio"], num / den / key) <= 1e-12, (clients, w)
            assert rel(x["modal_ratio"], modal / key) <= 1e-12 and x["modal_cell"] == "/".join((w, r_m, s_m)), w
            assert rel(modal_scope["by_world"][w]["ratio"], modal / key) <= 1e-12, (clients, w)
            if not clients:
                spread = max(spread, abs(mean - num / den) / (num / den))     # ожидание отношений ≠ форма гейта
    assert spread > 1e-9, spread
    own = cm.c_layer_weights(B)["analytical"]
    assert g["worlds"] == [w for w, x in g["by_world"].items() if x["ratio"] > g["max"]]
    assert g["mass"] == sum(float(own.get(w, 0.0)) for w in g["worlds"]) and g["ok"] == (not g["worlds"])
    fp = cm.c_funding_path(res)
    assert fp["clients"] is True
    pm = cm.c_point_mass(res)
    modal_c = cm.c_cell_of(res, *res["central"]["cell"])
    e0 = ctx["A"]["E0"]
    f0 = sum(e0[bk] for bk in g["books"])
    assert rel(fp["anchor"]["wholesale_share"], e0["wholesale"] / (f0 + e0["wholesale"])) <= 1e-12
    for i in range(len(res["years"])):
        tl = tf = tw = 0.0
        for c in res["cells"]:
            row, k = c["rows"][i], pm[tag(c)]
            tl, tf, tw = tl + k * row["loans"], tf + k * (row["funds"] - row["driven_end"][b6]), tw + k * row["wholesale"]
        assert rel(fp["mix"]["loans_to_funds"][i], tl / tf) <= 1e-12 and rel(fp["mix"]["wholesale_share"][i],
                                                                             tw / (tf + tw)) <= 1e-12, i
        row = modal_c["rows"][i]
        fu = row["funds"] - row["driven_end"][b6]
        assert rel(fp["modal_cell"]["wholesale_share"][i], row["wholesale"] / (fu + row["wholesale"])) <= 1e-12, i
    allf = cm.c_funding_path(res, clients=False)
    assert allf["mix"]["wholesale_share"][-1] < fp["mix"]["wholesale_share"][-1]


# ============================================================================ сверка с ядром (ci_only)


def _cases(book: dict) -> dict:
    """Книги сверки с формой строки: центр, концы оси связи страхования (0 и 0,74) и концы оси базы страхования (на концах
    — κ и ρ центра, пока книга не несёт путей κ и ρ формы строки в связках)."""
    base = keyed(plain(book)) if not own_keys(book) else book
    return {"centre": base, "link_low": at_end(base, LINK_AXIS, "low"), "link_high": at_end(base, LINK_AXIS, "high"),
            "base_low": at_end(base, BASE_AXIS, "low"), "base_high": at_end(base, BASE_AXIS, "high")}


CASES = ("centre", "link_low", "link_high", "base_low", "base_high")


@pytest.mark.ci_only
@pytest.mark.parametrize("case", CASES, ids=CASES)
def test_p8_control_rows_off_are_the_growth_cut_class(repo, case):
    """Сверка М§17 книг с формой строки (центр, концы осей связи и базы страхования): строки вне допуска — только класс
    Р6-9 (tests/test_control_pass4.growth_cut_class), V0 слоёв не совпадают до 1e-9; строки ведомой книги и роста смеси
    базы расходов — в допуске.

    Прототип методики (28.10.2026, p3 @ d127189, книга сухого перевывода c8-line с κ и ρ концов в связках): центр 14 170
    строк, вне допуска 0; связь 0 — 14 300 / 0, 0,74 — 14 177 / 0; концы оси базы — 14 243 / 0 и 14 260 / 0; книга без
    ключей — 14 243 / 0."""
    book, facts = repo
    b = _cases(book)[case]
    ctl = cm.c_control_run(b, facts)
    run = tcm.core_run_of(copy.deepcopy(b))
    rows = tcm.compare_with_core(run, ctl)
    stray = tp4.growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
    driven = [r for r in rows if r.get("group") == "driven"]
    assert driven and all(r["ok"] for r in driven), tcm._fail_lines([r for r in driven if not r["ok"]])
    assert not tcm.exact_match(run, ctl)


GATE_TOL = 0.003            # число гейта мира — отношение (М§17: отношения — 0,3 п.п.)


@pytest.mark.ci_only
@pytest.mark.parametrize("keys", [("world_expectation", "all"), ("modal_cell", "clients"),
                                  ("world_expectation", "clients")], ids=["exp-all", "modal-clients", "exp-clients"])
def test_p8_funds_gate_matches_core(repo, keys):
    """Гейт стоимости средств клиентов к ключевой (Р10-6, ключ (3)) на книге с формой строки: своё прочтение формулы на
    рядах клеток ядра (ставка × средний остаток × дни книг средств клиентов, P(r, s | w) — вероятности слоя «свой
    взгляд» ядра на вес мира) — число ядра до 1e-12; число контрольной модели (годовая форма) — до 0,003 (отношение);
    ключевая мира — до 1e-12; вердикт мира тот же, кроме мира у порога (|ratio − max| ≤ 0,003). Путь фондирования
    (средства клиентов, при clients — без книги К6): доли опта и кредиты к средствам — до 0,003, якорь — до 1e-12.

    Прототип методики (книга репозитория): ожидание мира N 0,701751, H 0,779832, M 0,868011 (контроль 0,702009, 0,780072,
    0,867963); модальная клетка, clients — N 0,717306, H 0,795402, M 0,883000 (контроль 0,717574, 0,795647, 0,882945);
    своё прочтение на рядах ядра — до 6e-17. Путь фондирования прототипа ключ client_funds не читает (тест ждёт
    реализации по спецификации)."""
    book, facts = repo
    scope, clients = keys
    b = gated(_cases(book)["centre"], scope, clients)
    ctl = cm.c_control_run(b, facts)
    run = tcm.core_run_of(copy.deepcopy(b))
    lv = __import__("importlib").import_module("model.levels")
    core = lv.funds_cost_to_key(run)
    mine = cm.c_funds_cost_to_key(ctl)
    assert core is not None and mine is not None
    ctx = ctl["ctx"]
    years = set(range(mine["from_year"], mine["to_year"] + 1))
    parts = {}
    for c in run.cells:
        n = d = 0.0
        for k in range(1, len(c.books[mine["books"][0]]["avg"])):
            y, q = cm.c_qper(ctx["anchor"], k)
            if y in years:
                dq = cm.c_q_len(y, q)
                n += math.fsum(c.books[bk]["rate"][k] * c.books[bk]["avg"][k] * dq for bk in mine["books"])
                d += math.fsum(c.books[bk]["avg"][k] * dq for bk in mine["books"])
        parts[(c.world, c.regime, c.scenario)] = (n, d)
    lay = run.layers["analytical"]
    for w, x in mine["by_world"].items():
        cw = core["by_world"][w]
        ww = sum(p for (xw, _, _), p in lay.prob.items() if xw == w)
        if ww:
            own = cm.c_ratio_of_expectations(parts, {k: p / ww for k, p in lay.prob.items() if k[0] == w})
            if scope == "world_expectation":
                assert rel(own, cw["cost"]) <= 1e-12, w
        assert rel(x["key"], cw["key"]) <= 1e-12, w
        assert abs(x["ratio"] - cw["ratio"]) <= GATE_TOL, (w, x["ratio"], cw["ratio"])
        if abs(cw["ratio"] - core["max"]) > GATE_TOL:
            assert (x["ratio"] > mine["max"]) == (cw["ratio"] > core["max"]), w
    fp_core, fp = lv.funding_path(run), cm.c_funding_path(ctl)
    if fp_core is not None:
        for m in ("loans_to_funds", "wholesale_share"):
            assert rel(fp["anchor"][m], fp_core["anchor"][m]) <= 1e-12, m
            for part in ("mix", "modal_cell"):
                for i, (a, c) in enumerate(zip(fp[part][m], fp_core[part][m])):
                    assert abs(a - c) <= GATE_TOL, (part, m, i, a, c)
