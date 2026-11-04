# -*- coding: utf-8 -*-
"""Объяснения сработавших гейтов книги — числами сетки книги и текстом по шаблону (шаг приёма миров и любой новой книги).

    python -B ops/tools/gate_texts.py [--numbers ФАЙЛ] [--write] [--flags ФАЙЛ]

Числа — функциями ядра на книге дерева (разложение гейта знака объёмов, пары требований гейта знака стресса, клетки
ниже пола, урезанный рост, путь маржи, P/B клеток), таблицы книги `results.json` (массы, опыт с убытком кризиса),
запись листа предельной экономики `evidence/path/out/marginal_loan_out.json` (единица сегмента КБ 2036 года по мирам);
`--numbers` — взять готовые числа (JSON того же вида), а не считать. Текст — шаблон этого файла: суждение (почему гейт
сработал и почему это свойство книги) написано один раз, числа и перечни клеток подставляются. У каждого текста —
подпись состава (какие клетки и пары сработали, знаки, порядок миров), на котором писались слова шаблона (книга 0.1):
состав другой — текст собирается тем же правилом, а в `--flags` (JSON-список строк; команда приёма кладёт их в
красные флаги отчёта) пишется «просмотреть ведущему». Запись `manual_input_overdue` — по правилу сроков ручных входов
(дата кривой миров книги, календарь фактов, срок записи не дальше ближайшего срока записей объяснений).

Масса записи — масса гейта в таблицах книги той же версии (3 знака); срок записи (`valid_until`) — прежний, у новой
записи — ближайший срок прочих записей. Без `--write` печатает файл, не пишет.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BOOK_DIR = ROOT / "data" / "assumptions"
TARGET = BOOK_DIR / "gate_explanations.yaml"
RESULTS = BOOK_DIR / "results.json"
MARGINAL = BOOK_DIR / "evidence" / "path" / "out" / "marginal_loan_out.json"
CALENDAR = ROOT / "data" / "facts" / "calendar.json"
ORDER = ("volume_sign", "stress_sign", "capital_gap", "m_crisis_vs_cbr", "growth_cut", "step_dividend", "nim_path_joint",
         "pb_by_world", "manual_input_overdue")
WORLDS = ("N", "H", "M")
W_NOM = {"N": "«Нормализация ставок»", "H": "«Высокие ставки надолго»", "M": "«Рыночный как есть»"}
R_NOM = {"soft": "«Мягкая посадка»", "norm": "«Нормализация»", "downturn": "«Розничный спад»", "crisis": "«Кризис»"}
R_GEN = {"soft": "«Мягкой посадки»", "norm": "«Нормализации»", "downturn": "«Розничного спада»", "crisis": "«Кризиса»"}
R_PREP = {"soft": "«Мягкой посадке»", "norm": "«Нормализации»", "downturn": "«Розничном спаде»", "crisis": "«Кризисе»"}
S_NOM = {"schedule": "«По графику»", "mid": "«АЦН 1 % и консолидация страховщиков»", "strict": "«Жёсткий»"}
REGIMES = ("soft", "norm", "downturn", "crisis")
SCENARIOS = ("schedule", "mid", "strict")
NUM_PREP = {1: "одной", 2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти", 6: "шести", 7: "семи", 8: "восьми", 9: "девяти",
            10: "десяти", 11: "одиннадцати", 12: "двенадцати"}
NUM_NOM = {1: "одна", 2: "две", 3: "три", 4: "четыре", 5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
           10: "десять", 11: "одиннадцать", 12: "двенадцать", 15: "пятнадцать"}
NUM_FEM_GEN = {1: "одной", 2: "двух", 3: "трёх"}
Q_ORD = {1: "первый", 2: "второй", 3: "третий", 4: "четвёртый"}
Q_ORD_GEN = {1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого"}
Q_ORD_PREP = {1: "первом", 2: "втором", 3: "третьем", 4: "четвёртом"}
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


# ------------------------------------------------------------------ печать чисел
def ru(x: float, nd: int = 2, sign: bool = False) -> str:
    """Число для текста: округление половины вверх (как печать книги), запятая, типографский минус."""
    from decimal import ROUND_HALF_UP, Decimal
    d = Decimal(repr(round(float(x), 9))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    s = f"{d:+.{nd}f}" if sign else f"{d:.{nd}f}"
    s = "+0" + s[2:] if s.startswith("-0") and set(s[2:]) <= set("0.,") and sign else s
    return s.replace("-", "−").replace(".", ",")


def pct(x: float, nd: int = 1) -> str:
    return ru(100 * x, nd)


def span(a: float, b: float, nd: int = 1, scale: float = 100.0) -> str:
    lo, hi = ru(scale * min(a, b), nd), ru(scale * max(a, b), nd)
    return lo if lo == hi else f"{lo}–{hi}"


def day_ru(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year} года"


def q_parts(period: str) -> tuple[int, int]:
    return int(period[:4]), int(period[-1])


def cell(label: str) -> tuple[str, str, str]:
    w, r, s = label.split("/")
    return w, r, s


def join_ru(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " и " + items[-1]


# ------------------------------------------------------------------ числа
def compute() -> dict:
    """Числа текстов на книге дерева (перенос листа gates_r12c.py круга 12 и pb_cells.py; счёт тот же)."""
    os.environ.setdefault("BANK_WORKERS", "2")
    from model import checks as K
    from model.book import load_book, load_facts
    from model.grid import bank_language, run_grid, world_layer
    from model.live import live_from_book
    F = load_facts()
    B = load_book(None, facts=F)
    L = live_from_book(B, F)
    g = run_grid(B, F, L)
    tl = g.ctx.timeline
    la = g.layers["analytical"]
    out: dict = {"book_version": str(B.get("meta.version")), "point": g.point}
    # volume_sign: разложение по поправкам
    off = {"capital.growth_constraint.enabled": False}
    base = run_grid(B.with_overrides(off), F, L, summary=True)

    def wp(run):
        return {w: world_layer(run, w)["price"] for w in WORLDS}
    pb = wp(base)
    opts, params = {}, {}
    for r in [str(x) for x in B.get("regimes.ids")]:
        node = B.get(f"regimes.{r}")
        if node.get("loan_growth_override"):
            opts[f"{r}:override"] = {f"regimes.{r}.loan_growth_override": {}}
        adj = node.get("loan_growth_adj") or 0.0
        if any(float(v) != 0.0 for k, v in (adj.items() if isinstance(adj, dict) else [("x", adj)]) if k != "LT_from"):
            opts[f"{r}:adj"] = {f"regimes.{r}.loan_growth_adj": 0.0}
        params[r] = {"adj": node.get("loan_growth_adj"), "override": node.get("loan_growth_override")}
    allov = dict(off)
    for v in opts.values():
        allov.update(v)
    free = run_grid(B.with_overrides(allov), F, L, summary=True)
    pf = wp(free)
    vs = {"base_point": base.point, "free_point": free.point, "d_point": free.point - base.point,
          "d_world": {w: pf[w] - pb[w] for w in pf}, "regime_params": params, "parts": {}}
    for k, v in opts.items():
        run = run_grid(B.with_overrides({**off, **v}), F, L, summary=True)
        p = wp(run)
        vs["parts"][k] = {"d_point": run.point - base.point, "d_world": {w: p[w] - pb[w] for w in p}}
    out["volume_sign"] = vs
    # stress_sign: пары требований — прибыль и стоимость
    regs = [str(r) for r in B.get("regimes.ids")]
    scen = [str(s) for s in B.get("capital.reg_scenarios.ids")]
    req = {s: float(g.ctx.prep.scenarios[s].req20[tl.Q]) for s in scen}
    pairs = []
    for w in WORLDS:
        for r in regs:
            for a in scen:
                for b in scen:
                    if req[a] > req[b] + 1e-9:
                        ca, cb = g.cell(w, r, a), g.cell(w, r, b)
                        pairs.append({"world": w, "regime": r, "stricter": a, "looser": b,
                                      "d_profit": ca.annual["ni_sh"][-1] - cb.annual["ni_sh"][-1], "d_value_bn": ca.v_price - cb.v_price})
    out["stress_pairs"] = pairs
    # клетки ниже пола и клетки шока
    cgall = []
    for c in g.cells:
        n20, fl = c.quarters["n20"], c.quarters["floor20"]
        below = [q for q in range(1, tl.Q + 1) if n20[q] is not None and n20[q] < fl[q]]
        if below:
            cgall.append({"cell": c.label, "p": la.prob[c.key], "first": tl.period(min(below)), "last": tl.period(max(below)),
                          "quarters": len(below), "gap_max": max(fl[q] - n20[q] for q in below),
                          "n20_min": min(n20[q] for q in below), "floor_at_min": fl[min(below, key=lambda q: n20[q])]})
    out["capital_gap_all"] = cgall
    gc = []
    for c in g.cells:
        vals = [(v, y) for v, y in zip(c.growth["cut_share"], c.years) if v is not None]
        if vals and max(vals)[0] > float(B.get("checks.growth_cut.max_cut_share")):
            top = max(vals)
            gc.append({"cell": c.label, "share": top[0], "year": top[1], "p": la.prob[c.key]})
    out["growth_cut"] = gc
    br, tr = g.ctx.bridge, g.ctx.transmission
    nim0 = g.ctx.facts.need("nii_books", "nim_eng_q")
    n, tol = int(B.get("checks.nim_path_joint.quarters")), float(B.get("checks.nim_path_joint.tolerance"))
    nj, nim_rows = [], []
    for c in g.cells:
        cap = max(br.to_mgmt_nim(nim0), br.to_mgmt_nim(tr.nss[c.world])) + tol
        over = [(tl.period(q), br.to_mgmt_nim(c.quarters["nim"][q])) for q in range(1, n + 1)
                if c.quarters["nim"][q] is not None and br.to_mgmt_nim(c.quarters["nim"][q]) > cap]
        ann = {y: br.to_mgmt_nim(v) for y, v in zip(c.years, c.annual["nim"]) if v is not None}
        row = {"cell": c.label, "cap": cap, "p": la.prob[c.key], "nim_2028": ann.get(2028), "nim_2029": ann.get(2029),
               "nim_2036": ann.get(2036)}
        nim_rows.append(row)
        if over:
            row.update(quarters=[o[0] for o in over], max=max(o[1] for o in over),
                       max_q=max(over, key=lambda o: o[1])[0])
            nj.append(row)
    keyN = B.get("worlds.N.key_rate")
    out["nim_path_joint"] = {"cells": nj, "rows": nim_rows, "nim0_mgmt": br.to_mgmt_nim(nim0), "tolerance": tol,
                             "nss_mgmt": {w: br.to_mgmt_nim(v) for w, v in tr.nss.items()},
                             "key_N": {h: float(keyN[h]) for h in keyN}}
    cg = []
    for c in g.cells:
        rp = g.ctx.prep.regimes[c.regime]
        if rp.shock_year is None:
            continue
        q27, q28 = tl.index("2027Q4"), tl.index("2028Q1")
        n20, fl = c.quarters["n20"], c.quarters["floor20"]
        below = [q for q in range(1, tl.Q + 1) if n20[q] is not None and n20[q] < fl[q]]
        rec = tl.period(max(below) + 1) if below and max(below) + 1 <= tl.Q else None
        loans = c.quarters["loans"]
        gy = {str(y): loans[tl.index(f"{y}Q4")] / loans[tl.index(f"{y - 1}Q4")] - 1 for y in range(2027, 2033)}
        cg.append({"cell": c.label, "p": la.prob[c.key], "n20_2027Q4": n20[q27], "floor_2027Q4": fl[q27], "floor_2028Q1": fl[q28],
                   "n20_min": c.n20_min, "gap_max": max((fl[q] - n20[q] for q in below), default=0.0),
                   "first_below": tl.period(min(below)) if below else None, "back_above": rec, "loan_growth": gy,
                   "cor_shock_mgmt": br.to_mgmt_cor(c.annual["cor"][c.years.index(rp.shock_year)]), "shock_year": rp.shock_year})
    out["crisis_cells"] = cg
    c = g.cell("H", "soft", "mid")
    out["step_dividend_cell"] = {"label": c.label, "dps": {str(k): v for k, v in zip(c.years, c.annual["dps"])},
                                 "dps_policy": {str(k): v for k, v in c.dps_policy.items()}}
    out["step_dividend_cuts"] = [{"cell": cc.label, "p": la.prob[cc.key],
                                  "cut_periods": sorted({d.period for d in cc.decisions if d.source == "model" and d.cut})}
                                 for cc in g.cells if g.ctx.prep.regimes[cc.regime].shock_year is None]
    req_q = {}
    for s in scen:
        sc = g.ctx.prep.scenarios[s]
        req_q[s] = {tl.period(q): float(sc.req20[q]) for q in range(0, tl.Q + 1)}
    out["req20"] = req_q
    out["floor20"] = {s: {tl.period(q): float(g.ctx.prep.scenarios[s].floor20[q]) for q in range(0, tl.Q + 1)} for s in scen}
    rows = []
    for cc in g.cells:
        lo, hi = B.get(f"checks.pb_by_world.{cc.world}")
        rows.append({"cell": cc.label, "pb": cc.v_price / cc.bv_v, "corridor": [lo, hi], "p": la.prob[cc.key]})
    out["pb_cells"] = rows
    out["market_pb"] = bank_language(g)["market_pb"]
    out["key_M_lt"] = float(B.get("worlds.M.key_rate")[max(B.get("worlds.M.key_rate"))])
    out["one_off_loss"] = {"amount": float(B.get("regimes.crisis.one_off_loss.amount")), "period": str(B.get("regimes.crisis.one_off_loss.period"))}
    out["checks_book"] = {k: B.get(f"checks.{k}") for k in ("m_crisis_vs_cbr", "pb_by_world", "growth_cut", "nim_path_joint", "step_dividend")}
    out["mgmt_buffer"] = float(B.get("capital.mgmt_buffer.n20_0"))
    out["gates_core"] = {f.name: {"fired": f.fired, "mass": f.mass, "message": f.message} for f in K.check_gates(g) if f.kind == "gate"}
    if RESULTS.exists():
        res = json.loads(RESULTS.read_text(encoding="utf-8"))
        if str(res.get("book_version")) == out["book_version"]:
            out["results"] = {"stress_sign": res["stress_sign"],
                              "gates": {x["name"]: {"mass": x.get("mass"), "message": x.get("message")}
                                        for x in res["checks"] if x.get("kind") == "gate" and x.get("fired")}}
    if MARGINAL.exists():
        m = json.loads(MARGINAL.read_text(encoding="utf-8"))
        out["marginal_2036"] = {w: next({"ret": r["return_segment_basis"], "k": r["cost_of_equity"]} for r in rows_w if r["year"] == 2036)
                                for w, rows_w in m["marginal"]["kb_unit"].items()}
    return out


# ------------------------------------------------------------------ тексты: суждение — здесь, числа — из `n`
NUM_PREP.update({13: "тринадцати", 14: "четырнадцати", 15: "пятнадцати", 16: "шестнадцати", 17: "семнадцати",
                 18: "восемнадцати", 19: "девятнадцати", 20: "двадцати", 27: "двадцати семи"})
S_SHORT = {"schedule": "по графику", "mid": "в сценарии «АЦН 1 % и консолидация страховщиков»", "strict": "в сценарии «Жёсткий»"}


def pp(x: float) -> str:
    """Сдвиг доли в п.п. со знаком: +1,5, −3 (нулевая дробь не печатается)."""
    return re.sub(r",0$", "", ru(100 * x, 1, True))


def trim(x: float, nd: int = 2) -> str:
    """Проценты без хвостовых нулей: 13,9; 9,25."""
    s = pct(x, nd)
    return re.sub(r",?0+$", "", s) if "," in s else s


def in_q(period: str) -> str:
    y, q = q_parts(period)
    word = Q_ORD_PREP[q]
    return f"{'во' if word.startswith('вт') else 'в'} {word} квартале {y} года"


def _back_range(periods: list[str]) -> str:
    a, b = min(periods), max(periods)
    (ya, qa), (yb, qb) = q_parts(a), q_parts(b)
    if a == b:
        return in_q(a)
    first = Q_ORD_GEN[qa]
    pre = "со" if first.startswith("вт") else "с"
    if ya == yb:
        return f"{pre} {first} по {Q_ORD[qb]} квартал {yb} года"
    return f"{pre} {first} квартала {ya} года по {Q_ORD[qb]} квартал {yb} года"


def _crisis_cor(n: dict, world: str | None = None) -> str:
    v = [c["cor_shock_mgmt"] for c in n["crisis_cells"] if world is None or cell(c["cell"])[0] == world]
    return span(min(v), max(v))


def t_volume_sign(n: dict) -> tuple[str, dict]:
    vs = n["volume_sign"]
    par = vs["regime_params"]
    ov = par["crisis"]["override"] or {}
    adj = {r: (par[r]["adj"] or {}) for r in REGIMES}
    parts = vs["parts"]
    cr, dn = parts["crisis:override"], parts["downturn:adj"]
    rest = sum(p["d_point"] for k, p in parts.items() if k not in ("crisis:override", "downturn:adj"))
    mg = n["marginal_2036"]
    below = [w for w in WORLDS if mg[w]["ret"] < mg[w]["k"]]
    sig = {"falls": vs["d_point"] < 0, "crisis_down_everywhere": all(v < 0 for v in cr["d_world"].values()),
           "most_from_crisis": abs(cr["d_point"]) > abs(vs["d_point"]) / 2, "worlds_below_k": below,
           "parts": sorted(parts)}
    words = {0: "ни в одном мире", 1: "в одном мире из трёх", 2: "в двух мирах из трёх", 3: "во всех трёх мирах"}[len(below)]
    t = (f"Гейт проверяет знак объёмных эффектов: если снять остановку кредита в кризисе (рост кредита {pct(ov['2027'])} % в "
         f"2027 году и {pct(ov['2028'])} % в 2028 году по рисковому сценарию Банка России вместо роста мира) и поправки роста "
         f"режимов ({pp(adj['soft']['2027'])} п.п. в «Мягкой посадке» и {pp(adj['downturn']['2027'])} п.п. в «Розничном спаде» "
         f"в 2027–2028 годах, {pp(adj['crisis']['2029'])} п.п. в «Кризисе» в 2029 году), оценка не должна падать, а цена мира "
         "«Рыночный как есть» — меняться хуже цены мира «Высокие ставки надолго». Проверка идёт при выключенном ограничении "
         f"роста капиталом. У книги оценка {'падает' if vs['d_point'] < 0 else 'растёт'} на {ru(abs(vs['d_point']))} ₽ "
         f"({ru(vs['base_point'])} → {ru(vs['free_point'])} ₽); по мирам: {ru(vs['d_world']['N'], 2, True)} ₽ в мире "
         f"«Нормализация ставок», {ru(vs['d_world']['H'], 2, True)} ₽ в мире «Высокие ставки надолго», "
         f"{ru(vs['d_world']['M'], 2, True)} ₽ в мире «Рыночный как есть». Большую часть падения даёт кредит в кризисе без "
         f"остановки: {ru(cr['d_point'], 2, True)} ₽ по точке (миры " + " / ".join(ru(cr["d_world"][w], 2, True) for w in WORLDS) +
         f" ₽) — лишний рост кредита в год шока идёт при стоимости риска кризиса {_crisis_cor(n)} % и требовании, растущем к "
         "ступени 2028 года, и капитал на него стоит дороже, чем он приносит, в каждом мире. Лишний рост в «Розничном спаде» "
         f"стоит {ru(dn['d_point'], 2, True)} ₽ (" + " / ".join(ru(dn["d_world"][w], 2, True) for w in WORLDS) +
         f" ₽), снятые надбавки «Мягкой посадки» и «Кризиса» — {ru(rest, 3, True)} ₽. Предельная единица корпоративного "
         "бизнеса (кредит юрлицу со средствами юрлиц и гарантиями в отношении сегмента) в 2036 году окупает капитал на "
         f"{pct(mg['N']['ret'])} % после налога в мире «Нормализация ставок» при стоимости капитала {pct(mg['N']['k'])} %, на "
         f"{pct(mg['H']['ret'])} % при {pct(mg['H']['k'])} % в мире «Высокие ставки надолго» и на {pct(mg['M']['ret'])} % при "
         f"{pct(mg['M']['k'])} % в мире «Рыночный как есть»: {words} рост кредита стоимость снижает и вне кризиса. Это "
         "свойство миров и кризисного года, а не ошибка калибровки. Калибровка ради гейта не менялась.")
    return t, sig


def _stress_cells(pairs: list[dict]) -> str:
    by: dict = {}
    for p in pairs:
        by.setdefault(p["looser"], []).append((p["world"], p["regime"]))
    order = sorted(by, key=lambda s: (-len(by[s]), SCENARIOS.index(s)))
    out = []
    for i, s in enumerate(order):
        cells = by[s]
        ws = [w for w in WORLDS if any(c[0] == w for c in cells)]
        rs = [r for r in REGIMES if any(c[1] == r for c in cells)]
        if len(cells) == len(ws) * len(rs) and i == 0:
            out.append(f"в {join_ru([R_PREP[r] for r in rs])} {'миров' if len(ws) > 1 else 'мира'} "
                       f"{join_ru([W_NOM[w] for w in ws])} — против сценария {S_NOM[s]}")
        else:
            who = ", ".join(f"у {R_GEN[r]} мира {W_NOM[w]}" for w, r in sorted(cells, key=lambda c: (WORLDS.index(c[0]), REGIMES.index(c[1]))))
            out.append(f"{who} — {'и против ' + S_NOM[s] if i else 'против сценария ' + S_NOM[s]}")
    return ", ".join(out)


def t_stress_sign(n: dict) -> tuple[str, dict]:
    ss = n["results"]["stress_sign"]
    up, loss = ss["requirement"]["cells"], ss["loss"]
    stricter = sorted({(p["world"], p["regime"], p["stricter"]) for p in up})
    scen = [s for s in SCENARIOS if any(p["stricter"] == s for p in up)]
    vals = {(p["world"], p["regime"], p["stricter"], p["looser"]): p for p in n["stress_pairs"]}
    dv = [vals[(p["world"], p["regime"], p["stricter"], p["looser"])]["d_value_bn"] for p in up]
    top = max(up, key=lambda p: p["d_profit"])
    value_up = [p for p in n["stress_pairs"] if p["d_value_bn"] > 0]
    sig = {"loss_ok": not loss["cells"], "value_up": len(value_up), "all_value_down": max(dv) < 0,
           "scenarios": scen}
    t = (f"Гейт проверяет знаки стресса двумя опытами. Первый — разовый убыток кризиса больше на {ru(loss['step'], 0)} млрд ₽ — "
         f"выполнен: стоимость ни одной клетки кризиса не растёт, на рубль убытка после налога она снижается на "
         f"{span(loss['transfer_min'], loss['transfer_max'], 2, 1.0)} ₽. Второй — при более высоком требовании к капиталу "
         "прибыль акционеров последнего года сетки (2036) не должна быть выше — нарушен в "
         f"{NUM_PREP[len(stricter)]} клетк{'е' if len(stricter) == 1 else 'ах'} сценария {join_ru([S_NOM[s] for s in scen])} "
         f"({pct(ss['mass'])} % вероятности точки): {_stress_cells(up)}. Прибыль выше на "
         f"{span(min(p['d_profit'] for p in up), max(p['d_profit'] for p in up), 1, 1.0)} млрд ₽ (больше всего — "
         f"{W_NOM[top['world']]}, {R_NOM[top['regime']]}). Это свойство мерки, а не оценки: жёсткий сценарий держит больше "
         "капитала, кредитов у него меньше, и доход на лишний капитал поднимает прибыль года, а стоимость клетки во всех "
         f"{NUM_PREP[len(up)]} парах ниже — на {span(-max(dv), -min(dv), 1, 1.0)} млрд ₽. Стоимость клетки при более жёстком "
         "требовании не выше ни в одной паре сценариев. Калибровка ради гейта не менялась.")
    return t, sig


def t_capital_gap(n: dict) -> tuple[str, dict]:
    cg, cc = n["capital_gap_all"], n["crisis_cells"]
    crisis = [c for c in cg if cell(c["cell"])[1] == "crisis"]
    other = [c for c in cg if cell(c["cell"])[1] != "crisis"]
    mass = n["results"]["gates"]["capital_gap"]["mass"]
    ly, lq = q_parts(n["one_off_loss"]["period"])
    fl28 = sorted({round(c["floor_2028Q1"], 6) for c in cc})
    early = {w: sorted((c["back_above"] or "9999Q9", SCENARIOS.index(cell(c["cell"])[2])) for c in cc if cell(c["cell"])[0] == w)[0][1]
             for w in WORLDS}
    sig = {"crisis_cells": len(crisis), "other": [c["cell"] for c in other], "other_quarters": [c["quarters"] for c in other],
           "earliest_schedule": all(v == 0 for v in early.values()), "floors_2028": len(fl28),
           "all_back": all(c["back_above"] for c in cc)}
    head = f"Это {NUM_NOM[len(crisis)]} клеток режима «Кризис» во всех мирах и сценариях"
    if other:
        w, r, s = cell(other[0]["cell"])
        head += f" и одна клетка {R_GEN[r]} мира {W_NOM[w]} в сценарии {S_NOM[s]}"
    t = ("Гейт отмечает клетки, где норматив достаточности собственных средств (капитала) банка Н1.0 опускается ниже пола "
         f"требований с надбавками. {head} (вместе {pct(mass, 2)} % вероятности; в полосе — во всех прогонах, потому что "
         f"режим «Кризис» есть в каждом из них). Разовый убыток {ru(abs(n['one_off_loss']['amount']), 0)} млрд ₽ в "
         f"{Q_ORD_PREP[lq]} квартале {ly} года и стоимость риска года шока {_crisis_cor(n)} % снижают норматив до "
         f"{span(min(c['n20_2027Q4'] for c in cc), max(c['n20_2027Q4'] for c in cc))} % к концу 2027 года — выше пола того "
         f"года {pct(cc[0]['floor_2027Q4'], 2)} %. Но 1 января 2028 года надбавки поднимают пол ступенью до {pct(fl28[0])} % "
         f"(«По графику») и {pct(fl28[-1])} % (в двух других сценариях), и норматив оказывается ниже пола на "
         f"{span(min(c['gap_max'] for c in cc), max(c['gap_max'] for c in cc))} п.п.; наименьшие значения — "
         f"{span(min(c['n20_min'] for c in cc), max(c['n20_min'] for c in cc))} %. Пробит пол с надбавками, а не минимум 8 %: "
         "книга в ответ останавливает рост кредита и не платит дивиденд за год шока, новый капитал не привлекает. Норматив "
         "возвращается выше пола " +
         ", ".join(f"{_back_range([c['back_above'] for c in cc if cell(c['cell'])[0] == w])} в мире {W_NOM[w]}" for w in WORLDS[:-1]) +
         f" и {_back_range([c['back_above'] for c in cc if cell(c['cell'])[0] == 'M'])} в мире {W_NOM['M']} (раньше всего — в "
         "сценарии «По графику»).")
    if other:
        o = other[0]
        w, r, s = cell(o["cell"])
        y, q = q_parts(o["first"])
        t += (f" Клетка {R_GEN[r]} ниже пола {'один квартал' if o['quarters'] == 1 else str(o['quarters']) + ' квартала'} — "
              f"{Q_ORD[q]} квартал {y} года, на {ru(100 * o['gap_max'], 2)} п.п. ({pct(o['n20_min'], 2)} % при поле "
              f"{pct(o['floor_at_min'], 1)} %): ступень надбавок приходит, пока прибыль мира высоких ставок медленно "
              "восстанавливает запас.")
    return t, sig


def _m_crisis(n: dict) -> list[dict]:
    return [c for c in n["crisis_cells"] if cell(c["cell"])[0] == "M"]


def _stop_years(cells: list[dict]) -> dict[str, int]:
    """Последний год без роста кредита у клеток (рост меньше 0,05 %), начиная с 2027."""
    out = {}
    for c in cells:
        last = 2026
        for y in range(2027, 2033):
            if abs(c["loan_growth"][str(y)]) < 5e-4 and last == y - 1:
                last = y
        out[cell(c["cell"])[2]] = last
    return out


def t_m_crisis_vs_cbr(n: dict) -> tuple[str, dict]:
    ch = n["checks_book"]["m_crisis_vs_cbr"]
    mc = _m_crisis(n)
    mass = n["results"]["gates"]["m_crisis_vs_cbr"]["mass"]
    stop = _stop_years(mc)
    common = min(stop.values())
    longer = [s for s in SCENARIOS if stop.get(s, 0) > common]
    rest = [s for s in SCENARIOS if s not in longer]
    g28 = [c["loan_growth"]["2028"] for c in mc]
    lo28, hi28 = ch["loan_growth"]["2028"]
    fails = sorted({re.sub(r"\s+[−-]?\d+(,\d+)?\s*%.*$", "", m.split(":", 1)[1].strip())
                    for m in n["results"]["gates"]["m_crisis_vs_cbr"]["message"].split(";") if ":" in m})
    sig = {"fails": fails, "all_zero_2028": max(abs(x) for x in g28) < 5e-4, "common_stop": common - 2027,
           "longer": longer}
    grow = {cell(c["cell"])[2]: c["loan_growth"][str(common + 1)] for c in mc}
    tail = ""
    if longer and rest:
        tail = (f", в сценари{'ях' if len(longer) > 1 else 'и'} {join_ru([S_NOM[s] for s in longer])} — и в {common + 1} году ("
                + ", ".join(f"{S_NOM[s]} — {pct(grow[s])} %" for s in rest) + ")")
    t = ("Гейт сверяет клетки «Рыночный как есть» × «Кризис» с рисковым сценарием Банка России: рост кредита 2027 года "
         f"{span(*ch['loan_growth']['2027'], 0)} %, 2028 года {span(lo28, hi28, 0)} %, стоимость риска года шока не ниже "
         f"{pct(ch['cor_shock_year'])} %, наименьший норматив достаточности собственных средств (капитала) банка Н1.0 не выше "
         f"{pct(ch['n20_min'], 2)} % (пол {pct(ch['n20_min'] - n['mgmt_buffer'])} % и запас менеджмента "
         f"{ru(100 * n['mgmt_buffer'], 2)} п.п.). Расходится одно условие — рост кредита 2028 года: {pct(max(g28))} % во всех "
         f"трёх клетках ({pct(mass, 0)} % вероятности). Причина — капитал: после разового убытка 2027 года и ступени надбавок "
         "1 января 2028 года норматив ниже пола, и книга не даёт кредиту расти, пока запас не восстановится; в этом мире рост "
         f"стоит до {common} года включительно" + tail +
         ". Кризис книги в мире высоких ставок жёстче сценария Банка России по кредиту — в консервативную сторону. Стоимость "
         f"риска года шока ({_crisis_cor(n)} %) и наименьший норматив ({span(min(c['n20_min'] for c in mc), max(c['n20_min'] for c in mc))} %) "
         "— в коридоре сценария.")
    return t, sig


def t_growth_cut(n: dict) -> tuple[str, dict]:
    cells = sorted(n["growth_cut"], key=lambda c: (WORLDS.index(cell(c["cell"])[0]), REGIMES.index(cell(c["cell"])[1]),
                                                     SCENARIOS.index(cell(c["cell"])[2])))
    mass = n["results"]["gates"]["growth_cut"]["mass"]
    ws = sorted({cell(c["cell"])[0] for c in cells}, key=WORLDS.index)
    by: dict = {}
    for c in cells:
        by.setdefault(cell(c["cell"])[1], []).append(c)
    mg = n["marginal_2036"]["M"]
    req = [v for p, v in n["req20"]["strict"].items() if p >= "2029Q1"]
    sig = {"worlds": ws, "cells": [c["cell"] for c in cells],
           "same_scenarios": len({tuple(cell(c["cell"])[2] for c in v) for v in by.values()}) == 1}
    groups = []
    first_scen = None
    for r, v in by.items():
        scen = [cell(c["cell"])[2] for c in v]
        years = {c["year"] for c in v}
        if first_scen == scen:
            nums = join_ru([f"{pct(c['share'])} %" for c in v])
            yr = f" к концу {v[0]['year']} года" if len(years) == 1 else ""
            groups.append(f"{R_NOM[r]} в тех же сценариях ({nums}{yr})")
        else:
            groups.append(f"{R_NOM[r]} в сценари{'и' if len(v) == 1 else 'ях'} " +
                          join_ru([f"{S_NOM[cell(c['cell'])[2]]} ({pct(c['share'])} % к концу {c['year']} года)" for c in v]))
            first_scen = first_scen or scen
    count = NUM_NOM.get(len(cells), str(len(cells)))
    where = f"все в мире {W_NOM[ws[0]]}" if len(ws) == 1 else "в мирах " + join_ru([W_NOM[w] for w in ws])
    t = (f"Гейт отмечает клетки, где ограничение капиталом урезает рост кредитных книг больше чем на "
         f"{pct(n['checks_book']['growth_cut']['max_cut_share'], 0)} % роста, который дал бы спрос. Таких клеток {count}, "
         f"{where} ({pct(mass)} % вероятности): {', '.join(groups)}. В мире высоких ставок предельный кредит окупает капитал хуже "
         f"его стоимости (единица корпоративного бизнеса в 2036 году — {pct(mg['ret'])} % после налога при стоимости капитала "
         f"{pct(mg['k'])} %), а требование с запасом менеджмента там {span(min(req), max(req))} % с 2029 года («Жёсткий»; запас — "
         f"{ru(100 * n['mgmt_buffer'], 2)} п.п., среднее скользящих окон): прибыль восстанавливает запас медленно, и рост годами "
         "ждёт капитала. Урезанный рост в этих клетках — порядок книги (сначала уступает рост, затем дивиденд), а не ошибка "
         f"спроса; в остальных клетках урезано не больше {pct(n['checks_book']['growth_cut']['max_cut_share'], 0)} % роста.")
    return t, sig


def t_step_dividend(n: dict) -> tuple[str, dict]:
    cuts = [c for c in n["step_dividend_cuts"] if c["cut_periods"]]
    allc = n["step_dividend_cuts"]
    mass = n["results"]["gates"]["step_dividend"]["mass"]
    cl = n["step_dividend_cell"]
    dps, pol = cl["dps"], cl["dps_policy"]
    years = [int(y) for y in pol if dps.get(y) is not None and dps[y] < pol[y] - 5e-3]    # срезанные годы клетки-примера
    fl, req = n["floor20"], n["req20"]
    f27 = sorted({round(fl[s]["2027Q1"], 6) for s in SCENARIOS})
    f28 = sorted({round(fl[s]["2028Q1"], 6) for s in SCENARIOS})
    f26 = fl["schedule"]["2026Q2"]
    msg = n["results"]["gates"]["step_dividend"]["message"]
    m = re.search(r"в (\d+) клетках \(наибольшее падение", msg)
    lam = int(m.group(1)) if m else None
    sig = {"all_cut": len(cuts) == len(allc), "years": years, "same_dps_2026_2027": abs(dps["2026"] - dps["2027"]) < 5e-3,
           "pays_more_2028": dps["2028"] > pol["2028"], "dps_2026": round(dps["2026"], 2)}
    t = ("Гейт срабатывает, когда у ступени пола норматива дивиденд по политике приходится срезать. Это все "
         f"{len(cuts)} клеток режимов без шока ({pct(mass, 0)} % вероятности): срезаны решения о дивиденде за прибыль "
         f"{join_ru([str(y) for y in years])} годов. Норматив достаточности собственных средств (капитала) банка Н1.0 на "
         "якоре — 10,985 % до вычета дивиденда за 2025 год (10,805 % после вычета) при требовании с запасом менеджмента "
         f"{pct(req['schedule']['2026Q2'], 2)} %; надбавки растут ступенями 1 января 2027 года (пол {pct(f27[0], 2)} %) и "
         f"1 января 2028 года ({span(f28[0], f28[-1])} %), и к 2028 году банку нужно на {span(f28[0] - f26, f28[-1] - f26)} п.п. "
         "капитала больше, чем в 2026 году. Книга удерживает прибыль и платит меньше политики: в клетке «Высокие ставки "
         f"надолго» × «Мягкая посадка» × «АЦН 1 % и консолидация страховщиков» — по {ru(dps['2026'])} ₽ на акцию за 2026 и "
         f"2027 годы, как банк за 2024 и 2025 годы, вместо {ru(pol['2026'])} и {ru(pol['2027'])} ₽ по политике; с 2028 года "
         f"выплата выше политики ({ru(dps['2028'])} ₽ против {ru(pol['2028'])} ₽) — книга отдаёт накопленный запас. Это "
         "порядок книги для банка, чей капитал стоит у требования: рост и дивиденд уступают ступени надбавок." +
         (f" Справочно: в {NUM_PREP.get(lam, str(lam))} клетках доля прироста кредита в квартал ступени падает больше чем на "
          f"{pct(n['checks_book']['step_dividend']['max_lam_drop'], 0)} п.п." if lam else ""))
    return t, sig


def _nim_cells(cells: list[dict]) -> str:
    by: dict = {}
    for c in cells:
        by.setdefault(cell(c["cell"])[1], []).append(cell(c["cell"])[2])
    full = [r for r in REGIMES if r in by and len(by[r]) == 3]
    part = [r for r in REGIMES if r in by and len(by[r]) < 3]
    bits = []
    if full:
        bits.append(f"{join_ru([R_NOM[r] for r in full])} во всех сценариях")
    for r in part:
        sc = sorted(by[r], key=SCENARIOS.index)
        named = [S_NOM[s] for s in sc if s != "schedule"]
        words = (["по графику"] if "schedule" in sc else []) + \
                ([f"в сценари{'ях' if len(named) > 1 else 'и'} {join_ru(named)}"] if named else [])
        bits.append(f"{R_NOM[r]} " + join_ru(words))
    return join_ru(bits)


def t_nim_path_joint(n: dict) -> tuple[str, dict]:
    nj = n["nim_path_joint"]
    cells = nj["cells"]
    mass = n["results"]["gates"]["nim_path_joint"]["mass"]
    ws = sorted({cell(c["cell"])[0] for c in cells}, key=WORLDS.index)
    caps = sorted({round(c["cap"], 6) for c in cells})
    top = max(cells, key=lambda c: c["max"])
    quarters = [q for c in cells for q in c["quarters"]]
    msg = n["results"]["gates"]["nim_path_joint"]["message"]
    rep = re.search(r"отчётная маржа квартала — ([0-9,]+) %", msg)
    key = nj["key_N"]
    nim2829 = [x for c in cells for x in (c["nim_2028"], c["nim_2029"])]
    nim36 = [c["nim_2036"] for c in cells]
    sig = {"worlds": ws, "cells": sorted(c["cell"] for c in cells), "one_cap": len(caps) == 1}
    t = ("Гейт следит, чтобы в первых восьми кварталах после якоря не было ступени маржи: управленческая чистая процентная "
         "маржа квартала не должна быть выше большей из двух величин — маржи якоря по счёту модели "
         f"({pct(nj['nim0_mgmt'], 2)} %; отчётная маржа квартала — {rep.group(1) if rep else '—'} %) и уровня своего мира — "
         f"больше чем на {ru(100 * nj['tolerance'], 1)} п.п.; порог во всех мирах — {pct(caps[0], 2)} %. Выше порога — "
         f"{cells_word(len(cells))} мира {W_NOM[ws[0]]} ({_nim_cells(cells)}; {pct(mass)} % вероятности) в кварталах {_back_range(quarters)}; "
         f"наибольшее значение — {pct(top['max'], 2)} % {in_q(top['max_q'])}. Это не ступень, а путь мира: ключевая ставка "
         f"снижается с {trim(key['2026H2'])} % в конце 2026 года до {trim(key['2028H2'])} % в конце 2028 года, средства клиентов "
         "дешевеют быстрее, чем переоцениваются кредиты, и сжатие спредов при высокой ставке уходит — маржа поднимается до "
         f"{span(min(nim2829), max(nim2829))} % в 2028–2029 годах и затем сходит к {span(min(nim36), max(nim36))} % к 2036 году. "
         f"{_nim_under(cells)} маржа первых восьми кварталов остаётся под порогом.")
    return t, sig


UNDER = {("mid", "strict"): "при двух более жёстких сценариях", ("schedule",): "по графику",
         ("schedule", "mid"): "при двух более мягких сценариях", ("mid",): "в сценарии «АЦН 1 % и консолидация страховщиков»",
         ("strict",): "в сценарии «Жёсткий»", ("schedule", "strict"): "по графику и в сценарии «Жёсткий»"}


def _nim_under(cells: list[dict]) -> str:
    """Где маржа под порогом: миры без срабатывания, режимы мира срабатывания с частью сценариев под порогом, режимы
    целиком под порогом («и в его …»)."""
    over = {(cell(c["cell"])[0], cell(c["cell"])[1], cell(c["cell"])[2]) for c in cells}
    ws = [w for w in WORLDS if not any(o[0] == w for o in over)]
    bits = [("В мирах " if len(ws) > 1 else "В мире ") + join_ru([W_NOM[w] for w in ws])] if ws else []
    whole = []
    for w in [w for w in WORLDS if w not in ws]:
        for r in REGIMES:
            under = tuple(s for s in SCENARIOS if (w, r, s) not in over)
            if len(under) == 3:
                whole.append(r)
            elif under:
                bits.append(f"в {R_PREP[r]} мира {W_NOM[w]} {UNDER[under]}")
    text = ", ".join(bits) if bits else "В остальных клетках"
    if whole:
        text += f" и в его {join_ru([R_PREP[r] for r in whole])}"
    return text[:1].upper() + text[1:]


def cells_word(k: int) -> str:
    if k % 10 == 1 and k % 100 != 11:
        return f"{NUM_NOM_F.get(k, str(k))} клетка"
    if k % 10 in (2, 3, 4) and k % 100 not in (12, 13, 14):
        return f"{NUM_NOM_F.get(k, str(k))} клетки"
    return f"{NUM_NOM.get(k, str(k))} клеток"


def t_pb_by_world(n: dict) -> tuple[str, dict]:
    rows = n["pb_cells"]
    out = [r for r in rows if not r["corridor"][0] <= r["pb"] <= r["corridor"][1]]
    mass = n["results"]["gates"]["pb_by_world"]["mass"]
    lo, hi = out[0]["corridor"] if out else rows[0]["corridor"]
    ws = sorted({cell(r["cell"])[0] for r in out}, key=WORLDS.index)
    regs = sorted({cell(r["cell"])[1] for r in out}, key=REGIMES.index)
    w = ws[0] if ws else "M"

    outs = {(cell(r["cell"])[1], cell(r["cell"])[2]): r["pb"] for r in out if cell(r["cell"])[0] == w}
    inside = {(cell(r["cell"])[1], cell(r["cell"])[2]): r["pb"] for r in rows if cell(r["cell"])[0] == w
              and (cell(r["cell"])[1], cell(r["cell"])[2]) not in outs}
    stop = _stop_years(_m_crisis(n))
    sig = {"worlds": ws, "regimes": regs, "below": all(r["pb"] < r["corridor"][0] for r in out), "count": len(out)}
    groups = []
    for r in reversed(REGIMES):                       # от тяжёлого режима к лёгкому, как в тексте 0.1
        sc = [s for s in SCENARIOS if (r, s) in outs]
        if not sc:
            continue
        vals = ", ".join(f"{ru(outs[(r, s)])} {S_NOM[s]}" for s in sc)
        groups.append(f"{R_NOM[r]} во всех трёх сценариях требований ({vals})" if len(sc) == 3 else
                      f"{R_NOM[r]} в сценари{'ях' if len(sc) > 1 else 'и'} " + join_ru([f"{S_NOM[s]} ({ru(outs[(r, s)])})" for s in sc]))
    near = []
    for r, title in (("downturn", "«Розничный спад» того же мира"), ("norm", "«Нормализация» мира")):
        sc = [s for s in SCENARIOS if (r, s) in inside]
        v = [inside[(r, s)] for s in sc]
        if v:
            where = ""
            if any((r, s) in outs for s in SCENARIOS):
                where = f" в сценари{'ях' if len(sc) > 1 else 'и'} {join_ru([S_NOM[s] for s in sc])}"
            near.append(f"{title}{where} — {span(min(v), max(v), 2, 1.0)}")
    t = (f"Гейт сверяет отношение стоимости клетки к капиталу акционеров с коридором {ru(lo, 1)}–{ru(hi, 1)}. Ниже коридора — "
         f"{cells_word(len(out))} мира {W_NOM[w]} ({pct(mass)} % вероятности): {'; '.join(groups)}; {', '.join(near)}. "
         "Это самые тяжёлые сочетания "
         f"книги: ключевая ставка около {ru(100 * n['key_M_lt'], 0)} % надолго, шок 2027 года с разовым убытком "
         f"{ru(abs(n['one_off_loss']['amount']), 0)} млрд ₽ (рост кредита стоит до {span(min(stop.values()), max(stop.values()), 0, 1.0)} "
         "годов), а требование с надбавками держит капитал, который в этом мире окупается хуже своей стоимости (единица "
         f"корпоративного бизнеса — {pct(n['marginal_2036']['M']['ret'])} % после налога при стоимости капитала "
         f"{pct(n['marginal_2036']['M']['k'])} %). Рынок оценивает банк в {ru(n['market_pb'])} капитала. Калибровка ради гейта "
         "не менялась.")
    return t, sig


NUM_NOM_F = {1: "одна", 2: "две", 3: "три", 4: "четыре", 5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять"}


def refusal_days(book: dict, notes: dict) -> dict:
    """Первые дни отказа сборки по ближайшим срокам (тем же счётом, что docs/MANUAL.md §10.9 и его тест)."""
    days, anchor = book["checks"]["manual_overdue_days"], str(book["meta"]["anchor_period"])
    curve = dt.date.fromisoformat(str(book["worlds"]["source"]["curve_date"]))
    events = json.loads(CALENDAR.read_text(encoding="utf-8"))["events"]

    def start(e):
        return dt.date.fromisoformat(str(e["latest"] if e.get("estimated") is True else e["date"]))
    out = {"curve": curve}
    past = [start(e) for e in events if e.get("kind") == "cbr_forecast" and start(e) <= curve]
    nxt = [start(e) for e in events if e.get("kind") == "cbr_forecast" and start(e) > curve]
    if past:
        out["meeting"] = max(past)
    if nxt:
        out["next_meeting"] = min(nxt)
        out["worlds"] = min(nxt) + dt.timedelta(days=int(days["worlds_after_cbr"]) + 1)
    reports = [e for e in events if e.get("kind") == "ifrs" and str(e.get("covers") or "") > anchor]
    if reports:
        first = min(reports, key=lambda e: str(e["covers"]))
        out["ifrs"] = start(first) + dt.timedelta(days=int(days["ifrs_fact"]) + 1)
        out["ifrs_covers"] = str(first["covers"])
    until = [dt.date.fromisoformat(str(v["valid_until"])) for v in notes.values()]
    if until:
        out["explanations"] = min(until) + dt.timedelta(days=1)
    return out


def t_manual_input_overdue(book: dict, notes: dict) -> tuple[str, dict, str]:
    """Запись гейта ручных входов: что о сроках миров и отчёта говорит книга. Срок — не дальше дня до отказа по отчёту и
    не дальше ближайшего срока прочих записей (иначе запись закрыла бы невнесённый отчёт МСФО)."""
    others = {k: v for k, v in notes.items() if k != "manual_input_overdue"}
    d = refusal_days(book, others)
    limit = min(x for x in (d.get("ifrs"), d.get("explanations")) if x) - dt.timedelta(days=1)
    if "meeting" not in d or "worlds" not in d or d["worlds"] <= d.get("ifrs", d["worlds"]):
        return None, {"worlds_silent": False}, limit.isoformat()      # ближе срок миров: правило текста не для этого случая
    y, q = q_parts(d["ifrs_covers"])
    months = {1: "три месяца", 2: "шесть месяцев", 3: "девять месяцев", 4: "год"}[q]
    t = ("Гейт следит за ручными входами книги. Миры ставок книги — запись семейства по кривой "
         f"{day_ru(d['curve'])}, после заседания Банка России {day_ru(d['meeting'])} со среднесрочным прогнозом: по мирам гейт "
         f"молчит до трёх недель после следующего такого заседания — до {day_ru(d['worlds'] - dt.timedelta(days=1))} "
         f"включительно. Отчёт МСФО за {months} {y} года в книгу ещё не внесён: с {day_ru(d['ifrs'])} гейт сработает по нему, "
         f"и эта запись его не объясняет — она живёт до {day_ru(limit)} включительно и называет только миры. Отчёт входит "
         f"перезаякориванием книги на {Q_ORD[q].replace('ий', 'ий')} квартал {y} года.")
    sig = {"worlds_silent": True}
    return t, sig, limit.isoformat()


TEXTS = {"volume_sign": t_volume_sign, "stress_sign": t_stress_sign, "capital_gap": t_capital_gap,
         "m_crisis_vs_cbr": t_m_crisis_vs_cbr, "growth_cut": t_growth_cut, "step_dividend": t_step_dividend,
         "nim_path_joint": t_nim_path_joint, "pb_by_world": t_pb_by_world}
# Подписи состава, на которых писались слова шаблона (книга 0.1, миры 1.4): другой состав — «просмотреть ведущему».
SIG_BOOK = {
    "volume_sign": {"falls": True, "crisis_down_everywhere": True, "most_from_crisis": True, "worlds_below_k": ["H", "M"],
                    "parts": ["crisis:adj", "crisis:override", "downturn:adj", "soft:adj"]},
    "stress_sign": {"loss_ok": True, "value_up": 0, "all_value_down": True, "scenarios": ["strict"]},
    "capital_gap": {"crisis_cells": 9, "other": ["M/downturn/strict"], "other_quarters": [1], "earliest_schedule": True,
                    "floors_2028": 2, "all_back": True},
    "m_crisis_vs_cbr": {"fails": ["рост кредита 2028 года"], "all_zero_2028": True, "common_stop": 2, "longer": ["mid", "strict"]},
    "growth_cut": {"worlds": ["M"], "cells": ["M/downturn/mid", "M/downturn/strict", "M/crisis/mid", "M/crisis/strict"],
                   "same_scenarios": True},
    "step_dividend": {"all_cut": True, "years": [2026, 2027], "same_dps_2026_2027": True, "pays_more_2028": True, "dps_2026": 0.35},
    "nim_path_joint": {"worlds": ["N"], "cells": ["N/downturn/schedule", "N/norm/mid", "N/norm/schedule", "N/norm/strict",
                                                  "N/soft/mid", "N/soft/schedule", "N/soft/strict"], "one_cap": True},
    "pb_by_world": {"worlds": ["M"], "regimes": ["crisis"], "below": True, "count": 3},
}


def wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=118, initial_indent="    ", subsequent_indent="    ", break_long_words=False,
                         break_on_hyphens=False)


def render(n: dict, current: str, book: dict) -> tuple[str, list[str]]:
    """Новый текст gate_explanations.yaml и флаги «просмотреть ведущему»."""
    flags = []
    old = yaml.safe_load(current) or {}
    first = re.search(r"^[a-z_]+:\n", current, flags=re.M).start()
    head = current[:first].rstrip("\n")
    version = n["book_version"]
    head = re.sub(r"^(# Письменные объяснения сработавших гейтов правдоподобия — книга Совкомбанка )[0-9.]+",
                  lambda m: m.group(1) + version, head, count=1)
    line = (f"# Книга {version}: объяснения сработавших гейтов — шаблоном ops/tools/gate_texts.py (суждение написано один раз, "
            "числа и перечни клеток — сеткой книги, массы — таблицами книги); состав гейта не тот, на котором писались слова "
            "шаблона, — флаг «просмотреть ведущему» в отчёте команды.")
    if line not in head:
        head += "\n#\n" + "\n".join(textwrap.wrap(line, width=124, subsequent_indent="# ", break_long_words=False))
    fired = n["results"]["gates"]
    default_until = min((str(v["valid_until"]) for k, v in old.items() if k != "manual_input_overdue"), default="2026-11-30")
    blocks, notes = [], {}
    for name in ORDER[:-1]:
        if name not in fired:
            if name in old:
                flags.append(f"гейт {name} больше не срабатывает — запись снята")
            continue
        if name not in TEXTS:
            flags.append(f"гейт {name} сработал, шаблона текста нет — запись прежняя, просмотреть ведущему")
            blocks.append((name, old[name]["explanation"], fired[name]["mass"], str(old[name]["valid_until"])))
            continue
        text, sig = TEXTS[name](n)
        if sig != SIG_BOOK.get(name):
            diff = {k: (SIG_BOOK.get(name, {}).get(k), v) for k, v in sig.items() if SIG_BOOK.get(name, {}).get(k) != v}
            flags.append(f"гейт {name}: состав не тот, на котором писались слова шаблона ({diff}) — текст собран правилом, "
                         "просмотреть ведущему")
        until = str(old[name]["valid_until"]) if name in old else default_until
        if name not in old:
            flags.append(f"гейт {name} сработал впервые — запись по шаблону, срок {until}; просмотреть ведущему")
        blocks.append((name, text, fired[name]["mass"], until))
        notes[name] = {"valid_until": until}
    for name in fired:
        if name not in ORDER:
            flags.append(f"гейт {name} сработал, шаблона текста нет — просмотреть ведущему")
    mtext, _, muntil = t_manual_input_overdue(book, notes)
    if mtext is None and "manual_input_overdue" in old:
        flags.append("manual_input_overdue: ближайший срок — миры (сработает раньше отчёта МСФО), правило текста не для этого "
                     "случая — запись прежняя, просмотреть ведущему")
        blocks.append(("manual_input_overdue", old["manual_input_overdue"]["explanation"],
                       old["manual_input_overdue"]["expected_mass"], str(old["manual_input_overdue"]["valid_until"])))
    elif mtext is not None:
        blocks.append(("manual_input_overdue", mtext, 1.0, muntil))
    out = [head, ""]
    for name, text, mass, until in blocks:
        m = round(float(mass), 3)
        out += [f"{name}:", "  explanation: >-"] + wrap(" ".join(text.split())) + \
               [f"  expected_mass: {m!r}", f"  valid_until: {until}"]
    return "\n".join(out) + "\n", flags


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--numbers", type=Path, help="готовые числа (JSON), иначе — счёт на книге дерева")
    ap.add_argument("--save-numbers", type=Path, help="записать посчитанные числа")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--flags", type=Path)
    a = ap.parse_args(argv)
    n = json.loads(a.numbers.read_text(encoding="utf-8")) if a.numbers else compute()
    if a.save_numbers:
        a.save_numbers.parent.mkdir(parents=True, exist_ok=True)
        a.save_numbers.write_text(json.dumps(n, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    if "results" not in n:
        print("ОТКАЗ: таблицы книги (results.json) другой версии — массы гейтов не с чего брать; сначала model.book_results")
        return 1
    book = yaml.safe_load((BOOK_DIR / "assumptions.yaml").read_text(encoding="utf-8"))
    text, flags = render(n, TARGET.read_text(encoding="utf-8"), book)
    if a.flags:
        a.flags.parent.mkdir(parents=True, exist_ok=True)
        a.flags.write_text(json.dumps(flags, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for f in flags:
        print("ФЛАГ:", f)
    if a.write:
        TARGET.write_text(text, encoding="utf-8", newline="\n")
        print(f"записано: {TARGET.relative_to(ROOT).as_posix()}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
