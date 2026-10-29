"""Настройки сборщиков этой копии (Совкомбанк) и ветви каркаса, которыми пользуются только они.

Месячного релиза у эмитента нет — месяц входит формами ЦБ банка; документы — с хоста API по номерам (проба
следующих номеров) и в слоте, номер которого перезаписывается; пост IR-канала — сигнал отчёта МСФО и документ
эмитента для реестра; решение о дивиденде — раз в год за весь год прибыли при квартальном календаре книги;
формы банковской группы ЦБ не раскрывает с 2К2025; ЧПД формы 0409102 — с разделом 12000.

Книга и факты — заглушка эмитента (`tests/fixtures/ind/issuer/`), настройки — `data/indicators/sources.yaml`
репозитория; ответы хоста документов, канала и ЦБ сочинены здесь же (адреса и имена файлов — в формате
источника, содержимое — заглушка).
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
import yaml

from indicators import calendar as cal
from indicators import cbr_forms, cbr_group, config, http, issuer_docs, news, outputs, register, release_watch
from indicators.sources import DEGRADED, FAILED, OK, Context
from indicators.store import Point, Store
from tests.support_ind import FakeGetter, use_issuer

pytestmark = pytest.mark.tact  # быстрые тесты такта

HOST = "https://prod-api.sovcombank.ru"
REPORT = HOST + "/finance-report/index?id={}"
PRES = HOST + "/finance-presentations/{}"
SLOT = HOST + "/documents/16976"
T1 = "2026-11-13T06:20:00+00:00"
TODAY = date(2026, 11, 13)


def _cfg():
    return config.sources()


def _ctx(store, getter, today=TODAY):
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter)


class Host(FakeGetter):
    """Хост API эмитента: адрес → (байты, имя файла из Content-Disposition); нет адреса — 404, как у хоста
    («Отчёт не найден»). Прочие адреса — фикстуры общего каркаса."""

    def __init__(self, files=None, moment=T1):
        super().__init__(moment=moment)
        self.files = dict(files or {})

    def __call__(self, url, *, data=None, headers=None, sink=None, name=None, **kw):
        if not url.startswith(HOST):
            return super().__call__(url, data=data, headers=headers, sink=sink, name=name, **kw)
        self.calls.append({"url": url, "data": data, "headers": dict(headers or {})})
        if url not in self.files:
            raise http.FetchError(url, 404, "HTTP 404")
        body, filename = self.files[url]
        disposition = f"attachment; filename=\"file.pdf\"; filename*=UTF-8''{urllib.parse.quote(filename)}"
        resp = http.Response(url=url, status=200, body=body, fetched_at=self.moment,
                             headers={"Content-Type": "application/pdf", "Content-Disposition": disposition})
        if sink is not None and name:
            resp = replace(resp, raw_path=str(sink.keep(name, resp)))
        return resp


def _started(store):
    """Сборщик уже работал: первый запуск историю не качает, а здесь нужны все документы."""
    store.write_state(issuer_docs.INDEX_FILE, {HOST + "/finance-report/index?id=1": {
        "first_seen": None, "note": issuer_docs.NOTE_BEFORE_START, "versions": []}})


# ------------------------------------------------------------------ настройки копии

def test_settings_of_this_copy_name_no_monthly_release_and_the_bank_forms():
    s = _cfg()
    sched = s["schedule"]
    assert cal.monthly_spec(sched) is None                         # месячного релиза у эмитента нет
    assert release_watch.monthly(s).wakes is False
    assert s["issuer_docs"]["hosts"] == ["prod-api.sovcombank.ru"] and not s["issuer_docs"].get("press_page")
    # сертификат хоста API эмитента — УЦ Минцифры: закреплённый корень рабочему хосту; запасных хостов нет
    assert s["issuer_docs"]["trusted_root_hosts"] == ["prod-api.sovcombank.ru"] and not s["issuer_docs"]["fallback_hosts"]
    assert [p["next_id"] for p in s["issuer_docs"]["probe"]] == [168, 165]
    assert s["issuer_docs"]["slots"][0]["id"] == 16976
    assert s["cbr_group"]["suspended_since"] == "2025Q2"
    assert "12000" in s["cbr_forms"]["nii_sections"]["plus"]
    assert s["dividends"]["period_rule"] == "quarterly" and s["dividends"]["annual_decision"] is True
    assert s["dividends"]["news_kinds"]["telegram:irsovcombank"] == register.ISSUER
    [channel] = s["news"]["telegram_channels"]
    assert channel["name"] == "irsovcombank" and channel["keywords"] == "any" and channel["require"] == []
    assert s["iss"]["issue_size"] is True
    # окно дозора: отчёт МСФО — пятница около 10:00 МСК; дни дозора — по видам событий фактов эмитента
    lo, hi = sched["watch_window_msk"]
    assert lo <= "10:00" < hi and set(sched["watch_kinds"]) == {"ifrs", "dividend_recommendation", "agm"}


def test_tiles_of_this_copy_are_the_bank_forms_without_the_group():
    spec = _cfg()["tiles"]
    assert outputs.tile_registry_errors(spec) == []
    items = {i["id"]: i for i in spec["items"]}
    assert {k for k, t in items.items() if t["basis"] == "regulatory"} == {"f135_n1_0", "f135_n1_1", "f135_n1_2"}
    assert not any(".f805." in " ".join(t["series"]) for t in items.values())     # Н20.x не раскрывается с 2К2025
    assert not any(t["basis"] == "mgmt" for t in items.values())                  # месячного релиза нет
    assert items["f102_nii_ytd"]["series"] == ["cbr.f102.nii_ytd"]


# ------------------------------------------------------------------ документы: имя файла, вид, период

@pytest.mark.parametrize("name, kind, period", [
    ("Совкомбанк_МСФО_3м26", "ifrs_statements", "2026Q1"),
    ("Совкомбанк_МСФО_1п26", "ifrs_statements", "2026Q2"),
    ("Совкомбанк_МСФО_9м25", "ifrs_statements", "2025Q3"),
    ("Совкомбанк_МСФО_2025", "ifrs_statements", "2025Q4"),
    ("IFRS_FS_Sovсombank_12m2021_RUS_обобщенная", "ifrs_statements", "2021Q4"),
    ("Sovcombank IFRS Group 2025m3", "ifrs_statements", "2025Q1"),
    ("Sovcombank IFRS Group 2024m12", "ifrs_statements", "2024Q4"),
    ("SVCB_Pres_2025Q3_Call_20251114", "ifrs_presentation", "2025Q3"),
    ("Презентация по МСФО за 1п26", "ifrs_presentation", "2026Q2"),
    ("Prezentacia po MSFO za 1p26", "ifrs_presentation", "2026Q2"),       # имя без filename* — транслитом
    ("Sovkombank_MSFO_1p26", "ifrs_statements", "2026Q2"),
    ("Совкомбанк_МСФО_1кв26_Презентация_для_IR_звонка", "ifrs_presentation", "2026Q1"),
    ("Sovcombank_Data_2025Q3_20251114", "databook", "2025Q3"),
])
def test_kind_and_period_come_from_the_file_name(name, kind, period):
    assert issuer_docs.classify(name, _cfg()["issuer_docs"], monthly_kind="ras_release") == {"kind": kind,
                                                                                             "period": period}


def test_the_title_of_a_file_comes_from_content_disposition():
    quoted = urllib.parse.quote("Совкомбанк_МСФО_9м26.pdf")
    got = issuer_docs.content_title({"Content-Disposition": f"attachment; filename=\"x.pdf\"; filename*=UTF-8''{quoted}"})
    assert got == "Совкомбанк_МСФО_9м26"
    latin = "Отчёт.pdf".encode("utf-8").decode("latin-1")     # имя без filename* — байты UTF-8 в латинице-1
    assert issuer_docs.content_title({"content-disposition": f'attachment; filename="{latin}"'}) == "Отчёт"
    assert issuer_docs.content_title({"Content-Type": "application/pdf"}) is None


def test_probe_finds_the_next_numbers_and_remembers_them(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _started(store)
    slot = (b"%PDF pres 1p26", "Презентация по МСФО за 1п26.pdf")
    host = Host({REPORT.format(168): (b"%PDF report 9m26", "Совкомбанк_МСФО_9м26.pdf"), SLOT: slot})
    res = issuer_docs.collect(_ctx(store, host))
    assert res.status == OK, res.reasons
    asked = [c["url"] for c in host.calls]
    assert asked[:3] == [REPORT.format(n) for n in (168, 169, 170)]          # номер и два вперёд
    assert PRES.format(165) in asked and SLOT in asked
    assert store.read_state(issuer_docs.PROBE_FILE)[HOST + "/finance-report/index?id={id}"] == 169
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    [key] = [k for k, c in cands.items() if c.get("period") == "2026Q3"]
    assert cands[key]["kind"] == "ifrs_statements" and cands[key]["sha256"] and cands[key]["first_seen"] == T1
    assert key in issuer_docs.wake_candidates(cands)                         # отчёт МСФО будит выпуск
    # следующий такт: проба идёт с 169, найденный номер не перекачивается
    host2 = Host({REPORT.format(168): (b"%PDF report 9m26", "Совкомбанк_МСФО_9м26.pdf"), SLOT: slot})
    issuer_docs.collect(_ctx(store, host2))
    assert REPORT.format(168) not in [c["url"] for c in host2.calls]
    assert [c["url"] for c in host2.calls][:3] == [REPORT.format(n) for n in (169, 170, 171)]


def test_the_slot_is_a_new_document_when_its_content_changes(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _started(store)
    issuer_docs.collect(_ctx(store, Host({SLOT: (b"%PDF pres 1p26", "Презентация по МСФО за 1п26.pdf")})))
    issuer_docs.collect(_ctx(store, Host({SLOT: (b"%PDF pres 1p26", "Презентация по МСФО за 1п26.pdf")})))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    assert len([c for c in cands.values() if c.get("kind") == "ifrs_presentation"]) == 1   # тот же файл — тот же
    later = "2026-11-17T06:20:00+00:00"
    issuer_docs.collect(_ctx(store, Host({SLOT: (b"%PDF pres 9m26", "Презентация по МСФО за 9м26.pdf")}, moment=later),
                             today=date(2026, 11, 17)))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    pres = sorted((c["period"], c["first_seen"]) for c in cands.values() if c.get("kind") == "ifrs_presentation")
    assert pres == [("2026Q2", T1), ("2026Q3", later)]                       # перезаписанный слот — новый документ
    versions = store.read_state(issuer_docs.INDEX_FILE)[SLOT]["versions"]
    assert len(versions) == 2 and versions[0]["sha256"] != versions[1]["sha256"]


def test_one_file_under_two_answered_addresses_does_not_hide_the_next_answer(monkeypatch, tmp_path):
    """Разбираемый документ под двумя адресами пробы и слота (один sha256) — один документ с двумя адресами; ответ пробы,
    который идёт после них, тоже разобран: ответы в руках не теряются после склейки адресов."""
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _started(store)
    rec = (b"%PDF divrec 2026", "Рекомендации совета директоров по дивидендам за 2026 год.pdf")
    minutes = (b"%PDF agm 2026", "Протокол годового общего собрания акционеров.pdf")
    host = Host({SLOT: rec, PRES.format(165): rec, REPORT.format(168): minutes})
    issuer_docs.collect(_ctx(store, host))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    [one] = [c for c in cands.values() if c.get("kind") == "dividend_recommendation"]
    assert sorted(one["urls"]) == sorted([SLOT, PRES.format(165)])
    assert [c["url"] for c in cands.values() if c.get("kind") == "meeting_minutes"] == [REPORT.format(168)]


def test_no_answer_from_the_host_fails_the_collector(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)

    def down(url, **kw):
        raise http.FetchError(url, 503, "HTTP 503")

    res = issuer_docs.collect(_ctx(store, down))
    assert res.status == FAILED and res.retry


# ------------------------------------------------------------------ пост IR-канала: сигнал отчёта и документ эмитента

POST_HTML = """<html><body>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="irsovcombank/300">
<div class="tgme_widget_message_text js-message_text">Отчетность МСФО Группы за 9 месяцев 2026 года.<br/>
Чистая прибыль за 9 месяцев 2026 года составила 61,2 млрд руб.</div>
<div class="tgme_widget_message_document_title accent_color">Совкомбанк_МСФО_9м26.pdf</div>
<time datetime="2026-11-13T07:24:00+00:00"></time></div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="irsovcombank/301">
<div class="tgme_widget_message_text js-message_text">Наблюдательный совет рекомендовал дивиденды за 2026 год
в размере 35 копеек на одну акцию. Дата закрытия реестра — 13 июля 2027 года.</div>
<time datetime="2027-05-28T06:32:00+00:00"></time></div></div>
</body></html>"""


def test_telegram_posts_carry_the_file_names():
    posts = news.telegram_posts(POST_HTML)
    assert posts[0]["files"] == ["Совкомбанк_МСФО_9м26.pdf"] and posts[0]["text"].endswith("Совкомбанк_МСФО_9м26.pdf")
    assert "files" not in posts[1]


def test_words_of_the_issuer_exclude_the_subsidiaries_and_the_analyst():
    words, exclude = _cfg()["news"]["issuer_keywords"], _cfg()["news"]["exclude"]
    assert not news.relevant("Совкомбанк Лизинг разместил облигации", words, None, exclude)
    assert not news.relevant("Главный аналитик Совкомбанка ждёт снижения ставки", words, None, exclude)
    assert news.relevant("Совкомбанк отчитался по МСФО; Совкомбанк Страхование — тоже", words, ["МСФО"], exclude)


def test_a_dividend_in_kopecks_is_read():
    got = news.extract_dividend_decision("Акционеры утвердили дивиденды за 2025 год: по 35 копеек на акцию.",
                                         published="2026-06-30T10:00:00+03:00")
    assert got["dps"] == pytest.approx(0.35) and got["year"] == 2025


def _news_state(store, posts):
    items = {}
    for p in posts:
        items[f"https://t.me/{p['post']}"] = {"kind": "telegram:irsovcombank", "first_seen": p["time"], "title": p["text"][:120],
                                             "published": p["time"], "text": p["text"],
                                             "topic": "dividend" if "дивиденд" in p["text"] else "ras"}
    store.write_state("news/items.json", {"items": items, "pdf": {}, "days": {}})


def test_the_ir_post_of_the_report_is_a_signal_with_its_numbers(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _started(store)
    _news_state(store, news.telegram_posts(POST_HTML))
    res = issuer_docs.collect(_ctx(store, Host({})))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    [post] = [c for c in cands.values() if c.get("origin") == "post"]
    assert (post["kind"], post["period"], post["url"]) == ("ifrs_press", "2026Q3", "https://t.me/irsovcombank/300")
    assert post["numbers"]["np_ytd"] == pytest.approx(61.2) and post["sha256"]
    assert res.data["posts"] and set(res.data["posts"]) <= set(issuer_docs.wake_candidates(cands))


def test_an_old_report_in_the_ir_channel_wakes_nothing(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _started(store)
    old = [{"post": "irsovcombank/250", "time": "2026-08-14T07:30:00+00:00",
            "text": "Отчетность МСФО Группы за 6 месяцев 2026 года\nСовкомбанк_МСФО_1п26.pdf"}]
    _news_state(store, old)
    issuer_docs.collect(_ctx(store, Host({})))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE) or {}
    assert not [c for c in cands.values() if c.get("origin") == "post"]      # квартал фактов книги — не сигнал


def test_the_ir_post_counts_as_the_document_of_the_issuer_in_the_register(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _news_state(store, news.telegram_posts(POST_HTML))
    rows = register.build(store, ticker="SVCB", today=date(2027, 5, 29), cfg=_cfg())
    [rec] = rows
    assert (rec["period"], rec["status"], rec["dps"]) == ("2026Q4", "recommended", 0.35)
    assert rec["sources"] == [register.ISSUER]                    # пост канала — документ эмитента, не новость
    assert rec["record_date"] == "2027-07-13"


def test_the_annual_decision_is_awaited_only_for_the_fourth_quarter(monkeypatch, tmp_path):
    use_issuer(monkeypatch, tmp_path)
    calendar = config.dividend_calendar()
    words = dict(template=config.book_value("meta.labels.register.collector_alarm"),
                 period_labels=config.book_value("meta.labels.periods"))
    # 15.04.2027: квартал решения за 1-й квартал 2026 года по карте лагов (1К2027) кончился, решения нет —
    # у годового плательщика его и не бывает; за 4-й квартал срок (2К2027) ещё идёт
    day = date(2027, 4, 15)
    assert register.alarm([], today=day, calendar=calendar, closed_through="2025Q4", annual_decision=True,
                          **words) is None
    quarterly = register.alarm([], today=day, calendar=calendar, closed_through="2025Q4", **words)
    assert quarterly and "2026" in quarterly
    late = register.alarm([], today=date(2027, 7, 15), calendar=calendar, closed_through="2025Q4",
                          annual_decision=True, **words)
    assert late and "за 2026 год" in late and "первый квартал" not in late
    paid = [{"year": 2026, "period": "2026Q4", "status": "paid", "dps": 0.35, "sources": ["T-Invest"]}]
    assert register.alarm(paid, today=date(2027, 7, 15), calendar=calendar, closed_through="2025Q4",
                          annual_decision=True, **words) is None
    assert register.alarm_from_book([], date(2027, 4, 15)) is None          # ключ настройки доходит до тревоги


# ------------------------------------------------------------------ календарь: формы ЦБ вместо месячного релиза

def test_the_month_enters_through_the_bank_forms(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    sched = _cfg()["schedule"]
    for month, value in (("2026M07", 30.0), ("2026M08", 40.0)):           # формы за июль и август уже в рядах
        store.upsert("cbr.f102.ni_ytd", [Point(month, value, "2026-09-25T07:00:00+00:00")])
    nxt = cal.next_ras(date(2026, 10, 20), store=store, schedule=sched, facts_events=config.calendar_events())
    assert nxt["enters_via"] == "form102" and nxt["release_date"] is None and nxt["month"] == "2026M09"
    events = cal.events(date(2026, 10, 20), store=store, schedule=sched, facts_events=config.calendar_events())
    kinds = {e["kind"] for e in events}
    assert "ras" not in kinds                                     # окна форм фактов — вид формы, а не релиза
    sept = [e for e in events if e.get("covers") == "2026M09"]
    assert [(e["kind"], e["title"]) for e in sept] == [("form102", "Формы банка на 01.10.2026")]
    dec = [e for e in events if e.get("covers") == "2026M12"]
    assert dec and dec[0]["kind"] == "form102" and "2026M12" not in dec[0]["title"]     # свой день — словами
    assert cal.is_release_day(date(2026, 11, 13), store=store, schedule=sched, facts_events=config.calendar_events())
    assert not cal.is_release_day(date(2026, 10, 26), store=store, schedule=sched,
                                  facts_events=config.calendar_events())         # день формы — не день дозора


# ------------------------------------------------------------------ формы ЦБ: ЧПД с разделом 12000; группа

def test_the_nii_of_the_form_102_includes_the_section_12000():
    values = {"11000": 100000.0, "12000": 30000.0, "13000": 1000.0, "14000": 0.0, "16000": 0.0,
              "31000": 40000.0, "32000": 0.0, "33000": 0.0, "34000": 0.0, "35000": 0.0, "36000": 0.0}
    tree = cbr_forms.f102_summary(values, nii=(cbr_forms.F102_NII_INCOME, cbr_forms.F102_NII_EXPENSE))["nii_ytd"]
    ours = cbr_forms.f102_summary(values)["nii_ytd"]                      # определение — настройкой копии
    assert tree == pytest.approx(0.061) and ours == pytest.approx(0.091)
    with pytest.raises(config.ConfigError):
        cbr_forms.nii_sections({"plus": [], "minus": ["31000"]})


def test_suspended_group_forms_are_not_awaited(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    getter = FakeGetter()                                       # перечень периодов фикстуры кончается раньше
    res = cbr_group.collect(_ctx(store, getter, today=date(2026, 10, 20)))
    assert res.data.get("suspended_since") == "2025Q2"
    asked = [c["data"].decode("utf-8") for c in getter.calls if c["data"]]
    assert not any("2026-07-01" in a for a in asked)              # 3К2026 не ждётся: раскрытие приостановлено
    assert res.status in (OK, DEGRADED) and not any("2026Q3" in r for r in res.reasons)


# ------------------------------------------------------------------ число акций по бирже

def test_the_issue_size_series_and_the_flag(monkeypatch, tmp_path):
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    store.upsert("iss.issue_size.SVCB", [Point("2026-11-12", 22516228905.0, T1)], unit="shares")
    r = outputs._Reader(store, date(2026, 11, 13))
    flag = outputs.shares_flag(r, "SVCB")
    assert flag["raised"] is False and flag["exchange_mln"] == pytest.approx(22516.228905)
    store.upsert("iss.issue_size.SVCB", [Point("2026-11-13", 24516228905.0, T1)], unit="shares")
    flag = outputs.shares_flag(outputs._Reader(store, date(2026, 11, 13)), "SVCB")
    assert flag["raised"] is True and "24 516,2" in flag["detail"]


def test_dividend_posts_of_the_channel_in_its_own_formats():
    """Пост канала: рекомендация с суммой «на 1 акцию» в копейках и итоги собрания пунктами — решение без
    подлежащего, год — в соседнем пункте (тексты сочинены в формате канала)."""
    patterns = _cfg()["dividends"]["period_patterns"]
    rec = news.extract_dividend_decision(
        "Наблюдательный совет банка рекомендовал собранию акционеров выплатить дивиденды за 2026 год в размере "
        "40 копеек на 1 акцию; всего на выплату пойдёт 9 млрд руб.", published="2027-05-28T06:30:00+00:00",
        period_patterns=patterns)
    assert (rec["status"], rec["period"], rec["dps"]) == ("recommended", "2026Q4", pytest.approx(0.40))
    minutes = news.extract_dividend_decision(
        "Итоги собрания акционеров\n\n1. Утвердили годовой отчёт за 2026 год.\n2. Приняли решение о выплате "
        "дивиденда - 0,40₽ на акцию.", published="2027-07-02T15:20:00+00:00", period_patterns=patterns)
    assert (minutes["status"], minutes["period"], minutes["dps"]) == ("declared", "2026Q4", pytest.approx(0.40))
    assert news.extract_dividend_decision("Приняли решение о выплате дивиденда - 0,40₽ на акцию.",
                                          published="2027-07-02T15:20:00+00:00", period_patterns=patterns) is None


def test_the_probe_of_this_copy_walks_the_numbers_the_slot_and_the_channel(monkeypatch, tmp_path):
    """Проба источников (ops/tools/probe.py) на настройках копии: последний известный номер — файл, следующий — 404
    или новый файл, слот — файл с именем, канал — посты; документа месячного релиза нет — строки о нём нет."""
    import importlib.util
    import sys
    from pathlib import Path

    use_issuer(monkeypatch, tmp_path)
    path = Path(__file__).resolve().parents[1] / "ops" / "tools" / "probe.py"
    spec = importlib.util.spec_from_file_location("tool_probe_svcb", path)
    probe = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = probe
    spec.loader.exec_module(probe)
    files = {REPORT.format(167): (b"%PDF-1.7 1p26", "Совкомбанк_МСФО_1п26.pdf"),
             PRES.format(164): (b"%PDF-1.7 pres", "SVCB_Pres_2025Q3_Call_20251114.pdf"),
             SLOT: (b"%PDF-1.7 slot", "Презентация по МСФО за 1п26.pdf")}
    host = Host(files)
    host.overrides["t.me/s/irsovcombank"] = POST_HTML.encode("utf-8")
    rows = probe.probe_issuer_docs(host, cfg=config.sources(), state=tmp_path / "нет")
    assert all(r.ok for r in rows), [(r.what, r.note) for r in rows if not r.ok]
    notes = {r.what: r.note for r in rows}
    assert notes["проба номеров «отчётность МСФО»: № 167 (последний известный)"] == "PDF «Совкомбанк_МСФО_1п26»"
    assert notes["проба номеров «отчётность МСФО»: № 168 (следующий)"].startswith("номера ещё нет")
    assert notes["слот: текущая презентация МСФО"] == "PDF «Презентация по МСФО за 1п26»"
    assert notes["канал эмитента: irsovcombank"].startswith("постов 2")
    assert probe.DOCS_WHAT not in notes                       # месячного релиза у эмитента нет
    host.files[REPORT.format(168)] = (b"%PDF-1.7 9m26", "Совкомбанк_МСФО_9м26.pdf")
    rows = probe.probe_issuer_docs(host, cfg=config.sources(), state=tmp_path / "нет")
    assert any(r.note == "вышел новый файл «Совкомбанк_МСФО_9м26»" for r in rows)


def test_the_monthly_watch_takes_nothing_without_a_monthly_release(monkeypatch, tmp_path):
    """Месячного релиза нет: дозор месяцев не ведёт — пост канала с числами отчёта в месячные ряды не идёт."""
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    _news_state(store, [{"post": "irsovcombank/300", "time": "2026-11-13T07:24:00+00:00",
                         "text": "Отчетность МСФО за 9 месяцев 2026 года. Кредитный портфель вырос до 3 300 млрд руб."}])
    res = release_watch.run(_ctx(store, Host({}), today=date(2026, 11, 13)))
    assert res.status == OK and res.data["months"] == [] and not res.series


def test_the_first_run_takes_the_slot_of_a_closed_quarter_as_known(monkeypatch, tmp_path):
    """Первый запуск: файл слота о квартале, уже закрытом фактами книги, — известный без момента появления (выпуск
    не будит); следующий файл в слоте — новый документ с моментом появления."""
    state = use_issuer(monkeypatch, tmp_path)
    store = Store(state)
    issuer_docs.collect(_ctx(store, Host({SLOT: (b"%PDF pres 1p26", "Презентация по МСФО за 1п26.pdf")}), today=date(2026, 10, 22)))
    entry = store.read_state(issuer_docs.INDEX_FILE)[SLOT]
    assert entry["note"] == issuer_docs.NOTE_BEFORE_START and entry["first_seen"] is None
    assert not issuer_docs.wake_candidates(store.read_state(issuer_docs.CANDIDATES_FILE) or {})
    issuer_docs.collect(_ctx(store, Host({SLOT: (b"%PDF pres 9m26", "Презентация по МСФО за 9м26.pdf")}), today=TODAY))
    cands = store.read_state(issuer_docs.CANDIDATES_FILE)
    assert [(c["period"], c["first_seen"]) for c in cands.values()] == [("2026Q3", T1)]
