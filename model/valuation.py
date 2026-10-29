"""Оценка клетки: остаточный доход (печать) и дивидендная модель (инвариант), терминал (М§6–§7).

V_RI  = BV_v + Σ RI_q DF_v(τ_q) + DF_v(τ_Q) TV_RI,   RI_q = CI_q − k_q BV_(q−1) (q0: доля 1 − e);
V_DDM = Σ Div_q DF_v(τ_q) + DF_v(τ_Q) TV_DDM.
Равенство алгебраическое (телескопическая сумма) при совокупном ROE в RI,
k_q = DF_(q−1)/DF_q − 1, дивиденде в квартал ГОСА, делителе без собственных акций
и одном множителе времени терминала у обеих форм (М§6.4).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from model.book_schema import FIXED_PARTS, BookError
from model.worlds import Discount

# Защита роста терминала: g_T не выше k_T − 1 б.п. (гейт k_gt_g, М§7).
G_BELOW_K = 0.0001
FADE_MODE = "valuation.terminal.fade_mode"   # вид угасания избыточной доходности терминала (М§7)
FIXED_SHARE = "valuation.terminal.fixed_growth_share"   # λ_F — доля запаса постоянных частей в бизнесе за T (М§7)
FIXED_PARTS_KEY = "valuation.terminal.fixed_parts"     # части блока постоянных частей (М§7); нет ключа — все
ONE_SIDED, SYMMETRIC = "one_sided", "symmetric"
# Терминал, сверенный с явными годами (К-Т2, М§7). Ключи необязательны; нет ключа — прежние строки.
YEAR_BASIS = "valuation.terminal.year_basis"           # год терминала (К-Т2а): calendar (и без ключа) | mean
FADE_ANCHOR = "valuation.terminal.fade_anchor_year"    # год-якорь угасания Y_a (К-Т2в): срок схода — после него
FIXED_FUNDING = "valuation.terminal.fixed_funding"     # ставка фондирования блока К-Т (К-Т2б): binary (и без ключа) |
#                                                        balancing
CALENDAR, MEAN = "calendar", "mean"
FUNDING_BINARY, FUNDING_BALANCING = "binary", "balancing"
MEAN_YEAR = 365.2425                         # средняя длина года (григорианская), дней
FADE_ITER = 200                              # потолок шагов бисекции срока угасания n_W (К-Т2в)
NAMED_LITERALS = {
    365.2425: "MEAN_YEAR: средняя длина года (григорианская), дней — год терминала (К-Т2а, М§7)",
    200: "FADE_ITER: потолок шагов бисекции срока угасания (К-Т2в, М§7)",
}


def year_basis(book) -> str:
    """Год терминала (К-Т2а, М§7): ключ `valuation.terminal.year_basis` — `mean` (вечный поток терминала — средний год
    365,2425 дня) или `calendar` (и без ключа: год L как есть — у високосного L 366 дней процентов навсегда)."""
    return str(book.opt(YEAR_BASIS, CALENDAR))


def fixed_funding(book) -> str:
    """Ставка фондирования блока постоянных частей (К-Т2б, М§7): `balancing` — по правилу балансирующих статей
    (связанность минимума ликвидности после выплаты избытка и минимум на постоянных активах), `binary` (и без ключа) —
    ставка опта при доборе опта на конце сетки, иначе смесь балансирующих. Читается только при блоке (λ_F задан):
    без него — `binary` (ключ неактивного режима)."""
    if book.opt(FIXED_SHARE) is None:
        return FUNDING_BINARY
    return str(book.opt(FIXED_FUNDING, FUNDING_BINARY))


def fade_anchor(book) -> int | None:
    """Год-якорь угасания Y_a (К-Т2в, М§7): срок схода избытка идёт после него по календарю; нет ключа — None (срок
    после T). Y_a позже года `last_period` — отказ: срок начинался бы внутри явных лет."""
    value = book.opt(FADE_ANCHOR)
    if value is None:
        return None
    last = int(str(book.get("meta.last_period"))[:4])
    if int(value) > last:
        raise BookError(f"{FADE_ANCHOR} = {value}: год-якорь угасания позже года last_period {last} — срок угасания "
                        "начинался бы внутри явных лет (М§7)")
    return int(value)


def fade_of(n: float, k: float, g: float, s: float = 0.0) -> float:
    """Множитель угасания при линейном сходе избытка к нулю за n лет после года-якоря, s — лет явного участка после
    якоря (М§7, справочная формула с началом s): (k − g)/(1 + k) Σ_(t ≥ 1) max(0, 1 − (t − 1 + s)/n) [(1 + g)/(1 + k)]^(t−1);
    n = ∞ — 1."""
    if n == float("inf"):
        return 1.0
    x = (1 + g) / (1 + k)
    acc, t = 0.0, 1
    while True:
        w = 1 - (t - 1 + s) / n
        if w <= 0:
            break
        acc += w * x ** (t - 1)
        t += 1
    return (k - g) / (1 + k) * acc


def fade_years(fade: float, k: float, g: float) -> float:
    """Срок n_W, которому отвечает множитель книги: fade(n_W, k, g, 0) = fade (бисекция по n > 0 до неподвижной точки;
    fade(n) не убывает по n). fade ≥ 1 — ∞ (избыток навсегда)."""
    if fade >= 1.0:
        return float("inf")
    lo, hi = 0.0, 1.0
    while fade_of(hi, k, g) < fade:
        lo, hi = hi, hi * 2
    for _ in range(FADE_ITER):
        mid = (lo + hi) / 2
        if mid in (lo, hi):
            break
        if fade_of(mid, k, g) < fade:
            lo = mid
        else:
            hi = mid
    return hi


def fade_at(fade: float, k: float, g: float, s: float) -> float:
    """Множитель угасания по календарю (К-Т2в, М§7): срок суждения n_W переводится из множителя книги при k_T, g_T
    мира (`fade_years`), а сход начинается s лет назад — φ_W = fade(n_W, k, g, s). s = 0 или fade ≥ 1 — множитель
    книги как есть."""
    if not s or fade >= 1.0:
        return fade
    return fade_of(fade_years(fade, k, g), k, g, s)


def fade_symmetric(book) -> bool:
    """Угасание терминала при любом знаке ROE_T − k_T — ключ книги `valuation.terminal.fade_mode: symmetric`;
    нет ключа или `one_sided` — одностороннее: угасает только положительный избыток (М§7)."""
    mode = book.opt(FADE_MODE, ONE_SIDED)
    if mode not in (ONE_SIDED, SYMMETRIC):
        raise BookError(f"{FADE_MODE} = {mode!r}: известны {ONE_SIDED}, {SYMMETRIC}")
    return mode == SYMMETRIC


@dataclass(frozen=True)
class Terminal:
    x_t: float                 # избыток капитала на T (млрд ₽; знак любой)
    bv_star: float             # BV* = BV_Q − X_T
    ni_t1: float               # ЧП акционерам терминального года
    ci_t1: float               # совокупный доход терминального года
    roe_raw: float             # ROE_T = CI_T+1 / BV*
    roe_t: float               # ROE'_T после угасания: одностороннего (fade — только при ROE_T > k_T) или,
    #                            при ключе книги, симметричного (fade — при любом знаке избытка)
    k_t: float
    g_t: float                 # после защиты
    g_capped: bool             # сработала защита g_T = k_T − 0,0001
    tv_ri: float
    tv_ddm: float
    y_x: float = 0.0           # доход на избыток, вычтенный из терминального года (млрд ₽)
    fixed: Mapping[str, Any] | None = None   # блок постоянных в рублях частей (М§7): входы и итоги; без ключа — None
    fade_cal: Mapping[str, Any] | None = None   # угасание по календарю (К-Т2в): {s, n, phi}; только при s > 0


def fixed_terms(book) -> tuple[float | None, tuple[str, ...] | None]:
    """Ключи блока постоянных частей терминала (М§7): λ_F и части. Нет ключа `fixed_growth_share` — (None, None):
    прежний терминал; части без ключа — все четыре."""
    lam = book.opt(FIXED_SHARE)
    if lam is None:
        return None, None
    parts = book.opt(FIXED_PARTS_KEY)
    return float(lam), tuple(FIXED_PARTS if parts is None else (str(x) for x in parts))


@dataclass(frozen=True)
class FixedInputs:
    """Входы блока постоянных частей терминала из прохода клетки (М§7), млрд ₽ (κ — доли RWA)."""
    f_a: float                 # F_A — постоянные прочие активы (OA_fixed)
    r_f: float                 # R_F — их RWA на конце сетки
    kappa20: float             # κ_20 — капитал Н20.0 на рубль RWA: req20 − (gap20 − ded_pp20) + Ded20_0 / RWA_0
    kappa11: float             # κ_11 — то же по Н20.1
    at1: float                 # AT1 — бессрочные инструменты (в K20, деньги — своей строкой пассивов)
    t2: float                  # T2_Q — субординированный капитал Н20.0 на конце сетки (деньги — внутри опта)
    nci: float                 # неконтролирующие доли якоря (постоянные)
    dp_fix: float              # постоянное обязательство дивидендов якоря
    misc_l: float              # «прочее» года L (реальные рубли × индекс цен мира)
    nc_l: float                # непрофильный результат года L


def fixed_block(*, x_t: float, bv_star: float, bv_q: float, g: float, k_t: float, ci_t1: float, y_x: float,
                ni_t1: float, capped: bool, n20: float, req20: float, n11_star: float, req11: float,
                y_balancing: float, c_wholesale: float, wholesale_extra: float, tau_eff: float, nci_share: float,
                coupon_annual: float, tau_stat: float, lt_inflation: float, fade: float, symmetric: bool,
                fixed: FixedInputs, lam_f: float, parts: Sequence[str], year_factor: float = 1.0,
                funding: str = FUNDING_BINARY, headroom: float = 0.0, min_share: float = 0.0,
                nci_l: float = 0.0) -> Terminal:
    """Терминал с блоком постоянных в рублях частей (М§7, ключ `valuation.terminal.fixed_growth_share`): номинальные
    постоянные части (прочие активы, инструменты капитала, постоянные пассивы) — доля w = 1 − λ_F их запаса стоит
    вне бизнеса: не растёт, капитала под рост не удерживает, не угасает; строки ОПУ в реальных рублях остаются в
    избытке бизнеса, растут с инфляцией мира и угасают вместе с ним. X_T, BV*, Y_X, CI_T+1, k_T, g_T — прежние.
    TV_DDM − TV_RI = BV_Q при любых λ_F и частях.

    `year_factor` — ψ (К-Т2а): годовая стоимость фондирования стоящей доли — за средний год. `funding` = balancing
    (К-Т2б, §4.10): связанность минимума ликвидности — после выплаты избытка: WT* = WT_Q + max(0, X_T − H*) при X_T > 0,
    max(0, WT_Q + X_T) при X_T ≤ 0 (H* = `headroom` / (1 − m), m — `min_share`; добавленный капитал гасит добор опта);
    при связанном минимуме (WT* > 0) — ставка опта и стоимость минимума на постоянных активах M_F = (c_wh − y_bal) m /
    (1 − m) F_A: постоянный актив поднимает минимум на m F_A / (1 − m), этот рубль берётся оптом и лежит в ликвидности.
    I_F = −ψ [y_m D_F + M_F] (1 − τ)(1 − nci) − CPN (1 − τ_stat); в CI_B — то же с (1 + g).

    `nci_l` — НДУ года L в рублях (`pnl.nci_real`, Р11-3; доля НДУ тогда 0): строка в реальных рублях после налога —
    в части real_rubles m_L = (misc_L + nc_L)(1 − τ) − NCI_L (w-доля идёт потоком с инфляцией мира, не с g)."""
    on = set(parts)
    k = k_t
    w = 1 - lam_f
    j20 = (n20 - req20) <= (n11_star - req11)            # связывающий норматив (при равенстве — Н20.0)
    kappa = fixed.kappa20 if j20 else fixed.kappa11
    assets = "other_assets_fixed" in on
    inst = "capital_instruments" in on
    f_a = fixed.f_a if assets else 0.0
    r_f = fixed.r_f if assets else 0.0
    chi = 1.0 if (inst and j20) else 0.0                 # инструменты капитала — только в K20 (Н20.0)
    m_at1 = fixed.at1 if inst else 0.0                   # деньги AT1 — своей строкой пассивов
    own = fixed.nci + fixed.dp_fix if "other_fixed_liabilities" in on else 0.0
    f_k = kappa * r_f - chi * (fixed.at1 + fixed.t2)     # капитал, который держат постоянные части (знак любой)
    d_f = f_a - f_k - m_at1 - own                        # их фондирование балансирующими статьями (знак любой)
    balancing = funding == FUNDING_BALANCING
    if balancing:                                        # К-Т2б: связанность минимума после выплаты избытка
        if x_t > 0:
            wt_after = wholesale_extra + max(0.0, x_t - headroom / (1 - min_share))
        else:
            wt_after = max(0.0, wholesale_extra + x_t)
        bound = wt_after > 0
        y_m = c_wholesale if bound else y_balancing
        m_f = (c_wholesale - y_balancing) * min_share / (1 - min_share) * f_a if bound else 0.0
    else:
        y_m = c_wholesale if wholesale_extra > 0 else y_balancing
    tax = (1 - tau_eff) * (1 - nci_share)
    cpn = coupon_annual * (1 - tau_stat) if inst else 0.0
    if balancing:                                        # К-Т2б (и К-Т2а): [y_m D_F + M_F] — за средний год
        drag = (y_m * d_f + m_f) * year_factor
        i_f = -drag * tax - cpn
    elif year_factor != 1.0:                             # К-Т2а: стоимость фондирования y_m D_F — за средний год
        drag = y_m * d_f * year_factor
        i_f = -drag * tax - cpn
    else:
        i_f = -y_m * d_f * tax - cpn                     # годовой доход стоящей доли, постоянный
    m_l = (fixed.misc_l + fixed.nc_l) * tax if "real_rubles" in on else 0.0
    if nci_l and "real_rubles" in on:        # Р11-3: НДУ в рублях — строка в реальных рублях после налога
        m_l -= nci_l
    pi_t = min(lt_inflation, k - G_BELOW_K)
    b = bv_star - w * f_k                                # капитал бизнеса
    if not b > 0:
        raise BookError(f"терминал: капитал бизнеса за концом сетки B = BV* − (1 − λ_F) F_K = {b:.6g} млрд ₽ — "
                        "не больше нуля (М§7)")
    # доход стоящей доли в PBT_L вырос на g — убирается с множителем 1 + g; купон в CI_T+1 стоит плоско; w-доля
    # строк в реальных рублях уходит из растущей части и возвращается потоком с инфляцией мира
    if balancing or year_factor != 1.0:
        ci_b = ci_t1 + w * (1 + g) * drag * tax + w * cpn - w * (1 + g) * m_l
    else:
        ci_b = ci_t1 + w * (1 + g) * y_m * d_f * tax + w * cpn - w * (1 + g) * m_l
    x_b = (ci_b - k * b) / (k - g) + w * m_l * (1 + pi_t) / (k - pi_t)
    phi = fade if (symmetric or x_b > 0) else 1.0
    tv_ri = phi * x_b + w * (i_f - k * f_k) / k          # блок постоянных частей — мимо угасания
    tv_ddm = bv_q + tv_ri
    roe_raw = (ci_b + w * m_l * (1 + pi_t)) / b          # ROE бизнеса года T + 1
    roe_t = k + phi * x_b * (k - g) / b                  # равносильная постоянная ROE′ бизнеса
    block = {"lam_f": lam_f, "parts": list(parts), "f_a": f_a, "r_f": r_f, "kappa": kappa,
             "binding": "n20" if j20 else "n11", "f_k": f_k, "d_f": d_f, "y_m": y_m, "i_f": i_f, "m_l": m_l,
             "business_capital": b, "x_b": x_b, "phi": phi}
    if balancing:
        block.update(bound_after_payout=bound, wt_after=wt_after, min_liquidity=m_f)
    return Terminal(x_t=x_t, bv_star=bv_star, ni_t1=ni_t1, ci_t1=ci_t1, roe_raw=roe_raw, roe_t=roe_t, k_t=k_t,
                    g_t=g, g_capped=capped, tv_ri=tv_ri, tv_ddm=tv_ddm, y_x=y_x, fixed=block)


def excess_income(x_t: float, y_balancing: float, c_wholesale: float, headroom: float,
                  min_share: float = 0.0, wholesale_extra: float = 0.0) -> float:
    """Y_X — доход на избыток капитала по маржинальной ставке балансирующих статей (М§7).

    Избыток (X_T > 0): пока минимум ликвидности не связывает — смесь бумаг и ликвидности, дальше — ставка
    опта. Порог — H* = HLA / (1 − m), а не сам запас HLA: изъятый капитал уменьшает и LA, и активы, от которых
    считается минимум (`min_share` — m). Недостаток (X_T ≤ 0) — зеркально: добавленный капитал сначала гасит
    добор опта WT (`wholesale_extra`, если минимум связывает), остальное ложится в балансирующие активы по смеси."""
    if x_t > 0:
        limit = headroom / (1 - min_share)
        within = min(x_t, limit)
        return y_balancing * within + c_wholesale * (x_t - within)
    repaid = min(-x_t, wholesale_extra)
    return -(c_wholesale * repaid + y_balancing * (-x_t - repaid))


def terminal(*, n20: float, req20: float, n11_star: float, req11: float, rwa: float, bv_q: float,
             pbt_last_year: float, y_balancing: float, c_wholesale: float, headroom: float,
             tau_eff: float, nci_share: float,
             coupon_annual: float, tau_stat: float, lt_inflation: float, real_growth: float,
             fade: float, multiple: float, k_t: float, min_share: float = 0.0,
             wholesale_extra: float = 0.0, symmetric: bool = False, fixed: FixedInputs | None = None,
             lam_f: float | None = None, parts: Sequence[str] | None = None, year_factor: float = 1.0,
             fade_s: int = 0, funding: str = FUNDING_BINARY, nci_l: float = 0.0) -> Terminal:
    """Терминал М§7: капиталонейтральная выплата, избыток капитала 1:1, одностороннее угасание через ROE_T.

    `y_balancing` — смесь доходностей бумаг и ликвидности на конце Q в их долях в LA, `c_wholesale` —
    ставка опта, `headroom` — запас HLA_Q балансирующих активов над минимумом ликвидности, `min_share` —
    доля минимума m (порог связывания — HLA / (1 − m)), `wholesale_extra` — добор опта WT_Q на конце Q.
    Угасание действует только на положительный избыток ROE_T − k_T: сходимость снизу не предполагается.
    `symmetric` (ключ книги `valuation.terminal.fade_mode: symmetric`) — угасание при любом знаке избытка:
    ROE'_T = k_T + fade × (ROE_T − k_T). `lam_f`, `parts`, `fixed` — блок постоянных в рублях частей (М§7, ключ
    `valuation.terminal.fixed_growth_share`; `fixed_block`); нет ключа или λ_F = 1 — прежние строки. `year_factor` — ψ =
    365,2425 / 365 при годе терминала по средней длине года (К-Т2а): годовые ставки за T (Y_X, фондирование блока) —
    за средний год; без ключа — 1 (прежние строки). `fade_s` — s = Y(L) − Y_a лет явного участка после года-якоря
    угасания (К-Т2в): при s > 0 и fade < 1 множитель угасания — φ_W = fade(n_W, k_T, g_T, s) (`fade_at`) и у одностороннего,
    и у симметричного угасания, и у блока К-Т; s = 0 — множитель книги как есть. `funding` — ставка фондирования
    блока К-Т (К-Т2б, `fixed_block`); читается только при блоке. `nci_l` — НДУ года L в рублях номинала мира
    (`pnl.nci_real`, Р11-3; `nci_share` тогда 0): NI_T+1 = (PBT_L (1 + g) − Y_X)(1 − τ) − NCI_L (1 + g) — в растущем бизнесе
    с g; блок К-Т (часть real_rubles) выносит w-долю потоком с инфляцией мира. Без ключа 0 — прежние строки."""
    x_t = multiple * min((n20 - req20) * rwa, (n11_star - req11) * rwa)
    bv_star = bv_q - x_t
    g = (1 + lt_inflation) * (1 + real_growth) - 1
    capped = g > k_t - G_BELOW_K
    if capped:
        g = k_t - G_BELOW_K
    if fade_s > 0:                          # К-Т2в: угасание по календарю — срок суждения после года-якоря
        return _calendar_fade(fade_s, fade, k_t, g, dict(
            n20=n20, req20=req20, n11_star=n11_star, req11=req11, rwa=rwa, bv_q=bv_q, pbt_last_year=pbt_last_year,
            y_balancing=y_balancing, c_wholesale=c_wholesale, headroom=headroom, tau_eff=tau_eff,
            nci_share=nci_share, coupon_annual=coupon_annual, tau_stat=tau_stat, lt_inflation=lt_inflation,
            real_growth=real_growth, multiple=multiple, k_t=k_t, min_share=min_share,
            wholesale_extra=wholesale_extra, symmetric=symmetric, fixed=fixed, lam_f=lam_f, parts=parts,
            year_factor=year_factor, funding=funding, nci_l=nci_l))
    y_x = excess_income(x_t, y_balancing, c_wholesale, headroom, min_share, wholesale_extra)
    if year_factor != 1.0:                  # К-Т2а: доход на избыток за средний год
        y_x *= year_factor
    ni_t1 = (pbt_last_year * (1 + g) - y_x) * (1 - tau_eff) * (1 - nci_share)
    if nci_l:                               # Р11-3: НДУ года L в рублях растёт в бизнесе с g (блок К-Т вынимает свою долю)
        ni_t1 -= nci_l * (1 + g)
    ci_t1 = ni_t1 - coupon_annual * (1 - tau_stat)
    if lam_f is not None and lam_f != 1.0:
        if fixed is None:
            raise BookError("терминал: λ_F задан, а входов блока постоянных частей у прохода нет (М§7)")
        return fixed_block(x_t=x_t, bv_star=bv_star, bv_q=bv_q, g=g, k_t=k_t, ci_t1=ci_t1, y_x=y_x, ni_t1=ni_t1,
                           capped=capped, n20=n20, req20=req20, n11_star=n11_star, req11=req11,
                           y_balancing=y_balancing, c_wholesale=c_wholesale, wholesale_extra=wholesale_extra,
                           tau_eff=tau_eff, nci_share=nci_share, coupon_annual=coupon_annual, tau_stat=tau_stat,
                           lt_inflation=lt_inflation, fade=fade, symmetric=symmetric, fixed=fixed, lam_f=lam_f,
                           parts=FIXED_PARTS if parts is None else parts, year_factor=year_factor, nci_l=nci_l,
                           **({} if funding == FUNDING_BINARY else {"funding": funding, "headroom": headroom,
                                                           "min_share": min_share}))
    roe_raw = ci_t1 / bv_star
    excess = roe_raw - k_t
    if symmetric:
        roe_t = k_t + fade * excess
    else:
        roe_t = k_t + fade * max(excess, 0.0) + min(excess, 0.0)
    tv_ri = (roe_t - k_t) * bv_star / (k_t - g)
    tv_ddm = x_t + (roe_t - g) * bv_star / (k_t - g)
    return Terminal(x_t=x_t, bv_star=bv_star, ni_t1=ni_t1, ci_t1=ci_t1, roe_raw=roe_raw, roe_t=roe_t,
                    k_t=k_t, g_t=g, g_capped=capped, tv_ri=tv_ri, tv_ddm=tv_ddm, y_x=y_x)


def _calendar_fade(s: int, fade: float, k_t: float, g: float, kw: dict[str, Any]) -> Terminal:
    """Терминал при угасании по календарю (К-Т2в, М§7): срок n_W — из множителя книги при k_T и g_T клетки (после
    защиты роста), множитель φ_W = fade(n_W, k_T, g_T, s) — вместо множителя книги; узел {s, n, phi} — в терминале.
    fade ≥ 1 — избыток навсегда: множитель как есть, срока нет."""
    n_w = fade_years(fade, k_t, g)
    phi = fade_at(fade, k_t, g, s)
    term = terminal(**kw, fade=phi)
    return dataclasses.replace(term, fade_cal={"s": s, "n": None if n_w == float("inf") else n_w, "phi": phi})


@dataclass(frozen=True)
class CellValue:
    bv_v: float
    v_ri: float
    v_ddm: float
    pv_ri_explicit: float      # Σ RI_q DF_v(τ_q)
    pv_terminal: float         # DF_v(τ_Q) TV_RI
    pv_div_explicit: float     # Σ Div_q DF_v(τ_q)
    terminal_share: float      # DF_v(τ_Q) TV_DDM / V_DDM
    ri: tuple[float, ...]      # RI_q, q = 0…Q (до q0 — 0)
    # выкуп по цене мира (М§5.6); без выкупа — нули и None (оценка в цене — V_RI)
    pv_buyback: float = 0.0    # Σ B_q DF_v(τ_q)
    s_price: float | None = None   # S_c — стоимость на оставшуюся акцию, ₽
    v_price: float | None = None   # V̂_c = S_c × N_out / 1000 — оценка в цене, млрд ₽


def value_cell(*, q0: int, elapsed: float, disc: Discount, bv: Sequence[float], ci: Sequence[float],
               div: Sequence[float], term: Terminal, bb: Sequence[float] | None = None,
               d_ext: Sequence[float] | None = None, n_t: float | None = None,
               n_out: float | None = None) -> CellValue:
    """RI и DDM по рядам клетки (индекс q = 0…Q; bv — на конец квартала после дивиденда и выкупа).

    Выкуп по цене мира (М§5.6; `bb` — B_q, `d_ext` — дивиденд на внешнюю акцию клетки d_q, `n_t` — акции клетки на
    конце сетки, `n_out` — акции в обращении якоря): V_DDM = Σ (Div + B) DF + DF_Q TV_DDM (= V_RI);
    S_c = Σ DF d_q + DF_Q × 1000 TV_DDM / N_T — стоимость на оставшуюся акцию; V̂_c = S_c N_out / 1000."""
    Q = len(bv) - 1
    e = elapsed
    bv_v = bv[q0 - 1] + e * ci[q0]
    dfq = disc.dfq
    ri = [0.0] * (Q + 1)
    k0 = 1 / dfq[q0] - 1
    ri[q0] = (1 - e) * ci[q0] - k0 * bv_v
    for q in range(q0 + 1, Q + 1):
        ri[q] = ci[q] - disc.k[q] * bv[q - 1]
    pv_ri = sum(ri[q] * dfq[q] for q in range(q0, Q + 1))
    pv_div = sum(div[q] * dfq[q] for q in range(q0, Q + 1))
    pv_term = dfq[Q] * term.tv_ri
    v_ri = bv_v + pv_ri + pv_term
    if bb is not None:
        return _with_buyback(q0=q0, dfq=dfq, bv_v=bv_v, v_ri=v_ri, pv_ri=pv_ri, pv_term=pv_term, pv_div=pv_div, ri=ri,
                             tv_ddm=term.tv_ddm, bb=bb, d_ext=d_ext, n_t=n_t, n_out=n_out)
    v_ddm = pv_div + dfq[Q] * term.tv_ddm
    share = dfq[Q] * term.tv_ddm / v_ddm if v_ddm else float("nan")
    return CellValue(bv_v=bv_v, v_ri=v_ri, v_ddm=v_ddm, pv_ri_explicit=pv_ri, pv_terminal=pv_term,
                     pv_div_explicit=pv_div, terminal_share=share, ri=tuple(ri))


def _with_buyback(*, q0: int, dfq: Sequence[float], bv_v: float, v_ri: float, pv_ri: float, pv_term: float,
                  pv_div: float, ri: Sequence[float], tv_ddm: float, bb: Sequence[float], d_ext: Sequence[float],
                  n_t: float, n_out: float) -> CellValue:
    """Оценка клетки с выкупом по цене мира (М§5.6): выкуп — распределение в DDM; стоимость на оставшуюся акцию —
    дивиденды на внешнюю акцию клетки и терминал на акции клетки на конце сетки (за T выкупа нет)."""
    Q = len(dfq) - 1
    pv_bb = sum(bb[q] * dfq[q] for q in range(q0, Q + 1))
    v_ddm = pv_div + pv_bb + dfq[Q] * tv_ddm
    s = sum(d_ext[q] * dfq[q] for q in range(q0, Q + 1)) + dfq[Q] * 1000 * tv_ddm / n_t
    share = dfq[Q] * tv_ddm / v_ddm if v_ddm else float("nan")
    return CellValue(bv_v=bv_v, v_ri=v_ri, v_ddm=v_ddm, pv_ri_explicit=pv_ri, pv_terminal=pv_term,
                     pv_div_explicit=pv_div, terminal_share=share, ri=tuple(ri), pv_buyback=pv_bb, s_price=s,
                     v_price=s * n_out / 1000)
