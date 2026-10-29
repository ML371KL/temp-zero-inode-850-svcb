"""Мир уровня ключа цели ЧПМ, окно фактов узла уровней, строки обратного расчёта с уточнением на полной полосе,
справочные варианты с подписью и отпечатком книги, слова гейтов — тесты на фикстуре `tests/fixtures/core_t`.

Проверки — тождества и закрытые формулы, выведенные из книги, фактов и рядов клеток независимо от кода ядра
(`tests/support_core_t6.py`; те же проверки зовёт мутационный набор): ключ `nii.transmission.level_world` (М§4.5);
премия роста средств клиентов по кварталам — ключи квартала и полугодия её траектории (М§4.3);
подузел `window` узла уровней и сообщение гейта окна (М§14.2, §14.5); ключи `valuation.reverse_dcf.refine_rows` и
`valuation.reverse_dcf.premium_facts` (М§11.2, §11.3); подпись и порядок справочных вариантов, сверка отпечатка
книги (М§14.5); число знаков порога и маржа якоря в сообщениях гейтов. Без своих ключей книги ничего из этого
нет — и у книги первой формы.
"""

from __future__ import annotations

import pytest

from model import checks as C
from model import reverse as R
from model.levels import level_nim, levels, window_facts
from model.nii import level_world
from tests import support_core_t3 as S
from tests import support_core_t6 as S6
from tests.support_core import fixture_run

tact = pytest.mark.tact                      # в такте сервера — проверки на готовой сетке и решения передачи;
#                                              сетки вариантов, полосы и поиск корня — только в CI


# ------------------------------------------------------------------ мир уровня ключа цели ЧПМ (М§4.5)


@tact
def test_target_key_is_the_stationary_margin_of_the_level_world():
    S6.check_level_world()


@tact
def test_level_world_stays_put_on_the_transmission_axis_and_moves_with_the_key():
    S6.check_level_world_axes()


@tact
def test_target_margin_row_reads_the_key_as_the_level_of_the_named_world():
    S6.check_level_world_row()


# ------------------------------------------------------------------ премия средств клиентов по кварталам (М§4.3)


def test_funds_premium_keyed_by_quarter_is_read_in_its_quarter():
    S6.check_funds_premium_by_quarter()


# ------------------------------------------------------------------ окно фактов и участок уровней (М§14.5)


@tact
def test_window_of_facts_stands_next_to_the_levels_and_in_the_gate_message():
    S6.check_window_node()


@tact
def test_levels_take_full_years_and_the_cost_of_risk_of_amortised_loans():
    S6.check_level_years_and_cost_base()


# ------------------------------------------------------------------ обратный расчёт (М§11.2, §11.3)


@tact
def test_rows_refined_on_the_full_band_are_named_by_the_book():
    S6.check_refine_rows()


def test_only_the_named_rows_are_refined_on_the_full_band():
    S6.check_refine_rows_run()


@tact
def test_value_without_excess_growth_keeps_the_premium_named_a_fact():
    S6.check_premium_facts()


def test_value_without_excess_growth_row_keeps_the_fact_of_the_anchor_year():
    S6.check_premium_facts_row()


# ------------------------------------------------------------------ справочные варианты (М§14.5)


def test_reference_variants_carry_the_note_and_print_by_the_size_of_the_price():
    S6.check_variants_note_and_order()


@tact
def test_release_takes_reference_variants_only_with_the_fingerprint_of_the_book():
    S6.check_variants_fingerprint()


def test_book_tables_carry_the_fingerprint_next_to_the_reference_variants():
    S6.check_tables_fingerprint()


# ------------------------------------------------------------------ слова гейтов (М§14.2)


@tact
def test_funds_cost_gate_prints_the_ratio_and_the_limit_with_the_same_digits():
    S6.check_funds_cost_digits()


def test_anchor_margin_of_the_joint_gate_is_named_by_the_label_of_the_book():
    S6.check_anchor_margin_words()


@tact
def test_control_summary_counts_answer_its_rows():
    S6.check_control_summary_counts()


@tact
def test_build_remark_and_the_words_of_a_release_without_indicators():
    S6.check_release_words()


@tact
@pytest.mark.tact
def test_funding_path_is_the_ratio_of_expected_balances_and_the_share_of_the_gate():
    S6.check_funding_path()


def test_nothing_of_the_level_world_and_the_window_without_their_keys():
    """Без ключей книги нет ни мира уровня, ни подузла окна, ни списка строк с уточнением, ни фактов премий — у
    книги первой формы и у формы Т; решение передачи несёт мир-опору как мир уровня."""
    for run in (fixture_run(), S.grid_of()):
        book, tr = run.ctx.book, run.ctx.transmission
        assert level_world(book) is None and level_nim(run.ctx) is None
        assert tr.level_world == tr.reference_world and tr.reference_level == tr.target_eng
        assert window_facts(run) is None and R.refine_rows(book) is None and R.premium_facts(book) == frozenset()
        assert "window" not in levels(run, run.ctx.timeline.last_year)
        solved = next(f for f in C.check_invariants(run) if f.name == "transmission_solved")
        assert not solved.fired and f"мира {tr.reference_world} равен цели" in solved.message
        joint = next(f for f in C.check_gates(run) if f.name == "nim_path_joint")
        assert "из ЧПМ якоря (" in joint.message
