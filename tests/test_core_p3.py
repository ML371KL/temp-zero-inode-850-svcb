"""Третий проход ядра Совкомбанка (core-pass3): терминал, сверенный с явными годами (К-Т2, М§7), неработающие деньги за
средствами клиентов (К8, М§4.3, §4.11) и смесь баз строки (К2б, М§4.7).

Проверки — тождества, закрытые формулы и числа примера методики (`tests/fixtures/core_pass3/example.json`), выведенные
независимо от кода ядра (`tests/support_core_p3.py`; те же проверки зовёт мутационный набор). Без ключей книги ядро
считает прежней ветвью кода бит в бит: это держат регрессии книги и сверка точки на книгах Т и Совкомбанка.
"""

from __future__ import annotations

import pytest

from tests import support_core_p3 as P3

tact = pytest.mark.tact


# ------------------------------------------------------------------ К-Т2а: год терминала по средней длине года (М§7)


@tact
def test_year_example_and_schema():
    P3.check_year_example()
    P3.check_year_schema()


def test_year_mean_terminal_input_and_explicit_quarters_bit_for_bit():
    P3.check_year_grid()


def test_year_mean_with_stationary_rates_and_the_fixed_block():
    P3.check_year_with_stationary_and_block()


def test_year_mean_at_a_year_that_is_not_leap():
    P3.check_year_not_leap()


# ------------------------------------------------------------------ К-Т2в: угасание по календарю (М§7)


@tact
def test_fade_example_and_schema():
    P3.check_fade_example()
    P3.check_fade_schema()


def test_fade_calendar_on_the_grid():
    P3.check_fade_grid()


def test_fade_calendar_in_the_fixed_block_and_symmetric():
    P3.check_fade_block_and_symmetric()


# ------------------------------------------------------------------ К-Т2б: ставка фондирования блока К-Т (М§7, §4.10)


@tact
def test_funding_example_and_schema():
    P3.check_funding_example()
    P3.check_funding_schema()


def test_funding_balancing_on_the_grid():
    P3.check_funding_grid()


# ------------------------------------------------------------------ К8: неработающие деньги за средствами клиентов (М§4.3)


@tact
def test_cash_example():
    P3.check_cash_example()


def test_cash_follows_the_funds_on_the_grid():
    P3.check_cash_grid()


def test_cash_neutral_forms():
    P3.check_cash_equivalences()


def test_cash_and_the_funds_side_memory():
    P3.check_cash_memo()


def test_cash_anchor_and_refusals():
    P3.check_cash_anchor_and_refusals()


# ------------------------------------------------------------------ К2б: смесь баз строки (М§4.7)


@tact
def test_mix_example_and_refusals():
    P3.check_mix_example()
    P3.check_mix_refusals()


def test_mix_equivalences_on_the_grid():
    P3.check_mix_equivalences()


def test_mix_guarantees_and_driven_book():
    P3.check_mix_guarantees_and_driven()


def test_mix_franchise_shares_and_step_memory():
    P3.check_mix_shares_and_memo()


# ------------------------------------------------------------------ выпуск с ключами третьего прохода (П§2)


def test_release_with_pass3_keys():
    P3.check_release_with_pass3_keys()
