"""Проверки пятого прохода ядра Совкомбанка (core-pass5): доля неработающих денег К8 параметром книги (Р6-1, М§4.3, §4.11).

Ключ — необязательные поля объекта `volumes.cash_assets`: доля денег без ФОР книги `share` (anchor — доля квартала якоря,
прежняя ветвь К8), ФОР якоря `reserves`, квартал доли книги `share_from` и вес вытесненной части прочих активов
`displaced_weight` (θ). Путь доли c_q = s_q + r: от доли якоря линейно по кварталам к доле книги; растущие прочие без
денег ρ′_q = ρ − c_q D_0 / L_0; в RWA — слагаемое (1 − θ)(ω′_oa − ω_c) δ_q L_q, δ_q = (c_q − c_0) D_0 / L_0, под дрейфом
плотности и валютным индексом; вырез плотности — на раскладке факта (C_0).

Одни и те же проверки зовут тесты (`tests/test_core_p5.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass5/example.json` — копия выхода
`example.py` агента методики, notes/core-pass5), выведенные из книги и фактов независимо от кода ядра. Ключа в книгах
фикстур нет (нет ключа — прежняя ветвь кода, бит в бит): проверки включают его подменой. Книга Совкомбанка дерева
(`data/assumptions/assumptions.yaml`) — только там, где проверка — пример или тождество на её числах (нет книги — пропуск).
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from model.book_schema import BookError, FactsError
from tests import support_core_p3 as P3
from tests import support_core_p4 as P4
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests" / "fixtures" / "core_pass5" / "example.json"
close = S.close
refused = P3.refused
CASH = "volumes.cash_assets"
T_CASH, T_CASH_W = P3.T_CASH, P3.T_CASH_W    # деньги якоря фикстуры `core_t` и их плотность (К8, проход 3)
T_RES = 10.0                                 # ФОР якоря фикстуры (узла фактов у `core_t` нет — числом)
T_SHARE = 0.05                               # доля денег без ФОР книги (якорь фикстуры — (150 − 10) / 4290 = 3,26 %)
T_FROM, T_QF = "2027Q1", 3                   # квартал доли книги и его номер (якорь фикстуры — 2026Q2)
T_THETA = 0.25                               # θ ≠ 0,5: слагаемое с θ вместо (1 − θ) различимо
# дрейф плотности и валютный индекс ≠ 1 (у фикстуры их нет): слагаемое вне Dn × X различимо
DRIFT = {"capital__rwa__density_drift_rate": -0.02,
         "capital__rwa__fx": {"enabled": True, "share": 0.15, "foreign_inflation": 0.02}}
B_KEY = {"share": 0.0576, "reserves": "anchor", "share_from": "2026Q4", "displaced_weight": 0.5}   # пример методики


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (книга Совкомбанка p3 @ 837590f, ключ core5-spec)."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def key(share: Any = T_SHARE, reserves: Any = T_RES, share_from: Any = T_FROM, theta: Any = T_THETA,
        driver: Any = "funds", amount: Any = T_CASH) -> dict[str, Any]:
    """Подмены фикстуры `core_t`: К8 (деньги 150 за средствами клиентов, плотность 0,1) с полями доли книги; поле со
    значением None не ставится."""
    spec: dict[str, Any] = {"amount": amount, "driver": driver}
    for name, value in (("share", share), ("reserves", reserves), ("share_from", share_from),
                        ("displaced_weight", theta)):
        if value is not None:
            spec[name] = value
    return {P3.CASH: spec, P3.CASH_W: T_CASH_W}


def t_run(**changes: Any) -> Any:
    return P3.t_run(**changes)


@functools.lru_cache(maxsize=None)
def class_checks() -> Any:
    """Инструмент проверок классов (`ops/tools/class_checks.py`) — модулем: ряды переходных слагаемых класса 5."""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("tool_class_checks_p5", ROOT / "ops" / "tools" / "class_checks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def path_ref(c0: float, r0: float, d0: float, s_star: float, q_f: int, Q: int) -> list[float]:
    """c_q, q = 0…Q, по спецификации заново: c_0 = C_0 / D_0; s_q = s_0 + (s* − s_0) q / q_f до q_f, дальше s*;
    c_q = s_q + R_0 / D_0."""
    s0, r = (c0 - r0) / d0, r0 / d0
    return [c0 / d0] + [(s_star if q >= q_f else s0 + (s_star - s0) * q / q_f) + r for q in range(1, Q + 1)]


def _t_levels(run: Any) -> tuple[float, float, float, float]:
    """L_0, D_0 (средства клиентов), F_A и ρ фикстуры — из остатков якоря и книги."""
    prep, book = run.ctx.prep, run.ctx.book
    af = prep.af
    l0 = sum(af.balances[b] for b in prep.roles.loans)
    d0 = sum(af.balances[b] for b in prep.roles.funds)
    return l0, d0, prep.oa_fixed, float(book.get("volumes.other_assets_to_loans"))


def _same(a: Any, b: Any) -> None:
    """Две сетки — бит в бит: точка, слои, стоимость клеток и все ряды кварталов."""
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high)
    for x, y in zip(a.cells, b.cells):
        assert x.v_ri == y.v_ri, x.label
        assert set(x.quarters) == set(y.quarters), x.label
        for name, series in x.quarters.items():
            assert series == y.quarters[name], (x.label, name)


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def check_neutral() -> None:
    """share: anchor (с прочими полями ключа, которые тогда не читаются) ≡ К8 без доли книги, θ = 1 ≡ поля θ нет —
    бит в бит: точка, клетки, ряды и отпечатки проходов миров; фикстура `core_t`."""
    from tests.support_core_p3 import _path_key
    plain = t_run(**P3.cash_keys())
    for keys in (key(share="anchor"), key(share="anchor", reserves=1e6, share_from="2026Q2", theta=0.0)):
        anchor = t_run(**keys)
        _same(anchor, plain)
    assert _path_key(anchor) == _path_key(plain) and anchor.ctx.prep.cash == plain.ctx.prep.cash
    one, none = t_run(**key(theta=1.0)), t_run(**key(theta=None))
    _same(one, none)
    assert _path_key(one) == _path_key(none) and one.ctx.prep.cash.shift_q is None
    assert t_run(**key()).ctx.prep.cash.shift_q is not None


def _plain_bank_data() -> dict[str, Any]:
    """Исходный словарь книги Совкомбанка дерева БЕЗ ключа Р6-1: поля доли денег сняты, оси на путях `volumes.cash_assets`
    (доля и θ) — тоже. Интеграция круга 6 поставила ключ и две оси в книгу дерева; на пути оси вида value схема требует
    числа, поэтому share: anchor на книге с осью доли — отказ схемы. Проверки «share: anchor ≡ книга без ключа» строят
    книгу без ключа сами (на книге без ключа — та же книга, бит в бит)."""
    import copy
    _, data = P4._real_book()
    data = copy.deepcopy(data)
    for k in ("share", "reserves", "share_from", "displaced_weight"):
        data["volumes"]["cash_assets"].pop(k, None)
    unc = data["valuation"]["uncertainty"]
    unc["axes"] = [a for a in unc["axes"] if not any(str(p).startswith(CASH + ".") for p in a["paths"])]
    return data


def _bank_run(data: dict[str, Any], fields: dict[str, Any] | None = None) -> Any:
    """Сетка книги-словаря `data` с полями доли денег `fields` (на копии) и фактами дерева."""
    import copy

    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    data = copy.deepcopy(data)
    data["volumes"]["cash_assets"].update(fields or {})
    facts = P4._real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts))


def check_neutral_bank() -> None:
    """Книга Совкомбанка дерева: share: anchor (ФОР anchor, квартал и θ заданы — не читаются; узел ФОР не выводится) ≡
    книга без полей доли — бит в бит (точка, клетки, ряды); якорь с ключом — факты: деньги C_0, OA_0 и RWA_0 те же."""
    data = _plain_bank_data()
    plain = _bank_run(data)
    anchor = _bank_run(data, {**B_KEY, "share": "anchor"})
    _same(anchor, plain)
    assert "volumes.cash_assets.reserves" not in anchor.ctx.book.anchors
    keyed = _bank_run(data, B_KEY)
    assert keyed.ctx.book.anchors["volumes.cash_assets.reserves"] == example()["facts"]["R_0_mandatory_reserves"]
    for c, b in zip(keyed.cells, plain.cells):
        for name in ("cash", "other_assets", "rwa", "bv"):
            assert c.quarters[name][0] == b.quarters[name][0], (c.label, name)
    assert keyed.point != plain.point


def check_overrides_reserves_anchor() -> None:
    """Ловушка with_overrides (Р6-1, М§4.3): у книги Совкомбанка с share: anchor ФОР anchor не выводится (ключ
    неактивного режима); доля книги подменой (вариант или ось на такой книге) оставляет reserves: anchor — ядро читает
    узел фактов mandatory_reserves само. Подменённая книга ≡ книга с той же долей, чей ФОР выведен из фактов, — бит в бит
    (точка, клетки, ряды): ядро читает тот же узел, что вывод anchor-ключей."""
    import copy

    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    data = _plain_bank_data()
    data["volumes"]["cash_assets"].update({**B_KEY, "share": "anchor"})
    facts = P4._real_facts()
    anchor = book_from_dict(data, facts=facts)
    assert anchor.get(f"{CASH}.reserves") == "anchor" and f"{CASH}.reserves" not in anchor.anchors
    over = anchor.with_overrides({f"{CASH}.share": B_KEY["share"]})
    assert over.get(f"{CASH}.reserves") == "anchor"
    run = run_grid(over, facts, live_from_book(over, facts))
    keyed = _bank_run(_plain_bank_data(), B_KEY)
    assert keyed.ctx.book.get(f"{CASH}.reserves") == example()["facts"]["R_0_mandatory_reserves"]
    _same(run, keyed)


# ------------------------------------------------------------------ пример методики (книга Совкомбанка)


def check_example() -> None:
    """Пример Р6-1 (книга Совкомбанка, доля 0,0576 с 2026Q4, ФОР — узел фактов, θ = 0,5): числа фактов и выводы
    примера из фактов и книги заново; путь c_q, ρ′_q и слагаемое (1 − θ)(ω′_oa − ω_c) δ_q ядра по всем q — формулы
    (1e-12); вырез плотности на раскладке факта; RWA прочих активов квартала (кредиты +2 %, средства +3 %) функцией
    `RwaWeights.rwa` с деньгами и слагаемым — число примера (1e-12); разница с RWA без ключа — линейная смесь концов θ
    (1e-9); прочие активы квартала — числа примера."""
    ex = example()
    f, bk, dv = ex["facts"], ex["book"], ex["derived"]
    run = P4._real_run(tuple((f"{CASH}.{k}", json.dumps(v)) for k, v in sorted(B_KEY.items())))
    ctx = run.ctx
    prep, facts, tl = ctx.prep, ctx.facts, ctx.timeline
    c0 = facts.need("balance", "nonworking_money.total")
    r0 = facts.need("balance", "nonworking_money.mandatory_reserves")
    d0 = sum(facts.need("balance", f"funds.{b}") for b in ("retail_current", "retail_term", "corp_term",
                                                               "corp_current"))
    l0 = sum(prep.af.balances[b] for b in prep.roles.loans)
    fa, oa0 = prep.oa_fixed, prep.af.other_assets
    assert (c0, r0) == (f["C_0"], f["R_0_mandatory_reserves"]) and close(d0, f["D_0_funds_four_books"], 1e-15)
    assert close(l0, f["L_0"], 1e-15) and (fa, oa0) == (f["F_A"], f["OA_0"])
    rho = float(ctx.book.get("volumes.other_assets_to_loans"))
    w_oa, w_c = (float(ctx.book.get(f"capital.rwa.density.{k}")) for k in ("other_assets", "cash_assets"))
    w_oaf = float(ctx.book.get("capital.rwa.density.other_assets_fixed"))
    assert close(rho, bk["rho"], 1e-15) and (w_oa, w_c, w_oaf) == (bk["omega_oa"], bk["omega_c"], bk["omega_oaf"])
    q_f = tl.index(B_KEY["share_from"])
    assert q_f == dv["q_from"] == 2
    c_path = path_ref(c0, r0, d0, B_KEY["share"], q_f, tl.Q)
    w_rest = (w_oa * (oa0 - fa) - w_c * c0) / (oa0 - fa - c0)          # вырез на раскладке ФАКТА
    theta = B_KEY["displaced_weight"]
    w_d = w_c + theta * (w_rest - w_c)
    for name, want in (("s_0", (c0 - r0) / d0), ("r", r0 / d0), ("c_0", c0 / d0), ("c_star", c_path[-1]),
                       ("rho_prime_0", rho - c0 / l0), ("rho_prime_star", rho - c_path[-1] * d0 / l0),
                       ("omega_rest_fact_carve", w_rest), ("omega_d", w_d)):
        assert close(dv[name], want, 1e-12), (name, dv[name], want)
    cash, rw = prep.cash, prep.rwa_w
    assert close(rw.other_assets_cash, w_rest, 1e-15) and rw.cash == w_c and cash.c0 == c0
    for q in range(tl.Q + 1):
        delta = (c_path[q] - c0 / d0) * d0 / l0
        assert close(cash.share_q[q], c_path[q], 1e-15), q
        assert close(cash.rho_q[q], rho - c_path[q] * d0 / l0, 1e-12), q
        assert abs(cash.shift_q[q] - (1 - theta) * (w_rest - w_c) * delta) <= 1e-15, q
        assert abs(cash.shift_q[q] - (w_rest - w_d) * delta) <= 1e-15, q
    for per, row in ex["path_first_quarters"].items():
        q = tl.index(per)
        assert close(cash.share_q[q], row["c"], 1e-12) and close(cash.rho_q[q], row["rho_prime"], 1e-12), per
        assert close(row["s"] + r0 / d0, c_path[q], 1e-12) and abs(cash.delta_q[q] - row["delta"]) <= 1e-15, per
    for per, row in ex["quarters"].items():
        q = row["q"]
        lq, dq = l0 * row["loans_x"], d0 * row["funds_x"]
        cq = c_path[q] * dq
        oa = (rho - c_path[q] * d0 / l0) * lq + cq + fa
        assert close(cq, row["cash"], 1e-12) and close(oa, row["oa"], 1e-12), per
        got = rw.rwa({b: 0.0 for b in rw.loans}, 0.0, 0.0, oa, 1.0, 1.0, cash=cq, cash_shift=cash.shift_q[q] * lq)
        assert close(got, row["rwa_other_assets"], 1e-12), (per, got, row["rwa_other_assets"])
        oa_old = (rho - c0 / l0) * lq + c0 / d0 * dq + fa                    # без ключа: c = C_0 / D_0
        rwa_old = w_rest * (oa_old - fa - c0 / d0 * dq) + w_c * c0 / d0 * dq + w_oaf * fa
        assert close(rwa_old, row["rwa_other_assets_without_key"], 1e-12), per
        d_th1 = -w_rest * (c_path[q] - c0 / d0) * d0 / l0 * lq + w_c * (c_path[q] - c0 / d0) * dq
        d_th0 = w_c * (c_path[q] - c0 / d0) * (dq - d0 * lq / l0)
        assert close(got - rwa_old, theta * d_th1 + (1 - theta) * d_th0, 1e-9), per
        assert close(row["d_rwa_theta1"], d_th1, 1e-9) and close(row["d_rwa_theta0"], d_th0, 1e-9), per


# ------------------------------------------------------------------ сетка фикстуры: путь, баланс и RWA в каждой клетке


def check_grid() -> None:
    """Фикстура `core_t` с дрейфом плотности и валютным индексом: деньги 150 за средствами клиентов, ФОР 10, доля книги 5 %
    с 2027Q1, θ = 0,25. В каждой клетке и квартале: C_q / D_q = c_q (путь заново), прочие активы ρ′_q L_q + C_q + F_A,
    RWA — плотности книги с вырезом на раскладке факта ω′_oa (OA − F_A − C) + ω_c C + ω_oaf F_A плюс (1 − θ)(ω′_oa −
    ω_c) δ_q L_q, × дрейф плотности, валютный индекс и множитель режима (1e-12); тождество баланса; якорь — ряд денег
    C_0, прочие активы и RWA бит в бит как у К8 без доли книги."""
    from model.capital import fx_index
    base, run = t_run(**P3.cash_keys(), **DRIFT), t_run(**key(), **DRIFT)
    ctx = run.ctx
    prep, book, tl = ctx.prep, ctx.book, ctx.timeline
    Q = tl.Q
    l0, d0, fa, rho = _t_levels(run)
    _, w_cut = P3._cash_weights(book, T_CASH, T_CASH_W, prep.af.other_assets, fa)
    c_path = path_ref(T_CASH, T_RES, d0, T_SHARE, T_QF, Q)
    assert tl.index(T_FROM) == T_QF
    dens = book.get("capital.rwa.density")
    assert any(x != 1.0 for x in prep.dn)
    moved = 0
    for c, b in zip(run.cells, base.cells):
        qs = c.quarters
        assert qs["cash"][0] == T_CASH
        for name in ("rwa", "other_assets", "bv"):
            assert qs[name][0] == b.quarters[name][0], (c.label, name)
        x = fx_index(book, ctx.worlds[c.world].cpi, Q)
        assert any(v != 1.0 for v in x)
        mult = prep.regimes[c.regime].rwa_mult
        for q in range(1, Q + 1):
            d_q = sum(c.books[n]["balance"][q] for n in prep.roles.funds)
            cash = qs["cash"][q]
            assert close(cash / d_q, c_path[q], 1e-15), (c.label, q, cash / d_q, c_path[q])
            loans = qs["loans"][q]
            oa = qs["other_assets"][q]
            assert close(oa, (rho - c_path[q] * d0 / l0) * loans + cash + fa, 1e-12), (c.label, q)
            base_rwa = sum(float(dens[n]) * c.books[n]["balance"][q] for n in prep.roles.loans)
            base_rwa += float(dens["securities"]) * qs["securities"][q] + float(dens["liquidity"]) * qs["liquidity"][q]
            base_rwa += w_cut * (oa - fa - cash) + T_CASH_W * cash + float(dens["other_assets_fixed"]) * fa
            base_rwa += (1 - T_THETA) * (w_cut - T_CASH_W) * (c_path[q] - c_path[0]) * d0 / l0 * loans
            want = base_rwa * prep.dn[q] * x[q] * (1.0 if mult is None else mult[q])
            assert close(qs["rwa"][q], want, 1e-12), (c.label, q, qs["rwa"][q], want)
            assert close(qs["assets"][q], qs["liabilities_equity"][q], 1e-9), (c.label, q)
        moved += abs(c.v_ri - b.v_ri) > 1e-6
    assert moved
    light = t_run(summary=True, **key(), **DRIFT)
    assert light.point == run.point


# ------------------------------------------------------------------ тождества и путь


def check_step_identity() -> None:
    """θ = 0 и доля книги с первого квартала прогноза ≡ К8 с деньгами якоря c* D_0 (вырез на раскладке книги, форма Д1)
    без доли книги: прочие активы, RWA и капитал всех кварталов прогноза и стоимость каждой клетки (1e-12); якорь у
    ключа — факт (деньги C_0)."""
    first = t_run(**key()).ctx.timeline.period(1)
    run = t_run(**key(share_from=first, theta=0.0))
    l0, d0, _, _ = _t_levels(run)
    c_star = T_SHARE + T_RES / d0
    d1 = t_run(**P3.cash_keys(amount=c_star * d0))
    for c, b in zip(run.cells, d1.cells):
        assert close(c.v_ri, b.v_ri, 1e-12), (c.label, c.v_ri, b.v_ri)
        for name in ("other_assets", "rwa", "bv", "cash", "liquidity"):
            for q in range(1, len(c.quarters[name])):
                assert close(c.quarters[name][q], b.quarters[name][q], 1e-12), (c.label, name, q)
        assert c.quarters["cash"][0] == T_CASH and b.quarters["cash"][0] == c_star * d0


def check_step_identity_bank() -> None:
    """То же тождество на книге Совкомбанка дерева (доля 0,0576 с 2026Q3, θ = 0, ФОР — узел фактов) против К8 с деньгами
    якоря c* D_0: стоимость клеток, прочие активы, RWA и капитал кварталов прогноза (1e-12) — приближение k8w возврата 06
    (вытесненная часть весит как деньги)."""
    fields = {**B_KEY, "share_from": "2026Q3", "displaced_weight": 0.0}
    run = P4._real_run(tuple((f"{CASH}.{k}", json.dumps(v)) for k, v in sorted(fields.items())))
    facts = run.ctx.facts
    d0 = sum(facts.need("balance", f"funds.{b}") for b in ("retail_current", "retail_term", "corp_term",
                                                               "corp_current"))
    c_star = B_KEY["share"] + facts.need("balance", "nonworking_money.mandatory_reserves") / d0
    d1 = _bank_run(_plain_bank_data(), {"amount": c_star * d0})        # К8 без ключа (книга дерева несёт ключ — снят)
    assert close(run.point, d1.point, 1e-12)
    for c, b in zip(run.cells, d1.cells):
        assert close(c.v_ri, b.v_ri, 1e-12), (c.label, c.v_ri, b.v_ri)
        for name in ("other_assets", "rwa", "bv"):
            for q in range(1, len(c.quarters[name])):
                assert close(c.quarters[name][q], b.quarters[name][q], 1e-12), (c.label, name, q)


def check_path() -> None:
    """Путь доли: share_from — первый квартал прогноза — шаг (c_q = c* с q = 1); c_q = c* ровно с квартала доли книги;
    до него — строго между c_0 и c* и монотонно (в обе стороны: доля книги выше и ниже доли якоря); c_0 = C_0 / D_0; δ_q
    = (c_q − c_0) D_0 / L_0; ряд класса 5 `cash_share` = c_q − c_Q нейтрален с года квартала доли книги, без доли книги
    рядов нет."""
    C = class_checks()
    tl = t_run(**key()).ctx.timeline
    for share, frm in ((T_SHARE, T_FROM), (0.02, T_FROM), (T_SHARE, tl.period(1)), (0.02, "2029Q4")):
        run = t_run(**key(share=share, share_from=frm))
        cash = run.ctx.prep.cash
        l0, d0, _, _ = _t_levels(run)
        q_f = tl.index(frm)
        c0, cs = T_CASH / d0, share + T_RES / d0
        assert close(cash.share_q[0], c0, 1e-15) and cash.delta_q[0] == 0.0
        for q in range(1, tl.Q + 1):
            c = cash.share_q[q]
            if q >= q_f:
                assert c == cs, (frm, q)
            else:
                assert min(c0, cs) < c < max(c0, cs), (frm, q)
                assert (c - cash.share_q[q - 1]) * (cs - c0) > 0, (frm, q)
            assert close(cash.delta_q[q], (c - c0) * d0 / l0, 1e-12), (frm, q)
        items = C.series_items(run.ctx, "cash_share")["cash_share"]
        assert [v for _, _, q, v in items if q >= q_f] == [0.0] * (tl.Q - q_f + 1)
        assert all(v != 0.0 for _, _, q, v in items if q < q_f)
        broken, _ = C.transitional_breaks(run.ctx, {"name": "доля денег", "series": "cash_share", "neutral": "last",
                                                    "until": tl.year(q_f)})
        assert broken == []
        if q_f > 1:
            broken, _ = C.transitional_breaks(run.ctx, {"name": "доля денег", "series": "cash_share", "neutral": 0.0,
                                                        "until": tl.year(q_f - 1) - 1})
            assert broken, frm
    assert C.series_items(t_run(**P3.cash_keys()).ctx, "cash_share") == {}
    assert C.series_items(t_run().ctx, "cash_share") == {}


def check_class_six_word_rule() -> None:
    """Класс 6 инструмента проверок: правило value со словом (квартал доли книги share_from) — равенство записи; другое
    слово — находка; ключа нет — проверка не отработала. Числовые правила — прежние."""
    from types import SimpleNamespace
    C = class_checks()
    run = t_run(**key())
    book = run.ctx.book

    def judge(*rules: dict) -> Any:
        # стенд класса 6 — книга и её сетка (`base`: решённая передача сетки — T() формул правил типа Б доли φ)
        chk = C.Check(6, "centres", "центры")
        C.class6(SimpleNamespace(cfg={"centres": list(rules)}, book=book, facts=None, base=run), chk)
        return chk
    same = judge({"key": f"{CASH}.share_from", "rule": "value", "value": T_FROM},
                 {"key": f"{CASH}.share", "rule": "value", "value": T_SHARE, "tol": 0})
    assert same.status == C.OK and [r["book"] for r in same.numbers["rows"]] == [T_FROM, T_SHARE], same.findings
    other = judge({"key": f"{CASH}.share_from", "rule": "value", "value": "2026Q4"})
    assert other.status == C.FIRED and "2026Q4" in other.findings[0], other.findings
    absent = judge({"key": f"{CASH}.no_such_key", "rule": "value", "value": T_FROM})
    assert absent.status == C.ERROR, absent.findings


def check_fingerprint() -> None:
    """Ключ, доля, квартал доли книги, ФОР и θ — входы прохода каждого мира (`path_keys`): полоса по записям не возьмёт
    чужой проход; θ = 1 и поле θ снятое — один отпечаток (выше, `check_neutral`)."""
    from tests.support_core_p3 import _moves_every_world
    run = t_run(**key())
    assert _moves_every_world(run, t_run(**P3.cash_keys()))
    for other in (key(share=0.06), key(share_from="2026Q4"), key(theta=0.5), key(reserves=12.0)):
        assert _moves_every_world(t_run(**other), run), other


def check_memo_and_light() -> None:
    """Память оценок шага и лёгкая оценка нормативов (рост, ограниченный капиталом): в квартале перехода (θ = 0,25)
    оценка при другой доле прироста с той же памятью — та же, что без памяти (деньги, прочие активы, RWA); лёгкая
    оценка — те же RWA и нормативы, что полный шаг (слагаемое вытесненной части — в обеих); слагаемое в квартале есть
    (RWA выше, чем при θ = 1)."""
    from model.cell import _Cell, initial_state
    ctx = t_run(**key()).ctx
    assert ctx.prep.growth is not None and not ctx.prep.memo_off
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(ctx.prep)
    memo: dict = {}
    first = cell.evaluate(st, 1, (), 1.0, memo=memo)[0]
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    assert first["rwa"] != fresh["rwa"], "доля прироста не сдвигает RWA"
    for name in ("cash", "other_assets", "rwa", "n20", "n11"):
        assert second[name] == fresh[name], name
    for lam in (1.0, 0.3):
        light = cell.evaluate(st, 1, (), lam, light=True)[0]
        full = cell.evaluate(st, 1, (), lam)[0]
        for name in ("rwa", "n20", "n11", "n11_star"):
            assert light[name] == full[name], (lam, name)
    ctx1 = t_run(**key(theta=1.0)).ctx
    other = _Cell(ctx1, "N", "norm", "mid").evaluate(initial_state(ctx1.prep), 1, (), 0.3)[0]
    assert other["cash"] == fresh["cash"] and fresh["rwa"] > other["rwa"]


def check_variant_trap() -> None:
    """Ловушка драйвера (вариант cash_with_loans): драйвер «кредиты» с share: anchor ≡ без ключа К8 (1e-12) при любых
    полях доли книги; драйвер «кредиты» с долей книги — уже не ≡ (доля средств легла бы на кредиты)."""
    base = t_run()
    for keys in (key(share="anchor", driver="loans"), key(share="anchor", driver="loans", theta=None)):
        run = t_run(**keys)
        for c, b in zip(run.cells, base.cells):
            assert close(c.v_ri, b.v_ri, 1e-12), (keys, c.label)
            for name in ("other_assets", "rwa", "bv"):
                for q, (x, y) in enumerate(zip(c.quarters[name], b.quarters[name])):
                    assert close(x, y, 1e-12), (keys, c.label, name, q)
    keyed = t_run(**key(driver="loans"))
    assert any(abs(c.v_ri - b.v_ri) > 1e-6 for c, b in zip(keyed.cells, base.cells))


# ------------------------------------------------------------------ отказы схемы и ядра


def check_refusals() -> None:
    """Схема: доля без ФОР или квартала; квартал не после якоря или позже конца сетки; ФОР, квартал или θ без доли; доля
    ≥ 1 и < 0; θ вне [0; 1]; при share: anchor поля не судятся. Ядро: ФОР больше денег якоря; ρ′_q < 0 (денег книги
    больше растущей части прочих активов) — с числами; reserves: anchor без узла фактов — FactsError (и при выводе
    anchor-ключей книги, и в ядре на подменённой книге); подмена без ФОР или с кварталом вне сетки — отказ ядра."""
    def book(**spec: Any) -> Any:
        return S.book_of(**{P3.CASH: {"amount": T_CASH, "driver": "funds", **spec}, P3.CASH_W: T_CASH_W})

    book(share=T_SHARE, reserves=T_RES, share_from=T_FROM, displaced_weight=0.5)          # форма верна
    book(share="anchor", reserves="anchor", share_from="2026Q2", displaced_weight=0.0)  # не судятся
    refused(lambda: book(share=T_SHARE, share_from=T_FROM), "volumes.cash_assets.reserves: нет ключа")
    refused(lambda: book(share=T_SHARE, reserves=T_RES), "volumes.cash_assets.share_from: нет ключа")
    refused(lambda: book(share=T_SHARE, reserves=T_RES, share_from="2026Q2"), "не позже квартала якоря")
    refused(lambda: book(share=T_SHARE, reserves=T_RES, share_from="2025Q4"), "не позже квартала якоря")
    refused(lambda: book(share=T_SHARE, reserves=T_RES, share_from="2037Q1"), "позже meta.last_period")
    for name, value in (("reserves", T_RES), ("share_from", T_FROM), ("displaced_weight", 0.5)):
        refused(lambda name=name, value=value: book(**{name: value}), f"volumes.cash_assets.{name}: читается только")
    for value in (1.0, -0.01, "доля"):
        refused(lambda value=value: book(share=value, reserves=T_RES, share_from=T_FROM), "или anchor")
    for value in (1.5, -0.1):
        refused(lambda value=value: book(share=T_SHARE, reserves=T_RES, share_from=T_FROM, displaced_weight=value),
                "доля от 0 до 1")
    refused(lambda: book(share=T_SHARE, reserves=T_RES, share_from="2027-01"), "квартал ГГГГQn")
    refused(lambda: t_run(**key(reserves=T_CASH + 1)), "ФОР больше денег якоря")
    text = None
    try:
        t_run(**key(share=0.3))
    except BookError as exc:
        text = str(exc)
    assert text is not None and "меньше нуля — денег книги больше растущей части" in text and "0.3" in text, text
    refused(lambda: book(share=T_SHARE, reserves="anchor", share_from=T_FROM), "mandatory_reserves", FactsError)
    refused(lambda: t_run(**key(reserves="anchor")), "mandatory_reserves", FactsError)
    # ядро — своим отказом и мимо схемы (книга без проверки: подмена в обход `with_overrides`)
    for spec in (key(reserves=None), key(share_from=None)):
        refused(lambda spec=spec: _unchecked(spec), "без ФОР якоря")
    for frm in ("2026Q2", "2037Q1"):
        refused(lambda frm=frm: _unchecked(key(share_from=frm)), "квартал доли книги — после якоря")


def _unchecked(changes: dict[str, Any]) -> Any:
    """Сетка фикстуры с подменами мимо проверки схемы (`dataclasses.replace` данных книги): так видны отказы самого
    ядра, которые схема закрывает раньше."""
    import copy
    import dataclasses

    from model.grid import run_grid
    from model.paths import set_path
    from tests.support_core_t import book_live
    book = S.book_of()
    data = copy.deepcopy(dict(book.data))
    for k, v in changes.items():
        set_path(data, k.replace("__", "."), v)
    probe = dataclasses.replace(book, data=data)
    return run_grid(probe, plain_facts(), book_live(probe))


def plain_facts() -> Any:
    from tests.support_core_t import t_facts
    return t_facts()


# ------------------------------------------------------------------ выпуск


def check_release_with_pass5_keys() -> None:
    """Выпуск фикстуры с ключом прохода 5 (К8 с долей книги, θ = 0,25): контракт выполнен; ряд клетки `cash` — тот же
    узел, нового ряда в выпуске нет."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    data = t_dict()
    for k, v in {"valuation__terminal__fixed_growth_share": 0.0, "checks__mix_ratio_tolerance": 0.002,
                 **key()}.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    run = run_grid(book, facts)
    assert run.ctx.prep.cash.shift_q is not None
    expl = explained(check_gates(run, today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    assert contract(d) == [], contract(d)[:5]
    for c in rel.run.cells:
        assert "cash" in c.quarters
