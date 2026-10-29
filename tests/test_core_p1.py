"""Первый проход ядра Совкомбанка (core-pass1): шаг хранения прогонов (М4, М§10), множители CoR по книгам (М7, М§4.6),
драйвер расходов по себестоимости книг (М13, М§4.7), постоянные в рублях части за концом сетки (терминал К-Т, М§7) и
выкуп по цене мира (М3, М§5.6).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass1/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p1.py`; те же проверки зовёт мутационный набор). Без ключей книги ядро
считает прежней ветвью кода бит в бит: это держат регрессии книги и сверка точки на книгах Т и Совкомбанка.
"""

from __future__ import annotations

import pytest

from tests import support_core_p1 as P1

tact = pytest.mark.tact


# ------------------------------------------------------------------ М4: шаг хранения прогонов (М§10)


@tact
def test_draw_step_example_rounds_half_up_and_takes_the_median_of_kept_draws():
    P1.check_draw_step_example()


def test_draw_step_key_changes_only_the_kept_draws():
    P1.check_draw_step_band()


@tact
def test_release_validator_checks_draws_against_the_draw_step():
    P1.check_draw_step_validator()


# ------------------------------------------------------------------ М7: множители CoR по книгам (М§4.6)


@tact
def test_book_cor_multipliers_example_and_refusals():
    P1.check_book_cor_example()
    P1.check_book_cor_schema()


def test_book_cor_form_equals_segments_and_plain_cor():
    P1.check_book_cor_equivalences()


def test_book_cor_reserves_by_book_on_the_cell_cor():
    P1.check_book_cor_quarters()


def test_book_cor_gate_reads_the_cor_at_the_anchor_mix():
    P1.check_book_cor_gate_and_levels()


# ------------------------------------------------------------------ М13: драйвер расходов по себестоимости книг (М§4.7)


@tact
def test_opex_weights_example_history_and_refusals():
    P1.check_opex_weights_example()


def test_opex_weights_reproduce_the_iea_and_loans_bases_and_ignore_scale():
    P1.check_opex_weights_equivalences()


def test_opex_weights_quarter_identity_and_fees_untouched():
    P1.check_opex_weights_quarters()


def test_opex_weights_refusals_and_zero_link():
    P1.check_opex_weights_refusals()


def test_opex_weights_probe_leaves_no_trace():
    P1.check_opex_weights_probe_leaves_no_trace()


# ------------------------------------------------------------------ терминал К-Т: постоянные в рублях части (М§7)


@tact
def test_terminal_block_example_closed_forms_and_neutral_asset():
    P1.check_terminal_example()


@tact
def test_terminal_block_equals_the_reference_formulas():
    P1.check_terminal_against_reference()


def test_terminal_block_on_the_grid_identity_linearity_and_inputs():
    P1.check_terminal_grid()


def test_terminal_block_keys_are_valuation_parameters():
    P1.check_terminal_parts_and_pass()


# ------------------------------------------------------------------ М3: выкуп по цене мира (М§5.6)


@tact
def test_buyback_example_path_value_and_rules():
    P1.check_buyback_example()


def test_buyback_switched_off_is_bit_for_bit_and_zero_amount_is_neutral():
    P1.check_buyback_without_key_and_zero()


def test_buyback_identities_price_path_and_decisions_on_cell_shares():
    P1.check_buyback_grid()


def test_buyback_book_tables_carry_the_price_valuation():
    P1.check_buyback_book_tables()


def test_buyback_price_rules_cheaper_price_fixed_point_and_shock_year():
    P1.check_buyback_rules()


def test_buyback_pass_key_moves_with_erp_and_ignores_the_live_price():
    P1.check_buyback_pass_key_and_live_price()


def test_buyback_refusals():
    P1.check_buyback_refusals()


def test_buyback_forward_drops_by_the_register_dividend_of_a_closed_quarter():
    P1.check_buyback_bridge_dividend()


# ------------------------------------------------------------------ выпуск с ключами прохода (П§2)


def test_release_with_all_pass_keys_keeps_the_contract_and_carries_their_nodes():
    P1.check_release_with_pass_keys()
