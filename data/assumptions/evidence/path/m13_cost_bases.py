# -*- coding: utf-8 -*-
"""Себестоимость рубля книг по сегментам МСФО (М13; решения ведущего № 3, Р1 и Р11): расходы сегментов (персонал + прочие)
на пять баз — кредиты розницы, корпоративный кредит, бумаги и ликвидность, средства клиентов (сегмента — его средства),
франшиза комиссий — по годам, с диапазонами; веса книг к корпоративному кредиту (= 1), центры (середины) и оси.
Лист скептика sk3-cost (круг 3; итог скептика ПОДТВЕРЖДЁН — решения ведущего № 3, Р1): ключей книги не пишет; центр весов
книги (opex.volume_weights) — середина окон схемы «середина» с франшизой комиссий за драйвером комиссий (кредиты —
volumes.link_base: loans, Р2): kernel_weights["mid/loans"]; ось-связка — концы «только кредиты» и «баланс» той же франшизы
(kernel_weights["loans/loans"], ["balance/loans"]), ось веса бумаг и ликвидности — min…max окон центра. Перенесён в книгу
потоком book3 (коммит скептика b130477, _wt/sk3-cost).

Входы (inputs/): m13_segment_pnl.csv — строки ОПУ сегментов (млн ₽, расходы положительными); m13_segment_balances.csv —
остатки сегментов на концы кварталов (кредиты — нетто, средства клиентов, деньги, ФОР, банки, ССПУ, ССПСД); остатки книг
бумаг и ликвидности модели — data/facts/balance.json (history: books; до 31.12.2024 — процентные активы минус кредиты).

Правила (каждое — свидетельство, а не выбор):
  * окна: FY2024, FY2025, 1П2026 (годовое выражение ×2); средние — трапеция по концам кварталов окна (ХКФ с 31.03.2024 —
    справочно простое среднее концов);
  * перенос 1П2026: персонал казначейства 10,248 против 1,485 в 1П2025 — +8,763 ушли из сегментов. Возврат: «из КБ» (решение
    ведущего: КБ −4,985 г/г, розница +0,647 — данные говорят, что ушло из КБ) и «равный рост» (каждый сегмент — рост группы
    +9,95 %; так считал econ-blind) — два свидетельства 1П2026;
  * казначейство: персонал (до переноса) — себестоимость бумаг и ликвидности; «прочие расходы» казначейства (8,0 / 18,5 /
    8,4 за полугодие) — общебанковские функции и прочие операции (описание сегмента в МСФО), накладные всего банка:
    распределяются пропорционально, на относительные веса не влияют (вариант «на бумаги» — справочно);
  * франшиза комиссий: доля чистых комиссий в чистой выручке сегмента (процентный вклад с трансфертом + комиссии + валюта +
    прочие + страховое и небанковское нетто) — эта доля расходов сегмента идёт за базой комиссий, а не за балансом;
  * кредиты и средства внутри сегмента: «только кредиты» (нынешняя форма М13) — вся себестоимость сегмента на его кредитах;
    «баланс» — рубль кредита и рубль средств сегмента несут одну цену; «середина» — доля кредитов посередине между ними.
Франшизы в долях базы расходов (решения ведущего № 4, Р4-1, Р4-2; проход ядра 3, К2б; поток book4, 21.10.2026): схема
«<доля>/share» — франшиза комиссий (доля чистых комиссий в чистой выручке сегмента) и франшиза страхования (доля страхового и
небанковского нетто в чистой выручке сегмента — то же правило, класс 1) уходят из весов книг; их расходы — доли базы расходов
opex.line_shares {fees, insurance} = пул франшизы / все расходы базы (сегменты + персонал казначейства; накладные казначейства
распределены пропорционально и на доли не влияют). Схема «<доля>/share_f» — только франшиза комиссий в доле (страхование —
в весах книг, как прежде). Веса схемы share — себестоимость рубля книг без франшиз (без добавки пула на рубль базы, как у
«/loans» и «/iea»): иначе франшиза стоит дважды — в весах на кредитах и в доле на базе строки (класс 1). Центры и оси — та же
середина min…max окон, что у весов.
Запуск из корня: python -B data/assumptions/evidence/path/m13_cost_bases.py  (печать и out/m13_cost_bases_out.{json,txt})
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WINDOWS = {"FY2024": ("2023-12-31", "2024-12-31", 1.0), "FY2025": ("2024-12-31", "2025-12-31", 1.0),
           "1H2026": ("2025-12-31", "2026-06-30", 0.5)}
TRANSFER = ("from_corp", "equal_growth")
SPLITS = ("loans", "mid", "balance")
FRANCHISE = ("none", "fees")
SHARE_SCHEMES = {"share": ("fees", "ins"), "share_f": ("fees",)}   # франшизы в долях базы расходов (Р4-1, Р4-2; К2б)
# Решения ведущего № 10, Р10-2 (правило строк-долей на класс): строка-доля, у которой числитель на окнах не идёт за знаменателем,
# меряется только на окнах в условиях модели — ROE группы (отчётная) не ниже нижней границы ROE модели (круг 10: 15,5 % — смесь точки
# 2027–2036; книга fix11 — 15,02 %, слой M 2027 года, Р11-8; книга круга 12 — 14,24 %, слой M 2028 года (раздел И, Р12-1а; до него 13,86 %, слой M 2030 года); отбор окон не меняется). Франшиза страхования: страховое и небанковское нетто к чистой выручке сегментов 22,8 / 24,8 / 14,2 % — за выручкой
# не идёт; окна FY2024 (ROE 25,1 %) и 1П2026 (21,4 %), FY2025 (13,6 %) — вне. Франшиза комиссий за выручкой идёт — все окна;
# веса книг — себестоимость рубля книг (не строки-доли) — все окна. Центр и концы оси М13 — одним правилом (класс 4).
# ПРАВКА 28.10.2026 (решения ведущего № 11, Р11-8): мерило условий модели — ROE БЕЗ РАЗОВЫХ окна против нижней границы ROE модели
# (наименьший ROE слоёв: смесь точки, «свой взгляд», слой M; книга круга 11 — слой M 2028 года ≈ 14,3 %), то же, что у окон НДУ: FY2024
# 19,12 % и 1П2026 19,55 % — в условиях, FY2025 9,98 % — вне (отбор не меняется). Отбор сверяет шаг ends_roe_bound листа вывода.
MODEL_WINDOWS_ONLY = {"line_ins": ("FY2024", "1H2026")}
# ПРАВКА 28.10.2026 (решения ведущего № 11, раздел А — тип центра на класс; поток fix11): веса книг и доли франшиз М13 —
# статистики окон FY2024, FY2025, 1П2026 (таблица раздела А: «франшизы» — тип А) — центр типа А: СРЕДНЕЕ окон с равным весом
# окна (у 1П2026 два возврата переноса — два прочтения одного окна: окно входит средним своих прочтений), ось — диапазон тех
# же окон (min…max, как прежде). Было — середина min…max (тип В). Поле «mean» kernel_weights — центр книги (лист вывода
# m13_weights, m13_line_shares); «mid» — справочно.


def window_mean(vals, x, sel=None):
    """Тип А на окнах М13: среднее окон с равным весом окна; прочтения одного окна (возвраты переноса 1П2026) — средним."""
    by = {}
    for v in vals:
        if sel is None or sel(v):
            by.setdefault(v["_window"], []).append(v[x])
    return sum(sum(r) / len(r) for r in by.values()) / len(by)


def load():
    pnl = {}
    for r in csv.DictReader((HERE / "inputs" / "m13_segment_pnl.csv").open(encoding="utf-8")):
        pnl[(r["period"], r["segment"])] = {k: float(v) / 1000 for k, v in r.items() if k not in ("period", "segment", "source")}
    bal = {}
    for r in csv.DictReader((HERE / "inputs" / "m13_segment_balances.csv").open(encoding="utf-8")):
        bal[(r["date"], r["segment"])] = {k: float(v) / 1000 for k, v in r.items() if k not in ("date", "segment", "source")}
    facts = json.loads((ROOT / "data" / "facts" / "balance.json").read_text(encoding="utf-8"))
    sl_model = {}
    for p, v in facts["history"].items():
        bk = v.get("books")
        if bk and "securities" in bk:                         # концы 2024К1–К3 несут только книги средств клиентов (Р1)
            sl_model[v["date"]] = bk["securities"]["v"] + bk["liquidity"]["v"]
        elif p == facts.get("as_of") or v["date"] == facts["as_of"]:
            sl_model[v["date"]] = facts["books"]["securities"]["v"] + facts["books"]["liquidity"]["v"]
        else:
            sl_model[v["date"]] = v["iea"]["v"] - v["loans"]["v"]
    sl_model[facts["as_of"]] = facts["books"]["securities"]["v"] + facts["books"]["liquidity"]["v"]
    model = {v["date"]: {"iea": v["iea"]["v"], "loans": v["loans"]["v"]} for v in facts["history"].values()}
    return pnl, bal, sl_model, model


def ends_between(dates, a, b):
    return [d for d in sorted(dates) if a <= d <= b]


def trap(vals):
    n = len(vals) - 1
    return (vals[0] / 2 + sum(vals[1:-1]) + vals[-1] / 2) / n


def window_bases(bal, sl_model, a, b):
    dates = ends_between({d for d, _ in bal}, a, b)
    out = {}
    for seg in ("retail", "corp", "treas"):
        for m in ("loans", "funds"):
            vals = [bal[(d, seg)][m] for d in dates]
            out[f"{seg}_{m}"] = trap(vals)
            out[f"{seg}_{m}_simple"] = (vals[0] + vals[-1]) / 2
    sl_t = [sum(bal[(d, "treas")][k] for k in ("cash", "mand", "banks", "fvtpl", "fvoci")) for d in dates]
    out["treas_sl"] = trap(sl_t)
    out["model_sl"] = trap([sl_model[d] for d in dates])
    out["ends"] = dates
    return out


def revenue(r):
    # ПРАВКА 22.10.2026 (решения ведущего № 8, Р8-1; ревизия класса 6 sweep8 — не та подстрока): финансовые расходы МСФО 17
    # (ins_fin) в книге — в ЧПД (книга-обязательство insurance_liab, решения № 1, п. 6), строка insurance_net — без них (сверка
    # FY2024: nb_rev − nb_cost сегментов 48,395 = Σ insurance_net кварталов); доля франшизы страхования и веса книг меряются на
    # той же строке: ins_fin — в процентном вкладе сегмента, страховое нетто — nb_rev − nb_cost (итог выручки сегмента тот же).
    # Было: nb = nb_rev − nb_cost − ins_fin (доля франшизы страхования 0,1563, веса розничных кредитов 2,0084, средств ФЛ 0,7124)
    nic = r["ii"] + r["interseg_rev"] - r["ie"] - r["dia"] - r["interseg_exp"] - r["ins_fin"]
    fees = r["fee_inc"] - r["fee_exp"]
    nb = r["nb_rev"] - r["nb_cost"]
    total = nic + fees + r["fx"] + r["oth_inc"] + nb
    return {"nic": nic, "fees": fees, "fx": r["fx"], "other": r["oth_inc"], "nb": nb, "total": total}


def costs(pnl, period, transfer):
    R, C, T = (pnl[(period, s)] for s in ("retail", "corp", "treas"))
    k = {"retail": R["staff"] + R["other"], "corp": C["staff"] + C["other"], "treas_staff": T["staff"], "treas_other": T["other"]}
    if period == "1H2026":
        prev = {s: pnl[("1H2025", s)]["staff"] for s in ("retail", "corp", "treas")}
        moved = T["staff"] - prev["treas"]                      # 8,763: персонал, ушедший в казначейство
        if transfer == "from_corp":
            k["corp"] += moved
            k["treas_staff"] = prev["treas"]
        else:                                                    # каждый сегмент — с ростом группы
            g = sum(pnl[("1H2026", s)]["staff"] for s in ("retail", "corp", "treas")) / sum(prev.values())
            back = {s: prev[s] * g - pnl[("1H2026", s)]["staff"] for s in ("retail", "corp")}
            k["retail"] += back["retail"]
            k["corp"] += back["corp"]
            k["treas_staff"] = T["staff"] - back["retail"] - back["corp"]
        k["moved"] = moved
    return k


def per_ruble(k, rev, bases, years, split, franchise, sl_base, ins=False):
    """Себестоимость рубля книг сегментов. `franchise` — "fees": доля чистых комиссий в чистой выручке сегмента уходит в пул
    франшизы комиссий; `ins` — то же для страхового и небанковского нетто (пул франшизы страхования; Р4-1, правило то же)."""
    out = {}
    pool_fee = pool_ins = 0.0
    for seg, key in (("retail", "R"), ("corp", "C")):
        K = k[seg] / years
        phi = max(0.0, rev[seg]["fees"] / rev[seg]["total"]) if franchise == "fees" else 0.0
        phi_i = max(0.0, rev[seg]["nb"] / rev[seg]["total"]) if ins else 0.0
        pool_fee += K * phi
        pool_ins += K * phi_i
        out[f"phi_ins_{key}"] = phi_i
        K_bal = K * (1 - phi - phi_i)
        L, F = bases[f"{seg}_loans"], bases[f"{seg}_funds"]
        s_bal = L / (L + F)
        s_L = {"loans": 1.0, "balance": s_bal, "mid": (1.0 + s_bal) / 2}[split]
        out[f"{key}L"] = K_bal * s_L / L
        out[f"{key}F"] = K_bal * (1 - s_L) / F
        out[f"phi_{key}"] = phi
    out["SL"] = k["treas_staff"] / years / bases[sl_base]
    out["SL_full"] = (k["treas_staff"] + k["treas_other"]) / years / bases[sl_base]
    fees_net = (rev["retail"]["fees"] + rev["corp"]["fees"]) / years
    out["FEE_per_net_fee"] = pool_fee / fees_net if fees_net else 0.0
    out["fee_pool"] = pool_fee
    out["ins_pool"] = pool_ins
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    pnl, bal, sl_model, model = load()
    rows, lines = [], []

    def say(t=""):
        lines.append(t)
        print(t)

    say("М13 — себестоимость рубля книг по сегментам МСФО (млрд ₽; ставки — % в год; веса — к корпоративному кредиту = 1)")
    for p, (a, b, years) in WINDOWS.items():
        bases = window_bases(bal, sl_model, a, b)
        rev = {s: revenue(pnl[(p, s)]) for s in ("retail", "corp")}
        say(f"\n{p}: концы {bases['ends'][0]}…{bases['ends'][-1]} ({len(bases['ends'])}); средние (трапеция): кредиты Р {bases['retail_loans']:.1f} "
            f"/ КБ {bases['corp_loans']:.1f}; средства Р {bases['retail_funds']:.1f} / КБ {bases['corp_funds']:.1f}; бумаги и ликвидность: "
            f"книги модели {bases['model_sl']:.1f}, казначейство {bases['treas_sl']:.1f}")
        say(f"  выручка сегмента (чистая, без резервов и расходов): Р {rev['retail']['total']:.1f} (комиссии {rev['retail']['fees']:.1f}), "
            f"КБ {rev['corp']['total']:.1f} (комиссии {rev['corp']['fees']:.1f}, валюта {rev['corp']['fx']:.1f}, процентный вклад {rev['corp']['nic']:.1f})")
        for tr in (TRANSFER if p == "1H2026" else ("—",)):
            k = costs(pnl, p, tr if tr != "—" else "from_corp")
            say(f"  перенос {tr}: расходы Р {k['retail'] / years:.2f}, КБ {k['corp'] / years:.2f}, казначейство персонал {k['treas_staff'] / years:.2f}, "
                f"прочие {k['treas_other'] / years:.2f} (в год)")
            for sl_base in ("model_sl", "treas_sl"):
                for fr in FRANCHISE:
                    for sp in SPLITS:
                        c = per_ruble(k, rev, bases, years, sp, fr, sl_base)
                        w = {x: c[x] / c["CL"] for x in ("RL", "RF", "CF", "SL", "SL_full")}
                        rows.append({"window": p, "transfer": tr, "sl_base": sl_base, "franchise": fr, "split": sp,
                                     **{f"c_{x}": round(100 * c[x], 4) for x in ("RL", "RF", "CL", "CF", "SL", "SL_full")},
                                     **{f"w_{x}": round(v, 4) for x, v in w.items()},
                                     "phi_R": round(c["phi_R"], 4), "phi_C": round(c["phi_C"], 4),
                                     "fee_cost_per_net_fee": round(c["FEE_per_net_fee"], 4), "fee_pool": round(c["fee_pool"], 3)})
                        if sl_base == "model_sl":
                            say(f"    франшиза {fr:4s} {sp:7s}: ₽ на рубль: РК {100 * c['RL']:.2f}  РС {100 * c['RF']:.2f}  КК {100 * c['CL']:.2f}  "
                                f"КС {100 * c['CF']:.2f}  БЛ {100 * c['SL']:.3f} | веса: РК {w['RL']:.3f} РС {w['RF']:.3f} КС {w['CF']:.3f} "
                                f"БЛ {w['SL']:.3f} (с накладными казначейства {w['SL_full']:.3f})"
                                + (f" | φ Р {c['phi_R']:.3f} КБ {c['phi_C']:.3f}, франшиза {c['fee_pool']:.1f} — {c['FEE_per_net_fee']:.2f} ₽ на рубль комиссий" if fr == "fees" else ""))
    # центры и оси: по каждому правилу — середина min…max свидетельств окон (1П2026 — оба возврата переноса)
    say("\nЦентры (середина min…max окон FY2024, FY2025, 1П2026 с обоими возвратами переноса) и оси, база бумаг — книги модели:")
    summary = {}
    for fr in FRANCHISE:
        for sp in SPLITS:
            sel = [r for r in rows if r["franchise"] == fr and r["split"] == sp and r["sl_base"] == "model_sl"]
            s = {}
            for x in ("w_RL", "w_RF", "w_CF", "w_SL", "w_SL_full"):
                vals = [r[x] for r in sel]
                s[x] = {"min": min(vals), "max": max(vals), "mid": round((min(vals) + max(vals)) / 2, 4)}
            summary[f"{fr}/{sp}"] = s
            say(f"  франшиза {fr:4s} {sp:7s}: " + "; ".join(f"{x[2:]} {v['mid']:.3f} ({v['min']:.3f}–{v['max']:.3f})" for x, v in s.items()))
    sel = [r for r in rows if r["sl_base"] == "treas_sl" and r["split"] == "loans" and r["franchise"] == "none"]
    say("  справочно, база бумаг — бумаги и ликвидность сегмента «Казначейство»: вес БЛ (только кредиты, без франшизы) "
        + ", ".join(f"{r['window']}{'' if r['transfer'] == '—' else ' ' + r['transfer']} {r['w_SL']:.3f}" for r in sel))
    # веса для ядра: франшиза комиссий — к драйверу комиссий (процентные активы iea или кредиты): её себестоимость на рубль базы
    # прибавляется ко всем книгам базы; середина окон, оси — min…max окон
    say()
    say("Веса для ядра (книги: розница РК, юрлица КК = 1, бумаги и ликвидность БЛ, средства ФЛ РС, средства ЮЛ КС), среднее окон — тип А "
        "(решения № 11, раздел А; середина и min–max — рядом):")
    kern = {}
    for sp in SPLITS:
        for fdrv in ("none", "iea", "loans"):
            vals = []
            for p, (a, b, years) in WINDOWS.items():
                bases = window_bases(bal, sl_model, a, b)
                dates = bases["ends"]
                iea = trap([model[d]["iea"] for d in dates]); lns = trap([model[d]["loans"] for d in dates])
                rev = {s_: revenue(pnl[(p, s_)]) for s_ in ("retail", "corp")}
                for tr in (TRANSFER if p == "1H2026" else ("from_corp",)):
                    k = costs(pnl, p, tr)
                    c = per_ruble(k, rev, bases, years, sp, "none" if fdrv == "none" else "fees", "model_sl")
                    f_a = c["fee_pool"] / iea if fdrv == "iea" else 0.0
                    f_l = c["fee_pool"] / lns if fdrv == "loans" else 0.0
                    cl = c["CL"] + f_a + f_l
                    vals.append({"_window": p, "RL": (c["RL"] + f_a + f_l) / cl, "SL": (c["SL"] + f_a) / cl, "RF": c["RF"] / cl,
                                 "CF": c["CF"] / cl, "pool_share": c["fee_pool"] / ((k["retail"] + k["corp"]) / years)})
            agg = {x: {"min": round(min(v[x] for v in vals), 4), "max": round(max(v[x] for v in vals), 4),
                       "mid": round((min(v[x] for v in vals) + max(v[x] for v in vals)) / 2, 4),
                       "mean": round(window_mean(vals, x), 4),
                       "windows": {w: round(window_mean([v for v in vals if v["_window"] == w], x), 6) for w in WINDOWS}}
                   for x in vals[0] if x != "_window"}
            kern[f"{sp}/{fdrv}"] = agg
            say(f"  {sp:7s} франшиза→{fdrv:5s}: " + "; ".join(f"{x} {v['mean']:.4f} [середина {v['mid']:.3f}] ({v['min']:.3f}–{v['max']:.3f})"
                                                            for x, v in agg.items()))
        # франшизы в долях базы расходов (Р4-1, Р4-2; К2б): веса — себестоимость рубля книг без франшиз, доли — пул / все
        # расходы базы (сегменты + персонал казначейства)
        for scheme, fr_lines in SHARE_SCHEMES.items():
            vals = []
            for p, (a, b, years) in WINDOWS.items():
                bases = window_bases(bal, sl_model, a, b)
                rev = {s_: revenue(pnl[(p, s_)]) for s_ in ("retail", "corp")}
                for tr in (TRANSFER if p == "1H2026" else ("from_corp",)):
                    k = costs(pnl, p, tr)
                    c = per_ruble(k, rev, bases, years, sp, "fees", "model_sl", ins="ins" in fr_lines)
                    total = (k["retail"] + k["corp"] + k["treas_staff"]) / years
                    vals.append({"_window": p, "RL": c["RL"] / c["CL"], "SL": c["SL"] / c["CL"], "RF": c["RF"] / c["CL"], "CF": c["CF"] / c["CL"],
                                 "line_fees": c["fee_pool"] / total, "line_ins": c["ins_pool"] / total,
                                 "phi_ins_R": c["phi_ins_R"], "pool_share": c["fee_pool"] / ((k["retail"] + k["corp"]) / years)})
            def sel(x):        # Р10-2: строка-доля, не идущая за знаменателем, — окна в условиях модели
                return [v[x] for v in vals if x not in MODEL_WINDOWS_ONLY or v["_window"] in MODEL_WINDOWS_ONLY[x]]
            def keep(x):
                return lambda v: x not in MODEL_WINDOWS_ONLY or v["_window"] in MODEL_WINDOWS_ONLY[x]
            agg = {x: {"min": round(min(sel(x)), 4), "max": round(max(sel(x)), 4),
                       "mid": round((min(sel(x)) + max(sel(x))) / 2, 4),
                       "mean": round(window_mean(vals, x, keep(x)), 4),
                       "windows": {w: round(window_mean([v for v in vals if v["_window"] == w], x), 6) for w in WINDOWS
                                   if keep(x)({"_window": w})}}
                   for x in vals[0] if x != "_window"}
            kern[f"{sp}/{scheme}"] = agg
            say(f"  {sp:7s} франшизы в долях ({scheme}): " + "; ".join(f"{x} {v['mean']:.4f} [середина {v['mid']:.4f}] ({v['min']:.4f}–{v['max']:.4f})"
                                                                       for x, v in agg.items()))
    out = {"rows": rows, "summary": summary, "kernel_weights": kern}
    target = HERE / "out" / "m13_cost_bases_out.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    target.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
