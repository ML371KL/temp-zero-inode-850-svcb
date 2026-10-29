"""Седьмой проход ядра Совкомбанка (core-pass7): книга страховых обязательств К6 несёт корень ρ номинальной части (Р9-1,
М§4.3; ключ `volumes.liability_driver_roots` {fees, insurance → траектория ρ}): E_q = E_(q−1) (1 + wage)^((1 − λ)/4)
(D_q / D_(q−1))^λ (1 + ρ_q)^(1 − λ) — λ за базой строки, 1 − λ — номинал мира с корнем строки.

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass7/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p7.py`; те же проверки зовёт мутационный набор). Без ключа (и с пустым
словарём, при ρ ≡ 0, при снятом К6, при ключе строки без ведомой книги, при связи строки 1) ядро считает прежней ветвью
кода бит в бит: это держат регрессии книги, сверка точки на книгах Т и Совкомбанка и проверки нейтральных форм ниже.
"""

from __future__ import annotations

import pytest

from tests import support_core_p7 as P7

tact = pytest.mark.tact


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def test_empty_key_zero_root_k6_off_fees_key_and_link_one_are_bit_for_bit_on_the_bank_book():
    P7.check_neutral_bank()


def test_empty_key_variant_and_key_of_a_line_without_a_driven_book_are_bit_for_bit():
    P7.check_neutral_fixture()


# ------------------------------------------------------------------ пример методики и ядро против формулы


def test_example_of_the_method_in_exact_fractions():
    P7.check_example()


def test_driven_book_with_the_root_in_every_cell_and_quarter():
    P7.check_grid()


def test_continuity_in_the_line_link_at_zero_and_one():
    P7.check_continuity()


# ------------------------------------------------------------------ слой M и миры


def test_layer_m_on_the_line_base_and_fixed_point_of_the_root_on_the_bank_book():
    P7.check_layer_bank()


def test_fixed_point_of_the_root_keeps_layer_m_on_the_line_base():
    P7.check_layer_fixture()


def test_root_is_common_to_worlds_and_the_book_drifts_like_the_line():
    P7.check_worlds_bank()


# ------------------------------------------------------------------ входы прохода, память шага, отказы, выпуск


def test_key_root_and_link_are_inputs_of_every_world_path():
    P7.check_fingerprint()


def test_step_memory_carries_the_root_and_the_level_row():
    P7.check_memo_and_light()


@tact
def test_schema_refusals():
    P7.check_refusals()


def test_release_with_pass7_key():
    P7.check_release_with_pass7_key()
