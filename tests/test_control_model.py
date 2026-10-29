# -*- coding: utf-8 -*-
"""Контрольная модель (docs/MODEL.md §17) на машинной книге и фактах репозитория: её собственные свойства
и сверка с ядром. Набор идёт на книге любой формы: тесты годовой ветви образца (решение о дивиденде раз
в год, метка annual_only) на книге с квартальным календарём пропускаются с причиной, тесты строки FVC — на
книге без кредитов по справедливой стоимости; и те и другие исполняются на фикстуре формы образца
(tests/test_control_forms.py, каталог-заготовка из фикстуры); ветвь с квартальным проходом капитала —
tests/test_control_t.py.

* Свойства контрольной модели (ядро не нужно; метка tact — быстрые): V_DDM = V_RI в каждой клетке
  (≤ 0,1 %, фактически машинная точность), тождества BV, баланса и PBT, квартальные профили прибыли и
  CI, вероятности слоёв, DPS истории до копейки, передача решена (T_real = T*, Nss(H) = цель) и
  парные передачи телескопичны, плоский мир ⇒ V = BV_v, кризисный перенос и догоняющая выплата
  (N, crisis, strict), связывающий капитал (M, downturn, strict), нормативы якоря воспроизводят факты.
* Решения W1 (LEAD-DECISIONS-2): σ0 с года sigma0_from, ближний сдвиг ЧПМ вне Nss и общий для клеток,
  «конец дня» на конце квартала ГОСА, ввод ε, доли «прочего», A-P2u при одном режиме.
* Решения W2 (LEAD-DECISIONS-3, аудит после W1): «прочее» года якоря — уровень × доля (№ 2), FVC
  режима на кредитах по СС (№ 3), доход на избыток по маржинальной ставке балансирующих статей
  (№ 4), цена с D_pend (№ 25), окно наблюдений, стационарные априорные и замороженные μ (В2),
  распределение сдвига σ0 между активами и пассивами (В8), год шока кризиса от года якоря.
* Решения W3 (LEAD-DECISIONS-4, второй аудит): раскладка сжатия φ между кредитными книгами и средствами
  клиентов, кредитная маржа миров (В12), одностороннее угасание (В13),
  опора FVC — путь нормы книги до розыгрыша (В14), пол вероятности режима и замороженные μ (В15),
  порог связывания минимума ликвидности и добор опта на терминале, кварталы выплаты и вычета
  объявленного дивиденда по записи реестра (М§5.4), центральная клетка по правилу (№ 86).
* Гейты знака (М§4.5, §14.2): числа гейта знака объёмных эффектов и набор нарушивших клеток гейта знака
  стресса контрольная модель считает сама; знак в тестах не утверждается — это гейты правдоподобия с
  объяснением, а не инварианты. Печатаемая маржа после фазы роста — у книги с ключом checks.nim_lt.
* Мир-опора κ (ключ credit.kappa_reference_world, М§4.6): обе ветви ключа — подменой, на любой книге.
* Уровни после фазы роста (ключи checks.window_backtest и checks.cir_lt, М§14.2): ЧПМ, CoR и C/I смеси
  клеток — отношение ожидаемых агрегатов; гейт сверки с окном фактов и уровень C/I цели книги.
* Сверка с ядром (маркер ci_only): ядро импортируется только внутри сверки; нет ядра, его функции или
  книги — провал, не пропуск. Допуски — М§17 (docs/CONTROL-MODEL.md, «Допуски»); точное совпадение V0
  слоёв (относительная разность ≤ 1e-9) — провал: это означало бы общий код.

Сводка сверки для выпуска (П§2 checks.control_model; строка несёт единицу и вид допуска):
    python -B -m tests.test_control_model --write   → data/checks/control_model.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import importlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    from tests import independent_model as cm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]

CHECKS_JSON = cm.ROOT / "data" / "checks" / "control_model.json"
# Каталог данных сверки: по умолчанию data/ репозитория; переменная окружения даёт прогнать тот же набор
# на каталоге-заготовке книги и фактов (внутри него — assumptions/assumptions.yaml и facts/).
DATA_DIR_ENV = "BANK_CONTROL_DATA_DIR"

# Допуски М§17 (доли; «ratio» — абсолютная разность долей, 0,003 = 0,3 п.п.).
TOL_LINE = 0.10          # строки ОПУ и баланса
TOL_SMALL_BV = 0.02      # PBT, NI, CI при малой величине: |Δ| ≤ 2 % BV
TOL_RATIO = 0.003        # нормативы, ROE_T, k_T, g_T
TOL_VALUE = 0.03         # V_c, V0_L, низ, верх, точка; TV — в форме TV_DDM
VALUE_FLOOR_BV = 0.005   # V_c: |Δ| ≤ 0,5 % BV_v — у клетки с оценкой около нуля относительный допуск не выполним (М§17)
LEARNING_REST = 0.05     # A-P2u на четырёх режимах: остаток сдвига V0 слоя сверх перевзвешивания, доля перевзвешивания
LEARNING_REST_RULE = 0.20   # то же у книги с ростом, ограниченным капиталом (на книге панели — до 0,16)
TOL_BRIDGE = 0.01        # мост и объявленные дивиденды
TOL_DERIVED = 1e-6       # σ0_A, σ0_L, φ, φ_A, φ_L, T_real, T(W), пары, ROE-эквивалент, LT-спреды, маржа миров
TOL_DDM = 0.001          # V_DDM = V_RI внутри контрольной модели
EXACT = 1e-9             # совпадение V0 слоёв с ядром до этой точности — провал (общий код)
DIV_FLOOR_BV = 0.005     # дивиденд года и DPS: |Δ| ≤ 0,5 % BV конца года выплаты (связывающий капитал)
TOL_ZERO_BN = 1e-9       # машинный ноль в единицах строки: мост при нуле у ядра; величина относительной строки

FLOW_LINES = ("nii", "llp", "fvc", "fees", "opex", "misc", "noncore", "pbt", "ni_sh", "ci")
STOCK_LINES = ("bv", "rwa")
RATIO_LINES = ("n20", "n11")
SMALL_BV_LINES = ("pbt", "ni_sh", "ci")
ABS_LINES = ("llp", "opex")      # расходные строки сверяются по модулю (знак хранения у ядра свой)

# Единицы строк сводки — коды П§0.2; слова строк — то, что печатает витрина (метку клетки W/r/s она
# переводит в слова сама).
U_BN, U_RUB, U_PCT, U_PP, U_NUM = "bn", "rub", "pct", "pp", "number"
REL, ABS = "rel", "abs"
LINE_KEYS = ("nii", "llp", "fvc", "fees", "opex", "misc", "noncore", "pbt", "ni_sh", "ci", "div", "bv", "rwa",
             "n20", "n11")
LAYER_TITLES = {"analytical": "свой макро-взгляд", "market_implied": "вменённые рынком",
                "macro_neutral": "рыночные ставки как есть"}
SUMMARY_WHOLE = ("derived", "value", "bridge", "cell", "gate")     # группы строк, которые идут в сводку целиком
ROW_FIELDS = ("what", "unit", "core", "control", "diff", "diff_rel", "tol", "tol_kind", "ok")
DPS_Q_FLOOR_BV = 0.0015  # DPS квартала прибыли: |Δ| ≤ 0,15 % BV конца года решения на акцию (М§17)
TOL_GROWTH = 0.03        # фактический рост кредитных книг за год, п.п. (М§17)
TOL_CUT_SHARE = 0.05     # доля урезанного роста на конец года (М§17)
SIGN_TOL_REL = 0.03      # число гейта знака объёмных эффектов: |Δ| ≤ 3 % модуля числа ядра …
SIGN_TOL_RUB = 0.5       # … или ≤ 0,5 ₽
SIGN_WORDS = "знак объёмных эффектов"       # начало слов строк гейта в сводке
MARGIN_WORDS = "печатаемая маржа после фазы роста, модальная клетка"
LEVEL_WORDS = "уровни после фазы роста, слой «рыночные ставки как есть»"      # начало слов строк уровней
LEVEL_TITLES = {"nim": "чистая процентная маржа", "cor": "стоимость риска", "cir": "расходы к доходам"}
CIR_GOAL_WORDS = "расходы к доходам для цели книги, слой «рыночные ставки как есть»"
TOL_KAPPA_SPREAD = 0.0003    # разность годовой CoR клеток мира и мира-опоры κ у двух моделей: 0,03 п.п.
TOL_COR_MIX0 = 0.0003        # CoR клетки на составе якоря (ключ credit.book_relative): 0,03 п.п., как κ-добавка
COR_MIX0_WORDS = "стоимость риска на составе якоря"
TOL_OPEX_VOLUME = 0.005      # рост взвешенной базы расходов за год (ключ opex.volume_weights): 0,5 п.п.
OPEX_VOLUME_WORDS = "рост базы расходов по себестоимости книг"
TOL_FIXED_REL, TOL_FIXED_BN = 0.01, 0.5     # F_K, D_F, I_F блока постоянных частей терминала: 1 % или 0,5 млрд ₽
BUYBACK_LINE = "buyback"     # строка выкупа сводки (meta.labels.control.lines.buyback — при включённом выкупе)
TOL_SHARES = 0.001           # акции клетки на конец сетки при выкупе: 0,1 %
# Ключи второго прохода ядра Совкомбанка (core-pass2): строки сверки — только у книги с ключом.
WHOLESALE_WORDS = "опт (облигации, субординированный долг и опт по нужде)"   # К3: опт конца года, ≤ 10 %
TOL_ALLOWANCE = 0.02         # К7: резерв на кредиты конца года при резерве по книгам — 2 %
ALLOWANCE_WORDS = "резерв на кредиты по книгам"
TOL_GUAR_REL, TOL_GUAR_BN = 0.01, 0.5     # К5: RWA гарантий конца года — 1 % или 0,5 млрд ₽
GUAR_WORDS = "RWA гарантий"
TOL_STAT_REL, TOL_STAT_BN = 0.10, 0.5     # К4: ΔNII*_L терминала от стационарных ставок — 10 % или 0,5 млрд ₽
STAT_WORDS = "поправка ЧПД последнего года к стационарным ставкам книг"
LINE_VOLUME_WORDS = {"fees": "рост базы комиссий", "ins": "рост базы страхования"}     # К2: ≤ 0,5 п.п., как у М13
TOL_DRIVEN = 0.02            # К6: остаток ведомой книги конца года — 2 %
TOKEN_WORDS = "жетон DPS уплачен"     # К1: признак по годам прибыли (1 — да); у порога — 0,3 п.п. × RWA квартала решения
TOKEN_DPS_WORDS = "DPS года с жетоном"
DRIVEN_WORDS = "остаток книги за драйвером строки"
TOL_BUYBACK_BN = 1e-9        # выкуп за год: рубли книги, обе модели читают одну траекторию
# Ключи третьего прохода ядра Совкомбанка (core-pass3): строки сверки — только у книги с ключом.
TOL_YEAR_REL, TOL_YEAR_BN = 0.10, 0.5     # К-Т2а: поправка года терминала — 10 % или 0,5 млрд ₽
YEAR_WORDS = "поправка года терминала к средней длине года"
TOL_PHI = 1e-6               # К-Т2в: множитель угасания по календарю φ_W
FADE_WORDS = "множитель угасания по календарю"
BOUND_WORDS = "минимум ликвидности связан после выплаты избытка"     # К-Т2б: признак совпадает; у порога — любой (ПОРОГ)
TOL_CASH = 0.02              # К8: деньги конца года — 2 %, как ведомая книга К6
CASH_WORDS = "неработающие деньги"
# Правило ПОРОГ (решения № 4, Р4-16; spec.yaml прохода 3, control_model_r4_16): дискретное решение «у порога», если его
# величина z в пределах ε = 0,3 п.п. × RWA квартала решения (допуск нормативов М§17) хотя бы у одной модели; строки,
# которые идут за таким решением, не судятся (их число — в отчёте), сама сверка не может ими съесться.
EPS_THRESHOLD = TOL_RATIO
THRESHOLD_SHARE_MAX = 0.10   # доля исключённых строк клеток сверх неё — тест красный (находка, не повод расширять ε)
THRESHOLD_WORDS = "правило ПОРОГ: доля исключённых строк клеток"
THRESHOLD_REASONS = ("token", "policy_step", "excess_payout", "bound_after_payout", "growth_cut")
# строки, которые идут за долей прироста λ точнее допуска роста кредитов (3 п.п.): рост баз строк (0,5 п.п.), RWA гарантий
# (1 %), опт с частью по нужде (К3), ведомая книга (К6), деньги (К8). Исключаются с года, где исходы урезания роста у
# моделей разные (урезала одна), или за дискретным решением у порога — не во всех годах урезанного роста: так правило
# съело бы 4–8 % строк клеток книги p3 и 14 % на фикстуре со всеми ключами при нуле расхождений (сторож 10 %)
LAMBDA_GROUPS = ("v_fees", "v_ins", "v_opex", "rwa_guar", "wholesale", "driven", "cash")
# строки клетки с квартала дискретного решения: DPS и дивиденд, BV, нормативы — годов не раньше года решения (DPS
# кварталов и признак жетона — кварталов не раньше квартала решения); X_T, Y_X, ROE'_T, TV, V_c, S_c — клетки целиком; и
# строки за λ: жетон, ступень и избыток входят в условие роста (М§4.13.2 п. 2а — «рост урезается под жетон»)
DISCRETE_DATED = ("dps", "dps_q", "div", "bv", "n20", "n11", "token", "token_dps") + LAMBDA_GROUPS
DISCRETE_WHOLE = ("x_t", "y_x", "roe_t", "tv", "cell", "bb_s_price")
# решение за концом сетки (связанность минимума после выплаты, К-Т2б): ROE'_T, TV, V_c, S_c, доход стоящей доли, признак
TERMINAL_WHOLE = ("roe_t", "tv", "cell", "bb_s_price", "terminal_i_f", "bound")
KAPPA_KEY = "kappa_reference_world"         # credit.kappa_reference_world — мир-опора κ (М§4.6)
WINDOW_KEY, SCOPE_KEY = "window_backtest", "scope"      # checks.window_backtest; checks.cir_lt.scope
ANNUAL_ONLY = ("тест годовой ветви образца (решение о дивиденде раз в год): у книги квартальный календарь; "
               "на форме образца этот тест исполняет tests/test_control_forms.py "
               "(test_book_suite_case_on_the_sample_form)")
NO_FAIR_VALUE = ("строку FVC на форме образца проверяет tests/test_control_forms.py "
                 "(test_book_suite_case_on_the_sample_form)")
# Тесты строки FVC (М§4.6): у книги без кредитов по справедливой стоимости они пропускаются или идут вхолостую;
# на каталоге-заготовке из фикстуры формы образца их исполняет tests/test_control_forms.py.
FAIR_VALUE_TESTS = ("test_fvc_is_the_regime_deviation_on_fair_value_loans", "test_fvc_reference_stays_with_the_book",
                    "test_control_matches_core_on_shifted_cor_level")


def line_titles(book: dict) -> dict:
    """Слова строк сводки — из книги (meta.labels.control.lines, М прил. A): ровно пятнадцать строк; у книги с
    включённым выкупом (dividends.buyback) — ещё строка buyback."""
    titles = cm.c_bget(book, "meta.labels.control.lines")
    keys = LINE_KEYS + ((BUYBACK_LINE,) if cm.c_bopt(book, "dividends.buyback.enabled") else ())
    assert sorted(titles) == sorted(keys), "meta.labels.control.lines: набор строк не равен перечню сводки"
    return {k: str(v) for k, v in titles.items()}


def book_titles(book: dict) -> dict:
    """Подписи кредитных книг сводки — из книги (meta.labels.control.books): ровно кредитные книги."""
    titles = cm.c_bget(book, "meta.labels.control.books")
    credit = [b for b, sp in cm.c_bget(book, "nii.books").items() if sp.get("sector")]
    assert sorted(titles) == sorted(credit), "meta.labels.control.books: набор не равен кредитным книгам"
    return {k: str(v) for k, v in titles.items()}


def data_dir() -> Path | None:
    raw = os.environ.get(DATA_DIR_ENV)
    return Path(raw) if raw else None


def _inputs():
    root = data_dir()
    try:
        if root is not None:
            return (cm.c_book_machine(root / "assumptions" / "assumptions.yaml"), cm.c_facts_bundle(root / "facts"))
        return cm.c_book_machine(), cm.c_facts_bundle()
    except cm.ControlInputError as exc:
        pytest.fail(f"нет машинной книги или фактов ({exc}): контрольной модели не на чем считать")


@pytest.fixture(scope="module")
def inputs():
    return _inputs()


_SHARED: dict = {}        # прогоны на книге каталога данных — по одному на процесс (их делят файлы тестов)


def shared_control() -> dict:
    """Прогон контрольной модели на машинной книге каталога данных: один на процесс."""
    key = ("run", os.environ.get(DATA_DIR_ENV))
    if key not in _SHARED:
        book, facts = _inputs()
        try:
            _SHARED[key] = cm.c_control_run(book, facts)
        except cm.ControlUnsupported as exc:
            # отказ «не поддержано» на настоящей книге — провал, не пропуск (М§17)
            pytest.fail(f"контрольная модель не считает ветвь настоящей книги: {exc}")
    return _SHARED[key]


def shared_gates() -> dict:
    """Числа гейтов знака и печатаемая маржа контрольной модели на той же книге: один счёт на процесс
    (два прогона сетки для знака объёмных эффектов и клетки режима шока для знака стресса)."""
    key = ("gates", os.environ.get(DATA_DIR_ENV))
    if key not in _SHARED:
        book, facts = _inputs()
        ctl = shared_control()
        _SHARED[key] = {"volume_sign": cm.c_volume_sign(book, facts, ctl),
                        "stress_sign": cm.c_stress_sign(book, facts, ctl),
                        "printed_margin": cm.c_printed_margin(ctl)}
    return _SHARED[key]


@pytest.fixture(scope="module")
def control(inputs):
    return shared_control()


def annual_only(fn):
    """Тест годовой ветви образца: на книге с квартальным календарём — пропуск с причиной (ветвь на такой
    книге не исполняется). Тело теста доступно как __wrapped__: на каталоге-заготовке из фикстуры формы
    образца его исполняет tests/test_control_forms.py."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        book = _inputs()[0]
        if cm.c_is_quarterly(book):
            pytest.skip(ANNUAL_ONLY)
        return fn(*args, **kwargs)
    run.annual_only = True
    return run


def modal_scenario(control: dict, regime: str = "norm") -> str:
    """Сценарий капитала с наибольшей P(s | r) у режима — правилом, не литералом."""
    prs = cm.c_bget(control["ctx"]["B"], "joint.reg_prob_given_regime")[regime]
    ids = list(cm.c_bget(control["ctx"]["B"], "capital.reg_scenarios.ids"))
    return max(ids, key=lambda x: (float(prs[x]), -ids.index(x)))


# ============================================================================ свойства контрольной модели


@pytest.mark.tact
def test_ddm_equals_ri_in_every_cell(control):
    tol = cm.c_bnum(control["ctx"]["B"], "checks.ddm_ri_tol")
    assert tol <= TOL_DDM
    for c in control["cells"]:
        gap = abs(c["v_ddm"] - c["v_ri"]) / abs(c["v_ri"])
        assert gap <= 1e-9, (c["world"], c["regime"], c["scenario"], gap)


@pytest.mark.tact
def test_bv_balance_and_pbt_identities(control):
    A = control["ctx"]["A"]
    for c in control["cells"]:
        bv_prev = A["BV"]
        for r in c["rows"]:
            # в форме ключа выкупа (М3): выкуп года уменьшает BV рубль в рубль, в CI его нет (без ключа строки bb нет)
            bv = bv_prev + r["ni_sh"] - r["cpn_net"] + r["oci"] + r["om"] - r["div"] - r.get("bb", 0.0)
            assert math.isclose(bv, r["bv"], rel_tol=1e-9), (c["world"], c["regime"], c["scenario"])
            assert abs(r["assets"] - r["liabilities"]) <= 1e-9 * r["assets"]
            pbt = (r["nii"] - r["llp"] - r["fvc"] + r["fees"] + r["ins"] + r["misc"] + r["fvr"]
                   + r["noncore"] - r["opex"] + r["one_off"])
            assert math.isclose(pbt, r["pbt"], rel_tol=1e-12, abs_tol=1e-9)
            assert math.isclose(r["ni"], r["pbt"] - r["tax"] - r["ot"], rel_tol=1e-12, abs_tol=1e-9)
            assert math.isclose(sum(r["ni_q"].values()), r["ni_sh"], rel_tol=1e-9, abs_tol=1e-9)
            assert math.isclose(sum(r["ci_q"]), r["ci"], rel_tol=1e-9, abs_tol=1e-9)
            assert math.isclose(sum(r["fvc_q"]), r["fvc"], rel_tol=1e-12, abs_tol=1e-12)
            bv_prev = r["bv"]


@pytest.mark.tact
def test_layer_probabilities_sum_to_one(control):
    for name, ly in control["layers"].items():
        assert abs(ly["prob_sum"] - 1.0) <= 1e-12, name
    assert abs(sum(control["posterior"].values()) - 1.0) <= 1e-12


@pytest.mark.tact
def test_point_is_low_plus_lambda(control):
    pt = control["low"] + control["lam"] * (control["high"] - control["low"])
    assert math.isclose(pt, control["point"], rel_tol=1e-12)
    B = control["ctx"]["B"]
    assert math.isclose(control["ctx"]["gov_sum"], cm.c_bnum(B, "valuation.governance.discount"), abs_tol=1e-12)


@pytest.mark.tact
def test_dividend_history_test_of_the_book(control):
    """Тест истории выплат вида книги (М§5.2). exact — формула пула на истории facts/dividends.json даёт
    объявленный DPS до копейки: все годы с полными данными, не меньше двух последних. cap — в каждом
    завершённом году сумма объявленных пулов не больше потолка × отчётная прибыль акционеров; завершённый
    год обязан быть, неполный — строка диагностики без вердикта."""
    kind = control["history_test"]
    if kind == cm.HIST_NONE:
        assert control["dps_history"] == []
        return
    if kind == cm.HIST_CAP:
        done = [h for h in control["dps_history"] if h["complete"]]
        assert done, "в facts/dividends.json → years нет ни одного завершённого года"
        for h in control["dps_history"]:
            assert math.isclose(h["limit"], h["cap"] * h["ni_shareholders"], rel_tol=1e-12)
            assert math.isclose(h["share"] * h["ni_shareholders"], h["pool"], rel_tol=1e-9, abs_tol=1e-9)
            assert (h["ok"] is None) == (not h["complete"])
            assert h["ok"] is not False, h
        return
    rows = [h for h in control["dps_history"] if h["declared"] is not None]
    assert len(rows) >= 2, "в facts/dividends.json меньше двух лет истории DPS"
    for h in rows:
        assert h["ok"], h


@pytest.mark.tact
def test_transmission_solved(control):
    tr = control["transmission"]
    tol = cm.c_bnum(control["ctx"]["B"], "checks.transmission_tol")
    assert abs(tr["nss_level"] - tr["target_eng"]) <= max(tol, 1e-12)      # стационар мира уровня = ключ цели
    assert abs(tr["t_real"] - cm.c_bnum(control["ctx"]["B"], "nii.transmission.target")) <= max(tol, 1e-12)


@pytest.mark.tact
def test_anchor_reproduces_capital_facts(control):
    """На якоре Н20.0 (до вычета дивиденда) и Н1.1 банка воспроизводятся (условие калибровки М§4.11)."""
    A = control["ctx"]["A"]
    for c in control["cells"]:
        cap = c["anchor_capital"]
        assert abs(cap["n20"] - A["n20_fact"]) <= TOL_RATIO
        assert abs(cap["n11"] - A["n11_fact"]) <= TOL_RATIO


@pytest.mark.tact
def test_crisis_cell_skips_and_catches_up(control):
    """(N, crisis, strict): выплата, решаемая в год шока (год якоря + shock_year_offset, М§3.2),
    отменена, пул уходит в отложенный и возвращается догоняющей выплатой (М§5.3 пп. 4–5)."""
    B = control["ctx"]["B"]
    shock = control["shock_year"]
    assert shock == control["ctx"]["anchor"][0] + int(cm.c_bget(B, "regimes.crisis.shock_year_offset"))
    c = cm.c_cell_of(control, "N", "crisis", "strict")
    if control["quarterly"]:
        # квартальный режим (М§5.7.4 п. 3): отменяются решения модели в кварталах года шока; записи
        # реестра кризис не отменяет; в прочих режимах отмены нет
        in_shock = [d for d in c["decisions_q"] if cm.c_qper(control["ctx"]["anchor"], d["q"])[0] == shock]
        assert in_shock and all(d["source"] in ("crisis_skip", "register") for d in in_shock)
        assert all(d["div"] == 0.0 and d["want"] >= 0.0 for d in in_shock if d["source"] == "crisis_skip")
        assert all(d["source"] != "crisis_skip" for d in c["decisions_q"]
                   if cm.c_qper(control["ctx"]["anchor"], d["q"])[0] != shock)
        if not cm.c_bget(B, "dividends.crisis.catch_up"):
            assert all(d["catch"] == 0.0 and d["deferred_after"] == 0.0 for d in c["decisions_q"])
        for other in ("soft", "norm", "downturn"):
            assert all(d["source"] != "crisis_skip"
                       for d in cm.c_cell_of(control, "N", other, "strict")["decisions_q"])
        one = cm.c_bget(B, "regimes.crisis.one_off_loss")
        row = c["rows"][control["years"].index(cm.c_per_parse(one["period"])[0])]
        assert row["one_off"] == float(one["amount"])                # разовый убыток — в году шока
        return
    skipped = c["decisions"][shock - 1]
    assert skipped["kind"] == "crisis_skip" and skipped["div"] == 0.0 and skipped["want"] > 0.0
    caught = sum(d.get("catch", 0.0) for d in c["decisions"].values())
    assert math.isclose(caught, skipped["want"], rel_tol=1e-9)
    assert c["rows"][-1]["D"] == pytest.approx(0.0, abs=1e-9)
    for other in ("soft", "norm", "downturn"):                      # отмена — только в клетке кризиса
        assert cm.c_cell_of(control, "N", other, "strict")["decisions"][shock - 1]["kind"] != "crisis_skip"


@pytest.mark.tact
def test_binding_capital_cell(control):
    """(M, downturn, strict): хотя бы в одном году запас H меньше пула политики — выплата по
    остатку сверх требований (М§5.3 п. 3), дивиденд не превышает запас."""
    c = cm.c_cell_of(control, "M", "downturn", "strict")
    if control["quarterly"]:
        # ветвь с квартальным проходом: капитал связывает рост (λ < 1) или дивиденд (cut) хотя бы в
        # одном квартале; при ограничении роста норматив связывающего стоит на требовании с глиссадой
        quarters = [x for r in c["rows"] for x in r["quarters"]]
        cut = [d for d in c["decisions_q"] if d["cut"]]
        slowed = [x for x in quarters if x["lam"] < 1.0]
        assert cut or slowed, "в клетке (M, downturn, strict) капитал ни разу не связывает"
        rule = control["growth_rule"]
        for x in slowed:
            if rule["lam_min"] < x["lam"] < 1.0:
                gap = min(x["n20"] - x["req20_glide"], x["n11_star"] - x["req11_glide"])
                assert abs(gap) <= rule["tol"], x
        for d in cut:
            assert d["base_div"] <= max(0.0, d["headroom"]) + 1e-9
        return
    bound = [d for d in c["decisions"].values() if d["kind"] == "policy" and d["H"] < d["want"]]
    assert bound, "в клетке (M, downturn, strict) капитал ни разу не связывает"
    for d in bound:
        assert d["div"] <= max(0.0, d["H"]) + d.get("catch", 0.0) + d.get("excess", 0.0) + 1e-9


@pytest.mark.tact
def test_flat_world_gives_book_value(control):
    """Плоский мир: плоская кривая, доход ровно k на капитал (с учётом даты выплаты) и ROE_T = k_T
    ⇒ V = BV_v (М§17) — проверка формы RI/DDM и терминала контрольной модели. Терминальный год
    подобран так, что ROE_T = k_T при множителе угасания книги: одностороннее угасание (М§7) само
    доходность ниже k_T к k_T не подтягивает.

    Книга второй формы банка (Совкомбанк): выкуп акций (dividends.buyback) — распределение, датированное концом квартала
    покупки, как дивиденд (М§5.6): в доходе «ровно k» и в капитале он стоит рядом с дивидендом. PBT терминала — корень
    ROE_T = k_T по двум оценкам (ROE_T линеен по PBT; так же при терминале от стационарных ставок К4, среднем годе К-Т2а и
    календаре угасания К-Т2в). Постоянная часть терминала (К-Т2, `valuation.terminal.fixed_growth_share`) доходность k_T
    не держит по построению (её числа — tests/test_control_pass*.py): тождество V = BV_v — без неё, а с ней — RI = DDM."""
    ctx = dict(control["ctx"])
    B = cm.copy.deepcopy(ctx["B"])
    z = 0.12
    for w in ctx["worlds"]:
        B["worlds"][w]["zero_curve"] = {"1": z, "3": z, "5": z, "10": z, "LT": z}
    add = cm.c_bnum(B, "valuation.beta_e") * cm.c_bnum(B, "valuation.erp")
    ctx["B"] = B
    ctx["disc"] = {w: cm.CDisc(B["worlds"][w]["zero_curve"], add, 0.3) for w in ctx["worlds"]}
    scen = modal_scenario(control)
    base = cm.c_cell_of(control, "H", "norm", scen)
    df = ctx["disc"]["H"]
    ck, periods = ctx["clock"], ctx["periods"]
    rows = [dict(r) for r in base["rows"]]
    bv = ctx["A"]["BV"]
    bb_on = ctx.get("bb") is not None
    for i, r in enumerate(rows):
        te = ck["tau_end"][i]
        k = (df(ck["tau_end"][i - 1]) / df(te) - 1.0) if i > ck["p0"] else (1.0 / df(te) - 1.0)
        # распределения года: дивиденды и выкуп (квартал j — конец квартала)
        flows = list(r["div_list"]) + ([(j, x) for j, x in enumerate(r["bb_q"]) if x] if bb_on else [])
        corr = 0.0
        for j, amt in flows:
            ta = ck["t_start"][i] + 0.25 * (j + 1)
            if ta > 0.0:
                corr += amt * (df(ta) / df(te) - 1.0)
        gone = sum(amt for j, amt in flows if ck["t_start"][i] + 0.25 * (j + 1) <= 0.0)
        if i == ck["p0"]:
            # (1 − e)·CI − k·BV_v + corr = 0 при BV_v = BV + e·CI
            # распределение до даты оценки уже вычтено из BV_v: BV_v = BV + e·CI − gone
            e = ck["e"]
            ci = (k * (bv - gone) - corr) / ((1.0 - e) - k * e)
        else:
            ci = k * bv - corr
        r["ci"] = ci
        r["ci_q"] = [ci / periods[i]["n"]] * periods[i]["n"]
        bv = bv + ci - r["div"] - (sum(r["bb_q"]) if bb_on else 0.0)
        r["bv"] = bv
    cell = {"world": "H", "regime": "norm", "scenario": scen}

    def at(context: dict, pbt: float) -> dict:
        rs = [dict(r) for r in rows]
        rs[-1]["pbt"] = pbt
        return cm._c_value_cell(context, cell, rs, {})

    def flat(context: dict) -> dict:
        lo, hi = at(context, 0.0), at(context, 100.0)        # X_T, BV*, Y_X, k_T, g_T от PBT терминала не зависят
        return at(context, (lo["k_t"] - lo["roe_t_raw"]) * 100.0 / (hi["roe_t_raw"] - lo["roe_t_raw"]))

    if ctx.get("term_fixed") is not None:                 # с постоянной частью терминала — RI и DDM одно число
        out = flat(ctx)
        assert out["v_ri"] == pytest.approx(out["v_ddm"], rel=1e-10)
        ctx["term_fixed"] = None
    out = flat(ctx)
    assert out["roe_t_raw"] == pytest.approx(out["k_t"], abs=1e-14)
    assert out["roe_t"] == pytest.approx(out["k_t"], abs=1e-14)
    assert out["v_ri"] == pytest.approx(out["bv_v"], rel=1e-10)
    assert out["v_ddm"] == pytest.approx(out["bv_v"], rel=1e-10)


def with_kappa_world(book: dict, world) -> dict:
    """Копия книги с миром-опорой κ world (ключ credit.kappa_reference_world); None — ключ снят."""
    out = cm.copy.deepcopy(book)
    if world is None:
        out["credit"].pop(KAPPA_KEY, None)
    else:
        out["credit"][KAPPA_KEY] = world
    return out


def plain_world(book: dict) -> str:
    """Мир без κ-добавки: мир-опора κ книги, а без ключа опоры — мир N (М§4.6)."""
    return cm.c_kappa_world(book) or cm.W_LOW


def other_kappa_branch(book: dict) -> dict:
    """Книга на другой ветви ключа мира-опоры κ: без ключа — опорой становится мир слоя «рыночные ставки как
    есть», с ключом — ключ снят. Так обе ветви исполняются на любой книге: одна — её прогоном, вторая —
    подменой."""
    if cm.c_bopt(book, f"credit.{KAPPA_KEY}") is None:
        return with_kappa_world(book, cm.c_bget(book, "joint.macro_neutral_world"))
    return with_kappa_world(book, None)


def kappa_reference_checks(book: dict, facts: dict, regime: str, scenario: str, *, full: bool = False) -> None:
    """Мир-опора κ своим счётом (ключ credit.kappa_reference_world, М§4.6) — обе ветви ключа подменой книги.

    Без ключа добавка квартала q — κ × max(0, rr_W − rr_N) квартала q − L: в мире N ноль, нигде не ниже нуля.
    С миром-опорой — κ × (rr_W − rr_опоры) с любым знаком: в мире-опоре ноль, в мире с меньшей реальной
    ставкой уровень CoR ниже уровня книги. История до сетки у миров общая — добавка ноль в обеих ветвях. Тем
    же правилом живут CoR клетки (разность CoR клеток двух миров одного режима — κ × разность их реальных
    ставок) и кредитная маржа стационара. Мир не из worlds.ids — отказ. full — ещё клетки всех миров и
    ожидание CoR режима в A-P2u (М§12): дольше, вне такта."""
    kap, lag = cm.c_bnum(book, "credit.kappa"), int(cm.c_bnum(book, "credit.real_rate_lag_q"))
    worlds = list(book["worlds"]["ids"])
    plain = cm.c_control_context(with_kappa_world(book, None), facts)
    anchor, last = plain["anchor"], plain["Q"]
    assert kap > 0.0 and 0 <= lag < last, "книга держит κ-добавку выключенной: проверять нечего"

    def rr(w, k):                                       # реальная ставка мира в квартале сетки k
        return cm.c_world_quarter(book, w, "real_key", *cm.c_qper(anchor, k))

    def gaps(ctx, w):                                   # разности κ-добавки по кварталам сетки 1…Q
        return [g for per in ctx["wv"][w] for g in per["kappa_gaps"]]

    def expected(w, ref):
        out = []
        for k in range(1, last + 1):
            if k - lag < 1:
                out.append(0.0)                         # история до сетки у миров общая
            elif ref is None:
                out.append(max(0.0, rr(w, k - lag) - rr(cm.W_LOW, k - lag)))
            else:
                out.append(rr(w, k - lag) - rr(ref, k - lag))
        return out

    for w in worlds:
        assert gaps(plain, w) == expected(w, None), w
        assert min(gaps(plain, w)) >= 0.0
    assert not any(gaps(plain, cm.W_LOW))
    by_ref, negative = {}, False
    for ref in worlds:
        ctx = by_ref[ref] = cm.c_control_context(with_kappa_world(book, ref), facts)
        assert not any(gaps(ctx, ref)), ref             # в мире-опоре добавки нет
        for w in worlds:
            assert gaps(ctx, w) == expected(w, ref), (ref, w)
            negative = negative or min(gaps(ctx, w)) < 0.0
            # кредитная маржа стационара несёт ту же добавку на долгосрочном конце (М§4.5)
            shift = (rr(w, last) - rr(ref, last)) - max(0.0, rr(w, last) - rr(cm.W_LOW, last))
            assert ctx["tr"]["loan_margin"][w] - plain["tr"]["loan_margin"][w] == pytest.approx(-kap * shift, abs=1e-15)
    assert negative, "реальные ставки миров книги равны во всех кварталах: знак добавки проверить не на чем"
    # CoR клетки: путь режима и отклонение A-P2u у миров одного режима общие, различает их только добавка
    ref = cm.c_bget(book, "joint.macro_neutral_world")
    ctx = by_ref[ref]
    home = cm.c_cell_annual(ctx, ref, regime, scenario)
    others = [w for w in worlds if w != ref]
    for w in others if full else others[:1]:
        away, want = cm.c_cell_annual(ctx, w, regime, scenario), expected(w, ref)
        got = [a - b for mine, base in zip(away["rows"], home["rows"]) for a, b in zip(mine["cor_q"], base["cor_q"])]
        assert got == pytest.approx([kap * g for g in want], abs=1e-15), w
    if full:
        # ожидание CoR режима в A-P2u — среднее по мирам слоя «свой взгляд» с той же добавкой
        k = min(last, lag + 1)
        y, q = cm.c_qper(anchor, k)
        pw = {w: float(v) for w, v in book["joint"]["world_prob"].items()}
        mu = cm.c_expectations_ctl(ctx, [(y, q)])[("cor", regime, y, q)]
        want = cm.c_cor_path_engine(ctx, regime, y, q) + kap * sum(pw[w] * expected(w, ref)[k - 1] for w in worlds)
        assert mu == pytest.approx(want, abs=1e-15)
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(with_kappa_world(book, "нет такого мира"), facts)


@pytest.mark.tact
def test_kappa_addon_stands_on_its_reference_world(inputs, control):
    """κ-добавка к CoR на книге как она есть: без ключа мира-опоры — относительно мира N и только вверх (в мире
    N ноль), с ключом — относительно названного мира с любым знаком (в нём ноль). Обе ветви ключа — подменой."""
    book, facts = inputs
    ref = cm.c_kappa_world(control["ctx"]["B"])
    for w in control["ctx"]["worlds"]:
        flat = [g for per in control["ctx"]["wv"][w] for g in per["kappa_gaps"]]
        assert len(flat) == control["ctx"]["Q"]
        if w == (ref or cm.W_LOW):
            assert not any(flat), w
        if ref is None:
            assert min(flat) >= 0.0, w
    kappa_reference_checks(book, facts, cm.R_NORM, modal_scenario(control))


def test_kappa_reference_world_in_every_world_and_in_learning(inputs, control):
    """То же полным счётом (вне такта): клетки всех миров и ожидание CoR режима в A-P2u."""
    book, facts = inputs
    kappa_reference_checks(book, facts, cm.R_NORM, modal_scenario(control), full=True)


@pytest.mark.tact
def test_draft_worlds_match_machine_book(inputs):
    """Миры и надстройка, собранные контрольной моделью из копии записи по таблице М§3.1, совпадают
    с блоком worlds машинной книги (независимая проверка сборки книги)."""
    book, _ = inputs
    if not (cm.WORLDS_SOURCE.exists() and cm.WORLDS_BANK.exists() and cm.DRAFT_YAML.exists()):
        pytest.skip("нет черновика, копии записи миров или надстройки")
    lt = {w: book["worlds"][w]["zero_curve"]["LT"] for w in book["worlds"]["ids"] if w != cm.W_MKT}
    draft = cm.c_book_from_draft(curve_lt=lt)
    for w in book["worlds"]["ids"]:
        for f, v in book["worlds"][w].items():
            if f == "name":
                continue
            got = draft["worlds"][w][f]
            if isinstance(v, dict):
                assert {str(k): float(x) for k, x in v.items()} == pytest.approx(
                    {str(k): float(x) for k, x in got.items()}, abs=1e-12), (w, f)
            else:
                assert float(v) == pytest.approx(float(got), abs=1e-12), (w, f)
    assert draft["worlds_bank"] == book["worlds_bank"]


@pytest.mark.tact
def test_template_plus_worlds_is_the_machine_book(inputs):
    """Шаблон книги + миры и надстройка, собранные контрольной моделью, — это машинная книга целиком
    (кроме названий миров — подписи сборки семейства) и хэш надстройки = sha256 worlds_bank.json:
    независимая проверка build_assumptions.py (М§3.1, прил. A)."""
    import hashlib
    book, _ = inputs
    root = data_dir()
    folder = cm.BOOK_DIR if root is None else root / "assumptions"
    template, source, bank = (folder / cm.TEMPLATE_YAML.name, folder / cm.WORLDS_SOURCE.name,
                              folder / cm.WORLDS_BANK.name)
    if not (template.exists() and source.exists() and bank.exists()):
        pytest.skip("нет шаблона, копии записи миров или надстройки")
    lt = {w: book["worlds"][w]["zero_curve"]["LT"] for w in book["worlds"]["ids"] if w != cm.W_MKT}
    built = cm.c_book_from_draft(template, worlds_source=source, overlay=bank, curve_lt=lt)
    assert book["worlds"]["overlay"]["sha256"] == hashlib.sha256(bank.read_bytes()).hexdigest()
    mine = cm.copy.deepcopy(book)
    for tree in (mine, built):
        tree["worlds"]["overlay"]["sha256"] = None
        for w in book["worlds"]["ids"]:
            tree["worlds"][w].pop("name", None)
    assert _same_tree(built, mine)


def _same_tree(a, b, path="") -> bool:
    """Равенство деревьев книги: числа — до 1e-12, остальное — точно (путь расхождения в ошибке)."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert set(map(str, a)) == set(map(str, b)), f"{path}: ключи {sorted(set(map(str, a)) ^ set(map(str, b)))}"
        bk = {str(k): v for k, v in b.items()}
        return all(_same_tree(v, bk[str(k)], f"{path}.{k}") for k, v in a.items())
    if isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), path
        return all(_same_tree(x, y, f"{path}[{i}]") for i, (x, y) in enumerate(zip(a, b)))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        assert abs(float(a) - float(b)) <= 1e-12, (path, a, b)
        return True
    assert a == b, (path, a, b)
    return True


# ============================================================================ решения W1 (LEAD-DECISIONS-2)


def _history_dps(facts: dict) -> float:
    """DPS последнего года истории — тестовое значение записи реестра (не допущение)."""
    return float(cm._c_nodeval(facts["dividends"]["history"][-1]["dps_ordinary"]))


def _declared(year: int, dps: float, agm_end: dt.date, status: str = "declared") -> dict:
    """Запись реестра сценария: отсечка = экс-дата через 20 дней после конца квартала ГОСА."""
    ex = agm_end + dt.timedelta(days=20)
    return {"year": year, "dps": dps, "status": status, "record_date": ex.isoformat(),
            "last_buy_date": (ex - dt.timedelta(days=1)).isoformat(), "ex_date": ex.isoformat(),
            "pay_date": (ex + dt.timedelta(days=14)).isoformat(), "sources": ["сверка М§17"]}


def _agm_end(book: dict) -> tuple[int, dt.date]:
    """Год прибыли якоря и конец квартала ГОСА, на котором решается его дивиденд (М§5.4)."""
    y0, _ = cm.c_per_parse(book["meta"]["anchor_period"])
    return y0, cm.c_q_last_day(y0 + 1, int(book["dividends"]["calendar"]["agm_quarter"]))


@pytest.mark.tact
def test_sigma0_enters_spreads_from_sigma0_from(inputs, control):
    """A1 F1, В8 (М§4.4): сдвиг σ0 прибавляется ко всем значениям спредов книг с lt_shift с года
    sigma0_from, не раньше: +σ0_A у активов, −σ0_L у пассивов. Сдвиг sigma0_from на год позже не меняет
    ЧПД раньше sigma0_from и поднимает ЧПД года sigma0_from (сдвиг стационарного ЧПМ Δ0 < 0); стационар
    (σ0_A, σ0_L, φ, T_real, пары) от sigma0_from не зависит."""
    book, facts = inputs
    ctx = control["ctx"]
    tr = ctx["tr"]
    y1 = ctx["sigma0_from"]
    for b, sp in ctx["B"]["nii"]["books"].items():
        sig = tr["sigma0"] if sp["side"] == cm.LOANS_SIDE else -tr["sigma0_liab"]
        for y in (y1 - 1, y1):
            got = cm.c_spread_at(ctx, b, y, cm.QY)
            want = cm.c_traj_at(sp["spread"], y, cm.QY) + (sig if sp.get("lt_shift") and y >= y1 else 0.0)
            assert got == want, (b, y)
    if y1 + 1 > control["years"][-1]:
        pytest.skip("sigma0_from — последний год явного участка: сдвинуть некуда")
    b2 = cm.copy.deepcopy(book)
    b2["nii"]["sigma0_from"] = y1 + 1
    later = cm.c_control_context(b2, facts)                      # сетка не нужна: стационар и одна клетка
    for k in ("sigma0", "sigma0_liab", "phi", "pairs"):
        assert later["tr"][k] == tr[k], k
    base_rows = cm.c_cell_of(control, "H", "norm", "schedule")["rows"]
    late_rows = cm.c_cell_annual(later, "H", "norm", "schedule")["rows"]
    for y, r0, r1 in zip(control["years"], base_rows, late_rows):
        if y < y1:
            assert r1["nii"] == r0["nii"], y
        elif y == y1:
            assert (r1["nii"] - r0["nii"]) * tr["delta0"] < 0.0, (y, r0["nii"], r1["nii"])


@pytest.mark.tact
def test_near_spread_keys_follow_anchor_rates(control):
    """A1 F3 (М§4.4, правило книги — независимая проверка): ключ года якоря траектории спреда =
    ставка якоря книги − опора мира H первого прогнозного квартала (у пассивов — β × опора), до
    половины пятого знака записи книги: при неизменной опоре ставка не прыгает в первом квартале."""
    ctx = control["ctx"]
    B, A = ctx["B"], ctx["A"]
    y0, _ = ctx["anchor"]
    fy, fq = cm.c_per_parse(B["meta"]["first_period"])
    ref_w = B["nii"]["transmission"]["reference_world"]
    checked = 0
    for b, sp in B["nii"]["books"].items():
        path = sp["spread"]
        if not isinstance(path, dict) or str(y0) not in {str(k) for k in path}:
            continue                                        # скалярный спред — калибровка без ближних ключей
        ref = cm.c_world_quarter(B, ref_w, cm.c_ref_field(sp["ref"]), fy, fq)
        beta = 1.0 if sp["side"] == cm.LOANS_SIDE else float(sp["beta"])
        key = float({str(k): v for k, v in path.items()}[str(y0)])
        assert abs(key - (A["rate0"][b] - beta * ref)) <= 5e-6 + 1e-12, (b, key, A["rate0"][b] - beta * ref)
        checked += 1
    assert checked, "в книге нет ни одной траектории спреда с ключом года якоря"


def growth_cut(row: dict) -> bool:
    """Рост кредитных книг периода урезан ограничением капиталом (М§4.13.2): доля прироста хотя бы одного квартала
    меньше 1 или в периоде есть навёрстывание. У ветви без квартального прохода капитала полей нет — не урезан."""
    return any(x < 1.0 for x in row.get("lam_q") or ()) or bool(row.get("catch_up"))


@pytest.mark.tact
def test_near_nim_shift_is_common_and_outside_nss(inputs, control):
    """A1 F2 (М§3.2, §4.4–§4.5): ближний сдвиг ЧПМ одинаков во всех клетках, не входит в Nss (σ0, φ,
    T_real и пары от него не зависят) и прибавляется к ЧПД как near × ĪEA × дни/365.

    Последнее сверяется там, где канал «прибыль шага → капитал → кредиты → ЧПД» (М§4.13.2) закрыт: при связывающем
    ограничении роста разность ЧПД несёт ещё и его, и это не ближний сдвиг (флаг 6 интеграции круга 4: H/norm/schedule
    книги c709f22 — +2,8 % сверх near × ĪEA при +29 млрд ₽ кредитов). (а) Клетки книги, где рост кредитных книг первого
    периода не урезан капиталом ни на книге, ни с шагом (доля прироста 1 во всех кварталах, навёрстывания нет), — первая
    такая клетка каждого мира; (б) у книги с ограничением роста — клетка H/norm/schedule на книге и на книге с шагом, обе
    с выключенным ограничением (подмена одного пути capital.growth_constraint.enabled): канал снят у всех клеток. Допуск
    прежний. Не сверено ни одной клетки — провал: предпосылку проверить не на чем."""
    book, facts = inputs
    first = control["cells"][0]["rows"]
    for c in control["cells"]:
        assert [r["near"] for r in c["rows"]] == [r["near"] for r in first]
    b2 = cm.copy.deepcopy(book)
    bump = cm.c_bnum(b2, "nii.transmission.fd_step")          # «шаг» из книги, не число теста
    near = b2["regimes"]["near_nim_shift"]
    b2["regimes"]["near_nim_shift"] = ({k: (v if k == "LT_from" else v + bump) for k, v in near.items()}
                                       if isinstance(near, dict) else near + bump)
    ctx2 = cm.c_control_context(b2, facts)
    for k in ("sigma0", "sigma0_liab", "phi", "t_real", "pairs"):
        assert ctx2["tr"][k] == control["transmission"][k], k
    p0 = ctx2["periods"][0]
    checked = []
    for w in ctx2["worlds"]:
        for c in control["cells"]:
            r_base = c["rows"][0]
            if c["world"] != w or growth_cut(r_base):
                continue
            r_bump = cm.c_cell_annual(ctx2, w, c["regime"], c["scenario"])["rows"][0]
            if growth_cut(r_bump):
                continue
            expect = bump * r_base["iea"] * p0["days"] / cm.DAYS_BASE
            assert (r_bump["nii"] - r_base["nii"]) == pytest.approx(expect, rel=0.02), (w, c["regime"], c["scenario"])
            checked.append((w, c["regime"], c["scenario"]))
            break
    if cm.c_growth_rule(book) is not None:
        free = []
        for b in (book, b2):
            b_off = cm.copy.deepcopy(b)
            b_off["capital"]["growth_constraint"]["enabled"] = False
            free.append(cm.c_cell_annual(cm.c_control_context(b_off, facts), "H", "norm", "schedule")["rows"][0])
        r_base, r_bump = free
        assert not growth_cut(r_base) and not growth_cut(r_bump)
        expect = bump * r_base["iea"] * p0["days"] / cm.DAYS_BASE
        assert (r_bump["nii"] - r_base["nii"]) == pytest.approx(expect, rel=0.02), "без ограничения роста"
        checked.append(("H", "norm", "schedule", "без ограничения роста"))
    assert checked, "ни в одной клетке канал капитала не закрыт: сверять не на чем"


def _with_governance(book: dict, g: float) -> dict:
    """Копия книги с дисконтом за управление g: вся величина — в первом канале (сумма каналов = дисконту)."""
    b = cm.copy.deepcopy(book)
    b["valuation"]["governance"]["discount"] = g
    for i, comp in enumerate(b["valuation"]["governance"]["components"]):
        comp["value"], comp["sign"] = (g if i == 0 else 0.0), 1
    return b


@pytest.mark.tact
@annual_only
def test_end_of_day_at_agm_quarter_end(inputs):
    """A2, № 25 (М§0.2, §8.1–§8.2, §18): «конец квартала — конец дня» и D_pend. С записью реестра за год
    прибыли точка на E_qA и E_qA + 1 — одна позиция линейки (равны); между E_qA − 1 и E_qA она меняется
    только на перекат двух дней (< 0,1 % цены) — не на DPS и не на g_gov × DPS: до вычета из BV
    объявленный дивиденд выведен из-под дисконта суммой D_pend, после — стоит в мосте. Поэтому скачок
    при другом дисконте g отличается ровно множителем (1 − g). Без записи точка на E_qA падает на
    ожидаемый дивиденд модели (клетки вычитают его, моста нет)."""
    book, facts = inputs
    y0, e_qa = _agm_end(book)
    dps = _history_dps(facts)
    f2 = cm.copy.deepcopy(facts)
    f2["dividends"]["register_seed"] = [_declared(y0, dps, e_qa)]
    run = {d: cm.c_control_run(book, f2, valuation_date=e_qa + dt.timedelta(days=d)) for d in (-1, 0, 1)}
    amount = dps * run[0]["ctx"]["A"]["N_out"] / 1000.0
    assert run[-1]["bridge_amount"] == 0.0 and run[-1]["pending_amount"] == pytest.approx(amount, rel=1e-12)
    assert run[0]["bridge_amount"] == pytest.approx(amount, rel=1e-12) and run[0]["pending_amount"] == 0.0
    assert run[0]["point"] == pytest.approx(run[1]["point"], rel=1e-12)
    jump = run[0]["point"] - run[-1]["point"]
    assert 0.0 < jump < 0.001 * run[0]["point"], (jump, run[0]["point"])      # только перекат двух дней
    g1 = run[0]["governance"]
    g2 = 10.0 * g1 if g1 > 0.0 else cm.c_bnum(book, "nii.transmission.fd_step")
    b2 = _with_governance(book, g2)
    alt = {d: cm.c_control_run(b2, f2, valuation_date=e_qa + dt.timedelta(days=d)) for d in (-1, 0)}
    jump2 = alt[0]["point"] - alt[-1]["point"]
    assert jump2 / jump == pytest.approx((1.0 - g2) / (1.0 - g1), rel=1e-9)   # g × DPS в скачке нет
    assert abs(jump2 - jump) < 0.1 * (g2 - g1) * dps
    # без записи реестра — падение на дивиденд модели в конце квартала ГОСА
    free = {d: cm.c_control_run(book, facts, valuation_date=e_qa + dt.timedelta(days=d)) for d in (-1, 0)}
    B = free[0]["ctx"]["B"]
    lam, gov = free[0]["lam"], free[0]["governance"]
    weights = cm.c_layer_weights(B)
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")

    def c_mean_dps(layer):
        return sum(weights[layer].get(c["world"], 0.0) * free[0]["posterior"][c["regime"]]
                   * float(prs[c["regime"]][c["scenario"]]) * c["decisions"][y0]["dps"] for c in free[0]["cells"])

    drop = (1.0 - gov) * (c_mean_dps("macro_neutral")
                          + lam * (c_mean_dps("analytical") - c_mean_dps("macro_neutral")))
    assert free[-1]["point"] - free[0]["point"] == pytest.approx(drop, rel=0.05)


@pytest.mark.tact
@annual_only
def test_excess_payout_ramps_in(control):
    """A4 (М§5.3 п. 4): ε_Y = ε × min(1, (Y − from + 1)/ramp_years) — накопленный избыток выпускается
    за ramp_years лет, а не разом; до from_profit_year — ноль."""
    B = control["ctx"]["B"]
    fy = int(cm.c_bnum(B, "dividends.excess.from_profit_year"))
    eps, ramp = cm.c_bnum(B, "dividends.excess.epsilon"), int(cm.c_bnum(B, "dividends.excess.ramp_years"))
    seen = set()
    for c in control["cells"]:
        for yp, d in c["decisions"].items():
            if d["kind"] != "policy":
                continue
            want = eps * min(1.0, (yp - fy + 1) / ramp) if yp >= fy else 0.0
            assert d["eps"] == pytest.approx(want, abs=1e-15), (c["world"], c["regime"], c["scenario"], yp)
            seen.add(yp)
    years = set(range(fy, fy + ramp)) & set(range(control["years"][0], control["years"][-1]))
    assert years <= seen, "годы ввода ε без решения по политике"


# вне такта сервера: один из самых долгих тестов набора — набор такта держит цель времени (ops/budgets.json)
def test_regime_update_fact_equal_to_expectation_moves_nothing(inputs):
    """A5 (М§12, §18): при одном режиме наблюдение, равное ожиданию μ (среднее слоя «свой взгляд» по
    клеткам режима), не меняет ни вероятностей, ни отклонений, ни V0 слоёв."""
    book, facts = inputs
    b1 = cm.copy.deepcopy(book)
    regimes = list(b1["regimes"]["ids"])
    only = regimes[1] if len(regimes) > 1 else regimes[0]
    b1["joint"]["regime_prob"] = {r: (1.0 if r == only else 0.0) for r in regimes}
    base = cm.c_control_run(b1, facts)
    per = b1["meta"]["first_period"]
    y, q = cm.c_per_parse(per)
    mu = cm.c_expectations_ctl(base["ctx"], [(y, q)])
    A = base["ctx"]["A"]
    b2 = cm.copy.deepcopy(b1)
    b2["joint"]["regime_update"]["observations"] = [{
        "period": per, "cor": cm.c_to_mgmt(A, "cor", mu[("cor", only, y, q)]),
        "nim": cm.c_to_mgmt(A, "nim", mu[("nim", only, y, q)]), "se_cor": 0.0, "se_nim": 0.0, "basis": "mgmt"}]
    obs = cm.c_control_run(b2, facts)
    assert obs["posterior"] == pytest.approx(base["posterior"], abs=1e-12)
    for x in ("cor", "nim"):
        assert abs(obs["ctx"]["dev"][only][x]["m"]) <= 1e-12
    for name in cm.LAYERS:
        assert obs["layers"][name]["v0"] == pytest.approx(base["layers"][name]["v0"], rel=1e-9)


@pytest.mark.tact
def test_transmission_pairs_telescope(control):
    """A6 (М§4.5): парные передачи соседних по key^LT миров телескопичны — Σ T_pair × Δkey^LT =
    Nss(крайний верхний) − Nss(крайний нижний); при N и M по краям это T_real × (key_M − key_N).
    ROE-эквивалент — тот же множитель IEA_0/BV_0 × (1 − τ_eff,L) для T* и пар."""
    tr = control["transmission"]
    key, nss = tr["key_lt"], tr["nss"]
    order = sorted(key, key=key.get)
    total = 0.0
    for w1, w2 in zip(order, order[1:]):
        t = tr["pairs"][f"{w1}_{w2}"]
        assert t is not None
        total += t * (key[w2] - key[w1])
    assert total == pytest.approx(nss[order[-1]] - nss[order[0]], abs=1e-12)
    if (order[0], order[-1]) == (cm.W_LOW, cm.W_MKT):
        assert total == pytest.approx(tr["t_real"] * (key[cm.W_MKT] - key[cm.W_LOW]), abs=1e-12)
    # масштаб ROE-эквивалента (М§4.5): IEA_0/BV_0 × (1 − τ_eff года last_period); цель передачи может быть нулём
    B, A = control["ctx"]["B"], control["ctx"]["A"]
    yl, ql = cm.c_per_parse(cm.c_bget(B, "meta.last_period"))
    scale = tr["iea0"] / A["BV"] * (1.0 - cm.c_traj_at(cm.c_bget(B, "tax.statutory"), yl, ql)
                                    - cm.c_bnum(B, "tax.effective_gap"))
    assert tr["roe_equiv"] == pytest.approx(cm.c_bnum(B, "nii.transmission.target") * scale, rel=1e-12, abs=1e-15)
    for k, v in tr["pairs"].items():
        assert tr["roe_equiv_pairs"][k] == pytest.approx(v * scale, rel=1e-12)


@pytest.mark.tact
def test_bad_keys_fail_loudly(inputs):
    """Ключи W1–W3 вне правил приложения A — громкий отказ, а не молчаливый расчёт."""
    book, facts = inputs

    def c_broken(change) -> dict:
        b = cm.copy.deepcopy(book)
        change(b)
        return b

    last_year = cm.c_per_parse(book["meta"]["last_period"])[0]
    shock_next = cm.c_per_parse(book["meta"]["anchor_period"])[0] + book["regimes"]["crisis"]["shock_year_offset"] + 1
    cases = {
        "доли «прочего» не в сумме 1": lambda b: b["other"].update(
            misc_quarter_shares={h: v * 2.0 for h, v in b["other"]["misc_quarter_shares"].items()}),
        "sigma0_from вне явного участка": lambda b: b["nii"].update(sigma0_from=last_year + 1),
        "sigma0_split больше единицы": lambda b: b["nii"].update(sigma0_split=1.5),
        "window_obs меньше единицы": lambda b: b["joint"]["regime_update"].update(window_obs=0),
        "phi_split больше единицы": lambda b: b["nii"].update(phi_split=1.5),
        "floor_share больше единицы": lambda b: b["joint"]["regime_update"].update(floor_share=1.5),
        "флаг phi у книг средств ФЛ разный": lambda b: b["nii"]["books"][cm.RETAIL_TERM].update(
            phi=not bool(b["nii"]["books"][cm.RETAIL_CURRENT].get("phi"))),
        "опора FVC — не режим книги": lambda b: b["credit"].update(fv_loans_ref="нет такого режима"),
        "год шока сдвинут, кризисные ключи — нет": lambda b: b["regimes"]["crisis"].update(
            shock_year_offset=b["regimes"]["crisis"]["shock_year_offset"] + 1),
        "разовый убыток вне года шока": lambda b: b["regimes"]["crisis"]["one_off_loss"].update(
            period=f"{shock_next}Q1"),
    }
    for name, change in cases.items():
        with pytest.raises(cm.ControlInputError):
            cm.c_control_context(c_broken(change), facts)
            pytest.fail(f"нет отказа: {name}")
    b = c_broken(lambda b: b["dividends"]["excess"].update(ramp_years=0))
    with pytest.raises(cm.ControlInputError):
        cm.c_control_run(b, facts)


# ============================================================================ решения W2 (LEAD-DECISIONS-3)


@pytest.mark.tact
def test_misc_of_the_anchor_year_is_level_times_share(control):
    """№ 2, В3 (М§0.3, §4.7): «прочее» каждого прогнозного квартала — уровень книги × доля квартала ×
    индекс цен мира, и в году якоря тоже: остатком года оно не закрывается, сумма года — выход.
    Непрофильный результат закрывает год якоря остатком (сумма книги − факт отчётных кварталов), поровну
    на оставшиеся кварталы."""
    ctx = control["ctx"]
    B, A = ctx["B"], ctx["A"]
    shares = ctx["misc_shares"]
    y0, qa = ctx["anchor"]
    assert ctx["periods"][0]["stub"], "якорь на конце года: правила года якоря не проверить"
    for c in control["cells"]:
        for p, r in zip(ctx["periods"], c["rows"]):
            level = cm.c_traj_mean(cm.c_bget(B, "other.misc_net_real"), p["year"], range(1, cm.QY + 1))
            assert math.isclose(sum(r["misc_q"]), r["misc"], rel_tol=1e-12, abs_tol=1e-9)
            for j, q in enumerate(p["quarters"]):
                assert r["misc_q"][j] == pytest.approx(level * shares[q] * r["idx_q"][j], rel=1e-12, abs=1e-12), \
                    (c["world"], p["year"], q)
        p0, r0 = ctx["periods"][0], c["rows"][0]
        book_nc = cm.c_traj_mean(cm.c_bget(B, "noncore.result_real"), y0, range(1, cm.QY + 1))
        fact_nc = sum(cm._c_fact_line(A, "noncore_net", y0, q) for q in range(1, qa + 1))
        per_quarter = [x / i for x, i in zip(r0["noncore_q"], r0["idx_q"])]
        assert per_quarter == pytest.approx([(book_nc - fact_nc) / p0["n"]] * p0["n"], rel=1e-12)
    # сумма года якоря — выход: факт отчётных кварталов + модель, а не сумма книги
    c = cm.c_cell_of(control, "H", "norm", "schedule")
    fact_misc = sum(cm._c_fact_line(A, "misc_net", y0, q) for q in range(1, qa + 1))
    level0 = cm.c_traj_mean(cm.c_bget(B, "other.misc_net_real"), y0, range(1, cm.QY + 1))
    rest_share = sum(shares[q] for q in ctx["periods"][0]["quarters"])
    if abs(fact_misc - level0 * (1.0 - rest_share)) > 1e-6:
        assert abs(fact_misc + c["rows"][0]["misc"] - level0) > 1e-6


@pytest.mark.tact
def test_fvc_is_the_regime_deviation_on_fair_value_loans(inputs, control):
    """№ 3, В4 (М§4.6): FVC = f × (CoR_corporate − CoR_ref) × кредиты по СС × d/365; опора — путь режима
    credit.fv_loans_ref через мост, без κ-добавки и отклонения A-P2u. В клетке режима-опоры мира без
    κ-добавки (мир-опора κ, без ключа опоры — мир N) без наблюдений FVC = 0; в спаде и кризисе — расход, в
    мягкой посадке — доход; κ-добавка мира действует и на кредиты по СС; строка линейна по fv_loans_factor
    (0 выключает её)."""
    book, facts = inputs
    ctx = control["ctx"]
    ref = ctx["fv_ref"]
    assert ref == cm.c_bget(ctx["B"], "credit.fv_loans_ref")
    scen = list(cm.c_bget(ctx["B"], "capital.reg_scenarios.ids"))
    calm = plain_world(ctx["B"])
    for s in scen:
        assert all(r["fvc"] == 0.0 for r in cm.c_cell_of(control, calm, ref, s)["rows"]), s
    if cm.c_bnum(ctx["B"], "credit.fv_loans_factor") <= 0.0:
        pytest.skip("книга держит строку FVC выключенной: " + NO_FAIR_VALUE)
    total = {r: sum(x["fvc"] for x in cm.c_cell_of(control, calm, r, scen[0])["rows"])
             for r in cm.c_bget(ctx["B"], "regimes.ids")}
    assert total["crisis"] > 0.0 and total["downturn"] > 0.0 and total["soft"] < 0.0, total
    shock = cm.c_cell_of(control, calm, "crisis", scen[0])["rows"][control["years"].index(control["shock_year"])]
    assert shock["fvc"] > 0.0 and min(shock["fvc_q"]) > 0.0
    # знак квартала — знак отклонения CoR клетки от опоры; в мире с κ-добавкой режим-опора несёт её
    for c in control["cells"]:
        for r in c["rows"]:
            for f, cor, cref in zip(r["fvc_q"], r["cor_q"], r["cor_ref_q"]):
                assert f * (cor - cref) >= 0.0 and (f == 0.0) == (cor == cref)
    gaps = [g for per in ctx["wv"]["H"] for g in per["kappa_gaps"]]
    h_ref = cm.c_cell_of(control, "H", ref, scen[0])["rows"]
    if min(gaps) >= 0.0 and max(gaps) > 0.0:
        assert sum(r["fvc"] for r in h_ref) > 0.0
    # линейность по множителю: кредиты и CoR от него не зависят
    b2 = cm.copy.deepcopy(book)
    b2["credit"]["fv_loans_factor"] = 0.5 * cm.c_bnum(book, "credit.fv_loans_factor")
    half = cm.c_cell_annual(cm.c_control_context(b2, facts), calm, "crisis", scen[0])["rows"]
    full = cm.c_cell_of(control, calm, "crisis", scen[0])["rows"]
    assert [r["fvc"] for r in half] == pytest.approx([0.5 * r["fvc"] for r in full], rel=1e-12, abs=1e-12)
    b0 = cm.copy.deepcopy(book)
    b0["credit"]["fv_loans_factor"] = 0.0
    off = cm.c_cell_annual(cm.c_control_context(b0, facts), calm, "crisis", scen[0])["rows"]
    assert all(r["fvc"] == 0.0 for r in off)
    assert off[0]["pbt"] > full[0]["pbt"]                 # расход FVC уменьшил прибыль клетки кризиса


def terminal_rates(forms: dict, last: dict, sec: float) -> tuple[float, float, float, float]:
    """Ставки терминала в формах ключей книги (Р4-16, cm.c_forms): (смесь балансирующих активов, ставка опта, ставка
    ликвидности, ставка бумаг) — на конце Q (lagged) или цели года L (stationary, К4: ставка при ρ = 1)."""
    if forms["rates"] == cm.RATES_STATIONARY:
        tg = last["stationary"]["targets"]
        y_sec, y_liq, wh = tg[cm.SECURITIES], tg[cm.LIQUIDITY], tg[cm.WHOLESALE]
    else:
        y_sec, y_liq, wh = last["y_sec_end"], last["y_liq_end"], last["c_wh_end"]
    return sec * y_sec + (1.0 - sec) * y_liq, wh, y_liq, y_sec


def terminal_year(forms: dict, c: dict, last: dict) -> tuple[float, float]:
    """База терминала в формах ключей (Р4-16): (PBT^T_L, ψ). PBT^T_L = PBT_L + ΔNII*_L (К4), а при годе терминала
    «средний год» (К-Т2а) — ещё поправка (ν_L − 1)(дневные строки года L + ΔNII*_L), ν_L = 365,2425 / дни года L;
    ψ = 365,2425 / 365 — множитель годовых ставок (Y_X). Без ключей — PBT_L и 1."""
    d_star = c["terminal_stationary"]["d_nii_l"] if forms["rates"] == cm.RATES_STATIONARY else 0.0
    if forms["year_basis"] != cm.YEAR_MEAN:
        return last["pbt"] + d_star, 1.0
    nu = cm.MEAN_YEAR / sum(last["days_q"])
    adj = (nu - 1.0) * (last["nii"] - last["llp"] - last["fvc"] + d_star)
    assert c["terminal_year"]["adj"] == pytest.approx(adj, rel=1e-12, abs=1e-12)
    return last["pbt"] + d_star + adj, cm.MEAN_YEAR / cm.DAYS_BASE


@pytest.mark.tact
def test_terminal_excess_income_at_the_marginal_rate(inputs, control):
    """№ 4, остаток № 38 (М§7): доход на избыток капитала вычитается по маржинальной ставке балансирующих
    статей. Избыток — по смеси доходностей бумаг и ликвидности на конце Q в их долях в LA, пока минимум
    ликвидности не свяжет, дальше — по ставке опта; порог связывания — H* = HLA / (1 − m), не сам запас
    HLA (изъятый капитал уменьшает и активы, от которых считается минимум). Недостаток капитала —
    зеркально: сначала гасится добор опта WT, остальное — по смеси. При доле бумаг 0 смесь — ставка
    ликвидности. Формы — по ключам книги (Р4-16, cm.c_forms): ставки — конца Q или цели года L (К4), добор опта —
    сверх s_eff × средства (К3), PBT_L — с ΔNII*_L (К4) и поправкой среднего года, Y_X — × ψ (К-Т2а)."""
    book, facts = inputs
    ctx = control["ctx"]
    B = ctx["B"]
    forms = cm.c_forms(B)
    sec = cm.c_bnum(B, "volumes.securities_share_of_liquid")
    m = cm.c_bnum(B, "volumes.liquid_min_share")
    nci_real = cm.c_nci_real(B) is not None         # Р11-3 (проход 9): НДУ в рублях — доля не читается, терминал − NCI_L
    nci = 0.0 if nci_real else cm.c_bnum(B, "pnl.nci_share")
    free = 0
    for c in control["cells"]:
        last = c["rows"][-1]
        mix, wh, _, _ = terminal_rates(forms, last, sec)
        pbt_t, psi = terminal_year(forms, c, last)
        assert c["y_bal"] == pytest.approx(mix, rel=1e-12)
        assert c["hla"] == pytest.approx(max(0.0, last["securities"] + last["liquidity"] - m * last["assets"]), abs=1e-6)
        assert c["h_star"] == pytest.approx(c["hla"] / (1.0 - m), rel=1e-12)
        # опт по нужде — сверх s_eff × средства клиентов (Р11-2: при volumes.funds_scope: clients — без книг К6)
        assert c["wt"] == pytest.approx(last["wholesale"] - forms["s_eff"] * last.get("clients", last["funds"]), abs=1e-6)
        if nci_real:
            assert c["ni_t1"] == pytest.approx((pbt_t * (1.0 + c["g_t"]) - c["y_x"]) * (1.0 - last["tau_eff"])
                                               - last["nci"] * (1.0 + c["g_t"]), rel=1e-12)
        else:
            assert c["ni_t1"] == pytest.approx((pbt_t * (1.0 + c["g_t"]) - c["y_x"]) * (1.0 - last["tau_eff"])
                                               * (1.0 - nci), rel=1e-12)
        if 0.0 < c["x_t"] <= c["h_star"]:
            assert c["y_x"] == pytest.approx(psi * mix * c["x_t"], rel=1e-12)
            free += 1
        elif c["x_t"] > 0.0:
            assert c["y_x"] == pytest.approx(psi * (mix * c["h_star"] + wh * (c["x_t"] - c["h_star"])), rel=1e-12)
        else:
            repaid = min(-c["x_t"], c["wt"])
            assert c["y_x"] == pytest.approx(-psi * (wh * repaid + mix * (-c["x_t"] - repaid)), rel=1e-12)
    assert free, "нет клетки с избытком в пределах порога связывания минимума ликвидности"
    # связанный минимум ликвидности: запаса нет — весь избыток по ставке опта
    cell = {"world": "H", "regime": "norm", "scenario": modal_scenario(control)}
    base = cm.c_cell_of(control, *cell.values())
    assert base["x_t"] > 0.0
    _, wh, _, _ = terminal_rates(forms, base["rows"][-1], sec)
    psi = terminal_year(forms, base, base["rows"][-1])[1]
    rows = [dict(r) for r in base["rows"]]
    la_min = m * rows[-1]["assets"]
    rows[-1]["securities"], rows[-1]["liquidity"] = sec * la_min, (1.0 - sec) * la_min
    bound = cm._c_value_cell(ctx, cell, rows, base["decisions"])
    assert bound["hla"] == pytest.approx(0.0, abs=1e-6)
    assert bound["y_x"] == pytest.approx(psi * wh * bound["x_t"], rel=1e-9)
    # частично связанный: порог H* = запас / (1 − m) меньше избытка — смесь до порога, опт на остаток;
    # избыток между запасом и порогом идёт ещё по смеси (порог — не сам запас)
    part = [dict(r) for r in base["rows"]]
    room = 0.5 * base["x_t"]
    part[-1]["securities"], part[-1]["liquidity"] = sec * (la_min + room), (1.0 - sec) * (la_min + room)
    mixed = cm._c_value_cell(ctx, cell, part, base["decisions"])
    edge = room / (1.0 - m)
    assert mixed["hla"] == pytest.approx(room, rel=1e-9) and room < edge < mixed["x_t"]
    assert mixed["y_x"] == pytest.approx(psi * (base["y_bal"] * edge + wh * (mixed["x_t"] - edge)), rel=1e-9)
    # недостаток капитала: добавленный капитал сначала гасит добор опта, остальное — по смеси
    short = [dict(r) for r in base["rows"]]
    gap = 2.0 * base["x_t"] / cm.c_bnum(B, "valuation.terminal.excess_capital_multiple") / short[-1]["rwa"]
    short[-1]["n20"], short[-1]["n11_star"] = short[-1]["n20"] - gap, short[-1]["n11_star"] - gap
    for extra in (0.0, 0.25 * base["x_t"], 3.0 * base["x_t"]):
        short[-1]["wholesale_extra"] = extra
        lack = cm._c_value_cell(ctx, cell, short, base["decisions"])
        assert lack["x_t"] == pytest.approx(-base["x_t"], rel=1e-9) and lack["wt"] == extra
        repaid = min(base["x_t"], extra)
        want = -psi * (wh * repaid + base["y_bal"] * (base["x_t"] - repaid))
        assert lack["y_x"] == pytest.approx(want, rel=1e-9)
    # доля бумаг 0: ставка смеси — ставка ликвидности
    b0 = cm.copy.deepcopy(book)
    b0["volumes"]["securities_share_of_liquid"] = 0.0
    liq = cm.c_cell_annual(cm.c_control_context(b0, facts), "H", "norm", modal_scenario(control))
    y_liq = terminal_rates(forms, liq["rows"][-1], 0.0)[2]
    assert liq["y_bal"] == y_liq
    if 0.0 < liq["x_t"] <= liq["h_star"]:
        assert liq["y_x"] == pytest.approx(psi * y_liq * liq["x_t"], rel=1e-12)
    # вычет по смеси больше вычета по одной ставке ликвидности, пока бумаги доходнее ликвидности
    _, _, y_liq, y_sec = terminal_rates(forms, base["rows"][-1], sec)
    if y_sec > y_liq and base["x_t"] <= base["h_star"]:
        assert base["y_x"] > psi * y_liq * base["x_t"]


@pytest.mark.tact
@annual_only
def test_price_keeps_declared_dividend_out_of_the_discount(inputs, control):
    """№ 25 (М§8.2): цена = [(V0 − D_pend)(1 − g) + D_pend + B] × 1000/N_out; при V0 − D_pend ≤ 0 дисконта
    нет. D_pend — объявленные (declared | paid) дивиденды реестра, которые клетки ещё не вычли из BV;
    запись `recommended` — только плашка: ни в цену, ни в клетки она не входит."""
    n_out = control["ctx"]["A"]["N_out"]
    g = 0.25                                                       # входы формулы, не допущения книги
    assert cm.c_price_of(100.0, 7.0, g, n_out, 20.0) == pytest.approx((80.0 * (1.0 - g) + 20.0 + 7.0) * 1000.0 / n_out)
    assert cm.c_price_of(100.0, 7.0, g, n_out) == pytest.approx((100.0 * (1.0 - g) + 7.0) * 1000.0 / n_out)
    assert cm.c_price_of(10.0, 7.0, g, n_out, 20.0) == pytest.approx((10.0 + 7.0) * 1000.0 / n_out)
    assert cm.c_price_of(-5.0, 0.0, g, n_out) == pytest.approx(-5.0 * 1000.0 / n_out)
    book, facts = inputs
    y0, e_qa = _agm_end(book)
    dps = _history_dps(facts)
    v = e_qa - dt.timedelta(days=10)
    amount = dps * n_out / 1000.0
    seen = {}
    for status in ("declared", "paid", "recommended"):
        f2 = cm.copy.deepcopy(facts)
        f2["dividends"]["register_seed"] = [_declared(y0, dps, e_qa, status)]
        ctx = cm.c_control_context(book, f2, valuation_date=v)
        seen[status] = (ctx["pending_amount"], ctx["bridge_amount"], cm._c_register_dps(ctx, y0))
    assert seen["declared"] == pytest.approx((amount, 0.0, dps), rel=1e-12)
    assert seen["paid"] == pytest.approx((amount, 0.0, dps), rel=1e-12)
    assert seen["recommended"] == (0.0, 0.0, None)
    assert control["pending_amount"] == sum(
        a for a, deduct, _ in cm._c_register_amounts(control["ctx"]) if control["ctx"]["clock"]["v"] < deduct)


def _obs(period: str, cor, nim) -> dict:
    return {"period": period, "cor": cor, "nim": nim, "se_cor": 0.0, "se_nim": 0.0, "basis": "mgmt"}


def _next_period(per: str) -> str:
    y, q = cm.c_per_parse(per)
    return f"{y + 1}Q1" if q == cm.QY else f"{y}Q{q + 1}"


@pytest.mark.tact
def test_regime_filter_reads_only_the_window(inputs):
    """В2 (М§12): фильтр стартует с базовых вероятностей книги и пустого состояния и проходит только
    последние window_obs наблюдений — более ранние на результат не влияют; без наблюдений
    апостериорные — базовые."""
    book, facts = inputs
    q1 = book["meta"]["first_period"]
    q2 = _next_period(q1)
    first, second = _obs(q1, 0.022, 0.058), _obs(q2, 0.011, 0.061)       # наблюдения — входы теста

    def c_ctx(observations, window):
        b = cm.copy.deepcopy(book)
        b["joint"]["regime_update"].update(observations=observations, window_obs=window)
        return cm.c_control_context(b, facts)

    prior = {r: float(v) for r, v in book["joint"]["regime_prob"].items()}
    assert c_ctx([], 1)["posterior"] == prior
    both_w1, only_second = c_ctx([first, second], 1), c_ctx([second], 1)
    assert both_w1["posterior"] == only_second["posterior"]
    assert both_w1["dev"] == only_second["dev"]
    both_w2 = c_ctx([second, first], 2)                                  # порядок записи не важен — по периодам
    assert both_w2["posterior"] != only_second["posterior"]
    assert both_w2["posterior"] == c_ctx([first, second], 4)["posterior"]
    assert both_w2["dev"]["norm"]["cor"]["q"] == cm.c_per_parse(q2)[1]   # отклонение — от последнего наблюдения
    cap = cm.c_bnum(book, "joint.regime_update.max_shift_pp")
    one = c_ctx([first], 4)["posterior"]
    assert max(abs(one[r] - prior[r]) for r in prior) <= cap + 1e-12     # предел сдвига — на квартал


@pytest.mark.tact
def test_observation_of_a_closed_quarter_uses_frozen_expectations(inputs):
    """В2 (М§12): наблюдение квартала не позже якоря несёт замороженные ожидания режимов mu_cor, mu_nim в
    базисе записи; фильтр берёт μ из записи (клетки этот квартал не считают), отклонение в клетке
    затухает от квартала наблюдения: δ_q = ρ^(q − q_obs) × (obs − μ) только в прогнозных кварталах.
    Запись без μ наблюдённой величины — отказ."""
    book, facts = inputs
    anchor = book["meta"]["anchor_period"]
    regimes = list(book["regimes"]["ids"])
    mu_cor = {r: 0.010 + 0.004 * i for i, r in enumerate(regimes)}       # входы теста
    obs_cor = 0.0135
    rec = {**_obs(anchor, obs_cor, None), "mu_cor": mu_cor}
    b = cm.copy.deepcopy(book)
    b["joint"]["regime_update"].update(observations=[rec], floor_share=0.0)   # пол — отдельным тестом
    ctx = cm.c_control_context(b, facts)
    ru = b["joint"]["regime_update"]
    sig, rho, cap = ru["observables"]["cor"]["sigma_pp"], ru["observables"]["cor"]["rho_q"], ru["max_shift_pp"]
    prior = {r: float(v) for r, v in book["joint"]["regime_prob"].items()}
    like = {r: math.exp(-0.5 * (obs_cor - mu_cor[r]) ** 2 / sig ** 2) for r in regimes}
    tot = sum(prior[r] * like[r] for r in regimes)
    raw = {r: prior[r] * like[r] / tot for r in regimes}
    clip = {r: prior[r] + max(-cap, min(cap, raw[r] - prior[r])) for r in regimes}
    z = sum(clip.values())
    clip = {r: v / z for r, v in clip.items()}
    worst = max(abs(clip[r] - prior[r]) for r in regimes)
    if worst > cap + 1e-12:
        clip = {r: prior[r] + cap / worst * (clip[r] - prior[r]) for r in regimes}
    assert ctx["posterior"] == pytest.approx(clip, abs=1e-12)
    ya, qa = cm.c_per_parse(anchor)
    fy, fq = cm.c_per_parse(book["meta"]["first_period"])
    A = ctx["A"]
    for r in regimes:
        dv = ctx["dev"][r]["cor"]
        assert (dv["y"], dv["q"]) == (ya, qa) and "nim" not in ctx["dev"][r]
        if A["bridge"]["cor"][0] == "additive":                       # отклонение не зависит от b_cor
            assert dv["m"] == pytest.approx(obs_cor - mu_cor[r], abs=1e-15)
        assert cm._c_dev_at(dv, fy, fq) == pytest.approx(rho * dv["m"], rel=1e-12)
        assert cm._c_dev_at(dv, fy + 1, fq) == pytest.approx(rho ** (cm.QY + 1) * dv["m"], rel=1e-12)
    # отклонение входит в CoR первого прогнозного квартала клетки
    r0 = regimes[0]
    with_obs = cm.c_cell_annual(ctx, cm.W_LOW, r0, "schedule")["rows"][0]["cor_q"][0]
    without = cm.c_cell_annual(cm.c_control_context(book, facts), cm.W_LOW, r0, "schedule")["rows"][0]["cor_q"][0]
    assert with_obs - without == pytest.approx(rho * ctx["dev"][r0]["cor"]["m"], rel=1e-9)
    bad = cm.copy.deepcopy(book)
    bad["joint"]["regime_update"]["observations"] = [_obs(anchor, obs_cor, None)]
    with pytest.raises(cm.ControlInputError):
        cm.c_control_context(bad, facts)
    partial = cm.copy.deepcopy(book)
    partial["joint"]["regime_update"]["observations"] = [{**_obs(anchor, obs_cor, 0.06), "mu_cor": mu_cor}]
    with pytest.raises(cm.ControlInputError):                           # ЧПМ наблюдена, mu_nim нет
        cm.c_control_context(partial, facts)


# вне такта сервера: один из самых долгих тестов набора — набор такта держит цель времени (ops/budgets.json)
# Известное расхождение (решение ведущего 29.10.2026: числа книги не задевает, разбор ноябрьской версией книги; долг —
# справочник панели, раздел долгов). strict: починка — снять метку.
@pytest.mark.xfail(strict=True, reason=(
    "известное расхождение: у книги Совкомбанка (рост урезан капиталом) остаток сдвига V0 аналитического слоя сверх "
    "перевзвешивания режимов — 25,5 % перевзвешивания (−0,174 против −0,234 млрд ₽) при допуске LEARNING_REST_RULE 0,20, "
    "заданном замером книги панели (до 0,16); допуск — решение ведущего, числа книги не задевает — разбор ноябрьской "
    "версией книги"))
def test_fact_equal_to_expectation_is_learning_on_four_regimes(inputs, control):
    """В2, № 21 (М§12, §18): при смеси режимов наблюдение, равное ожиданию квартала (среднему смеси),
    перевзвешивает режимы — это обучение, а не ноль: сдвиг V0 слоя равен Σ_r ΔP(r) × V_r (V_r — оценка
    при P(r) = 1 на том же объекте клетки, что V0 слоя: оценка в цене v_price), вклад отклонений клеток мал против
    него."""
    book, facts = inputs
    if control["ctx"]["mu"]:
        pytest.skip("в книге уже есть наблюдения: базовое ожидание квартала — не априорное")
    per = book["meta"]["first_period"]
    y, q = cm.c_per_parse(per)
    ctx = control["ctx"]
    A, B = ctx["A"], ctx["B"]
    regimes = list(B["regimes"]["ids"])
    prior = control["posterior"]
    mu = cm.c_expectations_ctl(ctx, [(y, q)])
    e_cor = sum(prior[r] * mu[("cor", r, y, q)] for r in regimes)
    if max(mu[("cor", r, y, q)] for r in regimes) == min(mu[("cor", r, y, q)] for r in regimes):
        pytest.skip("ожидания CoR режимов равны — обучения нет")
    b2 = cm.copy.deepcopy(book)
    b2["joint"]["regime_update"]["observations"] = [_obs(per, cm.c_to_mgmt(A, "cor", e_cor), None)]
    obs = cm.c_control_run(b2, facts)
    post = obs["posterior"]
    assert max(abs(post[r] - prior[r]) for r in regimes) > 1e-4          # вероятности перевзвешены
    assert sum(prior[r] * obs["ctx"]["dev"][r]["cor"]["m"] for r in regimes) == pytest.approx(0.0, abs=1e-12)
    weights = cm.c_layer_weights(B)
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")
    for name in cm.LAYERS:
        # V_r — оценка слоя при P(r) = 1 на том же объекте клетки, что V0 слоя: оценка в цене v_price (с выкупом — V̂,
        # без выкупа — V_RI бит в бит)
        v_r = {r: sum(weights[name].get(c["world"], 0.0) * float(prs[r][c["scenario"]]) * c["v_price"]
                      for c in control["cells"] if c["regime"] == r) for r in regimes}
        reweight = sum((post[r] - prior[r]) * v_r[r] for r in regimes)
        shift = obs["layers"][name]["v0"] - control["layers"][name]["v0"]
        assert abs(reweight) > 0.0
        # вклад отклонений клеток мал против перевзвешивания; при росте, ограниченном капиталом, клетки
        # отвечают на отклонение CoR нелинейно, и остаток больше, чем у годовой ветви: на книге панели он
        # одного знака во всех слоях и у ядра тот же (0,6 млрд ₽ при перевзвешивании 3,8 млрд ₽ и
        # капитале слоя около 800 млрд ₽) — режимы с меньшим портфелем отвечают на отклонение слабее
        assert abs(shift - reweight) <= (LEARNING_REST_RULE if control["growth_rule"] else LEARNING_REST) * abs(reweight), (
            name, shift, reweight)


@pytest.mark.tact
def test_sigma0_split_divides_the_shift(inputs, control):
    """В8 (М§4.5): сдвиг стационарного ЧПМ Δ0 делят активы и пассивы с lt_shift — σ0_A × Σa = split × Δ0,
    σ0_L × Σl_H = (1 − split) × Δ0, стационар мира уровня = цель при любом split; split = 1 — весь сдвиг на активах
    (σ0_L = 0, прежнее решение); φ от split не зависит, пока lt_shift у обеих книг средств ФЛ одинаков;
    эффективный LT-спред кредитной книги — s^LT + σ0_A × [lt_shift] − φ_A × [Φ_A] × (ref_W − ref_H)."""
    book, facts = inputs
    ctx = control["ctx"]
    tr, B, A = ctx["tr"], ctx["B"], ctx["A"]
    assert tr["split"] == cm.c_bnum(B, "nii.sigma0_split")
    assert tr["sigma0"] * tr["w_assets"] == pytest.approx(tr["split"] * tr["delta0"], abs=1e-15)
    assert tr["sigma0_liab"] * tr["w_liab"] == pytest.approx((1.0 - tr["split"]) * tr["delta0"], abs=1e-15)
    books = B["nii"]["books"]
    same_retail = bool(books[cm.RETAIL_CURRENT].get("lt_shift")) == bool(books[cm.RETAIL_TERM].get("lt_shift"))
    ref_w = B["nii"]["transmission"]["reference_world"]
    for split in (0.0, 0.5, 1.0):
        b2 = cm.copy.deepcopy(B)
        b2["nii"]["sigma0_split"] = split
        t2 = cm.c_transmission_ctl(b2, A)
        assert t2["nss_level"] == pytest.approx(tr["target_eng"], abs=1e-12), split
        assert t2["t_real"] == pytest.approx(cm.c_bnum(B, "nii.transmission.target"), abs=1e-12), split
        if t2["level_world"] == ref_w:                              # ключ цели — уровень мира-опоры: Δ0 от доли не зависит
            assert t2["delta0"] == tr["delta0"]
        if same_retail:
            assert t2["phi"] == pytest.approx(tr["phi"], abs=1e-12), split
        if split == 1.0:
            assert t2["sigma0_liab"] == 0.0 and t2["sigma0"] == pytest.approx(t2["delta0"] / tr["w_assets"], rel=1e-12)
        if split == 0.0:
            assert t2["sigma0"] == 0.0 and t2["sigma0_liab"] == pytest.approx(t2["delta0"] / tr["w_liab"], rel=1e-12)
    yl, ql = cm.c_per_parse(B["meta"]["last_period"])
    credit = [b for b, sp in books.items() if sp.get("sector")]
    assert sorted(tr["lt_spread"]) == sorted(credit)
    shares = cm.c_phi_shares(B)                     # доли сжатия книг (Р11-1, проход 9); без ключа — пусто
    for b in credit:
        sp = books[b]
        s_lt = cm.c_traj_at(sp["spread"], yl, ql) + (tr["sigma0"] if sp.get("lt_shift") else 0.0)
        assert tr["lt_spread"][b][ref_w] == pytest.approx(s_lt, abs=1e-15)          # в мире H сжатия нет
        for w in ctx["worlds"]:
            d_ref = (cm.c_world_quarter(B, w, cm.c_ref_field(sp["ref"]), yl, ql)
                     - cm.c_world_quarter(B, ref_w, cm.c_ref_field(sp["ref"]), yl, ql))
            want = s_lt - (tr["phi_assets"] * d_ref if sp.get("phi") else 0.0) - shares.get(b, 0.0) * d_ref
            assert tr["lt_spread"][b][w] == pytest.approx(want, abs=1e-15), (b, w)
    # отказ: остаток сдвига некому нести
    b3 = cm.copy.deepcopy(B)
    for sp in b3["nii"]["books"].values():
        if sp["side"] != cm.LOANS_SIDE:
            sp["lt_shift"] = False
    if tr["split"] < 1.0:
        with pytest.raises(cm.ControlInputError):
            cm.c_transmission_ctl(b3, A)
    b3["nii"]["sigma0_split"] = 1.0
    assert cm.c_transmission_ctl(b3, A)["sigma0_liab"] == 0.0


# ============================================================================ решения W3 (LEAD-DECISIONS-4)


def _shifted(traj, x: float):
    """Траектория, сдвинутая на x во всех ключах времени и в LT (LT_from — год, не сдвигается)."""
    if isinstance(traj, dict):
        return {k: (v if str(k) == "LT_from" else v + x) for k, v in traj.items()}
    return traj + x


def _with_split(book: dict, split: float) -> dict:
    b = cm.copy.deepcopy(book)
    b["nii"]["phi_split"] = split
    return b


@pytest.mark.tact
def test_phi_split_divides_the_compression(inputs, control):
    """В12, № 74 (М§4.4–§4.5): сжатие φ решается как раньше, доля nii.phi_split = p делит его — φ_A = p × φ
    снимается со спредов кредитных книг Φ_A, остаток — добавка φ_L × X_W к стоимости пассивов Φ_L, φ_L =
    (1 − p) × φ × A / L. Объём сжатия мира один при любой доле: φ, σ0, Nss, T_real, T(W) и пары от p не
    зависят, добавка пассивов в стационаре равна остатку сжатия (1 − p) × φ × C_W. В пути — только
    скаляры и доли ω_b якоря: в мире H сжатия нет, ставка пассива сдвинута на φ_L × X_W,q, от остатка
    кредитов добавка не зависит. При p = 1 расчёт — бит в бит без раскладки."""
    book, facts = inputs
    ctx = control["ctx"]
    tr, B, A = ctx["tr"], ctx["B"], ctx["A"]
    books = B["nii"]["books"]
    yl, ql = cm.c_per_parse(B["meta"]["last_period"])
    ref_w = B["nii"]["transmission"]["reference_world"]
    phi_assets = [b for b, sp in books.items() if sp["side"] == cm.LOANS_SIDE and sp.get("phi")]
    phi_liabs = [b for b, sp in books.items() if sp["side"] != cm.LOANS_SIDE and sp.get("phi")]
    p = cm.c_bnum(B, "nii.phi_split")
    assert tr["phi_split"] == p and set(tr["phi_weights"]) == set(phi_assets)
    assert sum(tr["phi_weights"].values()) == pytest.approx(1.0, abs=1e-15)
    assert tr["phi_a_sum"] == pytest.approx(sum(A["E0"][b] for b in phi_assets) / tr["iea0"], rel=1e-15)
    assert tr["phi_l_sum"] == pytest.approx(sum(A["E0"][b] for b in phi_liabs) / tr["iea0"], rel=1e-15)

    def c_ref_gap(w, b):
        f = cm.c_ref_field(books[b]["ref"])
        return cm.c_world_quarter(B, w, f, yl, ql) - cm.c_world_quarter(B, ref_w, f, yl, ql)

    volume = {w: sum(A["E0"][b] / tr["iea0"] * c_ref_gap(w, b) for b in phi_assets) for w in ctx["worlds"]}   # C_W
    for split in (0.0, 0.3, 1.0):
        t2 = cm.c_transmission_ctl(_with_split(B, split), A)
        for k in ("phi", "sigma0", "sigma0_liab", "t_real", "t_local", "pairs", "nss"):
            assert t2[k] == tr[k], (split, k)                       # от доли не зависят — точно
        assert t2["phi_assets"] == split * tr["phi"]
        for w in ctx["worlds"]:
            assert t2["nss_books"][w] == pytest.approx(tr["nss"][w], abs=1e-14), (split, w)
            assert t2["phi_l_sum"] * t2["phi_liab"] * t2["x_lt"][w] == pytest.approx(
                (1.0 - split) * tr["phi"] * volume[w], abs=1e-15), (split, w)
        if split == 1.0:
            assert t2["phi_liab"] == 0.0 and t2["phi_assets"] == tr["phi"]
        if split == 0.0:                                            # спреды кредитных книг одинаковы во всех мирах
            for b, per_world in t2["lt_spread"].items():            # (за вычетом доли сжатия книги, Р11-1)
                own = {w: v - (t2.get("share_lt") or {}).get(b, {}).get(w, 0.0) for w, v in per_world.items()}
                assert max(own.values()) - min(own.values()) <= 1e-15, b
    # путь клетки: ставки книг на конец первого периода при p = 0 против p = 1
    high = max(ctx["worlds"], key=lambda w: abs(tr["x_lt"][w]))
    ctx0, ctx1 = (cm.c_control_context(_with_split(book, s), facts) for s in (0.0, 1.0))
    cell = (high, "norm", "schedule")
    c0, c1 = cm.c_cell_annual(ctx0, *cell), cm.c_cell_annual(ctx1, *cell)
    p0 = ctx0["periods"][0]
    wd, wh = ctx0["wv"][high][0], ctx0["wv"][ref_w][0]
    r0, r1 = c0["rows"][0], c1["rows"][0]
    gaps = {b: [wd[cm.c_ref_field(books[b]["ref"])][j] - wh[cm.c_ref_field(books[b]["ref"])][j]
                for j in range(p0["n"])] for b in phi_assets}
    for j in range(p0["n"]):
        assert r0["x_q"][j] == pytest.approx(sum(ctx0["tr"]["phi_weights"][b] * gaps[b][j] for b in phi_assets),
                                             abs=1e-15)
    x_mean = sum(r0["x_q"]) / p0["n"]
    assert x_mean != 0.0
    for b, sp in books.items():
        k_end = cm._c_partial(float(sp["rho"]), p0["n"])[0]
        d = r0["rates_end"][b] - r1["rates_end"][b]
        if b in phi_liabs:                                          # вклады дорожают на φ_L × X_W,q
            assert d == pytest.approx(k_end * ctx0["tr"]["phi_liab"] * x_mean, abs=1e-14), b
        elif b in phi_assets:                                       # спред кредита больше не сжат
            assert d == pytest.approx(k_end * tr["phi"] * sum(gaps[b]) / p0["n"], abs=1e-14), b
        else:
            assert d == 0.0, b
    # в мире H сжатия нет при любой доле
    assert (cm.c_cell_annual(ctx0, ref_w, "norm", "schedule")["v_ri"]
            == cm.c_cell_annual(ctx1, ref_w, "norm", "schedule")["v_ri"])
    # предельный кредит добавку не несёт: остановка кредита в кризисе не меняет X_W,q и ставки пассивов
    crisis = cm.c_cell_annual(ctx0, high, cm.R_CRISIS, "schedule")
    for ra, rb in zip(c0["rows"], crisis["rows"]):
        assert ra["x_q"] == rb["x_q"] and all(ra["rates_end"][b] == rb["rates_end"][b] for b in phi_liabs)
    assert any(ra["loans"] != rb["loans"] for ra, rb in zip(c0["rows"], crisis["rows"]))
    # p = 1 — бит в бит с расчётом без раскладки (флаги phi у пассивов сняты)
    plain = _with_split(book, 1.0)
    for b in phi_liabs:
        plain["nii"]["books"][b]["phi"] = False
    assert cm.c_cell_annual(cm.c_control_context(plain, facts), *cell)["v_ri"] == c1["v_ri"]
    # отказы: доля вне [0; 1]; остаток сжатия некому нести; флаг phi у книг средств ФЛ разный
    with pytest.raises(cm.ControlInputError):
        cm.c_transmission_ctl(_with_split(B, 1.5), A)
    if p < 1.0:
        orphan = cm.copy.deepcopy(B)
        for b in phi_liabs:
            orphan["nii"]["books"][b]["phi"] = False
        with pytest.raises(cm.ControlInputError):
            cm.c_transmission_ctl(orphan, A)
    uneven = cm.copy.deepcopy(B)
    uneven["nii"]["books"][cm.RETAIL_TERM]["phi"] = not bool(books[cm.RETAIL_CURRENT].get("phi"))
    with pytest.raises(cm.ControlInputError):
        cm.c_transmission_ctl(uneven, A)


@pytest.mark.tact
def test_loan_margin_of_the_worlds(control):
    """В12, № 74 (М§4.5): кредитная маржа стационара мира — доходность кредитного портфеля (опора + эффективный
    LT-спред, веса якоря) минус CoR режима norm с κ-добавкой мира (к миру-опоре книги — с любым знаком, без
    ключа опоры — только вверх от мира N) минус смесь балансирующих активов. При центрах книги она
    неотрицательна в каждом мире; в мире H от доли сжатия не зависит; перенос сжатия с кредитных книг на
    пассивы поднимает её на φ × C_W / Σ a_кредиты."""
    ctx = control["ctx"]
    tr, B, A = ctx["tr"], ctx["B"], ctx["A"]
    books = B["nii"]["books"]
    yl, ql = cm.c_per_parse(B["meta"]["last_period"])
    ref_w = B["nii"]["transmission"]["reference_world"]
    credit = [b for b, sp in books.items() if sp.get("sector")]
    loans0 = sum(A["E0"][b] for b in credit)
    sec = cm.c_bnum(B, "volumes.securities_share_of_liquid")
    kap = cm.c_bnum(B, "credit.kappa")

    def c_lt(w, b):
        return cm.c_world_quarter(B, w, cm.c_ref_field(books[b]["ref"]), yl, ql)

    def c_rr(w):
        return cm.c_world_quarter(B, w, "real_key", yl, ql)

    cor_norm = cm.c_traj_at(B["regimes"][cm.R_NORM]["cor"], yl, ql)
    if B["regimes"]["cor_basis"] == "mgmt":
        cor_norm = cm.c_to_engine(A, "cor", cor_norm)
    kappa_ref = B["credit"].get(KAPPA_KEY)
    shares = cm.c_phi_shares(B)                     # доли сжатия балансирующих книг (Р11-1, проход 9); без ключа — пусто

    def c_bal(w, b):
        return c_lt(w, b) + cm.c_traj_at(books[b]["spread"], yl, ql) - shares.get(b, 0.0) * (c_lt(w, b) - c_lt(ref_w, b))

    for w in ctx["worlds"]:
        m = tr["loan_margin"][w]
        assert m >= 0.0, (w, m)
        yld = sum(A["E0"][b] * (c_lt(w, b) + tr["lt_spread"][b][w]) for b in credit) / loans0
        bal = sec * c_bal(w, cm.SECURITIES) + (1.0 - sec) * c_bal(w, cm.LIQUIDITY)
        gap = max(0.0, c_rr(w) - c_rr(cm.W_LOW)) if kappa_ref is None else c_rr(w) - c_rr(kappa_ref)
        risk = cor_norm + kap * gap
        assert m == pytest.approx(yld - risk - bal, abs=1e-15), w
    on_loans = cm.c_transmission_ctl(_with_split(B, 1.0), A)["loan_margin"]
    on_funds = cm.c_transmission_ctl(_with_split(B, 0.0), A)["loan_margin"]
    assert on_loans[ref_w] == on_funds[ref_w] == tr["loan_margin"][ref_w]
    for w in ctx["worlds"]:
        volume = sum(A["E0"][b] * (c_lt(w, b) - c_lt(ref_w, b)) for b in credit if books[b].get("phi")) / loans0
        assert on_funds[w] - on_loans[w] == pytest.approx(tr["phi"] * volume, abs=1e-15), w
    if tr["phi"] > 0.0:                    # сжатие на кредитных книгах съедает маржу там, где ставки выше мира H
        for w in ctx["worlds"]:
            if tr["x_lt"][w] > 0.0:
                assert on_loans[w] < on_funds[w]


def _world_price(res: dict, world: str) -> float:
    """Цена мира (М§8.2): оценка при P(W) = 1 с вероятностями режимов и сценариев прогона — формулой цены на
    делителе N_div (М§8.4): всё «на акцию» делится на одно число."""
    B, ctx = res["ctx"]["B"], res["ctx"]
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")
    # оценка клетки в цене — тот же объект, что V0 слоя: с выкупом (М3) — V̂, без него — V_RI бит в бит
    v0 = sum(res["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]]) * c["v_price"]
             for c in res["cells"] if c["world"] == world)
    return cm.c_price_of(v0, ctx["bridge_amount"], ctx["gov"], res["divisor"], ctx["pending_amount"])


def _point_weights(res: dict) -> dict:
    """Веса миров в точке (М§9): (1 − λ) × вес слоя «рыночные ставки как есть» + λ × вес слоя «свой взгляд»."""
    weights = cm.c_layer_weights(res["ctx"]["B"])
    lam = res["lam"]
    return {w: (1.0 - lam) * weights["macro_neutral"].get(w, 0.0) + lam * weights["analytical"].get(w, 0.0)
            for w in res["ctx"]["worlds"]}


@pytest.mark.tact
def test_world_prices_stand_on_the_divisor(control):
    """М§8.2, §8.4: цена мира — той же формулой и на том же делителе N_div, что цена слоя. Пока оценка каждого
    мира больше объявленного дивиденда до вычета (формула цены линейна по V0), цена слоя — смесь цен миров с
    весами слоя, точка — смесь с весами точки; на акциях в обращении вместо делителя равенство не держится."""
    ctx = control["ctx"]
    prices = {w: _world_price(control, w) for w in ctx["worlds"]}
    assert prices == {w: cm.c_world_price(control, w) for w in ctx["worlds"]}
    floor = cm.c_price_of(control["pending_amount"], ctx["bridge_amount"], ctx["gov"], control["divisor"],
                          control["pending_amount"])
    if min(prices.values()) <= floor:
        pytest.skip("оценка мира не больше объявленного дивиденда: формула цены не линейна по V0")
    weights = cm.c_layer_weights(ctx["B"])
    for name, ly in control["layers"].items():
        mixed = sum(weights[name].get(w, 0.0) * prices[w] for w in ctx["worlds"])
        assert mixed == pytest.approx(ly["price"], rel=1e-12), name
    assert sum(k * prices[w] for w, k in _point_weights(control).items()) == pytest.approx(control["point"], rel=1e-12)
    if control["divisor"] != control["shares_out"]:
        scale = control["divisor"] / control["shares_out"]            # цена на акциях в обращении — не цена мира
        assert sum(k * prices[w] * scale for w, k in _point_weights(control).items()) != pytest.approx(
            control["point"], rel=1e-6)


# вне такта сервера: два прогона сетки сверх основного; подмены гейта в такте держит
# test_volume_sign_changes_only_its_keys, сверку числа с ядром — test_volume_sign_numbers_match_core
def test_volume_sign_numbers_of_the_control_model(control):
    """Гейт знака объёмных эффектов (М§4.5, §14.2): его числа контрольная модель считает сама — сдвиг точки и
    цен миров при снятии остановки кредита в кризисе (loan_growth_override пуст) и поправок роста режимов
    (loan_growth_adj = 0); у книги с включённым ограничением роста обе стороны — при выключенном
    ограничении. Знак не утверждается: рост сверх капитала может не создавать стоимости — это свойство чисел
    книги, его судит гейт с объяснением, а не тест. Проверяется счёт: сдвиг точки — та же смесь сдвигов цен
    миров, что сама точка (цены миров — на делителе N_div)."""
    sign = shared_gates()["volume_sign"]
    B = control["ctx"]["B"]
    assert sign["growth_constraint_off"] == bool(control["growth_rule"])
    assert sign["market_world"] == cm.W_MKT
    assert sign["reference_world"] == B["nii"]["transmission"]["reference_world"]
    assert set(sign["d_world"]) == set(control["ctx"]["worlds"])
    numbers = [sign["point"], sign["point_free"], sign["d_point"], *sign["d_world"].values()]
    assert all(isinstance(x, float) and math.isfinite(x) for x in numbers), sign
    assert sign["d_point"] == sign["point_free"] - sign["point"]
    spec = cm.c_bopt(B, "checks.volume_sign")                       # условие гейта — только у книги с ключом
    if spec is None:
        assert sign["tol"] is None and sign["ok"] is None
    else:
        tol = float(spec["tol"])
        fired = (sign["d_point"] < -tol
                 or sign["d_world"][cm.W_MKT] < sign["d_world"][sign["reference_world"]] - tol)
        assert sign["tol"] == tol and sign["ok"] == (not fired)
    if not sign["growth_constraint_off"]:
        assert sign["point"] == control["point"]                   # выключать нечего: база — прогон книги
    mixed = sum(k * sign["d_world"][w] for w, k in _point_weights(control).items())
    assert sign["d_point"] == pytest.approx(mixed, abs=1e-9)


@pytest.mark.tact
def test_volume_sign_changes_only_its_keys(inputs, monkeypatch):
    """Обе стороны гейта знака объёмных эффектов — подмены книги и больше ничего: база отличается от книги
    только выключателем ограничения роста (у книги без включённого ограничения — ничем), вторая сторона от
    базы — пустой остановкой кредита в кризисе и нулевыми поправками роста всех режимов. Готовый прогон
    книги служит базой только тогда, когда выключать нечего."""
    book, facts = inputs
    seen = []

    def fake_ctx(b):
        return {"worlds": list(b["worlds"]["ids"]), "clock": {"v": None}, "B": b, "bridge_amount": 0.0, "gov": 0.0,
                "pending_amount": 0.0, "A": {"N_div": 1.0}}

    def fake_run(b, f, **kw):
        seen.append(cm.copy.deepcopy(b))
        return {"point": float(len(seen)), "cells": [], "posterior": {}, "ctx": fake_ctx(b)}

    monkeypatch.setattr(cm, "c_control_run", fake_run)

    def changed(a, b, path=""):
        if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b):
            return [x for k in a for x in changed(a[k], b[k], f"{path}.{k}" if path else str(k))]
        return [] if a == b else [path]

    regimes = list(book["regimes"]["ids"])
    wanted = sorted(([f"regimes.{cm.R_CRISIS}.loan_growth_override"]
                     if book["regimes"][cm.R_CRISIS]["loan_growth_override"] != {} else [])
                    + [f"regimes.{r}.loan_growth_adj" for r in regimes if book["regimes"][r]["loan_growth_adj"] != 0.0])
    rule = cm.c_bopt(book, "capital.growth_constraint")
    on = isinstance(rule, dict) and bool(rule.get("enabled"))
    out = cm.c_volume_sign(book, facts)
    base, free = seen
    assert changed(book, base) == (["capital.growth_constraint.enabled"] if on else [])
    assert sorted(changed(base, free)) == wanted
    assert free["regimes"][cm.R_CRISIS]["loan_growth_override"] == {}
    assert all(free["regimes"][r]["loan_growth_adj"] == 0.0 for r in regimes)
    assert out["growth_constraint_off"] == on and out["d_point"] == 1.0
    seen.clear()
    ready = {"point": 0.0, "cells": [], "posterior": {}, "ctx": fake_ctx(book)}
    cm.c_volume_sign(book, facts, ready)
    assert len(seen) == (2 if on else 1)                           # готовый прогон — база, если выключать нечего
    off = cm.copy.deepcopy(book)
    if on:
        off["capital"]["growth_constraint"]["enabled"] = False
    seen.clear()
    cm.c_volume_sign(off, facts, ready)
    assert len(seen) == 1 and sorted(changed(off, seen[0])) == wanted


# ============================================================================ уровни после фазы роста (М§14.2)


LEVEL_METRICS = ("nim", "cor", "cir")


def with_checks(control: dict, **keys) -> dict:
    """Тот же прогон с другими ключами проверок книги (checks.<ключ>: значение; None — ключ снят): счёт уровней
    и их гейтов читает только эти ключи, клетки прогона — те же."""
    book = control["ctx"]["B"]
    checks = dict(book["checks"])
    for key, value in keys.items():
        if value is None:
            checks.pop(key, None)
        else:
            checks[key] = value
    out = dict(control)
    out["ctx"] = {**control["ctx"], "B": {**book, "checks": checks}}
    return out


def level_start(control: dict) -> int:
    """Первый год участка уровней для тестов: год ключа книги checks.window_backtest, а у книги без ключа —
    середина полных лет сетки (вход теста, не допущение)."""
    spec = cm.c_bopt(control["ctx"]["B"], f"checks.{WINDOW_KEY}")
    if spec is not None:
        return int(spec["from_year"])
    full = [p["year"] for p in control["ctx"]["periods"] if not p["stub"]]
    return full[len(full) // 2]


def levels_checks(control: dict) -> None:
    """Уровни после фазы роста своим счётом (М§0.3, §14.2). Метрика смеси клеток — отношение ожидаемых
    агрегатов: ожидание годового числителя к ожиданию знаменателя (среднее пяти концов кварталов процентных
    активов у ЧПМ и кредитов по амортизированной стоимости у CoR, доход NII + F + INS + MISC + FVR у C/I), в
    упр. базис — через мост; уровень — простое среднее лет участка. Смеси — модальная клетка (её собственные
    годовые метрики), слой «свой взгляд», смесь точки, слой «рыночные ставки как есть» (только клетки его
    мира). Отношение ожиданий лежит между крайними отношениями клеток смеси и не равно ожиданию отношений."""
    ctx = control["ctx"]
    A, B = ctx["A"], ctx["B"]
    start = level_start(control)
    full = [p["year"] for p in ctx["periods"] if not p["stub"]]
    years = [y for y in full if y >= start]
    assert cm.c_levels(with_checks(control, **{WINDOW_KEY: None})) is None           # ни ключа, ни года — уровней нет
    lv = cm.c_levels(control, start)
    assert lv["from_year"] == start and lv["years"] == years
    weights = cm.c_mix_weights(control)
    assert list(lv["mixes"]) == list(weights) == [cm.MIX_MODAL, cm.LAYER_OWN, cm.MIX_POINT, cm.LAYER_MARKET]
    keys = [(c["world"], c["regime"], c["scenario"]) for c in control["cells"]]
    assert weights[cm.MIX_MODAL] == {tuple(control["central"]["cell"]): 1.0}
    lam, low_world = control["lam"], cm.c_bget(B, "joint.macro_neutral_world")
    for key in keys:
        own, low = weights[cm.LAYER_OWN][key], weights[cm.LAYER_MARKET][key]
        assert weights[cm.MIX_POINT][key] == pytest.approx((1.0 - lam) * low + lam * own, abs=1e-15)
        assert (low > 0.0) <= (key[0] == low_world)                 # слой «как есть» — только клетки своего мира
    for name in (cm.LAYER_OWN, cm.MIX_POINT, cm.LAYER_MARKET):
        assert sum(weights[name].values()) == pytest.approx(1.0, abs=1e-12)
    parts = {"nim": ("nii", lambda r: sum(r["iea_ends"]) / (cm.QY + 1)),
             "cor": ("llp", lambda r: sum(r["loans_ac_ends"]) / (cm.QY + 1)),
             "cir": ("opex", lambda r: r["nii"] + r["fees"] + r["ins"] + r["misc"] + r["fvr"])}
    apart = 0.0
    for mix, weight in weights.items():
        level = lv["mixes"][mix]
        for y in years:
            i = control["years"].index(y)
            rows = [(weight.get(key, 0.0), c["rows"][i]) for key, c in zip(keys, control["cells"])]
            rows = [(k, r) for k, r in rows if k]
            assert all(len(r["iea_ends"]) == len(r["loans_ac_ends"]) == cm.QY + 1 for _, r in rows)
            for x, (top, base) in parts.items():
                ratio = sum(k * r[top] for k, r in rows) / sum(k * base(r) for k, r in rows)
                got = level["by_year"][y][x]
                assert got == pytest.approx(cm.c_to_mgmt(A, x, ratio), rel=1e-12), (mix, y, x)
                own = [cm.c_to_mgmt(A, x, r[f"{x}_year"]) for _, r in rows]     # годовые метрики самих клеток
                assert own == pytest.approx([cm.c_to_mgmt(A, x, r[top] / base(r)) for _, r in rows], rel=1e-12)
                assert min(own) - 1e-12 <= got <= max(own) + 1e-12, (mix, y, x)
                apart = max(apart, abs(got - sum(k * v for (k, _), v in zip(rows, own)) / sum(k for k, _ in rows)))
        for x in LEVEL_METRICS:
            assert level[x] == pytest.approx(sum(level["by_year"][y][x] for y in years) / len(years), rel=1e-15)
    assert apart > 1e-9, "ожидание отношений совпало с отношением ожиданий: тест их не различает"
    cell = cm.c_cell_of(control, *control["central"]["cell"])             # модальная клетка — её собственные метрики
    modal = lv["mixes"][cm.MIX_MODAL]["by_year"]
    for y in years:
        row = cell["rows"][control["years"].index(y)]
        assert row["cir_year"] == row["cir"] and row["loans_ac_ends"][-1] == pytest.approx(row["loans_ac"], rel=1e-8)
        for x in LEVEL_METRICS:
            assert modal[y][x] == pytest.approx(cm.c_to_mgmt(A, x, row[f"{x}_year"]), rel=1e-12)
    stub = [r for p, r in zip(ctx["periods"], cell["rows"]) if p["stub"]]       # неполный год якоря значений не несёт
    assert all(r["nim_year"] is None and r["cor_year"] is None and r["cir_year"] is None for r in stub)
    with pytest.raises(cm.ControlInputError):
        cm.c_levels(control, control["years"][-1] + 1)


def window_backtest_checks(control: dict) -> None:
    """Гейт сверки с окном фактов своим счётом (ключ checks.window_backtest: {from_year, cor: [низ, верх], cir:
    [низ, верх]}, подставлен тестом): уровни CoR и C/I слоя «рыночные ставки как есть» — внутри коридоров
    книги, края включены; гейт называет метрику, вышедшую из коридора. Маржа гейтом не сверяется — печатается.
    Нет ключа — гейта нет. CoR — в форме ключа книги: при множителях CoR по книгам (М7) — на составе якоря."""
    start = level_start(control)
    assert cm.c_window_backtest(with_checks(control, **{WINDOW_KEY: None})) is None
    lv = cm.c_levels(control, start)
    layer = lv["mixes"][cm.LAYER_MARKET]
    step = TOL_RATIO                                            # полуширина коридора — вход теста
    # CoR, которую судит гейт, — в форме ключа книги: при множителях CoR по книгам (М7) — на составе якоря, реализованная
    # печатается рядом; без ключа — реализованная
    cor_of = "cor_mix0" if control["ctx"].get("book_rel") is not None else "cor"
    cor = layer[cor_of]

    def gate(**change):
        spec = {"from_year": start, "cor": [cor - step, cor + step],
                "cir": [layer["cir"] - step, layer["cir"] + step], **change}
        return cm.c_window_backtest(with_checks(control, **{WINDOW_KEY: spec}))

    inside = gate()
    assert inside["ok"] and inside["outside"] == [] and inside["layer"] == cm.LAYER_MARKET
    assert (inside["from_year"], inside["years"]) == (start, lv["years"])
    assert (inside["cor"], inside["cir"], inside["nim"]) == (cor, layer["cir"], layer["nim"])
    if cor_of != "cor":
        assert inside["cor_realized"] == layer["cor"]
    assert gate(cor=[cor, cor], cir=[layer["cir"], layer["cir"]])["ok"]      # края включены
    above = gate(cor=[cor + step, cor + 2.0 * step])
    assert not above["ok"] and above["outside"] == ["cor"]
    below = gate(cir=[layer["cir"] - 2.0 * step, layer["cir"] - step])
    assert not below["ok"] and below["outside"] == ["cir"]
    assert gate(cor=[1.0, 2.0], cir=[1.0, 2.0])["outside"] == ["cor", "cir"]
    later = gate(from_year=lv["years"][-1])                     # другой год участка — другие уровни
    assert later["years"] == lv["years"][-1:] and later["cor"] == layer["by_year"][lv["years"][-1]][cor_of]
    for wrong in ({"from_year": None}, {"cor": layer["cor"]}, {"cir": [0.6, 0.4]}, {"cir": None},
                  {"from_year": lv["years"][-1] + 1}):
        with pytest.raises(cm.ControlInputError):
            gate(**wrong)


def cir_level_checks(control: dict) -> None:
    """Уровень C/I цели книги своим счётом (ключ checks.cir_lt, подставлен тестом): без области — модальная
    клетка, как у образца; scope: market_layer — слой «рыночные ставки как есть», отношение ожидаемых
    агрегатов; годы — от from_year ключа; вердикт — уровень в допуске от цели. Нет ключа — уровня нет."""
    ctx = control["ctx"]
    start = level_start(control)
    assert cm.c_cir_level(with_checks(control, cir_lt=None)) is None
    lv = cm.c_levels(control, start)
    key = {"target": 0.5, "tolerance": 0.01, "from_year": start}             # цель и допуск — входы теста
    for scope in (None, cm.SCOPE_MODAL, cm.SCOPE_MARKET):
        spec = dict(key) if scope is None else {**key, "scope": scope}
        mix = cm.LAYER_MARKET if scope == cm.SCOPE_MARKET else cm.MIX_MODAL
        want = lv["mixes"][mix]
        out = cm.c_cir_level(with_checks(control, cir_lt=spec))
        assert (out["scope"], out["mix"], out["from_year"]) == (scope, mix, start)
        assert out["cell"] == (control["central"]["label"] if mix == cm.MIX_MODAL else None)
        assert out["by_year"] == {y: want["by_year"][y]["cir"] for y in lv["years"]}
        assert out["value"] == pytest.approx(want["cir"], rel=1e-15)
        assert out["ok"] == (abs(out["value"] - key["target"]) <= key["tolerance"])
        near = cm.c_cir_level(with_checks(control, cir_lt={**spec, "target": out["value"] + 0.5 * key["tolerance"]}))
        far = cm.c_cir_level(with_checks(control, cir_lt={**spec, "target": out["value"] + 2.0 * key["tolerance"]}))
        assert near["ok"] and not far["ok"] and near["value"] == far["value"] == out["value"]
    cell = cm.c_cell_of(control, *control["central"]["cell"])
    own = [cm.c_to_mgmt(ctx["A"], "cir", r["cir"]) for y, r in zip(control["years"], cell["rows"]) if y >= start]
    assert lv["mixes"][cm.MIX_MODAL]["cir"] == pytest.approx(sum(own) / len(own), rel=1e-12)
    for wrong in ({**key, "scope": "нет такой области"}, {"target": 0.5, "tolerance": 0.01},
                  {**key, "from_year": control["years"][-1] + 1}):
        with pytest.raises(cm.ControlInputError):
            cm.c_cir_level(with_checks(control, cir_lt=wrong))


@pytest.mark.tact
def test_levels_are_ratios_of_expected_aggregates(control):
    """Уровни после фазы роста на клетках книги: четыре смеси, три метрики, отношение ожидаемых агрегатов."""
    levels_checks(control)


@pytest.mark.tact
def test_window_backtest_and_cir_level_of_the_control_model(control):
    """Гейт сверки с окном фактов и уровень C/I цели книги — свой счёт при ключах, подставленных тестом; на
    книге как она есть гейт и уровень есть ровно при своих ключах, вердикт тест не судит."""
    window_backtest_checks(control)
    cir_level_checks(control)
    B = control["ctx"]["B"]
    window, level = cm.c_window_backtest(control), cm.c_cir_level(control)
    assert (window is None) == (cm.c_bopt(B, f"checks.{WINDOW_KEY}") is None)
    assert (level is None) == (cm.c_bopt(B, "checks.cir_lt") is None)
    if window is not None:
        assert window["from_year"] == int(B["checks"][WINDOW_KEY]["from_year"]) and isinstance(window["ok"], bool)
    if level is not None:
        market = B["checks"]["cir_lt"].get(SCOPE_KEY) == cm.SCOPE_MARKET
        assert level["mix"] == (cm.LAYER_MARKET if market else cm.MIX_MODAL)


@pytest.mark.tact
def test_fade_is_one_sided(inputs, control):
    """В13, № 75 (М§7): ROE'_T = k_T + fade × max(ROE_T − k_T, 0) + min(ROE_T − k_T, 0). Множитель действует
    только на положительный избыток: fade < 1 не повышает оценку ни в одной клетке; при ROE_T ≥ k_T —
    прежняя формула; при ROE_T < k_T оценка от fade не зависит; DDM = RI держится. Множитель входит только в
    оценку клетки, путь клетки от него не зависит, поэтому тест идёт переоценкой клеток прогона, а не вторым
    прогоном сетки; одна клетка пересчитана целиком — переоценка равна пересчёту. В форме блока К-Т (λ_F < 1) —
    то же правило на избытке бизнеса X_B: ROE'_T = k + φ X_B (k − g) / B."""
    book, facts = inputs
    f = 0.5 * cm.c_bnum(book, "valuation.terminal.fade")          # вход теста: половина множителя книги
    b2 = cm.copy.deepcopy(book)
    b2["valuation"]["terminal"]["fade"] = f
    ctx = dict(control["ctx"])
    ctx["B"] = {**ctx["B"], "valuation": {**ctx["B"]["valuation"],
                                          "terminal": {**ctx["B"]["valuation"]["terminal"], "fade": f}}}
    above = below = 0
    faded = {}
    for c0 in control["cells"]:
        tag = (c0["world"], c0["regime"], c0["scenario"])
        cell = dict(zip(("world", "regime", "scenario"), tag))
        c1 = faded[tag] = cm._c_value_cell(ctx, cell, [dict(r) for r in c0["rows"]], c0["decisions"])
        assert c1["roe_t_raw"] == c0["roe_t_raw"] and c1["k_t"] == c0["k_t"], tag
        gap = c1["roe_t_raw"] - c1["k_t"]
        assert c1["v_ri"] <= c0["v_ri"], tag
        assert abs(c1["v_ddm"] - c1["v_ri"]) <= 1e-9 * abs(c1["v_ri"]), tag
        if "terminal_fixed" in c1:
            # форма блока К-Т (λ_F < 1, М§7): множитель — на избытке бизнеса X_B, только положительном;
            # ROE'_T = k + φ X_B (k − g) / B, ниже k_T — без угасания
            blk, blk0 = c1["terminal_fixed"], c0["terminal_fixed"]
            assert blk["x_b"] == blk0["x_b"], tag
            phi = f if blk["x_b"] > 0.0 else 1.0
            want = c1["k_t"] + phi * blk["x_b"] * (c1["k_t"] - c1["g_t"]) / blk["business_capital"]
            assert c1["roe_t"] == pytest.approx(want, abs=1e-15), tag
            if blk["x_b"] > 0.0:
                above += 1
            else:
                assert c1["roe_t"] == c0["roe_t"] and c1["v_ri"] == c0["v_ri"], tag
                below += 1
        elif gap >= 0.0:
            assert c1["roe_t"] == pytest.approx(c1["k_t"] + f * gap, abs=1e-15), tag
            above += 1
        else:
            assert c1["roe_t"] == c1["roe_t_raw"] and c1["v_ri"] == c0["v_ri"], tag
            below += 1
    assert above, "нет клетки с ROE_T не ниже k_T"
    for weight in cm.c_mix_weights(control).values():            # оценка любой смеси клеток не выросла
        assert sum(k * faded[tag]["v_ri"] for tag, k in weight.items()) <= sum(
            k * cm.c_cell_of(control, *tag)["v_ri"] for tag, k in weight.items())
    key = tuple(control["central"]["cell"])                      # переоценка клетки — её пересчёт на книге с f
    again = cm.c_cell_annual(cm.c_control_context(b2, facts), *key)
    assert again["v_ri"] == pytest.approx(faded[key]["v_ri"], rel=1e-12)
    assert again["roe_t"] == pytest.approx(faded[key]["roe_t"], abs=1e-15)
    if not below:                                # книга без клеток ниже k_T: та же проверка на подмене терминала
        base = cm.c_cell_of(control, cm.W_MKT, "downturn", "strict")
        rows = [dict(r) for r in base["rows"]]
        rows[-1]["pbt"] = 0.5 * rows[-1]["pbt"]
        cell = {"world": cm.W_MKT, "regime": "downturn", "scenario": "strict"}
        low_f = cm._c_value_cell(ctx, cell, rows, base["decisions"])
        low_1 = cm._c_value_cell(control["ctx"], cell, [dict(r) for r in rows], base["decisions"])
        assert low_f["roe_t_raw"] < low_f["k_t"] and low_f["v_ri"] == low_1["v_ri"]
    # симметричное угасание — правило справочного варианта таблиц книги: точку книги с ним модель не считает
    b3 = cm.copy.deepcopy(book)
    b3["valuation"]["terminal"]["fade_mode"] = cm.FADE_SYMMETRIC
    with pytest.raises(cm.ControlUnsupported):
        cm.c_control_context(b3, facts)


@pytest.mark.tact
def test_fvc_reference_stays_with_the_book(inputs, control):
    if not control["ctx"]["fv"]:
        pytest.skip("у книг панели нет доли кредитов по справедливой стоимости (fv_share): строка FVC — ноль "
                    "(М§4.6); " + NO_FAIR_VALUE)
    """В14, № 76 (М§4.6): опора FVC — путь режима-опоры книги до розыгрыша. Сдвиг путей CoR всех режимов на x
    (ось уровня, строка «₽ за 0,1 п.п. CoR») доходит до кредитов по СС: ΔFVC = f × x × Ē^СС × d/365 в каждом
    квартале каждой клетки, резервы растут на x × Ē^АС × d/365. Книга, собранная заново, — сама себе
    база: опора сдвигается вместе с путями, строка не меняется."""
    book, facts = inputs
    ctx = control["ctx"]
    B, A = ctx["B"], ctx["A"]
    if cm.c_bget(B, "credit.segment_relative.enabled"):
        pytest.skip("сегментная поправка CoR включена: сдвиг сегмента — не x")
    f = cm.c_bnum(B, "credit.fv_loans_factor")
    x = cm.c_bnum(book, "valuation.sensitivities.cor_pp")          # шаг строки чувствительности — из книги
    b2 = cm.copy.deepcopy(book)
    for r in b2["regimes"]["ids"]:
        b2["regimes"][r]["cor"] = _shifted(b2["regimes"][r]["cor"], x)
    moved = cm.c_control_context(b2, facts, base_book=book)
    rebuilt = cm.c_control_context(b2, facts)
    x_eng = x
    if B["regimes"]["cor_basis"] == "mgmt":
        x_eng = cm.c_to_engine(A, "cor", x) - cm.c_to_engine(A, "cor", 0.0)
    scen = list(cm.c_bget(B, "capital.reg_scenarios.ids"))
    for key in ((plain_world(B), ctx["fv_ref"], scen[0]), (cm.W_MKT, "soft", scen[-1]), ("H", cm.R_CRISIS, scen[0])):
        base = cm.c_cell_of(control, *key)["rows"]
        new = cm.c_cell_annual(moved, *key)["rows"]
        own = cm.c_cell_annual(rebuilt, *key)["rows"]
        for p, r0, r1, r2 in zip(ctx["periods"], base, new, own):
            for j in range(p["n"]):
                want = f * x_eng * r0["fv_avg_q"][j] * r0["days_q"][j] / cm.DAYS_BASE
                assert r1["fvc_q"][j] - r0["fvc_q"][j] == pytest.approx(want, rel=1e-9, abs=1e-12), (key, p["year"], j)
                assert r1["cor_ref_q"][j] == r0["cor_ref_q"][j]
                assert r2["fvc_q"][j] == pytest.approx(r0["fvc_q"][j], rel=1e-9, abs=1e-12)
            assert r1["llp"] - r0["llp"] == pytest.approx(
                x_eng * r0["loans_ac_avg"] * p["days"] / cm.DAYS_BASE, rel=1e-9)
    if f > 0.0 and x_eng > 0.0:                  # в клетке режима-опоры мира без κ-добавки сдвиг уровня — расход FVC
        ref_rows = cm.c_cell_annual(moved, plain_world(B), ctx["fv_ref"], scen[0])["rows"]
        assert all(r["fvc"] > 0.0 for r in ref_rows)


def _closed_periods(book: dict, count: int) -> list[str]:
    """Последние count кварталов не позже якоря (наблюдения таких кварталов несут замороженные μ)."""
    y, q = cm.c_per_parse(book["meta"]["anchor_period"])
    out = []
    for _ in range(count):
        out.append(f"{y}Q{q}")
        y, q = (y - 1, cm.QY) if q == 1 else (y, q - 1)
    return out[::-1]


@pytest.mark.tact
def test_regime_probability_floor(inputs):
    """В15, № 77 (М§12): после каждого наблюдения, вслед за пределом сдвига, вероятность режима не ниже
    floor_share × базовой; режим ниже пола ставится на пол, остальные умножаются на общий множитель до
    суммы 1 (с повтором, если ещё кто-то ушёл ниже). floor_share = 0 пол выключает, 1 — выключает
    обучение; значение вне [0; 1] — отказ."""
    floors = {"a": 0.05, "b": 0.10, "c": 0.10, "d": 0.05}                 # входы теста
    same = {"a": 0.06, "b": 0.50, "c": 0.30, "d": 0.14}
    assert cm.c_floor_probabilities(same, floors) == same
    one = cm.c_floor_probabilities({"a": 0.01, "b": 0.50, "c": 0.30, "d": 0.19}, floors)
    assert one["a"] == floors["a"] and sum(one.values()) == pytest.approx(1.0, abs=1e-15)
    assert one["b"] / one["c"] == pytest.approx(0.50 / 0.30, rel=1e-12)   # остальные — общим множителем
    assert one["d"] / one["c"] == pytest.approx(0.19 / 0.30, rel=1e-12)
    chain = cm.c_floor_probabilities({"a": 0.01, "b": 0.88, "c": 0.10, "d": 0.01}, floors)
    assert chain == pytest.approx({"a": 0.05, "b": 0.80, "c": 0.10, "d": 0.05}, abs=1e-15)   # c ушёл ниже пола на втором шаге
    full = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
    assert cm.c_floor_probabilities({"a": 0.10, "b": 0.60, "c": 0.20, "d": 0.10}, full) == pytest.approx(full, abs=1e-15)
    # цепочка наблюдений закрытых кварталов против одного режима
    book, facts = inputs
    regimes = list(book["regimes"]["ids"])
    prior = {r: float(v) for r, v in book["joint"]["regime_prob"].items()}
    share = cm.c_bnum(book, "joint.regime_update.floor_share")
    window = int(book["joint"]["regime_update"]["window_obs"])
    mu = {r: 0.010 + 0.004 * i for i, r in enumerate(regimes)}            # входы теста
    obs = [{**_obs(per, mu[regimes[0]], None), "mu_cor": mu} for per in _closed_periods(book, window)]

    def c_ctx(floor_share):
        b = cm.copy.deepcopy(book)
        b["joint"]["regime_update"].update(observations=obs, floor_share=floor_share)
        return cm.c_control_context(b, facts)

    ctx = c_ctx(share)
    assert len(ctx["updates"]) == len(obs) and ctx["updates"][-1]["posterior"] == ctx["posterior"]
    for step in ctx["updates"]:
        post = step["posterior"]
        assert sum(post.values()) == pytest.approx(1.0, abs=1e-12)
        for r in regimes:
            assert post[r] >= share * prior[r] - 1e-15, (step["period"], r)
    loose = c_ctx(0.0)
    assert sum(loose["posterior"].values()) == pytest.approx(1.0, abs=1e-12)
    washed = [r for r in regimes if loose["posterior"][r] < share * prior[r]]
    if share > 0.0:
        assert washed, "цепочка наблюдений не довела ни один режим до пола — тест ничего не проверяет"
        for r in washed:                                                  # без пола режим вымыт, с полом — стоит на нём
            assert ctx["posterior"][r] == pytest.approx(share * prior[r], abs=1e-15)
    frozen = c_ctx(1.0)
    assert all(step["posterior"] == pytest.approx(prior, abs=1e-15) for step in frozen["updates"])
    assert frozen["dev"][regimes[0]]["cor"]["m"] == ctx["dev"][regimes[0]]["cor"]["m"]   # отклонения клеток пол не трогает
    for bad in (-0.1, 1.2):
        with pytest.raises(cm.ControlInputError):
            c_ctx(bad)


@pytest.mark.tact
def test_each_observed_quarter_keeps_its_own_deviation(inputs):
    """М§12 (толкование — docs/CONTROL-MODEL.md §7): клетка несёт отклонение от последнего наблюдения окна
    не позже квартала. Наблюдённый прогнозный квартал держит своё отклонение и тогда, когда за ним в окне
    есть более позднее наблюдение: у факта (se = 0) ожидание режима плюс отклонение в каждом наблюдённом
    квартале равно наблюдению; после последнего наблюдения отклонение затухает как ρ^k."""
    book, facts = inputs
    q1 = book["meta"]["first_period"]
    q2 = _next_period(q1)
    seen = {q1: 0.020, q2: 0.011}                                         # входы теста
    b = cm.copy.deepcopy(book)
    b["joint"]["regime_update"]["observations"] = [_obs(per, val, None) for per, val in seen.items()]
    if int(b["joint"]["regime_update"]["window_obs"]) < len(seen):
        pytest.skip("окно книги короче двух наблюдений")
    ctx = cm.c_control_context(b, facts)
    plain = cm.c_control_context(book, facts)
    A = ctx["A"]
    rho = cm.c_bnum(book, "joint.regime_update.observables.cor.rho_q")
    y3, q3 = cm.c_per_parse(_next_period(q2))
    for r in book["regimes"]["ids"]:
        dv = ctx["dev"][r]["cor"]
        assert [(y, q) for y, q, _ in dv["trail"]] == [cm.c_per_parse(q1), cm.c_per_parse(q2)]
        assert dv["trail"][-1][2] == dv["m"] and dv["trail"][0][2] != dv["m"]
        for per, val in seen.items():
            y, q = cm.c_per_parse(per)
            assert ctx["mu"][("cor", r, y, q)] + cm._c_dev_at(dv, y, q) == pytest.approx(
                cm.c_to_engine(A, "cor", val), abs=1e-15), (r, per)
        assert cm._c_dev_at(dv, y3, q3) == pytest.approx(rho * dv["m"], rel=1e-12)
    # то же в клетке: CoR наблюдённых кварталов сдвинут каждый на своё отклонение
    p0 = ctx["periods"][0]
    marks = [f"{p0['year']}Q{q}" for q in p0["quarters"]]
    if q1 in marks and q2 in marks:
        r0 = book["regimes"]["ids"][0]
        with_obs = cm.c_cell_annual(ctx, cm.W_LOW, r0, "schedule")["rows"][0]["cor_q"]
        without = cm.c_cell_annual(plain, cm.W_LOW, r0, "schedule")["rows"][0]["cor_q"]
        trail = ctx["dev"][r0]["cor"]["trail"]
        for per, (_, _, m) in zip((q1, q2), trail):
            j = marks.index(per)
            assert with_obs[j] - without[j] == pytest.approx(m, abs=1e-15), per


@pytest.mark.tact
def test_frozen_expectations_do_not_follow_the_book(inputs):
    """В15 (М§12): замороженные μ наблюдения квартала не позже якоря не пересчитываются — запись хранит
    ожидания, действовавшие на момент наблюдения. Смена путей режимов книги (её делает и смена года якоря:
    кризисные ключи сдвигаются) не меняет ни отклонений такого наблюдения, ни апостериорных."""
    book, facts = inputs
    regimes = list(book["regimes"]["ids"])
    mu = {r: 0.010 + 0.004 * i for i, r in enumerate(regimes)}            # входы теста
    rec = {**_obs(book["meta"]["anchor_period"], 0.0135, None), "mu_cor": mu}
    b1 = cm.copy.deepcopy(book)
    b1["joint"]["regime_update"]["observations"] = [rec]
    b2 = cm.copy.deepcopy(b1)
    step = cm.c_bnum(book, "valuation.sensitivities.cor_pp")
    for i, r in enumerate(regimes):
        b2["regimes"][r]["cor"] = _shifted(b2["regimes"][r]["cor"], (i + 1) * step)
    c1, c2 = cm.c_control_context(b1, facts), cm.c_control_context(b2, facts)
    assert c2["posterior"] == c1["posterior"] and c2["dev"] == c1["dev"] and c2["mu"] == c1["mu"]
    assert b2["joint"]["regime_update"]["observations"][0]["mu_cor"] == mu


@pytest.mark.tact
def test_central_cell_follows_the_rule(inputs, control):
    """№ 86 (INTERFACES §4.6): центральная клетка — мода по каждой оси в слое «свой взгляд»: мир с наибольшим
    весом, режим с наибольшей вероятностью после A-P2u, сценарий капитала с наибольшей P(s | r) у этого
    режима; при равенстве — первый по порядку книги. Вероятность клетки и вес сценария — рядом."""
    book, facts = inputs
    B = control["ctx"]["B"]
    pw = {w: float(v) for w, v in B["joint"]["world_prob"].items()}
    prs = B["joint"]["reg_prob_given_regime"]
    cen = control["central"]
    w, r, s = cen["cell"]
    assert pw[w] == max(pw.values()) and control["posterior"][r] == max(control["posterior"].values())
    assert float(prs[r][s]) == max(float(v) for v in prs[r].values())
    assert cen["label"] == f"{w}/{r}/{s}" and cen["scenario_weight"] == float(prs[r][s])
    assert cen["probability"] == pytest.approx(pw[w] * control["posterior"][r] * float(prs[r][s]), abs=1e-15)
    assert any(cen["label"] in line for line in cm.c_summary_lines(control))
    # правило, а не литерал: другие вероятности — другая клетка; равенство — первый по порядку книги
    regimes, worlds = list(B["regimes"]["ids"]), list(B["worlds"]["ids"])
    b2 = cm.copy.deepcopy(book)
    rest = 0.4 / (len(regimes) - 1)
    b2["joint"]["regime_prob"] = {x: (0.6 if x == regimes[-1] else rest) for x in regimes}
    b2["joint"]["world_prob"] = {x: 1.0 / len(worlds) for x in worlds}
    ctx2 = cm.c_control_context(b2, facts)
    alt = cm.c_central_cell({"ctx": ctx2, "posterior": ctx2["posterior"]})
    last = prs[regimes[-1]]
    scen = list(B["capital"]["reg_scenarios"]["ids"])
    best = [x for x in scen if float(last[x]) == max(float(v) for v in last.values())][0]
    assert alt["cell"] == (worlds[0], regimes[-1], best)


@pytest.mark.tact
def test_central_cell_agrees_with_the_book_results(control):
    """№ 86: клетка «центральная» в results.json (её выпускает ядро) — та же, что по правилу у контрольной
    модели, с той же вероятностью и весом сценария."""
    path = cm.BOOK_DIR / "results.json"
    if not path.exists():
        pytest.skip("results.json ещё не выпущен")
    doc = json.loads(path.read_text(encoding="utf-8"))
    cen = doc.get("central_cell")
    version = str(cm.c_bget(control["ctx"]["B"], "meta.version"))
    if str(doc.get("book_version")) != version or not isinstance(cen, dict) or "cell" not in cen:
        pytest.skip("results.json — прежней версии книги или без клетки по правилу (перевыпуск — после правок ядра)")
    mine = control["central"]
    assert cen["cell"] == mine["label"]
    assert cen["probability"] == pytest.approx(mine["probability"], abs=1e-12)
    assert cen["scenario_weight"] == pytest.approx(mine["scenario_weight"], abs=1e-12)


@pytest.mark.tact
def test_average_balances_of_the_year(inputs, control):
    """Годовая агрегация средних остатков (docs/CONTROL-MODEL.md §3). Небалансирующая статья растёт внутри
    периода одним квартальным множителем: средний остаток — сумма квартальных трапеций геометрического
    пути, у растущей статьи он ниже полусуммы начала и конца. Балансирующие активы: к полусумме начала и
    конца прибавляется время капитальных потоков по квартальному профилю дохода — доход квартала j входит
    в активы со следующего квартала, вес (n − j)/n − ½ — и выплаты, вес (n − j_выплаты + ½)/n − ½, и
    кривизна небалансирующих статей. При связанном на обоих концах минимуме ликвидности LA стоит на
    минимуме, а время потоков несёт добор опта. Средний опт без добора — база опта в форме ключей книги (Р4-16):
    s_eff × средства (структурная доля К3, иначе доля якоря)."""
    assert cm._c_geo_path(100.0, 100.0, cm.QY) == [100.0] * (cm.QY + 1)                # входы теста
    path = cm._c_geo_path(100.0, 121.0, 2)
    assert path == pytest.approx([100.0, 110.0, 121.0], rel=1e-12)
    assert cm._c_path_mean(path) == pytest.approx((105.0 + 115.5) / 2.0, rel=1e-12)
    assert cm._c_path_mean(path) < (100.0 + 121.0) / 2.0
    assert cm._c_geo_path(0.0, 8.0, 2) == [0.0, 4.0, 8.0]                              # с нуля — линейно
    ctx = control["ctx"]
    A = ctx["A"]
    loans = [b for b, sp in ctx["B"]["nii"]["books"].items() if sp.get("sector")]
    ssl = cm.c_bnum(ctx["B"], "volumes.securities_share_of_liquid")
    geometric = ctx["growth"] is None            # при ограничении роста путь кредитов внутри года — не геометрический
    s_eff = cm.c_forms(ctx["B"])["s_eff"]
    # средства клиентов базы опта — слово балансовой механики (Р11-2: при volumes.funds_scope: clients — без книг К6)
    funds0 = A["E0"][cm.RETAIL_CURRENT] + A["E0"][cm.RETAIL_TERM] + sum(A["E0"][b] for b in ctx["fund_biz"])
    for c in control["cells"][::7]:
        ac_prev = sum(A["E0"][b] * (1.0 - ctx["fv"].get(b, 0.0)) for b in loans)
        la_prev = A["E0"][cm.SECURITIES] + A["E0"][cm.LIQUIDITY]
        # опт сверх базы s_eff × средства на начало периода: на якоре минимум ликвидности не связывает, но в форме К3
        # опт якоря сверх структурной доли — та же часть «по нужде», гасится в первом периоде (без К3 — ноль)
        extra_prev = max(0.0, A["E0"][cm.WHOLESALE] - s_eff * funds0)
        for p, r in zip(ctx["periods"], c["rows"]):
            n = p["n"]
            assert not geometric or r["loans_ac_avg"] < (ac_prev + r["loans_ac"]) / 2.0 or r["loans_ac"] <= ac_prev
            timing = sum(((n - (j + 1)) / n - 0.5) * x for j, x in enumerate(r["ci_q"]))
            assert r["shift_la"] == pytest.approx(timing - r["paid_shift"] + r["curve_la"], rel=1e-6, abs=1e-6)
            la_end = r["securities"] + r["liquidity"]
            if r["wholesale_extra"] == 0.0:                                         # минимум не связывает на конце периода
                assert r["la_avg"] == pytest.approx((la_prev + la_end) / 2.0 + r["shift_la"], rel=1e-12)
                if extra_prev == 0.0:            # и на начале: иначе средний опт несёт добор начала периода
                    # средний опт без добора — база опта в форме ключей книги: s_eff × средства (К3 — структурная доля)
                    assert r["wholesale_avg"] == pytest.approx(s_eff * r.get("clients_avg", r["funds_avg"]),
                                                               rel=1e-12)
            ac_prev, la_prev, extra_prev = r["loans_ac"], la_end, r["wholesale_extra"]
    # связанный минимум ликвидности: доля минимума — вход теста, выше доли LA в активах якоря
    book, facts = inputs
    b2 = cm.copy.deepcopy(book)
    la0 = A["E0"][cm.SECURITIES] + A["E0"][cm.LIQUIDITY]
    assets0 = sum(A["E0"][b] for b in loans) - A["AL"] + la0 + A["OA"]
    m = min(0.9, la0 / assets0 + 0.15)
    b2["volumes"]["liquid_min_share"] = m
    ctx2 = cm.c_control_context(b2, facts)
    rows = cm.c_cell_annual(ctx2, cm.W_MKT, "norm", "schedule")["rows"]
    bound = [(r0, r1) for r0, r1 in zip(rows, rows[1:]) if r0["wholesale_extra"] > 0.0 and r1["wholesale_extra"] > 0.0]
    assert bound, "минимум ликвидности не связал ни одного года подряд"
    wtf = cm.c_forms(ctx2["B"])["s_eff"]                # база опта в форме ключей книги (К3 — структурная доля)
    for r0, r1 in bound:
        assert r1["securities"] + r1["liquidity"] == pytest.approx(m * r1["assets"], rel=1e-9)
        assert r1["la_avg"] == pytest.approx(m / (1.0 - m) * r1["assets_nb_avg"], rel=1e-12)
        free = ((r0["securities"] + r0["liquidity"] - r0["wholesale_extra"]
                 + r1["securities"] + r1["liquidity"] - r1["wholesale_extra"]) / 2.0 + r1["shift_la"])
        base = r1["wholesale_avg"] - (r1["la_avg"] - free)                          # опт без добора
        assert base == pytest.approx(wtf * r1.get("clients_avg", r1["funds_avg"]), rel=1e-9)     # Р11-2: при clients
        assert r1["wholesale_avg"] > base


def _dated_record(year: int, dps: float, *, pay=None, reg=None, status: str = "declared") -> dict:
    """Запись реестра за год прибыли с датами в заданных кварталах (год, квартал): отсечка — на 20-й день
    квартала reg, выплата — на 34-й день квартала pay; None — даты в записи нет."""
    rec = {"year": year, "dps": dps, "status": status, "sources": ["сверка М§17"]}
    if reg is not None:
        day = cm.c_q_first_day(*reg) + dt.timedelta(days=19)
        rec.update(record_date=day.isoformat(), ex_date=day.isoformat(),
                   last_buy_date=(day - dt.timedelta(days=1)).isoformat())
    if pay is not None:
        rec["pay_date"] = (cm.c_q_first_day(*pay) + dt.timedelta(days=33)).isoformat()
    return rec


@pytest.mark.tact
@annual_only
def test_declared_dividend_follows_the_register_dates(inputs):
    """М§5.4: у объявленного дивиденда (запись declared | paid) даты записи сильнее календаря книги — выплата
    (дивиденды к выплате и ликвидность) в квартале pay_date, вычет из регуляторного капитала в квартале
    отсечки; нет даты — квартал календаря. Запись recommended календарь не меняет."""
    book, facts = inputs
    y0, _ = _agm_end(book)
    dps = _history_dps(facts)
    cal = book["dividends"]["calendar"]
    agm, pay_q, reg_q = int(cal["agm_quarter"]), int(cal["payment_quarter"]), int(cal["reg_deduction_quarter"])
    ya = y0 + 1
    cell = ("H", "norm", "schedule")

    def c_rows(register):
        f2 = cm.copy.deepcopy(facts)
        f2["dividends"]["register_seed"] = register
        ctx = cm.c_control_context(book, f2)
        return cm.c_cell_annual(ctx, *cell), ctx

    plain, ctx = c_rows([_dated_record(y0, dps)])                          # записи без дат — календарь книги
    i = [p["year"] for p in ctx["periods"]].index(ya)
    n = ctx["periods"][i]["n"]
    amount = dps * ctx["A"]["N_out"] / 1000.0
    assert plain["rows"][i]["div"] == pytest.approx(amount, rel=1e-12) and plain["decisions"][y0]["kind"] == "register"
    same, _ = c_rows([_dated_record(y0, dps, pay=(ya, pay_q), reg=(ya, reg_q))])
    assert same["v_ri"] == plain["v_ri"]                                   # даты в кварталах календаря — тот же расчёт
    nii = {}
    for q in range(agm, cm.QY + 1):
        c, _ = c_rows([_dated_record(y0, dps, pay=(ya, q), reg=(ya, min(q, reg_q)))])
        row = c["rows"][i]
        assert row["dp"] == 0.0 and row["div"] == pytest.approx(amount, rel=1e-12)
        # вес выплаты в среднем остатке ликвидных активов года: (n − j + ½)/n — чем позже, тем дольше деньги в балансе
        assert row["paid_shift"] == pytest.approx(((n - q + 0.5) / n - 0.5) * amount, rel=1e-9, abs=1e-9), q
        nii[q] = row["nii"]
    assert all(nii[q + 1] > nii[q] for q in range(agm, cm.QY))
    # выплата и отсечка в следующем году: на конец года ГОСА сумма — в дивидендах к выплате и ещё в
    # регуляторном капитале; через год — выплачена
    late, _ = c_rows([_dated_record(y0, dps, pay=(ya + 1, 1), reg=(ya + 1, 1))])
    assert late["rows"][i]["dp"] == pytest.approx(amount, rel=1e-12) and late["rows"][i + 1]["dp"] == 0.0
    assert late["rows"][i]["dpreg"] == pytest.approx(amount, rel=1e-12) and late["rows"][i + 1]["dpreg"] == 0.0
    assert plain["rows"][i]["dpreg"] == 0.0 and late["rows"][i]["n20"] > plain["rows"][i]["n20"]
    # дивиденд, вычтенный в якоре: сумма — факт баланса, квартал выплаты — по записи за этот год прибыли
    if ctx["A"]["DP"] and ctx["periods"][0]["stub"]:
        qs = ctx["periods"][0]["quarters"]
        n0 = len(qs)
        for q in qs:
            c, _ = c_rows([_dated_record(y0 - 1, dps, pay=(y0, q), reg=(y0, qs[0]), status="paid")])
            row = c["rows"][0]
            want = ((n0 - (qs.index(q) + 1) + 0.5) / n0 - 0.5) * ctx["A"]["DP"]
            assert row["dp"] == 0.0 and row["paid_shift"] == pytest.approx(want, rel=1e-9, abs=1e-9), q
    # recommended — только плашка: ни дивиденда года, ни календаря она не задаёт
    advised, _ = c_rows([_dated_record(y0, dps, pay=(ya, cm.QY), reg=(ya, cm.QY), status="recommended")])
    nothing, _ = c_rows([])
    assert advised["v_ri"] == nothing["v_ri"] and advised["decisions"][y0]["kind"] != "register"


# ============================================================================ сверка с ядром


def _core_grid(book_path=None):
    """Прогон ядра (импорт только здесь). Нет ядра или его функций — None и причина."""
    try:
        book_mod = importlib.import_module("model.book")
        grid_mod = importlib.import_module("model.grid")
    except Exception as exc:                                   # ядро ещё пишется
        return None, f"ядро не импортируется ({type(exc).__name__}: {exc})"
    if not (hasattr(book_mod, "load_book") and hasattr(book_mod, "load_facts")
            and hasattr(grid_mod, "run_grid")):
        return None, "в ядре нет load_book / load_facts / run_grid (INTERFACES §4.1, §4.3)"
    root = data_dir()
    try:
        facts = _core_facts(book_mod)
        book = (book_mod.load_book(facts=facts) if root is None
                else book_mod.load_book(root / "assumptions" / "assumptions.yaml", facts=facts))
        return grid_mod.run_grid(book, facts), ""
    except Exception as exc:
        # ядро не считает книгу (ветвь ещё не исполнена): сверка красная, причина — в сообщении
        return None, f"ядро не посчитало книгу ({type(exc).__name__}: {str(exc)[:600]})"


def _core_facts(book_mod):
    """Факты ядра из каталога данных сверки (по умолчанию — data/facts репозитория)."""
    root = data_dir()
    return book_mod.load_facts() if root is None else book_mod.load_facts(root / "facts")


def _quarter_index(ctl: dict) -> dict[int, list[int]]:
    """Год → номера кварталов сетки ядра (1…Q), которые покрывает период контрольной модели."""
    y0, qa = ctl["ctx"]["anchor"]
    out = {}
    for p in ctl["ctx"]["periods"]:
        out[p["year"]] = [(p["year"] - y0) * cm.QY + (q - qa) for q in p["quarters"]]
    return out


def verdict(diff, diff_rel, tol, tol_kind, tol_abs=None) -> bool:
    """Вердикт строки по тому, что в ней записано (то же видит читатель витрины): abs — |diff| ≤ tol;
    rel — |diff_rel| ≤ tol, или |diff| ≤ tol_abs у строк с правилом «или» (М§17), или обе величины —
    ноль (diff_rel не определена при core = 0)."""
    if diff is None or tol is None:
        return False
    if tol_kind == ABS:
        return abs(diff) <= tol
    if diff_rel is not None and abs(diff_rel) <= tol:
        return True
    if tol_abs is not None and abs(diff) <= tol_abs:
        return True
    return diff_rel is None and diff == 0.0


def _row(what, unit, core, control, tol, tol_kind, *, group, tol_abs=None, ok=None):
    """Строка сверки: diff = control − core в единицах строки, diff_rel = control/core − 1 (None при
    core = 0), вид допуска tol_kind — с чем сравнивается tol; tol_abs — абсолютный пол правила «или».
    group — группа для выбора худшей строки сводки (в файл не пишется)."""
    diff = diff_rel = None
    if tol_kind == REL:                      # машинный ноль относительной строки — ноль (иначе шум 1e-15 дал бы −100 %)
        core, control = (0.0 if (v is not None and abs(v) <= TOL_ZERO_BN) else v for v in (core, control))
    if core is not None and control is not None:
        diff = control - core
        diff_rel = control / core - 1.0 if core != 0.0 else None
    row = {"what": what, "unit": unit, "core": core, "control": control, "diff": diff, "diff_rel": diff_rel,
           "tol": tol, "tol_kind": tol_kind,
           "ok": bool(verdict(diff, diff_rel, tol, tol_kind, tol_abs) if ok is None else ok), "group": group}
    if tol_abs is not None:
        row["tol_abs"] = tol_abs
    return row


def _mark(rows: list, start: int, **meta) -> None:
    """Метки строк сверки rows[start:] — клетка (cell), год (year), квартал сетки (q): по ним правило ПОРОГ находит
    строки, которые идут за решением у порога. Внутренняя метка сильнее внешней; в сводку метки не идут (_public)."""
    for r in rows[start:]:
        for k, v in meta.items():
            r.setdefault(k, v)


def _missing(what, unit, control=None):
    return _row(f"{what}: нет у ядра", unit, None, control, None, ABS, group="missing", ok=False)


def _bridge_row(what, core, control):
    """Мост и объявленные дивиденды: ≤ 1 % (М§17); при нуле у ядра обе модели обязаны дать ноль."""
    if core is None:
        return _missing(what, U_BN, control)
    if core == 0.0:
        return _row(what, U_BN, core, control, TOL_ZERO_BN, ABS, group="bridge")
    return _row(what, U_BN, core, control, TOL_BRIDGE, REL, group="bridge")


def dps_floor(ctl: dict, cell: dict, profit_year: int) -> float:
    """Пол допуска DPS (М§17): 0,5 % BV конца года решения на акцию — тот же год, что у строки Div; в
    квартальном режиме — год последнего решения за кварталы прибыли этого года."""
    year = cell["decisions"][profit_year].get("decision_year", profit_year + 1)
    row = cell["rows"][ctl["years"].index(year)]
    return DIV_FLOOR_BV * abs(row["bv"]) * 1000.0 / ctl["ctx"]["A"]["N_out"]


def cut_quarters(c: dict, cc) -> dict[int, float]:
    """Кварталы клетки, где решение о дивиденде срезано до запаса (cut, М§5.7.4 п. 5 и §4.13.2 п. 2) хотя бы в
    одной из моделей, → RWA конца квартала (контрольная модель)."""
    mine = {d["q"] for d in c["decisions_q"] if d["cut"]}
    theirs = {d.q for d in (getattr(cc, "decisions", None) or ())
              if getattr(d, "cut", False) and getattr(d, "q", None) is not None}
    rwa = {x["q"]: x["rwa"] for r in c["rows"] for x in r["quarters"]}
    return {q: rwa[q] for q in mine | theirs if q in rwa}


def _cut_floor(row: dict, cut_rwa: dict, quarters, per_share: float = 1.0) -> dict:
    """Допуск дивиденда решения, срезанного до запаса (М§17): срезанный дивиденд равен запасу
    (N − req*) × RWA — малой разности, повторяющей расхождение норматива квартала между моделями, поэтому
    абсолютный пол строки — не меньше 0,3 п.п. × RWA квартала решения (производная допуска норматива, как у
    X_T); у суммы решений (DPS и дивиденд года) — наибольший RWA кварталов срезанных решений. Строка с
    правилом несёт метку cut и прежний пол floor_plain (в файл сводки они не идут)."""
    hit = [cut_rwa[q] for q in quarters if q in cut_rwa]
    if not hit or row["diff"] is None:
        return row
    plain = row.get("tol_abs")
    floor = TOL_RATIO * max(hit) * per_share
    if plain is None or floor > plain:
        row["tol_abs"] = floor
        row["ok"] = bool(verdict(row["diff"], row["diff_rel"], row["tol"], row["tol_kind"], floor))
    row["cut"], row["floor_plain"] = True, plain
    return row


def margin_row(run, ctl: dict, margin: dict) -> dict:
    """Печатаемая маржа после фазы роста (гейт nim_lt): среднее годовых ЧПМ упр. базиса модальной клетки. У
    ядра — годовой ряд клетки annual.nim (базис движка, П§2 grid) за те же годы, через мост. Допуск — как у
    отношений строк ОПУ и баланса (М§17: ≤ 0,3 п.п.)."""
    cc = run.cell(*ctl["central"]["cell"])
    series, years = getattr(cc, "annual", None), getattr(cc, "years", None)
    vals = []
    if series is not None and years is not None and "nim" in series:
        vals = [series["nim"][i] for i, y in enumerate(years) if y in margin["by_year"]]
    if len(vals) != len(margin["by_year"]) or any(v is None for v in vals):
        return _missing(MARGIN_WORDS, U_PCT, margin["value"])
    core_v = sum(cm.c_to_mgmt(ctl["ctx"]["A"], "nim", v) for v in vals) / len(vals)
    return _row(MARGIN_WORDS, U_PCT, core_v, margin["value"], TOL_RATIO, ABS, group="gate")


def all_rows(run, ctl) -> list[dict]:
    """Все строки сверки М§17 (формат строки — _row; метки клетки, года и квартала — _mark)."""
    rows = []
    tr_c = run.ctx.transmission
    tr = ctl["transmission"]
    LINE_TITLES, BOOK_TITLES = line_titles(ctl["ctx"]["B"]), book_titles(ctl["ctx"]["B"])
    derived = [("передача: сдвиг спредов активов σ0", U_PP, getattr(tr_c, "sigma0", None), tr["sigma0"]),
               ("передача: сдвиг стоимости пассивов σ0", U_PP, getattr(tr_c, "sigma0_liab", None), tr["sigma0_liab"]),
               ("передача: сжатие спреда φ", U_NUM, getattr(tr_c, "phi", None), tr["phi"]),
               ("передача: сжатие φ на спредах кредитных книг", U_NUM, getattr(tr_c, "phi_assets", None),
                tr["phi_assets"]),
               ("передача: добавка сжатия φ к стоимости средств клиентов", U_NUM, getattr(tr_c, "phi_liab", None),
                tr["phi_liab"]),
               ("передача: реализованная M − N", U_NUM, getattr(tr_c, "t_real", None), tr["t_real"])]
    for w, v in tr["t_local"].items():
        derived.append((f"передача: локальная в мире {w}", U_NUM, tr_c.t_local.get(w), v))
    for what, unit, core_v, ctl_v in derived:
        rows.append(_missing(what, unit, ctl_v) if core_v is None
                    else _row(what, unit, core_v, ctl_v, TOL_DERIVED, ABS, group="derived"))
    # парные передачи и ROE-эквивалент (М§4.5, §17): аналитические, одно определение — до 1e-6
    pairs_c = getattr(tr_c, "pairs", None)
    for k, v in tr["pairs"].items():
        what = "передача: пара миров " + " → ".join(k.split("_"))
        if pairs_c is None or k not in pairs_c:
            rows.append(_missing(what, U_NUM, v))
        elif pairs_c[k] is None or v is None:                       # равные key^LT — пара не определена
            rows.append(_row(what, U_NUM, pairs_c[k], v, TOL_DERIVED, ABS, group="derived",
                             ok=pairs_c[k] is None and v is None))
        else:
            rows.append(_row(what, U_NUM, pairs_c[k], v, TOL_DERIVED, ABS, group="derived"))
    roe_c = getattr(tr_c, "roe_equiv", None)
    what = "передача: эквивалент в ROE"
    rows.append(_missing(what, U_NUM, tr["roe_equiv"]) if roe_c is None
                else _row(what, U_NUM, roe_c, tr["roe_equiv"], TOL_DERIVED, ABS, group="derived"))
    spreads_c = getattr(tr_c, "lt_spread", None)
    for b, per_world in tr["lt_spread"].items():
        for w, v in per_world.items():
            what = f"эффективный долгосрочный спред к опоре: {BOOK_TITLES.get(b, b)}, мир {w}"
            core_v = None if spreads_c is None else spreads_c.get(b, {}).get(w)
            rows.append(_missing(what, U_PP, v) if core_v is None
                        else _row(what, U_PP, core_v, v, TOL_DERIVED, ABS, group="lt_spread"))
    margin_c = getattr(tr_c, "loan_margin", None)
    for w, v in tr["loan_margin"].items():
        what = f"кредитная маржа стационара, мир {w}"
        core_v = None if margin_c is None else margin_c.get(w)
        rows.append(_missing(what, U_PP, v) if core_v is None
                    else _row(what, U_PP, core_v, v, TOL_DERIVED, ABS, group="derived"))
    for name in cm.LAYERS:
        rows.append(_row(f"V0 слоя «{LAYER_TITLES[name]}»", U_BN, run.layers[name].v0, ctl["layers"][name]["v0"],
                         TOL_VALUE, REL, group="value"))
    for name, core_v, ctl_v in (("низ", run.low, ctl["low"]), ("верх", run.high, ctl["high"]),
                                ("точка при λ книги", run.point, ctl["point"])):
        rows.append(_row(f"цена: {name}", U_RUB, core_v, ctl_v, TOL_VALUE, REL, group="value"))
    rows.append(_bridge_row("мост объявленных дивидендов", run.bridge_amount, ctl["bridge_amount"]))
    rows.append(_bridge_row("объявленный дивиденд до вычета из капитала модели",
                            getattr(run, "pending_dividend", None), ctl["pending_amount"]))
    margin = cm.c_printed_margin(ctl)
    if margin is not None:                                          # строка есть только у книги с ключом checks.nim_lt
        rows.append(margin_row(run, ctl, margin))
    qidx = _quarter_index(ctl)
    per_share = 1000.0 / ctl["ctx"]["A"]["N_out"]
    for c in ctl["cells"]:
        key = (c["world"], c["regime"], c["scenario"])
        cc = run.cell(*key)
        tag = "/".join(key)
        i_cell = len(rows)
        cut_rwa = cut_quarters(c, cc) if ctl["quarterly"] else {}
        rows.append(_row(f"стоимость клетки {tag}", U_BN, cc.v_ri, c["v_ri"], TOL_VALUE, REL, group="cell",
                         tol_abs=VALUE_FLOOR_BV * abs(c["bv_v"])))
        for name, grp, core_v, ctl_v in (("ROE терминала", "roe_t", cc.roe_t, c["roe_t"]),
                                         ("плата за капитал на терминале", "k_t", cc.k_t, c["k_t"]),
                                         ("рост терминала", "g_t", cc.g_t, c["g_t"])):
            rows.append(_row(f"{name}, клетка {tag}", U_PCT, core_v, ctl_v, TOL_RATIO, ABS, group=grp))
        rwa_q = c["rows"][-1]["rwa"]
        rows.append(_row(f"избыток капитала на терминале, клетка {tag}", U_BN, cc.x_t, c["x_t"],
                         TOL_RATIO * rwa_q, ABS, group="x_t"))
        # доход на избыток (М§7, §17) — строка ОПУ терминального года; поле ядра — договор INTERFACES §4.3
        yx_core = getattr(cc, "y_x", None)
        what = f"доход на избыток капитала на терминале, клетка {tag}"
        rows.append(_missing(what, U_BN, c["y_x"]) if yx_core is None
                    else _row(what, U_BN, yx_core, c["y_x"], TOL_LINE, REL, group="y_x",
                              tol_abs=TOL_RATIO * rwa_q * abs(c["y_bal"])))
        q = cc.quarters
        # TV сверяется в форме DDM (капитал на T): TV_DDM = BV_Q + TV_RI (М§7). Сам TV_RI — малая
        # разность, усиленная 1/(k_T − g_T): 0,1 п.п. ROE_T даёт у мира M ≈ 5 % TV_RI.
        if "bv" in q and q["bv"][-1] is not None:
            rows.append(_row(f"терминальная стоимость с капиталом, клетка {tag}", U_BN, q["bv"][-1] + cc.tv_ri,
                             c["rows"][-1]["bv"] + c["tv_ri"], TOL_VALUE, REL, group="tv"))
        for line in FLOW_LINES + STOCK_LINES + RATIO_LINES + ("div",):
            if line not in q:
                rows.append(_missing(f"{LINE_TITLES[line]}, клетка {tag}", U_PCT if line in RATIO_LINES else U_BN))
        for i, p in enumerate(ctl["ctx"]["periods"]):
            r = c["rows"][i]
            ids = qidx[p["year"]]
            bv_scale = abs(r["bv"])
            i_year = len(rows)
            for line in FLOW_LINES + ("div",):
                if line not in q:
                    continue
                what = f"{LINE_TITLES[line]} {p['year']}, клетка {tag}"
                vals = [q[line][j] for j in ids]
                if any(v is None for v in vals):
                    rows.append(_missing(what, U_BN, r[line]))
                    continue
                core_v, ctl_v = sum(vals), r[line]
                if line in ABS_LINES:
                    core_v, ctl_v = abs(core_v), abs(ctl_v)
                floor = (TOL_SMALL_BV * bv_scale if line in SMALL_BV_LINES
                         else DIV_FLOOR_BV * bv_scale if line == "div" else None)
                row = _row(what, U_BN, core_v, ctl_v, TOL_LINE, REL, group=line, tol_abs=floor)
                rows.append(_cut_floor(row, cut_rwa, ids) if line == "div" else row)
            j_end = ids[-1]
            for line in STOCK_LINES:
                if line in q and q[line][j_end] is not None:
                    rows.append(_row(f"{LINE_TITLES[line]} на конец {p['year']}, клетка {tag}", U_BN,
                                     q[line][j_end], r[line], TOL_LINE, REL, group=line))
            for line in RATIO_LINES:
                if line in q and q[line][j_end] is not None:
                    rows.append(_row(f"{LINE_TITLES[line]} на конец {p['year']}, клетка {tag}", U_PCT,
                                     q[line][j_end], r[line], TOL_RATIO, ABS, group=line))
            _mark(rows, i_year, year=p["year"])
        for yp, d in c["decisions"].items():
            what = f"DPS за {yp}, клетка {tag}"
            i_dps = len(rows)
            core_dps = cc.dps.get(yp) if hasattr(cc.dps, "get") else None
            if core_dps is None:
                rows.append(_missing(what, U_RUB, d["dps"]))
                continue
            row = _row(what, U_RUB, core_dps, d["dps"], TOL_LINE, REL, group="dps", tol_abs=dps_floor(ctl, c, yp))
            decided = [x["q"] for x in d.get("quarters", {}).values()]
            rows.append(_cut_floor(row, cut_rwa, decided, per_share))
            _mark(rows, i_dps, year=d.get("decision_year", yp + 1))
        if ctl["quarterly"]:
            rows.extend(_quarterly_rows(ctl, c, cc, tag, qidx, cut_rwa))
        if ctl["ctx"].get("book_rel") is not None:             # строки есть только у книги с ключом credit.book_relative
            rows.extend(cor_mix0_rows(ctl, c, cc, tag, qidx))
        if ctl["ctx"].get("opex_w") is not None or ctl["ctx"].get("line_shares") is not None:
            rows.extend(opex_volume_rows(ctl, c, cc, tag, qidx))   # веса М13 или смесь расходов К2
        if "terminal_fixed" in c:                                # блок постоянных частей терминала (λ_F < 1)
            rows.extend(terminal_fixed_rows(c, cc, tag))
        if ctl["ctx"].get("bb") is not None:                     # строки есть только у книги с включённым выкупом
            rows.extend(buyback_rows(ctl, c, cc, tag, qidx, LINE_TITLES))
        rows.extend(pass2_rows(ctl, c, cc, tag, qidx))           # ключи второго прохода — только у книги с ключом
        rows.extend(pass3_rows(ctl, c, cc, tag, qidx))           # ключи третьего прохода — только у книги с ключом
        _mark(rows, i_cell, cell=tag)
    if cm.c_kappa_world(ctl["ctx"]["B"]) is not None:           # строки есть только у книги с ключом мира-опоры κ
        rows.extend(kappa_spread_rows(run, ctl))
    return rows


def compare_with_core(run, ctl) -> list[dict]:
    """Строки сверки М§17, которые судятся: все строки (all_rows) за вычетом строк у порога дискретных решений (правило
    ПОРОГ, Р4-16); если правило съедает сверку (доля исключённых строк клеток больше 10 % или вся группа строк) —
    строка-сторож вне допуска."""
    return reconcile(run, ctl)[0]


def reconcile(run, ctl) -> tuple[list[dict], dict]:
    """Сверка М§17 с правилом ПОРОГ: (строки, которые судятся, отчёт об исключённых у порога)."""
    rows = all_rows(run, ctl)
    rules = threshold_rules(run, ctl)
    return apply_threshold(rows, rules, run, ctl)


def buyback_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict, titles: dict) -> list[dict]:
    """Выкуп по цене мира (ключ dividends.buyback, М3): акции клетки на конец сетки N_T (≤ 0,1 %), цена клетки на
    оставшуюся акцию S_c (как оценка клетки: ≤ 3 % или 0,5 % BV_v на акцию), выкуп за год (≤ 1e-9 млрд ₽ — обе модели
    читают одну траекторию книги). У ядра — поля клетки n_t, s_price и квартальный ряд bb."""
    rows = []
    bv_floor = VALUE_FLOOR_BV * abs(c["bv_v"]) * 1000.0 / ctl["ctx"]["A"]["N_out"]
    for name, field, unit, tol, kind, floor in (
            ("акции в обращении на конец сетки", "n_t", U_NUM, TOL_SHARES, REL, None),
            ("цена клетки на оставшуюся акцию", "s_price", U_RUB, TOL_VALUE, REL, bv_floor)):
        what = f"{name}, клетка {tag}"
        core_v = getattr(cc, field, None)
        rows.append(_missing(what, unit, c[field]) if core_v is None
                    else _row(what, unit, core_v, c[field], tol, kind, group=f"bb_{field}", tol_abs=floor))
    series = (getattr(cc, "quarters", None) or {}).get("bb")
    for i, p in enumerate(ctl["ctx"]["periods"]):
        what = f"{titles[BUYBACK_LINE]} {p['year']}, клетка {tag}"
        vals = None if series is None else [series[j] for j in qidx[p["year"]]]
        if vals is None or any(v is None for v in vals):
            rows.append(_missing(what, U_BN, c["rows"][i]["bb"]))
        else:
            rows.append(_row(what, U_BN, sum(vals), c["rows"][i]["bb"], TOL_BUYBACK_BN, ABS, group="bb"))
        _mark(rows, len(rows) - 1, year=p["year"])
    return rows


def pass2_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict) -> list[dict]:
    """Строки ключей второго прохода ядра Совкомбанка (core-pass2) — только у книги с ключом. К3 (структурная доля опта,
    volumes.wholesale_structural_to_funds): опт конца года — квартальный ряд ядра wholesale, ≤ 10 % (как остатки BV и
    RWA). К7 (резерв по книгам, credit.allowance_by_book): резерв конца года — ряд ядра allowance по модулю (знак
    хранения у ядра свой), ≤ 2 %: резерв по книгам сдвигает его на проценты, и допуск строк (10 %) их не различил бы.
    К5 (RWA гарантий, capital.rwa.guarantees): составляющая гарантий конца года G × дрейф × валютный индекс × множитель
    режима — ряд ядра rwa_guar, ≤ 1 % или 0,5 млрд ₽ (её доля в RWA — проценты, допуск RWA в 10 % её не различил бы).
    К4 (терминал от стационарных ставок, valuation.terminal.stationary_rates): ΔNII*_L — узел клетки ядра
    terminal_stationary (поле d_nii_l), ≤ 10 % или 0,5 млрд ₽; ROE_T и TV — прежними строками. К2 (своя база
    строки): рост базы комиссий и страхования за год — ряды ядра vol_fees, vol_ins (как vol_opex у М13), ≤ 0,5 п.п.
    К6 (книга-обязательство за драйвером, volumes.liability_drivers): остаток ведомой книги конца года — ряд остатка
    книги ядра books.<b>.balance, ≤ 2 % (книга — доли процента пассивов, допуск строк её не различил бы)."""
    ctx = ctl["ctx"]
    q = getattr(cc, "quarters", None) or {}
    rows = []
    if ctx.get("min_dps") is not None:
        rows.extend(token_rows(ctl, c, cc, tag))
    if ctx.get("stationary"):
        what = f"{STAT_WORDS}, клетка {tag}"
        node = getattr(cc, "terminal_stationary", None) or getattr(cc, "stationary", None)
        core_v, ctl_v = core_field(node, "d_nii_l"), c["terminal_stationary"]["d_nii_l"]
        rows.append(_missing(what, U_BN, ctl_v) if core_v is None
                    else _row(what, U_BN, core_v, ctl_v, TOL_STAT_REL, REL, group="d_nii_l", tol_abs=TOL_STAT_BN))
    for line, words in LINE_VOLUME_WORDS.items():
        if (ctx.get("line_base") or {}).get(line) is not None:
            rows.extend(line_volume_rows(ctl, c, cc, tag, qidx, line, words))
    for i, p in enumerate(ctx["periods"]):
        r, j_end = c["rows"][i], qidx[p["year"]][-1]
        i_year = len(rows)
        if ctx.get("wtf_key"):
            what = f"{WHOLESALE_WORDS} на конец {p['year']}, клетка {tag}"
            core_v = q["wholesale"][j_end] if "wholesale" in q else None
            rows.append(_missing(what, U_BN, r["wholesale"]) if core_v is None
                        else _row(what, U_BN, core_v, r["wholesale"], TOL_LINE, REL, group="wholesale"))
        for b in ctx.get("driven") or {}:
            what = f"{DRIVEN_WORDS} ({_driven_title(ctl, b)}) на конец {p['year']}, клетка {tag}"
            node = core_field(getattr(cc, "books", None), b)
            series = core_field(node, "balance")
            core_v = series[j_end] if series is not None and series[j_end] is not None else None
            rows.append(_missing(what, U_BN, r["driven_end"][b]) if core_v is None
                        else _row(what, U_BN, core_v, r["driven_end"][b], TOL_DRIVEN, REL, group="driven"))
        if ctx.get("allow") is not None:
            what = f"{ALLOWANCE_WORDS} на конец {p['year']}, клетка {tag}"
            core_v = q["allowance"][j_end] if "allowance" in q and q["allowance"][j_end] is not None else None
            rows.append(_missing(what, U_BN, r["al"]) if core_v is None
                        else _row(what, U_BN, abs(core_v), abs(r["al"]), TOL_ALLOWANCE, REL, group="allowance"))
        if ctx.get("guar") is not None:
            what = f"{GUAR_WORDS} на конец {p['year']}, клетка {tag}"
            core_v = q["rwa_guar"][j_end] if "rwa_guar" in q and q["rwa_guar"][j_end] is not None else None
            rows.append(_missing(what, U_BN, r["rwa_guar"]) if core_v is None
                        else _row(what, U_BN, core_v, r["rwa_guar"], TOL_GUAR_REL, REL, group="rwa_guar",
                                  tol_abs=TOL_GUAR_BN))
        _mark(rows, i_year, year=p["year"])
    return rows


def token_rows(ctl: dict, c: dict, cc, tag: str) -> list[dict]:
    """Жетон DPS (К1, dividends.min_dps): признак «жетон уплачен» по годам прибыли — у ядра поле token решений клетки
    (decisions; год — по кварталу прибыли period), у контрольной модели — жетон решения-носителя. Признак совпадает,
    кроме клетки у порога: |H_fl − Σ базового дивиденда модели − need| ≤ 0,3 п.п. × RWA квартала решения у контрольной
    модели (как допуск норматива). При совпавшем «уплачен», без догоняющей выплаты и избытка у контрольной модели и
    жетоне, не урезанном прибылью (m_Y = min_dps года), DPS года у ядра — min_dps до 1e-9 ₽ (у контрольной модели это
    держит тест прохода)."""
    rows = []
    decs = getattr(cc, "decisions", None)
    theirs, known = {}, False
    for d in decs or ():
        tok = getattr(d, "token", None)
        if tok is None:
            continue
        known = True
        per = getattr(d, "period", None)
        year = cm.c_per_parse(per)[0] if per else getattr(d, "year", None)
        theirs[year] = theirs.get(year, False) or tok > 0.0
    rwa = {x["q"]: x["rwa"] for r in c["rows"] for x in r["quarters"]}
    traj = ctl["ctx"]["min_dps"]
    for d in c["decisions_q"]:
        if "token_rule" not in d:
            continue
        rule, year = d["token_rule"], d["year"]
        what = f"{TOKEN_WORDS} за {year}, клетка {tag}"
        mine = d["token"] > 0.0
        i_tok = len(rows)
        if not known:
            rows.append(_missing(what, U_NUM, float(mine)))
            _mark(rows, i_tok, q=d["q"], year=cm.c_qper(ctl["ctx"]["anchor"], d["q"])[0])
            continue
        core_v = bool(theirs.get(year, False))
        near = abs(rule["h_floor"] - rule["model_base"] - rule["need"]) <= TOL_RATIO * rwa[d["q"]]
        rows.append(_row(what, U_NUM, float(core_v), float(mine), 0.0, ABS, group="token",
                         ok=core_v == mine or near))
        year_row = c["decisions"].get(year)
        plain = year_row is not None and all(x["catch"] == 0.0 and x["excess"] == 0.0
                                             for x in year_row["quarters"].values())
        cap = cm.c_traj_mean(traj, year, range(1, cm.QY + 1))
        if core_v and mine and plain and rule["m_Y"] == cap:
            core_dps = cc.dps.get(year) if hasattr(cc.dps, "get") else None
            what = f"{TOKEN_DPS_WORDS} за {year}, клетка {tag}"
            rows.append(_missing(what, U_RUB, cap) if core_dps is None
                        else _row(what, U_RUB, core_dps, cap, TOL_ZERO_BN, ABS, group="token_dps"))
        _mark(rows, i_tok, q=d["q"], year=cm.c_qper(ctl["ctx"]["anchor"], d["q"])[0])
    return rows


def _book_titles_of(ctl: dict) -> dict:
    """Подписи книг сводки (meta.labels.control.books)."""
    return book_titles(ctl["ctx"]["B"])


def _driven_title(ctl: dict, b: str) -> str:
    """Подпись книги за драйвером строки (volumes.liability_drivers): кредитная — из meta.labels.control.books, книга
    пассива (подписей там нет — схема держит набор кредитных книг) — своё имя книги nii.books.<книга>.name со строчной
    буквы; ключ книги на экран не идёт (PAYLOAD §0.2)."""
    titles = _book_titles_of(ctl)
    if b in titles:
        return titles[b]
    name = str(cm.c_bget(ctl["ctx"]["B"], f"nii.books.{b}.name"))
    return name[:1].lower() + name[1:] if name[1:2].islower() else name


def line_volume_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict, line: str, words: str) -> list[dict]:
    """Рост своей базы строки за год (К2): у ядра — квартальный ряд vol_<строка> (сумма кварталов года к сумме тех же
    кварталов прошлого года), у контрольной модели — годовая форма. Год, у которого кварталы прошлого года лежат до
    сетки, держит строка комиссий или страхования (≤ 10 %). Допуск — 0,5 п.п., как у роста базы расходов М13."""
    series = (getattr(cc, "quarters", None) or {}).get(f"vol_{line}")
    rows = []
    for i, p in enumerate(ctl["ctx"]["periods"]):
        ids = qidx[p["year"]]
        prev = [j - cm.QY for j in ids]
        if min(prev) < 1:
            continue
        what = f"{words} {p['year']}, клетка {tag}"
        ctl_v = c["rows"][i][f"v_{line}"]
        vals = None if series is None else [series[j] for j in ids + prev]
        if vals is None or any(v is None for v in vals):
            rows.append(_missing(what, U_PCT, ctl_v))
        else:
            core_v = sum(series[j] for j in ids) / sum(series[j] for j in prev) - 1.0
            rows.append(_row(what, U_PCT, core_v, ctl_v, TOL_OPEX_VOLUME, ABS, group=f"v_{line}"))
        _mark(rows, len(rows) - 1, year=p["year"])
    return rows


def core_field(obj, name: str):
    """Поле узла ядра — атрибутом или ключом словаря; нет узла или поля — None."""
    if obj is None:
        return None
    if isinstance(obj, dict) or hasattr(obj, "keys"):
        return obj.get(name)
    return getattr(obj, name, None)


def terminal_fixed_rows(c: dict, cc, tag: str) -> list[dict]:
    """Блок постоянных в рублях частей терминала (ключ valuation.terminal.fixed_growth_share < 1, М§7): капитал
    постоянных частей F_K, их фондирование D_F и годовой доход стоящей доли I_F — у ядра узел клетки terminal_fixed
    (поля f_k, d_f, i_f), у контрольной модели — свой блок на годовой строке года L. Допуск — 1 % или 0,5 млрд ₽:
    блок двигает TV на проценты, и TV (3 %) его ошибку не различил бы."""
    node = getattr(cc, "terminal_fixed", None)
    rows = []
    for name, key in (("капитал постоянных частей на терминале", "f_k"),
                      ("фондирование постоянных частей балансирующими статьями", "d_f"),
                      ("годовой доход стоящей доли постоянных частей", "i_f")):
        what = f"{name}, клетка {tag}"
        core_v, ctl_v = core_field(node, key), c["terminal_fixed"][key]
        rows.append(_missing(what, U_BN, ctl_v) if core_v is None
                    else _row(what, U_BN, core_v, ctl_v, TOL_FIXED_REL, REL, group=f"terminal_{key}",
                              tol_abs=TOL_FIXED_BN))
    return rows


def opex_volume_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict) -> list[dict]:
    """Рост базы расходов, взвешенной по себестоимости книг (ключ opex.volume_weights, М§4.7), за год: у ядра — из
    квартального ряда vol_opex (сумма кварталов года к сумме тех же кварталов прошлого года; нормировка весов на
    отношение не влияет), у контрольной модели — годовая форма. Год, у которого кварталы прошлого года лежат до
    первого прогнозного квартала, сверяется строкой расходов (ряд ядра начинается с сетки). Допуск — 0,5 п.п."""
    series = (getattr(cc, "quarters", None) or {}).get("vol_opex")
    rows = []
    for i, p in enumerate(ctl["ctx"]["periods"]):
        ids = qidx[p["year"]]
        prev = [j - cm.QY for j in ids]
        if min(prev) < 1:
            continue
        what = f"{OPEX_VOLUME_WORDS} {p['year']}, клетка {tag}"
        ctl_v = c["rows"][i]["v_opex"]
        vals = None if series is None else [series[j] for j in ids + prev]
        if vals is None or any(v is None for v in vals):
            rows.append(_missing(what, U_PCT, ctl_v))
        else:
            core_v = sum(series[j] for j in ids) / sum(series[j] for j in prev) - 1.0
            rows.append(_row(what, U_PCT, core_v, ctl_v, TOL_OPEX_VOLUME, ABS, group="v_opex"))
        _mark(rows, len(rows) - 1, year=p["year"])
    return rows


def cor_mix0_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict) -> list[dict]:
    """CoR клетки на составе якоря (ключ credit.book_relative, М§4.6): у ядра — квартальный ряд cor_mix0 (путь
    режима + κ-добавка + отклонение A-P2u), среднее кварталов года по дням; у контрольной модели — CoR периода
    (среднее кварталов по дням). Допуск — 0,03 п.п.: множители книг меняют реализованную CoR на десятые доли
    п.п., и допуск отношений М§17 (0,3 п.п.) их бы не различил."""
    series = (getattr(cc, "quarters", None) or {}).get("cor_mix0")
    rows = []
    for i, p in enumerate(ctl["ctx"]["periods"]):
        r = c["rows"][i]
        what = f"{COR_MIX0_WORDS} {p['year']}, клетка {tag}"
        ids = qidx[p["year"]]
        vals = None if series is None else [series[j] for j in ids]
        if vals is None or any(v is None for v in vals):
            rows.append(_missing(what, U_PCT, r["cor_mix0"]))
        else:
            core_v = sum(v * d for v, d in zip(vals, r["days_q"])) / sum(r["days_q"])
            rows.append(_row(what, U_PCT, core_v, r["cor_mix0"], TOL_COR_MIX0, ABS, group="cor_mix0"))
        _mark(rows, len(rows) - 1, year=p["year"])
    return rows


def kappa_spread_rows(run, ctl) -> list[dict]:
    """κ-добавка мира (М§4.6): разность годовой CoR клетки мира и клетки мира-опоры κ того же режима и сценария —
    у ядра (годовой ряд клетки annual.cor) и у контрольной модели. Допуск — 0,03 п.п.: сама добавка — десятые
    доли п.п., и допуск отношений М§17 (0,3 п.п.) её бы не различил. Мир-опора — ключ книги
    credit.kappa_reference_world, без ключа — мир N."""
    ref = cm.c_kappa_world(ctl["ctx"]["B"]) or cm.W_LOW
    rows = []
    for c in ctl["cells"]:
        if c["world"] == ref:
            continue
        tag = "/".join((c["world"], c["regime"], c["scenario"]))
        base = cm.c_cell_of(ctl, ref, c["regime"], c["scenario"])
        theirs = [getattr(run.cell(w, c["regime"], c["scenario"]), "annual", None) for w in (c["world"], ref)]
        years = getattr(run.cell(*(c["world"], c["regime"], c["scenario"])), "years", None) or ()
        for y, mine, home in zip(ctl["years"], c["rows"], base["rows"]):
            if mine["cor_year"] is None:
                continue                                # неполный год якоря годовой метрики не несёт
            what = f"стоимость риска к миру-опоре {y}, клетка {tag}"
            ctl_v = mine["cor_year"] - home["cor_year"]
            if y not in years or any(a is None or "cor" not in a or a["cor"][years.index(y)] is None for a in theirs):
                rows.append(_missing(what, U_PP, ctl_v))
                continue
            core_v = abs(theirs[0]["cor"][years.index(y)]) - abs(theirs[1]["cor"][years.index(y)])
            rows.append(_row(what, U_PP, core_v, ctl_v, TOL_KAPPA_SPREAD, ABS, group="kappa"))
    return rows


def _quarterly_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict, cut_rwa: dict) -> list[dict]:
    """Строки ветви с квартальным проходом капитала (М§17): DPS кварталов прибыли, требование с глиссадой
    на конец года, рост кредитных книг — потенциальный и фактический, доля урезанного роста."""
    rows = []
    n_out = ctl["ctx"]["A"]["N_out"]
    dps_q = getattr(cc, "dps_q", None)
    for d in c["decisions_q"]:
        what = f"DPS за квартал {d['period']}, клетка {tag}"
        core_v = dps_q.get(d["period"]) if hasattr(dps_q, "get") else None
        year = cm.c_qper(ctl["ctx"]["anchor"], d["q"])[0]
        floor = DPS_Q_FLOOR_BV * abs(c["rows"][ctl["years"].index(year)]["bv"]) * 1000.0 / n_out
        if core_v is None:
            rows.append(_missing(what, U_RUB, d["dps"]))
        else:
            row = _row(what, U_RUB, core_v, d["dps"], TOL_LINE, REL, group="dps_q", tol_abs=floor)
            rows.append(_cut_floor(row, cut_rwa, [d["q"]], 1000.0 / n_out))
        _mark(rows, len(rows) - 1, q=d["q"], year=year)
    q = cc.quarters
    growth = getattr(cc, "growth", None)
    for i, p in enumerate(ctl["ctx"]["periods"]):
        r, j_end = c["rows"][i], qidx[p["year"]][-1]
        i_year = len(rows)
        for name, key in (("требование Н20.0 с глиссадой", "req20_glide"), ("требование Н20.1 с глиссадой", "req11_glide")):
            what = f"{name} на конец {p['year']}, клетка {tag}"
            rows.append(_missing(what, U_PCT, r[key]) if key not in q or q[key][j_end] is None
                        else _row(what, U_PCT, q[key][j_end], r[key], TOL_DERIVED, ABS, group="glide"))
        for name, key, ctl_v, tol, grp in (
                ("потенциальный рост кредитных книг", "potential", r["growth_potential"], TOL_DERIVED, "growth_potential"),
                ("фактический рост кредитных книг", "actual", r["growth_actual"], TOL_GROWTH, "growth_actual"),
                ("доля урезанного роста", "cut_share", r["cut_share"], TOL_CUT_SHARE, "cut_share")):
            what = f"{name} за {p['year']}, клетка {tag}"
            core_v = growth[key][i] if growth is not None and key in growth else None
            if core_v is None and ctl_v is None:
                continue                                # за год якоря без факта конца прошлого года значения нет
            rows.append(_missing(what, U_PCT, ctl_v) if core_v is None or ctl_v is None
                        else _row(what, U_PCT, core_v, ctl_v, tol, ABS, group=grp))
        _mark(rows, i_year, year=p["year"])
    return rows


def pass3_rows(ctl: dict, c: dict, cc, tag: str, qidx: dict) -> list[dict]:
    """Строки ключей третьего прохода ядра Совкомбанка (core-pass3) — только у книги с ключом. К-Т2а (год терминала
    «средний год», valuation.terminal.year_basis): поправка PBT_L года терминала (ν_L − 1)(дневные строки + ΔNII*_L) — у
    ядра узел клетки terminal_year (поле adj), ≤ 10 % или 0,5 млрд ₽. К-Т2в (valuation.terminal.fade_anchor_year):
    множитель угасания по календарю φ_W — узел terminal_fade (поле phi), ≤ 1e-6. К-Т2б (valuation.terminal.fixed_funding:
    balancing): признак «минимум связан после выплаты избытка» — поле узла terminal_fixed bound_after_payout, совпадает
    (у порога — правило ПОРОГ); F_K, D_F, I_F — прежними строками блока. К8 (volumes.cash_assets): деньги конца года —
    квартальный ряд ядра cash, ≤ 2 % (как ведомая книга К6)."""
    rows = []
    year = c.get("terminal_year")
    if year is not None:
        what = f"{YEAR_WORDS}, клетка {tag}"
        core_v = core_field(getattr(cc, "terminal_year", None), "adj")
        rows.append(_missing(what, U_BN, year["adj"]) if core_v is None
                    else _row(what, U_BN, core_v, year["adj"], TOL_YEAR_REL, REL, group="terminal_year",
                              tol_abs=TOL_YEAR_BN))
    fade = c.get("terminal_fade")
    if fade is not None:
        what = f"{FADE_WORDS}, клетка {tag}"
        core_v = core_field(getattr(cc, "terminal_fade", None), "phi")
        rows.append(_missing(what, U_NUM, fade["phi"]) if core_v is None
                    else _row(what, U_NUM, core_v, fade["phi"], TOL_PHI, ABS, group="terminal_fade"))
    fixed = c.get("terminal_fixed") or {}
    if "bound_after_payout" in fixed:
        what = f"{BOUND_WORDS}, клетка {tag}"
        mine = float(bool(fixed["bound_after_payout"]))
        core_v = core_field(getattr(cc, "terminal_fixed", None), "bound_after_payout")
        rows.append(_missing(what, U_NUM, mine) if core_v is None
                    else _row(what, U_NUM, float(bool(core_v)), mine, 0.0, ABS, group="bound"))
    if ctl["ctx"].get("cash") is not None:
        q = getattr(cc, "quarters", None) or {}
        for i, p in enumerate(ctl["ctx"]["periods"]):
            r, j_end = c["rows"][i], qidx[p["year"]][-1]
            what = f"{CASH_WORDS} на конец {p['year']}, клетка {tag}"
            core_v = q["cash"][j_end] if "cash" in q and q["cash"][j_end] is not None else None
            rows.append(_missing(what, U_BN, r["cash"]) if core_v is None
                        else _row(what, U_BN, core_v, r["cash"], TOL_CASH, REL, group="cash"))
            _mark(rows, len(rows) - 1, year=p["year"])
    return rows


# ============================================================================ правило ПОРОГ (Р4-16)


def _core_year_of(d) -> int | None:
    """Год прибыли решения ядра: по кварталу прибыли period, иначе поле year."""
    per = getattr(d, "period", None)
    return cm.c_per_parse(per)[0] if per else getattr(d, "year", None)


def threshold_rules(run, ctl) -> list[dict]:
    """Решения у порога (правило ПОРОГ, решения № 4, Р4-16). Дискретное решение — у порога, если исходы моделей разные,
    а его величина z хотя бы у одной модели в пределах ε = 0,3 п.п. × RWA квартала решения (у своей модели):

    * жетон DPS (К1): z = H_fl − Σ base_div модели квартала − need (ядро: headroom_floor, base_div решений квартала,
      need — жетон ядра, если уплачен, иначе need контроля); и случай need → 0: need ≤ ε у модели;
    * ступень политики (годовой календарь): z = H − base_div выбранной ступени;
    * выплата избытка: z = запас при итоговых объёмах H_fin (headroom_final);
    * связанность минимума после выплаты избытка (К-Т2б): z = WT* до обрезки нулём; ε — 0,3 п.п. × RWA_Q;
    * урезание роста: z = N_j − req*_j в квартале; у модели, урезавшей рост (λ* < 1), норматив стоит на req* — z в
      пределах ε по построению. Исход года — «урезан» (наименьшая доля прироста года меньше 1) или нет; год, где исходы
      моделей разные, — у порога, и строки за λ исключаются с этого года (уровни RWA гарантий, опта, ведомой книги,
      денег несут разрыв пути кредитов дальше). Годы, где урезали обе модели, строк не исключают: обе ставят норматив
      на req*, и строки за λ сравнимы (на книге p3 и в восьми сценариях сверки — в допусках). Нет ряда lam_min у
      ядра — исход ядра неизвестен, строки судятся.

    Решение с одинаковым исходом у обеих моделей строк не исключает: скачка нет, строки сравнимы. Разный исход вне ε —
    находка: строки судятся. Возвращает правила исключения: клетка, причина, квартал или год, z обеих моделей, ε, группы."""
    out = []
    ctx = ctl["ctx"]
    anchor = ctx["anchor"]
    for c in ctl["cells"]:
        key = (c["world"], c["regime"], c["scenario"])
        tag = "/".join(key)
        cc = run.cell(*key)
        decs = list(getattr(cc, "decisions", None) or ())
        rwa_ctl = {x["q"]: x["rwa"] for r in c["rows"] for x in r.get("quarters", ())}
        core_rwa = (getattr(cc, "quarters", None) or {}).get("rwa")

        def eps_of(k, theirs=False):
            if theirs and core_rwa is not None and k < len(core_rwa) and core_rwa[k] is not None:
                return EPS_THRESHOLD * core_rwa[k]
            return EPS_THRESHOLD * rwa_ctl[k]

        def rule(reason, *, q=None, year=None, years=None, z_core=None, z_ctl=None, eps=None, groups, whole=()):
            out.append({"cell": tag, "reason": reason, "q": q, "year": year, "years": years,
                        "from": (f"{cm.c_qper(anchor, q)[0]}Q{cm.c_qper(anchor, q)[1]}" if q is not None
                                 else "T" if year is None and years is None else year if years is None
                                 else sorted(years)),
                        "z_core": z_core, "z_control": z_ctl, "eps": eps, "groups": tuple(groups), "whole": tuple(whole)})

        for d in c.get("decisions_q", ()):
            k = d["q"]
            if "token_rule" in d:                                       # жетон DPS (К1)
                tok = d["token_rule"]
                year_dec = [x for x in decs if getattr(x, "token", None) is not None and _core_year_of(x) == d["year"]]
                theirs = any((getattr(x, "token", 0.0) or 0.0) > 0.0 for x in year_dec)
                if theirs != (d["token"] > 0.0):
                    z_ctl = tok["h_floor"] - tok["model_base"] - tok["need"]
                    carrier = [x for x in year_dec if getattr(x, "headroom_floor", None) is not None]
                    z_core = need_core = None
                    if theirs:
                        need_core = max((getattr(x, "token", 0.0) or 0.0) for x in year_dec)
                    if carrier:
                        x = carrier[-1]
                        base_core = sum(getattr(y, "base_div", 0.0) or 0.0 for y in decs
                                        if getattr(y, "q", None) == x.q and getattr(y, "source", None) == "model")
                        z_core = x.headroom_floor - base_core - (need_core if need_core else tok["need"])
                    e_ctl, e_core = eps_of(k), eps_of(k, True)
                    near = (abs(z_ctl) <= e_ctl or (z_core is not None and abs(z_core) <= e_core)
                            or tok["need"] <= e_ctl or (need_core is not None and need_core <= e_core))
                    if near:
                        rule("token", q=k, year=cm.c_qper(anchor, k)[0], z_core=z_core, z_ctl=z_ctl, eps=e_ctl,
                             groups=DISCRETE_DATED, whole=DISCRETE_WHOLE)
            if d.get("source") == "policy" and d.get("h") == cm.QY and cm.c_excess_share(ctx["B"], d["year"]) > 0.0:
                theirs = [x for x in decs if getattr(x, "period", None) == d["period"]]
                excess_core = getattr(theirs[0], "excess", None) if theirs else None     # нет поля — исход неизвестен
                if excess_core is not None and (excess_core > 0.0) != (d["excess"] > 0.0):
                    z_ctl, z_core = d["headroom_final"], getattr(theirs[0], "headroom_final", None)
                    e_ctl, e_core = eps_of(k), eps_of(k, True)
                    if abs(z_ctl) <= e_ctl or (z_core is not None and abs(z_core) <= e_core):
                        rule("excess_payout", q=k, year=cm.c_qper(anchor, k)[0], z_core=z_core, z_ctl=z_ctl,
                             eps=e_ctl, groups=DISCRETE_DATED, whole=DISCRETE_WHOLE)
        if not ctl["quarterly"]:
            for yp, d in c["decisions"].items():                       # ступень политики (годовой календарь)
                theirs = [x for x in (getattr(cc, "decisions", None) or ()) if getattr(x, "year", None) == yp]
                if d.get("kind") != "policy" or not theirs or getattr(theirs[0], "step", d["step"]) == d["step"]:
                    continue
                y_dec = yp + 1
                rwa = c["rows"][ctl["years"].index(y_dec)]["rwa"] if y_dec in ctl["years"] else c["rows"][-1]["rwa"]
                z_ctl = d["H"] - d["base_div"]
                if abs(z_ctl) <= EPS_THRESHOLD * rwa:
                    rule("policy_step", year=y_dec, z_ctl=z_ctl, eps=EPS_THRESHOLD * rwa, groups=DISCRETE_DATED,
                         whole=DISCRETE_WHOLE)
        fixed = c.get("terminal_fixed") or {}
        if "bound_after_payout" in fixed:                               # связанность после выплаты (К-Т2б)
            node = getattr(cc, "terminal_fixed", None)
            theirs = core_field(node, "bound_after_payout")
            if theirs is not None and bool(theirs) != bool(fixed["bound_after_payout"]):
                wt_core = core_field(node, "wt_after")
                z_core = wt_core if theirs and wt_core is not None else None
                eps = EPS_THRESHOLD * c["rows"][-1]["rwa"]
                if abs(fixed["wt_z"]) <= eps or (z_core is not None and abs(z_core) <= eps):
                    rule("bound_after_payout", z_core=z_core, z_ctl=fixed["wt_z"], eps=eps, groups=(),
                         whole=TERMINAL_WHOLE)
        if ctl["quarterly"] and ctl.get("growth_rule") is not None:     # урезание роста
            lam_core = (getattr(cc, "growth", None) or {}).get("lam_min")
            years = [] if lam_core is None else [
                p["year"] for i, p in enumerate(ctx["periods"])
                if lam_core[i] is not None and (c["rows"][i]["lam_min"] < 1.0) != (lam_core[i] < 1.0)]
            if years:
                rule("growth_cut", year=min(years), z_ctl=0.0, groups=LAMBDA_GROUPS)
    return out


def _rule_hits(rule: dict, row: dict) -> bool:
    """Строка row идёт за решением rule: та же клетка, группа правила; у решения в квартале — год (или квартал у
    строк с квартальной меткой) не раньше решения; у урезания роста — год из годов правила."""
    if row.get("cell") != rule["cell"]:
        return False
    if row["group"] in rule["whole"]:
        return True
    if row["group"] not in rule["groups"] or row.get("year") is None:
        return False
    if rule["years"] is not None:
        return row["year"] in rule["years"]
    if rule["q"] is not None and row.get("q") is not None:
        return row["q"] >= rule["q"]
    return row["year"] >= rule["year"]


def apply_threshold(rows: list[dict], rules: list[dict], run, ctl) -> tuple[list[dict], dict]:
    """Правило ПОРОГ над строками сверки: строки за решениями у порога не судятся. Отчёт — счётчики исключённых строк
    по причинам (строка — по первому правилу), клетки с z обеих моделей, доля исключённых строк клеток; оценки V_c
    исключённых клеток — рядом, без суда. Сторож: доля больше 10 % или исключена вся группа строк — строка вне
    допуска (правило не может съесть сверку; срабатывание — находка, не повод расширять ε)."""
    kept, cells_out = [], []
    counts = dict.fromkeys(THRESHOLD_REASONS, 0)
    hits = [0] * len(rules)
    excluded_groups: dict[str, int] = {}
    for r in rows:
        first = next((i for i, rule in enumerate(rules) if _rule_hits(rule, r)), None)
        if first is None:
            kept.append(r)
            continue
        hits[first] += 1
        counts[rules[first]["reason"]] += 1
        excluded_groups[r["group"]] = excluded_groups.get(r["group"], 0) + 1
    total_groups: dict[str, int] = {}
    for r in rows:
        total_groups[r["group"]] = total_groups.get(r["group"], 0) + 1
    n_cell = sum(1 for r in rows if r.get("cell") is not None)
    n_out = sum(hits)
    values = []
    for rule, n in zip(rules, hits):
        cells_out.append({"cell": rule["cell"], "reason": rule["reason"], "from": rule["from"],
                          "z_core": rule["z_core"], "z_control": rule["z_control"], "eps": rule["eps"], "rows": n})
        if rule["reason"] != "growth_cut" and n:
            w, rg, sc = rule["cell"].split("/")
            values.append({"cell": rule["cell"], "core": run.cell(w, rg, sc).v_ri,
                           "control": cm.c_cell_of(ctl, w, rg, sc)["v_ri"]})
    share = n_out / n_cell if n_cell else 0.0
    whole = sorted(g for g, n in excluded_groups.items() if n == total_groups[g])
    report = {**counts, "n_excluded": n_out, "n_cell_rows": n_cell, "share": share, "whole_groups": whole,
              "cells": cells_out, "values": values}
    if n_out:
        kept.append(_row(THRESHOLD_WORDS, U_PCT, 0.0, share, THRESHOLD_SHARE_MAX, ABS, group="threshold"))
        for g in whole:
            # судится хотя бы одна строка группы: ядро — строк группы, контроль — оставшихся, допуск — все кроме одной
            kept.append(_row(f"правило ПОРОГ: исключена вся группа строк {g}", U_NUM, float(total_groups[g]),
                             float(total_groups[g] - excluded_groups[g]), float(total_groups[g] - 1), ABS,
                             group="threshold"))
    return kept, report


# ============================================================================ класс Р6-9: годовая форма контроля в клетках урезанного роста

# строки за путём кредитов: рост баз строк, RWA гарантий, опт, ведомая книга, деньги (ПОРОГ, LAMBDA_GROUPS), резерв по
# книгам, стоимость и цена клетки; ROE терминала клетки (roe_t — решения ведущего № 7, Р7-7): доходность капитала последнего
# года сетки стоит на уровне кредитов и капитала конца сетки, то есть за тем же путём урезанного роста; на книге угла +1 с
# ключом К8 (круг 6, p3 @ 9993b80) — ROE_T M/downturn/schedule 3,03 % у ядра против 2,70 % у контроля (допуск 0,3 п.п.), при
# выключенном ограничении роста — 13,64 против 13,67 % (в допуске): известный класс Р6-9, а не новое расхождение
BEHIND_GROWTH = LAMBDA_GROUPS + ("allowance", "cell", "bb_s_price", "roe_t")


def growth_cut_class(run, ctl, rows: list[dict]) -> list[dict]:
    """Строки сверки вне допуска, которые НЕ объясняет класс Р6-9 (годовая форма контроля в клетках урезанного роста,
    решения ведущего № 6). Строка объяснена, если: у неё метка клетки; она идёт за путём кредитов (BEHIND_GROWTH); рост
    кредитов этой клетки урезан капиталом у обеих моделей (наименьшая доля прироста года меньше 1) в году строки или
    раньше (строка клетки без года — в каком-либо году); строки фактического роста и доли урезанного роста этой клетки —
    все в допусках М§17 (сам рост модели считают одинаково в допусках). Возвращает необъяснённые строки.

    Сверки М§17 на ядре судят этим правилом (медленный круг, Д16: «всё зелёное» — список известных красных CI не читает):
    строка вне допуска, не объяснённая классом, — провал; строки класса печатаются числом. Сторожа класса
    (`*_rows_off_are_the_growth_cut_class`) проверяют то же правило и вдобавок — что при выключенном ограничении роста у
    обеих моделей строки за путём кредитов в допусках."""
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        return []
    years = [p["year"] for p in ctl["ctx"]["periods"]]
    cut, growth_ok = {}, {}
    for c in ctl["cells"]:
        key = (c["world"], c["regime"], c["scenario"])
        lam_core = (getattr(run.cell(*key), "growth", None) or {}).get("lam_min")
        cut["/".join(key)] = {y for i, y in enumerate(years) if lam_core is not None and lam_core[i] is not None
                              and lam_core[i] < 1.0 and c["rows"][i]["lam_min"] < 1.0}
    for r in rows:
        if r.get("group") in ("growth_actual", "cut_share") and r.get("cell"):
            growth_ok[r["cell"]] = growth_ok.get(r["cell"], True) and r["ok"]
    stray = []
    for r in bad:
        tag, y = r.get("cell"), r.get("year")
        yrs = cut.get(tag, set())
        if not (tag is not None and r.get("group") in BEHIND_GROWTH and growth_ok.get(tag, False)
                and (any(x <= y for x in yrs) if y is not None else bool(yrs))):
            stray.append(r)
    return stray


def fail_off_rows(run, ctl, rows: list[dict]) -> None:
    """Провал сверки М§17 на ядре: строки вне допуска, не объяснённые классом Р6-9 (`growth_cut_class`)."""
    stray = growth_cut_class(run, ctl, rows)
    if stray:
        n_class = sum(1 for r in rows if not r["ok"]) - len(stray)
        pytest.fail(f"вне допусков М§17: {len(stray)} из {len(rows)} строк сверки (сверх {n_class} строк класса Р6-9)"
                    + chr(10) + _fail_lines(stray))


def exact_match(run, ctl) -> bool:
    """V0 всех слоёв совпали с ядром до 1e-9 — признак общего кода (М§17)."""
    return all(abs(ctl["layers"][n]["v0"] / run.layers[n].v0 - 1.0) <= EXACT for n in cm.LAYERS)


def _fail_lines(bad: list[dict]) -> str:
    return "\n".join(f"{r['what']}: ядро {r['core']}, контроль {r['control']}, допуск {r['tol']} ({r['tol_kind']}"
                     + (f", или {r['tol_abs']}" if "tol_abs" in r else "") + ")" for r in bad[:60])


@pytest.mark.ci_only
def test_control_matches_core_within_tolerances(control):
    """Вся сверка М§17 на машинной книге в допусках.

    ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 8, Р8-9; ops/expected_counts.json → known_failures): на книге p3 @ 48f3ca2
    вне допуска 3 строки RWA гарантий конца 2027 (M/downturn/mid и strict) и 2028 (strict) — класс урезанного роста
    Р6-9 (годовая форма контроля в клетках урезанного роста). Сторож класса —
    tests/test_control_pass6.py::test_p6_control_rows_off_are_the_growth_cut_class[book]: ядро 612,52 против 606,27 млрд ₽
    (1,03 % при допуске 1 % или 0,5 млрд ₽). Рост урезан капиталом у обеих моделей в 2026–2028 годах (наименьшая доля
    прироста 0); долю прироста кварталов контроль ищет на профиле прибыли годовой строки: фактический рост 2027 года у ядра
    1,03 %, у контроля 0,32 % (допуск 3 п.п.), кредиты юрлиц (драйвер гарантий) конца 2027 — 1 812,3 против 1 793,8 млрд ₽
    (−1,02 %); в strict 2028 год роста нет у обеих, разница переходит на конец 2028."""
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    fail_off_rows(run, control, compare_with_core(run, control))


@pytest.mark.ci_only
def test_stationary_margins_of_the_worlds_match_core(control):
    """Стационарные ЧПМ миров решения передачи (М§4.5) у ядра и у контрольной модели — одно определение, до
    1e-6. Из них берётся число гейта стационарной маржи (ключ checks.nim_stationary): стационарный ЧПМ мира
    через мост; сам гейт контрольная модель не считает — его вердикт выносит сборка."""
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    theirs = getattr(run.ctx.transmission, "nss", None)
    if theirs is None:
        pytest.fail("в решении передачи ядра нет стационарных ЧПМ миров (nss): сверять не с чем")
    mine = control["transmission"]["nss"]
    assert set(theirs) == set(mine)
    for w, v in mine.items():
        assert abs(theirs[w] - v) <= TOL_DERIVED, (w, theirs[w], v)
    spec = cm.c_bopt(control["ctx"]["B"], "checks.nim_stationary")
    if spec is not None:                                    # мир гейта — мир книги, и его маржа посчитана
        assert spec["world"] in mine


def core_gate(run, name: str):
    """Гейт ядра по имени функции model.grid.<name>(book, facts, live=None, *, run=None) на книге и фактах
    прогона. Нет функции — None и причина."""
    fn = getattr(importlib.import_module("model.grid"), name, None)
    if fn is None:
        return None, f"в ядре нет model.grid.{name}"
    return fn(run.ctx.book, run.ctx.facts, run=run), ""


def gate_rows(core: dict | None, ctl: dict) -> list[dict]:
    """Строки сверки чисел гейта знака объёмных эффектов (М§4.5, §14.2): сдвиг точки и сдвиги цен миров —
    |Δ| ≤ 3 % модуля числа ядра или ≤ 0,5 ₽; точки обеих сторон сравнения — как цена (≤ 3 %). core — словарь
    ядра (point, point_free, d_point, d_world); числа, которого у ядра нет, — строка «нет у ядра»."""
    core = core or {}
    rows = []
    for words, key in (("точка до снятия остановки кредита и поправок роста", "point"),
                       ("точка после снятия остановки кредита и поправок роста", "point_free")):
        what = f"{SIGN_WORDS}: {words}"
        rows.append(_missing(what, U_RUB, ctl[key]) if core.get(key) is None
                    else _row(what, U_RUB, core[key], ctl[key], TOL_VALUE, REL, group="gate"))
    shifts = [(f"{SIGN_WORDS}: сдвиг точки", core.get("d_point"), ctl["d_point"])]
    shifts += [(f"{SIGN_WORDS}: сдвиг цены мира {w}", (core.get("d_world") or {}).get(w), v)
               for w, v in ctl["d_world"].items()]
    for what, core_v, ctl_v in shifts:
        rows.append(_missing(what, U_RUB, ctl_v) if core_v is None
                    else _row(what, U_RUB, core_v, ctl_v, SIGN_TOL_REL, REL, group="gate", tol_abs=SIGN_TOL_RUB))
    return rows


@pytest.mark.ci_only
def test_volume_sign_numbers_match_core(control):
    """Число гейта знака объёмных эффектов ядра контрольная модель воспроизводит сама: сдвиг точки и сдвиги цен
    миров — в допуске 3 % модуля или 0,5 ₽, обе точки сравнения — как цена. Сработал гейт или нет, тест не
    судит: сработавший гейт требует объяснения книги, а не знака в тесте."""
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    core, why = core_gate(run, "volume_sign_test")
    if core is None:
        pytest.fail(f"сверять не с чем: {why}")
    mine = shared_gates()["volume_sign"]
    bad = [r for r in gate_rows(core, mine) if not r["ok"]]
    if bad:
        pytest.fail("число гейта знака объёмных эффектов вне допуска:" + chr(10) + _fail_lines(bad))
    if "growth_constraint_off" in core:
        assert bool(core["growth_constraint_off"]) == mine["growth_constraint_off"]


STRESS_PARTS = (("loss", ("world", "regime", "scenario"), "dv", "убыток"),
                ("requirement", ("world", "regime", "stricter", "looser"), "d_profit", "требование"))


def stress_band(divisor: float) -> float:
    """Абсолютная часть допуска числа гейта знака в млрд ₽: 0,5 ₽ на акцию × делитель N_div."""
    return SIGN_TOL_RUB * divisor / 1000.0


def stress_sign_mismatch(core: dict, ctl: dict, band: float) -> list[str]:
    """Расхождения набора нарушивших клеток гейта знака стресса между ядром и контрольной моделью — словами.
    Наборы обязаны совпасть. Клетка (пара сценариев), названная только одной моделью, расхождением не
    считается, если она стоит на пороге: числа моделей в ней различаются не больше чем на допуск числа
    гейта — max(3 % модуля, band), где band — те же 0,5 ₽ на акцию в млрд ₽ (stress_band). У клетки, названной
    только контрольной моделью, число ядра не печатается (оно не выше tol), поэтому мера — превышение её
    числа над tol. При совпавших наборах сверяются масса гейта (вероятности точки нарушивших клеток; у пары —
    клетка более строгого сценария) и вердикт."""
    tol = float(ctl["tol"])
    out, same = [], True
    for part, fields, value, words in STRESS_PARTS:
        theirs = {tuple(x[f] for f in fields): float(x[value]) for x in core[part]["cells"]}
        table = {tuple(x[f] for f in fields): x[value] for x in ctl[part]["table"]}
        mine = {key: v for key, v in table.items() if v > tol}
        for key in sorted(set(theirs) | set(mine)):
            if key in theirs and key in mine:
                continue
            same = False
            tag = f"{words} {'/'.join(key)}"
            if key not in table:
                out.append(f"{tag}: ядро называет клетку, которой у контрольной модели нет в счёте")
                continue
            ref = theirs[key] if key in theirs else mine[key]
            gap = theirs[key] - table[key] if key in theirs else mine[key] - tol
            if gap > max(SIGN_TOL_REL * abs(ref), band):
                who = "только ядро" if key in theirs else "только контрольная модель"
                out.append(f"{tag}: нарушение называет {who}; ядро {theirs.get(key)}, контроль {table[key]}, "
                           f"порог {tol}")
    if same and core.get("mass") is not None and abs(float(core["mass"]) - ctl["mass"]) > TOL_DERIVED:
        out.append(f"масса гейта при совпавших наборах: ядро {core['mass']}, контроль {ctl['mass']} — модели "
                   f"по-разному читают, какая клетка пары сценариев нарушает")
    if same and core.get("ok") is not None and bool(core["ok"]) != ctl["ok"]:
        out.append(f"вердикт гейта при совпавших наборах: ядро {core['ok']}, контроль {ctl['ok']}")
    return out


@pytest.mark.ci_only
def test_stress_sign_cells_match_core(inputs, control):
    """Набор нарушивших клеток гейта знака стресса (ключ книги checks.stress_sign) контрольная модель считает
    сама: клетки режима шока, где стоимость растёт при большем разовом убытке, и пары сценариев капитала
    во всех режимах, включая режим шока, где прибыль последнего года растёт при большем требовании. Наборы
    ядра и контрольной модели совпадают (клетка на пороге — в допуске числа гейта). Сработал гейт или нет,
    тест не судит."""
    book, _ = inputs
    if cm.c_bopt(book, "checks.stress_sign") is None:
        pytest.skip("в книге нет ключа checks.stress_sign — гейта нет; свой счёт контрольной модели проверяется "
                    "на фикстуре формы панели подменой ключа (tests/test_control_t.py)")
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    core, why = core_gate(run, "stress_sign_test")
    if core is None:
        pytest.fail(f"{why}: сверять набор нарушивших клеток не с чем")
    problems = stress_sign_mismatch(core, shared_gates()["stress_sign"], stress_band(control["divisor"]))
    assert not problems, "набор нарушивших клеток гейта знака стресса расходится:" + chr(10) + chr(10).join(problems)


@pytest.mark.ci_only
def test_printed_margin_matches_core(inputs, control):
    """Печатаемая маржа после фазы роста (ключ книги checks.nim_lt): число, которое печатает ядро
    (model.grid.printed_nim_lt), контрольная модель воспроизводит сама — та же клетка, те же годы, среднее —
    в допуске отношений М§17 (0,3 п.п.); строка сверки на годовом ряде клетки даёт то же число ядра."""
    margin = shared_gates()["printed_margin"]
    if margin is None:
        pytest.skip("в книге нет ключа checks.nim_lt — гейта печатаемой маржи нет; свой счёт контрольной модели "
                    "проверяется на фикстуре формы панели подменой ключа (tests/test_control_t.py)")
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    fn = getattr(importlib.import_module("model.grid"), "printed_nim_lt", None)
    if fn is None:
        pytest.fail("в ядре нет model.grid.printed_nim_lt: сверять печатаемую маржу не с чем")
    core = fn(run)
    assert core["cell"] == control["central"]["label"] or tuple(core["cell"]) == tuple(control["central"]["cell"])
    assert [int(y) for y in core["years"]] == sorted(margin["by_year"])
    assert abs(core["value"] - margin["value"]) <= TOL_RATIO, (core["value"], margin["value"])
    row = margin_row(run, control, margin)
    assert row["ok"] and row["core"] == pytest.approx(core["value"], abs=TOL_DERIVED)


LEVEL_MIXES = {cm.MIX_MODAL: "modal_cell", cm.LAYER_OWN: "analytical", cm.MIX_POINT: "point",
               cm.LAYER_MARKET: "macro_neutral"}        # смесь контрольной модели → строка узла уровней ядра


def core_levels_module():
    """Модуль уровней ядра (узел levels и число гейта долгосрочного C/I); нет модуля или функций — провал."""
    try:
        mod = importlib.import_module("model.levels")
    except Exception as exc:
        pytest.fail(f"в ядре нет модуля уровней model.levels ({type(exc).__name__}: {exc}): сверять уровни не с чем")
    for name in ("levels", "cir_lt_value"):
        if not hasattr(mod, name):
            pytest.fail(f"в ядре нет model.levels.{name}: сверять уровни не с чем")
    return mod


def core_run_of(book: dict):
    """Прогон ядра на книге-словаре с фактами каталога данных сверки; ядро не посчитало книгу — провал."""
    try:
        book_mod, grid_mod = importlib.import_module("model.book"), importlib.import_module("model.grid")
        core_facts = _core_facts(book_mod)
        return grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts), core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу — сверять не с чем: {type(exc).__name__}: {str(exc)[:500]}")


def level_rows(core: dict | None, mine: dict) -> list[dict]:
    """Строки сверки уровней слоя «рыночные ставки как есть» после фазы роста (CoR, C/I и ЧПМ, упр. базис):
    допуск отношений М§17 — 0,3 п.п. core и mine — {cor, cir, nim}; числа, которого у ядра нет, — строка «нет у
    ядра»."""
    core = core or {}
    rows = []
    mix0 = "cor_realized" in mine        # ключ credit.book_relative: гейт сверяет CoR на составе якоря
    for x in ("cor", "cir", "nim"):
        what = f"{LEVEL_WORDS}: {LEVEL_TITLES[x]}"
        mine_v = mine["cor_realized"] if (mix0 and x == "cor") else mine[x]
        rows.append(_missing(what, U_PCT, mine_v) if core.get(x) is None
                    else _row(what, U_PCT, core[x], mine_v, TOL_RATIO, ABS, group="gate"))
    if mix0:
        what = f"{LEVEL_WORDS}: {COR_MIX0_WORDS}"
        rows.append(_missing(what, U_PCT, mine["cor"]) if core.get("cor_mix0") is None
                    else _row(what, U_PCT, core["cor_mix0"], mine["cor"], TOL_RATIO, ABS, group="gate"))
    return rows


def cir_goal_row(core_value, mine_value) -> dict:
    """Строка сверки уровня C/I, с которым сверяется цель книги при checks.cir_lt.scope: market_layer."""
    if core_value is None:
        return _missing(CIR_GOAL_WORDS, U_PCT, mine_value)
    return _row(CIR_GOAL_WORDS, U_PCT, core_value, mine_value, TOL_RATIO, ABS, group="gate")


def levels_mismatch(core: dict, mine: dict) -> list[str]:
    """Расхождения узла уровней ядра (model.levels.levels) и уровней контрольной модели — словами: годы участка,
    четыре смеси, три метрики по годам и в среднем, допуск отношений М§17 (0,3 п.п.)."""
    out = []
    if [int(y) for y in core["years"]] != mine["years"]:
        return [f"годы участка: ядро {core['years']}, контроль {mine['years']}"]
    for mix, name in LEVEL_MIXES.items():
        theirs, ours = core["rows"].get(name), mine["mixes"][mix]
        if theirs is None:
            out.append(f"{name}: строки нет у ядра")
            continue
        for x in LEVEL_METRICS + (("cor_mix0",) if "cor_mix0" in ours else ()):
            pairs = [("среднее", theirs.get(x), ours[x])]
            by_year = (theirs.get("by_year") or {}).get(x) or [None] * len(mine["years"])
            pairs += [(y, v, ours["by_year"][y][x]) for y, v in zip(mine["years"], by_year)]
            for when, a, b in pairs:
                if a is None or abs(a - b) > TOL_RATIO:
                    out.append(f"{name}, {x}, {when}: ядро {a}, контроль {b}")
    return out


@pytest.mark.ci_only
def test_levels_match_core(control):
    """Уровни после фазы роста (узел levels ядра) контрольная модель воспроизводит сама: модальная клетка, слой
    «свой взгляд», смесь точки и слой «рыночные ставки как есть» — ЧПМ, CoR и C/I по годам участка и в среднем
    в допуске отношений М§17. У книги с ключом checks.window_backtest участок — его год, и строки сводки
    уровней слоя «как есть» в допуске; у книги без ключа год участка — аргументом у обеих моделей."""
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    start = level_start(control)
    core = core_levels_module().levels(run, start)
    mine = cm.c_levels(control, start)
    problems = levels_mismatch(core, mine)
    assert not problems, "уровни после фазы роста расходятся:" + chr(10) + chr(10).join(problems)
    assert core["cell"] == control["central"]["label"]
    window = cm.c_window_backtest(control)
    if window is not None:
        own = core_levels_module().levels(run)                  # без аргумента — год ключа книги
        assert int(own["from_year"]) == window["from_year"]
        bad = [r for r in level_rows(own["rows"][LEVEL_MIXES[cm.LAYER_MARKET]], window) if not r["ok"]]
        assert not bad, _fail_lines(bad)


@pytest.mark.ci_only
def test_cir_level_matches_core(inputs, control):
    """Уровень C/I цели книги (ключ checks.cir_lt) у ядра (model.levels.cir_lt_value) и у контрольной модели — в
    допуске отношений М§17 в обеих областях: в области книги и в другой, подставленной тестом (модальная
    клетка без ключа scope, слой «рыночные ставки как есть» при scope: market_layer)."""
    book, _ = inputs
    spec = cm.c_bopt(book, "checks.cir_lt")
    if spec is None:
        pytest.skip("в книге нет ключа checks.cir_lt — цели C/I нет; свой счёт контрольной модели проверяется "
                    "подменой ключа")
    mod = core_levels_module()
    plain = {k: v for k, v in spec.items() if k != SCOPE_KEY}
    for variant in (plain, {**plain, SCOPE_KEY: cm.SCOPE_MARKET}):
        b2 = cm.copy.deepcopy(book)
        b2["checks"]["cir_lt"] = dict(variant)
        core = mod.cir_lt_value(core_run_of(b2))
        mine = cm.c_cir_level(with_checks(control, cir_lt=dict(variant)))
        assert [int(y) for y in core["years"]] == sorted(mine["by_year"]), variant
        assert abs(core["value"] - mine["value"]) <= TOL_RATIO, (variant, core["value"], mine["value"])
        assert cir_goal_row(core["value"], mine["value"])["ok"]


@pytest.mark.ci_only
def test_control_matches_core_on_the_other_kappa_branch(inputs, control):
    """Мир-опора κ у обеих моделей на ветви ключа, которой у книги нет: у книги без ключа
    credit.kappa_reference_world опорой становится мир слоя «рыночные ставки как есть», у книги с ключом ключ
    снят. Вся сверка М§17 в допусках; разность годовой CoR клеток мира и мира-опоры — в 0,03 п.п.; сдвиг точки
    между ветвями у моделей один — в допуске числа гейта знака (3 % модуля или 0,5 ₽).

    ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 8, Р8-9; ops/expected_counts.json → known_failures): на книге p3 @ 48f3ca2
    вне допуска 3 строки RWA гарантий конца 2027 (M/downturn/mid и strict) и 2028 (strict) — класс урезанного роста
    Р6-9 (годовая форма контроля в клетках урезанного роста). Сторож класса —
    tests/test_control_pass6.py::test_p6_control_rows_off_are_the_growth_cut_class[book]: те же 3 строки RWA гарантий,
    612,52 против 606,27 (ветвь κ этих клеток не меняет)."""
    book, facts = inputs
    base, why = _core_grid()
    if base is None:
        pytest.fail(f"сверять не с чем: {why}")
    b2 = other_kappa_branch(book)
    ctl = cm.c_control_run(b2, facts)
    run = core_run_of(b2)
    rows = compare_with_core(run, ctl)
    if cm.c_kappa_world(ctl["ctx"]["B"]) is None:               # у ветви без ключа опора — мир N
        rows += kappa_spread_rows(run, ctl)
    assert any(r["group"] == "kappa" for r in rows)
    fail_off_rows(run, ctl, rows)
    d_core, d_ctl = run.point - base.point, ctl["point"] - control["point"]
    assert d_core != 0.0 and d_ctl != 0.0, "ключ мира-опоры κ не меняет точку: ветви не различаются"
    assert abs(d_ctl - d_core) <= max(SIGN_TOL_REL * abs(d_core), SIGN_TOL_RUB), (d_core, d_ctl)
    assert not exact_match(run, ctl)


def _closed_quarter_obs(book: dict, cor: float) -> dict:
    """Наблюдение квартала якоря с замороженными μ (их пишет перезаякоривание, М§12): μ CoR — значения
    путей режимов книги в первом прогнозном квартале (вход сверки, не допущение)."""
    y, q = cm.c_per_parse(book["meta"]["first_period"])
    mu = {r: cm.c_traj_at(book["regimes"][r]["cor"], y, q) for r in book["regimes"]["ids"]}
    return {"period": book["meta"]["anchor_period"], "cor": cor, "nim": None, "se_cor": 0.0, "se_nim": None,
            "basis": "mgmt", "mu_cor": mu}


# наблюдения A-P2u (М§12) первого прогнозного квартала — входы сверки, не допущения. Числа — отступы от ожидания модели
# первого прогнозного квартала (упр. база, взвешено априорными вероятностями режимов; `first_quarter_expectation`), а не
# уровни: у книги формы образца ожидание было 1,2 % CoR / 6,0 % ЧПМ, и сценарии стояли числами (факт 1,2 / 6,0 %, плохой
# квартал 1,8 / 5,8 %, пол 2,4 %); у книги Совкомбанка ожидание 2,52 / 7,45 %, и те же уровни — уже не «факт = ожидание» и
# не «высокие кварталы» (Д16, литералы). Отступы — прежние: (CoR, ЧПМ) наблюдения; None — показатель не наблюдён.
OBS_OFFSETS = {
    "факт-ожидание": {"first": (0.0, 0.0, 0.0, 0.0)},
    "плохой-квартал": {"first": (0.006, -0.002, 0.0, 0.0)},
    "нау-каст-cor": {"first": (0.002, None, 0.001, None)},
    # квартал якоря с замороженными μ и первый прогнозный квартал: оба в окне
    "закрытый-квартал": {"closed": 0.007, "first": (0.001, None, 0.0, None)},
    # то же при окне в одно наблюдение: квартал якоря из окна выпал
    "окно-1": {"closed": 0.007, "window": 1, "first": (0.001, None, 0.0, None)},
    # три высоких квартала подряд (квартал якоря и два прогнозных): режим с низкой CoR доходит до пола (В15). Предел
    # сдвига вероятности за наблюдение (max_shift_pp) сценарий снимает — вход сверки, как окно у «окно-1»: у книги
    # Совкомбанка (предел 0,05, пол 0,33 × априорной) мягкая посадка за три наблюдения опускается не ниже 0,3188 − 3 × 0,05 =
    # 0,169 > пола 0,105, и ветвь пола не исполнилась бы ни у ядра, ни у контроля
    "пол": {"closed": 0.012, "max_shift": 1.0, "first": (0.012, None, 0.0, None), "more": [(0.012, None, 0.0, None)]},
}
OBS_NAMES = tuple(OBS_OFFSETS)


@functools.lru_cache(maxsize=None)
def first_quarter_expectation() -> tuple[float, float]:
    """Ожидание модели первого прогнозного квартала (CoR, ЧПМ) в упр. базе: Σ_r P(r) μ_r контрольной модели на машинной
    книге (наблюдений в книге нет — априорные вероятности)."""
    control = shared_control()
    ctx = control["ctx"]
    y, q = cm.c_per_parse(ctx["B"]["meta"]["first_period"])
    mu = cm.c_expectations_ctl(ctx, [(y, q)])
    prior = control["posterior"]
    return tuple(cm.c_to_mgmt(ctx["A"], x, sum(prior[r] * mu[(x, r, y, q)] for r in prior)) for x in ("cor", "nim"))


def obs_scenario(name: str) -> dict:
    """Сценарий наблюдений `name` числами: ожидание первого прогнозного квартала + отступы `OBS_OFFSETS`."""
    e_cor, e_nim = first_quarter_expectation()
    spec = OBS_OFFSETS[name]

    def one(d) -> dict:
        cor, nim, se_cor, se_nim = d
        return {"cor": e_cor + cor, "nim": None if nim is None else e_nim + nim, "se_cor": se_cor, "se_nim": se_nim,
                "basis": "mgmt"}
    out = {"first": one(spec["first"])}
    if "closed" in spec:
        out["closed"] = e_cor + spec["closed"]
    if "window" in spec:
        out["window"] = spec["window"]
    if "max_shift" in spec:
        out["max_shift"] = spec["max_shift"]
    if "more" in spec:
        out["more"] = [one(d) for d in spec["more"]]
    return out


TOL_POSTERIOR = 0.02     # вероятность режима после A-P2u (М§17)


def _book_with_observations(book: dict, spec: dict) -> dict:
    b2 = cm.copy.deepcopy(book)
    obs = [{"period": book["meta"]["first_period"], **spec["first"]}]
    for extra in spec.get("more", ()):                          # следующие прогнозные кварталы подряд
        obs.append({"period": _next_period(obs[-1]["period"]), **extra})
    if "closed" in spec:
        obs.insert(0, _closed_quarter_obs(book, spec["closed"]))
    b2["joint"]["regime_update"]["observations"] = obs
    if "window" in spec:
        b2["joint"]["regime_update"]["window_obs"] = spec["window"]
    if "max_shift" in spec:
        b2["joint"]["regime_update"]["max_shift_pp"] = spec["max_shift"]
    return b2


# Известное расхождение на тестовом сценарии «пол» (решение ведущего 29.10.2026: у книги наблюдений нет, числа книги не
# задевает, разбор ноябрьской версией книги; долг — справочник панели, раздел долгов). strict: починка — снять метку.
XFAIL_OBS_FLOOR = pytest.mark.xfail(strict=True, reason=(
    "известное расхождение на тестовом сценарии «пол»: при двух наблюдённых прогнозных кварталах года якоря (2026К3, К4) "
    "CoR 2026 года в клетках downturn и crisis у ядра 3,7705 / 3,7780 %, у контроля 3,7387 % (0,032 п.п. при допуске "
    "0,03); расходятся правила A-P2u ядра и контроля для года якоря (М§12); у книги наблюдений нет, числа книги не "
    "задевает — разбор ноябрьской версией книги"))
OBS_PARAMS = [pytest.param(n, marks=XFAIL_OBS_FLOOR) if n == "пол" else n for n in OBS_NAMES]


@pytest.mark.ci_only
@pytest.mark.parametrize("name", OBS_PARAMS)
def test_control_matches_core_with_observations(inputs, name):
    """Ветка A-P2u, которую книга держит пустой: апостериорные вероятности режимов (окно, пол, замороженные
    μ наблюдения квартала якоря) и точка."""
    book, facts = inputs
    try:
        book_mod = importlib.import_module("model.book")
        grid_mod = importlib.import_module("model.grid")
        run_fn, from_dict = grid_mod.run_grid, book_mod.book_from_dict
    except Exception as exc:
        pytest.fail(f"ядро не готово ({type(exc).__name__}: {exc})")
    b2 = _book_with_observations(book, obs_scenario(name))
    ctl = cm.c_control_run(b2, facts)
    core_facts = _core_facts(book_mod)
    run = run_fn(from_dict(b2, facts=core_facts), core_facts)
    for r, p in ctl["posterior"].items():
        assert abs(run.ctx.posterior[r] - p) <= TOL_POSTERIOR, (r, run.ctx.posterior[r], p)
    for layer in cm.LAYERS:
        assert abs(ctl["layers"][layer]["v0"] / run.layers[layer].v0 - 1.0) <= TOL_VALUE, layer
    assert abs(ctl["point"] / run.point - 1.0) <= TOL_VALUE
    fail_off_rows(run, ctl, compare_with_core(run, ctl))                  # отклонения клеток — в строках ОПУ


@pytest.mark.tact
def test_window_scenarios_of_the_reconciliation_differ(inputs):
    """Сценарии сверки «закрытый квартал» и «окно 1» действительно различаются окном: при окне в одно
    наблюдение квартал якоря на апостериорные не влияет."""
    book, facts = inputs
    both = cm.c_control_context(_book_with_observations(book, obs_scenario("закрытый-квартал")), facts)
    last = cm.c_control_context(_book_with_observations(book, obs_scenario("окно-1")), facts)
    spec = {"first": obs_scenario("окно-1")["first"]}
    alone = cm.c_control_context(_book_with_observations(book, spec), facts)
    assert last["posterior"] == alone["posterior"]
    if cm.c_bget(book, "joint.regime_update.window_obs") > 1:
        assert both["posterior"] != last["posterior"]


@pytest.mark.tact
def test_floor_scenario_of_the_reconciliation_binds(inputs):
    """Сценарий сверки «пол» действительно доводит режим до пола вероятности: без пола тот же набор
    наблюдений оставил бы его ниже floor_share × базовой."""
    book, facts = inputs
    share = cm.c_bnum(book, "joint.regime_update.floor_share")
    if share <= 0.0:
        pytest.skip("книга держит пол вероятности выключенным")
    b2 = _book_with_observations(book, obs_scenario("пол"))
    if len(b2["joint"]["regime_update"]["observations"]) > int(b2["joint"]["regime_update"]["window_obs"]):
        pytest.skip("окно книги короче сценария")
    prior = {r: float(v) for r, v in book["joint"]["regime_prob"].items()}
    post = cm.c_control_context(b2, facts)["posterior"]
    b2["joint"]["regime_update"]["floor_share"] = 0.0
    loose = cm.c_control_context(b2, facts)["posterior"]
    pinned = [r for r in prior if loose[r] < share * prior[r]]
    assert pinned and all(post[r] == pytest.approx(share * prior[r], abs=1e-15) for r in pinned), (post, loose)


def _core_with_register(book: dict, facts: dict, register: list, v: str):
    """Пара прогонов «контроль, ядро» на книге с датой оценки v и реестром объявленных дивидендов."""
    import dataclasses
    book_mod = importlib.import_module("model.book")
    grid_mod = importlib.import_module("model.grid")
    f2 = cm.copy.deepcopy(facts)
    f2["dividends"]["register_seed"] = register
    b2 = cm.copy.deepcopy(book)
    b2["meta"]["valuation_date"] = b2["meta"]["date"] = v
    ctl = cm.c_control_run(b2, f2)
    core_facts = _core_facts(book_mod)
    core_facts = dataclasses.replace(core_facts, files={**core_facts.files, "dividends": f2["dividends"]})
    return ctl, grid_mod.run_grid(book_mod.book_from_dict(b2, facts=core_facts), core_facts)


@pytest.mark.ci_only
@annual_only
def test_control_matches_core_bridge_before_ex_date(inputs):
    """Мост М§8.1: объявленный дивиденд последнего года истории в реестре, дата оценки — за пять дней
    до экс-даты. B(v) ≤ 1 %, цена ≤ 3 % (М§17)."""
    book, facts = inputs
    hist = facts["dividends"]["history"][-1]
    dates = ("record_date", "last_buy_date", "ex_date", "pay_date")
    if all(hist.get(k) for k in dates):
        rec = {"year": hist["year"], "dps": cm._c_nodeval(hist["dps_ordinary"]), "status": "declared",
               **{k: hist[k] for k in dates}, "sources": ["сверка М§17"]}
    else:
        # строка истории без дат записи: даты — от конца квартала собрания года после года прибыли
        year = int(cm._c_nodeval(hist["year"]))
        agm_end = cm.c_q_last_day(year + 1, int(book["dividends"]["calendar"]["agm_quarter"]))
        rec = _declared(year, cm._c_nodeval(hist["dps_ordinary"]), agm_end)
    v = (dt.date.fromisoformat(rec["ex_date"]) - dt.timedelta(days=5)).isoformat()
    try:
        ctl, run = _core_with_register(book, facts, [rec], v)
    except ImportError as exc:
        pytest.fail(f"ядро не готово ({exc})")
    assert ctl["bridge_amount"] > 0.0
    assert abs(ctl["bridge_amount"] / run.bridge_amount - 1.0) <= TOL_BRIDGE
    assert abs(ctl["point"] / run.point - 1.0) <= TOL_VALUE


@pytest.mark.ci_only
@pytest.mark.parametrize("offset", [-10, -1, 0, 1], ids=["E_qA-10", "E_qA-1", "E_qA", "E_qA+1"])
@annual_only
def test_control_matches_core_at_agm_quarter_end(inputs, offset):
    """A2, № 25 (М§0.2, §8.1–§8.2): «конец квартала — конец дня» и D_pend у обеих моделей. Запись реестра за
    год прибыли якоря, дата оценки — до, в день и после конца квартала ГОСА: B(v) и D_pend ≤ 1 %,
    точка ≤ 3 %."""
    book, facts = inputs
    y0, e_qa = _agm_end(book)
    v = (e_qa + dt.timedelta(days=offset)).isoformat()
    try:
        ctl, run = _core_with_register(book, facts, [_declared(y0, _history_dps(facts), e_qa)], v)
    except ImportError as exc:
        pytest.fail(f"ядро не готово ({exc})")
    for what, core_v, ctl_v in (("мост", run.bridge_amount, ctl["bridge_amount"]),
                                ("D_pend", run.pending_dividend, ctl["pending_amount"])):
        scale = max(abs(ctl_v), abs(core_v))
        assert abs(ctl_v - core_v) <= TOL_BRIDGE * scale + TOL_ZERO_BN, what
    assert (ctl["pending_amount"] > 0.0) == (offset < 0) and (ctl["bridge_amount"] > 0.0) == (offset >= 0)
    assert abs(ctl["point"] / run.point - 1.0) <= TOL_VALUE


REGISTER_DATES = {   # кварталы выплаты и отсечки записи реестра: (лет после года прибыли, квартал) — входы сверки
    "выплата-во-2К": {"pay": (1, 2), "reg": (1, 2)},
    "выплата-в-4К": {"pay": (1, 4), "reg": (1, 3)},
    "выплата-и-отсечка-через-год": {"pay": (2, 1), "reg": (2, 1)},
}


@pytest.mark.ci_only
@pytest.mark.parametrize("name", list(REGISTER_DATES))
@annual_only
def test_control_matches_core_on_register_dates(inputs, name):
    """М§5.4, §17: объявленный дивиденд года якоря с датами записи вне календаря книги — выплата и вычет из
    регуляторного капитала стоят у обеих моделей в кварталах записи: вся сверка М§17 в допусках, дивиденды
    к выплате и DPreg на концах годов совпадают (≤ 1 %)."""
    book, facts = inputs
    y0, _ = _agm_end(book)
    spec = REGISTER_DATES[name]
    rec = _dated_record(y0, _history_dps(facts), pay=(y0 + spec["pay"][0], spec["pay"][1]),
                        reg=(y0 + spec["reg"][0], spec["reg"][1]))
    try:
        ctl, run = _core_with_register(book, facts, [rec], str(book["meta"]["valuation_date"]))
    except ImportError as exc:
        pytest.fail(f"ядро не готово ({exc})")
    fail_off_rows(run, ctl, compare_with_core(run, ctl))
    qidx = _quarter_index(ctl)
    seen = 0.0
    for c in ctl["cells"]:
        q = run.cell(c["world"], c["regime"], c["scenario"]).quarters
        for p, r in zip(ctl["ctx"]["periods"], c["rows"]):
            for line in ("dp", "dpreg"):
                core_v = q[line][qidx[p["year"]][-1]]
                assert abs(r[line] - core_v) <= TOL_BRIDGE * max(abs(core_v), abs(r[line])) + TOL_ZERO_BN, (
                    line, p["year"], c["world"], c["regime"], c["scenario"], core_v, r[line])
                seen = max(seen, abs(r[line]))
    if spec["pay"][0] > 1:
        assert seen > 0.0, "выплата через год: на конце года ГОСА дивиденды к выплате обязаны быть ненулевыми"


@pytest.mark.ci_only
def test_control_matches_core_on_shifted_cor_level(inputs):
    """В14 (М§4.6, §17): пути CoR всех режимов сдвинуты на шаг строки чувствительности, опора FVC — путь
    нормы книги до подмены (у ядра — копия книги `with_overrides`, она помнит исходную; у контрольной
    модели — книга-опора). Вся сверка М§17 в допусках, и в клетке режима-опоры мира N строка FVC у обеих
    моделей — расход: сдвиг уровня дошёл до кредитов по СС."""
    book, facts = inputs
    try:
        book_mod = importlib.import_module("model.book")
        grid_mod = importlib.import_module("model.grid")
    except ImportError as exc:
        pytest.fail(f"ядро не готово ({exc})")
    step = cm.c_bnum(book, "valuation.sensitivities.cor_pp")
    b2 = cm.copy.deepcopy(book)
    for r in b2["regimes"]["ids"]:
        b2["regimes"][r]["cor"] = _shifted(b2["regimes"][r]["cor"], step)
    ctl = cm.c_control_run(b2, facts, base_book=book)
    core_facts = _core_facts(book_mod)
    over = {f"regimes.{r}.cor": b2["regimes"][r]["cor"] for r in b2["regimes"]["ids"]}
    run = grid_mod.run_grid(book_mod.book_from_dict(book, facts=core_facts).with_overrides(over), core_facts)
    fail_off_rows(run, ctl, compare_with_core(run, ctl))
    if cm.c_bnum(book, "credit.fv_loans_factor") > 0.0 and step > 0.0:
        key = (plain_world(book), ctl["ctx"]["fv_ref"], list(cm.c_bget(ctl["ctx"]["B"], "capital.reg_scenarios.ids"))[0])
        mine = sum(r["fvc"] for r in cm.c_cell_of(ctl, *key)["rows"])
        theirs = sum(v for v in run.cell(*key).quarters["fvc"] if v is not None)
        assert mine > 0.0 and theirs > 0.0, (mine, theirs)


@pytest.mark.ci_only
def test_control_is_not_bit_identical_to_core(control):
    run, why = _core_grid()
    if run is None:
        pytest.fail(f"сверять не с чем: {why}")
    assert not exact_match(run, control), (
        "V0 всех слоёв совпали с ядром до 1e-9: контрольная модель и ядро, видимо, делят код (М§17)")


# ============================================================================ сводка для выпуска


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cm.ROOT, capture_output=True, text=True,
                             timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _strain(r: dict) -> float:
    """Доля допуска, выбранная строкой (для выбора худшей строки группы): по тому же правилу, что вердикт."""
    if r["diff"] is None or not r["tol"]:
        return math.inf
    if r["tol_kind"] == ABS:
        return abs(r["diff"]) / r["tol"]
    parts = []
    if r["diff_rel"] is not None:
        parts.append(abs(r["diff_rel"]) / r["tol"])
    if r.get("tol_abs"):
        parts.append(abs(r["diff"]) / r["tol_abs"])
    if not parts:
        return 0.0 if r["diff"] == 0.0 else math.inf
    return min(parts)


def _public(r: dict, what: str | None = None) -> dict:
    """Строка сводки для выпуска (П§2 checks.control_model.rows[]): единица и вид допуска сохранены."""
    out = {}
    for k in ROW_FIELDS:
        if k == "ok" and "tol_abs" in r:
            out["tol_abs"] = r["tol_abs"]
        out[k] = what if (k == "what" and what is not None) else r[k]
    return out


def summary_rows(rows: list[dict]) -> list[dict]:
    """Сжатие строк сверки для выпуска: передача, слои, цена и мост, стоимость клеток, худшая строка
    каждой группы строк клетки, строки, которых нет у ядра (не больше 10)."""
    keep = [_public(r) for r in rows if r["group"] in SUMMARY_WHOLE]
    worst: dict[str, dict] = {}
    for r in rows:
        if r["group"] in SUMMARY_WHOLE + ("missing",):
            continue
        if r["group"] not in worst or _strain(r) > _strain(worst[r["group"]]):
            worst[r["group"]] = r
    keep += [_public(r, f"худшая строка: {r['what']}") for _, r in sorted(worst.items())]
    keep += [_public(r) for r in rows if r["group"] == "missing"][:10]
    return keep


def checks_document(run, ctl, *, as_of: str, commit: str | None, gates=()) -> dict:
    """Содержимое data/checks/control_model.json (INTERFACES §3.3). gates — строки сверки чисел гейтов: числа
    гейта знака объёмных эффектов (gate_rows, ключ checks.volume_sign), уровни слоя «рыночные ставки как есть»
    (level_rows, ключ checks.window_backtest) и уровень C/I цели книги (cir_goal_row, ключ checks.cir_lt.scope:
    market_layer). Писатель сводки добавляет их у книги с этими ключами, сама сверка М§17 от них не зависит."""
    judged, excluded = reconcile(run, ctl)
    rows = judged + list(gates)
    # as_of — день счёта сводки; valuation_date — дата оценки, на которой стоят её числа (цена и дата книги)
    return {"as_of": as_of, "commit": commit,
            "book_version": str(cm.c_bget(ctl["ctx"]["B"], "meta.version")),
            "valuation_date": str(ctl["ctx"]["clock"]["v"]),
            "all_ok": all(r["ok"] for r in rows) and not exact_match(run, ctl),
            "n_rows": len(rows), "n_bad": sum(not r["ok"] for r in rows),
            "rows": summary_rows(rows),
            "excluded_at_threshold": excluded}


def summary_level_rows(run, ctl) -> list[dict]:
    """Строки уровней для сводки: уровни слоя «рыночные ставки как есть» — у книги с ключом
    checks.window_backtest, уровень C/I цели книги — при checks.cir_lt.scope: market_layer. У книги без этих
    ключей строк нет, и набор строк сводки прежний. Числа ядра — его узел уровней и число гейта C/I."""
    rows = []
    window, goal = cm.c_window_backtest(ctl), cm.c_cir_level(ctl)
    market = goal is not None and goal["scope"] == cm.SCOPE_MARKET
    if window is None and not market:
        return rows
    try:
        mod = importlib.import_module("model.levels")
        if window is not None:
            rows += level_rows(mod.levels(run)["rows"][LEVEL_MIXES[cm.LAYER_MARKET]], window)
        if market:
            rows.append(cir_goal_row(mod.cir_lt_value(run)["value"], goal["value"]))
    except Exception as exc:
        raise SystemExit(f"сводку не записать: уровни ядра не посчитаны ({type(exc).__name__}: {exc})")
    return rows


def write_checks(path: Path = CHECKS_JSON) -> dict:
    book, facts = cm.c_book_machine(), cm.c_facts_bundle()
    ctl = cm.c_control_run(book, facts)
    run, why = _core_grid()
    if run is None:
        raise SystemExit(f"сводку не записать: {why}")
    gates = []
    if cm.c_bopt(book, "checks.volume_sign") is not None:          # нет ключа — гейта нет, и строк гейта нет
        sign, why = core_gate(run, "volume_sign_test")
        if sign is None:
            raise SystemExit(f"сводку не записать: {why}")
        gates = gate_rows(sign, cm.c_volume_sign(book, facts, ctl))
    gates += summary_level_rows(run, ctl)
    doc = checks_document(run, ctl, as_of=dt.date.today().isoformat(), commit=_git_commit(), gates=gates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, ensure_ascii=False, indent=1) + chr(10)).encode("utf-8"))   # LF, как в репозитории
    return doc


def _stub_core(ctl: dict, k: float, d_ratio: float = 0.0):
    """Заглушка прогона ядра из результата контрольной модели: денежные величины × k, отношения + d_ratio.
    Ядро не нужно — так писатель сводки проверяется в такте на строках реальной формы."""
    tr = ctl["transmission"]
    trn = SimpleNamespace(sigma0=tr["sigma0"], sigma0_liab=tr["sigma0_liab"], phi=tr["phi"], t_real=tr["t_real"],
                          phi_assets=tr["phi_assets"], phi_liab=tr["phi_liab"], loan_margin=dict(tr["loan_margin"]),
                          t_local=dict(tr["t_local"]), pairs=dict(tr["pairs"]), roe_equiv=tr["roe_equiv"],
                          lt_spread={b: dict(v) for b, v in tr["lt_spread"].items()})
    qidx = _quarter_index(ctl)
    n_q = max(ids[-1] for ids in qidx.values())
    cells = {}
    for c in ctl["cells"]:
        quarters = {line: [None] + [0.0] * n_q for line in FLOW_LINES + ("div",)}
        quarters.update({line: [None] * (n_q + 1) for line in STOCK_LINES + RATIO_LINES})
        for p, r in zip(ctl["ctx"]["periods"], c["rows"]):
            j = qidx[p["year"]][-1]
            for line in FLOW_LINES + ("div",):
                quarters[line][j] = r[line] * k
            for line in STOCK_LINES:
                quarters[line][j] = r[line] * k
            for line in RATIO_LINES:
                quarters[line][j] = r[line] + d_ratio
        bv_q = c["rows"][-1]["bv"]
        cells[(c["world"], c["regime"], c["scenario"])] = SimpleNamespace(
            v_ri=c["v_ri"] * k, roe_t=c["roe_t"] + d_ratio, k_t=c["k_t"], g_t=c["g_t"], x_t=c["x_t"] * k,
            y_x=c["y_x"] * k, tv_ri=(bv_q + c["tv_ri"]) * k - bv_q * k, quarters=quarters,
            dps={yp: d["dps"] * k for yp, d in c["decisions"].items()}, years=tuple(ctl["years"]),
            annual={"nim": tuple(None if r["nim_year"] is None else r["nim_year"] + d_ratio for r in c["rows"]),
                    "cor": tuple(None if r["cor_year"] is None else r["cor_year"] + d_ratio for r in c["rows"])})
        if ctl["quarterly"]:
            # ветвь с квартальным проходом: DPS кварталов прибыли, требование с глиссадой, ряды роста
            cell = cells[(c["world"], c["regime"], c["scenario"])]
            cell.dps_q = {d["period"]: d["dps"] * k for d in c["decisions_q"]}
            for key in ("req20_glide", "req11_glide"):
                quarters[key] = [None] * (n_q + 1)
                for p, r in zip(ctl["ctx"]["periods"], c["rows"]):
                    quarters[key][qidx[p["year"]][-1]] = r[key]
            cell.growth = {"potential": [r["growth_potential"] for r in c["rows"]],
                           "actual": [None if r["growth_actual"] is None else r["growth_actual"] + d_ratio
                                      for r in c["rows"]],
                           "cut_share": [r["cut_share"] + d_ratio for r in c["rows"]],
                           "lam_min": [r["lam_min"] for r in c["rows"]]}
        _stub_pass1(cells[(c["world"], c["regime"], c["scenario"])], ctl, c, qidx, n_q, k, d_ratio)
        _stub_pass2(cells[(c["world"], c["regime"], c["scenario"])], ctl, c, qidx, n_q, k, d_ratio)
        _stub_pass3(cells[(c["world"], c["regime"], c["scenario"])], ctl, c, qidx, n_q, k)
    return SimpleNamespace(
        ctx=SimpleNamespace(transmission=trn),
        layers={n: SimpleNamespace(v0=ly["v0"] * k) for n, ly in ctl["layers"].items()},
        low=ctl["low"] * k, high=ctl["high"] * k, point=ctl["point"] * k,
        # мост и объявленный дивиденд — с половиной отклонения: их допуск (1 %) строже допуска строк
        bridge_amount=ctl["bridge_amount"] * (1.0 + k) / 2.0, pending_dividend=ctl["pending_amount"] * (1.0 + k) / 2.0,
        cell=lambda w, r, s: cells[(w, r, s)])


def _stub_pass1(cell, ctl: dict, c: dict, qidx: dict, n_q: int, k: float, d_ratio: float) -> None:
    """Поля заглушки ядра для ключей первого прохода — только у клетки с ключом (книга без ключей — прежняя заглушка):
    выкуп (n_t, s_price, ряд bb), блок терминала (terminal_fixed), CoR на составе якоря (ряд cor_mix0, сдвиг — десятая
    доля d_ratio: допуск строки 0,03 п.п.), взвешенная база расходов (ряд vol_opex — средняя периода на квартал)."""
    q = cell.quarters
    periods = list(zip(ctl["ctx"]["periods"], c["rows"]))
    if "n_t" in c:
        cell.n_t, cell.s_price = c["n_t"], c["s_price"] * k
        q["bb"] = [None] + [0.0] * n_q
        for p, r in periods:
            q["bb"][qidx[p["year"]][-1]] = r["bb"]
    if "terminal_fixed" in c:
        # с половиной отклонения, как мост: допуск строк блока (1 %) строже допуска строк ОПУ
        cell.terminal_fixed = {x: c["terminal_fixed"][x] * (1.0 + k) / 2.0 for x in ("f_k", "d_f", "i_f")}
    if ctl["ctx"].get("book_rel") is not None:
        q["cor_mix0"] = [None] * (n_q + 1)
        for p, r in periods:
            for j in qidx[p["year"]]:
                q["cor_mix0"][j] = r["cor_mix0"] + d_ratio / 10.0
    if ctl["ctx"].get("opex_w") is not None or ctl["ctx"].get("line_shares") is not None:
        q["vol_opex"] = [None] * (n_q + 1)
        for p, r in periods:
            for j in qidx[p["year"]]:
                q["vol_opex"][j] = r["vol_opex"]


def _stub_pass2(cell, ctl: dict, c: dict, qidx: dict, n_q: int, k: float, d_ratio: float) -> None:
    """Поля заглушки ядра для ключей второго прохода — только у клетки с ключом (книга без ключей — прежняя заглушка):
    опт конца года (ряд wholesale, К3), резерв конца года (ряд allowance, К7; с половиной отклонения — допуск 2 %), RWA
    гарантий конца года (ряд rwa_guar, К5; с половиной отклонения), ΔNII*_L терминала (узел terminal_stationary, К4),
    рост баз строк (ряды vol_fees, vol_ins, К2), остаток ведомой книги (books.<b>.balance, К6), решения с жетоном
    (decisions, К1)."""
    q = cell.quarters
    periods = list(zip(ctl["ctx"]["periods"], c["rows"]))
    if ctl["ctx"].get("wtf_key"):
        q["wholesale"] = [None] * (n_q + 1)
        for p, r in periods:
            q["wholesale"][qidx[p["year"]][-1]] = r["wholesale"] * k
    if ctl["ctx"].get("allow") is not None:
        q["allowance"] = [None] * (n_q + 1)
        for p, r in periods:
            q["allowance"][qidx[p["year"]][-1]] = r["al"] * (1.0 + k) / 2.0
    if "terminal_stationary" in c:
        cell.terminal_stationary = {"d_nii_l": c["terminal_stationary"]["d_nii_l"] * k}
    if ctl["ctx"].get("min_dps") is not None:
        # решения клетки с жетоном (поля ядра token, period, q, cut); DPS года с жетоном — ровно min_dps
        cell.decisions = [SimpleNamespace(year=d["year"], period=d["period"], q=d["q"], cut=d["cut"],
                                          token=d.get("token", 0.0)) for d in c["decisions_q"]]
        for d in c["decisions_q"]:
            if d.get("token") and d["token_rule"]["m_Y"] == cm.c_traj_mean(ctl["ctx"]["min_dps"], d["year"],
                                                                           range(1, cm.QY + 1)):
                cell.dps[d["year"]] = c["decisions"][d["year"]]["dps"]
    if ctl["ctx"].get("driven"):
        cell.books = {b: {"balance": [None] * (n_q + 1)} for b in ctl["ctx"]["driven"]}
        for p, r in periods:
            for b in ctl["ctx"]["driven"]:
                cell.books[b]["balance"][qidx[p["year"]][-1]] = r["driven_end"][b] * (1.0 + k) / 2.0
    for line, spec in (ctl["ctx"].get("line_base") or {}).items():
        if spec is not None:
            q[f"vol_{line}"] = [None] * (n_q + 1)
            for p, r in periods:
                for j in qidx[p["year"]]:
                    q[f"vol_{line}"][j] = r[f"vol_{line}"]
    if ctl["ctx"].get("guar") is not None:
        q["rwa_guar"] = [None] * (n_q + 1)
        for p, r in periods:
            q["rwa_guar"][qidx[p["year"]][-1]] = r["rwa_guar"] * (1.0 + k) / 2.0


def _stub_pass3(cell, ctl: dict, c: dict, qidx: dict, n_q: int, k: float) -> None:
    """Поля заглушки ядра для ключей третьего прохода — только у клетки с ключом (книга без ключей — прежняя заглушка):
    поправка года терминала (узел terminal_year, К-Т2а; с половиной отклонения), множитель угасания по календарю
    (terminal_fade, К-Т2в; тот же — допуск 1e-6), признак связанности после выплаты (поле terminal_fixed, К-Т2б), деньги
    конца года (ряд cash, К8; с половиной отклонения — допуск 2 %)."""
    if "terminal_year" in c:
        cell.terminal_year = {"adj": c["terminal_year"]["adj"] * (1.0 + k) / 2.0}
    if "terminal_fade" in c:
        cell.terminal_fade = {"phi": c["terminal_fade"]["phi"]}
    fixed = c.get("terminal_fixed") or {}
    if "bound_after_payout" in fixed:
        node = dict(getattr(cell, "terminal_fixed", None) or {})
        node.update(bound_after_payout=fixed["bound_after_payout"], wt_after=fixed["wt_after"])
        cell.terminal_fixed = node
    if ctl["ctx"].get("cash") is not None:
        cell.quarters["cash"] = [None] * (n_q + 1)
        for p, r in zip(ctl["ctx"]["periods"], c["rows"]):
            cell.quarters["cash"][qidx[p["year"]][-1]] = r["cash"] * (1.0 + k) / 2.0


def _assert_row_form(r: dict) -> None:
    """Строка сводки — формы П§2: поля, единица из словаря, вид допуска, вердикт выводится из записанного."""
    assert set(ROW_FIELDS) <= set(r) and set(r) <= set(ROW_FIELDS) | {"tol_abs"}, sorted(r)
    assert r["unit"] in (U_BN, U_RUB, U_PCT, U_PP, U_NUM) and r["tol_kind"] in (REL, ABS), r
    if r["core"] is not None and r["control"] is not None:
        assert r["diff"] == pytest.approx(r["control"] - r["core"], abs=1e-12)
        if r["core"] != 0.0:
            assert r["diff_rel"] == pytest.approx(r["control"] / r["core"] - 1.0, abs=1e-12)
        else:
            assert r["diff_rel"] is None
        both_undefined = False
    else:
        assert r["diff"] is None and r["diff_rel"] is None
        both_undefined = r["core"] is None and r["control"] is None and r["ok"]     # пара миров не определена
    if not both_undefined:
        assert r["ok"] == verdict(r["diff"], r["diff_rel"], r["tol"], r["tol_kind"], r.get("tol_abs")), r


@pytest.mark.tact
def test_row_keeps_the_kind_of_tolerance():
    """№ 15 (П§2 checks.control_model): строка несёт единицу, вид допуска и относительную разность;
    вердикт следует из записанного — относительная строка не судится по абсолютной разности."""
    r = _row("ЧПД", U_BN, 1000.0, 975.0, TOL_LINE, REL, group="nii")
    assert (r["diff"], r["diff_rel"], r["tol_kind"], r["ok"]) == (-25.0, pytest.approx(-0.025), REL, True)
    assert not _row("ЧПД", U_BN, 1000.0, 880.0, TOL_LINE, REL, group="nii")["ok"]
    floor = _row("ЧП акционерам", U_BN, 10.0, 14.0, TOL_LINE, REL, group="ni_sh", tol_abs=5.0)
    assert floor["ok"] and floor["tol_abs"] == 5.0 and floor["diff_rel"] == pytest.approx(0.4)
    assert not _row("ЧП акционерам", U_BN, 10.0, 16.0, TOL_LINE, REL, group="ni_sh", tol_abs=5.0)["ok"]
    x_t = _row("избыток капитала", U_BN, 131.4, 101.4, 584.5, ABS, group="x_t")       # |diff| > 1 при допуске в млрд ₽
    assert x_t["ok"] and x_t["diff"] == pytest.approx(-30.0) and "tol_abs" not in x_t
    ratio = _row("Н20.0", U_PCT, 0.1489, 0.1525, TOL_RATIO, ABS, group="n20")
    assert not ratio["ok"] and ratio["diff"] == pytest.approx(0.0036)
    zero = _row("переоценка", U_BN, 0.0, 0.0, TOL_LINE, REL, group="fvc")
    assert zero["ok"] and zero["diff_rel"] is None
    noise = _row("переоценка", U_BN, -3.6e-15, 0.0, TOL_LINE, REL, group="fvc")     # шум ядра — ноль
    assert noise["ok"] and noise["core"] == 0.0 and noise["diff_rel"] is None
    assert not _row("переоценка", U_BN, 0.0, 0.2, TOL_LINE, REL, group="fvc")["ok"]
    assert _bridge_row("мост", 0.0, 0.0)["tol_kind"] == ABS and _bridge_row("мост", 0.0, 0.0)["ok"]
    assert not _bridge_row("мост", 0.0, 1.0)["ok"]
    assert _bridge_row("мост", 850.0, 851.0)["tol_kind"] == REL and _bridge_row("мост", 850.0, 851.0)["ok"]
    gone = _missing("капитал", U_BN, 5.0)
    assert not gone["ok"] and gone["diff"] is None and gone["tol"] is None
    for row in (r, floor, x_t, ratio, zero, gone):
        _assert_row_form(_public(row))


@pytest.mark.tact
def test_gate_reconciliation_keeps_its_tolerances():
    """Сверка гейтов знака (числа — входы теста). Число гейта знака объёмных эффектов: |Δ| ≤ 3 % модуля числа
    ядра или ≤ 0,5 ₽; точки сравнения — как цена; числа, которого у ядра нет, — строка «нет у ядра». Набор
    нарушивших клеток гейта знака стресса: совпадает; клетка на пороге (числа моделей различаются не больше
    чем на max(3 % модуля, 0,5 ₽ на акцию в млрд ₽)) расхождением не считается; при совпавших наборах
    сверяются масса и вердикт."""
    core = {"point": 250.0, "point_free": 240.0, "d_point": -10.0, "d_world": {"N": -1.0, "H": 0.2, "M": -30.0}}
    same = gate_rows(core, {**core, "d_world": dict(core["d_world"])})
    assert len(same) == 6 and all(r["ok"] and r["group"] == "gate" and r["unit"] == U_RUB for r in same)
    assert [r.get("tol_abs") for r in same] == [None, None] + [SIGN_TOL_RUB] * 4
    near = gate_rows(core, {"point": 251.0, "point_free": 241.0, "d_point": -10.4,
                            "d_world": {"N": -1.45, "H": -0.2, "M": -30.8}})
    assert all(r["ok"] for r in near)                    # 4 % при 0,4 ₽; 0,45 ₽; смена знака в пределах 0,5 ₽; 2,7 %
    far = gate_rows(core, {"point": 250.0, "point_free": 240.0, "d_point": -10.6,
                           "d_world": {"N": -1.0, "H": 0.8, "M": -31.0}})
    assert [r["what"] for r in far if not r["ok"]] == [f"{SIGN_WORDS}: сдвиг точки", f"{SIGN_WORDS}: сдвиг цены мира H",
                                                       f"{SIGN_WORDS}: сдвиг цены мира M"]
    gone = gate_rows({"point": 250.0}, {**core, "d_world": dict(core["d_world"])})
    assert sum(r["group"] == "missing" for r in gone) == 5 and not any(r["ok"] for r in gone[1:])
    for r in same + near + far + gone:
        _assert_row_form(_public(r))

    def cells(part, pairs):
        fields = dict((x[0], x[1]) for x in STRESS_PARTS)[part]
        value = dict((x[0], x[2]) for x in STRESS_PARTS)[part]
        return [{**dict(zip(fields, key)), value: v} for key, v in pairs.items()]

    def side(loss, req, **extra):
        return {"loss": {"cells": cells("loss", loss)}, "requirement": {"cells": cells("requirement", req)}, **extra}

    a, b, c = (("M", "crisis", x) for x in ("schedule", "mid", "strict"))
    pair = ("M", "norm", "mid", "schedule")
    ctl = {"tol": 0.5, "mass": 0.02, "ok": False,
           "loss": {"table": cells("loss", {a: 10.0, b: 0.7, c: -20.0})},
           "requirement": {"table": cells("requirement", {pair: 0.2})}}
    band = stress_band(1000.0)                           # делитель 1000 млн акций: 0,5 ₽ на акцию — 0,5 млрд ₽
    assert band == SIGN_TOL_RUB and stress_band(2000.0) == 2.0 * band
    assert stress_sign_mismatch(side({a: 10.3, b: 0.6}, {}, mass=0.02, ok=False), ctl, band) == []
    assert stress_sign_mismatch(side({a: 10.3}, {}), ctl, band) == []           # b у контрольной модели — на пороге
    assert stress_sign_mismatch(side({a: 10.3, b: 0.6}, {pair: 0.6}), ctl, band) == []  # пара у ядра — на пороге
    assert stress_sign_mismatch(side({a: 10.3, b: 0.6}, {pair: 0.6}), ctl, band / 2.0) != []
    for theirs, word in ((side({a: 10.3, b: 0.6, c: 5.0}, {}), "только ядро"),
                         (side({b: 0.6}, {}), "только контрольная модель"),
                         (side({a: 10.3, b: 0.6}, {pair: 3.0}), "только ядро"),
                         (side({a: 10.3, b: 0.6, ("N", "crisis", "mid"): 1.0}, {}), "нет в счёте"),
                         (side({a: 10.3, b: 0.6}, {}, mass=0.05), "масса"),
                         (side({a: 10.3, b: 0.6}, {}, ok=True), "вердикт")):
        found = stress_sign_mismatch(theirs, ctl, band)
        assert len(found) == 1 and word in found[0], (word, found)


@pytest.mark.tact
def test_summary_writer_on_rows_of_real_shape(control):
    """№ 15, № 41: сводка сверки на заглушке ядра (величины контрольной модели × 1,01) — все строки в
    допуске, формы П§2; относительные и абсолютные строки различены, есть абсолютная строка с |diff| > 1
    (избыток капитала, млрд ₽); пол допуска DPS — от BV конца года выплаты, свой у каждого года. При
    расхождении в 20 % строки выходят из допуска."""
    near = _stub_core(control, 1.0 / 1.01, d_ratio=0.001)
    rows = compare_with_core(near, control)
    assert rows and all(r["ok"] for r in rows), [r["what"] for r in rows if not r["ok"]][:10]
    doc = checks_document(near, control, as_of="2026-10-02", commit=None)
    assert doc["all_ok"] and doc["n_bad"] == 0 and doc["n_rows"] == len(rows)
    assert doc["valuation_date"] == str(control["ctx"]["clock"]["v"]) and doc["as_of"] == "2026-10-02"
    json.dumps(doc, ensure_ascii=False)
    for r in doc["rows"]:
        _assert_row_form(r)
    kinds = {r["tol_kind"] for r in doc["rows"]}
    assert kinds == {REL, ABS}
    assert any(r["tol_kind"] == ABS and r["unit"] == U_BN and abs(r["diff"]) > 1.0 for r in doc["rows"])
    assert any("tol_abs" in r for r in doc["rows"])
    rel = [r for r in rows if r["tol_kind"] == REL and r["diff_rel"] is not None and r["group"] in ("value", "cell")]
    assert rel and all(r["diff_rel"] == pytest.approx(0.01, rel=1e-9) for r in rel)
    groups = {r["group"] for r in rows}
    assert {"fvc", "misc", "y_x", "dps", "div", "x_t", "bridge", "derived", "lt_spread"} <= groups
    if control["quarterly"]:
        assert {"dps_q", "glide", "growth_potential", "growth_actual", "cut_share"} <= groups
    assert len([r for r in doc["rows"] if r["what"].startswith("худшая строка: ")]) == len(
        groups - set(SUMMARY_WHOLE) - {"missing"})
    # пол допуска DPS — BV конца года выплаты (тот же год, что у строки Div), а не последнего года
    scen = modal_scenario(control)
    c = cm.c_cell_of(control, "M", "norm", scen)
    n_out = control["ctx"]["A"]["N_out"]
    floors, decided = {}, {}
    for yp, d in c["decisions"].items():
        decided[yp] = d.get("decision_year", yp + 1)
        row = c["rows"][control["years"].index(decided[yp])]
        floors[yp] = dps_floor(control, c, yp)
        assert floors[yp] == pytest.approx(DIV_FLOOR_BV * abs(row["bv"]) * 1000.0 / n_out, rel=1e-12)
    assert len(set(floors.values())) == len(set(decided.values()))
    by_what = {r["what"]: r for r in rows}
    div_title = line_titles(control["ctx"]["B"])["div"]
    for yp, floor in floors.items():
        dps = by_what[f"DPS за {yp}, клетка M/norm/{scen}"]
        div = by_what[f"{div_title} {decided[yp]}, клетка M/norm/{scen}"]
        for r, plain in ((dps, floor), (div, floor * n_out / 1000.0)):
            if r.get("cut"):                  # решение срезано до запаса: пол не ниже прежнего (М§17)
                assert r["floor_plain"] == pytest.approx(plain, rel=1e-12) and r["tol_abs"] >= r["floor_plain"]
            else:
                assert r["tol_abs"] == pytest.approx(plain, rel=1e-12)
    far = compare_with_core(_stub_core(control, 1.0 / 1.2), control)
    bad = [r for r in far if not r["ok"]]
    assert bad and not checks_document(_stub_core(control, 1.0 / 1.2), control, as_of="2026-10-02", commit=None)["all_ok"]
    assert not exact_match(near, control) and exact_match(_stub_core(control, 1.0), control)


@pytest.mark.tact
def test_checks_file_has_the_payload_form():
    """Файл data/checks/control_model.json (ядро передаёт его в выпуск как есть): строки формы П§2,
    вердикты следуют из записанных чисел, счётчики сходятся."""
    if not CHECKS_JSON.exists():
        pytest.skip("сводки сверки ещё нет (её пишет интеграция: python -B -m tests.test_control_model --write)")
    doc = json.loads(CHECKS_JSON.read_text(encoding="utf-8"))
    assert {"as_of", "commit", "rows"} <= set(doc)
    assert doc["rows"], "в сводке нет строк"
    for r in doc["rows"]:
        _assert_row_form(r)
    assert doc["n_rows"] >= len(doc["rows"]) and doc["n_bad"] >= sum(not r["ok"] for r in doc["rows"])
    if doc["all_ok"]:
        assert doc["n_bad"] == 0


def _cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Сверка контрольной модели с ядром (М§17)")
    ap.add_argument("--write", action="store_true", help="записать data/checks/control_model.json")
    a = ap.parse_args(argv)
    if a.write:
        doc = write_checks()
        print(f"записано {CHECKS_JSON.relative_to(cm.ROOT)}: строк {doc['n_rows']}, вне допуска {doc['n_bad']}")
        return 0 if doc["all_ok"] else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
