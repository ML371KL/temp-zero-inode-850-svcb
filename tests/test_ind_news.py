"""Новостные ленты: архив дня, статьи, превью каналов, RSS изданий, слова эмитента в обоих написаниях,
период решения о дивиденде, числа месячного релиза из текста. Фикстуры — сочинённые тексты: от источника —
разметка и схема чисел, слова свои; с архивом настоящих текстов их сверяет тест с меткой `archive`."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from indicators import config, http, news
from indicators.sources import FAILED, OK, Context
from indicators.store import Store
from tests.support_ind import (FIX, NEWS_COMMON_RUN_LIMIT, FakeGetter, use_form_settings, longest_common_run, longest_common_runs,
                               plain_text, python_texts, real_news_corpus, use_fixtures)

pytestmark = pytest.mark.tact  # быстрые тесты такта


@pytest.fixture(autouse=True)
def _form_settings(monkeypatch):
    """Тесты общего каркаса — на настройках и истории формы образца (`tests/fixtures/ind/form/`): ветви, которыми
    настройки этой копии не пользуются; настройки копии проверяет `tests/test_ind_svcb.py`."""
    use_form_settings(monkeypatch)


def _t(name):
    return (FIX / "news" / name).read_text(encoding="utf-8")


def _patterns():
    return config.sources()["dividends"]["period_patterns"]


# ------------------------------------------------------------------ слова эмитента

def test_issuer_words_in_both_spellings():
    """Имя эмитента ищется в обоих написаниях: обычный и неразрывный дефис, кириллическая и латинская «Т»,
    прежние имена. Тикер из одной буквы хэштегом не ищется: он начало чужих хэштегов."""
    cfg = config.sources()["news"]
    words, need = cfg["issuer_keywords"], cfg["dividend_require"]
    for title in ('Акционеры "Т-Технологий" утвердили дивиденды', "Совет директоров «Т‑Технологий» рекомендовал дивиденды",
                  "T-Technologies объявила дивиденды", "Т‑Банк и дивиденды группы", "ТБанк: дивиденды за квартал"):
        assert news.relevant(title, words, need), title
    assert not news.relevant("Банк Пример утвердил дивиденды", words, need)
    assert not news.relevant('Акционеры "Т-Технологий" собрались', words, need)       # нет слова темы
    assert news.plain("Т‑Технологии и") == "Т-Технологии и"
    assert not news.hashtag_hit("Татнефть #TATN растёт, #T", "T")
    assert news.hashtag_hit("Отчёт #PRMR вышел", "PRMR") and not news.hashtag_hit("Отчёт #PRMRP вышел", "PRMR")
    assert cfg["telegram_channels"] == [] and all("#" not in w for w in words)


def test_interfax_listing():
    base = "https://www.interfax.ru/business/news/2026/10/02/"
    items = news.interfax_listing(_t("interfax_day_2026-10-02.html"), base)
    assert sorted(i["url"].rsplit("/", 1)[-1] for i in items) == ["9000301", "9000302"]
    doc = _t("interfax_9000301.html")
    assert news.meta(doc, "article:published_time") == "2026-10-02T13:35:00+03:00"
    assert news.article_text(doc).startswith("INTERFAX.RU")


# ------------------------------------------------------------------ период и решение о дивиденде

@pytest.mark.parametrize("words, period, label", [
    ("за первый квартал 2026 года", "2026Q1", "за первый квартал 2026 года"),
    ("за три месяца 2025 года", "2025Q1", "за три месяца 2025 года"),
    ("за полугодие 2026 года", "2026Q2", "за полугодие 2026 года"),
    ("за второй квартал 2026 года", "2026Q2", "за второй квартал 2026 года"),
    ("по итогам первого полугодия", "2026Q2", None),
    ("по результатам II квартала 2025 года", "2025Q2", None),
    ("по результатам I квартала 2026 г.", "2026Q1", None),
    ("по результатам III квартала 2025 г.", "2025Q3", None),
    ("по результатам IV квартала 2025 г.", "2025Q4", None),
    ("за девять месяцев 2025 года", "2025Q3", "за девять месяцев 2025 года"),
    ("за 2025 год", "2025Q4", "за 2025 год"),
    ("четвертого квартала", "2025Q4", None),
])
def test_period_words_name_the_profit_quarter(words, period, label):
    """Слова решения → квартал прибыли: накопительные слова называют квартал, которым период кончается;
    «II квартал» — не «I квартал», «года» и «полугодие» — не «год». Года в тексте нет — последний такой
    квартал, кончившийся к дню публикации."""
    assert news.period_of(f"Дивиденды {words} утверждены.", _patterns(), published=date(2026, 10, 2)) == (period, label)


def test_period_needs_patterns_and_a_year():
    assert news.period_of("за полугодие 2026 года", None) is None
    assert news.period_of("дивиденды утверждены", _patterns(), published=date(2026, 10, 2)) is None
    assert news.period_of("по итогам первого полугодия", _patterns()) is None                 # нет ни года, ни дня
    assert news.period_of("за девять месяцев", _patterns(), published=date(2026, 1, 10)) == ("2025Q3", None)
    # год периода — первый не левее слов периода: год в начале фразы периодом не становится
    text = "В 2025 году собрание утвердило дивиденды за первый квартал 2026 года"
    assert news.period_of(text, _patterns()) == ("2026Q1", "за первый квартал 2026 года")


def test_dividend_decisions_of_the_meeting_and_the_board():
    doc = _t("interfax_9000301.html")
    got = news.extract_dividend_decision(news.article_text(doc), published=news.meta(doc, "article:published_time"),
                                         period_patterns=_patterns())
    assert {k: got[k] for k in ("status", "year", "period", "label", "dps", "record_date", "decided_date")} == {
        "status": "declared", "year": 2026, "period": "2026Q2", "label": "за полугодие 2026 года", "dps": 4.7,
        "record_date": "2026-10-12", "decided_date": "2026-10-02"}      # прошлая выплата дальше по тексту не берётся
    page = _t("kommersant_doc.html")
    rec = news.extract_dividend_decision(news.page_text(page), published=news.page_published(page),
                                         period_patterns=_patterns())
    assert (rec["status"], rec["period"], rec["label"], rec["dps"], rec["record_date"], rec["decided_date"]) == (
        "recommended", "2026Q3", None, 4.9, None, "2026-11-19")
    item = news.rss_items(_t("tass_rss.xml"))[0]
    brief = news.extract_dividend_decision(f"{item['title']}. {item['description']}", published=item["published"],
                                           period_patterns=_patterns())
    assert (brief["status"], brief["period"], brief["dps"], brief["record_date"]) == ("declared", "2026Q1", 4.6, "2026-08-10")
    # без слов периода и без суммы на акцию решения нет
    assert news.extract_dividend_decision("Собрание акционеров утвердило дивиденды в размере 4,7 рубля на акцию.",
                                          published="2026-10-02T13:35:00+03:00", period_patterns={"1": "нет"}) is None
    assert news.extract_dividend_decision("Собрание акционеров утвердило дивиденды за полугодие 2026 года.",
                                          period_patterns=_patterns()) is None
    assert news.extract_dividend_decision("Аналитики ждут дивиденды за полугодие 2026 года в размере 5 рублей на акцию.",
                                          period_patterns=_patterns()) is None


def test_annual_wording_without_period_patterns():
    """Годовой реестр (настройки периода нет): год прибыли — «по итогам / за <год> год», период пуст."""
    text = ("Годовое собрание акционеров банка утвердило дивиденды по итогам 2025 года в размере 30 рублей на одну "
            "обыкновенную акцию. Реестр акционеров закроется 20 июля 2026 года.")
    got = news.extract_dividend_decision(text, published="2026-06-30T12:15:00+03:00")
    assert (got["status"], got["year"], got["period"], got["label"], got["dps"], got["record_date"]) == (
        "declared", 2025, None, None, 30.0, "2026-07-20")
    assert news.extract_dividend_decision("Совет директоров рекомендовал дивиденды за полугодие в размере 5 рублей "
                                          "на акцию.") is None


# ------------------------------------------------------------------ ленты

def test_rss_items_unwrap_cdata_and_dates():
    items = news.rss_items(_t("kommersant_rss.xml"))
    assert [i["url"] for i in items] == ["https://www.kommersant.ru/doc/9000401", "https://www.kommersant.ru/doc/9000402"]
    assert items[0]["published"] == "2026-11-19T10:20:00+03:00"
    assert items[0]["title"] == "Совет директоров «Т‑Технологий» назвал размер дивиденда за третий квартал"
    ld = ('<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-07-09T10:18:13+03:00",'
          '"articleBody":"Банк нарастил прибыль."}</script><div>меню</div>')
    assert news.page_text(ld) == "Банк нарастил прибыль." and news.page_published(ld) == "2026-07-09T10:18:13+03:00"
    sl = '<ul><li class="date">30 сентября 2026, 22:36</li></ul>'
    assert news.page_published(sl) == "2026-09-30T22:36:00+03:00"
    pats = config.sources()["news"]["pdf_patterns"]
    link = "https://cdn.tbank-online.com/static/documents/0d765044-5a4c-4e54-85f0-890eba01261b.pdf"
    assert news.pdf_links(f'<a href="{link}">документ</a> и <a href="https://example.com/x.pdf">x</a>', pats) == [link]


def test_telegram_previews():
    doc = ('<div class="tgme_widget_message_wrap"><div data-post="channel/900001"><div class="tgme_widget_message_text" '
           'dir="auto">Совет директоров рекомендовал дивиденды <a href="https://example.org/a">ссылка</a></div>'
           '<time datetime="2026-11-19T07:10:41+00:00"></time></div></div>')
    posts = news.telegram_posts(doc)
    assert posts == [{"post": "channel/900001", "time": "2026-11-19T07:10:41+00:00",
                      "text": "Совет директоров рекомендовал дивиденды ссылка", "links": ["https://example.org/a"]}]


def test_days_to_scan_catch_up_missed_days():
    cfg = {"lookback_days": 1, "catchup_days": 7}
    today = date(2026, 10, 7)
    done = [f"2026-10-0{d}" for d in (3, 4)]
    days = [d.isoformat() for d in news.days_to_scan(today, cfg, done)]
    assert days == ["2026-10-07", "2026-10-06", "2026-10-05", "2026-10-02", "2026-10-01", "2026-09-30"]


def test_collect_keeps_items_and_raw(monkeypatch, tmp_path):
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    ctx = Context(store=store, today=date(2026, 10, 2), company=config.company(), cfg=config.sources(),
                  getter=FakeGetter(moment="2026-10-02T11:00:00+00:00"))
    r = news.collect(ctx)
    assert r.status == OK, r.reasons
    items = store.read_state("news/items.json")["items"]
    by_kind = {v["kind"]: (url, v) for url, v in items.items()}
    assert set(by_kind) == {"interfax", "kommersant", "tass"}
    assert all(v["topic"] == "dividend" for _, v in by_kind.values())
    url, item = by_kind["interfax"]
    assert url.endswith("/business/9000301") and item["published"] == "2026-10-02T13:35:00+03:00"
    assert "4,7 рубля на акцию" in item["text"] and item["first_seen"]
    assert by_kind["tass"][1]["text"].startswith('Акционеры "Т-Технологий" одобрили')        # статья не качается
    assert store.raw_days("news") and store.read_state("news/items.json")["days"]["interfax"]
    asked = [c["url"] for c in ctx.getter.calls]
    assert not any("9000302" in u or "9000402" in u for u in asked)                         # чужие новости не качаются
    assert any(u.endswith("/forum/news/T/") for u in asked)                                 # тикер — из книги
    down = http.FetchError("x", 503, "HTTP 503")
    dead = FakeGetter(overrides={host: down for host in ("interfax.ru", "smart-lab.ru", "kommersant.ru",
                                                         "vedomosti.ru", "tass.ru")})
    r = news.collect(Context(store=Store(tmp_path / "s2"), today=date(2026, 10, 2), company=config.company(),
                             cfg=config.sources(), getter=dead))
    assert r.status == FAILED and "ни одна лента" in r.detail


# ------------------------------------------------------------------ числа месячного релиза из текста

def test_release_month_reads_period_phrases_not_substrings():
    """Месяц текста — по фразам периода целыми словами; «332,7 млрд» — не «7 м», «марте» — не май."""
    assert news.release_month("Прибыль выросла до 1 332,7 млрд рублей.") is None          # нет фразы периода
    assert news.release_month("В мае банк заработал 150,2 млрд рублей по РСБУ.") == 5
    assert news.release_month("В марте банк заработал 150,2 млрд рублей по РСБУ.") == 3
    assert news.release_month("Мартовский релиз: за два месяца прибыль составила 300 млрд.") == 2
    assert news.release_month("За январь-сентябрь 2026 года прибыль выросла, в августе была ниже.") == 9
    assert news.release_month("По итогам первого полугодия банк заработал 859,3 млрд.") == 6
    assert news.release_month("Банк в 1кв получил 404,5 млрд руб. чистой прибыли по РСБУ.") == 3
    assert news.release_month("Чистая прибыль по РСБУ за 2025 год составила 1 трлн 690,1 млрд рублей.") == 12
    assert news.release_month("Активы за год выросли на 12%.") is None                    # «за год» — год к году
    assert [news.cumulative_months(s) for s in ("за 12 месяцев", "по итогам восьми месяцев", "в январе-мае")] \
        == [12, 8, 5]


def test_numbers_of_the_release_text_belong_to_its_month():
    """Число берётся только из фразы, которая называет месяц релиза: нарастающее — за столько же месяцев."""
    nine = ("За январь-сентябрь 2026 года банк нарастил чистую прибыль по РСБУ на 18% - до 150,3 млрд рублей. "
            "Чистая прибыль банка за сентябрь составила 18,5 млрд рублей против 24,4 млрд рублей в августе.")
    got = news.extract_release_numbers(nine, month="2026M09")
    assert got["np_ytd"][0] == pytest.approx(150.3) and got["np_m"][0] == pytest.approx(18.5)
    assert news.extract_release_numbers(nine, month="2026M08") == {}
    year = ("INTERFAX.RU - В 2026 году банк поднял чистую прибыль по РСБУ без учета поправок на события после "
            "отчетной даты (СПОД) на 6,0% - до рекордных 1795,9 млрд рублей, годом ранее было 1700,0 млрд рублей "
            "прибыли за 2025 год, сообщил банк. В декабре чистая прибыль выросла на 5,0% - до 132,2 млрд рублей.")
    assert news.period_months(year) == (12,)
    got = news.extract_release_numbers(year, month="2026M12")
    assert got["np_ytd"][0] == pytest.approx(1795.9) and got["np_m"][0] == pytest.approx(132.2)
    assert "np_ytd" not in news.extract_release_numbers(year, month="2025M12")       # год фразы — другой
    coarse = news.extract_release_numbers("Чистая прибыль по РСБУ за 8 месяцев выросла до 1,332 трлн рублей.")
    assert "np_ytd" not in coarse                                                    # грубое число не берётся
    head = news.extract_headline("ЗА 8 МЕСЯЦЕВ БАНК УВЕЛИЧИЛ ЧИСТУЮ ПРИБЫЛЬ ПО РСБУ ДО 131,8 МЛРД РУБ.", month="2026M08")
    assert head["np_ytd"][0] == pytest.approx(131.8)
    assert news.extract_headline("ЗА 8 МЕСЯЦЕВ БАНК УВЕЛИЧИЛ ЧИСТУЮ ПРИБЫЛЬ ПО РСБУ ДО 131,8 МЛРД РУБ.", month="2026M07") == {}


# ------------------------------------------------------------------ фикстуры — сочинённые тексты

NEWS_FIXTURES = sorted(p.name for p in (FIX / "news").iterdir())


def test_the_excerpt_check_catches_a_copied_sentence_and_passes_a_reworded_one():
    """Сверка фикстур с настоящими текстами сама проверена: выписанное предложение ловится, в том числе под
    другой разметкой и с другим тире; пересказ своими словами с теми же числами — нет."""
    article = plain_text("<p>Банк за девять месяцев получил 1 234,5 млрд рублей прибыли — на 7% больше, "
                         "чем годом ранее.</p><p>Капитал вырос до 5,678 трлн рублей.</p>")
    corpus = {"статья": article}
    copied = plain_text("<div>Лента.<br/>Банк за девять месяцев получил 1 234,5 млрд рублей прибыли - на 7% "
                        "больше, чем годом ранее.</div>")
    size, piece, where = longest_common_run(copied, corpus)
    assert size >= 80 and where == "статья" and piece.startswith("Банк за девять месяцев")
    reworded = plain_text("<p>Прибыль банка с января по сентябрь — 1 234,5 млрд рублей, плюс 7% за год.</p>")
    assert longest_common_run(reworded, corpus)[0] < NEWS_COMMON_RUN_LIMIT
    both = longest_common_runs({"выписка": copied, "пересказ": reworded, "пусто": ""}, corpus)
    assert both["выписка"][0] == size and both["пересказ"][0] < NEWS_COMMON_RUN_LIMIT and both["пусто"] == (0, "", "")
    assert plain_text("<!-- пометка --><a href='https://example.org/x'>слово</a> https://example.org/y ёж") \
        == "слово еж"
    # тексты внутри тестов — тот же вопрос: строка файла кода читается с номером строки
    inline = python_texts(Path(__file__), shortest=NEWS_COMMON_RUN_LIMIT)
    assert any(text.startswith("INTERFAX.RU - В 2026 году банк поднял") for text in inline.values())


@pytest.mark.parametrize("name", NEWS_FIXTURES + ["../issuer_docs/press_page.html"])
def test_every_news_fixture_says_it_is_synthetic(name):
    """Каждая фикстура новостей и страница эмитента помечены в самом файле: сочинённый текст, не сохранённая
    страница; контактов и почт в фикстурах нет."""
    assert len(NEWS_FIXTURES) >= 5
    text = _t(name)
    assert "<!-- синтетика:" in text, name
    assert "@" not in text and "+7" not in text, name


@pytest.mark.archive
def test_news_fixtures_share_no_long_piece_with_the_real_texts():
    """Фикстуры — сочинённые тексты, не сокращение и не пересказ настоящих статей и документов: архив
    настоящих текстов этапа 1 (папка передачи) не содержит ни одного куска фикстуры длиной от
    `NEWS_COMMON_RUN_LIMIT` знаков; общее короче — термины и схема чисел, которую читает разбор. Тот же
    вопрос — к текстам внутри тестов и кода индикаторов (строки и комментарии); кусок без пробела — адрес
    или имя файла, а не текст."""
    root = os.environ.get("BANK_HANDOFF_DIR")
    if not root:
        pytest.skip("нужна папка передачи (BANK_HANDOFF_DIR)")
    corpus = real_news_corpus(Path(root))
    assert len(corpus) >= 5, f"архив настоящих текстов неполон: {len(corpus)} файлов"
    texts = {name: plain_text(_t(name)) for name in NEWS_FIXTURES}
    here = Path(__file__).resolve().parent
    code = [*sorted(here.glob("test_ind_*.py")), here / "support_ind.py",
            *sorted((here.parent / "indicators").glob("*.py"))]
    assert len(code) >= 30
    for path in code:
        texts.update(python_texts(path, shortest=NEWS_COMMON_RUN_LIMIT))
    assert len(texts) > len(NEWS_FIXTURES) + 100
    bad = [f"{name}: {size} знаков «{piece}» — {where}"
           for name, (size, piece, where) in longest_common_runs(texts, corpus).items()
           if size >= NEWS_COMMON_RUN_LIMIT and " " in piece.strip()]
    assert not bad, "тексты репозитория повторяют настоящие:\n" + "\n".join(bad)
