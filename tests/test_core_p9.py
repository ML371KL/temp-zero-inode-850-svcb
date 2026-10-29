"""Девятый проход ядра Совкомбанка (core-pass9): доля сжатия книги между мирами (Р11-1, ключ
`nii.books.<книга>.phi_share`), опт и слово funds на средствах клиентов (Р11-2, ключ `volumes.funds_scope`), неконтролирующие
в реальных рублях (Р11-3, ключ `pnl.nci_real`); стороны листов — бэктест книг на наклонах ядра, средства клиентов листов,
класс 6 проверок классов (наклоны книг).

Проверки — тождества, закрытые формулы своим счётом и числа примера методики (`tests/fixtures/core_pass9/example.json`),
выведенные независимо от кода ядра (`tests/support_core_p9.py`; те же проверки зовёт мутационный набор). Без ключей (и при
нулях, all, clients без К6) ядро считает прежней ветвью кода бит в бит.
"""

from __future__ import annotations

import pytest

from tests import support_core_p9 as P9

tact = pytest.mark.tact


def test_zero_shares_all_scope_and_inactive_clients_are_bit_for_bit_on_the_bank_book():
    P9.check_neutral_bank()


def test_t_book_without_keys_is_bit_for_bit():
    P9.check_neutral_fixture()


def test_example_of_the_method_in_exact_fractions_and_the_core_terminal():
    P9.check_example()


def test_rates_targets_stationary_lt_spreads_and_slopes_with_shares_on_all_books():
    P9.check_rates_bank()


def test_reference_world_h_is_untouched_by_shares():
    P9.check_h_world()


def test_structural_wholesale_and_anchor_on_client_funds():
    P9.check_funds_bank()


def test_funds_word_of_line_bases_on_client_funds():
    P9.check_funds_words()


def test_funds_side_memo_cash_driver_and_link_base_on_client_funds():
    P9.check_funds_memo_and_link_base()


def test_non_controlling_interest_in_real_rubles():
    P9.check_nci_bank()


@tact
def test_schema_refusals():
    P9.check_refusals()


def test_sheet_backtest_of_books_on_the_core_slopes():
    P9.check_sheet_backtest()


def test_sheets_read_client_funds_with_the_core_function():
    P9.check_sheet_funds()


def test_class_six_judges_book_slopes_by_type():
    P9.check_class_slopes()
