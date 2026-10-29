"""Ручной ввод — запасной путь автомата: record-ras, record-actual, record-consensus, record-guidance.

`record-ras` вносит числа месячного релиза эмитента: допустимые метрики и начало имён рядов — настройка
(`sources.yaml → monthly`); у доли-норматива значение — доля или проценты со знаком.

Каждое число вносится с источником (документ, страница или адрес) и ложится в ряды
со статусом `manual`; момент ввода — момент известности. Доли вводятся либо долей
(`0.229`), либо процентами со знаком (`22.9%`); доля больше 0,5 без знака «%» —
отказ (почти наверняка проценты). Факт журнала неснимаем (`journal.record_actual`).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from indicators import config, journal as journal_mod, periods
from indicators.journal import TARGETS, Journal
from indicators.release_watch import METRICS, SHARE_METRICS, STATE_DIR
from indicators.store import Point, Store

# Пункты гайденса — ключи фактов `guidance.json → items` (один словарь на факты и ручной ввод);
# `cor` — точка, если эмитент её назовёт, `payout` — доля выплаты. Перечень дополняют пункты книги
# `checks.guidance_items` (`guidance_items()`): у каждого эмитента гайденс свой.
GUIDANCE_ITEMS = ("roe", "nim", "cor", "cor_max", "cir", "fee_growth", "n20_0", "loan_growth.corporate",
                  "loan_growth.retail", "payout")
MAX_SHARE = 0.5
GUIDANCE_PATH = "items."


def guidance_items() -> tuple[str, ...]:
    """Допустимые пункты гайденса: общий перечень и пункты `checks.guidance_items` книги — узел фактов
    из поля `path` («items.<пункт>»), а без него — поле `key`."""
    extra = []
    for item in config.book_value("checks.guidance_items") or []:
        key = item.get("key") if isinstance(item, dict) else item
        path = str(item.get("path") or "") if isinstance(item, dict) else ""
        if path.startswith(GUIDANCE_PATH):
            key = path[len(GUIDANCE_PATH):]
        if isinstance(key, str) and key and key not in GUIDANCE_ITEMS and key not in extra:
            extra.append(key)
    return GUIDANCE_ITEMS + tuple(extra)


class RecordError(ValueError):
    """Ввод не принят."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_value(text: str, *, share: bool) -> float:
    """«1234,5» → 1234.5; «12,3%» → 0.123; доля без «%» больше 0,5 — отказ."""
    t = str(text).strip().replace(" ", "").replace(",", ".")
    pct = t.endswith("%")
    try:
        v = float(t.rstrip("%"))
    except ValueError as exc:
        raise RecordError(f"не число: {text!r}") from exc
    if pct:
        if not share:
            raise RecordError(f"«%» у денежной величины: {text!r}")
        return round(v / 100.0, 10)
    if share and abs(v) > MAX_SHARE:
        raise RecordError(f"{text!r}: доля больше {MAX_SHARE} — укажите проценты со знаком «%»")
    return v


def parse_pairs(items: Iterable[str], *, metrics: Iterable[str] | None = None) -> dict[str, float]:
    """[«np_ytd=1234,5», «n1_0=12,3%»] → {метрика: значение} с проверкой имён. `metrics` — допустимые
    метрики месячного релиза (`sources.yaml → monthly.metrics`); нет — перечень релиза РСБУ."""
    allowed = tuple(metrics) if metrics is not None else METRICS
    out = {}
    for item in items:
        if "=" not in item:
            raise RecordError(f"ожидалось метрика=значение: {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if key not in allowed:
            raise RecordError(f"неизвестная метрика релиза {key!r}; допустимы: {', '.join(allowed)}")
        out[key] = parse_value(raw, share=key in SHARE_METRICS)
    return out


def record_ras(store: Store, month: str, values: dict[str, float], source: str) -> dict[str, Any]:
    """Числа месячного релиза за месяц руками: в очередь дозора (вид `manual`, принимается сам)."""
    periods.parse_month(month)
    if not source:
        raise RecordError("нужен источник (документ, страница или адрес)")
    name = f"{STATE_DIR}/manual_{month}.json"
    held = store.read_state(name) or {}
    now = _now()
    for k, v in values.items():
        held[k] = {"value": v, "source": source, "at": now}
    store.write_state(name, held)
    return held


def record_actual(journal: Journal, store: Store, *, target: str, period: str, value: str | float,
                  source: str, reported_on: date | None = None) -> float:
    """Факт квартала: в журнал (неснимаем) и в ряд `actual.<цель>` (момент — день публикации)."""
    if target not in TARGETS:
        raise RecordError(f"неизвестная цель {target!r}; допустимы: {', '.join(TARGETS)}")
    periods.parse_quarter(period)
    meta = journal_mod.targets()[target]
    v = parse_value(str(value), share=meta["unit"] == "share")
    journal.record_actual(target=target, period=period, value=v, source=source, reported_on=reported_on)
    at = (reported_on.isoformat() + "T07:00:00+00:00") if reported_on else _now()
    store.upsert(f"actual.{target}", [Point(period, v, at, "manual", source)], basis=meta["basis"],
                 unit=meta["unit"], label=meta["title"])
    return v


def record_consensus(store: Store, *, period: str, value: str | float, source: str) -> float:
    """Консенсус прибыли квартала (цель `ni_q`) перед отчётом (эталон `consensus`)."""
    periods.parse_quarter(period)
    if not source:
        raise RecordError("нужен источник консенсуса")
    v = parse_value(str(value), share=False)
    store.upsert("consensus.ni_q", [Point(period, v, _now(), "manual", source)],
                 basis=journal_mod.targets()["ni_q"]["basis"], unit="RUB bn", label="консенсус прибыли квартала")
    return v


def record_guidance(store: Store, *, year: int, item: str, value: str | float, source: str) -> float:
    """Гайденс года (упр. базис) числом: пункты `GUIDANCE_ITEMS` и пункты книги `checks.guidance_items`.

    Эталоном журнала служат `nim` и `cor` (точки) и пункт роста прибыли года (`collect.GROWTH_GUIDANCE`);
    запись важнее фактов `guidance.json` и нужна, когда факты года ещё не обновлены, — до первой
    записи T-90 квартала. Все пункты — доли (проценты вводятся со знаком «%»)."""
    allowed = guidance_items()
    if item not in allowed:
        raise RecordError(f"неизвестный пункт гайденса {item!r}; допустимы: {', '.join(allowed)}")
    if not source:
        raise RecordError("нужен источник гайденса")
    v = parse_value(str(value), share=True)
    store.upsert(f"guidance.{item}", [Point(str(int(year)), v, _now(), "manual", source)], basis="mgmt",
                 unit="share", label=f"гайденс: {item}")
    return v
