"""Тексты фактов Совкомбанка, которые печатает витрина: слова для владельца, даты — с годом.

Из фактов в выпуск текстом уходят названия и записки событий календаря, формулировки и записки гайденса, название
и текст дивидендной политики, слова решений о дивидендах, подписи корпоративных событий, названия и базисы
аналогов. В них нет имён файлов и полей, кодов периодов, дат без года, рабочих пометок и хвостов sha256.
Источник строки аналога уходит в выпуск без хвоста sha256: в фактах он — название документа словами, не имя файла.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"

RULES = {
    "кортеж ответа источника": re.compile(r"\(\d{4}, \d+, [A-Z]{3,}"),
    "метка класса допущения": re.compile(r"\[(?:В|Ф|Р|НП)(?:\]|,)"),
    "хвост sha256": re.compile(r"sha256 [0-9a-f]{8,}"),
    "рабочая пометка": re.compile(r"ведущ|первичк|антибот", re.I),
    "короткая дата без года": re.compile(r"(?<![\d.,])(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])(?!\d|\.\d|\s?%)"),
    "код периода": re.compile(r"(?<![\w])\d{4}(?:M\d{2}|Q[1-4])(?![\w])"),
    "дата ISO": re.compile(r"(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])"),
    "имя поля": re.compile(r"(?<![\w])[a-z]+(?:_[a-z0-9]+)+(?![\w])"),
    "true/false": re.compile(r"(?<![\w])(?:true|false|None|null)(?![\w])"),
    "путь к листу или файлу": re.compile(r"stage\d/|\.(?:csv|json|py|ya?ml)(?![\w])"),
    "e-нотация": re.compile(r"\d(?:[.,]\d+)?e[+-]?\d+", re.I),
    "десятичная точка в проценте": re.compile(r"\d\.\d+\s?%"),
    "ссылка на раздел договора или решения": re.compile(r"KEYS|LEAD|DESIGN|§"),
}
SHA_TAIL = re.compile(r",?\s*sha256\s+[0-9a-f]{8,}")
FILE_NAME = re.compile(r"[\w.\-]+\.(?:pdf|html?|xlsx?|docx?|json|csv|tsv|xml)(?![\w])", re.I)
PEER_SRC_LIMIT = 120          # срез источника строки аналога в выпуске: длиннее — слово оборвётся


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def peer_source_words(src: str) -> str:
    """Источник строки аналога, как его печатает выпуск: пункты через «; » без хвостов sha256."""
    return "; ".join(x for x in (SHA_TAIL.sub("", item).strip() for item in src.split(";")) if x)


def printed() -> list[tuple[str, str]]:
    """(место, строка) — всё, что из фактов уходит в выпуск текстом."""
    out = []
    for e in load("calendar")["events"]:
        out.append((f"calendar.{e['id']}.title", e["title"]))
        if e.get("note"):
            out.append((f"calendar.{e['id']}.note", e["note"]))
    g = load("guidance")
    for k, n in g["items"].items():
        for f in ("text", "scope_note", "event"):
            if n.get(f):
                out.append((f"guidance.items.{k}.{f}", n[f]))
    for h in g["history"]:
        out.append((f"guidance.history.{h['date']}.{h['key']}.event", h["event"]))
        out.append((f"guidance.history.{h['date']}.{h['key']}.note", h["note"]))
    d = load("dividends")
    for k in ("name", "text", "valid_until_note", "approved_by"):
        out.append((f"dividends.policy.{k}", d["policy"][k]))
    out += [("dividends.dates_rule", d["dates_rule"]), ("dividends.broker_check", d["broker_check"])]
    for r in d["history"]:
        out.append((f"dividends.history.{r['period']}.label", r["label"]))
        out.append((f"dividends.history.{r['period']}.decided_by", r["decided_by"]))
    for r in d["history_before"]:
        out.append((f"dividends.history_before.{r['year']}.label", r["label"]))
    for a in load("shares")["corporate_actions"]:
        out.append((f"shares.corporate_actions.{a['date']}.title", a["title"]))
    for i in load("capital")["instruments"]:
        out.append((f"capital.instruments.{i['isin'] or i['instrument']}.instrument", i["instrument"]))
    p = load("peers")
    out.append(("peers.basis", p["basis"]))
    for b in p["banks"]:
        out += [(f"peers.{b['ticker']}.name", b["name"]), (f"peers.{b['ticker']}.basis", b["basis"]),
                (f"peers.{b['ticker']}.capital_ratio.name", b["capital_ratio"]["name"]),
                (f"peers.{b['ticker']}.src", peer_source_words(b["src"]))]
    return out


def breaches(text: str) -> list[str]:
    return [f"{rule}: «{m.group(0)}»" for rule, rx in RULES.items() for m in [rx.search(text)] if m]


# Отступления текстов фактов (листы этапа 1) от правил витрины — поимённо; поправка — в листах этапа 1 (решение
# ведущего). Новое нарушение — провал теста.
KNOWN_BREACHES = {
    ("calendar.ras-2027-01.note", "короткая дата без года"),
    ("calendar.call-szo01-2027-02.title", "метка класса допущения"),
    ("calendar.call-szo01-2027-02.note", "метка класса допущения"),
    ("guidance.history.2026-05-15.guidance_status.note", "рабочая пометка"),
    ("dividends.dates_rule", "имя поля"),
}


def test_printed_strings_are_plain_words():
    bad = [f"{where}: {b}" for where, text in printed() for b in breaches(text)
           if (where, b.split(":")[0]) not in KNOWN_BREACHES]
    assert not bad, "\n".join(bad[:40])
    assert len(printed()) > 100, "печатаемых строк подозрительно мало — проверьте перечень"


def test_peer_row_source_is_a_document_title():
    """Источник строки аналога (`banks[].src`) уходит в выпуск: название документа словами — без имени файла папки
    передачи; у пункта — хвост sha256 документа той панели, откуда строка скопирована (строка Т — из фактов панели Т,
    хвоста нет); без хвостов строка помещается в срез выпуска целиком."""
    p = load("peers")
    names = {Path(d["file"]).name for d in p["sources"] if d.get("file")}
    bad = []
    for b in p["banks"]:
        if b["ticker"] != "T":
            for item in (x.strip() for x in b["src"].split(";")):
                if not re.search(r"sha256 [0-9a-f]{16}$", item):
                    bad.append(f"{b['ticker']}: у пункта нет хвоста sha256 документа — «{item}»")
        words = peer_source_words(b["src"])
        if FILE_NAME.search(words) or any(n in words for n in names):
            bad.append(f"{b['ticker']}: в источнике строки имя файла — «{words}»")
        if not re.search(r"[а-яё]{4,}", words):
            bad.append(f"{b['ticker']}: источник строки — не название документа словами")
        if len(words) > PEER_SRC_LIMIT:
            bad.append(f"{b['ticker']}: источник строки длиннее {PEER_SRC_LIMIT} знаков ({len(words)})")
    assert not bad, "\n".join(bad)


def test_printed_strings_carry_no_latin_work_words():
    """Подписи — по-русски: латиница допустима только в устоявшихся названиях и обозначениях."""
    allowed = re.compile(r"ROE|T\+1|[CP]/[IEB]|CoR|XLSX|Databook|млн|IFRS|SVCB")
    known = {("calendar.ifrs-2026Q3.note", "Invest"), ("dividends.broker_check", "Invest"), ("dividends.dates_rule", "record")}
    bad = []
    for where, text in printed():
        if where.startswith(("guidance.", "peers.")) or ".decided_by" in where:
            continue                                  # дословные формулировки документов и названия нормативов
        rest = allowed.sub("", text)
        m = re.search(r"[A-Za-z]{4,}", rest)
        if m and (where, m.group(0)) not in known:
            bad.append(f"{where}: «{m.group(0)}»")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("text, rule", [
    ("(2026, 6, MONTH) → 0.146", "кортеж ответа источника"),
    ("оценка [В] по листу", "метка класса допущения"),
    ("см. отчёт, sha256 5b3a3de88ae6c96b", "хвост sha256"),
    ("ждёт решения ведущего", "рабочая пометка"),
    ("решение 30.06 и реестр через две недели", "короткая дата без года"),
    ("за 2026Q3 и далее", "код периода"),
    ("релиз за 2026M09", "код периода"),
    ("срок 2026-12-05", "дата ISO"),
    ("узел dividends_payable пуст", "имя поля"),
    ("флаг estimated: true", "true/false"),
    ("лист stage1/market", "путь к листу или файлу"),
    ("файл dividends_public.csv", "путь к листу или файлу"),
    ("допуск 1e-6", "e-нотация"),
    ("ставка 14.6 %", "десятичная точка в проценте"),
    ("по KEYS раздел 2", "ссылка на раздел договора или решения"),
])
def test_rules_catch_service_text(text, rule):
    got = breaches(text)
    assert any(b.startswith(rule) for b in got), f"правило «{rule}» не сработало на «{text}»: {got}"


@pytest.mark.parametrize("text", [
    "оценка по прошлым отчётам: 28.11.2024, 20.11.2025",
    "Дата реестра по дивидендам за полугодие 2026 года: 4,70 ₽ на акцию",
    "надбавка 250 % к коэффициентам риска; купон 11,26 %",
    "решение собрания 01.10.2026; выплата — до 26.10.2026",
    "граница строгая: более 17,88 ₽ на акцию за 2026 год при 14,90 ₽ за 2025 год",
])
def test_rules_pass_plain_words(text):
    assert not breaches(text), breaches(text)
