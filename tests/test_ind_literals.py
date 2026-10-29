"""В коде индикаторов нет литералов эмитента, годов и чисел книги и фактов (INTERFACES §0 п. 4, М§0.6).

Имя, тикеры и регномер — из `meta.company` книги; строки поиска, хосты и шаблоны документов эмитента,
заголовок запросов — из `data/indicators/sources.yaml`; подписи — из `meta.labels` книги; числа — из
книги, фактов и истории `data/indicators/seed/`. Технические константы (допуски, окна дней, коридоры
правдоподобия) совпасть с числом книги могут — тогда они названы здесь с причиной, по файлу: список
виден в диффе, и добавить в него число молча нельзя.

Эмитент проверяется дважды: по книге репозитория и по заглушке книги тестов (в ней тот же эмитент).
Заглушка держит проверку и на дереве с книгой другой копии: слой общий, и его литералы от книги в
`data/` не зависят. Голый тикер короче трёх знаков границей слова не проверяется (буква совпадает с
частью чужих имён: «T-Invest», `T1`). Регномер, похожий на обычное число кода (короче четырёх знаков, как
963 этой копии, или круглый: 1000), границей слова тоже не проверяется — только строковым литералом и числом рядом со словом
о регномере — в той же или соседней строке, в теге запроса службы форм, в параметре адреса — и константой
на месте параметра-регномера в вызове (`tests/support_literals.py`). Имена образцов семейства и слова эмитента этой копии ищутся
своими шаблонами. Префикс окружения проверяется по именам переменных, не подстрокой.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

from tests.support_literals import plain_regnum, regnum_call_hits, regnum_parameters, regnum_patterns

ROOT = Path(__file__).resolve().parents[1]
CODE = sorted((ROOT / "indicators").glob("*.py"))
FIXTURE_BOOK = ROOT / "tests/fixtures/ind/book_meta.yaml"
YEARS = range(2000, 2101)
MIN_BARE_TICKER = 3                 # тикер короче — границей слова не проверяется
# Панели-образцы семейства: Сбер (первая панель банков), Т (образец кода копии), ВТБ (источник инструментов
# быстрого круга; его регномер 1000 — «обычное число» и шаблоном не ищется): их имена, тикеры и регномеры в
# общем слое остаться не должны. Адрес API брокера совпадает со словами Т — он вырезается до поиска (`BROKER_API`).
PREVIOUS_COPY = re.compile(r"сбер|sber|\b1481\b|tbank|тбанк|т-банк|т‑банк|tinkoff|тинькофф|t-technologies|т-технолог"
                           r"|росбанк|\b2673\b|втб|vtb|внешторгбанк|vneshtorgbank", re.I)
# В коде остаётся только адрес API брокера.
BROKER_API = re.compile(r"invest-public-api\.(?:tinkoff|tbank)\.ru(?:/rest/tinkoff\.public\.invest\.api[\w.]*)?")
# Имена эмитента этой копии — кириллицей, латиницей (имя и хосты), тикер и прежнее имя — живут в книге и в
# sources.yaml; в коде их нет при любой книге (и пока в копии книга образца).
ISSUER_WORDS = re.compile(r"совком|sovcom|svcb|буйкомбанк", re.I)

# (файл, значение) → почему это не второй экземпляр числа книги или фактов.
NAMED_LITERALS: dict[tuple[str, float], str] = {
    ("cbr.py", 0.03): "нижняя граница коридора правдоподобия ставки (3 % годовых), как у прочих панелей семейства",
    ("iss.py", 0.03): "нижняя граница коридора правдоподобия узла кривой",
    ("cbr.py", 0.4): "верхняя граница коридора правдоподобия ставки (40 % годовых)",
    ("iss.py", 0.4): "верхняя граница коридора правдоподобия узла кривой",
    ("journal.py", 0.8): "порог правила допуска (MSE ≤ 0,8 лучшего эталона) — решение владельца",
    ("journal.py", 1.0): "порог понижения правила допуска",
    ("record.py", 0.5): "доля больше 0,5 без «%» — почти наверняка проценты (проверка ввода)",
    ("release_watch.py", 0.15): "допуск совпадения двух источников по умолчанию, млрд ₽ (sources.yaml)",
    ("release_watch.py", 0.35): "допуск тождества НМ по умолчанию, млрд ₽ (sources.yaml)",
    ("outputs.py", 0.15): "допуск сверки с формой 0409102 по умолчанию, млрд ₽ (sources.yaml)",
    ("http.py", 45.0): "тайм-аут запроса, с",
    ("http.py", 3.0): "пауза перед второй попыткой, с",
    ("http.py", 10.0): "пауза перед третьей попыткой, с",
    ("http.py", 0.35): "пауза между запросами к хосту T-Invest, с (лимит 200 в минуту)",
    ("nowcast.py", 1.0): "интервал — прогноз ± одна стандартная ошибка; w = 1 без ожидания модели",
    ("register.py", 0.005): "допуск совпадения DPS источников реестра по умолчанию — копейка (sources.yaml)",
    ("release_watch.py", 0.0005): "допуск совпадения долей двух источников по умолчанию — 0,05 п.п. (sources.yaml)",
    ("http.py", 0.5): "пауза между запросами к хосту ISS, с",
    ("http.py", 30.0): "пауза перед четвёртой попыткой, с",
}
# 0,5 здесь нет нарочно: в книге десяток ключей, равных 0,5, — половина разрешается только по файлу.
TRIVIAL = {0.0, 1.0, 2.0, 100.0, 1000.0, 1e-6, 1e-9, 1e-12}

pytestmark = pytest.mark.tact


def _company(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {})["meta"]["company"]


def _issuers() -> list[dict]:
    """Эмитент заглушки книги тестов и эмитент книги репозитория (машинной, без неё — её исходника)."""
    out = [_company(FIXTURE_BOOK)]
    for name in ("assumptions.yaml", "assumptions.draft.yaml"):
        book = ROOT / "data" / "assumptions" / name
        if book.exists():
            out.append(_company(book))
            break
    return out


def _numbers(obj, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)


def _data_numbers() -> set[float]:
    out: set[float] = set()
    for book in (ROOT / "data/assumptions/assumptions.yaml", ROOT / "data/assumptions/assumptions.draft.yaml"):
        if book.exists():
            _numbers(yaml.safe_load(book.read_text(encoding="utf-8")), out)
    for path in sorted((ROOT / "data" / "facts").glob("*.json")) + sorted((ROOT / "data/indicators/seed").glob("*.json")):
        _numbers(json.loads(path.read_text(encoding="utf-8")), out)
    return out


def _constants(source: str) -> list[tuple[int, float]]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            out.append((node.lineno, node.value))
    return out


def issuer_patterns(company: dict) -> list[re.Pattern]:
    """Шаблоны эмитента: тикеры от трёх знаков — целым словом, регномер, начало имени. Регномер, похожий на
    обычное число кода, — строковым литералом и числом рядом со словом о регномере, а не целым словом."""
    patterns = [re.compile(rf"\b{re.escape(str(t))}\b") for t in company["tickers"] if len(str(t)) >= MIN_BARE_TICKER]
    regnum = str(company["cbr_regnum"])
    patterns += regnum_patterns(regnum) if plain_regnum(regnum) else [re.compile(rf"\b{re.escape(regnum)}\b")]
    patterns.append(re.compile(re.escape(str(company["name"])[:4]), re.I))
    return patterns


def test_no_year_literals_in_indicators():
    found = {p.name: [(ln, v) for ln, v in _constants(p.read_text(encoding="utf-8"))
                      if type(v) is int and v in YEARS] for p in CODE}
    found = {k: v for k, v in found.items() if v}
    assert not found, f"литералы года в indicators/: {found}"


def test_no_issuer_literals_in_indicators():
    patterns = [pat for company in _issuers() for pat in issuer_patterns(company)]
    cfg = yaml.safe_load((ROOT / "data/indicators/sources.yaml").read_text(encoding="utf-8"))
    for ch in cfg["news"]["telegram_channels"]:
        patterns.append(re.compile(re.escape(ch["name"] if isinstance(ch, dict) else ch)))
    docs = cfg.get("issuer_docs") or {}
    for host in list(docs.get("hosts") or []) + list(docs.get("fallback_hosts") or []):      # запасных может не быть
        patterns.append(re.compile(re.escape(host), re.I))
    patterns += [PREVIOUS_COPY, ISSUER_WORDS]
    bad = []
    for p in CODE:
        text = BROKER_API.sub("<адрес API брокера>", p.read_text(encoding="utf-8"))
        for pat in patterns:
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{p.name}:{line}: {m.group(0)}")
    # регномер-«обычное число» константой на месте параметра-регномера: слова рядом может не быть
    sources = {p.name: p.read_text(encoding="utf-8") for p in CODE}
    parameters = regnum_parameters(sources.values())
    for regnum in sorted({str(company["cbr_regnum"]) for company in _issuers() if plain_regnum(company["cbr_regnum"])}):
        bad += [f"{name}:{line}: {what}" for name, source in sources.items()
                for line, what in regnum_call_hits(source, regnum, parameters)]
    assert not bad, "литералы эмитента в indicators/ (им место — книга и sources.yaml): " + "; ".join(sorted(set(bad)))


def test_the_issuer_scanner_has_teeth_and_skips_a_bare_short_ticker():
    short = {"name": "Т-Технологии", "tickers": ["T"], "cbr_regnum": 2673}
    hits = lambda text: [m.group(0) for pat in issuer_patterns(short) for m in pat.finditer(text)]  # noqa: E731
    assert hits('SOURCE = "T-Invest"; T1 = 1; TOKEN_ENV = "TINVEST_TOKEN"') == []      # буква тикера — не литерал
    assert hits("regnum = 2673") == ["2673"] and hits("# т-технологии") == ["т-те"]
    long = {"name": "Банк Пример", "tickers": ["PRMR"], "cbr_regnum": 1}
    assert [m.group(0) for pat in issuer_patterns(long) for m in pat.finditer('t = "PRMR"; x = "PRMRP"')] == ["PRMR"]
    assert PREVIOUS_COPY.search("indicators.sber_pdf") and PREVIOUS_COPY.search("регномер 1481")
    assert not PREVIOUS_COPY.search("x = 14810") and PREVIOUS_COPY.search("https://cdn.tbank.ru/a.pdf")
    assert PREVIOUS_COPY.search("# МКПАО «Т-Технологии»") and PREVIOUS_COPY.search("рег. № 2673")
    assert not PREVIOUS_COPY.search("x = 126730") and not PREVIOUS_COPY.search(BROKER_API.sub("<адрес>", (
        'BASE = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1."')))
    for text in ("https://www.vtb.ru/ir/", "# группа ВТБ", "бывший Внешторгбанк"):
        assert PREVIOUS_COPY.search(text), text
    for text in ("https://prod-api.sovcombank.ru/finance-report/", "# группа Совкомбанк", "бывший Буйкомбанк",
                 'ticker = "SVCB"'):
        assert ISSUER_WORDS.search(text), text


def test_the_issuer_scanner_sees_a_plain_regnum_only_as_a_string_or_in_context():
    """Регномер, похожий на обычное число кода (963 — короче четырёх знаков): то же число в арифметике, счётчике и
    подписи — не находка; регномер строковым литералом и число рядом со словом о регномере — находка. Имя и тикер —
    словами."""
    bank = {"name": "Совкомбанк", "tickers": ["SVCB"], "cbr_regnum": 963}
    hits = lambda text: [m.group(0) for pat in issuer_patterns(bank) for m in pat.finditer(text)]  # noqa: E731
    for text in ("x = total * 963 / n", "LIMIT = 963", "pause_ms = 963.0", "# до 963 записей за такт",
                 'note = "первые 963 знака"', "sizes = [96, 963, 9630]", "y = 1963 + x963 + 963_000 + 0.963"):
        assert hits(text) == [], text
    assert hits('REGNUM = "963"') == ['"963"', 'REGNUM = "963']
    assert hits("code = '963'") == ["'963'"]
    assert hits("regnum = 963") == ["regnum = 963"]
    assert hits('inner = dates_request(form, 963)  # регномер') == ["963)  # регномер"]
    assert hits('url = base + "?regn=963"') == ["regn=963"]
    assert hits("# банк, рег. № 963, лицензия") == ["рег. № 963"]
    # регномер в запросе службы форм уходит в теге: тег — слово о регномере (у тега дат — с опечаткой службы)
    assert hits('body = "<CredorgNumber>963</CredorgNumber><dt>x</dt>"') == ["CredorgNumber>963"]
    assert hits('body = "<CredprgNumber>963</CredprgNumber>"') == ["CredprgNumber>963"]
    assert hits('body = "<RegNumber>963</RegNumber>"') == ["RegNumber>963"]
    for text, found in (("reg_no = 963", "reg_no = 963"), ("regno = 963", "regno = 963"),
                        ("registration_number = 963", "registration_number = 963"),
                        ("license = 963", "license = 963"), ("LICENCE = 963", "LICENCE = 963"),
                        ("bank_id = 963", "bank_id = 963"), ("CBR_BANK = 963", "CBR_BANK = 963"),
                        ("regnum = 96_3", "regnum = 96_3"), ('url = base + "?id=963"', "?id=963"),
                        ('url = base + "&bank_id=963&x=1"', "&bank_id=963"),
                        ("REGNUM = (\n    963\n)", "REGNUM = (\n    963"),                # число строкой ниже слова
                        ("LIMITS = (\n    963,   # регномер\n)", "963,   # регномер")):
        assert hits(text) == [found], text
    for text in ("regnum = book_regnum\n\nLIMIT = 963", "x = 963_000_000  # регномер — из книги", "n = 1_963",
                 'url = base + "?limit=963"', "width = 963  # ширина"):
        assert hits(text) == [], text                    # через строку от слова, часть большего числа, не идентификатор
    assert hits('t = "SVCB"; x = "SVCBP"; name = "совкомбанк"') == ["SVCB", "совк"]
    assert plain_regnum(963) and plain_regnum(1000) and plain_regnum(1)
    assert not plain_regnum(2673) and not plain_regnum(1481)
    # длинный некруглый регномер — как раньше: целым словом, в любом месте
    assert [p.pattern for p in issuer_patterns({"name": "Образец", "tickers": ["OBRZ"], "cbr_regnum": 9999})][1] == r"\b9999\b"


def test_the_issuer_scanner_sees_a_plain_regnum_passed_to_a_regnum_parameter():
    """Голое число на месте параметра-регномера: слова о регномере в строке вызова нет — параметр называет
    определение функции (в том же или в другом модуле слоя). Число на другом месте и другое число — не находка."""
    defs = ("def dates_request(form: str, regnum: str):\n    return form, regnum\n"
            "class Client:\n    def fetch(self, reg_no, limit=963):\n        return reg_no, limit\n")
    calls = ('a = dates_request("101", 963)\n'                        # 1
             "b = dates_request(\n    form,\n    963,\n)\n"            # 2–5: число на своей строке
             "c = forms.dates_request(form, regnum=963)\n"             # 6: вызов через модуль, по имени
             "d = Client().fetch(963)\n"                               # 7: метод — место без self
             "e = Client().fetch(n, 963)\n"                            # 8: то же число на месте предела — не регномер
             'f = dates_request("963", regnum)\n'                      # 9: число на месте формы; строкой — другое правило
             "g = other(963) + dates_request(form, 2000)\n"            # 10
             "h = other(bank_id=963)\n")                               # 11: имя аргумента — слово о регномере
    parameters = regnum_parameters([defs])
    assert parameters == {"dates_request": {"positions": {1}, "names": {"regnum"}},
                          "fetch": {"positions": {0}, "names": {"reg_no"}}}
    assert [line for line, _ in regnum_call_hits(calls, 963, parameters)] == [1, 4, 6, 7, 11]
    assert regnum_call_hits(calls, 963, {}) == [(6, "регномер «963» аргументом вызова dates_request"),
                                                (11, "регномер «963» аргументом вызова other")]
    assert regnum_call_hits(defs, 963, parameters) == []            # умолчание предела в определении — не вызов
    # настоящий слой: функции запросов службы форм принимают регномер параметром — определения видны правилу
    real = regnum_parameters(p.read_text(encoding="utf-8") for p in CODE)
    assert "dates_request" in real and "form_request" in real, sorted(real)


def test_the_scanner_has_teeth():
    assert _constants("x = 2027 if y else 2.5\n'2028'\n") == [(1, 2027), (1, 2.5)]


def test_no_numbers_of_the_book_or_facts_in_code():
    data = _data_numbers()
    bad = []
    for p in CODE:
        for ln, v in _constants(p.read_text(encoding="utf-8")):
            if type(v) is int and abs(v) < 10_000:
                continue                      # счётчики, дни, коды — не числа книги
            fv = float(v)
            if fv in TRIVIAL or fv not in data:
                continue
            if (p.name, fv) in NAMED_LITERALS:
                continue
            bad.append(f"{p.name}:{ln}: {v}")
    assert not bad, "числа книги, фактов или истории в indicators/: " + "; ".join(bad)


def test_half_is_not_trivial_and_is_allowed_by_file_only():
    """0,5 — число книги (ключи, равные половине): сканер его видит, разрешение — по файлу с причиной."""
    assert 0.5 not in TRIVIAL
    allowed = {name for (name, value) in NAMED_LITERALS if value == 0.5}
    seen = {p.name for p in CODE if 0.5 in {float(v) for _, v in _constants(p.read_text(encoding="utf-8"))}}
    assert seen == allowed, f"0,5 в коде без названной причины: {sorted(seen - allowed)}"


def test_the_integer_key_of_the_book_is_read_not_hardcoded(monkeypatch, tmp_path):
    """Целые сканер не ловит — их проверяет чувствительность: лаг решения книги двигает тревогу реестра."""
    from datetime import date

    from indicators import collect, config
    from indicators.store import Store

    book = yaml.safe_load(FIXTURE_BOOK.read_text(encoding="utf-8"))
    seen = {}
    for lag in (1, 2):
        book["dividends"]["calendar"]["decision_lag_quarters"] = lag
        path = tmp_path / f"book{lag}.yaml"
        path.write_text(yaml.safe_dump(book, allow_unicode=True), encoding="utf-8")
        monkeypatch.setattr(config, "BOOK_PATH", path)
        monkeypatch.setattr(config, "FACTS_DIR", ROOT / "tests/fixtures/ind/facts")
        monkeypatch.setattr(config, "SOURCES_PATH", ROOT / "tests/fixtures/ind/form/sources.yaml")
        store = Store(tmp_path / f"state{lag}")
        # первый открытый квартал закрыт выплаченной записью: решает лаг второго
        store.write_state("manual/dividends.json", {"records": [
            {"year": 2026, "period": "2026Q1", "dps": 4.6, "status": "declared", "record_date": "2026-08-10",
             "pay_date": "2026-08-24", "decided_date": "2026-07-30", "source": "протокол", "origin": "issuer_docs",
             "recorded_at": "2026-08-01T07:00:00+00:00"}]})
        ctx = collect.context(store, date(2026, 10, 15))
        seen[lag] = collect.register_check(ctx).status
    # 15.10: квартал решения за второй квартал при лаге 1 (третий квартал) кончился, при лаге 2 — нет
    assert seen == {1: "degraded", 2: "ok"}


def test_every_named_literal_still_exists():
    for (name, value), why in NAMED_LITERALS.items():
        consts = {float(v) for _, v in _constants((ROOT / "indicators" / name).read_text(encoding="utf-8"))}
        assert value in consts, f"{name}: {value} больше нет — уберите из NAMED_LITERALS ({why})"


def test_environment_variables_have_no_bank_prefix():
    """Копия ядра под другой банк меняет только книгу и факты — переменные `BANK_*` и `TINVEST_TOKEN`.
    Проверяются имена переменных окружения (константы `*_ENV` и строки в обращениях к `environ`), а не
    подстрока «<тикер>_» в тексте: у короткого тикера она совпала бы с обычными именами."""
    from indicators import config, tinvest

    assert (config.STATE_ENV, config.HANDOFF_ENV, tinvest.TOKEN_ENV) == (
        "BANK_STATE_DIR", "BANK_HANDOFF_DIR", "TINVEST_TOKEN")
    names = set()
    for p in CODE:
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            # имя переменной — константа `*_ENV = "…"` или строка прямо в `os.environ.get("…")`
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and any(
                    isinstance(t, ast.Name) and t.id.endswith("_ENV") for t in node.targets):
                names.add(node.value.value)
            if isinstance(node, ast.Call) and "environ" in ast.unparse(node.func) and node.args \
                    and isinstance(node.args[0], ast.Constant):
                names.add(node.args[0].value)
    assert names == {"BANK_STATE_DIR", "BANK_HANDOFF_DIR", "TINVEST_TOKEN"}, names
    # свой префикс эксплуатации и префиксы эксплуатации панелей-образцов
    prefixes = {str(t).upper() + "_" for company in _issuers() for t in company["tickers"]} | {"SVCB_", "VTB_", "TTECH_", "SBER_"}
    bad = sorted(n for n in names if any(n.startswith(x) for x in prefixes) and n != "TINVEST_TOKEN")
    assert not bad, "переменные окружения с префиксом банка в indicators/: " + ", ".join(bad)
