"""Витрина: статика Pages, CSP и тема, бюджет веса, литералы, гигиена (docs/DASHBOARD.md §1, §2, §5).

* одна CSP в двух местах — `web/_headers` (статика) и `functions/_middleware.js`
  (ответы функций), посимвольно одинаковая; скрипт темы — по sha256 текста с LF;
* вся витрина (`web/`) — меньше 332 000 байт, файлы — в своих потолках (DASHBOARD §1);
* в витрине и функциях нет литералов эмитента (имя с границами слова, тикер строковым литералом,
  регномер), годов и дат; имя — только статическим текстом в index.html и 404.html;
* карточка панели не рисуется без своего узла выпуска; слова общей формы выбирают данные; у ROE и
  P/E есть подпись базиса; оценочная дата не печатается точной; «на акцию» подписано делителем;
* ни дисклеймеров, ни сторонних адресов, ни управляющих байтов, ни CRLF;
* ряды графиков держат контраст ≥ 3 : 1 к карточке в обеих темах; кегль ≥ 12,5 px;
* печать по контракту (AUDIT-1): свободный текст — с запятой, но версии и ссылки на разделы как есть;
  эквивалент в прибыли — уровень, а не чувствительность; одна P(ниже рынка) — одна функция; коды — словами;
* печать по второму аудиту (AUDIT-2): диапазон оси-словаря — парами концов, линия графика не идёт через
  нераскрытое, ноль на столбцах подписан, легенда — из нарисованного, чувствительности — целыми рублями,
  пустой интервал нау-каста — словами, шапка карточки с переключателем на телефоне — в две строки;
* печать по проверке W3 (решение P7): слово после числа — по напечатанному числу («1,6 года»), счётчики
  проверок согласованы с числом, сверка с контрольной моделью — в единице строки по виду допуска,
  источник истории дивидендов — словами выпуска.

Весь модуль — тесты такта (метка `tact`, INTERFACES §9): статика без Node, доли секунды.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.support_literals import plain_regnum, regnum_patterns

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
FUNCTIONS = ROOT / "functions"
MIDDLEWARE = FUNCTIONS / "_middleware.js"
DOOR = FUNCTIONS / "api" / "model.js"
APP = (WEB / "app.js").read_text(encoding="utf-8")
CSS = (WEB / "styles.css").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
PAGE_404 = (WEB / "404.html").read_text(encoding="utf-8")
# Бюджет витрины — DASHBOARD §1: все файлы `web/` вместе.
FRONT_BUDGET = 342_000
# Потолки по файлам — docs/DASHBOARD.md §1 (байты).
FILE_BUDGETS = {"app.js": 288_000, "styles.css": 43_000}
SMALL_FILES_BUDGET = 9_000   # index.html, 404.html, _headers, _routes.json, favicon.svg
SCREENS = ["overview", "market", "model", "report", "capital", "book"]


def code_only(text: str) -> str:
    """Код без комментариев: объяснение в комментарии не выдаёт себя за код."""
    out = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", out)


def _theme_script(html: str = HTML) -> str:
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match, "нет инлайн-скрипта темы (<script> без атрибутов)"
    return match.group(1).replace("\r\n", "\n")


def _theme_hash() -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(_theme_script().encode("utf-8")).digest()).decode("ascii")


def _headers_csp() -> str:
    found = re.findall(r"^\s+Content-Security-Policy: (.+)$", (WEB / "_headers").read_text(encoding="utf-8"), re.M)
    assert len(found) == 1, found
    return found[0].strip()


def _middleware_csp() -> str:
    src = MIDDLEWARE.read_text(encoding="utf-8")
    hash_ = re.search(r'THEME_SCRIPT_HASH = "([^"]+)"', src).group(1)
    body = re.search(r"const CSP = \[(.*?)\]\.join", src, re.S).group(1)
    parts = [m.group(1) for m in re.finditer(r"[`\"]([^`\"]+)[`\"]", body)]
    return "; ".join(p.replace("${THEME_SCRIPT_HASH}", hash_) for p in parts)


# ── CSP и тема ──

def test_csp_is_the_same_in_headers_and_middleware():
    assert _headers_csp() == _middleware_csp(), f"политики разошлись:\n  _headers:   {_headers_csp()}\n  middleware: {_middleware_csp()}"


def test_theme_script_hash_matches_csp():
    want = _theme_hash()
    have = re.search(r'THEME_SCRIPT_HASH = "([^"]+)"', MIDDLEWARE.read_text(encoding="utf-8")).group(1)
    lines = f'\nfunctions/_middleware.js: const THEME_SCRIPT_HASH = "{want}";\nweb/_headers: ... script-src \'self\' \'{want}\'; ...'
    assert have == want, "хэш скрипта темы устарел; строки на замену:" + lines
    assert f"'{want}'" in _headers_csp(), "хэш скрипта темы в web/_headers устарел; строки на замену:" + lines


def test_csp_forbids_third_party_and_inline_scripts():
    csp = _headers_csp()
    for directive in ("default-src 'self'", "connect-src 'self'", "font-src 'self'", "object-src 'none'", "base-uri 'none'",
                      "form-action 'none'", "frame-ancestors 'none'", "img-src 'self' data:"):
        assert directive in csp, directive
    script_src = re.search(r"script-src ([^;]+)", csp).group(1)
    assert re.fullmatch(r"'self' 'sha256-[A-Za-z0-9+/]{43}='", script_src.strip()), script_src
    headers = (WEB / "_headers").read_text(encoding="utf-8")
    assert "X-Content-Type-Options: nosniff" in headers and "Referrer-Policy: no-referrer" in headers and "Permissions-Policy:" in headers


def test_theme_rule_is_the_family_rule_in_one_place():
    script = _theme_script()
    assert 'var DAY = "tzi-theme", NIGHT = "tzi-theme-tonight", FROM = 20, TO = 7;' in script, "ключи и окно темы — общие для банковских витрин"
    assert "window.__theme = { isNight: isNight, resolve: resolve, remember: remember" in script
    assert "getHours" not in APP, "часы зрителя читает только скрипт темы"
    assert "window.__theme.remember(next)" in APP


def test_index_has_the_theme_script_and_the_app_only():
    assert HTML.count("<script") == 2, "в index.html ровно два скрипта: тема (инлайн) и /app.js"
    assert '<script src="/app.js" defer></script>' in HTML
    head = HTML.split("</head>")[0]
    assert head.index("<script>") < head.index('rel="stylesheet"'), "тема ставится до загрузки стилей"


def test_404_is_a_real_page_with_the_same_theme_script():
    assert "404" in PAGE_404 and 'href="/"' in PAGE_404 and "/styles.css" in PAGE_404 and PAGE_404 != HTML
    assert "#capital" in PAGE_404 and "#debt" not in PAGE_404
    assert _theme_script(PAGE_404) == _theme_script(), "404 вечером тоже тёмная: тот же скрипт байт в байт (тот же хэш CSP)"


# ── маршруты и граница /api/ ──

def test_routes_limit_functions_to_the_api():
    assert json.loads((WEB / "_routes.json").read_text(encoding="utf-8")) == {"version": 1, "include": ["/api/*"], "exclude": []}


def test_api_allowlist_matches_functions():
    listed = set(re.findall(r'"(\w+)"', re.search(r"ALLOWED_API = new Set\(\[([^\]]*)\]\)", MIDDLEWARE.read_text(encoding="utf-8")).group(1)))
    actual = {p.stem for p in (FUNCTIONS / "api").glob("*.js")}
    assert listed == actual == {"model"}, (listed, actual)


def test_the_door_reads_the_data_repository_from_pages_variables():
    """Адреса и схема — переменные Pages (wrangler.toml [vars]): в функции нет имени эмитента."""
    src = DOOR.read_text(encoding="utf-8")
    for name in ("DATA_SCHEMA", "DATA_PAGES_URL", "DATA_RAW_URL"):
        assert f'"{name}"' in src, name
    assert "https://" not in code_only(src), "адрес источника — только из переменных Pages"
    toml = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
    vars_ = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', toml.split("[vars]")[1], re.M))
    assert vars_["DATA_SCHEMA"] == "svcb-v1"
    assert vars_["DATA_PAGES_URL"] == "https://ml371kl.github.io/temp-zero-inode-850-svcb-data/latest.json"
    assert vars_["DATA_RAW_URL"] == "https://raw.githubusercontent.com/ML371KL/temp-zero-inode-850-svcb-data/release/latest.json"
    assert 'name = "tzi-850-svcb"' in toml and 'pages_build_output_dir = "web"' in toml
    assert "UPSTREAM_TIMEOUT_MS = 8000" in src and '"user-agent required"' in src


def test_the_door_schema_is_the_release_schema():
    """Дверь отдаёт только выпуск схемы `svcb-v1`: её настройка равна схеме обеих форм фикстуры
    (равенство ключу книги `meta.schema` держит тест эксплуатации)."""
    toml = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
    for path in (ROOT / "tests" / "fixtures" / "payload-sample.json", ROOT / "tests" / "web" / "payload-generic.json"):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert fixture["schema"] == "svcb-v1" and f'DATA_SCHEMA = "{fixture["schema"]}"' in toml, path.name
    door = DOOR.read_text(encoding="utf-8")
    assert "data.schema !== schema" in door and "svcb-v1" not in door, "схему дверь сверяет с переменной, имени схемы в коде нет"


# ── вес ──

def test_front_weight_within_budget():
    files = [p for p in WEB.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    assert total < FRONT_BUDGET, f"витрина весит {total} байт при потолке {FRONT_BUDGET}"
    for p in files:
        cap = FILE_BUDGETS.get(p.name, SMALL_FILES_BUDGET)
        assert p.stat().st_size <= cap, f"{p.name}: {p.stat().st_size} байт при потолке {cap}"
    assert {p.name for p in files} == {"index.html", "404.html", "app.js", "styles.css", "favicon.svg", "_headers", "_routes.json"}


# ── литералы и гигиена ──

# Имя эмитента — с границами слова (`tcs` без них совпал бы с `toUTCString`); шаблоны прежних копий семейства
# остаются: остаток копии обязан краснеть. Тикер из одной буквы (Т — образец кода) — строковым литералом в кавычках.
# Имя и тикер этой копии — словами (`совком…`, `sovcom…`: и имя, и хост эмитента; `svcb…`), прежнее имя — тоже;
# слова панели ВТБ (источник инструментов быстрого круга) — как остаток чужой копии.
COMPANY = re.compile(r"сбер|sber|1481|\b(?:т-технолог\w*|t-technolog\w*|т-банк\w*|t-?bank\w*|тинькофф\w*|tinkoff\w*|tcs|ткс|2673|росбанк\w*|rosbank\w*"
                     r"|втб\w*|vtb\w*|внешторгбанк\w*|vneshtorgbank\w*"
                     r"|совком\w*|sovcom\w*|svcb\w*|буйкомбанк\w*)\b", re.I)
TICKER_LITERAL = re.compile(r"""(["'`])T\1""")
TICKER_IN_TEXT = re.compile(r"(?<![A-Za-z0-9_-])T(?![A-Za-z0-9_-])|2673|(?i:\bSVCB\w*)")
# Регномер этой копии — короткое число (963, короче четырёх знаков): такое число может встретиться в арифметике и
# разметке витрины, поэтому он ищется строковым литералом и числом рядом со словом о регномере
# (tests/support_literals.py), не голым числом.
ISSUER_REGNUM = "963"
REGNUM = regnum_patterns(ISSUER_REGNUM)
YEAR = re.compile(r"(?<![\w.])(?:19[5-9]\d|20\d\d|2100)(?![\w.])")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}\.\d{2}\.\d{4}\b")


def _code_files():
    return [WEB / "app.js", WEB / "styles.css", WEB / "favicon.svg", WEB / "_headers", WEB / "_routes.json", *FUNCTIONS.rglob("*.js")]


def test_the_front_carries_no_company_literals():
    """Имя, тикеры и регномер — только из выпуска (`meta.company`); витрина — общий каркас семейства."""
    assert plain_regnum(ISSUER_REGNUM), "регномер этой копии — «обычное число»: правило — строкой и в контексте"
    for path in _code_files():
        text = path.read_text(encoding="utf-8")
        hit = COMPANY.search(text) or TICKER_LITERAL.search(text) or next(filter(None, (p.search(text) for p in REGNUM)), None)
        assert not hit, f"{path.relative_to(ROOT)}: литерал эмитента «{hit.group(0)}»"
    for name, text in (("index.html", HTML), ("404.html", PAGE_404)):
        visible = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|svg|style)\b.*?</\1>", " ", text))
        assert not TICKER_IN_TEXT.search(visible), f"{name}: тикер или регномер — только из выпуска"
        assert not any(p.search(text) for p in REGNUM), f"{name}: регномер — только из выпуска"
        assert not re.search(r"сбер|sber|1481|т-технолог|t-technolog|т-банк|t-?bank|тинькофф|tinkoff|2673|росбанк|втб|vtb",
                             text, re.I), (
            f"{name}: остаток чужой копии")
        # имя эмитента на странице — только статическим текстом: заголовок, описание, подпись бренда
        assert "Совкомбанк — справедливая стоимость" in text or "Совкомбанк, справедливая стоимость" in text, name
    for probe in ("ТКС Холдинг", "T-Bank", "tcs group", "Росбанка", '"T"', "t-technologies", "группа ВТБ", "втб", '"VTBR"',
                  "https://www.vtb.ru/ir/", "Внешторгбанк", "VTB Group", "группа Совкомбанк", "совкомбанк", '"SVCB"',
                  "https://prod-api.sovcombank.ru/finance-report/", "Буйкомбанк", "Sovcombank Group"):
        assert COMPANY.search(probe) or TICKER_LITERAL.search(probe), probe
    for probe in ("toUTCString", "T-Invest", "интербанк", "12673", "2026-10-07T16:05"):
        assert not COMPANY.search(probe) and not TICKER_LITERAL.search(probe), probe
    # регномер 963: то же число в арифметике и разметке — не находка; строковый литерал и число рядом со словом о
    # регномере — находка
    for probe in ("fmt.num(v, Math.abs(v) < 963 ? 2 : 0)", "`${fmt.num((m.bytes || 0) / 963)} КБ`", "API_TIMEOUT_MS / 963",
                  "const STEP = 963;", "width: 963px", "1963", "963.5"):
        assert not any(p.search(probe) for p in REGNUM), probe
    for probe in ('regnum: "963"', "const REGNUM = 963;", "cbr_regnum === 963", "банк, рег. № 963", 'id === "963"',
                  "лицензия Банка России № 963",
                  # тег запроса службы форм, английские слова, запись с подчёркиванием, параметр адреса, соседняя строка
                  "`<CredorgNumber>${963}</CredorgNumber>`", "<CredprgNumber>963</CredprgNumber>", "const regNo = 963;",
                  "const registrationNumber = 963;", "license: 963", "const bankId = 963;", "const REGNUM = 96_3;",
                  "fetch(`${API}?id=963`)", "const REGNUM =\n\t963;"):
        assert any(p.search(probe) for p in REGNUM), probe
    for probe in ("const regnum = company(d).cbr_regnum;\n\nconst STEP = 963;", "fetch(`${API}?limit=963`)", "963_000_000"):
        assert not any(p.search(probe) for p in REGNUM), probe
    for probe in ("SVCB", "тикер svcb", "рег. № 2673", "T"):
        assert TICKER_IN_TEXT.search(probe), probe
    assert not TICKER_IN_TEXT.search("Совкомбанк — справедливая стоимость акции, T-Invest"), "имя эмитента на странице — статический текст"
    assert re.search(r"function company\(d\) \{[^}]*company\)\.name", APP) and re.search(r"function ticker\(d\)[^\n]*main_ticker", APP)
    assert "company(DATA)" in APP, "заголовок вкладки — имя из выпуска"


def test_the_code_carries_no_years_or_dates():
    for path in [WEB / "app.js", *FUNCTIONS.rglob("*.js")]:
        code = code_only(path.read_text(encoding="utf-8")).replace("http://www.w3.org/2000/svg", "")
        years = YEAR.findall(code)
        dates = DATE.findall(code)
        assert not years and not dates, f"{path.relative_to(ROOT)}: литералы года {years[:5]} или даты {dates[:5]}"


def test_labels_come_from_the_release_not_dictionaries():
    """Подписи миров, режимов, сценариев, слоёв и нормативов — из выпуска."""
    code = code_only(APP)
    for literal in ("Мягкая посадка", "Нормализация", "Розничный спад", "Корпоративный спад", "Кризис\"", "По графику", "Жёсткий", "Средняя группа",
                    "Высокие ставки", "Рыночный как есть", "свой макро-взгляд\"", "банковской группы", "Н20.0 группы", "Н20.1 группы",
                    "после фазы роста", "сквозь цикл", "Яндекс", "Операционные результаты за"):
        assert literal not in code, literal
    for fn in ("worldName", "regimeName", "scenarioName", "capTitle", "layerTitle"):
        assert f"function {fn}(" in APP, fn


def test_ratio_labels_come_from_capital_titles():
    """Подписи нормативов — только `capital.titles` (в том числе Н1.0 и Н1.2 банка), в коде их нет (C7)."""
    code = code_only(APP)
    hit = re.search(r"Н\d+\.\d", code)
    assert not hit, f"литерал норматива в app.js: «{code[max(0, hit.start() - 30):hit.end() + 30]}»"
    for key in ("n20", "n11", "n11_observed", "n1_0", "n1_2"):
        assert f'capTitle(d, "{key}")' in code, key
    assert "function metricTitle(" in code, "метрика условия дивиденда (`n20_0`) — подписью из выпуска"


def _function(name: str) -> str:
    code = code_only(APP)
    body = code[code.index(f"function {name}("):]
    return body[:body.index("\nfunction ", 1)]


def test_small_band_shares_are_not_ranked():
    """Доли вклада меньше 1 % — «< 1 %» без упорядочивания; ось вне полосы — мерой правила М§10:
    сдвиг заголовка от её фиксации и порог гейта (`judgements.off_band_shift`), а не «вклад < 1 %» (№ 1)."""
    code = code_only(APP)
    assert "const SHARE_FLOOR = 0.01;" in code and "function shareText(" in code
    for fn in ("bandDrivers", "judgementsCard"):
        assert "shareText(" in _function(fn) and "offBandNote(d)" in _function(fn), fn
    assert "in_band === false" in code and "off_band_shift" in _function("offBandNote")
    assert "2${THIN}%" not in code and "вклад <" not in code.lower().replace("вклад ${share_small}", ""), "порог «< 2 %» и подпись «вклад < 1 %» у осей вне полосы сняты"


# ── печать по контракту (AUDIT-1) ──

def _ru_decimal(text: str) -> str:
    """Правило десятичной запятой `ruText` на регулярном выражении самой витрины (оно совместимо с Python)."""
    source = re.search(r"const RU_DECIMAL = /(.+)/g;", APP).group(1)
    assert "(a === undefined ? m : `${a},${b}`)" in APP, "дробь — последняя альтернатива RU_DECIMAL, прочие — «как есть»"
    return re.sub(source, lambda m: m.group(0) if m.group(1) is None else f"{m.group(1)},{m.group(2)}", text)


@pytest.mark.parametrize("text, want", [
    ("рост 1.5 %", "рост 1,5 %"), ("эмпирика 0.056–0.085", "эмпирика 0,056–0,085"), ("CoR 1.42 % против 1.4 %", "CoR 1,42 % против 1,4 %"),
    ("книга 1.1", "книга 1.1"), ("в книге 1.2 оси", "в книге 1.2 оси"), ("книга 1.1 → 1.2; факты те же", "книга 1.1 → 1.2; факты те же"),
    ("версия 1.2.3", "версия 1.2.3"), ("book-1.6", "book-1.6"), ("уравнение ni-1.0", "уравнение ni-1.0"),
    ("М§4.11 и DESIGN §3.3", "М§4.11 и DESIGN §3.3"), ("(М§14.4)", "(М§14.4)"), ("п. 6.4: срок 3 года", "п. 6.4: срок 3 года"),
    ("Н20.0 не ниже 13.3 %", "Н20.0 не ниже 13,3 %"), ("Н1.1 банка 11.96 %", "Н1.1 банка 11,96 %"), ("28.10.2026", "28.10.2026"),
])
def test_free_text_gets_the_decimal_comma_but_versions_and_references_stay(text, want):
    """№ 61: «book-1,6», «книга 1,1», «М§4,11» на экране не бывает; «рост 1.5 %» по-прежнему → «1,5 %»."""
    assert _ru_decimal(text) == want


def test_the_neutral_sentence_prints_the_profit_level_next_to_the_expectation():
    """№ 16: `ni_equivalent` — ЧП квартала ПРИ нейтральном значении (уровень), а не «на 0,1 п.п.»; рядом — ожидание.
    № 22: наклон — местный (`at_cor`/`at_nim`), рядом — размах реакции."""
    body = _function("neutralSentence")
    assert "ожидание модели" in body and "nr.expectation).ni" in body and "при ней прибыль квартала" in body
    assert "прибыли квартала на 0,1" not in APP and "Math.abs(n.ni_equivalent" not in APP
    assert "at_${kind}" in body and "d_median_min" in body and "d_median_max" in body and "каждые 0,1" not in APP


def test_one_probability_is_printed_by_one_function():
    """№ 63: P(ниже рынка) у героя, второй категории, подписи метра и таблицы — одной функцией."""
    hero = _function("hero")
    assert hero.count("pBelowText(") >= 4 and "fmt.pct(pBelow" not in hero and "p_below_by_ticker)[t], 1)" not in hero
    assert "p > 0 && p < 0.01 ? 2 : 0" in _function("pBelowText")
    assert "in_band === true" in hero, "число осей полосы — строки суждений `in_band`, а не длина `contributions`"


def test_codes_are_printed_in_words():
    """№ 62: базисы П§0.2 и коды политики дивидендов (М§5.1) — словами; «догоняющий — true» и ключи на экран не идут."""
    code = code_only(APP)
    basis = re.search(r"const BASIS = \{(.*?)\};", code).group(1)
    assert set(re.findall(r"(\w+): \"", basis)) >= {"ifrs", "ras", "mgmt", "engine", "regulatory", "sector"}
    words = re.search(r"const CODE_WORDS = \{(.*?)\};", code, re.S).group(1)
    assert set(re.findall(r"(\w+): \"", words)) >= {"ifrs_ni_shareholders", "ifrs_ni_adjusted", "issued", "residual_above_requirement", "ceil_kopeck", "half_up_kopeck", "none",
                                                     "quarterly", "annual", "dividend_first", "growth_first"}
    assert "обеих категорий" not in words, "слова о двух категориях — по числу тикеров, не в словаре кодов"
    policy = _function("dividendsCard")
    for field in ("pol.base", "pol.divisor", "pol.shortfall_rule", "pol.crisis.catch_up", ".rounding"):
        assert f"codeText({field}" in policy or f"codeText(obj(check[0]){field}" in policy, field
    assert "!pol.valid_until ? ruText(pol.valid_until_note" in policy and "`действует по ${fmt.date(pol.valid_until)}`" in policy, "срок политики: дата или причина, не «действует по —»"
    assert 'flag(d, "policy_expired")' in policy and "Срок: " not in policy, "истёкший срок — словами флага (В17); заметка срока — без приставки «Срок:» (№ 97)"
    assert "wordsText(d, f.detail)" in _function("banners"), "метка клетки и код периода в тексте флага — словами выпуска"
    assert "book.sections" not in code and ".sections" not in code, "строк книги по разделам в выпуске нет (П§6)"


def test_the_requirement_is_named_for_what_it_is():
    """№ 66: «запас до требования» — до порога дивидендной политики (когда он задан и связывает) или до минимума с
    надбавками и запасом; пол года — отдельным числом. Порог 0 — порога в политике нет, слово о нём не печатается."""
    body = _function("reqWords")
    assert "C.policy_threshold > 0" in body and "дивидендной политики" in body and "(минимум с надбавками + запас)" in body and "floor20" in body
    assert "C.policy_threshold > 0" in _function("capitalScenariosCard") and "const policy = C.policy_threshold > 0" in _function("ratioPathCard")
    assert "(${periodShort(anchor.req20_glide_period)})` : req.to}" in _function("passportRow") and "до ${req.to}" in _function("capitalKpis")
    # находка A13: правило роста сравнивает норматив с требованием с глиссадой — запас якоря печатается и до него, с кварталом
    assert "n20_headroom_glide" in body and "req20_glide_period" in body and "до ${req.glide}" in _function("capitalKpis")
    assert "fmt.pp(req.glide ? anchor.n20_headroom_glide : anchor.n20_headroom, 1)" in _function("passportRow") \
        and "до требования года — ${fmt.pp(anchor.n20_headroom, 1)}" in _function("passportRow"), "оба запаса — числами выпуска"
    assert "до требования`" not in APP and '"запас до требования"' not in APP


# ── печать по второму аудиту (AUDIT-2) ──

def test_a_dictionary_axis_prints_its_ends_by_key():
    """№ 101: у оси-словаря (вероятности режимов, веса миров) диапазон — пары концов по ключам, а не название типа;
    §4.3: у строки обратного расчёта без оси (концы равны) диапазон не печатается."""
    body = _function("rangeText")
    assert '"словарь долей"' not in APP and "isDict(j)" in body and "keyName(d, k)" in body and " → " in body and '"—"' in body
    assert "a !== b" in _function("reverseRange") and "reverseRange(r)" in _function("reverseDcfCard")
    assert "`${reverseValue(r, r.range[0], true)} … ${reverseValue(r, r.range[1], true)}`" not in APP


def test_lines_break_on_undisclosed_values_and_zero_bars_are_labelled():
    """№ 84: линия идёт по непрерывным участкам — `null` рвёт её, одиночная точка рисуется точкой;
    № 105: ноль на столбцах — подпись и цель подсказки (ноль — не пропуск), значение меньше единицы — с двумя знаками."""
    lines = _function("linesChart")
    assert "[...s.points, null]" in lines and "run.length > 1" in lines and "run.length && !s.dots" in lines
    assert 'pts.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" L")' not in lines, "линия через отфильтрованные точки соединяла соседей через провал"
    columns = _function("columnsChart")
    assert "it.value === 0 ? sv(\"rect\", { class: \"hit\"" in columns and "if (isNum(it.value)) {" in columns
    assert "Math.abs(v) < 1 ? 2 : 0" in _function("dividendHistoryCard")
    assert "basisName(g.basis)" in _function("historyCard"), "провалы раскрытия — по базисам (П§2 history.gaps[].basis)"


def test_legends_name_only_what_is_drawn():
    """№ 103: запись легенды появляется вместе с элементом графика; пунктирная линия — пунктирным ключом; плитка без числа не рисуется."""
    impact = _function("impactCard")
    for cond in ("M.neutral !== null &&", "M.iv &&", "M.forecast !== null &&", "M.other &&", "M.guide &&"):
        assert cond in impact, cond
    assert "impactMarks(d, kind, compact)" in _function("impactChart") and "forecast !== null) svg.append" in _function("impactChart"), "точка прогноза — и без интервала"
    assert "shown.length &&" in _function("nowcastCard") and "obj(nc.journal).entries" in _function("nowcastCard"), "эталоны полосы — из журнала, в пределах оси"
    path = _function("ratioPathCard")
    assert "key-neg2" in path and "key-neg3" in path and "keysOf(drawn)" in path and "keysOf(glide)" in path and '"регуляторный пол"' not in path
    assert "splits.length &&" in _function("priceCard") and "model.length &&" in _function("quarterlyDpsCard")
    assert ".key-third2" in CSS
    assert "key-line key-model2" in _function("priceCard") and "exd.length &&" in _function("priceCard")
    for key in (".key-neg3", ".key-model2"):
        assert key in CSS, key
    trans = _function("transmissionCard")
    assert "isNum(dis.nii_per_100bp) ? kpi(" in trans and "dis.src" in trans, "плитка без числа не рисуется — причина строкой"


def test_bank_language_prints_whole_rubles_and_empty_intervals_in_words():
    """№ 81: чувствительности языка банка — с точностью шага печати выпуска (оценщик срединных прогонов точнее не
    даёт): целые рубли при шаге 1 ₽ и крупнее, десятые — при шаге 0,1 ₽ (у цены около 10 ₽ целый рубль — 10 %);
    № 82: `dps_interval` и `ni_year_se` могут быть `null` — печатается «интервал не оценён», а не «—–— ₽»."""
    tiles = _function("heroTiles")
    assert "priceNum(d, row.rub_per_1pp_roe)," in tiles and "fmt.signedRub(row.rub_per_01pp_cor)}" in tiles and "fmt.signedRub(row.rub_per_01pp_nim)}" in tiles
    assert "RUB_DIGITS = pd(DATA)" in _function("render") and "rub(x, digits = RUB_DIGITS)" in APP
    assert "exactDigits(s, 3)" in _function("pd")
    assert "интервал не оценён" in _function("dpsInterval") and "isNum(lo) && isNum(hi)" in _function("dpsInterval")
    assert "dpsInterval(year, 1)" in _function("reportTeaser") and "dpsInterval(y, 2)" in _function("yearDpsCard")
    assert "list(y.dps_interval)[0]" not in APP and "list(year.dps_interval)[0]" not in APP
    assert "isNum(y.ni_year_se) ?" in _function("yearDpsCard") and "на прибыли смеси заголовка" in _function("yearDpsCard")


def test_gate_messages_and_typography_follow_the_text_rules():
    """№ 97: сообщение гейта — предложением с заглавной; текст ступени политики — через `ruText`; после многоточия точки нет;
    № 73: «Уравнение словами» без номера версии; запись миров — версией записи семейства, без имени её репозитория."""
    assert "sentence(upperFirst(wordsText(d, g.message)))" in _function("gatesCard")
    assert "ruText(r.title)" in _function("dividendsCard")
    meta = _function("bookMetaCard")
    assert '…${m.fast ? "; быстрая сборка." : ""} `' in meta and "…. " not in APP
    assert 'detailsBlock("Уравнение словами"' in _function("nowcastCard") and "b.version" not in _function("nowcastCard")
    assert "worldsRecord(d)" in meta and "worldsRecord(d)" in _function("worldsCard") and "src.origin" not in meta
    assert "запись семейства 850" in _function("worldsRecord") and "ruText(obj(obj(d.worlds).source).origin" not in APP


def test_w3_fields_of_the_contract_are_printed():
    """П§2 после W3: строка FVC и разовые статьи, φ по сторонам баланса и кредитная маржа, пол вероятности режима,
    окно даты формы ЦБ, флаги срока — плашками (В17), единицы плиток — коды П§0.2."""
    annual = _function("annualCard")
    assert "r.fvc" in annual and "r.one_off" in annual
    trans = _function("transmissionCard")
    for field in ("t.phi_assets", "t.phi_liab", "t.phi_split", "t.loan_margin"):
        assert field in trans, field
    assert "floor_share" in _function("regimesCard") and "form102_latest_est" in _function("earlierReport")
    banners = _function("banners")
    assert 'say("explanation_expiring", "banner-info")' in banners and 'say("policy_expired", "banner-info")' in banners
    chip = _function("releaseChip")
    assert "explanation_expiring" not in chip and "policy_expired" not in chip, "флаги срока — плашки, ярлык выпуска не желтеет (не тревога)"
    # закрытый первый период книги до отчёта за него — справка: ярлык желтит только отставание больше чем на период
    assert "book_first_period_closed" not in chip and "m.periods_closed > 1" in chip
    assert "m.periods_closed > 1" in banners and '"banner-info"' in banners.split("m.book_first_period_closed", 1)[1].split("last_buy_date", 1)[0]
    # плашки сворачиваются нажатием и помнятся браузером; «выпуск устарел» — нет; хранилище — только под try
    fold, memory = _function("plain"), _function("folded")
    assert 'if (kind === "banner-stale") return node;' in fold and '"is-folded"' in fold and '"aria-expanded"' in fold
    assert "try { window.localStorage.setItem(FOLD" in fold and "try { FOLDED = new Set(list(JSON.parse(window.localStorage.getItem(FOLD))))" in memory
    assert APP.count("localStorage") == 2, "хранилище браузера витрина трогает только ради свёрнутых плашек"
    assert ".banner.is-folded" in CSS and "flex-wrap: wrap" in CSS.split(".belt {", 1)[1].split("}", 1)[0]
    units = _function("indicatorValue")
    for code in ('"share"', '"pct"', '"bn"', '"price"', '"rub"', '"level"', '"count"'):
        assert f"case {code}" in units, code


def test_phone_card_heads_with_a_switch_wrap_and_the_passport_is_padded():
    """№ 104: на телефоне шапка карточки с переключателем или ссылкой переносится — заголовок занимает всю ширину;
    № 106: паспорт на «Оценке» — с тем же отступом от края, что остальные карточки."""
    code = code_only(CSS)
    phone = code[code.index("@media (max-width: 480px)"):]
    assert ".card-head:has(> .card-link, > .chooser, > .pick-row) { flex-wrap: wrap;" in phone
    assert ".card-head:has(> .card-link, > .chooser, > .pick-row) > div:first-child { flex-basis: 100%; }" in phone
    assert re.search(r"\.passport \{[^}]*padding: 4px 8px;", code) and "padding-left: 4px" not in re.search(r"\.passport \.pp:first-child \{([^}]*)\}", code).group(1)
    regimes, impact = _function("regimesCard"), _function("impactCard")
    assert "tools: chooser(" in regimes and 'tools: el("div", { class: "pick-row"' in impact, "две шапки с переключателем: «Режимы» и «Что даст отчёт»"


# ── печать по проверке W3 (решение P7) ──

def test_the_word_after_a_number_follows_the_printed_number():
    """verify-deploy № 4: дробное число лет — «1,6 года» (родительный единственного), а не форма по целой части;
    слово выбирается по числу, как оно напечатано: с дробной частью — всегда «года», целое — по правилу 1 / 2–4 / 5+."""
    body = _function("plural")
    assert "if (digits > 0) return few;" in body and "Math.round(n)" in body and "Math.trunc" not in APP
    years = _function("yearsText")
    assert "exactDigits(v, 1)" in years and "plural(v, YEAR_WORDS, k)" in years
    assert 'if (u === "years") return yearsText(value);' in _function("formatByUnit")
    assert "yearsText(pol.excess.ramp_years)" in _function("dividendsCard") and "yearsText(+t)" in _function("curveCard")
    assert APP.count('["год", "года", "лет"]') == 1 and "} лет" not in APP and "} года" not in APP, "срок в годах печатает одна функция"


def test_quiet_gates_print_their_messages_next_to_the_corridor():
    """Аудит 02.10.2026, № 7: сообщение несработавшего гейта печатается рядом с его коридором — у гейтов капитала в
    нём хвост прогонов полосы, которого в печатаемой сетке нет (М§10); те же правила текста, что у сработавших."""
    quiet = _function("gatesCard").split("Коридоры несработавших гейтов", 1)[1].split("Инварианты ·", 1)[0]
    assert "corridor(g)" in quiet and "g.message ?" in quiet
    assert "sentence(upperFirst(wordsText(d, g.message)))" in quiet


def test_check_counters_agree_with_their_numbers():
    """verify-deploy № 5: «1 поднятый флаг», «4 сработавших гейта из 19»; число клеток гейта — словом в падеже числа;
    у гейта, сравнивающего миры целиком (клеток в нём нет), счёт клеток не печатается."""
    gates = _function("gatesCard")
    assert "`${plural(n, adj)} ${plural(n, noun)}${tail}`" in gates
    for forms in ('["нарушенный", "нарушенных", "нарушенных"], ["инвариант", "инварианта", "инвариантов"]',
                  '["сработавший", "сработавших", "сработавших"], ["гейт", "гейта", "гейтов"]',
                  '["поднятый", "поднятых", "поднятых"], ["флаг", "флага", "флагов"]'):
        assert forms in gates, forms
    assert "g.cells > 0 ? `${fmt.num(g.cells)} ${plural(g.cells, CELL_WORDS)} · ` : \"\"" in gates
    assert " кл." not in APP and '"поднятых флагов"' not in APP and "`сработавших гейтов из" not in APP
    assert APP.count('["клетка", "клетки", "клеток"]') == 1, "слова клеток — одной константой"


def test_the_control_table_prints_in_the_unit_of_the_tolerance():
    """verify-deploy № 6: сдвиг доли (`pp`) — в п.п. и в столбцах уровня (как на «Расчёте»), уровень доли — в %;
    абсолютные разность и допуск — в единице строки со знаками допуска; разность мельче этих знаков — ноль,
    пока строка в допуске (шум счёта 6·10⁻¹⁷ рядом с «0 п.п.» не печатается); относительные — в процентах."""
    body = _function("controlCard")
    assert 'r.unit === "pp" ? fmt.num(v * 100, 2) + tail(r) : share(r) ? fmt.pct(v, 2)' in body
    assert "Math.ceil(-Math.log10(inUnit(r, t)) - 1e-9)" in body and "digits(r, t) > 4 ? sci(inUnit(r, t))" in body
    assert 'fmt.num(v, k) !== fmt.num(0, k) ? fmt.signed(v, k) : v === 0 || r.ok ? "0" : sci(v)' in body
    assert "rel(r) ? fmt.signedPct(r.diff_rel, 2) : diffAbs(r)" in body and "` или ${tolAbs(r, r.tol_abs)}`" in body
    assert "по виду допуска" in body and "String(cm.commit || \"—\").slice(0, 7)" in body
    rows = json.loads((ROOT / "tests" / "fixtures" / "payload-sample.json").read_text(encoding="utf-8"))["checks"]["control_model"]["rows"]
    assert {r["unit"] for r in rows} <= {"pp", "pct", "share", "bn", "rub", "price", "number"}, "единицы строк сверки, которые печатает карточка"


def test_the_dividend_history_names_its_source_in_the_words_of_the_release():
    """Решения P1, P7: источник истории дивидендов печатается как пришёл из выпуска (`dividends.history[].src`),
    годы с одним источником — одной записью; слов о методах API и токене в витрине нет."""
    card = _function("dividendHistoryCard")
    assert "sourcesByYear(list(dv.history)" in card and "Источник факта: " in card and "Источники факта по годам" in card
    by_year = _function("sourcesByYear")
    assert "srcText(src)" in by_year and "r.src" in by_year and ".reduce(" not in by_year and "new Set(" in by_year, "год с несколькими решениями — один раз"
    assert not re.search(r"[А-Яа-яЁё«»][^\n]*\bAPI\b|\bAPI\b[^\n]*[А-Яа-яЁё«»]|токен", APP), \
        "витрина не называет ни API, ни токен (имя константы адреса `API` — не текст экрана)"
    assert "расчёт модели на смеси заголовка, включая уровень на дату якоря" in _function("ratioBridgeCard")


def test_there_are_no_disclaimers_on_the_screen():
    """Правило владельца: ни «не рекомендация», ни «не вердикт», ни оговорок."""
    for name, text in (("index.html", HTML), ("404.html", PAGE_404), ("app.js", APP)):
        low = text.lower()
        for phrase in ("инвестиционн", "не является", "не рекомендац", "дисклеймер", "disclaimer", "не вердикт", "не оферт", "на свой риск"):
            assert phrase not in low, f"{name}: «{phrase}»"


def test_nothing_is_loaded_from_third_party_addresses():
    allowed = {"http://www.w3.org/2000/svg"}
    for name in ("index.html", "404.html", "app.js", "styles.css", "favicon.svg"):
        text = (WEB / name).read_text(encoding="utf-8")
        found = set(re.findall(r"https?://[^\s\"'`)<>]+", text)) - allowed
        assert not found, f"{name}: сторонние адреса {sorted(found)}"
        assert "@import" not in text and "fonts.googleapis" not in text
    assert 'const API = "/api/model"' in APP and "fetch(API" in APP


def test_public_hygiene_of_the_front():
    """Публичный репозиторий: ни IP, ни почт, ни путей пользователя, ни токенов в витрине, функциях и их тестах."""
    paths = [*WEB.iterdir(), *FUNCTIONS.rglob("*.js"), ROOT / "wrangler.toml", ROOT / "ops" / "tools" / "devserver.py",
             *(ROOT / "tests" / "web").glob("*"), *(ROOT / "tests").glob("test_web_*.py"), ROOT / "tests" / "fixtures" / "payload-sample.json"]
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"[\w.+-]+@[A-Za-z][\w-]*\.[A-Za-z]{2,}\b", text), f"{path.name}: почта"
        ips = [ip for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) if not ip.startswith(("127.", "192.0.2.", "198.51.100.", "203.0.113."))]
        assert not ips, f"{path.name}: IP {ips}"
        assert not re.search(r"[A-Za-z]:[\\/]+Users|/home/\w+|/Users/\w+", text), f"{path.name}: путь пользователя"
        assert not re.search(r"t\.[A-Za-z0-9_-]{40,}|ghp_[A-Za-z0-9]{20,}", text), f"{path.name}: похоже на токен"


def test_front_sources_carry_no_control_characters_or_crlf():
    for path in [*WEB.iterdir(), *FUNCTIONS.rglob("*.js")]:
        data = path.read_bytes()
        bad = sorted({b for b in data if b < 0x20 and b not in (0x0A, 0x09)})
        assert not bad, f"{path.name}: управляющие байты {bad} (CRLF — хэш темы считается по LF)"


# ── панель: карточки по узлам, слова общей формы — по данным ──

PANEL_CARDS = {"limitsCard": "bank_rows", "fadeCard": ").fade", "growthCard": ").growth",
               "rulePriceCard": ").rule_price", "quarterlyDpsCard": ".model_quarters", "sharesCard": ".corporate_actions"}
# Карточки формы Т, мёртвые для формы Совкомбанка (мост трёх прибылей `history.three_profits`, месячная таблица релиза
# `nowcast.ops`), сняты с витрины: функций нет, узлы выпуска ими не печатаются (DASHBOARD §1, §3).
T_ONLY_CARDS = ("threeProfitsCard", "opsMonthsCard", "Три прибыли: мост", "Операционные результаты и формы ЦБ по месяцам")


def test_a_panel_card_is_drawn_only_with_its_node():
    """Карточка панели читает свой необязательный узел и без него возвращает `null`: ни заглушки, ни «нет данных»."""
    for name, node in PANEL_CARDS.items():
        body = _function(name)
        assert node in body and re.search(r"if \([^\n]*\) return null;", body), name
        assert "missing(" not in body and "empty(" not in body, f"{name}: заглушки у карточки панели нет"
    assert "if (!rows.length) return null;" in _function("rasMonthsCard"), "месяцы РСБУ общей формы — только когда они есть"
    retro = _function("retroBenchmarksCard")
    assert "!horizons.length) return null;" in retro and "none(" not in retro, "блока ретро-проверки нет — карточки нет, без заглушки"
    assert not any(t in APP for t in T_ONLY_CARDS) and "three_profits" not in APP and "obj(obj(d.nowcast).ops)" not in APP, "карточки формы Т сняты"
    section = _function("section")
    assert "cards.flat().filter(Boolean)" in section and ": null" in section, "раздел без карточек не рисуется"
    for screen in ("screenMarket", "screenModel", "screenReport", "screenCapital"):
        assert "root.append(" not in _function(screen), f"{screen}: экран собирается одним узлом — пустая карточка не превращается в текст"
    assert "нет данных" not in APP


def test_words_of_the_general_form_are_chosen_by_the_data():
    """«Обеих категорий», вторая линия рынка, «РСБУ банка», купон и порог политики печатаются только там, где данные их оправдывают."""
    code = code_only(APP)
    assert code.count("обеих категорий") == 1 and 'return solo(d) ? "" : " обеих категорий";' in _function("both")
    assert "tickers(d).length < 2" in _function("solo") and 'solo(d) ? null : pa(' in _function("methodNote")
    assert "if (y.at1_coupon_after_tax) steps.push" in _function("yearDpsCard")
    kpis = _function("capitalKpis")
    assert "a.at1 ? kpi(" in kpis and "isNum(o.n1_0) ?" in kpis and 'a.estimated ? " — оценка до выхода формы" : ""' in kpis
    assert 'e.kind === "ras"' in _function("rasForm") and "rasForm(d)" in _function("earlierReport") and "rasForm(d)" in _function("screenReport")
    now = _function("nowcastCard")
    assert "months.length ? [" in now and "isNum(b.ras_estimate) ? kpi(" in now and "isNum(b.bridge) ? kpi(" in now and "b.w > 0 ? kpi(" in now
    policy = _function("dividendsCard")
    assert "check.length ?" in policy and "cap.length ?" in policy and "cond.threshold > 0 ?" in _function("dividendCard")
    assert "сквозь цикл" not in APP and "Банки-аналоги" not in APP and "Капитал банка оценивается" not in APP and "T-Invest" not in APP
    assert "A.some((r) => r.fvc)" in _function("annualCard"), "пустой столбец не рисуется"


def test_every_roe_and_pe_carries_its_basis_label():
    """Подпись базиса прибыли и ROE — из выпуска (`meta.basis_labels`), подвалом карточки или подписью плитки, не подсказкой."""
    assert "basis_labels" in _function("basisLabel") and "foot(" in _function("basisFoot")
    for name, keys in (("priceCard", '"profit"'), ("bankLineCard", '"roe"'), ("roeTreeCard", '"roe"'), ("fadeCard", '"roe"'),
                       ("yearDpsCard", '"profit"'), ("annualCard", '"profit", "roe"'), ("historyCard", '"profit", "roe"'), ("bookMetaCard", '"profit", "roe", "divisor"')):
        assert f"basisFoot(d, {keys})" in _function(name), name
    passport = _function("passportRow")
    assert 'basisLabel(d, "profit")' in passport and 'basisLabel(d, "roe")' in passport and "iss.label" in passport and "pp-foot" in passport
    assert ".passport .pp-foot" in CSS       # мост трёх прибылей формы Т (ROE эмитента с подписью базиса) снят с витрины


def test_estimated_dates_per_share_and_quarterly_yield_are_named():
    """Оценочная дата печатается «≈» и окном; «на акцию» подписано делителем выпуска; квартальная доходность не названа годовой;
    запись дивиденда — словами решения из выпуска, а без них — периодом."""
    assert "e.estimated" in _function("est") and 'e.precision !== "day"' in _function("est")
    events = _function("eventsCard")
    assert "est(e)" in events and "e.estimated ?" in events and "e.in_book === false" in events
    assert "est(e)" in _function("nextRasLine") and "est(nf)" in _function("nextFactLine") and "approx ?" in _function("countdown")
    assert "divisor_mln" in _function("divisor") and "divisor_label" in _function("divisor") and "outstanding_mln" in _function("divisor")
    for name in ("methodNote", "flowCard", "capitalKpis"):
        assert "divisor(d)" in _function(name), name
    assert "outstanding_mln, 1)} млн акций в обращении" not in _function("methodNote") + _function("flowCard")
    assert 'next.yield_period ? "квартальной выплаты " : ""' in _function("yieldWords")
    assert "yieldWords(d, next, t)" in _function("dividendsTeaser") and "yieldWords(d, next, t)" in _function("dividendCard") and "next.yield_period ?" in _function("passportRow")
    label = _function("divLabel")
    assert "r.label ? ruText(r.label)" in label and "periodLabel(r.period)" in label and "r.year" in label
    for name in ("dividendsTeaser", "dividendCard", "bridgeCard", "passportRow", "banners"):
        assert "divLabel(" in _function(name) or "divCell" in _function(name), name
    assert "за ${rec.year}" not in APP and "за ${r.year}" not in APP and "за ${next.year}" not in APP


# ── экраны и адреса ──

def test_there_are_six_screens_with_direct_links_and_old_addresses():
    assert re.findall(r'data-screen="([a-z]+)"', HTML) == SCREENS
    block = re.search(r"const SCREENS = \{(.*?)\};", APP, re.S).group(1)
    assert re.findall(r"^\s*([a-z]+):", block, re.M) == SCREENS
    old = re.search(r"const OLD_HASHES = \{(.*?)\};", APP).group(1)
    assert dict(re.findall(r'(\w+): "(\w+)"', old)) == {"debt": "capital", "money": "capital", "value": "overview", "priced": "market"}
    assert "function syncHash(" in APP and "history.replaceState(null" in APP


def test_two_503_answers_get_their_own_titles():
    boot = re.search(r"async function boot\(\) \{(.*?)\n\}", APP, re.S).group(1)
    assert '"not published yet"' in boot and "Выпуск ещё не опубликован" in boot and "Источник данных временно недоступен" in boot
    assert "API_TIMEOUT_MS" in boot


def test_time_is_printed_in_moscow_time():
    assert 'const MSK = "Europe/Moscow";' in APP and "timeZone: MSK" in APP and "МСК" in APP


# ── палитра и кегль ──

def _tokens(selector: str) -> dict:
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", CSS, re.S).group(1)
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block))


def _contrast(a: str, b: str) -> float:
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_series_colours_hold_3_to_1_on_cards_in_both_themes():
    light = _tokens(":root")
    dark = {**light, **_tokens(':root[data-theme="dark"]')}
    for name, theme in (("светлая", light), ("тёмная", dark)):
        for token in ("--model", "--market", "--third", "--neg", "--series-neutral"):
            ratio = _contrast(theme[token], theme["--surface"])
            assert ratio >= 3.0, f"{name} тема: {token} {theme[token]} к карточке {ratio:.2f} : 1"


def test_no_text_smaller_than_12_5_px():
    sizes = [float(x) for x in re.findall(r"font(?:-size)?:[^;{}]*?(\d+(?:\.\d+)?)px", code_only(CSS))]
    assert sizes and min(sizes) >= 12.5, f"мелкий кегль: {sorted(set(s for s in sizes if s < 12.5))}"
    for size in re.findall(r"textWidth\([^)]*?,\s*(\d+(?:\.\d+)?)", APP):
        assert float(size) >= 12.5, f"подпись графика меряется кеглем {size}"


def test_the_brand_is_the_neutral_family_glyph():
    """Без фирменного стиля эмитента: знак шапки и favicon — один нейтральный рисунок семейства."""
    fav = (WEB / "favicon.svg").read_text(encoding="utf-8")
    for d in re.findall(r'<path d="([^"]+)"', fav):
        assert d in HTML, "знак шапки и favicon — один рисунок"
    assert set(re.findall(r"#[0-9a-fA-F]{6}", fav)) == {"#121211", "#fcfcfb", "#eb6834"}, "знак — чернила, бумага и точка рынка"
    brand = re.findall(r"\.brand-(?:bg|curve|mid|dot)\s*\{([^}]*)\}", CSS)
    assert brand and all(re.search(r"var\(--(?:ink|surface|market)\)", b) for b in brand), brand


def test_phone_tables_keep_the_numbers_on_screen():
    code = code_only(CSS)
    assert "overflow-wrap: anywhere" not in code and "word-break: break-all" not in code
    assert re.search(r"td\.num\s*\{[^}]*white-space:\s*nowrap", code)
    assert re.search(r"\.scroll\s*\{[^}]*overflow-x:\s*auto", code)
    phone = code[code.index("@media (max-width: 480px)"):]
    assert "position: sticky" in phone and "max-width: 42vw" in phone
    assert ".more:not(.is-open) > .more-body { display: none; }" in code, "второстепенные карточки на телефоне сворачиваются"
