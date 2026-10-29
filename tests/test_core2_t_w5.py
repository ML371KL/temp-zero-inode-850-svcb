"""Выпуск на форме Т: узлы «на чём стоит заголовок», якорь с глиссадой, месячная таблица, провалы раскрытия.

Быстрый выпуск на фикстуре `tests/fixtures/core_t` с ключами панели (`tests/support_core_t5.py::FINAL_KEYS`):
уровни после фазы роста `paths.levels` и модальная клетка `paths.modal_cell` рядом с годовым путём смеси (одна
функция годового пути у выпуска и у таблиц книги); стационарная маржа мира-цели рядом с ключом цели и у строки
обратного расчёта; число гейта стоимости средств клиентов; масса гейта знака стресса с её базой и передача убытка
в стоимость; справочные варианты из таблиц книги; запас якоря до требования с глиссадой; цель ROE эмитента не
сравнивается; месячная таблица операционных результатов; частичные провалы раскрытия из фактов; источник строки
словами. У книги первой формы и у формы Т без ключей ни одного из этих узлов нет (П§2, §7).
"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from model import payload as P
from model import uncertainty as U
from model.book_schema import FactsError
from model.grid import run_grid
from model.levels import stationary_nim
from model.reverse import NIM_PATH
from tests import support_core_t3 as S
from tests import support_core_t4 as S4
from tests import support_core_t5 as S5
from tests.support_core2 import TODAY, book_prices, contract, fast_release_payload, outputs
from tests.support_core_t import book_live, t_facts

tact = pytest.mark.tact
OPS_ROW = {"month": "2026M08", "published_at": "2026-09-18", "clients_total": 52.4, "clients_active": 34.1,
           "loans_gross": 3120.0, "loans_retail": 2180.0, "loans_business": 940.0, "funds_total": 4410.0,
           "funds_retail": 3050.0, "funds_business": 1360.0, "ras_ni_ytd": 61.2, "ras_ni_m": 7.9, "f102_ni_ytd": None,
           "n1_0": 0.123, "n1_1": 0.091, "n1_2": 0.104, "capital_total": 512.0, "source": "seed"}


def _release(book, facts=None, *, out=None):
    return S5.release_of(book, facts, out=out)


_unknown = S5.unknown


def _facts(file: str, change):
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


# вне такта сервера: быстрая полоса — секунды, набор такта держит цель времени (ops/budgets.json)
def test_release_prints_the_levels_next_to_the_annual_path_of_the_mix():
    S5.check_release_paths()


def test_release_carries_the_numbers_of_the_level_gates():
    S5.check_release_gate_numbers()


def test_stress_sign_node_names_the_basis_of_its_mass():
    S5.check_release_stress_basis()


def test_release_reads_the_reference_variants_and_prints_the_glide_headroom():
    S5.check_release_variants_and_glide()


@tact
def test_first_form_release_has_none_of_the_nodes():
    """У книги первой формы узлов панели нет: ни уровней, ни модальной клетки, ни стационарной маржи, ни чисел
    новых гейтов, ни вариантов, ни полей якоря с глиссадой; подпись чувствительностей — прежняя."""
    _, d = fast_release_payload(first_form=True)
    assert not {"levels", "modal_cell"} & set(d["paths"]) and "nim_stationary" not in d["nii"]["transmission"]
    assert not {"funds_cost_to_key", "stress_sign"} & set(d["checks"]) and "reference_variants" not in d["book"]
    assert not {"req20_glide_next", "req20_glide_period", "n20_headroom_glide"} & set(d["capital"]["anchor"])
    assert "ops" not in d["nowcast"] and "ключ цели" not in d["fair_value"]["bank_first_line"]["sensitivity_basis"]
    assert all("stationary_book" not in r and "levels_solved" not in r for r in d["reverse_dcf"]["rows"])
    names = {g["name"] for g in d["checks"]["gates"]}
    assert not {"nim_stationary", "window_backtest", "funds_cost_to_key"} & names


def test_monthly_table_of_operating_results_reaches_the_release():
    """Месячная таблица операционных результатов и форм ЦБ — в выпуске, когда слой индикаторов несёт её строки;
    подпись — метка книги (без метки — пусто); без строк узла нет."""
    book = S.book_of()
    px = book_prices(book)
    base = outputs({t: [(TODAY, px[t])] for t in px}, register=[])
    _, without = _release(book, out=base)
    assert "ops" not in without["nowcast"]
    _, d = _release(book, out=dataclasses.replace(base, ops_months=(dict(OPS_ROW),)))
    assert d["nowcast"]["ops"] == {"note": None, "rows": [OPS_ROW]} and _unknown(contract(d)) == []
    note = "Прибыль банка по РСБУ и форма ЦБ — не прибыль группы по МСФО"
    labelled = S.book_of(**{"meta__labels__nowcast__ops_note": note})
    _, d = _release(labelled, out=dataclasses.replace(base, ops_months=(dict(OPS_ROW), {**OPS_ROW, "month": "2026M09"})))
    assert d["nowcast"]["ops"]["note"] == note and [r["month"] for r in d["nowcast"]["ops"]["rows"]] == ["2026M08", "2026M09"]


def test_partial_disclosure_gaps_come_from_the_facts():
    """Частичные провалы раскрытия — узел фактов упр. метрик: квартал или диапазон, базис, причина словами; в
    выпуске — по кварталам истории, подряд идущие с одной причиной — одной строкой; квартал, где базис уже пуст
    целиком, второй раз не называется; без узла провалы называет только счёт. Запись с чужим базисом — отказ."""
    book = S.book_of()
    _, plain = _release(book)
    whole = plain["history"]["gaps"]
    assert [g["basis"] for g in whole] == ["mgmt"] and whole[0]["period"].endswith("2025Q1")   # кварталы без упр. метрик
    periods = [r["period"] for r in plain["history"]["quarters"]]
    at = periods.index("2025Q2")                 # с этого квартала упр. метрики фикстуры раскрыты
    why = "C/I квартала в пресс-релизе не напечатан"

    def gaps(data: dict) -> None:
        data["history_gaps"] = [{"period": f"{periods[at]}–{periods[at + 2]}", "basis": "mgmt", "reason": why},
                                {"period": periods[at + 3], "basis": "mgmt", "reason": "ROE эмитента не раскрыт"},
                                {"period": periods[at - 1], "basis": "mgmt", "reason": "квартал уже пуст целиком"},
                                {"period": periods[1], "basis": "ifrs", "reason": "остатков на конец квартала нет"},
                                {"period": "2019Q1–2019Q4", "basis": "mgmt", "reason": "до истории выпуска"}]

    _, d = _release(book, _facts("mgmt_quarterly", gaps))
    assert d["history"]["gaps"] == [
        {"period": periods[1], "basis": "ifrs", "reason": "остатков на конец квартала нет"}, *whole,
        {"period": f"{periods[at]}–{periods[at + 2]}", "basis": "mgmt", "reason": why},
        {"period": periods[at + 3], "basis": "mgmt", "reason": "ROE эмитента не раскрыт"}]
    assert P._gap_problems(d["history"]["gaps"]) == [] and _unknown(contract(d)) == []

    def broken(data: dict) -> None:
        data["history_gaps"] = [{"period": periods[at], "basis": "ras", "reason": why}]

    with pytest.raises(FactsError, match="history_gaps"):
        _release(book, _facts("mgmt_quarterly", broken))


@tact
def test_sources_of_the_release_are_words():
    """Источник строки аналога длиннее предела обрезается по границе слова, а не посередине; документ дивидендной
    политики называется названием из фактов, когда оно есть."""
    text = ("Банк: сокращённая промежуточная финансовая информация специального назначения по МСФО на отчётную "
            "дату; пересказ отчёта в издании")
    cut = P._clip_words(text, P.SRC_MAX)
    assert len(text) > P.SRC_MAX >= len(cut) and cut.endswith("…") and text.startswith(cut[:-1])
    assert text[len(cut) - 1] == " " and P._clip_words(text[:P.SRC_MAX], P.SRC_MAX) == text[:P.SRC_MAX]
    assert P._clip_words("коротко", P.SRC_MAX) == "коротко"


def test_policy_document_is_named_by_its_title():
    """Документ дивидендной политики в выпуске — название из фактов (`policy.doc_title`), когда оно есть."""
    book = S.book_of()
    _, plain = _release(book)
    doc = t_facts().file("dividends")["policy"].get("doc")
    assert plain["dividends"]["policy"]["doc"] == doc             # без названия — прежнее поле фактов

    def titled(data: dict) -> None:
        data["policy"]["doc_title"] = "Дивидендная политика (редакция фикстуры)"

    _, d = _release(book, _facts("dividends", titled))
    assert d["dividends"]["policy"]["doc"] == "Дивидендная политика (редакция фикстуры)" != doc


# ------------------------------------------------------------------ строки чувствительности (М§8.3)


@tact
def test_sensitivity_book_moves_the_band_axis_with_the_shifted_key():
    S5.check_sensitivity_book()


def test_sensitivity_basis_names_the_judgement_behind_the_key():
    """Подпись строки «₽ за 0,1 п.п. ЧПМ»: без ключей — прежние слова; у книги с суждением о стационарной марже
    мира — «ключ цели» и на сколько меняется стационарная маржа мира-цели; у книги с целью печатаемой маржи —
    на сколько меняется маржа модальной клетки."""
    from model.grid import printed_nim_lt, sensitivity_overrides

    class _Part:                                 # то, что читает подпись чувствительностей выпуска
        pass

    def words(book):
        live = book_live(book)
        run = run_grid(book, t_facts(), live)
        shifted = run_grid(U.trial_book(book, sensitivity_overrides(book, "nim")), t_facts(), live)
        rel, x = _Part(), _Part()
        rel.sensitivities = {"nim": {"run": shifted}}
        x.rel, x.book, x.run = rel, book, run
        fast = _Part()
        fast.rel, fast.book, fast.run = _Part(), book, run
        fast.rel.sensitivities = None
        return P._nim_shift_words(x), P._nim_shift_words(fast), run, shifted

    bare = S4.bare_book()                        # без цели печатаемой маржи и без стационарной: прежние слова
    full, fast, _, _ = words(bare)
    assert full == fast == f"{bare.label('terms.lt_level')} (упр.) сдвинут на 0,10 п.п."
    full, fast, run, shifted = words(S.book_of())                # в книге фикстуры — цель печатаемой маржи
    d = printed_nim_lt(shifted)["value"] - printed_nim_lt(run)["value"]
    assert full.startswith("ключ цели") and "печатаемая маржа модальной клетки меняется на +0," in full
    assert f"{100 * d:+.2f}".replace(".", ",") in full and fast.endswith("сдвинут на 0,10 п.п.") and fast.startswith("ключ цели")
    full, _, run, shifted = words(S.book_of(**{S5.NIM_ST: S5.FINAL_KEYS["checks.nim_stationary"]}))
    d = stationary_nim(shifted.ctx)["value"] - stationary_nim(run.ctx)["value"]
    assert "стационарная маржа мира M на составе баланса якоря меняется на" in full and "модальной клетки" not in full
    assert f"{100 * d:+.2f}".replace(".", ",") in full and abs(d - 0.001) < 2e-4
