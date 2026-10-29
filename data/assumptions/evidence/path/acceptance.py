# -*- coding: utf-8 -*-
"""Приёмочные проверки книги Совкомбанка, которых нет в блоке команды перевывода (описание вывода, `ACCEPTANCE`):
мерки маржи в условиях своих окон и в определении банка, сверка порядка на одном делителе (решения ведущего № 2, А5, А6).

Мерки (решения ведущего № 2, А5):
  * мир N — с окном L: стационарная маржа мира N на составе якоря в опр. банка — 7,13–7,21 % (кварталы окна L, перенесённые
    книгами бэктеста, решения № 1, п. 1); путь клеток мира N 2030–2036 печатается рядом справочно (состав клеток);
  * слой «рыночные ставки как есть» (мир M) — с окном R (кварталы 2024К2–2026К2 опр. банка из фактов mgmt_quarterly.nim_exact)
    и со стационаром мира M на составе якоря (решатель передачи, опр. банка); доля кредитов в процентных активах — рядом;
  * печать маржи — в опр. банка ТОЧНЫМ мостом: ЧПМ банка = (ЧПД движка + финрасходы страхования) / (ПА движка × R), где
    финрасходы — проценты книги страховых обязательств клеток, R — отношение ПА банка к ПА движка на якоре (как шаг bridge
    листа вывода); ключ ядра («ЧПМ упр.» ядра = движок / b) — другая величина (N +0,13, M −0,19 п.п.);
  * стоимость риска окна — одно определение: резервы / средние валовые кредиты (факты mgmt_quarterly.cor_exact).
Сверка порядка (А6): P/B и P/E точки и рынка — на одном делителе, акциях в обращении на дату фактов (22 431,1 млн): справедливый
P/B на акцию = точка × N_out / BV; P/E = цена / (прибыль акционеров года / N_out). Ядро (`grid.bank_language`) печатает
V0 / BV — капитал на делителе после пути выкупа (19 560 млн) против рынка на 22 431: это печать ядра, не этого листа.

Запуск (команда перевывода зовёт сама): python -B data/assumptions/evidence/path/acceptance.py --book КНИГА --facts КАТАЛОГ --out ФАЙЛ
Запись — {"rows": [{name, value, low, high, ok, words}], "numbers": {...}}; в свой каталог лист не пишет.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_L_BANK = (0.0713, 0.0721)        # кварталы окна L на составе якоря, опр. банка [решения № 1, п. 1; лист nii, бэктест книг]
R_WINDOW = ("2024Q2", "2026Q2")          # окно R [устав §1]
INS_BOOK = "insurance_liab"


def repo_root() -> Path:
    root = HERE
    while not (root / "model" / "book.py").exists():
        root = root.parent
    return root


def pct(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else f"{100 * x:.{nd}f}".replace(".", ",") + " %"


def num(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else f"{x:.{nd}f}".replace(".", ",")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--facts", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    root = repo_root()
    sys.path.insert(0, str(root))
    from model.book import load_book, load_facts
    from model.grid import bank_language, run_grid
    from model.levels import _Mix, mix_year, point_probabilities  # noqa: PLC2701
    from model.live import live_from_book

    facts = load_facts(a.facts)
    book = load_book(a.book, facts=facts)
    live = live_from_book(book, facts)
    run = run_grid(book, facts, live)
    tl = run.ctx.timeline
    cfg = book.opt("checks.window_backtest") or {}
    first = int(cfg.get("from_year", 2030))
    years = [y for y in range(first, tl.last_year + 1)]

    # мост опр. банка ↔ движок на якоре (шаг bridge листа вывода)
    hist = facts.file("bridge_mgmt_ifrs")["nim"]["history"]
    days = float(facts.need("nii_books", "days")) if facts.has("nii_books", "days") else 91.0
    r_iea = float(hist[-1]["gap_iea_x4"]["v"]) * 365.0 / (4.0 * days)
    l_ins = float(facts.need("balance", "insurance.contract_liabilities")) / float(facts.need("balance", "iea"))
    spec = book.get(f"nii.books.{INS_BOOK}")
    beta, c_lt = float(spec["beta"]), float(spec["spread"]["LT"])
    key_lt = {w: float(book.get(f"worlds.{w}.key_rate")[max(book.get(f"worlds.{w}.key_rate"))]) for w in book.get("worlds.ids")}
    nss = run.ctx.transmission.nss
    stat_bank = {w: (float(v) + (beta * key_lt[w] + c_lt) * l_ins) / r_iea for w, v in nss.items()}

    def ins_interest(prob: dict, year: int) -> float:
        total = 0.0
        for c in run.cells:
            w = prob.get(c.key, 0.0)
            if not w:
                continue
            ib = c.books[INS_BOOK]
            total += w * sum(float(ib["rate"][q]) * float(ib["avg"][q]) * tl.d(q) / 365.0
                             for q in tl.quarters_of_year(year) if 1 <= q <= tl.Q)
        return total

    def bank_nim(prob: dict) -> tuple[float, float, list[float]]:
        """Средние лет участка: ЧПМ опр. банка точным мостом, ЧПМ ключа ядра, доля кредитов в ПА (по годам)."""
        vals, keys, shares = [], [], []
        for y in years:
            row = mix_year(run, prob, y)
            vals.append((row["flows"]["nii"] + ins_interest(prob, y)) / (row["avg_iea"] * r_iea))
            keys.append(row["mgmt"]["nim"])
            shares.append(row["loans_share"])
        return sum(vals) / len(vals), sum(keys) / len(keys), shares

    def mix_cor(prob: dict) -> float:
        vals = [mix_year(run, prob, y)["mgmt"]["cor"] for y in years]
        return sum(vals) / len(vals)

    layer_m = dict(run.layers["macro_neutral"].prob)
    own = dict(run.layers["analytical"].prob)
    in_n = {k: v for k, v in own.items() if k[0] == "N"}
    tot_n = sum(in_n.values())
    world_n = {k: (v / tot_n if k[0] == "N" else 0.0) for k, v in own.items()}
    m_bank, m_key, m_share = bank_nim(layer_m)
    n_bank, n_key, n_share = bank_nim(world_n)

    def roll4_mean(vals: list) -> float:          # «среднее окна» — равный вес календарных кварталов (решения ведущего № 6, Р6-2)
        roll = [sum(vals[i:i + 4]) / 4 for i in range(len(vals) - 3)]
        return sum(roll) / len(roll)

    q = facts.file("mgmt_quarterly")["quarters"]
    win = [p for p in sorted(q) if R_WINDOW[0] <= p <= R_WINDOW[1]]
    r_nim = [float(q[p]["nim_exact"]["v"]) for p in win]
    r_cor = [float(q[p]["cor_exact"]["v"]) for p in win]
    bh = facts.file("balance")["history"]
    ends = sorted(bh)

    def avg_share(p: str) -> float | None:
        i = ends.index(p) if p in ends else None
        if i is None or i == 0:
            return None
        lo_, hi_ = bh[ends[i - 1]], bh[p]
        return ((lo_["loans"]["v"] + hi_["loans"]["v"]) / 2, (lo_["iea"]["v"] + hi_["iea"]["v"]) / 2)

    pairs = [avg_share(p) for p in win]
    pairs = [x for x in pairs if x is not None]
    r_share = sum(x[0] for x in pairs) / sum(x[1] for x in pairs)
    anchor_share = float(run.cells[0].quarters["loans"][0]) / float(run.cells[0].quarters["iea"][0])
    m_cor = mix_cor(layer_m)

    rows = []
    rows.append({"name": "мир N (окно L): стационарная ЧПМ на составе якоря, опр. банка", "value": stat_bank["N"],
                 "low": WINDOW_L_BANK[0], "high": WINDOW_L_BANK[1],
                 "ok": WINDOW_L_BANK[0] - 5e-5 <= stat_bank["N"] <= WINDOW_L_BANK[1] + 5e-5,
                 "words": f"{pct(stat_bank['N'])} при окне L {pct(WINDOW_L_BANK[0])}–{pct(WINDOW_L_BANK[1])} (кварталы окна на составе "
                          f"якоря); стационары опр. банка N / H / M — {pct(stat_bank['N'])} / {pct(stat_bank['H'])} / {pct(stat_bank['M'])}"})
    rows.append({"name": f"мир N: путь клеток {years[0]}–{years[-1]}, опр. банка (справочно)", "value": n_bank,
                 "low": WINDOW_L_BANK[0], "high": WINDOW_L_BANK[1], "ok": True,
                 "words": f"справочно: ожидание клеток мира N {pct(n_bank)} опр. банка (ключ ядра {pct(n_key)}) против окна L "
                          f"{pct(WINDOW_L_BANK[0])}–{pct(WINDOW_L_BANK[1])} на составе якоря; доля кредитов в ПА клеток "
                          f"{pct(n_share[0], 1)} → {pct(n_share[-1], 1)} против {pct(anchor_share, 1)} якоря — отклонение пути — состав"})
    rows.append({"name": f"слой «рыночные ставки как есть» (окно R): ЧПМ {years[0]}–{years[-1]}, опр. банка точным мостом", "value": m_bank,
                 "low": min(r_nim), "high": max(r_nim), "ok": min(r_nim) <= m_bank <= max(r_nim),
                 "words": f"{pct(m_bank)} опр. банка (ключ ядра {pct(m_key)}) при окне R {pct(min(r_nim))}–{pct(max(r_nim))} "
                          f"(среднее {pct(roll4_mean(r_nim))} — скользящих 4 кварталов, Р6-2; mgmt_quarterly.nim_exact)"})
    rows.append({"name": "слой «рыночные ставки как есть» против стационара мира M на составе якоря (справочно)", "value": m_bank - stat_bank["M"],
                 "low": None, "high": None, "ok": True,
                 "words": f"справочно: {pct(m_bank)} против стационара M {pct(stat_bank['M'])} опр. банка — {f"{100 * (m_bank - stat_bank['M']):+.2f}".replace(".", ",").replace("-", "−")} п.п.; "
                          f"доля кредитов в ПА слоя {pct(sum(m_share) / len(m_share), 1)} против {pct(anchor_share, 1)} якоря и "
                          f"{pct(r_share, 1)} окна R — разрыв состава (средства клиентов растут с М2 мира, кредиты урезаны капиталом)"})
    rows.append({"name": f"слой «рыночные ставки как есть» (окно R): CoR {years[0]}–{years[-1]}, одно определение", "value": m_cor,
                 "low": min(r_cor), "high": max(r_cor), "ok": min(r_cor) <= m_cor <= max(r_cor),
                 "words": f"{pct(m_cor)} при окне R {pct(min(r_cor))}–{pct(max(r_cor))} (среднее {pct(roll4_mean(r_cor))} — скользящих 4 кварталов, Р6-2; "
                          f"резервы / средние валовые кредиты, mgmt_quarterly.cor_exact)"})
    # сверка порядка на одном делителе (А6)
    bank = bank_language(run)
    n_out = float(run.ctx.prep.af.n_out)
    market = float(live.prices[str(book.get("meta.company.main_ticker"))])
    bv = float(bank["bv_v"])
    fair_pb = run.point * n_out / 1000.0 / bv
    market_pb = market * n_out / 1000.0 / bv
    rows.append({"name": "сверка порядка: P/B точки и рынка на акциях в обращении", "value": fair_pb, "low": None, "high": None, "ok": True,
                 "words": f"P/B точки {num(fair_pb)} при рыночном {num(market_pb)} — оба на {num(n_out, 1)} млн акций в обращении "
                          f"(печать ядра V0 / BV {num(bank['fair_pb_point'])} — на делителе после пути выкупа {num(run.divisor, 1)} млн)"})
    pp = point_probabilities(run)
    pe = {}
    for y in (tl.anchor_year, tl.anchor_year + 1):
        ni = mix_year(run, pp, y)["flows"]["ni_sh"]
        eps = ni * 1000.0 / n_out
        pe[str(y)] = {"eps": eps, "pe_point": run.point / eps, "pe_market": market / eps}
        rows.append({"name": f"сверка порядка: P/E на прибыль {y} года на акциях в обращении", "value": run.point / eps,
                     "low": None, "high": None, "ok": True,
                     "words": f"P/E точки {num(run.point / eps, 1)}, рынка {num(market / eps, 1)}; прибыль на акцию {num(eps)} ₽ "
                              f"на {num(n_out, 1)} млн акций (обе стороны на одном делителе)"})
    out = {"rows": rows, "numbers": {"stationary_bank": stat_bank, "r_iea": r_iea, "l_ins": l_ins, "layer_m_bank": m_bank,
                                     "layer_m_key": m_key, "world_n_bank": n_bank, "world_n_key": n_key,
                                     "loans_share_layer_m": m_share, "loans_share_world_n": n_share, "loans_share_anchor": anchor_share,
                                     "loans_share_window_r": r_share, "window_r_nim": [min(r_nim), max(r_nim), sum(r_nim) / len(r_nim)],
                                     "window_r_cor": [min(r_cor), max(r_cor), sum(r_cor) / len(r_cor)], "layer_m_cor": m_cor,
                                     "fair_pb_out": fair_pb, "market_pb_out": market_pb, "fair_pb_core": bank["fair_pb_point"],
                                     "n_out": n_out, "divisor": run.divisor, "pe": pe}}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(("ок  " if r["ok"] else "НЕТ ") + r["name"] + ": " + r["words"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
