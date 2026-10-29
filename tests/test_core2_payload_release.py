"""Узлы выпуска ядра, которым нужен свой быстрый выпуск на изменённой книге первой формы. Сборка быстрого выпуска без
кэша — секунды: в набор такта сервера эти тесты не входят (цель времени набора — ops/budgets.json), идут в CI и в
полном прогоне. Узлы на общем быстром выпуске — в такте: `tests/test_core2_payload.py`.
"""
from __future__ import annotations

import copy

from model import payload as P
from tests.support_core2 import fast_release_payload_on, first_form_book_and_facts


def test_the_annual_calendar_key_gets_no_false_refusal():
    """Книга первой формы с явным нейтральным ключом `dividends.calendar.frequency: annual` (то же, что его отсутствие):
    частота выплат выпуска — annual, календарь модели годовой (узла `model_quarters` нет), главная цифра ближайшей
    выплаты без объявления — DPS политики, и сверка П§7 п. 9 её принимает."""
    from model.book import book_from_dict
    from tests.support_core_t import put
    book, facts = first_form_book_and_facts()
    data = copy.deepcopy(dict(book.data))
    put(data, "dividends.calendar.frequency", "annual")
    _, d = fast_release_payload_on(book_from_dict(data, facts=facts), facts)
    ne = d["dividends"]["next_expected"]
    assert d["dividends"]["policy"]["frequency"] == "annual" and "model_quarters" not in d["dividends"]
    assert ne["status"] != "model" or ne["dps"] == ne["dps_policy"]
    assert P._dividend_problems(d) == []
