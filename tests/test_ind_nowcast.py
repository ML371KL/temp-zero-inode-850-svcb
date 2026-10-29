"""Нау-каст квартала: уравнение, вес w, месяцы банка и профиль, заморозка, горизонты; ретро на истории.

Две истории. Затравка эмитента (`data/indicators/seed/`): моста прибыли нет — прогноз равен ожиданию
модели, эталон ЧПМ — оценка ЧПД по форме 0409102. Сочинённая история «банка с мостом» (`bridged_store`):
месячный релиз с прибылью, ЧПД и стоимостью риска, форма 0409101 — на ней проверяется общая механика
мостов, весов и ретро.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from indicators import collect, config, nowcast, periods, retro
from indicators.store import Point, Store
from tests.support_ind import FIX, seeded_store, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта

SIGMAS = {"ras": {"0": 0.07, "1": 0.04, "2": 0.04, "3": 0.035}, "base": 0.065}
NIM_SIGMAS = {**SIGMAS, "nim": {"ras": {"0": 0.002, "1": 0.0025, "2": 0.0013, "3": 0.001}, "base": 0.002}}
PROFIT_BRIDGE, NII_BRIDGE, IEA_BRIDGE, COR_BRIDGE = 1.5, 1.2, 1.1, 0.9
BRIDGE = {"by_quarter": {str(n): {"v": PROFIT_BRIDGE} for n in (1, 2, 3, 4)},
          "nii": {"value": {"v": NII_BRIDGE}, "n": {"v": 2},
                  "quarters": [{"period": f"{y}Q{n}", "ratio": NII_BRIDGE} for y in (2024, 2025) for n in (1, 2, 3, 4)]},
          "iea": {"value": {"v": IEA_BRIDGE}, "basis": "engine",
                  "quarters": [{"period": f"{y}Q{n}", "ratio": IEA_BRIDGE} for y in (2024, 2025) for n in (1, 2, 3, 4)]},
          "cor": {"value": {"v": COR_BRIDGE},
                  "quarters": [{"period": f"{y}Q{n}", "ratio": COR_BRIDGE} for y in (2024, 2025) for n in (1, 2, 3, 4)]}}


def _to_mgmt(v: float) -> float:
    return v + 0.004                       # аддитивный мост ядра: упр. = движок + 0,4 п.п.


def _month_profit(m: str) -> float:
    y, k = periods.parse_month(m)
    return 10.0 + (y - 2024) * 2.0 + 0.5 * k


def bridged_store(root) -> Store:
    """Сочинённая история банка с мостом: месячный релиз (прибыль, ЧПД, стоимость риска), процентные активы
    по форме 0409101 и факты кварталов — прибыль ровно в `PROFIT_BRIDGE` раз больше суммы месяцев."""
    store = Store(root)
    prefix = nowcast.monthly_prefix()
    month = "2024M01"
    iea = 1000.0
    while month <= "2026M08":
        at = (periods.month_end(month) + timedelta(days=12)).isoformat() + "T07:00:00+00:00"
        for metric, value in (("np_m", _month_profit(month)), ("nii_m", 3.0 * _month_profit(month)), ("cor_m", 0.05)):
            store.upsert(f"{prefix}{metric}", [Point(month, value, at, "ok", "тест")])
        store.upsert("cbr.f101.iea", [Point(month, iea, at, "ok", "тест")])
        iea *= 1.01
        month = periods.shift_month(month, 1)
    q = "2024Q1"
    while q <= "2026Q2":
        at = (periods.quarter_end(q) + timedelta(days=45)).isoformat() + "T07:00:00+00:00"
        ras = sum(_month_profit(m) for m in periods.quarter_months(q))
        store.upsert("actual.ni_q", [Point(q, PROFIT_BRIDGE * ras, at, "ok", "тест")])
        store.upsert("actual.nim_q", [Point(q, 0.11, at, "ok", "тест")])
        store.upsert("actual.cor_q", [Point(q, 0.05 * COR_BRIDGE, at, "ok", "тест")])
        q = periods.shift_quarter(q, 1)
    return store


@pytest.fixture
def fixtures(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    return tmp_path


def test_combine_is_the_design_equation(fixtures):
    ras = {"version": nowcast.VERSION, "targets": {
        "ni_q": {"ras_estimate": 500.0, "bridge": 1.003, "ras_bridged": 501.5, "w": 0.7, "rel_std_error": 0.03},
        "nim_q": {"ras_bridged": None, "w": 0.0}, "cor_q": {"ras_bridged": None, "w": 0.0}}}
    out = nowcast.combine(ras, {"ni_q": 490.0, "nim_q_mgmt": 0.061, "cor_q_mgmt": 0.012})
    ni = out["ni_q"]
    assert ni["forecast"] == pytest.approx(490.0 + 0.7 * (501.5 - 490.0))
    assert ni["deviation"] == pytest.approx(ni["forecast"] - 490.0)
    assert ni["std_error"] == pytest.approx(ni["forecast"] * 0.03)
    assert ni["interval"] == pytest.approx([ni["forecast"] - ni["std_error"], ni["forecast"] + ni["std_error"]])
    assert out["nim_q"]["forecast"] == 0.061 and out["nim_q"]["w"] == 0.0 and out["nim_q"]["basis"] == "mgmt"
    assert out["cor_q"]["forecast"] == 0.012
    assert any(b["key"] == "model" for b in ni["benchmarks"])
    no_model = nowcast.combine(ras, {})
    assert no_model["ni_q"]["forecast"] == 501.5 and no_model["nim_q"]["forecast"] is None


def test_the_basis_of_a_target_is_a_label_of_the_book(fixtures, monkeypatch):
    """Базис цели — подпись книги: прибыль в определении эмитента — упр. базис; без подписи — код по умолчанию."""
    empty = {"targets": {k: {"ras_bridged": None, "w": 0.0} for k in nowcast.TARGET_KEYS}}
    assert nowcast.combine(empty, {"ni_q": 50.0})["ni_q"]["basis"] == "mgmt"
    monkeypatch.setattr(config, "book_value", lambda dotted, path=None: None)
    assert nowcast.combine(empty, {"ni_q": 50.0})["ni_q"]["basis"] == "ifrs"


def test_the_basis_comes_from_the_passed_book_not_from_the_repository(fixtures, monkeypatch, tmp_path):
    """Сборка выпуска считает на своей книге и передаёт её подписи целей: базис — из них, книга репозитория
    при этом не читается (выпуск на чужой книге печатает её базис, а не базис книги из `data/`). Подписи —
    узел книги `meta.labels.nowcast.targets` или список целей выпуска; книга без подписей — код по умолчанию."""
    empty = {"targets": {}}
    exp = {"ni_q": 50.0, "nim_q_mgmt": 0.1, "cor_q_mgmt": 0.05}
    assert nowcast.combine(empty, exp)["ni_q"]["basis"] == "mgmt"            # без подписей — книга репозитория

    def forbidden(dotted, path=None):
        raise AssertionError(f"книга репозитория прочитана: {dotted}")

    monkeypatch.setattr(config, "book_value", forbidden)
    node = {"ni_q": {"title": "Прибыль квартала", "basis": "ifrs"}, "nim_q": {"basis": "mgmt"}, "cor_q": {"basis": "mgmt"}}
    by = nowcast.combine(empty, exp, targets=node)
    assert {k: v["basis"] for k, v in by.items()} == {"ni_q": "ifrs", "nim_q": "mgmt", "cor_q": "mgmt"}
    assert by["ni_q"]["forecast"] == 50.0 and by["ni_q"]["w"] == 0.0         # счёт от подписей не зависит
    listed = [{"key": "ni_q", "title": "Прибыль квартала", "unit": "bn", "basis": "regulatory"},
              {"key": "cor_q", "title": "Стоимость риска", "unit": "share", "basis": "ifrs"}]
    by = nowcast.combine(empty, exp, targets=listed)                         # список целей выпуска — как у ядра
    assert {k: v["basis"] for k, v in by.items()} == {"ni_q": "regulatory", "nim_q": "mgmt", "cor_q": "ifrs"}
    assert nowcast.combine(empty, exp, targets={})["ni_q"]["basis"] == "ifrs"      # книга без подписей целей
    assert nowcast.target_basis("ni_q", node) == "ifrs" and nowcast.target_basis("nim_q", listed) == "mgmt"
    ras = nowcast.ras_inputs(Store(tmp_path / "empty"), period="2026Q3", today=date(2026, 10, 1), bridge={},
                             sigmas=SIGMAS, targets=node)
    assert ras["targets"]["ni_q"]["basis"] == "ifrs"
    from indicators import journal, outputs

    assert outputs.combine(empty, exp, targets=node)["ni_q"]["basis"] == "ifrs"    # точка входа ядра — та же функция
    assert journal.targets(node)["ni_q"] == {"title": "Прибыль квартала", "unit": "RUB bn", "basis": "ifrs"}
    assert journal.target_labels("не подписи") == {} and journal.target_labels([{"basis": "x"}, "y"]) == {}


def test_weight_from_measured_variances():
    assert nowcast.weight(0.065, 0.035) == pytest.approx(0.065 ** 2 / (0.065 ** 2 + 0.035 ** 2))
    assert nowcast.weight(None, 0.03) == 0.0 and nowcast.weight(0.05, 0.0) == 1.0


# ------------------------------------------------------------------ эмитент без моста прибыли

def test_without_a_profit_bridge_the_forecast_is_the_expectation(fixtures):
    """Факты говорят «моста прибыли нет»: оценки по РСБУ, моста и строк месяцев нет, прогноз — ожидание
    модели, вес 0; по истории мост не восстанавливается, хотя и прибыль банка, и факты кварталов в ней есть."""
    store = seeded_store(fixtures / "seed")
    bridge = config.facts_file("bridge_ras_ifrs", FIX / "facts")
    assert nowcast.bridge_declined(bridge, "2026Q3") and not nowcast.bridge_declined({}, "2026Q3")
    assert not nowcast.bridge_declined(BRIDGE, "2026Q3")
    h = nowcast.History.load(store)
    assert h.quarter_ras("2026Q2", None) and nowcast.history_bridge(h, "2026Q3", None)[0]     # история моста есть
    out = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 7), bridge=bridge)
    ni = out["targets"]["ni_q"]
    assert out["months"] == [] and out["months_known"] == 0
    assert (ni["ras_estimate"], ni["bridge"], ni["ras_bridged"], ni["w"]) == (None, None, None, 0.0)
    assert ni["basis"] == "mgmt" and "нет" in ni["equation"]
    by = nowcast.combine(out, {"ni_q": 55.0, "nim_q_mgmt": 0.112, "cor_q_mgmt": 0.049})
    for key, expected in (("ni_q", 55.0), ("nim_q", 0.112), ("cor_q", 0.049)):
        row = by[key]
        assert row["forecast"] == row["expectation"] == expected and row["w"] == 0.0, key
        assert row["ras_estimate"] is None and row["bridge"] is None and row["ras_bridged"] is None, key
        assert row["std_error"] is None and row["interval"] is None, key
    sig = retro.sigma_table(store, today=date(2026, 10, 7), bridge_facts=bridge)
    assert set(sig["ras"].values()) == {None} and sig["base"] is not None       # веса у оценки без моста нет


def test_nim_benchmark_from_the_form_102(fixtures):
    """Эталон `f102_nii`: ЧПД банка по форме × мост прошлого квартала в единицах ЧПМ — ЧПМ прошлого квартала
    × отношение ЧПД формы × поправка на число дней; неизвестные месяцы — профилем прошлого года."""
    store = seeded_store(fixtures / "seed")
    h = nowcast.History.load(store)
    assert h.nii_from_form and h.release_month("nii_m", "2026M08", None)[1] == "form102"
    got = nowcast.f102_nim(h, "2026Q3", "2026-10-07")
    july, august = (h.release_month("nii_m", m, None)[0] for m in ("2026M07", "2026M08"))
    september = august * h.release_month("nii_m", "2025M09", None)[0] / h.release_month("nii_m", "2025M08", None)[0]
    assert got["months_known"] == 2 and got["nii"] == pytest.approx(july + august + september)
    assert got["nii_prev"] == pytest.approx(nowcast.quarter_known(h, "nii_m", "2026Q2", None))
    expected = got["nim_prev"] * got["nii"] / got["nii_prev"] * 91 / 92
    assert got["iea_growth"] == 1.0 and got["value"] == pytest.approx(expected)
    assert 0.08 < got["value"] < 0.15 and got["nim_prev"] == h.mgmt_quarter("nim", "2026Q2", None)
    assert nowcast.f102_nim(h, "2026Q3", "2026-08-01") is None            # ЧПМ прошлого квартала ещё не вышла
    frozen = nowcast.f102_nim(h, "2026Q3", "2026-10-07", profile={"2025M08": 1.0, "2025M09": 2.0})
    assert frozen["nii"] == pytest.approx(july + august + august * 2.0)   # замороженный профиль важнее истории
    assert nowcast.f102_nim(nowcast.History.load(bridged_store(fixtures / "b")), "2026Q3", "2026-10-07") is None


def test_benchmarks_of_the_issuer(fixtures):
    """Эталоны журнала: модель, прошлый квартал, год назад × рост, гайденс роста года, консенсус (ручной ввод);
    у ЧПМ — оценка по форме 0409102; эталона «РСБУ × мост» нет."""
    store = seeded_store(fixtures / "seed")
    bridge = config.facts_file("bridge_ras_ifrs", FIX / "facts")
    today = date(2026, 10, 7)
    ras = nowcast.ras_inputs(store, period="2026Q3", today=today, bridge=bridge)
    exp = {"ni_q": 55.0, "nim_q_mgmt": 0.112, "cor_q_mgmt": 0.049}
    marks = collect.target_benchmarks(store, "2026Q3", today, ras, exp, bridge)
    h = nowcast.History.load(store)
    ni = marks["ni_q"]
    assert "ras_bridge" not in ni and "consensus" not in ni
    assert ni["model"] == 55.0 and ni["prev_quarter"] == h.quarter_ifrs("2026Q2", None)
    assert ni["same_quarter_last_year"] == h.quarter_ifrs("2025Q3", None)
    assert ni["yoy_growth"] == pytest.approx(ni["same_quarter_last_year"] * ni["prev_quarter"]
                                             / h.quarter_ifrs("2025Q2", None))
    assert ni["guidance"] == pytest.approx(ni["same_quarter_last_year"] * 1.20)       # рост прибыли года ≥ 20 %
    assert set(marks["nim_q"]) == {"prev_quarter", "same_quarter_last_year", "f102_nii", "model"}
    assert marks["nim_q"]["f102_nii"] == marks["nim_q_f102"]["value"]
    assert set(marks["cor_q"]) == {"prev_quarter", "same_quarter_last_year", "model"}  # гайденса-точки нет
    from indicators import record

    record.record_consensus(store, period="2026Q3", value="54,2", source="опрос аналитиков, тест")
    # запись несёт настоящий момент (UTC): читается на дату не раньше него, иначе тест живёт до конца своего дня
    from datetime import datetime, timezone
    seen = max(today, datetime.now(timezone.utc).date())
    assert collect.target_benchmarks(store, "2026Q3", seen, ras, exp, bridge)["ni_q"]["consensus"] == 54.2
    r = retro.retro(store, today=today, bridge_facts=bridge)
    assert r["main"] == "model" and r["by_horizon"]["T-90"]["main"] == "model"
    assert "ras_bridge" not in r["rmse"] and {"prev_quarter", "yoy_growth"} <= set(r["rmse"])
    assert collect.guidance_declined("nim", 2026) and not collect.guidance_declined("op_np_growth", 2026)


def _ytd(store, *points):
    for month, value, day in points:
        store.upsert("cbr.f102.ni_ytd", [Point(month, value, day + "T07:00:00+00:00")], basis="ras", unit="RUB bn")
    return nowcast.History.load(store)


def test_revised_year_to_date_moves_the_next_month(tmp_path):
    """Месяц по форме 0409102 — разность двух нарастающих итогов: пересмотр прошлого итога (и его запоздавший
    приход) меняет и следующий месяц — с момента пересмотра, не раньше."""
    h = _ytd(Store(tmp_path / "revised"), ("2026M01", 100.0, "2026-02-25"), ("2026M02", 220.0, "2026-03-25"),
             ("2026M01", 110.0, "2026-04-02"))
    assert h.month("2026M01", "2026-04-01")[0] == pytest.approx(100.0)
    assert h.month("2026M02", "2026-04-01")[0] == pytest.approx(120.0)     # до пересмотра января
    assert h.month("2026M01", None)[0] == pytest.approx(110.0)
    value, source, first = h.month("2026M02", None)
    assert value == pytest.approx(110.0) and source == "form102" and first.startswith("2026-03-25")
    assert h.quarter_ras("2026Q1", None) is None                            # марта нет — квартал не собран
    late = _ytd(Store(tmp_path / "late"), ("2026M02", 220.0, "2026-03-25"), ("2026M01", 100.0, "2026-04-02"))
    assert late.month("2026M02", "2026-04-01") is None                      # январь ещё неизвестен
    value, _, first = late.month("2026M02", None)
    assert value == pytest.approx(120.0) and first.startswith("2026-04-02")  # известен с прихода января
    same = _ytd(Store(tmp_path / "same"), ("2026M01", 100.0, "2026-02-25"), ("2026M02", 220.0, "2026-03-25"),
                ("2026M03", 330.0, "2026-04-25"), ("2026M02", 230.0, "2026-05-02"))
    assert [r[1] for r in same.months["2026M01"]] == [100.0]                # январь пересмотр февраля не трогает
    assert [r[1] for r in same.months["2026M02"]] == [120.0, 130.0]
    assert [r[1] for r in same.months["2026M03"]] == [110.0, 100.0]
    december = _ytd(Store(tmp_path / "year"), ("2025M12", 1500.0, "2026-01-25"), ("2026M01", 100.0, "2026-02-25"),
                    ("2025M12", 1510.0, "2026-03-02"))
    assert [r[1] for r in december.months["2026M01"]] == [100.0]            # январь — сам итог, декабрь ни при чём
    # Два соседних итога пересмотрены в один момент (формы одной перекачки): у февраля на этот момент одно
    # значение — разность новых итогов, а не нового января и прежнего февраля (200 − 90 = 110 было бы больше
    # верных 105 и победило бы при выборе последней версии).
    together = _ytd(Store(tmp_path / "together"), ("2026M01", 100.0, "2026-02-25"), ("2026M02", 200.0, "2026-03-25"),
                    ("2026M01", 90.0, "2026-04-02"), ("2026M02", 195.0, "2026-04-02"))
    assert [r[1] for r in together.months["2026M01"]] == [100.0, 90.0]
    assert [r[1] for r in together.months["2026M02"]] == [100.0, 105.0]
    assert together.month("2026M02", None)[0] == pytest.approx(105.0)
    assert together.month("2026M02", "2026-04-01")[0] == pytest.approx(100.0)


def test_fact_of_a_quarter_is_read_as_of_the_date(tmp_path):
    """У факта квартала две версии: на дату между ними история отвечает первой — как хранилище, — а дата
    отчёта остаётся днём первого появления; без даты — последняя версия."""
    store = Store(tmp_path)
    for series, first, second in (("actual.ni_q", 100.0, 120.0), ("actual.nim_q", 0.060, 0.062)):
        store.upsert(series, [Point("2026Q1", first, "2026-04-30T07:00:00+00:00")])
        store.upsert(series, [Point("2026Q1", second, "2026-06-30T07:00:00+00:00", "manual")])
    h = nowcast.History.load(store)
    assert h.quarter_ifrs("2026Q1", "2026-04-29") is None
    assert h.quarter_ifrs("2026Q1", "2026-05-01") == store.value_as_of("actual.ni_q", "2026Q1", "2026-05-01") == 100.0
    assert h.quarter_ifrs("2026Q1", "2026-06-30") == h.quarter_ifrs("2026Q1", None) == 120.0
    assert h.report_date("2026Q1") == "2026-04-30" and h.ifrs["2026Q1"][1] == 120.0
    assert h.mgmt_quarter("nim", "2026Q1", "2026-05-01") == 0.060
    assert h.mgmt_quarter("nim", "2026Q1", None) == 0.062 and h.mgmt_quarter("nim", "2026Q1", "2026-04-01") is None
    manual = nowcast.History(store=store)                                   # история без версий — последнее значение
    manual.ifrs = {"2026Q1": ("2026-04-30T07:00:00+00:00", 120.0)}
    assert manual.quarter_ifrs("2026Q1", "2026-05-01") == 120.0


def test_horizons():
    rep = date(2026, 10, 28)
    assert nowcast.horizon_for(date(2026, 7, 30), rep) == "T-90"
    assert nowcast.horizon_for(date(2026, 9, 28), rep) == "T-30"
    assert nowcast.horizon_for(date(2026, 9, 27), rep) == "T-90"
    assert nowcast.horizon_for(date(2026, 10, 28), rep) is None
    assert nowcast.horizon_for(date(2026, 7, 29), rep) is None




# ------------------------------------------------------------------ банк с мостом: общая механика

def test_ras_inputs_with_a_bridge(fixtures):
    store = bridged_store(fixtures / "b")
    out = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge=BRIDGE, sigmas=SIGMAS)
    months = {m["month"]: m for m in out["months"]}
    assert months["2026M07"]["status"] == "known" and months["2026M07"]["ni"] == pytest.approx(_month_profit("2026M07"))
    assert months["2026M08"]["nii"] == pytest.approx(3.0 * _month_profit("2026M08"))
    sep = months["2026M09"]
    assert sep["status"] == "estimated" and sep["source"] == "profile"
    # профиль: август этого года × (сентябрь / август прошлого года)
    ratio = _month_profit("2025M09") / _month_profit("2025M08")
    assert sep["ni"] == pytest.approx(_month_profit("2026M08") * ratio)
    ni = out["targets"]["ni_q"]
    assert out["months_known"] == 2 and ni["bridge"] == PROFIT_BRIDGE and ni["bridge_source"].startswith("facts")
    total = _month_profit("2026M07") + _month_profit("2026M08") + sep["ni"]
    assert ni["ras_bridged"] == pytest.approx(total * PROFIT_BRIDGE)
    assert ni["w"] == pytest.approx(nowcast.weight(0.065, 0.04))
    assert ni["rel_std_error"] == pytest.approx(math.sqrt(ni["w"]) * 0.04)
    # без файла фактов мост берётся по истории: среднее отношение того же квартала прошлых лет
    hist = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge={}, sigmas=SIGMAS)
    assert hist["targets"]["ni_q"]["bridge_source"] == "history"
    assert hist["targets"]["ni_q"]["bridge"] == pytest.approx(PROFIT_BRIDGE)


def test_frozen_values_win_over_recomputed(fixtures):
    store = bridged_store(fixtures / "b")
    frozen = {"bridge": 1.1, "profile": {"2025M08": 100.0, "2025M09": 110.0},
              "sigmas": {"ras": {"2": 0.05}, "base": 0.05}}
    out = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge={}, frozen=frozen)
    sep = [m for m in out["months"] if m["month"] == "2026M09"][0]
    assert sep["ni"] == pytest.approx(_month_profit("2026M08") * 1.1)
    assert out["profile"] == {"2025M08": 100.0, "2025M09": 110.0}
    assert out["targets"]["ni_q"]["bridge"] == 1.1 and out["targets"]["ni_q"]["w"] == pytest.approx(0.5)


def test_form102_month_counts_as_known(fixtures):
    store = bridged_store(fixtures / "b")
    # сентябрь по форме 0409102 (нарастающим) появился раньше релиза
    store.upsert("cbr.f102.ni_ytd", [Point("2026M08", 200.0, "2026-09-25T06:00:00+00:00"),
                                     Point("2026M09", 230.0, "2026-10-01T06:00:00+00:00")])
    out = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge=BRIDGE, sigmas=SIGMAS)
    sep = [m for m in out["months"] if m["month"] == "2026M09"][0]
    assert sep["status"] == "known" and sep["source"] == "form102" and sep["ni"] == pytest.approx(30.0)
    assert out["months_known"] == 3
    aug = [m for m in out["months"] if m["month"] == "2026M08"][0]
    assert aug["source"] == "release"                                   # релиз важнее формы


def test_nim_and_cor_through_the_bridges(fixtures):
    store = bridged_store(fixtures / "b")
    out = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge=BRIDGE, sigmas=NIM_SIGMAS,
                             to_mgmt_nim=_to_mgmt)
    nim = out["targets"]["nim_q"]
    assert nim["bridge"] == pytest.approx(NII_BRIDGE / IEA_BRIDGE) and nim["months_known"] == 2
    assert nim["ras_estimate"] == pytest.approx(nim["nii_ras"] * 365 / 92 / nim["iea_ras"])
    assert nim["ras_bridged"] == pytest.approx(_to_mgmt(nim["ras_estimate"] * nim["bridge"]))
    assert nim["w"] == pytest.approx(nowcast.weight(0.002, 0.0013)) and nim["std_error"] is not None
    assert [m["status"] for m in nim["iea_months"]] == ["known", "estimated"]      # конец квартала ещё не вышел
    no_core = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge=BRIDGE, sigmas=NIM_SIGMAS)
    assert no_core["targets"]["nim_q"]["ras_bridged"] is None and no_core["targets"]["nim_q"]["equation"] == nowcast.NO_MGMT
    frozen = {"nim": {"bridge": 1.0, "basis": "mgmt"}}
    fz = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1), bridge=BRIDGE, sigmas=NIM_SIGMAS,
                            frozen=frozen)["targets"]["nim_q"]
    assert fz["bridge"] == 1.0 and fz["ras_bridged"] == pytest.approx(fz["ras_estimate"])   # упр. базис — без моста ядра
    cor = out["targets"]["cor_q"]
    assert cor["ras_estimate"] == pytest.approx(0.05) and cor["ras_bridged"] == pytest.approx(0.05 * COR_BRIDGE)
    bare = nowcast.ras_inputs(store, period="2026Q3", today=date(2026, 10, 1),
                              bridge={**BRIDGE, "cor": {"v": None, "calc": "нет данных"}}, sigmas=NIM_SIGMAS)
    assert bare["targets"]["cor_q"]["ras_estimate"] is None and bare["targets"]["cor_q"]["equation"] == nowcast.NO_BRIDGE["cor_q"]


def test_retro_and_sigmas_with_a_bridge(fixtures, monkeypatch):
    store = bridged_store(fixtures / "b")
    today = date(2026, 10, 1)
    r = retro.retro(store, today=today, bridge_facts=BRIDGE)
    assert r["horizon"] == "T-30" and set(r["by_horizon"]) == {"T-30", "T-90"}
    for hz in ("T-30", "T-90"):
        block = r["by_horizon"][hz]
        assert block["periods"] and all(math.isfinite(v) for v in block["rmse"].values())
        assert block["rmse"]["ras_bridge"] < 0.05                     # мост точен по построению истории
    # Главный эталон блока — настройка: он назван словами и сосчитан и тогда, когда истории в ретро у него нет
    # («ожидание модели» копит её в журнале прогнозов); ошибки у эталона без истории нет — не ноль, а нет.
    for main in ("model", "ras_bridge"):
        monkeypatch.setattr(retro, "main_benchmark", lambda main=main: main)
        got = retro.retro(store, today=today, bridge_facts=BRIDGE)
        for block in (got, *got["by_horizon"].values()):
            assert block["main"] == main and block["titles"][main] == retro.BENCHMARK_TITLES[main]
            assert block["n"][main] == sum(1 for p in block["periods"] if main in p["benchmarks"])
            assert set(block["rmse"]) == set(block["bias"]) == {k for k, n in block["n"].items() if n}
        assert (got["n"][main] == 0) == (main == "model")
    s = retro.sigma_table(store, today=today, bridge_facts=BRIDGE)
    assert s["ras"]["3"] == pytest.approx(0.0, abs=1e-9) and s["ras"]["0"] > s["ras"]["3"] and s["n"]["ras"]["3"] >= 4
    assert s["base"] == pytest.approx(r["by_horizon"]["T-90"]["rmse"]["yoy_growth"], rel=1e-3)   # тот же набор знаний
    h = nowcast.History.load(store)
    q, report = "2026Q2", h.report_date("2026Q2")
    assert retro.horizon_date(h, q, report, 90) == max(
        (date.fromisoformat(report) - timedelta(days=90)).isoformat(), h.report_date("2026Q1"))
    marks = retro.benchmarks_at(h, store, q, h.report_date("2026Q1"))
    assert marks["prev_quarter"] == h.ifrs["2026Q1"][1]                # прошлый квартал известен со дня отчёта
    early = retro.benchmarks_at(h, store, q, "2026-05-01")
    assert early["prev_quarter"] == h.ifrs["2025Q4"][1]                # до выхода отчёта — позапрошлый
    sig = retro.ratio_sigma_table(store, bridge=BRIDGE, to_mgmt_nim=_to_mgmt, today=today)
    assert sig["cor"]["ras"]["3"] == pytest.approx(0.0, abs=1e-9) and sig["nim"]["n"]["ras"]["3"] >= 1
    assert sig["nim"]["bridge_window"] == {"nii": 2, "iea": 4}


def test_mgmt_retro(fixtures):
    store = seeded_store(fixtures / "seed")
    out = retro.mgmt_retro(store, "nim_q")
    assert out["periods"] and out["rmse"]["prev_quarter"] < 0.02
    assert retro.mgmt_retro(Store(fixtures / "empty"), "cor_q") == {"periods": [], "rmse": {}}


def test_iea_average_from_an_older_form():
    store = Store.__new__(Store)
    h = nowcast.History(store=store)
    h.iea = {"2026M04": [("2026-05-26T07:00:00+00:00", 100.0, "form101")],
             "2026M05": [("2026-06-26T07:00:00+00:00", 101.0, "form101")]}
    got = nowcast.iea_average(h, "2026Q3", "2026-07-01")
    assert [m["status"] for m in got["months"]] == ["estimated", "estimated"]
    g = (101.0 / 100.0) - 1
    assert got["months"][0]["value"] == pytest.approx(101.0 * (1 + g))
    assert got["months"][1]["value"] == pytest.approx(101.0 * (1 + g) ** 4)
    assert nowcast.iea_average(h, "2027Q1", "2026-07-01") is None       # последний конец месяца слишком стар
