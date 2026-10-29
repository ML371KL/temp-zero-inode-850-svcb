"""Проверки третьего прохода ядра Совкомбанка (core-pass3): терминал, сверенный с явными годами (К-Т2: год терминала по
средней длине года — а, ставка фондирования блока К-Т по правилу балансирующих статей — б, угасание по календарю — в),
неработающие деньги за средствами клиентов (К8) и смесь баз строки (К2б).

Одни и те же проверки зовут тесты (`tests/test_core_p3.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass3/example.json` — копия выхода
`example.py` агента методики), выведенные независимо от кода ядра. Ключей прохода в книгах фикстур нет (нет ключа —
прежняя ветвь кода, бит в бит): проверки включают их подменой.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any, Mapping

from model.book_schema import BookError
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests" / "fixtures" / "core_pass3" / "example.json"
close = S.close
MEAN_DAYS = 365.2425                         # средняя длина года (григорианская) — независимо от ядра
DAYS = 365.0                                 # act/365 (М§0.3)
YB, FF, FA = "valuation.terminal.year_basis", "valuation.terminal.fixed_funding", "valuation.terminal.fade_anchor_year"
LAM_F, STAT = "valuation.terminal.fixed_growth_share", "valuation.terminal.stationary_rates"


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода: разделы K2b, K8, K_T2a, K_T2b, K_T2c."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def refused(fn, words: str, kind: type = BookError) -> None:
    """Отказ `kind` (BookError по умолчанию) со словами `words` в сообщении."""
    try:
        fn()
    except kind as exc:
        assert words in str(exc), str(exc)[:600]
        return
    raise AssertionError(f"нет отказа «{words}»")


def _t_base() -> tuple[Any, Any]:
    from model.book import book_from_dict
    from tests.support_core_t import t_dict, t_facts
    return book_from_dict(t_dict(), facts=t_facts()), t_facts()


@functools.lru_cache(maxsize=None)
def _t_run(changes: tuple = (), years: int = 0, summary: bool = False) -> Any:
    """Сетка фикстуры `core_t` с подменами (`((путь, json), …)`); `years` — явный участок длиннее на столько лет (правило
    класса 3 `ops/tools/class_checks.py::extended_book`); `summary` — лёгкая сетка (проходы через входы прохода)."""
    from model.grid import run_grid
    from tests.support_core_t import book_live
    book, facts = _t_base()
    if changes:
        book = book.with_overrides({k: json.loads(v) for k, v in changes}, create=True)
    if years:
        book = extended(book, years)
    return run_grid(book, facts, book_live(book), summary=summary)


def t_run(*, years: int = 0, summary: bool = False, **changes: Any) -> Any:
    """`_t_run` с подменами именами (`__` вместо точки)."""
    return _t_run(tuple(sorted((k.replace("__", "."), json.dumps(v)) for k, v in changes.items())), years, summary)


def extended(book: Any, years: int) -> Any:
    """Книга с явным участком длиннее на `years` лет: `meta.last_period` на `years` лет позже, новые полугодия
    траекторий миров — значением последнего полугодия (правило класса 3, `ops/tools/class_checks.py`)."""
    last = str(book.get("meta.last_period"))
    year, quarter = int(last[:4]), last[4:]
    ov: dict[str, Any] = {"meta.last_period": f"{year + years}{quarter}"}
    for w in book.get("worlds.ids"):
        for name, traj in (book.get(f"worlds.{w}") or {}).items():
            if not isinstance(traj, Mapping) or f"{year}H2" not in traj:
                continue
            for y in range(year + 1, year + years + 1):
                for h in ("H1", "H2"):
                    ov[f"worlds.{w}.{name}.{y}{h}"] = traj[f"{year}H2"]
    return book.with_overrides(ov, create=True)


def _path_key(run: Any) -> bytes:
    from model.grid import path_inputs, path_key
    return path_key(path_inputs(run.ctx))


def _moves_every_world(a: Any, b: Any) -> bool:
    """Вход прохода меняет отпечаток КАЖДОГО мира (`model.grid.path_keys`), а не только мира-опоры: по отпечаткам миров
    полоса другой книги берёт проходы из записи (`band(like=…)`), и мир с прежним отпечатком получил бы чужой проход.
    Отпечаток всей сетки (`path_key`) этого не различает: он меняется, если сдвинулся хотя бы один мир."""
    from model.grid import path_inputs, path_keys
    ka, kb = path_keys(path_inputs(a.ctx)), path_keys(path_inputs(b.ctx))
    return set(ka) == set(kb) and all(ka[w] != kb[w] for w in ka)


def _path(run: Any, c: Any) -> Any:
    from model.cell import cell_path
    return cell_path(run.ctx, c.world, c.regime, c.scenario)


def _year_l(run: Any) -> list[int]:
    tl = run.ctx.timeline
    return [q for q in range(1, tl.Q + 1) if tl.year(q) == tl.year(tl.Q)]


def _same_quarters(a: Any, b: Any, rows: tuple[str, ...] = ("bv", "ci", "div", "rwa", "n20", "nii", "pbt")) -> None:
    """Явные кварталы двух сеток — бит в бит (ключ трогает только терминал)."""
    for x, y in zip(a.cells, b.cells):
        for name in rows:
            assert x.quarters[name] == y.quarters[name], (x.label, name)


# ------------------------------------------------------------------ К-Т2а: год терминала по средней длине года (М§7)


def check_year_example() -> None:
    """Пример K_T2a (N/norm/mid, L = 2036, 366 дней) функцией ядра `mean_year`: ν_L = 365,2425 / 366, ψ = 365,2425 / 365,
    дневные строки года L и поправка PBT — 1e-12; у невисокосного L ν = ψ; Y_X × ψ — функцией терминала ядра (Y_X при
    year_factor = ψ — ψ × Y_X без него, 1e-15)."""
    from types import SimpleNamespace

    from model.cell import mean_year
    from model.valuation import terminal
    ex = example()["K_T2a"]
    run = t_run()
    tl = run.ctx.timeline
    qs = _year_l(run)
    assert sum(tl.d(q) for q in qs) == ex["days_L"] == 366
    rows = [{"nii": 0.0, "llp": 0.0, "fvc": 0.0} for _ in range(tl.Q)]
    nii, llp = 506.9768945069029, 127.16598770322082
    rows[qs[-1] - 1] = {"nii": nii, "llp": llp, "fvc": 0.0}
    pbt_l, d_nii = 288.0575404415721, -2.404796231285495
    pbt_t, node = mean_year(SimpleNamespace(timeline=tl), rows, pbt_l, d_nii)
    assert node["days_l"] == 366 and node["nu_l"] == MEAN_DAYS / 366 and node["psi"] == MEAN_DAYS / DAYS
    assert close(node["nu_l"], ex["nu_L"], 1e-15) and close(node["psi"], ex["psi"], 1e-15)
    assert close(node["day_weighted_l"], ex["day_weighted_L"], 1e-12)
    assert close(pbt_t, ex["pbt_terminal_base_new"], 1e-12) and close(pbt_l + d_nii, ex["pbt_terminal_base_old"], 1e-12)
    assert close(node["adj"], ex["adj"], 1e-12, 1e-12)
    assert close(ex["y_x_new"], ex["y_x_old"] * MEAN_DAYS / DAYS, 1e-15)
    assert close(ex["non_leap_L_365"]["nu"], MEAN_DAYS / DAYS, 1e-15)
    kw = dict(n20=0.16, req20=0.133, n11_star=0.13, req11=0.08, rwa=1000.0, bv_q=150.0, pbt_last_year=60.0,
              y_balancing=0.07, c_wholesale=0.12, headroom=5.0, tau_eff=0.25, nci_share=0.01, coupon_annual=1.0,
              tau_stat=0.25, lt_inflation=0.04, real_growth=0.01, fade=0.5, multiple=1.0, k_t=0.15, min_share=0.1)
    one, psi = terminal(**kw), terminal(**kw, year_factor=MEAN_DAYS / DAYS)
    assert one.x_t > 5.0 / 0.9 and close(psi.y_x, one.y_x * MEAN_DAYS / DAYS, 1e-15)


def check_year_grid() -> None:
    """Фикстура `core_t` (L = 2036, високосный): calendar — бит в бит как без ключа, узла нет; mean — явные кварталы бит
    в бит, вход терминала PBT^T_L = PBT_L + (ν − 1) DW_L (DW_L — ЧПД, резервы и FVC года L по рядам клетки), Y_X — ψ ×
    прежний, узел клетки — дни, ν, ψ, DW_L и поправка; TV_DDM − TV_RI = BV_Q; ключ — вход прохода (отпечаток проходов
    другой, лёгкая сетка — те же оценки)."""
    base, cal, run = t_run(), t_run(valuation__terminal__year_basis="calendar"), t_run(valuation__terminal__year_basis="mean")
    assert cal.point == base.point and [c.v_ri for c in cal.cells] == [c.v_ri for c in base.cells]
    assert all(c.terminal_year is None for c in base.cells + cal.cells)
    _same_quarters(run, base)
    tl = run.ctx.timeline
    qs = _year_l(run)
    days = sum(tl.d(q) for q in qs)
    nu, psi = MEAN_DAYS / days, MEAN_DAYS / DAYS
    for c, b in zip(run.cells, base.cells):
        dw = sum(c.quarters["nii"][q] - c.quarters["llp"][q] - c.quarters["fvc"][q] for q in qs)
        pbt_l = sum(c.quarters["pbt"][q] for q in qs)
        node = c.terminal_year
        assert node["days_l"] == days and close(node["nu_l"], nu, 1e-15) and close(node["psi"], psi, 1e-15)
        assert close(node["day_weighted_l"], dw, 1e-12, 1e-9)
        assert close(node["adj"], (nu - 1) * dw, 1e-9, 1e-9), (c.label, node["adj"], (nu - 1) * dw)
        kp, bp = _path(run, c), _path(base, b)
        assert bp.terminal["pbt_last_year"] == pbt_l and "year_factor" not in bp.terminal
        assert close(kp.terminal["pbt_last_year"], pbt_l + (nu - 1) * dw, 1e-12, 1e-9)
        assert kp.terminal["year_factor"] == psi
        assert close(c.y_x, b.y_x * psi, 1e-12, 1e-12), (c.label, c.y_x, b.y_x)
        assert close(c.tv_ddm - c.tv_ri, c.quarters["bv"][tl.Q], 1e-12, 1e-9), c.label
    assert run.point != base.point and _path_key(run) != _path_key(base) and _moves_every_world(run, base)
    light = t_run(summary=True, valuation__terminal__year_basis="mean")
    assert light.point == run.point and [x.v_ri for x in light.cells] == [x.v_ri for x in run.cells]
    # полоса книги с ключом на записях полосы без ключа (те же точки): ни один мир не берёт проход без поправки
    from model import uncertainty as U
    kept = U.band(base.ctx.book, base.ctx.facts, base.ctx.live, draws=3, workers=1, keep=True)
    got = U.band(run.ctx.book, run.ctx.facts, run.ctx.live, draws=3, workers=1, like=kept)
    want = U.band(run.ctx.book, run.ctx.facts, run.ctx.live, draws=3, workers=1)
    assert got.rows == want.rows and got.low_draws == want.low_draws and got.high_draws == want.high_draws


def check_year_with_stationary_and_block() -> None:
    """С К4: PBT^T_L = PBT_L + (ν − 1) DW_L + ν ΔNII*_L (ΔNII*_L — узел terminal_stationary); с блоком К-Т (λ_F = 0):
    стоимость фондирования стоящей доли — за средний год, −I_F − CPN после налога = ψ × прежняя (y_m, D_F те же);
    TV_DDM − TV_RI = BV_Q."""
    stat = t_run(valuation__terminal__stationary_rates=True)
    run = t_run(valuation__terminal__stationary_rates=True, valuation__terminal__year_basis="mean")
    tl = run.ctx.timeline
    qs = _year_l(run)
    nu = MEAN_DAYS / sum(tl.d(q) for q in qs)
    for c, b in zip(run.cells, stat.cells):
        dw = sum(c.quarters["nii"][q] - c.quarters["llp"][q] - c.quarters["fvc"][q] for q in qs)
        pbt_l = sum(c.quarters["pbt"][q] for q in qs)
        d_nii = c.terminal_stationary["d_nii_l"]
        assert d_nii == b.terminal_stationary["d_nii_l"]
        assert close(_path(run, c).terminal["pbt_last_year"], pbt_l + (nu - 1) * dw + nu * d_nii, 1e-12, 1e-9)
        assert close(c.terminal_year["adj"], (nu - 1) * (dw + d_nii), 1e-9, 1e-9)
    blk0 = t_run(valuation__terminal__fixed_growth_share=0.0)
    blk = t_run(valuation__terminal__fixed_growth_share=0.0, valuation__terminal__year_basis="mean")
    prep = blk.ctx.prep
    psi = MEAN_DAYS / DAYS
    seen = 0
    for c, b in zip(blk.cells, blk0.cells):
        f, f0 = c.terminal_fixed, b.terminal_fixed
        assert f["y_m"] == f0["y_m"] and f["d_f"] == f0["d_f"] and f["f_k"] == f0["f_k"]
        cpn = prep.coupon_annual * (1 - c.quarters["tau_stat"][tl.Q]) if "capital_instruments" in f["parts"] else 0.0
        assert close(-f["i_f"] - cpn, psi * (-f0["i_f"] - cpn), 1e-12, 1e-12), (c.label, f["i_f"], f0["i_f"])
        assert close(c.tv_ddm - c.tv_ri, c.quarters["bv"][tl.Q], 1e-12, 1e-9), c.label
        seen += abs(f0["d_f"]) > 1e-6
    assert seen, "у фикстуры нет фондирования постоянных частей — проверка пуста"


def check_year_not_leap() -> None:
    """Явный участок длиннее на год (L = 2037, 365 дней): ν = ψ точно, PBT^T_L − PBT_L = (ψ − 1) DW_L (1e-12); с К4 —
    (ψ − 1) DW_L + ψ ΔNII*_L − ΔNII*_L; узел — 365 дней."""
    run = t_run(years=1, valuation__terminal__year_basis="mean", valuation__terminal__stationary_rates=True)
    tl = run.ctx.timeline
    qs = _year_l(run)
    psi = MEAN_DAYS / DAYS
    assert tl.year(tl.Q) == 2037 and sum(tl.d(q) for q in qs) == 365
    for c in run.cells:
        node, d_nii = c.terminal_year, c.terminal_stationary["d_nii_l"]
        assert node["days_l"] == 365 and node["nu_l"] == node["psi"] == psi
        dw = sum(c.quarters["nii"][q] - c.quarters["llp"][q] - c.quarters["fvc"][q] for q in qs)
        pbt_l = sum(c.quarters["pbt"][q] for q in qs)
        got = _path(run, c).terminal["pbt_last_year"] - pbt_l - d_nii      # к прежнему входу PBT_L + ΔNII*_L
        assert close(got, (psi - 1) * dw + psi * d_nii - d_nii, 1e-9, 1e-9), (c.label, got)


def check_year_schema() -> None:
    """Отказ схемы: год терминала — calendar или mean."""
    refused(lambda: S.book_of(valuation__terminal__year_basis="actual"), "незнакомое значение")


# ------------------------------------------------------------------ К-Т2в: угасание по календарю (М§7)


def fade_ref(n: float, k: float, g: float, s: float = 0.0) -> float:
    """Множитель угасания при линейном сходе избытка за n лет после года-якоря, s лет которых уже в явном участке —
    справочная формула М§7 с началом s, заново: веса (1 − (t − 1 + s)/n) при t − 1 + s < n."""
    x = (1 + g) / (1 + k)
    total, j = 0.0, 0
    while j + s < n:
        total += (1 - (j + s) / n) * x ** j
        j += 1
    return (k - g) / (1 + k) * total


def check_fade_example() -> None:
    """Пример K_T2c функциями ядра: срок n_W миров N, H, M при fade 0,5 (fade(n_W, k, g, 0) = 0,5) — 1e-12, множители
    при s = 0, 1, 2 — 1e-9; φ_W(0) = fade, φ_W убывает по s; fade = 1 — φ = 1 при любом s; при целом n — справочная
    формула М§7 (сумма t = 1…n) и формула с началом s заново."""
    from model.valuation import fade_at, fade_of, fade_years
    ex = example()["K_T2c"]
    for world in ("N", "H", "M"):
        w = ex[world]
        k, g = w["k_T"], w["g_T"]
        n = fade_years(0.5, k, g)
        assert close(n, w["n_W"], 1e-12), (world, n, w["n_W"])
        assert close(fade_of(n, k, g, 0), 0.5, 1e-12)
        for s, key in ((0, "phi_s0"), (1, "phi_s1"), (2, "phi_s2")):
            assert close(fade_at(0.5, k, g, s), w[key], 1e-9), (world, s)
            assert close(fade_ref(n, k, g, s), w[key], 1e-9), (world, s)
        assert fade_at(0.5, k, g, 0) == 0.5 and w["phi_s2"] < w["phi_s1"] < 0.5
        for n_int in (3, 15, 20):
            ref = (k - g) / (1 + k) * sum((1 - (t - 1) / n_int) * ((1 + g) / (1 + k)) ** (t - 1)
                                          for t in range(1, n_int + 1))
            assert close(fade_of(n_int, k, g, 0), ref, 1e-13)
            for s in (1, 2, 5):
                assert close(fade_of(n_int, k, g, s), fade_ref(n_int, k, g, s), 1e-13)
    assert fade_at(1.0, 0.15, 0.06, 1) == ex["fade_1"]["phi_s1"] == 1.0
    assert fade_years(1.0, 0.15, 0.06) == float("inf")


def check_fade_grid() -> None:
    """Фикстура `core_t` (L = 2036, множитель угасания 0,5): год-якорь 2036 — бит в бит как без ключа, узла нет; 2035 и
    2034 (s = 1, 2) — явные
    кварталы и проходы бит в бит (ключ — параметр оценки, отпечаток проходов тот же), в каждой клетке срок n_W
    из множителя книги при k_T и g_T клетки (fade(n_W, 0) = fade), множитель φ_W = fade(n_W, s) по формуле заново,
    убывает по s и стоит в ROE'_T так же, как множитель книги (одностороннее угасание); TV_DDM − TV_RI = BV_Q; fade = 1 —
    φ = 1 и оценки без ключа."""
    half = {"valuation__terminal__fade": 0.5}
    base, at_l = t_run(**half), t_run(**half, valuation__terminal__fade_anchor_year=2036)
    assert at_l.point == base.point and [c.v_ri for c in at_l.cells] == [c.v_ri for c in base.cells]
    assert all(c.terminal_fade is None for c in at_l.cells + base.cells)
    one = t_run(**half, valuation__terminal__fade_anchor_year=2035)
    two = t_run(**half, valuation__terminal__fade_anchor_year=2034)
    _same_quarters(one, base)
    assert _path_key(one) == _path_key(two) == _path_key(at_l)
    from model.grid import path_inputs
    assert path_inputs(one.ctx).prep.fade_anchor is None and one.ctx.prep.fade_anchor == 2035
    fade = float(one.ctx.book.get("valuation.terminal.fade"))
    Q = one.ctx.timeline.Q
    hit = 0
    for c1, c2, b in zip(one.cells, two.cells, base.cells):
        assert c1.k_t == b.k_t and c1.g_t == b.g_t and c1.x_t == b.x_t
        f1, f2 = c1.terminal_fade, c2.terminal_fade
        assert f1["s"] == 1 and f2["s"] == 2 and f1["n"] == f2["n"]
        k, g = c1.k_t, c1.g_t
        assert close(fade_ref(f1["n"], k, g, 0), fade, 1e-12), c1.label
        assert close(f1["phi"], fade_ref(f1["n"], k, g, 1), 1e-12) and close(f2["phi"], fade_ref(f2["n"], k, g, 2), 1e-12)
        assert f2["phi"] < f1["phi"] < fade, c1.label
        excess = c1.roe_t_raw - k
        assert c1.roe_t_raw == b.roe_t_raw
        assert close(c1.roe_t - k, f1["phi"] * max(excess, 0.0) + min(excess, 0.0), 1e-12, 1e-15), c1.label
        assert close(c1.tv_ddm - c1.tv_ri, c1.quarters["bv"][Q], 1e-12, 1e-9), c1.label
        hit += excess > 0
    assert hit, "у фикстуры нет клеток с положительным избытком — проверка пуста"
    flat, flat1 = t_run(), t_run(valuation__terminal__fade_anchor_year=2034)      # множитель фикстуры — 1
    assert [c.v_ri for c in flat1.cells] == [c.v_ri for c in flat.cells]
    assert all(c.terminal_fade == {"s": 2, "n": None, "phi": 1.0} for c in flat1.cells)


def check_fade_block_and_symmetric() -> None:
    """Блок К-Т (λ_F = 0) и симметричное угасание (множитель 0,5, s = 1): множитель блока и ROE'_T — φ_W клетки (тот же,
    что у одностороннего угасания без блока); TV_DDM − TV_RI = BV_Q."""
    half = {"valuation__terminal__fade": 0.5, "valuation__terminal__fade_anchor_year": 2035}
    sym = t_run(**half, valuation__terminal__fade_mode="symmetric")
    one = t_run(**half)
    for c, d in zip(sym.cells, one.cells):
        assert c.terminal_fade == d.terminal_fade
        assert close(c.roe_t - c.k_t, c.terminal_fade["phi"] * (c.roe_t_raw - c.k_t), 1e-12, 1e-15), c.label
    blk = t_run(**half, valuation__terminal__fixed_growth_share=0.0)
    Q = blk.ctx.timeline.Q
    for c in blk.cells:
        f = c.terminal_fixed
        assert f["phi"] == (c.terminal_fade["phi"] if f["x_b"] > 0 else 1.0), c.label
        assert close(c.tv_ddm - c.tv_ri, c.quarters["bv"][Q], 1e-12, 1e-9), c.label


def check_fade_schema() -> None:
    """Отказ: год-якорь позже года last_period — схема (с числами) и функция ядра."""
    refused(lambda: S.book_of(valuation__terminal__fade_anchor_year=2037), "позже года last_period 2036")
    from types import SimpleNamespace

    from model.valuation import fade_anchor
    stub = SimpleNamespace(opt=lambda path, default=None: 2040, get=lambda path: "2036Q4")
    refused(lambda: fade_anchor(stub), "позже года last_period 2036")


# ------------------------------------------------------------------ К-Т2б: ставка фондирования блока К-Т (М§7, §4.10)


def _block(**kw: Any) -> Any:
    """Блок постоянных частей функцией ядра на синтетических входах (λ_F = 0, все части): постоянные активы 97,035,
    без инструментов, неконтролирующих долей и строк в реальных рублях — D_F = F_A − κ R_F."""
    from model.valuation import FixedInputs, fixed_block
    fixed = FixedInputs(f_a=97.035, r_f=100.0, kappa20=0.12, kappa11=0.1, at1=0.0, t2=0.0, nci=0.0, dp_fix=0.0,
                        misc_l=0.0, nc_l=0.0)
    args = dict(x_t=10.0, bv_star=500.0, bv_q=510.0, g=0.06, k_t=0.15, ci_t1=80.0, y_x=0.5, ni_t1=81.0, capped=False,
                n20=0.14, req20=0.12, n11_star=0.13, req11=0.1, y_balancing=0.07550438362233036, c_wholesale=0.08,
                wholesale_extra=0.0, tau_eff=0.233, nci_share=0.048, coupon_annual=0.0, tau_stat=0.25,
                lt_inflation=0.04, fade=0.5, symmetric=False, fixed=fixed, lam_f=0.0, parts=P_ALL)
    args.update(kw)
    return fixed_block(**args)


P_ALL = ("other_assets_fixed", "capital_instruments", "other_fixed_liabilities", "real_rubles")


def check_funding_example() -> None:
    """Пример K_T2b функцией ядра `fixed_block`: N/norm/mid — минимум связан, M_F = (c_wh − y_bal) m / (1 − m) F_A
    до налога (1e-12), I_F ниже прежнего на M_F (1 − τ)(1 − nci); H/norm/mid — на конце Q не связан (WT_Q = 0,
    HLA 38,5), но избыток 171,7 больше H* = 38,5 / (1 − m): связан после выплаты, WT* = X_T − H*, ставка — опта.
    Синтетика связанности: X_T < 0 гасит добор опта — связан при WT_Q > −X_T, свободен при WT_Q ≤ −X_T; свободный
    минимум — M_F = 0, y_m = y_bal и прежний блок (1e-15); M_F ≥ 0 при c_wh ≥ y_bal."""
    ex = example()["K_T2b"]
    m, fa = 0.207, 97.035
    bal = {"funding": "balancing", "min_share": m}
    n = _block(wholesale_extra=267.85, headroom=0.0, **bal)
    old = _block(wholesale_extra=267.85)
    f, f0 = n.fixed, old.fixed
    assert f["bound_after_payout"] is True and f["y_m"] == 0.08 == f0["y_m"]
    want = (0.08 - 0.07550438362233036) * m / (1 - m) * fa
    assert close(f["min_liquidity"], want, 1e-15) and close(want, ex["N_norm_mid"]["extra_pre_tax"], 1e-12)
    tax = (1 - 0.233) * (1 - 0.048)
    assert close(f["i_f"] - f0["i_f"], ex["N_norm_mid"]["d_I_F_after_tax"], 1e-9) and close(f["i_f"] - f0["i_f"], -want * tax, 1e-9)
    assert close(n.tv_ddm - n.tv_ri, 510.0, 1e-12)
    h = ex["H_norm_mid"]
    hb = _block(x_t=171.7, headroom=38.5, wholesale_extra=0.0, **bal)
    assert close(38.5 / (1 - m), h["h_star"], 1e-15)
    assert hb.fixed["bound_after_payout"] is True and close(hb.fixed["wt_after"], h["wt_after_payout"], 1e-12)
    assert hb.fixed["y_m"] == 0.08 and _block(x_t=171.7, headroom=38.5).fixed["y_m"] == 0.07550438362233036
    # X_T ≤ 0: добавленный капитал гасит добор опта
    tight = _block(x_t=-20.0, headroom=0.0, wholesale_extra=30.0, **bal).fixed
    assert tight["bound_after_payout"] is True and close(tight["wt_after"], 10.0, 1e-15) and tight["y_m"] == 0.08
    free = _block(x_t=-20.0, headroom=0.0, wholesale_extra=15.0, **bal).fixed
    assert free["bound_after_payout"] is False and free["wt_after"] == 0.0 and free["min_liquidity"] == 0.0
    assert free["y_m"] == 0.07550438362233036
    assert _block(x_t=-20.0, headroom=0.0, wholesale_extra=20.0, **bal).fixed["bound_after_payout"] is False
    # свободный минимум после выплаты — прежний блок
    a, b = _block(x_t=5.0, headroom=10.0, **bal), _block(x_t=5.0, headroom=10.0)
    assert a.fixed["bound_after_payout"] is False and a.fixed["min_liquidity"] == 0.0
    for key in ("i_f", "x_b", "business_capital", "d_f", "y_m"):
        assert close(a.fixed[key], b.fixed[key], 1e-15, 1e-15), key
    assert close(a.tv_ri, b.tv_ri, 1e-15) and close(a.roe_t, b.roe_t, 1e-15)
    assert "bound_after_payout" not in b.fixed
    assert _block(wholesale_extra=1.0, c_wholesale=0.09, **bal).fixed["min_liquidity"] > 0
    # с годом терминала по средней длине года (К-Т2а): [y_m D_F + M_F] — за средний год
    psi = MEAN_DAYS / DAYS
    y = _block(wholesale_extra=267.85, year_factor=psi, **bal).fixed
    assert close(y["i_f"], -psi * (y["y_m"] * y["d_f"] + y["min_liquidity"]) * tax, 1e-15)


def check_funding_grid() -> None:
    """Фикстура `core_t`, блок К-Т (λ_F = 0): binary — бит в бит как без ключа; balancing — явные кварталы и проходы те
    же (ключ — параметр оценки: входы прохода несут binary, отпечаток проходов тот же), в каждой клетке связанность
    после выплаты избытка, ставка и стоимость минимума на постоянных активах — по формуле заново из X_T, HLA_Q, WT_Q,
    ставок балансирующих на конце Q; I_F — прежний блок со ставкой y_m и добавкой M_F; TV_DDM − TV_RI = BV_Q. Доля
    минимума ликвидности 0,25 (связан только после выплаты избытка в части клеток) и 0,3 (добор опта на конце Q). Без
    блока ключ не читается (оценки без ключа)."""
    lam = {"valuation__terminal__fixed_growth_share": 0.0}
    base, binary = t_run(**lam), t_run(**lam, valuation__terminal__fixed_funding="binary")
    run = t_run(**lam, valuation__terminal__fixed_funding="balancing")
    assert [c.v_ri for c in binary.cells] == [c.v_ri for c in base.cells]
    assert all("bound_after_payout" not in c.terminal_fixed for c in base.cells)
    _same_quarters(run, base)
    from model.grid import path_inputs
    assert path_inputs(run.ctx).prep.fixed_funding == "binary" and run.ctx.prep.fixed_funding == "balancing"
    assert _path_key(run) == _path_key(binary)
    seen = {"bound": 0, "free": 0, "after": 0}
    for lm in (0.25, 0.3):
        tight = {"volumes__liquid_min_share": lm, **lam}
        _funding_cells(t_run(**tight, valuation__terminal__fixed_funding="balancing"), t_run(**tight), seen)
    assert seen["bound"] and seen["free"] and seen["after"], seen
    off = t_run(valuation__terminal__fixed_funding="balancing")
    assert [c.v_ri for c in off.cells] == [c.v_ri for c in t_run().cells] and off.ctx.prep.fixed_funding == "binary"


def _funding_cells(run: Any, base: Any, seen: dict) -> None:
    prep = run.ctx.prep
    m, Q = prep.liquid_min, run.ctx.timeline.Q
    for c, b in zip(run.cells, base.cells):
        t = _path(run, c).terminal
        f, f0 = c.terminal_fixed, b.terminal_fixed
        x_t, wt = c.x_t, c.quarters["wholesale_extra"][Q]
        assert wt == t["wholesale_extra"] and c.la_headroom == t["headroom"] and x_t == b.x_t
        wt_after = wt + max(0.0, x_t - c.la_headroom / (1 - m)) if x_t > 0 else max(0.0, wt + x_t)
        bound = wt_after > 0
        assert f["bound_after_payout"] is bound and close(f["wt_after"], wt_after, 1e-12, 1e-12), c.label
        y_bal, c_wh = t["y_balancing"], t["c_wholesale"]
        assert f["y_m"] == (c_wh if bound else y_bal)
        m_f = (c_wh - y_bal) * m / (1 - m) * f["f_a"] if bound else 0.0
        assert close(f["min_liquidity"], m_f, 1e-12, 1e-15), c.label
        tax = (1 - c.quarters["tau_eff"][Q]) * (1 - prep.nci_share)
        cpn = prep.coupon_annual * (1 - c.quarters["tau_stat"][Q])
        assert close(f["i_f"], -(f["y_m"] * f["d_f"] + m_f) * tax - cpn, 1e-12, 1e-12), c.label
        assert f["d_f"] == f0["d_f"] and f["f_k"] == f0["f_k"]
        assert close(c.tv_ddm - c.tv_ri, c.quarters["bv"][Q], 1e-12, 1e-9), c.label
        if not bound:
            assert close(c.v_ri, b.v_ri, 1e-12) or f0["y_m"] != y_bal, c.label
        seen["bound" if bound else "free"] += 1
        seen["after"] += bound and not wt > 0


def check_funding_schema() -> None:
    """Отказ схемы: ставка фондирования блока — binary или balancing."""
    refused(lambda: S.book_of(valuation__terminal__fixed_growth_share=0.0, valuation__terminal__fixed_funding="wholesale"),
            "незнакомое значение")


# ------------------------------------------------------------------ К8: неработающие деньги за средствами клиентов (М§4.3)

CASH, CASH_W = "volumes__cash_assets", "capital__rwa__density__cash_assets"
T_CASH = 150.0                               # деньги якоря фикстуры `core_t` (растущая часть прочих активов — 785)
T_CASH_W = 0.1                               # их плотность


def cash_keys(driver: Any = "funds", amount: Any = T_CASH, density: float = T_CASH_W) -> dict[str, Any]:
    return {CASH: {"amount": amount, "driver": driver}, CASH_W: density}


def check_cash_example() -> None:
    """Пример K8 (остатки якоря книги Совкомбанка) функциями ядра: вырез плотности `carve_cash` — ω′_oa (1e-15), RWA
    растущей части якоря не меняется; квартал (кредиты +2 %, депозиты +3 %): деньги за депозитами, прочие активы ρ′ L +
    C + F_A и RWA растущей части `RwaWeights.rwa` с деньгами — числа примера (1e-12); драйвер «кредиты» — прежние
    прочие активы; плотность денег, равная плотности растущей части, — ω′_oa = ω_oa."""
    from model.capital import RwaWeights, carve_cash
    k8 = example()["K8"]
    c0, oa0, fa, l0, d0 = k8["c0"], 549.592, 97.035, k8["l0"], k8["d0_deposits"]
    w = RwaWeights(loans={}, securities=0.0, liquidity=0.0, other_assets=k8["w_oa"], oa_fixed=fa,
                   other_assets_fixed=0.0)
    cut = carve_cash(w, k8["w_cash"], c0, oa0)
    assert cut.cash == k8["w_cash"] and close(cut.other_assets_cash, k8["w_oa_carved"], 1e-15)
    assert cut.other_assets == k8["w_oa"]                                  # прежняя плотность — для RWA якоря
    assert close(cut.rwa({}, 0.0, 0.0, oa0, 1.0, 1.0, cash=c0), k8["rwa0_growing_part_old"], 1e-15)
    assert close(w.rwa({}, 0.0, 0.0, oa0, 1.0, 1.0), k8["rwa0_growing_part_old"], 1e-15)
    rho = (oa0 - fa) / l0
    assert close(rho, k8["rho_book"], 1e-15) and close(rho - c0 / l0, k8["rho_without_cash"], 1e-15)
    q = k8["quarter"]
    cash = c0 / d0 * (d0 * q["deposits_x"])
    oa = (rho - c0 / l0) * l0 * q["loans_x"] + cash + fa
    assert close(cash, q["cash"], 1e-12) and close(oa, q["oa_new"], 1e-12)
    assert close(cut.rwa({}, 0.0, 0.0, oa, 1.0, 1.0, cash=cash), q["rwa_growing_new"], 1e-12)
    assert close(w.rwa({}, 0.0, 0.0, rho * l0 * q["loans_x"] + fa, 1.0, 1.0), q["rwa_growing_old"], 1e-12)
    loans = (rho - c0 / l0) * l0 * q["loans_x"] + c0 * q["loans_x"] + fa
    assert close(loans, rho * l0 * q["loans_x"] + fa, 1e-15) and k8["driver_loans_identity"] == 0.0
    same = carve_cash(w, k8["w_oa"], c0, oa0)
    assert close(same.other_assets_cash, k8["w_oa"], 1e-15)


def _cash_weights(book: Any, c0: float, density: float, oa0: float, fa: float) -> tuple[float, float]:
    """ω_oa и ω′_oa заново: [ω_oa (OA_0 − F_A) − ω_c C_0] / (OA_0 − F_A − C_0)."""
    w_oa = float(book.get("capital.rwa.density.other_assets"))
    return w_oa, (w_oa * (oa0 - fa) - density * c0) / (oa0 - fa - c0)


def check_cash_grid() -> None:
    """Фикстура `core_t` (постоянные прочие активы 205): деньги 150 за средствами клиентов, плотность 0,1. В каждой клетке
    и квартале: C_q / D_q = C_0 / D_0 (D_q — средства клиентов на конец квартала), прочие активы ρ′ L_q + C_q + F_A
    (ρ′ = ρ − C_0 / L_0), RWA — плотности книги с вырезом ω′_oa (OA − F_A − C) + ω_c C + ω_oaf F_A, × дрейф плотности,
    валютный индекс и множитель режима (заново); тождество баланса; якорь — прочие активы и RWA бит в бит как без
    ключа; ряд клетки cash — только при ключе; ключ и плотность — входы прохода."""
    from model.capital import fx_index
    base, run = t_run(), t_run(**cash_keys())
    ctx = run.ctx
    prep, book, tl = ctx.prep, ctx.book, ctx.timeline
    Q = tl.Q
    af = prep.af
    l0 = sum(af.balances[b] for b in prep.roles.loans)
    d0 = sum(af.balances[b] for b in prep.roles.funds)
    fa = prep.oa_fixed
    rho_cut = float(book.get("volumes.other_assets_to_loans")) - T_CASH / l0
    _, w_cut = _cash_weights(book, T_CASH, T_CASH_W, af.other_assets, fa)
    dens = book.get("capital.rwa.density")
    assert "cash" not in base.cells[0].quarters
    moved = 0
    for c, b in zip(run.cells, base.cells):
        qs = c.quarters
        assert qs["rwa"][0] == b.quarters["rwa"][0] and qs["other_assets"][0] == b.quarters["other_assets"][0]
        assert qs["cash"][0] == T_CASH
        x = fx_index(book, ctx.worlds[c.world].cpi, Q)
        mult = prep.regimes[c.regime].rwa_mult
        for q in range(1, Q + 1):
            d_q = sum(c.books[n]["balance"][q] for n in prep.roles.funds)
            cash = qs["cash"][q]
            assert close(cash / d_q, T_CASH / d0, 1e-15), (c.label, q)
            loans = qs["loans"][q]
            assert close(qs["other_assets"][q], rho_cut * loans + cash + fa, 1e-12), (c.label, q)
            base_rwa = sum(float(dens[n]) * c.books[n]["balance"][q] for n in prep.roles.loans)
            base_rwa += float(dens["securities"]) * qs["securities"][q] + float(dens["liquidity"]) * qs["liquidity"][q]
            base_rwa += w_cut * (qs["other_assets"][q] - fa - cash) + T_CASH_W * cash
            base_rwa += float(dens["other_assets_fixed"]) * fa
            want = base_rwa * prep.dn[q] * x[q] * (1.0 if mult is None else mult[q])
            assert close(qs["rwa"][q], want, 1e-12), (c.label, q, qs["rwa"][q], want)
            assert close(qs["assets"][q], qs["liabilities_equity"][q], 1e-9), (c.label, q)
        moved += abs(c.v_ri - b.v_ri) > 1e-6
    assert moved and _path_key(run) != _path_key(base) and _moves_every_world(run, base)
    assert _moves_every_world(t_run(**cash_keys(density=0.2)), run)
    # драйвер денег — вход прохода сам по себе (те же деньги и плотность — тот же вырез плотностей RWA)
    assert _moves_every_world(t_run(**cash_keys(driver="loans")), run)
    light = t_run(summary=True, **cash_keys())
    assert light.point == run.point


def check_cash_equivalences() -> None:
    """Нейтральные формы: драйвер «кредиты» (словом и весами 1 на кредитных книгах) и сумма 0 — оценки, прочие активы и
    RWA без ключа (1e-12) при любой плотности денег; плотность денег, равная плотности растущей части, — ω′_oa = ω_oa."""
    base = t_run()
    loans = {"cards": 1.0, "cash_loans": 1.0, "auto": 1.0, "mortgage": 1.0, "sme_loans": 1.0, "corp_loans": 1.0}
    for keys in (cash_keys("loans"), cash_keys(amount=0.0), cash_keys("loans", density=0.6), cash_keys(loans)):
        run = t_run(**keys)
        for c, b in zip(run.cells, base.cells):
            assert close(c.v_ri, b.v_ri, 1e-12), (keys, c.label, c.v_ri, b.v_ri)
            for name in ("other_assets", "rwa", "bv"):
                for q, (x, y) in enumerate(zip(c.quarters[name], b.quarters[name])):
                    assert close(x, y, 1e-12), (keys, c.label, name, q)
    run = t_run(**cash_keys("loans", density=0.6))
    assert close(run.ctx.prep.rwa_w.other_assets_cash, 0.6, 1e-15)


def check_cash_memo() -> None:
    """Драйвер «средства клиентов» с ведомой книгой К6 (средства юрлиц за строкой страхования на базе «кредиты»): память
    стороны средств квартала одна на все доли прироста, ведомая книга — от доли прироста; деньги оценки шага при другой
    доле с той же памятью — те же, что без памяти (и прочие активы, RWA, средства)."""
    from model.cell import _Cell, initial_state
    run = t_run(**cash_keys(), volumes__liability_drivers={"corp_funds": "insurance"},
                other__insurance_volume_base="loans")
    ctx = run.ctx
    assert not ctx.prep.memo_off and ctx.prep.growth is not None and ctx.prep.driven is not None
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(ctx.prep)
    memo: dict = {}
    first = cell.evaluate(st, 1, (), 1.0, memo=memo)[0]
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    assert first["cash"] != fresh["cash"], "доля прироста не сдвигает деньги"
    for name in ("cash", "other_assets", "rwa", "funds"):
        assert second[name] == fresh[name], name
    d0 = sum(ctx.prep.af.balances[b] for b in ctx.prep.roles.funds)
    assert close(fresh["cash"], T_CASH / d0 * fresh["funds"], 1e-15)


def check_cash_anchor_and_refusals() -> None:
    """amount: anchor — узел фактов balance.nonworking_money.total (те же оценки, что числом; вывод anchor-ключа книги);
    отказы: драйвер с балансирующей книгой, процентные активы и номинал (схема), чужая книга и нулевые веса, денег
    больше растущей части, ρ′ < 0, ω′_oa < 0, нет плотности денег, уровень драйвера клетки не больше нуля (с меткой
    клетки и кварталом)."""
    import copy

    from model.book import Facts, _digest, derive_anchors
    from model.cell import _Cell
    from model.grid import run_grid
    from tests.support_core_t import book_live
    book, facts = _t_base()
    files = copy.deepcopy(dict(facts.files))
    files["balance"]["nonworking_money"] = {"total": {"v": T_CASH, "calc": "проверка К8"}}
    with_cash = Facts(root=facts.root, files=files, digest=_digest(files))
    probe = book.with_overrides({k.replace("__", "."): v for k, v in cash_keys(amount="anchor").items()}, create=True)
    got = run_grid(probe, with_cash, book_live(probe))
    assert [c.v_ri for c in got.cells] == [c.v_ri for c in t_run(**cash_keys()).cells]
    assert derive_anchors(copy.deepcopy(dict(probe.source)), with_cash)["volumes.cash_assets.amount"] == T_CASH

    def run(**kw: Any) -> Any:
        b = book.with_overrides({k.replace("__", "."): v for k, v in kw.items()}, create=True)
        return run_grid(b, facts, book_live(b))
    refused(lambda: run(**cash_keys({"liquidity": 1.0, "retail_term": 1.0})), "круг")
    refused(lambda: run(**cash_keys({"securities": 0.5})), "круг")
    for word in ("iea", "nominal", "wholesale"):
        refused(lambda word=word: run(**cash_keys(word)), "не подходит ни под один вид")
    refused(lambda: run(**cash_keys({"noise": 1.0})), "не подходит ни под один вид")
    refused(lambda: run(**cash_keys({"cards": 0.0})), "все веса нулевые")
    refused(lambda: run(**cash_keys(amount=800.0)), "больше растущей части")
    refused(lambda: run(**cash_keys(), volumes__other_assets_to_loans=0.03), "ρ′")
    refused(lambda: run(**cash_keys(density=4.0)), "меньше нуля")
    refused(lambda: S.book_of(volumes__cash_assets={"amount": T_CASH, "driver": "funds"}), "плотности неработающих денег")
    ctx = t_run(**cash_keys()).ctx
    cell = _Cell(ctx, "M", "crisis", "strict")
    zero = {b: 0.0 for b in ctx.prep.roles.names}
    refused(lambda: cell.cash_end(zero, 3), "клетка M/crisis/strict: уровень драйвера неработающих денег")


# ------------------------------------------------------------------ К2б: смесь баз строки (М§4.7)

FEES_B, INS_B = "fees.volume_base", "other.insurance_volume_base"
T_LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")
T_RETAIL = {"cards": 1.0, "cash_loans": 1.0, "auto": 1.0, "mortgage": 1.0}
# пример методики: остатки якоря книги Совкомбанка (balance.json, 30.06.2026) — книги примера
EX_E0 = {"auto": 509.345, "mortgage": 429.782, "cash_loans": 262.301, "cards": 170.549, "corp_loans": 1785.47,
         "retail_current": 295.364, "retail_term": 952.271, "corp_term": 1613.787, "corp_current": 375.16,
         "insurance_liab": 171.11}
EX_LOANS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans")
EX_RETAIL = {"auto": 1.0, "mortgage": 1.0, "cash_loans": 1.0, "cards": 1.0}


def mix(**parts: tuple[float, Any]) -> dict[str, Any]:
    """Смесь {mix: {имя: {share, base}}} из пар (доля, база)."""
    return {"mix": {name: {"share": s, "base": b} for name, (s, b) in parts.items()}}


def _ex_resolve(spec: Any, key: str = FEES_B) -> Any:
    """`resolve_line_base` ядра на остатках якоря примера: книга-заглушка с одним ключом базы строки."""
    from types import SimpleNamespace

    from model.book import BookRoles
    from model.cell import resolve_line_base
    names = tuple(EX_E0)
    funds = ("retail_current", "retail_term", "corp_term", "corp_current", "insurance_liab")
    roles = BookRoles(names=names, assets=EX_LOANS, liabilities=funds, loans=EX_LOANS,
                      retail=("retail_current", "retail_term"), corp_funds=funds[2:], funds=funds)
    data = {key: spec, "nii.books": {b: {} for b in names}}
    stub = SimpleNamespace(opt=lambda path, default=None: data.get(path, default), get=lambda path: data[path])
    return resolve_line_base(stub, key, roles=roles, balances=EX_E0)


def check_mix_example() -> None:
    """Пример K2b функцией ядра `resolve_line_base`: веса компилированной смеси комиссий {КБ 0,855, розница 0,145} и
    страхования {розница 0,5, все кредиты 0,5} — 1e-15 (масштаб — к наибольшему весу 1); тождество индексов на концах
    кварталов D_q / D_0 = Σ_k s_k D^k_q / D^k_0 (1e-15); прочтение «вес корпоративного кредита 0,5» — доли {0,30290,
    0,69710}; доля КБ «все кредиты» C_0 / L_0 — веса 1 на всех кредитах; слово и словарь весов — как в книге."""
    ex = example()["K2b"]
    fees = _ex_resolve(mix(corporate=(0.855, {"corp_loans": 1.0}), retail=(0.145, EX_RETAIL)))
    assert set(fees) == set(ex["fees_mix_weights"])
    for b, w in ex["fees_mix_weights"].items():
        assert close(fees[b], w, 1e-15), (b, fees[b], w)
    ins = _ex_resolve(mix(retail=(0.5, EX_RETAIL), loans=(0.5, "loans")), INS_B)
    for b, w in ex["ins_mix_S_weights"].items():
        assert close(ins[b], w, 1e-15), (b, ins[b], w)
    grow = {"auto": 1.03, "mortgage": 1.01, "cash_loans": 1.05, "cards": 1.04, "corp_loans": 1.02}
    eq = {b: v * grow.get(b, 1.0) for b, v in EX_E0.items()}

    def lvl(w: dict, e: dict) -> float:
        return sum(x * e[b] for b, x in w.items())
    r0, l0 = lvl(EX_RETAIL, EX_E0), sum(EX_E0[b] for b in EX_LOANS)
    lhs = lvl(fees, eq) / lvl(fees, EX_E0)
    rhs = 0.855 * eq["corp_loans"] / EX_E0["corp_loans"] + 0.145 * lvl(EX_RETAIL, eq) / r0
    assert close(lhs, rhs, 1e-15) and close(lhs, ex["index_identity"]["fees_lhs"], 1e-15)
    lhs = lvl(ins, eq) / lvl(ins, EX_E0)
    rhs = 0.5 * lvl(EX_RETAIL, eq) / r0 + 0.5 * sum(eq[b] for b in EX_LOANS) / l0
    assert close(lhs, rhs, 1e-15) and close(lhs, ex["index_identity"]["ins_lhs"], 1e-15)
    s_l = ex["ins_S_share_equiv_of_L"]
    assert close(s_l, l0 / (r0 + l0), 1e-15)
    levels = _ex_resolve(mix(retail=(1 - s_l, EX_RETAIL), loans=(s_l, "loans")), INS_B)
    assert close(levels["corp_loans"], ex["ins_corp_weight_L"], 1e-12)
    s_c = ex["fees_axis_all_loans_s_corp"]
    assert close(s_c, EX_E0["corp_loans"] / l0, 1e-15)
    flat = _ex_resolve(mix(corporate=(s_c, {"corp_loans": 1.0}), retail=(1 - s_c, EX_RETAIL)))
    assert all(close(w, 1.0, 1e-12) for w in flat.values()) and set(flat) == set(EX_LOANS)
    assert _ex_resolve("loans") == "loans" and _ex_resolve({"corp_loans": 2.0}) == {"corp_loans": 2.0}
    seven = _ex_resolve(mix(one=(1.0, {b: 7.0 for b in EX_RETAIL})))
    assert seven == {b: 1.0 for b in EX_RETAIL}


def check_mix_refusals() -> None:
    """Отказы смеси: |Σ s − 1| > 1e-9 (с суммой), пустая смесь, все веса компоненты нулевые, уровень компоненты на якоре
    не больше нуля, номинал (функцией ядра — с объяснением; схемой — вид не подходит), чужая книга (схема)."""
    refused(lambda: _ex_resolve(mix(a=(0.5, "loans"), b=(0.4, EX_RETAIL))), "сумма долей смеси 0.9")
    refused(lambda: _ex_resolve({"mix": {}}), "пустая смесь")
    refused(lambda: _ex_resolve(mix(a=(1.0, {"cards": 0.0}))), "все веса нулевые")
    refused(lambda: _ex_resolve(mix(a=(1.0, "nominal"))), "номинал не остаток книг")
    zero = dict(EX_E0, cards=0.0)
    from model.book import BookRoles
    from model.cell import compile_mix
    roles = BookRoles(names=tuple(EX_E0), assets=EX_LOANS, liabilities=(), loans=EX_LOANS, retail=(), corp_funds=(),
                      funds=())
    refused(lambda: compile_mix({"a": {"share": 1.0, "base": {"cards": 1.0}}}, "x.mix", books=EX_E0, roles=roles,
                                balances=zero), "не больше нуля")
    refused(lambda: S.book_of(fees__volume_base=mix(a=(1.0, "nominal"))), "не подходит ни под один вид")
    refused(lambda: S.book_of(fees__volume_base=mix(a=(1.0, {"noise": 1.0}))), "не подходит ни под один вид")
    refused(lambda: S.book_of(fees__volume_base=mix(a=(1.2, "loans"))), "не подходит ни под один вид")
    assert S.book_of(fees__volume_base=mix(a=(0.5, "loans"), b=(0.5, T_RETAIL))).get(FEES_B)["mix"]["a"]["share"] == 0.5


@functools.lru_cache(maxsize=None)
def _mix_run(changes: tuple = ()) -> Any:
    """Сетка фикстуры `core_t` на фактах с историей книг (`support_core_p1.t_facts_with_books`) с подменами."""
    from model.book import book_from_dict
    from model.grid import run_grid
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import book_live, put, t_dict
    data = t_dict()
    for dotted, value in changes:
        put(data, dotted, json.loads(value))
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, book_live(book))


def mix_run(**changes: Any) -> Any:
    return _mix_run(tuple(sorted((k.replace("__", "."), json.dumps(v)) for k, v in changes.items())))


def _same_lines(a: Any, b: Any, rel: float, rows: tuple[str, ...] = ("fees", "ins", "opex", "rwa")) -> None:
    for x, y in zip(a.cells, b.cells):
        assert close(x.v_ri, y.v_ri, rel), (x.label, x.v_ri, y.v_ri)
        for name in rows:
            for q in range(1, a.ctx.timeline.Q + 1):
                assert close(x.quarters[name][q], y.quarters[name][q], rel), (x.label, name, q)


def check_mix_equivalences() -> None:
    """Фикстура `core_t` (связи строк 0,5 / 0,5 / 0,4): смесь из одной компоненты ≡ её база — веса 1 на кредитных
    книгах (1e-12) и слово loans (1e-9: история balance.history.loans против книг), веса × 7 (1e-12); смесь двух баз ≡
    её компилированный словарь в книге (бит в бит); доля меняет входы прохода; без ключа и словом — бит в бит."""
    from model.cell import FEES_BASE, resolve_line_base
    words = mix_run(fees__volume_base="loans", other__insurance_volume_base="loans")
    dict1 = mix_run(fees__volume_base={b: 1.0 for b in T_LOANS})
    one = mix_run(fees__volume_base=mix(all=(1.0, "loans")))
    _same_lines(one, dict1, 1e-12)
    _same_lines(one, mix_run(), 1e-9)
    _same_lines(mix_run(fees__volume_base=mix(r=(1.0, {b: 7.0 for b in T_RETAIL}))),
                mix_run(fees__volume_base=T_RETAIL), 1e-12)
    assert [c.v_ri for c in words.cells] == [c.v_ri for c in mix_run().cells]
    two = mix_run(fees__volume_base=mix(corp=(0.6, {"corp_loans": 1.0, "sme_loans": 1.0}), retail=(0.4, T_RETAIL)))
    ctx = two.ctx
    compiled = resolve_line_base(ctx.book, FEES_BASE, roles=ctx.prep.roles, balances=ctx.prep.af.balances)
    assert set(compiled) == set(T_LOANS) and max(compiled.values()) == 1.0
    as_dict = mix_run(fees__volume_base=compiled)
    assert [c.v_ri for c in as_dict.cells] == [c.v_ri for c in two.cells]
    other = mix_run(fees__volume_base=mix(corp=(0.7, {"corp_loans": 1.0, "sme_loans": 1.0}), retail=(0.3, T_RETAIL)))
    assert _path_key(other) != _path_key(two) and _moves_every_world(other, two) and other.point != two.point
    w = ctx.prep.fees_line.weights
    ref = w["corp_loans"]
    assert all(close(w[b] / ref, compiled[b] / compiled["corp_loans"], 1e-15) for b in compiled)


def _guar(**kw: Any) -> dict[str, Any]:
    spec = {"enabled": True, "notional": {"nonfinancial": 300.0, "financial": 50.0},
            "ccf": {"nonfinancial": 0.5, "financial": 1.0}, "weight": 1.0, "carve_from": "corp_loans",
            "driver": "fees_base"}
    spec.update(kw)
    return spec


def check_mix_guarantees_and_driven() -> None:
    """К5 по смеси комиссий: G_q = G_0 Σ_k s_k D^k_q / D^k_0 — концы кварталов книг клетки (заново); база гарантий —
    тот же словарь, что `resolve_line_base`. К6: книга страховых за смесью страхования с компонентой средств клиентов
    — отказ «круг» (по компилированному словарю); со смесью кредитных книг — книга за драйвером."""
    from model.cell import FEES_BASE, resolve_line_base
    fees = mix(corp=(0.6, {"corp_loans": 1.0, "sme_loans": 1.0}), retail=(0.4, T_RETAIL))
    run = mix_run(fees__volume_base=fees, capital__rwa__guarantees=_guar())
    ctx = run.ctx
    prep, tl = ctx.prep, ctx.timeline
    assert prep.guar.base.weights == resolve_line_base(ctx.book, FEES_BASE, roles=prep.roles,
                                                       balances=prep.af.balances)
    from model.capital import fx_index
    e0 = prep.af.balances
    corp0, ret0 = e0["corp_loans"] + e0["sme_loans"], sum(e0[b] for b in T_RETAIL)
    for c in run.cells:
        mult = prep.regimes[c.regime].rwa_mult
        x = fx_index(ctx.book, ctx.worlds[c.world].cpi, tl.Q)
        for q in range(1, tl.Q + 1):
            e = {b: c.books[b]["balance"][q] for b in T_LOANS}
            ratio = 0.6 * (e["corp_loans"] + e["sme_loans"]) / corp0 + 0.4 * sum(e[b] for b in T_RETAIL) / ret0
            g = c.quarters["rwa_guar"][q] / (prep.dn[q] * x[q] * (1.0 if mult is None else mult[q]))
            assert close(g, prep.guar.g0 * ratio, 1e-12), (c.label, q, g, prep.guar.g0 * ratio)
    from model.book import book_from_dict
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict

    def book(**kw: Any) -> Any:
        data = t_dict()
        for k, v in kw.items():
            put(data, k.replace("__", "."), v)
        return book_from_dict(data, facts=t_facts_with_books())
    from model.grid import run_grid
    from tests.support_core_t import book_live
    bad = book(volumes__liability_drivers={"corp_funds": "insurance"},
               other__insurance_volume_base=mix(loans=(0.5, "loans"), funds=(0.5, "funds")))
    refused(lambda: run_grid(bad, t_facts_with_books(), book_live(bad)), "круг")
    good = mix_run(volumes__liability_drivers={"corp_funds": "insurance"},
                   other__insurance_volume_base=mix(loans=(0.5, "loans"), retail=(0.5, T_RETAIL)))
    lb, _ = good.ctx.prep.driven["corp_funds"]
    assert lb.kind == "books" and set(lb.weights) == set(T_LOANS)


def check_mix_shares_and_memo() -> None:
    """Доля франшизы расходов за базой комиссий по смеси (opex.line_shares): смесь базы расходов на якоре без ступени
    (A^C_0 = B^C_0); доля на смеси из одной компоненты «кредиты» ≡ доля на базе «кредиты» (1e-9). Смесь с компонентой
    «процентные активы» выключает память оценок шага — оценка с дивидендом после оценки без него та же, что без
    памяти."""
    from model.cell import _Cell, initial_state
    run = mix_run(fees__volume_base=mix(corp=(0.6, {"corp_loans": 1.0, "sme_loans": 1.0}), retail=(0.4, T_RETAIL)),
                  opex__line_shares={"fees": 0.2})
    prep = run.ctx.prep
    assert close(prep.hist_vol_mix[0], prep.hist_vol[0], 1e-12) and prep.line_shares == {"fees": 0.2}
    a = mix_run(fees__volume_base=mix(all=(1.0, "loans")), opex__line_shares={"fees": 0.2})
    b = mix_run(fees__volume_base="loans", opex__line_shares={"fees": 0.2})
    _same_lines(a, b, 1e-9)
    iea = mix_run(fees__volume_base=mix(iea=(0.3, "iea"), loans=(0.7, "loans")))
    ctx = iea.ctx
    assert ctx.prep.memo_off and ctx.prep.fees_line.balancing and ctx.prep.growth is not None
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(ctx.prep)
    parts = ((40.0, 1, 1),)
    memo: dict = {}
    cell.evaluate(st, 1, (), 0.5, memo=memo)
    with_memo = cell.evaluate(st, 1, parts, 0.5, memo=memo)[0]
    fresh = cell.evaluate(st, 1, parts, 0.5)[0]
    assert with_memo["fees"] == fresh["fees"] and with_memo["opex"] == fresh["opex"]


# ------------------------------------------------------------------ выпуск с ключами третьего прохода (П§2)

PASS3_KEYS = {
    "valuation__terminal__year_basis": "mean", "valuation__terminal__fade_anchor_year": 2035,
    "valuation__terminal__fixed_funding": "balancing",
    CASH: {"amount": T_CASH, "driver": "funds"}, CASH_W: T_CASH_W,
    "fees__volume_base": {"mix": {"corp": {"share": 0.6, "base": {"corp_loans": 1.0, "sme_loans": 1.0}},
                                  "retail": {"share": 0.4, "base": "loans"}}},
}


@functools.lru_cache(maxsize=None)
def pass3_release(keys: bool = True) -> tuple[Any, dict]:
    """Быстрый выпуск фикстуры `core_t` на фактах с историей книг: блок К-Т (λ_F = 0) и угасание 0,5; с ключами
    третьего прохода (`PASS3_KEYS`: год терминала mean, год-якорь угасания 2035 — s = 1, ставка блока balancing, деньги за
    средствами клиентов, смесь баз комиссий) или без них."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    data = t_dict()
    base = {"valuation__terminal__fixed_growth_share": 0.0, "valuation__terminal__fade": 0.5,
            "checks__mix_ratio_tolerance": 0.002}
    for k, v in {**base, **(PASS3_KEYS if keys else {})}.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    return rel, P.build_payload(rel)


def check_release_with_pass3_keys() -> None:
    """Выпуск с ключами третьего прохода: контракт выполнен; узлы клетки terminal_year {days_l, nu_l, psi,
    day_weighted_l, adj}, terminal_fade {s, n, phi} и поля блока К-Т bound_after_payout, wt_after, min_liquidity — в
    каждой клетке и с числами клетки (шагом печати); без ключей — ни узлов, ни полей (прежняя печать)."""
    from model import payload as P
    from tests.support_core2 import contract
    rel, d = pass3_release(True)
    problems = contract(d)
    assert problems == [], problems[:5]
    cells = {(c["world"], c["regime"], c["scenario"]): c for c in d["grid"]["cells"]}
    for c in rel.run.cells:
        node = cells[c.key]
        year, fade, fixed = node["terminal_year"], node["terminal_fade"], node["terminal_fixed"]
        assert year["days_l"] == 366 and year["psi"] == P.R_SHARE(MEAN_DAYS / DAYS)
        assert year["adj"] == P.R_MONEY(c.terminal_year["adj"])
        assert fade["s"] == 1 and fade["phi"] == P.R_SHARE(c.terminal_fade["phi"]) and fade["phi"] < 0.5
        assert fixed["bound_after_payout"] is c.terminal_fixed["bound_after_payout"]
        assert fixed["min_liquidity"] == P.R_MONEY(c.terminal_fixed["min_liquidity"])
        assert "cash" in c.quarters
    _, plain = pass3_release(False)
    assert contract(plain) == []
    for node in plain["grid"]["cells"]:
        assert "terminal_year" not in node and "terminal_fade" not in node
        assert "bound_after_payout" not in node["terminal_fixed"] and "min_liquidity" not in node["terminal_fixed"]
