"""Ядро на настоящей книге и фактах (`assumptions.yaml`, `data/facts/`); пока их нет — пропуск."""

from __future__ import annotations

import functools

import pytest

from model.checks import check_gates, check_invariants
from model.grid import run_grid
from tests.support_core import real_book_or_skip

pytestmark = pytest.mark.tact            # быстрые тесты ядра — в такте сервера (W1/C1)


@functools.lru_cache(maxsize=None)
def _run():
    book, facts = real_book_or_skip()
    return run_grid(book, facts)


def test_real_book_invariants_hold():
    run = _run()
    fired = [(f.name, f.message) for f in check_invariants(run) if f.fired]
    assert not fired, fired


def test_real_book_ddm_equals_ri_in_every_cell():
    run = _run()
    tol = float(run.ctx.book.get("checks.ddm_ri_tol"))
    for c in run.cells:
        assert abs(c.v_ddm - c.v_ri) <= tol * abs(c.v_ri), c.label


def test_real_book_anchor_reproduces_facts():
    run = _run()
    facts = run.ctx.facts
    c = run.cells[0]
    assert c.quarters["n20"][0] == pytest.approx(facts.need("capital", "n20_0.value"), abs=5e-4)
    assert c.quarters["n11"][0] == pytest.approx(facts.need("capital", "n1_1_bank.value"), abs=5e-4)


def test_real_book_transmission_and_gates_run():
    run = _run()
    tr = run.ctx.transmission
    assert tr.t_real == pytest.approx(float(run.ctx.book.get("nii.transmission.target")),
                                      abs=float(run.ctx.book.get("checks.transmission_tol")))
    names = [f.name for f in check_gates(run)]
    assert "roe_k_homogeneity" in names and "capital_gap" in names


def test_real_book_gates_of_the_margin_target_and_of_the_signs_follow_their_keys():
    """Гейты цели печатаемой маржи и знаков (М§14.2) на настоящей книге — по её ключам: без ключа гейта нет; с
    ключом число гейта посчитано, гейт согласован с числом и, сработав, требует объяснения, как прочие гейты."""
    import math

    from model.checks import gate_statuses, sign_numbers
    from model.grid import NIM_LT, STRESS_SIGN, VOLUME_SIGN, printed_nim_lt
    run = _run()
    book = run.ctx.book
    gates = {f.name: f for f in check_gates(run)}
    numbers = sign_numbers(run)
    printed = printed_nim_lt(run)
    for key, name in ((NIM_LT, "nim_lt"), (VOLUME_SIGN, "volume_sign"), (STRESS_SIGN, "stress_sign")):
        assert (name in gates) is (book.opt(key) is not None), name
    assert (printed is None) is (book.opt(NIM_LT) is None)
    if printed is not None:
        cfg = book.get(NIM_LT)
        assert math.isfinite(printed["value"]) and printed["years"][0] == int(cfg["from_year"])
        assert gates["nim_lt"].fired is (abs(printed["value"] - float(cfg["target"])) > float(cfg["tolerance"]))
    for name in ("volume_sign", "stress_sign"):
        number = numbers[name]
        assert (number is None) is (name not in gates)
        if number is not None:
            assert gates[name].fired is (not number["ok"])
    if numbers["stress_sign"] is not None:
        st = numbers["stress_sign"]
        assert 0.0 <= st["mass"] <= 1.0 and math.isfinite(st["max_excess"])
        assert gates["stress_sign"].mass == pytest.approx(st["mass"], abs=1e-12)
        assert st["ok"] is (not st["loss"]["cells"] and not st["requirement"]["cells"])
    fired = [f for f in gates.values() if f.name in ("nim_lt", "volume_sign", "stress_sign") and f.fired]
    for status in gate_statuses(fired, {}, today=run.ctx.clock.valuation_date):
        assert status.status == "unexplained"            # сработавший гейт без записи — «не объяснён», как прочие


def test_real_book_level_gates_and_nodes_follow_their_keys():
    """Сторожа уровней и узлы «на чём стоит заголовок» (М§14.2, §14.5) на настоящей книге — по её ключам: без
    ключа нет ни гейта, ни числа; с ключом число посчитано на готовой сетке, гейт согласован с числом. Мир-опора
    κ-добавки и вид угасания терминала — тоже ключи книги."""
    import math

    from model.levels import (CIR_LT, FUNDS_COST, NIM_STATIONARY, POINT_PATH, WINDOW_BACKTEST, cir_lt_value,
                              funds_cost_to_key, levels, point_path, stationary_nim)
    run = _run()
    book = run.ctx.book
    gates = {f.name: f for f in check_gates(run)}
    numbers = {"nim_stationary": (NIM_STATIONARY, stationary_nim(run.ctx)), "window_backtest": (WINDOW_BACKTEST, levels(run)),
               "funds_cost_to_key": (FUNDS_COST, funds_cost_to_key(run))}
    for name, (key, number) in numbers.items():
        assert (name in gates) is (book.opt(key) is not None) is (number is not None), name
    assert (point_path(run) is None) is (book.opt(POINT_PATH) is not True)
    assert run.ctx.prep.kappa_world == book.opt("credit.kappa_reference_world")
    assert run.ctx.prep.fade_symmetric is (book.opt("valuation.terminal.fade_mode") == "symmetric")
    st, lv, fc = (numbers[k][1] for k in ("nim_stationary", "window_backtest", "funds_cost_to_key"))
    if st is not None:
        assert math.isfinite(st["value"]) and gates["nim_stationary"].fired is (abs(st["value"] - st["target"]) > st["tolerance"])
    if lv is not None:
        cfg = book.get(WINDOW_BACKTEST)
        assert all(math.isfinite(row[k]) for row in lv["rows"].values() for k in ("nim", "cor", "cir", "loans_share"))
        low = lv["rows"]["macro_neutral"]
        inside = all(float(cfg[k][0]) <= low[k] <= float(cfg[k][1]) for k in ("cor", "cir"))
        assert gates["window_backtest"].fired is (not inside)
    if fc is not None:
        assert gates["funds_cost_to_key"].fired is (not fc["ok"]) and set(fc["by_world"]) == set(book.get("worlds.ids"))
    cir = cir_lt_value(run)
    assert (cir is None) is (book.opt(CIR_LT) is None)
    if cir is not None:
        assert cir["scope"] == book.opt(f"{CIR_LT}.scope", "modal_cell")
        assert gates["cir_lt"].fired is (abs(cir["value"] - cir["target"]) > cir["tolerance"])


def test_real_book_target_key_is_the_level_of_its_world():
    """Мир уровня ключа цели ЧПМ (М§4.5) на настоящей книге. Ключ цели — стационарная маржа мира уровня (без ключа
    `nii.transmission.level_world` — мира-опоры решателя): решение передачи её воспроизводит. Подмена в памяти,
    которая называет тот же уровень другим миром, — книге без ключа уровня ставит мир слоя «рыночные ставки как
    есть» и его стационарную маржу, книге с ключом уровня ставит мир-опору и выведенный уровень мира-опоры, —
    даёт ту же сетку: все клетки и точка в 1e-9 относительных."""
    from model.levels import level_nim
    from model.nii import LEVEL_WORLD, NIM_KEY, level_world
    run = _run()
    book, tr, br = run.ctx.book, run.ctx.transmission, run.ctx.bridge
    named = level_world(book)
    level = named or tr.reference_world
    assert tr.level_world == level and (level_nim(run.ctx) is None) is (named is None)
    assert br.to_mgmt_nim(tr.nss[level]) == pytest.approx(float(book.get(NIM_KEY)), abs=1e-9)
    if named is None:
        other = str(book.get("joint.macro_neutral_world"))
        swap = {LEVEL_WORLD: other, NIM_KEY: br.to_mgmt_nim(tr.nss[other])}
    else:
        swap = {LEVEL_WORLD: tr.reference_world, NIM_KEY: br.to_mgmt_nim(tr.reference_level)}
    again = run_grid(book.with_overrides(swap, create=True), run.ctx.facts, run.ctx.live)
    assert again.point == pytest.approx(run.point, rel=1e-9)
    for a, b in zip(again.cells, run.cells):
        assert a.key == b.key and a.v_ri == pytest.approx(b.v_ri, rel=1e-9), a.label
        assert a.v_ddm == pytest.approx(b.v_ddm, rel=1e-9) and a.roe_t == pytest.approx(b.roe_t, rel=1e-9), a.label


def test_real_book_window_rows_and_facts_follow_their_keys():
    """Окно фактов узла уровней, список строк обратного расчёта с уточнением на полной полосе и элементы премий
    роста, названные фактом, на настоящей книге — по её ключам: без ключа нет ни подузла, ни списка; с ключом
    подузел несёт числа книги и долю кредитов якоря сетки, список называет строки книги, а строка «без
    опережающего роста» оставляет названные элементы как в книге."""
    from model import reverse as R
    from model import uncertainty as U
    from model.levels import WINDOW_BACKTEST, WINDOW_FIELDS, levels, window_facts
    run = _run()
    book = run.ctx.book
    cfg = book.opt(WINDOW_BACKTEST) or {}
    window = window_facts(run)
    assert (window is None) is (not any(k in cfg for k in WINDOW_FIELDS))
    if window is not None:
        node = levels(run)
        assert node["window"] == window and "window" not in node["rows"] and "window" not in node["order"]
        anchor = run.cells[0].quarters
        assert window["loans_share"]["anchor"] == pytest.approx(anchor["loans"][0] / anchor["iea"][0], rel=1e-12)
        for name in ("cor", "cir"):
            assert [window[name]["min"], window[name]["max"]] == [float(x) for x in cfg[name]]
        if "nim" in cfg:
            assert window["nim"]["min"] <= window["nim"]["max"]
            assert f"{100 * window['nim']['max']:.2f}".replace(".", ",") in next(
                f for f in check_gates(run) if f.name == "window_backtest").message
    named = R.refine_rows(book)
    assert (named is None) is (book.opt(R.REFINE_ROWS) is None)
    if named is not None:
        assert named <= {U.axis_key(ax) for ax in book.get("valuation.reverse_dcf.axes")}
    kept = R.premium_facts(book)
    assert bool(kept) is bool(book.opt(R.PREMIUM_FACTS))
    flat = book.with_overrides(R.no_premium_overrides(book))
    for path in kept:
        assert flat.get(path) == book.get(path)
