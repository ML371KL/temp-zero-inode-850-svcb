"""Рост, ограниченный капиталом (М§4.13), — аналитические тесты на фикстуре `tests/fixtures/core_t`.

Проверки — тождества и закрытые формулы, выведенные из книги, фактов и рядов клетки независимо от порядка
квартала ядра (`tests/support_core_t3.py`; те же проверки зовёт мутационный набор): норматив связывающего равен
требованию с глиссадой; доля прироста — одна на все кредитные книги; запас своего порядка и запас итоговых
объёмов — оценки шага на состоянии перед кварталом; навёрстывание — раньше выплаты избытка; λ не растёт с
требованием; у ступеней пола дивиденд политики цел; выключатель возвращает прежние числа. Затем — счёт оценок шага
на квартал, выходы клетки, гейты, сводка прогона полосы, «цена правила» и строки пределов обратного расчёта.
"""

from __future__ import annotations

from collections import Counter

import pytest

from model import book_results as BR
from model import cell as C
from model import uncertainty as U
from model.book_schema import BookError
from model.capital import glide_path
from model.checks import check_gates, check_invariants
from model.grid import modal_cell, run_grid, sensitivity_overrides, year_mgmt
from model.reverse import bank_rows, excess_by_year, excess_years, no_premium_overrides, reverse_overrides, reverse_trial
from tests import support_core_t3 as S
from tests.support_core import fixture_book, fixture_facts
from tests.support_core_t import book_live, neutral_book, neutral_run, plain_book, plain_run, t_facts

tact = pytest.mark.tact                      # быстрые тесты — в такте сервера; полосы и таблицы книги — только в CI

GC = S.GC


def _first():
    """Сетка полной книги фикстуры: порядок «дивиденд по политике, рост — остаток»."""
    return S.grid_of()


def _second():
    return S.grid_of(**{f"{GC}__order": S.GROWTH_FIRST})


def _broken(run) -> list[str]:
    return [f"{f.name}: {f.message}" for f in check_invariants(run) if f.fired]


# ------------------------------------------------------------------ норматив связывающего и глиссада


@tact
def test_binding_ratio_equals_the_glided_requirement():
    """В квартале с λ_min < λ* < 1 норматив связывающего равен req* в допуске `tol`, второй — не ниже req* − tol;
    флаг решателя не поднят ни в одной клетке — при обоих порядках (М§4.13.4 п. 1)."""
    assert S.check_binding(_first()) > 100 and S.check_binding(_second()) > 50
    assert not _broken(_first()) and not _broken(_second())


@tact
def test_requirement_glides_to_the_known_steps():
    """Требование с глиссадой — формула М§4.13.1: известная ступень набирается заранее, по δ за квартал."""
    S.check_glide(_first())
    # пример методики: требование по годам 11,5 → 12,25 → 13,5 %, δ = 0,25 п.п., H = 8, с третьего квартала года
    req = [0.115] * 2 + [0.1225] * 4 + [0.135] * 6
    got = glide_path(req, 8, 0.0025)
    assert got[:8] == pytest.approx([0.12, 0.1225, 0.125, 0.1275, 0.13, 0.1325, 0.135, 0.135], abs=1e-15)
    assert glide_path(req, 0, 0.0025) == tuple(req) and glide_path(req, 8, 0.0) == tuple([0.135] * 12)


@tact
def test_tighter_tolerance_takes_one_secant_step(monkeypatch):
    """Допуск строже отклонения закрытой формулы (на фикстуре оно до 0,3 б.п.): один шаг секущей по связывающему
    нормативу доводит норматив до требования, флага решателя нет; оценок шага в таком квартале — четыре
    (М§4.13.2 п. 4). Допуск строже точности самого шага секущей — флаг решателя без отказа."""
    book = S.book_of(**{f"{GC}__tol": 1e-5})
    calls = {"step": 0, "checked": 0}
    counts: list[int] = []
    step, checked, quarter = C._Cell.step, C._Cell.checked, C._Cell.quarter_constrained
    monkeypatch.setattr(C._Cell, "step", lambda self, *a, **k: (calls.__setitem__("step", calls["step"] + 1),
                                                                 step(self, *a, **k))[1])
    monkeypatch.setattr(C._Cell, "checked", lambda self, *a, **k: (calls.__setitem__("checked", calls["checked"] + 1),
                                                                   checked(self, *a, **k))[1])

    def counted(self, st, q, star):
        before = dict(calls)
        out = quarter(self, st, q, star)
        if calls["checked"] - before["checked"] == 2:
            counts.append(calls["step"] - before["step"])
        return out

    monkeypatch.setattr(C._Cell, "quarter_constrained", counted)
    run = run_grid(book, t_facts(), book_live(book))
    assert len(counts) > 100 and set(counts) == {4}            # две оценки, проверка, шаг секущей
    assert S.check_binding(run) > 100                          # норматив связывающего — в допуске 0,1 б.п.
    monkeypatch.undo()
    strict = S.grid_of(**{f"{GC}__tol": 1e-7})
    flagged = [c for c in strict.cells if "growth_solver" in c.flags]
    assert flagged and all(c.solver and abs(gap) > 1e-7 for c in flagged for _, gap in c.solver)
    assert all(len(period) == 6 for c in flagged for period, _ in c.solver) and not _broken(strict)


@tact
def test_capital_measure_takes_the_ratio_with_the_profit_of_the_period():
    """Н20.1 ограничения — с прибылью периода: когда связывает он, требованию равен N11*, а отчётный Н20.1 (без
    неаудированной прибыли) в кварталах перед отсечкой аудита ниже требования — «пила» рост не урезает."""
    run = S.grid_of(**{"capital__mgmt_buffer__n1_1": 0.04})
    tol = float(S.rule(run)["tol"])
    by_n11 = saw = 0
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, run.ctx.timeline.Q + 1):
            if not 0 < q_["lam"][q] < 1:
                continue
            gap11, gap20 = q_["n11_star"][q] - q_["req11_glide"][q], q_["n20"][q] - q_["req20_glide"][q]
            if gap11 < gap20:
                by_n11 += 1
                assert abs(gap11) <= tol, (c.label, q, gap11)
                saw += q_["n11"][q] < q_["req11_glide"][q] - 10 * tol
    assert by_n11 > 20 and saw > 10 and S.check_binding(run)
    S.check_outputs(_first())


# ------------------------------------------------------------------ доля прироста и потенциальный путь


@tact
def test_lambda_scales_every_loan_book_with_positive_growth():
    """λ — одна на все кредитные книги с положительным потенциальным приростом; потенциальный путь — рост без
    ограничения; в году `loan_growth_override` режима потенциал — из него."""
    run = _first()
    assert S.check_lambda_on_all_books(run) > 300
    tl = run.ctx.timeline
    crisis = run.cell("N", "crisis", "schedule")
    override = run.ctx.book.get("regimes.crisis.loan_growth_override")
    for year, growth in override.items():
        for q in tl.quarters_of_year(int(year)):
            step = crisis.quarters["loans_potential"][q] / crisis.quarters["loans_potential"][q - 1]
            assert step == pytest.approx((1 + growth) ** 0.25, rel=1e-12), (year, q)


@tact
def test_book_without_potential_growth_follows_the_potential_path():
    """Книга с неположительным потенциальным приростом идёт по потенциальному пути при любой λ; если прирост
    не положителен у всех книг, урезать нечего — λ* = 1 и при нехватке капитала."""
    down = {"2026": -0.5, "2027": -0.5, "LT": 0.0, "LT_from": 2029}
    run = S.grid_of(**{"regimes__downturn__loan_growth_adj": down})
    assert S.check_lambda_on_all_books(run)
    c = run.cell("M", "downturn", "strict")
    tl = run.ctx.timeline
    for q in tl.quarters_of_year(2027):
        assert c.quarters["lam"][q] == 1.0 and c.quarters["loans"][q] < c.quarters["loans"][q - 1]
        assert c.quarters["loans"][q] == pytest.approx(c.quarters["loans_potential"][q], rel=1e-12)
    assert not _broken(run)


@tact
def test_recorded_step_is_the_step_at_the_final_volumes_and_dividends():
    """Запись шага — расчёт квартала при итоговых (λ*, c) и дивидендах; запас своего порядка: при
    `dividend_first` — оценка шага при наименьшей доле прироста, при `growth_first` — при полном росте; избыток
    — от запаса итоговых объёмов и только при неурезанном росте (М§4.13.2 пп. 2, 6, 7)."""
    assert S.check_replay(_first()) > 100
    assert S.check_replay(_second(), S.REPLAY[:3]) > 60


@tact
def test_lambda_does_not_grow_with_the_requirement():
    """λ* не растёт при росте требования — на одном и том же состоянии перед кварталом (М§4.13.4 п. 2)."""
    assert S.check_monotone(_first()) > 10
    assert S.check_monotone(_second(), S.REPLAY[:1]) > 0


@tact
def test_catch_up_closes_the_gap_before_the_excess_is_paid():
    """Навёрстывание — общая доля θ от (κ / 4) разрыва с потенциальным путём, только при полном росте и пока
    норматив не ниже требования; при κ = 0 отношение книги к потенциальному пути не растёт (М§4.13.4 п. 5)."""
    run = _first()
    assert S.check_catch_up(run) > 300
    still = S.grid_of(**{f"{GC}__catch_up_rate": 0.0})
    loans = still.ctx.prep.roles.loans
    for c in still.cells:
        assert not any(c.quarters["catch_up"][1:])
        ratio = [c.quarters["loans"][q] / c.quarters["loans_potential"][q] for q in range(still.ctx.timeline.Q + 1)]
        for b in loans:
            star = c.books[b]["balance"][0]
            prev = 1.0
            for q in range(1, still.ctx.timeline.Q + 1):
                star *= S.potential_factor(still, c.key, b, still.ctx.timeline.year(q))
                now = c.books[b]["balance"][q] / star
                assert now <= prev + 1e-12, (c.label, b, q)
                prev = now
        assert min(ratio) == pytest.approx(ratio[-1], rel=1e-9) or ratio[-1] >= min(ratio)
    # избыток капитала сначала возвращает урезанный рост: с навёрстыванием выплата избытка меньше
    rich = [(a, b) for a, b in zip(run.cells, still.cells) if sum(a.quarters["catch_up"][1:]) > 1.0
            and any(d.excess > 0 for d in b.decisions)]
    assert rich
    for a, b in rich:
        assert sum(d.excess for d in a.decisions) < sum(d.excess for d in b.decisions), a.label


# ------------------------------------------------------------------ ступени пола и порядок


@tact
def test_policy_dividend_stays_whole_at_the_floor_steps():
    """У ступеней пола (М§4.13.4 п. 3): глиссада сняла ступень требования; в клетках мягкой посадки и
    нормализации дивиденд политики вокруг квартала ступени цел и рост в квартале ступени не оборван, а без
    глиссады в тех же клетках есть и срез, и обрыв. На пути спада фикстуры (он жёстче листа режимов эмитента)
    дивиденд у ступени срезан убытками спада; на пути спада порядка листа режимов среза нет ни в одной клетке
    режимов без года шока."""
    run = _first()
    S.check_glide(run)
    S.check_steps(run)
    quiet = ("soft", "norm", "downturn")
    assert S.cuts_near_steps(run, ("downturn",)) and not S.cuts_near_steps(run, ("soft", "norm"))
    mild = S.grid_of(**{"regimes__downturn__cor": S.MILD_DOWNTURN})
    assert not S.cuts_near_steps(mild, quiet)
    assert not [c.label for c in mild.cells if c.regime in quiet and "dividend_cut" in c.flags]


@tact
def test_order_decides_what_yields_first():
    """`dividend_first`: дивиденд политики срезается только при наименьшей доле прироста; `growth_first`: рост
    урезается, только когда базового дивиденда уже нет. Инвариант границ дивиденда держится при обоих порядках."""
    S.check_orders(_first(), _second())
    for run in (_first(), _second()):
        assert not next(f for f in check_invariants(run) if f.name == "dividend_bounds").fired


@tact
def test_capital_gap_is_left_only_at_the_minimum_growth():
    """Недостаток капитала сверх урезания роста остаётся флагом `capital_gap`: в каждом квартале, где Н20.0 ниже
    пола, рост уже урезан до наименьшего, а базового дивиденда модели нет — при обоих порядках; без ограничения
    роста клеток с разрывом больше."""
    off = S.grid_of(**{f"{GC}__enabled": False})
    for run in (_first(), _second()):
        lam_min = float(S.rule(run)["min_growth_scale"])
        below = 0
        for c in run.cells:
            q_ = c.quarters
            for q in range(1, run.ctx.timeline.Q + 1):
                if q_["n20"][q] < q_["floor20"][q]:
                    below += 1
                    assert q_["lam"][q] == lam_min and "capital_gap" in c.flags, (c.label, q)
                    assert not [d for d in c.decisions if d.q == q and d.source == "model" and d.base_div > 1e-9]
        gap = {c.label for c in run.cells if "capital_gap" in c.flags}
        assert below and gap and gap < {c.label for c in off.cells if "capital_gap" in c.flags}
        assert all(label.split("/")[1] == "crisis" for label in gap)
        assert run.layers["analytical"].capital_gap_mass < off.layers["analytical"].capital_gap_mass


@tact
def test_switch_off_restores_the_previous_numbers():
    """`enabled: false` при прочих полях-числах — рост задан: те же числа, что без объекта (М§4.13.4 п. 4)."""
    S.check_disabled(_first())
    assert plain_run().ctx.prep.growth is None and _first().ctx.prep.growth is not None


@tact
def test_growth_constraint_needs_its_conditions():
    """Условия включения — в схеме: квартальный календарь и год гайденса роста до сетки; поля — в границах."""
    from tests.support_core_t import plain_dict, t_dict, put
    from model.book_schema import validate
    with pytest.raises(BookError, match="quarterly"):
        validate(plain_dict(on=(f"{GC}.enabled",)))
    with pytest.raises(BookError, match="guidance_year"):
        validate(put(t_dict(), "volumes.guidance_year", 2027))
    with pytest.raises(BookError, match="min_growth_scale"):
        validate(put(t_dict(), f"{GC}.min_growth_scale", 1.5))
    one = S.grid_of(**{f"{GC}__min_growth_scale": 1.0})      # λ_min = 1 — урезания нет, остаются глиссада и N11*
    assert all(v == 1.0 for c in one.cells for v in c.quarters["lam"][1:])
    assert not any("growth_cut" in c.flags for c in one.cells)


# ------------------------------------------------------------------ бюджет счёта


def _counted(monkeypatch, book, facts, live=None):
    """Сетка со счётом шагов клетки: всего и по кварталам прохода с ограничением роста."""
    total = [0]
    kinds: Counter = Counter()
    step, quarter = C._Cell.step, C._Cell.quarter_constrained

    def one(self, *a, **k):
        total[0] += 1
        return step(self, *a, **k)

    def per_quarter(self, st, q, star):
        before = total[0]
        row, decs, after = quarter(self, st, q, star)
        lam = row["lam"]
        kind = "inside" if 0 < lam < 1 else "minimum" if lam < 1 else "catch_up" if row["catch_up"] else "full"
        kinds[(kind, any(d.source == "model" for d in decs), total[0] - before)] += 1
        return row, decs, after

    monkeypatch.setattr(C._Cell, "step", one)
    monkeypatch.setattr(C._Cell, "quarter_constrained", per_quarter)
    run_grid(book, facts, live)
    return total[0], kinds


@tact
def test_step_is_evaluated_at_most_three_times_in_a_binding_quarter(monkeypatch):
    """Бюджет счёта (М§4.13.2): в связывающем квартале шаг считается три раза (полный рост, наименьший рост,
    проверочная полная оценка — она же запись); без решений модели и без нехватки — один; навёрстывание — ещё
    до двух. Шагов клетки на сетку формы Т — не больше трёх сеток первой формы."""
    book = neutral_book()
    total, kinds = _counted(monkeypatch, book, t_facts(), book_live(book))
    inside = {n for (kind, _, n) in kinds if kind == "inside"}
    assert inside == {3}, kinds
    assert {n for (kind, model, n) in kinds if kind == "full" and not model} == {1}
    assert max(n for (kind, model, n) in kinds if kind == "full" and model) == 3
    assert max(n for (kind, _, n) in kinds if kind == "minimum") <= 3
    assert max(n for (kind, _, n) in kinds if kind == "catch_up") <= 5
    monkeypatch.undo()
    first, _ = _counted(monkeypatch, fixture_book(), fixture_facts())
    assert first < total < 3 * first, (first, total)


# ------------------------------------------------------------------ гейты, сводка прогона


def _gate(run, name):
    return next((f for f in check_gates(run) if f.name == name), None)


@tact
def test_growth_gates_follow_their_corridors():
    """Гейты роста (М§14.2): `growth_cut` — наибольшая по годам доля урезанного роста клетки против коридора;
    `step_dividend` — срез дивиденда у ступени, только в клетках режимов без года шока (падение λ в квартале
    ступени — диагностика сообщения, не срабатывание); без своих ключей гейтов нет."""
    run = _first()
    prob = run.layers["analytical"].prob
    limit = float(run.ctx.book.get("checks.growth_cut.max_cut_share"))
    over = [c for c in run.cells if max(c.growth["cut_share"]) > limit]
    gate = _gate(run, "growth_cut")
    assert set(gate.cells) == {c.label for c in over} and gate.mass == pytest.approx(sum(prob[c.key] for c in over))
    assert gate.fired and "%" in gate.message
    loose = _gate(run_grid(run.ctx.book.with_overrides({"checks.growth_cut.max_cut_share": 0.9}), t_facts(),
                           book_live(run.ctx.book)), "growth_cut")
    assert not loose.fired and loose.mass == 0
    # гейт ступени: срабатывает срез в окне ступени; падение доли прироста больше порога — слова сообщения
    drop = float(run.ctx.book.get("checks.step_dividend.max_lam_drop"))
    quiet = tuple(r for r, rp in run.ctx.prep.regimes.items() if rp.shock_year is None)
    assert "crisis" not in quiet and len(quiet) == 3
    bad = {label for label, _ in S.cuts_near_steps(run, quiet)}
    falls = {label for label, _, _ in S.lam_drops(run, quiet, tuple(run.ctx.prep.scenarios), drop)}
    step = _gate(run, "step_dividend")
    assert set(step.cells) == bad and step.fired
    assert falls - bad and "справочно" in step.message       # клетки с одним падением λ гейт не поднимают
    assert not any(label.split("/")[1] == "crisis" for label in step.cells)
    only_cut = run.ctx.book.with_overrides({"checks.step_dividend.max_lam_drop": 1.0})
    cut_only = _gate(run_grid(only_cut, t_facts(), book_live(only_cut)), "step_dividend")
    assert set(cut_only.cells) == bad and "справочно" not in cut_only.message
    off = run.ctx.book.with_overrides({f"{GC}.enabled": False})
    names = [f.name for f in check_gates(run_grid(off, t_facts(), book_live(off)))]
    assert "step_dividend" not in names and "growth_cut" in names        # первый — по выключателю, второй — по ключу
    assert not {"growth_cut", "step_dividend", "cir_lt", "wholesale_share"} & {f.name for f in check_gates(plain_run())}


@tact
def test_rule_guards_of_the_book_cir_and_wholesale_share():
    """Сторожа правил книги (М§14.2): `cir_lt` — среднее упр. C/I модальной клетки лет от `from_year` против цели;
    `wholesale_share` — доля оптового фондирования на конец года вне коридора."""
    run = _first()
    book, ctx = run.ctx.book, run.ctx
    cfg = book.get("checks.cir_lt")
    c = run.cell(*modal_cell(book, ctx.posterior))
    row = lambda name, q: c.quarters[name][q]  # noqa: E731
    vals = [year_mgmt(ctx, "cir", y, c.annual["cir"][i], row) for i, y in enumerate(c.years) if y >= cfg["from_year"]]
    mean = sum(vals) / len(vals)
    gate = _gate(run, "cir_lt")
    assert gate.detail["mean"] == pytest.approx(mean, rel=1e-12) and gate.detail["cell"] == c.label
    assert gate.fired == (abs(mean - cfg["target"]) > cfg["tolerance"]) and gate.mass in (0.0, 1.0)
    engine = sum(v for v, y in zip(c.annual["cir"], c.years) if y >= cfg["from_year"]) / len(vals)
    assert abs(mean - engine) > 1e-6                              # упр. базис — через мост, не базис движка
    hit = book.with_overrides({"checks.cir_lt.target": round(mean, 4)})
    assert not _gate(run_grid(hit, t_facts(), book_live(hit)), "cir_lt").fired
    # доля опта: опт / (средства клиентов + опт) на концы лет; на фикстуре доля постоянна (минимум ликвидности не
    # связывает), а без премии роста средств клиентов кредиты обгоняют средства — и сторож называет такие клетки
    tl = ctx.timeline
    lo, hi = book.get("checks.wholesale_share")
    ends = [q for q in range(1, tl.Q + 1) if tl.h(q) == 4]
    share = lambda cell, q: cell.quarters["wholesale"][q] / (cell.quarters["funds"][q] + cell.quarters["wholesale"][q])  # noqa: E731
    assert not _gate(run, "wholesale_share").fired and _gate(run, "wholesale_share").mass == 0
    short = S.grid_of(volumes__funds_share_drift={"retail": 0.0, "corporate": 0.0})
    bad = [cell for cell in short.cells if any(not lo <= share(cell, q) <= hi for q in ends)]
    gate = _gate(short, "wholesale_share")
    assert 0 < len(bad) < len(short.cells) and set(gate.cells) == {cell.label for cell in bad}
    assert gate.mass == pytest.approx(sum(short.layers["analytical"].prob[cell.key] for cell in bad))
    S.check_growth_gates(run)


@tact
def test_run_summary_carries_the_growth_cut_of_the_run():
    """Сводка прогона полосы: масса клеток с урезанным ростом и ожидание наибольшей по годам доли урезанного
    роста — под весами «свой взгляд»; у книги без ограничения роста этих полей нет; хвост полосы их усредняет."""
    run = _first()
    prob = run.layers["analytical"].prob
    row = U.run_summary(run)
    assert row["growth_cut_mass"] == pytest.approx(sum(prob[c.key] for c in run.cells if "growth_cut" in c.flags))
    assert row["cut_share"] == pytest.approx(sum(prob[c.key] * max(c.growth["cut_share"]) for c in run.cells))
    assert row["gap_mass"] == pytest.approx(sum(prob[c.key] for c in run.cells if "capital_gap" in c.flags))
    assert 0 < row["cut_share"] < row["growth_cut_mass"] <= 1
    assert not set(U.GROWTH_FIELDS) & set(U.run_summary(plain_run()))
    band = U.band(run.ctx.book, t_facts(), run.ctx.live, draws=4, workers=1)
    tail = band.tail(band.lam)
    assert tail["growth_cut"]["mass"] == pytest.approx(sum(r["growth_cut_mass"] for r in band.rows) / 4)
    assert tail["growth_cut"]["cut_share"] == pytest.approx(sum(r["cut_share"] for r in band.rows) / 4)
    gate = next(f for f in check_gates(run, band=band) if f.name == "growth_cut")
    assert "в полосе рост урезан в" in gate.message and "из 4 прогонов" in gate.message


# ------------------------------------------------------------------ «цена правила» и пределы обратного расчёта


@tact
def test_rule_price_values_three_closures_of_capital():
    """«Цена правила» (М§14.5): три замыкания — выключатель и два порядка; замыкание книги — на ней самой,
    остальные — подменой одного пути; масса капитального разрыва — слой «свой взгляд»."""
    run = _first()
    book, facts, live = run.ctx.book, t_facts(), run.ctx.live
    table = BR.rule_price(book, facts, live, run)
    rows = {r["key"]: r for r in table["rows"]}
    assert list(rows) == ["unconstrained", "dividend_first", "growth_first"] and table["median_draws"] is None
    assert [r["current"] for r in table["rows"]] == [False, True, False]
    off = run_grid(book.with_overrides({f"{GC}.enabled": False}), facts, live)
    second = _second()
    for key, grid in (("unconstrained", off), ("dividend_first", run), ("growth_first", second)):
        assert rows[key]["point"] == pytest.approx(grid.point, rel=1e-12), key
        assert rows[key]["capital_gap_mass"] == pytest.approx(grid.layers["analytical"].capital_gap_mass), key
        assert rows[key]["median"] is None and rows[key]["title"] == BR.rule_title(book, key)
    # подпись первой строки — подпись книги фикстуры, две другие — слова кода; без подписи книги — слово кода
    assert rows["unconstrained"]["title"] == book.label("rule_price.unconstrained") != BR.RULE_TITLES["unconstrained"]
    assert "образца" not in rows["unconstrained"]["title"]
    assert rows["growth_first"]["title"] == BR.RULE_TITLES["growth_first"]
    assert BR.rule_title(fixture_book(), "unconstrained") == BR.RULE_TITLES["unconstrained"]
    assert rows["unconstrained"]["capital_gap_mass"] > rows["dividend_first"]["capital_gap_mass"]
    # книга с другим порядком и книга с выключателем: строка книги — своя, числа строк те же
    for changed, current in (({f"{GC}.order": "growth_first"}, "growth_first"), ({f"{GC}.enabled": False}, "unconstrained")):
        b2 = book.with_overrides(changed)
        t2 = BR.rule_price(b2, facts, live, run_grid(b2, facts, live))
        assert [r["key"] for r in t2["rows"] if r["current"]] == [current]
        for r in t2["rows"]:
            assert r["point"] == pytest.approx(rows[r["key"]]["point"], rel=1e-12), (current, r["key"])
    assert BR.rule_price(plain_book(), facts, book_live(plain_book()), plain_run())["rows"][0]["current"] is True
    assert BR.rule_closures(fixture_book()) is None                # книги без объекта раздел не касается


def test_rule_price_medians_share_the_random_numbers_of_the_band():
    """Медиана замыкания — пересчёт на общих случайных числах с привязкой к печатаемой: у замыкания книги —
    сама печатаемая медиана, у другого — она плюс сдвиг пересчёта."""
    run = _first()
    book, facts, live = run.ctx.book, t_facts(), run.ctx.live
    band = U.band(book, facts, live, draws=6, workers=1)
    anchor = U.MedianAnchor(book, facts, live, band, n=6)
    table = BR.rule_price(book, facts, live, run, anchor)
    rows = {r["key"]: r for r in table["rows"]}
    printed = band.medians(run.lam)["central"]
    assert table["median_draws"] == 6 and rows["dividend_first"]["median"] == pytest.approx(printed)
    off = U.band(book.with_overrides({f"{GC}.enabled": False}), facts, live, draws=6, workers=1)
    assert rows["unconstrained"]["median"] == pytest.approx(off.medians(run.lam)["central"], abs=1e-9)


@tact
def test_catch_up_price_is_a_reference_variant_and_its_old_key_is_not_read():
    """Ключ-справка цены навёрстывания снят: её заменяет справочный вариант списка книги. Функции и узла таблиц
    у ядра нет. Пока снятый ключ числится в схеме (его ещё несёт книга репозитория), книга с ним читается и
    считается так же, как без него; когда строка схемы уйдёт, ключ станет незнакомым."""
    from model.book_schema import RETIRED_CHECKS
    assert not hasattr(BR, "catch_up_price") and not hasattr(BR, "CATCH_UP_PRICE")
    old_key = {"checks__catch_up_price": {"rate": 0.25}}
    if "catch_up_price" in RETIRED_CHECKS:
        keyed = S.grid_of(**old_key)
        assert [c.v_ri for c in keyed.cells] == [c.v_ri for c in _first().cells] and keyed.point == _first().point
        assert [f.name for f in check_gates(keyed)] == [f.name for f in check_gates(_first())]
    else:
        with pytest.raises(BookError, match="catch_up_price"):
            S.book_of(**old_key)
    # та же цена — справочным вариантом: точка книги с подменой одного пути
    rate = f"{GC}.catch_up_rate"
    variant = [{"id": "catch_up", "title": "Навёрстывание четверти разрыва в год", "overrides": {rate: 0.5}}]
    book = S.book_of(**{"valuation__reference_variants": variant})
    run, facts = _first(), t_facts()
    row = BR.reference_variants(book, facts, run.ctx.live, run)[0]
    other = run_grid(book.with_overrides({rate: 0.5}), facts, run.ctx.live)
    assert row["point"] == pytest.approx(other.point, rel=1e-12) and row["d_point"] == pytest.approx(other.point - run.point)


@tact
def test_limits_of_the_reverse_calculation():
    """Строки пределов (М§11.3): стоимость без опережающего роста — точка книги с нулевой премией роста;
    капитал без премии — капитал на акцию делителя; срок избыточной доходности в цене — номер первого года, на
    котором накопленная приведённая стоимость остаточного дохода смеси заголовка не меньше Cap − BV."""
    run = _first()
    book, facts, live = run.ctx.book, t_facts(), run.ctx.live
    rows = {r["key"]: r for r in bank_rows(book, facts, live, run, {}, follow=True)}
    flat = book.with_overrides(no_premium_overrides(book))
    # траектория сектора остаётся траекторией с нулями (на её ключах могут стоять пути оси-связки), число — нулём
    assert all(all(x == 0.0 for k, x in v.items() if k != "LT_from") if isinstance(v, dict) else v == 0.0
               for path in ("volumes.loan_share_drift", "volumes.funds_share_drift") for v in flat.get(path).values())
    assert all(isinstance(v, dict) == isinstance(book.get(path)[key], dict)
               for path in ("volumes.loan_share_drift", "volumes.funds_share_drift") for key, v in flat.get(path).items())
    growth = rows["value_without_excess_growth"]
    assert growth["implied"] == pytest.approx(run_grid(flat, facts, live).point, rel=1e-12)
    assert growth["book"] == run.point and growth["implied"] < growth["book"] and growth["unit"] == "₽"
    lam = run.lam
    lo, hi = run.layers["macro_neutral"], run.layers["analytical"]
    bv = lo.bv_v + lam * (hi.bv_v - lo.bv_v)
    assert rows["book_value_per_share"]["implied"] == pytest.approx(bv * 1000 / run.divisor, rel=1e-12)
    assert run.divisor != run.shares_out
    years = rows["excess_return_years"]
    by_year = years["by_year"]
    tl, q0 = run.ctx.timeline, run.ctx.clock.q0
    prob = {c.key: lo.prob[c.key] + lam * (hi.prob[c.key] - lo.prob[c.key]) for c in run.cells}
    assert [r["year"] for r in by_year] == list(range(tl.year(q0), tl.last_year + 2))
    explicit = sum(prob[c.key] * c.pv_ri_explicit for c in run.cells)
    assert by_year[-2]["pv_excess_cum"] == pytest.approx(explicit, rel=1e-12)
    v = lo.v0 + lam * (hi.v0 - lo.v0)
    assert by_year[-1]["pv_excess_cum"] == pytest.approx(v - bv, rel=1e-12)          # с терминалом — V − BV точки
    c = run.cells[0]                                                                # RI_q × DF_v — по определению
    disc = run.ctx.discounts[c.world]
    q = q0 + 3
    assert c.pv_ri_q[q] == pytest.approx((c.quarters["ci"][q] - disc.k[q] * c.quarters["bv"][q - 1]) * disc.dfq[q])
    assert all(x == 0.0 for x in c.pv_ri_q[:q0])
    cap = float(book.get("meta.market_price.T")) * run.divisor / 1000
    assert years["market_excess"] == pytest.approx(cap - bv, rel=1e-12) and years["unit"] == "лет"
    first = next(i for i, r in enumerate(by_year, 1) if r["pv_excess_cum"] >= cap - bv)
    assert years["implied"] == first and years["status"] == "solved" and years["book"] is None
    assert excess_years(by_year, -1.0) == 0 and excess_years(by_year, None) is None
    assert excess_years(by_year, by_year[-1]["pv_excess_cum"] + 1.0) is None
    assert excess_years(by_year, by_year[0]["pv_excess_cum"]) == 1
    assert excess_by_year(run)[-1] == by_year[-1]


@tact
def test_buffer_sensitivity_moves_both_ratios_at_once():
    """Сдвиг «₽ за 1 п.п. запаса капитала» двигает запас менеджмента обоих нормативов на `buffer_pp`."""
    book = neutral_book()
    step = float(book.get("valuation.sensitivities.buffer_pp"))
    ov = sensitivity_overrides(book, "buffer")
    assert ov == {"capital.mgmt_buffer.n20_0": book.get("capital.mgmt_buffer.n20_0") + step,
                  "capital.mgmt_buffer.n1_1": book.get("capital.mgmt_buffer.n1_1") + step}
    moved = run_grid(book.with_overrides(ov), t_facts(), book_live(book))
    assert moved.point < neutral_run().point                          # больший запас — меньше роста и дивиденда
    with pytest.raises(BookError, match="buffer"):
        sensitivity_overrides(book, "equity")


@tact
def test_buffer_row_of_the_reverse_calculation_is_one_axis_on_both_ratios():
    """Строка обратного расчёта «запас над минимумом» — данные книги: ось вида `value` по двум путям запаса
    менеджмента; проверяемое значение ставится на оба норматива, а граница оси полосы следует за ним."""
    book = neutral_book()
    paths = ["capital.mgmt_buffer.n20_0", "capital.mgmt_buffer.n1_1"]
    ax = {"name": "Запас менеджмента над минимумом", "kind": "value", "paths": paths, "search": [0.0, 0.05],
          "range": [0.005, 0.03], "unit": "%"}
    with_row = book.with_overrides({"valuation.reverse_dcf.axes": list(book.get("valuation.reverse_dcf.axes")) + [ax]})
    assert with_row.get("valuation.reverse_dcf.axes")[-1]["paths"] == paths          # схема принимает строку
    assert reverse_overrides(book, ax, 0.04) == {paths[0]: 0.04, paths[1]: 0.04}
    trial = reverse_trial(book, ax, 0.04, follow=True)
    assert [trial.get(x) for x in paths] == [0.04, 0.04]
    band_axis = next(a for a in trial.get("valuation.uncertainty.axes") if a["paths"] == paths)
    assert band_axis["high"] == 0.04 and band_axis["low"] == 0.005
    assert run_grid(trial, t_facts(), book_live(book)).point < neutral_run().point


# ------------------------------------------------------------------ таблицы книги на полной форме (вне такта)


def test_book_results_run_on_the_projection():
    """Таблицы книги считаются на форме Т: сетка, быстрая полоса, проверки; гейты второй формы — при своих
    ключах, после общих и в порядке перечня; без ключей формы Т состав проверок прежний. «Цена правила» —
    только в полном расчёте."""
    from model.checks import FORM_GATES
    from tests.support_core_t4 import KEYLESS_GATES
    res = BR.book_results(neutral_book(), t_facts(), slow=False)
    assert len(res["cells"]) == 36 and "rule_price" not in res
    names = [c["name"] for c in res["checks"]]
    gates = [c["name"] for c in res["checks"] if c["kind"] == "gate"]
    on = tuple(g for g in FORM_GATES if g not in KEYLESS_GATES)   # включены ключами фикстуры; прочие — нет
    assert tuple(gates[-len(on):]) == on and not set(KEYLESS_GATES) & set(gates)
    assert res["nim_lt"]["cell"] == res["central_cell"]["cell"] and "stress_sign" not in res
    assert res["nim_lt"]["key"] == neutral_book().get("nii.nim_lt_target_mgmt")
    plain = [f.name for f in check_invariants(plain_run()) + check_gates(plain_run())]
    assert plain == [n for n in names if n not in FORM_GATES]     # без ключей формы Т — прежний состав проверок
    text = BR.render_run_output(BR.json.loads(BR.json.dumps(res, default=BR._default)), neutral_book())
    assert "операционная прибыль акц." in text and "Н20.0" in text and "ЦЕНА ПРАВИЛА" not in text
    # полный расчёт добавляет «цену правила»: три строки замыканий, строка книги помечена
    rule = BR.rule_price(neutral_book(), t_facts(), neutral_run().ctx.live, neutral_run())
    text = BR.render_run_output(BR.json.loads(BR.json.dumps({**res, "rule_price": rule}, default=BR._default)),
                                neutral_book())
    assert "ЦЕНА ПРАВИЛА" in text and text.count("← книга") == 1 and "Сначала уступает дивиденд" in text
    # узлов «на чём стоит заголовок» без их ключей нет: ни уровней, ни пути смеси точки, ни вариантов
    assert not {"levels", "point_path", "reference_variants", "nim_stationary", "funds_cost_to_key",
                "catch_up_price"} & set(res)
    assert "УРОВНИ ПОСЛЕ ФАЗЫ РОСТА" not in text and "ЦЕНА ПРАВИЛ И РАЗВИЛОК" not in text
