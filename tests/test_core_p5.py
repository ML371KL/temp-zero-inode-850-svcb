"""Пятый проход ядра Совкомбанка (core-pass5): доля неработающих денег К8 параметром книги (Р6-1, М§4.3, §4.11) — путь
доли от квартала якоря к доле книги, ФОР долей якоря, вытесненная часть прочих активов своим слагаемым RWA (θ).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass5/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p5.py`; те же проверки зовёт мутационный набор). Без ключа (и при share:
anchor) ядро считает прежней ветвью кода бит в бит: это держат регрессии книги, сверка точки на книгах Т и Совкомбанка и
проверки нейтральных форм ниже.
"""

from __future__ import annotations

import pytest

from tests import support_core_p5 as P5

tact = pytest.mark.tact


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def test_share_anchor_and_theta_one_are_bit_for_bit():
    P5.check_neutral()


def test_share_anchor_on_the_bank_book_is_bit_for_bit_and_the_anchor_is_the_fact():
    P5.check_neutral_bank()


def test_book_share_by_override_on_a_share_anchor_book_reads_the_reserves_node_in_the_core():
    P5.check_overrides_reserves_anchor()


# ------------------------------------------------------------------ пример методики и сетка


def test_example_of_the_method_on_the_bank_book():
    P5.check_example()


def test_path_balance_and_rwa_in_every_cell_and_quarter():
    P5.check_grid()


def test_theta_zero_with_a_step_is_the_book_carve_d1():
    P5.check_step_identity()


def test_theta_zero_with_a_step_is_the_book_carve_d1_on_the_bank_book():
    P5.check_step_identity_bank()


def test_path_of_the_share_and_the_class_five_series():
    P5.check_path()


def test_class_six_judges_a_word_centre_by_equality():
    P5.check_class_six_word_rule()


def test_key_is_an_input_of_every_world_path():
    P5.check_fingerprint()


def test_step_memory_and_light_evaluation_carry_the_displaced_term():
    P5.check_memo_and_light()


def test_variant_with_the_loans_driver_and_share_anchor_is_k8_off():
    P5.check_variant_trap()


@tact
def test_schema_and_core_refusals():
    P5.check_refusals()


# ------------------------------------------------------------------ выпуск с ключом пятого прохода (П§2)


def test_release_with_pass5_key():
    P5.check_release_with_pass5_keys()
