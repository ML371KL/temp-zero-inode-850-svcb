"""Помощники тестов ядра на фикстуре формы Т (`tests/fixtures/core_t`): книга, факты, проекция и «прежняя ветвь».

Фикстура — малая синтетическая книга и факты в форме Т: один тикер, 12 книг ЧПД прямыми узлами
`balance.books.<b>`, квартальный календарь дивидендов, делитель `issued`, связь с объёмом, ограничение
роста по капиталу, тест истории `cap`, премии роста по секторам, постоянные прочие активы. Из неё собираются
три книги:

* **полная** (`t_dict`) — каждая ветвь формы Т включена, ядро исполняет её целиком;
* **проекция** (`neutral_dict`) — полная книга, в которой нейтральны ветви, принятые схемой и ещё не
  исполняемые ядром (`NEUTRAL`, зеркало `PENDING` схемы). Таких ветвей сейчас нет, и проекция совпадает с
  полной книгой; новая ветвь, принятая схемой раньше кода, получает строку и в `PENDING`, и в
  `PENDING_BRANCHES` здесь;
* **прежняя ветвь** (`plain_dict`) — каждая поведенческая ветвь формы Т в нейтральном значении (`OFF`: ключ
  снят, связь равна нулю, календарь годовой): те же 12 книг и подписи на прежних формулах. Аналитический тест
  ветви включает её одну (`plain_dict(on=…)`) и сверяет разницу с закрытой формулой.
"""

from __future__ import annotations

import copy
import functools
import json
from pathlib import Path
from typing import Any

from model.book import Book, Facts, book_from_dict, load_facts
from model.grid import GridRun, LiveInputs, run_grid
from model.timeline import to_date

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_T = ROOT / "tests" / "fixtures" / "core_t"
FIXTURE_T_BOOK = FIXTURE_T / "book.json"
FIXTURE_T_FACTS = FIXTURE_T / "facts"

DROP = object()                              # ключ снимается (нет ключа — прежняя ветвь кода)
# Годовой календарь: пока квартальный не исполняется, решение о дивиденде — раз в год.
ANNUAL_CALENDAR = {"agm_quarter": 2, "reg_deduction_quarter": 3, "payment_quarter": 3, "checkpoints": [3, 4]}
# Поведенческая ветвь формы Т → её нейтральное значение (прежняя ветвь кода).
OFF: dict[str, Any] = {
    "valuation.shares_basis": DROP,
    "dividends.policy.history_test": DROP,
    "dividends.calendar": ANNUAL_CALENDAR,
    "fees.volume_link": 0.0,
    "other.insurance_volume_link": 0.0,
    "opex.volume_link": 0.0,
    "volumes.loan_share_drift": 0.0,
    "volumes.funds_share_drift": 0.0,
    "volumes.other_assets_fixed": 0.0,
    "regimes.crisis.rwa_density_mult": DROP,
    "capital.growth_constraint.enabled": False,
    "checks.growth_cut": DROP,
    "checks.step_dividend": DROP,
    "checks.cir_lt": DROP,
    "checks.wholesale_share": DROP,
    "checks.nim_lt": DROP,
    "checks.manual_overdue_days.capital_form": DROP,
    "valuation.sensitivities.buffer_pp": DROP,
}
# Ветви, которых ядро ещё не исполняет (ровно ключи `PENDING` схемы; календарь — по ключу режима). Сейчас
# таких нет: проекция совпадает с полной книгой.
PENDING_BRANCHES: tuple[str, ...] = ()
NEUTRAL: dict[str, Any] = {k: OFF[k] for k in PENDING_BRANCHES}
# Ключи неактивного режима, которые уходят вместе с квартальным календарём (значение в них — отказ схемы).
WITH_ANNUAL_CALENDAR = ("dividends.policy.base_window_quarters",)
# Узлы гайденса и банковские строки, которых ядро ещё не считает, из проекции убираются.
NEUTRAL_GUIDANCE_KEYS: tuple[str, ...] = ()
NEUTRAL_BANK_ROWS: tuple[str, ...] = ()
# Банковские строки обратного расчёта второй формы: у «прежней ветви» их нет, пока тест не включит перечень.
FORM_BANK_ROWS = ("value_without_excess_growth", "book_value_per_share", "excess_return_years")
BANK_ROWS_BRANCH = "valuation.reverse_dcf.bank_rows"
# Узлы гайденса формы Т: у «прежней ветви» их нет, пока тест не включит перечень (`checks.guidance_items`).
FORM_GUIDANCE_KEYS = ("op_np_growth", "dps_growth", "roe_target")
GUIDANCE_BRANCH = "checks.guidance_items"
# Оси полосы, чей путь исчезает вместе с нейтральным значением ветви: префикс пути оси → ветвь.
AXIS_BRANCHES = {"volumes.loan_share_drift.": "volumes.loan_share_drift",
                 "regimes.crisis.rwa_density_mult.": "regimes.crisis.rwa_density_mult"}


def t_dict() -> dict:
    """Полная книга фикстуры формы Т — словарём."""
    return json.loads(FIXTURE_T_BOOK.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def t_facts() -> Facts:
    return load_facts(FIXTURE_T_FACTS)


def _parent(data: dict, dotted: str) -> tuple[dict, str]:
    cur = data
    *head, last = dotted.split(".")
    for part in head:
        cur = cur[part]
    return cur, last


def put(data: dict, dotted: str, value: Any) -> dict:
    """Значение по точечному пути на месте; `DROP` — снять ключ."""
    parent, last = _parent(data, dotted)
    if value is DROP:
        parent.pop(last, None)
    else:
        parent[last] = copy.deepcopy(value)
    return data


def _switch_off(table: dict[str, Any], keep: tuple[str, ...], guidance: bool, bank_rows: bool = True) -> dict:
    """Полная книга, в которой ветви `table` (кроме `keep`) стоят в нейтральных значениях."""
    data = t_dict()
    off = [k for k in table if k not in keep]
    for dotted in off:
        put(data, dotted, table[dotted])
    if "dividends.calendar" in off:
        for dotted in WITH_ANNUAL_CALENDAR:
            put(data, dotted, DROP)
    checks, val = data["checks"], data["valuation"]
    drop_items = NEUTRAL_GUIDANCE_KEYS + (() if guidance else FORM_GUIDANCE_KEYS)
    checks["guidance_items"] = [it for it in checks["guidance_items"] if it["key"] not in drop_items]
    drop_rows = NEUTRAL_BANK_ROWS + (() if bank_rows else FORM_BANK_ROWS)
    val["reverse_dcf"]["bank_rows"] = [r for r in val["reverse_dcf"]["bank_rows"] if r not in drop_rows]
    gone = tuple(prefix for prefix, branch in AXIS_BRANCHES.items() if branch in off)
    val["uncertainty"]["axes"] = [a for a in val["uncertainty"]["axes"]
                                  if not any(str(p).startswith(gone) for p in a["paths"])] if gone else \
        val["uncertainty"]["axes"]
    return data


def neutral_dict(keep: tuple[str, ...] = ()) -> dict:
    """Проекция книги формы Т: ещё не исполняемые ветви — в нейтральных значениях. `keep` — пути `NEUTRAL`,
    которые оставить как в полной книге (проверка одной ветви)."""
    return _switch_off(NEUTRAL, keep, guidance=True)


def plain_dict(on: tuple[str, ...] = ()) -> dict:
    """«Прежняя ветвь»: каждая поведенческая ветвь формы Т нейтральна, кроме названных в `on` (пути `OFF`,
    `checks.guidance_items` — перечень узлов гайденса формы Т, `valuation.reverse_dcf.bank_rows` — её
    банковские строки обратного расчёта)."""
    return _switch_off(OFF, on, guidance=GUIDANCE_BRANCH in on, bank_rows=BANK_ROWS_BRANCH in on)


@functools.lru_cache(maxsize=None)
def neutral_book() -> Book:
    return book_from_dict(neutral_dict(), facts=t_facts())


@functools.lru_cache(maxsize=None)
def plain_book(on: tuple[str, ...] = ()) -> Book:
    return book_from_dict(plain_dict(on), facts=t_facts())


def book_live(book: Book) -> LiveInputs:
    """Живые входы без реестра: цена и дата книги (записи фактов несут квартал прибыли — их читает
    квартальный календарь)."""
    v = to_date(book.get("meta.valuation_date"))
    prices = {str(t): float(p) for t, p in book.get("meta.market_price").items()}
    return LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=())


@functools.lru_cache(maxsize=None)
def neutral_run() -> GridRun:
    book = neutral_book()
    return run_grid(book, t_facts(), book_live(book))


@functools.lru_cache(maxsize=None)
def plain_run(on: tuple[str, ...] = ()) -> GridRun:
    """Сетка «прежней ветви» с включёнными ветвями `on`."""
    book = plain_book(on)
    return run_grid(book, t_facts(), book_live(book))
