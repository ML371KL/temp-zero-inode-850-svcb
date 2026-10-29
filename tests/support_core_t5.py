"""Проверки мира-опоры κ, симметричного угасания, сторожей уровней и узлов «на чём стоит заголовок» на фикстуре
`tests/fixtures/core_t`.

Одни и те же проверки зовут тесты (`tests/test_core_t_w5.py`, `tests/test_core2_t_w5.py`) и мутационный набор
(`tests/mutations.py`); каждая — тождество или закрытая формула, выведенная из книги, фактов и рядов клеток
независимо от кода ядра:

* **мир-опора κ** (М§4.6): CoR клетки = путь режима + κ × (реальная ставка мира − реальная ставка мира-опоры) с
  лагом, знак любой; без ключа — только превышение над базовым миром; кредитная маржа стационара — та же добавка;
* **симметричное угасание** (М§7): ROE терминала = k + fade × (ROE − k) при любом знаке; без ключа — одностороннее;
* **сторожа уровней** (М§14.2): стационарная маржа мира-цели (`nim_stationary`), уровни слоя «рыночные ставки как
  есть» против коридоров окна (`window_backtest`), долгосрочный C/I слоя (`cir_lt` с областью), стоимость средств
  клиентов к ключевой ставке (`funds_cost_to_key`) — числа пересчитываются по рядам клеток;
* **узлы** (М§14.5): уровни после фазы роста (`levels`), путь смеси точки (`point_path`), справочные варианты
  (`reference_variants`), стационарная маржа и уровни у строки обратного расчёта по ключу цели ЧПМ;
* **обратный расчёт** (М§11.2): решение подвыборки у края диапазона уточняется на полной полосе по ключу книги.

Ключей этих механик в книге фикстуры нет (нет ключа — прежнее поведение, и числа прочих тестов не сдвигаются):
проверки включают их подменой — `FINAL_KEYS` (значения фикстуры, не книги); тем же словарём их включает
сверка с контрольной моделью.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
from typing import Any

from model import book_results as BR
from model import payload as P
from model import uncertainty as U
from model.checks import check_gates
from model.credit import kappa_addon
from model.grid import GridRun, modal_cell, point_probabilities, run_grid
from model.levels import (LEVEL_METRICS, LEVEL_ROWS, cir_lt_value, funds_cost_to_key, levels, point_path,
                          stationary_nim)
from model.live import apply_live
from model.nii import nim_key_for_stationary, nss_value, solve_transmission
from model.reverse import NIM_PATH
from tests import support_core_t3 as S
from tests import support_core_t4 as S4
from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
from tests.support_core_t import book_live, t_facts

close = S.close
gate, refused = S4.gate, S4.refused

KAPPA_WORLD = "credit__kappa_reference_world"
FADE, FADE_MODE = "valuation__terminal__fade", "valuation__terminal__fade_mode"
NIM_ST, WINDOW, FUNDS, POINT = ("checks__nim_stationary", "checks__window_backtest", "checks__funds_cost_to_key",
                                "checks__point_path")
SCOPE = "checks__cir_lt__scope"
VARIANTS = "valuation__reference_variants"
EDGE = "valuation__reverse_dcf__edge_refine_rub"
# Справочные варианты фикстуры: новый необязательный ключ, число книги, элемент траектории.
VARIANT_LIST = [
    {"id": "fade_symmetric", "title": "Угасание при любом знаке избытка",
     "overrides": {"valuation.terminal.fade_mode": "symmetric"}},
    {"id": "kappa_zero", "title": "Стоимость риска без связи с реальной ставкой", "overrides": {"credit.kappa": 0.0}},
    {"id": "catch_up", "title": "Навёрстывание урезанного роста",
     "overrides": {"capital.growth_constraint.catch_up_rate": 0.5, "opex.real_growth.2027": 0.03}},
]
# Ключи панели в значениях фикстуры (не книги): мир-опора κ, сторожа уровней, узлы, варианты.
FINAL_KEYS: dict[str, Any] = {
    "credit.kappa_reference_world": "M",
    "valuation.terminal.fade": 0.5,
    "checks.nim_stationary": {"world": "M", "target": 0.1053, "tolerance": 0.0005},
    "checks.window_backtest": {"from_year": 2030, "cor": [0.040, 0.065], "cir": [0.44, 0.50]},
    "checks.funds_cost_to_key": {"max": 0.71, "from_year": 2030},
    "checks.cir_lt.scope": "market_layer",
    "checks.point_path": True,
    "valuation.reference_variants": VARIANT_LIST,
}


def keyed(**extra: Any) -> dict[str, Any]:
    """Замены книги фикстуры: все ключи панели (`FINAL_KEYS`) и добавочные (`__` вместо точки)."""
    return {**{k.replace(".", "__"): v for k, v in FINAL_KEYS.items()}, **extra}


def with_keys(run: GridRun, **changes: Any) -> GridRun:
    """Тот же прогон с книгой, в которой заменены ключи проверок: числа клеток от них не зависят — сетка не
    пересчитывается, гейты и узлы читают новые ключи."""
    book = run.ctx.book.with_overrides({k.replace("__", "."): v for k, v in changes.items()}, create=True)
    return dataclasses.replace(run, ctx=dataclasses.replace(run.ctx, book=book))


# ------------------------------------------------------------------ мир-опора κ


def check_kappa_world() -> None:
    """CoR клетки = путь режима + κ-добавка + отклонение A-P2u: при названном мире-опоре добавка —
    κ × (rr_W − rr_опоры) с лагом, любого знака (в мире-опоре ноль, в мире с меньшей реальной ставкой — минус);
    без ключа — κ × max(0, rr_W − rr_N). Та же разность — в кредитной марже стационара."""
    facts = t_facts()
    plain, moved = S.grid_of(), S.grid_of(**{KAPPA_WORLD: "M"})
    book = plain.ctx.book
    kappa, lag = float(book.get("credit.kappa")), int(book.get("credit.real_rate_lag_q"))
    assert kappa > 0 and lag >= 1
    Q = plain.ctx.timeline.Q
    lower = 0
    for run, ref, signed in ((plain, "N", False), (moved, "M", True)):
        assert run.ctx.prep.kappa_world == (ref if signed else None)
        rr_ref = run.ctx.worlds[ref].real_key
        for w in book.get("worlds.ids"):
            rr = run.ctx.worlds[w].real_key
            for regime, scenario in (("norm", "schedule"), ("downturn", "mid")):
                c = run.cell(w, regime, scenario)
                path = run.ctx.prep.regimes[regime].cor_engine
                dev = run.ctx.deviations.get(regime, {}).get("cor")
                for q in range(1, Q + 1):
                    gap = rr[q - lag] - rr_ref[q - lag] if q - lag >= 1 else 0.0
                    add = kappa * (gap if signed else max(0.0, gap))
                    want = path[q] + add + (dev[q] if dev is not None else 0.0)
                    assert close(c.quarters["cor"][q], want, rel=1e-9, abs_=1e-12), (ref, c.label, q)
                    lower += signed and add < -1e-6
                    if w == ref or q <= lag:
                        assert add == 0.0
    assert lower > 0                                             # в мирах ниже мира-опоры добавка отрицательна
    n_plain, n_moved = plain.cell("N", "norm", "mid"), moved.cell("N", "norm", "mid")
    assert n_moved.quarters["cor"][Q] < n_plain.quarters["cor"][Q] - 1e-4 and n_moved.v_ri > n_plain.v_ri
    # кредитная маржа стационара: та же разность реальных ставок последнего квартала
    last = Q
    for w in book.get("worlds.ids"):
        real = {v: plain.ctx.worlds[v].real_key[last] for v in ("N", "M", w)}
        was = kappa * max(0.0, real[w] - real["N"])
        now = kappa * (real[w] - real["M"])
        got = moved.ctx.transmission.loan_margin[w] - plain.ctx.transmission.loan_margin[w]
        assert close(got, was - now, abs_=1e-12), w
    # закрытая формула на построенных рядах: знак любой, лаг, история до сетки — ноль
    rr_w, rr_ref = (0.0, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09), (0.0, 0.06, 0.06, 0.06, 0.06, 0.06, 0.06)
    assert kappa_addon(0.5, 2, rr_w, rr_ref, 6, signed=True) == (0.0, 0.0, 0.0, 0.5 * (0.04 - 0.06),
                                                                  0.5 * (0.05 - 0.06), 0.0, 0.5 * (0.07 - 0.06))
    assert kappa_addon(0.5, 2, rr_w, rr_ref, 6)[3:5] == (0.0, 0.0)          # без ключа добавка вниз не идёт
    # лёгкая сетка (проходы клеток по мирам) читает путь мира-опоры κ: та же точка, что у полной
    light = run_grid(moved.ctx.book, facts, moved.ctx.live, summary=True)
    assert close(light.point, moved.point, rel=1e-12) and abs(moved.point - plain.point) > 1.0
    refused(lambda: S.book_of(**{KAPPA_WORLD: "X"}), "credit.kappa_reference_world")


# ------------------------------------------------------------------ симметричное угасание


def check_fade_symmetric() -> None:
    """Угасание избыточной доходности терминала: без ключа и при `one_sided` — только положительного избытка;
    при `symmetric` — ROE'_T = k_T + fade × (ROE_T − k_T) при любом знаке. Клетки с ROE_T не ниже k_T от вида
    угасания не зависят; у прочих симметричное угасание возвращает долю отрицательного терминала."""
    half = {FADE: 0.5}
    one, named, both = S.grid_of(**half), S.grid_of(**half, **{FADE_MODE: "one_sided"}), S.grid_of(
        **half, **{FADE_MODE: "symmetric"})
    assert [c.v_ri for c in named.cells] == [c.v_ri for c in one.cells] and named.point == one.point
    below = [c.key for c in one.cells if c.roe_t_raw < c.k_t]
    assert 0 < len(below) < len(one.cells)
    for a, b in zip(one.cells, both.cells):
        assert a.roe_t_raw == b.roe_t_raw and a.k_t == b.k_t and a.bv_star == b.bv_star
        assert close(b.roe_t, b.k_t + 0.5 * (b.roe_t_raw - b.k_t), abs_=1e-15), b.label
        assert close(b.tv_ri, (b.roe_t - b.k_t) * b.bv_star / (b.k_t - b.g_t), rel=1e-12)
        if a.key in below:
            assert close(a.roe_t, a.roe_t_raw, abs_=1e-15) and b.roe_t > a.roe_t and b.v_ri > a.v_ri, a.label
        else:
            assert b.roe_t == a.roe_t and b.v_ri == a.v_ri, a.label
    assert both.point > one.point + 0.5
    refused(lambda: S.book_of(**{FADE_MODE: "both"}), "valuation.terminal.fade_mode")


# ------------------------------------------------------------------ стационарная маржа мира-цели


def check_nim_stationary() -> None:
    """Гейт `nim_stationary`: стационарная маржа решателя передачи на составе якоря в мире ключа, через мост в
    упр. базис, против цели с допуском; в мире-опоре передачи она равна ключу цели ЧПМ; ключ под цель мира
    выводится линейно. Без ключа нет ни гейта, ни числа."""
    facts = t_facts()
    plain = S.grid_of()
    book, br, tr = plain.ctx.book, plain.ctx.bridge, plain.ctx.transmission
    assert gate(plain, "nim_stationary") is None and stationary_nim(plain.ctx) is None
    tol = 0.0005
    want = {w: br.to_mgmt_nim(nss_value(book, facts, w, 0.0, tr.sigma0, tr.phi, tr.sigma0_liab))
            for w in book.get("worlds.ids")}
    ref = str(book.get("nii.transmission.reference_world"))
    assert close(want[ref], float(book.get("nii.nim_lt_target_mgmt")), abs_=1e-12) and abs(want["M"] - want[ref]) > 1e-5
    for target, fired in ((want["M"], False), (want["M"] + 0.9 * tol, False), (want["M"] + 1.1 * tol, True),
                          (want["M"] - 1.1 * tol, True)):
        run = with_keys(plain, **{NIM_ST: {"world": "M", "target": target, "tolerance": tol}})
        node, found = stationary_nim(run.ctx), gate(run, "nim_stationary")
        assert close(node["value"], want["M"], abs_=1e-12) and node["world"] == "M" and node["target"] == target
        assert node["key"] == float(book.get("nii.nim_lt_target_mgmt"))
        assert found.fired is fired and found.mass == (1.0 if fired else 0.0), (target, found.message)
        assert "мира M" in found.message and f"мира {ref})" in found.message
    other = with_keys(plain, **{NIM_ST: {"world": "N", "target": want["N"], "tolerance": tol}})
    assert close(stationary_nim(other.ctx)["value"], want["N"], abs_=1e-12) and not gate(other, "nim_stationary").fired
    # ключ под суждение о стационарной марже мира: при нём гейт проходит с нулевым отклонением
    goal = want["M"] + 0.004
    key = nim_key_for_stationary(book, facts, br, "M", goal)
    solved = solve_transmission(book.with_overrides({"nii.nim_lt_target_mgmt": key}), facts, br)
    assert close(br.to_mgmt_nim(solved.nss["M"]), goal, abs_=1e-12) and abs(key - float(book.get("nii.nim_lt_target_mgmt"))) > 1e-3
    refused(lambda: S.book_of(**{NIM_ST: {"world": "X", "target": 0.1, "tolerance": tol}}), "checks.nim_stationary.world")


# ------------------------------------------------------------------ уровни после фазы роста


def layer_levels(run: GridRun, prob: dict, years: list[int]) -> dict[str, float]:
    """Уровни смеси клеток по рядам клеток: год — отношение ожидаемых агрегатов (ЧПД к среднему пяти концов
    процентных активов, резервы к средним кредитам по амортизированной стоимости, расходы к операционному
    доходу), через мост в упр. базис; уровень — простое среднее лет. Годы — без отчётных кварталов."""
    tl, br = run.ctx.timeline, run.ctx.bridge
    e = lambda name, q: sum(prob[c.key] * c.quarters[name][q] for c in run.cells)  # noqa: E731
    rows: dict[str, list[float]] = {"nim": [], "cor": [], "cir": [], "loans_share": []}
    for y in years:
        qs = tl.quarters_of_year(y)
        ends = [qs[0] - 1] + qs
        assert qs[0] >= 1
        income = sum(e(k, q) for k in ("nii", "fees", "ins", "misc", "fvr") for q in qs)
        rows["nim"].append(br.to_mgmt_nim(sum(e("nii", q) for q in qs) / (sum(e("iea", q) for q in ends) / 5)))
        rows["cor"].append(br.to_mgmt_cor(sum(e("llp", q) for q in qs) / (sum(e("loans_ac", q) for q in ends) / 5)))
        rows["cir"].append(br.to_mgmt_cir(sum(e("opex", q) for q in qs) / income))
        rows["loans_share"].append(sum(e("loans", q) for q in ends) / sum(e("iea", q) for q in ends))
    return {k: sum(v) / len(v) for k, v in rows.items()}


def level_probabilities(run: GridRun) -> dict[str, dict]:
    modal = modal_cell(run.ctx.book, run.ctx.posterior)
    lam, own, low = run.lam, run.layers["analytical"].prob, run.layers["macro_neutral"].prob
    return {"modal_cell": {c.key: float(c.key == modal) for c in run.cells}, "analytical": own,
            "point": {k: lam * own[k] + (1 - lam) * low[k] for k in own}, "macro_neutral": low}


def check_levels() -> None:
    """Узел `levels`: четыре строки — модальная клетка, слой «свой взгляд», смесь точки, слой «рыночные ставки как
    есть»; уровень — среднее лет от `from_year`; слои — отношение ожидаемых агрегатов, а не ожидание отношений
    клеток; строка модальной клетки — годовые ряды самой клетки. Гейт `window_backtest` судит CoR и C/I слоя
    «рыночные ставки как есть»; маржу не судит. Без ключа нет ни узла, ни гейта."""
    plain = S.grid_of()
    assert levels(plain) is None and gate(plain, "window_backtest") is None
    first = 2030
    years = list(range(first, plain.ctx.timeline.last_year + 1))
    probs = level_probabilities(plain)
    want = {key: layer_levels(plain, prob, years) for key, prob in probs.items()}
    wide = {"from_year": first, "cor": [0.0, 1.0], "cir": [0.0, 2.0]}
    run = with_keys(plain, **{WINDOW: wide})
    node = levels(run)
    assert node["order"] == list(LEVEL_ROWS) == list(want) and node["years"] == years
    assert (node["from_year"], node["to_year"]) == (first, years[-1])
    assert node["cell"] == "/".join(modal_cell(run.ctx.book, run.ctx.posterior))
    for key, row in node["rows"].items():
        for k, v in want[key].items():
            assert close(row[k], v, rel=1e-10), (key, k)
            assert len(row["by_year"][k]) == len(years) and close(sum(row["by_year"][k]) / len(years), v, rel=1e-10)
    # строка модальной клетки — её собственная печатаемая маржа (среднее годовых упр. ЧПМ клетки)
    mean, _ = S4.nim_mean(plain, first)
    assert close(node["rows"]["modal_cell"]["nim"], mean, rel=1e-10)
    # отношение ожидаемых агрегатов — не ожидание отношений клеток: на слое из многих клеток они различны
    low = probs["macro_neutral"]
    br = plain.ctx.bridge
    naive = sum(low[c.key] * br.to_mgmt_cir(sum(c.annual["cir"][c.years.index(y)] for y in years) / len(years))
                for c in plain.cells)
    assert abs(naive - want["macro_neutral"]["cir"]) > 1e-5
    later = levels(run, first + 3)
    assert later["years"] == years[3:] and abs(later["rows"]["point"]["nim"] - node["rows"]["point"]["nim"]) > 1e-6
    # гейт: коридоры окна для CoR и C/I слоя «рыночные ставки как есть»
    cor, cir, nim = (want["macro_neutral"][k] for k in ("cor", "cir", "nim"))
    quiet = gate(run, "window_backtest")
    assert not quiet.fired and quiet.mass == 0.0 and S4.gate(run, "nim_stationary") is None
    for band, outside in (({"cor": [cor - 0.002, cor + 0.002], "cir": [cir - 0.01, cir + 0.01]}, []),
                          ({"cor": [cor + 0.001, cor + 0.01], "cir": [cir - 0.01, cir + 0.01]}, ["cor"]),
                          ({"cor": [cor - 0.002, cor + 0.002], "cir": [cir - 0.03, cir - 0.001]}, ["cir"]),
                          ({"cor": [0.0, cor - 0.001], "cir": [cir + 0.001, 2.0]}, ["cor", "cir"])):
        found = gate(with_keys(plain, **{WINDOW: {"from_year": first, **band}}), "window_backtest")
        assert found.fired is bool(outside) and found.mass == float(bool(outside)), (band, found.message)
        assert found.detail["outside"] == outside and close(found.detail["nim"], nim, rel=1e-10)
        assert "гейтом не сверяется" in found.message
    refused(lambda: S.book_of(**{WINDOW: {**wide, "from_year": 2099}}), "checks.window_backtest.from_year")
    refused(lambda: S.book_of(**{WINDOW: {**wide, "cor": [0.07, 0.04]}}), "checks.window_backtest.cor")


def check_cir_scope() -> None:
    """Гейт `cir_lt` с областью: без ключа и при `modal_cell` — модальная клетка (число и сообщение прежние); при
    `market_layer` — среднее упр. C/I слоя «рыночные ставки как есть» за годы гейта, отношение ожидаемых
    агрегатов. Число гейта — `cir_lt_value`: его же читает лист книги, который выводит корни расходов."""
    plain = S.grid_of()
    cfg = dict(plain.ctx.book.get("checks.cir_lt"))
    assert "scope" not in cfg
    first = int(cfg["from_year"])
    years = list(range(first, plain.ctx.timeline.last_year + 1))
    probs = level_probabilities(plain)
    cell, layer = layer_levels(plain, probs["modal_cell"], years)["cir"], layer_levels(plain, probs["macro_neutral"],
                                                                                    years)["cir"]
    assert abs(cell - layer) > 0.005
    base = gate(plain, "cir_lt")
    named = with_keys(plain, **{SCOPE: "modal_cell"})
    same = gate(named, "cir_lt")
    assert (same.fired, same.mass, same.cells, same.message) == (base.fired, base.mass, base.cells, base.message)
    assert close(cir_lt_value(plain)["value"], cell, rel=1e-10) and cir_lt_value(plain)["scope"] == "modal_cell"
    tol = float(cfg["tolerance"])
    for target, fired in ((layer, False), (layer + 0.9 * tol, False), (layer + 1.1 * tol, True), (cell, abs(cell - layer) > tol)):
        run = with_keys(plain, **{"checks__cir_lt": {**cfg, "target": target, "scope": "market_layer"}})
        got, found = cir_lt_value(run), gate(run, "cir_lt")
        assert got["scope"] == "market_layer" and close(got["value"], layer, rel=1e-10) and close(got["modal"], cell, rel=1e-10)
        assert got["years"] == years and found.fired is fired and found.mass == float(fired), (target, found.message)
        assert "слоя «рыночные ставки как есть»" in found.message and found.cells == ()
    refused(lambda: S.book_of(**{SCOPE: "layer"}), "checks.cir_lt.scope")


def funds_ratio(run: GridRun, world: str, first: int) -> float:
    """Стоимость средств клиентов к ключевой ставке в клетке «мир × модальный режим × модальный сценарий» за годы
    от `first` — по рядам книг клетки: проценты по книгам средств клиентов к их средним остаткам, оба — по дням."""
    tl = run.ctx.timeline
    _, regime, scenario = modal_cell(run.ctx.book, run.ctx.posterior)
    c = run.cell(world, regime, scenario)
    books = [b for b, spec in run.ctx.book.get("nii.books").items()
             if spec["side"] == "liability" and not spec.get("balancing")]
    qs = [q for y in range(first, tl.last_year + 1) for q in tl.quarters_of_year(y)]
    days = {q: (tl.end(q) - tl.end(q - 1)).days for q in qs}
    paid = sum(c.books[b]["rate"][q] * c.books[b]["avg"][q] * days[q] for b in books for q in qs)
    held = sum(c.books[b]["avg"][q] * days[q] for b in books for q in qs)
    key = sum(run.ctx.worlds[world].key[q] * days[q] for q in qs) / sum(days.values())
    return paid / held / key


def check_funds_cost() -> None:
    """Гейт `funds_cost_to_key`: три числа — по миру, в клетке модального режима и сценария; срабатывает, когда
    хотя бы одно выше порога; масса — вес таких миров в слое «свой взгляд». Без ключа нет ни гейта, ни числа."""
    plain = S.grid_of()
    assert funds_cost_to_key(plain) is None and gate(plain, "funds_cost_to_key") is None
    first = 2030
    worlds = list(plain.ctx.book.get("worlds.ids"))
    want = {w: funds_ratio(plain, w, first) for w in worlds}
    order = sorted(worlds, key=lambda w: want[w])
    assert want[order[0]] < want[order[1]] - 0.01 < want[order[2]] - 0.02
    weights = plain.layers["analytical"].world_weights
    _, regime, scenario = modal_cell(plain.ctx.book, plain.ctx.posterior)
    for limit, bad in ((want[order[2]] + 0.01, []), ((want[order[1]] + want[order[2]]) / 2, order[2:]),
                       ((want[order[0]] + want[order[1]]) / 2, order[1:]), (want[order[0]] - 0.01, order)):
        run = with_keys(plain, **{FUNDS: {"max": limit, "from_year": first}})
        node, found = funds_cost_to_key(run), gate(run, "funds_cost_to_key")
        assert {w: row["ratio"] for w, row in node["by_world"].items()}.keys() == set(worlds)
        assert all(close(node["by_world"][w]["ratio"], want[w], rel=1e-10) for w in worlds)
        assert all(node["by_world"][w]["cell"] == f"{w}/{regime}/{scenario}" for w in worlds)
        assert node["ok"] is (not bad) and found.fired is bool(bad), (limit, found.message)
        assert close(found.mass, sum(weights[w] for w in bad), abs_=1e-12)
        assert set(found.cells) == {f"{w}/{regime}/{scenario}" for w in bad}
        assert all(f"{want[w]:.3f}".replace(".", ",") in found.message for w in worlds)
        assert f"при пороге {limit:.3f}".replace(".", ",") in found.message         # число и порог — одним числом знаков
    later = funds_cost_to_key(with_keys(plain, **{FUNDS: {"max": 1.0, "from_year": first + 4}}))
    assert close(later["by_world"]["M"]["ratio"], funds_ratio(plain, "M", first + 4), rel=1e-10)
    assert abs(later["by_world"]["M"]["ratio"] - want["M"]) > 1e-6
    refused(lambda: S.book_of(**{FUNDS: {"max": 0.0, "from_year": first}}), "checks.funds_cost_to_key.max")


# ------------------------------------------------------------------ путь смеси точки


def check_point_path() -> None:
    """Узел `point_path`: годовой путь смеси точки — факт отчётных кварталов плюс ожидание клеток под
    вероятностями точки; рядом — модальная клетка: её веса в слое «свой взгляд» и в смеси точки, цена на акцию,
    прибыль по годам. Без ключа узла нет."""
    plain = S.grid_of()
    assert point_path(plain) is None and point_path(with_keys(plain, **{POINT: False})) is None
    run = with_keys(plain, **{POINT: True})
    node = point_path(run)
    tl, facts = run.ctx.timeline, t_facts()
    prob = point_probabilities(run)
    years = list(range(tl.anchor_year, tl.last_year + 1))
    assert node["years"] == years and all(len(node[k]) == len(years) for k in ("ni_sh", "nim_mgmt", "cor_mgmt",
                                                                                 "cir_mgmt", "roe", "dps"))
    for i, y in enumerate(years):
        fact = sum(facts.need("pnl_quarterly", f"quarters.{tl.period(q)}.ni_shareholders")
                   for q in tl.quarters_of_year(y) if q <= 0)
        model = sum(prob[c.key] * c.quarters["ni_sh"][q] for c in run.cells for q in tl.quarters_of_year(y) if q >= 1)
        assert close(node["ni_sh"][i], fact + model, rel=1e-10), y
        dps = [c.dps.get(y) for c in run.cells]
        if None in dps:
            assert node["dps"][i] is None
        else:
            assert close(node["dps"][i], sum(prob[c.key] * v for c, v in zip(run.cells, dps)), rel=1e-10)
    full = [y for y in years if tl.quarters_of_year(y)[0] >= 1]
    want = layer_levels(run, prob, full)
    for k, name in (("nim", "nim_mgmt"), ("cor", "cor_mgmt"), ("cir", "cir_mgmt")):
        assert close(sum(node[name][years.index(y)] for y in full) / len(full), want[k], rel=1e-10), k
    key = modal_cell(run.ctx.book, run.ctx.posterior)
    c = run.cell(*key)
    mc = node["modal_cell"]
    assert mc["cell"] == c.label and mc["p_analytical"] == run.layers["analytical"].prob[key]
    assert close(mc["p_point"], prob[key], abs_=1e-15) and mc["p_point"] != mc["p_analytical"]
    assert mc["price"] == run.cell_price(c) and mc["v"] == c.v_ri and mc["ni_sh"] == list(c.annual["ni_sh"])
    assert abs(mc["ni_sh"][-1] - node["ni_sh"][-1]) > 1.0


# ------------------------------------------------------------------ справочные варианты


def check_reference_variants() -> None:
    """Справочные варианты: строка на вариант списка книги — точка книги с подменами варианта и её разность с
    точкой книги; подмена вводит новый необязательный ключ и меняет элемент траектории; вариант, чья книга не
    проходит схему, — отказ с его идентификатором; без списка узла нет."""
    facts = t_facts()
    plain = S.grid_of(**{FADE: 0.5})
    live = plain.ctx.live
    assert BR.reference_variants(plain.ctx.book, facts, live, plain) is None
    book = S.book_of(**{FADE: 0.5, VARIANTS: VARIANT_LIST})
    rows = BR.reference_variants(book, facts, live, plain)
    assert [(r["id"], r["title"]) for r in rows] == [(v["id"], v["title"]) for v in VARIANT_LIST]
    manual = {"fade_symmetric": S.grid_of(**{FADE: 0.5, FADE_MODE: "symmetric"}),
              "kappa_zero": S.grid_of(**{FADE: 0.5, "credit__kappa": 0.0}),
              "catch_up": S.grid_of(**{FADE: 0.5, "capital__growth_constraint__catch_up_rate": 0.5,
                                       "opex__real_growth__2027": 0.03})}
    for r in rows:
        want = manual[r["id"]].point
        assert close(r["point"], want, rel=1e-12) and close(r["d_point"], want - plain.point, abs_=1e-9), r["id"]
        assert abs(r["d_point"]) > 0.05
    # книга варианта: список вариантов и прочие ключи — как в книге; подмена — по пути
    trial = BR.variant_book(book, VARIANT_LIST[0])
    assert trial.get("valuation.terminal.fade_mode") == "symmetric" and book.opt("valuation.terminal.fade_mode") is None
    assert trial.get("valuation.reference_variants") == book.get("valuation.reference_variants")
    bad = [{"id": "broken", "title": "Опечатка в ключе", "overrides": {"valuation.terminal.fade_mod": "symmetric"}}]
    text = refused(lambda: BR.reference_variants(S.book_of(**{VARIANTS: bad}), facts, live, plain), "broken")
    assert "fade_mod" in text
    twice = [VARIANT_LIST[1], {**VARIANT_LIST[1], "title": "Повтор"}]
    refused(lambda: S.book_of(**{VARIANTS: twice}), "повтор идентификатора")
    nested = [{"id": "own_list", "title": "Список вариантов", "overrides": {"valuation.reference_variants": []}}]
    refused(lambda: S.book_of(**{VARIANTS: nested}), "список вариантов подменой не меняют")
    orphan = [{"id": "orphan", "title": "Нет раздела", "overrides": {"credit.extra.kappa": 0.1}}]
    refused(lambda: S.book_of(**{VARIANTS: orphan}), "раздела credit.extra в книге нет")
    refused(lambda: S.book_of(**{VARIANTS: [{"id": "Bad Id", "title": "x", "overrides": {"credit.kappa": 0.1}}]}),
            "идентификатор варианта")
    refused(lambda: S.book_of(**{VARIANTS: [{"id": "empty", "title": "x", "overrides": {}}]}), "overrides")


def check_variants_table() -> None:
    """Выпуск читает справочные варианты из таблиц книги: версия книги, идентификаторы строк — по списку книги — и
    отпечаток книги; иначе узла нет. Подпись строки — книги; строки — по убыванию модуля цены правила."""
    book = S.book_of(**{VARIANTS: VARIANT_LIST})
    version = str(book.get("meta.version"))
    rows = [{"id": v["id"], "title": "старое название", "point": 400.0 + i, "d_point": float(i) - 0.004}
            for i, v in enumerate(VARIANT_LIST)]
    table = {"book_version": version, "headline": {"point": 400.0}, "reference_variants": rows,
             BR.VARIANTS_BOOK: book.digest}
    node = P.reference_variants_table(book, table)
    assert node["point"] == 400.0 and [r["title"] for r in node["rows"]] == [v["title"] for v in VARIANT_LIST][::-1]
    assert [r["point"] for r in node["rows"]] == [402.0, 401.0, 400.0] and node["rows"][1]["d_point"] == 1.0
    assert P.reference_variants_table(S.book_of(), table) is None                  # нет списка книги — узла нет
    assert P.reference_variants_table(book, {**table, "book_version": "другая"}) is None
    assert P.reference_variants_table(book, {**table, "reference_variants": rows[:2]}) is None
    assert P.reference_variants_table(book, {**table, "reference_variants": rows[::-1]}) is None
    assert P.reference_variants_table(book, {k: v for k, v in table.items() if k != "headline"}) is None


# ------------------------------------------------------------------ обратный расчёт


def check_near_range_edge() -> None:
    """Правило «решение подвыборки у края диапазона» (чистая функция): без ключа и внутри диапазона — нет; за
    краем — по невязке подвыборки на ближнем краю против порога книги."""
    from model import reverse as R
    plain, keyed_book = S.book_of(), S.book_of(**{EDGE: 3.0})
    seen: list[float] = []

    def gap_at(v: float) -> float:
        seen.append(v)
        return {0.02: 2.9, 0.05: -3.1}[v]

    assert not R.near_range_edge(plain, gap_at, 0.06, 0.02, 0.05) and not seen       # нет ключа — не считается
    assert not R.near_range_edge(keyed_book, gap_at, 0.03, 0.02, 0.05) and not seen  # внутри диапазона
    assert R.near_range_edge(keyed_book, gap_at, 0.01, 0.02, 0.05) and seen == [0.02]            # нижний край: 2,9 ≤ 3
    assert not R.near_range_edge(keyed_book, gap_at, 0.06, 0.02, 0.05) and seen == [0.02, 0.05]  # верхний: 3,1 > 3
    refused(lambda: S.book_of(**{EDGE: 0.0}), "valuation.reverse_dcf.edge_refine_rub")


def check_stationary_fields() -> None:
    """Поля суждения о марже у строки обратного расчёта по ключу цели ЧПМ в быстрой сборке: у книги с ключом
    `nim_stationary` — стационарная маржа мира-цели на книге (при корне — пусто) и место под уровни при корне
    (при ключе `window_backtest`) вместо печатаемой маржи модальной клетки; без ключа — прежние поля."""
    from model import reverse as R
    plain = S.grid_of()
    old = next(r for r in R.not_computed(plain.ctx.book, "проверка", run=plain)["rows"] if R.NIM_PATH in r["paths"])
    assert "printed_book" in old and "stationary_book" not in old           # в книге фикстуры — ключ `nim_lt`
    run = with_keys(plain, **{NIM_ST: FINAL_KEYS["checks.nim_stationary"], WINDOW: FINAL_KEYS["checks.window_backtest"]})
    rows = R.not_computed(run.ctx.book, "проверка", run=run)["rows"]
    row = next(r for r in rows if R.NIM_PATH in r["paths"])
    assert row["stationary_book"] == stationary_nim(run.ctx)["value"] and row["stationary_solved"] is None
    assert row["levels_solved"] is None and "printed_book" not in row
    assert all("stationary_book" not in r for r in rows if R.NIM_PATH not in r["paths"])
    only = with_keys(plain, **{NIM_ST: FINAL_KEYS["checks.nim_stationary"]})
    assert "levels_solved" not in next(r for r in R.not_computed(only.ctx.book, "проверка", run=only)["rows"]
                                       if R.NIM_PATH in r["paths"])
    assert all("stationary_book" not in r for r in R.not_computed(run.ctx.book, "проверка")["rows"])


def check_stationary_row() -> None:
    """Строка обратного расчёта по ключу цели ЧПМ у книги с ключом `nim_stationary`: стационарная маржа мира-цели
    на книге и при корне и уровни после фазы роста при корне (один счёт сетки) — вместо печатаемой маржи
    модальной клетки. Решение подвыборки чуть за краем диапазона при ключе `edge_refine_rub` уточняется на
    полной полосе."""
    from model import reverse as R
    keys = {**S4.SMALL_BAND, NIM_ST: FINAL_KEYS["checks.nim_stationary"], WINDOW: FINAL_KEYS["checks.window_backtest"]}
    base = S.book_of(**keys)
    facts = t_facts()
    live0 = book_live(base)
    run0 = run_grid(base, facts, live0)
    nim = next(a for a in base.get("valuation.reverse_dcf.axes") if R.NIM_PATH in a["paths"])
    b = float(base.get(R.NIM_PATH))
    on_book = stationary_nim(run0.ctx)["value"]
    edge = b + 0.006

    def setup(rng: list[float], price: float | None = None, **more: Any):
        book = S.book_of(**keys, **more, **{"valuation__reverse_dcf__axes": [{**nim, "search": [b - 0.02, b + 0.03],
                                                                             "range": rng}],
                                            "valuation__reverse_dcf__bank_rows": []})
        live = live0 if price is None else dataclasses.replace(live0, prices={t: price for t in live0.prices})
        band = U.band(book, facts, live, draws=4, workers=1)
        return book, live, band, U.MedianAnchor(book, facts, live, band, base=band)

    book, _, _, anchor = setup([b - 0.01, b + 0.02])
    axis = book.get("valuation.reverse_dcf.axes")[0]
    price = anchor.at(R.reverse_trial(book, axis, edge, follow=True))["central"]

    def solve(rng: list[float], **more: Any) -> dict:
        bk, live, band, anc = setup(rng, price, **more)
        return R.reverse_dcf(bk, facts, live, band, anchor=anc)["rows"][0]

    inside = solve([b - 0.01, b + 0.02])
    assert inside["status"] == "solved" and close(inside["solved"], edge, abs_=1e-3) and inside["in_range"]
    at_root = run_grid(R.reverse_trial(base, nim, inside["solved"], follow=True), facts, live0)
    assert inside["stationary_book"] == on_book and "printed_solved" not in inside
    assert close(inside["stationary_solved"], stationary_nim(at_root.ctx)["value"], abs_=1e-12)
    assert inside["stationary_solved"] > on_book + 0.003
    assert inside["levels_solved"] == R.levels_brief(levels(at_root))
    assert set(inside["levels_solved"]) == set(LEVEL_ROWS)
    # диапазон кончается чуть раньше корня — там, где невязка подвыборки втрое больше стопа: без ключа — «вне
    # диапазона» по подвыборке; с ключом и порогом шире этой невязки — уточнение на полной полосе, пометку ставит
    # её корень (порог уже невязки — чистая функция правила, `check_near_range_edge`)
    stop = float(base.get("valuation.headline.search_tol_rub"))
    slope = (price - anchor.at(R.reverse_trial(book, axis, edge - 0.002, follow=True))["central"]) / 0.002
    assert slope * 0.002 > 2 * stop
    rng = [b - 0.01, edge - 3 * stop / slope]
    plain_row = solve(rng)
    assert plain_row["gap_basis"] == "subsample" and plain_row["in_range"] is False and plain_row["status"] == "solved"
    assert plain_row["solved"] > rng[1]
    refined = solve(rng, **{EDGE: 4.5 * stop})
    assert refined["gap_basis"] == "full" and refined["status"] == "solved"


# ------------------------------------------------------------------ узлы выпуска

# Контракт П§7 п. 10 на фикстуре формы Т: норматив смеси расходится с ожиданием нормативов клеток чуть больше
# допуска — свойство фикстуры (у книги допуск задаёт её ключ); к узлам уровней не относится.
KNOWN = ("capital.mix.n20", "нарушены инварианты: payload_contract")


def approx(value: float, abs: float = 1e-9):                    # сравнение в допуске хранимой точности выпуска
    import pytest
    return pytest.approx(value, abs=abs)


def unknown(problems) -> list[str]:
    return [p for p in problems if not p.startswith(KNOWN)]


def variants_table(book) -> dict:
    """Таблицы книги для выпуска: справочные варианты и точка книги (сборка выпуска их не пересчитывает)."""
    rows = [{"id": v["id"], "title": v["title"], "point": 401.0 + i, "d_point": 1.0 + i}
            for i, v in enumerate(book.opt("valuation.reference_variants") or [])]
    return {"book_version": str(book.get("meta.version")), "headline": {"point": 400.0}, "reference_variants": rows,
            BR.VARIANTS_BOOK: book.digest}


def release_of(book, facts=None, *, out=None):
    facts = facts or t_facts()
    if out is None:
        expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
        rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                             draws=4, control_model=CONTROL_FIXTURE, results=variants_table(book))
    else:
        live, _ = apply_live(book, facts, out, today=TODAY, previous={})
        expl = explained(check_gates(run_grid(book, facts, live), today=TODAY), today=TODAY)
        rel = P.make_release(live=True, fast=True, today=TODAY, book=book, facts=facts, outputs=out, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE, results=variants_table(book))
    return rel, P.build_payload(rel)


@functools.lru_cache(maxsize=None)
def keyed_release():
    """Быстрый выпуск фикстуры со всеми ключами панели и ключом гейта знака стресса."""
    return release_of(S.book_of(**keyed(**{S4.STRESS: S4.GATE_KEYS["checks.stress_sign"]})))


def check_release_paths() -> None:
    """`paths.levels` — узел уровней сетки выпуска с хранимой точностью; `paths.modal_cell` — модальная клетка
    рядом с путём смеси; годовой путь выпуска и узел таблиц книги `point_path` считает одна функция."""
    rel, d = keyed_release()
    assert unknown(contract(d)) == []
    node, got = levels(rel.run), d["paths"]["levels"]
    assert got["order"] == list(LEVEL_ROWS) and (got["from_year"], got["to_year"], got["cell"]) == (
        node["from_year"], node["to_year"], node["cell"])
    for key in LEVEL_ROWS:
        assert got["rows"][key]["title"] == node["rows"][key]["title"]
        for k in LEVEL_METRICS:
            assert got["rows"][key][k] == approx(node["rows"][key][k], abs=5.1e-7), (key, k)
        assert "by_year" not in got["rows"][key]
    # узел таблиц книги «путь смеси точки» — тот же счёт, что годовой путь выпуска (в допуске хранимой точности)
    path, annual = point_path(rel.run), d["paths"]["annual"]
    assert path["years"] == [r["year"] for r in annual]
    for name, field_, tol in (("ni_sh", "ni_sh", 0.0051), ("nim_mgmt", "nim_mgmt", 5.1e-7), ("cor_mgmt", "cor_mgmt", 5.1e-7),
                              ("cir_mgmt", "cir_mgmt", 5.1e-7), ("roe", "roe", 5.1e-7), ("dps", "dps", 5.1e-5)):
        for value, row in zip(path[name], annual):
            assert (value is None and row[field_] is None) or value == approx(row[field_], abs=tol), (name, row["year"])
    # уровни смеси заголовка — среднее строк годового пути выпуска за годы участка
    tail = [r for r in annual if got["from_year"] <= r["year"] <= got["to_year"]]
    for k, field_ in (("nim", "nim_mgmt"), ("cor", "cor_mgmt"), ("cir", "cir_mgmt")):
        assert got["rows"]["point"][k] == approx(sum(r[field_] for r in tail) / len(tail), abs=1e-6)
    mc = d["paths"]["modal_cell"]
    cell = rel.run.cell(*mc["cell"].split("/"))
    assert mc["cell"] == got["cell"] == path["modal_cell"]["cell"] and mc["years"] == path["years"]
    assert mc["p_analytical"] == approx(path["modal_cell"]["p_analytical"], abs=1e-6)
    assert mc["p_point"] == approx(path["modal_cell"]["p_point"], abs=1e-6) != mc["p_analytical"]
    assert mc["price"] == approx(rel.run.cell_price(cell), abs=0.0051)
    assert mc["ni_sh"] == [approx(v, abs=0.0051) for v in cell.annual["ni_sh"]]
    cells = {(c["world"], c["regime"], c["scenario"]): c for c in d["grid"]["cells"]}
    assert cells[tuple(mc["cell"].split("/"))]["price"] == mc["price"]


def check_release_gate_numbers() -> None:
    """Стационарная маржа мира-цели — рядом с ключом цели и у строки обратного расчёта по нему; число гейта
    стоимости средств клиентов — узлом, согласованным с гейтом; заголовок гейта долгосрочного C/I называет слой;
    коридоры новых гейтов — ключи книги."""
    rel, d = keyed_release()
    book = rel.book
    st = d["nii"]["transmission"]["nim_stationary"]
    assert st == {"world": "M", "value": approx(stationary_nim(rel.run.ctx)["value"], abs=5.1e-7),
                  "target": 0.1053, "tolerance": 0.0005}
    assert "nim_lt_printed" in d["nii"]["transmission"]              # в книге фикстуры стоит и ключ `nim_lt`
    row = next(r for r in d["reverse_dcf"]["rows"] if NIM_PATH in r["paths"])
    assert row["stationary_book"] == approx(st["value"], abs=1e-6) and row["stationary_solved"] is None
    assert row["levels_solved"] is None and "printed_book" not in row
    assert all("stationary_book" not in r for r in d["reverse_dcf"]["rows"] if NIM_PATH not in r["paths"])
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    fc, number = d["checks"]["funds_cost_to_key"], funds_cost_to_key(rel.run)
    assert set(fc["by_world"]) == {"N", "H", "M"} and fc["max"] == 0.71 and fc["from_year"] == 2030
    assert all(fc["by_world"][w]["ratio"] == approx(number["by_world"][w]["ratio"], abs=5.1e-7) for w in fc["by_world"])
    assert gates["funds_cost_to_key"]["fired"] is (not fc["ok"]) and gates["funds_cost_to_key"]["mass"] == 0.2
    assert gates["cir_lt"]["title"] == P.CIR_LT_LAYER_TITLE and "слоя" in gates["cir_lt"]["message"]
    assert P.gate_title(S.book_of(), "cir_lt") == P.FORM_GATE_TITLES["cir_lt"]
    for name in ("nim_stationary", "window_backtest", "funds_cost_to_key"):
        assert gates[name]["title"] == P.gate_title(book, name) and "{" not in gates[name]["title"]
        assert gates[name]["corridor"]["value"] == book.get(f"checks.{name}") and gates[name]["corridor"]["text"]
        assert gates[name]["message"] and gates[name]["status"] in ("quiet", "explained")
    assert book.label("terms.lt_level") in gates["window_backtest"]["title"]
    broken = copy.deepcopy(d)
    broken["checks"]["funds_cost_to_key"]["ok"] = not fc["ok"]
    assert any("checks.funds_cost_to_key" in x for x in P._panel_problems(broken))
    assert not [x for x in P._panel_problems(d) if "checks." in x]


def check_release_stress_basis() -> None:
    """Узел гейта знака стресса: масса — под вероятностями точки, рядом — масса тех же клеток под весами слоя
    «свой взгляд»; сообщение гейта называет базу; передача убытка в стоимость — по клеткам режима шока."""
    rel, d = keyed_release()
    ss = d["checks"]["stress_sign"]
    number = rel.stress_sign
    assert ss["mass_basis"] == "point" and ss["mass_analytical"] == approx(number["mass_analytical"], abs=1e-6)
    assert ss["mass"] == approx(number["mass"], abs=1e-6) and ss["mass"] != ss["mass_analytical"]
    assert ss["loss"]["after_tax"] == approx(number["loss"]["after_tax"], abs=0.0051)
    assert ss["loss"]["transfer_min"] <= ss["loss"]["transfer_max"]
    assert ss["loss"]["transfer_max"] == approx(number["loss"]["transfer_max"], abs=5.1e-7)
    gate = next(g for g in d["checks"]["gates"] if g["name"] == "stress_sign")
    assert gate["fired"] and "под вероятностями точки" in gate["message"] and "слоя «свой взгляд»" in gate["message"]
    assert {c["regime"] for c in ss["requirement"]["cells"]} >= {"crisis"}        # часть о требовании судит и режим шока


def check_release_variants_and_glide() -> None:
    """Справочные варианты — из таблиц книги (сборка их не считает: чисел таблицы нет ни в одной сетке выпуска);
    запас якоря до требования — и с глиссадой: к требованию конца первого квартала сетки под весами слоя «свой
    взгляд»."""
    rel, d = keyed_release()
    variants = d["book"]["reference_variants"]
    # строки — по убыванию модуля цены правила: у таблицы проверки он растёт по списку книги
    assert variants["point"] == 400.0 and [r["id"] for r in variants["rows"]] == [v["id"] for v in VARIANT_LIST][::-1]
    assert [r["point"] for r in variants["rows"]] == [403.0, 402.0, 401.0]
    assert [r["title"] for r in variants["rows"]] == [v["title"] for v in VARIANT_LIST][::-1]
    anchor = d["capital"]["anchor"]
    run = rel.run
    p_an = run.layers["analytical"].prob
    glide = sum(p_an[c.key] * c.quarters["req20_glide"][1] for c in run.cells)
    assert anchor["req20_glide_next"] == approx(glide, abs=5.1e-7)
    assert anchor["req20_glide_period"] == run.ctx.timeline.period(1) == d["capital"]["requirement"]["periods"][0]
    assert anchor["n20_headroom_glide"] == approx(anchor["n20_post_dividend"] - glide, abs=1.1e-6)
    assert anchor["req20_glide_next"] > anchor["req20_now"] and anchor["n20_headroom_glide"] < anchor["n20_headroom"]
    assert "ключ цели" in d["fair_value"]["bank_first_line"]["sensitivity_basis"]


def check_sensitivity_book() -> None:
    """Книга строки чувствительности: при `axis_follow: both` ось полосы вида `value`, на которой стоит сдвинутый
    ключ, идёт за ним обоими концами (ЧПМ и запас капитала); без ключа концы стоят; пути CoR водит ось вида
    `shift` — её книга строки не трогает."""
    near, both = S.book_of(), S.book_of(**{"valuation__reverse_dcf__axis_follow": "both"})
    assert not P.axes_follow(near) and P.axes_follow(both)

    def axis(book, path):
        return next(a for a in book.get("valuation.uncertainty.axes") if a["kind"] == "value" and path in a["paths"])

    for kind, path, key in (("nim", NIM_PATH, "nim_pp"), ("buffer", "capital.mgmt_buffer.n20_0", "buffer_pp")):
        step = float(near.get(f"valuation.sensitivities.{key}"))
        was = axis(near, path)
        stay, moved = P.sensitivity_book(near, kind), P.sensitivity_book(both, kind)
        assert float(stay.get(path)) == float(moved.get(path)) and close(float(stay.get(path)), float(near.get(path)) + step)
        assert (axis(stay, path)["low"], axis(stay, path)["high"]) == (was["low"], was["high"])
        assert close(axis(moved, path)["low"], was["low"] + step, abs_=1e-15)
        assert close(axis(moved, path)["high"], was["high"] + step, abs_=1e-15)
        others = [a for a in moved.get("valuation.uncertainty.axes") if path not in a["paths"]]
        assert others == [a for a in both.get("valuation.uncertainty.axes") if path not in a["paths"]]
    assert P.sensitivity_book(both, "cor").get("valuation.uncertainty.axes") == both.get("valuation.uncertainty.axes")
    assert P._follow_words(near) == "" and "обоими концами" in P._follow_words(both)
