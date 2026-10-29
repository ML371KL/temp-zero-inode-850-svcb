"""Проверки связки полосы и новых гейтов на фикстуре `tests/fixtures/core_t`.

Одни и те же проверки зовут тесты (`tests/test_core_t_w4.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество или закрытая формула, выведенная из книги, фактов и рядов клетки независимо от кода ядра:

* **связка** (ось вида `bundle`, М§10): значение пути = книга + |s| × (конец − книга); в прогон связка входит
  приращением и складывается со сдвигом оси вида `shift` на том же пути; положение ноль возвращает книгу бит
  в бит; общий путь с осью вида `value`, `dict` или с другой связкой — отказ;
* **печатаемая маржа после фазы роста** и гейт `nim_lt` (М§14.2): среднее годовых упр. ЧПМ модальной клетки;
* **гейты знака** `volume_sign` и `stress_sign` (М§4.5, §14.2): число гейта пересчитывается полными сетками;
* **допуск гейта `payout_cap`**: выплата ровно на потолке — не превышение, допуск книги — в долях прибыли;
* **закрытый квартал без своей строки истории** даёт ноль в годовой сумме DPS (М§5.7.5);
* **обратный расчёт** (М§11.2): оба конца оси идут за проверяемым значением; корень на краю отрезка поиска.

Ключ цели печатаемой маржи `checks.nim_lt` в книге фикстуры стоит; ключи гейтов знака — нет: число каждого из
них стоит двух-трёх сеток, и гейт в каждой книге каждого теста растил бы время набора такта. Проверки включают
их подменой — `GATE_KEYS` (значения фикстуры, не книги); тем же словарём их включает тест другого потока.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Callable

from model import uncertainty as U
from model.book import Book, book_from_dict
from model.book_schema import BookError
from model.checks import Finding, check_gates, sign_numbers
from model.grid import (GridRun, live_from_book, modal_cell, point_probabilities, printed_nim_lt, run_grid,
                        stress_sign_test, volume_sign_test, world_layer)
from tests import support_core_t3 as S
from tests.support_core_t import DROP, book_live, put, t_dict, t_facts

close = S.close
GC = S.GC

SIGN_GATES = ("volume_sign", "stress_sign")  # гейты знака: в книге фикстуры их ключей нет
# Гейты, чьих ключей в книге фикстуры нет: гейты знака и сторожа уровней (их включают `tests/support_core_t5.py`).
KEYLESS_GATES = SIGN_GATES + ("nim_stationary", "window_backtest", "funds_cost_to_key")
# Ключи гейтов (значения — фикстуры, не книги): цель печатаемой маржи, допуск знака объёмных эффектов,
# шаг убытка и допуск знака стресса.
GATE_KEYS: dict[str, Any] = {
    "checks.nim_lt": {"target": 0.1076, "tolerance": 0.001, "from_year": 2030},
    "checks.volume_sign": {"tol": 0.0},
    "checks.stress_sign": {"loss_step": 60.0, "tol": 0.5},
}
STRESS = "checks__stress_sign"
# Построенные случаи гейта знака стресса. Без выплаты избытка сценарий капитала меняет только рост кредитных
# книг — прибыль с требованием не растёт нигде, кроме клетки кризиса мира рыночных ставок (там урезанный кредит
# убыточен); «тихий» случай — тот же с допуском шире этого остатка. Убыток «в плюс»: расходы целиком идут за
# портфелем, а комиссии и страхование — нет: рост кредита разрушает стоимость, и больший убыток кризиса, урезая
# рост, её повышает.
QUIET = {"dividends__excess__epsilon": 0.0}
QUIET_TOL = 3.0                              # млрд ₽: шире остаточного роста прибыли в клетке кризиса мира M
LOSS_UP = {"opex__volume_link": 1.0, "fees__volume_link": 0.0, "other__insurance_volume_link": 0.0}

# ------------------------------------------------------------------ связка

P_OPEX, P_FEES, P_YEAR = "opex.volume_link", "fees.volume_link", "opex.real_growth.2027"
WHOLE = "opex.real_growth"
BUNDLE: dict[str, Any] = {
    "name": "Гибкость расходов и услуг к портфелю", "kind": "bundle", "paths": [P_OPEX, P_FEES, P_YEAR],
    "low": {P_OPEX: 0.2, P_FEES: 0.3, P_YEAR: 0.055}, "high": {P_OPEX: 0.6, P_FEES: 0.7, P_YEAR: 0.02},
    "dist": "triangular"}
SHIFT_SAME: dict[str, Any] = {"name": "Расходы 2027 года", "kind": "shift", "paths": [P_YEAR], "low": -0.01,
                              "high": 0.02, "dist": "triangular"}


def fixture_axes() -> list[dict]:
    return copy.deepcopy(t_dict()["valuation"]["uncertainty"]["axes"])


def whole_shift() -> dict:
    """Ось вида `shift` фикстуры на всей траектории реального роста расходов."""
    return next(a for a in fixture_axes() if a["paths"] == [WHOLE])


def bundle_book(*extra: dict, off_band: bool = False) -> Book:
    """Полная книга фикстуры с осью-связкой (в полосе или вне неё) и добавочными осями полосы."""
    axes = fixture_axes() + list(extra)
    if off_band:
        return S.book_of(**{"valuation__uncertainty__axes": axes, "valuation__uncertainty__off_band_axes": [BUNDLE]})
    return S.book_of(**{"valuation__uncertainty__axes": axes + [BUNDLE]})


def refused(build: Callable[[], Any], *fragments: str) -> str:
    """`build` обязан отказать `BookError`, а текст отказа — нести все `fragments`."""
    try:
        build()
    except BookError as exc:
        text = str(exc)
        assert all(f in text for f in fragments), text
        return text
    raise AssertionError(f"отказа BookError нет: ждали {fragments}")


def check_bundle_values() -> None:
    """Значение пути связки = книга + |s| × (конец − книга); конец — `high` при s ≥ 0, `low` при s < 0."""
    book = S.book_of()
    for s in (-1.0, -0.4, 0.0, 0.25, 1.0):
        got = U.axis_overrides(book, BUNDLE, s)
        assert set(got) == set(BUNDLE["paths"])
        for path in BUNDLE["paths"]:
            base = float(book.get(path))
            end = BUNDLE["high" if s >= 0 else "low"][path]
            assert got[path] == base + abs(s) * (end - base), (s, path)
            if s == 0.0:
                assert got[path] == base
            if abs(s) == 1.0:
                assert close(got[path], end, abs_=1e-15)


def check_bundle_adds_to_shift() -> None:
    """Связка — приращение к значению книги: на пути, который водит и ось вида `shift` (сам путь или
    траектория, чьим элементом он является), приращения складываются; порядок осей не важен."""
    book = S.book_of()
    base = float(book.get(P_YEAR))
    # тот же путь: сдвиг +0,5 × верх оси shift и связка на −0,4 к своему низу
    got = U.draw_overrides(book, [SHIFT_SAME, BUNDLE], (0.5, -0.4))
    want = base + 0.5 * SHIFT_SAME["high"] + 0.4 * (BUNDLE["low"][P_YEAR] - base)
    assert close(got[P_YEAR], want, abs_=1e-15) and abs(got[P_YEAR] - base) > 1e-3, (got[P_YEAR], want)
    assert close(got[P_OPEX], float(book.get(P_OPEX)) + 0.4 * (BUNDLE["low"][P_OPEX] - float(book.get(P_OPEX))),
                 abs_=1e-15)
    assert U.draw_overrides(book, [BUNDLE, SHIFT_SAME], (-0.4, 0.5)) == got
    assert float(U.draw_book(book, [SHIFT_SAME, BUNDLE], (0.5, -0.4)).get(P_YEAR)) == got[P_YEAR]
    # траектория целиком под осью shift: приращение связки — её элементу, прочие ключи только сдвинуты
    whole = whole_shift()
    got = U.draw_overrides(book, [whole, BUNDLE], (1.0, 1.0))
    traj, src = got[WHOLE], book.get(WHOLE)
    assert P_YEAR not in got and set(traj) == set(src)
    assert close(traj["2027"], base + whole["high"] + (BUNDLE["high"][P_YEAR] - base), abs_=1e-15)
    for key, value in src.items():
        if key not in ("2027", "LT_from"):
            assert close(traj[key], float(value) + whole["high"], abs_=1e-15), key
    assert U.draw_overrides(book, [BUNDLE, whole], (1.0, 1.0)) == got
    assert close(float(U.draw_book(book, [whole, BUNDLE], (1.0, 1.0)).get(P_YEAR)), traj["2027"], abs_=1e-15)


def check_bundle_zero_is_the_book() -> None:
    """Связка в положении ноль возвращает книгу бит в бит — одна и рядом с осью вида `shift` на том же пути."""
    book = bundle_book()
    alone = U.draw_book(book, [BUNDLE], [0.0])
    assert alone.data == book.data
    live = book_live(book)
    base, same = run_grid(book, t_facts(), live), run_grid(alone, t_facts(), live)
    assert (same.low, same.high, same.point) == (base.low, base.high, base.point)
    assert [c.v_ri for c in same.cells] == [c.v_ri for c in base.cells]
    axes = list(book.get("valuation.uncertainty.axes"))
    others = [a for a in axes if a["kind"] != U.BUNDLE]
    assert len(others) == len(axes) - 1
    s = [0.3 if a["paths"] == [WHOLE] else -0.2 for a in others]
    assert U.draw_book(book, others + [BUNDLE], s + [0.0]).data == U.draw_book(book, others, s).data


def check_bundle_refusals() -> None:
    """Отказы связки: общий путь с осью вида `value`, внутри словаря оси вида `dict`, с другой связкой; концы не
    ровно по путям; путь — не число книги (траектория целиком, `LT_from`), ключ года при квартальных ключах;
    связка строкой обратного расчёта не бывает."""
    axes = fixture_axes()

    def with_bundle(**change: Any) -> Callable[[], Book]:
        ax = {**copy.deepcopy(BUNDLE), **change}
        return lambda: S.book_of(**{"valuation__uncertainty__axes": axes + [ax]})

    def paths(*names: str) -> dict[str, Any]:
        return {"paths": list(names), "low": {p: 0.0 for p in names}, "high": {p: 0.1 for p in names}}

    refused(with_bundle(**paths(P_OPEX, "credit.kappa")), "credit.kappa", "вида value", "только с осью вида shift")
    refused(with_bundle(**paths(P_OPEX, "joint.world_prob.N")), "joint.world_prob.N", "вида dict")
    second = {**copy.deepcopy(BUNDLE), "name": "Вторая связка", **paths(P_FEES)}
    refused(lambda: S.book_of(**{"valuation__uncertainty__axes": axes + [BUNDLE, second]}), P_FEES, "вида bundle")
    refused(with_bundle(low={P_OPEX: 0.2, P_FEES: 0.3}), "ровно по путям")
    refused(with_bundle(high=0.5), "ровно по путям")
    refused(with_bundle(**paths(P_OPEX, "regimes.crisis.cor.LT_from")), "LT_from")
    refused(with_bundle(**paths(P_OPEX, WHOLE)), "не число")
    refused(with_bundle(**paths(P_OPEX, "regimes.crisis.cor.2027")), "квартальными ключами")
    refused(with_bundle(**paths(P_OPEX, P_OPEX)), "повторяется")
    reverse = {"name": "Связка", "kind": "bundle", "paths": [P_OPEX], "search": [0.0, 1.0], "range": [0.2, 0.6],
               "unit": "доля"}
    refused(lambda: S.book_of(**{"valuation__reverse_dcf__axes": [reverse]}), "kind")
    # прогон на осях мимо схемы: тот же отказ — у оси вида value общий путь со связкой
    value = {"name": "Связь расходов", "kind": "value", "paths": [P_OPEX], "low": 0.2, "high": 0.6,
             "dist": "triangular"}
    refused(lambda: U.draw_overrides(S.book_of(), [value, BUNDLE], (0.1, 0.1)), P_OPEX, "вида value")
    refused(lambda: U.axis_overrides(S.book_of(), {**BUNDLE, "kind": "bunch"}, 0.1), "kind")


def check_bundle_prints() -> None:
    """Печать связки — как у оси вида `value`, по первому пути; цена на конце — точка при всех путях на этом
    конце; связка несёт вклад в полосу; вне полосы её сдвиг положения входит в диагностику."""
    from model import payload as P
    from model.reverse import _band_axis
    book, facts = bundle_book(), t_facts()
    live = book_live(book)
    ax = next(a for a in book.get("valuation.uncertainty.axes") if a["kind"] == U.BUNDLE)
    row = U.axis_print(book, ax)
    assert (row["book"], row["low"], row["high"]) == (float(book.get(P_OPEX)), BUNDLE["low"][P_OPEX],
                                                    BUNDLE["high"][P_OPEX])
    assert row["ends"] == {"book": {p: float(book.get(p)) for p in BUNDLE["paths"]}, "low": BUNDLE["low"],
                           "high": BUNDLE["high"]}
    assert U.axis_book_value(book, ax) == row["book"] and U.axis_unit(book, ax) == "pct"
    assert "ends" not in U.axis_print(book, whole_shift())
    lam = float(book.get("joint.own_macro_confidence"))
    point, prices = U._axis_prices(book, facts, live, [ax], lam, None)
    for end, price in zip(("low", "high"), prices[0]):
        assert price == run_grid(book.with_overrides(BUNDLE[end]), facts, live).point, end
    assert point == run_grid(book, facts, live).point and prices[0][0] != prices[0][1]
    assert U.mean_shift(point, *prices[0]) == (prices[0][1] + prices[0][0] - 2 * point) / 6
    band = U.band(book, facts, live, draws=4, workers=1)
    shares = {r["name"]: r["share"] for r in band.contributions(band.lam)}
    assert BUNDLE["name"] in shares and "Веса миров" not in shares
    fast = next(r for r in P._judgements_not_computed(book, band, "проверка") if r["kind"] == U.BUNDLE)
    assert (fast["book"], fast["low"], fast["high"]) == (row["book"], row["low"], row["high"])
    assert fast["ends"] == row["ends"] and fast["share"] is not None and fast["paths"] == BUNDLE["paths"]
    assert _band_axis(book, P_OPEX) is None                      # строкой обратного расчёта связка не становится
    off = bundle_book(off_band=True)
    assert [a["kind"] for a in U.off_band_axes(off)] == [U.BUNDLE]
    diag = U.off_band_shift(off, facts, book_live(off))
    assert diag["axes"] == 1 and close(diag["rub"], U.mean_shift(point, *prices[0]), rel=1e-12)


def check_band_draw_with_bundle() -> None:
    """Прогон полосы со связкой и осью вида `shift` на её пути — сетка книги, собранной руками."""
    book, facts = S.book_of(), t_facts()
    live = book_live(book)
    whole = whole_shift()
    s = (-0.6, 0.7)
    got = U.band_chunk(book, facts, live, [whole, BUNDLE], [s])[0]
    step = 0.6 * whole["low"]
    traj = {k: (v if k == "LT_from" else float(v) + step) for k, v in book.get(WHOLE).items()}
    base = float(book.get(P_YEAR))
    traj["2027"] = base + step + 0.7 * (BUNDLE["high"][P_YEAR] - base)
    manual = book.with_overrides({WHOLE: traj, **{p: float(book.get(p)) + 0.7 * (BUNDLE["high"][p] - float(book.get(p)))
                                                  for p in (P_OPEX, P_FEES)}})
    run = run_grid(manual, facts, live)
    assert close(got["low"], run.low, rel=1e-12) and close(got["high"], run.high, rel=1e-12)
    assert abs(run.point - run_grid(book, facts, live).point) > 1.0


# ------------------------------------------------------------------ печатаемая маржа и гейт nim_lt


def gate(run: GridRun, name: str, **kw: Any) -> Finding | None:
    return next((f for f in check_gates(run, **kw) if f.name == name), None)


def bare_book(**changes: Any) -> Book:
    """Книга фикстуры без ключа цели печатаемой маржи (и с заменами по путям, `__` вместо точки)."""
    data = t_dict()
    put(data, "checks.nim_lt", DROP)
    for dotted, value in changes.items():
        put(data, dotted.replace("__", "."), value)
    return book_from_dict(data, facts=t_facts())


def nim_mean(run: GridRun, first: int) -> tuple[float, str]:
    """Среднее годовых упр. ЧПМ модальной клетки за годы `first` … последний год сетки — по рядам клетки:
    ЧПД года к среднему пяти концов кварталов процентных активов, через мост в упр. базис."""
    book, tl = run.ctx.book, run.ctx.timeline
    worlds, regimes = book.get("joint.world_prob"), run.ctx.posterior
    world = max(worlds, key=lambda w: worlds[w])
    regime = max(regimes, key=lambda r: regimes[r])
    table = book.get(f"joint.reg_prob_given_regime.{regime}")
    cell = run.cell(world, regime, max(table, key=lambda s: table[s]))
    values = []
    for year in range(first, tl.last_year + 1):
        qs = tl.quarters_of_year(year)
        nii = sum(cell.quarters["nii"][q] for q in qs)
        iea = sum(cell.quarters["iea"][q] for q in [qs[0] - 1] + qs) / 5
        values.append(run.ctx.bridge.to_mgmt_nim(nii / iea))
    return sum(values) / len(values), cell.label


def check_nim_lt() -> None:
    """Печатаемая маржа после фазы роста — среднее годовых упр. ЧПМ модальной клетки с года книги; гейт
    срабатывает, когда она дальше допуска от цели; без ключа книги нет ни узла, ни гейта."""
    bare = bare_book()
    plain = run_grid(bare, t_facts(), book_live(bare))
    assert printed_nim_lt(plain) is None and gate(plain, "nim_lt") is None
    assert S.book_of().opt("checks.nim_lt") == GATE_KEYS["checks.nim_lt"]       # в книге фикстуры ключ стоит
    first = GATE_KEYS["checks.nim_lt"]["from_year"]
    mean, label = nim_mean(plain, first)
    assert label == "/".join(modal_cell(plain.ctx.book, plain.ctx.posterior))
    got = printed_nim_lt(plain, first)
    assert close(got["value"], mean, rel=1e-12) and got["cell"] == label and "target" not in got
    assert got["years"] == list(range(first, plain.ctx.timeline.last_year + 1)) and got["to_year"] == got["years"][-1]
    later, _ = nim_mean(plain, first + 3)
    assert close(printed_nim_lt(plain, first + 3)["value"], later, rel=1e-12) and abs(later - mean) > 1e-5
    engine = sum(plain.cell(*label.split("/")).annual["nim"][-len(got["years"]):]) / len(got["years"])
    assert abs(engine - mean) > 1e-4                             # мост упр. ↔ движок на фикстуре не нулевой
    tol = 0.001
    for target, fired in ((mean, False), (mean + 0.9 * tol, False), (mean + 1.1 * tol, True), (mean - 1.1 * tol, True)):
        run = S.grid_of(**{"checks__nim_lt": {"target": target, "tolerance": tol, "from_year": first}})
        node, found = printed_nim_lt(run), gate(run, "nim_lt")
        assert close(node["value"], mean, rel=1e-12) and node["target"] == target and node["tolerance"] == tol
        assert found.fired is fired and found.mass == (1.0 if fired else 0.0), (target, found.message)
        assert found.cells == ((label,) if fired else ()) and label in found.message
    refused(lambda: S.book_of(**{"checks__nim_lt": {"target": mean, "tolerance": tol, "from_year": 2099}}),
            "checks.nim_lt.from_year")


# ------------------------------------------------------------------ гейты знака


def check_volume_sign_gate(extra: bool = True) -> None:
    """Гейт `volume_sign`: число — прежний тест знака (обе стороны при выключенном ограничении роста); условие —
    точка не снижается больше допуска и цена мира M меняется не хуже цены мира-опоры; без ключа гейта нет.
    `extra` — и проверки, которым нужны лишние сетки (мутационный набор их не гоняет)."""
    facts = t_facts()
    plain = S.grid_of()
    assert gate(plain, "volume_sign") is None and "tol" not in volume_sign_test(plain.ctx.book, facts, run=plain)
    run = S.grid_of(**{"checks__volume_sign": {"tol": 0.0}})
    book, live = run.ctx.book, run.ctx.live
    st = volume_sign_test(book, facts, run=run)
    off = {f"{GC}.enabled": False}
    free = {**off, **{f"regimes.{r}.loan_growth_adj": 0.0 for r in book.get("regimes.ids")},
            "regimes.crisis.loan_growth_override": {}}
    a, b = run_grid(book.with_overrides(off), facts, live), run_grid(book.with_overrides(free), facts, live)
    assert st["growth_constraint_off"] is True and st["tol"] == 0.0
    assert close(st["point"], a.point, rel=1e-12) and close(st["d_point"], b.point - a.point, rel=1e-9)
    d_world = {w: world_layer(b, w)["price"] - world_layer(a, w)["price"] for w in book.get("worlds.ids")}
    assert all(close(st["d_world"][w], v, rel=1e-9) for w, v in d_world.items())
    ref = str(book.get("nii.transmission.reference_world"))
    assert st["d_point"] > 1.0 and d_world["M"] < d_world[ref] - 1.0       # на фикстуре: точка растёт, мир M отстаёт
    assert st["ok"] is False
    # число гейта — центральной книги на её собственных входах (цена, дата и реестр книги), одно на книгу
    number = sign_numbers(run)["volume_sign"]
    assert sign_numbers(run)["stress_sign"] is None
    if extra:
        own = volume_sign_test(book, facts, run=run_grid(book, facts, live_from_book(book, facts)))
        assert close(number["d_point"], own["d_point"], rel=1e-12)
    found = gate(run, "volume_sign")
    assert found.fired and found.mass == 1.0 and found.detail["d_point"] == number["d_point"]
    assert f"{number['d_point']:+.2f}".replace(".", ",") in found.message
    lag = number["d_world"][ref] - number["d_world"]["M"]
    wide = S.grid_of(**{"checks__volume_sign": {"tol": lag + 0.01}})
    quiet = gate(wide, "volume_sign")
    assert not quiet.fired and quiet.mass == 0.0, quiet.message
    if extra:
        narrow = S.grid_of(**{"checks__volume_sign": {"tol": lag - 0.01}})
        assert gate(narrow, "volume_sign").fired
    # готовое число гейта принимается как есть: сеток проверка не считает
    assert not gate(run, "volume_sign", volume_sign={**number, "ok": True}).fired


def stress_run(**changes: Any) -> GridRun:
    return S.grid_of(**{STRESS: GATE_KEYS["checks.stress_sign"], **changes})


def loss_differences(run: GridRun) -> dict[tuple[str, str, str], float]:
    """Прирост стоимости клеток режима шока при разовом убытке больше на шаг книги — полной сеткой."""
    book = run.ctx.book
    step = float(book.get("checks.stress_sign.loss_step"))
    amount = float(book.get("regimes.crisis.one_off_loss.amount"))
    assert amount < 0
    full = run_grid(book.with_overrides({"regimes.crisis.one_off_loss.amount": amount - step}), run.ctx.facts,
                    run.ctx.live)
    for c in run.cells:
        if c.regime != "crisis":                 # прочих клеток убыток не касается: считать их заново незачем
            assert full.cell(*c.key).v_ri == c.v_ri, c.label
    return {c.key: full.cell(*c.key).v_ri - c.v_ri for c in run.cells if c.regime == "crisis"}


def requirement_pairs(run: GridRun) -> dict[tuple[str, str, str, str], float]:
    """Пары «мир × режим × (строже, мягче)» — по всем режимам, включая режим шока, — с разностью прибыли
    последнего года сетки, по рядам клеток: требование — ряд `req20` клетки на конец сетки."""
    book = run.ctx.book
    last = run.ctx.timeline.Q
    scenarios = list(book.get("capital.reg_scenarios.ids"))
    out = {}
    for w in book.get("worlds.ids"):
        for r in book.get("regimes.ids"):
            cells = {s: run.cell(w, r, s) for s in scenarios}
            for a in scenarios:
                for b in scenarios:
                    if cells[a].quarters["req20"][last] > cells[b].quarters["req20"][last] + 1e-9:
                        out[(w, r, a, b)] = cells[a].annual["ni_sh"][-1] - cells[b].annual["ni_sh"][-1]
    return out


def loss_after_tax(run: GridRun) -> float:
    """Прирост разового убытка на шаг книги после налога и доли неконтролирующих акционеров, млрд ₽ — по ключам
    книги: эффективная ставка года убытка и доля неконтролирующих акционеров."""
    from model.paths import Trajectory
    book = run.ctx.book
    year = int(str(book.get("regimes.crisis.one_off_loss.period"))[:4])
    tau = Trajectory(book.get("tax.statutory")).year_value(year) + float(book.get("tax.effective_gap"))
    return float(book.get("checks.stress_sign.loss_step")) * (1 - tau) * (1 - float(book.get("pnl.nci_share")))


def check_stress_sign(extra: bool = True) -> None:
    """Гейт `stress_sign` на построенных случаях: тихий; прибыль растёт с требованием только в клетке режима шока;
    прибыль растёт с требованием (выплата избытка оставляет строгому сценарию больше капитала); стоимость растёт с
    убытком (рост кредита разрушает стоимость). Часть о требовании судит все режимы, включая режим шока. Рядом с
    знаком — передача убытка в стоимость по всем клеткам режима шока и масса под двумя наборами вероятностей.
    `extra` — и проверки, которым нужны лишние сетки (мутационный набор их не гоняет)."""
    plain = S.grid_of()
    assert gate(plain, "stress_sign") is None
    refused(lambda: stress_sign_test(plain.ctx.book, t_facts(), run=plain), "checks.stress_sign")
    wide_tol = {STRESS: {**GATE_KEYS["checks.stress_sign"], "tol": QUIET_TOL}}
    for name, changes in (("quiet", {**QUIET, **wide_tol}), ("shock", QUIET), ("requirement", {}),
                          ("loss", {**LOSS_UP, **QUIET})):
        run = stress_run(**changes)
        tol = float(run.ctx.book.get("checks.stress_sign.tol"))
        st = stress_sign_test(run.ctx.book, t_facts(), run=run)
        dv, pairs = loss_differences(run), requirement_pairs(run)
        bad_loss = {k: v for k, v in dv.items() if v > tol}
        bad_pairs = {k: v for k, v in pairs.items() if v > tol}
        assert {(c["world"], c["regime"], c["scenario"]) for c in st["loss"]["cells"]} == set(bad_loss), name
        assert all(close(c["dv"], bad_loss[(c["world"], c["regime"], c["scenario"])], abs_=1e-6)
                   for c in st["loss"]["cells"])
        got_pairs = {(c["world"], c["regime"], c["stricter"], c["looser"]): c["d_profit"]
                     for c in st["requirement"]["cells"]}
        assert set(got_pairs) == set(bad_pairs), name
        assert all(close(got_pairs[k], v, rel=1e-12) for k, v in bad_pairs.items())
        prob = point_probabilities(run)
        lam, layers = run.lam, run.layers
        assert all(close(prob[k], (1 - lam) * layers["macro_neutral"].prob[k] + lam * layers["analytical"].prob[k],
                         abs_=1e-15) for k in prob)
        cells = set(bad_loss) | {k[:3] for k in bad_pairs}
        assert close(st["mass"], sum(prob[k] for k in cells), abs_=1e-12), name
        assert close(st["mass_analytical"], sum(layers["analytical"].prob[k] for k in cells), abs_=1e-12), name
        # передача убытка в стоимость — по всем клеткам режима шока, не только нарушившим
        net = loss_after_tax(run)
        moved = [-v / net for v in dv.values()]
        assert close(st["loss"]["after_tax"], net, rel=1e-12) and 0 < net < st["loss"]["step"]
        assert close(st["loss"]["transfer_min"], min(moved), abs_=1e-6) and close(st["loss"]["transfer_max"], max(moved), abs_=1e-6)
        assert close(st["max_excess"], max(list(bad_loss.values()) + list(bad_pairs.values()), default=0.0), abs_=1e-6)
        assert st["ok"] is (not cells) and st["loss"]["step"] == GATE_KEYS["checks.stress_sign"]["loss_step"]
        # гейт судит число центральной книги на её собственных входах (реестр книги): состав нарушивших — свой
        number = sign_numbers(run)["stress_sign"]
        if extra:
            own = stress_sign_test(run.ctx.book, t_facts())
            assert number["ok"] is own["ok"] and close(number["mass"], own["mass"], abs_=1e-12)
        found = gate(run, "stress_sign")
        named = ({(c["world"], c["regime"], c["scenario"]) for c in number["loss"]["cells"]}
                 | {(c["world"], c["regime"], c["stricter"]) for c in number["requirement"]["cells"]})
        assert found.fired is (not number["ok"]) and close(found.mass, number["mass"], abs_=1e-12)
        assert set(found.cells) == {"/".join(k) for k in named} and number["ok"] is st["ok"]
        assert found.detail["mass_basis"] == "point" and "снижение стоимости клетки на рубль убытка" in found.message
        assert ("под вероятностями точки" in found.message) is bool(named)
        if name == "quiet":
            assert not cells and st["mass"] == 0 and st["max_excess"] == 0.0 and found.mass == 0.0
            assert max(dv.values()) < 0 and st["loss"]["transfer_min"] > 0   # больший убыток снижает каждую клетку
        if name == "shock":                                      # нарушение — только в клетке режима шока
            assert bad_pairs and not bad_loss and {k[1] for k in bad_pairs} == {"crisis"}
            assert max(bad_pairs.values()) < QUIET_TOL
        if name == "requirement":
            assert bad_pairs and not bad_loss and {k[1] for k in bad_pairs} == {"soft", "crisis"}
        if name == "loss":
            assert bad_loss and "стоимость клетки растёт" in found.message and st["loss"]["transfer_min"] < 0
            # масса — под вероятностями точки, а не слоя «свой взгляд»: в этом случае они различны
            assert abs(st["mass"] - st["mass_analytical"]) > 1e-3 and "слоя «свой взгляд»" in found.message
            # допуск части об убытке: прирост стоимости между нулём и допуском — не нарушение
            edge = (min(bad_loss.values()) + max(bad_loss.values())) / 2.0
            part = stress_sign_test(run.ctx.book.with_overrides({"checks.stress_sign.tol": edge}), t_facts(), run=run)
            over = {k for k, v in dv.items() if v > edge}
            assert {(c["world"], c["regime"], c["scenario"]) for c in part["loss"]["cells"]} == over
            assert 0 < len(over) < len(bad_loss)
    if extra:
        wide = stress_run(**{STRESS: {"loss_step": 60.0, "tol": 1e6}})
        assert stress_sign_test(wide.ctx.book, t_facts(), run=wide)["ok"] and not gate(wide, "stress_sign").fired
    refused(lambda: S.book_of(**{STRESS: {"loss_step": 0.0, "tol": 0.5}}), "checks.stress_sign.loss_step")


# ------------------------------------------------------------------ потолок выплат


def payout_shares(run: GridRun) -> dict[tuple[str, int], float]:
    """Доля базовой выплаты года на все размещённые акции в прибыли акционеров клетки — по решениям клетки."""
    af, cal = run.ctx.prep.af, run.ctx.prep.calendar
    out = {}
    for c in run.cells:
        for year in c.dps:
            ni = c.annual["ni_sh"][c.years.index(year)]
            if ni is None or ni <= 0:
                continue
            paid = sum(d.base_div for d in c.decisions if d.year == year) * af.n_iss / af.n_out
            paid += cal.closed_dps.get(year, 0.0) * af.n_iss / 1000
            out[(c.label, year)] = paid / ni
    return out


def check_payout_cap_tolerance() -> None:
    """Гейт `payout_cap`: выплата ровно на потолке — не превышение; допуск книги — в долях прибыли года."""
    base = S.grid_of()
    shares = payout_shares(base)
    (label, _year), top = max(shares.items(), key=lambda kv: kv[1])
    assert 0 < top < 1
    cap = "dividends__policy__cap"
    # потолок на 1e-12 (относительно) ниже выплаты — внутри допуска равенства, но дальше ошибки счёта: без
    # допуска гейт сработал бы
    exact = gate(S.grid_of(**{cap: top * (1 - 1e-12)}), "payout_cap")
    assert not exact.fired and exact.mass == 0, exact.message       # ровно на потолке — не превышение
    above = gate(S.grid_of(**{cap: top * (1 - 1e-6)}), "payout_cap")
    assert above.fired and label in above.cells and above.mass > 0
    gap = 0.0004
    low = top - gap                                               # потолок ниже выплаты на `gap` прибыли
    assert gate(S.grid_of(**{cap: low}), "payout_cap").fired
    slack = gate(S.grid_of(**{cap: low, "checks__payout_cap": {"tolerance": 2 * gap}}), "payout_cap")
    assert not slack.fired, slack.message
    tight = gate(S.grid_of(**{cap: low, "checks__payout_cap": {"tolerance": gap / 2}}), "payout_cap")
    assert tight.fired and "больше чем на" in tight.message
    data = t_dict()
    data["checks"]["payout_cap"] = {"tolerance": 0.001}
    data["dividends"]["policy"].pop("history_test")
    from model.book_schema import validate
    refused(lambda: validate(data), "checks.payout_cap")


# ------------------------------------------------------------------ закрытый квартал без своей строки истории


def facts_changed(file: str, change: Callable[[dict], None]):
    """Факты фикстуры с правкой одного файла на месте его копии."""
    facts = t_facts()
    data = copy.deepcopy(facts.files[file])
    change(data)
    return dataclasses.replace(facts, files={**facts.files, file: data})


def check_covered_quarter() -> None:
    """Решение за полугодие закрывает два квартала одной строкой истории (период — второй квартал): первый
    квартал своей строки не имеет и даёт в годовой сумме DPS ноль; строка без DPS — по-прежнему отказ."""
    from model.book_schema import FactsError
    book = S.book_of()

    def covered(data: dict) -> None:
        data["history"] = [r for r in data["history"] if r["period"] != "2026Q1"]
        row = next(r for r in data["history"] if r["period"] == "2026Q2")
        row["decided_date"] = "2026-06-25"                       # решение не позже даты фактов: квартал закрыт

    facts = facts_changed("dividends", covered)
    run = run_grid(book, facts, book_live(book))
    cal = run.ctx.prep.calendar
    tl = run.ctx.timeline
    assert tl.period(cal.p_last) == "2026Q2" and cal.closed_dps[2026] == 4.7
    cell = run.cell("N", "norm", "schedule")
    assert set(cell.dps_q) & {"2026Q1", "2026Q2"} == set()
    assert close(cell.dps[2026], 4.7 + cell.dps_q["2026Q3"] + cell.dps_q["2026Q4"], rel=1e-12)

    def no_dps(data: dict) -> None:
        covered(data)
        next(r for r in data["history"] if r["period"] == "2026Q2")["dps"] = None

    broken = facts_changed("dividends", no_dps)
    try:
        run_grid(book, broken, book_live(book))
    except FactsError as exc:
        assert "2026Q2" in str(exc)
    else:
        raise AssertionError("строка истории закрытого квартала без DPS принята")


# ------------------------------------------------------------------ обратный расчёт


def check_reverse_axis_follows() -> None:
    """При `axis_follow: both` за проверяемым значением идут оба конца оси полосы вида `value`: ось сдвигается
    на (значение − книга) и не выходит из отрезка поиска строки; без ключа — только пересечённая граница."""
    from model.reverse import axis_follow, reverse_trial
    near = S.book_of()
    both = S.book_of(**{"valuation__reverse_dcf__axis_follow": "both"})
    assert axis_follow(near) == "near" and axis_follow(both) == "both"
    refused(lambda: S.book_of(**{"valuation__reverse_dcf__axis_follow": "all"}), "axis_follow")

    def band_axis(book: Book, path: str) -> dict:
        return next(a for a in book.get("valuation.uncertainty.axes") if a["kind"] == "value" and path in a["paths"])

    def row(book: Book, path: str) -> dict:
        return next(a for a in book.get("valuation.reverse_dcf.axes") if path in a["paths"])

    path = "valuation.erp"
    ax, band = row(near, path), band_axis(near, path)
    b, low, high = float(near.get(path)), float(band["low"]), float(band["high"])
    assert low < b < high
    for v in (high + 0.02, b + (high - b) / 2, low - 0.01):
        moved = band_axis(reverse_trial(both, ax, v, follow=True), path)
        assert close(moved["low"], low + (v - b), abs_=1e-15) and close(moved["high"], high + (v - b), abs_=1e-15)
        assert moved["low"] < v < moved["high"]                   # ось двусторонняя и за краем диапазона
        old = band_axis(reverse_trial(near, ax, v, follow=True), path)
        assert (old["low"], old["high"]) == (min(low, v), max(high, v))
    assert band_axis(reverse_trial(both, ax, b, follow=True), path) == band
    # концы не выходят из отрезка поиска строки: дисконт за управление у нижнего края поиска
    path = "valuation.governance.discount"
    ax, band = row(near, path), band_axis(near, path)
    lo, hi = (float(x) for x in ax["search"])
    v = hi - 0.01
    moved = band_axis(reverse_trial(both, ax, v, follow=True), path)
    assert moved["high"] == hi and moved["low"] == max(lo, float(band["low"]) + v - float(near.get(path)))
    # запас менеджмента: одна ось полосы на два пути строки — сдвиг один, не двойной
    path = "capital.mgmt_buffer.n20_0"
    band = band_axis(near, path)
    ax = {"name": "Запас", "kind": "value", "paths": list(band["paths"]), "search": [0.0, 0.08], "range": [0.005, 0.03],
          "unit": "п.п."}
    v = 0.04
    moved = band_axis(reverse_trial(both, ax, v, follow=True), path)
    step = v - float(near.get(path))
    assert close(moved["low"], float(band["low"]) + step, abs_=1e-15)
    assert close(moved["high"], float(band["high"]) + step, abs_=1e-15)


SMALL_BAND = {"valuation__uncertainty__draws": 4, "valuation__uncertainty__median_draws": 4,
              "valuation__reverse_dcf__subsample": 4, "valuation__headline__search_tol_rub": 2.0}


def check_edge_rule_and_printed_margin() -> None:
    """Правило края отрезка поиска (чистая функция) и поля печатаемой маржи у строки по ключу цели ЧПМ в
    быстрой сборке: маржа модальной клетки на книге есть, при корне — пусто; у прочих строк и без ключа
    `checks.nim_lt` полей нет."""
    from model import reverse as R
    assert R.on_search_edge(0.08, 0.015, 0.0, 0.08) and R.on_search_edge(0.0, 0.015, 0.0, 0.08)
    assert not R.on_search_edge(0.05, 0.015, 0.0, 0.08) and not R.on_search_edge(None, 0.015, 0.0, 0.08)
    assert not R.on_search_edge(0.0, 0.0, 0.0, 0.9)              # значение книги на краю отрезка — решение
    base = S.book_of(**SMALL_BAND, **{"checks__nim_lt": GATE_KEYS["checks.nim_lt"]})
    run = run_grid(base, t_facts(), book_live(base))
    printed = printed_nim_lt(run)["value"]
    fast = R.not_computed(base, "проверка", run=run)["rows"]
    row = next(r for r in fast if R.NIM_PATH in r["paths"])
    assert row["printed_book"] == printed and row["printed_solved"] is None
    assert all("printed_book" not in r for r in fast if R.NIM_PATH not in r["paths"])
    assert all("printed_book" not in r for r in R.not_computed(bare_book(), "проверка", run=run)["rows"])
    assert all("printed_book" not in r for r in R.not_computed(base, "проверка")["rows"])


def check_edge_root_is_unreachable() -> None:
    """Обратный расчёт на строке цели ЧПМ: корень внутри отрезка поиска — решение, и строка несёт печатаемую
    маржу модальной клетки при корне (один счёт сетки); тот же корень на краю отрезка — «недостижимо в поиске»."""
    from model import reverse as R
    key = {"checks__nim_lt": GATE_KEYS["checks.nim_lt"]}
    base = S.book_of(**SMALL_BAND, **key)
    nim = next(a for a in base.get("valuation.reverse_dcf.axes") if R.NIM_PATH in a["paths"])
    b = float(base.get(R.NIM_PATH))
    facts = t_facts()
    live0 = book_live(base)
    printed = printed_nim_lt(run_grid(base, facts, live0))["value"]
    edge = b + 0.006

    def setup(search: list[float], price: float | None = None):
        book = S.book_of(**SMALL_BAND, **key, **{"valuation__reverse_dcf__axes": [{**nim, "search": search}],
                                                  "valuation__reverse_dcf__bank_rows": []})
        live = live0 if price is None else dataclasses.replace(live0, prices={t: price for t in live0.prices})
        band = U.band(book, facts, live, draws=4, workers=1)
        return book, live, band, U.MedianAnchor(book, facts, live, band, base=band)

    def solve(search: list[float], price: float) -> dict:
        book, live, band, anchor = setup(search, price)
        return R.reverse_dcf(book, facts, live, band, anchor=anchor)["rows"][0]

    # цена — медиана при цели ЧПМ на значении `edge`: корень строки стоит ровно на нём
    book, _, _, anchor = setup([b - 0.02, edge + 0.02])
    axis = book.get("valuation.reverse_dcf.axes")[0]
    price = anchor.at(R.reverse_trial(book, axis, edge, follow=True))["central"]
    assert price > anchor.at(R.reverse_trial(book, axis, edge - 0.002, follow=True))["central"] + 4.0
    inside = solve([b - 0.02, edge + 0.02], price)
    assert inside["status"] == "solved" and close(inside["solved"], edge, abs_=1e-3), inside
    at_root = run_grid(R.reverse_trial(base, nim, inside["solved"], follow=True), facts, live0)
    assert inside["printed_book"] == printed
    assert close(inside["printed_solved"], printed_nim_lt(at_root)["value"], rel=1e-12)
    assert inside["printed_solved"] > printed + 0.003 and "reason" not in inside
    # отрезок поиска кончается на `edge`, а цена на рубль выше медианы на нём: корень — чуть за краем, невязка
    # на краю — в стопе; поиск упирается в край
    on_edge = solve([b - 0.02, edge], price + 1.0)
    assert on_edge["status"] == "unreachable" and on_edge["solved"] is None and on_edge["delta"] is None, on_edge
    assert on_edge["reason"] == R.EDGE_REASON and on_edge["in_range"] is False and on_edge["converged"] is False
    assert on_edge["printed_solved"] is None and abs(on_edge["gap"]) <= 2.0


# ------------------------------------------------------------------ подписи книги и узлы выпуска


def check_words_of_the_book() -> None:
    """Слова, которые раньше стояли в коде, — подписи книги с прежним словом по умолчанию: отношение расходов к
    доходам в заголовке, сообщении и коридоре гейта; подпись первой строки «цены правила»."""
    from model import book_results as BR
    from model import payload as P
    from model.checks import CIR_WORD, cir_word
    from tests.support_core import fixture_book, fixture_run
    book, first = S.book_of(), fixture_book()
    assert cir_word(book) == book.label("terms.cir") == "C/I" and cir_word(first) == CIR_WORD == "CIR"
    assert P.gate_title(book, "cir_range") == "C/I года вне коридора"
    assert P.gate_title(first, "cir_range") == "CIR года вне коридора"
    assert P._corridor(book, "cir_range")["text"].startswith("коридор C/I года")
    assert gate(S.grid_of(), "cir_range").message.startswith("C/I года (базис движка) вне коридора")
    assert gate(fixture_run(), "cir_range").message.startswith("CIR года (базис движка) вне коридора")
    assert BR.rule_title(book, "unconstrained") == book.label("rule_price.unconstrained")
    assert "образца" not in BR.rule_title(book, "unconstrained")
    assert BR.rule_title(book, "growth_first") == BR.RULE_TITLES["growth_first"]
    table = {"book_version": str(book.get("meta.version")), "rule_price": {"rows": [
        {"key": k, "title": BR.RULE_TITLES[k], "point": 1.0, "median": 1.0, "capital_gap_mass": 0.0,
         "current": k == "dividend_first"} for k in BR.RULE_TITLES]}}
    rows = P.rule_price_table(book, table)["rows"]
    assert rows[0]["title"] == book.label("rule_price.unconstrained") and rows[1]["title"] == BR.RULE_TITLES["dividend_first"]


def keyed_book() -> Book:
    """Книга фикстуры с ключами трёх гейтов и осью-связкой в полосе."""
    return S.book_of(**{k.replace(".", "__"): v for k, v in GATE_KEYS.items()},
                     **{"valuation__uncertainty__axes": fixture_axes() + [BUNDLE]})


def node_factor_facts():
    """Факты фикстуры, в которых коэффициент дробления стоит узлом факта, а не голым числом."""
    def node(data: dict) -> None:
        data["corporate_actions"][0]["factor"] = {"v": 10.0, "src": "решение о дроблении, фикстура"}
    return facts_changed("shares", node)


def check_release_nodes() -> None:
    """Узлы выпуска на одном быстром выпуске книги с ключами гейтов: коэффициент дробления — число; доходность
    за 12 месяцев — четыре последних объявленных квартала прибыли; словарь терминов — все термины книги; база
    суммы дивиденда; норматив, который сравнивает правило роста; числа гейтов знака согласованы с гейтами;
    печатаемая маржа рядом с ключом цели; связка в строках суждений."""
    import copy as _copy

    from model import payload as P
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
    book, facts = keyed_book(), node_factor_facts()
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    action = d["meta"]["shares"]["corporate_actions"][0]
    assert action["factor"] == 10.0 and not isinstance(action["factor"], dict)
    broken = _copy.deepcopy(d)
    broken["meta"]["shares"]["corporate_actions"][0]["factor"] = {"v": 10.0, "src": "узел факта"}
    assert any("factor" in x for x in P._format_problems(broken)) and not any("factor" in x for x in P._format_problems(d))
    div = d["dividends"]
    assert div["yield_ltm_periods"] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert close(div["yield_ltm"]["T"], (3.6 + 4.5 + 4.6 + 4.7) / 330.0, abs_=1e-6)
    assert d["meta"]["terms"] == {**dict(book.get("meta.labels.terms")), "noncore": book.label("control.lines.noncore")}
    assert len(d["meta"]["terms"]) > 3
    assert div["amount_basis"] == "issued" and d["fair_value"]["bridge"]["amount_basis"] == "outstanding"
    assert {"dividend_issued", "dividend_outstanding"} <= set(d["meta"]["basis_labels"])
    req = d["capital"]["requirement"]
    assert req["compare"] == {"n20": "n20", "n11": "n11_star"} and set(req["notes"]) == {"n11_star", "n11"}
    assert len(req["years_mix"]["n11_star"]) == len(d["capital"]["years"])
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    numbers = sign_numbers(rel.run)
    vs, ss = d["checks"]["volume_sign"], d["checks"]["stress_sign"]
    assert close(vs["d_point"], numbers["volume_sign"]["d_point"], abs_=0.006) and gates["volume_sign"]["fired"] is (not vs["ok"])
    assert len(ss["requirement"]["cells"]) == len(numbers["stress_sign"]["requirement"]["cells"]) > 0
    assert gates["stress_sign"]["fired"] is (not ss["ok"]) and close(ss["mass"], numbers["stress_sign"]["mass"], abs_=1e-6)
    printed = printed_nim_lt(rel.run)
    node = d["nii"]["transmission"]["nim_lt_printed"]
    assert close(node["value"], printed["value"], abs_=1e-6) and node["cell"] == printed["cell"]
    row = next(r for r in d["judgements"]["rows"] if r["kind"] == U.BUNDLE)
    assert row["ends"]["low"] == BUNDLE["low"] and row["book"] == float(book.get(P_OPEX))
    assert not [x for x in P._panel_problems(d) if "checks." in x or "compare" in x]
