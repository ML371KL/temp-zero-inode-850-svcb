"""Помощники тестов ядра части 2 (core2): книга и факты, малые книги полосы, выходы индикаторов.

Книга и факты — настоящие (`data/`), когда они есть, иначе фикстура core1. Малые книги
уменьшают число прогонов (`median_draws`, `subsample`), чтобы тесты шли секунды; полный
выпуск тесты не собирают (сторож такта, `tests/conftest.py`).
"""

from __future__ import annotations

import functools
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from model.book import Book, Facts
from tests.support_core import (FIXTURE_BOOK, REAL_BOOK, fixture_book, fixture_facts, real_facts_ready)

try:
    from indicators.outputs import IndicatorOutputs, PricePoint
except ImportError:      # копия без слоя индикаторов (одно ядро) — заглушка с тем же интерфейсом
    sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "core2"))
    from outputs_stub import IndicatorOutputs, PricePoint  # type: ignore  # noqa: E402

TODAY = date(2026, 10, 1)
# Сводка сверки с контрольной моделью в формате П§2 (W2) — своя заглушка: файл `data/checks/` пишет поток
# control, и тесты ядра не зависят от того, пересобран ли он уже.
CONTROL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "core2" / "control_model.json"


REAL_UNAVAILABLE: list[str] = []     # почему настоящие книга и факты не взяты (для отчёта прогона)


@functools.lru_cache(maxsize=None)
def book_and_facts() -> tuple[Book, Facts]:
    """Настоящие книга и факты, если есть и они в договоре ядра, иначе фикстура core1.

    Книга или факты не в договоре (например, волна правок книги ещё не дошла) — тесты части 2
    идут на фикстуре; саму настоящую книгу строго проверяют `tests/test_core_real.py`."""
    from model.book import load_book, load_facts
    from model.book_schema import BookError, FactsError
    from model.credit import bridge_from_facts
    if REAL_BOOK.exists() and real_facts_ready():
        try:
            facts = load_facts()
            book = load_book(facts=facts)
            bridge_from_facts(facts)
            return book, facts
        except (BookError, FactsError) as exc:
            REAL_UNAVAILABLE.append(f"{type(exc).__name__}: {str(exc)[:300]}")
    return fixture_book(), fixture_facts()


def is_second_form(book: Book) -> bool:
    """Книга второй формы банка: квартальный календарь дивидендов или объект правила роста по капиталу (М§4.13, §5.7)."""
    return book.opt("capital.growth_constraint") is not None \
        or str(book.opt("dividends.calendar.frequency", "annual")) == "quarterly"


@functools.lru_cache(maxsize=None)
def first_form_book_and_facts() -> tuple[Book, Facts]:
    """Книга и факты первой формы — для проверок её узлов выпуска (годовой календарь, формула DPS до копейки, узлы
    гайденса ЧПМ / CoR / CIR, флаг срока политики): книга репозитория, если она первой формы, иначе фикстура core.
    Узлы второй формы проверяют `tests/test_core2_t_w*.py` на фикстуре `core_t`."""
    book, facts = book_and_facts()
    return (fixture_book(), fixture_facts()) if is_second_form(book) else (book, facts)


def today_of(book: Book) -> date:
    """«Сегодня» теста с живой ценой на книге: не раньше дня после даты оценки книги — цена «вчера» не старше цены,
    принятой книгой (назад цена не откатывается, М§15)."""
    return max(TODAY, date.fromisoformat(str(book.get("meta.valuation_date"))) + timedelta(days=1))


def small_book(book: Book, *, median_draws: int = 8, subsample: int = 8, **extra: Any) -> Book:
    """Книга с малым числом прогонов пересчёта медианы (для тестов поисков). Если замена оставляет часть строк
    обратного расчёта, а книга называет строки с уточнением на полной полосе, перечень сужается до
    оставшихся строк: названная строка, которой в книге нет, — отказ схемы."""
    from model.book_schema import paths_key

    ov = {"valuation.uncertainty.median_draws": median_draws, "valuation.reverse_dcf.subsample": subsample}
    ov.update(extra)
    rows, named = ov.get("valuation.reverse_dcf.axes"), book.opt("valuation.reverse_dcf.refine_rows")
    if rows is not None and named is not None and "valuation.reverse_dcf.refine_rows" not in ov:
        left = {paths_key(a["paths"]) for a in rows}
        ov["valuation.reverse_dcf.refine_rows"] = [k for k in named if k in left]
    return book.with_overrides(ov)


def point(ticker: str, price: float, day: date, source: str = "tinvest") -> PricePoint:
    return PricePoint(ticker=ticker, price=float(price), date=day.isoformat(), time="18:39", source=source,
                      fetched_at=f"{day.isoformat()}T16:00:00+00:00")


def outputs(prices: Mapping[str, Sequence[tuple[date, float]]], *, register: Sequence[Mapping] = (),
            curve: Mapping | None = None, key_rate: Mapping | None = None, degraded: Sequence[str] = (),
            peer_prices: Mapping[str, PricePoint] | None = None, alarm: Sequence[str] | None = None,
            tiles: Sequence[Mapping] = (), nowcast: Mapping | None = None,
            ras_schedule: Mapping | None = None) -> IndicatorOutputs:
    """Выходы индикаторов для прогона: цены по дням (новейшая последней), реестр, кривая; `alarm` — источники,
    получившие код 3 у сборщиков (None — отчёт прежнего формата, без списка)."""
    pts = {t: tuple(point(t, p, d) for d, p in rows) for t, rows in prices.items()}
    collector: dict[str, Any] = {"degraded": list(degraded), "sources": {}}
    if alarm is not None:
        collector["alarm"] = list(alarm)
    return IndicatorOutputs(
        as_of=f"{TODAY.isoformat()}T16:00:00+00:00", prices=pts,
        price_history={t: tuple((d.isoformat(), p) for d, p in rows) for t, rows in prices.items()},
        peer_prices=dict(peer_prices or {}), curve=curve, key_rate=key_rate, register=tuple(register),
        brokers=None, groups=(), tiles=tuple(tiles), ras_months=(), form102=(), ras_schedule=ras_schedule,
        nowcast=nowcast,
        journal={"entries": [], "total_entries": 0, "releases": {}}, admission={"status": "collecting"}, retro={},
        collector=collector, flags={"ras_mismatch": {"raised": False, "detail": ""}})


def contract(payload: Mapping[str, Any], **kw: Any) -> list[str]:
    """Контракт выпуска теста (`model.payload.validate`) с именем схемы самого выпуска: тесты собирают выпуск
    и на книге репозитория, и на фикстуре, и от того, чья книга лежит в `data/`, не зависят. Что имя схемы
    выпуска — ключ книги и что чужую схему контракт не принимает, проверяет `tests/test_core_labels.py`."""
    from model import payload as P
    return P.validate(payload, schema=str(payload.get("schema")), **kw)


def book_prices(book: Book) -> dict[str, float]:
    return {str(t): float(p) for t, p in book.get("meta.market_price").items()}


def explained(findings: Sequence[Any], *, today: date = TODAY) -> dict[str, dict]:
    """Объяснения на все сработавшие гейты с их массой (для годного выпуска в тестах)."""
    out = {}
    for f in findings:
        if f.kind == "gate" and f.fired:
            out[f.name] = {"explanation": "тест: объяснение гейта", "expected_mass": f.mass,
                           "expected_mass_range": None, "valid_until": today + timedelta(days=365)}
    return out


@functools.lru_cache(maxsize=None)
def fast_release_payload(draws: int = 12, first_form: bool = False):
    """Быстрый выпуск на книге (без индикаторов) с объяснёнными гейтами: (Release, payload). `first_form` — на книге
    первой формы (`first_form_book_and_facts`)."""
    book, facts = first_form_book_and_facts() if first_form else book_and_facts()
    return fast_release_payload_on(book, facts, draws)


def fast_release_payload_on(book: Book, facts: Facts, draws: int = 12):
    """То же на своей паре (книга, факты), без кэша: (Release, payload)."""
    from model import payload as P
    from model.checks import check_gates
    from model.grid import run_grid, live_from_book
    run = run_grid(book, facts, live_from_book(book, facts))
    expl = explained(check_gates(run, today=TODAY))
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl,
                         notes=[], draws=draws, control_model=CONTROL_FIXTURE)
    return rel, P.build_payload(rel)


def sensitivity_rows(book: Book, facts: Facts, live: Any, draws: int, workers: int | None = None):
    """Строки чувствительностей `by_lambda` выпуска на `draws` прогонах пересчёта медианы (М§8.3):
    (контекст выпуска, строки по сетке λ) — полосы книги и сдвинутых книг на одних точках гиперкуба."""
    import copy

    from model import payload as P
    from model import uncertainty as U
    from model.grid import run_grid
    small = book.with_overrides({"valuation.uncertainty.median_draws": draws})
    band = U.band(small, facts, live, draws=draws, workers=workers)
    anchor = U.MedianAnchor(small, facts, live, band, base=band)
    run = run_grid(small, facts, live)
    rel = copy.copy(fast_release_payload()[0])
    rel.book, rel.facts, rel.live, rel.run, rel.band, rel.anchor = small, facts, live, run, band, anchor
    rel.sensitivities = P.sensitivities(small, facts, live, anchor, run)
    x = P._Ctx(rel)
    return x, [P._sens_at(x, lam) for lam in P._lambda_grid(run.lam)]


def uses_fixture() -> bool:
    return not (REAL_BOOK.exists() and real_facts_ready()) or FIXTURE_BOOK is None


GROWTH_CUT = "capital.growth_constraint.enabled"


def book_with_equal_regime_nim(book: Book, facts: Facts, live: Any) -> Book:
    """Книга, у которой ожидания ЧПМ режимов в открытом квартале равны (условие проверок нейтральной ЧПМ, М§13).

    Ставки и наклоны книг от режима не зависят; режим и сценарий капитала доходят до ЧПМ квартала только через рост,
    урезанный капиталом (М§4.13): у книги Т ограничение в первых кварталах не связывало, а у книги Совкомбанка рост
    урезан уже в 2026К3, и ожидания режимов расходятся на 0,8 б.п. Тогда проверка берёт ту же книгу без ограничения
    роста — ожидания режимов на ней равны до машинной точности; книга, где они равны и так, возвращается как есть."""
    from model.nextreport import model_expectation, open_period

    def spread(b: Book) -> float:
        e = model_expectation(b, facts, open_period(b, facts), live=live)
        vals = [r["nim_q_engine"] for r in e["by_regime"]]
        return max(vals) - min(vals)

    if spread(book) < 1e-6 or not book.opt(GROWTH_CUT):
        return book
    return book.with_overrides({GROWTH_CUT: False})
