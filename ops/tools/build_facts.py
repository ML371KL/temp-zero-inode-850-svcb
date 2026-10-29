"""Факты ПАО «Совкомбанк» (data/facts/*.json) из листов этапа 1 папки передачи.

Запуск из корня репозитория (нужна папка передачи; в CI не запускается — JSON закоммичены):

    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py            # переписать data/facts
    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py --check    # сверить с data/facts, не писать
    BANK_HANDOFF_DIR=<папка передачи> python -B ops/tools/build_facts.py --out DIR  # записать в DIR
    … build_facts.py --anchor 2026Q3 --out DIR [--report ОТЧЁТ.json]                # якорь — другой квартал
    … build_facts.py --anchor 2026Q3 --plan                                          # чего не хватает в листах квартала
    python -B ops/tools/build_facts.py --report ОТЧЁТ.json --facts DIR              # отчёт квартала из готовых фактов
    python -B ops/tools/build_facts.py --expected ОТЧЁТ.json --out DIR [--facts DIR]  # отчёт квартала → факты (без папки)
    python -B ops/tools/build_facts.py --forms ПЕРЕПИСЬ.txt [ВТОРАЯ.txt]            # тождества переписи форм-сканов

СОСТАВ — таблицы в начале файла: книги ЧПД (BOOKS — 13 книг: пять кредитных, бумаги, ликвидность, четыре книги
средств клиентов, опт, обязательства страховщиков), строки ОПУ движка (PNL_SLOTS; состав слота — лист
pnl_composition.csv), прочие активы и обязательства, проценты книг (INTEREST_LINES), окна и параметры. Числа якоря
приходят из листов этапа 1 по дате якоря; чисел, которых в листах нет, — таблица SHEET_GAPS (каждое — с документом и
страницей; на следующий квартал их кладут в листы, перечень печатает --plan).

Якорь — аргумент `--anchor` (по умолчанию — период закоммиченных фактов): квартал, дата, конец прошлого квартала и
года, нарастающий итог, ряд кварталов, окна истории капитала выводятся из него.

Читает (пути — от папки передачи):
  stage1/facts/sheets/*.csv          — листы потока facts этапа 1 (источник истины; состав — FACT_SHEETS);
  stage1/calib-nii/sheets/interest_lines_quarterly.csv — проценты по продуктам и источникам (книги ЧПД);
  stage1/round2/sheets/ecl_products.csv, ecl_rel.csv; stage1/round3/sheets/b7_mult.json — стоимость риска по книгам;
  stage1/round5/perimeter_series.csv — ряд поправок периметра (сверка числа с числом);
  stage1/round7/r7_1_misc_slope.json — ряд «прочего» и наклон прохождения переоценки (круг 7, на строке «бумаги и валюта»);
  research/facts/svcb-history/statements_long.csv — строка ССПУ квартала (metric fvtpl): наклон прохождения — регрессия
      строки ССПУ на переоценку (решения ведущего № 8, Р8-2; правило листа stage1/round8/r8_book.py, пункт misc);
  research/facts/svcb_capital_instruments.csv — инструменты капитала;
  research/samples/svcb-business_txt/*.txt — текстовый слой отчётности (страница числа, которого нет в листах);
  primary/DATABOOK_2010-1Q26.xlsx — справочник банка (резервы и валовые кредиты по продуктам, лист COR).
Каждое число — узел {"v", "src"} (документ, страница или ячейка, sha256) или {"v", "calc"} (формула из узлов);
нераскрытое — {"v": null, "calc": причина}. Схема — data/facts/SCHEMA.md, происхождение — docs/FACTS.md.

Сверки печатаются; при расхождении сборка останавливается, файлы не пишутся: баланс якоря по книгам; книги = листу
книг; прочие активы и обязательства = частям; тождество ОПУ каждого квартала; проценты книг = ЧПД движка; капитал
акционеров = строкам; акции и делитель дивиденда; решения о дивидендах (сумма = DPS × акции в расчёте); мосты =
средним окна; ряд периметра = листу круга.

`--report` пишет файл отчёта квартала якоря (`quarter-report/1`) — вход `ops/tools/reanchor.py --facts`.
`--plan` — перечень строк листов, которых не хватает для якоря `--anchor` (сборка идёт до конца, недостающее
собирается в список), и шаги квартала; код выхода 1, если чего-то нет.
`--forms` — тождества переписи форм-сканов ОПУ и ОФП (формат manual/*.txt соседа svcb-history: блоки `@doc …`);
с двумя файлами — ещё и сверка двух независимых переписей число с числом.
`--expected` — сухой прогон перезаякоривания (docs/MODEL.md §15.2, docs/REANCHOR.md): факты следующего квартала из
фактов якоря (`--facts`, по умолчанию data/facts) и отчёта квартала — того же `quarter-report/1`, что пишет
`ops/tools/reanchor.py --expected`. Папка передачи не нужна; пишет только в `--out`, и это не data/facts.

Код выхода: 0 — собрано (или --check: файлы совпали); 1 — расхождение, ошибка сверки или нет папки.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FACTS = REPO / "data" / "facts"

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 1. Книги ЧПД. Состав остатка книги — строки листа books_balances*.csv (книга → строки, итог TOTAL);
# проценты — столбцы листа процентов calib-nii (INTEREST_LINES). segment — сегмент стоимости риска кредитной книги.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
LOANS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans")
ASSET_BOOKS = LOANS + ("securities", "liquidity")
LIAB_BOOKS = ("retail_current", "retail_term", "corp_term", "corp_current", "wholesale", "insurance_liab")
FUNDS_BOOKS = ("retail_current", "retail_term", "corp_term", "corp_current")
BOOKS = ASSET_BOOKS + LIAB_BOOKS
RETAIL_LOANS = ("auto", "mortgage", "cash_loans", "cards")
INSURANCE_BOOK = "insurance_liab"          # 13-я книга (решения ведущего № 1, п. 6): обязательства страховщиков МСФО 17
# Строки листа книг: «книга» _nonworking_money — неработающие деньги вне книг (решения № 2, А1); служебные строки —
# итог книги TOTAL и средний квартала листа AVG_<квартал>.


def service_row(line: str) -> bool:
    return line == "TOTAL" or line.startswith("AVG_")


RU_LINES = {"loans_ac_auto_gross": "автокредиты", "loans_ac_mortgage_gross": "ипотечные кредиты",
            "loans_ac_consumer_gross": "потребительские кредиты", "loans_ac_installment_gross": "карты рассрочки «Халва»",
            "loans_ac_corp_gross": "кредиты корпоративным клиентам", "loans_ac_sme_other_gross":
            "кредиты малым предприятиям и прочие (с лизингом и кредитами ФЛ на индивидуальных условиях)",
            "loans_ac_municipal_gross": "кредиты субъектам и муниципалитетам", "loans_fvtpl": "корпоративные кредиты по СС",
            "sec_fvtpl_corp_bonds": "облигации корпоративных эмитентов ССПУ", "sec_fvtpl_gov_bonds": "облигации РФ и субъектов ССПУ",
            "sec_fvtpl_other_bonds": "облигации прочих эмитентов ССПУ", "repo_fvtpl_corp_bonds": "корпоративные облигации ССПУ в репо",
            "repo_fvtpl_gov_bonds": "облигации РФ ССПУ в репо", "sec_fvoci_debt_total": "долговые ССПСД (с ЦФА)",
            "sec_ac_bonds": "облигации по АС", "cash_and_equivalents_net": "денежные средства и эквиваленты (с обратным репо ≤ 90 дней)",
            "cash_st_deposits_reverse_repo": "краткосрочные депозиты и обратное репо ≤ 90 дней (прим. «Денежные средства»)",
            "cash_allowance": "резерв под обесценение денежных средств", "cbr_deposits_est": "депозиты в ЦБ [О]",
            "cbr_accounts": "счета в ЦБ РФ", "cbr_deposits_est_out": "минус депозиты в ЦБ [О]",
            "nostro": "счета «ностро»", "cash_on_hand": "наличные средства",
            "insurance_contract_liabilities": "обязательства по операциям страхования (МСФО 17, общая модель)",
            "mandatory_reserves": "обязательные резервы в ЦБ", "due_from_banks_net": "средства в банках",
            "dep_ind_current": "текущие счета ФЛ", "dep_ind_term": "срочные депозиты ФЛ", "dep_corp_term": "срочные депозиты ЮЛ",
            "dep_corp_current": "текущие счета ЮЛ", "due_to_cbr": "средства ЦБ", "due_to_banks": "депозиты и счета банков",
            "debt_securities": "выпущенные долговые бумаги", "sub_debt": "субординированная задолженность",
            "other_borrowed": "прочие заёмные средства"}
FVTPL_BONDS = ("sec_fvtpl_corp_bonds", "sec_fvtpl_gov_bonds", "sec_fvtpl_other_bonds", "repo_fvtpl_corp_bonds",
               "repo_fvtpl_gov_bonds")   # долговые ССПУ (собственные и в репо) — узел securities.fvtpl_bonds
FUNDS_LINES = (("retail_current", "dep_ind_current"), ("retail_term", "dep_ind_term"), ("corp_term", "dep_corp_term"),
               ("corp_current", "dep_corp_current"))
# Проценты книги квартала — столбцы листа процентов (строки примечания «Процентные доходы и расходы», млн ₽; у пассивов —
# со знаком минус, в узле — величиной). Проценты книги insurance_liab — финансовые расходы страхования (лист
# ins_finance_quarterly.csv). Порядок столбцов — порядок сложения (как в листе calib-nii).
INTEREST_LINES = {"auto": ("ii_auto",), "mortgage": ("ii_mortgage",), "cash_loans": ("ii_consumer",), "cards": ("ii_cards",),
                  "corp_loans": ("ii_corp", "ii_lease"), "securities": ("ii_fvtpl", "ii_fvoci", "ii_ac_bonds", "ii_ac_bank_bonds"),
                  "liquidity": ("ii_banks",), "retail_current": ("ie_ind_current",), "retail_term": ("ie_ind_term",),
                  "corp_term": ("ie_corp_term", "ie_corp_repo"), "corp_current": ("ie_corp_current",),
                  "wholesale": ("ie_banks", "ie_debt_sec", "ie_sub_debt", "ie_dfa", "ie_other_borrowed")}
INTEREST_OUTSIDE = ("ii_swaps", "ie_lease")   # проценты вне книг (остаются в ЧПД, в ставки книг не входят)
INTEREST_SHEET = "stage1/calib-nii/sheets/interest_lines_quarterly.csv"

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 2. Строки ОПУ движка (отчётный базис: прибыль движка — отчётная прибыль акционеров Банка). Состав каждого
# слота и формула квартала — лист pnl_composition.csv; SLOT_SRC_LINES — строки листа нарастающих итогов, на которые
# ссылается источник узла (первая — та, чья формула квартала печатается).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
PNL_SLOTS = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "misc_net", "noncore_net", "opex", "pbt", "tax", "ni",
             "ni_shareholders", "ni_nci", "dia", "fee_income", "fee_expense", "guarantee_provisions", "oci_total",
             "ci_total", "ins_finance_expense", "nii_form", "insurance_net_form")
PNL_REPORTED_SLOTS = ("pbt", "tax", "ni", "ni_shareholders", "ni_nci", "fee_income", "fee_expense", "oci_total", "ci_total",
                      "nii_form", "insurance_net_form")   # формула квартала — сама строка листа
PNL_SUM = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex", "misc_net")   # = pbt
SLOT_SRC_LINES = {"nii": ["nii", "ins_fin"], "llp_debt_fa": ["ecl"], "fees_net": ["fee_inc", "fee_exp", "oth_imp"],
                  "insurance_net": ["nb_net", "ins_fin"], "ins_finance_expense": ["ins_fin"], "nii_form": ["nii"],
                  "insurance_net_form": ["nb_net"], "opex": ["staff", "ga"], "pbt": ["pbt"], "tax": ["tax"], "ni": ["np"],
                  "ni_shareholders": ["np_sh"], "ni_nci": ["np_nci"], "misc_net": ["oth_bank", "reval"],
                  "noncore_net": ["oth_opinc"], "fee_income": ["fee_inc"], "fee_expense": ["fee_exp"], "dia": ["dep_ins"],
                  "oci_total": ["oci"], "ci_total": ["ci"], "guarantee_provisions": ["oth_imp"]}
YEAR_LINES = (("pbt", "pbt"), ("tax", "tax"), ("ni", "np"), ("ni_shareholders", "np_sh"), ("ni_nci", "np_nci"))
NONCORE_PARTS = (("bargain", "bargain_gain", "доход от выгодного приобретения"),
                 ("preexist", "preexisting_settlement", "доход от урегулирования ранее существовавших отношений"),
                 ("subsettle", "subdebt_settlement", "доход от урегулирования обязательств по субординированным облигациям"),
                 ("day1", "day1_ecl_acquired", "резерв «первого дня» по кредитам приобретённого бизнеса"))
INS_FIN_ESTIMATED = ("2023Q1", "2023Q2", "2023Q3")   # финрасходы страхования — оценка листа (до МСФО 17 в сканах)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ТАБЛИЦА 3. Прочие активы и обязательства (части — строки ОФП листа balance_anchor.csv и узлы книг).
# Постоянные прочие активы (не растут с кредитами) — ассоциированные, гудвил, ОНА (решения ведущего № 1, п. 14; № 2, А1).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
OTHER_ASSETS = (("associates", "bs_assoc", "ассоциированные компании"),
                ("investment_property", "bs_invprop", "инвестиционная собственность"),
                ("ppe_intangibles", "bs_ppe", "основные средства и нематериальные активы"),
                ("rou", "bs_rou", "активы в форме права пользования"),
                ("goodwill", "bs_goodwill", "гудвил"),
                ("current_tax", "bs_curtax_a", "текущий налог к возмещению"),
                ("deferred_tax", "bs_dta", "отложенный налоговый актив"))
OTHER_ASSETS_FIXED = ("associates", "goodwill", "deferred_tax")
EQUITY_LINES = (("share_capital", "bs_sh_cap"), ("other_contributions", "bs_oth_contrib"), ("reval_buildings", "bs_reval_res"),
                ("fvoci_reserve", "bs_fvoci_res"), ("retained_earnings", "bs_re"))   # вместе = капитал без бессрочных

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Параметры сборщика (не допущения модели): начала рядов, окна, листы, срез.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
PNL_FIRST = "2023Q1"             # первый квартал ОПУ (МСФО 17 и нынешний учёт ССПУ; 2022 — без квартальной МСФО)
BRIDGE_HISTORY_FIRST = "2024Q1"  # первый квартал истории мостов упр. ↔ движок
CAPITAL_HISTORY_FIRST = "2025Q1" # первый квартал истории нормативов банка в capital.history
HORIZON_YEARS = 10               # last_period якоря — четвёртый квартал года якоря + 10
SNAPSHOT = dict(sheets_as_of="2026-10-21",   # дата среза листов этапа 1 (календарь, аналоги, гайденс, стартовый реестр)
                valuation_date="2026-10-20")  # дата оценки книги, на которую собраны факты (справка anchor.json)
TICKER = "SVCB"
ISSUER = "ПАО «Совкомбанк»"
BANK = "ПАО «Совкомбанк», рег. № 963"
FACT_SHEETS = "stage1/facts/sheets"
INSTRUMENTS_SHEET = "research/facts/svcb_capital_instruments.csv"
TEXT_LAYER = "research/samples/svcb-business_txt"
DATABOOK = "primary/DATABOOK_2010-1Q26.xlsx"
ECL_PRODUCTS, ECL_REL = "stage1/round2/sheets/ecl_products.csv", "stage1/round2/sheets/ecl_rel.csv"
B7_SHEET = "stage1/round3/sheets/b7_mult.json"
PERIMETER_SHEET = "stage1/round5/perimeter_series.csv"
MISC_SHEET = "stage1/round7/r7_1_misc_slope.json"
MISC_STATEMENTS = "research/facts/svcb-history/statements_long.csv"   # строка ССПУ квартала (metric fvtpl; Р8-2)
POLICY_DOC = "POLICY_dividend_v2_2023-11-20.pdf"
PEER_ORDER = ["SBER", "VTBR", "T", "BSPB", "MBNK"]

# Числа якоря, которых нет в листах этапа 1 (их нёс черновой сборщик литералами). Каждое — с документом и страницей
# (страница проверяется по текстовому слою, где он есть). На следующий квартал их кладут в листы (`--plan` печатает,
# куда); сборщик сначала ищет строку листа balance_anchor.csv с тем же именем и датой якоря, потом — эту таблицу.
SHEET_GAPS = {
    "2026Q2": {
        "allowance_ac": (151.719, "2026Q2_ifrs_fs.pdf", "24"),            # резерв под обесценение кредитов и облигаций по АС
        "allowance_retail": (87.939, "2026Q2_ifrs_fs.pdf", "24"),         # его части: физлица
        "allowance_corporate": (63.780, "2026Q2_ifrs_fs.pdf", "24"),      #   юрлица
        "fvoci_gov_bonds": (27.914, "2026Q2_ifrs_fs.pdf", "32"),          # долговые ССПСД: облигации РФ
        "fvoci_corp_bonds": (23.154, "2026Q2_ifrs_fs.pdf", "32"),         #   корпоративные
        "fvoci_dfa": (6.194, "2026Q2_ifrs_fs.pdf", "32"),                 #   цифровые финансовые активы
        "fvoci_equity": (0.763, "2026Q2_ifrs_fs.pdf", "32"),              # акции ССПСД
        "fvtpl_derivatives": (6.329, "2026Q2_ifrs_fs.pdf", "23"),         # ПФИ внутри строки ССПУ ОФП
        "fvtpl_equity_own": (43.155, "2026Q2_ifrs_fs.pdf", "23"),         # акции и паи ССПУ собственные (слова)
        "fvtpl_equity_other": (0.001, "2026Q2_ifrs_fs.pdf", "23"),        #   прочие (слова)
        "fvtpl_equity_repo": (0.001, "2026Q2_ifrs_fs.pdf", "23"),         #   в репо (слова)
        "fvtpl_floating_share": (0.365, "2026Q2_ifrs_fs.pdf", "24"),      # доля бумаг с плавающей ставкой в долговых ССПУ
        "insurance_reinsurance_assets": (0.616, "2026Q2_ifrs_fs.pdf", "39"),   # «Страховые активы» в прочих активах
        "lease_gross": (100.261, "FY2025_ifrs_fs.pdf", "53"),             # чистые инвестиции в аренду (годовой отчёт)
        "due_to_cbr_repo": (41.190, "2026Q2_ifrs_fs.pdf", "34"),          # репо внутри средств ЦБ (слова)
        "min_n1_0_with_buffers": (0.100, "research/facts/svcb_capital.csv", ""),   # требование Н1.0 с надбавками СЗКО
        "regular_fvtpl_coupon_ytd": (14.446, "2026Q2_ifrs_fs.pdf", "13"),
        "ins_finance_note": (2.365, "2026Q2_ifrs_fs.pdf", "19"),          # финрасходы страхования квартала (прим. 7, страница)   # купон ССПУ в «регулярной» прибыли (прим. 3)
        "at1_coupon_annual_low": (1.88, "", ""),                          # диапазон оценки годового купона [В]
        "at1_coupon_annual_high": (2.08, "", ""),
    },
}
BUILT = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends", "bridge_mgmt_ifrs",
         "bridge_ras_ifrs", "mgmt_quarterly", "guidance", "calendar", "peers", "credit_products", "perimeter", "misc_window")
REPORT_SCHEMA = "quarter-report/1"


class BuildError(RuntimeError):
    """Нет листа, строки или документа; не сошлась сверка."""


# ------------------------------------------------------------------ периоды

def q_parse(p: str) -> tuple[int, int]:
    return int(p[:4]), int(p[5])


def q_range(a: str, b: str) -> list[str]:
    y, k = q_parse(a)
    out = []
    while f"{y}Q{k}" <= b:
        out.append(f"{y}Q{k}")
        y, k = (y + 1, 1) if k == 4 else (y, k + 1)
    return out


def q_end(p: str) -> dt.date:
    y, k = q_parse(p)
    return dt.date(y, 3 * k, 31 if k in (1, 4) else 30)


def q_prev(p: str) -> str:
    y, k = q_parse(p)
    return f"{y - 1}Q4" if k == 1 else f"{y}Q{k - 1}"


def q_next(p: str) -> str:
    y, k = q_parse(p)
    return f"{y + 1}Q1" if k == 4 else f"{y}Q{k + 1}"


def q_days(p: str) -> int:
    return (q_end(p) - q_end(q_prev(p))).days


def q_of_date(iso: str) -> str:
    y, m = int(iso[:4]), int(iso[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def d_ru(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def q_ru(p: str) -> str:
    """2К2026 — квартал в словах."""
    return f"{p[5]}К{p[:4]}"


def qk(p: str) -> str:
    """2026К2 — квартал в подписях окон."""
    return f"{p[:4]}К{p[5]}"


CUM_OF = {1: "3M", 2: "6M", 3: "9M", 4: "FY"}   # нарастающий итог квартала в именах листов


def ytd(p: str) -> str:
    y, k = q_parse(p)
    return f"{CUM_OF[k]}{y}"


class Anchor:
    """Квартал якоря и всё, что из него выводится."""

    def __init__(self, period: str):
        if not re.fullmatch(r"20\d\dQ[1-4]", period or ""):
            raise BuildError(f"якорь {period!r}: нужен квартал вида ГГГГQк")
        self.period = period
        self.y, self.k = q_parse(period)
        self.date = q_end(period).isoformat()
        self.prev = q_prev(period)
        self.open_date = q_end(self.prev).isoformat()
        self.prev_year_end = dt.date(self.y - 1, 12, 31).isoformat()
        self.next = q_next(period)
        self.ytd = ytd(period)
        self.ytd_prev = ytd(self.prev) if self.k > 1 else None
        self.form_date = (q_end(period) + dt.timedelta(days=1)).isoformat()
        self.days = q_days(period)
        self.quarters = q_range(PNL_FIRST, period)
        self.report_doc = f"FY{self.y}_ifrs_fs.pdf" if self.k == 4 else f"{period}_ifrs_fs.pdf"
        self.open_doc = f"FY{self.y - 1}_ifrs_fs.pdf" if self.k == 1 else f"{self.prev}_ifrs_fs.pdf"
        self.ru = d_ru(self.date)
        self.q_ru = q_ru(period)
        self.ytd_ru = self.ytd.replace("M", "М")

    def __repr__(self) -> str:
        return f"Anchor({self.period})"


def default_anchor() -> str:
    try:
        return str(json.loads((FACTS / "anchor.json").read_text(encoding="utf-8"))["period"])
    except (OSError, KeyError, ValueError) as e:
        raise BuildError(f"нет data/facts/anchor.json с периодом якоря ({e}); задайте --anchor") from e


# ------------------------------------------------------------------ числа и узлы

def r6(x) -> float:
    return round(float(x) + 0.0, 6)


def r9(x) -> float | None:
    return None if x is None else round(float(x) + 0.0, 9)


def ru(x: float, nd: int = 3) -> str:
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


def node(v, src=None, calc=None, **kw) -> dict:
    n = {"v": v}
    if src:
        n["src"] = src
    if calc:
        n["calc"] = calc
    n.update(kw)
    return n


def est(v, calc, rng=None, src=None, **kw) -> dict:
    n = {"v": v}
    if src:
        n["src"] = src
    n["calc"] = calc
    n["estimated"] = True
    if rng is not None:
        n["range"] = [rng[0], rng[1]]
    n.update(kw)
    return n


def null(why: str, **kw) -> dict:
    return {"v": None, "calc": why, **kw}


na = null


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def dig(obj, dotted: str):
    for part in dotted.split("."):
        obj = obj[part]
    return obj


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------ листы и недостающее

class Missing(dict):
    """Строка листа, которой нет: в режиме --plan сборка идёт дальше на «пустых» числах, строка — в перечень."""

    def __missing__(self, key):
        return "nan"


class Ctx:
    """Листы этапа 1, документы, сверки и перечень недостающего (режим --plan)."""

    def __init__(self, root: Path, anchor: Anchor, *, plan: bool = False):
        self.root, self.a, self.plan = root, anchor, plan
        self.checks: list[tuple[str, bool, str]] = []
        self.missing: list[str] = []
        self.notes: list[str] = []
        self.carry_from: Path | None = None    # откуда переносить узлы калибровки книги на другом якоре
        sh = root / FACT_SHEETS
        if not sh.is_dir():
            raise BuildError(f"нет каталога листов {sh}")
        rd = lambda name: read_csv(self.need_file(sh / name))   # noqa: E731
        self.docs = {os.path.basename(r["file"]): r for r in rd("documents.csv")}
        self.bb = rd("books_balances.csv") + rd("books_balances_history.csv")
        self.bb_liab = rd("books_balances_liab_2024.csv")
        self.bal = {r["metric"] + "@" + r["date"]: r for r in rd("balance_anchor.csv")}
        self.cmp = {(r["period"], r["slot"]): r for r in rd("pnl_composition.csv")}
        self.ql = {(r["period"], r["metric"]): r for r in rd("pnl_quarterly_lines.csv")}
        self.cum = {(r["metric"], r["period"]): r for r in rd("pnl_cumulative.csv")}
        self.named = {(r["item"], r["period"]): r for r in rd("pnl_named_items.csv")}
        self.eqf = {(r["item"], r["period"]): r for r in rd("equity_flows.csv")}
        self.capb = {r["form_date"]: r for r in rd("capital_bank.csv")}
        self.capg = {(r["metric"], r["date"]): r for r in rd("capital_group_databook.csv")}
        self.ofz = {(r["date"], r["period_y"]): r for r in rd("ofz_curve.csv")}
        self.key = {r["period"]: r for r in rd("key_rate_quarterly.csv")}
        self.shr = {(r["metric"], r["date"]): r for r in rd("shares.csv")}
        self.acts = rd("corporate_actions.csv")
        self.div = rd("dividends.csv")
        self.divb = rd("dividends_before.csv")
        self.pol = {r["key"]: r for r in rd("dividend_policy.csv")}
        self.cal = rd("calendar.csv")
        self.peers = rd("peers.csv")
        self.ras = rd("ras_bridge.csv")
        self.guid = rd("guidance.csv")
        self.hist = {r["date"]: r for r in rd("balance_history.csv")}
        self.kpi = {(r["metric"], r["period"]): r for r in rd("mgmt_kpi.csv")}
        self.brg = {(r["metric"], r["period"]): r for r in rd("bridges.csv")}
        self.brs = {r["metric"]: r for r in rd("bridges_summary.csv")}
        self.instr = read_csv(self.need_file(root / INSTRUMENTS_SHEET))
        self.interest = {r["period"]: r for r in read_csv(self.need_file(root / INTEREST_SHEET))}
        self._pages: dict[str, list[tuple[int, str]]] = {}
        if anchor.report_doc not in self.docs:
            self.miss(f"{FACT_SHEETS}/documents.csv: {anchor.report_doc} (отчёт квартала якоря — реестр документов, sha256)")

    # --- доступ с перечнем недостающего
    def need_file(self, path: Path) -> Path:
        if not path.is_file():
            raise BuildError(f"нет листа {path.relative_to(self.root) if self.root in path.parents else path}")
        return path

    def miss(self, what: str) -> Missing:
        if what not in self.missing:
            self.missing.append(what)
        if not self.plan:
            raise BuildError(f"нет строки листа: {what}")
        return Missing()

    def get(self, table: dict, key, what: str):
        r = table.get(key)
        return r if r is not None else self.miss(what)

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, bool(ok), detail))

    # --- документы
    def S(self, doc, page="") -> str:
        """«файл, с. N, sha256 <16>»; doc — путь или имя; несколько — через «|» (страницы тоже)."""
        docs = [d.strip() for d in str(doc).split("|") if d.strip()]
        pgs = [p.strip() for p in str(page).split("|")] if page != "" else [""] * len(docs)
        out = []
        for i, d in enumerate(docs):
            b = os.path.basename(d)
            p = pgs[i] if i < len(pgs) else pgs[-1]
            p = p.replace("с.", "").strip()
            place = ""
            if p:
                place = (", с. " + p) if all(ch.isdigit() or ch in "–-; " for ch in p) else (", " + p)
            h = self.docs[b]["sha256"][:16] if b in self.docs else None
            out.append(f"{b}{place}" + (f", sha256 {h}" if h else ""))
        return "; ".join(out)

    # --- лист книг
    def book_total(self, book: str, date: str) -> dict:
        rows = [r for r in self.bb if r["book"] == book and r["date"] == date and r["line"] == "TOTAL"]
        return rows[0] if rows else self.miss(f"{FACT_SHEETS}/books_balances.csv: {book} TOTAL на {date}")

    def book_lines(self, book: str, date: str) -> list[dict]:
        rows = [r for r in self.bb if r["book"] == book and r["date"] == date and not service_row(r["line"])]
        return rows or [self.miss(f"{FACT_SHEETS}/books_balances.csv: строки книги {book} на {date}")]

    def lines_at(self, date: str) -> dict[str, float]:
        """Строки листа книг на дату → млрд ₽ (значение строки, без итогов)."""
        return {r["line"]: float(r["value_mn"]) / 1000 for r in self.bb if r["date"] == date and not service_row(r["line"])}

    def line(self, lines: dict[str, float], name: str, date: str) -> float:
        if name in lines:
            return lines[name]
        self.miss(f"{FACT_SHEETS}/books_balances.csv: строка {name} на {date}")
        return math.nan

    def line_row(self, name: str, date: str) -> dict:
        rows = [r for r in self.bb if r["date"] == date and r["line"] == name]
        return rows[0] if rows else self.miss(f"{FACT_SHEETS}/books_balances.csv: строка {name} на {date}")

    def line_page(self, name: str, date: str) -> str:
        return self.line_row(name, date)["page"].replace("с.", "")

    # --- строки ОФП и примечаний якоря
    def bal_row(self, metric: str, date: str | None = None) -> dict:
        d = date or self.a.date
        return self.get(self.bal, metric + "@" + d, f"{FACT_SHEETS}/balance_anchor.csv: {metric} на {d}")

    def bv(self, metric: str, date: str | None = None) -> float:
        return float(self.bal_row(metric, date)["value_mn"]) / 1000

    def bsrc(self, metric: str, date: str | None = None) -> str:
        r = self.bal_row(metric, date)
        return self.S(r["doc"], r["page"])

    def gap(self, name: str) -> tuple[float, str, str]:
        """Число якоря вне листов: строка balance_anchor.csv с тем же именем, иначе таблица SHEET_GAPS."""
        r = self.bal.get(name + "@" + self.a.date)
        if r is not None:
            return float(r["value_mn"]) / 1000, os.path.basename(r["doc"]), str(r["page"])
        g = SHEET_GAPS.get(self.a.period, {}).get(name)
        if g is None:
            self.miss(f"{FACT_SHEETS}/balance_anchor.csv: {name} на {self.a.date} (число якоря, которого не было в листах — "
                      f"SHEET_GAPS)")
            return math.nan, self.a.report_doc, ""
        return g

    def gv(self, name: str) -> float:
        return self.gap(name)[0]

    # --- текстовый слой отчётности (страница числа)
    def pages(self, doc: str) -> list[tuple[int, str]]:
        if doc not in self._pages:
            out, pg = [], 0
            path = self.root / TEXT_LAYER / f"{doc}.txt"
            if not path.is_file():
                self.miss(f"{TEXT_LAYER}/{doc}.txt (текстовый слой отчёта)")
                self._pages[doc] = []
                return []
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    m = re.match(r"=== PAGE (\d+) ===", ln)
                    if m:
                        pg = int(m.group(1))
                        continue
                    out.append((pg, ln.rstrip("\n")))
            self._pages[doc] = out
        return self._pages[doc]


def fmt_mn(v: float) -> str:
    """Число млн ₽ так, как его печатает отчёт: 1 029 221; отрицательное — в скобках."""
    s = f"{abs(int(round(v))):,}".replace(",", " ")
    return f"({s})" if v < 0 else s


MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
              "ноября", "декабря")
MONTHS_PREP = ("январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
               "ноябре", "декабре")
PERIOD_WORDS = {1: "3 месяца", 2: "6 месяцев", 3: "9 месяцев", 4: "12 месяцев"}

# Слова якоря, которых из листов не вывести (суждения и справки потока facts этапа 1, с числами вне листов).
# Ключ — период якоря; на другом якоре сборщик печатает общие слова без этих справок (перечень — --plan).
# Постоянные слова фактов с датами, к якорю не привязанными (раскрытия, источники, срезы соседей) — именованным
# параметром, чтобы в теле функций сборщика не было календаря.
GROUP_FORM_LAST = "01.04.2025"   # последняя опубликованная форма 0409805 банковской группы (рег. № 963)
BROKER_SNAPSHOT = "календарём дивидендов брокера T-Invest (снимок соседа svcb-capital-shares, 21.10.2026)"
# Ответ брокера — не источник данных (гигиена публичного репозитория, tests/test_public_hygiene.py): строки листов этапа 1
# называют метод API и поле ответа — сборщик пишет вместо них слова; источник дивиденда — решение собрания и раскрытие эмитента,
# сверка с брокером — словами без метода.
BROKER_WORDS = (("T-Invest declaredDate", "дата решения — по календарю дивидендов брокера T-Invest"),
                ("T-Invest GetDividends", "сверка — календарь дивидендов брокера T-Invest"))


def broker_words(text: str) -> str:
    """Строка листа этапа 1 без метода API и поля ответа брокера (BROKER_WORDS); прочее — как в листе."""
    for old, new in BROKER_WORDS:
        text = text.replace(old, new)
    return text


# Строки календаря печатает витрина (PAYLOAD §0.2): метка класса листа — «[оценка]» (у события и так признак estimated:
# окно и «≈» на экране) и «[НП]» (не проверено — словами в самой заметке) — не печатаются; дата без года после «до»
# читается как дробь — год берётся из даты события.
CAL_MARKS = re.compile(r"\s*\[(?:оценка|НП)\]")
CAL_SHORT_DATE = re.compile(r"(?<=до )(\d{1,2})\.(\d{2})(?![.\d])")


def calendar_words(text: str, year: int) -> str:
    """Заголовок или заметка события листа календаря — словами для экрана: без меток класса, «до 31.01» → «до 31 января
    <год события> года»."""
    text = CAL_MARKS.sub("", text).strip()
    return CAL_SHORT_DATE.sub(lambda m: f"{int(m.group(1))} {MONTHS_GEN[int(m.group(2)) - 1]} {year} года", text)


# Таблицы исследования в реестре документов якоря: лист называет их «Лист фазы 1 (исследование): <путь>», а название
# документа печатает витрина как источник факта (model/payload.py, _src_words) — словами, без пути и имени файла.
RESEARCH_TITLES = {
    "research/facts/sdn/bridge_ras_ifrs_quarterly.csv": "квартальный мост прибыли РСБУ банка и МСФО группы",
    "research/facts/svcb-history/key_rate_daily.csv": "ключевая ставка Банка России по дням",
    "research/facts/svcb-history/manual_long.csv": "ручная перепись форм отчётности МСФО группы",
    "research/facts/svcb-regulation-macro/calendar_2026Q4_2028.tsv": "календарь регулирования и макроданных до 2028 года",
    "research/facts/svcb_capital.csv": "капитал и нормативы Совкомбанка",
    "research/facts/svcb_capital_instruments.csv": "инструменты капитала Совкомбанка",
    "research/facts/svcb_cbr_n1_capital_reg963.csv": "нормативы Н1 и капитал банка по формам Банка России",
    "research/facts/svcb_dividends.csv": "история дивидендов Совкомбанка",
    "research/facts/svcb_quarterly.csv": "квартальные показатели МСФО Совкомбанка",
    "research/facts/svcb_release_calendar.csv": "календарь публикаций и дивидендных дат Совкомбанка",
    "research/facts/svcb_shares.csv": "история акционерного капитала Совкомбанка",
    "research/samples/svcb-business_tg_irsovcombank_20261021.json": "посты канала IR Совкомбанка на 21.10.2026",
    "research/samples/svcb-capital-shares/iss_totals_SVCB_issuesize.csv": "число акций выпуска по данным Московской биржи",
}
RESEARCH_PREFIX = "Лист фазы 1 (исследование): "


def doc_title(r: dict) -> str:
    """Название документа реестра для экрана: таблица исследования — словами (RESEARCH_TITLES), прочие — как в листе."""
    if not r["title"].startswith(RESEARCH_PREFIX):
        return r["title"]
    if r["file"] not in RESEARCH_TITLES:
        raise BuildError(f"таблица исследования без названия словами: {r['file']} (RESEARCH_TITLES)")
    return f"Таблица исследования: {RESEARCH_TITLES[r['file']]}"
PROSE = {
    "insurance_book": "обязательства по операциям страхования = книга insurance_liab (п. 6): общая модель МСФО 17 (BBA) у "
                      "всех групп договоров — финансовые расходы начисляются на всю балансовую стоимость (ООЧП и ОВТ, FY2025 "
                      "прим. 11)",
    "tax_statutory": "законная ставка налога на прибыль года (20 % до 2024 года, 25 % с 2025 года)",
    "guidance_why": "не раскрыт в доступных источниках: «мартовский прогноз» 2026 года (звонок по МСФО 2025, март 2026) "
                    "упомянут в канале IR (пост 169: «идём по мартовскому прогнозу»), но его текст и числа — только во вложениях "
                    "постов 161, 176, 192 (решение владельца О6)",
    "guidance_note": "гайденс 2026 года — заглушка: чисел в доступной первичке нет; не выдумывать (договор ведущего)",
    "calendar_horizon": "до конца 2027 года: отчёты МСФО, решения о дивидендах, заседания Банка России, формы банка; ступень "
                        "требований 01.01.2028",
    "peers_note": "ведётся вручную: строки SBER, VTBR, BSPB, MBNK — без изменений из таблицы аналогов панели Т (peers.json, as_of "
                  "2026-10-01; её источники — в той панели); строка Т — из фактов панели Т на якоре {anchor}. Строки "
                  "Совкомбанка нет: её собирает выпуск из фактов.",
    "t_peers_title": "Таблица аналогов панели Т-Технологий (peers.json, as_of 2026-10-01)",
}

ANCHOR_WORDS = {
    "2026Q2": {
        "anchor_note": "якорь — МСФО группы ПАО «Совкомбанк» за 6 месяцев 2026 года (обобщённая промежуточная отчётность, "
                       "формы — сканы: числа форм — перепись соседа svcb-history, сведённая 651 тождеством; примечания — "
                       "текстовый слой). Цена рынка — LEGALCLOSEPRICE ISS (на 19.10.2026 — 10,105 ₽), её берёт сборщик "
                       "книги. Черновик потока facts этапа 1 (21.10.2026): собран скриптом "
                       "stage1/facts/code/build_draft_facts.py из листов stage1/facts/sheets; сборщик фактов Совкомбанка "
                       "(фаза 4) обязан воспроизвести эти файлы бит в бит.",
        "lease_words": "сумма по срокам 56,699 + 26,486 + 11,366 + 3,646 + 1,412 + 0,652",
        "pre_dividend_note": "Н1.0 на 01.07.2026 — до вычета дивиденда за 2025 год (7,856): решение ГОСА 30.06.2026, "
                             "реестр 13.07.2026, выплата до 28.07.2026; вычет из капитала банка — в месяце реестра "
                             "(июль), как у Сбера. Свидетельство: базовый капитал банка 01.07 → 01.08 падает в оба года "
                             "(2025: 326,1 → 315,2 при реестре 08.07.2025; 2026: 371,5 → 365,1) при положительной "
                             "прибыли месяца. Норматив после вычета ≈ 10,985 − 7,856 / 4 365,2 = 10,805 %.",
        "min_with_buffers_words": "требование Н1.0 с надбавками для СЗКО на 2026 год (10,0 %); 10,75 % с 01.01.2027, "
                                  "12,0 % с 01.01.2028 (лестница — лист регулирования)",
        "at1_coupon_annual_words": "годовой купон величиной (через капитал): 2 × купон 6М2026 0,990 = 1,980 [В]; за 2025 год — "
                                   "1,654, за 2024 год — 3,814 (до прекращения признания еврооблигаций в 1К2025); "
                                   "кварталы 2026: 0,519 и 0,471; в долларах — зависит от курса",
        "at1_coupon_quarter_words": "купон платится каждый квартал, слот ядра — одна годовая сумма в квартале "
                                    "coupon_quarter; 4 — по форме Сбера. За 6М2026 уже вычтено 0,990: решение ведущего "
                                    "№ 1, п. 13 — «остаток 2026 года» схемой не выражается (coupon_annual — одно "
                                    "число на все годы и терминал) — двойной вычет 0,990 × (1 − 0,25) = 0,743 в "
                                    "4К2026 — справочным вариантом потока капитала с ценой",
        "at1_fx_reval_words": "курсовая переоценка бессрочных через нераспределённую прибыль за 6М2026 (+0,121); "
                              "1К2026 −0,779, 2К2026 +0,900; годы: 2023 −7,333, 2024 −6,510, 2025 +11,943 (вкл. "
                              "прекращение признания)",
        "treasury_subsidiary_words": "куплены ООО «Совкомбанк Страхование Жизни» с 22.06.2026 (−0,161 млрд ₽ в капитале) [Р]",
        "buyback_note": "выкуп страховой дочкой: 2 млрд ₽ в квартал с 22.06.2026, 3 млрд ₽ в квартал с 07.10.2026 (на 30.06.2026 "
                        "куплено 14,94 млн акций); «продавать не планируем» (t.me/irsovcombank/196); путь выкупа — суждение книги",
        "register_seed_sources_2025": ["manual: материалы ГОСА 30.06.2026, с. 4 — 0,35 ₽, реестр 13.07.2026, выплата до "
                                       "28.07.2026",
                                       "news: пост 184 канала IR эмитента в Telegram (30.06.2026) — решение годового собрания "
                                       "акционеров; брокер T-Invest — последний день покупки 10.07.2026"],
        "register_seed_note": "решение 30.06.2026 с экс-датой 13.07.2026 позже якоря — запись реестра (status paid: выплачено в "
                              "июле 2026 года; обязательство 7,856 на якоре — balance.dividends_payable). У Сбера при том же "
                              "календаре список пуст — выбор формы за сборщиком; вклад записи в мост цены на 20.10.2026 — ноль "
                              "(вычет и экс-дата оба до даты оценки)",
        "bridge_cor_def_note": "; 2К2026 — оценка по напечатанной RAM",
        "bridge_cir_def_note": "; 2024К1–К3 и 2К2026 — расчёт по определению",
        "mgmt_note": "напечатанное (презентация 1П2026) — без суффикса; точное — с суффиксом _exact: ДАТАБУК банка (ячейка) до "
                     "1К2026, за 2К2026 — расчёт по определению банка из МСФО (ЧПМ 7,555 против напечатанных 7,6; C/I 42,4 "
                     "против 42), CoR 2К2026 — оценка (резерв по кредитам за квартал не раскрыт)",
        "ras_cor_why": "моста резервов нет: резервы РСБУ и МСФО несопоставимы поквартально (отношение 0,28–1,59)",
    },
}


def words(c: "Ctx", key: str, default: str | None = None) -> str | None:
    """Слова якоря из ANCHOR_WORDS; нет — общие слова `default` (и строка в перечне --plan)."""
    w = ANCHOR_WORDS.get(c.a.period, {}).get(key)
    if w is None:
        what = f"ops/tools/build_facts.py ANCHOR_WORDS[{c.a.period!r}][{key!r}] (слова якоря; без них — общие слова)"
        if what not in c.notes:
            c.notes.append(what)
    return w if w is not None else default


def int_ru(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def dec_ru(x: float) -> str:
    """Число как написано в отчёте, без лишних нулей: 0,35; 1,14; 0,10985."""
    return f"{x}".replace(".", ",")


def money_ru(x: float) -> str:
    """Рубли с копейками: 7 856 117 007,20."""
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


# ================================================================== anchor.json
def build_anchor(c: Ctx) -> dict:
    docs = [dict(key=r["key"], file=r["file"], sha256=r["sha256"], url=r["url"], title=doc_title(r))
            for r in sorted(c.docs.values(), key=lambda x: x["file"])]
    a = c.a
    generic = (f"якорь — МСФО группы {ISSUER} за {PERIOD_WORDS[a.k]} {a.y} года (обобщённая промежуточная отчётность, "
               f"формы — сканы: числа форм — перепись, сведённая тождествами; примечания — текстовый слой). Собран "
               f"ops/tools/build_facts.py из листов {FACT_SHEETS}.")
    return {
        "basis": "IFRS", "as_of": a.date, "period": a.period, "first_period": a.next,
        "last_period": f"{a.y + HORIZON_YEARS}Q4", "valuation_date": SNAPSHOT["valuation_date"],
        "note": words(c, "anchor_note", generic),
        "documents": docs,
    }


# ================================================================== balance.json
def comp_calc(c: Ctx, book: str, date: str) -> str:
    rows = c.book_lines(book, date)
    parts = [f"{RU_LINES.get(r['line'], r['line'])} {ru(float(r['value_mn']) / 1000)}" for r in rows if float(r["value_mn"]) != 0]
    return " + ".join(parts) + " (остатки валовые, млрд ₽)"


def line_src(c: Ctx, rows: list[dict]) -> str:
    seen, docs, pgs = [], [], []
    for r in rows:
        d = r["source"].split(" ")[0]
        p = r["page"].replace("с.", "")
        if (d, p) not in seen:
            seen.append((d, p))
            docs.append(d)
            pgs.append(p)
    return c.S("|".join(docs), "|".join(pgs))


def last_decision(c: Ctx) -> dict | None:
    """Последнее решение о дивиденде, принятое не позже якоря."""
    rows = sorted((r for r in c.div if r["decided_date"] <= c.a.date), key=lambda r: r["decided_date"])
    return rows[-1] if rows else None


def dividend_unpaid(c: Ctx) -> dict | None:
    """Решение о дивиденде, принятое не позже якоря и выплаченное после него (обязательство на дату якоря)."""
    rows = sorted((r for r in c.div if r["decided_date"] <= c.a.date < r["pay_date"]), key=lambda r: r["decided_date"])
    return rows[-1] if rows else None


def build_balance(c: Ctx) -> dict:
    a = c.a
    A = a.date
    L = c.lines_at(A)

    def lv(name: str) -> float:
        return c.line(L, name, A)

    rep = a.report_doc
    b = {"basis": "IFRS", "as_of": A, "unit": "млрд ₽",
         "note": "остатки книг — прямыми узлами books (состав — в calc; лист sheets/books_balances.csv); 12 книг договора "
                 "ведущего + 13-я книга insurance_liab (решения ведущего № 1, п. 6): средства юрлиц — две книги (corp_term, "
                 f"corp_current); кредиты по СС ({ru(lv('loans_fvtpl'))}) и лизинг — внутри corp_loans; облигации по АС "
                 f"({ru(lv('sec_ac_bonds'))}) — в securities; обязательства по операциям страхования "
                 f"({ru(lv('insurance_contract_liabilities'))}) — книга-обязательство ЧПД (ядро относит её к роли средств "
                 "юрлиц: рост — темп средств юрлиц мира); книга ликвидности — только процентные статьи (п. 3): касса, счета в "
                 "ЦБ (корсчёт), «ностро», обязательные резервы — в растущей части прочих активов (решения ведущего № 2, А1: ФОР и "
                 "корсчёт растут с обязательствами; постоянная часть — ассоциированные, гудвил, ОНА)."}
    books = {}
    for k in BOOKS:
        t = c.book_total(k, A)
        books[k] = node(r6(float(t["value_mn"]) / 1000), line_src(c, c.book_lines(k, A)), comp_calc(c, k, A))
    b["books"] = books
    b["loans_fvtpl"] = node(lv("loans_fvtpl"), c.S(rep, c.line_page("loans_fvtpl", A)),
                            "справочно: корпоративные кредиты по справедливой стоимости — внутри books.corp_loans (ядро при "
                            "прямых книгах их отдельно не выделяет: fv_share = 0)")
    lease = c.gap("lease_gross")
    lease_year = re.match(r"FY(\d{4})", lease[1])
    lease_asof = f"{lease_year.group(1)}-12-31" if lease_year else A
    lw = words(c, "lease_words")
    b["lease_gross"] = node(lease[0], c.S(lease[1], lease[2]),
                            f"справочно: чистые инвестиции в финансовую аренду на {d_ru(lease_asof)}"
                            + (f" ({lw})" if lw else "") + " — внутри «кредитов малым предприятиям и прочих»"
                            + (f"; на {a.ru} не раскрыто" if lease_asof != A else ""), as_of=lease_asof)
    b["loans_sme_other"] = node(lv("loans_ac_sme_other_gross"), c.S(rep, c.line_page("loans_ac_sme_other_gross", A)),
                                "справочно: кредиты малым предприятиям и прочие (внутри corp_loans; проценты отдельно не раскрыты)")
    fvtpl_b = sum(lv(x) for x in FVTPL_BONDS)
    p23, p32 = c.S(rep, c.line_page("sec_fvtpl_corp_bonds", A)), c.S(rep, c.line_page("sec_fvoci_debt_total", A))
    deriv, fvoci_eq = c.gap("fvtpl_derivatives"), c.gap("fvoci_equity")
    eq_fvtpl = r6(c.bv("bs_fvtpl_own") + c.bv("bs_fvtpl_repo") - fvtpl_b - deriv[0])
    fvoci_repo = c.bv("bs_fvoci_repo")
    floating = c.gap("fvtpl_floating_share")
    b["securities"] = {
        "fvoci_debt": node(lv("sec_fvoci_debt_total"), p32, f"долговые ССПСД в собственности: облигации РФ "
                                                          f"{ru(c.gv('fvoci_gov_bonds'))} + корпоративные "
                                                          f"{ru(c.gv('fvoci_corp_bonds'))} + цифровые финансовые активы "
                                                          f"{ru(c.gv('fvoci_dfa'))}"),
        "fvoci_repo": node(fvoci_repo, p32, f"в репо на {a.ru} — «–» (прим. 16)" if fvoci_repo == 0 else
                           f"долговые ССПСД в репо на {a.ru} (прим. 16)"),
        "ac": node(lv("sec_ac_bonds"), c.S(rep, c.line_page("sec_ac_bonds", A)), "облигации корпоративных эмитентов по АС (прим. 15)"),
        "ac_repo": node(0.0, c.bsrc("bs_loans_repo"), "облигации по АС в репо — строка ОФП «заложенные по репо» "
                                                      f"{ru(c.bv('bs_loans_repo'))} совпадает с ними (входят в ac); отдельно 0"),
        "fvtpl_bonds": node(r6(fvtpl_b), p23, f"долговые ССПУ: корпоративные {ru(lv('sec_fvtpl_corp_bonds'))} + РФ и субъекты "
                            f"{ru(lv('sec_fvtpl_gov_bonds'))} + прочие {ru(lv('sec_fvtpl_other_bonds'))} + в репо: корпоративные "
                            f"{ru(lv('repo_fvtpl_corp_bonds'))} + РФ {ru(lv('repo_fvtpl_gov_bonds'))}; доля в книге бумаг "
                            f"{fvtpl_b / (fvtpl_b + lv('sec_fvoci_debt_total') + lv('sec_ac_bonds')):.3f}"),
        "equity_fvtpl": node(eq_fvtpl, p23,
                             f"справочно, вне книги (прочие активы): акции и паи ССПУ (собственные {ru(c.gv('fvtpl_equity_own'))} + "
                             f"{ru(c.gv('fvtpl_equity_other'))} прочих, в репо {ru(c.gv('fvtpl_equity_repo'))})"),
        "derivatives": node(deriv[0], c.S(deriv[1], deriv[2]), "справочно, вне книги: производные финансовые инструменты (внутри "
                                                               "строки ССПУ ОФП)"),
        "equity_fvoci": node(fvoci_eq[0], c.S(fvoci_eq[1], fvoci_eq[2]), "справочно, вне книги: акции ССПСД"),
        "equity_other": node(r6(c.bv("bs_fvtpl_own") + c.bv("bs_fvtpl_repo") - fvtpl_b - deriv[0] + fvoci_eq[0]), p23 + "; " + p32,
                             f"справочно, вне книги (прочие активы): акции и паи ССПУ {ru(eq_fvtpl)} + акции ССПСД {ru(fvoci_eq[0])}"),
        "floating_share_fvtpl": node(floating[0], c.S(floating[1], floating[2]), "доля бумаг с плавающей ставкой в долговых ССПУ"),
    }
    p22 = c.S(rep, c.line_page("cash_st_deposits_reverse_repo", A))
    cbr_dep = r6(lv("cbr_deposits_est"))
    b["liquidity"] = {
        "cash": node(r6(lv("cash_st_deposits_reverse_repo") + lv("cash_allowance")), p22,
                     f"процентная часть денежных средств (п. 3): краткосрочные депозиты и обратное репо ≤ 90 дней "
                     f"{ru(lv('cash_st_deposits_reverse_repo'))} (прим. 12; в основном — сделки с группой «Московская Биржа») + "
                     f"резерв под обесценение денежных средств {ru(lv('cash_allowance'))} (ОФП нетто − итог примечания)"),
        "cbr": node(cbr_dep, calc="депозиты в ЦБ внутри строки «Счета в ЦБ РФ» [О: κ-правило листа книг]"
                                  + ("; на якоре 0 — строка целиком корсчёт (неработающие деньги)" if cbr_dep == 0 else ""),
                    estimated=True),
        "due_from_banks": node(lv("due_from_banks_net"), c.bsrc("bs_due_banks")),
        "reverse_repo": null("отдельной строки ОФП нет: обратное репо — внутри liquidity.cash (прим. 12)"),
        "reverse_repo_in_cash": node(lv("cash_st_deposits_reverse_repo"), p22,
                                     "справочно: краткосрочные депозиты и обратное репо, валовые — внутри liquidity.cash"),
    }
    nw = {"cbr_accounts": (lv("cbr_accounts"), "счета в ЦБ РФ (корсчёт: усреднение обязательных резервов) — беспроцентные"),
          "cbr_deposits_out": (lv("cbr_deposits_est_out"), "минус депозиты в ЦБ [О] (они в книге ликвидности)"),
          "nostro": (lv("nostro"), "счета «ностро» в банках — беспроцентные корсчета"),
          "cash_on_hand": (lv("cash_on_hand"), "наличные средства (банкоматы, в пути)"),
          "mandatory_reserves": (lv("mandatory_reserves"), "обязательные резервы на счетах в ЦБ РФ (ОФП)")}
    b["nonworking_money"] = {k: node(r6(v[0]), c.bsrc("bs_oblres") if k == "mandatory_reserves" else p22, v[1])
                             for k, v in nw.items()}
    b["nonworking_money"]["total"] = node(r6(sum(v[0] for v in nw.values())), calc="неработающие деньги (п. 3) — в растущей "
                                          "части прочих активов (доля к кредитам; решения ведущего № 2, А1 — было: постоянной "
                                          "частью, решения № 1, п. 3)")
    b["funds"] = {k: node(lv(v), c.S(rep, c.line_page(v, A)), RU_LINES[v]) for k, v in FUNDS_LINES}
    b["funds"]["total"] = node(c.bv("bs_cust"), c.bsrc("bs_cust"), "средства клиентов (ОФП) = сумма четырёх книг")
    reins = c.gap("insurance_reinsurance_assets")
    b["insurance"] = {"contract_liabilities": node(lv("insurance_contract_liabilities"), c.bsrc("ol_insurance_liabilities"),
                                                   PROSE["insurance_book"]),
                      "oms_payables_excluded": node(c.bv("ol_oms_payables"), c.bsrc("ol_total"),
                                                    "справочно: кредиторка ОМС — не в книге (без процентов), в прочих "
                                                    "обязательствах"),
                      "reinsurance_assets_in_other": node(reins[0], c.S(reins[1], reins[2]),
                                                          "справочно: «Страховые активы» (дебиторка по перестрахованию) — в "
                                                          "прочих активах; в книге не неттуются "
                                                          f"({ru(reins[0] / lv('insurance_contract_liabilities') * 100, 1)} % "
                                                          "книги)")}
    b["wholesale"] = {
        "cbr": node(lv("due_to_cbr"), c.bsrc("bs_cbr"), f"средства ЦБ РФ (в т. ч. репо {ru(c.gv('due_to_cbr_repo'))} — прим. 18)"),
        "banks": node(lv("due_to_banks"), c.bsrc("bs_due_to_banks"), "депозиты и счета банков (кредиты и депозиты, короткие "
                                                                     "позиции, репо, лоро, ПФИ — прим. 19)"),
        "issued_debt": node(lv("debt_securities"), c.bsrc("bs_debt_sec"), "выпущенные долговые ценные бумаги (с ЦФА)"),
        "subordinated": node(lv("sub_debt"), c.bsrc("bs_subdebt"), "срочная субординированная задолженность (T2); бессрочные "
                                                                   "облигации (AT1) — в капитале"),
        "other_borrowed": node(lv("other_borrowed"), c.S(rep, c.line_page("other_borrowed", A)),
                               f"строки «прочие заёмные средства» в ОФП на {a.ru} нет" if lv("other_borrowed") == 0 else
                               "прочие заёмные средства (ОФП)"),
    }
    alw = c.gap("allowance_ac")
    b["allowance_ac"] = node(alw[0], c.S(alw[1], alw[2]), "резерв под обесценение кредитов и облигаций по АС, величиной (ФЛ "
                                                          f"{ru(c.gv('allowance_retail'))}; ЮЛ {ru(c.gv('allowance_corporate'))})")
    ta = c.bv("bs_assets")
    asset_sum = sum(books[k]["v"] for k in ASSET_BOOKS)
    oa = r6(ta - asset_sum + alw[0])
    parts = {k: (c.bv(m), c.bsrc(m), t) for k, m, t in OTHER_ASSETS}
    parts["other"] = (c.bv("bs_oth_a"), c.bsrc("bs_oth_a"),
                      f"прочие активы ОФП (драгметаллы {ru(c.bv('oa_precious_metals'))}; материальные ценности "
                      f"{ru(c.bv('oa_inventory'))}; ОМС {ru(c.bv('oa_oms_receivables'))}; требования по поставке "
                      f"{ru(c.bv('oa_claims_settlement'))} — прим. 21)")
    parts["equity_and_derivatives_fvtpl"] = (b["securities"]["equity_fvtpl"]["v"] + deriv[0], p23, "акции ССПУ и ПФИ (вне книги бумаг)")
    parts["equity_fvoci"] = (fvoci_eq[0], p32, "акции ССПСД")
    parts["nonworking_money"] = (b["nonworking_money"]["total"]["v"], p22, "неработающие деньги (п. 3): счета в ЦБ (корсчёт), "
                                                                           "«ностро», наличные, обязательные резервы")
    b["other_assets"] = node(oa, calc=f"активы {ru(ta)} − книги активов {ru(asset_sum)} + резерв {ru(alw[0])}; по строкам — "
                                      f"{ru(sum(v[0] for v in parts.values()))} (other_assets_parts)")
    b["other_assets_parts"] = {k: node(r6(v[0]), v[1], v[2]) for k, v in parts.items()}
    fx_parts = {k: parts[k] for k in OTHER_ASSETS_FIXED}
    fx = r6(sum(v[0] for v in fx_parts.values()))
    b["other_assets_fixed"] = node(fx, calc="постоянные прочие активы — одно определение для объёмов и плотности RWA (решения "
                                            "ведущего № 1, п. 14; № 2, А1): ассоциированные " + ru(c.bv("bs_assoc")) + " + гудвил " +
                                            ru(c.bv("bs_goodwill")) + " + ОНА " + ru(c.bv("bs_dta")) + "; неработающие деньги " +
                                            ru(b["nonworking_money"]["total"]["v"]) + " — в растущей части (решения № 2, А1: "
                                            "ФОР и корсчёт растут с обязательствами, у ВТБ — так же); прочее — нет (ОМС "
                                            + ru(c.bv("oa_oms_receivables")) + " — зеркало кредиторки ОМС, растущей с кредитами в "
                                            "прочих обязательствах; драгметаллы " + ru(c.bv("oa_precious_metals")) + " — зеркало "
                                            "металлических счетов; инвестиционная собственность " + ru(c.bv("bs_invprop"))
                                            + ", ОС и НМА — растущая часть)")
    b["other_assets_fixed_parts"] = {k: node(r6(v[0]), v[1], v[2]) for k, v in fx_parts.items()}
    b["total_assets"] = node(ta, c.bsrc("bs_assets"))
    tl = c.bv("bs_liab")
    b["total_liabilities"] = node(tl, c.bsrc("bs_liab"))
    liab_sum = sum(books[k]["v"] for k in LIAB_BOOKS)
    dp = c.bv("ol_dividends_payable")
    ins_l = c.bv("ol_insurance_liabilities")
    b["other_liabilities"] = node(r6(tl - liab_sum - dp), calc=f"обязательства {ru(tl)} − книги пассивов {ru(liab_sum)} − "
                                                              f"дивиденды к выплате {ru(dp)}; по строкам — other_liabilities_parts")
    b["other_liabilities_parts"] = {
        "other_ex_insurance_dividends": node(r6(c.bv("bs_oth_l") - ins_l - dp), c.bsrc("ol_total"),
                                             f"прочие обязательства {ru(c.bv('bs_oth_l'))} − страхование {ru(ins_l)} − дивиденды "
                                             f"{ru(dp)} (ОМС {ru(c.bv('ol_oms_payables'))}; ПФИ {ru(c.bv('ol_derivatives'))}; "
                                             f"аренда {ru(c.bv('ol_lease'))}; резервы по гарантиям "
                                             f"{ru(c.bv('ol_guarantee_provisions'))} — прим. 21)"),
        "deferred_tax": node(c.bv("bs_dtl"), c.bsrc("bs_dtl")),
        "current_tax": node(c.bv("bs_curtax_l"), c.bsrc("bs_curtax_l")),
        "nci_puttable": node(c.bv("bs_nci_liab"), c.bsrc("bs_nci_liab"), "обязательства перед держателями неконтрольных долей"),
    }
    d = dividend_unpaid(c)
    if d is not None and dp > 0:
        pay = d["pay_date"]
        paid = (f"выплачен в {MONTHS_PREP[int(pay[5:7]) - 1]} {pay[:4]} года" if pay <= SNAPSHOT["sheets_as_of"]
                else f"срок выплаты — {d_ru(pay)}")
        eq_page = c.get(c.eqf, ("dividends_shareholders", a.ytd),
                        f"{FACT_SHEETS}/equity_flows.csv: dividends_shareholders {a.ytd}")["page"]
        b["dividends_payable"] = node(dp, c.bsrc("ol_dividends_payable"),
                                      f"строка прим. 21 «Обязательства по дивидендам»: дивиденд за {d['fiscal_year']} год "
                                      f"({dec_ru(float(d['dps']))} ₽ × {int_ru(d['eligible_shares'])} = "
                                      f"{money_ru(float(d['pool_declared_rub']))} ₽), решение ГОСА {d_ru(d['decided_date'])}, "
                                      f"реестр {d_ru(d['record_date'])}, {paid}; из капитала МСФО вычтен в {a.ytd_ru} (отчёт об "
                                      f"изменениях капитала, с. {eq_page})")
        b["dividends_payable_year"] = int(d["fiscal_year"])
        y, k = q_parse(d["period"])
        b["dividends_payable_declared"] = [{"period": d["period"], "amount": node(dp, c.bsrc("ol_dividends_payable"),
                                                                                 f"дивиденд за {d['fiscal_year']} год (квартал "
                                                                                 f"прибыли — {k}-й квартал {y} года; форма "
                                                                                 "квартального календаря)")}]
    else:
        b["dividends_payable"] = node(dp, c.bsrc("ol_dividends_payable"), "строка прим. 21 «Обязательства по дивидендам»")
        b["dividends_payable_declared"] = []
    eq = {"total": node(c.bv("bs_equity"), c.bsrc("bs_equity")),
          "at1": node(c.bv("bs_perp"), c.bsrc("bs_perp"), "бессрочные субординированные облигации в капитале МСФО (USD; курсовая "
                                                         "переоценка — через нераспределённую прибыль); вне капитала обыкновенных "
                                                         "акционеров (позиция Сбера)"),
          "nci": node(c.bv("bs_nci"), c.bsrc("bs_nci")),
          "bv_common": node(c.bv("bs_eq_ex_perp"), c.bsrc("bs_eq_ex_perp") + "; " + c.bsrc("eq_ex_perp_note22"),
                            "капитал акционеров Банка без бессрочных облигаций (база ROE и P/BV банка, прим. 22)"),
          "share_capital": node(c.bv("bs_sh_cap"), c.bsrc("bs_sh_cap")),
          "other_contributions": node(c.bv("bs_oth_contrib"), c.bsrc("bs_oth_contrib"), "прочие вклады в капитал (в т. ч. оплата "
                                                                                       "«Хоум Капитала» акциями)"),
          "reval_buildings": node(c.bv("bs_reval_res"), c.bsrc("bs_reval_res")),
          "fvoci_reserve": node(c.bv("bs_fvoci_res"), c.bsrc("bs_fvoci_res"), "резерв переоценки ССПСД, после налога"),
          "retained_earnings": node(c.bv("bs_re"), c.bsrc("bs_re"))}
    b["equity"] = eq
    pye = a.prev_year_end
    tot = lambda bk: float(c.book_total(bk, pye)["value_mn"])   # noqa: E731
    pr = sum(tot(k) for k in RETAIL_LOANS) / 1000
    pc = tot("corp_loans") / 1000
    pye_src = c.S(f"FY{pye[:4]}_ifrs_fs.pdf", c.line_page("loans_ac_corp_gross", pye))
    b["prev_year_end"] = {"as_of": pye,
                          "loans_corporate": node(r6(pc), pye_src, f"книга corp_loans на {d_ru(pye)}: "
                                                  + comp_calc(c, "corp_loans", pye)),
                          "loans_retail": node(r6(pr), pye_src, f"четыре розничные книги на {d_ru(pye)}: "
                                               + comp_calc(c, "auto", pye).split(" (")[0]
                                               + f" + ипотека {ru(tot('mortgage') / 1000)} + потребительские "
                                               f"{ru(tot('cash_loans') / 1000)} + «Халва» {ru(tot('cards') / 1000)}")}
    b["iea"] = node(r6(asset_sum), calc="процентные активы движка: кредитные книги " + ru(sum(books[k]['v'] for k in LOANS)) +
                    " + бумаги " + ru(books['securities']['v']) + " + ликвидность (процентная часть, п. 3) " +
                    ru(books['liquidity']['v']))
    b["history"] = balance_history(c)
    b["allowance_books"] = allowance_books(c, alw[0])
    return b


def balance_history(c: Ctx) -> dict:
    """Концы кварталов до якоря: капитал, кредиты, средства, процентные активы (лист balance_history.csv) и остатки
    книг ЧПД (листы books_balances*.csv; М13)."""
    A = c.a.date
    if A not in c.hist:
        c.miss(f"{FACT_SHEETS}/balance_history.csv: строка {A} (конец квартала якоря: капитал, кредиты, средства, процентные "
               "активы)")
    hist = {}
    for d, h in sorted(c.hist.items()):
        if d > A:
            continue
        db = h["cls"] == "Ф"
        src_h = h["src"] if db else "sheets/books_balances*.csv"
        if db:
            s_l = c.S(os.path.basename(DATABOOK), src_h.split(", ")[1].split(" ")[0])
            # средства клиентов — свои ячейки листа (строки «средства ФЛ» и «средства ЮЛ» датабука), не ячейка кредитов
            cells_f = re.search(r"([A-Z]+\d+\+[A-Z]+\d+) \(средства ФЛ и ЮЛ\)", src_h)
            sheet = src_h.split(", ")[1].split("!")[0]
            s_f = c.S(os.path.basename(DATABOOK), f"{sheet}!{cells_f.group(1)}") if cells_f else s_l
        else:
            s_l = line_src(c, [r for r in c.bb if r["date"] == d and r["book"] in LOANS and not service_row(r["line"])])
            s_f = s_l
        row = {"date": d,
               "bv_common": node(float(h["bv_common"]), c.S(h["bv_common_src"].split(", ")[0],
                                                            h["bv_common_src"].split(", ")[1].replace("p", "")),
                                 "капитал акционеров без бессрочных облигаций и НДУ (ОФП)"),
               "loans": node(float(h["loans"]), s_l, "сумма пяти кредитных книг (валовые, с кредитами по СС, без облигаций по АС)"
                             + ("; ДАТАБУК: валовые кредиты − облигации по АС" if db else "")),
               "loans_ac_gross": node(float(h["loans"]), calc="= loans: кредиты по СС лежат в corp_loans (отдельной книги нет)"),
               "funds": node(float(h["funds"]), s_f if db else c.S(c.a.report_doc, c.line_page("dep_ind_current", A)) if d == A
                             else s_f, "средства клиентов: четыре книги" + ("; ДАТАБУК: средства ФЛ + средства ЮЛ" if db else "")),
               "iea": node(float(h["iea"]), calc="процентные активы движка: кредиты + долговые бумаги + ликвидность "
                                               "(процентная часть, п. 3: депозиты и обратное репо, депозиты в ЦБ [О], средства "
                                               "в банках)" + ("; ДАТАБУК и примечание «Денежные средства» МСФО — лист "
                                                             "balance_history.csv" if db else "")),
               "insurance_liab": node(float(h["insurance_liab"]), calc="книга insurance_liab (обязательства по операциям "
                                                                       "страхования; ядро считает её в средствах клиентов — "
                                                                       "роль средств юрлиц)"),
               "total_assets": node(float(h["total_assets"]), c.S(h["total_assets_src"].split(", ")[0],
                                                                   h["total_assets_src"].split(", ")[1].replace("p", "")))}
        fvl = [r for r in c.bb if r["date"] == d and r["line"] == "loans_fvtpl"]
        if fvl:
            row["loans_fvtpl"] = node(float(fvl[0]["value_mn"]) / 1000, line_src(c, fvl), "справочно: кредиты по СС (внутри corp_loans)")
        hist[q_of_date(d)] = row
    # остатки книг ЧПД на концы кварталов до якоря (М13): все книги — где лист книг их несёт; концы, где есть только книги
    # средств клиентов (лист books_balances_liab_2024.csv), — четыре книги средств
    reg = {d["key"]: d["sha256"][:16] for d in c.docs.values()}
    rows = c.bb + c.bb_liab
    for d in sorted({r["date"] for r in c.bb if r["line"] == "TOTAL" and r["date"] < A}):
        per = q_of_date(d)
        node_ = {bk: book_node(rows, bk, d, reg) for bk in BOOKS}
        h = hist[per]
        loans = sum(node_[bk]["v"] for bk in LOANS)
        iea = sum(node_[bk]["v"] for bk in ASSET_BOOKS)
        c.check(f"история {per}: кредитные книги = loans, книги активов = iea (листы книг против balance_history.csv)",
                abs(loans - float(h["loans"]["v"])) < 2e-3 and abs(iea - float(h["iea"]["v"])) < 2e-3,
                f"{loans:.3f} / {h['loans']['v']}; {iea:.3f} / {h['iea']['v']}")
        h["books"] = node_
    for d in sorted({r["date"] for r in c.bb_liab if r["line"] == "TOTAL"}):
        per = q_of_date(d)
        node_ = {bk: book_node(rows, bk, d, reg) for bk in FUNDS_BOOKS}
        funds = float(hist[per]["funds"]["v"])
        s = sum(x["v"] for x in node_.values())
        c.check(f"история {per}: книги средств клиентов ≤ средства клиентов (без репо с клиентами)",
                s <= funds + 2e-3 and funds - s < 1.0, f"{s:.3f} / {funds}")
        hist[per]["books"] = node_
    return hist


def book_node(rows: list[dict], b: str, date: str, reg: dict) -> dict:
    tot = [r for r in rows if r["book"] == b and r["date"] == date and r["line"] == "TOTAL"]
    if len(tot) != 1:
        raise BuildError(f"лист книг: у книги {b} на {date} итогов {len(tot)}, нужен один")
    lines = [r for r in rows if r["book"] == b and r["date"] == date and not service_row(r["line"])]
    if abs(sum(float(r["value_bn"]) for r in lines) - float(tot[0]["value_bn"])) >= 2e-3:
        raise BuildError(f"лист книг: строки книги {b} на {date} не дают итога")
    srcs = []
    for r in lines:
        if r["cls"] != "Ф":
            continue
        doc = r["source"].split(".pdf")[0].strip()
        page = r["page"].replace("с.", "").strip()
        s = f"{doc}.pdf, с. {page}, sha256 {reg[doc]}"
        if s not in srcs:
            srcs.append(s)
    calc = " + ".join(f"{r['line']} {float(r['value_bn']):.3f}" for r in lines)
    return {"v": round(float(tot[0]["value_bn"]), 3), **({"src": "; ".join(srcs)} if srcs else {}),
            "calc": f"сумма строк книги ({calc}) — лист stage1/facts/sheets/books_balances*.csv; М13"}


# Резерв под обесценение по кредитным книгам на дату якоря (ключ К7 ядра) и объём гарантий (К5): итоги строк таблиц
# движения резерва по классам и примечания об условных обязательствах; млн ₽ — как в отчёте. Листа с ними нет — числа
# названы здесь, страница каждого находится по текстовому слою отчёта (число обязано стоять в строке).
ALLOWANCE_BOOKS = {
    "2026Q2": {"auto": [21223], "mortgage": [11414], "cash_loans": [38702], "cards": [16600], "corp_loans": [45269, 324, 18187]},
}
ALLOWANCE_CORP_WORDS = ("корпоративные", "субъекты РФ", "малые и прочие")
GUARANTEES = {
    "2026Q2": {"nonfinancial": (1029221, "нефинансовые гарантии"), "financial": (137704, "объем финансовых гарантий")},
}


def page_of_line(c: Ctx, doc: str, start: str, last_value: float) -> int:
    want = fmt_mn(last_value)
    for pg, ln in c.pages(doc):
        s = ln.strip()
        if s.startswith(start) and s.endswith(want):
            return pg
    c.miss(f"{TEXT_LAYER}/{doc}.txt: строка «{start} … {want}»")
    return 0


def page_of_text(c: Ctx, doc: str, words_: str, value: float) -> int:
    want = fmt_mn(value)
    lines = c.pages(doc)
    for pg, ln in lines:
        if want + " млн руб" in ln and any(w in ln for w in words_.split("|")):
            return pg
    for i, (pg, ln) in enumerate(lines):          # число на следующей строке после слов
        near = " ".join(x[1] for x in lines[max(0, i - 3):i])
        if want + " млн руб" in ln and any(w in near for w in words_.split("|")):
            return pg
    c.miss(f"{TEXT_LAYER}/{doc}.txt: «{words_}» = {want}")
    return 0


def allowance_books(c: Ctx, total: float) -> dict:
    a = c.a
    spec = ALLOWANCE_BOOKS.get(a.period)
    if spec is None:
        c.miss(f"ops/tools/build_facts.py ALLOWANCE_BOOKS[{a.period!r}] (резерв по кредитным книгам на {a.ru}, прим. 15)")
        return {}
    doc = a.report_doc[:-4]
    reg = {d["key"]: d["sha256"][:16] for d in c.docs.values()}
    start = f"Остаток на {int(a.date[8:])} {MONTHS_GEN[int(a.date[5:7]) - 1]} {a.y} г."
    out = {}
    for bk, parts in spec.items():
        pgs = [page_of_line(c, doc, start, v) for v in parts]
        out[bk] = {"v": round(sum(parts) / 1000, 3),
                   "src": f"{doc}.pdf, с. {', '.join(str(p) for p in sorted(set(pgs)))}, sha256 {reg[doc]}",
                   "calc": (f"резерв на {a.ru} по классу (итог строки «{start}» таблицы движения резерва, прим. 15)"
                            + ("" if len(parts) == 1 else ": " + " + ".join(f"{w} {fmt_mn(v)}" for w, v in
                                                                            zip(ALLOWANCE_CORP_WORDS, parts))))}
    s = sum(sum(v) for v in spec.values())
    c.check("резерв по кредитным книгам: Σ = резерв под обесценение кредитов (allowance_ac)", abs(s / 1000 - total) < 1e-9,
            f"{s / 1000:.3f} / {total}")
    return out


def guarantees(c: Ctx) -> dict:
    a = c.a
    spec = GUARANTEES.get(a.period)
    if spec is None:
        c.miss(f"ops/tools/build_facts.py GUARANTEES[{a.period!r}] (объём банковских гарантий на {a.ru})")
        return {}
    doc = a.report_doc[:-4]
    reg = {d["key"]: d["sha256"][:16] for d in c.docs.values()}
    out = {}
    for k, (v, w) in spec.items():
        pg = page_of_text(c, doc, "гарант", v)
        out[k] = {"v": round(v / 1000, 3), "src": f"{doc}.pdf, с. {pg}, sha256 {reg[doc]}",
                  "calc": f"{w} на {a.ru} (условные обязательства кредитного характера)"}
    return out


# ================================================================== pnl_quarterly.json
def q_src(c: Ctx, q: str, metrics: list[str]) -> str | None:
    y, k = q_parse(q)
    docs, pgs = [], []
    for cum in [f"{CUM_OF[k]}{y}"] + ([f"{CUM_OF[k - 1]}{y}"] if k > 1 else []):
        for m in metrics:
            r = c.cum.get((m, cum))
            if r and (r["doc"], r["page"]) not in zip(docs, pgs):
                docs.append(r["doc"])
                pgs.append(r["page"])
    return c.S("|".join(docs), "|".join(pgs)) if docs else None


def q_calc(c: Ctx, q: str, metric: str) -> str | None:
    r = c.ql.get((q, metric))
    return r["calc"] if r else None


def eq_src(c: Ctx, q: str) -> tuple[str, str]:
    """Источник квартального купона бессрочных: строки нарастающих итогов отчёта об изменениях капитала."""
    y, k = q_parse(q)
    cur = c.eqf.get(("perp_coupon", f"{CUM_OF[k]}{y}"))
    prev = c.eqf.get(("perp_coupon", f"{CUM_OF[k - 1]}{y}")) if k > 1 else None
    docs = [x for x in (cur, prev) if x]
    return "|".join(x["doc"] for x in docs), "|".join(str(x["page"]) for x in docs)


def build_pnl(c: Ctx) -> dict:
    a = c.a
    out = {"basis": "IFRS", "profit_basis": "reported", "as_of": a.date,
           "unit": "млрд ₽ за квартал; key_avg — доля единицы",
           "sign": "как в отчётности: расходы, резервы, налог — со знаком минус; dia — величиной; тождество pbt = nii + "
                   "llp_debt_fa + fees_net + insurance_net + noncore_net + opex + misc_net; ni = pbt + tax; "
                   "ni_shareholders = ni − ni_nci",
           "note": "прибыль движка — отчётная прибыль МСФО, приходящаяся на акционеров Банка (не «регулярная» прибыль банка); "
                   "квартал — разность нарастающих итогов (редакция — последний документ, печатающий период; формула — в "
                   "calc; сверка с колонками «за три месяца» — лист pnl_quarterly_lines.csv, расхождения — межредакционные "
                   "переклассификации ≤ 0,32 млрд внутри строк, прибыль до налога не затронута); состав слотов — лист "
                   "pnl_composition.csv: nii — ЧПД формы + финансовые расходы страхования (МСФО 17; решения ведущего № 1, "
                   "п. 6 — книга insurance_liab; 2023К1–К3 — оценка [О], лист ins_finance_quarterly.csv); fees_net — с "
                   "резервом по нефинансовым гарантиям неттом; insurance_net — страхование и прочая небанковская нетто БЕЗ "
                   "финансовых расходов страхования; nii_form, insurance_net_form — строки формы (справочно: ЧПМ банка — по "
                   "nii_form); noncore_net — выгодные приобретения и названные разовые (отдельными "
                   "узлами noncore_parts); misc_net — бумаги, валюта, прочие доходы и обесценение, переоценка зданий. Купон "
                   "бессрочных — мимо прибыли, через капитал (at1_coupon).",
           "quarters": {}}
    reg_cpn = c.gap("regular_fvtpl_coupon_ytd")
    for q in a.quarters:
        y, k = q_parse(q)
        row = {}
        for slot in PNL_SLOTS:
            cm = c.get(c.cmp, (q, slot), f"{FACT_SHEETS}/pnl_composition.csv: {slot} за {q}")
            v = r6(float(cm["value_mn"]) / 1000)
            src = q_src(c, q, SLOT_SRC_LINES[slot])
            base = q_calc(c, q, SLOT_SRC_LINES[slot][0])
            calc = cm["composition"]
            if slot in PNL_REPORTED_SLOTS:
                calc = base or calc
            elif base and k > 1:
                calc = calc + "; каждое слагаемое — разность нарастающих итогов (лист pnl_quarterly_lines.csv)"
            if slot == "ins_finance_expense" and q in INS_FIN_ESTIMATED:
                row[slot] = est(v, calc + "; лист ins_finance_quarterly.csv", src=c.S(*INS_FIN_ESTIMATED_SRC))
            else:
                row[slot] = node(v, src, calc)
        row["dia"]["calc"] = "величиной: взносы в систему страхования вкладов (внутри nii); " + (q_calc(c, q, "dep_ins") or "")
        parts = {}
        for item, name, ru_ in NONCORE_PARTS:
            ra = c.named.get((item, f"{CUM_OF[k]}{y}"))
            rb = c.named.get((item, f"{CUM_OF[k - 1]}{y}")) if k > 1 else None
            av = float(ra["value_mn"]) if ra else 0.0
            bvv = float(rb["value_mn"]) if rb else 0.0
            docs = [x for x in (ra, rb) if x and x["doc"]]
            src = c.S("|".join(x["doc"].split(" | ")[0] for x in docs),
                      "|".join((x["page"] or "").split(" | ")[0] for x in docs)) if docs else None
            calc = f"{ru_}: " + (f"{CUM_OF[k]}{y} {av:.0f} − {CUM_OF[k - 1]}{y} {bvv:.0f} млн" if k > 1 else f"3M{y} {av:.0f} млн")
            notes = [x["note"] for x in (ra, rb) if x and x["cls"] == "В"]
            if notes:
                calc += "; " + notes[0]
            parts[name] = node(r6((av - bvv) / 1000), src, calc) if src else node(r6((av - bvv) / 1000), calc=calc +
                                                                                    " (статьи в примечаниях нет — ноль)")
        row["noncore_parts"] = parts
        cp = c.eqf.get(("perp_coupon_q", q))
        if cp:
            row["at1_coupon"] = node(r6(-float(cp["value_mn"]) / 1000), c.S(*eq_src(c, q)),
                                     "купон бессрочных облигаций величиной (через нераспределённую прибыль, мимо ОПУ); " + cp["note"])
        else:
            fy = c.eqf.get(("perp_coupon", f"FY{y}"))
            row["at1_coupon"] = null(f"поквартально не раскрыт: за {y} год {ru(-float(fy['value_mn']) / 1000)} (отчёт об "
                                     f"изменениях капитала {os.path.basename(fy['doc']).split('_')[0]}, с. {fy['page']}); "
                                     f"промежуточные отчёты {y} года — сканы без поквартальной строки" if fy else
                                     "поквартально не раскрыт")
        kq = c.get(c.key, q, f"{FACT_SHEETS}/key_rate_quarterly.csv: {q}")
        row["key_avg"] = node(float(kq["key_avg"]), c.S("key_rate_daily.csv"), "средняя ключевая ставка Банка России за квартал "
                              "(календарные дни), доля единицы")
        row["ci_shareholders"] = node(r6(row["ci_total"]["v"] - row["ni_nci"]["v"]), calc="совокупный доход за вычетом прибыли НДУ "
                                      "(ПСД неконтрольных долей не выделен — в отчёте об изменениях капитала ПСД целиком у акционеров)")
        oc = c.eqf.get(("oci_shareholders", ytd(q))) if y == a.y else None
        if oc:
            ob = c.eqf[("oci_shareholders", ytd(q_prev(q)))] if k > 1 else None
            row["oci_fvoci"] = node(r6((float(oc["value_mn"]) - (float(ob["value_mn"]) if ob else 0.0)) / 1000),
                                    c.S(oc["doc"], oc["page"]),
                                    "ПСД акционеров — изменение резерва переоценки ССПСД (отчёт об изменениях капитала)" +
                                    (f": {ytd(q)} − {ytd(q_prev(q))}" if ob else ""))
        else:
            row["oci_fvoci"] = null("в переписи формы ПСД не разнесён на ССПСД и прочее; весь ПСД — oci_total")
        row["reported"] = {kk: dict(row[kk]) for kk in ("pbt", "tax", "ni", "ni_shareholders", "ni_nci")}
        row["fv_loans_credit"] = null("не раскрыто: кредитная переоценка кредитов по справедливой стоимости отдельной строкой "
                                      "ОПУ не раскрыта (внутри результата ССПУ)")
        row["fvtpl_bond_reval"] = null("не раскрыто поквартально: результат по ССПУ (строка fvtpl) включает купон по облигациям "
                                       "ССПУ в части «регулярной» прибыли (" + f"{ru(reg_cpn[0])} за {a.ytd_ru}, прим. 3"
                                       + ") — переоценку отдельно банк не печатает")
        out["quarters"][q] = row
        c.check(f"ОПУ {q}: pbt = Σ строк движка; ni = pbt + tax; ni_shareholders = ni − ni_nci",
                abs(sum(row[s]["v"] for s in PNL_SUM) - row["pbt"]["v"]) < 1e-6
                and abs(row["pbt"]["v"] + row["tax"]["v"] - row["ni"]["v"]) < 1e-6
                and abs(row["ni"]["v"] - row["ni_nci"]["v"] - row["ni_shareholders"]["v"]) < 1e-6)
        c.check(f"ОПУ {q}: noncore_net = Σ noncore_parts; nii = ЧПД формы + финрасходы страхования",
                abs(row["noncore_net"]["v"] - sum(x["v"] for x in parts.values())) < 1e-6
                and abs(row["nii"]["v"] - row["nii_form"]["v"] - row["ins_finance_expense"]["v"]) < 1e-6)
    yrs = {}
    first = q_parse(a.quarters[0])[0]
    full = list(range(first, a.y + (1 if a.k == 4 else 0)))
    for y in full:
        yrs[str(y)] = {kk: year_node(c, m, f"FY{y}") for kk, m in YEAR_LINES}
        qsum = sum(out["quarters"][f"{y}Q{k}"]["ni_shareholders"]["v"] for k in (1, 2, 3, 4))
        c.check(f"ОПУ {y}: Σ кварталов прибыли акционеров = году", abs(qsum - yrs[str(y)]["ni_shareholders"]["v"]) < 1e-6)
    if a.k < 4:
        yrs[f"{a.y}{YTD_KEY[a.k]}"] = {kk: year_node(c, m, a.ytd) for kk, m in YEAR_LINES}
    out["years"] = yrs
    return out


YTD_KEY = {1: "Q1", 2: "H1", 3: "9M"}
INS_FIN_ESTIMATED_SRC = ("FY2024_ifrs_fs.pdf", "12")


def year_node(c: Ctx, metric: str, period: str) -> dict:
    r = c.get(c.cum, (metric, period), f"{FACT_SHEETS}/pnl_cumulative.csv: {metric} за {period}")
    return node(r6(float(r["value_mn"]) / 1000), c.S(r["doc"], r["page"]))


# ================================================================== capital.json
def build_capital(c: Ctx) -> dict:
    a = c.a
    fd = a.form_date
    f = c.get(c.capb, fd, f"{FACT_SHEETS}/capital_bank.csv: формы 0409135/0409123 на {fd}")
    s135 = c.S(f["doc135"]) + f", форма 0409135 на {d_ru(fd)}, разд. 3"
    s123 = c.S(f["doc123"]) + f", форма 0409123 на {d_ru(fd)}"
    out = {"basis": "mixed", "as_of": a.date,
           "note": f"слоты нормативов — банк соло ({BANK}) по формам 0409135/0409123 на {d_ru(fd)} (устав: "
                   "n20_0 ← Н1.0 банка, n1_1_bank ← Н1.2 банка — связывает вторым); нормативы банковской группы (0409805) "
                   f"опубликованы только по {GROUP_FORM_LAST}, МСФО «обобщённая» без примечания о капитале — группа справочно "
                   f"(Базель по ДАТАБУКу на {d_ru(databook_date(c))}). У каждого блока свой basis."}
    d = dividend_unpaid(c)
    pre_div = d is not None and d["record_date"] >= fd
    dp = c.bv("ol_dividends_payable")
    n10 = float(f["n1_0"])
    pre_note = words(c, "pre_dividend_note", (f"Н1.0 на {d_ru(fd)} — до вычета дивиденда за {d['fiscal_year']} год ({ru(dp)}): "
                                              f"решение {d_ru(d['decided_date'])}, реестр {d_ru(d['record_date'])}; вычет из "
                                              "капитала банка — в месяце реестра.") if pre_div else None)
    mb = c.gap("min_n1_0_with_buffers")
    out["n20_0"] = {"basis": "RAS (банк соло)",
                    "value": node(n10, s135, "Н1.0 банка, % / 100; слот n20_0 ядра ← Н1.0 банка (устав калибровки)"),
                    "as_of": fd, "estimated": False, "pre_dividend": pre_div}
    if pre_div:
        out["n20_0"]["pre_dividend_note"] = pre_note
    out["n20_0"]["min_with_buffers"] = node(mb[0], c.S(mb[1], mb[2]), words(c, "min_with_buffers_words",
                                                                             f"требование Н1.0 с надбавками для СЗКО на {a.y} год"))
    out["n1_1_bank"] = {"basis": "RAS (банк соло)",
                        "value": node(float(f["n1_2"]), s135, "Н1.2 банка, % / 100; слот второго норматива ядра ← Н1.2 банка "
                                                              "(устав: связывает вторым; имя слота историческое)"),
                        "as_of": fd, "estimated": False, "slot_metric": "Н1.2"}
    out["n1_0_bank"] = {"v": n10, "src": s135, "calc": "Н1.0 банка, % / 100", "basis": "RAS", "as_of": fd}
    out["n1_1_bank_h11"] = {"v": float(f["n1_1"]), "src": s135, "calc": "Н1.1 банка (достаточность базового капитала), % / 100; "
                                                                         "справочно (в слоте n1_1_bank стоит Н1.2)",
                            "basis": "RAS", "as_of": fd}
    out["n1_2_bank"] = {"v": float(f["n1_2"]), "src": s135, "calc": "Н1.2 банка, % / 100", "basis": "RAS", "as_of": fd}
    out["n20_2"] = node(float(f["n1_2"]), s135, "Н1.2 банка (в смысле слотов — тот же второй норматив)", basis="RAS", as_of=fd)
    out["n27_bank"] = (node(float(f["n27"]), s135, "Н27 (краткосрочная ликвидность) банка, % / 100"
                            + (" — ровно 100 %" if float(f["n27"]) == 1.0 else ""), basis="RAS", as_of=fd)
                       if f["n27"] else null("Н27 в форме не раскрыт"))
    out["bank_base_capital"] = node(float(f["base_bn"]), s123, "форма 0409123, код 102 «Базовый капитал, итого», тыс. ₽ / 10⁶",
                                    basis="RAS", as_of=fd)
    out["bank_own_funds"] = node(float(f["capital_total_bn"]), s123, "код 000 «Собственные средства (капитал), итого»",
                                 basis="RAS", as_of=fd)
    out["bank_additional_capital"] = node(float(f["additional_bn"]), s123, "код 105 «Добавочный капитал, итого»", basis="RAS",
                                          as_of=fd)
    out["bank_main_capital"] = node(r6(float(f["main_bn"])), s123, "основной капитал = базовый + добавочный", basis="RAS",
                                    as_of=fd)
    why_group = f"не раскрыто: форма 0409805 по рег. № 963 опубликована только по {GROUP_FORM_LAST}"
    out["group_capital"] = {"basis": "RAS (банковская группа, 0409805)",
                            "total": null(why_group), "base": null(why_group), "additional": null(why_group),
                            "supplementary": null(why_group)}
    bvc, base, k20 = c.bv("bs_eq_ex_perp"), float(f["base_bn"]), float(f["capital_total_bn"])
    out["basel"] = {"basis": "RAS (банк соло; слоты ядра: капитал и знаменатель норматива банка)", "as_of": fd,
                    "cet1": node(base, s123, "слот ядра: базовый капитал банка (код 102) — прокси «CET1 без "
                                             "регуляторных инструментов»; ключ capital.n20.deductions_anchor: anchor "
                                             f"даст bv − cet1 = {ru(bvc)} − {ru(base)} = {ru(bvc - base)} (см. core_form_check)"),
                    "rwa": node(float(f["rwa_n10_bn"]), s135 + "; " + s123,
                                f"RWA знаменателя Н1.0 = собственные средства / Н1.0 = {ru(k20)} / {dec_ru(n10)} [Р]; форма 0409135 "
                                "знаменатели не публикует; точность ≈ ±0,5 млрд (округление норматива)"),
                    "rwa_n11": node(float(f["rwa_n11_bn"]), s135 + "; " + s123, "знаменатель Н1.1 = базовый капитал / Н1.1 [Р]"),
                    "rwa_n12": node(float(f["rwa_n12_bn"]), s135 + "; " + s123, "знаменатель Н1.2 = основной капитал / Н1.2 [Р]"),
                    "cet1_ratio": node(float(f["n1_1"]), s135, "Н1.1 банка"),
                    "total_ratio": node(n10, s135, "Н1.0 банка")}
    out["t2_recognized"] = node(float(f["t2_bn"]), s123, "дополнительный капитал банка (код 203) — регуляторный T2, включая "
                                                         "прибыль текущего года до аудита", basis="RAS", as_of=fd)

    def eqf(item: str, per: str) -> dict:
        return c.get(c.eqf, (item, per), f"{FACT_SHEETS}/equity_flows.csv: {item} {per}")

    ef = lambda it, per: float(eqf(it, per)["value_mn"]) / 1000   # noqa: E731
    es = lambda it, per: c.S(eqf(it, per)["doc"], eqf(it, per)["page"])   # noqa: E731
    at1 = c.bv("bs_perp")
    lo, hi = c.gv("at1_coupon_annual_low"), c.gv("at1_coupon_annual_high")
    tag = a.ytd.lower()
    blk = {"basis": "IFRS",
           "amount": node(at1, c.bsrc("bs_perp") + "; " + c.bsrc("eq_perp_note22"),
                          "бессрочные субординированные облигации в капитале МСФО (USD)"),
           "coupon_annual": est(round(-4 / a.k * ef("perp_coupon", a.ytd), 6),
                                words(c, "at1_coupon_annual_words",
                                      f"годовой купон величиной (через капитал): {4 // a.k if 4 % a.k == 0 else '4/3'} × купон "
                                      f"{a.ytd_ru} {ru(-ef('perp_coupon', a.ytd))} [В]"),
                                rng=(lo, hi), src=es("perp_coupon", a.ytd)),
           "coupon_quarter": node(4, calc=words(c, "at1_coupon_quarter_words",
                                                "купон платится каждый квартал, слот ядра — одна годовая сумма в квартале "
                                                "coupon_quarter; 4 — по форме Сбера")),
           f"coupon_{tag}": node(-ef("perp_coupon", a.ytd), es("perp_coupon", a.ytd), "величиной")}
    for k in range(1, a.k + 1):
        q = f"{a.y}Q{k}"
        if k == 1:
            blk[f"coupon_q1_{a.y}"] = node(-ef("perp_coupon", ytd(q)), es("perp_coupon", ytd(q)), "величиной")
        else:
            blk[f"coupon_q{k}_{a.y}"] = node(r6(-(ef("perp_coupon", ytd(q)) - ef("perp_coupon", ytd(q_prev(q))))),
                                             es("perp_coupon", ytd(q)) + "; " + es("perp_coupon", ytd(q_prev(q))),
                                             f"разность {ytd(q).replace('M', 'М')} − {ytd(q_prev(q)).replace('M', 'М')}, величиной")
    blk[f"coupon_tax_{tag}"] = node(ef("perp_tax", a.ytd), es("perp_tax", a.ytd), "налоговый эффект по бессрочным, признанный в "
                                                                                   "капитале (+)")
    blk[f"eps_interest_after_tax_{tag}"] = node(-ef("eps_perp_interest_after_tax", a.ytd), es("eps_perp_interest_after_tax", a.ytd),
                                                "проценты по бессрочным, вычтенные при расчёте прибыли на акцию (после налога)")
    blk[f"fx_reval_re_{tag}"] = node(ef("perp_fx_reval_re", a.ytd), es("perp_fx_reval_re", a.ytd),
                                     words(c, "at1_fx_reval_words", f"курсовая переоценка бессрочных через нераспределённую "
                                                                    f"прибыль за {a.ytd_ru}"))
    if a.k > 1:
        fxq = c.get(c.eqf, ("perp_fx_reval_re_q", a.period), f"{FACT_SHEETS}/equity_flows.csv: perp_fx_reval_re_q {a.period}")
        blk[f"fx_reval_re_q{a.k}_{a.y}"] = node(r6(float(fxq["value_mn"]) / 1000),
                                                es("perp_fx_reval_re", a.ytd) + "; " + es("perp_fx_reval_re", a.ytd_prev),
                                                f"разность {a.ytd_ru} − {a.ytd_prev.replace('M', 'М')}")
    out["at1"] = blk
    out["fvoci_reserve"] = node(c.bv("bs_fvoci_res"), c.bsrc("bs_fvoci_res"), "после налога; = balance.equity.fvoci_reserve",
                                basis="IFRS")
    out["ofz_curve_anchor"] = {"basis": "market", "as_of": a.date,
                               "convention": "бескупонная доходность ОФЗ (КБД MOEX), годовое начисление, доли"}
    for t in ("1.0", "2.0", "3.0", "5.0", "10.0"):
        r = c.get(c.ofz, (a.date, t), f"{FACT_SHEETS}/ofz_curve.csv: {a.date}, {t} года")
        out["ofz_curve_anchor"][t.split(".")[0]] = node(float(r["value"]), f"MOEX ISS zcyc {r['date']} {r['tradetime']}, "
                                                                            f"yearyields, sha256 {r['sha256'][:16]}")
    dd = databook_date(c)
    g = lambda m: c.get(c.capg, (m, dd), f"{FACT_SHEETS}/capital_group_databook.csv: {m} на {dd}")   # noqa: E731
    db = os.path.basename(DATABOOK)
    out["basel_ifrs"] = {"basis": "Basel (группа; ДАТАБУК банка)", "as_of": dd,
                         "tier1": node(float(g("tier1_group_basel")["value"]), c.S(db, g("tier1_group_basel")["cell"])),
                         "tier2": node(float(g("tier2_group_basel")["value"]), c.S(db, g("tier2_group_basel")["cell"])),
                         "total_capital": node(float(g("total_capital_group_basel")["value"]),
                                               c.S(db, g("total_capital_group_basel")["cell"])),
                         "rwa": node(float(g("rwa_group_basel")["value"]), c.S(db, g("rwa_group_basel")["cell"])),
                         "tier1_ratio": node(float(g("tier1_ratio_group_basel")["value"]), c.S(db, g("tier1_ratio_group_basel")["cell"])),
                         "total_ratio": node(float(g("car_group_basel")["value"]), c.S(db, g("car_group_basel")["cell"])),
                         "cet1": null("CET1 группы в ДАТАБУКе не раскрыт (только Tier 1 и общий капитал)"),
                         "note": f"справочно: группа на {d_ru(dd)} — последняя дата ДАТАБУКа" +
                                 (f"; за {a.q_ru} ДАТАБУК не вышел" if dd < a.date else "")}
    out["instruments"] = [{k: r[k] for k in ("instrument", "isin", "layer", "currency", "nominal_issued", "coupon", "issue_date",
                                             "maturity_or_call", "status_2026")} | {"src": c.S(INSTRUMENTS_SHEET)}
                          for r in c.instr]
    out["instruments_total"] = node(at1, c.bsrc("bs_perp"), f"бессрочные в капитале МСФО на {a.ru}; срочные субординированные "
                                                            f"{ru(c.bv('bs_subdebt'))} — в обязательствах (книга wholesale)")
    hist = []
    for per in q_range(CAPITAL_HISTORY_FIRST, a.period):
        form = (q_end(per) + dt.timedelta(days=1)).isoformat()
        r = c.get(c.capb, form, f"{FACT_SHEETS}/capital_bank.csv: формы на {form}")
        s1 = c.S(r["doc135"]) + f", форма 0409135 на {form}"
        s2 = c.S(r["doc123"]) + f", форма 0409123 на {form}"
        row = {"period": per, "date": form, "basis": "RAS (банк соло)",
               "n1_0": node(float(r["n1_0"]), s1), "n1_1": node(float(r["n1_1"]), s1), "n1_2": node(float(r["n1_2"]), s1),
               "own_funds": node(float(r["capital_total_bn"]), s2), "base_capital": node(float(r["base_bn"]), s2),
               "rwa_n10": node(float(r["rwa_n10_bn"]), calc="собственные средства / Н1.0 [Р]")}
        qe = q_end(per).isoformat()
        gg, gt = c.capg.get(("rwa_group_basel", qe)), c.capg.get(("car_group_basel", qe))
        if gg and gt:
            row["group_basel_rwa"] = node(float(gg["value"]), c.S(db, gg["cell"]), basis="Basel (группа)")
            row["group_basel_total_ratio"] = node(float(gt["value"]), c.S(db, gt["cell"]), basis="Basel (группа)")
        hist.append(row)
    out["history"] = hist
    out["history_monthly"] = [{"date": r["form_date"], "n1_0": float(r["n1_0"]), "n1_1": float(r["n1_1"]), "n1_2": float(r["n1_2"]),
                               "own_funds": float(r["capital_total_bn"]), "base": float(r["base_bn"]),
                               "additional": float(r["additional_bn"]), "t2": float(r["t2_bn"]),
                               "src": c.S(r["doc135"]) + "; " + c.S(r["doc123"])}
                              for r in sorted(c.capb.values(), key=lambda x: x["form_date"])]
    R = c.bv("bs_fvoci_res")
    t2 = float(f["t2_bn"])
    base_impl = bvc + dp + at1 + t2 - k20
    out["core_form_check"] = {
        "note": "справка потоку капитала (ядро блок не читает): какие вычеты дают K20 якоря = собственным средствам банка "
                f"{ru(k20)} в форме ядра k20 = bv + dp − (1 − f)·R − ded20 + at1 + t2",
        "ded20_implied_f0": node(r6(base_impl - R), calc=f"f = 0: {ru(bvc)} + {ru(dp)} + {ru(-R)} + {ru(at1)} + {ru(t2)} − {ru(k20)}"),
        "ded20_implied_f1": node(r6(base_impl), calc=f"f = 1: {ru(bvc)} + {ru(dp)} + {ru(at1)} + {ru(t2)} − {ru(k20)}"),
        "ded20_anchor_formula": node(r6(bvc - base), calc="ключ deductions_anchor: anchor → bv − basel.cet1 = "
                                                          f"{ru(bvc)} − {ru(base)}"),
    }
    out["guarantees"] = guarantees(c)
    c.check("капитал: базовый + добавочный = основной (форма 0409123 банка)",
            abs(float(f["base_bn"]) + float(f["additional_bn"]) - float(f["main_bn"])) < 1e-6)
    c.check("капитал: RWA Н1.0 = собственные средства / Н1.0 (±0,5 млрд — округление норматива)",
            abs(k20 / n10 - float(f["rwa_n10_bn"])) < 0.5, f"{k20 / n10:.3f} / {f['rwa_n10_bn']}")
    return out


def databook_date(c: Ctx) -> str:
    """Последняя дата справочника банка (Базель группы) не позже якоря."""
    ds = sorted(d for (m, d) in c.capg if m == "rwa_group_basel" and d <= c.a.date)
    return ds[-1] if ds else c.a.date


# ================================================================== shares.json
def build_shares(c: Ctx) -> dict:
    a = c.a

    def sh(m: str, d: str | None = None) -> dict:
        d = d or a.date
        return c.get(c.shr, (m, d), f"{FACT_SHEETS}/shares.csv: {m} на {d}")

    def ss(m: str, d: str | None = None) -> str:
        r = sh(m, d)
        return c.S(r["doc"], str(r["page"]).split(" | ")[-1])

    def iv(m: str, d: str | None = None) -> int:
        v = sh(m, d)["value"]
        return int(v) if v != "nan" else 0

    def mn(m: str, d: str | None = None) -> float:
        v = sh(m, d)["value"]
        return round(int(v) / 1e6, 6) if v != "nan" else math.nan
    issued, outst = mn("issued_total"), mn("outstanding_total")
    own_row = [k for k in c.shr if k[0] == "treasury_bank_own" and k[1] <= a.date]
    own_date = max(d for _, d in own_row) if own_row else a.date
    own, sub = mn("treasury_bank_own", own_date), mn("treasury_insurance_sub")
    elig = mn("dividend_eligible")
    d = last_decision(c)
    out = {"basis": "IFRS", "as_of": a.date, "unit": "млн шт.; номинал — ₽",
           "issued_total": node(issued, ss("issued_total"), "выпущенные обыкновенные акции (прим. 22); одна категория, "
                                                            "дробления не было"),
           "issued_ordinary": node(issued, ss("issued_total"), "все выпущенные акции — обыкновенные"),
           "treasury_ordinary": node(mn("treasury_group"), ss("issued_total"), "собственные акции группы = выпущенные − в "
                                     f"обращении (банк {f'{own:.6f}'.replace('.', ',')} + страховая дочка "
                                     f"{f'{sub:.6f}'.replace('.', ',')})"),
           "outstanding_total": node(outst, ss("outstanding_total"), f"акции в обращении на {a.ru} (прим. 22)"),
           "outstanding_ordinary": node(outst, ss("outstanding_total")),
           "treasury_bank_own": node(own, ss("treasury_bank_own", own_date),
                                     f"собственные акции самого банка на {d_ru(own_date)} (= {int_ru(iv('issued_total'))} − "
                                     f"{int_ru(iv('issued_total') - iv('treasury_bank_own', own_date))});"
                                     + (f" принято неизменным на {a.ru} [В];" if own_date != a.date else "")
                                     + " по закону подлежат продаже или погашению в течение года [НП]"),
           "treasury_subsidiary": node(sub, ss("treasury_insurance_sub"),
                                       words(c, "treasury_subsidiary_words", "собственные акции у дочерних компаний группы [Р]")),
           "dividend_eligible": node(elig, ss("dividend_eligible"),
                                     "делитель дивиденда: выпущенные − собственные акции банка; "
                                     + (f"{money_ru(float(d['pool_declared_rub']))} ₽ / {dec_ru(float(d['dps']))} ₽; " if d else "")
                                     + "акции у дочерних компаний дивиденд получают (внутри группы)"),
           "divisor_note": "делитель «на акцию» ядра — outstanding_total (без ключа valuation.shares_basis); пул дивиденда — "
                           "dps × dividend_eligible (не issued_total, не outstanding_total)",
           "economic_treasury": node(0.0, calc="экономически собственных акций сверх собственных по МСФО нет: покупки страховой "
                                               "дочки — собственные акции МСФО (внутри treasury_ordinary)"),
           "depositary_block": node(0.0, calc="депозитарного блока нет"),
           "voting": null("число голосующих акций на дату собрания не раскрыто в первичке этапа 1"),
           "motivation_program": null(f"программа мотивации акциями не раскрыта в обобщённой отчётности {a.ytd_ru}"),
           "par_value": node(float(sh("par_value_rub")["value"]), ss("par_value_rub"), "номинал, ₽"),
           "by_ticker": {TICKER: {"class": "ordinary"}},
           "buyback_note": words(c, "buyback_note", "выкуп страховой дочкой; путь выкупа — суждение книги"),
           "corporate_actions": []}
    for r in c.acts:
        row = {"date": r["date"], "kind": r["kind"], "title": r["title"], "src": c.S(r["doc"]) + (f"; {r['note']}" if r["note"] else "")}
        if r["shares_before"]:
            row["shares_before"] = node(round(int(r["shares_before"]) / 1e6, 6), c.S(r["doc"]), "выпущенные акции до события, млн шт.")
            row["shares_after"] = node(round(int(r["shares_after"]) / 1e6, 6), c.S(r["doc"]), "выпущенные акции после события, млн шт.")
        if r["price"]:
            row["price"] = node(float(r["price"]), c.S(r["doc"]), "цена/оценка за акцию, ₽")
        out["corporate_actions"].append(row)
    c.check("акции: выпущенные − в обращении = собственные (банк + дочка)", abs(issued - outst - own - sub) < 1e-6,
            f"{issued} − {outst} против {own} + {sub}")
    c.check("акции: делитель дивиденда = выпущенные − собственные акции банка", abs(issued - own - elig) < 1e-6)
    return out


# ================================================================== dividends.json
# Политика (числа — лист dividend_policy.csv; слова — документ политики).
POLICY = dict(
    name="Дивидендная политика ПАО «Совкомбанк»", doc_title="Дивидендная политика ПАО «Совкомбанк», версия 2.0",
    approved_by="Наблюдательный совет, протокол № 29 от 20.11.2023", frequency="annual",
    payout_low_words="п. 5.2(б): от 25 % чистой прибыли по МСФО", payout_high_words="п. 5.2(б): до 50 %",
    cap_words="верх политики (50 %)",
    threshold_words="п. 5.2(г): выплата не снижает фактический Н1.0 банка ниже 11,5 % (порог политики, не требование ЦБ)",
    base="ifrs_ni (политика: «чистая прибыль по МСФО», без уточнения доли акционеров)",
    divisor="outstanding_bank (выпущенные − собственные акции банка; shares.dividend_eligible)",
    valid_until_why="срок действия в политике не указан (п. 8.1: изменения утверждает НС)",
    valid_until_note="политика действует до пересмотра Наблюдательным советом",
    text="Банк стремится распределять от 25 % до 50 % чистой прибыли по МСФО не реже раза в год; выплата не должна "
         "снижать Н1.0 банка ниже 11,5 %. С 2024 года выплата ниже политики (10–16 %).",
    pages="4–5")
DIVIDEND_NEWS = ("канал IR t.me/irsovcombank; сверка — календарь дивидендов брокера T-Invest (снимок соседа "
                 "svcb-capital-shares, 21.10.2026)")


def build_dividends(c: Ctx) -> dict:
    a = c.a

    def pol(k: str) -> dict:
        return c.get(c.pol, k, f"{FACT_SHEETS}/dividend_policy.csv: {k}")

    psrc = lambda k: c.S(pol(k)["doc"], pol(k)["page"])   # noqa: E731
    last = last_decision(c)
    base = POLICY["base"]
    if last:
        pool = float(last["pool_declared_rub"]) / 1e9
        base += (f"; факт {last['fiscal_year']}: {ru(100 * pool / float(last['ni_total_bn']), 1)} % всей прибыли, "
                 f"{ru(100 * pool / float(last['ni_shareholders_bn']), 1)} % прибыли акционеров")
    out = {"basis": "IFRS", "as_of": a.date, "unit": "DPS — ₽ на акцию; суммы — млрд ₽; доли",
           "policy": {"name": POLICY["name"], "doc": POLICY_DOC, "doc_title": POLICY["doc_title"],
                      "sha256": c.docs[POLICY_DOC]["sha256"] if POLICY_DOC in c.docs else c.miss(f"{FACT_SHEETS}/documents.csv: "
                                                                                                   f"{POLICY_DOC}"),
                      "approved": pol("approved")["value"], "approved_by": POLICY["approved_by"],
                      "frequency": POLICY["frequency"],
                      "payout_low": node(float(pol("payout_low")["value"]), psrc("payout_low"), POLICY["payout_low_words"]),
                      "payout_high": node(float(pol("payout_high")["value"]), psrc("payout_high"), POLICY["payout_high_words"]),
                      "cap": node(float(pol("payout_high")["value"]), psrc("payout_high"), POLICY["cap_words"]),
                      "threshold": node(float(pol("threshold_n1_0")["value"]), psrc("threshold_n1_0"), POLICY["threshold_words"]),
                      "base": base, "divisor": POLICY["divisor"],
                      "valid_until": null(POLICY["valid_until_why"]), "valid_until_note": POLICY["valid_until_note"],
                      "text": POLICY["text"], "src": c.S(POLICY_DOC, POLICY["pages"])},
           "history": [], "history_before": [], "years": {}, "register_seed": []}
    for r in c.div:
        docs = r["doc"].split(" | ")
        pg = r["page"].split(" | ")
        s_main = c.S("|".join(d for d in docs if d), "|".join(pg[:len([d for d in docs if d])]))
        dps = float(r["dps"])
        pool = float(r["pool_declared_rub"]) / 1e9
        fy = r["fiscal_year"]
        np_sh = c.get(c.cum, ("np_sh", f"FY{fy}"), f"{FACT_SHEETS}/pnl_cumulative.csv: np_sh FY{fy}")
        np_all = c.get(c.cum, ("np", f"FY{fy}"), f"{FACT_SHEETS}/pnl_cumulative.csv: np FY{fy}")
        cpn = c.get(c.eqf, ("perp_coupon", f"FY{fy}"), f"{FACT_SHEETS}/equity_flows.csv: perp_coupon FY{fy}")
        row = {"year": int(fy), "period": r["period"], "label": r["label"],
               "dps": node(dps, s_main, "решение собрания, ₽ на акцию"),
               "dps_ordinary": node(dps, s_main, "одна категория акций"),
               "dps_pre_split": node(dps, s_main, "дробления не было"), "split_factor": 1,
               "recommended_date": r["recommended_date"], "decided_date": r["decided_date"], "decided_by": r["decided_by"],
               "record_date": r["record_date"], "last_buy_date": r["last_buy_date"], "ex_date": r["ex_date"],
               "pay_date": r["pay_date"], "pay_deadline_others": r["pay_deadline_others"] or None,
               "settlement": r["settlement"],
               "pool_declared": node(r6(pool), s_main, "сумма решения, млрд ₽" + (f" = {dps} × {int(r['eligible_shares']):,} акций"
                                                                                 .replace(",", " ") if r["eligible_shares"] else "")),
               "ni_shareholders": node(float(r["ni_shareholders_bn"]), c.S(np_sh["doc"], np_sh["page"]),
                                       "отчётная прибыль акционеров за год (МСФО)"),
               "ni_total": node(float(r["ni_total_bn"]), c.S(np_all["doc"], np_all["page"])),
               "at1_coupon": node(float(r["at1_coupon_bn"]), c.S(cpn["doc"], cpn["page"]),
                                  "купон бессрочных за год величиной (отчёт об изменениях капитала)"),
               "tax_statutory": node(float(r["tax_statutory"]), calc=PROSE["tax_statutory"]),
               "payout_shareholders": node(r6(pool / float(r["ni_shareholders_bn"])), calc="pool_declared / ni_shareholders"),
               "sources": [f"manual: {broker_words(r['note'])}", f"news: {DIVIDEND_NEWS}"]}
        if r["eligible_shares"]:
            row["eligible_shares"] = node(round(int(r["eligible_shares"]) / 1e6, 6), s_main, "акций в расчёте суммы, млн шт.")
            c.check(f"дивиденды за {fy}: сумма решения = DPS × акции в расчёте (±1 ₽)",
                    abs(dps * int(r["eligible_shares"]) - float(r["pool_declared_rub"])) <= 1.0)
        if r["pay_deadline_decision"]:
            row["pay_deadline_decision"] = r["pay_deadline_decision"]
        c.check(f"дивиденды за {fy}: реестр — 10–20 дней после решения; экс-дата = реестр; покупка — рабочий день до реестра",
                10 <= (dt.date.fromisoformat(r["record_date"]) - dt.date.fromisoformat(r["decided_date"])).days <= 20
                and r["ex_date"] == r["record_date"] and r["last_buy_date"] < r["record_date"])
        out["history"].append(row)
    out["history"].sort(key=lambda x: x["year"])
    for r in c.divb:
        out["history_before"].append({"year": r["year"], "label": r["label"],
                                      "dps": node(float(r["dps"]), c.S("research/facts/svcb_dividends.csv"), broker_words(r["src"])),
                                      "total": node(round(float(r["total_mn"]) / 1000, 3), c.S("research/facts/svcb_dividends.csv"),
                                                    broker_words(r["src"])),
                                      "decided_date": r["decided_date"] or None, "record_date": r["record_date"] or None,
                                      "kind": r["kind"], "note": r["note"]})
    first = q_parse(a.quarters[0])[0]
    for y in range(first, a.y + (1 if a.k == 4 else 0)):
        r = c.get(c.cum, ("np_sh", f"FY{y}"), f"{FACT_SHEETS}/pnl_cumulative.csv: np_sh FY{y}")
        out["years"][str(y)] = {"ni_shareholders": node(r6(float(r["value_mn"]) / 1000), c.S(r["doc"], r["page"])),
                                "complete": True, "through": f"{y}Q4"}
    if a.k < 4:
        r = c.get(c.cum, ("np_sh", a.ytd), f"{FACT_SHEETS}/pnl_cumulative.csv: np_sh {a.ytd}")
        out["years"][str(a.y)] = {"ni_shareholders": node(r6(float(r["value_mn"]) / 1000), c.S(r["doc"], r["page"])),
                                  "complete": False, "through": a.period}
    snap = SNAPSHOT["sheets_as_of"]
    for r in sorted(c.div, key=lambda x: x["decided_date"]):
        if not (r["decided_date"] <= snap and r["ex_date"] > a.date):
            continue
        h = [x for x in out["history"] if x["year"] == int(r["fiscal_year"])][0]
        out["register_seed"].append({"year": int(r["fiscal_year"]), "period": r["period"], "label": r["label"], "dps": h["dps"],
                                     "status": "paid" if r["pay_date"] <= snap else "declared",
                                     "recommended_date": r["recommended_date"], "decided_date": r["decided_date"],
                                     "record_date": r["record_date"], "last_buy_date": r["last_buy_date"], "ex_date": r["ex_date"],
                                     "pay_date": r["pay_date"],
                                     "sources": words(c, f"register_seed_sources_{r['fiscal_year']}",
                                                      [f"manual: {broker_words(r['note'])}", f"news: {DIVIDEND_NEWS}"])})
    if out["register_seed"]:
        out["register_seed_note"] = words(c, "register_seed_note",
                                          "решение с экс-датой позже якоря — запись реестра (обязательство на якоре — "
                                          "balance.dividends_payable)")
    rules = sorted((r for r in c.div if r["pay_deadline_decision"]), key=lambda x: x["decided_date"])
    rule_words = ""
    if rules:
        pdd = rules[-1]["pay_deadline_decision"]
        rule_words = (f"; решение {rules[-1]['decided_date'][:4]} года: «в срок до {int(pdd[8:])} {MONTHS_GEN[int(pdd[5:7]) - 1]} "
                      f"{pdd[:4]} года»")
    out["dates_rule"] = ("Реестр (record_date) — решение собрания; торги T+1: последний день покупки — рабочий день до реестра, "
                         "экс-дата = дата реестра. Срок выплаты номинальным держателям — 10 рабочих дней после реестра, прочим — 25 "
                         "(политика, п. 4.7; закон об АО)" + rule_words + ".")
    hs = out["history"]
    out["broker_check"] = (f"DPS и даты реестра за {hs[0]['year']}–{hs[-1]['year']} годы сверены с {BROKER_SNAPSHOT}: "
                           + "; ".join(f"{dec_ru(x['dps']['v'])} ₽ / {d_ru(x['record_date'])}" for x in hs) + " — совпало")
    out["snapshot"] = snap
    return out


# ================================================================== bridge_mgmt_ifrs.json
BRIDGE_DEFS = {
    "nim": "ЧПМ движка = nii × 365/d / средние процентные активы движка (5 кредитных книг + долговые бумаги + "
           "ликвидность — процентная часть; среднее начала и конца квартала); nii движка — с финансовыми расходами "
           "страхования (книга insurance_liab); engine_x4 — то же × 4; упр. — ЧПМ банка: ЧПД формы × 4 / средние "
           "процентные активы банка (без денежных средств и ЦБ, кредиты — нетто, инструменты ССПУ/ССПСД с акциями; "
           "ДАТАБУК NIM!6); банк финансовые расходы страхования в ЧПМ не включает. Мост: nim_eng = nim_bank × R_iea − "
           "ife × l_ins, R_iea = ПА банка / ПА движка (value_iea), ife — ставка книги insurance_liab, l_ins — её "
           "остаток к ПА движка; value — ratio с ними внутри (ядро держит одно число)",
    "cor": "CoR движка = −llp_debt_fa × 365/d / средняя сумма пяти кредитных книг (валовые, с кредитами по СС); упр. — "
           "резервы по кредитам × 4 / средний валовой портфель (ДАТАБУК COR!6{note})",
    "cir": "C/I движка = −opex / (nii + fees_net + insurance_net + misc_net); упр. — (персонал + АХР) / (ЧПД + ЧКД + "
           "чистый доход небанковской деятельности) (ДАТАБУК NIM!59{note})",
}


def build_bridges(c: Ctx) -> dict:
    a = c.a
    s0 = c.get(c.brs, "nim", f"{FACT_SHEETS}/bridges_summary.csv: nim")
    w0, w1 = s0["window_from"], s0["window_to"]
    out = {"basis": "mgmt↔IFRS", "as_of": a.date, "unit": "доли, годовые", "window": [w0, w1],
           "direction": "nim: method ratio — to_engine(v) = v × value, gap = engine / mgmt (значение — среднее gap_x4 по окну); "
                        "cor, cir: method additive — to_engine(v) = v + value, gap = engine − mgmt. Окно "
                        f"{qk(w0)}–{qk(w1)} (договор ведущего); история {qk(BRIDGE_HISTORY_FIRST)}–{qk(a.period)}. Упр. — "
                        f"определения банка (ДАТАБУК; {a.q_ru} — расчёт по определению)."}
    defs = {"nim": BRIDGE_DEFS["nim"],
            "cor": BRIDGE_DEFS["cor"].format(note=words(c, "bridge_cor_def_note", "")),
            "cir": BRIDGE_DEFS["cir"].format(note=words(c, "bridge_cir_def_note", ""))}
    for m in ("nim", "cor", "cir"):
        s = c.get(c.brs, m, f"{FACT_SHEETS}/bridges_summary.csv: {m}")
        o = {"method": s["method"], "window": [s["window_from"], s["window_to"]],
             "value": node(float(s["value"]), calc=f"среднее {'gap_x4' if m == 'nim' else 'gap'} по окну {s['window_from']}–"
                                                  f"{s['window_to']} (n = {s['n']})"),
             "sd": node(float(s["sd"]) if s["sd"] else None, calc="выборочное стандартное отклонение по окну"),
             "sd_all": node(float(s["sd_all"]), calc=f"по всей истории (n = {s['n_all']})"),
             "n": node(int(s["n"]), calc="кварталов в окне"), "definition": defs[m], "history": []}
        gaps = []
        for q in q_range(BRIDGE_HISTORY_FIRST, a.period):
            r = c.brg.get((m, q))
            if r is None:
                c.miss(f"{FACT_SHEETS}/bridges.csv: {m} {q}")
                continue
            k = c.kpi.get((f"{m}_exact", q))
            if k is not None:
                ksrc = c.S(k["doc"], k["page"]) if k["doc"] else None
                mg = node(float(k["value"]), ksrc, k["note"] or ("точное значение ДАТАБУКа" if k["cls"] == "Ф" else
                                                                 "расчёт по определению банка"))
                if k["cls"] == "В":
                    mg = est(float(k["value"]), k["note"], (float(k["range_low"]), float(k["range_high"])), src=ksrc)
            else:
                mg = null("нет упр. значения")
            row = {"period": q, "mgmt": mg,
                   "engine": node(float(r["engine"]), calc=f"движок: d = {r['days']}; средние процентные активы {r['iea_avg']}, "
                                                          f"кредитные книги {r['loans_avg']}, доход для C/I {r['income_engine']}")}
            if m == "nim":
                row["engine_x4"] = node(float(r["engine_x4"]), calc="nii × 4 / средние процентные активы движка")
                row["gap"] = node(float(r["gap"]), calc="engine / mgmt")
                row["gap_x4"] = node(float(r["gap_x4"]), calc="engine_x4 / mgmt")
                row["engine_form_x4"] = node(float(r["engine_form_x4"]), calc="ЧПД формы × 4 / средние процентные активы движка")
                row["gap_iea_x4"] = node(float(r["gap_iea_x4"]), calc="engine_form_x4 / mgmt = ПА банка / ПА движка (R_iea)")
                row["ife_share"] = node(float(r["ife_share_of_nii_form"]), calc="финансовые расходы страхования / ЧПД формы")
            else:
                row["gap"] = node(float(r["gap"]), calc="engine − mgmt")
            if m == "cor":
                row["engine_books"] = dict(row["engine"])
                row["gap_books"] = dict(row["gap"])
            if s["window_from"] <= q <= s["window_to"]:
                gaps.append(float(r["gap_x4"] if m == "nim" else r["gap"]))
            o["history"].append(row)
        if gaps:
            c.check(f"мосты упр. ↔ движок: {m} — value = среднему по окну ({len(gaps)} кв.)",
                    abs(statistics.fmean(gaps) - float(s["value"])) < 5e-6 and len(gaps) == int(s["n"]),
                    f"{statistics.fmean(gaps):.6f} / {s['value']}")
        if m == "nim":
            si = c.get(c.brs, "nim_iea", f"{FACT_SHEETS}/bridges_summary.csv: nim_iea")
            o["value_iea"] = node(float(si["value"]), calc=f"справочно: среднее gap_iea_x4 по окну {si['window_from']}–"
                                                         f"{si['window_to']} — мост знаменателей R_iea без финансовых расходов "
                                                         "страхования (для перевода уровня и передачи банка, решения ведущего "
                                                         "№ 1, п. 6)")
        if m == "cor":
            o["value_books"] = dict(o["value"])
            o["value_ac_only"] = node(float(s["value"]), calc="кредиты по СС не выделены (fv_share = 0): то же, что value_books")
        out[m] = o
    return out


# ================================================================== mgmt_quarterly.json
MGMT_METRICS = ("nim", "nim_exact", "cor", "cor_exact", "cir", "cir_exact", "roe_exact", "op_np_exact", "cost_of_funding",
                "cost_of_funding_exact", "asset_yield", "asset_yield_exact", "ram")


def build_mgmt(c: Ctx) -> dict:
    a = c.a
    out = {"basis": "mgmt", "as_of": a.date, "unit": "доли, годовые; op_np, op_equity — млрд ₽",
           "note": words(c, "mgmt_note", "напечатанное (презентации банка) — без суффикса; точное — с суффиксом _exact: ДАТАБУК "
                                         "банка (ячейка) или расчёт по определению банка из МСФО"),
           "quarters": {}, "halfyear": {}, "history_gaps": []}
    for q in a.quarters:
        row = {}
        for m in MGMT_METRICS:
            k = c.kpi.get((m, q))
            if k is None:
                continue
            src = c.S(k["doc"], k["page"]) if k["doc"] else None
            if k["cls"] == "В":
                row[m] = est(float(k["value"]), k["note"], (float(k["range_low"]), float(k["range_high"])), src=src)
            else:
                row[m] = node(float(k["value"]), src, k["note"] or None)
        oe = c.kpi.get(("op_equity", q_end(q).isoformat()))
        if oe:
            row["op_equity"] = node(float(oe["value"]), c.S(oe["doc"], oe["page"]), oe["note"])
        out["quarters"][q] = row
        missing = [m for m in ("nim", "cor", "cir") if m not in row]
        if missing:
            out["history_gaps"].append({"period": q, "basis": "mgmt",
                                        "reason": "напечатанное значение квартала не найдено в доступных презентациях: " +
                                                  ", ".join(missing) + " (есть точное из ДАТАБУКа или расчёт)"})
    for m in ("nim", "cor", "cir"):
        if (f"{m}_exact", a.period) not in c.kpi and (m, a.period) not in c.kpi:
            c.miss(f"{FACT_SHEETS}/mgmt_kpi.csv: {m} или {m}_exact за {a.period} (упр. метрика квартала якоря — ядру обязательна)")
    out["annual"] = {}
    first = q_parse(a.quarters[0])[0]
    halves = sorted({p for (_, p) in c.kpi if re.fullmatch(r"\d{4}H[12]", p) and p[:4] <= str(a.y)})
    for y in range(first, a.y + (1 if a.k == 4 else 0)):
        row = {}
        for m in ("nim", "cor", "cir"):
            k = c.kpi.get((f"{m}_exact", f"{y}FY"))
            row[m] = node(float(k["value"]), c.S(k["doc"], k["page"]), "точное годовое значение ДАТАБУКа") if k else \
                null("в ДАТАБУКе нет годового значения")
        roe_h = [f"1П{h[:4]} — {round(100 * float(c.kpi[('roe', h)]['value']))} %" for h in reversed(halves)
                 if ("roe", h) in c.kpi]
        row["roe"] = null("годовой ROE банка в доступной первичке этапа 1 не напечатан" +
                          (f" ({', '.join(roe_h)})" if roe_h else ""))
        out["annual"][str(y)] = row
    for h in halves:
        out["halfyear"][h] = {m: node(float(c.kpi[(m, h)]["value"]), c.S(c.kpi[(m, h)]["doc"], c.kpi[(m, h)]["page"]))
                              for m in ("nim", "cor", "cir", "roe") if (m, h) in c.kpi}
    return out


# ================================================================== guidance.json
GUIDANCE_ITEMS = ("roe", "nim", "cor_max", "cir", "op_np_growth", "dps_growth", "roe_target", "fee_growth", "n20_0",
                  "loan_growth_corporate", "loan_growth_retail")


def build_guidance(c: Ctx) -> dict:
    items = {k: null(PROSE["guidance_why"]) for k in GUIDANCE_ITEMS}
    g = c.guid[0] if c.guid else c.miss(f"{FACT_SHEETS}/guidance.csv: строка о гайденсе года")
    return {"basis": "mgmt", "year": c.a.y, "as_of": SNAPSHOT["sheets_as_of"], "unit": "доли",
            "note": PROSE["guidance_note"],
            "items": items,
            "history": [{"date": g["date"], "key": g["key"], "value": None, "event": g["event"], "note": g["text"] + "; " + g["note"],
                         "src": c.S("research/samples/svcb-business_tg_irsovcombank_20261021.json", g["page"])}]}


# ================================================================== calendar.json
CALENDAR_SOURCES = ("srm_cbr_cal_mp_20261021.html", "svcb_release_calendar.csv", "calendar_2026Q4_2028.tsv",
                    "svcb_capital_instruments.csv")


def build_calendar(c: Ctx) -> dict:
    snap = SNAPSHOT["sheets_as_of"]
    srcs = []
    for f in CALENDAR_SOURCES:
        if f in c.docs:
            d = c.docs[f]
            srcs.append({"key": d["key"], "title": doc_title(d), "url": d["url"], "accessed": snap, "file": d["file"],
                         "sha256": d["sha256"]})
    ev = []
    for e in c.cal:
        year = int(e["date"][:4])
        row = {"id": e["id"], "kind": e["kind"], "date": e["date"], "title": calendar_words(e["title"], year),
               "covers": e["covers"] or None,
               "confirmed": e["confirmed"] == "true", "precision": e["precision"], "src": c.S(e["src"])}
        if e["estimated"] == "true":
            row["estimated"] = True
            row["earliest"], row["latest"] = e["earliest"], e["latest"]
        if calendar_words(e["note"], year):
            row["note"] = calendar_words(e["note"], year)
        ev.append(row)
    nxt = [e for e in ev if e["kind"] == "ifrs" and e["covers"] == c.a.next]
    c.check(f"календарь: есть событие отчёта МСФО за следующий квартал ({c.a.next})", bool(nxt))
    return {"as_of": snap,
            "horizon": PROSE["calendar_horizon"],
            "note": "confirmed: true — дата объявлена (календарь Банка России, решение собрания); estimated: true — день по "
                    "прецеденту внутри окна earliest–latest. Файл ведётся вручную (лист sheets/calendar.csv); kind ras — формы "
                    "банка 0409101/102/123/135 (вместо form805 группы — она не публикуется).",
            "sources": srcs, "events": ev}


# ================================================================== peers.json
def build_peers(c: Ctx) -> dict:
    a = c.a
    banks = [json.loads(r["json"]) for r in c.peers]
    banks.sort(key=lambda b: PEER_ORDER.index(b["ticker"]) if b["ticker"] in PEER_ORDER else 99)
    snap = SNAPSHOT["sheets_as_of"]
    year_ago = q_end(f"{a.y - 1}Q{a.k}").isoformat()
    return {"as_of": snap,
            "basis": f"МСФО групп на {a.ru}. Капитал для P/B — капитал обыкновенных акционеров (без бессрочных инструментов). "
                     f"Прибыль для P/E и ROE — чистая прибыль акционерам за {qk(q_next(f'{a.y - 1}Q{a.k}'))}–{qk(a.period)}; ROE — к "
                     f"среднему капиталу на {d_ru(year_ago)} и {a.ru}. Норматив — как раскрыт банком (название — в строке).",
            "subject_ticker": TICKER,
            "note": PROSE["peers_note"].format(anchor=a.ru),
            "sources": [{"key": "t_peers", "title": PROSE["t_peers_title"],
                         "url": "", "accessed": snap, "file": "T-Technologies/t-850/data/facts/peers.json",
                         "sha256": c.peers[0]["src_sha256"] if c.peers and "src_sha256" in c.peers[0] else ""},
                        {"key": "t_facts", "title": f"Факты модели Т-Технологий на якоре {a.ru}", "url": "",
                         "accessed": snap, "file": "T-Technologies/t-850/data/facts/*.json", "sha256": ""}],
            "banks": banks}


# ================================================================== bridge_ras_ifrs.json
RAS_SRC = "research/facts/sdn/bridge_ras_ifrs_quarterly.csv"


def build_ras(c: Ctx) -> dict:
    a = c.a
    qs, nq = [], []
    for r in c.ras:
        p = r["period"]
        if p not in a.quarters:
            continue
        sh_ = float(c.get(c.cmp, (p, "ni_shareholders"), f"{FACT_SHEETS}/pnl_composition.csv: ni_shareholders {p}")["value_mn"]) / 1000
        if r["ras_ni"]:
            ras = float(r["ras_ni"])
            qs.append({"period": p, "ras_ni": node(ras, c.S(RAS_SRC), "прибыль банка за квартал по форме 0409102 (рег. 963)"),
                       "ifrs_ni_sh": node(r6(sh_), calc=f"pnl_quarterly.{p}.ni_shareholders"),
                       "ratio": node(r6(sh_ / ras) if ras else None, calc="ifrs_ni_sh / ras_ni"),
                       "src": c.S(RAS_SRC)})
        if r["ras_nii"]:
            nii = float(c.cmp[(p, "nii")]["value_mn"]) / 1000
            nq.append({"period": p, "ras": node(float(r["ras_nii"]), c.S(RAS_SRC), "ЧПД банка за квартал по форме 0409102"),
                       "ifrs": node(r6(nii), calc=f"pnl_quarterly.{p}.nii"),
                       "ratio": node(r6(nii / float(r["ras_nii"])), calc="ifrs / ras"),
                       "src": c.S(RAS_SRC)})
    if not nq or nq[-1]["period"] != a.period:
        c.miss(f"{FACT_SHEETS}/ras_bridge.csv: ЧПД банка по форме 0409102 за {a.period}")
        if not nq:
            return {}
    ratios = [x["ratio"]["v"] for x in nq]
    last = nq[-1]
    rr = [(r["period"], float(r["ifrs_np_total"]) / float(r["ras_ni"])) for r in c.ras
          if r["period"] in a.quarters and r["ras_ni"] and float(r["ras_ni"])]
    why = ("нет данных: прибыль банка по РСБУ не предсказывает прибыль группы (отношение "
           f"{ru(min(x for _, x in rr), 2)}…{ru(max(x for _, x in rr), 2)} за {qk(rr[0][0])}–{qk(rr[-1][0])})")
    return {"basis": "RAS→IFRS", "as_of": a.date, "unit": "млрд ₽ за квартал; отношения — доли",
            "definition": "справочный ряд (ядру не нужен; нау-каст): ratio = отчётная прибыль акционеров группы (МСФО) / прибыль "
                          "банка по РСБУ за квартал (форма 0409102, рег. 963); ЧПД — то же",
            "quarters": qs, "by_quarter": {str(k): null(why) for k in (1, 2, 3, 4)},
            "nii": {"definition": "ras — ЧПД банка за квартал по форме 0409102; ifrs — ЧПД движка группы (pnl_quarterly.nii: "
                                  "ЧПД формы МСФО + финансовые расходы страхования)",
                    "method": "prev_quarter", "method_note": "value — отношение последнего отчётного квартала",
                    "window": [last["period"], last["period"]], "quarters": nq,
                    "value": node(last["ratio"]["v"], calc=f"ratio квартала {last['period']}"),
                    "n": node(1, calc="кварталов в окне"),
                    "sd": node(r6(statistics.stdev(ratios[-6:])), calc="выборочное стандартное отклонение ratio за последние 6 кварталов"),
                    "by_quarter": {str(k): null("сезонности нет: ряд короткий и сдвигается со ставкой") for k in (1, 2, 3, 4)}},
            "iea": {"basis": "RAS (банк соло)", "definition": "процентные активы банка по форме 0409101 — для нау-каста ЧПМ; "
                                                              "разметка кодов счетов — работа сборщика фаз 4–5",
                    "codes": None, "codes_required": None, "codes_note": "не размечено на этапе 1",
                    "by_quarter": {str(k): null("моста активов нет") for k in (1, 2, 3, 4)},
                    "value": null("процентные активы по форме 0409101 не размечены (поток facts этапа 1)")},
            "cor": null(words(c, "ras_cor_why", "моста резервов нет: резервы РСБУ и МСФО несопоставимы поквартально"))}


# ================================================================== nii_books.json
NII_WORDS = {  # книга → (строки в словах узла: столбец, подпись) и приписка
    "auto": ([("ii_auto", "автокредиты")], ""), "mortgage": ([("ii_mortgage", "ипотечные кредиты")], ""),
    "cash_loans": ([("ii_consumer", "потребительские кредиты")], ""),
    "cards": ([("ii_cards", "карты рассрочки")], " (в т. ч. доходы партнёров «Халвы»)"),
    "corp_loans": ([("ii_corp", "кредиты корпоративным клиентам"), ("ii_lease", "финансовая аренда")], ""),
    "securities": ([("ii_fvtpl", "ССПУ"), ("ii_fvoci", "ССПСД"), ("ii_ac_bonds", "облигации АС"),
                    ("ii_ac_bank_bonds", "облигации банков АС")], ""),
    "liquidity": ([("ii_banks", "средства в банках и финансовых институтах")], " (остаток — процентные статьи, п. 3)"),
    "retail_current": ([("ie_ind_current", "ФЛ: текущие счета")], ""), "retail_term": ([("ie_ind_term", "ФЛ: срочные депозиты")], ""),
    "corp_term": ([("ie_corp_term", "ЮЛ: срочные депозиты"), ("ie_corp_repo", "ЮЛ: репо")], ""),
    "corp_current": ([("ie_corp_current", "ЮЛ: текущие счета")], ""),
    "wholesale": ([("ie_banks", "банки"), ("ie_debt_sec", "выпущенные бумаги"), ("ie_dfa", "ЦФА"),
                   ("ie_sub_debt", "субординированный долг"), ("ie_other_borrowed", "прочие заёмные")], ""),
}
KEY_RATE_RESEARCH = "research/facts/svcb-history/key_rate_quarterly.csv"
INS_FIN_SHEET = "ins_finance_quarterly.csv"


def build_nii_books(c: Ctx) -> dict:
    a = c.a
    q = c.get(c.interest, a.period, f"{INTEREST_SHEET}: проценты по продуктам и источникам за {a.period}")
    num = lambda k: float(q[k]) if q.get(k) not in (None, "") else 0.0   # noqa: E731
    page = re.search(r"с\. (\d+)", q.get("source") or "")
    ife_rows = {r["period"]: r for r in read_csv(c.need_file(c.root / FACT_SHEETS / INS_FIN_SHEET))}
    ife = -float(c.get(ife_rows, a.period, f"{FACT_SHEETS}/{INS_FIN_SHEET}: {a.period}")["value_mn"]) / 1000
    kr = {r["quarter"]: r for r in read_csv(c.need_file(c.root / KEY_RATE_RESEARCH))}
    key_ref = float(c.get(kr, a.period, f"{KEY_RATE_RESEARCH}: {a.period}")["kr_avg"]) / 100
    sha_open = c.docs.get(a.open_doc, {}).get("sha256", "")[:16]
    bal = {}
    for b in BOOKS:
        bal[b] = (float(c.book_total(b, a.open_date)["value_mn"]) / 1000, float(c.book_total(b, a.date)["value_mn"]) / 1000)
    inter = {}
    for b in BOOKS:
        if b == INSURANCE_BOOK:
            inter[b] = round(ife, 3)
        else:
            sign = 1.0 if b in ASSET_BOOKS else -1.0
            inter[b] = round(sign * sum(num(k) for k in INTEREST_LINES[b]) / 1000, 3)
    nii_form = num("nii") / 1000
    nii_eng = round(nii_form - ife, 3)
    outside = round(sum(num(k) for k in INTEREST_OUTSIDE) / 1000, 3)
    dia = round(abs(num("dia")) / 1000, 3)
    ins_page = c.gap("ins_finance_note")[2]          # страница примечания о страховании (финансовые расходы квартала)
    out = {"basis": "IFRS", "as_of": a.date, "period": a.period,
           "days": {"v": a.days, "calc": f"дней в квартале {a.q_ru} (act/365)"},
           "unit": "остатки и проценты — млрд ₽; ставки — доли, годовые, act/365",
           "rates_carry_residual": False, "books": {}}
    for b in BOOKS:
        o, cl = bal[b]
        i = inter[b]
        if b == INSURANCE_BOOK:
            words_ = (f"финансовые расходы от страховой деятельности {ru(i)} (прим. 7; МСФО 17) — в ЧПД движка (решения № 1, "
                      "п. 6)")
        else:
            lines, tail = NII_WORDS[b]
            words_ = " + ".join(f"{w} {ru(abs(num(k)) / 1000)}" for k, w in lines if q.get(k) not in (None, "")) + tail
        out["books"][b] = {
            "balance_open": {"v": round(o, 3), "src": f"{a.open_doc}, примечания 12–19 и ОФП, sha256 {sha_open}",
                             "calc": f"остаток книги на {d_ru(a.open_date)} (stage1/facts/sheets/books_balances.csv)"},
            "balance_close": {"v": round(cl, 3), "calc": f"остаток книги на {a.ru} (balance.books.{b})"},
            "balance_avg": {"v": round((o + cl) / 2, 4), "calc": "(balance_open + balance_close) / 2"},
            "interest_q": {"v": round(i, 3), "src": nb_src(c, a, page),
                           "calc": words_ + ("; величиной (в отчёте — со знаком минус)" if b in LIAB_BOOKS else "")},
            "rate_anchor": {"v": round(i / ((o + cl) / 2) * 365 / a.days, 6),
                            "calc": f"interest_q / balance_avg × 365/{a.days} (доля, act/365)"},
        }
    ia = sum(inter[b] for b in ASSET_BOOKS)
    il = sum(inter[b] for b in LIAB_BOOKS)
    iea = sum((bal[b][0] + bal[b][1]) / 2 for b in ASSET_BOOKS)
    diff = ia - il - dia + outside - nii_eng
    out.update({
        "interest_assets_q": {"v": round(ia, 3), "calc": "Σ interest_q книг активов"},
        "interest_liabilities_q": {"v": round(il, 3), "calc": "Σ interest_q книг пассивов (величиной)"},
        "other_interest_net_q": {"v": outside, "src": nb_src(c, a, page),
                                 "calc": "проценты вне книг (остаются в ЧПД, в ставки книг не входят): чистый доход по "
                                         f"сделкам своп в иностранной валюте {ru(num('ii_swaps') / 1000)}; обязательства по "
                                         f"аренде {ru(num('ie_lease') / 1000)}"},
        "dia_q": {"v": dia, "src": nb_src(c, a, page), "calc": "расходы, связанные со страхованием вкладов, за квартал, величиной"},
        "nii_q": {"v": nii_eng, "src": nb_src(c, a, page, ins_page),
                  "calc": f"ЧПД движка {a.q_ru} = ЧПД формы {ru(nii_form)} − финансовые расходы страхования {ru(ife)} (решения "
                          "ведущего № 1, п. 6); = interest_assets_q − interest_liabilities_q (с книгой insurance_liab) − dia_q + "
                          f"other_interest_net_q (сверка {ru(abs(diff))})"},
        "nii_form_q": {"v": round(nii_form, 3), "src": nb_src(c, a, page),
                       "calc": "справочно: строка «Чистый процентный доход» формы (ЧПМ банка — по ней)"},
        "iea_avg": {"v": round(iea, 3), "calc": "Σ balance_avg книг активов (кредитные книги, долговые бумаги, ликвидность)"},
        "nim_eng_q": {"v": round(nii_eng * 365 / a.days / iea, 6),
                      "calc": f"nii_q × 365/{a.days} / iea_avg (ЧПМ базиса движка; ЧПД — с финрасходами страхования)"},
        "current_share_anchor": {"v": round(bal["retail_current"][1] / (bal["retail_current"][1] + bal["retail_term"][1]), 6),
                                 "calc": "текущие счета физлиц / (текущие счета + срочные вклады физлиц) на якоре"},
        "key_avg_anchor_q": {"v": round(key_ref, 6),
                             "src": f"{KEY_RATE_RESEARCH} (средняя ключевая Банка России за квартал по календарным дням)"},
    })
    c.check("проценты книг − страхование вкладов + проценты вне книг = ЧПД движка (с книгой insurance_liab)", abs(diff) < 1e-6,
            f"{ia:.3f} − {il:.3f} − {dia} + {outside} − {nii_eng} = {diff:.6f}")
    return out


def nb_src(c: Ctx, a: Anchor, page, ins_page: str | None = None) -> str:
    sha = c.docs.get(a.report_doc, {}).get("sha256", "")[:16]
    p = page.group(1) if page else ""
    return f"{a.report_doc}, с. {p} (прим. 4)" + (f" и с. {ins_page} (прим. 7)" if ins_page else "") + f", sha256 {sha}"


# ================================================================== credit_products.json
# Стоимость риска по пяти кредитным книгам (решения ведущего № 3, Р3 и Р11): справочник банка (лист COR) по кварталам,
# квартал якоря — МСФО за период минус справочник прошлого квартала; МСФО по годам и окна прочтений М7 — листы кругов 2–3.
# Узел калибровки книги (ядро не читает; читают правила класса 6): на якоре, где он собран, — из листов; на другом
# якоре — переносится из прежних фактов как есть (пересчёт — листом круга калибровки).
CP_ANCHOR = "2026Q2"
CP = dict(
    gross_row={"cash_loans": 19, "cards": 20, "auto": 21, "mortgage": 22, "corp_loans": 34},
    llp_row={"cash_loans": 43, "cards": 44, "auto": 46, "mortgage": 47, "corp_loans": 50}, llp_corp_fallback=48,
    first="2018Q4", last_databook="2026Q1", h1_label="1П2026",
    ecl_col={"auto": "auto", "mortgage": "mortgage", "cash_loans": "cash", "cards": "cards", "corp_loans": "corporate"},
    ecl_prod={"auto": ("auto",), "mortgage": ("mortgage",), "cash_loans": ("cash",), "cards": ("cards",),
              "corp_loans": ("corp_large", "regions", "sme_other")},
)


def _years(*ys):
    return [f"{y}Q{k}" for y in ys for k in (1, 2, 3, 4)]


CP_R_QUARTERS = ["2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"]
CP_WINDOWS = {
    "q2_2026": (["2026Q2"], ["1П2026"], ["regimes.soft.cor.2026"], "2К2026 (нау-каст мягкой посадки); МСФО — 6М2026"),
    "q1_2026": (["2026Q1"], ["1П2026"], ["regimes.downturn.cor.2026", "regimes.crisis.cor.2026"],
                "1К2026 (нау-каст спада и кризиса); МСФО — 6М2026"),
    "norm_2026": ("norm_2026", "norm_2026", ["regimes.norm.cor.2026"],
                  "середина 1П2026 и окна R (как ключ 2026 нормы): датабук — середины уровней всего и на якоре; МСФО — "
                  "середина уровней на якоре 6М2026 и окна R"),
    "soft": (_years(2019, 2023), ["2023"], ["regimes.soft.cor.2027", "regimes.soft.cor.2028", "regimes.soft.cor.2029"],
             "мягкая посадка 2019 и 2023 (класс устава 2017–2019, 2023: 2017–2018 без данных по продуктам); МСФО — 2023"),
    "soft_LT": (_years(2019, 2020, 2021, 2023, 2024, 2025), ["2021", "2023", "2024", "2025"], ["regimes.soft.cor.LT"],
                "сквозь цикл без 2022 года: 2019–2025 без 2022 (2018 — без данных по продуктам); МСФО — 2021–2025 без 2022"),
    "R": (CP_R_QUARTERS, "R", ["regimes.norm.cor.2027", "regimes.norm.cor.2028", "regimes.norm.cor.2029", "regimes.norm.cor.LT"],
          "окно R 2К2024–2К2026; МСФО — окно R листа Б7 (2024, 2025, 1П2026 сумма к сумме)"),
    "downturn": (_years(2020, 2021), ["2021"],
                 ["regimes.downturn.cor.2027Q1", "regimes.downturn.cor.2027Q2", "regimes.downturn.cor.2027Q3",
                  "regimes.downturn.cor.2027Q4", "regimes.downturn.cor.2028", "regimes.downturn.cor.2029",
                  "regimes.downturn.cor.LT"], "спад 2020–2021; МСФО — 2021"),
    "crisis": (_years(2022), ["2022"], ["regimes.crisis.cor.2027Q1", "regimes.crisis.cor.2027Q2", "regimes.crisis.cor.2027Q3",
                                        "regimes.crisis.cor.2027Q4"], "кризисный год 2022 (2015 — без данных по продуктам)"),
    "post1": (_years(2023), ["2023"], ["regimes.crisis.cor.2028"], "год после шока 2023 (2016 — без данных по продуктам)"),
    "post2": (_years(2024), ["2024"], ["regimes.crisis.cor.2029"], "второй год после шока 2024"),
    "crisis_LT": (_years(2019, 2020, 2021, 2022, 2023, 2024, 2025), ["2021", "2022", "2023", "2024", "2025"],
                  ["regimes.crisis.cor.LT"], "сквозь цикл 2019–2025 (2015–2018 — без данных по продуктам); МСФО — 2021–2025"),
}
CP_M7_WINDOWS = {"R_2024_1H2026": "R 2024–1П2026", "2019_2025": "2019–2025", "2021_2025": "2021–2025", "1H2026": "1П2026"}
CP_M7_READINGS = ("R_2024_1H2026", "2019_2025", "1H2026")


def xlsx_sheet(path: Path, name: str) -> dict[tuple[int, int], object]:
    """Лист XLSX без сторонних пакетов: {(строка, столбец): сохранённое значение} (формулы не вычисляются)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rmap = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    for sh in wb.find("m:sheets", ns):
        if sh.get("name") != name:
            continue
        root = ET.fromstring(z.read("xl/" + rmap[sh.get("{%s}id" % ns["r"])].lstrip("/").replace("xl/", "")))
        cells = {}
        for cell in root.iter("{%s}c" % ns["m"]):
            v, t = cell.find("m:v", ns), cell.get("t")
            if v is None:
                is_ = cell.find("m:is", ns)
                if is_ is None:
                    continue
                val = "".join(x.text or "" for x in is_.iter("{%s}t" % ns["m"]))
            elif t == "s":
                val = ss[int(v.text)]
            elif t in ("str", "inlineStr", "e"):
                val = v.text
            elif t == "b":
                val = bool(int(v.text))
            else:
                try:
                    val = float(v.text)
                except (TypeError, ValueError):
                    val = v.text
            m = re.match(r"([A-Z]+)(\d+)$", cell.get("r"))
            col = 0
            for ch in m.group(1):
                col = col * 26 + ord(ch) - 64
            cells[(int(m.group(2)), col)] = val
        return cells
    raise BuildError(f"{path.name}: нет листа {name}")


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def build_credit_products(c: Ctx, bal: dict) -> dict:
    if c.a.period != CP_ANCHOR:
        return carried(c, "credit_products", "стоимость риска по книгам — узел калибровки книги на якоре " + CP_ANCHOR)
    path = c.need_file(c.root / DATABOOK)
    cor = xlsx_sheet(path, "COR")
    dbsha = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    dbname = path.name
    cols = {}
    for (r, col), v in cor.items():
        if r == 3 and isinstance(v, str) and len(v) == 6 and v[1] == "Q":
            cols[f"{v[2:]}Q{v[0]}"] = col
    periods = sorted(p for p in cols if CP["first"] <= p <= CP["last_databook"])
    anchor_books = {b: float(bal["books"][b]["v"]) for b in LOANS}
    w_tot = sum(anchor_books.values())
    w0 = {b: anchor_books[b] / w_tot for b in LOANS}

    def ref(row, p):
        return f"COR!{col_letters(cols[p])}{row}"

    gross, charge = {}, {}
    for p in periods:
        gross[p], charge[p] = {}, {}
        for b in LOANS:
            g = cor.get((CP["gross_row"][b], cols[p]))
            gross[p][b] = (float(g) / 1000, ref(CP["gross_row"][b], p))
            if p == CP["first"]:
                continue
            row = CP["llp_row"][b]
            v = cor.get((row, cols[p]))
            if b == "corp_loans" and not isinstance(v, float):
                row = CP["llp_corp_fallback"]
                v = cor.get((row, cols[p]))
            charge[p][b] = (-float(v) / 1000, ref(row, p))
    h1 = {b: 0.0 for b in LOANS}
    for r in read_csv(c.need_file(c.root / ECL_PRODUCTS)):
        if r["period"] == CP["h1_label"]:
            for b, prods in CP["ecl_prod"].items():
                if r["product"] in prods:
                    h1[b] += float(r["charge"]) / 1000
    A, L = c.a.period, CP["last_databook"]
    gross[A] = {b: (anchor_books[b], f"balance.books.{b} (якорь {c.a.ru})") for b in LOANS}
    charge[A] = {b: (h1[b] - charge[L][b][0],
                     f"МСФО 6М2026 (лист Б7 ecl_products.csv: {'+'.join(CP['ecl_prod'][b])}) {h1[b]:.3f} − датабук 1К2026 "
                     f"{charge[L][b][1]}") for b in LOANS}
    qs = periods[1:] + [A]
    allp = periods + [A]
    quarters = {}
    for i, p in enumerate(allp):
        nd = {"gross_end": {b: {"v": round(gross[p][b][0], 6), "src": f"{dbname}, {gross[p][b][1]}, sha256 {dbsha}"
                                if p != A else gross[p][b][1]} for b in LOANS}}
        if p != CP["first"]:
            prev = allp[i - 1]
            nd["charge"] = {b: {"v": round(charge[p][b][0], 6),
                                "src": (f"{dbname}, {charge[p][b][1]}, sha256 {dbsha}" if p != A else charge[p][b][1])}
                            for b in LOANS}
            avg = {b: (gross[prev][b][0] + gross[p][b][0]) / 2 for b in LOANS}
            cb = {b: charge[p][b][0] * 4 / avg[b] for b in LOANS}
            total = sum(charge[p][b][0] for b in LOANS) * 4 / sum(avg.values())
            on = sum(w0[b] * cb[b] for b in LOANS)
            nd["cor_books"] = {b: {"v": round(cb[b], 9)} for b in LOANS}
            nd["total"] = {"v": round(total, 9), "calc": "Σ резервов × 4 / Σ средних валовых пяти книг"}
            nd["on_anchor"] = {"v": round(on, 9), "calc": "Σ w0_b × CoR_b квартала (w0 — anchor_weights)"}
            nd["intensity"] = {"v": round(total / on, 9), "calc": "total / on_anchor"}
        quarters[p] = nd
    T = {p: quarters[p]["total"]["v"] for p in qs}
    Aq = {p: quarters[p]["on_anchor"]["v"] for p in qs}

    def dbk(qlist):
        return (sum(T[p] for p in qlist) / len(qlist)) / (sum(Aq[p] for p in qlist) / len(qlist))

    def r4mean(series, qlist):                     # среднее скользящих 4 кварталов (Р6-2; лист make_credit_products.py)
        vals = [series[p] for p in qlist]
        rolls = [sum(vals[i:i + 4]) / 4 for i in range(len(vals) - 3)]
        return sum(rolls) / len(rolls)

    ecl = {}
    for r in read_csv(c.need_file(c.root / ECL_REL)):
        cb = {b: float(r[CP["ecl_col"][b]]) for b in LOANS}
        tot = float(r["total"])
        on = sum(w0[b] * cb[b] for b in LOANS)
        ecl[r["period"]] = {"total": {"v": round(tot, 9)}, "cor_books": {b: {"v": round(cb[b], 9)} for b in LOANS},
                            "on_anchor": {"v": round(on, 9), "calc": "Σ w0_b × CoR_b периода"},
                            "intensity": {"v": round(tot / on, 9), "calc": "total / on_anchor"},
                            "src": "примечания МСФО о движении резервов по классам кредитов (лист Б7: начисление периода × 12 / мес. / "
                                   "средние валовые начала и конца периода) — stage1/round2/sheets/ecl_rel.csv"}
    E = {p: v["intensity"]["v"] for p, v in ecl.items()}
    b7 = json.loads(c.need_file(c.root / B7_SHEET).read_text(encoding="utf-8"))
    wins = {}
    for key, name in CP_M7_WINDOWS.items():
        w = b7["windows"][name]
        cb = {b: float(w[f"cor_{b}"]) for b in LOANS}
        tot = float(w["total"])
        on = sum(w0[b] * cb[b] for b in LOANS)
        wins[key] = {"total": {"v": round(tot, 9)}, "cor_books": {b: {"v": round(cb[b], 9)} for b in LOANS},
                     "rel": {b: {"v": round(cb[b] / tot, 9)} for b in LOANS},
                     "on_anchor": {"v": round(on, 9)}, "intensity": {"v": round(tot / on, 9)},
                     "src": f"лист Б7 (скептик sk-credit, коммит 0069c25, var/sk/out/b7_mult.json, окно «{name}»; копия — "
                            "stage1/round3/sheets/b7_mult.json): начисление / средние валовые сумма к сумме, примечания "
                            "МСФО FY2019–FY2025, 6М2026"}
    ecl_R = wins["R_2024_1H2026"]["intensity"]["v"]
    inten = {}
    for name, (dq, ey, keys, words_) in CP_WINDOWS.items():
        if dq == "norm_2026":
            h1t, h1a = (T["2026Q1"] + T["2026Q2"]) / 2, (Aq["2026Q1"] + Aq["2026Q2"]) / 2
            rt = r4mean(T, CP_R_QUARTERS)          # Р6-2 (решения ведущего № 6, на класс; ревизия класса 6 круга 8): окно R —
            ra = r4mean(Aq, CP_R_QUARTERS)         #   среднее скользящих 4 кварталов (было — 9 кварталов, 2К трижды)
            d = ((h1t + rt) / 2) / ((h1a + ra) / 2)
            e = 2.0 / (1.0 / E["1П2026"] + 1.0 / ecl_R)
            dcalc = ("((ср. 1К–2К2026 всего + ср. окна R всего) / 2) / ((ср. 1К–2К2026 на якоре + ср. окна R на якоре) / 2); "
                     "окно R — среднее скользящих 4 кварталов (Р6-2)")
            ecalc = "2 / (1 / I_МСФО(6М2026) + 1 / I_МСФО(окно R Б7)) — середина уровней на якоре"
        elif ey == "R":                            # Р6-2: равный вес календарных кварталов — среднее скользящих 4 кварталов
            d = r4mean(T, dq) / r4mean(Aq, dq)
            dcalc = (f"среднее скользящих 4 кварталов total / среднее скользящих 4 кварталов on_anchor, {dq[0]}…{dq[-1]} "
                     f"({len(dq) - 3} окон; Р6-2 — было среднее {len(dq)} кв., 2К трижды)")
            e = ecl_R
            ecalc = "windows_ifrs.R_2024_1H2026.intensity (лист Б7, сумма к сумме)"
        else:
            d = dbk(dq)
            dcalc = f"среднее кварталов total / среднее кварталов on_anchor, {dq[0]}…{dq[-1]} ({len(dq)} кв.)"
            if ey == "R":
                e = ecl_R
                ecalc = "windows_ifrs.R_2024_1H2026.intensity (лист Б7, сумма к сумме)"
            else:
                e = sum(E[y] for y in ey) / len(ey)
                ecalc = "среднее years_ifrs.<год>.intensity: " + ", ".join(ey)
        inten[name] = {"databook": {"v": round(d, 9), "calc": dcalc}, "ifrs": {"v": round(e, 9), "calc": ecalc},
                       "mid": {"v": round((d + e) / 2, 9), "calc": "середина двух источников (решения № 3, Р3)"},
                       "low": {"v": round(min(d, e), 9)}, "high": {"v": round(max(d, e), 9)},
                       "keys": keys, "window": words_}
    m7 = {}
    for b in LOANS:
        vals = [wins[k]["rel"][b]["v"] for k in CP_M7_READINGS]
        m7[b] = {"min": {"v": round(min(vals), 9)}, "max": {"v": round(max(vals), 9)},
                 "mid": {"v": round((min(vals) + max(vals)) / 2, 9)}, "readings": {k: wins[k]["rel"][b]["v"] for k in CP_M7_READINGS}}
    return {
        "basis": "МСФО группы и ДАТАБУК банка (определение банка: резервы / средние валовые кредиты)",
        "as_of": bal["as_of"], "unit": "доли годовых (CoR); млрд ₽ (резервы квартала, валовые остатки)",
        "note": "Стоимость риска по пяти кредитным книгам ядра (auto, mortgage, cash_loans, cards, corp_loans): датабук по кварталам "
                "4К2018–2К2026 (2К2026 — МСФО 1П2026 минус датабук 1К2026, остатки — книги якоря), МСФО по годам и окна прочтений "
                "множителей М7 (лист Б7). Интенсивность состава окна — CoR окна на своём составе к CoR книг окна на долях якоря "
                "(решения ведущего № 3, Р3); множители М7 — отношение CoR книги к общей CoR окна (Р11). Лист: "
                "stage1/facts/code/make_credit_products.py → sheets/cor_products_quarterly.csv.",
        "books": list(LOANS),
        "anchor_weights": {b: {"v": round(w0[b], 9), "calc": f"balance.books.{b} {anchor_books[b]:.3f} / Σ пяти кредитных книг {w_tot:.3f}"}
                           for b in LOANS},
        "quarters": quarters, "years_ifrs": ecl, "windows_ifrs": wins, "intensity": inten, "m7_readings": m7,
    }


def carried(c: Ctx, name: str, what: str) -> dict:
    """Узел калибровки книги на другом якоре: переносится из прежних фактов как есть (с пометкой в перечне --plan)."""
    src = (c.carry_from or FACTS) / f"{name}.json"
    c.notes.append(f"{name}.json — {what}: на якоре {c.a.period} перенесён из {src} как есть (пересчёт — листом круга "
                   "калибровки, не сборщиком)")
    if not src.is_file():
        c.miss(f"{src} (узел калибровки книги для переноса)")
        return {}
    return json.loads(src.read_text(encoding="utf-8"))


# ================================================================== perimeter.json
# Ряд поправок периметра окна R к периметру якоря (решения ведущего № 4, Р4-3; № 5, Р5-2). Числа — свидетельства
# скептика круга 4 (источники — в строках); лист круга — stage1/round5/perimeter_series.py (perimeter_series.csv):
# сборщик считает ряд тем же правилом и сверяет его с листом строка в строку. Узел калибровки книги (ядро не читает).
PERIM_ANCHOR = "2026Q2"
PERIM_WINDOW = ("2024Q2", "2026Q2")
PERIM = dict(
    kl_res={"2026Q2": (25.163, 12.178), "2026Q1": (21.575, 9.025), "2025Q2": (22.519, 7.159), "2025Q1": (23.568, 6.774)},
    src_kl="2026Q2_ifrs_fs.pdf с. 19 прим. 7 (выручка 25,163 / расходы 12,178 по договорам страхования); 2026Q1_ifrs_fs.pdf с. 20 "
           "(21,575 / 9,025); 2025Q2_ifrs_fs.pdf (22,519 / 7,159); 2026Q1_ifrs_fs.pdf, сравнительный 1К2025 (23,568 / 6,774)",
    t_2026q2=1.1, klms_days=42, q2_days=91, klms_margin=0.23,
    src_t="презентация 1П2026 с. 7 (расходы двух страховщиков 1,1 млрд ₽ во 2К2026, «вкл. OPEX КЛСЖ и КЛМС»); пост IR 178 (сделка "
          "КЛМС 19.05.2026; чистый доход 2025 — 1 млрд ₽); 2026Q2_ifrs_fs.pdf с. 9 (4 тыс. сотрудников в купленных страховщиках)",
    gold_other_nb={"2025Q1": 0.91, "2025Q2": 2.69, "2025Q3": 4.64, "2025Q4": -1.65, "2026Q1": 1.74, "2026Q2": 1.73},
    src_gold="FY2025_ifrs_fs.pdf с. 43 прим. 11 (рост прочей небанковской — покупка в 1К2025 золотодобытчика и рост трейдинга); "
             "прочая небанковская нетто: 2К24 −0,10; 3К24 −0,02; 4К24 +0,09; 1К25 +0,91; 2К25 +2,69; 3К25 +4,64; 4К25 −1,65; "
             "1К26 +1,74; 2К26 +1,73",
    hcf_items={"2024Q4": (8.160, 7.690), "2025Q1": (5.797, 5.326), "2025Q2": (7.389, 4.714)},
    src_hcf="пять статей «Прочих ОХР» (содержание ОС, проф. услуги, связь, транспорт, ТМЦ) против того же квартала следующего года: "
            "FY2024/FY2025 прим. «Прочие ОХР» (4К = год − 9М), 2025Q1_ifrs_fs.pdf прим. 11 («интеграция отделений ХКФ Банка»), "
            "2025Q2_ifrs_fs.pdf прим. 10, 2026Q1_ifrs_fs.pdf прим. 9, 2026Q2_ifrs_fs.pdf прим. 9; 2025Q1_ifrs_fs.pdf прим. сегментов — "
            "затраты интеграции «не выделяются отдельно»",
    hcf_high_total=4.1, hcf_high_quarters=("2024Q3", "2024Q4", "2025Q1", "2025Q2"), kl_assets=90.0,
)
PERIM_ENTITIES = {
    "klszh": {"title": "АО СК «Капитал Лайф Страхование Жизни» (КЛСЖ)", "control": "2026-03-31", "in_pnl_from": "2026Q2",
              "lines": ["ins", "opex", "fees", "cor"]},
    "klms": {"title": "АО «Капитал МС» (КЛМС, ОМС)", "control": "2026-05-19", "in_pnl_from": "2026Q2 (42 дня из 91)",
             "lines": ["ins", "opex", "fees", "cor"]},
    "gold": {"title": "золотодобывающая компания (куплена в 1К2025)", "control": "2025Q1", "in_pnl_from": "2025Q1",
             "lines": ["ins", "opex", "fees", "cor"]},
    "hcf": {"title": "ХКФ Банк (консолидация 31.03.2024)", "control": "2024-03-31", "in_pnl_from": "2024Q2",
            "lines": ["ins", "opex_window", "fees", "cor"]},
    "deal_2025q3": {"title": "сделка 3К2025 (лицо не раскрыто)", "control": "2025Q3", "status": "НП", "lines": ["ins", "opex", "fees", "cor"]},
    "deal_2025q4": {"title": "сделка 4К2025 (лицо не раскрыто)", "control": "2025Q4", "status": "НП", "lines": ["ins", "opex", "fees", "cor"]},
}
PERIM_EVENTS = {
    "2024Q2": {"entity": "hcf", "reason": "уточнение оценки и урегулирование ранее существовавших отношений ХКФ (0,731 + 4,653); ХКФ в периметре с 31.03.2024 — поправки нет"},
    "2024Q3": {"entity": "hcf", "reason": "уточнение выгодной покупки ХКФ (3,184) — ХКФ в периметре всё окно, поправки нет"},
    "2024Q4": {"entity": "hcf", "reason": "уточнение выгодной покупки ХКФ (−0,185); разовые расходы интеграции — строки opex_window"},
    "2025Q1": {"entity": "gold", "reason": "выгодная покупка золотодобытчика 5,664 (FY2025 прим. 10–11); 2К–4К2024 — поправка ряда"},
    "2025Q2": {"entity": "gold", "reason": "уточнение оценки (0,103) — лицо в периметре с 1К2025, поправки нет"},
    "2025Q3": {"entity": "deal_2025q3", "reason": "выгодная покупка 0,642 — лицо не раскрыто [НП], поправки нет"},
    "2025Q4": {"entity": "deal_2025q4", "reason": "выгодная покупка 3,806 — лицо не раскрыто [НП], поправки нет"},
    "2026Q1": {"entity": "klszh", "reason": "выгодная покупка «Капитал Лайф» ≈2,9 (контроль 31.03.2026) — ряд 2024К2–2026К1"},
    "2026Q2": {"entity": "klms", "reason": "выгодная покупка 0,962 во 2К2026 — по дате сделки КЛМС (19.05.2026) [В]; 2К2026 — достройка 49/91"},
}


def r2_half_up(x: float) -> float:
    """Два знака половиной вверх (как в свидетельствах скептика: 7,389 − 4,714 = 2,675 → 2,68)."""
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(repr(round(x, 9))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def perimeter_rows() -> tuple[list[dict], dict, dict]:
    P = PERIM
    r2 = r2_half_up
    res = {p: a - b for p, (a, b) in P["kl_res"].items()}
    organic = res["2026Q1"] / res["2025Q1"] - 1
    lo, hi = res["2026Q2"] - res["2026Q1"], res["2026Q2"] - (1 + organic) * res["2025Q2"]
    kl = {"low": r2(lo), "high": r2(hi), "centre": r2((lo + hi) / 2)}
    t2 = P["t_2026q2"]
    t_hi = t2 * P["q2_days"] / P["klms_days"]
    T = {"low": r2(t2), "high": r2(t_hi), "centre": r2((t2 + t_hi) / 2)}
    part = 1 - P["klms_days"] / P["q2_days"]
    o_klms = {k: (v - t2) / part for k, v in T.items()}
    r_klms = {k: (0.0 if o_klms[k] <= 1e-12 else o_klms[k] + P["klms_margin"]) for k in T}
    gold_hi = sum(P["gold_other_nb"].values()) / len(P["gold_other_nb"])
    gold = {"low": 0.0, "high": r2(gold_hi), "centre": r2(gold_hi / 2)}
    hcf_c = {p: r2(a - b) for p, (a, b) in P["hcf_items"].items()}
    win = q_range(*PERIM_WINDOW)
    pre_kl = q_range("2024Q2", "2026Q1")
    rows = []

    def row(line, entity, periods, centre, low, high, group, cls, src, calc, scope="all"):
        for p in periods:
            rows.append({"line": line, "entity": entity, "period": p, "scope": scope,
                         "centre": centre[p] if isinstance(centre, dict) else centre,
                         "low": low[p] if isinstance(low, dict) else low, "high": high[p] if isinstance(high, dict) else high,
                         "group": group, "cls": cls, "src": src, "calc": calc})
    row("ins", "klszh", pre_kl, kl["centre"], kl["low"], kl["high"], "kl_ins", "В/Р", P["src_kl"],
        f"низ — результат страховых услуг 2К2026 к 1К2026 при органике без изменения {kl['low']}; верх — органика г/г 2К2026 как в "
        f"1К2026 ({100 * organic:.1f} %): {kl['high']}; центр — середина")
    row("ins", "klszh", ["2026Q2"], 0.0, 0.0, 0.0, "kl_ins", "Ф", P["src_kl"], "2К2026 — КЛСЖ в ОПУ весь квартал (контроль с 31.03.2026)")
    row("ins", "klms", pre_kl, round(r_klms["centre"], 6), round(r_klms["low"], 6), round(r_klms["high"], 6), "T", "В", P["src_t"],
        f"выручка ОМС = расходы КЛМС + {P['klms_margin']}; расходы КЛМС = (T − {t2}) / (49/91): центр T {T['centre']} → "
        f"{o_klms['centre']:.4f}; на низу оси (T {T['low']}) лица нет")
    row("ins", "klms", ["2026Q2"], round(part * r_klms["centre"], 6), round(part * r_klms["low"], 6), round(part * r_klms["high"], 6),
        "T", "Р", P["src_t"], "достройка 2К2026 до полного квартала: 49/91 выручки КЛМС")
    row("opex", "klszh+klms", pre_kl, T["centre"], T["low"], T["high"], "T", "Ф/В", P["src_t"],
        f"T = o_КЛСЖ + o_КЛМС; связь {t2} = o_КЛСЖ + 42/91 o_КЛМС; низ — o_КЛМС = 0; верх — o_КЛСЖ = 0; центр — середина")
    row("opex", "klms", ["2026Q2"], round(part * o_klms["centre"], 6), round(part * o_klms["low"], 6), round(part * o_klms["high"], 6),
        "T", "Р", P["src_t"], "достройка 2К2026: 49/91 расходов КЛМС")
    row("opex_base:securities", "klszh", q_range("2024Q1", "2025Q4"), P["kl_assets"], P["kl_assets"], P["kl_assets"], None, "Ф/В",
        "пост IR 165 (активы 90 млрд ₽); баланс 31.03.2026 уже с КЛСЖ (пост 169)", "остаток книги securities на конец, млрд ₽")
    row("ins", "gold", ["2024Q2", "2024Q3", "2024Q4"], gold["centre"], gold["low"], gold["high"], "gold", "Р/В", P["src_gold"],
        f"верх — среднее 1К2025–2К2026 ({gold['high']}) против ≈0 в 2024; центр — середина; доля трейдинга не раскрыта")
    row("ins", "gold", ["2025Q1", "2025Q2"], 0.0, 0.0, 0.0, "gold", "Р", P["src_gold"],
        "1К2025 — куплен внутри квартала (дата покупки не раскрыта); 2К2025 — в периметре (выгодная покупка 0,103 — уточнение оценки)")
    hq = q_range("2024Q3", "2025Q2")
    hcf_hi = {p: (-round(P["hcf_high_total"] / len(P["hcf_high_quarters"]), 3) if p in P["hcf_high_quarters"] else 0.0) for p in hq}
    hcf_lo = {p: (-hcf_c[p] if p in hcf_c else 0.0) for p in hq}
    hcf_ce = {p: round((hcf_lo[p] + hcf_hi[p]) / 2, 6) for p in hq}
    row("opex_window", "hcf", hq, hcf_ce, hcf_lo, hcf_hi, "hcf", "Р/В", P["src_hcf"],
        "низ связки — пять статей ОХР против того же квартала следующего года (2К–3К2024 — 0; всего 3,62); верх — спад скользящих "
        "4 кварталов расходов к взвешенной базе 2,337 → 2,273 % (без страховщиков) ≈ 4,1 по 1,025 в 2024К3–2025К2; центр — середина "
        "двух оценок по кварталам (3,86); 0 — не свидетельство: банк называет рост расходов 2025 года интеграцией отделений ХКФ "
        "(решения ведущего № 5, Р5-2)", scope="window")
    row("opex_window", "hcf", ["2024Q2"], 0.0, 0.0, 0.0, "hcf", "Р", P["src_hcf"], "2К2024 — следа разовых в пяти статьях нет", scope="window")
    for line in ("ins", "fees", "cor"):
        row(line, "hcf", win, 0.0, 0.0, 0.0, None, "Р", "pnl_named_items (резерв первого дня ХКФ 5,362 — 1К2024, вне окна); ХКФ в "
            "периметре с 31.03.2024", "ХКФ в периметре всё окно: средняя база 2К2024 начинается с конца 1К2024, где ХКФ уже есть")
    for ent, periods in (("klszh", win), ("klms", win), ("gold", win)):
        for line in ("fees", "cor"):
            row(line, ent, periods, 0.0, 0.0, 0.0, None, "Р", "2026Q2_ifrs_fs.pdf прим. 5 (комиссии); cor_products_quarterly",
                "комиссионных строк и кредитов у лица нет — поправки нет")
    row("opex", "gold", win, 0.0, 0.0, 0.0, None, "НП", P["src_gold"], "расходы золотодобытчика не раскрыты — поправки нет (в FY2025 прим. 11 — "
        "нетто прочей небанковской, расходы внутри)")
    for p, v in (("2025Q3", 0.642), ("2025Q4", 3.806)):
        for line in ("ins", "opex", "fees", "cor"):
            row(line, f"deal_{p.lower()}", [p], 0.0, 0.0, 0.0, None, "НП",
                "2025Q3_ifrs_fs.pdf прим. 7; FY2025_ifrs_fs.pdf прим. 10; stage1/calib-pnl/sheets/bargain_series.csv («прочие»)",
                f"выгодная покупка {v} млрд ₽ в {p}: лицо и строки не раскрыты — не оценено (поправки нет)")
    hcf_low = r2(sum(hcf_c.values()))
    groups = {"kl_ins": kl, "T": T, "gold": gold,
              "hcf": {"low": hcf_low, "high": P["hcf_high_total"], "centre": r2((hcf_low + P["hcf_high_total"]) / 2)}}
    return rows, groups, {"o_klms": o_klms, "r_klms": r_klms, "organic_1q26": organic}


def build_perimeter(c: Ctx) -> dict:
    if c.a.period != PERIM_ANCHOR:
        return carried(c, "perimeter", "ряд поправок периметра окна R — узел калибровки книги на якоре " + PERIM_ANCHOR)
    rows, groups, aux = perimeter_rows()
    sheet = read_csv(c.need_file(c.root / PERIMETER_SHEET))
    same = len(sheet) == len(rows) and all(
        all(str(r[k] if r[k] is not None else "") == s[k] for k in ("line", "entity", "period", "scope", "group", "cls", "src", "calc"))
        and all(float(s[k]) == float(r[k]) for k in ("centre", "low", "high")) for r, s in zip(rows, sheet))
    c.check(f"ряд периметра = листу круга ({PERIMETER_SHEET}) строка в строку", same, f"строк {len(rows)} / {len(sheet)}")

    def nd(v, src, calc):
        return {"v": v, "src": src, "calc": calc}

    return {
        "basis": "IFRS",
        "as_of": c.a.date,
        "unit": "млрд ₽ за квартал (потоки строк ОПУ, в знаке уровня строки); млрд ₽ (остатки книг базы расходов)",
        "note": ("Ряд поправок периметра окна R к периметру якоря 30.06.2026 (решения ведущего № 4, Р4-3; итог скептика econ3-classes "
                 "круга 4; центр разовых ХКФ — решения ведущего № 5, Р5-2). Лист — svcb-850-handoff/stage1/round5/perimeter_series.py (perimeter_series.csv). Читает лист вывода "
                 "(evidence/path/derive_on_engine.py: perim) — одной функцией в центре и концах уровней строк, скользящих 4 кварталах, "
                 "свидетельстве «2П года якоря» и цели роста года якоря; ступень периметра в прогнозе (2027К1, 2027К2) — из того же "
                 "ряда. Ядро файл не читает. Концы — связки (groups): центр — середина концов нераскрытой разбивки."),
        "window": list(PERIM_WINDOW),
        "entities": PERIM_ENTITIES,
        "events": PERIM_EVENTS,
        "groups": {g: {k: nd(v, "лист perimeter_series.py", f"конец связки {g}") for k, v in d.items()} for g, d in groups.items()},
        "rows": [{"line": r["line"], "entity": r["entity"], "period": r["period"], "scope": r["scope"], "group": r["group"],
                  "cls": r["cls"], "centre": nd(r["centre"], r["src"], r["calc"]), "low": r["low"], "high": r["high"]} for r in rows],
        "aux": {"o_klms": {k: round(v, 6) for k, v in aux["o_klms"].items()}, "r_klms": {k: round(v, 6) for k, v in aux["r_klms"].items()},
                "organic_1q26": round(aux["organic_1q26"], 6)},
    }


# ================================================================== misc_window.json
# Ряд «прочего» книги (other.misc_net_real; решения ведущего № 7, Р7-1): лист круга 7 stage1/round7/r7_1_misc_slope.py
# пишет рядом r7_1_misc_slope.json — кварталы (sec, переоценка ССПУ по ОФЗ 1 и 3 лет, прочее без разовых, дефлятор) и
# регрессии наклона прохождения. Сборщик собирает узел из этого листа. Узел калибровки книги (ядро не читает).
# Решения ведущего № 8, Р8-2 (правило листа stage1/round8/r8_book.py, пункт misc; запись r8_apply.py): наклон прохождения
# slope — МНК строки ССПУ квартала (поле fvtpl, statements_long.csv) на fvr узла; регрессии круга 7 на всей строке
# «бумаги и валюта» — узел slope_sec_line (справочно).
MISC_ANCHOR = "2026Q2"
MISC_SAMPLE_WORDS = {"R": "окно R 2024К2–2026К2", "y2023_2026": "2023К1–2026К2"}
MISC_SAMPLES = {"R": ["2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"],
                "y2023_2026": [f"{y}Q{k}" for y in (2023, 2024, 2025) for k in (1, 2, 3, 4)] + ["2026Q1", "2026Q2"]}


def ols1(y: list[float], x: list[float]) -> tuple[float, float, float, float]:
    """y = a + b x (МНК с константой): a, b, с.о. b, R² — функция листа stage1/round8/r8_lib.py."""
    n = len(y)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((u - mx) * (v - my) for u, v in zip(x, y)) / sxx
    a = my - b * mx
    res = [v - a - b * u for u, v in zip(x, y)]
    s2 = sum(e * e for e in res) / (n - 2)
    sst = sum((v - my) ** 2 for v in y)
    return a, b, math.sqrt(s2 / sxx), 1 - sum(e * e for e in res) / sst


def build_misc_window(c: Ctx) -> dict:
    if c.a.period != MISC_ANCHOR:
        return carried(c, "misc_window", "ряд «прочего» и наклон прохождения переоценки — узел калибровки книги на якоре "
                       + MISC_ANCHOR)
    sheet = json.loads(c.need_file(c.root / MISC_SHEET).read_text(encoding="utf-8"))
    rows, reg = sheet["rows"], sheet["regressions"]
    fvtpl = {r["period"]: float(r["value"]) / 1000 for r in read_csv(c.need_file(c.root / MISC_STATEMENTS))
             if r["metric"] == "fvtpl" and r["period"] in rows}
    c.check("ряд «прочего»: строка ССПУ (statements_long.csv, metric fvtpl) — за каждый квартал ряда", set(fvtpl) == set(rows))
    src = ("лист svcb-850-handoff/stage1/round7/r7_1_misc_slope.py: панель кварталов research/facts/svcb-history/panel_quarterly.csv "
           "(sec, other — МСФО), облигации ССПУ — датабук (строка 312; 30.06.2026 — МСФО 6М2026 прим. 14, 361,4), кривая ОФЗ zcyc "
           "(primary/p3pnl_iss_zcyc_quarter_ends_2018-2026.csv), ИПЦ — primary/p3pnl_cbr_hd_base_infl_2013-09_2026-08_snap20261007.html")
    node_q = {}
    for q, r in rows.items():
        c.check(f"ряд «прочего» {q}: fvr — середина прочтений ОФЗ 1 и 3 лет", abs((r["fvr_1y"] + r["fvr_3y"]) / 2 - r["fvr_mid"]) < 1e-9)
        node_q[q] = {
            "sec": {"v": round(r["sec"], 6), "calc": "строка «бумаги и валюта» квартала (МСФО; лист pnl: sec), млрд ₽"},
            "fvr": {"v": round(r["fvr_mid"], 6), "calc": f"переоценка облигаций ССПУ в полную дюрацию: −1,6 × Δy × средние облигации ССПУ, "
                                                         f"середина прочтений ОФЗ 1 г. ({r['fvr_1y']:+.4f}) и 3 лет ({r['fvr_3y']:+.4f})"},
            "other_core": {"v": round(r["other_core"], 6), "calc": "прочее квартала без резерва по гарантиям (он — в комиссиях) и без разовых "
                                                                   "(выгодные приобретения, урегулирование ХКФ и субординированных, переоценка "
                                                                   "ассоциированных и зданий; числа листа pnl s5_other.py)"},
            "deflator": {"v": round(r["deflator"], 9), "calc": "индекс цен конца квартала якоря к концу квартала: Π (1 + ИПЦ г/г квартала)^(1/4)"},
            "sec_real": {"v": round(r["sec"] * r["deflator"], 6), "calc": "sec × дефлятор (цены якоря)"},
            "fvr_real": {"v": round(r["fvr_mid"] * r["deflator"], 6), "calc": "fvr × дефлятор (цены якоря)"},
            "other_real": {"v": round(r["other_core"] * r["deflator"], 6), "calc": "other_core × дефлятор (цены якоря)"},
            "fvtpl": {"v": round(fvtpl[q], 6), "calc": "строка ССПУ квартала — доходы за вычетом расходов по операциям с финансовыми "
                                                       "инструментами по справедливой стоимости через прибыль или убыток (МСФО; "
                                                       "research/facts/svcb-history/statements_long.csv, metric fvtpl), млрд ₽"},
        }
    pnl_sec = {q: r for q, r in rows.items()}
    c.check("ряд «прочего»: кварталы листа — 2023К1 … квартал якоря", list(pnl_sec)[-1] == c.a.period)
    fit = {k: ols1([round(fvtpl[q], 6) for q in MISC_SAMPLES[k]], [node_q[q]["fvr"]["v"] for q in MISC_SAMPLES[k]])
           for k in MISC_SAMPLE_WORDS}
    return {"basis": "IFRS", "as_of": c.a.date,
            "unit": "млрд ₽ за квартал (номинал и в ценах якоря 30.06.2026); наклон — доля единицы",
            "note": ("Ряд «прочего» книги (other.misc_net_real) — решения ведущего № 7, Р7-1: отчётная строка «бумаги и валюта» за вычетом "
                     "переоценки облигаций ССПУ с наклоном прохождения s (середина оценок узла slope) плюс прочее без разовых и резерва по "
                     "гарантиям, в ценах якоря. Читают правила класса 6 (data/assumptions/class_checks.yaml) формулой; ядро файл не читает. "
                     "Источник — " + src + " ПРАВКА 22.10.2026 (решения ведущего № 8, Р8-2): наклон прохождения s — регрессия "
                     "СТРОКИ ССПУ квартала (поле fvtpl) на FVR, а не всей строки «бумаги и валюта» (с валютой); прежние оценки — "
                     "узел slope_sec_line (справочно)."),
            "quarters": node_q,
            "slope": {k: {"v": round(fit[k][1], 6), "se": round(fit[k][2], 6),
                          "calc": f"МНК fvtpl_q = a + b × fvr_q с константой, {MISC_SAMPLE_WORDS[k]} (n {len(MISC_SAMPLES[k])}): b "
                                  f"{fit[k][1]:.4f}, с.о. {fit[k][2]:.4f}, t(b = 1) {(fit[k][1] - 1) / fit[k][2]:+.2f}, R² {fit[k][3]:.2f} — "
                                  "решения № 8, Р8-2: наклон прохождения на строке ССПУ (лист stage1/round8/r8_book.py, misc)"}
                      for k in MISC_SAMPLE_WORDS},
            "slope_sec_line": {k: {"v": round(reg[k]["fvr_mid"]["b"], 6), "se": round(reg[k]["fvr_mid"]["se"], 6),
                                   "calc": f"МНК sec_q = a + b × fvr_q с константой, {MISC_SAMPLE_WORDS[k]} (n {reg[k]['fvr_mid']['n']}): b "
                                           f"{reg[k]['fvr_mid']['b']:.4f}, с.о. {reg[k]['fvr_mid']['se']:.4f}, t(b = 1) "
                                           f"{reg[k]['fvr_mid']['t_vs_1']:+.2f}, R² {reg[k]['fvr_mid']['r2']:.2f} — СПРАВОЧНО (круг 7): наклон "
                                           "на всей строке «бумаги и валюта» с валютой; решения № 8, Р8-2: не та подстрока"}
                               for k in MISC_SAMPLE_WORDS}}


# ================================================================== сборка, сверки, запись

NO_FINAL_NEWLINE = ("nii_books",)   # файл потока nii записан без перевода строки в конце — байты сохраняются как есть


def body(name: str, data: dict) -> str:
    s = dumps(data)
    return s[:-1] if name in NO_FINAL_NEWLINE else s


def cross_checks(c: Ctx, f: dict[str, dict]) -> None:
    """Сверки между файлами: баланс по книгам, части, капитал, ЧПД книг против ОПУ."""
    b, nb, pnl = f["balance"], f["nii_books"], f["pnl_quarterly"]
    v = lambda x: x["v"] if isinstance(x, dict) else x   # noqa: E731
    sa = sum(v(b["books"][k]) for k in ASSET_BOOKS)
    sl = sum(v(b["books"][k]) for k in LIAB_BOOKS)
    ta = v(b["total_assets"])
    c.check("баланс якоря: Σ книг активов − резерв + прочие активы = активы",
            abs(sa - v(b["allowance_ac"]) + v(b["other_assets"]) - ta) < 1e-6, f"{sa:.3f} − {v(b['allowance_ac'])} + "
                                                                              f"{v(b['other_assets'])} против {ta}")
    E = b["equity"]
    c.check("баланс якоря: Σ книг пассивов + прочие обязательства + дивиденды к выплате + капитал = активы",
            abs(sl + v(b["other_liabilities"]) + v(b["dividends_payable"]) + v(E["total"]) - ta) < 1e-6)
    c.check("прочие активы = Σ частей; прочие обязательства = Σ частей; постоянные прочие активы = Σ частей",
            abs(v(b["other_assets"]) - sum(v(x) for x in b["other_assets_parts"].values())) < 1e-6
            and abs(v(b["other_liabilities"]) - sum(v(x) for x in b["other_liabilities_parts"].values())) < 1e-6
            and abs(v(b["other_assets_fixed"]) - sum(v(x) for x in b["other_assets_fixed_parts"].values())) < 1e-6)
    c.check("капитал: строки капитала = капитал без бессрочных; bv_common + at1 + nci = капитал итого",
            abs(sum(v(E[k]) for k, _ in EQUITY_LINES) - v(E["bv_common"])) < 1e-6
            and abs(v(E["bv_common"]) + v(E["at1"]) + v(E["nci"]) - v(E["total"])) < 1e-6)
    c.check("книги: бумаги = Σ узлов securities; ликвидность = Σ узлов liquidity; опт = Σ узлов wholesale; средства = ОФП",
            abs(v(b["books"]["securities"]) - sum(v(b["securities"][k]) for k in ("fvoci_debt", "fvoci_repo", "ac", "ac_repo",
                                                                                     "fvtpl_bonds"))) < 1e-6
            and abs(v(b["books"]["liquidity"]) - sum(v(b["liquidity"][k]) for k in ("cash", "cbr", "due_from_banks"))) < 1e-6
            and abs(v(b["books"]["wholesale"]) - sum(v(x) for x in b["wholesale"].values())) < 1e-6
            and abs(v(b["funds"]["total"]) - sum(v(b["books"][k]) for k in FUNDS_BOOKS)) < 1e-6)
    c.check("nii_books: остатки книг на якоре = balance.books; на начало квартала = истории баланса",
            all(abs(nb["books"][k]["balance_close"]["v"] - v(b["books"][k])) < 1e-9 for k in BOOKS)
            and all(abs(nb["books"][k]["balance_open"]["v"] - b["history"][c.a.prev]["books"][k]["v"]) < 1e-9 for k in BOOKS
                    if "books" in b["history"].get(c.a.prev, {})))
    row = pnl["quarters"][c.a.period]
    c.check("ЧПД движка квартала якоря: nii_books.nii_q = pnl_quarterly.nii; ЧПД формы = nii_form",
            abs(nb["nii_q"]["v"] - row["nii"]["v"]) < 1e-6 and abs(nb["nii_form_q"]["v"] - row["nii_form"]["v"]) < 1e-6)
    c.check("капитал: фонд ССПСД = balance.equity.fvoci_reserve; AT1 = balance.equity.at1",
            f["capital"]["fvoci_reserve"]["v"] == v(E["fvoci_reserve"]) and f["capital"]["at1"]["amount"]["v"] == v(E["at1"]))


FILE_BUILDERS = (("balance", lambda c, f: build_balance(c)), ("nii_books", lambda c, f: build_nii_books(c)),
                 ("pnl_quarterly", lambda c, f: build_pnl(c)), ("capital", lambda c, f: build_capital(c)),
                 ("shares", lambda c, f: build_shares(c)), ("dividends", lambda c, f: build_dividends(c)),
                 ("bridge_mgmt_ifrs", lambda c, f: build_bridges(c)), ("bridge_ras_ifrs", lambda c, f: build_ras(c)),
                 ("mgmt_quarterly", lambda c, f: build_mgmt(c)), ("guidance", lambda c, f: build_guidance(c)),
                 ("calendar", lambda c, f: build_calendar(c)), ("peers", lambda c, f: build_peers(c)),
                 ("credit_products", lambda c, f: build_credit_products(c, f["balance"])),
                 ("perimeter", lambda c, f: build_perimeter(c)), ("misc_window", lambda c, f: build_misc_window(c)),
                 ("anchor", lambda c, f: build_anchor(c)))


def build_ctx(root: Path, anchor: Anchor, *, plan: bool = False, carry_from: Path | None = None) -> tuple[dict[str, dict], Ctx]:
    c = Ctx(root, anchor, plan=plan)
    c.carry_from = carry_from
    files: dict[str, dict] = {}
    for name, fn in FILE_BUILDERS:
        try:
            files[name] = fn(c, files)
        except (BuildError, KeyError, ValueError, TypeError, ZeroDivisionError, IndexError) as e:
            if not plan:
                raise
            c.missing.append(f"{name}.json: сборка прервалась на недостающем ({type(e).__name__}: {e})")
            files[name] = {}
    if not plan:
        cross_checks(c, files)
    return {k: files[k] for k in BUILT}, c


def build(root: Path, anchor: Anchor) -> tuple[dict[str, dict], list]:
    files, c = build_ctx(root, anchor)
    return files, c.checks


def write(files: dict[str, dict], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        with open(target / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(body(name, data))


# ------------------------------------------------------------------ файл отчёта квартала (вход перезаякоривания)
#
# Формат — тот, что читает ops/tools/reanchor.py (`quarter-report/1`, docs/REANCHOR.md §2). Отличия Совкомбанка: 13 книг
# (с книгой обязательств страховщиков: её «проценты» — финансовые расходы страхования); годовой календарь дивиденда
# (`balance.dividends_payable_year` при остатке к выплате > 0); бессрочные в капитале МСФО (`balance.at1`); нормативы —
# банк соло (слоты n20_0 ← Н1.0, n1_1_bank ← Н1.2) по формам 0409135/0409123, к дню отчёта обычно уже вышедшим.

REPORT_PNL = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni", "ni_shareholders",
              "misc_net")
REPORT_TOP = ("schema", "period", "as_of", "source", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt", "shares")
CURVE_NODES = ("1", "3", "5", "10")
# Поле отчёта ← узел фактов ← строки листов этапа 1 (что положить в листы к дню отчёта; печатает --plan).
REPORT_SOURCES = (
    ("balance.books.<книга>", "balance.books", "books_balances.csv: строки книг на дату якоря (примечания 12–19 и ОФП; формы — "
                                               "перепись скана)"),
    ("balance.loans_fvtpl", "balance.loans_fvtpl", "books_balances.csv: loans_fvtpl"),
    ("balance.fvoci; fvtpl_bonds", "balance.securities.*", "books_balances.csv: строки бумаг; balance_anchor.csv: bs_fvoci_repo"),
    ("balance.allowance", "balance.allowance_ac", "SHEET_GAPS allowance_ac (резерв по кредитам, прим. 15) — положить строкой листа"),
    ("balance.other_assets; other_assets_fixed", "balance.other_assets*", "balance_anchor.csv: bs_* строки ОФП (скан), oa_* (прим. 21)"),
    ("balance.other_liabilities; dividends_payable", "balance.other_liabilities, dividends_payable",
     "balance_anchor.csv: bs_liab, ol_* (прим. 21)"),
    ("balance.dividends_payable_year; dividends_payable_declared", "balance.*", "dividends.csv: решение, не выплаченное на якоре"),
    ("balance.bv_common; at1; nci; fvoci_reserve", "balance.equity.*", "balance_anchor.csv: bs_eq_ex_perp, bs_perp, bs_nci, "
                                                                       "bs_fvoci_res; eq_*_note22"),
    ("interest.<книга>", "nii_books.books.<книга>.interest_q", "calib-nii/sheets/interest_lines_quarterly.csv (прим. 4); "
                                                               "ins_finance_quarterly.csv (книга insurance_liab)"),
    ("dia", "nii_books.dia_q", "interest_lines_quarterly.csv: dia"),
    ("pnl.*", "pnl_quarterly.quarters.<квартал>", "pnl_cumulative.csv (перепись ОПУ: 3M/6M/9M/FY), pnl_quarterly_lines.csv, "
                                                   "pnl_composition.csv, pnl_named_items.csv, equity_flows.csv"),
    ("capital.n20_0; n1_1_bank; basel_*; bank_base_capital; t2", "capital.*", "capital_bank.csv: формы 0409135/0409123 на первое "
                                                                             "число после квартала"),
    ("market.ofz_curve; key_avg", "capital.ofz_curve_anchor; nii_books.key_avg_anchor_q", "ofz_curve.csv; research "
                                                                                          "key_rate_quarterly.csv"),
    ("mgmt.nim; cor; cir", "mgmt_quarterly.quarters.<квартал>", "mgmt_kpi.csv: nim/cor/cir (_exact — расчёт по определению банка)"),
    ("shares.*", "shares.*", "shares.csv: issued_total, outstanding_total, treasury_*, dividend_eligible"),
    ("dividend_decisions", "dividends.history", "dividends.csv: решения квартала"),
)


def report_from_facts(files: dict[str, dict], *, source: str) -> dict:
    """Файл отчёта квартала из фактов якоря: остатки и проценты книг, строки ОПУ движка, капитал, рынок, упр. метрики."""
    bal, nb, cap, sh = files["balance"], files["nii_books"], files["capital"], files["shares"]
    period = str(files["anchor"]["period"])

    def need(n, where: str) -> float:
        if not isinstance(n, dict) or n.get("v") is None:
            raise BuildError(f"отчёт квартала из фактов: нет числа {where}")
        return float(n["v"])

    row = files["pnl_quarterly"]["quarters"][period]
    pnl: dict = {k: need(row[k], f"pnl_quarterly.{period}.{k}") for k in REPORT_PNL}
    if row.get("oci_fvoci", {}).get("v") is not None:
        pnl["oci_fvoci"] = float(row["oci_fvoci"]["v"])
    if row["ni_shareholders"].get("estimated"):
        pnl["estimated"] = True
    mrow = files["mgmt_quarterly"]["quarters"][period]
    mgmt = {}
    for x in ("nim", "cor", "cir"):
        n = mrow.get(x + "_exact") if (mrow.get(x + "_exact") or {}).get("v") is not None else mrow.get(x)
        if x != "cir" or (n or {}).get("v") is not None:
            mgmt[x] = need(n, f"mgmt_quarterly.{period}.{x}")
    capital = {"n20_0": need(cap["n20_0"]["value"], "capital.n20_0.value"),
               "n20_pre_dividend": bool(cap["n20_0"]["pre_dividend"]),
               "n1_1_bank": need(cap["n1_1_bank"]["value"], "capital.n1_1_bank.value"),
               "basel_cet1": need(cap["basel"]["cet1"], "capital.basel.cet1"),
               "basel_rwa": need(cap["basel"]["rwa"], "capital.basel.rwa"),
               "bank_base_capital": need(cap["bank_base_capital"], "capital.bank_base_capital"),
               "t2": need(cap["t2_recognized"], "capital.t2_recognized"),
               "estimated": bool(cap["n20_0"].get("estimated"))}
    if capital["estimated"]:
        capital["estimate"] = {slot: {k: (v["v"] if isinstance(v, dict) else v) for k, v in cap[slot]["estimate"].items()}
                               for slot in ("n20_0", "n1_1_bank")}
    balance = {
        "books": {b: need(bal["books"][b], f"balance.books.{b}") for b in BOOKS},
        "loans_fvtpl": need(bal["loans_fvtpl"], "balance.loans_fvtpl"),
        "fvoci": r6(need(bal["securities"]["fvoci_debt"], "balance.securities.fvoci_debt")
                    + need(bal["securities"]["fvoci_repo"], "balance.securities.fvoci_repo")),
        "fvtpl_bonds": need(bal["securities"]["fvtpl_bonds"], "balance.securities.fvtpl_bonds"),
        "allowance": need(bal["allowance_ac"], "balance.allowance_ac"),
        "other_assets": need(bal["other_assets"], "balance.other_assets"),
        "other_assets_fixed": need(bal["other_assets_fixed"], "balance.other_assets_fixed"),
        "other_liabilities": need(bal["other_liabilities"], "balance.other_liabilities"),
        "dividends_payable": need(bal["dividends_payable"], "balance.dividends_payable"),
        "dividends_payable_declared": [{"period": x["period"], "amount": need(x["amount"], "balance.dividends_payable_declared")}
                                       for x in bal.get("dividends_payable_declared") or []],
        "bv_common": need(bal["equity"]["bv_common"], "balance.equity.bv_common"),
        "fvoci_reserve": need(cap["fvoci_reserve"], "capital.fvoci_reserve"),
        "at1": need(bal["equity"]["at1"], "balance.equity.at1"), "nci": need(bal["equity"]["nci"], "balance.equity.nci"),
    }
    if bal.get("dividends_payable_year") is not None:
        balance["dividends_payable_year"] = int(bal["dividends_payable_year"])
    report = {
        "schema": REPORT_SCHEMA, "period": period, "as_of": str(files["anchor"]["as_of"]), "source": source,
        "balance": balance,
        "interest": {b: need(nb["books"][b]["interest_q"], f"nii_books.books.{b}.interest_q") for b in BOOKS},
        "dia": need(nb["dia_q"], "nii_books.dia_q"),
        "pnl": pnl,
        "capital": capital,
        "market": {"ofz_curve": {t: need(cap["ofz_curve_anchor"][t], f"capital.ofz_curve_anchor.{t}") for t in CURVE_NODES},
                   "key_avg": need(nb["key_avg_anchor_q"], "nii_books.key_avg_anchor_q")},
        "mgmt": mgmt,
        "shares": {k: need(sh[k], f"shares.{k}") for k in ("issued_total", "outstanding_total", "economic_treasury",
                                                           "issued_ordinary", "outstanding_ordinary")},
        "dividend_decisions": report_decisions(files),
    }
    check_report(report)
    return report


def report_decisions(files: dict[str, dict]) -> list[dict]:
    """Решения собраний о дивиденде, принятые в квартале якоря (позже конца прошлого квартала и не позже якоря): период
    прибыли (у годового дивиденда — четвёртый квартал года), DPS, день решения, даты реестра и выплаты, сумма решения."""
    period, as_of = str(files["anchor"]["period"]), str(files["anchor"]["as_of"])
    opened = q_end(q_prev(period)).isoformat()
    out = []
    for h in files["dividends"].get("history") or []:
        if not opened < str(h.get("decided_date") or "") <= as_of:
            continue
        row = {"period": h["period"], "dps": float(h["dps"]["v"]), "decided_date": h["decided_date"]}
        for key in ("record_date", "pay_date"):
            if h.get(key):
                row[key] = h[key]
        if (h.get("pool_declared") or {}).get("v") is not None:
            row["pool_declared"] = float(h["pool_declared"]["v"])
        out.append(row)
    return out


def check_report(report: dict) -> None:
    """Состав и тождества файла отчёта: недостающий ключ или несходящийся баланс — отказ."""
    problems = [f"нет {k}" for k in REPORT_TOP if k not in report]
    if not problems:
        b, p = report["balance"], report["pnl"]
        problems += [f"нет balance.books.{x}" for x in BOOKS if x not in b["books"]]
        problems += [f"нет interest.{x}" for x in BOOKS if x not in report["interest"]]
        problems += [f"нет pnl.{x}" for x in REPORT_PNL if x not in p]
        if not problems:
            assets = sum(b["books"][x] for x in ASSET_BOOKS) - b["allowance"] + b["other_assets"]
            claims = (sum(b["books"][x] for x in LIAB_BOOKS) + b["other_liabilities"] + b["dividends_payable"]
                      + b["bv_common"] + b["at1"] + b["nci"])
            if abs(assets - claims) > 0.5:
                problems.append(f"баланс не сходится: активы {assets:.3f}, обязательства и капитал {claims:.3f}")
            lines = sum(p[k] for k in PNL_SUM)
            if abs(lines - p["pbt"]) > 1e-4 or abs(p["pbt"] + p["tax"] - p["ni"]) > 1e-4:
                problems.append("ОПУ не сходится: сумма строк против pbt или pbt + tax против ni")
            if sum(x["amount"] for x in b["dividends_payable_declared"]) > b["dividends_payable"] + 1e-9:
                problems.append("объявленные дивиденды больше остатка к выплате")
            if b["dividends_payable"] > 0 and b.get("dividends_payable_year") is None:
                problems.append("дивиденды к выплате > 0 без balance.dividends_payable_year (годовой календарь)")
        if not isinstance(report["capital"].get("n20_pre_dividend"), bool):
            problems.append("capital.n20_pre_dividend — true или false")
    if problems:
        raise BuildError("отчёт квартала: " + "; ".join(problems))


def write_report(files: dict[str, dict], path: Path, *, source: str) -> None:
    report = report_from_facts(files, source=source)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(report))
    print(f"записан отчёт квартала {report['period']} ({REPORT_SCHEMA}): {path}")


# ------------------------------------------------------------------ перечень квартала (--plan)

QUARTER_STEPS = (
    "Первичка в primary/ (+ строка MANIFEST на файл: имя, адрес, sha256, «что это»): отчёт МСФО за период "
    "({doc}; сайт prod-api.sovcombank.ru, дверь документов), презентация результатов, формы банка 0409135 и 0409123 на "
    "{form} (рег. № 963, primary/cbr-svcb-capital/); текстовый слой отчёта — research/samples/svcb-business_txt/{stem}.txt.",
    "Перепись форм-сканов: ОПУ (с. 5: колонки «за три месяца» отчётного и сравнительного квартала, нарастающий итог) и ОФП "
    "(с. 6: {date} и сравнительная дата) — блоками «@doc …» (формат research/code/svcb-history/manual/README.md), двумя "
    "независимыми переписями; `build_facts.py --forms A.txt B.txt --anchor {period}` — тождества сумм каждой переписи и "
    "сверка двух переписей число с числом; затем sh_build_quarterly.py (manual_long.csv, svcb_quarterly.csv).",
    "Листы потока facts этапа 1 (stage1/facts/code/run_all.sh — скрипты этапа 1 стоят на 2026Q2: квартал якоря в них "
    "поменять) — строки, которые сборщик читает на якоре {period}, перечислены ниже как недостающие.",
    "Лист процентов calib-nii (interest_lines_quarterly.csv — строка {period}), ins_finance_quarterly.csv ({period}), ряд "
    "ключевой ставки research/facts/svcb-history/key_rate_quarterly.csv ({period}).",
    "Числа якоря, которых нет в листах (SHEET_GAPS, ALLOWANCE_BOOKS, GUARANTEES сборщика): строками balance_anchor.csv с "
    "теми же именами на {date} (сборщик берёт их оттуда первыми) или таблицами сборщика на {period}.",
    "Сборка: `build_facts.py --anchor {period} --out var/reanchor/facts-{period} --report var/reanchor/report-{period}.json` "
    "(сверки обязаны сойтись), затем `reanchor.py --facts var/reanchor/report-{period}.json --compare-facts "
    "var/reanchor/facts-{period}` (docs/REANCHOR.md §1.4).",
)


def plan(root: Path, anchor: Anchor, carry_from: Path | None = None) -> tuple[list[str], list[str]]:
    """Перечень недостающего для якоря: строки листов (сборка идёт до конца на «пустых» числах), несошедшиеся сверки
    на тех строках, что есть, и пометки."""
    files, c = build_ctx(root, anchor, plan=True, carry_from=carry_from)
    failed = [f"сверка не сошлась: {n}" + (f" ({d})" if d else "") for n, ok, d in c.checks if not ok]
    return (c.missing or failed), c.notes


def print_plan(root: Path, anchor: Anchor, carry_from: Path | None = None) -> int:
    missing, notes = plan(root, anchor, carry_from)
    a = anchor
    stem = a.report_doc[:-4]
    print(f"Перечень квартала: якорь {a.period} ({a.ru}), отчёт {a.report_doc}")
    print("\nШаги:")
    for i, s in enumerate(QUARTER_STEPS, 1):
        print(f"  {i}. " + s.format(doc=a.report_doc, form=d_ru(a.form_date), stem=stem, date=a.ru, period=a.period))
    print("\nПоля отчёта квартала (quarter-report/1 — вход reanchor.py) и их листы:")
    for field, nd, sheet in REPORT_SOURCES:
        print(f"  {field:<58} ← {nd:<46} ← {sheet}")
    print(f"\nНедостающее в листах на якоре {a.period}: {len(missing)}")
    for m in missing:
        print(f"  – {m}")
    if notes:
        print("\nПометки (не останавливают сборку):")
        for n in notes:
            print(f"  · {n}")
    print("\nИТОГ: " + ("листы полны — можно собирать" if not missing else "листы не полны — сборка якоря откажет"))
    return 0 if not missing else 1


# ------------------------------------------------------------------ перепись форм-сканов: тождества и двойная проверка
#
# Формат — research/code/svcb-history/manual/README.md: блок «@doc <файл> p<страница> <PL|BS> <колонка> <период> <основа>»,
# затем строки «ключ значение» (млн ₽; расходы — со знаком минус; «–» = 0 — строку не писать). Тождества — те же, что у
# сборщика переписи соседа svcb-history (sh_build_quarterly.py): 651 тождество на переписи 2018–2026.

PL_OTHER_BANK = ("fvtpl", "derec_ac", "derec_fvoci", "fx", "oth_imp", "loss_offmkt", "oth_opinc", "jv_share", "assoc_share",
                 "afs_gain")
BS_ASSETS = ("cash", "oblres", "due_banks", "due_banks_repo", "fvtpl_own", "fvtpl_repo", "fvoci_own", "fvoci_repo", "loans_own",
             "loans_repo", "hedge_fv", "assoc", "jv", "hfs", "invprop", "ppe", "rou", "goodwill", "curtax_a", "dta", "oth_a")
BS_LIAB = ("cbr", "due_to_banks", "cust", "debt_sec", "oth_borr", "dtl", "curtax_l", "subdebt", "nci_liab", "oth_l")
BS_EQ = ("sh_cap", "treasury", "oth_contrib", "fvoci_res", "fx_res", "perp", "reval_res", "re")
FORMS_TOL = 0.5   # млн ₽: тождество суммы строк (округление отчёта)
MANUAL_DIR = "research/code/svcb-history/manual"


def parse_forms(text: str, name: str = "перепись") -> list[dict]:
    blocks, cur = [], None
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@doc"):
            parts = line.split()
            if len(parts) != 7:
                raise BuildError(f"{name}:{ln}: заголовок блока — «@doc файл pN PL|BS колонка период основа»")
            _, doc, page, typ, col, label, basis = parts
            if typ not in ("PL", "BS"):
                raise BuildError(f"{name}:{ln}: тип формы {typ!r} — PL или BS")
            cur = dict(doc=doc, page=page, typ=typ, col=col, label=label, basis=basis, data={}, line=ln)
            blocks.append(cur)
            continue
        if cur is None:
            raise BuildError(f"{name}:{ln}: строка до первого заголовка @doc")
        try:
            k, v = line.split()
            val = float(v)
        except ValueError as e:
            raise BuildError(f"{name}:{ln}: строка «ключ значение» — {line!r}") from e
        if k in cur["data"]:
            raise BuildError(f"{name}:{ln}: ключ {k} второй раз в блоке")
        cur["data"][k] = val
    return blocks


def form_identities(b: dict) -> list[tuple[str, float, float]]:
    """(тождество, сумма частей, итог формы) — для всех тождеств, итоги которых в блоке есть."""
    d = b["data"]
    g = lambda k: d.get(k, 0.0)   # noqa: E731
    out = []
    if b["typ"] == "PL":
        if "nii" in d and ("ii_eir" in d or "ii_tot" in d) and "ie" in d:
            out.append(("nii", g("ii_eir") + g("ii_oth") + g("ii_tot") + g("ie") + g("dep_ins"), g("nii")))
        if "nii_after" in d and "nii" in d:
            out.append(("nii_after", g("nii") + g("ecl") + g("ecl_ma_day1"), g("nii_after")))
        if "nfc" in d and "fee_inc" in d:
            out.append(("nfc", g("fee_inc") + g("fee_exp"), g("nfc")))
        if "op_inc" in d and "nii_after" in d and "nfc" in d:
            out.append(("op_inc", g("nii_after") + g("nfc") + sum(g(k) for k in PL_OTHER_BANK), g("op_inc")))
        if "nb_net" in d and "nb_rev" in d:
            out.append(("nb_net", g("nb_rev") + g("nb_cost") + g("ins_fin"), g("nb_net")))
        if "pbt" in d and "op_inc" in d:
            out.append(("pbt", g("op_inc") + g("nb_net") + g("reval") + g("staff") + g("ga"), g("pbt")))
        if "np" in d and "pbt" in d and "tax" in d:
            out.append(("np", g("pbt") + g("tax"), g("np")))
        if "np_sh" in d and "np_nci" in d:
            out.append(("np_split", g("np_sh") + g("np_nci"), g("np")))
        if "ci" in d and "np" in d and "oci" in d:
            out.append(("ci", g("np") + g("oci"), g("ci")))
    else:
        if "assets" in d and "cash" in d:
            out.append(("assets", sum(g(k) for k in BS_ASSETS), g("assets")))
        if "liab" in d and "cust" in d:
            out.append(("liab", sum(g(k) for k in BS_LIAB), g("liab")))
        if "eq_sh" in d and "re" in d:
            out.append(("eq_sh", sum(g(k) for k in BS_EQ), g("eq_sh")))
        if "equity" in d and "eq_sh" in d:
            out.append(("equity", g("eq_sh") + g("nci"), g("equity")))
        if "assets" in d and "liab" in d and "equity" in d:
            out.append(("balance", g("liab") + g("equity"), g("assets")))
    return out


def expected_form_blocks(anchor: Anchor) -> list[tuple[str, str, str]]:
    """Блоки переписи, которых ждёт отчёт квартала: (тип, период, основа). Годовой отчёт — без колонки «за три месяца»."""
    a = anchor
    if a.k == 4:
        out = [("PL", f"{a.y}FY", "12M"), ("PL", f"{a.y - 1}FY", "12M")]
    else:
        out = [("PL", a.period, "3M"), ("PL", f"{a.y - 1}Q{a.k}", "3M")]
        if a.k > 1:
            lab, basis = {2: ("H1", "6M"), 3: ("M9", "9M")}[a.k]
            out += [("PL", f"{a.y}{lab}", basis), ("PL", f"{a.y - 1}{lab}", basis)]
    return out + [("BS", a.date, "pt"), ("BS", a.prev_year_end if a.k > 1 else q_end(f"{a.y - 1}Q4").isoformat(), "pt")]


def form_template(template_dir: Path | None, typ: str, basis: str) -> set[str]:
    """Строки, которые переписаны в том же блоке (тип и основа) последнего квартального отчёта переписи соседа."""
    if template_dir is None or not template_dir.is_dir():
        return set()
    best: tuple[str, set[str]] | None = None
    for f in sorted(template_dir.glob("m20*Q*.txt")):
        for b in parse_forms(f.read_text(encoding="utf-8"), f.name):
            if b["typ"] == typ and b["basis"] == basis and b["col"] == "c1" and (best is None or b["doc"] >= best[0]):
                best = (b["doc"], set(b["data"]))
    return best[1] if best else set()


def check_forms(paths: list[Path], anchor: Anchor | None, template_dir: Path | None) -> int:
    """Тождества переписи (каждой), сверка двух переписей число с числом, полнота блоков и строк квартала якоря."""
    fails = 0
    sets = []
    for p in paths:
        blocks = parse_forms(p.read_text(encoding="utf-8"), p.name)
        sets.append(blocks)
        n_id, bad = 0, 0
        for b in blocks:
            for name, parts, total in form_identities(b):
                n_id += 1
                diff = parts - total
                if abs(diff) > FORMS_TOL:
                    bad += 1
                    print(f"  СБОЙ {p.name}: {b['doc']} {b['page']} {b['typ']} {b['col']} {b['label']}: тождество {name}: "
                          f"части {int_ru(parts)}, итог {int_ru(total)}, разница {'+' if diff > 0 else '−'}{int_ru(abs(diff))}")
        fails += bad
        print(f"{p.name}: блоков {len(blocks)}, тождеств {n_id}, не сошлось {bad}")
    if len(sets) == 2:
        key = lambda b: (b["doc"], b["page"], b["typ"], b["col"], b["label"], b["basis"])   # noqa: E731
        a_, b_ = {key(x): x for x in sets[0]}, {key(x): x for x in sets[1]}
        diff_n = 0
        for k in sorted(set(a_) | set(b_)):
            if k not in a_ or k not in b_:
                diff_n += 1
                print(f"  СБОЙ блок {' '.join(k)} — только в {paths[0].name if k in a_ else paths[1].name}")
                continue
            da, db = a_[k]["data"], b_[k]["data"]
            for m in sorted(set(da) | set(db)):
                if da.get(m) != db.get(m):
                    diff_n += 1
                    print(f"  СБОЙ {' '.join(k)}: {m} — {da.get(m)} против {db.get(m)}")
        fails += diff_n
        print(f"сверка двух переписей: блоков {len(set(a_) | set(b_))}, расхождений {diff_n}")
    if anchor is not None:
        blocks = sets[0]
        lack_n = 0
        for typ, label, basis in expected_form_blocks(anchor):
            got = [b for b in blocks if b["typ"] == typ and b["label"] == label and b["doc"] == anchor.report_doc]
            if not got:
                lack_n += 1
                print(f"  НЕТ блока «@doc {anchor.report_doc} p? {typ} c? {label} {basis}»")
                continue
            lack = sorted(form_template(template_dir, typ, basis) - set(got[0]["data"]))
            if lack:
                lack_n += 1
                print(f"  НЕТ строк в блоке {typ} {label}: {', '.join(lack)} (их несёт тот же блок прошлого отчёта)")
        fails += lack_n
        print(f"полнота переписи квартала {anchor.period}: блоков ждём {len(expected_form_blocks(anchor))}, недостаёт {lack_n}")
    print("ИТОГ: " + ("перепись сходится" if not fails else f"не сошлось {fails}"))
    return 0 if not fails else 1


# ------------------------------------------------------------------ режим --expected: отчёт квартала → факты
#
# Факты следующего квартала из фактов якоря и файла отчёта квартала — того, что пишет `reanchor.py --expected`
# (ожидание модели). Независимая от `reanchor.py` сборка тех же правил переноса (docs/MODEL.md §15.2): ставки якоря
# несут весь ЧПД; упр. факт квартала входит в историю мостов, их значения продлеваются закрытым кварталом; решения
# собраний закрываемого квартала становятся строками истории дивидендов; строки, которых модель не ведёт, — `null` с
# причиной. Узлы калибровки книги (стоимость риска по книгам, ряд периметра, ряд «прочего»), календарь и аналоги —
# как в фактах прежнего якоря.

EXPECTED_TOP = (("period", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt"),
                ("schema", "as_of", "published", "source", "note", "shares", "dividend_decisions"))
EXPECTED_SECTIONS = {
    "balance": (("books", "loans_fvtpl", "fvoci", "fvtpl_bonds", "allowance", "other_assets", "other_liabilities",
                 "dividends_payable", "bv_common", "fvoci_reserve"),
                ("dividends_payable_year", "dividends_payable_declared", "other_assets_fixed", "at1", "nci",
                 "nonworking_money", "allowance_books")),
    "pnl": (("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax", "ni", "ni_shareholders"),
            ("misc_net", "oci_fvoci", "other_equity_movements", "estimated")),
    "capital": (("n20_0", "n20_pre_dividend", "n1_1_bank", "basel_cet1", "basel_rwa", "bank_base_capital"),
                ("t2", "estimated", "estimate", "guarantees", "bank_own_funds", "bank_main_capital")),
    "market": (("ofz_curve", "key_avg"), ("price_index",)),
    "mgmt": (("nim", "cor"), ("cir",)),
    "shares": ((), ("issued_total", "issued_ordinary", "issued_preferred", "outstanding_total", "outstanding_ordinary",
                    "outstanding_preferred", "economic_treasury")),
}
MGMT_WORDS = {"nim": "чистая процентная маржа", "cor": "стоимость риска", "cir": "отношение расходов к доходам"}
# Узлы баланса, на которые раскладывается книга (вместе — вся книга): отчёт называет книгу одной суммой, узлы делятся
# долями прежнего якоря; кредиты по СС и долговые бумаги FVOCI / ССПУ отчёт называет сам.
BOOK_NODES = {
    "securities": ("securities.fvoci_debt", "securities.fvoci_repo", "securities.ac", "securities.ac_repo",
                   "securities.fvtpl_bonds"),
    "liquidity": ("liquidity.cash", "liquidity.cbr", "liquidity.due_from_banks"),
    "retail_current": ("funds.retail_current",), "retail_term": ("funds.retail_term",), "corp_term": ("funds.corp_term",),
    "corp_current": ("funds.corp_current",),
    "wholesale": ("wholesale.cbr", "wholesale.banks", "wholesale.issued_debt", "wholesale.subordinated", "wholesale.other_borrowed"),
    "insurance_liab": ("insurance.contract_liabilities",),
}
FVOCI_NODES = ("securities.fvoci_debt", "securities.fvoci_repo")
NOT_MODELLED = ("lease_gross", "loans_sme_other", "securities.equity_fvtpl", "securities.derivatives", "securities.equity_fvoci",
                "securities.equity_other", "securities.floating_share_fvtpl", "liquidity.reverse_repo_in_cash",
                "insurance.oms_payables_excluded", "insurance.reinsurance_assets_in_other")
CARRIED = ("calendar", "peers", "credit_products", "perimeter", "misc_window")


def put(obj: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for p in parts[:-1]:
        obj = obj.setdefault(p, {})
    obj[parts[-1]] = value


def carry_scale(interest: dict[str, float], nii: float, dia: float) -> tuple[float, float]:
    """(остаток ЧПД вне книг, множитель ставок книг активов). Ставки якоря несут весь ЧПД: остаток
    `nii − (Σ процентов книг активов − Σ процентов книг пассивов − страхование вкладов)` разнесён по книгам активов
    пропорционально их процентному доходу (docs/MODEL.md §15.2 п. 4; то же правило — в ops/tools/reanchor.py)."""
    income = sum(interest[b] for b in ASSET_BOOKS)
    residual = nii - (income - sum(interest[b] for b in LIAB_BOOKS) - dia)
    return residual, 1.0 + residual / income


def check_report_shape(report: dict) -> None:
    """Состав файла отчёта: незнакомый или недостающий ключ — отказ (опечатка не должна пройти молча)."""
    if not isinstance(report, dict):
        raise BuildError("отчёт квартала: ожидается словарь JSON")
    if report.get("schema", REPORT_SCHEMA) != REPORT_SCHEMA:
        raise BuildError(f"отчёт квартала: schema {report.get('schema')!r}, нужна {REPORT_SCHEMA!r} (docs/REANCHOR.md)")
    required, optional = EXPECTED_TOP
    problems = [f"нет {k}" for k in required if k not in report]
    problems += [f"незнакомый ключ {k}" for k in report if k not in required + optional]
    for name, (req, opt) in EXPECTED_SECTIONS.items():
        section = report.get(name)
        if section is None:
            continue
        if not isinstance(section, dict):
            problems.append(f"{name} — не словарь")
            continue
        problems += [f"нет {name}.{k}" for k in req if k not in section]
        problems += [f"незнакомый ключ {name}.{k}" for k in section if k not in req + opt]
    for where, block in (("balance.books", (report.get("balance") or {}).get("books")), ("interest", report.get("interest"))):
        if isinstance(block, dict):
            problems += [f"нет {where}.{b}" for b in BOOKS if b not in block]
            problems += [f"незнакомая книга {where}.{b}" for b in block if b not in BOOKS]
        elif block is not None:
            problems.append(f"{where} — не словарь по книгам")
    curve = (report.get("market") or {}).get("ofz_curve")
    if isinstance(curve, dict):
        problems += [f"нет market.ofz_curve.{t}" for t in CURVE_NODES if t not in curve]
    if problems:
        raise BuildError("отчёт квартала: " + "; ".join(problems))
    if not isinstance(report["capital"]["n20_pre_dividend"], bool):
        raise BuildError("отчёт квартала: capital.n20_pre_dividend — true или false")
    if (report["capital"].get("estimated") is True) != ("estimate" in report["capital"]):
        raise BuildError("отчёт квартала: capital.estimate — блок оценки есть тогда и только тогда, когда estimated: true")


def expected_facts(prev: dict[str, dict], report: dict, *, name: str, sha: str) -> tuple[dict[str, dict], list]:
    """Факты нового якоря (файлы сборщика) из фактов прежнего якоря `prev` и отчёта следующего квартала `report`.
    Возвращает (файлы, сверки). Чистая функция: вход не меняет."""
    checks: list[tuple[str, bool, str]] = []
    check_report_shape(report)
    old, new = Anchor(str(prev["anchor"]["period"])), Anchor(str(report["period"]))
    if new.period != q_next(old.period):
        raise BuildError(f"отчёт квартала — за {new.period}, факты стоят на {old.period}: нужен отчёт следующего "
                         f"квартала ({q_next(old.period)})")
    if "as_of" in report and str(report["as_of"]) != new.date:
        raise BuildError(f"отчёт квартала: as_of {report['as_of']} — не конец квартала {new.period} ({new.date})")

    def has(path: str) -> bool:
        try:
            return dig(report, path) is not None
        except (KeyError, TypeError):
            return False

    def num(path: str) -> float:
        x = dig(report, path)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or abs(x) == float("inf"):
            raise BuildError(f"отчёт квартала: {path} — не число ({x!r})")
        return float(x)

    def ref(path: str) -> str:
        return f"{name}, {path}, sha256 {sha[:16]}"

    def en(path: str, what: str, *, value: float | None = None, **extra) -> dict:
        """Узел из отчёта квартала — с точностью файла отчёта (девять знаков): число — ожидание модели, не отчётность."""
        return node(r9(num(path) if value is None else value), src=ref(path), calc=f"отчёт квартала: {what}", **extra)

    def calc(v: float, how: str, **extra) -> dict:
        return node(r9(v), calc=f"отчёт квартала: {how}", **extra)

    def kept(n: dict, **extra) -> dict:
        """Величина, которую отчёт квартала не называет, а модель не двигает: значение прежнего якоря."""
        if n.get("v") is None:
            return dict(n)
        return node(n["v"], calc=f"как на {d_ru(old.date)}: отчёт квартала величину не называет", **extra)

    def none(why: str, **extra) -> dict:
        return na(f"нет данных: отчёт квартала строку не несёт — {why}", **extra)

    out = {k: copy.deepcopy(prev[k]) for k in BUILT if k in prev}
    d, days = new.date, q_days(new.period)
    on, kq = d_ru(d), q_ru(new.period)

    # ---------------- balance.json
    pb, bal = prev["balance"], out["balance"]
    bal["as_of"] = d
    book = {b: num(f"balance.books.{b}") for b in BOOKS}
    for b in BOOKS:
        bal["books"][b] = en(f"balance.books.{b}", f"остаток книги {b} на {on}")
    given = {"securities.fvtpl_bonds": num("balance.fvtpl_bonds")}
    f_old = [float(dig(pb, p)["v"]) for p in FVOCI_NODES]
    given[FVOCI_NODES[0]] = r9(num("balance.fvoci") * f_old[0] / sum(f_old)) if sum(f_old) else r9(num("balance.fvoci"))
    given[FVOCI_NODES[1]] = r9(num("balance.fvoci") - given[FVOCI_NODES[0]])
    bal["loans_fvtpl"] = en("balance.loans_fvtpl", f"кредиты по справедливой стоимости на {on} (справочно: внутри corp_loans)")
    for b, nodes in BOOK_NODES.items():
        free = [p for p in nodes if p not in given]
        olds = {p: float(dig(pb, p)["v"]) for p in nodes}
        rest = book[b] - sum(given[p] for p in nodes if p in given)
        base = sum(olds[p] for p in free)
        if rest < -0.05:
            raise BuildError(f"отчёт квартала: строки книги {b}, заданные отдельно, больше её остатка")
        vals = {p: r9(rest * olds[p] / base) if base else r9(rest / len(free)) for p in free}
        if free:
            vals[free[-1]] = r9(rest - sum(vals[p] for p in free[:-1]))
        for p in nodes:
            if p in given:
                what = "balance.fvoci" if p in FVOCI_NODES else "balance.fvtpl_bonds"
                put(bal, p, node(given[p], src=ref(what), calc=f"отчёт квартала: строка книги {b} на {on}"
                                 + (f" — долей строки на {d_ru(old.date)}" if p in FVOCI_NODES else "")))
            else:
                put(bal, p, node(vals[p], src=ref(f"balance.books.{b}"),
                                 calc=f"отчёт квартала: остаток книги {b} × доля строки на {d_ru(old.date)} — модель ведёт "
                                      "книгу одной суммой"))
    for p in NOT_MODELLED:
        put(bal, p, none("справочную строку модель не ведёт"))
    bal["funds"]["total"] = calc(sum(book[b] for b in FUNDS_BOOKS), "Σ четырёх книг средств клиентов")
    # ключи проходов ядра (docs/REANCHOR.md §3.16; поля отчёта — те же, что пишет ops/tools/reanchor.py --expected):
    # неработающие деньги и ФОР (К8, Р6-1), резерв по кредитным книгам (К7) — узлы, которые ядро читает словом anchor
    nw = dig(report, "balance").get("nonworking_money") or {}
    bal["nonworking_money"] = {k: (en(f"balance.nonworking_money.{k}", f"неработающие деньги ({k}) на {on}") if k in nw else
                                   none("неработающие деньги модель ведёт внутри прочих активов"))
                               for k in list(pb["nonworking_money"]) + [k for k in nw if k not in pb["nonworking_money"]]}
    if "total" in nw and "mandatory_reserves" in nw:
        checks.append(("отчёт квартала: ФОР не больше неработающих денег",
                       num("balance.nonworking_money.mandatory_reserves") <= num("balance.nonworking_money.total"),
                       f"{ru(num('balance.nonworking_money.mandatory_reserves'), 3)} из {ru(num('balance.nonworking_money.total'), 3)}"))
    bal["allowance_ac"] = en("balance.allowance", f"резерв под обесценение кредитов на {on} (величиной)")
    ab = dig(report, "balance").get("allowance_books") or {}
    ab0 = pb.get("allowance_books", {})
    bal["allowance_books"] = {k: (en(f"balance.allowance_books.{k}", f"резерв по кредитной книге {k} на {on} (величиной)")
                                  if k in ab else none("резерв по кредитным книгам модель не ведёт"))
                              for k in list(ab0) + [k for k in ab if k not in ab0]}
    for k in ab:
        checks.append((f"отчёт квартала: резерв книги {k} меньше её остатка", num(f"balance.allowance_books.{k}") < book[k],
                       f"{ru(num(f'balance.allowance_books.{k}'), 3)} против {ru(book[k], 3)}"))
    bal["other_assets"] = en("balance.other_assets", f"прочие активы на {on}")
    fixed0 = pb["other_assets_fixed"]
    bal["other_assets_fixed"] = (en("balance.other_assets_fixed", f"постоянные прочие активы на {on}")
                                 if has("balance.other_assets_fixed") else kept(fixed0))
    share = bal["other_assets_fixed"]["v"] / fixed0["v"] if fixed0["v"] else 0.0
    bal["other_assets_fixed_parts"] = {k: calc(v["v"] * share, f"часть постоянных прочих активов — долей на {d_ru(old.date)}")
                                       for k, v in pb["other_assets_fixed_parts"].items()}
    bal["other_assets_parts"] = {k: none("разбивку прочих активов модель не ведёт") for k in pb["other_assets_parts"]}
    bal["other_liabilities"] = en("balance.other_liabilities", f"прочие обязательства на {on} (без дивидендов к выплате)")
    bal["other_liabilities_parts"] = {k: none("разбивку прочих обязательств модель не ведёт")
                                      for k in pb["other_liabilities_parts"]}
    bal["dividends_payable"] = en("balance.dividends_payable", f"дивиденды к выплате на {on}")
    if has("balance.dividends_payable_year"):
        bal["dividends_payable_year"] = int(num("balance.dividends_payable_year"))
    elif bal["dividends_payable"]["v"] == 0:
        bal.pop("dividends_payable_year", None)
    declared = dig(report, "balance.dividends_payable_declared") if has("balance.dividends_payable_declared") else []
    bal["dividends_payable_declared"] = [
        {"period": str(x["period"]), "amount": node(r6(float(x["amount"])), src=ref("balance.dividends_payable_declared"),
                                                     calc=f"отчёт квартала: объявлено и не выплачено на {on}")}
        for x in declared]
    eq, peq = bal["equity"], pb["equity"]
    for k in ("at1", "nci"):
        eq[k] = en(f"balance.{k}", f"{k} на {on}") if has(f"balance.{k}") else kept(peq[k])
    eq["bv_common"] = en("balance.bv_common", f"капитал акционеров без бессрочных на {on}")
    bv, at1, nci = eq["bv_common"]["v"], eq["at1"]["v"], eq["nci"]["v"]
    eq["total"] = calc(bv + at1 + nci, "bv_common + at1 + nci")
    for k, _ in EQUITY_LINES:
        eq[k] = none("компонент капитала модель отдельно не ведёт")
    eq["fvoci_reserve"] = en("balance.fvoci_reserve", f"фонд переоценки ССПСД после налога на {on}")
    al, oa = bal["allowance_ac"]["v"], bal["other_assets"]["v"]
    sum_a, sum_l = sum(book[b] for b in ASSET_BOOKS), sum(book[b] for b in LIAB_BOOKS)
    total_a = sum_a - al + oa
    total_l = sum_l + bal["other_liabilities"]["v"] + bal["dividends_payable"]["v"]
    bal["total_assets"] = calc(total_a, "Σ книг активов − резерв + прочие активы")
    bal["total_liabilities"] = calc(total_l, "Σ книг пассивов + прочие обязательства + дивиденды к выплате")
    checks.append(("отчёт квартала: активы = обязательства + капитал", abs(total_a - (total_l + eq["total"]["v"])) < 0.05,
                   f"активы {ru(total_a)}, обязательства и капитал {ru(total_l + eq['total']['v'])}"))
    listed = sum(x["amount"]["v"] for x in bal["dividends_payable_declared"])
    checks.append(("отчёт квартала: объявленные и не выплаченные дивиденды — часть остатка к выплате",
                   listed <= bal["dividends_payable"]["v"] + 1e-6 and 0 <= bal["other_assets_fixed"]["v"] <= oa,
                   f"по периодам {ru(listed, 3)} из {ru(bal['dividends_payable']['v'], 3)}; постоянные прочие активы "
                   f"{ru(bal['other_assets_fixed']['v'])} из {ru(oa)}"))
    if new.y != old.y:                                 # новый год якоря: концы прошлого года — прежний якорь
        bal["prev_year_end"] = {"as_of": old.date,
                                "loans_corporate": node(r6(float(pb["books"]["corp_loans"]["v"])),
                                                        calc=f"книга corp_loans на {d_ru(old.date)}: balance.json фактов {old.period}"),
                                "loans_retail": node(r6(sum(float(pb["books"][b]["v"]) for b in RETAIL_LOANS)),
                                                     calc=f"четыре розничные книги на {d_ru(old.date)}: balance.json фактов "
                                                          f"{old.period}")}
    loans, funds = sum(book[b] for b in LOANS), sum(book[b] for b in FUNDS_BOOKS)
    bal["iea"] = calc(sum_a, "процентные активы движка: кредитные книги + долговые бумаги + ликвидность")
    hist = bal["history"]
    if old.period in hist and "books" not in hist[old.period]:
        hist[old.period]["books"] = {b: node(float(pb["books"][b]["v"]), calc=f"balance.books.{b} фактов {old.period}")
                                     for b in BOOKS}
    hist[new.period] = {
        "date": d, "bv_common": calc(bv, "balance.equity.bv_common"), "loans": calc(loans, "сумма пяти кредитных книг"),
        "loans_ac_gross": calc(loans, "= loans: кредиты по СС лежат в corp_loans (отдельной книги нет)"),
        "funds": calc(funds, "средства клиентов: четыре книги"), "iea": calc(sum_a, "balance.iea"),
        "insurance_liab": calc(book[INSURANCE_BOOK], "книга insurance_liab"),
        "total_assets": calc(total_a, "balance.total_assets"),
        "loans_fvtpl": calc(bal["loans_fvtpl"]["v"], "balance.loans_fvtpl (справочно: внутри corp_loans)"),
    }

    # ---------------- nii_books.json: ставки якоря несут весь ЧПД
    nb = out["nii_books"]
    nb.update(as_of=d, period=new.period, days=node(days, calc=f"дней в квартале {kq} (act/365)"), rates_carry_residual=True)
    interest = {b: abs(num(f"interest.{b}")) for b in BOOKS}
    nii, dia = num("pnl.nii"), abs(num("dia"))
    residual, scale = carry_scale(interest, nii, dia)
    inc, exp = sum(interest[b] for b in ASSET_BOOKS), sum(interest[b] for b in LIAB_BOOKS)
    checks.append(("отчёт квартала: проценты книг дают ЧПД отчёта (остаток вне книг — меньше 10 % ЧПД)",
                   abs(residual) < 0.10 * abs(nii), f"Σ книг − страхование вкладов {ru(nii - residual)}, ЧПД {ru(nii)}, "
                                                    f"остаток {ru(residual, 3)}"))
    for b in BOOKS:
        bo, bc = float(pb["books"][b]["v"]), book[b]
        avg = (bo + bc) / 2
        asset = b in ASSET_BOOKS
        how = (f"interest_q × (1 + остаток ЧПД {ru(residual, 3)} / Σ процентов книг активов {ru(inc)}) / balance_avg × 365/{days}: "
               "ставка книги активов несёт долю процентов вне книг") if asset else f"interest_q / balance_avg × 365/{days}"
        nb["books"][b] = {
            "balance_open": node(bo, calc=f"остаток книги на {d_ru(old.date)} (balance.books.{b} фактов {old.period})"),
            "balance_close": node(r9(bc), calc=f"остаток книги на {on} (balance.books.{b})"),
            "balance_avg": node(r9(avg), calc="(balance_open + balance_close) / 2"),
            "interest_q": en(f"interest.{b}", f"проценты книги за {kq} (величиной)", value=interest[b]),
            "rate_anchor": node(round(interest[b] * (scale if asset else 1.0) / avg * 365 / days, 9), src=ref(f"interest.{b}"),
                                calc=f"отчёт квартала: {how}"),
        }
    iea_avg = sum((float(pb["books"][b]["v"]) + book[b]) / 2 for b in ASSET_BOOKS)
    nb.update(
        interest_assets_q=calc(inc, "Σ interest_q книг активов"),
        interest_liabilities_q=calc(exp, "Σ interest_q книг пассивов (величиной, с книгой insurance_liab)"),
        other_interest_net_q=calc(residual, "остаток: nii_q − (Σ процентов книг активов − Σ пассивов − dia_q); разнесён по "
                                            "ставкам книг активов (rates_carry_residual)"),
        dia_q=en("dia", f"расходы на страхование вкладов за {kq}, величиной", value=dia),
        nii_q=en("pnl.nii", f"ЧПД движка за {kq} (с финансовыми расходами страхования)"),
        nii_form_q=none("ЧПД формы (без финрасходов страхования) отчёт квартала не несёт"),
        iea_avg=calc(iea_avg, "Σ balance_avg книг активов"),
        nim_eng_q=node(round(nii * 365 / days / iea_avg, 9), calc=f"отчёт квартала: nii_q × 365/{days} / iea_avg (ЧПМ базиса движка)"),
        current_share_anchor=node(round(book["retail_current"] / (book["retail_current"] + book["retail_term"]), 9),
                                  calc="отчёт квартала: текущие счета физлиц / (текущие счета + срочные вклады) на якоре"),
        key_avg_anchor_q=en("market.key_avg", f"средняя ключевая ставка за {kq}"),
    )

    # ---------------- pnl_quarterly.json
    pq = out["pnl_quarterly"]
    pq["as_of"] = d
    last_row = prev["pnl_quarterly"]["quarters"][old.period]
    row = {k: none("строку отчёта модель отдельно не ведёт") for k, v in last_row.items() if isinstance(v, dict) and "v" in v}
    for k in EXPECTED_SECTIONS["pnl"][0]:
        row[k] = en(f"pnl.{k}", f"строка движка за {kq} (отчётный базис)")
    for k in ("oci_fvoci", "other_equity_movements"):
        if has(f"pnl.{k}"):
            row[k] = en(f"pnl.{k}", f"движение капитала за {kq}")
    lines = sum(row[k]["v"] for k in PNL_SUM if k != "misc_net")
    row["misc_net"] = (en("pnl.misc_net", f"прочие строки за {kq}") if has("pnl.misc_net")
                       else calc(row["pbt"]["v"] - lines, "pbt − (nii + llp_debt_fa + fees_net + insurance_net + noncore_net + opex)"))
    p = {k: row[k]["v"] for k in EXPECTED_SECTIONS["pnl"][0] + ("misc_net",)}
    row["ni_nci"] = calc(p["ni"] - p["ni_shareholders"], "ni − ni_shareholders")
    row["dia"] = calc(dia, "nii_books.dia_q: расходы на страхование вкладов, величиной")
    row["at1_coupon"] = kept(last_row["at1_coupon"])
    row["key_avg"] = en("market.key_avg", f"средняя ключевая ставка за {kq}")
    row["noncore_parts"] = {k: none("разбивку разовых модель не ведёт") for k in last_row.get("noncore_parts", {})}
    row["reported"] = {k: dict(row[k]) for k in ("pbt", "tax", "ni", "ni_shareholders", "ni_nci")}
    if dig(report, "pnl").get("estimated") is True:
        for k in ("ni_shareholders", "ni", "ni_nci", "pbt", "tax", "misc_net", "noncore_net"):
            row[k]["estimated"] = True
    pq["quarters"][new.period] = row
    s = sum(p[k] for k in PNL_SUM)
    checks.append((f"отчёт квартала: прибыль до налога {kq} = сумме строк; прибыль = прибыль до налога + налог; расходы — "
                   "со знаком минус", abs(s - p["pbt"]) < 0.05 and abs(p["pbt"] + p["tax"] - p["ni"]) < 0.05 and p["opex"] < 0,
                   f"Σ строк {ru(s, 2)} против {ru(p['pbt'], 2)}; налог {ru(p['tax'], 2)}, прибыль {ru(p['ni'], 2)}"))

    # ---------------- capital.json: слоты — банк соло (n20_0 ← Н1.0, n1_1_bank ← Н1.2)
    cap0, cap = prev["capital"], out["capital"]
    cap["as_of"] = d
    estimated = dig(report, "capital").get("estimated") is True
    flag = {"estimated": True} if estimated else {}
    form_date = new.form_date
    t2 = (en("capital.t2", f"дополнительный капитал банка на {d_ru(form_date)}", basis="RAS") if has("capital.t2")
          else kept(cap0["t2_recognized"], basis="RAS"))
    cet1, rwa, base = num("capital.basel_cet1"), num("capital.basel_rwa"), num("capital.bank_base_capital")
    pre = bool(dig(report, "capital.n20_pre_dividend"))
    for slot, what in (("n20_0", "Н1.0"), ("n1_1_bank", "Н1.2")):
        block = {"basis": cap0[slot]["basis"], "value": en(f"capital.{slot}", f"{what} банка на {d_ru(form_date)}", **flag),
                 "as_of": form_date, "estimated": estimated}
        if slot == "n1_1_bank":
            block["slot_metric"] = cap0[slot].get("slot_metric", "Н1.2")
        if estimated:
            e = dig(report, f"capital.estimate.{slot}")
            block["estimate"] = {"bank_value": node(float(e["bank_value"]), src=ref(f"capital.estimate.{slot}.bank_value"),
                                                    calc="норматив банка на последнюю форму"),
                                 "spread": node(float(e["spread"]), src=ref(f"capital.estimate.{slot}.spread"),
                                                calc="поправка оценки к последней форме"),
                                 "spread_as_of": str(e["spread_as_of"])}
        cap[slot] = block
    cap["n20_0"]["pre_dividend"] = pre
    cap["n20_0"]["pre_dividend_note"] = ("норматив — до вычета объявленного дивиденда из капитала банка" if pre else
                                         "объявленных и не вычтенных из норматива дивидендов на якоре нет")
    if "min_with_buffers" in cap0["n20_0"]:
        cap["n20_0"]["min_with_buffers"] = dict(cap0["n20_0"]["min_with_buffers"])
    n10, n12 = cap["n20_0"]["value"]["v"], cap["n1_1_bank"]["value"]["v"]
    cap["n1_0_bank"] = calc(n10, "capital.n20_0.value (Н1.0 банка)", basis="RAS", as_of=form_date)
    cap["n1_2_bank"] = calc(n12, "capital.n1_1_bank.value (Н1.2 банка)", basis="RAS", as_of=form_date)
    cap["n20_2"] = calc(n12, "Н1.2 банка (тот же второй норматив)", basis="RAS", as_of=form_date)
    cap["n1_1_bank_h11"] = none("Н1.1 банка модель не ведёт", basis="RAS")
    cap["n27_bank"] = none("Н27 банка модель не ведёт", basis="RAS")
    cap["bank_base_capital"] = en("capital.bank_base_capital", f"базовый капитал банка на {d_ru(form_date)} (слот ядра)",
                                  basis="RAS", **flag)
    own = num("capital.bank_own_funds") if has("capital.bank_own_funds") else None
    cap["bank_own_funds"] = (en("capital.bank_own_funds", f"собственные средства банка на {d_ru(form_date)} (форма 0409123)",
                                basis="RAS", **flag) if own is not None else
                             calc(rwa * n10, "basel.rwa × Н1.0 (знаменатель норматива вменён)", basis="RAS", **flag))
    cap["bank_additional_capital"] = none("добавочный капитал банка модель не ведёт", basis="RAS")
    cap["bank_main_capital"] = (en("capital.bank_main_capital", f"основной капитал банка на {d_ru(form_date)} (форма 0409123)",
                                   basis="RAS", **flag) if has("capital.bank_main_capital") else
                                none("основной капитал банка модель не ведёт", basis="RAS"))
    cap["basel"] = {"basis": cap0["basel"]["basis"], "as_of": form_date,
                    "cet1": en("capital.basel_cet1", f"базовый капитал банка на {d_ru(form_date)} (слот ядра)", **flag),
                    "rwa": en("capital.basel_rwa", f"RWA знаменателя Н1.0 на {d_ru(form_date)}", **flag),
                    "rwa_n11": none("знаменатель Н1.1 модель не ведёт"), "rwa_n12": none("знаменатель Н1.2 модель не ведёт"),
                    "cet1_ratio": calc(cet1 / rwa, "basel.cet1 / basel.rwa", **flag),
                    "total_ratio": calc(n10, "Н1.0 банка", **flag)}
    cap["t2_recognized"] = t2
    cap["at1"] = {**{k: (kept(v) if isinstance(v, dict) and "v" in v else v) for k, v in cap0["at1"].items()},
                  "amount": calc(at1, "balance.equity.at1 (бессрочные в капитале МСФО)")}
    cap["fvoci_reserve"] = en("balance.fvoci_reserve", "фонд переоценки ССПСД после налога; = balance.equity.fvoci_reserve",
                              basis="IFRS")
    cap["ofz_curve_anchor"] = {"basis": "отчёт квартала (у ожидаемого отчёта — кривая миров слоя «свой взгляд»)", "as_of": d,
                               "convention": cap0["ofz_curve_anchor"]["convention"],
                               **{t: en(f"market.ofz_curve.{t}", f"бескупонная доходность ОФЗ {t} лет на {on}") for t in CURVE_NODES}}
    cap["basel_ifrs"] = {"basis": cap0["basel_ifrs"]["basis"], "as_of": d,
                         **{k: none("Базель группы — только в справочнике банка") for k, v in cap0["basel_ifrs"].items()
                            if isinstance(v, dict)}}
    cap["instruments_total"] = calc(at1, "balance.equity.at1")
    gr = dig(report, "capital").get("guarantees") or {}
    g0 = cap0.get("guarantees", {})
    cap["guarantees"] = {k: (en(f"capital.guarantees.{k}", f"номинал гарантий ({k}) на {on}") if k in gr else
                             none("объём гарантий модель не ведёт"))
                         for k in list(g0) + [k for k in gr if k not in g0]}
    cap["history"].append({"period": new.period, "date": form_date, "basis": "RAS (банк соло)",
                           "n1_0": calc(n10, "capital.n20_0.value", **flag), "n1_1": none("Н1.1 банка модель не ведёт"),
                           "n1_2": calc(n12, "capital.n1_1_bank.value", **flag),
                           "own_funds": calc(rwa * n10 if own is None else own, "capital.bank_own_funds", **flag),
                           "base_capital": calc(base, "capital.bank_base_capital", **flag),
                           "rwa_n10": calc(rwa, "capital.basel.rwa", **flag)})
    cap.pop("core_form_check", None)                   # справка формой ядра — только из листов
    checks.append(("отчёт квартала: вычеты якоря (капитал без бессрочных − базовый капитал банка) положительны",
                   0 < bv - cet1 < bv, ru(bv - cet1, 3)))

    # ---------------- shares.json
    out["shares"]["as_of"] = d
    for k in EXPECTED_SECTIONS["shares"][1]:
        if has(f"shares.{k}"):
            out["shares"][k] = en(f"shares.{k}", f"число акций на {on}, млн шт.")
    if has("shares.issued_total") and has("shares.outstanding_total"):
        out["shares"]["treasury_ordinary"] = calc(num("shares.issued_total") - num("shares.outstanding_total"),
                                                  "issued_total − outstanding_total")

    # ---------------- dividends.json: решения закрываемого квартала — строки истории; запись реестра
    div = out["dividends"]
    div["as_of"] = d
    rows = {h["period"]: h for h in div["history"]}
    n_div = float((out["shares"].get("dividend_eligible") or out["shares"]["outstanding_total"])["v"])
    seeded = {s_["period"] for s_ in div["register_seed"]}
    for i, x in enumerate(dig(report, "dividend_decisions") if has("dividend_decisions") else []):
        per, dps = str(x["period"]), float(x["dps"])
        where = f"dividend_decisions.{i}"
        if not old.date < str(x["decided_date"]) <= d:
            raise BuildError(f"отчёт квартала: {where}.decided_date {x['decided_date']} — решение закрываемого квартала: позже "
                             f"{d_ru(old.date)} и не позже {on}")
        h = rows.get(per)
        if h is None:
            h = {"year": q_parse(per)[0], "period": per}
            div["history"].append(h)
            rows[per] = h
        if h.get("dps") is None or abs(float(h["dps"]["v"]) - dps) > 1e-6:
            h["dps"] = node(dps, src=ref(f"{where}.dps"), calc="отчёт квартала: дивиденд на акцию, ₽")
            h["pool_declared"] = (node(r6(float(x["pool_declared"])), src=ref(f"{where}.pool_declared"),
                                       calc="отчёт квартала: сумма решения")
                                  if x.get("pool_declared") is not None else
                                  calc(dps * n_div / 1000, "DPS × акции в расчёте суммы (dividend_eligible) / 1000"))
        h["decided_date"] = str(x["decided_date"])
        for k in ("record_date", "pay_date"):
            if x.get(k) is not None:
                h[k] = str(x[k])
        if x.get("record_date") is not None and str(x["record_date"]) > d and per not in seeded:
            div["register_seed"].append({"year": q_parse(per)[0], "period": per,
                                         "dps": node(dps, src=ref(f"{where}.dps"), calc="отчёт квартала: дивиденд на акцию, ₽"),
                                         "status": "declared", "decided_date": str(x["decided_date"]),
                                         "record_date": str(x["record_date"]), "ex_date": str(x["record_date"]),
                                         **({"pay_date": str(x["pay_date"])} if x.get("pay_date") is not None else {}),
                                         "sources": [f"manual: отчёт квартала {new.period} ({name})"]})
            seeded.add(per)
    div["history"].sort(key=lambda h: h["period"])
    unpaid = {x["period"] for x in bal["dividends_payable_declared"]}
    div["register_seed"] = [s_ for s_ in div["register_seed"]
                            if s_["period"] in unpaid or not (s_.get("ex_date") or s_.get("record_date"))
                            or str(s_.get("ex_date") or s_["record_date"]) > d]
    if not div["register_seed"]:
        div.pop("register_seed_note", None)
    closed = {h["period"] for h in div["history"] if str(h.get("decided_date") or "9") <= d}
    checks.append(("отчёт квартала: у каждой суммы «объявлено, не выплачено» есть решение не позже якоря",
                   unpaid <= closed, ", ".join(sorted(unpaid)) or "список пуст"))

    # ---------------- bridge_mgmt_ifrs.json и mgmt_quarterly.json
    br = out["bridge_mgmt_ifrs"]
    br["as_of"] = d
    l0 = sum(float(pb["books"][b]["v"]) for b in LOANS)
    i0 = sum(float(pb["books"][b]["v"]) for b in ASSET_BOOKS)
    income = sum(p[k] for k in ("nii", "fees_net", "insurance_net", "misc_net"))
    engine = {"cor": (-p["llp_debt_fa"] * 365 / days / ((l0 + loans) / 2),
                      f"−llp_debt_fa {ru(p['llp_debt_fa'], 3)} × 365/{days} / средняя сумма пяти кредитных книг "
                      f"{ru((l0 + loans) / 2, 2)}"),
              "nim": (nii * 365 / days / ((i0 + sum_a) / 2),
                      f"nii {ru(nii, 3)} × 365/{days} / средние процентные активы движка {ru((i0 + sum_a) / 2)}"),
              "cir": (-p["opex"] / income, f"−opex {ru(p['opex'], 3)} / (nii + fees_net + insurance_net + misc_net) {ru(income, 3)}")}
    mgmt_nodes = {}
    for x_, (eng, how) in engine.items():
        block = br[x_]
        value0, n0 = float(prev["bridge_mgmt_ifrs"][x_]["value"]["v"]), int(prev["bridge_mgmt_ifrs"][x_]["n"]["v"])
        ratio = block.get("method") == "ratio"
        if has(f"mgmt.{x_}"):
            mg = en(f"mgmt.{x_}", f"упр. {MGMT_WORDS[x_]} за {kq}")
        elif ratio:
            mg = calc(eng * 4 * days / 365 / value0, f"упр. базис через мост: engine_x4 / bridge_mgmt_ifrs.{x_}.value фактов "
                                                       f"{old.period}")
        else:
            mg = calc(eng - value0, f"упр. базис через мост: engine − bridge_mgmt_ifrs.{x_}.value фактов {old.period}")
        mgmt_nodes[x_] = mg
        line = {"period": new.period, "mgmt": dict(mg), "engine": node(round(eng, 9), calc=how)}
        if x_ == "nim":
            eng4 = eng * 4 * days / 365
            level = eng4 / mg["v"] if ratio else eng4 - mg["v"]
            line["engine_x4"] = node(round(eng4, 9), calc="nii × 4 / средние процентные активы движка")
            line["gap"] = node(round(eng / mg["v"] if ratio else eng - mg["v"], 9),
                               calc="engine / mgmt" if ratio else "engine − mgmt")
            line["gap_x4"] = node(round(level, 9), calc="engine_x4 / mgmt" if ratio else "engine_x4 − mgmt")
        else:
            level = eng - mg["v"]
            line["gap"] = node(round(level, 9), calc="engine − mgmt")
        if x_ == "cor":
            line["engine_books"] = node(round(eng, 9), calc="знаменатель движка — сумма пяти кредитных книг: тот же engine")
            line["gap_books"] = node(round(level, 9), calc="engine_books − mgmt")
        block["history"].append(line)
        block["window"], n1 = [block["window"][0], new.period], n0 + 1
        block["value"] = node(round((value0 * n0 + level) / n1, 9),
                              calc=f"среднее по окну {block['window'][0]}–{new.period}: значение фактов {old.period} продлено "
                                   f"кварталом (n = {n1})")
        block["n"] = node(n1, calc="кварталов в окне")
        block["sd"] = none("разброс по окну считается из листов этапа 1")
        if x_ == "cor":
            block["value_books"] = dict(block["value"])
            block["value_ac_only"] = dict(block["value"])
        checks.append((f"отчёт квартала: мост «{MGMT_WORDS[x_]}» упр. ↔ движок", True,
                       f"{value0:.6f} → {block['value']['v']:.6f} (n = {n1})"))
    br["window"] = [br["window"][0], new.period]
    mq = out["mgmt_quarterly"]
    mq["as_of"] = d
    mrow = {k: none("управленческую метрику модель не ведёт") for k in prev["mgmt_quarterly"]["quarters"][old.period]}
    for x_ in ("nim", "cor", "cir"):
        mrow[x_] = dict(mgmt_nodes[x_])
        mrow[f"{x_}_exact"] = dict(mgmt_nodes[x_])
    mq["quarters"][new.period] = mrow

    # ---------------- bridge_ras_ifrs.json, guidance.json, узлы калибровки: состав прежний
    out["bridge_ras_ifrs"]["as_of"] = d
    out["bridge_ras_ifrs"]["note"] = (f"отчёт квартала {new.period}: формы банка за квартал не собраны — мосты по {old.period} "
                                      "(ядро их не читает)")
    checks.append(("гайденс — как в фактах прежнего якоря", True,
                   f"год гайденса {out['guidance']['year']}" + ("" if int(out["guidance"]["year"]) == new.y else
                                                              f" при якоре {new.period}: гайденс нового года — из листов этапа 1")))

    # ---------------- anchor.json: отчёт — документ реестра
    an = out["anchor"]
    an.update(as_of=d, period=new.period, first_period=new.next,
              note=(f"ЯКОРЬ ИЗ ОТЧЁТА КВАРТАЛА (сухой прогон перезаякоривания, docs/MODEL.md §15.2): числа {new.period} — из файла "
                    f"«{name}» (у ожидаемого отчёта — ожидание модели, не отчётность); кварталы по {old.period} — факты. "
                    "В data/facts не кладётся"),
              expected={"period": new.period, "from_anchor": old.period, "report": name, "sha256": sha,
                        "source": "; ".join(str(report[k]) for k in ("source", "note") if report.get(k))})
    an["documents"] = sorted(an["documents"] + [{
        "key": f"quarter_report_{new.period}", "file": None, "sha256": sha, "url": None,
        "title": f"Отчёт квартала {new.period} (quarter-report/1) — вход сухого прогона перезаякоривания; не отчётность",
    }], key=lambda r: (r["key"], r["sha256"]))
    return {k: out[k] for k in BUILT if k in out}, checks


def main_expected(a) -> int:
    """Режим --expected: факты следующего квартала из фактов якоря и отчёта квартала; только в --out."""
    source = a.facts or FACTS
    if a.out is None or a.out.resolve() == FACTS.resolve():
        print("ПРОВАЛ: --expected пишет только в --out, и это не data/facts (ожидание — не факт)", file=sys.stderr)
        return 1
    try:
        raw = a.expected.read_bytes()
        report = json.loads(raw.decode("utf-8"))
        prev = {k: json.loads((source / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
        if a.anchor and isinstance(report, dict) and a.anchor != report.get("period"):
            raise BuildError(f"--anchor {a.anchor}, а отчёт квартала — за {report.get('period')}")
        files, checks = expected_facts(prev, report, name=a.expected.name, sha=hashlib.sha256(raw).hexdigest())
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ПРОВАЛ: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except BuildError as e:
        print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
        return 1
    print(f"якорь {files['anchor']['period']} ({files['anchor']['as_of']}) из фактов {prev['anchor']['period']} и {a.expected.name}")
    for name, ok, detail in checks:
        print(f"{'ок  ' if ok else 'СБОЙ'} {name}: {detail}")
    if any(not ok for _, ok, _ in checks):
        print("ПРОВАЛ: отчёт квартала не сошёлся — файлы не записаны", file=sys.stderr)
        return 1
    if a.check:
        diff = [k for k, v in files.items() if not (a.out / f"{k}.json").exists()
                or (a.out / f"{k}.json").read_text(encoding="utf-8") != body(k, v)]
        if diff:
            print(f"РАСХОЖДЕНИЕ с {a.out}: " + ", ".join(f"{k}.json" for k in diff), file=sys.stderr)
            return 1
        print(f"ок: {len(files)} файлов совпали с {a.out}")
        return 0
    write(files, a.out)
    print(f"записано: {len(files)} файлов в {a.out}; без изменений перенесены: {', '.join(CARRIED)}")
    return 0


# ------------------------------------------------------------------ командная строка

def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Факты ПАО «Совкомбанк» из листов этапа 1 (папка передачи — BANK_HANDOFF_DIR)")
    ap.add_argument("--check", action="store_true", help="сверить с каталогом выхода, не писать")
    ap.add_argument("--out", type=Path, default=None, help="каталог для записи (по умолчанию data/facts)")
    ap.add_argument("--anchor", default=None, metavar="ПЕРИОД",
                    help="квартал якоря вида ГГГГQк (по умолчанию — period из data/facts/anchor.json)")
    ap.add_argument("--report", type=Path, default=None, metavar="ФАЙЛ",
                    help="записать файл отчёта квартала якоря (quarter-report/1) — вход reanchor.py --facts")
    ap.add_argument("--plan", action="store_true",
                    help="перечень квартала: шаги дня отчёта и строки листов, которых не хватает для якоря --anchor")
    ap.add_argument("--forms", type=Path, nargs="+", default=None, metavar="ПЕРЕПИСЬ",
                    help="тождества переписи форм-сканов ОПУ и ОФП (одна или две независимые переписи); с --anchor — "
                         "полнота блоков квартала")
    ap.add_argument("--expected", type=Path, default=None, metavar="ФАЙЛ",
                    help="сухой прогон перезаякоривания: факты следующего квартала из фактов якоря и отчёта квартала "
                         "(quarter-report/1, его пишет reanchor.py --expected); пишет только в --out; папка передачи не нужна")
    ap.add_argument("--facts", type=Path, default=None, metavar="КАТАЛОГ",
                    help="с --report: готовый каталог фактов вместо сборки из папки передачи; с --expected и --anchor другого "
                         "квартала: каталог фактов прежнего якоря (по умолчанию data/facts)")
    a = ap.parse_args(argv)
    if a.expected is not None:
        return main_expected(a)
    root_env = os.environ.get("BANK_HANDOFF_DIR")
    try:
        if a.forms is not None:
            if len(a.forms) > 2:
                raise BuildError("--forms: одна или две переписи")
            tmpl = Path(root_env) / MANUAL_DIR if root_env else None
            return check_forms(a.forms, Anchor(a.anchor) if a.anchor else None, tmpl)
        if a.report is not None and a.facts is not None:
            files = {k: json.loads((a.facts / f"{k}.json").read_text(encoding="utf-8")) for k in BUILT}
            if a.anchor and a.anchor != files["anchor"]["period"]:
                raise BuildError(f"--anchor {a.anchor}, а факты в {a.facts.name} — на {files['anchor']['period']}")
            write_report(files, a.report, source=f"факты сборщика на якоре {files['anchor']['period']}")
            return 0
        if not root_env:
            print("ПРОВАЛ: BANK_HANDOFF_DIR не задан — нужна папка передачи с листами этапа 1", file=sys.stderr)
            return 1
        anchor = Anchor(a.anchor or default_anchor())
        if a.plan:
            return print_plan(Path(root_env), anchor, a.facts)
        files, c = build_ctx(Path(root_env), anchor, carry_from=a.facts)
        checks = c.checks
    except (OSError, ValueError, KeyError) as e:
        print(f"ПРОВАЛ: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except BuildError as e:
        print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
        return 1
    print(f"якорь {anchor.period} ({anchor.date})")
    for name, ok, detail in checks:
        print(f"{'ок  ' if ok else 'СБОЙ'} {name}" + (f": {detail}" if detail else ""))
    for n in c.notes:
        print(f"пометка: {n}")
    if any(not ok for _, ok, _ in checks):
        print("ПРОВАЛ: сверки не сошлись — файлы не записаны", file=sys.stderr)
        return 1
    target = a.out or FACTS
    if a.check:
        diff = [k for k, v in files.items() if not (target / f"{k}.json").exists()
                or (target / f"{k}.json").read_bytes() != body(k, v).encode("utf-8")]
        if diff:
            print(f"РАСХОЖДЕНИЕ с {target}: " + ", ".join(f"{k}.json" for k in diff), file=sys.stderr)
            return 1
        print(f"ок: {len(files)} файлов совпали с {target} байт в байт")
    else:
        write(files, target)
        print(f"записано: {len(files)} файлов в {target}")
    if a.report is not None:
        try:
            write_report(files, a.report, source=f"листы этапа 1, якорь {anchor.period}")
        except BuildError as e:
            print(f"ПРОВАЛ сборки: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
