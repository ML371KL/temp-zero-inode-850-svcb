"""RWA, нормативы из BV с аддитивными вычетами, требования и полы (М§3.3, §4.11–§4.12).

K20 = BV + DPreg − (1 − f)·R − Ded20 + AT1 + T2;  K11 = BV + DPreg − (1 − f)·R − max(E, 0) − Ded11;
Ded_q = Ded_0 × RWA_q / RWA_0 (вычеты растут с бизнесом; дивиденд и прибыль входят
один к одному). Из базового капитала исключается только неаудированная ПРИБЫЛЬ: убыток
неаудированного периода уменьшает его сразу, вместе с BV. Н20.1 группы — через прокси
Н1.1 банка. Пол = минимум + надбавки сценария года; требование Н20.0 = max(порог
политики; пол + буфер). Постоянные прочие активы (`volumes.other_assets_fixed`) входят в RWA со своей
плотностью `capital.rwa.density.other_assets_fixed`; множитель RWA режима
(`regimes.<r>.rwa_density_mult`, роспуск макронадбавок) стоит на всех RWA клетки (М§4.11).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, NamedTuple, Sequence

from model.book import SECURITIES, LIQUIDITY, AnchorFacts, BookRoles
from model.book_schema import BookError
from model.paths import Trajectory
from model.timeline import QUARTER_YEARS, Timeline, parse_period

if TYPE_CHECKING:
    from model.book import Book

OTHER_ASSETS = "other_assets"
OTHER_ASSETS_FIXED = "other_assets_fixed"


@dataclass(frozen=True)
class ScenarioPath:
    """Полы, требования и вычеты сценария s по кварталам q = 0…Q."""
    scenario: str
    floor20: tuple[float, ...]
    floor11: tuple[float, ...]
    req20: tuple[float, ...]
    req11: tuple[float, ...]
    ded_pp20: tuple[float, ...]
    ded_pp11: tuple[float, ...]
    conservation: tuple[float, ...]
    sifi: tuple[float, ...]
    ccyb: tuple[float, ...]

    def req20_at(self, q: int, threshold: float, buffer20: float) -> float:
        """Требование Н20.0 при пороге ступени политики (М§5.3 п. 2)."""
        return max(threshold, self.floor20[q] + buffer20)


def _series(traj, timeline: Timeline) -> tuple[float, ...]:
    t = Trajectory(traj)
    return tuple(t.value(*parse_period(timeline.period(q))) for q in range(timeline.Q + 1))


def scenario_path(book: "Book", scenario: str, timeline: Timeline) -> ScenarioPath:
    base = f"capital.reg_scenarios.{scenario}"
    cons = _series(book.get(f"{base}.conservation"), timeline)
    sifi = _series(book.get(f"{base}.sifi"), timeline)
    ccyb = _series(book.get(f"{base}.ccyb"), timeline)
    d20 = _series(book.get(f"{base}.deduction_pp.n20_0"), timeline)
    d11 = _series(book.get(f"{base}.deduction_pp.n1_1"), timeline)
    m20 = float(book.get("capital.minimum.n20_0"))
    m11 = float(book.get("capital.minimum.n1_1"))
    b20 = float(book.get("capital.mgmt_buffer.n20_0"))
    b11 = float(book.get("capital.mgmt_buffer.n1_1"))
    thr = float(book.get("dividends.policy.threshold"))
    add = [cons[q] + sifi[q] + ccyb[q] for q in range(timeline.Q + 1)]
    floor20 = tuple(m20 + a for a in add)
    floor11 = tuple(m11 + a for a in add)
    return ScenarioPath(scenario=scenario, floor20=floor20, floor11=floor11,
                        req20=tuple(max(thr, f + b20) for f in floor20),
                        req11=tuple(f + b11 for f in floor11),
                        ded_pp20=d20, ded_pp11=d11, conservation=cons, sifi=sifi, ccyb=ccyb)


def density_index(book: "Book", timeline: Timeline) -> tuple[float, ...]:
    """Dn_q: рост плотности RWA до `density_drift_until` включительно (М§4.11)."""
    rate = float(book.get("capital.rwa.density_drift_rate"))
    until = int(book.get("capital.rwa.density_drift_until"))
    out = [1.0]
    for q in range(1, timeline.Q + 1):
        out.append(out[-1] * ((1 + rate) ** QUARTER_YEARS if timeline.year(q) <= until else 1.0))
    return tuple(out)


def fx_index(book: "Book", cpi: Sequence[float], Q: int) -> tuple[float, ...]:
    """X_q валютной части RWA по относительному ППС; выключено — X ≡ 1."""
    if not book.get("capital.rwa.fx.enabled"):
        return tuple([1.0] * (Q + 1))
    share = float(book.get("capital.rwa.fx.share"))
    pi = float(book.get("capital.rwa.fx.foreign_inflation"))
    out, cum = [1.0], 1.0
    for q in range(1, Q + 1):
        cum *= ((1 + cpi[q]) / (1 + pi)) ** QUARTER_YEARS
        out.append(1 - share + share * cum)
    return tuple(out)


@dataclass(frozen=True)
class RwaWeights:
    loans: Mapping[str, float]             # кредитная книга → плотность
    securities: float
    liquidity: float
    other_assets: float
    oa_fixed: float = 0.0                  # OA_fixed — постоянная часть прочих активов, млрд ₽ (М§4.3)
    other_assets_fixed: float = 0.0        # её плотность ω_oaf; читается только при OA_fixed ≠ 0
    guar_g0: float | None = None           # G_0 — RWA гарантий якоря (К5, М§4.11); плотность книги выреза уже без них
    guar_carve: str | None = None          # книга выреза; None — составляющей гарантий нет
    cash: float | None = None              # ω_c — плотность неработающих денег (К8, М§4.11); None — денег отдельно нет
    other_assets_cash: float = 0.0         # ω′_oa — плотность растущих прочих активов без денег (вырез К8)

    def rwa(self, loans: Mapping[str, float], securities: float, liquidity: float,
            other_assets: float, dn: float, x: float, guar: float | None = None, cash: float | None = None,
            cash_shift: float | None = None) -> float:
        """База RWA × дрейф плотности × валютный индекс; `other_assets` — прочие активы целиком. `loans` —
        остатки по книгам: читаются только кредитные (прочие ключи словаря не мешают). `guar` — составляющая
        гарантий квартала G_q (К5): входит в базу — дрейф плотности и валютный индекс стоят и на ней. `cash` —
        неработающие деньги квартала C_q (К8): ω′_oa (OA − F_A − C) + ω_c C + ω_oaf F_A; без них — прежние строки.
        `cash_shift` — слагаемое вытесненной части прочих активов (1 − θ)(ω′_oa − ω_c) δ_q L_q (Р6-1): в базе, под
        дрейфом плотности и валютным индексом (множитель режима — снаружи, как у всех RWA); без него — прежняя строка."""
        base = sum([self.loans[b] * loans[b] for b in self.loans])
        base += self.securities * securities + self.liquidity * liquidity
        if cash is not None:                # К8: деньги со своей плотностью, вырезанной из растущей части
            base += (self.other_assets_cash * (other_assets - self.oa_fixed - cash) + self.cash * cash
                     + self.other_assets_fixed * self.oa_fixed)
        elif self.oa_fixed:
            base += self.other_assets * (other_assets - self.oa_fixed) + self.other_assets_fixed * self.oa_fixed
        else:
            base += self.other_assets * other_assets
        if cash_shift is not None:          # Р6-1: вытесненная часть прочих активов — своей плотностью
            base += cash_shift
        if guar is not None:
            base += guar
        return base * dn * x


def rwa_weights(book: "Book", roles: BookRoles) -> RwaWeights:
    dens = book.get("capital.rwa.density")
    oa_fixed = float(book.opt("volumes.other_assets_fixed", 0.0))
    if oa_fixed and OTHER_ASSETS_FIXED not in dens:
        raise BookError("capital.rwa.density.other_assets_fixed: нет плотности постоянных прочих активов (М§4.11)")
    return RwaWeights(loans={b: float(dens[b]) for b in roles.loans},
                      securities=float(dens[SECURITIES]), liquidity=float(dens[LIQUIDITY]),
                      other_assets=float(dens[OTHER_ASSETS]), oa_fixed=oa_fixed,
                      other_assets_fixed=float(dens[OTHER_ASSETS_FIXED]) if oa_fixed else 0.0)


def regime_rwa_mult(book: "Book", regime: str, timeline: Timeline) -> tuple[float, ...] | None:
    """M_r,q — множитель RWA клеток режима по кварталам q = 0…Q (М§4.11); ключа у режима нет — None
    (множителя нет). В квартале якоря множитель не применяется: RWA_0 — факт."""
    traj = book.get(f"regimes.{regime}").get("rwa_density_mult")
    if traj is None:
        return None
    series = _series(traj, timeline)
    if min(series) <= 0:
        raise BookError(f"regimes.{regime}.rwa_density_mult: множитель RWA — больше нуля (М§4.11)")
    return series


def rwa_anchor(weights: RwaWeights, af: AnchorFacts) -> float:
    """RWA_0 модели: плотности × книги якоря (калиброваны к RWA по Базелю); при составляющей гарантий — с G_0 (вырез
    плотности книги её не меняет)."""
    return weights.rwa({b: af.balances[b] for b in weights.loans}, af.balances[SECURITIES],
                       af.balances[LIQUIDITY], af.other_assets, 1.0, 1.0, guar=weights.guar_g0)


GUARANTEES = "capital.rwa.guarantees"
CASH_DENSITY = "capital.rwa.density.cash_assets"


def carve_cash(weights: RwaWeights, density: float, c0: float, oa0: float) -> RwaWeights:
    """Вырез неработающих денег из плотности растущих прочих активов (К8, М§4.11): ω′_oa = [ω_oa (OA_0 − F_A) − ω_c C_0] /
    (OA_0 − F_A − C_0) — RWA растущей части якоря не меняется (ω′_oa (OA_0 − F_A − C_0) + ω_c C_0 = ω_oa (OA_0 − F_A)).
    RWA якоря считается прежней строкой (без денег) — бит в бит. ω′_oa < 0 — отказ: плотность денег выше, чем RWA
    растущей части оставляет на прочие активы без денег. Растущая часть без денег нулевая — ω′_oa = ω_oa (множит ноль)."""
    grow = oa0 - weights.oa_fixed
    rest = grow - c0
    carved = (weights.other_assets * grow - density * c0) / rest if rest else weights.other_assets
    if carved < 0:
        raise BookError(f"{CASH_DENSITY} = {density:g}: RWA денег {density * c0:g} больше RWA растущих прочих активов "
                        f"якоря {weights.other_assets * grow:g} — плотность прочих активов без денег меньше нуля "
                        "(К8, М§4.11)")
    return dataclasses.replace(weights, cash=density, other_assets_cash=carved)


def guarantees_g0(spec: Mapping[str, Any]) -> float:
    """G_0 — RWA гарантий якоря (К5, М§4.11): (N_нф × CCF_нф + N_ф × CCF_ф) × вес (вес риска × масштаб калибровки
    RWA книги)."""
    n, ccf = spec["notional"], spec["ccf"]
    return (float(n["nonfinancial"]) * float(ccf["nonfinancial"])
            + float(n["financial"]) * float(ccf["financial"])) * float(spec["weight"])


def carve_guarantees(weights: RwaWeights, g0: float, carve: str, e_carve0: float) -> RwaWeights:
    """Вырез гарантий из плотности книги (К5, М§4.11): ω′_c = ω_c − G_0 / E_c,0 — RWA якоря не меняется
    (ω′_c E_c,0 + G_0 = ω_c E_c,0). Книга выреза — кредитная; ω′_c < 0 — отказ: гарантий больше, чем RWA книги
    выреза."""
    if carve not in weights.loans:
        raise BookError(f"{GUARANTEES}.carve_from = {carve!r}: не кредитная книга ({', '.join(weights.loans)}; М§4.11)")
    carved = weights.loans[carve] - g0 / e_carve0
    if carved < 0:
        raise BookError(f"{GUARANTEES}: RWA гарантий якоря {g0:g} больше RWA книги выреза {carve} "
                        f"{weights.loans[carve] * e_carve0:g} — плотность после выреза меньше нуля (М§4.11)")
    return dataclasses.replace(weights, loans={**weights.loans, carve: carved}, guar_g0=g0, guar_carve=carve)


@dataclass(frozen=True)
class CapitalConst:
    """Постоянные книги для нормативов (М§4.11)."""
    ded20_0: float
    ded11_0: float
    rwa0: float
    fvoci_recognition: float
    gap20: float
    gap11: float
    at1: float
    audit_cutoffs: tuple[int, ...]
    buffer20: float
    buffer11: float


def capital_const(book: "Book", af: AnchorFacts, rwa0: float) -> CapitalConst:
    return CapitalConst(
        ded20_0=float(book.get("capital.n20.deductions_anchor")),
        ded11_0=float(book.get("capital.n11.deductions_anchor")),
        rwa0=rwa0,
        fvoci_recognition=float(book.get("capital.n20.fvoci_recognition")),
        gap20=float(book.get("capital.n20.gap_pp")),
        gap11=float(book.get("capital.n11.gap_pp")),
        at1=af.at1,
        audit_cutoffs=tuple(int(x) for x in book.get("capital.n11.audit_cutoffs")),
        buffer20=float(book.get("capital.mgmt_buffer.n20_0")),
        buffer11=float(book.get("capital.mgmt_buffer.n1_1")),
    )


class Ratios(NamedTuple):                  # кортеж, а не класс данных: создаётся на каждой оценке шага
    rwa: float
    k20: float
    k11: float
    n20: float
    n11: float
    ded20: float
    ded11: float
    n11_star: float = 0.0                  # Н20.1 с прибылью периода (N11*, М§4.11)


def ratios(c: CapitalConst, *, bv: float, dpreg: float, reserve: float, unaudited: float,
           t2: float, rwa: float, ded_pp20: float, ded_pp11: float) -> Ratios:
    """K20, K11, Н20.0 и Н20.1 (прокси Н1.1) на конец квартала (М§4.11); рядом с отчётным Н20.1 — Н20.1 с
    прибылью периода (N11*): он входит в ограничение роста капиталом (М§4.13).

    `unaudited` — E_q, результат неаудированного периода (знак любой). Из K11 исключается только
    прибыль, max(E_q, 0): убыток уже уменьшил BV и в базовый капитал не возвращается."""
    ded20 = c.ded20_0 * rwa / c.rwa0
    ded11 = c.ded11_0 * rwa / c.rwa0
    bvreg = bv + dpreg - (1 - c.fvoci_recognition) * reserve
    k20 = bvreg - ded20 + c.at1 + t2
    k11 = bvreg - max(unaudited, 0.0) - ded11
    return Ratios(rwa=rwa, k20=k20, k11=k11, n20=k20 / rwa + c.gap20 - ded_pp20,
                  n11=k11 / rwa + c.gap11 - ded_pp11, ded20=ded20, ded11=ded11,
                  n11_star=n11_audited(k11, unaudited, rwa, c.gap11, ded_pp11))


def n11_audited(k11: float, unaudited: float, rwa: float, gap11: float, ded_pp11: float) -> float:
    """N11* — Н20.1 с прибылью периода в базовом капитале (E = 0, как после аудита; М§7): в K11
    возвращается ровно то, что из него исключено, — max(E, 0); убыток в нём уже учтён."""
    return (k11 + max(unaudited, 0.0)) / rwa + gap11 - ded_pp11


# ------------------------------------------------------------------ рост, ограниченный капиталом (М§4.13)

GROWTH = "capital.growth_constraint"
DIVIDEND_FIRST, GROWTH_FIRST = "dividend_first", "growth_first"


@dataclass(frozen=True)
class GrowthRule:
    """Параметры ограничения роста кредитных книг капиталом (`capital.growth_constraint`, М§4.13)."""
    order: str                             # что уступает первым: dividend_first — рост, growth_first — дивиденд
    lam_min: float                         # λ_min — нижняя граница доли потенциального прироста
    lookahead: int                         # H — на сколько кварталов вперёд видны ступени требования
    glide: float                           # δ — сколько требования набирается за квартал перед ступенью
    catch_up: float                        # κ_g — доля разрыва с потенциальным путём, навёрстываемая за год
    tol: float                             # допуск равенства норматива требованию

    @property
    def dividend_first(self) -> bool:
        return self.order == DIVIDEND_FIRST


def growth_rule(book: "Book") -> GrowthRule | None:
    """Правило ограничения роста книги; объекта нет или он выключен — None (рост задан, М§4.3)."""
    spec = book.opt(GROWTH)
    if not spec or spec.get("enabled") is not True:
        return None
    return GrowthRule(order=str(spec["order"]), lam_min=float(spec["min_growth_scale"]),
                      lookahead=int(spec["lookahead_quarters"]), glide=float(spec["glide_pp_per_quarter"]),
                      catch_up=float(spec["catch_up_rate"]), tol=float(spec["tol"]))


def glide_path(req: Sequence[float], lookahead: int, glide: float) -> tuple[float, ...]:
    """Требование с глиссадой (М§4.13.1): req*_q = max по h = 0…H (r_min(q+h, Q) − h × δ) — известная ступень
    требования набирается заранее, по δ за квартал; на конце сетки req* равно требованию."""
    last = len(req) - 1
    return tuple(max(req[min(q + h, last)] - h * glide for h in range(lookahead + 1)) for q in range(last + 1))


def after_audit_start(quarter: int, cutoffs: Sequence[int]) -> int:
    """Номер первого квартала года, прибыль с которого ещё не аудирована на конец `quarter`.

    E_q = Σ NI по кварталам после последнего квартала-отсечки, строго
    предшествующего q, по q включительно; возвращается сдвиг назад (0 — только q).
    """
    back = 0
    h = quarter
    while True:
        h = 4 if h == 1 else h - 1
        if h in cutoffs:
            return back
        back += 1
        if back > 3:
            return back
