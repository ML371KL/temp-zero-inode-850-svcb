"""Запись сухого перевывода развилок (`data/assumptions/forks_rd.json`, MODEL §14.5): цены справочных вариантов и «цены
правила» книги — книга, перевыведенная под вариант, а не точка на замороженных выведенных числах.

Запись — этой книги (числовой отпечаток), покрывает каждый вариант списка книги и три замыкания капитала (цена или
«без цены» словами), её слова проходят правила текста экранов; отпечаток не замечает слов и замечает числа; таблицы
книги берут из записи разности, а при записи от другой книги цен не печатают; сборка выпуска передаёт поля строки и
предупреждение; правки инструмента развилок ложатся на шаблон и лист вывода дерева (место правки — ровно одно).
"""
from __future__ import annotations

import json
import re
import shutil

import pytest

try:
    from tests import support_book as S
except ImportError:                      # запуск из каталога tests
    import support_book as S

from model import book_results as BR
from model import payload as P
from model.book import load_book, load_facts

RECORD = S.BOOK_DIR / "forks_rd.json"


@pytest.fixture(scope="module")
def book():
    return load_book(facts=load_facts())


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run(book):
    from model.grid import live_from_book, run_grid
    facts = load_facts()
    return run_grid(book, facts, live_from_book(book, facts))


def test_the_record_belongs_to_this_book(book, record):
    """Книга называет запись ключом, запись той же схемы и того же числового отпечатка — цены печатаются."""
    assert book.get(BR.RECORD_KEY) == RECORD.name and record["schema"] == BR.RECORD_SCHEMA
    rec, why = BR.reference_record(book)
    assert why is None and rec == record and record["book"]["numbers"] == BR.book_numbers(book)
    from ops.tools import forks
    assert forks.main(["--check"]) == 0


def test_the_record_prices_every_variant_and_closure(book, record, run):
    """Строка на каждый вариант списка книги и на три замыкания капитала: разности точки и медианы — или причина словами;
    база записи — точка книги (сетка) бит в бит до записанного знака; замыкание книги — сама книга."""
    ids = [str(v["id"]) for v in book.get("valuation.reference_variants")]
    assert list(record["variants"]) == ids
    current, closures = BR.rule_closures(book)
    assert list(record["rule_price"]) == list(closures) and record["rule_price"][current]["d_point"] == 0.0
    assert abs(record["base"]["point"] - run.point) < 5e-7
    for key, r in {**record["variants"], **record["rule_price"]}.items():
        if "why" in r:
            assert r["why"].startswith("без цены") and "d_point" not in r, key
        else:
            assert isinstance(r["d_point"], float) and isinstance(r["d_median"], float) and r["fork"], key
            assert r["d_point"] == round(r["point"] - record["base"]["point"], 4), key
    assert all(isinstance(r.get("capital_gap_mass"), float) for r in record["rule_price"].values())


def test_record_words_pass_the_screen_rules(record):
    """Причины «без цены» и пометки цены печатаются на витрине: правила текста экранов (служебные имена, метки, пути)."""
    words = [r[k] for r in {**record["variants"], **record["rule_price"]}.values() for k in ("why", "mark", "median_mark") if r.get(k)]
    assert words
    assert [(w, S.printed_issues(w)) for w in words if S.printed_issues(w)] == []
    assert not [w for w in words if re.search(r"[κσφρλ]|[a-z_]{4,}", w)], "словами, без обозначений модели и ключей"


def test_the_numbers_digest_sees_numbers_not_words(book):
    """Отпечаток не меняют слова (имя оси, заголовок варианта, подпись, ссылка на запись), меняет любое число."""
    base = BR.book_numbers(book)
    axes = [dict(a) for a in book.get("valuation.uncertainty.axes")]
    axes[0]["name"] = "Другое имя оси"
    variants = [dict(v) for v in book.get("valuation.reference_variants")]
    variants[0]["title"] = "Другой заголовок"
    assert BR.book_numbers(book.with_overrides({"valuation.uncertainty.axes": axes})) == base
    assert BR.book_numbers(book.with_overrides({"valuation.reference_variants": variants})) == base
    assert BR.book_numbers(book.with_overrides({"meta.labels.rule_price.unconstrained": "другая подпись"})) == base
    assert BR.book_numbers(book.with_overrides({"valuation.reference_record": "other.json"})) == base
    assert BR.book_numbers(book.with_overrides({"valuation.erp": float(book.get("valuation.erp")) + 1e-6})) != base
    assert BR.book_numbers(book.with_overrides({"checks.m_crisis_vs_cbr.n20_min": 0.129})) != base


def test_tables_take_differences_or_say_why(book, record, run):
    """Таблицы: точка варианта — точка книги плюс разность записи; варианта нет в записи — «без цены»; запись от другой
    книги — ни одной цены, причина у каждой строки и в узле записи."""
    rows = BR.record_variants(book, run, record, None)
    spec = {str(v["id"]): v for v in book.get("valuation.reference_variants")}
    for r in rows:
        rec = record["variants"][r["id"]]
        if "why" in rec:
            assert r["point"] is None and r["d_point"] is None and r["why"] == rec["why"]
        else:
            assert r["point"] == run.point + rec["d_point"] and r["d_median"] == rec["d_median"] and r["title"] == spec[r["id"]]["title"]
    short = {**record, "variants": {k: v for k, v in record["variants"].items() if k != rows[0]["id"]}}
    assert BR.record_variants(book, run, short, None)[0]["why"].startswith("без цены")
    other = book.with_overrides({"valuation.erp": float(book.get("valuation.erp")) + 0.001})
    rec, why = BR.reference_record(other)
    assert rec is not None and why and "другой книге" in why
    assert all(r["d_point"] is None and r["why"] == why for r in BR.record_variants(other, run, rec, why))
    node = BR.record_node(other, rec, why)
    assert node["matches"] is False and node["warning"] == why
    rule = BR.record_rule_price(book, run, record, None)["rows"]
    assert [r["key"] for r in rule] == list(record["rule_price"]) and all("median" not in r for r in rule)
    cur = next(r for r in rule if r["current"])
    assert cur["point"] == run.point and cur["d_point"] == cur["d_median"] == 0.0


def test_release_passes_the_row_fields_and_the_warning(book, record, run):
    """Выпуск: строки — по убыванию модуля цены, без цены — последними, с причиной; база разностей; предупреждение таблиц о
    записи от другой книги — в узле и замечанием сборки; у «цены правила» — разности вместо медианы."""
    rows = BR.record_variants(book, run, record, None)
    table = {"book_version": str(book.get("meta.version")), "headline": {"point": run.point}, "reference_variants": rows,
             BR.VARIANTS_BOOK: book.digest, "reference_record": BR.record_node(book, record, None),
             "rule_price": BR.record_rule_price(book, run, record, None)}
    node, why_not = P.reference_variants_state(book, table)
    assert why_not is None and node["basis"] and "warning" not in node
    priced = [r for r in node["rows"] if r["d_point"] is not None]
    assert node["rows"][len(priced):] and all(r["why"] for r in node["rows"][len(priced):])
    assert [abs(r["d_point"]) for r in priced] == sorted((abs(r["d_point"]) for r in priced), reverse=True)
    assert all("d_median" in r for r in priced)
    assert P.variants_remark(None, node) == []
    stale = {**table, "reference_record": {**table["reference_record"], "matches": False, "warning": "запись от другой книги"}}
    node2, _ = P.reference_variants_state(book, stale)
    assert node2["warning"] == "запись от другой книги" and P.variants_remark(None, node2)
    rule = P.rule_price_table(book, table)["rows"]
    assert all("median" not in r and "d_point" in r and "d_median" in r for r in rule)


def test_tool_patches_land_once_on_the_tree(tmp_path):
    """Правки инструмента развилок из описания вывода (FORK_PATCHES) и подмены вариантов и замыканий ложатся на копию
    шаблона и листа дерева: место правки текста — ровно одно, строки таблиц — правки, которые инструмент знает."""
    from ops.tools import forks
    book_dir = tmp_path / "data" / "assumptions"
    (book_dir / "evidence" / "path").mkdir(parents=True)
    shutil.copy(S.BOOK_DIR / "assumptions_template.yaml", book_dir)
    for name in ("derive_on_engine.py", "derive_spec.py"):
        shutil.copy(S.EVIDENCE / "path" / name, book_dir / "evidence" / "path")
    spec = forks.load_spec(book_dir)
    known = set(spec.FORK_PATCHES) | {"base", "var", "rule"}
    for fork in list(spec.FORKS.values()) + list(spec.RULE_FORKS.values()):
        assert {part.partition(":")[0] for part in fork.split("+")} <= known, fork
    keep = {p: p.read_text(encoding="utf-8") for p in book_dir.rglob("*.*")}
    for name in spec.FORK_PATCHES:
        assert forks.apply_fork(tmp_path, name, spec.FORK_PATCHES), name
        for p, text in keep.items():
            p.write_text(text, encoding="utf-8")
    assert forks.apply_fork(tmp_path, "rule:unconstrained+var:buyback_none", spec.FORK_PATCHES)
    assert set(spec.FORK_WHY) <= {str(v["id"]) for v in load_book(facts=load_facts()).get("valuation.reference_variants")}
