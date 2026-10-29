"""Квартальный календарь дивидендов (М§5.7) — аналитические тесты на фикстуре `tests/fixtures/core_t`.

Календарь включается один поверх «прежней ветви» (`tests.support_core_t.plain_dict`): те же 12 книг на прежних
формулах, решение о дивиденде — за каждый квартал прибыли. Проверки — закрытые формулы и тождества, выведенные
из книги и фактов независимо от ядра: карта лагов и правило закрытого квартала (М§5.7.2), база — средняя прибыль
окна (М§5.7.3), состояние якоря и порядок квартала (М§5.7.4), решение, DPS по кварталам и годам (М§5.7.5),
реестр, мост и дивиденд без записи реестра по периодам (М§5.7.6, §8.1, §14.4), тождества DDM = RI и капитала при
квартальных выплатах (М§6.4), избыток капитала терминала без дивидендов, ещё стоящих в регуляторном капитале (М§7).
Связка с ростом, ограниченным капиталом (М§4.13), — два теста в конце файла; сам механизм — `tests/test_core_t_w3.py`.
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import date, timedelta

import pytest

from model.book import book_from_dict
from model.book_schema import BookError, FactsError
from model.cell import _Cell, initial_state
from model.checks import check_gates, check_invariants
from model.dividends import closed_through, lag_rule, quarter_calendar
from model.grid import DividendRecord, LiveInputs, live_from_book, run_grid
from model.paths import Trajectory
from tests.support_core_t import book_live, plain_book, plain_dict, plain_run, put, t_dict, t_facts

pytestmark = pytest.mark.tact

CAL = "dividends.calendar"
BASIS = "valuation.shares_basis"
HISTORY = "dividends.policy.history_test"
REF = ("N", "norm", "schedule")              # клетка без шока и без среза дивиденда
CRISIS = ("N", "crisis", "schedule")


def _on(*keys: str):
    """Книга и сетка «прежней ветви» с квартальным календарём и ветвями `keys`; реестр пуст."""
    keys = (CAL,) + keys
    return plain_book(keys), plain_run(keys)


def _book(**changes):
    """Книга «прежней ветви» с квартальным календарём и заменами по точечным путям."""
    data = plain_dict(on=(CAL,))
    for dotted, value in changes.items():
        put(data, dotted.replace("__", "."), value)
    return book_from_dict(data, facts=t_facts())


def _facts(file: str, change):
    """Факты фикстуры с правкой одного файла: `change(копия содержимого)` правит её на месте."""
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


def _grid(book, facts=None, register=(), day=None):
    live = book_live(book)
    v = day or live.valuation_date
    live = LiveInputs(valuation_date=v, prices=dict(live.prices), price_dates={t: v for t in live.prices},
                      register=tuple(register))
    return run_grid(book, facts or t_facts(), live)


def _rec(period: str, dps: float, record: date, *, decided: date | None = None, pay: date | None = None,
         status: str = "declared", label: str | None = None) -> DividendRecord:
    """Запись реестра за квартал прибыли: экс-дата — день реестра."""
    return DividendRecord(year=int(period[:4]), dps=dps, status=status, record_date=record,
                          last_buy_date=record - timedelta(days=3), ex_date=record, pay_date=pay,
                          sources=("проверка",), period=period, label=label, decided_date=decided)


# Четыре записи одного года прибыли: решение, реестр, выплата (как решает эмитент: реестр через 11 дней).
FOUR = (
    _rec("2026Q1", 4.60, date(2026, 8, 10), decided=date(2026, 7, 30), pay=date(2026, 8, 24), status="paid"),
    _rec("2026Q2", 4.70, date(2026, 10, 12), decided=date(2026, 10, 1), pay=date(2026, 10, 26)),
    _rec("2026Q3", 4.80, date(2026, 12, 28), decided=date(2026, 12, 17), pay=date(2027, 1, 11)),
    _rec("2026Q4", 5.00, date(2027, 5, 24), decided=date(2027, 5, 13), pay=date(2027, 6, 7)),
)


def _broken(run) -> list[str]:
    """Нарушенные инварианты прогона. Тест истории выплат в счёт не идёт: без ключа его вид — формула «до
    копейки», а она читает поля строк истории первой формы (на «прежней ветви» он нарушен по построению)."""
    return [f"{f.name}: {f.message}" for f in check_invariants(run) if f.fired and f.name != "dps_history"]


def _ni(run, cell, idx: int) -> float:
    """Прибыль акционеров квартала с номером `idx` на линейке сетки: не позже якоря — факт, позже — клетка."""
    if idx >= 1:
        return cell.quarters["ni_sh"][idx]
    return t_facts().need("pnl_quarterly", f"quarters.{run.ctx.timeline.period(idx)}.ni_shareholders")


def _room(run, key, q: int) -> float:
    """Запас квартала q, собранный заново: кварталы 1…q − 1 — шагами клетки с дивидендами решений прогона, квартал
    q — на копии состояния, только с записями реестра; одна точка — конец квартала, отчётные нормативы против
    требований (М§5.7.4 п. 4)."""
    cell, slots = run.cell(*key), run.ctx.prep.calendar.periods
    walker = _Cell(run.ctx, *key)
    st = initial_state(run.ctx.prep)

    def parts(quarter: int, registered_only: bool = False) -> tuple:
        return tuple((d.div, slots[d.period].q_pay, slots[d.period].q_reg) for d in cell.decisions
                     if d.q == quarter and (d.source == "register" or not registered_only))

    for quarter in range(1, q):
        given = parts(quarter)
        walker.step(st, quarter, sum(a for a, _, _ in given), parts=given)
    given = parts(q, registered_only=True)
    row = walker.step(st.clone(), q, sum(a for a, _, _ in given), parts=given)
    return min((row["n20"] - row["req20"]) * row["rwa"], (row["n11"] - row["req11"]) * row["rwa"])


# ------------------------------------------------------------------ карта лагов и закрытый квартал (М§5.7.2)


def test_decisions_follow_the_lag_map():
    """Квартал решения — квартал прибыли плюс лаг его номера в году, не раньше первого прогнозного: за первый
    квартал — в третьем, за второй и третий — в четвёртом, за четвёртый — во втором следующего года; в первом
    квартале года решений нет; в квартале — от нуля до двух решений; решение за сеткой клетка не считает."""
    book, run = _on()
    tl, cal = run.ctx.timeline, run.ctx.prep.calendar
    lags = book.get("dividends.calendar.decision_lag_quarters")
    assert tl.period(cal.p_last) == "2025Q4"                 # последнее решение собрания до даты фактов — за 4К2025
    cell = run.cell(*REF)
    assert [d.period for d in cell.decisions] == [tl.period(i) for i in range(cal.p_last + 1, tl.Q)]
    for d in cell.decisions:
        idx = tl.index(d.period)
        assert d.q == max(1, idx + lags[str(tl.h(idx))]) and d.year == tl.year(idx) and d.source == "model"
        assert tl.h(d.q) != 1                                # первый квартал года — без решений
    per_quarter = [sum(1 for d in cell.decisions if d.q == q) for q in range(1, tl.Q + 1)]
    assert set(per_quarter) == {0, 1, 2}
    assert [d.q for d in cell.decisions[:4]] == [1, 2, 2, 4]                 # 1К–4К года якоря
    assert tl.period(tl.Q)[:4] + "Q4" not in cell.dps_q                      # решение за последний квартал — за сеткой
    assert set(cell.dps) == set(range(tl.anchor_year, tl.last_year)) and tl.last_year not in cell.dps


def test_profit_quarter_leaves_the_book_value_exactly_once():
    """Каждый открытый квартал прибыли уменьшает BV ровно один раз — при любой карте лагов: закрыт квартал или
    нет, решает факт (строка истории с решением не позже даты фактов), а не карта."""
    facts = t_facts()
    n_out = facts.need("shares", "outstanding_total")
    for lag in (1, 2, 4, {"1": 4, "2": 1, "3": 3, "4": 2}):
        run = _grid(_book(dividends__calendar__decision_lag_quarters=lag))
        tl, cal = run.ctx.timeline, run.ctx.prep.calendar
        assert tl.period(cal.p_last) == "2025Q4"
        for c in (run.cell(*REF), run.cell(*CRISIS)):
            periods = sorted(d.period for d in c.decisions)
            assert periods == [o.period for o in cal.open] and periods[0] == "2026Q1"      # ни пропуска, ни повтора
            lags = lag if isinstance(lag, dict) else {str(h): lag for h in (1, 2, 3, 4)}
            assert periods == [tl.period(i) for i in range(cal.p_last + 1, tl.Q) if i + lags[str(tl.h(i))] <= tl.Q]
            assert "2025Q4" not in c.dps_q                                           # закрыт фактом — при любой карте
            paid = sum(c.quarters["div"][q] for q in range(1, tl.Q + 1))
            assert paid == pytest.approx(sum(c.dps_q.values()) * n_out / 1000, rel=1e-12)
            for d in c.decisions:
                assert c.quarters["div"][d.q] >= d.div - 1e-12
    # лаг 1: по одной карте решение за 1К года якоря «состоялось до якоря» — по факту оно открыто и идёт в первый
    # прогнозный квартал; лаг 4: по карте решение за 4К прошлого года «впереди» — по факту оно закрыто
    early = _grid(_book(dividends__calendar__decision_lag_quarters=1)).cell(*REF)
    assert early.decisions[0].period == "2026Q1" and early.decisions[0].q == 1
    late = _grid(_book(dividends__calendar__decision_lag_quarters=4)).cell(*REF)
    assert late.decisions[0].period == "2026Q1" and late.decisions[0].q == 3


def test_closed_quarter_follows_the_decision_date_of_the_history_row():
    """p_last — самый поздний квартал прибыли со строкой истории, решённой не позже даты фактов; строка с решением
    позже даты фактов квартал не закрывает; нет ни одной закрывающей строки или у строки нет периода — отказ."""
    book = plain_book((CAL,))
    tl = plain_run((CAL,)).ctx.timeline
    facts_date = book.get("meta.facts_date")
    assert tl.period(closed_through(t_facts(), tl, facts_date)) == "2025Q4"

    def decided(period: str, day: str):
        def change(data):
            next(r for r in data["history"] if r["period"] == period)["decided_date"] = day
        return _facts("dividends", change)

    moved = decided("2026Q1", "2026-06-25")                  # собрание за 1К прошло до даты фактов
    assert tl.period(closed_through(moved, tl, facts_date)) == "2026Q1"
    cell = _grid(book, moved).cell(*REF)
    assert "2026Q1" not in cell.dps_q and cell.decisions[0].period == "2026Q2"
    history = {r["period"]: r["dps"]["v"] for r in moved.files["dividends"]["history"]}
    assert cell.dps[2026] == pytest.approx(history["2026Q1"] + sum(cell.dps_q[f"2026Q{h}"] for h in (2, 3, 4)), rel=1e-12)
    later = decided("2025Q4", "2026-07-02")                  # собрание за 4К прошло после даты фактов
    assert tl.period(closed_through(later, tl, facts_date)) == "2025Q3"
    cell = _grid(book, later).cell(*REF)
    assert cell.decisions[0].period == "2025Q4" and cell.decisions[0].q == 1 and 2025 in cell.dps
    assert cell.dps[2025] == pytest.approx(3.30 + 3.50 + 3.60 + cell.dps_q["2025Q4"], rel=1e-12)
    with pytest.raises(FactsError, match="не позже даты фактов"):
        _grid(book, _facts("dividends", lambda d: [r.update(decided_date="2026-08-01") for r in d["history"]]))
    with pytest.raises(FactsError, match="обязательны в каждой строке"):
        _grid(book, _facts("dividends", lambda d: d["history"][0].pop("period")))
    # закрытый квартал без своей строки истории покрыт строкой более позднего квартала (решение «за полугодие»
    # несёт период второго квартала) и даёт в годовой сумме ноль; строка без DPS — отказ
    holes = _facts("dividends", lambda d: d.update(history=[r for r in d["history"] if r["period"] != "2026Q1"]))
    holes = dataclasses.replace(holes, files={**holes.files, "dividends": {
        **holes.files["dividends"], "history": [dict(r, decided_date="2026-06-20") if r["period"] == "2026Q2" else r
                                                for r in holes.files["dividends"]["history"]]}})
    run = _grid(book, holes)
    assert tl.period(run.ctx.prep.calendar.p_last) == "2026Q2" and run.ctx.prep.calendar.closed_dps[2026] == 4.7
    cell = run.cell(*REF)
    assert cell.decisions[0].period == "2026Q3"
    assert cell.dps[2026] == pytest.approx(4.7 + cell.dps_q["2026Q3"] + cell.dps_q["2026Q4"], rel=1e-12)
    empty = dataclasses.replace(holes, files={**holes.files, "dividends": {
        **holes.files["dividends"], "history": [dict(r, dps=None) if r["period"] == "2026Q2" else r
                                                for r in holes.files["dividends"]["history"]]}})
    with pytest.raises(FactsError, match="закрытый квартал прибыли 2026Q2"):
        _grid(book, empty)


# ------------------------------------------------------------------ база, пул, DPS (М§5.7.3)


def test_quarterly_decision_takes_the_window_mean_not_the_year():
    """База решения — средняя прибыль акционеров окна W последних кварталов: кварталы не позже якоря — факт,
    позже — клетка; пул — доля от базы на все размещённые акции, уменьшение BV — на акции в обращении."""
    book, run = _on()
    facts, tl = t_facts(), run.ctx.timeline
    window = int(book.get("dividends.policy.base_window_quarters"))
    payout = Trajectory(book.get("dividends.policy.payout"))
    n_iss, n_out = facts.need("shares", "issued_total"), facts.need("shares", "outstanding_total")
    assert window == 4
    cell = run.cell(*REF)
    for d in cell.decisions[:12]:
        idx = tl.index(d.period)
        mean = sum(_ni(run, cell, x) for x in range(idx - window + 1, idx + 1)) / window
        assert d.base == pytest.approx(mean, rel=1e-12), d.period
        assert not d.cut and d.excess == 0.0 and d.catch == 0.0
        assert d.dps == pytest.approx(payout.year_value(d.year) * mean * 1000 / n_iss, rel=1e-12)
        assert d.div == pytest.approx(d.dps * n_out / 1000, rel=1e-12)
        assert cell.dps_policy_q[d.period] == pytest.approx(d.dps, rel=1e-12)
    first = cell.decisions[0]                                # окно первого решения целиком из фактов
    assert first.base == pytest.approx((41.5 + 43.9 + 46.5 + 49.4) / 4, rel=1e-12)
    year_to_date = _ni(run, cell, 0) + _ni(run, cell, -1)
    assert cell.decisions[1].period == "2026Q2" and abs(cell.decisions[1].base - year_to_date) > 1.0
    assert abs(cell.decisions[1].base - _ni(run, cell, 0)) > 1.0             # и не прибыль одного квартала
    # без ключа окна — база равна прибыли самого квартала
    one = _grid(_book(dividends__policy__base_window_quarters=1)).cell(*REF)
    for d in one.decisions[:6]:
        idx = tl.index(d.period)
        assert d.base == pytest.approx(one.quarters["ni_sh"][idx] if idx >= 1 else _ni(run, cell, idx), rel=1e-12)
    data = plain_dict(on=(CAL,))
    del data["dividends"]["policy"]["base_window_quarters"]
    bare = _grid(book_from_dict(data, facts=facts)).cell(*REF)
    assert [d.base for d in bare.decisions] == [d.base for d in one.decisions]
    with pytest.raises(FactsError, match="нет прибыли акционеров за 2025Q2"):
        _grid(book, _facts("pnl_quarterly", lambda d: d["quarters"].pop("2025Q2")))


def test_base_deducts_the_coupon_in_its_quarter_when_the_policy_says_so():
    """`deduct_at1_after_tax`: из базы квартала выплаты купона вычитается годовой купон за вычетом налогового
    эффекта; в прочих кварталах окна — ничего."""
    coupon = _facts("capital", lambda d: (d["at1"]["coupon_annual"].update(v=8.0), d["at1"]["coupon_quarter"].update(v=2)))
    plain = _grid(plain_book((CAL,)), coupon).cell(*REF)
    book = _book(dividends__policy__deduct_at1_after_tax=True)
    cell = _grid(book, coupon).cell(*REF)
    tau = Trajectory(book.get("tax.statutory"))
    for i, (d, was) in enumerate(list(zip(cell.decisions, plain.decisions))[:6]):
        year = int(d.period[:4])
        # окно — четыре квартала подряд, квартал купона в нём ровно один: у решения за первый квартал — прошлого
        # года. Окна первых двух решений — целиком из фактов; дальше прибыль клетки чуть зависит от дивиденда
        want = was.base - 8.0 * (1 - tau.year_value(year if d.period[-1] != "1" else year - 1)) / 4
        assert d.base == pytest.approx(want, rel=1e-12 if i < 2 else 1e-3), d.period
    assert cell.decisions[0].base < plain.decisions[0].base


# ------------------------------------------------------------------ порядок квартала (М§5.7.4, §5.7.5)


def test_room_is_one_point_of_the_decision_quarter_and_two_decisions_share_it():
    """Запас квартала — оценка шага этого квартала без решений модели, одна точка; базовый дивиденд квартала —
    min(Σ пулов, запас), между решениями — пропорционально пулам; срез — общий на квартал."""
    book, run = _on()
    cell = run.cell(*CRISIS)
    by_q: dict[int, list] = {}
    for d in cell.decisions:
        if d.source == "model":
            by_q.setdefault(d.q, []).append(d)
    partial = {q: ds for q, ds in by_q.items() if ds[0].cut and sum(d.base_div for d in ds) > 1e-6}
    two = [q for q, ds in partial.items() if len(ds) == 2]
    assert two and any(len(ds) == 1 for ds in partial.values())
    for q in two[:2] + [next(q for q, ds in partial.items() if len(ds) == 1)]:
        ds = by_q[q]
        room = _room(run, CRISIS, q)
        want = sum(d.want[0] for d in ds)
        assert all(d.headroom == (ds[0].headroom[0],) and d.headroom_final == d.headroom[0] for d in ds)
        assert ds[0].headroom[0] == pytest.approx(room, rel=1e-9)
        assert 0 < room < want
        assert sum(d.base_div for d in ds) == pytest.approx(room, rel=1e-12)
        for d in ds:
            assert d.base_div == pytest.approx(room * d.want[0] / want, rel=1e-12) and d.cut and "dividend_cut" in d.flags
    # квартал без нехватки: запас больше пула — пул выплачен целиком, среза нет
    free = next(q for q, ds in by_q.items() if len(ds) == 2 and not ds[0].cut)
    assert _room(run, CRISIS, free) == pytest.approx(by_q[free][0].headroom[0], rel=1e-9)
    assert all(d.base_div == d.want[0] for d in by_q[free])


def test_room_counts_the_register_dividends_of_the_quarter():
    """Запас меряется с записями реестра этого квартала и без решений модели: объявленный дивиденд с вычетом из
    регуляторного капитала в том же квартале уменьшает запас под решение модели один к одному (с точностью до
    дохода на выплаченные деньги)."""
    book = plain_book((CAL,))
    rec = FOUR[1]                                            # 2К: решение и реестр в 4-м квартале — как решение за 3К
    run, base = _grid(book, register=(rec,)), _grid(book)
    cell, was = run.cell(*REF), base.cell(*REF)
    d3 = next(d for d in cell.decisions if d.period == "2026Q3")
    assert d3.q == 2 and d3.headroom[0] == pytest.approx(_room(run, REF, 2), rel=1e-9)
    w2 = next(d for d in was.decisions if d.period == "2026Q2")
    w3 = next(d for d in was.decisions if d.period == "2026Q3")
    n_out = t_facts().need("shares", "outstanding_total")
    # прежде запас был без дивиденда за 2К (тогда — решение модели); запись снимает с него свой дивиденд
    # (деньги дивиденда уходят из балансирующих активов вместе с их RWA — отсюда доля процента)
    assert w3.headroom[0] - d3.headroom[0] == pytest.approx(rec.dps * n_out / 1000, rel=1e-2)
    assert w2.source == "model" and next(d for d in cell.decisions if d.period == "2026Q2").source == "register"


def test_excess_is_paid_once_a_year_with_the_fourth_quarter_decision():
    """Доля избытка — только в решении за четвёртый квартал прибыли: ε_Y × max(0, запас − базовый дивиденд
    квартала − догоняющая выплата), ε вводится линейно за `ramp_years` лет с года `from_profit_year`; в прочих
    решениях — ноль."""
    book, run = _on()
    eps, start, ramp = (float(book.get("dividends.excess.epsilon")), int(book.get("dividends.excess.from_profit_year")),
                        int(book.get("dividends.excess.ramp_years")))
    assert ramp > 1
    seen = set()
    for c in run.cells:
        by_q: dict[int, list] = {}
        for d in c.decisions:
            if d.source == "model":
                by_q.setdefault(d.q, []).append(d)
        for ds in by_q.values():
            base = sum(d.base_div for d in ds)
            for d in ds:
                if d.period.endswith("Q4"):
                    e_y = eps * min(1.0, (d.year - start + 1) / ramp) if d.year >= start else 0.0
                    assert d.excess == pytest.approx(e_y * max(0.0, d.headroom_final - base - d.catch), abs=1e-9)
                    assert d.div == pytest.approx(d.base_div + d.catch + d.excess, rel=1e-12)
                    if d.excess > 0:
                        seen.add(d.year)
                else:
                    assert d.excess == 0.0 and d.catch == 0.0 and d.div == d.base_div
    assert {start, start + 1, start + ramp} <= seen            # ввод: ε/3, 2ε/3, ε
    assert not _broken(run)


def test_shock_year_cancels_the_decisions_taken_in_it():
    """Год шока отменяет решения модели, принимаемые в его кварталах: источник и флаг — `crisis_skip`, не срез
    капиталом; решения до и после — в силе; запись реестра кризис не отменяет; отложенный пул без догоняющей
    выплаты не копится."""
    book, run = _on()
    tl = run.ctx.timeline
    shock = tl.anchor_year + int(book.get("regimes.crisis.shock_year_offset"))
    for c in run.cells:
        skipped = [d for d in c.decisions if d.source == "crisis_skip"]
        if c.regime != "crisis":
            assert not skipped and "crisis_skip" not in c.flags
            continue
        assert [d.period for d in skipped] == ["2026Q4", "2027Q1", "2027Q2", "2027Q3"] and "crisis_skip" in c.flags
        for d in c.decisions:
            in_shock = tl.year(d.q) == shock
            assert (d.source == "crisis_skip") == in_shock, d.period
            if in_shock:
                assert d.div == 0.0 and d.dps == 0.0 and not d.cut and d.flags == ("crisis_skip",)
                assert d.deferred_before == d.deferred_after == 0.0 and d.want[0] >= 0
        assert sum(d.want[0] for d in skipped) > 0
        for q in tl.quarters_of_year(shock):
            assert c.quarters["div"][q] == 0.0
    rec = _rec("2027Q1", 5.0, date(2027, 9, 20), decided=date(2027, 9, 9), pay=date(2027, 10, 4))
    cell = _grid(book, register=(rec,)).cell(*CRISIS)
    kept = next(d for d in cell.decisions if d.period == "2027Q1")
    assert kept.source == "register" and kept.dps == 5.0 and tl.year(kept.q) == shock


def test_catch_up_pays_the_cancelled_pools_with_the_fourth_quarter_decision():
    """`crisis.catch_up: true`: отменённые пулы копятся в отложенном пуле и выплачиваются в пределах запаса в
    решении за четвёртый квартал прибыли: catch = min(D, max(0, запас − базовый дивиденд квартала))."""
    run = _grid(_book(dividends__crisis__catch_up=True))
    cell = run.cell(*CRISIS)
    pool = cancelled = paid = 0.0
    for d in cell.decisions:                                 # решения идут по кварталам клетки, в квартале — по порядку
        assert d.deferred_before == pytest.approx(pool, abs=1e-9), d.period
        if d.source == "crisis_skip":
            pool += d.want[0]
            cancelled += d.want[0]
        elif d.period.endswith("Q4"):
            quarter_base = sum(x.base_div for x in cell.decisions if x.q == d.q and x.source == "model")
            assert d.catch == pytest.approx(min(pool, max(0.0, d.headroom_final - quarter_base)), abs=1e-9)
            pool -= d.catch
            paid += d.catch
        else:
            assert d.catch == 0.0
        assert d.deferred_after == pytest.approx(pool, abs=1e-9), d.period
    assert cancelled > 0 and 0 < paid <= cancelled + 1e-9      # выплачено, сколько позволил запас; остаток — в пуле
    assert pool == pytest.approx(cancelled - paid, abs=1e-9)
    assert not _broken(run)
    # без ключа догоняющей выплаты пул не копится и не платится
    off = plain_run((CAL,)).cell(*CRISIS)
    assert all(d.catch == 0.0 and d.deferred_after == 0.0 for d in off.decisions)


# ------------------------------------------------------------------ реестр по периодам (М§5.7.6)


def test_register_record_replaces_the_model_dividend_of_its_quarter_only():
    """Запись `declared` или `paid` — обязательство без проверок за свой квартал прибыли: две записи одного года
    не схлопываются, остальные кварталы года решает модель; DPS года — сумма четырёх кварталов."""
    book = plain_book((CAL,))
    facts = t_facts()
    n_out = facts.need("shares", "outstanding_total")
    run = run_grid(book, facts, live_from_book(book, facts))
    base = plain_run((CAL,))
    for c, was in zip(run.cells, base.cells):
        got = {d.period: d for d in c.decisions}
        for period, dps in (("2026Q1", 4.60), ("2026Q2", 4.70)):
            d = got[period]
            assert d.source == "register" and d.dps == dps and not d.cut and d.excess == d.catch == 0.0
            assert d.div == d.base_div == pytest.approx(dps * n_out / 1000, rel=1e-15)
            assert c.dps_q[period] == dps
            # DPS политики квартала — пул на размещённые акции — от записи не зависит
            assert c.dps_policy_q[period] == pytest.approx(was.dps_policy_q[period], rel=1e-12)
        assert got["2026Q3"].source != "register" and got["2026Q4"].source != "register"
        assert c.dps[2026] == pytest.approx(4.60 + 4.70 + c.dps_q["2026Q3"] + c.dps_q["2026Q4"], rel=1e-12)
        assert c.annual["dps"][0] == c.dps[2026]
        ni = c.annual["ni_sh"][0]
        assert c.annual["payout"][0] == pytest.approx(c.dps[2026] * facts.need("shares", "issued_total") / 1000 / ni, rel=1e-12)
        # квартал с записью и решением модели: ряд div_model несёт только часть модели
        q = got["2026Q3"].q
        assert got["2026Q2"].q == q == 2
        assert c.quarters["div"][q] == pytest.approx(got["2026Q2"].div + got["2026Q3"].div, rel=1e-12)
        assert c.quarters["div_model"][q] == pytest.approx(got["2026Q3"].div, rel=1e-12)
        assert c.quarters["div_model"][1] == 0.0 and c.quarters["div"][1] == pytest.approx(got["2026Q1"].div, rel=1e-15)
    assert run.ctx.prep.register == {"2026Q1": 4.60, "2026Q2": 4.70}
    # рекомендация совета ничего не меняет
    hint = dataclasses.replace(FOUR[2], status="recommended")
    rec_run = _grid(book, register=(hint,))
    assert [c.dps_q for c in rec_run.cells] == [c.dps_q for c in base.cells]


def test_record_dates_move_the_decision_quarter_and_the_queues():
    """Квартал решения записи — не раньше карты и не раньше квартала даты решения; вычет из регуляторного
    капитала и выплата — по датам записи, не раньше квартала решения, без дат — по карте. Между решением и
    вычетом дивиденд стоит в регуляторном капитале; выплата уменьшает дивиденды к выплате в своём квартале."""
    book = plain_book((CAL,))
    tl = plain_run((CAL,)).ctx.timeline
    n_out = t_facts().need("shares", "outstanding_total")

    def slot(rec):
        run = _grid(book, register=(rec,))
        return run, run.ctx.prep.calendar.periods[rec.period]

    # решение позже карты: квартал прибыли 3К (карта — 4-й квартал), собрание — в феврале следующего года
    late = _rec("2026Q3", 4.8, date(2027, 2, 22), decided=date(2027, 2, 11), pay=date(2027, 4, 5))
    run, s = slot(late)
    assert (s.q, s.q_reg, s.q_pay) == (tl.index("2027Q1"), tl.index("2027Q1"), tl.index("2027Q2"))
    cell = run.cell(*REF)
    amount = 4.8 * n_out / 1000
    assert cell.quarters["div"][s.q] == pytest.approx(amount, rel=1e-12) and tl.h(s.q) == 1
    # реестр в квартале решения: вычет из регуляторного капитала сразу, в DPreg дивиденда нет
    assert cell.quarters["dpreg"][s.q] == pytest.approx(0.0, abs=1e-12)
    assert cell.quarters["dp"][s.q] - cell.quarters["dp"][s.q - 1] == pytest.approx(amount, rel=1e-9)
    assert cell.quarters["pay"][s.q_pay] >= amount - 1e-9
    # решение раньше карты: квартал решения — по карте (не раньше), даты записи раньше квартала решения не действуют
    early = _rec("2026Q4", 5.0, date(2027, 3, 22), decided=date(2027, 3, 11), pay=date(2027, 3, 29))
    run, s = slot(early)
    assert (s.q, s.q_reg, s.q_pay) == (tl.index("2027Q2"),) * 3
    # запись без дат: всё по карте — решение за 3К в 4-м квартале, вычет и выплата кварталом позже
    bare = DividendRecord(year=2026, dps=4.8, status="declared", record_date=None, last_buy_date=None, ex_date=None,
                          pay_date=None, sources=("проверка",), period="2026Q3")
    run, s = slot(bare)
    assert (s.q, s.q_reg, s.q_pay) == (2, 3, 3)
    cell = run.cell(*REF)
    assert cell.quarters["dpreg"][2] == pytest.approx(amount, rel=1e-12)     # решён, из регуляторного капитала не вычтен
    assert cell.quarters["dpreg"][3] < amount                               # вычтен кварталом позже
    # регуляторный капитал квартала решения к размеру такого дивиденда нейтрален: BV ниже, DPreg выше
    k20 = []
    for dps in (3.0, 6.0):
        k20.append(_grid(book, register=(dataclasses.replace(bare, dps=dps),)).cell(*REF).quarters["k20"][2])
    assert k20[0] == pytest.approx(k20[1], rel=1e-12)
    bv = [_grid(book, register=(dataclasses.replace(bare, dps=dps),)).cell(*REF).quarters["bv"][2] for dps in (3.0, 6.0)]
    assert bv[0] - bv[1] == pytest.approx(3.0 * n_out / 1000, rel=1e-6)


def test_register_refusals_of_the_quarterly_calendar():
    """Объявленная запись без квартала прибыли и запись за открытый квартал с решением не позже даты фактов —
    отказ: сначала правятся факты (строка истории закрывает квартал)."""
    book = plain_book((CAL,))
    no_period = dataclasses.replace(FOUR[1], period=None)
    with pytest.raises(FactsError, match="без квартала прибыли"):
        _grid(book, register=(no_period,))
    stale = dataclasses.replace(FOUR[0], decided_date=date(2026, 6, 25))
    with pytest.raises(FactsError, match="сначала правятся факты"):
        _grid(book, register=(stale,))
    # запись за закрытый квартал (отсечка после даты фактов) клетку не меняет: её дивиденд вычтен в якоре
    closed = _rec("2025Q4", 4.5, date(2026, 7, 6), decided=date(2026, 5, 14), pay=date(2026, 7, 20), status="paid")
    assert [c.quarters["bv"] for c in _grid(book, register=(closed,)).cells] == [
        c.quarters["bv"] for c in plain_run((CAL,)).cells]


# ------------------------------------------------------------------ состояние якоря (М§5.7.4)


def test_anchor_payable_declared_part_goes_to_the_queues_and_the_rest_stays():
    """Дивиденды к выплате якоря: объявленная часть закрытых кварталов выплачивается в квартале выплаты (не
    раньше первого прогнозного) и до квартала вычета стоит в регуляторном капитале; остаток — постоянное
    обязательство: не выплачивается и в регуляторный капитал не возвращается."""
    book = plain_book((CAL,))
    base = plain_run((CAL,))
    tl = base.ctx.timeline
    payable = t_facts().need("balance", "dividends_payable")
    cell = base.cell(*REF)
    assert base.ctx.prep.calendar.payable == () and cell.quarters["dpreg"][0] == 0.0
    # без объявленной части весь остаток постоянен: выплаты — только дивиденды решений клетки
    assert sum(cell.quarters["pay"][q] for q in range(1, tl.Q + 1)) == pytest.approx(
        sum(cell.quarters["div"][q] for q in range(1, tl.Q + 1)) - (cell.quarters["dp"][tl.Q] - payable), rel=1e-12)
    assert min(cell.quarters["dp"][q] for q in range(tl.Q + 1)) >= payable - 1e-9
    declared = _facts("balance", lambda d: d.update(dividends_payable_declared=[{"period": "2025Q4", "amount": 3.0}]))
    run = _grid(book, declared)
    c = run.cell(*REF)
    # по карте вычет за 4К прошлого года — до якоря: в очередь вычетов сумма не входит; выплата — в первом квартале
    assert run.ctx.prep.calendar.payable == ((1, 0, 3.0),) and c.quarters["dpreg"][0] == 0.0
    assert c.quarters["pay"][1] - cell.quarters["pay"][1] == pytest.approx(3.0, abs=1e-6)
    assert c.quarters["dp"][1] == pytest.approx(payable - 3.0, abs=1e-9)        # решение 1К выплачено в том же квартале
    assert min(c.quarters["dp"][q] for q in range(1, tl.Q + 1)) >= payable - 3.0 - 1e-9
    # даты записи реестра сильнее карты: отсечка в первом прогнозном квартале — до неё сумма в регуляторном капитале
    rec = _rec("2025Q4", 4.5, date(2026, 7, 6), decided=date(2026, 5, 14), pay=date(2026, 10, 19), status="declared")
    run = _grid(book, declared, register=(rec,))
    c2 = run.cell(*REF)
    assert run.ctx.prep.calendar.payable == ((2, 1, 3.0),)
    assert c2.quarters["dpreg"][0] == 3.0 and c2.quarters["k20"][0] - c.quarters["k20"][0] == pytest.approx(3.0, abs=1e-9)
    assert c2.quarters["pay"][2] - c.quarters["pay"][2] == pytest.approx(3.0, abs=1e-6)
    assert c2.quarters["dp"][1] == pytest.approx(payable, abs=1e-9)
    for bad, words in (([{"period": "2026Q1", "amount": 1.0}], "не закрыт до якоря"),
                       ([{"period": "2025Q4", "amount": 1.0}, {"period": "2025Q4", "amount": 1.0}], "повторяется"),
                       ([{"period": "2025Q4", "amount": payable + 0.5}], "больше дивидендов к выплате")):
        with pytest.raises(FactsError, match=words):
            _grid(book, _facts("balance", lambda d, bad=bad: d.update(dividends_payable_declared=bad)))
    # признак годового режима в квартальном не читается
    year = _facts("balance", lambda d: d.update(dividends_payable_year=2025))
    assert _grid(book, year).cell(*REF).quarters["pay"] == cell.quarters["pay"]


# ------------------------------------------------------------------ мост и дивиденд без записи (М§8.1, §14.4)


def test_bridge_dates_the_deduction_by_the_decision_quarter_of_the_record():
    """Строка моста — на запись: вычет из BV модели — конец квартала клетки решения записи (у закрытого квартала
    прибыли — дата фактов), а не квартал годового собрания; знак и «ещё не вычтен» — по дате оценки."""
    book = plain_book((CAL,))
    facts = t_facts()
    n_out = facts.need("shares", "outstanding_total")
    q1, q2 = FOUR[0], FOUR[1]

    def rows(day):
        run = _grid(book, register=(q1, q2), day=day)
        return run, {r["period"]: r for r in run.bridge_rows}

    run, got = rows(date(2026, 8, 5))
    assert (got["2026Q1"]["deducted_on"], got["2026Q2"]["deducted_on"]) == (date(2026, 9, 30), date(2026, 12, 31))
    assert got["2026Q1"]["label"] is None and got["2026Q1"]["year"] == 2026
    assert [(r["sign"], r["pending"]) for r in run.bridge_rows] == [(0, True), (0, True)]      # оба ещё внутри V0
    assert run.pending_dividend == pytest.approx((4.60 + 4.70) * n_out / 1000, rel=1e-12) and run.bridge_amount == 0.0
    run, got = rows(date(2026, 8, 20))                       # экс-дата 1К прошла, квартал решения не закрыт
    assert (got["2026Q1"]["sign"], got["2026Q1"]["pending"]) == (-1, True)
    assert run.bridge_amount == pytest.approx(-4.60 * n_out / 1000, rel=1e-12)
    run, got = rows(date(2026, 9, 30))                       # конец квартала решения: вычтен, права уже нет
    assert (got["2026Q1"]["sign"], got["2026Q1"]["pending"], got["2026Q2"]["sign"]) == (0, False, 0)
    assert run.pending_dividend == pytest.approx(4.70 * n_out / 1000, rel=1e-12)
    run, got = rows(date(2026, 12, 31))
    assert (got["2026Q2"]["sign"], got["2026Q2"]["pending"]) == (0, False) and run.pending_dividend == 0.0
    # реестр в следующем квартале после решения: с конца квартала решения по последний день покупки — +DPS × N_out
    q4 = FOUR[3]
    slow = dataclasses.replace(q4, record_date=date(2027, 7, 12), ex_date=date(2027, 7, 12), last_buy_date=date(2027, 7, 9))
    run = _grid(book, register=(slow,), day=date(2027, 7, 5))
    assert run.bridge_rows[0]["deducted_on"] == date(2027, 6, 30) and run.bridge_rows[0]["sign"] == 1
    assert run.bridge_amount == pytest.approx(5.0 * n_out / 1000, rel=1e-12) and run.pending_dividend == 0.0
    # закрытый квартал прибыли: дивиденд вычтен в якоре — строка моста стоит с даты фактов до экс-даты
    closed = _rec("2025Q4", 4.5, date(2026, 7, 6), decided=date(2026, 5, 14), pay=date(2026, 7, 20), label="за 2025 год")
    run = _grid(book, register=(closed, q1), day=date(2026, 7, 2))
    row = run.bridge_rows[0]
    assert (row["period"], row["label"], row["deducted_on"], row["sign"], row["pending"]) == (
        "2025Q4", "за 2025 год", date(2026, 6, 30), 1, False)
    assert run.bridge_amount == pytest.approx(4.5 * n_out / 1000, rel=1e-12)
    assert _grid(book, register=(closed, q1), day=date(2026, 7, 6)).bridge_amount == 0.0


def test_point_jumps_by_the_dividend_on_each_of_four_ex_dates():
    """Скачок оценки на экс-дату = −DPS × N_out / N_div — на каждой из четырёх экс-дат года; прочие записи при
    этом в мосте и в клетке не трогаются (объявленный дивиденд дисконта за управление не несёт)."""
    book = plain_book((CAL, BASIS))
    assert float(book.get("valuation.governance.discount")) > 0
    seen = set()
    for i, rec in enumerate(FOUR):
        points = []
        for shift in (0, 1):
            ex = rec.ex_date + timedelta(days=shift)
            moved = dataclasses.replace(rec, record_date=ex, ex_date=ex, last_buy_date=ex - timedelta(days=1))
            run = _grid(book, register=FOUR[:i] + (moved,) + FOUR[i + 1:], day=rec.ex_date)
            points.append(run.point)
        k = run.shares_out / run.divisor
        assert k < 0.99 and points[0] - points[1] == pytest.approx(-rec.dps * k, abs=1e-7), rec.period
        seen.add(run.ctx.clock.q0)
    assert len(seen) >= 3                                    # экс-даты в разных кварталах сетки
    # непрерывность на конце квартала решения: точка меняется на перекат дня, не на DPS и не на g × DPS
    end = date(2026, 12, 31)
    before, on, after = (_grid(book, register=FOUR, day=end + timedelta(days=d)).point for d in (-1, 0, 1))
    assert abs(on - before) < 0.5 and after == pytest.approx(on, rel=1e-12)


def test_unregistered_dividend_is_the_model_part_of_the_closed_quarters():
    """U — дивиденд, который клетки решили сами и вычли на концах кварталов сетки до даты оценки: сумма ожиданий
    ряда `div_model`; запись реестра снимает свой квартал прибыли, но не соседнее решение модели того же квартала."""
    book = plain_book((CAL,))
    tl = plain_run((CAL,)).ctx.timeline

    def u(day, register=()):
        run = _grid(book, register=register, day=day)
        prob = run.layers["analytical"].prob
        return run, lambda q: sum(prob[c.key] * c.quarters["div_model"][q] for c in run.cells)

    run, model = u(tl.end(1) - timedelta(days=1))
    assert run.unregistered_dividend == 0.0
    run, model = u(tl.end(1))
    assert model(1) > 0 and run.unregistered_dividend == pytest.approx(model(1), rel=1e-12)
    run, model = u(tl.end(2))
    assert run.unregistered_dividend == pytest.approx(model(1) + model(2), rel=1e-12)
    run, model = u(tl.end(2), FOUR[:2])                      # записи за 1К и 2К: во втором квартале остаётся решение за 3К
    prob = run.layers["analytical"].prob
    third = sum(prob[c.key] * next(d.div for d in c.decisions if d.period == "2026Q3") for c in run.cells)
    assert third > 0 and run.unregistered_dividend == pytest.approx(third, rel=1e-12)
    assert _grid(book, register=FOUR[:3], day=tl.end(2)).unregistered_dividend == 0.0


# ------------------------------------------------------------------ тождества и терминал (М§6.4, §7)


def test_ddm_equals_ri_and_the_identities_hold_with_quarterly_payouts():
    """DDM = RI — в каждой клетке при квартальных выплатах, записях реестра и любой дате оценки; тождества
    капитала, баланса и отчёта о прибыли — в каждом квартале; границы дивиденда — по суммам квартала."""
    book = plain_book((CAL,))
    for register, day in (((), None), (FOUR, date(2026, 11, 14)), (FOUR, date(2027, 6, 30)), ((), date(2029, 2, 9))):
        run = _grid(book, register=register, day=day)
        assert max(abs(c.v_ddm - c.v_ri) / abs(c.v_ri) for c in run.cells) < 1e-12
        assert not _broken(run)
        for c in run.cells:
            q_ = c.quarters
            for q in range(1, run.ctx.timeline.Q + 1):
                assert q_["bv"][q] == pytest.approx(q_["bv"][q - 1] + q_["ci"][q] - q_["div"][q], rel=1e-12)
                assert q_["dp"][q] == pytest.approx(q_["dp"][q - 1] + q_["div"][q] - q_["pay"][q], rel=1e-9, abs=1e-9)


def test_terminal_excess_leaves_out_dividends_still_in_regulatory_capital():
    """Решение за третий квартал прибыли последнего года принято в последнем квартале сетки, а его вычет из
    регуляторного капитала — за сеткой: избыток капитала терминала считается без него (иначе он роздан дважды)."""
    book, run = _on()
    tl = run.ctx.timeline
    multiple = float(book.get("valuation.terminal.excess_capital_multiple"))
    for c in run.cells:
        q_ = c.quarters
        last = next(d for d in reversed(c.decisions) if d.period == f"{tl.last_year}Q3")
        assert last.q == tl.Q and run.ctx.prep.calendar.periods[last.period].q_reg == tl.Q + 1
        dpreg, rwa = q_["dpreg"][tl.Q], q_["rwa"][tl.Q]
        assert dpreg == pytest.approx(last.div, rel=1e-12)
        x_t = multiple * min((q_["n20"][tl.Q] - dpreg / rwa - q_["req20"][tl.Q]) * rwa,
                             (c.n11_star - dpreg / rwa - q_["req11"][tl.Q]) * rwa)
        assert c.x_t == pytest.approx(x_t, rel=1e-12)
        assert c.bv_star == pytest.approx(q_["bv"][tl.Q] - c.x_t, rel=1e-12)
    assert any(c.decisions[-1].div > 1.0 for c in run.cells)
    # вычет в квартале решения (лаг вычета равен лагу решения) — DPreg на конце сетки нет, формула прежняя
    same = _grid(_book(dividends__calendar__decision_lag_quarters=2))
    assert all(c.quarters["dpreg"][tl.Q] == 0.0 for c in same.cells)


# ------------------------------------------------------------------ годовые суммы и проверки (М§5.7.5, §14)


def test_dividend_bounds_checks_the_sums_of_a_quarter():
    """Инвариант `dividend_bounds` в квартальном режиме — по суммам решений модели одного квартала: решение,
    которое вместе с соседним превышает запас, он называет; каждое по отдельности запас не превышает."""
    _, run = _on()
    cell = next(c for c in run.cells if c.key == CRISIS)
    q = next(q for q in range(1, run.ctx.timeline.Q + 1)
             if len([d for d in cell.decisions if d.q == q and d.source == "model" and not d.cut]) == 2
             and all(not d.period.endswith("Q4") for d in cell.decisions if d.q == q))
    a, b = [d for d in cell.decisions if d.q == q]
    room = a.headroom[0]
    assert a.div + b.div < room
    grow = room - (a.div + b.div) + 1.0                      # вместе — на 1 млрд ₽ больше запаса
    assert a.div + grow < room                               # по одному решению превышения не видно
    over = dataclasses.replace(a, base_div=a.base_div + grow, div=a.div + grow)
    changed = dataclasses.replace(cell, decisions=tuple(over if d is a else d for d in cell.decisions))
    bad = dataclasses.replace(run, cells=tuple(changed if c is cell else c for c in run.cells))
    found = next(f for f in check_invariants(bad) if f.name == "dividend_bounds")
    assert found.fired and f"{a.period}–{b.period}" in found.message
    # избыток — часть выплаты внутри запаса, а не добавка к границе
    rich = next(c for c in run.cells if any(d.excess > 0 for d in c.decisions))
    d = next(d for d in rich.decisions if d.excess > 0)
    more = dataclasses.replace(d, excess=d.excess + (d.headroom[0] - d.div) + 1.0, div=d.headroom[0] + 1.0)
    changed = dataclasses.replace(rich, decisions=tuple(more if x is d else x for x in rich.decisions))
    bad = dataclasses.replace(run, cells=tuple(changed if c is rich else c for c in run.cells))
    assert next(f for f in check_invariants(bad) if f.name == "dividend_bounds").fired
    assert not next(f for f in check_invariants(run) if f.name == "dividend_bounds").fired


def test_payout_cap_gate_adds_the_closed_quarters_of_the_year():
    """Гейт `payout_cap` при квартальном календаре: базовая выплата года — решения клетки за кварталы прибыли
    года плюс строки истории его закрытых кварталов на все размещённые акции."""
    book = plain_book((CAL, HISTORY))
    gate = lambda run: next(f for f in check_gates(run) if f.name == "payout_cap")  # noqa: E731
    base = gate(_grid(book))                                # фикстура не калибрована: в клетках спада гейт срабатывает
    assert base.mass < 0.5 and REF[1] == "norm" and not any(label.split("/")[1] == "norm" for label in base.cells)

    def closed(dps: float):
        def change(data):
            row = next(r for r in data["history"] if r["period"] == "2026Q1")
            row["decided_date"] = "2026-06-25"
            row["dps"]["v"] = dps
        return _facts("dividends", change)

    label = "/".join(REF)
    assert label not in gate(_grid(book, closed(4.6))).cells
    fat = gate(_grid(book, closed(15.0)))                   # 15 ₽ × 2 680 млн = 40,2 млрд ₽ за один закрытый квартал
    assert fat.fired and "2026 год" in fat.message and fat.mass > 0.99 and label in fat.cells
    # закрытая формула клетки без шока: строка истории закрытого квартала плюс базовые выплаты трёх открытых
    run = _grid(book, closed(15.0))
    cell, n_iss = run.cell(*REF), t_facts().need("shares", "issued_total")
    paid = 15.0 * n_iss / 1000 + sum(cell.dps_q[f"2026Q{h}"] for h in (2, 3, 4)) * n_iss / 1000
    assert paid > float(book.get("dividends.policy.cap")) * cell.annual["ni_sh"][0]
    assert paid - 15.0 * n_iss / 1000 < float(book.get("dividends.policy.cap")) * cell.annual["ni_sh"][0]


def test_manual_input_gate_reads_the_dividend_decision_event():
    """Гейт ручного входа при квартальном календаре: событие календаря «решение о дивиденде» за квартал прибыли
    прошло дольше срока книги, а записи `declared` или `paid` за этот квартал нет. Дата отсчёта события-оценки —
    край его окна; событие годового собрания — ветвь годового режима; закрытый квартал записи не ждёт."""
    book = plain_book((CAL,))
    days = int(book.get("checks.manual_overdue_days.dividend_register"))
    gate = lambda run, today: next(f for f in check_gates(run, today=today) if f.name == "manual_input_overdue")  # noqa: E731
    run = _grid(book)
    latest = date(2026, 12, 31)                              # событие за 3К — оценка с окном до 31 декабря
    words = "не в реестре"                                   # прочие ветви гейта (МСФО квартала) тесту не мешают
    assert words not in gate(run, latest + timedelta(days=days)).message
    late = gate(run, latest + timedelta(days=days + 1))
    assert late.fired and "решение о дивиденде 2026-12-31: запись за девять месяцев 2026 года не в реестре" in late.message
    assert words not in gate(_grid(book, register=(FOUR[2],)), latest + timedelta(days=days + 30)).message
    # запись другого квартала того же года событие не закрывает
    assert words in gate(_grid(book, register=(FOUR[1],)), latest + timedelta(days=days + 1)).message

    def events(*rows):
        return _facts("calendar", lambda d: d.update(events=list(rows)))

    agm = {"id": "agm", "kind": "agm", "date": "2026-07-01", "title": "Годовое собрание", "covers": None,
           "confirmed": True, "precision": "day", "src": "проверка"}
    old = {"id": "div-2025Q4", "kind": "dividend_decision", "date": "2026-05-14", "title": "Решение о дивиденде",
           "covers": "2025Q4", "confirmed": True, "precision": "day", "src": "проверка"}
    assert not gate(_grid(book, events(agm, old)), date(2026, 12, 1)).fired
    # при годовом календаре событие решения за квартал гейт не читает
    assert words not in gate(_grid(plain_book(), day=None), latest + timedelta(days=days + 30)).message


# ------------------------------------------------------------------ календарь прогона как объект


def test_quarter_calendar_is_one_for_the_run_and_matches_the_rule():
    """`Prepared.calendar` — один на прогон: открытые кварталы, их кварталы решения, вычета и выплаты — по карте
    и записям; годы словаря DPS — все решения года на сетке."""
    book = plain_book((CAL,))
    run = _grid(book, register=FOUR)
    tl, cal, rule = run.ctx.timeline, run.ctx.prep.calendar, lag_rule(book)
    assert rule.lags == (2, 2, 1, 2) and (rule.reg_lag, rule.pay_lag) == (2, 2) and lag_rule(plain_book()) is None
    again = quarter_calendar(run.ctx.prep.policy, t_facts(), tl, FOUR, book.get("meta.facts_date"),
                             t_facts().need("balance", "dividends_payable"))
    assert again == cal
    got = {o.period: (o.q, o.q_reg, o.q_pay, o.dps) for o in cal.open[:6]}
    assert got == {"2026Q1": (1, 1, 1, 4.60), "2026Q2": (2, 2, 2, 4.70), "2026Q3": (2, 2, 3, 4.80),
                   "2026Q4": (4, 4, 4, 5.00), "2027Q1": (5, 5, 5, None), "2027Q2": (6, 6, 6, None)}
    for o in cal.open:
        if o.dps is None:
            assert o.q == max(1, rule.q_dec(o.idx, o.h))
            assert (o.q_reg, o.q_pay) == (max(o.q, o.idx + 2), max(o.q, o.idx + 2))
    assert cal.years == tuple(range(tl.anchor_year, tl.last_year))
    assert {q: [o.period for o in v] for q, v in cal.by_q.items() if q <= 4} == {
        1: ["2026Q1"], 2: ["2026Q2", "2026Q3"], 4: ["2026Q4"]}
    assert plain_run().ctx.prep.calendar is None             # годовой календарь — без объекта


# ------------------------------------------------------------------ связка с ростом по капиталу (М§4.13.2)


def test_dividend_first_measures_the_room_at_the_minimum_growth():
    """Запас своего порядка: при `dividend_first` — при наименьшей доле прироста, и он отличается от запаса
    итоговых объёмов; инвариант границ дивиденда сверяет суммы квартала с обоими (М§4.13.2 п. 2, §14.1)."""
    book = book_from_dict(t_dict(), facts=t_facts())
    run = _grid(book)
    assert any(d.headroom_final != d.headroom[0] for c in run.cells for d in c.decisions if d.source == "model")
    assert not next(f for f in check_invariants(run) if f.name == "dividend_bounds").fired


def test_excess_is_zero_in_a_quarter_with_growth_cut():
    """Избыток и догоняющая выплата — только при несвязанном капитале: в квартале с урезанным ростом у решения
    за четвёртый квартал прибыли их нет (М§4.13.2 п. 6)."""
    book = book_from_dict(t_dict(), facts=t_facts())
    run = _grid(book)
    cut = [(c, d) for c in run.cells for d in c.decisions
           if d.source == "model" and d.period.endswith("Q4") and c.quarters["lam"][d.q] < 1 - 1e-12]
    assert cut and all(d.excess == 0.0 and d.catch == 0.0 for _, d in cut)
