"""Проба сетки: клетки книги с подменами — быстрый круг чисел (числа ПРЕДВАРИТЕЛЬНЫЕ).

    python -B ops/tools/probe_grid.py [--overrides ФАЙЛ.yaml] [--set путь=значение ...] [--out ФАЙЛ.json] [--cells] [--quiet]

Что делает: загружает машинную книгу и факты дерева, накладывает подмены (`Book.with_overrides`: путь книги →
значение; `null` — ключ неактивного режима) и считает сетку (`model.grid.run_grid`) на цене и дате книги. Печатает
точку и слои, строку якоря (RWA и оба норматива против фактов), инварианты, сработавшие гейты с числами, годовой
путь модальной клетки, слоёв и смеси точки. Ядро (`model/`) не меняется и не дублируется: всё считают его функции.

Книга — машинная книга дерева (`data/assumptions/assumptions.yaml`). Файл подмен — YAML «путь книги → значение» (или с
верхним ключом `overrides`): так считается развилка без правки шаблона — например, другая цель расходов к доходам
(`--set checks.cir_lt.target=0.48`; выведенные на ядре числа подмена не пересчитывает — для этого `ops/tools/rederive.py`).
Без подмен точка равна точке таблиц книги (`data/assumptions/results.json`) на той же цене и дате. Полосу команда не
считает. Запись — только в названный `--out` (вне git) либо никуда.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import levels as L  # noqa: E402
from model.book import load_book, load_facts  # noqa: E402
from model.checks import check_gates, check_invariants, ddm_ri_max  # noqa: E402
from model.grid import modal_cell, point_probabilities, run_grid  # noqa: E402
from model.live import live_from_book  # noqa: E402


def load_overrides(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "overrides" in data and isinstance(data["overrides"], dict):
        data = data["overrides"]
    return {str(k): v for k, v in data.items()}


def parse_set(items: list[str]) -> dict[str, Any]:
    out = {}
    for item in items:
        path, _, raw = item.partition("=")
        out[path.strip()] = yaml.safe_load(raw)
    return out


def pc(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else f"{100 * x:.{nd}f}"


def fl(x: Any) -> float | None:
    return None if x is None else float(x)


def year_rows(run, prob, years) -> list[dict]:
    rows = []
    for y in years:
        m = L.mix_year(run, prob, y)
        opex = L.year_flow(run, prob, "opex", y)
        fees = L.year_flow(run, prob, "fees", y)
        assets = L.year_mean_end(run, prob, "assets", y)
        rows.append({"year": y, "ni_sh": m["flows"]["ni_sh"], "nii": m["flows"]["nii"], "fees": fees, "opex": opex,
                     "misc": m["flows"]["misc"], "llp": m["flows"]["llp"],
                     "nim_mgmt": m["mgmt"]["nim"], "cor_mgmt": m["mgmt"]["cor"], "cir_mgmt": m["mgmt"]["cir"],
                     "nim_eng": m["nim"], "roe": m["roe"], "loans_share": m["loans_share"],
                     "opex_to_assets": None if opex is None or not assets else opex / assets,
                     "fees_to_assets": None if fees is None or not assets else fees / assets,
                     "loans": L.quarter_end(run, prob, "loans", run.ctx.timeline.quarters_of_year(y)[-1]),
                     "bv": L.quarter_end(run, prob, "bv", run.ctx.timeline.quarters_of_year(y)[-1]),
                     "rwa": L.quarter_end(run, prob, "rwa", run.ctx.timeline.quarters_of_year(y)[-1]),
                     "n20": L.quarter_end(run, prob, "n20", run.ctx.timeline.quarters_of_year(y)[-1]),
                     "n11": L.quarter_end(run, prob, "n11", run.ctx.timeline.quarters_of_year(y)[-1]),
                     "div": L.year_flow(run, prob, "div", y) if y > run.ctx.timeline.anchor_year else None})
    return rows


def print_path(title: str, rows: list[dict], say) -> None:
    say(f"  {title}")
    say("    год   ЧПМупр  CoRупр  C/Iупр   ROE    прибыль  кредиты   BV      RWA     Н20.0  Н20.1  расх/акт  ком/акт  дивид")
    for r in rows:
        say(f"    {r['year']}  {pc(r['nim_mgmt']):>6}  {pc(r['cor_mgmt']):>6}  {pc(r['cir_mgmt'], 1):>6}  {pc(r['roe'], 1):>5}  "
            f"{(r['ni_sh'] or 0):8.1f}  {(r['loans'] or 0):8.0f}  {(r['bv'] or 0):7.0f}  {(r['rwa'] or 0):7.0f}  "
            f"{pc(r['n20']):>5}  {pc(r['n11']):>5}  {pc(r['opex_to_assets']):>7}  {pc(r['fees_to_assets']):>7}  "
            f"{('' if r['div'] is None else format(r['div'], '7.1f'))}")


def collect(book, facts, *, cells: bool = False) -> dict[str, Any]:
    t0 = time.time()
    run = run_grid(book, facts, live_from_book(book, facts))
    seconds = time.time() - t0
    ctx = run.ctx
    tl = ctx.timeline
    key = modal_cell(book, ctx.posterior)
    modal = run.cell(*key)
    one = {c.key: (1.0 if c.key == key else 0.0) for c in run.cells}
    years = list(range(tl.anchor_year, tl.last_year + 1))
    af = ctx.prep.af
    q0 = lambda name: fl(modal.quarters[name][0])  # noqa: E731
    anchor = {"rwa_model": q0("rwa"), "rwa_fact": af.basel_rwa, "n20_model": q0("n20"), "n20_fact": af.n20,
              "n11_model": q0("n11"), "n11_fact": af.n11_bank, "assets": q0("assets"), "iea": q0("iea"), "bv": q0("bv"),
              "loans": q0("loans"), "funds": q0("funds"), "wholesale": q0("wholesale")}
    inv = check_invariants(run)
    gates = check_gates(run)
    out = {
        "seconds": round(seconds, 2), "price": run.market_price, "point": run.point, "low": run.low, "high": run.high,
        "lam": run.lam, "divisor": run.divisor, "bridge_amount": run.bridge_amount,
        "layers": {n: {"price": la.price, "v0": la.v0, "pb": la.pb, "roe_tc": la.roe_tc, "k_tc": la.k_tc,
                       "terminal_share": la.terminal_share, "capital_gap_mass": la.capital_gap_mass,
                       "p_price_below_market": la.p_price_below_market, "p_roe_below_k": la.p_roe_below_k}
                   for n, la in run.layers.items()},
        "modal": {"cell": "/".join(key), "price": run.cell_price(modal), "v": modal.v_ri, "pb": modal.v_ri / modal.bv_v,
                  "roe_t": modal.roe_t, "k_t": modal.k_t, "g_t": modal.g_t, "x_t": modal.x_t,
                  "n20_min": modal.n20_min, "n11_min": modal.n11_min, "flags": sorted(modal.flags)},
        "anchor": anchor, "ddm_ri_max": ddm_ri_max(run),
        "transmission": {"sigma0": ctx.transmission.sigma0, "sigma0_liab": ctx.transmission.sigma0_liab,
                         "phi": ctx.transmission.phi, "phi_assets": ctx.transmission.phi_assets,
                         "phi_liab": ctx.transmission.phi_liab, "t_real": ctx.transmission.t_real,
                         "nss_engine": dict(ctx.transmission.nss),
                         "nss_mgmt": {w: ctx.bridge.to_mgmt_nim(v) for w, v in ctx.transmission.nss.items()},
                         "pairs": dict(ctx.transmission.pairs),
                         "lt_spread": {b: dict(r) for b, r in ctx.transmission.lt_spread.items()}},
        "invariants": [{"name": f.name, "fired": f.fired, "message": f.message} for f in inv],
        "gates": [{"name": f.name, "kind": f.kind, "fired": f.fired, "mass": f.mass, "message": f.message,
                   "cells": list(f.cells)[:6]} for f in gates],
        "paths": {"modal_cell": year_rows(run, one, years),
                  "analytical": year_rows(run, dict(run.layers["analytical"].prob), years),
                  "macro_neutral": year_rows(run, dict(run.layers["macro_neutral"].prob), years),
                  "point": year_rows(run, point_probabilities(run), years)},
        "cir_lt": L.cir_lt_value(run), "funds_cost_to_key": L.funds_cost_to_key(run),
        "levels": L.levels(run),
        "modal_quarters": {name: [None if x is None else float(x) for x in modal.quarters[name][:13]]
                           for name in ("nim", "cor", "nii", "ni_sh", "opex", "fees", "misc", "n20", "n11", "req20_glide",
                                        "req11_glide", "lam", "loans", "rwa", "bv", "div", "coupon", "om", "wholesale",
                                        "funds", "securities", "liquidity", "assets", "key")},
        "modal_growth": {k: list(v) for k, v in modal.growth.items()},
        "modal_dps": {str(k): v for k, v in modal.dps.items()},
    }
    if cells:
        out["cells"] = [{"cell": c.label, "p_analytical": run.layers["analytical"].prob[c.key],
                         "price": run.cell_price(c), "pb": c.v_ri / c.bv_v, "roe_t": c.roe_t, "k_t": c.k_t,
                         "x_t": c.x_t, "n20_min": c.n20_min, "n11_min": c.n11_min, "gap_period": c.gap_period,
                         "terminal_share": c.terminal_share, "flags": sorted(c.flags)} for c in run.cells]
    return out


def report(out: dict[str, Any], say=print, *, quarters: bool = True) -> None:
    say(f"сетка: {out['seconds']} с; цена книги {out['price']:.2f} ₽; ТОЧКА {out['point']:.2f} ₽ (ПРЕДВАРИТЕЛЬНО); низ "
        f"{out['low']:.2f}, верх {out['high']:.2f}; λ {out['lam']}; делитель {out['divisor']:.1f} млн")
    for name, la in out["layers"].items():
        say(f"  слой {name:15s} цена {la['price']:7.2f}  P/B {la['pb']:.3f}  ROE {pc(la['roe_tc'], 1)} %  k {pc(la['k_tc'], 1)} %  "
            f"терминал {pc(la['terminal_share'], 0)} %  масса разрыва капитала {pc(la['capital_gap_mass'], 1)} %  "
            f"P(цена<рынка) {pc(la['p_price_below_market'], 0)} %")
    m = out["modal"]
    say(f"  модальная клетка {m['cell']}: цена {m['price']:.2f} ₽, P/B {m['pb']:.3f}, ROE_T {pc(m['roe_t'], 1)} %, k_T {pc(m['k_t'], 1)} %, "
        f"X_T {m['x_t']:.1f}; мин. Н20.0 {pc(m['n20_min'])} %, Н20.1 {pc(m['n11_min'])} %; флаги {m['flags']}")
    a = out["anchor"]
    say(f"  якорь: RWA {a['rwa_model']:.1f} (факт {a['rwa_fact']}); Н20.0 {pc(a['n20_model'], 3)} % (факт {pc(a['n20_fact'], 3)}); "
        f"Н20.1 {pc(a['n11_model'], 3)} % (факт {pc(a['n11_fact'], 3)}); активы {a['assets']}; IEA {a['iea']}; BV {a['bv']}")
    t = out["transmission"]
    say(f"  передача: σ0_A {pc(t['sigma0'], 3)} п.п., σ0_L {pc(t['sigma0_liab'], 3)}, φ {t['phi']:.4f} (φ_A {t['phi_assets']:.4f}, φ_L {t['phi_liab']:.4f}), "
        f"T_real {t['t_real']:+.4f}; Nss упр.: " + ", ".join(f"{w} {pc(v, 3)}" for w, v in t["nss_mgmt"].items())
        + "; пары " + ", ".join(f"{k} {'—' if v is None else format(v, '+.3f')}" for k, v in t["pairs"].items()))
    say("  LT-спреды книг к опоре по мирам: " + "; ".join(
        f"{b}: " + ", ".join(f"{w} {pc(v)}" for w, v in row.items()) for b, row in t["lt_spread"].items()))
    say(f"  DDM = RI: наибольшая невязка {out['ddm_ri_max']:.2e}")
    bad = [f for f in out["invariants"] if f["fired"]]
    say(f"  инварианты: {len(out['invariants'])} проверено, нарушено {len(bad)}")
    for f in bad:
        say(f"    НАРУШЕН {f['name']}: {f['message'][:400]}")
    fired = [f for f in out["gates"] if f["fired"]]
    say(f"  гейты и флаги: сработало {len(fired)} из {len(out['gates'])}")
    for f in fired:
        mass = "" if f["mass"] is None else f" [масса {pc(f['mass'], 1)} %]"
        say(f"    {f['kind']} {f['name']}{mass}: {f['message'][:600]}")
    c = out.get("cir_lt")
    if c:
        say(f"  гейт cir_lt: значение {pc(c['value'])} % (цель {pc(c['target'])} ± {pc(c['tolerance'])}); модальная клетка {pc(c['modal'])} %")
    fc = out.get("funds_cost_to_key")
    if fc:
        say("  стоимость средств клиентов к ключевой: " + ", ".join(
            f"{w} {r['ratio']:.3f}" + ("" if "modal_ratio" not in r else f" (модальная клетка {r['modal_ratio']:.3f})")
            for w, r in fc["by_world"].items()) + f" (порог {fc['max']}" + (f"; {fc['scope']}" if "scope" in fc else "") + ")")
    for name, title in (("modal_cell", "модальная клетка"), ("macro_neutral", "слой «рыночные ставки как есть»"),
                        ("analytical", "слой «свой взгляд»"), ("point", "смесь заголовка")):
        print_path(title, out["paths"][name], say)
    if quarters:
        q = out["modal_quarters"]
        say("  модальная клетка по кварталам (q = 0 — якорь):")
        say("    q   ЧПМдв  CoRдв    ЧПД   прибыль  расходы   Н20.0  треб20   Н20.1  треб11    λ    кредиты    RWA   дивид  купон  прочие дв.")
        for i in range(len(q["nim"])):
            f = lambda k, w=7, nd=1: ("" if q[k][i] is None else format(q[k][i], f"{w}.{nd}f"))  # noqa: E731
            say(f"    {i:2d}  {pc(q['nim'][i]):>5}  {pc(q['cor'][i]):>5}  {f('nii')}  {f('ni_sh')}  {f('opex')}  {pc(q['n20'][i]):>6}  "
                f"{pc(q['req20_glide'][i]):>6}  {pc(q['n11'][i]):>6}  {pc(q['req11_glide'][i]):>6}  {f('lam', 5, 2)}  {f('loans', 8, 0)}  "
                f"{f('rwa', 7, 0)}  {f('div', 6, 1)}  {f('coupon', 5, 1)}  {f('om', 6, 1)}")
    if "cells" in out:
        say("  клетки: вес | цена | P/B | ROE_T | k_T | мин. Н20.0 | флаги")
        for c in out["cells"]:
            say(f"    {c['cell']:28s} {pc(c['p_analytical'], 1):>5}  {c['price']:8.2f}  {c['pb']:6.3f}  {pc(c['roe_t'], 1):>5}  {pc(c['k_t'], 1):>5}  "
                f"{pc(c['n20_min']):>6}  {','.join(c['flags'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="проба сетки книги с подменами (числа предварительные)")
    ap.add_argument("--overrides", help="файл подмен YAML: путь книги → значение")
    ap.add_argument("--set", action="append", default=[], help="подмена путь=значение (YAML)")
    ap.add_argument("--out", help="куда записать JSON пробы (вне git)")
    ap.add_argument("--cells", action="store_true", help="печатать таблицу 36 клеток")
    ap.add_argument("--quiet", action="store_true", help="без квартального пути модальной клетки")
    args = ap.parse_args(argv)
    facts = load_facts()
    book = load_book(facts=facts)
    overrides: dict[str, Any] = {}
    if args.overrides:
        overrides.update(load_overrides(Path(args.overrides)))
    overrides.update(parse_set(args.set))
    if overrides:
        book = book.with_overrides(overrides, create=True)
    print(f"книга {book.get('meta.version')}; подмен: {len(overrides)}" + (": " + ", ".join(list(overrides)[:8]) + (" …" if len(overrides) > 8 else "") if overrides else ""))
    out = collect(book, facts, cells=args.cells)
    out["overrides"] = {k: v for k, v in overrides.items()}
    report(out, quarters=not args.quiet)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"запись: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
