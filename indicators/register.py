"""Реестр объявленных дивидендов для выпуска: источники, ключ записи и тревога (М§15, §14.3).

**Ключ записи** — настройка `sources.yaml → dividends.period_rule`: `quarterly` — квартал прибыли
(`period`, «2026Q2»; год записи — год периода), иначе год прибыли (`year`).

Источники записи (главный тикер книги):

1. **Документ эмитента** (`issuer_docs`: рекомендация совета в пресс-релизе МСФО, «Рекомендации
   совета директоров…» и протокол собрания) — запись `manual/dividends.json` с пометкой
   `origin: issuer_docs`: период, слова решения, DPS, дата реестра, срок выплаты, день решения.
   При квартальном ключе это первый источник: его DPS и даты — опорные.
2. **Брокерский календарь** (`tinvest/dividends.json`): DPS, дата реестра, последний день покупки,
   выплата. Периода брокер не называет. При квартальном ключе период присваивает `build`:
   (1) по записи документа, оператора или новости с той же датой реестра; (2) запасное правило —
   квартал даты реестра минус `dividends.record_lag_quarters`, только когда в этом квартале у
   брокера одна запись без пары и вычисленный период никем не занят; (3) иначе запись в реестр не
   входит, строка о ней ложится в заметки записей того же квартала и в тревогу сборщика. Размер
   на акцию брокер отдаёт в нынешних акциях на всю историю — после дробления пересчитывает сам,
   и сборщик его не делит (`tinvest.dividends_split_adjusted`; `false` — делить запись с датой
   реестра раньше первого торгового дня после дробления на коэффициент из фактов).
3. **Новость о решении собрания или рекомендации совета** (`news/items.json`, тема `dividend`,
   виды `dividends.news_kinds`) — `news.extract_dividend_decision`. Засчитывается одна новость. Вид, чьё
   слово в `news_kinds` — «документ эмитента» (пост канала эмитента, когда сайт и страница раскрытия для
   скрипта закрыты), — источник первого рода: его решение идёт как документ эмитента, а не как новость.
4. **Ручная запись оператора** (`record-dividend`) со ссылкой на документ — запасной источник.

Источник засчитывается, если его DPS совпадает с опорным до `dividends.dps_tolerance` и даты
реестра не противоречат; несовпадения — в `notes`. Статус (М§15.1):

* `declared` — есть решение собрания (документ, новость или ручная запись) или только брокер;
* «брокер + только рекомендация совета» — `recommended` до дня реестра и `declared` с него;
  рекомендация вторым источником решения не считается;
* `recommended` — только рекомендация совета;
* `paid` — запись брокера или объявленная запись, и срок выплаты наступил.

Дата решения (`decided_date`) — только из решений собрания; день рекомендации —
`recommended_date`. Годность (два источника у `declared`, 0 < DPS < 0,5 цены, реестр через
10–20 дней после решения) проверяет ядро (`model/live.py`).

**Тревога** (`alarm`). Квартальный календарь книги (`dividends.calendar.frequency: quarterly`):
открытый квартал прибыли — позже последнего закрытого по фактам (`closed_through`), — у которого
квартал решения по карте лагов кончился, а годной записи (`paid` или `declared` с двумя
источниками) нет. Эмитент, решающий раз в год за весь год прибыли (`dividends.annual_decision`), —
запись года несёт период четвёртого квартала, и тревога смотрит только четвёртые кварталы: первые три
квартала прибыли отдельного решения не имеют. Годовой календарь: прошёл конец квартала собрания (`agm_quarter`), годной
записи за прошлый год нет. Текст — шаблон книги `meta.labels.register.collector_alarm`.

**Стартовый реестр фактов закрывает период.** Запись `paid` в `facts/dividends.json →
register_seed` — выплаченный дивиденд, подтверждённый первичкой при сборке фактов; ядро
начинает реестр выпуска с этих записей (`model/live.py`). Период (год — при годовом календаре)
с такой записью для тревоги закрыт, даже если у сборщиков записи за него нет: документ о
решении старше окна первого запуска сборщик не скачает, а брокерский календарь без токена
пуст. Запись `declared` стартового реестра период не закрывает — выплату и второй источник
подтверждают сборщики.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from indicators import config, news, periods
from indicators.tinvest import DIVIDENDS_FILE as TINVEST_FILE
from indicators.store import Store

TINVEST = "T-Invest"
MANUAL = "ручная запись"
ISSUER = "документ эмитента"
ISSUER_ORIGIN = "issuer_docs"
MANUAL_FILE = "manual/dividends.json"
STATUSES = ("declared", "recommended")
QUARTERLY = "quarterly"
DEFAULT_DPS_TOLERANCE = 0.005
KEEP = ("year", "period", "label", "dps", "status", "record_date", "last_buy_date", "ex_date", "pay_date",
        "decided_date", "recommended_date", "sources")
LOOSE_NOTE = "брокер: {dps} ₽, реестр {date} — период не определён"


class RegisterError(ValueError):
    """Ручная запись реестра не принята или тревогу не собрать."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def period_rule(cfg: Mapping[str, Any]) -> str:
    return str((cfg.get("dividends") or {}).get("period_rule") or "annual")


def _split_adjust(dps: float, day: str | None, splits: Sequence[Mapping[str, Any]], field: str) -> float:
    out = float(dps)
    for s in splits or ():
        cut = str(s.get(field) or s.get("first_trade_date") or "")
        if day and cut and str(day)[:10] < cut and s.get("factor"):
            out /= float(s["factor"])
    return round(out, 6)


def broker_split_adjusted(cfg: Mapping[str, Any]) -> bool:
    """Брокер сам пересчитывает размер дивиденда на дробление (`tinvest.dividends_split_adjusted`): да —
    записи календаря уже в нынешних акциях, и сборщик их не делит. Нет настройки — да: так отдаёт брокер."""
    value = (cfg.get("tinvest") or {}).get("dividends_split_adjusted")
    return True if value is None else bool(value)


def tinvest_records(store: Store, ticker: str, *, splits: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Записи брокерского календаря. `splits` — дробления, на которые размер надо пересчитать самим
    (брокер отдаёт его как объявлен): запись с датой реестра раньше первого торгового дня после
    дробления делится на коэффициент. Пусто — размер берётся как есть."""
    data = store.read_state(TINVEST_FILE) or {}
    out = []
    for r in (data.get("by_ticker") or {}).get(ticker) or []:
        row = dict(r)
        try:
            row["dps"] = _split_adjust(float(row["dps"]), row.get("record_date"), splits, "first_trade_date")
        except (KeyError, TypeError, ValueError):
            continue
        out.append(row)
    return out


def news_decisions(store: Store, cfg: Mapping[str, Any], *,
                   splits: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Решения собрания и рекомендации совета из новостей видов `dividends.news_kinds`."""
    div = cfg.get("dividends") or {}
    kinds = dict(div.get("news_kinds") or {})
    patterns = div.get("period_patterns") if period_rule(cfg) == QUARTERLY else None
    items = (store.read_state("news/items.json") or {}).get("items") or {}
    out = []
    for url, item in sorted(items.items()):
        kind = str(item.get("kind") or "")
        if kind not in kinds or item.get("topic") != "dividend":
            continue
        text = f"{item.get('title') or ''}. {item.get('text') or ''}"
        got = news.extract_dividend_decision(text, published=item.get("published") or item.get("first_seen"),
                                             period_patterns=patterns)
        if got is not None:
            got["dps"] = _split_adjust(got["dps"], got.get("decided_date"), splits, "date")
            out.append({**got, "source": kinds[kind], "url": url, "published": item.get("published")})
    return out


def manual_records(store: Store) -> list[dict[str, Any]]:
    return [dict(r) for r in (store.read_state(MANUAL_FILE) or {}).get("records") or []]


def record_manual(store: Store, *, year: int | None, dps: float, status: str, source: str,
                  record_date: str | None = None, decided_date: str | None = None, pay_date: str | None = None,
                  last_buy_date: str | None = None, dps_preferred: float | None = None,
                  period: str | None = None, label: str | None = None, origin: str | None = None,
                  extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Запись решения собрания или рекомендации совета: оператором (`record-dividend`) или сборщиком
    документов эмитента (`origin`). День рекомендации совета — `decided_date` записи `recommended`."""
    if status not in STATUSES:
        raise RegisterError(f"статус {status!r}: допустимы {', '.join(STATUSES)}")
    if not source or not str(source).strip():
        raise RegisterError("нужна ссылка на документ эмитента (сообщение о существенном факте, протокол, пресс-релиз)")
    if not dps or dps <= 0:
        raise RegisterError(f"DPS {dps}: нужен положительный валовой дивиденд на акцию, ₽")
    if period is not None:
        try:
            period_year = periods.parse_quarter(period)[0]
        except periods.PeriodError as exc:
            raise RegisterError(f"период {period!r} — не квартал прибыли вида 2026Q3") from exc
        if year is not None and int(year) != period_year:
            raise RegisterError(f"год {year} не совпадает с годом периода {period}")
        year = period_year
    if year is None:
        raise RegisterError("нужен год прибыли (--year) или квартал прибыли (--period)")
    if status == "declared" and not record_date:
        raise RegisterError("у решения собрания нужна дата реестра (--record-date)")
    for name, day in (("record_date", record_date), ("decided_date", decided_date), ("pay_date", pay_date),
                      ("last_buy_date", last_buy_date)):
        if day:
            try:
                date.fromisoformat(day)
            except ValueError as exc:
                raise RegisterError(f"{name}: {day!r} — не дата YYYY-MM-DD") from exc
    rec = {"year": int(year), "period": period, "label": (str(label).strip() or None) if label else None,
           "dps": float(dps), "dps_preferred": dps_preferred, "status": status,
           "record_date": record_date, "ex_date": record_date, "last_buy_date": last_buy_date,
           "pay_date": pay_date, "decided_date": decided_date, "source": str(source).strip(),
           "origin": origin, "recorded_at": _now(), **dict(extra or {})}
    held = store.read_state(MANUAL_FILE) or {"records": []}
    held.setdefault("records", []).append(rec)
    store.write_state(MANUAL_FILE, held)
    return rec


def _latest(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return sorted(rows, key=lambda r: str(r.get(key) or ""))[-1] if rows else None


def _best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Главная запись источника: последнее решение собрания, а без него — последняя запись."""
    return _latest([r for r in rows if r.get("status") == "declared"], "recorded_at") or _latest(rows, "recorded_at")


def _word(r: Mapping[str, Any]) -> str:
    """Источник записи словом для `sources`: документ эмитента, ручная запись или лента новости."""
    if r.get("origin") == ISSUER_ORIGIN:
        return ISSUER
    return str(r["source"]) if r.get("url") else MANUAL


def merge(key: int | str, tinvest: list[dict], found: list[dict], manual: list[dict], *, today: date,
          tolerance: float = DEFAULT_DPS_TOLERANCE, issuer_first: bool = False) -> dict[str, Any]:
    """Одна запись реестра из источников (правила — в шапке модуля). `key` — год или квартал прибыли;
    `issuer_first` — опорные DPS и даты берутся у документа эмитента, брокер — сверка."""
    ti = _latest(tinvest, "record_date")
    doc = _best([r for r in manual if r.get("origin") == ISSUER_ORIGIN])
    hand = _best([r for r in manual if r.get("origin") != ISSUER_ORIGIN])
    ordered = sorted(found, key=lambda r: (r["status"] == "declared", str(r.get("published") or "")))
    last_news = ordered[-1] if ordered else None
    order = (doc, hand, ti, last_news) if issuer_first else (ti, doc, hand, last_news)
    ref = next((r for r in order if r is not None), None)
    if ref is None:
        raise ValueError(f"{key}: нет ни одного источника")
    dps = float(ref["dps"])
    record = next((r["record_date"] for r in order if r is not None and r.get("record_date")), None) or next(
        (r["record_date"] for r in reversed(ordered) if r.get("record_date")), None)

    def agrees(r: Mapping[str, Any]) -> bool:
        return abs(float(r["dps"]) - dps) <= tolerance and (
            not r.get("record_date") or not record or r["record_date"] == record)

    def differs(name: str, r: Mapping[str, Any]) -> str:
        return (f"{name}: {r['dps']} ₽, реестр {r.get('record_date') or '—'} — не совпадает с {dps} ₽, "
                f"{record or '—'}" + (f" ({r['url']})" if r.get("url") else ""))

    notes: list[str] = []
    news_ok = [r for r in ordered if agrees(r)]
    notes += [differs(r["source"], r) for r in ordered if not agrees(r)]
    held = [r for r in (doc, hand) if r is not None and agrees(r)]
    notes += [differs(_word(r), r) for r in (doc, hand) if r is not None and not agrees(r)]
    ti_ok = ti is not None and agrees(ti)
    if ti is not None and not ti_ok:
        notes.append(differs(TINVEST, ti))
    evidence = held + list(reversed(news_ok))
    declared = [r for r in evidence if r.get("status") == "declared"]
    recommended = [r for r in evidence if r.get("status") == "recommended"]
    day = today.isoformat()
    cut_off = bool(ti_ok and record and record <= day)       # день реестра у брокера наступил: решение состоялось
    status = "recommended" if recommended and not declared and not cut_off else "declared"
    # Одна новость (решение собрания важнее рекомендации), документ эмитента и ручная запись; у
    # объявленной записи рекомендация совета вторым источником решения не считается.
    counted = [r for r in news_ok[-1:] + held if status == "recommended" or r.get("status") == "declared"]
    sources = ([TINVEST] if ti_ok else []) + [_word(r) for r in counted]
    decided = next((r.get("decided_date") for r in declared if r.get("decided_date")), None)
    advised = [r.get("decided_date") for r in list(manual) + list(found)
               if r.get("status") == "recommended" and r.get("decided_date") and agrees(r)]
    first = [r for r in ((doc, hand, ti) if issuer_first else (ti, doc, hand))
             if r is not None and ((r is ti and ti_ok) or any(r is h for h in held))]
    pay = next((r["pay_date"] for r in first if r.get("pay_date")), None)
    if (ti_ok or status == "declared") and pay and pay <= day:
        status = "paid"
    label = next((r.get("label") for r in held + news_ok[::-1] if r.get("label")), None)
    year = int(key) if not isinstance(key, str) else periods.parse_quarter(key)[0]
    return {"year": year, "period": key if isinstance(key, str) else None, "label": label, "dps": dps,
            "status": status, "record_date": record,
            "last_buy_date": next((r["last_buy_date"] for r in (ti if ti_ok else None, hand) if r
                                   and r.get("last_buy_date")), None),
            "ex_date": record, "pay_date": pay, "decided_date": decided,
            "recommended_date": min(advised) if advised else None,
            "sources": list(dict.fromkeys(sources)), "notes": notes,
            "evidence": ([{"source": TINVEST, "dps": ti["dps"], "record_date": ti.get("record_date")}] if ti else [])
            + [{"source": _word(r), "status": r.get("status"), "dps": r["dps"],
                "record_date": r.get("record_date"), "decided_date": r.get("decided_date"),
                "ref": r.get("url") or r.get("source")} for r in evidence]}


def assign_periods(tinvest: list[dict], dated: list[dict], *, lag: int | None,
                   tolerance: float = DEFAULT_DPS_TOLERANCE) -> tuple[dict[str, list[dict]], list[dict]]:
    """Период записей брокера (правило — в шапке модуля) → ({период: [записи]}, записи без периода)."""
    by_period: dict[str, list[dict]] = {}
    loose: list[dict] = []
    for r in tinvest:
        same_day = [d for d in dated if d.get("period") and d.get("record_date") == r.get("record_date")]
        exact = [d for d in same_day if abs(float(d["dps"]) - float(r["dps"])) <= tolerance]
        periods_hit = {d["period"] for d in (exact or same_day)}
        if len(periods_hit) == 1:
            by_period.setdefault(periods_hit.pop(), []).append(r)
        else:
            loose.append(r)
    taken = set(by_period) | {d["period"] for d in dated if d.get("period")}
    unassigned: list[dict] = []

    def quarter(r: Mapping[str, Any]) -> str:
        return periods.quarter_of(date.fromisoformat(str(r["record_date"])[:10]))

    for r in loose:
        alone = sum(1 for x in loose if quarter(x) == quarter(r)) == 1
        guess = periods.shift_quarter(quarter(r), -int(lag)) if lag else None
        if guess is not None and alone and guess not in taken:
            by_period[guess] = [r]
            taken.add(guess)
        else:
            unassigned.append(r)
    return by_period, unassigned


def build_full(store: Store, *, ticker: str, today: date, cfg: Mapping[str, Any], since: str | None = None,
               splits: Sequence[Mapping[str, Any]] = ()) -> tuple[list[dict[str, Any]], list[str]]:
    """(записи реестра, строки о записях брокера без периода). `since` — отсечь записи с датой реестра
    (или решением) раньше даты; `splits` — дробления из фактов (`config.splits()`): на них пересчитываются
    суммы из новостей до дня дробления, а записи брокера — только при `tinvest.dividends_split_adjusted: false`."""
    div = cfg.get("dividends") or {}
    tol = float(div.get("dps_tolerance", DEFAULT_DPS_TOLERANCE))
    quarterly = period_rule(cfg) == QUARTERLY
    key = "period" if quarterly else "year"
    groups: dict[Any, dict[str, list]] = {}
    usable_rows: dict[str, list[dict]] = {}
    broker_splits = () if broker_split_adjusted(cfg) else splits
    found = news_decisions(store, cfg, splits=splits)
    # пост канала эмитента (слово вида — «документ эмитента») — источник первого рода, не новость
    issuer_posts = [{**r, "origin": ISSUER_ORIGIN} for r in found if r.get("source") == ISSUER]
    found = [r for r in found if r.get("source") != ISSUER]
    for kind, rows in (("tinvest", tinvest_records(store, ticker, splits=broker_splits)),
                       ("news", found), ("manual", manual_records(store) + issuer_posts)):
        good = []
        for r in rows:
            try:
                float(r["dps"])
                if not (quarterly and kind == "tinvest"):
                    periods.parse_quarter(r[key]) if quarterly else int(r[key])
            except (KeyError, TypeError, ValueError):
                continue
            good.append(r)
        usable_rows[kind] = good
    loose_notes: list[str] = []
    if quarterly:
        lag = div.get("record_lag_quarters")
        assigned, loose = assign_periods(usable_rows["tinvest"], usable_rows["manual"] + usable_rows["news"],
                                         lag=int(lag) if isinstance(lag, int) and not isinstance(lag, bool) else None,
                                         tolerance=tol)
        for p, rows in assigned.items():
            groups.setdefault(p, {})["tinvest"] = rows
        for r in loose:
            if not since or str(r.get("record_date") or "") >= since:
                loose_notes.append(LOOSE_NOTE.format(dps=r["dps"], date=r.get("record_date") or "—"))
    else:
        for r in usable_rows["tinvest"]:
            groups.setdefault(int(r["year"]), {}).setdefault("tinvest", []).append(r)
    for kind in ("news", "manual"):
        for r in usable_rows[kind]:
            groups.setdefault(r[key] if quarterly else int(r[key]), {}).setdefault(kind, []).append(r)
    out = []
    for k, src in sorted(groups.items(), key=lambda kv: str(kv[0])):
        rec = merge(k, src.get("tinvest", []), src.get("news", []), src.get("manual", []), today=today,
                    tolerance=tol, issuer_first=quarterly)
        anchor = rec.get("record_date") or rec.get("decided_date") or rec.get("recommended_date")
        if since and anchor and anchor < since:
            continue
        out.append(rec)
    for note in loose_notes:
        day = note_date(note)
        for rec in out:
            if day and rec.get("record_date") and periods.quarter_of(date.fromisoformat(rec["record_date"])) \
                    == periods.quarter_of(date.fromisoformat(day)):
                rec["notes"].append(note)
    return out, loose_notes


def note_date(note: str) -> str | None:
    """Дата реестра из строки `LOOSE_NOTE`."""
    head, _, tail = note.partition("реестр ")
    day = tail[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    return day


def build(store: Store, *, ticker: str, today: date, cfg: Mapping[str, Any], since: str | None = None,
          splits: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Записи реестра по ключу настройки (год или квартал прибыли)."""
    return build_full(store, ticker=ticker, today=today, cfg=cfg, since=since, splits=splits)[0]


def usable(rec: Mapping[str, Any]) -> bool:
    """Запись закрывает период: выплачена или объявлена и подтверждена двумя источниками (М§15)."""
    return rec.get("status") == "paid" or (rec.get("status") == "declared" and len(set(rec.get("sources") or [])) >= 2)


def decision_quarter(period: str, calendar: Mapping[str, Any]) -> str:
    """Квартал решения о дивиденде за квартал прибыли по карте лагов книги (не раньше первого квартала сетки)."""
    lag = calendar.get("decision_lag_quarters")
    if isinstance(lag, Mapping):
        n = periods.parse_quarter(period)[1]
        lag = lag.get(str(n), lag.get(n))
    if isinstance(lag, bool) or not isinstance(lag, int):
        raise RegisterError("в книге нет dividends.calendar.decision_lag_quarters для квартального календаря")
    q = periods.shift_quarter(period, lag)
    first = calendar.get("first_period")
    return max(q, str(first)) if first and periods.is_quarter(str(first)) else q


def label_of(period: str | None, year: int | None, label: str | None,
             period_labels: Mapping[str, Any] | None) -> str:
    """Слова записи: слова решения, иначе подпись периода книги (`meta.labels.periods`) с годом."""
    if label:
        return str(label)
    n = periods.parse_quarter(period)[1] if period else 4
    y = periods.parse_quarter(period)[0] if period else year
    words = (period_labels or {}).get(str(n), (period_labels or {}).get(n))
    return str(words).format(year=y) if words else (period or str(y))


def _detail(rows: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(f"{r['status']} {r['dps']} ₽ ({', '.join(r.get('sources') or []) or 'без источника'})"
                     for r in rows) or "записей нет"


def _text(template: str | None, **fields: Any) -> str:
    if not template:
        raise RegisterError("в книге нет meta.labels.register.collector_alarm — текст тревоги реестра не собрать")
    try:
        return str(template).format(**fields)
    except (KeyError, IndexError) as exc:
        raise RegisterError(f"meta.labels.register.collector_alarm: незнакомое поле {exc}") from exc


def seed_closed(seed: Sequence[Mapping[str, Any]], *, quarterly: bool) -> set[Any]:
    """Периоды, закрытые стартовым реестром фактов: кварталы прибыли записей `paid`, при годовом
    календаре — годы записей `paid` без квартала (запись за квартал год не закрывает). Запись
    `declared` период не закрывает."""
    paid = [r for r in seed or () if r.get("status") == "paid"]
    if quarterly:
        return {str(r["period"]) for r in paid if r.get("period")}
    out = set()
    for r in paid:
        if r.get("period"):
            continue
        try:
            out.add(int(r["year"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def alarm(records: Sequence[Mapping[str, Any]], *, today: date, agm_quarter: int | None = None,
          calendar: Mapping[str, Any] | None = None, closed_through: str | None = None,
          template: str | None = None, period_labels: Mapping[str, Any] | None = None,
          seed: Sequence[Mapping[str, Any]] = (), annual_decision: bool = False) -> str | None:
    """Тревога реестра (правило — в шапке модуля) или None. `calendar` — `dividends.calendar` книги
    (с `first_period`), `closed_through` — последний закрытый квартал прибыли по фактам, `template` —
    `meta.labels.register.collector_alarm`, `period_labels` — `meta.labels.periods`, `seed` — стартовый
    реестр фактов (`config.register_seed()`): период с записью `paid` в нём закрыт; `annual_decision` — решение раз
    в год за весь год прибыли (`dividends.annual_decision`): смотрятся только четвёртые кварталы."""
    cal = dict(calendar or {})
    if cal.get("frequency") == QUARTERLY:
        if not closed_through:
            return None
        settled = seed_closed(seed, quarterly=True)
        gaps = []
        period = periods.shift_quarter(closed_through, 1)
        while period <= periods.quarter_of(today):
            if annual_decision and periods.parse_quarter(period)[1] != 4:
                period = periods.shift_quarter(period, 1)
                continue
            end = periods.quarter_end(decision_quarter(period, cal))
            if end < today and period not in settled and not any(
                    r.get("period") == period and usable(r) for r in records):
                have = [r for r in records if r.get("period") == period]
                label = next((r.get("label") for r in have if r.get("label")), None)
                gaps.append(_text(template, year=periods.parse_quarter(period)[0], period=period,
                                  label=label_of(period, None, label, period_labels), end=end.isoformat(),
                                  detail=_detail(have)))
            period = periods.shift_quarter(period, 1)
        return "; ".join(gaps) or None
    quarter = agm_quarter if agm_quarter is not None else cal.get("agm_quarter")
    if isinstance(quarter, bool) or not isinstance(quarter, int) or not quarter:
        return None
    year = today.year - 1
    end = periods.quarter_end(periods.quarter(today.year, int(quarter)))
    if today <= end:
        return None
    if year in seed_closed(seed, quarterly=False) or any(r.get("year") == year and usable(r) for r in records):
        return None
    have = [r for r in records if r.get("year") == year]
    return _text(template, year=year, period="", label=label_of(None, year, None, period_labels),
                 end=end.isoformat(), detail=_detail(have))


def alarm_from_book(records: Sequence[Mapping[str, Any]], today: date) -> str | None:
    """Тревога реестра по календарю дивидендов книги, закрытому кварталу фактов, стартовому реестру фактов
    и подписям книги."""
    return alarm(records, today=today, calendar=config.dividend_calendar(), closed_through=config.closed_through(),
                 template=config.book_value("meta.labels.register.collector_alarm"),
                 period_labels=config.book_value("meta.labels.periods"), seed=config.register_seed(),
                 annual_decision=bool(config.setting("dividends.annual_decision", False)))
