# -*- coding: utf-8 -*-
"""Перезаякоривание книги на отчёт квартала: кандидат книги и фактов, «что сдвинулось», разложение скачка.

ЗАЧЕМ ФУНКЦИЯ, А НЕ РУЧНАЯ ПРАВКА (М§15.2). Книга стоит на одном квартале; отчёт МСФО закрывает
её первый прогнозный квартал, и якорь переходит на него. Всё, что помнит прошлое или привязано к
якорю, обязано переехать вместе с ним: иначе оценка сдвигается без единой новости (урок 850oa:
ручная процедура дала сотни рублей «механики»). Инструмент делает перенос одной функцией, а тесты
`tests/test_reanchor*.py` держат инвариант «факт = ожидание ⇒ механика ≈ 0»: клетка,
перезаякоренная на своём пути, сохраняет стоимость. Порядок работы и формулы — docs/REANCHOR.md.

Форму книги выбирают её ключи, форму фактов — узлы прежних фактов: годовой или квартальный календарь
дивидендов (`dividends.calendar.frequency`), остатки книг суммой строк или прямыми узлами
`balance.books.<b>`, постоянные прочие активы, ограничение роста капиталом, строки истории мостов.

Как запускать (из корня репозитория):
  python -B ops/tools/reanchor.py --expected ФАЙЛ.json
      ожидаемый отчёт закрываемого квартала — «факты = ожидание модели» (сухой прогон; не
      шаблон для настоящих чисел: в нём нет ни одного факта)
  python -B ops/tools/reanchor.py --facts ФАЙЛ.json --out КАТАЛОГ
      [--valuation-date ГГГГ-ММ-ДД] [--version В] [--band ПРОГОНОВ] [--no-cells]
      [--transmission keep|resolve] [--compare-facts КАТАЛОГ]
      [--book КНИГА] [--facts-dir КАТАЛОГ] [--template ШАБЛОН]
      кандидат книги и фактов на отчёте ФАЙЛ и разложение скачка на дате оценки
      (по умолчанию — `published` отчёта, иначе день после конца квартала)
  python -B ops/tools/reanchor.py --capital-form ФАЙЛ.json --out КАТАЛОГ
      [--valuation-date ГГГГ-ММ-ДД] [--version В] [--band ПРОГОНОВ] [--compare-facts КАТАЛОГ]
      замена оценки нормативов якоря фактом формы БЕЗ смены якоря: кандидат книги и фактов на том
      же квартале и сдвиг точки от замены (строка «факты» разложения между выпусками)
Файл настоящего отчёта пишет сборщик фактов из листов нового квартала, факты нового якоря из
ожидаемого отчёта — он же:
  python -B ops/tools/build_facts.py --anchor КВАРТАЛ --out КАТАЛОГ --report ФАЙЛ.json
  python -B ops/tools/build_facts.py --expected ФАЙЛ.json --out КАТАЛОГ

Что пишет — ТОЛЬКО в --out (по умолчанию var/reanchor/<квартал>/, у формы — var/reanchor/<квартал>-form/).
Внутри репозитория каталог кандидата — только под var/ (в git оттуда попадает один .gitkeep): любой
другой каталог рабочей копии (data/, model/, docs/, tests/, ops/, web/…) — отказ; вне репозитория —
куда угодно. В режиме `resolve` — только expected.json и REANCHOR.md.
  assumptions.yaml, assumptions.json   машинная книга-кандидат (без комментариев)
  assumptions_template.yaml            шаблон книги с теми же правками (комментарии сохранены)
  facts/*.json                         рабочие факты нового якоря из файла отчёта (узлы с пометкой
                                       `calc: reanchor…`; канон фактов с источниками и сверками
                                       собирает `build_facts.py`, сверка — `--compare-facts`)
  expected.json                        ожидаемый отчёт того же квартала
  REANCHOR.md                          производные величины, дивиденды по периодам, «что сдвинулось»,
                                       разложение скачка точки и медианы (в квартале шока — ещё строка
                                       «обучение» отчёта без шока, М§12; при росте, урезанном капиталом
                                       в части клеток, — абзац о росте; у книги с миром-опорой κ — строка
                                       «история до сетки»), проверки ядра на кандидате (инварианты,
                                       сработавшие гейты и флаги; числа гейтов-целей книги и уровни после
                                       фазы роста — до и после), предупреждения и ручные шаги
                                       у `--capital-form` REANCHOR.md — о замене оценки фактом формы: что
                                       заменено, что выведено заново, сдвиг точки, проверки ядра

ФАЙЛ ОТЧЁТА КВАРТАЛА (`quarter-report/1`; JSON; млрд ₽, млн шт., доли единицы; расходы — со знаком
минус, как в отчётности; ОПУ и проценты — за КВАРТАЛ, не нарастающим итогом). Незнакомый ключ — отказ.
  schema       "quarter-report/1" (необязательно)
  period       закрываемый квартал — РОВНО первый прогнозный квартал книги
  as_of, published, source, note      конец квартала (сверка), дата публикации (дата оценки
               кандидата), источник и примечание — необязательно
  balance      остатки на конец квартала (МСФО группы):
               books {книга ЧПД: остаток} — все книги `nii.books` (кредиты — валовые, кредиты по СС —
               внутри своей книги); loans_fvtpl (у книги без отдельной части по СС — справка); fvoci,
               fvtpl_bonds (долговые бумаги FVOCI с репо и облигации по СС через ОПУ); allowance
               (резерв по кредитам АС, величиной); other_assets, other_liabilities (без дивидендов к
               выплате); other_assets_fixed (постоянная в рублях часть прочих активов; нет — значение
               прежних фактов); dividends_payable; bv_common (капитал акционеров); fvoci_reserve
               (после налога); at1, nci — если изменились.
               Годовой календарь: dividends_payable_year (год прибыли; обязателен при сумме > 0).
               Квартальный календарь: dividends_payable_declared [{period, amount}] — объявленные и
               не выплаченные дивиденды по кварталам прибыли (нет поля — список пуст; остаток сверх
               списка — постоянное обязательство); dividends_payable_year не читается — предупреждение
  interest     {книга: проценты квартала по книге, величиной}; dia — взносы на страхование вкладов
  pnl          nii, fees_net, llp_debt_fa, insurance_net, noncore_net, opex, pbt, tax, ni,
               ni_shareholders; необязательно — misc_net (иначе остаток до pbt), oci_fvoci,
               other_equity_movements, estimated (прибыль квартала — напечатанное значение: строки
               прибыли фактов кандидата несут пометку оценки)
  capital      n20_0 и n20_pre_dividend (норматив до вычета объявленного дивиденда из
               регуляторного капитала?), n1_1_bank, basel_cet1, basel_rwa, bank_base_capital — слоты
               семейства, смысл — по книге (у панели с нормативами банковской группы: второй норматив
               группы, капитал группы без регуляторных инструментов, вменённые RWA, базовый капитал
               группы); необязательно — t2 (инструменты капитала), estimated и estimate
               {слот: {bank_value, spread, spread_as_of}} — нормативы стоят оценкой до выхода формы
  market       ofz_curve {1, 3, 5, 10} — бескупонная кривая на отчётную дату; key_avg — средняя
               ключевая квартала; price_index — индекс цен квартала (конец к началу), необязательно:
               без него — ожидаемый индекс миров книги
  mgmt         nim, cor — управленческие ЧПМ и стоимость риска квартала; cir — необязательно
  shares       issued_total, outstanding_total, economic_treasury, поля по категориям акций — если
               изменились
  dividend_decisions   квартальный календарь: [{period, dps, decided_date, record_date?, pay_date?,
               pool_declared?}] — решения собраний, принятые после прежней даты фактов и не позже
               конца закрываемого квартала; в ожидаемом отчёте — решения клеток этого квартала

ФАЙЛ ФОРМЫ (`capital-form/1`): period (якорь книги), n20_0, n1_1_bank, basel_cet1, basel_rwa,
bank_base_capital; необязательно — schema, as_of, published, source, note, t2, n20_pre_dividend.

ЧТО ПЕРЕНОСИТСЯ:
  meta         anchor_period, first_period, facts_date, valuation_date, version
  наблюдение   закрытый квартал → `joint.regime_update.observations` с замороженными ожиданиями
               режимов прежней книги (mu_cor, mu_nim); нау-каст того же квартала заменяется;
               наблюдения старше окна удаляются; μ оставшихся записей не пересчитываются — ни при
               следующих переносах, ни при смене года якоря (М§12); апостериорные в книгу не
               вписываются
  цены якоря   `noncore.result_real`, `other.misc_net_real` и их оси × индекс цен квартала (у года
               якоря первой строки индексируется только остаток года)
  anchor-ключи отношения, которые клетка держит постоянными, выводятся из новых фактов сами;
               линия доли текущих счетов (c_ref, key_ref) и базовое оптовое фондирование
               (`volumes.wholesale_to_funds`) замораживаются числами прежней книги — их состояние
               идёт с лагом, и вывод заново сдвинул бы само правило
  капитал      плотности RWA × общий множитель к RWA якоря; вычеты `deductions_anchor` — формулой
               книги на новых фактах (при квартальном календаре вычет второго норматива — с
               дивидендами очереди вычетов якоря, М§4.11); `gap_pp` — так, чтобы якорь воспроизводил
               оба норматива отчёта; ключ квартала якоря траектории `capital.n20.t2` — факт отчёта,
               если книга пишет этот ключ явно
  дивиденды    квартальный календарь: решения отчёта — строками истории дивидендов с днём решения
               (они закрывают свои кварталы прибыли на новом якоре); объявленное и не выплаченное —
               списком по периодам; записи реестра — в затравку нового якоря, пока их экс-дата впереди
               или их сумма стоит в списке. Годовой календарь: год объявленного дивиденда
  передача     режим `keep` (единственный в процедуре, М§15.2 п. 8): скаляры пути σ0_A, σ0_L, φ_A,
               φ_L прежней книги сохраняются, а цели A-N2, A-N3 и доли `nii.sigma0_split`,
               `nii.phi_split` пересчитываются на структуру нового якоря. `--transmission resolve`
               — только диагностика: цели прежние, ядро решает скаляры заново (скачок без новости
               целиком в строке «механика»); кандидат книги и фактов при этом не пишется
  уровень      у книги с ключом `nii.transmission.level_world` ключ цели ЧПМ — само суждение об уровне:
  маржи        стационарная маржа названного мира на составе баланса якоря. При сохранённых скалярах
               пути (спреды книг те же) ключ переписывается на состав баланса нового якоря — запись
               прежнего суждения, механика ≈ 0; прежнее и новое значение печатаются с разложением сдвига
               на маржу движка и мост. Гейт `checks.nim_stationary` в том же мире сверяет то же число:
               его цель идёт за ключом тем же сдвигом, и сам перенос якоря гейт не включает. Пересмотр
               уровня по новому окну фактов — решение новой версии книги, а не перенос
  ставки, ЧПМ  остаток процентного дохода (ближний сдвиг модели, прочие проценты отчёта) разнесён
               по книгам активов пропорционально их доходу — ставки якоря несут весь ЧПД; ключи
               спредов от ставок якоря выводятся заново; `regimes.near_nim_shift` — так, чтобы
               ожидаемый путь ЧПМ новой книги совпал с путём прежней на ожидаемом отчёте; ось по
               ключам ближнего пути получает ключи тех же лет новой траектории
  смена года   кризисные ключи (и множитель RWA режима) сдвигаются вместе с годом шока;
               `noncore.price_base_year`
  справочное   `valuation.next_report.period`
  оси          ось вида value по одному параметру — тем же пересчётом, что параметр. Ось-связка (вид bundle,
               М§10; концы — словари «путь → значение»): конец по пути, значение которого перенос пересчитал
               (цены якоря, плотности RWA, поправки нормативов, цели и доли передачи), идёт за центром тем же
               правилом; ключи словарей концов переименовываются вместе с годом шока; связка по пути,
               пересчитанному без правила для конца, и связка по ключам ближнего пути ЧПМ — отказ.
               Строки `valuation.reverse_dcf.refine_rows` (корень уточняется на полной полосе) названы
               ключами строк — путями осей обратного расчёта — и идут за ними; строка, ось которой
               снята, из перечня уходит с предупреждением
  история     у книги с миром-опорой κ-добавки (`credit.kappa_reference_world`) добавка к стоимости риска от
               реальной ставки закрываемого квартала у нового якоря равна нулю — до сетки реальная ставка у
               миров общая (М§4.6). Это свойство ядра, а не механика: кандидат и клетки на своём пути
               сверяются с прежней книгой без этой добавки, её цена — строка разложения «история до сетки»

ЧЕГО ПЕРЕНОС НЕ ТРОГАЕТ (суждения книги — называются в предупреждениях и ручных шагах):
  цели гейтов  цель и допуск `checks.cir_lt` и прочих гейтов-целей, `checks.nim_stationary` — кроме гейта в
               мире ключа уровня маржи (см. «уровень маржи»); число каждого на прежней книге и на кандидате
               печатается рядом с допуском, сдвиг маржи разложен на маржу движка и мост. У книги без ключа
               мира уровня ключ цели ЧПМ кандидата — запись прежних скаляров пути, а не вывод из цели
               стационарной маржи: порядок нового вывода — в предупреждении
  окно фактов  коридоры и поля `checks.window_backtest` (`cor`, `cir`, `nim`, `means`, `loans_share`) —
               запись окна прежней книги: упр. числа квартала отчёта печатаются рядом с краями окна,
               продлить ли окно и пересмотреть ли по нему уровни — решение новой версии книги
  выведенное  числа книги, выведенные на ядре: перечень — ключи шаблона книги с пометкой «ВЫВЕДЕНО НА
  на ядре      ЯДРЕ» (`derived_on_core`); названо, что из них перенос переписал на новый якорь
  варианты     подмены `valuation.reference_variants`: подмена по ключу, который перенос переписал
               (ключ уровня маржи, цель передачи, доли, ближний путь, ключи спредов от ставки якоря,
               поправки нормативов, ключи года шока), называется — значение остаётся записью на прежнем якоре
  премии       ключи премий роста к сектору и ось-связка по ним; ключ закрытого квартала называется

Коды возврата: 0 — сделано; 1 — отказ (отчёт не того квартала, негодные входы, календарь дивидендов
не представим фактами якоря, запись внутри репозитория вне var/, механика вне допуска) — причина в тексте.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.book import (BOOK_BALANCE_FIELDS, BOOK_PATH, FACTS_DIR, FVOCI_FIELDS,  # noqa: E402
                        FVTPL_BOND_FIELD, FV_LOANS_FIELD, LIQUIDITY, SECURITIES, Book, BookError,
                        Facts, FactsError, anchor_facts, book_from_dict, book_roles,
                        canonical_json, funds_books, load_book, load_facts)
from model.capital import growth_rule, rwa_anchor, rwa_weights  # noqa: E402
from model.checks import check_gates, check_invariants  # noqa: E402
from model.credit import bridge_from_facts  # noqa: E402
from model.dividends import DECLARED, THOUSAND, closed_through, history_dps, is_quarterly  # noqa: E402
from model.grid import (GridRun, LiveInputs, live_from_book, make_context,  # noqa: E402
                        regime_expectations, run_cell, run_grid)
from model.nii import solve_transmission  # noqa: E402
from model.paths import Trajectory, get_path, has_path  # noqa: E402
from model.timeline import (parse_period, period_str, quarter_days, quarter_end,  # noqa: E402
                            shift_quarter, to_date)
from model.worlds import BASE_WORLD  # noqa: E402

SCHEMA = "quarter-report/1"
TEMPLATE = BOOK_PATH.parent / "assumptions_template.yaml"
DEFAULT_OUT = ROOT / "var" / "reanchor"
WRITABLE = "var"                             # единственный каталог рабочей копии, куда инструмент пишет
OBS = "joint.regime_update.observations"
ANALYTICAL, NEUTRAL = "analytical", "macro_neutral"

TOP_REQUIRED = ("period", "balance", "interest", "dia", "pnl", "capital", "market", "mgmt")
TOP_OPTIONAL = ("schema", "as_of", "published", "source", "note", "shares", "dividend_decisions")
SECTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "balance": (("books", "loans_fvtpl", "fvoci", "fvtpl_bonds", "allowance", "other_assets",
                 "other_liabilities", "dividends_payable", "bv_common", "fvoci_reserve"),
                ("dividends_payable_year", "dividends_payable_declared", "other_assets_fixed", "at1", "nci",
                 "nonworking_money", "allowance_books")),
    "pnl": (("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt", "tax",
             "ni", "ni_shareholders"),
            ("misc_net", "oci_fvoci", "other_equity_movements", "estimated")),
    "capital": (("n20_0", "n20_pre_dividend", "n1_1_bank", "basel_cet1", "basel_rwa",
                 "bank_base_capital"), ("t2", "estimated", "estimate", "guarantees", "bank_own_funds", "bank_main_capital")),
    "market": (("ofz_curve", "key_avg"), ("price_index",)),
    "mgmt": (("nim", "cor"), ("cir",)),
    "shares": ((), ("issued_total", "issued_ordinary", "issued_preferred", "outstanding_total",
                    "outstanding_ordinary", "outstanding_preferred", "economic_treasury")),
}
NOT_NUMBERS = ("books", "ofz_curve", "n20_pre_dividend", "dividends_payable_year", "dividends_payable_declared",
               "estimated", "estimate", "nonworking_money", "allowance_books", "guarantees")
CURVE_NODES = ("1", "3", "5", "10")
# Квартальный календарь дивидендов (М§5.7): решение собрания и сумма к выплате — по кварталу прибыли.
DECISION_REQUIRED, DECISION_OPTIONAL = ("period", "dps", "decided_date"), ("record_date", "pay_date", "pool_declared")
DECLARED_KEYS = ("period", "amount")
# Слоты нормативов, которые отчёт может нести оценкой до выхода формы (М§3.3): слот отчёта → слот фактов.
ESTIMATE_SLOTS = {"n20_0": "n20_0", "n1_1_bank": "n1_1_bank"}
ESTIMATE_KEYS = ("bank_value", "spread", "spread_as_of")
CAPITAL_FORM = "capital-form/1"              # файл замены оценки нормативов фактом формы (без смены якоря)
CAPITAL_FORM_REQUIRED = ("period", "n20_0", "n1_1_bank", "basel_cet1", "basel_rwa", "bank_base_capital")
CAPITAL_FORM_OPTIONAL = ("schema", "as_of", "published", "source", "note", "t2", "n20_pre_dividend",
                         "bank_own_funds", "bank_main_capital")   # капитал нормативов банка — у фактов с его узлами
PNL_SUM = ("nii", "llp_debt_fa", "fees_net", "insurance_net", "noncore_net", "opex")   # + misc_net = pbt

# Допуски СВЕРОК файла отчёта и точности переноса — параметры проверки, не допущения модели.
BALANCE_CHECK = 5.0        # млрд ₽: активы против пассивов и капитала (округление строк отчёта)
PNL_CHECK = 0.5            # млрд ₽: pbt против суммы строк, ni против pbt + tax
RESIDUAL_SHARE = 0.10      # остаток «ЧПД − проценты книг» не больше этой доли ЧПД
BASIS_SANITY = 0.01        # упр. ЧПМ и CoR против величин движка через мост: 1 п.п.
MECHANICS_TOL = 0.001      # механика: стоимость клетки на своём пути — в пределах 0,1 % (М§15.2)
LEVEL_TOL = 1e-6           # ключ уровня маржи записан шестью знаками: стационарная маржа ядра равна ему с этой точностью
GAP_TOL = 1e-9             # якорь воспроизводит норматив отчёта с этой точностью
NEAR_TOL = 1e-6            # 0,0001 п.п. ЧПМ: хвост ближней калибровки меньше — не пишется
NEAR_RANGE = 2e-4          # разброс внутри года больше 0,02 п.п. — год пишется кварталами
SPREAD_RULE_TOL = 6e-6     # ключ спреда «от ставки якоря» в книге округлён до 5 знаков
SOLVE_STEP = 0.001         # шаг пробы целей A-N2 и A-N3 (решение аффинно — шаг не важен)
PASSES = 60                # не больше стольких проходов калибровки по прогону кандидата: проход доводит путь ЧПМ
#                            на квартал дальше там, где капитал связывает рост (ЧПД → капитал → рост → ЧПМ); обычно 3–12

# Реальные суммы книги в ценах якоря: индекс цен клетки стартует с единицы на якоре (М§4.7).
PRICE_INDEXED = ("noncore.result_real", "other.misc_net_real", "pnl.nci_real")   # pnl.nci_real — Р11-3, необязательный
NCI_REAL = "pnl.nci_real"
NONCORE = "noncore.result_real"
# anchor-ключи, состояние которых идёт с лагом: вывод заново сдвинул бы само правило.
FROZEN_ANCHORS = ("nii.retail_current_share.c_ref", "nii.retail_current_share.key_ref",
                  "volumes.wholesale_to_funds")
DEDUCTIONS = ("capital.n20.deductions_anchor", "capital.n11.deductions_anchor")
GAPS = (("capital.n20.gap_pp", "n20"), ("capital.n11.gap_pp", "n11"))
DENSITY = "capital.rwa.density"
FX = "capital.rwa.fx"
NIM_TARGET, T_TARGET = "nii.nim_lt_target_mgmt", "nii.transmission.target"
SPLIT, PHI_SPLIT = "nii.sigma0_split", "nii.phi_split"
TRANSMISSION_KEYS = (NIM_TARGET, T_TARGET, SPLIT, PHI_SPLIT)
SCALARS = ("σ0_A", "σ0_L", "φ_A", "φ_L")      # скаляры пути передачи ставки (М§4.5) — порядок `_sigmas`
KEEP, RESOLVE = "keep", "resolve"            # resolve — только диагностика (М§15.2 п. 8)
TRANSMISSION_MODES = (KEEP, RESOLVE)
NEAR = "regimes.near_nim_shift"
CRISIS_TRAJECTORIES = ("cor", "nim_shift", "loan_growth_adj", "rwa_density_mult")
T2 = "capital.n20.t2"                        # траектория инструментов капитала: ключ квартала якоря — факт (М§4.11)
T2_TOL = 1e-6                                # млрд ₽: ключ квартала якоря правится, если факт отчёта отличается
CATCH_UP = "capital.growth_constraint.catch_up_rate"
DIV_TOL = 1e-6                               # млрд ₽: сверки сумм дивидендов по периодам
BUNDLE = "bundle"                            # вид оси «связка» (М§10): концы — словари «путь → значение на конце»
# Корни путей, конец оси-связки по которым инструмент переносит вместе с центром; прочий путь связки, значение
# которого перенос якоря изменил, — отказ.
BUNDLE_CARRIED = PRICE_INDEXED + (DENSITY,) + tuple(path for path, _ in GAPS) + TRANSMISSION_KEYS
KAPPA_WORLD = "credit.kappa_reference_world"   # мир-опора κ-добавки (М§4.6): пути CoR режимов стоят в нём
LEVEL_WORLD = "nii.transmission.level_world"   # мир, стационарную маржу которого на составе якоря задаёт ключ цели
#                                                ЧПМ (М§4.5); нет ключа — мир-опора решателя передачи, как у образца
REFINE_ROWS = "valuation.reverse_dcf.refine_rows"   # строки обратного расчёта с уточнением корня на полной полосе
PREMIUM_FACTS = "valuation.reverse_dcf.premium_facts"   # ключи времени премий роста, названные книгой фактом
NIM_STATIONARY = "checks.nim_stationary"     # гейт стационарной маржи: {world, target, tolerance} — цель-суждение
GATE_TARGET = NIM_STATIONARY + ".target"     # у гейта в мире ключа уровня маржи — то же суждение, что ключ
CIR_LT = "checks.cir_lt"                     # гейт долгосрочного C/I: {target, tolerance, from_year, scope?}
MARKET_LAYER = "market_layer"                # область гейта C/I — слой «рыночные ставки как есть»
WINDOW_BACKTEST = "checks.window_backtest"   # включает узел уровней после фазы роста
WINDOW_CORRIDORS = (("cor", "CoR"), ("cir", "C/I"))   # коридоры гейта окна: наименьший и наибольший квартал окна
WINDOW_FIELDS = ("nim", "means", "loans_share")       # необязательные поля окна фактов: маржа, средние, доля кредитов
VARIANTS ="valuation.reference_variants"    # справочные варианты: [{id, title, overrides: {путь: значение}}]
WHOLESALE_SHARE = "checks.wholesale_share"   # коридор гейта доли оптового фондирования — по счёту ядра
PREMIUMS = ("volumes.funds_share_drift", "volumes.loan_share_drift")   # премии роста к сектору — суждения книги
# Пометка шаблона книги у ключа, выведенного на ядре (до вывода и после): перечень таких чисел — по самой книге.
DERIVED_MARKS = ("ВЫВЕДЕНО НА ЯДРЕ", "ВЫВОДИТСЯ НА ЯДРЕ")

# Ключи проходов ядра 1–5 (книга Совкомбанка; docs/REANCHOR.md §3.16). Каждый ключ, привязанный к якорю, переезжает
# своим правилом; ключ без привязки к якорю перенос не трогает.
BUYBACK = "dividends.buyback"                # выкуп по цене мира (М3, М§5.6): суммы по кварталам, цены закрытых кварталов
CASH = "volumes.cash_assets"                 # неработающие деньги (К8, Р6-1): путь доли от якоря к доле книги
CASH_LEAD = 2                                # Р7-6: квартал доли книги share_from = квартал якоря + 2
LINE_MIX = ("fees.volume_base", "other.insurance_volume_base")   # смеси баз строк (К2б): доли строки на якоре
LINE_SHARES = "opex.line_shares"             # доли базы расходов якоря за базами строк (К2)
BOOK_REL = "credit.book_relative"            # множители CoR по книгам (М7): нормировка на составе кредитов якоря
KAPPA = "credit.kappa"
GUAR = "capital.rwa.guarantees"              # RWA гарантий (К5): вес — вес риска × масштаб калибровки RWA
GUAR_WEIGHT = GUAR + ".weight"
FVOCI_RECOGNITION = "capital.n20.fvoci_recognition"
# Капитал нормативов банка по форме 0409123 (узлы фактов `capital.bank_own_funds`, `capital.bank_main_capital`): у
# книги с этими узлами вычеты якоря — правилом книги «капитал модели без вычетов − капитал формы» (шаг anchor листа
# вывода), а не формулой ядра по слотам CET1 и базового капитала.
OWN_FUNDS = ("bank_own_funds", "bank_main_capital")
CASH_NODES = ("total", "mandatory_reserves")  # узлы balance.nonworking_money, которые читает ядро (К8, Р6-1)
GUAR_KINDS = ("nonfinancial", "financial")   # номиналы гарантий якоря (К5): узлы capital.guarantees.<вид>
# Пути, конец оси-связки по которым идёт за центром правилом ключей проходов: вычеты якоря (доля признания фонда
# ССПСД), вес RWA гарантий (масштаб плотностей), доли смесей баз строк (состав нового якоря), κ (состав кредитов М7);
# пути CoR режимов добавляет перенос состава кредитов (`carry_book_cor`) — у книги с ключом М7.
BUNDLE_CARRIED = BUNDLE_CARRIED + DEDUCTIONS + (GUAR_WEIGHT, KAPPA) + tuple(f"{key}.mix" for key in LINE_MIX)

REASONS = (
    ("meta.", "якорь переходит на закрытый квартал"),
    (OBS, "факт квартала — наблюдение A-P2u с замороженными ожиданиями режимов; окно"),
    ("noncore.result_real", "цены якоря: индекс цен закрытого квартала"),
    ("other.misc_net_real", "цены якоря: индекс цен закрытого квартала"),
    ("noncore.price_base_year", "год цен — год якоря"),
    ("nii.retail_current_share.", "линия доли текущих счетов заморожена числами прежней книги"),
    ("volumes.wholesale_to_funds", "базовое оптовое фондирование заморожено числом прежней книги"),
    (DENSITY, "плотности RWA — общим множителем к RWA якоря"),
    (FX, "валютная доля RWA — на новом якоре (индекс курса стартует с единицы)"),
    ("capital.n20.deductions_anchor", "вычеты капитала — формулой книги на фактах якоря"),
    ("capital.n11.deductions_anchor", "вычеты капитала — формулой книги на фактах якоря"),
    ("capital.n20.gap_pp", "якорь воспроизводит Н20.0 отчёта"),
    ("capital.n11.gap_pp", "якорь воспроизводит второй норматив отчёта"),
    (T2, "ключ квартала якоря траектории инструментов капитала — факт отчёта"),
    ("nii.books.", "ключи спреда от ставок якоря (М§4.4)"),
    (NEAR, "ближняя калибровка ЧПМ: уровень уже в ставках якоря"),
    (NIM_TARGET, "A-N2 на структуре нового якоря при прежних σ0_A и σ0_L"),
    (T_TARGET, "A-N3 на структуре нового якоря при прежних φ_A и φ_L"),
    (SPLIT, "доля сдвига σ0 на активах на структуре нового якоря при прежних σ0_A и σ0_L"),
    (PHI_SPLIT, "доля сжатия φ на активах на структуре нового якоря при прежних φ_A и φ_L"),
    ("nii.sigma0_from", "год начала σ0 — не раньше первого прогнозного года"),
    ("regimes.", "кризис: ключи сдвинуты вместе с годом шока"),
    ("checks.m_crisis_vs_cbr", "кризис: ключи сдвинуты вместе с годом шока"),
    (GATE_TARGET, "цель гейта — то же суждение, что ключ уровня маржи: записана на составе нового якоря вместе с ним"),
    (REFINE_ROWS, "строки с уточнением корня названы ключами строк: идут за путями осей обратного расчёта"),
    ("valuation.next_report.period", "новый открытый квартал"),
    ("valuation.", "ось — в единицах параметра и на его ключах: пересчитана вместе с ним"),
)

Path_ = tuple                                # звенья пути: ключ словаря или ("name", имя) у элемента списка


class ReportError(ValueError):
    """Отчёт квартала или входы не годятся для перезаякоривания — объяснение в тексте."""


@dataclass
class Reanchored:
    """Кандидат и всё, что о нём надо знать до переноса в канон."""

    data: dict                               # кандидат машинной книги (anchor-ключи — строкой)
    book: Book
    facts: Facts
    period: str
    derived: dict
    changes: list[tuple[Path_, Any, Any]]    # (путь звеньями, было, стало); печать — `dotted(путь)`
    warnings: list[str] = field(default_factory=list)
    near: Any = None                         # ближняя калибровка ЧПМ (траектория книги)


# ------------------------------------------------------------------ периоды и пути


def next_period(p: str) -> str:
    return period_str(*shift_quarter(*parse_period(p), 1))


def period_end(p: str) -> dt.date:
    return quarter_end(*parse_period(p))


def pindex(p: str) -> int:
    y, q = parse_period(p)
    return 4 * y + q


def _get(tree: Any, dotted_path: str, default: Any = None) -> Any:
    node = tree
    for part in dotted_path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def _set(tree: dict, dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    node = tree
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _r(x: float, digits: int = 9) -> float:
    return round(float(x), digits)


def _rounded(tree: Any, digits: int = 9) -> Any:
    if isinstance(tree, Mapping):
        return {k: _rounded(v, digits) for k, v in tree.items()}
    if isinstance(tree, float):
        return round(tree, digits)
    return tree


def _plain(tree: Any) -> Any:
    """Дерево после JSON туда-обратно: ключи — строки, даты — строки."""
    return json.loads(json.dumps(tree, default=str))


def _sorted_traj(traj: Mapping) -> dict:
    """Ключи траектории по времени, `LT` и `LT_from` — в конце (как в книге)."""
    head = sorted((k for k in traj if str(k) not in ("LT", "LT_from")), key=lambda k: (int(str(k)[:4]), str(k)))
    return {**{k: traj[k] for k in head}, **{k: traj[k] for k in ("LT", "LT_from") if k in traj}}


# ------------------------------------------------------------------ файл отчёта


def read_report(path: Path) -> dict:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReportError(f"файл отчёта {path}: {exc}") from exc
    if not isinstance(report, dict):
        raise ReportError(f"файл отчёта {path}: ожидается объект JSON")
    return report


def _fraction(value: float, where: str, lo: float = -0.5, hi: float = 1.0) -> None:
    if not lo < value < hi:
        raise ReportError(f"отчёт: {where} = {value} — ожидается доля единицы (0,062 — это 6,2 %), "
                          "а не проценты")


def _check_shape(book: Book, facts: Facts, report: Mapping) -> None:
    unknown = sorted(set(report) - set(TOP_REQUIRED) - set(TOP_OPTIONAL))
    if unknown:
        raise ReportError(f"отчёт: незнакомые ключи {', '.join(unknown)} "
                          f"(известны: {', '.join(TOP_REQUIRED + TOP_OPTIONAL)})")
    missing = [k for k in TOP_REQUIRED if k not in report]
    if missing:
        raise ReportError(f"отчёт: нет обязательных ключей {', '.join(missing)}")
    if report.get("schema", SCHEMA) != SCHEMA:
        raise ReportError(f"отчёт: schema {report['schema']!r}, ожидается {SCHEMA!r}")
    period, first = str(report["period"]), str(book.get("meta.first_period"))
    try:
        parse_period(period)
    except BookError as exc:
        raise ReportError(f"отчёт: period — {exc}") from exc
    if period != first:
        raise ReportError(
            f"отчёт за {period}, а первый прогнозный квартал книги — {first}. Перезаякоривание "
            f"идёт по одному кварталу: сначала отчёт за {first}, потом следующий")
    if pindex(period) >= pindex(str(book.get("meta.last_period"))):
        raise ReportError(f"квартал {period} — последний прогнозный книги: горизонт кончился "
                          "(продление meta.last_period — решение книги)")
    if str(facts.plain("anchor", "period")) != str(book.get("meta.anchor_period")):
        raise ReportError(f"факты на якоре {facts.plain('anchor', 'period')}, книга — на "
                          f"{book.get('meta.anchor_period')}: книга и факты не пара")
    end = period_end(period)
    if "as_of" in report and str(report["as_of"]) != end.isoformat():
        raise ReportError(f"отчёт: as_of {report['as_of']} — не конец квартала {period} ({end})")
    if "published" in report:
        try:
            published = to_date(report["published"])
        except ValueError as exc:
            raise ReportError(f"отчёт: published {report['published']!r} — не дата") from exc
        if published <= end:
            raise ReportError(f"отчёт: published {published} не позже конца квартала {end}")
    for name, (required, optional) in SECTIONS.items():
        if name not in report:
            continue
        section = report[name]
        if not isinstance(section, Mapping):
            raise ReportError(f"отчёт: {name} — словарь")
        unknown = sorted(set(section) - set(required) - set(optional))
        if unknown:
            raise ReportError(f"отчёт: {name} — незнакомые ключи {', '.join(unknown)} "
                              f"(известны: {', '.join(required + optional)})")
        missing = [k for k in required if k not in section]
        if missing:
            raise ReportError(f"отчёт: {name} — нет ключей {', '.join(missing)}")
        for key, value in section.items():
            if key not in NOT_NUMBERS and not _num(value):
                raise ReportError(f"отчёт: {name}.{key} = {value!r} — ожидается число")
    names = tuple(book.get("nii.books"))
    for where, block in (("balance.books", report["balance"]["books"]), ("interest", report["interest"])):
        if not isinstance(block, Mapping) or set(block) != set(names):
            raise ReportError(f"отчёт: {where} — словарь по книгам {', '.join(names)} (все и только они)")
        for b, v in block.items():
            if not _num(v) or v < 0:
                raise ReportError(f"отчёт: {where}.{b} = {v!r} — ожидается неотрицательное число")
    if not _num(report["dia"]):
        raise ReportError(f"отчёт: dia = {report['dia']!r} — ожидается число")
    for where, flag in (("pnl.estimated", report["pnl"].get("estimated")),
                        ("capital.estimated", report["capital"].get("estimated"))):
        if flag is not None and not isinstance(flag, bool):
            raise ReportError(f"отчёт: {where} — true или false (значение стоит оценкой до выхода точного?)")
    _check_estimate(report["capital"])
    fixed = report["balance"].get("other_assets_fixed")
    if fixed is not None and not 0 <= fixed <= report["balance"]["other_assets"]:
        raise ReportError(f"отчёт: balance.other_assets_fixed = {fixed} — постоянная часть прочих активов: от нуля "
                          f"до balance.other_assets ({report['balance']['other_assets']})")
    held = (report.get("shares") or {}).get("economic_treasury")
    if held is not None and held < 0:
        raise ReportError(f"отчёт: shares.economic_treasury = {held} — число акций, не меньше нуля")
    _check_panel(book, facts, report)


def panel_needs(book: Book, facts: Facts) -> dict[str, tuple[str, ...]]:
    """Поля отчёта квартала, которые нужны ключам проходов ядра (docs/REANCHOR.md §2, §3.16): узлы фактов якоря, которые
    ядро читает словом `anchor`, и капитал нормативов банка, которым книга выводит вычеты. {раздел.поле: подполя}
    (у полей-чисел — пустой кортеж); книга без этих ключей — пусто, отчёт — прежней формы."""
    need: dict[str, tuple[str, ...]] = {}
    src = book.source if book.source is not None else book.data    # слово anchor — в источнике книги
    cash = _get(src, CASH)
    if isinstance(cash, Mapping):
        parts = ["total"] if cash.get("amount") == "anchor" else []
        if cash.get("share") not in (None, "anchor") and cash.get("reserves") == "anchor":
            parts.append("mandatory_reserves")
        if parts:
            need["balance.nonworking_money"] = tuple(parts)
    if _get(src, "credit.allowance_by_book.enabled") is True:
        need["balance.allowance_books"] = book_roles(book.get("nii.books")).loans
    guar = _get(src, GUAR)
    if isinstance(guar, Mapping) and guar.get("enabled") is True:
        kinds = tuple(k for k in GUAR_KINDS if (guar.get("notional") or {}).get(k) == "anchor")
        if kinds:
            need["capital.guarantees"] = kinds
    if all(facts.has("capital", slot) for slot in OWN_FUNDS):
        for slot in OWN_FUNDS:
            need[f"capital.{slot}"] = ()
    return need


def _check_panel(book: Book, facts: Facts, report: Mapping) -> None:
    """Поля ключей проходов ядра (docs/REANCHOR.md §2): нужные книге — обязательны; словари — ровно названные подполя,
    числа — не меньше нуля; ФОР — не больше неработающих денег, резерв книги — меньше её остатка."""
    need = panel_needs(book, facts)
    for where, parts in need.items():
        section, key = where.split(".")
        if key not in report[section]:
            raise ReportError(f"отчёт: нет {where} — его читает книга ({_panel_reason(where)}; docs/REANCHOR.md §2)")
    for where in ("balance.nonworking_money", "balance.allowance_books", "capital.guarantees"):
        section, key = where.split(".")
        block = report[section].get(key)
        if block is None:
            continue
        known = {"balance.nonworking_money": CASH_NODES, "capital.guarantees": GUAR_KINDS,
                 "balance.allowance_books": book_roles(book.get("nii.books")).loans}[where]
        if not isinstance(block, Mapping) or not set(block) <= set(known) or not set(need.get(where, ())) <= set(block):
            raise ReportError(f"отчёт: {where} — словарь {{{', '.join(known)}}}"
                              + (f", обязательны {', '.join(need[where])}" if need.get(where) else ""))
        for k, v in block.items():
            if not _num(v) or v < 0:
                raise ReportError(f"отчёт: {where}.{k} = {v!r} — млрд ₽, не меньше нуля")
    cash = report["balance"].get("nonworking_money") or {}
    if "mandatory_reserves" in cash and "total" in cash and cash["mandatory_reserves"] > cash["total"]:
        raise ReportError(f"отчёт: balance.nonworking_money.mandatory_reserves = {cash['mandatory_reserves']} больше "
                          f"неработающих денег total = {cash['total']} (ФОР — их часть)")
    for b, v in (report["balance"].get("allowance_books") or {}).items():
        if v >= report["balance"]["books"][b]:
            raise ReportError(f"отчёт: balance.allowance_books.{b} = {v} не меньше остатка книги {b} "
                              f"{report['balance']['books'][b]}")
    for slot in OWN_FUNDS:
        if slot in report["capital"] and not report["capital"][slot] > 0:
            raise ReportError(f"отчёт: capital.{slot} = {report['capital'][slot]} — капитал норматива банка, больше нуля")


def _panel_reason(where: str) -> str:
    return {"balance.nonworking_money": f"{CASH}: amount или reserves — anchor (К8, Р6-1)",
            "balance.allowance_books": "credit.allowance_by_book.enabled (К7)",
            "capital.guarantees": f"{GUAR}.notional — anchor (К5)",
            }.get(where, "у фактов якоря есть узлы капитала норматива банка capital.bank_own_funds и "
                         "capital.bank_main_capital — вычеты выводятся правилом книги")


def _check_estimate(capital: Mapping) -> None:
    """Блок оценки нормативов есть тогда и только тогда, когда нормативы стоят оценкой (М§3.3)."""
    estimated, block = capital.get("estimated") is True, capital.get("estimate")
    if estimated != (block is not None):
        raise ReportError("отчёт: capital.estimate — блок оценки нормативов: он есть тогда и только тогда, когда "
                          "capital.estimated: true")
    if block is None:
        return
    if not isinstance(block, Mapping) or set(block) != set(ESTIMATE_SLOTS):
        raise ReportError(f"отчёт: capital.estimate — словарь по слотам {', '.join(ESTIMATE_SLOTS)} (все и только они)")
    for slot, spec in block.items():
        where = f"capital.estimate.{slot}"
        if not isinstance(spec, Mapping) or set(spec) != set(ESTIMATE_KEYS):
            raise ReportError(f"отчёт: {where} — ключи {', '.join(ESTIMATE_KEYS)} (все и только они)")
        for key in ESTIMATE_KEYS[:2]:
            if not _num(spec[key]):
                raise ReportError(f"отчёт: {where}.{key} = {spec[key]!r} — ожидается число")
            _fraction(float(spec[key]), f"{where}.{key}")
        _iso(spec["spread_as_of"], f"{where}.spread_as_of")


def _iso(value: Any, where: str) -> dt.date:
    try:
        return to_date(value)
    except (ValueError, TypeError) as exc:
        raise ReportError(f"отчёт: {where} = {value!r} — не дата ГГГГ-ММ-ДД") from exc


def _check_dividends(book: Book, facts: Facts, report: Mapping) -> None:
    """Дивиденды по периодам (квартальный календарь, М§5.7): решения собраний закрываемого квартала и
    объявленное, но не выплаченное на его конец. Громкий отказ на всём, что ядро не примет."""
    period = str(report["period"])
    end = period_end(period)
    old_date = to_date(book.get("meta.facts_date"))
    decisions = report.get("dividend_decisions") or []
    declared = report["balance"].get("dividends_payable_declared") or []
    if not isinstance(decisions, list) or not isinstance(declared, list):
        raise ReportError("отчёт: dividend_decisions и balance.dividends_payable_declared — списки")
    closing: set[str] = set()
    for i, row in enumerate(decisions):
        where = f"dividend_decisions.{i}"
        if not isinstance(row, Mapping):
            raise ReportError(f"отчёт: {where} — словарь {{period, dps, decided_date}}")
        unknown = sorted(set(row) - set(DECISION_REQUIRED) - set(DECISION_OPTIONAL))
        missing = [k for k in DECISION_REQUIRED if k not in row]
        if unknown or missing:
            raise ReportError(f"отчёт: {where} — " + "; ".join(x for x in (
                f"незнакомые ключи {', '.join(unknown)}" if unknown else "",
                f"нет ключей {', '.join(missing)}" if missing else "") if x)
                + f" (известны: {', '.join(DECISION_REQUIRED + DECISION_OPTIONAL)})")
        try:
            y, q = parse_period(str(row["period"]))
        except BookError as exc:
            raise ReportError(f"отчёт: {where}.period — {exc}") from exc
        if pindex(str(row["period"])) > pindex(period):
            raise ReportError(f"отчёт: {where}.period {row['period']} — квартал прибыли позже закрываемого {period}")
        if str(row["period"]) in closing:
            raise ReportError(f"отчёт: {where}.period {row['period']} повторяется")
        closing.add(str(row["period"]))
        if not _num(row["dps"]) or row["dps"] < 0:
            raise ReportError(f"отчёт: {where}.dps = {row['dps']!r} — ₽ на акцию, не меньше нуля")
        if "pool_declared" in row and (not _num(row["pool_declared"]) or row["pool_declared"] < 0):
            raise ReportError(f"отчёт: {where}.pool_declared = {row['pool_declared']!r} — млрд ₽, не меньше нуля")
        decided = _iso(row["decided_date"], f"{where}.decided_date")
        if not old_date < decided <= end:
            raise ReportError(
                f"отчёт: {where}.decided_date {decided} — решение собрания закрываемого квартала: позже прежней "
                f"даты фактов {old_date} и не позже конца квартала {end} (более раннее решение — сначала правка "
                "фактов прежнего якоря, более позднее — запись реестра нового)")
        for key in ("record_date", "pay_date"):
            if row.get(key) is not None and _iso(row[key], f"{where}.{key}") < decided:
                raise ReportError(f"отчёт: {where}.{key} {row[key]} раньше дня решения {decided}")
    known = {str(_fact(r.get("period"))) for r in facts.file("dividends").get("history") or []
             if _fact(r.get("decided_date")) and to_date(_fact(r["decided_date"])) <= end}
    seen: set[str] = set()
    total = 0.0
    for i, item in enumerate(declared):
        where = f"balance.dividends_payable_declared.{i}"
        if not isinstance(item, Mapping) or set(item) != set(DECLARED_KEYS):
            raise ReportError(f"отчёт: {where} — словарь {{period, amount}}")
        try:
            parse_period(str(item["period"]))
        except BookError as exc:
            raise ReportError(f"отчёт: {where}.period — {exc}") from exc
        if str(item["period"]) in seen:
            raise ReportError(f"отчёт: {where}.period {item['period']} повторяется")
        seen.add(str(item["period"]))
        if not _num(item["amount"]) or item["amount"] < 0:
            raise ReportError(f"отчёт: {where}.amount = {item['amount']!r} — млрд ₽, не меньше нуля")
        if str(item["period"]) not in closing | known:
            raise ReportError(
                f"отчёт: {where}.period {item['period']} — объявленный дивиденд без решения: нет ни строки "
                "dividend_decisions, ни строки истории дивидендов прежних фактов с днём решения не позже конца "
                "квартала")
        total += float(item["amount"])
    if total > report["balance"]["dividends_payable"] + DIV_TOL:
        raise ReportError(f"отчёт: сумма balance.dividends_payable_declared {total:g} больше остатка "
                          f"balance.dividends_payable {report['balance']['dividends_payable']:g}")


def _fact(x: Any) -> Any:
    """Значение поля фактов: узел {v, …} или голое значение."""
    return x.get("v") if isinstance(x, Mapping) and "v" in x else x


def check_report(book: Book, facts: Facts, report: Mapping) -> None:
    """Громкий отказ на всём, что ядро прочло бы молча не так."""
    _check_shape(book, facts, report)
    B, P, C, M, G = (report[k] for k in ("balance", "pnl", "capital", "market", "mgmt"))
    quarterly = is_quarterly(book)
    if quarterly:
        _check_dividends(book, facts, report)
    if not isinstance(C["n20_pre_dividend"], bool):
        raise ReportError("отчёт: capital.n20_pre_dividend — true или false (норматив до вычета "
                          "объявленного дивиденда из регуляторного капитала?)")
    curve = M["ofz_curve"]
    if not isinstance(curve, Mapping) or set(map(str, curve)) != set(CURVE_NODES):
        raise ReportError(f"отчёт: market.ofz_curve — узлы {', '.join(CURVE_NODES)} лет")
    for node, v in curve.items():
        if not _num(v):
            raise ReportError(f"отчёт: market.ofz_curve.{node} = {v!r} — ожидается число")
        _fraction(float(v), f"market.ofz_curve.{node}", 0.0)
    for where, value in (("market.key_avg", M["key_avg"]), ("mgmt.nim", G["nim"]), ("mgmt.cor", G["cor"]),
                         ("capital.n20_0", C["n20_0"]), ("capital.n1_1_bank", C["n1_1_bank"])):
        _fraction(float(value), where)
    if "cir" in G:
        _fraction(float(G["cir"]), "mgmt.cir", 0.0)
    if "price_index" in M and not 0.8 < float(M["price_index"]) < 1.5:
        raise ReportError(f"отчёт: market.price_index = {M['price_index']} — индекс цен квартала "
                          "(конец к началу, около 1,015), а не темп")
    if B["dividends_payable"] < 0 or B["allowance"] < 0:
        raise ReportError("отчёт: balance.dividends_payable и balance.allowance — величинами (≥ 0)")
    year = B.get("dividends_payable_year")
    if not quarterly and B["dividends_payable"] > 0 and (isinstance(year, bool) or not isinstance(year, int)):
        raise ReportError("отчёт: balance.dividends_payable > 0 — нужен dividends_payable_year "
                          "(год прибыли объявленного дивиденда)")
    if P["opex"] >= 0:
        raise ReportError(f"отчёт: pnl.opex = {P['opex']} — расходы со знаком минус, как в отчётности")
    for key in ("basel_cet1", "basel_rwa", "bank_base_capital"):
        if C[key] <= 0:
            raise ReportError(f"отчёт: capital.{key} = {C[key]} — ожидается положительное число")
    # тождества
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    bal = B["books"]
    at1, nci = float(B.get("at1", af.at1)), float(B.get("nci", af.nci))
    assets = sum(bal[b] for b in roles.assets) - B["allowance"] + B["other_assets"]
    claims = (sum(bal[b] for b in roles.liabilities) + B["other_liabilities"] + B["dividends_payable"]
              + B["bv_common"] + at1 + nci)
    if abs(assets - claims) > BALANCE_CHECK:
        raise ReportError(
            f"отчёт: баланс не сходится — активы {assets:.1f} (книги активов − резерв + прочие активы) "
            f"против пассивов и капитала {claims:.1f} (пассивы + прочие + дивиденды к выплате + "
            f"капитал + AT1 + неконтролирующие): разница {assets - claims:+.1f} млрд ₽ "
            f"(допуск {BALANCE_CHECK})")
    if B["loans_fvtpl"] < 0 or B["loans_fvtpl"] > (bal[af.fv_book] if af.fv_book else sum(bal[b] for b in roles.loans)):
        raise ReportError("отчёт: balance.loans_fvtpl — кредиты по СС внутри своей книги"
                          + (f" ({af.fv_book})" if af.fv_book else "") + ", не больше её остатка")
    if B["fvoci"] < 0 or B["fvtpl_bonds"] < 0 or B["fvoci"] + B["fvtpl_bonds"] > bal[SECURITIES] + BALANCE_CHECK:
        raise ReportError("отчёт: balance.fvoci и balance.fvtpl_bonds — части книги долговых бумаг "
                          "(неотрицательные, в сумме не больше её остатка)")
    lines = sum(P[k] for k in PNL_SUM)
    if "misc_net" in P and abs(lines + P["misc_net"] - P["pbt"]) > PNL_CHECK:
        raise ReportError(
            f"отчёт: pbt {P['pbt']} ≠ сумме строк {lines + P['misc_net']:.2f} (nii + llp_debt_fa + "
            "fees_net + insurance_net + noncore_net + opex + misc_net) — расходы со знаком минус?")
    if abs(P["pbt"] + P["tax"] - P["ni"]) > PNL_CHECK:
        raise ReportError(f"отчёт: ni {P['ni']} ≠ pbt + tax = {P['pbt'] + P['tax']:.2f} "
                          "(налог — со знаком минус)")
    income = sum(report["interest"][b] for b in roles.assets)
    booked = income - sum(report["interest"][b] for b in roles.liabilities) - abs(float(report["dia"]))
    if not income or abs(P["nii"] - booked) > RESIDUAL_SHARE * abs(P["nii"]):
        raise ReportError(
            f"отчёт: проценты книг дают {booked:.1f}, а pnl.nii — {P['nii']}: остаток "
            f"{P['nii'] - booked:+.1f} больше {RESIDUAL_SHARE:.0%} ЧПД — проценты за квартал или "
            "нарастающим итогом? все ли книги?")
    # базис: величины движка из строк отчёта против управленческих через мост
    bridge = bridge_from_facts(facts)
    eng = engine_ratios(book, facts, report)
    for name, got, mgmt, back in (("ЧПМ", eng["nim"], G["nim"], bridge.to_mgmt_nim),
                                  ("CoR", eng["cor"], G["cor"], bridge.to_mgmt_cor)):
        if abs(back(got) - mgmt) > BASIS_SANITY:
            raise ReportError(
                f"отчёт: {name} движка из строк отчёта {got:.4%} через мост — {back(got):.4%} упр., "
                f"а mgmt — {mgmt:.4%}: расхождение больше {BASIS_SANITY * 100:.0f} п.п. — ОПУ за "
                "квартал или нарастающим итогом? доля или проценты?")


def engine_ratios(book: Book, facts: Facts, report: Mapping) -> dict[str, float]:
    """ЧПМ, CoR и C/I движка закрытого квартала из строк отчёта (М§0.3, §4.6; средние остатки —
    начало и конец квартала, как в фактах)."""
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    B, P = report["balance"], report["pnl"]
    days = quarter_days(*parse_period(str(report["period"])))
    bal = B["books"]
    iea_avg = sum(af.balances[b] + bal[b] for b in roles.assets) / 2
    # кредиты по СС вычитаются, только когда ядро ведёт их отдельной частью книги (М§4.6); иначе знаменатель CoR —
    # сумма кредитных книг, а balance.loans_fvtpl отчёта — справка
    fv = af.fv_loans + B["loans_fvtpl"] if af.fv_book else 0.0
    loans_avg = (sum(af.balances[b] + bal[b] for b in roles.loans) - fv) / 2
    misc = P["misc_net"] if "misc_net" in P else P["pbt"] - sum(P[k] for k in PNL_SUM)
    income = P["nii"] + P["fees_net"] + P["insurance_net"] + misc
    return {"nim": P["nii"] / iea_avg * 365 / days, "cor": -P["llp_debt_fa"] / loans_avg * 365 / days,
            "cir": -P["opex"] / income if income else float("nan"),
            "iea_avg": iea_avg, "loans_ac_avg": loans_avg, "misc_net": misc, "days": days}


# ------------------------------------------------------------------ факты нового якоря


def _node(value: Any, calc: str) -> dict:
    return {"v": value, "calc": calc}


def _put(tree: dict, dotted_path: str, value: Any, calc: str, touched: set[str]) -> None:
    _set(tree, dotted_path, _node(value, calc))
    touched.add(dotted_path)


def _spread_total(tree: dict, fields: Sequence[str], total: float, calc: str, touched: set[str]) -> None:
    """`total` по узлам `fields` — в пропорции прежнего якоря (`null` остаётся `null`)."""
    old = {f: _get(tree, f + ".v") for f in fields}
    live = [f for f in fields if old[f] is not None]
    base = sum(float(old[f]) for f in live)
    for f in fields:
        touched.add(f)
        if old[f] is not None:
            share = float(old[f]) / base if base else 1.0 / len(live)
            _set(tree, f, _node(_r(total * share, 6), calc + " (разбивка — в пропорции прежнего якоря)"))


def _null_untouched(tree: Any, touched: set[str], keep: Sequence[str], calc: str, prefix: str = "") -> None:
    """Узлы, которых отчёт не назвал, — `null`: прежнее число под новой датой было бы ложью."""
    if not isinstance(tree, dict):
        return
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if any(path == k or path.startswith(k + ".") for k in keep):
            continue
        if isinstance(value, dict) and "v" in value and ("src" in value or "calc" in value):
            if path not in touched:
                tree[key] = _node(None, calc)
        else:
            _null_untouched(value, touched, keep, calc, path)


def _add_period_row(holder: dict, key: str, period: str, row: dict) -> None:
    """Строка периода в словарь {период: строка} или список [{period, …}] — как лежит в файле."""
    rows = holder.get(key)
    if isinstance(rows, dict):
        rows[period] = row
    elif isinstance(rows, list):
        rows[:] = [r for r in rows if not (isinstance(r, dict) and r.get("period") == period)]
        rows.append({"period": period, **row})


def _node_keys(rows: Any) -> set[str]:
    """Ключи узлов, которые несут строки по периодам (словарь {период: строка} или список строк)."""
    items = rows.values() if isinstance(rows, dict) else rows or []
    return {k for r in items if isinstance(r, dict) for k, v in r.items() if isinstance(v, dict) and "v" in v}


def _row_of(rows: Any, period: str) -> dict | None:
    """Строка периода из словаря {период: строка} или списка [{period, …}]; нет — None."""
    if isinstance(rows, dict):
        row = rows.get(period)
    else:
        row = next((r for r in rows or [] if isinstance(r, dict) and r.get("period") == period), None)
    return row if isinstance(row, dict) else None


def _funds_books(rows: Any, old_period: str, old_bal: Mapping[str, float], roles: Any) -> tuple[str, ...]:
    """Книги, которые узел `funds` строк истории баланса суммирует, — как в прежнем файле: все средства клиентов
    ядра или они без книг, которые строки несут отдельным узлом (книга страховых обязательств у книги с ведомой
    книгой К6). Решает строка прежнего якоря: чья сумма равна её узлу `funds`; нет строки или узла — все средства."""
    split = tuple(b for b in roles.funds if b in _node_keys(rows))
    choices = (tuple(roles.funds), tuple(b for b in roles.funds if b not in split))
    got = _get(_row_of(rows, old_period) or {}, "funds.v")
    if _num(got):
        for books in choices:
            if abs(sum(old_bal[b] for b in books) - float(got)) <= 1e-3:
                return books
    return choices[0]


def _check_funds_books(rows: Any, old_period: str, old_bal: Mapping[str, float], roles: Any,
                       in_funds: Sequence[str]) -> None:
    """Сверка состава узла `funds` строк истории: книги решает ключ `volumes.funds_scope` (`model.book.funds_books`,
    Р11-2); прежний файл — второе прочтение. Если узел `funds` строки прежнего якоря равен сумме состава, который
    выводит `_funds_books`, и не равен сумме состава по ключу — ключ и факты истории расходятся: перенос
    остановится (новая строка легла бы базой другого состава, ряд роста объёма г/г сломался бы)."""
    got = _get(_row_of(rows, old_period) or {}, "funds.v")
    if not _num(got):
        return
    was = _funds_books(rows, old_period, old_bal, roles)
    key_sum, was_sum = sum(old_bal[b] for b in in_funds), sum(old_bal[b] for b in was)
    if abs(key_sum - float(got)) > 1e-3 and abs(was_sum - float(got)) <= 1e-3:
        raise ReportError(f"история баланса: узел funds строки {old_period} ({float(got):.3f}) — сумма книг "
                          f"{', '.join(was)}, а ключ volumes.funds_scope книги даёт {', '.join(in_funds)} "
                          f"({key_sum:.3f}); состав базы средств строк истории и ключ расходятся")


def _complete_history_row(bal: dict, period: str, balances: Mapping[str, float], split: Sequence[str],
                          calc: str) -> None:
    """Строка истории баланса `period` с остатками книг, которые несут прочие строки: словарь `books` (все книги ЧПД,
    если его несёт хоть одна строка) и узлы-книги верхнего уровня (`split`). Узел, который строка уже несёт, не
    трогается (факт прежнего файла)."""
    rows = bal.get("history")
    row = _row_of(rows, period)
    if row is None:
        return
    items = rows.values() if isinstance(rows, dict) else rows or []
    if any(isinstance(r, dict) and isinstance(r.get("books"), dict) for r in items):
        have = row.setdefault("books", {})
        for b, value in balances.items():
            if not _num(_get(have, f"{b}.v")):
                have[b] = _node(_r(value, 6), calc)
    for b in split:
        if not _num(_get(row, f"{b}.v")):
            row[b] = _node(_r(balances[b], 6), calc)


def _shifted(old_day: Any, old_end: dt.date, end: dt.date) -> str:
    """Дата блока на новом якоре — с тем же сдвигом от конца квартала, что в прежнем файле (форма на 1-е число
    после квартала остаётся формой на 1-е число)."""
    try:
        gap = (to_date(old_day) - old_end).days
    except (ValueError, TypeError):
        gap = 0
    return (end + dt.timedelta(days=gap if 0 <= gap <= 31 else 0)).isoformat()


def facts_after(book: Book, facts: Facts, report: Mapping, *, update_bridge: bool = True) -> Facts:
    """Факты нового якоря из отчёта квартала: те же файлы, узлы якоря — из отчёта.

    Форма файлов — как лежит в прежних фактах: остатки книг прямыми узлами `balance.books.<b>` или суммой
    строк; строки истории (баланс, капитал, мосты) несут те же ключи, что прежние строки. Ставки якоря несут
    весь ЧПД: остаток `nii − (проценты книг − взносы АСВ)` разнесён по книгам активов пропорционально их
    процентному доходу (М§15.2 п. 4). Упр. факты квартала входят в историю моста упр. ↔ движок (отчётные
    кварталы года якоря ядро берёт оттуда, М§4.6); среднее моста продлевается закрытым кварталом при
    `update_bridge`. При квартальном календаре дивидендов решения закрываемого квартала становятся строками
    истории дивидендов, объявленное и не выплаченное — списком по периодам, записи реестра переходят в
    затравку нового якоря (М§15.2 п. 9)."""
    period = str(report["period"])
    end = period_end(period)
    tag = f"reanchor: отчёт {period}" + (f" ({report['source']})" if report.get("source") else "")
    absent = f"reanchor: в отчёте {period} нет — пересобрать build_facts.py --anchor {period}"
    books = book.get("nii.books")
    roles = book_roles(books)
    old = anchor_facts(facts, books)
    old_period = str(facts.plain("anchor", "period"))
    old_end = period_end(old_period)
    quarterly = is_quarterly(book)
    files = copy.deepcopy(dict(facts.files))
    B, P, C, M, G = (report[k] for k in ("balance", "pnl", "capital", "market", "mgmt"))
    eng = engine_ratios(book, facts, report)
    days = int(eng["days"])
    at1, nci = float(B.get("at1", old.at1)), float(B.get("nci", old.nci))

    files["anchor"]["as_of"] = end.isoformat()
    files["anchor"]["period"] = period

    # --- баланс
    bal = files["balance"]
    touched: set[str] = set()
    bal["as_of"] = end.isoformat()
    direct = bal.get("books") if isinstance(bal.get("books"), dict) else None
    for name in roles.names:
        total = float(B["books"][name])
        if direct is not None and name in direct:
            _put(bal, f"books.{name}", total, tag, touched)
            continue
        fields = list(BOOK_BALANCE_FIELDS[name])
        if FV_LOANS_FIELD in fields:
            _put(bal, FV_LOANS_FIELD, float(B["loans_fvtpl"]), tag, touched)
            fields.remove(FV_LOANS_FIELD)
            total -= float(B["loans_fvtpl"])
        if name == SECURITIES:
            _spread_total(bal, list(FVOCI_FIELDS), float(B["fvoci"]), tag, touched)
            _put(bal, FVTPL_BOND_FIELD, float(B["fvtpl_bonds"]), tag, touched)
            fields = [f for f in fields if f not in FVOCI_FIELDS and f != FVTPL_BOND_FIELD]
            total -= float(B["fvoci"]) + float(B["fvtpl_bonds"])
        _spread_total(bal, fields, total, tag, touched)
    if direct is not None and SECURITIES in direct:
        # прямые книги: части книги долговых бумаг и кредиты по СС ядро и выпуск читают своими узлами
        _spread_total(bal, list(FVOCI_FIELDS), float(B["fvoci"]), tag, touched)
        _put(bal, FVTPL_BOND_FIELD, float(B["fvtpl_bonds"]), tag, touched)
    if FV_LOANS_FIELD not in touched and isinstance(bal.get(FV_LOANS_FIELD), dict):
        _put(bal, FV_LOANS_FIELD, float(B["loans_fvtpl"]), tag, touched)
    sign = -1.0 if (_get(bal, "allowance_ac.v") or 0.0) < 0 else 1.0     # знак — как в прежнем файле
    _put(bal, "allowance_ac", sign * float(B["allowance"]), tag, touched)
    for key, name in (("other_assets", "other_assets"), ("other_liabilities", "other_liabilities"),
                      ("dividends_payable", "dividends_payable"), ("equity.bv_common", "bv_common")):
        _put(bal, key, float(B[name]), tag, touched)
    _put(bal, "equity.at1", at1, tag, touched)
    _put(bal, "equity.nci", nci, tag, touched)
    # ключи проходов ядра: неработающие деньги и ФОР (К8, Р6-1), резерв по кредитным книгам (К7) — узлы, которые
    # ядро читает словом anchor (docs/REANCHOR.md §3.16)
    for key, value in (B.get("nonworking_money") or {}).items():
        _put(bal, f"nonworking_money.{key}", float(value), tag, touched)
    for b, value in (B.get("allowance_books") or {}).items():
        _put(bal, f"allowance_books.{b}", float(value), tag, touched)
    if "other_assets_fixed" in B:
        _put(bal, "other_assets_fixed", float(B["other_assets_fixed"]), tag, touched)
    elif _get(bal, "other_assets_fixed.v") is not None:
        _put(bal, "other_assets_fixed", float(bal["other_assets_fixed"]["v"]),
             f"reanchor: в отчёте {period} нет — значение прежнего якоря {old_period}", touched)
    if quarterly:
        bal["dividends_payable_declared"] = [{"period": str(x["period"]), "amount": _node(float(x["amount"]), tag)}
                                             for x in B.get("dividends_payable_declared") or []]
    elif B.get("dividends_payable_year") is not None:
        bal["dividends_payable_year"] = int(B["dividends_payable_year"])
    if B.get("dividends_payable_year") is None and float(B["dividends_payable"]) == 0:
        # год прибыли без суммы к выплате не переносится (как у сборщика фактов, ops/tools/build_facts.py --expected и
        # сборка из листов): у прежнего якоря он называл выплаченный теперь дивиденд; ядро при нулевой сумме его не читает
        bal.pop("dividends_payable_year", None)
    loans = sum(float(B["books"][b]) for b in roles.loans)
    # Р11-2 (решения ведущего № 11; поток fix11 — спящий экземпляр слова funds): база funds строк истории баланса — книги слова
    # «средства клиентов» балансовой механики по ключу volumes.funds_scope (model.book.funds_books — одна функция с ядром: clients —
    # без ведомых книг К6), как узел funds фактов истории (на 2026-06-30 — 3 236,582 без книги страховых 171,11). Было —
    # roles.funds (с К6): при перезаякоривании на 3К2026 строки истории легли бы базой с книгой страховых
    in_funds = funds_books(roles, book)
    funds = sum(float(B["books"][b]) for b in in_funds)
    iea = sum(float(B["books"][b]) for b in roles.assets)
    fv_part = float(B["loans_fvtpl"]) if old.fv_book else 0.0            # часть книги, которую ядро ведёт по СС
    assets = iea - float(B["allowance"]) + float(B["other_assets"])
    totals = {"equity.total": B["bv_common"] + at1 + nci, "equity.shareholders": B["bv_common"] + at1,
              "equity.fvoci_reserve": B["fvoci_reserve"], "loans_ac_gross.total": loans - B["loans_fvtpl"],
              "securities.debt_total": B["books"][SECURITIES], "liquidity.total": B["books"][LIQUIDITY],
              "total_assets": assets, "total_liabilities": assets - (B["bv_common"] + at1 + nci), "iea": iea}
    for key, value in totals.items():
        if isinstance(_get(bal, key), dict):
            _put(bal, key, _r(value, 6), tag, touched)
    if parse_period(period)[0] != parse_period(old_period)[0] and isinstance(bal.get("prev_year_end"), dict):
        prev = bal["prev_year_end"]            # новый год якоря: концы прошлого года — прежний якорь
        if "as_of" in prev:
            prev["as_of"] = old_end.isoformat()
        for seg in ("corporate", "retail"):
            total = sum(old.balances[b] for b in roles.loans if books[b]["cor_segment"] == seg)
            prev[f"loans_{seg}"] = _node(_r(total, 6), f"reanchor: книги сегмента на конец {old_period}")
    _null_untouched(bal, touched, ("history", "prev_year_end"), absent)
    rows = bal.get("history")
    carried = _node_keys(rows) & {"loans", "funds"}      # базы объёма: рост объёма г/г читает их с концов кварталов (М§4.7)
    listed = set(rows) if isinstance(rows, dict) else {r.get("period") for r in rows or [] if isinstance(r, dict)}
    old_bal = {b: float(old.balances[b]) for b in roles.names}
    new_bal = {b: float(B["books"][b]) for b in roles.names}
    # книги узла funds строк истории решает ключ volumes.funds_scope (in_funds выше — funds_books ядра, Р11-2); правило
    # «как в прежнем файле» — сверка: строка прежнего якоря, чей узел funds сложен из другого состава книг, — стоп
    _check_funds_books(rows, old_period, old_bal, roles, in_funds)
    split = sorted(_node_keys(rows) & set(roles.names))         # книги, которые строки несут отдельным узлом
    if rows is not None and old_period not in listed:
        # конец прежнего якоря уходит в историю: по концам отчётных кварталов ядро взвешивает год якоря (М§4.6)
        was = f"reanchor: состояние прежнего якоря {old_period}"
        old_loans = sum(old.balances[b] for b in roles.loans)
        bases = {"loans": old_loans, "funds": sum(old_bal[b] for b in in_funds)}
        _add_period_row(bal, "history", old_period, {
            "date": old_end.isoformat(),
            "loans_ac_gross": _node(_r(old_loans - old.fv_loans, 6), was),
            "bv_common": _node(float(old.bv), was),
            "iea": _node(_r(sum(old.balances[b] for b in roles.assets), 6), was),
            **{k: _node(_r(bases[k], 6), was) for k in sorted(carried)}})
    if rows is not None:
        # остатки книг на конце прежнего якоря (база расходов М13 и базы строк К2 — по книгам, М§4.7): у строки якоря,
        # которую прежние факты несли без них (на якоре ядро читает остатки якоря), — дописываются
        _complete_history_row(bal, old_period, old_bal, split, f"reanchor: остатки прежнего якоря {old_period}")
    bases = {"loans": loans, "funds": funds}                     # funds — книги in_funds на новом якоре (выше)
    _add_period_row(bal, "history", period, {
        "date": end.isoformat(), "loans_ac_gross": _node(_r(loans - fv_part, 6), tag),
        "allowance_ac": _node(float(B["allowance"]), tag), "loans_fvtpl": _node(float(B["loans_fvtpl"]), tag),
        "bv_common": _node(float(B["bv_common"]), tag), "iea": _node(_r(iea, 6), tag),
        "total_assets": _node(_r(assets, 6), tag),
        **{k: _node(_r(bases[k], 6), tag) for k in sorted(carried)}})
    if rows is not None:
        _complete_history_row(bal, period, new_bal, split, tag)

    # --- книги ЧПД: ставки якоря несут весь ЧПД
    nb = files["nii_books"]
    nb["as_of"] = end.isoformat()
    if "period" in nb:
        nb["period"] = period
    if "rates_carry_residual" in nb:
        nb["rates_carry_residual"] = True
    touched = set()
    interest = {b: float(report["interest"][b]) for b in roles.names}
    income = sum(interest[b] for b in roles.assets)
    expense = sum(interest[b] for b in roles.liabilities)
    dia = abs(float(report["dia"]))
    residual = float(P["nii"]) - (income - expense - dia)
    scale = 1.0 + residual / income
    prefix = "books." if isinstance(nb.get("books"), dict) else ""
    for b in roles.names:
        avg = (old.balances[b] + float(B["books"][b])) / 2
        carried_interest = interest[b] * (scale if b in roles.assets else 1.0)
        entry = _get(nb, f"{prefix}{b}") or {}
        for key, value in (("balance_open", old.balances[b]), ("balance_close", float(B["books"][b])),
                           ("balance_avg", avg), ("interest_q", interest[b])):
            if key in entry:
                _put(nb, f"{prefix}{b}.{key}", _r(value, 6), tag, touched)
        _put(nb, f"{prefix}{b}.rate_anchor", _r(carried_interest / avg * 365 / days) if avg else 0.0,
             tag + ": проценты книги" + (" с долей остатка ЧПД" if b in roles.assets else "")
             + f" / средний остаток × 365/{days}", touched)
    retail = sum(float(B["books"][b]) for b in roles.retail)
    for key, value in (("dia_q", dia), ("nim_eng_q", eng["nim"]), ("key_avg_anchor_q", float(M["key_avg"])),
                       ("current_share_anchor", float(B["books"][roles.retail[0]]) / retail)):
        _put(nb, key, _r(value), tag, touched)
    for key, value in (("nii_q", float(P["nii"])), ("iea_avg", eng["iea_avg"]), ("days", days),
                       ("other_interest_net_q", residual),
                       ("interest_loans_q", sum(interest[b] for b in roles.loans)),
                       ("interest_assets_q", income), ("interest_liabilities_q", expense)):
        if isinstance(nb.get(key), dict):
            _put(nb, key, value if isinstance(value, int) else _r(value, 6), tag, touched)
    _null_untouched(nb, touched, (), absent)

    # --- ОПУ квартала
    pnl = files["pnl_quarterly"]
    pnl["as_of"] = end.isoformat()
    rows = pnl.get("quarters")
    last = (rows.get(old_period) if isinstance(rows, dict)
            else next((r for r in rows or [] if isinstance(r, dict) and r.get("period") == old_period), None)) or {}
    row = {k: _node(None, absent) for k, v in last.items() if isinstance(v, dict) and "v" in v}
    values = {k: float(P[k]) for k in SECTIONS["pnl"][0]}
    magnitude = (_get(last, "dia.v") or -1.0) > 0                        # знак взносов — как в прежнем файле
    values.update(misc_net=eng["misc_net"], key_avg=float(M["key_avg"]), dia=dia if magnitude else -dia)
    if "ni_nci" in last:
        values["ni_nci"] = float(P["ni"]) - float(P["ni_shareholders"])
    for key in ("oci_fvoci", "other_equity_movements"):
        if key in P:
            values[key] = float(P[key])
    for key, value in values.items():
        row[key] = _node(_r(value), tag)
    if P.get("estimated") is True:           # прибыль квартала — напечатанное значение: точное придёт позже
        for key in ("ni_shareholders", "ni", "ni_nci", "pbt", "tax", "misc_net", "noncore_net"):
            if key in row and row[key]["v"] is not None:
                row[key]["estimated"] = True
    _add_period_row(pnl, "quarters", period, row)

    # --- капитал и нормативы
    cap = files["capital"]
    cap["as_of"] = end.isoformat()
    touched = set()
    estimated = C.get("estimated") is True
    _put(cap, "basel.cet1", float(C["basel_cet1"]), tag, touched)
    _put(cap, "basel.rwa", float(C["basel_rwa"]), tag, touched)
    if isinstance(_get(cap, "basel.cet1_ratio"), dict):
        _put(cap, "basel.cet1_ratio", _r(C["basel_cet1"] / C["basel_rwa"], 6), tag, touched)
    _put(cap, "n20_0.value", float(C["n20_0"]), tag, touched)
    cap["n20_0"]["pre_dividend"] = bool(C["n20_pre_dividend"])
    cap["n20_0"].pop("pre_dividend_note", None)
    _put(cap, "n1_1_bank.value", float(C["n1_1_bank"]), tag, touched)
    _put(cap, "bank_base_capital", float(C["bank_base_capital"]), tag, touched)
    for kind, value in (C.get("guarantees") or {}).items():       # номиналы гарантий якоря (К5)
        _put(cap, f"guarantees.{kind}", float(value), tag, touched)
    for slot in OWN_FUNDS:                   # капитал нормативов банка (форма 0409123): из него книга выводит вычеты
        if slot in C:
            _put(cap, slot, float(C[slot]), tag, touched)
    _put(cap, "fvoci_reserve", float(B["fvoci_reserve"]), tag, touched)
    if "t2" in C:
        _put(cap, "t2_recognized", float(C["t2"]), tag, touched)
    for node in CURVE_NODES:
        _put(cap, f"ofz_curve_anchor.{node}", float(M["ofz_curve"][node]), tag, touched)
    kept = ["at1", "history", "t2_recognized"]
    for slot, name in ESTIMATE_SLOTS.items():
        block = cap[name]
        if estimated:                        # норматив стоит оценкой до выхода формы (М§3.3)
            block["estimated"] = True
            block["value"]["estimated"] = True
            block["estimate"] = {k: (str(v) if k == ESTIMATE_KEYS[2] else _node(float(v), tag))
                                 for k, v in C["estimate"][slot].items()}
            kept.append(f"{name}.estimate")
        else:
            if "estimated" in block:
                block["estimated"] = False
            block.pop("estimate", None)
    if estimated:
        for path in ("basel.cet1", "basel.rwa", "basel.cet1_ratio", "bank_base_capital"):
            if isinstance(_get(cap, path), dict):
                _get(cap, path)["estimated"] = True
    for name in ("basel", "n20_0", "ofz_curve_anchor", "n1_1_bank"):
        if "as_of" in cap.get(name, {}):     # сдвиг даты блока от конца квартала — как в прежнем файле
            cap[name]["as_of"] = _shifted(cap[name]["as_of"], old_end, end)
    _null_untouched(cap, touched, tuple(kept), absent)
    t2_now = float(C["t2"]) if "t2" in C else old.t2
    known = {"n20_0": float(C["n20_0"]), "cet1": float(C["basel_cet1"]), "rwa": float(C["basel_rwa"]),
             "n1_1_bank": float(C["n1_1_bank"]), "n20_1": float(C["n1_1_bank"]),
             "capital_base": float(C["bank_base_capital"]), "capital_additional": t2_now,
             "capital_total": None if t2_now is None else float(C["basel_cet1"]) + t2_now,
             "rwa_imputed": float(C["basel_rwa"]),
             # строки истории банка соло (форма 0409135 / 0409123): второй слот — тот норматив, что называет факт
             "n1_0": float(C["n20_0"]), "base_capital": float(C["bank_base_capital"]), "rwa_n10": float(C["basel_rwa"]),
             **({"own_funds": float(C["bank_own_funds"])} if "bank_own_funds" in C else {}),
             f"n1_{2 if (_get(cap, 'n1_1_bank.slot_metric') == 'Н1.2') else 1}": float(C["n1_1_bank"])}
    have = _node_keys(cap.get("history"))
    names = [k for k in known if k in have] or ["n20_0", "cet1", "rwa", "n1_1_bank"]
    line = {"date": end.isoformat(), **{k: _node(None if known[k] is None else _r(known[k]), tag) for k in names}}
    if estimated:
        for k in names:
            line[k]["estimated"] = True
    _add_period_row(cap, "history", period, line)

    # --- акции
    if "shares" in report:
        files["shares"]["as_of"] = end.isoformat()
        for key, value in report["shares"].items():
            files["shares"][key] = _node(float(value), tag)

    # --- дивиденды по периодам
    if quarterly:
        _carry_dividends(files, book, old, report, tag)

    # --- мост упр. ↔ МСФО: упр. факт закрытого квартала — в историю всегда (год якоря в упр. базисе
    #     собирается из отчётных кварталов, М§4.6); среднее по окну продлевается при `update_bridge`
    br = files["bridge_mgmt_ifrs"]
    br["as_of"] = end.isoformat()
    window = br.get("window")
    in_window = isinstance(window, list) and len(window) == 2
    count0 = pindex(old_period) - pindex(str(window[0])) + 1 if in_window else 0
    old_year, new_year = parse_period(old_period)[0], parse_period(period)[0]
    for x in ("cor", "nim", "cir"):
        if x not in G:
            continue
        block = br[x]
        additive = block["method"] == "additive"
        gap = eng[x] - float(G[x]) if additive else eng[x] / float(G[x])
        have = _node_keys(block.get("history"))
        line = {"mgmt": _node(float(G[x]), tag), "engine": _node(_r(eng[x]), tag),
                "gap": _node(_r(gap), "engine − mgmt" if additive else "engine / mgmt")}
        if "engine_books" in have:           # вариант на знаменателе движка: сумма кредитных книг — он же engine
            line["engine_books"] = _node(_r(eng[x]), tag)
            line["gap_books"] = _node(_r(gap), "engine_books − mgmt" if additive else "engine_books / mgmt")
        level = gap                          # разность, по которой считается value моста
        if "gap_x4" in have:                 # база «× 4» без ряби счёта дней: value моста — среднее gap_x4
            x4 = eng[x] * 4 * days / 365
            level = x4 - float(G[x]) if additive else x4 / float(G[x])
            line["engine_x4"] = _node(_r(x4), tag + ": × 4 вместо × 365/" + str(days))
            line["gap_x4"] = _node(_r(level), "engine_x4 − mgmt" if additive else "engine_x4 / mgmt")
        own = block.get("window") if isinstance(block.get("window"), list) and len(block["window"]) == 2 else None
        # окно значения — отчётные кварталы года якоря: начинается с первого квартала года и не совпадает с окном файла
        yearly = (own is not None and in_window and str(own[0]) != str(window[0])
                  and parse_period(str(own[0])) == (old_year, 1))
        count = int(_get(block, "n.v") or count0)
        if update_bridge and yearly and new_year != old_year:
            block["value"] = _node(_r(level), f"reanchor: окно значения — отчётные кварталы года якоря: {period} (n = 1)")
            block["window"] = [period, period]
            count = 0
        elif update_bridge and count:
            value = (float(block["value"]["v"]) * count + level) / (count + 1)
            block["value"] = _node(_r(value), f"reanchor: среднее по окну с {period} (n = {count + 1})")
            if own is not None:
                block["window"] = [own[0], period]
        if update_bridge and (count or yearly):
            if isinstance(block.get("n"), dict):
                block["n"] = _node(count + 1, "кварталов в окне")
            if isinstance(block.get("sd"), dict):
                block["sd"] = _node(None, absent)
            if isinstance(block.get("value_books"), dict):
                block["value_books"] = dict(block["value"])
            if isinstance(block.get("value_ac_only"), dict):
                block["value_ac_only"] = _node(None, absent)
        if isinstance(block.get("history"), list):
            _add_period_row(block, "history", period, line)
    if update_bridge and in_window:
        br["window"] = [window[0], period]

    # --- упр. метрики квартала
    mq = files.get("mgmt_quarterly")
    if isinstance(mq, dict) and isinstance(mq.get("quarters"), (dict, list)):
        mq["as_of"] = end.isoformat()
        _add_period_row(mq, "quarters", period, {k: _node(float(v), tag) for k, v in G.items()})

    return Facts(root=Path(f"reanchor-{period}"), files=files,
                 digest=hashlib.sha256(canonical_json(files)).hexdigest())


def _carry_dividends(files: dict, book: Book, old: Any, report: Mapping, tag: str) -> None:
    """Квартальный календарь (М§15.2 п. 9): решения собраний закрываемого квартала — строками истории
    дивидендов (они закрывают свои кварталы прибыли на новом якоре); записи реестра — в затравку нового
    якоря, пока их экс-дата впереди или их сумма стоит в списке «объявлено, не выплачено»."""
    period = str(report["period"])
    end = period_end(period)
    div = files["dividends"]
    div["as_of"] = end.isoformat()
    history = div.setdefault("history", [])
    by_period = {str(_fact(r.get("period"))): r for r in history if isinstance(r, dict)}
    seed = [r for r in div.get("register_seed") or [] if isinstance(r, dict)]
    seeded = {str(_fact(r.get("period"))) for r in seed}
    for d in report.get("dividend_decisions") or []:
        p, dps = str(d["period"]), float(d["dps"])
        pool = float(d["pool_declared"]) if "pool_declared" in d else dps * old.n_iss / THOUSAND
        row = by_period.get(p)
        if row is None:
            row = {"year": parse_period(p)[0], "period": p}
            history.append(row)
            by_period[p] = row
        same = history_dps(row) is not None and abs(history_dps(row) - dps) <= DIV_TOL
        if not same:                         # строка истории несёт решение отчёта; прежние источники — не о нём
            row["dps"] = _node(dps, tag)
            row["pool_declared"] = _node(_r(pool, 6), tag + ": DPS × размещённые акции" if "pool_declared" not in d else tag)
        elif not isinstance(row.get("pool_declared"), dict) or row["pool_declared"].get("v") is None:
            row["pool_declared"] = _node(_r(pool, 6), tag)
        row["decided_date"] = str(d["decided_date"])
        for key in ("record_date", "pay_date"):
            if d.get(key) is not None:
                row[key] = str(d[key])
        # решение с датой реестра позже нового якоря: дивиденд уже вычтен из капитала якоря, а акционеру ещё
        # причитается — запись реестра держит его в мосте до экс-даты (М§8.1)
        if d.get("record_date") is not None and to_date(d["record_date"]) > end and p not in seeded:
            seed.append({"year": parse_period(p)[0], "period": p, "dps": _node(dps, tag), "status": "declared",
                         "decided_date": str(d["decided_date"]), "record_date": str(d["record_date"]),
                         "ex_date": str(d["record_date"]),
                         **({"pay_date": str(d["pay_date"])} if d.get("pay_date") is not None else {}),
                         "sources": [f"manual: отчёт квартала {period}"]})
            seeded.add(p)
    history.sort(key=lambda r: pindex(str(_fact(r.get("period")))))
    unpaid = {str(x["period"]) for x in report["balance"].get("dividends_payable_declared") or []}

    def alive(rec: Mapping) -> bool:
        ex = _fact(rec.get("ex_date")) or _fact(rec.get("record_date"))
        return str(_fact(rec.get("period"))) in unpaid or ex is None or to_date(ex) > end

    if "register_seed" in div or seed:
        div["register_seed"] = [r for r in seed if alive(r)]


# ------------------------------------------------------------------ шаги переноса книги


def _scale_traj(traj: Any, factor: float) -> Any:
    if _num(traj):
        return _r(traj * factor, 6)
    return {k: (v if str(k) == "LT_from" else _r(float(v) * factor, 6)) for k, v in traj.items()}


def _explicit_from(traj: Mapping, year: int) -> dict:
    """Та же траектория с явными ключами лет от `year` до начала LT-уровня: правка ключа года
    не должна сдвигать соседние интерполированные годы."""
    t = Trajectory(traj)
    stop = max([int(k) for k in map(str, traj) if k.isdigit()] + [year])
    if "LT_from" in traj and "LT" in traj:
        stop = max(stop, int(traj["LT_from"]) - 1)
    out = dict(traj)
    for y in range(year, stop + 1):
        out.setdefault(str(y), _r(t.year_value(y)))
    return _sorted_traj(out)


def _axis_lists(X: dict) -> list[tuple[str, list, tuple[str, ...]]]:
    V = X["valuation"]
    return [("valuation.uncertainty.axes", V["uncertainty"].get("axes") or [], ("low", "high")),
            ("valuation.uncertainty.off_band_axes", V["uncertainty"].get("off_band_axes") or [], ("low", "high")),
            ("valuation.reverse_dcf.axes", V["reverse_dcf"].get("axes") or [], ("search", "range"))]


def _axis_lists_of(X: Mapping) -> list[tuple[str, list, tuple[str, ...]]]:
    """Те же списки осей, что `_axis_lists`; у словаря книги без раздела оценки (части книги в тестах) — пустые."""
    V = X.get("valuation") or {}
    U_ = V.get("uncertainty") or {}
    return [("valuation.uncertainty.axes", U_.get("axes") or [], ("low", "high")),
            ("valuation.uncertainty.off_band_axes", U_.get("off_band_axes") or [], ("low", "high")),
            ("valuation.reverse_dcf.axes", (V.get("reverse_dcf") or {}).get("axes") or [], ("search", "range"))]


def _value_axes(X: dict, path: str) -> list[tuple[dict, tuple[str, ...]]]:
    """Оси вида value по одному параметру `path` (полоса, оси вне полосы, обратный расчёт)."""
    return [(axis, keys) for _, axes, keys in _axis_lists(X) for axis in axes
            if axis.get("kind") == "value" and [str(p) for p in axis.get("paths") or []] == [path]]


def _under(path: str, roots: Sequence[str]) -> bool:
    return any(path == r or path.startswith(r + ".") for r in roots)


def _move_axis(axis: dict, keys: Sequence[str], move) -> None:
    for key in keys:
        value = axis.get(key)
        if _num(value):
            axis[key] = move(value)
        elif isinstance(value, list) and value and all(_num(v) for v in value):
            axis[key] = [move(v) for v in value]


def _scale_axes(X: dict, roots: Sequence[str], factor: float) -> None:
    """Оси по параметрам `roots` — тем же множителем, что и сами параметры: диапазон суждения
    задан в единицах параметра. Ось, которая двигает их вместе с другими, одним множителем не
    перевести — отказ. Ось-связка сюда не входит: её концы заданы по путям и идут за своим центром
    (`_bundle_centers`, `_follow_centers`)."""
    for where, axes, keys in _axis_lists(X):
        for axis in axes:
            if axis.get("kind") == BUNDLE:
                continue
            paths = [str(p) for p in axis.get("paths") or []]
            hit = [p for p in paths if _under(p, roots)]
            if not hit:
                continue
            if len(hit) != len(paths):
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось двигает {', '.join(paths)} — пересчитываемые "
                    f"({', '.join(hit)}) вместе с другими; разделить ось (решение книги)")
            _move_axis(axis, keys, lambda v: _r(v * factor, 6))


def _remap_axes(X: dict, path: str, was: float, now: float, slope: float = 1.0,
                bounds: tuple[float, float] | None = None) -> None:
    """Ось вида value по одному параметру — тем же пересчётом, что и параметр: значение оси v
    переходит в `now + slope × (v − was)` (сдвиг при slope = 1). `bounds` — область определения:
    конец оси, стоящий на её границе, остаётся на границе, прочие из неё не выходят."""
    def move(v: float) -> float:
        if bounds is not None and v in bounds:
            return v
        v = _r(now + slope * (v - was))
        return v if bounds is None else min(bounds[1], max(bounds[0], v))
    for axis, keys in _value_axes(X, path):
        _move_axis(axis, keys, move)
    _move_bundle_ends(X, path, move)


def _leaf(tree: Any, dotted_path: str) -> Any:
    """Значение книги по точечному пути оси (ключ траектории — строкой или числом); нет пути — None."""
    return get_path(tree, dotted_path) if has_path(tree, dotted_path) else None


def _bundles(X: dict) -> list[tuple[str, dict, tuple[str, ...]]]:
    """Оси-связки книги (вид `bundle`, М§10): (где, ось, ключи концов)."""
    return [(where, axis, keys) for where, axes, keys in _axis_lists(X) for axis in axes if axis.get("kind") == BUNDLE]


def _move_bundle_ends(X: dict, path: str, move) -> None:
    """Концы осей-связок по пути `path` — правилом `move` (тем же, что у оси вида `value` по этому пути)."""
    for _, axis, keys in _bundles(X):
        for key in keys:
            ends = axis.get(key)
            if isinstance(ends, dict) and _num(ends.get(path)):
                ends[path] = move(ends[path])


def _bundle_centers(X: dict, roots: Sequence[str]) -> dict[str, Any]:
    """Центры осей-связок по путям под `roots` — значения книги ДО пересчёта: {путь: значение}. Связка применяется
    приращением к значению книги (М§10), поэтому её конец идёт за центром — `_follow_centers`."""
    return {p: _leaf(X, p) for _, axis, _ in _bundles(X) for p in map(str, axis.get("paths") or []) if _under(p, roots)}


def _follow_centers(X: dict, centers: Mapping[str, Any], slope: float, digits: int = 6) -> None:
    """Концы осей-связок после пересчёта центров: конец v пути переходит в `стало + slope × (v − было)` — то же
    правило, что у оси вида `value`; у чистого множителя это `v × slope`, у суммы года якоря, закрытой остатком
    к факту, — сдвиг вместе с центром и множитель на отклонение от него."""
    for path, was in centers.items():
        now = _leaf(X, path)
        if not _num(was) or not _num(now):
            raise ReportError(f"ось-связка: путь {path} после пересчёта — не число ({was!r} → {now!r}); концы оси "
                              "перенести нечем (решение книги)")
        _move_bundle_ends(X, path, lambda v, was=was, now=now: _r(now + slope * (v - was), digits))


def check_bundles(X: dict, old: Mapping, renamed: Mapping[str, str] | None = None,
                  carried: Sequence[str] = ()) -> None:
    """Сторож осей-связок: путь связки, значение которого перенос якоря изменил, обязан иметь правило переноса
    конца (`BUNDLE_CARRIED`, `carried` — пути, правило которых включила книга); иначе центр ушёл бы, а концы
    остались — молча. `renamed` — ключи, переименованные вместе с годом шока: {прежний путь: новый}."""
    back = {new: was for was, new in (renamed or {}).items()}
    for where, axis, _ in _bundles(X):
        for path in map(str, axis.get("paths") or []):
            if _under(path, tuple(BUNDLE_CARRIED) + tuple(carried)):
                continue
            was, now = _leaf(old, back.get(path, path)), _leaf(X, path)
            if was != now:
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось-связка двигает {path}, а перенос якоря его пересчитал "
                    f"({_fmt(was)} → {_fmt(now)}): правила переноса конца оси по этому пути нет — концы задаёт книга "
                    "(решение книги: снять путь с оси или задать концы на новом якоре)")


def reindex_prices(X: dict, facts: Facts, period: str, factor: float) -> None:
    """Реальные суммы книги — из цен прежнего якоря в цены нового (М§15.2 п. 2).

    Сумма непрофильного результата года якоря закрывается остатком к факту (М§0.3): индексируется
    только остаток года, `S' = F + (S − F) × индекс`, F — факт отчётных кварталов прежней книги."""
    year = parse_period(period)[0]
    reported = 0.0
    centers = _bundle_centers(X, PRICE_INDEXED)
    for per, row in facts.periods("pnl_quarterly").items():
        if parse_period(per)[0] == year and pindex(per) < pindex(period):
            value = _get(row, "noncore_net.v")
            if value is None:
                raise ReportError(f"факты: pnl_quarterly.{per}.noncore_net — null, а год якоря "
                                  "непрофильного результата закрывается остатком к факту (М§0.3)")
            reported += float(value)
    for path in PRICE_INDEXED:
        traj = _get(X, path)
        if traj is None and path == NCI_REAL:   # Р11-3: ключ необязателен — нет ключа, нечего переводить
            continue
        if path == NONCORE and reported:
            if not isinstance(traj, Mapping):
                raise ReportError(f"{NONCORE} — скаляр, а год якоря закрывается остатком к факту: "
                                  "нужна траектория с ключом года якоря (решение книги)")
            traj = _explicit_from(traj, year)
            scaled = _scale_traj(traj, factor)
            scaled[str(year)] = _r(reported + (float(traj[str(year)]) - reported) * factor, 6)
            _set(X, path, scaled)
        else:
            _set(X, path, _scale_traj(traj, factor))
    _scale_axes(X, PRICE_INDEXED, factor)
    _follow_centers(X, centers, factor)


def freeze_anchors(X: dict, book: Book) -> None:
    for path in FROZEN_ANCHORS:
        if _get(X, path) == "anchor":
            _set(X, path, _r(book.anchors[path]))


def carry_fx(X: dict, factor: float) -> None:
    """Валютная доля RWA на новом якоре: индекс курса стартует с единицы (М§4.11), поэтому доля
    пересчитывается на достигнутый курс — тогда путь RWA тот же."""
    if not _get(X, f"{FX}.enabled"):
        return
    share, abroad = float(_get(X, f"{FX}.share")), float(_get(X, f"{FX}.foreign_inflation"))
    rate = factor / (1.0 + abroad) ** 0.25
    _set(X, f"{FX}.share", _r(share * rate / (1.0 - share + share * rate)))


def spread_rule(data: Mapping, rates: Mapping[str, float], name: str) -> tuple[int, float] | None:
    """Ключ спреда года первого прогнозного квартала по правилу «от ставки якоря» (М§4.4):
    ставка якоря − β × опора мира-эталона в первом прогнозном квартале; `None` — у книги такого
    ключа нет."""
    spec = data["nii"]["books"][name]
    spread = spec["spread"]
    year, quarter = parse_period(str(data["meta"]["first_period"]))
    if not isinstance(spread, Mapping) or str(year) not in spread:
        return None
    world = data["worlds"][data["nii"]["transmission"]["reference_world"]]
    ref = Trajectory(world["key_rate" if spec["ref"] == "key" else spec["ref"]]).value(year, quarter)
    beta = float(spec["beta"]) if spec["side"] == "liability" else 1.0
    return year, rates[name] - beta * ref


def rederive_spreads(X: dict, old: Book, old_rates: Mapping[str, float], rates: Mapping[str, float]) -> list[str]:
    """Ключи спредов от ставок якоря — заново, тем же правилом, что в прежней книге (М§4.4).

    Ключ правится, только если прежняя книга правилу следовала; ключ следующего года остаётся
    серединой до калибровки, если был ею."""
    moved = []
    for name, spec in X["nii"]["books"].items():
        was = spread_rule(old.source, old_rates, name)
        now = spread_rule(X, rates, name)
        if was is None or now is None:
            continue
        old_spread = old.source["nii"]["books"][name]["spread"]
        y_old, rule_old = was
        if abs(float(old_spread[str(y_old)]) - rule_old) > SPREAD_RULE_TOL:
            continue
        year, rule = now
        spread = dict(spec["spread"])
        if abs(rule - float(spread[str(year)])) <= SPREAD_RULE_TOL:
            continue                             # ставка якоря та же — ключ книги остаётся как есть
        old_t = Trajectory(old_spread)
        middle = (str(y_old + 1) in old_spread and abs(
            float(old_spread[str(y_old + 1)])
            - (float(old_spread[str(y_old)]) + old_t.year_value(y_old + 2)) / 2) <= SPREAD_RULE_TOL)
        spread[str(year)] = _r(rule, 6)
        if middle:
            spread[str(year + 1)] = _r((spread[str(year)] + old_t.year_value(year + 2)) / 2, 6)
        spec["spread"] = _sorted_traj(spread)
        spread_ends(X, old, name, (y_old, rule_old), (year, rule), middle, old_rates, rates)
        moved.append(name)
    return moved


def spread_ends(X: dict, old: Book, name: str, was: tuple[int, float], now: tuple[int, float], middle: bool,
                old_rates: Mapping[str, float], rates: Mapping[str, float]) -> None:
    """Концы осей-связок по ключам спреда книги `name`, выведенным от ставки якоря (М§4.4, связка β книги со спредом):
    тем же правилом, что центр, при β конца — `ставка якоря − β_конца × опора`; ключ следующего года, если центр —
    середина до калибровки, — середина конца. Конец, который прежней книге правилом не следовал, сдвигается вместе с
    центром (наклон 1). Ось вида value по такому ключу — тем же сдвигом."""
    y_old, rule_old = was
    year, rule = now
    spec = old.source["nii"]["books"][name]
    liability = spec["side"] == "liability"
    beta0 = float(spec["beta"]) if liability else 1.0      # правило спреда: β — у пассивов, у активов — единица
    base = f"nii.books.{name}"
    key, nxt = f"{base}.spread.{year}", f"{base}.spread.{year + 1}"
    center_old = float(spec["spread"][str(y_old)])
    ref_old = (old_rates[name] - rule_old) / beta0 if beta0 else None    # опора мира-эталона — из правила центра
    ref_new = (rates[name] - rule) / beta0 if beta0 else None
    for where, axis, keys in _bundles(X):
        if key not in map(str, axis.get("paths") or []):
            continue
        for end in keys:
            ends = axis.get(end)
            if not isinstance(ends, dict) or not _num(ends.get(key)):
                continue
            beta = float(ends.get(f"{base}.beta", beta0)) if liability else 1.0
            follows = ref_old is not None and abs(float(ends[key]) - (old_rates[name] - beta * ref_old)) <= SPREAD_RULE_TOL
            ends[key] = _r(rates[name] - beta * ref_new, 6) if follows else _r(float(ends[key]) + rule - center_old, 6)
            if middle and _num(ends.get(nxt)):
                after = ends.get(f"{base}.spread.{year + 2}")
                after = float(after) if _num(after) else Trajectory(_get(X, f"{base}.spread")).year_value(year + 2)
                ends[nxt] = _r((float(ends[key]) + after) / 2, 6)
    _remap_value_axis(X, key, center_old, rule)


def _remap_value_axis(X: dict, path: str, was: float, now: float) -> None:
    """Оси вида value по одному пути — сдвигом вместе с центром (концы связок здесь не трогаются)."""
    for axis, keys in _value_axes(X, path):
        _move_axis(axis, keys, lambda v: _r(now + (v - was)))


def _shift_key(key: Any, years: int) -> str:
    key = str(key)
    return key if key in ("LT", "LT_from") else f"{int(key[:4]) + years}{key[4:]}"


def _shift_traj(traj: Any, years: int, last_year: int, where: str) -> Any:
    if not isinstance(traj, Mapping):
        return traj
    out = {}
    for k, v in traj.items():
        if str(k) == "LT_from":
            if int(v) + years > last_year:
                raise ReportError(f"{where}.LT_from {v} + {years} — позже года last_period {last_year}: "
                                  "кризисная траектория не помещается в горизонт (решение книги)")
            out[k] = int(v) + years
        else:
            out[_shift_key(k, years)] = v
    return out


def shift_crisis(X: dict, years: int) -> dict[str, str]:
    """Смена года якоря: год шока сдвигается вместе с ним, ключи кризисных траекторий — на
    столько же лет (М§15.2 п. 6). `shock_year_offset` сохраняется. Пути осей по этим ключам переименовываются
    вместе с ними; у оси-связки — и ключи словарей её концов. Возвращает {прежний путь: новый}."""
    if not years:
        return {}
    last_year = parse_period(str(X["meta"]["last_period"]))[0]
    renamed: dict[str, str] = {}
    for r in X["regimes"]["ids"]:
        spec = X["regimes"][r]
        if "shock_year_offset" not in spec:
            continue
        for name in CRISIS_TRAJECTORIES + ("loan_growth_override",):
            if isinstance(spec.get(name), Mapping):
                for k in spec[name]:
                    renamed[f"regimes.{r}.{name}.{k}"] = f"regimes.{r}.{name}.{_shift_key(k, years)}"
                spec[name] = _shift_traj(spec[name], years, last_year, f"regimes.{r}.{name}")
        if isinstance(spec.get("one_off_loss"), Mapping):
            y, q = parse_period(str(spec["one_off_loss"]["period"]))
            spec["one_off_loss"] = {**spec["one_off_loss"], "period": period_str(y + years, q)}
    for _, axes, keys in _axis_lists(X):
        for axis in axes:
            axis["paths"] = [renamed.get(str(p), p) for p in axis.get("paths") or []]
            if axis.get("kind") == BUNDLE:           # концы связки — словари по путям оси: ключи идут за путями
                for key in keys:
                    if isinstance(axis.get(key), Mapping):
                        axis[key] = {renamed.get(str(p), p): v for p, v in axis[key].items()}
    table = _get(X, "checks.m_crisis_vs_cbr.loan_growth")
    if isinstance(table, Mapping):
        X["checks"]["m_crisis_vs_cbr"]["loan_growth"] = {_shift_key(k, years): v for k, v in table.items()}
    return renamed


def near_trajectory(old: Any, periods: Sequence[str], values: Sequence[float], last_year: int,
                    detail_from: int = 0) -> dict:
    """Ближняя калибровка ЧПМ траекторией книги: кварталы — по год после якоря включительно и
    дальше, пока значения внутри года заметно расходятся; затем — ключи лет со средним года,
    пока хвост заметен (в последнем году сетки — только ключ года, М§0.4: там остаток уровня в
    ставках и калибровка гасят друг друга, и терминал читает LT-уровни); `LT` — прежний.
    `detail_from` — год, по который кварталы пишутся в любом случае: год, записанный кварталами на
    прошлом проходе калибровки, остаётся записанным кварталами (иначе запись прыгает между двумя
    видами и проходы не сходятся)."""
    lt = float(old.get("LT", 0.0)) if isinstance(old, Mapping) else float(old)
    by_year: dict[int, list[tuple[int, float]]] = {}
    for p, v in zip(periods, values):
        y, q = parse_period(p)
        by_year.setdefault(y, []).append((q, v))
    detail = parse_period(periods[0])[0] + 1
    for y in sorted(by_year):
        vals = [v for _, v in by_year[y]]
        if y == detail + 1 and max(vals) - min(vals) > NEAR_RANGE:
            detail = y
    detail = min(max(detail, detail_from), last_year - 1)
    out: dict[str, float] = {}
    for y in sorted(by_year):
        if y > detail:
            break
        for q, v in by_year[y]:
            out[period_str(y, q)] = _r(v, 7)
        if len(by_year[y]) == 4:
            out[str(y)] = sum(out[period_str(y, q)] for q in (1, 2, 3, 4)) / 4
    means = {y: sum(v for _, v in qs) / len(qs) for y, qs in by_year.items() if detail < y <= last_year}
    tail = [y for y in means if abs(means[y] - lt) >= NEAR_TOL]
    for y in sorted(means):
        if tail and y <= max(tail):
            out[str(y)] = _r(means[y], 7)
    out["LT"] = lt
    return out


def set_near(X: dict, traj: Any, warnings: list[str] | None = None) -> None:
    """Ближняя калибровка ЧПМ — в книгу, вместе с осями по её ключам. Траектория пишется заново (кварталы,
    затем годы), и ось, которая сдвигает её ключи нескольких лет, получает ключи тех же лет новой траектории:
    ключ закрытого квартала из путей уходит, год, записанный теперь кварталами, входит всеми своими ключами.
    Ось, у которой не осталось ни одного ключа (все её годы закрыты), снимается — с предупреждением."""
    _set(X, NEAR, traj)
    keys = [str(k) for k in traj if str(k) not in ("LT", "LT_from")] if isinstance(traj, Mapping) else []
    prefix = NEAR + "."
    for where, axes, _ in _axis_lists(X):
        for axis in list(axes):
            paths = [str(p) for p in axis.get("paths") or []]
            mine = [p for p in paths if p.startswith(prefix)]
            if not mine:
                continue
            if axis.get("kind") == BUNDLE:
                raise ReportError(
                    f"{where} «{axis.get('name')}»: ось-связка двигает ключи ближнего пути ЧПМ ({', '.join(mine)}), а "
                    "перенос якоря пишет траекторию заново — другими ключами; концы оси для новых ключей инструмент "
                    "придумать не может (решение книги: ось вида shift или концы на новом якоре)")
            years = {p[len(prefix):][:4] for p in mine}
            fresh = [prefix + k for k in keys if k[:4] in years]
            if set(fresh) == set(mine):
                continue
            rest = [p for p in paths if not p.startswith(prefix)]
            if fresh or rest:
                axis["paths"] = rest + fresh
            else:
                axes.remove(axis)
                if warnings is not None:
                    warnings.append(f"{where} «{axis.get('name')}»: все ключи ближнего пути ЧПМ, которые двигала ось, "
                                    "закрыты отчётами — ось снята (решение книги: нужна ли ось на новых ключах)")


def _reference_form(tree: Mapping) -> dict:
    """Копия книги в записи образца: без ключа мира уровня (`nii.transmission.level_world`) ключ цели ЧПМ задаёт
    уровень мира-опоры решателя передачи (М§4.5). У книги без этого ключа — просто копия."""
    Y = copy.deepcopy(dict(tree))
    Y["nii"]["transmission"].pop(LEVEL_WORLD.rsplit(".", 1)[-1], None)
    return Y


def _sigmas(tr: Any) -> tuple[float, float, float, float]:
    """Скаляры пути передачи ставки (М§4.5) — σ0_A, σ0_L, φ_A, φ_L: всё, что клетка несёт из решения
    `solve_transmission` в ставки своих кварталов и терминала."""
    return float(tr.sigma0), float(tr.sigma0_liab), float(tr.phi_assets), float(tr.phi_liab)


def keep_transmission(X: dict, new_facts: Facts, old: GridRun) -> dict[str, tuple[float, float, float]]:
    """Режим `keep` (М§15.2 п. 8). Цели A-N2, A-N3 и доли `nii.sigma0_split`, `nii.phi_split` — числа
    «на структуре якоря» (М§4.5): при переносе якоря они пересчитываются на новую структуру так,
    чтобы скаляры пути σ0_A, σ0_L, φ_A, φ_L остались прежними.

    Иначе ядро решило бы те же цели на сдвинувшихся весах книг и сдвинуло бы спреды всего пути
    и терминала — без единой новости. Решение — по самой функции ядра `solve_transmission`, без
    её внутренностей: σ0_A и σ0_L аффинны по цели A-N2, объём сжатия φ — по цели A-N3, а
    `φ_A = p × φ`, `φ_L = (1 − p) × φ × A/L` (A/L — отношение весов книг с `phi` на структуре
    якоря; читается из наклонов φ_L и φ по цели). Оси целей пересчитываются тем же правилом —
    концу оси отвечают те же скаляры, что в прежней книге; оси долей сдвигаются вместе с центром
    (конец на границе 0 или 1 остаётся на ней). Возвращает {ключ: (было, стало, наклон пересчёта оси)}.

    Ключ мира уровня (`nii.transmission.level_world`): ключ цели ЧПМ книги — не уровень мира-опоры решателя, а
    стационарная маржа названного мира на составе баланса якоря, уровень мира-опоры ядро находит сам. Скаляры
    сохраняются тем же решением в записи образца (книга без ключа мира уровня, цель — уровень мира-опоры:
    там σ0 от цели A-N3 не зависят, и решение идёт в два шага), а ключ книги на новом якоре — стационарная маржа
    мира уровня при этих скалярах: то же суждение на составе баланса нового якоря. Оси по ключу и по цели A-N3
    пересчитываются в единицах ключа книги: вдоль оси A-N3 неподвижен ключ, а не уровень мира-опоры."""
    bridge = bridge_from_facts(new_facts)
    was = old.ctx.transmission
    level = _get(X, LEVEL_WORLD)                         # None — ключ цели стоит в мире-опоре решателя (образец)
    key0, star0 = float(_get(X, NIM_TARGET)), float(_get(X, T_TARGET))
    s0, p0 = float(_get(X, SPLIT)), float(_get(X, PHI_SPLIT))
    # проба цели в записи образца — уровень мира-опоры решателя прежней книги (у образца — сам ключ)
    t0 = key0 if level is None else old.ctx.bridge.to_mgmt_nim(float(was.nss[was.reference_world]))

    def solve(target: float, t_star: float, split: float, phi_split: float) -> Any:
        Y = _reference_form(X)
        for path, value in zip(TRANSMISSION_KEYS, (target, t_star, split, phi_split)):
            _set(Y, path, value)
        return solve_transmission(book_from_dict(Y, facts=new_facts), new_facts, bridge)

    def solve_old(path: str | None) -> Any:              # прежняя структура; `path` — цель, сдвинутая на шаг
        if level is None:
            probe = old.ctx.book.with_overrides({path: float(old.ctx.book.get(path)) + SOLVE_STEP})
        else:
            Y = _reference_form(old.ctx.book.source or old.ctx.book.data)
            _set(Y, NIM_TARGET, t0)
            if path is not None:
                _set(Y, path, float(_get(Y, path)) + SOLVE_STEP)
            probe = book_from_dict(Y, facts=old.ctx.facts)
        return solve_transmission(probe, old.ctx.facts, old.ctx.bridge)

    want_a, want_l, want_pa, want_pl = _sigmas(was)
    base = was if level is None else solve_old(None)     # прежнее решение в записи образца — база наклонов
    if max(abs(x - y) for x, y in zip(_sigmas(base), _sigmas(was))) > GAP_TOL:
        raise ReportError(
            f"передача ставки: прежняя книга в записи образца (без `{LEVEL_WORLD}`, цель — уровень мира-опоры "
            f"решателя {was.reference_world}) даёт скаляры пути {_fmt(list(_sigmas(base)))}, а сама книга — "
            f"{_fmt(list(_sigmas(was)))}: ключ мира уровня ядро читает не как стационарную маржу этого мира (М§4.5)")

    # --- σ0_A, σ0_L: цель A-N2 и доля сдвига
    a0, l0, _, _ = _sigmas(solve(t0, star0, s0, p0))
    a1, l1, _, _ = _sigmas(solve(t0 + SOLVE_STEP, star0, s0, p0))
    da, dl = (a1 - a0) / SOLVE_STEP, (l1 - l0) / SOLVE_STEP
    if (s0 > 0 and not da) or (s0 < 1 and not dl):
        raise ReportError("передача ставки: σ0 не зависит от цели A-N2 — нет книг с lt_shift?")
    old_target = solve_old(NIM_TARGET)
    (old_a, old_l, _, _), (base_a, base_l, _, _) = _sigmas(old_target), _sigmas(base)
    da_old, dl_old = (old_a - base_a) / SOLVE_STEP, (old_l - base_l) / SOLVE_STEP
    if s0 >= 1.0:                                        # весь сдвиг — на активах
        target, split, slope = t0 + (want_a - a0) / da, s0, da_old / da
    elif s0 <= 0.0:                                      # весь сдвиг — на пассивах
        target, split, slope = t0 + (want_l - l0) / dl, s0, dl_old / dl
    else:
        root = t0 - a0 / da                              # цель, при которой сдвиг нулевой
        g1, h1 = da / s0, dl / (1.0 - s0)
        target = root + want_a / g1 + want_l / h1
        split = want_a / (g1 * (target - root)) if target != root else s0
        slope = da_old / g1 + dl_old / h1
    split = _r(min(1.0, max(0.0, split)), 6)
    if level is None:                                    # у книги с миром уровня округляется ключ книги, не проба
        target = _r(target, 6)

    # --- φ_A, φ_L: цель A-N3 и доля сжатия
    tr0, tr1 = solve(target, star0, split, p0), solve(target, star0 + SOLVE_STEP, split, p0)
    dphi = float(tr1.phi) - float(tr0.phi)
    if not dphi:
        raise ReportError("передача ставки: φ не зависит от цели A-N3 — нет книг с phi?")
    if p0 < 1.0:
        ratio = (float(tr1.phi_liab) - float(tr0.phi_liab)) / ((1.0 - p0) * dphi)    # A/L новой структуры
        if not ratio:
            raise ReportError("передача ставки: φ_L не зависит от цели A-N3 — нет пассивов с phi?")
        want_phi = want_pa + want_pl / ratio
    else:                                                # всё сжатие — в спредах кредитных книг
        want_phi = want_pa
    phi_split = want_pa / want_phi if 0.0 < p0 < 1.0 and want_phi else p0
    phi_split = _r(min(1.0, max(0.0, phi_split)), 6)
    t_star = _r(star0 + (want_phi - float(tr0.phi)) * SOLVE_STEP / dphi, 6)
    old_star = solve_old(T_TARGET)
    dphi_old = float(old_star.phi) - float(base.phi)
    key = target

    if level is not None:                                # ключ книги — стационарная маржа мира уровня при этих скалярах
        def margin(tr: Any, br: Any) -> float:
            return br.to_mgmt_nim(float(tr.nss[level]))

        at = solve(target, t_star, split, phi_split)
        by_target = solve(target + SOLVE_STEP, t_star, split, phi_split)
        by_star = solve(target, t_star + SOLVE_STEP, split, phi_split)
        gain = margin(by_target, bridge) - margin(at, bridge)            # ключ книги на шаг уровня мира-опоры
        gain_old = margin(old_target, old.ctx.bridge) - margin(base, old.ctx.bridge)
        if not gain or not gain_old:
            raise ReportError(f"передача ставки: стационарная маржа мира {level} не зависит от уровня мира-опоры "
                              f"решателя — ключ `{NIM_TARGET}` в мире `{LEVEL_WORLD}` не определён")
        key = _r(margin(at, bridge), 6)
        slope *= gain / gain_old
        # вдоль оси A-N3 неподвижен ключ книги: уровень мира-опоры идёт за целью так, чтобы ключ остался на месте
        dphi = float(by_star.phi) - float(at.phi) - (float(by_target.phi) - float(at.phi)) * (
            margin(by_star, bridge) - margin(at, bridge)) / gain
        dphi_old -= (float(old_target.phi) - float(base.phi)) * (
            margin(old_star, old.ctx.bridge) - margin(base, old.ctx.bridge)) / gain_old
        if not dphi:
            raise ReportError("передача ставки: при неподвижном ключе уровня маржи φ не зависит от цели A-N3")
    slope_star = dphi_old / dphi
    if float(was.phi):                                   # конец оси: обе части сжатия — в той же пропорции
        slope_star *= want_phi / float(was.phi)

    out = {}
    for path, before, now, k, bounds in ((NIM_TARGET, key0, key, slope, None),
                                         (T_TARGET, star0, t_star, slope_star, None),
                                         (SPLIT, s0, split, 1.0, (0.0, 1.0)),
                                         (PHI_SPLIT, p0, phi_split, 1.0, (0.0, 1.0))):
        _set(X, path, now)
        _remap_axes(X, path, before, now, k, bounds)
        out[path] = (before, now, k)
    return out


def carry_level_gate(X: dict, kept: Mapping[str, tuple]) -> tuple[float, float] | None:
    """Гейт `checks.nim_stationary` в мире ключа уровня маржи (`nii.transmission.level_world`) сверяет то же
    число, что задаёт ключ цели ЧПМ, — тождество: его цель — вторая запись того же суждения и идёт за ключом тем
    же сдвигом (гейт, молчавший на прежней книге, молчит и на кандидате). Возвращает (было, стало). Гейт в
    другом мире, книга без гейта и книга без ключа мира уровня — None: цель гейта — отдельное суждение."""
    gate, level = _get(X, NIM_STATIONARY), _get(X, LEVEL_WORLD)
    if gate is None or level is None or str(gate["world"]) != str(level):
        return None
    before, (was, now, _) = float(gate["target"]), kept[NIM_TARGET]
    after = _r(before + (now - was), 6)
    _set(X, GATE_TARGET, after)
    return before, after


def _row_keys(X: Mapping) -> list[tuple[Any, str]]:
    """Оси обратного расчёта книги с ключами их строк (ключ строки — путь оси, как его пишет ядро)."""
    from model.uncertainty import axis_key
    return [(axis, axis_key(axis)) for axis in _get(X, "valuation.reverse_dcf.axes") or []]


def carry_refine_rows(X: dict, rows: Sequence[Any] | None, before: Sequence[tuple[Any, str]],
                      warnings: list[str] | None = None) -> None:
    """Строки обратного расчёта, корень которых уточняется на полной полосе (`valuation.reverse_dcf.refine_rows`),
    названы ключами строк — путями осей. Перенос переименовывает пути осей (ключи года шока, ключи ближнего пути
    ЧПМ) и может снять ось: строка перечня идёт за своей осью, строка снятой оси из перечня уходит — с
    предупреждением. `rows` — перечень прежней книги (None — ключа нет), `before` — оси кандидата с ключами строк
    прежней книги (`_row_keys` сразу после копии книги). Имя, которого среди строк прежней книги не было,
    остаётся как есть: его судит схема книги."""
    if rows is None:
        return
    now = {id(axis): key for axis, key in _row_keys(X)}
    renamed = {key: now.get(id(axis)) for axis, key in before}
    out: list[str] = []
    gone: list[str] = []
    for row in map(str, rows):
        new = renamed.get(row, row)
        if new is None:
            gone.append(row)
        elif new not in out:
            out.append(new)
    if out != [str(r) for r in _get(X, REFINE_ROWS) or []]:
        _set(X, REFINE_ROWS, out)
    if gone and warnings is not None:
        warnings.append(f"{REFINE_ROWS}: строки {', '.join(gone)} сняты — их осей обратного расчёта у кандидата нет; "
                        "какие строки уточнять на полной полосе — решение книги")


# ------------------------------------------------------------------ наблюдение A-P2u


def _drop_observation(book: Book, period: str) -> Book:
    obs = [o for o in book.get(OBS) or [] if str(o["period"]) != period]
    if len(obs) == len(book.get(OBS) or []):
        return book
    return book.with_overrides({OBS: obs})


def expected_observation(book: Book, facts: Facts, live: LiveInputs | None = None, *,
                         without: Sequence[str] = ()) -> dict:
    """Наблюдение первого прогнозного квартала, равное ожиданию модели (М§13): прогноз фильтра
    A-P2u в упр. базисе; нау-каст этого квартала из книги снимается. `without` — режимы, которые в
    ожидание не входят (отчёт «без шока»: ожидание прочих режимов с их вероятностями, в сумме 1)."""
    from model.nextreport import model_expectation
    period = str(book.get("meta.first_period"))
    exp = model_expectation(_drop_observation(book, period), facts, period, live=live)
    cor, nim = exp["cor_q_mgmt"], exp["nim_q_mgmt"]
    if without:
        rows = [r for r in exp["by_regime"] if r["regime"] not in without]
        total = sum(r["posterior"] for r in rows)
        if not total:
            raise ReportError(f"ожидание без режимов {', '.join(without)}: прочих режимов с вероятностью нет")
        cor = sum(r["posterior"] * r["cor_q_mgmt"] for r in rows) / total
        nim = sum(r["posterior"] * r["nim_q_mgmt"] for r in rows) / total
    return {"period": period, "cor": _r(cor, 12), "nim": _r(nim, 12), "se_cor": 0.0, "se_nim": 0.0,
            "basis": "mgmt"}


def shock_regimes(run: GridRun) -> list[str]:
    """Режимы, у которых первый прогнозный квартал книги лежит в году шока (М§3.2): в этом квартале
    прогноз наблюдения двугорбый — шок либо случился, либо нет."""
    year = run.ctx.timeline.year(1)
    return [r for r, rp in run.ctx.prep.regimes.items() if rp.shock_year is not None and rp.shock_year == year]


def with_observation(book: Book, obs: Mapping) -> Book:
    """Прежняя книга с наблюдением её первого прогнозного квартала (A⁺, М§15.2)."""
    base = _drop_observation(book, str(obs["period"]))
    return base.with_overrides({OBS: list(base.get(OBS) or []) + [dict(obs)]})


def frozen_expectations(book: Book, facts: Facts) -> dict[str, dict[str, float]]:
    """Ожидания режимов прежней книги на её первый прогнозный квартал, упр. базис (М§12)."""
    period = str(book.get("meta.first_period"))
    ctx = make_context(_drop_observation(book, period), facts)
    q = ctx.timeline.index(period)
    mu = ctx.expectations if ctx.expectations and int(ctx.expectations.get("until", 0)) >= q \
        else regime_expectations(ctx, q)
    br = ctx.bridge
    return {"mu_cor": {r: _r(br.to_mgmt_cor(mu["cor"][r][q]), 12) for r in book.get("regimes.ids")},
            "mu_nim": {r: _r(br.to_mgmt_nim(mu["nim"][r][q]), 12) for r in book.get("regimes.ids")}}


def carry_observation(X: dict, book: Book, facts: Facts, obs: Mapping) -> dict:
    """Факт квартала считается один раз: наблюдение с замороженными μ (М§15.2 п. 1)."""
    period = str(obs["period"])
    ru = X["joint"]["regime_update"]
    kept = [o for o in ru.get("observations") or [] if str(o["period"]) != period]
    record = {**{k: obs[k] for k in ("period", "cor", "nim", "se_cor", "se_nim", "basis")},
              **frozen_expectations(book, facts)}
    for x in ("cor", "nim"):
        if record[x] is None:
            record.pop(f"mu_{x}")
    kept.append(record)
    kept.sort(key=lambda o: pindex(str(o["period"])))
    window = ru.get("window_obs")
    ru["observations"] = kept[-int(window):] if window else kept
    return record


# ------------------------------------------------------------------ перезаякоривание


def valuation_day(valuation_date: Any, report: Mapping) -> dt.date:
    """Дата оценки кандидата: заданная, иначе `published` отчёта, иначе день после конца квартала."""
    end = period_end(str(report["period"]))
    try:
        day = to_date(valuation_date or report.get("published") or (end + dt.timedelta(days=1)))
    except ValueError as exc:
        raise ReportError(f"дата оценки {valuation_date!r} — не дата ГГГГ-ММ-ДД") from exc
    if day < end:
        raise ReportError(f"дата оценки {day} раньше конца квартала {end}")
    return day


def _weights(run: GridRun, cell: Sequence[str] | None) -> dict[tuple[str, str, str], float]:
    if cell is not None:
        return {tuple(cell): 1.0}
    return dict(run.layers[ANALYTICAL].prob)


def _mean(run: GridRun, weights: Mapping, name: str, q: int) -> float:
    return sum(w * float(run.cell(*key).quarters[name][q]) for key, w in weights.items() if w)


def _anchor_row(run: GridRun, weights: Mapping, name: str) -> float:
    """Норматив якоря модели: строка q = 0 зависит только от сценария капитала."""
    by_scenario: dict[str, float] = {}
    for (_, _, s), w in weights.items():
        by_scenario[s] = by_scenario.get(s, 0.0) + w
    return sum(w * float(next(c for c in run.cells if c.scenario == s).quarters[name][0])
               for s, w in by_scenario.items() if w)


def carry_t2(X: dict, old_anchor: str, period: str, fact: Any, derived: dict, warnings: list[str]) -> None:
    """Траектория инструментов капитала `capital.n20.t2` (М§4.11): книга, которая пишет ключ квартала якоря
    явно, получает ключ квартала нового якоря, равный факту отчёта, — иначе строка якоря не воспроизвела бы
    норматив. Остальные ключи траектории — суждение книги: инструмент их не трогает и называет это."""
    traj = _get(X, T2)
    if fact is None or not _anchor_key(X, T2, old_anchor):
        return
    now = Trajectory(traj).value(*parse_period(period))
    if abs(float(fact) - now) <= T2_TOL:
        return
    _set(X, T2, _sorted_traj({**traj, period: _r(float(fact), 6)}))
    derived["t2_anchor"] = (now, float(fact))
    warnings.append(f"{T2}: ключ квартала якоря {period} — факт отчёта {float(fact):g} (траектория книги давала "
                    f"{now:g}); остальные ключи траектории — суждение книги (инструменты растут с RWA): пересмотреть")


ESTIMATED_LEVELS = ("basel_cet1", "basel_rwa", "bank_base_capital", "t2")


def estimated_levels(book: Book, facts: Facts, report: Mapping, base_run: GridRun,
                     weights: Mapping[tuple, float]) -> tuple[dict, dict[str, tuple[Any, float]]]:
    """Отчёт с оценкой нормативов (`capital.estimated`, М§3.3): оценка есть только у двух нормативов, а уровни —
    капитал группы и вменённые RWA — на дату якоря ещё не раскрыты; отчёт несёт на их месте уровни последней
    формы. Калибровать плотности RWA к RWA прошлого квартала нельзя: якорь получил бы уровень RWA на квартал
    роста ниже, и каждый рубль роста портфеля стоил бы капитала меньше — без единой новости. Поэтому уровни
    якоря считаются по оценке нормативов на RWA модели:

        RWA    = Σ плотность книги × остаток нового якоря × ожидаемый дрейф плотности за квартал
        K20    = (Н20.0 − поправка + вычет сценария) × RWA;   капитал без инструментов = K20 + (1 − f) × R − AT1 − T2
        K11    = (второй норматив − поправка + вычет сценария) × RWA                       (базовый капитал)

    T2 — значение траектории книги в квартале якоря; ожидаемый дрейф — отношение RWA клеток прежней книги к
    RWA по её плотностям на остатках тех же клеток в закрываемом квартале. Поправки при этом остаются прежними,
    нормативы якоря равны оценке. Возвращает отчёт с расчётными уровнями и {слот: (значение отчёта, расчёт)}."""
    from dataclasses import replace
    roles = book_roles(book.get("nii.books"))
    B, C = report["balance"], report["capital"]
    prep, tl = base_run.ctx.prep, base_run.ctx.timeline
    old = anchor_facts(facts, book.get("nii.books"))
    total = sum(weights.values())
    p = {tuple(k): v / total for k, v in weights.items() if v}
    plain = prep.rwa_w                           # плотности прежней книги
    drift = 0.0
    for key, share in p.items():
        c = base_run.cell(*key)
        bal = {b: float(c.books[b]["balance"][1]) for b in roles.names}
        base = plain.rwa({b: bal[b] for b in roles.loans}, bal[SECURITIES], bal[LIQUIDITY],
                         float(c.quarters["other_assets"][1]), 1.0, 1.0)
        drift += share * float(c.quarters["rwa"][1]) / base
    fixed = float(B["other_assets_fixed"]) if "other_assets_fixed" in B else plain.oa_fixed
    w = replace(plain, oa_fixed=fixed) if plain.oa_fixed else plain
    rwa = drift * w.rwa({b: float(B["books"][b]) for b in roles.loans}, float(B["books"][SECURITIES]),
                        float(B["books"][LIQUIDITY]), float(B["other_assets"]), 1.0, 1.0)
    by_scenario: dict[str, float] = {}
    for (_, _, s), share in p.items():
        by_scenario[s] = by_scenario.get(s, 0.0) + share
    dpp20 = sum(v * prep.scenarios[s].ded_pp20[1] for s, v in by_scenario.items())
    dpp11 = sum(v * prep.scenarios[s].ded_pp11[1] for s, v in by_scenario.items())
    t2 = float(prep.t2[1])
    f = float(book.get("capital.n20.fvoci_recognition"))
    at1 = float(B.get("at1", old.at1))
    k20 = (float(C["n20_0"]) - float(book.get("capital.n20.gap_pp")) + dpp20) * rwa
    k11 = (float(C["n1_1_bank"]) - float(book.get("capital.n11.gap_pp")) + dpp11) * rwa
    levels = {"basel_rwa": rwa, "basel_cet1": k20 + (1 - f) * float(B["fvoci_reserve"]) - at1 - t2,
              "bank_base_capital": k11, "t2": t2}
    if own_funds_form(facts):                # капитал нормативов банка — тот же расчёт: K20 и K11 по оценке
        levels.update(bank_own_funds=k20, bank_main_capital=k11)
    out = copy.deepcopy(dict(report))
    moved = {k: (C.get(k), _r(v, 6)) for k, v in levels.items()}
    out["capital"].update({k: v for k, (_, v) in moved.items()})
    return out, moved


def pending_deduction(book: Book, facts: Facts) -> float:
    """DPreg якоря при квартальном календаре (М§4.11, §5.7.4): суммы списка «объявлено, не выплачено», вычет
    которых из регуляторного капитала ещё впереди, — так, как их ставит в очередь ядро."""
    if not is_quarterly(book):
        return 0.0
    calendar = make_context(book, facts).prep.calendar
    return sum(amount for _, reg_q, amount in calendar.payable if reg_q >= 1)


def calibrate_capital(X: dict, new_facts: Facts, rwa_fact: float, derived: dict, warnings: list[str],
                      numbers: bool = False, old_prep: Any = None) -> float:
    """Калибровки капитала к якорю (М§15.2 п. 3): вычеты — формулой книги на фактах якоря, плотности RWA и их
    оси — общим множителем к RWA якоря. Возвращает множитель плотностей. `numbers` — записать вычеты числами и
    там, где книга выводит их словом `anchor` (оценка нормативов: уровни капитала якоря — расчёт, не факт).

    При квартальном календаре BVreg якоря несёт DPreg очереди вычетов якоря (М§4.11): вычет Н20.1 считается с
    ним — формула книги берёт вместо него весь остаток дивидендов к выплате при признаке `pre_dividend` и ноль
    без него. Разница стоит в поправке «норматив − расчёт» и на путь норматива не влияет: вычет идёт за RWA.

    Книга с капиталом нормативов банка в фактах (`capital.bank_own_funds`, `capital.bank_main_capital`; книга
    Совкомбанка) выводит вычеты своим правилом (шаг anchor листа вывода): вычет — капитал модели якоря без вычетов
    минус капитал формы, `Ded20 = BVreg + AT1 + T2_0 − собственные средства`, `Ded11 = BVreg − max(E_0, 0) − основной
    капитал`; BVreg, E_0 и T2_0 — те, что ядро ставит в строку якоря (с очередью вычетов дивидендов). Концы осей-связок
    по вычетам (связка с долей признания фонда ССПСД f) — тем же правилом при f конца: `Ded(f_конца) = Ded(f) + (f_конца
    − f) × R`, R — фонд ССПСД нового якоря после налога (`deduction_ends`).

    Вес RWA гарантий (К5: вес риска × масштаб калибровки RWA) — масштаб тех же единиц, что плотности: тем же
    множителем, оси и концы связок — за ним."""
    books = _get(X, "nii.books")
    af = anchor_facts(new_facts, books)
    values, form = deduction_values(X, new_facts, derived, warnings)
    for path in DEDUCTIONS:
        if _get(X, path) != "anchor":
            _set(X, path, _r(values[path], 3))
        elif numbers:                        # уровни капитала якоря — расчёт по оценке: канон фактов несёт на их месте
            _set(X, path, _r(values[path], 3))   # уровни прошлой формы, и слово anchor вывело бы вычеты из них
            warnings.append(f"{path}: книга выводила вычет словом anchor; на время оценки нормативов он записан числом "
                            f"{values[path]:.3f} — вернуть anchor после замены оценки фактом формы (решение книги)")
    deduction_ends(X, form, af)
    roles = book_roles(books)
    if old_prep is not None and (old_prep.guar is not None or old_prep.cash is not None) and not _get(X, f"{FX}.enabled"):
        factors, k_rwa, surprise = structured_rwa(X, old_prep, af, new_facts, rwa_fact, roles)
        derived["rwa_surprise"] = surprise
    else:
        probe = book_from_dict(_without_axes(X), facts=new_facts)
        k_rwa = rwa_fact / rwa_anchor(rwa_weights(probe, roles), af)
        factors = {f"{DENSITY}.{k}": k_rwa for k in X["capital"]["rwa"]["density"]}
        if _num(_get(X, GUAR_WEIGHT)):
            factors[GUAR_WEIGHT] = k_rwa
    centers = _bundle_centers(X, tuple(factors))
    for path, factor in factors.items():
        _set(X, path, _r(float(_get(X, path)) * factor, 6))
    if len(set(factors.values())) == 1:
        _scale_axes(X, (DENSITY,) + ((GUAR_WEIGHT,) if GUAR_WEIGHT in factors else ()), k_rwa)
    else:
        _scale_axes_by(X, factors)
    for path, was in centers.items():
        _follow_centers(X, {path: was}, factors[path])
    derived.update(rwa_factor=k_rwa, rwa_factors=factors, deductions={path: _get(X, path) for path in DEDUCTIONS},
                   deduction_form=form)
    return k_rwa


def _scale_axes_by(X: dict, factors: Mapping[str, float]) -> None:
    """Оси (не связки) по путям `factors` — множителем своего пути; ось по путям с разными множителями — отказ."""
    for where, axes, keys in _axis_lists(X):
        for axis in axes:
            if axis.get("kind") == BUNDLE:
                continue
            paths = [str(p) for p in axis.get("paths") or []]
            hit = [p for p in paths if p in factors or any(_under(p, (f,)) for f in factors)]
            if not hit:
                continue
            got = {factors.get(p, next((factors[f] for f in factors if _under(p, (f,))), None)) for p in hit}
            if len(hit) != len(paths) or len(got) != 1:
                raise ReportError(f"{where} «{axis.get('name')}»: ось двигает {', '.join(paths)} — пересчитываемые "
                                  "разными множителями (или вместе с другими путями); разделить ось (решение книги)")
            factor = got.pop()
            _move_axis(axis, keys, lambda v: _r(v * factor, 6))


def structured_rwa(X: dict, old_prep: Any, af: Any, new_facts: Facts, rwa_fact: float,
                   roles: Any) -> tuple[dict[str, float], float, float]:
    """Плотности RWA нового якоря у книги с RWA гарантий (К5) или неработающими деньгами (К8) — по слагаемым модели
    (docs/REANCHOR.md §3.16). Общий множитель к «сырой» строке якоря (плотности × остатки) разнёс бы по всем книгам то,
    что в RWA квартала стоит в одной статье: вытесненную часть прочих активов (К8, Р6-1: слагаемое
    (1 − θ)(ω′_oa − ω_c) δ_1 L_1) и гарантии сверх выреза (К5: G_1 − G_0 E_c,1 / E_c,0). Поэтому: RWA модели прежней
    книги на остатках нового якоря (квартал 1, дрейф Dn_1) — `RWA_м`; сюрприз k = RWA_факт / RWA_м; плотности книг,
    бумаг, ликвидности, денег, постоянной части и вес гарантий — × k Dn_1; книга выреза — k Dn_1 (ω′_c E_c + G_1) / E_c;
    растущие прочие активы — k Dn_1 [ω′_oa (OA − F − C) + ω_c C + слагаемое] / (OA − F). На отчёте, равном
    ожиданию клетки, k = 1 и строка якоря новой книги — RWA квартала прежней. Возвращает ({путь: множитель}, множитель
    плотностей кредитных книг k Dn_1, k)."""
    w, dn = old_prep.rwa_w, float(old_prep.dn[1])
    E = af.balances
    loans = sum(E[b] for b in roles.loans)
    guar = None
    if old_prep.guar is not None:
        g = old_prep.guar
        if g.base is not None:
            d = _base_level(g.base, E, roles)
        else:                                # строка комиссий за четыре квартала по новый якорь включительно
            periods = sorted(af.pnl, key=pindex)[-4:]
            d = sum(float(af.pnl[p]["fees_net"]) for p in periods)
        guar = g.g0 * d / g.d0
    cash = shift = None
    if old_prep.cash is not None:
        c = old_prep.cash
        cash = (new_facts.need("balance", "nonworking_money.total") if new_facts.has("balance", "nonworking_money.total")
                else (c.share_q[1] if c.share_q else c.share) * _base_level(c.base, E, roles))
        if c.shift_q is not None:
            shift = c.shift_q[1] * loans
    model = w.rwa(E, E[SECURITIES], E[LIQUIDITY], af.other_assets, dn, 1.0, guar=guar, cash=cash, cash_shift=shift)
    k = rwa_fact / model
    scale = k * dn
    dens = X["capital"]["rwa"]["density"]
    factors = {f"{DENSITY}.{name}": scale for name in dens}
    if guar is not None:
        carve = old_prep.guar.carve
        factors[f"{DENSITY}.{carve}"] = scale * (w.loans[carve] * E[carve] + guar) / E[carve] / float(dens[carve])
        if _num(_get(X, GUAR_WEIGHT)):
            factors[GUAR_WEIGHT] = scale
    if cash is not None:
        grow = af.other_assets - w.oa_fixed
        block = w.other_assets_cash * (grow - cash) + w.cash * cash + (shift or 0.0)
        factors[f"{DENSITY}.other_assets"] = scale * block / grow / float(dens["other_assets"])
    return factors, scale, k


def _without_axes(X: Mapping) -> dict:
    """Копия книги без осей полосы — для проб, которые выводят числа якоря: ось-связка по вычетам не допускает на пути
    слово anchor (схема), а оси на выводимые числа не влияют."""
    Y = copy.deepcopy(dict(X))
    unc = Y["valuation"]["uncertainty"]
    unc["axes"], unc["off_band_axes"] = [], []
    return Y


def own_funds_form(facts: Facts) -> bool:
    """Факты якоря несут капитал нормативов банка (форма 0409123): вычеты — правилом книги, а не формулой ядра."""
    return all(facts.has("capital", slot) for slot in OWN_FUNDS)


def deduction_values(X: dict, new_facts: Facts, derived: dict | None = None,
                     warnings: list[str] | None = None) -> tuple[dict[str, float], str]:
    """Вычеты якоря на фактах `new_facts` правилом книги (М§4.11, М§15.2 п. 3): {путь: значение} и форма правила —
    `own_funds` (капитал модели якоря без вычетов минус капитал формы 0409123) или `core` (формула ядра для слова
    anchor с очередью вычетов дивидендов якоря)."""
    books = _get(X, "nii.books")
    af = anchor_facts(new_facts, books)
    if own_funds_form(new_facts):
        from model.cell import anchor_row
        probe_data = _without_axes(X)
        for path in DEDUCTIONS:              # вычеты пробы — любые числа: строка якоря несёт их отдельно от капитала
            if not _num(_get(probe_data, path)):
                _set(probe_data, path, 0.0)
        probe = book_from_dict(probe_data, facts=new_facts)
        ctx = make_context(probe, new_facts)
        row = anchor_row(ctx.prep, ctx, str(probe.get("capital.reg_scenarios.ids")[0]))
        if row["k11"] is None:
            raise ReportError("вычеты якоря: нет неаудированной прибыли якоря (факты pnl_quarterly) — K11 якоря "
                              "не определён (М§4.11)")
        own, main = (new_facts.need("capital", slot) for slot in OWN_FUNDS)
        if derived is not None:
            derived["dpreg_anchor"] = float(row["dpreg"] or 0.0)
        return {DEDUCTIONS[0]: float(row["k20"]) + float(row["ded20"]) - own,
                DEDUCTIONS[1]: float(row["k11"]) + float(row["ded11"]) - main}, "own_funds"
    probe_data = _without_axes(X)
    for path in DEDUCTIONS:
        _set(probe_data, path, "anchor")
    probe = book_from_dict(probe_data, facts=new_facts)
    values = {path: float(probe.anchors[path]) for path in DEDUCTIONS}
    if is_quarterly(probe):
        queue = pending_deduction(probe, new_facts)
        values[DEDUCTIONS[1]] += queue - (af.dividends_payable if af.n20_pre_dividend else 0.0)
        if derived is not None:
            derived["dpreg_anchor"] = queue
        if queue > DIV_TOL and not af.n20_pre_dividend and warnings is not None:
            warnings.append(
                f"на якоре в очереди вычетов из регуляторного капитала стоят объявленные дивиденды {queue:.3f} млрд ₽ "
                "(вычет впереди по датам записи реестра или карте лагов книги), а отчёт помечает норматив как "
                "посчитанный после вычета (capital.n20_pre_dividend: false): модель вычтет их ещё раз в квартале "
                "вычета — проверить дату реестра записи или карту лагов (решение книги)")
    return values, "core"


def deduction_ends(X: dict, form: str, af: Any) -> None:
    """Концы осей-связок по вычетам якоря (`DEDUCTIONS`) — тем же правилом, что центр, при значениях конца прочих
    путей связки. Правило вычетов зависит из чисел книги только от доли признания фонда ССПСД f (BVreg = BV + DPreg −
    (1 − f) R): `Ded(f_конца) = Ded(f) + (f_конца − f) × R` — у обоих вычетов в форме `own_funds` и у вычета второго
    норматива в форме ядра (вычет первого норматива ядра от f не зависит). Связка, у которой рядом с вычетами стоит
    другой путь, — отказ: правила для её конца нет."""
    f = _get(X, FVOCI_RECOGNITION)
    slope = {DEDUCTIONS[0]: float(af.fvoci_reserve) if form == "own_funds" else 0.0,
             DEDUCTIONS[1]: float(af.fvoci_reserve)}
    for where, axis, keys in _bundles(X):
        paths = [str(p) for p in axis.get("paths") or []]
        hit = [p for p in paths if p in DEDUCTIONS]
        if not hit:
            continue
        other = [p for p in paths if p not in DEDUCTIONS]
        if any(p != FVOCI_RECOGNITION for p in other):
            raise ReportError(f"{where} «{axis.get('name')}»: ось-связка двигает вычеты якоря вместе с "
                              f"{', '.join(p for p in other if p != FVOCI_RECOGNITION)} — правило конца вычета знает "
                              "только долю признания фонда ССПСД (решение книги: снять путь с оси)")
        for key in keys:
            ends = axis.get(key)
            if not isinstance(ends, dict):
                continue
            f_end = ends.get(FVOCI_RECOGNITION, f)
            for p in hit:
                ends[p] = _r(float(_get(X, p)) + (float(f_end) - float(f)) * slope[p], 3)


# ------------------------------------------------------------------ ключи проходов ядра 1–5 (docs/REANCHOR.md §3.16)


def _ac_shares(balances: Mapping[str, float], roles: Any, af: Any, fv: float) -> dict[str, float]:
    """Доли кредитных книг в кредитах по амортизированной стоимости (FV — только у книги с долей по СС), М§4.6."""
    ac = {b: balances[b] - (fv if b == af.fv_book else 0.0) for b in roles.loans}
    total = sum(ac.values())
    return {b: v / total for b, v in ac.items()}


def regime_cor_paths(X: Mapping) -> list[str]:
    """Пути CoR режимов (`regimes.<r>.cor`) — траектории в базисе `regimes.cor_basis`."""
    return [f"regimes.{r}.cor" for r in X["regimes"]["ids"] if isinstance(X["regimes"][r].get("cor"), (Mapping, int, float))]


def carry_book_cor(X: dict, old_af: Any, new_af: Any, roles: Any, bridge: Any) -> dict[str, Any] | None:
    """Множители CoR по книгам (М7, М§4.6): нормировка r̂_b = r_b / Σ w_b,0 r_b — на составе кредитов якоря, поэтому путь
    CoR режима — CoR «на составе якоря». На новом якоре состав другой, и те же числа путей дали бы другую CoR каждой
    книги — сдвиг резервов всего пути без новости. Правило переноса — запись того же суждения на составе нового якоря:
    CoR клетки в базисе движка умножается на f = Σ w_b,1 r_b / Σ w_b,0 r_b (тогда r̂′_b × CoR′ = r̂_b × CoR у каждой
    книги): ключи путей режимов `v′ = f v + (f − 1) b` (мост CoR аддитивный: движок = упр. + b; у моста-отношения и
    базиса движка — `v′ = f v`), κ′ = f κ (κ-добавка стоит на всей CoR клетки). Оси по этим путям: сдвиг — × f, вид
    value и концы связок — за центром с наклоном f. Отклонение A-P2u δ (из наблюдений) правилу не следует: остаток
    (1/f − 1) δ — в строке «механика». Сырые множители r_b — суждение книги, не трогаются. Нет ключа — None."""
    spec = _get(X, BOOK_REL)
    if not isinstance(spec, Mapping) or spec.get("enabled") is not True:
        return None
    raw = {b: float(v) for b, v in spec["by_book"].items()}
    w0 = _ac_shares(old_af.balances, roles, old_af, old_af.fv_loans)
    w1 = _ac_shares(new_af.balances, roles, new_af, new_af.fv_loans)
    f = sum(w1[b] * raw[b] for b in roles.loans) / sum(w0[b] * raw[b] for b in roles.loans)
    basis = str(_get(X, "regimes.cor_basis", "engine"))
    additive = basis == "mgmt" and bridge.cor_method == "additive"
    b = float(bridge.cor_value) if additive else 0.0
    paths = regime_cor_paths(X)
    kappa = (KAPPA,) if _num(_get(X, KAPPA)) else ()
    centers = _bundle_centers(X, tuple(paths) + kappa)
    singles = {str(p): _leaf(X, str(p)) for _, axes, _ in _axis_lists(X) for axis in axes
               if axis.get("kind") == "value" for p in axis.get("paths") or [] if _under(str(p), paths + list(kappa))}
    for path in paths:
        traj = _get(X, path)
        if _num(traj):
            _set(X, path, _r(f * traj + (f - 1) * b, 6))
        else:
            _set(X, path, {k: (v if str(k) == "LT_from" else _r(f * float(v) + (f - 1) * b, 6)) for k, v in traj.items()})
    if kappa:
        _set(X, KAPPA, _r(f * float(_get(X, KAPPA)), 6))
    for where, axes, keys in _axis_lists(X):
        for axis in axes:
            kind, ax_paths = axis.get("kind"), [str(p) for p in axis.get("paths") or []]
            hit = [p for p in ax_paths if _under(p, paths + list(kappa))]
            if kind == BUNDLE or not hit:
                continue
            if len(hit) != len(ax_paths):
                raise ReportError(f"{where} «{axis.get('name')}»: ось двигает пути CoR режимов вместе с "
                                  f"{', '.join(p for p in ax_paths if p not in hit)} — правило переноса состава "
                                  "кредитов (М7) их не знает; разделить ось (решение книги)")
            if kind == "shift":
                _move_axis(axis, keys, lambda v: _r(v * f, 6))
            elif kind == "value" and len(ax_paths) == 1 and _num(singles.get(ax_paths[0])):
                was, now = float(singles[ax_paths[0]]), float(_leaf(X, ax_paths[0]))
                _move_axis(axis, keys, lambda v, was=was, now=now: _r(now + f * (v - was), 6))
            else:
                raise ReportError(f"{where} «{axis.get('name')}»: ось вида {kind} по путям CoR режимов — правила "
                                  "переноса состава кредитов (М7) для неё нет (решение книги)")
    _follow_centers(X, centers, f)
    return {"factor": f, "bridge": b, "shares_old": w0, "shares_new": w1}


def _component_level(base: Any, balances: Mapping[str, float], roles: Any) -> float:
    """Уровень компоненты смеси базы строки на конец квартала (К2б, М§4.7): слово loans | funds | iea (веса 1 на книгах
    роли; средства клиентов — с ведомыми книгами К6) или веса книг ЧПД."""
    if isinstance(base, Mapping):
        return sum(float(w) * balances[str(b)] for b, w in base.items())
    books = {"loans": roles.loans, "funds": roles.funds, "iea": roles.assets}[str(base)]
    return sum(balances[b] for b in books)


def _mix_map(shares: Mapping[str, float], growth: Mapping[str, float]) -> dict[str, float]:
    """Доли строки на якоре по компонентам на новом якоре: s′_k = s_k g_k / Σ s_j g_j (g_k — рост уровня компоненты за
    квартал на концах кварталов); последняя доля — остатком до единицы (сумма смеси — единица в допуске ядра)."""
    total = sum(float(shares[k]) * growth[k] for k in shares)
    names = list(shares)
    out = {k: _r(float(shares[k]) * growth[k] / total, 9) for k in names[:-1]}
    out[names[-1]] = _r(1.0 - sum(out.values()), 12)
    return out


def carry_line_mix(X: dict, old_af: Any, new_af: Any, roles: Any) -> dict[str, dict]:
    """Смеси баз строк (К2б, М§4.7): доли s_k — доли строки на якоре по базам-компонентам, и ядро нормирует компоненты
    на остатках якоря (D^k_0). На новом якоре база строки идёт тем же путём, только если доли переписаны на состав
    нового якоря: `s′_k = s_k g_k / Σ s_j g_j`, g_k = D^k_1 / D^k_0 — тогда база новой книги пропорциональна базе прежней
    на всех кварталах (рост тот же; RWA гарантий К5 и ведомые книги К6 читают ту же базу). Концы осей-связок по долям —
    тем же правилом при долях конца (прочие доли конца — центр; сумма конца — единица, иначе отказ). Ось вида value
    по одной доле — отказ (одно число доли смесь не задаёт). Возвращает {ключ: {было, стало}}."""
    out: dict[str, dict] = {}
    for key in LINE_MIX:
        spec = _get(X, key)
        if not (isinstance(spec, Mapping) and isinstance(spec.get("mix"), Mapping)):
            continue
        mix = spec["mix"]
        growth = {k: _component_level(c["base"], new_af.balances, roles)
                  / _component_level(c["base"], old_af.balances, roles) for k, c in mix.items()}
        before = {k: float(c["share"]) for k, c in mix.items()}
        after = _mix_map(before, growth)
        for k, v in after.items():
            mix[k]["share"] = v
        out[key] = {"was": before, "now": after, "growth": growth}
        share_paths = {f"{key}.mix.{k}.share": k for k in mix}
        for where, axes, keys in _axis_lists(X):
            for axis in axes:
                ax_paths = [str(p) for p in axis.get("paths") or []]
                hit = [p for p in ax_paths if p in share_paths]
                if not hit:
                    continue
                if axis.get("kind") != BUNDLE:
                    raise ReportError(f"{where} «{axis.get('name')}»: ось вида {axis.get('kind')} по доле смеси {key} — "
                                      "одно число доли смесь не задаёт; правило переноса — только у оси-связки по долям")
                for end in keys:
                    ends = axis.get(end)
                    if not isinstance(ends, dict):
                        continue
                    vec = {k: float(ends.get(p, before[k])) for p, k in share_paths.items()}
                    if abs(sum(vec.values()) - 1.0) > 1e-6:
                        raise ReportError(f"{where} «{axis.get('name')}»: доли смеси {key} на конце {end} в сумме "
                                          f"{sum(vec.values()):.6g}, не единица — переписать их на новый якорь нечем")
                    mapped = _mix_map(vec, growth)
                    for p in hit:
                        ends[p] = _r(mapped[share_paths[p]], 6)
    return out


def carry_line_shares(X: dict, old_prep: Any, old_af: Any, new_af: Any, roles: Any) -> dict[str, Any] | None:
    """Доли базы расходов якоря на базах строк (`opex.line_shares`, К2, М§4.7): `A^C_x = (1 − Σ s) B^C_x + Σ s_ℓ B^C_0
    A^ℓ_x / A^ℓ_0` — ступени на якоре нет, и доли s_ℓ — доли «квартала якоря». На новом якоре база расходов идёт тем же
    путём при `s′_ℓ = s_ℓ a_ℓ / T`, `T = (1 − Σ s) b + Σ s_ℓ a_ℓ`, где a_ℓ и b — рост за квартал средних базы строки ℓ и
    базы расходов (М13 или link_base) от квартала прежнего якоря к кварталу нового — тем же весам и тем же средним
    концов, что ядро возьмёт из фактов нового якоря. Ключ не читается (связь расходов ноль) или его нет — None."""
    shares = old_prep.line_shares
    raw = _get(X, LINE_SHARES)
    if not shares or not isinstance(raw, Mapping):
        return None

    def avg(level) -> tuple[float, float]:    # средние квартала прежнего якоря (по фактам) и нового (концы якорей)
        return level(old_af.balances), (level(old_af.balances) + level(new_af.balances)) / 2

    def books_level(weights: Mapping[str, float]):
        return lambda bal: sum(float(w) * bal[b] for b, w in weights.items())

    def word_level(kind: str):
        books = {"loans": roles.loans, "funds": roles.funds, "iea": roles.assets}[kind]
        return lambda bal: sum(bal[b] for b in books)

    if old_prep.opex_w is not None:
        b_old, b_level = old_prep.hist_vol_opex[0], books_level(old_prep.opex_w)
    else:
        b_old, b_level = old_prep.hist_vol[0], word_level(old_prep.link_base)
    b_ratio = avg(b_level)[1] / b_old
    lines = {"fees": old_prep.fees_line, "insurance": old_prep.ins_line}
    a_ratio = {}
    for line in shares:
        base = lines[line]
        if base is None:                     # строка на link_base: та же база, что у расходов без весов М13
            a_old, level = old_prep.hist_vol[0], word_level(old_prep.link_base)
        elif base.kind == "books":
            a_old, level = base.hist[0], books_level(base.weights)
        elif base.kind == "nominal":
            raise ReportError(f"{LINE_SHARES}.{line}: база строки — номинал (индекс зарплат мира), её средний уровень "
                              "квартала по остаткам книг не определён — правила переноса доли нет (решение книги)")
        else:
            a_old, level = base.hist[0], word_level(base.kind)
        a_ratio[line] = avg(level)[1] / a_old
    keep = 1.0 - sum(shares.values())
    total = keep * b_ratio + sum(s * a_ratio[line] for line, s in shares.items())
    before = {k: float(v) for k, v in raw.items()}
    for line, s in shares.items():
        raw[line] = _r(s * a_ratio[line] / total, 9)
    return {"was": before, "now": {k: float(v) for k, v in raw.items()}, "line_growth": a_ratio, "base_growth": b_ratio}


def carry_cash_share(X: dict, period: str, rule: bool = True) -> tuple[str, str] | None:
    """Доля неработающих денег книги (К8, Р6-1): путь доли — от доли якоря линейно до квартала `share_from`. Правило
    Р7-6 (решения ведущего № 7): квартал доли книги на новом якоре — квартал якоря + 2 (путь снова идёт два квартала от
    факта нового якоря). `rule=False` — путь прежней книги (строка «механика»): квартал прежний, если он позже нового
    якоря, иначе — первый прогнозный. Нет числовой доли книги — None. Возвращает (было, стало)."""
    spec = _get(X, CASH)
    if not isinstance(spec, Mapping) or spec.get("share") in (None, "anchor") or spec.get("share_from") is None:
        return None
    was = str(spec["share_from"])
    if rule:
        now = period_str(*shift_quarter(*parse_period(period), CASH_LEAD))
    else:
        now = was if pindex(was) > pindex(period) else next_period(period)
    spec["share_from"] = now
    return was, now


def carry_cash_structure(X: dict, old_prep: Any, new_af: Any, new_facts: Facts, roles: Any) -> dict[str, float] | None:
    """Доля денег книги (К8, Р6-1) стоит на структуре якоря: растущие прочие активы без денег на рубль кредита
    ρ′_q = ρ − c_q D_0 / L_0, где ρ = `volumes.other_assets_to_loans` (anchor — (OA_0 − F) / L_0) и D_0 / L_0 —
    отношение драйвера денег к кредитам на якоре. На новом якоре отношение другое (a_1 = D_1 / L_1 вместо a_0), и при
    ρ нового якоря прочие активы пути отличались бы от прежнего на (c_q − c_1)(a_1 − a_0) L_q — сдвиг баланса без
    новости. Правило: ρ записывается числом `ρ_1 + (c* − c_1)(a_1 − a_0)` (ρ_1 — отношение нового якоря, c* = s* + r —
    доля книги с ФОР, c_1 — доля нового якоря): с квартала доли книги путь прочих активов — прежний; на якоре
    остаток — факт, и отношение факта (сюрприз прочих активов) остаётся в пути, как у слова anchor. Ключ ρ —
    `anchor` или число, записанное прежним переносом: правило одно. Доля якоря (`share: anchor`) или ключа нет —
    None."""
    spec = _get(X, CASH)
    if (not isinstance(spec, Mapping) or spec.get("share") in (None, "anchor") or old_prep.cash is None
            or old_prep.cash.share_q is None):
        return None
    c = old_prep.cash
    loans0 = sum(old_prep.af.balances[b] for b in roles.loans)
    loans1 = sum(new_af.balances[b] for b in roles.loans)
    a0 = c.base.end0 / loans0
    d1 = _base_level(c.base, new_af.balances, roles)
    a1 = d1 / loans1
    cash1 = (new_facts.need("balance", "nonworking_money.total") if new_facts.has("balance", "nonworking_money.total")
             else c.share_q[1] * d1)
    c1 = cash1 / d1
    c_star = float(spec["share"]) + float(c.reserves)
    fixed = float(old_prep.rwa_w.oa_fixed)
    rho1 = (new_af.other_assets - fixed) / loans1
    value = _r(rho1 + (c_star - c1) * (a1 - a0), 9)
    _set(X, "volumes.other_assets_to_loans", value)
    return {"rho_anchor": rho1, "rho": value, "a_old": a0, "a_new": a1, "c_new": c1, "c_star": c_star}


def carry_buyback(X: dict, period: str) -> dict[str, list[str]] | None:
    """Выкуп по цене мира (М3, М§5.6): закрытый квартал — история. Его покупки уже в фактах нового якоря (капитал после
    выкупа, акции в обращении — делитель), поэтому цена закрытого квартала `closed_prices` уходит (ядро читает её только
    у кварталов сетки до квартала даты книги), а ключ суммы закрытого квартала `amount` — тоже, если без него значения
    кварталов новой сетки те же (иначе остаётся и называется) и его не называет путь оси (полоса, оси вне полосы,
    обратный расчёт): ось «выкуп по сроку» — связка по ключам кварталов, её путь закрытого квартала остаётся в книге
    (конец оси закрытый квартал не двигает — его сетка не читает). Выкупа нет или выключен — None."""
    spec = _get(X, BUYBACK)
    if not isinstance(spec, Mapping) or spec.get("enabled") is not True:
        return None
    gone: dict[str, list[str]] = {"closed_prices": [], "amount": []}
    closed = spec.get("closed_prices")
    if isinstance(closed, Mapping):
        for key in [k for k in closed if pindex(str(k)) <= pindex(period)]:
            closed.pop(key)
            gone["closed_prices"].append(str(key))
        if not closed:
            spec.pop("closed_prices")
    amount = spec.get("amount")
    if isinstance(amount, Mapping):
        last = str(X["meta"]["last_period"])
        quarters = [parse_period(period_str(*shift_quarter(*parse_period(period), i)))
                    for i in range(1, pindex(last) - pindex(period) + 1)]
        old = Trajectory(amount)
        on_axes = {str(p) for _, axes, _ in _axis_lists_of(X) for axis in axes for p in axis.get("paths") or []}
        dead = [k for k in amount if "Q" in str(k) and pindex(str(k)) <= pindex(period)
                and f"{BUYBACK}.amount.{k}" not in on_axes]
        trimmed = {k: v for k, v in amount.items() if k not in dead}
        try:
            same = bool(dead) and all(Trajectory(trimmed).value(y, q) == old.value(y, q) for y, q in quarters)
        except BookError:                    # без ключа траектория не читается — ключ остаётся
            same = False
        if same:
            spec["amount"] = trimmed
            gone["amount"] = [str(k) for k in dead]
    return gone


def dividend_carry(old: GridRun, new: GridRun) -> dict[str, Any]:
    """Дивиденды по периодам при переносе якоря (раздел REANCHOR.md, М§15.2 п. 9): последний закрытый квартал
    прибыли до и после, строки истории, закрывшие кварталы, очередь «объявлено, не выплачено» с кварталами
    выплаты и вычета из регуляторного капитала, записи реестра — перешедшие в затравку и выпавшие из неё."""
    tl0, tl1 = old.ctx.timeline, new.ctx.timeline
    c0, c1 = old.ctx.prep.calendar, new.ctx.prep.calendar
    day0, day1 = (to_date(r.ctx.book.get("meta.facts_date")) for r in (old, new))
    f0, f1 = old.ctx.facts.file("dividends"), new.ctx.facts.file("dividends")
    closed = []
    for row in f1.get("history") or []:
        decided = _fact(row.get("decided_date"))
        if decided and day0 < to_date(decided) <= day1:
            closed.append({"period": str(_fact(row.get("period"))), "dps": history_dps(row), "decided_date": str(decided)})
    queue = []
    items = new.ctx.facts.file("balance").get("dividends_payable_declared") or []
    for item, (pay_q, reg_q, amount) in zip(items, c1.payable):
        queue.append({"period": str(_fact(item.get("period"))), "amount": amount, "pay": tl1.period(pay_q),
                      "reg": tl1.period(reg_q) if reg_q >= 1 else None})
    seeds = [{str(_fact(r.get("period"))) for r in f.get("register_seed") or []} for f in (f0, f1)]
    return {"p_last": (tl0.period(c0.p_last), tl1.period(c1.p_last)), "closed": closed, "queue": queue,
            "payable": new.ctx.prep.af.dividends_payable,
            "seed": sorted(seeds[1], key=pindex), "dropped": sorted(seeds[0] - seeds[1], key=pindex),
            "added": sorted(seeds[1] - seeds[0], key=pindex)}


@dataclass(frozen=True)
class CellRun:
    """Прогон одной клетки на общем контексте книги: всё, что перезаякоривание клетки на своём пути читает из
    прогона кандидата (контекст, строка якоря сценария, ряды клетки), — без остальных клеток сетки."""

    ctx: Any
    cells: tuple
    layers: Mapping[str, Any] = field(default_factory=dict)   # слои прогона, из которого взяты клетки (вероятности)

    def cell(self, world: str, regime: str, scenario: str) -> Any:
        for c in self.cells:
            if c.key == (world, regime, scenario):
                return c
        raise KeyError((world, regime, scenario))


def candidate_run(data: Mapping, facts: Facts, cell: Sequence[str] | None) -> Any:
    """Прогон кандидата `data` на фактах нового якоря: вся сетка, а у клетки на своём пути — она одна (клетки
    сетки независимы при общем контексте: числа клетки те же, что в полном прогоне)."""
    book = book_from_dict(data, facts=facts)
    if cell is None:
        return run_grid(book, facts)
    ctx = make_context(book, facts)
    return CellRun(ctx=ctx, cells=(run_cell(ctx, *cell),))


def reanchor(book: Book, facts: Facts, report: Mapping, *, valuation_date: Any = None,
             version: str | None = None, near: Any = None, cell: Sequence[str] | None = None,
             base_run: GridRun | None = None, observation: Mapping | None = None,
             observe: bool = True, update_bridge: bool | None = None,
             transmission: str = KEEP, marked: Sequence[str] | None = None, book_rules: bool = True) -> Reanchored:
    """Книга и факты-кандидат на отчёте `report` (формат — шапка модуля).

    `near` — готовая ближняя калибровка ЧПМ (у фактического отчёта — та, что выведена на
    ожидаемом); без неё калибровка выводится здесь: ожидаемый путь ЧПМ кандидата совпадает с
    путём `base_run` (прежняя книга с наблюдением отчёта) — по слою «свой взгляд» или по клетке
    `cell` (перезаякоривание клетки на своём пути). `observation` — наблюдение A-P2u вместо
    упр. ЧПМ и CoR отчёта (у клетки на своём пути — то же, что у прежней книги);
    `observe=False` — без наблюдения. `transmission`: `keep` — скаляры пути σ0_A, σ0_L, φ_A, φ_L
    прежней книги сохраняются, цели A-N2, A-N3 и обе доли пересчитываются на структуру нового
    якоря (режим процедуры, М§15.2 п. 8); `resolve` — только диагностика: цели и доли не
    трогаются, ядро решает скаляры заново на новой структуре. `marked` — ключи книги, выведенные на ядре
    (`derived_on_core` по шаблону книги): перечень в ручных шагах — по самой книге. `book_rules=False` — без правил
    книги, которые двигают путь намеренно (квартал доли денег книги К8 = якорь + 2, Р7-6): путь прежней книги, по
    нему меряется строка «механика»; цена правила — своя строка разложения.
    """
    if transmission not in TRANSMISSION_MODES:
        raise ReportError(f"transmission {transmission!r}: известны {', '.join(TRANSMISSION_MODES)}")
    check_report(book, facts, report)
    period = str(report["period"])
    first_new = next_period(period)
    end = period_end(period)
    old_anchor = str(book.get("meta.anchor_period"))
    year_shift = parse_period(period)[0] - parse_period(old_anchor)[0]
    warnings: list[str] = []
    derived: dict[str, Any] = {"year_shift": year_shift, "transmission_mode": transmission}
    X = copy.deepcopy(dict(book.source))
    M = X["meta"]
    row_keys, refine = _row_keys(X), copy.deepcopy(_get(X, REFINE_ROWS))   # строки обратного расчёта прежней книги

    # --- дата оценки и meta
    vdate = valuation_day(valuation_date, report)
    M.update(anchor_period=period, first_period=first_new, facts_date=end.isoformat(),
             valuation_date=vdate.isoformat(), version=version or f"{M['version']}+{period}")
    if _get(X, f"{BUYBACK}.enabled") is True and str(book.get("meta.valuation_date")) != vdate.isoformat():
        # выкуп по цене мира (М3, М§5.6): форвард цены покупок идёт от цены книги на дату книги — дата и цена одна пара;
        # перенос якоря цену не обновляет, поэтому и дату оставляет: иначе путь акций клетки сдвинулся бы без новости
        M["valuation_date"] = str(book.get("meta.valuation_date"))
        warnings.append(
            f"meta.valuation_date оставлен {M['valuation_date']} (дата оценки кандидата {vdate}): у книги выкуп по цене "
            f"мира ({BUYBACK}), его форвард цены идёт от цены книги meta.market_price на дату книги — обновить "
            "meta.market_price, meta.date и meta.valuation_date вместе (решение книги, М§5.6)")

    # --- наблюдение закрытого квартала
    obs = dict(observation) if observation is not None else {
        "period": period, "cor": float(report["mgmt"]["cor"]), "nim": float(report["mgmt"]["nim"]),
        "se_cor": 0.0, "se_nim": 0.0, "basis": "mgmt"}
    if observe:
        replaced = [o for o in book.get(OBS) or [] if str(o["period"]) == period]
        if replaced:
            warnings.append(f"наблюдение {period} прежней книги ({replaced[0]}) заменено фактом отчёта")
        derived["observation"] = carry_observation(X, book, facts, obs)

    # --- прежняя книга с тем же наблюдением: путь, с которым сверяется кандидат
    if base_run is None:
        base_run = run_grid(with_observation(book, obs) if observe else book, facts)
    if base_run.ctx.timeline.index(period) != 1:
        raise ReportError("base_run — не прогон прежней книги: квартал отчёта у него не первый прогнозный")
    kappa_note = lost_kappa(book, base_run)
    base_run = history_run(book, base_run, cell)     # путь прежней книги, каким его увидит новый якорь (М§4.6)
    weights = _weights(base_run, cell)

    # --- цены якоря
    if "price_index" in report["market"]:
        factor = float(report["market"]["price_index"])
    else:
        factor = sum(float(book.get(f"joint.world_prob.{w}")) * base_run.ctx.worlds[w].price_index[1]
                     for w in book.get("worlds.ids"))
        derived["price_index_source"] = "ожидаемый индекс миров книги"
    derived["price_index"] = factor
    reindex_prices(X, facts, period, factor)
    carry_fx(X, factor)
    if year_shift:
        X["noncore"]["price_base_year"] = int(X["noncore"]["price_base_year"]) + year_shift

    # --- anchor-ключи с лагом — числами прежней книги
    freeze_anchors(X, book)
    derived["frozen"] = {k: _get(X, k) for k in FROZEN_ANCHORS}

    # --- смена года якоря, справочные ключи
    renamed = shift_crisis(X, year_shift)
    carry_refine_rows(X, refine, row_keys)
    if year_shift:
        warnings.append(
            f"год якоря сменился ({parse_period(old_anchor)[0]} → {parse_period(period)[0]}): кризисные "
            "ключи сдвинуты вместе с годом шока — режим «перезаряжен», и строки «механика» и «выпуклость» "
            "ненулевые по определению стационарных режимов (М§3.2). Замороженные μ наблюдений окна не "
            "пересчитываются (М§12): наблюдение закрытого квартала судится против ожидания прежней книги — "
            "с шоком, и несостоявшийся шок остаётся свидетельством против перезаряженного режима, пока запись "
            "не выйдет из окна; снизу — пол вероятности режима. Сдвиг точки на ожидаемом отчёте (строки "
            "«обучение», «механика» и «выпуклость» сухого прогона) и строка «обучение» отчёта без шока — в "
            "журнал версии книги. Гайденс нового "
            "года (volumes.guidance_year, guidance_growth, fees.growth_override) — решение книги")
    first_year = parse_period(first_new)[0]
    if int(X["nii"]["sigma0_from"]) < first_year:
        X["nii"]["sigma0_from"] = first_year
    if "next_report" in X["valuation"]:
        X["valuation"]["next_report"]["period"] = first_new
    # закрытый квартал выкупа — история (М3); квартал доли денег книги К8 — правилом Р7-6 (docs/REANCHOR.md §3.16)
    derived["buyback"] = carry_buyback(X, period)
    derived["cash_share_from"] = carry_cash_share(X, period, rule=book_rules)

    # --- оценка нормативов до выхода формы: уровни капитала и RWA якоря — расчётом по оценке, не уровнями прошлой формы
    if report["capital"].get("estimated") is True:
        report, derived["estimated_levels"] = estimated_levels(book, facts, report, base_run, weights)
        warnings.append(
            "уровни капитала и RWA якоря посчитаны по оценке нормативов на RWA модели (плотности × остатки нового якоря "
            "× ожидаемый дрейф): " + "; ".join(
                f"{k} {'—' if a is None else format(float(a), '.3f')} → {b:.3f}" for k, (a, b) in derived["estimated_levels"].items())
            + " — значения отчёта на этих слотах (уровни последней формы) в калибровку не входят; факт придёт с формой")

    # --- факты нового якоря
    quarterly = is_quarterly(book)
    new_facts = facts_after(book, facts, report,
                            update_bridge=(cell is None) if update_bridge is None else update_bridge)
    books = book.get("nii.books")
    old_af, new_af = anchor_facts(facts, books), anchor_facts(new_facts, books)
    if quarterly and report["balance"].get("dividends_payable_year") is not None:
        warnings.append("balance.dividends_payable_year отчёта не прочитан: у книги квартальный календарь дивидендов — "
                        "объявленное и не выплаченное несёт список balance.dividends_payable_declared по периодам")
    if not quarterly and (report.get("dividend_decisions") or report["balance"].get("dividends_payable_declared")):
        warnings.append("dividend_decisions и balance.dividends_payable_declared отчёта не прочитаны: у книги годовой "
                        "календарь дивидендов — год объявленного дивиденда несёт balance.dividends_payable_year")
    if new_af.estimated:
        warnings.append(
            "нормативы якоря стоят оценкой до выхода формы (capital.estimated): вычеты и поправки «норматив − расчёт» "
            "выведены на оценке; когда форма выйдет — замена оценки фактом без смены якоря: "
            "`reanchor.py --capital-form ФАЙЛ` на кандидате, перенесённом в канон (docs/REANCHOR.md)")
    if report["pnl"].get("estimated") is True:
        warnings.append("прибыль квартала стоит напечатанным значением (pnl.estimated): строки прибыли фактов кандидата "
                        "несут пометку оценки; точные значения — правкой фактов без смены якоря (docs/REANCHOR.md)")

    # --- ключи спредов от ставок якоря
    derived["spread_books"] = rederive_spreads(X, book, old_af.rates, new_af.rates)

    # --- инструменты капитала: книга, которая пишет ключ квартала якоря явно, получает ключ нового якоря — факт
    carry_t2(X, old_anchor, period, report["capital"].get("t2"), derived, warnings)

    # --- капитал: вычеты формулой книги, плотности RWA — общим множителем к RWA якоря
    calibrate_capital(X, new_facts, float(report["capital"]["basel_rwa"]), derived, warnings,
                      numbers="estimated_levels" in derived, old_prep=base_run.ctx.prep)

    # --- ключи проходов ядра 1–5, привязанные к якорю (docs/REANCHOR.md §3.16)
    roles = book_roles(books)
    derived["book_cor"] = carry_book_cor(X, old_af, new_af, roles, bridge_from_facts(facts))
    derived["line_mix"] = carry_line_mix(X, old_af, new_af, roles)
    derived["line_shares"] = carry_line_shares(X, base_run.ctx.prep, old_af, new_af, roles)
    derived["cash_structure"] = carry_cash_structure(X, base_run.ctx.prep, new_af, new_facts, roles)
    if derived["cash_structure"]:
        touched_cash = [str(v.get("id")) for v in _get(X, VARIANTS) or []
                        if any(_under(str(p), (CASH,)) for p in (v.get("overrides") or {}))]
        if touched_cash:
            warnings.append(
                f"справочные варианты {', '.join('«' + v + '»' for v in touched_cash)} меняют ключ денег {CASH}, а "
                "`volumes.other_assets_to_loans` записан числом на структуре нового якоря для доли денег книги (К8): "
                "вариант без доли книги (share: anchor, другой драйвер) читает ρ слова anchor — добавить к его подменам "
                "`volumes.other_assets_to_loans: anchor` (решение книги)")
    carried = (regime_cor_paths(X) if derived["book_cor"] else []) + [
        f"nii.books.{name}.spread" for name in derived["spread_books"]]   # концы — правилом спреда (`spread_ends`)

    # --- передача ставки: скаляры пути прежней книги на структуре нового якоря
    kept_axes = {path: [{k: copy.deepcopy(axis[k]) for k in keys if k in axis}
                        for axis, keys in _value_axes(X, path)] for path in TRANSMISSION_KEYS}
    derived["transmission"] = keep_transmission(X, new_facts, base_run)
    level_gate = carry_level_gate(X, derived["transmission"])
    check_bundles(X, book.source, renamed, carried)

    # --- поправки «норматив − расчёт» и ближняя калибровка ЧПМ: по прогону кандидата
    periods = [period_str(*shift_quarter(*parse_period(first_new), i))
               for i in range(pindex(str(M["last_period"])) - pindex(first_new) + 1)]
    last_year = parse_period(str(M["last_period"]))[0]
    target = [_mean(base_run, weights, "nim", q + 1) for q in range(1, len(periods) + 1)]
    fact = {"n20": float(report["capital"]["n20_0"]), "n11": float(report["capital"]["n1_1_bank"])}
    if near is not None:
        set_near(X, copy.deepcopy(near), warnings)
        carry_refine_rows(X, refine, row_keys)
    old_near = book.source["regimes"]["near_nim_shift"]
    moved, detail = 0.0, 0
    for step in range(PASSES):               # повторы добирают второй порядок (ЧПД → капитал → баланс → ЧПМ)
        run = candidate_run(X, new_facts, cell)
        moved = 0.0
        for path, name in GAPS:
            delta = fact[name] - _anchor_row(run, weights, name)
            if abs(delta) > GAP_TOL:
                value = float(_get(X, path))
                _set(X, path, _r(value + delta, 12))
                _remap_axes(X, path, value, value + delta)
                moved = max(moved, abs(delta))
        if near is None:
            got = [_mean(run, weights, "nim", q) for q in range(1, len(periods) + 1)]
            before = X["regimes"]["near_nim_shift"]
            t_near = Trajectory(before)
            values = [t_near.value(*parse_period(p)) - (g - t) for p, g, t in zip(periods, got, target)]
            after = near_trajectory(old_near if step == 0 else before, periods, values, last_year, detail)
            detail = max([detail] + [parse_period(k)[0] for k in after if "Q" in k])
            set_near(X, after, warnings if step == 0 else None)
            carry_refine_rows(X, refine, row_keys)
            was = before if isinstance(before, Mapping) else {}
            moved = max([moved] + [abs(float(after.get(k, 0.0)) - float(was.get(k, 0.0)))
                                   for k in set(after) | set(was)])
            moved = moved if step else 1.0   # первый проход — от прежней траектории: всегда повторить
        if moved < NEAR_TOL / 2:
            break
    else:
        warnings.append(f"калибровка к якорю не сошлась за {PASSES} проходов (последний сдвиг ключа {moved:.2e}): "
                        "ожидаемый путь ЧПМ кандидата совпадает с путём прежней книги не во всех кварталах — остаток "
                        "печатается в производных величинах, эффект — в строке «механика»")
    carry_refine_rows(X, refine, row_keys, warnings)
    cand = book_from_dict(X, facts=new_facts)
    run = candidate_run(X, new_facts, cell)
    if near is None:
        got = [_mean(run, weights, "nim", q) for q in range(1, len(periods) + 1)]
        derived["nim_path"] = {"periods": periods, "old": target, "new": got,
                               "residual": max(abs(g - t) for g, t in zip(got, target))}
    if transmission == RESOLVE:              # диагностика: цели, доли и их оси — прежней книги, скаляры решает ядро
        for path in TRANSMISSION_KEYS:
            _set(X, path, _get(book.source, path))
            for (axis, _), before in zip(_value_axes(X, path), kept_axes[path]):
                axis.update(before)
        if level_gate:
            _set(X, GATE_TARGET, level_gate[0])
        cand = book_from_dict(X, facts=new_facts)
        run = candidate_run(X, new_facts, cell)
    eng = engine_ratios(book, facts, report)
    bridges = bridge_from_facts(facts), bridge_from_facts(new_facts)
    derived.update(
        gaps={path: _get(X, path) for path, _ in GAPS},
        anchor_row={name: _anchor_row(run, weights, name) for _, name in GAPS},
        engine={k: eng[k] for k in ("nim", "cor", "cir")}, mgmt=dict(report["mgmt"]),
        bridge_old={x: getattr(bridges[0], f"{x}_value") for x in ("cor", "nim", "cir")},
        bridge_new={x: getattr(bridges[1], f"{x}_value") for x in ("cor", "nim", "cir")},
        posterior=dict(run.ctx.posterior),
        sigmas={"old": _sigmas(base_run.ctx.transmission), "new": _sigmas(run.ctx.transmission)},
        phi_weights={"old": dict(base_run.ctx.transmission.phi_weights),
                     "new": dict(run.ctx.transmission.phi_weights)},
        regime_floor=regime_floor(book, run.ctx.posterior))
    if "cir" not in report["mgmt"]:
        warnings.append("в отчёте нет mgmt.cir: история моста C/I останется без закрытого квартала, и годовой "
                        "C/I года якоря в упр. базисе (гейт guidance_gap, выпуск) на фактах кандидата не "
                        "соберётся (М§4.6) — внести C/I презентации")
    if quarterly:
        derived["dividends"] = dividend_carry(base_run, run)
    rule = growth_rule(book)
    if rule is not None and rule.catch_up > 0:
        warnings.append(
            f"навёрстывание роста включено ({CATCH_UP} = {rule.catch_up:g}): клетка помнит разрыв с потенциальным "
            "путём кредитных книг, а факты якоря — нет. Потенциальный путь стартует с факта нового якоря (М§4.13.1), "
            "и у клеток, где рост был урезан до якоря, перенос стирает разрыв: их строка «механика» не ноль")
    if kappa_note:
        warnings.append(kappa_note)
    derived["level"] = level_shift(base_run.ctx, run.ctx, gate=None if transmission == RESOLVE else level_gate)
    if derived["level"]:
        warnings.append(level_note(derived["level"]))
    derived["stationary"] = stationary_shift(base_run.ctx, run.ctx)
    if derived["stationary"] and not (derived["level"] and derived["level"]["world"] == derived["stationary"]["world"]):
        warnings.append(stationary_note(derived["stationary"], level=derived["level"]))
    changes = diff(dict(book.source), X)
    warnings += manual_steps(book, X, marked=marked, changes=changes, first_new=first_new, report=report,
                             facts=facts)
    return Reanchored(data=X, book=cand, facts=new_facts, period=period, derived=derived,
                      changes=changes, warnings=warnings,
                      near=copy.deepcopy(X["regimes"]["near_nim_shift"]))


def regime_floor(book: Book, posterior: Mapping[str, float]) -> dict[str, Any]:
    """Пол вероятности режима (М§12): `floor_share` × базовая; режимы, стоящие на полу после наблюдений."""
    share = float(book.get("joint.regime_update.floor_share"))
    floors = {r: share * float(p) for r, p in book.get("joint.regime_prob").items()}
    on_floor = [r for r in floors if share and float(posterior[r]) <= floors[r] + GAP_TOL]
    return {"share": share, "floors": floors, "on_floor": on_floor}


def lost_kappa_adds(book: Book, run: Any) -> dict[str, float]:
    """κ-добавка к CoR квартала 1 + L от реальной ставки закрываемого квартала по мирам (ненулевые) — та, которую
    ядро после переноса якоря считает нулём: до сетки реальная ставка у миров общая (М§4.6). Мир-опора — ключ
    книги `credit.kappa_reference_world`: добавка κ × разность реальных ставок мира и мира-опоры любого знака; нет
    ключа — базовый мир и только превышение над ним."""
    kappa, lag = float(book.get("credit.kappa")), int(book.get("credit.real_rate_lag_q"))
    worlds = run.ctx.worlds
    named = book.opt(KAPPA_WORLD)
    ref = BASE_WORLD if named is None else str(named)
    if not kappa or ref not in worlds or 1 + lag > run.ctx.timeline.Q:
        return {}
    level = worlds[ref].real_key[1]
    adds = {w: kappa * ((p.real_key[1] - level) if named is not None else max(0.0, p.real_key[1] - level))
            for w, p in worlds.items()}
    return {w: v for w, v in adds.items() if v}


def lost_kappa(book: Book, run: GridRun) -> str | None:
    """κ-добавка квартала, уходящего в историю: после переноса якоря ядро считает её нулём (М§4.6: до сетки
    реальная ставка у миров общая) — это не переносится, только называется. У книги с миром-опорой добавка
    любого знака и стоит в разложении отдельной строкой (`history_run`)."""
    adds = lost_kappa_adds(book, run)
    if not adds:
        return None
    period = run.ctx.timeline.period(1 + int(book.get("credit.real_rate_lag_q")))
    parts = ", ".join(f"{w}: {v * 100:+.2f} п.п." for w, v in adds.items())
    if book.opt(KAPPA_WORLD) is None:
        return (f"κ-добавка к CoR в {period} от реальной ставки закрытого квартала "
                f"теряется при переносе якоря ({parts}): ядро считает добавку до сетки нулём (М§4.6) — "
                "эффект в строке «механика»")
    return (f"κ-добавка к CoR в {period} от реальной ставки закрытого квартала (к миру-опоре {book.get(KAPPA_WORLD)}; "
            f"{parts}) после переноса якоря равна нулю: до сетки реальная ставка у миров общая (М§4.6). Это свойство "
            "ядра, а не механика переноса: в разложении — отдельная строка «история до сетки», клетка на своём пути "
            "сверяется с прежней книгой без этой добавки, и в допуск механики она не входит")


def history_run(book: Book, run: Any, cell: Sequence[str] | None = None) -> Any:
    """Путь прежней книги, каким его увидит новый якорь: история до сетки у миров общая (М§4.6), и κ-добавка от
    реальной ставки закрываемого квартала у книги с миром-опорой (`credit.kappa_reference_world`) после переноса
    равна нулю. Возвращает прогон без этой добавки — клетки миров, где она была, пересчитаны на контексте, в
    котором реальная ставка закрываемого квартала у них — как у мира-опоры; остальное то же. С ним сверяется
    кандидат: иначе ближняя калибровка ЧПМ подгоняла бы путь кандидата под путь, которого у него быть не может
    (добавка меняет прибыль, капитал и рост следующих кварталов). Нет ключа или добавки — тот же прогон.
    `cell` — нужна одна клетка (перезаякоривание клетки на своём пути)."""
    if book.opt(KAPPA_WORLD) is None:
        return run
    adds = lost_kappa_adds(book, run)
    if not adds:
        return run
    ctx = run.ctx
    level = ctx.worlds[str(book.get(KAPPA_WORLD))].real_key[1]
    worlds = dict(ctx.worlds)
    for w in adds:
        series = list(worlds[w].real_key)
        series[1] = level
        worlds[w] = replace(worlds[w], real_key=tuple(series))
    flat = replace(ctx, worlds=worlds)
    keys = [tuple(cell)] if cell is not None else [c.key for c in run.cells]
    cells = tuple(run_cell(flat, *key) if key[0] in adds else run.cell(*key) for key in keys)
    return CellRun(ctx=flat, cells=cells, layers=getattr(run, "layers", {}))


def stationary_margin(ctx: Any) -> dict[str, Any] | None:
    """Число гейта `nim_stationary` на контексте прогона (М§14.2): стационарная маржа решателя передачи на
    составе баланса якоря в мире ключа книги — в базисе движка и, мостом, в упр. базисе. Нет ключа — None."""
    cfg = ctx.book.opt(NIM_STATIONARY)
    if cfg is None:
        return None
    world = str(cfg["world"])
    engine = float(ctx.transmission.nss[world])
    return {"world": world, "engine": engine, "value": ctx.bridge.to_mgmt_nim(engine),
            "target": float(cfg["target"]), "tolerance": float(cfg["tolerance"])}


def stationary_shift(old_ctx: Any, new_ctx: Any) -> dict[str, Any] | None:
    """Стационарная маржа гейта `nim_stationary` на прежнем якоре и на новом: скаляры пути при переносе
    сохранены, поэтому сдвиг — состав баланса нового якоря (маржа движка) и мост упр. ↔ движок."""
    was, now = stationary_margin(old_ctx), stationary_margin(new_ctx)
    if was is None or now is None:
        return None
    return {**now, "before": was["value"], "d_engine": now["engine"] - was["engine"],
            "d_bridge": (now["value"] - was["value"]) - (now["engine"] - was["engine"]),
            "fired": abs(now["value"] - now["target"]) > now["tolerance"]}


def _pp(x: float, digits: int = 3) -> str:
    return f"{x * 100:+.{digits}f} п.п.".replace(".", ",", 1)


def level_shift(old_ctx: Any, new_ctx: Any, gate: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Ключ уровня маржи у книги с ключом мира уровня (`nii.transmission.level_world`) на прежнем якоре и на
    новом: ключ книги (`key`), стационарная маржа мира уровня по счёту ядра на обоих контекстах (`value` — по
    определению ключа равна ему), её сдвиг — маржа движка (состав баланса при сохранённых скалярах пути) и мост
    упр. ↔ движок, и уровень мира-опоры решателя (`reference`), который ядро находит под ключ. `gate` — цель
    гейта стационарной маржи в том же мире, перенесённая вместе с ключом: (было, стало). Нет ключа — None."""
    world = new_ctx.book.opt(LEVEL_WORLD)
    if world is None:
        return None
    world, was, now = str(world), old_ctx.transmission, new_ctx.transmission
    ref = str(now.reference_world)
    engine = float(was.nss[world]), float(now.nss[world])
    value = old_ctx.bridge.to_mgmt_nim(engine[0]), new_ctx.bridge.to_mgmt_nim(engine[1])
    return {"world": world, "key": (float(old_ctx.book.get(NIM_TARGET)), float(new_ctx.book.get(NIM_TARGET))),
            "value": value, "d_engine": engine[1] - engine[0],
            "d_bridge": (value[1] - value[0]) - (engine[1] - engine[0]), "reference_world": ref,
            "reference": (old_ctx.bridge.to_mgmt_nim(float(was.nss[ref])),
                          new_ctx.bridge.to_mgmt_nim(float(now.nss[ref]))),
            "gate": gate}


def level_note(lv: Mapping[str, Any]) -> str:
    """Слова о ключе уровня маржи после переноса: он переписан на состав баланса нового якоря — это запись
    прежнего суждения, а не пересмотр уровня; пересмотр по новому окну фактов — решение новой версии книги."""
    (k0, k1), (v0, v1), (r0, r1) = lv["key"], lv["value"], lv["reference"]
    text = (f"{NIM_TARGET} — уровень маржи: стационарная маржа мира {lv['world']} на составе баланса якоря, упр. "
            f"(`{LEVEL_WORLD}`). ")
    if k1 == k0:
        text += (f"Ключ оставлен числом прежней книги ({_pct(k0, 3)}): скаляры пути ядро решило под него заново на "
                 "составе баланса нового якоря. ")
    else:
        text += ("Перенос якоря сохранил скаляры пути (спреды книг те же) и переписал ключ на состав баланса нового "
                 f"якоря: {_pct(k0, 3)} → {_pct(k1, 3)}; сдвиг {_pp(v1 - v0)} = маржа движка {_pp(lv['d_engine'])} "
                 f"(состав баланса) и мост упр. ↔ движок {_pp(lv['d_bridge'])}; уровень мира-опоры решателя "
                 f"{lv['reference_world']} — {_pct(r0, 3)} → {_pct(r1, 3)}. Новое число — запись прежнего суждения, а не "
                 "новый уровень: оси по ключу перенесены тем же правилом, оценку оно не сдвигает (строка «механика»). ")
    text += ("Пересмотр уровня по новому окну фактов (закрытый квартал стал его фактом) — решение новой версии книги: "
             "ключ задаётся заново правилом книги, сдвиг точки от него — строка «суждения книги» журнала версии, не "
             "механика")
    if lv.get("gate"):
        text += (f". Гейт `{NIM_STATIONARY}` стоит в том же мире и сверяет то же число: его цель записана вместе с "
                 f"ключом ({_pct(lv['gate'][0], 3)} → {_pct(lv['gate'][1], 3)}) — разницу между целью и ключом перенос "
                 "якоря не меняет, и сам по себе гейт от него не срабатывает")
    if abs(v1 - k1) > LEVEL_TOL:
        text += (f". ВНИМАНИЕ: стационарная маржа мира {lv['world']} на кандидате по счёту ядра — {_pct(v1, 4)}, а "
                 f"ключ — {_pct(k1, 4)}: запись ключа не воспроизводится, кандидата в канон не переносить")
    return text


def stationary_note(st: Mapping[str, Any], level: Mapping[str, Any] | None = None) -> str:
    """Предупреждение и порядок действий по гейту стационарной маржи: цель — суждение книги, ключ цели ЧПМ после
    переноса — запись прежних скаляров пути, а не вывод из цели. `level` — книга несёт ключ мира уровня маржи, а
    гейт стоит в другом мире: его цель — отдельное суждение, из неё ключ не выводится."""
    head = (f"{NIM_STATIONARY}: стационарная маржа мира {st['world']} на составе баланса нового якоря — "
            f"{_pct(st['value'], 3)} упр. при цели {_pct(st['target'], 2)} ± {_pp(st['tolerance'], 2)[1:]} "
            f"(на прежнем якоре {_pct(st['before'], 3)}): сдвиг {_pp(st['value'] - st['before'])} = маржа движка {_pp(st['d_engine'])} "
            f"(состав баланса при сохранённых скалярах пути) и мост упр. ↔ движок {_pp(st['d_bridge'])}"
            + (" — гейт на кандидате срабатывает" if st["fired"] else " — в допуске"))
    if level is not None:
        return (head + f". Цель гейта — отдельное суждение книги о марже мира {st['world']}: инструмент её не трогает. "
                f"Уровень маржи книга задаёт ключом `{NIM_TARGET}` в мире {level['world']}, и он переписан на состав "
                "баланса нового якоря; что делать с целью этого гейта на новом якоре — решение книги, сработавшему "
                "гейту нужно объяснение")
    return (head
            + f". Цель гейта — суждение книги о марже на составе якоря: инструмент её не трогает. Ключ `{NIM_TARGET}` "
            "у кандидата — запись прежних скаляров пути на новой структуре (режим keep), а не новый вывод из цели. "
            "Порядок: (1) цель на составе нового якоря — правилом книги от фактов окна; (2) ключ выводится на ядре "
            "заново листом книги — решением передачи под эту цель, за ним — числа, которые от него зависят, в порядке "
            "листа; (3) сдвиг точки от нового ключа — строка «суждения книги» журнала версии, не механика. Пока шаги "
            "1–2 не сделаны, сработавшему гейту нужно объяснение")


def derived_on_core(template: str) -> list[str]:
    """Ключи книги, выведенные на ядре, — по самой книге: ключи блочных словарей шаблона, в комментарии которых
    (на строке ключа или на строках-продолжениях сразу под ней) стоит пометка `DERIVED_MARKS`. Комментарий с
    первой колонки — легенда или заголовок раздела; комментарий, который начинается не правее имени ключа, —
    заголовок следующего ключа: ни тот, ни другой ключу не принадлежат."""
    lines = template.splitlines()
    keys: list[tuple[int, int, str]] = []        # (строка ключа, колонка конца его имени, путь)

    def walk(node: yaml.Node | None, prefix: str) -> None:
        if not isinstance(node, yaml.MappingNode) or node.flow_style:
            return
        for key, value in node.value:
            path = f"{prefix}.{key.value}" if prefix else str(key.value)
            keys.append((key.start_mark.line, key.end_mark.column, path))
            walk(value, path)

    walk(yaml.compose(template), "")
    keys.sort()
    out: list[str] = []
    for i, line in enumerate(lines):
        head, sep, comment = line.partition("#")
        if not sep or not any(mark in comment for mark in DERIVED_MARKS) or line.startswith("#"):
            continue
        owner = max((key for key in keys if key[0] <= i), default=None)
        if owner is None:
            continue
        at, end, path = owner
        if at != i:                              # строка-продолжение: только комментарии между ней и ключом
            between = lines[at + 1:i + 1]
            if head.strip() or len(head) <= end or not all(x.strip().startswith("#") for x in between):
                continue
        if path not in out:
            out.append(path)
    return out


def _axes_on(X: dict, roots: Sequence[str]) -> list[dict]:
    """Оси книги (полоса, оси вне полосы, обратный расчёт), которые двигают хотя бы один путь под `roots`."""
    return [axis for _, axes, _ in _axis_lists(X) for axis in axes
            if any(_under(str(p), roots) for p in axis.get("paths") or [])]


def derived_note(book: Book, X: dict, marked: Sequence[str] | None, changes: Sequence[tuple]) -> str | None:
    """Ручной шаг о числах книги, выведенных на ядре. Перечень — по книге: ключи шаблона с пометкой (`marked`);
    без шаблона — общими словами. Называет, что из перечня перенос переписал на новый якорь (это запись, не
    вывод), оси по этим ключам и коридор гейта оптового фондирования, если книга его несёт."""
    if not marked and growth_rule(book) is None:
        return None
    tail = ("Правилом книги перенос якоря их не выводит: пересмотр — решение книги, тогда вывод повторяется листом "
            "книги в его порядке (README каталога книги), а сдвиг точки — строка «суждения книги»")
    corridor = (f"; коридор `{WHOLESALE_SHARE}` посчитан на сетке прежней книги" if _get(X, WHOLESALE_SHARE) is not None
                else "")
    if not marked:
        return ("числа книги, выведенные на ядре (ключи шаблона книги с пометкой «" + DERIVED_MARKS[0] + "»; перечень и "
                "порядок вывода — README каталога книги), остаются числами прежней книги или её записью на новом якоре"
                + corridor + ". " + tail)
    moved = sorted({key for key in marked for path, _, _ in changes if _under(dotted(path), (key,))}, key=list(marked).index)
    axes = [f"«{a.get('name')}»" for a in _axes_on(X, marked)]
    return ("числа книги, выведенные на ядре (в шаблоне — пометка «" + DERIVED_MARKS[0] + "»): "
            + ", ".join(f"`{k}`" for k in marked)
            + ("; оси по этим ключам (их концы выведены или заданы вместе с ключом): " + ", ".join(dict.fromkeys(axes))
               if axes else "") + corridor + ". "
            + ("Из них перенос якоря переписал на новый якорь " + ", ".join(f"`{k}`" for k in moved)
               + " (таблица «что сдвинулось»: запись прежнего числа на новом якоре, не новый вывод); остальные — "
               "числа прежней книги. " if moved else "Перенос якоря их не трогает. ") + tail)


def variant_note(X: dict, changes: Sequence[tuple]) -> str | None:
    """Справочные варианты (`valuation.reference_variants`): подмена, которая ложится на ключ, переписанный
    переносом якоря, осталась записью на прежнем якоре — инструмент подмены не трогает, только называет."""
    moved = [dotted(path) for path, _, _ in changes]
    hit = []
    for variant in _get(X, VARIANTS) or []:
        paths = [str(p) for p in (variant.get("overrides") or {})
                 if any(d == str(p) or d.startswith(f"{p}.") or str(p).startswith(d + ".") for d in moved)]
        if paths:
            hit.append(f"«{variant.get('id')}» — " + ", ".join(f"`{p}`" for p in paths))
    if not hit:
        return None
    return (f"справочные варианты (`{VARIANTS}`): подмены ложатся на ключи, которые перенос якоря переписал, — "
            + "; ".join(hit) + ". Значения подмен остались записью на прежнем якоре (на смене года якоря — и на прежних "
            "ключах года шока): инструмент их не трогает; пересчитать на новом якоре (решение книги) — иначе таблица "
            "«Цена правил и развилок» сравнит записи разных якорей")


def premium_note(X: dict, first_old: str, first_new: str) -> str | None:
    """Ключи премии роста к сектору и ось-связка по ним (суждение книги): перенос не трогает ни ключи, ни концы оси —
    называет ключ года, который книга задаёт по фактам закрытых месяцев, год, ставший первым прогнозным, и ключи
    закрытого квартала (книга, которая пишет год якоря кварталами): новая книга их не читает."""
    axes = [a for a in _axes_on(X, PREMIUMS) if a.get("kind") == BUNDLE]
    closed = sorted(f"{root}.{part}.{first_old}" for root in PREMIUMS if isinstance(_get(X, root), Mapping)
                    for part, traj in _get(X, root).items()
                    if isinstance(traj, Mapping) and first_old in map(str, traj))
    if not axes and not closed:
        return None
    year_old, year_new = parse_period(first_old)[0], parse_period(first_new)[0]
    named = {str(p) for p in _get(X, PREMIUM_FACTS) or []}
    quarters = ("" if not closed else
                f". Ключи закрытого квартала ({', '.join(closed)}) новая книга не читает — снять"
                + (f" (вместе с их записями в `{PREMIUM_FACTS}`)" if named & set(closed) else "")
                + "; ключи оставшихся кварталов года — по правилу книги от фактов закрытых месяцев")
    if not axes:
        return "премия роста к сектору — суждение книги: перенос якоря её ключи не трогает" + quarters
    on_axis = sorted({str(p) for a in axes for p in a.get("paths") or [] if str(p).rsplit(".", 1)[-1] == str(year_new)})
    names = ", ".join(f"«{a.get('name')}»" for a in axes)
    text = (f"премия роста к сектору и её ось-связка {names} — суждение книги: перенос якоря не трогает ни ключи премии, "
            "ни концы оси. ")
    if year_new == year_old:
        return text + (f"Ключ {year_new} года после отчёта действует только на оставшиеся кварталы года; если книга "
                       "задаёт его по фактам закрытых месяцев — пересмотреть по её правилу") + quarters
    return text + (f"Первым прогнозным стал {year_new} год"
                   + (f", и его ключи стоят на оси ({', '.join(on_axis)}): оставить ли их на оси и задать ли ключ года по "
                      "фактам закрытых месяцев — решение книги" if on_axis else
                      ": задать ли его ключ по фактам закрытых месяцев — решение книги")) + quarters


def _pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(_num(v) for v in value)


def window_note(X: Mapping, report: Mapping | None = None) -> str | None:
    """Окно фактов книги (`checks.window_backtest`): коридоры гейта и необязательные поля окна (маржа, средние,
    доля кредитов окна) — запись окна прежней книги. Перенос их не трогает: называет поля и ставит рядом с краями
    окна упр. числа квартала отчёта (`report`) — продлить ли окно и пересмотреть ли по нему уровни, решает новая
    версия книги. Долю кредитов якоря ядро считает само — в узле уровней кандидата она уже нового якоря."""
    cfg = _get(X, WINDOW_BACKTEST)
    if not isinstance(cfg, Mapping):
        return None
    fields = [name for name in tuple(key for key, _ in WINDOW_CORRIDORS) + WINDOW_FIELDS if name in cfg]
    text = (f"окно фактов (`{WINDOW_BACKTEST}`: {', '.join(fields)}) — запись окна прежней книги: перенос якоря её не "
            "трогает. ")
    mgmt = (report or {}).get("mgmt") or {}
    seen = []
    for key, title in (("nim", "ЧПМ"),) + WINDOW_CORRIDORS:
        pair, fact = cfg.get(key), mgmt.get(key)
        if not _pair(pair) or not _num(fact):
            continue
        low, high = sorted(map(float, pair))
        where = ("ниже наименьшего квартала окна" if fact < low else
                 "выше наибольшего квартала окна" if fact > high else "внутри окна")
        seen.append(f"{title} {_pct(float(fact))} — {where} ({_pct(low)}…{_pct(high)})")
    if seen:
        text += f"Квартал отчёта {report.get('period')}, упр.: " + "; ".join(seen) + ". "
    return text + ("Продлить ли окно на закрытый квартал — и тогда пересчитать его коридоры и поля, а по новому окну "
                   "пересмотреть уровни книги — решение новой версии книги, не перенос")


CARRIED_FILES = ("anchor", "balance", "nii_books", "pnl_quarterly", "capital", "shares", "dividends",
                 "bridge_mgmt_ifrs", "mgmt_quarterly")      # файлы фактов, узлы якоря которых пишет `facts_after`
# Файлы фактов окна, которые ядро не читает, а читают лист вывода книги и правила класса 6: перенос их не продлевает.
WINDOW_FILES = {
    "perimeter": "ряд периметра окна R (Р4-3, Р5-3): поправки периметра к периметру якоря — продлить кварталом отчёта "
                 "и сделками квартала листом stage1/round5/perimeter_series.py; ступени периметра в корнях строк "
                 "(даты контроля) и концы осей периметра перенос не двигает, их перевывод — шаг ends_perimeter",
    "misc_window": "ряд «прочего» (Р7-1): строка «бумаги и валюта» без переоценки ССПУ и разовых в ценах якоря — продлить "
                   "кварталом отчёта и перевести в цены нового якоря листом stage1/round7/r7_1_misc_slope.py",
    "credit_products": "окна CoR по продуктам (Р3): интенсивности состава окон — продлить кварталом отчёта",
}


def stale_facts_notes(facts: Facts | None) -> list[str]:
    """Ручной шаг: файлы фактов окна, которые остались на прежнем якоре (`WINDOW_FILES`, прочие файлы с датой прежнего
    якоря, кроме переносимых `CARRIED_FILES`) — их ядро не читает, а правила класса 6 и лист вывода — читают."""
    if facts is None:
        return []
    old = str(_get(facts.files.get("anchor", {}), "as_of", ""))
    stale = [name for name, body in facts.files.items()
             if name not in CARRIED_FILES and isinstance(body, Mapping) and str(body.get("as_of", "")) == old]
    if not stale:
        return []
    known = [f"`{name}.json` — {WINDOW_FILES[name]}" for name in stale if name in WINDOW_FILES]
    rest = [f"`{name}.json`" for name in stale if name not in WINDOW_FILES]
    return [f"факты на прежнем якоре ({old}), перенос их не трогает (ядро не читает или читает как есть): "
            + "; ".join(known + ([", ".join(rest) + " — проверить вручную"] if rest else []))
            + " (решение книги; правила класса 6 сверяют центры с этими рядами)"]


def manual_steps(book: Book, X: dict, *, marked: Sequence[str] | None = None, changes: Sequence[tuple] = (),
                 first_new: str | None = None, report: Mapping | None = None, facts: Facts | None = None) -> list[str]:
    """Что инструмент сознательно НЕ делает — суждения книги и работа других инструментов. `marked` — ключи книги,
    выведенные на ядре (по шаблону книги), `changes` — что перенос изменил, `first_new` — новый первый
    прогнозный квартал, `report` — отчёт квартала (его упр. числа ставятся рядом с окном фактов книги)."""
    out = []
    for path, _ in GAPS:
        old, new = float(book.get(path)), float(_get(X, path))
        if abs(new - old) > 0.0005:
            out.append(f"{path}: {old:+.4f} → {new:+.4f} — якорь воспроизводит норматив отчёта; ось "
                       "сдвинута вместе с центром, ширину пересмотреть (решение книги)")
    out.append(f"{SPLIT}, {PHI_SPLIT}: центры и оси — правило листов книги на структуре якоря (evidence/nii): "
               "пересчитать на новом якоре; дисконт за управление — неподвижная точка на новой медиане (решения "
               "книги, в разложении выпусков — строка «суждения книги»)")
    note = derived_note(book, X, marked, changes)
    if note:
        out.append(note)
    if _get(X, f"{CIR_LT}.scope") == MARKET_LAYER:
        out.append(f"{CIR_LT}: цель C/I сверяется по слою «рыночные ставки как есть» (`scope: {MARKET_LAYER}`), и корни "
                   "`opex.real_growth` выведены под неё по всей сетке; перенос якоря корни не трогает — число гейта на "
                   "кандидате стоит в таблице целей, вывод корней заново — лист книги (решение книги)")
    for note in (window_note(X, report), variant_note(X, changes),
                 premium_note(X, str(book.get("meta.first_period")), first_new or str(_get(X, "meta.first_period")))):
        if note:
            out.append(note)
    out += stale_facts_notes(facts)
    if is_quarterly(book):
        out.append("дивиденды: отчётную прибыль акционеров по годам для теста потолка политики (dividends.years) и "
                   "слова решений строк истории инструмент не двигает — их несёт канон фактов; события календаря "
                   "фактов следующего квартала (отчёт, решение о дивиденде, выход формы) — руками")
    out.append("миры и кривые — на прежней дате (meta.curve_as_of): пересборка миров — отдельной версией "
               "книги вместе с семейством")
    out.append("meta.market_price и meta.date — прежней книги: обновить вместе с датой оценки")
    out.append("valuation.next_report.cor_values, nim_values — сетки «что даст отчёт» вокруг ожидания "
               "нового открытого квартала: пересмотреть")
    out.append("факты: канон пересобирает `ops/tools/build_facts.py` (`--anchor` из листов квартала, "
               "`--expected` из ожидаемого отчёта) с источниками и сверками; сверка с фактами кандидата — "
               "`--compare-facts`")
    out.append("объяснения гейтов (gate_explanations.yaml), results.json и run_output.txt, закреплённые "
               "числа тестов книги и документов — на новой книге (MANUAL §10.4)")
    return out


# ------------------------------------------------------------------ дифф


def diff(a: Any, b: Any, prefix: Path_ = ()) -> list[tuple[Path_, Any, Any]]:
    """Все листья, которые изменились: (путь звеньями, было, стало)."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        out = []
        for key in list(a) + [k for k in b if k not in a]:
            path = prefix + (str(key),)
            if key not in b:
                out.append((path, a[key], None))
            elif key not in a:
                out.append((path, None, b[key]))
            else:
                out += diff(a[key], b[key], path)
        return out
    if isinstance(a, list) and isinstance(b, list) and a \
            and all(isinstance(x, Mapping) and "name" in x for x in a) \
            and [x["name"] for x in a] == [y.get("name") if isinstance(y, Mapping) else None for y in b]:
        out = []
        for x, y in zip(a, b):
            out += diff(x, y, prefix + (("name", x["name"]),))
        return out
    return [] if a == b else [(prefix, a, b)]


def dotted(path: Path_) -> str:
    out = ""
    for part in path:
        out += f"[{part[1]}]" if isinstance(part, tuple) else (f".{part}" if out else part)
    return out


PASS_REASONS = (
    (f"{BUYBACK}.", "выкуп закрытого квартала — история: капитал и акции в обращении — в фактах нового якоря (М3)"),
    (f"{CASH}.share_from", f"Р7-6: квартал доли денег книги — квартал якоря + {CASH_LEAD} (К8)"),
    (LINE_SHARES, "доли базы расходов на базах строк — на составе нового якоря (К2)"),
    (KAPPA, "состав кредитов нового якоря (М7): κ × f"),
    (GUAR_WEIGHT, "вес RWA гарантий — масштаб плотностей: тем же множителем (К5)"),
    ("volumes.other_assets_to_loans", "К8: ρ на структуре нового якоря — ρ_1 + (c* − c_1)(a_1 − a_0), путь прочих активов прежний"),
) + tuple((f"{key}.mix", "доли смеси базы строки — на составе нового якоря (К2б)") for key in LINE_MIX)


def reason(path: str) -> str:
    """Почему ключ сдвинулся — для таблицы «что сдвинулось»."""
    parts = path.split(".")
    if len(parts) >= 3 and parts[0] == "regimes" and parts[2] == "cor":
        return "состав кредитов нового якоря (М7): CoR режима — запись прежнего суждения на новом составе, × f"
    if path.startswith("valuation.") and ".cor." in path and "regimes." in path:
        return "ось по CoR режимов — тем же правилом состава кредитов (М7)"
    return next((text for prefix, text in PASS_REASONS + REASONS if path.startswith(prefix)), "")


# ------------------------------------------------------------------ ожидаемый отчёт


def _cell_report(run: GridRun, weights: Mapping[tuple, float]) -> dict:
    """Отчёт за первый прогнозный квартал прежней книги: состояние клеток `weights` на конец
    квартала (одна клетка — её путь; слой — ожидание, отношения — отношением ожиданий).

    Ближний сдвиг ЧПМ (слагаемое Ov, М§4.4) разнесён по книгам активов пропорционально их
    процентному доходу — как в настоящей отчётности, где процентный доход разложен без остатка."""
    ctx = run.ctx
    book, tl, prep = ctx.book, ctx.timeline, ctx.prep
    af, roles = prep.af, prep.roles
    total = sum(weights.values())
    w = {tuple(k): v / total for k, v in weights.items() if v}
    cells = {k: run.cell(*k) for k in w}
    year_days = tl.d(1) / 365

    def avg(name: str) -> float:
        return sum(p * float(cells[k].quarters[name][1]) for k, p in w.items())

    balances = {b: sum(p * float(cells[k].books[b]["balance"][1]) for k, p in w.items()) for b in roles.names}
    interest = {b: sum(p * float(cells[k].books[b]["rate"][1]) * float(cells[k].books[b]["avg"][1]) * year_days
                       for k, p in w.items()) for b in roles.names}
    carried = 1.0 + avg("overlay") / sum(interest[b] for b in roles.assets)
    for b in roles.assets:
        interest[b] *= carried
    pbt = avg("pbt")
    lines = {"nii": avg("nii"), "fees_net": avg("fees"), "llp_debt_fa": -avg("llp"),
             "insurance_net": avg("ins"), "noncore_net": avg("noncore"), "opex": -avg("opex")}
    misc = pbt - sum(lines.values())
    dp, dpreg = avg("dp"), avg("dpreg")
    quarterly = prep.calendar is not None
    year, by_period = None, None
    if quarterly:                            # решения и суммы к выплате — по кварталам прибыли (М§15.2 п. 9)
        by_period = _dividends_by_period(run, w, dp, dpreg)
    else:
        if dpreg and abs(dpreg - dp) > 1e-6 * max(1.0, dp):
            raise ReportError("ожидаемый отчёт: дивиденд, не вычтенный из регуляторного капитала, не равен "
                              "дивидендам к выплате на конец квартала — календарь книги не представим фактами якоря")
        declared = [dec.year for k in w for dec in cells[k].decisions
                    if tl.index(period_str(dec.year + 1, prep.policy.agm_quarter)) == 1]
        year = declared[0] if declared else af.dividends_payable_year
    by_world: dict[str, float] = {}
    for (world, _, _), p in w.items():
        by_world[world] = by_world.get(world, 0.0) + p

    def world_avg(series) -> float:
        return sum(p * series(ctx.worlds[x]) for x, p in by_world.items())

    def over_ratio(name: str, capital: str) -> float:    # норматив − капитал / RWA: поправка и вычеты сценария
        return sum(p * (float(cells[k].quarters[name][1])
                        - float(cells[k].quarters[capital][1]) / float(cells[k].quarters["rwa"][1]))
                   for k, p in w.items())

    rwa, k11 = avg("rwa"), avg("k11")
    br = ctx.bridge
    who = f"клетка {'/'.join(next(iter(w)))}" if len(w) == 1 else "слой «свой взгляд»"
    balance = {
        "books": balances, "loans_fvtpl": avg("loans_fv"),
        "fvoci": float(book.get("oci.fvoci_share")) * balances[SECURITIES],
        "fvtpl_bonds": float(book.get("oci.fvtpl_bond_share")) * balances[SECURITIES],
        "allowance": avg("allowance"), "other_assets": avg("other_assets"),
        "other_liabilities": avg("other_liabilities"), "dividends_payable": dp,
        "bv_common": avg("bv"), "fvoci_reserve": avg("reserve"), "at1": af.at1, "nci": af.nci,
    }
    if year is not None:
        balance["dividends_payable_year"] = int(year)
    capital = {"n20_0": avg("k20") / rwa + over_ratio("n20", "k20"), "n20_pre_dividend": dpreg > DIV_TOL,
               "n1_1_bank": k11 / rwa + over_ratio("n11", "k11"),
               "basel_cet1": avg("bv") - avg("ded20"), "basel_rwa": rwa, "bank_base_capital": k11}
    extra: dict[str, Any] = {}
    if by_period is not None:
        balance["dividends_payable_declared"] = by_period["declared"]
        extra["dividend_decisions"] = by_period["decisions"]
    if prep.oa_fixed:                        # постоянная в рублях часть прочих активов клетка несёт числом (М§4.3)
        balance["other_assets_fixed"] = prep.oa_fixed
    if _anchor_key(book.source or book.data, T2, tl.anchor):
        capital["t2"] = prep.t2[1]           # инструменты капитала конца квартала — значение траектории книги
    panel = _panel_report(run, w)            # поля ключей проходов ядра: узлы фактов, которые ядро читает словом anchor
    balance.update(panel["balance"])
    capital.update(panel["capital"])
    if panel["shares"]:
        extra["shares"] = panel["shares"]
    return _rounded({
        "schema": SCHEMA, "period": tl.period(1), "as_of": tl.end(1).isoformat(),
        "note": (f"синтетический отчёт: ожидание модели книги {book.get('meta.version')} ({who}) — "
                 "сухой прогон, не факты"),
        "balance": balance, "interest": interest, "dia": avg("dia"),
        "pnl": {**lines, "misc_net": misc, "pbt": pbt, "tax": -(avg("tax") + avg("ot")), "ni": avg("ni"),
                "ni_shareholders": avg("ni_sh"), "oci_fvoci": avg("oci"), "other_equity_movements": avg("om")},
        "capital": capital,
        "market": {"ofz_curve": {n: world_avg(lambda x, n=n: x.ofz[f"ofz_{n}y"][1]) for n in CURVE_NODES},
                   "key_avg": avg("key"), "price_index": world_avg(lambda x: x.price_index[1])},
        "mgmt": {"nim": br.to_mgmt_nim(avg("nim")), "cor": br.to_mgmt_cor(avg("cor")),
                 "cir": br.to_mgmt_cir(avg("opex") / (avg("nii") + avg("fees") + avg("ins") + misc))},
        **extra,
    }, 9)


def _base_level(base: Any, balances: Mapping[str, float], roles: Any) -> float:
    """Уровень базы строки или драйвера на конец квартала по остаткам книг (М§4.7: слово loans | funds | iea или веса
    книг; у номинала уровня нет — отказ)."""
    if base.kind == "books":
        return sum(float(w) * balances[b] for b, w in base.weights.items())
    books = {"loans": roles.loans, "funds": roles.funds, "iea": roles.assets}.get(base.kind)
    if books is None:
        raise ReportError(f"ожидаемый отчёт: база вида {base.kind} не имеет уровня по остаткам книг")
    return sum(balances[b] for b in books)


def _panel_report(run: GridRun, w: Mapping[tuple, float]) -> dict[str, dict]:
    """Поля ключей проходов ядра в ожидаемом отчёте (docs/REANCHOR.md §2, §3.16) — состояние клеток `w` на конец
    первого прогнозного квартала, теми же правилами, что их ведёт ядро:

    * неработающие деньги C_1 (ряд `cash`) и ФОР — доля якоря r = R_0 / D_0 к уровню драйвера D_1 (К8, Р6-1);
    * резерв по кредитным книгам — покрытие книги якоря × остаток книги по АС (К7);
    * номиналы гарантий — номинал якоря × D^G_1 / D^G_0, уровень драйвера RWA гарантий (К5);
    * капитал нормативов банка — K20 и K11 клетки (форма 0409123: собственные средства и основной капитал);
    * акции в обращении после выкупа квартала — N_c,1 (М3, М§5.6).

    Поле пишется, только когда его читает книга (`panel_needs`) — у книги без ключей отчёт прежней формы."""
    ctx = run.ctx
    book, facts, prep, tl = ctx.book, ctx.facts, ctx.prep, ctx.timeline
    roles, af = prep.roles, prep.af
    need = panel_needs(book, facts)
    cells = {k: run.cell(*k) for k in w}

    def avg(fn) -> float:
        return sum(p * float(fn(cells[k])) for k, p in w.items())

    def bal(c: Any) -> dict[str, float]:
        return {b: float(c.books[b]["balance"][1]) for b in roles.names}

    out: dict[str, dict] = {"balance": {}, "capital": {}, "shares": {}}
    cash_need = need.get("balance.nonworking_money", ())
    if cash_need:
        block = {}
        if "total" in cash_need:
            block["total"] = avg(lambda c: c.quarters["cash"][1])
        if "mandatory_reserves" in cash_need:
            r0, d0 = facts.need("balance", "nonworking_money.mandatory_reserves"), prep.cash.base.end0
            block["mandatory_reserves"] = avg(lambda c: r0 * _base_level(prep.cash.base, bal(c), roles) / d0)
        out["balance"]["nonworking_money"] = block
    if "balance.allowance_books" in need:
        from model.book import allowance_books
        a0 = allowance_books(facts, roles.loans)

        def ac(balances: Mapping[str, float], b: str, fv: float) -> float:
            return balances[b] - (fv if b == af.fv_book else 0.0)

        out["balance"]["allowance_books"] = {
            b: avg(lambda c, b=b: a0[b] / ac(af.balances, b, af.fv_loans) * ac(bal(c), b, c.quarters["loans_fv"][1]))
            for b in roles.loans}
    kinds = need.get("capital.guarantees", ())
    if kinds:
        g = prep.guar
        if g.base is not None:
            ratio = avg(lambda c: _base_level(g.base, bal(c), roles) / g.d0)
        else:                                # драйвер «строка комиссий за четыре квартала»: три квартала фактов + клетка
            hist = sum(float(af.pnl[tl.period(x)]["fees_net"]) for x in range(-2, 1))
            ratio = avg(lambda c: (hist + c.quarters["fees"][1]) / g.d0)
        out["capital"]["guarantees"] = {k: facts.need("capital", f"guarantees.{k}") * ratio for k in kinds}
    if "capital.bank_own_funds" in need:     # капитал нормативов банка: K20 и K11 клетки (без поправок «норматив − расчёт»)
        out["capital"]["bank_own_funds"] = avg(lambda c: c.quarters["k20"][1])
        out["capital"]["bank_main_capital"] = avg(lambda c: c.quarters["k11"][1])
    if prep.bb is not None:                  # выкуп квартала уменьшил акции в обращении (М§5.6)
        n1 = avg(lambda c: c.quarters["n_out"][1])
        out["shares"]["outstanding_total"] = n1
        if facts.has("shares", "outstanding_ordinary"):
            out["shares"]["outstanding_ordinary"] = n1
    return out


def _anchor_key(data: Mapping, path: str, period: str) -> bool:
    """Траектория книги пишет ключ квартала `period` явно (правило «ключ квартала якоря — факт», М§4.11)."""
    traj = _get(data, path)
    return isinstance(traj, Mapping) and period in {str(k) for k in traj}


def _dividends_by_period(run: GridRun, w: Mapping[tuple, float], dp: float, dpreg: float) -> dict[str, list]:
    """Квартальный календарь: решения клеток `w` в закрываемом квартале и объявленное, но не выплаченное на его
    конец — так, как их несёт файл отчёта (М§15.2 п. 9). Запись реестра даёт решению свой день, даты реестра и
    выплаты; решение модели датируется концом квартала. Состояние, которого факты якоря не выражают, — отказ:
    вычет из регуляторного капитала после выплаты; решение за квартал прибыли, оставившее открытым более ранний."""
    ctx = run.ctx
    prep, tl = ctx.prep, ctx.timeline
    cal, n_out = prep.calendar, prep.policy.n_out
    end = tl.end(1)
    facts_date = to_date(ctx.book.get("meta.facts_date"))
    records = {str(r.period): r for r in ctx.live.register if r.status in DECLARED and r.period}
    unpaid: dict[str, float] = {}
    pending, problems = 0.0, []
    items = ctx.facts.file("balance").get("dividends_payable_declared") or []
    for item, (pay_q, reg_q, amount) in zip(items, cal.payable):   # объявлено до прежнего якоря (тот же порядок)
        p = str(_fact(item.get("period")))
        if pay_q > 1:
            unpaid[p] = unpaid.get(p, 0.0) + amount
        if reg_q > 1:
            pending += amount
            if pay_q <= 1:
                problems.append(f"{p}: выплата в закрываемом квартале, вычет из регуляторного капитала — позже")
    decisions = []
    due = cal.by_q.get(1, ())
    for o in due:
        got = [(p, next(d for d in run.cell(*k).decisions if d.q == 1 and d.period == o.period)) for k, p in w.items()]
        div, dps = sum(p * d.div for p, d in got), sum(p * d.dps for p, d in got)
        rec = records.get(o.period)
        day = rec.decided_date if rec is not None and rec.decided_date is not None else None
        row = {"period": o.period, "dps": dps,
               "decided_date": (day if day is not None and facts_date < day <= end else end).isoformat()}
        if rec is not None:
            for key, value in (("record_date", rec.record_date), ("pay_date", rec.pay_date)):
                if value is not None:
                    row[key] = value.isoformat()
        decisions.append(row)
        if o.q_pay > 1 and div > DIV_TOL:
            unpaid[o.period] = unpaid.get(o.period, 0.0) + div
        if o.q_reg > 1 and div > DIV_TOL:
            pending += div
            if o.q_pay <= 1:
                problems.append(f"{o.period}: выплата в квартале решения, вычет из регуляторного капитала — позже")
    if due:
        last = max(o.idx for o in due)
        late = [o.period for o in cal.open if o.idx < last and o.q > 1]
        if late:
            problems.append(f"решение за {tl.period(last)} принято раньше решения за {', '.join(late)}: строка "
                            "истории закрыла бы и более ранний квартал прибыли")
    if abs(pending - dpreg) > DIV_TOL * max(1.0, abs(dpreg)):
        problems.append(f"дивиденды в регуляторном капитале {dpreg:g} не равны объявленным с вычетом впереди {pending:g}")
    if sum(unpaid.values()) > dp + DIV_TOL:
        problems.append(f"объявлено и не выплачено {sum(unpaid.values()):g} — больше дивидендов к выплате {dp:g}")
    if problems:
        raise ReportError("ожидаемый отчёт: календарь дивидендов книги не представим фактами якоря — "
                          + "; ".join(problems) + " (решение книги: payment_lag_quarters не меньше "
                          "reg_deduction_lag_quarters; даты записи реестра)")
    order = sorted(unpaid, key=pindex)
    return {"decisions": decisions, "declared": [{"period": p, "amount": unpaid[p]} for p in order]}


def expected_run(book: Book, facts: Facts, live: LiveInputs | None = None, *,
                 observe: bool = True) -> tuple[Book, GridRun, dict | None]:
    """Прежняя книга с наблюдением, равным ожиданию модели (A⁺), её прогон и само наблюдение."""
    if not observe:
        return book, run_grid(book, facts, live), None
    obs = expected_observation(book, facts, live)
    plus = with_observation(book, obs)
    return plus, run_grid(plus, facts, live), obs


def expected_report(book: Book, facts: Facts, *, cell: Sequence[str] | None = None,
                    run: GridRun | None = None, observe: bool = True) -> dict:
    """Синтетический отчёт за первый прогнозный квартал = ожидание модели (М§15.2).

    `cell` — путь одной клетки (точная проверка механики, без неравенства Йенсена); иначе —
    ожидание слоя «свой взгляд». `run` — готовый прогон прежней книги с ожидаемым наблюдением."""
    if run is None:
        _, run, _ = expected_run(book, facts, observe=observe)
    return _cell_report(run, _weights(run, cell))


# ------------------------------------------------------------------ разложение скачка


def live_at(book: Book, facts: Facts, valuation_date: dt.date) -> LiveInputs:
    """Живые входы книги на дате оценки `valuation_date`: цены и реестр — книжные."""
    live = live_from_book(book, facts)
    return LiveInputs(valuation_date=valuation_date, prices=live.prices,
                      price_dates={t: valuation_date for t in live.prices}, register=live.register)


def headline(run: GridRun) -> dict:
    """Низ, точка при λ и верх (₽) и V0 слоёв (млрд ₽) при значениях книги."""
    return {"low": run.low, "point": run.point, "high": run.high,
            "v0": {name: layer.v0 for name, layer in run.layers.items()}}


def _priced(run_plus: GridRun, values: Mapping[tuple, float]) -> dict:
    """Низ, точка и верх (₽) и V0 слоёв (млрд ₽) при стоимостях клеток `values` и вероятностях прогона `run_plus`:
    цена линейна по V0 (М§8.2), делитель «на акцию» — книги (М§8.4)."""
    n_div = (getattr(run_plus, "divisor", 0.0) or getattr(run_plus, "shares_out", 0.0)
             or run_plus.ctx.prep.af.n_out)
    per_v0 = (1.0 - run_plus.governance) * 1000.0 / n_div
    price, v0 = {}, {}
    for name, layer in run_plus.layers.items():
        v0[name] = sum(p * values[k] for k, p in layer.prob.items())
        price[name] = layer.price + (v0[name] - layer.v0) * per_v0
    low, high = price[NEUTRAL], price[ANALYTICAL]
    return {"low": low, "high": high, "point": low + run_plus.lam * (high - low), "v0": v0}


def cell_mechanics(book: Book, facts: Facts, run_plus: GridRun, obs: Mapping | None,
                   valuation_date: dt.date, *, cells: Sequence[Sequence[str]] | None = None,
                   transmission: str = KEEP, history: Any = None) -> dict:
    """Строка «механика» (М§15.2): каждая клетка перезаякорена на своём пути.

    Отчёт клетки — её состояние на конец закрытого квартала; наблюдение и вероятности — как у
    прежней книги с ожидаемым наблюдением. Возвращает строки по клеткам и точку слоёв. При
    смене года якоря клетки режима с годом шока «перезаряжены» (М§3.2) — их путь другой по
    определению, и в допуск они не входят. База сравнения клетки — путь прежней книги, каким его увидит новый
    якорь (`history_run`; `history` — готовый): у книги с миром-опорой κ он не несёт добавку от реальной ставки
    закрываемого квартала. Строка клетки несёт обе величины — `history` (прежняя книга без этой добавки к прежней
    книге) и `rel` (клетка на своём пути к базе); допуск — по `rel`. Без мира-опоры база — сама прежняя книга.
    Мера — оценка клетки в цене V̂ на делителе прежней книги (стоимость на акцию, М§8.4; у книги без выкупа — V_RI);
    клетка перезаякоривается без правил книги, которые двигают путь намеренно (`book_rules=False`, Р7-6)."""
    keys = [tuple(k) for k in cells] if cells is not None else [c.key for c in run_plus.cells]
    hist = history if history is not None else history_run(book, run_plus)
    tl = run_plus.ctx.timeline
    rearmed = {r for r in book.get("regimes.ids")
               if tl.year(1) != tl.anchor_year and "shock_year_offset" in book.source["regimes"][r]}
    rows = []
    n_base = _divisor(hist)
    for key in keys:
        old, base = run_plus.cell(*key), hist.cell(*key)
        cand = reanchor(book, facts, _cell_report(run_plus, {key: 1.0}), valuation_date=valuation_date,
                        cell=key, base_run=hist, observation=obs, observe=obs is not None,
                        transmission=transmission, book_rules=False)
        run_new = run_grid(cand.book, cand.facts, live_at(cand.book, cand.facts, valuation_date))
        new = run_new.cell(*key)
        # мера — стоимость на акцию делителя своего прогона (М§8.4): выкуп закрытого квартала (М3) уже в акциях нового
        # якоря, и оценка клетки в цене V̂ = S N_out / 1000 меняется вместе с делителем, а S — нет
        n_new = _divisor(run_new)
        priced = new.v_price * n_base / n_new          # V̂ клетки на делителе прежней книги: та же стоимость на акцию
        rows.append({"cell": old.label, "key": key, "old": old.v_price, "base": base.v_price, "new": priced,
                     "rel": priced / base.v_price - 1, "history": base.v_price / old.v_price - 1,
                     "v_ri": (old.v_ri, base.v_ri, new.v_ri), "rearmed": key[1] in rearmed})
    kept = [r for r in rows if not r["rearmed"]] or rows
    worst = max(kept, key=lambda r: abs(r["rel"]))
    out = {"rows": rows, "worst": worst, "tolerance": MECHANICS_TOL, "ok": abs(worst["rel"]) <= MECHANICS_TOL,
           "rearmed": sorted(rearmed), "history": hist is not run_plus}
    if cells is None:                        # точка: те же вероятности, цена линейна по V0 (М§8.2)
        out["headline"] = _priced(run_plus, {r["key"]: r["new"] for r in rows})
    return out


def _divisor(run: Any) -> float:
    """Делитель «на акцию» прогона (М§8.4): N_div прогона сетки; у прогона клеток — та же функция ядра на его книге."""
    from model.grid import divisor
    got = float(getattr(run, "divisor", 0.0) or 0.0)
    return got or divisor(run.ctx.book, run.ctx.facts, run.ctx.prep.af)


def band_stats(book: Book, facts: Facts, live: LiveInputs, draws: int) -> dict:
    """Медиана и полоса 80 % печатаемого заголовка на `draws` прогонах (те же точки гиперкуба
    у каждой книги — сравнение парное)."""
    from model.uncertainty import band
    b = band(book, facts, live, draws=draws)
    st = b.stats(b.lam)
    main = str(book.get("meta.company.main_ticker"))
    return {"p10": st["p10"], "median": st["median"], "p90": st["p90"],
            "p_below": b.p_below(b.lam, float(live.prices[main]))}


MARGIN_TARGETS = ("nim_stationary", "nim_lt")  # гейты целей маржи: упр. число = маржа движка через мост


def target_levels(run: GridRun, findings: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Числа гейтов-целей книги на прогоне (М§14.2): гейт, который сверяет своё число с целью-суждением, несёт
    число, цель и допуск (`nim_stationary`, `cir_lt`, `nim_lt` — какие есть у книги). У целей маржи рядом —
    маржа движка: по ней сдвиг упр. числа раскладывается на путь и мост упр. ↔ движок."""
    out: dict[str, dict[str, Any]] = {}
    bridge = run.ctx.bridge
    for f in findings:
        d = f.detail or {}
        value = d.get("value", d.get("mean"))
        if f.kind != "gate" or not (_num(value) and _num(d.get("target")) and _num(d.get("tolerance"))):
            continue
        row = {"value": float(value), "target": float(d["target"]), "tolerance": float(d["tolerance"]),
               "fired": bool(f.fired), "message": f.message}
        if f.name in MARGIN_TARGETS:
            row["engine"] = bridge.to_engine_nim(float(value))
        out[f.name] = row
    return out


def level_node(run: GridRun) -> dict[str, Any] | None:
    """Узел уровней после фазы роста (ключ книги `checks.window_backtest`, М§14.5): ЧПМ, CoR, C/I в упр. базисе
    и доля кредитов в процентных активах — модальной клетки, слоёв и смеси заголовка. Нет ключа — None."""
    if run.ctx.book.opt(WINDOW_BACKTEST) is None:
        return None
    from model.levels import levels
    return levels(run)


def core_checks(run: GridRun, today: dt.date) -> dict[str, Any]:
    """Инварианты и гейты ядра на прогоне (М§14.1–§14.2): нарушенные инварианты и сработавшие гейты
    с массой; числа гейтов-целей книги (`targets`) и узел уровней после фазы роста (`levels`) — сработал гейт
    или нет. Отказ ядра (нет факта, без которого проверка не считается) — причиной в `error`."""
    try:
        broken = [(f.name, f.message) for f in check_invariants(run) if f.fired]
        every = check_gates(run, today=today)
        found = [f for f in every if f.fired]
        gates = {f.name: (f.mass, f.message) for f in found if f.kind == "gate"}
        flags = {f.name: f.message for f in found if f.kind == "flag"}
        targets, levels = target_levels(run, every), level_node(run)
    except (BookError, FactsError) as exc:
        return {"error": str(exc), "invariants": [], "gates": {}, "flags": {}, "targets": {}, "levels": None}
    return {"error": None, "invariants": broken, "gates": gates, "flags": flags, "targets": targets, "levels": levels}


LEVEL_COLUMNS = (("nim", "ЧПМ", 2), ("cor", "CoR", 2), ("cir", "C/I", 1),
                 ("loans_share", "доля кредитов в проц. активах", 1))       # (ключ узла уровней, графа, знаков)


WINDOW_WORDS = {"min": "наименьший", "max": "наибольший", "mean": "среднее", "window": "окно", "anchor": "якорь"}


def _window_cell(value: Any, digits: int, was: Any = None) -> str:
    """Ячейка строки окна фактов узла уровней (подузел `window`, М§14.6): {min, max, mean} — наименьший…наибольший
    квартал окна и среднее окна; доля кредитов — окна (поле книги) и якоря (состояние якоря прогона: у кандидата
    она новая — `was` несёт прежнюю); нет величины — «—»."""
    if not isinstance(value, Mapping):
        return "—"
    if _num(value.get("min")) and _num(value.get("max")):
        text = f"{_pct(float(value['min']), digits)}…{_pct(float(value['max']), digits)}"
        return text + (f", среднее {_pct(float(value['mean']), digits)}" if _num(value.get("mean")) else "")
    before = was if isinstance(was, Mapping) else {}
    return ", ".join(
        f"{WINDOW_WORDS.get(str(k), k)} "
        + (f"{_pct(float(before[k]), digits)} → " if _num(before.get(k)) and float(before[k]) != float(v) else "")
        + _pct(float(v), digits) for k, v in value.items() if _num(v)) or "—"


def target_lines(was: Mapping[str, Any], now: Mapping[str, Any], before: str = "прежняя книга") -> list[str]:
    """Раздел «Цели книги и уровни после фазы роста» отчёта кандидата: число каждого гейта-цели до и после
    рядом с целью и допуском (сработал гейт или нет), разложение сдвига маржи на путь и мост, узел уровней."""
    lines: list[str] = []
    rows = now.get("targets") or {}
    if rows:
        lines += ["", "Цели книги, которые сверяют её гейты (цель и допуск — суждение книги: инструмент их не трогает; "
                  "число печатается, сработал гейт или нет; цель гейта стационарной маржи в мире ключа уровня маржи — "
                  "то же суждение, что ключ, и идёт за ним: «было → стало»):", "",
                  f"| гейт | {before} | кандидат | цель ± допуск | до границы допуска |", "|---|---|---|---|---|"]
        for name, a in rows.items():
            b = (was.get("targets") or {}).get(name)
            room = a["tolerance"] - abs(a["value"] - a["target"])
            moved = b is not None and abs(b["target"] - a["target"]) > LEVEL_TOL / 2
            lines.append(f"| `{name}` | {_pct(b['value'], 3) if b else '—'} | {_pct(a['value'], 3)} | "
                         + (f"{_pct(b['target'], 3)} → {_pct(a['target'], 3)}" if moved else _pct(a["target"], 2))
                         + f" ± {_pp(a['tolerance'], 2)[1:]} | "
                         + (f"{_pp(room)[1:]}" if room >= 0 else f"вне допуска на {_pp(-room)[1:]}") + " |")
        for name, a in rows.items():
            b = (was.get("targets") or {}).get(name)
            if b is None or "engine" not in a or "engine" not in b:
                continue
            total, engine = a["value"] - b["value"], a["engine"] - b["engine"]
            lines += ["", f"Сдвиг числа `{name}`: {_pp(total)}, из них маржа движка {_pp(engine)}, мост упр. ↔ движок "
                      f"{_pp(total - engine)}; " + (
                          "маржа движка здесь — состав баланса нового якоря при сохранённых скалярах пути."
                          if name == "nim_stationary" else
                          "маржа движка модальной клетки — обучение наблюдением и её путь на отчёте, одном на все "
                          "клетки: клетка стартует со среднего состояния слоя, а ближняя калибровка ЧПМ выравнивает "
                          "только ожидание слоя.")]
    a, b = now.get("levels"), was.get("levels")
    if a:
        lines += ["", f"Уровни после фазы роста, упр. базис, среднее за {a['from_year']}–{a['to_year']} годы "
                  f"({before} → кандидат); модальная клетка — {a['cell']}:", "",
                  "| | " + " | ".join(title for _, title, _ in LEVEL_COLUMNS) + " |",
                  "|---|" + "---|" * len(LEVEL_COLUMNS)]
        for key in a["order"]:
            new, old = a["rows"][key], ((b or {}).get("rows") or {}).get(key) or {}
            cells = []
            for name, _, digits in LEVEL_COLUMNS:
                x, y = old.get(name), new.get(name)
                cells.append("—" if y is None else (f"{_pct(x, digits)} → " if x is not None else "") + _pct(y, digits))
            lines.append(f"| {new.get('title', key)} | " + " | ".join(cells) + " |")
        window = a.get("window")
        if isinstance(window, Mapping):          # окно фактов — поля книги: у кандидата те же; доля кредитов якоря — новая
            old = (b or {}).get("window") or {}
            lines.append("| Окно фактов книги: наименьший…наибольший квартал | " + " | ".join(
                _window_cell(window.get(name), digits, old.get(name)) for name, _, digits in LEVEL_COLUMNS) + " |")
    return lines


def attribution(book: Book, facts: Facts, report: Mapping, *, valuation_date: Any = None,
                version: str | None = None, band_draws: int | None = None, cells: bool = True,
                transmission: str = KEEP, observe: bool = True, marked: Sequence[str] | None = None) -> dict:
    """Кандидат на отчёте `report` и разложение скачка на одной дате оценки (М§15.2):

    обучение    A⁺ − A  прежняя книга с наблюдением, равным ожиданию модели, минус она же без него;
    история     A⁰ − A⁺ (только у книги с миром-опорой κ) та же книга без κ-добавки от реальной ставки закрываемого
                квартала: до сетки реальная ставка у миров общая, и у нового якоря этой добавки нет (М§4.6);
    механика    O − A⁰  каждая клетка перезаякорена на своём пути — должна быть ≈ 0 (A⁰ = A⁺ без мира-опоры);
    выпуклость  E − O   кандидат на ожидаемом отчёте: один отчёт на все клетки (неравенство Йенсена);
    сюрприз     F − E   кандидат на отчёте `report` с той же ближней калибровкой ЧПМ.

    Всегда — точка при значениях книги; медиана полосы — при `band_draws` (одни точки гиперкуба
    на каждой книге; у медианы механика и выпуклость — одной строкой E − A⁺). `checks` — инварианты
    и гейты ядра на прежней книге и на кандидате (дата оценки — та же). `marked` — ключи книги, выведенные на
    ядре (`derived_on_core`): перечень в ручных шагах кандидата."""
    check_report(book, facts, report)
    vdate = valuation_day(valuation_date, report)
    live = live_at(book, facts, vdate)
    run_a = run_grid(book, facts, live)
    plus, run_plus, obs = expected_run(book, facts, live, observe=observe)
    expected = _cell_report(run_plus, _weights(run_plus, None))
    common = dict(valuation_date=vdate, version=version, base_run=run_plus, observe=observe,
                  transmission=transmission)
    cand_e = reanchor(book, facts, expected, **common)
    cand_f = reanchor(book, facts, report, near=cand_e.near, marked=marked, **common)
    live_e, live_f = live_at(cand_e.book, cand_e.facts, vdate), live_at(cand_f.book, cand_f.facts, vdate)
    run_e, run_f = run_grid(cand_e.book, cand_e.facts, live_e), run_grid(cand_f.book, cand_f.facts, live_f)
    # правила книги, которые двигают путь намеренно (квартал доли денег книги К8 = якорь + 2, Р7-6): кандидат без них —
    # путь прежней книги; разность — своя строка разложения, механика меряется без них
    ruled = cand_e.derived.get("cash_share_from")
    kept = None
    if ruled and ruled[1] != (ruled[0] if pindex(ruled[0]) > pindex(cand_e.period) else next_period(cand_e.period)):
        cand_k = reanchor(book, facts, expected, book_rules=False, **common)
        kept = run_grid(cand_k.book, cand_k.facts, live_at(cand_k.book, cand_k.facts, vdate))
    out: dict[str, Any] = {
        "valuation_date": vdate, "observation": obs, "expected": expected, "candidate": cand_f,
        "candidate_expected": cand_e, "transmission": transmission, "band_draws": band_draws,
        "posterior": {"book": dict(run_a.ctx.posterior), "expected": dict(run_plus.ctx.posterior),
                      "candidate": dict(run_f.ctx.posterior)},
        "steps": {"rolled": headline(run_a), "learning": headline(run_plus),
                  **({} if kept is None else {"kept": headline(kept)}),
                  "expected": headline(run_e), "candidate": headline(run_f)},
        "book_rules": {"cash_share_from": ruled} if kept is not None else {},
        "divisor": (_divisor(run_plus), _divisor(run_e)),
        "print_step": float(book.get("valuation.headline.print_step")),
        "checks": {"book": core_checks(run_a, vdate), "candidate": core_checks(run_f, vdate)},
        "growth": growth_spread(run_plus),
    }
    shocked = shock_regimes(run_a) if observe else []
    if shocked:                              # квартал шока: ожидаемый отчёт — среднее двугорбого прогноза (М§12)
        calm = expected_observation(book, facts, live, without=shocked)
        run_calm = run_grid(with_observation(book, calm), facts, live)
        by_regime = {r["regime"]: r for r in _regime_rows(book, facts, live)}
        out["no_shock"] = {"regimes": shocked, "observation": calm, "headline": headline(run_calm),
                           "posterior": dict(run_calm.ctx.posterior),
                           "shock_cor": {r: by_regime[r]["cor_q_mgmt"] for r in shocked},
                           "shock_probability": sum(by_regime[r]["posterior"] for r in shocked)}
    hist = history_run(book, run_plus)
    if hist is not run_plus:                 # κ-добавка закрытого квартала, которой у нового якоря нет (М§4.6)
        out["steps"]["history"] = _priced(run_plus, {c.key: hist.cell(*c.key).v_price for c in run_plus.cells})
        out["history"] = {"adds": lost_kappa_adds(book, run_plus), "world": str(book.get(KAPPA_WORLD)),
                          "period": run_plus.ctx.timeline.period(1 + int(book.get("credit.real_rate_lag_q")))}
    if cells:
        out["mechanics"] = cell_mechanics(book, facts, run_plus, obs, vdate, transmission=transmission,
                                          history=hist)
        out["steps"]["mechanics"] = out["mechanics"]["headline"]
    if band_draws:
        for key, (b, f, lv) in {"rolled": (book, facts, live), "learning": (plus, facts, live),
                                "expected": (cand_e.book, cand_e.facts, live_e),
                                "candidate": (cand_f.book, cand_f.facts, live_f)}.items():
            out["steps"][key]["band"] = band_stats(b, f, lv, band_draws)
    return out


def growth_spread(run: GridRun) -> dict[str, Any] | None:
    """Доля прироста кредитных книг λ в закрываемом квартале по клеткам (М§4.13): наименьшая, наибольшая и масса
    клеток слоя «свой взгляд», где рост урезан капиталом. Рост не ограничен капиталом — None. Отчёт один на все
    клетки и несёт среднее их остатков: при разных λ это часть строки «выпуклость»."""
    if run.ctx.prep.growth is None:
        return None
    prob = run.layers[ANALYTICAL].prob
    lam = {c.key: float(c.quarters["lam"][1]) for c in run.cells}
    cut = [k for k, v in lam.items() if v < 1.0 - 1e-9]
    return {"min": min(lam.values()), "max": max(lam.values()), "cells": len(cut),
            "mass": sum(prob[k] for k in cut), "catch_up": run.ctx.prep.growth.catch_up}


def _regime_rows(book: Book, facts: Facts, live: LiveInputs) -> list[dict]:
    """Прогноз фильтра на первый прогнозный квартал по режимам (упр. базис) и их вероятности."""
    from model.nextreport import model_expectation
    period = str(book.get("meta.first_period"))
    return model_expectation(_drop_observation(book, period), facts, period, live=live)["by_regime"]


def is_dry_run(result: Mapping) -> bool:
    """Отчёт — сам ожидаемый отчёт (сухой прогон): факты обоих кандидатов совпадают."""
    return result["candidate"].facts.digest == result["candidate_expected"].facts.digest


# ------------------------------------------------------------------ REANCHOR.md


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{k}: {_fmt(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)


def _mass(gate: tuple | None) -> str:
    """Масса сработавшего гейта для таблицы проверок: «—» — не сработал."""
    if gate is None:
        return "—"
    return "сработал" if gate[0] is None else f"{gate[0]:.4f}"


def _pct(x: float, digits: int = 2) -> str:
    return f"{x * 100:.{digits}f} %".replace(".", ",")


STEP_TITLES = (
    ("rolled", "прежняя книга на дате оценки (без отчёта)"),
    ("learning", "+ наблюдение, равное ожиданию модели (обучение)"),
    ("history", "− κ-добавка закрытого квартала (история до сетки — общая для миров)"),
    ("mechanics", "каждая клетка — на своём пути (механика, ≈ 0)"),
    ("kept", "кандидат на ожидаемом отчёте, путь прежней книги (выпуклость)"),
    ("expected", "кандидат на ожидаемом отчёте (выпуклость)"),
    ("candidate", "кандидат на отчёте (сюрприз факта)"),
)
BAND_TITLES = (
    ("rolled", "прежняя книга (без отчёта)"),
    ("learning", "+ ожидаемое наблюдение (обучение)"),
    ("expected", "кандидат на ожидаемом отчёте (механика и выпуклость, ≈ 0)"),
    ("candidate", "кандидат на отчёте (сюрприз факта)"),
)


def report_text(book: Book, result: Mapping) -> str:
    """REANCHOR.md: производные величины, «что сдвинулось», разложение скачка, ручные шаги."""
    cand: Reanchored = result["candidate"]
    X, d = cand.data, cand.derived
    M = X["meta"]
    lines = [f"# Перезаякоривание книги {book.get('meta.version')} на отчёт {cand.period}", ""]
    mech = result.get("mechanics")
    diagnosis = result["transmission"] == RESOLVE
    if mech and not mech["ok"]:
        lines += [f"**ОТКАЗ: механика вне допуска** — клетка {mech['worst']['cell']} на своём пути меняет "
                  f"стоимость на {_pct(mech['worst']['rel'], 3)} (допуск {_pct(mech['tolerance'], 1)}): "
                  + ("скаляры пути передачи ставки решены заново — это и есть сдвиг без новости, который снимает "
                     "режим `keep`." if diagnosis else
                     "какое-то правило, помнящее прошлое, не перенесено. Кандидат записан для разбора, "
                     "в канон не переносить."), ""]
    if diagnosis:
        lines += ["**ДИАГНОСТИКА: режим `resolve`.** Цели A-N2, A-N3 и доли оставлены числами прежней книги, "
                  "скаляры пути решены заново на структуре нового якоря — их сдвиг целиком в строке «механика». "
                  "Кандидат книги и фактов не записан: в процедуре перезаякоривания режим один — `keep` "
                  "(М§15.2 п. 8).", ""]
    vday = str(result.get("valuation_date", M["valuation_date"]))
    lines += [f"Кандидат: версия {M['version']}, якорь {M['anchor_period']} (факты на {M['facts_date']}), "
              f"первый прогнозный квартал {M['first_period']}, дата оценки {vday}"
              + (f" (`meta.valuation_date` книги — {M['valuation_date']}: дата цены книги выкупа)"
                 if vday != str(M["valuation_date"]) else "")
              + f". Передача ставки: `{result['transmission']}`.", ""]
    if is_dry_run(result):
        lines += ["Отчёт — ожидаемый (сухой прогон): фактов в нём нет, строка «сюрприз факта» — ноль.", ""]

    eng, mg = d["engine"], d["mgmt"]
    lines += ["## Производные величины", "",
              f"- квартал {cand.period}: ЧПМ движка {_pct(eng['nim'], 3)} (упр. {_pct(mg['nim'], 3)}), "
              f"CoR движка {_pct(eng['cor'], 3)} (упр. {_pct(mg['cor'], 3)}), C/I движка {_pct(eng['cir'], 2)}"]
    if result.get("observation"):
        exp = result["observation"]
        lines.append(f"- ожидание модели на квартал (упр.): ЧПМ {_pct(exp['nim'], 3)}, CoR {_pct(exp['cor'], 3)}")
    if d.get("observation"):
        obs, post = d["observation"], result["posterior"]
        lines.append("- наблюдение A-P2u с замороженными ожиданиями режимов: CoR " + _fmt(obs.get("mu_cor"))
                     + "; ЧПМ " + _fmt(obs.get("mu_nim")))
        lines.append("- вероятности режимов: книга " + _fmt(post["book"]) + " → после ожидаемого наблюдения "
                     + _fmt(post["expected"]) + " → кандидат " + _fmt(post["candidate"]))
        fl = d["regime_floor"]
        lines.append(f"- пол вероятности режима ({fl['share']:g} × базовая): " + _fmt(fl["floors"]) + "; на полу у "
                     "кандидата: " + (", ".join(fl["on_floor"]) or "нет")
                     + " — ниже пола вероятности после наблюдений не опускаются; его действие — в строке «обучение»")
    lines.append(f"- индекс цен квартала {d['price_index']:.6f}"
                 + (f" ({d['price_index_source']})" if d.get("price_index_source") else "")
                 + " — множитель реальных сумм книги и их осей")
    lines.append(f"- множитель плотностей RWA к RWA якоря {d['rwa_factor']:.6f}; вычеты: "
                 + ", ".join(f"`{k}` {_fmt(float(v)) if _num(v) else v}" for k, v in d["deductions"].items()))
    first = str(book.opt("meta.labels.capital.n20_short", "Н20.0"))
    second = str(book.opt("meta.labels.capital.n11_observed", "Н1.1")).split(",")[0]
    lines.append("- поправки «норматив − расчёт»: " + ", ".join(f"`{k}` {float(v):+.6f}" for k, v in d["gaps"].items())
                 + f"; якорь модели: {first} {_pct(d['anchor_row']['n20'], 3)}, {second} {_pct(d['anchor_row']['n11'], 3)}"
                 + (f"; в регуляторном капитале якоря — объявленные дивиденды с вычетом впереди {d['dpreg_anchor']:.3f} млрд ₽"
                    if d.get("dpreg_anchor") else ""))
    if anchor_facts(cand.facts, book.get("nii.books")).estimated:
        lines.append("- **нормативы якоря — оценка до выхода формы** (`capital.estimated`): вычеты и поправки выведены на "
                     "оценке; уровни капитала и RWA якоря — расчётом по ней на RWA модели"
                     + (": " + ", ".join(f"`{k}` {b:.3f}" for k, (_, b) in d["estimated_levels"].items())
                        if d.get("estimated_levels") else "")
                     + "; замена оценки фактом — `--capital-form` без смены якоря")
    if d.get("t2_anchor"):
        lines.append(f"- инструменты капитала: ключ квартала якоря `{T2}` — факт отчёта {d['t2_anchor'][1]:.3f} млрд ₽ "
                     f"(траектория книги давала {d['t2_anchor'][0]:.3f})")
    kept = "; ".join(f"`{k}` {a:.6f} → {b:.6f}" for k, (a, b, _) in d["transmission"].items())
    sig, omega = d["sigmas"], d["phi_weights"]
    lines.append(f"- передача ставки, скаляры пути {', '.join(SCALARS)}: прежняя книга " + _fmt(list(sig["old"]))
                 + ", кандидат " + _fmt(list(sig["new"])) + "; цели и доли на структуре нового якоря при прежних "
                 "скалярах: " + kept
                 + (" — в режиме `resolve` цели и доли оставлены прежними, скаляры решены заново"
                    if d["transmission_mode"] == RESOLVE else ""))
    lv = d.get("level")
    if lv:
        lines.append(f"- уровень маржи — ключ `{NIM_TARGET}`, стационарная маржа мира {lv['world']} на составе баланса "
                     f"якоря (упр.): прежняя книга {_pct(lv['key'][0], 3)} → кандидат {_pct(lv['key'][1], 3)}; по счёту "
                     f"ядра {_pct(lv['value'][0], 3)} → {_pct(lv['value'][1], 3)}, из сдвига маржа движка "
                     f"{_pp(lv['d_engine'])}, мост упр. ↔ движок {_pp(lv['d_bridge'])}; уровень мира-опоры решателя "
                     f"{lv['reference_world']} {_pct(lv['reference'][0], 3)} → {_pct(lv['reference'][1], 3)}"
                     + (f"; цель гейта `{NIM_STATIONARY}` в том же мире {_pct(lv['gate'][0], 3)} → "
                        f"{_pct(lv['gate'][1], 3)}" if lv.get("gate") else "")
                     + (" — ключ оставлен числом прежней книги, скаляры пути решены под него заново"
                        if lv["key"][0] == lv["key"][1] else
                        " — запись прежнего суждения на новом якоре, не пересмотр уровня"))
    if omega["old"]:
        drift = max(abs(omega["new"][b] - omega["old"][b]) for b in omega["old"])
        lines.append("- доли кредитных книг ω в разности опорных ставок X (добавка к стоимости пассивов) — со "
                     "структуры нового якоря: " + ", ".join(
                         f"{b} {omega['old'][b]:.4f} → {omega['new'][b]:.4f}" for b in omega["old"])
                     + f"; наибольший сдвиг {drift * 100:.3f} п.п. — скаляром не сохраняется, эффект в строке "
                     "«механика»")
    lines.append("- мост упр. ↔ МСФО: " + ", ".join(
        f"{x} {d['bridge_old'][x]:+.6f} → {d['bridge_new'][x]:+.6f}" for x in ("cor", "nim", "cir")))
    lines.append("- заморожены числами прежней книги: "
                 + ", ".join(f"`{k}` = {_fmt(v)}" for k, v in d["frozen"].items()))
    if d.get("spread_books"):
        lines.append("- ключи спреда от ставок якоря выведены заново у книг: " + ", ".join(d["spread_books"]))
    lines += pass_lines(d)
    path = result["candidate_expected"].derived.get("nim_path")
    if path:
        lines.append("- ближняя калибровка ЧПМ выведена на ожидаемом отчёте: наибольшее расхождение ожидаемого "
                     f"пути ЧПМ с прежней книгой {path['residual'] * 1e4:.2f} б.п. "
                     f"(кварталы {path['periods'][0]}…{path['periods'][-1]})")

    lines += dividend_lines(d.get("dividends"))
    lines += ["", "## Что сдвинулось в книге", "", "| путь | было | стало | почему |", "|---|---|---|---|"]
    lines += [f"| `{dotted(p)}` | {_fmt(a)} | {_fmt(b)} | {reason(dotted(p))} |" for p, a, b in cand.changes]

    steps = result["steps"]
    lines += ["", f"## Разложение скачка на {result['valuation_date']}: точка при значениях книги", "",
              "Низ — слой «рыночные ставки как есть», верх — «свой взгляд», точка — при λ книги; V0 — млрд ₽.", "",
              "| шаг | низ, ₽ | точка, ₽ | верх, ₽ | V0 свой взгляд | V0 рыночные ставки |",
              "|---|---|---|---|---|---|"]
    prev = None
    for key, title in STEP_TITLES:
        if key not in steps:
            continue
        if key == "kept" and "mechanics" not in steps:
            title = "кандидат на ожидаемом отчёте, путь прежней книги (механика и выпуклость, ≈ 0)"
        elif key == "expected" and "kept" in steps:
            was, now = result["book_rules"]["cash_share_from"]
            title = f"+ правило книги: квартал доли денег К8 = якорь + {CASH_LEAD} ({was} → {now}; Р7-6)"
        elif key == "expected" and "mechanics" not in steps:
            title = "кандидат на ожидаемом отчёте (механика и выпуклость, ≈ 0)"
        h = steps[key]
        now = [h["low"], h["point"], h["high"], h["v0"][ANALYTICAL], h["v0"][NEUTRAL]]
        if prev is None:
            lines.append(f"| {title} | " + " | ".join(f"{x:.2f}" for x in now[:3])
                         + " | " + " | ".join(f"{x:.1f}" for x in now[3:]) + " |")
        else:
            lines.append(f"| {title} | " + " | ".join(f"{x:.2f} ({x - y:+.2f})" for x, y in zip(now[:3], prev[:3]))
                         + " | " + " | ".join(f"{x:.1f} ({x - y:+.1f})" for x, y in zip(now[3:], prev[3:])) + " |")
        prev = now
    if "mechanics" not in steps:
        lines += ["", "Клетки на своём пути не считались (`--no-cells`): механика и выпуклость — одной строкой, "
                  "допуск механики не проверен."]
    n_old, n_new = result.get("divisor") or (None, None)
    if n_old and n_new and abs(n_new / n_old - 1) > 1e-12:
        lines += ["", f"V0 кандидата — на акциях в обращении нового якоря ({n_old:.3f} → {n_new:.3f} млн шт.: выкуп "
                  "закрытого квартала, М3): V0 = стоимость на акцию × акции в обращении, и строки с ним в млрд ₽ "
                  "меняются вместе с делителем; цены в ₽ на акцию сравнимы как есть, механика клеток — на акцию."]
    gone = result.get("history")
    if gone:
        lines += ["", f"**История до сетки.** Пути стоимости риска режимов стоят в мире {gone['world']}; в прочих мирах к ним "
                  "идёт κ-добавка от реальной ставки с лагом. Реальная ставка закрываемого квартала давала в "
                  f"{gone['period']} добавку " + ", ".join(f"{w}: {v * 100:+.2f} п.п." for w, v in gone["adds"].items())
                  + "; у нового якоря этот квартал — история, общая для миров, и добавки нет (М§4.6). Строка «история до "
                  "сетки» — цена этого свойства ядра; клетки на своём пути и кандидат сверяются с прежней книгой уже без "
                  "добавки, в допуск механики строка не входит."]
    growth = result.get("growth")
    if growth and growth["cells"]:
        lines += ["", f"**Рост, ограниченный капиталом.** В закрываемом квартале доля прироста кредитных книг по клеткам — от "
                  f"{growth['min']:.2f} до {growth['max']:.2f}; рост урезан в {growth['cells']} клетках с массой "
                  f"{_pct(growth['mass'], 1)} слоя «свой взгляд». Отчёт один на все клетки и несёт среднее их остатков: "
                  "клетка, чей рост был урезан сильнее среднего, стартует с большего портфеля, и наоборот — это часть "
                  "строки «выпуклость», в строку «механика» не входит."
                  + ("" if not growth["catch_up"] else " Навёрстывание включено: разрыв с потенциальным путём при переносе "
                     "якоря стирается, и строка «механика» урезанных клеток не ноль.")]
    calm = result.get("no_shock")
    if calm:
        exp, a, plus, h = result["observation"], steps["rolled"], steps["learning"], calm["headline"]
        names = ", ".join(calm["regimes"])
        lines += ["", f"**Квартал шока режима {names}.** Закрываемый квартал лежит в году шока прежней книги: прогноз "
                  "наблюдения двугорбый — шок либо случился, либо нет. Ожидаемый отчёт несёт долю шока (CoR "
                  f"{_pct(exp['cor'], 3)} — смесь, в которой с вероятностью {_pct(calm['shock_probability'], 1)} "
                  "стоит CoR " + ", ".join(_pct(v, 2) for v in calm["shock_cor"].values()) + "): такого числа не ждёт "
                  "ни один режим, и «отчётом без новостей» он не является — фильтр читает его как стресс (М§12). "
                  f"Отчёт без шока — ожидание прочих режимов, CoR {_pct(calm['observation']['cor'], 3)}, ЧПМ "
                  f"{_pct(calm['observation']['nim'], 3)}: строка «обучение» — {h['point'] - a['point']:+.2f} ₽ точки "
                  f"(на ожидаемом отчёте {plus['point'] - a['point']:+.2f} ₽), вероятности режимов "
                  + _fmt(calm["posterior"]) + ". В журнал версии книги — оба числа."]
    if mech:
        worst = sorted(mech["rows"], key=lambda r: -abs(r["rel"]))[:5]
        lines += ["", "### Механика по клеткам", "",
                  f"Клеток {len(mech['rows'])}; наибольшее изменение стоимости клетки на своём пути — "
                  f"{_pct(mech['worst']['rel'], 4)} ({mech['worst']['cell']}); допуск {_pct(mech['tolerance'], 1)} — "
                  + ("выполнен." if mech["ok"] else "НАРУШЕН.")]
        if mech["rearmed"]:
            lines.append(f"Год якоря сменился: клетки режима {', '.join(mech['rearmed'])} «перезаряжены» (год шока "
                         "сдвинут, М§3.2) — их путь другой по определению, в допуск они не входят.")
        if mech.get("history"):
            top = max(mech["rows"], key=lambda r: abs(r["history"]))
            lines.append("База сравнения — прежняя книга без κ-добавки закрытого квартала (история до сетки): сама добавка "
                         f"меняет стоимость клетки не больше чем на {_pct(abs(top['history']), 4)} ({top['cell']}) и в "
                         "допуск не входит.")
            lines += ["", "| клетка | V прежняя, млрд ₽ | без κ-добавки закрытого квартала | V на своём пути | "
                      "изменение к базе |", "|---|---|---|---|---|"]
            lines += [f"| {r['cell']}{' (перезаряжена)' if r['rearmed'] else ''} | {r['old']:.1f} | {r['base']:.1f} "
                      f"({_pct(r['history'], 4)}) | {r['new']:.1f} | {_pct(r['rel'], 4)} |" for r in worst]
        else:
            lines += ["", "| клетка | V прежняя, млрд ₽ | V на своём пути | изменение |", "|---|---|---|---|"]
            lines += [f"| {r['cell']}{' (перезаряжена)' if r['rearmed'] else ''} | {r['old']:.1f} | {r['new']:.1f} | "
                      f"{_pct(r['rel'], 4)} |" for r in worst]

    lines += ["", "## Заголовок — медиана полосы", ""]
    if result.get("band_draws"):
        lines += [f"{result['band_draws']} прогонов на книгу, одни точки гиперкуба (сравнение парное); шаг печати "
                  f"{result['print_step']:g} ₽. У медианы механика и выпуклость — одной строкой"
                  + (" (в ней же — снятая κ-добавка закрытого квартала: у точки она стоит отдельной строкой)."
                     if result.get("history") else "."), "",
                  "| шаг | P10 | медиана | P90 | P(центр < рынка) |", "|---|---|---|---|---|"]
        before = None
        for key, title in BAND_TITLES:
            b = steps[key]["band"]
            if before is None:
                lines.append(f"| {title} | {b['p10']:.1f} | {b['median']:.1f} | {b['p90']:.1f} | {b['p_below']:.1%} |")
            else:
                lines.append(f"| {title} | " + " | ".join(
                    f"{b[k]:.1f} ({b[k] - before[k]:+.1f})" for k in ("p10", "median", "p90"))
                    + f" | {b['p_below']:.1%} ({(b['p_below'] - before['p_below']) * 100:+.1f} п.п.) |")
            before = b
    else:
        lines.append("Не считалась: разложение печатаемого заголовка — ключом `--band ПРОГОНОВ` (четыре полосы).")
    checks = result.get("checks")
    if checks:
        was, now = checks["book"], checks["candidate"]
        lines += ["", "## Проверки ядра на кандидате", ""]
        if now["error"]:
            lines.append(f"**Проверки не посчитаны:** {now['error']}")
        else:
            lines.append("Инварианты: " + ("выполнены все." if not now["invariants"] else "НАРУШЕНЫ — " + "; ".join(
                f"`{name}`: {message}" for name, message in now["invariants"])))
            names = list(dict.fromkeys(list(was["gates"]) + list(now["gates"])))
            if names:
                lines += ["", "Сработавшие гейты (масса — вероятность клеток, где условие нарушено: слоя «свой взгляд», у "
                          "гейта знака стресса — под вероятностями точки, у гейтов уровня книги — 1); каждому на "
                          "новой книге нужно действующее объяснение — `gate_explanations.yaml`, решение книги:", "",
                          "| гейт | прежняя книга | кандидат | сообщение на кандидате |", "|---|---|---|---|"]
                lines += [f"| `{n}` | {_mass(was['gates'].get(n))} | {_mass(now['gates'].get(n))} | "
                          f"{now['gates'][n][1] if n in now['gates'] else 'не сработал'} |" for n in names]
            else:
                lines.append("Сработавших гейтов нет.")
            if now.get("flags"):
                lines += ["", "Флаги ядра на кандидате (плашка, сборку не блокируют): "
                          + "; ".join(f"`{n}` — {m}" for n, m in now["flags"].items())]
            lines += target_lines(was, now)
            if was["error"]:
                lines += ["", f"На прежней книге проверки не посчитаны: {was['error']}"]
    if result.get("facts_check") is not None:
        lines += ["", "## Сверка фактов кандидата с пересобранными фактами", ""]
        if result["facts_check"]:
            lines += ["| поле якоря | кандидат | пересобранные факты |", "|---|---|---|"]
            lines += [f"| `{k}` | {_fmt(a)} | {_fmt(b)} |" for k, a, b in result["facts_check"]]
        else:
            lines.append("Расхождений нет: ядро читает из обоих наборов одно и то же состояние якоря.")
    lines += ["", "## Предупреждения и ручные шаги", ""] + [f"- {w}" for w in cand.warnings]
    lines += ["", "Механика ≈ 0 — инвариант `tests/test_reanchor*.py` (М§15.2): клетка на своём пути сохраняет "
              "стоимость в пределах 0,1 %. Строка «выпуклость» — неравенство Йенсена: отчёт один на все клетки, "
              "а слой «рыночные ставки как есть» ждал путь своего мира.", ""]
    return "\n".join(lines)


def pass_lines(d: Mapping[str, Any]) -> list[str]:
    """Строки производных величин о ключах проходов ядра 1–5 (docs/REANCHOR.md §3.16); у книги без них — пусто."""
    out: list[str] = []
    if d.get("deduction_form") == "own_funds":
        out.append("- вычеты якоря — правилом книги: капитал модели якоря без вычетов минус капитал нормативов банка "
                   "(форма 0409123: собственные средства, основной капитал); концы связки с долей признания фонда ССПСД "
                   "— тем же правилом при доле конца")
    if d.get("rwa_surprise") is not None:
        factors = d.get("rwa_factors") or {}
        special = {k: v for k, v in factors.items() if abs(v - d["rwa_factor"]) > 1e-12}
        out.append(f"- RWA по слагаемым модели (К5, К8): сюрприз RWA к модели прежней книги на остатках якоря "
                   f"{d['rwa_surprise']:.6f}; плотности × {d['rwa_factor']:.6f}"
                   + ("; свои множители: " + ", ".join(f"`{k}` × {v:.6f}" for k, v in special.items()) if special else ""))
    bc = d.get("book_cor")
    if bc:
        out.append(f"- состав кредитов (М7): CoR клетки на составе нового якоря × f = {bc['factor']:.6f} — пути CoR "
                   f"режимов `v′ = f v + (f − 1) b` (b = {bc['bridge']:+.6f}), κ × f; доли книг в кредитах АС "
                   + ", ".join(f"{b} {bc['shares_old'][b]:.4f} → {bc['shares_new'][b]:.4f}" for b in bc["shares_old"]))
    for key, m in (d.get("line_mix") or {}).items():
        out.append(f"- смесь базы `{key}` (К2б): доли строки на составе нового якоря "
                   + ", ".join(f"{k} {m['was'][k]:.4f} → {m['now'][k]:.4f} (рост компоненты {m['growth'][k] - 1:+.4%})"
                               for k in m["now"]))
    ls = d.get("line_shares")
    if ls:
        out.append(f"- доли базы расходов на базах строк `{LINE_SHARES}` (К2): " + ", ".join(
            f"{k} {ls['was'][k]:.4f} → {ls['now'][k]:.4f}" for k in ls["now"])
            + f"; рост средних за квартал: база расходов {ls['base_growth'] - 1:+.4%}, строки "
            + ", ".join(f"{k} {v - 1:+.4%}" for k, v in ls["line_growth"].items()))
    cs = d.get("cash_structure")
    if cs:
        out.append(f"- доля денег книги (К8): ρ = `volumes.other_assets_to_loans` на структуре нового якоря — отношение "
                   f"якоря {cs['rho_anchor']:.6f} → {cs['rho']:.6f} (драйвер денег к кредитам {cs['a_old']:.4f} → "
                   f"{cs['a_new']:.4f}; доля денег якоря {_pct(cs['c_new'], 3)}, книги с ФОР {_pct(cs['c_star'], 3)}) — "
                   "путь прочих активов прежний")
    cash = d.get("cash_share_from")
    if cash:
        out.append(f"- доля денег книги (К8): квартал `{CASH}.share_from` {cash[0]} → {cash[1]}"
                   + (f" (правило Р7-6: якорь + {CASH_LEAD})" if cash[0] != cash[1] else " (путь прежней книги)"))
    bb = d.get("buyback")
    if bb:
        gone = [f"`{BUYBACK}.{k}.{p}`" for k, ps in bb.items() for p in ps]
        out.append("- выкуп (М3): закрытый квартал — история (капитал после выкупа и акции в обращении — в фактах "
                   "нового якоря, делитель — они же)" + ("; сняты ключи " + ", ".join(gone) if gone else ""))
    return out


def dividend_lines(div: Mapping | None) -> list[str]:
    """Раздел «Дивиденды по периодам» (квартальный календарь, М§15.2 п. 9)."""
    if not div:
        return []
    was, now = div["p_last"]
    lines = ["", "## Дивиденды по периодам", "",
             f"Последний закрытый квартал прибыли: {was} → {now} — по самой поздней строке истории дивидендов с днём "
             "решения не позже даты фактов; дивиденд закрытого квартала уже вычтен из капитала якоря, в клетке его нет."]
    if div["closed"]:
        lines += ["", "Строки истории, закрывшие кварталы прибыли на новом якоре:", "",
                  "| квартал прибыли | DPS, ₽ | день решения |", "|---|---|---|"]
        lines += [f"| {r['period']} | {r['dps']:.4f} | {r['decided_date']} |" for r in div["closed"]]
    else:
        lines += ["", "Новых решений в закрытом квартале нет: закрытые кварталы прибыли те же."]
    listed = sum(r["amount"] for r in div["queue"])
    lines += ["", f"Объявлено и не выплачено на новом якоре: {listed:.3f} млрд ₽ из остатка «дивиденды к выплате» "
              f"{div['payable']:.3f}; остаток сверх списка — постоянное обязательство: не выплачивается и в регуляторный "
              "капитал не возвращается."]
    if div["queue"]:
        lines += ["", "| квартал прибыли | сумма, млрд ₽ | квартал выплаты | вычет из регуляторного капитала |", "|---|---|---|---|"]
        lines += [f"| {r['period']} | {r['amount']:.3f} | {r['pay']} | {r['reg'] or 'уже вычтен'} |" for r in div["queue"]]
    lines += ["", "Записи реестра в затравке нового якоря: " + (", ".join(div["seed"]) or "нет")
              + "; выпали (экс-дата не позже новой даты фактов): " + (", ".join(div["dropped"]) or "нет")
              + "; добавлены из решений отчёта: " + (", ".join(div["added"]) or "нет") + "."]
    return lines


# ------------------------------------------------------------------ шаблон книги


def _bare(text: str) -> bool:
    return bool(text) and text.isascii() and text.replace("_", "a").isalnum() and not text[0].isdigit() \
        and text.lower() not in ("null", "true", "false", "yes", "no", "on", "off")


def _flow(value: Any) -> str:
    """Значение в строку потока YAML (ключи-периоды в кавычках, как в шаблоне книги)."""
    if isinstance(value, Mapping):
        return "{" + ", ".join((str(k) if _bare(str(k)) else json.dumps(str(k), ensure_ascii=False))
                               + ": " + _flow(v) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        text = repr(value)
        mantissa = text.split("e")[0]
        if isinstance(value, float) and "e" in text and "." not in mantissa:
            text = text.replace("e", ".0e", 1)   # YAML 1.1 (PyYAML) читает -8e-06 строкой, -8.0e-06 — числом
        return text
    return str(value) if _bare(str(value)) else json.dumps(str(value), ensure_ascii=False)


def _span(node: yaml.Node) -> tuple[int, int]:
    """Границы узла в тексте; у блочной коллекции конец — конец последнего элемента (без хвоста
    из пустых строк и комментариев)."""
    if isinstance(node, yaml.ScalarNode) or getattr(node, "flow_style", False) or not node.value:
        return node.start_mark.index, node.end_mark.index
    last = node.value[-1]
    return node.start_mark.index, _span(last[1] if isinstance(last, tuple) else last)[1]


def _find(node: yaml.Node | None, path: Path_) -> yaml.Node | None:
    for part in path:
        if isinstance(part, tuple):
            if not isinstance(node, yaml.SequenceNode):
                return None
            node = next((item for item in node.value if isinstance(item, yaml.MappingNode) and any(
                k.value == part[0] and getattr(v, "value", None) == part[1] for k, v in item.value)), None)
        else:
            if not isinstance(node, yaml.MappingNode):
                return None
            node = next((v for k, v in node.value if str(k.value) == part), None)
        if node is None:
            return None
    return node


def _value_at(data: Any, path: Path_) -> Any:
    for part in path:
        if isinstance(part, tuple):
            data = next(x for x in data if isinstance(x, Mapping) and x.get(part[0]) == part[1])
        else:
            data = data[part]
    return data


def _block_key_span(text: str, root: yaml.Node, path: Path_) -> tuple[int, int] | None:
    """Строки ключа `path` блочного словаря шаблона: от начала строки ключа до конца строки значения и строки
    комментариев-продолжений под ним (отступ глубже ключа). Родитель — не блочный словарь — None."""
    if len(path) < 2 or isinstance(path[-1], tuple):
        return None
    parent = _find(root, path[:-1])
    if not isinstance(parent, yaml.MappingNode) or parent.flow_style:
        return None
    pair = next(((k, v) for k, v in parent.value if str(k.value) == path[-1]), None)
    if pair is None:
        return None
    key, value = pair
    start = text.rfind("\n", 0, key.start_mark.index) + 1
    end = text.find("\n", _span(value)[1])
    stop = len(text) if end < 0 else end + 1
    while stop < len(text):
        end = text.find("\n", stop)
        line = text[stop:len(text) if end < 0 else end]
        body = line.lstrip()
        if not (body.startswith("#") and len(line) - len(body) > key.start_mark.column):
            break
        stop = len(text) if end < 0 else end + 1
    return start, stop


def patch_template(text: str, cand: Reanchored) -> str:
    """Шаблон книги с правками кандидата: меняется только текст изменившихся значений,
    комментарии остаются. Результат сверяется с кандидатом целиком; расхождение — отказ."""
    root = yaml.compose(text)
    edits: dict[Path_, tuple[int, int, str]] = {}
    for path, _old, new in cand.changes:
        target = path
        node = _find(root, target)
        gone = _block_key_span(text, root, path) if new is None and node is not None else None
        if gone is not None:                         # ключ блочного словаря убран — строки ключа уходят, комментарии
            edits[path] = (*gone, "")                # соседей остаются
            continue
        while node is None or new is None:           # ключ добавлен или убран — правится родитель
            target = target[:-1]
            if not target:
                raise ReportError(f"шаблон книги: нет узла для правки {dotted(path)}")
            node = _find(root, target)
            new = True
        edits[target] = (*_span(node), _flow(_value_at(cand.data, target)))
    out = text
    chosen = [p for p in edits if not any(p[:n] in edits for n in range(1, len(p)))]
    for path in sorted(chosen, key=lambda p: -edits[p][0]):
        start, stop, new_text = edits[path]
        out = out[:start] + new_text + out[stop:]
    got, want = _plain(yaml.safe_load(out)), _plain(cand.data)
    for w in want["worlds"].get("ids", []):          # блоки миров и надстройку вписывает сборка книги
        if w not in got["worlds"]:
            want["worlds"].pop(w, None)
    if "worlds_bank" not in got:
        want.pop("worlds_bank", None)
    if _get(got, "worlds.overlay.sha256") is None:
        want["worlds"]["overlay"]["sha256"] = None
    if got != want:
        raise ReportError("шаблон книги после правок не равен кандидату — правки шаблона переносятся "
                          "вручную по таблице «что сдвинулось»")
    return out


# ------------------------------------------------------------------ сверка фактов


def _beyond_anchor(book: Book, facts: Facts) -> dict[str, Any]:
    """Состояние, которое ядро читает из фактов сверх `anchor_facts`: постоянные прочие активы, экономически
    собственные акции, значения мостов, а при квартальном календаре — список «объявлено, не выплачено», строки
    истории дивидендов (квартал прибыли → DPS и день решения) и затравка реестра; при связи строк с объёмом —
    базы объёма пяти концов кварталов."""
    out: dict[str, Any] = {}
    bal, shares = facts.file("balance"), facts.file("shares")
    if isinstance(bal.get("other_assets_fixed"), Mapping):
        out["other_assets_fixed"] = _fact(bal["other_assets_fixed"])
    if isinstance(shares.get("economic_treasury"), Mapping):
        out["economic_treasury"] = _fact(shares["economic_treasury"])
    out["bridge"] = {x: facts.v("bridge_mgmt_ifrs", f"{x}.value") for x in ("cor", "nim", "cir")}
    if is_quarterly(book):
        out["dividends_payable_declared"] = {str(_fact(x.get("period"))): _fact(x.get("amount"))
                                             for x in bal.get("dividends_payable_declared") or []}
        div = facts.file("dividends")
        out["dividend_history"] = {str(_fact(r.get("period"))): {"dps": history_dps(r),
                                                                 "decided_date": str(_fact(r.get("decided_date")))}
                                   for r in div.get("history") or []}
        out["register_seed"] = {str(_fact(r.get("period"))): {"dps": _fact(r.get("dps")), "status": _fact(r.get("status"))}
                                for r in div.get("register_seed") or []}
    base = book.opt("volumes.link_base")
    if base and any(float(book.opt(p, 0.0)) for p in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link")):
        rows = facts.periods("balance", "history")
        last = sorted(rows, key=pindex)[-5:]
        out["volume_base"] = {p: _fact(rows[p].get(base)) for p in last}
    return out


def compare_facts(book: Book, candidate: Facts, other: Facts, tol: float = 1e-6) -> list[tuple[str, Any, Any]]:
    """Состояние якоря, которое ядро читает из фактов кандидата и из пересобранных фактов
    (`build_facts.py --anchor` или `--expected`): поля, разошедшиеся больше допуска."""
    books = book.get("nii.books")
    a, b = asdict(anchor_facts(candidate, books)), asdict(anchor_facts(other, books))
    a.update(_beyond_anchor(book, candidate))
    b.update(_beyond_anchor(book, other))
    if a.get("estimated") and b.get("estimated"):
        # нормативы — оценка до выхода формы: уровни капитала и RWA кандидат несёт расчётом по оценке, а сборщик —
        # значениями последней формы с пометкой оценки; сверяются нормативы, уровни придут с формой
        for key in ESTIMATED_LEVELS:
            a.pop(key, None)
            b.pop(key, None)
    out: list[tuple[str, Any, Any]] = []

    def walk(x: Any, y: Any, where: str) -> None:
        if isinstance(x, Mapping) and isinstance(y, Mapping):
            for k in sorted(set(x) | set(y), key=str):
                if where == "pnl" and (k not in x or k not in y):
                    continue                     # история ОПУ разной глубины — не состояние якоря
                walk(x.get(k), y.get(k), f"{where}.{k}" if where else str(k))
        elif _num(x) and _num(y):
            if abs(x - y) > tol * max(1.0, abs(x), abs(y)):
                out.append((where, x, y))
        elif x != y:
            out.append((where, x, y))

    walk(a, b, "")
    return out


# ------------------------------------------------------------------ замена оценки нормативов фактом формы


def read_form(path: Path) -> dict:
    form = read_report(path)
    return form


def check_form(book: Book, facts: Facts, form: Mapping) -> None:
    """Файл формы (`capital-form/1`): нормативы и капитал банковской группы на дату якоря книги."""
    unknown = sorted(set(form) - set(CAPITAL_FORM_REQUIRED) - set(CAPITAL_FORM_OPTIONAL))
    missing = [k for k in CAPITAL_FORM_REQUIRED if k not in form]
    if unknown or missing:
        raise ReportError("файл формы: " + "; ".join(x for x in (
            f"незнакомые ключи {', '.join(unknown)}" if unknown else "",
            f"нет ключей {', '.join(missing)}" if missing else "") if x)
            + f" (известны: {', '.join(CAPITAL_FORM_REQUIRED + CAPITAL_FORM_OPTIONAL)})")
    if form.get("schema", CAPITAL_FORM) != CAPITAL_FORM:
        raise ReportError(f"файл формы: schema {form['schema']!r}, ожидается {CAPITAL_FORM!r}")
    anchor = str(book.get("meta.anchor_period"))
    if str(form["period"]) != anchor or str(facts.plain("anchor", "period")) != anchor:
        raise ReportError(f"файл формы за {form['period']}, якорь книги — {anchor}, фактов — "
                          f"{facts.plain('anchor', 'period')}: замена оценки идёт на якоре книги, без его смены")
    if "as_of" in form and str(form["as_of"]) != period_end(anchor).isoformat():
        raise ReportError(f"файл формы: as_of {form['as_of']} — не конец квартала якоря {anchor}")
    for key in CAPITAL_FORM_REQUIRED[1:] + ("t2",):
        if key in form and not _num(form[key]):
            raise ReportError(f"файл формы: {key} = {form[key]!r} — ожидается число")
    for key in ("n20_0", "n1_1_bank"):
        _fraction(float(form[key]), key)
    for key in ("basel_cet1", "basel_rwa", "bank_base_capital"):
        if form[key] <= 0:
            raise ReportError(f"файл формы: {key} = {form[key]} — ожидается положительное число")
    if "n20_pre_dividend" in form and not isinstance(form["n20_pre_dividend"], bool):
        raise ReportError("файл формы: n20_pre_dividend — true или false")
    if own_funds_form(facts):                # из капитала нормативов банка книга выводит вычеты якоря
        missing = [k for k in OWN_FUNDS if k not in form]
        if missing:
            raise ReportError(f"файл формы: нет {', '.join(missing)} — факты якоря несут капитал нормативов банка, из "
                              "него книга выводит вычеты (docs/REANCHOR.md §3.16)")
        for key in OWN_FUNDS:
            if not _num(form[key]) or form[key] <= 0:
                raise ReportError(f"файл формы: {key} = {form[key]!r} — ожидается положительное число")


def facts_with_form(facts: Facts, form: Mapping) -> Facts:
    """Факты того же якоря с нормативами и капиталом формы: оценка заменена фактом, пометки оценки сняты."""
    period = str(form["period"])
    tag = f"reanchor: форма на якорь {period}" + (f" ({form['source']})" if form.get("source") else "")
    files = copy.deepcopy(dict(facts.files))
    cap = files["capital"]
    values = {"n20_0.value": form["n20_0"], "n1_1_bank.value": form["n1_1_bank"], "basel.cet1": form["basel_cet1"],
              "basel.rwa": form["basel_rwa"], "bank_base_capital": form["bank_base_capital"]}
    if "t2" in form:
        values["t2_recognized"] = form["t2"]
    for key in OWN_FUNDS:
        if key in form:
            values[key] = form[key]
    if isinstance(_get(cap, "basel.cet1_ratio"), dict):
        values["basel.cet1_ratio"] = _r(form["basel_cet1"] / form["basel_rwa"], 6)
    for path, value in values.items():
        _set(cap, path, _node(float(value), tag))
    for name in ESTIMATE_SLOTS.values():
        if "estimated" in cap[name]:
            cap[name]["estimated"] = False
        cap[name].pop("estimate", None)
    if "n20_pre_dividend" in form:
        cap["n20_0"]["pre_dividend"] = bool(form["n20_pre_dividend"])
        cap["n20_0"].pop("pre_dividend_note", None)
    t2 = form.get("t2", _get(cap, "t2_recognized.v"))
    known = {"n20_0": form["n20_0"], "cet1": form["basel_cet1"], "rwa": form["basel_rwa"], "n1_1_bank": form["n1_1_bank"],
             "n20_1": form["n1_1_bank"], "capital_base": form["bank_base_capital"], "capital_additional": t2,
             "capital_total": None if t2 is None else form["basel_cet1"] + t2, "rwa_imputed": form["basel_rwa"]}
    rows = cap.get("history")
    row = (rows.get(period) if isinstance(rows, dict)
           else next((r for r in rows or [] if isinstance(r, dict) and r.get("period") == period), None))
    if isinstance(row, dict):
        for key, value in known.items():
            if isinstance(row.get(key), dict) and value is not None:
                row[key] = _node(_r(float(value)), tag)
    return Facts(root=Path(f"capital-form-{period}"), files=files,
                 digest=hashlib.sha256(canonical_json(files)).hexdigest())


def replace_capital(book: Book, facts: Facts, form: Mapping, *, valuation_date: Any = None,
                    version: str | None = None) -> dict:
    """Замена оценки нормативов якоря фактом формы БЕЗ смены якоря (М§3.3, §15.2 п. 10): факты капитала —
    значения формы, пометка оценки снята; калибровки к якорю выводятся заново тем же правилом, что при
    переносе якоря, — вычеты формулой книги, плотности RWA общим множителем к RWA формы, ключ квартала якоря
    траектории инструментов капитала, поправки «норматив − расчёт». Ближняя калибровка ЧПМ, наблюдения и
    передача ставки не трогаются: квартал тот же. Возвращает кандидата и точку до и после на дате оценки —
    это строка «факты» разложения между выпусками (М§16), а не механика."""
    check_form(book, facts, form)
    anchor = str(book.get("meta.anchor_period"))
    try:
        vdate = to_date(valuation_date or book.get("meta.valuation_date"))
    except ValueError as exc:
        raise ReportError(f"дата оценки {valuation_date!r} — не дата ГГГГ-ММ-ДД") from exc
    warnings: list[str] = []
    derived: dict[str, Any] = {"was_estimated": list(anchor_facts(facts, book.get("nii.books")).estimated)}
    if not derived["was_estimated"]:
        warnings.append("нормативы якоря в фактах не помечены оценкой: файл формы заменяет факт фактом — проверить, "
                        "что это исправление, а не повторная замена")
    X = copy.deepcopy(dict(book.source))
    X["meta"].update(version=version or f"{X['meta']['version']}+form", valuation_date=vdate.isoformat())
    new_facts = facts_with_form(facts, form)
    if _get(X, T2) is not None and form.get("t2") is not None:
        traj = _get(X, T2)
        now = Trajectory(traj).value(*parse_period(anchor))
        if abs(float(form["t2"]) - now) > T2_TOL:
            if not isinstance(traj, Mapping):
                raise ReportError(f"{T2} — скаляр, а инструменты капитала формы {form['t2']} отличаются от него: нужна "
                                  "траектория с ключом квартала якоря (решение книги)")
            _set(X, T2, _sorted_traj({**traj, anchor: _r(float(form["t2"]), 6)}))
            derived["t2_anchor"] = (now, float(form["t2"]))
            warnings.append(f"{T2}: ключ квартала якоря {anchor} — факт формы {float(form['t2']):g} (было {now:g}); "
                            "остальные ключи траектории — суждение книги: пересмотреть")
    calibrate_capital(X, new_facts, float(form["basel_rwa"]), derived, warnings)
    check_bundles(X, book.source)
    fact = {"n20": float(form["n20_0"]), "n11": float(form["n1_1_bank"])}
    for _ in range(PASSES):
        run = run_grid(book_from_dict(X, facts=new_facts), new_facts)
        weights = _weights(run, None)
        moved = 0.0
        for path, name in GAPS:
            delta = fact[name] - _anchor_row(run, weights, name)
            if abs(delta) > GAP_TOL:
                value = float(_get(X, path))
                _set(X, path, _r(value + delta, 12))
                _remap_axes(X, path, value, value + delta)
                moved = max(moved, abs(delta))
        if moved <= GAP_TOL:
            break
    cand = book_from_dict(X, facts=new_facts)
    live_a, live_b = live_at(book, facts, vdate), live_at(cand, new_facts, vdate)
    run_a, run_b = run_grid(book, facts, live_a), run_grid(cand, new_facts, live_b)
    weights = _weights(run_b, None)
    derived.update(gaps={path: _get(X, path) for path, _ in GAPS},
                   anchor_row={name: _anchor_row(run_b, weights, name) for _, name in GAPS},
                   old_values={"n20": anchor_facts(facts, book.get("nii.books")).n20,
                               "n11": anchor_facts(facts, book.get("nii.books")).n11_bank})
    warnings += ["оси поправок нормативов сдвинуты вместе с центром: ширину пересмотреть (решение книги)",
                 "объяснения гейтов, результаты книги и закреплённые числа — на новой версии книги; в разложении "
                 "между выпусками замена оценки фактом — строка «факты» (М§16)",
                 "канон фактов пересобирает `ops/tools/build_facts.py` (форма — в листе формы группы папки передачи); "
                 "сверка с фактами кандидата — `--compare-facts`"]
    candidate = Reanchored(data=X, book=cand, facts=new_facts, period=anchor, derived=derived,
                           changes=diff(dict(book.source), X), warnings=warnings,
                           near=copy.deepcopy(X["regimes"]["near_nim_shift"]))
    return {"candidate": candidate, "valuation_date": vdate, "form": dict(form),
            "steps": {"book": headline(run_a), "candidate": headline(run_b)},
            "print_step": float(book.get("valuation.headline.print_step")),
            "checks": {"book": core_checks(run_a, vdate), "candidate": core_checks(run_b, vdate)}}


def form_text(book: Book, result: Mapping) -> str:
    """REANCHOR.md режима `--capital-form`: что заменено, что выведено заново, сдвиг точки от замены оценки фактом."""
    cand: Reanchored = result["candidate"]
    d, M, form = cand.derived, cand.data["meta"], result["form"]
    first = str(book.opt("meta.labels.capital.n20_short", "Н20.0"))
    second = str(book.opt("meta.labels.capital.n11_observed", "Н1.1")).split(",")[0]
    a, b = result["steps"]["book"], result["steps"]["candidate"]
    lines = [f"# Замена оценки нормативов фактом формы: книга {book.get('meta.version')}, якорь {cand.period}", "",
             f"Кандидат: версия {M['version']}, якорь прежний — {M['anchor_period']} (факты на {M['facts_date']}), дата "
             f"оценки {M['valuation_date']}. Перезаякоривания нет: квартал тот же, меняются факты капитала и калибровки "
             "к якорю.", "",
             "## Что заменено", "",
             f"- {first}: {_pct(d['old_values']['n20'], 3)} → {_pct(float(form['n20_0']), 3)}; {second}: "
             f"{_pct(d['old_values']['n11'], 3)} → {_pct(float(form['n1_1_bank']), 3)}"
             + (" (прежние значения — оценка: " + ", ".join(d["was_estimated"]) + ")" if d["was_estimated"] else ""),
             f"- множитель плотностей RWA к RWA формы {d['rwa_factor']:.6f}; вычеты: "
             + ", ".join(f"`{k}` {_fmt(float(v)) if _num(v) else v}" for k, v in d["deductions"].items()),
             "- поправки «норматив − расчёт»: " + ", ".join(f"`{k}` {float(v):+.6f}" for k, v in d["gaps"].items())
             + f"; якорь модели: {first} {_pct(d['anchor_row']['n20'], 3)}, {second} {_pct(d['anchor_row']['n11'], 3)}"]
    if d.get("t2_anchor"):
        lines.append(f"- инструменты капитала: ключ квартала якоря `{T2}` {d['t2_anchor'][0]:.3f} → {d['t2_anchor'][1]:.3f} млрд ₽")
    lines += ["", "## Что сдвинулось в книге", "", "| путь | было | стало | почему |", "|---|---|---|---|"]
    lines += [f"| `{dotted(p)}` | {_fmt(x)} | {_fmt(y)} | "
              f"{'новая версия книги на том же якоре' if dotted(p).startswith('meta.') else reason(dotted(p)) or 'замена оценки фактом формы'} |"
              for p, x, y in cand.changes]
    lines += ["", f"## Сдвиг точки на {result['valuation_date']} (строка «факты»)", "",
              "| | низ, ₽ | точка, ₽ | верх, ₽ |", "|---|---|---|---|",
              f"| книга на оценке нормативов | {a['low']:.2f} | {a['point']:.2f} | {a['high']:.2f} |",
              f"| кандидат на форме | {b['low']:.2f} ({b['low'] - a['low']:+.2f}) | {b['point']:.2f} "
              f"({b['point'] - a['point']:+.2f}) | {b['high']:.2f} ({b['high'] - a['high']:+.2f}) |"]
    band = result.get("band")
    if band:
        x, y = band
        lines += ["", f"Медиана полосы ({result['band_draws']} прогонов, одни точки гиперкуба): {x['median']:.1f} → "
                  f"{y['median']:.1f} ({y['median'] - x['median']:+.1f}); P10 {x['p10']:.1f} → {y['p10']:.1f}; "
                  f"P90 {x['p90']:.1f} → {y['p90']:.1f}."]
    was, now = result["checks"]["book"], result["checks"]["candidate"]
    lines += ["", "## Проверки ядра на кандидате", ""]
    if now["error"]:
        lines.append(f"**Проверки не посчитаны:** {now['error']}")
    else:
        lines.append("Инварианты: " + ("выполнены все." if not now["invariants"] else "НАРУШЕНЫ — " + "; ".join(
            f"`{name}`: {message}" for name, message in now["invariants"])))
        names = list(dict.fromkeys(list(was["gates"]) + list(now["gates"])))
        if names:
            lines += ["", "| гейт | книга на оценке | кандидат | сообщение на кандидате |", "|---|---|---|---|"]
            lines += [f"| `{n}` | {_mass(was['gates'].get(n))} | {_mass(now['gates'].get(n))} | "
                      f"{now['gates'][n][1] if n in now['gates'] else 'не сработал'} |" for n in names]
        if now.get("flags"):
            lines += ["", "Флаги ядра на кандидате: " + "; ".join(f"`{n}` — {m}" for n, m in now["flags"].items())]
        lines += target_lines(was, now, "книга на оценке")
    if result.get("facts_check") is not None:
        lines += ["", "## Сверка фактов кандидата с пересобранными фактами", ""]
        if result["facts_check"]:
            lines += ["| поле | кандидат | пересобранные факты |", "|---|---|---|"]
            lines += [f"| `{k}` | {_fmt(x)} | {_fmt(y)} |" for k, x, y in result["facts_check"]]
        else:
            lines.append("Расхождений нет: ядро читает из обоих наборов одно и то же состояние якоря.")
    lines += ["", "## Предупреждения и ручные шаги", ""] + [f"- {w}" for w in cand.warnings] + [""]
    return "\n".join(lines)


def write_form_candidate(out: Path, book: Book, result: Mapping, template: Path | None = None) -> None:
    """Кандидат книги и фактов после замены оценки фактом формы и REANCHOR.md о замене — в каталог `out`."""
    check_out(out)
    cand: Reanchored = result["candidate"]
    text = yaml.safe_dump(cand.data, allow_unicode=True, sort_keys=False, width=100000)
    if _plain(yaml.safe_load(text)) != _plain(cand.data):
        raise ReportError("кандидат не переживает YAML туда-обратно — отказ записи")
    patched = None
    if template is not None and Path(template).exists():
        try:
            patched = patch_template(Path(template).read_text(encoding="utf-8"), cand)
        except (ReportError, yaml.YAMLError, StopIteration) as exc:
            cand.warnings.append(f"шаблон книги не записан: {exc or 'узел шаблона не найден'}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts").mkdir(exist_ok=True)
    _write(out / "assumptions.yaml", text)
    _write(out / "assumptions.json", _json(cand.data))
    if patched is not None:
        _write(out / "assumptions_template.yaml", patched)
    for name, content in cand.facts.files.items():
        _write(out / "facts" / f"{name}.json", _json(content))
    _write(out / "REANCHOR.md", form_text(book, result))


# ------------------------------------------------------------------ запись и запуск


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def check_out(out: Path) -> None:
    """Внутри репозитория инструмент пишет только под `var/`: кандидат — не канон, а всё остальное
    дерево рабочей копии либо канон (`data/`, `model/`, `docs/`), либо уходит в git, CI и на
    витрину (`tests/`, `ops/`, `web/`…). Вне репозитория — без ограничений."""
    if _inside(out, ROOT) and not _inside(out, ROOT / WRITABLE):
        where = out.resolve().relative_to(ROOT.resolve()).parts
        raise ReportError(
            f"запись в {out} — внутри репозитория вне {WRITABLE}/ ({where[0] + '/' if where else 'корень'}): "
            "кандидата в канон переносят владельцы книги и фактов (docs/REANCHOR.md), инструмент туда не "
            f"пишет; каталог кандидата — под {WRITABLE}/ или вне рабочей копии")


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")


def _json(tree: Any) -> str:
    return json.dumps(tree, ensure_ascii=False, indent=1) + "\n"


def write_candidate(out: Path, book: Book, result: Mapping, template: Path | None = None) -> None:
    """Кандидат книги и фактов, ожидаемый отчёт и REANCHOR.md — в каталог `out`. В режиме `resolve`
    (диагностика) — только ожидаемый отчёт и REANCHOR.md: такого кандидата в канон не переносят."""
    check_out(out)
    cand: Reanchored = result["candidate"]
    if result["transmission"] == RESOLVE:
        out.mkdir(parents=True, exist_ok=True)
        _write(out / "expected.json", _json(result["expected"]))
        _write(out / "REANCHOR.md", report_text(book, result))
        return
    text = yaml.safe_dump(cand.data, allow_unicode=True, sort_keys=False, width=100000)
    if _plain(yaml.safe_load(text)) != _plain(cand.data):
        raise ReportError("кандидат не переживает YAML туда-обратно — отказ записи")
    patched = None
    if template is not None and Path(template).exists():
        try:
            patched = patch_template(Path(template).read_text(encoding="utf-8"), cand)
        except (ReportError, yaml.YAMLError, StopIteration) as exc:
            cand.warnings.append(f"шаблон книги не записан: {exc or 'узел шаблона не найден'}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts").mkdir(exist_ok=True)
    _write(out / "assumptions.yaml", text)
    _write(out / "assumptions.json", _json(cand.data))
    if patched is not None:
        _write(out / "assumptions_template.yaml", patched)
    for name, content in cand.facts.files.items():
        _write(out / "facts" / f"{name}.json", _json(content))
    _write(out / "expected.json", _json(result["expected"]))
    _write(out / "REANCHOR.md", report_text(book, result))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", type=Path, default=BOOK_PATH, help="машинная книга (по умолчанию — канон)")
    ap.add_argument("--facts-dir", type=Path, default=FACTS_DIR, help="факты прежнего якоря")
    ap.add_argument("--template", type=Path, default=TEMPLATE, help="шаблон книги для кандидата шаблона")
    ap.add_argument("--expected", type=Path, metavar="ФАЙЛ",
                    help="записать ожидаемый отчёт закрываемого квартала и выйти")
    ap.add_argument("--facts", type=Path, metavar="ФАЙЛ", help="файл отчёта квартала")
    ap.add_argument("--out", type=Path, help="каталог кандидата (по умолчанию var/reanchor/<квартал>/)")
    ap.add_argument("--valuation-date", help="дата оценки разложения и кандидата")
    ap.add_argument("--version", help="версия кандидата (по умолчанию «<версия>+<квартал>»)")
    ap.add_argument("--band", type=int, metavar="ПРОГОНОВ",
                    help="разложение печатаемой медианы на ПРОГОНОВ прогонах каждой из четырёх книг")
    ap.add_argument("--no-cells", action="store_true",
                    help="не считать строку «механика» по клеткам (быстрее; допуск механики не проверяется)")
    ap.add_argument("--transmission", choices=TRANSMISSION_MODES, default=KEEP,
                    help="keep (по умолчанию, режим процедуры) — скаляры пути σ0_A, σ0_L, φ_A, φ_L прежней книги, "
                         "цели A-N2, A-N3 и обе доли пересчитываются на структуру нового якоря; resolve — только "
                         "диагностика: цели прежние, скаляры решаются заново, кандидат не пишется")
    ap.add_argument("--compare-facts", type=Path, metavar="КАТАЛОГ",
                    help="сверить факты кандидата с пересобранными фактами нового якоря")
    ap.add_argument("--capital-form", type=Path, metavar="ФАЙЛ",
                    help="замена оценки нормативов якоря фактом формы БЕЗ смены якоря: файл capital-form/1 с нормативами "
                         "и капиталом группы на дату якоря; кандидат книги и фактов и REANCHOR.md о замене — в --out")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        facts = load_facts(args.facts_dir)
        book = load_book(args.book, facts=facts)
        if args.expected:
            check_out(args.expected)
            report = expected_report(book, facts)
            args.expected.parent.mkdir(parents=True, exist_ok=True)
            _write(args.expected, _json(report))
            print(f"ожидаемый отчёт за {report['period']} → {args.expected}")
            return 0
        if args.capital_form:
            form = read_form(args.capital_form)
            out = args.out or DEFAULT_OUT / f"{form.get('period', 'anchor')}-form"
            check_out(out)
            result = replace_capital(book, facts, form, valuation_date=args.valuation_date, version=args.version)
            if args.band:
                vdate, cand = result["valuation_date"], result["candidate"]
                result["band_draws"] = args.band
                result["band"] = (band_stats(book, facts, live_at(book, facts, vdate), args.band),
                                  band_stats(cand.book, cand.facts, live_at(cand.book, cand.facts, vdate), args.band))
            if args.compare_facts:
                result["facts_check"] = compare_facts(book, result["candidate"].facts, load_facts(args.compare_facts))
            write_form_candidate(out, book, result, args.template)
            print(form_text(book, result))
            return 0
        if not args.facts:
            ap.error("нужен --facts ФАЙЛ (или --expected ФАЙЛ, или --capital-form ФАЙЛ)")
        report = read_report(args.facts)
        out = args.out or DEFAULT_OUT / str(report.get("period", "report"))
        check_out(out)
        marked = None
        if args.template is not None and Path(args.template).exists():
            try:
                marked = derived_on_core(Path(args.template).read_text(encoding="utf-8"))
            except yaml.YAMLError:
                marked = None                # шаблон не читается: перечень — общими словами, о шаблоне скажет запись
        result = attribution(book, facts, report, valuation_date=args.valuation_date, version=args.version,
                             band_draws=args.band, cells=not args.no_cells, transmission=args.transmission,
                             marked=marked)
        if args.compare_facts:
            result["facts_check"] = compare_facts(book, result["candidate"].facts, load_facts(args.compare_facts))
        write_candidate(out, book, result, args.template)
    except (ReportError, BookError, FactsError) as exc:
        print(f"reanchor: {exc}", file=sys.stderr)
        return 1
    print(report_text(book, result))
    mech = result.get("mechanics")
    if mech and not mech["ok"]:
        print(f"reanchor: механика вне допуска ({mech['worst']['cell']}: {mech['worst']['rel']:+.4%}) — "
              + (f"диагностика режима resolve, в {out} — только REANCHOR.md" if args.transmission == RESOLVE
                 else f"кандидат в {out} только для разбора"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
