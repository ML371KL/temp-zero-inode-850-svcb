"""Проверки шестого прохода ядра Совкомбанка (core-pass6): франшиза строки в смеси базы расходов — за связью строки
(Р8-6, М§4.7; ключ `opex.line_share_roots` {fees, insurance → траектория κ}, необязательный).

Форма: Φ^ℓ_q = λ_ℓ A^ℓ_q / A^ℓ_0 + (1 − λ_ℓ) H^ℓ_q, H^ℓ_q = H^ℓ_(q−4) (1 + wage_W,q)(1 + κ_q), H^ℓ_x = A^ℓ_x / A^ℓ_0 при
x ≤ 0; смесь базы расходов A^C_q = (1 − Σ s) B^C_q + Σ s_ℓ B^C_0 Φ^ℓ_q (история смеси и квартал якоря — прежние); λ_ℓ —
связь самой строки; κ — корень номинальной части, общий для миров: лист выводит его так, что в слое «рыночные ставки
как есть» номинальная часть до 2029К4 идёт за базой строки (κ_q = E_M[A_q] / E_M[A_(q−4)] / (1 + w^M_q) − 1), дальше 0.

Одни и те же проверки зовут тесты (`tests/test_core_p6.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass6/example.json` — копия выхода
`example.py` агента методики, notes/core-pass6; κ примера — `tests/fixtures/core_pass6/book_keys_pass6.yaml`),
выведенные из книги и фактов независимо от кода ядра. Ключа в книгах фикстур и в книге дерева нет (нет ключа — прежняя
ветвь кода, бит в бит): проверки включают его подменой. Базы строк, их история (К2) и история базы расходов (М13)
берутся из подготовки ядра — их держат проверки проходов 1–3; здесь судится только новое: H, Φ, смесь и расходы.
"""

from __future__ import annotations

import copy
import functools
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from tests import support_core_p3 as P3
from tests import support_core_p4 as P4
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "core_pass6"
EXAMPLE, BOOK_KEYS = FIXTURE / "example.json", FIXTURE / "book_keys_pass6.yaml"
close = S.close
refused = P3.refused
KEY, SHARES = "opex.line_share_roots", "opex.line_shares"
LINK = {"fees": "fees.volume_link", "insurance": "other.insurance_volume_link"}
SERIES = {"fees": "vol_fees", "insurance": "vol_ins"}          # база строки — ряд клетки (К2)
NOMINAL = {"fees": "vol_nom_fees", "insurance": "vol_nom_ins"}  # номинальная часть франшизы H^ℓ — ряд клетки (Р8-6)
Q_END, LT_FROM = "2029Q4", 2030                                # корень κ — до 2029К4, дальше 0 (правило листа)
MACRO = "macro_neutral"                                        # слой «рыночные ставки как есть» (слой M)
# фикстура `core_t` (связи 0,5 / 0,5 / 0,4, link_base — кредиты) на фактах с историей книг: база комиссий — средства
# клиентов, страхования — розничные кредитные книги; доли франшиз 0,2 / 0,15
T_BASES = {"fees__volume_base": "funds", "other__insurance_volume_base": P3.T_RETAIL}
T_SHARES = {"fees": 0.2, "insurance": 0.15}
# κ фикстуры: кварталы до LT_from явно (чтение проверки — ключ квартала или LT), у комиссий — число
T_KAPPA = {"insurance": {"2026Q3": -0.04, "2026Q4": -0.06, "2027Q1": -0.05, "2027Q2": -0.03, "2027Q3": 0.02,
                         "2027Q4": -0.01, "LT": 0.0, "LT_from": 2028},
           "fees": 0.01}
EX_BASE_POINT = 17.169831269292906           # точка книги примера без ключа (p3 @ 48f3ca2)


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (ключ core6-spec): formula — формулы точными дробями; core — сводка прототипа."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def bank_kappa() -> dict[str, Any]:
    """κ примера (неподвижная точка методики на книге p3 @ 48f3ca2) — траектория из фрагмента книги прохода."""
    import yaml
    return yaml.safe_load(BOOK_KEYS.read_text(encoding="utf-8"))["opex"]["line_share_roots"]["insurance"]


def t6(*, roots: Any = None, shares: Any = T_SHARES, **changes: Any) -> Any:
    """Сетка фикстуры `core_t` с базами строк `T_BASES`, долями франшиз `shares` и ключом `roots` (None — без ключа)."""
    kw: dict[str, Any] = dict(T_BASES)
    kw["opex__line_shares"] = shares
    if roots is not None:
        kw["opex__line_share_roots"] = roots
    kw.update(changes)
    return P3.mix_run(**kw)


def bank(roots: Any = None, **paths: Any) -> Any:
    """Сетка книги дерева с ключом `roots` (None — без ключа) и подменами точечных путей (`__` вместо точки). Книга —
    без ключа Р8-6 и без путей κ в осях (`_bank_data`), даже если поток книги их уже поставил: «без ключа» — без него."""
    changes = [(k.replace("__", "."), json.dumps(v)) for k, v in paths.items()]
    if roots is not None:
        changes.append((KEY, json.dumps(roots)))
    return _bank_run(tuple(sorted(changes)))


def strip_later_passes(out: dict) -> None:
    """Ключи проходов 8 и 9, которыми книга дерева сменила форму прохода 6 (интеграция кругов 10–11; то же снимают
    проверки проходов 7 и 8 — `support_core_p7._bank_data`, `support_core_p8._bank_data`): форма строки
    `volumes.line_link_form: line` (Р10-5 — франшиза Φ^ℓ формой строки вместо H^ℓ: ряда vol_nom_* нет, и при связи 1 κ
    двигает франшизу), книги средств клиентов в числах гейтов `checks.client_funds` и область гейта стоимости средств
    `checks.funds_cost_to_key.scope`; ключ прохода 9 `volumes.funds_scope` схема пускает только вместе с
    `checks.client_funds: clients` — снимается и он, с вариантами на его пути. Без них книга дерева идёт формой прохода 6
    (mixed), которую проход 6 и судит; форму строки судят проверки прохода 8."""
    vol, checks = out.get("volumes") or {}, out.get("checks") or {}
    vol.pop("line_link_form", None)
    checks.pop("client_funds", None)
    (checks.get("funds_cost_to_key") or {}).pop("scope", None)
    vol.pop("funds_scope", None)
    val = out.get("valuation", {})
    if isinstance(val.get("reference_variants"), list):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(str(k) == "volumes.funds_scope" for k in (v.get("overrides") or {}))]


@functools.lru_cache(maxsize=None)
def _bank_data() -> dict[str, Any]:
    """Исходный словарь книги дерева без ключа `opex.line_share_roots` и без его путей в осях-связках (κ на концах осей
    ставит поток книги вместе с ключом), в форме прохода 6 — без ключей проходов 8 и 9 (`strip_later_passes`). Книга без
    ключа — та же, что книга дерева до потока (бит в бит)."""
    _, data = P4._real_book()
    out = copy.deepcopy(data)
    (out.get("opex") or {}).pop("line_share_roots", None)
    strip_later_passes(out)
    for ax in out.get("valuation", {}).get("uncertainty", {}).get("axes", []):
        if any(str(p).startswith(KEY + ".") for p in ax.get("paths", [])):
            ax["paths"] = [p for p in ax["paths"] if not str(p).startswith(KEY + ".")]
            for end in ("low", "high"):
                if isinstance(ax.get(end), dict):
                    ax[end] = {k: v for k, v in ax[end].items() if not str(k).startswith(KEY + ".")}
    return out


@functools.lru_cache(maxsize=None)
def _bank_run(changes: tuple = ()) -> Any:
    """Сетка книги `_bank_data` с подменами точечных путей `changes` ((путь, JSON значения), …)."""
    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    from model.paths import set_path
    data = copy.deepcopy(_bank_data())
    for dotted, value in changes:
        set_path(data, dotted, json.loads(value))
    facts = P4._real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts))


def kappa_ref(traj: Any, tl: Any) -> list[float | None]:
    """κ_q, q = 0…Q, заново по записи траектории теста: число — на все кварталы; словарь — ключ квартала, с года LT_from
    — LT (квартал без ключа до LT_from — ошибка записи теста). q = 0 (якорь) не читается — None."""
    if not isinstance(traj, dict):
        return [None] + [float(traj)] * tl.Q
    out: list[float | None] = [None]
    for q in range(1, tl.Q + 1):
        per = tl.period(q)
        if per in traj:
            out.append(float(traj[per]))
        else:
            assert tl.year(q) >= int(traj["LT_from"]), f"в траектории теста нет квартала {per}"
            out.append(float(traj["LT"]))
    return out


def _base_hist(prep: Any, line: str) -> dict[int, float]:
    """A^ℓ_x, x ≤ 0 — история базы строки ядра (свой ключ К2 или link_base)."""
    own = prep.fees_line if line == "fees" else prep.ins_line
    return dict(own.hist) if own is not None else dict(prep.hist_vol)


def _same(a: Any, b: Any, extra: frozenset[str] = frozenset()) -> None:
    """Две сетки — бит в бит: точка, слои, стоимость клеток и все ряды кварталов `b`; у `a` сверх них — ровно `extra`."""
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high), (a.point, b.point)
    for x, y in zip(a.cells, b.cells):
        assert x.key == y.key and x.v_ri == y.v_ri and x.v_ddm == y.v_ddm, (x.label, x.v_ri, y.v_ri)
        assert set(x.quarters) == set(y.quarters) | extra, (x.label, set(x.quarters) ^ set(y.quarters))
        for name, series in y.quarters.items():
            assert x.quarters[name] == series, (x.label, name)


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def check_neutral() -> None:
    """Фикстура: пустой словарь ≡ без ключа (и отпечаток прохода тот же); доля строки 0 (нет или 0) и связь расходов 0 —
    ключ не читается, бит в бит с книгой без ключа; связь строк 1 с ключом ≡ без ключа (точка, клетки, все ряды; ряды
    vol_nom_* — только при ключе); без ключа рядов H нет."""
    base = t6()
    assert base.ctx.prep.share_nominal is None and base.ctx.prep.hist_share_nominal == {}
    assert not {"vol_nom_fees", "vol_nom_ins"} & set(base.cells[0].quarters)
    empty = t6(roots={})
    _same(empty, base)
    assert P3._path_key(empty) == P3._path_key(base)
    keyed = t6(roots=T_KAPPA)
    assert set(keyed.ctx.prep.share_nominal) == {"fees", "insurance"} and abs(keyed.point - base.point) > 1e-6
    from model.grid import run_grid                 # справочный вариант {opex.line_share_roots: {}} подменой книги с ключом
    from tests.support_core_t import book_live
    variant = keyed.ctx.book.with_overrides({KEY: {}})
    _same(run_grid(variant, keyed.ctx.facts, book_live(variant)), base)
    for shares in ({"fees": 0.2}, {"fees": 0.2, "insurance": 0.0}):
        off = t6(roots={"insurance": T_KAPPA["insurance"]}, shares=shares)
        assert off.ctx.prep.share_nominal is None, shares
        _same(off, t6(shares=shares))
    only_fees = t6(roots=T_KAPPA, shares={"fees": 0.2})
    assert set(only_fees.ctx.prep.share_nominal) == {"fees"} and "vol_nom_ins" not in only_fees.cells[0].quarters
    off = t6(roots=T_KAPPA, opex__volume_link=0.0)
    assert off.ctx.prep.share_nominal is None
    _same(off, t6(opex__volume_link=0.0))
    ones = {"fees__volume_link": 1.0, "other__insurance_volume_link": 1.0}
    one, plain = t6(roots=T_KAPPA, **ones), t6(**ones)
    assert one.ctx.prep.share_nominal["insurance"][0] == 1.0
    _same(one, plain, extra=frozenset(NOMINAL.values()))


def check_neutral_bank() -> None:
    """Книга дерева: пустой словарь ≡ без ключа; κ примера при связи страхования 1 ≡ связь 1 без ключа (все клетки и
    ряды); доля франшизы страхования 0 и связь расходов 0 — ключ не читается (бит в бит)."""
    base = bank()
    assert base.ctx.prep.share_nominal is None
    _same(bank({}), base)
    kap = {"insurance": bank_kappa()}
    _same(bank(kap, other__insurance_volume_link=1.0), bank(other__insurance_volume_link=1.0),
          extra=frozenset({"vol_nom_ins"}))
    off = bank(kap, opex__line_shares__insurance=0.0)
    assert off.ctx.prep.share_nominal is None
    _same(off, bank(opex__line_shares__insurance=0.0))
    off = bank(kap, opex__volume_link=0.0)
    assert off.ctx.prep.share_nominal is None
    _same(off, bank(opex__volume_link=0.0))


# ------------------------------------------------------------------ пример методики (формулы точными дробями)


def _fr(s: str) -> Fraction:
    return Fraction(s)


def check_example() -> None:
    """Пример Р8-6 (formula): по входам примера заново — H (история A / A_0, рекурсия г/г с корнем), Φ = λ A / A_0 +
    (1 − λ) H, смесь A^C и её рост г/г, смесь без ключа — точными дробями, равны числам примера; на якоре ступени нет,
    история смеси прежняя; связь 1 — смесь прежняя; связь 0 — Φ = H; κ правилом (рост базы к росту зарплат) — H = Φ =
    A / A_0. Книга дерева — книга примера (точка без ключа — число примера): точка с κ примера — число примера бит в бит."""
    ex = example()["formula"]
    inp = ex["inputs"]
    a = {int(x): _fr(v) for x, v in inp["A_I"].items()}
    b = {int(x): _fr(v) for x, v in inp["B_C"].items()}
    f = {int(x): _fr(v) for x, v in inp["A_F"].items()}
    w = {int(q): _fr(v) for q, v in inp["wage"].items()}
    s_f, s_i = _fr(inp["s_F"]), _fr(inp["s_I"])
    keep, a0, b0, f0 = 1 - s_f - s_i, a[0], b[0], f[0]
    rule = {q: a[q] / a[q - 4] / (1 + w[q]) - 1 for q in range(1, 9)}
    assert len(ex["cases"]) == 5
    seen = set()
    for name, case in ex["cases"].items():
        lam = _fr(case["lambda"])
        kap = {int(q): _fr(v) for q, v in case["kappa"].items()}
        h = {x: a[x] / a0 for x in range(-3, 1)}
        for q in range(1, 9):
            h[q] = h[q - 4] * (1 + w[q]) * (1 + kap[q])
        phi = {x: a[x] / a0 for x in range(-3, 1)}
        phi.update({q: lam * a[q] / a0 + (1 - lam) * h[q] for q in range(1, 9)})
        mix = {x: keep * b[x] + s_f * b0 * f[x] / f0 + s_i * b0 * phi[x] for x in range(-3, 9)}
        old = {x: keep * b[x] + s_f * b0 * f[x] / f0 + s_i * b0 * a[x] / a0 for x in range(-3, 9)}
        for field, want in (("H", h), ("Phi", phi), ("A_C", mix), ("A_C_without_key", old)):
            assert {int(x): _fr(v) for x, v in case[field].items()} == want, (name, field)
        assert {int(q): _fr(v) for q, v in case["A_C_growth"].items()} == {q: mix[q] / mix[q - 4] - 1
                                                                            for q in range(1, 9)}, name
        assert mix[0] == b0 and all(mix[x] == old[x] for x in range(-3, 1)), name
        if lam == 1:
            assert mix == old, name
            seen.add("lam1")
        if lam == 0:
            assert all(phi[q] == h[q] for q in range(1, 9)), name
            seen.add("lam0")
        if kap == rule:
            assert all(h[q] == phi[q] == a[q] / a0 for q in range(1, 9)), name
            seen.add("rule")
        elif lam not in (0, 1):
            assert any(mix[q] != old[q] for q in range(1, 9)), name
            seen.add("moves")
    assert seen == {"lam1", "lam0", "rule", "moves"}, seen
    core = example()["core"]
    if bank().point == EX_BASE_POINT:
        assert bank({"insurance": bank_kappa()}).point == core["point"]


# ------------------------------------------------------------------ ядро против формулы в каждой клетке и квартале


def check_cells(run: Any, roots: dict[str, Any]) -> int:
    """Каждая клетка и квартал сетки `run` с ключом `roots`: H^ℓ — формулой заново (история A^ℓ_x / A^ℓ_0 и рекурсия г/г
    с зарплатами мира клетки и κ записи, 1e-12) и рекурсией по ряду клетки ровно (q > 4); история H подготовки — A_x /
    A_0 ровно; Φ^ℓ = λ_ℓ A^ℓ / A^ℓ_0 + (1 − λ_ℓ) H^ℓ; смесь A^C = (1 − Σ s) B^C + Σ s_ℓ B^C_0 Φ^ℓ (B^C — веса М13 по
    средним книг или link_base «кредиты») — ряд vol_opex (1e-12); расходы — прежняя формула роста по смеси (1e-12).
    Возвращает число сверенных кварталов."""
    ctx = run.ctx
    tl, prep, book = ctx.timeline, ctx.prep, ctx.book
    shares = {k: float(v) for k, v in (book.opt(SHARES) or {}).items() if float(v) > 0}
    keep = 1.0 - sum(shares.values())
    l_c = float(book.get("opex.volume_link"))
    hist = {line: _base_hist(prep, line) for line in shares}
    kap = {line: kappa_ref(roots[line], tl) for line in shares if line in roots}
    lam = {line: float(book.get(LINK[line])) for line in shares}
    assert set(prep.share_nominal or {}) == set(kap)
    for line in kap:
        assert prep.hist_share_nominal[NOMINAL[line]] == {x: hist[line][x] / hist[line][0] for x in range(-3, 1)}
    if prep.opex_w is None:
        assert prep.link_base == "loans"
        b_hist = prep.hist_vol
    else:
        b_hist = prep.hist_vol_opex
    b0 = b_hist[0]
    n = 0
    for c in run.cells:
        qs = c.quarters
        wage = ctx.worlds[c.world].wage
        h = {line: {x: hist[line][x] / hist[line][0] for x in range(-3, 1)} for line in kap}
        mix = {x: keep * b_hist[x] + sum(s * b0 * hist[line][x] / hist[line][0] for line, s in shares.items())
               for x in range(-3, 1)}
        opex = {x: prep.hist["opex"][x] for x in range(-3, 1)}
        for line in kap:
            assert qs[NOMINAL[line]][0] is None, c.label
        for q in range(1, tl.Q + 1):
            if prep.opex_w is None:
                b_q = (qs["loans"][q - 1] + qs["loans"][q]) / 2
            else:
                b_q = sum(wb * c.books[bk]["avg"][q] for bk, wb in prep.opex_w.items())
            a_c = keep * b_q
            for line, s in shares.items():
                if SERIES[line] in qs:          # своя база строки (К2)
                    a = qs[SERIES[line]][q] / hist[line][0]
                else:                           # база link_base «кредиты»: полусумма концов квартала
                    assert prep.link_base == "loans"
                    a = (qs["loans"][q - 1] + qs["loans"][q]) / 2 / hist[line][0]
                if line in kap:
                    h[line][q] = h[line][q - 4] * (1 + wage[q]) * (1 + kap[line][q])
                    got = qs[NOMINAL[line]][q]
                    assert close(got, h[line][q], 1e-12), (c.label, line, q, got, h[line][q])
                    if q > 4:
                        assert got == qs[NOMINAL[line]][q - 4] * (1 + wage[q]) * (1 + kap[line][q]), (c.label, line, q)
                    phi = lam[line] * a + (1 - lam[line]) * h[line][q]
                else:
                    phi = a
                a_c += s * b0 * phi
            mix[q] = a_c
            assert close(qs["vol_opex"][q], a_c, 1e-12), (c.label, q, qs["vol_opex"][q], a_c)
            want = opex[q - 4] * (1 + wage[q] + l_c * (a_c / mix[q - 4] - 1 - wage[q])) * (1 + prep.opex_real[q])
            assert close(qs["opex"][q], want, 1e-12), (c.label, q, qs["opex"][q], want)
            opex[q] = qs["opex"][q]
            n += 1
    return n


def check_grid() -> None:
    """Фикстура с ключом у обеих строк (связи 0,5): ядро против формулы в каждой клетке и квартале; ключ двигает
    стоимость клеток, лёгкая сетка (проходы полосы) — те же оценки; связь страхования 0 — Φ = H (формула с λ = 0) и 0,3;
    κ = 0 (LT) — та же формула; строка без своей базы (комиссии на link_base) — H и Φ на базе link_base."""
    keyed = t6(roots=T_KAPPA)
    assert check_cells(keyed, T_KAPPA) == 36 * keyed.ctx.timeline.Q
    base = t6()
    assert sum(abs(c.v_ri - b.v_ri) > 1e-6 for c, b in zip(keyed.cells, base.cells)) > 30
    from model.grid import run_grid                 # лёгкая сетка (проходы полосы) — те же оценки
    from tests.support_core_t import book_live
    light = run_grid(keyed.ctx.book, keyed.ctx.facts, book_live(keyed.ctx.book), summary=True)
    assert light.point == keyed.point and [c.v_ri for c in light.cells] == [c.v_ri for c in keyed.cells]
    for link in (0.0, 0.3):
        check_cells(t6(roots=T_KAPPA, other__insurance_volume_link=link), T_KAPPA)
    zero = {"insurance": {"LT": 0.0, "LT_from": 2027, "2026Q3": 0.0, "2026Q4": 0.0}}
    check_cells(t6(roots=zero), zero)
    plain_fees = P3.mix_run(other__insurance_volume_base=P3.T_RETAIL, opex__line_shares=T_SHARES,
                            opex__line_share_roots=T_KAPPA)     # комиссии без своей базы — на link_base
    assert plain_fees.ctx.prep.fees_line is None and set(plain_fees.ctx.prep.share_nominal) == {"fees", "insurance"}
    check_cells(plain_fees, T_KAPPA)


def check_grid_bank() -> None:
    """Книга дерева (форма прохода 6) с κ примера (связь страхования и доли франшиз — книги дерева, веса М13): ядро против
    формулы в каждой клетке и квартале (смесь по рядам vol_ins, vol_nom_ins, vol_fees и средним книг)."""
    kap = {"insurance": bank_kappa()}
    run = bank(kap)
    assert run.ctx.prep.opex_w is not None and set(run.ctx.prep.share_nominal) == {"insurance"}
    assert check_cells(run, kap) == 36 * run.ctx.timeline.Q


def check_continuity() -> None:
    """Непрерывность по связи строки (фикстура): точка при λ = 0 и 1e-9, 1 − 1e-9 и 1 — до 1e-8 относительно."""
    for a, b in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
        x = t6(roots=T_KAPPA, other__insurance_volume_link=a).point
        y = t6(roots=T_KAPPA, other__insurance_volume_link=b).point
        assert close(x, y, 1e-8), (a, b, x, y)


# ------------------------------------------------------------------ слой M: неподвижная точка κ и миры


def kappa_rule(run: Any, line: str = "insurance") -> dict[str, Any]:
    """κ правилом листа на сетке `run`: κ_q = E_M[A_q] / E_M[A_(q−4)] / (1 + w^M_q) − 1, q = 1…2029К4 (E_M[A_x], x ≤ 0 —
    история базы), 6 знаков; с 2030 года 0. E_M — ожидание ряда клеток под вероятностями слоя M."""
    ctx = run.ctx
    tl = ctx.timeline
    prob = run.layers[MACRO].prob
    wage = ctx.worlds[str(ctx.book.get("joint.macro_neutral_world"))].wage
    em = _base_hist(ctx.prep, line)
    for q in range(1, tl.Q + 1):
        em[q] = sum(prob[c.key] * c.quarters[SERIES[line]][q] for c in run.cells)
    out: dict[str, Any] = {"LT": 0.0, "LT_from": LT_FROM}
    for q in range(1, tl.index(Q_END) + 1):
        out[tl.period(q)] = round(em[q] / em[q - 4] / (1 + wage[q]) - 1, 6)
    return out


def fixed_point(make: Any, rounds: int = 5) -> tuple[Any, dict[str, Any], list[float]]:
    """Неподвижная точка κ (как лист вывода): κ = 0 → сетка с ключом → κ правилом → … `rounds` кругов; сетка последнего
    κ, κ и сдвиги кругов."""
    traj: dict[str, Any] = {"LT": 0.0, "LT_from": LT_FROM}
    shifts = []
    for _ in range(rounds):
        new = kappa_rule(make(traj))
        shifts.append(max(abs(v - traj.get(k, 0.0)) for k, v in new.items() if k not in ("LT", "LT_from")))
        traj = new
    return make(traj), traj, shifts


def check_layer_m(run: Any, traj: dict[str, Any], shifts: list[float]) -> None:
    """Слой M на неподвижной точке κ: сдвиги кругов убывают, последний ≤ 1e-5; E_M[H_q] = E_M[A_q] / A_0 до 2029К4 (1e-5;
    κ записан 6 знаками) и E_M[Φ_q] = E_M[A_q] / A_0 так же; H всех клеток слоя M одна (общий корень и зарплаты мира);
    с 2030 года в каждой клетке H_q = H_(q−4) (1 + wage мира) ровно (κ = 0)."""
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    assert all(b <= a for a, b in zip(shifts, shifts[1:])) and shifts[-1] <= 1e-5, shifts
    prob = run.layers[MACRO].prob
    lam, a0 = prep.share_nominal["insurance"][0], _base_hist(prep, "insurance")[0]
    q_end = tl.index(Q_END)
    worst = 0.0
    for q in range(1, q_end + 1):
        e_h = sum(prob[c.key] * c.quarters["vol_nom_ins"][q] for c in run.cells)
        e_a = sum(prob[c.key] * c.quarters["vol_ins"][q] for c in run.cells) / a0
        worst = max(worst, abs(e_h - e_a), abs(lam * e_a + (1 - lam) * e_h - e_a))
        assert len({c.quarters["vol_nom_ins"][q] for c in run.cells if prob[c.key] > 0}) == 1, q
    assert worst <= 1e-5, worst
    assert kappa_ref(traj, tl)[q_end + 1:] == [0.0] * (tl.Q - q_end)
    for c in run.cells:
        wage = ctx.worlds[c.world].wage
        for q in range(q_end + 1, tl.Q + 1):
            assert c.quarters["vol_nom_ins"][q] == c.quarters["vol_nom_ins"][q - 4] * (1 + wage[q]), (c.label, q)


def world_relations(run: Any, years: tuple[int, ...] = (2029, 2036)) -> dict[tuple[int, str], tuple[float, float]]:
    """Миры относительно слоя M (средние года, веса аналитического слоя внутри мира): франшиза — уровень Φ / (A / A_0)
    мира к тому же слоя M; строка — INS / A мира к тому же слоя M. {(год, мир): (франшиза, строка)}."""
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    lam, _, name = prep.share_nominal["insurance"]
    a0 = _base_hist(prep, "insurance")[0]
    la = run.layers["analytical"]
    groups = {MACRO: [(c, run.layers[MACRO].prob[c.key]) for c in run.cells]}
    for w in la.world_weights:
        groups[w] = [(c, la.prob[c.key] / la.world_weights[w]) for c in run.cells if c.world == w]
    out = {}
    for y in years:
        qs = [q for q in tl.quarters_of_year(y) if 1 <= q <= tl.Q]
        lvl, line = {}, {}
        for g, cw in groups.items():
            fr = sum(wt * (lam * c.quarters["vol_ins"][q] / a0 + (1 - lam) * c.quarters[name][q]) for c, wt in cw
                     for q in qs)
            base = sum(wt * c.quarters["vol_ins"][q] / a0 for c, wt in cw for q in qs)
            ins = sum(wt * c.quarters["ins"][q] for c, wt in cw for q in qs)
            lvl[g], line[g] = fr / base, ins / base
        for w in la.world_weights:
            out[(y, w)] = (lvl[w] / lvl[MACRO], line[w] / line[MACRO])
    return out


def check_layer_and_worlds_bank() -> None:
    """Книга дерева: неподвижная точка κ правилом листа (5 кругов от κ = 0) — слой M (`check_layer_m`); миры относительно
    слоя M у франшизы и у строки страхования — те же до 2e-3 в 2029 и 2036 годах (класс 1: франшиза дрейфует, как
    строка); без ключа франшиза по мирам не дрейфует (отношение 1), а строка — дрейфует."""
    run, traj, shifts = fixed_point(lambda t: bank({"insurance": t}))
    check_layer_m(run, traj, shifts)
    for (y, w), (fr, line) in world_relations(run).items():
        assert abs(fr - line) <= 2e-3, (y, w, fr, line)
    moved = [abs(line - 1) for (_, w), (_, line) in world_relations(run).items() if w != "M"]
    assert max(moved) > 0.02, moved


def check_layer_fixture() -> None:
    """Фикстура: неподвижная точка κ страхования (5 кругов) — слой M (`check_layer_m`)."""
    run, traj, shifts = fixed_point(lambda t: t6(roots={"insurance": t}))
    check_layer_m(run, traj, shifts)


# ------------------------------------------------------------------ входы прохода, память шага, отказы


def check_fingerprint() -> None:
    """Ключ, κ и связь строки — входы прохода каждого мира (`path_keys`): полоса по записям не возьмёт чужой проход."""
    run = t6(roots=T_KAPPA)
    assert P3._moves_every_world(run, t6())
    other = dict(T_KAPPA, insurance=dict(T_KAPPA["insurance"], **{"2027Q2": -0.031}))
    for alt in (t6(roots=other), t6(roots=T_KAPPA, other__insurance_volume_link=0.3), t6(roots={"insurance": 0.0})):
        assert P3._moves_every_world(alt, run)


def check_memo_and_light() -> None:
    """Память оценок шага и лёгкая оценка (фикстура с ключом, ограничение роста режет рост): сетка с выключенной памятью
    ≡ сетка с памятью — бит в бит (все клетки и ряды, H тоже); оценка шага на копии состояния не оставляет ряда H
    квартала, принятая — несёт его, лёгкая — снимает; повтор оценки той же доли из памяти — тот же H и смесь."""
    import dataclasses

    from model.cell import STEP_FLOWS, _Cell, initial_state, run_cell
    run = t6(roots=T_KAPPA)
    ctx = run.ctx
    assert ctx.prep.growth is not None and not ctx.prep.memo_off
    off = dataclasses.replace(ctx, prep=dataclasses.replace(ctx.prep, memo_off=True))
    cut = 0
    for c in run.cells:
        d = run_cell(off, c.world, c.regime, c.scenario)
        assert d.v_ri == c.v_ri and d.quarters == c.quarters, c.label
        cut += any((x or 0.0) > 0 for x in c.growth["cut_share"])
    assert cut, "ограничение роста не режет рост — проверка памяти пуста"
    cell = _Cell(ctx, "M", "downturn", "mid")
    st = initial_state(ctx.prep)
    cell.probe(st, 1)
    assert 1 not in cell.flows["vol_nom_ins"] and 1 not in cell.flows["vol_nom_fees"], "проба оставила ряд H квартала"
    memo: dict = {}
    first, _, kept = cell.evaluate(st, 1, (), 1.0, memo=memo)
    assert {"vol_nom_ins", "vol_nom_fees", "vol_mix"} <= set(kept) and 1 not in cell.flows["vol_nom_ins"]
    again = cell.evaluate(st, 1, ((40.0, 1, 1),), 1.0, memo=memo)[0]
    fresh = cell.evaluate(st, 1, ((40.0, 1, 1),), 1.0)[0]
    for name in ("vol_nom_ins", "vol_nom_fees", "vol_opex", "opex"):
        assert again[name] == fresh[name] == first[name], name
    cell.evaluate(st, 1, (), 0.5, light=True)
    assert 1 not in cell.flows["vol_nom_ins"]
    assert {"vol_nom_fees", "vol_nom_ins"} <= set(STEP_FLOWS) and "vol_nom_ins" in ctx.prep.line_flows


def check_refusals() -> None:
    """Схема: null ключа и строки, пустая траектория, строка вне {fees, insurance}, не число, LT_from позже конца сетки —
    отказ; ключ неактивного режима (доля 0, связь расходов 0) — не отказ; подмена null — отказ."""
    def book(value: Any, **more: Any) -> Any:
        return S.book_of(**{"opex__line_share_roots": value, **more})

    book({"insurance": T_KAPPA["insurance"], "fees": 0.01})                    # форма верна
    book({})                                                                   # пустой словарь — нет ключа
    book({"insurance": 0.0}, opex__volume_link=0.0)                            # ключ неактивного режима
    refused(lambda: book(None), "opex.line_share_roots: null в читаемом пути")
    refused(lambda: book({"insurance": None}), "opex.line_share_roots.insurance: null в читаемом пути")
    refused(lambda: book({"insurance": {}}), "траектория — число или непустой словарь")
    refused(lambda: book({"retail": 0.0}), "opex.line_share_roots.retail: незнакомый ключ")
    refused(lambda: book({"insurance": {"2026Q3": "минус", "LT": 0.0}}), "ожидается число")
    refused(lambda: book({"insurance": {"LT": 0.0, "LT_from": 2040}}), "позже года last_period")
    refused(lambda: book({"insurance": [0.0]}), "траектория — число или непустой словарь")
    base = S.book_of()
    refused(lambda: base.with_overrides({KEY: None}, create=True), "null")
    assert base.with_overrides({KEY: {"insurance": 0.0}}, create=True).get(f"{KEY}.insurance") == 0.0


# ------------------------------------------------------------------ выпуск


def check_release_with_pass6_key() -> None:
    """Выпуск фикстуры с ключом прохода 6 (базы строк, доли франшиз, κ у обеих строк): контракт выполнен; ряды клетки
    vol_nom_* — в клетках прогона."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    data = t_dict()
    changes = {"valuation__terminal__fixed_growth_share": 0.0, "checks__mix_ratio_tolerance": 0.002, **T_BASES,
               "opex__line_shares": T_SHARES, "opex__line_share_roots": T_KAPPA}
    for k, v in changes.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    run = run_grid(book, facts)
    assert run.ctx.prep.share_nominal is not None
    expl = explained(check_gates(run, today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    assert contract(d) == [], contract(d)[:5]
    for c in rel.run.cells:
        assert {"vol_nom_fees", "vol_nom_ins"} <= set(c.quarters)
