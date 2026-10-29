"""Второй проход ядра Совкомбанка (core-pass2): опт сверх структурной доли (К3, М§4.10), резерв по книгам (К7, М§4.6),
RWA гарантий (К5, М§4.11), терминал от стационарных ставок книг (К4, М§7), база связи по строке (К2, М§4.7),
книга-обязательство за драйвером строки (К6, М§4.3) и жетон DPS в машине роста (К1, М§4.13.2).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass2/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p2.py`; те же проверки зовёт мутационный набор). Без ключей книги ядро
считает прежней ветвью кода бит в бит: это держат регрессии книги и сверка точки на книгах Т и Совкомбанка.
"""

from __future__ import annotations

import pytest

from tests import support_core_p2 as P2

tact = pytest.mark.tact


# ------------------------------------------------------------------ К3: опт сверх структурной доли (М§4.10)


@tact
def test_wholesale_example_and_refusals():
    P2.check_wholesale_example()
    P2.check_wholesale_refusals()


def test_wholesale_structural_share_is_the_book_share_and_bit_for_bit_at_the_anchor():
    P2.check_wholesale_identity()


def test_wholesale_above_the_structural_part_is_repaid_on_surplus():
    P2.check_wholesale_quarters()


# ------------------------------------------------------------------ К7: резерв по книгам (М§4.6)


@tact
def test_allowance_example_and_refusals():
    P2.check_allowance_example()
    P2.check_allowance_refusals()


def test_allowance_anchor_exact_and_equal_cover_is_the_anchor_share():
    P2.check_allowance_anchor_and_equal_cover()


def test_allowance_follows_the_books_of_the_quarter():
    P2.check_allowance_quarters()


# ------------------------------------------------------------------ К5: RWA гарантий (М§4.11)


@tact
def test_guarantees_example_with_core_functions():
    P2.check_guarantees_example()


def test_guarantees_rwa_identity_anchor_unchanged_and_switch_off():
    P2.check_guarantees_grid()


def test_guarantees_driver_fees_line():
    P2.check_guarantees_fees_line()


def test_guarantees_driver_nominal_fees_base():
    P2.check_guarantees_nominal_driver()


def test_guarantees_anchor_notional_and_refusals():
    P2.check_guarantees_anchor_and_refusals()


# ------------------------------------------------------------------ К4: терминал от стационарных ставок книг (М§7)


@tact
def test_stationary_example():
    P2.check_stationary_example()


def test_stationary_terminal_input_and_explicit_quarters_bit_for_bit():
    P2.check_stationary_grid()


def test_stationary_is_neutral_at_full_rate_adjustment():
    P2.check_stationary_neutral_at_full_adjustment()


# ------------------------------------------------------------------ К2: база связи по строке (М§4.7)


@tact
def test_lines_example():
    P2.check_lines_example()


def test_lines_bases_equivalences_and_bit_for_bit_at_the_link_base():
    P2.check_lines_equivalences()


def test_lines_quarter_identity_funds_nominal_and_opex_mix():
    P2.check_lines_quarters()


def test_lines_step_memory_and_step_flows():
    P2.check_lines_memo_and_trace()


def test_lines_refusals():
    P2.check_lines_refusals()


def test_guarantees_driven_by_the_carve_book_are_the_old_rwa():
    P2.check_guarantees_driver_is_the_carve_book()


# ------------------------------------------------------------------ К6: книга-обязательство за драйвером строки (М§4.3)


@tact
def test_driven_example():
    P2.check_driven_example()


def test_driven_book_follows_the_line_driver():
    P2.check_driven_quarters()


def test_driven_book_follows_the_nominal_driver_at_any_link():
    P2.check_driven_nominal()


def test_driven_book_is_outside_the_funds_side_memory():
    P2.check_driven_memo()


def test_driven_refusals():
    P2.check_driven_refusals()


# ------------------------------------------------------------------ К1: жетон DPS в машине роста (М§4.13.2 п. 2а)


@tact
def test_token_example_with_core_functions():
    P2.check_token_example()


def test_token_year_identities_floor_refusals_and_neutral_zero():
    P2.check_token_grid()


def test_token_is_monotone_in_the_minimum():
    P2.check_token_monotone()


def test_token_memory_resets_with_the_pass():
    P2.check_token_memory_reset()
