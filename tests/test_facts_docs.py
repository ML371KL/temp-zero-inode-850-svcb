"""Документы фактов Совкомбанка: SCHEMA.md описывает каждый файл и параметры сборщика; FACTS.md и REANCHOR.md говорят о
сборщике Совкомбанка (режимы, форма, перечень квартала). Полный текст FACTS.md и SCHEMA.md §1–2.13 — после «устоялось»."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"

pytestmark = pytest.mark.docs


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_schema_describes_every_file():
    schema = (FACTS / "SCHEMA.md").read_text(encoding="utf-8")
    missing = [p.name for p in sorted(FACTS.glob("*.json")) if f"`{p.name}`" not in schema]
    assert not missing, f"SCHEMA.md не описывает: {missing}"
    assert "16 файлов" in schema and "SVCB" in schema


def test_schema_lists_the_named_parameters_of_the_builder():
    """Всё, что в сборщике названо датой, периодом или таблицей состава, — именованный параметр, и схема его называет."""
    schema = (FACTS / "SCHEMA.md").read_text(encoding="utf-8")
    src = BUILDER.read_text(encoding="utf-8")
    for name in ("PNL_FIRST", "BRIDGE_HISTORY_FIRST", "CAPITAL_HISTORY_FIRST", "HORIZON_YEARS", "SNAPSHOT", "SHEET_GAPS",
                 "ALLOWANCE_BOOKS", "GUARANTEES", "ANCHOR_WORDS", "INTEREST_LINES", "INTEREST_OUTSIDE", "PNL_SLOTS",
                 "PNL_SUM", "OTHER_ASSETS", "OTHER_ASSETS_FIXED", "EQUITY_LINES", "POLICY", "CP_ANCHOR", "PERIM_ANCHOR",
                 "MISC_ANCHOR"):
        assert re.search(rf"^{name}\b", src, re.M), f"в сборщике нет параметра {name}"
        assert f"`{name}`" in schema, f"SCHEMA.md не называет параметр {name}"


@pytest.mark.parametrize("rel", ("docs/FACTS.md", "docs/REANCHOR.md", "data/facts/SCHEMA.md"))
def test_documents_name_the_modes_of_the_builder(rel):
    doc = text(rel)
    for mode in ("--plan", "--forms", "--expected"):
        assert mode in doc, f"{rel}: не назван режим {mode}"
    assert "Совкомбанк" in doc


def test_facts_md_states_the_form_of_the_issuer():
    doc = text("docs/FACTS.md")
    for words in ("13 книг", "годовой", "Н1.2", "SHEET_GAPS", "байт в байт", "узлы калибровки"):
        assert words in doc, words


def test_reanchor_md_names_the_quarter_steps_of_the_issuer():
    doc = text("docs/REANCHOR.md")
    sec = doc[doc.index("### 1.10."):doc.index("## 2. Файл отчёта квартала")]
    for words in ("2026Q3", "перепись", "01.10.2026", "dividends_payable_year", "calib-nii"):
        assert words in sec, words
