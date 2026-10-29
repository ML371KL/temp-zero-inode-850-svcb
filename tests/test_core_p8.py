"""Восьмой проход ядра Совкомбанка (core-pass8): одна форма связи λ у франшизы строки и книги К6 (Р10-5, ключ
`volumes.line_link_form`), гейт стоимости средств клиентов на ожидании мира (Р10-6, ключ `checks.funds_cost_to_key.scope`) и
«средства клиентов» без книг К6 в числах гейтов ядра (ключ (3) Р10-1, `checks.client_funds`).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass8/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p8.py`; те же проверки зовёт мутационный набор). Без ключей (и при mixed,
modal_cell, all, и при ключе формы в неактивных режимах) ядро считает прежней ветвью кода бит в бит.
"""

from __future__ import annotations

import pytest

from tests import support_core_p8 as P8

tact = pytest.mark.tact


# ------------------------------------------------------------------ без ключей и нейтральные формы — бит в бит


def test_mixed_modal_cell_all_and_inactive_line_are_bit_for_bit_on_the_bank_book():
    P8.check_neutral_bank()


def test_t_book_and_fixture_without_keys_are_bit_for_bit():
    P8.check_neutral_fixture()


# ------------------------------------------------------------------ пример методики и ядро против формулы


def test_example_of_the_method_in_exact_fractions():
    P8.check_example()


def test_franchise_and_k6_in_line_form_in_every_cell_and_quarter():
    P8.check_grid()


def test_limits_of_the_line_form_at_link_zero_and_one():
    P8.check_limits()


def test_continuity_in_the_line_link_at_zero_and_one():
    P8.check_continuity()


# ------------------------------------------------------------------ слой M, неподвижная точка, миры


def test_fixed_point_of_kappa_and_rho_keeps_layer_m_on_the_line_bases_on_the_bank_book():
    P8.check_layer_bank()


def test_fixed_point_of_kappa_and_rho_on_the_fixture():
    P8.check_layer_fixture()


def test_franchise_drifts_like_the_line_in_every_world():
    P8.check_drift_bank()


# ------------------------------------------------------------------ входы прохода, память шага, отказы


def test_key_roots_and_link_are_inputs_of_every_world_path():
    P8.check_fingerprint()


def test_step_memory_carries_phi_psi_and_the_lag_row():
    P8.check_memo()


@tact
def test_schema_refusals_and_missing_history():
    P8.check_refusals()


# ------------------------------------------------------------------ Р10-6 и ключ (3)


def test_funds_cost_gate_on_the_world_expectation():
    P8.check_gate()


def test_client_funds_without_k6_in_the_core_gates():
    P8.check_client_funds()


# ------------------------------------------------------------------ лист вывода


def test_sheet_roots_in_the_line_form():
    P8.check_sheet_roots()


def test_sheet_spec_rho_corridor_by_form_and_level_residuals_at_the_ends():
    P8.check_sheet_spec()


def test_sheet_judges_both_numbers_at_the_bundle_ends():
    P8.check_sheet_ends()


def test_sheet_phi_axis_calls_the_core_gate():
    P8.check_sheet_phi_axis()


# ------------------------------------------------------------------ выпуск


def test_release_with_pass8_keys():
    P8.check_release_with_pass8_keys()
