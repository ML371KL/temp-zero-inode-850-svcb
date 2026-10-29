# -*- coding: utf-8 -*-
"""Перезаякоривание книги с ключами проходов ядра 1–5 (книга Совкомбанка; `ops/tools/reanchor.py`, docs/REANCHOR.md
§3.16): что инструмент делает с каждым ключом, привязанным к якорю, и что «факт = ожидание ⇒ механика ≈ 0» держится и
у них.

Быстрые тесты (метка `tact`) — чистые функции правил на малых словарях: правило проверяется тождеством, ради которого
оно написано (путь новой книги — путь прежней), а не числом книги. Прогоны на книге дерева — `ci_only`: числа книги
меняются от круга к кругу, поэтому тесты сверяют только свойства (механика в допуске, ключи переписаны своим
правилом, отказов нет), а не значения.

* **Выкуп (М3)**: закрытый квартал — история; цена закрытого квартала снимается, ключ суммы — если он мёртв.
* **Доля денег К8 (Р6-1, Р7-6)**: квартал доли книги — якорь + 2; без правил книги — путь прежней книги; ρ на
  структуре нового якоря держит путь прочих активов.
* **Смеси баз строк (К2б) и доли базы расходов (К2)**: база новой книги пропорциональна базе прежней.
* **Множители CoR по книгам (М7)**: CoR каждой книги та же; оси и концы связок — тем же правилом.
* **Вычеты якоря**: концы связки с долей признания фонда ССПСД — тем же правилом при доле конца.
* **Поля отчёта**: нужные книге — обязательны, с причиной.
"""
from __future__ import annotations

import copy
import datetime as dt
import random
from functools import lru_cache
from types import SimpleNamespace

import pytest

from model.cell import LineBase
from model.grid import run_grid
from tests.support_core import real_book_or_skip
from tests.test_reanchor import R

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

ROLES = SimpleNamespace(loans=("c", "r1", "r2"), funds=("d1", "d2"), assets=("c", "r1", "r2", "s"),
                        names=("c", "r1", "r2", "s", "d1", "d2"))
OLD = {"c": 100.0, "r1": 40.0, "r2": 20.0, "s": 30.0, "d1": 90.0, "d2": 60.0}
NEW = {"c": 104.0, "r1": 39.0, "r2": 21.5, "s": 31.0, "d1": 93.0, "d2": 61.0}


def axes_book(axes: list, **sections) -> dict:
    return {"valuation": {"uncertainty": {"axes": axes, "off_band_axes": []}, "reverse_dcf": {"axes": []}}, **sections}


def af(balances: dict, **kw) -> SimpleNamespace:
    return SimpleNamespace(balances=dict(balances), fv_book=None, fv_loans=0.0, **kw)


# ------------------------------------------------------------------ выкуп (М3), доля денег К8 (Р7-6)


@tact
def test_the_closed_quarter_of_the_buyback_becomes_history():
    """Выкуп закрытого квартала уже в капитале и акциях нового якоря: его цена (`closed_prices`) снимается — ядро
    читает цены только кварталов сетки; ключ суммы закрытого квартала снимается, когда значения новой сетки без него
    те же, и остаётся, когда он их задаёт. Выключенный выкуп не трогается."""
    meta = {"last_period": "2028Q4"}
    X = {"meta": meta, "dividends": {"buyback": {"enabled": True, "amount": {"2026Q3": 2.0, "2026Q4": 3.0, "2027": 3.0},
                                                 "closed_prices": {"2026Q3": 10.05}}}}
    gone = R.carry_buyback(X, "2026Q3")
    assert gone == {"closed_prices": ["2026Q3"], "amount": ["2026Q3"]}
    assert "closed_prices" not in X["dividends"]["buyback"] and X["dividends"]["buyback"]["amount"] == {
        "2026Q4": 3.0, "2027": 3.0}
    year = {"meta": meta, "dividends": {"buyback": {"enabled": True, "amount": {"2026": 2.0, "2027": 3.0}}}}
    assert R.carry_buyback(year, "2026Q3") == {"closed_prices": [], "amount": []}, "ключ года — не ключ квартала"
    assert year["dividends"]["buyback"]["amount"] == {"2026": 2.0, "2027": 3.0}
    assert R.carry_buyback({"dividends": {"buyback": {"enabled": False}}}, "2026Q3") is None
    # ключ закрытого квартала, который называет путь оси (связка «выкуп по сроку»), остаётся: иначе ось книги без пути
    axis = {"name": "выкуп по сроку", "kind": "bundle", "paths": ["dividends.buyback.amount.2026Q4", "dividends.buyback.amount.2027"]}
    X = {"meta": meta, "valuation": {"uncertainty": {"axes": [axis]}},
         "dividends": {"buyback": {"enabled": True, "amount": {"2026Q4": 3.0, "2027": 3.0}}}}
    assert R.carry_buyback(X, "2026Q4") == {"closed_prices": [], "amount": []}
    assert X["dividends"]["buyback"]["amount"] == {"2026Q4": 3.0, "2027": 3.0}


@tact
def test_the_quarter_of_the_book_cash_share_moves_two_quarters_past_the_anchor():
    """Р7-6: квартал доли денег книги на новом якоре — квартал якоря + 2 (путь снова идёт два квартала от факта);
    без правил книги — путь прежней книги: квартал прежний, если он позже нового якоря, иначе первый прогнозный.
    Доля якоря (`share: anchor`) правила не требует."""
    def book(share, frm):
        return {"volumes": {"cash_assets": {"share": share, "share_from": frm}}}
    X = book(0.06, "2026Q4")
    assert R.carry_cash_share(X, "2026Q3") == ("2026Q4", "2027Q1") and X["volumes"]["cash_assets"]["share_from"] == "2027Q1"
    assert R.carry_cash_share(book(0.06, "2026Q4"), "2026Q3", rule=False) == ("2026Q4", "2026Q4")
    assert R.carry_cash_share(book(0.06, "2026Q4"), "2026Q4", rule=False) == ("2026Q4", "2027Q1")
    assert R.carry_cash_share(book(0.06, "2026Q4"), "2026Q4") == ("2026Q4", "2027Q2")
    assert R.carry_cash_share(book("anchor", "2026Q4"), "2026Q3") is None
    assert R.carry_cash_share({"volumes": {}}, "2026Q3") is None


@tact
def test_the_other_assets_path_of_the_book_cash_share_is_kept_on_the_new_structure():
    """К8 с долей книги: прочие активы пути OA_q = ρ L_q + F + c_q (D_q − a_0 L_q) стоят на структуре якоря a_0 =
    D_0 / L_0. Правило ρ′ = ρ_1 + (c* − c_1)(a_1 − a_0) даёт с квартала доли книги (c_q = c*) те же прочие активы при
    любых кредитах и средствах — и отношение нового якоря, когда факт равен пути."""
    w = {"d1": 1.0, "d2": 1.0}
    d0, l0 = sum(OLD[b] for b in w), sum(OLD[b] for b in ROLES.loans)
    d1, l1 = sum(NEW[b] for b in w), sum(NEW[b] for b in ROLES.loans)
    rho, fixed, r, s_star, s1 = 0.25, 5.0, 0.004, 0.06, 0.055
    c1, c_star = s1 + r, s_star + r
    oa1 = rho * l1 + fixed + c1 * (d1 - d0 / l0 * l1)          # прочие активы квартала 1 по пути прежней книги
    prep = SimpleNamespace(cash=SimpleNamespace(share_q=(0.0, c1), base=LineBase(kind="books", weights=w, end0=d0),
                                                reserves=r),
                           af=af(OLD), rwa_w=SimpleNamespace(oa_fixed=fixed))
    facts = SimpleNamespace(has=lambda *a: False)
    X = {"volumes": {"cash_assets": {"share": s_star, "share_from": "2026Q4"}, "other_assets_to_loans": "anchor"}}
    got = R.carry_cash_structure(X, prep, af(NEW, other_assets=oa1), facts, ROLES)
    new_rho = X["volumes"]["other_assets_to_loans"]
    assert got["rho"] == new_rho and got["rho_anchor"] == pytest.approx((oa1 - fixed) / l1, abs=1e-12)
    rng = random.Random(7)
    for _ in range(5):
        loans, funds = rng.uniform(100, 300), rng.uniform(100, 300)
        old_oa = rho * loans + fixed + c_star * (funds - d0 / l0 * loans)
        new_oa = new_rho * loans + fixed + c_star * (funds - d1 / l1 * loans)
        assert new_oa == pytest.approx(old_oa, abs=1e-7)
    assert R.carry_cash_structure({"volumes": {"cash_assets": {"share": "anchor"}}}, prep, af(NEW), facts, ROLES) is None


# ------------------------------------------------------------------ базы строк (К2б, К2)


def mix_book(axes: list) -> dict:
    return axes_book(axes, fees={"volume_base": {"mix": {"corp": {"share": 0.8, "base": {"c": 1.0}},
                                                        "retail": {"share": 0.2, "base": "loans"}}}})


@tact
def test_the_shares_of_a_line_mix_are_written_on_the_new_composition():
    """Доли смеси — доли строки на якоре: на новом якоре `s′_k = s_k g_k / Σ s_j g_j`, и база строки новой книги
    пропорциональна базе прежней при любых остатках (рост тот же). Концы оси-связки по долям — тем же правилом при
    долях конца; ось вида value по одной доле и конец с суммой долей не единица — отказ."""
    paths = ["fees.volume_base.mix.corp.share", "fees.volume_base.mix.retail.share", "fees.growth_vs_wages.2027"]
    bundle = {"name": "база", "kind": "bundle", "paths": paths,
              "low": {paths[0]: 0.6, paths[1]: 0.4, paths[2]: 0.01}, "high": {paths[0]: 1.0, paths[1]: 0.0, paths[2]: 0.03}}
    X = mix_book([bundle])
    out = R.carry_line_mix(X, af(OLD), af(NEW), ROLES)["fees.volume_base"]
    mix = X["fees"]["volume_base"]["mix"]
    assert sum(c["share"] for c in mix.values()) == pytest.approx(1.0, abs=1e-12)

    def level(bal, comp):
        return R._component_level(comp["base"], bal, ROLES)

    rng = random.Random(3)
    ratios = []
    for _ in range(5):
        bal = {b: v * rng.uniform(0.8, 1.3) for b, v in OLD.items()}
        old = sum(out["was"][k] * level(bal, c) / level(OLD, c) for k, c in mix.items())
        new = sum(mix[k]["share"] * level(bal, c) / level(NEW, c) for k, c in mix.items())
        ratios.append(new / old)
    assert max(ratios) - min(ratios) < 1e-8, "база новой книги — множитель базы прежней (доли — 9 знаков)"
    g = out["growth"]
    want = {k: v * g[k] / sum(v2 * g[k2] for k2, v2 in {"corp": 0.6, "retail": 0.4}.items())
            for k, v in {"corp": 0.6, "retail": 0.4}.items()}
    assert bundle["low"][paths[0]] == pytest.approx(want["corp"], abs=1e-6)
    assert bundle["low"][paths[1]] == pytest.approx(want["retail"], abs=1e-6)
    assert (bundle["high"][paths[0]], bundle["high"][paths[1]], bundle["low"][paths[2]]) == (1.0, 0.0, 0.01)
    with pytest.raises(R.ReportError, match="одно число доли"):
        R.carry_line_mix(mix_book([{"name": "доля", "kind": "value", "paths": [paths[0]], "low": 0.7, "high": 0.9}]),
                         af(OLD), af(NEW), ROLES)
    bad = copy.deepcopy(bundle)
    bad["low"] = {paths[0]: 0.6, paths[1]: 0.5}
    with pytest.raises(R.ReportError, match="не единица"):
        R.carry_line_mix(mix_book([bad]), af(OLD), af(NEW), ROLES)


@tact
def test_the_cost_base_on_the_bases_of_lines_keeps_its_path():
    """Доли базы расходов на базах строк `A^C_x = (1 − Σ s) B_x + Σ s_ℓ B_0 A^ℓ_x / A^ℓ_0`: на новом якоре правило
    `s′ = s a / ((1 − Σ s) b + Σ s a)` (a, b — рост средних квартала) держит A^C новой книги пропорциональной A^C
    прежней при любых будущих средних."""
    w_opex, w_fees = {"c": 1.0, "s": 0.5}, {"c": 1.0, "r1": 0.4}

    def lvl(w, bal):
        return sum(v * bal[b] for b, v in w.items())

    prev = {b: v * 0.97 for b, v in OLD.items()}                  # конец квартала до прежнего якоря
    b0 = (lvl(w_opex, prev) + lvl(w_opex, OLD)) / 2
    f0 = (lvl(w_fees, prev) + lvl(w_fees, OLD)) / 2
    i0 = (sum(prev[b] for b in ROLES.loans) + sum(OLD[b] for b in ROLES.loans)) / 2
    prep = SimpleNamespace(line_shares={"fees": 0.12, "insurance": 0.15}, opex_w=w_opex, hist_vol_opex={0: b0},
                           hist_vol={0: i0}, link_base="loans",
                           fees_line=LineBase(kind="books", weights=w_fees, end0=lvl(w_fees, OLD), hist={0: f0}),
                           ins_line=None)
    X = {"opex": {"line_shares": {"fees": 0.12, "insurance": 0.15}}}
    got = R.carry_line_shares(X, prep, af(OLD), af(NEW), ROLES)
    s_new = X["opex"]["line_shares"]
    b1 = (lvl(w_opex, OLD) + lvl(w_opex, NEW)) / 2
    f1 = (lvl(w_fees, OLD) + lvl(w_fees, NEW)) / 2
    i1 = (sum(OLD[b] for b in ROLES.loans) + sum(NEW[b] for b in ROLES.loans)) / 2
    assert got["base_growth"] == pytest.approx(b1 / b0) and got["line_growth"]["fees"] == pytest.approx(f1 / f0)
    rng = random.Random(5)
    ratios = []
    for _ in range(6):
        bx, fx, ix = (rng.uniform(50, 200) for _ in range(3))
        old = (1 - 0.27) * bx + 0.12 * b0 * fx / f0 + 0.15 * b0 * ix / i0
        new = (1 - sum(s_new.values())) * bx + s_new["fees"] * b1 * fx / f1 + s_new["insurance"] * b1 * ix / i1
        ratios.append(new / old)
    assert max(ratios) - min(ratios) < 1e-8
    assert R.carry_line_shares({"opex": {}}, SimpleNamespace(line_shares=None), af(OLD), af(NEW), ROLES) is None


# ------------------------------------------------------------------ множители CoR по книгам (М7)


@tact
def test_the_regime_cor_is_written_on_the_new_loan_composition():
    """М7: множители нормированы на составе кредитов якоря, путь CoR режима — «на составе якоря». Правило переноса —
    CoR клетки × f = Σ w_1 r / Σ w_0 r: у каждой книги CoR та же (r̂′_b × CoR′ = r̂_b × CoR, мост CoR аддитивный);
    κ × f; сдвиг оси — × f, концы связки — за центром с наклоном f; ось, которая двигает путь CoR вместе с другим
    путём, — отказ. Без ключа (или выключен) — ничего."""
    raw = {"c": 0.5, "r1": 1.5, "r2": 3.0}
    lt = "regimes.a.cor.LT"
    shift = {"name": "уровень", "kind": "shift", "paths": ["regimes.a.cor.LT", "regimes.b.cor.LT"], "low": -0.003,
             "high": 0.005}
    bundle = {"name": "κ", "kind": "bundle", "paths": ["credit.kappa", lt],
              "low": {"credit.kappa": 0.0, lt: 0.020}, "high": {"credit.kappa": 0.08, lt: 0.026}}
    X = axes_book([shift, bundle],
                  regimes={"ids": ["a", "b"], "cor_basis": "mgmt", "a": {"cor": {"2026": 0.025, "LT": 0.023, "LT_from": 2030}},
                           "b": {"cor": 0.03}},
                  credit={"kappa": 0.04, "book_relative": {"enabled": True, "by_book": raw}})
    old = copy.deepcopy(X)
    bridge = SimpleNamespace(cor_method="additive", cor_value=0.001)
    got = R.carry_book_cor(X, af(OLD), af(NEW), ROLES, bridge)
    f, b = got["factor"], 0.001

    def hat(bal):
        total = sum(bal[k] for k in ROLES.loans)
        norm = sum(bal[k] / total * raw[k] for k in ROLES.loans)
        return {k: raw[k] / norm for k in ROLES.loans}

    h0, h1 = hat(OLD), hat(NEW)
    assert f == pytest.approx(h0["c"] / h1["c"])
    for k in ROLES.loans:
        for was, now in ((old["regimes"]["a"]["cor"]["2026"], X["regimes"]["a"]["cor"]["2026"]),
                         (old["regimes"]["b"]["cor"], X["regimes"]["b"]["cor"])):
            assert h1[k] * (now + b) == pytest.approx(h0[k] * (was + b), abs=2e-6), k   # запись — 6 знаков
    assert X["regimes"]["a"]["cor"]["LT_from"] == 2030 and X["credit"]["kappa"] == pytest.approx(0.04 * f, abs=1e-6)
    assert (shift["low"], shift["high"]) == pytest.approx((-0.003 * f, 0.005 * f), abs=1e-6)
    now_lt = X["regimes"]["a"]["cor"]["LT"]
    assert bundle["high"][lt] == pytest.approx(now_lt + f * (0.026 - 0.023), abs=1e-6)
    assert bundle["high"]["credit.kappa"] == pytest.approx(0.08 * f, abs=1e-6)
    R.check_bundles(X, old, carried=R.regime_cor_paths(X))
    mixed = axes_book([{"name": "смесь", "kind": "shift", "paths": [lt, "opex.real_growth.2027"], "low": -1, "high": 1}],
                      **{k: copy.deepcopy(old[k]) for k in ("regimes", "credit")})
    with pytest.raises(R.ReportError, match="М7"):
        R.carry_book_cor(mixed, af(OLD), af(NEW), ROLES, bridge)
    off = copy.deepcopy(old)
    off["credit"]["book_relative"]["enabled"] = False
    assert R.carry_book_cor(off, af(OLD), af(NEW), ROLES, bridge) is None and off == {**old, "credit": off["credit"]}


# ------------------------------------------------------------------ вычеты якоря и их концы


@tact
def test_the_ends_of_the_deductions_follow_the_recognition_share_of_their_end():
    """Связка «признание фонда ССПСД»: доля f входит в BVreg якоря, и вычет конца — тем же правилом при f конца:
    `Ded(f_конца) = Ded(f) + (f_конца − f) R`. Форма книги (капитал формы 0409123) — у обоих вычетов, форма ядра —
    у второго (вычет первого норматива ядра от f не зависит). Связка с другим путём рядом с вычетами — отказ."""
    d20, d11, f = "capital.n20.deductions_anchor", "capital.n11.deductions_anchor", "capital.n20.fvoci_recognition"
    bundle = {"name": "фонд", "kind": "bundle", "paths": [f, d20, d11],
              "low": {f: 0.25, d20: 0.0, d11: 0.0}, "high": {f: 0.75, d20: 0.0, d11: 0.0}}
    X = axes_book([bundle], capital={"n20": {"fvoci_recognition": 0.5, "deductions_anchor": 25.0},
                                     "n11": {"deductions_anchor": 1.0}})
    R.deduction_ends(X, "own_funds", SimpleNamespace(fvoci_reserve=-18.0))
    assert bundle["low"] == {f: 0.25, d20: 25.0 + 4.5, d11: 1.0 + 4.5} and bundle["high"][d20] == 25.0 - 4.5
    R.deduction_ends(X, "core", SimpleNamespace(fvoci_reserve=-18.0))
    assert bundle["low"][d20] == 25.0 and bundle["low"][d11] == 5.5
    bad = axes_book([{**bundle, "paths": [f, d20, "capital.n20.gap_pp"]}], capital=X["capital"])
    with pytest.raises(R.ReportError, match="долю признания"):
        R.deduction_ends(bad, "own_funds", SimpleNamespace(fvoci_reserve=-18.0))


# ------------------------------------------------------------------ книга дерева: поля отчёта, кандидат, механика


V = dt.date(2026, 10, 20)        # день книги дерева: цена и дата книги — одна пара (выкуп по цене мира, М§5.6)


@lru_cache(maxsize=None)
def tree_scene() -> SimpleNamespace:
    book, facts = real_book_or_skip()
    v = dt.date.fromisoformat(str(book.get("meta.valuation_date")))
    live = R.live_at(book, facts, v)
    plus, run_plus, obs = R.expected_run(book, facts, live)
    expected = R.expected_report(book, facts, run=run_plus)
    cand = R.reanchor(book, facts, expected, valuation_date=v, base_run=run_plus)
    return SimpleNamespace(book=book, facts=facts, v=v, run_plus=run_plus, obs=obs, expected=expected, cand=cand)


@ci_only
def test_the_report_of_the_tree_book_carries_and_requires_the_fields_of_its_keys():
    """Поля, которые книга читает словом anchor (деньги и ФОР К8, резерв по книгам К7, номиналы гарантий К5), и
    капитал нормативов банка (вычеты книги) — в ожидаемом отчёте есть, в фактах кандидата — узлами; отчёт без них или
    с ФОР больше денег — отказ с названием поля. Акции в обращении после выкупа — в отчёте и в фактах."""
    s = tree_scene()
    need = R.panel_needs(s.book, s.facts)
    rep = s.expected
    for where, parts in need.items():
        section, key = where.split(".")
        assert key in rep[section], where
        assert set(parts) <= set(rep[section][key] if isinstance(rep[section][key], dict) else ()), where
        broken = copy.deepcopy(rep)
        broken[section].pop(key)
        with pytest.raises(R.ReportError, match=where.replace(".", r"\.")):
            R.check_report(s.book, s.facts, broken)
    if "balance.nonworking_money" in need:
        assert s.cand.facts.need("balance", "nonworking_money.total") == pytest.approx(rep["balance"]["nonworking_money"]["total"])
        if "mandatory_reserves" in need["balance.nonworking_money"]:
            bad = copy.deepcopy(rep)
            bad["balance"]["nonworking_money"]["mandatory_reserves"] = bad["balance"]["nonworking_money"]["total"] + 1
            with pytest.raises(R.ReportError, match="ФОР"):
                R.check_report(s.book, s.facts, bad)
    if s.book.opt(f"{R.BUYBACK}.enabled") is True:
        n1 = rep["shares"]["outstanding_total"]
        assert n1 < s.facts.need("shares", "outstanding_total") and s.cand.facts.need("shares", "outstanding_total") == n1
    rows = s.cand.facts.file("balance")["history"]
    old = str(s.book.get("meta.anchor_period"))
    if any(isinstance(r, dict) and "books" in r for r in (rows.values() if isinstance(rows, dict) else rows)):
        for period in (old, s.cand.period):
            row = R._row_of(rows, period)
            assert set(s.book.get("nii.books")) <= set(row["books"]), period


@ci_only
def test_the_tree_book_reanchors_with_every_key_carried_by_its_rule():
    """Кандидат на ожидаемом отчёте книги дерева: ключи проходов переписаны своим правилом и названы в производных
    величинах — CoR режимов × f (М7), доли смесей и базы расходов на составе нового якоря, квартал доли денег — якорь +
    2, ρ числом, закрытый квартал выкупа снят, вычеты — правилом книги, плотности — по слагаемым модели (сюрприз 1);
    сторож связок молчит, шаблон с правками равен кандидату, дата цены книги выкупа не сдвинута."""
    s = tree_scene()
    d, X = s.cand.derived, s.cand.data
    book = s.book
    if book.opt(f"{R.BOOK_REL}.enabled") is True:
        assert d["book_cor"] and d["book_cor"]["factor"] > 0
    for key in R.LINE_MIX:
        if isinstance(book.opt(key), dict) and "mix" in book.opt(key):
            assert key in d["line_mix"]
            assert sum(c["share"] for c in R._get(X, f"{key}.mix").values()) == pytest.approx(1.0, abs=1e-9)
    cash = book.source["volumes"].get("cash_assets") or {}
    if cash.get("share") not in (None, "anchor"):
        frm = R.period_str(*R.shift_quarter(*R.parse_period(s.cand.period), R.CASH_LEAD))
        assert d["cash_share_from"][1] == frm == X["volumes"]["cash_assets"]["share_from"]
        assert d["cash_structure"] and isinstance(X["volumes"]["other_assets_to_loans"], float)
    if book.opt(f"{R.BUYBACK}.enabled") is True:
        assert not any(R.pindex(k) <= R.pindex(s.cand.period) for k in X["dividends"]["buyback"].get("closed_prices") or {})
        assert X["meta"]["valuation_date"] == str(book.get("meta.valuation_date"))
    if R.own_funds_form(s.facts):
        assert d["deduction_form"] == "own_funds"
    if d.get("rwa_surprise") is not None:
        assert d["rwa_surprise"] == pytest.approx(1.0, abs=1e-9), "на ожидаемом отчёте RWA модели — факт"
    assert R.patch_template(R.TEMPLATE.read_text(encoding="utf-8"), s.cand) is not None
    text = "\n".join(R.pass_lines(d))
    assert ("М7" in text) == bool(d.get("book_cor")) and ("Р7-6" in text) == bool(
        d.get("cash_share_from") and d["cash_share_from"][0] != d["cash_share_from"][1])


CELLS = (("M", "crisis", "schedule"), ("M", "crisis", "strict"), ("N", "soft", "mid"), ("H", "downturn", "mid"))


@ci_only
def test_cells_of_the_tree_book_keep_their_value_per_share_on_their_own_path():
    """«Факт = ожидание ⇒ механика ≈ 0» с ключами проходов: клетки, где капитал режет рост (кризис мира M), и обычные
    сохраняют стоимость на акцию в допуске 0,1 % (выкуп закрытого квартала меняет делитель, не цену). Мера — на пути
    прежней книги (правило Р7-6 — своя строка разложения): кандидат с правилом и без него различается только
    кварталом доли денег книги."""
    s = tree_scene()
    hist = R.history_run(s.book, s.run_plus)
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS, history=hist)
    assert mech["ok"], mech["worst"]
    assert all(abs(r["rel"]) <= R.MECHANICS_TOL for r in mech["rows"])
    kept = R.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus, book_rules=False)
    moved = {R.dotted(p) for p, a, b in R.diff(kept.data, s.cand.data)}
    calibrated = (R.NEAR, "capital.n20.gap_pp", "capital.n11.gap_pp")     # калибровка к пути — своя у каждого кандидата
    assert f"{R.CASH}.share_from" in moved or not s.cand.derived["cash_share_from"]
    assert all(p == f"{R.CASH}.share_from" or R._under(p, calibrated) for p in moved), moved
    run_k = run_grid(kept.book, kept.facts, R.live_at(kept.book, kept.facts, s.v))
    run_e = run_grid(s.cand.book, s.cand.facts, R.live_at(s.cand.book, s.cand.facts, s.v))
    step = float(s.book.get("valuation.headline.print_step"))
    assert abs(run_e.point - run_k.point) <= 0.1 * step, "цена правила Р7-6 — доли шага печати"
