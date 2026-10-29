# -*- coding: utf-8 -*-
"""Бэктест книг ЧПД на наклонах ЯДРА (устав §5 1(б); решения ведущего № 11, Р11-1; проход ядра 9, notes/core-pass9/spec.yaml,
sheet.backtest) — лист приёмки команды перевывода (описание вывода, `ACCEPTANCE`).

Механика — бэктеста листа nii этапа 1 (stage1/calib-nii, backtest.py): ставка книги y_b,q = a_b EMA_ρb(ref_b)_q + c_b, ЧПМ
банка — проценты двенадцати книг (без книги страховых обязательств) плюс проценты вне книг минус взносы АСВ, к средним
процентным активам банка (act/365, полусумма концов; 1К2024 — без купленного «Хоум Кредита» 31.03.2024). Отличие от листа
этапа 1 (класс 4): тот судил СОВМЕСТНЫЙ ПОДБОР (a, ρ, c — подбором), а модель считает перенос своими наклонами. Здесь наклон
a_b каждой книги — наклон модели между мирами M и N на стационаре решённой передачи (функция ядра model.nii.book_slopes: 1 −
φ_A [Φ_A] − share_b у актива, β + φ_L dX/dref − share_b у пассива), ρ_b — книги, свободный член c_b — подбором при закреплённых
a и ρ (веса «центра» листа: ряд ставки книги и ЧПМ квартала с весом LAMBDA, координатный спуск), справочно — по ряду ставки
своей книги. Гейт приёмки §5 1(б): на каждом плече (L, W4, спуск, C) наибольшая ошибка ЧПМ модели не больше 0,3 п.п.

Входы — копии (inputs/stage1/calib/nii/backtest/, опись inputs/SOURCES.json): панель ставок листа nii, совместный подбор joint
и ряды опор кварталов окна. Печать «было → стало»: плечи совместного подбора листа этапа 1 (было) и наклонов ядра (стало).

Запуск (команда перевывода зовёт сама): python -B data/assumptions/evidence/nii/backtest_books.py --book КНИГА --facts КАТАЛОГ
--out ФАЙЛ; без --out — печать. Запись — {"rows": [{name, value, low, high, ok, words}], "numbers": {...}}.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs" / "stage1" / "calib" / "nii" / "backtest"
ASSETS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans", "securities", "liquidity")
LIABS = ("retail_current", "retail_term", "corp_term", "corp_current", "wholesale")
BOOKS = ASSETS + LIABS                    # двенадцать книг ЧПД банка (ЧПМ банка — без финрасходов страхования)
REF0 = "2022Q4"                           # стационарный старт EMA — опора квартала перед окном
LEGS = {"L": ("L (2023К1–К2, стационар 7,5 %)", ("2023Q1", "2023Q2")),
        "W4": ("W4 подъём (2023К3–2025К1)", ("2023Q3", "2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1")),
        "down": ("спуск (2025К2–2026К2)", ("2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")),
        "C": ("C (2025К4–2026К2)", ("2025Q4", "2026Q1", "2026Q2"))}
NORM = 0.003                              # гейт приёмки §5 1(б): наибольшая ошибка ЧПМ на плече — не больше 0,3 п.п.
LAMBDA = 6.0                              # вес ЧПМ квартала в подборе c («центр» листа nii этапа 1)
ROUNDS = 8                                # кругов координатного спуска по книгам
# покупка «Хоум Кредита» 31.03.2024 [лист nii этапа 1, nii_lib.ACQ_2024Q1]: проценты купленного в 1К2024 не входят
ACQ_2024Q1 = {"cash_loans": 177.0, "cards": 17.0, "mortgage": 7.0, "auto": 1.865, "liquidity": 3.342, "securities": 23.704,
              "retail_term": 130.0, "retail_current": 20.0, "corp_term": 8.531, "corp_current": 10.0, "wholesale": 7.552 + 6.213}
ACQ_BANK_IEA_2024Q1 = 202.865 + 3.342 + 23.704


def repo_root() -> Path:
    root = HERE
    while not (root / "model" / "book.py").exists():
        root = root.parent
    return root


def prev_q(p: str) -> str:
    y, q = int(p[:4]), int(p[-1])
    return f"{y - 1}Q4" if q == 1 else f"{y}Q{q - 1}"


def qdays(p: str) -> int:
    y, q = int(p[:4]), int(p[-1])
    return {1: 91 if y % 4 == 0 else 90, 2: 91, 3: 92, 4: 92}[q]


def ema(ref: list[float], ref0: float, rho: float) -> list[float]:
    x, out = ref0, []
    for r in ref:
        x = x + rho * (r - x)
        out.append(x)
    return out


class Panel:
    """Панель окна: опоры, наблюдённые ставки, средние остатки, ЧПМ МСФО кварталов."""

    def __init__(self) -> None:
        data = json.loads((INPUTS / "panel_backtest.json").read_text(encoding="utf-8"))
        joint = json.loads((INPUTS / "backtest_joint.json").read_text(encoding="utf-8"))
        rates = {r["quarter"]: r for r in csv.DictReader((INPUTS / "ref_rates_quarterly.csv").open(encoding="utf-8"))}
        self.q = list(data["quarters"])
        self.joint, self.refs = joint["joint"], joint["ref"]
        # выход листа этапа 1 (сверка механики): плечи совместного подбора, ЧПМ модели joint и факта по кварталам окна
        self.stage1 = {k: joint[k] for k in ("legs_joint", "nim_model_joint", "nim_actual_bank")}
        rows, bal = data["rows"], data["balances"]

        def ref_of(name: str, p: str) -> float:
            return float(rates[p]["key_pct" if name == "key" else f"{name}_pct"]) / 100

        def eff_avg(p: str, b: str) -> float:
            c = bal[p][b] - (ACQ_2024Q1.get(b, 0.0) if p == "2024Q1" else 0.0)
            return (bal[prev_q(p)][b] + c) / 2

        self.ref = {b: [ref_of(self.refs[b], p) for p in self.q] for b in BOOKS}
        self.ref0 = {b: ref_of(self.refs[b], REF0) for b in BOOKS}
        self.avg = {b: [eff_avg(p, b) for p in self.q] for b in BOOKS}
        self.obs = {b: [rows[p][f"{b}_int"] / self.avg[b][i] * 365 / qdays(p) for i, p in enumerate(self.q)] for b in BOOKS}
        iea = [(bal[prev_q(p)]["iea_bank"] + bal[p]["iea_bank"] - (ACQ_BANK_IEA_2024Q1 if p == "2024Q1" else 0.0)) / 2
               for p in self.q]
        self.iea, self.days = iea, [qdays(p) for p in self.q]
        self.other = [-rows[p]["dia"] + rows[p]["outside_net"] for p in self.q]
        self.nim = [rows[p]["nii_ifrs"] * 4 / iea[i] for i, p in enumerate(self.q)]
        self.sign = {b: 1.0 if b in ASSETS else -1.0 for b in BOOKS}
        self.k = {b: [self.avg[b][i] * self.days[i] / 365 * 4 / iea[i] for i in range(len(self.q))] for b in BOOKS}
        self.kbar = {b: sum(self.k[b]) / len(self.q) for b in BOOKS}

    def nim_model(self, params: dict) -> list[float]:
        out = []
        for i in range(len(self.q)):
            nii = self.other[i]
            for b in BOOKS:
                x = ema(self.ref[b], self.ref0[b], params[b]["rho"])[i]
                nii += self.sign[b] * (params[b]["a"] * x + params[b]["c"]) * self.avg[b][i] * self.days[i] / 365
            out.append(nii * 4 / self.iea[i])
        return out

    def legs(self, nim: list[float]) -> dict:
        out = {}
        for key, (_, ps) in list(LEGS.items()) + [("all", ("все 14", tuple(self.q)))]:
            e = [nim[self.q.index(p)] - self.nim[self.q.index(p)] for p in ps]
            out[key] = {"rmse": math.sqrt(sum(x * x for x in e) / len(e)), "max_abs": max(abs(x) for x in e),
                        "mean": sum(e) / len(e)}
        return out

    def fit_c(self, a: dict, rho: dict, own: bool = False) -> dict:
        """Свободный член c при закреплённых a, ρ: веса «центра» листа nii (ряд ставки книги и ЧПМ квартала, LAMBDA),
        координатный спуск по книгам; `own` — только по ряду ставки своей книги."""
        params = {b: {"a": a[b], "rho": rho[b], "c": float(self.joint[b]["c"])} for b in BOOKS}
        n = len(self.q)
        for b in BOOKS if own else ():
            xs = ema(self.ref[b], self.ref0[b], rho[b])
            params[b]["c"] = sum(self.obs[b][i] - a[b] * xs[i] for i in range(n)) / n
        for _ in range(0 if own else ROUNDS):
            for b in BOOKS:
                base = self.nim_model({k: (v if k != b else {"rho": 1.0, "a": 0.0, "c": 0.0}) for k, v in params.items()})
                xs = ema(self.ref[b], self.ref0[b], rho[b])
                num = den = 0.0
                for i in range(n):
                    w1, w2 = self.kbar[b] ** 2, LAMBDA * self.k[b][i] ** 2
                    t2 = self.sign[b] * (self.nim[i] - base[i]) / self.k[b][i]
                    num += w1 * (self.obs[b][i] - a[b] * xs[i]) + w2 * (t2 - a[b] * xs[i])
                    den += w1 + w2
                params[b]["c"] = num / den
        for b in BOOKS:
            xs = ema(self.ref[b], self.ref0[b], rho[b])
            params[b]["rmse_rate"] = math.sqrt(sum((a[b] * xs[i] + params[b]["c"] - self.obs[b][i]) ** 2 for i in range(n)) / n)
        return params


def pp(x: float, nd: int = 3) -> str:
    return f"{100 * x:.{nd}f}".replace(".", ",")


def model_slopes(book, facts) -> tuple[dict, dict, dict]:
    """Наклоны книг ядра (model.nii.book_slopes) на решённой передаче книги, ρ книг и параметры передачи."""
    from model.credit import bridge_from_facts
    from model.nii import book_slopes, phi_shares, solve_transmission
    tr = solve_transmission(book, facts, bridge_from_facts(facts))
    slopes = book_slopes(book, facts, tr)
    books = book.get("nii.books")
    return ({b: float(slopes[b]) for b in BOOKS}, {b: float(books[b]["rho"]) for b in BOOKS},
            {"phi": tr.phi, "phi_assets": tr.phi_assets, "phi_liab": tr.phi_liab, "phi_share": phi_shares(books)})


def backtest(book, facts) -> dict:
    """Записи листа: плечи совместного подбора (было) и наклонов ядра с c подбором (стало) и по ряду книги (справочно)."""
    panel = Panel()
    a, rho, tr = model_slopes(book, facts)
    joint = {b: {k: float(panel.joint[b][k]) for k in ("a", "rho", "c")} for b in BOOKS}
    fit, own = panel.fit_c(a, rho), panel.fit_c(a, rho, own=True)
    return {"legs_joint": panel.legs(panel.nim_model(joint)), "legs": panel.legs(panel.nim_model(fit)),
            "legs_own_intercept": panel.legs(panel.nim_model(own)), "slope_model": a, "slope_joint": {b: joint[b]["a"] for b in BOOKS},
            "rho": rho, "c_fit": {b: fit[b]["c"] for b in BOOKS}, "rmse_rate_fit": {b: fit[b]["rmse_rate"] for b in BOOKS},
            "rmse_rate_own": {b: own[b]["rmse_rate"] for b in BOOKS}, "transmission": tr, "norm": NORM}


def rows_of(res: dict) -> list[dict]:
    rows = []
    for key, (title, _) in LEGS.items():
        now, was, own = res["legs"][key], res["legs_joint"][key], res["legs_own_intercept"][key]
        rows.append({"name": f"бэктест книг на наклонах ядра (§5 1(б)): плечо {title} — наибольшая ошибка ЧПМ",
                     "value": now["max_abs"], "low": 0.0, "high": NORM, "ok": now["max_abs"] <= NORM,
                     "words": f"{pp(now['max_abs'])} п.п. (среднее {pp(now['mean'])}, RMSE {pp(now['rmse'])}) при норме "
                              f"{pp(NORM, 1)} п.п.; было — совместный подбор листа nii {pp(was['max_abs'])} п.п.; справочно c по "
                              f"ряду книги {pp(own['max_abs'])} п.п."})
    off = {b: (res["slope_model"][b], res["slope_joint"][b]) for b in BOOKS}
    rows.append({"name": "наклоны книг к опоре между мирами: ядро против совместного подбора (справочно)",
                 "value": max(abs(m - j) for m, j in off.values()), "low": None, "high": None, "ok": True,
                 "words": "; ".join(f"{b} {m:.4f} / {j:.4f}" for b, (m, j) in off.items())})
    return rows


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="бэктест книг ЧПД на наклонах ядра (устав §5 1(б))")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--facts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(repo_root()))
    from model.book import load_book, load_facts
    facts = load_facts(a.facts)
    book = load_book(a.book, facts=facts)
    res = backtest(book, facts)
    rows = rows_of(res)
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"rows": rows, "numbers": res}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tr = res["transmission"]
    print(f"передача: φ {tr['phi']:.4f}, φ_A {tr['phi_assets']:.4f}, φ_L {tr['phi_liab']:.4f}; доли сжатия книг "
          + (", ".join(f"{b} {v:g}" for b, v in tr["phi_share"].items()) or "нет"))
    print("плечо                               было (совм. подбор)   стало (наклоны ядра)   c по ряду книги")
    for key, (title, _) in list(LEGS.items()) + [("all", ("все 14", ()))]:
        w, n, o = res["legs_joint"][key], res["legs"][key], res["legs_own_intercept"][key]
        print(f"  {title:34s} max {pp(w['max_abs'])} → max {pp(n['max_abs'])} (RMSE {pp(n['rmse'])})   max {pp(o['max_abs'])} п.п.")
    print("наклоны ядро / совместный подбор: " + ", ".join(
        f"{b} {res['slope_model'][b]:.3f}/{res['slope_joint'][b]:.3f}" for b in BOOKS))
    for r in rows:
        print(("ок  " if r["ok"] else "НЕТ ") + r["name"] + ": " + r["words"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
