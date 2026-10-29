"""Синтетический выпуск svcb-v1 для витрины: tests/fixtures/payload-sample.json и общая форма.

Генератор даёт две формы выпуска (docs/DASHBOARD.md §7):

* форма панели — tests/fixtures/payload-sample.json: один тикер, делитель «размещённые
  акции», квартальные дивиденды по периодам (реестр, история, экс-даты, мост, путь
  `model_quarters` с решёнными кварталами, проверка потолка `cap_check`), требование к
  капиталу с глиссадой и запас якоря до него, рост, на который хватает капитала, «цена
  правила», путь к терминалу, мост трёх прибылей, месячная таблица операционных результатов,
  пределы обратного расчёта, событие дробления, оценочные даты календаря, флаги
  `deal_pending` и `capital_estimated`; узлы «на чём стоит заголовок» — суждение о марже
  ключом уровня (`nii.transmission.level`: ключ цели — стационарная маржа мира окна фактов),
  уровни с окном фактов (`paths.levels`, `paths.levels.window`), модальная клетка
  (`paths.modal_cell`), путь фондирования (`paths.funding`), мир уровней режимов
  (`regimes.reference_world`), справочные варианты по модулю цены с подписью строки
  (`book.reference_variants`), список строк обратного расчёта с уточнением на полной полосе
  (`reverse_dcf.refine_rows`, `gap_basis`), счётчики сводки контрольной модели; поля каркаса,
  которым нечего нести, пусты (`formula_check`, месяцы РСБУ, оценка квартала по РСБУ);
* общая форма без узлов панели — tests/web/payload-generic.json (модуль sample_generic).

Порядки формы панели: цена ≈270 ₽, медиана ≈350 ₽; ЧИСЛА ВЫДУМАНЫ — это заглушка, не
оценка. Тождества validate (П§7) выполнены, печатаемые строки — словами (П§0.2).

    python tests/web/make_sample.py            # перезаписать обе фикстуры
    python tests/web/make_sample.py --check    # сверить файлы с генератором
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "tests" / "fixtures" / "payload-sample.json"
sys.path.insert(0, str(HERE))

import sample_generic as G  # noqa: E402  общая форма и общие помощники (печать, квантиль, хэш)

hup, r, q7, wq, seal, render, trading_days = G.hup, G.r, G.q7, G.wq, G.seal, G.render, G.trading_days

RNG = random.Random(8501)

# ── константы формы панели ──
SCHEMA = "svcb-v1"
MAIN = "T"
TICKERS = [MAIN]
PRICE = 271.2
N_ISS = 2682.748            # размещённые акции после дробления, млн шт.
N_TREASURY = 132.8
N_OUT = round(N_ISS - N_TREASURY, 3)
N_DIV = N_ISS               # делитель: размещённые акции (valuation.shares_basis: issued)
SPLIT_DATE = "2026-04-15"
SPLIT = 10
VDATE = "2026-10-07"
FACTS_DATE = "2026-06-30"
LAM = 0.5
STEP = 5.0
DRAWS = 2000
YEARS = list(range(2026, 2037))
NY = len(YEARS)
WORLDS = ["N", "H", "M"]
REGIMES = ["soft", "norm", "downturn", "crisis"]
SCEN = ["schedule", "mid", "strict"]
WORLD_NAMES = {"N": "Нормализация ставок", "H": "Высокие ставки надолго", "M": "Рыночный как есть"}
REGIME_NAMES = {"soft": "Мягкая посадка", "norm": "Нормализация", "downturn": "Розничный спад", "crisis": "Кризис"}
SCEN_NAMES = {"schedule": "По графику", "mid": "Средняя группа СЗКО", "strict": "Жёсткий"}
W_A = {"N": 0.35, "H": 0.45, "M": 0.20}
W_MI = {"N": 0.10, "H": 0.25, "M": 0.65}
W_N = {"N": 0.0, "H": 0.0, "M": 1.0}
P_REG = {"soft": 0.15, "norm": 0.40, "downturn": 0.30, "crisis": 0.15}
P_SC = {g: {"schedule": 0.25, "mid": 0.45, "strict": 0.30} for g in REGIMES}
P_SC["crisis"] = {"schedule": 0.70, "mid": 0.25, "strict": 0.05}
BV_V = 702.4                # капитал акционеров на дату оценки, млрд ₽
GOV = 0.0                   # дисконт за управление
BOOK = "1.1"
BOOK_PREV = "1.0"
QUARTERS = 14               # кварталов в квартальных узлах выпуска
PERIODS = [f"{2026 + (2 + i) // 4}Q{(2 + i) % 4 + 1}" for i in range(QUARTERS)]   # 2026Q3 … 2029Q4
LABELS = {1: "за первый квартал {y} года", 2: "за полугодие {y} года", 3: "за девять месяцев {y} года", 4: "за {y} год"}
TITLES = {"n20": "Н20.0 банковской группы", "n11": "Н20.1 банковской группы", "n11_observed": "Н20.1 банковской группы, форма 0409805",
          "n1_0": "Н1.0 банка", "n1_2": "Н1.2 банка"}
BASIS_LABELS = {"profit": "операционная прибыль акционеров — без переоценки пакета и процентов по долгу под него (определение эмитента)",
                "roe": "операционная прибыль акционеров к капиталу акционеров МСФО", "divisor": "размещённые акции",
                "dividend_issued": "на все размещённые акции", "dividend_outstanding": "на акции в обращении"}
TERMS = {"lt_level": "после фазы роста", "profit_short": "операционная прибыль", "noncore": "доход пакета (возврат процентов по долгу под него)",
         "cir": "C/I", "roe_lt": "ROE после фазы роста", "stake": "пакет Яндекса и долг под него"}
# четыре последних объявленных квартала прибыли и их DPS — окно дивидендной доходности за 12 месяцев
LTM_PERIODS = ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
LTM_DPS = 3.6 + 4.5 + 4.6 + 4.7
# ключ цели маржи — само суждение книги: стационарная маржа мира окна фактов (M) на составе баланса якоря;
# уровень мира-опоры (H) решатель выводит из неё
NIM_JUDGED, NIM_REF = 0.111, 0.1131
# окно фактов: наименьший, наибольший и средний квартал (упр.), доля кредитов в процентных активах — окно и якорь
WINDOW = {"nim": {"min": 0.0912, "max": 0.0998, "mean": 0.0961}, "cor": {"min": 0.0469, "max": 0.0665, "mean": 0.0564},
          "cir": {"min": 0.46, "max": 0.4828, "mean": 0.4704}, "loans_share": {"window": 0.6358, "anchor": 0.677}}
MODAL = ("H", "norm", "mid")              # модальная клетка


def label_of(period: str) -> str:
    return LABELS[int(period[-1])].format(y=period[:4])


def yearly(vals):
    return [{"year": y, "value": r(v, 6)} for y, v in zip(YEARS, vals)]


def ramp(a, b, n=NY, k=4):
    return [a + (b - a) * min(1.0, i / k) for i in range(n)]


def price_of(v0, bridge=0.0):
    """Формула цены М§8.2 на делителе выпуска (объявленный дивиденд без дисконта при g = 0 не выделяется)."""
    return (v0 * (1 - GOV) + bridge) * 1000 / N_DIV


# ── сетка ──
PB_W = {"N": 1.86, "H": 1.48, "M": 1.246}
F_R = {"soft": 1.14, "norm": 1.05, "downturn": 0.93, "crisis": 0.74}
F_S = {"schedule": 1.03, "mid": 1.0, "strict": 0.965}
BASE_N20 = [0.1262, 0.1268, 0.1362, 0.1392, 0.1396, 0.1398, 0.1399, 0.14, 0.14, 0.1401, 0.1401]     # Н20.0 на конец года, общий уровень
NI_PATH = [212.0, 258.0, 304.0, 346.0, 384.0, 418.0, 448.0, 474.0, 497.0, 517.0, 535.0]      # операционная прибыль акционеров
BV_PATH = [802.0, 968.0, 1160.0, 1372.0, 1600.0, 1838.0, 2082.0, 2330.0, 2580.0, 2830.0, 3080.0]
DPS_YEAR = [19.64, 23.4, 27.6, 31.4, 34.9, 38.0, 40.7, 43.1, 45.2, 47.0]                         # DPS политики: сумма кварталов прибыли года
ROE_T_W = {"N": 0.18, "H": 0.195, "M": 0.222}
K_T_W = {"N": 0.15, "H": 0.185, "M": 0.214}
G_T_W = {"N": 0.055, "H": 0.07, "M": 0.105}


def make_cells():
    cells = []
    for w in WORLDS:
        for rg in REGIMES:
            for s in SCEN:
                pb = PB_W[w] * F_R[rg] * F_S[s]
                v = BV_V * pb
                crisis = rg == "crisis"
                cut = rg == "downturn" and s == "strict" and w != "N"
                gap = crisis and s != "schedule" and w != "N"
                growth_cut = s == "strict" or (s == "mid" and rg in ("downturn", "crisis"))
                roe_t = ROE_T_W[w] + {"soft": 0.012, "norm": 0.0, "downturn": -0.012, "crisis": -0.03}[rg]
                n20 = [BASE_N20[i] + {"soft": 0.003, "norm": 0.0, "downturn": -0.004, "crisis": -0.014}[rg] * (0.2 if i == 0 else 1 if i <= 3 else 0.4)
                       + {"schedule": 0.0015, "mid": 0.0, "strict": -0.002}[s] * min(1, i / 2) - (0.012 if gap and i == 1 else 0) for i in range(NY)]
                flags = [name for name, on in (("capital_gap", gap), ("roe_below_k", roe_t < K_T_W[w]), ("dividend_cut", cut), ("crisis_skip", crisis),
                                               ("growth_cut", growth_cut), ("growth_solver", crisis and s == "strict" and w == "M")) if on]
                ni = [NI_PATH[i] * F_R[rg] ** (0.7 if i > 0 else 0.1) * (0.55 if crisis and i == 1 else 1)
                      * (1 + (0.02 if w == "M" else -0.01 if w == "N" else 0) * i) for i in range(NY)]
                cor = [0.056 + {"soft": -0.006, "norm": 0.0, "downturn": 0.012, "crisis": 0.02}[rg] * (1 if i < 3 else 0.35)
                       + (0.03 if crisis and i == 1 else 0) for i in range(NY)]
                nim = [0.1058 - (0.006 if crisis and i == 1 else 0) + {"N": -0.004, "H": 0.0, "M": 0.005}[w] * min(1, i / 3) for i in range(NY)]
                dps = [DPS_YEAR[i] * F_R[rg] ** 0.8 * (0.42 if crisis and i == 1 else 1) for i in range(NY - 1)] + [None]   # решение за 4-й квартал последнего года — за сеткой
                payout = [None if x is None else r(x * N_ISS / 1000 / ni[i], 4) for i, x in enumerate(dps)]
                cells.append({
                    "world": w, "regime": rg, "scenario": s,
                    "p_analytical": r(W_A[w] * P_REG[rg] * P_SC[rg][s], 6), "p_market_implied": r(W_MI[w] * P_REG[rg] * P_SC[rg][s], 6),
                    "p_neutral": r(W_N[w] * P_REG[rg] * P_SC[rg][s], 6),
                    "v": r(v), "bv_v": BV_V, "price": r(price_of(v)), "pb": r(pb, 4),
                    "pv_ri_explicit": r((v - BV_V) * (0.58 if not crisis else 0.4)), "terminal_share": r(0.44 + 0.04 * (PB_W[w] - 1), 4),
                    "roe_t": r(roe_t, 4), "k_t": K_T_W[w], "g_t": G_T_W[w], "x_t": r(18 + 8 * (PB_W[w] - 1)),
                    "n20_min": r(min(n20), 4), "n11_min": r(min(n20) - 0.023, 4), "gap_period": "2027Q2" if gap else None,
                    "dps_first": r(dps[0]), "flags": flags,
                    "annual": {"ni_sh": [r(x, 1) for x in ni], "roe": [r(x / b, 4) for x, b in zip(ni, BV_PATH)],
                               "cor": [r(x, 4) for x in cor], "nim": [r(x, 4) for x in nim],
                               "cir": [r(0.474 - 0.002 * min(i, 4), 4) for i in range(NY)],
                               "n20": [r(x, 4) for x in n20], "n11": [r(x - 0.023, 4) for x in n20],
                               "dps": [r(x) for x in dps], "payout": payout},
                })
    for key in ("p_analytical", "p_market_implied", "p_neutral"):          # последняя клетка слоя — остаток до суммы 1
        total = sum(c[key] for c in cells)
        last = max(range(len(cells)), key=lambda i: cells[i][key])
        cells[last][key] = r(cells[last][key] + 1 - total, 6)
    return cells


def layer(cells, key, title, weights):
    v0 = sum(c[key] * c["v"] for c in cells)
    pvri = r(sum(c[key] * c["pv_ri_explicit"] for c in cells))
    return {"title": title, "world_weights": weights, "v0": r(v0), "bv_v": BV_V, "price": r(price_of(v0)), "pb": r(v0 / BV_V, 4),
            "excess": r(v0 - BV_V), "pv_ri_explicit": pvri, "pv_terminal": r(v0 - BV_V - pvri),
            "terminal_share": r(sum(c[key] * c["terminal_share"] for c in cells), 4),
            "roe_tc": r(sum(c[key] * c["roe_t"] for c in cells), 4), "k_tc": r(sum(c[key] * c["k_t"] for c in cells), 4),
            "p_price_below_market": r(sum(c[key] for c in cells if c["price"] < PRICE), 6),
            "p_roe_below_k": r(sum(c[key] for c in cells if c["roe_t"] < c["k_t"]), 6),
            "capital_gap_mass": r(sum(c[key] for c in cells if "capital_gap" in c["flags"]), 6)}


def make_draws(low_c, high_c):
    """Низ и верх прогонов: медиана центра при λ книги ≈350 ₽, точка — выше медианы."""
    lows, highs = [], []
    for _ in range(DRAWS):
        z = RNG.gauss(0, 1)
        c = 352 + 47 * z - 5 * z * z
        d = (high_c - low_c) * (1 + 0.18 * RNG.gauss(0, 1))
        lows.append(hup(max(40.0, c - d / 2), 0.1))
        highs.append(hup(max(40.0, c + d / 2), 0.1))
    return lows, highs


def stats_at(lows, highs, lam):
    c = sorted(lo + lam * (hi - lo) for lo, hi in zip(lows, highs))
    return {"median": q7(c, 0.5), "p10": q7(c, 0.1), "p25": q7(c, 0.25), "p75": q7(c, 0.75), "p90": q7(c, 0.9), "mean": sum(c) / len(c),
            "p_below": sum(1 for x in c if x < PRICE) / len(c), "pct": sum(1 for x in c if x <= PRICE) / len(c)}


# ── дивиденды по периодам: решения собраний (факты), реестр, путь модели ──
# период, DPS после дробления, DPS решения до дробления, день решения, отсечка, выплата, объявленный пул
DECISIONS = [("2024Q3", 9.25, 92.5, "2024-11-12", "2024-11-25", "2024-12-06", 24.8), ("2024Q4", 3.2, 32.0, "2025-06-05", "2025-06-17", "2025-06-30", 8.58),
             ("2025Q1", 3.3, 33.0, "2025-06-30", "2025-07-17", "2025-07-31", 8.85), ("2025Q2", 3.5, 35.0, "2025-09-25", "2025-10-06", "2025-10-20", 9.39),
             ("2025Q3", 3.6, 36.0, "2025-12-25", "2026-01-08", "2026-01-22", 9.66), ("2025Q4", 4.5, 45.0, "2026-05-14", "2026-05-25", "2026-06-08", 12.07)]
REGISTER = [("2026Q1", 4.6, "2026-07-30", "2026-08-10", "2026-08-07", "2026-08-24", "paid"),
            ("2026Q2", 4.7, "2026-10-01", "2026-10-12", "2026-10-09", "2026-10-26", "declared")]
DPS_POLICY_Q = {"2026Q3": 5.02, "2026Q4": 5.31}         # DPS политики первых открытых кварталов
DPS_POLICY_DONE = {"2026Q1": 4.55, "2026Q2": 4.76}      # DPS политики решённых кварталов: решения собраний — 4,60 и 4,70
SHOCK_Q = ("2026Q4", "2027Q1", "2027Q2", "2027Q3")      # кварталы прибыли, решение по которым приходится на год шока
Q_MEAN = lambda p, policy: policy * (0.86 if p in SHOCK_Q else 0.985)  # noqa: E731  ожидание по клеткам с отменой в кризисе
# ожидание DPS года якоря: два решения собраний и два открытых квартала — ниже суммы политики
DPS_MEAN_0 = round(sum(dps for _p, dps, *_ in REGISTER) + sum(Q_MEAN(p, v) for p, v in DPS_POLICY_Q.items()), 4)


def build():
    RNG.seed(8501)
    cells = make_cells()
    la = layer(cells, "p_analytical", "свой макро-взгляд", W_A)
    lm = layer(cells, "p_market_implied", "вменённые рынком", W_MI)
    ln = layer(cells, "p_neutral", "рыночные ставки как есть", W_N)
    low_p, high_p = ln["price"], la["price"]
    central = low_p + LAM * (high_p - low_p)
    lows, highs = make_draws(low_p, high_p)
    median = stats_at(lows, highs, LAM)["median"]
    cap = r(PRICE * N_DIV / 1000)

    # ── мост и смесь заголовка: объявленные дивиденды ещё не вышли из капитала модели или уже прошли экс-дату ──
    div_rows = [{"year": int(p[:4]), "period": p, "label": label_of(p), "dps": dps, "amount": r(dps * N_OUT / 1000),
                 "deducted_on": "2026-09-30" if p == "2026Q1" else "2026-12-31", "last_buy_date": buy, "ex_date": rec, "sign": 0}
                for p, dps, _dec, rec, buy, _pay, _st in REGISTER]
    bridge_amount = r(sum(x["amount"] * x["sign"] for x in div_rows))
    pending = div_rows[-1]["amount"]                 # объявлен, из капитала модели ещё не вычтен: внутри V0
    v0_mix = ln["v0"] + LAM * (la["v0"] - ln["v0"])
    pvri_mix = ln["pv_ri_explicit"] + LAM * (la["pv_ri_explicit"] - ln["pv_ri_explicit"])
    pvt_mix = v0_mix - BV_V - pvri_mix
    gov_amount = -GOV * (v0_mix - pending)
    equity = v0_mix + gov_amount + bridge_amount
    per = lambda x: r(x * 1000 / N_DIV)  # noqa: E731
    waterfall = [{"key": k, "title": t, "amount": r(a), "per_share": per(a), "total": tot} for k, t, a, tot in (
        ("bv_v", "Капитал на дату оценки", BV_V, False),
        ("pv_ri_explicit", "PV доходности сверх стоимости капитала, явный участок", pvri_mix, False),
        ("pv_terminal", "PV терминала (остаточный доход)", pvt_mix, False), ("v0", "Оценка капитала V0", v0_mix, True),
        ("governance", "Дисконт за управление", gov_amount, False), ("bridge", "Объявленный дивиденд до отсечки", bridge_amount, False),
        ("equity", "Капитал акционеров по модели", equity, True))]
    headline_mix = {"title": "смесь заголовка: λ × «свой взгляд» + (1 − λ) × «рыночные ставки»", "lambda": LAM,
                    "v0": r(v0_mix), "bv_v": BV_V, "pv_ri_explicit": r(pvri_mix), "pv_terminal": r(pvt_mix),
                    "governance": r(gov_amount), "bridge": bridge_amount, "price": r(central), "waterfall": waterfall}

    # ── заголовок и таблица λ ──
    def headline_row(lam):
        s = stats_at(lows, highs, lam)
        return {"lambda": round(lam, 2), "median": r(s["median"]), "p10": r(s["p10"]), "p25": r(s["p25"]), "p75": r(s["p75"]), "p90": r(s["p90"]),
                "mean": r(s["mean"]), "point": r(low_p + lam * (high_p - low_p)), "p_below_market": r(s["p_below"], 6),
                "p_below_by_ticker": {MAIN: r(s["p_below"], 6)}, "market_percentile": r(s["pct"], 6), "upside": {MAIN: r(s["median"] / PRICE - 1, 6)}}

    by_lambda = [headline_row(i / 20) for i in range(21)]
    book_row = by_lambda[10]
    judg = judgement_axes()
    shares = [0.238, 0.162, 0.121, 0.098, 0.09, 0.082, 0.064, 0.048, 0.039, 0.031, 0.026, 0.021, 0.018, 0.014, 0.012, 0.009, 0.007, 0.006, 0.004, 0.003]
    scalar = [j for j in judg if j["kind"] != "dict"]
    contributions = [{"axis": j["id"], "name": j["name"], "share": r(share / sum(shares), 6),
                      "rank_corr": r(math.copysign(math.sqrt(share * 0.93), j["sign"]), 3), "paths": j["paths"], "judgement_key": j["id"]}
                     for share, j in zip(shares, scalar)]
    contributions[0]["share"] = r(1 - sum(c["share"] for c in contributions[1:]), 6)
    share_of = {c["axis"]: c for c in contributions}
    head = {
        "median": book_row["median"], "printed_median": hup(book_row["median"], STEP),
        "band80": [book_row["p10"], book_row["p90"]], "printed_band80": [hup(book_row["p10"], STEP), hup(book_row["p90"], STEP)],
        "band50": [book_row["p25"], book_row["p75"]], "printed_band50": [hup(book_row["p25"], STEP), hup(book_row["p75"], STEP)],
        "mean": book_row["mean"], "point": r(central), "printed_point": hup(r(central), STEP),
        "market": PRICE, "market_by_ticker": {MAIN: PRICE}, "p_below_market": book_row["p_below_market"],
        "p_below_by_ticker": book_row["p_below_by_ticker"], "market_percentile": book_row["market_percentile"], "upside": book_row["upside"],
        "draws": DRAWS, "seed": 20261007, "quantiles": [0.1, 0.25, 0.5, 0.75, 0.9], "own_macro_confidence": LAM, "lambda_step": 0.05,
        "print_step": STEP, "ceiling_x_market": 3.0, "low_draws": lows, "high_draws": highs, "contributions": contributions, "by_lambda": by_lambda}

    # ── язык банка ──
    def first_line(lam):
        s = stats_at(lows, highs, lam)
        v_point = (low_p + lam * (high_p - low_p)) * N_DIV / 1000
        v_med = (s["median"] * N_DIV / 1000 - bridge_amount - pending) / (1 - GOV) + pending
        return {"lambda": round(lam, 2), "bv_v": BV_V, "v_point": r(v_point), "v_median": r(v_med), "fair_pb_point": r(v_point / BV_V, 4),
                "fair_pb_median": r(v_med / BV_V, 4), "market_pb": r(cap / BV_V, 4), "excess_point": r(v_point - BV_V),
                "excess_median": r(v_med - BV_V), "excess_market": r(cap - BV_V),
                "roe_tc": r(ln["roe_tc"] + lam * (la["roe_tc"] - ln["roe_tc"]), 4), "k_tc": r(ln["k_tc"] + lam * (la["k_tc"] - ln["k_tc"]), 4),
                "rub_per_1pp_roe": r(18.6 + 3 * lam, 2), "rub_per_01pp_cor": r(-5.4 - 0.6 * lam, 2), "rub_per_01pp_nim": r(6.1 + 0.8 * lam, 2),
                "rub_per_1pp_buffer": r(-5.8 - 0.8 * lam, 2)}

    bfl_rows = [first_line(i / 20) for i in range(21)]
    bfl = dict(bfl_rows[10])
    bfl.pop("lambda")
    bfl.update({"target": "median", "roe_ltm": 0.2812,
                "sensitivity_basis": "сдвиг путей стоимости риска всех режимов на 0,1 п.п. (упр. базис, мостом в движок); ЧПМ после фазы роста (упр.) "
                                     "на 0,1 п.п.; ROE — через строку ЧПМ; запас менеджмента над минимумом обоих нормативов — на 1 п.п.",
                "layers": {k: {"bv_v": BV_V, "v0": L["v0"], "fair_pb": L["pb"], "excess": L["excess"], "roe_tc": L["roe_tc"], "k_tc": L["k_tc"]}
                           for k, L in (("analytical", la), ("macro_neutral", ln))},
                "by_lambda": bfl_rows})
    by_world = {}
    for w in WORLDS:
        v0w = sum(P_REG[c["regime"]] * P_SC[c["regime"]][c["scenario"]] * c["v"] for c in cells if c["world"] == w)
        by_world[w] = {"price": r(price_of(v0w)), "v0": r(v0w), "bv_v": BV_V, "pb": r(v0w / BV_V, 4)}
    fair_value = {
        "method": "judgement_median", "target": "median", "headline": head, "low": r(low_p), "central": r(central), "high": r(high_p),
        "printed_low": hup(r(low_p), STEP), "printed_central": hup(r(central), STEP), "printed_high": hup(r(high_p), STEP),
        "own_macro_confidence": LAM, "rates_view": {"low": r(low_p), "high": r(high_p), "rub": r(r(high_p) - r(low_p))}, "bank_first_line": bfl,
        "bridge": {"amount": bridge_amount, "per_share": per(bridge_amount), "governance_applies": False, "pending_dividend": pending, "rows": div_rows,
                   "amount_basis": "outstanding"},
        "by_world": by_world,
        "jump_guard": {"previous_median": r(median - 2.1), "exdate_adjustment": 0.0, "median_change": r(2.1 / (median - 2.1), 6), "median_limit": 0.08,
                       "v0_agm_adjustment": 0.0, "v0_change": 0.0058, "unregistered_dividend": 0.0, "unregistered_dps": 0.0, "v0_limit": 0.08,
                       "reason": "within_limit"}}

    capital = make_capital(cells)
    n20_check = capital.pop("_n20_analytical")
    dividends = make_dividends(n20_check)
    payload = {
        "schema": SCHEMA, "meta": make_meta(), "market": make_market(cap, median), "fair_value": fair_value,
        "layers": {"analytical": la, "market_implied": lm, "macro_neutral": ln, "headline_mix": headline_mix},
        "grid": {"world_order": WORLDS, "regime_order": REGIMES, "scenario_order": SCEN, "years": YEARS, "basis": "engine", "cells": cells},
        "variance": {"price": {"world": 0.438, "regime": 0.421, "scenario": 0.058, "interaction": 0.083},
                     "method": "доли дисперсии цены клеток под вероятностями слоя «свой взгляд»: главные эффекты осей сетки и остаток"},
        "worlds": make_worlds(by_world, cells), "regimes": make_regimes(), "capital": capital, "dividends": dividends,
        "paths": make_paths(capital["mix"], cells), "nii": make_nii(), "guidance": make_guidance(),
        "governance": {"discount": GOV, "components": [
            {"id": "related_parties", "name": "Сделки со связанными сторонами", "value": 0.0, "sign": 1,
             "basis": "сделки группы со связанными сторонами раскрыты и идут по рыночным условиям; опоры для числа нет — 0"},
            {"id": "capital_allocation", "name": "Распределение капитала вне основного бизнеса", "value": 0.0, "sign": 1,
             "basis": "пакет и долг под него заданы явно строкой дохода пакета; в дисконт не входят"},
            {"id": "liquidity_listing", "name": "Ликвидность и листинг", "value": 0.0, "sign": 1, "basis": "≈0: ликвидная бумага первого уровня"}],
            "sum_signed": GOV, "price_at_low": r(central), "price_at_high": r(central * 0.9)},
        "reverse_dcf": make_reverse(central, cap), "judgements": {"rows": make_judgement_rows(judg, share_of, central),
                                                                 "off_band_shift": {"rub": 0.0, "limit": STEP / 2, "axes": 0}},
        "next_report": make_next_report(median, central), "nowcast": make_nowcast(n20_check), "indicators": make_indicators(),
        "calendar": make_calendar(), "history": make_history(), "checks": make_checks(capital["capital_gap"]), "inputs": make_inputs(),
        "live": make_live(), "changes": make_changes(median, central), "valuation_history": make_valuation_history(median), "book": make_book(central),
    }
    seal(payload)
    return payload


def make_meta():
    return {
        "generated_at": "2026-10-07T16:05:12+00:00", "published_at": "2026-10-07T16:07:40+00:00", "valuation_date": VDATE,
        "facts_date": FACTS_DATE, "book_version": BOOK, "book_date": "2026-10-06", "book_tag": f"book-{BOOK}",
        "engine_commit": "7a1c0d9b2a7e4c3f8e6d1a0b9c8d7e6f5a4b3c2d", "fast": False, "payload_sha256": None,
        "previous_sha256": "4b0e4f6a1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f", "bytes": None,
        "company": {"name": "Т-Технологии", "tickers": TICKERS, "main_ticker": MAIN, "share_classes": [{"ticker": MAIN, "class": "ordinary"}],
                    "cbr_regnum": 2673, "fiscal_year_end": "12-31"},
        "shares": {"issued_mln": N_ISS, "outstanding_mln": N_OUT,
                   "by_ticker": {MAIN: {"issued_mln": N_ISS, "treasury_mln": N_TREASURY, "outstanding_mln": N_OUT}}, "as_of": FACTS_DATE,
                   "src": "размещённые и собственные акции — МСФО за шесть месяцев 2026 года, примечание о капитале; после дробления 1 к 10",
                   "divisor_mln": N_DIV, "divisor_basis": "issued", "divisor_label": BASIS_LABELS["divisor"],
                   "depositary_block_mln": 112.4, "economic_treasury_mln": 0.0,
                   "corporate_actions": [
                       {"date": "2024-12-27", "kind": "issue", "title": "Дополнительный выпуск под присоединение банка"},
                       {"date": SPLIT_DATE, "kind": "split", "title": "Дробление акций 1 к 10", "factor": SPLIT},
                       {"date": "2026-08-11", "kind": "buyback_program", "title": "Программа выкупа до 5 % капитала"},
                       {"date": "2026-10-01", "kind": "deal", "title": "Объявлена покупка доли в расчётном банке для бизнеса"}]},
        "basis_labels": dict(BASIS_LABELS), "period_unit": "quarter", "input_unit": "month",
        "terms": dict(TERMS),
        "anchor_period": "2026Q2", "first_period": "2026Q3", "last_period": "2036Q4", "horizon": ["2026Q3", "2036Q4"],
        "open_period": "2026Q4", "periods_closed": 1, "elapsed": 1.076, "book_first_period_closed": False,
        "curve_as_of": "2026-10-02", "basis": "ifrs", "step": "quarter", "day_count": "act365", "governance_discount": GOV}


# ── рынок ──
# экс-даты за 12 месяцев до даты оценки: период прибыли, DPS, день
EX_DATES = [("2025Q3", 3.6, "2026-01-08"), ("2025Q4", 4.5, "2026-05-25"), ("2026Q1", 4.6, "2026-08-10")]


def make_market(cap, median):
    days = trading_days("2025-10-08", VDATE)
    x, closes = 318.0, []
    for day in days:
        x *= math.exp(RNG.gauss(-0.0004, 0.0125))
        x -= sum(dps for _p, dps, ex in EX_DATES if ex == day)
        closes.append(x)
    k = PRICE / closes[-1]
    full = [(dd, r(c * k)) for dd, c in zip(days, closes)]
    full[-1] = (VDATE, PRICE)
    thin = full[::2] + ([] if full[::2][-1][0] == VDATE else [full[-1]])
    lo, hi = min(full, key=lambda p: p[1]), max(full, key=lambda p: p[1])
    ratio = lambda name, value, as_of=FACTS_DATE: {"name": name, "value": value, "as_of": as_of}  # noqa: E731
    peer = lambda t, name, price, pcap, bv, ni, roe, dy, cr, bv_date=FACTS_DATE, src="МСФО за шесть месяцев 2026 года": {  # noqa: E731
        "ticker": t, "name": name, "price": price, "price_date": VDATE if price else None, "cap": pcap, "bv": bv, "bv_date": bv_date, "ni_ltm": ni,
        "pb": r(pcap / bv, 4) if pcap else None, "pe": r(pcap / ni, 4) if pcap else None, "roe_ltm": roe, "dividend_yield": dy, "capital_ratio": cr,
        "basis": "МСФО группы", "src": src, "status": "live" if price else "missing", "reason": None if price else "живой цены нет: торги по бумаге не велись в день оценки"}
    peers = [peer(MAIN, "Т-Технологии", PRICE, cap, 757.0, 198.1, 0.2812, r(16.2 / PRICE, 4), ratio("Н20.0", 0.1293), src="выпуск и факты капитала"),
             peer("SBER", "Сбербанк", 301.4, 6742.5, 8387.2, 1745.1, 0.2254, 0.1249, ratio("Н20.0", 0.151)),
             peer("VTBR", "ВТБ", 71.35, 383.6, 2170.4, 571.2, 0.188, 0.0, ratio("Н20.0", 0.098)),
             peer("BSPB", "Банк Санкт-Петербург", 318.2, 141.7, 212.9, 49.1, 0.231, 0.118, ratio("Н1.0", 0.187, "2026-09-01"), "2026-03-31", "МСФО за три месяца 2026 года"),
             peer("CBOM", "МКБ", None, None, 351.0, 31.4, 0.089, None, ratio("Н1.0", 0.121, "2026-09-01"))]
    peers[0]["basis"] = "МСФО группы; прибыль — операционная (определение эмитента)"
    history = [{"date": f"{2024 + (9 + i) // 12}-{(9 + i) % 12 + 1:02d}-28", "median": r(352 + 9 * math.sin(i / 3) + 0.9 * i, 1), "n": 9 + (i % 4)} for i in range(24)]
    return {
        "price": PRICE, "price_date": VDATE,
        "prices": {MAIN: {"price": PRICE, "date": VDATE, "time": "18:49", "source": "Мосбиржа, TQBR", "status": "live", "book_price": 268.4}},
        "cap": cap, "cap_by_ticker": {MAIN: cap},
        "multiples": {"pb": r(cap / BV_V, 4), "pb_reported": r(cap / 757.0, 4), "pe_ltm": r(cap / 198.1, 4), "pe_fwd": r(cap / NI_PATH[0], 4),
                      "dividend_yield_ltm": {MAIN: r(LTM_DPS / PRICE, 6)},
                      "dividend_yield_fwd": {MAIN: r((4.7 + 5.02 + 5.31 + 5.55) / PRICE, 6)}, "bv_per_share": r(BV_V * 1000 / N_DIV), "basis": "ifrs"},
        "price_history": {MAIN: [{"date": dd, "close": c} for dd, c in thin]},
        "price_min": {MAIN: {"date": lo[0], "close": lo[1]}}, "price_max": {MAIN: {"date": hi[0], "close": hi[1]}},
        "ex_dividend": [{"date": ex, "dps": dps, "year": int(p[:4]), "period": p, "label": label_of(p)} for p, dps, ex in EX_DATES],
        "peers": {"as_of": "2026-10-06", "basis": "МСФО групп на отчётную дату аналога; капитал — акционеров без бессрочных инструментов; прибыль — "
                  "акционерам за четыре квартала (у эмитента — операционная); ROE — к среднему капиталу; дивиденд — с отсечкой за 12 месяцев; "
                  "норматив — как раскрыт; цены — закрытия дня оценки", "subject_ticker": MAIN, "rows": peers},
        "brokers": {"as_of": "2026-10-06", "source": "T-Invest: консенсус-прогнозы, агрегаты", "n": 12, "median": 385.0, "min": 310.0, "max": 460.0,
                    "recommendations": {"buy": 11, "hold": 1, "sell": 0}, "history": history}}


def make_worlds(by_world, cells):
    key = {"N": [0.152, 0.1225, 0.0975, 0.085, 0.08], "H": [0.155, 0.14, 0.1275, 0.1175, 0.1125, 0.105], "M": [0.152, 0.1515, 0.169, 0.1745, 0.175, 0.17]}
    cpi = {"N": [0.065, 0.053, 0.042, 0.04], "H": [0.066, 0.0665, 0.0625, 0.057, 0.055], "M": [0.065, 0.056, 0.074, 0.097, 0.105, 0.108]}
    curve = {"1": {"N": 0.1316, "H": 0.1388, "M": 0.136}, "3": {"N": 0.1155, "H": 0.1443, "M": 0.1548}, "5": {"N": 0.1061, "H": 0.1405, "M": 0.1614},
             "10": {"N": 0.0985, "H": 0.1344, "M": 0.1646}}
    rows = {}
    for w in WORLDS:
        k = key[w] + [key[w][-1]] * (NY - len(key[w]))
        c = cpi[w] + [cpi[w][-1]] * (NY - len(cpi[w]))
        ws = [x for x in cells if x["world"] == w]
        growth = lambda a, lt: yearly(ramp(a, lt[w], k=3))  # noqa: E731
        rows[w] = {
            "name": WORLD_NAMES[w], "weights": {"analytical": W_A[w], "market_implied": W_MI[w], "macro_neutral": W_N[w]},
            "key_rate": yearly(k), "cpi": yearly(c), "real_key": yearly([(1 + a) / (1 + b) - 1 for a, b in zip(k, c)]),
            "ofz": {t: curve[t][w] for t in curve}, "zero_curve": {**{t: curve[t][w] for t in curve}, "LT": {"N": 0.09, "H": 0.127, "M": 0.167}[w]},
            "lt_inflation": {"N": 0.04, "H": 0.055, "M": 0.098}[w],
            "k_t": r(sum(P_REG[x["regime"]] * P_SC[x["regime"]][x["scenario"]] * x["k_t"] for x in ws), 4), "g_t": G_T_W[w],
            "price": by_world[w]["price"], "v0": by_world[w]["v0"],
            "credit_growth": {"corporate": growth(0.09, {"N": 0.075, "H": 0.08, "M": 0.12}), "mortgage": growth(0.07, {"N": 0.08, "H": 0.075, "M": 0.115}),
                              "retail_other": growth(0.12, {"N": 0.08, "H": 0.08, "M": 0.12})},
            "funds_growth": {"retail": growth(0.11, {"N": 0.075, "H": 0.085, "M": 0.12}), "corporate": growth(0.11, {"N": 0.075, "H": 0.085, "M": 0.12})},
            "transmission": {"N": 0.094, "H": 0.071, "M": 0.052}[w]}
    return {"order": WORLDS, "rows": rows,
            "source": {"record": "worlds_source.json", "origin": "worlds-850 book-1.7", "record_asof": "2026-10-05", "curve_date": "2026-10-02",
                       "sha256": "5196567d5200b5599efd0989de6ed8c8461d56c5c5dda244ab7d622303969fec"},
            "overlay": {"file": "worlds_bank.json", "sha256": "2d3270ef8a1b9d2e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e"}}


def make_regimes():
    cor = {"soft": [0.05, 0.047, 0.046, 0.047, 0.048], "norm": [0.056, 0.056, 0.056, 0.056, 0.056],
           "downturn": [0.058, 0.07, 0.066, 0.06, 0.062], "crisis": [0.058, 0.095, 0.074, 0.06, 0.066]}
    nim = {"soft": [0.0, 0.002, 0.003], "norm": [0.0, 0.0, 0.0], "downturn": [0.0, -0.004, -0.004, -0.002], "crisis": [0.0, -0.008, -0.004]}
    near = [("2026Q3", 0.0078), ("2026Q4", 0.0073), ("2027Q1", 0.0055), ("2027Q2", 0.0037), ("2027Q3", 0.0018), ("2027Q4", 0.0)]
    lga = {"soft": [0.0, 0.02, 0.02, 0.0], "norm": [0.0], "downturn": [0.0, -0.05, -0.05, 0.0], "crisis": [0.0, 0.0, 0.0, 0.02, 0.0]}
    post = {"soft": 0.158, "norm": 0.409, "downturn": 0.291, "crisis": 0.142}
    bridge = 0.0006
    series = lambda vals: [{"year": 2026 + i, "value": v} for i, v in enumerate(vals)]  # noqa: E731
    rows = {g: {"title": REGIME_NAMES[g], "prior": P_REG[g], "posterior": post[g], "cor": series(cor[g][:4]),
                "cor_engine": series([r(v + bridge, 4) for v in cor[g][:4]]), "cor_lt": cor[g][4], "cor_lt_engine": r(cor[g][4] + bridge, 4),
                "nim_shift": series(nim[g]), "nim_shift_lt": nim[g][-1], "loan_growth_adj": series(lga[g])} for g in REGIMES}
    rows["crisis"]["crisis"] = {"shock_year": 2027, "shock_year_offset": 1, "one_off_loss": {"period": "2027Q1", "amount": -40.0},
                                "loan_growth_override": [{"year": 2027, "value": 0.02}, {"year": 2028, "value": 0.06}],
                                "cor_quarters": [{"period": f"2027Q{i + 1}", "value": v} for i, v in enumerate((0.118, 0.102, 0.088, 0.072))]}
    exp_lt = sum(post[g] * rows[g]["cor_lt"] for g in REGIMES)
    cor_m = [None] * 2 + [0.058, 0.061, 0.064, 0.066, 0.071, 0.066, 0.062, 0.058, 0.056, 0.051, 0.049, 0.047]
    nim_m = [None] * 2 + [0.118, 0.116, 0.113, 0.111, 0.104, 0.107, 0.109, 0.112, 0.113, 0.114, 0.115, 0.116]
    hist = [{"period": f"{2023 + i // 4}Q{i % 4 + 1}", "cor_mgmt": a, "cor_engine": None if a is None else r(a + bridge, 4),
             "nim_mgmt": b, "nim_engine": None if b is None else r(b - 0.0012, 4)} for i, (a, b) in enumerate(zip(cor_m, nim_m))]
    return {
        "reference_world": "M", "order": REGIMES, "basis": "engine", "cor_basis": "mgmt",
        "cor_bridge": {"method": "движок = упр. + сдвиг моста (отчётные кварталы года якоря, резервы к средней сумме кредитных книг)", "value": bridge},
        "rows": rows, "near_nim_shift": [{"period": q, "value": v} for q, v in near],
        "expected": {"cor_lt": r(exp_lt, 5), "cor_lt_engine": r(exp_lt + bridge, 5), "nim_shift_lt": r(sum(post[g] * rows[g]["nim_shift_lt"] for g in REGIMES), 5)},
        "update": {"cor": {"sigma_pp": 0.009, "rho_q": 0.5}, "nim": {"sigma_pp": 0.004, "rho_q": 0.7}, "max_shift_pp": 0.05, "window_obs": 4, "floor_share": 0.33,
                   "observations": [{"period": "2026Q2", "basis": "mgmt", "cor": 0.047, "nim": 0.116, "se_cor": 0.0, "se_nim": 0.0,
                                     "cor_engine": 0.0476, "nim_engine": 0.1148, "posterior_after": post}]},
        "history": hist,
        "reference_class": {"episodes": [
            {"id": "2008", "name": "Кризис 2008–2009", "period": "2008Q4–2010Q1", "cor_peak": 0.17, "quarters": 6, "nim_drop": -0.02, "src": "годовые отчёты розничных банков"},
            {"id": "2014", "name": "Санкции и девальвация", "period": "2014Q4–2015Q4", "cor_peak": 0.155, "quarters": 5, "nim_drop": -0.03, "src": "МСФО 2015"},
            {"id": "2020", "name": "Пандемия", "period": "2020Q1–2020Q4", "cor_peak": 0.104, "quarters": 4, "nim_drop": -0.012, "src": "МСФО 2020"},
            {"id": "2023", "name": "Перегрев розницы", "period": "2023Q3–2024Q4", "cor_peak": 0.071, "quarters": 6, "nim_drop": -0.014, "src": "МСФО 2024"}],
            "shares": [{"regime": g, "book": P_REG[g], "class": s, "lo": lo, "hi": hi} for g, s, lo, hi in (
                ("soft", 0.17, 0.06, 0.39), ("norm", 0.44, 0.25, 0.65), ("downturn", 0.22, 0.09, 0.45), ("crisis", 0.17, 0.06, 0.39))]}}


# ── капитал: сценарии, путь нормативов, требование с глиссадой, рост, «цена правила» ──
def make_capital(cells):
    cons = [0.0125, 0.01875] + [0.025] * (NY - 2)
    sifi = {"schedule": [0.0, 0.0025, 0.005] + [0.01] * (NY - 3), "mid": [0.0, 0.0025, 0.005, 0.0075] + [0.01] * (NY - 4),
            "strict": [0.0, 0.005, 0.0075] + [0.01] * (NY - 3)}
    ccyb = {"schedule": [0.0025] * NY, "mid": [0.0025, 0.0025] + [0.005] * (NY - 2), "strict": [0.0025, 0.005] + [0.01] * (NY - 2)}
    ded = [0.0] * NY
    buffer_ = 0.015
    scen = {}
    for s in SCEN:
        floor20 = [0.08 + a + b + c for a, b, c in zip(cons, sifi[s], ccyb[s])]
        floor11 = [0.045 + a + b + c for a, b, c in zip(cons, sifi[s], ccyb[s])]
        scen[s] = {"title": SCEN_NAMES[s], "p_given_regime": {g: P_SC[g][s] for g in REGIMES}, "mass": r(sum(P_REG[g] * P_SC[g][s] for g in REGIMES), 6),
                   "conservation": cons, "sifi": sifi[s], "ccyb": ccyb[s], "deduction_n20": ded, "deduction_n11": ded,
                   "floor20": [r(x, 4) for x in floor20], "floor11": [r(x, 4) for x in floor11],
                   "req20": [r(x + buffer_, 4) for x in floor20], "req11": [r(x + buffer_, 4) for x in floor11]}
    by = {}
    for s in SCEN:                                     # норматив сценария — ожидание нормативов клеток под весами «свой взгляд»
        own = [c for c in cells if c["scenario"] == s]
        tot = sum(c["p_analytical"] for c in own)
        by[s] = {}
        for k in ("n20", "n11"):
            by[s][k] = [r(sum(c["p_analytical"] * c["annual"][k][i] for c in own) / tot, 4) for i in range(NY)]
            for q, name in ((0.1, "p10"), (0.9, "p90")):
                by[s][f"{k}_{name}"] = [wq([(c["annual"][k][i], c["p_analytical"]) for c in own], q) for i in range(NY)]
    mass = {s: scen[s]["mass"] for s in SCEN}
    p_mix = [LAM * c["p_analytical"] + (1 - LAM) * c["p_neutral"] for c in cells]
    mix = {k: [r(sum(w * c["annual"][k][i] for w, c in zip(p_mix, cells)), 4) for i in range(NY)] for k in ("n20", "n11")}
    for k in ("req20", "req11", "floor20", "floor11"):
        mix[k] = [r(sum(mass[s] * scen[s][k][i] for s in SCEN), 4) for i in range(NY)]
    gap_cells = [c for c in cells if "capital_gap" in c["flags"]]
    start = 0.1293
    rows = [("dividend_accrual", "Дивиденды: вычет и начисление", -0.0046, -24.3), ("profit", "Операционная прибыль акционеров", 0.0211, 111.6),
            ("oci_other", "OCI и прочие движения капитала", 0.0004, 2.1), ("rwa_growth", "Рост RWA", -0.0182, 742.0),
            ("deductions", "Рост вычетов вместе с RWA, поправка и вычеты сценария", -0.0011, -5.8)]
    rows.append(("other", "Прочее (фонд FVOCI, инструменты капитала, неаудированная прибыль)", r(mix["n20"][0] - start - sum(x[2] for x in rows), 6), 3.4))

    # требование с глиссадой: известная ступень минимума набирается заранее, по 0,25 п.п. за квартал за 4 квартала до ступени
    glide, look = 0.0025, 4
    year_of = lambda p: YEARS.index(int(p[:4]))  # noqa: E731

    def stepped(arr, glided):
        level = [arr[year_of(p)] for p in PERIODS]
        ahead = level + [arr[min(NY - 1, year_of(PERIODS[-1]) + 1)]] * look
        return [r(max([ahead[i]] + [ahead[i + k] - glide * k for k in range(1, look + 1)]) if glided else ahead[i], 4) for i in range(QUARTERS)]

    n20_q = [r(mix["n20"][year_of(p)] + 0.0007 * (3 - (2 + i) % 4), 4) for i, p in enumerate(PERIODS)]
    # отчётный второй норматив ниже норматива с прибылью периода на неаудированную прибыль: «пила» внутри года
    n11_star_q = [r(mix["n11"][year_of(p)] + 0.0007 * (3 - (2 + i) % 4), 4) for i, p in enumerate(PERIODS)]
    n11_q = [r(v - 0.0042 * (int(p[-1]) % 4), 4) for v, p in zip(n11_star_q, PERIODS)]
    requirement = {
        "periods": PERIODS,
        "mix": {"n20": n20_q, "n11": n11_q, "n11_star": n11_star_q,
                "req20_glide": stepped(mix["req20"], True), "req11_glide": stepped(mix["req11"], True),
                "req20": stepped(mix["req20"], False), "req11": stepped(mix["req11"], False)},
        "by_scenario": {s: {"req20_glide": stepped(scen[s]["req20"], True), "req11_glide": stepped(scen[s]["req11"], True)} for s in SCEN},
        # концы лет: ступень следующего года уже набирается — требование с глиссадой выше требования года
        "years_mix": {"req20_glide": [r(max(v, mix["req20"][min(i + 1, NY - 1)] - glide), 4) for i, v in enumerate(mix["req20"])],
                      "req11_glide": [r(max(v, mix["req11"][min(i + 1, NY - 1)] - glide), 4) for i, v in enumerate(mix["req11"])],
                      "n11_star": [r(v + 0.0126, 4) for v in mix["n11"]]},
        "lookahead_quarters": look, "glide_pp_per_quarter": glide, "compare": {"n20": "n20", "n11": "n11_star"},
        "notes": {"n11_star": "с прибылью периода — его сравнивает с требованием правило роста",
                  "n11": "отчётный, без прибыли неаудированного периода — справочно"}}

    potential = [0.206, 0.248, 0.221, 0.196, 0.172, 0.151, 0.134, 0.121, 0.112, 0.106, 0.102]    # рост года якоря — к факту конца прошлого года
    cut = [0.0, 0.018, 0.049, 0.076, 0.095, 0.107, 0.115, 0.12, 0.123, 0.125, 0.126]              # доля урезанного копится: навёрстывания нет
    step = [0.0, 0.018, 0.031, 0.027, 0.019, 0.012, 0.008, 0.005, 0.003, 0.002, 0.001]              # урезано за год
    actual = [r(p - c * 0.9, 4) for p, c in zip(potential, step)]
    scale = {"schedule": 0.3, "mid": 1.0, "strict": 2.1}
    growth = {
        "years": YEARS, "potential": potential, "actual": actual, "cut_share": cut,
        "catch_up": [0.0] * NY,
        "lam_min": [1.0, 0.62, 0.48, 0.71, 0.84, 0.93, 1.0, 1.0, 1.0, 1.0, 1.0],
        "p_cut": [0.0, 0.412, 0.538, 0.421, 0.287, 0.164, 0.092, 0.047, 0.021, 0.008, 0.0],
        "by_scenario": {s: {"actual": [r(p - c * 0.9 * scale[s], 4) for p, c in zip(potential, step)],
                            "cut_share": [r(c * scale[s], 4) for c in cut]} for s in SCEN},
        "quarters": {"periods": PERIODS, "lam": [1.0, 1.0, 0.91, 0.74, 0.62, 0.68, 0.57, 0.48, 0.55, 0.66, 0.71, 0.78, 0.82, 0.88]},
        "order": "dividend_first", "min_growth_scale": 0.0, "catch_up_rate": 0.0}
    # цена правила книги с записью сухого перевывода развилок (М§14.5): разности с точкой и медианой книги, медианы в рублях нет
    rule_price = {"rows": [
        {"key": "unconstrained", "title": "Без ограничения роста капиталом", "point": 372.4, "d_point": 11.64, "d_median": 9.9, "capital_gap_mass": 0.186, "current": False},
        {"key": "dividend_first", "title": "Дивиденд по политике, рост — остаток", "point": 360.76, "d_point": 0.0, "d_median": 0.0, "capital_gap_mass": 0.0105, "current": True},
        {"key": "growth_first", "title": "Сначала уступает дивиденд", "point": None, "d_point": None, "d_median": None, "capital_gap_mass": None, "current": False,
         "why": "без цены: книга под замыкание не перевыводится — концы осей-связок расходятся с правилом листа"}]}
    return {
        "titles": dict(TITLES),
        "anchor": {"as_of": FACTS_DATE, "n20": start, "n20_pre_dividend": False, "n20_post_dividend": 0.1271,
                   "n11_bank": {"value": 0.106, "as_of": FACTS_DATE}, "rwa": 5287.3, "bv_common": 757.0, "at1": 0.0, "t2": 123.18,
                   "fvoci_reserve": -6.4, "ded20": 197.99, "ded11": 197.99, "req20_now": r(mix["req20"][0], 4), "req11_now": r(mix["req11"][0], 4),
                   "n20_headroom": r(0.1271 - r(mix["req20"][0], 4), 4), "n11_headroom": r(0.106 - r(mix["req11"][0], 4), 4),
                   # правило роста сравнивает норматив с требованием с глиссадой: запас якоря — и до него, к концу первого квартала сетки
                   "req20_glide_next": requirement["mix"]["req20_glide"][0], "req20_glide_period": PERIODS[0],
                   "n20_headroom_glide": r(0.1271 - requirement["mix"]["req20_glide"][0], 4),
                   "basis": "ifrs", "estimated": True,
                   "src": "Н20.0 и Н20.1 банковской группы на 30 июня 2026 года — оценка по нормативам банка (форма 0409135) и их разности с нормативами "
                          "группы на последнюю общую дату: форма 0409805 на эту дату ещё не вышла"},
        "observed": {"n1_0": None, "n1_1": 0.1042, "n1_2": None, "as_of": "2026-03-31", "source": "форма 0409805 ЦБ, банковская группа"},
        "policy_threshold": 0.0, "minimum": {"n20_0": 0.08, "n1_1": 0.045}, "mgmt_buffer": {"n20_0": buffer_, "n1_1": buffer_},
        "years": YEARS, "scenarios": scen, "by_scenario": by, "mix": mix,
        "capital_gap": {"mass": r(sum(c["p_analytical"] for c in gap_cells), 6), "cells": len(gap_cells),
                        "cell_list": [f"{c['world']}/{c['regime']}/{c['scenario']}" for c in gap_cells][:10], "first_period": "2027Q2",
                        "by_scenario": {s: r(sum(c["p_analytical"] for c in gap_cells if c["scenario"] == s), 6) for s in SCEN}},
        "_n20_analytical": r(sum(c["p_analytical"] * c["annual"]["n20"][0] for c in cells), 4),
        "bridge": {"from": "2026Q2", "to": "2026Q4", "start": start, "end": mix["n20"][0], "rows": [{"key": k, "title": t, "pp": pp, "amount": a} for k, t, pp, a in rows]},
        "requirement": requirement, "growth": growth, "rule_price": rule_price}


def make_dividends(n20_check):
    hist = [{"year": int(p[:4]), "period": p, "label": label_of(p), "dps": dps, "dps_pre_split": pre, "split_factor": SPLIT, "dps_preferred": None,
             "pool": pool, "payout_ratio": None, "record_date": rec, "ex_date": rec, "pay_date": pay, "ni_shareholders": None,
             "src": f"решение внеочередного общего собрания акционеров от {date.fromisoformat(dec).strftime('%d.%m.%Y')} (раскрытие эмитента); сверено с брокерским календарём дивидендов"
             if p != "2025Q4" else "решение годового общего собрания акционеров от 14.05.2026 (раскрытие эмитента); сверено с брокерским календарём дивидендов"}
            for p, dps, pre, dec, rec, pay, pool in DECISIONS]
    # решения после дробления: квартал стоит и в истории, и в реестре
    hist += [{"year": int(p[:4]), "period": p, "label": label_of(p), "dps": dps, "dps_pre_split": None, "split_factor": 1, "dps_preferred": None,
              "pool": r(dps * N_ISS / 1000), "payout_ratio": None, "record_date": rec, "ex_date": rec, "pay_date": pay, "ni_shareholders": None,
              "src": f"решение внеочередного общего собрания акционеров от {date.fromisoformat(dec).strftime('%d.%m.%Y')} (раскрытие эмитента); "
                     "сверено с брокерским календарём дивидендов"} for p, dps, dec, rec, _buy, pay, _st in REGISTER]
    register = [{"year": int(p[:4]), "period": p, "label": label_of(p), "decided_date": dec, "dps": dps, "amount": r(dps * N_ISS / 1000),
                 "record_date": rec, "last_buy_date": buy, "ex_date": rec, "pay_date": pay, "status": st, "in_bridge": False,
                 "sources": ["документ эмитента", "T-Invest"] + (["Интерфакс"] if st == "declared" else [])} for p, dps, dec, rec, buy, pay, st in REGISTER]
    # путь квартальных DPS: открытые кварталы прибыли без записи, решение по которым приходится на первые 14 кварталов сетки
    lag = {1: 2, 2: 2, 3: 1, 4: 2}
    done = {"2026Q1": ("2026Q3", "2026Q3"), "2026Q2": ("2026Q4", "2026Q4")}      # квартал решения и квартал выплаты
    quarters = [{"period": p, "decision_period": done[p][0], "pay_period": done[p][1], "dps": dps, "dps_p10": dps, "dps_p90": dps,
                 "dps_policy": DPS_POLICY_DONE[p], "amount": r(dps * N_ISS / 1000), "p_cut": 0.0, "p_zero": 0.0, "declared": True}
                for p, dps, *_ in REGISTER]
    for i in range(13):
        y, q = 2026 + (2 + i) // 4, (2 + i) % 4 + 1
        idx = 1 + i + lag[q]                              # квартал сетки, в котором принимается решение
        if idx > QUARTERS:
            break
        period = f"{y}Q{q}"
        policy = DPS_POLICY_Q.get(period, 5.31 * 1.045 ** (i - 1))
        shock = period in SHOCK_Q
        mean = Q_MEAN(period, policy)
        quarters.append({"period": period, "decision_period": PERIODS[idx - 1], "pay_period": PERIODS[min(idx + (q == 3), QUARTERS) - 1],
                         "dps": r(mean, 4), "dps_p10": 0.0 if shock else r(mean * 0.82, 4), "dps_p90": r(policy * 1.02, 4), "dps_policy": r(policy, 4),
                         "amount": r(mean * N_ISS / 1000), "p_cut": r(0.058 if shock else 0.021, 6), "p_zero": 0.15 if shock else 0.0, "declared": False})
    model = []
    for i, y in enumerate(YEARS[:-1]):
        dps = DPS_YEAR[i] * (0.9 if i == 1 else 0.985) if i else DPS_MEAN_0
        model.append({"year": y, "pay_year": y + 1, "dps": r(dps, 4), "dps_p10": r(dps * (0.55 if i == 1 else 0.86), 4), "dps_p90": r(DPS_YEAR[i] * 1.05, 4),
                      "dps_policy": r(DPS_YEAR[i], 4), "payout": 0.26, "amount": r(dps * N_ISS / 1000), "p_cut": r(0.064 if i in (1, 2) else 0.027, 6),
                      "p_zero": 0.0, "declared": False})
    return {
        "policy": {"name": "Положение о дивидендной политике (редакция 2, совет директоров 20.03.2025)",
                   "text": "До 30 % чистой прибыли по МСФО за год; решения о выплате — ежеквартально, с учётом потребности в капитале и требований "
                           "Банка России к достаточности капитала",
                   "doc": "dividend_policy.pdf", "sha256": "a186aa17c0de4b1f8a9e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6b7a8f9e0d1c2b3a", "approved": "2025-03-20",
                   "valid_until": None, "valid_until_note": "срок действия в Положении не ограничен", "base": "ifrs_ni_shareholders",
                   "payout": [{"year": y, "value": 0.26} for y in YEARS], "metric": "n20_0", "threshold": 0.0, "steps": [],
                   "shortfall_rule": "residual_above_requirement", "deduct_at1_after_tax": False, "divisor": "issued",
                   "excess": {"from_profit_year": 2030, "epsilon": 0.25, "ramp_years": 3}, "crisis": {"skip_in_shock_year": True, "catch_up": False},
                   "history_test": "cap", "cap": 0.3, "frequency": "quarterly", "base_window_quarters": 4,
                   "decision_lag_quarters": {"1": 2, "2": 2, "3": 1, "4": 2}},
        "ladder": [{"key": "policy", "title": "Выплата по политике", "payout": 0.26, "current": True,
                    "condition": "доля прибыли по политике; при нехватке капитала сначала замедляется рост портфеля, дивиденд снижается только при нулевом росте"}],
        "register": register, "history": hist, "formula_check": [],
        "cap_check": [{"year": 2025, "pool": 39.97, "ni_shareholders": 174.43, "share": r(39.97 / 174.43, 6), "cap": 0.3, "complete": True, "ok": True},
                      {"year": 2026, "pool": 24.95, "ni_shareholders": 83.1, "share": r(24.95 / 83.1, 6), "cap": 0.3, "complete": False, "ok": None}],
        "model": model, "model_quarters": quarters,
        "next_expected": {"year": 2026, "period": "2026Q2", "label": label_of("2026Q2"), "status": "declared", "dps": 4.7, "dps_policy": 4.6713,
                          "dps_mean": 4.7, "dps_p10": 4.7, "dps_p90": 4.7, "p_cancel": 0.0, "record_date": "2026-10-12", "record_date_est": None,
                          "record_date_note": None, "last_buy_date": "2026-10-09", "pay_date_est": "2026-10-26", "yield": {MAIN: r(4.7 / PRICE, 6)},
                          "yield_period": "quarter", "condition": {"metric": "n20_0", "threshold": 0.0, "n20_expected": n20_check, "p_limited": 0.0}},
        "yield_ltm": {MAIN: r(LTM_DPS / PRICE, 6)}, "yield_ltm_periods": list(LTM_PERIODS), "amount_basis": "issued", "basis": "ifrs"}


def make_paths(mix, cells):
    rows, tree = [], []
    bv_prev, assets_prev = 757.0, 5760.0
    for i, y in enumerate(YEARS):
        g = NI_PATH[i] / NI_PATH[0]
        nii, fees, ins, other = 640.0 * g ** 0.93, 196.0 * g ** 1.05, 52.0 * g, -14.0 * g ** 0.5
        noncore = 10.13 * (1 - 0.06 * min(i, 6))
        llp = 178.0 * g ** 0.92 * (1.22 if i == 1 else 1)
        one_off = -6.0 if i == 1 else 0.0
        ni = NI_PATH[i] / 0.976                         # вся прибыль; акционерам — без доли неконтролирующих
        pbt = (ni - 2.0) / 0.75
        opex = nii - llp + fees + ins + other + noncore + one_off - pbt
        tax = pbt - ni
        bv_end = BV_PATH[i]
        assets_end = assets_prev * (1.21 - 0.012 * min(i, 8) if i else 1.09)
        avg_bv, avg_a = (bv_prev + bv_end) / 2, (assets_prev + assets_end) / 2
        income = nii + fees + ins + other + noncore
        rows.append({"year": y, "fact_quarters": 2 if i == 0 else 0, "nii": r(nii), "nim": r(0.1058 - 0.0012 * min(i, 4), 4),
                     "nim_mgmt": r(0.107 - 0.0012 * min(i, 4), 4), "fees": r(fees), "fees_growth": r(0.0 if i == 0 else 0.2 - 0.012 * min(i, 9), 4),
                     "insurance": r(ins), "other": r(other), "noncore": r(noncore), "opex": r(opex), "cir": r(opex / income, 4),
                     "cir_mgmt": r(opex / income + 0.006, 4), "llp": r(llp), "cor": r(0.0566 + (0.011 if i == 1 else 0), 4),
                     "cor_mgmt": r(0.056 + (0.011 if i == 1 else 0), 4), "fvc": 0.0, "one_off": r(one_off), "pbt": r(pbt), "tax": r(tax), "ni": r(ni),
                     "ni_sh": r(NI_PATH[i]), "oci": 1.5, "ci": r(ni + 1.5), "roe": r(NI_PATH[i] / avg_bv, 4), "roe_ci": r((NI_PATH[i] + 1.5) / avg_bv, 4),
                     "bv_end": r(bv_end), "rwa_end": r(5287.3 * (assets_end / 5760.0) ** 0.97), "n20_end": mix["n20"][i], "n11_end": mix["n11"][i],
                     "req20_end": mix["req20"][i], "floor20_end": mix["floor20"][i], "loans_end": r(3813.1 * (assets_end / 5760.0) ** 1.02),
                     "funds_end": r(4122.0 * (assets_end / 5760.0)), "assets_end": r(assets_end),
                     "dps": r(DPS_YEAR[i] * (0.9 if i == 1 else 0.985) if i else DPS_MEAN_0, 4) if i < NY - 1 else None,
                     "payout": 0.26 if i < NY - 1 else None,
                     "div_paid": r(4.5 * N_OUT / 1000 if i == 0 else DPS_YEAR[i - 1] * N_OUT / 1000)})
        parts = {k: r(v / avg_a, 6) for k, v in (("nii_to_assets", nii), ("fees_to_assets", fees), ("other_to_assets", ins + other + one_off),
                                                  ("noncore_to_assets", noncore), ("opex_to_assets", -opex), ("llp_to_assets", -llp),
                                                  ("tax_to_assets", -(tax + ni - NI_PATH[i])))}
        roa, lev = r(sum(parts.values()), 6), r(avg_a / avg_bv, 4)
        tree.append({"year": y, **parts, "roa": roa, "leverage": lev, "roe": r(roa * lev, 6)})
        bv_prev, assets_prev = bv_end, assets_end
    quarters = [{"period": p, "fact": False, "nii": r(165 + 6.5 * i), "nim": r(0.1153 - 0.0011 * min(i, 6), 4), "nim_mgmt": r(0.1165 - 0.0011 * min(i, 6), 4),
                 "llp": r(46 + 1.6 * i + (9 if 2 <= i <= 5 else 0)), "cor": r(0.0506 + (0.009 if 2 <= i <= 5 else 0), 4),
                 "cor_mgmt": r(0.05 + (0.009 if 2 <= i <= 5 else 0), 4), "fees": r(50 + 2.4 * i), "opex": r(106 + 4.2 * i),
                 "ni_sh": r(54 + 3.1 * i - (5 if 2 <= i <= 5 else 0)), "bv": r(742 + 43 * i),
                 "n20": r(mix["n20"][YEARS.index(int(p[:4]))] + 0.0007 * (3 - (2 + i) % 4), 4),
                 "n11": r(mix["n11"][YEARS.index(int(p[:4]))] + 0.0007 * (3 - (2 + i) % 4), 4),
                 "req20": mix["req20"][YEARS.index(int(p[:4]))], "floor20": mix["floor20"][YEARS.index(int(p[:4]))]} for i, p in enumerate(PERIODS)]
    k_path = [0.2105, 0.2011, 0.1936, 0.1884, 0.1851, 0.1832, 0.1822, 0.1817, 0.1814, 0.1813, 0.1812]
    fade = {"years": YEARS, "roe": [x["roe"] for x in rows], "bv_growth": [r(BV_PATH[i] / (BV_PATH[i - 1] if i else 757.0) - 1, 4) for i in range(NY)],
            "k": k_path, "roe_t_raw": 0.2063, "roe_t": 0.1952, "k_t": 0.1812, "g_t": 0.0738, "fade": 0.5}
    # на чём стоит заголовок: уровни 2030 года и дальше; смесь заголовка — средние её же годовых строк, прочие строки — рядом
    tail = [x for x in rows if x["year"] >= 2030]
    mean = lambda k: sum(x[k] for x in tail) / len(tail)  # noqa: E731
    point = {"nim": mean("nim_mgmt"), "cor": mean("cor_mgmt"), "cir": mean("cir_mgmt"), "loans_share": 0.7267}
    shifts = (("modal_cell", "Модальная клетка", 0.0085, -0.0011, -0.019, 0.0523), ("analytical", "Свой макро-взгляд", 0.0018, -0.0005, -0.006, 0.0163),
              ("point", "Смесь заголовка", 0.0, 0.0, 0.0, 0.0), ("macro_neutral", "Рыночные ставки как есть", -0.0017, 0.0005, 0.0054, -0.0143))
    levels = {"from_year": 2030, "to_year": YEARS[-1], "cell": "/".join(MODAL), "order": [k for k, *_ in shifts],
              "rows": {k: {"title": t, "nim": r(point["nim"] + a, 6), "cor": r(point["cor"] + b, 6), "cir": r(point["cir"] + c, 6),
                           "loans_share": r(point["loans_share"] + e, 6)} for k, t, a, b, c, e in shifts}, "window": WINDOW}
    cell = next(c for c in cells if (c["world"], c["regime"], c["scenario"]) == MODAL)
    modal = {"cell": "/".join(MODAL), "p_analytical": cell["p_analytical"], "p_point": r(LAM * cell["p_analytical"] + (1 - LAM) * cell["p_neutral"], 6),
             "price": cell["price"], "years": YEARS, "ni_sh": [r(v * (1.012 + 0.031 * min(i, 6))) for i, v in enumerate(NI_PATH)]}
    # путь фондирования: кредиты к средствам клиентов и доля оптового фондирования — якорь, смесь и модальная клетка
    ltf = [r(x["loans_end"] / x["funds_end"], 6) for x in rows]
    whs = [r(0.135 + 0.011 * min(i, 6), 6) for i in range(NY)]
    funding = {"years": YEARS, "cell": "/".join(MODAL), "anchor": {"loans_to_funds": 0.887, "wholesale_share": 0.135},
               "mix": {"loans_to_funds": ltf, "wholesale_share": whs},
               "modal_cell": {"loans_to_funds": [r(v + 0.012 * i, 6) for i, v in enumerate(ltf)], "wholesale_share": [r(v + 0.004 * i, 6) for i, v in enumerate(whs)]}}
    return {"mix": {"title": "смесь заголовка (λ книги)", "lambda": LAM}, "annual": rows, "quarters": quarters, "roe_tree": tree,
            "terminal": {"roe_t": 0.1952, "k_t": 0.1812, "g_t": 0.0738, "x_t": 21.6, "payout_t": r(1 - 0.0738 / 0.1952, 4), "fade": 0.5}, "fade": fade,
            "levels": levels, "modal_cell": modal, "funding": funding}


def make_nii():
    # ключ, название, сторона, опора, ρ, β, флаг φ, балансирующая, остаток, ставка якоря, LT-спред
    books = [("cards", "Кредитные карты", "asset", "key", 0.45, None, True, False, 742.0, 0.412, 0.214),
             ("cash_loans", "Кредиты наличными", "asset", "ofz_3y", 0.18, None, True, False, 1096.4, 0.287, 0.118),
             ("auto", "Автокредиты", "asset", "ofz_3y", 0.14, None, True, False, 512.6, 0.221, 0.062),
             ("mortgage", "Ипотека", "asset", "ofz_5y", 0.08, None, True, False, 498.3, 0.142, 0.021),
             ("sme_loans", "Кредиты МСБ", "asset", "key", 0.5, None, True, False, 437.2, 0.213, 0.052),
             ("corp_loans", "Корпоративные кредиты и лизинг", "asset", "key", 0.6, None, True, False, 526.6, 0.193, 0.031),
             ("securities", "Долговые бумаги", "asset", "ofz_3y", 0.33, None, True, False, 1012.4, 0.131, -0.008),
             ("liquidity", "Ликвидность", "asset", "key", 1.0, None, False, True, 934.5, 0.118, -0.032),
             ("retail_current", "Текущие счета физлиц", "liability", "key", 0.31, 0.21, True, False, 1384.0, 0.031, -0.118),
             ("retail_term", "Срочные вклады физлиц", "liability", "key", 0.52, 0.86, True, False, 1642.0, 0.128, -0.021),
             ("corp_funds", "Средства бизнеса", "liability", "key", 0.85, 0.48, True, False, 1096.0, 0.064, -0.072),
             ("wholesale", "Оптовое фондирование", "liability", "key", 1.0, 1.0, False, True, 388.0, 0.168, 0.012)]
    floors = {"cards": 0.12, "cash_loans": 0.06, "auto": 0.03, "mortgage": 0.005, "sme_loans": 0.025, "corp_loans": 0.01}
    sigma = {"asset": -0.0021, "liability": 0.0005}
    squeeze = {"asset": {"N": 0.0016, "H": 0.0, "M": -0.0009}, "liability": {"N": -0.0011, "H": 0.0, "M": 0.0021}}
    out = []
    for key, title, side, ref, rho, beta, phi, bal, bal0, rate0, lt in books:
        row = {"key": key, "title": title, "side": side, "ref": ref, "rho": rho, "phi": phi, "balancing": bal, "balance_anchor": bal0,
               "rate_anchor": rate0, "spread_lt": lt, "spread_lt_world": {w: r(lt + (sigma[side] + squeeze[side][w] if phi else 0.0), 5) for w in WORLDS},
               "spread_floor": floors.get(key), "rate_lt": {"N": r(0.08 + lt, 4), "H": r(0.105 + lt, 4), "M": r(0.17 + lt, 4)}}
        if beta is not None:
            row["beta"] = beta
        out.append(row)
    nim_w = {"N": [0.107, 0.1052, 0.1038, 0.1026, 0.1018] + [0.1012] * 6, "H": [0.107, 0.1066, 0.1068, 0.1072, 0.1075] + [0.1075] * 6,
             "M": [0.107, 0.1078, 0.1094, 0.1108, 0.1118] + [0.1124] * 6}
    share = lambda step: [r(0.336 + step * min(i, 4), 4) for i in range(NY)]  # noqa: E731
    return {"books": out,
            "transmission": {"target": 0.125, "definition": "разность стационарных ЧПМ миров M и N на разность их долгосрочных ключевых",
                             "realized": 0.125, "nim_lt_target_mgmt": NIM_JUDGED, "target_eng": 0.1098, "sigma0": -0.0021, "sigma0_liab": 0.0005,
                             "sigma0_split": 0.8, "phi": 0.412, "phi_assets": 0.2266, "phi_liab": 0.164, "phi_split": 0.55,
                             "loan_margin": {"N": 0.0684, "H": 0.0571, "M": 0.0362}, "tol": 1e-9, "solved": True, "roe_equiv": 0.5127,
                             "pairs": [{"from": "N", "to": "H", "key_from": 0.08, "key_to": 0.105, "value": 0.252, "roe_equiv": 1.034, "inside": True},
                                       {"from": "H", "to": "M", "key_from": 0.105, "key_to": 0.17, "value": 0.0754, "roe_equiv": 0.309, "inside": True}],
                             "pairs_range": [-0.05, 0.3], "by_world": {"N": 0.181, "H": 0.142, "M": 0.083}, "realized_cells": 0.1246,
                             "level": {"world": "M", "value": NIM_JUDGED, "reference_world": "H", "reference_value": NIM_REF}},
            "nim_by_world": {"years": YEARS, **nim_w},
            "current_share": {"c_ref": 0.336, "psi": 1.08, "bounds": [0.26, 0.42], "by_world": {"N": share(0.012), "H": share(0.004), "M": share(-0.014)}},
            "disclosed": {"nii_per_100bp": None, "src": "не раскрыто в фактах книги"}}


def make_guidance():
    # ключ, название, базис, вид, гайденс, факт с начала года, модель года, нужно в остатке, статус, масса вне, примечание
    items = [("op_np_growth", "Рост операционной прибыли акционеров за год", "mgmt", "min", 0.2, 0.312, 0.2154, None, "inside", 0.14,
              "граница нестрогая: «на 20 % и выше»"),
             ("dps_growth", "Рост дивиденда на акцию за год", "mgmt", "min", 0.2, 0.3676, 0.2638, None, "inside", 0.09,
              "граница строгая: «более чем на 20 %» — больше 17,88 ₽ на акцию за год"),
             ("roe_target", "Цель ROE эмитента (к операционному капиталу)", "mgmt", "point", 0.3, 0.274, None, None, "n/a", None,
              "цель эмитента — к операционному капиталу; цель стратегии, не прогноз года"),
             ("nim", "ЧПМ", "mgmt", "point", None, 0.1145, 0.107, None, "n/a", None, None),
             ("cor_max", "Стоимость риска", "mgmt", "max", None, 0.048, 0.056, None, "n/a", None, None),
             ("cir", "C/I", "mgmt", "point", None, 0.4742, 0.4764, None, "n/a", None, None)]
    events = [("2026-02-19", "МСФО за 2025 год (19.02.2026)"), ("2026-05-21", "МСФО за первый квартал 2026 года (21.05.2026)"),
              ("2026-08-11", "МСФО за второй квартал 2026 года (11.08.2026)")]
    revisions = [{"date": "2024-11-28", "key": "roe_target", "value": 0.3, "event": "МСФО за третий квартал 2024 года (28.11.2024)"}]   # цель без года названа раньше гайденса года
    for i, (day, event) in enumerate(events):
        for key, *_rest in items:
            value = _rest[3]
            if key == "op_np_growth" and i == 0:
                value = 0.3                                 # гайденс года снижен после первого квартала
            revisions.append({"date": day, "key": key, "value": value, "event": event})
    return {"year": 2026, "as_of": "2026-08-11", "src": "пресс-релиз о результатах за второй квартал 2026 года", "basis": "mgmt",
            "items": [{"key": k, "title": t, "basis": b, "kind": kind, "guidance": g, "scope": "group", "relation": None, **({"scope_note": note} if note else {}),
                       "fact_ytd": f, "fact_periods": ["2026Q1", "2026Q2"], "model_year": m, "required_rest": rr, "status": st, "mass_outside": mo}
                      for k, t, b, kind, g, f, m, rr, st, mo, note in items],
            "gate": {"name": "guidance_gap", "fired": False, "mass": 0.14, "explanation": None, "valid_until": None}, "revisions": revisions}


REFINE_ROWS = ("nim_lt", "cor_lt")


def make_reverse(central, cap):
    rows = [("nim_lt", "ЧПМ после фазы роста (при рыночных ставках, на балансе якоря)", "value", "pct", ["nii.nim_lt_target_mgmt"], NIM_JUDGED, [0.103, 0.116], 0.1047, "solved"),
            ("cor_lt", "Сдвиг стоимости риска после фазы роста", "shift", "pp", ["regimes.*.cor.LT"], 0.0, [-0.008, 0.012], 0.0109, "solved"),
            ("transmission", "Передача ключевой в ЧПМ", "value", "number", ["nii.transmission.target"], 0.125, [0.05, 0.2], None, "unreachable"),
            ("buffer", "Запас менеджмента над минимумом норматива", "value", "pct", ["capital.mgmt_buffer.n20_0", "capital.mgmt_buffer.n1_1"], 0.015, [0.005, 0.025], None, "unreachable"),
            ("payout", "Доля выплаты", "value", "pct", ["dividends.payout.LT"], 0.26, [0.21, 0.3], None, "unreachable"),
            ("beta", "β_E", "value", "number", ["valuation.beta_e"], 1.18, [1.0, 1.4], 1.612, "solved"),
            ("erp", "ERP", "value", "pct", ["valuation.erp"], 0.0557, [0.049, 0.062], 0.0791, "solved"),
            ("reg_mix", "Регуляторный сценарий (смесь к «Жёсткому»)", "mix", "mix", ["joint.reg_prob_given_regime"], 0.0, [0.0, 0.0], None, "unreachable"),
            ("real_growth", "Реальный рост в терминале", "value", "pct", ["valuation.terminal.real_growth"], 0.015, [0.005, 0.025], -0.0182, "solved"),
            ("fade", "Угасание избыточной доходности", "value", "number", ["valuation.terminal.fade"], 0.5, [0.25, 1.0], None, "unreachable"),
            ("governance", "Дисконт за управление", "value", "pct", ["valuation.governance.discount"], GOV, [0.0, 0.1], 0.2314, "solved")]
    out = []
    for key, name, kind, unit, paths, book, rng, solved, status in rows:
        out.append({"key": key, "name": name, "kind": kind, "unit": unit, "paths": paths, "book": book, "range": rng, "solved": solved,
                    "delta": None if solved is None else r(solved - book, 6), "in_range": solved is not None and rng[0] <= solved <= rng[1],
                    "status": status, "gap": 0.0 if solved is not None else r({"transmission": 41.7, "reg_mix": 66.2}.get(key, 24.8), 2),
                    "point_solved": None if solved is None else r(solved * 1.02, 6), "point_status": status,
                    # на полной полосе уточняются только названные книгой строки; у прочих решение — корень подвыборки
                    "gap_basis": "full" if key in REFINE_ROWS and solved is not None else "subsample",
                    **({"stationary_book": NIM_JUDGED, "stationary_solved": solved,
                        "levels_solved": {"modal_cell": {"nim": 0.1072, "cor": 0.0549, "cir": 0.4744, "loans_share": 0.779},
                                          "analytical": {"nim": 0.1005, "cor": 0.0555, "cir": 0.4889, "loans_share": 0.743},
                                          "point": {"nim": 0.0987, "cor": 0.056, "cir": 0.4957, "loans_share": 0.7267},
                                          "macro_neutral": {"nim": 0.097, "cor": 0.0565, "cir": 0.5021, "loans_share": 0.7124}}} if key == "nim_lt" else {}),
                    **({"reason": "корень на краю отрезка поиска"} if key == "buffer" else {})})
    by_year = [{"year": y, "pv_excess_cum": v} for y, v in zip(YEARS, (9.8, 31.4, 57.2, 84.9, 112.3, 138.1, 161.4, 181.9, 199.6, 214.7, 227.4))]
    by_year.append({"year": YEARS[-1] + 1, "pv_excess_cum": 264.5})        # последняя строка — с терминалом
    return {"target": PRICE, "number": "median",
            "method": "подвыборка 400 прогонов с общими случайными числами, поправка к полной медиане, секущая; невязка — медиана полной полосы в решении; "
                      "у оси полосы прогоны распределены вокруг проверяемого значения, поэтому решения разных строк не перемножаются; на полной полосе "
                      "уточняются только строки, названные книгой (2 из 11): у прочих решение и пометка «в диапазоне книги» — оценка по подвыборке",
            "refine_rows": list(REFINE_ROWS), "rows": out,
            "bank_rows": [
                {"key": "implied_roe_through_cycle", "title": "Вменённый ROE после фазы роста", "unit": "pct", "book": 0.1952, "implied": 0.1674, "delta": -0.0278, "status": "solved"},
                {"key": "implied_cost_of_equity", "title": "Вменённая стоимость капитала", "unit": "pct", "book": 0.1812, "implied": 0.2146, "delta": 0.0334,
                 "status": "solved", "by_world": {"N": 0.1782, "H": 0.2161, "M": 0.2493}},
                {"key": "market_cap_minus_bv", "title": "Рынок: капитализация минус капитал", "unit": "bn", "book": r(central * N_DIV / 1000 - BV_V),
                 "implied": r(cap - BV_V), "delta": r(cap - central * N_DIV / 1000), "status": "solved"},
                {"key": "value_without_excess_growth", "title": "Стоимость без опережающего роста", "unit": "rub", "book": r(central), "implied": 304.6,
                 "delta": r(304.6 - central), "status": "solved"},
                {"key": "book_value_per_share", "title": "Капитал без премии", "unit": "rub", "book": r(central), "implied": r(BV_V * 1000 / N_DIV),
                 "delta": r(BV_V * 1000 / N_DIV - central), "status": "solved"},
                {"key": "excess_return_years", "title": "В цене — лет избыточной доходности", "unit": "years", "book": None, "implied": 2, "delta": None,
                 "status": "solved", "by_year": by_year, "market_excess": r(cap - BV_V)}]}


# ось-связка: несколько чисел книги идут к своим концам одним положением оси; строка печатается по первому пути
BUNDLE = {"book": {"opex.volume_link": 0.5, "fees.volume_link": 0.6, "opex.real_growth.2027": 0.0158, "opex.real_growth.LT": 0.0079},
          "low": {"opex.volume_link": 0.3, "fees.volume_link": 0.4, "opex.real_growth.2027": 0.0258, "opex.real_growth.LT": 0.0179},
          "high": {"opex.volume_link": 0.7, "fees.volume_link": 0.8, "opex.real_growth.2027": 0.0058, "opex.real_growth.LT": -0.0021}}


# вторая связка — премия роста средств клиентов: уровень года и сход диапазона к нулю
PREMIUM = {k: {f"volumes.funds_share_drift.retail.{y}": v for y, v in zip(range(2027, 2032), vals)}
           for k, vals in (("book", [0.0] * 5), ("low", [-0.05, -0.05, -0.04, -0.03, -0.02]), ("high", [0.05, 0.05, 0.04, 0.03, 0.02]))}
ENDS = {"flex": BUNDLE, "funds_premium": PREMIUM}


def judgement_axes():
    """Оси книги: источник — слова для владельца (П§0.2), не длиннее 80 знаков; единица — код оси."""
    axes = [("nim_lt", "ЧПМ после фазы роста", "value", "pct", ["nii.nim_lt_target_mgmt"], NIM_JUDGED, 0.103, 0.116, 1, "средняя маржа окна фактов, приведённая к балансу якоря"),
            ("cor_lt", "Стоимость риска после фазы роста (сдвиг всех режимов)", "shift", "pp", ["regimes.*.cor.LT"], 0.0, -0.008, 0.012, -1, "история стоимости риска 2015–2026 годов"),
            ("erp", "ERP", "value", "pct", ["valuation.erp"], 0.0557, 0.049, 0.062, -1, "решение владельца 30.09.2026"),
            ("beta", "β_E", "value", "number", ["valuation.beta_e"], 1.18, 1.0, 1.4, -1, "β к индексу за 3 года — 1,18"),
            ("flex", "Гибкость расходов и услуг к портфелю", "bundle", "number", list(BUNDLE["book"]), 0.5, 0.3, 0.7, 1, "за кредитным портфелем идёт около половины расходов"),
            ("premium", "Премия роста кредитов к сектору", "shift", "pp", ["volumes.loan_share_drift"], 0.0, -0.05, 0.05, 1, "рост портфеля против сектора в 2023–2026 годах"),
            ("funds_premium", "Премия роста средств клиентов с 2027 года", "bundle", "pp", list(PREMIUM["book"]), 0.0, -0.05, 0.05, 1, "середина между фактами и нуждой баланса"),
            ("transmission", "Передача ключевой в ЧПМ", "value", "number", ["nii.transmission.target"], 0.125, 0.05, 0.2, 1, "калибровка книг ЧПД: эмпирика 0,08–0,17"),
            ("buffer", "Запас менеджмента над минимумом норматива", "value", "pct", ["capital.mgmt_buffer.n20_0"], 0.015, 0.005, 0.025, -1, "три чтения ряда норматива; запас — сверх глиссады"),
            ("opex", "Расходы: реальный рост", "shift", "pp", ["opex.real_growth"], 0.0, -0.01, 0.03, -1, "цель C/I на долгосрочном участке"),
            ("rwa_density", "Плотность RWA: дрейф", "value", "pct", ["capital.rwa_density_drift"], 0.01, -0.04, 0.035, -1, "ступень операционного риска — плавным дрейфом"),
            ("crisis_nim", "Кризис: сдвиг ЧПМ 2027", "value", "pp", ["regimes.crisis.nim_shift.2027"], -0.008, -0.02, 0.0, 1, f"книга {BOOK}, ось „Кризис: сдвиг ЧПМ 2027“"),
            ("one_off", "Кризис: разовый убыток", "value", "bn", ["regimes.crisis.one_off_loss.amount"], -40.0, -90.0, 0.0, 1, "до 12 % капитала: эпизоды 2008 и 2014 годов"),
            ("instruments", "Инструменты капитала к RWA", "value", "pct", ["capital.n20.t2"], 0.0233, 0.0163, 0.0303, 1, "шесть дат формы группы — 2,2–2,5 % RWA"),
            ("payout", "Доля выплаты", "value", "pct", ["dividends.payout.LT"], 0.26, 0.21, 0.3, 1, "факт к средней прибыли четырёх кварталов — 25,86 %"),
            ("growth", "Реальный рост в терминале", "value", "pct", ["valuation.terminal.real_growth"], 0.015, 0.005, 0.025, 1, "рост реального ВВП в долгосрочном периоде"),
            ("fade", "Угасание избыточной доходности", "value", "number", ["valuation.terminal.fade"], 0.5, 0.25, 1.0, 1, "суждение книги: половина избыточной доходности за горизонтом"),
            ("governance", "Дисконт за управление", "value", "pct", ["valuation.governance.discount"], GOV, 0.0, 0.1, -1, "ни один канал не имеет опоры — 0"),
            ("share_count", "Число акций: поправка делителя", "value", "pct", ["valuation.share_count_adj"], 0.0, -0.05, 0.02, -1, "программа мотивации и собственные акции"),
            ("fvoci_maturity", "Срок подтягивания FVOCI", "value", "years", ["oci.fvoci_maturity"], 3.0, 1.5, 5.0, -1, "сроки портфеля 1,5–5 лет по отчётности 2024–2026"),
            ("world_prob", "Веса миров", "dict", "dict", ["joint.world_prob"], dict(W_A), {"N": 0.25, "H": 0.5, "M": 0.25}, {"N": 0.4, "H": 0.45, "M": 0.15}, 1,
             "запись миров семейства 850, версия 1.7"),
            ("regime_prob", "Вероятности режимов (P(кризис) 10–25 %)", "dict", "dict", ["joint.regime_prob"], dict(P_REG),
             {"soft": 0.1588, "norm": 0.4235, "downturn": 0.3177, "crisis": 0.1}, {"soft": 0.1324, "norm": 0.3529, "downturn": 0.2647, "crisis": 0.25}, -1,
             "частота эпизодов 2008–2025")]
    return [{"id": a, "name": n, "kind": k, "unit": u, "paths": p, "book": b, "low": lo, "high": hi, "sign": s, "source": src}
            for a, n, k, u, p, b, lo, hi, s, src in axes]


def make_judgement_rows(axes, share_of, central):
    swings = [84.0, 58.0, 46.0, 41.0, 38.0, 36.0, 30.0, 24.0, 21.0, 19.0, 16.0, 13.0, 12.0, 10.0, 9.0, 8.0, 6.0, 5.0, 4.0, 2.0, 11.0, 26.0]
    out = []
    for a, swing in zip(axes, swings):
        down = 0.4 if a["id"] in ("growth", "premium") else 0.6       # широкая сторона диапазона — снижающая цену
        if a["kind"] != "dict" and a["book"] in (a["low"], a["high"]):
            down = 1.0                                                  # односторонняя ось: на своём краю — сама точка
        lo, hi = (central - swing * down, central + swing * (1 - down)) if a["sign"] > 0 else (central + swing * (1 - down), central - swing * down)
        lo, hi = r(lo), r(hi)
        c = share_of.get(a["id"])
        out.append({"id": a["id"], "name": a["name"], "unit": a["unit"], "kind": a["kind"], "paths": a["paths"], "book": a["book"], "low": a["low"],
                    "high": a["high"], "dist": "triangular", "price_low": lo, "price_high": hi, "swing": r(abs(hi - lo)),
                    "mean_shift": None if a["kind"] == "dict" else r((hi + lo - 2 * r(central)) / 6, 4), "share": c["share"] if c else None,
                    "rank_corr": c["rank_corr"] if c else None, "in_band": True, "source": a["source"],
                    **({"ends": ENDS[a["id"]]} if a["kind"] == "bundle" else {})})
    out.sort(key=lambda x: -x["swing"])
    return out


def make_next_report(median, central):
    post = lambda c: {"soft": r(max(0.02, 0.35 - 6 * (c - 0.04)), 4), "crisis": r(min(0.4, 0.05 + 7 * max(0, c - 0.05)), 4)}  # noqa: E731
    cor_rows = []
    for i in range(13):
        c = round(0.038 + 0.002 * i, 3)
        d = -16.0 * math.tanh((c - 0.0496) / 0.008)
        p = post(c)
        rest = 1 - p["soft"] - p["crisis"]
        cor_rows.append({"cor": c, "point": r(central + d * 1.05), "median": r(median + d), "median_low": r(median + d - 38), "median_high": r(median + d + 38),
                         "d_point": r(d * 1.05), "d_median": r(d), "posterior": {"soft": p["soft"], "norm": r(rest * 0.58, 4), "downturn": r(rest * 0.42, 4), "crisis": p["crisis"]}})
    nim_rows = []
    for i in range(9):
        v = round(0.111 + 0.001 * i, 3)
        d = (v - 0.1153) / 0.001 * 2.4                 # ожидания ЧПМ у режимов равны: строки ЧПМ вероятностей режимов не меняют (М§13)
        nim_rows.append({"nim": v, "point": r(central + d * 1.05), "median": r(median + d), "median_low": r(median + d - 38), "median_high": r(median + d + 38),
                         "d_point": r(d * 1.05), "d_median": r(d), "posterior": {"soft": 0.158, "norm": 0.409, "downturn": 0.291, "crisis": 0.142}})
    fact_note = "факт (ЧПМ и стоимость риска — упр. базис; прибыль — операционная, определение эмитента)"
    return {"period": "2026Q3", "book_period": "2026Q3", "target": "median",
            "closing": {"date": "2026-11-19", "title": "МСФО за девять месяцев 2026 года", "confirmed": False, "published": False},
            "expectation": {"cor_mgmt": 0.05, "nim_mgmt": 0.1153, "cor_engine": 0.0506, "nim_engine": 0.1141, "ni": 54.0, "loans_ac": 3962.0, "iea": 5712.0,
                            "tau_eff": 0.247, "days": 92,
                            "by_regime": [{"regime": g, "cor_mgmt": c, "nim_mgmt": 0.1153, "posterior": p} for g, c, p in (
                                ("soft", 0.0462, 0.158), ("norm", 0.0496, 0.409), ("downturn", 0.0518, 0.291), ("crisis", 0.0513, 0.142))]},
            "cor_table": cor_rows, "nim_table": nim_rows,
            "neutral": {"cor": {"value": 0.0496, "gap_rub": 0.02, "ni_equivalent": 54.3}, "nim": {"value": 0.1153, "gap_rub": -0.03, "ni_equivalent": 54.0},
                        "point_cor": 0.0502, "point_nim": 0.115},
            "slope": {"rub_per_01pp_cor": -2.0, "rub_per_01pp_nim": 2.4, "at_cor": "neutral", "at_nim": "neutral"},
            "reaction": {k: {"d_median_min": min(x["d_median"] for x in rows), "d_median_max": max(x["d_median"] for x in rows)}
                         for k, rows in (("cor", cor_rows), ("nim", nim_rows))},
            "benchmarks": [{"key": "same_quarter_last_year", "name": "тот же квартал год назад", "cor": 0.062, "nim": 0.109, "ni": 40.1, "note": fact_note},
                           {"key": "last_quarter", "name": "прошлый отчётный квартал", "cor": 0.047, "nim": 0.116, "ni": 52.06, "note": fact_note},
                           {"key": "guidance", "name": "гайденс года", "cor": None, "nim": None, "ni": None,
                            "note": "гайденс года — рост операционной прибыли и дивиденда на акцию; ЧПМ и стоимость риска эмитент числом не называет; "
                                    "прибыль квартала гайденс не даёт"}]}


EQUATION = ("прогноз равен ожиданию модели: прибыль банка по РСБУ прибыль группы не предсказывает (за шесть кварталов они расходились в 0,85–6,6 раза), "
            "моста к МСФО нет; месячные данные — наблюдение")


def make_nowcast(n20_check):
    bench = lambda *rows: [{"key": k, "name": n, "value": v} for k, n, v in rows]  # noqa: E731
    target = lambda exp, se, basis, rows: {  # noqa: E731
        "ras_estimate": None, "bridge": None, "ras_bridged": None, "expectation": exp, "w": 0.0, "forecast": exp, "std_error": se,
        "interval": None if se is None else [r(exp - se, 4), r(exp + se, 4)], "deviation": 0.0, "equation": EQUATION, "version": "nowcast-1",
        "benchmarks": bench(("model", "ожидание модели без индикаторов", exp), *rows), "basis": basis}
    by_target = {"ni_q": target(54.0, 3.4, "mgmt", [("prev_quarter", "прошлый квартал", 52.06), ("same_quarter_last_year", "тот же квартал год назад", 40.1)]),
                 "nim_q": target(0.1153, 0.0021, "mgmt", [("prev_quarter", "прошлый квартал", 0.116), ("form102_nii", "оценка ЧПД по форме 0409102 с мостом прошлого квартала", 0.1147)]),
                 "cor_q": target(0.05, None, "mgmt", [("prev_quarter", "прошлый квартал", 0.047)])}
    fact, quarter = 98.6, 54.0
    rest = r(NI_PATH[0] - fact - quarter)
    se = r(math.sqrt(3.4 ** 2 + (0.06 * rest) ** 2))
    dps = r(sum(DPS_POLICY_Q.values()) + sum(DPS_POLICY_DONE.values()), 4)       # DPS политики года: сумма четырёх кварталов
    per = 0.26 * 1000 / N_ISS * 2 / 4                  # ошибка открытого квартала входит в окна двух решений года из четырёх кварталов базы
    year = {"year": 2026, "ni_fact": fact, "ni_quarter": quarter, "ni_rest": rest, "ni_year": NI_PATH[0], "ni_year_se": se, "at1_coupon_after_tax": 0.0,
            "base": NI_PATH[0], "payout": 0.26, "dps": dps, "dps_interval": [r(dps - per * 3.4, 4), r(dps + per * 3.4, 4)], "dps_model": dps,
            "capital_check": {"n20_expected": n20_check, "requirement": 0.11, "ok": n20_check >= 0.11}, "yield": {MAIN: r(dps / PRICE, 6)},
            "note": "факт отчётных кварталов + смесь заголовка на открытый квартал и на остаток года; дивиденд года — сумма решений за кварталы прибыли; "
                    "к цене не подключено до допуска"}
    # месячная таблица «операционные результаты и формы ЦБ»: 15 месяцев до августа 2026 года
    ops, ytd = [], 0.0
    for i in range(15):
        m = 6 + i
        y, mm = 2025 + (m - 1) // 12, (m - 1) % 12 + 1
        month = 15.2 + 1.1 * math.sin(i) + 0.14 * i
        ytd = (month if mm == 1 else ytd + month) if i else 71.4
        loans = 2996 + 45.4 * i
        funds = 3540 + 41.6 * i
        f102 = None if i == 14 else r(ytd + (0.4 if i == 9 else 0.0), 1)       # форма за последний месяц ещё не вышла
        ops.append({"month": f"{y}M{mm:02d}", "published_at": (date(y + (mm == 12), mm % 12 + 1, 1) + timedelta(days=22 + i % 3)).isoformat(),
                    "clients_total": r(50.2 + 0.42 * i, 1), "clients_active": r(31.1 + 0.214 * i, 1), "loans_gross": r(loans, 1),
                    "loans_retail": r(loans * (0.79 - 0.004 * i), 1), "loans_business": r(loans * (0.21 + 0.004 * i), 1), "funds_total": r(funds, 1),
                    "funds_retail": r(funds * 0.71, 1), "funds_business": r(funds * 0.29, 1), "ras_ni_ytd": r(ytd, 1), "ras_ni_m": None if i == 0 else r(month, 1),
                    "f102_ni_ytd": f102, "n1_0": r(0.128 + 0.0015 * math.sin(i / 2), 4), "n1_1": r(0.087 + 0.001 * math.sin(i / 2), 4),
                    "n1_2": r(0.11 + 0.001 * math.sin(i / 2), 4), "capital_total": r(498 + 4.4 * i, 1), "source": "seed" if i < 3 else "релиз эмитента"})
    form102 = [{"month": x["month"], "ni": x["f102_ni_ytd"], "first_seen": None if x["f102_ni_ytd"] is None else f"{x['published_at'][:8]}27",
                "release_ni": x["ras_ni_ytd"], "diff": None if x["f102_ni_ytd"] is None else r(x["f102_ni_ytd"] - x["ras_ni_ytd"], 1),
                "ok": None if x["f102_ni_ytd"] is None else True} for x in ops[-3:]]
    return {"period_unit": "quarter", "input_unit": "month", "connected_to_price": False,
            "targets": [{"key": "ni_q", "title": "Операционная прибыль акционеров квартала", "unit": "bn", "basis": "mgmt"},
                        {"key": "nim_q", "title": "ЧПМ квартала", "unit": "share", "basis": "mgmt"},
                        {"key": "cor_q", "title": "Стоимость риска квартала", "unit": "share", "basis": "mgmt"}],
            "quarter": {"period": "2026Q3", "months": [], "months_known": 0, "by_target": by_target}, "year": year,
            "months": {"basis": "ras", "rows": []},
            "ops": {"note": "клиенты, портфель и средства — данные эмитента (упр.); прибыль и капитал — банк по РСБУ, нормативы — банка; "
                            "за шесть кварталов прибыль группы отличалась от прибыли банка в 0,85–6,6 раза", "rows": ops},
            "form102": form102,
            "admission": {"rule": "4 события вне выборки; MSE прогноза не больше 0,8 MSE лучшего эталона — по ЧПМ и стоимости риска квартала",
                          "status": "collecting", "events_needed": 4, "events_scored": 0, "mse_ratio": {"nim_q": None, "cor_q": None},
                          "first_event": "2026Q3", "earliest_decision": "2027-11-18"},
            "retro": make_retro(),
            "journal": {"entries": [
                {"id": f"{t}-2026Q3-T-30", "target": t, "period": "2026Q3", "horizon": "T-30", "recorded_at": "2026-10-05T16:05:00+00:00",
                 "release_sha": "4b0e4f6a1c2d", "book_version": BOOK_PREV, "forecast": f, "benchmarks": bm, "actual": None,
                 "errors": {"forecast": None, **{k: None for k in bm}}}
                for t, f, bm in (("ni_q", 54.0, {"model": 54.0, "prev_quarter": 52.06, "same_quarter_last_year": 40.1}),
                                 ("nim_q", 0.1153, {"model": 0.1153, "prev_quarter": 0.116, "form102_nii": 0.1147}),
                                 ("cor_q", 0.05, {"model": 0.05, "prev_quarter": 0.047}))],
                "total_entries": 3, "rule": "записи неизменяемы; эталоны замораживаются при первой записи; факт вносится после МСФО",
                "releases": {"4b0e4f6a1c2d": {"book_version": BOOK_PREV, "generated_at": "2026-10-05T16:04:10+00:00"}}}}


HIST_NI = [20.6, 21.9, 23.4, 24.7, 26.1, 28.3, 31.2, 34.8, 33.5, 37.6, 40.1, 39.9, 46.5, 52.06]      # 2023Q1 … 2026Q2
RETRO_TITLES = {"consensus": "консенсус у отчёта (за день до выхода)", "prev_quarter": "прошлый квартал",
                "same_quarter_last_year": "тот же квартал год назад", "yoy_growth": "год назад × рост г/г прошлого квартала"}


def make_retro():
    out = {}
    for h, lag in (("T-30", 1), ("T-90", 2)):
        periods = []
        for i, act in enumerate(HIST_NI):
            b = {}
            if i >= lag:
                b["prev_quarter"] = HIST_NI[i - lag]
            if i >= 4:
                b["same_quarter_last_year"] = HIST_NI[i - 4]
            if i >= 4 + lag:
                b["yoy_growth"] = r(HIST_NI[i - 4] * HIST_NI[i - lag] / HIST_NI[i - 4 - lag], 2)
            if i % 3 != 1 and h == "T-30":
                b["consensus"] = r(act * (1 + 0.03 * math.cos(0.9 * i)), 2)
            periods.append({"period": f"{2023 + i // 4}Q{i % 4 + 1}", "actual": act, "benchmarks": b})
        keys = sorted({k for p in periods for k in p["benchmarks"]})
        err = {k: [(p["benchmarks"][k], p["actual"]) for p in periods if k in p["benchmarks"]] for k in keys}
        out[h] = {"periods": periods, "rmse": {k: r(math.sqrt(sum(((b - x) / x) ** 2 for b, x in v) / len(v)), 6) for k, v in err.items()},
                  "bias": {k: r(sum(b - x for b, x in v) / len(v), 2) for k, v in err.items()}, "n": {k: len(v) for k, v in err.items()},
                  "main": "yoy_growth", "horizon": h, "titles": {k: RETRO_TITLES[k] for k in keys}}
    return {**out["T-30"], "by_horizon": out}


def make_indicators():
    groups = [("ops", "Операционные результаты за месяц"), ("cbr", "Формы ЦБ: банк и банковская группа"), ("rates", "Ставки и кривая"),
              ("market", "Рынок"), ("sector", "Сектор — справочно")]

    def series(n, a, b, noise, digits, kind):
        if kind == "month":                               # 12 месяцев до последнего раскрытого: 2025M09 … 2026M08
            dates = [f"{2025 + (8 + i) // 12}M{(8 + i) % 12 + 1:02d}" for i in range(n)]
        elif kind == "quarter":
            dates = [f"{2024 + (2 + i) // 4}Q{(2 + i) % 4 + 1}" for i in range(n)]
        else:
            dates = [(date(2025, 10, 7) + timedelta(days=int(i * 365 / (n - 1)))).isoformat() for i in range(n)]
        return dates, [round(a + (b - a) * i / (n - 1) + noise * math.sin(i * 1.7), digits) for i in range(n)]

    bank = "прибыль банка, не группы: за шесть кварталов прибыль группы отличалась от неё в 0,85–6,6 раза"
    spec = [("ops_clients", "ops", "Клиенты всего, млн", "number", "mgmt", 12, 51.9, 56.1, 0.1, 1, "релиз эмитента «Операционные результаты»", "month", None),
            ("ops_active", "ops", "Активные клиенты, млн", "number", "mgmt", 12, 31.9, 34.1, 0.1, 1, "релиз эмитента «Операционные результаты»", "month", None),
            ("ops_loans", "ops", "Кредитный портфель до резервов", "bn", "mgmt", 12, 3140, 3631, 12, 0, "релиз эмитента «Операционные результаты»", "month", None),
            ("ops_funds", "ops", "Средства клиентов", "bn", "mgmt", 12, 3660, 4122, 14, 0, "релиз эмитента «Операционные результаты»", "month", None),
            ("ops_np", "ops", "Прибыль банка по РСБУ с начала года", "bn", "ras", 12, 96.0, 131.8, 0.0, 1, "релиз эмитента «Операционные результаты»", "month", bank),
            ("n1_0", "cbr", "Н1.0 банка", "share", "regulatory", 12, 0.127, 0.13, 0.001, 4, "ЦБ, форма 0409135", "month", None),
            ("n1_1", "cbr", "Н1.1 банка", "share", "regulatory", 12, 0.086, 0.088, 0.001, 4, "ЦБ, форма 0409135", "month", None),
            ("f123_capital", "cbr", "Собственные средства банка, форма 0409123", "bn", "ras", 12, 512, 560.4, 3, 1, "ЦБ, форма 0409123", "month", None),
            ("n20_1", "cbr", "Н20.1 банковской группы, форма 0409805", "share", "regulatory", 7, 0.098, 0.1042, 0.002, 4, "ЦБ, форма 0409805", "quarter", None),
            ("key", "rates", "Ключевая ставка", "share", "market", 12, 0.17, 0.15, 0.0, 4, "ЦБ", "day", None),
            ("ofz5", "rates", "ОФЗ 5 лет (кривая)", "share", "market", 60, 0.158, 0.1614, 0.003, 4, "Мосбиржа, кривая бескупонной доходности", "day", None),
            ("ruonia", "rates", "RUONIA", "share", "market", 60, 0.168, 0.1482, 0.001, 4, "ЦБ", "day", None),
            ("close", "market", "Цена акции", "price", "market", 60, 318, PRICE, 9, 2, "Мосбиржа, TQBR", "day", None),
            ("imoex", "market", "Индекс Мосбиржи", "level", "market", 60, 2890, 2710, 60, 0, "Мосбиржа", "day", None),
            ("brokers_median", "market", "Медиана целей брокеров", "price", "market", 24, 352, 385, 4, 1, "T-Invest", "day", None),
            ("deposits", "sector", "Средняя ставка по вкладам (топ-10)", "share", "market", 30, 0.172, 0.148, 0.002, 4, "ЦБ", "day", None),
            ("sector_retail", "sector", "Розничный кредит, сектор, г/г", "share", "market", 12, 0.11, 0.04, 0.005, 4, "ЦБ, обзор банковского сектора", "month", None)]
    tiles = []
    for sid, grp, title, unit, basis, n, a, b, noise, dg, src, kind, note in spec:
        dates, vals = series(n, a, b, noise, dg, kind)
        i_lo, i_hi = min(range(n), key=lambda i: vals[i]), max(range(n), key=lambda i: vals[i])
        tiles.append({"id": sid, "group": grp, "title": title, "unit": unit, "basis": basis, "value": vals[-1], "date": dates[-1],
                      "change": r(vals[-1] - vals[-2], 6), "change_from": dates[-2], "min": {"date": dates[i_lo], "value": vals[i_lo]},
                      "max": {"date": dates[i_hi], "value": vals[i_hi]}, "history": {"date": dates, "value": vals}, "source": src,
                      **({"note": note} if note else {}), "status": "ok"})
    next(x for x in tiles if x["id"] == "key")["since"] = "2026-09-11"
    tiles.append({"id": "form102_ni", "group": "cbr", "title": "Прибыль банка по форме 0409102 с начала года", "unit": "bn", "basis": "ras", "value": None,
                  "date": None, "change": None, "change_from": None, "min": None, "max": None, "history": {"date": [], "value": []},
                  "source": "ЦБ, форма 0409102", "status": "missing", "reason": "форма за сентябрь ещё не раскрыта ЦБ"})
    return {"groups": [{"id": g, "title": t} for g, t in groups], "tiles": tiles}


def make_calendar():
    today = date.fromisoformat(VDATE)
    # идентификатор, дата, вид, название, квартал, подтверждено, окно (дней до и после; None — точный день), оценочная дата, примечание
    ev = [("record-2026Q2", "2026-10-12", "record", "Дата реестра: дивиденд за полугодие 2026 года", None, True, None, False, None),
          ("ops-2026M09", "2026-10-23", "ops_release", "Операционные результаты за сентябрь 2026 года", None, False, (2, 4), True,
           "день — по прошлым релизам: 24.09.2026, 25.08.2026"),
          ("cbr-2026-10", "2026-10-23", "cbr_rate", "Заседание Банка России по ключевой ставке", None, True, None, False, None),
          ("f102-2026M09", "2026-10-24", "form102", "Форма 0409102 за сентябрь 2026 года", None, False, (0, 2), False, None),
          ("pay-2026Q2", "2026-10-26", "pay", "Выплата дивиденда за полугодие 2026 года", None, True, None, False, "срок выплаты номинальным держателям"),
          ("ifrs-2026Q3", "2026-11-19", "ifrs", "МСФО за девять месяцев 2026 года", "2026Q3", False, (16, 11), True, "эмитент назвал месяц: ноябрь 2026 года"),
          ("databook-2026Q3", "2026-11-19", "databook", "Файл эмитента с точными значениями квартала", "2026Q3", False, (16, 11), True, None),
          ("f805-2026Q3", "2026-11-27", "form805", "Форма 0409805 на 30 сентября 2026 года", "2026Q3", False, (6, 8), False, None),
          ("call-2026", "2026-12-15", "call_option", "Право отзыва бессрочного субординированного займа", None, True, None, False,
           "отзыв — решение эмитента; в книге заём остаётся в инструментах капитала"),
          ("cbr-2026-12", "2026-12-18", "cbr_rate", "Заседание Банка России по ключевой ставке", None, True, None, False, None),
          ("div-2026Q3", "2026-12-24", "dividend_decision", "Решение собрания о дивиденде за девять месяцев 2026 года", "2026Q3", False, (9, 12), True, None),
          ("reg-2027-01", "2027-01-01", "regulation", "Надбавки к нормативам: следующая ступень", None, True, None, False, None),
          ("deal-2027", "2027-02-15", "deal", "Закрытие сделки: доля в расчётном банке для бизнеса", None, False, (45, 45), True,
           "условия объявлены 01.10.2026; в оценку войдёт фактами после закрытия"),
          ("ifrs-2026Q4", "2027-03-18", "ifrs", "МСФО за 2026 год", "2026Q4", False, (10, 10), True, None)]
    events = []
    for eid, dt, kind, title, covers, conf, window, est, note in ev:
        d0 = date.fromisoformat(dt)
        e = {"id": eid, "date": dt, "kind": kind, "title": title, "confirmed": conf, "precision": "window" if window else "day", "days": (d0 - today).days}
        if covers:
            e["covers"] = covers
        if window:
            e["earliest"], e["latest"] = (d0 - timedelta(days=window[0])).isoformat(), (d0 + timedelta(days=window[1])).isoformat()
        if est:
            e["estimated"] = True
        if kind == "deal":
            e["in_book"] = False
        if note:
            e["note"] = note
        events.append(e)
    recent = [{"id": "div-2026Q2", "date": "2026-10-01", "kind": "dividend_decision", "title": "Решение собрания о дивиденде за полугодие 2026 года",
               "covers": "2026Q2", "confirmed": True, "precision": "day", "days": -6, "note": "4,70 ₽ на акцию"},
              {"id": "deal-2026-10", "date": "2026-10-01", "kind": "deal", "title": "Объявлена покупка доли в расчётном банке для бизнеса",
               "confirmed": True, "precision": "day", "days": -6, "in_book": False}]
    return {"today": VDATE, "next_fact": dict(next(e for e in events if e["id"] == "ifrs-2026Q3"), kind="ifrs"),
            "next_ras": {"month": "2026M09", "release_date": "2026-10-23", "release_confirmed": False, "form102_date_est": "2026-10-24",
                         "form102_latest_est": "2026-10-26", "enters_via": "form102", "date": "2026-10-24", "days": 17},
            "events": events, "recent": recent}


def make_history():
    ni = [None] * 4 + HIST_NI                              # 2022Q1–2022Q4: потоков квартала в фактах нет
    cor_m = [0.071, 0.064, 0.058] + [None] * 3 + [0.058, 0.061, 0.064, 0.066, 0.071, 0.066, 0.062, 0.058, 0.056, 0.051, 0.049, 0.047]
    nim_m = [0.128, 0.126, 0.124] + [None] * 3 + [0.118, 0.116, 0.113, 0.111, 0.104, 0.107, 0.109, 0.112, 0.113, 0.114, 0.115, 0.116]
    qs = []
    for i in range(18):
        k, bv = ni[i], 262 + 29 * i + (120 if i >= 12 else 0)
        f = lambda v, nd=2: None if ni[i] is None else r(v, nd)  # noqa: E731
        k = k or 0.0
        qs.append({"period": f"{2022 + i // 4}Q{i % 4 + 1}",
                   "ifrs": {"ni": f(k * 1.02), "ni_sh": ni[i], "nii": f(48 + 6.4 * i), "fees": f(14 + 1.9 * i), "llp": f(11 + 2.0 * i),
                            "cor": f(cor_m[i] + 0.0006, 4) if cor_m[i] is not None else None, "opex": f(30 + 4.4 * i), "pbt": f(k * 1.3), "bv": f(bv),
                            "roe": f(k * 4 / bv, 4)},
                   "mgmt": {"nim": nim_m[i], "cor": cor_m[i], "cir": f(0.5 - 0.002 * i, 4), "roe": f(k * 4 / (bv * 0.9), 4)},
                   "n20": f(0.124 + 0.002 * math.sin(i), 4)})
    annual = [{"year": y, "ifrs": {"ni_sh": n, "roe": ro, "bv_end": b}, "mgmt": {"nim": nm, "cor": c, "cir": ci}, "dps": d, "payout": p, "n20_end": nn}
              for y, n, ro, b, nm, c, ci, d, p, nn in (
                  (2021, 63.4, 0.42, 176.0, 0.141, 0.049, 0.49, None, None, None), (2022, 20.8, 0.103, 206.0, 0.126, 0.078, 0.52, None, None, None),
                  (2023, 90.6, 0.332, 283.4, 0.1145, 0.0623, 0.497, None, None, 0.127), (2024, 124.2, 0.318, 519.6, 0.1078, 0.0655, 0.489, None, None, 0.125),
                  (2025, 174.43, 0.297, 687.0, 0.111, 0.0563, 0.478, 14.9, 0.2292, 0.128))]
    three = []
    for i, (period, total, nci, stake, debt) in enumerate((("2025Q1", 33.5, 1.3, 0.4, -3.9), ("2025Q2", 39.2, 1.5, 3.1, -4.2), ("2025Q3", 43.6, 1.8, 6.6, -4.5),
                                                           ("2025Q4", 35.1, 1.6, -5.3, -4.8), ("2026Q1", 34.6, -4.2, -3.2, -4.5), ("2026Q2", 39.5, -4.8, -3.56, -4.2))):
        sh = r(total - nci)
        three.append({"period": period, "ni_total": total, "ni_nci": nci, "ni_shareholders": sh, "stake_effect": stake, "debt_interest_effect": debt,
                      "ni_operating": r(sh - stake - debt)})
    return {"quarters": qs, "annual": annual,
            "ltm": {"as_of": FACTS_DATE, "ni_sh": 198.1, "roe": 0.2812, "basis": "ifrs",
                    "roe_issuer": {"value": 0.2916, "as_of": FACTS_DATE, "label": "операционная прибыль акционеров к операционному капиталу (определение эмитента)"}},
            "three_profits": three,
            "gaps": [{"period": "2022Q1–2022Q4", "basis": "ifrs", "reason": "потоков МСФО квартала в фактах нет"},
                     {"period": "2022Q4–2023Q2", "basis": "mgmt", "reason": "управленческие метрики квартала не раскрывались"}]}


# числа гейтов знака: гейт сработал тогда и только тогда, когда узел несёт `ok: false`
SIGN = {"volume_sign": {"point": 372.4, "point_free": 366.0, "d_point": -6.4, "d_world": {"N": -2.1, "H": -4.8, "M": -9.3}, "tol": 0.0, "ok": False,
                        "growth_constraint_off": True},
        "stress_sign": {"loss": {"step": 60.0, "cells": [], "after_tax": 44.5, "transfer_min": 0.44, "transfer_max": 0.66},
                        "requirement": {"cells": [{"world": "M", "regime": "downturn", "stricter": "strict", "looser": "schedule", "d_profit": 4.2},
                                                  {"world": "M", "regime": "crisis", "stricter": "strict", "looser": "mid", "d_profit": 1.9}]},
                        "mass": 0.027, "max_excess": 4.2, "ok": False, "mass_basis": "point", "mass_analytical": 0.039},
        "funds_cost_to_key": {"from_year": 2030, "to_year": YEARS[-1], "max": 0.71,
                              "by_world": {"N": {"cell": "N/norm/mid", "cost": 0.0374, "key": 0.08, "ratio": 0.4675},
                                           "H": {"cell": "H/norm/mid", "cost": 0.0629, "key": 0.105, "ratio": 0.599},
                                           "M": {"cell": "M/norm/mid", "cost": 0.1183, "key": 0.17, "ratio": 0.6959}}, "ok": True}}


def make_checks(gap):
    inv = [("probabilities", "Вероятности клеток, режимов, сценариев и веса миров в сумме 1"),
           ("bv_identity", "Капитал: тождество чистого излишка в каждом квартале каждой клетки"),
           ("balance_identity", "Баланс: активы = пассивы + капитал"), ("pnl_identity", "ОПУ: прибыль = сумма строк"),
           ("ddm_equals_ri", "Дивидендная модель = остаточный доход в каждой клетке", "во всех клетках сетки и 2 000 прогонах полосы; наибольшая относительная разность 2,4·10⁻¹²"),
           ("dps_history", "Выплаты завершённого года не выше потолка политики", "2025 год: 22,9 % отчётной прибыли акционеров при потолке 30 %"),
           ("exdate_jump", "Скачок оценки на экс-дату = −DPS × акции в обращении / делитель"),
           ("transmission_solved", "Передача ставки решена: ЧПМ в мире H и реализованная передача M − N равны книге"),
           ("dividend_bounds", "Дивиденды неотрицательны и не больше запаса капитала"), ("governance_sum", "Дисконт за управление = сумма каналов"),
           ("release_numbers", "Числа выпуска конечны; печать = округлению половиной вверх; P10 ≤ медиана ≤ P90; точка на оси ставок"),
           ("book_schema", "Книга: закрытая схема, все читаемые ключи заполнены"),
           ("jump_guard", "Защита заголовка: скачок медианы объяснён (М§14.4)"), ("payload_contract", "Контракт выпуска и потолок 500 КБ")]
    gates = [("pb_by_world", "P/B клетки вне коридора мира", "P/B клетки мира 0,5–3,0×", [0.5, 3.0]),
             ("roe_range", "ROE года вне коридора", "ROE года 5–40 %", [0.05, 0.4]),
             ("cor_range", "CoR года вне коридора", "CoR года 3–9,5 % (движок)", [0.03, 0.095]),
             ("nim_range", "ЧПМ квартала вне коридора", "ЧПМ квартала 8–13 % (упр.)", [0.08, 0.13]),
             ("nim_path_joint", "Ближний путь ЧПМ выше якоря и уровня после фазы роста",
              "ЧПМ упр. первых 8 кварталов не выше наибольшего из якоря и уровня мира после фазы роста + 0,3 п.п.", {"quarters": 8, "tolerance": 0.003}),
             ("cir_range", "C/I года вне коридора", "коридор C/I года, базис движка (книга)", [0.4, 0.55]),
             ("roe_k_homogeneity", "Разрыв «ROE − стоимость капитала» неоднороден по мирам", "−10…+10 п.п.; разброс миров ≤ 8 п.п.", [-0.1, 0.1]),
             ("guidance_gap", "Путь года вне гайденса", "масса клеток вне гайденса", None),
             ("capital_gap", "Капитальный разрыв: норматив ниже регуляторного пола", "норматив после дивидендов не ниже пола сценария", None),
             ("k_gt_g", "Сработала защита «стоимость капитала больше роста»", "k_T > g_T во всех клетках", None),
             ("roe_gt_g", "ROE терминала не выше роста", "ROE'_T > g_T", None), ("terminal_share", "Доля терминала вне коридора", "15–65 %", [0.15, 0.65]),
             ("real_rate", "Реальная ставка терминала вне коридора", "2–13 %", [0.02, 0.13]),
             ("bridge_drift", "Мост упр. ↔ МСФО дрейфует", "ЧПМ ±0,3 п.п., CoR ±0,4 п.п.", [-0.004, 0.004]),
             ("transmission_pairs", "Передача ставки между соседними мирами вне коридора", "каждая пара соседних миров −0,05…0,30", [-0.05, 0.3]),
             ("lt_spread_floor", "Долгосрочный спред кредитной книги к опорной ставке ниже пола",
              "LT-спред к опоре: карты не ниже 12 п.п., кредиты наличными — 6 п.п., автокредиты — 3 п.п.", {"cards": 0.12, "cash_loans": 0.06, "auto": 0.03}),
             ("off_band_shift", "Оси вне полосы сдвигают заголовок", "сумма сдвигов положения осей вне полосы не больше половины шага печати", 2.5),
             ("m_crisis_vs_cbr", "Клетка «M × кризис» мягче рискового сценария ЦБ", "рост кредита 2027 года 0–5 %; CoR года шока ≥ 9,5 % (упр.)", None),
             ("manual_input_overdue", "Ручной вход просрочен", "МСФО 7 дней, миры 21 день, реестр 5 дней, форма группы 10 дней", None),
             ("growth_cut", "Рост портфеля урезан капиталом сильнее коридора", "доля урезанного роста на конец пятого года не больше 10 %", 0.1),
             ("step_dividend", "У ступени минимума срезан дивиденд политики", "в квартале ступени доля прироста не падает больше чем на 0,5", 0.5),
             ("cir_lt", "C/I слоя «рыночные ставки как есть» на долгосрочном участке вне цели", "цель C/I после фазы роста, допуск и первый год участка (книга)",
              {"target": 0.47, "tolerance": 0.01, "from_year": 2033, "scope": "market_layer"}),
             ("wholesale_share", "Доля оптового фондирования вне коридора", "не больше 15 % пассивов", [0.0, 0.15]),
             ("payout_cap", "Выплата года по политике выше потолка", "базовая выплата года не выше 30 % прибыли", 0.3),
             ("volume_sign", "Снятие остановки кредита и поправок роста снижает оценку",
              "допуск изменения точки и разности изменений цен миров, ₽ на акцию (книга)", {"tol": 0.0}),
             ("stress_sign", "Оценка растёт с убытком кризиса или прибыль — с требованием к капиталу",
              "шаг разового убытка кризиса и допуск роста стоимости и прибыли, млрд ₽ (книга)", {"loss_step": 60.0, "tol": 0.5}),
             ("window_backtest", "Уровни слоя «рыночные ставки как есть» после фазы роста вне окна фактов",
              "первый год участка и коридоры окна фактов для CoR и C/I, упр. базис (книга)", {"from_year": 2030, "cor": [0.0469, 0.0665], "cir": [0.46, 0.4828]}),
             ("funds_cost_to_key", "Стоимость средств клиентов к ключевой ставке выше порога",
              "порог отношения стоимости средств клиентов к ключевой ставке и первый год участка (книга)", {"max": 0.71, "from_year": 2030})]
    out = []
    for name, title, text, val in gates:
        g = {"name": name, "title": title, "fired": False, "mass": 0.0, "cells": 0, "cell_list": [], "status": "quiet", "explanation": None,
             "expected_mass": None, "valid_until": None, "expiring": False, "message": None, "corridor": {"text": text, "value": val}}
        if name == "capital_gap":
            g.update({"fired": True, "mass": gap["mass"], "cells": gap["cells"], "status": "explained", "expected_mass": [0.0, 0.05], "valid_until": "2027-03-31",
                      "message": f"норматив ниже пола в {gap['cells']} клетках", "cell_list": gap["cell_list"],
                      "explanation": "Клетки «кризис × средняя группа СЗКО / жёсткий» в мирах H и M опускают Н20.0 ниже пола в год шока (разовый убыток 40 млрд ₽ "
                                     "и стоимость риска 11,8 % в квартале шока). Рост портфеля к этому кварталу уже остановлен, решения года кризиса "
                                     "отменены; разрыв закрывается через год — так и задумано книгой."})
        if name == "growth_cut":
            g.update({"fired": True, "mass": 0.342, "cells": 14, "status": "explained", "expected_mass": [0.2, 0.5], "valid_until": "2026-10-30", "expiring": True,
                      "message": "доля урезанного роста на конец 2031 года выше 10 % в 14 клетках",
                      "cell_list": [f"{w}/{g_}/strict" for w in WORLDS for g_ in REGIMES][:10],
                      "explanation": "В жёстком сценарии надбавки набираются быстрее, чем капитал успевает расти из прибыли: при выплате по политике рост "
                                     "кредитных книг в 2027–2029 годах уступает капиталу. Это свойство замыкания «дивиденд по политике, рост — остаток»; "
                                     "цена правила — на экране «Капитал и дивиденды»."})
        if name == "window_backtest":
            g["message"] = (f"уровни слоя «рыночные ставки как есть» в среднем за 2030–{YEARS[-1]} годы (упр.): CoR 5,65 % при коридоре окна фактов 4,69…6,65 %, "
                            "C/I 47,9 % при коридоре 46,0…48,3 %; ЧПМ 10,05 % при наибольшем квартале окна фактов 9,98 % и доле кредитов в процентных "
                            "активах 71,2 % — гейтом не сверяется")
        if name == "funds_cost_to_key":
            g["message"] = (f"стоимость средств клиентов к ключевой ставке в среднем за 2030–{YEARS[-1]} годы: N/norm/mid 0,47, H/norm/mid 0,60, M/norm/mid 0,70 "
                            "при пороге 0,71")
        if name == "cir_lt":
            g["message"] = (f"C/I (упр.) слоя «рыночные ставки как есть» в среднем за 2033–{YEARS[-1]} годы — 47,9 % при цели 47,0 % ± 1,0 п.п.; "
                            "модальная клетка H/norm/mid — 45,4 %")
        if name == "volume_sign":
            g.update({"fired": True, "mass": 1.0, "status": "explained", "expected_mass": [1.0, 1.0], "valid_until": "2027-03-31",
                      "message": "снятие остановки кредита в кризисе и поправок роста режимов (при выключенном ограничении роста капиталом) меняет точку на "
                                 "−6,40 ₽ (372,40 → 366,00 ₽); цены миров: N −2,10 ₽, H −4,80 ₽, M −9,30 ₽; условие — точка не снижается, а цена "
                                 "мира M меняется не хуже цены мира H, допуск 0,00 ₽",
                      "explanation": "Рост сверх заданного спросом в книге стоимости не создаёт: за кредитным портфелем идёт около половины расходов, а "
                                     "кредит в мире высоких ставок приносит маржу ниже стоимости капитала под него. Это свойство суждений о гибкости "
                                     "расходов и о марже, а не ошибка счёта; цена — в строке «Гибкость расходов и услуг к портфелю»."})
        if name == "stress_sign":
            g.update({"fired": True, "mass": SIGN["stress_sign"]["mass"], "cells": 2, "cell_list": ["M/downturn/strict", "M/crisis/strict"], "status": "explained",
                      "expected_mass": [0.0, 0.1], "valid_until": "2027-03-31",
                      "message": "при разовом убытке кризиса больше на 60 млрд ₽ стоимость клеток режима шока не растёт; при более высоком требовании к капиталу "
                                 "прибыль последнего года сетки выше в 2 клетках (миры: M; наибольшее превышение — M/downturn/strict против "
                                 "M/downturn/schedule: 4,2 млрд ₽); допуск 0,5 млрд ₽; масса — под вероятностями точки (под весами слоя «свой взгляд» "
                                 "те же клетки — 3,9 %)",
                      "explanation": "Жёсткий сценарий удерживает больше капитала: избыток выплачивается от запаса над требованием, а на удержанном "
                                     "капитале клетка зарабатывает — прибыль последнего года выше при том, что стоимость клетки ниже."})
        out.append(g)
    flags = [("book_update", "Книгу пора обновить", False, None), ("report_fact", "Вышла МСФО, факт не внесён", False, None),
             ("dividend_register", "Срок решения о дивиденде прошёл, объявления нет в реестре", False, None),
             ("ni_jump", "Прибыль квартала г/г прыгает при неизменной ключевой", False, None),
             ("dividend_recommended", "Совет директоров рекомендовал дивиденд", False, None),
             ("explanation_expiring", "Срок объяснения проверки истекает", True, "«Рост портфеля урезан капиталом сильнее коридора» — объяснение действует по 2026-10-30"),
             ("policy_expired", "Срок дивидендной политики истёк: действует прежняя до новой", False, None),
             ("price_fallback", "Живая цена не принята", False, None),
             ("ras_mismatch", "Прибыль банка по РСБУ за месяц: релиз и форма 0409102 расходятся", False, None),
             ("deal_pending", "Объявлена сделка, в книге её нет", True,
              "Закрытие сделки: доля в расчётном банке для бизнеса — условия объявлены 01.10.2026; в оценку войдёт фактами после закрытия"),
             ("capital_estimated", "Нормативы якоря — оценка до выхода формы", True, "форма 0409805 на 30.06.2026 ещё не вышла")]
    return {"invariants": [{"name": n, "title": t, "ok": True, "detail": (rest or ["в допуске"])[0]} for n, t, *rest in inv], "invariants_broken": 0,
            "gates": out, "flags": [{"name": n, "title": t, "raised": rz, "detail": dt} for n, t, rz, dt in flags],
            # сводка стоит на цене и дате книги; строк сверено больше, чем несёт выдержка `rows`
            "control_model": {"as_of": "2026-10-07", "commit": "7a1c0d9", "book_version": BOOK, "valuation_date": "2026-10-06", "all_ok": True,
                              "n_rows": 9842, "n_bad": 0, "rows": control_rows()}, **SIGN}


def control_rows():
    """Сводка сверки в форме писателя: diff — в единицах строки, diff_rel — относительная, вид допуска — tol_kind."""
    spec = [("передача: сдвиг спредов активов σ0", "pp", -0.0021, -0.0021, 1e-6, "abs", None),
            ("кредитная маржа стационара, мир M", "pp", 0.0362, 0.0362, 1e-6, "abs", None),
            ("передача: реализованная M − N", "number", 0.125, 0.125, 1e-6, "abs", None),
            ("V0 слоя «свой макро-взгляд»", "bn", 1077.41, 1074.5, 0.03, "rel", None),
            ("цена: точка при λ книги", "rub", 360.76, 359.3, 0.03, "rel", None),
            ("операционная прибыль акционеров 2027, клетка мира H, нормализация, по графику", "bn", 261.2, 259.9, 0.1, "rel", 6.2),
            ("резервы 2027, клетка мира N, кризис, по графику", "bn", 334.74, 336.06, 0.1, "rel", None),
            ("Н20.0 на конец 2027, клетка мира H, спад, по графику", "pct", 0.12294, 0.12262, 0.003, "abs", None),
            ("избыток капитала на терминале, клетка мира M, мягкая посадка, по графику", "bn", 21.6, 17.3, 55.0, "abs", None),
            ("DPS 2029, клетка мира M, спад, жёсткий", "rub", 29.12, 29.84, 0.1, "rel", 1.3),
            ("доля прироста 2027, клетка мира H, спад, жёсткий", "pct", 0.482, 0.4795, 0.01, "abs", None),
            ("вероятность режима «кризис» после A-P2u", "pct", 0.142, 0.142, 0.02, "abs", None),
            ("мост объявленных дивидендов", "bn", 0.0, 0.0, 0.01, "rel", None)]
    rows = []
    for what, unit, core, control, tol, kind, tol_abs in spec:
        diff = r(control - core, 6)
        rel = None if core == 0 else r(control / core - 1, 6)
        ok = (abs(rel) <= tol if rel is not None else diff == 0) if kind == "rel" else abs(diff) <= tol
        row = {"what": what, "unit": unit, "core": core, "control": control, "diff": diff, "diff_rel": rel, "tol": tol, "tol_kind": kind,
               "ok": ok or (tol_abs is not None and abs(diff) <= tol_abs)}
        if tol_abs is not None:
            row["tol_abs"] = tol_abs
        rows.append(row)
    rows[1].update({"diff": 5.55e-17, "diff_rel": 1.53e-15})      # шум счёта: писатель хранит разность как есть, на экране она — ноль
    return rows


def make_inputs():
    row = lambda key, name, value, unit, as_of, source: {"key": key, "name": name, "value": value, "unit": unit, "as_of": as_of, "source": source, "status": "ok"}  # noqa: E731
    return {"rows": [row("price.T", "Цена акции", PRICE, "rub", VDATE, "Мосбиржа, TQBR, 18:49 МСК"),
                     row("curve", "Кривая ОФЗ (5 лет)", 0.1597, "share", VDATE, "Мосбиржа, кривая бескупонной доходности"),
                     row("key_rate", "Ключевая ставка", 0.15, "share", "2026-09-11", "ЦБ"),
                     row("register", "Реестр дивидендов", 2, "count", VDATE, "документы эмитента; брокерский календарь дивидендов"),
                     row("book", "Книга допущений", BOOK, "version", "2026-10-06", "машинная книга допущений"),
                     row("facts", "Факты якоря", "2026Q2", "period", FACTS_DATE, "факты отчётности: МСФО за шесть месяцев 2026 года")]}


def make_live():
    return {"applied": True, "degraded": [], "degraded_flag": False, "valuation_date": VDATE, "fetched_at": "2026-10-07T16:04:31+00:00",
            "prices": {MAIN: {"value": PRICE, "date": VDATE, "time": "18:49", "accepted": True, "status": "live", "reason": None,
                              "last_accepted": {"value": PRICE, "date": VDATE}}},
            "curve": {"as_of": VDATE, "nodes": {"1": 0.1352, "3": 0.1512, "5": 0.1597, "10": 0.1629},
                      "book_nodes": {"1": 0.136, "3": 0.1548, "5": 0.1614, "10": 0.1646}, "shift_bp": {"5": -17, "10": -17}},
            "key_rate": {"value": 0.15, "date": VDATE, "since": "2026-09-11"},
            "register": {"as_of": VDATE, "entries": 2,
                         "note": "реестр сборщиков (документы эмитента, брокерский календарь) и факты книги; в оценку — объявленные с экс-датой позже даты фактов"},
            "book_date": "2026-10-06", "book_age_days": 1}


def make_changes(median, central):
    rows = [("valuation_date", "Перекат даты оценки", 0.6, 0.5, "06.10.2026 → 07.10.2026"), ("register", "Реестр дивидендов", 0.0, 0.0, ""),
            ("facts", "Факты и перезаякоривание", 0.0, 0.0, ""), ("book", "Суждения книги", 1.5, 1.6, f"книга {BOOK_PREV} → {BOOK}; сюда входит и смена кода ядра"),
            ("worlds", "Миры", 0.0, 0.0, ""), ("engine", "Код ядра", 0.0, 0.0, "входит в строку «Суждения книги»"), ("rounding", "Округление", 0.0, 0.0, "")]
    digest = lambda s: hashlib.sha256(s).hexdigest()  # noqa: E731
    return {"vs_previous": {"previous_sha": "4b0e4f6a1c2d", "previous_generated_at": "2026-10-06T16:04:55+00:00", "previous_published_at": "2026-10-06T16:06:10+00:00",
                            "rows": [{"component": c, "title": t, "point_rub": p, "median_rub": m, "note": n} for c, t, p, m, n in rows], "walk_book": [],
                            "total_point_rub": 2.1, "total_median_rub": 2.1, "market_price": {MAIN: {"from": 268.4, "to": PRICE}},
                            "reference": {"median": r(median - 2.1), "point": r(central - 2.1), "exdate_adjustment": 0.0},
                            "note": f"книга {BOOK_PREV} → {BOOK}; факты те же"},
            "snapshot": {"valuation_date": VDATE, "prices": {MAIN: PRICE}, "price_dates": {MAIN: VDATE}, "register": [], "book_version": BOOK,
                         "book_digest": digest(b"book"), "facts_digest": digest(b"facts"), "worlds_digest": digest(b"worlds"), "facts_date": FACTS_DATE}}


def make_valuation_history(median):
    rows = {"date": [], "sha": [], "median": [], "p10": [], "p25": [], "p75": [], "p90": [], "point": [], "price": {MAIN: []}}
    px, ex, dps = 296.0, "2026-08-10", 4.6 * N_OUT / N_DIV          # после экс-даты оценка падает на DPS × акции в обращении / делитель
    for i in range(0, 99, 3):
        day = (date(2026, 7, 1) + timedelta(days=i)).isoformat()
        if day >= VDATE:
            break
        m = median - 9 + 0.09 * i + (dps if day < ex else 0)
        px *= math.exp(RNG.gauss(-0.002, 0.012))
        if day >= ex and not any(x >= ex for x in rows["date"]):
            px -= 4.6
        rows["date"].append(day)
        rows["sha"].append(hashlib.sha256(day.encode()).hexdigest()[:12])
        for key, shift in (("median", 0), ("p10", -58), ("p25", -30), ("p75", 29), ("p90", 55), ("point", 10)):
            rows[key].append(r(m + shift))
        rows["price"][MAIN].append(r(px))
    rows.update({"rollbacks": [5], "book_changes": [{"date": "2026-09-18", "from": "0.9", "to": BOOK_PREV}],
                 "rule": "день — последняя строка дня (МСК); старше 180 дней — недели; старше двух лет — месяцы; не больше 400 строк",
                 "source": "история публикаций в репозитории данных"})
    return rows


# справочные варианты — в порядке списка книги; выпуск печатает их по убыванию модуля цены, главная развилка — первой
VARIANTS = (("fade_symmetric", "Угасание избыточной доходности в обе стороны", 1.4), ("kappa_zero", "Стоимость риска не зависит от реальной ставки", 9.8),
            ("divisor_earned", "Делитель с заработанной долей программы мотивации", -6.2), ("no_instrument_cost", "Без стоимости новых инструментов капитала", 7.1),
            ("catch_up", "Урезанный рост навёрстывается: четверть разрыва за квартал", 5.3),
            ("window_in_modal_cell", "Уровень окна фактов — в модальной клетке мира «Высокие ставки надолго»", -118.6),
            ("near_shift_stays", "Расхождение маржи ближнего квартала с механикой книг не сходит", -64.2),
            ("funds_need", "Премия роста средств клиентов — на уровне нужды баланса", 21.4), ("funds_fact", "Премия роста средств клиентов — на уровне фактов", -17.9))
VARIANT_NOTES = {"window_in_modal_cell": "Модальная клетка варианта печатает после фазы роста маржу 9,7 % и расходы к доходам 47,6 % — рядом с уровнями окна, а не ровно их"}
# книга с записью сухого перевывода развилок (М§14.5): разность медиан, пометка медианы, строка без цены — последней
VARIANT_MEDIAN_MARKS = {"catch_up": "медиана — при вдвое большем допуске концов осей-связок (центр сошёлся; точка — точная цена)"}
VARIANT_NO_PRICE = ("level_window_gate", "Уровень мира на составе окна фактов",
                    "без цены: вариант несовместим с гейтом стоимости средств клиентов к ключевой — центра в области гейта нет")
VARIANTS_BASIS = ("сухой перевывод книги под вариант (корни, концы осей и проверки выведены заново); точка — разность с точкой книги; "
                  "медиана — разность медиан малой полосы на общих случайных числах (600 прогонов)")


def make_book(central):
    return {"version": BOOK, "date": "2026-10-06", "tag": f"book-{BOOK}", "facts_date": FACTS_DATE, "curve_as_of": "2026-10-02",
            "worlds_source": "запись миров семейства 05.10.2026, кривые 02.10.2026",
            "key_judgements": [{"id": "A-N2", "name": "ЧПМ после фазы роста", "value": NIM_JUDGED, "unit": "pct"},
                               {"id": "A-N3", "name": "Передача ставки", "value": 0.125, "unit": "number"},
                               {"id": "A-P2b", "name": "P(кризис)", "value": 0.15, "unit": "pct"}],
            "changes_last": {"from_version": BOOK_PREV, "summary": "доля выплаты 26 % прибыли; запас менеджмента 1,5 п.п. сверх глиссады; инструменты капитала растут вместе с RWA"},
            # цена правил и развилок книги: точка на её цене и дате при одном изменённом правиле; в выпуске не пересчитывается
            "reference_variants": {"point": r(central), "basis": VARIANTS_BASIS, "rows": [
                {"id": k, "title": t, "point": r(r(central) + dv), "d_point": dv, "d_median": r(dv * 0.85, 2),
                 **({"note": VARIANT_NOTES[k]} if k in VARIANT_NOTES else {}),
                 **({"median_mark": VARIANT_MEDIAN_MARKS[k]} if k in VARIANT_MEDIAN_MARKS else {})}
                for k, t, dv in sorted(VARIANTS, key=lambda v: -abs(v[2]))] + [
                {"id": VARIANT_NO_PRICE[0], "title": VARIANT_NO_PRICE[1], "point": None, "d_point": None, "d_median": None, "why": VARIANT_NO_PRICE[2]}]}}


FORMS = ((OUT, build), (G.OUT, G.build))


def main(argv) -> int:
    for stream in (sys.stdout, sys.stderr):      # сообщения — по-русски и в консоли с чужой кодировкой
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    code = 0
    for path, make in FORMS:
        text = render(make())
        name = path.relative_to(ROOT).as_posix()
        if "--check" in argv:
            ok = path.exists() and path.read_text(encoding="utf-8") == text
            print(f"{name}: {'совпадает с генератором' if ok else 'разошлась с генератором'}")
            code = code or (0 if ok else 1)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"{name}: {len(text.encode('utf-8'))} байт")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
