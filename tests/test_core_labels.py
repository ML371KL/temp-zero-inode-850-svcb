"""Литералы эмитента живут в книге (М§0.6): имя схемы выпуска, подписи нормативов, строк моста норматива,
узлов гайденса, целей нау-каста, флагов, источника якоря капитала, книг ЧПД, тексты о решении о дивиденде.

Приём проверки — книга-метка: каждая подпись фикстуры заменена меткой со своим ключом (поля подстановки
сохранены). Всё, что ядро печатает на такой книге, обязано нести метки и не нести ни одной прежней подписи:
вторая копия слов в коде осталась бы в выпуске прежним текстом. Перечень ключей `meta.labels` разбит без
остатка: ключ либо найден в напечатанном, либо назван среди тех, что читает другой слой или следующая волна.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import date, timedelta
from string import Formatter

import pytest

from model import book_results as BR
from model import payload as P
from model.book import book_from_dict, lower_first, record_fields, record_label
from model.book_schema import BookError
from model.checks import check_gates, check_invariants
from model.grid import DividendRecord, LiveInputs, live_from_book, run_grid
from model.live import apply_live, register_gaps
from model.nextreport import benchmarks
from model.reverse import bank_title
from tests.support_core import book_with, fixture_dict, fixture_facts
from tests.support_core2 import CONTROL_FIXTURE, book_prices, explained, outputs

pytestmark = pytest.mark.tact

SCHEMA = "marked-v7"


def _fields(text: str) -> list[str]:
    return [name for _, name, _, _ in Formatter().parse(text) if name]


def _leaves(node, path=""):
    for k, v in node.items():
        p = f"{path}.{k}" if path else k
        if isinstance(v, dict):
            yield from _leaves(v, p)
        else:
            yield p, v


def mark(key: str) -> str:
    return f"‹{key}›"


def marked_dict() -> dict:
    """Книга фикстуры, в которой каждая подпись — метка своего ключа с теми же полями подстановки."""
    data = fixture_dict()
    labels = data["meta"]["labels"]
    for path, text in list(_leaves(labels)):
        if path.endswith(".basis"):                      # код базиса цели нау-каста — не подпись
            continue
        node = labels
        *head, last = path.split(".")
        for part in head:
            node = node[part]
        node[last] = mark(path) + "".join(f" {{{f}}}" for f in dict.fromkeys(_fields(text)))
    for b, spec in data["nii"]["books"].items():
        spec["name"] = f"Книга‹{b}›"
    for it in data["checks"]["guidance_items"]:
        it["title"] = mark(f"g.{it['key']}")
        if "words" in it:
            it["words"] = mark(f"w.{it['key']}")
    data["meta"]["schema"] = SCHEMA
    return data


ORIGINAL = {path: text for path, text in _leaves(fixture_dict()["meta"]["labels"]) if not path.endswith(".basis")}
# Подписи, которых в напечатанном на этой фикстуре нет: читает другой слой, либо подпись печатается только при
# своём условии в фактах (оно проверяется на фикстуре формы Т, `tests/test_core2_t_w1.py`).
READ_ELSEWHERE = {
    "capital.anchor_src_estimated": "печатается, когда норматив якоря несёт признак оценки",
    "basis.roe_issuer": "печатается при узлах операционной прибыли и капитала эмитента в фактах",
    "register.collector_alarm": "тревога сборщиков — слой индикаторов читает ключ книги сам",
    "nowcast.targets.ni_q.title_long": "журнал прогнозов — слой индикаторов",
    "nowcast.targets.nim_q.title_long": "журнал прогнозов — слой индикаторов",
    "nowcast.targets.cor_q.title_long": "журнал прогнозов — слой индикаторов",
    **{f"control.lines.{k}": "сводка контрольной модели читает книгу сама" for k in (
        "nii", "llp", "fvc", "fees", "opex", "misc", "pbt", "ni_sh", "ci", "div", "bv", "rwa", "n20", "n11")},
    # control.lines.noncore ядро печатает: словарь терминов выпуска `meta.terms.noncore` (PAYLOAD §2)
    **{f"control.books.{b}": "сводка контрольной модели читает книгу сама"
       for b in fixture_dict()["meta"]["labels"]["control"]["books"]},
}


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in _strings(v)]
    return []


@pytest.fixture(scope="module")
def printed() -> dict:
    """Всё, что ядро печатает на книге-метке: выпуск с реестром, проверки, флаги живых входов, эталоны отчёта,
    сводка результатов книги."""
    facts = fixture_facts()
    book = book_from_dict(marked_dict(), facts=facts)
    day = P.to_date(book.get("meta.valuation_date"))
    px = book_prices(book)
    tl_year = int(str(book.get("meta.anchor_period"))[:4])
    ex = day + timedelta(days=40)

    def row(year, dps, status, **kw):
        return {"year": year, "dps": dps, "status": status, "record_date": ex.isoformat(), "ex_date": ex.isoformat(),
                "last_buy_date": (ex - timedelta(days=1)).isoformat(), "pay_date": (ex + timedelta(days=15)).isoformat(),
                "decided_date": (ex - timedelta(days=15)).isoformat(), "sources": ["первый источник", "второй источник"],
                **kw}

    register = [row(tl_year - 1, 30.0, "declared"),
                {"year": tl_year, "dps": 31.0, "status": "recommended", "sources": ["новость"]},
                row(tl_year + 1, 32.0, "declared", sources=["один источник"])]           # не принята: один источник
    rec = DividendRecord(year=tl_year - 1, dps=30.0, status="declared", record_date=ex,
                         last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=15),
                         sources=("первый источник", "второй источник"))
    live = LiveInputs(valuation_date=day, prices=px, price_dates={t: day for t in px}, register=(rec,))
    run = run_grid(book, facts, live)
    gates = check_gates(run, today=day)
    out = outputs({t: [(day, px[t])] for t in px}, register=register)
    rel = P.make_release(live=True, fast=True, today=day, book=book, facts=facts, outputs=out,
                         explanations=explained(gates, today=day), notes=[], draws=4, control_model=CONTROL_FIXTURE)
    payload = P.build_payload(rel)
    late = date(tl_year + 1, 7, 15)                       # после конца квартала решения за год якоря, записи нет
    gaps = register_gaps(book, [], late)
    _, late_report = apply_live(book, facts, outputs({t: [(late, px[t])] for t in px}), today=late)
    alert = P.alerts(rel, {"live": {"degraded_flag": False}, "meta": {"bytes": 0},
                           "checks": {"flags": [{"name": "dividend_register", "raised": True, "detail": "пропуск"}]}})
    cal = copy.deepcopy(facts.files["calendar"])
    cal["events"].append({"id": "agm", "kind": "agm", "date": (day - timedelta(days=60)).isoformat(), "title": "собрание",
                          "covers": None, "confirmed": True, "precision": "day"})
    guid = copy.deepcopy(facts.files["guidance"])
    guid["items"]["roe"] = {**guid["items"]["roe"], "v": 0.95, "kind": "point", "tol": 0.001}
    facts2 = dataclasses.replace(facts, files={**facts.files, "calendar": cal, "guidance": guid})
    run2 = run_grid(book, facts2, live_from_book(book, facts2))
    res = json.loads(json.dumps(BR.book_results(book, facts, slow=False), default=BR._default))
    return {
        "book": book, "payload": payload, "release": rel,
        "текст": "\n".join(
            _strings(payload) + [f.message for f in check_invariants(run)] + [f.message for f in gates]
            + [f.message for f in check_gates(run2, today=day)] + [f.message for f in rel.extra_findings]
            + list(rel.live_report.alarms) + list(rel.live_report.degraded) + gaps + alert
            + _strings(late_report.flags) + _strings(benchmarks(book, facts, str(book.get("valuation.next_report.period"))))
            + [BR.render_run_output(res, book)]),
    }


def test_every_label_is_printed_from_the_book_or_named_as_read_elsewhere(printed):
    """Каждый ключ `meta.labels` найден меткой в напечатанном ядром — или назван среди читаемых другим слоем."""
    text = printed["текст"]
    keys = [k for k in ORIGINAL if not k.startswith("periods.")]              # слова периода — отдельный тест ниже
    missing = [k for k in keys if k not in READ_ELSEWHERE and mark(k) not in text]
    assert not missing, f"подпись книги не дошла до печати ядра: {missing}"
    stale = [k for k in READ_ELSEWHERE if k not in ORIGINAL or mark(k) in text]
    assert not stale, f"ключ назван «читается не ядром», а ядро его печатает (или ключа нет): {stale}"


def test_no_former_label_survives_in_the_code(printed):
    """Ни одна прежняя подпись фикстуры не печатается на книге-метке: второго экземпляра слов в коде нет.
    Короткие слова («ROE», «ЧПМ») встречаются и в текстах кода — проверяются куски подписей длиннее двенадцати
    знаков; подписи, которые ядро не печатает (`READ_ELSEWHERE`), сюда не входят: их слова — общие термины."""
    text = printed["текст"]
    left = []
    for key, label in ORIGINAL.items():
        if key in READ_ELSEWHERE:
            continue
        for literal, _, _, _ in Formatter().parse(label):     # куски подписи между полями подстановки
            piece = literal.strip(" :;—(),.")
            if len(piece) > 12 and piece in text:
                left.append(f"{key}: «{piece}»")
    assert not left, f"прежние подписи напечатаны при книге-метке — литерал остался в коде: {left}"


def test_release_nodes_carry_the_labels_of_the_book(printed):
    d, book = printed["payload"], printed["book"]
    cap = d["capital"]
    assert cap["titles"] == {k: mark(f"capital.{k}") for k in ("n20", "n11", "n11_observed", "n1_0", "n1_2")}
    assert cap["anchor"]["src"] == f"{mark('capital.anchor_src')} {P._ru_date(P.to_date(book.get('meta.facts_date')))}"
    assert cap["observed"]["source"] == mark("capital.observed_source")
    assert {r["title"] for r in cap["bridge"]["rows"]} == {
        mark(f"capital_bridge.{k}") for k in ("dividend_accrual", "profit", "oci_other", "rwa_growth", "deductions", "other")}
    ladder = d["dividends"]["ladder"]
    assert ladder[0]["condition"].startswith(mark("dividends.ladder_condition")) and "%" in ladder[0]["condition"]
    assert (ladder[-1]["title"], ladder[-1]["condition"]) == (mark("dividends.ladder_residual_title"),
                                                              mark("dividends.ladder_residual_condition"))
    subject = d["market"]["peers"]["rows"][0]
    assert (subject["capital_ratio"]["name"], subject["basis"]) == (mark("capital.n20_short"), mark("peers.subject_basis"))
    targets = {t["key"]: t for t in d["nowcast"]["targets"]}
    labels = book.get("meta.labels.nowcast.targets")
    assert {k: (t["title"], t["basis"], t["unit"]) for k, t in targets.items()} == {
        "ni_q": (mark("nowcast.targets.ni_q.title"), labels["ni_q"]["basis"], "bn"),
        "nim_q": (mark("nowcast.targets.nim_q.title"), labels["nim_q"]["basis"], "share"),
        "cor_q": (mark("nowcast.targets.cor_q.title"), labels["cor_q"]["basis"], "share")}
    flags = {f["name"]: f for f in d["checks"]["flags"]}
    assert list(flags) == list(P.FLAG_TITLES)
    assert flags["dividend_register"]["title"] == mark("register.flag_title")
    assert flags["ras_mismatch"]["title"] == mark("flags.ras_mismatch")
    assert flags["book_update"]["title"] == P.FLAG_TITLES["book_update"]
    assert flags["dividend_recommended"]["raised"] and mark("register.recommended_item") in flags["dividend_recommended"]["detail"]
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    lt = mark("terms.lt_level")
    assert gates["nim_path_joint"]["title"] == P.GATE_TITLES["nim_path_joint"].format(lt_level=lt)
    assert lt in gates["nim_path_joint"]["corridor"]["text"]
    assert gates["guidance_gap"]["corridor"]["text"] == mark("corridors.guidance_gap")
    assert mark("capital.n20_short") in gates["m_crisis_vs_cbr"]["corridor"]["text"]
    assert gates["capital_gap"]["corridor"]["text"] == (
        f"пол {mark('capital.n20_short')} и {mark('capital.n11_short')} сценария после дивидендов")
    assert [b["title"] for b in d["nii"]["books"]] == [f"Книга‹{b}›" for b in book.get("nii.books")]
    floor = gates["lt_spread_floor"]                         # на фикстуре гейт срабатывает: книга — со строчной
    assert floor["fired"] and "книга‹" in floor["message"] and "Книга‹" not in floor["message"]
    items = book.get("checks.guidance_items")
    assert [(i["key"], i["title"], i["basis"]) for i in d["guidance"]["items"]] == [
        (it["key"], mark(f"g.{it['key']}"), "sector" if it["key"].startswith("loan_growth") else it["basis"])
        for it in items]
    assert [r["title"] for r in d["reverse_dcf"]["bank_rows"]][0] == bank_title(book, "implied_roe_through_cycle")
    assert lt in d["reverse_dcf"]["bank_rows"][0]["title"]
    pay = [e for e in d["calendar"]["events"] if e.get("kind") == "pay"]
    assert pay and all(e["title"].startswith(mark("dividends.pay_event")) for e in pay)


def test_guidance_gate_reads_the_list_of_the_book(printed):
    """Гейт гайденса сравнивает узлы перечня книги с `gate: true` и называет их словами пункта; узел без
    `gate` в гейт не входит; узла фактов нет — «гайденс не прочитан», а не отказ."""
    book, facts = printed["book"], fixture_facts()
    run = run_grid(book, facts, live_from_book(book, facts))
    quiet = next(f for f in check_gates(run) if f.name == "guidance_gap")
    guid = copy.deepcopy(facts.files["guidance"])
    guid["items"]["roe"] = {**guid["items"]["roe"], "v": 0.95, "kind": "point", "tol": 0.001}
    facts2 = dataclasses.replace(facts, files={**facts.files, "guidance": guid})
    fired = next(f for f in check_gates(run_grid(book, facts2, live_from_book(book, facts2))) if f.name == "guidance_gap")
    assert fired.fired and mark("w.roe") in fired.message and "roe" in fired.detail["outside"]
    assert set(fired.detail["bands"]) <= {it["key"] for it in book.get("checks.guidance_items") if it["gate"]}
    items = [dict(it, gate=False) if it["key"] == "roe" else it for it in book.get("checks.guidance_items")]
    off = book.with_overrides({"checks.guidance_items": items})
    calm = next(f for f in check_gates(run_grid(off, facts2, live_from_book(off, facts2))) if f.name == "guidance_gap")
    assert "roe" not in calm.detail["bands"] and mark("w.roe") not in calm.message
    assert calm.fired == quiet.fired                                             # без узла ROE — как на фактах фикстуры
    moved = [dict(it, path="items.no_such_node") if it["key"] == "nim" else it for it in book.get("checks.guidance_items")]
    lost = book.with_overrides({"checks.guidance_items": moved})
    unread = next(f for f in check_gates(run_grid(lost, facts, live_from_book(lost, facts))) if f.name == "guidance_gap")
    assert not unread.fired and unread.message.startswith("гайденс не прочитан")


def test_schema_name_is_a_key_of_the_book(printed):
    """Имя схемы выпуска — `meta.schema`: поле выпуска, контракт, приём прошлого выпуска, инвариант контракта."""
    d, rel, book = printed["payload"], printed["release"], printed["book"]
    assert d["schema"] == SCHEMA == P.schema_name(book)
    assert P.validate(d, schema=SCHEMA) == []
    other = P.validate(d, schema="other-v1")
    assert len(other) == 1 and "schema" in other[0] and "other-v1" in other[0]
    assert not hasattr(P, "SCHEMA")
    wrong = copy.deepcopy(d)
    wrong["schema"] = "other-v1"
    assert any("schema" in p for p in P._contract_problems(wrong, P.schema_name(book)))
    assert {i["name"]: i["ok"] for i in d["checks"]["invariants"]}["payload_contract"]


def test_previous_release_of_another_schema_is_not_previous(tmp_path):
    for name, kept in ((SCHEMA, True), ("other-v1", False)):
        (tmp_path / "latest.json").write_text(json.dumps({"schema": name, "meta": {}}), encoding="utf-8")
        (tmp_path / "history.json").write_text("[]", encoding="utf-8")
        prev, hist = P.read_data_repo(tmp_path, schema=SCHEMA)
        assert (prev is not None) is kept and hist == []


def test_record_label_follows_the_rule_of_the_book():
    """Поле `{label}`: слова решения записи; нет их — подпись периода по номеру квартала с годом периода; нет и
    периода — подпись года прибыли (М§0.6)."""
    book = book_from_dict(fixture_dict(), facts=fixture_facts())
    periods = book.get("meta.labels.periods")
    assert record_label(book, 2026, "2026Q2", "за полугодие двадцать шестого") == "за полугодие двадцать шестого"
    for h in ("1", "2", "3", "4"):
        assert record_label(book, 2027, f"2026Q{h}") == periods[h].format(year=2026)
    assert record_label(book, 2025) == periods["4"].format(year=2025)
    assert record_fields(book, 2025) == {"year": 2025, "period": "", "label": periods["4"].format(year=2025)}
    assert record_fields(book, 2026, "2026Q1")["period"] == "2026Q1"
    assert book.label("register.gap_item", decision_quarter="2027Q2", end="2027-06-30", **record_fields(book, 2026)) \
        == fixture_dict()["meta"]["labels"]["register"]["gap_item"].format(
            year=2026, decision_quarter="2027Q2", end="2027-06-30")


def test_lower_first_keeps_the_rest_of_the_title():
    assert lower_first("Кредиты МСБ") == "кредиты МСБ" and lower_first("Ипотека") == "ипотека" and lower_first("") == ""


# ------------------------------------------------------------------ схема: описательные ключи обязательны


def _fails(data, *fragments):
    with pytest.raises(BookError) as exc:
        book_from_dict(data, facts=fixture_facts())
    for fr in fragments:
        assert fr in str(exc.value), str(exc.value)


@pytest.mark.parametrize("dotted", [
    "meta.schema", "meta.labels", "meta.labels.capital.n20", "meta.labels.capital.anchor_src_estimated",
    "meta.labels.capital_bridge.other", "meta.labels.dividends.pay_event", "meta.labels.register.collector_alarm",
    "meta.labels.flags.ras_mismatch", "meta.labels.nowcast.targets.cor_q.title_long",
    "meta.labels.nowcast.targets.ni_q.basis", "meta.labels.nextreport.guidance_note", "meta.labels.terms.lt_level",
    "meta.labels.terms.profit_short", "meta.labels.corridors.guidance_gap", "meta.labels.periods.3",
    "meta.labels.basis.divisor", "meta.labels.peers.subject_basis", "meta.labels.control.lines.n11",
    "meta.labels.control.books.mortgage_sub", "nii.books.wholesale.name", "checks.guidance_items"])
def test_descriptive_keys_are_required_and_have_no_default(dotted):
    _fails(book_with({}, drop=(dotted,)), dotted, "нет ключа")


def test_label_rules_of_the_schema():
    """Подпись — непустая строка; поле подстановки — только названное у ключа, без формата; набор подписей
    кредитных книг сводки — ровно кредитные книги; имя схемы — вида <слово>-v<номер>."""
    _fails(book_with({"meta.labels.capital.n20": ""}), "meta.labels.capital.n20", "подписи")
    _fails(book_with({"meta.labels.capital.n20": "Норматив {year}"}), "meta.labels.capital.n20", "незнакомое поле", "{year}")
    _fails(book_with({"meta.labels.register.gap_item": "дивидент {label} ({reason})"}), "register.gap_item", "{reason}")
    _fails(book_with({"meta.labels.dividends.ladder_condition": "не ниже {threshold:.1f}"}), "без формата")
    _fails(book_with({"meta.labels.capital.anchor_src": "на {date"}), "не разбирается")
    _fails(book_with({"meta.labels.control.books.securities": "бумаги"}), "control.books.securities", "незнакомый ключ")
    _fails(book_with({"meta.labels.nowcast.targets.ni_q.basis": "МСФО"}), "ni_q.basis")
    _fails(book_with({"nii.books.corp_loans.name": None}), "nii.books.corp_loans.name")
    for bad in ("Sber-v1", "sber_v1", "sber-v", "v1", "sber-v1.2", 7):
        _fails(book_with({"meta.schema": bad}), "meta.schema")
    book_from_dict(book_with({"meta.schema": "t-v12", "meta.labels.register.gap_item": "{label}: {period} {year}",
                              "meta.labels.dividends.pay_event": "Выплата {label}"}), facts=fixture_facts())


def test_guidance_items_rules_of_the_schema():
    items = fixture_dict()["checks"]["guidance_items"]
    by = {it["key"]: it for it in items}
    _fails(book_with({"checks.guidance_items": items + [dict(by["nim"])]}), "повтор ключа")
    _fails(book_with({"checks.guidance_items": [dict(by["roe"], key="roa")]}), "roa")
    _fails(book_with({"checks.guidance_items": [{k: v for k, v in by["roe"].items() if k != "words"}]}), "words")
    _fails(book_with({"checks.guidance_items": [dict(by["roe"], basis="МСФО")]}), "basis")
    _fails(book_with({"checks.guidance_items": [dict(by["roe"], path="roe")]}), "items.")
    _fails(book_with({"checks.guidance_items": [dict(by["n20_0"], gate=True, words="норматив")]}), "не сравнивается")
    book_from_dict(book_with({"checks.guidance_items": []}), facts=fixture_facts())           # пустой перечень допустим
