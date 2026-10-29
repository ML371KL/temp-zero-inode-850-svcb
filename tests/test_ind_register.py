"""Реестр дивидендов по кварталам прибыли: источники, период записи брокера, статус, тревога по календарю книги.

Числа и даты — заглушки тестов в формате состояния сборщиков (`tinvest/dividends.json`, `news/items.json`,
`manual/dividends.json`).
"""

from __future__ import annotations

import json
import shutil
from datetime import date

import pytest

from indicators import collect, config, outputs, register, sources
from indicators.store import Store
from tests.support_ind import FIX, FakeGetter, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта

CFG = {"dividends": {"period_rule": "quarterly", "record_lag_quarters": 2, "dps_tolerance": 0.005,
                     "news_kinds": {"interfax": "Интерфакс", "tass": "ТАСС"}}}
SPLITS = [{"date": "2026-04-15", "first_trade_date": "2026-04-17", "factor": 10.0}]
CALENDAR = {"frequency": "quarterly", "decision_lag_quarters": {"1": 2, "2": 2, "3": 1, "4": 2},
            "first_period": "2026Q3"}
TEMPLATE = "нет записи реестра {label} к сроку решения ({end}): {detail} — внести `record-dividend`"
LABELS = {"1": "за первый квартал {year} года", "2": "за полугодие {year} года",
          "3": "за девять месяцев {year} года", "4": "за {year} год"}


def _broker(store, *rows):
    store.write_state("tinvest/dividends.json", {"by_ticker": {"T": [
        {"year": None, "period": None, "dps": dps, "status": "declared", "record_date": record, "ex_date": record,
         "last_buy_date": last_buy, "pay_date": pay, "sources": ["T-Invest"]} for dps, record, last_buy, pay in rows]}})


def _doc(store, period, status, dps, **kw):
    return register.record_manual(store, year=None, period=period, dps=dps, status=status,
                                  source="документ, sha256 0123456789ab", origin="issuer_docs", **kw)


def _build(store, today, **kw):
    return register.build_full(store, ticker="T", today=today, cfg=CFG, splits=SPLITS, **kw)


def test_issuer_document_is_the_first_source_and_the_broker_checks_it(tmp_path):
    """Документ эмитента задаёт период, DPS и даты; запись брокера с той же датой реестра получает его период
    и становится вторым источником. Размер на акцию у брокера — в нынешних акциях и до дробления: сборщик
    его не делит; делит — только по настройке, когда брокер отдаёт размер как объявлен."""
    store = Store(tmp_path)
    _doc(store, "2026Q2", "recommended", 4.7, decided_date="2026-08-11")
    _doc(store, "2026Q2", "recommended", 4.7, record_date="2026-10-12", pay_date="2026-10-26", decided_date="2026-09-09",
         label="за полугодие 2026 года")
    _doc(store, "2026Q2", "declared", 4.7, record_date="2026-10-12", pay_date="2026-10-26", decided_date="2026-10-01",
         label="за полугодие 2026 года")
    _doc(store, "2025Q3", "declared", 3.6, record_date="2026-01-08", pay_date="2026-01-23", decided_date="2025-12-25")
    _broker(store, (4.7, "2026-10-12", "2026-10-09", "2026-10-26"), (3.6, "2026-01-08", "2026-01-06", "2026-01-23"))
    rows, loose = _build(store, date(2026, 10, 7))
    assert loose == [] and [r["period"] for r in rows] == ["2025Q3", "2026Q2"]
    new = rows[1]
    assert {k: new[k] for k in register.KEEP} == {
        "year": 2026, "period": "2026Q2", "label": "за полугодие 2026 года", "dps": 4.7, "status": "declared",
        "record_date": "2026-10-12", "last_buy_date": "2026-10-09", "ex_date": "2026-10-12", "pay_date": "2026-10-26",
        "decided_date": "2026-10-01", "recommended_date": "2026-08-11", "sources": ["T-Invest", "документ эмитента"]}
    assert register.usable(new) and new["notes"] == []
    old = rows[0]
    assert (old["dps"], old["status"], old["year"]) == (3.6, "paid", 2025)
    assert old["evidence"][0] == {"source": "T-Invest", "dps": 3.6, "record_date": "2026-01-08"}
    assert old["sources"] == ["T-Invest", "документ эмитента"] and old["notes"] == []     # брокера не делили
    # брокер, который отдаёт размер как объявлен (36 ₽ до дробления): деление включает настройка
    raw = Store(tmp_path / "raw")
    _doc(raw, "2025Q3", "declared", 3.6, record_date="2026-01-08", pay_date="2026-01-23", decided_date="2025-12-25")
    _broker(raw, (36.0, "2026-01-08", "2026-01-06", "2026-01-23"))
    declared = {**CFG, "tinvest": {"dividends_split_adjusted": False}}
    assert not register.broker_split_adjusted(declared) and register.broker_split_adjusted(CFG)
    got = register.build(raw, ticker="T", today=date(2026, 10, 7), cfg=declared, splits=SPLITS)[0]
    assert got["evidence"][0] == {"source": "T-Invest", "dps": 3.6, "record_date": "2026-01-08"} and got["notes"] == []
    wrong = register.build(raw, ticker="T", today=date(2026, 10, 7), cfg=CFG, splits=SPLITS)[0]
    assert wrong["sources"] == ["документ эмитента"] and "36.0 ₽" in wrong["notes"][0]   # расхождение названо
    assert register.build(store, ticker="T", today=date(2026, 10, 7), cfg=CFG, splits=SPLITS, since="2026-05-01") == [new]
    paid = _build(store, date(2026, 10, 27))[0][1]
    assert paid["status"] == "paid"


def test_only_a_recommendation_stays_recommended_until_the_record_date(tmp_path):
    store = Store(tmp_path)
    _doc(store, "2026Q3", "recommended", 4.9, decided_date="2026-11-19")
    rec = _build(store, date(2026, 11, 20))[0][0]
    assert (rec["status"], rec["sources"], rec["decided_date"], rec["recommended_date"]) == (
        "recommended", ["документ эмитента"], None, "2026-11-19")
    assert not register.usable(rec) and rec["record_date"] is None
    # брокер назвал дату реестра: до неё запись остаётся рекомендацией, с неё — объявлена, но источник один
    _doc(store, "2026Q3", "recommended", 4.9, record_date="2026-12-28", pay_date="2027-01-15", decided_date="2026-12-04")
    _broker(store, (4.9, "2026-12-28", "2026-12-25", "2027-01-15"))
    before = _build(store, date(2026, 12, 20))[0][0]
    assert before["status"] == "recommended" and before["sources"] == ["T-Invest", "документ эмитента"]
    after = _build(store, date(2026, 12, 28))[0][0]
    assert after["status"] == "declared" and after["sources"] == ["T-Invest"] and not register.usable(after)
    assert _build(store, date(2027, 1, 15))[0][0]["status"] == "paid"


def test_operator_record_is_a_second_source(tmp_path):
    """Документ эмитента и ручная запись оператора — разные источники: оператор может закрыть период сам."""
    store = Store(tmp_path)
    _doc(store, "2026Q2", "declared", 4.7, record_date="2026-10-12", decided_date="2026-10-01")
    register.record_manual(store, year=None, period="2026Q2", dps=4.7, status="declared", record_date="2026-10-12",
                           source="сообщение о существенном факте")
    rec = _build(store, date(2026, 10, 7))[0][0]
    assert rec["sources"] == ["документ эмитента", "ручная запись"] and register.usable(rec)


def test_sources_that_disagree_are_named_in_notes(tmp_path):
    store = Store(tmp_path)
    _doc(store, "2026Q2", "declared", 4.7, record_date="2026-10-12", decided_date="2026-10-01")
    _broker(store, (47.0, "2026-10-12", "2026-10-09", "2026-10-26"))       # брокер не пересчитал на дробление
    store.write_state("news/items.json", {"items": {"https://www.interfax.ru/business/1": {
        "kind": "interfax", "topic": "dividend", "published": "2026-10-02T13:35:00+03:00",
        "title": "Собрание акционеров компании утвердило дивиденды за полугодие 2026 года в размере 4,7 рубля на акцию",
        "text": "Реестр акционеров закроется 12 октября."}}})
    cfg = {"dividends": {**CFG["dividends"], "period_patterns": config.sources()["dividends"]["period_patterns"]}}
    rows, loose = register.build_full(store, ticker="T", today=date(2026, 10, 7), cfg=cfg, splits=SPLITS)
    rec = rows[0]
    assert loose == [] and rec["dps"] == 4.7 and rec["sources"] == ["Интерфакс", "документ эмитента"]
    assert rec["notes"] == ["T-Invest: 47.0 ₽, реестр 2026-10-12 — не совпадает с 4.7 ₽, 2026-10-12"]
    assert rec["last_buy_date"] is None and rec["pay_date"] is None        # даты несогласного источника не берутся


def test_period_of_a_broker_record(tmp_path):
    """Период записи брокера: (1) по записи с той же датой реестра; (2) лаг — только когда запись в квартале
    даты реестра одна без пары и период свободен; (3) иначе запись не входит в реестр и названа."""
    docs = [{"period": "2026Q2", "dps": 4.7, "record_date": "2026-10-12"},
            {"period": "2026Q3", "dps": 4.9, "record_date": "2026-12-28"}]
    oct_row = {"dps": 4.7, "record_date": "2026-10-12"}
    dec_row = {"dps": 4.9, "record_date": "2026-12-28"}
    by, loose = register.assign_periods([oct_row, dec_row], docs, lag=2)
    assert by == {"2026Q2": [oct_row], "2026Q3": [dec_row]} and loose == []
    # документов нет: два решения ложатся в один квартал — лаг дал бы обоим период 2К, запись не присваивается
    by, loose = register.assign_periods([oct_row, dec_row], [], lag=2)
    assert by == {} and loose == [oct_row, dec_row]
    aug_row = {"dps": 4.6, "record_date": "2026-08-10"}
    by, loose = register.assign_periods([aug_row], [], lag=2)
    assert by == {"2026Q1": [aug_row]} and loose == []                      # одна запись квартала: реестр − 2 квартала
    by, loose = register.assign_periods([aug_row], [{"period": "2026Q1", "dps": 4.6, "record_date": "2026-08-11"}], lag=2)
    assert by == {} and loose == [aug_row]                                  # период занят другой записью
    assert register.assign_periods([aug_row], [], lag=None) == ({}, [aug_row])   # без настройки лага правила (2) нет
    store = Store(tmp_path)
    _doc(store, "2026Q2", "declared", 4.7, record_date="2026-10-12", decided_date="2026-10-01")
    _broker(store, (4.7, "2026-10-12", "2026-10-09", "2026-10-26"), (4.9, "2026-12-28", "2026-12-25", "2027-01-15"),
            (5.0, "2026-12-30", "2026-12-29", "2027-01-18"))
    rows, loose = _build(store, date(2026, 12, 29))
    assert [r["period"] for r in rows] == ["2026Q2"]
    assert loose == ["брокер: 4.9 ₽, реестр 2026-12-28 — период не определён",
                     "брокер: 5.0 ₽, реестр 2026-12-30 — период не определён"]
    assert rows[0]["notes"] == loose                       # дата реестра записи — в том же квартале
    assert register.note_date(loose[0]) == "2026-12-28"


def test_annual_key_is_the_default(tmp_path):
    """Без `dividends.period_rule` ключ записи — год прибыли: одна запись на год, период пуст."""
    store = Store(tmp_path)
    store.write_state("tinvest/dividends.json", {"by_ticker": {"T": [
        {"year": 2025, "dps": 30.0, "status": "declared", "record_date": "2026-07-20", "ex_date": "2026-07-20",
         "last_buy_date": "2026-07-17", "pay_date": "2026-08-03", "sources": ["T-Invest"]}]}})
    register.record_manual(store, year=2025, dps=30.0, status="declared", record_date="2026-07-20",
                           decided_date="2026-06-30", source="протокол собрания")
    rec = register.build(store, ticker="T", today=date(2026, 7, 21), cfg={"dividends": {}})[0]
    assert (rec["year"], rec["period"], rec["status"], rec["sources"]) == (2025, None, "declared",
                                                                         ["T-Invest", "ручная запись"])
    text = register.alarm([], today=date(2026, 7, 21), agm_quarter=2, template="нет записи за {year} год ({end}): {detail}",
                          period_labels=LABELS)
    assert text == "нет записи за 2025 год (2026-06-30): записей нет"
    assert register.alarm([rec], today=date(2026, 7, 21), agm_quarter=2, template="x") is None
    assert register.alarm([], today=date(2026, 6, 30), agm_quarter=2, template="x") is None       # срок не прошёл
    assert register.alarm([], today=date(2026, 7, 21)) is None                                    # квартала нет — нет срока


def test_manual_record_validation(tmp_path):
    store = Store(tmp_path)
    ok = register.record_manual(store, year=None, period="2026Q3", label=" за девять месяцев 2026 года ", dps=4.9,
                                status="recommended", source="пресс-релиз МСФО", decided_date="2026-11-19")
    assert (ok["year"], ok["period"], ok["label"], ok["origin"]) == (2026, "2026Q3", "за девять месяцев 2026 года", None)
    for kw, words in (({"period": "2026-Q3"}, "не квартал"), ({"period": "2026Q3", "year": 2025}, "не совпадает"),
                      ({"year": None}, "год прибыли"), ({"year": 2026, "status": "declared"}, "дата реестра"),
                      ({"year": 2026, "dps": 0.0}, "положительный"), ({"year": 2026, "source": " "}, "ссылка"),
                      ({"year": 2026, "status": "paid"}, "статус"),
                      ({"year": 2026, "decided_date": "19.11.2026"}, "не дата")):
        args = {"year": 2026, "dps": 4.9, "status": "recommended", "source": "документ", **kw}
        with pytest.raises(register.RegisterError, match=words):
            register.record_manual(store, **args)
    assert len(register.manual_records(store)) == 1


def test_alarm_follows_the_quarterly_calendar_of_the_book():
    """Тревога: открытый квартал прибыли (позже последнего закрытого по фактам), чей квартал решения по карте
    лагов кончился, а годной записи нет. Закрытые кварталы и кварталы, срок которых не прошёл, молчат."""
    def alarm(records, today, **kw):
        return register.alarm(records, today=today, calendar=CALENDAR, closed_through="2025Q4", template=TEMPLATE,
                              period_labels=LABELS, **kw)

    assert register.decision_quarter("2026Q1", CALENDAR) == "2026Q3"          # 1К + 2
    assert register.decision_quarter("2026Q2", CALENDAR) == register.decision_quarter("2026Q3", CALENDAR) == "2026Q4"
    assert register.decision_quarter("2026Q4", CALENDAR) == "2027Q2"
    assert register.decision_quarter("2025Q4", CALENDAR) == "2026Q3"          # не раньше первого квартала сетки
    assert register.decision_quarter("2025Q4", {"decision_lag_quarters": 2}) == "2026Q2"
    assert alarm([], date(2026, 9, 30)) is None                               # квартал решения за 1К ещё идёт
    text = alarm([], date(2026, 10, 1))
    assert text == ("нет записи реестра за первый квартал 2026 года к сроку решения (2026-09-30): записей нет — "
                    "внести `record-dividend`")
    paid = {"period": "2026Q1", "status": "paid", "dps": 4.6, "sources": ["T-Invest"]}
    assert alarm([paid], date(2026, 10, 1)) is None
    one = {"period": "2026Q2", "status": "declared", "dps": 4.7, "sources": ["документ эмитента"],
           "label": "за полугодие 2026 года"}
    late = alarm([paid, one], date(2027, 1, 5))
    assert late.count("нет записи реестра") == 2                              # за 2К (один источник) и за 3К
    assert "за полугодие 2026 года к сроку решения (2026-12-31): declared 4.7 ₽ (документ эмитента)" in late
    assert "за девять месяцев 2026 года к сроку решения (2026-12-31): записей нет" in late
    two = dict(one, sources=["документ эмитента", "T-Invest"])
    q3 = {"period": "2026Q3", "status": "paid", "dps": 4.9, "sources": ["T-Invest"]}
    assert alarm([paid, two, q3], date(2027, 1, 5)) is None                   # 4К: решение ждут во 2К следующего года
    assert alarm([paid, two, q3], date(2027, 7, 1)).startswith("нет записи реестра за 2026 год к сроку решения (2027-06-30)")
    assert register.alarm([], today=date(2027, 1, 5), calendar=CALENDAR, closed_through=None, template=TEMPLATE) is None
    with pytest.raises(register.RegisterError, match="collector_alarm"):
        register.alarm([], today=date(2026, 10, 1), calendar=CALENDAR, closed_through="2025Q4")
    with pytest.raises(register.RegisterError, match="незнакомое поле"):
        register.alarm([], today=date(2026, 10, 1), calendar=CALENDAR, closed_through="2025Q4", template="{nope}")
    with pytest.raises(register.RegisterError, match="decision_lag_quarters"):
        register.alarm([], today=date(2026, 10, 1), calendar={"frequency": "quarterly"}, closed_through="2025Q4",
                       template=TEMPLATE)
    assert register.label_of("2026Q2", None, None, LABELS) == "за полугодие 2026 года"
    assert register.label_of("2026Q2", None, "за второй квартал 2026 года", LABELS) == "за второй квартал 2026 года"
    assert register.label_of(None, 2025, None, LABELS) == "за 2025 год" and register.label_of("2026Q2", None, None, None) == "2026Q2"


def test_a_paid_record_of_the_facts_register_closes_the_period():
    """Стартовый реестр фактов (его записи читает и ядро): период с записью `paid` для тревоги закрыт и без
    записей сборщиков; запись `declared` период не закрывает — выплату и второй источник подтверждают сборщики."""
    seed = [{"year": 2026, "period": "2026Q1", "status": "paid", "dps": 4.6},
            {"year": 2026, "period": "2026Q2", "status": "declared", "dps": 4.7}]

    def alarm(today, seed=()):
        return register.alarm([], today=today, calendar=CALENDAR, closed_through="2025Q4", template=TEMPLATE,
                              period_labels=LABELS, seed=seed)

    assert register.seed_closed(seed, quarterly=True) == {"2026Q1"} and register.seed_closed((), quarterly=True) == set()
    assert alarm(date(2026, 10, 1)).startswith("нет записи реестра за первый квартал 2026 года")
    assert alarm(date(2026, 10, 1), seed) is None
    late = alarm(date(2027, 1, 5), seed)
    assert late.count("нет записи реестра") == 2 and "за первый квартал" not in late     # за 2К и за 3К
    assert "за полугодие 2026 года" in late and "за девять месяцев 2026 года" in late
    # годовой календарь: год закрывает запись `paid` без квартала
    annual = dict(today=date(2026, 7, 21), agm_quarter=2, template="нет записи за {year} год")
    assert register.alarm([], **annual) == "нет записи за 2025 год"
    assert register.alarm([], **annual, seed=[{"year": 2025, "status": "paid", "dps": 30.0}]) is None
    assert register.alarm([], **annual, seed=[{"year": 2025, "status": "declared", "dps": 30.0}]) == "нет записи за 2025 год"
    assert register.alarm([], **annual, seed=[{"year": 2025, "period": "2025Q1", "status": "paid"}]) is not None
    assert register.seed_closed([{"year": "x", "status": "paid"}, {"status": "paid"}], quarterly=False) == set()


def _facts_with_a_seed(tmp_path, seed):
    """Копия фактов-заглушек с узлом `register_seed` (значения — узлами `{v, …}`, как пишет сборщик фактов)."""
    facts = tmp_path / "facts"
    shutil.copytree(FIX / "facts", facts)
    path = facts / "dividends.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["register_seed"] = seed
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return facts


def test_the_first_tact_on_an_empty_state_does_not_alarm_about_a_dividend_the_facts_have_paid(monkeypatch, tmp_path):
    """Первый запуск: каталог состояния пуст, документ о решении старше окна первого запуска, брокерского
    календаря без токена нет. Выплаченный дивиденд стартового реестра фактов тревогой не становится: шаг
    реестра — код 0, флаг выходов опущен, сборке о тревоге сборщиков не сообщается."""
    use_fixtures(monkeypatch, tmp_path, token=False)
    seed = [{"year": 2026, "period": "2026Q1", "label": "за первый квартал 2026 года",
             "dps": {"v": 4.6, "src": "протокол собрания", "calc": "дивиденд на акцию, ₽"}, "status": "paid",
             "decided_date": "2026-07-30", "record_date": "2026-08-10", "pay_date": "2026-08-24",
             "sources": ["manual: документ эмитента"]},
            {"year": 2026, "period": "2026Q2", "dps": {"v": 4.7}, "status": "declared", "record_date": "2026-10-12"}]
    monkeypatch.setattr(config, "FACTS_DIR", _facts_with_a_seed(tmp_path, seed))
    assert [(r["period"], r["status"], r["dps"]) for r in config.register_seed()] == [
        ("2026Q1", "paid", 4.6), ("2026Q2", "declared", 4.7)]
    state = tmp_path / "state"
    today = date(2026, 10, 8)
    res = collect.register_check(collect.context(Store(state), today))
    assert res.status == "ok" and res.reasons == [] and res.data["records"] == []
    assert sources.verdict([res]).code == 0
    out = outputs.release_inputs(tickers=["T"], state_dir=state, today=today)
    assert out.flags["dividend_register"] == {"raised": False, "detail": ""}
    # такт без токена и с пустым состоянием: реестр кода 3 не даёт и в список тревог сборке не попадает
    code = collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(), today=today)
    got = outputs.release_inputs(tickers=["T"], state_dir=state, today=today).collector
    assert code == 0 and got["alarm"] == [] and got["sources"]["register"] == "ok"
    # срок решения за 2К прошёл, а в стартовом реестре оно только объявлено — тревога, как и без него
    late = collect.register_check(collect.context(Store(state), date(2027, 1, 11)))
    [text] = [x for x in late.reasons if "нет записи реестра" in x]
    assert text.count("нет записи реестра") == 2 and "за первый квартал" not in text
    assert "за полугодие 2026 года" in text and "за девять месяцев 2026 года" in text
    # без узла в фактах — прежнее поведение: тревога о первом открытом квартале
    monkeypatch.setattr(config, "FACTS_DIR", FIX / "facts")
    assert config.register_seed() == []
    bare = collect.register_check(collect.context(Store(tmp_path / "s2"), today))
    assert any(x.startswith("нет записи реестра за первый квартал 2026 года") for x in bare.reasons)


def test_the_book_of_the_repository_is_quiet_on_its_own_date_with_an_empty_register():
    """Книга и факты репозитория: на дату книги у каждого открытого квартала прибыли, чей срок решения прошёл,
    в стартовом реестре фактов есть выплаченная запись — выпуск с пустого каталога состояния тревоги реестра
    не несёт. Дата — дата книги, не «сегодня»: тест не зависит от дня прогона."""
    book_date = config.book_value("meta.date")
    if not book_date or not config.facts_file("dividends"):
        pytest.skip("нет книги или фактов о дивидендах")
    today = date.fromisoformat(str(book_date)[:10])
    for rec in config.register_seed():
        assert rec.get("status") in ("paid", "declared", "recommended") and (rec.get("period") or rec.get("year")), rec
        assert not isinstance(rec.get("dps"), dict), "узел факта развёрнут в значение"
    assert register.alarm_from_book([], today) is None


def test_register_check_of_the_tact_reads_the_book_and_the_facts(monkeypatch, tmp_path):
    """Шаг такта: календарь и подписи — из книги, последний закрытый квартал — из фактов (`dividends.history`
    с решением не позже даты фактов), дробления — из фактов."""
    use_fixtures(monkeypatch, tmp_path)
    assert config.closed_through() == "2025Q4"            # решение за 1К2026 принято позже даты фактов
    assert config.dividend_calendar()["first_period"] == "2026Q3"
    store = Store(tmp_path / "state")
    _broker(store, (4.6, "2026-08-10", "2026-08-07", "2026-08-24"), (5.0, "2026-10-12", "2026-10-09", "2026-10-26"),
            (5.1, "2026-11-12", "2026-11-11", "2026-11-26"))
    _doc(store, "2026Q2", "declared", 4.7, record_date="2026-10-12", decided_date="2026-10-01")
    res = collect.register_check(collect.context(store, date(2026, 10, 15)))
    # запись брокера за август получила период 1К по лагу и закрыла его (выплачена); у 2К DPS разошёлся
    assert [(r["period"], r["status"]) for r in res.data["records"]] == [("2026Q1", "paid"), ("2026Q2", "declared")]
    assert res.status == "degraded" and not res.retry
    assert any("реестр 2026Q2: T-Invest: 5.0 ₽" in x for x in res.reasons)
    assert "реестр: брокер: 5.1 ₽, реестр 2026-11-12 — период не определён" in res.reasons
    assert not any("нет записи реестра" in x for x in res.reasons)            # срок решения за 2К — конец года
    late = collect.register_check(collect.context(store, date(2027, 1, 11)))
    assert any(x.startswith("нет записи реестра за полугодие 2026 года к сроку решения (2026-12-31)") for x in late.reasons)
    # без фактов о решениях срок не проверяется — и об этом сказано
    monkeypatch.setattr(config, "FACTS_DIR", tmp_path / "нет")
    blind = collect.register_check(collect.context(Store(tmp_path / "s2"), date(2027, 1, 11)))
    assert blind.reasons == ["реестр: в фактах нет решения о дивиденде не позже даты фактов книги — срок решения "
                             "не проверяется"]
    assert (FIX / "facts/dividends.json").exists()
