"""Проверки восьмого прохода ядра Совкомбанка (core-pass8): одна форма связи λ (Р10-5, ключ `volumes.line_link_form`),
гейт стоимости средств клиентов на ожидании мира (Р10-6, ключ `checks.funds_cost_to_key.scope`) и «средства клиентов» без
книг К6 в числах гейтов ядра (ключ (3) Р10-1, `checks.client_funds`). Все три ключа необязательны; нет ключа (и mixed /
modal_cell / all) — прежняя ветвь кода, бит в бит.

Р10-5, форма строки: g(x, w, λ, r) = (1 + w + λ (x − 1 − w)) (1 + r) при `volumes.line_root_form: multiplicative`, иначе
1 + w + r + λ (x − 1 − w). Франшиза строки в смеси базы расходов — Φ_q = Φ_(q−4) g(A_q / A_(q−4), w_q, λ, κ_q), Φ_x = A_x /
A_0 (A — средние базы строки, ряд vol_phi_<строка> вместо vol_nom_<строка>); книга К6 — Ψ_q = Ψ_(q−4) g(D_q / D_(q−4), w_q,
λ, ρ_q), Ψ_x = D_x / D_0 (D — база строки на концах кварталов, история — концы фактов), E_b,q = E_b,0 Ψ_q (ряды vol_psi_* и
vol_end_*). κ и ρ — корни г/г: лист выводит их последовательным правилом так, что в слое M до 2029К4 E_M[Φ_q] = E_M[A_q] /
A_0 и E_M[Ψ_q] = E_M[D_q] / D_0.

Р10-6: число гейта мира — отношение ожиданий Σ_c P(c | w) проценты_c / Σ_c P(c | w) остатки_c, P(r, s | w) = P(r) P(s | r);
модальная клетка печатается рядом. Ключ (3): книги средств клиентов — roles.funds без ведомых книг К6.

Одни и те же проверки зовут тесты (`tests/test_core_p8.py`) и мутационный набор (`tests/mutations.py`); каждая — тождество,
закрытая формула или число примера методики (`tests/fixtures/core_pass8/example.json` — копия выхода `example.py` агента
методики, notes/core-pass8; κ и ρ формы строки — `tests/fixtures/core_pass8/book_keys_pass8.yaml`), выведенные из книги и
фактов независимо от кода ядра: формула g, история D_x из фактов, вероятности P(r) P(s | r) из книги — своим счётом.
"""

from __future__ import annotations

import copy
import functools
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests import support_core_p3 as P3
from tests import support_core_p4 as P4
from tests import support_core_p6 as P6
from tests import support_core_p7 as P7
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "core_pass8"
EXAMPLE, BOOK_KEYS = FIXTURE / "example.json", FIXTURE / "book_keys_pass8.yaml"
close = S.close
refused = P3.refused
FORM, SCOPE, CLIENTS = "volumes.line_link_form", "checks.funds_cost_to_key.scope", "checks.client_funds"
KAPPA, RHO, DRIVERS = "opex.line_share_roots", "volumes.liability_driver_roots", "volumes.liability_drivers"
GATE = "checks.funds_cost_to_key"
LINK = {"fees": "fees.volume_link", "insurance": "other.insurance_volume_link"}
SERIES = {"fees": "vol_fees", "insurance": "vol_ins"}            # база строки A — ряд клетки (К2)
NOMINAL = {"fees": "vol_nom_fees", "insurance": "vol_nom_ins"}    # H^ℓ формы уровней (Р8-6)
PHI = {"fees": "vol_phi_fees", "insurance": "vol_phi_ins"}        # Φ^ℓ формы строки (Р10-5)
PSI = {"fees": "vol_psi_fees", "insurance": "vol_psi_ins"}        # Ψ^ℓ книг К6 формой строки (Р10-5)
END = {"fees": "vol_end_fees", "insurance": "vol_end_ins"}        # D^ℓ_q на конец квартала (Р9-1)
LAG = {"fees": "k6_end4_fees", "insurance": "k6_end4_ins"}        # D^ℓ «к тому же кварталу» — внутренний ряд шага
Q_END, LT_FROM = "2029Q4", 2030
MACRO = "macro_neutral"
B6 = "insurance_liab"
EX_BASE_POINT = 15.540107135265956           # точка книги дерева (p3 @ d127189) — без ключей прохода 8
EX_LINE_POINT = 15.560338036077532           # та же книга с ключом line и κ, ρ неподвижной точки прототипа
# фикстура `core_t` на фактах с историей книг: базы строк (комиссии — средства клиентов, страхование — розничные кредиты),
# доли франшиз 0,2 / 0,15 с κ у обеих строк (проход 6) и книга К6 «средства юрлиц» за строкой страхования с ρ (проход 7)
T_KEYS = {**P6.T_BASES, "opex__line_shares": P6.T_SHARES, "opex__line_share_roots": P6.T_KAPPA, **P7.T_K6,
          "volumes__liability_driver_roots": P7.T_RHO}
MULT = {"volumes__line_root_form": "multiplicative"}


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (ключ core8-spec): R10_5 — формулы точными дробями; R10_6 — гейт мира."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def _fragment() -> dict[str, Any]:
    import yaml
    return yaml.safe_load(BOOK_KEYS.read_text(encoding="utf-8"))


def frag_kappa() -> dict[str, Any]:
    """κ формы строки фрагмента книги прохода (сухой перевывод прототипа c8-line)."""
    return copy.deepcopy(_fragment()["opex"]["line_share_roots"]["insurance"])


def frag_rho() -> dict[str, Any]:
    """ρ формы строки фрагмента книги прохода (корень г/г, совместно с κ)."""
    return copy.deepcopy(_fragment()["volumes"]["liability_driver_roots"]["insurance"])


def g(x: Any, w: Any, lam: Any, r: Any, mult: bool) -> Any:
    """Рост г/г формы строки своим счётом (не функция ядра)."""
    return (1 + w + lam * (x - 1 - w)) * (1 + r) if mult else 1 + w + r + lam * (x - 1 - w)


def t8(form: str | None = "line", **changes: Any) -> Any:
    """Сетка фикстуры `core_t` с франшизами и книгой К6 (`T_KEYS`) и ключом формы `form` (None — без ключа)."""
    kw: dict[str, Any] = dict(T_KEYS)
    if form is not None:
        kw["volumes__line_link_form"] = form
    kw.update(changes)
    return P3.mix_run(**kw)


def _stripped(path: Any) -> bool:
    return any(str(path) == k or str(path).startswith(k + ".") for k in (KAPPA, RHO))


def tree_scope() -> dict[str, Any]:
    """Интеграция круга 11: «средства клиентов» книги дерева (проход 9, Р11-2) — volumes.funds_scope: clients вместе с
    checks.client_funds: clients (схема ставит их вместе). Неподвижная точка κ, ρ книги дерева выведена на этих ключах: проверки
    неподвижной точки на книге дерева ставят их обратно (`_bank_data` их снимает как ключи прохода 8). Нет ключа — пусто."""
    _, data = P4._real_book()
    if (data.get("volumes") or {}).get("funds_scope") == "clients":
        return {"volumes__funds_scope": "clients", "checks__client_funds": "clients"}
    return {}


def strip_pass9(out: dict) -> None:
    """Интеграция круга 11: книга дерева несёт ключи прохода ядра 9. Ключ volumes.funds_scope: clients схема пускает только вместе
    с checks.client_funds: clients (ключ прохода 8, который «без ключа» снимает) — он снимается тоже, с вариантами на его пути.
    Доли сжатия книг phi_share и вариант pnl.nci_real схеме ключей прохода 8 не мешают и остаются (книга дерева)."""
    (out.get("volumes") or {}).pop("funds_scope", None)
    val = out.get("valuation", {})
    if isinstance(val.get("reference_variants"), list):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(str(k) == "volumes.funds_scope" for k in (v.get("overrides") or {}))]


@functools.lru_cache(maxsize=None)
def _bank_data() -> dict[str, Any]:
    """Исходный словарь книги дерева без ключей прохода 8 (если поток книги их уже поставил) и без путей κ, ρ в осях и
    вариантах (κ и ρ проверки ставят целиком; сами ключи κ и ρ книги остаются)."""
    _, data = P4._real_book()
    out = copy.deepcopy(data)
    (out.get("volumes") or {}).pop("line_link_form", None)
    (out.get("checks") or {}).pop("client_funds", None)
    ((out.get("checks") or {}).get("funds_cost_to_key") or {}).pop("scope", None)
    strip_pass9(out)                                        # интеграция круга 11: и ключи прохода 9
    val = out.get("valuation", {})
    for ax in val.get("uncertainty", {}).get("axes", []):
        if any(_stripped(p) for p in ax.get("paths", [])):
            ax["paths"] = [p for p in ax["paths"] if not _stripped(p)]
            for end in ("low", "high"):
                if isinstance(ax.get(end), dict):
                    ax[end] = {k: v for k, v in ax[end].items() if not _stripped(k)}
    if isinstance(val.get("reference_variants"), list):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(_stripped(k) for k in (v.get("overrides") or {}))]
    return out


@functools.lru_cache(maxsize=None)
def _bank_run(changes: tuple = ()) -> Any:
    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    from model.paths import set_path
    data = copy.deepcopy(_bank_data())
    for dotted, value in changes:
        set_path(data, dotted, json.loads(value))
    facts = P4._real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts))


def bank(paths: dict[str, Any] | None = None, **short: Any) -> Any:
    """Сетка книги дерева (`_bank_data`) с подменами: `paths` — {точечный путь: значение}, `short` — `__` вместо точки."""
    changes = {**(paths or {}), **{k.replace("__", "."): v for k, v in short.items()}}
    return _bank_run(tuple(sorted((k, json.dumps(v)) for k, v in changes.items())))


def line_roots() -> tuple[dict[str, Any], dict[str, Any]]:
    """κ и ρ формы строки по умолчанию: книги дерева, если она уже несёт форму строки (поток книги поставил их неподвижной
    точкой листа на своей книге — интеграция круга 10), иначе — фрагмента книги прохода (неподвижная точка на p3 @ d127189)."""
    _, data = P4._real_book()
    if (data.get("volumes") or {}).get("line_link_form") == "line":
        return (copy.deepcopy(data["opex"][KAPPA.split(".")[1]]["insurance"]),
                copy.deepcopy(data["volumes"][RHO.split(".")[1]]["insurance"]))
    return frag_kappa(), frag_rho()


def bank_line(kappa: Any = None, rho: Any = None, **short: Any) -> Any:
    """Книга дерева с ключом line и κ, ρ (по умолчанию — `line_roots`: книги дерева с формой строки или фрагмента)."""
    kap, rh = line_roots()
    return bank({FORM: "line", f"{KAPPA}.insurance": kap if kappa is None else kappa,
                 f"{RHO}.insurance": rh if rho is None else rho}, **short)


_same = P6._same


def _ex_point_tree() -> bool:
    """Книга дерева — книга примера (точка без ключей — число p3 @ d127189)."""
    return bank().point == EX_BASE_POINT


# ------------------------------------------------------------------ без ключей и нейтральные формы — бит в бит


def check_neutral_bank() -> None:
    """Книга дерева: без ключей — точка p3 @ d127189 (если книга та же); mixed, modal_cell, all ≡ без ключа (точка, клетки,
    все ряды, отпечаток прохода, узел гейта, путь фондирования); line при неактивных режимах (нет κ и нет К6; связь расходов
    0 и нет К6) ≡ без ключа; рядов vol_phi_*, vol_psi_* без ключа нет."""
    from model.grid import path_inputs, path_key
    from model.levels import funding_path, funds_cost_to_key
    base = bank()
    q0 = set(base.cells[0].quarters)
    assert not (set(PHI.values()) | set(PSI.values())) & q0 and base.ctx.prep.k6_line is None
    assert base.ctx.prep.link_line is False and base.ctx.prep.hist_k6_line == {}
    key = path_key(path_inputs(base.ctx))
    for paths in ({FORM: "mixed"}, {SCOPE: "modal_cell"}, {CLIENTS: "all"}):
        run = bank(paths)
        _same(run, base)
        assert path_key(path_inputs(run.ctx)) == key, paths
        assert funds_cost_to_key(run) == funds_cost_to_key(base) and funding_path(run) == funding_path(base), paths
    for off in ({KAPPA: {}, DRIVERS: {}}, {"opex.volume_link": 0.0, DRIVERS: {}}):
        plain, keyed = bank(off), bank({**off, FORM: "line"})
        assert keyed.ctx.prep.link_line is False and keyed.ctx.prep.k6_line is None, off
        _same(keyed, plain)
        assert path_key(path_inputs(keyed.ctx)) == path_key(path_inputs(plain.ctx)), off


def check_neutral_fixture() -> None:
    """Т-книга (фикстура `core_t`, копия данных образца): mixed, modal_cell, all и line (κ и К6 у неё нет — ключ
    неактивного режима) ≡ без ключа; фикстура с франшизами и К6: mixed ≡ без ключа (отпечаток тот же), line двигает
    стоимость клеток."""
    from model.grid import path_inputs, path_key
    base = P3.mix_run()
    from model.checks import _wholesale_gate
    from model.levels import funding_path
    for kw in ({"volumes__line_link_form": "mixed"}, {"volumes__line_link_form": "line"},
               {"checks__client_funds": "all"}, {"checks__client_funds": "clients"}):
        run = P3.mix_run(**kw)
        assert run.ctx.prep.k6_line is None and not run.ctx.prep.link_line
        _same(run, base)
        # clients без К6 — ключ неактивного режима: путь фондирования и гейт доли опта — прежней ветвью, бит в бит
        assert funding_path(run) == funding_path(base) and repr(_wholesale_gate(run)) == repr(_wholesale_gate(base)), kw
    plain = t8(None)
    mixed = t8("mixed")
    _same(mixed, plain)
    assert path_key(path_inputs(mixed.ctx)) == path_key(path_inputs(plain.ctx))
    line = t8()
    assert line.ctx.prep.link_line and set(line.ctx.prep.k6_line) == {"insurance"}
    assert sum(abs(a.v_ri - b.v_ri) > 1e-6 for a, b in zip(line.cells, plain.cells)) > 30
    assert {"vol_phi_ins", "vol_phi_fees", "vol_psi_ins", "vol_end_ins"} <= set(line.cells[0].quarters)
    assert not {"vol_nom_ins", "vol_nom_fees"} & set(line.cells[0].quarters)


# ------------------------------------------------------------------ пример методики (точные дроби)


def _fr(s: str) -> Fraction:
    return Fraction(s)


def check_example() -> None:
    """Пример Р10-5 и Р10-6 (точные дроби): функция ядра `link_growth` на дробях — g примера обеих форм корня; Φ формы
    строки двух клеток — рекурсией своим счётом, равна числам примера; λ = 0 — Φ = H (форма уровней), λ = 1 и κ = 0 — Φ =
    A / A_0 ровно; строка страхования той же формы — Φ / INS одинаково в клетках; правило κ на двух клетках — E[Φ_q] =
    E[A_q] / A_0 ровно; книга К6 — Ψ и E = E_0 Ψ примера; гейт мира — P(r, s | w) = P(r) P(s | r), отношение ожиданий
    3704/4955 ≈ 0,74753 против модальной клетки 0,7 (и не ожидание отношений)."""
    from model.cell import link_growth
    ex = example()["R10_5"]
    lam, w = _fr(ex["lam"]), _fr(ex["wage"])
    assert link_growth(Fraction(11, 10), w, lam, Fraction(-1, 20), False) == _fr(ex["g_additive_example"])
    assert link_growth(Fraction(11, 10), w, lam, Fraction(-1, 20), True) == _fr(ex["g_multiplicative_example"])
    for x in (Fraction(9, 10), Fraction(6, 5)):
        for r in (Fraction(0), Fraction(1, 30)):
            for m in (True, False):
                assert link_growth(x, w, lam, r, m) == g(x, w, lam, r, m)
    fr = ex["franchise"]
    hist = {int(k): _fr(v) for k, v in fr["hist_A"].items()}
    kap = [_fr(x) for x in fr["kappa"]]
    cells = {k: [_fr(x) for x in v] for k, v in fr["A"].items()}

    def chain(h: dict, path: list, lam_: Fraction, roots: list) -> dict:
        x = {i: h[i] / h[0] for i in range(-3, 1)}
        b = {**h, **{q + 1: v for q, v in enumerate(path)}}
        for q in range(1, len(path) + 1):
            x[q] = x[q - 4] * link_growth(b[q] / b[q - 4], w, lam_, roots[q - 1], True)
        return x

    n = len(kap)
    phi = {k: chain(hist, v, lam, kap) for k, v in cells.items()}
    for k in cells:
        assert [phi[k][q] for q in range(1, n + 1)] == [_fr(fr["phi_line_form"][k][str(q)]) for q in range(1, n + 1)], k
    hh = {i: hist[i] / hist[0] for i in range(-3, 1)}
    for q in range(1, n + 1):
        hh[q] = hh[q - 4] * (1 + w) * (1 + kap[q - 1])
    phi0 = chain(hist, cells["c1"], Fraction(0), kap)
    assert all(phi0[q] == hh[q] for q in range(1, n + 1)) and fr["lambda0_equals_H"] is True
    phi1 = chain(hist, cells["c1"], Fraction(1), [Fraction(0)] * n)
    a1 = {**hist, **{q + 1: v for q, v in enumerate(cells["c1"])}}
    assert all(phi1[q] == a1[q] / hist[0] for q in range(1, n + 1)) and fr["lambda1_kappa0_equals_A_over_A0"] is True
    ins_hist = {-3: Fraction(30), -2: Fraction(35), -1: Fraction(33), 0: Fraction(40)}
    r_ins = [_fr(x) for x in fr["line_root_r"]]
    ratio = {}
    for k, v in cells.items():
        a = {**hist, **{q + 1: x for q, x in enumerate(v)}}
        ins = dict(ins_hist)
        for q in range(1, n + 1):
            ins[q] = ins[q - 4] * g(a[q] / a[q - 4], w, lam, r_ins[q - 1], True)
            assert ins[q] == _fr(fr["line_ins"][k][str(q)]), (k, q)
        ratio[k] = [phi[k][q] / ins[q] for q in range(1, n + 1)]
    assert ratio["c1"] == ratio["c2"] == [_fr(fr["phi_over_ins"][str(q)]) for q in range(1, n + 1)]
    pr = Fraction(1, 2)
    xs = {k: {i: hist[i] / hist[0] for i in range(-3, 1)} for k in cells}
    bs = {k: {**hist, **{q + 1: v for q, v in enumerate(cells[k])}} for k in cells}
    rule = []
    for q in range(1, n + 1):
        eg = sum(pr * xs[k][q - 4] * g(bs[k][q] / bs[k][q - 4], w, lam, 0, True) for k in xs)
        ea = sum(pr * bs[k][q] for k in xs) / hist[0]
        rule.append(ea / eg - 1)
        for k in xs:
            xs[k][q] = xs[k][q - 4] * g(bs[k][q] / bs[k][q - 4], w, lam, rule[-1], True)
        assert sum(pr * xs[k][q] for k in xs) == ea, q
    assert rule == [_fr(x) for x in fr["kappa_rule_two_cells"]] and fr["rule_holds_exactly"] is True
    k6 = ex["k6"]
    hd = {int(k): _fr(v) for k, v in k6["hist_D"].items()}
    psi = chain(hd, [_fr(x) for x in k6["D"]], lam, [_fr(x) for x in k6["rho"]])
    e0 = _fr(k6["E0"])
    assert all(psi[q] == _fr(k6["psi"][str(q)]) and e0 * psi[q] == _fr(k6["E"][str(q)]) for q in range(1, n + 1))
    gate = example()["R10_6"]
    post = {"soft": Fraction(3, 5), "norm": Fraction(2, 5)}
    table = {"soft": {"mid": Fraction(7, 10), "strict": Fraction(3, 10)}, "norm": {"mid": Fraction(1, 2), "strict": Fraction(1, 2)}}
    cells_g = {("soft", "mid"): (70, 1000), ("soft", "strict"): (66, 950), ("norm", "mid"): (80, 1010),
               ("norm", "strict"): (84, 990)}
    p = {c: post[c[0]] * table[c[0]][c[1]] for c in cells_g}
    assert {"/".join(c): str(v) for c, v in p.items()} == {k: str(_fr(v)) for k, v in gate["P(r,s|w)"].items()}
    expect = sum(p[c] * cells_g[c][0] for c in p) / sum(p[c] * cells_g[c][1] for c in p) / Fraction(1, 10)
    assert expect == _fr(gate["world_expectation_ratio"]) and abs(float(expect) - 0.74753) < 1e-5
    assert Fraction(70, 1000) / Fraction(1, 10) == _fr(gate["modal_cell_ratio"])
    mean_of_ratios = sum(p[c] * Fraction(cells_g[c][0], cells_g[c][1]) for c in p) / Fraction(1, 10)
    assert mean_of_ratios != expect and abs(float(mean_of_ratios) - gate["mean_of_ratios_NOT_gate_form"]) < 1e-15


# ------------------------------------------------------------------ ядро против формулы в каждой клетке и квартале


def _history(ctx: Any, period: str) -> dict[str, Any] | None:
    hist = ctx.facts.file("balance").get("history")
    if isinstance(hist, list):
        hist = {str(r["period"]): r for r in hist}
    return (hist or {}).get(period)


def fact_end(ctx: Any, lb: Any, x: int) -> float:
    """D_x — уровень базы строки-драйвера на конец квартала x ≤ 0 своим счётом по фактам (`balance.history`; x = 0 —
    остатки якоря): кредиты — узел loans, веса книг — Σ ω × остаток книги, номинал — 1."""
    if lb.kind == "nominal":
        return 1.0
    if x == 0:
        return float(lb.end0)
    row = _history(ctx, ctx.timeline.period(x))
    if lb.kind == "books":
        return sum(w * float(row["books"][b]["v"]) for b, w in lb.weights.items())
    return float(row[lb.kind]["v"])


def check_cells(run: Any) -> tuple[int, int]:
    """Каждая клетка и квартал сетки `run` с ключом line: франшиза Φ^ℓ (ряд vol_phi_<строка>) — рекурсия формы строки своим
    счётом (история A_x / A_0, зарплаты мира клетки, κ записи, форма корня книги; 1e-12); книга К6 — Ψ (ряд vol_psi_*) той же
    рекурсией по уровням базы на концах (история D_x из фактов, D_q своим счётом; ρ записи или 0), ряд vol_end_* = D_q,
    якорь — D_0 и 1, каждая ведомая книга E_q = E_0 Ψ_q (1e-12). → (кварталов франшизы, кварталов К6)."""
    ctx = run.ctx
    tl, prep, book = ctx.timeline, ctx.prep, ctx.book
    mult = book.opt("volumes.line_root_form") == "multiplicative"
    assert book.opt(FORM) == "line"
    kap_keys, rho_keys = book.opt(KAPPA) or {}, book.opt(RHO) or {}
    n_phi = n_psi = 0
    for line, (lam, _, name) in (prep.share_nominal or {}).items():
        assert prep.link_line and name == PHI[line] and lam == float(book.get(LINK[line]))
        kap = P6.kappa_ref(kap_keys[line], tl)
        hist = P6._base_hist(prep, line)
        own = (prep.fees_line if line == "fees" else prep.ins_line) is not None
        for c in run.cells:
            qs, wage = c.quarters, ctx.worlds[c.world].wage
            a = dict(hist)
            for q in range(1, tl.Q + 1):
                a[q] = qs[SERIES[line]][q] if own else (qs["loans"][q - 1] + qs["loans"][q]) / 2
            phi = {x: hist[x] / hist[0] for x in range(-3, 1)}
            assert qs[name][0] is None, c.label
            for q in range(1, tl.Q + 1):
                phi[q] = phi[q - 4] * g(a[q] / a[q - 4], wage[q], lam, kap[q], mult)
                assert close(qs[name][q], phi[q], 1e-12), (c.label, line, q, qs[name][q], phi[q])
                n_phi += 1
    spec = book.opt(DRIVERS) or {}
    for line, (lam, _, lb) in (prep.k6_line or {}).items():
        assert lam == float(book.get(LINK[line]))
        rho = P6.kappa_ref(rho_keys[line], tl) if line in rho_keys else [None] + [0.0] * tl.Q
        books = [str(b) for b, ln in spec.items() if ln == line]
        hist = {x: fact_end(ctx, lb, x) for x in range(-3, 1)}
        for c in run.cells:
            qs, wage = c.quarters, ctx.worlds[c.world].wage
            d = dict(hist)
            for q in range(1, tl.Q + 1):
                d[q] = P7._driver_level(prep, c, lb, q, wage)
            psi = {x: d[x] / d[0] for x in range(-3, 1)}
            assert qs[END[line]][0] == lb.end0 and qs[PSI[line]][0] == 1.0, c.label
            for q in range(1, tl.Q + 1):
                psi[q] = psi[q - 4] * g(d[q] / d[q - 4], wage[q], lam, rho[q], mult)
                assert close(qs[PSI[line]][q], psi[q], 1e-12), (c.label, line, q, qs[PSI[line]][q], psi[q])
                assert close(qs[END[line]][q], d[q], 1e-12), (c.label, line, q)
                for b in books:
                    e = c.books[b]["balance"]
                    assert close(e[q], e[0] * psi[q], 1e-12), (c.label, b, q, e[q], e[0] * psi[q])
                n_psi += 1
    return n_phi, n_psi


def check_phi_over_line(run: Any, line: str = "insurance") -> None:
    """Корень множителем: Φ^ℓ_q / INS_q одинаково во всех клетках сетки (1e-12 относительно) — франшиза пропорциональна
    строке, суждение λ одно; с 2030К1 (κ = 0) Φ_q / Φ_(q−4) = g(A_q / A_(q−4), w, λ, 0) — то же, что у строки без корня."""
    tl = run.ctx.timeline
    assert run.ctx.book.opt("volumes.line_root_form") == "multiplicative"
    first = run.cells[0].quarters
    for q in range(1, tl.Q + 1):
        ref = first[PHI[line]][q] / first["ins"][q]
        for c in run.cells[1:]:
            got = c.quarters[PHI[line]][q] / c.quarters["ins"][q]
            assert close(got, ref, 1e-12), (c.label, q, got, ref)


def check_grid() -> None:
    """Фикстура (франшизы обеих строк, книга К6 за страхованием; корень слагаемым и множителем; связь страхования 0,5, 0,
    0,3, 1; без ключа ρ — ρ ≡ 0) и книга дерева с κ, ρ фрагмента (36 × 42) — ядро против формулы в каждой клетке и квартале;
    лёгкая сетка (проходы полосы) — те же оценки; книга дерева с κ, ρ неподвижной точки прототипа — точка прототипа."""
    from model.grid import run_grid
    from tests.support_core_t import book_live
    run = t8()
    q = run.ctx.timeline.Q
    assert check_cells(run) == (2 * 36 * q, 36 * q)
    light = run_grid(run.ctx.book, run.ctx.facts, book_live(run.ctx.book), summary=True)
    assert light.point == run.point and [c.v_ri for c in light.cells] == [c.v_ri for c in run.cells]
    check_cells(t8(**MULT))
    for link in (0.0, 0.3, 1.0):
        check_cells(t8(other__insurance_volume_link=link))
    no_rho = t8(volumes__liability_driver_roots={})
    assert no_rho.ctx.prep.driver_roots is None and no_rho.ctx.prep.k6_line is not None
    check_cells(no_rho)
    brun = bank_line()
    assert brun.ctx.prep.root_mult and brun.ctx.prep.k6_line["insurance"][2].kind == "books"
    assert check_cells(brun) == (36 * brun.ctx.timeline.Q, 36 * brun.ctx.timeline.Q)
    check_phi_over_line(brun)


def check_limits() -> None:
    """Пределы формы (фикстура, корень множителем; книга дерева): λ = 0 (связи строк 0, К6 снят) — Φ ≡ H формы уровней
    при тех же κ: ряд до 1e-14, точка и стоимость клеток до 1e-12 (не бит в бит: у Φ множитель g(…) (1 + κ) — одним
    числом, у H — по очереди; замер — до 6e-16); λ = 1, κ = 0, ρ = 0 — Φ = A / A_0 и Ψ = D / D_0 (1e-12)."""
    def fixture(kappa: Any = None, rho: Any = None, **k: Any) -> Any:
        roots = {} if kappa is None else {"opex__line_share_roots": {"insurance": kappa, "fees": 0.0},
                                          "volumes__liability_driver_roots": {"insurance": rho}}
        return t8(**MULT, **roots, **k)

    for make in (fixture, bank_line):
        zero = {"other__insurance_volume_link": 0.0, "fees__volume_link": 0.0, "volumes__liability_drivers": {}}
        line, mixed = make(**zero), make(volumes__line_link_form="mixed", **zero)
        assert close(line.point, mixed.point, 1e-12), (line.point, mixed.point)
        for a, b in zip(line.cells, mixed.cells):         # до округления: Φ_(q−4)·(g·(1 + κ)) против (H_(q−4)·(1 + w))·(1 + κ)
            assert close(a.v_ri, b.v_ri, 1e-12), a.label
            for q in range(1, line.ctx.timeline.Q + 1):
                assert close(a.quarters["vol_phi_ins"][q], b.quarters["vol_nom_ins"][q], 1e-14), (a.label, q)
        one = make(0.0, 0.0, other__insurance_volume_link=1.0)
        prep, tl = one.ctx.prep, one.ctx.timeline
        a0 = P6._base_hist(prep, "insurance")[0]
        lb = prep.k6_line["insurance"][2]
        for c in one.cells:
            for q in range(1, tl.Q + 1):
                assert close(c.quarters["vol_phi_ins"][q], c.quarters["vol_ins"][q] / a0, 1e-12), (c.label, q)
                assert close(c.quarters["vol_psi_ins"][q], c.quarters["vol_end_ins"][q] / lb.end0, 1e-12), (c.label, q)


def check_continuity() -> None:
    """Непрерывность по связи страхования (книга дерева с ключом line и κ, ρ фрагмента; фикстура): точка при λ = 0 и 1e-9,
    1 − 1e-9 и 1 — до 1e-8 относительно."""
    for make in (lambda **k: bank_line(**k), lambda **k: t8(**k)):
        for a, b in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
            x = make(other__insurance_volume_link=a).point
            y = make(other__insurance_volume_link=b).point
            assert close(x, y, 1e-8), (a, b, x, y)


# ------------------------------------------------------------------ слой M: правило листа своим счётом, неподвижная точка


def _layer(run: Any) -> list[tuple[float, Any]]:
    prob = run.layers[MACRO].prob
    return [(prob[c.key], c) for c in run.cells if prob[c.key] > 0]


def line_rule(run: Any, lam: float, hist: dict, row: str) -> dict[str, Any]:
    """Корень формы строки правилом листа своим счётом: X_x = B_x / B_0, G = X_(q−4) g(B_q / B_(q−4), w^M_q, λ, 0), r_q =
    (E_M[B_q] / B_0) / E_M[G] − 1 (множителем) или (E_M[B_q] / B_0 − E_M[G]) / E_M[X_(q−4)], 6 знаков, рекурсия на записанном
    r; с 2030 года 0. B — ряд клетки `row` (q ≥ 1) и история `hist` (x ≤ 0)."""
    ctx = run.ctx
    tl = ctx.timeline
    mult = ctx.book.opt("volumes.line_root_form") == "multiplicative"
    wage = ctx.worlds[str(ctx.book.get("joint.macro_neutral_world"))].wage
    layer = _layer(run)
    b0 = float(hist[0])
    xs = [{x: float(hist[x]) / b0 for x in range(-3, 1)} for _ in layer]
    bs = [{**{x: float(hist[x]) for x in range(-3, 1)}, **{q: float(c.quarters[row][q]) for q in range(1, tl.Q + 1)}}
          for _, c in layer]
    out: dict[str, Any] = {}
    for q in range(1, tl.index(Q_END) + 1):
        w = float(wage[q])
        eg = sum(p * (x[q - 4] * g(b[q] / b[q - 4], w, lam, 0.0, mult)) for (p, _), x, b in zip(layer, xs, bs))
        eb = sum(p * b[q] for (p, _), b in zip(layer, bs)) / b0
        r = round(eb / eg - 1 if mult else (eb - eg) / sum(p * x[q - 4] for (p, _), x in zip(layer, xs)), 6)
        out[tl.period(q)] = r
        for x, b in zip(xs, bs):
            x[q] = x[q - 4] * g(b[q] / b[q - 4], w, lam, r, mult)
    out.update(LT=0.0, LT_from=LT_FROM)
    return out


def rules(run: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """κ и ρ страхования правилом листа своим счётом на сетке `run` с ключом line."""
    ctx = run.ctx
    prep = ctx.prep
    lam = float(ctx.book.get(LINK["insurance"]))
    kap = line_rule(run, lam, P6._base_hist(prep, "insurance"), SERIES["insurance"])
    lb = prep.k6_line["insurance"][2]
    rho = line_rule(run, lam, {x: fact_end(ctx, lb, x) for x in range(-3, 1)}, END["insurance"])
    return kap, rho


def _shift(a: dict, b: dict) -> float:
    return max(abs(float(v) - float(a.get(k, 0.0))) for k, v in b.items() if k not in ("LT", "LT_from"))


def fixed_point(make: Any, kap: Any, rho: Any, rounds: int = 7) -> tuple[Any, dict, dict, list[float]]:
    """Неподвижная точка κ, ρ (одна итерация на круг, как шаг share_roots листа) от `kap`, `rho`."""
    shifts: list[float] = []
    run = make(kap, rho)
    for _ in range(rounds):
        nk, nr = rules(run)
        shifts.append(max(_shift(kap, nk), _shift(rho, nr)))
        kap, rho = nk, nr
        run = make(kap, rho)
        if shifts[-1] < 5e-7:
            break
    return run, kap, rho, shifts


def check_layer_m(run: Any, top: float = 1e-5) -> tuple[float, float]:
    """Слой M (до 2029К4): |E_M[Φ_q] − E_M[A_q] / A_0| и |E_M[Ψ_q] − E_M[D_q] / D_0| — до `top` (запись 6 знаков);
    E_M[К6_q] / К6_0 = E_M[Ψ_q] (1e-12 — книга линейна по Ψ: Йенсена нет). → (невязка Φ, невязка Ψ)."""
    prep, tl = run.ctx.prep, run.ctx.timeline
    layer = _layer(run)
    a0 = P6._base_hist(prep, "insurance")[0]
    d0 = prep.k6_line["insurance"][2].end0
    b6 = next(b for b, ln in prep.k6_books.items() if ln == "insurance")       # книга К6 строки страхования
    e0 = prep.af.balances[b6]
    dev_phi = dev_psi = 0.0
    for q in range(1, tl.index(Q_END) + 1):
        e_phi = sum(p * c.quarters[PHI["insurance"]][q] for p, c in layer)
        e_psi = sum(p * c.quarters[PSI["insurance"]][q] for p, c in layer)
        dev_phi = max(dev_phi, abs(e_phi - sum(p * c.quarters[SERIES["insurance"]][q] for p, c in layer) / a0))
        dev_psi = max(dev_psi, abs(e_psi - sum(p * c.quarters[END["insurance"]][q] for p, c in layer) / d0))
        e_k6 = sum(p * c.books[b6]["balance"][q] for p, c in layer) / e0
        assert close(e_k6, e_psi, 1e-12), (q, e_k6, e_psi)
    assert dev_phi <= top and dev_psi <= top, (dev_phi, dev_psi)
    return dev_phi, dev_psi


def check_layer_bank() -> None:
    """Книга дерева: неподвижная точка κ, ρ правилом листа своим счётом от κ, ρ книги (форма уровней и цепи) — сдвиги кругов
    убывают до < 5e-7 (прототип: 5 кругов); слой M на ней (`check_layer_m`); на книге примера — κ и ρ фрагмента до 2e-6
    (фрагмент — сухой перевывод: ближние ключи книги тоже сдвинуты) и точка прототипа при κ, ρ его неподвижной точки."""
    data = _bank_data()
    run, kap, rho, shifts = fixed_point(lambda k, r: bank_line(k, r), data["opex"][KAPPA.split(".")[1]]["insurance"],
                                        data["volumes"][RHO.split(".")[1]]["insurance"])
    assert shifts[-1] < 5e-7 and all(b <= a for a, b in zip(shifts, shifts[1:])) and len(shifts) <= 6, shifts
    check_layer_m(run)
    if _ex_point_tree():
        assert _shift(frag_kappa(), kap) <= 2e-6 and _shift(frag_rho(), rho) <= 2e-6, (kap, rho)
        assert run.point == EX_LINE_POINT, run.point


def check_layer_fixture() -> None:
    """Фикстура (корень множителем): неподвижная точка κ, ρ правилом листа своим счётом от нуля — сдвиги не растут, последний
    — до единицы шестого знака (запись качается на округлении); слой M."""
    zero = {"LT": 0.0, "LT_from": LT_FROM}

    def make(k: Any, r: Any) -> Any:
        return t8(**MULT, opex__line_share_roots={"insurance": k, "fees": 0.0}, volumes__liability_driver_roots={"insurance": r})

    run, _, _, shifts = fixed_point(make, zero, zero)    # разброс клеток шире книги: запись 6 знаков может качаться на 1e-6
    assert shifts[-1] <= 1.0001e-6 and all(b <= a for a, b in zip(shifts, shifts[1:])), shifts
    check_layer_m(run)


def world_drift(run: Any, years: tuple[int, int] = (2029, 2036)) -> dict[str, tuple[float, float]]:
    """Дрейф 2036 / 2029 (IV квартал, веса аналитического слоя внутри мира; слой M — свой) у франшизы к базе строки
    (E[Φ] / E[A]) и у строки страхования к той же базе (E[INS] / E[A]). {мир или слой: (франшиза, строка)}."""
    tl = run.ctx.timeline
    la = run.layers["analytical"]
    groups = {MACRO: [(run.layers[MACRO].prob[c.key], c) for c in run.cells if run.layers[MACRO].prob[c.key]]}
    for w, ww in la.world_weights.items():
        groups[w] = [(la.prob[c.key] / ww, c) for c in run.cells if c.world == w]
    out = {}
    for name, cw in groups.items():
        vals = []
        for y in years:
            q = max(x for x in tl.quarters_of_year(y) if 1 <= x <= tl.Q)
            base = sum(p * c.quarters["vol_ins"][q] for p, c in cw)
            vals.append((sum(p * c.quarters[PHI["insurance"]][q] for p, c in cw) / base,
                         sum(p * c.quarters["ins"][q] for p, c in cw) / base))
        out[name] = (vals[1][0] / vals[0][0], vals[1][1] / vals[0][1])
    return out


def check_drift_bank() -> None:
    """Книга дерева с ключом line (корень множителем): дрейф 2036 / 2029 франшизы к базе — тот же, что у строки, во всех
    мирах и в слое M (1e-9: Φ / INS одинаково в клетках, с 2030 года корней нет); миры расходятся (не все дрейфы 1)."""
    drift = world_drift(bank_line())
    for name, (fr, line) in drift.items():
        assert close(fr, line, 1e-9), (name, fr, line)
    assert max(abs(fr - 1) for fr, _ in drift.values()) > 5e-3, drift


# ------------------------------------------------------------------ входы прохода, память шага, отказы


def check_fingerprint() -> None:
    """Ключ формы, κ, ρ и связь строки при line — входы прохода каждого мира (`path_keys`): полоса по записям не возьмёт
    чужой проход; mixed ≡ без ключа — тот же отпечаток (`check_neutral_fixture`)."""
    run = t8()
    assert P3._moves_every_world(run, t8(None))
    other_k = {**P6.T_KAPPA, "insurance": dict(P6.T_KAPPA["insurance"], **{"2027Q2": -0.031})}
    other_r = {"insurance": dict(P7.T_RHO["insurance"], **{"2027Q2": -0.0151})}
    for alt in (t8(opex__line_share_roots=other_k), t8(volumes__liability_driver_roots=other_r),
                t8(other__insurance_volume_link=0.3), t8(**MULT)):
        assert P3._moves_every_world(alt, run)


def check_memo() -> None:
    """Память оценок шага (фикстура с ключом line, ограничение роста режет рост): сетка с выключенной памятью ≡ с памятью —
    бит в бит (все клетки и ряды); ряды Φ, Ψ и лага D — в STEP_FLOWS и в рядах памяти строк, ряд vol_end_* — нет; проба
    квартала их не оставляет, принятая оценка несёт, повтор оценки той же доли из памяти — те же Ψ, остаток К6 и Φ."""
    import dataclasses

    from model.cell import STEP_FLOWS, _Cell, initial_state, run_cell
    run = t8()
    ctx = run.ctx
    assert ctx.prep.growth is not None and not ctx.prep.memo_off
    off = dataclasses.replace(ctx, prep=dataclasses.replace(ctx.prep, memo_off=True))
    cut = 0
    for c in run.cells:
        d = run_cell(off, c.world, c.regime, c.scenario)
        assert d.v_ri == c.v_ri and d.quarters == c.quarters, c.label
        cut += any((x or 0.0) > 0 for x in c.growth["cut_share"])
    assert cut, "ограничение роста не режет рост — проверка памяти пуста"
    rows = {PHI["insurance"], PHI["fees"], PSI["insurance"], LAG["insurance"]}
    assert rows <= set(STEP_FLOWS) and rows <= set(ctx.prep.line_flows) and not set(END.values()) & set(STEP_FLOWS)
    cell = _Cell(ctx, "M", "downturn", "mid")
    st = initial_state(ctx.prep)
    cell.probe(st, 1)
    assert all(1 not in cell.flows[r] for r in rows), "проба оставила ряды квартала"
    memo: dict = {}
    first, _, kept = cell.evaluate(st, 1, (), 1.0, memo=memo)
    assert rows <= set(kept) and all(1 not in cell.flows[r] for r in rows)
    again = cell.evaluate(st, 1, (), 1.0, memo=memo)[0]
    for name in ("vol_psi_ins", "vol_phi_ins", "vol_end_ins", "opex"):
        assert again[name] == first[name], name
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    assert first["_bal"]["corp_funds"] != fresh["_bal"]["corp_funds"], "доля прироста не сдвигает книгу К6"
    for name in ("vol_psi_ins", "vol_end_ins", "funds", "wholesale"):
        assert second[name] == fresh[name], name
    assert second["_bal"]["corp_funds"] == fresh["_bal"]["corp_funds"]
    cell.accept(1, kept)                         # принята первая оценка, последней была другая доля прироста
    for name in rows:
        assert cell.flows[name][1] == kept[name], name
    assert cell.flows[LAG["insurance"]][1] == first["vol_end_ins"] != fresh["vol_end_ins"], \
        "ряд лага D несёт не принятую оценку шага"


def check_refusals() -> None:
    """Схема: null и значения вне перечня у трёх ключей — отказ; ключ формы при неактивных режимах — не отказ. Нет конца
    истории базы строки-драйвера — FactsError; уровень базы строки-драйвера ≤ 0 — BookError с меткой клетки."""
    from model.book_schema import FactsError
    from model.cell import _Cell, initial_state, k6_line
    S.book_of(volumes__line_link_form="line")
    S.book_of(volumes__line_link_form="mixed", checks__client_funds="clients")
    refused(lambda: S.book_of(volumes__line_link_form=None), "volumes.line_link_form: null в читаемом пути")
    refused(lambda: S.book_of(volumes__line_link_form="chain"), "volumes.line_link_form")
    refused(lambda: S.book_of(checks__client_funds=None), "checks.client_funds: null в читаемом пути")
    refused(lambda: S.book_of(checks__client_funds="funds"), "checks.client_funds")
    gate = {"max": 0.9, "from_year": 2030}
    S.book_of(checks__funds_cost_to_key={**gate, "scope": "world_expectation"})
    refused(lambda: S.book_of(checks__funds_cost_to_key={**gate, "scope": None}), "scope")
    refused(lambda: S.book_of(checks__funds_cost_to_key={**gate, "scope": "layer"}), "scope")
    run = t8()
    ctx = run.ctx
    refused(lambda: k6_line(ctx.book, ctx.prep.driven, ctx.timeline, hist_bal={}, hist_books={}),
            "индекс книг К6 формой строки г/г не определён", FactsError)
    cell = _Cell(ctx, "M", "norm", "mid")
    st = initial_state(ctx.prep)
    e = dict(st.E)
    for b in P3.T_RETAIL:
        e[b] = 0.0
    refused(lambda: cell.drive(st.E, e, 1), "клетка M/norm/mid: уровень базы строки insurance")


# ------------------------------------------------------------------ Р10-6 и ключ (3): гейт мира и средства клиентов


def gate_ref(run: Any, *, clients: bool = False) -> dict[str, dict[str, float]]:
    """Число гейта мира своим счётом: P(r, s | w) = P(r) P(s | r) (апостериорные режимы прогона, таблица книги);
    отношение ожиданий процентов × дни к остаткам × дни книг средств клиентов (`clients` — без книг К6) за годы гейта,
    к средней по дням ключевой мира; рядом модальная клетка. {мир: {ratio, modal}}."""
    ctx = run.ctx
    book, tl = ctx.book, ctx.timeline
    cfg = book.get(GATE)
    years = [y for y in range(max(int(cfg["from_year"]), tl.anchor_year), tl.last_year + 1)
             if all(1 <= q <= tl.Q for q in tl.quarters_of_year(y))]
    qs = [q for y in years for q in tl.quarters_of_year(y)]
    driven = set(map(str, book.opt(DRIVERS) or {})) if clients else set()
    funds = [b for b in ctx.prep.roles.funds if b not in driven]
    table = book.get("joint.reg_prob_given_regime")
    from model.grid import modal_cell
    _, r_m, s_m = modal_cell(book, ctx.posterior)

    def parts(c: Any) -> tuple[float, float]:
        return (sum(c.books[b]["rate"][q] * c.books[b]["avg"][q] * tl.d(q) for q in qs for b in funds),
                sum(c.books[b]["avg"][q] * tl.d(q) for q in qs for b in funds))

    out = {}
    for w in book.get("worlds.ids"):
        key = sum(ctx.worlds[w].key[q] * tl.d(q) for q in qs) / sum(tl.d(q) for q in qs)
        num = den = 0.0
        for c in run.cells:
            if c.world == w:
                p = float(ctx.posterior[c.regime]) * float(table[c.regime][c.scenario])
                i, b = parts(c)
                num, den = num + p * i, den + p * b
        i, b = parts(run.cell(w, r_m, s_m))
        out[str(w)] = {"ratio": num / den / key, "modal": i / b / key}
    return out


def check_gate() -> None:
    """Книга дерева, scope world_expectation: число гейта мира — независимый счёт (1e-12), модальная клетка рядом; узел
    несёт scope; при пороге между модальной клеткой и ожиданием мира M гейт срабатывает только на ожидании (масса — вес
    мира M слоя «свой взгляд»; сообщение называет и модальную клетку); вызов с scope явно — то же число и без ключа книги;
    мир с нулевым весом слоя определён (вероятности внутри мира от весов миров не зависят)."""
    from model.checks import _funds_cost_gate
    from model.levels import funds_cost_to_key, world_probabilities
    run = bank({SCOPE: "world_expectation"})
    ref = gate_ref(run)
    node = funds_cost_to_key(run)
    assert node["scope"] == "world_expectation"
    for w, row in node["by_world"].items():
        assert close(row["ratio"], ref[w]["ratio"], 1e-12) and close(row["modal_ratio"], ref[w]["modal"], 1e-12), w
        assert row["cell"] == f"{w} · ожидание мира" and row["modal_cell"].startswith(f"{w}/")
    assert abs(node["by_world"]["M"]["ratio"] - node["by_world"]["M"]["modal_ratio"]) > 1e-4
    plain = funds_cost_to_key(bank(), scope="world_expectation")
    assert {w: r["ratio"] for w, r in plain["by_world"].items()} == {w: r["ratio"] for w, r in node["by_world"].items()}
    mid = (node["by_world"]["M"]["ratio"] + node["by_world"]["M"]["modal_ratio"]) / 2
    fired = _funds_cost_gate(bank({SCOPE: "world_expectation", f"{GATE}.max": mid}))
    quiet = _funds_cost_gate(bank({f"{GATE}.max": mid}))
    assert fired.fired and not quiet.fired, (fired.message, quiet.message)
    assert fired.mass == run.layers["analytical"].world_weights["M"] and "модальная клетка M/" in fired.message
    probs = world_probabilities(run)
    assert all(close(sum(p.values()), 1.0, 1e-12) for p in probs.values())
    weights = {"N": 0.0, "H": 0.6, "M": 0.4}
    zero = bank({SCOPE: "world_expectation", "joint.world_prob": weights})
    assert zero.layers["analytical"].world_weights["N"] == 0.0
    got = funds_cost_to_key(zero)["by_world"]["N"]
    assert close(got["ratio"], gate_ref(zero)["N"]["ratio"], 1e-12) and got["ratio"] > 0


def check_client_funds() -> None:
    """Ключ (3): clients — книги средств без книги К6 (insurance_liab) в числе funds_cost_to_key (обе области — независимый
    счёт; у одних клиентов модальная клетка = ожиданию мира), в доле опта гейта wholesale_share (порог между долей всех
    средств и долей клиентов — срабатывает только при clients) и в пути фондирования (смесь и модальная клетка — своим
    счётом); all ≡ без ключа (`check_neutral_bank`)."""
    from model.checks import _wholesale_gate
    from model.grid import modal_cell, point_probabilities
    from model.levels import client_funds, funding_path, funds_cost_to_key
    run = bank({CLIENTS: "clients"})
    ctx = run.ctx
    assert B6 in ctx.prep.roles.funds and client_funds(ctx) == tuple(b for b in ctx.prep.roles.funds if b != B6)
    for scope in ("modal_cell", "world_expectation"):
        ref = gate_ref(run, clients=True)
        node = funds_cost_to_key(run, scope=scope)
        for w, row in node["by_world"].items():
            assert close(row["ratio"], ref[w]["ratio" if scope == "world_expectation" else "modal"], 1e-12), (scope, w)
            assert close(ref[w]["ratio"], ref[w]["modal"], 1e-12), w
    tl = ctx.timeline
    ends = [q for q in (tl.quarters_of_year(y)[-1] for y in run.cells[0].years) if 1 <= q <= tl.Q]
    clients = [b for b in ctx.prep.roles.funds if b != B6]

    def share(c: Any, q: int, own: bool) -> float:
        funds = sum(c.books[b]["balance"][q] for b in clients) if own else c.quarters["funds"][q]
        return c.quarters["wholesale"][q] / (funds + c.quarters["wholesale"][q])

    top_all = max(share(c, q, False) for c in run.cells for q in ends)
    top_own = max(share(c, q, True) for c in run.cells for q in ends)
    assert top_own > top_all + 1e-3, (top_own, top_all)
    hi = (top_all + top_own) / 2
    corridor = {"checks.wholesale_share": [0.0, hi]}
    own, every = _wholesale_gate(bank({CLIENTS: "clients", **corridor})), _wholesale_gate(bank(corridor))
    assert own.fired and not every.fired
    assert set(own.cells) == {c.label for c in run.cells if max(share(c, q, True) for q in ends) > hi}
    path = funding_path(run)
    prob = point_probabilities(run)
    cell = run.cell(*modal_cell(ctx.book, ctx.posterior))
    for i, y in enumerate(path["years"]):
        q = tl.quarters_of_year(y)[-1]
        if not 0 <= q <= tl.Q:
            continue
        loans = sum(prob[c.key] * c.quarters["loans"][q] for c in run.cells)
        funds = sum(prob[c.key] * sum(c.books[b]["balance"][q] for b in clients) for c in run.cells)
        wh = sum(prob[c.key] * c.quarters["wholesale"][q] for c in run.cells)
        assert close(path["mix"]["loans_to_funds"][i], loans / funds, 1e-12), y
        assert close(path["mix"]["wholesale_share"][i], wh / (funds + wh), 1e-12), y
        assert close(path["modal_cell"]["wholesale_share"][i], share(cell, q, True), 1e-12), y


# ------------------------------------------------------------------ лист вывода


SHEET = Path("data") / "assumptions" / "evidence" / "path" / "derive_on_engine.py"
SPEC = Path("data") / "assumptions" / "evidence" / "path" / "derive_spec.py"


def _sheet() -> Any:
    """Лист вывода: копия мутанта (каталог запуска проверок), иначе — дерево."""
    from tests.support_book import load_module
    here = Path.cwd() / SHEET
    return load_module(here if here.exists() else ROOT / SHEET, "sheet_derive_on_engine_p8")


def _eng() -> Any:
    from model import levels
    return SimpleNamespace(levels=levels, overrides={}, book=None)


def check_sheet_roots() -> None:
    """Лист: на сетке с ключом line kappa_of и rho_of — правило формы строки (`line_rule` своим счётом: κ и ρ до единицы
    шестого знака; невязки слоя M — по рядам Φ и Ψ ядра, 1e-12); на книге без ключа — прежние правила (κ — уровни, ρ —
    квартальная цепь) отличаются от формы строки больше, чем на 1e-3."""
    sheet = _sheet()
    sheet.QUIET[0] = True
    eng = _eng()
    for run in (bank_line(**tree_scope()), t8(**MULT), t8()):          # книга дерева — на своих средствах клиентов (круг 11)
        kap, rho = rules(run)
        got_k, dev_k = sheet.kappa_of(eng, run, "insurance")
        got_r, dev_r, jen = sheet.rho_of(eng, run, "insurance")
        assert _shift(kap, got_k) <= 1.0001e-6 and _shift(rho, got_r) <= 1.0001e-6, (got_k, kap, got_r, rho)
        prep, tl = run.ctx.prep, run.ctx.timeline
        layer = _layer(run)
        a0 = P6._base_hist(prep, "insurance")[0]
        d0 = prep.k6_line["insurance"][2].end0
        want_k = max(abs(sum(p * c.quarters[PHI["insurance"]][q] for p, c in layer)
                         - sum(p * c.quarters["vol_ins"][q] for p, c in layer) / a0) for q in range(1, tl.index(Q_END) + 1))
        want_r = max(abs(sum(p * c.quarters[PSI["insurance"]][q] for p, c in layer)
                         - sum(p * c.quarters["vol_end_ins"][q] for p, c in layer) / d0) for q in range(1, tl.index(Q_END) + 1))
        assert close(dev_k, want_k, 1e-9, 1e-15) and close(dev_r, want_r, 1e-9, 1e-15), (dev_k, dev_r)
        if run.ctx.prep.k6_line["insurance"][2].kind == "books" and run.ctx.book.opt(KAPPA)["insurance"] == line_roots()[0]:
            assert jen <= 1e-4, jen                   # книга дерева у неподвижной точки: книга К6 против базы — округление
    plain = bank()
    lk, _ = sheet.kappa_of(eng, plain, "insurance")
    lr, _, _ = sheet.rho_of(eng, plain, "insurance")
    kap, rho = rules(bank_line(plain.ctx.book.get(KAPPA)["insurance"], plain.ctx.book.get(RHO)["insurance"]))
    assert _shift(kap, lk) > 1e-3 and _shift(rho, lr) > 1e-3


def _spec_line() -> Any:
    """Описание записи листа (derive_spec): как в дереве (шаблон без ключа формы) и при форме строки в шаблоне — тот же
    исходный текст, где чтение ключа шаблона заменено на line."""
    import sys
    import types

    from tests.support_book import load_module
    here = Path.cwd() / SPEC
    path = here if here.exists() else ROOT / SPEC
    load_module(path, "sheet_derive_spec_p8")                 # как в дереве — описание читается без отказа
    src = path.read_text(encoding="utf-8")
    old = '_LINK_LINE = _template_value(sheet.LINK_FORM) == "line"'
    assert old in src, "ключ формы в описании записи не читается"

    def form(flag: bool) -> Any:
        """Описание с формой, заданной явно (шаблон дерева может уже нести форму строки — интеграция круга 10)."""
        mod = types.ModuleType(f"sheet_derive_spec_p8_{'line' if flag else 'plain'}")
        mod.__file__ = str(path)
        sys.path.insert(0, str(path.parent))
        keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            exec(compile(src.replace(old, f"_LINK_LINE = {flag}"), str(path), "exec"), mod.__dict__)
        finally:
            sys.dont_write_bytecode = keep
            sys.path.remove(str(path.parent))
        return mod

    return form(False), form(True)


def check_sheet_spec() -> None:
    """Описание записи листа: коридор ρ по форме — line −0,30…+0,20 (корень г/г, как κ) у центра и у концов связок, без
    ключа — прежний квартальный −0,085…+0,045; Р10-13 — у концов связок две записи приёмки невязки уровня (κ и ρ) с допуском
    1e-4 рядом с правилом против записи (5e-5)."""
    plain, line = _spec_line()
    assert (plain._RHO[-1][1], plain._RHO[-1][2]) == (-0.085, 0.045) and plain._RHO_END[1:3] == (-0.085, 0.045)
    assert (line._RHO[-1][1], line._RHO[-1][2]) == (-0.30, 0.20) and line._RHO_END[1:3] == (-0.30, 0.20)
    assert line._KAPPA[-1][1:3] == plain._KAPPA[-1][1:3] == (-0.30, 0.20)
    sheet = _sheet()
    assert sheet.LEVEL_END_TOL == 1e-4 and sheet.KAPPA_END_TOL == 5e-5
    for mod in (plain, line):
        res = {r["value"]: r["tol"] for r in mod.RESIDUALS if r.get("value", ("",))[0] == "ends"}
        if mod._SHARE_ROOTS:
            assert res[("ends", "kappa_ends", "max_dev_max")] == 1e-4 and res[("ends", "kappa_ends", "rule_change_max")] == 5e-5
        if mod._DRIVER_ROOTS:
            assert res[("ends", "rho_ends", "max_dev_max")] == 1e-4 and res[("ends", "rho_ends", "rule_change_max")] == 5e-5


def check_sheet_ends() -> None:
    """Р10-13 на концах связок: ok κ и ρ — оба числа в допусках (правило против записи ≤ 5e-5 и невязка уровня ≤ 1e-4);
    невязка выше допуска при малом правиле — не ok; печать несёт оба числа."""
    sheet = _sheet()
    sheet.QUIET[0] = True

    def run(rc: float, md: float) -> dict:
        row = {"axis": "a", "end": "low", "line": "insurance", "carried": True, "rule_change": rc, "max_dev": md}
        eng = SimpleNamespace(kappa_ends={("a", "low", "insurance"): dict(row)},
                              rho_ends={("a", "low", "insurance"): dict(row, jensen=0.0)}, link_line=True)
        out: dict = {"ends": {}}
        sheet.ends_kappa_check(eng, out)
        return out["ends"]

    good, level, rule = run(3e-5, 5e-5), run(1e-5, 2e-4), run(6e-5, 1e-5)
    for name in ("kappa_ends", "rho_ends"):
        assert good[name]["ok"] and not level[name]["ok"] and not rule[name]["ok"], name
        assert good[name]["max_dev_max"] == 5e-5 and good[name]["level_tol"] == 1e-4 and good[name]["tol"] == 5e-5


def check_sheet_phi_axis() -> None:
    """Низ оси φ: лист судит число гейта ядра — funds_cost_to_key(run, scope="world_expectation") — и своей формулы не
    держит (заглушка ядра: отношение линейно по доле φ; низ — шаг 0,01 над корнем). Порог — правило листа на величине числа
    гейта ядра (решения № 10, Р10-1, Р10-16; поток book10, слит при интеграции круга 10): средства ядра с К6 — 0,870,
    средства клиентов (ключ checks.client_funds: clients) — 0,876; порог книги лист не читает."""
    sheet = _sheet()
    sheet.QUIET[0] = True
    for clients, low in ((None, 0.34), ("clients", 0.32)):     # корень 0,97 − 0,3 φ = порог: 0,3333 → 0,34; 0,3133 → 0,32
        calls: list = []

        def gate(run: Any, scope: Any = None, calls=calls) -> dict:
            calls.append(scope)
            return {"by_world": {"N": {"ratio": 0.5}, "M": {"ratio": 0.97 - 0.3 * run}}}

        def opt(p: str, clients=clients) -> Any:
            return clients if p == sheet.CLIENT_FUNDS_KEY else {"max": 0.86, "from_year": 2030}

        eng = SimpleNamespace(value=lambda p: 0.6, grid=lambda extra: extra["nii.phi_split"],
                              current=lambda opt=opt: SimpleNamespace(opt=opt),
                              levels=SimpleNamespace(WORLD_EXPECTATION="world_expectation", funds_cost_to_key=gate))
        out = {"splits": {"axis_phi": [0.30, 0.72]}, "ends": {}}
        sheet.ends_phi_axis(eng, out)
        assert calls and set(calls) == {"world_expectation"}, calls
        assert out["splits"]["axis_phi"] == [low, 0.72], (clients, out["splits"]["axis_phi"])
        assert out["ends"]["funds_cost_gate"]["max"] == sheet.FUNDS_COST_MAX["clients" if clients else "all"]


# ------------------------------------------------------------------ выпуск


def check_release_with_pass8_keys() -> None:
    """Выпуск фикстуры с тремя ключами прохода 8 (форма строки при франшизах и К6, гейт на ожидании мира, средства клиентов
    без К6): контракт выполнен; узел гейта несёт scope и модальную клетку рядом; ряды vol_phi_*, vol_psi_* — в клетках."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    data = t_dict()
    changes = {"valuation__terminal__fixed_growth_share": 0.0, "checks__mix_ratio_tolerance": 0.002, **T_KEYS,
               "volumes__line_link_form": "line", "checks__funds_cost_to_key": {"max": 2.0, "from_year": 2030,
                                                                               "scope": "world_expectation"},
               "checks__client_funds": "clients"}
    for k, v in changes.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    run = run_grid(book, facts)
    assert run.ctx.prep.link_line and run.ctx.prep.k6_line is not None
    expl = explained(check_gates(run, today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    assert contract(d) == [], contract(d)[:5]
    node = d["checks"]["funds_cost_to_key"]
    assert node["scope"] == "world_expectation" and all("modal_cell" in r for r in node["by_world"].values())
    for c in rel.run.cells:
        assert {"vol_phi_ins", "vol_phi_fees", "vol_psi_ins", "vol_end_ins"} <= set(c.quarters)
