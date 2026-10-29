"""Узлы выпуска мира уровня ключа цели ЧПМ, окна фактов, справочных вариантов и выпуска без слоя индикаторов —
тесты на фикстуре `tests/fixtures/core_t` (проверки — `tests/support_core_t6.py`, их же зовёт мутационный набор).

`nii.transmission.level` — суждение об уровне маржи рядом с ключом цели; `paths.levels.window` — окно фактов
подузлом узла уровней; `book.reference_variants` — по убыванию модуля цены правила, с подписью строки, только
при отпечатке книги таблиц; `nowcast.absent` — слова выпуска, собранного без слоя индикаторов; счётчики сводки
сверки с контрольной моделью сверяет контракт (П§2, §7). Без своих ключей книги узлов нет.
"""

from __future__ import annotations

import pytest

from model import payload as P
from tests import support_core_t6 as S6
from tests.support_core2_doc import required_from_doc

# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)


def test_release_carries_the_level_judgement_the_window_and_the_noted_variants():
    S6.check_release_level_nodes()


def test_release_carries_the_funding_path_the_world_of_regime_levels_and_names_the_level_world():
    S6.check_release_funding_and_names()


def test_release_built_without_indicators_says_so():
    S6.check_release_without_indicators()


def test_stale_book_tables_leave_a_remark_instead_of_the_variants():
    S6.check_release_stale_variants()


@pytest.mark.tact
def test_new_nodes_are_named_in_the_contract_text():
    """Новые узлы и поля названы и в перечне полей контракта, и в его тексте (П§2): уровень маржи, окно фактов,
    список строк с уточнением и признак оценки по подвыборке, подпись варианта, узел выпуска без слоя
    индикаторов, счётчики сводки контрольной модели."""
    fields = P.REQUIRED_FIELDS
    assert "level?" in fields["nii.transmission"] and set(fields["nii.transmission.level"]) == {
        "world", "value", "reference_world", "reference_value"}
    assert "window?" in fields["paths.levels"] and set(fields["paths.levels.window"]) == {"nim", "cor", "cir", "loans_share"}
    assert set(fields["paths.levels.window.loans_share"]) == {"window", "anchor"}
    assert "refine_rows?" in fields["reverse_dcf"] and "gap_basis?" in fields["reverse_dcf.rows[]"]
    assert "note?" in fields["book.reference_variants.rows[]"] and "absent?" in fields["nowcast"]
    assert {"n_rows?", "n_bad?", "book_version?", "all_ok?", "valuation_date?"} <= set(fields["checks.control_model"])
    assert "funding?" in fields["paths"] and set(fields["paths.funding"]) == {"years", "cell", "anchor", "mix", "modal_cell"}
    assert all(set(fields[f"paths.funding.{part}"]) == {"loans_to_funds", "wholesale_share"}
               for part in ("anchor", "mix", "modal_cell"))
    assert "reference_world?" in fields["regimes"]
    doc = required_from_doc()
    for node in ("nii.transmission.level", "paths.levels.window", "paths.levels.window.loans_share", "paths.funding",
                 "paths.funding.mix"):
        assert node in doc, node
