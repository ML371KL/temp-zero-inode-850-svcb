"""Выпуск: сборка (`make_release` → `build_payload`) и контракт (`validate`) — docs/PAYLOAD.md.

Имя схемы выпуска — ключ книги `meta.schema` (`schema_name`), подписи эмитента — `meta.labels`,
`nii.books.<b>.name`, `checks.guidance_items` (М§0.6): в модуле нет ни имени схемы, ни названий
нормативов, органа решения о дивиденде и терминов эмитента.
Контракт — PAYLOAD («П§N») и константы этого модуля: `REQUIRED_TOP_LEVEL` (28 блоков П§1),
`REQUIRED_FIELDS` (поля П§2; «?» — необязательные), `FORBIDDEN_FIELDS` (П§6), `PRECISION` (П§0.3),
`HASH_EXCLUDED` (П§0.4), `HYGIENE_RULES` (П§7 п. 3), `UNIT_CODES` и `BASIS_CODES` (П§0.2), `CODE_DIRS`
(каталоги кода выпуска = `CODE_DIRS` ops/run.sh). Строки, которые печатает витрина, — словами для владельца:
без имён полей, `inf`, кортежей, e-нотации, путей к файлам и рабочих пометок, доли — в процентах, разности
долей — в п.п., даты — с годом (П§0.2). Три исхода сборки (М§14.2–§14.3): отказ — нарушенный инвариант или
сработавший гейт без действующего объяснения; тревога (`alerts`, код 3) — деградация живых входов, флаг
`dividend_register`, тяжёлый выпуск; плашка (флаги `explanation_expiring`, `policy_expired`) — код 0.
Норматив смеси — в определении движка
(`_Ctx.ratio`: E[K]/E[RWA] + ожидание аддитивного слагаемого клеток, П§2 `capital`). Методика чисел — MODEL; фронт ничего не
считает, кроме λ (П§0.1): всё, что зависит от λ, — таблицы `by_lambda` на сетке 0; 0,05; …; 1.

Порядок сборки (INTERFACES §6): факты и книга → выходы индикаторов (без `--book-only`) → живые
входы → сетка и полоса → диагностики (без `--fast`) → проверки → прошлый выпуск и история из
клона репозитория данных → выпуск → `validate`. Инварианты уровня выпуска (`release_numbers`,
`jump_guard`, `payload_contract`, `exdate_jump`) проверяются здесь тем же типом `Finding`.

Вторая форма банка (М§8.4, §5.2, §3.3): всё «на акцию» делится на делитель прогона `GridRun.divisor`
(деньги дивиденда — на акции в обращении); блок дивидендов несёт проверку вида `dividends.policy.history_test`
(`formula_check` — только при `exact`, `cap_check` — при `cap`); нормативы якоря, стоящие оценкой, — поле
`capital.anchor.estimated` и флаг `capital_estimated`. Новые узлы выпуска необязательны: без своих ключей
книги и узлов фактов их нет.

Квартальный календарь дивидендов (М§5.7; П§2 `dividends`): ключ записи реестра, строки истории, экс-даты и
строки моста — квартал прибыли (`period`), год прибыли остаётся в каждой записи. `dividends.model[]` — по годам
прибыли (сумма кварталов), квартальный путь — `dividends.model_quarters[]`; ближайшая выплата ищется по периоду
и несёт доходность одной квартальной выплаты; форвардная доходность — сумма четырёх ближайших кварталов; ступень
лестницы без порога норматива не печатается. При годовом календаре блок собирается прежним кодом.

Рост, ограниченный капиталом (М§4.13; П§2 `capital`): у книги с включённым правилом — `capital.requirement`
(нормативы смеси против требования с глиссадой, Н20.1 с прибылью периода) и `capital.growth` (потенциальный и
фактический рост кредитных книг, доля урезанного, λ по кварталам); `capital.rule_price` — «цена правила» из
таблиц книги (`results.json`; сборка её не пересчитывает). `paths.fade` — путь ROE и роста капитала к терминалу
(у любой книги); `history.three_profits` — мост «вся прибыль → акционерам → операционная» при узлах фактов;
`rub_per_1pp_buffer` — при ключе чувствительности к запасу капитала. Длины массивов узлов и тождество моста
сверяет контракт (П§7 п. 15).

Гейты знака и цель маржи (М§14.2; П§2): числа гейтов `volume_sign` и `stress_sign` считаются один раз на
центральной книге (`model.checks.sign_numbers`) и стоят узлами `checks.volume_sign`, `checks.stress_sign`;
печатаемая маржа модальной клетки после фазы роста — `nii.transmission.nim_lt_printed` рядом с ключом цели и
поля `printed_book`, `printed_solved` строки обратного расчёта по этому ключу. Словарь терминов `meta.terms`
собирается из всех ключей `meta.labels.terms` книги; сумма дивиденда несёт код базы (`amount_basis`:
размещённые акции у реестра и рядов модели, акции в обращении у моста) при подписях базы в книге; дивидендная
доходность за 12 месяцев при квартальном календаре — сумма четырёх последних объявленных кварталов прибыли;
узел требования к капиталу называет, какой норматив сравнивает правило роста (`compare`), и подписывает
отчётный норматив справочным (`notes`). Все эти узлы необязательны: без своих ключей книги их нет.

На чём стоит заголовок (М§14.5; П§2): годовой путь смеси считает одна функция `model.levels.mix_year` — она же у
узла уровней после фазы роста `paths.levels` (ключ `checks.window_backtest`: модальная клетка, слой «свой
взгляд», смесь заголовка, слой «рыночные ставки как есть») и узла `paths.modal_cell` (ключ `checks.point_path`:
вес и цена модальной клетки, её прибыль по годам); стационарная маржа мира-цели — `nii.transmission.nim_stationary`
(ключ `checks.nim_stationary`), у строки обратного расчёта по ключу цели ЧПМ — она же на книге и при корне с
уровнями при корне; стоимость средств клиентов к ключевой ставке по мирам — `checks.funds_cost_to_key`. Справочные
варианты `book.reference_variants` — из таблиц книги (`results.json`): сборка выпуска их не пересчитывает. Запас
якоря до требования с глиссадой — поля `capital.anchor` при правиле роста. Месячная таблица операционных
результатов `nowcast.ops` — при рядах слоя индикаторов; частичные провалы раскрытия `history.gaps` — при узле
фактов; источник строки — названием документа. Узлы необязательны: без ключей книги и узлов фактов их нет.

Суждение об уровне маржи (М§4.5; П§2): у книги с ключом `nii.transmission.level_world` ключ цели ЧПМ — стационарная
маржа названного мира; узел `nii.transmission.level` несёт мир, эту маржу и выведенный решателем уровень
мира-опоры, а строка обратного расчёта по ключу цели — ту же маржу на книге и при корне. Окно фактов —
подузел `paths.levels.window` (поля окна в ключе `checks.window_backtest`). Справочные варианты выпуск берёт из
таблиц книги только при том же отпечатке книги и печатает по убыванию модуля цены правила, с подписью строки из
книги; несовпадение — узла нет и замечание сборки (`Release.remarks`). Список строк обратного расчёта с уточнением
на полной полосе — `reverse_dcf.refine_rows` (ключ книги), признак оценки по подвыборке — `gap_basis` строки.
Выпуск, собранный без слоя индикаторов, называет это узлом `nowcast.absent` (подпись книги). Сводка сверки с
контрольной моделью несёт число сверенных строк, число строк вне допуска, версию книги и дату, на которой стоят
её числа, — как их записал писатель сводки.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from model.book import ROOT, Book, Facts, load_book, load_facts, record_fields, record_label
from model.book_schema import BASIS_CODES, UNIT_CODES, UNIT_WORDS, BookError, FactsError
from model.cell import LAM_TOL
from model.checks import (GUIDANCE_GROWTH, Finding, GateStatus, check_gates, check_invariants, cir_word,
                          gate_statuses, grouped, guidance_band, guidance_bases, guidance_values, inside,
                          load_gate_explanations, pct, sign_numbers)
from model.dividends import (DECLARED, HISTORY_CAP, HISTORY_EXACT, HISTORY_NONE, cap_history, dps_history,
                             history_dps, history_test, record_key)
from model.grid import (NIM_LT, SHARES_ISSUED, DividendRecord, GridRun, LiveInputs, bank_language, cell_probabilities,
                        market_cap, modal_cell, printed_nim_lt, realized_cells, run_grid, sensitivity_overrides,
                        unregistered_dividend, world_layer)
from model.credit import kappa_world
from model.levels import (FUNDING_METRICS, LEVEL_METRICS, MARKET_LAYER, NIM_STATIONARY, POINT_PATH, client_funds_end,
                          expect, funding_path, funds_cost_to_key, level_nim, levels, mix_year, quarter_end,
                          stationary_nim, year_flow)
from model.nii import level_world
from model.live import LiveReport, apply_live, read_last_accepted, state_dir
from model.paths import Trajectory, get_path
from model.timeline import (DAYS_IN_YEAR, parse_period, period_str, period_words, quarter_days, shift_quarter,
                            to_date)
from model import uncertainty as U

__all__ = ["schema_name", "REQUIRED_TOP_LEVEL", "REQUIRED_FIELDS", "FORBIDDEN_FIELDS", "PRECISION", "LAMBDA_STEPS",
           "QUARTERS_SHOWN", "HISTORY_ROWS", "MAX_BYTES", "WARN_BYTES", "HASH_EXCLUDED", "HYGIENE_RULES",
           "Release", "make_release", "build_payload", "validate", "payload_hash", "compact_bytes",
           "engine_commit", "INVARIANT_TITLES", "GATE_TITLES", "FLAG_TITLES", "FLAG_LABELS", "gate_title", "flag_title",
           "FORM_GATE_TITLES", "RAISED_FLAG_TITLES", "invariant_title", "hygiene_problems",
           "release_findings", "data_repo_dir", "CODE_DIRS", "UNIT_CODES", "BASIS_CODES", "alerts"]

LAMBDA_STEPS = 20
QUARTERS_SHOWN = 14
HISTORY_ROWS = 400
MAX_BYTES = 500_000
WARN_BYTES = 450_000
PRICE_HISTORY_POINTS = 130
DATA_REPO_ENV = "BANK_DATA_REPO_DIR"
# Каталоги кода выпуска (INTERFACES §4.6): сменились с опубликованного выпуска — пересборка (ops/run.sh,
# без *.md); web/, functions/, docs/ в выпуск не входят.
CODE_DIRS: tuple[str, ...] = ("model", "indicators", "ops", "data/assumptions", "data/facts", "data/indicators",
                              "data/checks", "requirements.txt")
RELEASE_NOTES = ROOT / "data" / "assumptions" / "release_notes.yaml"
CONTROL_MODEL = ROOT / "data" / "checks" / "control_model.json"
NOTE_TOLERANCE_MAX = 25          # допуск записки к скачку — не больше 25 % (М§14.4)
PP01 = 0.001                     # 0,1 п.п.
PP1 = 10 * PP01                  # 1 п.п. — единица чувствительности к запасу капитала (М§8.3)
RESULTS = ROOT / "data" / "assumptions" / "results.json"      # таблицы книги: «цена правила» (М§14.5)
HEX40 = re.compile(r"[0-9a-f]{40}")
EPS = 1e-9                       # сравнение λ, нулевой DPS, хранение дерева ROE
TAILS = (0.1, 0.9)               # P10–P90 по клеткам (П§2 capital.by_scenario, dividends.model)
TOL_POINT = 0.011                # тождества точки на хранимых ценах (две по 0,005 + запас)
TOL_FORMULA = 0.02               # цена смеси по формуле М§8.2 на хранимых V0 и мосте
TOL_RATIO = 0.0005               # норматив смеси против ожидания клеток и мост против факта якоря: 0,05 п.п. (П§7 п. 10)

NAMED_LITERALS = {
    0.001: "PP01: 0,1 п.п. — единица чувствительностей «₽ за 0,1 п.п.» (М§8.3)",
    0.005: "допуск validate: квантили и среднее заголовка из прогонов — до 0,005 ₽ (П§7 п. 5)",
    0.05: "допуск validate: деньги 0,05 млрд ₽ (П§0.3); шаг сетки λ 1/20",
    1e-05: "допуск validate: вероятности 1e-5 (П§0.3), дерево ROE 1e-5 (П§7 п. 11)",
    1e-06: "точность долей и вероятностей 1e-6 (П§0.3)",
    0.0001: "точность мультипликаторов 1e-4 (П§0.3)",
    0.01: "точность цен 0,01 ₽ и денег 0,01 млрд ₽ (П§0.3)",
    0.1: "точность прогонов полосы 0,1 ₽ и годовых денег клеток (П§0.3)",
    0.5: "DPS < 0,5 × цены (П§7 п. 9)",
    500000: "MAX_BYTES: потолок выпуска (П§0.4)",
    10.0: "BN_FROM: строка без единицы со значением от 10 — млрд ₽ (код единицы витрины)",
    1e-09: "EPS: сравнение λ и нулевого DPS, хранение дерева ROE",
    0.9: "TAILS: верхний хвост P90 по клеткам (П§2)",
    0.011: "TOL_POINT: тождества точки на хранимых ценах",
    0.02: "TOL_FORMULA: цена смеси по формуле М§8.2 на хранимых числах",
    0.0005: "TOL_RATIO: норматив смеси и старт моста норматива — до 0,05 п.п. (П§7 п. 10)",
    450000: "WARN_BYTES: предупреждение о размере (П§0.4)",
}

REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "schema", "meta", "market", "fair_value", "layers", "grid", "variance", "worlds", "regimes", "capital",
    "dividends", "paths", "nii", "guidance", "governance", "reverse_dcf", "judgements", "next_report",
    "nowcast", "indicators", "calendar", "history", "checks", "inputs", "live", "changes",
    "valuation_history", "book",
)

_F = lambda s: tuple(s.split())  # noqa: E731
# Поля блоков и вложенных узлов П§2 (запись П§2 вступление; «?» — необязательные): «a.b» — объект,
# «a.b[]» — каждый элемент списка, «a.b.*» — каждое значение словаря. Полноту по тексту П§2 (и §4 для
# valuation_history) сверяет tests/test_core2_payload_doc.py — узлы и поля в обе стороны.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "meta": _F("generated_at published_at? valuation_date facts_date book_version book_date book_tag "
               "engine_commit fast payload_sha256 previous_sha256 bytes company shares period_unit input_unit "
               "anchor_period first_period last_period horizon open_period periods_closed elapsed "
               "book_first_period_closed curve_as_of basis step day_count governance_discount basis_labels? terms?"),
    "meta.company": _F("name tickers main_ticker share_classes cbr_regnum fiscal_year_end"),
    "meta.company.share_classes[]": _F("ticker class"),
    "meta.shares": _F("issued_mln outstanding_mln by_ticker as_of src divisor_mln? divisor_basis? divisor_label? "
                      "depositary_block_mln? economic_treasury_mln? dividend_eligible_mln? corporate_actions?"),
    "meta.shares.by_ticker.*": _F("issued_mln treasury_mln outstanding_mln"),
    "meta.shares.corporate_actions[]": _F("date kind title factor?"),
    "meta.basis_labels": _F("profit roe divisor dividend_issued? dividend_outstanding?"),
    "meta.terms": _F("lt_level profit_short noncore cir? roe_lt? stake?"),
    "market": _F("price price_date prices cap cap_by_ticker multiples price_history price_min price_max "
                 "ex_dividend peers brokers"),
    "market.prices.*": _F("price date time source status book_price"),
    "market.multiples": _F("pb pb_reported pe_ltm pe_fwd dividend_yield_ltm dividend_yield_fwd bv_per_share basis"),
    "market.price_history.*[]": _F("date close"),
    "market.price_min.*": _F("date close"),
    "market.price_max.*": _F("date close"),
    "market.ex_dividend[]": _F("date dps year period? label?"),
    "market.peers": _F("as_of basis subject_ticker rows"),
    "market.peers.rows[]": _F("ticker name price price_date cap bv bv_date ni_ltm pb pe roe_ltm dividend_yield "
                              "capital_ratio basis src status reason"),
    "market.peers.rows[].capital_ratio": _F("name value as_of"),
    "market.brokers": _F("as_of source n median min max recommendations history?"),
    "market.brokers.recommendations": _F("buy hold sell"),
    "market.brokers.history[]": _F("date median n"),
    "fair_value": _F("method target headline low central high printed_low printed_central printed_high "
                     "own_macro_confidence rates_view bank_first_line bridge by_world jump_guard"),
    "fair_value.headline": _F("median printed_median band80 printed_band80 band50 printed_band50 mean point "
                              "printed_point market market_by_ticker p_below_market p_below_by_ticker "
                              "market_percentile upside draws seed quantiles own_macro_confidence lambda_step "
                              "print_step ceiling_x_market low_draws high_draws contributions by_lambda "
                              "draw_step?"),
    "fair_value.headline.contributions[]": _F("axis name share rank_corr paths judgement_key"),
    "fair_value.headline.by_lambda[]": _F("lambda median p10 p25 p75 p90 mean point p_below_market "
                                          "p_below_by_ticker market_percentile upside"),
    "fair_value.rates_view": _F("low high rub"),
    "fair_value.bank_first_line": _F("target bv_v v_point v_median fair_pb_point fair_pb_median market_pb "
                                     "excess_point excess_median excess_market roe_tc k_tc roe_ltm "
                                     "rub_per_1pp_roe rub_per_01pp_cor rub_per_01pp_nim sensitivity_basis layers "
                                     "by_lambda rub_per_1pp_buffer?"),
    "fair_value.bank_first_line.layers": _F("analytical macro_neutral"),
    "fair_value.bank_first_line.layers.analytical": _F("bv_v v0 fair_pb excess roe_tc k_tc"),
    "fair_value.bank_first_line.layers.macro_neutral": _F("bv_v v0 fair_pb excess roe_tc k_tc"),
    "fair_value.bank_first_line.by_lambda[]": _F("lambda bv_v v_point v_median fair_pb_point fair_pb_median "
                                                 "market_pb excess_point excess_median excess_market roe_tc k_tc "
                                                 "rub_per_1pp_roe rub_per_01pp_cor rub_per_01pp_nim "
                                                 "rub_per_1pp_buffer?"),
    "fair_value.bridge": _F("amount per_share governance_applies pending_dividend rows amount_basis?"),
    "fair_value.bridge.rows[]": _F("year dps amount deducted_on last_buy_date ex_date sign period? label?"),
    "fair_value.by_world.*": _F("price v0 bv_v pb"),
    "fair_value.jump_guard": _F("previous_median exdate_adjustment median_change median_limit v0_agm_adjustment "
                                "v0_change unregistered_dividend unregistered_dps v0_limit reason note_valid_until?"),
    "layers": _F("analytical market_implied macro_neutral headline_mix"),
    "layers.analytical": _F("title world_weights v0 bv_v price pb excess pv_ri_explicit pv_terminal "
                            "terminal_share roe_tc k_tc p_price_below_market p_roe_below_k capital_gap_mass "
                            "buyback_effect?"),
    "layers.market_implied": _F("title world_weights v0 bv_v price pb excess pv_ri_explicit pv_terminal "
                                "terminal_share roe_tc k_tc p_price_below_market p_roe_below_k capital_gap_mass "
                                "buyback_effect?"),
    "layers.macro_neutral": _F("title world_weights v0 bv_v price pb excess pv_ri_explicit pv_terminal "
                               "terminal_share roe_tc k_tc p_price_below_market p_roe_below_k capital_gap_mass "
                               "buyback_effect?"),
    "layers.headline_mix": _F("title lambda v0 bv_v pv_ri_explicit pv_terminal governance bridge price waterfall "
                              "buyback_effect?"),
    "layers.headline_mix.waterfall[]": _F("key title amount per_share total"),
    "grid": _F("world_order regime_order scenario_order years basis cells"),
    "grid.cells[]": _F("world regime scenario p_analytical p_market_implied p_neutral v bv_v price pb "
                       "pv_ri_explicit terminal_share roe_t k_t g_t x_t n20_min n11_min gap_period dps_first "
                       "flags annual terminal_fixed? terminal_stationary? terminal_year? terminal_fade?"),
    "grid.cells[].annual": _F("ni_sh roe cor nim cir n20 n11 dps payout buyback?"),
    "grid.cells[].terminal_fixed": _F("lam_f parts f_a r_f kappa binding f_k d_f y_m i_f m_l business_capital x_b "
                                      "phi bound_after_payout? wt_after? min_liquidity?"),
    "grid.cells[].terminal_stationary": _F("d_nii_l y_bal c_wh y_bal_lagged c_wh_lagged"),
    "grid.cells[].terminal_year": _F("days_l nu_l psi day_weighted_l adj"),
    "grid.cells[].terminal_fade": _F("s n phi"),
    "variance": _F("price method"),
    "variance.price": _F("world regime scenario interaction"),
    "worlds": _F("order rows source overlay"),
    "worlds.rows.*": _F("name weights key_rate cpi real_key ofz zero_curve lt_inflation k_t g_t price v0 "
                        "credit_growth funds_growth transmission"),
    "worlds.rows.*.weights": _F("analytical market_implied macro_neutral"),
    "worlds.rows.*.credit_growth": _F("corporate mortgage retail_other"),
    "worlds.rows.*.funds_growth": _F("retail corporate"),
    "worlds.source": _F("record origin record_asof curve_date sha256"),
    "worlds.overlay": _F("file sha256"),
    "regimes": _F("order basis cor_basis cor_bridge rows near_nim_shift expected update history reference_class? "
                  "reference_world?"),
    "regimes.cor_bridge": _F("method value"),
    "regimes.rows.*": _F("title prior posterior cor cor_engine cor_lt cor_lt_engine nim_shift nim_shift_lt "
                         "loan_growth_adj crisis?"),
    "regimes.rows.*.cor[]": _F("year value"),
    "regimes.rows.*.cor_engine[]": _F("year value"),
    "regimes.rows.*.nim_shift[]": _F("year value"),
    "regimes.rows.*.loan_growth_adj[]": _F("year value"),
    "regimes.rows.*.crisis": _F("shock_year shock_year_offset one_off_loss loan_growth_override cor_quarters"),
    "regimes.rows.*.crisis.one_off_loss": _F("period amount"),
    "regimes.rows.*.crisis.loan_growth_override[]": _F("year value"),
    "regimes.rows.*.crisis.cor_quarters[]": _F("period value"),
    "regimes.near_nim_shift[]": _F("period value"),
    "regimes.expected": _F("cor_lt cor_lt_engine nim_shift_lt"),
    "regimes.update": _F("cor nim max_shift_pp window_obs floor_share observations"),
    "regimes.update.cor": _F("sigma_pp rho_q"),
    "regimes.update.nim": _F("sigma_pp rho_q"),
    "regimes.update.observations[]": _F("period basis cor nim se_cor se_nim cor_engine nim_engine posterior_after"),
    "regimes.history[]": _F("period cor_mgmt cor_engine nim_mgmt nim_engine"),
    "regimes.reference_class": _F("episodes shares"),
    "regimes.reference_class.episodes[]": _F("id name period cor_peak quarters nim_drop src"),
    "regimes.reference_class.shares[]": _F("regime book class lo hi"),
    "capital": _F("titles anchor observed? policy_threshold minimum mgmt_buffer years scenarios by_scenario mix "
                  "mix_tolerance? capital_gap bridge requirement? growth? rule_price?"),
    "capital.titles": _F("n20 n11 n11_observed n1_0 n1_2"),
    "capital.anchor": _F("as_of n20 n20_pre_dividend n20_post_dividend n11_bank n10_bank? rwa bv_common at1 t2 "
                         "fvoci_reserve ded20 ded11 req20_now req11_now n20_headroom n11_headroom? basis src estimated? "
                         "req20_glide_next? req20_glide_period? n20_headroom_glide?"),
    "capital.anchor.n11_bank": _F("value as_of"),
    "capital.anchor.n10_bank": _F("value as_of"),
    "capital.observed": _F("n1_0 n1_1 n1_2 as_of source"),
    "capital.minimum": _F("n20_0 n1_1"),
    "capital.mgmt_buffer": _F("n20_0 n1_1"),
    "capital.scenarios.*": _F("title p_given_regime mass conservation sifi ccyb deduction_n20 deduction_n11 "
                              "floor20 floor11 req20 req11"),
    "capital.by_scenario.*": _F("n20 n20_p10 n20_p90 n11 n11_p10 n11_p90"),
    "capital.mix": _F("n20 n11 req20 req11 floor20 floor11"),
    "capital.capital_gap": _F("mass cells cell_list first_period by_scenario"),
    "capital.bridge": _F("from to start end rows"),
    "capital.bridge.rows[]": _F("key title pp amount"),
    "capital.requirement": _F("periods mix by_scenario years_mix lookahead_quarters glide_pp_per_quarter compare? "
                              "notes?"),
    "capital.requirement.mix": _F("n20 n11 n11_star req20_glide req11_glide req20 req11"),
    "capital.requirement.by_scenario.*": _F("req20_glide req11_glide"),
    "capital.requirement.years_mix": _F("req20_glide req11_glide n11_star?"),
    "capital.requirement.compare": _F("n20 n11"),
    "capital.requirement.notes": _F("n11_star n11"),
    "capital.growth": _F("years potential actual cut_share catch_up lam_min p_cut by_scenario quarters order "
                         "min_growth_scale catch_up_rate"),
    "capital.growth.by_scenario.*": _F("actual cut_share"),
    "capital.growth.quarters": _F("periods lam"),
    "capital.rule_price": _F("rows"),
    "capital.rule_price.rows[]": _F("key title point median? d_point? d_median? capital_gap_mass current why? median_mark? mark?"),
    "dividends": _F("policy ladder register history formula_check model next_expected yield_ltm basis cap_check? "
                    "model_quarters? amount_basis? yield_ltm_periods? buyback? token?"),
    "dividends.buyback": _F("title price_rule price_book closed first_period last_period shares_start_mln amount "
                            "shares_bought_mln price divisor_after_mln years by_world"),
    "dividends.buyback.closed[]": _F("period price"),
    "dividends.buyback.years[]": _F("year amount price shares_bought_mln shares_end_mln"),
    "dividends.buyback.by_world.*": _F("price divisor_after_mln"),
    "dividends.token": _F("min_dps years"),
    "dividends.token.years[]": _F("year min_dps p_token dps"),
    "dividends.policy": _F("name text doc sha256 approved valid_until valid_until_note? base payout metric "
                           "threshold steps shortfall_rule deduct_at1_after_tax divisor excess crisis history_test? "
                           "cap? frequency? base_window_quarters? decision_lag_quarters?"),
    "dividends.policy.payout[]": _F("year value"),
    "dividends.policy.steps[]": _F("payout threshold"),
    "dividends.policy.excess": _F("from_profit_year epsilon ramp_years"),
    "dividends.policy.crisis": _F("skip_in_shock_year catch_up"),
    "dividends.ladder[]": _F("key title condition payout current"),
    "dividends.register[]": _F("year dps amount record_date last_buy_date ex_date pay_date status in_bridge "
                               "sources period? label? decided_date?"),
    "dividends.history[]": _F("year dps dps_preferred pool payout_ratio record_date ex_date pay_date "
                              "ni_shareholders src period? label? dps_pre_split? split_factor?"),
    "dividends.cap_check[]": _F("year pool ni_shareholders share cap complete ok"),
    "dividends.model_quarters[]": _F("period decision_period pay_period dps dps_p10 dps_p90 dps_policy amount p_cut "
                                     "p_zero declared"),
    "dividends.formula_check[]": _F("year ni_shareholders at1_coupon tax_statutory base pool dps_exact "
                                    "dps_rounded dps_declared rounding ok"),
    "dividends.model[]": _F("year pay_year dps dps_p10 dps_p90 dps_policy payout amount p_cut p_zero declared"),
    "dividends.next_expected": _F("year status dps dps_policy dps_mean dps_p10 dps_p90 p_cancel record_date "
                                  "record_date_est record_date_note last_buy_date? pay_date_est yield condition "
                                  "period? label? yield_period?"),
    "dividends.next_expected.condition": _F("metric threshold n20_expected p_limited"),
    "paths": _F("mix annual quarters roe_tree terminal fade? levels? modal_cell? funding?"),
    "paths.funding": _F("years cell anchor mix modal_cell"),
    "paths.funding.anchor": _F("loans_to_funds wholesale_share"),
    "paths.funding.mix": _F("loans_to_funds wholesale_share"),
    "paths.funding.modal_cell": _F("loans_to_funds wholesale_share"),
    "paths.levels": _F("from_year to_year cell order rows window?"),
    "paths.levels.rows.*": _F("title nim cor cir loans_share cor_mix0?"),
    "paths.levels.window": _F("nim cor cir loans_share"),
    "paths.levels.window.nim": _F("min max mean"),
    "paths.levels.window.cor": _F("min max mean"),
    "paths.levels.window.cir": _F("min max mean"),
    "paths.levels.window.loans_share": _F("window anchor"),
    "paths.modal_cell": _F("cell p_analytical p_point price years ni_sh"),
    "paths.fade": _F("years roe bv_growth k roe_t_raw roe_t k_t g_t fade"),
    "paths.mix": _F("title lambda"),
    "paths.annual[]": _F("year fact_quarters nii nim nim_mgmt fees fees_growth insurance other noncore opex cir "
                         "cir_mgmt llp cor cor_mgmt fvc one_off pbt tax ni ni_sh oci ci roe roe_ci bv_end rwa_end n20_end "
                         "n11_end req20_end floor20_end loans_end funds_end assets_end dps payout div_paid"),
    "paths.quarters[]": _F("period fact nii nim nim_mgmt llp cor cor_mgmt fees opex ni_sh bv n20 n11 req20 "
                           "floor20"),
    "paths.roe_tree[]": _F("year nii_to_assets fees_to_assets other_to_assets noncore_to_assets opex_to_assets "
                           "llp_to_assets tax_to_assets roa leverage roe"),
    "paths.terminal": _F("roe_t k_t g_t x_t payout_t fade"),
    "nii": _F("books transmission nim_by_world current_share disclosed"),
    "nii.books[]": _F("key title side ref rho beta? phi phi_share? balancing balance_anchor rate_anchor spread_lt "
                      "spread_lt_world spread_floor rate_lt"),
    "nii.transmission": _F("target definition realized nim_lt_target_mgmt target_eng sigma0 sigma0_liab "
                           "sigma0_split phi phi_assets phi_liab phi_split loan_margin tol solved roe_equiv pairs "
                           "pairs_range by_world realized_cells nim_lt_printed? nim_stationary? level?"),
    "nii.transmission.nim_lt_printed": _F("value target tolerance from_year to_year cell"),
    "nii.transmission.nim_stationary": _F("world value target tolerance"),
    "nii.transmission.level": _F("world value reference_world reference_value"),
    "nii.transmission.pairs[]": _F("from to key_from key_to value roe_equiv inside"),
    "nii.nim_by_world": _F("years"),
    "nii.current_share": _F("c_ref psi bounds by_world"),
    "nii.disclosed": _F("nii_per_100bp src"),
    "guidance": _F("year as_of src basis items gate revisions strategy?"),
    "guidance.items[]": _F("key title basis kind guidance scope relation scope_note? fact_ytd fact_periods "
                           "model_year required_rest status mass_outside"),
    "guidance.gate": _F("name fired mass explanation valid_until"),
    "guidance.revisions[]": _F("date key value event"),
    "guidance.strategy": _F("name targets next_event?"),
    "guidance.strategy.targets[]": _F("key title target fact_last fact_period model met"),
    "guidance.strategy.targets[].model[]": _F("year value"),
    "guidance.strategy.next_event": _F("date title"),
    "governance": _F("discount components sum_signed price_at_low price_at_high"),
    "governance.components[]": _F("id name value sign basis"),
    "reverse_dcf": _F("target number method rows bank_rows refine_rows?"),
    "reverse_dcf.rows[]": _F("key name kind unit paths book range solved delta in_range status gap point_solved "
                             "point_status reason? printed_book? printed_solved? stationary_book? "
                             "stationary_solved? levels_solved? gap_basis?"),
    "reverse_dcf.rows[].levels_solved.*": _F("nim cor cir loans_share"),
    "reverse_dcf.bank_rows[]": _F("key title unit book implied delta status by_world? reason? by_year? "
                                  "market_excess?"),
    "reverse_dcf.bank_rows[].by_year[]": _F("year pv_excess_cum"),
    "judgements": _F("rows off_band_shift"),
    "judgements.rows[]": _F("id name unit kind paths book low high dist price_low price_high swing mean_shift "
                            "share rank_corr in_band source status? reason? ends?"),
    "judgements.rows[].ends": _F("book low high"),
    "judgements.off_band_shift": _F("rub limit axes"),
    "next_report": _F("period book_period target closing expectation cor_table nim_table neutral slope reaction "
                      "benchmarks status? reason?"),
    "next_report.closing": _F("date title confirmed published"),
    "next_report.expectation": _F("cor_mgmt nim_mgmt cor_engine nim_engine ni loans_ac iea tau_eff days by_regime"),
    "next_report.expectation.by_regime[]": _F("regime cor_mgmt nim_mgmt posterior"),
    "next_report.cor_table[]": _F("cor point median median_low median_high d_point d_median posterior"),
    "next_report.neutral": _F("cor nim point_cor point_nim error?"),
    "next_report.neutral.cor": _F("value gap_rub ni_equivalent middle_expectation?"),
    "next_report.neutral.nim": _F("value gap_rub ni_equivalent middle_expectation?"),
    "next_report.slope": _F("rub_per_01pp_cor rub_per_01pp_nim at_cor at_nim"),
    "next_report.reaction": _F("cor nim"),
    "next_report.reaction.cor": _F("d_median_min d_median_max"),
    "next_report.reaction.nim": _F("d_median_min d_median_max"),
    "next_report.benchmarks[]": _F("key name cor nim ni note"),
    "nowcast": _F("period_unit input_unit connected_to_price targets quarter year months form102 admission retro "
                  "journal ops? absent?"),
    "nowcast.ops": _F("note rows"),
    "nowcast.ops.rows[]": _F("month published_at clients_total clients_active loans_gross loans_retail loans_business "
                             "funds_total funds_retail funds_business ras_ni_ytd ras_ni_m f102_ni_ytd n1_0 n1_1 n1_2 "
                             "capital_total source"),
    "nowcast.targets[]": _F("key title unit basis"),
    "nowcast.quarter": _F("period months months_known by_target"),
    "nowcast.quarter.months[]": _F("month status source date_known ni nii llp"),
    "nowcast.quarter.by_target": _F("ni_q nim_q cor_q"),
    "nowcast.quarter.by_target.ni_q": _F("ras_estimate bridge ras_bridged expectation w forecast std_error "
                                         "interval deviation equation version benchmarks basis"),
    "nowcast.quarter.by_target.ni_q.benchmarks[]": _F("key name value"),
    "nowcast.quarter.by_target.nim_q": _F("ras_estimate bridge ras_bridged expectation w forecast std_error "
                                          "interval deviation equation version benchmarks basis"),
    "nowcast.quarter.by_target.nim_q.benchmarks[]": _F("key name value"),
    "nowcast.quarter.by_target.cor_q": _F("ras_estimate bridge ras_bridged expectation w forecast std_error "
                                          "interval deviation equation version benchmarks basis"),
    "nowcast.quarter.by_target.cor_q.benchmarks[]": _F("key name value"),
    "nowcast.year": _F("year ni_fact ni_quarter ni_rest ni_year ni_year_se at1_coupon_after_tax base payout dps "
                       "dps_interval dps_model capital_check yield note"),
    "nowcast.year.capital_check": _F("n20_expected requirement ok"),
    "nowcast.months": _F("basis rows"),
    "nowcast.months.rows[]": _F("month ni ni_ytd nii fees llp opex cor roe loans_corporate loans_retail "
                                "funds_retail funds_corporate n1_0 n1_1 source published_at"),
    "nowcast.form102[]": _F("month ni first_seen release_ni diff ok"),
    "nowcast.admission": _F("rule status events_needed events_scored mse_ratio first_event earliest_decision"),
    "nowcast.admission.mse_ratio": _F("nim_q cor_q"),
    "nowcast.retro": _F("periods rmse bias n main horizon titles by_horizon?"),
    "nowcast.retro.periods[]": _F("period actual benchmarks"),
    "nowcast.journal": _F("entries total_entries rule releases"),
    "nowcast.journal.entries[]": _F("id target period horizon recorded_at release_sha book_version forecast "
                                    "benchmarks actual errors"),
    "nowcast.journal.entries[].errors": _F("forecast"),
    "nowcast.journal.releases.*": _F("book_version generated_at"),
    "indicators": _F("groups tiles"),
    "indicators.groups[]": _F("id title"),
    "indicators.tiles[]": _F("id group title unit basis value date change change_from since? min max history "
                             "source note? status reason?"),
    "indicators.tiles[].history": _F("date value"),
    "calendar": _F("today next_fact next_ras events recent"),
    "calendar.next_fact": _F("id date title kind covers confirmed precision earliest? latest? days"),
    "calendar.next_ras": _F("month release_date release_confirmed form102_date_est form102_latest_est enters_via "
                            "date days"),
    "calendar.events[]": _F("id date kind title covers? confirmed precision earliest? latest? days note? "
                            "estimated? in_book?"),
    "history": _F("quarters annual ltm gaps three_profits?"),
    "history.quarters[]": _F("period ifrs mgmt n20"),
    "history.quarters[].ifrs": _F("ni ni_sh nii fees llp cor opex pbt bv roe"),
    "history.quarters[].mgmt": _F("nim cor cir roe"),
    "history.annual[]": _F("year ifrs mgmt dps payout n20_end"),
    "history.annual[].ifrs": _F("ni_sh roe bv_end"),
    "history.annual[].mgmt": _F("nim cor cir"),
    "history.ltm": _F("as_of ni_sh roe basis roe_issuer?"),
    "history.ltm.roe_issuer": _F("value as_of label"),
    "history.three_profits[]": _F("period ni_total ni_nci ni_shareholders stake_effect debt_interest_effect "
                                  "ni_operating"),
    "history.gaps[]": _F("period basis reason"),
    "checks": _F("invariants invariants_broken gates flags control_model? volume_sign? stress_sign? "
                 "funds_cost_to_key?"),
    "checks.volume_sign": _F("point point_free d_point d_world tol ok growth_constraint_off?"),
    "checks.stress_sign": _F("loss requirement mass max_excess ok mass_basis? mass_analytical?"),
    "checks.stress_sign.loss": _F("step cells after_tax? transfer_min? transfer_max?"),
    "checks.funds_cost_to_key": _F("from_year to_year max by_world ok scope?"),
    "checks.funds_cost_to_key.by_world.*": _F("cell cost key ratio modal_cell? modal_ratio?"),
    "checks.stress_sign.loss.cells[]": _F("world regime scenario dv"),
    "checks.stress_sign.requirement": _F("cells"),
    "checks.stress_sign.requirement.cells[]": _F("world regime stricter looser d_profit"),
    "checks.invariants[]": _F("name title ok detail"),
    "checks.gates[]": _F("name title fired mass cells cell_list status explanation expected_mass valid_until "
                         "expiring message corridor"),
    "checks.gates[].corridor": _F("text value"),
    "checks.flags[]": _F("name title raised detail"),
    "checks.control_model": _F("as_of commit rows book_version? all_ok? n_rows? n_bad? valuation_date?"),
    "checks.control_model.rows[]": _F("what unit core control diff diff_rel tol tol_kind tol_abs? ok"),
    "inputs": _F("rows"),
    "inputs.rows[]": _F("key name value unit as_of source status"),
    "live": _F("applied degraded degraded_flag valuation_date fetched_at prices curve key_rate register book_date "
               "book_age_days"),
    "live.prices.*": _F("value date time accepted status reason last_accepted"),
    "live.prices.*.last_accepted": _F("value date"),
    "live.curve": _F("as_of nodes book_nodes shift_bp"),
    "live.key_rate": _F("value date since"),
    "live.register": _F("as_of entries note"),
    "changes": _F("vs_previous snapshot"),
    "changes.vs_previous": _F("previous_sha previous_generated_at previous_published_at rows walk_book "
                              "total_point_rub total_median_rub market_price reference note"),
    "changes.vs_previous.rows[]": _F("component title point_rub median_rub note"),
    "changes.vs_previous.walk_book[]": _F("key title point_rub"),
    "changes.vs_previous.market_price.*": _F("from to"),
    "changes.vs_previous.reference": _F("median point exdate_adjustment"),
    "valuation_history": _F("date sha median p10 p25 p75 p90 point price rollbacks book_changes rule source"),
    "valuation_history.book_changes[]": _F("date from to"),
    "book": _F("version date tag facts_date curve_as_of worlds_source key_judgements changes_last? "
               "reference_variants?"),
    "book.reference_variants": _F("point rows basis? warning?"),
    "book.reference_variants.rows[]": _F("id title point d_point d_median? note? why? median_mark? mark?"),
    "book.key_judgements[]": _F("id name value unit"),
    "book.changes_last": _F("from_version summary"),
}

FORBIDDEN_FIELDS: dict[str, tuple[str, ...]] = {
    "": _F("debt bases network perimeter strategy scenarios capex_levels mixes regime_prob next_report_value "
           "next_report_neutral gates assumptions headline"),
    "meta.company": ("ticker",),
    "fair_value": _F("ev_first_line center_ev v_star ev_model ev_market_implied ev_gap rub_per_ev_percent "
                     "ev_comparison sigma_live sigma_ev strike credit_put horizon_years p_equity_nonpositive "
                     "judgement_spread"),
    "layers.*": _F("d pv_fcff pv_shield pv_financing structural strike strike_effective credit_put ev_ebitda_fwd "
                   "v0_to_d"),
    "grid.cells[]": _F("ev d capex margin_lt ev_ebitda_fwd max_leverage price_structural"),
    "market": _F("market_ev claims ev_ebitda_ltm peers_same_base sellside"),
    "market.brokers": ("rows",),
    "dividends": _F("target_leverage leverage_target no_pay_above"),
    "nowcast": _F("margin implied_half interest"),
    "book": ("sections",),
}

PRECISION: dict[str, float] = {
    "price": 0.01, "market": 0.001, "draw": 0.1, "money": 0.01, "money_cells": 0.1, "share": 1e-6, "share_cells": 1e-4,
    "prob": 1e-6, "multiple": 1e-4, "dps": 1e-4, "dps_cells": 0.01, "shares": 0.001, "significant": 9,
}

HASH_EXCLUDED: tuple[str, ...] = (
    "meta.generated_at", "meta.published_at", "meta.payload_sha256", "meta.previous_sha256", "meta.bytes",
    "live.fetched_at", "nowcast.journal.releases", "nowcast.journal.entries[].release_sha", "changes",
    "valuation_history",
)

_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
HYGIENE_RULES: tuple[tuple[str, re.Pattern, re.Pattern | None], ...] = (
    ("почта", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
     re.compile(r"[^@\s]+@(?:[\w-]+\.)*(?:example\.(?:com|org|net)|[\w-]+\.(?:test|invalid|example))")),
    ("телефон", re.compile(r"\+7[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)|"
                           r"(?<![\d.])8[\s-]?\(\d{3}\)[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"), None),
    ("IPv4", re.compile(rf"(?<![\w.]){_OCTET}\.{_OCTET}\.{_OCTET}\.{_OCTET}(?![\w.])"),
     re.compile(r"127\.0\.0\.1|0\.0\.0\.0|(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d+")),
    ("путь", re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|(?<![\w.:/])/(?:home|root|srv|Users)/|"
                        r"(?<![\w.:/])/(?:var/lib|usr/local/etc)/"), None),
)

INVARIANT_TITLES = {
    "probabilities": "Вероятности клеток, режимов, сценариев и веса миров в сумме 1",
    "bv_identity": "Капитал: тождество чистого излишка в каждом квартале каждой клетки",
    "balance_identity": "Баланс: активы = пассивы + капитал",
    "pnl_identity": "ОПУ: прибыль = сумма строк",
    "ddm_equals_ri": "Дивидендная модель = остаточный доход в каждой клетке",
    "dps_history": "Формула политики воспроизводит объявленный DPS до копейки",
    "exdate_jump": "Скачок оценки на экс-дату = −DPS",
    "transmission_solved": "Передача ставки решена: ЧПМ в мире H и реализованная передача M − N равны книге",
    "dividend_bounds": "Дивиденды неотрицательны и не больше запаса капитала",
    "governance_sum": "Дисконт за управление = сумма каналов",
    "release_numbers": ("Числа выпуска конечны; печать = округлению половиной вверх; P10 ≤ медиана ≤ P90; "
                        "точка на оси ставок"),
    "book_schema": "Книга: закрытая схема, все читаемые ключи заполнены",
    "jump_guard": "Защита заголовка: скачок медианы объяснён (М§14.4)",
    "payload_contract": "Контракт выпуска и потолок 500 КБ",
}
GATE_TITLES = {
    "pb_by_world": "P/B клетки вне коридора мира",
    "roe_range": "ROE года вне коридора",
    "cor_range": "CoR года вне коридора",
    "nim_range": "ЧПМ квартала вне коридора",
    "nim_path_joint": "Ближний путь ЧПМ выше якоря и уровня {lt_level}",
    "cir_range": "{cir} года вне коридора",
    "roe_k_homogeneity": "Разрыв «ROE − стоимость капитала» неоднороден по мирам",
    "guidance_gap": "Путь года вне гайденса",
    "capital_gap": "Капитальный разрыв: норматив ниже регуляторного пола",
    "k_gt_g": "Сработала защита «стоимость капитала больше роста»",
    "roe_gt_g": "ROE терминала не выше роста",
    "terminal_share": "Доля терминала вне коридора",
    "real_rate": "Реальная ставка терминала вне коридора",
    "bridge_drift": "Мост упр. ↔ МСФО дрейфует",
    "transmission_pairs": "Передача ставки между соседними мирами вне коридора",
    "lt_spread_floor": "Долгосрочный спред кредитной книги к опорной ставке ниже пола",
    "off_band_shift": "Оси вне полосы сдвигают заголовок",
    "m_crisis_vs_cbr": "Клетка «M × кризис» мягче рискового сценария ЦБ",
    "manual_input_overdue": "Ручной вход просрочен",
}
# Гейты второй формы банка (М§14.2; порядок — `model.checks.FORM_GATES`): в выпуске — при условии включения.
FORM_GATE_TITLES = {
    "growth_cut": "Рост портфеля урезан капиталом сильнее коридора",
    "step_dividend": "У ступени минимума срезан дивиденд политики",
    "cir_lt": "C/I модальной клетки на долгосрочном участке вне цели",
    "wholesale_share": "Доля оптового фондирования вне коридора",
    "payout_cap": "Выплата года по политике выше потолка",
    "nim_lt": "ЧПМ модальной клетки {lt_level} вне цели",
    "volume_sign": "Снятие остановки кредита и поправок роста снижает оценку",
    "stress_sign": "Оценка растёт с убытком кризиса или прибыль — с требованием к капиталу",
    "nim_stationary": "Стационарная ЧПМ мира-цели вне цели",
    "window_backtest": "Уровни слоя «рыночные ставки как есть» {lt_level} вне окна фактов",
    "funds_cost_to_key": "Стоимость средств клиентов к ключевой ставке выше порога",
}
# Заголовок гейта долгосрочного C/I, когда его область — слой «рыночные ставки как есть» (`checks.cir_lt.scope`).
CIR_LT_LAYER_TITLE = "C/I слоя «рыночные ставки как есть» на долгосрочном участке вне цели"
# Заголовки инвариантов, которые выбирает поведенческий ключ книги (М§14.1): вид теста истории выплат и база
# делителя; без ключа — строка `INVARIANT_TITLES`.
HISTORY_TITLES = {HISTORY_CAP: "Выплаты завершённого года не выше потолка политики",
                  HISTORY_NONE: "Тест истории выплат выключен книгой"}
EXDATE_TITLE_DIVISOR = "Скачок оценки на экс-дату = −DPS × акции в обращении / делитель"
# Флаги, которые добавляются в конец списка только поднятыми, в этом порядке (М§14.3): состав списка без них
# прежний.
RAISED_FLAG_TITLES = {"deal_pending": "Объявлена сделка, в книге её нет",
                      "capital_estimated": "Нормативы якоря — оценка до выхода формы"}
# Флаги выпуска по порядку печати. Заголовок, называющий орган решения о дивиденде или месячный релиз
# эмитента, — подпись книги (`FLAG_LABELS`: имя флага → ключ `meta.labels`); здесь у него `None`.
FLAG_TITLES = {
    "book_update": "Книгу пора обновить",
    "report_fact": "Вышла МСФО, факт не внесён",
    "dividend_register": None,
    "ni_jump": "Прибыль квартала г/г прыгает при неизменной ключевой",
    "dividend_recommended": "Совет директоров рекомендовал дивиденд",
    "explanation_expiring": "Срок объяснения проверки истекает",
    "policy_expired": "Срок дивидендной политики истёк: действует прежняя до новой",
    "price_fallback": "Живая цена не принята",
    "ras_mismatch": None,
}
FLAG_LABELS = {"dividend_register": "register.flag_title", "ras_mismatch": "flags.ras_mismatch"}


def schema_name(book: Book) -> str:
    """Имя схемы выпуска — ключ книги `meta.schema` (М§0.6)."""
    return str(book.get("meta.schema"))


def gate_title(book: Book, name: str) -> str:
    """Заголовок гейта: слова кода с терминами книги (`meta.labels.terms.lt_level`; слово отношения расходов к
    доходам — `terms.cir`, без него — прежнее слово кода)."""
    title = GATE_TITLES.get(name) or FORM_GATE_TITLES.get(name, name)
    if name == "cir_lt" and book.opt("checks.cir_lt.scope") == MARKET_LAYER:
        title = CIR_LT_LAYER_TITLE
    return title.format(lt_level=book.label("terms.lt_level"), cir=cir_word(book))


TRANSMISSION_TITLE_LEVEL = ("Передача ставки решена: ЧПМ {lt_level} мира {world} и реализованная передача равны "
                            "книге")


def invariant_title(book: Book, name: str) -> str:
    """Заголовок инварианта; у `dps_history`, `exdate_jump` и `transmission_solved` его выбирает ключ книги
    (М§14.1): у книги с миром уровня (`nii.transmission.level_world`, М§4.5) инвариант передачи сверяет ЧПМ
    этого мира — заголовок называет его."""
    if name == "transmission_solved" and level_world(book) is not None:
        return TRANSMISSION_TITLE_LEVEL.format(lt_level=book.label("terms.lt_level"), world=level_world(book))
    if name == "dps_history":
        return HISTORY_TITLES.get(history_test(book), INVARIANT_TITLES[name])
    if name == "exdate_jump" and book.opt("valuation.shares_basis") == SHARES_ISSUED:
        return EXDATE_TITLE_DIVISOR
    return INVARIANT_TITLES[name]


def flag_title(book: Book, name: str) -> str:
    """Заголовок флага: литерал кода или подпись книги (`FLAG_LABELS`)."""
    return book.label(FLAG_LABELS[name]) if name in FLAG_LABELS else FLAG_TITLES[name]


# ------------------------------------------------------------------ хэш, размер, коммит


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _content(payload: Mapping[str, Any]) -> dict:
    p = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    meta = p.get("meta") or {}
    for k in ("generated_at", "published_at", "payload_sha256", "previous_sha256", "bytes"):
        meta.pop(k, None)
    (p.get("live") or {}).pop("fetched_at", None)
    journal = (p.get("nowcast") or {}).get("journal") or {}
    if isinstance(journal, dict):
        journal.pop("releases", None)
        for e in journal.get("entries") or []:
            if isinstance(e, dict):
                e.pop("release_sha", None)
    p.pop("changes", None)
    p.pop("valuation_history", None)
    return p


def payload_hash(payload: Mapping[str, Any]) -> str:
    """sha256 канонического JSON без полей и блоков HASH_EXCLUDED (П§0.4)."""
    return hashlib.sha256(_canon(_content(payload))).hexdigest()


def compact_bytes(payload: Mapping[str, Any]) -> int:
    """Байты компактного JSON без `meta.published_at` и `meta.bytes` (П§0.4)."""
    meta = {k: v for k, v in (payload.get("meta") or {}).items() if k not in ("published_at", "bytes")}
    return len(json.dumps(dict(payload, meta=meta), ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8"))


def engine_commit() -> str:
    """40 hex коммита ядра: git; без git — окружение CI (GITHUB_SHA) или нули."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        sha = out.stdout.strip()
        if out.returncode == 0 and HEX40.fullmatch(sha):
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    return sha if HEX40.fullmatch(sha) else "0" * 40


# ------------------------------------------------------------------ округление


def _nd(step: float) -> int:
    return max(0, -int(math.floor(math.log10(step) + EPS)))


def rnd(x: Any, step: float) -> Any:
    """Хранимая точность П§0.3 (None и не числа — как есть)."""
    if x is None or isinstance(x, bool) or not isinstance(x, (int, float)):
        return x
    if not math.isfinite(float(x)):
        return float(x)
    return round(float(x), _nd(step))


def sig(x: Any) -> Any:
    if x is None or isinstance(x, bool) or not isinstance(x, (int, float)):
        return x
    return float(f"{float(x):.9g}") if math.isfinite(float(x)) else float(x)


R_PRICE = lambda x: rnd(x, PRECISION["price"])      # noqa: E731
# цены рынка (market.price, market.prices[*].price, headline.market, headline.market_by_ticker) — шаг 0,001 ₽: тик бумаги
# мельче 0,01 ₽ (LEGALCLOSEPRICE 10,105 ₽), с шагом цены выпуск печатал бы цену, по которой бумага не закрывалась (П§0.3)
R_MARKET = lambda x: rnd(x, PRECISION["market"])    # noqa: E731
R_MONEY = lambda x: rnd(x, PRECISION["money"])      # noqa: E731
R_SHARE = lambda x: rnd(x, PRECISION["share"])      # noqa: E731
R_PROB = lambda x: rnd(x, PRECISION["prob"])        # noqa: E731
R_MULT = lambda x: rnd(x, PRECISION["multiple"])    # noqa: E731
R_DPS = lambda x: rnd(x, PRECISION["dps"])          # noqa: E731


# ------------------------------------------------------------------ гигиена и validate


def _strings(node: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(node, Mapping):
        for k, v in node.items():
            if isinstance(k, str):
                yield f"{path}.{k}(ключ)", k
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _may_match(rule: str, text: str) -> bool:
    """Дешёвый предфильтр: без «@», цифр или «:»/«/» правило не сработает (и не переберёт длинную строку)."""
    if rule == "почта":
        return "@" in text
    if rule in ("телефон", "IPv4"):
        return any(ch.isdigit() for ch in text)
    return ":" in text or "/" in text


def hygiene_problems(payload: Mapping[str, Any]) -> list[str]:
    """Почты, телефоны, IPv4 (кроме петли и RFC 5737) и пути ФС в строках выпуска — отказ (без самого текста)."""
    found = []
    for path, text in _strings(payload):
        for rule, pattern, allow in HYGIENE_RULES:
            if not _may_match(rule, text):
                continue
            for hit in pattern.finditer(text):
                if allow is not None and allow.fullmatch(hit.group(0)):
                    continue
                found.append(f"{path}: {rule}")
                break
    return [f"гигиена выпуска: {len(found)} совпадений — " + "; ".join(found[:5])] if found else []


def _finite_problems(node: Any, path: str = "$", out: list | None = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(node, float):
        if not math.isfinite(node):
            out.append(f"{path}: не конечное число")
    elif isinstance(node, Mapping):
        for k, v in node.items():
            _finite_problems(v, f"{path}.{k}", out)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _finite_problems(v, f"{path}[{i}]", out)
    return out


def _nodes(payload: Mapping[str, Any], spec: str) -> list[tuple[str, Any]]:
    """Узлы по спецификации пути «a.b[].c», «layers.*»."""
    cur: list[tuple[str, Any]] = [("", payload)]
    for part in spec.split(".") if spec else []:
        nxt = []
        many = part.endswith("[]")
        name = part[:-2] if many else part
        for where, node in cur:
            if not isinstance(node, Mapping):
                continue
            if name == "*":
                items = [(f"{where}.{k}", v) for k, v in node.items()]
            elif name in node:
                items = [(f"{where}.{name}".lstrip("."), node[name])]
            else:
                continue
            for w, v in items:
                if many:
                    if isinstance(v, list):
                        nxt.extend((f"{w}[{i}]", x) for i, x in enumerate(v))
                else:
                    nxt.append((w, v))
        cur = nxt
    return cur


def _close(a: Any, b: Any, tol: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _q7(vals: Sequence[float], q: float) -> float:
    return U.quantile(vals, q)


PERIOD_RE = re.compile(r"^\d{4}(Q[1-4]|M(0[1-9]|1[0-2]))$")
INF_RE = re.compile(r"(?<![A-Za-zА-Яа-я])-?inf(?![A-Za-zА-Яа-я])")
TUPLE_RE = re.compile(r"\((?:-?[\d.]+|None|-?inf)(?:,\s+(?:-?[\d.]+|None|-?inf))+\)")
CODE_RE = re.compile(r"[a-z][a-z_0-9]*")          # код базиса; слова («МСФО группы») — не код
SERVICE_SOURCE = "valuation.uncertainty"          # служебный путь источником суждения не бывает (П§2)
# Базисы П§0.2 и `market` — рыночные ряды плиток индикаторов (ставки, кривая, цены): код живёт в
# конфигурации индикаторов и в словаре витрины.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(payload: Mapping[str, Any], *, publish: bool = False, schema: str | None = None) -> list[str]:
    """Контракт выпуска П§7; [] — годен. `publish=True` требует `meta.fast = false`. `schema` — имя схемы,
    которое обязан нести выпуск; `None` — имя из книги репозитория (`meta.schema`)."""
    p: list[str] = []
    if not isinstance(payload, Mapping):
        return ["выпуск — не объект JSON"]
    schema = schema_name(load_book()) if schema is None else str(schema)
    if payload.get("schema") != schema:
        p.append(f"schema = {payload.get('schema')!r}, нужно {schema!r}")
    missing = [b for b in REQUIRED_TOP_LEVEL if b not in payload]
    if missing:
        p.append("нет блоков: " + ", ".join(missing))
    for spec, fields in REQUIRED_FIELDS.items():
        for where, node in _nodes(payload, spec):
            if not isinstance(node, Mapping):
                continue
            lost = [f for f in fields if not f.endswith("?") and f not in node]
            if lost:
                p.append(f"{where or spec}: нет полей {', '.join(lost)}")
    for spec, fields in FORBIDDEN_FIELDS.items():
        for where, node in _nodes(payload, spec):
            if isinstance(node, Mapping):
                bad = [f for f in fields if f in node]
                if bad:
                    p.append(f"{where or 'верхний уровень'}: снятые поля {', '.join(bad)} (П§6)")
    if p:
        return p          # дальше проверки читают поля — без них бессмысленны
    p.extend(_finite_problems(payload))
    try:
        _canon(payload)
    except (TypeError, ValueError) as exc:
        p.append(f"выпуск не сериализуется в строгий JSON: {exc}")
        return p
    meta = payload["meta"]
    size = compact_bytes(payload)
    if meta.get("bytes") != size:
        p.append(f"meta.bytes = {meta.get('bytes')}, измерено {size}")
    if size > MAX_BYTES:
        p.append(f"выпуск {size} байт больше потолка {MAX_BYTES}")
    if meta.get("payload_sha256") != payload_hash(payload):
        p.append("meta.payload_sha256 не равен хэшу содержания (П§0.4)")
    if publish and meta.get("fast") is not False:
        p.append("быстрая сборка (meta.fast) не публикуется")
    if not HEX40.fullmatch(str(meta.get("engine_commit") or "")):
        p.append("meta.engine_commit — не 40 hex")
    p.extend(hygiene_problems(payload))
    company = _guarded(_company_problems, payload)
    p.extend(company)
    if company:
        return p          # без главного тикера и цен дальше сверять не с чем
    for check in (_headline_problems, _point_problems, _bank_problems, _layer_problems, _dividend_problems,
                  _capital_problems, _path_problems, _judgement_problems, _check_problems, _format_problems):
        p.extend(_guarded(check, payload))
    return p


def _guarded(check, payload: Mapping[str, Any]) -> list[str]:
    """Проверка, которая на испорченном выпуске не падает, а называет поломку."""
    try:
        return check(payload)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, ZeroDivisionError) as exc:
        return [f"{check.__name__.strip('_')}: выпуск не разбирается ({type(exc).__name__}: {exc})"]


def _company_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    c = d["meta"]["company"]
    tickers = list(c.get("tickers") or [])
    main = c.get("main_ticker")
    if main not in tickers:
        p.append("meta.company.main_ticker не среди tickers")
        return p
    h = d["fair_value"]["headline"]
    for where, node in (("market.prices", d["market"]["prices"]), ("headline.market_by_ticker", h["market_by_ticker"]),
                        ("headline.p_below_by_ticker", h["p_below_by_ticker"]), ("headline.upside", h["upside"])):
        if not isinstance(node, Mapping) or set(node) != set(tickers):
            p.append(f"{where}: тикеры не те, что meta.company.tickers")
    if main not in d["market"]["prices"]:
        return p
    if d["market"]["price"] != (d["market"]["prices"].get(main) or {}).get("price"):
        p.append("market.price ≠ цене главного тикера")
    return p


def _centres(h: Mapping[str, Any], lam: float) -> list[float]:
    return sorted(lo + lam * (hi - lo) for lo, hi in zip(h["low_draws"], h["high_draws"]))


def _headline_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    h = d["fair_value"]["headline"]
    lo, hi = h["low_draws"], h["high_draws"]
    if not lo or len(lo) != len(hi) or len(lo) != h.get("draws"):
        return ["headline: low_draws/high_draws не той длины, что draws"]
    # прогоны хранятся с шагом полосы (М§10): поле `draw_step` выпуска, без поля — PRECISION["draw"]
    grain = float(h.get("draw_step", PRECISION["draw"]))
    off_grid = [v for v in list(lo) + list(hi) if U.round_half_up(v, grain) != v]
    if off_grid:
        p.append(f"headline: прогоны не кратны шагу хранения {grain:g} ₽ (первый — {off_grid[0]!r})")
    main = d["meta"]["company"]["main_ticker"]
    price = d["market"]["prices"][main]["price"]
    step = float(h["print_step"])
    lam = float(h["own_macro_confidence"])
    levels = sorted(float(q) for q in h["quantiles"])
    if len(levels) != len(U.QUANTILE_NAMES):
        return [f"headline.quantiles: нужно {len(U.QUANTILE_NAMES)} уровней"]

    def check_row(row: Mapping[str, Any], lam_: float, where: str, printed: bool) -> None:
        c = _centres(h, lam_)
        want = {name: _q7(c, q) for name, q in zip(U.QUANTILE_NAMES, levels)}
        want["mean"] = sum(c) / len(c)
        got = {"median": row.get("median"), "mean": row.get("mean")}
        if printed:
            got.update(p10=row["band80"][0], p90=row["band80"][1], p25=row["band50"][0], p75=row["band50"][1])
        else:
            got.update(p10=row.get("p10"), p25=row.get("p25"), p75=row.get("p75"), p90=row.get("p90"))
        for k, v in want.items():
            if not _close(got[k], v, 0.005):
                p.append(f"{where}: {k} {got[k]} не воспроизводится из прогонов ({v:.4f})")
        pb = sum(1 for v in c if v < price) / len(c)
        half = (grain + PRECISION["market"]) / 2 + 1e-9  # прогоны хранятся с шагом grain, цена рынка — с шагом market (перенос правки семейства 521f4e3):
        pb_lo = sum(1 for v in c if v < price - half) / len(c)     # прогон в полушаге от цены считается любой стороной
        pb_hi = sum(1 for v in c if v < price + half) / len(c)
        got_pb = row.get("p_below_market")
        if got_pb is None or not (pb_lo - 1e-6 <= got_pb <= pb_hi + 1e-6):
            p.append(f"{where}: P(ниже рынка) {got_pb} ≠ {pb} (допустимо {pb_lo}…{pb_hi})")
        if printed:
            for key, val in (("printed_median", want["median"]),):
                if row.get(key) != U.round_half_up(val, step):
                    p.append(f"{where}: {key} {row.get(key)} ≠ ROUND_HALF_UP({val:.4f}, {step:g})")
            for key, pair in (("printed_band80", (want["p10"], want["p90"])),
                              ("printed_band50", (want["p25"], want["p75"]))):
                if list(row.get(key) or []) != [U.round_half_up(x, step) for x in pair]:
                    p.append(f"{where}: {key} ≠ округлению полос")
            ceiling = float(h["ceiling_x_market"]) * price
            if not (0 <= want["p10"] <= want["p25"] <= want["median"] <= want["p75"] <= want["p90"] <= ceiling):
                p.append(f"{where}: нарушено 0 ≤ P10 ≤ P25 ≤ медиана ≤ P75 ≤ P90 ≤ потолок {ceiling:.2f}")

    check_row(h, lam, "headline", True)
    rows = h.get("by_lambda") or []
    step_l = float(h.get("lambda_step") or 0)
    grid = [round(i * step_l, 9) for i in range(LAMBDA_STEPS + 1)] if step_l else []
    have = [round(float(r["lambda"]), 9) for r in rows]
    if step_l * LAMBDA_STEPS != 1.0 and abs(step_l * LAMBDA_STEPS - 1) > 1e-12:
        p.append(f"lambda_step {step_l} — не 1/{LAMBDA_STEPS}")
    if any(g not in have for g in grid):
        p.append("headline.by_lambda не покрывает сетку λ")
    for r in rows:
        check_row(r, float(r["lambda"]), f"by_lambda λ={r['lambda']}", False)
    book_row = [r for r in rows if abs(float(r["lambda"]) - lam) < EPS]
    if not book_row:
        p.append("headline.by_lambda: нет строки λ книги")
    elif book_row[0]["median"] != h["median"] or book_row[0]["p_below_market"] != h["p_below_market"]:
        p.append("headline.by_lambda: строка λ книги ≠ заголовку")
    contrib = h.get("contributions") or []
    if contrib and not _close(sum(float(c["share"]) for c in contrib), 1.0, 1e-5):
        p.append("headline.contributions: доли не в сумме 1")
    return p


def _point_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    fv = d["fair_value"]
    lam = float(fv["own_macro_confidence"])
    if not _close(fv["central"], fv["low"] + lam * (fv["high"] - fv["low"]), TOL_POINT):
        p.append("fair_value.central ≠ low + λ (high − low)")
    rv = fv["rates_view"]
    if not _close(rv["rub"], rv["high"] - rv["low"], TOL_POINT):
        p.append("rates_view.rub ≠ high − low")
    mix = d["layers"]["headline_mix"]
    if not _close(mix["price"], fv["central"], TOL_POINT):
        p.append("layers.headline_mix.price ≠ fair_value.central")
    shares = d["meta"]["shares"]
    n_div = shares.get("divisor_mln", shares["outstanding_mln"])     # делитель выпуска (М§8.4)
    if not n_div > 0:
        return p + [f"meta.shares: делитель выпуска {n_div!r} — не больше нуля (П§7 п. 15)"]
    g = d["meta"]["governance_discount"]
    v0 = mix["v0"]
    pend = float(fv["bridge"].get("pending_dividend") or 0.0)
    core = v0 - pend
    want = ((core * (1 - g) + pend if core > 0 else v0) + mix["bridge"]) * 1000 / n_div
    if not _close(mix["price"], want, TOL_FORMULA):
        p.append(f"headline_mix.price ≠ формуле М§8.2 ({want:.2f})")
    wf = {r["key"]: r["amount"] for r in mix.get("waterfall") or []}
    if set(wf) >= {"bv_v", "pv_ri_explicit", "pv_terminal", "v0", "governance", "bridge", "equity"}:
        if not _close(wf["bv_v"] + wf["pv_ri_explicit"] + wf["pv_terminal"] + wf.get("buyback", 0.0), wf["v0"], 0.05):
            p.append("водопад: bv_v + pv_ri + pv_terminal ≠ v0")
        if not _close(wf["v0"] + wf["governance"] + wf["bridge"], wf["equity"], 0.05):
            p.append("водопад: v0 + governance + bridge ≠ equity")
    else:
        p.append("layers.headline_mix.waterfall: не все строки")
    return p


def _bank_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    b = d["fair_value"]["bank_first_line"]
    cap = d["market"]["cap"]
    if cap is not None and b.get("bv_v"):
        if not _close(b["market_pb"], cap / b["bv_v"], 1e-4):
            p.append("bank_first_line.market_pb ≠ Cap / bv_v")
        if not _close(b["excess_market"], cap - b["bv_v"], 0.05):
            p.append("bank_first_line.excess_market ≠ Cap − bv_v")
    if b["market_pb"] != d["market"]["multiples"]["pb"]:
        p.append("bank_first_line.market_pb ≠ market.multiples.pb")
    if not _close(b["excess_point"], b["v_point"] - b["bv_v"], 0.05):
        p.append("bank_first_line.excess_point ≠ v_point − bv_v")
    if b.get("v_median") is not None and not _close(b["excess_median"], b["v_median"] - b["bv_v"], 0.05):
        p.append("bank_first_line.excess_median ≠ v_median − bv_v")
    lam = float(d["fair_value"]["own_macro_confidence"])
    rows = [r for r in b.get("by_lambda") or [] if abs(float(r["lambda"]) - lam) < EPS]
    if not rows:
        p.append("bank_first_line.by_lambda: нет строки λ книги")
    else:
        for k in ("bv_v", "v_point", "v_median", "market_pb", "excess_point", "roe_tc", "k_tc"):
            if rows[0].get(k) != b.get(k):
                p.append(f"bank_first_line.by_lambda при λ книги: {k} ≠ полю блока")
    return p


def _layer_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    for key in ("analytical", "market_implied", "macro_neutral"):
        L = d["layers"][key]
        if not _close(sum(L["world_weights"].values()), 1.0, 1e-5):
            p.append(f"layers.{key}: веса миров не в сумме 1")
        if not _close(L["v0"], L["bv_v"] + L["pv_ri_explicit"] + L["pv_terminal"] + L.get("buyback_effect", 0.0), 0.05):
            p.append(f"layers.{key}: v0 ≠ bv_v + pv_ri_explicit + pv_terminal")
    cells = d["grid"]["cells"]
    if len(cells) != 36 or len({(c["world"], c["regime"], c["scenario"]) for c in cells}) != 36:
        p.append("grid.cells: нужно 36 клеток, по одной на тройку")
    for field_, layer in (("p_analytical", "analytical"), ("p_market_implied", "market_implied"),
                          ("p_neutral", "macro_neutral")):
        if not _close(sum(c[field_] for c in cells), 1.0, 1e-5):
            p.append(f"grid.cells: {field_} не в сумме 1")
        v0 = sum(c[field_] * c["v"] for c in cells)
        # погрешность хранения: v — 0,01, вероятности — 1e-6 (половина шага на клетку)
        tol = 0.05 + len(cells) * PRECISION["prob"] / 2 * max((abs(c["v"]) for c in cells), default=0.0)
        if not _close(v0, d["layers"][layer]["v0"], tol):
            p.append(f"layers.{layer}.v0 ≠ Σ P·v клеток ({v0:.2f})")
    return p


def _dividend_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    br = d["fair_value"]["bridge"]
    if not _close(br["amount"], sum(r["amount"] * r["sign"] for r in br.get("rows") or []), 0.05):
        p.append("fair_value.bridge.amount ≠ Σ строк со знаком")
    price = d["market"]["price"]
    for r in d["dividends"]["register"]:
        who = r.get("period") or r.get("year")
        if r.get("dps") is None or not 0 < r["dps"] < 0.5 * price:
            p.append(f"реестр {who}: DPS вне (0; 0,5 × цены)")
        if r.get("status") in ("declared", "paid") and r.get("ex_date") != r.get("record_date"):
            p.append(f"реестр {who}: экс-дата ≠ отсечке")
    fc = d["dividends"]["formula_check"]
    kind = d["dividends"]["policy"].get("history_test", HISTORY_EXACT)
    if kind == HISTORY_EXACT:                  # формула «до копейки» — только у этого вида теста (М§5.2)
        if not all(r.get("ok") for r in fc):
            p.append("dividends.formula_check: не все строки ok")
        years = {r.get("year") for r in fc}
        anchor_year = parse_period(d["meta"]["anchor_period"])[0]
        need = {anchor_year - 2, anchor_year - 1}
        if not need <= years:
            p.append(f"dividends.formula_check: нет лет {sorted(need - years)}")
    elif fc:
        p.append(f"dividends.formula_check: строки формулы при тесте истории вида {kind!r}")
    if kind == HISTORY_CAP:
        rows = d["dividends"].get("cap_check") or []
        if not any(r.get("complete") for r in rows) or any(r.get("ok") is False for r in rows):
            p.append("dividends.cap_check: нет завершённого года или выплаты года выше потолка политики")
    ne = d["dividends"]["next_expected"]
    if ne.get("status") == "model":
        # годовой плательщик при квартальном календаре модели (узел `model_quarters` — ровно при нём, как у сборщика
        # `annual_payer`): ожидание модели (П§2); в годовом календаре модели главная цифра — DPS политики
        if d["dividends"]["policy"].get("frequency") == "annual" and "model_quarters" in d["dividends"]:
            if not _close(ne.get("dps"), ne.get("dps_mean"), PRECISION["dps"]):
                p.append("dividends.next_expected.dps ≠ dps_mean при статусе model годового плательщика (П§7 п. 9)")
        elif ne.get("dps") != ne.get("dps_policy"):
            p.append("dividends.next_expected.dps ≠ dps_policy при статусе model (П§7 п. 9)")
    else:
        key = "period" if ne.get("period") is not None else "year"     # запись — по периоду, если поле есть
        reg = [r for r in d["dividends"]["register"] if r.get(key) == ne.get(key)
               and r.get("status") == ne.get("status")]
        if not reg or not _close(reg[0].get("dps"), ne.get("dps"), PRECISION["dps"]):
            p.append("dividends.next_expected.dps ≠ DPS записи реестра (П§7 п. 9)")
    return p


def _capital_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    cap = d["capital"]
    b = cap["bridge"]
    if not _close(b["start"] + sum(r["pp"] for r in b["rows"]), b["end"], 1e-5):
        p.append("capital.bridge: start + Σ pp ≠ end")
    n = len(cap["years"])
    for s, row in cap["by_scenario"].items():
        if any(isinstance(v, list) and len(v) != n for v in row.values()):
            p.append(f"capital.by_scenario.{s}: массивы не длины years")
    for s, row in cap["scenarios"].items():
        if any(isinstance(v, list) and len(v) != n for k, v in row.items() if k != "p_given_regime"):
            p.append(f"capital.scenarios.{s}: массивы не длины years")
    for row in d["paths"]["roe_tree"]:
        if None not in (row.get("roa"), row.get("leverage"), row.get("roe")) and \
                abs(row["roa"] * row["leverage"] - row["roe"]) > 1e-5:
            p.append(f"paths.roe_tree {row.get('year')}: roa × leverage ≠ roe")
    # норматив смеси — в определении движка: = ожиданию нормативов клеток под весами смеси (П§7 п. 10); допуск —
    # 0,05 п.п. либо ключ книги `checks.mix_ratio_tolerance` (поле `capital.mix_tolerance`), не шире десяти обычных
    tol_mix = cap.get("mix_tolerance", TOL_RATIO)
    if isinstance(tol_mix, bool) or not isinstance(tol_mix, (int, float)) or not 0 < tol_mix <= 10 * TOL_RATIO:
        p.append(f"capital.mix_tolerance = {tol_mix!r}: допуск сверки норматива смеси — больше нуля и не шире "
                 f"{10 * TOL_RATIO:g}")
        tol_mix = TOL_RATIO
    lam = float(d["fair_value"]["own_macro_confidence"])
    cells = d["grid"]["cells"]
    if cap["years"] != d["grid"]["years"]:
        p.append("capital.years ≠ grid.years")
    else:
        for i, y in enumerate(cap["years"]):
            got = cap["mix"]["n20"][i]
            vals = [(c["annual"]["n20"][i], lam * c["p_analytical"] + (1 - lam) * c["p_neutral"]) for c in cells]
            if got is None or any(v is None for v, _ in vals):
                continue
            want = sum(v * w for v, w in vals)
            if not _close(got, want, tol_mix):
                p.append(f"capital.mix.n20 {y}: {got} ≠ ожиданию нормативов клеток {want:.5f} (норматив смеси — "
                         "с поправкой и вычетами сценария)")
                break
    if b["from"] == d["meta"]["anchor_period"] and not _close(b["start"], cap["anchor"]["n20"], TOL_RATIO):
        p.append(f"capital.bridge.start {b['start']} ≠ факту якоря {cap['anchor']['n20']}")
    gap = cap["capital_gap"]
    if isinstance(gap.get("cells"), bool) or not isinstance(gap.get("cells"), int) \
            or not isinstance(gap.get("cell_list"), list):
        p.append("capital.capital_gap: cells — число клеток, cell_list — список меток")
    p.extend(_panel_problems(d))
    return p


def _panel_problems(d: Mapping[str, Any]) -> list[str]:
    """П§7 п. 15: узлы панели, когда они есть, — массивы `capital.requirement` и `capital.growth` длины своих
    осей, одна строка замыкания книги в «цене правила», тождество моста «три прибыли»."""
    p = []
    cap = d["capital"]
    req = cap.get("requirement")
    if req is not None:
        n = len(req["periods"])
        rows = list(req["mix"].values()) + [v for row in req["by_scenario"].values() for v in row.values()]
        if any(len(v) != n for v in rows):
            p.append("capital.requirement: массивы не длины periods")
        if any(len(v) != len(cap["years"]) for v in req["years_mix"].values()):
            p.append("capital.requirement.years_mix: массивы не длины capital.years")
    growth = cap.get("growth")
    if growth is not None:
        n = len(growth["years"])
        rows = [growth[k] for k in ("potential", "actual", "cut_share", "catch_up", "lam_min", "p_cut")]
        rows += [v for row in growth["by_scenario"].values() for v in row.values()]
        if any(len(v) != n for v in rows):
            p.append("capital.growth: массивы не длины years")
        if len(growth["quarters"]["lam"]) != len(growth["quarters"]["periods"]):
            p.append("capital.growth.quarters: lam не длины periods")
    rule = cap.get("rule_price")
    if rule is not None and sum(1 for r in rule["rows"] if r.get("current") is True) != 1:
        p.append("capital.rule_price: замыкание книги (current) — ровно в одной строке")
    if req is not None and any(v not in req["mix"] for v in (req.get("compare") or {}).values()):
        p.append("capital.requirement.compare: названа строка, которой нет в mix")
    gates = {g.get("name"): g for g in d["checks"]["gates"]}
    for name in ("volume_sign", "stress_sign", "funds_cost_to_key"):   # узел числа гейта и гейт: сработал ⇔ не ok
        node = d["checks"].get(name)
        if node is not None and (name not in gates or bool(gates[name].get("fired")) == bool(node.get("ok"))):
            p.append(f"checks.{name}: узел числа гейта не согласован с гейтом {name}")
    for r in d["history"].get("three_profits") or []:
        parts = [r.get(k) for k in ("ni_operating", "ni_shareholders", "stake_effect", "debt_interest_effect")]
        if None not in parts and not _close(parts[0], parts[1] - parts[2] - parts[3], 0.05):
            p.append(f"history.three_profits {r.get('period')}: операционная прибыль ≠ прибыль акционеров − эффект "
                     "пакета − проценты по долгу")
    return p


PBT_ROWS = (("nii", 1), ("llp", -1), ("fvc", -1), ("fees", 1), ("insurance", 1), ("other", 1), ("noncore", 1),
            ("opex", -1), ("one_off", 1))      # строки года и их знак в прибыли до налога (П§2 paths.annual)


def _path_problems(d: Mapping[str, Any]) -> list[str]:
    """П§7 п. 11: в каждой строке `paths.annual[]` прибыль до налога равна сумме строк года (допуск денег на строку)."""
    p = []
    tol = 0.05 + len(PBT_ROWS) * PRECISION["money"] / 2
    for row in d["paths"]["annual"]:
        parts = [row.get(k) for k, _ in PBT_ROWS]
        if row.get("pbt") is None or any(v is None for v in parts):
            continue
        total = sum(sign * float(row[k]) for k, sign in PBT_ROWS)
        if not _close(row["pbt"], total, tol):
            p.append(f"paths.annual {row.get('year')}: pbt {row['pbt']} ≠ сумме строк года {total:.2f}")
    return p


def _judgement_problems(d: Mapping[str, Any]) -> list[str]:
    """П§7 п. 12: источник суждения непуст и не служебный путь; Σ сдвигов осей вне полосы = диагностике."""
    p = []
    rows = d["judgements"]["rows"]
    bad = [r.get("id") for r in rows if not str(r.get("source") or "").strip()
           or SERVICE_SOURCE in str(r.get("source"))]
    if bad:
        p.append(f"judgements.rows: источник пуст или служебный путь у {len(bad)} строк ({', '.join(map(str, bad[:3]))})")
    off = [r for r in rows if r.get("in_band") is False]
    diag = d["judgements"]["off_band_shift"]
    if diag.get("axes") != len(off):
        p.append("judgements.off_band_shift.axes ≠ числу строк вне полосы")
    shifts = [r.get("mean_shift") for r in off]
    if all(s is not None for s in shifts) and not _close(diag.get("rub"), sum(shifts),
                                                             PRECISION["price"] * (len(off) + 1)):
        p.append("judgements.off_band_shift.rub ≠ Σ mean_shift строк вне полосы")
    return p


def _check_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    ch = d["checks"]
    broken = [i["name"] for i in ch["invariants"] if not i.get("ok")]
    if ch.get("invariants_broken") != len(broken):
        p.append("checks.invariants_broken ≠ числу нарушенных инвариантов")
    if broken:
        p.append("нарушены инварианты: " + ", ".join(broken))
    today = d["meta"]["valuation_date"]
    for g in ch["gates"]:
        if g.get("fired") and g.get("status") != "explained":
            p.append(f"гейт {g['name']} сработал: {g.get('status')} (М§14.2)")
        elif g.get("fired") and g.get("valid_until") and str(g["valid_until"]) < str(today):
            p.append(f"гейт {g['name']}: объяснение истекло {g['valid_until']}")
    p.extend(_control_summary_problems(ch.get("control_model")))
    # истекающее объяснение — плашка `explanation_expiring`, не отказ и не тревога (М§14.2–§14.3)
    expiring = any(g.get("fired") and g.get("expiring") for g in ch["gates"])
    flag = next((x for x in ch["flags"] if x.get("name") == "explanation_expiring"), None)
    if flag is None or bool(flag.get("raised")) != expiring:
        p.append("checks.flags: флаг explanation_expiring не согласован с истекающими объяснениями гейтов")
    return p


def _control_summary_problems(cm: Any) -> list[str]:
    """Сводка сверки с контрольной моделью (П§2 `checks.control_model`): счётчики, когда сводка их несёт, отвечают
    её строкам — сверенных строк не меньше показанных, строк вне допуска не меньше показанных вне допуска,
    «всё в допуске» — только без строк вне допуска. Витрина печатает счётчики, а не длину показанного списка."""
    if not isinstance(cm, Mapping):
        return []
    p = []
    rows = [r for r in cm.get("rows") or [] if isinstance(r, Mapping)]
    shown_bad = sum(1 for r in rows if r.get("ok") is False)
    n_rows, n_bad = cm.get("n_rows"), cm.get("n_bad")
    if n_rows is not None and (not isinstance(n_rows, int) or isinstance(n_rows, bool) or n_rows < len(rows)):
        p.append(f"checks.control_model.n_rows = {n_rows!r}: сверенных строк не меньше показанных ({len(rows)})")
    if n_bad is not None and (not isinstance(n_bad, int) or isinstance(n_bad, bool) or n_bad < shown_bad
                              or (isinstance(n_rows, int) and n_bad > n_rows)):
        p.append(f"checks.control_model.n_bad = {n_bad!r}: не согласовано со строками сводки "
                 f"(показано вне допуска {shown_bad})")
    if cm.get("all_ok") is True and (shown_bad or (isinstance(n_bad, int) and n_bad > 0)):
        p.append("checks.control_model.all_ok: «всё в допуске» при строках вне допуска")
    if cm.get("valuation_date") is not None and not DATE_RE.match(str(cm["valuation_date"])):
        p.append(f"checks.control_model.valuation_date = {cm['valuation_date']!r}: нужна дата ГГГГ-ММ-ДД")
    return p


def _format_problems(d: Mapping[str, Any]) -> list[str]:
    p = []
    meta = d["meta"]
    for k in ("anchor_period", "first_period", "last_period", "open_period"):
        if not PERIOD_RE.match(str(meta.get(k))):
            p.append(f"meta.{k} = {meta.get(k)!r} — не период")
    for k in ("valuation_date", "facts_date", "book_date", "curve_as_of"):
        if not DATE_RE.match(str(meta.get(k))):
            p.append(f"meta.{k} = {meta.get(k)!r} — не дата ISO")
    for y in d["grid"]["years"]:
        if not isinstance(y, int):
            p.append("grid.years: годы — целые")
            break
    for r in d["paths"]["quarters"]:
        if not PERIOD_RE.match(str(r.get("period"))):
            p.append(f"paths.quarters: период {r.get('period')!r}")
            break
    # коды единиц и базисов — из словаря §0.2 (код без подписи витрина не знает)
    for where, rows in (("judgements.rows", d["judgements"]["rows"]), ("reverse_dcf.rows", d["reverse_dcf"]["rows"]),
                        ("reverse_dcf.bank_rows", d["reverse_dcf"]["bank_rows"]), ("inputs.rows", d["inputs"]["rows"]),
                        ("nowcast.targets", d["nowcast"]["targets"]),
                        ("book.key_judgements", d["book"]["key_judgements"]),
                        ("indicators.tiles", d["indicators"]["tiles"]),
                        ("checks.control_model.rows", (d["checks"].get("control_model") or {}).get("rows") or [])):
        bad = sorted({str(r.get("unit")) for r in rows if r.get("unit") not in UNIT_CODES})
        if bad:
            p.append(f"{where}: единицы вне кодов §0.2: {', '.join(bad)}")
    bad = sorted({f"{path}: {value}" for path, value in _basis_values(d) if value not in BASIS_CODES})
    if bad:
        p.append("basis вне кодов §0.2: " + "; ".join(bad[:5]))
    bad = sorted({str(t.get("basis")) for t in d["indicators"]["tiles"] if t.get("basis") not in BASIS_CODES})
    if bad:                                    # у плитки базис — только код: слов рядов в выпуске нет
        p.append("indicators.tiles: basis вне кодов §0.2: " + ", ".join(bad))
    for ev in list(d["calendar"]["events"]) + list(d["calendar"].get("recent") or []):
        if ev.get("kind") == "form102" and not (ev.get("precision") == "window" and ev.get("earliest")
                                                and ev.get("latest") and ev.get("confirmed") is False):
            p.append(f"calendar: событие {ev.get('id')} — дата формы ЦБ печатается окном (precision: window)")
            break
    for ev in list(d["calendar"]["events"]) + list(d["calendar"].get("recent") or []):
        if ev.get("estimated") is True and not (ev.get("earliest") and ev.get("latest")
                                                and ev.get("confirmed") is False):
            p.append(f"calendar: событие {ev.get('id')} — оценка даты печатается окном и без подтверждения")
            break
    p.extend(_gap_problems(d["history"]["gaps"]))
    for a in d["meta"]["shares"].get("corporate_actions") or []:
        factor = a.get("factor") if isinstance(a, Mapping) else None
        if factor is not None and (isinstance(factor, bool) or not isinstance(factor, (int, float)) or not factor > 0):
            p.append(f"meta.shares.corporate_actions {a.get('date')}: factor — число больше нуля, в выпуске "
                     f"{type(factor).__name__}")
            break
    keys = {i.get("key") for i in d["guidance"]["items"]}
    lost = sorted({str(r.get("key")) for r in d["guidance"]["revisions"] if r.get("key") not in keys})
    if lost:
        p.append("guidance.revisions: ключей нет среди guidance.items: " + ", ".join(lost))
    for g in d["checks"]["gates"]:
        msg = str(g.get("message") or "")
        if INF_RE.search(msg) or TUPLE_RE.search(msg):
            p.append(f"гейт {g.get('name')}: в сообщении inf или кортеж (служебный текст, П§0.2)")
    return p


GAP_RE = re.compile(r"^(\d{4}Q[1-4])(?:–(\d{4}Q[1-4]))?$")


def _gap_problems(gaps: Sequence[Mapping[str, Any]]) -> list[str]:
    """П§7 п. 14: период провала — квартал или диапазон; диапазоны одного базиса не пересекаются."""
    p = []
    spans: dict[str, list[tuple[int, int]]] = {}
    for g in gaps:
        m = GAP_RE.match(str(g.get("period")))
        if not m:
            p.append(f"history.gaps: период {g.get('period')!r} — не квартал и не диапазон")
            continue
        if g.get("basis") not in ("ifrs", "mgmt"):
            p.append(f"history.gaps {g.get('period')}: basis {g.get('basis')!r} — нужен ifrs или mgmt")
            continue
        idx = [y * 4 + q for y, q in (parse_period(x) for x in (m.group(1), m.group(2) or m.group(1)))]
        spans.setdefault(str(g["basis"]), []).append((idx[0], idx[1]))
    for basis, rows in spans.items():
        rows.sort()
        if any(a[1] >= b[0] for a, b in zip(rows, rows[1:])) or any(lo > hi for lo, hi in rows):
            p.append(f"history.gaps: диапазоны базиса {basis} пересекаются")
    return p


def _basis_values(node: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    """Все поля `basis` выпуска, значение которых — код (строка без пробелов и кириллицы)."""
    if isinstance(node, Mapping):
        for k, v in node.items():
            if k == "basis" and isinstance(v, str) and CODE_RE.fullmatch(v):
                yield f"{path}.basis", v
            else:
                yield from _basis_values(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _basis_values(v, f"{path}[{i}]")


# ================================================================== сборка


@dataclass
class Release:                             # всё посчитанное для одного выпуска
    book: Book
    facts: Facts
    live: LiveInputs
    live_report: LiveReport
    run: GridRun
    band: U.Band
    reverse: Mapping | None
    next_report: Mapping | None
    judgements: list
    findings: list[Finding]
    gates: list[GateStatus]
    indicators: Any
    previous: Mapping | None
    history: list[Mapping]
    fast: bool
    engine_commit: str
    # сверх договора (только добавление)
    today: date | None = None
    anchor: U.MedianAnchor | None = None
    sensitivities: Mapping[str, Any] | None = None
    explanations: Mapping[str, Any] = field(default_factory=dict)
    notes: list = field(default_factory=list)
    extra_findings: list[Finding] = field(default_factory=list)
    generated_at: str = ""
    off_band: Mapping[str, Any] = field(default_factory=dict)      # диагностика сдвига осей вне полосы (М§10)
    control_model: Mapping[str, Any] | None = None                 # сводка сверки с контрольной моделью (как есть)
    rule_price: Mapping[str, Any] | None = None                    # «цена правила» из таблиц книги (М§14.5)
    volume_sign: Mapping[str, Any] | None = None                   # число гейта знака объёмных эффектов (М§14.2)
    stress_sign: Mapping[str, Any] | None = None                   # число гейта знака стресса (М§14.2)
    reference_variants: Mapping[str, Any] | None = None            # справочные варианты из таблиц книги (М§14.5)
    remarks: list = field(default_factory=list)                    # замечания сборки словами: не отказ и не тревога


def data_repo_dir(data_repo: Path | None = None, state_dir_: Path | None = None) -> Path:
    if data_repo is not None:
        return Path(data_repo)
    env = os.environ.get(DATA_REPO_ENV)
    return Path(env) if env else state_dir(state_dir_) / "data-repo"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_data_repo(data_repo: Path | None = None, state_dir_: Path | None = None, *,
                   schema: str | None = None) -> tuple[dict | None, list]:
    """Прошлый выпуск (`latest.json`) и история публикаций (`history.json`) клона репозитория данных.
    Выпуск другой схемы прошлым не считается; `schema=None` — имя из книги репозитория."""
    schema = schema_name(load_book()) if schema is None else str(schema)
    root = data_repo_dir(data_repo, state_dir_)
    prev = _read_json(root / "latest.json")
    hist = _read_json(root / "history.json")
    if isinstance(hist, Mapping):
        hist = hist.get("rows") or []
    return (prev if isinstance(prev, dict) and prev.get("schema") == schema else None,
            [h for h in hist or [] if isinstance(h, Mapping)])


def load_release_notes(path: Path | None = None, *, today: date) -> list[dict]:
    """Записки к скачку заголовка (М§14.4): действующие на сегодня, допуск ≤ 25 %."""
    path = Path(path) if path else RELEASE_NOTES
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    out = []
    for i, n in enumerate(raw):
        until = to_date(n.get("valid_until"))
        tol = float(n.get("tolerance_pct"))
        if tol > NOTE_TOLERANCE_MAX:
            raise BookError(f"release_notes.yaml[{i}]: tolerance_pct {tol} > {NOTE_TOLERANCE_MAX}")
        if until >= today:
            out.append({"valid_until": until, "expected_central": float(n["expected_central"]),
                        "tolerance_pct": tol, "note": str(n.get("note", "")).strip()})
    return out


def _release_inputs(book: Book, facts: Facts, state_dir_: Path | None, today: date):
    """Выходы индикаторов (`indicators/outputs.py`, ленивый импорт; нет модуля — None)."""
    try:
        from indicators.outputs import release_inputs
    except ImportError:
        return None
    peers = [str(b.get("ticker")) for b in (facts.file("peers").get("banks") or [])] if "peers" in facts.files else []
    return release_inputs(tickers=[str(t) for t in book.get("meta.company.tickers")], peer_tickers=peers,
                          state_dir=state_dir_, today=today)


def axes_follow(book: Book) -> bool:
    """Идут ли концы оси полосы за сдвинутым значением в строках чувствительности (М§8.3): да — при ключе книги
    `valuation.reverse_dcf.axis_follow: both`, как в строках обратного расчёта; без ключа концы стоят."""
    return book.opt("valuation.reverse_dcf.axis_follow") == "both"


def sensitivity_book(book: Book, kind: str) -> Book:
    """Книга строки чувствительности (М§8.3): подмены `sensitivity_overrides`; при `axis_follow: both` ось
    полосы вида `value`, на которой стоит сдвинутый ключ, сдвигается вместе с ним обоими концами — та же
    конвенция, что у строк обратного расчёта (строки ЧПМ и запаса капитала; пути CoR водит ось вида `shift`,
    их сдвиг доходит до каждого прогона целиком)."""
    ov = sensitivity_overrides(book, kind)
    if kind != "cor" and axes_follow(book):
        axes = copy.deepcopy(list(book.get("valuation.uncertainty.axes")))
        moved: set[int] = set()
        for path, value in ov.items():
            for j, ax in enumerate(axes):
                if j not in moved and ax.get("kind") == "value" and path in ax.get("paths", []):
                    step = float(value) - float(book.get(path))
                    ax["low"], ax["high"] = float(ax["low"]) + step, float(ax["high"]) + step
                    moved.add(j)
        if moved:
            ov["valuation.uncertainty.axes"] = axes
    return U.trial_book(book, ov)


def sensitivities(book: Book, facts: Facts, live: LiveInputs, anchor: U.MedianAnchor, run: GridRun) -> dict:
    """Пересчёты для «₽ за 0,1 п.п. CoR / ЧПМ» (М§8.3): полосы median_draws на сдвинутой книге (те же точки
    гиперкуба, что у базовой, — сдвиг медианы считает оценщик срединных прогонов) и прогоны точки."""
    out: dict[str, Any] = {}
    for kind, key in (("cor", "cor_pp"), ("nim", "nim_pp")):
        b2 = sensitivity_book(book, kind)
        out[kind] = {"band": anchor.recompute(b2), "run": run_grid(b2, facts, live),
                     "step": float(book.get(f"valuation.sensitivities.{key}"))}
    out["roe_pp"] = float(book.get("valuation.sensitivities.roe_pp"))
    step = book.opt("valuation.sensitivities.buffer_pp")
    if step is not None:                        # «₽ за 1 п.п. запаса капитала» — только при ключе книги
        out["buffer"] = {"band": anchor.recompute(sensitivity_book(book, "buffer")), "step": float(step)}
    return out


def _priced_fields(r: Mapping[str, Any]) -> dict[str, Any]:
    """Поля цены строки из записи сухого перевывода (М§14.5): разности точки и медианы, причина «без цены» и пометки —
    только те, что несёт строка таблиц."""
    out: dict[str, Any] = {}
    for k in ("d_point", "d_median"):
        if k in r:
            out[k] = R_PRICE(r.get(k))
    for k in ("why", "median_mark", "mark"):
        if r.get(k):
            out[k] = str(r[k])
    return out


def rule_price_table(book: Book, results: Any = None) -> dict | None:
    """«Цена правила» (М§14.5) для выпуска: таблица `rule_price` из таблиц книги (`results.json`); сборка
    выпуска её не пересчитывает. `results` — словарь таблиц или путь к файлу; нет — файл репозитория. Таблица
    другой версии книги, без строк или не с одной строкой замыкания книги — узла нет. Подпись строки — подпись
    книги `meta.labels.rule_price.<замыкание>`, без неё — подпись таблицы. У книги с записью сухого перевывода
    (`valuation.reference_record`) строка несёт разности точки и медианы к книге (`d_point`, `d_median`), а не
    медиану в рублях; строка без цены — причину (`why`)."""
    if book.opt("capital.growth_constraint") is None:
        return None
    data = results if isinstance(results, Mapping) else _read_json(Path(results) if results is not None else RESULTS)
    if not isinstance(data, Mapping) or str(data.get("book_version")) != str(book.get("meta.version")):
        return None
    rows = (data.get("rule_price") or {}).get("rows") if isinstance(data.get("rule_price"), Mapping) else None
    if not rows or sum(1 for r in rows if r.get("current") is True) != 1:
        return None
    title = lambda r: book.label_or(f"rule_price.{r.get('key')}", str(r.get("title")))  # noqa: E731
    return {"rows": [{"key": r.get("key"), "title": title(r), "point": R_PRICE(r.get("point")),
                      **({"median": R_PRICE(r.get("median"))} if "median" in r else {}), **_priced_fields(r),
                      "capital_gap_mass": R_PROB(r.get("capital_gap_mass")),
                      "current": r.get("current") is True} for r in rows]}


VARIANTS_BOOK = "reference_variants_book"       # узел таблиц книги: отпечаток книги справочных вариантов


def reference_variants_state(book: Book, results: Any = None) -> tuple[dict | None, str | None]:
    """Справочные варианты (М§14.5) для выпуска и причина, по которой их нет: узел `reference_variants` таблиц
    книги (`results.json`) и точка книги рядом; сборка выпуска варианты не пересчитывает. `results` — словарь
    таблиц или путь к файлу; нет — файл репозитория. Узел берётся, только когда таблицы посчитаны на этой же
    книге: та же версия, строки по списку `valuation.reference_variants` (идентификаторы по порядку) и тот же
    отпечаток книги (`reference_variants_book`) — подмена варианта, сменённая без пересборки таблиц, в выпуск
    не попадает. Иначе узла нет, а причина возвращается словами (замечание сборки). Нет списка в книге — ни
    узла, ни причины. Подпись и необязательная подпись строки (`note`) — книги; строки — по убыванию модуля цены
    правила, строки без цены — последними. У книги с записью сухого перевывода (М§14.5) строка несёт и разность
    медиан (`d_median`), пометки и причину «без цены» (`why`), узел — базу разностей (`basis`) и предупреждение
    таблиц о записи от другой книги (`warning`: цены тогда не печатаются)."""
    specs = book.opt("valuation.reference_variants")
    if not specs:
        return None, None
    data = results if isinstance(results, Mapping) else _read_json(Path(results) if results is not None else RESULTS)
    if not isinstance(data, Mapping):
        return None, "таблиц книги нет"
    if str(data.get("book_version")) != str(book.get("meta.version")):
        return None, "таблицы книги — другой версии книги"
    rows = data.get("reference_variants")
    point = (data.get("headline") or {}).get("point") if isinstance(data.get("headline"), Mapping) else None
    if not isinstance(rows, list) or point is None or [r.get("id") for r in rows] != [str(s["id"]) for s in specs]:
        return None, "строки таблиц книги — не по списку вариантов книги"
    if data.get(VARIANTS_BOOK) is None:
        return None, "таблицы книги не несут отпечаток книги справочных вариантов (собраны до его появления)"
    if data.get(VARIANTS_BOOK) != book.digest:
        return None, "таблицы книги посчитаны на другой книге (отпечаток книги не совпал)"
    table = [{"id": str(s["id"]), "title": str(s["title"]), "point": R_PRICE(r.get("point")),
              "d_point": R_PRICE(r.get("d_point")), **{k: v for k, v in _priced_fields(r).items() if k != "d_point"},
              **({"note": str(s["note"])} if s.get("note") is not None else {})}
             for s, r in zip(specs, rows)]
    rec = data.get("reference_record") if isinstance(data.get("reference_record"), Mapping) else {}
    extra = {**({"basis": str(rec["basis"])} if rec.get("basis") else {}),
             **({"warning": str(rec["warning"])} if rec.get("warning") else {})}
    return {"point": R_PRICE(point), "rows": sorted(table, key=lambda r: (r["d_point"] is None, -abs(float(r["d_point"] or 0.0)))),
            **extra}, None


def reference_variants_table(book: Book, results: Any = None) -> dict | None:
    """Узел справочных вариантов выпуска (`reference_variants_state` без причины): нет — None."""
    return reference_variants_state(book, results)[0]


def variants_remark(why_not: str | None, node: Mapping[str, Any] | None = None) -> list[str]:
    """Замечание сборки о справочных вариантах, которых выпуск не взял: причина словами и что сделать; и
    предупреждение таблиц о записи сухого перевывода от другой книги (цены вариантов не печатаются, М§14.5).
    Причины нет — пусто. Замечание — не отказ и не тревога: код сборки не меняет."""
    out = []
    if why_not is not None:
        out.append(f"справочные варианты в выпуск не взяты: {why_not} — пересобрать таблицы книги "
                   "(python -B -m model.book_results)")
    if node is not None and node.get("warning"):
        out.append(f"цены справочных вариантов не напечатаны: {node['warning']}")
    return out


def absent_words(book: Book, indicators: Any) -> str | None:
    """Слова выпуска, собранного без слоя индикаторов (П§2 `nowcast.absent`): подпись книги
    `meta.labels.nowcast.absent`, когда выходов слоя индикаторов у сборки нет (сборка на цене и дате книги).
    Выходы есть или подписи нет — None: узла нет."""
    words = book.opt("meta.labels.nowcast.absent")
    return str(words) if indicators is None and words is not None else None


def make_release(*, live: bool = True, fast: bool = False, today: date | None = None,
                 state_dir: Path | None = None, data_repo: Path | None = None, book: Book | None = None,
                 facts: Facts | None = None, outputs: Any = None, explanations: Mapping | None = None,
                 notes: list | None = None, draws: int | None = None, control_model: Path | None = None,
                 results: Any = None) -> Release:
    """Порядок INTERFACES §6: книга и факты → индикаторы → живые входы → сетка, полоса → диагностики → проверки."""
    today = today or date.today()
    facts = facts or load_facts()
    book = book or load_book(facts=facts)
    commit = engine_commit()
    if live:
        if outputs is None:
            outputs = _release_inputs(book, facts, state_dir, today)
        live_in, report = apply_live(book, facts, outputs, today=today, previous=read_last_accepted(state_dir))
    else:
        outputs = None
        live_in, report = apply_live(book, facts, None, today=today)
    run = run_grid(book, facts, live_in)
    n = draws if draws is not None else (U.FAST_DRAWS if fast else int(book.get("valuation.uncertainty.draws")))
    band = U.band(book, facts, live_in, draws=n, keep=not fast)    # записи — уточнению обратного расчёта
    anchor = sens = None
    from model import nextreport as NR, reverse as RV
    if fast:
        reason = "быстрая сборка: поиски не считались"
        rev = RV.not_computed(book, reason, run=run)
        nxt = NR.not_computed(book, facts, live_in, reason, run=run)
        judg = _judgements_not_computed(book, band, reason)
    else:
        anchor = U.MedianAnchor(book, facts, live_in, band)
        rev = RV.reverse_dcf(book, facts, live_in, band, anchor=anchor, run=run)
        nxt = NR.next_report(book, facts, live_in, band, anchor=anchor, run=run)
        judg = U.judgements(book, facts, live_in, band, point=run.point)
        sens = sensitivities(book, facts, live_in, anchor, run)
    off_band = U.off_band_shift(book, facts, live_in, run.point, judg)
    signs = sign_numbers(run)                   # числа гейтов знака — центральной книги, одни с её таблицами
    findings = check_invariants(run, band) + check_gates(run, today=today, off_band=off_band, band=band, **signs)
    expl = explanations if explanations is not None else load_gate_explanations(today=today)
    gates = gate_statuses(findings, expl, today=today)
    previous, history = read_data_repo(data_repo, state_dir, schema=schema_name(book))
    cm = _read_json(Path(control_model) if control_model is not None else CONTROL_MODEL)
    variants, why_not = reference_variants_state(book, results)
    rel = Release(book=book, facts=facts, live=live_in, live_report=report, run=run, band=band, reverse=rev,
                  next_report=nxt, judgements=judg, findings=findings, gates=gates, indicators=outputs,
                  previous=previous, history=history, fast=fast, engine_commit=commit, today=today, anchor=anchor,
                  sensitivities=sens, explanations=expl, off_band=off_band,
                  control_model=cm if isinstance(cm, dict) else None,
                  rule_price=rule_price_table(book, results),
                  reference_variants=variants, **signs,
                  remarks=variants_remark(why_not, variants),
                  notes=notes if notes is not None else load_release_notes(today=today),
                  generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    rel.extra_findings = [exdate_finding(book, facts, live_in, run)]
    return rel


def _judgements_not_computed(book: Book, band: U.Band, reason: str) -> list[dict]:
    contrib = {r["axis"]: r for r in band.contributions(band.lam)}
    off = U.off_band_axes(book)
    keys = list(band.keys) + U.axis_keys(off)
    notes = U.book_notes(book)
    rows = []
    for j, ax in enumerate(tuple(band.axes) + off):
        in_band = j < len(band.axes)
        c = contrib.get(keys[j]) if in_band else None
        rows.append({"id": keys[j], "name": ax["name"], "unit": U.axis_unit(book, ax), "kind": ax["kind"],
                     "paths": list(ax["paths"]), **U.axis_print(book, ax),
                     "dist": ax["dist"], "price_low": None, "price_high": None, "swing": None,
                     "mean_shift": None,
                     "share": None if c is None else c["share"], "rank_corr": None if c is None else c["rank_corr"],
                     "in_band": in_band, "source": U.judgement_source(book, ax, notes),
                     "status": "not_computed", "reason": reason})
    return rows


# ------------------------------------------------------------------ инварианты уровня выпуска


def exdate_finding(book: Book, facts: Facts, live: LiveInputs, run: GridRun) -> Finding:
    """exdate_jump (М§14.1, §8.4): для последней записи реестра — скачок цены на экс-дату = −DPS × N_out / N_div:
    с баланса уходит DPS на акции в обращении, а делится он на делитель (без ключей делителя — −DPS)."""
    tol = float(book.get("checks.exdate_jump_tol"))
    recs = [r for r in live.register if r.status in ("declared", "paid") and r.ex is not None]
    tl = run.ctx.timeline
    cal = run.ctx.prep.calendar
    quarterly = cal is not None
    synthetic = not recs
    if recs:
        rec = recs[-1]
        v = rec.ex
    elif quarterly:
        # синтетическая запись — за ближайший открытый квартал прибыли без записи (М§14.1)
        slot = next((o for o in cal.open if o.dps is None), None) or (cal.open[0] if cal.open else None)
        if slot is None:
            return Finding(name="exdate_jump", kind="invariant", fired=True, mass=None, cells=(),
                           message="проверка не выполнена: в сетке нет открытого квартала прибыли", detail={})
        v = tl.end(slot.q) + timedelta(days=20)
        cell_dps = [c.dps_q[slot.period] for c in run.cells]
        dps = sum(cell_dps) / len(cell_dps) if cell_dps and sum(cell_dps) > 0 else 1.0
        rec = DividendRecord(year=slot.year, dps=dps, status="declared", record_date=v,
                             last_buy_date=v - timedelta(days=1), ex_date=v, pay_date=v + timedelta(days=15),
                             sources=("синтетическая запись проверки",), period=slot.period)
    else:
        year = tl.anchor_year
        agm_q = tl.index(period_str(year + 1, int(book.get("dividends.calendar.agm_quarter"))))
        v = tl.end(agm_q) + timedelta(days=20)
        cell_dps = [c.dps.get(year) for c in run.cells if c.dps.get(year) is not None]
        dps = sum(cell_dps) / len(cell_dps) if cell_dps else 1.0
        rec = DividendRecord(year=year, dps=dps, status="declared", record_date=v, last_buy_date=v - timedelta(days=1),
                             ex_date=v, pay_date=v + timedelta(days=15), sources=("синтетическая запись проверки",))

    def shifted(days: int) -> DividendRecord:
        ex = rec.ex + timedelta(days=days)
        return DividendRecord(year=rec.year, dps=rec.dps, status=rec.status, record_date=ex,
                              last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=rec.pay_date,
                              sources=rec.sources, period=rec.period, label=rec.label, decided_date=rec.decided_date)

    # прочие записи — записи с другим ключом (год прибыли; при квартальном календаре — квартал прибыли)
    others = tuple(r for r in live.register if record_key(r, quarterly) != record_key(rec, quarterly))

    def at(r: DividendRecord) -> float:
        lv = LiveInputs(valuation_date=v, prices=dict(live.prices), price_dates=dict(live.price_dates),
                        register=tuple(sorted(others + (r,), key=lambda x: (x.year, x.period or ""))))
        return run_grid(book, facts, lv, summary=True).point

    expected = rec.dps * (run.shares_out / run.divisor)        # на акцию оценки; без ключей делителя — DPS
    try:
        jump = at(shifted(0)) - at(shifted(1))
        ok = abs(jump + expected) <= tol * expected
        who = "синтетическая запись" if synthetic else book.label(
            "register.record_words", **record_fields(book, rec.year, rec.period, rec.label))
        msg = (f"{who}: скачок на экс-дату {_rub(jump)} ₽ при дивиденде на акцию {_rub(rec.dps)} ₽ "
               f"(допуск — {pct(tol)} дивиденда)")
        if run.divisor != run.shares_out:
            msg += (f"; на акцию оценки — {_rub(expected)} ₽: дивиденд уходит на {_mln(run.shares_out)} млн акций "
                    f"в обращении, оценка делится на {_mln(run.divisor)} млн")
    except (BookError, FactsError, ValueError, KeyError) as exc:
        ok, jump, msg = False, None, f"проверка не выполнена: {exc}"
    return Finding(name="exdate_jump", kind="invariant", fired=not ok, mass=None, cells=(), message=msg,
                   detail={"jump": jump, "dps": rec.dps, "expected": expected, "synthetic": synthetic})


def release_findings(payload: Mapping[str, Any]) -> Finding:
    """release_numbers (М§14.1): конечность, печать ROUND_HALF_UP, P10 ≤ медиана ≤ P90 ≤ потолок, точка на оси."""
    bad = _finite_problems(payload)[:3]
    fv = payload["fair_value"]
    h = fv["headline"]
    step = float(h["print_step"])
    c = _centres(h, float(h["own_macro_confidence"]))
    lv = sorted(float(q) for q in h["quantiles"])
    median = _q7(c, lv[2])
    if h["printed_median"] != U.round_half_up(median, step):
        bad.append("печать медианы")
    price = payload["market"]["price"]
    if not 0 <= _q7(c, lv[0]) <= median <= _q7(c, lv[-1]) <= float(h["ceiling_x_market"]) * price:
        bad.append("нарушено 0 ≤ P10 ≤ медиана ≤ P90 ≤ потолок")
    lam = float(fv["own_macro_confidence"])
    if not _close(fv["central"], fv["low"] + lam * (fv["high"] - fv["low"]), TOL_POINT):
        bad.append("точка ≠ низ + λ (верх − низ)")
    return Finding("release_numbers", "invariant", bool(bad), None, (),
                   "; ".join(bad) if bad else "числа конечны, печать и полосы согласованы", {})


# ------------------------------------------------------------------ помощники


RATIO_CAPITAL = {"n20": "k20", "n11": "k11"}      # норматив → его капитал в рядах клетки


class _Ctx:
    """Общее для блоков выпуска: книга, прогон, вероятности слоёв и смеси заголовка."""

    def __init__(self, rel: Release):
        self.rel = rel
        self.book, self.facts, self.run, self.band = rel.book, rel.facts, rel.run, rel.band
        self.live = rel.live
        self.tl = rel.run.ctx.timeline
        self.prep = rel.run.ctx.prep
        self.af = self.prep.af
        self.br = rel.run.ctx.bridge
        self.lam = rel.run.lam
        self.company = self.book.get("meta.company")
        self.tickers = [str(t) for t in self.company["tickers"]]
        self.main = str(self.company["main_ticker"])
        self.prices = {t: float(self.live.prices[t]) for t in self.tickers if t in self.live.prices}
        self.v = self.live.valuation_date
        self.n_out, self.n_iss = self.af.n_out, self.af.n_iss
        self.n_div = rel.run.divisor                 # делитель «на акцию» (М§8.4); без ключей книги — N_out
        self.per_div = self.n_out / self.n_div       # DPS → ₽ на акцию оценки; без ключей — ровно 1
        self.issued_basis = self.book.opt("valuation.shares_basis") == SHARES_ISSUED
        self.p_an = rel.run.layers["analytical"].prob
        self.p_neu = rel.run.layers["macro_neutral"].prob
        self.p_mi = rel.run.layers["market_implied"].prob
        self.p_mix = {k: self.lam * self.p_an[k] + (1 - self.lam) * self.p_neu[k] for k in self.p_an}
        self.years = list(range(self.tl.anchor_year, self.tl.last_year + 1))
        self.worlds = [str(w) for w in self.book.get("worlds.ids")]
        self.regimes = [str(r) for r in self.book.get("regimes.ids")]
        self.scenarios = [str(s) for s in self.book.get("capital.reg_scenarios.ids")]
        self.cap = market_cap(rel.run)
        self.bl = bank_language(rel.run, self.lam)
        self.shares_by_ticker = self._shares_by_ticker()
        self.cal = self.prep.calendar                # квартальный календарь дивидендов (М§5.7); None — годовой
        self._by_period: dict = {}

    def decision(self, cell: Any, period: str) -> Any:
        """Решение клетки за квартал прибыли (квартальный календарь)."""
        if not self._by_period:
            self._by_period = {c.key: {d.period: d for d in c.decisions} for c in self.run.cells}
        return self._by_period[cell.key][period]

    def _shares_by_ticker(self) -> dict[str, dict]:
        """Акции по тикеру: класс — ключ книги `meta.company.share_classes.<t>` (М§8.3), не порядок тикеров."""
        classes = self.book.get("meta.company.share_classes")
        out = {}
        for t in self.tickers:
            cls = str(classes[t])
            out[t] = {"class": cls, "issued_mln": self.fv("shares", f"issued_{cls}"),
                      "treasury_mln": self.fv("shares", f"treasury_{cls}"),
                      "outstanding_mln": self.fv("shares", f"outstanding_{cls}")}
        return out

    def E(self, prob: Mapping, name: str, q: int) -> float | None:
        return expect(self.run, prob, name, q)

    def ratio(self, prob: Mapping, key: str, q: int) -> float | None:
        """Норматив смеси в определении движка (П§2 capital): E[K]/E[RWA] + A, где
        A = Σ p_c × (N_c − K_c/RWA_c) — ожидание аддитивного слагаемого клеток (поправка «норматив −
        расчёт» минус вычеты сценария, М§4.11) под теми же весами. `key` — "n20" | "n11"."""
        parts = self.ratio_parts(prob, key, q)
        return None if parts is None else parts[0] + parts[1]

    def ratio_parts(self, prob: Mapping, key: str, q: int) -> tuple[float, float] | None:
        """(E[K]/E[RWA], A) норматива смеси; None — нет числа хотя бы у одной клетки."""
        num = RATIO_CAPITAL[key]
        k = rwa = add = 0.0
        for c in self.run.cells:
            n, kc, rc = c.quarters[key][q], c.quarters[num][q], c.quarters["rwa"][q]
            if n is None or kc is None or not rc:
                return None
            w = prob[c.key]
            k, rwa, add = k + w * float(kc), rwa + w * float(rc), add + w * (float(n) - float(kc) / float(rc))
        return (k / rwa, add) if rwa else None

    def flow(self, prob: Mapping, name: str, year: int) -> float | None:
        """Сумма строки за год: факт отчётных кварталов (q ≤ 0) + ожидание по вероятностям."""
        return year_flow(self.run, prob, name, year)

    def end(self, prob: Mapping, name: str, q: int) -> float | None:
        v = quarter_end(self.run, prob, name, q)
        if v is None and name == "assets" and q <= 0:        # всего активов до сетки — строкой баланса фактов
            v = self.fv("balance", "total_assets" if q == 0 else f"history.{self.tl.period(q)}.total_assets")
        return v

    def wquantile(self, pairs: Sequence[tuple[float | None, float]], q: float) -> float | None:
        pairs = sorted((x, w) for x, w in pairs if x is not None and w > 0)
        if not pairs:
            return None
        tot = sum(w for _, w in pairs)
        acc = 0.0
        for x, w in pairs:
            acc += w
            if acc >= q * tot - 1e-12:
                return x
        return pairs[-1][0]

    def fv(self, file: str, path: str) -> float | None:
        try:
            return self.facts.v(file, path)
        except (FactsError, KeyError):
            return None

    def plain(self, file: str, path: str) -> Any:
        try:
            return get_path(self.facts.file(file), path)
        except (BookError, FactsError, KeyError):
            return None


def _half_year_rows(traj: Mapping[str, float], years: Sequence[int]) -> list[dict]:
    out = []
    for y in years:
        vals = [float(x) for k, x in traj.items() if str(k).startswith(str(y))]
        if vals:
            out.append({"year": y, "value": R_SHARE(sum(vals) / len(vals))})
    return out


def _year_rows(table: Mapping[str, float] | None, years: Sequence[int] | None = None) -> list[dict]:
    out = []
    for k, x in (table or {}).items():
        if str(k).isdigit() and (years is None or int(k) in years):
            out.append({"year": int(k), "value": R_SHARE(float(x))})
    return sorted(out, key=lambda r: r["year"])


def _iso(x: Any) -> str | None:
    if x is None:
        return None
    if isinstance(x, (date, datetime)):
        return x.isoformat()[:10]
    return str(x)[:10]


def _node_v(x: Any) -> Any:
    return x.get("v") if isinstance(x, Mapping) and "v" in x else x


def _ru_date(x: Any) -> str | None:
    """Дата для текста экрана — с годом: «30.09.2026» (П§0.2)."""
    iso = _iso(x)
    if not iso or not DATE_RE.match(iso):
        return iso
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


SHA_TAIL = re.compile(r",?\s*sha256\s+([0-9a-f]{8,})…?")
PAGE_RE = re.compile(r"с\.\s?\d+(?:[–-]\d+)?")


def _src_words(facts: Facts, text: Any) -> str | None:
    """Источник словами для экрана (П§0.2): вместо имени файла и хвоста sha256 — название документа из
    реестра фактов (`anchor.json → documents[]`, поиск по началу sha256) со страницей; документа в реестре
    нет — строка без хвоста хэша (хэш — только в карточке «Выпуск и книга»)."""
    if text is None:
        return None
    docs = facts.files.get("anchor", {}).get("documents") or []
    out = []
    for item in str(text).split(";"):
        m = SHA_TAIL.search(item)
        title = None
        if m:
            title = next((str(d.get("title")) for d in docs if isinstance(d, Mapping) and d.get("title")
                          and str(d.get("sha256") or "").startswith(m.group(1))), None)
        if title:
            page = PAGE_RE.search(item)
            out.append(title + (f", {page.group(0)}" if page else ""))
        else:
            out.append(SHA_TAIL.sub("", item).strip())
    return "; ".join(x for x in out if x)


# Коды единиц строк выпуска (словарь витрины: pct/share — доля, pp — сдвиг, bn — млрд ₽, rub — ₽,
# number — число, mix — доля смеси, dict — словарь долей, count — штуки, version — как есть,
# date — дата YYYY-MM-DD, period — период, печатается подписью периода).
# Словари `UNIT_CODES` и `UNIT_WORDS` живут в схеме книги (`model/book_schema.py`): единицу оси задаёт книга.
BN_FROM = 10.0                   # значение от 10 по модулю в строке без единицы — деньги, млрд ₽


def unit_code(unit: Any, *, kind: str | None = None, values: Sequence[Any] = ()) -> str:
    """Код единицы строки: слово книги → код; «» книги — число (или млрд ₽); нет слова (None) —
    по виду оси и величине значений."""
    u = None if unit is None else str(unit)
    if u in UNIT_CODES:
        return u
    if kind == "mix":
        return "mix"
    if kind == "dict" or any(isinstance(v, Mapping) for v in values):
        return "dict"
    if kind == "shift":
        return "pp"
    if any(isinstance(v, str) for v in values):
        return "version"
    nums = [abs(float(v)) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    top = max(nums) if nums else 0.0
    if u == "":
        return "bn" if top >= BN_FROM else "number"
    if u in UNIT_WORDS:
        return UNIT_WORDS[u]
    return "bn" if top >= BN_FROM else ("number" if top > 1 else "pct")


BANK_UNIT_CODES = {"implied_roe_through_cycle": "pct", "implied_cost_of_equity": "pct", "market_cap_minus_bv": "bn"}


def _coded(reverse: Mapping | None, judgements: Sequence[Mapping] | None) -> tuple[dict, list]:
    """Строки обратного расчёта и суждений с кодами единиц витрины."""
    rev = copy.deepcopy(dict(reverse or {}))
    for r in rev.get("rows") or []:
        r["unit"] = unit_code(r.get("unit"), kind=r.get("kind"), values=[r.get("book"), *(r.get("range") or [])])
    for r in rev.get("bank_rows") or []:
        r["unit"] = BANK_UNIT_CODES.get(r.get("key"), unit_code(r.get("unit")))
    rows = copy.deepcopy(list(judgements or []))
    for r in rows:
        r["unit"] = unit_code(r.get("unit"), kind=r.get("kind"), values=[r.get("book"), r.get("low"), r.get("high")])
    return rev, rows


# ------------------------------------------------------------------ meta, market


def _shares_extra(x: _Ctx) -> dict:
    """Необязательные поля `meta.shares` (П§2): делитель — при ключах делителя книги; блок депозитарных программ,
    экономически собственные акции и корпоративные события — при узлах фактов."""
    b, out = x.book, {}
    if b.opt("valuation.shares_basis") is not None or b.opt("valuation.share_count_adj") is not None:
        out.update(divisor_mln=rnd(x.n_div, PRECISION["shares"]),
                   divisor_basis=str(b.opt("valuation.shares_basis", "outstanding")),
                   divisor_label=b.label("basis.divisor"))
    for field_, node in (("depositary_block_mln", "depositary_block"), ("economic_treasury_mln", "economic_treasury"),
                         ("dividend_eligible_mln", "dividend_eligible")):
        value = x.fv("shares", node)
        if value is not None:
            out[field_] = rnd(value, PRECISION["shares"])
    actions = x.facts.file("shares").get("corporate_actions")
    if actions:
        out["corporate_actions"] = [
            {"date": _iso(a.get("date")), "kind": a.get("kind"), "title": a.get("title"),
             **({"factor": _node_v(a["factor"])} if _node_v(a.get("factor")) is not None else {})} for a in actions]
    return out


# Подписи базы суммы дивиденда (`meta.labels.basis`, необязательные): пул — на все размещённые акции, отток
# из капитала группы — на акции в обращении. Обе есть в книге — выпуск несёт коды базы `amount_basis`.
AMOUNT_BASIS_LABELS = ("dividend_issued", "dividend_outstanding")
AMOUNT_ISSUED, AMOUNT_OUTSTANDING = "issued", "outstanding"
FREQUENCIES = ("annual", "quarterly")             # частота выплат политики (П§2 `dividends.policy.frequency`)


def _amount_basis(book: Book) -> bool:
    """Несёт ли выпуск коды базы суммы дивиденда: в книге есть обе подписи базы."""
    return all(book.opt(f"meta.labels.basis.{k}") is not None for k in AMOUNT_BASIS_LABELS)


def _terms(book: Book) -> dict[str, str]:
    """Словарь терминов книги для витрины (П§2 `meta.terms`): все ключи `meta.labels.terms` книги и имя строки
    вне основного бизнеса (`noncore`: термин книги, без него — подпись строки сводки контрольной модели)."""
    terms = {str(k): str(v) for k, v in book.get("meta.labels.terms").items()}
    terms.setdefault("noncore", book.label("control.lines.noncore"))
    return terms


def _meta(x: _Ctx) -> dict:
    rel, b = x.rel, x.book
    clock = x.run.ctx.clock
    shares_as_of = x.plain("shares", "as_of")
    return {
        "generated_at": rel.generated_at, "valuation_date": x.v.isoformat(),
        "facts_date": _iso(b.get("meta.facts_date")), "book_version": str(b.get("meta.version")),
        "book_date": _iso(b.get("meta.date")), "book_tag": f"book-{b.get('meta.version')}",
        "engine_commit": rel.engine_commit, "fast": bool(rel.fast), "payload_sha256": None,
        "previous_sha256": ((rel.previous or {}).get("meta") or {}).get("payload_sha256"), "bytes": 0,
        "company": {"name": str(x.company["name"]), "tickers": list(x.tickers), "main_ticker": x.main,
                    "share_classes": [{"ticker": t, "class": x.shares_by_ticker[t]["class"]} for t in x.tickers],
                    "cbr_regnum": x.company["cbr_regnum"], "fiscal_year_end": str(x.company["fiscal_year_end"])},
        "shares": {"issued_mln": rnd(x.n_iss, PRECISION["shares"]), "outstanding_mln": rnd(x.n_out, PRECISION["shares"]),
                   "by_ticker": {t: {k: rnd(v, PRECISION["shares"]) for k, v in row.items() if k != "class"}
                                 for t, row in x.shares_by_ticker.items()},
                   "as_of": _iso(shares_as_of), "src": "отчётность МСФО и данные Московской биржи (факты книги)",
                   **_shares_extra(x)},
        "basis_labels": {**{k: b.label(f"basis.{k}") for k in ("profit", "roe", "divisor")},
                         **({k: b.label(f"basis.{k}") for k in AMOUNT_BASIS_LABELS} if _amount_basis(b) else {})},
        "terms": _terms(b),                          # термины книги: витрина своих слов не держит
        "period_unit": "quarter", "input_unit": "month",
        "anchor_period": str(b.get("meta.anchor_period")), "first_period": str(b.get("meta.first_period")),
        "last_period": str(b.get("meta.last_period")),
        "horizon": [str(b.get("meta.first_period")), str(b.get("meta.last_period"))],
        "open_period": x.tl.period(clock.q0), "periods_closed": clock.q0 - 1, "elapsed": R_SHARE(clock.elapsed),
        "book_first_period_closed": x.tl.end(1) <= x.v, "curve_as_of": _iso(b.get("meta.curve_as_of")),
        "basis": "ifrs", "step": "quarter", "day_count": "act365", "governance_discount": x.run.governance,
    }


def _ltm(x: _Ctx) -> dict:
    """ЧП акционерам за 4 отчётных квартала и ROE (к среднему пяти концов BV)."""
    qs = [0, -1, -2, -3]
    ni = [x.prep.hist["ni_sh"].get(q) for q in qs]
    bvs = [x.end(x.p_an, "bv", q) for q in (0, -1, -2, -3, -4)]
    bvs = [v for v in bvs if v is not None]
    ni_sum = None if any(v is None for v in ni) else sum(ni)
    roe = None if ni_sum is None or not bvs else ni_sum / (sum(bvs) / len(bvs))
    return {"as_of": _iso(x.af.as_of), "ni_sh": R_MONEY(ni_sum), "roe": R_SHARE(roe), "basis": "ifrs"}


def _roe_issuer(x: _Ctx) -> dict | None:
    """ROE эмитента за четыре квартала по якорь (П§2 `history.ltm.roe_issuer`): операционная прибыль четырёх
    кварталов к среднему операционного капитала пяти концов кварталов (`facts/mgmt_quarterly.json`); точное
    значение (`*_exact`), а где его ещё нет — напечатанное. Нет любого из девяти чисел — узла нет."""
    if "mgmt_quarterly" not in x.facts.files:
        return None
    rows = x.facts.file("mgmt_quarterly").get("quarters") or {}

    def pick(q: int, name: str) -> float | None:
        row = rows.get(x.tl.period(q)) or {}
        exact = _node_v(row.get(f"{name}_exact"))
        return exact if exact is not None else _node_v(row.get(name))

    profit = [pick(q, "op_np") for q in (0, -1, -2, -3)]
    equity = [pick(q, "op_equity") for q in (0, -1, -2, -3, -4)]
    if None in profit or None in equity:
        return None
    return {"value": R_SHARE(sum(profit) / (sum(equity) / len(equity))), "as_of": _iso(x.af.as_of),
            "label": x.book.label("basis.roe_issuer")}


def _record_id(r: Mapping[str, Any]) -> Any:
    """Ключ записи в выпуске: квартал прибыли, а у записи без него — год прибыли (П§2 `dividends`)."""
    return r.get("period") or int(r["year"])


_ONE_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _history_year(r: Mapping[str, Any]) -> int:
    """Год строки истории дивидендов: число; у строк до IPO (`history_before`) год бывает меткой — «2023-interim»,
    «2021» строкой: год — её первые четыре цифры, смысл строки несёт `label`."""
    y = r.get("year")
    if isinstance(y, int) and not isinstance(y, bool):
        return y
    m = re.match(r"\s*(\d{4})", str(y))
    if m is None:
        raise FactsError(f"dividends: год строки истории {y!r} — не год")
    return int(m.group(1))


def _one_day(x: Any) -> str | None:
    """Дата строки истории: один день ISO. Несколько дат через «|» (выплаты до IPO в несколько решений) или год без
    дня — пусто: такая строка несёт слова `label`, а не дату."""
    if x is None or isinstance(x, (date, datetime)):
        return _iso(x)
    s = str(x).strip()
    return s[:10] if "|" not in s and _ONE_DAY.fullmatch(s[:10]) else None


def _period_words(r: Mapping[str, Any]) -> dict[str, str]:
    """Необязательные поля записи: квартал прибыли и слова решения — только у записи, которая их несёт."""
    return {k: str(r[k]) for k in ("period", "label") if r.get(k)}


def _dividend_events(x: _Ctx) -> list[dict]:
    """Выплаты с экс-датой: история фактов и реестр (год прибыли, DPS, экс-дата; квартал прибыли и слова
    решения — у записи, которая их несёт). Запись — по кварталу прибыли, а без него — по году: решения одного
    года при квартальном календаре в одно не сворачиваются."""
    out = {}
    for r in x.facts.file("dividends").get("history") or []:
        ex = r.get("ex_date") or r.get("record_date")
        out[_record_id(r)] = {"year": int(r["year"]), "date": _iso(ex), "dps": float(history_dps(r)),
                              "dps_preferred": _node_v(r.get("dps_preferred")), **_period_words(r)}
    for r in x.rel.live_report.records:
        if r.get("status") in ("declared", "paid") and (r.get("ex_date") or r.get("record_date")):
            out[_record_id(r)] = {"year": int(r["year"]), "date": _iso(r.get("ex_date") or r.get("record_date")),
                                  "dps": float(r["dps"]), "dps_preferred": float(r["dps"]), **_period_words(r)}
    return sorted(out.values(), key=lambda r: r["date"] or "")


YIELD_QUARTERS = 4                # дивдоходность за 12 месяцев при квартальном календаре — четыре квартала прибыли


def _declared_quarters(x: _Ctx) -> tuple[list[str], list[dict]] | None:
    """Четыре последних объявленных квартала прибыли (квартальный календарь; П§2 `dividends.yield_ltm`): окно
    из четырёх кварталов прибыли, которое кончается самым поздним кварталом с решением (строка истории или
    запись реестра `declared` | `paid`), и решения, попавшие в окно. Квартал окна без своей строки покрыт
    решением более позднего квартала и даёт ноль. История решений короче окна — None."""
    by_idx = {x.tl.index(str(e["period"])): e for e in _dividend_events(x) if e.get("period")}
    if not by_idx or min(by_idx) > max(by_idx) - (YIELD_QUARTERS - 1):
        return None
    window = range(max(by_idx) - (YIELD_QUARTERS - 1), max(by_idx) + 1)
    return [x.tl.period(i) for i in window], [by_idx[i] for i in window if i in by_idx]


def _yield_ltm(x: _Ctx) -> dict[str, float | None]:
    """Дивидендная доходность за 12 месяцев: при годовом календаре — DPS с экс-датой за 365 дней до даты
    оценки к цене; при квартальном — сумма DPS четырёх последних объявленных кварталов прибыли к цене (окно по
    экс-датам у квартального плательщика то теряет выплату, то прыгает на экс-дате)."""
    if x.cal is not None:
        got = _declared_quarters(x)
        if got is None:
            return {t: None for t in x.tickers}
        ev = got[1]
    else:
        start = x.v - timedelta(days=365)
        ev = [e for e in _dividend_events(x) if e["date"] and start < date.fromisoformat(e["date"]) <= x.v]
    out = {}
    for t in x.tickers:
        pref = x.shares_by_ticker[t]["class"] == "preferred"
        total = sum(float(e["dps_preferred"] if pref and e.get("dps_preferred") is not None else e["dps"]) for e in ev)
        out[t] = R_SHARE(total / x.prices[t]) if x.prices.get(t) else None
    return out


SRC_MAX = 120                    # знаков источника строки аналога (П§2 `market.peers.rows[].src`)


def _clip_words(text: str, limit: int) -> str:
    """Строка не длиннее `limit` знаков: длинная обрезается по границе слова с многоточием — слово и название
    документа не рвутся посередине; короткая — как есть."""
    if len(text) <= limit:
        return text
    head = text[:limit - 1]
    cut = head.rfind(" ")
    return (head[:cut] if cut > 0 else head).rstrip(" ,;:(«") + "…"


def _thin(items: list, limit: int) -> list:
    if len(items) <= limit:
        return items
    step = (len(items) - 1) / (limit - 1)
    idx = sorted({round(i * step) for i in range(limit)})
    return [items[i] for i in idx]


def _peers(x: _Ctx, bv: float, ni_ltm: float | None, roe_ltm: float | None, yields: Mapping) -> dict:
    f = x.facts.file("peers") if "peers" in x.facts.files else {}
    words = {"tinvest": "T-Invest", "iss": "Мосбиржа, TQBR"}
    rows = [{
        "ticker": x.main, "name": str(x.company["name"]), "price": R_PRICE(x.prices.get(x.main)),
        "price_date": _iso(x.live.price_dates.get(x.main)), "cap": R_MONEY(x.cap), "bv": R_MONEY(bv),
        "bv_date": _iso(x.af.as_of), "ni_ltm": R_MONEY(ni_ltm),
        "pb": R_MULT(None if x.cap is None else x.cap / bv), "pe": R_MULT(None if not ni_ltm or x.cap is None
                                                                         else x.cap / ni_ltm),
        "roe_ltm": R_SHARE(roe_ltm), "dividend_yield": yields.get(x.main),
        "capital_ratio": {"name": x.book.label("capital.n20_short"), "value": x.fv("capital", "n20_0.value"),
                          "as_of": _iso(x.plain("capital", "n20_0.as_of"))},
        "basis": x.book.label("peers.subject_basis"),
        "src": "факты книги (баланс, ОПУ по кварталам, капитал) и живая цена",
        "status": "live",
        "reason": None}]
    peer_prices = getattr(x.rel.indicators, "peer_prices", None) or {}
    for bnk in f.get("banks") or []:
        t = str(bnk.get("ticker"))
        pp = peer_prices.get(t)
        shares = _node_v(bnk.get("shares_outstanding"))
        pbv, pni, pdps = _node_v(bnk.get("bv")), _node_v(bnk.get("ni_ltm")), _node_v(bnk.get("dps_ltm"))
        price = None if pp is None else float(pp.price)
        cap = None if price is None or shares is None else price * float(shares) / 1000
        roe = _node_v(bnk.get("roe_ltm"))
        if roe is None and pni is not None and pbv:
            roe = float(pni) / float(pbv)
        cr = bnk.get("capital_ratio") or {}
        rows.append({
            "ticker": t, "name": bnk.get("name"), "price": R_PRICE(price),
            "price_date": None if pp is None else pp.date, "cap": R_MONEY(cap), "bv": R_MONEY(pbv),
            "bv_date": _iso(bnk.get("bv_date")), "ni_ltm": R_MONEY(pni),
            "pb": R_MULT(None if cap is None or not pbv else cap / float(pbv)),
            "pe": R_MULT(None if cap is None or not pni else cap / float(pni)), "roe_ltm": R_SHARE(roe),
            "dividend_yield": R_SHARE(None if price is None or pdps is None else float(pdps) / price),
            "capital_ratio": {"name": cr.get("name"), "value": _node_v(cr.get("value")), "as_of": _iso(cr.get("as_of"))},
            "basis": bnk.get("basis"), "src": _clip_words(_src_words(x.facts, bnk.get("src")) or "", SRC_MAX),
            "status": "live" if pp is not None else "missing",
            "reason": None if pp is not None else "нет живой цены аналога (сборщики)"})
        if pp is not None:
            rows[-1]["source"] = words.get(pp.source, pp.source)
    return {"as_of": _iso(f.get("as_of")), "basis": f.get("basis"), "subject_ticker": x.main, "rows": rows}


def _market(x: _Ctx, pe_fwd_ni: float | None, next_yield: Mapping) -> dict:
    rep = x.rel.live_report
    words = {"tinvest": "T-Invest", "iss": "Мосбиржа, TQBR", "book": "книга"}
    prices = {}
    for t in x.tickers:
        r = rep.prices.get(t) or {}
        prices[t] = {"price": R_MARKET(x.prices[t]), "date": _iso(r.get("date")) or _iso(x.live.price_dates.get(t)),
                     "time": r.get("time"), "source": words.get(r.get("source"), r.get("source")),
                     "status": r.get("status", "book"), "book_price": r.get("book_price")}
    if x.issued_basis:                          # один тикер, одно число: цена × делитель (М§8.3)
        cap_by = {t: R_MONEY(x.prices[t] * x.n_div / 1000) for t in x.tickers}
    else:
        cap_by = {t: R_MONEY(x.prices[t] * float(x.shares_by_ticker[t]["outstanding_mln"]) / 1000)
                  for t in x.tickers}
    ltm = _ltm(x)
    bv_rep = x.af.bv
    yields = _yield_ltm(x)
    hist = getattr(x.rel.indicators, "price_history", None) or {}
    ph, pmin, pmax = {}, {}, {}
    for t in x.tickers:
        items = [(d, float(v)) for d, v in hist.get(t, ())]
        ph[t] = [{"date": d, "close": R_PRICE(v)} for d, v in _thin(items, PRICE_HISTORY_POINTS)]
        pmin[t] = None if not items else dict(zip(("date", "close"), min(items, key=lambda z: z[1])))
        pmax[t] = None if not items else dict(zip(("date", "close"), max(items, key=lambda z: z[1])))
    start = x.v - timedelta(days=365)
    ex_div = [{"date": e["date"], "dps": e["dps"], "year": e["year"], **_period_words(e)} for e in _dividend_events(x)
              if e["date"] and start < date.fromisoformat(e["date"]) <= x.v]
    brokers = getattr(x.rel.indicators, "brokers", None)
    b_block = {k: (brokers or {}).get(k) for k in ("as_of", "source", "n", "median", "min", "max", "recommendations")}
    if brokers and brokers.get("history"):
        b_block["history"] = list(brokers["history"])[-60:]
    return {
        "price": R_MARKET(x.prices[x.main]), "price_date": prices[x.main]["date"], "prices": prices,
        "cap": R_MONEY(x.cap), "cap_by_ticker": cap_by,
        "multiples": {"pb": R_MULT(None if x.cap is None else x.cap / x.bl["bv_v"]),
                      "pb_reported": R_MULT(None if x.cap is None else x.cap / bv_rep),
                      "pe_ltm": R_MULT(None if x.cap is None or not ltm["ni_sh"] else x.cap / ltm["ni_sh"]),
                      "pe_fwd": R_MULT(None if x.cap is None or not pe_fwd_ni else x.cap / pe_fwd_ni),
                      "dividend_yield_ltm": yields, "dividend_yield_fwd": dict(next_yield),
                      "bv_per_share": R_PRICE(x.bl["bv_v"] * 1000 / x.n_div), "basis": "ifrs"},
        "price_history": ph, "price_min": pmin, "price_max": pmax, "ex_dividend": ex_div,
        "peers": _peers(x, bv_rep, ltm["ni_sh"], ltm["roe"], yields), "brokers": b_block,
    }


# ------------------------------------------------------------------ fair_value, layers


def _lambda_grid(lam_book: float) -> list[float]:
    grid = [round(i / LAMBDA_STEPS, 10) for i in range(LAMBDA_STEPS + 1)]
    if all(abs(g - lam_book) > EPS for g in grid):
        grid = sorted(grid + [lam_book])
    return grid


def quantile_grain(draw_step: float) -> float:
    """Хранимая точность квантилей и среднего полосы (П§0.3): шаг цены 0,01 ₽, а при прогонах мельче шага по
    умолчанию (ключ книги `valuation.uncertainty.draw_step`, М4) — десятая шага хранения. Медиана чётного числа
    прогонов — полусумма двух, и на шаге 0,01 ₽ она ложится на 0,005: хранение с шагом 0,01 теряло бы половину
    шага, и validate не воспроизводил бы её из прогонов (допуск 0,005)."""
    return PRECISION["price"] if draw_step >= PRECISION["draw"] - EPS else min(PRECISION["price"], draw_step / 10)


def _headline_row(band: U.Band, lam: float, prices: Mapping[str, float], main: str) -> dict:
    h = band.headline(lam, prices, main)
    grain = quantile_grain(float(band.draw_step))
    R_Q = lambda v: rnd(v, grain)  # noqa: E731
    return {"median": R_Q(h["median"]), "p10": R_Q(h["p10"]), "p25": R_Q(h["p25"]),
            "p75": R_Q(h["p75"]), "p90": R_Q(h["p90"]), "mean": R_Q(h["mean"]),
            "p_below_market": R_PROB(h["p_below_market"]),
            "p_below_by_ticker": {t: R_PROB(v) for t, v in h["p_below_by_ticker"].items()},
            "market_percentile": R_PROB(h["market_percentile"]),
            "upside": {t: R_SHARE(v) for t, v in h["upside"].items()}, "_exact": h}


def _sens_at(x: _Ctx, lam: float) -> dict[str, float | None]:
    s = x.rel.sensitivities
    with_buffer = x.book.opt("valuation.sensitivities.buffer_pp") is not None
    if not s or x.rel.anchor is None:
        return {"rub_per_1pp_roe": None, "rub_per_01pp_cor": None, "rub_per_01pp_nim": None,
                **({"rub_per_1pp_buffer": None} if with_buffer else {})}
    base = x.rel.anchor.base.exact_centres(lam)
    window = U.rank_window(x.book)
    # сдвиг медианы — оценщиком срединных прогонов (М§10), а не разностью двух медиан
    shift = {kind: U.median_shift(base, s[kind]["band"].exact_centres(lam), window) for kind in ("cor", "nim")}
    out = {kind: shift[kind] * PP01 / s[kind]["step"] for kind in ("cor", "nim")}
    d_roe = bank_language(s["nim"]["run"], lam)["roe_tc"] - bank_language(x.run, lam)["roe_tc"]
    roe = None if not d_roe else shift["nim"] / d_roe * s["roe_pp"]
    row = {"rub_per_1pp_roe": R_PRICE(roe), "rub_per_01pp_cor": R_PRICE(out["cor"]),
           "rub_per_01pp_nim": R_PRICE(out["nim"])}
    if with_buffer:                             # сдвиг медианы на 1 п.п. запаса менеджмента над минимумом
        b = s.get("buffer")
        row["rub_per_1pp_buffer"] = None if b is None else R_PRICE(
            U.median_shift(base, b["band"].exact_centres(lam), window) * PP1 / b["step"])
    return row


def _buffer_words(book: Book) -> str:
    """Слова о строке «₽ за 1 п.п. запаса капитала» в подписи чувствительностей — только при ключе книги."""
    step = book.opt("valuation.sensitivities.buffer_pp")
    if step is None:
        return ""
    return (f"; запас капитала: запас менеджмента над минимумом обоих нормативов сдвинут на "
            f"{pct(float(step))[:-2]} п.п., строка — на 1 п.п.")


def _nim_shift_words(x: _Ctx) -> str:
    """Что сдвинуто в строке «₽ за 0,1 п.п. ЧПМ» (П§2 `sensitivity_basis`, М§8.3). Без ключей книги — прежние
    слова. У книги с суждением о марже, которое печатается не ключом (`checks.nim_stationary` — стационарная
    маржа мира-цели; `checks.nim_lt` — печатаемая маржа модальной клетки), сдвинут ключ цели, и рядом названо,
    на сколько при этом меняется само суждение (сетка сдвинутой книги уже посчитана; в быстрой сборке — без
    числа). У книги с ключом уровня `nii.transmission.level_world` ключ цели и есть суждение — стационарная
    маржа названного мира: слова называют мир."""
    b = x.book
    step = f"{pct(float(b.get('valuation.sensitivities.nim_pp')))[:-2]} п.п."
    level = b.label("terms.lt_level")
    stationary, printed = b.opt(NIM_STATIONARY) is not None, b.opt(NIM_LT) is not None
    named = level_nim(x.run.ctx)                # ключ цели — стационарная маржа названного мира: сдвинута она сама
    if named is not None and not stationary:
        return (f"ключ цели {level} (упр.) — стационарная маржа мира {named['world']} на составе баланса якоря — "
                f"сдвинут на {step}")
    if not stationary and not printed:
        return f"{level} (упр.) сдвинут на {step}"
    words = f"ключ цели {level} (упр.) сдвинут на {step}"
    shifted = (x.rel.sensitivities or {}).get("nim", {}).get("run")
    if shifted is None:
        return words
    if stationary:
        d = stationary_nim(shifted.ctx)["value"] - stationary_nim(x.run.ctx)["value"]
        return (words + f" — стационарная маржа мира {stationary_nim(x.run.ctx)['world']} на составе баланса якоря "
                        f"меняется на {_signed_pp(d)}")
    d = printed_nim_lt(shifted)["value"] - printed_nim_lt(x.run)["value"]
    return words + f" — печатаемая маржа модальной клетки меняется на {_signed_pp(d)}"


def _signed_pp(x: float) -> str:
    """Изменение доли словами со знаком: 0.0016 → «+0,16 п.п.»."""
    return f"{100 * float(x):+.2f}".replace(".", ",").replace("-", "−") + " п.п."


def _follow_words(book: Book) -> str:
    """Слова о концах осей полосы в подписи чувствительностей — только при ключе `axis_follow: both`."""
    if not axes_follow(book):
        return ""
    return ("; в строках ЧПМ и запаса капитала ось полосы идёт за сдвинутым значением обоими концами — как в "
            "строках обратного расчёта")


def _bank_row(x: _Ctx, lam: float, median: float) -> dict:
    bl = bank_language(x.run, lam)
    bv = bl["bv_v"]
    g = x.run.governance
    pend = x.run.pending_dividend                   # D_pend — вне дисконта за управление (М§8.2)
    unit = median * x.n_div / 1000 - x.run.bridge_amount - pend
    v_med = (unit / (1 - g) if unit > 0 else unit) + pend
    cap = x.cap
    row = {"lambda": lam, "bv_v": R_MONEY(bv), "v_point": R_MONEY(bl["v_point"]), "v_median": R_MONEY(v_med),
           "fair_pb_point": R_MULT(bl["v_point"] / bv), "fair_pb_median": R_MULT(v_med / bv),
           "market_pb": R_MULT(None if cap is None else cap / bv),
           "excess_point": R_MONEY(bl["v_point"] - bv), "excess_median": R_MONEY(v_med - bv),
           "excess_market": R_MONEY(None if cap is None else cap - bv),
           "roe_tc": R_SHARE(bl["roe_tc"]), "k_tc": R_SHARE(bl["k_tc"])}
    row.update(_sens_at(x, lam))
    return row


def _fair_value(x: _Ctx, jump: Mapping) -> tuple[dict, dict]:
    run, band = x.run, x.band
    lam, step = x.lam, band.print_step
    rows = []
    book_row = None
    for L in _lambda_grid(lam):
        r = _headline_row(band, L, x.prices, x.main)
        exact = r.pop("_exact")
        r = {"lambda": L, **{k: r[k] for k in ("median", "p10", "p25", "p75", "p90", "mean")},
             "point": R_PRICE(run.price_at(L)), **{k: r[k] for k in ("p_below_market", "p_below_by_ticker",
                                                                      "market_percentile", "upside")}}
        rows.append(r)
        if abs(L - lam) < EPS:
            book_row, book_exact = r, exact
    h = book_exact
    contrib = [{"axis": c["axis"], "name": c["name"], "share": R_PROB(c["share"]), "rank_corr": R_SHARE(c["rank_corr"]),
                "paths": c["paths"][:U.BUNDLE_ENDS_PRINTED], "judgement_key": c["judgement_key"]} for c in band.contributions(lam)]
    if contrib:        # доли после округления — в сумме ровно 1 (остаток — самой крупной)
        contrib[0]["share"] = R_PROB(1.0 - sum(c["share"] for c in contrib[1:]))
    headline = {
        "median": book_row["median"], "printed_median": h["printed_median"],
        "band80": [book_row["p10"], book_row["p90"]], "printed_band80": h["printed_band80"],
        "band50": [book_row["p25"], book_row["p75"]], "printed_band50": h["printed_band50"],
        "mean": book_row["mean"], "point": R_PRICE(run.point), "printed_point": U.round_half_up(run.point, step),
        "market": R_MARKET(x.prices[x.main]), "market_by_ticker": {t: R_MARKET(v) for t, v in x.prices.items()},
        "p_below_market": book_row["p_below_market"], "p_below_by_ticker": book_row["p_below_by_ticker"],
        "market_percentile": book_row["market_percentile"], "upside": book_row["upside"],
        "draws": band.draws, "seed": band.seed, "quantiles": list(band.quantiles), "own_macro_confidence": lam,
        "lambda_step": 1 / LAMBDA_STEPS, "print_step": step, "ceiling_x_market": band.ceiling_x_market,
        "low_draws": list(band.low_draws), "high_draws": list(band.high_draws), "contributions": contrib,
        "by_lambda": rows,
    }
    if x.book.opt(U.DRAW_STEP_KEY) is not None:     # шаг хранения прогонов — только при ключе книги (М§10, П§0.3)
        headline["draw_step"] = band.draw_step
    bank_rows = [_bank_row(x, r["lambda"], r["median"]) for r in rows]
    b_book = next(r for r in bank_rows if abs(r["lambda"] - lam) < EPS)
    lo, hi = run.layers["macro_neutral"], run.layers["analytical"]
    bank = {"target": "median", **{k: b_book[k] for k in b_book if k != "lambda"},
            "roe_ltm": _ltm(x)["roe"],
            "sensitivity_basis": ("CoR: пути всех режимов (упр. базис, в движок — мостом) сдвинуты на "
                                  f"{pct(float(x.book.get('valuation.sensitivities.cor_pp')))[:-2]} п.п.; ЧПМ: "
                                  f"{_nim_shift_words(x)}; "
                                  "ROE — строка ЧПМ, делённая "
                                  f"на вызванное ею изменение ROE {x.book.label('terms.lt_level')}; сдвиг медианы — "
                                  "среднее по срединным "
                                  f"прогонам из {grouped(x.rel.anchor.n if x.rel.anchor else 0)} на общих случайных "
                                  "числах" + _buffer_words(x.book) + _follow_words(x.book)),
            "layers": {name: {"bv_v": R_MONEY(L.bv_v), "v0": R_MONEY(L.v0), "fair_pb": R_MULT(L.pb),
                              "excess": R_MONEY(L.excess), "roe_tc": R_SHARE(L.roe_tc), "k_tc": R_SHARE(L.k_tc)}
                       for name, L in (("analytical", hi), ("macro_neutral", lo))},
            "by_lambda": bank_rows}
    bridge_rows = [{"year": r["year"], "dps": r["dps"], "amount": R_MONEY(r["amount"]),
                    "deducted_on": _iso(r["deducted_on"]), "last_buy_date": _iso(r["last_buy_date"]),
                    "ex_date": _iso(r["ex_date"]), "sign": int(r["sign"]), **_period_words(r)}
                   for r in run.bridge_rows]
    by_world = {}
    for w in x.worlds:
        wl = world_layer(run, w)
        by_world[w] = {"price": R_PRICE(wl["price"]), "v0": R_MONEY(wl["v0"]), "bv_v": R_MONEY(wl["bv_v"]),
                       "pb": R_MULT(wl["pb"])}
    fv = {
        "method": "judgement_median", "target": "median", "headline": headline,
        "low": R_PRICE(run.low), "central": R_PRICE(run.point), "high": R_PRICE(run.high),
        "printed_low": U.round_half_up(run.low, step), "printed_central": U.round_half_up(run.point, step),
        "printed_high": U.round_half_up(run.high, step), "own_macro_confidence": lam,
        "rates_view": {"low": R_PRICE(run.low), "high": R_PRICE(run.high), "rub": R_PRICE(run.high - run.low)},
        "bank_first_line": bank,
        "bridge": {"amount": R_MONEY(run.bridge_amount), "per_share": R_PRICE(run.bridge_amount * 1000 / x.n_div),
                   "governance_applies": bool(x.book.get("bridge.governance_applies")),
                   "pending_dividend": R_MONEY(run.pending_dividend), "rows": bridge_rows,
                   # суммы моста — отток из капитала группы: на акции в обращении (подпись — meta.basis_labels)
                   **({"amount_basis": AMOUNT_OUTSTANDING} if _amount_basis(x.book) else {})},
        "by_world": by_world, "jump_guard": dict(jump),
    }
    return fv, h


def _layers(x: _Ctx) -> dict:
    run = x.run
    out = {}
    bb = run.ctx.prep.bb is not None
    for name, L in run.layers.items():
        out[name] = {"title": L.title, "world_weights": {w: R_PROB(v) for w, v in L.world_weights.items()},
                     "v0": R_MONEY(L.v0), "bv_v": R_MONEY(L.bv_v), "price": R_PRICE(L.price), "pb": R_MULT(L.pb),
                     "excess": R_MONEY(L.excess), "pv_ri_explicit": R_MONEY(L.pv_ri_explicit),
                     "pv_terminal": R_MONEY(L.pv_terminal), "terminal_share": R_SHARE(L.terminal_share),
                     "roe_tc": R_SHARE(L.roe_tc), "k_tc": R_SHARE(L.k_tc),
                     "p_price_below_market": R_PROB(L.p_price_below_market), "p_roe_below_k": R_PROB(L.p_roe_below_k),
                     "capital_gap_mass": R_PROB(L.capital_gap_mass)}
        if bb:                                  # выкуп по цене мира: стоимость на оставшиеся акции (М§5.6)
            out[name]["buyback_effect"] = R_MONEY(L.buyback_effect)
    lo, hi = run.layers["macro_neutral"], run.layers["analytical"]
    mix = lambda a, b: a + x.lam * (b - a)  # noqa: E731
    v0, bv = mix(lo.v0, hi.v0), mix(lo.bv_v, hi.bv_v)
    pv_ri, pv_t = mix(lo.pv_ri_explicit, hi.pv_ri_explicit), mix(lo.pv_terminal, hi.pv_terminal)
    g = run.governance
    core = v0 - run.pending_dividend                # объявленный, ещё не вычтенный дивиденд — без дисконта (М§8.2)
    gov = -g * core if core > 0 else 0.0
    bridge = run.bridge_amount
    equity = v0 + gov + bridge
    per = lambda m: R_PRICE(m * 1000 / x.n_div)  # noqa: E731
    # суммы водопада складываются в хранимых числах (округление — один раз, остаток — в промежуточный итог)
    a_bv, a_ri, a_t = R_MONEY(bv), R_MONEY(pv_ri), R_MONEY(pv_t)
    a_v0 = R_MONEY(a_bv + a_ri + a_t)
    if bb:                                      # выкуп по цене мира: строка водопада до V0 (М§5.6)
        bbe = mix(lo.buyback_effect, hi.buyback_effect)
        a_bb = R_MONEY(bbe)
        a_v0 = R_MONEY(a_bv + a_ri + a_t + a_bb)
    a_gov, a_br = R_MONEY(gov), R_MONEY(bridge)
    a_eq = R_MONEY(a_v0 + a_gov + a_br)
    out["headline_mix"] = {
        "title": f"Смесь заголовка: λ × «{hi.title}» + (1 − λ) × «{lo.title}»", "lambda": x.lam,
        "v0": R_MONEY(v0), "bv_v": R_MONEY(bv), "pv_ri_explicit": R_MONEY(pv_ri), "pv_terminal": R_MONEY(pv_t),
        "governance": R_MONEY(gov), "bridge": R_MONEY(bridge), "price": R_PRICE(run.point),
        **({"buyback_effect": R_MONEY(bbe)} if bb else {}),
        "waterfall": [
            {"key": "bv_v", "title": "Капитал на дату оценки", "amount": a_bv, "per_share": per(bv), "total": False},
            {"key": "pv_ri_explicit", "title": "PV остаточного дохода явного участка", "amount": a_ri,
             "per_share": per(pv_ri), "total": False},
            {"key": "pv_terminal", "title": "PV терминала (остаточный доход)", "amount": a_t, "per_share": per(pv_t),
             "total": False},
            *([{"key": "buyback", "title": "Выкуп акций: стоимость на оставшиеся акции", "amount": a_bb,
                "per_share": per(bbe), "total": False}] if bb else []),
            {"key": "v0", "title": "Оценка капитала V0", "amount": a_v0, "per_share": per(v0), "total": True},
            {"key": "governance", "title": "Дисконт за управление", "amount": a_gov, "per_share": per(gov),
             "total": False},
            {"key": "bridge", "title": "Мост: объявленные дивиденды", "amount": a_br, "per_share": per(bridge),
             "total": False},
            {"key": "equity", "title": "Стоимость для акционера", "amount": a_eq, "per_share": per(equity),
             "total": True},
        ]}
    return out


# ------------------------------------------------------------------ grid, variance, worlds, regimes


def _grid(x: _Ctx) -> dict:
    cells = []
    ay = x.tl.anchor_year
    for c in x.run.cells:
        a = c.annual
        cells.append({
            "world": c.world, "regime": c.regime, "scenario": c.scenario,
            "p_analytical": R_PROB(x.p_an[c.key]), "p_market_implied": R_PROB(x.p_mi[c.key]),
            "p_neutral": R_PROB(x.p_neu[c.key]), "v": R_MONEY(c.v_price), "bv_v": R_MONEY(c.bv_v),
            "price": R_PRICE(x.run.cell_price(c)), "pb": R_MULT(c.v_price / c.bv_v),
            "pv_ri_explicit": R_MONEY(c.pv_ri_explicit), "terminal_share": R_SHARE(c.terminal_share),
            "roe_t": R_SHARE(c.roe_t), "k_t": R_SHARE(c.k_t), "g_t": R_SHARE(c.g_t), "x_t": R_MONEY(c.x_t),
            "n20_min": R_SHARE(c.n20_min), "n11_min": R_SHARE(c.n11_min), "gap_period": c.gap_period,
            "dps_first": rnd(c.dps.get(ay), PRECISION["dps_cells"]), "flags": sorted(c.flags),
            "annual": {
                "ni_sh": [rnd(v, PRECISION["money_cells"]) for v in a["ni_sh"]],
                **{k: [rnd(v, PRECISION["share_cells"]) for v in a[k]] for k in ("roe", "cor", "nim", "cir", "n20",
                                                                                  "n11", "payout")},
                "dps": [rnd(v, PRECISION["dps_cells"]) for v in a["dps"]],
                **({} if "buyback" not in a else {"buyback": [rnd(v, PRECISION["money_cells"]) for v in a["buyback"]]})},
            **({} if c.terminal_stationary is None
               else {"terminal_stationary": _terminal_stationary(c.terminal_stationary)}),
            **({} if c.terminal_fixed is None else {"terminal_fixed": _terminal_fixed(c.terminal_fixed)}),
            **({} if c.terminal_year is None else {"terminal_year": _terminal_year(c.terminal_year)}),
            **({} if c.terminal_fade is None else {"terminal_fade": {
                "s": c.terminal_fade["s"], "n": rnd(c.terminal_fade["n"], PRECISION["share"]),
                "phi": R_SHARE(c.terminal_fade["phi"])}})})
    return {"world_order": x.worlds, "regime_order": x.regimes, "scenario_order": x.scenarios,
            "years": list(x.run.cells[0].years), "basis": "engine", "cells": cells}


def _terminal_stationary(block: Mapping[str, float]) -> dict:
    """Узел клетки «терминал от стационарных ставок книг» (К4, М§7): ΔNII* года L — шагом денег, ставки — шагом долей."""
    return {k: R_MONEY(v) if k == "d_nii_l" else R_SHARE(v) for k, v in block.items()}


def _terminal_year(block: Mapping[str, float]) -> dict:
    """Узел клетки «год терминала по средней длине года» (К-Т2а, М§7): дни года L — как есть, множители ν_L и ψ —
    шагом долей, рубли — шагом денег."""
    return {k: v if k == "days_l" else R_SHARE(v) if k in ("nu_l", "psi") else R_MONEY(v) for k, v in block.items()}


def _terminal_fixed(block: Mapping[str, Any]) -> dict:
    """Узел клетки «постоянные в рублях части за концом сетки» (М§7): λ_F, части, связывающий норматив; рубли — шагом
    денег, доли — шагом долей."""
    shares = ("lam_f", "kappa", "y_m", "phi")
    return {k: (v if k in ("parts", "binding", "bound_after_payout") else R_SHARE(v) if k in shares else R_MONEY(v))
            for k, v in block.items()}


def _variance(x: _Ctx) -> dict:
    prob = x.p_an
    cells = x.run.cells
    price = {c.key: x.run.cell_price(c) for c in cells}
    mu = sum(prob[k] * v for k, v in price.items())
    total = sum(prob[k] * (v - mu) ** 2 for k, v in price.items())
    out = {}
    for name, idx in (("world", 0), ("regime", 1), ("scenario", 2)):
        groups: dict[str, list] = {}
        for k in price:
            groups.setdefault(k[idx], []).append(k)
        eff = 0.0
        for ks in groups.values():
            w = sum(prob[k] for k in ks)
            if w > 0:
                m = sum(prob[k] * price[k] for k in ks) / w
                eff += w * (m - mu) ** 2
        out[name] = eff / total if total else 0.0
    out["interaction"] = 1.0 - sum(out.values())
    return {"price": {k: R_SHARE(v) for k, v in out.items()},
            "method": ("доли дисперсии цены клеток под вероятностями слоя «свой взгляд»: главные эффекты осей "
                       "(дисперсия условных средних) и остаток — взаимодействие")}


def _worlds(x: _Ctx) -> dict:
    b = x.book
    tr = x.run.ctx.transmission
    weights = {name: L.world_weights for name, L in x.run.layers.items()}
    rows = {}
    for w in x.worlds:
        cells = [c for c in x.run.cells if c.world == w]
        wl = world_layer(x.run, w)
        wb = b.get(f"worlds_bank.{w}")
        first_half = min(k for k in b.get(f"worlds.{w}.ofz_1y"))
        rows[w] = {
            "name": b.get(f"worlds.{w}.name"),
            "weights": {k: R_PROB(weights[k].get(w, 0.0)) for k in ("analytical", "market_implied", "macro_neutral")},
            "key_rate": _half_year_rows(b.get(f"worlds.{w}.key_rate"), x.years),
            "cpi": _half_year_rows(b.get(f"worlds.{w}.cpi"), x.years),
            "real_key": _half_year_rows(b.get(f"worlds.{w}.real_key"), x.years),
            "ofz": {n: R_SHARE(float(b.get(f"worlds.{w}.ofz_{n}y")[first_half])) for n in ("1", "3", "5", "10")},
            "zero_curve": {k: R_SHARE(float(v)) for k, v in b.get(f"worlds.{w}.zero_curve").items()},
            "lt_inflation": R_SHARE(b.get(f"worlds.{w}.lt_inflation")),
            "k_t": R_SHARE(sum(c.k_t for c in cells) / len(cells)), "g_t": R_SHARE(sum(c.g_t for c in cells) / len(cells)),
            "price": R_PRICE(wl["price"]), "v0": R_MONEY(wl["v0"]),
            "credit_growth": {k: _year_rows(wb["credit_growth"].get(k)) for k in ("corporate", "mortgage", "retail_other")},
            "funds_growth": {k: _year_rows(wb["funds_growth"].get(k)) for k in ("retail", "corporate")},
            "transmission": R_SHARE(tr.t_local.get(w)),
        }
    src = b.get("worlds.source")
    ov = b.get("worlds.overlay")
    return {"order": x.worlds, "rows": rows,
            "source": {k: src.get(k) for k in ("record", "origin", "record_asof", "curve_date", "sha256")},
            "overlay": {"file": ov.get("file"), "sha256": ov.get("sha256")}}


def _explicit_years(traj: Any, years: Sequence[int]) -> list[int]:
    """Годы явного участка траектории: до LT_from, иначе до года после последнего ключа года."""
    if not isinstance(traj, Mapping):
        return list(years[:1])
    if traj.get("LT_from") is not None:
        end = int(traj["LT_from"])
    else:
        keys = [int(str(k)[:4]) for k in traj if str(k)[:4].isdigit()]
        end = (max(keys) + 1) if keys else years[0]
    return [y for y in years if y <= end] or list(years[:1])


def _traj_years(traj: Any, years: Sequence[int]) -> list[dict]:
    t = Trajectory(traj)
    return [{"year": y, "value": R_SHARE(t.year_value(y))} for y in years]


def _regimes(x: _Ctx) -> dict:
    b, br = x.book, x.br
    rows = {}
    post = x.run.ctx.posterior
    for r in x.regimes:
        spec = b.get(f"regimes.{r}")
        cor = _traj_years(spec["cor"], _explicit_years(spec["cor"], x.years))
        cor_lt = float(spec["cor"]["LT"]) if isinstance(spec["cor"], Mapping) and "LT" in spec["cor"] else cor[-1]["value"]
        mgmt = b.get("regimes.cor_basis") == "mgmt"
        to_e = (lambda v: br.to_engine_cor(v)) if mgmt else (lambda v: v)
        ns = spec["nim_shift"]
        row = {"title": spec["name"], "prior": float(b.get(f"joint.regime_prob.{r}")), "posterior": R_PROB(post[r]),
               "cor": cor, "cor_engine": [{"year": c["year"], "value": R_SHARE(to_e(c["value"]))} for c in cor],
               "cor_lt": cor_lt, "cor_lt_engine": R_SHARE(to_e(cor_lt)),
               "nim_shift": _traj_years(ns, _explicit_years(ns, x.years)),
               "nim_shift_lt": R_SHARE(Trajectory(ns).year_value(x.years[-1])),
               "loan_growth_adj": _traj_years(spec["loan_growth_adj"], _explicit_years(spec["loan_growth_adj"], x.years))}
        if spec.get("shock_year_offset") is not None:
            prof = [{"period": k, "value": float(v)} for k, v in spec["cor"].items() if "Q" in str(k)]
            one = spec.get("one_off_loss") or {}
            row["crisis"] = {"shock_year": int(x.prep.regimes[r].shock_year),
                             "shock_year_offset": int(spec["shock_year_offset"]),
                             "one_off_loss": {"period": one.get("period"),
                                              "amount": None if one.get("amount") is None else float(one["amount"])},
                             "loan_growth_override": _year_rows(spec.get("loan_growth_override")),
                             "cor_quarters": prof}
        rows[r] = row
    exp_lt = sum(post[r] * rows[r]["cor_lt"] for r in x.regimes)
    ru = "joint.regime_update"
    obs = []
    for u in x.run.ctx.updates:
        obs.append({"period": u["period"], "basis": u["basis"], "cor": u["cor_raw"], "nim": u["nim_raw"],
                    "se_cor": u["se_cor"], "se_nim": u["se_nim"], "cor_engine": R_SHARE(u["cor"]),
                    "nim_engine": R_SHARE(u["nim"]), "posterior_after": {k: R_PROB(v) for k, v in u["posterior_after"].items()}})
    hist = _regime_history(x)
    # мир, в котором стоят пути и уровни CoR режимов, — при ключе мира-опоры κ-добавки (М§4.6)
    ref = {} if kappa_world(b) is None else {"reference_world": kappa_world(b)}
    return {**ref, "order": x.regimes, "basis": "engine", "cor_basis": str(b.get("regimes.cor_basis")),
            "cor_bridge": {"method": br.cor_method, "value": br.cor_value}, "rows": rows,
            "near_nim_shift": _near_rows(x),
            "expected": {"cor_lt": R_SHARE(exp_lt), "cor_lt_engine": R_SHARE(sum(post[r] * rows[r]["cor_lt_engine"]
                                                                               for r in x.regimes)),
                         "nim_shift_lt": R_SHARE(sum(post[r] * rows[r]["nim_shift_lt"] for r in x.regimes))},
            "update": {"cor": {"sigma_pp": b.get(f"{ru}.observables.cor.sigma_pp"), "rho_q": b.get(f"{ru}.observables.cor.rho_q")},
                       "nim": {"sigma_pp": b.get(f"{ru}.observables.nim.sigma_pp"), "rho_q": b.get(f"{ru}.observables.nim.rho_q")},
                       "max_shift_pp": b.get(f"{ru}.max_shift_pp"), "window_obs": int(b.get(f"{ru}.window_obs")),
                       "floor_share": float(b.get(f"{ru}.floor_share")), "observations": obs},
            "history": hist}


def _near_rows(x: _Ctx) -> list[dict]:
    """Ближний сдвиг ЧПМ по кварталам от first_period до первого квартала с нулём включительно (П§2)."""
    near = x.prep.near
    out = []
    for q in range(1, x.tl.Q + 1):
        v = float(near[q]) if near else 0.0
        out.append({"period": x.tl.period(q), "value": R_SHARE(v)})
        if v == 0.0:
            break
    return out


def _regime_history(x: _Ctx) -> list[dict]:
    mq = (x.facts.file("mgmt_quarterly").get("quarters") or {}) if "mgmt_quarterly" in x.facts.files else {}
    bh = x.facts.file("bridge_mgmt_ifrs") if "bridge_mgmt_ifrs" in x.facts.files else {}
    eng = {}
    for key in ("cor", "nim"):
        for h in (bh.get(key) or {}).get("history") or []:
            eng.setdefault(str(h.get("period")), {})[key] = _node_v(h.get("engine"))
    periods = sorted(set(mq) | set(eng))
    out = []
    for p in periods:
        row = mq.get(p) or {}
        out.append({"period": p, "cor_mgmt": _node_v(row.get("cor")), "cor_engine": (eng.get(p) or {}).get("cor"),
                    "nim_mgmt": _node_v(row.get("nim")), "nim_engine": (eng.get(p) or {}).get("nim")})
    return out


# ------------------------------------------------------------------ capital


# Подписи нормативов (`capital.titles`) и строк моста норматива — ключи книги `meta.labels.capital`,
# `meta.labels.capital_bridge` (М§0.6).
CAPITAL_TITLE_KEYS = ("n20", "n11", "n11_observed", "n1_0", "n1_2")


def _q_end(x: _Ctx, year: int) -> int:
    return x.tl.index(period_str(year, 4))


def _scenario_series(x: _Ctx, series: Sequence[float]) -> list[float | None]:
    out = []
    for y in x.years:
        q = _q_end(x, y)
        out.append(R_SHARE(series[q]) if 0 <= q < len(series) else None)
    return out


def _capital(x: _Ctx) -> dict:
    b, af, run = x.book, x.af, x.run
    q0 = run.ctx.clock.q0
    rwa0 = x.prep.rwa0
    post = af.n20 - af.dividends_payable / rwa0 if af.n20_pre_dividend else af.n20
    req20_now, req11_now = x.E(x.p_an, "req20", q0), x.E(x.p_an, "req11", q0)
    c0 = run.cells[0]
    n10 = x.fv("capital", "n1_0_bank")
    anchor = {"as_of": _iso(af.as_of), "n20": af.n20, "n20_pre_dividend": af.n20_pre_dividend,
              "n20_post_dividend": R_SHARE(post),
              "n11_bank": {"value": af.n11_bank, "as_of": _iso(x.plain("capital", "n1_1_bank.as_of"))},
              "rwa": R_MONEY(rwa0), "bv_common": R_MONEY(af.bv), "at1": R_MONEY(af.at1), "t2": R_MONEY(af.t2),
              "fvoci_reserve": R_MONEY(af.fvoci_reserve), "ded20": R_MONEY(c0.quarters["ded20"][0]),
              "ded11": R_MONEY(c0.quarters["ded11"][0]), "req20_now": R_SHARE(req20_now),
              "req11_now": R_SHARE(req11_now), "n20_headroom": R_SHARE(post - req20_now), "basis": "ifrs",
              "src": b.label("capital.anchor_src_estimated" if af.estimated else "capital.anchor_src",
                             date=_ru_date(af.as_of))}
    if af.n11_bank is not None:                 # запас второго норматива якоря до требования года даты оценки
        anchor["n11_headroom"] = R_SHARE(af.n11_bank - req11_now)
    if x.prep.growth is not None and x.tl.Q >= 1:
        # правило роста сравнивает норматив с требованием с глиссадой (М§4.13.1): запас якоря — и до него, к
        # концу первого квартала сетки (ожидание слоя «свой взгляд», как у требования года)
        glide = x.E(x.p_an, "req20_glide", 1)
        anchor.update(req20_glide_next=R_SHARE(glide), req20_glide_period=x.tl.period(1),
                      n20_headroom_glide=R_SHARE(post - glide))
    if af.estimated:                            # нормативы якоря — оценка до выхода формы (М§3.3)
        anchor["estimated"] = True
    if n10 is not None:
        anchor["n10_bank"] = {"value": n10, "as_of": _iso(x.plain("capital", "n1_0_bank.as_of"))}
    observed = None
    if x.fv("capital", "n1_1_bank.value") is not None:
        observed = {"n1_0": n10, "n1_1": x.fv("capital", "n1_1_bank.value"), "n1_2": x.fv("capital", "n1_2_bank"),
                    "as_of": _iso(x.plain("capital", "n1_1_bank.as_of")),
                    "source": b.label("capital.observed_source")}
    table = b.get("joint.reg_prob_given_regime")
    scen, by_s = {}, {}
    for s in x.scenarios:
        sp = x.prep.scenarios[s]
        cells = [c for c in run.cells if c.scenario == s]
        mass = sum(x.p_an[c.key] for c in cells)
        scen[s] = {"title": b.get(f"capital.reg_scenarios.{s}.name"),
                   "p_given_regime": {r: float(table[r][s]) for r in x.regimes}, "mass": R_PROB(mass),
                   "conservation": _scenario_series(x, sp.conservation), "sifi": _scenario_series(x, sp.sifi),
                   "ccyb": _scenario_series(x, sp.ccyb), "deduction_n20": _scenario_series(x, sp.ded_pp20),
                   "deduction_n11": _scenario_series(x, sp.ded_pp11), "floor20": _scenario_series(x, sp.floor20),
                   "floor11": _scenario_series(x, sp.floor11), "req20": _scenario_series(x, sp.req20),
                   "req11": _scenario_series(x, sp.req11)}
        row = {}
        for key in ("n20", "n11"):
            mean, p10, p90 = [], [], []
            for i, _y in enumerate(x.years):
                pairs = [(c.annual[key][i], x.p_an[c.key]) for c in cells]
                w = sum(p for v, p in pairs if v is not None)
                mean.append(R_SHARE(sum(v * p for v, p in pairs if v is not None) / w) if w else None)
                p10.append(R_SHARE(x.wquantile(pairs, TAILS[0])))
                p90.append(R_SHARE(x.wquantile(pairs, TAILS[1])))
            row[key], row[f"{key}_p10"], row[f"{key}_p90"] = mean, p10, p90
        by_s[s] = row
    mix = {k: [] for k in ("n20", "n11", "req20", "req11", "floor20", "floor11")}
    for y in x.years:
        q = _q_end(x, y)
        ok = 0 <= q <= x.tl.Q
        for k in ("n20", "n11"):
            mix[k].append(R_SHARE(x.ratio(x.p_mix, k, q) if ok else None))
        for k in ("req20", "req11", "floor20", "floor11"):
            mix[k].append(R_SHARE(x.E(x.p_mix, k, q) if ok else None))
    gap_cells = [c for c in run.cells if "capital_gap" in c.flags]
    gap = {"mass": R_PROB(sum(x.p_an[c.key] for c in gap_cells)), "cells": len(gap_cells),
           "cell_list": [c.label for c in gap_cells][:CELL_LIST_MAX],
           "first_period": min((c.gap_period for c in gap_cells if c.gap_period), default=None),
           "by_scenario": {s: R_PROB(sum(x.p_an[c.key] for c in gap_cells if c.scenario == s)) for s in x.scenarios}}
    extra = {}
    if x.prep.growth is not None:               # рост, ограниченный капиталом (М§4.13)
        extra = {"requirement": _requirement(x), "growth": _growth(x)}
    if x.rel.rule_price is not None:
        extra["rule_price"] = copy.deepcopy(dict(x.rel.rule_price))
    if b.opt("checks.mix_ratio_tolerance") is not None:    # допуск сверки норматива смеси — ключ книги (П§7 п. 10)
        extra["mix_tolerance"] = float(b.opt("checks.mix_ratio_tolerance"))
    return {"titles": {k: b.label(f"capital.{k}") for k in CAPITAL_TITLE_KEYS}, "anchor": anchor,
            **({"observed": observed} if observed else {}),
            "policy_threshold": float(b.get("dividends.policy.threshold")),
            "minimum": {"n20_0": b.get("capital.minimum.n20_0"), "n1_1": b.get("capital.minimum.n1_1")},
            "mgmt_buffer": {"n20_0": b.get("capital.mgmt_buffer.n20_0"), "n1_1": b.get("capital.mgmt_buffer.n1_1")},
            "years": list(x.years), "scenarios": scen, "by_scenario": by_s, "mix": mix, "capital_gap": gap,
            "bridge": _capital_bridge(x), **extra}


# Какая строка `capital.requirement.mix` стоит против требования (М§4.13.1): первый норматив — отчётный,
# второй — с прибылью периода (его сравнивает правило роста); подписи строк второго норматива — словами.
REQUIREMENT_COMPARE = {"n20": "n20", "n11": "n11_star"}
REQUIREMENT_NOTES = {"n11_star": "с прибылью периода — его сравнивает с требованием правило роста",
                     "n11": "отчётный, без прибыли неаудированного периода — справочно"}


def _requirement(x: _Ctx) -> dict:
    """`capital.requirement` (П§2): нормативы смеси заголовка против требования с глиссадой (М§4.13.1) по первым
    кварталам сетки; Н20.1 с прибылью периода — в определении движка, как нормативы смеси. `compare` называет
    строку, которую правило роста сравнивает с требованием, `notes` подписывает обе строки второго норматива."""
    gr, p, tl = x.prep.growth, x.p_mix, x.tl
    qs = list(range(1, min(QUARTERS_SHOWN, tl.Q) + 1))

    def with_profit(q: int) -> float | None:
        k = rwa = add = 0.0
        for c in x.run.cells:
            row = c.quarters
            if row["k11"][q] is None or row["e_unaudited"][q] is None or row["n11_star"][q] is None:
                return None                     # строка якоря без факта прибыли неаудированного периода
            cap = float(row["k11"][q]) + max(float(row["e_unaudited"][q]), 0.0)
            w, r = p[c.key], float(row["rwa"][q])
            k, rwa, add = k + w * cap, rwa + w * r, add + w * (float(row["n11_star"][q]) - cap / r)
        return k / rwa + add

    mix = {"n20": [R_SHARE(x.ratio(p, "n20", q)) for q in qs], "n11": [R_SHARE(x.ratio(p, "n11", q)) for q in qs],
           "n11_star": [R_SHARE(with_profit(q)) for q in qs],
           **{k: [R_SHARE(x.E(p, k, q)) for q in qs] for k in ("req20_glide", "req11_glide", "req20", "req11")}}
    ends = [_q_end(x, y) for y in x.years]
    return {"periods": [tl.period(q) for q in qs], "mix": mix,
            "by_scenario": {s: {"req20_glide": [R_SHARE(x.prep.glide[s][0][q]) for q in qs],
                                "req11_glide": [R_SHARE(x.prep.glide[s][1][q]) for q in qs]} for s in x.scenarios},
            "years_mix": {**{k: [R_SHARE(x.E(p, k, q)) if 0 <= q <= tl.Q else None for q in ends]
                             for k in ("req20_glide", "req11_glide")},
                          "n11_star": [R_SHARE(with_profit(q)) if 0 <= q <= tl.Q else None for q in ends]},
            "lookahead_quarters": gr.lookahead, "glide_pp_per_quarter": gr.glide,
            # с требованием правило роста сравнивает второй норматив с прибылью периода; отчётный — справочно
            "compare": dict(REQUIREMENT_COMPARE), "notes": dict(REQUIREMENT_NOTES)}


def _growth(x: _Ctx) -> dict:
    """`capital.growth` (П§2): потенциальный и фактический рост суммы кредитных книг по годам — смесь заголовка
    (рост — отношение ожиданий концов лет; год якоря — к факту конца прошлого года), доля урезанного роста на
    конец года, навёрстанное за год, доля прироста по первым кварталам, вероятность клеток с урезанным ростом."""
    gr, tl = x.prep.growth, x.tl
    cells_all = list(x.run.cells)

    def level(prob: Mapping, cells: Sequence[Any], name: str, q: int) -> float | None:
        if q < 0:                               # конец квартала до якоря — факт, один на все клетки
            return x.prep.hist_bal.get(q, {}).get("loans")
        mass = sum(prob[c.key] for c in cells)
        return sum(prob[c.key] * float(c.quarters[name][q]) for c in cells) / mass if mass else None

    def by_years(prob: Mapping, cells: Sequence[Any]) -> dict[str, list]:
        out: dict[str, list] = {"potential": [], "actual": [], "cut_share": []}
        for y in x.years:
            qe, qp = _q_end(x, y), _q_end(x, y - 1)
            if not 0 <= qe <= tl.Q:
                for k in out:
                    out[k].append(None)
                continue
            loans, pot = level(prob, cells, "loans", qe), level(prob, cells, "loans_potential", qe)
            base, base_pot = level(prob, cells, "loans", qp), level(prob, cells, "loans_potential", qp)
            out["potential"].append(R_SHARE(None if not base_pot or pot is None else pot / base_pot - 1))
            out["actual"].append(R_SHARE(None if not base or loans is None else loans / base - 1))
            out["cut_share"].append(R_SHARE(None if not pot or loans is None else 1 - loans / pot))
        return out

    mix = by_years(x.p_mix, cells_all)
    catch, lam_min, p_cut = [], [], []
    for i, y in enumerate(x.years):
        qs = [q for q in tl.quarters_of_year(y) if 1 <= q <= tl.Q]
        catch.append(R_MONEY(sum(x.E(x.p_mix, "catch_up", q) for q in qs)) if qs else None)
        lam_min.append(R_SHARE(min(x.E(x.p_mix, "lam", q) for q in qs)) if qs else None)
        cut = [c for c in cells_all if c.growth["lam_min"][i] is not None and c.growth["lam_min"][i] < 1 - LAM_TOL]
        p_cut.append(R_PROB(sum(x.p_an[c.key] for c in cut)) if qs else None)
    shown = list(range(1, min(QUARTERS_SHOWN, tl.Q) + 1))
    by_s = {}
    for sc in x.scenarios:
        rows = by_years(x.p_an, [c for c in cells_all if c.scenario == sc])
        by_s[sc] = {"actual": rows["actual"], "cut_share": rows["cut_share"]}
    return {"years": list(x.years), **mix, "catch_up": catch, "lam_min": lam_min, "p_cut": p_cut,
            "by_scenario": by_s,
            "quarters": {"periods": [tl.period(q) for q in shown],
                         "lam": [R_SHARE(x.E(x.p_mix, "lam", q)) for q in shown]},
            "order": gr.order, "min_growth_scale": gr.lam_min, "catch_up_rate": gr.catch_up}


CELL_LIST_MAX = 10               # меток клеток в списке — не больше 10 (П§2 checks.gates, capital_gap)


def _capital_bridge(x: _Ctx) -> dict:
    """Мост Н20.0 смеси заголовка от якоря до конца года даты оценки: норматив — в определении движка
    (E[K]/E[RWA] + A); изменение аддитивного слагаемого A (поправка и вычеты сценария) — в строке вычетов."""
    qe = min(max(_q_end(x, x.v.year), 1), x.tl.Q)
    p = x.p_mix
    k0, r0 = x.E(p, "k20", 0), x.E(p, "rwa", 0)
    ke, re_ = x.E(p, "k20", qe), x.E(p, "rwa", qe)
    qs = range(1, qe + 1)

    def total(fn) -> float:
        return sum(sum(p[c.key] * fn(c, q) for c in x.run.cells) for q in qs)

    Q = lambda c, name, q: float(c.quarters[name][q] or 0.0)  # noqa: E731
    profit = total(lambda c, q: Q(c, "ni_sh", q) - Q(c, "coupon", q) * (1 - Q(c, "tau_stat", q)))
    oci = total(lambda c, q: Q(c, "oci", q) + Q(c, "om", q))
    if "bb" in x.run.cells[0].quarters:         # выкуп по цене мира — в строке «OCI и прочее» (М§5.6)
        oci -= total(lambda c, q: Q(c, "bb", q))
    div = -total(lambda c, q: Q(c, "div", q)) + (x.E(p, "dpreg", qe) - x.E(p, "dpreg", 0))
    ded = -(x.E(p, "ded20", qe) - x.E(p, "ded20", 0))
    other = (ke - k0) - (profit + oci + div + ded)
    (_, a0), (_, ae) = x.ratio_parts(p, "n20", 0), x.ratio_parts(p, "n20", qe)
    rows = []
    for key, amount in (("dividend_accrual", div), ("profit", profit), ("oci_other", oci), ("deductions", ded),
                        ("other", other)):
        extra = (ae - a0) if key == "deductions" else 0.0
        rows.append({"key": key, "title": x.book.label(f"capital_bridge.{key}"), "pp": amount / re_ + extra,
                     "amount": R_MONEY(amount)})
    rows.insert(3, {"key": "rwa_growth", "title": x.book.label("capital_bridge.rwa_growth"),
                    "pp": k0 * (1 / re_ - 1 / r0),
                    "amount": R_MONEY(re_ - r0)})
    start, end = k0 / r0 + a0, ke / re_ + ae
    # хранимые доли: остаток округления — в «прочее», чтобы start + Σ pp = end на хранимых числах
    for r in rows:
        r["pp"] = R_SHARE(r["pp"])
    s_start, s_end = R_SHARE(start), R_SHARE(end)
    other_row = next(r for r in rows if r["key"] == "other")
    other_row["pp"] = R_SHARE(s_end - s_start - sum(r["pp"] for r in rows if r["key"] != "other"))
    return {"from": x.tl.anchor, "to": x.tl.period(qe), "start": s_start, "end": s_end, "rows": rows}


# ------------------------------------------------------------------ dividends


def _quarter_row(x: _Ctx, slot: Any) -> dict:
    """Строка `dividends.model_quarters[]` открытого квартала прибыли (П§2): DPS решения клетки — ожидание
    смеси заголовка и хвосты слоя «свой взгляд», DPS политики, вероятности среза и нуля — по решению периода."""
    per = slot.period
    dps = {c.key: c.dps_q[per] for c in x.run.cells}
    mix = sum(x.p_mix[k] * v for k, v in dps.items())
    pol = sum(x.p_mix[c.key] * c.dps_policy_q[per] for c in x.run.cells)
    pairs = [(dps[c.key], x.p_an[c.key]) for c in x.run.cells]
    return {"period": per, "decision_period": x.tl.period(slot.q), "pay_period": x.tl.period(slot.q_pay),
            "dps": R_DPS(mix), "dps_p10": R_DPS(x.wquantile(pairs, TAILS[0])),
            "dps_p90": R_DPS(x.wquantile(pairs, TAILS[1])), "dps_policy": R_DPS(pol),
            "amount": R_MONEY(mix * x.n_iss / 1000),
            "p_cut": R_PROB(sum(x.p_an[c.key] for c in x.run.cells if x.decision(c, per).cut)),
            "p_zero": R_PROB(sum(x.p_an[k] for k, v in dps.items() if abs(v) < EPS)),
            "declared": slot.dps is not None}


def _model_quarters(x: _Ctx) -> list[dict]:
    """Квартальный путь DPS: открытые кварталы прибыли, решение по которым приходится на первые
    `QUARTERS_SHOWN` кварталов сетки (П§2 `dividends.model_quarters`)."""
    return [_quarter_row(x, o) for o in x.cal.open if o.q <= QUARTERS_SHOWN]


def _dividends_model_quarterly(x: _Ctx) -> list[dict]:
    """`dividends.model[]` при квартальном календаре (М§5.7.5): годы словаря DPS клетки, DPS и DPS политики —
    суммы кварталов прибыли года; `p_cut` — срезано хотя бы одно решение модели за кварталы года; `declared` —
    записи реестра есть за все открытые кварталы года."""
    cal = x.cal
    out = []
    for y in cal.years:
        dps = {c.key: c.dps[y] for c in x.run.cells}
        mix = sum(x.p_mix[k] * v for k, v in dps.items())
        pol = sum(x.p_mix[c.key] * c.dps_policy[y] for c in x.run.cells)
        ni = x.flow(x.p_mix, "ni_sh", y)
        amount = mix * x.n_iss / 1000
        pairs = [(dps[c.key], x.p_an[c.key]) for c in x.run.cells]
        cut = sum(x.p_an[c.key] for c in x.run.cells if any(d.cut for d in c.decisions if d.year == y))
        out.append({"year": y, "pay_year": y + 1, "dps": R_DPS(mix), "dps_p10": R_DPS(x.wquantile(pairs, TAILS[0])),
                    "dps_p90": R_DPS(x.wquantile(pairs, TAILS[1])), "dps_policy": R_DPS(pol),
                    "payout": R_SHARE(None if not ni else amount / ni), "amount": R_MONEY(amount),
                    "p_cut": R_PROB(cut), "p_zero": R_PROB(sum(x.p_an[k] for k, v in dps.items() if abs(v) < EPS)),
                    "declared": all(cal.periods[per].dps is not None for per in cal.year_periods[y])})
    return out


def _dividends_model(x: _Ctx) -> list[dict]:
    if x.cal is not None:
        return _dividends_model_quarterly(x)
    agm = int(x.book.get("dividends.calendar.agm_quarter"))
    declared = {int(r["year"]) for r in x.rel.live_report.records if r.get("status") in ("declared", "paid")}
    out = []
    for y in x.years:
        q_agm = x.tl.index(period_str(y + 1, agm))
        if q_agm > x.tl.Q:
            break
        dps = {c.key: c.dps.get(y) for c in x.run.cells}
        if any(v is None for v in dps.values()):
            continue
        dec = {c.key: next((d for d in c.decisions if d.year == y), None) for c in x.run.cells}
        mix = sum(x.p_mix[k] * v for k, v in dps.items())
        pol = sum(x.p_mix[c.key] * c.dps_policy.get(y, 0.0) for c in x.run.cells)
        ni = x.flow(x.p_mix, "ni_sh", y)
        amount = mix * x.n_iss / 1000
        pairs = [(dps[c.key], x.p_an[c.key]) for c in x.run.cells]
        out.append({"year": y, "pay_year": y + 1, "dps": R_DPS(mix), "dps_p10": R_DPS(x.wquantile(pairs, TAILS[0])),
                    "dps_p90": R_DPS(x.wquantile(pairs, TAILS[1])), "dps_policy": R_DPS(pol),
                    "payout": R_SHARE(None if not ni else amount / ni), "amount": R_MONEY(amount),
                    "p_cut": R_PROB(sum(x.p_an[k] for k, d in dec.items() if d is not None and d.cut)),
                    "p_zero": R_PROB(sum(x.p_an[k] for k, v in dps.items() if abs(v) < EPS)),
                    "declared": y in declared})
    return out


def _median_gap_days(x: _Ctx) -> int | None:
    gaps = []
    for r in x.facts.file("dividends").get("history") or []:
        a, b = r.get("record_date"), r.get("pay_date")
        if a and b:
            gaps.append((date.fromisoformat(str(b)) - date.fromisoformat(str(a))).days)
    return sorted(gaps)[len(gaps) // 2] if gaps else None


def _next_expected_quarterly(x: _Ctx) -> dict:
    """Ближайшая выплата при квартальном календаре (П§2): запись — по ближайшей будущей экс-дате; без записи —
    первый открытый квартал прибыли без записи, решение по которому не раньше квартала даты оценки. Решение
    клетки, риск отмены и срез — по этому периоду; норматив — в квартале регуляторного вычета этой выплаты;
    доходность — одной квартальной выплаты."""
    b, cal, tl = x.book, x.cal, x.tl
    q0 = x.run.ctx.clock.q0

    def day(r: Mapping[str, Any]) -> str | None:
        got = r.get("ex_date") or r.get("record_date")
        return str(got)[:10] if got else None

    def upcoming(r: Mapping[str, Any]) -> bool:
        ahead = bool(day(r)) and date.fromisoformat(day(r)) > x.v
        if r.get("status") == "recommended":
            return ahead or not day(r)
        return r.get("status") == "declared" and ahead

    recs = sorted((r for r in x.rel.live_report.records if upcoming(r)),
                  key=lambda r: (day(r) is None, day(r) or "", int(r["year"]), str(r.get("period") or "")))
    rec = recs[0] if recs else None
    if rec is not None:
        period = None if rec.get("period") is None else str(rec["period"])
        year, status = int(rec["year"]), str(rec["status"])
        slot = cal.periods.get(period) if period else None
    else:
        slot = next((o for o in cal.open if o.dps is None and o.q >= q0), None)
        period = None if slot is None else slot.period
        year, status = (x.years[0] if slot is None else slot.year), "model"
    row = None if slot is None else _quarter_row(x, slot)
    # главная цифра: объявленный или рекомендованный DPS реестра, при статусе model — DPS политики квартала
    dps = float(rec["dps"]) if rec is not None else (row["dps_policy"] if row else None)
    cancel = limited = 0.0
    if slot is not None:
        for c in x.run.cells:
            d = x.decision(c, slot.period)
            if d.source == "crisis_skip" or abs(d.dps) < EPS:
                cancel += x.p_an[c.key]
            if d.cut:
                limited += x.p_an[c.key]
    events = (x.facts.file("calendar").get("events") or []) if "calendar" in x.facts.files else []
    ev = next((e for e in events if e.get("kind") == "record" and period and str(e.get("covers")) == period), None)
    record = _iso(rec.get("record_date")) if rec else None
    est = record or (_iso(ev.get("date")) if ev else None)
    note = ("дата отсечки из реестра" if record else
            ("оценка по календарю событий" + (" (окно)" if ev and ev.get("precision") == "window" else ""))
            if ev else "оценки даты нет в календаре фактов")
    gap = _median_gap_days(x)
    pay_est = None if est is None or gap is None else (date.fromisoformat(est) + timedelta(days=gap)).isoformat()
    q_chk = slot.q_reg if slot is not None else (tl.q_of_date(date.fromisoformat(record)) if record else None)
    n20e = x.ratio(x.p_an, "n20", q_chk) if q_chk is not None and 0 <= q_chk <= tl.Q else None
    out = {"year": year, "status": status, "dps": R_DPS(dps), "dps_policy": row["dps_policy"] if row else None,
           "dps_mean": row["dps"] if row else None, "dps_p10": row["dps_p10"] if row else None,
           "dps_p90": row["dps_p90"] if row else None, "p_cancel": R_PROB(cancel if row else None),
           "record_date": record, "record_date_est": est, "record_date_note": note,
           "pay_date_est": _iso(rec.get("pay_date")) if rec and rec.get("pay_date") else pay_est,
           "yield": {t: R_SHARE(None if dps is None else dps / x.prices[t]) for t in x.tickers},
           "yield_period": "quarter",
           "condition": {"metric": b.get("dividends.policy.metric"), "threshold": b.get("dividends.policy.threshold"),
                         "n20_expected": R_SHARE(n20e), "p_limited": R_PROB(limited)}}
    if period:
        out["period"] = period
        out["label"] = record_label(b, year, period, rec.get("label") if rec else None)
    if rec and rec.get("last_buy_date"):
        out["last_buy_date"] = _iso(rec.get("last_buy_date"))
    return out


def _yield_fwd_quarterly(x: _Ctx, nearest: Mapping[str, Any]) -> dict[str, float | None]:
    """Форвардная дивидендная доходность при квартальном календаре (П§2 `market.multiples`): сумма DPS четырёх
    кварталов прибыли, начиная с периода ближайшей выплаты, к цене. DPS квартала — запись реестра (объявленная,
    выплаченная, а нет их — рекомендация), без записи — DPS политики квартала по смеси заголовка."""
    start = nearest.get("period")
    if not start:
        return {t: None for t in x.tickers}
    known: dict[str, float] = {}
    for statuses in (("recommended",), DECLARED):       # решение собрания сильнее рекомендации
        for r in x.rel.live_report.records:
            if r.get("period") and r.get("status") in statuses:
                known[str(r["period"])] = float(r["dps"])
    total, first = 0.0, x.tl.index(str(start))
    for idx in range(first, first + 4):
        per = x.tl.period(idx)
        if per in known:
            total += known[per]
        elif per in x.cal.periods:
            total += _quarter_row(x, x.cal.periods[per])["dps_policy"]
        else:
            return {t: None for t in x.tickers}
    return {t: R_SHARE(total / x.prices[t]) for t in x.tickers}


def annual_payer(x: _Ctx) -> bool:
    """Эмитент платит раз в год (документ политики в фактах: `dividends.policy.frequency = annual`), а календарь
    модели квартальный (решения по кварталам прибыли — техника ядра): ближайшая выплата и форвардная доходность —
    за год прибыли, а не за квартал."""
    return x.cal is not None and (x.facts.file("dividends").get("policy") or {}).get("frequency") == "annual"


def _next_expected_annual(x: _Ctx, model: Sequence[Mapping]) -> dict:
    """Ближайшая выплата годового плательщика при квартальном календаре модели (П§2): запись — по ближайшей будущей
    экс-дате; без записи — год прибыли, последнее решение за который (за четвёртый квартал) не раньше квартала даты
    оценки. DPS, риск отмены и срез — года прибыли (строка `dividends.model`: суммы кварталов прибыли года);
    норматив — в квартале регуляторного вычета решения за четвёртый квартал; доходность — годовая."""
    b, cal, tl = x.book, x.cal, x.tl
    q0 = x.run.ctx.clock.q0

    def day(r: Mapping[str, Any]) -> str | None:
        got = r.get("ex_date") or r.get("record_date")
        return str(got)[:10] if got else None

    def upcoming(r: Mapping[str, Any]) -> bool:
        ahead = bool(day(r)) and date.fromisoformat(day(r)) > x.v
        if r.get("status") == "recommended":
            return ahead or not day(r)
        return r.get("status") == "declared" and ahead

    recs = sorted((r for r in x.rel.live_report.records if upcoming(r)),
                  key=lambda r: (day(r) is None, day(r) or "", int(r["year"]), str(r.get("period") or "")))
    rec = recs[0] if recs else None
    last_slot = lambda y: cal.periods.get(period_str(y, 4))  # noqa: E731
    if rec is not None:
        year, status = int(rec["year"]), str(rec["status"])
    else:
        year = next((y for y in sorted(cal.years) if last_slot(y) is not None and last_slot(y).dps is None
                     and last_slot(y).q >= q0), x.years[0])
        status = "model"
    mrow = next((r for r in model if r["year"] == year), None)
    # главная цифра без объявления — ожидание модели по клеткам (`dps_mean`), DPS политики — рядом (П§2): капитал
    # срезает годовую выплату до жетона в большей части массы, и выплаты по политике может не быть ни в одной клетке
    dps = float(rec["dps"]) if rec is not None else (mrow["dps"] if mrow else None)
    slot = last_slot(year)
    events = (x.facts.file("calendar").get("events") or []) if "calendar" in x.facts.files else []
    ev = next((e for e in events if e.get("kind") == "record" and (str(e.get("covers")) in (str(year), period_str(year, 4))
                                                                  or str(e.get("date", ""))[:4] == str(year + 1))), None)
    record = _iso(rec.get("record_date")) if rec else None
    est = record or (_iso(ev.get("date")) if ev else None)
    note = ("дата отсечки из реестра" if record else
            ("оценка по календарю событий" + (" (окно)" if ev and ev.get("precision") == "window" else ""))
            if ev else "оценки даты нет в календаре фактов")
    gap = _median_gap_days(x)
    pay_est = None if est is None or gap is None else (date.fromisoformat(est) + timedelta(days=gap)).isoformat()
    q_chk = slot.q_reg if slot is not None else (tl.q_of_date(date.fromisoformat(record)) if record else None)
    n20e = x.ratio(x.p_an, "n20", q_chk) if q_chk is not None and 0 <= q_chk <= tl.Q else None
    out = {"year": year, "status": status, "dps": R_DPS(dps), "dps_policy": mrow["dps_policy"] if mrow else None,
           "dps_mean": mrow["dps"] if mrow else None, "dps_p10": mrow["dps_p10"] if mrow else None,
           "dps_p90": mrow["dps_p90"] if mrow else None, "p_cancel": mrow["p_zero"] if mrow else None,
           "record_date": record, "record_date_est": est, "record_date_note": note,
           "pay_date_est": _iso(rec.get("pay_date")) if rec and rec.get("pay_date") else pay_est,
           "yield": {t: R_SHARE(None if dps is None else dps / x.prices[t]) for t in x.tickers},
           "condition": {"metric": b.get("dividends.policy.metric"), "threshold": b.get("dividends.policy.threshold"),
                         "n20_expected": R_SHARE(n20e), "p_limited": mrow["p_cut"] if mrow else None}}
    if rec is not None and rec.get("period"):
        out["period"] = str(rec["period"])
    out["label"] = record_label(b, year, period_str(year, 4), rec.get("label") if rec else None)
    if rec and rec.get("last_buy_date"):
        out["last_buy_date"] = _iso(rec.get("last_buy_date"))
    return out


def _next_expected(x: _Ctx, model: Sequence[Mapping]) -> dict:
    if annual_payer(x):
        return _next_expected_annual(x, model)
    if x.cal is not None:
        return _next_expected_quarterly(x)
    b = x.book
    agm = int(b.get("dividends.calendar.agm_quarter"))
    reg_q = int(b.get("dividends.calendar.reg_deduction_quarter"))
    q0 = x.run.ctx.clock.q0
    def upcoming(r: Mapping[str, Any]) -> bool:
        """Запись — ближайшая выплата: отсечка впереди; рекомендация без даты — тоже; рекомендация с
        прошедшей отсечкой ближайшей выплатой не считается (М§15)."""
        day = r.get("ex_date") or r.get("record_date")
        ahead = bool(day) and date.fromisoformat(str(day)[:10]) > x.v
        if r.get("status") == "recommended":
            return ahead or not day
        return r.get("status") == "declared" and ahead

    recs = sorted((r for r in x.rel.live_report.records if upcoming(r)), key=lambda r: int(r["year"]))
    rec = recs[0] if recs else None
    if rec is not None:
        year, status = int(rec["year"]), str(rec["status"])
    else:
        year = next((y for y in x.years if x.tl.index(period_str(y + 1, agm)) >= q0), x.years[0])
        status = "model"
    mrow = next((r for r in model if r["year"] == year), None)
    # главная цифра: объявленный или рекомендованный DPS реестра, при статусе model — DPS политики (П§2)
    dps = float(rec["dps"]) if rec is not None else (mrow["dps_policy"] if mrow else None)
    cancel = 0.0
    for c in x.run.cells:
        d = next((d for d in c.decisions if d.year == year), None)
        if d is not None and (d.source == "crisis_skip" or abs(d.dps) < EPS):
            cancel += x.p_an[c.key]
    cal = (x.facts.file("calendar").get("events") or []) if "calendar" in x.facts.files else []
    ev = next((e for e in cal if e.get("kind") == "record" and str(e.get("date", ""))[:4] == str(year + 1)), None)
    record = _iso(rec.get("record_date")) if rec else None
    est = record or (_iso(ev.get("date")) if ev else None)
    note = ("дата отсечки из реестра" if record else
            ("оценка по календарю событий" + (" (окно)" if ev and ev.get("precision") == "window" else ""))
            if ev else "оценки даты нет в календаре фактов")
    gap = _median_gap_days(x)
    pay_est = None if est is None or gap is None else (date.fromisoformat(est) + timedelta(days=gap)).isoformat()
    q_chk = x.tl.index(period_str(year + 1, reg_q))
    n20e = x.ratio(x.p_an, "n20", q_chk) if 0 <= q_chk <= x.tl.Q else None
    limited = 0.0
    for c in x.run.cells:
        d = next((d for d in c.decisions if d.year == year), None)
        if d is not None and d.cut:
            limited += x.p_an[c.key]
    out = {"year": year, "status": status, "dps": R_DPS(dps), "dps_policy": mrow["dps_policy"] if mrow else None,
           "dps_mean": mrow["dps"] if mrow else None, "dps_p10": mrow["dps_p10"] if mrow else None,
           "dps_p90": mrow["dps_p90"] if mrow else None, "p_cancel": R_PROB(cancel if mrow else None),
           "record_date": record, "record_date_est": est, "record_date_note": note,
           "pay_date_est": _iso(rec.get("pay_date")) if rec and rec.get("pay_date") else pay_est,
           "yield": {t: R_SHARE(None if dps is None else dps / x.prices[t]) for t in x.tickers},
           "condition": {"metric": b.get("dividends.policy.metric"), "threshold": b.get("dividends.policy.threshold"),
                         "n20_expected": R_SHARE(n20e), "p_limited": R_PROB(limited)}}
    if rec and rec.get("last_buy_date"):
        out["last_buy_date"] = _iso(rec.get("last_buy_date"))
    return out


def _dividends(x: _Ctx, n20_post: float) -> dict:
    b, f = x.book, x.facts
    pol_f = f.file("dividends").get("policy") or {}
    payout = Trajectory(b.get("dividends.policy.payout"))
    steps = [{"payout": float(s["payout"]), "threshold": float(s["threshold"])}
             for s in b.get("dividends.policy.steps") or []]
    threshold = float(b.get("dividends.policy.threshold"))
    ladder_steps = steps or [{"payout": payout.year_value(x.years[0]), "threshold": threshold}]
    ladder = []
    current_set = False
    for i, s in enumerate(ladder_steps):
        if not s["threshold"] > 0:
            continue                            # ступень без порога норматива не печатается (П§2)
        cur = not current_set and n20_post >= s["threshold"]
        current_set = current_set or cur
        ladder.append({"key": f"step{i + 1}", "title": f"Доля {pct(s['payout'], 0)} прибыли",
                       "condition": b.label("dividends.ladder_condition", threshold=pct(s["threshold"])),
                       "payout": s["payout"],
                       "current": cur})
    if ladder:
        ladder.append({"key": "residual", "title": b.label("dividends.ladder_residual_title"),
                       "condition": b.label("dividends.ladder_residual_condition"),
                       "payout": None, "current": not current_set})
    else:                                       # порога нет ни у одной ступени: одна строка — выплата по политике
        ladder.append({"key": "policy", "title": b.label("dividends.ladder_residual_title"),
                       "condition": b.label("dividends.ladder_residual_condition"),
                       "payout": ladder_steps[0]["payout"], "current": True})
    in_bridge = {_record_id(r) for r in x.run.bridge_rows if r["sign"] != 0}     # по ключу записи
    register = []
    for r in x.rel.live_report.records:
        row = {"year": int(r["year"]), "dps": float(r["dps"]),
               "amount": R_MONEY(float(r["dps"]) * x.n_iss / 1000), "record_date": _iso(r.get("record_date")),
               "last_buy_date": _iso(r.get("last_buy_date")), "ex_date": _iso(r.get("ex_date")),
               "pay_date": _iso(r.get("pay_date")), "status": r.get("status"),
               "in_bridge": _record_id(r) in in_bridge, "sources": list(r.get("sources") or []),
               **_period_words(r)}
        if r.get("period") and r.get("decided_date"):
            row["decided_date"] = _iso(r.get("decided_date"))
        register.append(row)
    history = []
    for r in sorted(f.file("dividends").get("history_before") or [], key=_history_year) + \
            (f.file("dividends").get("history") or []):
        dps = history_dps(r)
        pool, ni = _node_v(r.get("pool_declared")), _node_v(r.get("ni_shareholders"))
        node = r.get("dps") if r.get("dps") is not None else r.get("dps_ordinary")
        history.append({"year": _history_year(r), "dps": dps, "dps_preferred": _node_v(r.get("dps_preferred")),
                        "pool": pool, "payout_ratio": R_SHARE(None if pool is None or not ni else pool / ni),
                        "record_date": _one_day(r.get("record_date")), "ex_date": _one_day(r.get("ex_date")),
                        "pay_date": _one_day(r.get("pay_date")), "ni_shareholders": ni,
                        "src": (_src_words(f, node.get("src") or node.get("calc"))
                                if isinstance(node, Mapping) else None),
                        **_period_words(r),
                        **{k: _node_v(r[k]) for k in ("dps_pre_split", "split_factor") if k in r}})
    # проверка истории выплат — вида, заданного книгой (М§5.2): формула «до копейки» или потолок политики
    kind = history_test(b)
    formula = [{k: row[k] for k in ("year", "ni_shareholders", "at1_coupon", "tax_statutory", "base", "pool",
                                    "dps_exact", "dps_rounded", "dps_declared", "rounding", "ok")}
               for row in (dps_history(b, f) if kind == HISTORY_EXACT else [])]
    for row in formula:
        row["base"], row["pool"] = rnd(row["base"], 0.001), rnd(row["pool"], 0.0001)
        row["dps_exact"] = rnd(row["dps_exact"], 0.00001)
    by_kind: dict[str, Any] = {}
    policy_kind: dict[str, Any] = {} if b.opt("dividends.policy.history_test") is None else {"history_test": kind}
    if kind == HISTORY_CAP:
        policy_kind["cap"] = float(b.get("dividends.policy.cap"))
        by_kind["cap_check"] = [{**row, "pool": rnd(row["pool"], 0.001), "share": R_SHARE(row["share"])}
                                for row in cap_history(b, f)]
    # параметры календаря — значения книги: только ключи, которые книга несёт (П§2 `dividends.policy`)
    for field_, dotted in (("frequency", "dividends.calendar.frequency"),
                           ("base_window_quarters", "dividends.policy.base_window_quarters"),
                           ("decision_lag_quarters", "dividends.calendar.decision_lag_quarters")):
        if b.opt(dotted) is not None:
            policy_kind[field_] = copy.deepcopy(b.opt(dotted))
    # частота выплат — по документу политики (факты), когда он её называет: календарь модели бывает мельче
    # (решения по кварталам прибыли при годовой выплате эмитента — собрание раз в год)
    if pol_f.get("frequency") in FREQUENCIES:
        policy_kind["frequency"] = str(pol_f["frequency"])
    model = _dividends_model_cache(x)
    if x.cal is not None:
        by_kind["model_quarters"] = _model_quarters(x)
        window = _declared_quarters(x)
        if window is not None:                  # кварталы прибыли, по которым посчитана доходность за 12 месяцев
            by_kind["yield_ltm_periods"] = window[0]
    if _amount_basis(b):                        # суммы блока — пул на все размещённые акции
        by_kind["amount_basis"] = AMOUNT_ISSUED
    # документ политики — названием из фактов (`doc_title`), когда оно есть; без него — прежнее поле `doc`
    return {"policy": {"name": b.get("dividends.policy.name"), "text": pol_f.get("text"),
                       "doc": pol_f.get("doc_title") or pol_f.get("doc"),
                       "sha256": pol_f.get("sha256"), "approved": _iso(pol_f.get("approved")),
                       "valid_until": _iso(_node_v(pol_f.get("valid_until"))),
                       **({"valid_until_note": str(pol_f["valid_until_note"])} if pol_f.get("valid_until_note") else {}),
                       "base": b.get("dividends.policy.base"),
                       "payout": [{"year": y, "value": payout.year_value(y)} for y in x.years],
                       "metric": b.get("dividends.policy.metric"), "threshold": threshold, "steps": steps,
                       "shortfall_rule": b.get("dividends.policy.shortfall_rule"),
                       "deduct_at1_after_tax": bool(b.get("dividends.policy.deduct_at1_after_tax")),
                       "divisor": b.get("dividends.policy.divisor"),
                       "excess": {"from_profit_year": int(b.get("dividends.excess.from_profit_year")),
                                  "epsilon": float(b.get("dividends.excess.epsilon")),
                                  "ramp_years": int(b.get("dividends.excess.ramp_years"))},
                       "crisis": {"skip_in_shock_year": bool(b.get("dividends.crisis.skip_in_shock_year")),
                                  "catch_up": b.get("dividends.crisis.catch_up")}, **policy_kind},
            "ladder": ladder, "register": register, "history": history, "formula_check": formula, **by_kind,
            "model": model,
            "next_expected": _next_expected(x, model), "yield_ltm": _yield_ltm(x), "basis": "ifrs",
            **_optional("buyback", _buyback(x)), **_optional("token", _token(x, model))}


def _optional(key: str, node: Any) -> dict:
    return {} if node is None else {key: node}


def _cell_weights(x: _Ctx, cells: Sequence[Any]) -> dict[str, float]:
    """Веса клеток внутри мира: вероятности слоя «свой взгляд», нормированные на мир (при нулевой массе мира в
    слое — поровну). Условные веса режима и сценария в мире у слоёв одни и те же."""
    w = {c.key: x.p_an[c.key] for c in cells}
    total = sum(w.values())
    if total <= EPS:
        return {c.key: 1.0 / len(cells) for c in cells}
    return {k: v / total for k, v in w.items()}


def _buyback(x: _Ctx) -> dict | None:
    """Выкуп акций по цене мира (М§5.6, ключ `dividends.buyback`) — для витрины (П§2 `dividends.buyback`): суммы по
    годам и путь акций смеси заголовка, делитель после выкупа (акции в обращении на конце последнего квартала
    покупок), средняя цена покупок — смеси, по годам и по мирам (сумма / купленные акции: цена мира — форвард его
    рынка). Без ключа или при выключенном — None. Чисел модели блок не меняет: он читает ряды клеток."""
    bb_spec = getattr(x.prep, "bb", None)
    cells = x.run.cells
    if bb_spec is None or not cells or "bb" not in cells[0].quarters:
        return None
    tl, p = x.tl, x.p_mix
    Q = tl.Q

    def amount(c: Any, q: int) -> float:
        return float(c.quarters["bb"][q] or 0.0)

    def bought(c: Any, q: int) -> float:          # млн акций, купленных клеткой в квартале q
        b = amount(c, q)
        return 0.0 if b <= EPS else 1000.0 * b / float(c.quarters["p_bar"][q])

    active = [q for q in range(1, Q + 1) if any(amount(c, q) > EPS for c in cells)]
    if not active:
        return None
    last = active[-1]

    def mix(fn: Any, qs: Sequence[int]) -> float:
        return sum(p[c.key] * sum(fn(c, q) for q in qs) for c in cells)

    years = []
    for y in x.years:
        qs = [q for q in tl.quarters_of_year(y) if 1 <= q <= Q and q in active]
        if not qs:
            continue
        amt, sh = mix(amount, qs), mix(bought, qs)
        end_q = max(q for q in tl.quarters_of_year(y) if q <= Q)
        years.append({"year": y, "amount": R_MONEY(amt), "price": R_PRICE(None if sh <= EPS else 1000.0 * amt / sh),
                      "shares_bought_mln": rnd(sh, PRECISION["shares"]),
                      "shares_end_mln": rnd(x.E(p, "n_out", end_q), PRECISION["shares"])})
    by_world = {}
    for w in x.worlds:
        cw = [c for c in cells if c.world == w]
        if not cw:
            continue
        wt = _cell_weights(x, cw)
        amt = sum(wt[c.key] * sum(amount(c, q) for q in active) for c in cw)
        sh = sum(wt[c.key] * sum(bought(c, q) for q in active) for c in cw)
        by_world[w] = {"price": R_PRICE(None if sh <= EPS else 1000.0 * amt / sh),
                       "divisor_after_mln": rnd(sum(wt[c.key] * float(c.quarters["n_out"][last]) for c in cw),
                                                PRECISION["shares"])}
    amt, sh = mix(amount, active), mix(bought, active)
    return {"title": x.book.label("control.lines.buyback"), "price_rule": str(bb_spec.rule),
            "price_book": rnd(bb_spec.p_book, 1e-4),
            "closed": [{"period": tl.period(q), "price": rnd(v, 1e-4)} for q, v in sorted(bb_spec.closed.items())],
            "first_period": tl.period(active[0]), "last_period": tl.period(last),
            "shares_start_mln": rnd(x.n_out, PRECISION["shares"]), "amount": R_MONEY(amt),
            "shares_bought_mln": rnd(sh, PRECISION["shares"]),
            "price": R_PRICE(None if sh <= EPS else 1000.0 * amt / sh),
            "divisor_after_mln": rnd(x.E(p, "n_out", last), PRECISION["shares"]),
            "years": years, "by_world": by_world}


def _token(x: _Ctx, model: Sequence[Mapping[str, Any]]) -> dict | None:
    """Жетон DPS (К1, ключ `dividends.min_dps`) — для витрины (П§2 `dividends.token`): минимум DPS за год прибыли и
    по годам — масса клеток слоя «свой взгляд», где жетон вошёл в решение (рост урезан под выплату минимума), и
    ожидаемый DPS года. Без ключа или при нулевом минимуме — None."""
    years_min = getattr(x.prep, "min_dps", None)
    if not years_min or not any(float(v) > EPS for v in years_min.values()):
        return None
    dps = {int(r["year"]): r.get("dps") for r in model}
    rows = []
    for y in sorted(int(k) for k in years_min):
        m = float(years_min[y])
        if m <= EPS or y not in dps:
            continue
        mass = sum(x.p_an[c.key] for c in x.run.cells
                   if any(d.year == y and float(getattr(d, "token", 0.0)) > EPS for d in c.decisions))
        rows.append({"year": y, "min_dps": R_DPS(m), "p_token": R_PROB(mass), "dps": dps[y]})
    if not rows:
        return None
    return {"min_dps": rows[0]["min_dps"], "years": rows}


# ------------------------------------------------------------------ paths


def _annual_path(x: _Ctx) -> list[dict]:
    p = x.p_mix
    out = []
    prev_fees = None
    ay = x.tl.anchor_year
    fees_prev_year = x.flow(p, "fees", ay - 1)
    for y in x.years:
        # потоки, средние остатки и отношения года смеси — одна функция с узлами уровней и пути смеси (М§14.5)
        m = mix_year(x.run, p, y)
        f = m["flows"]
        model_qs = [q for q in x.tl.quarters_of_year(y) if 1 <= q <= x.tl.Q]
        fact_qs = [q for q in x.tl.quarters_of_year(y) if q <= 0]
        extra = {k: (sum(x.E(p, k, q) for q in model_qs) if model_qs else 0.0)
                 for k in ("fvc", "one_off", "oci", "ci", "div")}
        extra["fvr"] = m["fvr"]
        avg_bv = m["avg_bv"]
        nim, cor, cir, mgmt = m["nim"], m["cor"], m["cir"], m["mgmt"]
        qe = _q_end(x, y)
        ok = 0 <= qe <= x.tl.Q
        e = lambda name: x.E(p, name, qe) if ok else None  # noqa: E731
        rwa = e("rwa")
        # средства клиентов конца года (Р11-2): при volumes.funds_scope: clients — без книг К6, функцией гейтов
        # (`client_funds_end`: тот же ключ checks.client_funds: clients — правило схемы); иначе — ряд funds смеси
        funds_end = (e("funds") if x.prep.funds_words is None or not ok
                     else sum(p[c.key] * client_funds_end(x.run.ctx, c, qe) for c in x.run.cells))
        dps = [r for r in _dividends_model_cache(x) if r["year"] == y]
        fees_base = fees_prev_year if y == ay else prev_fees
        # переоценка облигаций по СС — внутри «прочего»; FVC и разовые статьи — своими строками (П§2)
        other = None if f["misc"] is None else f["misc"] + extra["fvr"]
        row = {"year": y, "fact_quarters": len(fact_qs), "nii": R_MONEY(f["nii"]), "nim": R_SHARE(nim),
               "nim_mgmt": R_SHARE(mgmt["nim"]), "fees": R_MONEY(f["fees"]),
               "fees_growth": R_SHARE(None if f["fees"] is None or not fees_base else f["fees"] / fees_base - 1),
               "insurance": R_MONEY(f["ins"]), "other": R_MONEY(other), "noncore": R_MONEY(f["noncore"]),
               "opex": R_MONEY(f["opex"]), "cir": R_SHARE(cir), "cir_mgmt": R_SHARE(mgmt["cir"]),
               "llp": R_MONEY(f["llp"]), "cor": R_SHARE(cor), "cor_mgmt": R_SHARE(mgmt["cor"]),
               "fvc": R_MONEY(extra["fvc"]), "one_off": R_MONEY(extra["one_off"]), "pbt": R_MONEY(f["pbt"]),
               "tax": R_MONEY(f["tax"]), "ni": R_MONEY(f["ni"]), "ni_sh": R_MONEY(f["ni_sh"]),
               "oci": R_MONEY(extra["oci"] if not fact_qs else None), "ci": R_MONEY(extra["ci"] if not fact_qs else None),
               "roe": R_SHARE(None if f["ni_sh"] is None or not avg_bv else f["ni_sh"] / avg_bv),
               "roe_ci": R_SHARE(None if fact_qs or not avg_bv else extra["ci"] / avg_bv),
               "bv_end": R_MONEY(e("bv")), "rwa_end": R_MONEY(rwa),
               "n20_end": R_SHARE(x.ratio(p, "n20", qe) if ok else None),
               "n11_end": R_SHARE(x.ratio(p, "n11", qe) if ok else None), "req20_end": R_SHARE(e("req20")),
               "floor20_end": R_SHARE(e("floor20")), "loans_end": R_MONEY(e("loans")), "funds_end": R_MONEY(funds_end),
               "assets_end": R_MONEY(e("assets")), "dps": dps[0]["dps"] if dps else None,
               "payout": dps[0]["payout"] if dps else None,
               "div_paid": R_MONEY(extra["div"] + _fact_div_paid(x, y, fact_qs))}
        prev_fees = f["fees"]
        out.append(row)
    return out


def _dividends_model_cache(x: _Ctx) -> list[dict]:
    if not hasattr(x, "_div_model"):
        x._div_model = _dividends_model(x)
    return x._div_model


def _fact_div_paid(x: _Ctx, year: int, fact_qs: Sequence[int]) -> float:
    """Дивиденд, вычтенный из BV в отчётных кварталах года (ГОСА года — пул прошлого года прибыли)."""
    if not fact_qs:
        return 0.0
    if x.cal is not None:
        # квартальный календарь: решения собраний, пришедшиеся на отчётные кварталы года, — оттоком по акциям
        # в обращении (П§2 `paths.annual[].div_paid`)
        total = 0.0
        for r in x.facts.file("dividends").get("history") or []:
            decided, pool = _node_v(r.get("decided_date")), _node_v(r.get("pool_declared"))
            if decided and pool is not None and x.tl.q_of_date(to_date(decided)) in fact_qs:
                total += float(pool) * x.n_out / x.n_iss
        return total
    agm = int(x.book.get("dividends.calendar.agm_quarter"))
    if x.tl.index(period_str(year, agm)) not in fact_qs:
        return 0.0
    for r in x.facts.file("dividends").get("history") or []:
        if int(r["year"]) == year - 1 and _node_v(r.get("pool_declared")) is not None:
            return float(_node_v(r["pool_declared"]))
    return 0.0


def _quarters_path(x: _Ctx) -> list[dict]:
    p, br = x.p_mix, x.br
    out = []
    for q in range(1, min(QUARTERS_SHOWN, x.tl.Q) + 1):
        d = x.tl.d(q)
        e = lambda name: x.E(p, name, q)  # noqa: E731
        nim = e("nii") * DAYS_IN_YEAR / d / e("iea_avg")
        cor = e("llp") * DAYS_IN_YEAR / d / e("loans_ac_avg")
        out.append({"period": x.tl.period(q), "fact": False, "nii": R_MONEY(e("nii")), "nim": R_SHARE(nim),
                    "nim_mgmt": R_SHARE(br.to_mgmt_nim(nim)), "llp": R_MONEY(e("llp")), "cor": R_SHARE(cor),
                    "cor_mgmt": R_SHARE(br.to_mgmt_cor(cor)), "fees": R_MONEY(e("fees")), "opex": R_MONEY(e("opex")),
                    "ni_sh": R_MONEY(e("ni_sh")), "bv": R_MONEY(e("bv")), "n20": R_SHARE(x.ratio(p, "n20", q)),
                    "n11": R_SHARE(x.ratio(p, "n11", q)), "req20": R_SHARE(e("req20")),
                    "floor20": R_SHARE(e("floor20"))})
    return out


def _roe_tree(x: _Ctx) -> list[dict]:
    p = x.p_mix
    out = []
    for y in x.years:
        f = {k: x.flow(p, k, y) for k in ("nii", "fees", "ins", "misc", "noncore", "opex", "llp", "tax", "ni_sh")}
        if any(v is None for v in f.values()):
            continue
        model_qs = [q for q in x.tl.quarters_of_year(y) if 1 <= q <= x.tl.Q]
        extra = {k: sum(x.E(p, k, q) for q in model_qs) for k in ("fvr", "fvc", "one_off", "ot")}
        qs = x.tl.quarters_of_year(y)
        ends = [q for q in [qs[0] - 1] + qs if q <= x.tl.Q]
        pairs = [(x.end(p, "assets", q), x.end(p, "bv", q)) for q in ends]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if not pairs:
            continue
        assets = sum(a for a, _ in pairs) / len(pairs)
        bv = sum(b for _, b in pairs) / len(pairs)
        roa = f["ni_sh"] / assets
        lev = assets / bv
        out.append({"year": y, "nii_to_assets": R_SHARE(f["nii"] / assets), "fees_to_assets": R_SHARE(f["fees"] / assets),
                    "other_to_assets": R_SHARE((f["ins"] + f["misc"] + extra["fvr"] - extra["fvc"] + extra["one_off"]) / assets),
                    "noncore_to_assets": R_SHARE(f["noncore"] / assets), "opex_to_assets": R_SHARE(-f["opex"] / assets),
                    "llp_to_assets": R_SHARE(-f["llp"] / assets), "tax_to_assets": R_SHARE(-(f["tax"] + extra["ot"]) / assets),
                    "roa": roa, "leverage": lev, "roe": roa * lev, "ends": len(pairs)})
    for r in out:      # хранимая точность; roe — произведение хранимых roa и leverage
        r["roa"], r["leverage"] = rnd(r["roa"], EPS), rnd(r["leverage"], EPS)
        r["roe"] = rnd(r["roa"] * r["leverage"], EPS)
    return out


def _paths(x: _Ctx) -> dict:
    p = x.p_mix
    term = {k: sum(p[c.key] * getattr(c, k) for c in x.run.cells) for k in ("roe_t", "k_t", "g_t", "x_t")}
    annual = _annual_path(x)
    return {"mix": {"title": "смесь заголовка: λ × «свой взгляд» + (1 − λ) × «рыночные ставки как есть»",
                    "lambda": x.lam},
            "annual": annual, "quarters": _quarters_path(x), "roe_tree": _roe_tree(x),
            "terminal": {"roe_t": R_SHARE(term["roe_t"]), "k_t": R_SHARE(term["k_t"]), "g_t": R_SHARE(term["g_t"]),
                         "x_t": R_MONEY(term["x_t"]), "payout_t": R_SHARE(1 - term["g_t"] / term["roe_t"]),
                         "fade": float(x.book.get("valuation.terminal.fade"))},
            "fade": _fade(x, annual, term), **_level_nodes(x)}


def _level_nodes(x: _Ctx) -> dict:
    """Узлы «на чём стоит заголовок» (П§2, М§14.5), каждый при своём ключе книги: `levels` — уровни после фазы
    роста модальной клетки, слоя «свой взгляд», смеси заголовка и слоя «рыночные ставки как есть» (ключ
    `checks.window_backtest`); `modal_cell` — модальная клетка рядом с путём смеси: её вес в слое «свой взгляд» и
    в смеси заголовка, цена на акцию и прибыль акционеров по годам пути (ключ `checks.point_path`); `funding` —
    кредиты к средствам клиентов и доля оптового фондирования на дату якоря и на конец года у смеси заголовка и
    модальной клетки (ключ `checks.wholesale_share`)."""
    out: dict[str, Any] = {}
    node = levels(x.run)                        # с подузлом окна фактов `window` — при его полях в ключе книги
    if node is not None:
        out["levels"] = {"from_year": node["from_year"], "to_year": node["to_year"], "cell": node["cell"],
                         "order": list(node["order"]),
                         "rows": {key: {"title": row["title"], **{k: R_SHARE(row[k]) for k in LEVEL_METRICS},
                                        # множители CoR по книгам: CoR на составе якоря — рядом (М§4.6)
                                        **({"cor_mix0": R_SHARE(row["cor_mix0"])} if "cor_mix0" in row else {})}
                                  for key, row in node["rows"].items()}}
        if node.get("window") is not None:      # окно фактов — мерка уровней: подузел, не строка
            out["levels"]["window"] = {name: {k: R_SHARE(v) for k, v in part.items()}
                                       for name, part in node["window"].items()}
    if x.book.opt(POINT_PATH) is True:
        key = modal_cell(x.book, x.run.ctx.posterior)
        c = x.run.cell(*key)
        out["modal_cell"] = {"cell": c.label, "p_analytical": R_PROB(x.p_an[key]), "p_point": R_PROB(x.p_mix[key]),
                             "price": R_PRICE(x.run.cell_price(c)), "years": list(x.years),
                             "ni_sh": [R_MONEY(c.annual["ni_sh"][c.years.index(y)]) if y in c.years else None
                                       for y in x.years]}
    path = funding_path(x.run)
    if path is not None:
        out["funding"] = {"years": list(path["years"]), "cell": path["cell"],
                          "anchor": {k: R_SHARE(path["anchor"][k]) for k in FUNDING_METRICS},
                          **{part: {k: [R_SHARE(v) for v in path[part][k]] for k in FUNDING_METRICS}
                             for part in ("mix", "modal_cell")}}
    return out


def _fade(x: _Ctx, annual: Sequence[Mapping], term: Mapping[str, float]) -> dict:
    """`paths.fade` (П§2): путь ROE и роста капитала к терминалу — по годам годового пути ROE, рост капитала
    конца года г/г и ожидание стоимости капитала года (годовая ставка по дисконту между концами лет; год даты
    оценки — от даты оценки); терминал — ROE до и после угасания, стоимость капитала и рост (смесь заголовка)."""
    p, tl, clock = x.p_mix, x.tl, x.run.ctx.clock
    by_world: dict[str, list[float | None]] = {}
    for w, disc in x.run.ctx.discounts.items():
        row = []
        for y in x.years:
            qs = [q for q in tl.quarters_of_year(y) if clock.q0 <= q <= tl.Q]
            span = clock.tau[qs[-1]] - clock.tau[qs[0] - 1] if qs else 0.0
            row.append((disc.dfq[qs[0] - 1] / disc.dfq[qs[-1]]) ** (1 / span) - 1 if span > 0 else None)
        by_world[w] = row
    k, growth = [], []
    for i, y in enumerate(x.years):
        vals = [(p[c.key], by_world[c.world][i]) for c in x.run.cells]
        k.append(None if any(v is None for _, v in vals) else R_SHARE(sum(w * v for w, v in vals)))
        qe, qp = _q_end(x, y), _q_end(x, y - 1)
        end = x.end(p, "bv", qe) if 0 <= qe <= tl.Q else None
        prev = x.end(p, "bv", qp)
        growth.append(R_SHARE(None if end is None or not prev else end / prev - 1))
    return {"years": list(x.years), "roe": [r["roe"] for r in annual], "bv_growth": growth, "k": k,
            "roe_t_raw": R_SHARE(sum(p[c.key] * c.roe_t_raw for c in x.run.cells)),
            "roe_t": R_SHARE(term["roe_t"]), "k_t": R_SHARE(term["k_t"]), "g_t": R_SHARE(term["g_t"]),
            "fade": float(x.book.get("valuation.terminal.fade"))}


# ------------------------------------------------------------------ nii, guidance, governance


def _nii(x: _Ctx, invariants: Mapping[str, Finding]) -> dict:
    b, run = x.book, x.run
    tr = run.ctx.transmission
    Q = x.tl.Q
    ref = {w: run.cell(w, "norm", "schedule") for w in x.worlds} if "norm" in x.regimes else {}
    books = []
    floors = b.get("checks.lt_spread_floor")
    for key, spec in b.get("nii.books").items():
        eff = tr.lt_spread.get(key)             # эффективный LT-спред к опоре мира — у кредитных книг (М§4.5)
        # у пассива с phi — добавка φ_L × X_W к стоимости (М§4.4); у прочих книг — спред пути со сдвигом σ0; доля сжатия
        # книги между мирами (Р11-1) — сдвигом −share (ref_W − ref_H) (у кредитных книг он уже в эффективном LT-спреде)
        add = tr.phi_liab if spec["side"] == "liability" and spec.get("phi") else 0.0
        shl = tr.share_lt.get(key)

        def spread_lt(w: str, eff=eff, add=add, shl=shl, key=key) -> float:
            if eff is not None:
                return eff[w]
            s = x.prep.spreads[key][Q] + add * tr.x_lt.get(w, 0.0)
            return s if shl is None else s + shl[w]

        row = {"key": key, "title": str(spec["name"]), "side": spec["side"], "ref": spec["ref"],
               "rho": spec["rho"], "phi": bool(spec.get("phi")), "balancing": bool(spec.get("balancing")),
               "balance_anchor": R_MONEY(x.af.balances.get(key)), "rate_anchor": R_SHARE(x.af.rates.get(key)),
               "spread_lt": R_SHARE(Trajectory(spec["spread"]).year_value(x.tl.last_year)),
               "spread_lt_world": {w: R_SHARE(spread_lt(w)) for w in x.worlds},
               "spread_floor": None if key not in floors else float(floors[key]),
               "rate_lt": {w: R_SHARE(c.books[key]["rate"][Q]) for w, c in ref.items()}}
        if "beta" in spec:
            row["beta"] = spec["beta"]
        if key in x.prep.phi_share:             # Р11-1: доля сжатия книги между мирами (только ≠ 0)
            row["phi_share"] = x.prep.phi_share[key]
        books.append(row)
    ts = invariants.get("transmission_solved")
    nim_by = {"years": list(x.years)}
    cs = {"c_ref": x.prep.c_ref, "psi": x.prep.psi, "bounds": list(x.prep.c_bounds), "by_world": {}}
    for w in x.worlds:
        prob = cell_probabilities(b, {v: (1.0 if v == w else 0.0) for v in x.worlds}, run.ctx.posterior)
        vals = []
        for i, _y in enumerate(x.years):
            pairs = [(c.annual["nim"][i], prob[c.key]) for c in run.cells if c.world == w]
            wsum = sum(pw for v, pw in pairs if v is not None)
            vals.append(R_SHARE(x.br.to_mgmt_nim(sum(v * pw for v, pw in pairs if v is not None) / wsum)) if wsum else None)
        nim_by[w] = vals
        c = ref.get(w)
        if c is not None:
            row = []
            for y in x.years:
                qs = [q for q in x.tl.quarters_of_year(y) if 1 <= q <= Q]
                row.append(R_SHARE(sum(c.quarters["current_share"][q] for q in qs) / len(qs)) if qs else None)
            cs["by_world"][w] = row
    disc = x.fv("nii_books", "nii_per_100bp")
    printed = printed_nim_lt(run)               # печатаемая маржа после фазы роста — при ключе `checks.nim_lt`
    printed_node = {} if printed is None else {"nim_lt_printed": {
        "value": R_SHARE(printed["value"]), "target": printed["target"], "tolerance": printed["tolerance"],
        "from_year": printed["from_year"], "to_year": printed["to_year"], "cell": printed["cell"]}}
    stationary = stationary_nim(run.ctx)        # стационарная маржа мира-цели — при ключе `checks.nim_stationary`
    if stationary is not None:
        printed_node["nim_stationary"] = {"world": stationary["world"], "value": R_SHARE(stationary["value"]),
                                          "target": stationary["target"], "tolerance": stationary["tolerance"]}
    named = level_nim(run.ctx)                  # суждение об уровне маржи — при ключе `nii.transmission.level_world`
    if named is not None:
        printed_node["level"] = {"world": named["world"], "value": R_SHARE(named["value"]),
                                 "reference_world": named["reference_world"],
                                 "reference_value": R_SHARE(named["reference_value"])}
    return {"books": books,
            "transmission": {"target": float(b.get("nii.transmission.target")),
                             "definition": "разность стационарных ЧПМ миров M и N на разность их долгосрочных ключевых",
                             "realized": R_SHARE(tr.t_real), "nim_lt_target_mgmt": float(b.get("nii.nim_lt_target_mgmt")),
                             "target_eng": R_SHARE(tr.target_eng), "sigma0": R_SHARE(tr.sigma0),
                             "sigma0_liab": R_SHARE(tr.sigma0_liab), "sigma0_split": float(tr.split),
                             "phi": R_SHARE(tr.phi), "phi_assets": R_SHARE(tr.phi_assets),
                             "phi_liab": R_SHARE(tr.phi_liab), "phi_split": float(tr.phi_split),
                             "loan_margin": {w: R_SHARE(tr.loan_margin.get(w)) for w in x.worlds},
                             "tol": float(b.get("checks.transmission_tol")),
                             "solved": bool(ts is not None and not ts.fired), "roe_equiv": R_SHARE(tr.roe_equiv),
                             "pairs": _pairs(x), "pairs_range": [float(v) for v in b.get("checks.transmission_pairs")],
                             "by_world": {w: R_SHARE(v) for w, v in tr.t_local.items()},
                             "realized_cells": R_SHARE(realized_cells(run)), **printed_node},
            "nim_by_world": nim_by, "current_share": cs,
            "disclosed": {"nii_per_100bp": disc,
                          "src": "раскрытие банка (факты книги)" if disc is not None else "не раскрыто в фактах книги"}}


def _pairs(x: _Ctx) -> list[dict]:
    """Парные передачи соседних по key^LT миров (М§4.5; П§2 nii.transmission.pairs)."""
    tr = x.run.ctx.transmission
    lo, hi = (float(v) for v in x.book.get("checks.transmission_pairs"))
    out = []
    for w1, w2 in zip(tr.order, tr.order[1:]):
        key = f"{w1}_{w2}"
        v = tr.pairs.get(key)
        out.append({"from": w1, "to": w2, "key_from": R_SHARE(tr.key_lt[w1]), "key_to": R_SHARE(tr.key_lt[w2]),
                    "value": R_SHARE(v), "roe_equiv": R_SHARE(tr.pairs_roe.get(key)),
                    "inside": None if v is None else bool(lo <= v <= hi)})
    return out


def _guidance(x: _Ctx, paths: Mapping, gates: Mapping[str, Mapping]) -> dict:
    """Строки гайденса — по перечню книги `checks.guidance_items` (ключ, узел фактов, подпись, базис; М§14.2)."""
    f = x.facts
    guidance_keys = [(str(it["key"]), str(it["path"]), str(it["title"]), str(it["basis"]))
                     for it in x.book.get("checks.guidance_items")]
    item_keys = {path[len("items."):]: key for key, path, _, _ in guidance_keys}     # ключ фактов → ключ строки
    if "guidance" not in f.files:
        return {"year": None, "as_of": None, "src": None, "basis": "mgmt", "items": [], "gate": None, "revisions": []}
    g = f.file("guidance")
    gy = int(g["year"])
    ann = {r["year"]: r for r in paths["annual"]}
    mq = (f.file("mgmt_quarterly").get("quarters") or {}) if "mgmt_quarterly" in f.files else {}
    fact_periods = [x.tl.period(q) for q in x.tl.quarters_of_year(gy) if q <= 0]
    i = x.years.index(gy) if gy in x.years else None
    qe = _q_end(x, gy)
    prev_end = x.af.prev_year_end
    loans_now = {"corporate": [b for b in x.prep.roles.loans if x.prep.books[b].get("sector") == "corporate"]}
    loans_now["retail"] = [b for b in x.prep.roles.loans if b not in loans_now["corporate"]]

    # базы прошлого года узлов роста (прибыль акционеров, DPS); нет числа в фактах — узел не сравнивается
    bases: dict[str, float] = {}
    for k in GUIDANCE_GROWTH:
        if i is not None and any(key == k for key, _, _, _ in guidance_keys):
            try:
                bases.update(guidance_bases(x.run, gy, (k,)))
            except FactsError:
                pass
    # путь года клетки — тем же правилом, что у гейта и у `model_year` (М§4.6: год с отчётными кварталами)
    by_cell = {} if i is None else {c.key: guidance_values(x.run, c, gy, bases) for c in x.run.cells}

    def growth_ytd(now: Sequence[float | None], before: Sequence[float | None]) -> float | None:
        """Рост с начала года: сумма отчётных кварталов к сумме тех же кварталов прошлого года минус 1."""
        if not now or None in now or None in before or not sum(before):
            return None
        return sum(now) / sum(before) - 1

    def cell_value(c, key):
        if i is None:
            return None
        if key in ("roe", "nim", "cor_max", "cir") or key in GUIDANCE_GROWTH:
            return by_cell[c.key].get(key)
        if key == "n20_0":
            return c.annual["n20"][i]
        if key.startswith("loan_growth_") and 0 <= qe <= x.tl.Q:
            seg = key.split("_")[-1]
            base = prev_end.get(seg)
            return None if not base else sum(c.books[b]["balance"][qe] for b in loans_now[seg]) / base - 1
        if key == "fee_growth":
            return None
        return None

    def mean_mgmt(field_):
        vals = [_node_v((mq.get(p) or {}).get(field_)) for p in fact_periods]
        vals = [float(v) for v in vals if v is not None]
        return (sum(vals) / len(vals), vals) if vals else (None, [])

    items = []
    for key, path, title, basis in guidance_keys:
        try:
            node = f.node("guidance", path)
        except FactsError:
            continue
        band = None if node.get("v") is None else guidance_band(node)      # (мин, макс); открытая граница — None
        scope = str(node.get("scope") or "group")
        relation = node.get("relation") if scope == "sector" else None
        if scope == "sector":
            basis = "sector"                    # прогноз сектора, а не отчётность банка (П§0.2)
        compared = not (scope == "sector" and relation != "in_line")   # «лучше сектора» с сектором не сравнивается
        row_a = ann.get(gy) or {}
        fact, fact_vals, model = None, [], None
        if key in ("roe", "nim", "cor_max", "cir"):
            fact, fact_vals = mean_mgmt({"cor_max": "cor"}.get(key, key))
            model = {"roe": row_a.get("roe"), "nim": row_a.get("nim_mgmt"), "cor_max": row_a.get("cor_mgmt"),
                     "cir": row_a.get("cir_mgmt")}[key]
        elif key == "roe_target":               # цель эмитента — к его капиталу: факт — по его определению, а
            fact, fact_vals = mean_mgmt("roe")  # пути модели в этом определении нет — строка не сравнивается
        elif key == "op_np_growth":
            ni_hist = x.prep.hist["ni_sh"]
            fact = growth_ytd([ni_hist.get(x.tl.index(p)) for p in fact_periods],
                              [ni_hist.get(x.tl.index(p) - 4) for p in fact_periods])
            ni_year = x.flow(x.p_mix, "ni_sh", gy)
            if key in bases and ni_year is not None:
                model = ni_year / bases[key] - 1
        elif key == "dps_growth":
            hist_dps = {str(r["period"]): history_dps(r) for r in f.file("dividends").get("history") or []
                        if r.get("period")}
            decided = [p for p in (period_str(gy, n) for n in (1, 2, 3, 4)) if p in hist_dps]
            fact = growth_ytd([hist_dps[p] for p in decided],
                              [hist_dps.get(period_str(gy - 1, parse_period(p)[1])) for p in decided])
            mix = [(x.p_mix[c.key], c.dps.get(gy)) for c in x.run.cells]
            if key in bases and all(v is not None for _, v in mix):
                model = sum(w * v for w, v in mix) / bases[key] - 1
        elif key == "fee_growth":
            cur = [x.prep.hist["fees"].get(x.tl.index(p)) for p in fact_periods]
            prev = [x.prep.hist["fees"].get(x.tl.index(p) - 4) for p in fact_periods]
            if cur and None not in cur and None not in prev and sum(prev):
                fact = sum(cur) / sum(prev) - 1
            model = row_a.get("fees_growth")
        elif key == "n20_0":
            fact = x.af.n20
            model = row_a.get("n20_end")
        else:
            seg = key.split("_")[-1]
            base = prev_end.get(seg)
            if base:
                fact = sum(x.af.balances[b] for b in loans_now[seg]) / base - 1
                if 0 <= qe <= x.tl.Q:
                    model = sum(x.p_mix[c.key] * sum(c.books[b]["balance"][qe] for b in loans_now[seg])
                                for c in x.run.cells) / base - 1
        status = "n/a" if band is None or model is None or not compared else (
            "inside" if inside(band, model) else "outside")
        required = None
        k = len(fact_vals)
        if band is not None and key in ("roe", "nim", "cor_max", "cir") and 0 < 4 - k and model is not None:
            target = None
            if node.get("kind") == "point":
                target = node["v"]
            elif band[0] is not None and model < band[0]:
                target = band[0]
            elif band[1] is not None and model > band[1]:
                target = band[1]
            if target is not None:
                required = (4 * float(target) - sum(fact_vals)) / (4 - k)
        pairs = [(cell_value(c, key), x.p_an[c.key]) for c in x.run.cells]
        mass = None if band is None or not compared or all(v is None for v, _ in pairs) else sum(
            w for v, w in pairs if v is not None and not inside(band, v))
        kind = node.get("kind") or ("range" if isinstance(node.get("v"), list) else "point")
        item = {"key": key, "title": title, "basis": basis, "kind": kind, "guidance": node.get("v"),
                "scope": scope, "relation": relation,
                "fact_ytd": R_SHARE(fact), "fact_periods": fact_periods, "model_year": R_SHARE(model),
                "required_rest": R_SHARE(required), "status": status, "mass_outside": R_PROB(mass)}
        if node.get("scope_note"):
            item["scope_note"] = str(node["scope_note"])
        items.append(item)
    gate = gates.get("guidance_gap") or {}
    have = {i["key"] for i in items}
    revisions = []
    for h in g.get("history") or []:          # ключ пересмотра — ключ строки items (П§2); без строки — не печатается
        rkey = item_keys.get(str(h.get("key")), str(h.get("key")))
        if rkey in have:
            revisions.append({"date": _iso(h.get("date")), "key": rkey, "value": _node_v(h.get("value")),
                              "event": h.get("event")})
    # источник блока — узел первого по перечню пункта с числом
    src_node = {}
    for _key, path, _title, _basis in guidance_keys:
        try:
            node = f.node("guidance", path)
        except FactsError:
            continue
        if node.get("v") is not None:
            src_node = node
            break
    return {"year": gy, "as_of": _iso(g.get("as_of")), "src": _src_words(f, src_node.get("src")), "basis": "mgmt",
            "items": items,
            "gate": {"name": "guidance_gap", "fired": gate.get("fired"), "mass": gate.get("mass"),
                     "explanation": gate.get("explanation"), "valid_until": gate.get("valid_until")},
            "revisions": revisions}


def _off_band_block(x: _Ctx) -> dict:
    """П§2 judgements.off_band_shift: Σ сдвигов положения осей вне полосы, порог гейта, число осей."""
    d = x.rel.off_band or U.off_band_shift(x.book, x.facts, x.live, x.run.point, x.rel.judgements)
    return {"rub": R_PRICE(d["rub"]), "limit": float(d["limit"]), "axes": int(d["axes"])}


def _governance(x: _Ctx, judgements: Sequence[Mapping]) -> dict:
    comps = copy.deepcopy(list(x.book.get("valuation.governance.components")))
    row = next((r for r in judgements or [] if "valuation.governance.discount" in r.get("paths", [])), None)
    total = sum(float(c["sign"]) * float(c["value"]) for c in comps)
    return {"discount": x.run.governance, "components": comps,
            "sum_signed": x.run.governance if abs(total - x.run.governance) <= 1e-12 else total,
            "price_at_low": None if row is None else R_PRICE(row.get("price_low")),
            "price_at_high": None if row is None else R_PRICE(row.get("price_high"))}


# ------------------------------------------------------------------ nowcast, indicators, calendar


# Цели нау-каста: ключ → единица (коды витрины UNIT_CODES: прибыль — млрд ₽, ЧПМ и CoR — доли). Подпись и
# базис цели — ключи книги `meta.labels.nowcast.targets.<цель>` (М§0.6).
NOWCAST_UNITS = {"ni_q": "bn", "nim_q": "share", "cor_q": "share"}


def nowcast_targets(book: Book) -> list[dict]:
    """Цели нау-каста выпуска: `{key, title, unit, basis}` в порядке `NOWCAST_UNITS`."""
    labels = book.get("meta.labels.nowcast.targets")
    return [{"key": k, "title": str(labels[k]["title"]), "unit": unit, "basis": str(labels[k]["basis"])}
            for k, unit in NOWCAST_UNITS.items()]


def _combine(book: Book, ras: Mapping[str, Any], expectation: Mapping[str, float]) -> dict:
    try:
        from indicators.outputs import combine          # реэкспорт (INTERFACES §5): ядро читает индикаторы через outputs
    except ImportError:
        combine = None
    if combine is not None:
        return combine(ras, expectation, targets=nowcast_targets(book))   # базис целей — переданной книги (INTERFACES §5)
    return {t["key"]: {"ras_estimate": None, "bridge": None, "ras_bridged": None,
                       "expectation": expectation.get({"ni_q": "ni_q", "nim_q": "nim_q_mgmt", "cor_q": "cor_q_mgmt"}[t["key"]]),
                       "w": 0.0, "forecast": None, "std_error": None, "interval": None, "deviation": None,
                       "equation": None, "version": None, "benchmarks": [], "basis": t["basis"]}
            for t in nowcast_targets(book)}


def _nowcast(x: _Ctx, nxt: Mapping, next_exp: Mapping) -> dict:
    ind = x.rel.indicators
    period = nxt["period"]
    e = nxt["expectation"]
    expectation = {"ni_q": e["ni"], "nim_q_mgmt": e["nim_mgmt"], "cor_q_mgmt": e["cor_mgmt"]}
    nc = getattr(ind, "nowcast", None) or {}
    ras = nc.get("ras") if nc.get("period") == period else None
    by_target = _combine(x.book, ras or {"targets": {}}, expectation)
    for v in by_target.values():
        for k in ("forecast", "expectation", "deviation", "std_error", "ras_estimate", "ras_bridged"):
            if isinstance(v.get(k), float):
                v[k] = sig(v[k])
    quarter = {"period": period, "months": list((ras or {}).get("months") or []),
               "months_known": int((ras or {}).get("months_known") or 0), "by_target": by_target}
    # T2: прибыль года → DPS
    y, _q = parse_period(period)
    fact = [x.prep.hist["ni_sh"].get(q) for q in x.tl.quarters_of_year(y) if q <= 0]
    ni_fact = None if None in fact else sum(fact)
    qs = x.tl.index(period)
    rest = [q for q in x.tl.quarters_of_year(y) if q > qs and q <= x.tl.Q]
    rest_ni = [x.E(x.p_mix, "ni_sh", q) for q in rest]
    ni_rest = sum(rest_ni)
    t1 = by_target.get("ni_q") or {}
    # все слагаемые года — на одном слое (смесь заголовка): квартал смеси + отклонение нау-каста от своего
    # ожидания; без нау-каста — квартал смеси, и `dps` = `dps_model` (П§2 nowcast.year)
    deviation = (t1.get("forecast") - t1.get("expectation")
                 if t1.get("forecast") is not None and t1.get("expectation") is not None else 0.0)
    ni_q = x.E(x.p_mix, "ni_sh", qs) + deviation
    ni_year = None if ni_fact is None else ni_fact + ni_q + ni_rest
    # ошибка года: открытый квартал и оставшиеся кварталы (σ_база — относительная ошибка ожидания модели из
    # входов нау-каста, не константа); оставшиеся есть, а σ_база нет — ошибки года нет
    sigma_base = (((ras or {}).get("targets") or {}).get("ni_q") or {}).get("sigma_base")
    if sigma_base is None:
        sigma_base = ((ras or {}).get("sigmas") or {}).get("base")
    se_q = t1.get("std_error")
    if se_q is None or (rest and sigma_base is None):
        se = None
    else:
        se = math.sqrt(float(se_q) ** 2 + sum((float(sigma_base) * abs(v)) ** 2 for v in rest_ni))
    tau = float(Trajectory(x.book.get("tax.statutory")).year_value(y))
    after = bool(x.book.get("dividends.policy.deduct_at1_after_tax"))
    cpn = x.af.coupon_annual * (1 - tau) if after else 0.0
    base = None if ni_year is None else ni_year - cpn
    payout = x.prep.policy.payouts(y)[0]            # доля первой ступени политики — как у `dps_model`
    dps = None if base is None else payout * max(0.0, base) * 1000 / x.n_iss
    width = None if se is None or dps is None else payout * se * 1000 / x.n_iss
    note = ("факт отчётных кварталов + открытый квартал (смесь заголовка плюс отклонение нау-каста от "
            "своего ожидания) + смесь заголовка на остаток года; к цене не подключено до допуска")
    if x.cal is not None:
        # квартальный календарь (П§2 nowcast.year): DPS года — сумма кварталов прибыли; отклонение нау-каста
        # открытого квартала входит в базы тех решений модели года, в окно которых этот квартал попадает
        window = x.prep.policy.window
        hit = sum(1 for o in x.cal.open if o.year == y and o.dps is None and o.idx - window + 1 <= qs <= o.idx)
        shift = deviation * hit / window
        bases = [_quarter_base(x, x.tl.index(period_str(y, n))) for n in (1, 2, 3, 4)]
        base = None if None in bases else sum(bases) + shift
        model_dps = _dps_policy_of(x, y)
        dps = None if model_dps is None else model_dps + payout * shift * 1000 / x.n_iss
        width = (None if se is None or se_q is None or dps is None
                 else payout * float(se_q) * hit / window * 1000 / x.n_iss)
        note = ("факт отчётных кварталов + открытый квартал (смесь заголовка плюс отклонение нау-каста от "
                "своего ожидания) + смесь заголовка на остаток года; дивиденд года — сумма решений за кварталы "
                "прибыли; к цене не подключено до допуска")
    cond = next_exp.get("condition") or {}
    n20e, thr = cond.get("n20_expected"), cond.get("threshold")
    year = {"year": y, "ni_fact": R_MONEY(ni_fact), "ni_quarter": R_MONEY(ni_q), "ni_rest": R_MONEY(ni_rest),
            "ni_year": R_MONEY(ni_year), "ni_year_se": R_MONEY(se), "at1_coupon_after_tax": R_MONEY(cpn),
            "base": R_MONEY(base), "payout": payout, "dps": R_DPS(dps),
            "dps_interval": None if width is None else [R_DPS(dps - width), R_DPS(dps + width)],
            "dps_model": _dps_policy_of(x, y),
            "capital_check": {"n20_expected": n20e, "requirement": thr,
                              "ok": None if n20e is None or thr is None else n20e >= thr},
            "yield": {t: R_SHARE(None if dps is None else dps / x.prices[t]) for t in x.tickers},
            "note": note}
    # месячная таблица операционных результатов и форм ЦБ — при рядах слоя индикаторов; подпись — метка книги
    ops_rows = [dict(r) for r in (getattr(ind, "ops_months", ()) or ())]
    ops = {"ops": {"note": x.book.opt("meta.labels.nowcast.ops_note"), "rows": ops_rows}} if ops_rows else {}
    # выпуск собран без слоя индикаторов (на цене и дате книги): узлы допуска, ретро-проверки и журнала — пустые
    # скелеты; слова об этом — подпись книги, без неё узла нет
    words = absent_words(x.book, ind)
    if words is not None:
        ops["absent"] = words
    return {"period_unit": "quarter", "input_unit": "month", "connected_to_price": False,
            "targets": nowcast_targets(x.book), "quarter": quarter, "year": year,
            "months": {"basis": "ras", "rows": list(getattr(ind, "ras_months", ()) or ())},
            "form102": list(getattr(ind, "form102", ()) or ()),
            "admission": _filled(getattr(ind, "admission", None), ADMISSION_SKELETON),
            "retro": _filled(getattr(ind, "retro", None), RETRO_SKELETON),
            "journal": _filled(getattr(ind, "journal", None), JOURNAL_SKELETON), **ops}


# Узлы нау-каста, которые приходят из индикаторов: без них (или без поля) — поле есть, значение пустое
# (П§0.2: непосчитанное — null при присутствующем поле; П§2 — поля обязательны).
ADMISSION_SKELETON = {"rule": None, "status": "collecting", "events_needed": None, "events_scored": None,
                      "mse_ratio": None, "first_event": None, "earliest_decision": None}
RETRO_SKELETON = {"periods": [], "rmse": {}, "bias": {}, "n": {}, "main": None, "horizon": None, "titles": {}}
JOURNAL_SKELETON = {"entries": [], "total_entries": 0, "rule": None, "releases": {}}


def _filled(node: Any, skeleton: Mapping[str, Any]) -> dict:
    out = dict(node or {})
    for k, v in skeleton.items():
        out.setdefault(k, copy.deepcopy(v))
    return out


def _quarter_base(x: _Ctx, idx: int) -> float | None:
    """База пула квартала прибыли на смеси заголовка (М§5.7.3): у открытого квартала — ожидание базы решения
    клетки; у закрытого — средняя прибыль акционеров окна по фактам (без числа — None)."""
    slot = x.cal.periods.get(x.tl.period(idx))
    if slot is not None:
        return sum(x.p_mix[c.key] * x.decision(c, slot.period).base for c in x.run.cells)
    pol, ni = x.prep.policy, x.prep.hist["ni_sh"]
    window = range(idx - pol.window + 1, idx + 1)
    if not x.cal.closed(idx) or any(q not in ni for q in window):
        return None
    total = sum(ni[q] for q in window)
    if pol.deduct_at1_after_tax and x.af.coupon_annual:
        stat = Trajectory(x.book.get("tax.statutory"))
        total -= sum(x.af.coupon_annual * (1 - stat.year_value(x.tl.year(q))) for q in window
                     if x.tl.h(q) == x.af.coupon_quarter)
    return total / len(window)


def _dps_policy_of(x: _Ctx, year: int) -> float | None:
    """DPS политики года прибыли на смеси заголовка (= `dividends.next_expected.dps_policy`, П§2)."""
    row = next((r for r in _dividends_model_cache(x) if r["year"] == year), None)
    return None if row is None else row["dps_policy"]


def _indicators(x: _Ctx) -> dict:
    ind = x.rel.indicators
    return {"groups": list(getattr(ind, "groups", ()) or ()), "tiles": list(getattr(ind, "tiles", ()) or ())}


def _event(ev: Mapping[str, Any], v: date) -> dict:
    d = date.fromisoformat(str(ev["date"])[:10])
    out = {"id": ev.get("id"), "date": d.isoformat(), "kind": ev.get("kind"), "title": ev.get("title"),
           "confirmed": bool(ev.get("confirmed")), "precision": ev.get("precision") or "day", "days": (d - v).days}
    for k in ("covers", "earliest", "latest", "note", "estimated", "in_book"):
        if ev.get(k) is not None:
            out[k] = ev[k]
    return out


def _calendar(x: _Ctx, nxt: Mapping) -> dict:
    v = x.v
    evs = list((x.facts.file("calendar").get("events") or []) if "calendar" in x.facts.files else [])
    for r in x.rel.live_report.records:
        if r.get("pay_date"):
            evs.append({"id": f"pay-{_record_id(r)}", "kind": "pay", "date": r["pay_date"],
                        "title": x.book.label("dividends.pay_event", **record_fields(
                            x.book, r["year"], r.get("period"), r.get("label"))),
                        "confirmed": r.get("status") == "declared",
                        "precision": "day"})
    sched = getattr(x.rel.indicators, "ras_schedule", None)
    if sched and sched.get("form102_date_est"):
        # дата формы ЦБ — оценка по прошлым публикациям, не объявление: печатается окном (П§2 calendar)
        early = sched["form102_date_est"]
        evs.append({"id": f"form102-{sched.get('month')}", "kind": "form102", "date": early,
                    "title": f"Форма 0409102 за {period_words(sched.get('month'))}", "confirmed": False,
                    "precision": "window", "earliest": early, "latest": sched.get("form102_latest_est") or early,
                    "covers": sched.get("month")})
    events, recent = [], []
    for ev in evs:
        try:
            e = _event(ev, v)
        except (KeyError, ValueError):
            continue
        if 0 <= e["days"] <= 366:
            events.append(e)
        elif -7 <= e["days"] < 0:
            recent.append(e)
    events.sort(key=lambda e: e["date"])
    closing = nxt.get("closing")
    next_fact = None
    if closing:
        next_fact = {"id": closing.get("id"), "date": closing["date"], "title": closing.get("title"), "kind": "ifrs",
                     "covers": nxt["period"], "confirmed": closing.get("confirmed"),
                     "precision": closing.get("precision") or "day",
                     "days": (date.fromisoformat(closing["date"]) - v).days}
        for k in ("earliest", "latest"):
            if closing.get(k):
                next_fact[k] = closing[k]
    if sched:
        next_ras = {k: sched.get(k) for k in ("month", "release_date", "release_confirmed", "form102_date_est",
                                             "form102_latest_est", "enters_via", "date")}
        d = next_ras.get("date") or next_ras.get("release_date")
        next_ras["days"] = None if not d else (date.fromisoformat(str(d)[:10]) - v).days
    else:
        ras = next((e for e in events if e["kind"] == "ras"), None)
        next_ras = None if ras is None else {
            "month": ras.get("covers"), "release_date": ras["date"], "release_confirmed": ras["confirmed"],
            "form102_date_est": None, "form102_latest_est": None, "enters_via": "release", "date": ras["date"],
            "days": ras["days"]}
        if ras is not None and ras.get("estimated") and ras.get("earliest"):
            # событие фактов — окно выкладки форм ЦБ банка, а не релиз эмитента (у эмитента без месячного
            # релиза месяц входит формой 0409102): окно — оценка, нижний край — дата
            lo = str(ras["earliest"])[:10]
            next_ras.update(release_date=None, release_confirmed=False, form102_date_est=lo,
                            form102_latest_est=str(ras.get("latest") or lo)[:10], enters_via="form102", date=lo,
                            days=(date.fromisoformat(lo) - v).days)
    return {"today": v.isoformat(), "next_fact": next_fact, "next_ras": next_ras, "events": events,
            "recent": sorted(recent, key=lambda e: e["date"])}


# ------------------------------------------------------------------ history


def _history(x: _Ctx) -> dict:
    f = x.facts
    pnl = (f.file("pnl_quarterly").get("quarters") or {}) if "pnl_quarterly" in f.files else {}
    mq = (f.file("mgmt_quarterly").get("quarters") or {}) if "mgmt_quarterly" in f.files else {}
    caph = {str(h.get("period")): _node_v(h.get("n20_0"))
            for h in ((f.file("capital").get("history") or []) if "capital" in f.files else [])}
    bal = (f.file("balance").get("history") or {}) if "balance" in f.files else {}
    if isinstance(bal, list):               # [{period, …}] (INTERFACES §3.2) или словарь по периодам
        bal = {str(r["period"]): r for r in bal if isinstance(r, Mapping) and "period" in r}
    anchor = x.tl.anchor

    def bal_v(p: str, key: str) -> float | None:
        if p == anchor:
            return {"bv_common": x.af.bv, "loans_ac_gross": x.E(x.p_an, "loans_ac", 0)}.get(key)
        return _node_v((bal.get(p) or {}).get(key))

    mgmt_annual = (f.file("mgmt_quarterly").get("annual") or {}) if "mgmt_quarterly" in f.files else {}
    periods = sorted(set(pnl) | set(mq))
    periods = [p for p in periods if x.tl.index(p) <= 0]
    quarters, gaps = [], []
    for p in periods:
        r = pnl.get(p) or {}
        g = lambda k: _node_v(r.get(k))  # noqa: E731
        y, qn = parse_period(p)
        prev = period_str(*shift_quarter(y, qn, -1))
        d = quarter_days(y, qn)
        llp = None if g("llp_debt_fa") is None else -g("llp_debt_fa")
        ac = [bal_v(prev, "loans_ac_gross"), bal_v(p, "loans_ac_gross")]
        bv = [bal_v(prev, "bv_common"), bal_v(p, "bv_common")]
        cor = None if llp is None or None in ac else llp * DAYS_IN_YEAR / d / (sum(ac) / 2)
        roe = None if g("ni_shareholders") is None or None in bv else g("ni_shareholders") * DAYS_IN_YEAR / d / (sum(bv) / 2)
        m = mq.get(p) or {}
        row = {"period": p,
               "ifrs": {"ni": g("ni"), "ni_sh": g("ni_shareholders"), "nii": g("nii"), "fees": g("fees_net"),
                        "llp": llp, "cor": R_SHARE(cor), "opex": None if g("opex") is None else -g("opex"),
                        "pbt": g("pbt"), "bv": bv[1], "roe": R_SHARE(roe)},
               "mgmt": {k: _node_v(m.get(k)) for k in ("nim", "cor", "cir", "roe")},
               "n20": caph.get(p) if caph.get(p) is not None else _node_v(m.get("n20_0"))}
        # провалы раскрытия — по каждому базису отдельно: нет потоков МСФО квартала; нет упр. метрик
        if all(row["ifrs"][k] is None for k in IFRS_FLOWS):
            gaps.append({"period": p, "basis": "ifrs", "reason": "квартальные потоки МСФО не раскрыты"})
        if all(v is None for v in row["mgmt"].values()):
            gaps.append({"period": p, "basis": "mgmt", "reason": "управленческие метрики квартала не раскрыты"})
        quarters.append(row)
    annual = []
    by_year: dict[int, list] = {}
    for r in quarters:
        by_year.setdefault(parse_period(r["period"])[0], []).append(r)
    divs = {int(d["year"]): d for d in (f.file("dividends").get("history") or [])}
    div_rows: dict[int, list] = {}
    for d in f.file("dividends").get("history") or []:
        div_rows.setdefault(int(d["year"]), []).append(d)
    for y, rows in sorted(by_year.items()):
        if len(rows) < 4:
            continue
        ni = [r["ifrs"]["ni_sh"] for r in rows]
        ends = [bal_v(period_str(y - 1, 4), "bv_common")] + [r["ifrs"]["bv"] for r in rows]
        ends = [e for e in ends if e is not None]
        ni_sum = None if None in ni else sum(ni)
        dv = divs.get(y)
        pool = None if dv is None else _node_v(dv.get("pool_declared"))
        dps_year = None if dv is None else history_dps(dv)
        if x.cal is not None:
            # квартальный календарь: суммы строк решений года; год без строки за четвёртый квартал прибыли —
            # не завершён, оба поля пусты (П§2 `history.annual`)
            decided = div_rows.get(y, [])
            done = any(str(r.get("period")) == period_str(y, 4) for r in decided)
            parts = [history_dps(r) for r in decided]
            pools = [_node_v(r.get("pool_declared")) for r in decided]
            dps_year = sum(parts) if done and None not in parts else None
            pool = sum(pools) if done and None not in pools else None
        node = mgmt_annual.get(str(y)) or {}

        def year_metric(k: str, rows=rows, node=node) -> float | None:
            """Годовая упр. метрика — раскрытое годовое значение; без него — среднее четырёх раскрытых
            кварталов; неполный год — None (среднее трёх кварталов годом не называется)."""
            value = _node_v(node.get(k))
            if value is not None:
                return float(value)
            vals = [r["mgmt"][k] for r in rows]
            return sum(vals) / len(vals) if len(vals) == 4 and all(v is not None for v in vals) else None

        annual.append({"year": y, "ifrs": {"ni_sh": ni_sum,
                                           "roe": R_SHARE(None if ni_sum is None or len(ends) < 2 else ni_sum / (sum(ends) / len(ends))),
                                           "bv_end": rows[-1]["ifrs"]["bv"]},
                       "mgmt": {k: R_SHARE(year_metric(k)) for k in ("nim", "cor", "cir")},
                       "dps": dps_year,
                       "payout": R_SHARE(None if pool is None or not ni_sum else pool / ni_sum),
                       "n20_end": rows[-1]["n20"]})
    ltm = _ltm(x)
    issuer = _roe_issuer(x)
    if issuer is not None:                      # рядом с ROE выпуска — ROE по определению эмитента, фактом
        ltm["roe_issuer"] = issuer
    three = _three_profits(x, pnl)
    return {"quarters": quarters, "annual": annual, "ltm": ltm,
            "gaps": _gap_ranges(gaps + _partial_gaps(x, gaps, [r["period"] for r in quarters])),
            **({"three_profits": three} if three else {})}


FACT_GAPS = "history_gaps"       # узел фактов упр. метрик: частичные провалы раскрытия [{period, basis, reason}]


def _partial_gaps(x: _Ctx, whole: Sequence[Mapping], periods: Sequence[str]) -> list[dict]:
    """Частичные провалы раскрытия из фактов (`mgmt_quarterly.json → history_gaps`: квартал или диапазон,
    базис, причина словами — какая метрика не раскрыта и почему): по кварталам истории выпуска, кроме тех, где
    тот же базис уже пуст целиком. Узла нет — пусто: провалы называет только счёт выше."""
    f = x.facts
    rows = (f.file("mgmt_quarterly").get(FACT_GAPS) or []) if "mgmt_quarterly" in f.files else []
    taken = {(g["period"], g["basis"]) for g in whole}
    out: list[dict] = []
    for row in rows:
        m = GAP_RE.match(str(row.get("period")))
        if not m or row.get("basis") not in ("ifrs", "mgmt") or not str(row.get("reason") or "").strip():
            raise FactsError(f"mgmt_quarterly.{FACT_GAPS}: запись {dict(row)!r} — нужны period (квартал или "
                             "диапазон), basis (ifrs | mgmt) и reason")
        lo, hi = (x.tl.index(p) for p in (m.group(1), m.group(2) or m.group(1)))
        for p in periods:
            if lo <= x.tl.index(p) <= hi and (p, row["basis"]) not in taken:
                taken.add((p, row["basis"]))
                out.append({"period": p, "basis": str(row["basis"]), "reason": str(row["reason"]).strip()})
    return out


def _three_profits(x: _Ctx, pnl: Mapping[str, Any]) -> list[dict]:
    """`history.three_profits` (П§2): мост «вся прибыль → акционерам → операционная» по отчётным кварталам —
    отчётные строки и блок исключённого из фактов ОПУ (`reported`, `investment_block`); квартал без этих узлов
    в мост не входит. Тождество: операционная = акционерам − эффект пакета − проценты по долгу."""
    rows = []
    for period in sorted(pnl):
        r = pnl[period] or {}
        rep, blk = r.get("reported"), r.get("investment_block")
        if x.tl.index(period) > 0 or not isinstance(rep, Mapping) or not isinstance(blk, Mapping):
            continue
        rows.append({"period": period, "ni_total": R_MONEY(_node_v(rep.get("ni"))),
                     "ni_nci": R_MONEY(_node_v(rep.get("ni_nci"))),
                     "ni_shareholders": R_MONEY(_node_v(rep.get("ni_shareholders"))),
                     "stake_effect": R_MONEY(_node_v(blk.get("adj_stake_sh"))),
                     "debt_interest_effect": R_MONEY(_node_v(blk.get("adj_interest_sh"))),
                     "ni_operating": R_MONEY(_node_v(r.get("ni_shareholders")))})
    return rows


IFRS_FLOWS = ("ni", "ni_sh", "nii", "fees", "llp", "opex", "pbt")     # потоки МСФО квартала (без капитала и отношений)


def _gap_ranges(gaps: list[dict]) -> list[dict]:
    """Подряд идущие кварталы одного базиса с одной причиной — одной строкой «2019Q1–2022Q3» (так читает
    витрина); диапазоны одного базиса не пересекаются."""
    out: list[dict] = []
    for basis in ("ifrs", "mgmt"):
        last = None
        for g in sorted((g for g in gaps if g["basis"] == basis), key=lambda g: parse_period(g["period"])):
            if (last and last["reason"] == g["reason"]
                    and period_str(*shift_quarter(*parse_period(last["_to"]), 1)) == g["period"]):
                last["_to"] = g["period"]
            else:
                last = {"_from": g["period"], "_to": g["period"], "basis": basis, "reason": g["reason"]}
                out.append(last)
    return [{"period": r["_from"] if r["_from"] == r["_to"] else f"{r['_from']}–{r['_to']}", "basis": r["basis"],
             "reason": r["reason"]} for r in out]


# ------------------------------------------------------------------ checks, inputs, live


CORRIDOR_KEYS = {"pb_by_world": "pb_by_world", "roe_range": "roe_range", "cor_range": "cor_range",
                 "nim_range": "nim_range", "nim_path_joint": "nim_path_joint", "cir_range": "cir_range",
                 "roe_k_homogeneity": "roe_k_spread", "terminal_share": "terminal_share", "real_rate": "real_rate",
                 "bridge_drift": "bridge_drift_pp", "transmission_pairs": "transmission_pairs",
                 "m_crisis_vs_cbr": "m_crisis_vs_cbr", "manual_input_overdue": "manual_overdue_days"}
CORRIDOR_WORDS = {
    "pb_by_world": "коридор P/B клетки по мирам (книга)", "roe_range": "коридор ROE года (книга)",
    "cor_range": "коридор CoR года, базис движка (книга)", "nim_range": "коридор ЧПМ квартала, упр. базис (книга)",
    "nim_path_joint": "число первых кварталов и допуск к большему из ЧПМ якоря и ЧПМ {lt_level} (книга)",
    "cir_range": "коридор {cir} года, базис движка (книга)",
    "roe_k_homogeneity": "коридор «ROE терминала − стоимость капитала» и предел разрыва между мирами (книга)",
    "terminal_share": "коридор доли терминала в стоимости (книга)",
    "real_rate": "коридор реальной ставки терминала (книга)",
    "bridge_drift": "предел дрейфа моста упр. ↔ МСФО по стоимости риска и ЧПМ (книга)",
    "transmission_pairs": "коридор передачи ставки между соседними мирами (книга)",
    "lt_spread_floor": "полы долгосрочного спреда кредитных книг к опорной ставке (книга)",
    "off_band_shift": "половина шага печати заголовка",
    "m_crisis_vs_cbr": "рисковый сценарий ЦБ: рост кредита по годам, CoR года шока, минимум {n20_short} (книга)",
    "manual_input_overdue": "сроки ручных входов, дней (книга)",
    "guidance_gap": "{guidance_gap}",
    "capital_gap": "пол {n20_short} и {n11_short} сценария после дивидендов",
    "k_gt_g": "рост терминала ниже стоимости капитала без защиты", "roe_gt_g": "ROE терминала выше роста",
    "payout_cap": "потолок выплат года к прибыли акционеров (политика, книга)",
    "growth_cut": "наибольшая доля урезанного капиталом роста кредитных книг на конец года (книга)",
    "step_dividend": ("срез дивиденда политики у ступени пола норматива — без допуска; порог падения доли прироста "
                      "кредитных книг в квартале ступени — для сообщения (книга)"),
    "cir_lt": "цель C/I {lt_level}, допуск и первый год участка (книга)",
    "wholesale_share": "коридор доли оптового фондирования на конец года (книга)",
    "nim_lt": "цель ЧПМ модальной клетки {lt_level}, допуск и первый год участка (книга)",
    "volume_sign": "допуск изменения точки и разности изменений цен миров, ₽ на акцию (книга)",
    "stress_sign": "шаг разового убытка кризиса и допуск роста стоимости и прибыли, млрд ₽ (книга)",
    "nim_stationary": "мир, цель стационарной ЧПМ на составе баланса якоря (упр.) и допуск (книга)",
    "window_backtest": "первый год участка и коридоры окна фактов для CoR и {cir}, упр. базис (книга)",
    "funds_cost_to_key": "порог отношения стоимости средств клиентов к ключевой ставке и первый год участка (книга)"}
CORRIDOR_KEYS["lt_spread_floor"] = "lt_spread_floor"
CORRIDOR_KEYS.update(growth_cut="growth_cut", step_dividend="step_dividend", cir_lt="cir_lt",
                     wholesale_share="wholesale_share", nim_lt="nim_lt", volume_sign="volume_sign",
                     stress_sign="stress_sign", nim_stationary="nim_stationary", window_backtest="window_backtest",
                     funds_cost_to_key="funds_cost_to_key")


def _corridor(book: Book, name: str) -> dict:
    """Коридор гейта: подпись словами и значение из книги (число, [мин, макс] или словарь). Названия
    нормативов, термин долгосрочного уровня и слова о гайденсе в подписи — из `meta.labels`."""
    text = CORRIDOR_WORDS.get(name, "").format(
        lt_level=book.label("terms.lt_level"), n20_short=book.label("capital.n20_short"),
        n11_short=book.label("capital.n11_short"), guidance_gap=book.label("corridors.guidance_gap"),
        cir=cir_word(book))
    if name == "off_band_shift":
        return {"text": text, "value": float(book.get("valuation.headline.print_step")) / 2}
    if name == "payout_cap":                    # коридор гейта — ключ политики, не раздела проверок
        return {"text": text, "value": float(book.get("dividends.policy.cap"))}
    key = CORRIDOR_KEYS.get(name)
    if key is None:
        return {"text": text, "value": None}
    if name in FORM_GATE_TITLES:                # ключ коридора гейта второй формы может отсутствовать
        return {"text": text, "value": copy.deepcopy(book.opt(f"checks.{key}"))}
    return {"text": text, "value": copy.deepcopy(book.get(f"checks.{key}"))}


def _rub(x: float) -> str:
    """Рубли в тексте: два знака, десятичная запятая."""
    return f"{float(x):.2f}".replace(".", ",").replace("-", "−")


def _mln(x: float) -> str:
    """Число акций в тексте, млн шт.: один знак, разрядка неразрывным пробелом, десятичная запятая."""
    return f"{float(x):,.1f}".replace(",", "\u00a0").replace(".", ",")


JUMP_REASONS = {"first_release": "первый выпуск", "within_limit": "в пределах порога",
                "new_book": "новая версия книги", "new_facts": "новая дата фактов",
                "release_note": "действующая записка к выпуску", "unexplained": "объяснения нет"}


def _jump_guard(x: _Ctx, median: float) -> tuple[dict, Finding]:
    """Защита заголовка (М§14.4): медиана против прошлой за вычетом DPS экс-дат; капитал — V0 + B(v) + U слоя
    «свой взгляд» против прошлого V0 + B + U за вычетом дивидендов экс-дат. Сумма не меняется ни на конце
    квартала ГОСА (дивиденд переходит из V0 в мост, а без записи реестра — в U: дивиденд, который клетки
    вычли сами), ни на экс-дате (её уменьшение снято поправкой). В сравнении медианы U — на акцию по смеси
    заголовка."""
    b = x.book
    lim_m = float(b.get("valuation.headline.jump_guard.median_pct"))
    lim_v = float(b.get("valuation.headline.jump_guard.v0_pct"))
    prev = x.rel.previous
    v0 = x.run.layers["analytical"].v0
    u = x.run.unregistered_dividend                                              # U слоя «свой взгляд», млрд ₽
    u_ps = unregistered_dividend(x.run.ctx, x.run.cells, x.p_mix) * 1000 / x.n_div   # u смеси заголовка, ₽
    if not prev:
        jg = {"previous_median": None, "exdate_adjustment": 0.0, "median_change": None, "median_limit": lim_m,
              "v0_agm_adjustment": None, "v0_change": None, "unregistered_dividend": R_MONEY(u),
              "unregistered_dps": R_PRICE(u_ps), "v0_limit": lim_v, "reason": "first_release"}
        return jg, Finding("jump_guard", "invariant", False, None, (), "первый выпуск", {})
    pm = float(prev["fair_value"]["headline"]["median"])
    pv0 = float(prev["layers"]["analytical"]["v0"])
    pb = float(((prev.get("fair_value") or {}).get("bridge") or {}).get("amount") or 0.0)
    pjg = (prev.get("fair_value") or {}).get("jump_guard") or {}
    pu, pu_ps = float(pjg.get("unregistered_dividend") or 0.0), float(pjg.get("unregistered_dps") or 0.0)
    pdate = date.fromisoformat(str(prev["meta"]["valuation_date"]))
    adj = 0.0
    for e in _dividend_events(x):
        if e["date"] and pdate < date.fromisoformat(e["date"]) <= x.v:
            adj += float(e["dps"])
    adj_ps = adj * x.per_div                    # экс-даты на акцию оценки: Σ DPS × N_out / N_div (М§14.4)
    ref = pm + pu_ps - adj_ps
    mc = (median + u_ps) / ref - 1 if ref else None
    v0_adj = pb - adj * x.n_out / 1000          # мост прошлого выпуска минус дивиденды экс-дат между выпусками
    ref_v = pv0 + v0_adj + pu
    vc = (v0 + x.run.bridge_amount + u) / ref_v - 1 if ref_v else None
    within = mc is not None and vc is not None and abs(mc) <= lim_m and abs(vc) <= lim_v
    note = next((n for n in x.rel.notes if abs(median - n["expected_central"])
                 <= n["tolerance_pct"] / 100 * abs(n["expected_central"])), None)
    if within:
        reason = "within_limit"
    elif str(prev["meta"].get("book_version")) != str(b.get("meta.version")):
        reason = "new_book"
    elif str(prev["meta"].get("facts_date")) != str(_iso(b.get("meta.facts_date"))):
        reason = "new_facts"
    elif note is not None:
        reason = "release_note"
    else:
        reason = "unexplained"
    jg = {"previous_median": R_PRICE(pm), "exdate_adjustment": R_PRICE(adj_ps), "median_change": R_SHARE(mc),
          "median_limit": lim_m, "v0_agm_adjustment": R_MONEY(v0_adj), "v0_change": R_SHARE(vc),
          "unregistered_dividend": R_MONEY(u), "unregistered_dps": R_PRICE(u_ps), "v0_limit": lim_v,
          "reason": reason}
    if reason == "release_note":
        jg["note_valid_until"] = _iso(note["valid_until"])
    msg = (f"медиана {_rub(median + u_ps)} ₽ против {_rub(ref)} ₽ (прошлая {_rub(pm)} − экс-даты {_rub(adj_ps)}"
           + (f", дивиденд без записи реестра {_rub(u_ps)}" if u_ps or pu_ps else "") + f"): {pct(mc)}; "
           f"капитал с мостом {pct(vc)}; основание — {JUMP_REASONS[reason]}") \
        if mc is not None and vc is not None else "нет опоры"
    return jg, Finding("jump_guard", "invariant", reason == "unexplained", None, (), msg, {})


def _flags(x: _Ctx, nxt: Mapping) -> list[dict]:
    fl = dict(x.rel.live_report.flags)
    for f in x.rel.findings:
        if f.kind == "flag":
            fl[f.name] = {"raised": bool(f.fired), "detail": f.message if f.fired else None}
    closing = nxt.get("closing") or {}
    raised = bool(closing.get("published"))
    fl["report_fact"] = {"raised": raised,
                         "detail": (f"МСФО за {period_words(nxt['period'])} вышло {_ru_date(closing.get('date'))}, "
                                    "книга квартал не закрыла" if raised else None)}
    # плашки сроков (М§14.3): не тревога и не отказ — выпуск выходит с кодом 0
    exp = [g for g in x.rel.gates if g.fired and g.expiring]
    fl["explanation_expiring"] = {
        "raised": bool(exp),
        "detail": "; ".join(f"{gate_title(x.book, g.name)} — объяснение действует до {_ru_date(g.valid_until)}"
                            for g in exp) or None}
    until = _node_v(((x.facts.file("dividends").get("policy") or {}) if "dividends" in x.facts.files else {})
                    .get("valid_until"))
    expired = until is not None and to_date(_iso(until)) < x.v
    fl["policy_expired"] = {
        "raised": bool(expired),
        "detail": (f"срок политики по документу — до {_ru_date(until)}; клетки платят по политике книги до новой"
                   if expired else None)}
    out = [{"name": k, "title": flag_title(x.book, k), "raised": bool((fl.get(k) or {}).get("raised")),
            "detail": (fl.get(k) or {}).get("detail")} for k in FLAG_TITLES]
    # флаги второй формы банка — только поднятыми: состав списка без них прежний (М§14.3)
    raised = {}
    events = (x.facts.file("calendar").get("events") or []) if "calendar" in x.facts.files else []
    deals = [e for e in events if e.get("kind") == "deal" and e.get("in_book") is False]
    if deals:                                   # объявленная сделка войдёт в оценку фактами нового якоря
        raised["deal_pending"] = "; ".join(": ".join(str(t) for t in (e.get("title"), e.get("note")) if t)
                                           for e in deals)
    if x.af.estimated:
        raised["capital_estimated"] = x.book.label("capital.anchor_src_estimated", date=_ru_date(x.af.as_of))
    return out + [{"name": k, "title": title, "raised": True, "detail": raised[k]}
                  for k, title in RAISED_FLAG_TITLES.items() if k in raised]


ORDER_INVARIANTS = ("probabilities", "bv_identity", "balance_identity", "pnl_identity", "ddm_equals_ri", "dps_history",
                    "exdate_jump", "transmission_solved", "dividend_bounds", "governance_sum", "release_numbers",
                    "book_schema", "jump_guard", "payload_contract")


def _checks(x: _Ctx, findings: Mapping[str, Finding], nxt: Mapping) -> dict:
    inv = []
    for name in ORDER_INVARIANTS:
        f = findings.get(name)
        inv.append({"name": name, "title": invariant_title(x.book, name), "ok": f is not None and not f.fired,
                    "detail": "не проверено" if f is None else f.message})
    gates = []
    by_name = {f.name: f for f in x.rel.findings if f.kind == "gate"}
    for gs in x.rel.gates:
        f = by_name.get(gs.name)
        exp = gs.expected_mass
        gates.append({"name": gs.name, "title": gate_title(x.book, gs.name), "fired": gs.fired,
                      "mass": R_PROB(gs.mass), "cells": len(f.cells) if f else 0,
                      "cell_list": list(f.cells[:CELL_LIST_MAX]) if f else [], "status": gs.status,
                      "explanation": gs.explanation, "expected_mass": list(exp) if isinstance(exp, tuple) else exp,
                      "valid_until": _iso(gs.valid_until), "expiring": gs.expiring,
                      "message": f.message if f else None, "corridor": _corridor(x.book, gs.name)})
    return {"invariants": inv, "invariants_broken": sum(1 for i in inv if not i["ok"]), "gates": gates,
            "flags": _flags(x, nxt), "control_model": x.rel.control_model, **_sign_nodes(x)}


def _sign_nodes(x: _Ctx) -> dict:
    """Узлы чисел гейтов знака (П§2 `checks.volume_sign`, `checks.stress_sign`; М§14.2) — при ключах книги."""
    out: dict[str, Any] = {}
    st = x.rel.volume_sign
    if st is not None:
        out["volume_sign"] = {"point": R_PRICE(st["point"]), "point_free": R_PRICE(st["point_free"]),
                              "d_point": R_PRICE(st["d_point"]),
                              "d_world": {w: R_PRICE(v) for w, v in st["d_world"].items()},
                              "tol": float(st.get("tol", 0.0)), "ok": bool(st["ok"]),
                              **({"growth_constraint_off": True} if st.get("growth_constraint_off") else {})}
    ss = x.rel.stress_sign
    if ss is not None:
        out["stress_sign"] = {
            "loss": {"step": float(ss["loss"]["step"]),
                     "cells": [{**{k: c[k] for k in ("world", "regime", "scenario")}, "dv": R_MONEY(c["dv"])}
                               for c in ss["loss"]["cells"]]},
            "requirement": {"cells": [{**{k: c[k] for k in ("world", "regime", "stricter", "looser")},
                                       "d_profit": R_MONEY(c["d_profit"])} for c in ss["requirement"]["cells"]]},
            "mass": R_PROB(ss["mass"]), "max_excess": R_MONEY(ss["max_excess"]), "ok": bool(ss["ok"])}
        # масса гейта — под вероятностями точки; рядом — масса тех же клеток под весами слоя «свой взгляд»
        if ss.get("mass_analytical") is not None:
            out["stress_sign"].update(mass_basis="point", mass_analytical=R_PROB(ss["mass_analytical"]))
        if ss["loss"].get("transfer_min") is not None:       # рубль убытка после налога → рубли стоимости клетки
            out["stress_sign"]["loss"].update(after_tax=R_MONEY(ss["loss"]["after_tax"]),
                                              transfer_min=R_SHARE(ss["loss"]["transfer_min"]),
                                              transfer_max=R_SHARE(ss["loss"]["transfer_max"]))
    fc = funds_cost_to_key(x.run)               # стоимость средств клиентов к ключевой ставке — при ключе книги
    if fc is not None:
        out["funds_cost_to_key"] = {
            "from_year": fc["from_year"], "to_year": fc["to_year"], "max": fc["max"],
            "by_world": {w: {"cell": row["cell"], **{k: R_SHARE(row[k]) for k in ("cost", "key", "ratio")},
                             # Р10-6: у ожидания мира модальная клетка — рядом (необязательные поля)
                             **({} if "modal_cell" not in row else
                                {"modal_cell": row["modal_cell"], "modal_ratio": R_SHARE(row["modal_ratio"])})}
                         for w, row in fc["by_world"].items()}, "ok": bool(fc["ok"]),
            **({} if "scope" not in fc else {"scope": fc["scope"]})}
    return out


def _inputs(x: _Ctx) -> dict:
    rep = x.rel.live_report
    words = {"tinvest": "T-Invest", "iss": "Мосбиржа, TQBR", "book": "книга"}
    rows = []
    for t in x.tickers:
        r = rep.prices.get(t) or {}
        st = {"live": "ok", "fallback": "fallback", "book": "ok" if not rep.applied else "fallback"}.get(r.get("status"), "ok")
        rows.append({"key": f"price.{t}", "name": f"Цена {t}", "value": x.prices[t], "unit": "rub",
                     "as_of": _iso(r.get("date")), "source": words.get(r.get("source"), r.get("source")), "status": st})
    if rep.curve:
        rows.append({"key": "curve.10", "name": "Кривая ОФЗ, 10 лет", "value": rep.curve["nodes"]["10"], "unit": "share",
                     "as_of": rep.curve["as_of"], "source": "Мосбиржа ISS, КБД", "status": "ok"})
    if rep.key_rate:
        rows.append({"key": "key_rate", "name": "Ключевая ставка", "value": rep.key_rate["value"], "unit": "share",
                     "as_of": _iso(rep.key_rate.get("date")), "source": "Банк России", "status": "ok"})
    rows.append({"key": "register", "name": "Реестр дивидендов", "value": rep.register.get("entries"),
                 "unit": "count", "as_of": rep.register.get("as_of"), "source": rep.register.get("note"),
                 "status": "ok"})
    rows.append({"key": "book", "name": "Книга допущений", "value": str(x.book.get("meta.version")), "unit": "version",
                 "as_of": _iso(x.book.get("meta.date")), "source": "машинная книга допущений (каталог книги)", "status":
                     "stale" if (rep.flags.get("book_update") or {}).get("raised") else "ok"})
    rows.append({"key": "facts", "name": "Факты якоря", "value": str(x.book.get("meta.anchor_period")), "unit": "period",
                 "as_of": _iso(x.book.get("meta.facts_date")), "source": "факты отчётности (каталог фактов)",
                 "status": "ok"})
    return {"rows": rows}


def _live(x: _Ctx) -> dict:
    rep = x.rel.live_report
    prices = {}
    for t in x.tickers:
        r = rep.prices.get(t) or {}
        prices[t] = {"value": r.get("value", x.prices[t]), "date": _iso(r.get("date")), "time": r.get("time"),
                     "accepted": bool(r.get("accepted")), "status": r.get("status"), "reason": r.get("reason"),
                     "last_accepted": r.get("last_accepted")}
    curve = None
    if rep.curve:
        curve = {k: rep.curve[k] for k in ("as_of", "nodes", "book_nodes", "shift_bp")}
    return {"applied": rep.applied, "degraded": list(rep.degraded), "degraded_flag": rep.degraded_flag,
            "valuation_date": x.v.isoformat(), "fetched_at": rep.fetched_at, "prices": prices, "curve": curve,
            "key_rate": rep.key_rate, "register": {k: rep.register.get(k) for k in ("as_of", "entries", "note")},
            "book_date": _iso(rep.book_date), "book_age_days": rep.book_age_days}


# ------------------------------------------------------------------ changes, valuation_history, book


def _changes(x: _Ctx, median: float, printed_median: float) -> dict:
    from model.attribution import attribute, inputs_snapshot
    snap = inputs_snapshot(x.book, x.facts, x.live)
    prev = x.rel.previous
    if not prev:
        return {"vs_previous": None, "snapshot": snap}
    steps = attribute(prev, x.book, x.facts, x.live, engine_commit=x.rel.engine_commit,
                      current={"point": x.run.point, "median": median,
                               "printed_point": U.round_half_up(x.run.point, x.band.print_step),
                               "printed_median": printed_median}, anchor=x.rel.anchor)
    pfv = prev.get("fair_value") or {}
    pm = prev.get("meta") or {}
    pprices = (prev.get("market") or {}).get("prices") or {}
    rows = [{"component": s.component, "title": s.title, "point_rub": R_PRICE(s.point_rub),
             "median_rub": R_PRICE(s.median_rub), "note": s.note} for s in steps]
    total_p = sum(s.point_rub for s in steps) if steps else None
    total_m = sum(s.median_rub for s in steps if s.median_rub is not None) if steps and all(
        s.median_rub is not None for s in steps) else None
    adj = sum(float(e["dps"]) for e in _dividend_events(x) if e["date"] and pm.get("valuation_date")
              and date.fromisoformat(str(pm["valuation_date"])) < date.fromisoformat(e["date"]) <= x.v)
    return {"vs_previous": {
        "previous_sha": pm.get("payload_sha256"), "previous_generated_at": pm.get("generated_at"),
        "previous_published_at": pm.get("published_at"), "rows": rows, "walk_book": [],
        "total_point_rub": R_PRICE(total_p), "total_median_rub": R_PRICE(total_m),
        "market_price": {t: {"from": (pprices.get(t) or {}).get("price"), "to": R_PRICE(x.prices[t])} for t in x.tickers},
        "reference": {"median": pfv.get("headline", {}).get("median"), "point": pfv.get("central"),
                      "exdate_adjustment": R_PRICE(adj)},
        "note": ("смена рыночной цены стоимость не меняет — двигает только сравнения; вклады отдельных ключей книги "
                 "даёт прогулка книги вне выпуска") if steps
        else "снимка входов прошлого выпуска нет — разложение не считалось"},
        "snapshot": snap}


def _thin_history(rows: Sequence[Mapping[str, Any]], today: date) -> list[Mapping[str, Any]]:
    """Прореживание П§4: день — последняя строка дня; старше 180 дней — недели; старше двух лет — месяца."""
    keyed: dict[tuple, Mapping] = {}
    for r in sorted(rows, key=lambda r: str(r.get("published_at") or "")):
        stamp = str(r.get("published_at") or r.get("generated_at") or "")
        try:
            d = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=3))).date()
        except ValueError:
            continue
        age = (today - d).days
        if age > 730:
            key = ("m", d.year, d.month)
        elif age > 180:
            iso = d.isocalendar()
            key = ("w", iso[0], iso[1])
        else:
            key = ("d", d.isoformat())
        keyed[key] = {**r, "_day": d.isoformat()}
    out = sorted(keyed.values(), key=lambda r: r["_day"])
    return out[-HISTORY_ROWS:]


def _valuation_history(x: _Ctx) -> dict:
    rows = _thin_history(x.rel.history, x.v)
    band = lambda r, i: (r.get("band80") or [None, None])[i]  # noqa: E731
    inner = lambda r, i: (r.get("band50") or [None, None])[i]  # noqa: E731
    changes, last_v = [], None
    for r in rows:
        v = r.get("book_version")
        if last_v is not None and v != last_v:
            changes.append({"date": r["_day"], "from": last_v, "to": v})
        last_v = v
    return {"date": [r["_day"] for r in rows], "sha": [str(r.get("payload_sha256") or "")[:12] for r in rows],
            "median": [r.get("median") for r in rows], "p10": [band(r, 0) for r in rows],
            "p25": [inner(r, 0) for r in rows], "p75": [inner(r, 1) for r in rows], "p90": [band(r, 1) for r in rows],
            "point": [r.get("point") for r in rows],
            "price": {t: [(r.get("prices") or {}).get(t) for r in rows] for t in x.tickers},
            "rollbacks": [i for i, r in enumerate(rows) if r.get("event") == "rollback"], "book_changes": changes,
            "rule": "день — последняя строка дня (МСК); старше 180 дней — недели; старше двух лет — месяца; "
                    f"не больше {HISTORY_ROWS} строк",
            "source": "журнал опубликованных выпусков (репозиторий данных)"}


def _book_block(x: _Ctx, judgements: Sequence[Mapping]) -> dict:
    b = x.book
    src = b.get("worlds.source")
    keyj = [{"id": r["id"], "name": r["name"], "value": r["book"], "unit": r.get("unit", "")}
            for r in (judgements or [])[:10]]
    return {"version": str(b.get("meta.version")), "date": _iso(b.get("meta.date")),
            "tag": f"book-{b.get('meta.version')}", "facts_date": _iso(b.get("meta.facts_date")),
            "curve_as_of": _iso(b.get("meta.curve_as_of")),
            "worlds_source": f"{src.get('origin')}, запись {src.get('record_asof')}, кривая {src.get('curve_date')}",
            "key_judgements": keyj,
            # справочные варианты — из таблиц книги, на её цене и дате; в такте не пересчитываются (М§14.5)
            **({"reference_variants": copy.deepcopy(dict(x.rel.reference_variants))}
               if x.rel.reference_variants is not None else {})}


# ------------------------------------------------------------------ выпуск целиком


def _round_tree(node: Any) -> Any:
    """Оставшиеся свободные числа — 9 значащих цифр (П§0.3, «прочее»)."""
    if isinstance(node, float):
        return sig(node)
    if isinstance(node, Mapping):
        return {k: _round_tree(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_round_tree(v) for v in node]
    if isinstance(node, (date, datetime)):
        return node.isoformat()
    return node


def _contract_problems(payload: Mapping[str, Any], schema: str) -> list[str]:
    """Контракт без проверок (П§7 пп. 1–12, 14): для инварианта payload_contract. `schema` — имя схемы
    книги выпуска."""
    return [p for p in validate(payload, schema=schema) if not p.startswith(("нарушены инварианты", "гейт ",
                                                                "checks.invariants_broken"))]


def build_payload(release: Release) -> dict:
    """Выпуск по PAYLOAD (имя схемы — `meta.schema` книги); хэш и размер — последними."""
    x = _Ctx(release)
    band = release.band
    h = band.headline(x.lam, x.prices, x.main)
    jg, jg_find = _jump_guard(x, h["median"])
    fair_value, _hx = _fair_value(x, jg)
    layers = _layers(x)
    divs = _dividends(x, (release.run.ctx.prep.af.n20 - release.run.ctx.prep.af.dividends_payable
                          / release.run.ctx.prep.rwa0) if release.run.ctx.prep.af.n20_pre_dividend
                      else release.run.ctx.prep.af.n20)
    paths = _paths(x)
    ay_row = next((r for r in paths["annual"] if r["year"] == x.v.year), None)
    yield_fwd = (divs["next_expected"]["yield"] if x.cal is None or annual_payer(x)
                 else _yield_fwd_quarterly(x, divs["next_expected"]))
    market = _market(x, None if ay_row is None else ay_row["ni_sh"], yield_fwd)
    gates_map = {g.name: {"fired": g.fired, "mass": g.mass, "explanation": g.explanation,
                          "valid_until": _iso(g.valid_until)} for g in release.gates}
    nxt = dict(release.next_report or {})
    reverse, judg_rows = _coded(release.reverse, release.judgements)
    invariants = {f.name: f for f in release.findings if f.kind == "invariant"}
    payload: dict[str, Any] = {
        "schema": schema_name(x.book), "meta": _meta(x), "market": market, "fair_value": fair_value, "layers": layers,
        "grid": _grid(x), "variance": _variance(x), "worlds": _worlds(x), "regimes": _regimes(x),
        "capital": _capital(x), "dividends": divs, "paths": paths, "nii": _nii(x, invariants),
        "guidance": _guidance(x, paths, gates_map), "governance": _governance(x, judg_rows),
        "reverse_dcf": reverse, "judgements": {"rows": judg_rows, "off_band_shift": _off_band_block(x)},
        "next_report": nxt,
        "nowcast": _nowcast(x, nxt, divs["next_expected"]), "indicators": _indicators(x),
        "calendar": _calendar(x, nxt), "history": _history(x), "checks": {}, "inputs": _inputs(x),
        "live": _live(x), "changes": _changes(x, h["median"], h["printed_median"]),
        "valuation_history": _valuation_history(x), "book": _book_block(x, judg_rows),
    }
    payload = _round_tree(payload)
    for f in release.extra_findings:
        invariants[f.name] = f
    invariants["jump_guard"] = jg_find
    invariants["payload_contract"] = Finding("payload_contract", "invariant", False, None, (), "контракт выполнен", {})
    payload["checks"] = _round_tree(_checks(x, invariants, nxt))
    invariants["release_numbers"] = release_findings(payload)
    payload["checks"] = _round_tree(_checks(x, invariants, nxt))
    _seal(payload)
    problems = _contract_problems(payload, schema_name(x.book))
    if problems:
        invariants["payload_contract"] = Finding("payload_contract", "invariant", True, None, (),
                                                 "; ".join(problems[:5]), {"problems": problems})
        payload["checks"] = _round_tree(_checks(x, invariants, nxt))
        _seal(payload)
    return payload


def _seal(payload: dict) -> None:
    payload["meta"]["payload_sha256"] = payload_hash(payload)
    payload["meta"]["bytes"] = 0
    payload["meta"]["bytes"] = compact_bytes(payload)


def alerts(release: Release, payload: Mapping[str, Any]) -> list[str]:
    """Тревоги выпуска (код 3): деградация живых входов (`live.degraded_flag`), флаг `dividend_register`
    (нет записи реестра к сроку решения о дивиденде; слова — `meta.labels.register.alert`), размер ≥ 450 000.
    Истекающее объяснение гейта и истёкший документ эмитента — плашки (флаги `explanation_expiring`,
    `policy_expired`), в тревоги не входят."""
    out = []
    if payload["live"].get("degraded_flag"):
        reasons = list(getattr(release.live_report, "alarms", None) or payload["live"]["degraded"])
        out.append("деградация живых входов: " + "; ".join(reasons[:3]))
    reg = next((f for f in payload["checks"]["flags"] if f.get("name") == "dividend_register"), None)
    if reg and reg.get("raised"):
        out.append(release.book.label("register.alert", detail=reg.get("detail")))
    if payload["meta"]["bytes"] >= WARN_BYTES:
        out.append(f"выпуск {payload['meta']['bytes']} байт ≥ {WARN_BYTES}")
    return out
