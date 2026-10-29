"""Календарь индикаторов (окна МСФО и месячного релиза настройкой, дни дозора, события) и дозор месячного релиза.

Расписание эмитента — `data/indicators/sources.yaml`; события — заглушка фактов `tests/fixtures/ind/facts/`.
"""

from __future__ import annotations

from datetime import date

import pytest

from indicators import calendar as cal
from indicators import collect, config, issuer_docs, record, register, release_watch
from indicators.sources import Context
from indicators.store import Point, Store
from tests.support_ind import FakeGetter, use_fixtures, use_form_settings

pytestmark = pytest.mark.tact  # быстрые тесты такта


@pytest.fixture(autouse=True)
def _form_settings(monkeypatch):
    """Тесты общего каркаса — на настройках и истории формы образца (`tests/fixtures/ind/form/`): ветви, которыми
    настройки этой копии не пользуются; настройки копии проверяет `tests/test_ind_svcb.py`."""
    use_form_settings(monkeypatch)

LEGACY = {"ras_release_day": [8, 15], "ras_december_day": [17, 20], "ifrs_quarter_day": [20, 31],
          "ifrs_q4": {"month_offset": 2, "day": [20, 28]}, "late_days": 3}


def _env(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    return Store(tmp_path / "state"), config.sources()["schedule"], config.calendar_events()


def _ctx(store, today, getter=None):
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter or FakeGetter())


# ------------------------------------------------------------------ окна и расписание

def test_ifrs_window_month_offset_is_a_setting(monkeypatch, tmp_path):
    """МСФО 1–3 кварталов — второй месяц после квартала, годовой — март: сдвиг месяца в настройке, не в коде.
    Без ключа `ifrs_quarter` — месяц после квартала и прежний ключ дней."""
    _, sched, _ = _env(monkeypatch, tmp_path)
    assert cal.ifrs_window("2026Q1", sched) == (date(2026, 5, 11), date(2026, 5, 22))
    assert cal.ifrs_window("2026Q2", sched) == (date(2026, 8, 11), date(2026, 8, 22))
    assert cal.ifrs_window("2026Q3", sched) == (date(2026, 11, 11), date(2026, 11, 22))
    assert cal.ifrs_window("2026Q4", sched) == (date(2027, 3, 14), date(2027, 3, 20))
    assert cal.ifrs_window("2026Q3", LEGACY) == (date(2026, 10, 20), date(2026, 10, 31))
    assert cal.ifrs_window("2026Q4", LEGACY) == (date(2027, 2, 20), date(2027, 2, 28))
    assert cal.ifrs_window("2026Q1", {"ifrs_quarter": {"month_offset": 3, "day": [1, 31]}}) == (
        date(2026, 6, 1), date(2026, 6, 30))                          # день обрезается по длине месяца


def test_monthly_event_is_a_setting_and_can_be_switched_off(monkeypatch, tmp_path):
    store, sched, events = _env(monkeypatch, tmp_path)
    spec = cal.monthly_spec(sched)
    assert spec == {"kind": "ops_release", "title": "Операционные результаты за {month}", "day": (17, 29),
                    "december_day": (17, 29), "wakes_release": False}
    assert cal.monthly_window("2026M09", sched) == (date(2026, 10, 17), date(2026, 10, 29))
    assert cal.monthly_window("2027M01", sched) == (date(2027, 2, 17), date(2027, 2, 28))
    rel = cal.monthly_release("2026M09", store=store, schedule=sched, facts_events=events)
    assert rel == {"date": "2026-10-17", "confirmed": False, "precision": "window", "earliest": "2026-10-17",
                   "latest": "2026-10-29", "src": "sources.yaml schedule"}
    named = events + [{"kind": "ops_release", "covers": "2026M09", "date": "2026-10-23", "confirmed": True}]
    assert cal.monthly_release("2026M09", store=store, schedule=sched, facts_events=named)["date"] == "2026-10-23"
    # без ключа — событие прежнего вида со своими окнами; выключатель снимает событие совсем
    legacy = cal.monthly_spec(LEGACY)
    assert (legacy["kind"], legacy["day"], legacy["december_day"], legacy["wakes_release"]) == ("ras", (8, 15), (17, 20), True)
    assert cal.monthly_window("2026M12", LEGACY) == (date(2027, 1, 17), date(2027, 1, 20))
    assert cal.monthly_spec({"monthly": {"enabled": False}}) is None and cal.monthly_spec({"monthly": False}) is None
    assert cal.month_words("2026M09") == "сентябрь 2026 года"
    assert cal.monthly_series() == "ops.release.loans_gross"


def test_watch_days_are_ifrs_and_dividend_decision_only(monkeypatch, tmp_path):
    """Дни дозора — МСФО квартала и решение о дивиденде: окно месячного релиза дозор не открывает."""
    store, sched, events = _env(monkeypatch, tmp_path)
    assert sched["watch_kinds"] == ["ifrs", "dividend_decision"] and sched["watch_window_msk"] == ["09:00", "18:00"]

    def day(d):
        return cal.is_release_day(d, store=store, schedule=sched, facts_events=events)

    assert not day(date(2026, 10, 23))                    # окно месячного релиза за сентябрь — не день дозора
    assert not day(date(2026, 10, 31)) and day(date(2026, 11, 1)) and day(date(2026, 11, 30))    # МСФО «в ноябре»
    assert day(date(2026, 12, 1)) and day(date(2026, 12, 31)) and day(date(2027, 1, 3))          # решение + late_days
    assert not day(date(2027, 1, 4))
    # документ МСФО квартала появился — со следующего дня окно закрыто
    store.write_state(issuer_docs.CANDIDATES_FILE, {"ifrs_press:2026Q3:abc": {
        "kind": "ifrs_press", "period": "2026Q3", "first_seen": "2026-11-19T07:05:00+00:00", "status": "ok"}})
    assert day(date(2026, 11, 19)) and not day(date(2026, 11, 20))
    # решение о дивиденде записано — окно решения закрыто со следующего дня
    register.record_manual(store, year=None, period="2026Q3", dps=4.9, status="declared", record_date="2026-12-28",
                           source="протокол", origin="issuer_docs")
    rows = store.read_state("manual/dividends.json")
    rows["records"][0]["recorded_at"] = "2026-12-17T08:00:00+00:00"
    store.write_state("manual/dividends.json", rows)
    assert day(date(2026, 12, 17)) and not day(date(2026, 12, 18))
    # без `watch_kinds` — прежние окна: месячный релиз и МСФО
    legacy_store = Store(tmp_path / "legacy")
    assert cal.is_release_day(date(2026, 10, 9), store=legacy_store, schedule=LEGACY, facts_events=[])
    assert cal.is_release_day(date(2026, 10, 25), store=legacy_store, schedule=LEGACY, facts_events=[])
    assert not cal.is_release_day(date(2026, 10, 19), store=legacy_store, schedule=LEGACY, facts_events=[])
    off = {**LEGACY, "monthly": {"enabled": False}}
    assert not cal.is_release_day(date(2026, 10, 9), store=legacy_store, schedule=off, facts_events=[])


def test_dates_from_facts_and_the_broker(monkeypatch, tmp_path):
    store, sched, events = _env(monkeypatch, tmp_path)
    rep = cal.ifrs_report("2026Q3", store=store, schedule=sched, facts_events=events)
    assert (rep["date"], rep["confirmed"], rep["earliest"], rep["latest"], rep["src"]) == (
        "2026-11-19", False, "2026-11-01", "2026-11-30", "facts/calendar.json")
    store.write_state("tinvest/reports.json", {"events": [
        {"date": "2027-03-18", "year": 2026, "num": 4, "type": "PERIOD_TYPE_QUARTER"}]})
    by_broker = cal.ifrs_report("2026Q4", store=store, schedule=sched, facts_events=events)
    assert by_broker["date"] == "2027-03-18" and by_broker["confirmed"] and by_broker["src"].startswith("T-Invest")
    by_window = cal.ifrs_report("2027Q1", store=store, schedule=sched, facts_events=events)
    assert (by_window["date"], by_window["precision"]) == ("2027-05-22", "window")


def test_next_month_and_events(monkeypatch, tmp_path):
    store, sched, events = _env(monkeypatch, tmp_path)
    at = "2026-09-24T08:00:00+00:00"
    for m in ("2026M07", "2026M08"):
        store.upsert("ops.release.loans_gross", [Point(m, 3600.0, at)])
    nxt = cal.next_ras(date(2026, 10, 7), store=store, schedule=sched, facts_events=events)
    assert nxt == {"month": "2026M09", "release_date": "2026-10-17", "release_confirmed": False,
                   "form102_date_est": "2026-10-24", "form102_latest_est": "2026-10-26", "enters_via": "form102",
                   "date": "2026-10-24"}                                 # месячный релиз выпуск не будит
    assert cal.ras_known(store, "2026M08") == "release" and cal.ras_known(store, "2026M09") is None
    store.upsert("cbr.f102.ni_ytd", [Point("2026M09", 150.0, "2026-10-25T07:00:00+00:00")])
    assert cal.ras_known(store, "2026M09") == "form102"
    off = cal.next_ras(date(2026, 10, 7), store=Store(tmp_path / "x"), schedule={"monthly": {"enabled": False}},
                       facts_events=[])
    assert off["release_date"] is None and off["enters_via"] == "form102"
    reg = [{"year": 2026, "period": "2026Q2", "label": "за полугодие 2026 года", "record_date": "2026-10-12",
            "pay_date": "2026-10-26"}, {"year": 2025, "period": None, "pay_date": "2026-10-20"}]
    evs = cal.events(date(2026, 10, 7), store=store, schedule=sched, facts_events=events, register=reg)
    by_id = {e["id"]: e for e in evs}
    assert evs == sorted(evs, key=lambda e: (e["date"], e["kind"]))
    ops = by_id["ops_release-2026M09"]
    assert (ops["kind"], ops["title"], ops["covers"], ops["earliest"], ops["latest"]) == (
        "ops_release", "Операционные результаты за сентябрь 2026 года", "2026M09", "2026-10-17", "2026-10-29")
    assert not any(e["kind"] == "ras" for e in evs)
    assert by_id["ifrs-2026Q3"]["estimated"] is True and by_id["ifrs-2026Q3"]["title"] == "МСФО за 3 квартал 2026 года"
    assert {"dividend-2026Q3", "form805-2026Q3", "record-2026Q2", "cbr-2026-10-23"} <= set(by_id)     # события фактов
    assert by_id["pay-2026Q2"] == {"id": "pay-2026Q2", "date": "2026-10-26", "kind": "pay", "covers": "2026Q2",
                                  "title": "выплата дивиденда за полугодие 2026 года", "confirmed": True,
                                  "precision": "day"}
    assert by_id["pay-2025"]["title"] == "выплата дивиденда за 2025"
    assert by_id["form102-2026M09"]["precision"] == "window"
    assert not any(e["kind"] == "ops_release" for e in cal.events(
        date(2026, 10, 7), store=store, schedule={**sched, "monthly": {"enabled": False}}, facts_events=events))


# ------------------------------------------------------------------ дозор месячного релиза

def _candidate(store, numbers, *, month="2026M08", method="text", status="ok"):
    store.write_state(issuer_docs.CANDIDATES_FILE, {f"ops_release:{month}:abcdefabcdef": {
        "kind": "ops_release", "period": month, "month": month, "status": status, "method": method,
        "numbers": numbers, "url": "https://cdn.example/doc.pdf", "sha256": "ab" * 32,
        "first_seen": "2026-09-24T08:00:00+00:00"}})


def test_settings_of_the_monthly_release():
    spec = release_watch.monthly(config.sources())
    assert (spec.prefix, spec.main, spec.doc_kind, spec.wakes) == ("ops.release.", "loans_gross", "ops_release", False)
    assert spec.series("np_ytd") == "ops.release.np_ytd" and "np_m" not in spec.metrics
    assert (spec.unit("n1_0"), spec.unit("clients_total"), spec.unit("loans_gross")) == ("share", "mn", "RUB bn")
    default = release_watch.monthly({})
    assert (default.prefix, default.main, default.doc_kind, default.wakes) == ("ras.release.", "np_ytd", "ras_release", True)
    assert default.metrics == release_watch.METRICS
    words = {m: release_watch.metric_words(m) for m in release_watch.METRICS + spec.metrics}
    assert all(w != m and "_" not in w for m, w in words.items()), words     # ключи в строки для витрины не попадают


def test_text_document_of_the_issuer_is_accepted_alone(monkeypatch, tmp_path):
    """Таблицы PDF эмитента с текстовым слоем принимаются сами; форма 0409102 — подтверждение прибыли."""
    store, _, _ = _env(monkeypatch, tmp_path)
    numbers = {"loans_gross": 3700.0, "funds_total": 4200.0, "np_ytd": 130.1, "n1_0": 0.131, "clients_total": 57.3,
               "np_m": 20.0}                                             # метрики вне настройки не берутся
    _candidate(store, numbers)
    store.upsert("cbr.f102.ni_ytd", [Point("2026M08", 130.0, "2026-09-25T07:00:00+00:00")])
    ctx = _ctx(store, date(2026, 9, 26))
    out = release_watch.watch(ctx, "2026M08")
    assert sorted(out["new"]) == ["clients_total", "funds_total", "loans_gross", "n1_0", "np_ytd"]
    assert out["month_accepted"] and out["complete"] and not out["mismatches"] and not out["identity_failures"]
    acc = store.read_state("release_watch/2026M08.json")["accepted"]
    assert acc["loans_gross"]["kinds"] == ["pdf"] and acc["np_ytd"]["kinds"] == ["form102", "pdf"]
    loans = store.load("ops.release.loans_gross")
    assert loans.value_as_of("2026M08") == 3700.0 and loans.meta["unit"] == "RUB bn"
    assert store.load("ops.release.clients_total").meta["unit"] == "mn"
    assert store.load("ops.release.n1_0").meta["unit"] == "share" and store.load("ops.release.np_m") is None
    again = release_watch.watch(ctx, "2026M08")
    assert again["new"] == [] and not again["month_accepted"]            # повторный проход ничего не пишет
    # другое число того же месяца автомат не переписывает — расхождение; правит ручной ввод
    _candidate(store, {**numbers, "loans_gross": 3710.0})
    third = release_watch.watch(ctx, "2026M08")
    assert third["mismatches"] == ["loans_gross"] and loans.value_as_of("2026M08") == 3700.0
    values = record.parse_pairs(["loans_gross=3710", "n1_0=13,2%"], metrics=release_watch.monthly(ctx.cfg).metrics)
    record.record_ras(store, "2026M08", values, "исправленный релиз, с. 2")
    fixed = release_watch.watch(ctx, "2026M08")
    assert sorted(fixed["new"]) == ["loans_gross", "n1_0"]
    assert store.load("ops.release.loans_gross").point_as_of("2026M08").status == "manual"
    assert store.load("ops.release.n1_0").value_as_of("2026M08") == pytest.approx(0.132)
    with pytest.raises(record.RecordError, match="неизвестная метрика"):
        record.parse_pairs(["np_m=20"], metrics=release_watch.monthly(ctx.cfg).metrics)


def test_a_recognised_document_still_needs_a_second_kind():
    cfg = {"tolerance": {"money": 0.15}}
    ocr = {"kind": "pdf", "value": 130.1, "method": "ocr"}
    form = {"kind": "form102", "value": 130.0}
    assert release_watch.decide({"np_ytd": [ocr]}, cfg) == ({}, {})
    accepted, mismatches = release_watch.decide({"np_ytd": [ocr, form]}, cfg)
    assert accepted["np_ytd"] == {"value": 130.1, "kinds": ["form102", "pdf"]} and not mismatches
    accepted, mismatches = release_watch.decide({"np_ytd": [ocr, {"kind": "form102", "value": 140.0}]}, cfg)
    assert not accepted and "np_ytd" in mismatches
    text = {"kind": "pdf", "value": 130.1, "method": "text"}
    accepted, mismatches = release_watch.decide({"np_ytd": [text, {"kind": "form102", "value": 140.0}]}, cfg)
    assert accepted["np_ytd"] == {"value": 130.1, "kinds": ["pdf"]} and not mismatches
    # две группы по два вида — расхождение; в январе нарастающее и месяц — одно число (потоки с обеими метриками)
    rows = [{"kind": k, "value": v} for k, v in (("interfax", 150.0), ("telegram:a", 150.0), ("kommersant", 140.0),
                                                 ("smartlab", 140.0))]
    assert release_watch.decide({"np_ytd": rows}, cfg) == ({}, {"np_ytd": rows})
    jan = {"np_m": {"value": 15.2, "kinds": ["interfax", "smartlab"]}}
    release_watch.derive_month(Store.__new__(Store), "2027M01", jan)
    assert jan["np_ytd"] == {"value": 15.2, "kinds": ["calc"], "manual": False}
    only_ytd = {"np_ytd": {"value": 15.2, "kinds": ["pdf"]}}
    release_watch.derive_month(Store.__new__(Store), "2027M01", only_ytd, release_watch.monthly(config.sources()))
    assert set(only_ytd) == {"np_ytd"}                    # месячной прибыли в метриках релиза нет — не выводится
    assert release_watch.release_days("2026M12") == (date(2026, 12, 31), date(2027, 1, 31))


def test_profit_of_the_release_against_the_form_102(tmp_path):
    """Флаг `ras_mismatch` — прибыль с начала года по релизу против формы; строки формы 0409102 сравнивают
    прибыль месяца: у релиза без месячного ряда она — разность нарастающих."""
    store = Store(tmp_path)
    at = "2026-09-25T07:00:00+00:00"
    for m, release, form in (("2026M06", 88.2, 88.25), ("2026M07", 107.3, 107.35), ("2026M08", 131.8, 131.77)):
        store.upsert("ops.release.np_ytd", [Point(m, release, at)])
        store.upsert("cbr.f102.ni_ytd", [Point(m, form, at)])
    months = ["2026M06", "2026M07", "2026M08"]
    assert not release_watch.mismatch_flag(store, months, prefix="ops.release.")["raised"]
    rows = release_watch.form102_rows(store, months, prefix="ops.release.")
    assert [r["month"] for r in rows] == ["2026M07", "2026M08"]          # у июня нет соседнего месяца формы
    assert rows[1]["ni"] == pytest.approx(24.42) and rows[1]["release_ni"] == pytest.approx(24.5)
    assert rows[1]["diff"] == pytest.approx(-0.08) and rows[1]["ok"] and rows[1]["first_seen"] == at
    assert release_watch.release_month_profit(store, "2026M06", "ops.release.") is None
    store.upsert("ops.release.np_ytd", [Point("2026M08", 135.0, "2026-09-26T07:00:00+00:00")])
    flag = release_watch.mismatch_flag(store, months, prefix="ops.release.")
    assert flag["raised"] and "135.0 против формы 0409102 131.8" in flag["detail"]
    assert not release_watch.mismatch_flag(store, months)["raised"]      # ряды другого релиза пусты


# ------------------------------------------------------------------ такт дозора

def test_release_watch_tact_skips_ordinary_days_and_reports_what_wakes(monkeypatch, tmp_path, capsys):
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    assert collect.run_mode("release-watch", store, date(2026, 10, 23), getter=FakeGetter()) == 0
    assert "не день дозора" in capsys.readouterr().out and store.read_state(collect.REPORT_FILE) is None
    # день МСФО: новости и документы эмитента; принятый месячный релиз выпуск не будит, документы — будят
    store.write_state(issuer_docs.INDEX_FILE, {"https://cdn.tbank-online.com/static/documents/old.pdf": {
        "first_seen": None, "note": issuer_docs.NOTE_BEFORE_START, "versions": []}})
    code = collect.run_mode("release-watch", store, date(2026, 11, 2),
                            getter=FakeGetter(moment="2026-11-02T07:05:00+00:00"))
    out = capsys.readouterr().out
    report = store.read_state(collect.REPORT_FILE)
    assert set(report["sources"]) == {"news", "issuer_docs", "release_watch"} and code == report["code"]
    assert report["release_watch"]["accepted"] == []
    kinds = {key.split(":", 1)[0] for key in report["ifrs_candidates"]}
    assert kinds == {"ifrs_press", "ifrs_statements", "ifrs_presentation", "dividend_recommendation", "meeting_minutes"}
    assert not any(k.startswith("ops_release") for k in report["ifrs_candidates"])
    # сентябрьский релиз принят в ряды в этом же такте — и выпуск не будит
    assert "release-watch" in out and "принят месячный релиз 2026M09 (выпуск не будит)" in out
    month = next(m for m in report["release_watch"]["months"] if m["month"] == "2026M09")
    assert month["month_accepted"] and store.load("ops.release.np_ytd").value_as_of("2026M09") == 150.1
    assert store.load("ops.release.loans_gross").first_seen("2026M09")              # момент приёма — в ряду
