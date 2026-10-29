"""Четвёртый проход ядра Совкомбанка (core-pass4): драйвер RWA гарантий — компонента смеси базы комиссий (Р5-5,
М§4.11), корень строк комиссий и страхования множителем (Р5-6, М§4.7), сложение связок на общем пути (Р5-4, М§10).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass4/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p4.py`; те же проверки зовёт мутационный набор). Без ключей книги ядро
считает прежней ветвью кода бит в бит: это держат регрессии книги и сверка точки на книгах Т и Совкомбанка.
"""

from __future__ import annotations

import pytest

from tests import support_core_p4 as P4

tact = pytest.mark.tact


# ------------------------------------------------------------------ Р5-5: драйвер RWA гарантий — компонента смеси (М§4.11)


def test_k5_component_neutral_forms():
    P4.check_k5_neutral()


def test_k5_component_level_does_not_depend_on_the_mix_shares():
    P4.check_k5_mix_invariance()


def test_k5_component_equal_to_the_carve_book_is_k5_off():
    P4.check_k5_carve_identity()


@tact
def test_k5_component_refusals():
    P4.check_k5_refusals()


def test_k5_component_example_and_the_bank_book():
    P4.check_k5_example()


def test_k5_component_in_the_marginal_sheet():
    P4.check_k5_marginal()


# ------------------------------------------------------------------ Р5-6: корень строки множителем (М§4.7)


def test_mult_neutral_forms():
    P4.check_mult_neutral()


def test_mult_override_year_has_no_root():
    P4.check_mult_override_year()


def test_mult_quarter_formula():
    P4.check_mult_quarter()


def test_mult_line_to_base_is_one_in_every_cell():
    P4.check_mult_class2()


def test_mult_form_is_an_input_of_every_world_path():
    P4.check_mult_fingerprint()


# ------------------------------------------------------------------ Р5-4: сложение связок (М§10)


@tact
def test_bundle_refusal_without_key_and_the_sum_of_increments():
    P4.check_bundle_refusal_without_key()
    P4.check_bundle_sum()


@tact
def test_bundle_sum_is_exact_and_does_not_depend_on_the_order():
    P4.check_bundle_sum_fsum()


@tact
def test_bundle_increments_on_a_trial_book_are_from_the_root_centre():
    P4.check_bundle_trial_centre()


def test_bundle_zero_is_the_book():
    P4.check_bundle_zero()


def test_bundle_key_without_shared_paths_is_bit_for_bit():
    P4.check_bundle_no_overlap_bit_for_bit()


@tact
def test_bundle_first_paths_are_distinct_under_the_key():
    P4.check_bundle_first_path_unique()


@tact
def test_bundle_corners_pass_the_schema():
    P4.check_bundle_corner_rule()


def test_bundle_corners_are_judged_on_the_root_book_only():
    P4.check_bundle_corners_only_on_the_root_book()


@tact
def test_bundle_shared_with_value_or_dict_refuses_under_the_key():
    P4.check_bundle_value_dict_overlap()


def test_bundle_axis_end_price():
    P4.check_bundle_axis_end_price()


def test_bundle_reverse_row_keeps_its_value():
    P4.check_bundle_reverse_row_keeps_its_value()


def test_bundle_band_with_records():
    P4.check_bundle_band_like()


def test_reanchor_moves_both_bundles_of_a_shared_path_once():
    P4.check_reanchor_shared_path()


# ------------------------------------------------------------------ Р5-4: лист вывода


def test_sheet_base_axis_carries_opex_roots():
    P4.check_sheet_base_axis_opex()


# ------------------------------------------------------------------ выпуск с ключами четвёртого прохода (П§2)


def test_release_with_pass4_keys():
    P4.check_release_with_pass4_keys()
