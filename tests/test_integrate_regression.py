"""Регрессия книги (М§18): свежий расчёт воспроизводит закоммиченный `data/assumptions/results.json`.

Не проверяет правильность (ошибка ядра вошла бы в таблицы) — ловит незамеченную смену чисел:
правка кода, книги или фактов без нового `python -B -m model.book_results`. Допуск М§18 —
относительный 1e-12, пол 1e-10. Коммит ядра и гейт, зависящий от «сегодня»
(`manual_input_overdue`), в сравнение не входят.

Узлы, которые таблицы несут только при своих ключах книги (`KEYED_NODES`: уровни после фазы роста, путь смеси
точки, справочные варианты и отпечаток их книги, числа сторожей уровней и знака стресса), сверяются наравне с
обязательными: быстрый расчёт их считает, а часть их чисел не держит ни одно сообщение проверки. Узел, который
есть только в свежем расчёте или только в сохранённом, — расхождение.
"""
from __future__ import annotations

import json
import math

import pytest

from model import book_results as BR
from model.book import ROOT

RESULTS = ROOT / "data" / "assumptions" / "results.json"
REL, FLOOR = 1e-12, 1e-10
GRID_KEYS = ("book_version", "facts_date", "derived", "layers", "cells", "central_cell", "sign_test")
# Узлы при ключах книги (М§14.2, §14.5): считаются на сетке без полосы; сверяются, когда узел есть хотя бы в
# одной из сторон.
KEYED_NODES = ("levels", "point_path", "reference_variants", "reference_variants_book", "nim_stationary",
               "funds_cost_to_key", "stress_sign", "nim_lt")
GRID_HEADLINE = ("point", "printed_point", "low", "high", "rates_view", "lambda", "market")
BAND_HEADLINE = ("median", "printed_median", "band80", "printed_band80", "band50", "printed_band50",
                 "p10", "p25", "p75", "p90", "mean", "p_below_market", "p_below_by_ticker", "upside",
                 "draws", "seed", "contributions")
TODAY_DEPENDENT = {"manual_input_overdue"}
# Текст инварианта DDM = RI называет число прогонов полосы и максимум разности по ним (C4), тексты гейтов
# `capital_gap`, `roe_gt_g` и `growth_cut` — хвост прогонов полосы (М§10): быстрая полоса сетки их меняет —
# сверяются имя, вид, срабатывание и масса, без текста.
BAND_DEPENDENT_TEXT = {"ddm_equals_ri", "capital_gap", "roe_gt_g", "growth_cut"}


def _diff(saved, fresh, path: str, bad: list[str]) -> None:
    if isinstance(saved, dict) and isinstance(fresh, dict):
        for k in sorted(set(saved) | set(fresh)):
            if k not in saved or k not in fresh:
                bad.append(f"{path}.{k}: ключ есть только в {'свежем' if k in fresh else 'сохранённом'}")
            else:
                _diff(saved[k], fresh[k], f"{path}.{k}", bad)
    elif isinstance(saved, list) and isinstance(fresh, list):
        if len(saved) != len(fresh):
            bad.append(f"{path}: длина {len(saved)} против {len(fresh)}")
        for i, (a, b) in enumerate(zip(saved, fresh)):
            _diff(a, b, f"{path}[{i}]", bad)
    elif isinstance(saved, (int, float)) and isinstance(fresh, (int, float)) \
            and not isinstance(saved, bool) and not isinstance(fresh, bool):
        if not math.isclose(saved, fresh, rel_tol=REL, abs_tol=FLOOR):
            bad.append(f"{path}: {saved!r} против {fresh!r}")
    elif saved != fresh:
        bad.append(f"{path}: {saved!r} против {fresh!r}")


def _saved() -> dict:
    if not RESULTS.exists():
        pytest.skip("нет data/assumptions/results.json (python -B -m model.book_results)")
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def _plain(res: dict) -> dict:
    return json.loads(json.dumps(res, default=BR._default))


def _checks(res: dict) -> list[dict]:
    return [{k: v for k, v in c.items() if not (k == "message" and c["name"] in BAND_DEPENDENT_TEXT)}
            for c in res["checks"] if c["name"] not in TODAY_DEPENDENT]


def keyed_node_diffs(saved: dict, fresh: dict) -> list[str]:
    """Расхождения узлов при ключах книги: узел только в одной из сторон и числа узла вне допуска."""
    bad: list[str] = []
    for k in KEYED_NODES:
        if k not in saved and k not in fresh:
            continue
        if k not in saved or k not in fresh:
            bad.append(f"{k}: узел есть только в {'свежем' if k in fresh else 'сохранённом'}")
        else:
            _diff(saved[k], fresh[k], k, bad)
    return bad


def test_keyed_nodes_are_compared_like_the_rest():
    """Сторож узлов при ключах книги: устаревшее число справочного варианта, пропавший узел уровней, лишний
    отпечаток книги — расхождения; равные узлы и узлы, которых нет ни в одной из сторон, — нет."""
    saved = {"levels": {"rows": {"point": {"nim": 0.11}}}, "reference_variants": [{"id": "a", "point": 339.51}],
             "reference_variants_book": "abc"}
    assert keyed_node_diffs(saved, _plain(saved)) == []
    stale = {**saved, "reference_variants": [{"id": "a", "point": 354.06}]}
    assert any(x.startswith("reference_variants[0].point") for x in keyed_node_diffs(saved, stale))
    assert keyed_node_diffs(saved, {k: v for k, v in saved.items() if k != "levels"}) == [
        "levels: узел есть только в сохранённом"]
    assert keyed_node_diffs({}, {"point_path": {"years": [2026]}}) == ["point_path: узел есть только в свежем"]
    assert any(x.startswith("reference_variants_book") for x in keyed_node_diffs(saved, {**saved, "reference_variants_book": "abd"}))


def test_grid_part_of_the_book_results_reproduces():
    """Сетка без полосы (≈1 с): выводимое, слои, 36 клеток, центральная клетка, тест знака, проверки, точка и
    узлы при ключах книги (уровни, путь смеси точки, справочные варианты, числа сторожей)."""
    saved = _saved()
    fresh = _plain(BR.book_results(slow=False))
    bad: list[str] = []
    for k in GRID_KEYS:
        if k not in saved:
            bad.append(f"{k}: ключ есть только в свежем")
            continue
        _diff(saved[k], fresh[k], k, bad)
    bad.extend(keyed_node_diffs(saved, fresh))
    for k in GRID_HEADLINE:
        _diff(saved["headline"][k], fresh["headline"][k], f"headline.{k}", bad)
    _diff(_checks(saved), _checks(fresh), "checks", bad)
    assert not bad, "results.json устарел — пересобрать python -B -m model.book_results:\n" + "\n".join(bad[:20])


@pytest.mark.ci_only
def test_band_part_of_the_book_results_reproduces(parallel_band):
    """Полоса на полном числе прогонов книги: заголовок и вклады осей (поиски — не пересчитываются)."""
    from model.book import load_book, load_facts
    from model.grid import live_from_book, run_grid
    from model import uncertainty as U

    saved = _saved()
    facts = load_facts()
    book = load_book(facts=facts)
    live = live_from_book(book, facts)
    run = run_grid(book, facts, live)
    with parallel_band():
        band = U.band(book, facts, live, draws=int(book.get("valuation.uncertainty.draws")))
    h = band.headline(run.lam, live.prices, str(book.get("meta.company.main_ticker")))
    fresh = {k: h[k] for k in BAND_HEADLINE if k in h}
    fresh.update(draws=band.draws, seed=band.seed,
                 contributions=[{k: c[k] for k in ("axis", "name", "share", "rank_corr")}
                                for c in band.contributions(run.lam)])
    bad: list[str] = []
    for k in BAND_HEADLINE:
        _diff(saved["headline"][k], _plain(fresh)[k], f"headline.{k}", bad)
    assert not bad, "results.json устарел — пересобрать python -B -m model.book_results:\n" + "\n".join(bad[:20])
