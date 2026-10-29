"""Скорость сетки: полоса — 2 000 прогонов 36 клеток, поэтому прогон сетки обязан быть быстрым.

Вторая половина — равенство ускоренных путей: лёгкая сетка, проход клеток по своим входам, полоса по записям
прогонов другой полосы и пересчёт медианы на тех же входах дают те же числа бит в бит, что и расчёт целиком.
"""

from __future__ import annotations

import dataclasses
import pickle
import time
from datetime import timedelta

import pytest

from model import grid as G
from model import uncertainty as U
from model.cell import cell_path
from model.grid import (LiveInputs, live_from_book, make_context, path_inputs, path_key, path_keys, run_grid,
                        run_paths, world_inputs)
from tests.support_core import fixture_book, fixture_facts
from tests.support_core_t import book_live, neutral_book, t_facts

# Потолок одного прогона сетки (36 клеток с пробными проходами дивиденда и контекстом),
# секунды: на ноутбуке разработчика ≈0,1 с; запас на медленный раннер CI.
GRID_SECONDS = 2.0
# Сетка второй формы эмитента (12 книг, рост, ограниченный капиталом: в связывающем квартале — три оценки шага, с
# навёрстыванием — до пяти) — не дольше трёх времён сетки первой формы; прибавка — на шум замера коротких
# прогонов. Счёт шагов клетки без часов — `tests/test_core_t_w3.py`.
FORM_RATIO, FORM_SLACK = 3.0, 0.05
# Суждения, которые проход клеток не читают (оценка, дисконт, вероятности), и суждения, которые его меняют.
OUTSIDE_THE_PATH = ({"valuation.erp": 0.071}, {"valuation.beta_e": 1.21}, {"valuation.terminal.fade": 0.37},
                    {"valuation.governance.discount": 0.04}, {"joint.own_macro_confidence": 0.31})
INSIDE_THE_PATH = ({"credit.kappa": 0.07}, {"valuation.terminal.real_growth": 0.011},
                   {"nii.nim_lt_target_mgmt": 0.0501})
# Суждение о передаче ставки меняет сжатие φ: проход клеток мира-опоры от него не зависит, остальных — зависит.
TRANSMISSION = {"nii.transmission.target": 0.11}
CELLS = 36


def _per_run(book, facts, live=None, n: int = 3) -> float:
    """Лучшее из `n` время одного прогона сетки на книге с подменой (подмена — как у прогона полосы)."""
    best = float("inf")
    for i in range(n):
        trial = book.with_overrides({"credit.kappa": 0.05 + 0.01 * i})
        t = time.perf_counter()
        run_grid(trial, facts, live)
        best = min(best, time.perf_counter() - t)
    return best


def test_grid_is_fast_enough_for_the_band():
    book, facts = fixture_book(), fixture_facts()
    run_grid(book, facts)                                   # прогрев импорта и кэшей
    t = time.perf_counter()
    n = 3
    for i in range(n):
        run_grid(book.with_overrides({"credit.kappa": 0.05 + 0.01 * i}), facts)
    per_run = (time.perf_counter() - t) / n
    assert per_run < GRID_SECONDS, f"прогон сетки {per_run:.2f} с"


def test_grid_of_the_second_form_is_within_three_grids_of_the_first():
    """Форма Т (полная книга фикстуры `core_t`, с ростом, ограниченным капиталом) против первой формы
    (фикстура `core`)."""
    book, facts = fixture_book(), fixture_facts()
    t_book, t_fx = neutral_book(), t_facts()
    run_grid(book, facts)
    run_grid(t_book, t_fx, book_live(t_book))                # прогрев
    first = _per_run(book, facts)
    second = _per_run(t_book, t_fx, book_live(t_book))
    assert second < GRID_SECONDS, f"прогон сетки формы Т {second:.2f} с"
    assert second < FORM_RATIO * first + FORM_SLACK, f"сетка формы Т {second:.3f} с против {first:.3f} с первой формы"


# ------------------------------------------------------------------ равенство ускоренных путей


def _forms():
    """Обе формы эмитента: (книга, факты, живые входы)."""
    book, facts = fixture_book(), fixture_facts()
    t_book = neutral_book()
    return ((book, facts, live_from_book(book, facts)), (t_book, t_facts(), book_live(t_book)))


def _counted_paths(monkeypatch) -> list[int]:
    """Счётчик проходов клеток, посчитанных заново (у клеток, взятых из записей, проход не считается)."""
    calls: list[int] = []
    real = G.cell_path
    monkeypatch.setattr(G, "cell_path", lambda *a, **k: calls.append(1) or real(*a, **k))
    return calls


def _same_band(a: U.Band, b: U.Band) -> bool:
    return a.rows == b.rows and a.low_draws == b.low_draws and a.high_draws == b.high_draws and a.s == b.s


@pytest.mark.parametrize("form", (0, 1), ids=("first", "second"))
def test_summary_grid_gives_the_numbers_of_the_full_grid(form):
    """Лёгкая сетка (полосе и поискам ряды клеток не нужны) — те же цены, слои, мост и сводка прогона, что у
    полной: проход и оценка клетки у них общие."""
    book, facts, live = _forms()[form]
    full, light = run_grid(book, facts, live), run_grid(book, facts, live, summary=True)
    assert U.run_summary(light) == U.run_summary(full)
    assert (light.low, light.high, light.point) == (full.low, full.high, full.point)
    assert light.layers == full.layers
    for name in ("bridge_amount", "bridge_rows", "pending_dividend", "unregistered_dividend", "divisor", "governance"):
        assert getattr(light, name) == getattr(full, name), name
    for a, b in zip(light.cells, full.cells):
        assert a.key == b.key and a.flags == b.flags and a.gap_period == b.gap_period and a.solver == b.solver
        for name in ("v_ri", "v_ddm", "bv_v", "x_t", "roe_t", "k_t", "g_t", "tv_ri", "tv_ddm", "terminal_share",
                     "pv_ri_explicit", "pv_terminal", "roe_t_raw", "bv_star", "n20_min", "n11_min", "n11_star",
                     "y_x", "la_headroom"):
            assert getattr(a, name) == getattr(b, name), (a.label, name)
        assert a.growth["cut_share"] == b.growth["cut_share"] and a.quarters["bv"] == b.quarters["bv"]
        assert a.quarters["div_model"] == b.quarters["div_model"] and a.quarters["div"] == b.quarters["div"]


@pytest.mark.parametrize("form", (0, 1), ids=("first", "second"))
def test_cell_path_reads_only_its_inputs(form):
    """Проход клетки считается по входам прохода — в них нет ни книги, ни фактов, ни дисконта, а параметры
    терминала заменены на «не число» — и совпадает с проходом по контексту прогона. Отпечаток входов прохода
    не меняют суждения оценки и меняют суждения прохода: по нему полоса решает, считать ли проход заново."""
    book, facts, live = _forms()[form]
    ctx = make_context(book, facts, live)
    inputs = path_inputs(ctx)
    assert {f.name for f in dataclasses.fields(inputs)} == {"prep", "worlds", "deviations", "fx"}
    assert all(x != x for x in (inputs.prep.real_growth, inputs.prep.fade, inputs.prep.multiple))
    paths = run_paths(ctx, inputs)
    assert len(paths) == CELLS and [p.world for p in paths] == [c.world for c in run_grid(book, facts, live).cells]
    for path in paths[::7]:
        assert cell_path(ctx, path.world, path.regime, path.scenario) == path
    ref = inputs.prep.reference_world
    for world in inputs.worlds:                             # клетка мира видит свой мир, мир-опору и базовый
        own = world_inputs(inputs, world)
        assert set(own.worlds) == {world, ref, G.BASE_WORLD} and set(own.fx) == {world}
        assert run_paths(ctx, inputs, world) == tuple(p for p in paths if p.world == world)
    key, keys = path_key(inputs), path_keys(inputs)
    assert key == path_key(path_inputs(make_context(book, facts, live))) and list(keys) == list(inputs.worlds)
    moved = path_keys(path_inputs(make_context(U.trial_book(book, TRANSMISSION), facts, live)))
    assert [w for w in keys if moved[w] == keys[w]] == [ref]                   # сжатие φ в мире-опоре — ноль
    for ov in OUTSIDE_THE_PATH:
        trial = U.trial_book(book, ov)
        assert path_key(path_inputs(make_context(trial, facts, live))) == key, ov
    later = LiveInputs(valuation_date=live.valuation_date + timedelta(days=3), prices=dict(live.prices),
                       price_dates=dict(live.price_dates), register=live.register)
    assert path_key(path_inputs(make_context(book, facts, later))) == key      # дата оценки проход не трогает
    for ov in INSIDE_THE_PATH:
        trial = U.trial_book(book, ov)
        assert path_key(path_inputs(make_context(trial, facts, live))) != key, ov


def test_grid_takes_the_paths_of_the_search_store_only_when_the_path_is_the_same():
    """Хранилище проходов поиска (`run_grid(paths=…)`): сетка книги с суждением вне прохода берёт проходы из него
    и даёт те же числа, что без хранилища; суждение прохода кладёт в хранилище свою сетку проходов."""
    book, facts, live = _forms()[1]
    store: dict = {}
    base = run_grid(book, facts, live, summary=True, paths=store)
    assert len(store) == 1 and U.run_summary(base) == U.run_summary(run_grid(book, facts, live))
    for ov in OUTSIDE_THE_PATH[:3]:
        trial = U.trial_book(book, ov)
        got = run_grid(trial, facts, live, summary=True, paths=store)
        assert len(store) == 1 and U.run_summary(got) == U.run_summary(run_grid(trial, facts, live)), ov
    trial = U.trial_book(book, INSIDE_THE_PATH[0])
    got = run_grid(trial, facts, live, summary=True, paths=store)
    assert len(store) == 2 and U.run_summary(got) == U.run_summary(run_grid(trial, facts, live))


@pytest.mark.parametrize("form", (0, 1), ids=("first", "second"))
def test_band_from_the_records_equals_the_band_computed_in_full(form, monkeypatch):
    """Полоса по записям прогонов (`keep`, `like`): книга с суждением вне прохода считает одну оценку — проходов
    клеток ноль — и даёт те же прогоны бит в бит; книга с суждением прохода расходится на пробе первой точки и
    считается целиком. Записи чисел полосы не меняют."""
    book, facts, live = _forms()[form]
    n = 6
    plain = U.band(book, facts, live, draws=n, workers=1)
    base = U.band(book, facts, live, draws=n, workers=1, keep=True)
    assert plain.records is None and len(base.records) == n and _same_band(plain, base)
    calls = _counted_paths(monkeypatch)
    for ov in OUTSIDE_THE_PATH[:4]:
        trial = U.trial_book(book, ov)
        del calls[:]
        got = U.band(trial, facts, live, draws=n, workers=1, like=base)
        assert not calls, ov
        want = U.band(trial, facts, live, draws=n, workers=1)
        assert _same_band(got, want) and got.rows != base.rows, ov
    trial = U.trial_book(book, INSIDE_THE_PATH[0])
    del calls[:]
    got = U.band(trial, facts, live, draws=n, workers=1, like=base)
    assert len(calls) == n * CELLS
    assert _same_band(got, U.band(trial, facts, live, draws=n, workers=1))
    trial = U.trial_book(book, TRANSMISSION)                # клетки мира-опоры — из записей, остальные — заново
    del calls[:]
    got = U.band(trial, facts, live, draws=n, workers=1, like=base)
    assert len(calls) == n * CELLS * 2 // 3
    assert _same_band(got, U.band(trial, facts, live, draws=n, workers=1)) and got.rows != base.rows
    other = U.band(book, facts, live, draws=n + 1, workers=1, like=base)       # другая выборка — записи не годятся
    assert other.draws == n + 1 and _same_band(other, U.band(book, facts, live, draws=n + 1, workers=1))


def test_median_anchor_takes_the_base_for_the_same_inputs_and_the_records_for_a_rolled_date(monkeypatch):
    """Пересчёт медианы: на книге и входах базы — сама база (счётчик пересчётов идёт); на другой дате оценки —
    по записям базы, без проходов клеток, с теми же числами, что у полосы целиком."""
    book, facts, live = _forms()[1]
    n = 6
    full = U.band(book, facts, live, draws=n, workers=1)
    anchor = U.MedianAnchor(book, facts, live, full, n=n)
    assert anchor.base.records is not None and anchor.evaluations == 1
    assert anchor.recompute() is anchor.base and anchor.recompute(book, live) is anchor.base
    assert anchor.evaluations == 3
    later = LiveInputs(valuation_date=live.valuation_date + timedelta(days=10), prices=dict(live.prices),
                       price_dates=dict(live.price_dates), register=live.register)
    calls = _counted_paths(monkeypatch)
    got = anchor.recompute(live=later)
    assert not calls and anchor.evaluations == 4
    assert _same_band(got, U.band(book, facts, later, draws=n, workers=1)) and got.rows != anchor.base.rows


@pytest.mark.ci_only
def test_pool_keeps_and_takes_the_records_bit_identically():
    """Пул: записи прогонов возвращаются кусками по порядку точек, полоса по записям считается в пуле — числа
    те же, что последовательно."""
    book, facts, live = _forms()[0]
    n = U.PARALLEL_MIN_DRAWS
    serial = U.band(book, facts, live, draws=n, workers=1, keep=True)
    pooled = U.band(book, facts, live, draws=n, workers=2, keep=True)
    assert _same_band(serial, pooled)
    for record, record_pool in zip(serial.records, pooled.records, strict=True):
        for (key, blob), (key_pool, blob_pool) in zip(record, record_pool, strict=True):
            assert key == key_pool                          # отпечаток входов прохода от процесса не зависит
            assert pickle.loads(blob) == pickle.loads(blob_pool)    # запись — нет: порядок множества флагов свой
    trial = U.trial_book(book, OUTSIDE_THE_PATH[0])
    got = U.band(trial, facts, live, draws=n, workers=2, like=pooled)
    assert _same_band(got, U.band(trial, facts, live, draws=n, workers=1))
    U.close_pool()
