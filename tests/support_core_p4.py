"""Проверки четвёртого прохода ядра Совкомбанка (core-pass4): сложение связок на общем пути (Р5-4, М§10), драйвер RWA
гарантий — компонента смеси базы комиссий (Р5-5, М§4.11), корень строк комиссий и страхования множителем (Р5-6, М§4.7).

Одни и те же проверки зовут тесты (`tests/test_core_p4.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass4/example.json` — копия выхода
`example.py` агента методики, notes/core-pass4), выведенные независимо от кода ядра. Ключей прохода в книгах фикстур нет
(нет ключа — прежняя ветвь кода, бит в бит): проверки включают их подменой. Книга Совкомбанка дерева
(`data/assumptions/assumptions.yaml`) — только там, где проверка — тождество на её числах (нет книги — пропуск).
"""

from __future__ import annotations

import copy
import functools
import itertools
import json
import math
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from model.book_schema import BookError
from tests import support_core_p3 as P3
from tests import support_core_t3 as S
from tests import support_core_t4 as S4

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests" / "fixtures" / "core_pass4" / "example.json"
close = S.close
AX = "valuation.uncertainty.axes"
GUAR = "capital.rwa.guarantees"
FEES_B, INS_B = P3.FEES_B, P3.INS_B
T_RETAIL = P3.T_RETAIL
T_CORP = {"corp_loans": 1.0, "sme_loans": 1.0}
refused = S4.refused


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода: разделы bundle_sum (Р5-4), k5 (Р5-5), mult (Р5-6)."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def bits(value: Any) -> str:
    """Запись значения с точными битами чисел (repr) — сравнение «бит в бит» словарей подмен."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _u():
    from model import uncertainty as U
    return U


@functools.lru_cache(maxsize=None)
def _real_facts() -> Any:
    from tests.support_core import real_facts_or_skip
    return real_facts_or_skip()


@functools.lru_cache(maxsize=None)
def _real_book() -> tuple[Any, dict]:
    """Книга Совкомбанка дерева и её исходный словарь (до вывода anchor-ключей)."""
    from tests.support_core import real_book_or_skip
    book, _ = real_book_or_skip()
    return book, copy.deepcopy(dict(book.source))


@functools.lru_cache(maxsize=None)
def _real_run(changes: tuple = (), summary: bool = False) -> Any:
    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    from model.paths import set_path
    _, data = _real_book()
    data = copy.deepcopy(data)
    for dotted, value in changes:
        set_path(data, dotted, json.loads(value))
    facts = _real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts), summary=summary)


# ================================================================== Р5-5: драйвер RWA гарантий — компонента смеси (М§4.11)

def _k5_run(mix: dict, **guar: Any) -> Any:
    return P3.mix_run(fees__volume_base=mix, capital__rwa__guarantees=P3._guar(**guar))


TWO = P3.mix(corp=(0.6, T_CORP), retail=(0.4, T_RETAIL))


def _same_runs(a: Any, b: Any, rows: tuple[str, ...] = ("rwa", "rwa_guar", "fees", "bv")) -> None:
    """Две сетки — бит в бит: стоимость клеток, точка и ряды."""
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high)
    for x, y in zip(a.cells, b.cells):
        assert x.v_ri == y.v_ri, x.label
        for name in rows:
            assert x.quarters[name] == y.quarters[name], (x.label, name)


def _g_series(run: Any) -> dict:
    """G_q клеток по рядам RWA гарантий: rwa_guar / (дрейф плотностей × валюта × множитель режима)."""
    from model.capital import fx_index
    ctx = run.ctx
    prep, tl = ctx.prep, ctx.timeline
    out = {}
    for c in run.cells:
        mult = prep.regimes[c.regime].rwa_mult
        x = fx_index(ctx.book, ctx.worlds[c.world].cpi, tl.Q)
        out[c.key] = {q: c.quarters["rwa_guar"][q] / (prep.dn[q] * x[q] * (1.0 if mult is None else mult[q]))
                      for q in range(1, tl.Q + 1)}
    return out


def check_k5_neutral() -> None:
    """G1: при драйвере fees_base поле component — ключ неактивного режима, не читается (любое имя): сетка бит в бит та
    же, что без поля. G2: смесь из одной компоненты — fees_component ≡ fees_base бит в бит. G3: верх оси базы комиссий
    (доля КБ 1, доля розницы 0) — fees_component ≡ fees_base бит в бит."""
    base = _k5_run(TWO)
    _same_runs(base, _k5_run(TWO, component="corp"))
    _same_runs(base, _k5_run(TWO, component="нет такой"))
    one = P3.mix(corp=(1.0, T_CORP))
    _same_runs(_k5_run(one), _k5_run(one, driver="fees_component", component="corp"))
    top = P3.mix(corp=(1.0, T_CORP), retail=(0.0, T_RETAIL))
    _same_runs(_k5_run(top), _k5_run(top, driver="fees_component", component="corp"))
    assert _k5_run(TWO, driver="fees_component", component="corp").point != base.point


def check_k5_mix_invariance() -> None:
    """G4 и G6: при драйвере компоненты G_q = G_0 D^c_q / D^c_0 (D^c — остатки книг компоненты на конец квартала) во
    всех клетках и кварталах — при любых долях смеси (1e-12); RWA якоря — тот же, что при fees_base."""
    for mix in (TWO, P3.mix(corp=(0.9, T_CORP), retail=(0.1, T_RETAIL))):
        run = _k5_run(mix, driver="fees_component", component="corp")
        prep = run.ctx.prep
        assert prep.guar.base.kind == "books" and prep.guar.base.weights == T_CORP
        d0 = sum(prep.af.balances[b] for b in T_CORP)
        assert close(prep.guar.d0, d0, 1e-15)
        g = _g_series(run)
        for c in run.cells:
            for q, value in g[c.key].items():
                dq = sum(c.books[b]["balance"][q] for b in T_CORP)
                assert close(value, prep.guar.g0 * dq / d0, 1e-12), (c.label, q, value, prep.guar.g0 * dq / d0)
        base = _k5_run(mix)
        assert [c.quarters["rwa"][0] for c in run.cells] == [c.quarters["rwa"][0] for c in base.cells]


def check_k5_carve_identity() -> None:
    """G5: база компоненты = книга выреза ({corp_loans: 1}, вырез из corp_loans): RWA гарантий возвращаются в плотность
    кредита юрлиц — RWA всех клеток и кварталов ≡ К5 выключен (1e-12 отн.), точка — 1e-9."""
    mix = P3.mix(corpx=(0.6, {"corp_loans": 1.0}), rest=(0.4, {**T_RETAIL, "sme_loans": 1.0}))
    on = _k5_run(mix, driver="fees_component", component="corpx")
    off = _k5_run(mix, enabled=False)
    assert off.ctx.prep.guar is None and on.ctx.prep.guar is not None
    assert close(on.point, off.point, 1e-9), (on.point, off.point)
    for x, y in zip(on.cells, off.cells):
        for q in range(on.ctx.timeline.Q + 1):
            assert close(x.quarters["rwa"][q], y.quarters["rwa"][q], 1e-12), (x.label, q)


def check_k5_refusals() -> None:
    """Отказы: драйвер компоненты без поля component, имя не из смеси, база комиссий словом или весами (не смесь) —
    схема; функция ядра `guarantee_component` — те же отказы мимо схемы."""
    from model.cell import guarantee_component
    refused(lambda: S.book_of(fees__volume_base=TWO, capital__rwa__guarantees=P3._guar(driver="fees_component")),
            "component", "нет ключа")
    refused(lambda: S.book_of(fees__volume_base=TWO,
                              capital__rwa__guarantees=P3._guar(driver="fees_component", component="nope")),
            "'nope'", "нет среди компонент")
    for word in ("loans", T_CORP):
        refused(lambda word=word: S.book_of(fees__volume_base=word, capital__rwa__guarantees=P3._guar(
            driver="fees_component", component="corp")), "не смесь")
    book = S.book_of(fees__volume_base=TWO)
    assert guarantee_component(book, {"component": "corp"}) == ("corp", T_CORP)
    refused(lambda: guarantee_component(book, {}), "нет ключа")
    refused(lambda: guarantee_component(book, {"component": "nope"}), "нет среди компонент")
    refused(lambda: guarantee_component(S.book_of(fees__volume_base="loans"), {"component": "corp"}), "не смесь")


def check_k5_example() -> None:
    """Пример k5 (книга Совкомбанка c709f22, H/soft/mid, кварталы 1–6): G_q = G_0 E^КБ_q / E^КБ_0, множитель дрейфа ×
    валюты × режима — отношение ряда клетки к G_q; на книге дерева (если она есть) — то же тождество функцией ядра во
    всех клетках, G_0 — по номиналам книги (и числом примера, если номиналы те же)."""
    ex = example()["k5"]
    for row in ex["rows"]:
        assert close(row["G_q_component"], ex["G0"] * row["E_corp_q"] / ex["E_corp_0"], 1e-12)
        assert close(row["multiplier_drift_fx_regime"], row["rwa_guar_component"] / row["G_q_component"], 1e-12)
    from tests.support_core import REAL_BOOK, real_facts_ready
    if not (REAL_BOOK.exists() and real_facts_ready()):
        return
    book, data = _real_book()
    if (data.get("capital", {}).get("rwa", {}).get("guarantees") or {}).get("enabled") is not True:
        return
    run = _real_run((("capital.rwa.guarantees.driver", '"fees_component"'),
                     ("capital.rwa.guarantees.component", '"corporate"')))
    prep = run.ctx.prep
    weights = prep.guar.base.weights
    d0 = sum(w * prep.af.balances[b] for b, w in weights.items())
    g = _g_series(run)
    for c in run.cells:
        for q, value in g[c.key].items():
            dq = sum(w * c.books[b]["balance"][q] for b, w in weights.items())
            assert close(value, prep.guar.g0 * dq / d0, 1e-12), (c.label, q)
    spec = run.ctx.book.get(GUAR)
    n, ccf = spec["notional"], spec["ccf"]
    g0 = float(spec["weight"]) * (float(n["nonfinancial"]) * float(ccf["nonfinancial"])
                                  + float(n["financial"]) * float(ccf["financial"]))
    assert close(prep.guar.g0, g0, 1e-15)


def check_k5_marginal() -> None:
    """Лист предельной экономики (единица кредита юрлиц) на книге дерева: при драйвере компоненты {corp_loans: 1} RWA
    гарантий на рубль кредита юрлиц — G / E_юрлиц конца года (разность rwa_per_loan с К5 и без его слагаемого, шаг
    записи листа 1e-6). Нет книги или К5 выключен — пропуск."""
    import dataclasses
    from tests.support_core import REAL_BOOK, real_facts_ready
    if not (REAL_BOOK.exists() and real_facts_ready()):
        return
    book, data = _real_book()
    if (data.get("capital", {}).get("rwa", {}).get("guarantees") or {}).get("enabled") is not True:
        return
    mix = (data.get("fees") or {}).get("volume_base")
    if not (isinstance(mix, dict) and "corporate" in (mix.get("mix") or {})):
        return
    from model.book import anchor_facts
    from tests.support_book import load_module
    mod = load_module(ROOT / "data" / "assumptions" / "evidence" / "path" / "marginal_loan.py", "sheet_marginal_p4")
    run = _real_run((("capital.rwa.guarantees.driver", '"fees_component"'),
                     ("capital.rwa.guarantees.component", '"corporate"')))
    ctx = run.ctx
    if ctx.prep.guar.base.weights != {"corp_loans": 1.0}:
        return
    cell = run.cell("N", "norm", "mid")
    af = anchor_facts(_real_facts(), ctx.book.get("nii.books"))
    mult = mod.cor_multipliers(ctx.book, af, tuple(ctx.prep.roles.loans))
    year = cell.years[2]
    with_g = mod.marginal(run, ctx.book, cell, year, ("corp_loans",), mult)
    bare = SimpleNamespace(ctx=dataclasses.replace(ctx, prep=dataclasses.replace(ctx.prep, guar=None)))
    without = mod.marginal(bare, ctx.book, cell, year, ("corp_loans",), mult)
    last = [k for k in ctx.timeline.quarters_of_year(year) if 1 <= k <= ctx.timeline.Q][-1]
    want = cell.quarters["rwa_guar"][last] / cell.books["corp_loans"]["balance"][last]
    assert abs(with_g["rwa_per_loan"] - without["rwa_per_loan"] - want) <= 2e-6, (with_g["rwa_per_loan"],
                                                                                  without["rwa_per_loan"], want)


# ================================================================== Р5-6: корень строки множителем (М§4.7)

ROOTS = {"fees__growth_vs_wages": {"2026": 0.03, "2027": -0.02, "LT": 0.01},
         "other__insurance_growth_vs_wages": {"2026": -0.04, "2027": 0.05, "LT": 0.015}}
OWN = {"fees__volume_base": TWO, "other__insurance_volume_base": P3.mix(loans=(0.5, "loans"), retail=(0.5, T_RETAIL))}
MULT = {"volumes__line_root_form": "multiplicative"}


def _lines(run: Any) -> list:
    return [(c.v_ri, c.quarters["fees"], c.quarters["ins"], c.quarters["opex"]) for c in run.cells]


def check_mult_neutral() -> None:
    """I1: ключ additive ≡ нет ключа бит в бит. I2: корни (и переопределения) нулевые — множитель ≡ сумма бит в бит: при
    связях фикстуры (link_base), со своими базами строк (К2б) и без связи."""
    _same_runs(P3.mix_run(), P3.mix_run(volumes__line_root_form="additive"), ("fees", "ins", "opex", "bv"))
    zero = {"fees__growth_vs_wages": 0.0, "other__insurance_growth_vs_wages": 0.0}
    for extra in ({}, OWN, {"fees__volume_link": 0.0, "other__insurance_volume_link": 0.0}):
        a = P3.mix_run(**zero, **extra)
        b = P3.mix_run(**zero, **extra, **MULT)
        assert _lines(a) == _lines(b)
        assert P3.mix_run(**ROOTS, **extra, **MULT).point != P3.mix_run(**ROOTS, **extra).point


def check_mult_override_year() -> None:
    """I6: в году переопределения комиссий корня нет ни в какой форме: F_q = F_(q−4) × (1 + переопределение) бит в бит."""
    y = 2028
    for form in ({}, MULT):
        run = P3.mix_run(**ROOTS, fees__growth_override={str(y): 0.07}, **form)
        tl = run.ctx.timeline
        for c in run.cells:
            for q in tl.quarters_of_year(y):
                f = c.quarters["fees"]
                assert f[q] == f[q - 4] * (1 + 0.07), (c.label, q)


def _wage(run: Any, c: Any) -> Any:
    return run.ctx.worlds[c.world].wage


def check_mult_quarter() -> None:
    """I4: при ключе F_q = F_(q−4) (1 + w + link (A_q / A_(q−4) − 1 − w)) (1 + r_q), A — средняя база строки по своему
    ключу (К2б), так же страхование (1e-12; фикстура, связь 0,5); I5: связь 0 — F_q = F_(q−4) (1 + w)(1 + r_q). Пример
    mult (книга c709f22, 2027К3 H/soft/mid): число примера — той же формулой из его входов (1e-12)."""
    for extra in (OWN, {"fees__volume_link": 0.0, "other__insurance_volume_link": 0.0}):
        run = P3.mix_run(**ROOTS, **extra, **MULT)
        p = run.ctx.prep
        for c in run.cells:
            w = _wage(run, c)
            for line, base, link, r in (("fees", "vol_fees", p.link_fees, p.fees_gvw),
                                        ("ins", "vol_ins", p.link_ins, p.ins_gvw)):
                f = c.quarters[line]
                for q in range(5, run.ctx.timeline.Q + 1):
                    v = (c.quarters[base][q] / c.quarters[base][q - 4] - 1) if link else 0.0
                    want = f[q - 4] * (1 + w[q] + link * (v - w[q])) * (1 + r[q])
                    assert close(f[q], want, 1e-12), (c.label, line, q, f[q], want)
    # связь через volumes.link_base (фикстура как есть: кредиты, связи 0,5 / 0,5, расходы 0,4; своих баз строк нет) —
    # третья ветвь обеих строк: превышение роста объёма над зарплатами v_ex — из строки расходов той же клетки
    # (C_q = C_(q−4)(1 + w + λ_C v_ex)(1 + реальный рост)), комиссии и страхование — формулой ключа с тем же v_ex (1e-12)
    run = P3.mix_run(**ROOTS, **MULT)
    p = run.ctx.prep
    assert p.fees_line is None and p.ins_line is None and p.opex_w is None and p.line_shares is None
    assert p.link_base and p.link_fees and p.link_ins and p.link_opex and not p.fees_override
    for c in run.cells:
        w, o = _wage(run, c), c.quarters["opex"]
        for q in range(5, run.ctx.timeline.Q + 1):
            v_ex = (o[q] / o[q - 4] / (1 + p.opex_real[q]) - 1 - w[q]) / p.link_opex
            for line, link, r in (("fees", p.link_fees, p.fees_gvw), ("ins", p.link_ins, p.ins_gvw)):
                f = c.quarters[line]
                want = f[q - 4] * (1 + w[q] + link * v_ex) * (1 + r[q])
                assert close(f[q], want, 1e-12), (c.label, line, q, f[q], want)
    for row in example()["mult"]["rows"]:
        for line, r in (("fees", row["r_fees"]), ("ins", row["r_ins"])):
            node = row[line]
            if "F_q_mult_formula" not in node:
                continue
            v = node["A_q"] / node["A_q_minus_4"] - 1
            want = node["F_q_minus_4"] * (1 + row["wage"] + 1.0 * (v - row["wage"])) * (1 + r)
            assert close(want, node["F_q_mult_core"], 1e-12) and close(want, node["F_q_mult_formula"], 1e-12)


def check_mult_class2() -> None:
    """I3 (класс 2): при связи 1 со своей базой строки уровень строки к её базе F_q / A_q — один во всех 36 клетках (1e-12
    отн.) у комиссий и у страхования: F_q / A_q = F_(q−4) / A_(q−4) × (1 + r_q). При сумме (прежняя форма) — разный по
    мирам (больше 1e-6)."""
    links = {"fees__volume_link": 1.0, "other__insurance_volume_link": 1.0}

    def spread(run: Any, line: str, base: str) -> float:
        worst = 0.0
        for q in range(1, run.ctx.timeline.Q + 1):
            ratios = [c.quarters[line][q] / c.quarters[base][q] for c in run.cells]
            worst = max(worst, max(ratios) / min(ratios) - 1)
        return worst

    mult = P3.mix_run(**ROOTS, **OWN, **links, **MULT)
    add = P3.mix_run(**ROOTS, **OWN, **links)
    for line, base in (("fees", "vol_fees"), ("ins", "vol_ins")):
        assert spread(mult, line, base) <= 1e-12, (line, spread(mult, line, base))
        assert spread(add, line, base) > 1e-6, (line, spread(add, line, base))


def check_mult_fingerprint() -> None:
    """Форма корня — вход прохода клеток: флаг в подготовке, отпечаток КАЖДОГО мира другой (полоса по записям
    `band(like=…)` не берёт проходы книги без ключа)."""
    a, b = P3.mix_run(**ROOTS), P3.mix_run(**ROOTS, **MULT)
    assert b.ctx.prep.root_mult is True and a.ctx.prep.root_mult is False
    assert P3._moves_every_world(a, b)


# ================================================================== Р5-4: сложение связок (М§10)

P = "opex.real_growth.2028"                 # путь примера: три связки и сдвиг траектории
WHOLE = "opex.real_growth"
LINKS = {"М13": "opex.volume_link", "страхование": "other.insurance_volume_link", "комиссии": "fees.volume_link"}


def _ex_axes() -> tuple[list[dict], list[float], float]:
    """Оси примера bundle_sum на фикстуре `core_t`: ось вида shift фикстуры на всей траектории реального роста расходов
    с верхом примера и три связки с концами примера на пути P (первые пути — свои связи строк, чтобы первые пути осей
    были различны). → (оси полосы фикстуры с ними, положения s, центр пути)."""
    ex = example()["bundle_sum"]
    axes = S4.fixture_axes()
    s = [0.0] * len(axes)
    terms = ex["terms"]
    shift = next(t for t in terms if t["kind"] == "shift")
    j = next(i for i, a in enumerate(axes) if a["paths"] == [WHOLE])
    axes[j] = {**axes[j], ("high" if shift["s"] >= 0 else "low"): shift["end"]}
    s[j] = shift["s"]
    c = ex["centre"]
    for (word, link), term in zip(LINKS.items(), [t for t in terms if t["kind"] == "bundle"]):
        side = "high" if term["s"] >= 0 else "low"
        other = "low" if side == "high" else "high"
        axes.append({"name": f"Связка примера ({word})", "kind": "bundle", "paths": [link, P],
                     side: {link: 0.3, P: term["end"]}, other: {link: 0.7, P: c}, "dist": "triangular"})
        s.append(term["s"])
    return axes, s, c


@functools.lru_cache(maxsize=None)
def ex_book(key: str | None = "additive") -> Any:
    """Книга фикстуры с осями примера и центром пути P примера; `key` — ключ сложения связок (None — без ключа)."""
    axes, _, c = _ex_axes()
    changes = {"opex__real_growth__2028": c, "valuation__uncertainty__axes": axes}
    if key is not None:
        changes["valuation__uncertainty__bundle_compose"] = key
    return S.book_of(**changes)


def _increment(c: float, s: float, end: float) -> float:
    """Приращение связки от центра c (формула методики, независимо от ядра)."""
    return (c + abs(s) * (end - c)) - c


def _ex_terms(c: float) -> tuple[float, list[float]]:
    """Сдвиг и приращения связок примера от центра c (формулы методики)."""
    terms = example()["bundle_sum"]["terms"]
    shift = next(abs(t["s"]) * t["end"] for t in terms if t["kind"] == "shift")
    return shift, [_increment(c, t["s"], t["end"]) for t in terms if t["kind"] == "bundle"]


def check_bundle_refusal_without_key() -> None:
    """Без ключа (и при exclusive) общий путь двух связок — прежний отказ схемы и прогона (текст «вида bundle»)."""
    axes, s, _ = _ex_axes()
    refused(lambda: ex_book(None), P, "вида bundle")
    refused(lambda: ex_book("exclusive"), P, "вида bundle")
    book = S.book_of()
    bundles = [a for a in axes if a["kind"] == "bundle"]
    refused(lambda: _u().draw_overrides(book, bundles, [0.5] * len(bundles)), P)


def check_bundle_sum() -> None:
    """Пример bundle_sum: путь opex.real_growth.2028 (центр 0,0039) несут три связки (s −0,6 / +0,3 / −1,0) и ось вида
    shift на траектории (s +0,5): v = (c + сдвиг) + fsum(Δ_k), Δ_k = (c + |s|(e − c)) − c — бит в бит формуле и числу
    примера 0,00686; перестановка осей — те же подмены бит в бит; книга прогона несёт то же значение."""
    U = _u()
    ex = example()["bundle_sum"]
    book = ex_book()
    axes, s, c = _ex_axes()
    assert float(book.get(P)) == c == ex["centre"]
    shift, deltas = _ex_terms(c)
    want = (c + shift) + math.fsum(deltas)
    got = U.draw_overrides(book, axes, s)
    assert P not in got and got[WHOLE]["2028"] == want == ex["value"] == ex["value_core"], (got[WHOLE]["2028"], want)
    assert float(U.draw_book(book, axes, s).get(P)) == want
    rng = random.Random(4)
    for _ in range(6):
        order = list(range(len(axes)))
        rng.shuffle(order)
        assert bits(U.draw_overrides(book, [axes[i] for i in order], [s[i] for i in order])) == bits(got)
    # прочие пути связок — по одной связке на пути: прежняя строка
    for ax, sj in zip(axes, s):
        if ax["kind"] == "bundle":
            link = ax["paths"][0]
            b = float(book.get(link))
            end = (ax["high"] if sj >= 0 else ax["low"])[link]
            assert got[link] == b + abs(sj) * (end - b)


def check_bundle_sum_fsum() -> None:
    """Три связки с приращениями 1e16, 1 и −1e16 на пути с центром 0: сумма слева направо зависит от порядка (0 или 1;
    встроенная `sum` Python 3.12 — со своей компенсацией), сумма ядра — точная (`math.fsum`): 1,0 при любом порядке осей."""
    U = _u()
    book = S.book_of(opex__real_growth__2028=0.0, valuation__uncertainty__bundle_compose="additive")
    ends = (1e16, 1.0, -1e16)
    axes = [{"name": f"Связка {i}", "kind": "bundle", "paths": [P], "low": {P: e}, "high": {P: e},
             "dist": "triangular"} for i, e in enumerate(ends)]
    naive = {functools.reduce(lambda a, b: a + b, order, 0.0) for order in itertools.permutations(ends)}
    assert naive == {0.0, 1.0}, naive
    for order in itertools.permutations(range(3)):
        got = U.draw_overrides(book, [axes[i] for i in order], [1.0, 1.0, 1.0])
        assert got[P] == 1.0, (order, got[P])


def check_bundle_trial_centre() -> None:
    """Книга-копия (вариант, строка обратного расчёта): подмена пути 0,0050 сохраняется целиком, приращения связок — от
    центра корневой книги 0,0039: 0,0050 + сдвиг + fsum(Δ_k(0,0039)) = 0,00796 примера бит в бит; копия копии — та же
    корневая книга. Одна связка на копии — значение копии плюс приращение от центра (и `axis_overrides` — цена конца
    оси на копии); на корневой книге — прежняя строка."""
    U = _u()
    ex = example()["bundle_sum"]
    book = ex_book()
    axes, s, c = _ex_axes()
    trial = book.with_overrides({P: ex["trial_centre"]})
    shift, deltas = _ex_terms(c)
    want = (ex["trial_centre"] + shift) + math.fsum(deltas)
    assert want == ex["trial_value"] == ex["trial_value_core"]
    assert U.draw_overrides(trial, axes, s)[WHOLE]["2028"] == want
    twice = trial.with_overrides({"credit.kappa": float(trial.get("credit.kappa"))})
    assert twice.base is book and U.draw_overrides(twice, axes, s)[WHOLE]["2028"] == want
    one = next(a for a in axes if a["name"].endswith("(страхование)"))
    sj = s[axes.index(one)]
    end = one["high" if sj >= 0 else "low"][P]
    on_copy = ex["trial_centre"] + _increment(c, sj, end)
    assert U.axis_overrides(trial, one, sj)[P] == on_copy
    assert U.draw_overrides(trial, [one], [sj])[P] == on_copy
    assert U.axis_overrides(book, one, sj)[P] == c + abs(sj) * (end - c)
    assert U.draw_overrides(book, [one], [sj])[P] == c + abs(sj) * (end - c)
    # без ключа на копии — прежняя строка: приращение от значения копии (так было, флаг F1 методики)
    plain = S.book_of(opex__real_growth__2028=c).with_overrides({P: ex["trial_centre"]})
    b = ex["trial_centre"]
    assert U.axis_overrides(plain, one, sj)[P] == b + abs(sj) * (end - b)


def check_bundle_zero() -> None:
    """Все оси в положении ноль: книга бит в бит и при общих путях связок (Δ = 0), лёгкая сетка — точка бит в бит."""
    from model.grid import run_grid
    U = _u()
    book = ex_book()
    axes = list(book.get(AX))
    assert U.draw_book(book, axes, [0.0] * len(axes)).data == book.data
    zero = U.draw_overrides(book, axes, [0.0] * len(axes))
    assert zero[WHOLE]["2028"] == float(book.get(P))
    live = S4.book_live(book)
    a = run_grid(book, S4.t_facts(), live, summary=True)
    b = run_grid(U.draw_book(book, axes, [0.0] * len(axes)), S4.t_facts(), live, summary=True)
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high)


def _same_draws(plain: Any, keyed: Any, n: int = 50) -> None:
    U = _u()
    axes = list(plain.get(AX))
    assert bits(axes) == bits(list(keyed.get(AX)))
    for s in U.draw_points(n, len(axes), int(plain.get("valuation.uncertainty.seed"))):
        assert bits(U.draw_overrides(plain, axes, s)) == bits(U.draw_overrides(keyed, axes, s)), s


def check_bundle_no_overlap_bit_for_bit() -> None:
    """Ключ на книге без общих путей связок (связка и сдвиг на одном пути — можно): подмены прогонов полосы на 50 точках
    гиперкуба — бит в бит те же, что без ключа (путь одной связки на корневой книге — прежняя строка); фикстура `core_t`
    со связкой и книга Совкомбанка дерева (нет книги — только фикстура)."""
    from tests.support_core import REAL_BOOK, real_facts_ready
    plain = S4.bundle_book()
    keyed = S.book_of(**{"valuation__uncertainty__axes": list(plain.get(AX)),
                         "valuation__uncertainty__bundle_compose": "additive"})
    _same_draws(plain, keyed)
    if REAL_BOOK.exists() and real_facts_ready():
        book, data = _real_book()
        data = copy.deepcopy(data)
        data["valuation"]["uncertainty"]["bundle_compose"] = "additive"
        from model.book import book_from_dict
        _same_draws(book, book_from_dict(data, facts=_real_facts()))


def check_bundle_first_path_unique() -> None:
    """При ключе первые пути осей попарно различны (адрес оси для листа вывода, печати и общих случайных чисел):
    связка с первым путём оси вида shift — отказ с обоими местами; без ключа та же книга грузится (прежние книги)."""
    axes = S4.fixture_axes()
    twin = {"name": "Связка на пути сдвига", "kind": "bundle", "paths": [S4.P_YEAR, S4.P_FEES],
            "low": {S4.P_YEAR: 0.05, S4.P_FEES: 0.4}, "high": {S4.P_YEAR: 0.03, S4.P_FEES: 0.6}, "dist": "triangular"}
    plain = S.book_of(**{"valuation__uncertainty__axes": axes + [S4.SHIFT_SAME, twin]})
    assert [a["paths"][0] for a in plain.get(AX)].count(S4.P_YEAR) == 2
    n = len(axes)
    text = refused(lambda: S.book_of(**{"valuation__uncertainty__axes": axes + [S4.SHIFT_SAME, twin],
                                        "valuation__uncertainty__bundle_compose": "additive"}),
                   f"первый путь {S4.P_YEAR}", f"axes[{n}]", f"axes[{n + 1}]")
    assert "Р5-4" in text


def _weights_book(axes_extra: list[dict], key: bool) -> Any:
    weights = {"cards": 0.5, "cash_loans": 0.5, "auto": 0.5, "mortgage": 0.5, "sme_loans": 1.0, "corp_loans": 1.0}
    changes = {"opex__volume_weights": weights, "valuation__uncertainty__axes": S4.fixture_axes() + axes_extra}
    if key:
        changes["valuation__uncertainty__bundle_compose"] = "additive"
    return S.book_of(**changes)


W_PATH = "opex.volume_weights.mortgage"      # вес книги в базе расходов: число ≥ 0 (схема), центр 0,5


def _w_bundle(name: str, first: str, low_w: float) -> dict:
    return {"name": name, "kind": "bundle", "paths": [first, W_PATH], "low": {first: 0.3, W_PATH: low_w},
            "high": {first: 0.7, W_PATH: 0.6}, "dist": "triangular"}


def check_bundle_corner_rule() -> None:
    """Правило углов (только при ключе): путь двух и более осей-приращений проходит схему в углах v_min / v_max. Две
    связки на весе книги (центр 0,5, низы 0,2 и 0,1: угол −0,2) — отказ «угол сложения осей» с путём; низы 0,3 и 0,3
    (угол 0,1) — книга грузится. Связка (низ 0,1) и ось вида shift на ВСЕЙ таблице весов (низ −0,3): угол −0,2 —
    отказ; та же книга без ключа грузится (связка со сдвигом складывалась и раньше)."""
    first, second = "opex.volume_link", "fees.volume_link"
    a, b = _w_bundle("Вес ипотеки, М13", first, 0.2), _w_bundle("Вес ипотеки, база", second, 0.1)
    refused(lambda: _weights_book([a, b], True), "угол сложения осей на пути", W_PATH, "v_min")
    ok = _weights_book([_w_bundle("Вес ипотеки, М13", first, 0.3), _w_bundle("Вес ипотеки, база", second, 0.3)], True)
    assert float(ok.get(W_PATH)) == 0.5
    shift = {"name": "Веса базы расходов", "kind": "shift", "paths": ["opex.volume_weights"], "low": -0.3, "high": 0.3,
             "dist": "triangular"}
    one = _w_bundle("Вес ипотеки, М13", first, 0.1)
    refused(lambda: _weights_book([shift, one], True), "угол сложения осей на пути", W_PATH)
    assert float(_weights_book([shift, one], False).get(W_PATH)) == 0.5
    assert float(_weights_book([shift, _w_bundle("Вес ипотеки, М13", first, 0.35)], True).get(W_PATH)) == 0.5


def check_bundle_corners_only_on_the_root_book() -> None:
    """Правило углов судит книгу, чьи значения — центр связок: у копии (прогон, вариант) путь уже сдвинут, и углы «от
    значения копии» ничего не говорят об области полосы. Копия книги, чьи углы в области, с весом у края: схема копии
    без правила углов принимает её, с правилом — отказала бы; инвариант book_schema сетки копии молчит."""
    from model.book_schema import validate
    from model.checks import check_invariants
    from model.grid import run_grid
    from tests.support_core_p1 import t_facts_with_books
    shift = {"name": "Веса базы расходов", "kind": "shift", "paths": ["opex.volume_weights"], "low": -0.3, "high": 0.3,
             "dist": "triangular"}
    book = _weights_book([shift, _w_bundle("Вес ипотеки, М13", "opex.volume_link", 0.35)], True)
    copy_ = book.with_overrides({W_PATH: 0.1})
    assert copy_.base is book and float(copy_.get(W_PATH)) == 0.1
    refused(lambda: validate(copy_.data), "угол сложения осей на пути", W_PATH)
    validate(copy_.data, corners=False)
    facts = t_facts_with_books()
    run = run_grid(copy_, facts, S4.book_live(copy_))
    schema = [f for f in check_invariants(run) if f.name == "book_schema"]
    assert len(schema) == 1 and not schema[0].fired, schema


def check_bundle_value_dict_overlap() -> None:
    """При ключе общий путь связки с осью вида value или словарём оси dict — прежний отказ (схема и прогон)."""
    U = _u()
    axes = S4.fixture_axes()
    on = {"valuation__uncertainty__bundle_compose": "additive"}

    def with_bundle(*paths: str) -> Callable[[], Any]:
        ax = {**copy.deepcopy(S4.BUNDLE), "paths": list(paths), "low": {p: 0.0 for p in paths},
              "high": {p: 0.1 for p in paths}}
        return lambda: S.book_of(**{"valuation__uncertainty__axes": axes + [ax], **on})

    refused(with_bundle(S4.P_OPEX, "credit.kappa"), "credit.kappa", "вида value")
    refused(with_bundle(S4.P_OPEX, "joint.world_prob.N"), "joint.world_prob.N", "вида dict")
    value = {"name": "Связь расходов", "kind": "value", "paths": [S4.P_OPEX], "low": 0.2, "high": 0.6,
             "dist": "triangular"}
    book = S.book_of(**on)
    refused(lambda: U.draw_overrides(book, [value, S4.BUNDLE], (0.1, 0.1)), S4.P_OPEX, "вида value")
    second = {**copy.deepcopy(S4.BUNDLE), "name": "Вторая связка", "paths": [S4.P_FEES], "low": {S4.P_FEES: 0.2},
              "high": {S4.P_FEES: 0.8}}
    refused(lambda: U.draw_overrides(book, [value, second, S4.BUNDLE], (0.1, 0.2, 0.1)), S4.P_OPEX, "вида value")


def check_bundle_axis_end_price() -> None:
    """Цена конца оси (одна ось на конце, прочие — книга, класс 4): на корневой книге путь — конец этой связки и при
    общем пути; точка конца равна точке книги, где все пути связки на этом конце (1e-12). На книге-копии путь —
    значение копии плюс приращение конца от центра корневой книги."""
    from model.grid import run_grid
    U = _u()
    book = ex_book()
    facts, live = S4.t_facts(), S4.book_live(book)
    ax = next(a for a in book.get(AX) if a["name"].endswith("(комиссии)"))
    for s, end in ((-1.0, "low"), (1.0, "high")):
        ov = U.axis_overrides(book, ax, s)
        assert set(ov) == set(ax["paths"]) and all(close(ov[p], ax[end][p], abs_=1e-15) for p in ax["paths"])
        a = run_grid(U.trial_book(book, ov), facts, live, summary=True)
        b = run_grid(book.with_overrides({p: ax[end][p] for p in ax["paths"]}), facts, live, summary=True)
        assert close(a.point, b.point, 1e-12), (end, a.point, b.point)
    trial = book.with_overrides({P: 0.0050})
    got = U.axis_overrides(trial, ax, -1.0)[P]
    assert got == 0.0050 + _increment(float(book.get(P)), -1.0, ax["low"][P]) and got != ax["low"][P]


def check_bundle_reverse_row_keeps_its_value() -> None:
    """Строка обратного расчёта на пути связки (флаг F2 методики): книга строки — копия со значением v на пути; при
    ключе прогон её полосы несёт v + Δ(центр корневой книги), без ключа — v + |s|(e − v) (связка тянула проверяемое
    значение к своему концу)."""
    from model.reverse import reverse_trial
    U = _u()
    book = ex_book()
    axes, s, c = _ex_axes()
    one = next(a for a in axes if a["name"].endswith("(комиссии)"))
    row = {"name": "Строка на пути связки", "kind": "value", "paths": [P], "search": [0.0, 0.02], "range": [0.0, 0.01],
           "unit": "доля"}
    v = 0.0071
    trial = reverse_trial(book, row, v, follow=False)
    sj = s[axes.index(one)]
    end = one["high" if sj >= 0 else "low"][P]
    assert U.draw_overrides(trial, [one], [sj])[P] == v + _increment(c, sj, end)
    plain = reverse_trial(S.book_of(opex__real_growth__2028=c), row, v, follow=False)
    assert U.draw_overrides(plain, [one], [sj])[P] == v + abs(sj) * (end - v)


def check_bundle_band_like() -> None:
    """Полоса с записями прогонов (`band(like=…)`) на книге с ключом и общими путями — те же прогоны, что без записей."""
    U = _u()
    book = ex_book()
    facts, live = S4.t_facts(), S4.book_live(book)
    first = U.band(book, facts, live, draws=4, workers=1, keep=True)
    again = U.band(book, facts, live, draws=4, workers=1, like=first)
    assert (first.low_draws, first.high_draws) == (again.low_draws, again.high_draws)
    assert [r["low"] for r in first.rows] == [r["low"] for r in again.rows]


def check_reanchor_shared_path() -> None:
    """Перенос якоря (М§15.2): путь, который несут две связки, — центр один, концы ОБЕИХ идут за ним одним правилом
    `стало + наклон × (конец − было)`, каждый один раз."""
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("tool_reanchor_p4", ROOT / "ops" / "tools" / "reanchor.py")
    R = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = R
    spec.loader.exec_module(R)
    p = "capital.rwa.density.corp_loans"
    axes = [{"name": f"Связка {i}", "kind": "bundle", "paths": [f"x.k{i}", p], "low": {f"x.k{i}": 0.0, p: lo},
             "high": {f"x.k{i}": 1.0, p: hi}, "dist": "triangular"} for i, (lo, hi) in enumerate(((0.8, 1.2), (0.9, 1.3)))]
    X = {"capital": {"rwa": {"density": {"corp_loans": 1.0}}}, "x": {"k0": 0.5, "k1": 0.5},
         "valuation": {"uncertainty": {"axes": axes, "off_band_axes": []}, "reverse_dcf": {"axes": []}}}
    centers = R._bundle_centers(X, ("capital.rwa.density",))
    assert centers == {p: 1.0}
    X["capital"]["rwa"]["density"]["corp_loans"] = 1.1
    R._follow_centers(X, centers, 1.1)
    got = [(a["low"][p], a["high"][p]) for a in X["valuation"]["uncertainty"]["axes"]]
    want = [(round(1.1 + 1.1 * (lo - 1.0), 6), round(1.1 + 1.1 * (hi - 1.0), 6)) for lo, hi in ((0.8, 1.2), (0.9, 1.3))]
    assert got == want, (got, want)


# ------------------------------------------------------------------ Р5-4: лист вывода

SHEET = Path("data") / "assumptions" / "evidence" / "path" / "derive_on_engine.py"


def _sheet() -> Any:
    """Лист вывода: копия мутанта (каталог запуска проверок), иначе — дерево."""
    from tests.support_book import load_module
    here = Path.cwd() / SHEET
    return load_module(here if here.exists() else ROOT / SHEET, "sheet_derive_on_engine_p4")


def _sheet_run(mod: Any, carried: list[str], share: bool = True) -> dict:
    """`ends_base_axes` листа на книге-заглушке: ось базы страхования (смесь «розница … все кредиты») несёт пути
    `carried` из корней расходов; корни строк — заглушка (решатель листа не зовётся). `share` — у страхования есть доля
    франшизы в базе расходов (opex.line_shares)."""
    ins_keys = [f"other.insurance_growth_vs_wages.{k}" for k in mod._root_keys("ins")]
    mix = ["other.insurance_volume_base.mix.retail.share", "other.insurance_volume_base.mix.loans.share"]
    paths = mix + ins_keys + carried
    ax = {"name": "База страхования", "kind": "bundle", "paths": paths,
          "low": {**{p: 0.01 for p in paths}, mix[0]: 1.0, mix[1]: 0.0},
          "high": {**{p: 0.02 for p in paths}, mix[0]: 0.0, mix[1]: 1.0}, "dist": "triangular"}
    raw = {AX: [ax], "opex.line_shares": {"insurance": 0.05 if share else 0.0},
           INS_B: {"mix": {"retail": {"share": 0.98, "base": dict(T_RETAIL)}, "loans": {"share": 0.02, "base": "loans"}}}}
    book = SimpleNamespace(get=lambda p: raw[p], opt=lambda p, d=None: copy.deepcopy(raw.get(p, d)))
    eng = SimpleNamespace(book=book, overrides={}, level_goals={}, level_evidence={}, value=lambda p: {})
    mod.QUIET[0] = True
    mod.sync_line_bases = lambda eng_: None
    mod._solve_line = lambda eng_, ln, *a, **k: {"anchor": 0.001, "lt": 0.0, "g0": 0.002}
    out: dict = {"ends": {}}
    mod.ends_base_axes(eng, out)
    return out["ends"]["base_axes"]["ins"]


def check_sheet_base_axis_opex() -> None:
    """Лист вывода (Р5-4): ось базы строки, чьи пути — все ключи корней расходов, несёт корни расходов в самих концах
    связки; ни одного — запись {конец}_opex, как раньше; часть — остановка листа."""
    mod = _sheet()
    opex = [f"opex.real_growth.{k}" for k in mod._root_keys("opex")]
    assert opex[0] == "opex.real_growth.2026" and len(opex) == 7
    full = _sheet_run(mod, opex)
    assert set(opex) <= set(full["low"]) and set(opex) <= set(full["high"]) and "low_opex" not in full
    none = _sheet_run(mod, [])
    assert not set(opex) & set(none["low"]) and set(none["low_opex"]) == set(opex) == set(none["high_opex"])
    assert {k: v for k, v in full["low"].items() if k in opex} == none["low_opex"]
    try:
        _sheet_run(mod, opex[:3])
    except RuntimeError as exc:
        assert "часть корней расходов" in str(exc), str(exc)
    else:
        raise AssertionError("лист не остановился на оси с частью корней расходов")
    # ось несёт все корни расходов, а доли франшизы строки в базе расходов нет — корни на концах не выводятся: остановка
    assert "low_opex" not in _sheet_run(mod, [], share=False)
    try:
        _sheet_run(mod, opex, share=False)
    except RuntimeError as exc:
        assert "доли франшизы" in str(exc), str(exc)
    else:
        raise AssertionError("лист не остановился на оси с корнями расходов без доли франшизы строки")


# ================================================================== все три ключа вместе: выпуск

def check_release_with_pass4_keys() -> None:
    """Выпуск фикстуры с ключами прохода 4 (сложение связок на общем пути, драйвер компоненты, корень множителем):
    контракт выполнен; узлов выпуска ключи не добавляют."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    axes, _, c = _ex_axes()
    data = t_dict()
    for k, v in {"valuation__terminal__fixed_growth_share": 0.0, "checks__mix_ratio_tolerance": 0.002,
                 "opex__real_growth__2028": c, "valuation__uncertainty__axes": axes,
                 "valuation__uncertainty__bundle_compose": "additive", "fees__volume_base": TWO,
                 "capital__rwa__guarantees": P3._guar(driver="fees_component", component="corp"), **MULT}.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    assert contract(d) == [], contract(d)[:5]
