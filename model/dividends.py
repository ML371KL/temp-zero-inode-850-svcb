"""Дивидендная политика данными книги (М§5): база, пул, DPS, решение года.

Пул года прибыли Y: p × max(0, ЧП акционерам − купон AT1 × (1 − τ_stat)); DPS =
пул / размещённые акции обеих категорий; BV уменьшается на DPS × акции в обращении
(часть на собственные акции остаётся в группе). Решение — в квартал ГОСА года
Y+1 по пробному проходу без дивиденда: запас капитала H в точках проверки,
ступени политики, остаток сверх требований, догоняющая выплата, доля ε избытка с
линейным вводом за `excess.ramp_years` лет (М§5.3 п. 4), кризисный перенос; объявленный
в реестре DPS — обязательство без проверок. Отмена выплаты в год шока кризиса — флаг
`crisis_skip`, а не `dividend_cut`: капитал выплату не урезал (М§5.3 п. 5).
Тест истории выплат — вида `dividends.policy.history_test` (М§5.2): `exact` (и без ключа) — формула на
фактах в точной десятичной арифметике (ceil_kopeck); `cap` — выплаты каждого завершённого года не выше
потолка `dividends.policy.cap` от отчётной прибыли акционеров (`facts/dividends.json → years`); `none` —
тест выключен книгой.

Квартальный календарь (`dividends.calendar.frequency: quarterly`, М§5.7): решение — за каждый квартал прибыли.
Карта лагов (`LagRule`) задаёт кварталы решения, регуляторного вычета и выплаты от квартала прибыли; закрыт ли
квартал прибыли до якоря, решает факт — строка истории дивидендов с решением не позже даты фактов
(`closed_through`), а не карта. `quarter_calendar` один раз на прогон раскладывает открытые кварталы прибыли по
кварталам клетки (с датами записей реестра) и состояние якоря; `decide_quarter` — решения одного квартала клетки:
записи реестра — обязательство, год шока отменяет решения модели, пул — доля от средней прибыли окна, базовый
дивиденд — в пределах запаса квартала, догоняющая выплата и доля избытка — раз в год, в решении за четвёртый
квартал прибыли. Без ключа календарь годовой — прежние функции без единой правки.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Mapping, NamedTuple, Sequence

from model.book_schema import BookError, FactsError
from model.paths import Trajectory
from model.timeline import to_date

if TYPE_CHECKING:
    from model.book import Book, Facts

KOPECK = Decimal("0.01")
THOUSAND = 1000                              # млрд ₽ × 1000 / млн шт. = ₽ на акцию
HISTORY_EXACT, HISTORY_CAP, HISTORY_NONE = "exact", "cap", "none"
CAP_TOL = 1e-9                               # допуск сравнения с потолком политики, млрд ₽
FREQ_ANNUAL, FREQ_QUARTERLY = "annual", "quarterly"
DECLARED = ("declared", "paid")              # статусы записи реестра, которые несут обязательство
CUT_TOL = 1e-9                               # базовый дивиденд ниже пула политики больше чем на допуск — урезан
LAST_QUARTER = 4                             # решение за этот квартал прибыли несёт догоняющую выплату и избыток


def history_test(book: "Book") -> str:
    """Вид теста истории выплат — ключ `dividends.policy.history_test`; без ключа — `exact` (М§5.2)."""
    return str(book.opt("dividends.policy.history_test", HISTORY_EXACT))


def history_dps(row: Mapping[str, Any]) -> float | None:
    """DPS строки истории дивидендов: узел `dps`, а если его нет — `dps_ordinary` (М прил. B)."""
    node = row.get("dps") if row.get("dps") is not None else row.get("dps_ordinary")
    value = node.get("v") if isinstance(node, Mapping) else node
    return None if value is None else float(value)


def round_dps(value: Decimal, rule: str) -> Decimal:
    if rule == "ceil_kopeck":
        return value.quantize(KOPECK, rounding=ROUND_CEILING)
    if rule == "half_up_kopeck":
        return value.quantize(KOPECK, rounding=ROUND_HALF_UP)
    raise BookError(f"dividends.policy.dps_rounding = {rule!r}: известны ceil_kopeck, half_up_kopeck")


def _dec(x: Any) -> Decimal:
    return Decimal(str(x))


def dps_formula(*, ni_shareholders: Any, at1_coupon: Any, tax_statutory: Any, payout: Any,
                n_issued: Any, deduct_at1_after_tax: bool = True,
                rounding: str = "ceil_kopeck") -> dict[str, Decimal]:
    """Формула М§5.2 в точной десятичной арифметике (тест истории, прил. C)."""
    ni, cpn, tau = _dec(ni_shareholders), _dec(at1_coupon), _dec(tax_statutory)
    base = ni - (cpn * (1 - tau) if deduct_at1_after_tax else Decimal(0))
    pool = _dec(payout) * max(Decimal(0), base)
    exact = pool * THOUSAND / _dec(n_issued)
    return {"base": base, "pool": pool, "dps_exact": exact, "dps_rounded": round_dps(exact, rounding)}


def dps_history(book: "Book", facts: "Facts") -> list[dict[str, Any]]:
    """Строки теста `dps_history`: формула на `facts/dividends.json → history`."""
    rows = facts.file("dividends").get("history")
    if not isinstance(rows, list) or not rows:
        raise FactsError("dividends.history: нет истории выплат")
    n_iss = facts.need("shares", "issued_total")
    payout = Trajectory(book.get("dividends.policy.payout"))
    rule = str(book.get("dividends.policy.dps_rounding"))
    after_tax = bool(book.get("dividends.policy.deduct_at1_after_tax"))
    out = []
    for i, row in enumerate(rows):
        year = int(row["year"])
        get = lambda k: facts.need("dividends", f"history.{i}.{k}")
        r = dps_formula(ni_shareholders=get("ni_shareholders"), at1_coupon=get("at1_coupon"),
                        tax_statutory=get("tax_statutory"), payout=payout.year_value(year),
                        n_issued=n_iss, deduct_at1_after_tax=after_tax, rounding=rule)
        declared = _dec(get("dps_ordinary"))
        out.append({"year": year, "ni_shareholders": get("ni_shareholders"), "at1_coupon": get("at1_coupon"),
                    "tax_statutory": get("tax_statutory"), "base": float(r["base"]), "pool": float(r["pool"]),
                    "dps_exact": float(r["dps_exact"]), "dps_rounded": float(r["dps_rounded"]),
                    "dps_declared": float(declared), "rounding": rule,
                    "ok": r["dps_rounded"] == declared})
    return out


def cap_history(book: "Book", facts: "Facts") -> list[dict[str, Any]]:
    """Строки теста истории вида `cap` (М§5.2): по годам `facts/dividends.json → years` — сумма `pool_declared`
    строк `history` года против потолка политики от отчётной прибыли акционеров. `ok` — у завершённого года;
    у неполного — None (строка диагностики). Записи живого реестра в тест не входят."""
    cap = float(book.get("dividends.policy.cap"))
    file = facts.file("dividends")
    years = file.get("years")
    if not isinstance(years, Mapping) or not years:
        raise FactsError("dividends.years: нет отчётной прибыли акционеров по годам (тест истории выплат, М§5.2)")
    pools: dict[int, float] = {}
    for i, row in enumerate(file.get("history") or []):
        year = int(row["year"])
        pools[year] = pools.get(year, 0.0) + facts.need("dividends", f"history.{i}.pool_declared")
    out = []
    for key in sorted(years, key=int):
        year, complete = int(key), years[key].get("complete") is True
        ni = facts.need("dividends", f"years.{key}.ni_shareholders")
        pool = pools.get(year, 0.0)
        out.append({"year": year, "pool": pool, "ni_shareholders": ni, "share": pool / ni if ni else None,
                    "cap": cap, "complete": complete, "ok": pool <= cap * ni + CAP_TOL if complete else None})
    return out


@dataclass(frozen=True)
class Step:
    payout: Trajectory
    threshold: float


@dataclass(frozen=True)
class Policy:
    """Политика книги, разобранная один раз на прогон."""
    steps: tuple[Step, ...]
    deviation: Trajectory
    deduct_at1_after_tax: bool
    epsilon: float
    excess_from: int
    ramp_years: int
    skip_in_shock: bool
    catch_up: bool
    agm_quarter: int                       # годовой календарь: кварталы года Y + 1 (при квартальном — нули,
    reg_quarter: int                       # ключи неактивного режима не читаются)
    pay_quarter: int
    checkpoints: tuple[int, ...]
    n_iss: float
    n_out: float
    rule: "LagRule | None" = None          # карта лагов квартального календаря; None — календарь годовой
    window: int = 1                        # W — окно базы пула, кварталов (только квартальный календарь)

    def epsilon_at(self, year: int) -> float:
        """ε_Y = ε × min(1, (Y − from + 1) / ramp_years) при Y ≥ from, иначе 0 (М§5.3 п. 4)."""
        if year < self.excess_from:
            return 0.0
        return self.epsilon * min(1.0, (year - self.excess_from + 1) / self.ramp_years)

    def payouts(self, year: int) -> list[float]:
        dev = self.deviation.year_value(year)
        return [min(1.0, max(0.0, s.payout.year_value(year) + dev)) for s in self.steps]


def make_policy(book: "Book", n_iss: float, n_out: float) -> Policy:
    pol = book.get("dividends.policy")
    raw_steps = pol.get("steps") or []
    if raw_steps:
        steps = tuple(Step(Trajectory(s["payout"]), float(s["threshold"])) for s in raw_steps)
    else:
        steps = (Step(Trajectory(pol["payout"]), float(pol["threshold"])),)
    cal = book.get("dividends.calendar")
    rule = lag_rule(book)
    if rule is not None:                    # квартальный календарь: ключи годового режима не читаются (М§5.7.1)
        return Policy(steps=steps, deviation=Trajectory(book.get("dividends.payout_deviation")),
                      deduct_at1_after_tax=bool(pol["deduct_at1_after_tax"]),
                      epsilon=float(book.get("dividends.excess.epsilon")),
                      excess_from=int(book.get("dividends.excess.from_profit_year")),
                      ramp_years=int(book.get("dividends.excess.ramp_years")),
                      skip_in_shock=bool(book.get("dividends.crisis.skip_in_shock_year")),
                      catch_up=bool(book.get("dividends.crisis.catch_up")),
                      agm_quarter=0, reg_quarter=0, pay_quarter=0, checkpoints=(), n_iss=n_iss, n_out=n_out,
                      rule=rule, window=int(pol.get("base_window_quarters") or 1))
    return Policy(steps=steps, deviation=Trajectory(book.get("dividends.payout_deviation")),
                  deduct_at1_after_tax=bool(pol["deduct_at1_after_tax"]),
                  epsilon=float(book.get("dividends.excess.epsilon")),
                  excess_from=int(book.get("dividends.excess.from_profit_year")),
                  ramp_years=int(book.get("dividends.excess.ramp_years")),
                  skip_in_shock=bool(book.get("dividends.crisis.skip_in_shock_year")),
                  catch_up=bool(book.get("dividends.crisis.catch_up")),
                  agm_quarter=int(cal["agm_quarter"]), reg_quarter=int(cal["reg_deduction_quarter"]),
                  pay_quarter=int(cal["payment_quarter"]),
                  checkpoints=tuple(int(x) for x in cal["checkpoints"]),
                  n_iss=n_iss, n_out=n_out)


@dataclass(frozen=True)
class Checkpoint:
    """Норматив пробного прохода (без дивиденда года) в точке проверки."""
    n20: float
    n11: float
    rwa: float
    floor20: float
    req11: float


@dataclass(frozen=True)
class Decision:
    year: int                  # год прибыли
    base: float                # база выплаты (млрд ₽)
    want: tuple[float, ...]    # уменьшение BV по ступеням при полной выплате пула
    headroom: tuple[float, ...]  # H_j (млрд ₽; inf — точек проверки нет)
    step: int                  # индекс выбранной ступени
    base_div: float
    catch: float
    excess: float
    div: float                 # Div_Y: уменьшение BV
    dps: float                 # ₽ на акцию, не округлён
    deferred_before: float
    deferred_after: float
    source: str                # model | register | crisis_skip
    cut: bool                  # капитал урезал выплату: base_div < пула политики (М§5.3 п. 3); отмена кризисом — нет
    flags: tuple[str, ...] = field(default_factory=tuple)
    # квартальный календарь (М§5.7.5); в годовом режиме — None
    period: str | None = None              # квартал прибыли
    q: int | None = None                   # квартал клетки, в котором решение принято
    headroom_final: float | None = None    # запас при итоговых объёмах без решений модели
    # жетон DPS в машине роста (К1, М§4.13.2 п. 2а): сумма жетона у решения-носителя (млрд ₽) и запас над требованием
    # без запаса менеджмента при наименьшей доле прироста, по которому он решён; без ключа — 0 и None
    token: float = 0.0
    headroom_floor: float | None = None


def base_of_year(ni_sh_year: float, coupon_year: float, tau_stat: float, after_tax: bool) -> float:
    """База выплаты: ЧП акционерам − купоны AT1 за вычетом налогового эффекта."""
    return ni_sh_year - (coupon_year * (1 - tau_stat) if after_tax else 0.0)


def headroom(points: Sequence[Checkpoint], threshold: float, buffer20: float) -> float:
    """H_j = min_c min((N20 − req20_j) RWA, (N11 − req11) RWA) — дивиденд снижает K20 и K11 1:1."""
    if not points:
        return float("inf")
    return min(min((p.n20 - max(threshold, p.floor20 + buffer20)) * p.rwa,
                   (p.n11 - p.req11) * p.rwa) for p in points)


def decide(policy: Policy, *, year: int, base: float, points: Sequence[Checkpoint], buffer20: float,
           deferred: float, shock: bool, declared_dps: float | None) -> Decision:
    """Решение о дивиденде за год Y (М§5.3 пп. 2–6)."""
    pays = policy.payouts(year)
    ratio = policy.n_out / policy.n_iss
    want = tuple(p * max(0.0, base) * ratio for p in pays)
    hs = tuple(headroom(points, s.threshold, buffer20) for s in policy.steps)
    if declared_dps is not None:
        div = declared_dps * policy.n_out / THOUSAND
        return Decision(year=year, base=base, want=want, headroom=hs, step=0, base_div=div, catch=0.0,
                        excess=0.0, div=div, dps=declared_dps, deferred_before=deferred,
                        deferred_after=deferred, source="register", cut=False)
    if shock and policy.skip_in_shock:
        return Decision(year=year, base=base, want=want, headroom=hs, step=0, base_div=0.0, catch=0.0,
                        excess=0.0, div=0.0, dps=0.0, deferred_before=deferred,
                        deferred_after=deferred + want[0], source="crisis_skip", cut=False,
                        flags=("crisis_skip",))
    chosen = None
    for j, (w, h) in enumerate(zip(want, hs)):
        if h >= w:
            chosen = j
            break
    if chosen is not None:
        base_div, h_sel = want[chosen], hs[chosen]
    else:
        chosen = len(want) - 1
        h_sel = hs[chosen]
        base_div = max(0.0, min(want[chosen], h_sel))
    catch = min(deferred, max(0.0, h_sel - base_div)) if policy.catch_up else 0.0
    eps = policy.epsilon_at(year)
    exc = eps * max(0.0, h_sel - base_div - catch) if eps else 0.0
    if exc == float("inf") or catch == float("inf"):
        raise BookError("запас капитала бесконечен: нет точек проверки дивиденда в сетке")
    div = base_div + catch + exc
    cut = base_div < want[0] - 1e-9
    return Decision(year=year, base=base, want=want, headroom=hs, step=chosen, base_div=base_div,
                    catch=catch, excess=exc, div=div, dps=div * THOUSAND / policy.n_out,
                    deferred_before=deferred, deferred_after=deferred - catch, source="model", cut=cut,
                    flags=("dividend_cut",) if cut else ())


def pool_policy(policy: Policy, year: int, base: float) -> float:
    """Пул политики первой ступени без капитального ограничения (млрд ₽, на все размещённые)."""
    return policy.payouts(year)[0] * max(0.0, base)


def record_key(rec: Any, quarterly: bool = False) -> Any:
    """Ключ записи реестра: квартал прибыли при квартальном календаре, иначе год прибыли (М§5.7.6)."""
    return str(rec.period) if quarterly else int(rec.year)


def register_dps(register: Sequence[Any], quarterly: bool = False) -> Mapping[Any, float]:
    """Ключ записи (год прибыли; при квартальном календаре — квартал прибыли) → DPS объявленных записей
    реестра (declared | paid)."""
    out = {}
    for rec in register:
        status = getattr(rec, "status", None)
        if status in DECLARED:
            out[record_key(rec, quarterly)] = float(rec.dps)
    return out


# ------------------------------------------------------------------ квартальный календарь (М§5.7)


def frequency(book: "Book") -> str:
    """Режим календаря дивидендов — ключ `dividends.calendar.frequency`; без ключа — годовой (М§5.1)."""
    return str(book.opt("dividends.calendar.frequency", FREQ_ANNUAL))


def is_quarterly(book: "Book") -> bool:
    return frequency(book) == FREQ_QUARTERLY


@dataclass(frozen=True)
class LagRule:
    """Карта лагов (М§5.7.2): кварталы решения, вычета из регуляторного капитала и выплаты — от квартала
    прибыли с номером `idx` на линейке сетки и номером в году `h`."""
    lags: tuple[int, ...]                  # лаг решения по номеру квартала прибыли в году, h = 1…4
    reg_lag: int
    pay_lag: int

    def q_dec(self, idx: int, h: int) -> int:
        return idx + self.lags[h - 1]

    def q_reg(self, idx: int, h: int) -> int:
        return max(self.q_dec(idx, h), idx + self.reg_lag)

    def q_pay(self, idx: int, h: int) -> int:
        return max(self.q_dec(idx, h), idx + self.pay_lag)


def lag_rule(book: "Book") -> LagRule | None:
    """Карта лагов книги; при годовом календаре — None."""
    if not is_quarterly(book):
        return None
    cal = book.get("dividends.calendar")
    raw = cal["decision_lag_quarters"]
    lags = tuple(int(raw[str(h)]) if isinstance(raw, Mapping) else int(raw) for h in (1, 2, 3, 4))
    return LagRule(lags=lags, reg_lag=int(cal["reg_deduction_lag_quarters"]),
                   pay_lag=int(cal["payment_lag_quarters"]))


def _plain(x: Any) -> Any:
    return x.get("v") if isinstance(x, Mapping) else x


def closed_through(facts: "Facts", timeline: Any, facts_date: Any) -> int:
    """Номер p_last на линейке сетки — самый поздний квартал прибыли, у которого в истории дивидендов есть
    строка с решением не позже даты фактов: он и все более ранние закрыты, их дивиденд вычтен из BV якоря
    (М§5.7.2). Закрыт ли квартал, решает факт, а не карта лагов. Нет такой строки — FactsError."""
    facts_date = to_date(facts_date)
    last = None
    for i, row in enumerate(facts.file("dividends").get("history") or []):
        period, decided = _plain(row.get("period")), _plain(row.get("decided_date"))
        if not period or not decided:
            raise FactsError(f"dividends.history.{i}: нет квартала прибыли или даты решения — при квартальном "
                             "календаре дивидендов они обязательны в каждой строке (М§5.7.2)")
        try:
            idx, day = timeline.index(str(period)), to_date(decided)
        except (BookError, ValueError) as exc:
            raise FactsError(f"dividends.history.{i}: {exc}") from None
        if day <= facts_date and (last is None or idx > last):
            last = idx
    if last is None:
        raise FactsError("dividends.history: нет ни одного решения о дивиденде не позже даты фактов — закрытые "
                         "кварталы прибыли не определены (М§5.7.2)")
    return last


@dataclass(frozen=True)
class OpenQuarter:
    """Открытый квартал прибыли в клетке (М§5.7.2): дивиденд за него уменьшает BV в конце квартала `q`."""
    idx: int                               # номер квартала прибыли на линейке сетки (якорь — 0)
    period: str
    year: int
    h: int                                 # номер квартала прибыли в году
    q: int                                 # q_cell: квартал клетки решения
    q_reg: int                             # квартал вычета из регуляторного капитала, не раньше q
    q_pay: int                             # квартал выплаты, не раньше q
    dps: float | None = None               # DPS записи реестра declared | paid; None — решает модель


@dataclass(frozen=True)
class QuarterCalendar:
    """Календарь решений прогона (М§5.7.2, §5.7.4): общий для всех клеток — карта лагов, факты и реестр."""
    p_last: int                            # последний закрытый квартал прибыли (номер на линейке сетки)
    open: tuple[OpenQuarter, ...]          # открытые кварталы прибыли клетки, по порядку
    by_q: Mapping[int, tuple[OpenQuarter, ...]]     # квартал клетки → решения, по порядку кварталов прибыли
    years: tuple[int, ...]                 # годы прибыли словаря DPS: все решения года приходятся на сетку
    closed_dps: Mapping[int, float]        # год → Σ DPS строк истории закрытых кварталов года
    payable: tuple[tuple[int, int, float], ...]     # состояние якоря: (квартал выплаты, квартал вычета, сумма)
    periods: Mapping[str, OpenQuarter] = field(default_factory=dict)       # период → открытый квартал клетки
    year_periods: Mapping[int, tuple[str, ...]] = field(default_factory=dict)   # год словаря → открытые кварталы

    def closed(self, idx: int) -> bool:
        return idx <= self.p_last


def quarter_calendar(policy: Policy, facts: "Facts", timeline: Any, register: Sequence[Any], facts_date: Any,
                     dividends_payable: float = 0.0) -> QuarterCalendar:
    """Открытые кварталы прибыли по кварталам клетки и состояние якоря (М§5.7.2, §5.7.4).

    Квартал прибыли p > p_last открыт; квартал клетки решения — max(1, квартал решения по карте, квартал даты
    решения записи реестра). Вычет из регуляторного капитала и выплата — по датам записи, без них — по карте,
    не раньше квартала решения. Решение за сеткой остаётся терминалу. Объявленная часть дивидендов к выплате
    якоря (`balance.dividends_payable_declared`) — в очереди выплат и вычетов; остаток — постоянное
    обязательство. В годовую сумму DPS закрытый квартал входит строкой истории своего периода; закрытый квартал
    без своей строки покрыт строкой более позднего квартала (одно решение за несколько кварталов) и даёт ноль
    (М§5.7.5)."""
    rule, tl = policy.rule, timeline
    facts_date = to_date(facts_date)
    p_last = closed_through(facts, tl, facts_date)
    records: dict[str, Any] = {}
    for rec in register:
        if getattr(rec, "status", None) not in DECLARED:
            continue
        if not getattr(rec, "period", None):
            raise FactsError(f"реестр дивидендов: запись за {rec.year} год без квартала прибыли — при квартальном "
                             "календаре объявленная запись несёт период (М§5.7.6)")
        records[record_key(rec, True)] = rec
    open_: list[OpenQuarter] = []
    for idx in range(p_last + 1, tl.Q):                   # лаг решения не меньше квартала: позже — за сеткой
        period, h = tl.period(idx), tl.h(idx)
        q, q_reg, q_pay, dps = max(1, rule.q_dec(idx, h)), rule.q_reg(idx, h), rule.q_pay(idx, h), None
        rec = records.get(period)
        if rec is not None:
            decided = getattr(rec, "decided_date", None)
            if decided is not None:
                if decided <= facts_date:
                    raise FactsError(f"реестр дивидендов: запись за {period} с решением {decided} не позже даты "
                                     f"фактов {facts_date}, а строки в истории дивидендов нет — сначала правятся "
                                     "факты (М§5.7.6)")
                q = max(q, tl.q_of_date(decided))
            if rec.record_date is not None:
                q_reg = tl.q_of_date(rec.record_date)
            if rec.pay_date is not None:
                q_pay = tl.q_of_date(rec.pay_date)
            dps = float(rec.dps)
        if q <= tl.Q:
            open_.append(OpenQuarter(idx=idx, period=period, year=tl.year(idx), h=h, q=q, q_reg=max(q, q_reg),
                                     q_pay=max(q, q_pay), dps=dps))
    by_q: dict[int, list[OpenQuarter]] = {}
    for o in open_:
        by_q.setdefault(o.q, []).append(o)
    # годы словаря DPS: хотя бы один квартал прибыли открыт и ни одно решение года не ушло за сетку
    in_cell = {o.idx for o in open_}
    history = {str(_plain(r.get("period"))): r for r in facts.file("dividends").get("history") or []}
    years, closed_dps = [], {}
    for year in range(tl.year(p_last + 1), tl.last_year + 1):
        quarters = tl.quarters_of_year(year)
        after = [x for x in quarters if x > p_last]
        if not after or any(x not in in_cell for x in after):
            continue
        total = 0.0
        for x in quarters:
            if x > p_last:
                continue
            row = history.get(tl.period(x))
            if row is None:
                # квартал покрыт строкой истории более позднего квартала (решение «за девять месяцев» несёт
                # период последнего из покрытых): его дивиденд уже стоит в той строке — здесь ноль (М§5.7.5)
                continue
            dps = history_dps(row)
            if dps is None:
                raise FactsError(f"dividends.history: в строке за закрытый квартал прибыли {tl.period(x)} нет DPS — "
                                 f"годовой дивиденд {year} года не определён (М§5.7.5)")
            total += dps
        years.append(year)
        closed_dps[year] = total
    # состояние якоря: объявленные и не выплаченные дивиденды закрытых кварталов прибыли
    payable, seen, declared_sum = [], set(), 0.0
    for i, item in enumerate(facts.file("balance").get("dividends_payable_declared") or []):
        period, amount = str(_plain(item.get("period"))), _plain(item.get("amount"))
        if amount is None:
            raise FactsError(f"balance.dividends_payable_declared.{i}: нет суммы")
        idx = tl.index(period)
        if idx > p_last:
            raise FactsError(f"balance.dividends_payable_declared.{i}: квартал прибыли {period} не закрыт до якоря "
                             "(М§5.7.4)")
        if period in seen:
            raise FactsError(f"balance.dividends_payable_declared.{i}: период {period} повторяется (М§5.7.4)")
        seen.add(period)
        declared_sum += float(amount)
        h, rec = tl.h(idx), records.get(period)
        q_reg = tl.q_of_date(rec.record_date) if rec is not None and rec.record_date is not None else rule.q_reg(idx, h)
        q_pay = tl.q_of_date(rec.pay_date) if rec is not None and rec.pay_date is not None else rule.q_pay(idx, h)
        payable.append((max(1, q_pay), q_reg, float(amount)))
    if declared_sum > dividends_payable + CAP_TOL:
        raise FactsError(f"balance.dividends_payable_declared: сумма {declared_sum:g} больше дивидендов к выплате "
                         f"якоря {dividends_payable:g} (М§5.7.4)")
    return QuarterCalendar(p_last=p_last, open=tuple(open_), by_q={q: tuple(v) for q, v in by_q.items()},
                           years=tuple(years), closed_dps=closed_dps, payable=tuple(payable),
                           periods={o.period: o for o in open_},
                           year_periods={y: tuple(o.period for o in open_ if o.year == y) for y in years})


class BaseShare(NamedTuple):
    """Базовый дивиденд одного решения квартала: источник (`register` | `crisis_skip` | `model`) и сумма."""
    source: str
    base_div: float


class QuarterBases(NamedTuple):
    """Базовые дивиденды решений квартала (`quarter_bases`)."""
    wants: list[float]                     # пулы политики решений, млрд ₽ (на акции в обращении)
    cancelled: bool                        # решения модели отменены годом шока
    live: list[int]                        # номера решений модели в силе
    total: float                           # сумма их пулов
    div_base: float                        # базовый дивиденд квартала: min(Σ пулов, запас)
    shares: list[BaseShare]                # по решениям, по порядку кварталов прибыли


def first_payout(policy: Policy, year: int, memo: dict | None = None) -> float:
    """Доля выплаты первой ступени политики за год прибыли; `memo` — память вызывающего (год → доля): у клеток
    одного прогона политика одна."""
    if memo is None:
        return policy.payouts(year)[0]
    got = memo.get(year)
    if got is None:
        got = memo[year] = policy.payouts(year)[0]
    return got


def quarter_bases(policy: Policy, *, due: Sequence[OpenQuarter], bases: Sequence[float], headroom: float,
                  shock: bool, payout: dict | None = None, n_out: float | None = None) -> QuarterBases:
    """Базовые дивиденды решений квартала (М§5.7.4 пп. 1–3) — без догоняющей выплаты и избытка: запись реестра —
    обязательство без проверок; в год шока решения модели отменены; базовый дивиденд квартала — min(Σ пулов,
    запас), между решениями — пропорционально пулам. Одна функция у решений квартала (`decide_quarter`) и у
    условия роста по капиталу (М§4.13.2 п. 2), которому нужны только базовые суммы. `payout` — память долей
    выплаты политики (`first_payout`). `n_out` — акции в обращении клетки в квартале решения (выкуп по цене мира,
    М§5.6); без него — акции в обращении якоря."""
    n_c = policy.n_out if n_out is None else n_out
    out_share = n_c / policy.n_iss                        # дивиденд на собственные акции остаётся в группе
    wants = [first_payout(policy, o.year, payout) * max(0.0, base) * out_share for o, base in zip(due, bases)]
    cancelled = shock and policy.skip_in_shock
    live = [] if cancelled else [i for i, o in enumerate(due) if o.dps is None]      # решения модели в силе
    total = sum(wants[i] for i in live)
    div_base = min(total, max(0.0, headroom)) if live else 0.0
    shares = []
    for o, want in zip(due, wants):
        if o.dps is not None:
            div = o.dps * n_c / THOUSAND
            shares.append(BaseShare("register", div))
        elif cancelled:
            shares.append(BaseShare("crisis_skip", 0.0))
        else:
            shares.append(BaseShare("model", want if div_base == total else div_base * want / total))
    return QuarterBases(wants, cancelled, live, total, div_base, shares)


class TokenNeed(NamedTuple):
    """Недостача года до жетона DPS (К1): сумма (млрд ₽), жетон года m_Y и уже решённое S_Y (₽ на акцию)."""
    need: float
    m_y: float
    s_y: float


def token_need(*, min_dps: float, base_year: float, n_iss: float, n_c: float, closed_dps: float, prior_dps: float,
               same_dps: float) -> TokenNeed:
    """Недостача года прибыли Y до жетона DPS (К1, М§4.13.2 п. 2а): m_Y = min(min_dps(Y), max(0, base_Y) × 1000 / N_iss)
    — жетон не больше прибыли года на размещённую акцию (при убытке — 0); S_Y = DPS закрытых кварталов года + DPS
    решений года в прошлых кварталах клетки + базовые дивиденды решений года в квартале на акцию клетки; need =
    max(0, m_Y − S_Y) × N_c / 1000."""
    m_y = min(min_dps, max(0.0, base_year) * THOUSAND / n_iss)
    s_y = closed_dps + prior_dps + same_dps
    return TokenNeed(max(0.0, m_y - s_y) * n_c / THOUSAND, m_y, s_y)


def token_carrier(due: Sequence[OpenQuarter], shock: bool, policy: Policy) -> int | None:
    """Носитель жетона и избытка — последнее неотменённое решение модели квартала за квартал прибыли с h(p) = 4."""
    if shock and policy.skip_in_shock:
        return None
    annual = [i for i, o in enumerate(due) if o.dps is None and o.h == LAST_QUARTER]
    return annual[-1] if annual else None


def decide_quarter(policy: Policy, *, q: int, due: Sequence[OpenQuarter], bases: Sequence[float], headroom: float,
                   deferred: float, shock: bool, headroom_final: float | None = None,
                   growth_cut: bool = False, payout: dict | None = None, n_out: float | None = None,
                   token: float = 0.0, token_carrier: int | None = None,
                   headroom_floor: float | None = None) -> list[Decision]:
    """Решения квартала клетки q (М§5.7.4 пп. 1–5, §5.7.5) — по порядку кварталов прибыли `due`.

    `bases` — базы кварталов прибыли (средняя прибыль окна); `headroom` — запас квартала без решений модели
    (H_ref), `headroom_final` — запас при итоговых объёмах (H_fin; без ограничения роста — тот же). Запись
    реестра — обязательство без проверок; в год шока решения модели отменены; базовый дивиденд квартала —
    min(Σ пулов, запас), между решениями — пропорционально пулам (`quarter_bases`); догоняющая выплата и доля
    избытка — целиком в решении за четвёртый квартал прибыли. `growth_cut` — прирост кредитных книг квартала
    урезан капиталом (λ* < 1, М§4.13.2 п. 6): догоняющей выплаты и избытка нет — остаток запаса в пределах
    допуска не избыток. `payout` — память долей выплаты политики (`first_payout`). `n_out` — акции в обращении клетки
    в квартале решения (выкуп по цене мира, М§5.6): на них пул, запись реестра и DPS. `token` — жетон DPS решения-носителя
    `token_carrier` (К1, М§4.13.2 п. 2а): входит в его дивиденд, догоняющая выплата и избыток — за его вычетом;
    `headroom_floor` — запас, по которому жетон решён (печать решения)."""
    h_fin = headroom if headroom_final is None else headroom_final
    wants, cancelled, live, total, div_base, shares = quarter_bases(policy, due=due, bases=bases, headroom=headroom,
                                                                    shock=shock, payout=payout, n_out=n_out)
    n_c = policy.n_out if n_out is None else n_out
    cut = div_base < total - CUT_TOL
    annual = [i for i in live if due[i].h == LAST_QUARTER]
    carrier = annual[-1] if annual else None              # решение, несущее догоняющую выплату и избыток
    catch = exc = 0.0
    if token and token_carrier != carrier:
        raise BookError(f"квартал {q}: жетон DPS решён не у носителя избытка (решение {token_carrier}, носитель "
                        f"{carrier}; М§4.13.2)")
    if carrier is not None and not growth_cut:
        base_t = div_base + token if token else div_base   # жетон носителя — раньше догоняющей выплаты и избытка
        catch = min(deferred, max(0.0, h_fin - base_t)) if policy.catch_up else 0.0
        eps = policy.epsilon_at(due[carrier].year)
        exc = eps * max(0.0, h_fin - base_t - catch) if eps else 0.0
        if exc == float("inf") or catch == float("inf"):
            raise BookError("запас капитала бесконечен: квартал решения о дивиденде не оценён")
    out: list[Decision] = []
    for i, (o, base, want) in enumerate(zip(due, bases, wants)):
        common = dict(year=o.year, period=o.period, q=q, base=base, want=(want,), headroom=(headroom,),
                      headroom_final=h_fin, step=0, deferred_before=deferred)
        base_div = shares[i].base_div
        if o.dps is not None:
            out.append(Decision(base_div=base_div, catch=0.0, excess=0.0, div=base_div, dps=o.dps,
                                deferred_after=deferred, source="register", cut=False, **common))
        elif cancelled:
            after = deferred + want if policy.catch_up else deferred
            out.append(Decision(base_div=0.0, catch=0.0, excess=0.0, div=0.0, dps=0.0, deferred_after=after,
                                source="crisis_skip", cut=False, flags=("crisis_skip",), **common))
            deferred = after
        else:
            paid_catch, paid_exc = (catch, exc) if i == carrier else (0.0, 0.0)
            div = base_div + paid_catch + paid_exc
            tok: dict[str, Any] = {}
            paid_token = token if i == carrier else 0.0
            if paid_token:                      # жетон DPS (К1): в дивиденде носителя, флаг решения
                div = base_div + paid_token + paid_catch + paid_exc
                tok = {"token": paid_token, "flags": (("dividend_cut",) if cut else ()) + ("dividend_token",)}
            if headroom_floor is not None and i == carrier:
                tok["headroom_floor"] = headroom_floor
            out.append(Decision(base_div=base_div, catch=paid_catch, excess=paid_exc, div=div,
                                dps=div * THOUSAND / n_c, deferred_after=deferred - paid_catch,
                                source="model", cut=cut, **{"flags": ("dividend_cut",) if cut else (), **tok},
                                **common))
            deferred -= paid_catch
    return out
