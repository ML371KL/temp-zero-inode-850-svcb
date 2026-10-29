"""Аналитические проверки роста, ограниченного капиталом (М§4.13), на фикстуре `tests/fixtures/core_t`.

Одни и те же проверки зовут тесты (`tests/test_core_t_w3.py`) и мутационный набор (`tests/mutations.py`):
каждая — тождество или закрытая формула, выведенная из книги, фактов и рядов клетки независимо от порядка
квартала ядра. Основной приём — **повтор клетки**: кварталы считаются заново шагами клетки при итоговых доле
прироста, навёрстывании и дивидендах прогона; на состоянии перед шагом заново меряются запасы капитала —
оценками шага при наименьшей доле прироста, при полном росте и при итоговых объёмах.
"""

from __future__ import annotations

import functools
import json
from typing import Any, Iterator

from model.book import Book, book_from_dict
from model.cell import _Cell, initial_state
from model.grid import GridRun, run_grid
from model.paths import Trajectory
from model.timeline import QUARTER_YEARS
from tests.support_core_t import book_live, put, t_dict, t_facts

GC = "capital.growth_constraint"
ORDER, ENABLED = f"{GC}.order", f"{GC}.enabled"
DIVIDEND_FIRST, GROWTH_FIRST = "dividend_first", "growth_first"
REL = 1e-9                                   # сверка рядов повтора с рядами прогона
# Клетки повтора: норма с ранним связыванием, спад, кризис с отменой решений, мягкая посадка без урезания.
REPLAY = (("N", "norm", "mid"), ("H", "norm", "strict"), ("M", "downturn", "schedule"), ("N", "crisis", "schedule"),
          ("N", "soft", "schedule"))
# Путь CoR спада мягче пути фикстуры (порядок листа режимов эмитента): на нём дивиденд у ступеней пола цел.
MILD_DOWNTURN = {"2026": 0.054, "2027": 0.069, "2027Q1": 0.062, "2027Q2": 0.068, "2027Q3": 0.072, "2027Q4": 0.074,
                 "2028": 0.063, "2029": 0.059, "LT": 0.059, "LT_from": 2030}


def close(a: float, b: float, rel: float = REL, abs_: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def book_of(**changes: Any) -> Book:
    """Полная книга фикстуры с заменами по точечным путям (`__` вместо точки)."""
    return _book(tuple(sorted((k.replace("__", "."), json.dumps(v)) for k, v in changes.items())))


@functools.lru_cache(maxsize=None)
def _book(changes: tuple) -> Book:
    data = t_dict()
    for dotted, value in changes:
        put(data, dotted, json.loads(value))
    return book_from_dict(data, facts=t_facts())


def grid_of(**changes: Any) -> GridRun:
    """Сетка полной книги фикстуры с заменами; реестр пуст (решения — модели)."""
    return _grid(tuple(sorted((k.replace("__", "."), json.dumps(v)) for k, v in changes.items())))


@functools.lru_cache(maxsize=None)
def _grid(changes: tuple) -> GridRun:
    book = _book(changes)
    return run_grid(book, t_facts(), book_live(book))


def rule(run: GridRun) -> dict[str, Any]:
    return dict(run.ctx.book.get(GC))


# ------------------------------------------------------------------ независимые формулы


def glide(req: list[float], lookahead: int, delta: float) -> list[float]:
    """req*_q = max по h = 0…H (r_min(q+h, Q) − h × δ) (М§4.13.1) — заново, по определению."""
    last = len(req) - 1
    out = []
    for q in range(last + 1):
        best = req[q]
        for h in range(1, lookahead + 1):
            best = max(best, req[min(q + h, last)] - h * delta)
        out.append(best)
    return out


def potential_factor(run: GridRun, key: tuple[str, str, str], book_name: str, year: int) -> float:
    """1 + m_b = (1 + g_b,Y)^0,25 (М§4.3): рост сектора мира × премия книги + поправка режима; в году
    `loan_growth_override` режима — значение переопределения."""
    book = run.ctx.book
    world, regime, _ = key
    spec = book.get(f"regimes.{regime}")
    override = spec.get("loan_growth_override") or {}
    if str(year) in override:
        g = float(override[str(year)])
    else:
        sector = book.get(f"nii.books.{book_name}.sector")
        drift = book.get("volumes.loan_share_drift")
        premium = Trajectory(drift[sector] if isinstance(drift, dict) else drift).year_value(year)
        if year > int(book.get("volumes.share_drift_until")):
            premium = 0.0
        g = ((1 + run.ctx.worlds[world].credit_growth[sector][year]) * (1 + premium) - 1
             + Trajectory(spec["loan_growth_adj"]).year_value(year))
    return (1 + g) ** QUARTER_YEARS


def room(row: dict, cell: Any, q: int) -> float:
    """Запас ограничения роста по строке оценки шага: min_j (N_j − req*_j,q) × RWA; N_11 — с прибылью периода."""
    return min((row["n20"] - cell.quarters["req20_glide"][q]) * row["rwa"],
               (row["n11_star"] - cell.quarters["req11_glide"][q]) * row["rwa"])


# ------------------------------------------------------------------ повтор клетки


def replay(run: GridRun, key: tuple[str, str, str]) -> Iterator[dict[str, Any]]:
    """Клетка заново, шагами при итоговых (λ*, c) и дивидендах прогона. На каждом квартале отдаёт словарь:
    `q`, `st` (состояние перед шагом), `walker` (клетка-счётчик), `decs` (решения квартала), `parts` и
    `reg_parts` (дивиденды: все и только записей реестра), `lam`, `extra` (навёрстывание по книгам), `star`
    (уровни потенциального пути на конец q − 1), `fac` (потенциальные множители квартала); после возврата
    управления делает шаг и кладёт его строку в `step["row"]` следующего обращения к словарю."""
    ctx, cell = run.ctx, run.cell(*key)
    tl, loans, slots = ctx.timeline, ctx.prep.roles.loans, ctx.prep.calendar.periods
    walker, st = _Cell(ctx, *key), initial_state(ctx.prep)
    star = {b: st.E[b] for b in loans}
    for q in range(1, tl.Q + 1):
        decs = [d for d in cell.decisions if d.q == q]
        parts = tuple((d.div, slots[d.period].q_pay, slots[d.period].q_reg) for d in decs)
        reg_parts = tuple((d.div, slots[d.period].q_pay, slots[d.period].q_reg) for d in decs if d.source == "register")
        fac = {b: potential_factor(run, key, b, tl.year(q)) for b in loans}
        lam = cell.quarters["lam"][q]
        extra = None
        if cell.quarters["catch_up"][q]:
            extra = {b: cell.books[b]["balance"][q] - cell.books[b]["balance"][q - 1] * fac[b] for b in loans}
            extra = {b: v for b, v in extra.items() if v > 1e-9}
        step = {"q": q, "st": st, "walker": walker, "decs": decs, "parts": parts, "reg_parts": reg_parts, "lam": lam,
                "extra": extra, "star": dict(star), "fac": fac, "cell": cell}
        yield step
        step["row"] = walker.step(st, q, sum(a for a, _, _ in parts), parts=parts, lam=lam, top_up=extra)
        star = {b: star[b] * fac[b] for b in loans}


def check_replay(run: GridRun, keys: tuple = REPLAY) -> int:
    """Запись шага совпадает с расчётом квартала при итоговых (λ*, c) и дивидендах; запасы решений — оценки шага
    на состоянии перед кварталом: H_ref — при доле своего порядка, H_fin — при итоговых объёмах без решений
    модели; базовый дивиденд — min(Σ пулов, max(0, H_ref)); избыток — доля от запаса итоговых объёмов и только при
    неурезанном росте (М§4.13.2). Возвращает число проверенных кварталов с решениями модели."""
    gr = rule(run)
    lam_min, first = float(gr["min_growth_scale"]), gr["order"] == DIVIDEND_FIRST
    tol = float(gr["tol"])
    pol = run.ctx.prep.policy
    seen = 0
    for key in keys:
        cell = run.cell(*key)
        steps = []
        for step in replay(run, key):
            q, walker, st = step["q"], step["walker"], step["st"]
            model = [d for d in step["decs"] if d.source == "model"]
            can_cut = lam_min < 1 and any(f > 1 for f in step["fac"].values())
            if model:
                seen += 1
                h_full = room(walker.evaluate(st, q, step["reg_parts"], 1.0)[0], cell, q)
                h_ref = room(walker.evaluate(st, q, step["reg_parts"], lam_min)[0], cell, q) if first and can_cut \
                    else h_full
                want, base = sum(d.want[0] for d in model), sum(d.base_div for d in model)
                assert all(close(d.headroom[0], h_ref) for d in model), (key, q, model[0].headroom[0], h_ref)
                assert close(base, min(want, max(0.0, h_ref))), (key, q, base, want, h_ref)
                assert all(d.cut == (base < want - 1e-9) for d in model), (key, q)
                same_q = sum(d.base_div for d in model if run.ctx.prep.calendar.periods[d.period].q_reg == q)
                carrier = [d for d in model if d.period.endswith("Q4")]
                if step["lam"] == 1.0:
                    h_fin = room(walker.evaluate(st, q, step["reg_parts"], 1.0, step["extra"])[0], cell, q)
                    assert all(close(d.headroom_final, h_fin, abs_=1e-6) for d in model), (key, q, h_fin)
                    for d in carrier[-1:]:
                        eps = pol.epsilon_at(d.year)
                        assert close(d.excess, eps * max(0.0, h_fin - base - d.catch), abs_=1e-6), (key, q, d.excess)
                else:
                    assert all(d.excess == 0.0 and d.catch == 0.0 for d in model), (key, q)
                    if step["lam"] > lam_min:       # принятая полная оценка: запас — отклонение норматива и ι-дивиденд
                        full = walker.evaluate(st, q, tuple((d.base_div,) + p[1:] for d, p in zip(step["decs"],
                                                                                                    step["parts"])),
                                               step["lam"])[0]
                        assert all(close(d.headroom_final, room(full, cell, q) + same_q, abs_=1e-6) for d in model)
                        assert abs(room(full, cell, q)) <= tol * full["rwa"] * (1 + 1e-9), (key, q)
                assert all(d.excess == 0.0 and d.catch == 0.0 for d in model if d not in carrier[-1:]), (key, q)
            steps.append(step)
        for step in steps:
            q, row = step["q"], step["row"]
            for name in ("bv", "ni_sh", "rwa", "n20", "n11", "n11_star", "loans", "funds", "div", "dpreg", "liquidity",
                         "securities", "wholesale", "fees", "opex", "nii", "llp"):
                assert close(row[name], cell.quarters[name][q]), (key, q, name, row[name], cell.quarters[name][q])
            assert close(sum(d.div for d in step["decs"]), cell.quarters["div"][q]), (key, q)
            assert close(sum(d.div for d in step["decs"] if d.source != "register"), cell.quarters["div_model"][q])
    assert seen
    return seen


def check_binding(run: GridRun) -> int:
    """В квартале с λ_min < λ* < 1 норматив связывающего равен требованию с глиссадой в допуске `tol`, второй —
    не ниже требования минус допуск; решатель сошёлся во всех клетках (М§4.13.4 п. 1). Возвращает число таких
    кварталов."""
    gr = rule(run)
    lam_min, tol = float(gr["min_growth_scale"]), float(gr["tol"])
    inside = 0
    for c in run.cells:
        assert "growth_solver" not in c.flags and c.solver == (), (c.label, c.solver)
        q_ = c.quarters
        for q in range(1, run.ctx.timeline.Q + 1):
            lam = q_["lam"][q]
            assert lam_min <= lam <= 1.0, (c.label, q, lam)
            if lam_min < lam < 1.0:
                inside += 1
                gaps = (q_["n20"][q] - q_["req20_glide"][q], q_["n11_star"][q] - q_["req11_glide"][q])
                assert abs(min(gaps)) <= tol and max(gaps) >= -tol, (c.label, q, gaps)
        assert ("growth_cut" in c.flags) == any(q_["lam"][q] < 1 - 1e-12 for q in range(1, run.ctx.timeline.Q + 1))
    return inside


def check_glide(run: GridRun) -> None:
    """Ряды требования с глиссадой клетки — формула М§4.13.1 на рядах требования сценария; на конце сетки
    глиссада равна требованию; прирост за квартал — не больше δ, в том числе в кварталах ступени пола."""
    gr = rule(run)
    look, delta = int(gr["lookahead_quarters"]), float(gr["glide_pp_per_quarter"])
    assert look > 0 and delta > 0
    Q = run.ctx.timeline.Q
    for s in run.ctx.book.get("capital.reg_scenarios.ids"):
        c = run.cell("N", "norm", s)
        differs = False
        for name in ("req20", "req11"):
            req = list(c.quarters[name])
            expect = glide(req, look, delta)
            got = c.quarters[f"{name}_glide"]
            assert all(close(a, b, abs_=1e-15) for a, b in zip(got, expect)), (s, name)
            assert got[Q] == req[Q] and all(g >= r for g, r in zip(got, req))
            assert all(got[q] - got[q - 1] <= delta + 1e-12 for q in range(1, Q + 1)), (s, name)
            assert max(req[q] - req[q - 1] for q in range(1, Q + 1)) > delta       # у требования ступени есть
            differs |= any(g > r + 1e-9 for g, r in zip(got, req))
        assert differs, s


def check_lambda_on_all_books(run: GridRun) -> int:
    """Доля λ — одна на все кредитные книги с положительным потенциальным приростом: в квартале без
    навёрстывания E_b,q = E_b,q−1 × (1 + λ × m_b); потенциальный путь — произведение потенциальных множителей
    (в году переопределения роста режима — из него). Возвращает число кварталов с урезанным ростом."""
    tl, loans = run.ctx.timeline, run.ctx.prep.roles.loans
    cut = mixed = 0
    for c in run.cells:
        star = {b: c.books[b]["balance"][0] for b in loans}
        for q in range(1, tl.Q + 1):
            lam = c.quarters["lam"][q]
            fac = {b: potential_factor(run, c.key, b, tl.year(q)) for b in loans}
            star = {b: star[b] * fac[b] for b in loans}
            assert close(c.quarters["loans_potential"][q], sum(star.values()), rel=1e-12), (c.label, q)
            if c.quarters["catch_up"][q]:
                continue
            cut += lam < 1
            mixed += lam < 1 and len({round(f, 9) for f in fac.values()}) > 1      # у книг разные темпы
            for b in loans:
                share = lam if fac[b] > 1 else 1.0
                expect = c.books[b]["balance"][q - 1] * (1 + share * (fac[b] - 1))
                assert close(c.books[b]["balance"][q], expect, rel=1e-12), (c.label, q, b)
    assert cut and mixed
    return cut


def check_catch_up(run: GridRun) -> int:
    """Навёрстывание — только при полном росте: добавка книги — общая доля θ ≤ 1 от (κ / 4) × разрыва с
    потенциальным путём; книга не обгоняет потенциальный путь; после навёрстывания норматив не ниже требования
    минус допуск (М§4.13.2 п. 5). Возвращает число кварталов с навёрстыванием."""
    gr = rule(run)
    kappa, tol = float(gr["catch_up_rate"]), float(gr["tol"])
    tl, loans = run.ctx.timeline, run.ctx.prep.roles.loans
    seen = throttled = 0
    for c in run.cells:
        star = {b: c.books[b]["balance"][0] for b in loans}
        for q in range(1, tl.Q + 1):
            fac = {b: potential_factor(run, c.key, b, tl.year(q)) for b in loans}
            prev = {b: c.books[b]["balance"][q - 1] for b in loans}
            star = {b: star[b] * fac[b] for b in loans}
            for b in loans:
                assert c.books[b]["balance"][q] <= star[b] * (1 + 1e-12), (c.label, q, b)
            total = c.quarters["catch_up"][q]
            if not total:
                continue
            seen += 1
            assert c.quarters["lam"][q] == 1.0 and kappa > 0, (c.label, q)
            added = {b: c.books[b]["balance"][q] - prev[b] * fac[b] for b in loans}
            full = {b: kappa * QUARTER_YEARS * (star[b] - prev[b] * fac[b]) for b in loans}
            assert close(sum(added.values()), total, rel=1e-9, abs_=1e-7), (c.label, q)
            thetas = [added[b] / full[b] for b in loans if full[b] > 1e-6]
            assert thetas and max(thetas) <= 1 + 1e-7 and max(thetas) - min(thetas) <= 1e-6, (c.label, q, thetas)
            throttled += max(thetas) < 1 - 1e-6
            gaps = (c.quarters["n20"][q] - c.quarters["req20_glide"][q],
                    c.quarters["n11_star"][q] - c.quarters["req11_glide"][q])
            assert min(gaps) >= -tol - 1e-9, (c.label, q, gaps)
    assert seen and throttled
    return seen


def check_monotone(run: GridRun, keys: tuple = REPLAY[:3], bump: float = 0.005) -> int:
    """λ* не растёт при росте требования (М§4.13.4 п. 2): на одном и том же состоянии перед кварталом доля
    прироста при требовании обоих нормативов выше на `bump` не больше исходной. Возвращает число кварталов,
    где доля стала строго меньше."""
    lower = 0
    for key in keys:
        for step in replay(run, key):
            walker, q = step["walker"], step["q"]
            base20, base11 = walker.req20g, walker.req11g
            walker.req20g = tuple(v + bump for v in base20)
            walker.req11g = tuple(v + bump for v in base11)
            try:
                row, _, _ = walker.quarter_constrained(step["st"].clone(), q, step["star"])
            finally:
                walker.req20g, walker.req11g = base20, base11
            assert row["lam"] <= step["lam"] + 1e-9, (key, q, row["lam"], step["lam"])
            lower += row["lam"] < step["lam"] - 1e-9
    assert lower
    return lower


def step_quarters(run: GridRun, scenario: str) -> list[int]:
    """Кварталы ступени пола сценария: пол хотя бы одного норматива выше, чем в предыдущем квартале."""
    sp = run.ctx.prep.scenarios[scenario]
    return [q for q in range(1, run.ctx.timeline.Q + 1)
            if sp.floor20[q] > sp.floor20[q - 1] or sp.floor11[q] > sp.floor11[q - 1]]


def cuts_near_steps(run: GridRun, regimes: tuple[str, ...]) -> list[tuple[str, str]]:
    """Решения модели со срезом дивиденда, принятые в кварталах q_s − 1 … q_s + 1 у ступени пола q_s."""
    out = []
    for c in run.cells:
        if c.regime not in regimes:
            continue
        steps = step_quarters(run, c.scenario)
        out += [(c.label, d.period) for d in c.decisions
                if d.source == "model" and d.cut and any(abs(d.q - s) <= 1 for s in steps)]
    return out


def lam_drops(run: GridRun, regimes: tuple[str, ...], scenarios: tuple[str, ...], limit: float) -> list[tuple]:
    """Кварталы ступени, где доля прироста упала к предыдущему кварталу больше чем на `limit`."""
    out = []
    for c in run.cells:
        if c.regime in regimes and c.scenario in scenarios:
            lam = c.quarters["lam"]
            out += [(c.label, s, lam[s - 1] - lam[s]) for s in step_quarters(run, c.scenario)
                    if s >= 2 and lam[s] < lam[s - 1] - limit]
    return out


def check_steps(run: GridRun) -> None:
    """Ступени пола (М§4.13.4 п. 3): глиссада сняла ступень требования; в клетках мягкой посадки и нормализации у
    решений вокруг квартала ступени дивиденд политики цел, а в клетках сценария «по графику» рост в квартале
    ступени не оборван; без глиссады (тот же расчёт с нулевым горизонтом) в тех же клетках и срез, и обрыв есть."""
    calm = ("soft", "norm")
    drop = float(run.ctx.book.get("checks.step_dividend.max_lam_drop"))
    assert not cuts_near_steps(run, calm)
    assert not lam_drops(run, calm, ("schedule",), drop)
    blind = grid_of(**{f"{GC}__lookahead_quarters": 0})
    assert cuts_near_steps(blind, calm) and lam_drops(blind, calm, ("schedule",), drop)
    for c in blind.cells:                        # без горизонта требование с глиссадой — само требование
        assert c.quarters["req20_glide"] == c.quarters["req20"] and c.quarters["req11_glide"] == c.quarters["req11"]


def check_orders(first: GridRun, second: GridRun) -> None:
    """Два порядка (М§4.13): при `dividend_first` дивиденд политики срезается только при наименьшей доле прироста
    — кроме квартала, где у одного из решений вычет из регуляторного капитала позже: его дивиденд снимает запас
    один к одному, а норматив квартала не снижает, и снятое достаётся росту. При `growth_first` рост урезается,
    только когда базового дивиденда модели уже нет, — и срез дивиденда встречается при полном росте."""
    lam_min = float(rule(first)["min_growth_scale"])
    slots = first.ctx.prep.calendar.periods
    assert rule(first)["order"] == DIVIDEND_FIRST and rule(second)["order"] == GROWTH_FIRST
    cut_first = [(c, d) for c in first.cells for d in c.decisions if d.source == "model" and d.cut]
    assert cut_first
    at_minimum = 0
    for c, d in cut_first:
        later = [x for x in c.decisions if x.q == d.q and x.source == "model" and slots[x.period].q_reg > d.q]
        assert c.quarters["lam"][d.q] == lam_min or later, (c.label, d.period)
        at_minimum += c.quarters["lam"][d.q] == lam_min
    assert at_minimum
    paid_while_cut = cut_at_full = 0
    for c in second.cells:
        for d in c.decisions:
            if d.source != "model":
                continue
            lam = c.quarters["lam"][d.q]
            paid_while_cut += lam < 1 and d.base_div > 1e-9
            cut_at_full += d.cut and lam == 1.0
    assert paid_while_cut == 0 and cut_at_full > 0
    # цена порядка: при «сначала дивиденд» рост урезан сильнее, дивиденд срезан реже
    cuts = lambda run: sum(1 for c in run.cells if "dividend_cut" in c.flags)  # noqa: E731
    share = lambda run: sum(max(c.growth["cut_share"]) for c in run.cells)  # noqa: E731
    assert cuts(first) < cuts(second) and share(first) > share(second)


def without_object() -> GridRun:
    """Сетка книги фикстуры без объекта ограничения роста (и без осей и гейтов, которым он нужен)."""
    data = t_dict()
    del data["capital"]["growth_constraint"]
    axes = data["valuation"]["uncertainty"]["axes"]
    data["valuation"]["uncertainty"]["axes"] = [a for a in axes if not any(str(p).startswith(GC) for p in a["paths"])]
    book = book_from_dict(data, facts=t_facts())
    return run_grid(book, t_facts(), book_live(book))


def check_disabled(run: GridRun) -> None:
    """Подмена одного пути `enabled: false` (прочие поля остаются числами) — рост задан: числа те же, что у
    книги без объекта; обратная подмена возвращает числа книги (М§4.13.4 п. 4)."""
    book = run.ctx.book
    off_book = book.with_overrides({ENABLED: False})
    assert off_book.get(f"{GC}.catch_up_rate") == book.get(f"{GC}.catch_up_rate")
    off = run_grid(off_book, t_facts(), book_live(off_book))
    bare = without_object()
    assert off.point == bare.point and off.point != run.point
    for a, b in zip(off.cells, bare.cells):
        assert a.quarters == b.quarters and a.dps == b.dps and a.v_ri == b.v_ri and a.growth == b.growth
        q_ = a.quarters
        assert all(v == 1.0 for v in q_["lam"][1:]) and not any(q_["catch_up"][1:])
        assert q_["loans_potential"] == q_["loans"] and q_["req20_glide"] == q_["req20"]
        assert q_["req11_glide"] == q_["req11"] and not {"growth_cut", "growth_solver"} & a.flags
        assert all(v == 0.0 for v in a.growth["cut_share"]) and a.growth["potential"] == a.growth["actual"]
    on_again = off_book.with_overrides({ENABLED: True})
    again = run_grid(on_again, t_facts(), book_live(on_again))
    assert again.point == run.point and [c.quarters for c in again.cells] == [c.quarters for c in run.cells]
    # потенциальный путь книги с ограничением — путь кредитных книг без ограничения
    for a, b in zip(run.cells, off.cells):
        assert all(close(x, y, rel=1e-12) for x, y in zip(a.quarters["loans_potential"], b.quarters["loans"]))
        assert a.quarters["funds"] == b.quarters["funds"] and a.quarters["funds_retail"] == b.quarters["funds_retail"]


def check_outputs(run: GridRun) -> None:
    """Выходы клетки (М§4.13.3): строка якоря; Н20.1 с прибылью периода; годовые ряды роста."""
    tl, prep = run.ctx.timeline, run.ctx.prep
    gap11 = float(run.ctx.book.get("capital.n11.gap_pp"))
    base = t_facts().need("balance", f"history.{tl.period(tl.quarters_of_year(tl.anchor_year)[0] - 1)}.loans")
    for c in run.cells:
        q_ = c.quarters
        assert q_["lam"][0] is None and q_["catch_up"][0] is None and q_["div_model"][0] is None
        assert q_["loans_potential"][0] == q_["loans"][0]
        sc = prep.scenarios[c.scenario]
        for q in range(0, tl.Q + 1):
            star = (q_["k11"][q] + max(q_["e_unaudited"][q], 0.0)) / q_["rwa"][q] + gap11 - sc.ded_pp11[q]
            assert close(q_["n11_star"][q], star, rel=1e-12), (c.label, q)
            assert q_["n11_star"][q] >= q_["n11"][q] - 1e-15
        assert close(c.n11_star, q_["n11_star"][tl.Q], rel=1e-12)
        loans, pot = q_["loans"], q_["loans_potential"]
        for i, y in enumerate(c.years):
            qs = tl.quarters_of_year(y)
            end, prev = qs[-1], qs[0] - 1
            inside = [q for q in qs if q >= 1]
            b_act, b_pot = (loans[prev], pot[prev]) if prev >= 0 else (base, base)
            g = c.growth
            assert close(g["potential"][i], pot[end] / b_pot - 1, rel=1e-12) and close(g["actual"][i], loans[end] / b_act - 1)
            assert close(g["cut_share"][i], 1 - loans[end] / pot[end], abs_=1e-15)
            assert close(g["catch_up"][i], sum(q_["catch_up"][q] for q in inside))
            assert g["lam_min"][i] == min(q_["lam"][q] for q in inside)
        assert set(c.growth) == {"potential", "actual", "cut_share", "catch_up", "lam_min"}


def check_shock_year(run: GridRun) -> None:
    """Год шока отменяет решения модели, принимаемые в его кварталах, и при ограничении роста (М§5.5); рост в
    эти кварталы капитал урезает как в любые другие."""
    tl = run.ctx.timeline
    seen = 0
    for c in run.cells:
        shock = run.ctx.prep.regimes[c.regime].shock_year
        for d in c.decisions:
            in_shock = shock is not None and tl.year(d.q) == shock
            assert (d.source == "crisis_skip") == in_shock, (c.label, d.period, d.source)
            if in_shock:
                seen += 1
                assert d.div == 0.0 and not d.cut and d.flags == ("crisis_skip",)
    assert seen


def check_no_excess_when_cut() -> int:
    """При урезанном росте (λ* < 1) догоняющей выплаты и избытка нет — и тогда, когда доля избытка действует с
    первого года (М§4.13.2 п. 6): остаток запаса в пределах допуска избытком не считается."""
    run = grid_of(dividends__excess__from_profit_year=2026, dividends__excess__ramp_years=1)
    cut = [(c, d) for c in run.cells for d in c.decisions
           if d.source == "model" and d.period.endswith("Q4") and c.quarters["lam"][d.q] < 1 - 1e-12]
    paid = [d for c in run.cells for d in c.decisions if d.source == "model" and d.excess > 0]
    assert len(cut) > 20 and paid and all(d.excess == 0.0 and d.catch == 0.0 for _, d in cut)
    for c in run.cells:                          # решения и ряд дивидендов клетки — одно и то же
        for q in range(1, run.ctx.timeline.Q + 1):
            assert close(sum(d.div for d in c.decisions if d.q == q), c.quarters["div"][q]), (c.label, q)
    return len(cut)


def check_budget() -> dict:
    """Счёт оценок шага на квартал (М§4.13.2): в связывающем квартале — три (полный рост, наименьший рост,
    проверочная полная оценка — она же запись шага); без решений модели и нехватки — одна; навёрстывание — ещё
    до двух. Возвращает счётчик «вид квартала, есть ли решение модели, число шагов»."""
    from collections import Counter
    book = book_of()
    total = [0]
    kinds: Counter = Counter()
    step, quarter = _Cell.step, _Cell.quarter_constrained

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

    _Cell.step, _Cell.quarter_constrained = one, per_quarter
    try:
        run_grid(book, t_facts(), book_live(book))
    finally:
        _Cell.step, _Cell.quarter_constrained = step, quarter
    assert {n for (kind, _, n) in kinds if kind == "inside"} == {3}, dict(kinds)
    assert {n for (kind, model, n) in kinds if kind == "full" and not model} == {1}, dict(kinds)
    assert max(n for (kind, model, n) in kinds if kind == "full" and model) == 3
    assert max(n for (kind, _, n) in kinds if kind == "minimum") <= 3
    assert max(n for (kind, _, n) in kinds if kind == "catch_up") <= 5
    out = dict(kinds)
    out["total"] = total[0]
    return out


def check_growth_gates(run: GridRun) -> None:
    """Гейты роста и сторожа правил книги против прямого счёта по рядам клеток (М§14.2)."""
    from model.checks import check_gates
    from model.grid import modal_cell, year_mgmt
    book, ctx, tl = run.ctx.book, run.ctx, run.ctx.timeline
    gates = {f.name: f for f in check_gates(run)}
    prob = run.layers["analytical"].prob
    limit = float(book.get("checks.growth_cut.max_cut_share"))
    over = [c for c in run.cells if max(c.growth["cut_share"]) > limit]
    assert any(c.growth["cut_share"][-1] <= limit for c in over)          # наибольшая доля — не в последнем году
    assert set(gates["growth_cut"].cells) == {c.label for c in over}
    assert close(gates["growth_cut"].mass, sum(prob[c.key] for c in over))
    drop = float(book.get("checks.step_dividend.max_lam_drop"))
    quiet = tuple(r for r, rp in ctx.prep.regimes.items() if rp.shock_year is None)
    cuts = {label for label, _ in cuts_near_steps(run, quiet)}
    falls = {label for label, _, _ in lam_drops(run, quiet, tuple(ctx.prep.scenarios), drop)}
    assert cuts and falls - cuts and set(gates["step_dividend"].cells) == cuts     # срабатывает только срез дивиденда
    assert "справочно" in gates["step_dividend"].message                           # падение λ — слова сообщения
    only_cut = book.with_overrides({"checks.step_dividend.max_lam_drop": 1.0})
    gate = next(f for f in check_gates(run_grid(only_cut, t_facts(), book_live(only_cut))) if f.name == "step_dividend")
    assert set(gate.cells) == cuts and "справочно" not in gate.message
    exact = {c.label for c in run.cells if c.regime in quiet and any(
        d.source == "model" and d.cut and d.q in step_quarters(run, c.scenario) for d in c.decisions)}
    assert exact != cuts                          # окно шире самого квартала ступени
    shocked = [c for c in run.cells if c.regime not in quiet and any(d.cut for d in c.decisions)]
    assert shocked and not {c.label for c in shocked} & set(gates["step_dividend"].cells)
    cfg = book.get("checks.cir_lt")
    c = run.cell(*modal_cell(book, ctx.posterior))
    row = lambda name, q: c.quarters[name][q]  # noqa: E731
    vals = [year_mgmt(ctx, "cir", y, c.annual["cir"][i], row) for i, y in enumerate(c.years) if y >= cfg["from_year"]]
    mean = sum(vals) / len(vals)
    engine = sum(v for v, y in zip(c.annual["cir"], c.years) if y >= cfg["from_year"]) / len(vals)
    assert close(gates["cir_lt"].detail["mean"], mean, rel=1e-12) and abs(mean - engine) > 1e-6
    assert gates["cir_lt"].fired == (abs(mean - cfg["target"]) > cfg["tolerance"])
    # доля опта: без премии роста средств клиентов кредиты обгоняют средства, и опт добирает до минимума ликвидности
    lo, hi = (float(v) for v in book.get("checks.wholesale_share"))
    ends = [q for q in range(1, tl.Q + 1) if tl.h(q) == 4]
    share = lambda cell, q: cell.quarters["wholesale"][q] / (cell.quarters["funds"][q] + cell.quarters["wholesale"][q])  # noqa: E731
    assert not gates["wholesale_share"].fired and all(lo <= share(cell, q) <= hi for cell in run.cells for q in ends)
    short = grid_of(volumes__funds_share_drift={"retail": 0.0, "corporate": 0.0})
    gate = next(f for f in check_gates(short) if f.name == "wholesale_share")
    bad = {cell.label for cell in short.cells if any(not lo <= share(cell, q) <= hi for q in ends)}
    assert bad and len(bad) < len(short.cells) and set(gate.cells) == bad
    by_funds = {cell.label for cell in short.cells
                if any(not lo <= cell.quarters["wholesale"][q] / cell.quarters["funds"][q] <= hi for q in ends)}
    assert by_funds != bad                        # знаменатель — средства клиентов вместе с оптом


def check_summary(run: GridRun) -> None:
    """Сводка прогона полосы: масса клеток с урезанным ростом и ожидание наибольшей по годам доли урезанного
    роста — под весами «свой взгляд»; масса капитального разрыва."""
    from model import uncertainty as U
    prob = run.layers["analytical"].prob
    row = U.run_summary(run)
    cut = sum(prob[c.key] for c in run.cells if "growth_cut" in c.flags)
    gap = sum(prob[c.key] for c in run.cells if "capital_gap" in c.flags)
    assert close(row["growth_cut_mass"], cut) and close(row["gap_mass"], gap) and gap < cut
    assert close(row["cut_share"], sum(prob[c.key] * max(c.growth["cut_share"]) for c in run.cells))


def check_rule_price(run: GridRun) -> None:
    """«Цена правила»: три замыкания капитала — точка и масса капитального разрыва слоя «свой взгляд»."""
    from model import book_results as BR
    book, facts, live = run.ctx.book, t_facts(), run.ctx.live
    rows = {r["key"]: r for r in BR.rule_price(book, facts, live, run)["rows"]}
    off = run_grid(book.with_overrides({ENABLED: False}), facts, live)
    second = run_grid(book.with_overrides({ORDER: GROWTH_FIRST}), facts, live)
    assert list(rows) == ["unconstrained", DIVIDEND_FIRST, GROWTH_FIRST]
    for key, grid in (("unconstrained", off), (DIVIDEND_FIRST, run), (GROWTH_FIRST, second)):
        assert close(rows[key]["point"], grid.point, rel=1e-12), key
        assert close(rows[key]["capital_gap_mass"], grid.layers["analytical"].capital_gap_mass), key
        assert rows[key]["current"] == (key == DIVIDEND_FIRST)
    assert off.layers["analytical"].capital_gap_mass != off.layers["macro_neutral"].capital_gap_mass
    assert off.point != run.point != second.point


def check_limits(run: GridRun) -> None:
    """Строки пределов обратного расчёта (М§11.3) против прямого счёта."""
    from model.reverse import bank_rows
    book, facts, live = run.ctx.book, t_facts(), run.ctx.live
    rows = {r["key"]: r for r in bank_rows(book, facts, live, run, {}, follow=True)}
    zero = {f"{path}.{k}": 0.0 for path in ("volumes.loan_share_drift", "volumes.funds_share_drift")
            for k in book.get(path)}
    flat = run_grid(book.with_overrides(zero), facts, live)
    assert close(rows["value_without_excess_growth"]["implied"], flat.point, rel=1e-12)
    lam, lo, hi = run.lam, run.layers["macro_neutral"], run.layers["analytical"]
    bv, v = lo.bv_v + lam * (hi.bv_v - lo.bv_v), lo.v0 + lam * (hi.v0 - lo.v0)
    assert close(rows["book_value_per_share"]["implied"], bv * 1000 / run.divisor, rel=1e-12)
    assert run.divisor != run.shares_out
    by_year = rows["excess_return_years"]["by_year"]
    prob = {c.key: lo.prob[c.key] + lam * (hi.prob[c.key] - lo.prob[c.key]) for c in run.cells}
    assert close(by_year[-2]["pv_excess_cum"], sum(prob[c.key] * c.pv_ri_explicit for c in run.cells), rel=1e-12)
    assert close(by_year[-1]["pv_excess_cum"], v - bv, rel=1e-12)
    tl, q0 = run.ctx.timeline, run.ctx.clock.q0
    second_year = sum(prob[c.key] * (c.quarters["ci"][q] - run.ctx.discounts[c.world].k[q] * c.quarters["bv"][q - 1])
                      * run.ctx.discounts[c.world].dfq[q]
                      for c in run.cells for q in tl.quarters_of_year(tl.year(q0) + 1))
    assert close(by_year[1]["pv_excess_cum"] - by_year[0]["pv_excess_cum"], second_year, rel=1e-9)
    cap = float(book.get("meta.market_price.T")) * run.divisor / 1000
    want = next(i for i, r in enumerate(by_year, 1) if r["pv_excess_cum"] >= cap - bv)
    assert rows["excess_return_years"]["implied"] == want
    assert close(rows["excess_return_years"]["market_excess"], cap - bv, rel=1e-12)


def check_release_nodes() -> None:
    """Узлы панели в выпуске (П§2): Н20.1 смеси с прибылью периода, вероятность клеток с урезанным ростом под
    весами «свой взгляд», мост «три прибыли», стоимость капитала года пути, «цена правила» своей версии книги,
    длины массивов в контракте."""
    import copy

    from model import book_results as BR
    from model import payload as P
    from model.checks import check_gates
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
    book, facts = book_of(), t_facts()
    run0 = run_grid(book, facts)
    table = {"book_version": str(book.get("meta.version")), "rule_price": BR.rule_price(book, facts, run0.ctx.live, run0)}
    expl = explained(check_gates(run0, today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE, results=table)
    d = P.build_payload(rel)
    run, lam = rel.run, rel.run.lam
    p_an, p_neu = run.layers["analytical"].prob, run.layers["macro_neutral"].prob
    p = {c.key: lam * p_an[c.key] + (1 - lam) * p_neu[c.key] for c in run.cells}
    req, growth = d["capital"]["requirement"], d["capital"]["growth"]
    for i, q in enumerate(range(1, P.QUARTERS_SHOWN + 1)):
        cap = lambda c: c.quarters["k11"][q] + max(c.quarters["e_unaudited"][q], 0.0)  # noqa: E731
        k = sum(p[c.key] * cap(c) for c in run.cells) / sum(p[c.key] * c.quarters["rwa"][q] for c in run.cells)
        add = sum(p[c.key] * (c.quarters["n11_star"][q] - cap(c) / c.quarters["rwa"][q]) for c in run.cells)
        assert close(req["mix"]["n11_star"][i], k + add, abs_=1.5e-6), q
        assert req["mix"]["n11_star"][i] > req["mix"]["n11"][i]
    assert p_an != p
    for i, _y in enumerate(growth["years"]):
        cut = sum(p_an[c.key] for c in run.cells if c.growth["lam_min"][i] < 1 - 1e-12)
        assert close(growth["p_cut"][i], cut, abs_=1.5e-6), i
    pnl = facts.file("pnl_quarterly")["quarters"]
    rows = d["history"]["three_profits"]
    assert rows and any(r["stake_effect"] != r["debt_interest_effect"] for r in rows)
    for r in rows:
        blk = pnl[r["period"]]["investment_block"]
        assert r["stake_effect"] == blk["adj_stake_sh"]["v"] and r["debt_interest_effect"] == blk["adj_interest_sh"]["v"]
    clock, tl = run.ctx.clock, run.ctx.timeline
    end = tl.index(f"{growth['years'][0]}Q4")
    first = sum(p[c.key] * ((1 / run.ctx.discounts[c.world].dfq[end]) ** (1 / clock.tau[end]) - 1) for c in run.cells)
    assert clock.tau[end] < 1 and close(d["paths"]["fade"]["k"][0], first, abs_=1.5e-6)
    assert [r["current"] for r in d["capital"]["rule_price"]["rows"]] == [False, True, False]
    assert P.rule_price_table(book, {**table, "book_version": "другая"}) is None
    broken = copy.deepcopy(d)
    broken["capital"]["growth"]["p_cut"] = broken["capital"]["growth"]["p_cut"][:-1]
    assert any("capital.growth" in x for x in P.validate(broken, schema=d["schema"]))


def check_buffer_sensitivity() -> None:
    """«₽ за 1 п.п. запаса капитала»: запас менеджмента обоих нормативов сдвигается на `buffer_pp`, сдвиг медианы
    приводится к одному процентному пункту."""
    from model import payload as P
    from model import uncertainty as U
    from model.grid import bank_language, sensitivity_overrides
    book, facts = book_of(**{"valuation__uncertainty__median_draws": 4}), t_facts()
    live = book_live(book)
    step = float(book.get("valuation.sensitivities.buffer_pp"))
    ov = sensitivity_overrides(book, "buffer")
    assert ov == {f"capital.mgmt_buffer.{k}": float(book.get(f"capital.mgmt_buffer.{k}")) + step for k in ("n20_0", "n1_1")}
    band = U.band(book, facts, live, draws=4, workers=1)
    anchor = U.MedianAnchor(book, facts, live, band, base=band)
    other = anchor.recompute(U.trial_book(book, ov))
    lam = band.lam
    shift = U.median_shift(band.exact_centres(lam), other.exact_centres(lam), U.rank_window(book))
    run = run_grid(book, facts, live)

    class _Part:                                 # то, что читает строка чувствительностей выпуска
        pass

    rel, x = _Part(), _Part()
    rel.sensitivities = {"buffer": {"band": other, "step": step}, "roe_pp": 0.01,
                         "cor": {"band": band, "step": 0.001, "run": run},
                         "nim": {"band": band, "step": 0.001, "run": run}}
    rel.anchor = anchor
    x.rel, x.book, x.run = rel, book, run
    assert bank_language(run, lam)["roe_tc"] is not None
    row = P._sens_at(x, lam)
    assert shift < 0 and close(row["rub_per_1pp_buffer"], shift * 0.01 / step, abs_=0.006), (row, shift)
