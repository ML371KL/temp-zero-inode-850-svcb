"""Выходы индикаторов для выпуска: `release_inputs()` → `IndicatorOutputs` (INTERFACES §5).

Только чтение `$BANK_STATE_DIR`, без сети и без записи. Нет ряда — поле `None` или
пусто, а причина словами — в `collector.degraded`; функция не бросает. Ядро
(`model/live.py`, `model/payload.py`) проверяет годность живых входов само (М§15);
здесь — только то, что было собрано, с источником и моментом. `combine` — реэкспорт из
`indicators/nowcast.py`: сборка пересчитывает `nowcast.quarter.by_target` с ожиданием своего
прогона, импортируя только этот модуль (INTERFACES §5), и передаёт подписи целей своей книги
(`combine(…, targets=…)`): базис цели — из переданной книги, не из книги репозитория.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from indicators import calendar as cal
from indicators import cbr, cbr_forms, config, periods, release_watch, retro
from indicators import register as reg
from indicators.journal import BENCHMARK_TITLES, Journal, JournalError, TARGETS, rule_text
from indicators.nowcast import combine  # noqa: F401 — реэкспорт: ядро берёт combine отсюда (INTERFACES §5)
from indicators.store import Point, Series, Store

PRICE_OBSERVATIONS = 10
HISTORY_DAYS = 366
TILE_POINTS = 60
# Единицы и базис плиток — коды П§0.2 (словарь витрины): доля, млрд ₽, цена в ₽, уровень индекса,
# число без денежной единицы (клиенты в миллионах); релиз и формы банка — `ras`, нормативы —
# `regulatory`, рынок и ставки — `market`, управленческие данные месячного релиза эмитента — `mgmt`.
TILE_UNITS = ("share", "bn", "price", "level", "number")
TILE_BASES = ("ras", "regulatory", "market", "mgmt")
MONEY_UNITS = frozenset({"bn", "price"})    # деньги печатаются до копейки и до 0,01 млрд
MONEY_DIGITS = 2
RAS_MONTHS = 15
MILLION = 10 ** 6
SHARES_TOLERANCE = 1e-6           # относительное расхождение числа акций биржи и фактов, с которого поднят флаг
SHARES_FLAG = "shares_changed"
SHARES_TITLE = "число акций на бирже отличается от фактов"
SOURCE_WORDS = {"tinvest": "T-Invest", "iss": "Мосбиржа, TQBR"}
# Сборщик и шаг такта словами — в причинах деградации, которые печатает витрина (П§0.2: без ключей).
COLLECTOR_WORDS = {"tinvest": "T-Invest", "iss": "Мосбиржа", "cbr": "Банк России", "cbr_forms": "формы ЦБ",
                   "cbr_group": "формы банковской группы", "news": "новости",
                   "issuer_docs": "документы эмитента", "release_watch": "дозор релиза",
                   "register": "реестр дивидендов"}
# Источник плитки словами — по префиксу ряда (длинные префиксы раньше); настройка
# `sources.yaml → words.series` дополняет список и идёт первой.
SERIES_WORDS = (("ras.release.", "релиз РСБУ банка"), ("cbr.f102.", "ЦБ, форма 0409102"),
                ("cbr.f135.", "ЦБ, форма 0409135"), ("cbr.f123.", "ЦБ, форма 0409123"),
                ("cbr.f101.", "ЦБ, форма 0409101"), ("cbr.", "Банк России"), ("iss.", "Мосбиржа ISS"),
                ("tinvest.", "T-Invest"))
# Слова выпуска о месячном релизе по умолчанию (настройка — `sources.yaml → words`).
MONTHLY_ROWS_WORDS, MONTHLY_SCHEDULE_WORDS = "РСБУ по месяцам", "расписание РСБУ"


def _extra_series_words() -> tuple[tuple[str, str], ...]:
    try:
        extra = config.setting("words.series") or {}
    except config.ConfigError:
        return ()
    return tuple(sorted(((str(k), str(v)) for k, v in extra.items()), key=lambda kv: -len(kv[0])))


def series_words(sid: str) -> str:
    for prefix, words in _extra_series_words() + SERIES_WORDS:
        if sid.startswith(prefix):
            return words
    return sid


@dataclass(frozen=True)
class PricePoint:
    ticker: str
    price: float
    date: str
    time: str | None
    source: str
    fetched_at: str


@dataclass(frozen=True)
class IndicatorOutputs:
    as_of: str
    prices: Mapping[str, tuple[PricePoint, ...]]
    price_history: Mapping[str, tuple[tuple[str, float], ...]]
    peer_prices: Mapping[str, PricePoint]
    curve: Mapping[str, Any] | None
    key_rate: Mapping[str, Any] | None
    register: tuple[Mapping[str, Any], ...]
    brokers: Mapping[str, Any] | None
    groups: tuple[Mapping[str, Any], ...]
    tiles: tuple[Mapping[str, Any], ...]
    ras_months: tuple[Mapping[str, Any], ...]
    form102: tuple[Mapping[str, Any], ...]
    ras_schedule: Mapping[str, Any] | None
    nowcast: Mapping[str, Any] | None
    journal: Mapping[str, Any]
    admission: Mapping[str, Any]
    retro: Mapping[str, Any]
    collector: Mapping[str, Any]
    flags: Mapping[str, Mapping[str, Any]]
    # Строки месячной таблицы «операционные результаты и формы ЦБ» (П§2 `nowcast.ops.rows`): по их
    # месяцам считаются `form102` и флаг `ras_mismatch`, когда у эмитента свой месячный релиз.
    ops_months: tuple[Mapping[str, Any], ...] = ()


@dataclass
class _Reader:
    store: Store
    today: date
    degraded: list[str] = field(default_factory=list)

    def series(self, sid: str) -> Series | None:
        try:
            return self.store.load(sid)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.degraded.append(f"ряд «{series_words(sid)}» не прочитан: {type(exc).__name__}")
            return None

    def safe(self, what: str, fn, default):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — выход выпуска не бросает
            self.degraded.append(f"{what}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
            return default


# ------------------------------------------------------------------ цены

def _upto(items: dict, today: date) -> dict:
    """Точки с датой периода не позже «сегодня» (месяцы и кварталы — как есть).

    Выход выпуска читает нынешнее состояние (последний винтаж каждой точки): «что было
    известно на дату» нужно истории и ретро, а не живым входам.
    """
    day = today.isoformat()
    return {k: v for k, v in items.items() if not (len(k) == 10 and k[4] == "-") or k <= day}


def _points_by_day(s: Series | None, today: date) -> dict[str, Point]:
    return {} if s is None else {d: p for d, p in _upto(s.points_as_of(None), today).items() if p.value is not None}


def price_points(r: _Reader, ticker: str) -> tuple[PricePoint, ...]:
    """Наблюдения цены за последние торговые дни: T-Invest, иначе ISS; новейшее последним."""
    by_source = {src: _points_by_day(r.series(f"{src}.price.{ticker}"), r.today) for src in ("tinvest", "iss")}
    days = sorted({d for pts in by_source.values() for d in pts})[-PRICE_OBSERVATIONS:]
    out = []
    for d in days:
        for src in ("tinvest", "iss"):
            p = by_source[src].get(d)
            if p is not None:
                out.append(PricePoint(ticker=ticker, price=p.value, date=d, time=p.note or None,
                                      source=src, fetched_at=p.fetched_at))
                break
    return tuple(out)


def price_history(r: _Reader, ticker: str) -> tuple[tuple[str, float], ...]:
    s = r.series(f"iss.close.{ticker}")
    if s is None:
        return ()
    start = (r.today - timedelta(days=HISTORY_DAYS)).isoformat()
    return tuple((d, v) for d, v in _upto(s.history(), r.today).items() if start <= d)


def curve(r: _Reader) -> dict[str, Any] | None:
    nodes, dates = {}, set()
    for node in ("1", "3", "5", "10"):
        s = r.series(f"iss.zcyc.{node}")
        p = None if s is None else s.latest()
        if p is None:
            r.degraded.append(f"кривая ОФЗ: нет узла {node} лет")
            return None
        nodes[node] = p.value
        dates.add(p.period)
    if len(dates) != 1:
        r.degraded.append("кривая ОФЗ: узлы на разные даты")
        return None
    return {"as_of": dates.pop(), "nodes": nodes, "source": "Мосбиржа ISS, zcyc"}


def key_rate(r: _Reader) -> dict[str, Any] | None:
    s = r.series("cbr.key_rate")
    if s is None:
        r.degraded.append("ключевая ставка: ряда нет")
        return None
    return cbr.key_rate_summary(_upto(s.history(), r.today))


def register(r: _Reader, main: str, cfg: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Реестр за год с небольшим: документы эмитента, брокерский календарь, новость о решении, ручная
    запись (`indicators/register.py`); ключ записи — по настройке `dividends.period_rule`."""
    start = (r.today - timedelta(days=HISTORY_DAYS + 35)).isoformat()
    rows = reg.build(r.store, ticker=main, today=r.today, cfg=cfg, since=start, splits=config.splits())
    return tuple({**{k: row.get(k) for k in reg.KEEP}, "notes": row.get("notes") or []} for row in rows)


def register_flag(r: _Reader, rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Флаг `dividend_register`: срок решения о дивиденде прошёл, годной записи за период нет (М§14.3)."""
    text = reg.alarm_from_book(list(rows), r.today)
    return {"raised": text is not None, "detail": text or ""}


def brokers(r: _Reader, main: str) -> dict[str, Any] | None:
    agg = r.store.read_state(f"tinvest/brokers_{main}.json")
    if not agg:
        return None
    med, n = r.series(f"tinvest.brokers.median.{main}"), r.series(f"tinvest.brokers.n.{main}")
    hist = []
    if med is not None:
        nn = {} if n is None else n.history()
        for d, v in list(med.history().items())[-TILE_POINTS:]:
            hist.append({"date": d, "median": v, "n": int(nn[d]) if d in nn else None})
    keep = ("as_of", "source", "n", "median", "min", "max", "recommendations")
    return {**{k: agg.get(k) for k in keep}, "history": hist}


# ------------------------------------------------------------------ плитки

def _thin(items: list[tuple[str, float]], limit: int) -> list[tuple[str, float]]:
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1)
    idx = sorted({round(i * step) for i in range(limit)})
    return [items[i] for i in idx]


def tile(r: _Reader, spec: Mapping[str, Any], company: Mapping[str, Any]) -> dict[str, Any]:
    fill = {"main_ticker": company.get("main_ticker")}
    ids = [str(s).format(**fill, ticker=spec.get("_ticker", "")) for s in spec.get("series") or []]
    hist_ids = [str(s).format(**fill, ticker=spec.get("_ticker", "")) for s in spec.get("history") or []]
    out: dict[str, Any] = {"id": spec["id"], "group": spec["group"], "title": spec["title"], "unit": spec["unit"],
                           "basis": spec.get("basis"), "value": None, "date": None, "change": None,
                           "change_from": None, "min": None, "max": None, "history": {"date": [], "value": []},
                           "source": None, "status": "missing"}
    if spec.get("note"):
        out["note"] = spec["note"]
    main = None
    for sid in ids:
        s = r.series(sid)
        if s is not None and _upto(s.history(), r.today):
            main = s
            out["source"] = series_words(sid)
            out["series"] = sid
            break
    if main is None:
        out["reason"] = "данных ещё нет" + (f": {series_words(ids[0])}" if ids else "")
        return out
    full = _upto(main.history(), r.today)
    for sid in hist_ids:
        h = r.series(sid)
        if h is not None:
            for d, v in _upto(h.history(), r.today).items():
                full.setdefault(d, v)
    money = spec["unit"] in MONEY_UNITS
    items = sorted((d, round(v, MONEY_DIGITS) if money else v) for d, v in full.items())
    last_d, last_v = items[-1]
    out.update(value=last_v, date=last_d)
    if spec.get("change") == "previous_distinct":
        prev = [x for x in items if x[1] != last_v]
        if prev:
            out.update(change=_diff(last_v, prev[-1][1], money), change_from=prev[-1][0])
    elif len(items) >= 2:
        out.update(change=_diff(last_v, items[-2][1], money), change_from=items[-2][0])
    if spec.get("since"):
        s = cbr.key_rate_summary(dict(items))
        out["since"] = None if s is None else s["since"]
    # Окно плитки — год до последней точки, по календарному дню периода (месяц — его конец):
    # и история, и минимум с максимумом — за него (П§2 `indicators.tiles`).
    end = _period_day(last_d)
    start = None if end is None else end - timedelta(days=HISTORY_DAYS)
    year = [x for x in items if start is None or (_period_day(x[0]) or end) >= start]
    lo, hi = min(year, key=lambda x: x[1]), max(year, key=lambda x: x[1])
    out["min"], out["max"] = {"date": lo[0], "value": lo[1]}, {"date": hi[0], "value": hi[1]}
    thin = _thin(year, TILE_POINTS)
    out["history"] = {"date": [d for d, _ in thin], "value": [v for _, v in thin]}
    age = _age_days(last_d, r.today)
    if age is not None and age > int(spec.get("stale_days", 7)):
        out["status"], out["reason"] = "stale", f"последнее значение — {last_d}"
    else:
        out["status"] = "ok"
    return out


def _period_day(period: str) -> date | None:
    """Календарный день периода точки: день — он сам, месяц и квартал — их последний день."""
    try:
        if periods.is_month(period):
            return periods.month_end(period)
        if periods.is_quarter(period):
            return periods.quarter_end(period)
        return date.fromisoformat(period[:10])
    except ValueError:
        return None


def _age_days(period: str, today: date) -> int | None:
    day = _period_day(period)
    return None if day is None else (today - day).days


def _diff(a: float, b: float, money: bool) -> float:
    return round(a - b, MONEY_DIGITS) if money else a - b


def tile_registry_errors(spec: Mapping[str, Any]) -> list[str]:
    """Ошибки реестра плиток `sources.yaml → tiles`: единица и базис — только коды П§0.2, группа — из списка."""
    groups = {g.get("id") for g in spec.get("groups") or []}
    out = []
    for item in spec.get("items") or []:
        if item.get("unit") not in TILE_UNITS:
            out.append(f"{item.get('id')}: единица {item.get('unit')!r} — не из {', '.join(TILE_UNITS)}")
        if item.get("basis") not in TILE_BASES:
            out.append(f"{item.get('id')}: базис {item.get('basis')!r} — не из {', '.join(TILE_BASES)}")
        if item.get("group") not in groups:
            out.append(f"{item.get('id')}: группы {item.get('group')!r} нет в списке групп")
    return out


def tiles(r: _Reader, cfg: Mapping[str, Any], company: Mapping[str, Any]) -> tuple[list, list]:
    spec = cfg.get("tiles") or {}
    errors = tile_registry_errors(spec)
    if errors:
        raise config.ConfigError("реестр плиток: " + "; ".join(errors))
    groups = [{"id": g["id"], "title": g["title"]} for g in spec.get("groups") or []]
    out = []
    for item in spec.get("items") or []:
        if item.get("per_ticker"):
            for t in company.get("tickers") or []:
                s = dict(item, _ticker=t)
                s["id"], s["title"] = item["id"].format(ticker=t), item["title"].format(ticker=t)
                out.append(tile(r, s, company))
        else:
            out.append(tile(r, item, company))
    return groups, out


# ------------------------------------------------------------------ РСБУ по месяцам

RAS_ROW = (("ni", "np_m"), ("ni_ytd", "np_ytd"), ("nii", "nii_m"), ("fees", "fee_m"), ("llp", "prov_m"),
           ("opex", "opex_m"), ("cor", "cor_m"), ("roe", "roe_m"), ("loans_corporate", "loans_ul"),
           ("loans_retail", "loans_fl"), ("funds_retail", "funds_fl"), ("funds_corporate", "funds_ul"),
           ("n1_0", "n1_0"), ("n1_1", "n1_1"))


def ras_months(r: _Reader, prefix: str = release_watch.DEFAULT_PREFIX) -> list[dict[str, Any]]:
    """Строки релиза РСБУ банка по месяцам (П§2 `nowcast.months.rows`); у эмитента со своим месячным
    релизом (другое начало имён рядов) таблицу несёт `ops_months`, а эта пуста."""
    if prefix != release_watch.DEFAULT_PREFIX:
        return []
    ytd = r.series("ras.release.np_ytd")
    if ytd is None:
        return []
    as_of = None                      # нынешнее состояние: последний винтаж каждой точки
    months = sorted(ytd.history(as_of))[-RAS_MONTHS:]
    cache = {metric: r.series(f"ras.release.{metric}") for _, metric in RAS_ROW}
    rows = []
    for m in months:
        row: dict[str, Any] = {"month": m}
        for key, metric in RAS_ROW:
            s = cache[metric]
            row[key] = None if s is None else s.value_as_of(m, as_of)
        p = ytd.point_as_of(m, as_of)
        row["source"] = "seed" if str(p.source).startswith("seed") else (p.source or None)
        row["published_at"] = ytd.first_seen(m)
        rows.append(row)
    return rows


def shares_flag(r: _Reader, main: str | None) -> dict[str, Any] | None:
    """Флаг `shares_changed`: число акций на бирже (ряд `iss.issue_size.<тикер>`, шт.) против размещённых
    акций фактов (`shares.json → issued_<класс>`, млн шт.). Ряда нет (настройка `iss.issue_size` выключена)
    — флага нет вовсе; нет числа в фактах — флаг опущен, причина — в `detail`. Покупки акций дочерней компанией
    числа размещённых акций не меняют: флаг ловит выпуск и погашение (перенос из соседней панели семейства)."""
    series = r.series(f"iss.issue_size.{main}") if main else None
    point = None if series is None else series.latest()
    if point is None or point.value is None:
        return None
    facts = config.facts_file("shares") or {}
    kind = ((facts.get("by_ticker") or {}).get(main) or {}).get("class") or "ordinary"
    held = config.node_value(facts.get(f"issued_{kind}"))
    if held is None:
        held = config.node_value(facts.get("issued_total"))
    listed = point.value / MILLION
    out = {"raised": False, "title": SHARES_TITLE, "detail": "", "exchange_mln": round(listed, 6),
           "facts_mln": held, "date": point.period}
    if not isinstance(held, (int, float)) or isinstance(held, bool) or held <= 0:
        out["detail"] = "в фактах нет числа размещённых акций — сверять не с чем"
        return out
    if abs(listed - held) > SHARES_TOLERANCE * held:
        words = lambda v: f"{v:,.1f}".replace(",", " ").replace(".", ",")  # noqa: E731 — «22 516,2»
        out["raised"] = True
        out["detail"] = f"на бирже {words(listed)} млн акций на {point.period}, в фактах {words(held)} млн"
    return out


# Поле строки месячной таблицы → метрика ряда месячного релиза (П§2 `nowcast.ops.rows`).
OPS_ROW = (("clients_total", "clients_total"), ("clients_active", "clients_active"),
           ("loans_gross", "loans_gross"), ("loans_retail", "loans_retail"), ("loans_business", "loans_business"),
           ("funds_total", "funds_total"), ("funds_retail", "funds_retail"), ("funds_business", "funds_business"),
           ("ras_ni_ytd", "np_ytd"), ("n1_0", "n1_0"), ("n1_1", "n1_1"), ("n1_2", "n1_2"),
           ("capital_total", "cap_total"))
OPS_AFTER_PROFIT = "ras_ni_ytd"       # за этим полем в строке идут расчётная прибыль месяца и форма 0409102


def ops_months(r: _Reader, spec: release_watch.Monthly) -> list[dict[str, Any]]:
    """Месячная таблица «операционные результаты и формы ЦБ»: последние месяцы главного ряда релиза.

    Поля — ряды месячного релиза (`OPS_ROW`), `ras_ni_m` — разность нарастающей прибыли соседних
    месяцев (январь — само значение; нет соседнего — `null`), `f102_ni_ytd` — форма 0409102. Нет точки
    ряда за месяц — `null`. У эмитента без своего месячного релиза — пусто."""
    if spec.prefix == release_watch.DEFAULT_PREFIX:
        return []
    main = r.series(spec.series(spec.main))
    if main is None:
        return []
    months = sorted(main.history())[-RAS_MONTHS:]
    cache = {metric: r.series(spec.series(metric)) for _, metric in OPS_ROW}
    f102 = r.series("cbr.f102.ni_ytd")
    profit = cache["np_ytd"]
    by_month = {} if profit is None else cbr_forms.month_from_ytd(profit.history())
    rows = []
    for m in months:
        row: dict[str, Any] = {"month": m, "published_at": main.first_seen(m)}
        for key, metric in OPS_ROW:
            s = cache[metric]
            row[key] = None if s is None else s.value_as_of(m)
            if key == OPS_AFTER_PROFIT:
                month_profit = by_month.get(m)       # разность нарастающих: хвост двоичной дроби в выпуск не идёт
                row["ras_ni_m"] = None if month_profit is None else round(month_profit, 6)
                row["f102_ni_ytd"] = None if f102 is None else f102.value_as_of(m)
        p = main.point_as_of(m)
        row["source"] = "seed" if str(p.source).startswith("seed") else (p.source or None)
        rows.append(row)
    return rows


# ------------------------------------------------------------------ журнал и допуск

def journal_block(r: _Reader, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        j = Journal(path, readonly=True)
    except JournalError:
        empty = {"entries": [], "total_entries": 0, "rule": rule_text(), "releases": {}}
        return empty, {"rule": rule_text(), "status": "collecting", "events_needed": 4, "events_scored": 0,
                       "mse_ratio": {"nim_q": None, "cor_q": None}}
    entries = j.entries()
    releases = r.store.read_state("journal_releases.json") or {}
    shas = {e["release_sha"] for e in entries}
    block = {"entries": entries, "total_entries": len(j.forecasts()), "rule": rule_text(),
             "releases": {k: v for k, v in releases.items() if k in shas}}
    return block, j.admission_summary()


def with_journal_titles(retro_block: Mapping[str, Any], jblock: Mapping[str, Any]) -> dict[str, Any]:
    """Ретро-проверка с названиями эталонов записей журнала: словарь `titles` один на оба блока, и витрина
    печатает название эталона, а не его ключ, — и у эталона, которого в ретро-проверке нет."""
    titles = dict(retro_block.get("titles") or {})
    for entry in jblock.get("entries") or ():
        for key in entry.get("benchmarks") or ():
            titles.setdefault(key, BENCHMARK_TITLES.get(key, key))
    return {**retro_block, "titles": titles} if titles else dict(retro_block)


def admission_dates(adm: dict[str, Any], r: _Reader, cfg: Mapping[str, Any], facts_events: list[dict],
                    journal_path: Path) -> dict[str, Any]:
    """Первое зачётное событие (квартал с записью T-90 или ближайший, где T-90 впереди) и самое раннее решение."""
    sched = cfg.get("schedule") or {}
    first = None
    try:
        j = Journal(journal_path, readonly=True)
        t90 = sorted(f["period"] for f in j.forecasts() if f["horizon"] == "T-90" and f["target"] in ("nim_q", "cor_q"))
        first = t90[0] if t90 else None
    except JournalError:
        pass
    if first is None:
        q = periods.quarter_of(r.today)
        for _ in range(8):
            rep = cal.ifrs_report(q, store=r.store, schedule=sched, facts_events=facts_events)
            if (date.fromisoformat(rep["date"]) - r.today).days > 30:
                first = q
                break
            q = periods.shift_quarter(q, 1)
    out = dict(adm)
    out["first_event"] = first
    if first:
        last = periods.shift_quarter(first, adm.get("events_needed", 4) - 1)
        out["earliest_decision"] = cal.ifrs_report(last, store=r.store, schedule=sched,
                                                   facts_events=facts_events)["date"]
    else:
        out["earliest_decision"] = None
    return out


# ------------------------------------------------------------------ сборка

def degraded_words(reasons: Sequence[Any]) -> list[str]:
    """Причины отчёта такта («<сборщик>: <причина>») с именем сборщика словами — такими их печатает выпуск."""
    out = []
    for reason in reasons:
        name, sep, rest = str(reason).partition(": ")
        out.append(f"{COLLECTOR_WORDS[name]}: {rest}" if sep and name in COLLECTOR_WORDS else str(reason))
    return out


def collector_alarm(report: Mapping[str, Any]) -> list[str]:
    """Источники последнего такта сборщиков, уже получившие код 3 по политике тревог (INTERFACES §6):
    невосполнимый или критический источник, тревога реестра, восполнимый — с третьего такта подряд.
    Деградация восполнимого источника плиток моложе трёх тактов сюда не входит: её причина остаётся
    в `degraded`, тревогой сборки она не становится."""
    return sorted(str(d.get("name")) for d in report.get("details") or [] if d.get("code") == 3)


def release_inputs(*, tickers: Sequence[str], peer_tickers: Sequence[str] = (), state_dir: Path | None = None,
                   today: date | None = None) -> IndicatorOutputs:
    """Выходы индикаторов для выпуска: только чтение состояния; не бросает."""
    today = today or date.today()
    store = Store(Path(state_dir) if state_dir is not None else None)
    r = _Reader(store=store, today=today)
    cfg = r.safe("sources.yaml", config.sources, {})
    company = r.safe("meta.company книги", config.company, {})
    tickers = list(tickers) or list(company.get("tickers") or [])
    main = tickers[0] if tickers else company.get("main_ticker")
    company = dict(company, tickers=tickers, main_ticker=main)
    facts_events = r.safe("facts/calendar.json", config.calendar_events, [])
    prices = {t: r.safe(f"цены {t}", lambda t=t: price_points(r, t), ()) for t in tickers}
    for t, pts in prices.items():
        if not pts:
            r.degraded.append(f"цена {t}: наблюдений нет")
    peers = {}
    for t in peer_tickers:
        pts = r.safe(f"цена аналога {t}", lambda t=t: price_points(r, t), ())
        if pts:
            peers[t] = pts[-1]
        else:
            r.degraded.append(f"цена аналога {t}: наблюдений нет")
    groups, tile_rows = r.safe("плитки", lambda: tiles(r, cfg, company), ([], []))
    words = cfg.get("words") or {}
    spec = release_watch.monthly(cfg)
    rows_words = str(words.get("monthly_rows") or MONTHLY_ROWS_WORDS)
    months = r.safe(rows_words, lambda: ras_months(r, spec.prefix), [])
    ops = r.safe(rows_words, lambda: ops_months(r, spec), [])
    month_ids = [row["month"] for row in (ops or months)]
    tol = float((cfg.get("release_watch") or {}).get("form102_tolerance", 0.15))
    f102 = r.safe("форма 0409102", lambda: release_watch.form102_rows(store, month_ids, tolerance_bn=tol,
                                                                     prefix=spec.prefix), [])
    schedule = r.safe(str(words.get("monthly_schedule") or MONTHLY_SCHEDULE_WORDS),
                      lambda: cal.next_ras(today, store=store, schedule=cfg.get("schedule") or {},
                                           facts_events=facts_events), None)
    journal_path = store.root / "journal.sqlite"
    jblock, adm = r.safe("журнал", lambda: journal_block(r, journal_path),
                         ({"entries": [], "total_entries": 0, "rule": rule_text(), "releases": {}}, {}))
    adm = r.safe("допуск", lambda: admission_dates(adm, r, cfg, facts_events, journal_path), adm)
    retro_block = with_journal_titles(r.safe("ретро", lambda: retro.retro(store, today=today), {}), jblock)
    report = store.read_state("collector_report.json") or {}
    degraded = degraded_words(report.get("degraded") or []) + r.degraded
    flag = r.safe("флаг ras_mismatch", lambda: release_watch.mismatch_flag(store, month_ids[-3:], tolerance_bn=tol,
                                                                           prefix=spec.prefix),
                  {"raised": False, "detail": ""})
    reg_rows = r.safe("реестр", lambda: register(r, main, cfg), ())
    reg_flag = r.safe("флаг dividend_register", lambda: register_flag(r, reg_rows), {"raised": False, "detail": ""})
    flags = {"ras_mismatch": flag, "dividend_register": reg_flag}
    shares = r.safe(f"флаг {SHARES_FLAG}", lambda: shares_flag(r, main), None)
    if shares is not None:
        flags[SHARES_FLAG] = shares         # флаг выходов, не тревога такта: делитель правит новая версия фактов
    return IndicatorOutputs(
        as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        prices=prices,
        price_history={t: r.safe(f"история {t}", lambda t=t: price_history(r, t), ()) for t in tickers},
        peer_prices=peers,
        curve=r.safe("кривая", lambda: curve(r), None),
        key_rate=r.safe("ключевая", lambda: key_rate(r), None),
        register=reg_rows,
        brokers=r.safe("цели брокеров", lambda: brokers(r, main), None),
        groups=tuple(groups), tiles=tuple(tile_rows),
        ras_months=tuple(months), form102=tuple(f102), ras_schedule=schedule,
        nowcast=store.read_state("nowcast.json"),
        journal=jblock, admission=adm, retro=retro_block,
        collector={"degraded": degraded, "sources": dict(report.get("sources") or {}),
                   "streak": dict(report.get("streak") or {}), "retry": bool(report.get("retry")),
                   "alarm": collector_alarm(report), "generated_at": report.get("generated_at")},
        flags=flags,
        ops_months=tuple(ops),
    )


__all__ = ["PricePoint", "IndicatorOutputs", "release_inputs", "combine", "TARGETS"]
