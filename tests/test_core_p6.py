"""Шестой проход ядра Совкомбанка (core-pass6): франшиза строки в смеси базы расходов — за связью строки (Р8-6, М§4.7;
ключ `opex.line_share_roots` {fees, insurance → траектория κ}): Φ = λ A / A_0 + (1 − λ) H, H — номинал мира с общим
корнем κ, λ — связь строки.

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass6/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p6.py`; те же проверки зовёт мутационный набор). Без ключа (и с пустым
словарём, при доле франшизы 0, связи расходов 0, связи строки 1) ядро считает прежней ветвью кода бит в бит: это держат
регрессии книги, сверка точки на книгах Т и Совкомбанка и проверки нейтральных форм ниже.
"""

from __future__ import annotations

import pytest

from tests import support_core_p6 as P6

tact = pytest.mark.tact


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def test_empty_key_share_zero_opex_link_zero_and_line_link_one_are_bit_for_bit():
    P6.check_neutral()


def test_neutral_forms_on_the_bank_book_are_bit_for_bit():
    P6.check_neutral_bank()


# ------------------------------------------------------------------ пример методики и ядро против формулы


def test_example_of_the_method_in_exact_fractions():
    P6.check_example()


def test_franchise_mix_and_opex_in_every_cell_and_quarter():
    P6.check_grid()


def test_franchise_mix_and_opex_in_every_cell_and_quarter_of_the_bank_book():
    P6.check_grid_bank()


def test_continuity_in_the_line_link_at_zero_and_one():
    P6.check_continuity()


# ------------------------------------------------------------------ слой M и миры


def test_fixed_point_of_the_root_keeps_layer_m_on_the_line_base():
    P6.check_layer_fixture()


def test_layer_m_and_worlds_on_the_bank_book_franchise_drifts_like_the_line():
    P6.check_layer_and_worlds_bank()


# ------------------------------------------------------------------ входы прохода, память шага, отказы, выпуск


def test_key_root_and_link_are_inputs_of_every_world_path():
    P6.check_fingerprint()


def test_step_memory_and_light_evaluation_carry_the_nominal_part():
    P6.check_memo_and_light()


@tact
def test_schema_refusals():
    P6.check_refusals()


def test_release_with_pass6_key():
    P6.check_release_with_pass6_key()
