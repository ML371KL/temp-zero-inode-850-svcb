# -*- coding: utf-8 -*-
"""Бэктест ПУТИ МАРЖИ (устав §5 1(б) в редакции решений ведущего № 12, Р12-5; поток book12) — лист приёмки команды перевывода
(описание вывода, `ACCEPTANCE`). Рядом — прежний бэктест книг (backtest_books.py, решения № 11, Р11-1): его механика и панель
берутся без правок, его плечи печатаются справочно.

Две проверки, норма — ошибка квартала ЧПМ банка не больше 0,3 п.п. на каждом из плеч L, W4, спуск, C:
  (i)  совместный подбор книг листа nii этапа 1 (stage1/calib-nii, backtest.py: a, ρ, c каждой книги — подбором): плечи записи
       листа этапа 1, пересчитанные механикой панели (сверка с записью листа — печать);
  (ii) путь ЧПМ банка В МОДЕЛИ, определение «c подбором» (лист решения № 12, С-2): ставки двенадцати книг на наклонах ядра между
       мирами (model.nii.book_slopes на решённой передаче книги) и лагах ядра (ρ книг), веса — остатки фактов (средние остатки
       книг панели, act/365), по фактической ключевой (опоры книг) 2023К1–2026К2; свободный член книги (уровень) ПОДБИРАЕТСЯ на
       окне (механика бэктеста книг backtest_books.py, веса «центра» листа nii): уровень судит §5 1(а), а 1(б) судит путь.
       Проценты вне книг и взносы АСВ — факты кварталов.
Справочно (печать, не приёмка): (ii) «старт от якоря» — тот же путь, свободный член от ставки книги в квартале якоря (2026К2 —
факт панели; c_b = ставка якоря − a_b × EMA якоря, подбора на окне нет); c по ряду своей книги; наклоны ядра против совместного
подбора.

Запуск (команда перевывода зовёт сама): python -B data/assumptions/evidence/nii/backtest_path.py --book КНИГА --facts КАТАЛОГ
--out ФАЙЛ; без --out — печать. Запись — {"rows": [{name, value, low, high, ok, words}], "numbers": {...}}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import backtest_books as BB  # noqa: E402

LEGS, NORM, BOOKS, pp = BB.LEGS, BB.NORM, BB.BOOKS, BB.pp
ANCHOR_Q = "2026Q2"                      # квартал якоря модели (МСФО 6М2026) — последний квартал панели
# Решения ведущего № 12, раздел И, Р12-5а; лист решения № 12, С-1 и С-2: центр передачи −0,06 остаётся (регрессии на составе
# якоря и пары кварталов — прямые свидетельства на этой величине). Ошибка (ii) убывает к верху оси на всех плечах, но внутри оси
# не проходит нигде; проходит она только около +0,09…+0,12 — это стационарный наклон совместного подбора, который путь 2023–2026
# не определяет. Удержание −0,06 требует стационарных наклонов срочных средств 1,11–1,13 — названное свойство решателя.
# Отклонение печатается с ЦЕНОЙ развилки «передача на верху оси (+0,03 опр. банка)» и плечами (ii) на ней (законно по PLAYBOOK
# §2 (б)); рядом — развилка «середина трёх прочтений (−0,06; −0,052; ≈ +0,10) −0,025». Числа — итоговой книги круга 12
# (a148cf8): сухой перевывод развилок trtop (коридор оси передачи ±0,20 — Р12-8а; граница ROE развилки 15,92 %: окно оси НДУ
# 2П2025 выпадает — ось НДУ книги, пометка Р12-8а) и trmid, общие случайные числа круга 4, 600 прогонов. Плечи — (ii) c подбором
# (С-2) и справочно «старт от якоря»; на верху оси Φ_A = совместному подбору (0,2024).
TOP_OF_AXIS = {"book": "a148cf8", "price_point": 6.2302, "price_median": 4.5825, "price_own": 4.69,
               "worlds": {"N": 0.2437, "H": 2.5931, "M": 9.34},
               "legs_path": {"L": 0.00654, "W4": 0.00519, "down": 0.00415, "C": 0.00221},
               "legs_c_fit": {"L": 0.0054, "W4": 0.00361, "down": 0.00257, "C": 0.00157},
               "phi_assets": 0.2024, "phi_liab": 0.0785}
# Лист решения № 12, С-1: развилка «середина трёх прочтений» — передача −0,025 опр. банка (−0,06 центр; −0,052 пары кварталов;
# ≈ +0,10 стационарный наклон подбора), сухой перевывод на итоговой книге (медленный круг, var/rel/r12s/forks_s1.json; граница
# ROE развилки 14,95 %, отбор окон не меняется; φ 0,48 на границе области гейтов).
MID_OF_READINGS = {"book": "a148cf8", "target": -0.025, "price_point": 2.3263, "price_median": 1.7025, "price_own": 1.7575,
                   "worlds": {"N": 0.0779, "H": 1.0261, "M": 3.4697},
                   "legs_path": {"L": 0.01072, "W4": 0.00856, "down": 0.00616, "C": 0.00341},
                   "legs_c_fit": {"L": 0.00829, "W4": 0.00616, "down": 0.00378, "C": 0.00204},
                   "phi_assets": 0.2029, "phi_liab": 0.1391}


def model_path(panel: BB.Panel, a: dict, rho: dict) -> tuple[list[float], dict]:
    """Путь ЧПМ банка в модели: ставка книги = a_b × EMA_ρb(опоры) + c_b, c_b — от ставки книги в квартале якоря (факт панели)."""
    i0 = panel.q.index(ANCHOR_Q)
    params = {}
    for b in BOOKS:
        xs = BB.ema(panel.ref[b], panel.ref0[b], rho[b])
        params[b] = {"a": a[b], "rho": rho[b], "c": panel.obs[b][i0] - a[b] * xs[i0]}
    return panel.nim_model(params), params


def backtest_path(book, facts) -> dict:
    panel = BB.Panel()
    a, rho, tr = BB.model_slopes(book, facts)
    joint = {b: {k: float(panel.joint[b][k]) for k in ("a", "rho", "c")} for b in BOOKS}
    nim_joint = panel.nim_model(joint)
    nim_path, params = model_path(panel, a, rho)
    old = BB.backtest(book, facts)                       # прежний бэктест книг (c подбором) — справочно
    stage1 = {k: float(v["max_abs_pp"]) / 100 for k, v in (panel.stage1.get("legs_joint") or {}).items()}   # запись листа этапа 1
    return {"legs_joint": panel.legs(nim_joint), "legs_path": panel.legs(nim_path), "legs_old": old["legs"],
            "legs_old_own": old["legs_own_intercept"], "stage1_legs_joint": stage1,
            "nim_actual": dict(zip(panel.q, panel.nim)), "nim_path": dict(zip(panel.q, nim_path)),
            "nim_joint": dict(zip(panel.q, nim_joint)), "slope_model": a, "slope_joint": {b: joint[b]["a"] for b in BOOKS},
            "rho": rho, "c_path": {b: params[b]["c"] for b in BOOKS}, "transmission": tr, "norm": NORM, "anchor": ANCHOR_Q}


def rub(x: float) -> str:
    return f"{x:+.2f}".replace(".", ",")


def num(x: float, nd: int) -> str:
    """Число со знаком для печати словами: запятая и минус-тире (−0,025)."""
    return f"{x:+.{nd}f}".replace(".", ",").replace("-", "−")


def rows_of(res: dict) -> list[dict]:
    rows = []
    for key, (title, _) in LEGS.items():
        j = res["legs_joint"][key]
        rows.append({"name": f"бэктест пути маржи (§5 1(б), Р12-5) (i): совместный подбор книг листа этапа 1 — плечо {title}",
                     "value": j["max_abs"], "low": 0.0, "high": NORM, "ok": j["max_abs"] <= NORM,
                     "words": f"{pp(j['max_abs'])} п.п. (среднее {pp(j['mean'])}, RMSE {pp(j['rmse'])}) при норме {pp(NORM, 1)} п.п."})
    for key, (title, _) in LEGS.items():
        n, a0 = res["legs_old"][key], res["legs_path"][key]       # (ii) — «c подбором» (лист решения № 12, С-2); от якоря — справочно
        rows.append({"name": f"бэктест пути маржи (§5 1(б), Р12-5) (ii): путь ЧПМ банка в модели (наклоны и лаги ядра, остатки фактов, "
                             f"уровень — подбором на окне) — плечо {title}",
                     "value": n["max_abs"], "low": 0.0, "high": NORM, "ok": n["max_abs"] <= NORM,
                     "words": f"{pp(n['max_abs'])} п.п. (среднее {pp(n['mean'])}, RMSE {pp(n['rmse'])}) при норме {pp(NORM, 1)} п.п.; "
                              f"справочно старт от якоря {pp(a0['max_abs'])} п.п."
                              + ("" if n["max_abs"] <= NORM else
                                 f"; ОТКЛОНЕНИЕ С ЦЕНОЙ (PLAYBOOK §2 (б); решения № 12, Р12-5а; лист решения № 12, С-1): развилка "
                                 f"«передача на верху оси (+0,03)» {rub(TOP_OF_AXIS['price_point'])} / "
                                 f"{rub(TOP_OF_AXIS['price_median'])} ₽ (точка / медиана), плечо (ii) на ней "
                                 f"{pp(TOP_OF_AXIS['legs_c_fit'][key])} п.п. (от якоря {pp(TOP_OF_AXIS['legs_path'][key])}); "
                                 f"развилка «середина трёх прочтений ({num(MID_OF_READINGS['target'], 3)})» "
                                 f"{rub(MID_OF_READINGS['price_point'])} / {rub(MID_OF_READINGS['price_median'])} ₽, плечо (ii) на ней "
                                 f"{pp(MID_OF_READINGS['legs_c_fit'][key])} п.п.; центр −0,06 — регрессии и пары кварталов")})
    off = {b: (res["slope_model"][b], res["slope_joint"][b]) for b in BOOKS}
    rows.append({"name": "наклоны книг к опоре между мирами: ядро против совместного подбора (справочно; распределение передачи "
                         "решателем — связь устава §8, Р12-5, не предмет проверки)",
                 "value": max(abs(m - j) for m, j in off.values()), "low": None, "high": None, "ok": True,
                 "words": "; ".join(f"{b} {m:.4f} / {j:.4f}" for b, (m, j) in off.items())})
    return rows


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="бэктест пути маржи (устав §5 1(б), решения № 12, Р12-5)")
    ap.add_argument("--book", type=Path, default=None)
    ap.add_argument("--facts", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(BB.repo_root()))
    from model.book import load_book, load_facts
    facts = load_facts(a.facts)
    book = load_book(a.book, facts=facts)
    res = backtest_path(book, facts)
    rows = rows_of(res)
    if a.out is not None:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"rows": rows, "numbers": res}, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    tr = res["transmission"]
    print(f"передача: φ {tr['phi']:.4f}, φ_A {tr['phi_assets']:.4f}, φ_L {tr['phi_liab']:.4f}")
    print("плечо                               (i) совм. подбор   (ii) путь модели, c подбором   справочно: старт от якоря / c по ряду книги")
    for key, (title, _) in list(LEGS.items()) + [("all", ("все 14", ()))]:
        j, n, a0, w = res["legs_joint"][key], res["legs_old"][key], res["legs_path"][key], res["legs_old_own"][key]
        print(f"  {title:34s} max {pp(j['max_abs'])}        max {pp(n['max_abs'])} (ср. {pp(n['mean'])})               "
              f"{pp(a0['max_abs'])} / {pp(w['max_abs'])} п.п.")
    print("(i) сверка механики: запись листа этапа 1 — " + "; ".join(f"{k} {pp(v)}" for k, v in (res["stage1_legs_joint"] or {}).items()))
    print("ЧПМ по кварталам, факт / (ii) от якоря (справочно) / (i): " + "; ".join(
        f"{q} {100 * res['nim_actual'][q]:.2f}/{100 * res['nim_path'][q]:.2f}/{100 * res['nim_joint'][q]:.2f}" for q in res["nim_actual"]))
    for r in rows:
        print(("ок  " if r["ok"] else "НЕТ ") + r["name"] + ": " + r["words"])
    print(f"Р12-5а: цена развилки «передача на верху оси (+0,03)» на книге {TOP_OF_AXIS['book']}: {TOP_OF_AXIS['price_point']:+.4f} / "
          f"{TOP_OF_AXIS['price_median']:+.4f} ₽ (своя выборка {TOP_OF_AXIS['price_own']:+.4f}); миры "
          + " / ".join(f"{w} {v:+.2f}" for w, v in TOP_OF_AXIS["worlds"].items())
          + "; плечи (ii) на ней: " + " / ".join(f"{LEGS[k][0].split()[0]} {pp(v)}" for k, v in TOP_OF_AXIS["legs_c_fit"].items())
          + " (от якоря " + " / ".join(pp(v) for v in TOP_OF_AXIS["legs_path"].values()) + f") п.п.; Φ_A {TOP_OF_AXIS['phi_assets']}")
    print(f"С-1: цена развилки «середина трёх прочтений ({num(MID_OF_READINGS['target'], 3)})» на книге {MID_OF_READINGS['book']}: "
          f"{MID_OF_READINGS['price_point']:+.4f} / {MID_OF_READINGS['price_median']:+.4f} ₽ (своя выборка "
          f"{MID_OF_READINGS['price_own']:+.4f}); миры " + " / ".join(f"{w} {v:+.2f}" for w, v in MID_OF_READINGS["worlds"].items())
          + "; плечи (ii) на ней: " + " / ".join(f"{LEGS[k][0].split()[0]} {pp(v)}" for k, v in MID_OF_READINGS["legs_c_fit"].items())
          + " (от якоря " + " / ".join(pp(v) for v in MID_OF_READINGS["legs_path"].values()) + ") п.п.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
