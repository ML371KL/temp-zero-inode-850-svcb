"""Документы эмитента: список «дата · заголовок · ссылка», вид и период по заголовку, личность документа,
момент первого появления, разбор месячного релиза и документов о дивиденде, хосты и запасные хосты.

Фикстуры — сочинённые страница пресс-релизов, ответы двери и тексты документов в формате источника
(`tests/fixtures/ind/issuer_docs/`); «PDF» — текст, чтение текстового слоя подменено (`support_ind.pdf_text`).
"""

from __future__ import annotations

from datetime import date

import pytest

from indicators import config, http, issuer_docs, register
from indicators.sources import DEGRADED, FAILED, IRRECOVERABLE, OK, Context, verdict
from indicators.store import PROTECTED_SOURCES, Store
from tests.support_ind import FIX, FakeGetter, pdf_text, use_fixtures, use_form_settings

pytestmark = pytest.mark.tact  # быстрые тесты такта

MONTHLY = "ops_release"
T1 = "2026-10-26T07:00:00+00:00"
TODAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def _form_settings(monkeypatch):
    """Тесты общего каркаса — на настройках и истории формы образца (`tests/fixtures/ind/form/`): ветви, которыми
    настройки этой копии не пользуются; настройки копии проверяет `tests/test_ind_svcb.py`."""
    use_form_settings(monkeypatch)


def _cfg():
    return config.sources()["issuer_docs"]


def _text(name):
    return "\n".join(pdf_text((FIX / "issuer_docs" / name).read_bytes()))


def _ctx(store, getter, today=TODAY):
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter)


def _started(store):
    """Сборщик уже работал: первый запуск историю не качает, а здесь нужны все документы списка."""
    store.write_state(issuer_docs.INDEX_FILE, {"https://cdn.tbank-online.com/static/documents/old.pdf": {
        "first_seen": None, "note": issuer_docs.NOTE_BEFORE_START, "versions": []}})


# ------------------------------------------------------------------ список, вид, период

def test_press_page_and_door_give_date_title_link():
    rows = issuer_docs.parse_press((FIX / "issuer_docs/press_page.html").read_text(encoding="utf-8"))
    assert [r["date"] for r in rows] == ["2026-10-23", "2026-10-14", "2026-08-11"]
    assert rows[0]["title"] == "Операционные результаты Т-Технологий за сентябрь 2026 года"    # типографика снята
    assert rows[0]["url"].startswith("https://cdn.tbank-online.com/static/documents/aaaa0001-")
    assert issuer_docs.parse_press("<html><body><p>нет списка</p></body></html>") == []
    door = issuer_docs.parse_door((FIX / "issuer_docs/door_quarterly.json").read_text(encoding="utf-8"))
    assert [d["title"] for d in door][0] == "Пресс-релиз МСФО за II кв. 2026"
    assert door[0]["folder"] == "2026 / II кв. 2026" and door[0]["published_at"] == "2026-08-11T07:00:15.301Z"
    assert issuer_docs.parse_door('{"response": []}') == []
    with pytest.raises(ValueError):
        issuer_docs.parse_door('{"error": "нет раздела"}')


@pytest.mark.parametrize("title, kind, period", [
    ("Операционные результаты Т‑Технологий за август 2026 года", "ops_release", "2026M08"),
    ("Операционные результаты за январь 2026", "ops_release", "2026M01"),
    ("Операционные результаты за декабрь и 12 месяцев 2025 года", "ops_release", "2025M12"),
    ("Финансовые результаты по МСФО за II квартал 2026 года", "ifrs_press", "2026Q2"),
    ("Финансовые результаты по МСФО за IV квартал и 2025 год", "ifrs_press", "2025Q4"),
    ("Финансовые результаты по МСФО за III квартал и девять месяцев 2025 года", "ifrs_press", "2025Q3"),
    ("Пресс‑релиз МСФО за I кв. 2026", "ifrs_press", "2026Q1"),
    ("Консолидированная финансовая отчетность, МСФО, II кв. 2026", "ifrs_statements", "2026Q2"),
    ("Презентация МСФО за III кв. 2025", "ifrs_presentation", "2025Q3"),
    ("Databook за II кв. 2026", "databook", "2026Q2"),
    ("Рекомендации Совета директоров МКПАО «Т‑Технологии» по размеру дивиденда по акциям МКПАО «Т‑Технологии» "
     "и порядку его выплаты", "dividend_recommendation", None),
    ("Рекомендации совета директоров по размеру дивиденда по акциям общества и порядку его выплаты",
     "dividend_recommendation", None),
    ("Протокол № 16 от 02.10.2026", "meeting_minutes", None),
    ("Совет директоров Т‑Технологий утвердил параметры сделки по покупке сервиса «Пример»", "deal", None),
    ("Проекты решений по вопросам повестки дня", None, None),
    ("Запись звонка МСФО за II кв. 2026", None, None),
])
def test_kind_and_period_come_from_the_title(title, kind, period):
    assert issuer_docs.classify(title, _cfg(), monthly_kind=MONTHLY) == {"kind": kind, "period": period}


def test_identity_is_kind_period_and_hash():
    a = issuer_docs.document_key("ops_release", "2026M08", "ab" * 32)
    assert a == "ops_release:2026M08:abababababab" and issuer_docs.document_key(None, None, "cd" * 32) == "other:-:cdcdcdcdcdcd"
    assert issuer_docs.title_key("Пресс‑релиз МСФО") == issuer_docs.title_key("пресс-релиз мсфо")
    assert issuer_docs.normalize("Т‑Технологий за&nbsp;август") == "Т-Технологий за август"


def test_hosts_rewrite_and_fallback():
    cfg = _cfg()
    door = "https://cdn.tbank.ru/static/documents/x.pdf"
    assert issuer_docs.rewrite_host(door, cfg["host_rewrite"]) == "https://cdn.tbank-online.com/static/documents/x.pdf"
    assert issuer_docs.rewrite_host("https://example.org/x.pdf", cfg["host_rewrite"]) == "https://example.org/x.pdf"
    work = "https://cfg.tbank-online.com/documents/api?section=a"
    assert issuer_docs.fallback_urls(work, cfg["fallback_hosts"]) == ["https://cfg.tbank.ru/documents/api?section=a"]
    assert issuer_docs.fallback_urls(cfg["press_page"], cfg["fallback_hosts"]) == []      # у сайта запасного хоста нет


# ------------------------------------------------------------------ разбор текста

def test_monthly_release_tables_and_the_profit_phrase():
    got = issuer_docs.parse_ops_release(_text("ops_2026-09.pdf.txt"), _cfg()["ops_release"])
    assert got == {"clients_total": 57.3, "clients_active": 35.2, "loans_gross": 3700.0, "loans_retail": 2700.0,
                   "loans_business": 1000.0, "funds_total": 4200.0, "funds_retail": 3300.0, "funds_business": 900.0,
                   "np_ytd": 150.1, "cap_base": 470.0, "cap_main": 598.0, "cap_total": 700.0,
                   "n1_1": pytest.approx(0.089), "n1_2": pytest.approx(0.112), "n1_0": pytest.approx(0.131)}
    assert set(got) == set(config.sources()["monthly"]["metrics"])
    # показатель «без учёта разовых…» — не прибыль по РСБУ: в ряд не идёт
    excl = _text("ops_2026-09.pdf.txt").replace("составила 150,1 млрд\nруб. Прибыль по РСБУ",
                                                "составила 9 млрд руб. без учета разовых резервов. Прибыль по РСБУ")
    assert "np_ytd" not in issuer_docs.parse_ops_release(excl, _cfg()["ops_release"])
    # значение между частями метки норматива и рост тремя знаками
    odd = ("1. КЛЮЧЕВЫЕ ОПЕРАЦИОННЫЕ ПОКАЗАТЕЛИ\nБазовый капитал, млрд руб. 1 024 121%\n"
           "Достаточность общего капитала Н1.0 (мин\n13,0% 1,8 п.п.\n8.0%)\n")
    assert issuer_docs.parse_ops_release(odd, _cfg()["ops_release"]) == {"cap_base": 1024.0, "n1_0": pytest.approx(0.13)}
    assert issuer_docs.parse_ops_release("в тексте нет таблиц", _cfg()["ops_release"]) == {}


def test_dividend_documents_give_period_amount_and_dates():
    patterns = config.sources()["dividends"]["period_patterns"]
    rec = issuer_docs.parse_dividend_document(_text("recommendation_2026Q2.pdf.txt"), "dividend_recommendation",
                                              period_patterns=patterns)
    assert rec == {"status": "recommended", "period": "2026Q2", "label": "за полугодие 2026 года", "dps": 4.7,
                   "record_date": "2026-10-12", "pay_date": "2026-10-26", "meeting_date": "2026-10-01",
                   "phrase": rec["phrase"]}
    done = issuer_docs.parse_dividend_document(_text("minutes_16.pdf.txt"), "meeting_minutes", period_patterns=patterns)
    assert (done["status"], done["period"], done["dps"], done["record_date"]) == ("declared", "2026Q2", 4.7, "2026-10-12")
    # заочное собрание: день решения — конец приёма бюллетеней, а не дата нормативного акта из текста протокола
    assert done["meeting_date"] == "2026-10-01"
    by_the_act = _text("minutes_16.pdf.txt").replace("Дата окончания приема 01 октября 2026 года (включительно)", "")
    assert issuer_docs.parse_dividend_document(by_the_act, "meeting_minutes", period_patterns=patterns)["meeting_date"] is None
    other = issuer_docs.parse_dividend_document(_text("minutes_15.pdf.txt"), "meeting_minutes", period_patterns=patterns)
    assert other is None                                                   # протокол не о дивиденде
    not_adopted = _text("minutes_16.pdf.txt").replace("РЕШЕНИЕ ПО ВОПРОСУ № 1 ПОВЕСТКИ ДНЯ ПРИНЯТО", "РЕШЕНИЕ НЕ ПРИНЯТО")
    assert issuer_docs.parse_dividend_document(not_adopted, "meeting_minutes", period_patterns=patterns) is None
    press = issuer_docs.parse_dividend_document(_text("ifrs_press_2026Q2.pdf.txt"), "ifrs_press", period_patterns=patterns)
    assert (press["status"], press["period"], press["dps"], press["record_date"]) == ("recommended", "2026Q2", 4.7, None)
    for text, period, dps in (
            ("Выплатить дивиденды по обыкновенным акциям общества за 2025 год в размере 4 (четырех) рублей 50 копеек "
             "на 1 (одну) обыкновенную акцию.", "2025Q4", 4.5),
            ("Выплатить дивиденды по обыкновенным акциям общества за девять месяцев 2024 года в размере 92,5 рубля "
             "(Девяносто два рубля 50 копеек) на одну обыкновенную акцию.", "2024Q3", 92.5),
            ("Выплатить дивиденды по обыкновенным акциям общества за три месяца 2025 года в размере 33 (Тридцать три) "
             "рубля на одну обыкновенную акцию.", "2025Q1", 33.0)):
        got = issuer_docs.parse_dividend_document(text, "dividend_recommendation", period_patterns=patterns)
        assert (got["period"], got["dps"]) == (period, dps), text
    assert issuer_docs.parse_dividend_document("Дивиденды обсуждались.", "ifrs_press", period_patterns=patterns) is None
    assert issuer_docs.parse_dividend_document(_text("minutes_16.pdf.txt"), "deal", period_patterns=patterns) is None
    # сумма из документа с датой раньше дробления — в нынешних акциях; коэффициент и дата — из фактов
    splits = config.splits(FIX / "facts")
    assert issuer_docs.split_adjusted(45.0, "2026-03-19", splits) == 4.5
    assert issuer_docs.split_adjusted(4.5, "2026-04-22", splits) == 4.5 and issuer_docs.split_adjusted(4.5, None, splits) == 4.5


def test_a_document_without_text_needs_a_hand_and_ocr_is_a_switch(monkeypatch):
    monkeypatch.setattr(issuer_docs, "text_pages", pdf_text)
    scan = (FIX / "issuer_docs/scan.pdf.txt").read_bytes()
    cfg = dict(_cfg())
    assert cfg["ocr"] is False
    got = issuer_docs.analyse(scan, MONTHLY, cfg, monthly_kind=MONTHLY)
    assert got["status"] == "needs_manual" and "выключено настройкой" in got["detail"]
    called = []
    monkeypatch.setattr(issuer_docs, "ocr_pages", lambda body: called.append(1) or [_text("ops_2026-09.pdf.txt")])
    on = issuer_docs.analyse(scan, MONTHLY, {**cfg, "ocr": True}, monthly_kind=MONTHLY)
    assert called and on["status"] == "ok" and on["method"].startswith("ocr") and on["numbers"]["loans_gross"] == 3700.0

    def refuses(body):
        raise issuer_docs.NeedsManual("tesseract не установлен")

    monkeypatch.setattr(issuer_docs, "ocr_pages", refuses)
    off = issuer_docs.analyse(scan, MONTHLY, {**cfg, "ocr": True}, monthly_kind=MONTHLY)
    assert off == {"status": "needs_manual", "detail": "tesseract не установлен", "numbers": {}}
    monkeypatch.setattr(issuer_docs, "text_pages", lambda body: (_ for _ in ()).throw(ValueError("битый файл")))
    assert issuer_docs.analyse(b"x", MONTHLY, cfg, monthly_kind=MONTHLY)["status"] == "failed"
    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n" \
          "5\t1\t1\t1\t1\t2\t200\t10\t50\t20\t95\tклиентов\n5\t1\t1\t1\t1\t1\t100\t10\t50\t20\t95\tВсего\n" \
          "5\t1\t1\t1\t2\t1\t100\t40\t50\t20\t95\t57,3\n4\t1\t1\t1\t2\t0\t0\t0\t0\t0\t-1\t\n"
    assert issuer_docs.tsv_lines(tsv) == ["Всего клиентов", "57,3"]


# ------------------------------------------------------------------ сбор

def test_collect_lists_downloads_parses_and_writes_the_first_seen_moment(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    g = FakeGetter(moment=T1)
    r = issuer_docs.collect(_ctx(store, g))
    assert r.status == OK, r.reasons
    index = store.read_state(issuer_docs.INDEX_FILE)
    page = next(u for u in index if "aaaa0001" in u)
    door = next(u for u in index if "bbbb0001" in u)
    assert door.startswith("https://cdn.tbank-online.com/")            # ссылка двери переписана на рабочий хост
    assert index[page]["first_seen"] == index[door]["first_seen"] == T1
    assert (index[page]["kind"], index[page]["period"], index[page]["listed"]) == ("ops_release", "2026M09", "2026-10-23")
    assert index[door]["published_at"] == "2026-10-23T08:00:00.000Z" and index[door]["where"].startswith("door:")
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    ops = [c for c in cands.values() if c["kind"] == "ops_release" and c.get("sha256")]
    # один файл под адресом страницы и двери — один документ: личность — вид, период и хэш содержимого
    assert len(ops) == 1 and sorted(ops[0]["urls"]) == sorted([page, door])
    assert ops[0]["status"] == "ok" and ops[0]["method"] == "text" and ops[0]["month"] == "2026M09"
    assert ops[0]["numbers"]["np_ytd"] == 150.1 and ops[0]["first_seen"] == T1
    kinds = sorted({c["kind"] for c in cands.values()})
    assert kinds == ["deal", "dividend_recommendation", "ifrs_presentation", "ifrs_press", "ifrs_statements",
                     "meeting_minutes", "ops_release"]
    listed = [c for c in cands.values() if c["status"] == issuer_docs.LISTED]
    assert {c["kind"] for c in listed} == {"deal", "ifrs_presentation", "ifrs_statements"}     # замечены, не качаются
    fetched = [c["url"] for c in g.calls if "/static/documents/" in c["url"]]
    assert not any("0005-" in u or "0008-" in u or "0009-" in u or "000a-" in u for u in fetched)
    assert all(u.startswith("https://cdn.tbank-online.com/") for u in fetched)
    assert store.raw_days("issuer_docs") and issuer_docs.SOURCE in PROTECTED_SOURCES and issuer_docs.SOURCE in IRRECOVERABLE
    # документы о дивиденде — записи реестра вида «документ эмитента»: рекомендации и решение собрания
    records = register.manual_records(store)
    assert [(x["period"], x["status"], x["dps"], x["doc_kind"]) for x in records] == [
        ("2026Q2", "recommended", 4.7, "ifrs_press"), ("2026Q2", "recommended", 4.7, "dividend_recommendation"),
        ("2026Q2", "declared", 4.7, "meeting_minutes")]
    assert all(x["origin"] == "issuer_docs" and "sha256" in x["source"] for x in records)
    declared = records[-1]
    assert declared["decided_date"] == "2026-10-01"                 # день собрания — из рекомендации того же периода
    assert (declared["record_date"], declared["pay_date"], declared["label"]) == (
        "2026-10-12", "2026-10-26", "за полугодие 2026 года")
    assert records[0]["decided_date"] == "2026-08-11" and records[0]["record_date"] is None
    # выпуск будят МСФО квартала и документы с рекомендацией или решением; месячный релиз и протокол
    # не о дивиденде — нет
    wake = issuer_docs.wake_candidates(cands)
    assert {cands[k]["kind"] for k in wake} == {"ifrs_press", "ifrs_statements", "ifrs_presentation",
                                                "dividend_recommendation", "meeting_minutes"}
    assert len([k for k in wake if cands[k]["kind"] == "meeting_minutes"]) == 1
    assert issuer_docs.seen_periods(store, "ifrs") == {"2026Q2": "2026-10-26"}
    assert issuer_docs.last_document_url(store, "ops_release") in (door, page)

    # следующий такт: ничего не качается заново и записи реестра не дублируются
    g2 = FakeGetter(moment="2026-10-27T07:00:00+00:00")
    r2 = issuer_docs.collect(_ctx(store, g2, date(2026, 10, 27)))
    assert not [c for c in g2.calls if "/static/documents/" in c["url"]]
    assert len(register.manual_records(store)) == 3 and store.read_state(issuer_docs.INDEX_FILE)[page]["first_seen"] == T1
    assert r2.data["listed"] == 0


def test_first_run_does_not_download_history(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    g = FakeGetter(moment=T1)
    issuer_docs.collect(_ctx(store, g))
    index = store.read_state(issuer_docs.INDEX_FILE)
    old = next(e for u, e in index.items() if "0002-" in u and "aaaa" in u)        # пресс-релиз МСФО 11.08: старше окна
    assert old["note"] == issuer_docs.NOTE_BEFORE_START and old["first_seen"] is None and not old["versions"]
    fetched = {u.rsplit("/", 1)[-1][:8] for u in (c["url"] for c in g.calls) if "/static/documents/" in u}
    assert fetched == {"aaaa0001", "bbbb0001", "bbbb0003", "bbbb0004", "bbbb0006"}  # только свежие документы
    assert [x["status"] for x in register.manual_records(store)] == ["recommended", "declared"]


def test_listing_failures_fall_back_and_degrade(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    # рабочий хост двери молчит — тот же путь берётся с запасного хоста (корень закреплён только ему)
    monkeypatch.setattr(http, "_PINNED_BY_CONFIG", set())
    down = FakeGetter(overrides={"cfg.tbank-online.com": http.FetchError("x", None, "нет связи")}, moment=T1)
    r = issuer_docs.collect(_ctx(store, down))
    assert r.status == OK, r.reasons
    assert any(c["url"].startswith("https://cfg.tbank.ru/") for c in down.calls)
    assert http._PINNED_BY_CONFIG == {"cdn.tbank.ru", "cfg.tbank.ru"}
    assert http.tls_context("https://cdn.tbank-online.com/a.pdf") is None

    # страница отдала разметку без списка — причина деградации, дверь работает
    store2 = Store(tmp_path / "state2")
    _started(store2)
    blank = FakeGetter(overrides={"/press-releases/": b"<html><body>404</body></html>"}, moment=T1)
    r = issuer_docs.collect(_ctx(store2, blank))
    assert r.status == DEGRADED and any("нет ни одной записи списка" in x for x in r.reasons)
    # не ответили ни страница, ни дверь — отказ невосполнимого источника с повтором
    store3 = Store(tmp_path / "state3")
    dead = FakeGetter(overrides={"/press-releases/": http.FetchError("x", 503, "HTTP 503"),
                                 "getFolderTree": http.FetchError("x", 503, "HTTP 503")}, moment=T1)
    r = issuer_docs.collect(_ctx(store3, dead))
    assert r.status == FAILED and r.retry and verdict([r]).code == 3
    # документ на чужом хосте не качается
    store4 = Store(tmp_path / "state4")
    _started(store4)
    alien = (FIX / "issuer_docs/door_operating.json").read_bytes().replace(b"cdn.tbank.ru", b"files.example.org")
    g4 = FakeGetter(overrides={"Operating%20Results": alien}, moment=T1)
    r = issuer_docs.collect(_ctx(store4, g4))
    assert any("не на хосте эмитента" in x for x in r.reasons)
    assert not any("files.example.org" in c["url"] for c in g4.calls)          # запрос на чужой хост не ушёл


def test_an_interrupted_or_unreadable_document_is_named(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    _started(store)
    scan = (FIX / "issuer_docs/scan.pdf.txt").read_bytes()
    g = FakeGetter(overrides={"0001-": scan}, moment=T1)
    r = issuer_docs.collect(_ctx(store, g))
    assert r.status == DEGRADED and not r.retry
    assert any("не разобран" in x and "распознавание выключено" in x and "внести вручную" in x for x in r.reasons)
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    key = next(k for k, c in cands.items() if c["kind"] == "ops_release")
    assert cands[key]["status"] == "needs_manual"
    # такт оборвался на разборе: следующий говорит об этом один раз и заново не разбирает
    cands[key]["detail"] = issuer_docs.PENDING
    store.write_state(issuer_docs.CANDIDATES_FILE, cands)
    r2 = issuer_docs.collect(_ctx(store, FakeGetter(moment="2026-10-27T07:00:00+00:00"), date(2026, 10, 27)))
    assert any(issuer_docs.INTERRUPTED in x for x in r2.reasons)
    assert store.read_state(issuer_docs.CANDIDATES_FILE)[key]["detail"] == issuer_docs.INTERRUPTED


def test_a_rewritten_listing_date_does_not_make_an_old_document_new(monkeypatch, tmp_path):
    """Отметка двери переписывается при перезаливке: возраст документа — по дню из заголовка и по его периоду,
    день для пересчёта на дробление — даты самого документа; за квартал, закрытый фактами, запись не пишется."""
    assert issuer_docs.title_day("Протокол № 16 от 02.10.2026") == "2026-10-02"
    assert issuer_docs.title_day("Протокол № 7 Общего собрания") is None and issuer_docs.title_day("от 32.13.2026") is None
    assert issuer_docs.period_day("2026M09") == "2026-09-30" and issuer_docs.period_day("2026Q2") == "2026-06-30"
    assert issuer_docs.period_day(None) is None
    patterns = [r"(?P<months>\d{1,2})months(?P<year>\d{4})", r"(?P<month_name>january|august)_?(?P<year>\d{4})"]
    assert issuer_docs.month_from_url("https://x.example/ras_for_8months2026_ru.pdf", patterns) == "2026M08"
    assert issuer_docs.month_from_url("https://x.example/release_August_2026.pdf", patterns) == "2026M08"
    assert issuer_docs.month_from_url("https://x.example/other.pdf", patterns) is None

    use_fixtures(monkeypatch, tmp_path)
    old_release = {"response": [{"name": "2024", "type": "folder", "children": [
        {"id": "x1", "name": "Операционные результаты за октябрь 2024", "type": "file", "typeFile": "pdf", "size": "1",
         "link": "https://cdn.tbank.ru/static/documents/cccc0001-0000-4000-8000-000000000001.pdf",
         "publishedAt": "2026-10-20T06:38:31.662Z"}]}]}
    old_minutes = {"response": [{"name": "default", "type": "folder", "children": [
        {"id": "x2", "name": "Протокол № 4 от 15.11.2024", "type": "file", "typeFile": "pdf", "size": "1",
         "link": "https://cdn.tbank.ru/static/documents/cccc0002-0000-4000-8000-000000000002.pdf",
         "publishedAt": "2026-10-20T06:38:31.662Z"},
        {"id": "x3", "name": "Рекомендации совета директоров по размеру дивиденда по акциям общества и порядку его выплаты",
         "type": "file", "typeFile": "pdf", "size": "1",
         "link": "https://cdn.tbank.ru/static/documents/cccc0003-0000-4000-8000-000000000003.pdf",
         "publishedAt": "2026-10-20T06:38:31.662Z"}]}]}
    old_text = ("%PDF-1.7 синтетика теста\nСовет директоров рекомендовал собранию акционеров 14 ноября 2024 года принять "
                "решение. " + "Текст рекомендации совета директоров общества о порядке выплаты. " * 4 +
                "Выплатить дивиденды по обыкновенным акциям общества за девять месяцев 2024 года в размере 92,5 рубля "
                "(Девяносто два рубля 50 копеек) на одну обыкновенную акцию. Установить дату, на которую определяются "
                "лица, имеющие право на получение дивидендов, – 25 ноября 2024 года.").encode("utf-8")
    import json as _json

    g = FakeGetter(overrides={"Operating%20Results": _json.dumps(old_release).encode("utf-8"),
                              "vneocherednoe-sobranie-akcionerov": _json.dumps(old_minutes).encode("utf-8"),
                              "cccc0003": old_text}, moment=T1)
    store = Store(tmp_path / "state")
    r = issuer_docs.collect(_ctx(store, g))
    index = store.read_state(issuer_docs.INDEX_FILE)
    by = {u.rsplit("/", 1)[-1][:8]: e for u, e in index.items()}
    # первый запуск: релиз за октябрь 2024 и протокол от 15.11.2024 стары, хотя отметка списка свежая
    assert by["cccc0001"]["note"] == issuer_docs.NOTE_BEFORE_START and by["cccc0002"]["note"] == issuer_docs.NOTE_BEFORE_START
    assert by["cccc0002"]["listed"] == "2024-11-15"
    fetched = {u.rsplit("/", 1)[-1][:8] for u in (c["url"] for c in g.calls) if "/static/documents/" in u}
    assert "cccc0001" not in fetched and "cccc0002" not in fetched and "cccc0003" in fetched
    # рекомендация без дня в заголовке скачана и разобрана, но квартал закрыт фактами — записи реестра нет
    cand = next(c for c in store.read_state(issuer_docs.CANDIDATES_FILE).values() if "cccc0003" in c["url"])
    assert cand["decision"]["period"] == "2024Q3" and cand["decision"]["dps"] == 92.5
    assert not [x for x in register.manual_records(store) if x["period"] == "2024Q3"]
    # а была бы открытым кварталом — сумма пересчиталась бы по дате реестра документа, не по отметке списка
    monkeypatch.setattr(config, "closed_through", lambda *a, **k: "2024Q2")
    assert issuer_docs.record_decision(_ctx(store, g), cand, cand["decision"], "2026-10-20")
    rec = register.manual_records(store)[-1]
    assert (rec["period"], rec["dps"], rec["dps_document"], rec["record_date"]) == ("2024Q3", 9.25, 92.5, "2024-11-25")
    assert r.status in (OK, DEGRADED)
