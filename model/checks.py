"""Проверки прогона: инварианты (блокируют), гейты правдоподобия (требуют объяснения) — М§14.

Инварианты уровня клетки и книги — здесь; инварианты уровня выпуска
(`release_numbers`, `jump_guard`, `payload_contract`, `exdate_jump`) — model/payload.py.
Коридоры гейтов — в книге (`checks.*`), не в коде. Масса гейта — суммарная
вероятность клеток слоя «свой взгляд», где условие нарушено; у гейтов уровня
выпуска — 1; у гейта знака стресса — вероятность нарушивших клеток под вероятностями
точки (его сообщение называет и массу тех же клеток под весами слоя «свой взгляд»).
Сработавший гейт требует действующего объяснения — записи в
`data/assumptions/gate_explanations.yaml` {explanation, expected_mass |
expected_mass_range, valid_until}: сборку роняют нет записи, истёкший срок
(действует включительно), масса вне коридора 0,4 × lo − 0,02 … 1,5 × hi + 0,02.
Объяснение, срок которого истекает в ближайшие 30 дней, сборку не роняет и тревогой не
является: выпуск несёт флаг `explanation_expiring` (М§14.2–§14.3).
Флаги ядра (М§14.3, `ni_jump`) — тем же типом `Finding` (kind «flag»); флаги живых входов —
model/live.py. DDM = RI — в печатаемой сетке и во всех прогонах полосы (`band.ddm_ri_max`).

Сообщения гейтов и инвариантов печатает витрина: словами, доли — в процентах, разности долей
(спреды к опоре, сдвиги, запасы) — в п.п., число клеток и кварталов — согласованным падежом,
малые отклонения — как допуск («1·10⁻⁹»), без кодов полей, `inf`, кортежей и e-нотации (П§0.2).
Годовые ЧПМ, CoR и CIR гейта `guidance_gap` — в упр. базисе по правилу «год с отчётными
кварталами» (`model.grid.year_mgmt`, М§4.6). Границы узла гайденса — одна функция `guidance_band` (гейт и выпуск):
у `point` — ± `tol` узла фактов, без него — половина единицы последнего разряда числа из `text`.
Инвариант `dps_history` — тест истории выплат вида, заданного книгой (М§5.2); гейты второй формы банка
(`FORM_GATES`) выпускаются только при своём условии включения — у книги без их ключей в выходе их нет.
При квартальном календаре дивидендов (М§5.7) инвариант `dividend_bounds` сверяет суммы решений модели одного
квартала клетки с запасом квартала, гейт `payout_cap` прибавляет строки истории закрытых кварталов года, а гейт
ручного входа читает событие календаря «решение о дивиденде» за квартал прибыли. Гейты роста по капиталу
(М§4.13, §14.2): `growth_cut` — доля урезанного роста клетки выше коридора; `step_dividend` — у ступени пола срезан
дивиденд политики (падение доли прироста в квартале ступени — диагностика сообщения); сторожа правил книги — `cir_lt` (C/I на долгосрочном участке
против цели: модальной клетки, а при ключе `checks.cir_lt.scope: market_layer` — слоя «рыночные ставки как есть»),
`nim_lt` (печатаемая маржа модальной клетки после фазы роста против цели), `nim_stationary` (стационарная маржа
решателя передачи в названном мире против цели), `window_backtest` (CoR и C/I слоя «рыночные ставки как есть» после
фазы роста — в коридорах окна фактов), `funds_cost_to_key` (стоимость средств клиентов к ключевой ставке по мирам
не выше порога) и `wholesale_share` (доля оптового фондирования на конец года); числа сторожей уровней считаются на
готовой сетке (`model.levels`). Гейты знака (М§14.2): `volume_sign` — знак объёмных эффектов (число —
`model.grid.volume_sign_test`), `stress_sign` — стоимость не растёт с убытком кризиса, прибыль не растёт с
требованием к капиталу ни в одном режиме (`model.grid.stress_sign_test`); оба считаются на центральной книге с её собственными
входами (цена, дата и реестр книги) один раз на книгу (`sign_numbers`) и в прогонах полосы не участвуют. Гейт `payout_cap` сравнивает выплату с потолком с допуском
равенства (выплата ровно на потолке — не превышение) и, при ключе книги, с допуском в долях прибыли. Слово
отношения расходов к доходам в сообщениях — термин книги `meta.labels.terms.cir`, без него — прежнее.
Инвариант `transmission_solved` сверяет с ключом цели ЧПМ стационарную маржу мира уровня — мира ключа книги
`nii.transmission.level_world`, а без него мира-опоры решателя. Сообщение гейта `window_backtest` ставит маржу
слоя рядом с наибольшим кварталом окна фактов, когда книга его называет (сведением: условие гейта от него не
зависит); сообщение гейта `funds_cost_to_key` печатает отношения миров и порог одним числом знаков; маржу якоря
в сообщении гейта `nim_path_joint` подписывает книга (`meta.labels.gates.nim_anchor`: маржа по книгам ядра через
мост и отчётная маржа квартала якоря), без подписи — прежние слова.
"""

from __future__ import annotations

import datetime as _dt
import itertools
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from model.book import ROOT, lower_first, record_fields
from model.book_schema import BookError, FactsError, validate
from model.dividends import (DECLARED, HISTORY_CAP, HISTORY_NONE, cap_history, dps_history, history_dps,
                             history_test)
from model.grid import (LAYER_TITLES, NIM_LT, REFERENCE_REGIME, REFERENCE_SCENARIO, STRESS_SIGN, VOLUME_SIGN,
                        GridRun, live_from_book, printed_nim_lt, run_grid, stress_sign_test, volume_sign_test,
                        year_mgmt)
from model.levels import (FUNDS_COST, MARKET_LAYER, NIM_STATIONARY, WINDOW_BACKTEST, cir_lt_value, client_funds_end,
                          funds_cost_to_key, levels, stationary_nim)
from model.nii import nss_value, solve_transmission
from model.timeline import period_words

EXPLANATIONS_PATH = ROOT / "data" / "assumptions" / "gate_explanations.yaml"
WARN_DAYS = 30                               # плашка «объяснение истекает» — за 30 дней до срока (М§14.2)
MASS_LOW = (0.4, 0.02)                       # коридор массы: 0,4 × lo − 0,02 …
MASS_HIGH = (1.5, 0.02)                      # … 1,5 × hi + 0,02
REL_TOL = 1e-9                               # тождества BV, баланса, ОПУ (относительно)
PROB_TOL = 1e-12                             # суммы вероятностей

INVARIANTS = ("probabilities", "bv_identity", "balance_identity", "pnl_identity", "ddm_equals_ri",
              "dps_history", "transmission_solved", "dividend_bounds", "governance_sum", "book_schema")
GATES = ("pb_by_world", "roe_range", "cor_range", "nim_range", "nim_path_joint", "cir_range",
         "roe_k_homogeneity", "guidance_gap", "capital_gap", "k_gt_g", "roe_gt_g", "terminal_share",
         "real_rate", "bridge_drift", "transmission_pairs", "lt_spread_floor", "off_band_shift",
         "m_crisis_vs_cbr", "manual_input_overdue")
# Гейты второй формы банка (М§14.2): стоят после общих в этом порядке; гейт выпускается при условии включения.
FORM_GATES = ("growth_cut", "step_dividend", "cir_lt", "wholesale_share", "payout_cap", "nim_lt", "volume_sign",
              "stress_sign", "nim_stationary", "window_backtest", "funds_cost_to_key")
GATE_ORDER = GATES + FORM_GATES
CORE_FLAGS = ("ni_jump",)
# Доли, которые делят сдвиг σ0 и сжатие φ между кредитными книгами и средствами клиентов (М§4.5): гейт
# `lt_spread_floor` проверяется и на концах осей по этим ключам.
SHARE_KEYS = ("nii.sigma0_split", "nii.phi_split")
SHARE_WORDS = {"nii.sigma0_split": "доле сдвига σ0 на кредитных книгах",
               "nii.phi_split": "доле сжатия φ на кредитных книгах"}
PERCENT = 100                                # доля → проценты в текстах сообщений


def pct(x: float, digits: int = 2) -> str:
    """Доля словами: 0.0125 → «1,25 %» (тексты сообщений, П§0.2)."""
    return f"{PERCENT * float(x):.{digits}f}".replace(".", ",").replace("-", "−") + " %"


def pp(x: float, digits: int = 2) -> str:
    """Разность долей словами: 0.003 → «0,30 п.п.»."""
    return pct(x, digits)[:-2] + " п.п."


def num(x: float, digits: int = 3) -> str:
    return f"{float(x):.{digits}f}".replace(".", ",").replace("-", "−")


NBSP = "\u00a0"                              # неразрывный пробел: разрядка чисел в текстах
SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def grouped(n: int) -> str:
    """Целое с разрядкой: 2000 → «2 000» (неразрывный пробел)."""
    return f"{int(n):,}".replace(",", NBSP)


def sci(x: float, digits: int = 1) -> str:
    """Малое число как допуск: 6.9e-18 → «6,9·10⁻¹⁸», 1e-9 → «1·10⁻⁹», 0 → «0» (П§0.2: без e-нотации)."""
    x = float(x)
    if x == 0:
        return "0"
    mantissa, _, exponent = f"{x:.{digits}e}".partition("e")
    mantissa = mantissa.rstrip("0").rstrip(".").replace(".", ",").replace("-", "−")
    return f"{mantissa}·10{str(int(exponent)).translate(SUPERSCRIPT)}"


def _one(n: int) -> bool:
    return n % 10 == 1 and n % 100 != 11


def in_cells(n: int) -> str:
    """«в 1 клетке», «в 5 клетках», «в 21 клетке» (предложный падеж)."""
    return f"в {n} {'клетке' if _one(n) else 'клетках'}"


def in_quarters(n: int) -> str:
    """«в 1 квартале», «в 5 кварталах» (предложный падеж)."""
    return f"в {n} {'квартале' if _one(n) else 'кварталах'}"


def band_words(band: Sequence[float | None], digits: int = 2) -> str:
    """Коридор словами: «1,00…2,00 %», «не выше 1,40 %», «не ниже 13,30 %»; вырожденный — одно число."""
    lo, hi = band
    if lo is not None and lo == hi:
        return pct(lo, digits)
    if lo is None and hi is None:
        return "без границ"
    if lo is None:
        return f"не выше {pct(hi, digits)}"
    if hi is None:
        return f"не ниже {pct(lo, digits)}"
    return f"{pct(lo, digits)[:-2]}…{pct(hi, digits)}"


@dataclass(frozen=True)
class Finding:
    name: str                              # имя из М§14.1–§14.3
    kind: str                              # "invariant" | "gate" | "flag"
    fired: bool
    mass: float | None
    cells: tuple[str, ...]
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)


def _inv(name: str, bad: Sequence[str], message_ok: str, message_bad: str, **detail) -> Finding:
    return Finding(name=name, kind="invariant", fired=bool(bad), mass=None, cells=tuple(bad[:36]),
                   message=message_bad if bad else message_ok, detail=detail)


# ------------------------------------------------------------------ инварианты


def check_invariants(run: GridRun, band: Any = None) -> list[Finding]:
    """Инварианты М§14.1 уровня клетки и книги; `band` — полоса: DDM = RI и в её прогонах (М§6.4)."""
    ctx, book = run.ctx, run.ctx.book
    out: list[Finding] = []
    # probabilities: каждая таблица — неотрицательные числа в сумме 1 (сумма 1 при отрицательном весе —
    # не распределение: клетка вошла бы в оценку с обратным знаком)
    bad, negative = [], []

    def table(name: str, values) -> None:
        values = [float(v) for v in values]
        if abs(sum(values) - 1) > PROB_TOL:
            bad.append(name)
        if min(values) < 0:
            negative.append(name)

    table("вероятности режимов книги", book.get("joint.regime_prob").values())
    for r, row in book.get("joint.reg_prob_given_regime").items():
        table(f"вероятности сценариев капитала режима {r}", row.values())
    for name, layer in run.layers.items():
        table(f"веса миров слоя {name}", layer.world_weights.values())
        table(f"вероятности клеток слоя {name}", layer.prob.values())
    table("вероятности режимов после наблюдений", ctx.posterior.values())
    broken = (["суммы вероятностей ≠ 1: " + ", ".join(bad)] if bad else []) + (
        ["отрицательные вероятности: " + ", ".join(negative)] if negative else [])
    out.append(_inv("probabilities", bad + negative, "все таблицы вероятностей неотрицательны и в сумме 1",
                    "; ".join(broken)))
    # тождества по кварталам
    bv_bad, bal_bad, pnl_bad = [], [], []
    for c in run.cells:
        q_ = c.quarters
        for q in range(1, len(q_["bv"])):
            lhs = q_["bv"][q]
            rhs = (q_["bv"][q - 1] + q_["ni_sh"][q] - q_["coupon"][q] * (1 - q_["tau_stat"][q])
                   + q_["oci"][q] + q_["om"][q] - q_["div"][q])
            if "bb" in q_:                      # выкуп по цене мира — распределение акционерам (М§5.6)
                rhs -= q_["bb"][q]
            if abs(lhs - rhs) > REL_TOL * max(1.0, abs(lhs)):
                bv_bad.append(f"{c.label} {ctx.timeline.period(q)}")
            a, le = q_["assets"][q], q_["liabilities_equity"][q]
            if abs(a - le) > REL_TOL * max(1.0, abs(a)):
                bal_bad.append(f"{c.label} {ctx.timeline.period(q)}")
            pbt = (q_["nii"][q] - q_["llp"][q] - q_["fvc"][q] + q_["fees"][q] + q_["ins"][q]
                   + q_["misc"][q] + q_["fvr"][q] + q_["noncore"][q] - q_["opex"][q] + q_["one_off"][q])
            ni = q_["pbt"][q] - q_["tax"][q] - q_["ot"][q]
            if (abs(pbt - q_["pbt"][q]) > REL_TOL * max(1.0, abs(pbt))
                    or abs(ni - q_["ni"][q]) > REL_TOL * max(1.0, abs(ni))):
                pnl_bad.append(f"{c.label} {ctx.timeline.period(q)}")
    out.append(_inv("bv_identity", bv_bad, "капитал на конец квартала равен капиталу на начало плюс совокупный "
                                           "доход минус дивиденд — во всех кварталах клеток",
                    f"тождество капитала нарушено {in_quarters(len(bv_bad))}"))
    out.append(_inv("balance_identity", bal_bad, "активы равны пассивам с капиталом во всех кварталах",
                    f"тождество баланса нарушено {in_quarters(len(bal_bad))}"))
    out.append(_inv("pnl_identity", pnl_bad, "прибыль до налога равна сумме строк, чистая прибыль — прибыли до "
                                             "налога за вычетом налогов",
                    f"тождество отчёта о прибыли нарушено {in_quarters(len(pnl_bad))}"))
    tol = float(book.get("checks.ddm_ri_tol"))
    ddm_bad = [c.label for c in run.cells if abs(c.v_ddm - c.v_ri) > tol * abs(c.v_ri)]
    worst = ddm_ri_max(run)
    band_worst = getattr(band, "ddm_ri_max", None)
    where = "во всех клетках"
    if band_worst is not None:
        where = f"во всех клетках сетки и во всех {grouped(getattr(band, 'draws', 0))} прогонах полосы"
        if band_worst > tol:
            ddm_bad = ddm_bad + [f"полоса: наибольшая разность {sci(band_worst)}"]
    both = max(worst, band_worst or 0.0)
    out.append(_inv("ddm_equals_ri", ddm_bad,
                    f"дивидендная модель равна остаточному доходу {where} (наибольшая относительная разность "
                    f"{sci(both)})",
                    f"дивидендная модель расходится с остаточным доходом: {', '.join(ddm_bad[:3])} (наибольшая "
                    f"относительная разность {sci(both)} при допуске {sci(tol)})", worst=worst,
                    band_worst=band_worst))
    out.append(_history_invariant(book, ctx.facts))
    # transmission_solved: ключ цели — стационарная ЧПМ мира уровня (ключ книги `nii.transmission.level_world`;
    # без него — мира-опоры решателя)
    tr = ctx.transmission
    ttol = float(book.get("checks.transmission_tol"))
    level = tr.level_world or tr.reference_world
    nss_ref = nss_value(book, ctx.facts, level, 0.0, tr.sigma0, tr.phi, tr.sigma0_liab)
    e1, e2 = abs(nss_ref - tr.target_eng), abs(tr.t_real - tr.t_target)
    lt_level = book.label("terms.lt_level")
    bad = [x for x, e in ((f"ЧПМ {lt_level} мира {level}", e1), ("реализованная передача", e2))
           if e > ttol]
    out.append(_inv("transmission_solved", bad,
                    f"ЧПМ {lt_level} мира {level} равен цели (отклонение {sci(e1)}), реализованная "
                    f"передача равна цели книги (отклонение {sci(e2)})",
                    "передача ставки не решена: " + ", ".join(bad), nss_error=e1, t_error=e2))
    # dividend_bounds: вся выплата года — базовая, догоняющая и доля избытка — не больше запаса капитала
    # выбранной ступени (догоняющая и избыток — части Div_Y, а не добавка к границе; М§5.3 п. 4)
    bad = []
    for c in run.cells:
        if ctx.prep.calendar is not None:
            bad.extend(f"{c.label} {where}" for where in _quarter_bounds(c))
            continue
        for d in c.decisions:
            if d.dps < 0 or d.deferred_after < -1e-9:
                bad.append(f"{c.label} {d.year}")
            elif d.source == "model":
                h = d.headroom[d.step]
                if d.div > max(0.0, h) + REL_TOL * max(1.0, abs(d.div)):
                    bad.append(f"{c.label} {d.year}")
    out.append(_inv("dividend_bounds", bad, "дивиденд неотрицателен и не больше запаса капитала, отложенный пул "
                                            "неотрицателен",
                    f"границы дивиденда нарушены: {', '.join(bad[:5])}"))
    # governance_sum
    comps = book.get("valuation.governance.components")
    total = sum(float(x["sign"]) * float(x["value"]) for x in comps)
    g = float(book.get("valuation.governance.discount"))
    bad = ["governance"] if abs(total - g) > PROB_TOL else []
    out.append(_inv("governance_sum", bad, "дисконт за управление равен сумме каналов с их знаками",
                    f"дисконт за управление {pct(g, 3)} не равен сумме каналов {pct(total, 3)}"))
    # book_schema
    try:
        validate(book.data, corners=book.base is None)      # углы сложения связок — у корневой книги (Р5-4, М§10)
        out.append(_inv("book_schema", [], "книга в закрытой схеме", ""))
    except BookError as exc:
        out.append(_inv("book_schema", ["книга"], "", str(exc)))
    return out


def _quarter_bounds(cell: Any) -> list[str]:
    """Границы дивиденда при квартальном календаре (М§5.7.5, §14.1): по суммам решений модели одного квартала
    клетки — Σ base_div ≤ max(0, H_ref) и Σ div ≤ max(0, H_ref, H_fin) + Σ жетонов, допуск — относительный от суммы
    дивидендов; при жетоне DPS (К1) — Σ base_div + жетон ≤ max(0, запас над требованием без запаса менеджмента); DPS
    и отложенный пул неотрицательны — по каждому решению. Возвращает периоды нарушений."""
    bad: list[str] = []
    by_q: dict[int, list] = {}
    for d in cell.decisions:
        if d.dps < 0 or d.deferred_after < -1e-9:
            bad.append(str(d.period))
        elif d.source == "model":
            by_q.setdefault(d.q, []).append(d)
    for decs in by_q.values():
        base, paid = sum(d.base_div for d in decs), sum(d.div - d.token for d in decs)
        ref, final = decs[0].headroom[0], decs[0].headroom_final
        tol = REL_TOL * max(1.0, abs(paid))
        if base > max(0.0, ref) + tol or paid > max(0.0, ref, final) + tol:
            bad.append("–".join(dict.fromkeys(str(d.period) for d in decs)))
        token = sum(d.token for d in decs)      # жетон DPS (К1): в пределах запаса над требованием без запаса
        if token > 0:
            floor = next(d.headroom_floor for d in decs if d.token > 0)
            if base + token > max(0.0, floor) + REL_TOL * max(1.0, base + token):
                bad.append("–".join(dict.fromkeys(str(d.period) for d in decs)) + " (жетон)")
    return bad


def _history_invariant(book: Any, facts: Any) -> Finding:
    """Инвариант `dps_history` — тест истории выплат вида `dividends.policy.history_test` (М§5.2, §14.1)."""
    kind = history_test(book)
    if kind == HISTORY_NONE:
        return _inv("dps_history", [], "тест истории выплат выключен книгой", "")
    try:
        if kind == HISTORY_CAP:
            return _cap_invariant(cap_history(book, facts))
        rows = dps_history(book, facts)
        bad = [str(r["year"]) for r in rows if not r["ok"]]
        return _inv("dps_history", bad, "формула политики воспроизводит объявленный дивиденд на акцию до копейки",
                    "дивиденд на акцию истории не воспроизводится: " + ", ".join(bad), rows=rows)
    except (FactsError, BookError) as exc:
        return _inv("dps_history", ["история"], "", f"проверка дивиденда на акцию не выполнена: {exc}")


def _cap_invariant(rows: Sequence[Mapping[str, Any]]) -> Finding:
    """Тест вида `cap`: выплаты каждого завершённого года не выше потолка политики от отчётной прибыли
    акционеров; неполный год — строка диагностики; ни одного завершённого года — нарушен (М§5.2)."""
    share = lambda r: "доля не определена" if r["share"] is None else pct(r["share"], 1)  # noqa: E731
    done = [r for r in rows if r["complete"]]
    open_ = [r for r in rows if not r["complete"]]
    cap = pct(rows[0]["cap"], 0)
    bad = [str(r["year"]) for r in done if not r["ok"]] if done else ["нет завершённого года"]
    years = ", ".join(f"{r['year']} — {share(r)}" for r in done)
    tail = "".join(f"; неполный {r['year']} год — {share(r)} (диагностика)" for r in open_)
    ok = f"выплаты завершённых лет не выше потолка политики {cap} отчётной прибыли акционеров: {years}{tail}"
    broken = (f"выплаты года выше потолка политики {cap} отчётной прибыли акционеров: "
              + ", ".join(f"{r['year']} — {share(r)}" for r in done if not r["ok"]) + tail) if done else (
        "в фактах нет ни одного завершённого года — потолок политики не проверен")
    return _inv("dps_history", bad, ok, broken, rows=list(rows))


def ddm_ri_max(run: GridRun) -> float:
    """max |V_DDM − V_RI| / |V_RI| по клеткам прогона (М§6.4)."""
    return max(abs(c.v_ddm - c.v_ri) / abs(c.v_ri) for c in run.cells)


# ------------------------------------------------------------------ гейты


def _gate(name: str, run: GridRun, bad_cells: Sequence[str], message: str, *, mass: float | None = None,
          **detail) -> Finding:
    prob = run.layers["analytical"].prob
    if mass is None:
        keys = {c.label: c.key for c in run.cells}
        mass = sum(prob[keys[x]] for x in set(bad_cells))
    return Finding(name=name, kind="gate", fired=bool(bad_cells) or bool(mass and mass > 0),
                   mass=mass, cells=tuple(bad_cells), message=message, detail=detail)


def _outside(x: float | None, rng: Sequence[float]) -> bool:
    return x is not None and not (rng[0] <= x <= rng[1])


NUMBER_IN_TEXT = re.compile(r"(\d+)(?:[.,](\d+))?\s*(%)?")


def text_tolerance(text: Any) -> float | None:
    """Половина единицы последнего разряда числа, как оно записано в гайденсе (М§14.2):
    «22%» → 0,005; «~6.2%» → 0,0005; «~0%» → 0,005; числа в тексте нет — None."""
    m = NUMBER_IN_TEXT.search(str(text or ""))
    if not m:
        return None
    unit = Decimal(1) / Decimal(10) ** len(m.group(2) or "")
    if m.group(3):
        unit /= PERCENT
    return float(unit / 2)


def guidance_band(node: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Границы узла гайденса по `kind` (М§14.2, прил. B): `range` — [мин, макс]; `min` — (v, None);
    `max` — (None, v); `point` — v ± `tol` узла (нет `tol` — половина единицы последнего разряда числа из
    `text`). Открытая граница — None. Одна функция для гейта и выпуска."""
    v, kind = node.get("v"), node.get("kind")
    if v is None:
        return (None, None)
    if isinstance(v, (list, tuple)):
        if kind not in (None, "range"):
            raise FactsError(f"узел гайденса: список при kind = {kind!r}")
        return (float(v[0]), float(v[1]))
    v = float(v)
    if kind == "max":
        return (None, v)
    if kind == "min":
        return (v, None)
    if kind != "point":
        raise FactsError(f"узел гайденса: незнакомый kind {kind!r} (известны point, min, max, range)")
    tol = node.get("tol")
    if tol is None:
        tol = text_tolerance(node.get("text"))
    if tol is None:
        raise FactsError("узел гайденса point: нет ни tol, ни числа в text — допуск не определён (М§14.2)")
    return (v - float(tol), v + float(tol))


def inside(band: Sequence[float | None], x: float) -> bool:
    lo, hi = band
    return (lo is None or x >= lo) and (hi is None or x <= hi)


CIR_WORD = "CIR"                             # слово отношения расходов к доходам без термина книги `terms.cir`
RANGE_WORDS = {"roe": "ROE года", "cor": "CoR года (базис движка)", "cir": "{cir} года (базис движка)"}


def cir_word(book: Any) -> str:
    """Слово отношения расходов к доходам в заголовках и сообщениях гейтов: термин книги
    `meta.labels.terms.cir`, без него — прежнее слово кода (М§0.6)."""
    return book.label_or("terms.cir", CIR_WORD)


def _band_share(part: Mapping[str, Any], n: int) -> str:
    """«в 807 из 2 000 прогонов (масса таких клеток в среднем по всем прогонам — 0,77 %)» — строка хвоста
    полосы (М§10). Масса усреднена по всем прогонам полосы, а не по тем, где такие клетки есть."""
    return (f"в {grouped(part['draws'])} из {grouped(n)} прогонов (масса таких клеток в среднем по всем "
            f"прогонам — {pct(part['mass'])})")


def _band_gap_words(tail: Mapping[str, Any] | None) -> str:
    """Добавка к сообщению гейта `capital_gap`: то же условие в прогонах полосы."""
    return "" if tail is None else f"; в полосе — {_band_share(tail['capital_gap'], tail['n'])}"


def _band_capital_words(tail: Mapping[str, Any] | None) -> str:
    """Добавка к сообщению гейта `roe_gt_g`: в прогонах полосы — клетки, где нужна докапитализация, и клетки
    с отрицательной стоимостью; сколько такие клетки весят в печатаемой полосе (М§7, §10)."""
    if tail is None:
        return ""
    text = f"; в полосе — {_band_share(tail['need_capital'], tail['n'])}"
    neg, shift = tail["negative"], tail["floor_shift"]
    if not neg["draws"]:
        return text + "; стоимость клетки ниже нуля — ни в одном прогоне"
    return (text + f"; стоимость клетки ниже нуля — {_band_share(neg, tail['n'])}: с ограничением нулём снизу "
            f"низ полосы был бы выше на {num(shift['low'], 1)} ₽, медиана — на {num(shift['median'], 1)} ₽")


_ONCE: dict[tuple, tuple[Any, Any]] = {}     # (имя числа, книга) → (факты, число гейта уровня книги)
ONCE_MAX = 64                                # столько чисел помнится; дальше вытесняется самое старое


def _once(name: str, run: GridRun, compute) -> Any:
    """Число гейта уровня книги — один раз на книгу (с подменами; книга до подмен — отдельно) и факты (тот же
    объект): повторный вызов проверок на той же книге новых сеток не считает (время набора такта, М§18)."""
    book, facts = run.ctx.book, run.ctx.facts
    key = (name, book.digest, None if book.base is None else book.base.digest)
    hit = _ONCE.get(key)
    if hit is None or hit[0] is not facts:
        _ONCE.pop(key, None)
        while len(_ONCE) >= ONCE_MAX:
            _ONCE.pop(next(iter(_ONCE)))
        hit = _ONCE[key] = (facts, compute())
    return hit[1]


def _book_run(run: GridRun) -> GridRun:
    """Сетка центральной книги на её собственных входах — цене, дате и реестре книги: число гейта уровня книги
    от живой цены и даты такта не зависит. Прогон на тех же входах берётся как есть."""
    live = live_from_book(run.ctx.book, run.ctx.facts)
    return run if run.ctx.live == live else run_grid(run.ctx.book, run.ctx.facts, live)


def sign_numbers(run: GridRun) -> dict[str, Any]:
    """Числа гейтов знака центральной книги (М§14.2): `volume_sign` — результат
    `model.grid.volume_sign_test`, `stress_sign` — `model.grid.stress_sign_test`; у книги без ключа гейта —
    None. Считаются на книге прогона с её собственными входами (цена, дата и реестр книги) один раз на книгу и
    факты: их читают гейты, таблицы книги и выпуск — в таблицах книги и в выпуске число одно."""
    book, facts = run.ctx.book, run.ctx.facts
    volume, stress = book.opt(VOLUME_SIGN) is not None, book.opt(STRESS_SIGN) is not None
    if not volume and not stress:
        return {"volume_sign": None, "stress_sign": None}

    def compute() -> dict[str, Any]:
        base = _book_run(run)                   # одна сетка книги на оба числа
        return {"volume_sign": volume_sign_test(book, facts, run=base) if volume else None,
                "stress_sign": stress_sign_test(book, facts, run=base) if stress else None}

    return dict(_once("sign_numbers", run, compute))


def check_gates(run: GridRun, *, today: _dt.date | None = None,
                off_band: Mapping[str, Any] | None = None, band: Any = None,
                volume_sign: Mapping[str, Any] | None = None,
                stress_sign: Mapping[str, Any] | None = None) -> list[Finding]:
    """Гейты М§14.2 и флаги ядра М§14.3. `off_band` — диагностика сдвига положения осей вне полосы
    (`model.uncertainty.off_band_shift`: {rub, limit, axes}); нет — считается здесь, если такие оси есть.
    `band` — полоса: сообщения гейтов `capital_gap` и `roe_gt_g` называют и хвост её прогонов (условие и
    масса гейта — по-прежнему печатаемой сетки: прогоны полосы объяснения не требуют). `volume_sign` и
    `stress_sign` — готовые числа гейтов знака (`sign_numbers`); нет — берутся там же: один раз на книгу."""
    ctx, book = run.ctx, run.ctx.book
    bridge = ctx.bridge
    today = today or ctx.clock.valuation_date
    tail = band.tail(run.lam) if band is not None else None
    out: list[Finding] = []
    ch = lambda k: book.get(f"checks.{k}")
    # pb_by_world
    bad = [c.label for c in run.cells if _outside(c.v_price / c.bv_v, ch(f"pb_by_world.{c.world}"))]
    out.append(_gate("pb_by_world", run, bad, f"P/B клетки вне коридора мира {in_cells(len(bad))}"))
    # годовые коридоры ROE, CoR, CIR; квартальный ЧПМ (упр. базис)
    for name, key, field_ in (("roe_range", "roe_range", "roe"), ("cor_range", "cor_range", "cor"),
                              ("cir_range", "cir_range", "cir")):
        rng = ch(key)
        bad, worst = [], []
        for c in run.cells:
            vals = [v for v in c.annual[field_] if v is not None]
            if any(_outside(v, rng) for v in vals):
                bad.append(c.label)
                worst.append((min(vals), max(vals)))
        span = (min(w[0] for w in worst), max(w[1] for w in worst)) if worst else None
        words = RANGE_WORDS[field_].format(cir=cir_word(book))
        out.append(_gate(name, run, bad, f"{words} вне коридора {band_words(rng)} {in_cells(len(bad))}"
                         + (f" (размах {band_words(span)})" if span else ""), span=span))
    rng = ch("nim_range")
    bad = []
    for c in run.cells:
        nims = [bridge.to_mgmt_nim(v) for v in c.quarters["nim"][1:] if v is not None]
        if any(_outside(v, rng) for v in nims):
            bad.append(c.label)
    out.append(_gate("nim_range", run, bad, f"ЧПМ квартала (упр.) вне коридора {in_cells(len(bad))}"))
    out.append(_nim_joint_gate(run))
    # однородность ROE'_T − k_T
    lo_hi = ch("roe_k_spread.range")
    bad = [c.label for c in run.cells if _outside(c.roe_t - c.k_t, lo_hi)]
    prob = run.layers["analytical"].prob
    by_world = {}
    for w in book.get("worlds.ids"):
        cells = [c for c in run.cells if c.world == w]
        mass = sum(prob[c.key] for c in cells)
        by_world[w] = (sum(prob[c.key] * (c.roe_t - c.k_t) for c in cells) / mass if mass
                       else sum(c.roe_t - c.k_t for c in cells) / len(cells))
    gap = max(by_world.values()) - min(by_world.values())
    world_fired = gap > float(ch("roe_k_spread.max_world_gap"))
    f = _gate("roe_k_homogeneity", run, bad,
              "ROE терминала − стоимость капитала по мирам: "
              + ", ".join(f"{w} {pp(v)}" for w, v in by_world.items()) + f"; разрыв {pp(gap)}",
              by_world=by_world, gap=gap)
    if world_fired:
        f = Finding(f.name, "gate", True, 1.0, f.cells, f.message + " — больше предела книги", f.detail)
    out.append(f)
    # guidance_gap
    out.append(_guidance_gate(run))
    # capital_gap
    bad = [c.label for c in run.cells if "capital_gap" in c.flags]
    first = min((c.gap_period for c in run.cells if c.gap_period), default=None)
    out.append(_gate("capital_gap", run, bad, f"норматив ниже пола {in_cells(len(bad))}"
                     + (f", первый квартал — {period_words(first)}" if first else "") + _band_gap_words(tail),
                     first_period=first, band=None if tail is None else tail["capital_gap"]))
    bad = [c.label for c in run.cells if c.g_capped]
    out.append(_gate("k_gt_g", run, bad, f"защита роста терминала (на 1 б.п. ниже стоимости капитала) "
                                         f"сработала {in_cells(len(bad))}"))
    bad = [c.label for c in run.cells if c.roe_t <= c.g_t]
    out.append(_gate("roe_gt_g", run, bad, f"ROE терминала не выше роста {in_cells(len(bad))}"
                     + _band_capital_words(tail), band=tail))
    bad = [c.label for c in run.cells if _outside(c.terminal_share, ch("terminal_share"))]
    out.append(_gate("terminal_share", run, bad, f"доля терминала вне коридора {in_cells(len(bad))}"))
    bad = [c.label for c in run.cells if _outside(c.real_rate, ch("real_rate"))]
    out.append(_gate("real_rate", run, bad, f"реальная ставка мира вне коридора {in_cells(len(bad))}"))
    out.append(_bridge_gate(run))
    out.append(_pairs_gate(run))
    out.append(_lt_floor_gate(run))
    out.append(_off_band_gate(run, off_band))
    out.append(_crisis_gate(run))
    out.append(_overdue_gate(run, today))
    # гейты второй формы банка — только при условии включения (М§14.2)
    if book.opt("checks.growth_cut") is not None:
        out.append(_growth_cut_gate(run, tail))
    if ctx.prep.growth is not None:
        out.append(_step_gate(run))
    if book.opt("checks.cir_lt") is not None:
        out.append(_cir_lt_gate(run))
    if book.opt("checks.wholesale_share") is not None:
        out.append(_wholesale_gate(run))
    if history_test(book) == HISTORY_CAP:
        out.append(_payout_cap_gate(run))
    if book.opt(NIM_LT) is not None:
        out.append(_nim_lt_gate(run))
    if book.opt(VOLUME_SIGN) is not None or book.opt(STRESS_SIGN) is not None:
        signs = sign_numbers(run)               # готовое число не пересчитывается; нет — один раз на книгу
        if book.opt(VOLUME_SIGN) is not None:
            out.append(_volume_sign_gate(run, volume_sign if volume_sign is not None else signs["volume_sign"]))
        if book.opt(STRESS_SIGN) is not None:
            out.append(_stress_sign_gate(run, stress_sign if stress_sign is not None else signs["stress_sign"]))
    # сторожа уровней — на готовой сетке, новых сеток не считают (М§14.2)
    if book.opt(NIM_STATIONARY) is not None:
        out.append(_nim_stationary_gate(run))
    if book.opt(WINDOW_BACKTEST) is not None:
        out.append(_window_backtest_gate(run))
    if book.opt(FUNDS_COST) is not None:
        out.append(_funds_cost_gate(run))
    gates = sorted(out, key=lambda f: GATE_ORDER.index(f.name))
    return gates + [_ni_jump_flag(run)]


def _band_growth_words(tail: Mapping[str, Any] | None) -> str:
    """Добавка к сообщению гейта `growth_cut`: рост, урезанный капиталом, в прогонах полосы (М§10)."""
    part = None if tail is None else tail.get("growth_cut")
    if part is None:
        return ""
    return (f"; в полосе рост урезан {_band_share(part, tail['n'])}, наибольшая по годам доля урезанного роста "
            f"клетки в среднем по прогонам — {pct(part['cut_share'], 1)}")


def _growth_cut_gate(run: GridRun, tail: Mapping[str, Any] | None = None) -> Finding:
    """Рост портфеля урезан капиталом сильнее коридора (М§14.2): наибольшая по годам доля урезанного роста
    клетки `cut_share` (М§4.13.3) больше `checks.growth_cut.max_cut_share`. Сообщение называет и прогоны
    полосы (условие и масса гейта — печатаемой сетки)."""
    limit = float(run.ctx.book.get("checks.growth_cut.max_cut_share"))
    bad, worst = [], None
    for c in run.cells:
        top = max(((v, y) for v, y in zip(c.growth["cut_share"], c.years) if v is not None), default=None)
        if top is not None and top[0] > limit:
            bad.append(c.label)
            if worst is None or top[0] > worst[0]:
                worst = (top[0], top[1], c.label)
    msg = f"доля урезанного капиталом роста кредитных книг выше {pct(limit, 0)} {in_cells(len(bad))}"
    if worst is not None:
        msg += f"; наибольшая — {worst[2]}, конец {worst[1]} года: {pct(worst[0], 1)}"
    return _gate("growth_cut", run, bad, msg + _band_growth_words(tail), limit=limit)


def step_quarters(sc: Any, last: int) -> list[int]:
    """Кварталы ступени пола сценария (М§4.13.4): пол хотя бы одного норматива выше, чем в предыдущем квартале."""
    return [q for q in range(1, last + 1) if sc.floor20[q] > sc.floor20[q - 1] or sc.floor11[q] > sc.floor11[q - 1]]


def _step_gate(run: GridRun) -> Finding:
    """У ступени пола срезан дивиденд политики (М§14.2) — в клетках режимов без года шока: у решения модели,
    принятого в кварталах q_s − 1 … q_s + 1 у квартала ступени q_s, срезан дивиденд. Падение доли прироста в
    квартале ступени к предыдущему кварталу больше чем на `checks.step_dividend.max_lam_drop` гейт не поднимает:
    это диагностика в его сообщении (порог — для печати)."""
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    drop = ctx.book.opt("checks.step_dividend.max_lam_drop")
    bad, cuts, falls = [], [], []
    for c in run.cells:
        if prep.regimes[c.regime].shock_year is not None:
            continue
        steps = step_quarters(prep.scenarios[c.scenario], tl.Q)
        lam = c.quarters["lam"]
        cut = [d for d in c.decisions if d.source == "model" and d.cut and any(abs(d.q - s) <= 1 for s in steps)]
        fall = [] if drop is None else [(lam[s - 1] - lam[s], s) for s in steps
                                        if s >= 2 and lam[s] < lam[s - 1] - float(drop)]
        if cut:                                 # срабатывание — только срез дивиденда политики
            bad.append(c.label)
        if cut:
            cuts.append((c.label, cut[0]))
        if fall:
            falls.append(max(fall) + (c.label,))
    parts = []
    if cuts:
        label, d = cuts[0]
        parts.append(f"дивиденд политики срезан {in_cells(len(cuts))} (первая — {label}, решение за "
                     f"{period_words(d.period)})")
    note = ""
    if falls:                                   # диагностика, не срабатывание
        size, q, label = max(falls)
        note = (f"; справочно: доля прироста кредитных книг в квартале ступени упала больше чем на "
                f"{pp(float(drop), 0)} {in_cells(len(falls))} (наибольшее падение — {label}, "
                f"{period_words(tl.period(q))}: {pp(size, 0)})")
    msg = (("у ступени пола норматива: " + "; ".join(parts)) if parts else
           "у ступеней пола норматива дивиденд политики цел в клетках режимов без года шока") + note
    return _gate("step_dividend", run, bad, msg, max_lam_drop=None if drop is None else float(drop))


def _cir_lt_gate(run: GridRun) -> Finding:
    """C/I на долгосрочном участке вне цели (М§14.2): среднее упр. C/I лет от `from_year` до последнего года
    сетки отличается от `target` больше чем на `tolerance`; масса 1 или 0. Область — модальная клетка, а при
    ключе `checks.cir_lt.scope: market_layer` — слой «рыночные ставки как есть» (отношение ожидаемых агрегатов);
    число — `model.levels.cir_lt_value`, оно же у листа книги, который выводит корни расходов."""
    got = cir_lt_value(run)
    target, tol, first = got["target"], got["tolerance"], got["from_year"]
    if not got["values"]:
        return Finding("cir_lt", "gate", False, None, (), f"C/I лет с {first} года не определён")
    mean = got["value"]
    fired = abs(mean - target) > tol
    if got["scope"] == MARKET_LAYER:
        msg = (f"C/I (упр.) слоя «{lower_first(got['subject'])}» в среднем за {first}–{got['to_year']} годы — "
               f"{pct(mean, 1)} при цели {pct(target, 1)} ± {pp(tol, 1)}; модальная клетка {got['cell']} — "
               f"{pct(got['modal'], 1)}")
        return Finding("cir_lt", "gate", fired, 1.0 if fired else 0.0, (), msg,
                       {"mean": mean, "target": target, "tolerance": tol, "scope": got["scope"],
                        "modal": got["modal"]})
    msg = (f"C/I (упр.) модальной клетки {got['cell']} в среднем за {first}–{got['to_year']} годы — {pct(mean, 1)} при цели "
           f"{pct(target, 1)} ± {pp(tol, 1)}")
    return Finding("cir_lt", "gate", fired, 1.0 if fired else 0.0, (got["cell"],) if fired else (), msg,
                   {"mean": mean, "target": target, "tolerance": tol, "cell": got["cell"]})


def _nim_stationary_gate(run: GridRun) -> Finding:
    """Стационарная маржа решателя передачи вне цели (М§14.2): стационарная ЧПМ на составе баланса якоря в мире
    ключа книги, переведённая мостом в упр. базис (`model.levels.stationary_nim`), отличается от `target` больше
    чем на `tolerance`; масса 1 или 0. Сообщение называет и ключ цели ЧПМ книги — уровень мира-опоры передачи
    (у книги с ключом `nii.transmission.level_world` — названного им мира)."""
    got = stationary_nim(run.ctx)
    book = run.ctx.book
    value, target, tol = got["value"], got["target"], got["tolerance"]
    fired = abs(value - target) > tol
    msg = (f"стационарная ЧПМ (упр.) мира {got['world']} на составе баланса якоря — {pct(value)} при цели "
           f"{pct(target)} ± {pp(tol)}; ключ цели ЧПМ {book.label('terms.lt_level')} (уровень мира "
           f"{run.ctx.transmission.level_world or run.ctx.transmission.reference_world}) — {pct(got['key'])}")
    return Finding("nim_stationary", "gate", fired, 1.0 if fired else 0.0, (), msg,
                   {"value": value, "target": target, "tolerance": tol, "world": got["world"]})


def _window_backtest_gate(run: GridRun) -> Finding:
    """Уровни после фазы роста против окна фактов (М§14.2): средние упр. CoR и C/I слоя «рыночные ставки как
    есть» за годы `from_year` … последний год сетки (узел уровней, `model.levels.levels`) — вне коридоров книги;
    масса 1 или 0. Маржа гейтом не сверяется (её законно сдвигает состав баланса клеток): печатается рядом с
    долей кредитов в процентных активах и, когда книга называет окно маржи (`checks.window_backtest.nim`), —
    рядом с наибольшим кварталом окна: сведением, не условием."""
    book = run.ctx.book
    cfg = book.get(WINDOW_BACKTEST)
    node = levels(run)
    row = node["rows"]["macro_neutral"]
    bands = {"cor": [float(x) for x in cfg["cor"]], "cir": [float(x) for x in cfg["cir"]]}
    # при множителях CoR по книгам коридор окна сверяет CoR на составе якоря (окно — на своём составе, М§4.6)
    mix0 = "cor_mix0" in row
    judged = {"cor": row["cor_mix0"] if mix0 else row["cor"], "cir": row["cir"]}
    outside = [k for k in ("cor", "cir") if judged[k] is None or not bands[k][0] <= judged[k] <= bands[k][1]]
    fired = bool(outside)
    cir = cir_word(book)
    # маржа — сведением: рядом с наибольшим кварталом окна фактов, когда книга его называет
    best = ((node.get("window") or {}).get("nim") or {}).get("max")
    beside = "" if best is None else f"наибольшем квартале окна фактов {pct(best)} и "
    cor_words = (f"CoR на составе якоря {pct(row['cor_mix0'])} (на составе клеток {pct(row['cor'])})" if mix0
                 else f"CoR {pct(row['cor'])}")
    msg = (f"уровни слоя «{lower_first(LAYER_TITLES['macro_neutral'])}» в среднем за {node['from_year']}–"
           f"{node['to_year']} годы (упр.): {cor_words} при коридоре окна фактов "
           f"{band_words(bands['cor'])}, {cir} {pct(row['cir'], 1)} при коридоре {band_words(bands['cir'], 1)}; "
           f"ЧПМ {pct(row['nim'])} при {beside}доле кредитов в процентных активах {pct(row['loans_share'], 1)} — "
           "гейтом не сверяется")
    values = {"cor": row["cor"], "cir": row["cir"], "nim": row["nim"], "loans_share": row["loans_share"],
              "outside": outside}
    if mix0:
        values["cor_mix0"] = row["cor_mix0"]
    return Finding("window_backtest", "gate", fired, 1.0 if fired else 0.0, (), msg, values)


RATIO_DIGITS = 3                             # знаков отношения и его порога в сообщении гейта — одно число


def _funds_cost_gate(run: GridRun) -> Finding:
    """Стоимость средств клиентов к ключевой ставке выше порога (М§14.2): в области гейта хотя бы одного мира — клетке
    «мир × модальный режим × модальный сценарий» или, при `checks.funds_cost_to_key.scope: world_expectation` (Р10-6),
    ожидании мира — средняя стоимость средств клиентов к средней ключевой ставке за годы `from_year` … последний год сетки
    (`model.levels.funds_cost_to_key`) больше `max`. Масса — вес миров слоя «свой взгляд», где порог превышен; сообщение
    печатает числа всех миров (у ожидания мира — и модальную клетку рядом)."""
    got = funds_cost_to_key(run)
    weights = run.layers["analytical"].world_weights
    bad = [w for w, row in got["by_world"].items() if row["ratio"] > got["max"]]
    parts = ", ".join(f"{row['cell']} {num(row['ratio'], RATIO_DIGITS)}"
                      + ("" if "modal_cell" not in row else
                         f" (модальная клетка {row['modal_cell']} {num(row['modal_ratio'], RATIO_DIGITS)})")
                      for row in got["by_world"].values())
    msg = (f"стоимость средств клиентов к ключевой ставке в среднем за {got['from_year']}–{got['to_year']} годы: "
           f"{parts} при пороге {num(got['max'], RATIO_DIGITS)}")
    return Finding("funds_cost_to_key", "gate", bool(bad), sum(float(weights.get(w, 0.0)) for w in bad),
                   tuple(got["by_world"][w]["cell"] for w in bad), msg,
                   {"by_world": {w: row["ratio"] for w, row in got["by_world"].items()}, "max": got["max"]})


def _nim_lt_gate(run: GridRun) -> Finding:
    """Печатаемая маржа модальной клетки после фазы роста вне цели (М§14.2): среднее годовых упр. ЧПМ лет от
    `from_year` до последнего года сетки (`model.grid.printed_nim_lt`) отличается от `target` больше чем на
    `tolerance`; масса 1 или 0. Сообщение называет и ключ цели ЧПМ книги: печатаются оба числа."""
    got = printed_nim_lt(run)
    book = run.ctx.book
    first, last = got["from_year"], got["to_year"]
    if got["value"] is None:
        return Finding("nim_lt", "gate", False, None, (), f"ЧПМ лет с {first} года не определён")
    mean, target, tol = got["value"], got["target"], got["tolerance"]
    fired = abs(mean - target) > tol
    msg = (f"ЧПМ (упр.) модальной клетки {got['cell']} в среднем за {first}–{last} годы — {pct(mean)} при цели "
           f"{pct(target)} ± {pp(tol)}; ключ цели ЧПМ {book.label('terms.lt_level')} — "
           f"{pct(float(book.get('nii.nim_lt_target_mgmt')))}")
    return Finding("nim_lt", "gate", fired, 1.0 if fired else 0.0, (got["cell"],) if fired else (), msg,
                   {"mean": mean, "target": target, "tolerance": tol, "cell": got["cell"], "from_year": first})


def _rub(x: float) -> str:
    """Изменение в рублях со знаком: «+1,25», «−17,63»."""
    return f"{float(x):+.2f}".replace(".", ",").replace("-", "−")


def _volume_sign_gate(run: GridRun, st: Mapping[str, Any]) -> Finding:
    """Знак объёмных эффектов (М§4.5, §14.2): снятие остановки кредита в кризисе и поправок роста режимов
    снижает точку больше допуска или меняет цену мира M хуже цены мира-опоры; масса 1 или 0. Число гейта —
    `model.grid.volume_sign_test`; гейт правдоподобия, а не инвариант: на числах книги рост сверх заданного
    спросом может не создавать стоимости — это печатается и объясняется."""
    fired = not st["ok"]
    worlds = ", ".join(f"{w} {_rub(v)} ₽" for w, v in st["d_world"].items())
    msg = ("снятие остановки кредита в кризисе и поправок роста режимов"
           + (" (при выключенном ограничении роста капиталом)" if st.get("growth_constraint_off") else "")
           + f" меняет точку на {_rub(st['d_point'])} ₽ ({num(st['point'], 2)} → {num(st['point_free'], 2)} ₽); "
           f"цены миров: {worlds}; условие — точка не снижается, а цена мира {st['market_world']} меняется не "
           f"хуже цены мира {st['reference_world']}, допуск {num(st.get('tol', 0.0), 2)} ₽")
    return Finding("volume_sign", "gate", fired, 1.0 if fired else 0.0, (), msg,
                   {k: st[k] for k in ("point", "point_free", "d_point", "d_world", "ok")})


def _stress_sign_gate(run: GridRun, st: Mapping[str, Any]) -> Finding:
    """Знак стресса (М§14.2): стоимость клетки режима шока растёт при большем разовом убытке или прибыль
    последнего года сетки растёт с требованием к капиталу (по всем режимам). Число гейта —
    `model.grid.stress_sign_test`; масса — вероятность нарушивших клеток под вероятностями точки: сообщение
    называет эту базу и массу тех же клеток под весами слоя «свой взгляд», которыми взвешены массы прочих
    гейтов. Рядом с проверкой знака сообщение печатает передачу убытка в стоимость: на сколько рублей снижает
    стоимость клетки рубль убытка после налога — наименьшее и наибольшее по клеткам режима шока."""
    loss, req = st["loss"]["cells"], st["requirement"]["cells"]
    step = st["loss"]["step"]
    tol = float(run.ctx.book.get(f"{STRESS_SIGN}.tol"))
    label = lambda x, s: f"{x['world']}/{x['regime']}/{x[s]}"  # noqa: E731
    worlds = lambda rows: ", ".join(dict.fromkeys(str(x["world"]) for x in rows))  # noqa: E731
    cells = list(dict.fromkeys([label(x, "scenario") for x in loss] + [label(x, "stricter") for x in req]))
    parts = []
    if loss:
        top = max(loss, key=lambda x: x["dv"])
        parts.append(f"при разовом убытке кризиса больше на {num(step, 0)} млрд ₽ стоимость клетки растёт "
                     f"{in_cells(len(loss))} (миры: {worlds(loss)}; наибольший прирост — {label(top, 'scenario')}: "
                     f"{num(top['dv'], 1)} млрд ₽)")
    else:
        parts.append(f"при разовом убытке кризиса больше на {num(step, 0)} млрд ₽ стоимость клеток режима шока не "
                     "растёт")
    low, high = st["loss"].get("transfer_min"), st["loss"].get("transfer_max")
    if low is not None and high is not None:    # сколько стоимости снимает рубль убытка — по всем клеткам режима шока
        span = num(low, 2) if low == high else f"от {num(low, 2)} до {num(high, 2)}"
        parts[-1] += f"; снижение стоимости клетки на рубль убытка после налога — {span} ₽"
    if req:
        top = max(req, key=lambda x: x["d_profit"])
        n = len({(x["world"], x["regime"], x["stricter"]) for x in req})
        parts.append(f"при более высоком требовании к капиталу прибыль последнего года сетки выше {in_cells(n)} "
                     f"(миры: {worlds(req)}; наибольшее превышение — {label(top, 'stricter')} против "
                     f"{label(top, 'looser')}: {num(top['d_profit'], 1)} млрд ₽)")
    else:
        parts.append("прибыль последнего года сетки с требованием к капиталу не растёт")
    msg = "; ".join(parts) + f"; допуск {num(tol, 1)} млрд ₽"
    if cells:                                   # база массы — не та, что у прочих гейтов: названа словами
        msg += "; масса — под вероятностями точки"
        if st.get("mass_analytical") is not None:
            msg += f" (под весами слоя «свой взгляд» те же клетки — {pct(st['mass_analytical'], 1)})"
    return Finding("stress_sign", "gate", not st["ok"], float(st["mass"]), tuple(cells), msg,
                   {"max_excess": st["max_excess"], "loss": len(loss), "requirement": len(req),
                    "mass_basis": "point", "mass_analytical": st.get("mass_analytical")})


def _wholesale_gate(run: GridRun) -> Finding:
    """Доля оптового фондирования вне коридора (М§14.2): в клетке на конец какого-либо года сетки
    `wholesale / (funds + wholesale)` вне `checks.wholesale_share` — сторож правила премии средств клиентов. Средства
    клиентов — книги `model.levels.client_funds` (при `checks.client_funds: clients` — без ведомых книг К6, Р10-1)."""
    ctx = run.ctx
    tl = ctx.timeline
    lo, hi = (float(v) for v in ctx.book.get("checks.wholesale_share"))
    ends = [q for q in (tl.quarters_of_year(y)[-1] for y in run.cells[0].years) if 1 <= q <= tl.Q]
    bad, span = [], None
    for c in run.cells:
        shares = [c.quarters["wholesale"][q] / (client_funds_end(ctx, c, q) + c.quarters["wholesale"][q]) for q in ends]
        if any(not lo <= v <= hi for v in shares):
            bad.append(c.label)
            span = (min(shares + ([span[0]] if span else [])), max(shares + ([span[1]] if span else [])))
    msg = (f"доля оптового фондирования на конец года вне коридора {band_words((lo, hi), 0)} {in_cells(len(bad))}"
           + (f" (размах {band_words(span, 1)})" if span else ""))
    return _gate("wholesale_share", run, bad, msg, span=span)


def _payout_cap_gate(run: GridRun) -> Finding:
    """Базовая выплата года по политике выше потолка `dividends.policy.cap` от прибыли акционеров клетки
    (М§5.2, §14.2): Σ base_div × N_iss / N_out по решениям клетки за год прибыли; у записи реестра base_div —
    её дивиденд. Догоняющая выплата и доля избытка в сравнение не входят. Клетка потолок не применяет —
    превышение показывает гейт. Решение года в годовом режиме одно; при квартальном календаре — решения за
    кварталы прибыли года плюс строки истории его закрытых кварталов (DPS × N_iss, М§5.7.5). Сравнение — с
    допуском равенства (относительный, точность счёта: выплата ровно на потолке — не превышение) и с допуском
    книги `checks.payout_cap.tolerance` в долях прибыли года (без ключа — ноль)."""
    ctx = run.ctx
    cap = float(ctx.book.get("dividends.policy.cap"))
    slack = float(ctx.book.opt("checks.payout_cap.tolerance", 0.0))
    af = ctx.prep.af
    gross = af.n_iss / af.n_out                 # уменьшение BV → сумма на все размещённые акции
    cal = ctx.prep.calendar
    closed = {} if cal is None else {y: dps * af.n_iss / 1000 for y, dps in cal.closed_dps.items() if dps}
    bad, worst = [], None
    for c in run.cells:
        over = []
        for year in c.dps:
            ni = c.annual["ni_sh"][c.years.index(year)] if year in c.years else None
            if ni is None:
                continue
            if "n_out" in c.quarters:           # выкуп (М§5.6): решение — на акциях клетки в квартале решения
                paid = sum(d.base_div * af.n_iss / c.quarters["n_out"][d.q] for d in c.decisions if d.year == year)
            else:
                paid = sum(d.base_div for d in c.decisions if d.year == year) * gross
            if year in closed:
                paid += closed[year]
            limit = (cap + slack) * max(ni, 0.0)         # год убытка: потолок — ноль, нулевая выплата его не выше
            if paid > limit + REL_TOL * max(1.0, limit):
                over.append((paid / ni if ni > 0 else float("inf"), year))
        if over:
            bad.append(c.label)
            top = max(over)
            if worst is None or top[0] > worst[0]:
                worst = (top[0], top[1], c.label)
    msg = (f"базовая выплата года выше потолка политики {pct(cap, 0)} прибыли акционеров"
           + (f" больше чем на {pp(slack)}" if slack else "") + f" {in_cells(len(bad))}")
    if worst is not None:
        level = "прибыль года не положительна" if worst[0] == float("inf") else pct(worst[0])
        msg += f"; наибольшая — {worst[2]}, {worst[1]} год: {level}"
    return _gate("payout_cap", run, bad, msg, cap=cap, tolerance=slack)


ANCHOR_NIM_WORDS = "ЧПМ якоря ({value})"    # маржа якоря в сообщении гейта стыка без подписи книги
REPORTED_DIGITS = 1                         # знаков отчётной упр. маржи квартала — как на экране истории


def _anchor_nim_words(run: GridRun, value: float) -> str:
    """Маржа якоря в сообщении гейта `nim_path_joint`. Гейт сравнивает с маржой якоря по книгам ядра, переведённой
    мостом в упр. базис (`value`); экран истории печатает отчётную упр. маржу квартала якоря (`reported`, факты
    `mgmt_quarterly`) — их разность равна дрейфу моста. Подпись книги `meta.labels.gates.nim_anchor` называет
    базис и ставит обе величины; без подписи — прежние слова."""
    ctx = run.ctx
    if ctx.book.opt("meta.labels.gates.nim_anchor") is None:
        return ANCHOR_NIM_WORDS.format(value=pct(value))
    path = f"quarters.{ctx.timeline.anchor}.nim"
    reported = ctx.facts.v("mgmt_quarterly", path) if ctx.facts.has("mgmt_quarterly", path) else None
    return ctx.book.label("gates.nim_anchor", value=pct(value),
                          reported="не раскрыта" if reported is None else pct(reported, REPORTED_DIGITS))


def _nim_joint_gate(run: GridRun) -> Finding:
    """Стык ближнего пути ЧПМ и сквозь цикл (М§14.2): первые N кварталов не выше
    max(ЧПМ якоря, Nss мира) + допуск, всё в упр. базисе через мост."""
    ctx, book = run.ctx, run.ctx.book
    br, tr = ctx.bridge, ctx.transmission
    n = int(book.get("checks.nim_path_joint.quarters"))
    tol = float(book.get("checks.nim_path_joint.tolerance"))
    nim0 = ctx.facts.need("nii_books", "nim_eng_q")
    bad, worst = [], []
    for c in run.cells:
        cap = max(br.to_mgmt_nim(nim0), br.to_mgmt_nim(tr.nss[c.world])) + tol
        over = [(q, br.to_mgmt_nim(c.quarters["nim"][q])) for q in range(1, min(n, ctx.timeline.Q) + 1)
                if c.quarters["nim"][q] is not None and br.to_mgmt_nim(c.quarters["nim"][q]) > cap]
        if over:
            bad.append(c.label)
            q, v = max(over, key=lambda t: t[1] - cap)
            worst.append((v - cap, c.label, ctx.timeline.period(q), v, cap))
    msg = (f"ЧПМ (упр.) первых {n} кварталов выше большего из {_anchor_nim_words(run, br.to_mgmt_nim(nim0))} и ЧПМ "
           f"{book.label('terms.lt_level')} мира более чем на {pp(tol)} {in_cells(len(bad))}")
    if worst:
        _, lab, per, v, cap = max(worst)
        msg += f"; наибольшее превышение — {lab}, {period_words(per)}: {pct(v)} при пороге {pct(cap)}"
    return _gate("nim_path_joint", run, bad, msg,
                 nss_mgmt={w: br.to_mgmt_nim(v) for w, v in tr.nss.items()}, nim0_mgmt=br.to_mgmt_nim(nim0))


def _pairs_gate(run: GridRun) -> Finding:
    """Парные передачи соседних по key^LT миров в коридоре книги (М§4.5, §14.2); масса 1."""
    tr, book = run.ctx.transmission, run.ctx.book
    lo, hi = (float(x) for x in book.get("checks.transmission_pairs"))
    parts, fired = [], False
    for key, v in tr.pairs.items():
        if v is None:
            parts.append(f"{key.replace('_', '→')}: не определена (долгосрочные ключевые миров равны)")
            continue
        out = not lo <= v <= hi
        fired |= out
        parts.append(f"{key.replace('_', '→')} {num(v)} — {'вне коридора' if out else 'в коридоре'} "
                     f"{num(lo, 2)}…{num(hi, 2)}")
    return Finding("transmission_pairs", "gate", fired, 1.0 if fired else 0.0, (),
                   "; ".join(parts) or "пар миров нет", {"pairs": dict(tr.pairs)})


def share_axis_ends(book: Any) -> list[dict[str, float]]:
    """Углы области осей долей `nii.sigma0_split` и `nii.phi_split` (М§4.5): сочетания концов осей полосы
    по этим ключам, кроме самих значений книги. Эффективный LT-спред линеен по обеим долям, поэтому
    наименьший спред на осях — в одном из углов."""
    ends: list[list[tuple[str, float]]] = []
    for ax in book.get("valuation.uncertainty.axes") or []:
        paths = [p for p in ax.get("paths") or [] if p in SHARE_KEYS]
        if ax.get("kind") == "bundle" and paths:          # связка: конец доли — по её пути
            ends.append([(p, float(ax[end][p])) for p in paths for end in ("low", "high")])
            continue
        if ax.get("kind") != "value" or not paths:
            continue
        ends.append([(p, float(end)) for p in paths for end in (ax["low"], ax["high"])])
    corners = [dict(combo) for combo in itertools.product(*ends)] if ends else []
    centre = {p: float(book.get(p)) for p in SHARE_KEYS}
    out: list[dict[str, float]] = []
    for corner in corners:
        if any(corner[p] != centre[p] for p in corner) and corner not in out:
            out.append(corner)
    return out


def _lt_floor_gate(run: GridRun) -> Finding:
    """Эффективный LT-спред кредитной книги к опоре в стационаре мира ниже пола книги (М§4.5, §14.2).

    Проверяется при значениях книги и в углах области осей долей `nii.sigma0_split`, `nii.phi_split`:
    оси долей обязаны лежать там, где гейт проходит, — иначе половина прогонов полосы считалась бы на
    кредитных спредах ниже пола. Масса — вес миров слоя «свой взгляд», где условие нарушено хотя бы у одной
    кредитной книги (при значениях книги или в углу осей)."""
    ctx, book = run.ctx, run.ctx.book
    floors = book.get("checks.lt_spread_floor")

    def below(lt_spread: Mapping[str, Mapping[str, float]]) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for b, row in lt_spread.items():
            if b not in floors:
                raise BookError(f"checks.lt_spread_floor.{b}: нет пола кредитной книги (М§14.2)")
            floor = float(floors[b])
            for w, s in row.items():
                if s < floor:
                    found.setdefault(w, []).append(f"{lower_first(book.book_name(b))} {pp(s)} при поле {pp(floor)}")
        return found

    def worlds_text(found: Mapping[str, Sequence[str]]) -> str:
        return "; ".join(f"мир {w} — {', '.join(v)}" for w, v in found.items())

    bad = below(ctx.transmission.lt_spread)
    corners = share_axis_ends(book)
    at_ends = []
    for corner in corners:
        found = below(solve_transmission(book.with_overrides(corner), ctx.facts, ctx.bridge).lt_spread)
        if found:
            at_ends.append({"shares": corner, "worlds": sorted(found), "text": worlds_text(found)})
    worlds = sorted(set(bad) | {w for e in at_ends for w in e["worlds"]})
    cells = [c.label for c in run.cells if c.world in worlds]
    if bad:
        msg = "долгосрочный спред кредитной книги к опорной ставке ниже пола: " + worlds_text(bad)
    elif at_ends:
        msg = ("долгосрочный спред кредитной книги к опорной ставке ниже пола на концах осей долей: "
               + "; ".join("при " + ", ".join(f"{SHARE_WORDS[p]} {pct(v, 1)}" for p, v in e["shares"].items())
                           + f" — {e['text']}" for e in at_ends))
    else:
        msg = "долгосрочные спреды кредитных книг к опорным ставкам не ниже полов во всех мирах" \
            + (" — при значениях книги и на концах осей долей" if corners else "")
    return _gate("lt_spread_floor", run, cells, msg, worlds=worlds,
                 lt_spread={b: dict(row) for b, row in ctx.transmission.lt_spread.items()},
                 axis_ends=[{"shares": e["shares"], "worlds": e["worlds"]} for e in at_ends])


def _off_band_gate(run: GridRun, off_band: Mapping[str, Any] | None) -> Finding:
    """|Σ сдвигов положения осей вне полосы| > print_step / 2 (М§10, §14.2); масса 1; пусто — молчит."""
    book = run.ctx.book
    axes = book.get("valuation.uncertainty.off_band_axes") or []
    if not axes:
        return Finding("off_band_shift", "gate", False, 0.0, (), "все оси книги — в полосе", {"rub": 0.0, "axes": 0})
    if off_band is None:
        from model.uncertainty import off_band_shift          # полоса импортирует сетку, не наоборот
        off_band = off_band_shift(book, run.ctx.facts, run.ctx.live, run.point)
    rub, limit = float(off_band["rub"]), float(off_band["limit"])
    fired = abs(rub) > limit
    msg = (f"оси вне полосы ({len(axes)}) сдвигают заголовок на {num(rub, 2)} ₽ при пороге {num(limit, 2)} ₽ "
           f"(половина шага печати)")
    return Finding("off_band_shift", "gate", fired, 1.0 if fired else 0.0, (), msg,
                   {"rub": rub, "limit": limit, "axes": len(axes)})


def _key_before(run: GridRun) -> dict[int, float | None]:
    """Средняя ключевая кварталов до сетки (q ≤ 0): факты `pnl_quarterly → key_avg`, якорь — nii_books."""
    tl, facts = run.ctx.timeline, run.ctx.facts
    out: dict[int, float | None] = {}
    for per, row in facts.periods("pnl_quarterly").items():
        q = tl.index(per)
        if q <= 0:
            node = row.get("key_avg")
            out[q] = float(node["v"]) if isinstance(node, Mapping) and node.get("v") is not None else None
    anchor = facts.v("nii_books", "key_avg_anchor_q") if facts.has("nii_books", "key_avg_anchor_q") else None
    if anchor is not None:
        out[0] = anchor
    return out


def _ni_jump_flag(run: GridRun) -> Finding:
    """Флаг «прыжок ЧП» (М§14.3): клетки (W, norm, schedule), первые N кварталов, г/г > порога при
    неизменной ключевой; кварталы до сетки — факты (ЧП акционерам и средняя ключевая)."""
    ctx, book = run.ctx, run.ctx.book
    tl = ctx.timeline
    n = int(book.get("checks.ni_jump.quarters"))
    yoy_max = float(book.get("checks.ni_jump.yoy"))
    key_tol = float(book.get("checks.ni_jump.key_tol"))
    keys_before = _key_before(run)
    hist = ctx.prep.hist["ni_sh"]
    profit = book.label("terms.profit_short")
    jumps, cells = [], []
    for w in book.get("worlds.ids"):
        try:
            c = run.cell(w, REFERENCE_REGIME, REFERENCE_SCENARIO)
        except KeyError:
            continue
        key_w = ctx.worlds[w].key
        for q in range(1, min(n, tl.Q) + 1):
            j = q - 4
            ni_prev = c.quarters["ni_sh"][j] if j >= 1 else hist.get(j)
            key_prev = key_w[j] if j >= 1 else keys_before.get(j)
            ni_now = c.quarters["ni_sh"][q]
            if ni_prev is None or key_prev is None or ni_now is None or ni_prev <= 0:
                continue
            growth = ni_now / ni_prev - 1
            if growth > yoy_max and abs(key_w[q] - key_prev) <= key_tol:
                jumps.append(f"{c.label}, {period_words(tl.period(q))}: {profit} г/г {pct(growth, 0)} при ключевой "
                             f"{pct(key_prev)} → {pct(key_w[q])}")
                if c.label not in cells:
                    cells.append(c.label)
    detail = ("; ".join(jumps[:6]) + (f" … и ещё {len(jumps) - 6}" if len(jumps) > 6 else "")) if jumps else None
    return Finding("ni_jump", "flag", bool(jumps), None, tuple(cells),
                   detail or f"{profit} первых {n} кварталов г/г не выше {pct(yoy_max, 0)} при неизменной ключевой",
                   {"jumps": jumps, "quarters": n, "yoy": yoy_max, "key_tol": key_tol})


BRIDGE_WORDS = {"cor": "стоимость риска", "nim": "ЧПМ"}


GUIDANCE_METRICS = {"nim": "nim", "cor_max": "cor", "cir": "cir"}     # ключ гайденса → метрика моста
GUIDANCE_GROWTH = ("op_np_growth", "dps_growth")                      # узлы роста к прошлому году (М§14.2)


def guidance_bases(run: GridRun, year: int, keys: Any) -> dict[str, float]:
    """Базы прошлого года узлов роста из `keys` (М§14.2): `op_np_growth` — прибыль акционеров четырёх кварталов
    года Y − 1 (факты ОПУ), `dps_growth` — сумма DPS строк истории дивидендов за год Y − 1. Нет числа или база
    не положительна — FactsError: гейт отвечает «гайденс не прочитан»."""
    ctx, tl = run.ctx, run.ctx.timeline
    out: dict[str, float] = {}
    if "op_np_growth" in keys:
        hist = ctx.prep.hist["ni_sh"]
        qs = tl.quarters_of_year(year - 1)
        missing = [tl.period(q) for q in qs if q not in hist]
        if missing:
            raise FactsError(f"pnl_quarterly: нет прибыли акционеров за {', '.join(missing)} — база роста прибыли "
                             f"{year} года не определена (М§14.2)")
        out["op_np_growth"] = sum(hist[q] for q in qs)
    if "dps_growth" in keys:
        rows = [r for r in ctx.facts.file("dividends").get("history") or [] if int(r["year"]) == year - 1]
        dps = [history_dps(r) for r in rows]
        if not dps or None in dps:
            raise FactsError(f"dividends.history: нет DPS за {year - 1} год — база роста дивиденда {year} года "
                             "не определена (М§14.2)")
        out["dps_growth"] = sum(dps)
    for key, base in out.items():
        if not base > 0:
            raise FactsError(f"гайденс {key}: база прошлого года {base:g} не положительна — рост не определён")
    return out


def guidance_values(run: GridRun, cell: Any, year: int, bases: Mapping[str, float] | None = None
                    ) -> dict[str, float | None]:
    """Путь года гайденса клетки: ROE — одного определения; ЧПМ, CoR и CIR — в упр. базисе по правилу «год с
    отчётными кварталами» (М§4.6); узлы роста — прибыль акционеров и DPS года клетки к базам прошлого года
    (`guidance_bases`; без баз их нет). Одна функция у гейта и у выпуска (`guidance.items[].mass_outside`)."""
    i = cell.years.index(year)
    row = lambda name, q: cell.quarters[name][q]  # noqa: E731
    out: dict[str, float | None] = {"roe": cell.annual["roe"][i]}
    for key, metric in GUIDANCE_METRICS.items():
        out[key] = year_mgmt(run.ctx, metric, year, cell.annual[metric][i], row)
    bases = bases or {}
    if "op_np_growth" in bases:
        ni = cell.annual["ni_sh"][i]
        out["op_np_growth"] = None if ni is None else ni / bases["op_np_growth"] - 1
    if "dps_growth" in bases:
        dps = cell.dps.get(year)
        out["dps_growth"] = None if dps is None else dps / bases["dps_growth"] - 1
    return out


def _guidance_gate(run: GridRun) -> Finding:
    """Путь года гайденса против узлов фактов по перечню книги `checks.guidance_items` (пункты с `gate: true`;
    слова сообщения — поле `words` пункта; М§14.2)."""
    ctx = run.ctx
    facts = ctx.facts
    items = [it for it in ctx.book.get("checks.guidance_items") if it.get("gate")]
    words = {str(it["key"]): str(it["words"]) for it in items}
    try:
        year = int(facts.plain("guidance", "year"))
        nodes = {str(it["key"]): facts.node("guidance", str(it["path"])) for it in items}
    except FactsError as exc:
        return Finding("guidance_gap", "gate", False, None, (), f"гайденс не прочитан: {exc}")
    # ЧПМ, CoR и CIR — в упр. базисе: отчётные кварталы — раскрытым упр. фактом, прогнозные — мостом
    # (М§4.6, §14.2); ROE — одного определения; узлы сектора (scope: sector) гейт не берёт
    years = run.cells[0].years
    if year not in years:
        return Finding("guidance_gap", "gate", False, 0.0, (), f"год гайденса {year} вне сетки")
    bands = {}
    for k, node in nodes.items():
        if node.get("v") is None or node.get("scope") == "sector":
            continue
        bands[k] = guidance_band(node)
    try:
        bases = guidance_bases(run, year, bands)
    except FactsError as exc:
        return Finding("guidance_gap", "gate", False, None, (), f"гайденс не прочитан: {exc}")
    bad, why = [], {}
    for c in run.cells:
        vals = guidance_values(run, c, year, bases)
        miss = [k for k, b in bands.items() if vals.get(k) is not None and not inside(b, vals[k])]
        if miss:
            bad.append(c.label)
            for k in miss:
                why.setdefault(k, []).append(vals[k])
    msg = "; ".join(f"{words[k]}: {band_words((min(v), max(v)))} против гайденса {band_words(bands[k])}"
                    for k, v in why.items())
    return _gate("guidance_gap", run, bad, f"путь {year} года вне гайденса ({msg})" if bad
                 else f"путь {year} года внутри гайденса", bands={k: list(b) for k, b in bands.items()},
                 outside=sorted(why))


def _bridge_gate(run: GridRun) -> Finding:
    ctx, book = run.ctx, run.ctx.book
    facts = ctx.facts
    fired, parts = False, []
    for x, value in (("cor", ctx.bridge.cor_value), ("nim", ctx.bridge.nim_value)):
        hist = facts.file("bridge_mgmt_ifrs").get(x, {}).get("history") or []
        word = BRIDGE_WORDS[x]
        if not hist:
            parts.append(f"{word}: истории моста нет — не проверено")
            continue
        last = hist[-1]
        gap = last.get("gap")
        gap = gap.get("v") if isinstance(gap, Mapping) else gap
        when = period_words(last.get("period"))
        if gap is None:
            parts.append(f"{word}: разность за {when} не раскрыта")
            continue
        limit = float(book.get(f"checks.bridge_drift_pp.{x}"))
        drift = abs(float(gap) - value)
        parts.append(f"{word}, {when}: разность упр. ↔ МСФО {pp(float(gap))} при мосте {pp(value)} — дрейф "
                     f"{pp(drift)} {'больше' if drift > limit else 'не больше'} предела {pp(limit)}")
        fired |= drift > limit
    return Finding("bridge_drift", "gate", fired, 1.0 if fired else 0.0, (), "; ".join(parts))


def _crisis_gate(run: GridRun) -> Finding:
    ctx, book = run.ctx, run.ctx.book
    tl = ctx.timeline
    from model.worlds import MARKET_WORLD
    crisis = [r for r, rp in ctx.prep.regimes.items() if rp.shock_year is not None]
    if not crisis:
        return Finding("m_crisis_vs_cbr", "gate", False, 0.0, (), "кризисного режима нет")
    r = crisis[0]
    shock = int(ctx.prep.regimes[r].shock_year)
    cfg = book.get("checks.m_crisis_vs_cbr")
    bad, why = [], []
    for c in run.cells:
        if c.world != MARKET_WORLD or c.regime != r:
            continue
        loans = c.quarters["loans"]
        reasons = []
        for y, rng in cfg["loan_growth"].items():
            y = int(y)
            q_end, q_prev = tl.index(f"{y}Q4"), tl.index(f"{y - 1}Q4")
            if 0 <= q_prev and q_end <= tl.Q:
                g = loans[q_end] / loans[q_prev] - 1
                if _outside(g, rng):
                    reasons.append(f"рост кредита {y} года {pct(g, 1)} вне {band_words(rng, 1)}")
        if shock in c.years:
            cor = c.annual["cor"][c.years.index(shock)]
            if cor is not None and ctx.bridge.to_mgmt_cor(cor) < float(cfg["cor_shock_year"]):
                reasons.append(f"CoR {shock} года (упр.) {pct(ctx.bridge.to_mgmt_cor(cor))} ниже "
                               f"{pct(float(cfg['cor_shock_year']))}")
        if c.n20_min > float(cfg["n20_min"]):
            reasons.append(f"минимум {book.label('capital.n20_short')} {pct(c.n20_min)} выше "
                           f"{pct(float(cfg['n20_min']))}")
        if reasons:
            bad.append(c.label)
            why.append(f"{c.label}: " + ", ".join(reasons))
    return _gate("m_crisis_vs_cbr", run, bad, "; ".join(why) if why else "клетки M × кризис не мягче сценария ЦБ")


FORM_EVENT = "form805"                       # событие календаря: вышла форма с нормативами группы
DECISION_EVENT = "dividend_decision"         # событие календаря: решение собрания о дивиденде за квартал прибыли


def _overdue_from(event: Mapping[str, Any]) -> _dt.date | None:
    """Дата отсчёта просрочки события календаря (М§14.2): у события с `estimated: true` (дата названа
    составителем, событие могло ещё не наступить) — поле `latest`, без него ветвь по событию не срабатывает;
    у события без `estimated` — `date`."""
    raw = event.get("latest") if event.get("estimated") is True else event.get("date")
    try:
        return _dt.date.fromisoformat(str(raw))
    except ValueError:
        return None


def _overdue_gate(run: GridRun, today: _dt.date) -> Finding:
    ctx, book = run.ctx, run.ctx.book
    try:
        events = ctx.facts.file("calendar").get("events") or []
    except FactsError:
        return Finding("manual_input_overdue", "gate", False, None, (), "календаря нет")
    days = book.get("checks.manual_overdue_days")
    anchor_q = ctx.timeline.index(ctx.timeline.anchor)
    curve = _dt.date.fromisoformat(str(book.get("worlds.source.curve_date")))
    declared = {r.year for r in ctx.live.register if r.status in ("declared", "paid")}
    cal = ctx.prep.calendar                      # квартальный календарь дивидендов: событие — решение за квартал
    periods = {str(r.period) for r in ctx.live.register if r.status in DECLARED and r.period}
    estimated = bool(ctx.prep.af.estimated)      # норматив якоря стоит оценкой до выхода формы (М§3.3)
    late = []
    for ev in events:
        d = _overdue_from(ev)
        if d is None:
            continue
        kind, covers = ev.get("kind"), ev.get("covers")
        if kind == "ifrs" and covers and ctx.timeline.index(str(covers)) > anchor_q:
            if (today - d).days > int(days["ifrs_fact"]):
                late.append(f"МСФО за {period_words(covers)} ({d})")
        elif kind == "cbr_forecast" and curve < d and (today - d).days > int(days["worlds_after_cbr"]):
            late.append(f"прогноз ЦБ {d}")
        elif (kind == "agm" and cal is None and (today - d).days > int(days["dividend_register"])
              and d.year - 1 not in declared):
            late.append(book.label("register.overdue_item", date=d, **record_fields(book, d.year - 1)))
        elif (kind == DECISION_EVENT and cal is not None and covers and str(covers) not in periods
              and (today - d).days > int(days["dividend_register"])
              and not cal.closed(ctx.timeline.index(str(covers)))):
            # решение собрания прошло, записи declared | paid за квартал прибыли нет (закрытый квартал записи
            # не ждёт: его решение — строка истории фактов, М§5.7.2)
            late.append(book.label("register.overdue_item", date=d, **record_fields(
                book, ctx.timeline.year(ctx.timeline.index(str(covers))), str(covers))))
        elif (kind == FORM_EVENT and estimated and covers == ctx.timeline.anchor and "capital_form" in days
              and (today - d).days > int(days["capital_form"])):
            late.append(f"{lower_first(str(ev.get('title') or 'форма с нормативами'))} ({d}) вышла, оценка "
                        "нормативов якоря не заменена фактом")
    fired = bool(late)
    return Finding("manual_input_overdue", "gate", fired, 1.0 if fired else 0.0, (),
                   "просрочен ручной вход: " + "; ".join(late) if late else "ручные входы не просрочены")


# ------------------------------------------------------------------ объяснения гейтов


def _parse_until(key: str, raw: Any) -> _dt.date | None:
    if raw is None:
        return None
    if isinstance(raw, _dt.datetime):
        return raw.date()
    if isinstance(raw, _dt.date):
        return raw
    try:
        return _dt.date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError(f"gate_explanations.yaml, {key}: valid_until = {raw!r} — не дата ГГГГ-ММ-ДД") from None


def load_gate_explanations(path: Path | None = None, *, today: _dt.date | None = None
                           ) -> Mapping[str, Mapping[str, Any]]:
    """Объяснения гейтов; действуют включительно по `valid_until`."""
    path = Path(path) if path else EXPLANATIONS_PATH
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    today = today or _dt.date.today()
    out = {}
    for key, spec in raw.items():
        spec = spec or {}
        until = _parse_until(key, spec.get("valid_until"))
        rng = spec.get("expected_mass_range")
        if rng is not None:
            if not isinstance(rng, (list, tuple)) or len(rng) != 2 or not 0 <= float(rng[0]) <= float(rng[1]) <= 1:
                raise ValueError(f"gate_explanations.yaml, {key}: expected_mass_range = {rng!r}")
            rng = (float(rng[0]), float(rng[1]))
        stale = until is not None and until < today
        out[str(key)] = {"explanation": str(spec.get("explanation", "")).strip(),
                         "expected_mass": spec.get("expected_mass"), "expected_mass_range": rng,
                         "valid_until": until, "stale": stale,
                         "expiring": (not stale and until is not None and 0 <= (until - today).days <= WARN_DAYS)}
    return out


@dataclass(frozen=True)
class GateStatus:
    name: str
    fired: bool
    mass: float | None
    status: str                            # quiet | explained | unexplained | expired | mass_off
    explanation: str | None
    expected_mass: float | tuple[float, float] | None
    valid_until: _dt.date | None
    expiring: bool


def mass_corridor(expected: float | tuple[float, float] | None) -> tuple[float, float] | None:
    if expected is None:
        return None
    lo, hi = expected if isinstance(expected, tuple) else (float(expected), float(expected))
    return (lo * MASS_LOW[0] - MASS_LOW[1], hi * MASS_HIGH[0] + MASS_HIGH[1])


def gate_statuses(findings: Sequence[Finding], explanations: Mapping, *, today: _dt.date) -> list[GateStatus]:
    out = []
    for f in findings:
        if f.kind != "gate":
            continue
        spec = explanations.get(f.name)
        expected = None
        if spec:
            expected = spec.get("expected_mass_range") or spec.get("expected_mass")
            if isinstance(expected, list):
                expected = (float(expected[0]), float(expected[1]))
        until = spec.get("valid_until") if spec else None
        if isinstance(until, str):
            until = _parse_until(f.name, until)
        stale = until is not None and until < today
        expiring = bool(spec) and not stale and until is not None and 0 <= (until - today).days <= WARN_DAYS
        if not f.fired:
            status = "quiet"
        elif not spec:
            status = "unexplained"
        elif stale:
            status = "expired"
        else:
            corridor = mass_corridor(expected)
            if corridor is not None and f.mass is not None and not corridor[0] <= f.mass <= corridor[1]:
                status = "mass_off"
            else:
                status = "explained"
        out.append(GateStatus(name=f.name, fired=f.fired, mass=f.mass, status=status,
                              explanation=spec.get("explanation") if spec else None,
                              expected_mass=expected, valid_until=until, expiring=expiring))
    return out
