"""Результаты книги: `results.json` и `run_output.txt` (регрессия книги, М§18).

`python -B -m model.book_results [--fast] [--out КАТАЛОГ]` — расчёт на цене, дате и реестре
книги (`live_from_book`): выводимые величины, слои, заголовок (медиана, полосы, точка, низ,
верх), 36 клеток, центральная (модальная) клетка по годам, тест знака объёмных эффектов, проверки,
обратный расчёт и «что даст отчёт». Центральная клетка выбирается правилом (`model.grid.modal_cell`:
мода по каждой оси в слое «свой взгляд»), а не литералом; опорная клетка диагностик (`norm`,
`schedule`) — другое понятие.
Числа — полной точности; `ops/tools/render_numbers.py` печатает их в документах по меткам.
Свежий расчёт воспроизводит файлы (rel 1e-12, пол 1e-10); коммит ядра в сравнение не входит.
По умолчанию файлы пишутся в `data/assumptions/` (их коммитит интеграция).
У книги с объектом ограничения роста капиталом полный расчёт пишет и «цену правила» (`rule_price`, М§14.5):
точка, медиана и масса капитального разрыва при трёх замыканиях капитала — без ограничения роста, «дивиденд по
политике, рост — остаток» и «сначала уступает дивиденд»; выпуск читает таблицу отсюда и сам её не считает.
Подписи строк — слова кода или подписи книги `meta.labels.rule_price.<замыкание>`.
Узлы гейтов этой панели (М§14.2) — только при своём ключе книги: `nim_lt` — печатаемая маржа модальной клетки
после фазы роста (`model.grid.printed_nim_lt`), `nim_stationary` — стационарная маржа мира-цели
(`model.levels.stationary_nim`), `funds_cost_to_key` — стоимость средств клиентов к ключевой ставке по мирам
(`model.levels.funds_cost_to_key`), `stress_sign` — гейт знака стресса (`model.grid.stress_sign_test`); число
гейта `volume_sign` — узел `sign_test`.
Узлы раздела «на чём стоит заголовок» (М§14.5), тоже только при своих ключах: `levels` — уровни после фазы
роста модальной клетки, слоёв и смеси точки (`model.levels.levels`; ключ `checks.window_backtest`),
`point_path` — годовой путь смеси точки рядом с модальной клеткой (`model.levels.point_path`; ключ
`checks.point_path`), `reference_variants` — справочные варианты: точка книги с подменами варианта по списку
`valuation.reference_variants` (одна лёгкая сетка на вариант; выпуск такта читает узел отсюда и варианты не
пересчитывает). Подмены варианта проходят обычную проверку книги: вариант с отказом — отказ сборки таблиц.
Рядом с вариантами таблицы несут отпечаток книги, на которой они посчитаны (`reference_variants_book`): выпуск
берёт узел только при том же отпечатке — устаревшие числа в выпуск не попадают.
Книга с ключом `valuation.reference_record` (М§14.5) цены вариантов и замыканий капитала берёт из записи сухого
перевывода развилок (файл рядом с книгой, инструмент `ops/tools/forks.py`): разности точки и медианы (`d_point`,
`d_median`) к книге, а не точку на замороженных выведенных числах. Варианта нет в записи или он без цены —
строка «без цены — причина»; запись от другой книги (числовой отпечаток `book_numbers` не совпал) — цены не
печатаются, таблицы и сборка пишут предупреждение. Суждение об уровне маржи
(`derived.nii.level_world` и выведенный уровень мира-опоры) печатается у книги с ключом
`nii.transmission.level_world`; окно фактов (`levels.window`) — при его полях в ключе `checks.window_backtest`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Mapping

from model.book import ROOT, Book, Facts, canonical_json, load_book, load_facts
from model.book_schema import BookError, FactsError
from model.capital import DIVIDEND_FIRST, GROWTH, GROWTH_FIRST
from model.checks import CIR_WORD, check_gates, check_invariants, ddm_ri_max, sign_numbers
from model.grid import (GridRun, LiveInputs, derived_values, live_from_book, modal_cell, printed_nim_lt,
                        realized_cells, run_grid, volume_sign_test)
from model.levels import LEVEL_ROWS, MGMT, funds_cost_to_key, levels, point_path, stationary_nim
from model import uncertainty as U

__all__ = ["book_results", "result_cells", "render_run_output", "rule_price", "reference_variants", "variant_book", "main",
           "by_price", "book_numbers", "numbers_view", "reference_record", "record_variants", "record_rule_price",
           "CENTRAL_RULE", "OUT_DIR", "RULE_TITLES", "REFERENCE_VARIANTS", "VARIANTS_BOOK", "RECORD_KEY", "RECORD_SCHEMA"]

OUT_DIR = ROOT / "data" / "assumptions"
CENTRAL_RULE = ("мода по каждой оси в слое «свой взгляд»: мир с наибольшим весом, режим с наибольшей вероятностью "
                "после наблюдений, сценарий капитала с наибольшей вероятностью при этом режиме; при равенстве — "
                "первый по порядку книги")
MESSAGE_WIDTH = 140       # строка сообщения проверки в `run_output.txt`; длинное переносится, а не обрезается
MESSAGE_INDENT = 35       # продолжение сообщения — под началом его первой строки (вид и имя проверки — слева)
UNCONSTRAINED = "unconstrained"
REFERENCE_VARIANTS = "valuation.reference_variants"   # [{id, title, overrides, note?}] — справочные варианты (М§14.5)
VARIANTS_BOOK = "reference_variants_book"             # узел таблиц: отпечаток книги, на которой посчитаны варианты
# Запись сухого перевывода развилок (М§14.5): файл рядом с книгой; её схема и слова, которыми таблицы называют её базу
RECORD_KEY = "valuation.reference_record"
RECORD_SCHEMA = "forks-rd-v1"
RECORD_BASIS = ("сухой перевывод книги под вариант (корни, концы осей и проверки выведены заново); точка — разность с точкой "
                "книги; медиана — разность медиан малой полосы на общих случайных числах ({runs} прогонов)")
# Текст книги, который в числовой отпечаток не входит: подписи и слова (ключи-имена со строкой), сама ссылка на запись
PROSE_KEYS = ("name", "title", "note", "words")
PROSE_PATHS = (("meta", "labels"), ("meta", "basis"), tuple(RECORD_KEY.split(".")))
# «Цена правила» (М§14.5): замыкания капитала по порядку строк и их подписи — слова кода; книга может
# заменить их подписями `meta.labels.rule_price.<замыкание>` (`rule_title`).
RULE_TITLES = {UNCONSTRAINED: "Без ограничения роста капиталом (как у образца)",
               DIVIDEND_FIRST: "Дивиденд по политике, рост — остаток",
               GROWTH_FIRST: "Сначала уступает дивиденд"}


def numbers_view(book: Book) -> Any:
    """Книга без текста (М§14.5): исходная книга без подписей `meta.labels`, `meta.basis`, ссылки на запись сухого
    перевывода и строковых ключей-слов (`name`, `title`, `note`, `words`) на любой глубине. Значения ключей — числа,
    выключатели, перечисления, пути осей — остаются."""
    def strip(x: Any, at: tuple) -> Any:
        if isinstance(x, Mapping):
            return {k: strip(v, at + (str(k),)) for k, v in x.items()
                    if not (str(k) in PROSE_KEYS and isinstance(v, str)) and at + (str(k),) not in PROSE_PATHS}
        if isinstance(x, (list, tuple)):
            return [strip(v, at) for v in x]
        return x
    return strip(book.source or book.data, ())


def book_numbers(book: Book) -> str:
    """Числовой отпечаток книги (М§14.5): sha256 канонического JSON книги без текста (`numbers_view`). Меняют его
    значения ключей, а не слова: переименование оси или правка подписи запись сухого перевывода не старит."""
    return hashlib.sha256(canonical_json(numbers_view(book))).hexdigest()


def reference_record(book: Book) -> tuple[dict | None, str | None]:
    """Запись сухого перевывода развилок книги (ключ `valuation.reference_record` — файл в каталоге книги) и причина,
    по которой её цены не печатаются: нет ключа — (None, None); нет файла, другая схема, запись от другой книги
    (числовой отпечаток не совпал) — (запись или None, причина словами)."""
    rel = book.opt(RECORD_KEY)
    if rel is None:
        return None, None
    path = (Path(book.path).parent if book.path is not None else OUT_DIR) / str(rel)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, f"нет записи сухого перевывода развилок ({rel})"
    if not isinstance(record, dict) or record.get("schema") != RECORD_SCHEMA:
        return None, f"запись сухого перевывода развилок ({rel}) — не схемы {RECORD_SCHEMA}"
    if (record.get("book") or {}).get("numbers") != book_numbers(book):
        return record, ("запись сухого перевывода развилок посчитана на другой книге (числовой отпечаток не совпал) — "
                        "цены не печатаются: перевывести развилки (ops/tools/forks.py) и пересобрать таблицы книги")
    return record, None


def _record_row(r: Mapping[str, Any] | None, why: str | None) -> dict[str, Any]:
    """Цена строки из записи: разности точки и медианы и пометки — или «без цены — причина»."""
    if why is not None:
        return {"d_point": None, "d_median": None, "why": why}
    if r is None:
        return {"d_point": None, "d_median": None, "why": "без цены: варианта нет в записи сухого перевывода развилок"}
    if r.get("d_point") is None:
        return {"d_point": None, "d_median": None, "why": str(r.get("why") or "без цены: перевывод не дал цены")}
    out = {"d_point": float(r["d_point"]), "d_median": float(r["d_median"])}
    for k in ("median_mark", "mark"):
        if r.get(k):
            out[k] = str(r[k])
    return out


def record_variants(book: Book, run: GridRun, record: Mapping[str, Any] | None, why: str | None) -> list[dict[str, Any]]:
    """Справочные варианты из записи сухого перевывода (М§14.5): строка на вариант списка книги, в его порядке —
    точка книги плюс разность записи (`point`, `d_point`), разность медиан (`d_median`) и пометки; без цены —
    `point`, `d_point`, `d_median` пусты, `why` — причина. `note` — как в книге."""
    rows = []
    for spec in book.opt(REFERENCE_VARIANTS) or []:
        r = _record_row(((record or {}).get("variants") or {}).get(str(spec["id"])), why)
        row = {"id": str(spec["id"]), "title": str(spec["title"]),
               "point": None if r["d_point"] is None else run.point + r["d_point"], **r}
        if spec.get("note") is not None:
            row["note"] = str(spec["note"])
        rows.append(row)
    return rows


def record_rule_price(book: Book, run: GridRun, record: Mapping[str, Any] | None, why: str | None) -> dict[str, Any] | None:
    """«Цена правила» из записи сухого перевывода (М§14.5): замыкание книги — сама книга (разности нулевые, масса
    капитального разрыва — её сетки), два других — разности точки и медианы записи и масса капитального разрыва
    пробной книги замыкания; без цены — причина. Медиан в рублях строка не несёт: база разностей — малая полоса."""
    plan = rule_closures(book)
    if plan is None:
        return None
    current = plan[0]
    rows = []
    for key in plan[1]:
        row: dict[str, Any] = {"key": key, "title": rule_title(book, key), "current": key == current}
        if key == current:
            row.update(point=run.point, d_point=0.0, d_median=0.0, capital_gap_mass=run.layers["analytical"].capital_gap_mass)
        else:
            rec = ((record or {}).get("rule_price") or {}).get(key)
            r = _record_row(rec, why)
            row.update(point=None if r["d_point"] is None else run.point + r["d_point"], **r,
                       capital_gap_mass=None if r["d_point"] is None else (rec or {}).get("capital_gap_mass"))
        rows.append(row)
    return {"rows": rows, "median_draws": None}


def record_node(book: Book, record: Mapping[str, Any] | None, why: str | None) -> dict[str, Any] | None:
    """Узел таблиц о записи сухого перевывода: файл, отпечатки, база разностей и предупреждение (запись непригодна)."""
    if book.opt(RECORD_KEY) is None:
        return None
    base = (record or {}).get("base") or {}
    return {"file": str(book.get(RECORD_KEY)), "numbers": ((record or {}).get("book") or {}).get("numbers"),
            "book_numbers": book_numbers(book), "matches": why is None,
            "basis": RECORD_BASIS.format(runs=base.get("runs", "—")), "warning": why}


def rule_title(book: Book, key: str) -> str:
    """Подпись строки «цены правила»: `meta.labels.rule_price.<key>` книги, без ключа — слово кода."""
    return book.label_or(f"rule_price.{key}", RULE_TITLES[key])


def _layer(L, buyback: bool = False) -> dict[str, Any]:
    """Слой таблиц книги; при выкупе по цене мира (М§5.6) — и строка `buyback_effect` (v0 = bv_v + pv_ri_explicit +
    pv_terminal + buyback_effect); без ключа — прежний узел."""
    return {"title": L.title, "world_weights": dict(L.world_weights), "v0": L.v0, "bv_v": L.bv_v, "price": L.price,
            "pb": L.pb, "excess": L.excess, "pv_ri_explicit": L.pv_ri_explicit, "pv_terminal": L.pv_terminal,
            "terminal_share": L.terminal_share, "roe_tc": L.roe_tc, "k_tc": L.k_tc,
            "p_price_below_market": L.p_price_below_market, "p_roe_below_k": L.p_roe_below_k,
            "capital_gap_mass": L.capital_gap_mass, **({"buyback_effect": L.buyback_effect} if buyback else {})}


def result_cells(run: GridRun) -> list[dict[str, Any]]:
    """Клетки таблиц книги (results.json → cells): стоимость и P/B клетки — оценка в цене (М§8.2; при выкупе по цене
    мира — V̂_c, рядом V_RI, S_c и акции на конце сетки, М§5.6); узел постоянных частей терминала — при своём ключе
    (М§7). Без ключей прохода — прежние поля (v_price — тот же объект, что v_ri)."""
    ay = run.ctx.timeline.anchor_year
    return [{"world": c.world, "regime": c.regime, "scenario": c.scenario, "v": c.v_price, "v_ddm": c.v_ddm,
             "bv_v": c.bv_v, "pb": c.v_price / c.bv_v, "roe_t": c.roe_t, "k_t": c.k_t, "g_t": c.g_t,
             "n20_min": c.n20_min, "n11_min": c.n11_min, "dps_first": c.dps.get(ay), "flags": sorted(c.flags),
             **({} if c.terminal_fixed is None else {"terminal_fixed": dict(c.terminal_fixed)}),
             **({} if c.terminal_stationary is None else {"terminal_stationary": dict(c.terminal_stationary)}),
             **({} if c.terminal_year is None else {"terminal_year": dict(c.terminal_year)}),
             **({} if c.terminal_fade is None else {"terminal_fade": dict(c.terminal_fade)}),
             **({} if c.v_hat is None else {"v_ri": c.v_ri, "s_price": c.s_price, "n_t": c.n_t})}
            for c in run.cells]


def book_results(book: Book | None = None, facts: Facts | None = None, *, slow: bool = True) -> dict:
    """Таблицы книги; `slow=False` — быстрая полоса без поисков (проверка, не регрессия)."""
    facts = facts or load_facts()
    book = book or load_book(facts=facts)
    live = live_from_book(book, facts)
    run = run_grid(book, facts, live)
    draws = int(book.get("valuation.uncertainty.draws")) if slow else U.FAST_DRAWS
    band = U.band(book, facts, live, draws=draws, keep=slow)       # записи — уточнению обратного расчёта
    main = str(book.get("meta.company.main_ticker"))
    lam = run.lam
    h = band.headline(lam, live.prices, main)
    step = band.print_step
    headline = {"median": h["median"], "printed_median": h["printed_median"], "band80": h["band80"],
                "printed_band80": h["printed_band80"], "band50": h["band50"], "printed_band50": h["printed_band50"],
                "p10": h["p10"], "p25": h["p25"], "p75": h["p75"], "p90": h["p90"],
                "mean": h["mean"], "p_below_market": h["p_below_market"], "market": h["market"],
                "market_by_ticker": h["market_by_ticker"], "p_below_by_ticker": h["p_below_by_ticker"],
                "upside": h["upside"],
                "point": run.point, "printed_point": U.round_half_up(run.point, step), "low": run.low, "high": run.high,
                "rates_view": run.high - run.low, "lambda": lam, "draws": band.draws, "seed": band.seed,
                "ddm_ri_max": max(band.ddm_ri_max, ddm_ri_max(run)),
                "contributions": [{k: c[k] for k in ("axis", "name", "share", "rank_corr")}
                                  for c in band.contributions(lam)]}
    cells = result_cells(run)
    key = modal_cell(book, run.ctx.posterior)
    cc = run.cell(*key)
    central = {"cell": "/".join(key), "probability": run.layers["analytical"].prob[key],
               "scenario_weight": float(book.get(f"joint.reg_prob_given_regime.{key[1]}.{key[2]}")),
               "rule": CENTRAL_RULE, "years": list(cc.years),
               **{k: list(v) for k, v in cc.annual.items()},
               "v": cc.v_price, "bv_v": cc.bv_v, "roe_t": cc.roe_t, "k_t": cc.k_t, "g_t": cc.g_t, "x_t": cc.x_t,
               "terminal_share": cc.terminal_share}
    judg = U.judgements(book, facts, live, band, point=run.point) if slow else None
    off_band = U.off_band_shift(book, facts, live, run.point, judg)
    # числа гейтов знака — один раз на центральной книге: их читают гейты и узлы таблиц (М§14.2)
    signs = sign_numbers(run)
    sign = signs["volume_sign"] if signs["volume_sign"] is not None else volume_sign_test(book, facts, run=run)
    stress = signs["stress_sign"]
    findings = check_invariants(run, band) + check_gates(run, off_band=off_band, band=band, **signs)
    checks = [{"name": f.name, "kind": f.kind, "fired": f.fired, "mass": f.mass, "message": f.message}
              for f in findings]
    derived = derived_values(run.ctx)
    derived["nii"]["realized_cells"] = realized_cells(run)
    out = {"book_version": str(book.get("meta.version")), "facts_date": str(book.get("meta.facts_date")),
           "engine_commit": _commit(), "draws": band.draws, "slow": slow, "derived": derived,
           "layers": {k: _layer(L, run.ctx.prep.bb is not None) for k, L in run.layers.items()}, "headline": headline, "cells": cells,
           "central_cell": central, "sign_test": sign, "checks": checks}
    nim_lt = printed_nim_lt(run)
    if nim_lt is not None:                      # печатаемая маржа после фазы роста — только при ключе книги
        out["nim_lt"] = {**nim_lt, "key": float(book.get("nii.nim_lt_target_mgmt"))}
    if stress is not None:
        out["stress_sign"] = stress
    # узлы «на чём стоит заголовок» — на готовой сетке, каждый при своём ключе книги (М§14.5)
    for name, node in (("nim_stationary", stationary_nim(run.ctx)), ("levels", levels(run)),
                       ("point_path", point_path(run)), ("funds_cost_to_key", funds_cost_to_key(run))):
        if node is not None:
            out[name] = node
    record, record_why = reference_record(book)
    keyed = book.opt(RECORD_KEY) is not None    # цены — из записи сухого перевывода развилок (М§14.5)
    if keyed:
        out["reference_record"] = record_node(book, record, record_why)
        if record_why is not None:
            print(f"ПРЕДУПРЕЖДЕНИЕ: {record_why}", file=sys.stderr)
    variants = (record_variants(book, run, record, record_why) if keyed and book.opt(REFERENCE_VARIANTS) is not None
                else None if keyed else reference_variants(book, facts, live, run))
    if variants is not None:                    # справочные варианты — только при списке книги (М§14.5)
        out["reference_variants"] = variants
        out[VARIANTS_BOOK] = book.digest        # на какой книге посчитаны: выпуск сверяет отпечаток
    if slow:
        from model.nextreport import next_report
        from model.reverse import reverse_dcf
        anchor = U.MedianAnchor(book, facts, live, band)
        out["reverse_dcf"] = reverse_dcf(book, facts, live, band, anchor=anchor, run=run)
        out["next_report"] = next_report(book, facts, live, band, anchor=anchor, run=run)
        out["judgements"] = judg
        out["off_band_shift"] = off_band
        rule = record_rule_price(book, run, record, record_why) if keyed else rule_price(book, facts, live, run, anchor)
        if rule is not None:                    # раздел — только у книги с объектом ограничения роста (М§14.5)
            out["rule_price"] = rule
    else:
        out["reverse_dcf"] = out["next_report"] = out["judgements"] = None
    return out


def rule_closures(book: Book) -> tuple[str, dict[str, dict[str, Any]]] | None:
    """Замыкание книги и подмены трёх замыканий капитала (М§14.5): `unconstrained` — выключатель ограничения
    роста, два других — порядок «дивиденд или рост»; у замыкания самой книги подмен нет. Объекта
    `capital.growth_constraint` в книге нет — None."""
    spec = book.opt(GROWTH)
    if spec is None:
        return None
    current = str(spec["order"]) if spec.get("enabled") is True else UNCONSTRAINED
    closures: dict[str, dict[str, Any]] = {UNCONSTRAINED: {f"{GROWTH}.enabled": False}}
    for order in (DIVIDEND_FIRST, GROWTH_FIRST):
        closures[order] = {f"{GROWTH}.order": order}
        if spec.get("enabled") is not True:
            closures[order][f"{GROWTH}.enabled"] = True
    closures[current] = {}
    return current, closures


def rule_price(book: Book, facts: Facts, live: LiveInputs, run: GridRun,
               anchor: U.MedianAnchor | None = None) -> dict[str, Any] | None:
    """«Цена правила» (М§14.5): оценка при трёх замыканиях капитала — точка, медиана и масса гейта
    капитального разрыва (слой «свой взгляд»). Замыкание книги считается на ней самой (`run`), два других —
    подменой; медиана — пересчётом `anchor` на общих случайных числах с привязкой к печатаемой (без него —
    нет значения). Замыкание, которого книга не допускает (нет полей объекта, годовой календарь), — строка без
    чисел с причиной."""
    plan = rule_closures(book)
    if plan is None:
        return None
    current, closures = plan
    lam = run.lam
    rows = []
    for key, overrides in closures.items():
        row = {"key": key, "title": rule_title(book, key), "point": None, "median": None, "capital_gap_mass": None,
               "current": key == current}
        try:
            trial = book.with_overrides(overrides) if overrides else book
            grid = run if not overrides else run_grid(trial, facts, live, summary=True)
            row.update(point=grid.point, capital_gap_mass=grid.layers["analytical"].capital_gap_mass)
            if anchor is not None:
                row["median"] = anchor.at(trial if overrides else None, lam=lam)["central"]
        except (BookError, FactsError, KeyError) as exc:
            row["reason"] = str(exc).splitlines()[0]
        rows.append(row)
    return {"rows": rows, "median_draws": None if anchor is None else anchor.n}


def variant_book(book: Book, spec: Mapping[str, Any]) -> Book:
    """Книга справочного варианта (М§14.5): книга с подменами `spec["overrides"]` по путям; подмена может
    ввести необязательный ключ схемы. Числа, выведенные на ядре, не пересчитываются — вариант несёт их сам,
    подменами. Подмены проходят обычную проверку книги; отказ — `BookError` с идентификатором варианта."""
    try:
        return book.with_overrides(dict(spec["overrides"]), create=True)
    except BookError as exc:
        raise BookError(f"{REFERENCE_VARIANTS}, вариант {spec.get('id')!r}: {exc}") from None


def reference_variants(book: Book, facts: Facts, live: LiveInputs, run: GridRun) -> list[dict[str, Any]] | None:
    """Справочные варианты (М§14.5): цена названных правил и развилок книги — только точка. Строка на вариант
    списка `valuation.reference_variants`: точка книги с подменами варианта (одна лёгкая сетка на входах `live`)
    и её разность с точкой книги (`run`). Нет ключа — None; вариант, чья книга не проходит схему, — `BookError`
    (сборка таблиц падает). Строки — в порядке списка книги; необязательная подпись варианта `note` — как в
    книге."""
    specs = book.opt(REFERENCE_VARIANTS)
    if specs is None:
        return None
    rows = []
    for spec in specs:
        grid = run_grid(variant_book(book, spec), facts, live, summary=True)
        row = {"id": str(spec["id"]), "title": str(spec["title"]), "point": grid.point,
               "d_point": grid.point - run.point}
        if spec.get("note") is not None:        # подпись строки — как в книге
            row["note"] = str(spec["note"])
        rows.append(row)
    return rows


def by_price(rows: Any) -> list:
    """Строки справочных вариантов по убыванию модуля цены правила (`d_point`); равные — в порядке списка книги;
    строки без цены — последними. Так их печатают сводка таблиц и выпуск: главная развилка — первой строкой."""
    return sorted(rows, key=lambda r: (r.get("d_point") is None, -abs(float(r.get("d_point") or 0.0))))


def _commit() -> str:
    from model.payload import engine_commit
    return engine_commit()


def _f(x: Any, nd: int = 2) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.{nd}f}".replace(",", " ")
    return str(x)


def _p(x: Any, nd: int = 2) -> str:
    return "—" if x is None else f"{100 * x:.{nd}f} %"


def render_run_output(results: Mapping[str, Any], book: Book | None = None) -> str:
    """Текстовая сводка результатов книги (для людей и диффа). `book` — книга результатов: из неё слова
    прибыли и норматива (`meta.labels`, М§0.6); нет — книга репозитория."""
    book = book or load_book()
    profit, n20 = book.label("terms.profit_short"), book.label("capital.n20_short")
    h = results["headline"]
    L = results["layers"]
    step = f"{float(book.get('valuation.headline.print_step')):g}"
    nd = len(step.partition(".")[2])            # знаки печати — по шагу печати книги (0,1 ₽ → один знак)
    lines = [f"Книга {results['book_version']} · факты на {results['facts_date']} · прогонов полосы {results['draws']}"
             + ("" if results.get("slow") else " (быстрая проверка, не регрессия)"), "",
             "ЗАГОЛОВОК (₽ на акцию)",
             f"  медиана {_f(h['median'])} → печать {_f(h['printed_median'], nd)}; полоса 80 % {_f(h['band80'][0])}–"
             f"{_f(h['band80'][1])} (печать {_f(h['printed_band80'][0], nd)}–{_f(h['printed_band80'][1], nd)}); "
             f"50 % {_f(h['band50'][0])}–{_f(h['band50'][1])}",
             f"  среднее {_f(h['mean'])}; P(центр < рынка {h['market']:g}) = {_p(h['p_below_market'], 1)}",
             f"  точка при λ = {h['lambda']:g}: {_f(h['point'])} (печать {_f(h['printed_point'], nd)}); низ {_f(h['low'])}, "
             f"верх {_f(h['high'])}, взгляд на ставки {_f(h['rates_view'])}", "", "СЛОИ"]
    for k, v in L.items():
        lines.append(f"  {v['title']:<28} V0 {_f(v['v0'], 1):>10}  BV_v {_f(v['bv_v'], 1):>9}  цена {_f(v['price']):>8}  "
                     f"P/B {v['pb']:.3f}  ROE'_T {_p(v['roe_tc'])}  k_T {_p(v['k_tc'])}")
    lines += ["", "ВКЛАДЫ ОСЕЙ В ПОЛОСУ (доля квадрата ранговой корреляции)"]
    for c in h["contributions"][:12]:
        lines.append(f"  {c['share']:6.3f}  ρ {c['rank_corr']:+.3f}  {c['name']}")
    d = results["derived"]["nii"]
    lines += ["", "ПЕРЕДАЧА СТАВКИ",
              f"  σ0 активов {d['sigma0']:+.6f}, σ0 пассивов {d.get('sigma0_liab', 0.0):+.6f} (доля на активах "
              f"{d.get('sigma0_split', 1.0):g}), φ {d['phi']:.6f}: активы {d.get('phi_assets', d['phi']):.6f}, "
              f"пассивы {d.get('phi_liab', 0.0):.6f} (доля на активах {d.get('phi_split', 1.0):g}), "
              f"T_real {d['T_real']:.6f}, цель движка "
              f"{d['target_eng']:.6f}, ROE-экв. {d['roe_equiv']:.4f}, по клеткам {d['realized_cells']:.6f}",
              *([f"  ключ цели ЧПМ — стационарная маржа мира {d['level_world']} на составе баланса якоря; выведенный "
                 f"уровень мира-опоры {d['reference_world']}: {_p(d['reference_level_mgmt'], 3)} упр. "
                 f"({d['reference_level']:.6f} в движке)"] if d.get("level_world") else []),
              "  кредитная маржа стационара: " + ", ".join(f"{w} {_p(v)}" for w, v in (d.get("loan_margin") or {}).items()),
              "  LT-спред кредитных книг к опоре: " + "; ".join(
                  f"{b} " + ", ".join(f"{w} {_p(v)}" for w, v in row.items())
                  for b, row in (d.get("lt_spread") or {}).items()),
              # Р11-1 (проход ядра 9): сдвиг ставки книги в стационаре мира от доли сжатия между мирами
              *(["  доли сжатия книг (сдвиг ставки в стационаре мира, −share × (ref_W − ref_H)): " + "; ".join(
                  f"{b} " + ", ".join(f"{w} {_p(v)}" for w, v in row.items())
                  for b, row in d["share_lt"].items())] if d.get("share_lt") else []),
              "  T(W): " + ", ".join(f"{w} {v:.4f}" for w, v in d["T"].items()),
              "  пары: " + ", ".join(f"{k.replace('_', '→')} " + ("—" if v is None else f"{v:.4f}")
                                    + ("" if (d.get("roe_equiv_pairs") or {}).get(k) is None
                                       else f" (ROE-экв. {d['roe_equiv_pairs'][k]:.3f})")
                                    for k, v in (d.get("T_pairs") or {}).items()),
              f"  DDM = RI: макс. отн. разность по сетке и полосе {h.get('ddm_ri_max', 0.0):.1e}"]
    st = results.get("sign_test")
    if st:
        lines.append("  тест знака (снятие остановки кредита в кризисе и поправок роста режимов"
                     + (", при выключенном ограничении роста" if st.get("growth_constraint_off") else "") + "): точка "
                     f"{st['d_point']:+.2f} ₽; миры " + ", ".join(f"{w} {v:+.2f}" for w, v in st["d_world"].items())
                     + (" — выполнен" if st["ok"] else " — НЕ выполнен"))
    nl = results.get("nim_lt")
    if nl:
        lines.append(f"  печатаемая маржа {book.label('terms.lt_level')}: модальная клетка {nl['cell']}, среднее упр. ЧПМ "
                     f"{nl['from_year']}–{nl['to_year']} годов {_p(nl['value'])} при цели {_p(nl.get('target'))} ± "
                     f"{_p(nl.get('tolerance'))}; ключ цели ЧПМ {_p(nl['key'])}")
    ss = results.get("stress_sign")
    if ss:
        lines.append(f"  знак стресса: убыток кризиса больше на {_f(ss['loss']['step'], 0)} млрд ₽ — стоимость растёт в "
                     f"{len(ss['loss']['cells'])} клетках; прибыль последнего года растёт с требованием в "
                     f"{len(ss['requirement']['cells'])} парах сценариев; масса {_p(ss['mass'], 1)} под вероятностями "
                     f"точки" + ("" if ss.get("mass_analytical") is None
                                 else f" ({_p(ss['mass_analytical'], 1)} под весами слоя «свой взгляд»)")
                     + f", наибольшее превышение {_f(ss['max_excess'], 1)} млрд ₽"
                     + ("" if ss["loss"].get("transfer_min") is None
                        else f"; снижение стоимости клетки на рубль убытка после налога — от "
                             f"{_f(ss['loss']['transfer_min'])} до {_f(ss['loss']['transfer_max'])} ₽")
                     + (" — выполнен" if ss["ok"] else " — НЕ выполнен"))
    ns = results.get("nim_stationary")
    if ns:
        lines.append(f"  стационарная маржа мира {ns['world']} на составе баланса якоря (упр.): {_p(ns['value'])} при цели "
                     f"{_p(ns['target'])} ± {_p(ns['tolerance'])}; ключ цели ЧПМ {_p(ns['key'])}")
    fc = results.get("funds_cost_to_key")
    if fc:
        lines.append(f"  стоимость средств клиентов к ключевой ставке, {fc['from_year']}–{fc['to_year']} годы: "
                     + ", ".join(f"{row['cell']} {row['ratio']:.3f}"
                                 + ("" if "modal_cell" not in row else
                                    f" (модальная клетка {row['modal_cell']} {row['modal_ratio']:.3f})")
                                 for row in fc["by_world"].values())
                     + f" при пороге {fc['max']:.3f}" + (" — выполнен" if fc["ok"] else " — НЕ выполнен"))
    cc = results["central_cell"]
    lines += ["", f"ЦЕНТРАЛЬНАЯ (МОДАЛЬНАЯ) КЛЕТКА {cc['cell']} (вероятность {_p(cc.get('probability'), 1)}, вес сценария "
              f"{_p(cc.get('scenario_weight'), 0)}): V {_f(cc['v'], 1)}, BV_v {_f(cc['bv_v'], 1)}, ROE'_T {_p(cc['roe_t'])}, "
              f"k_T {_p(cc['k_t'])}, g_T {_p(cc['g_t'])}, доля терминала {_p(cc['terminal_share'], 1)}",
              "  год      " + "".join(f"{y:>9}" for y in cc["years"])]
    cir = book.label_or("terms.cir", CIR_WORD)
    for key, title, pct in (("ni_sh", f"{profit} акц.", False), ("roe", "ROE", True), ("nim", "ЧПМ дв.", True),
                            ("cor", "CoR дв.", True), ("cir", cir, True), ("n20", n20, True), ("dps", "DPS", False)):
        vals = cc.get(key) or []                # DPS — двумя знаками: жетон 0,35 ₽ одним знаком печатался бы «0.3»
        lines.append(f"  {title:<8} " + "".join(f"{(_p(v, 1) if pct else _f(v, 2 if key == 'dps' else 1)):>9}" for v in vals))
    lv = results.get("levels")
    if lv:
        lines += ["", f"УРОВНИ ПОСЛЕ ФАЗЫ РОСТА: средние {lv['from_year']}–{lv['to_year']} годов, упр. базис (слои и "
                      "смесь — отношение ожидаемых агрегатов)",
                  f"  {'':<28}{'ЧПМ':>9}{'CoR':>9}{cir:>9}{'кредиты в проц. активах':>26}"]
        for key in lv.get("order") or LEVEL_ROWS:
            r = lv["rows"][key]
            name = r["title"] + (f" {lv['cell']}" if key == "modal_cell" else "")
            lines.append(f"  {name:<28}{_p(r['nim']):>9}{_p(r['cor']):>9}{_p(r['cir'], 1):>9}{_p(r['loans_share'], 1):>26}")
            if "cor_mix0" in r:                 # множители CoR по книгам: CoR на составе якоря (М§4.6)
                lines.append(f"  {'  CoR на составе якоря':<28}{'':>9}{_p(r['cor_mix0']):>9}")
        win = lv.get("window")
        if win:                                 # окно фактов — мерка уровней: наименьший…наибольший квартал и среднее
            span = lambda m, nd: f"{_p(m['min'], nd)} … {_p(m['max'], nd)} (среднее {_p(m['mean'], nd)})"  # noqa: E731
            lines.append("  окно фактов: " + "; ".join(
                f"{title} {span(win[k], nd)}" for k, title, nd in zip(MGMT, ("ЧПМ", "CoR", cir), (2, 2, 1)))
                + f"; кредиты в процентных активах — окно {_p(win['loans_share']['window'], 1)}, якорь "
                  f"{_p(win['loans_share']['anchor'], 1)}")
    pp_ = results.get("point_path")
    if pp_:
        mc = pp_["modal_cell"]
        lines += ["", f"ПУТЬ СМЕСИ ТОЧКИ (модальная клетка {mc['cell']}: вес в слое «свой взгляд» {_p(mc['p_analytical'], 1)}, "
                      f"в смеси точки {_p(mc['p_point'], 1)}, цена {_f(mc['price'])} ₽ на акцию)",
                  "  год      " + "".join(f"{y:>9}" for y in pp_["years"])]
        for key, title, pct in (("ni_sh", f"{profit} акц.", False), ("nim_mgmt", "ЧПМ упр.", True),
                                ("cor_mgmt", "CoR упр.", True), ("cir_mgmt", f"{cir} упр.", True), ("roe", "ROE", True),
                                ("dps", "DPS", False)):
            lines.append(f"  {title:<8} " + "".join(f"{(_p(v, 1) if pct else _f(v, 2 if key == 'dps' else 1)):>9}"
                                                    for v in pp_[key]))
        lines.append(f"  {'мод. кл.':<8} " + "".join(f"{_f(v, 1):>9}" for v in mc["ni_sh"]))
    lines += ["", "ПРОВЕРКИ"]
    for c in results["checks"]:
        mark = ("НАРУШЕН" if c["kind"] == "invariant" else "сработал") if c["fired"] else "ок"
        mass = "" if c["mass"] is None else f" (масса {c['mass']:.3f})"
        # Сообщение — целиком: длинное переносится под своё начало (в хвосте сообщения гейта — прогоны полосы).
        first, *rest = textwrap.wrap(c["message"], MESSAGE_WIDTH, break_on_hyphens=False) or [""]
        lines.append(f"  {c['kind']:<9} {c['name']:<22} {mark}{mass}: {first}")
        lines += [" " * MESSAGE_INDENT + part for part in rest]
    rev = results.get("reverse_dcf")
    if rev:
        lines += ["", f"ЧТО В ЦЕНЕ (медиана = {_f(rev['target'])} ₽)"]
        for r in rev["rows"]:                              # «в диапазоне» — только о корне (М§11.2)
            where = "" if r["status"] != "solved" else ", в диапазоне" if r["in_range"] else ", вне диапазона"
            if r["status"] == "solved" and rev.get("refine_rows") is not None and r["key"] not in rev["refine_rows"]:
                where += ", оценка по подвыборке"       # строку не назвал список книги: на полной полосе не уточнялась
            loose = ", уточнение не сошлось" if r["status"] == "solved" and r.get("converged") is False else ""
            edge = f", {r['reason']}" if r["status"] == "unreachable" and r.get("reason") else ""
            printed = "" if "printed_book" not in r else (
                f"; печатаемая маржа модальной клетки {_p(r['printed_book'])} → {_p(r.get('printed_solved'))}")
            if "stationary_book" in r:          # суждение о марже — стационарная маржа мира-цели; уровни при корне
                at_root = (r.get("levels_solved") or {}).get("macro_neutral") or {}
                printed = (f"; стационарная маржа мира-цели {_p(r['stationary_book'])} → {_p(r.get('stationary_solved'))}"
                           + ("" if not at_root else f"; слой «рыночные ставки как есть» при корне: ЧПМ "
                                                     f"{_p(at_root.get('nim'))}, CoR {_p(at_root.get('cor'))}, "
                                                     f"{cir} {_p(at_root.get('cir'), 1)}"))
            lines.append(f"  {r['name']:<44} книга {_f(r['book'], 4):>9} → {_f(r['solved'], 4):>9} "
                         f"({r['status']}{where}{loose}{edge}; невязка {_f(r['gap'])} ₽{printed})")
        for r in rev["bank_rows"]:
            lines.append(f"  {r['title']:<44} книга {_f(r['book'], 4):>9} → {_f(r['implied'], 4):>9} ({r['status']})")
    nr = results.get("next_report")
    if nr:
        n = nr["neutral"]
        e = nr["expectation"]
        lines += ["", f"ЧТО ДАСТ ОТЧЁТ {nr['period']}: ожидание CoR упр. {_p(e['cor_mgmt'])}, ЧПМ упр. {_p(e['nim_mgmt'])}, "
                      f"{profit} {_f(e['ni'], 1)} млрд",
                  f"  нейтральная CoR {_p(n['cor']['value'])} (невязка {_f(n['cor']['gap_rub'])} ₽, экв. {profit} "
                  f"{_f(n['cor']['ni_equivalent'], 1)}); нейтральная ЧПМ {_p(n['nim']['value'])} "
                  f"(невязка {_f(n['nim']['gap_rub'])} ₽, экв. {profit} {_f(n['nim']['ni_equivalent'], 1)})",
                  f"  местный наклон: {_f(nr['slope']['rub_per_01pp_cor'])} ₽ на 0,1 п.п. CoR; "
                  f"{_f(nr['slope']['rub_per_01pp_nim'])} ₽ на 0,1 п.п. ЧПМ" + (f"; {n['error']}" if n.get("error") else "")]
        rc = nr.get("reaction") or {}
        if rc:
            lines.append("  размах реакции медианы: CoR "
                         f"{_f(rc['cor']['d_median_min'])}…{_f(rc['cor']['d_median_max'])} ₽; ЧПМ "
                         f"{_f(rc['nim']['d_median_min'])}…{_f(rc['nim']['d_median_max'])} ₽")
    rec = results.get("reference_record")
    if rec:                                     # цены вариантов и замыканий — из записи сухого перевывода (М§14.5)
        lines += ["", f"ЗАПИСЬ СУХОГО ПЕРЕВЫВОДА РАЗВИЛОК ({rec['file']}): " + ("числовой отпечаток книги совпал" if rec.get("matches")
                                                                                else "ПРЕДУПРЕЖДЕНИЕ — " + str(rec.get("warning")))]
        lines += [" " * 2 + part for part in textwrap.wrap(str(rec.get("basis")), MESSAGE_WIDTH - 2, break_on_hyphens=False)]
    d2 = lambda x: "—" if x is None else f"{x:+.2f}"  # noqa: E731
    rule = results.get("rule_price")
    if rule and rec:
        lines += ["", "ЦЕНА ПРАВИЛА: три замыкания капитала (точка — ₽ на акцию; к книге — разности точки и медианы; масса "
                      "капитального разрыва — слой «свой взгляд»)"]
        for r in rule["rows"]:
            mark = " ← книга" if r.get("current") else ""
            lines.append(f"  {r['title']:<52} точка {_f(r['point']):>8}  к книге {d2(r.get('d_point')):>6} / "
                         f"{d2(r.get('d_median')):>6}  разрыв {_p(r.get('capital_gap_mass'), 1):>7}{mark}")
            if r.get("why"):
                lines.append(" " * 4 + str(r["why"]))
    elif rule:
        lines += ["", "ЦЕНА ПРАВИЛА: три замыкания капитала (точка и медиана — ₽ на акцию; масса капитального "
                      "разрыва — слой «свой взгляд»)"]
        for r in rule["rows"]:
            mark = " ← книга" if r.get("current") else ""
            lines.append(f"  {r['title']:<52} точка {_f(r['point']):>8}  медиана {_f(r['median']):>8}  "
                         f"разрыв {_p(r['capital_gap_mass'], 1):>7}{mark}")
    variants = results.get("reference_variants")
    if variants:
        lines += ["", "ЦЕНА ПРАВИЛ И РАЗВИЛОК: справочные варианты (точка, ₽ на акцию; к точке книги"
                  + (" и к медиане — сухим перевыводом)" if rec else ")")]
        for r in by_price(variants):
            if rec:
                lines.append(f"  {r['title'][:70]:<70} точка {_f(r['point']):>8}  к книге {d2(r.get('d_point')):>6} / "
                             f"{d2(r.get('d_median')):>6}")
            else:
                lines.append(f"  {r['title'][:70]:<70} точка {_f(r['point']):>8}  к книге {r['d_point']:+.2f}")
            for text in (r.get("note"), r.get("why"), r.get("mark"), r.get("median_mark")):
                if text:
                    lines += [" " * 4 + part for part in textwrap.wrap(str(text), MESSAGE_WIDTH - 4, break_on_hyphens=False)]
    judg = results.get("judgements")
    if judg:
        ob = results.get("off_band_shift") or {}
        total = sum(r["mean_shift"] for r in judg if r.get("in_band") and r.get("mean_shift") is not None)
        lines += ["", "ЦЕНА ОШИБКИ СУЖДЕНИЙ (точка на краях оси; сдвиг положения — первый порядок «среднее − точка»)",
                  f"  Σ сдвигов положения осей полосы {_f(total)} ₽; осей вне полосы {ob.get('axes', 0)}: "
                  f"{_f(ob.get('rub'))} ₽ при пороге {_f(ob.get('limit'))} ₽"]
        for r in judg[:12]:
            lines.append(f"  {r['name'][:52]:<52} {_f(r['price_low']):>8} … {_f(r['price_high']):>8}  размах "
                         f"{_f(r['swing']):>7}  сдвиг {_f(r['mean_shift']):>7}")
    return "\n".join(lines) + "\n"


def _default(o: Any) -> Any:
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m model.book_results", description="results.json и run_output.txt книги")
    ap.add_argument("--fast", action="store_true", help="быстрая полоса без поисков (не регрессия)")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="каталог для results.json и run_output.txt")
    args = ap.parse_args(argv)
    try:
        facts = load_facts()
        book = load_book(facts=facts)
        res = book_results(book, facts, slow=not args.fast)
    except Exception as exc:  # noqa: BLE001 — любой отказ — код 1 с причиной
        print(f"ПРОВАЛ: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_default) + "\n",
                                           encoding="utf-8", newline="\n")
    (args.out / "run_output.txt").write_text(render_run_output(json.loads(json.dumps(res, default=_default)), book),
                                             encoding="utf-8", newline="\n")
    print(f"готово: {args.out / 'results.json'}, {args.out / 'run_output.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
