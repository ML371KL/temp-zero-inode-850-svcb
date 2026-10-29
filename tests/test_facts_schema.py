"""Факты Совкомбанка: схема узлов и происхождение каждого числа (data/facts/SCHEMA.md).

Каждое число — узел {v, src|calc}; null — с причиной; src ссылается на документ реестра (anchor.json → documents или
sources ручного файла) по префиксу sha256; базисы помечены; поля, которые читает ядро, на месте и не null; форма —
гибрид семейства (годовой календарь дивиденда, бессрочные в капитале, нормативы банка соло, отчётный базис прибыли);
нет следов частной машины в публичных файлах. Отступления фактов от правил семейства названы поимённо (KNOWN_*):
новое отступление — провал теста.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tact          # быстрые (≈1 с): схема и провенанс идут в такте сервера

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
CORE = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends", "bridge_mgmt_ifrs",
        "bridge_ras_ifrs", "mgmt_quarterly", "guidance")
SNAPSHOT_FILES = ("calendar", "peers")                 # срез на день листов этапа 1: as_of — день среза
CALIBRATION = ("credit_products", "perimeter", "misc_window")   # узлы калибровки книги (ядро не читает)
ALL = CORE + SNAPSHOT_FILES + CALIBRATION
BASES = {"IFRS", "RAS", "mgmt", "mgmt↔IFRS", "RAS→IFRS", "mixed"}
LOANS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans")
ASSET_BOOKS = LOANS + ("securities", "liquidity")
LIAB_BOOKS = ("retail_current", "retail_term", "corp_term", "corp_current", "wholesale", "insurance_liab")
BOOKS = ASSET_BOOKS + LIAB_BOOKS
SHA_RE = re.compile(r"sha256 ([0-9a-f]{16})")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Голые числа вне узлов: поля семейства и таблицы Совкомбанка, где число стоит в строке с источником строки.
BARE_NUMBER_KEYS = {"year", "split_factor", "dividends_payable_year"}
NODE_NUMBER_KEYS = {"tol", "se"}                       # числовые поля внутри узла: допуск, стандартная ошибка оценки
BARE_PATHS = {
    "capital": [r"^history_monthly\.\d+\.(n1_0|n1_1|n1_2|own_funds|base|additional|t2)$"],   # строки месячных форм (src строки)
    "perimeter": [r"^rows\.\d+\.(low|high)$", r"^aux\..+$"],   # концы связки при центре-узле; справочные числа листа круга
    "credit_products": [r"^m7_readings\.\w+\.readings\.\w+$"],  # прочтения окон М7 (узлы — min, max, mid)
}
# Отступления фактов от правила «src — документ реестра» (источник — лист этапа 1, ответ ISS или факты другой панели).
KNOWN_SRC_WITHOUT_SHA = {
    "nii_books": [r"^key_avg_anchor_q\.src$"],
    "credit_products": [r"^quarters\.\d{4}Q\d\.(gross_end|charge)\.\w+\.src$", r"^(years_ifrs|windows_ifrs)\.[^.]+\.src$"],
    "perimeter": [r"\.src$"],
    "peers": [r"^banks\.\d+\.src$"],
}
KNOWN_SHA_OUTSIDE_REGISTRY = {"capital": {"90b297f62e10f888"}}   # ответ MOEX ISS zcyc (кривая ОФЗ) — не документ реестра
# Узлы калибровки стоимости риска по книгам: источник — у строки (резерв, валовые, лист Б7), у производных долей и
# уровней — только число.
KNOWN_BARE_NODES = {"credit_products": [r"\.cor_books\.\w+$", r"\.rel\.\w+$", r"^(years_ifrs|windows_ifrs)\.[^.]+\.(total|on_anchor|intensity)$",
                                        r"^intensity\.\w+\.(low|high)$", r"^m7_readings\.\w+\.(min|max|mid)$"]}
# Числа отчётности, у которых в источнике документ без страницы: строки «расчёт» листа книг (резерв денег, депозиты
# в ЦБ — оценка листа), выгодное приобретение 2023 года (страница в листе пуста), события акций (место — в записке).
KNOWN_SRC_WITHOUT_PLACE = [r"^balance\.books\.liquidity$", r"^pnl_quarterly\.quarters\.2023Q4\.noncore_parts\.",
                           r"^shares\.corporate_actions\.\d+\."]


def load(name: str) -> dict:
    return json.loads((FACTS / f"{name}.json").read_text(encoding="utf-8"))


def is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def has_text(x) -> bool:
    return isinstance(x, str) and any(ch.isalnum() for ch in x)


def walk(obj, path=""):
    """(путь, значение, ключ) для всех значений дерева."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, v, k
            yield from walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}.{i}"
            yield p, v, None
            yield from walk(v, p)


def nodes(obj):
    for p, v, _ in walk(obj):
        if isinstance(v, dict) and "v" in v:
            yield p, v


def get(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def anchor_period() -> str:
    return load("anchor")["period"]


def year_quarters(period: str) -> list[str]:
    return [f"{period[:4]}Q{k}" for k in range(1, int(period[-1]) + 1)]


@pytest.mark.parametrize("name", ALL)
def test_file_present_and_parses(name):
    path = FACTS / f"{name}.json"
    assert path.exists(), f"нет {path.name}"
    raw = path.read_bytes()
    assert b"\r\n" not in raw, f"{name}.json: переводы строк CRLF"
    data = json.loads(raw.decode("utf-8"))
    assert DATE_RE.match(str(data.get("as_of", ""))), f"{name}.json: нет as_of YYYY-MM-DD"


def test_the_facts_are_of_one_issuer_and_one_anchor():
    """Файлы ядра и узлы калибровки — на одном якоре; срезы — на день листов; эмитент — один тикер; книги ЧПД — 13."""
    a = load("anchor")
    assert re.fullmatch(r"\d{4}Q[1-4]", a["period"])
    for name in CORE:
        if name != "guidance":                         # у гайденса as_of — день среза
            assert load(name)["as_of"] == a["as_of"], f"{name}.json: as_of не на якоре"
    for name in CALIBRATION:                           # узел калибровки — на якоре своего круга (перенос — как есть)
        assert load(name)["as_of"] <= a["as_of"], f"{name}.json: as_of позже якоря"
    snap = {load(n)["as_of"] for n in SNAPSHOT_FILES + ("guidance",)}
    assert len(snap) == 1 and snap.pop() > a["as_of"], "срезы календаря, аналогов и гайденса — один день после якоря"
    assert list(load("shares")["by_ticker"]) == [load("peers")["subject_ticker"]] == ["SVCB"]
    assert tuple(load("balance")["books"]) == BOOKS == tuple(load("nii_books")["books"])
    extra = sorted(p.name for p in FACTS.iterdir() if p.name not in {f"{n}.json" for n in ALL} | {"SCHEMA.md"})
    assert not extra, f"в каталоге фактов лишнее: {extra}"


@pytest.mark.parametrize("name", CORE + ("peers", "perimeter", "misc_window"))
def test_basis_declared(name):
    data = load(name)
    assert data.get("basis"), f"{name}.json: нет basis"
    if name == "peers":
        for b in data["banks"]:
            assert has_text(b.get("basis")), f"peers {b.get('ticker')}: нет basis"
        return
    assert data["basis"] in BASES, f"{name}.json: basis {data['basis']!r} вне {sorted(BASES)}"


KNOWN_MIXED_WITHOUT_BASIS = {"at1", "instruments", "instruments_total", "history_monthly", "core_form_check", "guarantees"}


def test_mixed_capital_marks_the_basis_of_each_block():
    """Смешанный файл капитала: у каждого блока верхнего уровня свой basis (нормативы банка — RAS, Базель группы,
    бессрочные — IFRS, кривая — market); строки истории — basis строки. Без basis — справочные блоки, названные
    поимённо (бессрочные и инструменты — МСФО по смыслу, месячные формы — RAS по источнику строки)."""
    cap = load("capital")
    assert cap["basis"] == "mixed"
    bad = [k for k, v in cap.items() if isinstance(v, dict) and k not in KNOWN_MIXED_WITHOUT_BASIS and not has_text(v.get("basis"))]
    assert not bad, f"capital: блоки без basis: {bad}"
    assert all(has_text(r.get("basis")) for r in cap["history"])
    assert all(r["n1_0"]["src"] and "0409135" in r["n1_0"]["src"] for r in cap["history"])


@pytest.mark.parametrize("name", ALL)
def test_every_number_is_a_node_with_provenance(name):
    data = load(name)
    bad = []
    bare_nodes = [re.compile(x) for x in KNOWN_BARE_NODES.get(name, [])]
    for p, v in nodes(data):
        val = v["v"]
        if val is None:
            if not has_text(v.get("calc")):
                bad.append(f"{p}: null без причины в calc")
            continue
        if not is_num(val):
            bad.append(f"{p}: v не число ({val!r})")
        if not (has_text(v.get("src")) or has_text(v.get("calc"))) and not any(rx.search(p) for rx in bare_nodes):
            bad.append(f"{p}: число без src и calc")
    allowed = [re.compile(x) for x in BARE_PATHS.get(name, [])]
    for p, v, key in walk(data):
        if not is_num(v):
            continue
        last = p.rsplit(".", 1)
        if last[-1] == "v" or key in BARE_NUMBER_KEYS or any(rx.search(p) for rx in allowed):
            continue
        if key in NODE_NUMBER_KEYS:
            owner = get(data, last[0])
            if not (isinstance(owner, dict) and "v" in owner):
                bad.append(f"{p}: поле {key} вне узла")
            continue
        if re.search(r"\.range\.[01]$", p):            # диапазон оценки — только у узла с estimated: true
            owner = get(data, p.rsplit(".", 2)[0])
            if not (isinstance(owner, dict) and owner.get("estimated") is True):
                bad.append(f"{p}: диапазон у узла без оценки")
            continue
        bad.append(f"{p}: голое число {v} вне узла")
    assert not bad, "\n".join(bad[:30])


@pytest.mark.parametrize("name", ALL)
def test_nulls_carry_a_reason_and_are_not_zeros(name):
    """Нераскрытое — null с причиной словами; причина не подменяет источник и не пуста."""
    bad = [p for p, v in nodes(load(name)) if v["v"] is None and (len(str(v.get("calc") or "")) < 12 or v.get("src"))]
    assert not bad, f"{name}: null без содержательной причины или с источником: {bad[:10]}"


def registry(name: str) -> dict[str, dict]:
    docs = load(name)["sources"] if name in SNAPSHOT_FILES else load("anchor")["documents"]
    return {d["sha256"][:16]: d for d in docs}


@pytest.mark.parametrize("name", ALL)
def test_src_resolves_to_registry(name):
    data = load(name)
    reg = registry(name)
    no_sha = [re.compile(x) for x in KNOWN_SRC_WITHOUT_SHA.get(name, [])]
    outside = KNOWN_SHA_OUTSIDE_REGISTRY.get(name, set())
    if name == "peers":                                # строки аналогов — копии чужих панелей: их реестры — там
        outside = {s for b in data["banks"] for s in SHA_RE.findall(json.dumps(b, ensure_ascii=False))}
    bad = []
    for p, v, key in walk(data):
        if key == "src" and isinstance(v, str):
            shas = SHA_RE.findall(v)
            if not shas and not any(rx.search(p) for rx in no_sha):
                bad.append(f"{p}: в src нет sha256 документа")
            bad += [f"{p}: sha256 {s} нет в реестре" for s in shas if s not in reg and s not in outside]
    assert not bad, "\n".join(bad[:30])


def test_registry_cites_almost_every_document():
    """Реестр якоря — лист документов этапа 1: процитированы все, кроме листов исследования, по которым собраны листы."""
    cited = set()
    for name in ALL:
        cited |= set(SHA_RE.findall(json.dumps(load(name), ensure_ascii=False)))
    cited |= {d["sha256"][:16] for n in SNAPSHOT_FILES for d in load(n)["sources"] if d["sha256"]}
    cited.add(load("dividends")["policy"]["sha256"][:16])
    unused = sorted(d["key"] for s, d in registry("anchor").items() if s not in cited)
    assert all(k.startswith("research_") for k in unused), f"документы реестра без ссылок: {unused}"
    assert len(unused) <= 4, unused


def test_src_names_a_page_or_a_cell():
    """Источник числа отчётности — у каждого документа отчётности (PDF, XLSX) названа страница, ячейка или
    примечание; файлы листов и форм — целиком (место — сам файл)."""
    doc = re.compile(r"([\w.\-]+\.(?:pdf|xlsx))(, [^;]*?)?, sha256 [0-9a-f]{16}")
    place = re.compile(r", (?:с\. \d|[A-Za-z_ ]+![A-Z]+\d+|прим\. |примечани|форма \d{7})")
    known = [re.compile(x) for x in KNOWN_SRC_WITHOUT_PLACE]
    bad, seen = [], 0
    for name in ("balance", "nii_books", "pnl_quarterly", "mgmt_quarterly", "capital", "shares", "dividends"):
        for p, v in nodes(load(name)):
            for m in doc.finditer(v.get("src") or ""):
                seen += 1
                if not place.search(m.group(2) or "") and not any(rx.search(f"{name}.{p}") for rx in known):
                    bad.append(f"{name}.{p}: {m.group(0)}")
    assert not bad, "\n".join(bad[:20])
    assert seen > 500


def test_quarter_differences_state_the_formula():
    """Квартал 2–4 — разность нарастающих итогов: строка прибыли несёт формулу с числами (млн ₽), и разность даёт
    значение узла; строки движка (слоты из нескольких строк) называют способ словами."""
    words = "разность нарастающих итогов"
    rx = re.compile(words + r" \S+ − \S+: (\(?−?-?[\d.]+\)?) − (\(?−?-?[\d.]+\)?)")
    checked, bad = 0, []
    for period, row in load("pnl_quarterly")["quarters"].items():
        if period.endswith("Q1"):
            continue
        for slot in ("pbt", "tax", "ni", "ni_shareholders", "ni_nci"):
            m = rx.search(row[slot]["calc"])
            if not m:
                bad.append(f"{period}.{slot}: нет формулы разности")
                continue
            a, b = (float(x.strip("()").replace("−", "-")) for x in m.groups())
            checked += 1
            if abs((a - b) / 1000 - row[slot]["v"]) > 5e-7:
                bad.append(f"{period}.{slot}: {a} − {b} не даёт {row[slot]['v']}")
        for slot in ("nii", "fees_net", "opex"):
            if words not in row[slot]["calc"]:
                bad.append(f"{period}.{slot}: способ квартала не назван")
    assert not bad, "\n".join(bad[:20])
    assert checked >= 40


@pytest.mark.parametrize("name", ("anchor", "calendar", "peers"))
def test_registry_entries(name):
    data = load(name)
    docs = data["documents"] if name == "anchor" else data["sources"]
    assert docs
    keys, shas = set(), set()
    for d in docs:
        assert re.fullmatch(r"[0-9a-f]{64}", d["sha256"]) or (name == "peers" and d["sha256"] == ""), d
        assert has_text(d.get("title")), f"{d['key']}: нет заголовка"
        assert d["key"] not in keys, f"повтор ключа {d['key']}"
        keys.add(d["key"])
        if d["sha256"]:
            assert d["sha256"][:16] not in shas, f"коллизия префикса sha256 {d['sha256'][:16]}"
            shas.add(d["sha256"][:16])
        f = d.get("file")
        if f is not None:
            assert not re.match(r"^([A-Za-z]:|/|\\)", f), f"{d['key']}: абсолютный путь"
            assert ".." not in f.split("/"), f"{d['key']}: путь с .."


@pytest.mark.docs                       # читает и data/facts/SCHEMA.md (коммит из одних *.md — docs.yml)
def test_no_private_traces():
    pats = {
        "абсолютный путь": re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\\Users\\"),
        "почта": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
        "IPv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "токен": re.compile(r"(?i)(bearer\s+[a-z0-9._-]{10,}|token\s*[:=]\s*\S{10,}|t\.[A-Za-z0-9_-]{40,})"),
    }
    bad = []
    for path in sorted(FACTS.glob("*")):
        if path.suffix not in (".json", ".md"):
            continue
        text = path.read_text(encoding="utf-8")
        for what, rx in pats.items():
            m = rx.search(text)
            if m:
                bad.append(f"{path.name}: {what}: {m.group(0)[:40]}")
    assert not bad, "\n".join(bad)


# Поля, которые ядро требует числом (model/book.py:anchor_facts, credit.py, dividends.py, payload.py): узел с числом.
CORE_NUMBERS = {
    "balance": [f"books.{b}" for b in BOOKS] + [
        "securities.fvoci_debt", "securities.fvoci_repo", "securities.fvtpl_bonds", "allowance_ac", "other_assets",
        "other_assets_fixed", "other_liabilities", "dividends_payable", "equity.bv_common", "equity.at1", "equity.nci",
        "equity.total", "prev_year_end.loans_corporate", "prev_year_end.loans_retail", "total_assets", "total_liabilities", "iea"]
    + [f"allowance_books.{b}" for b in LOANS],
    "nii_books": ["dia_q", "nii_q", "nim_eng_q", "current_share_anchor", "key_avg_anchor_q", "other_interest_net_q"]
    + [f"books.{b}.{f}" for b in BOOKS for f in ("balance_open", "balance_close", "balance_avg", "interest_q", "rate_anchor")],
    "capital": ["at1.amount", "at1.coupon_annual", "at1.coupon_quarter", "t2_recognized", "basel.cet1", "basel.rwa",
                "n20_0.value", "n1_1_bank.value", "n20_2", "n1_0_bank", "n1_2_bank", "fvoci_reserve", "bank_base_capital",
                "ofz_curve_anchor.1", "ofz_curve_anchor.3", "ofz_curve_anchor.5", "ofz_curve_anchor.10",
                "guarantees.nonfinancial", "guarantees.financial"],
    "shares": ["issued_total", "issued_ordinary", "treasury_ordinary", "outstanding_total", "outstanding_ordinary",
               "economic_treasury", "depositary_block", "dividend_eligible"],
    "bridge_mgmt_ifrs": ["cor.value", "nim.value", "cir.value", "cor.sd", "nim.sd", "cir.sd", "cor.n", "nim.n", "cir.n",
                         "nim.value_iea"],
    "bridge_ras_ifrs": ["nii.value"],
    "dividends": ["policy.cap", "policy.payout_low", "policy.payout_high", "policy.threshold"],
}
CORE_PLAIN = {
    "anchor": ["as_of", "period", "first_period", "last_period", "documents"],
    "balance": ["dividends_payable_year", "dividends_payable_declared", "prev_year_end.as_of", "history"],
    "capital": ["n20_0.as_of", "n20_0.pre_dividend", "n20_0.estimated", "n1_1_bank.as_of", "n1_1_bank.estimated", "history",
                "instruments"],
    "bridge_mgmt_ifrs": ["window", "cor.method", "nim.method", "cir.method"],
    "bridge_ras_ifrs": ["nii.window", "nii.method", "iea.codes", "cor", "by_quarter"],
    "guidance": ["year", "as_of", "history", "items"],
    "dividends": ["policy.valid_until", "policy.frequency", "history", "history_before", "years", "register_seed"],
    "shares": ["corporate_actions", "by_ticker"],
}


@pytest.mark.parametrize("name", sorted(set(CORE_NUMBERS) | set(CORE_PLAIN)))
def test_core_fields_present(name):
    data = load(name)
    bad = []
    for path in CORE_NUMBERS.get(name, []):
        try:
            n = get(data, path)
        except (KeyError, IndexError, TypeError):
            bad.append(f"{name}.{path}: нет")
            continue
        if not (isinstance(n, dict) and "v" in n) or n["v"] is None:
            bad.append(f"{name}.{path}: не узел с числом")
    for path in CORE_PLAIN.get(name, []):
        try:
            get(data, path)
        except (KeyError, IndexError, TypeError):
            bad.append(f"{name}.{path}: нет поля")
    assert not bad, "\n".join(bad)


def test_hybrid_form_of_the_issuer():
    """Форма фактов Совкомбанка — гибрид семейства: годовой календарь дивиденда и бессрочные в капитале (Сбер),
    прямые книги и отчёт квартала (Т), нормативы банка соло (слот n1_1_bank несёт Н1.2), отчётный базис прибыли."""
    bal, cap, d, p = load("balance"), load("capital"), load("dividends"), load("pnl_quarterly")
    assert isinstance(bal["dividends_payable_year"], int) and bal["equity"]["at1"]["v"] > 0
    assert cap["n1_1_bank"]["slot_metric"] == "Н1.2" and cap["n1_1_bank"]["value"]["v"] == cap["n1_2_bank"]["v"]
    assert cap["n20_0"]["value"]["v"] == cap["n1_0_bank"]["v"] and cap["n1_1_bank_h11"]["v"] < cap["n1_2_bank"]["v"]
    assert all(g["v"] is None for g in cap["group_capital"].values() if isinstance(g, dict))
    assert d["policy"]["frequency"] == "annual" and d["history_before"]
    for h in d["history"]:
        assert {"ni_shareholders", "at1_coupon", "tax_statutory", "dps_ordinary"} <= set(h), h["period"]
        assert h["period"].endswith("Q4") and h["split_factor"] == 1, h["period"]
    assert p["profit_basis"] == "reported" and not any("investment_block" in r for r in p["quarters"].values())
    for k, n in load("guidance")["items"].items():
        assert n["v"] is None and has_text(n["calc"]), k


def test_pnl_quarters_cover_anchor_year_and_four_before():
    """Ядро читает строки ОПУ года якоря и кварталов до первого прогнозного; ряд — с 2023К1 (окно калибровки) без
    пропусков; купон бессрочных — числом с 2024К1 (2023 год поквартально не раскрыт — null с причиной)."""
    q = load("pnl_quarterly")["quarters"]
    anchor = anchor_period()
    y, k = int(anchor[:4]), int(anchor[-1])
    need = []
    for _ in range(max(4, k) + 4):
        need.append(f"{y}Q{k}")
        y, k = (y - 1, 4) if k == 1 else (y, k - 1)
    fields = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni",
              "ni_shareholders", "misc_net", "ni_nci", "dia", "at1_coupon", "key_avg")
    bad = [f"{p}.{f}" for p in need for f in fields if p not in q or q[p][f]["v"] is None]
    assert not bad, "нет чисел ОПУ: " + ", ".join(bad)
    assert list(q) == sorted(q) and min(q) == "2023Q1" and max(q) == anchor
    assert all(q[p]["at1_coupon"]["v"] is None for p in q if p < "2024Q1")


def test_pnl_reported_rows_are_the_engine_rows():
    p = load("pnl_quarterly")
    assert p["basis"] == "IFRS"
    for per, row in p["quarters"].items():
        assert set(row["reported"]) == {"pbt", "tax", "ni", "ni_shareholders", "ni_nci"}, per
        assert all(row["reported"][k]["v"] == row[k]["v"] for k in row["reported"]), per


def test_balance_history_covers_the_quarter_ends_with_books():
    """Якорь и концы кварталов до него — числами; остатки книг ЧПД — на концах до якоря (все 13 книг с 2024К4,
    четыре книги средств клиентов — на концах 2024К1–К3)."""
    h = load("balance")["history"]
    p, need = anchor_period(), []
    for _ in range(5):
        need.append(p)
        y, k = int(p[:4]), int(p[-1])
        p = f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"
    for per in need:
        assert per in h, f"нет конца квартала {per}"
        for f in ("bv_common", "loans", "loans_ac_gross", "funds", "iea", "total_assets", "insurance_liab"):
            assert h[per][f]["v"] is not None, f"{per}.{f}"
        assert DATE_RE.match(h[per]["date"])
    for per, row in h.items():
        if "books" in row:
            assert per < anchor_period() and set(row["books"]) in (set(BOOKS), {"retail_current", "retail_term",
                                                                                "corp_term", "corp_current"}), per
    assert all("books" in h[per] for per in need[1:]), "остатки книг на концах кварталов до якоря"


def test_bridge_window_matches_history():
    b = load("bridge_mgmt_ifrs")
    assert b["window"] == b["cor"]["window"] == b["cir"]["window"] == b["nim"]["window"]
    for x in ("cor", "nim", "cir"):
        lo, hi = b[x]["window"]
        periods = [h["period"] for h in b[x]["history"]]
        assert lo in periods and hi in periods and hi == anchor_period(), f"{x}: окно вне истории"
    assert b["nim"]["method"] == "ratio" and b["cor"]["method"] == b["cir"]["method"] == "additive"


def test_bridge_history_carries_every_reported_quarter_of_the_anchor_year():
    """Год гайденса в упр. базисе собирается из упр. факта отчётных кварталов года якоря: история моста обязана
    нести каждый такой квартал числами — иначе ядро отказывает."""
    b = load("bridge_mgmt_ifrs")
    need = year_quarters(anchor_period())
    for x in ("cor", "nim", "cir"):
        rows = {h["period"]: h for h in b[x]["history"]}
        bad = [p for p in need if p not in rows or any(rows[p][f]["v"] is None for f in ("mgmt", "engine", "gap"))]
        assert not bad, f"{x}: в истории моста нет отчётных кварталов года якоря {bad}"


def test_mgmt_quarters_carry_printed_and_exact_values():
    """Напечатанное — без суффикса, точное (справочник банка или расчёт по определению банка) — с суффиксом _exact;
    на якоре точные ЧПМ, CoR и C/I — числами, напечатанное и точное расходятся не больше разряда печати."""
    m = load("mgmt_quarterly")
    a = m["quarters"][anchor_period()]
    unit = {"nim": 0.001, "cor": 0.001, "cir": 0.01}       # разряд печати: 7,6 %; 2,2 %; 42 %
    for k in ("nim", "cor", "cir"):
        assert a[k + "_exact"]["v"] is not None, k
        if k in a:
            assert abs(a[k]["v"] - a[k + "_exact"]["v"]) <= 0.6 * unit[k], f"{k}: напечатанное и точное расходятся"
    assert sorted(m["quarters"]) == list(m["quarters"]) and list(m["quarters"]) == list(load("pnl_quarterly")["quarters"])
    assert a["op_equity"]["v"] == load("balance")["equity"]["bv_common"]["v"], "капитал для ROE банка — без бессрочных"


def test_history_gaps_name_every_quarter_without_a_printed_value():
    m = load("mgmt_quarterly")
    named = {g["period"]: g for g in m["history_gaps"]}
    for p, row in m["quarters"].items():
        empty = [k for k in ("nim", "cor", "cir") if k not in row]
        if empty:
            assert p in named and named[p]["basis"] == "mgmt", p
            assert named[p]["reason"].split(": ")[1].split(" (")[0] == ", ".join(empty), p
        else:
            assert p not in named, p


def test_mgmt_annual_nodes_have_a_source():
    m = load("mgmt_quarterly")
    anchor = anchor_period()
    last_full = int(anchor[:4]) - (0 if anchor.endswith("Q4") else 1)
    assert sorted(m["annual"]) == [str(y) for y in range(int(min(m["quarters"])[:4]), last_full + 1)]
    for y, rec in m["annual"].items():
        assert set(rec) == {"nim", "cor", "cir", "roe"}, y
        for f, n in rec.items():
            assert has_text(n.get("src")) if n["v"] is not None else has_text(n.get("calc")), f"annual.{y}.{f}"
            assert n["v"] is None or 0 < n["v"] < 1, f"annual.{y}.{f}: не доля"


def test_shares_and_ratios_are_fractions_or_millions():
    """Единицы: нормативы и ставки — доли (не проценты); акции — млн шт."""
    cap, nb, sh = load("capital"), load("nii_books"), load("shares")
    for path in ("n20_0.value", "n1_1_bank.value", "n20_2"):
        assert 0.03 < get(cap, path)["v"] < 0.5, path
    for b in BOOKS:
        assert 0.0 < nb["books"][b]["rate_anchor"]["v"] < 0.6, b
    assert 10000 < sh["issued_total"]["v"] < 50000 and sh["unit"].startswith("млн шт.")
    for p, row in load("pnl_quarterly")["quarters"].items():
        assert 0.0 < row["key_avg"]["v"] < 0.5, f"{p}: key_avg не доля"


def test_estimated_flags_are_booleans_and_explained():
    """Оценочный узел несёт estimated: true и слова о способе оценки (у диапазона — два конца вокруг значения);
    нормативы якоря — фактом формы банка (оценки нет)."""
    for name in ALL:
        for p, v in nodes(load(name)):
            if "estimated" in v:
                assert v["estimated"] is True and has_text(v.get("calc")), f"{name}.{p}"
                if "range" in v:
                    lo, hi = v["range"]
                    assert lo <= v["v"] <= hi, f"{name}.{p}: значение вне диапазона"
    cap = load("capital")
    for slot in ("n20_0", "n1_1_bank"):
        assert cap[slot]["estimated"] is False and "estimate" not in cap[slot], slot


def test_ras_bridges_are_blocks_or_nulls_with_reason():
    """Моста прибыли и моста стоимости риска нет: null с причиной — не ноль; мост ЧПД — справочный блок с числом."""
    r = load("bridge_ras_ifrs")
    assert r["cor"]["v"] is None and has_text(r["cor"]["calc"])
    for k in "1234":
        assert r["by_quarter"][k]["v"] is None and "нет данных" in r["by_quarter"][k]["calc"]
        assert r["nii"]["by_quarter"][k]["v"] is None
    assert r["nii"]["value"]["v"] == r["nii"]["quarters"][-1]["ratio"]["v"] and r["nii"]["window"][0] == anchor_period()
    assert r["iea"]["value"]["v"] is None and r["iea"]["codes"] is None
