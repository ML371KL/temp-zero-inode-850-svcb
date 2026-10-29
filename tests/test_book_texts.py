# -*- coding: utf-8 -*-
"""Тексты книги: строки, которые печатает витрина (источники и имена осей, каналы дисконта, подписи книги), — словами
для владельца; идентификаторы суждений шаблона описаны в тексте книги; версия книги одна в шаблоне, тексте и README;
таблица осей текста — все оси книги; пути ключей, названные в тексте, есть в книге; гигиена публичного репозитория в
каталоге книги (поток book; печатаемые строки и гигиена — метка `tact`). Текст книги `ASSUMPTIONS-BOOK.md` и README
каталога пишутся после машинной части: пока их нет, тесты текста пропускаются с названной причиной."""
from __future__ import annotations

import re

import pytest

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

BOOK_MD = S.BOOK_DIR / "ASSUMPTIONS-BOOK.md"
README = S.BOOK_DIR / "README.md"
SECTIONS = ("Главное", "Миры", "Режимы", "ЧПД", "Капитал", "Дивиденды", "Оценка", "Оси полосы", "Обратный расчёт",
            "Гейты", "Ограничения")
FIELDS = ("**Ключи", "**Ось", "**Класс", "**Обоснование", "**Чем может ошибаться")
EVIDENCE_AREAS = ("worlds_bank", "nii", "path")    # листы книги Совкомбанка в дереве с README (листы калибровки — в папке передачи)
# Источники суждений осей (сводка этапа 1, раздел 1.2): что обязана напечатать витрина у оси — слово в слово
SOURCES = {  # источники главных осей книги Совкомбанка — так, как их печатает выпуск (комментарий первого пути оси)
    "Передача ключевой в ЧПМ (опр. банка −0,15…+0,03; базис движка)": "Регрессия маржи на ключевую −0,06 (−0,15…+0,03), пары кварталов −0,05",
    "ЧПМ мира N на составе якоря (опр. банка 6,92–7,28 %; ключ ядра)": "Окно L 2023 года, перенесённое на состав баланса якоря: 7,13–7,21 %",
    "LT-спред оптового фондирования": "Облигации, субординированный долг и межбанк по ставкам примечаний МСФО 6М2026",
    "Сжатие маржи при высокой ставке: доля на кредитных книгах (A-N8)": "Сжатие истории книг 0,395 — вне области гейта; центр — граница области 0,48",
    "Запас менеджмента над требованием (оба норматива; глиссада — связкой)": "Запас Н1.0 банка над требованием: среднее скользящих 4 кварталов 2025–2026",
    "Инструменты капитала банка (сдвиг пути)": "Добавочный и дополнительный капитал банка на 01.07.2026 без прибыли",
    "Премия роста средств клиентов к сектору (2027–2029)": "Середина между ростом средств в 2025–2026 годах и ростом, нужным балансу",
    "CoR ипотеки к общей (множитель книги)": "CoR книг к общей по МСФО: середина окон 2024–1П2026, 2019–2025 и 1П2026",
    "Налог: эффективная ставка 23,5–24,9 %": "Скользящие 4 квартала без всех разовых статей: 23,5–24,9 %, среднее 24,0 %",
    "β_E": "Недельная доходность к индексу полной доходности, вся история с IPO",
}


@pytest.fixture(scope="module")
def text() -> str:
    if not BOOK_MD.exists():
        pytest.skip("текста книги ASSUMPTIONS-BOOK.md ещё нет — его пишут после машинной части")
    return BOOK_MD.read_text(encoding="utf-8")


@pytest.mark.docs
def test_the_book_has_every_section(text):
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    for sec in SECTIONS:
        assert any(sec in h for h in heads), sec


@pytest.mark.docs
def test_every_judgement_carries_all_fields(text):
    blocks = re.split(r"(?m)^### ", text)[1:]
    assert len(blocks) >= 50
    for b in blocks:
        title = b.splitlines()[0]
        assert re.match(r"A-[A-Z]+\d+[a-z]*\. ", title), title
        body = b.split("\n## ")[0]
        missing = [f for f in FIELDS if f not in body]
        assert missing == [], (title, missing)
        assert re.search(r"\*\*Класс:\*\* ([ABC])", body), title         # класс надёжности A / B / C


@pytest.mark.docs
def test_template_ids_are_described_in_the_book(text):
    tpl = (S.BOOK_DIR / "assumptions_template.yaml").read_text(encoding="utf-8")
    ids = set(re.findall(r"\bA-[A-Z]+\d+[a-z]*\b", tpl))
    heads = set(re.findall(r"(?m)^### (A-[A-Z]+\d+[a-z]*)\.", text))
    assert ids and ids <= heads, sorted(ids - heads)


@pytest.mark.docs
def test_key_paths_named_in_the_book_exist(text):
    book = S.built_book()
    bad = []
    for tok in set(re.findall(r"`([a-z_]+(?:\.[A-Za-z0-9_<>{}, .]+)+)`", text)):
        tok = tok.strip()
        if tok.split(".")[0] not in S.TOP or " " in tok.replace(", ", ","):
            continue
        for p in S._expand(tok.replace(", ", ","), book):
            if "*" not in p and "<" not in p and not p.endswith(".fv_share") and S._applies(p, book) and not S.has(book, p):
                bad.append(p)
    assert bad == []


@pytest.mark.docs
def test_the_version_is_one_in_the_template_text_and_readme(text):
    version = S.template()["meta"]["version"]
    assert text.splitlines()[0].endswith(f"версия {version}")
    assert f"`book-{version}`" in text
    if not README.exists():
        pytest.skip("README каталога книги ещё нет")
    readme = README.read_text(encoding="utf-8")
    assert re.search(rf"(?m)^\| {re.escape(version)} \| ", readme)
    for s in ("build_assumptions.py", "worlds_recipe.py --check", "tests/test_book_"):
        assert s in readme, s


@pytest.mark.docs
def test_the_axes_table_lists_every_axis_of_the_book(text):
    """Раздел осей: строка таблицы на каждую ось книги (первый путь оси назван в строке), номера подряд."""
    unc = S.template()["valuation"]["uncertainty"]
    a = text.index(next(ln for ln in text.splitlines() if ln.startswith("## ") and "Оси полосы" in ln))
    nxt = text.find("\n## ", a + 5)
    section = text[a:nxt if nxt > 0 else len(text)]
    rows = [ln for ln in section.splitlines() if re.match(r"\| \d+ \| ", ln)]
    assert [int(ln.split("|")[1]) for ln in rows] == list(range(1, len(unc["axes"]) + len(unc["off_band_axes"]) + 1))
    for ax in unc["axes"] + unc["off_band_axes"]:
        first, last = ax["paths"][0].split(".")[0], ax["paths"][0].split(".")[-1]
        assert any(first in ln and last in ln for ln in rows), ax["name"]


@pytest.mark.docs
def test_the_evidence_readme_names_every_area():
    ev = (S.EVIDENCE / "README.md").read_text(encoding="utf-8")
    for area in EVIDENCE_AREAS:
        assert f"`{area}/`" in ev, area
        assert (S.EVIDENCE / area / "README.md").exists(), area
    assert "derive_on_engine.py" in ev


@pytest.mark.tact
def test_axis_sources_names_and_channels_are_written_for_the_owner():
    """Строки книги, которые печатает витрина: источник суждения каждой оси полосы — комментарий машинной книги к
    первому пути оси, разобранный ядром, — найден (не запасная подпись «book-…, ось …»), не длиннее 80 знаков и написан
    словами: без рабочих пометок, имён листов и ключей, меток класса, дат без года и версий без имени; то же — имена
    осей, имена и основания каналов дисконта за управление, имена строк обратного расчёта, заголовки справочных
    вариантов."""
    book = S.template()
    sources = S.axis_sources()
    axes = book["valuation"]["uncertainty"]["axes"]
    assert list(sources) == [a["name"] for a in axes]
    bad = {}
    for name, src in sources.items():
        issues = S.printed_issues(src) + S.printed_issues(name)
        if src.startswith(("книга ", "book-")) or not src.strip():
            issues.append("нет комментария-источника у первого пути оси")
        if len(src) > 80 or src.endswith("…"):
            issues.append(f"источник обрезан или длиннее 80 знаков ({len(src)})")
        if src.count("(") != src.count(")"):
            issues.append("скобка в источнике не закрыта: фраза обрезана внутри скобок")
        if src[:1].islower() and not src.startswith("общая запись"):
            issues.append("источник начинается со строчной буквы")
        if issues:
            bad[name] = issues
    assert bad == {}
    for name, want in SOURCES.items():
        assert sources[name] == want, name
    for ch in book["valuation"]["governance"]["components"]:
        assert S.printed_issues(ch["basis"]) == [] and S.printed_issues(ch["name"]) == [], ch["id"]
    for a in book["valuation"]["reverse_dcf"]["axes"]:
        assert S.printed_issues(a["name"]) == [], a["name"]
    for v in book["valuation"]["reference_variants"]:                      # заголовки справочных вариантов — экран «Книга»
        assert S.printed_issues(v["title"]) == [] and S.printed_issues(v.get("note", "")) == [], v["id"]
    for w in ("Веса миров", "Инфляция мира M"):
        assert book["worlds"]["source"]["origin"] in sources[w]                    # запись миров — с именем и версией


@pytest.mark.tact
def test_labels_gate_titles_and_guidance_words_are_written_for_the_owner():
    """Подписи книги (их печатают выпуск и тревоги) и подписи узлов гайденса — без рабочих пометок, имён листов и
    ключей; имя команды ручного ввода в тревоге сборщика — единственное служебное слово, оно в обратных кавычках."""
    book = S.template()
    bad = {}
    for path, value in S.leaves(book["meta"]["labels"]):
        if path.endswith(".basis") or not isinstance(value, str):
            continue
        shown = re.sub(r"`[^`]*`", "", re.sub(r"\{[a-z_]+\}", "…", value))
        issues = S.printed_issues(shown)
        if issues:
            bad[path] = issues
    for item in book["checks"]["guidance_items"]:
        issues = S.printed_issues(item["title"]) + S.printed_issues(item.get("words", ""))
        if issues:
            bad[item["key"]] = issues
    for r in book["regimes"]["ids"]:
        assert S.printed_issues(book["regimes"][r]["name"]) == []
    for s in book["capital"]["reg_scenarios"]["ids"]:
        assert S.printed_issues(book["capital"]["reg_scenarios"][s]["name"]) == []
    for b, spec in book["nii"]["books"].items():
        assert S.printed_issues(spec["name"]) == [], b
    assert bad == {}


@pytest.mark.tact
def test_book_directory_is_clean_for_a_public_repository():
    """В каталоге книги нет путей пользователя, почт, адресов IPv4, имён локальных папок передачи, первички (PDF,
    XLSX) и ответов брокерского API (ни файлом, ни именами его методов и полей)."""
    user = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/home/[a-z_][a-z0-9_-]*/", re.I)
    email = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
    octet = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    ipv4 = re.compile(rf"(?<![\w.]){octet}\.{octet}\.{octet}\.{octet}(?![\w.])")
    broker = re.compile("|".join(a + b for a, b in (("Get", "Dividends"), ("Instruments", "Service"), ("tinvest_", "samples"),
                                                     ("dividend", "Net"), ("lastBuy", "Date"))))
    bad = []
    for p in S.BOOK_DIR.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        assert p.suffix.lower() not in (".pdf", ".xlsx", ".xls", ".docx"), p      # первичка — только ссылкой
        t = p.read_text(encoding="utf-8", errors="replace")
        for name, rx in (("путь пользователя", user), ("почта", email), ("IPv4", ipv4), ("ответ брокерского API", broker)):
            if rx.search(t):
                bad.append((str(p.relative_to(S.ROOT)), name, rx.search(t).group(0)))
    assert bad == []


def test_the_run_summary_prints_the_headline_with_the_print_step_of_the_book():
    """`run_output.txt` печатает заголовок знаками шага печати книги, как выпуск (шаг 0,1 ₽ — «печать 14.8», а не
    «печать 15»): медиана, полоса 80 % и точка; цена рынка — как в книге (10.105), DPS — двумя знаками."""
    import json
    from model.book import load_book, load_facts
    from model.book_results import render_run_output
    book = load_book(facts=load_facts())
    results = json.loads((S.BOOK_DIR / "results.json").read_text(encoding="utf-8"))
    h = results["headline"]
    step = float(book.get("valuation.headline.print_step"))
    nd = len(f"{step:g}".partition(".")[2])
    assert step == 0.1 and nd == 1
    text = render_run_output(results, book)
    f = lambda x: f"{x:,.{nd}f}".replace(",", " ")  # noqa: E731
    assert f"→ печать {f(h['printed_median'])};" in text and f"(печать {f(h['printed_point'])})" in text
    assert f"(печать {f(h['printed_band80'][0])}–{f(h['printed_band80'][1])})" in text
    assert f"рынка {h['market']:g})" in text and "10.105" in text
    committed = (S.BOOK_DIR / "run_output.txt").read_text(encoding="utf-8")
    assert f"→ печать {f(h['printed_median'])};" in committed, "сводка таблиц книги — той же печати"
