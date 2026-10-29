# -*- coding: utf-8 -*-
"""Перезаякоривание на форме панели (`ops/tools/reanchor.py`, М§15.2 пп. 9–11): квартальный календарь дивидендов,
нормативы группы слотами и оценкой, постоянные прочие активы, рост по капиталу.

Фикстура — `tests/fixtures/core_t` (форма панели: 12 книг прямыми узлами, решения о дивиденде по кварталам
прибыли, затравка реестра с датами, рост, ограниченный капиталом). Быстрые тесты (метка `tact`) — чистые
функции без прогона сетки: оси по ключам ближнего пути ЧПМ, запись траектории между проходами калибровки,
перенос решений в историю дивидендов и затравку реестра, проверка файла формы. Тесты с прогоном сетки —
`ci_only`: ожидаемый отчёт несёт решения клеток закрываемого квартала и суммы к выплате по периодам; каждая
клетка на своём пути сохраняет стоимость — и через квартал, где решение за третий квартал прибыли объявлено,
но не выплачено и не вычтено из регуляторного капитала; смена года якоря сдвигает множитель RWA режима вместе
с прочими кризисными траекториями; отчёт с оценкой нормативов даёт факты с пометкой оценки, а замена оценки
фактом формы — кандидата на том же якоре; непредставимый календарь — отказ с названной причиной.

Навёрстывание роста у фикстуры включено (25 % разрыва в год), у книги эмитента — ноль: тесты инварианта
«механика ≈ 0» идут на фикстуре с навёрстыванием, равным нулю (память о разрыве с потенциальным путём факты
якоря не несут), отдельный тест проверяет, что при включённом навёрстывании инструмент это называет.

Даты тестов — от периодов книги фикстуры, не от «сегодня».
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from types import SimpleNamespace

import pytest

from model.book import anchor_facts, book_from_dict
from model.dividends import closed_through
from model.grid import run_grid
from model.timeline import make_timeline, parse_period
from tests.support_core_t import FIXTURE_T_BOOK, FIXTURE_T_FACTS, put, t_dict, t_facts
from tests.test_reanchor import R, scene_of

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

NO_CATCH_UP = (("capital.growth_constraint.catch_up_rate", 0.0),)
CELLS = (("N", "soft", "schedule"), ("H", "downturn", "strict"), ("M", "norm", "mid"))
LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")


def t_book(changes: tuple = NO_CATCH_UP):
    data = t_dict()
    for path, value in changes:
        put(data, path, value)
    return book_from_dict(data, facts=t_facts())


def walk(steps: int = 1, changes: tuple = NO_CATCH_UP) -> tuple[SimpleNamespace, ...]:
    """Сухие прогоны квартал за кварталом: каждый следующий — от кандидата на ожидаемом отчёте."""
    book, facts, out = t_book(changes), t_facts(), []
    for _ in range(steps):
        s = scene_of(book, facts)
        out.append(s)
        book, facts = s.cand.book, s.cand.facts
    return tuple(out)


chain = lru_cache(maxsize=None)(walk)        # с памятью — для правок, которые можно хешировать


def first() -> SimpleNamespace:
    return chain(1)[0]


def changed(report: dict, **changes) -> dict:
    """Копия отчёта с правками по точечным путям (`None` — убрать ключ)."""
    report = copy.deepcopy(report)
    for path, value in changes.items():
        node, parts = report, path.split(".")
        for part in parts[:-1]:
            node = node[part]
        if value is None:
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    return report


# ------------------------------------------------------------------ чистые функции (такт)


@tact
def test_axes_on_the_near_path_follow_its_keys():
    """Ось, которая сдвигает ключи ближнего пути ЧПМ нескольких лет, получает ключи тех же лет новой траектории:
    ключ закрытого квартала уходит, год, записанный теперь кварталами, входит всеми ключами; ось без ключей
    снимается с предупреждением; прочие оси не трогаются."""
    near = "regimes.near_nim_shift"
    axis = {"name": "сход", "kind": "shift", "paths": [f"{near}.2027", f"{near}.2027Q1", f"{near}.2027Q2", f"{near}.2028"],
            "low": -0.002, "high": 0.002}
    other = {"name": "прочая", "kind": "value", "paths": ["valuation.erp"], "low": 0.04, "high": 0.06}
    X = {"regimes": {"near_nim_shift": {}},
         "valuation": {"uncertainty": {"axes": [axis, other], "off_band_axes": []}, "reverse_dcf": {"axes": []}}}
    warnings: list[str] = []
    R.set_near(X, {"2027Q2": 0.001, "2027Q3": 0.002, "2028Q1": 0.0, "2028Q2": 0.0, "2028Q3": 0.0, "2028Q4": 0.0,
                   "2028": 0.0, "2029": 0.0, "LT": 0.0}, warnings)
    assert set(axis["paths"]) == {f"{near}.{k}" for k in ("2027Q2", "2027Q3", "2028Q1", "2028Q2", "2028Q3", "2028Q4", "2028")}
    assert other["paths"] == ["valuation.erp"] and not warnings
    same = list(axis["paths"])
    R.set_near(X, dict(reversed(list(X["regimes"]["near_nim_shift"].items()))), warnings)
    assert axis["paths"] == same, "те же ключи в другом порядке — пути оси не переписываются"
    R.set_near(X, {"2029Q1": 0.0, "2029": 0.0, "LT": 0.0}, warnings)
    assert [a["name"] for a in X["valuation"]["uncertainty"]["axes"]] == ["прочая"]
    assert len(warnings) == 1 and "ось снята" in warnings[0] and "сход" in warnings[0]


@tact
def test_the_detail_of_the_near_trajectory_does_not_shrink_between_passes():
    """Год, записанный кварталами на прошлом проходе калибровки, остаётся записанным кварталами: иначе запись
    прыгает между двумя видами, и проходы не сходятся (у книги, где капитал связывает рост)."""
    periods = [f"{y}Q{q}" for y in range(2027, 2033) for q in (1, 2, 3, 4)][1:]
    flat = [0.001] * len(periods)
    plain = R.near_trajectory({"LT": 0.0}, periods, flat, 2032)
    assert "2028Q4" in plain and "2029Q1" not in plain and "2029" in plain
    kept = R.near_trajectory({"LT": 0.0}, periods, flat, 2032, 2030)
    assert all(f"{y}Q{q}" in kept for y in (2029, 2030) for q in (1, 2, 3, 4)) and "2031Q1" not in kept
    assert not any(k.startswith("2032Q") for k in R.near_trajectory({"LT": 0.0}, periods, flat, 2032, 2040))


@tact
def test_decisions_of_the_closed_quarter_become_history_rows_and_the_seed_keeps_what_is_ahead():
    """М§15.2 п. 9 на словарях фактов: решение отчёта — строка истории с днём решения (она закрывает квартал
    прибыли); строка с тем же DPS сохраняет свои источники; запись реестра остаётся в затравке, пока её экс-дата
    впереди или её сумма стоит в списке «объявлено, не выплачено»; решение с датой реестра после якоря без
    записи получает запись."""
    facts = t_facts()
    files = copy.deepcopy(dict(facts.files))
    book = t_book()
    old = anchor_facts(facts, book.get("nii.books"))
    report = {"period": "2026Q3", "balance": {"dividends_payable_declared": [{"period": "2026Q3", "amount": 11.5}]},
              "dividend_decisions": [
                  {"period": "2026Q1", "dps": 4.6, "decided_date": "2026-07-30", "record_date": "2026-08-10"},
                  {"period": "2026Q3", "dps": 4.5, "decided_date": "2026-09-28", "record_date": "2026-10-09",
                   "pay_date": "2026-10-23"}]}
    before = copy.deepcopy(next(r for r in files["dividends"]["history"] if r["period"] == "2026Q1"))
    R._carry_dividends(files, book, old, report, "reanchor: тест")
    history = {r["period"]: r for r in files["dividends"]["history"]}
    assert history["2026Q1"]["dps"] == before["dps"] and history["2026Q1"]["sources"] == before["sources"]
    new = history["2026Q3"]
    assert (new["year"], new["dps"]["v"], new["decided_date"], new["record_date"]) == (2026, 4.5, "2026-09-28", "2026-10-09")
    assert new["pool_declared"]["v"] == pytest.approx(4.5 * old.n_iss / 1000)
    assert [r["period"] for r in files["dividends"]["history"]] == sorted(history, key=R.pindex)
    seed = {r["period"]: r for r in files["dividends"]["register_seed"]}
    assert set(seed) == {"2026Q2", "2026Q3"}, "запись за 2026Q1 выпала: экс-дата не позже новой даты фактов"
    assert seed["2026Q3"]["status"] == "declared" and seed["2026Q3"]["ex_date"] == "2026-10-09"
    assert files["dividends"]["as_of"] == "2026-09-30"


@tact
def test_the_form_file_is_checked_before_anything_is_computed():
    """Файл замены оценки фактом формы: якорь книги, состав, доли — долями; отказ называет причину."""
    book, facts = t_book(), t_facts()
    form = {"schema": R.CAPITAL_FORM, "period": "2026Q2", "n20_0": 0.131, "n1_1_bank": 0.095, "basel_cet1": 560.0,
            "basel_rwa": 5300.0, "bank_base_capital": 495.0}
    R.check_form(book, facts, form)
    for change, fragment in (({"period": "2026Q3"}, "без его смены"), ({"n20_0": 13.1}, "доля единицы"),
                             ({"extra": 1}, "незнакомые ключи extra"), ({"basel_rwa": None}, "нет ключей basel_rwa"),
                             ({"schema": "чужая/1"}, "schema"), ({"as_of": "2026-07-01"}, "не конец квартала"),
                             ({"n20_pre_dividend": 1}, "true или false"), ({"bank_base_capital": 0.0}, "положительное")):
        bad = {k: v for k, v in {**form, **change}.items() if v is not None}
        with pytest.raises(R.ReportError) as exc:
            R.check_form(book, facts, bad)
        assert fragment in str(exc.value), str(exc.value)
    swapped = R.facts_with_form(facts, {**form, "t2": 125.0})
    af = anchor_facts(swapped, book.get("nii.books"))
    assert (af.n20, af.n11_bank, af.basel_rwa, af.bank_base_capital, af.t2) == (0.131, 0.095, 5300.0, 495.0, 125.0)
    assert af.estimated == () and "estimate" not in swapped.files["capital"]["n20_0"]
    assert anchor_facts(facts, book.get("nii.books")).n20 != 0.131, "прежние факты не тронуты"


@tact
def test_the_dividend_section_of_the_candidate_report_reads_as_a_table():
    lines = R.dividend_lines({"p_last": ("2026Q1", "2026Q3"), "payable": 16.5,
                              "closed": [{"period": "2026Q3", "dps": 4.54, "decided_date": "2026-12-31"}],
                              "queue": [{"period": "2026Q3", "amount": 11.5, "pay": "2027Q1", "reg": "2027Q1"},
                                        {"period": "2026Q2", "amount": 1.0, "pay": "2027Q1", "reg": None}],
                              "seed": ["2026Q3"], "dropped": ["2026Q2"], "added": []})
    text = "\n".join(lines)
    for fragment in ("## Дивиденды по периодам", "2026Q1 → 2026Q3", "| 2026Q3 | 4.5400 | 2026-12-31 |",
                     "12.500 млрд ₽ из остатка «дивиденды к выплате» 16.500", "| 2026Q3 | 11.500 | 2027Q1 | 2027Q1 |",
                     "| 2026Q2 | 1.000 | 2027Q1 | уже вычтен |", "выпали (экс-дата не позже новой даты фактов): 2026Q2"):
        assert fragment in text, fragment
    assert R.dividend_lines(None) == []


# ------------------------------------------------------------------ ожидаемый отчёт и факты кандидата


@ci_only
def test_the_expected_report_of_the_quarterly_form_names_dividends_by_period():
    """Ожидаемый отчёт несёт решения клеток закрываемого квартала (у записи реестра — её день решения и даты),
    список «объявлено, не выплачено» по периодам и постоянную часть прочих активов; года дивиденда в нём нет."""
    s = first()
    rep = s.expected
    R.check_report(s.book, s.facts, rep)
    seed = {r["period"]: r for r in s.facts.file("dividends")["register_seed"]}
    assert rep["dividend_decisions"] == [{"period": "2026Q1", "dps": seed["2026Q1"]["dps"]["v"],
                                          "decided_date": seed["2026Q1"]["decided_date"],
                                          "record_date": seed["2026Q1"]["record_date"],
                                          "pay_date": seed["2026Q1"]["pay_date"]}]
    assert rep["balance"]["dividends_payable_declared"] == [] and "dividends_payable_year" not in rep["balance"]
    assert rep["balance"]["other_assets_fixed"] == s.facts.need("balance", "other_assets_fixed")
    assert rep["capital"]["n20_pre_dividend"] is False and "estimated" not in rep["capital"]
    assert rep["balance"]["dividends_payable"] == pytest.approx(s.facts.need("balance", "dividends_payable")), \
        "решение записи выплачено в том же квартале: остаток — постоянное обязательство"
    assert json.loads(json.dumps(rep)) == rep


@ci_only
def test_the_decision_made_in_the_closed_quarter_closes_its_profit_quarter():
    """М§15.2 п. 9: строка истории с днём решения не позже новой даты фактов закрывает свой квартал прибыли —
    на новом якоре его дивиденд в капитале, в клетке его нет; запись реестра с прошедшей экс-датой из затравки
    выпадает, запись открытого квартала остаётся."""
    s = first()
    old_tl, new_tl = make_timeline(s.book), make_timeline(s.cand.book)
    was = closed_through(s.facts, old_tl, s.book.get("meta.facts_date"))
    now = closed_through(s.cand.facts, new_tl, s.cand.book.get("meta.facts_date"))
    assert (old_tl.period(was), new_tl.period(now)) == ("2025Q4", "2026Q1") == s.cand.derived["dividends"]["p_last"]
    div = s.cand.derived["dividends"]
    assert [r["period"] for r in div["closed"]] == ["2026Q1"] and div["queue"] == []
    assert (div["seed"], div["dropped"], div["added"]) == (["2026Q2"], ["2026Q1"], [])
    new = s.run_e.cells[0]
    assert "2026Q1" not in new.dps_q and "2026Q2" in new.dps_q, "закрытый квартал прибыли клетка больше не решает"
    old = s.run_plus.cell(*new.key)
    assert new.dps[2026] == pytest.approx(old.dps[2026], rel=1e-3), "годовой дивиденд — тот же: закрытый квартал — строкой истории"
    files = s.cand.facts.files
    assert files["balance"]["dividends_payable_declared"] == []
    assert files["balance"]["other_assets_fixed"]["v"] == s.expected["balance"]["other_assets_fixed"]
    assert files["nii_books"].get("rates_carry_residual", True) is True


@ci_only
def test_the_candidate_facts_keep_the_shape_the_core_reads():
    """Прямые книги баланса, части книги бумаг, базы объёма пяти концов кварталов, история мостов: ядро читает из
    фактов кандидата то же состояние, что несёт отчёт, и считает на них проверки."""
    s = first()
    books = s.book.get("nii.books")
    af = anchor_facts(s.cand.facts, books)
    rep = s.expected
    for b in books:
        assert af.balances[b] == pytest.approx(rep["balance"]["books"][b], abs=1e-6), b
        assert s.cand.facts.files["balance"]["books"][b]["v"] == pytest.approx(rep["balance"]["books"][b], abs=1e-6)
    assert af.fv_book is None and af.fv_loans == 0.0, "кредиты по справедливой стоимости — справка: ядро их не вычитает"
    assert af.fvoci == pytest.approx(rep["balance"]["fvoci"], abs=1e-5) and af.fvtpl_bonds == rep["balance"]["fvtpl_bonds"]
    history = s.cand.facts.periods("balance", "history")
    loans, funds = (sum(rep["balance"]["books"][b] for b in names)
                    for names in (LOANS, ("retail_current", "retail_term", "corp_funds")))
    row = history[s.period]
    assert row["loans"]["v"] == pytest.approx(loans, abs=1e-5) and row["funds"]["v"] == pytest.approx(funds, abs=1e-5)
    assert row["loans_ac_gross"]["v"] == pytest.approx(loans, abs=1e-5), "без книги кредитов по СС кредиты АС — сумма книг"
    ends = sorted(history, key=R.pindex)[-5:]
    assert ends[-1] == s.period and all(history[p]["loans"]["v"] is not None for p in ends), "пять концов для роста объёма г/г"
    eng = R.engine_ratios(s.book, s.facts, rep)
    assert eng["loans_ac_avg"] == pytest.approx(
        (loans + sum(anchor_facts(s.facts, books).balances[b] for b in LOANS)) / 2), "CoR — к сумме кредитных книг"
    checks = R.core_checks(s.run_e, s.v)
    assert checks["error"] is None and checks["invariants"] == []
    assert R.compare_facts(s.book, s.cand.facts, R.facts_after(s.book, s.facts, rep)) == []
    more = changed(rep, **{"balance.other_assets_fixed": rep["balance"]["other_assets_fixed"] - 5.0})
    assert [k for k, _, _ in R.compare_facts(s.book, s.cand.facts, R.facts_after(s.book, s.facts, more))] == ["other_assets_fixed"]


# ------------------------------------------------------------------ инвариант: механика ≈ 0


@ci_only
def test_every_cell_of_the_quarterly_form_keeps_its_value():
    """Каждая клетка, перезаякоренная на своём пути, сохраняет стоимость — и клетки, где капитал урезал рост в
    закрываемом квартале (навёрстывания нет — памяти о разрыве нет): оговорки об урезанных клетках нет."""
    s = first()
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    assert len(mech["rows"]) == len(s.run_plus.cells) and mech["rearmed"] == []
    assert mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL, mech["worst"]
    cut = [c.key for c in s.run_plus.cells if "growth_cut" in c.flags]
    assert cut, "на фикстуре капитал урезает рост — инвариант проверен и на таких клетках"
    assert abs(mech["headline"]["point"] / s.run_plus.point - 1) <= R.MECHANICS_TOL
    assert s.run_plus.divisor != s.run_plus.shares_out, "точка строки «механика» — на делителе книги (М§8.4)"
    step = float(s.book.get("valuation.headline.print_step"))
    assert abs(s.run_e.point - s.run_plus.point) <= step
    assert not any("не сошлась" in w for w in s.cand.warnings)


@ci_only
def test_a_chain_of_quarters_carries_declared_dividends_and_the_year_change():
    """Четыре отчёта подряд на ожидаемых отчётах. Якорь на четвёртом квартале: решение за третий квартал
    прибыли объявлено, не выплачено и стоит в регуляторном капитале — отчёт несёт его суммой по периоду, клетка
    выплачивает и вычитает его в свои кварталы, поправки нормативов не двигаются больше постоянной части остатка.
    Смена года якоря: множитель RWA режима сдвинут вместе с годом шока, клетки кризиса «перезаряжены» и в допуск
    не входят, прочие — в допуске. Следующий квартал: решение за четвёртый квартал прибыли закрыто строкой
    истории с днём решения — концом квартала."""
    s1, s2, s3, s4 = chain(4)
    # --- якорь на четвёртом квартале
    rep = s2.expected
    assert [d["period"] for d in rep["dividend_decisions"]] == ["2026Q2", "2026Q3"]
    by_record, by_model = rep["dividend_decisions"]
    assert by_record["decided_date"] == "2026-10-01" and by_model["decided_date"] == R.period_end(s2.period).isoformat()
    assert "record_date" not in by_model, "решение модели: дат реестра нет, кварталы выплаты и вычета — по карте лагов"
    (item,) = rep["balance"]["dividends_payable_declared"]
    probs = s2.run_plus.layers["analytical"].prob
    mean = sum(p * next(d.div for d in s2.run_plus.cell(*k).decisions if d.period == "2026Q3") for k, p in probs.items())
    assert item == {"period": "2026Q3", "amount": pytest.approx(mean, abs=1e-6)} and rep["capital"]["n20_pre_dividend"]
    assert rep["balance"]["dividends_payable"] == pytest.approx(item["amount"] + s2.facts.need("balance", "dividends_payable"))
    div = s2.cand.derived["dividends"]
    assert div["p_last"] == ("2026Q1", "2026Q3") and [r["period"] for r in div["closed"]] == ["2026Q2", "2026Q3"]
    assert div["queue"] == [{"period": "2026Q3", "amount": pytest.approx(item["amount"]), "pay": "2027Q1", "reg": "2027Q1"}]
    assert s2.cand.derived["dpreg_anchor"] == pytest.approx(item["amount"])
    anchor = s2.run_e.cells[0].quarters
    assert anchor["dpreg"][0] == pytest.approx(item["amount"]) and anchor["dpreg"][1] == 0.0
    assert anchor["pay"][1] == pytest.approx(item["amount"]), "объявленное выплачено в свой квартал"
    row = next(r for r in s2.cand.facts.file("dividends")["history"] if r["period"] == "2026Q3")
    assert row["dps"]["v"] == by_model["dps"] and row["pool_declared"]["v"] == pytest.approx(
        by_model["dps"] * anchor_facts(s2.facts, s2.book.get("nii.books")).n_iss / 1000)
    assert s2.cand.derived["anchor_row"]["n20"] == pytest.approx(rep["capital"]["n20_0"], abs=1e-8)
    assert s2.cand.derived["anchor_row"]["n11"] == pytest.approx(rep["capital"]["n1_1_bank"], abs=1e-8)
    mech = R.cell_mechanics(s2.book, s2.facts, s2.run_plus, s2.obs, s2.v, cells=CELLS)
    assert mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 2, mech["worst"]
    # --- смена года якоря
    assert s3.cand.derived["year_shift"] == 1 and s3.expected["dividend_decisions"] == []
    was, now = s3.book.source["regimes"]["crisis"], s3.cand.data["regimes"]["crisis"]
    assert now["rwa_density_mult"] == {R._shift_key(k, 1): (v + 1 if k == "LT_from" else v)
                                       for k, v in was["rwa_density_mult"].items()}
    shock = parse_period(now["one_off_loss"]["period"])[0]
    assert min(now["rwa_density_mult"], key=lambda k: now["rwa_density_mult"][k] if k != "LT_from" else 9.0) == str(shock)
    paths = [p for a in s3.cand.data["valuation"]["uncertainty"]["axes"] for p in a["paths"]]
    assert f"regimes.crisis.rwa_density_mult.{shock}" in paths and f"regimes.crisis.rwa_density_mult.{shock - 1}" not in paths
    mech = R.cell_mechanics(s3.book, s3.facts, s3.run_plus, s3.obs, s3.v, cells=CELLS + (("M", "crisis", "strict"),))
    assert mech["rearmed"] == ["crisis"] and mech["rows"][-1]["rearmed"]
    assert mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 2, mech["worst"]
    # --- решение за четвёртый квартал прибыли
    (decision,) = s4.expected["dividend_decisions"]
    assert (decision["period"], decision["decided_date"]) == ("2026Q4", R.period_end(s4.period).isoformat())
    assert s4.cand.derived["dividends"]["p_last"] == ("2026Q3", "2026Q4")
    mech = R.cell_mechanics(s4.book, s4.facts, s4.run_plus, s4.obs, s4.v, cells=CELLS + (("M", "crisis", "strict"),))
    assert mech["ok"] and mech["rearmed"] == [] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL, mech["worst"]
    for s in (s1, s2, s3, s4):
        assert not any("не сошлась" in w for w in s.cand.warnings), s.period
        checks = R.core_checks(s.run_e, s.v)
        assert checks["error"] is None and checks["invariants"] == [], (s.period, checks)


@ci_only
def test_catch_up_of_growth_is_named_because_the_anchor_forgets_the_gap():
    """Навёрстывание роста включено: клетка помнит разрыв с потенциальным путём, факты якоря — нет. Инструмент
    называет это предупреждением и печатает абзац о росте; на книге с навёрстыванием, равным нулю, — молчит."""
    s = chain(1, ())[0]
    assert any("навёрстывание роста включено" in w for w in s.cand.warnings)
    assert not any("навёрстывание роста включено" in w for w in first().cand.warnings)
    spread = R.growth_spread(s.run_plus)
    assert spread["catch_up"] == 0.25 and 0.0 <= spread["min"] <= spread["max"] <= 1.0
    result = R.attribution(s.book, s.facts, s.expected, valuation_date=s.v, cells=False)
    text = R.report_text(s.book, result)
    assert ("**Рост, ограниченный капиталом.**" in text) == bool(spread["cells"])
    assert "## Дивиденды по периодам" in text and "Последний закрытый квартал прибыли: 2025Q4 → 2026Q1" in text


# ------------------------------------------------------------------ нормативы: оценка и замена фактом формы


@ci_only
def test_estimated_ratios_are_flagged_and_replaced_by_the_form_without_moving_the_anchor(tmp_path):
    """Отчёт с оценкой нормативов несёт на слотах уровней капитала и RWA значения последней формы: инструмент
    считает уровни якоря по оценке на RWA модели — кандидат тот же, что на тех же нормативах фактом (плотности RWA
    не калибруются к RWA прошлого квартала); факты кандидата несут пометку оценки. Замена оценки фактом формы —
    кандидат на том же якоре: пометка снята, якорь воспроизводит форму, плотности RWA пересчитаны к RWA формы,
    ближняя калибровка ЧПМ не тронута."""
    s = first()
    estimate = {slot: {"bank_value": s.expected["capital"][slot] - 0.004, "spread": 0.004, "spread_as_of": "2026-06-30"}
                for slot in R.ESTIMATE_SLOTS}
    last_form = anchor_facts(s.facts, s.book.get("nii.books"))
    rep = changed(s.expected, **{"capital.estimated": True, "capital.estimate": estimate, "pnl.estimated": True,
                                 "capital.basel_cet1": last_form.basel_cet1, "capital.basel_rwa": last_form.basel_rwa,
                                 "capital.bank_base_capital": last_form.bank_base_capital})
    cand = R.reanchor(s.book, s.facts, rep, valuation_date=s.v, base_run=s.run_plus, near=s.cand.near)
    af = anchor_facts(cand.facts, s.book.get("nii.books"))
    assert af.estimated == ("n20_0", "n1_1_bank")
    levels = cand.derived["estimated_levels"]
    assert set(levels) == set(R.ESTIMATED_LEVELS) and levels["basel_rwa"][0] == last_form.basel_rwa
    for slot in ("basel_rwa", "basel_cet1", "bank_base_capital"):
        assert levels[slot][1] == pytest.approx(s.expected["capital"][slot], rel=1e-6), slot
    assert af.basel_rwa == pytest.approx(s.expected["capital"]["basel_rwa"], rel=1e-6) != last_form.basel_rwa
    assert cand.derived["rwa_factor"] == pytest.approx(s.cand.derived["rwa_factor"], rel=1e-8)
    assert cand.derived["anchor_row"]["n20"] == pytest.approx(rep["capital"]["n20_0"], abs=1e-8)
    assert any("уровни капитала и RWA якоря посчитаны по оценке" in w for w in cand.warnings)
    run = run_grid(cand.book, cand.facts, R.live_at(cand.book, cand.facts, s.v))
    assert run.point == pytest.approx(s.run_e.point, abs=1e-3), "оценка, равная расчёту, — тот же кандидат"
    cap = cand.facts.files["capital"]
    assert cap["n20_0"]["estimate"]["bank_value"]["v"] == pytest.approx(estimate["n20_0"]["bank_value"])
    assert cap["n20_0"]["estimate"]["spread_as_of"] == "2026-06-30" and cap["n20_0"]["value"]["estimated"] is True
    assert cand.facts.files["pnl_quarterly"]["quarters"][s.period]["ni_shareholders"]["estimated"] is True
    for path, value in s.cand.derived["gaps"].items():      # поправки прежние — с точностью округления вычетов (0,001 млрд ₽)
        assert cand.derived["gaps"][path] == pytest.approx(value, abs=1e-6), path
    assert any("--capital-form" in w for w in cand.warnings) and any("pnl.estimated" in w for w in cand.warnings)
    text = R.report_text(s.book, R.attribution(s.book, s.facts, rep, valuation_date=s.v, cells=False))
    assert "нормативы якоря — оценка до выхода формы" in text
    # --- форма вышла: нормативы чуть ниже оценки, RWA выше
    c = s.expected["capital"]
    form = {"schema": R.CAPITAL_FORM, "period": s.period, "as_of": R.period_end(s.period).isoformat(),
            "n20_0": c["n20_0"] - 0.002, "n1_1_bank": c["n1_1_bank"] - 0.001, "basel_cet1": c["basel_cet1"] - 4.0,
            "basel_rwa": c["basel_rwa"] * 1.01, "bank_base_capital": c["bank_base_capital"] - 3.0}
    result = R.replace_capital(cand.book, cand.facts, form, valuation_date=s.v)
    new = result["candidate"]
    assert new.period == s.period == new.data["meta"]["anchor_period"], "якорь прежний"
    assert new.data["meta"]["first_period"] == cand.data["meta"]["first_period"]
    assert new.data["regimes"]["near_nim_shift"] == cand.data["regimes"]["near_nim_shift"]
    assert new.data["joint"]["regime_update"]["observations"] == cand.data["joint"]["regime_update"]["observations"]
    assert anchor_facts(new.facts, s.book.get("nii.books")).estimated == ()
    assert new.derived["anchor_row"]["n20"] == pytest.approx(form["n20_0"], abs=1e-8)
    assert new.derived["anchor_row"]["n11"] == pytest.approx(form["n1_1_bank"], abs=1e-8)
    assert new.derived["rwa_factor"] == pytest.approx(1.01, rel=1e-6)
    run = run_grid(new.book, new.facts)
    assert run.cells[0].quarters["rwa"][0] == pytest.approx(form["basel_rwa"], rel=1e-6)
    assert result["steps"]["candidate"]["point"] != result["steps"]["book"]["point"], "замена оценки — строка «факты»"
    assert new.derived["was_estimated"] == ["n20_0", "n1_1_bank"]
    out = tmp_path / "form"
    R.write_form_candidate(out, cand.book, result)
    assert sorted(p.name for p in out.iterdir()) == ["REANCHOR.md", "assumptions.json", "assumptions.yaml", "facts"]
    text = (out / "REANCHOR.md").read_text(encoding="utf-8")
    for fragment in ("Замена оценки нормативов фактом формы", "якорь прежний", "строка «факты»", "## Проверки ядра на кандидате"):
        assert fragment in text, fragment
    again = R.replace_capital(new.book, new.facts, form, valuation_date=s.v)
    assert any("не помечены оценкой" in w for w in again["candidate"].warnings)
    assert again["steps"]["candidate"]["point"] == pytest.approx(result["steps"]["candidate"]["point"], abs=1e-6)


@ci_only
def test_the_anchor_key_of_capital_instruments_takes_the_fact_of_the_report():
    """М§4.11: книга, которая пишет ключ квартала якоря траектории инструментов капитала явно, получает ключ
    нового якоря, равный факту отчёта; ожидаемый отчёт несёт значение траектории — ключ не правится."""
    traj = {"2026Q2": 123.0, "2026Q3": 125.0, "LT": 130.0}
    s = walk(1, NO_CATCH_UP + (("capital.n20.t2", traj),))[0]
    assert s.expected["capital"]["t2"] == 125.0 and "t2_anchor" not in s.cand.derived
    assert s.cand.data["capital"]["n20"]["t2"] == traj
    rep = changed(s.expected, **{"capital.t2": 127.5})
    cand = R.reanchor(s.book, s.facts, rep, valuation_date=s.v, base_run=s.run_plus, near=s.cand.near)
    assert cand.data["capital"]["n20"]["t2"] == {**traj, "2026Q3": 127.5} and cand.derived["t2_anchor"] == (125.0, 127.5)
    assert any("capital.n20.t2" in w and "суждение книги" in w for w in cand.warnings)
    assert cand.derived["anchor_row"]["n20"] == pytest.approx(rep["capital"]["n20_0"], abs=1e-8)
    assert "t2" not in first().expected["capital"], "траектория без ключа квартала якоря: отчёт инструменты не называет"


# ------------------------------------------------------------------ отказы


@ci_only
@pytest.mark.parametrize("changes,fragment", [
    ({"balance.dividends_payable_declared": [{"period": "2026Q2", "amount": 1.0}]}, "объявленный дивиденд без решения"),
    ({"balance.dividends_payable_declared": [{"period": "2026Q1", "amount": 99.0}]}, "больше остатка"),
    ({"balance.dividends_payable_declared": [{"period": "2026Q1", "amount": 1.0}, {"period": "2026Q1", "amount": 1.0}]},
     "повторяется"),
    ({"balance.dividends_payable_declared": [{"period": "2026Q1", "sum": 1.0}]}, "{period, amount}"),
    ({"dividend_decisions": [{"period": "2026Q1", "dps": 4.6, "decided_date": "2026-10-02"}]}, "не позже конца квартала"),
    ({"dividend_decisions": [{"period": "2026Q1", "dps": 4.6, "decided_date": "2026-06-30"}]}, "позже прежней"),
    ({"dividend_decisions": [{"period": "2026Q1", "dps": -1.0, "decided_date": "2026-07-30"}]}, "не меньше нуля"),
    ({"dividend_decisions": [{"period": "2026Q1", "dps": 4.6}]}, "нет ключей decided_date"),
    ({"dividend_decisions": [{"period": "2026Q4", "dps": 4.6, "decided_date": "2026-07-30"}]}, "позже закрываемого"),
    ({"dividend_decisions": [{"period": "2026Q1", "dps": 4.6, "decided_date": "2026-07-30", "record_date": "2026-07-01"}]},
     "раньше дня решения"),
    ({"capital.estimated": True}, "capital.estimate"),
    ({"capital.estimate": {"n20_0": {}, "n1_1_bank": {}}}, "capital.estimate"),
    ({"capital.estimated": "да"}, "true или false"),
    ({"balance.other_assets_fixed": 1e6}, "постоянная часть прочих активов"),
    ({"shares": {"economic_treasury": -1.0}}, "не меньше нуля"),
])
def test_a_bad_report_of_the_quarterly_form_is_refused_with_the_reason(changes, fragment):
    s = first()
    with pytest.raises(R.ReportError) as exc:
        R.check_report(s.book, s.facts, changed(s.expected, **changes))
    assert fragment in str(exc.value), str(exc.value)


@ci_only
def test_the_year_of_the_dividend_is_not_read_under_the_quarterly_calendar():
    """`dividends_payable_year` — поле годового календаря: при квартальном оно не читается, инструмент
    предупреждает; экономически собственные акции отчёта становятся фактом и меняют делитель."""
    s = first()
    rep = changed(s.expected, **{"balance.dividends_payable_year": 2025,
                                 "shares": {"issued_total": 2700.0, "outstanding_total": 2570.0, "economic_treasury": 20.0}})
    R.check_report(s.book, s.facts, rep)
    cand = R.reanchor(s.book, s.facts, rep, valuation_date=s.v, base_run=s.run_plus, near=s.cand.near)
    assert any("dividends_payable_year отчёта не прочитан" in w for w in cand.warnings)
    assert "dividends_payable_year" not in cand.facts.files["balance"]
    run = run_grid(cand.book, cand.facts, R.live_at(cand.book, cand.facts, s.v))
    assert run.divisor == pytest.approx(2700.0 - 20.0) and run.shares_out == 2570.0


@ci_only
def test_a_calendar_the_anchor_cannot_express_is_refused():
    """Выплата раньше вычета из регуляторного капитала: на конец квартала дивиденд выплачен, а в регуляторном
    капитале ещё стоит — фактами якоря это не выразить (списка «к выплате» для него нет). Отказ называет квартал
    прибыли и решение книги."""
    s1 = chain(1, NO_CATCH_UP + (("dividends.calendar.payment_lag_quarters", 1),))[0]
    plus, run_plus, _ = R.expected_run(s1.cand.book, s1.cand.facts, R.live_at(s1.cand.book, s1.cand.facts, s1.v))
    with pytest.raises(R.ReportError) as exc:
        R.expected_report(s1.cand.book, s1.cand.facts, run=run_plus)
    text = str(exc.value)
    assert "не представим фактами якоря" in text and "2026Q3" in text and "payment_lag_quarters" in text


# ------------------------------------------------------------------ командная строка


@ci_only
def test_the_command_line_carries_the_quarterly_form_and_the_form_file(tmp_path, capsys):
    """`--expected`, `--facts` на нём же, затем `--capital-form` на записанном кандидате: разделы формы панели в
    выводе, кандидат читается ядром, код возврата 0."""
    data = t_dict()
    put(data, *NO_CATCH_UP[0])
    book_file = tmp_path / "book.json"
    book_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    common = ["--book", str(book_file), "--facts-dir", str(FIXTURE_T_FACTS), "--template", str(tmp_path / "нет")]
    expected = tmp_path / "expected.json"
    assert R.main(common + ["--expected", str(expected)]) == 0
    capsys.readouterr()
    rep = json.loads(expected.read_text(encoding="utf-8"))
    out = tmp_path / "out"
    v = "2026-10-02"
    assert R.main(common + ["--facts", str(expected), "--out", str(out), "--valuation-date", v, "--no-cells",
                            "--compare-facts", str(FIXTURE_T_FACTS)]) == 0
    printed = capsys.readouterr().out
    for title in ("## Дивиденды по периодам", "Последний закрытый квартал прибыли: 2025Q4 → 2026Q1",
                  "## Сверка фактов кандидата с пересобранными фактами", "`period`", "Передача ставки: `keep`"):
        assert title in printed, title
    c = rep["capital"]
    form = tmp_path / "form.json"
    form.write_text(json.dumps({"period": rep["period"], "n20_0": c["n20_0"] + 0.001, "n1_1_bank": c["n1_1_bank"],
                                "basel_cet1": c["basel_cet1"], "basel_rwa": c["basel_rwa"],
                                "bank_base_capital": c["bank_base_capital"]}), encoding="utf-8")
    cand = ["--book", str(out / "assumptions.json"), "--facts-dir", str(out / "facts"), "--template", str(tmp_path / "нет")]
    assert R.main(cand + ["--capital-form", str(form), "--out", str(tmp_path / "form-out")]) == 0
    printed = capsys.readouterr().out
    assert "Замена оценки нормативов фактом формы" in printed and "не помечены оценкой" in printed
    assert (tmp_path / "form-out" / "REANCHOR.md").read_text(encoding="utf-8").strip() == printed.strip()
    form.write_text(json.dumps({"period": "2026Q2", "n20_0": 0.13, "n1_1_bank": 0.09, "basel_cet1": 1.0, "basel_rwa": 1.0,
                                "bank_base_capital": 1.0}), encoding="utf-8")
    assert R.main(cand + ["--capital-form", str(form), "--out", str(tmp_path / "form-out")]) == 1
    assert "без его смены" in capsys.readouterr().err
    assert FIXTURE_T_BOOK.exists()
