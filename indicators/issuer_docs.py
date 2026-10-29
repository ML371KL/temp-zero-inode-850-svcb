"""Документы эмитента: список «дата · заголовок · ссылка», вид и период по заголовку, разбор PDF с текстом.

Откуда список (`sources.yaml → issuer_docs`): страница пресс-релизов (`press_page`: готовый HTML,
запись — дата, ссылка, заголовок), JSON-дверь документов (`door`: дерево папок, у файла —
название, ссылка, момент публикации) и, у хоста без перечня, **проба номеров** (`probe`: шаблон адреса
с `{id}`, первый ожидаемый номер `next_id`, сколько номеров вперёд `ahead`; 404 — номера ещё нет, ответ —
новый документ, следующий номер пробы — за ним; номер помнит состояние) и **слоты** (`slots`: номер, файл
под которым перезаписывается, — перекачка каждый такт, другой sha256 — новый документ). Заголовок документа
пробы и слота — имя файла из `Content-Disposition` (`filename*` по RFC 5987 или `filename`). Посты каналов
эмитента (`posts`: виды новостей) — тоже документы: пост с отчётом МСФО за открытый квартал
(`post_kinds`) — сигнал «отчёт вышел», его числа — в запись кандидата. Рабочие хосты — `hosts`; хост, который не ответил, заменяется
запасным с тем же первым именем (`fallback_hosts`), закреплённый корень — только хостам
`trusted_root_hosts`; ссылки двери на запасной хост переписываются на рабочий (`host_rewrite`).
Документ берётся только по https с названных хостов; редирект на чужой адрес не исполняется.

* **Вид и период — по заголовку** (`title_kinds`, `title_period_patterns`): месячный релиз —
  месяц `2026M08`, МСФО и справочник аналитика — квартал `2026Q2` (римский квартал «III квартал 2026»,
  код периода в имени файла «МСФО_9м26» / «12m2021» — группы `code` и `yy`, «2025m3» — `year` и `months`,
  «2025Q3» — `year` и `qn`, год без квартала — четвёртый квартал). До сравнения заголовок
  нормализуется: неразрывные пробелы и неразрывный дефис — обычные.
* **Личность документа — вид + период + sha256 содержимого** (у документа, который не качается, —
  хэш нормализованного заголовка): один файл под разными адресами страницы и двери — один
  кандидат. **Момент первого появления** адреса и документа пишется в состояние: отметка двери
  переписывается при перезаливке, восстановить её потом неоткуда.
* **Качаются и разбираются** (`PARSED`) месячный релиз (`schedule.monthly.kind`), пресс-релиз МСФО
  и документы о дивиденде. Прочие виды (отчётность, презентация, справочник, сделка) — только
  запись «появился». Первый запуск историю не качает: записи старше `BOOTSTRAP_DAYS` дней помечаются
  известными без момента появления (история рядов — в `data/indicators/seed/`). Возраст — по дню из
  заголовка («от 02.10.2026») или по отметке списка; документ о периоде, который кончился давно,
  стар при любой отметке: отметку двери переписывает перезаливка.
* **Месячный релиз** — таблицы PDF с текстовым слоем: строка таблицы начинается меткой
  (`ops_release.rows`), значение стоит в хвосте строки или на следующей; прибыль банка по РСБУ —
  фразой (`ops_release.profit`). Числа — кандидаты `issuer_docs/candidates.json`, в ряды их пишет
  дозор (`release_watch.py`).
* **Дивиденд** — рекомендация совета в пресс-релизе МСФО, «Рекомендации совета директоров…» в
  материалах собрания, решение в протоколе: период — по словам решения
  (`dividends.period_patterns`), сумма до дробления делится на коэффициент из фактов (день
  документа — его дата реестра или день собрания, а не отметка списка). Запись ложится в
  `manual/dividends.json` (вид «документ эмитента») — первый источник реестра; за квартал,
  закрытый фактами, запись не пишется.
* **PDF без текста** получает статус `needs_manual`. Распознавание (`pypdfium2` + `tesseract`)
  включается настройкой `issuer_docs.ocr: true`; любой его отказ — тоже `needs_manual` с причиной.
* Запись кандидата ложится в состояние ДО разбора: оборванный разбор (потолок юнита) не оставит
  файл без записи — следующий такт назовёт его в причинах деградации.
"""

from __future__ import annotations

import hashlib
import html as _html
import io
import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from indicators import config, http, news, periods
from indicators.sources import FAILED, Context, Result

SOURCE = "issuer_docs"
INDEX_FILE = "issuer_docs/index.json"
CANDIDATES_FILE = "issuer_docs/candidates.json"
RECHECK_DAYS = 7              # перекачка: перезалив (другой sha256) — новый винтаж
RECHECK_WINDOW_DAYS = 60      # перекачиваются только документы моложе этого
BOOTSTRAP_DAYS = 45           # первый запуск: документы старше — известны без скачивания
TEXT_LAYER_MIN_CHARS = 200
RENDER_SCALE = 3              # масштаб рендера страницы для распознавания
OCR_PAGE_TIMEOUT_S = 60       # страница дольше — зависание, а не работа
OCR_BUDGET_S = 180            # весь документ — не дольше (шаг сбора обязан уложиться в потолок юнита)
DETAIL_CHARS = 200
NOTE_BEFORE_START = "до запуска сборщика"
PENDING = "разбор не завершён"
INTERRUPTED = "разбор был оборван — число внести вручную"
LISTED = "listed"             # документ замечен в списке, не качается
# Статус разбора словами — для причин деградации, которые печатает витрина.
STATUS_WORDS = {"needs_manual": "не разобран", "failed": "не прочитан"}
DEFAULT_MONTHLY_KIND = "ras_release"
# Виды документов о дивиденде → статус записи реестра: рекомендация совета или решение собрания.
DIVIDEND_KINDS = {"ifrs_press": "recommended", "dividend_recommendation": "recommended",
                  "meeting_minutes": "declared"}
IFRS_PREFIX = "ifrs"
QUARTER_KINDS = ("ifrs", "databook")       # у этих видов период заголовка — квартал
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
MONTH_NAMES_EN = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                  "november", "december")
PERIOD_GRACE_DAYS = 120       # документ о периоде, кончившемся раньше, — старый, что бы ни говорила отметка списка
MONTH_NOMINATIVE = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
                    "октябрь", "ноябрь", "декабрь")
NUM = r"-?\d{1,3}(?: \d{3}(?![\d,]*\s*%))*(?:,\d+)?"
ISSUER_SOURCE = "документ эмитента"
PROBE_FILE = "issuer_docs/probe.json"
# Код периода в имени файла → месяцев с начала года (квартал — их треть).
PERIOD_CODE_MONTHS = {"3м": 3, "3m": 3, "1п": 6, "1p": 6, "6м": 6, "6m": 6, "9м": 9, "9m": 9, "12м": 12, "12m": 12,
                      "1кв": 3, "2кв": 6, "3кв": 9, "4кв": 12}      # «1кв26» — квартал по номеру (кварталом месяцев)


class NeedsManual(RuntimeError):
    """PDF без текста, а распознавание выключено или не сработало: число вносится руками."""


# ------------------------------------------------------------------ заголовки и списки

def normalize(text: str) -> str:
    """Текст без разметки и типографики: сущности раскрыты, неразрывные пробелы и дефисы — обычные."""
    t = _html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    t = re.sub(r"[    ]", " ", t)
    t = re.sub(r"[‐‑‒–—−]", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_press(page: str) -> list[dict[str, Any]]:
    """Страница пресс-релизов → [{date, title, url}], новые сверху. Запись — блок списка: первый абзац —
    дата словами, ссылка `panel-link`, второй абзац — заголовок."""
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", page, flags=re.S | re.I)
    parts = re.split(r'<div[^>]*data-test="panels-\d+"[^>]*>', body)
    out = []
    for chunk in parts[1:]:
        paras = [p for p in (normalize(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S)) if p]
        link = re.search(r'<a[^>]*data-test="panel-link"[^>]*href="([^"]+)"', chunk) \
            or re.search(r'<a[^>]*href="([^"]+)"[^>]*data-test="panel-link"', chunk)
        if len(paras) < 2 or link is None:
            continue
        m = re.fullmatch(r"(\d{1,2}) ([а-яё]+) (\d{4})(?: г(?:\.|ода))?", paras[0], re.I)
        if m is None:
            continue
        try:
            day = date(int(m.group(3)), news._month_no(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            continue
        out.append({"date": day, "title": paras[1], "url": _html.unescape(link.group(1))})
    return out


def parse_door(payload: Any) -> list[dict[str, Any]]:
    """Ответ двери документов → [{folder, title, url, published_at, id, size}] по всему дереву папок."""
    data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    root = data.get("response") if isinstance(data, dict) else None
    if root is None:
        raise ValueError("в ответе двери нет узла response")
    out: list[dict[str, Any]] = []

    def walk(nodes: Any, prefix: list[str]) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            if node.get("type") == "folder" or "children" in node:
                walk(node.get("children"), prefix + [normalize(str(node.get("name") or ""))])
            elif node.get("link"):
                out.append({"folder": " / ".join(p for p in prefix if p), "title": normalize(str(node.get("name") or "")),
                            "url": str(node["link"]), "published_at": node.get("publishedAt"),
                            "id": node.get("id"), "size": node.get("size")})

    walk(root if isinstance(root, list) else [root], [])
    return out


def title_period(title: str, kind: str | None, cfg: Mapping[str, Any], *, monthly_kind: str) -> str | None:
    """Период документа из заголовка: месяц — у месячного релиза, квартал — у МСФО и справочника."""
    patterns = cfg.get("title_period_patterns") or {}
    text = normalize(title).lower().replace("ё", "е")
    if kind == monthly_kind and patterns.get("month"):
        m = re.search(str(patterns["month"]), text, re.I)
        if m:
            name = m.group("month_name").lower()
            if name in MONTH_NOMINATIVE:
                return periods.month(int(m.group("year")), MONTH_NOMINATIVE.index(name) + 1)
    if kind and kind.startswith(QUARTER_KINDS):
        for name, pattern in patterns.items():
            if name == "month" or not isinstance(pattern, str):
                continue
            m = re.search(pattern, text, re.I)
            got = None if m is None else _quarter_of_match(m.groupdict())
            if got:
                return got
    return None


def _quarter_of_match(g: Mapping[str, Any]) -> str | None:
    """Квартал по группам совпадения: год (`year`, или две цифры `yy`) и квартал — римский (`q`), номер (`qn`),
    число месяцев с начала года (`months`) или код периода имени файла (`code`: 3м, 1п, 9м, 12m…); без квартала
    — год, четвёртый квартал."""
    raw_year = g.get("year") or g.get("yy")
    if not raw_year:
        return None
    year = int(raw_year)
    if len(str(raw_year)) == 2:                     # «3м26»: век — нынешний
        year += date.today().year // 100 * 100
    if g.get("q"):
        q = ROMAN.get(str(g["q"]).lower())
    elif g.get("qn"):
        q = int(g["qn"])
    elif g.get("months"):
        q = int(g["months"]) // 3 if int(g["months"]) in (3, 6, 9, 12) else None
    elif g.get("code"):
        months = PERIOD_CODE_MONTHS.get(str(g["code"]).lower())
        q = None if months is None else months // 3
    else:
        q = 4
    return periods.quarter(year, q) if q in (1, 2, 3, 4) else None


def content_title(headers: Mapping[str, str]) -> str | None:
    """Имя файла из `Content-Disposition` без расширения: `filename*=UTF-8''…` (RFC 5987, проценты раскрыты), иначе
    `filename="…"`. Нет заголовка или имени — None."""
    value = next((v for k, v in (headers or {}).items() if str(k).lower() == "content-disposition"), None)
    if not value:
        return None
    m = re.search(r"filename\*\s*=\s*([\w-]+)'[^']*'([^;]+)", value, re.I)
    if m:
        try:
            name = urllib.parse.unquote(m.group(2).strip().strip('"'), encoding=m.group(1) or "utf-8")
        except LookupError:
            name = urllib.parse.unquote(m.group(2).strip().strip('"'))
    else:
        m = re.search(r'filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)', value, re.I)
        if m is None:
            return None
        name = (m.group(1) or m.group(2) or "").strip()
        try:                                        # латиница-1 заголовка — байты UTF-8 имени
            name = name.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    name = normalize(re.sub(r"\.(?:pdf|xlsx?|docx?|zip)$", "", name, flags=re.I))
    return name or None


def classify(title: str, cfg: Mapping[str, Any], *, monthly_kind: str = DEFAULT_MONTHLY_KIND) -> dict[str, Any]:
    """Вид и период документа по заголовку: первый совпавший шаблон `title_kinds` (в порядке настройки)."""
    text = normalize(title).lower().replace("ё", "е")
    kind = None
    for name, pattern in (cfg.get("title_kinds") or {}).items():
        if re.search(str(pattern), text, re.I):
            kind = str(name)
            break
    return {"kind": kind, "period": title_period(title, kind, cfg, monthly_kind=monthly_kind)}


def classify_url(url: str, kinds: Mapping[str, str]) -> str | None:
    """Вид документа по адресу (`kinds`) — для эмитента без списка с заголовками."""
    for kind, pattern in (kinds or {}).items():
        if re.search(pattern, url, re.I):
            return kind
    return None


def month_from_url(url: str, patterns: list[str]) -> str | None:
    """Месяц релиза из имени файла по шаблонам с группами `months` (число месяцев с начала года) или
    `month_name` (английское название) и `year` — для эмитента, у которого вид и период читаются по адресу."""
    for pat in patterns or []:
        m = re.search(pat, url, re.I)
        if not m:
            continue
        g = m.groupdict()
        year = int(g["year"])
        if g.get("months"):
            return periods.month(year, int(g["months"]))
        if g.get("month_name"):
            name = g["month_name"].lower()
            for i, n in enumerate(MONTH_NAMES_EN):
                if name.startswith(n[:3]):
                    return periods.month(year, i + 1)
    return None


def title_day(title: str) -> str | None:
    """День документа из заголовка («Протокол № 16 от 02.10.2026») — он не меняется при перезаливке файла."""
    m = re.search(r"\bот (\d{2})\.(\d{2})\.(\d{4})\b", normalize(title))
    if m is None:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def period_day(period: str | None) -> str | None:
    """Последний день периода документа (месяца или квартала)."""
    if not period:
        return None
    if periods.is_month(period):
        return periods.month_end(period).isoformat()
    return periods.quarter_end(period).isoformat() if periods.is_quarter(period) else None


def rewrite_host(url: str, rewrite: Mapping[str, str]) -> str:
    """Ссылка на запасной хост → тот же путь на рабочем (`host_rewrite`)."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    target = (rewrite or {}).get(host)
    return urllib.parse.urlunsplit(parts._replace(netloc=target)) if target else url


def fallback_urls(url: str, fallback_hosts: list[str]) -> list[str]:
    """Тот же адрес на запасных хостах с тем же первым именем (`cdn.` → `cdn.`, `cfg.` → `cfg.`)."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    head = host.split(".", 1)[0]
    return [urllib.parse.urlunsplit(parts._replace(netloc=h)) for h in fallback_hosts or []
            if h.lower() != host and h.lower().split(".", 1)[0] == head]


def title_key(title: str) -> str:
    return hashlib.sha256(normalize(title).lower().encode("utf-8")).hexdigest()


def document_key(kind: str | None, period: str | None, digest: str) -> str:
    """Личность документа: вид, период, хэш (содержимого или заголовка)."""
    return f"{kind or 'other'}:{period or '-'}:{digest[:12]}"


# ------------------------------------------------------------------ текстовый слой и распознавание

def text_pages(body: bytes) -> list[str]:
    """Текст страниц (pdfplumber, импорт ленивый); пустая страница — ''."""
    import pdfplumber  # noqa: PLC0415 — зависимость только инструмента разбора PDF

    with pdfplumber.open(io.BytesIO(body)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def has_text_layer(pages: list[str]) -> bool:
    return sum(len(p.strip()) for p in pages) >= TEXT_LAYER_MIN_CHARS


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def tsv_lines(tsv: str) -> list[str]:
    """TSV tesseract (уровень слов) → строки текста по (block, par, line), слова — слева направо."""
    groups: dict[tuple, list[tuple[int, str]]] = {}
    header = None
    for raw in tsv.splitlines():
        cols = raw.split("\t")
        if header is None:
            header = cols
            continue
        if len(cols) != len(header):
            continue
        row = dict(zip(header, cols))
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        key = (int(row["page_num"]), int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        groups.setdefault(key, []).append((int(row["left"]), row["text"]))
    return [" ".join(t for _, t in sorted(words)) for _, words in sorted(groups.items())]


def _brief(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:DETAIL_CHARS]


def ocr_pages(body: bytes, *, lang: str = "rus", page_timeout: float = OCR_PAGE_TIMEOUT_S,
              budget: float = OCR_BUDGET_S) -> list[str]:
    """Рендер pypdfium2 + tesseract → текст страниц. Любой отказ — `NeedsManual` с причиной: зависший
    или упавший tesseract, нерендерящийся PDF и мусор в выводе не роняют сборщик."""
    if not tesseract_available():
        raise NeedsManual("PDF без текстового слоя, tesseract не установлен")
    try:
        import pypdfium2 as pdfium  # noqa: PLC0415 — зависимость только инструмента разбора PDF
    except ImportError as exc:
        raise NeedsManual("PDF без текстового слоя, pypdfium2 не установлен") from exc

    started = time.monotonic()
    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        try:
            pdf = pdfium.PdfDocument(body)
            count = len(pdf)
        except Exception as exc:  # noqa: BLE001 — ошибки pdfium: битый или защищённый PDF
            raise NeedsManual(f"PDF не открывается для рендера — {_brief(exc)}") from exc
        for i in range(count):
            where = f"стр. {i + 1} из {count}"
            left = budget - (time.monotonic() - started)
            if left <= 0:
                raise NeedsManual(f"распознавание не уложилось в {budget:.0f} с ({where})")
            png = Path(tmp) / f"p{i + 1}.png"
            try:
                pdf[i].render(scale=RENDER_SCALE).to_pil().convert("L").save(png)
            except Exception as exc:  # noqa: BLE001 — pdfium, растровая библиотека, диск
                raise NeedsManual(f"{where} не рендерится — {_brief(exc)}") from exc
            wait = min(page_timeout, left)
            try:
                done = subprocess.run(["tesseract", str(png), "-", "-l", lang, "--psm", "6", "tsv"],
                                      capture_output=True, text=True, encoding="utf-8", errors="replace",
                                      timeout=wait)
            except subprocess.TimeoutExpired as exc:
                raise NeedsManual(f"tesseract не ответил за {wait:.0f} с ({where})") from exc
            except OSError as exc:
                raise NeedsManual(f"tesseract не запустился — {_brief(exc)}") from exc
            if done.returncode != 0:
                said = (done.stderr or "").strip().splitlines()
                raise NeedsManual(f"tesseract: код {done.returncode} ({where})"
                                  + (f" — {said[-1][:DETAIL_CHARS]}" if said else ""))
            try:
                pages.append("\n".join(tsv_lines(done.stdout)))
            except (ValueError, KeyError) as exc:
                raise NeedsManual(f"вывод tesseract не разобран ({where}) — {_brief(exc)}") from exc
    return pages


# ------------------------------------------------------------------ месячный релиз

def _number(token: str) -> float:
    return float(token.replace(" ", "").replace(",", "."))


def _lines(text: str) -> list[str]:
    t = re.sub(r"[    ]", " ", text)
    t = re.sub(r"[‐‑‒–−]", "-", t)
    return [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.split("\n")]


def parse_ops_release(text: str, spec: Mapping[str, Any]) -> dict[str, float]:
    """Таблицы и фраза прибыли месячного релиза → {метрика: значение}: млн клиентов, млрд ₽, нормативы — доли.

    Строка таблицы в текстовом слое рвётся по-разному: значение стоит в хвосте строки метки, на
    следующей строке или после продолжения метки. Поэтому берётся «кусок» — от конца метки до
    следующей известной метки (не дальше двух строк); из него убираются хвосты меток с их числами
    (`strip`: «Н1.1 (мин 4,5%)») и читается первое число (`kind: value` — не процент и не «п.п.»;
    `kind: percent` — число перед «%»). Метрика берётся из первой совпавшей строки. Прибыль с начала
    года — первая совпавшая фраза `profit` (группа `value`); фраза с группой `excl` («без учёта
    разовых…») — показатель эмитента, а не прибыль по РСБУ: в ряд не идёт.
    """
    rows = dict(spec.get("rows") or {})
    lines = _lines(text)
    start = next((i for i, ln in enumerate(lines) if spec.get("start") and re.match(str(spec["start"]), ln)), 0)
    stop = next((i for i, ln in enumerate(lines) if spec.get("stop") and re.match(str(spec["stop"]), ln)), len(lines))
    body = lines[start:stop]
    labels = [str(r.get("label")) for r in rows.values() if r.get("label")]
    boundary = re.compile("|".join(f"(?:{x})" for x in labels + [str(b) for b in spec.get("breaks") or []]) or r"(?!)")
    strip = [str(x) for x in spec.get("strip") or []]
    out: dict[str, float] = {}
    for i, ln in enumerate(body):
        for metric, row in rows.items():
            if metric in out or not row.get("label"):
                continue
            m = re.match(str(row["label"]), ln)
            if m is None:
                continue
            parts = [ln[m.end():]]
            for nxt in body[i + 1:i + 3]:
                if boundary.match(nxt):
                    break
                parts.append(nxt)
            chunk = " ".join(parts)
            for pattern in strip:
                chunk = re.sub(pattern, " ", chunk)
            chunk = re.sub(r"\s+", " ", chunk).strip()
            if row.get("kind") == "percent":
                got = re.search(r"(?<![\d,.])(\d{1,2}(?:,\d+)?)\s*%", chunk)
                if got:
                    out[metric] = round(_number(got.group(1)) / 100.0, 10)
            else:
                got = re.search(r"(?<![\d,.])(" + NUM + r")(?!\s*%)(?!\s*п\.п)(?![\d,])", chunk)
                if got:
                    out[metric] = _number(got.group(1))
            break
    flat = re.sub(r"\s+", " ", " ".join(lines))
    for pattern in spec.get("profit") or []:
        m = re.search(str(pattern).replace("{num}", NUM), flat)
        if m is None or (m.groupdict().get("excl") or "").strip():
            continue                    # фразы нет или это показатель «без учёта разовых…»
        out[str(spec.get("profit_metric") or "np_ytd")] = _number(m.group("value"))
        break
    return out


# ------------------------------------------------------------------ дивиденд в документе

_RU_DATE = r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s+года"
# Формула рекомендации, проекта решения и протокола: «Выплатить дивиденды … за <период> в размере
# 4 (четыре) рубля 70 копеек на 1 (одну) обыкновенную акцию»; сумма бывает «92,5 рубля (…)»,
# «32 (Тридцать два) рубля».
_DECISION = re.compile(
    r"Выплатить дивиденды[^.]{0,220}?\sза\s+(?P<period>[^.]{0,40}?\d{4}\s+(?:года|год))(?![а-яё])[^.]{0,120}?\s+в размере\s+"
    r"(?P<rub>\d+(?:,\d+)?)\s*(?:\([^)]*\)\s*)?рубл\w*(?:\s*\([^)]*\))?(?:\s+(?P<kop>\d{1,2})\s+копе\w+)?\s+"
    r"на\s+(?:1\s*\([Оо]дну\)|одну)\s+обыкновенную акцию", re.S)
_RECORD = re.compile(r"дату, на которую определяются лица, имеющие\s+право на получение дивидендов.{0,200}?"
                     r"(?:[–—-])\s*" + _RU_DATE, re.S)
_PAY = re.compile(r"в срок\s+не позднее\s+" + _RU_DATE, re.S)
_MEETING = re.compile(r"(?:собрани\w+ акционеров|голосовани\w+ общего собрания акционеров)[^.]{0,80}?\s" + _RU_DATE,
                      re.S)
# Заочное собрание: решение принято в день окончания приёма бюллетеней — он стоит в шапке протокола
# («Дата окончания приема 01 октября 2026 года (включительно) бюллетеней для голосования»).
_BALLOT_END = re.compile(r"Дата окончания при[её]ма\s+" + _RU_DATE, re.S | re.I)
# Ссылка на нормативный акт («…«Об общих собраниях акционеров» от 16 ноября 2018 года») — не дата собрания.
_ACT_REFERENCE = re.compile(r"акционеров\s*[»\"”]\s*от\s", re.S)
_ADOPTED = re.compile(r"РЕШЕНИЕ ПО ВОПРОСУ[^.]{0,60}?ПРИНЯТО", re.S)
# Пресс-релиз МСФО: «…совет директоров рекомендовал выплатить 4,7 рублей на акцию по результатам
# II квартала 2026 г.», «Дивиденды в размере 35 рубля на акцию рекомендовал выплатить совет директоров…».
_PRESS = re.compile(
    r"(?:[Дд]ивиденд\w*[^.]{0,90}?в размере|рекомендовал\w*\s+(?:очередную\s+)?(?:выплат\w+|выплатить)\s*[—–-]?)\s*"
    r"(?P<rub>\d+(?:,\d+)?)\s*рубл\w*\s+на\s+акцию(?P<tail>[^.]{0,120}?по\s+(?:результатам|итогам)\s+[^.]{3,40})", re.S)


def _day(day: str, month: str, year: str) -> str | None:
    try:
        return date(int(year), news._month_no(month), int(day)).isoformat()
    except ValueError:
        return None


def parse_dividend_document(text: str, kind: str, *, period_patterns: Mapping[str, Any] | None,
                            published: date | None = None) -> dict[str, Any] | None:
    """Рекомендация или решение о дивиденде в тексте документа эмитента → поля записи реестра или None.

    Документы собрания (`dividend_recommendation`, `meeting_minutes`): формула «Выплатить дивиденды …
    за <период> в размере …», дата реестра, срок выплаты номинальным держателям, дата собрания.
    Протокол даёт `declared`, только если решение принято («РЕШЕНИЕ ПО ВОПРОСУ … ПРИНЯТО»).
    Пресс-релиз МСФО (`ifrs_press`): сумма и слова периода, без дат. Сумма — как в документе
    (пересчёт на дробление — у вызывающего).
    """
    flat = re.sub(r"\s+", " ", re.sub(r"[  ]", " ", text or "")).replace("‑", "-")
    status = DIVIDEND_KINDS.get(kind)
    if status is None:
        return None
    if kind == "ifrs_press":
        m = _PRESS.search(flat)
        got = news.period_of(m.group("tail"), dict(period_patterns or {}), published=published) if m else None
        if got is None:
            return None
        return {"status": status, "period": got[0], "label": got[1], "dps": _number(m.group("rub")),
                "record_date": None, "pay_date": None, "meeting_date": None, "phrase": m.group(0)[:220]}
    m = _DECISION.search(flat)
    got = news.period_of("за " + m.group("period"), dict(period_patterns or {}), published=published) if m else None
    if got is None:
        return None
    if kind == "meeting_minutes" and not _ADOPTED.search(flat):
        return None
    dps = _number(m.group("rub")) + (int(m.group("kop")) / 100.0 if m.group("kop") else 0.0)
    record = _RECORD.search(flat)
    pay = _PAY.search(flat)
    meeting = _BALLOT_END.search(flat) or next(
        (found for found in _MEETING.finditer(flat) if not _ACT_REFERENCE.search(found.group(0))), None)
    return {"status": status, "period": got[0], "label": got[1] or re.sub(r"\s+", " ", "за " + m.group("period")),
            "dps": round(dps, 4), "record_date": _day(*record.groups()) if record else None,
            "pay_date": _day(*pay.groups()) if pay else None,
            "meeting_date": _day(*meeting.groups()) if meeting else None, "phrase": m.group(0)[:220]}


def split_adjusted(dps: float, day: str | None, splits: list[Mapping[str, Any]]) -> float:
    """Сумма на акцию из документа с датой раньше дробления — в нынешних акциях (коэффициент из фактов)."""
    out = float(dps)
    for s in splits or []:
        cut = str(s.get("date") or s.get("first_trade_date") or "")
        if day and cut and day < cut and s.get("factor"):
            out /= float(s["factor"])
    return round(out, 6)


# ------------------------------------------------------------------ разбор

def analyse_text(text: str, kind: str, cfg: Mapping[str, Any], *, monthly_kind: str,
                 period_patterns: Mapping[str, Any] | None = None, published: date | None = None) -> dict[str, Any]:
    """Разбор текста документа по виду → {status, numbers, decision?}."""
    if kind == monthly_kind:
        numbers = parse_ops_release(text, cfg.get("ops_release") or {})
        out: dict[str, Any] = {"status": "ok" if numbers else "needs_manual", "numbers": numbers}
        if not numbers:
            out["detail"] = "в тексте не найдены таблицы релиза"
        return out
    if kind in DIVIDEND_KINDS:
        return {"status": "ok", "numbers": {},
                "decision": parse_dividend_document(text, kind, period_patterns=period_patterns, published=published)}
    return {"status": "ok", "numbers": {}}


def analyse(body: bytes, kind: str, cfg: Mapping[str, Any], *, monthly_kind: str = DEFAULT_MONTHLY_KIND,
            period_patterns: Mapping[str, Any] | None = None, published: date | None = None) -> dict[str, Any]:
    """PDF → текст (текстовый слой; без него — распознавание, если включено) → разбор по виду."""
    try:
        pages = text_pages(body)
    except Exception as exc:  # noqa: BLE001 — битый PDF — не падение такта
        return {"status": "failed", "detail": f"pdfplumber: {type(exc).__name__}: {exc}"[:DETAIL_CHARS], "numbers": {}}
    method = "text"
    if not has_text_layer(pages):
        if not cfg.get("ocr"):
            return {"status": "needs_manual", "numbers": {},
                    "detail": "PDF без текстового слоя: распознавание выключено настройкой"}
        started = time.monotonic()
        try:
            pages = ocr_pages(body)
        except NeedsManual as exc:
            return {"status": "needs_manual", "detail": str(exc), "numbers": {}}
        method = f"ocr ({time.monotonic() - started:.0f} с)"
    out = analyse_text("\n".join(pages), kind, cfg, monthly_kind=monthly_kind, period_patterns=period_patterns,
                       published=published)
    out["method"] = method
    return out


# ------------------------------------------------------------------ сбор

def _settings(ctx: Context) -> dict[str, Any]:
    cfg = dict(ctx.cfg.get(SOURCE) or {})
    monthly = ((ctx.cfg.get("schedule") or {}).get("monthly") or {})
    cfg["_monthly_kind"] = str(monthly.get("kind") or DEFAULT_MONTHLY_KIND) if isinstance(monthly, dict) \
        else DEFAULT_MONTHLY_KIND
    cfg["_hosts"] = list(cfg.get("hosts") or []) + list(cfg.get("fallback_hosts") or [])
    return cfg


def _fetch(ctx: Context, url: str, cfg: Mapping[str, Any], *, name: str) -> http.Response:
    """Запрос к хосту эмитента: рабочий адрес, при отказе сети — тот же путь на запасном хосте."""
    hosts = cfg["_hosts"]
    getter = ctx.getter or http.fetch
    sink = http.Sink(ctx.store, SOURCE)
    last: http.FetchError | None = None
    for candidate in [url] + fallback_urls(url, list(cfg.get("fallback_hosts") or [])):
        if not http.on_hosts(candidate, hosts):
            raise http.FetchError(candidate, None, "адрес не на хосте эмитента по https", final=True)
        try:
            resp = getter(candidate, sink=sink, name=name, hosts=hosts)
        except http.FetchError as exc:
            last = exc
            if exc.final:
                raise
            continue
        if not http.on_hosts(resp.landed, hosts):
            raise http.FetchError(candidate, None, f"ответ пришёл с чужого адреса ({http.host_of(resp.landed)})",
                                  final=True)
        return resp
    assert last is not None
    raise last


def listing(ctx: Context, cfg: Mapping[str, Any], res: Result) -> tuple[list[dict[str, Any]], int]:
    """Список документов со страницы пресс-релизов и из папок двери → (записи, сколько списков ответило)."""
    entries: list[dict[str, Any]] = []
    answered = 0
    rewrite = dict(cfg.get("host_rewrite") or {})
    if cfg.get("press_page"):
        try:
            resp = _fetch(ctx, str(cfg["press_page"]), cfg, name="press_page.html")
            rows = parse_press(news.decode(resp.body))
            if not rows:
                res.degrade("страница пресс-релизов: в ответе нет ни одной записи списка")
            else:
                answered += 1
            entries += [{"url": rewrite_host(r["url"], rewrite), "title": r["title"], "listed": r["date"],
                         "published_at": None, "where": "press", "seen": resp.fetched_at} for r in rows]
            res.raw += 1
        except http.FetchError as exc:
            res.degrade(f"страница пресс-релизов: {exc}", retry=http.retryable(exc))
    door = cfg.get("door") or {}
    for folder in door.get("folders") or []:
        section, path = str(folder.get("section") or ""), str(folder.get("path") or "")
        url = str(door.get("url") or "").format(section=urllib.parse.quote(section), path=urllib.parse.quote(path))
        words = f"дверь документов, папка «{path or section}»"
        try:
            resp = _fetch(ctx, url, cfg, name=f"door_{section}_{path or 'root'}.json")
            rows = parse_door(resp.body.decode("utf-8", errors="replace"))
            answered += 1
            res.raw += 1
        except http.FetchError as exc:
            res.degrade(f"{words}: {exc}", retry=http.retryable(exc))
            continue
        except ValueError as exc:
            res.degrade(f"{words}: ответ не разобран — {_brief(exc)}")
            continue
        entries += [{"url": rewrite_host(r["url"], rewrite), "title": r["title"],
                     "listed": str(r.get("published_at") or "")[:10] or None,
                     "published_at": r.get("published_at"), "where": f"door:{section}/{path}",
                     "seen": resp.fetched_at} for r in rows]
    return entries, answered


def probe_listing(ctx: Context, cfg: Mapping[str, Any], res: Result) -> tuple[list[dict[str, Any]], int]:
    """Проба номеров (`probe`) и слоты (`slots`) хоста без перечня → (записи с готовым ответом, сколько адресов
    ответило). У пробы 404 — номера ещё нет (ответ хоста: хост жив); ответ с файлом — документ, и следующий номер
    пробы — за ним (`issuer_docs/probe.json`). Слот качается каждый такт: sha256 сверяет `collect`."""
    entries: list[dict[str, Any]] = []
    answered = 0
    state = ctx.store.read_state(PROBE_FILE) or {}
    for spec in cfg.get("probe") or []:
        tpl, words = str(spec.get("url") or ""), str(spec.get("title") or "документы по номерам")
        if "{id}" not in tpl:
            res.degrade(f"проба номеров «{words}»: в шаблоне адреса нет {{id}}", retry=False)
            continue
        start = max(int(spec.get("next_id") or 1), int(state.get(tpl) or 0))
        for n in range(start, start + max(1, int(spec.get("ahead") or 1))):
            url = tpl.format(id=n)
            try:
                resp = _fetch(ctx, url, cfg, name=f"probe_{n}")
            except http.FetchError as exc:
                if exc.status == 404:
                    answered += 1
                    continue
                res.degrade(f"проба номеров «{words}», номер {n}: {exc}", retry=http.retryable(exc))
                continue
            answered += 1
            res.raw += 1
            state[tpl] = n + 1
            entries.append({"url": url, "title": content_title(resp.headers) or f"{words} № {n}", "listed": None,
                            "published_at": None, "where": f"probe:{words}", "seen": resp.fetched_at,
                            "response": resp})
    for spec in cfg.get("slots") or []:
        tpl, words = str(spec.get("url") or ""), str(spec.get("title") or "слот документов")
        url = tpl.format(id=spec.get("id"))
        try:
            resp = _fetch(ctx, url, cfg, name=f"slot_{spec.get('id')}")
        except http.FetchError as exc:
            res.degrade(f"слот «{words}»: {exc}", retry=http.retryable(exc))
            continue
        answered += 1
        res.raw += 1
        entries.append({"url": url, "title": content_title(resp.headers) or words, "listed": None,
                        "published_at": None, "where": f"slot:{words}", "seen": resp.fetched_at, "response": resp,
                        "slot": True})
    ctx.store.write_state(PROBE_FILE, state)
    return entries, answered


def post_candidates(ctx: Context, cfg: Mapping[str, Any], candidates: dict[str, Any], index: dict[str, Any],
                    monthly_kind: str) -> list[str]:
    """Посты каналов эмитента (`posts`: виды новостей `news/items.json`) → кандидаты-документы. Пост берётся, когда
    его текст с названиями файлов — отчёт МСФО (`post_kinds`: вид → выражение, первое совпавшее) за квартал после
    квартала фактов книги (`meta.facts_date`): старые отчёты и посты о прошлом в выпуск не будят. Период — по коду
    в имени файла (`title_period_patterns`), иначе по словам периода (`dividends.period_patterns`). Числа поста
    (`news.extract_release_numbers`, `news.extract_headline`) — в запись кандидата: первичка рядом с моментом и sha256
    текста."""
    kinds_of_posts = {str(k) for k in cfg.get("posts") or []}
    post_kinds = dict(cfg.get("post_kinds") or {})
    if not kinds_of_posts or not post_kinds:
        return []
    facts_day = str(config.book_value("meta.facts_date") or "")[:10]
    floor = periods.quarter_of(date.fromisoformat(facts_day)) if facts_day else None
    patterns = (ctx.cfg.get("dividends") or {}).get("period_patterns")
    items = (ctx.store.read_state("news/items.json") or {}).get("items") or {}
    added = []
    for url, item in sorted(items.items()):
        if str(item.get("kind") or "") not in kinds_of_posts:
            continue
        text = str(item.get("text") or "")
        low = normalize(text).lower().replace("ё", "е")
        kind = next((str(k) for k, rx in post_kinds.items() if re.search(str(rx), low, re.I)), None)
        if kind is None:
            continue
        period = title_period(text, kind, cfg, monthly_kind=monthly_kind)
        if period is None:
            got = news.period_of(text, patterns, published=news.published_day(item.get("published")))
            period = got[0] if got else None
        if period is None or (floor and period <= floor):
            continue
        digest = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
        key = document_key(kind, period, digest)
        if key in candidates:
            continue
        numbers = {m: v for m, (v, _) in {**news.extract_release_numbers(text), **news.extract_headline(text)}.items()}
        seen = str(item.get("first_seen") or ctx.moment())
        candidates[key] = {"status": LISTED, "kind": kind, "period": period, "title": text[:120], "url": url,
                           "first_seen": seen, "published": item.get("published"), "sha256": digest,
                           "numbers": numbers, "origin": "post"}
        index.setdefault(url, {"first_seen": seen, "versions": [], "title": text[:120], "kind": kind,
                               "period": period, "where": "post", "listed": str(item.get("published") or "")[:10]
                               or None})
        added.append(key)
    return added


def _called(cand: Mapping[str, Any]) -> str:
    """Документ словами: заголовок и период — без адреса (он в записи кандидата)."""
    title = str(cand.get("title") or "документ эмитента")
    return f"«{title[:80]}»" + (f" ({cand['period']})" if cand.get("period") and cand["period"] not in title else "")


def record_decision(ctx: Context, cand: Mapping[str, Any], decision: Mapping[str, Any], day: str | None) -> bool:
    """Рекомендация или решение из документа → запись `manual/dividends.json` (вид «документ эмитента»).
    Один документ пишет одну запись; True — записано сейчас."""
    from indicators import register  # noqa: PLC0415 — реестр импортирует новости, не этот модуль

    if any(r.get("doc_sha256") == cand.get("sha256") for r in register.manual_records(ctx.store)):
        return False
    closed = config.closed_through()
    if closed and decision["period"] <= closed:
        return False                          # квартал закрыт фактами: его решение уже в истории, запись не нужна
    status = str(decision["status"])
    decided = day
    if status == "declared":
        # день решения — день собрания: из протокола, иначе назначенный в рекомендации того же периода
        planned = next((r.get("meeting_date") for r in reversed(register.manual_records(ctx.store))
                        if r.get("period") == decision["period"] and r.get("meeting_date")), None)
        decided = decision.get("meeting_date") or planned or day
    if status == "declared" and not decision.get("record_date"):
        return False                          # решение без даты реестра записью не становится
    register.record_manual(
        ctx.store, year=periods.parse_quarter(decision["period"])[0], period=decision["period"],
        label=decision.get("label"), status=status,
        # день документа для пересчёта на дробление — его собственные даты: отметка списка переписывается
        dps=split_adjusted(decision["dps"], decision.get("record_date") or decision.get("meeting_date") or day,
                           config.splits()),
        source=f"{cand.get('title') or 'документ эмитента'}, {cand.get('url')}, sha256 {str(cand.get('sha256'))[:12]}",
        record_date=decision.get("record_date"), decided_date=decided, pay_date=decision.get("pay_date"),
        origin=SOURCE, extra={"doc_sha256": cand.get("sha256"), "doc_kind": cand.get("kind"),
                              "meeting_date": decision.get("meeting_date"), "dps_document": decision["dps"]})
    return True


def collect(ctx: Context) -> Result:
    """Список документов → новые записи индекса; новые документы разбираемых видов — скачать и разобрать."""
    cfg = _settings(ctx)
    monthly_kind = cfg["_monthly_kind"]
    parsed_kinds = {monthly_kind, *DIVIDEND_KINDS}
    res = Result(name=SOURCE)
    # Запасные хосты подписаны издателем, чьего корня нет в хранилище сервера: корень — только им.
    http.pin_trusted_root(cfg.get("trusted_root_hosts") or [])
    index = ctx.store.read_state(INDEX_FILE) or {}
    candidates = ctx.store.read_state(CANDIDATES_FILE) or {}
    for cand in candidates.values():
        if cand.get("status") == "needs_manual" and cand.get("detail") == PENDING:
            # прошлый такт оборвался на разборе этого файла: сказать один раз, заново не разбирать
            cand["detail"] = INTERRUPTED
            res.degrade(f"{_called(cand)}: {INTERRUPTED}", retry=False)
    bootstrap = not index
    now = ctx.moment()
    entries, answered = listing(ctx, cfg, res)
    probed, probe_answered = probe_listing(ctx, cfg, res)
    entries += probed
    answered += probe_answered
    if not answered and (cfg.get("press_page") or (cfg.get("door") or {}).get("folders") or cfg.get("probe")
                         or cfg.get("slots")):
        ctx.store.write_state(CANDIDATES_FILE, candidates)
        res.status, res.detail = FAILED, "ни один перечень документов эмитента не ответил"
        res.retry = True
        return res
    held: dict[str, http.Response] = {e["url"]: e.pop("response") for e in entries if e.get("response") is not None}
    slots = {e["url"] for e in entries if e.pop("slot", False)}
    # Эмитент без списка с заголовками: адреса PDF из новостей, вид — по адресу (`kinds`).
    by_url = dict(cfg.get("kinds") or {})
    if by_url:
        for url in sorted((ctx.store.read_state("news/items.json") or {}).get("pdf") or {}):
            entries.append({"url": url, "title": None, "listed": None, "published_at": None, "where": "news",
                            "kind": classify_url(url, by_url)})
    old = (ctx.today - timedelta(days=BOOTSTRAP_DAYS)).isoformat()
    stale = (ctx.today - timedelta(days=BOOTSTRAP_DAYS + PERIOD_GRACE_DAYS)).isoformat()
    # Проба и слот дня в списке не знают: на первом запуске их файл о квартале, уже закрытом фактами книги, — старый.
    facts_day = str(config.book_value("meta.facts_date") or "")[:10] or None
    fresh: list[str] = []
    for e in entries:
        if e.get("title"):
            got = classify(e["title"], cfg, monthly_kind=monthly_kind)
            e["listed"] = title_day(e["title"]) or e.get("listed")      # день из заголовка надёжнее отметки списка
        else:
            got = {"kind": e.get("kind"), "period": month_from_url(e["url"], list(cfg.get("ras_month_patterns") or []))
                   if e.get("kind") == monthly_kind else None}
        entry = index.get(e["url"])
        if entry is None:
            # момент первого появления — момент ответа списка, в котором документ впервые назван
            entry = index[e["url"]] = {"first_seen": e.get("seen") or now, "versions": []}
            ended = period_day(got["period"])
            closed = bool(e["url"] in held and ended and facts_day and ended <= facts_day)
            if bootstrap and ((e.get("listed") and e["listed"] < old) or (ended and ended < stale) or closed):
                entry.update(first_seen=None, note=NOTE_BEFORE_START)
            fresh.append(e["url"])
        entry.update({"title": e.get("title") or entry.get("title"), "kind": got["kind"], "period": got["period"],
                      "listed": e.get("listed") or entry.get("listed"), "where": e["where"],
                      "published_at": e.get("published_at") or entry.get("published_at")})
    # Ответ пробы и слота уже в руках: версия — по sha256 (у слота другой хэш — другой документ под тем же адресом).
    for url, resp in held.items():
        entry = index[url]
        versions = entry.setdefault("versions", [])
        if not versions or versions[-1]["sha256"] != resp.sha256:
            versions.append({"sha256": resp.sha256, "fetched_at": resp.fetched_at,
                             "last_modified": resp.headers.get("Last-Modified"), "etag": resp.headers.get("ETag")})
            if url in slots and len(versions) > 1:
                entry["first_seen"] = resp.fetched_at       # новый файл в слоте: момент появления — этот ответ
                entry.pop("note", None)
        entry["checked"] = resp.fetched_at
    ctx.store.write_state(INDEX_FILE, index)
    for key in post_candidates(ctx, cfg, candidates, index, monthly_kind):
        res.data.setdefault("posts", []).append(key)
    patterns = (ctx.cfg.get("dividends") or {}).get("period_patterns")
    for url in sorted(index, key=lambda u: (str(index[u].get("listed") or ""), u)):
        entry = index[url]
        kind, period = entry.get("kind"), entry.get("period")
        if entry.get("note") or kind is None:
            continue
        seen = str(entry.get("first_seen") or now)
        if kind not in parsed_kinds:
            # документ не качается: личность — вид, период, заголовок; запись «появился». Ответ пробы и слота уже
            # скачан: личность — по содержимому (sha256), версия — в индексе
            got_resp = held.get(url)
            digest = got_resp.sha256 if got_resp is not None else title_key(str(entry.get("title") or url))
            key = document_key(kind, period, digest)
            if key not in candidates:
                candidates[key] = {"status": LISTED, "kind": kind, "period": period, "title": entry.get("title"),
                                   "url": url, "first_seen": seen, "numbers": {},
                                   **({"sha256": got_resp.sha256, "fetched_at": got_resp.fetched_at}
                                      if got_resp is not None else {})}
            continue
        if entry.get("checked") and url not in held:
            age = (ctx.today - date.fromisoformat(str(entry["checked"])[:10])).days
            young = (ctx.today - date.fromisoformat(seen[:10])).days <= RECHECK_WINDOW_DAYS
            if age < RECHECK_DAYS or not young:
                continue
        resp = held.get(url)
        if resp is None:
            try:
                resp = _fetch(ctx, url, cfg, name=url.rsplit("/", 1)[-1] or "document.pdf")
            except http.FetchError as exc:
                res.degrade(f"документ эмитента {_called(entry)}: {exc}", retry=http.retryable(exc))
                continue
            res.raw += 1
        versions = entry.setdefault("versions", [])
        new = not versions or versions[-1]["sha256"] != resp.sha256
        if new:
            versions.append({"sha256": resp.sha256, "fetched_at": resp.fetched_at,
                             "last_modified": resp.headers.get("Last-Modified"), "etag": resp.headers.get("ETag")})
        entry["checked"] = resp.fetched_at
        ctx.store.write_state(INDEX_FILE, index)
        key = document_key(kind, period, resp.sha256)
        if key in candidates and candidates[key].get("detail") != PENDING:
            same = candidates[key]              # тот же файл под другим адресом — тот же документ (не `held`: там ответы)
            same["urls"] = sorted(set(same.get("urls") or [same.get("url")]) | {url})
            same["first_seen"] = min(str(same.get("first_seen") or seen), seen)
            continue
        about = {"url": url, "urls": [url], "kind": kind, "period": period, "title": entry.get("title"),
                 "sha256": resp.sha256, "fetched_at": resp.fetched_at, "first_seen": seen}
        if kind == monthly_kind:
            about["month"] = period
        # Запись — до разбора: индекс уже отметил файл проверенным.
        candidates[key] = {"status": "needs_manual", "detail": PENDING, "numbers": {}, **about}
        ctx.store.write_state(CANDIDATES_FILE, candidates)
        listed = entry.get("listed") or resp.fetched_at[:10]
        try:
            published = date.fromisoformat(str(listed)[:10])
            result = analyse(resp.body, kind, cfg, monthly_kind=monthly_kind, period_patterns=patterns,
                             published=published)
        except Exception as exc:  # noqa: BLE001 — разбор одного файла не роняет сборщик
            result = {"status": "needs_manual", "detail": f"разбор упал — {_brief(exc)}", "numbers": {}}
        result.update(about)
        candidates[key] = result
        res.data.setdefault("new", []).append(key)
        if result["status"] != "ok":
            res.degrade(f"документ эмитента {_called(result)} {STATUS_WORDS.get(result['status'], result['status'])}"
                        f" — {result.get('detail') or 'причина не названа'}; число внести вручную", retry=False)
            continue
        if kind == monthly_kind and not period:
            res.degrade(f"документ эмитента {_called(result)}: месяц релиза по заголовку не определён", retry=False)
        decision = result.get("decision")
        if decision:
            try:
                if record_decision(ctx, result, decision, str(listed)[:10]):
                    res.data.setdefault("dividends", []).append(decision["period"])
            except ValueError as exc:
                res.degrade(f"документ эмитента {_called(result)}: запись о дивиденде не принята — {exc}",
                            retry=False)
    ctx.store.write_state(INDEX_FILE, index)
    ctx.store.write_state(CANDIDATES_FILE, candidates)
    res.data["listed"] = len(fresh)
    return res


def wake_candidates(candidates: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Документы, которые будят выпуск: МСФО квартала и документы с рекомендацией или решением о дивиденде."""
    out = []
    for key, cand in candidates.items():
        kind = str(cand.get("kind") or "")
        if kind.startswith(IFRS_PREFIX) or (kind in DIVIDEND_KINDS and cand.get("decision")):
            out.append(key)
    return sorted(out)


def seen_periods(store: Any, kinds_prefix: str) -> dict[str, str]:
    """Период → день первого появления документа видов с этим началом (`ifrs`) по кандидатам состояния."""
    out: dict[str, str] = {}
    for cand in (store.read_state(CANDIDATES_FILE) or {}).values():
        period, seen = cand.get("period"), str(cand.get("first_seen") or "")[:10]
        if period and seen and str(cand.get("kind") or "").startswith(kinds_prefix):
            out[period] = min(out.get(period, seen), seen)
    return out


def last_document_url(store: Any, kind: str | None = None) -> str | None:
    """Адрес самого свежего известного документа (вида `kind`, если назван) — для пробы источников."""
    index = store.read_state(INDEX_FILE) or {}
    rows = [(str(e.get("listed") or ""), url) for url, e in index.items()
            if isinstance(e, dict) and (kind is None or e.get("kind") == kind)]
    return max(rows)[1] if rows else None

