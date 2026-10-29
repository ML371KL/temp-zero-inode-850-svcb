"""Календарь индикаторов и выпуска: месячный релиз эмитента, формы ЦБ, МСФО, события фактов.

Источники дат по убыванию силы: `facts/calendar.json` (поток facts; подтверждённые и оценочные
даты, события эмитента: решение о дивиденде, дата реестра, выход формы банковской группы),
календарь отчётов T-Invest, расписание `sources.yaml → schedule` (окна дней). Форма 0409102 — по
истории первого появления (`cbr_forms.expected_form102_date`).

Настройки расписания:

* `monthly` — месячное событие эмитента: вид события фактов (`kind`), заголовок (`title` с полем
  `{month}` — месяц словами), окно дней следующего месяца (`day`, для декабря — `december_day`),
  будит ли релиз выпуск (`wakes_release`); `monthly: {enabled: false}` — события нет. Без ключа —
  событие вида `ras` с окнами `ras_release_day` и `ras_december_day`;
* `ifrs_quarter: {month_offset, day}` — МСФО 1–3 кварталов: сдвиг месяца от конца квартала и дни;
  без ключа — месяц после квартала и дни `ifrs_quarter_day`; `ifrs_q4` — МСФО года;
* `watch_kinds` — виды событий, в окна которых открыт дозор (`is_release_day`): `ifrs`, вид
  месячного события, любой вид событий фактов (`dividend_decision`); без ключа — месячное событие
  и МСФО.

Литералов дат нет: окна — числа дней конфигурации, годы — из переданных периодов.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from indicators import cbr_forms, config, issuer_docs, periods
from indicators.store import Store

EVENT_HORIZON_DAYS = 366
RECENT_DAYS = 7
LEGACY_MONTHLY_KIND = "ras"
FORM102_KIND = "form102"            # событие формы 0409102 банка
DEFAULT_MONTHLY_PREFIX = "ras.release."
DEFAULT_MAIN_METRIC = "np_ytd"
IFRS_KIND = "ifrs"
MONTH_WORDS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
               "ноябрь", "декабрь")


def _clip(y: int, m: int, day: int) -> date:
    return date(y, m, min(day, periods.month_end(periods.month(y, m)).day))


def month_words(month: str) -> str:
    """«2026M09» → «сентябрь 2026 года»."""
    y, m = periods.parse_month(month)
    return f"{MONTH_WORDS[m - 1]} {y} года"


# ------------------------------------------------------------------ месячное событие

def monthly_spec(schedule: dict[str, Any]) -> dict[str, Any] | None:
    """Настройка месячного события эмитента; None — событие выключено."""
    raw = schedule.get("monthly")
    if raw is False or (isinstance(raw, dict) and raw.get("enabled") is False):
        return None
    if isinstance(raw, dict):
        day = tuple(raw.get("day") or schedule.get("ras_release_day", (8, 15)))
        return {"kind": str(raw.get("kind") or LEGACY_MONTHLY_KIND), "title": raw.get("title"), "day": day,
                "december_day": tuple(raw.get("december_day") or day),
                "wakes_release": bool(raw.get("wakes_release", True))}
    day = tuple(schedule.get("ras_release_day", (8, 15)))
    return {"kind": LEGACY_MONTHLY_KIND, "title": None, "day": day,
            "december_day": tuple(schedule.get("ras_december_day", (8, 15))), "wakes_release": True}


def monthly_series() -> str:
    """Ряд, по которому месяц считается принятым из релиза: `monthly.series_prefix` + `monthly.main_metric`."""
    try:
        block = config.setting("monthly") or {}
    except config.ConfigError:
        block = {}
    return f"{block.get('series_prefix') or DEFAULT_MONTHLY_PREFIX}{block.get('main_metric') or DEFAULT_MAIN_METRIC}"


def monthly_window(month: str, schedule: dict[str, Any]) -> tuple[date, date]:
    """Окно выхода месячного релиза за месяц: дни следующего месяца (декабрь — своё окно)."""
    spec = monthly_spec(schedule) or monthly_spec({})
    y, m = periods.parse_month(periods.shift_month(month, 1))
    lo, hi = spec["december_day"] if periods.parse_month(month)[1] == 12 else spec["day"]
    return _clip(y, m, int(lo)), _clip(y, m, int(hi))


ras_release_window = monthly_window        # прежнее имя


def ifrs_window(period: str, schedule: dict[str, Any]) -> tuple[date, date]:
    """Окно выхода МСФО квартала: сдвиг месяца от конца квартала и дни — из расписания."""
    _, q = periods.parse_quarter(period)
    last = periods.quarter_months(period)[-1]
    if q == 4:
        spec = schedule.get("ifrs_q4", {"month_offset": 2, "day": (20, 28)})
        offset = int(spec.get("month_offset", 2))
        lo, hi = spec.get("day", (20, 28))
    else:
        spec = schedule.get("ifrs_quarter")
        if isinstance(spec, dict):
            offset = int(spec.get("month_offset", 1))
            lo, hi = spec.get("day") or schedule.get("ifrs_quarter_day", (20, 31))
        else:
            offset = 1
            lo, hi = schedule.get("ifrs_quarter_day", (20, 31))
    ty, tm = periods.parse_month(periods.shift_month(last, offset))
    return _clip(ty, tm, int(lo)), _clip(ty, tm, int(hi))


def tinvest_reports(store: Store) -> list[dict[str, Any]]:
    data = store.read_state("tinvest/reports.json") or {}
    return list(data.get("events") or [])


def _tinvest_pair(store: Store, period: str) -> list[date]:
    y, q = periods.parse_quarter(period)
    days = sorted({date.fromisoformat(e["date"]) for e in tinvest_reports(store)
                   if e.get("year") == y and e.get("num") == q and "QUARTER" in str(e.get("type", ""))})
    return days


def _facts_event(events: list[dict], kind: str, covers: str) -> dict | None:
    for e in events:
        if e.get("kind") == kind and e.get("covers") == covers:
            return e
    return None


def monthly_release(month: str, *, store: Store, schedule: dict, facts_events: list[dict]) -> dict[str, Any]:
    """Ожидаемый месячный релиз за месяц: {date, confirmed, precision, earliest, latest, src}."""
    spec = monthly_spec(schedule) or monthly_spec({})
    ev = _facts_event(facts_events, spec["kind"], month)
    lo, hi = monthly_window(month, schedule)
    if ev and ev.get("date"):
        return {"date": ev["date"], "confirmed": bool(ev.get("confirmed")), "precision": ev.get("precision", "day"),
                "earliest": ev.get("earliest"), "latest": ev.get("latest"), "src": "facts/calendar.json"}
    _, m = periods.parse_month(month)
    if m % 3 == 0 and spec["kind"] == LEGACY_MONTHLY_KIND:
        # календарь брокера не различает релиз банка и МСФО: из двух дат квартала ранняя — релиз
        pair = _tinvest_pair(store, periods.quarter_of_month(month))
        if len(pair) >= 2:
            return {"date": pair[0].isoformat(), "confirmed": True, "precision": "day",
                    "earliest": None, "latest": None, "src": "T-Invest, календарь отчётов"}
    return {"date": lo.isoformat(), "confirmed": False, "precision": "window",
            "earliest": lo.isoformat(), "latest": hi.isoformat(), "src": "sources.yaml schedule"}


ras_release = monthly_release              # прежнее имя


def ifrs_report(period: str, *, store: Store, schedule: dict, facts_events: list[dict]) -> dict[str, Any]:
    """Ожидаемая МСФО квартала: {date, confirmed, precision, earliest, latest, src}."""
    ev = _facts_event(facts_events, IFRS_KIND, period)
    if ev and ev.get("date"):
        return {"date": ev["date"], "confirmed": bool(ev.get("confirmed")), "precision": ev.get("precision", "day"),
                "earliest": ev.get("earliest"), "latest": ev.get("latest"), "src": "facts/calendar.json",
                "id": ev.get("id"), "title": ev.get("title")}
    pair = _tinvest_pair(store, period)
    if pair:
        return {"date": pair[-1].isoformat(), "confirmed": True, "precision": "day", "earliest": None,
                "latest": None, "src": "T-Invest, календарь отчётов"}
    lo, hi = ifrs_window(period, schedule)
    return {"date": hi.isoformat(), "confirmed": False, "precision": "window", "earliest": lo.isoformat(),
            "latest": hi.isoformat(), "src": "sources.yaml schedule"}


def ras_known(store: Store, month: str, as_of: str | None = None) -> str | None:
    """Как месяц уже известен: `release` (месячный релиз) | `form102` | None."""
    s = store.load(monthly_series())
    if s is not None and s.value_as_of(month, as_of) is not None:
        return "release"
    f = store.load("cbr.f102.ni_ytd")
    if f is not None and f.value_as_of(month, as_of) is not None:
        return "form102"
    return None


def next_ras(today: date, *, store: Store, schedule: dict, facts_events: list[dict],
             release_auto: bool = True) -> dict[str, Any]:
    """П§2 `calendar.next_ras` без `days`: первый месяц, которого ещё нет ни в релизе, ни в форме 102.

    Дата формы 0409102 — оценка по прошлым публикациям, не объявление: отдаётся окном
    (`form102_date_est` — нижний край, `form102_latest_est` — верхний). `enters_via` — чем месяц входит
    в выпуск: `release`, если месячный релиз будит выпуск, иначе `form102`."""
    current = periods.month_of(today)
    month = current
    for back in (3, 2, 1):
        candidate = periods.shift_month(current, -back)
        if ras_known(store, candidate) is None:
            month = candidate
            break
    spec = monthly_spec(schedule)
    f_lo, f_hi = cbr_forms.expected_form102_date(store, month, default_days=tuple(schedule.get("form102_day", (24, 26))))
    if spec is None:
        return {"month": month, "release_date": None, "release_confirmed": False, "form102_date_est": f_lo,
                "form102_latest_est": f_hi, "enters_via": "form102", "date": f_lo}
    rel = monthly_release(month, store=store, schedule=schedule, facts_events=facts_events)
    enters = "release" if release_auto and spec["wakes_release"] else "form102"
    return {"month": month, "release_date": rel["date"], "release_confirmed": rel["confirmed"],
            "form102_date_est": f_lo, "form102_latest_est": f_hi, "enters_via": enters,
            "date": rel["date"] if enters == "release" else f_lo}


def open_ifrs_period(today: date, store: Store) -> str:
    """Самый ранний квартал без внесённого факта журнала (прибыль) не раньше прошлого квартала."""
    return periods.shift_quarter(periods.quarter_of(today), -1)


def _window(ev: dict[str, Any]) -> tuple[date, date]:
    return (date.fromisoformat(ev.get("earliest") or ev["date"]), date.fromisoformat(ev.get("latest") or ev["date"]))


def _decided(store: Store, covers: str | None, before: str) -> bool:
    """Решение о дивиденде за период уже записано раньше дня `before` (окно дозора закрыто)."""
    if not covers:
        return False
    rows = (store.read_state("manual/dividends.json") or {}).get("records") or []
    return any(r.get("period") == covers and r.get("status") == "declared"
               and str(r.get("recorded_at") or "")[:10] < before for r in rows)


def is_release_day(today: date, *, store: Store, schedule: dict, facts_events: list[dict]) -> bool:
    """Открыт ли сегодня дозор: день в окне события одного из видов `schedule.watch_kinds`.

    Месячный релиз — окно ещё не принятого месяца плюс `late_days`; МСФО — окно отчёта прошлого
    квартала, пока документ МСФО этого квартала не появился (со следующего дня окно закрыто); прочие
    виды — окна событий фактов плюс `late_days` (решение о дивиденде — пока решение не записано)."""
    kinds = schedule.get("watch_kinds")
    spec = monthly_spec(schedule)
    late = timedelta(days=int(schedule.get("late_days", 3)))
    if spec is not None and (kinds is None or spec["kind"] in kinds):
        for back in (1, 2):
            month = periods.shift_month(periods.month_of(today), -back)
            if ras_known(store, month) == "release":
                continue
            lo, hi = _window(monthly_release(month, store=store, schedule=schedule, facts_events=facts_events))
            if lo <= today <= hi + late:
                return True
    if kinds is None or IFRS_KIND in kinds:
        q = periods.shift_quarter(periods.quarter_of(today), -1)
        lo, hi = _window(ifrs_report(q, store=store, schedule=schedule, facts_events=facts_events))
        caught = issuer_docs.seen_periods(store, issuer_docs.IFRS_PREFIX).get(q)
        if lo <= today <= hi and not (caught and caught < today.isoformat()):
            return True
    skip = {IFRS_KIND} | ({spec["kind"]} if spec is not None else set())
    for kind in kinds or ():
        if kind in skip:
            continue
        for ev in facts_events:
            if ev.get("kind") != kind or not ev.get("date"):
                continue
            lo, hi = _window(ev)
            if lo <= today <= hi + late and not _decided(store, ev.get("covers"), today.isoformat()):
                return True
    return False


def events(today: date, *, store: Store, schedule: dict, facts_events: list[dict],
           register: list[dict] | tuple = ()) -> list[dict[str, Any]]:
    """События на 12 месяцев вперёд и за `RECENT_DAYS` назад (П§2 `calendar.events` без `days`)."""
    start, end = today - timedelta(days=RECENT_DAYS), today + timedelta(days=EVENT_HORIZON_DAYS)
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(ev: dict[str, Any]) -> None:
        d = date.fromisoformat(ev["date"])
        key = (ev["kind"], ev.get("covers"), ev["date"])
        if start <= d <= end and key not in seen:
            seen.add(key)
            out.append(ev)

    spec = monthly_spec(schedule)
    # Месячного события эмитента нет: событие фактов прежнего вида месячного релиза (`ras`) — окно выкладки форм ЦБ
    # банка, вид `form102`; свой расчётный день формы за тот же месяц тогда не добавляется (у фактов — окно и слова).
    form_months = set()
    for e in facts_events:
        if e.get("date"):
            ev = {k: e.get(k) for k in ("id", "date", "kind", "title", "covers", "confirmed", "precision",
                                        "earliest", "latest", "note", "estimated", "in_book")
                  if e.get(k) is not None or k in ("covers",)}
            if spec is None and ev.get("kind") == LEGACY_MONTHLY_KIND:
                ev["kind"] = FORM102_KIND
                form_months.add(str(ev.get("covers")))
            add(ev)
    month = periods.shift_month(periods.month_of(today), -1)
    for k in range(13):
        m = periods.shift_month(month, k)
        if spec is not None:
            rel = monthly_release(m, store=store, schedule=schedule, facts_events=facts_events)
            title = str(spec["title"]).format(month=month_words(m)) if spec["title"] else f"РСБУ банка за {m}"
            add({"id": f"{spec['kind']}-{m}", "date": rel["date"], "kind": spec["kind"], "title": title, "covers": m,
                 "confirmed": rel["confirmed"], "precision": rel["precision"],
                 **({"earliest": rel["earliest"], "latest": rel["latest"]} if rel["precision"] == "window" else {})})
        if m in form_months:
            continue
        f_lo, f_hi = cbr_forms.expected_form102_date(store, m, default_days=tuple(schedule.get("form102_day", (24, 26))))
        title = f"форма 0409102 за {month_words(m)}" if spec is None else f"форма 0409102 за {m}"
        add({"id": f"form102-{m}", "date": f_lo, "kind": "form102", "title": title,
             "covers": m, "confirmed": False, "precision": "window", "earliest": f_lo, "latest": f_hi})
    q = periods.shift_quarter(periods.quarter_of(today), -1)
    for k in range(5):
        p = periods.shift_quarter(q, k)
        rep = ifrs_report(p, store=store, schedule=schedule, facts_events=facts_events)
        add({"id": rep.get("id") or f"ifrs-{p}", "date": rep["date"], "kind": IFRS_KIND,
             "title": rep.get("title") or f"МСФО за {p}", "covers": p, "confirmed": rep["confirmed"],
             "precision": rep["precision"],
             **({"earliest": rep["earliest"], "latest": rep["latest"]} if rep["precision"] == "window" else {})})
    for r in register or ():
        key = r.get("period") or r.get("year")
        words = r.get("label") or f"за {key}"
        if r.get("pay_date"):
            add({"id": f"pay-{key}", "date": r["pay_date"], "kind": "pay", "title": f"выплата дивиденда {words}",
                 "covers": r.get("period"), "confirmed": True, "precision": "day"})
        if r.get("record_date"):
            add({"id": f"record-{key}", "date": r["record_date"], "kind": "record",
                 "title": f"дата реестра по дивиденду {words}", "covers": r.get("period"), "confirmed": True,
                 "precision": "day"})
    return sorted(out, key=lambda e: (e["date"], e["kind"]))
