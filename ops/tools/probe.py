"""Проба источников с сервера: доступны ли они той дорогой, какой ходят сборщики.

    python ops/tools/probe.py                   все пробы, таблица в stdout
    python ops/tools/probe.py --only iss cbr_forms
    python ops/tools/probe.py --pdf URL         документ эмитента по адресу
    python ops/tools/probe.py --json ФАЙЛ       ещё и строки таблицы в JSON

Первый шаг выкладки на новую машину (проверено с ноутбука, с сервера — пробой) и первый шаг
разбора «источник молчит». Ходит через `indicators.http` — ту же таблицу User-Agent по хостам,
без прокси окружения, с закреплённым корнем только для хостов T-Invest и запасных хостов
эмитента, — поэтому проба проверяет именно боевую дорогу, а не соседнюю. Одна попытка на пробу,
без повторов и без записи в сырой архив; эмитент (тикеры, регномер) — из `meta.company` книги,
его хосты и адреса — из `data/indicators/sources.yaml`.

Пробы:
  iss          MOEX ISS: котировки акций (TQBR) и кривая zcyc
  cbr_soap     ЦБ DailyInfo (SOAP): ключевая ставка за 30 дней
  cbr_forms    ЦБ CreditOrgInfo (SOAP) по регномеру: GetDatesForF101/102/123/135 — 4 метода
  cbr_group    ЦБ CreditOrgInfo (SOAP), формы банковской группы: внутренний код организации,
               перечень периодов, форма 0409805 за последний период перечня (итог капитала и
               Н20.0 — числами: признак наличия формы — число, а не код ответа)
  avgprocstav  ЦБ, HTML: максимальная ставка по вкладам топ-10 по декадам
  dataservice  ЦБ, JSON /dataservice: список публикаций
  issuer_docs  документы эмитента: страница пресс-релизов (записи «дата · заголовок · ссылка»),
               JSON-дверь документов по папкам настройки на рабочем хосте и первая папка — на
               запасном хосте с закреплённым корнем; документ месячного релиза. Адрес документа:
               `--pdf`; иначе последний адрес сборщика из состояния; иначе — на свежем сервере —
               самый свежий месячный релиз из только что снятого списка. Откуда адрес, сказано
               в строке таблицы. У хоста без перечня (`probe`, `slots`): последний известный номер
               пробы — файл с именем из Content-Disposition, следующий — 404 или новый файл; слот —
               файл с именем; каналы эмитента настройки новостей — превью t.me/s/<канал> с постами.
               Первые байты файла — запросом диапазона (документ целиком не качается). Документа
               месячного релиза у эмитента без месячного события нет — строки о нём тоже
  tinvest      T-Invest: TLS с закреплённым корнем (и отказ без него); с токеном из
               окружения — ShareBy главного тикера. Токен не печатается никогда

Коды: 0 — все пробы прошли (на пустом состоянии свежего сервера — тоже); 1 — хоть одна
не прошла (строка «НЕТ» с причиной); 64 — неверные аргументы.
"""
# Без `from __future__ import annotations`: dataclass с отложенными аннотациями
# не грузится через importlib.util.spec_from_file_location (так модуль грузят тесты).
import argparse
import json
import socket
import ssl
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indicators import config, http  # noqa: E402

TIMEOUT = 30.0
CREDIT_ORG_INFO = "https://www.cbr.ru/CreditInfoWebServ/CreditOrgInfo.asmx"
DAILY_INFO = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
DATASERVICE = "https://www.cbr.ru/dataservice/publications"
TINVEST_HOST = "invest-public-api.tinkoff.ru"
FORMS = ("101", "102", "123", "135")


@dataclass
class Row:
    probe: str
    what: str
    target: str               # хост и путь, без строки запроса
    ok: bool
    status: str               # HTTP-код или «TLS»/«—»
    seconds: float
    size: int | None
    note: str


def _target(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.hostname}{parts.path}"


def _timed(probe: str, what: str, url: str, call: Callable[[], tuple[bool, str, int | None, str]]) -> Row:
    """Одна проба: (годно, статус, байт, заметка) из `call`; отказ — строка «нет» с причиной."""
    start = time.monotonic()
    try:
        ok, status, size, note = call()
    except http.FetchError as exc:
        ok, status, size, note = False, str(exc.status or "—"), None, str(exc).split(": ", 1)[-1]
    except Exception as exc:  # noqa: BLE001 — проба называет любой отказ, а не падает
        ok, status, size, note = False, "—", None, f"{type(exc).__name__}: {exc}"[:200]
    return Row(probe, what, _target(url), ok, status, round(time.monotonic() - start, 2), size, note)


def _get(getter, url: str, **kwargs) -> http.Response:
    return (getter or http.fetch)(url, attempts=1, timeout=TIMEOUT, **kwargs)


# ------------------------------------------------------------------ пробы

def probe_iss(getter=None, *, company: dict, board: str) -> list[Row]:
    from indicators import iss  # noqa: PLC0415

    tickers = list(company["tickers"])
    url = iss.quotes_url(tickers, board)

    def quotes():
        resp = _get(getter, url)
        got = iss.parse_quotes(resp.json(), board)
        missing = [t for t in tickers if t not in got]
        prices = ", ".join(f"{t} {got[t].get('price')}" for t in tickers if t in got)
        return not missing, str(resp.status), len(resp.body), prices + (f"; нет {', '.join(missing)}" if missing else "")

    def zcyc():
        resp = _get(getter, iss.ZCYC_URL)
        curve = iss.parse_zcyc(resp.json())
        return True, str(resp.status), len(resp.body), f"кривая {curve['as_of']}: узлы {', '.join(curve['nodes'])}"

    return [_timed("iss", "котировки " + ", ".join(tickers), url, quotes),
            _timed("iss", "кривая zcyc", iss.ZCYC_URL, zcyc)]


def probe_cbr_soap(getter=None, *, today: date) -> list[Row]:
    from indicators import cbr  # noqa: PLC0415

    def key_rate():
        resp = http.soap(DAILY_INFO, "KeyRate", cbr.dates_inner(today - timedelta(days=30), today),
                         getter=lambda url, **kw: _get(getter, url, **kw))
        rows = cbr.parse_key_rate(resp.body)
        return True, str(resp.status), len(resp.body), f"ключевая {rows[-1][1]:.2%} на {rows[-1][0]}"

    return [_timed("cbr_soap", "DailyInfo KeyRate", DAILY_INFO, key_rate)]


def probe_cbr_forms(getter=None, *, company: dict) -> list[Row]:
    from indicators import cbr_forms  # noqa: PLC0415

    regnum = company["cbr_regnum"]
    rows = []
    for form in FORMS:
        op, inner = cbr_forms.dates_request(form, regnum)

        def dates(op=op, inner=inner):
            resp = http.soap(CREDIT_ORG_INFO, op, inner, getter=lambda url, **kw: _get(getter, url, **kw))
            got = cbr_forms.parse_dates(resp.body)        # ответ без дат — отказ пробы (FormError)
            return True, str(resp.status), len(resp.body), f"дат {len(got)}, последняя {max(got)}"

        rows.append(_timed("cbr_forms", f"{op} (регномер из книги)", CREDIT_ORG_INFO, dates))
    return rows


def probe_avgprocstav(getter=None, *, today: date) -> list[Row]:
    from indicators import cbr  # noqa: PLC0415

    url = cbr.deposits_url(today - timedelta(days=90), today)

    def page():
        resp = _get(getter, url)
        rows = cbr.parse_deposits(resp.text)
        return True, str(resp.status), len(resp.body), f"декад {len(rows)}, последняя {rows[-1][0]}: {rows[-1][1]:.3%}"

    return [_timed("avgprocstav", "ставки по вкладам топ-10", url, page)]


def probe_dataservice(getter=None) -> list[Row]:
    def publications():
        resp = _get(getter, DATASERVICE, headers={"Accept": "application/json"})
        data = resp.json()
        return isinstance(data, list) and bool(data), str(resp.status), len(resp.body), (
            f"публикаций {len(data)}" if isinstance(data, list) else f"не список: {type(data).__name__}")

    return [_timed("dataservice", "список публикаций", DATASERVICE, publications)]


def probe_cbr_group(getter=None, *, company: dict) -> list[Row]:
    """Формы банковской группы той же дорогой, что у сборщика: код организации, перечень периодов, форма 0409805."""
    from indicators import cbr_group  # noqa: PLC0415

    regnum = company["cbr_regnum"]
    seen: dict[str, str] = {}

    def soap(op: str, inner: str):
        return http.soap(CREDIT_ORG_INFO, op, inner, getter=lambda url, **kw: _get(getter, url, **kw))

    def intcode():
        resp = soap(*cbr_group.intcode_request(regnum))
        seen["code"] = cbr_group.parse_intcode(resp.body)
        return True, str(resp.status), len(resp.body), "внутренний код организации получен"

    def listing():
        if "code" not in seen:
            return False, "—", None, "нет внутреннего кода организации — перечень не запрошен"
        resp = soap(*cbr_group.periods_request(seen["code"]))
        got = cbr_group.parse_periods(resp.body)              # ответ без периодов — отказ пробы
        seen["dt"] = got["805"][-1]
        return True, str(resp.status), len(resp.body), (
            "периодов: " + ", ".join(f"0409{f} — {len(got[f])}" for f in cbr_group.FORMS)
            + f"; последний {cbr_group.period_of(seen['dt'])}")

    def form():
        if "dt" not in seen:
            return False, "—", None, "нет перечня периодов — форма не запрошена"
        parts, size, status = {}, 0, "200"
        for part, op, inner in cbr_group.form_requests("805", regnum, seen["dt"]):
            resp = soap(op, inner)
            parts[part], size, status = resp.body, size + len(resp.body), str(resp.status)
        there, lack = cbr_group.present("805", parts)
        points = cbr_group.series_points("805", parts)
        note = (f"{cbr_group.period_of(seen['dt'])}: капитал {points['cbr.f805.capital_total']:.1f} млрд ₽, "
                f"Н20.0 {points['cbr.f805.n20_0']:.2%}" if there
                else f"{cbr_group.period_of(seen['dt'])}: чисел в форме нет" + (f" ({lack})" if lack else ""))
        return there, status, size, note

    return [_timed("cbr_group", "RegNumToIntCode (регномер из книги)", CREDIT_ORG_INFO, intcode),
            _timed("cbr_group", "GetPeriodsOfDocuments", CREDIT_ORG_INFO, listing),
            _timed("cbr_group", "GetF805Xml: итог капитала и Н20.0", CREDIT_ORG_INFO, form)]


DOCS_WHAT = "документ эмитента (месячный релиз)"


def _docs_cfg(cfg: dict) -> dict:
    return dict(cfg.get("issuer_docs") or {})


def _docs_hosts(cfg: dict) -> list[str]:
    docs = _docs_cfg(cfg)
    return list(docs.get("hosts") or []) + list(docs.get("fallback_hosts") or [])


def _monthly_kind(cfg: dict) -> str:
    from indicators import issuer_docs  # noqa: PLC0415

    monthly = (cfg.get("schedule") or {}).get("monthly")
    return str(monthly.get("kind")) if isinstance(monthly, dict) and monthly.get("kind") \
        else issuer_docs.DEFAULT_MONTHLY_KIND


def last_doc_url(state: Path, kind: str) -> str | None:
    """Последний адрес документа эмитента нужного вида, известный сборщику (состояние)."""
    try:
        index = json.loads((state / "issuer_docs" / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = [(str(e.get("listed") or ""), url) for url, e in index.items()
            if isinstance(e, dict) and e.get("kind") == kind and str(url).startswith("http")]
    return max(rows)[1] if rows else None


def doc_address(cfg: dict, *, pdf: str | None = None, state: Path | None = None,
                listed: list[dict] | None = None) -> tuple[str | None, str]:
    """Адрес документа для пробы и откуда он. Порядок: `--pdf` → последний адрес сборщика в состоянии →
    самый свежий месячный релиз из только что снятого списка эмитента (свежий сервер)."""
    if pdf:
        return pdf, "адрес из --pdf"
    kind = _monthly_kind(cfg)
    known = last_doc_url(state if state is not None else config.state_dir(), kind)
    if known:
        return known, "адрес сборщика (состояние)"
    rows = sorted((r for r in listed or [] if r.get("kind") == kind and r.get("url")),
                  key=lambda r: str(r.get("date") or ""))
    if rows:
        return rows[-1]["url"], f"адрес из списка эмитента ({rows[-1].get('period') or rows[-1].get('date')})"
    return None, "адреса нет"


def probe_issuer_docs(getter=None, *, cfg: dict, pdf: str | None = None, state: Path | None = None) -> list[Row]:
    """Документы эмитента той же дорогой, что у сборщика: страница пресс-релизов, папки двери на рабочем
    хосте, первая папка — на запасном хосте с закреплённым корнем, документ месячного релиза."""
    from indicators import issuer_docs  # noqa: PLC0415

    docs = _docs_cfg(cfg)
    hosts = _docs_hosts(cfg)
    kind = _monthly_kind(cfg)
    listed: list[dict] = []
    rows: list[Row] = []

    def fetch(url: str, **kw) -> http.Response:
        return _get(getter, url, **({"hosts": hosts} if hosts else {}), **kw)

    press = str(docs.get("press_page") or "")
    if press:
        def page():
            resp = fetch(press)
            got = issuer_docs.parse_press(resp.body.decode("utf-8", errors="replace"))
            for r in got:
                r.update(issuer_docs.classify(r["title"], docs, monthly_kind=kind))
            listed.extend(got)
            monthly = [r for r in got if r["kind"] == kind]
            return bool(got), str(resp.status), len(resp.body), (
                f"записей {len(got)}, месячных релизов {len(monthly)}"
                + (f"; свежая — {got[0]['date']}" if got else "; в разметке нет ни одной записи списка"))

        rows.append(_timed("issuer_docs", "страница пресс-релизов", press, page))
    door = docs.get("door") or {}
    folders = list(door.get("folders") or [])

    def door_url(folder: dict) -> str:
        return str(door.get("url") or "").format(section=urllib.parse.quote(str(folder.get("section") or "")),
                                                 path=urllib.parse.quote(str(folder.get("path") or "")))

    def door_row(url: str, folder: dict):
        def call():
            resp = fetch(url)
            got = issuer_docs.parse_door(resp.body.decode("utf-8", errors="replace"))
            for r in got:
                r.update(issuer_docs.classify(r["title"], docs, monthly_kind=kind))
                listed.append({"url": issuer_docs.rewrite_host(r["url"], docs.get("host_rewrite") or {}),
                               "date": str(r.get("published_at") or "")[:10], "kind": r["kind"],
                               "period": r["period"], "title": r["title"]})
            return True, str(resp.status), len(resp.body), f"документов {len(got)}"
        return call

    for spec in docs.get("probe") or []:
        rows += _probe_numbers(fetch, spec)
    for spec in docs.get("slots") or []:
        url = str(spec.get("url") or "").format(id=spec.get("id"))
        rows.append(_timed("issuer_docs", f"слот: {spec.get('title') or 'документ'}", url, _file_row(fetch, url)))
    for channel in (cfg.get("news") or {}).get("telegram_channels") or []:
        name = channel["name"] if isinstance(channel, dict) else str(channel)
        url = f"https://t.me/s/{name}"

        def preview(url=url):
            from indicators import news  # noqa: PLC0415

            resp = _get(getter, url)
            posts = news.telegram_posts(resp.body.decode("utf-8", errors="replace"))
            last = max((str(p.get("time") or "") for p in posts), default="")
            return bool(posts), str(resp.status), len(resp.body), (
                f"постов {len(posts)}" + (f"; свежий — {last[:16].replace('T', ' ')} UTC" if last else
                                          "; в разметке нет ни одного поста"))

        rows.append(_timed("issuer_docs", f"канал эмитента: {name}", url, preview))
    for folder in folders:
        url = door_url(folder)
        rows.append(_timed("issuer_docs", f"дверь документов: {folder.get('path') or folder.get('section')}", url,
                           door_row(url, folder)))
    if folders:
        for url in issuer_docs.fallback_urls(door_url(folders[0]), list(docs.get("fallback_hosts") or [])):
            rows.append(_timed("issuer_docs", "дверь документов на запасном хосте (закреплённый корень)", url,
                               door_row(url, folders[0])))
    from indicators import calendar as cal  # noqa: PLC0415

    if not pdf and not press and not folders and cal.monthly_spec(cfg.get("schedule") or {}) is None:
        return rows                     # месячного релиза у эмитента нет: документа месячного релиза не ищем
    url, origin = doc_address(cfg, pdf=pdf, state=state, listed=listed)
    if not url:
        rows.append(Row("issuer_docs", DOCS_WHAT, "—", False, "—", 0.0, None,
                        "адреса нет: ни сборщик, ни список эмитента его не назвали — задайте --pdf URL"))
        return rows

    def document():
        if hosts and not http.on_hosts(url, hosts):
            return False, "—", None, f"адрес не на хосте эмитента по https; {origin}"
        resp = fetch(url)
        is_pdf = resp.body[:5] == b"%PDF-"
        return is_pdf, str(resp.status), len(resp.body), (
            f"PDF, sha256 {resp.sha256[:12]}…; {origin}" if is_pdf
            else f"ответ не PDF (страница вместо файла?); {origin}")

    rows.append(_timed("issuer_docs", DOCS_WHAT, url, document))
    return rows


RANGE = {"Range": "bytes=0-4095"}      # первые байты файла: признак PDF и заголовки, без закачки целиком


def _file_row(fetch, url: str):
    """Строка «файл есть»: ответ с PDF и именем файла из Content-Disposition (первые байты — диапазоном)."""
    def call():
        from indicators import issuer_docs  # noqa: PLC0415

        resp = fetch(url, headers=RANGE)
        is_pdf = resp.body[:5] == b"%PDF-"
        name = issuer_docs.content_title(resp.headers)
        return is_pdf, str(resp.status), len(resp.body), (f"PDF «{name}»" if name else "PDF без имени файла") \
            if is_pdf else "ответ не PDF (страница вместо файла?)"
    return call


def _probe_numbers(fetch, spec: dict) -> list:
    """Проба номеров: последний известный номер (`next_id` − 1) — файл; следующий — 404 (номера ещё нет) или новый
    файл (вышел: сборщик возьмёт его в ближайший такт)."""
    tpl, words = str(spec.get("url") or ""), str(spec.get("title") or "документы по номерам")
    n = int(spec.get("next_id") or 1)
    rows = [_timed("issuer_docs", f"проба номеров «{words}»: № {n - 1} (последний известный)", tpl.format(id=n - 1),
                   _file_row(fetch, tpl.format(id=n - 1)))]

    def ahead():
        from indicators import issuer_docs  # noqa: PLC0415

        try:
            resp = fetch(tpl.format(id=n), headers=RANGE)
        except http.FetchError as exc:
            if exc.status == 404:
                return True, "404", None, "номера ещё нет: хост отвечает «не найден» — проба работает"
            raise
        name = issuer_docs.content_title(resp.headers)
        return True, str(resp.status), len(resp.body), f"вышел новый файл «{name or 'без имени'}»"

    rows.append(_timed("issuer_docs", f"проба номеров «{words}»: № {n} (следующий)", tpl.format(id=n), ahead))
    return rows


def _tls(host: str, context: ssl.SSLContext | None) -> str:
    """Рукопожатие TLS; возвращает издателя сертификата, отказ — исключение."""
    ctx = context or ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=TIMEOUT) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as conn:
            issuer = dict(x[0] for x in conn.getpeercert().get("issuer", ()))
            return issuer.get("organizationName") or issuer.get("commonName") or "?"


def probe_tinvest(getter=None, *, company: dict, class_code: str, tls=_tls) -> list[Row]:
    from indicators import tinvest  # noqa: PLC0415

    url = tinvest.BASE + "InstrumentsService/ShareBy"
    pinned = http.tls_context(url)

    def with_pin():
        if pinned is None:
            return False, "TLS", None, f"для {TINVEST_HOST} нет закреплённого корня (indicators/http.py EXTRA_CA)"
        issuer = tls(TINVEST_HOST, pinned)
        return True, "TLS", None, f"рукопожатие с закреплённым корнем, издатель «{issuer}»"

    def without_pin():
        try:
            issuer = tls(TINVEST_HOST, None)
        except ssl.SSLError as exc:
            why = getattr(exc, "verify_message", None) or getattr(exc, "reason", None) or exc
            return True, "TLS", None, f"без закреплённого корня — отказ проверки, как ожидается ({why})"
        return True, "TLS", None, f"проходит и без закреплённого корня (издатель «{issuer}») — корень уже в системе"

    def share_by():
        if not tinvest.token():
            return False, "—", None, f"нет {tinvest.TOKEN_ENV} в окружении — источник будет «отсутствует», цены с ISS"
        main = company["main_ticker"]
        payload = tinvest.call("InstrumentsService/ShareBy",
                               {"idType": "INSTRUMENT_ID_TYPE_TICKER", "classCode": class_code, "id": main},
                               getter=lambda u, **kw: _get(getter, u, **kw))
        share = tinvest.parse_share(payload)
        return bool(share.get("uid")), "200", None, f"{main}: инструмент найден"

    return [_timed("tinvest", "TLS с закреплённым корнем", url, with_pin),
            _timed("tinvest", "TLS без закреплённого корня (справочно)", url, without_pin),
            _timed("tinvest", "ShareBy главного тикера (токен из окружения)", url, share_by)]


PROBES = ("iss", "cbr_soap", "cbr_forms", "cbr_group", "avgprocstav", "dataservice", "issuer_docs", "tinvest")
# Пробы только по имени (минуты работы, сверка качества): у этой копии таких нет.
EXTRA_PROBES: tuple[str, ...] = ()


def run(only: list[str] | None = None, *, pdf: str | None = None, getter=None, today: date | None = None,
        tls=_tls) -> list[Row]:
    today = today or date.today()
    company = config.company()
    cfg = config.sources()
    # Та же настройка, что у сборщика документов эмитента: корень издателя — только запасным хостам.
    http.pin_trusted_root(_docs_cfg(cfg).get("trusted_root_hosts") or [])
    board = (cfg.get("iss") or {}).get("board", "TQBR")
    class_code = (cfg.get("tinvest") or {}).get("class_code", board)
    chosen = only or list(PROBES)
    rows: list[Row] = []
    for name in chosen:
        if name == "iss":
            rows += probe_iss(getter, company=company, board=board)
        elif name == "cbr_soap":
            rows += probe_cbr_soap(getter, today=today)
        elif name == "cbr_forms":
            rows += probe_cbr_forms(getter, company=company)
        elif name == "cbr_group":
            rows += probe_cbr_group(getter, company=company)
        elif name == "avgprocstav":
            rows += probe_avgprocstav(getter, today=today)
        elif name == "dataservice":
            rows += probe_dataservice(getter)
        elif name == "issuer_docs":
            rows += probe_issuer_docs(getter, cfg=cfg, pdf=pdf)
        elif name == "tinvest":
            rows += probe_tinvest(getter, company=company, class_code=class_code, tls=tls)
    return rows


def table(rows: list[Row]) -> str:
    head = ("проба", "что", "адрес", "итог", "статус", "с", "байт", "заметка")
    body = [(r.probe, r.what, r.target, "да" if r.ok else "НЕТ", r.status, f"{r.seconds:.2f}",
             "—" if r.size is None else str(r.size), r.note) for r in rows]
    width = [max(len(str(x)) for x in col) for col in zip(head, *body)]
    fmt = lambda cells: "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, width)) + " |"  # noqa: E731
    return "\n".join([fmt(head), "|" + "|".join("-" * (w + 2) for w in width) + "|", *map(fmt, body)])


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=PROBES + EXTRA_PROBES, help="только эти пробы")
    ap.add_argument("--pdf", help="адрес документа эмитента (иначе — состояние сборщика, затем список эмитента)")
    ap.add_argument("--json", help="записать строки таблицы в JSON")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 64 if exc.code else 0
    rows = run(args.only, pdf=args.pdf)
    print(table(rows))
    failed = [r for r in rows if not r.ok]
    print(f"\nпроб {len(rows)}, прошли {len(rows) - len(failed)}"
          + (f"; не прошли: {', '.join(sorted({r.probe for r in failed}))}" if failed else ""))
    if args.json:
        Path(args.json).write_text(json.dumps([asdict(r) for r in rows], ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
