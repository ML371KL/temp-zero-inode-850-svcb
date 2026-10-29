"""Ветви второй формы банка, волна 1 — аналитические тесты на фикстуре `tests/fixtures/core_t`.

Каждая ветвь включается одна поверх «прежней ветви» (`tests.support_core_t.plain_dict`): 12 книг и подписи
формы Т на прежних формулах. Проверка — закрытая формула, выведенная из книги и фактов независимо от ядра:
делитель (М§8.4), связь комиссий, страхования и расходов с ростом объёма (М§4.7), премия роста по секторам
и постоянные прочие активы (М§4.3), плотность постоянных активов и множитель RWA режима (М§4.11), тест
истории выплат и гейт потолка (М§5.2, §14.2), узлы роста гайденса и оценка нормативов якоря (М§14.2, §3.3).
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import date, timedelta

import pytest

from model.book import anchor_facts, book_from_dict
from model.book_schema import BookError, FactsError
from model.checks import check_gates, check_invariants, guidance_bases, guidance_values
from model.dividends import cap_history, history_test
from model.grid import DividendRecord, LiveInputs, bank_language, divisor, live_from_book, market_cap, run_grid
from model.paths import Trajectory
from model.timeline import QUARTER_YEARS
from tests.support_core_t import book_live, plain_book, plain_dict, plain_run, put, t_facts

pytestmark = pytest.mark.tact

LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")
FUNDS = ("retail_current", "retail_term", "corp_funds")
BASIS = "valuation.shares_basis"
HISTORY = "dividends.policy.history_test"
LINKS = ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link")
GUIDANCE = "checks.guidance_items"


def _on(*keys: str):
    """Книга и сетка «прежней ветви» с включёнными ветвями `keys`."""
    return plain_book(keys), plain_run(keys)


def _facts(file: str, change) -> "object":
    """Факты фикстуры с правкой одного файла: `change(копия содержимого)` правит её на месте."""
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


def _grid(book, facts=None, register=(), day=None):
    live = book_live(book)
    if register or day is not None:
        v = day or live.valuation_date
        live = LiveInputs(valuation_date=v, prices=dict(live.prices), price_dates={t: v for t in live.prices},
                          register=tuple(register))
    return run_grid(book, facts or t_facts(), live)


def _gate(run, name: str, **kw):
    return next((f for f in check_gates(run, **kw) if f.name == name), None)


# ------------------------------------------------------------------ делитель (М§8.4)


def test_issued_divisor_scales_every_price_and_nothing_inside_the_cell():
    """N_div = размещённые − экономически собственные: цена слоя, клетки и точки — в N_out / N_div раз ниже;
    клетка, её дивиденд и акции в обращении делителя не знают."""
    base, facts = plain_run(), t_facts()
    book, run = _on(BASIS)
    n_iss, n_out = facts.need("shares", "issued_total"), facts.need("shares", "outstanding_total")
    assert base.divisor == base.shares_out == n_out                      # без ключа делитель — акции в обращении
    assert run.divisor == n_iss - facts.need("shares", "economic_treasury") and run.shares_out == n_out
    k = n_out / run.divisor
    assert 0.9 < k < 1.0
    for got, was in ((run.point, base.point), (run.low, base.low), (run.high, base.high)):
        assert got == pytest.approx(was * k, rel=1e-12)
    for a, b in zip(base.cells, run.cells):
        assert a.v_ri == b.v_ri and a.dps == b.dps and a.quarters["div"] == b.quarters["div"]
        assert run.cell_price(b) == pytest.approx(base.cell_price(a) * k, rel=1e-12)
    for name in base.layers:
        assert run.layers[name].v0 == base.layers[name].v0
        assert run.layers[name].price == pytest.approx(base.layers[name].price * k, rel=1e-12)
    assert divisor(book, facts, run.ctx.prep.af) == run.divisor


def test_market_cap_is_the_price_times_the_divisor():
    """При делителе «размещённые» капитализация — цена × N_div / 1000, одно число; без ключа — по классам
    акций в обращении. Рыночный P/B и вменённая рынком избыточная доходность идут за ней (М§8.3)."""
    base = plain_run()
    book, run = _on(BASIS)
    price = float(book.get("meta.market_price.T"))
    assert market_cap(run) == pytest.approx(price * run.divisor / 1000, rel=1e-15)
    assert market_cap(base) == pytest.approx(price * base.shares_out / 1000, rel=1e-15)
    bl = bank_language(run)
    assert bl["market_pb"] == pytest.approx(price * run.divisor / 1000 / bl["bv_v"], rel=1e-12)
    assert bl["excess_market"] == pytest.approx(price * run.divisor / 1000 - bl["bv_v"], rel=1e-12)
    assert bl["bv_v"] == bank_language(base)["bv_v"]


def test_economic_treasury_is_subtracted_only_from_the_issued_divisor():
    """Узел `shares.economic_treasury` вычитается из размещённых; при базе «в обращении» не читается; нет узла —
    ноль; `null` в узле при базе «размещённые» — отказ (null ≠ 0)."""
    facts = t_facts()
    n_iss, n_out = facts.need("shares", "issued_total"), facts.need("shares", "outstanding_total")
    held = _facts("shares", lambda d: d["economic_treasury"].update(v=85.0))
    assert _grid(plain_book((BASIS,)), held).divisor == n_iss - 85.0
    assert _grid(plain_book(), held).divisor == n_out
    assert _grid(plain_book((BASIS,)), _facts("shares", lambda d: d.pop("economic_treasury"))).divisor == n_iss
    hidden = _facts("shares", lambda d: d["economic_treasury"].update(v=None))
    assert _grid(plain_book(), hidden).divisor == n_out
    with pytest.raises(FactsError) as exc:
        _grid(plain_book((BASIS,)), hidden)
    assert "economic_treasury" in str(exc.value)


def test_share_count_adjustment_multiplies_the_divisor():
    """N_div = база × (1 + share_count_adj) — у обеих баз; капитализация по классам акций поправки не знает."""
    book, run = _on(BASIS)
    for adj in (0.02, -0.05):
        moved = _grid(book.with_overrides({"valuation.share_count_adj": adj}))
        assert moved.divisor == pytest.approx(run.divisor * (1 + adj), rel=1e-15)
        assert moved.point == pytest.approx(run.point / (1 + adj), rel=1e-12)
        assert market_cap(moved) == pytest.approx(market_cap(run) * (1 + adj), rel=1e-12)
    plain, base = plain_book(), plain_run()
    moved = _grid(plain.with_overrides({"valuation.share_count_adj": -0.05}))
    assert moved.divisor == pytest.approx(base.shares_out * 0.95, rel=1e-15) and moved.shares_out == base.shares_out
    assert moved.point == pytest.approx(base.point / 0.95, rel=1e-12) and market_cap(moved) == market_cap(base)
    for bad in (-0.5, 0.5):
        with pytest.raises(BookError):
            plain.with_overrides({"valuation.share_count_adj": bad})


def _record(year: int, dps: float, ex: date) -> DividendRecord:
    return DividendRecord(year=year, dps=dps, status="declared", record_date=ex, last_buy_date=ex - timedelta(days=1),
                          ex_date=ex, pay_date=ex + timedelta(days=14), sources=("проверка",))


def test_exdate_jump_is_minus_dps_times_outstanding_over_the_divisor():
    """Скачок на экс-дату = −DPS × N_out / N_div: мост, D_pend и вычет клетки считают запись на акции в
    обращении, а делится оценка на делитель; дисконт за управление объявленного дивиденда не касается."""
    comp = [{"id": "t", "name": "т", "value": 0.05, "sign": 1, "basis": "проверка"}]
    book = plain_book((BASIS,)).with_overrides({"valuation.governance.discount": 0.05,
                                                "valuation.governance.components": comp})
    base = plain_run((BASIS,))
    tl, n_out = base.ctx.timeline, base.shares_out
    year, dps = tl.anchor_year, 40.0
    agm_q = tl.index(f"{year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
    v = tl.end(agm_q) + timedelta(days=20)
    runs = [_grid(book, register=(_record(year, dps, ex),), day=v) for ex in (v, v + timedelta(days=1))]
    k = n_out / runs[0].divisor
    assert runs[0].point - runs[1].point == pytest.approx(-dps * k, abs=1e-6)
    assert abs(runs[0].point - runs[1].point + dps) > 1.0                  # не −DPS: делитель больше акций в обращении
    for run in runs:
        row = run.bridge_rows[0]
        assert row["amount"] == pytest.approx(dps * n_out / 1000, rel=1e-15)
        for c in run.cells:
            dec = next(d for d in c.decisions if d.year == year)
            assert dec.source == "register" and dec.div == pytest.approx(dps * n_out / 1000, rel=1e-15)
            assert c.quarters["div"][agm_q] == dec.div
    assert runs[1].bridge_amount == pytest.approx(dps * n_out / 1000) and runs[0].bridge_amount == 0.0


# ------------------------------------------------------------------ связь с объёмом (М§4.7)


def _history_end(facts, q: int, tl, key: str) -> float:
    return facts.need("balance", f"history.{tl.period(q)}.{key}")


def _volume(c, facts, tl, q: int, key: str = "loans") -> float:
    """A_q — средний остаток базы за квартал: полусумма концов; до сетки — факты, конец якоря — строка якоря."""
    end = lambda x: c.quarters[key][x] if x >= 0 else _history_end(facts, x, tl, key)  # noqa: E731
    return (end(q - 1) + end(q)) / 2


def _flow(c, facts, tl, q: int, name: str, node: str, sign: int = 1) -> float:
    return c.quarters[name][q] if q >= 1 else sign * facts.need("pnl_quarterly", f"quarters.{tl.period(q)}.{node}")


def test_fees_grow_with_the_excess_of_volume_growth_over_wages():
    """F_q = F_(q−4) × (1 + wage + спред + link × (v_q − wage)); v_q — рост г/г среднего остатка кредитных книг:
    до якоря — концы кварталов фактов, в сетке — ряд клетки."""
    base, facts = plain_run(), t_facts()
    book, run = _on("fees.volume_link")
    link, tl = float(book.get("fees.volume_link")), run.ctx.timeline
    gvw = Trajectory(book.get("fees.growth_vs_wages"))
    assert link > 0 and book.get("volumes.link_base") == "loans"
    for w in book.get("worlds.ids"):
        c0, c1, wage = base.cell(w, "norm", "schedule"), run.cell(w, "norm", "schedule"), run.ctx.worlds[w].wage
        for q in range(1, 13):
            v = _volume(c1, facts, tl, q) / _volume(c1, facts, tl, q - 4) - 1
            before = _flow(c1, facts, tl, q - 4, "fees", "fees_net")
            spread = gvw.value(tl.year(q), tl.h(q))
            assert c1.quarters["fees"][q] == pytest.approx(before * (1 + wage[q] + spread + link * (v - wage[q])),
                                                           rel=1e-12), (w, q)
        assert any(abs(c1.quarters["fees"][q] / c0.quarters["fees"][q] - 1) > 1e-3 for q in range(1, 13)), w
        f_base = facts.need("pnl_quarterly", f"quarters.{tl.period(-3)}.fees_net")
        v1 = _volume(c1, facts, tl, 1) / _volume(c1, facts, tl, -3) - 1
        assert c1.quarters["fees"][1] == pytest.approx(c0.quarters["fees"][1] + f_base * link * (v1 - wage[1]), rel=1e-12)
        assert c1.quarters["opex"][1] == c0.quarters["opex"][1] and c1.quarters["ins"][1] == c0.quarters["ins"][1]


def test_opex_link_sits_inside_the_wage_bracket_and_insurance_follows_the_same_rule():
    """C_q = C_(q−4) × (1 + wage + link_C × (v_q − wage)) × (1 + real) — произведением, как прежняя формула;
    INS_q = INS_(q−4) × (1 + wage + спред + link_I × (v_q − wage))."""
    facts = t_facts()
    book, run = _on(*LINKS)
    tl = run.ctx.timeline
    link_c, link_i = float(book.get("opex.volume_link")), float(book.get("other.insurance_volume_link"))
    real, gvw = Trajectory(book.get("opex.real_growth")), Trajectory(book.get("other.insurance_growth_vs_wages"))
    c, wage = run.cell("H", "soft", "mid"), run.ctx.worlds["H"].wage
    for q in range(1, tl.Q + 1):
        y, h = tl.year(q), tl.h(q)
        v = _volume(c, facts, tl, q) / _volume(c, facts, tl, q - 4) - 1
        opex = _flow(c, facts, tl, q - 4, "opex", "opex", -1) * (1 + wage[q] + link_c * (v - wage[q])) * (1 + real.value(y, h))
        ins = _flow(c, facts, tl, q - 4, "ins", "insurance_net") * (1 + wage[q] + gvw.value(y, h) + link_i * (v - wage[q]))
        assert c.quarters["opex"][q] == pytest.approx(opex, rel=1e-12), q
        assert c.quarters["ins"][q] == pytest.approx(ins, rel=1e-12), q
    assert real.value(tl.year(1), 1) > 0.01                                    # сумма и произведение различимы


def test_crisis_loan_stop_lowers_fees_only_with_the_link():
    """Кризисная остановка кредита (`loan_growth_override`) снижает комиссии при link > 0; без связи комиссии
    клеток одного мира от режима не зависят."""
    base = plain_run()
    book, run = _on("fees.volume_link")
    tl = run.ctx.timeline
    shock = run.ctx.prep.regimes["crisis"].shock_year
    after = [q for q in range(1, tl.Q + 1) if tl.year(q) in (shock, shock + 1)]
    for w in book.get("worlds.ids"):
        norm, crisis = run.cell(w, "norm", "schedule"), run.cell(w, "crisis", "schedule")
        assert crisis.quarters["loans"][after[-1]] < norm.quarters["loans"][after[-1]]
        assert all(crisis.quarters["fees"][q] < norm.quarters["fees"][q] for q in after), w
        flat_n, flat_c = base.cell(w, "norm", "schedule"), base.cell(w, "crisis", "schedule")
        assert flat_n.quarters["fees"] == flat_c.quarters["fees"]


def test_fees_override_year_ignores_the_link():
    """В году `fees.growth_override` комиссии считаются по переопределению — связь к ним не применяется; в
    соседних годах она работает."""
    facts = t_facts()
    book = plain_book(("fees.volume_link",))
    tl = plain_run().ctx.timeline
    year = tl.anchor_year + 1
    over = book.with_overrides({"fees.growth_override": {str(year): 0.10}})
    run, free = _grid(over), plain_run(("fees.volume_link",))
    c, f = run.cell("N", "norm", "schedule"), free.cell("N", "norm", "schedule")
    for q in tl.quarters_of_year(year):
        before = _flow(c, facts, tl, q - 4, "fees", "fees_net")
        assert c.quarters["fees"][q] == pytest.approx(before * 1.10, rel=1e-12)
        assert abs(f.quarters["fees"][q] / _flow(f, facts, tl, q - 4, "fees", "fees_net") - 1.10) > 1e-6
    q = tl.quarters_of_year(year + 1)[0]
    v = _volume(c, facts, tl, q) / _volume(c, facts, tl, q - 4) - 1
    wage = run.ctx.worlds["N"].wage[q]
    growth = 1 + wage + Trajectory(book.get("fees.growth_vs_wages")).value(year + 1, 1) + float(book.get("fees.volume_link")) * (v - wage)
    assert c.quarters["fees"][q] == pytest.approx(c.quarters["fees"][q - 4] * growth, rel=1e-12)


@pytest.mark.parametrize("base_key", ["funds", "iea"])
def test_link_base_names_the_volume(base_key):
    """`volumes.link_base`: средства клиентов — полусумма концов кварталов; процентные активы — средние активы
    шага клетки, до якоря — полусумма концов фактов."""
    facts = t_facts()
    book = plain_book(("fees.volume_link",)).with_overrides({"volumes.link_base": base_key})
    run = _grid(book)
    tl, link = run.ctx.timeline, float(book.get("fees.volume_link"))
    c, wage = run.cell("M", "norm", "strict"), run.ctx.worlds["M"].wage
    gvw = Trajectory(book.get("fees.growth_vs_wages"))

    def volume(q: int) -> float:
        if base_key == "iea" and q >= 1:
            return c.quarters["iea_avg"][q]
        return _volume(c, facts, tl, q, base_key)

    for q in range(1, 9):
        v = volume(q) / volume(q - 4) - 1
        want = _flow(c, facts, tl, q - 4, "fees", "fees_net") * (1 + wage[q] + gvw.value(tl.year(q), tl.h(q)) + link * (v - wage[q]))
        assert c.quarters["fees"][q] == pytest.approx(want, rel=1e-12), q
    other = plain_run(("fees.volume_link",)).cell("M", "norm", "strict")
    assert abs(c.quarters["fees"][4] - other.quarters["fees"][4]) > 1e-3     # база меняет число


def test_volume_history_is_required_only_with_a_link():
    """Нет конца квартала базы объёма до якоря: при ненулевой связи — отказ `FactsError` с периодом; при
    нулевых связях база не читается."""
    short = _facts("balance", lambda d: d["history"]["2025Q2"].pop("loans"))
    assert _grid(plain_book(), short).point == plain_run().point
    with pytest.raises(FactsError) as exc:
        _grid(plain_book(("fees.volume_link",)), short)
    assert "2025Q2" in str(exc.value) and "loans" in str(exc.value)
    for key in LINKS:                                                          # любая из трёх связей читает базу
        with pytest.raises(FactsError):
            _grid(plain_book((key,)), short)


# ------------------------------------------------------------------ премия роста и год гайденса (М§4.3)


def test_sector_premium_multiplies_the_growth_of_the_book():
    """g = (1 + G_сектор) × (1 + d_сектор,год) − 1 + поправка режима; d — значение года траектории сектора
    (между ключами — линейно), после `share_drift_until` — ноль."""
    book, run = _on("volumes.loan_share_drift")
    tl = run.ctx.timeline
    until = int(book.get("volumes.share_drift_until"))
    drift = {s: Trajectory(t) for s, t in book.get("volumes.loan_share_drift").items()}
    assert len({t.year_value(tl.anchor_year) for t in drift.values()}) == 3   # три разные премии
    for w, regime in (("N", "norm"), ("H", "soft"), ("M", "downturn")):
        c, growth = run.cell(w, regime, "schedule"), run.ctx.worlds[w].credit_growth
        adj = Trajectory(book.get(f"regimes.{regime}.loan_growth_adj"))
        for b in LOANS:
            sector = book.get(f"nii.books.{b}.sector")
            for q in (1, 3, 7, 11, 15, 23, 27, tl.Q):
                y = tl.year(q)
                d = drift[sector].year_value(y) if y <= until else 0.0
                want = (1 + growth[sector][y]) * (1 + d) - 1 + adj.year_value(y)
                step = c.books[b]["balance"][q] / c.books[b]["balance"][q - 1]
                assert step == pytest.approx((1 + want) ** QUARTER_YEARS, rel=1e-12), (w, b, q)
    y_mid = tl.anchor_year + 3                                              # между ключом и LT — линейный сход
    assert 0 < drift["corporate"].year_value(y_mid) < drift["corporate"].year_value(tl.anchor_year)
    assert drift["corporate"].year_value(until + 1) == 0.0


def test_funds_premium_by_segment_and_the_end_of_the_premium():
    """Средства физлиц и бизнеса растут со своей премией сегмента; год после `share_drift_until` премии не
    несёт, даже если траектория там не ноль."""
    book, run = _on("volumes.funds_share_drift")
    tl = run.ctx.timeline
    drift = {s: Trajectory(t) for s, t in book.get("volumes.funds_share_drift").items()}
    for w in book.get("worlds.ids"):
        c, growth = run.cell(w, "norm", "schedule"), run.ctx.worlds[w].funds_growth
        for q in (1, 2, 6, 10, tl.Q):
            y = tl.year(q)
            retail = c.quarters["funds_retail"][q] / c.quarters["funds_retail"][q - 1]
            corp = c.books["corp_funds"]["balance"][q] / c.books["corp_funds"]["balance"][q - 1]
            for got, seg in ((retail, "retail"), (corp, "corporate")):
                want = (1 + growth[seg][y]) * (1 + drift[seg].year_value(y))
                assert got == pytest.approx(want ** QUARTER_YEARS, rel=1e-12), (w, q, seg)
    cut = tl.anchor_year                                                    # премия действует только по этот год
    short = _grid(book.with_overrides({"volumes.share_drift_until": cut}))
    c = short.cell("N", "norm", "schedule")
    q = tl.quarters_of_year(cut + 1)[0]
    growth = short.ctx.worlds["N"].funds_growth["retail"][cut + 1]
    assert drift["retail"].year_value(cut + 1) > 0
    assert c.quarters["funds_retail"][q] / c.quarters["funds_retail"][q - 1] == pytest.approx(
        (1 + growth) ** QUARTER_YEARS, rel=1e-12)


def test_scalar_premium_is_one_for_all_books():
    """Число в ключе премии — прежняя форма: одна премия на все книги и оба сегмента средств."""
    book = plain_book().with_overrides({"volumes.loan_share_drift": 0.05, "volumes.funds_share_drift": 0.03})
    run = _grid(book)
    tl = run.ctx.timeline
    c, world = run.cell("H", "norm", "schedule"), run.ctx.worlds["H"]
    y = tl.year(1)
    for b in LOANS:
        g = world.credit_growth[book.get(f"nii.books.{b}.sector")][y]
        assert c.books[b]["balance"][1] / c.books[b]["balance"][0] == pytest.approx(
            ((1 + g) * 1.05) ** QUARTER_YEARS, rel=1e-12), b
    assert c.quarters["funds_retail"][1] / c.quarters["funds_retail"][0] == pytest.approx(
        ((1 + world.funds_growth["retail"][y]) * 1.03) ** QUARTER_YEARS, rel=1e-12)


def test_guidance_year_inside_the_grid_overrides_the_premium():
    """Год гайденса внутри сетки обходит рост сектора и премию (механизм образца); у формы Т он стоит годом
    до якоря, и ни один квартал сетки в него не попадает."""
    book, run = _on("volumes.loan_share_drift")
    tl = run.ctx.timeline
    assert int(book.get("volumes.guidance_year")) < tl.year(1)
    on = _grid(book.with_overrides({"volumes.guidance_year": tl.anchor_year,
                                    "volumes.guidance_growth": {"corporate": 0.10, "retail": 0.10}}))
    c, free = on.cell("N", "norm", "schedule"), run.cell("N", "norm", "schedule")
    q_end = tl.quarters_of_year(tl.anchor_year)[-1]
    prev = t_facts().need("balance", "prev_year_end.loans_corporate")
    assert c.books["corp_loans"]["balance"][q_end] == pytest.approx(prev * 1.10, rel=1e-12)
    assert abs(free.books["corp_loans"]["balance"][q_end] / c.books["corp_loans"]["balance"][q_end] - 1) > 0.01


# ------------------------------------------------------------------ постоянные прочие активы (М§4.3, §4.11)


def _rwa_base(book, c, q: int, fixed: float) -> float:
    dens = book.get("capital.rwa.density")
    total = sum(float(dens[b]) * c.books[b]["balance"][q] for b in LOANS)
    total += float(dens["securities"]) * c.quarters["securities"][q] + float(dens["liquidity"]) * c.quarters["liquidity"][q]
    return total + float(dens["other_assets"]) * (c.quarters["other_assets"][q] - fixed) + float(dens["other_assets_fixed"]) * fixed


def test_fixed_other_assets_do_not_grow_and_carry_their_own_density():
    """OA_q = отношение × кредиты + OA_fixed, отношение якоря — (прочие активы − OA_fixed) / кредиты; в RWA
    постоянная часть входит со своей плотностью — и на якоре тоже."""
    facts = t_facts()
    fixed = facts.need("balance", "other_assets_fixed")
    loans0 = sum(facts.need("balance", f"books.{b}") for b in LOANS)
    ratio = (facts.need("balance", "other_assets") - fixed) / loans0
    weight = 0.4
    book = plain_book(("volumes.other_assets_fixed",)).with_overrides({"capital.rwa.density.other_assets_fixed": weight})
    assert book.anchors["volumes.other_assets_fixed"] == fixed and book.get("volumes.other_assets_fixed") == fixed
    assert book.anchors["volumes.other_assets_to_loans"] == pytest.approx(ratio, rel=1e-12)
    run = _grid(book)
    tl = run.ctx.timeline
    for w, regime in (("H", "norm"), ("N", "crisis")):
        c = run.cell(w, regime, "schedule")
        for q in range(0, tl.Q + 1):
            assert c.quarters["other_assets"][q] == pytest.approx(ratio * c.quarters["loans"][q] + fixed, rel=1e-12), q
            assert c.quarters["rwa"][q] == pytest.approx(_rwa_base(book, c, q, fixed), rel=1e-12), q
            if q:
                assert c.quarters["assets"][q] == pytest.approx(c.quarters["liabilities_equity"][q], rel=1e-12)
    assert run.ctx.prep.rwa0 == pytest.approx(_rwa_base(book, run.cells[0], 0, fixed), rel=1e-12)
    growing = plain_run().cell("H", "norm", "schedule")                        # без ключа прочие активы растут целиком
    assert growing.quarters["other_assets"][tl.Q] > run.cell("H", "norm", "schedule").quarters["other_assets"][tl.Q] + 100
    zero = _grid(plain_book(("volumes.other_assets_fixed",)))                  # плотность фикстуры — ноль
    dens = float(book.get("capital.rwa.density.other_assets"))
    assert zero.ctx.prep.rwa0 == pytest.approx(run.ctx.prep.rwa0 - weight * fixed, rel=1e-12)
    assert plain_run().ctx.prep.rwa0 == pytest.approx(zero.ctx.prep.rwa0 + dens * fixed, rel=1e-12)


def test_fixed_other_assets_as_a_number_and_their_refusals():
    """Число в ключе — те же формулы; больше прочих активов якоря — отказ книги; `anchor` без узла фактов —
    отказ фактов; ненулевое значение без плотности — отказ схемы."""
    facts = t_facts()
    loans0 = sum(facts.need("balance", f"books.{b}") for b in LOANS)
    total = facts.need("balance", "other_assets")
    data = put(plain_dict(), "volumes.other_assets_fixed", 100.0)
    book = book_from_dict(data, facts=facts)
    assert book.anchors["volumes.other_assets_to_loans"] == pytest.approx((total - 100.0) / loans0, rel=1e-12)
    assert "volumes.other_assets_fixed" not in book.anchors
    with pytest.raises(BookError) as exc:
        book_from_dict(put(plain_dict(), "volumes.other_assets_fixed", total + 1.0), facts=facts)
    assert "volumes.other_assets_fixed" in str(exc.value)
    with pytest.raises(FactsError):
        book_from_dict(plain_dict(("volumes.other_assets_fixed",)), facts=_facts("balance", lambda d: d.pop("other_assets_fixed")))
    no_density = plain_dict(("volumes.other_assets_fixed",))
    del no_density["capital"]["rwa"]["density"]["other_assets_fixed"]
    with pytest.raises(BookError) as exc:
        book_from_dict(no_density, facts=facts)
    assert "capital.rwa.density.other_assets_fixed" in str(exc.value)


# ------------------------------------------------------------------ множитель RWA режима (М§4.11)


def test_regime_multiplier_scales_all_rwa_of_the_regime_and_deductions_follow():
    """RWA_q = база_q × M_r,q: множитель — значение траектории режима в квартале (год шока — 0,90, дальше линейно
    к единице); вычеты капитала идут за итоговыми RWA; клетки прочих режимов не меняются."""
    base = plain_run()
    book, run = _on("regimes.crisis.rwa_density_mult")
    tl = run.ctx.timeline
    mult = Trajectory(book.get("regimes.crisis.rwa_density_mult"))
    shock = run.ctx.prep.regimes["crisis"].shock_year
    ded20, ded11 = float(book.get("capital.n20.deductions_anchor")), float(book.get("capital.n11.deductions_anchor"))
    seen = set()
    for w in book.get("worlds.ids"):
        c, was = run.cell(w, "crisis", "mid"), base.cell(w, "crisis", "mid")
        rwa0 = c.quarters["rwa"][0]
        assert rwa0 == was.quarters["rwa"][0]                                  # якорь — факт, множителя нет
        for q in range(1, tl.Q + 1):
            m = mult.value(tl.year(q), tl.h(q))
            seen.add(round(m, 6))
            assert c.quarters["rwa"][q] == pytest.approx(_rwa_base(book, c, q, 0.0) * m, rel=1e-12), (w, q)
            assert c.quarters["ded20"][q] == pytest.approx(ded20 * c.quarters["rwa"][q] / rwa0, rel=1e-12)
            assert c.quarters["ded11"][q] == pytest.approx(ded11 * c.quarters["rwa"][q] / rwa0, rel=1e-12)
            assert c.quarters["n20"][q] == pytest.approx(
                c.quarters["k20"][q] / c.quarters["rwa"][q] + float(book.get("capital.n20.gap_pp"))
                - run.ctx.prep.scenarios["mid"].ded_pp20[q], rel=1e-12)
        for q in tl.quarters_of_year(shock):                                   # до первого решения о дивиденде баланс тот же
            assert c.quarters["rwa"][q] == pytest.approx(0.9 * was.quarters["rwa"][q], rel=1e-12)
            assert c.quarters["n20"][q] > was.quarters["n20"][q]
        for q in tl.quarters_of_year(tl.anchor_year):
            assert c.quarters["rwa"][q] == was.quarters["rwa"][q]              # ключ года якоря — единица
        for regime in ("soft", "norm", "downturn"):
            assert run.cell(w, regime, "mid").quarters == base.cell(w, regime, "mid").quarters
    assert {1.0, 0.9} <= seen and len(seen) > 3                                # год шока, возврат и единица


def test_regime_multiplier_is_allowed_for_any_regime_and_refuses_non_positive_paths():
    """Ключ допустим у любого режима; число — тоже траектория; значение не больше нуля — отказ."""
    book = plain_book()
    data = plain_dict()
    data["regimes"]["norm"]["rwa_density_mult"] = 1.1
    run = _grid(book_from_dict(data, facts=t_facts()))
    base = plain_run()
    for q in (1, run.ctx.timeline.Q):
        assert run.cell("N", "norm", "schedule").quarters["rwa"][q] == pytest.approx(
            _rwa_base(book, run.cell("N", "norm", "schedule"), q, 0.0) * 1.1, rel=1e-12)
    assert run.cell("N", "soft", "schedule").quarters == base.cell("N", "soft", "schedule").quarters
    data["regimes"]["norm"]["rwa_density_mult"] = 0.0
    with pytest.raises(BookError):
        book_from_dict(data, facts=t_facts())


# ------------------------------------------------------------------ тест истории выплат и гейт потолка (М§5.2, §14.2)


def _history(run):
    return next(f for f in check_invariants(run) if f.name == "dps_history")


def test_history_test_cap_reads_the_years_of_the_facts():
    """Вид `cap`: Σ pool_declared строк истории года ≤ cap × отчётная прибыль акционеров года; неполный год —
    строка диагностики; записи живого реестра в тест не входят."""
    book, run = _on(HISTORY)
    facts = t_facts()
    assert history_test(book) == "cap" and history_test(plain_book()) == "exact"
    found = _history(run)
    rows = {r["year"]: r for r in found.detail["rows"]}
    n_iss = facts.need("shares", "issued_total")
    assert not found.fired and rows[2024]["ok"] is True and rows[2025]["ok"] is True and rows[2026]["ok"] is None
    assert rows[2025]["pool"] == pytest.approx((3.30 + 3.50 + 3.60 + 4.50) * n_iss / 1000)
    assert rows[2025]["share"] == pytest.approx(rows[2025]["pool"] / 177.0) and rows[2025]["cap"] == 0.30
    assert rows[2026]["share"] > 0.30 and not rows[2026]["complete"]         # неполный год выше потолка — не отказ
    assert "2026" in found.message and "диагностика" in found.message and "30 %" in found.message
    with_register = run_grid(book, facts, live_from_book(book, facts))
    assert _history(with_register).detail["rows"] == found.detail["rows"]
    assert cap_history(book, facts) == found.detail["rows"]


def test_history_test_cap_fires_on_a_complete_year_over_the_cap():
    book = plain_book((HISTORY,))
    over = _facts("dividends", lambda d: d["years"]["2025"]["ni_shareholders"].update(v=130.0))
    found = _history(_grid(book, over))
    rows = {r["year"]: r for r in found.detail["rows"]}
    assert found.fired and rows[2025]["ok"] is False and rows[2024]["ok"] is True
    assert "2025" in found.message and "2024" not in found.message.split(":")[1].split(";")[0]
    edge = _facts("dividends", lambda d: d["years"]["2025"]["ni_shareholders"].update(v=39.932 / 0.30))
    assert not _history(_grid(book, edge)).fired                              # ровно на потолке — выполнен
    lower = book.with_overrides({"dividends.policy.cap": 0.25})               # потолок — ключ книги
    assert _history(_grid(lower)).fired
    open_only = _facts("dividends", lambda d: [y.update(complete=False) for y in d["years"].values()])
    found = _history(_grid(book, open_only))
    assert found.fired and "ни одного завершённого года" in found.message
    no_years = _facts("dividends", lambda d: d.pop("years"))
    found = _history(_grid(book, no_years))
    assert found.fired and "не выполнена" in found.message


def test_history_test_none_and_exact():
    """`none` — инвариант выполнен словами «выключен книгой»; без ключа — формула «до копейки» (на строках
    истории формы Т её полей нет, и проверка об этом говорит)."""
    data = put(plain_dict((HISTORY,)), HISTORY, "none")
    found = _history(_grid(book_from_dict(data, facts=t_facts())))
    assert not found.fired and found.message == "тест истории выплат выключен книгой"
    found = _history(plain_run())
    assert found.fired and "не выполнена" in found.message


def test_payout_cap_gate_compares_the_base_payout_with_the_cap():
    """Гейт `payout_cap` есть только при тесте вида `cap`. Базовая выплата года на все размещённые акции —
    доля политики от прибыли года: при потолке ниже доли гейт срабатывает в каждой клетке, где есть несрезанная
    выплата, при потолке выше — молчит; отмена выплаты кризисом и год убытка потолок не превышают."""
    assert _gate(plain_run(), "payout_cap") is None
    book, run = _on(HISTORY)
    payout = Trajectory(book.get("dividends.policy.payout")).year_value(run.ctx.timeline.anchor_year)
    quiet = _gate(run, "payout_cap")
    assert float(book.get("dividends.policy.cap")) > payout and not quiet.fired and quiet.mass == 0.0
    af = run.ctx.prep.af
    for cap in (payout - 0.005, payout - 0.05):
        low = _grid(book.with_overrides({"dividends.policy.cap": cap}))
        gate = _gate(low, "payout_cap")
        want = []
        for c in low.cells:
            for d in c.decisions:
                ni = c.annual["ni_sh"][c.years.index(d.year)] if d.year in c.years else None
                if ni is not None and d.base_div * af.n_iss / af.n_out > cap * max(ni, 0.0) + 1e-9:
                    want.append(c.label)
                    break
        assert gate.fired and list(gate.cells) == want and gate.detail["cap"] == cap
        assert {c.label for c in low.cells if c.regime != "crisis"} <= set(want)   # где выплата не срезана капиталом
        prob = low.layers["analytical"].prob
        assert gate.mass == pytest.approx(sum(prob[c.key] for c in low.cells if c.label in want))
    names = [f.name for f in check_gates(run)]
    assert names.index("payout_cap") == names.index("manual_input_overdue") + 1
    uncut = [d for c in run.cells for d in c.decisions if d.source == "model" and not d.cut and d.base > 0]
    assert uncut and all(d.base_div * af.n_iss / af.n_out == pytest.approx(payout * d.base, rel=1e-12) for d in uncut)
    skipped = [d for c in run.cells for d in c.decisions if d.source == "crisis_skip"]
    assert skipped and all(d.base_div == 0.0 for d in skipped)


# ------------------------------------------------------------------ узлы роста гайденса (М§14.2)


def test_guidance_gate_compares_the_growth_of_profit_and_dividend():
    """`op_np_growth` — прибыль акционеров года клетки к сумме четырёх кварталов прошлого года (факты);
    `dps_growth` — DPS года прибыли клетки к сумме DPS строк истории за прошлый год; цель ROE в гейт не входит."""
    book, run = _on(GUIDANCE)
    facts, tl = t_facts(), run.ctx.timeline
    year = int(facts.plain("guidance", "year"))
    gate = _gate(run, "guidance_gap")
    assert set(gate.detail["bands"]) == {"op_np_growth", "dps_growth"}        # узлы без числа и цель ROE — вне гейта
    ni_prev = sum(facts.need("pnl_quarterly", f"quarters.{year - 1}Q{h}.ni_shareholders") for h in (1, 2, 3, 4))
    dps_prev = 3.30 + 3.50 + 3.60 + 4.50
    bases = guidance_bases(run, year, ("op_np_growth", "dps_growth"))
    assert bases == {"op_np_growth": pytest.approx(ni_prev), "dps_growth": pytest.approx(dps_prev)}
    assert guidance_bases(run, year, ("roe", "nim")) == {}
    low = []
    for c in run.cells:
        got = guidance_values(run, c, year, bases)
        ni = sum(facts.need("pnl_quarterly", f"quarters.{tl.period(q)}.ni_shareholders") if q <= 0
                 else c.quarters["ni_sh"][q] for q in tl.quarters_of_year(year))
        assert got["op_np_growth"] == pytest.approx(ni / ni_prev - 1, rel=1e-12)
        assert got["dps_growth"] == pytest.approx(c.dps[year] / dps_prev - 1, rel=1e-12)
        assert "op_np_growth" not in guidance_values(run, c, year)             # без баз узлов роста нет
        if got["op_np_growth"] < 0.20 or got["dps_growth"] < 0.20:
            low.append(c.label)
    assert list(gate.cells) == low and gate.fired == bool(low)
    for words in ("рост операционной прибыли", "рост дивиденда на акцию"):
        assert (words in gate.message) == any(words == it["words"] and it["key"] in gate.detail["outside"]
                                              for it in book.get(GUIDANCE))
    assert _gate(plain_run(), "guidance_gap").detail["bands"] == {}


def test_guidance_gate_without_the_base_of_the_previous_year_is_not_read():
    """Нет прибыли квартала прошлого года или строк истории дивидендов за него — находка «гайденс не прочитан»
    без отказа; узел без числа базы не требует."""
    book = plain_book((GUIDANCE,))
    hole = _facts("pnl_quarterly", lambda d: d["quarters"]["2025Q1"]["ni_shareholders"].update(v=None, calc="не раскрыто"))
    gate = _gate(_grid(book, hole), "guidance_gap")
    assert not gate.fired and gate.message.startswith("гайденс не прочитан") and "2025Q1" in gate.message
    no_rows = _facts("dividends", lambda d: d.update(history=[r for r in d["history"] if r["year"] != 2025]))
    gate = _gate(_grid(book, no_rows), "guidance_gap")
    assert not gate.fired and "гайденс не прочитан" in gate.message and "2025" in gate.message
    silent = _facts("guidance", lambda d: [d["items"][k].update(v=None, calc="не раскрыто") for k in ("op_np_growth", "dps_growth")])
    gate = _gate(_grid(book, _facts_merge(hole, silent)), "guidance_gap")
    assert not gate.fired and gate.detail["bands"] == {} and "внутри гайденса" in gate.message


def _facts_merge(a, b):
    """Факты `a` с файлами, которые в `b` отличаются от фикстуры."""
    base = t_facts()
    changed = {k: v for k, v in b.files.items() if v is not base.files[k]}
    return dataclasses.replace(a, files={**a.files, **changed})


# ------------------------------------------------------------------ оценка нормативов якоря (М§3.3, §14.2)


def _estimated(slot: str = "n20_0"):
    return _facts("capital", lambda d: d[slot].update(estimated=True, estimate={"bank_value": 0.125, "spread": 0.004,
                                                                                  "spread_as_of": "2026-03-31"}))


def _form_event(**extra) -> dict:
    return {"id": "form805-2026Q2", "kind": "form805", "date": "2026-08-20", "title": "Форма 0409805 на 1 июля 2026 года",
            "covers": "2026Q2", "confirmed": False, "precision": "window", "src": "проверка", **extra}


def _with_events(facts, *events):
    data = copy.deepcopy(facts.files["calendar"])
    data["events"] = list(events)
    return dataclasses.replace(facts, files={**facts.files, "calendar": data})


def test_estimated_capital_slot_is_read_from_the_facts():
    books = plain_book().get("nii.books")
    assert anchor_facts(t_facts(), books).estimated == ()
    assert anchor_facts(_estimated(), books).estimated == ("n20_0",)
    assert anchor_facts(_estimated("n1_1_bank"), books).estimated == ("n1_1_bank",)
    explicit = _facts("capital", lambda d: d["n20_0"].update(estimated=False))
    assert anchor_facts(explicit, books).estimated == ()


def test_capital_form_branch_of_the_manual_input_gate():
    """Форма с нормативами группы за период якоря вышла, а норматив якоря ещё стоит оценкой дольше срока книги —
    гейт ручного входа срабатывает; без оценки, без ключа срока и для формы другого периода — молчит."""
    book = plain_book().with_overrides({"checks.manual_overdue_days": {
        **plain_book().get("checks.manual_overdue_days"), "capital_form": 7}})
    day = date(2026, 8, 20)
    est = _with_events(_estimated(), _form_event())

    def gate(facts, today, b=book):
        return _gate(_grid(b, facts), "manual_input_overdue", today=today)

    late = gate(est, day + timedelta(days=8))
    assert late.fired and late.mass == 1.0 and "форма 0409805 на 1 июля 2026 года" in late.message
    assert "оценка нормативов якоря не заменена фактом" in late.message
    assert not gate(est, day + timedelta(days=7)).fired                       # срок — включительно
    assert not gate(_with_events(t_facts(), _form_event()), day + timedelta(days=30)).fired        # норматив — факт
    assert not gate(_with_events(_estimated(), _form_event(covers="2026Q1")), day + timedelta(days=30)).fired
    assert not gate(est, day + timedelta(days=30), plain_book()).fired        # ключа срока нет — ветви нет
    assert gate(_with_events(_estimated("n1_1_bank"), _form_event()), day + timedelta(days=8)).fired


def test_overdue_of_an_estimated_event_is_measured_from_its_latest_date():
    """У события с `estimated: true` просрочка меряется от `latest`, без `latest` ветвь не срабатывает; у
    события без `estimated` — от `date` (М§14.2)."""
    book = plain_book().with_overrides({"checks.manual_overdue_days": {
        **plain_book().get("checks.manual_overdue_days"), "capital_form": 7}})
    window = _form_event(estimated=True, earliest="2026-08-10", latest="2026-09-05")

    def fired(event, today):
        return _gate(_grid(book, _with_events(_estimated(), event)), "manual_input_overdue", today=today).fired

    assert not fired(window, date(2026, 9, 12)) and fired(window, date(2026, 9, 13))
    assert fired(_form_event(), date(2026, 8, 28))                             # без оценки даты — от date
    no_latest = {k: v for k, v in window.items() if k != "latest"}
    assert not fired(no_latest, date(2026, 12, 31))
    ifrs = {"id": "ifrs-2026Q3", "kind": "ifrs", "date": "2026-11-19", "title": "МСФО", "covers": "2026Q3",
            "estimated": True, "earliest": "2026-11-01", "latest": "2026-11-30"}
    days = int(book.get("checks.manual_overdue_days.ifrs_fact"))
    edge = date(2026, 11, 30) + timedelta(days=days)
    assert not fired(ifrs, edge) and fired(ifrs, edge + timedelta(days=1))
