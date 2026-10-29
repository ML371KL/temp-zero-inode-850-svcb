"""Реестр сборщиков и политика тревог такта: COLLECTORS, режимы, CRITICAL, IRRECOVERABLE, `verdict`.

Сборщик — функция `collect(ctx: Context) -> Result` в своём модуле; реестр держит
её адрес строкой и разрешает лениво (модули сборщиков сами импортируют этот файл).
Режимы (`python -m indicators.collect <режим>`, DESIGN §6.1):

* `collect` (утро) — `MORNING`: формы ЦБ банка и банковской группы, T-Invest, ISS, ЦБ, новости,
  документы эмитента;
* `daily-indicators` (будни вечером) — `DAILY`: цены, ряды рынка и ставок;
* `release-watch` (дни дозора) — `RELEASE_WATCH`: новости и документы эмитента.

Политика тревог (INTERFACES §6, В9) — `verdict`:

* провал сборщика из `CRITICAL` — код 1;
* невосполнимый источник (`IRRECOVERABLE`: его день потом не добрать) отказал или деградировал —
  код 3 и признак повтора `retry` (нет токена — тревога без повтора: повтор токена не добавит);
* восполнимый источник, питающий плитки и наблюдения, деградировал — код 0, пока деградация не
  держится `DEGRADED_STREAK` такта подряд; с этого такта — код 3;
* деградация критического источника и проверка реестра дивидендов (`ALARM_AT_ONCE`) — код 3 сразу.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Collection, Mapping

from indicators.store import PROTECTED_SOURCES, Store

# Статусы источника в отчёте такта.
OK, DEGRADED, FAILED, MISSING, SKIPPED = "ok", "degraded", "failed", "missing", "skipped"


@dataclass
class Context:
    """Всё, что нужно сборщику: хранилище, «сегодня», эмитент, строки, способ ходить в сеть."""

    store: Store
    today: date
    company: dict[str, Any]
    cfg: dict[str, Any]
    getter: Callable[..., Any] | None = None
    peer_tickers: tuple[str, ...] = ()
    now: datetime | None = None
    options: dict[str, Any] = field(default_factory=dict)

    def moment(self) -> str:
        return (self.now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


@dataclass
class Result:
    """Итог сборщика: статус, причина словами, затронутые ряды, число сырых файлов."""

    name: str
    status: str = OK
    detail: str = ""
    series: list[str] = field(default_factory=list)
    raw: int = 0
    reasons: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    retry: bool = False     # среди причин есть та, которую снимет повторный сбор (сеть), а не человек

    def degrade(self, reason: str, *, retry: bool = True) -> None:
        """Деградация с причиной; `retry=False` — повтор не поможет (нечем распознать, расхождение чисел)."""
        self.reasons.append(reason)
        self.retry = self.retry or retry
        if self.status == OK:
            self.status = DEGRADED

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail,
                "series": sorted(set(self.series)), "raw": self.raw, "reasons": self.reasons}


@dataclass(frozen=True)
class Collector:
    name: str
    target: str            # «модуль:функция»
    title: str
    cadence: str
    raw_source: str        # каталог сырого архива

    def resolve(self) -> Callable[[Context], Result]:
        module, func = self.target.split(":")
        return getattr(importlib.import_module(module), func)


COLLECTORS: dict[str, Collector] = {c.name: c for c in (
    Collector("tinvest", "indicators.tinvest:collect", "T-Invest: цены, дивиденды, календарь отчётов, цели брокеров",
              "каждый такт", "tinvest"),
    Collector("iss", "indicators.iss:collect", "Мосбиржа ISS: запасные цены, история закрытий, кривая ОФЗ, индексы",
              "каждый такт", "iss"),
    Collector("cbr", "indicators.cbr:collect", "ЦБ: ключевая, RUONIA, ставки вкладов топ-10, ликвидность",
              "ежедневно", "cbr"),
    Collector("cbr_forms", "indicators.cbr_forms:collect", "ЦБ CreditOrgInfo: формы 101/102/123/135 с винтажами",
              "ежедневно утром", "cbr_forms"),
    Collector("cbr_group", "indicators.cbr_group:collect",
              "ЦБ CreditOrgInfo: формы банковской группы 0409805/803/802 с днём первого появления",
              "ежедневно утром", "cbr_group"),
    Collector("news", "indicators.news:collect", "Новостные ленты: тексты релизов и ссылки на PDF эмитента",
              "утро и дни релизов", "news"),
    Collector("issuer_docs", "indicators.issuer_docs:collect",
              "Документы эмитента: страница пресс-релизов, дверь документов, PDF с текстом",
              "утро и дни релизов", "issuer_docs"),
)}

MORNING: tuple[str, ...] = ("cbr_forms", "cbr_group", "tinvest", "iss", "cbr", "news", "issuer_docs")
DAILY: tuple[str, ...] = ("tinvest", "iss", "cbr")
RELEASE_WATCH: tuple[str, ...] = ("news", "issuer_docs")
# ISS — запасной путь цен, кривой и индексов без токена: его провал оставляет выпуск без рынка.
CRITICAL: frozenset[str] = frozenset({"iss"})
# Источники без истории у первоисточника (винтажи форм и день их появления, снимки T-Invest, новости,
# документы эмитента с моментом выхода).
IRRECOVERABLE: frozenset[str] = frozenset({"cbr_forms", "cbr_group", "tinvest", "news", "issuer_docs"})
# Восполнимый источник плиток и наблюдений: тревога — с такого по счёту такта деградации подряд (В9).
DEGRADED_STREAK = 3
# Шаги такта, не сборщики: проверка реестра дивидендов — живой вход оценки, тревога сразу;
# дозор релиза (`release_watch`) — по счётчику: поздние источники дня релиза расхождение снимают.
ALARM_AT_ONCE: frozenset[str] = frozenset({"register"})

MODES: dict[str, tuple[str, ...]] = {
    "collect": MORNING,
    "daily-indicators": DAILY,
    "release-watch": RELEASE_WATCH,
}


def run(names: tuple[str, ...], ctx: Context) -> list[Result]:
    """Запускает сборщики по порядку; исключение сборщика — его статус `failed`, не падение такта."""
    out: list[Result] = []
    for name in names:
        spec = COLLECTORS[name]
        try:
            result = spec.resolve()(ctx)
        except Exception as exc:  # noqa: BLE001 — провал источника, не прогона
            result = Result(name=name, status=FAILED, detail=f"{type(exc).__name__}: {exc}", retry=True)
        out.append(result)
    return out


@dataclass(frozen=True)
class Verdict:
    """Итог политики тревог по результатам такта."""

    code: int                         # 0 — ок; 1 — провал критического; 3 — тревога
    retry: bool                       # невосполнимый источник отказал: повтор сбора может спасти день
    streak: dict[str, int]            # источник → тактов деградации подряд (после этого такта)
    codes: dict[str, int]             # источник → его вклад в код
    lines: tuple[str, ...]            # строки журнала такта о деградации восполнимых источников


def verdict(results: list[Result], streak: Mapping[str, int] | None = None, *,
            counted: Collection[str] = ()) -> Verdict:
    """Политика тревог (шапка модуля). `streak` — счётчики до такта; `counted` — источники, чья
    деградация в этом такте уже сосчитана (повтор сбора внутри такта счётчик не двигает)."""
    held = {k: int(v) for k, v in (streak or {}).items()}
    codes: dict[str, int] = {}
    lines: list[str] = []
    retry = False
    for r in results:
        if r.status == OK:
            held.pop(r.name, None)
            codes[r.name] = 0
            continue
        n = held.get(r.name, 0) + (0 if r.name in counted and r.name in held else 1)
        held[r.name] = n
        if r.name in CRITICAL and r.status == FAILED:
            codes[r.name] = 1
        elif r.name in IRRECOVERABLE:
            codes[r.name] = 3
            retry = retry or r.status == FAILED or (r.status == DEGRADED and r.retry)
        elif r.name in CRITICAL or r.name in ALARM_AT_ONCE or n >= DEGRADED_STREAK:
            codes[r.name] = 3
            if n >= DEGRADED_STREAK and r.name not in CRITICAL and r.name not in ALARM_AT_ONCE:
                lines.append(f"{r.name}: деградация {n}-й такт подряд — тревога")
        else:
            codes[r.name] = 0
            lines.append(f"{r.name}: деградация (такт {n} из {DEGRADED_STREAK})")
    code = 1 if 1 in codes.values() else (3 if 3 in codes.values() else 0)
    return Verdict(code=code, retry=retry, streak=held, codes=codes, lines=tuple(lines))


def exit_code(results: list[Result], streak: Mapping[str, int] | None = None) -> int:
    """Код такта по политике тревог: 0 — ок; 1 — провал критического; 3 — тревога."""
    return verdict(results, streak).code


def protected_raw_sources() -> frozenset[str]:
    """Каталоги сырого архива невосполнимых сборщиков (обязаны быть защищены в store.py)."""
    return frozenset(COLLECTORS[n].raw_source for n in IRRECOVERABLE) | PROTECTED_SOURCES
