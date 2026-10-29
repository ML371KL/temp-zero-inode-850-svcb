"""Мир-опора κ, симметричное угасание, сторожа уровней и узлы «на чём стоит заголовок» — тесты на фикстуре
`tests/fixtures/core_t`.

Проверки — тождества и закрытые формулы, выведенные из книги, фактов и рядов клеток независимо от кода ядра
(`tests/support_core_t5.py`; те же проверки зовёт мутационный набор): κ-добавка к миру-опоре книги (М§4.6);
угасание терминала при любом знаке избытка (М§7); гейты `nim_stationary`, `window_backtest`, `funds_cost_to_key`
и область гейта `cir_lt` (М§14.2); узлы `levels`, `point_path`, `reference_variants` таблиц книги (М§14.5);
стационарная маржа и уровни у строки обратного расчёта по ключу цели ЧПМ и уточнение решения у края диапазона
(М§11.2). Без своих ключей книги новых гейтов и узлов нет — и у книги первой формы; отпечаток входов прохода
клеток пишется и при подменённой дате.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pickle

import pytest

from model import book_results as BR
from model import checks as C
from model.grid import path_inputs, path_key, path_keys, run_grid
from model.levels import cir_lt_value, funds_cost_to_key, levels, point_path, stationary_nim
from tests import support_core_t3 as S
from tests import support_core_t5 as S5
from tests.support_core import fixture_book, fixture_facts, fixture_run
from tests.support_core_t import book_live, t_facts

tact = pytest.mark.tact                      # в такте сервера — проверки на готовой сетке; сетки вариантов, полосы
#                                              и поиск корня — только в CI


# ------------------------------------------------------------------ механики (М§4.6, §7)


@tact
def test_kappa_addon_is_measured_from_the_reference_world_of_the_book():
    S5.check_kappa_world()


def test_fade_is_symmetric_only_with_the_key_of_the_book():
    S5.check_fade_symmetric()


# ------------------------------------------------------------------ сторожа уровней (М§14.2)


@tact
def test_stationary_margin_of_the_named_world_against_its_target():
    S5.check_nim_stationary()


@tact
def test_levels_are_ratios_of_expected_aggregates_and_the_window_gate_judges_the_market_layer():
    S5.check_levels()


@tact
def test_long_term_cost_to_income_gate_judges_the_scope_of_the_book():
    S5.check_cir_scope()


@tact
def test_cost_of_client_funds_to_the_key_rate_by_world():
    S5.check_funds_cost()


@tact
def test_gates_and_nodes_of_the_levels_need_their_keys():
    """Без ключей книги нет ни сторожей уровней, ни узлов — у книги первой формы и у формы Т без ключей; с ключами
    гейты стоят после прежних, в порядке перечня, и новых сеток не считают."""
    for run in (fixture_run(), S.grid_of()):
        names = {f.name for f in C.check_gates(run)}
        assert not {"nim_stationary", "window_backtest", "funds_cost_to_key"} & names
        assert levels(run) is None and point_path(run) is None and stationary_nim(run.ctx) is None
        assert funds_cost_to_key(run) is None
    assert cir_lt_value(fixture_run()) is None and cir_lt_value(S.grid_of())["scope"] == "modal_cell"
    plain = S.grid_of()
    keys = {k: v for k, v in S5.keyed().items() if k.startswith("checks__")}
    run = S5.with_keys(plain, **keys)
    gates = [f.name for f in C.check_gates(run) if f.kind == "gate"]
    assert gates[-3:] == ["nim_stationary", "window_backtest", "funds_cost_to_key"] == list(C.FORM_GATES[-3:])
    assert tuple(gates) == tuple(g for g in C.GATE_ORDER if g in gates)
    assert [c.v_ri for c in run.cells] == [c.v_ri for c in plain.cells]


# ------------------------------------------------------------------ узлы таблиц книги (М§14.5)


@tact
def test_point_path_is_the_annual_path_of_the_point_mix_next_to_the_modal_cell():
    S5.check_point_path()


def test_reference_variants_are_the_point_of_the_book_with_the_overrides_of_the_variant():
    S5.check_reference_variants()


@tact
def test_release_reads_the_reference_variants_from_the_tables_of_the_book():
    S5.check_variants_table()


def test_book_tables_carry_the_nodes_of_the_levels_only_with_their_keys():
    """Таблицы книги: с ключами — уровни после фазы роста, путь смеси точки, стационарная маржа мира-цели,
    стоимость средств клиентов к ключевой ставке и справочные варианты; печать называет их. Что без ключей узлов
    нет — у книги первой формы и у формы Т, — сверяют тест выше и таблицы проекции (`tests/test_core_t_w3.py`)."""
    nodes = {"levels", "point_path", "reference_variants", "nim_stationary", "funds_cost_to_key"}
    assert BR.reference_variants(fixture_book(), fixture_facts(), fixture_run().ctx.live, fixture_run()) is None
    book = S.book_of(**S5.keyed())
    res = BR.book_results(book, t_facts(), slow=False)
    assert nodes <= set(res)
    run = run_grid(book, t_facts())                               # входы книги: цена, дата и реестр фактов
    assert res["levels"]["rows"]["macro_neutral"]["cir"] == pytest.approx(levels(run)["rows"]["macro_neutral"]["cir"])
    assert res["levels"]["rows"]["macro_neutral"]["cir"] == pytest.approx(cir_lt_value(run)["value"], abs=0.02)
    assert res["point_path"]["modal_cell"]["cell"] == res["central_cell"]["cell"] == res["levels"]["cell"]
    assert res["point_path"]["modal_cell"]["p_analytical"] == res["central_cell"]["probability"]
    assert res["nim_stationary"]["value"] == pytest.approx(stationary_nim(run.ctx)["value"])
    assert [r["id"] for r in res["reference_variants"]] == [v["id"] for v in S5.VARIANT_LIST]
    assert all(r["d_point"] == pytest.approx(r["point"] - res["headline"]["point"]) for r in res["reference_variants"])
    gates = {c["name"]: c for c in res["checks"]}
    assert gates["funds_cost_to_key"]["fired"] is (not res["funds_cost_to_key"]["ok"])
    assert "слоя «рыночные ставки как есть»" in gates["cir_lt"]["message"]
    text = BR.render_run_output(json.loads(json.dumps(res, default=BR._default)), book)
    for words in ("УРОВНИ ПОСЛЕ ФАЗЫ РОСТА", "ПУТЬ СМЕСИ ТОЧКИ", "ЦЕНА ПРАВИЛ И РАЗВИЛОК", "стационарная маржа мира M",
                  "стоимость средств клиентов к ключевой ставке", "Смесь заголовка", S5.VARIANT_LIST[0]["title"]):
        assert words in text, words


# ------------------------------------------------------------------ обратный расчёт (М§11.2)


@tact
def test_subsample_root_near_the_edge_of_the_range_is_named_by_the_key_of_the_book():
    S5.check_near_range_edge()


@tact
def test_target_margin_row_carries_the_stationary_margin_instead_of_the_printed_one():
    S5.check_stationary_fields()


def test_target_margin_row_carries_the_stationary_margin_and_the_levels_at_the_root():
    S5.check_stationary_row()


# ------------------------------------------------------------------ отпечаток входов прохода клеток


@tact
def test_path_fingerprint_is_written_with_the_date_class_of_the_run():
    """Отпечаток входов прохода клеток пишется через pickle: класс каждого значения обязан находиться по имени
    модуля. Прогон «в будущем» (`FAKE_TODAY`) подменяет классы даты — тест идёт в наборе такта и на подменённой
    дате: дата пишется, читается обратно тем же классом, а отпечаток входов с датой внутри считается и от
    способа создания даты не зависит."""
    run = S.grid_of()
    inputs = path_inputs(run.ctx)
    keys = path_keys(inputs)
    assert set(keys) == set(run.ctx.worlds) and path_key(inputs) == path_key(path_inputs(run.ctx))
    day = dt.date.today()
    back = pickle.loads(pickle.dumps(day, protocol=pickle.HIGHEST_PROTOCOL))
    assert back == day and type(back) is dt.date and dt.date.__module__ == "datetime"
    stamped = dataclasses.replace(inputs, deviations={**inputs.deviations, "as_of": day})
    same = dataclasses.replace(inputs, deviations={**inputs.deviations, "as_of": dt.date.fromisoformat(day.isoformat())})
    assert path_key(stamped) == path_key(same) != path_key(inputs)
    # лёгкая сетка берёт проходы клеток из хранилища по отпечатку: второй раз — те же проходы, та же точка
    store: dict = {}
    book = run.ctx.book
    first = run_grid(book, t_facts(), book_live(book), summary=True, paths=store)
    again = run_grid(book, t_facts(), book_live(book), summary=True, paths=store)
    assert len(store) == 1 and first.point == again.point == pytest.approx(run.point, rel=1e-12)


FUTURE_PROBE = """
import datetime, pickle
from tests import fakedate_plugin
assert fakedate_plugin.install() is not None and datetime.date.today().isoformat() == "{day}"
from model.grid import path_inputs, path_key, run_grid
from tests import support_core_t3 as S
from tests.support_core_t import book_live, t_facts
run = S.grid_of()
inputs = path_inputs(run.ctx)
light = run_grid(run.ctx.book, t_facts(), book_live(run.ctx.book), summary=True, paths={{}})
assert abs(light.point - run.point) < 1e-9
assert type(pickle.loads(pickle.dumps(datetime.date.today()))) is datetime.date
print("KEY", path_key(inputs).hex())
"""


def test_path_fingerprint_survives_the_run_in_the_future():
    """Тот же отпечаток — в настоящем прогоне «в будущем»: интерпретатор с `FAKE_TODAY` ставит подмену даты до
    импорта ядра (как `tests/conftest.py`), считает сетку фикстуры и отпечаток входов прохода клеток. Отпечаток
    пишется (класс подменённой даты находится по имени модуля) и равен отпечатку этого прогона: от «сегодня» и
    от класса даты входы прохода не зависят."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    day = "2031-03-17"
    env = {**os.environ, "FAKE_TODAY": day, "PYTHONPATH": str(root), "PYTHONIOENCODING": "utf-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run([sys.executable, "-B", "-c", FUTURE_PROBE.format(day=day)], cwd=str(root), env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert out.returncode == 0, out.stderr[-1500:]
    key = next(line.split()[1] for line in out.stdout.splitlines() if line.startswith("KEY "))
    assert key == path_key(path_inputs(S.grid_of().ctx)).hex()


def test_retired_check_keys_leave_the_schema_together_with_the_book():
    """Снятый ключ раздела проверок схема принимает, только пока его несёт книга репозитория: ядро по нему ничего
    не считает, и держать его в схеме дольше книги незачем. Книга сняла ключ — строка `RETIRED_CHECKS` схемы
    (`model/book_schema.py`) уходит следом; этот тест напоминает о ней."""
    from model.book_schema import RETIRED_CHECKS
    from tests.support_core import real_book_or_skip
    book, _ = real_book_or_skip()
    stale = [key for key in RETIRED_CHECKS if book.opt(f"checks.{key}") is None]
    assert not stale, f"книга больше не несёт {stale}: снять их из RETIRED_CHECKS (model/book_schema.py)"
