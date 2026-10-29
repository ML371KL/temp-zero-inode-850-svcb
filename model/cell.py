"""Квартальный проход клетки (мир × режим × регуляторный сценарий) в порядке М§4.2.

В квартале q: (1) в квартал ГОСА — решение о дивиденде (пробный проход с состояния
на конец q − 1); (2) ставки мира и пути режима и сценария; (3) объёмы небалансирующих
статей; (4) ставки книг; (5) предварительный баланс при BV_(q−1) − Div_q и DP_q;
(6) строки ОПУ; (7) капитал — OCI, купон AT1, прочие движения, BV_q; (8) окончательный
баланс при BV_q; (9) RWA и нормативы. Затем терминал (М§7) и оценка RI/DDM (М§6).

Сдвиг ЧПМ в ЧПД — ближний (`regimes.near_nim_shift`, общий для клеток) + сдвиг режима +
отклонение A-P2u (М§4.4). «Прочее» ОПУ — годовая сумма × индекс цен × доля квартала
(`other.misc_quarter_shares`, М§4.7) — и в году якоря: остатком год не закрывается, сумма
года — выход (М§0.3); остатком закрывается только непрофильный результат. Кредитная
переоценка кредитов по СС (FVC) — отклонение CoR клетки от пути режима-опоры
`credit.fv_loans_ref` на средних кредитах по СС, внутри шага; опора — путь книги до
розыгрыша осей (`Book.base`, М§4.6). Сжатие φ: доля `nii.phi_split` — в спредах кредитных
книг (φ_A), остаток — добавкой φ_L × X_W,q к стоимости пассивов с `phi` (М§4.4). Доход на
избыток капитала терминала — по маржинальной ставке балансирующих статей (М§7). Предварительный
проход (`preliminary_paths`) — клетка без отклонений A-P2u до заданного квартала: ожидания
режимов μ (М§12). Ключи второй формы банка (все необязательны; нет ключа — прежняя строка кода): премия роста
траекториями по секторам (`volumes.loan_share_drift`, `funds_share_drift`), постоянные прочие активы
(`volumes.other_assets_fixed`), связь комиссий, страхования и расходов с ростом объёма (`*.volume_link`,
`volumes.link_base`, М§4.7), множитель RWA режима (`regimes.<r>.rwa_density_mult`, М§4.11).

Квартальный календарь дивидендов (`dividends.calendar.frequency: quarterly`, М§5.7): в квартале клетки от нуля
до двух решений — записи реестра и решения модели за открытые кварталы прибыли (`Prepared.calendar`). Запас
капитала под решения модели — оценка шага этого же квартала на копии состояния, без записи и без решений модели
(`_Cell.quarter_room`: одна точка, пробных проходов вперёд нет); квартал считается один раз с суммой дивидендов,
у каждого решения свои кварталы выплаты и вычета из регуляторного капитала. Терминал не раздаёт как избыток
дивиденды, уже вычтенные из BV, но ещё стоящие в регуляторном капитале (М§7). Без ключа — годовой проход.

Рост, ограниченный капиталом (`capital.growth_constraint`, М§4.13; только при квартальном календаре): дивиденд и
доля прироста кредитных книг λ квартала определяются вместе, оценками шага на копии состояния
(`_Cell.evaluate`). Требование — с глиссадой к известным ступеням (`capital.glide_path`), Н20.1 ограничения — с
прибылью периода. λ* — закрытая формула по двум оценкам (полный рост и наименьший), проверочная полная оценка и не
больше одного шага секущей; при λ* = 1 и запасе — навёрстывание разрыва с потенциальным путём, раньше выплаты
избытка. Принятая оценка и есть запись шага (`_Cell.run_constrained`). Объекта нет или он выключен — рост задан.

Книжные величины, общие для всех клеток прогона, готовит `prepare` (один раз на
прогон); клетка читает их из контекста `RunContext` (model/grid.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from operator import methodcaller
from typing import TYPE_CHECKING, Any, Mapping

from model.book import (AnchorFacts, BookRoles, CASH_NODE, RESERVES_NODE, SECURITIES, LIQUIDITY, WHOLESALE, anchor_facts,
                        book_roles, funds_books)
from model.book_schema import BookError, FactsError
from model.capital import (CASH_DENSITY, CapitalConst, GrowthRule, RwaWeights, ScenarioPath, after_audit_start,
                           capital_const, carve_cash, carve_guarantees, density_index, fx_index, glide_path, growth_rule,
                           n11_audited, ratios, regime_rwa_mult, rwa_anchor, rwa_weights, scenario_path)
from model.credit import Bridge, fvc_amount, kappa_addon, kappa_world, regime_cor_engine
from model.dividends import (DECLARED, THOUSAND, Checkpoint, Decision, Policy, QuarterCalendar, base_of_year, decide,
                             decide_quarter, headroom, make_policy, pool_policy, quarter_bases, quarter_calendar,
                             record_key, register_dps, token_carrier, token_need)
from model.nii import current_share_target, phi_shares, spread_paths
from model.paths import Trajectory
from model.timeline import DAYS_IN_YEAR, QUARTER_YEARS, Timeline, make_clock, parse_period, period_str, to_date
from model.valuation import (CALENDAR, FUNDING_BALANCING, FUNDING_BINARY, MEAN, MEAN_YEAR, FixedInputs, fade_anchor,
                             fade_symmetric, fixed_funding, fixed_terms, terminal, value_cell, year_basis)
from model.worlds import BASE_WORLD, Discount, WorldPath, discount

if TYPE_CHECKING:
    from model.book import Book, Facts
    from model.grid import RunContext
    from model.nii import Transmission

# Строки кварталов CellResult.quarters (индекс q = 0…Q; q = 0 — якорь по фактам).
QUARTER_FIELDS = (
    "bv", "ni_sh", "ni", "pbt", "nii", "llp", "fvc", "fees", "opex", "ins", "misc", "noncore", "fvr",
    "one_off", "tax", "ot", "oci", "coupon", "om", "ci", "div", "dp", "dpreg", "pay", "reserve",
    "rwa", "k20", "k11", "n20", "n11", "ded20", "ded11", "e_unaudited", "req20", "req11", "floor20",
    "floor11", "loans", "loans_ac", "loans_fv", "funds", "funds_retail", "iea", "iea_avg",
    "loans_ac_avg", "loans_fv_avg", "assets", "liabilities_equity", "securities", "liquidity", "wholesale",
    "wholesale_extra", "other_assets", "other_liabilities", "allowance", "current_share",
    "nim", "cor", "cir", "roe_q", "k_q", "key", "tau_stat", "tau_eff", "int_income", "int_expense",
    "dia", "overlay",
    "div_model",                           # часть div, решённая моделью, а не записью реестра (М§5.7.5)
    # рост, ограниченный капиталом (М§4.13.3); при выключенном механизме — λ = 1, требование без глиссады
    "lam", "loans_potential", "catch_up", "req20_glide", "req11_glide",
    "n11_star",                            # Н20.1 с прибылью периода (М§4.11)
)
# Ряды ключей прохода (только при ключе книги, `quarter_fields`): CoR на составе якоря — CoR клетки — и резервы
# при ней (`credit.book_relative`, М§4.6).
BOOK_REL_FIELDS = ("cor_mix0", "llp_mix0")
# ... и база связи расходов с объёмом, взвешенная по себестоимости книг (`opex.volume_weights`, М§4.7).
OPEX_W_FIELDS = ("vol_opex",)
# ... и выкуп по цене мира (`dividends.buyback`, М§5.6): сумма квартала, акции клетки на конец квартала, цена покупок,
# форвард цены после дивидендов квартала, дивиденд на внешнюю акцию.
BB_FIELDS = ("bb", "n_out", "p_bar", "p_plus", "d_ext")
# ... и RWA гарантий квартала с дрейфом плотности, валютным индексом и множителем режима (`capital.rwa.guarantees`, К5).
GUAR_FIELDS = ("rwa_guar",)
# ... и неработающие деньги на конец квартала (`volumes.cash_assets`, К8).
CASH_FIELDS = ("cash",)
WORLD_FORWARD, CELL_VALUE, MARKET = "world_forward", "cell_value", "market"   # правила цены выкупа (М§5.6)
BB_MAX_ITER = 30                             # итераций неподвижной точки «цена = стоимость клетки» (М§5.6)
BB_TOL = 1e-9                                # её относительный допуск
# Ряды-базы «к тому же кварталу», которые шаг пишет в клетку: оценка шага на копии состояния их снимает.
STEP_FLOWS = ("fees", "opex", "ins", "ni_sh", "vol", "vol_opex")
STEP_FLOWS += ("vol_fees", "vol_ins", "vol_mix")    # базы строк по своим ключам и смесь базы расходов (К2, М§4.7)
# номинальная часть франшизы строки H^ℓ (Р8-6, М§4.7): ряд клетки — только при ключе `opex.line_share_roots`
NOM_FLOWS = {"fees": "vol_nom_fees", "insurance": "vol_nom_ins"}
STEP_FLOWS += tuple(NOM_FLOWS.values())
# уровень базы строки-драйвера книг К6 на конец квартала D^ℓ_q (Р9-1, М§4.3): ряд клетки — только при ключе
# `volumes.liability_driver_roots`; не в STEP_FLOWS — уровень конца квартала — функция состояния, не поток
END_FLOWS = {"fees": "vol_end_fees", "insurance": "vol_end_ins"}
# одна форма связи λ (Р10-5, проход ядра 8, М§4.7; ключ `volumes.line_link_form: line`): франшиза строки Φ^ℓ (на средних
# базы строки, вместо H^ℓ) и индекс книг К6 строки Ψ^ℓ (на концах кварталов) — ряды клетки только при ключе; уровень базы
# строки на концах D^ℓ «к тому же кварталу» (лаг 4) — внутренний ряд шага (не ряд клетки; ряд клетки vol_end_<ℓ> —
# по-прежнему вне STEP_FLOWS: уровень конца квартала — функция состояния). Все три — в STEP_FLOWS
PHI_FLOWS = {"fees": "vol_phi_fees", "insurance": "vol_phi_ins"}
PSI_FLOWS = {"fees": "vol_psi_fees", "insurance": "vol_psi_ins"}
LAG_END_FLOWS = {"fees": "k6_end4_fees", "insurance": "k6_end4_ins"}
STEP_FLOWS += tuple(PHI_FLOWS.values()) + tuple(PSI_FLOWS.values()) + tuple(LAG_END_FLOWS.values())
LINE_LINK_FORM, FORM_MIXED, FORM_LINE = "volumes.line_link_form", "mixed", "line"


def link_growth(ratio: float, wage: float, lam: float, root: float, mult: bool) -> float:
    """Рост г/г за связью λ формой строки (М§4.7; Р10-5 — одна форма у строки, франшизы и книг К6): `ratio` — база
    квартала к тому же кварталу прошлого года, `wage` — рост зарплат мира клетки г/г, `root` — корень квартала; при
    `mult` (`volumes.line_root_form: multiplicative`) — (1 + w + λ (x − 1 − w)) (1 + r), иначе — 1 + w + r + λ (x − 1 − w).
    Порядок операций — как у строки страхования: 1 + wage + link × (x − 1 − wage)."""
    if mult:
        return (1 + wage + lam * (ratio - 1 - wage)) * (1 + root)
    return 1 + wage + root + lam * (ratio - 1 - wage)


LINES = "lines"                            # ключ памяти оценок шага: ряды баз строк квартала (К2)
# Годовые ряды роста кредитных книг CellResult.growth (по годам клетки, М§4.13.3).
GROWTH_FIELDS = ("potential", "actual", "cut_share", "catch_up", "lam_min")
FUNDS_SIDE = "funds"                         # ключ памяти оценок шага: сторона средств клиентов квартала
CALENDAR = "calendar"                        # ключ общего прогона: годы и номера кварталов сетки
PAYOUT = "payout"                            # ключ общего прогона: доля выплаты политики по годам прибыли
ANCHOR = "anchor"                            # ключ общего прогона: строка якоря сценария капитала
SLOPE_TOL = 1e-9                             # млрд ₽: урезание роста норматив не поправляет — делить не на что
LAM_TOL = 1e-12                              # λ* < 1 − допуск — прирост квартала урезан (флаг growth_cut)
NAMED_LITERALS = {
    1e-9: "SLOPE_TOL: порог наклона условия роста по доле прироста, млрд ₽ (М§4.13.2 п. 3)",
    1e-12: "LAM_TOL: допуск признака «рост урезан» (М§4.13.3)",
    30: "BB_MAX_ITER: итераций неподвижной точки цены выкупа «стоимость клетки» (М§5.6)",
    0.05: "RESID_MAX: предел |R_0| / AL_0 — остаток резерва якоря вне книг (резерв по книгам, К7, М§4.6)",
}


# ------------------------------------------------------------------ подготовка прогона


@dataclass(frozen=True)
class RegimePath:
    regime: str
    cor_engine: tuple[float, ...]          # путь CoR режима в базисе движка (без κ и δ)
    nim_shift: tuple[float, ...]           # сдвиг ЧПМ режима (без ближнего сдвига)
    loan_adj: Mapping[int, float]          # год → поправка к росту кредита
    override: Mapping[int, float]          # год → абсолютный рост (кризис)
    one_off_q: int | None
    one_off_amount: float
    shock_year: int | None                 # год шока = год якоря + shock_year_offset (М§3.2); нет ключа — None
    rwa_mult: tuple[float, ...] | None = None   # M_r,q — множитель RWA режима (М§4.11); нет ключа — None


@dataclass(frozen=True)
class Buyback:
    """Выкуп акций по цене мира (М§5.6, ключ `dividends.buyback`): общее для клеток прогона. Цена покупок — от цены
    книги и платы за капитал мира на дату книги (k_b — ряд `disc[мир].k` с квартала даты книги); от живой цены и даты
    оценки проход не зависит. Поля — входы прохода (ключ кэша проходов `model.grid.path_keys` их видит)."""
    rule: str                              # world_forward | cell_value | market
    amount: tuple[float, ...]              # B_q, млрд ₽ за квартал, q = 0…Q
    p_book: float                          # P_b — цена книги главного тикера
    qb: int                                # q_b — квартал даты книги (конец дня)
    e_book: float                          # доля прошедшего квартала q_b на дату книги
    closed: Mapping[int, float]            # закрытые кварталы q < q_b → средняя цена покупок
    disc: Mapping[str, Discount]           # мир → дисконт на дату книги
    bridge_dps: Mapping[int, float]        # d^R_q: DPS записей закрытых кварталов прибыли с экс-датой в q
    skip: bool                             # skip_in_shock_year: в год шока режима выкупа нет


@dataclass(frozen=True)
class LineBase:
    """База строки (М§4.7, К2): что считается объёмом строки — кредиты, средства клиентов, процентные активы, номинал
    (индекс зарплат мира) или книги ЧПД с весами. Уровень на конец квартала D_q читают RWA гарантий (К5) и
    книги-обязательства за драйвером строки (К6); средние остатки по кварталам A_x — рост строки г/г (К2)."""
    kind: str                              # loans | funds | iea | nominal | books
    weights: Mapping[str, float] | None = None     # ω книг (вид books)
    end0: float = 1.0                      # D_0 — уровень базы на конец квартала якоря (у номинала — 1)
    hist: Mapping[int, float] | None = None        # A_x, x = −3…0 — средние остатки по фактам (только при связи строки)
    balancing: bool = False                # база читает балансирующие книги: iea или вес у бумаг, ликвидности, опта


@dataclass(frozen=True)
class Guarantees:
    """Составляющая RWA гарантий (К5, М§4.11): G_q = G_0 × D^G_q / D^G_0 — драйвер `fees_base` (уровень базы комиссий
    на конец квартала), `fees_component` (уровень базы одной компоненты смеси базы комиссий, Р5-5) или `fees_line`
    (строка комиссий за четыре квартала, справочно)."""
    g0: float                              # G_0 = (N_нф CCF_нф + N_ф CCF_ф) × вес
    carve: str                             # книга выреза из плотности
    driver: str                            # fees_base | fees_component | fees_line
    base: LineBase | None                  # база драйвера-уровня: комиссий (fees_base) или компоненты (fees_component)
    d0: float                              # D^G_0


@dataclass(frozen=True)
class Cash:
    """Неработающие деньги со своим драйвером (К8, М§4.3, §4.11): C_q = c D_q, c = C_0 / D_0 — D_q уровень драйвера на
    конец квартала; растущие прочие активы без денег — ρ′ = ρ − C_0 / L_0 на рубль кредита.

    Доля денег книги (Р6-1, проход ядра 5): c_q = s_q + r — путь доли без ФОР от доли якоря к доле книги s* линейно по
    кварталам до `share_from`, ФОР — доля якоря r = R_0 / D_0; растущие прочие без денег ρ′_q = ρ − c_q D_0 / L_0;
    вытесненная часть прочих активов δ_q = (c_q − c_0) D_0 / L_0 на рубль кредита весит в RWA слагаемым
    (1 − θ)(ω′_oa − ω_c) δ_q (`shift_q`, считает `prepare` после выреза плотности). Без доли книги поля пути — None:
    прежняя строка."""
    c0: float                              # C_0 — деньги якоря, млрд ₽
    base: LineBase                         # драйвер: средства клиентов (с ведомыми книгами К6), кредиты или веса книг
    share: float                           # c = C_0 / D_0
    rho: float                             # ρ′ = ρ − C_0 / L_0
    share_q: tuple[float, ...] | None = None   # Р6-1: c_q = s_q + r, q = 0…Q (c_0 = C_0 / D_0); None — прежняя строка
    rho_q: tuple[float, ...] | None = None     # Р6-1: ρ′_q = ρ − c_q D_0 / L_0
    reserves: float | None = None              # Р6-1: r = R_0 / D_0 — ФОР долей якоря
    delta_q: tuple[float, ...] | None = None   # Р6-1: δ_q = (c_q − c_0) D_0 / L_0 — вытесненная часть на рубль кредита
    theta: float | None = None                 # Р6-1: θ (`displaced_weight`); None — поля нет или θ = 1 (слагаемого нет)
    shift_q: tuple[float, ...] | None = None   # Р6-1: (1 − θ)(ω′_oa − ω_c) δ_q — слагаемое RWA на рубль кредита


@dataclass(frozen=True)
class Prepared:
    """Книжные величины прогона, общие для 36 клеток."""
    timeline: Timeline
    roles: BookRoles
    books: Mapping[str, Mapping[str, Any]]
    af: AnchorFacts
    spreads: Mapping[str, tuple[float, ...]]
    phi: float                             # φ — сжатие целиком
    reference_world: str
    regimes: Mapping[str, RegimePath]
    scenarios: Mapping[str, ScenarioPath]
    dn: tuple[float, ...]
    rwa_w: RwaWeights
    cap: CapitalConst
    policy: Policy
    anchor_year: int
    guidance_year: int
    guidance_growth: Mapping[str, float]
    loan_share_drift: float
    funds_share_drift: float
    drift_until: int
    liquid_min: float
    sec_share: float
    wh_to_funds: float
    oa_ratio: float
    ol_ratio: float
    allowance_ratio: float
    fv_share: float
    fv_book: str | None
    c_ref: float
    psi: float
    key_ref: float
    c_bounds: tuple[float, float]
    c_rho: float
    dia: float
    fees_gvw: tuple[float, ...]
    fees_override: Mapping[int, float]     # год → рост (год якоря — рост остатка года gF_rest)
    opex_real: tuple[float, ...]
    ins_gvw: tuple[float, ...]
    noncore_q: Mapping[int, float]         # год → сумма в цены якоря на квартал (год якоря — остаток)
    misc_q: Mapping[tuple[int, int], float]   # (год, квартал) → «прочее» квартала в ценах якоря (М§4.7)
    tau_stat: Mapping[int, float]
    tax_gap: float
    ot_q: int | None
    ot_amount: float
    other_movements: tuple[float, ...]
    t2: tuple[float, ...]
    nci_share: float
    fv_factor: float
    kappa: float
    lag: int
    segment_rel: Mapping[str, float] | None
    coupon_annual: float
    coupon_quarter: int
    hist: Mapping[str, Mapping[int, float]]   # fees, opex (C > 0), ins, ni_sh по q ≤ 0
    hist_bal: Mapping[int, Mapping[str, float]]   # концы кварталов до якоря: bv, loans_ac, iea (balance.history)
    fvoci_duration: float
    fvoci_maturity: float
    fvoci_share: float
    fvoci_tenor: str
    y_tenor0: float
    fvr_on: bool
    fvtpl_share: float
    fvtpl_duration: float
    real_growth: float
    fade: float
    multiple: float
    register: Mapping[Any, float]          # ключ записи реестра → объявленный DPS: год прибыли, а при
    #                                        квартальном календаре — квартал прибыли (то же у двух полей ниже)
    reg_q_by_year: Mapping[Any, int]       # ключ записи → квартал вычета из рег. капитала (реестр)
    pay_q_by_year: Mapping[Any, int]
    rwa0: float
    anchor_state: Mapping[str, float]
    near: tuple[float, ...] = ()           # ближний сдвиг ЧПМ по q = 0…Q (М§3.2)
    misc_shares: Mapping[int, float] = field(default_factory=dict)   # доля квартала h в годовой сумме
    fv_ref: str = ""                       # режим-опора FVC (credit.fv_loans_ref, М§4.6)
    fv_ref_cor: tuple[float, ...] = ()     # путь опоры FVC в базисе движка — по книге до розыгрыша (Book.base)
    phi_assets: float = 0.0                # φ_A — сжатие спредов активов с phi
    phi_liab: float = 0.0                  # φ_L — добавка к стоимости пассивов с phi на единицу X_W,q
    phi_weights: Mapping[str, float] = field(default_factory=dict)   # ω_b книг Φ_A в X_W,q (М§4.4)
    # вторая форма банка (ключи необязательны)
    loan_drift: Mapping[str, Mapping[int, float]] | None = None    # сектор → год → премия роста кредитов (словарь книги)
    funds_drift: Mapping[str, Mapping[int, float]] | None = None   # сегмент → год → премия роста средств клиентов
    funds_drift_q: Mapping[str, Mapping[tuple[int, int], float]] = field(default_factory=dict)
    #                                            сегмент → (год, квартал) → премия квартала: только у траектории с
    #                                            ключами квартала или полугодия (М§4.3); пусто — значение года
    oa_fixed: float = 0.0                  # OA_fixed — прочие активы, постоянные в рублях (М§4.3)
    link_fees: float = 0.0                 # связи с ростом объёма (М§4.7): комиссии,
    link_ins: float = 0.0                  # страхование,
    link_opex: float = 0.0                 # расходы
    link_base: str = ""                    # база объёма (loans | funds | iea); пусто — связей нет
    hist_vol: Mapping[int, float] = field(default_factory=dict)   # A_x, x ≤ 0 — средний остаток базы (факты)
    calendar: QuarterCalendar | None = None    # квартальный календарь дивидендов (М§5.7); None — годовой
    growth: GrowthRule | None = None           # ограничение роста капиталом (М§4.13); None — рост задан
    glide: Mapping[str, tuple[tuple[float, ...], tuple[float, ...]]] = field(default_factory=dict)
    #                                            сценарий → (req*_20, req*_11): требование с глиссадой по q = 0…Q
    kappa_world: str | None = None             # мир-опора κ-добавки (`credit.kappa_reference_world`, М§4.6); None —
    #                                            базовый мир, добавка только вверх
    fade_symmetric: bool = False               # угасание терминала при любом знаке ROE_T − k_T (М§7); False — одностороннее
    book_rel: Mapping[str, float] | None = None    # r̂_b — множители CoR кредитных книг, нормированные на составе якоря
    #                                            (`credit.book_relative`, М§4.6); None — сегменты или общая CoR
    opex_w: Mapping[str, float] | None = None      # ω̂_b — веса книг в базе связи расходов с объёмом, нормированные на
    #                                            квартале якоря (`opex.volume_weights`, М§4.7); None — база link_base
    hist_vol_opex: Mapping[int, float] = field(default_factory=dict)   # A^C_x, x ≤ 0 — взвешенная база (факты)
    opex_w_bal: bool = False                   # вес > 0 у балансирующей книги: расходы зависят от дивиденда квартала
    fixed_growth_share: float | None = None    # λ_F — блок постоянных частей терминала (М§7); None — прежний терминал
    fixed_parts: tuple[str, ...] | None = None     # части блока (`valuation.terminal.fixed_parts`)
    bb: Buyback | None = None                  # выкуп по цене мира (`dividends.buyback`, М§5.6); None — выкупа нет
    # второй проход ядра (ключи необязательны; нет ключа — прежняя строка кода)
    wh_anchor: float | None = None             # доля опта якоря при структурной доле (К3, М§4.10): `wh_to_funds` — s,
    #                                            сверх s опт идёт по нужде в обе стороны; None — ключа нет
    allow_cov: Mapping[str, float] | None = None   # cov_b — покрытие кредитной книги якоря (резерв по книгам, К7,
    #                                            М§4.6); None — резерв долей якоря `allowance_ratio`
    allow_resid: float = 0.0                   # R_0 — резерв якоря вне книг (облигации по АС и т. п.), млрд ₽
    loans_ac0: float = 0.0                     # кредиты по амортизированной стоимости якоря — масштаб роста R_0
    guar: Guarantees | None = None             # составляющая RWA гарантий (К5, М§4.11); None — её нет
    stationary_rates: bool = False             # терминал от стационарных ставок книг (К4, М§7): вход прохода клетки
    fees_line: LineBase | None = None          # база строки комиссий по своему ключу (К2, М§4.7); None — link_base
    ins_line: LineBase | None = None           # то же у страхования
    line_shares: Mapping[str, float] | None = None   # s_ℓ — доли базы расходов якоря на базах строк (К2); None — нет
    hist_vol_mix: Mapping[int, float] = field(default_factory=dict)   # A^C_x, x ≤ 0 — смесь базы расходов (факты)
    mix_keep: float = 1.0                      # 1 − Σ s_ℓ
    mix_b0: float = 0.0                        # B^C_0 — база расходов квартала якоря
    mix_src: Mapping[str, tuple[str, float]] = field(default_factory=dict)   # строка → (ряд базы, A^ℓ_0)
    line_flows: tuple[str, ...] = ()           # ряды баз строк клетки (vol_fees, vol_ins, vol_mix) — при своих ключах
    #                                            (и ряды номинальной части франшизы vol_nom_<ℓ> — при ключе Р8-6)
    memo_off: bool = False                     # база строки читает балансирующие книги: оценки шага квартала память не
    #                                            переиспользуют (обобщение opex_w_bal и link_base: iea)
    driven: Mapping[str, tuple[LineBase, float]] | None = None   # книга-обязательство → (база строки-драйвера, связь
    #                                            строки) — К6, М§4.3; None — книги растут с сектором средств бизнеса
    min_dps: Mapping[int, float] | None = None     # жетон DPS по году прибыли, ₽ на акцию (К1, М§4.13.2 п. 2а); None —
    #                                            ключа нет или он не читается (годовой календарь, рост задан)
    # третий проход ядра (ключи необязательны; нет ключа — прежняя строка кода)
    year_basis: str = CALENDAR                 # год терминала (К-Т2а, М§7): mean — средний год; вход прохода клетки
    fade_anchor: int | None = None             # год-якорь угасания Y_a (К-Т2в, М§7): параметр оценки; None — срок после T
    fixed_funding: str = FUNDING_BINARY        # ставка фондирования блока К-Т (К-Т2б, М§7): параметр оценки
    cash: Cash | None = None                   # неработающие деньги за своим драйвером (К8, М§4.3); None — в доле к кредитам
    # четвёртый проход ядра (ключи необязательны; нет ключа — прежняя строка кода)
    root_mult: bool = False                    # корень строк комиссий и страхования множителем (Р5-6, М§4.7):
    #                                            prev × (1 + рост базы) × (1 + корень); False — прежняя сумма
    # шестой проход ядра (ключ необязателен; нет ключа — прежняя строка кода)
    share_nominal: Mapping[str, tuple[float, tuple[float, ...], str]] | None = None
    #                                            франшиза строки за связью строки (Р8-6, М§4.7): строка смеси →
    #                                            (λ_ℓ — связь строки, κ_q по q = 0…Q, ряд H^ℓ клетки); None — ключа нет
    #                                            (франшиза целиком за базой строки, прежняя строка)
    hist_share_nominal: Mapping[str, Mapping[int, float]] = field(default_factory=dict)
    #                                            ряд H^ℓ → H^ℓ_x = A^ℓ_x / A^ℓ_0, x = −3…0 (факты базы строки)
    # седьмой проход ядра (ключ необязателен; нет ключа — прежняя строка кода)
    driver_roots: Mapping[str, tuple[str, tuple[float, ...]]] | None = None
    #                                            корень номинальной части книг К6 (Р9-1, М§4.3): ведомая книга →
    #                                            (строка-драйвер, ρ_q по q = 0…Q); None — ключа нет или он не читается
    #                                            (книга за драйвером без корня, прежняя строка)
    # восьмой проход ядра (ключ необязателен; нет ключа или mixed — прежняя строка кода)
    link_line: bool = False                    # франшиза строки (Р8-6) формой строки (Р10-5): Φ г/г с корнем κ; False —
    #                                            ключа нет, mixed или франшиза строки ключом κ не читается
    k6_line: Mapping[str, tuple[float, tuple[float, ...], LineBase]] | None = None
    #                                            книги К6 формой строки (Р10-5, М§4.3): строка-драйвер → (λ, ρ_q по
    #                                            q = 0…Q — нули без ключа ρ строки, база строки); None — ключа нет,
    #                                            mixed или К6 нет
    k6_books: Mapping[str, str] = field(default_factory=dict)      # ведомая книга → строка-драйвер (при k6_line)
    hist_k6_line: Mapping[str, Mapping[int, float]] = field(default_factory=dict)
    #                                            ряд → история x = −3…0: D^ℓ_x (концы фактов), Ψ^ℓ_x = D^ℓ_x / D^ℓ_0
    # девятый проход ядра (ключи необязательны; нет ключа — прежняя строка кода)
    phi_share: Mapping[str, float] = field(default_factory=dict)
    #                                            Р11-1: книга → доля сжатия спреда к опоре между мирами (только ≠ 0,
    #                                            `model.nii.phi_shares`); пусто — долей нет
    funds_words: tuple[str, ...] | None = None   # Р11-2 (volumes.funds_scope: clients при активном К6): книги слова
    #                                            «средства клиентов» механики — `model.book.client_books`; None — все
    #                                            книги средств (прежняя строка)
    wh_corp: tuple[str, ...] | None = None     # Р11-2: книги средств ЮЛ в базе структурного опта и в слове funds —
    #                                            corp_funds без ведомых книг К6; None — все corp_funds (прежняя строка)
    nci_q: Mapping[tuple[int, int], float] | None = None
    #                                            Р11-3 (pnl.nci_real): (год, квартал) → НДУ квартала в ценах якоря
    #                                            (год / 4; в клетке × индекс цен мира); None — доля `nci_share` (прежняя
    #                                            строка). При ключе `nci_share` = 0: читатели доли считают без неё


def _series(traj: Any, tl: Timeline) -> tuple[float, ...]:
    t = Trajectory(traj)
    return tuple(t.value(*parse_period(tl.period(q))) for q in range(tl.Q + 1))


def _drift(value: Any, years: range) -> tuple[float, dict[str, dict[int, float]] | None]:
    """Премия роста к сектору (М§4.3): число — одна на все книги (прежняя форма); словарь — траектория на
    ключ набора, значение года — `year_value`."""
    if isinstance(value, Mapping):
        return 0.0, {str(k): {y: Trajectory(v).year_value(y) for y in years} for k, v in value.items()}
    return float(value), None


def _drift_quarters(value: Any) -> dict[str, dict[tuple[int, int], float]]:
    """Премия роста средств клиентов, заданная ключом квартала или полугодия (М§4.3): сегмент → (год, номер
    квартала) → значение траектории в этом квартале (правило М§0.4: ключ квартала, затем ключ полугодия).
    Кварталы без своего ключа и траектории без таких ключей сюда не входят — их премию задаёт значение года,
    как у образца: число и словарь с ключами лет читаются прежней строкой."""
    out: dict[str, dict[tuple[int, int], float]] = {}
    if not isinstance(value, Mapping):
        return out
    for name, traj in value.items():
        t = Trajectory(traj)
        keyed = set(t.quarters) | {(y, n) for y, h in t.halves for n in ((1, 2) if h == 1 else (3, 4))}
        if keyed:
            out[str(name)] = {(y, n): t.value(y, n) for y, n in sorted(keyed)}
    return out


LINK_BASES = ("loans", "funds", "iea")       # volumes.link_base — он же узел конца квартала в balance.history


def _volume_history(base: str, hist_bal: Mapping[int, Mapping[str, float]], anchor_end: float,
                    tl: Timeline) -> dict[int, float]:
    """A_x, x = −3…0: средний остаток базы объёма за квартал до сетки — полусумма концов кварталов фактов
    (`balance.history`; конец якоря — остатки якоря). Нет конца — FactsError (М§4.7)."""
    ends = {0: anchor_end}
    for x in range(-4, 0):
        value = hist_bal.get(x, {}).get(base)
        if value is None:
            raise FactsError(f"balance.history: нет {base} на конец {tl.period(x)} — рост объёма г/г не определён "
                             "(связь с объёмом, М§4.7)")
        ends[x] = value
    return {x: (ends[x - 1] + ends[x]) / 2 for x in range(-3, 1)}


BOOK_RELATIVE = "credit.book_relative"


def book_relative(book: "Book", roles: BookRoles, af: AnchorFacts) -> dict[str, float] | None:
    """Множители CoR кредитных книг r̂_b (М§4.6, ключ `credit.book_relative`): сырые r_b книги, нормированные на
    составе якоря — r̂_b = r_b / Σ w_b,0 r_b, w_b,0 = (E_b,0 − FV_b,0) / Σ (кредиты по амортизированной стоимости; FV —
    только у книги с долей по справедливой стоимости). На составе якоря общая CoR клетки равна пути. Нормировка — в
    каждом прогоне по сырым значениям прогона. Нет ключа или он выключен — None (сегменты или общая CoR)."""
    spec = book.opt(BOOK_RELATIVE)
    if spec is None or spec.get("enabled") is not True:
        return None
    if book.get("credit.segment_relative.enabled"):
        raise BookError(f"{BOOK_RELATIVE}.enabled: множители по книгам и множители сегментов включены вместе (М§4.6)")
    raw = {str(b): float(v) for b, v in spec["by_book"].items()}
    if set(raw) != set(roles.loans):
        raise BookError(f"{BOOK_RELATIVE}.by_book: книги {', '.join(sorted(raw))} — не кредитные книги "
                        f"{', '.join(roles.loans)} (М§4.6)")
    bad = [b for b, r in raw.items() if not r > 0]
    if bad:
        raise BookError(f"{BOOK_RELATIVE}.by_book: множитель не больше нуля у {', '.join(bad)} (М§4.6)")
    ac = {b: af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0) for b in roles.loans}
    total = sum(ac.values())
    norm = sum(ac[b] / total * raw[b] for b in roles.loans)
    return {b: raw[b] / norm for b in roles.loans}


OPEX_WEIGHTS = "opex.volume_weights"
BUYBACK = "dividends.buyback"
WH_STRUCTURAL = "volumes.wholesale_structural_to_funds"
STATIONARY_RATES = "valuation.terminal.stationary_rates"


def wholesale_structural(book: "Book") -> float | None:
    """Структурная доля опта к средствам клиентов s (К3, М§4.10): сверх s × средства опт идёт по нужде — добирается
    при нехватке ликвидности и гасится при её избытке над минимумом. Это та же формула шага с базой опта s вместо доли
    якоря (тождество методики): ключ разводит факт якоря (доля `volumes.wholesale_to_funds` — печать) и суждение
    (структурная часть — центр и ось). Нет ключа — None (база опта — доля якоря); s < 0 или больше доли якоря —
    отказ: структурная часть больше фактического опта дала бы скачок ликвидности в первом квартале."""
    value = book.opt(WH_STRUCTURAL)
    if value is None:
        return None
    s, anchor = float(value), float(book.get("volumes.wholesale_to_funds"))
    if not 0.0 <= s <= anchor:
        raise BookError(f"{WH_STRUCTURAL} = {s:g}: структурная доля опта — от нуля до доли опта якоря "
                        f"volumes.wholesale_to_funds = {anchor:g} (М§4.10)")
    return s


ALLOWANCE_BY_BOOK = "credit.allowance_by_book"
RESID_MAX = 0.05                             # |R_0| / AL_0 — сверх этого факты по книгам не сходятся с резервом якоря


def allowance_by_book(book: "Book", facts: "Facts", roles: BookRoles, af: AnchorFacts
                      ) -> tuple[dict[str, float], float, float] | None:
    """Резерв по книгам (К7, М§4.6, ключ `credit.allowance_by_book`): покрытие книги якоря cov_b = A_b,0 / (E_b,0 −
    FV_b,0) по фактам `balance.allowance_books.<b>`, остаток резерва якоря вне книг R_0 = AL_0 − Σ A_b,0 и кредиты по
    амортизированной стоимости якоря (масштаб роста R_0). Запас резерва идёт за составом портфеля, как поток резервов
    по книгам (М7). Нет ключа или он выключен — None (доля якоря). Отказы фактов: резерв книги не меньше её остатка по
    АС; |R_0| больше 5 % резерва якоря — факты по продуктам не сходятся с резервом якоря."""
    spec = book.opt(ALLOWANCE_BY_BOOK)
    if spec is None or spec.get("enabled") is not True:
        return None
    from model.book import allowance_books
    raw = allowance_books(facts, roles.loans)
    cov = {}
    for b in roles.loans:
        ac = af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0)
        if not raw[b] < ac:
            raise FactsError(f"balance.allowance_books.{b} = {raw[b]:g}: резерв книги не меньше её остатка по "
                             f"амортизированной стоимости {ac:g} (М§4.6)")
        cov[b] = raw[b] / ac
    resid = af.allowance - sum(raw.values())
    if abs(resid) > RESID_MAX * af.allowance:
        raise FactsError(f"balance.allowance_books: сумма резервов по книгам {sum(raw.values()):g} расходится с "
                         f"резервом якоря {af.allowance:g} больше чем на 5 % (остаток вне книг {resid:g}, М§4.6)")
    return cov, resid, sum(af.balances[b] for b in roles.loans) - af.fv_loans


def allowance_of(p: "Prepared", E: Mapping[str, float], fv: float, loans_ac: float) -> float:
    """Резерв на конец квартала по книгам (К7, М§4.6): AL = Σ_b cov_b (E_b − FV_b) + R_0 × кредиты АС / кредиты АС
    якоря; FV — только у книги с долей по справедливой стоимости."""
    total = sum([cov * (E[b] - (fv if b == p.fv_book else 0.0)) for b, cov in p.allow_cov.items()])
    return total + p.allow_resid * loans_ac / p.loans_ac0


LINE_KINDS = LINK_BASES + ("nominal",)       # базы строки словом (К2); словарь {книга → вес} — вид books
BALANCING = (SECURITIES, LIQUIDITY, WHOLESALE)


def line_base(spec: Any, key: str, *, books: Mapping[str, Any], roles: BookRoles, af: AnchorFacts,
              hist_bal: Mapping[int, Mapping[str, float]], hist_books: Mapping[int, Mapping[str, float]],
              tl: Timeline, history: bool, funds: tuple[str, ...] | None = None) -> LineBase:
    """База строки по спецификации книги `key` (М§4.7, К2): слово loans | funds | iea | nominal или словарь {книга ЧПД →
    вес ≥ 0}. Уровень якоря D_0 — остатки якоря (у номинала — 1). `history` — нужны средние остатки x = −3…0 (связь
    строки не ноль): loans, funds, iea — по концам кварталов `balance.history` (как база link_base), книги — по
    `balance.history.<период>.books` с весами, нормированными на квартале якоря (как веса М13), номинал — 1. `funds` —
    книги слова funds (`model.book.funds_books`, Р11-2; None — `roles.funds`, прежняя строка). Отказы:
    незнакомое слово, книга не из книг ЧПД, все веса нулевые (BookError); нет конца квартала — FactsError."""
    if isinstance(spec, Mapping):
        raw = {str(b): float(w) for b, w in spec.items()}
        unknown = sorted(set(raw) - set(books))
        if unknown:
            raise BookError(f"{key}: книги {', '.join(unknown)} — не книги nii.books (М§4.7)")
        used = {b: raw[b] for b in books if raw.get(b, 0.0) > 0}
        if not used:
            raise BookError(f"{key}: все веса нулевые — базы строки нет (М§4.7)")
        hist = None
        if history:
            used, hist = _weighted_history(used, books, hist_books, af.balances, tl, key)
        return LineBase(kind="books", weights=used, end0=sum(w * af.balances[b] for b, w in used.items()), hist=hist,
                        balancing=any(b in BALANCING for b in used))
    kind = str(spec)
    if kind not in LINE_KINDS:
        raise BookError(f"{key} = {kind!r}: база строки — {', '.join(LINE_KINDS)} или словарь весов книг (М§4.7)")
    if kind == "nominal":
        return LineBase(kind=kind, end0=1.0, hist={x: 1.0 for x in range(-3, 1)} if history else None)
    end0 = {"loans": sum(af.balances[b] for b in roles.loans),
            "funds": sum(af.balances[b] for b in (roles.funds if funds is None else funds)),
            "iea": sum(af.balances[b] for b in roles.assets)}[kind]
    return LineBase(kind=kind, end0=end0, hist=_volume_history(kind, hist_bal, end0, tl) if history else None,
                    balancing=kind == "iea")


FEES_BASE, INS_BASE, LINE_SHARES = "fees.volume_base", "other.insurance_volume_base", "opex.line_shares"
# корень κ номинальной части франшизы строки (Р8-6, М§4.7): {fees, insurance → траектория}; читается при доле строки > 0
LINE_SHARE_ROOTS = "opex.line_share_roots"
# форма корня строк комиссий и страхования (Р5-6, М§4.7): multiplicative — (1 + рост базы)(1 + корень), как у расходов;
# нет ключа или additive — прежняя сумма 1 + рост базы + корень
LINE_ROOT_FORM, ROOT_MULTIPLICATIVE = "volumes.line_root_form", "multiplicative"
MIX = "mix"                                  # смесь баз строки (К2б, М§4.7): доли строки на якоре по базам-компонентам
MIX_TOL = 1e-9                               # допуск суммы долей смеси


def compile_mix(mix: Mapping[str, Any], key: str, *, books: Mapping[str, Any], roles: BookRoles,
                balances: Mapping[str, float], funds: tuple[str, ...] | None = None) -> dict[str, float]:
    """Смесь баз строки → словарь весов книг (К2б, М§4.7): ω_b = Σ_k s_k ω^k_b / D^k_0, D^k_0 = Σ_b ω^k_b E_b,0 — остатки
    якоря на конец квартала якоря; компонента — слово loans | funds | iea (веса 1 на кредитных книгах, на средствах
    клиентов — книги `funds`: при `volumes.funds_scope: clients` без книг К6 (Р11-2), иначе с ними — `roles.funds`, на
    процентных активах) или веса книг ЧПД. На концах кварталов D_q / D_0 = Σ_k s_k
    D^k_q / D^k_0 точно: доля s_k строки якоря идёт за базой k. Масштаб весов — к наибольшему весу 1 (рост от него не
    зависит), порядок — nii.books. Отказы: пустая смесь, |Σ s − 1| > 1e-9, номинал (не остаток книг: смесь с ним
    нелинейна — часть строки за зарплатами задаёт связь строки < 1), чужая книга, все веса нулевые, D^k_0 ≤ 0."""
    if not mix:
        raise BookError(f"{key}: пустая смесь — базы строки нет (К2б, М§4.7)")
    total = sum(float(comp["share"]) for comp in mix.values())
    if abs(total - 1.0) > MIX_TOL:
        raise BookError(f"{key}: сумма долей смеси {total:.12g} — не единица (К2б, М§4.7)")
    words = {"loans": roles.loans, "funds": roles.funds if funds is None else funds, "iea": roles.assets}
    out: dict[str, float] = {}
    for name, comp in mix.items():
        where, base, share = f"{key}.{name}", comp["base"], float(comp["share"])
        if isinstance(base, Mapping):
            raw = {str(b): float(w) for b, w in base.items()}
            unknown = sorted(set(raw) - set(books))
            if unknown:
                raise BookError(f"{where}.base: книги {', '.join(unknown)} — не книги nii.books (К2б, М§4.7)")
            weights = {b: raw[b] for b in books if raw.get(b, 0.0) > 0}
            if not weights:
                raise BookError(f"{where}.base: все веса нулевые — базы компоненты нет (К2б, М§4.7)")
        elif str(base) in words:
            weights = {b: 1.0 for b in words[str(base)]}
        else:
            raise BookError(f"{where}.base = {base!r}: компонента смеси — loans, funds, iea или веса книг; номинал не "
                            "остаток книг — смесь с ним нелинейна (часть строки за зарплатами — связью строки < 1) "
                            "(К2б, М§4.7)")
        d0 = sum(w * balances[b] for b, w in weights.items())
        if not d0 > 0:
            raise BookError(f"{where}: уровень компоненты на якоре {d0:g} не больше нуля (К2б, М§4.7)")
        for b, w in weights.items():
            out[b] = out.get(b, 0.0) + share * w / d0
    top = max(out.values())
    return {b: out[b] / top for b in books if out.get(b, 0.0) > 0}


def resolve_line_base(book: "Book", key: str, *, roles: BookRoles, balances: Mapping[str, float]) -> Any:
    """База строки `key` (`fees.volume_base` или `other.insurance_volume_base`; М§4.7, К2, К2б) — одна функция у строки
    ядра, RWA гарантий (К5), книг-обязательств за драйвером строки (К6) и листа вывода: свой ключ строки, без него —
    `volumes.link_base` (без ключа — кредиты). Слово и словарь весов — как в книге; смесь {mix: …} — словарь весов книг
    (`compile_mix`, остатки якоря `balances`; слово funds компоненты — `funds_books`, Р11-2)."""
    spec = book.opt(key, book.opt("volumes.link_base", LINK_BASES[0]))
    if isinstance(spec, Mapping) and MIX in spec:
        return compile_mix(spec[MIX], f"{key}.{MIX}", books=book.get("nii.books"), roles=roles, balances=balances,
                           funds=funds_books(roles, book))
    return spec


def fees_base_spec(book: "Book", roles: BookRoles, balances: Mapping[str, float]) -> Any:
    """База строки комиссий (М§4.7): свой ключ `fees.volume_base` (К2; смесь — К2б), без него — `volumes.link_base`
    (без ключа — кредиты)."""
    return resolve_line_base(book, FEES_BASE, roles=roles, balances=balances)


def ins_base_spec(book: "Book", roles: BookRoles, balances: Mapping[str, float]) -> Any:
    """База строки страхования (М§4.7): свой ключ `other.insurance_volume_base` (К2; смесь — К2б), без него —
    `volumes.link_base` (без ключа — кредиты)."""
    return resolve_line_base(book, INS_BASE, roles=roles, balances=balances)


LIABILITY_DRIVERS = "volumes.liability_drivers"
NCI_REAL = "pnl.nci_real"                    # Р11-3: неконтролирующие в реальных рублях (проход ядра 9, М§4.8)
LIABILITY_DRIVER_ROOTS = "volumes.liability_driver_roots"   # Р9-1: корень ρ номинальной части книг К6 по строке
CASH_ASSETS = "volumes.cash_assets"


def cash_assets(book: "Book", facts: "Facts", *, roles: BookRoles, af: AnchorFacts, tl: Timeline, oa_fixed: float
                ) -> Cash | None:
    """Неработающие деньги со своим драйвером (К8, М§4.3, ключ `volumes.cash_assets` {amount, driver}): деньги якоря C_0
    (anchor — узел фактов balance.nonworking_money.total), драйвер — средства клиентов (`funds`: с ведомыми книгами К6),
    кредиты (`loans`) или веса небалансирующих книг; c = C_0 / D_0 на остатках якоря; ρ′ = ρ − C_0 / L_0 — растущие
    прочие активы без денег на рубль кредита (ρ = `volumes.other_assets_to_loans`, его смысл не меняется). Отказы:
    драйвер с балансирующей книгой или процентные активы (круг: ликвидность зависит от прочих активов), номинал; D_0 ≤ 0;
    денег больше растущей части прочих активов якоря; ρ′ < 0. Нет ключа — None (прежняя строка: деньги в доле к
    кредитам)."""
    spec = book.opt(CASH_ASSETS)
    if spec is None:
        return None
    key = f"{CASH_ASSETS}.driver"
    amount = spec["amount"]
    c0 = facts.need("balance", CASH_NODE) if amount == "anchor" else float(amount)
    lb = line_base(spec["driver"], key, books=book.get("nii.books"), roles=roles, af=af, hist_bal={}, hist_books={},
                   tl=tl, history=False, funds=funds_books(roles, book))     # Р11-2: драйвер словом funds
    if lb.kind in ("iea", "nominal") or lb.balancing:
        raise BookError(f"{key}: драйвер денег читает баланс (балансирующие книги или процентные активы) или номинал — "
                        "круг: ликвидность зависит от прочих активов (К8, М§4.3)")
    if not lb.end0 > 0:
        raise BookError(f"{key}: уровень драйвера якоря {lb.end0:g} не больше нуля (К8, М§4.3)")
    l0 = sum(af.balances[b] for b in roles.loans)
    grow = af.other_assets - oa_fixed
    if c0 > grow:
        raise BookError(f"{CASH_ASSETS}.amount = {c0:g}: денег больше растущей части прочих активов якоря {grow:g} "
                        "(К8, М§4.3)")
    rho = float(book.get("volumes.other_assets_to_loans")) - c0 / l0
    if rho < 0:
        raise BookError(f"{CASH_ASSETS}: ρ′ = volumes.other_assets_to_loans − C_0 / L_0 = {rho:g} меньше нуля — денег "
                        "больше растущих прочих активов книги (К8, М§4.3)")
    raw = spec.get("share")
    if raw is None or raw == "anchor":      # доля якоря: прежняя строка (Р6-1: share: anchor — та же ветвь, бит в бит)
        return Cash(c0=c0, base=lb, share=c0 / lb.end0, rho=rho)
    return cash_share_path(spec, float(raw), facts, c0=c0, lb=lb, l0=l0, tl=tl,
                           rho_book=float(book.get("volumes.other_assets_to_loans")), rho=rho)


def cash_share_path(spec: Mapping[str, Any], s_star: float, facts: "Facts", *, c0: float, lb: LineBase, l0: float,
                    tl: Timeline, rho_book: float, rho: float) -> Cash:
    """Доля неработающих денег книги (Р6-1, проход ядра 5, М§4.3): s* = `share` — доля денег без ФОР к уровню драйвера
    на конец квартала; ФОР — доля якоря r = R_0 / D_0 (`reserves`; anchor — узел фактов
    balance.nonworking_money.mandatory_reserves); путь s_q = s_0 + (s* − s_0) q / q_f до квартала `share_from` (q_f),
    дальше s*; s_0 = (C_0 − R_0) / D_0; c_q = s_q + r, c_0 = C_0 / D_0 — факт якоря; ρ′_q = ρ − c_q D_0 / L_0; δ_q =
    (c_q − c_0) D_0 / L_0; θ = `displaced_weight` (нет поля или 1 — слагаемого RWA нет). Отказы: нет ФОР или квартала;
    ФОР больше денег якоря; квартал не после якоря или позже конца сетки; ρ′_q < 0 (денег книги больше растущей части
    прочих активов якоря)."""
    res, frm = spec.get("reserves"), spec.get("share_from")
    if res is None or frm is None:
        raise BookError(f"{CASH_ASSETS}: доля денег книги share = {s_star:g} без ФОР якоря (reserves) или квартала доли "
                        "книги (share_from) (Р6-1, М§4.3)")
    r0 = facts.need("balance", RESERVES_NODE) if res == "anchor" else float(res)
    if r0 > c0:
        raise BookError(f"{CASH_ASSETS}.reserves = {r0:g}: ФОР больше денег якоря C_0 = {c0:g} (Р6-1, М§4.3)")
    q_f = tl.index(str(frm))
    if not 1 <= q_f <= tl.Q:
        raise BookError(f"{CASH_ASSETS}.share_from = {frm}: квартал доли книги — после якоря {tl.period(0)} и не позже "
                        f"{tl.period(tl.Q)} (Р6-1, М§4.3)")
    d0 = lb.end0
    s0, r, c_0 = (c0 - r0) / d0, r0 / d0, c0 / d0
    s_q = [s_star if q >= q_f else s0 + (s_star - s0) * q / q_f for q in range(1, tl.Q + 1)]
    share_q = (c_0,) + tuple(s + r for s in s_q)
    rho_q = (rho,) + tuple(rho_book - c * d0 / l0 for c in share_q[1:])
    if min(rho_q) < 0:
        q = rho_q.index(min(rho_q))
        raise BookError(f"{CASH_ASSETS}.share = {s_star:g}: ρ′ = ρ − (s* + R_0 / D_0) D_0 / L_0 = {rho_book:g} − "
                        f"{share_q[q]:g} × {d0:g} / {l0:g} = {rho_q[q]:g} меньше нуля — денег книги больше растущей части "
                        "прочих активов якоря (Р6-1, М§4.3)")
    th = spec.get("displaced_weight")
    return Cash(c0=c0, base=lb, share=c_0, rho=rho, share_q=share_q, rho_q=rho_q, reserves=r,
                delta_q=tuple((c - c_0) * d0 / l0 for c in share_q),
                theta=None if th is None or float(th) == 1.0 else float(th))


def displaced_shift(cash: Cash, rw: RwaWeights) -> Cash:
    """Слагаемое RWA вытесненной части прочих активов (Р6-1, М§4.11) на рубль кредита: (1 − θ)(ω′_oa − ω_c) δ_q — на
    плотностях после выреза денег своей книги (ω′_oa — вырез на раскладке факта, `carve_cash`). θ = 0 — вытесненная
    часть весит как деньги, θ = 1 (нет слагаемого) — как растущие прочие без денег."""
    k = (1.0 - cash.theta) * (rw.other_assets_cash - rw.cash)
    return replace(cash, shift_q=tuple(k * d for d in cash.delta_q))


MIN_DPS = "dividends.min_dps"


def min_dps_years(book: "Book", tl: Timeline, calendar: QuarterCalendar | None, growth: GrowthRule | None
                  ) -> dict[int, float] | None:
    """Жетон DPS по годам прибыли открытых кварталов (К1, М§4.13.2 п. 2а, ключ `dividends.min_dps` — траектория, ₽ на
    акцию за год прибыли). Читается только в машине роста: квартальный календарь и включённое ограничение роста; иначе —
    ключ неактивного режима (None, прежняя ветвь). Значение меньше нуля — отказ схемы."""
    raw = book.opt(MIN_DPS)
    if raw is None or calendar is None or growth is None:
        return None
    t = Trajectory(raw)
    return {y: t.year_value(y) for y in range(tl.year(calendar.p_last + 1), tl.last_year + 1)}


def liability_drivers(book: "Book", links: Mapping[str, float], *, roles: BookRoles, **kw: Any
                      ) -> dict[str, tuple[LineBase, float]] | None:
    """Книги-обязательства за драйвером строки (К6, М§4.3, ключ `volumes.liability_drivers` {книга → insurance | fees}):
    книга растёт за «объёмной частью» строки — зарплатами и долей связи за базой строки (без корня уровня). База
    строки — свой ключ К2 или `volumes.link_base` (без ключа — кредиты), связь — связь строки. Книга остаётся в
    средствах клиентов для сумм, но не растёт с сектором средств бизнеса. Отказы: книга — не небалансирующий пассив
    вне пары средств физлиц; база драйвера — процентные активы, средства клиентов или веса на балансирующих книгах
    либо на ведомых книгах (круг: книга зависела бы от баланса или от себя). Нет ключа или пусто — None."""
    spec = book.opt(LIABILITY_DRIVERS)
    if not spec:
        return None
    out = {}
    for b, line in spec.items():
        b = str(b)
        if b not in roles.corp_funds:
            raise BookError(f"{LIABILITY_DRIVERS}.{b}: ведомая книга — небалансирующий пассив вне пары средств физлиц "
                            f"({', '.join(roles.corp_funds)}; М§4.3)")
        key = FEES_BASE if line == "fees" else INS_BASE
        resolved = resolve_line_base(book, key, roles=roles, balances=kw["af"].balances)
        lb = line_base(resolved, key, roles=roles, **kw)
        circle = lb.kind == "books" and bool(set(lb.weights) & set(map(str, spec)))
        if lb.kind in ("iea", "funds") or lb.balancing or circle:
            raise BookError(f"{LIABILITY_DRIVERS}.{b} = {line}: база строки-драйвера ({key}) читает баланс или ведомую "
                            "книгу — круг (М§4.3)")
        out[b] = (lb, float(links["fees"] if line == "fees" else links["ins"]))
    return out


def driver_roots(book: "Book", driven: Mapping[str, tuple[LineBase, float]] | None, tl: Timeline
                 ) -> dict[str, tuple[str, tuple[float, ...]]] | None:
    """Корень номинальной части книг К6 (Р9-1, проход ядра 7, М§4.3; ключ `volumes.liability_driver_roots` {fees,
    insurance → траектория ρ}, необязательный). Ключ — по СТРОКЕ-драйверу (ρ — свойство базы строки: все книги строки
    несут один корень, книга, сменившая строку-драйвер, чужого корня не берёт). Книга b строки ℓ растёт E_b,q = E_b,q−1
    (1 + wage_W,q)^((1 − λ)/4) (D_q / D_q−1)^λ (1 + ρ_q)^(1 − λ). Ключ читается для ведомой книги, когда К6 активен и её
    строка-драйвер есть в ключе; иначе — ключ неактивного режима, не отказ (вариант, снявший К6, считает прежней
    строкой). Возвращает {ведомая книга → (строка, ρ_q по q = 0…Q)} или None — ключа нет, пустой словарь, К6 нет, ни
    одна строка ключа книгой не ведёт."""
    roots = book.opt(LIABILITY_DRIVER_ROOTS)
    if not roots or not driven:
        return None
    spec = book.opt(LIABILITY_DRIVERS) or {}
    out = {str(b): (str(line), _series(roots[line], tl)) for b, line in spec.items()
           if line in roots and str(b) in driven}
    return out or None


def form_line(book: "Book") -> bool:
    """Ключ формы связи λ (Р10-5, проход ядра 8, М§4.7): `volumes.line_link_form: line` — франшиза строки и книги К6
    формой строки; нет ключа или mixed — прежние формы."""
    return book.opt(LINE_LINK_FORM, FORM_MIXED) == FORM_LINE


def k6_line(book: "Book", driven: Mapping[str, tuple[LineBase, float]] | None, tl: Timeline, *,
            hist_bal: Mapping[int, Mapping[str, float]], hist_books: Mapping[int, Mapping[str, float]]
            ) -> tuple[dict[str, tuple[float, tuple[float, ...], LineBase]] | None, dict[str, str],
                       dict[str, dict[int, float]]]:
    """Книги К6 формой строки (Р10-5, проход ядра 8, М§4.3; ключ `volumes.line_link_form: line`). Индекс строки-драйвера
    на концах кварталов: Ψ^ℓ_q = Ψ^ℓ_(q−4) × g(D^ℓ_q / D^ℓ_(q−4), w_q, λ_ℓ, ρ^ℓ_q) (`link_growth`, форма корня — как у
    строки), Ψ^ℓ_x = D^ℓ_x / D^ℓ_0 при x = −3…0; ведомая книга b строки ℓ — E_b,q = E_b,0 × Ψ^ℓ_q. D_x — уровень базы
    строки на концах фактов: кредиты (средства) — `balance.history`, веса книг — Σ ω E_b,x по
    `balance.history.<период>.books` с весами `base_end`, номинал — 1. ρ — ключ `volumes.liability_driver_roots` строки
    (нет строки в ключе — нули). Ключ читается при активном К6; иначе (нет ключа, mixed, К6 нет) — ключ неактивного режима,
    не отказ. Нет конца истории — FactsError. → ({строка: (λ, ρ_q по q = 0…Q, база)} | None, {книга: строка}, {ряд:
    история x = −3…0} — ряды D^ℓ (лаг 4) и Ψ^ℓ)."""
    if not driven or not form_line(book):
        return None, {}, {}
    spec = book.opt(LIABILITY_DRIVERS) or {}
    roots = book.opt(LIABILITY_DRIVER_ROOTS) or {}
    out: dict[str, tuple[float, tuple[float, ...], LineBase]] = {}
    of_book: dict[str, str] = {}
    hist: dict[str, dict[int, float]] = {}
    for b, (lb, lam) in driven.items():
        line = str(spec[b])
        of_book[b] = line
        if line in out:
            continue
        rho = _series(roots[line], tl) if line in roots else tuple(0.0 for _ in range(tl.Q + 1))
        ends = {0: lb.end0}
        for x in range(-3, 0):
            if lb.kind == "nominal":
                ends[x] = 1.0
            elif lb.kind == "books":
                row = hist_books.get(x, {})
                missing = [k for k in lb.weights if row.get(k) is None]
                if missing:
                    raise FactsError(f"balance.history: нет остатков книг {', '.join(missing)} на конец {tl.period(x)} — "
                                     "индекс книг К6 формой строки г/г не определён (Р10-5, М§4.3)")
                ends[x] = sum([w * row[k] for k, w in lb.weights.items()])
            else:
                value = hist_bal.get(x, {}).get(lb.kind)
                if value is None:
                    raise FactsError(f"balance.history: нет {lb.kind} на конец {tl.period(x)} — индекс книг К6 формой "
                                     "строки г/г не определён (Р10-5, М§4.3)")
                ends[x] = value
        out[line] = (float(lam), rho, lb)
        hist[LAG_END_FLOWS[line]] = dict(ends)
        hist[PSI_FLOWS[line]] = {x: ends[x] / ends[0] for x in range(-3, 1)}
    return out, of_book, hist


def line_bases(book: "Book", links: Mapping[str, float], *, hist_vol: Mapping[int, float],
               hist_vol_opex: Mapping[int, float], opex_w: Mapping[str, float] | None, **kw: Any) -> dict[str, Any]:
    """Базы строк по своим ключам и смесь базы расходов (К2, М§4.7) — поля подготовки. Свой ключ базы читается, когда
    связь строки не ноль или его читает доля расходов; доли `opex.line_shares` — при связи расходов. Смесь:
    A^C_x = (1 − Σ s) B^C_x + Σ s_ℓ B^C_0 A^ℓ_x / A^ℓ_0 (B^C — база М13 или link_base; A^ℓ — база строки по своему
    ключу или link_base) — на якоре ступени нет. Σ долей ≥ 1 — отказ. Нет ключей — пусто (прежняя ветвь)."""
    raw = book.opt(LINE_SHARES) if links["opex"] else None
    shares = {k: float(raw[k]) for k in ("fees", "insurance") if raw and float(raw.get(k, 0.0)) > 0} or None
    if shares and sum(shares.values()) >= 1:
        raise BookError(f"{LINE_SHARES}: сумма долей {sum(shares.values()):g} не меньше единицы (М§4.7)")
    out: dict[str, Any] = {}
    fees_spec, ins_spec = book.opt(FEES_BASE), book.opt(INS_BASE)
    if isinstance(fees_spec, Mapping) and MIX in fees_spec:     # смесь баз — словарь весов книг (К2б)
        fees_spec = resolve_line_base(book, FEES_BASE, roles=kw["roles"], balances=kw["af"].balances)
    if isinstance(ins_spec, Mapping) and MIX in ins_spec:
        ins_spec = resolve_line_base(book, INS_BASE, roles=kw["roles"], balances=kw["af"].balances)
    words = funds_books(kw["roles"], book)                  # Р11-2: слово funds базы строки
    if fees_spec is not None and (links["fees"] or (shares and "fees" in shares)):
        out["fees_line"] = line_base(fees_spec, FEES_BASE, history=True, funds=words, **kw)
    if ins_spec is not None and (links["ins"] or (shares and "insurance" in shares)):
        out["ins_line"] = line_base(ins_spec, INS_BASE, history=True, funds=words, **kw)
    flows = tuple(f for f, k in (("vol_fees", "fees_line"), ("vol_ins", "ins_line")) if k in out)
    if shares:
        b_hist = hist_vol_opex if opex_w is not None else hist_vol
        srcs = {"fees": ("vol_fees", out["fees_line"].hist) if "fees_line" in out else ("vol", hist_vol),
                "insurance": ("vol_ins", out["ins_line"].hist) if "ins_line" in out else ("vol", hist_vol)}
        keep, b0 = 1 - sum(shares.values()), b_hist[0]
        mix = {}
        for x in range(-3, 1):
            a_c = keep * b_hist[x]
            for line, share in shares.items():
                a_c += share * b0 * srcs[line][1][x] / srcs[line][1][0]
            mix[x] = a_c
        out.update(line_shares=shares, hist_vol_mix=mix, mix_keep=keep, mix_b0=b0,
                   mix_src={line: (srcs[line][0], srcs[line][1][0]) for line in shares})
        flows += ("vol_mix",)
        nominal, hist_nom = share_nominal(book, links, shares, {line: srcs[line][1] for line in shares}, kw["tl"])
        if nominal is not None:                 # Р8-6: франшиза строки за связью строки (М§4.7)
            out.update(share_nominal=nominal, hist_share_nominal=hist_nom)
            flows += tuple(nom[2] for nom in nominal.values())
    if flows:
        out["line_flows"] = flows
    if any(out[k].balancing for k in ("fees_line", "ins_line") if k in out):
        out["memo_off"] = True
    return out


def share_nominal(book: "Book", links: Mapping[str, float], shares: Mapping[str, float],
                  hist: Mapping[str, Mapping[int, float]], tl: Timeline
                  ) -> tuple[dict[str, tuple[float, tuple[float, ...], str]] | None, dict[str, dict[int, float]]]:
    """Франшиза строки за связью строки (Р8-6, проход ядра 6, М§4.7; ключ `opex.line_share_roots` {fees, insurance →
    траектория κ}, необязательный). Доля s_ℓ франшизы строки ℓ в смеси базы расходов идёт той же формой, что строка:
    Φ^ℓ_q = λ_ℓ A^ℓ_q / A^ℓ_0 + (1 − λ_ℓ) H^ℓ_q, H^ℓ_q = H^ℓ_(q−4) (1 + wage_W,q)(1 + κ_q), H^ℓ_x = A^ℓ_x / A^ℓ_0 при
    x ≤ 0 (история смеси — прежняя). λ_ℓ — связь самой строки (не новый ключ), κ — корень номинальной части, общий для
    миров (выводит лист). Ключ строки читается, когда читаются доли (связь расходов > 0) и доля строки > 0; иначе — ключ
    неактивного режима (не отказ). Возвращает ({строка: (λ_ℓ, κ_q по q = 0…Q, имя ряда H^ℓ)} или None — ключа нет или
    он не читается ни одной строкой, {имя ряда: H^ℓ_x, x = −3…0}); `hist` — история базы строки A^ℓ_x, x ≤ 0.

    При `volumes.line_link_form: line` (Р10-5, проход ядра 8) франшиза строки идёт формой строки — ряд Φ^ℓ (vol_phi_<ℓ>)
    вместо H^ℓ: Φ^ℓ_q = Φ^ℓ_(q−4) × g(A^ℓ_q / A^ℓ_(q−4), w_q, λ_ℓ, κ_q) (`link_growth`), Φ^ℓ_x = A^ℓ_x / A^ℓ_0 (та же
    история); смесь — A^C_q = (1 − Σ s) B^C_q + Σ s_ℓ B^C_0 Φ^ℓ_q."""
    roots = book.opt(LINE_SHARE_ROOTS)
    if not roots:
        return None, {}
    lam_of = {"fees": float(links["fees"]), "insurance": float(links["ins"])}
    nominal: dict[str, tuple[float, tuple[float, ...], str]] = {}
    hist_nom: dict[str, dict[int, float]] = {}
    names = PHI_FLOWS if form_line(book) else NOM_FLOWS    # Р10-5: ряд Φ^ℓ формы строки вместо H^ℓ
    for line in shares:
        if line not in roots:
            continue
        name, a = names[line], hist[line]
        nominal[line] = (lam_of[line], _series(roots[line], tl), name)
        hist_nom[name] = {x: a[x] / a[0] for x in range(-3, 1)}
    return (nominal or None), hist_nom


GUARANTEE_LEVEL_DRIVERS = ("fees_base", "fees_component")   # драйверы К5 — уровень базы на конец квартала (М§4.11)


def guarantee_component(book: "Book", spec: Mapping[str, Any]) -> tuple[str, Any]:
    """База компоненты смеси базы комиссий — драйвер RWA гарантий `fees_component` (Р5-5, М§4.11): имя
    `capital.rwa.guarantees.component` и база компоненты `fees.volume_base.mix.<имя>.base` КАК ЗАПИСАНА (слово loans |
    funds | iea или веса книг) — без доли s_c и без нормировки смеси: D^G_q = Σ_b ω^c_b E_b,q. Поле читается только
    при этом драйвере. Отказы: нет поля, база комиссий — не смесь, имени нет в смеси."""
    from model.capital import GUARANTEES
    name = spec.get("component")
    if name is None:
        raise BookError(f"{GUARANTEES}.component: нет ключа при driver = fees_component — компонента смеси базы "
                        "комиссий не названа (Р5-5, М§4.11)")
    raw = book.opt(FEES_BASE)
    if not (isinstance(raw, Mapping) and MIX in raw):
        raise BookError(f"{GUARANTEES}.driver = fees_component: база комиссий {FEES_BASE} — не смесь {{mix: …}}, "
                        "компоненты нет (Р5-5, М§4.11)")
    if str(name) not in raw[MIX]:
        raise BookError(f"{GUARANTEES}.component = {name!r}: нет среди компонент смеси {FEES_BASE}.{MIX} "
                        f"({', '.join(map(str, raw[MIX]))}; Р5-5, М§4.11)")
    return str(name), raw[MIX][str(name)]["base"]


def guarantees(book: "Book", facts: "Facts", roles: BookRoles, af: AnchorFacts, tl: Timeline) -> Guarantees | None:
    """Составляющая RWA гарантий (К5, М§4.11, ключ `capital.rwa.guarantees`): G_0 по номиналам (anchor — факты
    `capital.guarantees.<вид>`), CCF и весу; книга выреза — кредитная; драйвер и его уровень якоря D^G_0 — база
    комиссий на конец квартала якоря (`fees_base`), база одной компоненты смеси базы комиссий на конец квартала якоря
    (`fees_component`, Р5-5: G_q / D^c_q не зависит от долей смеси) или комиссии четырёх кварталов до якоря
    включительно (`fees_line`). Нет ключа или выключен — None."""
    from model.capital import GUARANTEES, guarantees_g0
    spec = book.opt(GUARANTEES)
    if spec is None or spec.get("enabled") is not True:
        return None
    spec = dict(spec)
    spec["notional"] = {kind: facts.need("capital", f"guarantees.{kind}") if value == "anchor" else float(value)
                        for kind, value in spec["notional"].items()}
    carve = str(spec["carve_from"])
    if carve not in roles.loans:
        raise BookError(f"{GUARANTEES}.carve_from = {carve!r}: не кредитная книга ({', '.join(roles.loans)}; М§4.11)")
    driver, base = str(spec["driver"]), None
    if driver == "fees_component":                # Р5-5: уровень базы компоненты смеси (без доли s_c)
        name, comp = guarantee_component(book, spec)
        base = line_base(comp, f"{FEES_BASE}.{MIX}.{name}.base", books=book.get("nii.books"), roles=roles, af=af,
                         hist_bal={}, hist_books={}, tl=tl, history=False, funds=funds_books(roles, book))
        d0 = base.end0                            # D^c_0 — остатки якоря по весам компоненты
    elif driver == "fees_base":
        base = line_base(fees_base_spec(book, roles, af.balances), "fees.volume_base", books=book.get("nii.books"),
                         roles=roles, af=af, hist_bal={}, hist_books={}, tl=tl, history=False,
                         funds=funds_books(roles, book))
        d0 = base.end0
    else:
        d0 = 0.0
        for x in range(-3, 1):
            got = af.pnl.get(tl.period(x), {}).get("fees_net")
            if got is None:
                raise FactsError(f"факты pnl_quarterly: нет fees за {tl.period(x)} — драйвер RWA гарантий «строка "
                                 "комиссий за четыре квартала» не определён (М§4.11)")
            d0 += got
    if not d0 > 0:
        raise BookError(f"{GUARANTEES}.driver = {driver}: уровень драйвера якоря {d0:g} не больше нуля (М§4.11)")
    return Guarantees(g0=guarantees_g0(spec), carve=carve, driver=driver, base=base, d0=d0)


def buyback(book: "Book", tl: Timeline, calendar: QuarterCalendar | None, register: tuple) -> Buyback | None:
    """Выкуп по цене мира (М§5.6, ключ `dividends.buyback`): сумма по кварталам сетки (≥ 0), правило цены, цена книги и
    квартал даты книги, цены закрытых кварталов (first_period ≤ q < q_b), дисконт миров на дату книги, DPS записей
    реестра закрытых кварталов прибыли с экс-датой позже даты книги. Нет ключа или выключен — None."""
    spec = book.opt(BUYBACK)
    if spec is None or spec.get("enabled") is not True:
        return None
    if calendar is None:
        raise BookError(f"{BUYBACK}.enabled: выкуп по цене мира — только при квартальном календаре дивидендов (М§5.6)")
    for key in ("amount", "price"):
        if spec.get(key) is None:
            raise BookError(f"{BUYBACK}.{key}: нет ключа при включённом выкупе (М§5.6)")
    amount = _series(spec["amount"], tl)
    negative = [tl.period(q) for q in range(1, tl.Q + 1) if amount[q] < 0]
    if negative:
        raise BookError(f"{BUYBACK}.amount: сумма выкупа меньше нуля за {', '.join(negative)} (М§5.6)")
    main = str(book.get("meta.company.main_ticker"))
    p_book = float(book.get("meta.market_price")[main])
    if not p_book > 0:
        raise BookError(f"meta.market_price.{main} = {p_book}: цена книги не больше нуля — выкупа по ней нет (М§5.6)")
    v = to_date(book.get("meta.valuation_date"))
    clock = make_clock(book, tl, v)
    closed = {}
    for key, price in (spec.get("closed_prices") or {}).items():
        q = tl.index(str(key))
        if not 1 <= q < clock.q0:
            raise BookError(f"{BUYBACK}.closed_prices.{key}: квартал вне закрытых к дате книги кварталов сетки "
                            f"{tl.period(1)} … {tl.period(clock.q0 - 1)} (М§5.6)")
        closed[q] = float(price)
    bridge: dict[int, float] = {}
    for rec in register:
        period, ex = getattr(rec, "period", None), getattr(rec, "ex", None)
        if getattr(rec, "status", None) not in DECLARED or not period or ex is None or ex <= v:
            continue
        if calendar.closed(tl.index(str(period))):     # вычтен из BV в якоре, цена рынка до экс-даты его содержит
            q = tl.q_of_date(ex)
            if 1 <= q <= tl.Q:
                bridge[q] = bridge.get(q, 0.0) + float(rec.dps)
    return Buyback(rule=str(spec["price"]), amount=amount, p_book=p_book, qb=clock.q0, e_book=clock.elapsed,
                   closed=closed, disc={str(w): discount(book, str(w), clock) for w in book.get("worlds.ids")},
                   bridge_dps=bridge, skip=bool(spec.get("skip_in_shock_year", False)))


def _weighted_history(weights: Mapping[str, Any], books: Mapping[str, Any],
                      hist_books: Mapping[int, Mapping[str, float]], anchor: Mapping[str, float], tl: Timeline,
                      key: str = OPEX_WEIGHTS) -> tuple[dict[str, float], dict[int, float]]:
    """База связи расходов с объёмом по себестоимости книг (М§4.7, ключ `opex.volume_weights`): веса ω̂_b,
    нормированные на квартале якоря (ω̂_b = ω_b Σ Ē_b,0 / Σ ω_b Ē_b,0 — взвешенная база якоря равна невзвешенной сумме
    тех же книг; рост от нормировки не зависит), и A^C_x = Σ ω̂_b Ē_b,x по кварталам x = −3…0 — средние остатки книг
    по фактам (`balance.history.<период>.books.<b>`; конец якоря — остатки якоря). Книги с нулевым весом не
    читаются; нет конца квартала у книги с весом — FactsError. `key` — ключ книги в отказах (тот же расчёт у базы
    строки, К2)."""
    raw = {str(b): float(w) for b, w in weights.items()}
    unknown = sorted(set(raw) - set(books))
    if unknown:
        raise BookError(f"{key}: книги {', '.join(unknown)} — не книги nii.books (М§4.7)")
    used = [b for b in books if raw.get(b, 0.0) > 0]
    if not used:
        raise BookError(f"{key}: все веса нулевые — базы связи с объёмом нет (М§4.7)")
    ends: dict[int, dict[str, float]] = {0: {b: anchor[b] for b in used}}
    for x in range(-4, 0):
        row = hist_books.get(x, {})
        missing = [b for b in used if row.get(b) is None]
        if missing:
            what = "расходов" if key == OPEX_WEIGHTS else key
            raise FactsError(f"balance.history: нет остатков книг {', '.join(missing)} на конец {tl.period(x)} — "
                             f"рост базы {what} по книгам г/г не определён (М§4.7)")
        ends[x] = {b: row[b] for b in used}
    avg = {x: {b: (ends[x - 1][b] + ends[x][b]) / 2 for b in used} for x in range(-3, 1)}
    norm = sum(avg[0][b] for b in used) / sum(raw[b] * avg[0][b] for b in used)
    w_hat = {b: raw[b] * norm for b in used}
    return w_hat, {x: sum(w_hat[b] * avg[x][b] for b in used) for x in range(-3, 1)}


def _year_sum_table(traj: Any, years: range) -> dict[int, float]:
    t = Trajectory(traj)
    return {y: sum(t.value(y, n) for n in (1, 2, 3, 4)) / 4 for y in years}


def prepare(book: "Book", facts: "Facts", timeline: Timeline, bridge: Bridge,
            transmission: "Transmission", register: tuple = ()) -> Prepared:
    books = book.get("nii.books")
    roles = book_roles(books)
    af = anchor_facts(facts, books)
    tl = timeline
    ay = tl.anchor_year
    years = range(ay - 1, tl.last_year + 1)
    if int(book.get("noncore.price_base_year")) != ay:
        raise BookError("noncore.price_base_year: цены книги — цены года якоря (М§4.7)")
    spreads = spread_paths(book, tl, transmission.sigma0, transmission.sigma0_liab)
    regimes = {}
    for r in book.get("regimes.ids"):
        spec = book.get(f"regimes.{r}")
        adj = Trajectory(spec["loan_growth_adj"])
        one = spec.get("one_off_loss")
        one_q = tl.index(one["period"]) if one else None
        offset = spec.get("shock_year_offset")
        regimes[r] = RegimePath(
            regime=r, cor_engine=regime_cor_engine(book, bridge, r, tl),
            nim_shift=_series(spec["nim_shift"], tl),
            loan_adj={y: adj.year_value(y) for y in years},
            override={int(k): float(v) for k, v in (spec.get("loan_growth_override") or {}).items()},
            one_off_q=one_q if one_q is not None and 1 <= one_q <= tl.Q else None,
            one_off_amount=float(one["amount"]) if one else 0.0,
            shock_year=None if offset is None else ay + int(offset),
            rwa_mult=regime_rwa_mult(book, r, tl))
    scenarios = {s: scenario_path(book, s, tl) for s in book.get("capital.reg_scenarios.ids")}
    rw = rwa_weights(book, roles)
    guar = guarantees(book, facts, roles, af, tl)
    if guar is not None:                    # вырез гарантий из плотности книги: RWA якоря тот же (К5, М§4.11)
        rw = carve_guarantees(rw, guar.g0, guar.carve, af.balances[guar.carve])
    cash = cash_assets(book, facts, roles=roles, af=af, tl=tl, oa_fixed=rw.oa_fixed)
    if cash is not None:                    # вырез денег из плотности растущих прочих активов: RWA якоря тот же (К8)
        rw = carve_cash(rw, float(book.get(CASH_DENSITY)), cash.c0, af.other_assets)
        if cash.theta is not None:          # вытесненная часть прочих активов — слагаемым RWA (Р6-1, М§4.11)
            cash = displaced_shift(cash, rw)
    rwa0 = rwa_anchor(rw, af)
    cap = capital_const(book, af, rwa0)
    policy = make_policy(book, af.n_iss, af.n_out)
    quarterly = policy.rule is not None
    calendar = None
    if quarterly:                           # открытые кварталы прибыли по кварталам клетки, состояние якоря (М§5.7)
        calendar = quarter_calendar(policy, facts, tl, register, to_date(book.get("meta.facts_date")),
                                    af.dividends_payable)
    # История по кварталам до якоря (q ≤ 0): база «к тому же кварталу» и прибыль.
    hist: dict[str, dict[int, float]] = {"fees": {}, "opex": {}, "ins": {}, "ni_sh": {}, "noncore": {},
                                         "misc": {}, "llp": {}, "nii": {}, "pbt": {}, "tax": {}, "ni": {}}
    for per, row in af.pnl.items():
        q = tl.index(per)
        if q > 0:
            continue
        for name, key, sign in (("fees", "fees_net", 1), ("opex", "opex", -1), ("ins", "insurance_net", 1),
                                ("ni_sh", "ni_shareholders", 1), ("noncore", "noncore_net", 1),
                                ("misc", "misc_net", 1), ("llp", "llp_debt_fa", -1), ("nii", "nii", 1),
                                ("pbt", "pbt", 1), ("tax", "tax", -1), ("ni", "ni", 1)):
            if row.get(key) is not None:
                hist[name][q] = sign * row[key]
    # Концы кварталов до якоря (годовые отношения года якоря — средние пяти концов, М§0.3).
    hist_bal: dict[int, dict[str, float]] = {}
    hist_books: dict[int, dict[str, float]] = {}
    bal_hist = facts.file("balance").get("history")
    if isinstance(bal_hist, list):          # запись INTERFACES §3.2: [{period, …}]; словарь по периодам — тоже
        bal_hist = {str(r["period"]): r for r in bal_hist if isinstance(r, Mapping) and "period" in r}
    if isinstance(bal_hist, Mapping):
        for per, row in bal_hist.items():
            q = tl.index(str(per))
            if q >= 0 or not isinstance(row, Mapping):
                continue
            vals = {}
            for key, name in (("bv_common", "bv"), ("loans_ac_gross", "loans_ac"), ("iea", "iea"),
                              ("loans", "loans"), ("funds", "funds")):
                node = row.get(key)
                if isinstance(node, Mapping) and node.get("v") is not None:
                    vals[name] = float(node["v"])
            hist_bal[q] = vals
            node = row.get("books")
            if isinstance(node, Mapping):         # концы кварталов по книгам ЧПД (М§4.7, база расходов по книгам)
                hist_books[q] = {str(b): float(x["v"]) for b, x in node.items()
                                 if isinstance(x, Mapping) and x.get("v") is not None}
    # Год якоря: факт отчётных кварталов и остаток года (М§0.3).
    fact_qs = [q for q in tl.quarters_of_year(ay) if q <= 0]
    rest_qs = [q for q in tl.quarters_of_year(ay) if q >= 1]

    def need_hist(name: str, qs: list[int]) -> float:
        missing = [tl.period(q) for q in qs if q not in hist[name]]
        if missing:
            raise FactsError(f"факты pnl_quarterly: нет {name} за {', '.join(missing)} (М§0.3)")
        return sum(hist[name][q] for q in qs)

    for q in range(1, 5):
        for name in ("fees", "opex", "ins"):
            if q - 4 not in hist[name]:
                raise FactsError(f"факты pnl_quarterly: нет {name} за {tl.period(q - 4)} "
                                "(база «к тому же кварталу», М§0.3)")
    fees_override = {int(k): float(v) for k, v in book.get("fees.growth_override").items()}
    if ay in fees_override and rest_qs:
        prev = need_hist("fees", tl.quarters_of_year(ay - 1))
        fact = need_hist("fees", fact_qs)
        base = sum(hist["fees"][q - 4] for q in rest_qs)
        fees_override[ay] = (prev * (1 + fees_override[ay]) - fact) / base - 1
    noncore_tab = _year_sum_table(book.get("noncore.result_real"), years)
    misc_tab = _year_sum_table(book.get("other.misc_net_real"), years)
    noncore_q = {y: v / 4 for y, v in noncore_tab.items()}
    shares = {h: float(book.get(f"other.misc_quarter_shares.{h}")) for h in (1, 2, 3, 4)}
    misc_q = {(y, h): v * shares[h] for y, v in misc_tab.items() for h in (1, 2, 3, 4)}
    nci_raw = book.opt(NCI_REAL)            # Р11-3: НДУ в реальных рублях — год / 4 на квартал (как «прочее» — в ценах якоря)
    nci_q = None if nci_raw is None else {
        (y, h): v / 4 for y, v in _year_sum_table(nci_raw, years).items() for h in (1, 2, 3, 4)}
    if rest_qs:             # остатком года закрывается только непрофильный результат (М§0.3)
        noncore_q[ay] = (noncore_tab[ay] - need_hist("noncore", fact_qs)) / len(rest_qs)
    stat = Trajectory(book.get("tax.statutory"))
    tau_stat = {y: sum(stat.value(y, n) for n in (1, 2, 3, 4)) / 4 for y in years}
    if calendar is not None:                # окно базы первого открытого квартала прибыли уходит раньше якоря
        for y in range(tl.year(calendar.p_last + 2 - policy.window), years[0]):
            tau_stat[y] = sum(stat.value(y, n) for n in (1, 2, 3, 4)) / 4
    ot = book.get("tax.one_off")
    ot_q = tl.index(period_str(int(ot["year"]), 1))
    book_rel = book_relative(book, roles, af)
    seg = None
    if book.get("credit.segment_relative.enabled"):
        seg = {"corporate": float(book.get("credit.segment_relative.corporate")),
               "retail": float(book.get("credit.segment_relative.retail"))}
    tenor = str(book.get("oci.fvoci_tenor"))
    node = tenor.split("_")[1].rstrip("y")
    fv_book = af.fv_book
    fv_share = float(books[fv_book]["fv_share"]) if fv_book and "fv_share" in books[fv_book] else 0.0
    reg_q, pay_q = {}, {}
    for rec in register:
        if getattr(rec, "status", None) not in ("declared", "paid"):
            continue
        if rec.record_date is not None:
            reg_q[record_key(rec, quarterly)] = tl.q_of_date(rec.record_date)
        if rec.pay_date is not None:
            pay_q[record_key(rec, quarterly)] = tl.q_of_date(rec.pay_date)
    anchor_state = {"loans": sum(af.balances[b] for b in roles.loans), "rwa0": rwa0}
    fvr_on = bool(book.get("other.fvtpl_bond_reval"))
    fv_ref = str(book.get("credit.fv_loans_ref"))
    if fv_ref not in regimes:
        raise BookError(f"credit.fv_loans_ref = {fv_ref!r}: нет такого режима (М§4.6)")
    ref_book = book if book.base is None else book.base      # опора FVC — путь нормы книги до розыгрыша (М§4.6)
    fv_ref_cor = regime_cor_engine(ref_book, bridge, fv_ref, tl)
    loan_d, loan_drift = _drift(book.get("volumes.loan_share_drift"), years)
    funds_d, funds_drift = _drift(book.get("volumes.funds_share_drift"), years)
    funds_drift_q = _drift_quarters(book.get("volumes.funds_share_drift"))
    growth = growth_rule(book)
    if growth is not None and calendar is None:
        raise BookError("capital.growth_constraint.enabled: рост по капиталу — только при квартальном календаре "
                        "дивидендов (М§4.13)")
    glide = {} if growth is None else {
        s: (glide_path(sp.req20, growth.lookahead, growth.glide), glide_path(sp.req11, growth.lookahead, growth.glide))
        for s, sp in scenarios.items()}
    links = {k: float(book.opt(path, 0.0)) for k, path in (
        ("fees", "fees.volume_link"), ("ins", "other.insurance_volume_link"), ("opex", "opex.volume_link"))}
    link_base, hist_vol = "", {}
    words = funds_books(roles, book)        # Р11-2: книги слова «средства клиентов» механики (без ключа — roles.funds)
    if any(links.values()):                 # база объёма читается, когда хотя бы одна связь не ноль (М§4.7)
        link_base = str(book.opt("volumes.link_base", LINK_BASES[0]))
        anchor_end = {"loans": anchor_state["loans"], "funds": sum(af.balances[b] for b in words),
                      "iea": sum(af.balances[b] for b in roles.assets)}[link_base]
        hist_vol = _volume_history(link_base, hist_bal, anchor_end, tl)
    lam_f, fixed_parts = fixed_terms(book)           # блок постоянных частей терминала (М§7): параметр оценки
    opex_w, hist_vol_opex, opex_w_bal = None, {}, False
    weights = book.opt(OPEX_WEIGHTS)
    if weights is not None and links["opex"]:       # веса читаются при связи расходов с объёмом (М§4.7)
        opex_w, hist_vol_opex = _weighted_history(weights, books, hist_books, af.balances, tl)
        opex_w_bal = any(opex_w.get(b, 0.0) > 0 for b in (SECURITIES, LIQUIDITY, WHOLESALE))
    wh_struct = wholesale_structural(book)
    lines = line_bases(book, links, hist_vol=hist_vol, hist_vol_opex=hist_vol_opex, opex_w=opex_w, books=books,
                       roles=roles, af=af, hist_bal=hist_bal, hist_books=hist_books, tl=tl)
    driven = liability_drivers(book, links, roles=roles, books=books, af=af, hist_bal=hist_bal, hist_books=hist_books,
                               tl=tl, history=False)
    allow = allowance_by_book(book, facts, roles, af)
    k6, k6_books, hist_k6 = k6_line(book, driven, tl, hist_bal=hist_bal, hist_books=hist_books)   # Р10-5: К6 формой строки
    if k6 is not None:                      # ряды D (лаг 4) и Ψ книг К6 — в памяти оценок шага, как ряды баз строк
        lines["line_flows"] = tuple(lines.get("line_flows", ())) + tuple(hist_k6)
    return Prepared(
        timeline=tl, roles=roles, books=books, af=af, spreads=spreads, phi=transmission.phi,
        reference_world=transmission.reference_world or str(book.get("nii.transmission.reference_world")),
        regimes=regimes, scenarios=scenarios, dn=density_index(book, tl), rwa_w=rw, cap=cap,
        policy=policy, anchor_year=ay, guidance_year=int(book.get("volumes.guidance_year")),
        guidance_growth={k: float(v) for k, v in book.get("volumes.guidance_growth").items()},
        loan_share_drift=loan_d, funds_share_drift=funds_d, loan_drift=loan_drift, funds_drift=funds_drift,
        funds_drift_q=funds_drift_q,
        oa_fixed=float(book.opt("volumes.other_assets_fixed", 0.0)),
        link_fees=links["fees"], link_ins=links["ins"], link_opex=links["opex"], link_base=link_base,
        hist_vol=hist_vol,
        drift_until=int(book.get("volumes.share_drift_until")),
        liquid_min=float(book.get("volumes.liquid_min_share")),
        sec_share=float(book.get("volumes.securities_share_of_liquid")),
        wh_to_funds=float(book.get("volumes.wholesale_to_funds")) if wh_struct is None else wh_struct,
        wh_anchor=None if wh_struct is None else float(book.get("volumes.wholesale_to_funds")),
        **({} if allow is None else {"allow_cov": allow[0], "allow_resid": allow[1], "loans_ac0": allow[2]}),
        guar=guar, stationary_rates=book.opt(STATIONARY_RATES) is True, **lines, driven=driven,
        driver_roots=driver_roots(book, driven, tl),
        root_mult=book.opt(LINE_ROOT_FORM) == ROOT_MULTIPLICATIVE,
        link_line=lines.get("share_nominal") is not None and form_line(book),
        k6_line=k6, k6_books=k6_books, hist_k6_line=hist_k6,
        min_dps=min_dps_years(book, tl, calendar, growth), year_basis=year_basis(book), fade_anchor=fade_anchor(book),
        fixed_funding=fixed_funding(book), cash=cash,
        oa_ratio=float(book.get("volumes.other_assets_to_loans")),
        ol_ratio=float(book.get("volumes.other_liabilities_to_loans")),
        allowance_ratio=float(book.get("credit.allowance_ratio")),
        fv_share=fv_share, fv_book=fv_book,
        c_ref=float(book.get("nii.retail_current_share.c_ref")),
        psi=float(book.get("nii.retail_current_share.psi")),
        key_ref=float(book.get("nii.retail_current_share.key_ref")),
        c_bounds=tuple(float(x) for x in book.get("nii.retail_current_share.bounds")),
        c_rho=float(book.get("nii.retail_current_share.rho")),
        dia=float(book.get("nii.dia_rate")),
        fees_gvw=_series(book.get("fees.growth_vs_wages"), tl),
        fees_override=fees_override,
        opex_real=_series(book.get("opex.real_growth"), tl),
        ins_gvw=_series(book.get("other.insurance_growth_vs_wages"), tl),
        noncore_q=noncore_q, misc_q=misc_q, tau_stat=tau_stat,
        tax_gap=float(book.get("tax.effective_gap")),
        ot_q=ot_q if 1 <= ot_q <= tl.Q else None,
        ot_amount=float(ot["prob"]) * float(ot["amount"]),
        other_movements=_series(book.get("equity.other_movements"), tl),
        t2=_series(book.get("capital.n20.t2"), tl),
        nci_share=float(book.get("pnl.nci_share")) if nci_q is None else 0.0,    # Р11-3: при nci_real доля не читается
        fv_factor=float(book.get("credit.fv_loans_factor")),
        kappa=float(book.get("credit.kappa")), lag=int(book.get("credit.real_rate_lag_q")),
        segment_rel=seg, coupon_annual=af.coupon_annual, coupon_quarter=af.coupon_quarter,
        hist={k: dict(v) for k, v in hist.items()}, hist_bal=hist_bal,
        fvoci_duration=float(book.get("oci.fvoci_duration")),
        fvoci_maturity=float(book.get("oci.fvoci_maturity")),
        fvoci_share=float(book.get("oci.fvoci_share")), fvoci_tenor=tenor,
        y_tenor0=af.ofz_anchor[node], fvr_on=fvr_on,
        fvtpl_share=float(book.get("oci.fvtpl_bond_share")),
        fvtpl_duration=float(book.get("oci.fvtpl_bond_duration")) if fvr_on else 0.0,
        real_growth=float(book.get("valuation.terminal.real_growth")),
        fade=float(book.get("valuation.terminal.fade")),
        multiple=float(book.get("valuation.terminal.excess_capital_multiple")),
        register=register_dps(register, quarterly), reg_q_by_year=reg_q, pay_q_by_year=pay_q, calendar=calendar,
        growth=growth, glide=glide, kappa_world=kappa_world(book), fade_symmetric=fade_symmetric(book),
        book_rel=book_rel, opex_w=opex_w, hist_vol_opex=hist_vol_opex, opex_w_bal=opex_w_bal,
        fixed_growth_share=lam_f, fixed_parts=fixed_parts, bb=buyback(book, tl, calendar, register),
        rwa0=rwa0, anchor_state=anchor_state,
        near=_series(book.get("regimes.near_nim_shift"), tl), misc_shares=shares,
        fv_ref=fv_ref, fv_ref_cor=fv_ref_cor, phi_assets=transmission.phi_assets,
        phi_liab=transmission.phi_liab, phi_weights=dict(transmission.phi_weights),
        phi_share=phi_shares(books),
        nci_q=nci_q,
        **({} if len(words) == len(roles.funds) else {
            "funds_words": words, "wh_corp": tuple(b for b in words if b not in roles.retail)}),
    )


# ------------------------------------------------------------------ состояние


class State:
    """Состояние клетки на конец квартала (копируется для пробного прохода)."""

    __slots__ = ("E", "rate", "FR", "c", "AL", "OA", "OL", "DP", "BV", "R", "D", "pay", "reg",
                 "guid", "wh_extra", "q", "n_out", "p_plus")

    def clone(self) -> "State":
        s = State.__new__(State)
        s.E, s.rate = dict(self.E), dict(self.rate)
        s.FR, s.c, s.AL, s.OA, s.OL = self.FR, self.c, self.AL, self.OA, self.OL
        s.DP, s.BV, s.R, s.D = self.DP, self.BV, self.R, self.D
        s.pay, s.reg = dict(self.pay), list(self.reg)
        s.guid, s.wh_extra, s.q = dict(self.guid), self.wh_extra, self.q
        s.n_out, s.p_plus = self.n_out, self.p_plus     # выкуп (М§5.6): акции клетки, форвард цены после квартала
        return s


def initial_state(p: Prepared) -> State:
    af, roles = p.af, p.roles
    s = State.__new__(State)
    s.E = {b: af.balances[b] for b in roles.names}
    s.rate = {b: af.rates[b] for b in roles.names}
    s.FR = sum(af.balances[b] for b in roles.retail)
    s.c = af.balances[roles.retail[0]] / s.FR
    s.AL, s.OA, s.OL = af.allowance, af.other_assets, af.other_liabilities
    s.DP, s.BV, s.R, s.D = af.dividends_payable, af.bv, af.fvoci_reserve, 0.0
    s.pay, s.reg, s.guid, s.wh_extra, s.q = {}, [], {}, 0.0, 0
    s.n_out, s.p_plus = af.n_out, None
    tl, pol = p.timeline, p.policy
    if p.calendar is not None:
        # квартальный календарь (М§5.7.4): в очереди — только объявленная часть остатка; остальное —
        # постоянное обязательство: не выплачивается и в регуляторный капитал не возвращается
        for pq, rq, amount in p.calendar.payable:
            s.pay[pq] = s.pay.get(pq, 0.0) + amount
            if rq >= 1:
                s.reg.append((0, rq, amount))
        return s
    if af.dividends_payable and af.dividends_payable_year is not None:
        y = af.dividends_payable_year
        pq = p.pay_q_by_year.get(y, tl.index(period_str(y + 1, pol.pay_quarter)))
        rq = p.reg_q_by_year.get(y, tl.index(period_str(y + 1, pol.reg_quarter)))
        s.pay[max(1, pq)] = s.pay.get(max(1, pq), 0.0) + af.dividends_payable
        if rq >= 1:
            s.reg.append((0, rq, af.dividends_payable))
    return s


def dpreg_at(reg: list, q: int) -> float:
    """DPreg на конец q: решено к кварталу q включительно, не вычтено из регуляторного капитала до квартала
    вычета (М§4.11). Шаг держит в очереди состояния только то, что ещё не вычтено (квартал вычета позже
    квартала шага): вычтенное в сумму уже не входит."""
    return sum([a for (dq, rq, a) in reg if dq <= q < rq])


# ------------------------------------------------------------------ результат клетки


@dataclass(frozen=True)
class CellResult:
    world: str
    regime: str
    scenario: str
    quarters: Mapping[str, tuple[float | None, ...]]   # ряды по кварталам 0..Q
    annual: Mapping[str, tuple[float | None, ...]]     # по годам якоря … last_period
    dps: Mapping[int, float]               # год прибыли → DPS (₽, не округлён)
    v_ri: float
    v_ddm: float
    bv_v: float
    x_t: float
    roe_t: float
    k_t: float
    g_t: float
    tv_ri: float
    terminal_share: float
    n20_min: float
    n11_min: float
    gap_period: str | None
    flags: frozenset[str]
    # сверх договора INTERFACES §4.3 (только добавление)
    years: tuple[int, ...] = ()
    tv_ddm: float = 0.0
    pv_ri_explicit: float = 0.0
    pv_terminal: float = 0.0
    roe_t_raw: float = 0.0
    g_capped: bool = False
    bv_star: float = 0.0
    decisions: tuple[Decision, ...] = ()
    dps_policy: Mapping[int, float] = field(default_factory=dict)
    ci_q0: float = 0.0
    n11_star: float = 0.0
    real_rate: float = 0.0
    y_x: float = 0.0                       # доход на избыток, вычтенный из терминального года (М§7)
    la_headroom: float = 0.0               # HLA_Q — запас балансирующих активов над минимумом на конце Q
    books: Mapping[str, Mapping[str, tuple[float | None, ...]]] = field(default_factory=dict)
    # книга → {"rate": ставка квартала, "avg": средний остаток, "balance": остаток на конец} по q = 0…Q
    # квартальный календарь дивидендов (М§5.7.5); при годовом — пусто
    dps_q: Mapping[str, float] = field(default_factory=dict)          # квартал прибыли → DPS решения клетки
    dps_policy_q: Mapping[str, float] = field(default_factory=dict)   # квартал прибыли → пул политики / N_iss
    # рост кредитных книг по годам клетки (`GROWTH_FIELDS`, М§4.13.3): потенциальный и фактический рост суммы
    # кредитных книг за год, доля урезанного на конец года, навёрстанное за год, наименьшая λ* года
    growth: Mapping[str, tuple[float | None, ...]] = field(default_factory=dict)
    solver: tuple[tuple[str, float], ...] = ()     # кварталы флага growth_solver: (период, невязка норматива)
    pv_ri_q: tuple[float, ...] = ()        # RI_q × DF_v(τ_q) по q = 0…Q (до квартала даты оценки — 0), млрд ₽
    terminal_fixed: Mapping[str, Any] | None = None   # блок постоянных частей терминала (М§7); без ключа — None
    # выкуп по цене мира (М§5.6); без ключа — None и ноль
    v_hat: float | None = None             # V̂_c = S_c × N_out / 1000 — оценка в цене (млрд ₽)
    s_price: float | None = None           # S_c — стоимость на оставшуюся акцию клетки, ₽
    n_t: float | None = None               # акции клетки на конце сетки, млн шт.
    pv_buyback: float = 0.0                # Σ B_q DF_v(τ_q), млрд ₽
    terminal_stationary: Mapping[str, float] | None = None   # терминал от стационарных ставок книг (К4, М§7); без
    #                                                          ключа — None
    terminal_year: Mapping[str, float] | None = None   # год терминала по средней длине года (К-Т2а, М§7); без ключа —
    #                                                    None
    terminal_fade: Mapping[str, Any] | None = None     # угасание по календарю (К-Т2в, М§7): {s, n, phi}; только при s > 0

    @property
    def v_price(self) -> float:
        """Оценка клетки в цене (М§8.2): при выкупе по цене мира — V̂_c; без него — V_RI (тот же объект)."""
        return self.v_ri if self.v_hat is None else self.v_hat

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.world, self.regime, self.scenario)

    @property
    def label(self) -> str:
        return f"{self.world}/{self.regime}/{self.scenario}"


# ------------------------------------------------------------------ квартальный проход


def growth_share(g_min: float, g_full: float, lam_min: float) -> float:
    """λ*_j — доля прироста, при которой невязка условия роста норматива j равна нулю (М§4.13.2 п. 3): по двум
    оценкам шага, при наименьшей доле (`g_min`) и при полном росте (`g_full`); условие почти аффинно по доле.
    Норматив не связывает (`g_full ≥ 0`) или урезание роста его не поправляет — единица."""
    if g_full >= 0 or g_min - g_full <= SLOPE_TOL:
        return 1.0
    return lam_min + (1 - lam_min) * g_min / (g_min - g_full)


class _Cell:
    """Одна клетка: ряды мира, режима и сценария + шаг квартала."""

    def __init__(self, ctx: "RunContext", world: str, regime: str, scenario: str, *,
                 preliminary: bool = False, shared: dict | None = None):
        """`shared` — общее для клеток одного прогона (словарь вызывающего, один на прогон): годы и номера
        кварталов сетки; по миру — κ-добавка (к миру-опоре книги), разность опорных ставок X_W,q и ставки книг по кварталам (от
        режима, сценария, объёмов и дивидендов они не зависят); по миру и режиму — потенциальные множители роста
        кредитных книг. Без него клетка считает всё сама."""
        p: Prepared = ctx.prep
        self.p, self.tl = p, p.timeline
        self.w: WorldPath = ctx.worlds[world]
        self.wh: WorldPath = ctx.worlds[p.reference_world]
        self.rg: RegimePath = p.regimes[regime]
        self.sc: ScenarioPath = p.scenarios[scenario]
        self.world, self.regime, self.scenario = world, regime, scenario
        Q = self.tl.Q
        dev = ctx.deviations.get(regime, {}) if not preliminary else {}
        zero = tuple([0.0] * (Q + 1))
        self.d_cor = dev.get("cor", zero)
        self.d_nim = dev.get("nim", zero)
        near = p.near or zero
        self.nim_shift = tuple(near[q] + self.rg.nim_shift[q] for q in range(Q + 1))
        if shared is None:
            shared = {}
        of_world = shared.get(world)
        if of_world is None:
            # κ-добавка — к миру-опоре книги (любого знака); нет ключа — к базовому миру, только вверх (М§4.6)
            kap = kappa_addon(p.kappa, p.lag, self.w.real_key, ctx.worlds[p.kappa_world or BASE_WORLD].real_key, Q,
                              signed=p.kappa_world is not None)
            # X_W,q — разность опорных ставок кредитных книг Φ_A мира и мира H, взвешенная долями якоря (М§4.4)
            refs = [(wt, self.w.ref(p.books[b]["ref"]), self.wh.ref(p.books[b]["ref"]))
                    for b, wt in p.phi_weights.items()]
            x_w = tuple(sum(wt * (rw[q] - rh[q]) for wt, rw, rh in refs) for q in range(Q + 1))
            of_world = shared[world] = (kap, x_w, {})       # третье — ставки книг по кварталам (`evaluate`)
        kap, self.x_w, self.rates = of_world
        self.cor = tuple(self.rg.cor_engine[q] + kap[q] + self.d_cor[q] for q in range(Q + 1))
        self.kappa = kap
        self.cor_ref = p.fv_ref_cor                         # путь режима-опоры книги до розыгрыша, без κ и δ
        fx = getattr(ctx, "fx", None)                       # входы прохода (`PathInputs`) несут индекс готовым
        self.x = fx[world] if fx is not None else fx_index(ctx.book, self.w.cpi, Q)
        # CoR сегментов: при выключенной сегментной схеме — общая CoR (М§4.6).
        if p.segment_rel is not None:
            af = p.af
            w_ac = {"corporate": 0.0, "retail": 0.0}
            for b in p.roles.loans:
                seg = p.books[b]["cor_segment"]
                w_ac[seg] += af.balances[b] - (af.fv_loans if b == p.fv_book else 0.0)
            tot = sum(w_ac.values())
            norm = sum(w_ac[s] / tot * p.segment_rel[s] for s in w_ac)
            self.seg_mult = {s: p.segment_rel[s] / norm for s in w_ac}
        else:
            self.seg_mult = None
        calendar = shared.get(CALENDAR)
        if calendar is None:
            calendar = shared[CALENDAR] = ({q: self.tl.year(q) for q in range(-8, Q + 1)},
                                           {q: self.tl.h(q) for q in range(-8, Q + 1)})
        self.years, self.hs = calendar
        self.flows: dict[str, dict[int, float]] = {k: dict(v) for k, v in p.hist.items()}
        if p.link_base:
            self.flows["vol"] = dict(p.hist_vol)           # A_x — средний остаток базы объёма по кварталам
        if p.opex_w is not None:
            self.flows["vol_opex"] = dict(p.hist_vol_opex)  # A^C_x — база расходов по себестоимости книг (М§4.7)
        self.line_flows()
        # требование с глиссадой req* (М§4.13.1); без ограничения роста — требование сценария
        self.req20g, self.req11g = p.glide[scenario] if p.growth is not None else (self.sc.req20, self.sc.req11)
        self.payout: dict[int, float] = shared.setdefault(PAYOUT, {})   # год прибыли → доля выплаты политики
        # год → книга → потенциальный множитель квартала: один у клеток мира и режима
        self.factors: dict[int, dict[str, float]] = shared.setdefault((world, regime), {})
        # `self.rates` (выше): квартал → ставки книг — одни у клеток мира и у всех оценок шага квартала
        self.unsolved: list[tuple[str, float]] = []         # кварталы, где доля прироста не сошлась в допуске
        # выкуп по цене мира (М§5.6): сумма квартала шага, начало форварда цены (у правила «стоимость клетки» —
        # неподвижная точка), признак внутреннего прохода неподвижной точки
        self.bb_q = 0.0
        self.p_start = p.bb.p_book if p.bb is not None else None
        self.fixed_point = False
        self.bb_iterations = 0
        self._nominal: tuple[float, ...] | None = None   # индекс номинала на концах кварталов (база строки, К2)
        self.stationary: dict[str, float] | None = None     # терминал от стационарных ставок книг (К4): печать клетки
        self.year_node: dict[str, float] | None = None      # год терминала по средней длине года (К-Т2а): печать клетки
        self.dps_year: dict[int, float] = {}                # жетон DPS (К1): год прибыли → Σ DPS решений клетки

    # ------------------------------------------------------------ рост объёмов
    def loan_growth(self, b: str, year: int) -> float:
        p, rg = self.p, self.rg
        if year in rg.override:
            return rg.override[year]
        sector = p.books[b]["sector"]
        g = self.w.credit_growth[sector][year]
        if p.loan_drift is not None:
            d = p.loan_drift[sector][year] if year <= p.drift_until else 0.0
        else:
            d = p.loan_share_drift if year <= p.drift_until else 0.0
        return (1 + g) * (1 + d) - 1 + rg.loan_adj.get(year, 0.0)

    def funds_growth(self, sector: str, year: int, quarter: int | None = None) -> float:
        """Годовой темп средств сегмента в квартале года: рост сектора мира с премией. Премия — значение года
        траектории; у квартала, заданного ключом квартала или полугодия, — значение этого ключа (М§4.3)."""
        p = self.p
        g = self.w.funds_growth[sector][year]
        if p.funds_drift is not None:
            d = p.funds_drift[sector][year] if year <= p.drift_until else 0.0
            keyed = p.funds_drift_q.get(sector)
            if keyed and year <= p.drift_until:
                d = keyed.get((year, quarter), d)
        else:
            d = p.funds_share_drift if year <= p.drift_until else 0.0
        return (1 + g) * (1 + d) - 1

    def growth_factors(self, year: int) -> dict[str, float]:
        """Потенциальный множитель квартала кредитных книг года: 1 + m_b = (1 + g_b,Y)^0,25 (М§4.13.1)."""
        fac = self.factors.get(year)
        if fac is None:
            fac = self.factors[year] = {b: (1 + self.loan_growth(b, year)) ** QUARTER_YEARS
                                        for b in self.p.roles.loans}
        return fac

    def guidance_multipliers(self, st: State, q: int) -> dict[str, float]:
        """Год гайденса: сегменты растут одним квартальным множителем к цели года (М§4.3)."""
        p, tl = self.p, self.tl
        year = self.years[q]
        qs = [x for x in tl.quarters_of_year(year) if x >= 1]
        n = len(qs)
        out = {}
        for seg in ("corporate", "retail"):
            books = [b for b in p.roles.loans if p.books[b]["cor_segment"] == seg]
            start = sum(st.E[b] for b in books)
            base_end = p.af.prev_year_end[seg] if year == p.anchor_year else start
            target = base_end * (1 + p.guidance_growth[seg])
            out[seg] = (target / start) ** (1 / n)
        return out

    # ------------------------------------------------------------ шаг квартала
    def step(self, st: State, q: int, div_decl: float, pay_q: int | None = None,
             reg_q: int | None = None, parts: tuple | None = None, lam: float | None = None,
             top_up: Mapping[str, float] | None = None,
             rates: Mapping[str, float] | None = None, memo: dict | None = None,
             light: bool = False) -> dict[str, float]:
        """Шаг квартала q. `div_decl` — уменьшение BV дивидендами квартала; `parts` — решения квартала
        (сумма, квартал выплаты, квартал вычета из регуляторного капитала) при квартальном календаре:
        `div_decl` — их сумма, у каждого решения свои кварталы (М§5.7.4 п. 6). `lam` — доля потенциального
        прироста кредитных книг при ограничении роста капиталом, `top_up` — навёрстывание по книгам, млрд ₽
        (М§4.13.1); без `lam` рост задан. `rates` — ставки книг квартала, уже посчитанные другой оценкой шага
        этого же квартала (от объёмов и дивидендов они не зависят); без них считаются здесь. `memo` — память
        оценок шага этого квартала с одного и того же состояния (её ведёт `quarter_constrained`): объёмы и
        строки ОПУ, которые от дивидендов не зависят, считаются один раз на долю прироста и навёрстывание,
        сторона средств клиентов — один раз на квартал; без неё всё считается здесь. `light` — вернуть только
        нормативы и RWA квартала (и ставки книг), без записи шага и перехода состояния: так считаются оценки,
        по которым меряется запас капитала."""
        p, tl, w = self.p, self.tl, self.w
        books, roles = p.books, p.roles
        year, h = self.years[q], self.hs[q]
        d = tl.days[q - 1]
        dt = d / DAYS_IN_YEAR
        key = w.key[q]
        wage = w.wage[q]
        # 2. объёмы небалансирующих статей
        E0 = st.E
        slot = same = None                      # ключ памяти оценки и её запись (тот же квартал, та же доля)
        if p.memo_off:                          # база строки на балансирующих книгах (К2): строки зависят от дивиденда
            memo = None
        if (memo is not None and lam is not None and year != p.guidance_year and p.link_base != "iea"
                and not p.opex_w_bal):
            slot = (lam, id(top_up)) if top_up else lam
            same = memo.get(slot)
        if same is None:
            E = dict(E0)
            if year == p.guidance_year:
                if not st.guid or st.guid.get("_year") != year:
                    st.guid = dict(self.guidance_multipliers(st, q))
                    st.guid["_year"] = year
                for b in roles.loans:
                    E[b] = E0[b] * st.guid[books[b]["cor_segment"]]
            elif lam is not None:
                # доля λ — одна на все кредитные книги с положительным потенциальным приростом; книга без него
                # идёт по потенциальному пути при любой λ (М§4.13.1)
                fac = self.growth_factors(year)
                for b in roles.loans:
                    E[b] = E0[b] * fac[b] if lam == 1.0 or fac[b] <= 1.0 else E0[b] * (1 + lam * (fac[b] - 1))
                if top_up:
                    for b, add in top_up.items():
                        E[b] += add
            else:
                for b in roles.loans:
                    E[b] = E0[b] * (1 + self.loan_growth(b, year)) ** QUARTER_YEARS
            side = memo.get(FUNDS_SIDE) if slot is not None else None
            if side is None:
                n_q = parse_period(tl.period(q))[1] if p.funds_drift_q else None
                FR = st.FR * (1 + self.funds_growth("retail", year, n_q)) ** QUARTER_YEARS
                gc = (1 + self.funds_growth("corporate", year, n_q)) ** QUARTER_YEARS
                for b in roles.corp_funds:
                    E[b] = E0[b] * gc
                c_star = current_share_target(key, p.c_ref, p.psi, p.key_ref, p.c_bounds)
                c = st.c + p.c_rho * (c_star - st.c)
                rc, rt = roles.retail
                E[rc], E[rt] = c * FR, (1 - c) * FR
                if p.driven is not None:            # книги-обязательства за драйвером строки (К6, М§4.3)
                    self.drive(E0, E, q)
                funds = FR + sum([E[b] for b in roles.corp_funds])
                # база структурного опта К3 — средства клиентов (Р11-2: при funds_scope: clients — без книг К6)
                wh_base = p.wh_to_funds * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))
                if slot is not None:
                    memo[FUNDS_SIDE] = (FR, c, funds, wh_base, {b: E[b] for b in roles.funds})
            else:
                FR, c, funds, wh_base, books_side = side
                E.update(books_side)
                if p.driven is not None:            # ведомые книги зависят от доли прироста: вне памяти стороны средств
                    self.drive(E0, E, q)
                    funds = FR + sum([E[b] for b in roles.corp_funds])
                    wh_base = p.wh_to_funds * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))
            loans = sum([E[b] for b in roles.loans])
            fv = E[p.fv_book] * p.fv_share if p.fv_book else 0.0
            loans_ac = loans - fv
            OA, OL, AL = p.oa_ratio * loans, p.ol_ratio * loans, p.allowance_ratio * loans_ac
            if p.cash is not None:              # деньги за своим драйвером, растущая часть — без денег (К8, М§4.3)
                cash = self.cash_end(E, q)
                if p.cash.rho_q is None:
                    OA = p.cash.rho * loans + cash
                else:                           # растущая часть без денег идёт за путём доли денег (Р6-1)
                    OA = p.cash.rho_q[q] * loans + cash
            if p.allow_cov is not None:
                AL = allowance_of(p, E, fv, loans_ac)    # резерв по книгам: покрытие якоря × книга (К7, М§4.6)
            if p.oa_fixed:
                OA += p.oa_fixed                    # постоянная часть не растёт с кредитами (М§4.3)
        else:
            (_, E, FR, c, loans, fv, loans_ac, funds, wh_base, OA, OL, AL, avg, fv_avg, ac_avg, llp, fvc, vol,
             fees, opex, ins) = same[:21]
            E, avg = dict(E), dict(avg)
            vol_c = same[21] if p.opex_w is not None else None
            if p.cash is not None:
                cash = self.cash_end(E, q)      # деньги — от тех же остатков, что OA записи памяти (К8)
        # слово funds баз строк (Р11-2): при funds_scope: clients — средства клиентов без книг К6; иначе — ряд funds
        funds_w = funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp])
        # 3. ставки книг
        if rates is not None:
            rate = rates
        else:
            rate = dict(st.rate)
            phi, phi_l = p.phi_assets, p.phi_liab
            for b in roles.names:
                spec = books[b]
                ref = w.ref(spec["ref"])[q]
                s = p.spreads[b][q]
                rho = float(spec["rho"])
                if b in p.phi_share:            # Р11-1: доля сжатия книги между мирами (в мире-опоре H — ноль)
                    s -= p.phi_share[b] * (ref - self.wh.ref(spec["ref"])[q])
                if spec["side"] == "asset":
                    if spec.get("phi"):
                        s -= phi * (ref - self.wh.ref(spec["ref"])[q])
                    rate[b] = st.rate[b] + rho * (ref + s - st.rate[b])
                else:
                    if phi_l and spec.get("phi"):
                        s += phi_l * self.x_w[q]
                    rate[b] = st.rate[b] + rho * (float(spec["beta"]) * ref + s - st.rate[b])
        # 4. предварительный баланс при BV_(q−1); выплата объявленного в том же квартале — сразу
        pay = st.pay.get(q, 0.0)
        if parts is not None:
            pay += sum(a for a, part_pay, _ in parts if part_pay == q)
        else:
            pq = (pay_q if pay_q is not None else q) if div_decl else None
            if div_decl and pq == q:
                pay += div_decl
        DP = st.DP + div_decl - pay
        nonbal_assets = loans - AL + OA
        fixed_liab = funds + OL + DP + p.af.at1 + p.af.nci
        la_min = p.liquid_min * nonbal_assets / (1 - p.liquid_min)
        la_pre = fixed_liab + wh_base + (st.BV - div_decl) - nonbal_assets
        bb = self.bb_q
        if bb:
            la_pre -= bb                        # деньги выкупа уходят из группы в квартале покупки (М§5.6)
        extra_pre = max(0.0, la_min - la_pre)
        la_pre += extra_pre
        sec_pre = p.sec_share * la_pre
        liq_pre = la_pre - sec_pre
        wh_pre = wh_base + extra_pre
        # 5. ОПУ
        if same is None:
            avg = {}
            for b in roles.names:
                avg[b] = (E0[b] + E[b]) / 2
            kept_avg = dict(avg) if slot is not None else None
        avg[SECURITIES] = (E0[SECURITIES] + sec_pre) / 2
        avg[LIQUIDITY] = (E0[LIQUIDITY] + liq_pre) / 2
        avg[WHOLESALE] = (E0[WHOLESALE] + wh_pre) / 2
        income = sum(rate[b] * avg[b] for b in roles.assets) * dt
        expense = sum([rate[b] * avg[b] for b in roles.liabilities]) * dt
        fr_avg = (st.FR + FR) / 2
        dia = p.dia * fr_avg * dt
        iea_avg = sum([avg[b] for b in roles.assets])
        ov = (self.nim_shift[q] + self.d_nim[q]) * iea_avg * dt
        nii = income - expense - dia + ov
        flows = self.flows
        if same is None:
            fv0 = E0[p.fv_book] * p.fv_share if p.fv_book else 0.0
            fv_avg = (fv0 + fv) / 2
            ac_avg = sum([avg[b] for b in roles.loans]) - fv_avg
            cor = self.cor[q]
            if p.book_rel is not None:
                # множители по книгам (М§4.6): CoR книги — r̂_b × CoR клетки (путь, κ-добавка, δ A-P2u)
                llp = 0.0
                for b in roles.loans:
                    part = avg[b] - (fv_avg if b == p.fv_book else 0.0)
                    llp += cor * p.book_rel[b] * part * dt
                r_fv = p.book_rel[p.fv_book] if p.fv_book else 0.0
                cor_corp, ref_corp = cor * r_fv, self.cor_ref[q] * r_fv
            elif self.seg_mult is None:
                llp = cor * ac_avg * dt
                cor_corp, ref_corp = cor, self.cor_ref[q]
            else:
                llp = 0.0
                for b in roles.loans:
                    seg = books[b]["cor_segment"]
                    part = avg[b] - (fv_avg if b == p.fv_book else 0.0)
                    llp += cor * self.seg_mult[seg] * part * dt
                cor_corp = cor * self.seg_mult["corporate"]
                ref_corp = self.cor_ref[q] * self.seg_mult["corporate"]
            fvc = fvc_amount(p.fv_factor, cor_corp, ref_corp, fv_avg, dt)
            gvw = p.fees_override.get(year)
            mult_f = p.root_mult and gvw is None    # Р5-6: корень комиссий множителем (в году переопределения его нет)
            g_fees = gvw if gvw is not None else (wage if mult_f else wage + p.fees_gvw[q])
            vol = None
            if p.link_base:
                # рост объёма г/г: средний остаток базы квартала к тому же кварталу прошлого года (М§4.7)
                if p.link_base == "iea":
                    vol = iea_avg
                elif p.link_base == "funds":
                    vol = (st.FR + sum(E0[b] for b in (roles.corp_funds if p.wh_corp is None else p.wh_corp))
                           + funds_w) / 2
                else:
                    vol = (sum(E0[b] for b in roles.loans) + loans) / 2
                flows["vol"][q] = vol
                v_ex = vol / flows["vol"][q - 4] - 1 - wage      # превышение роста объёма над ростом зарплат
                if gvw is None and p.link_fees:
                    g_fees += p.link_fees * v_ex
            if p.fees_line is not None:             # база комиссий по своему ключу (К2, М§4.7)
                a_f = self.line_avg(p.fees_line, "vol_fees", q, st, E0, loans, funds_w, iea_avg, avg)
                if gvw is None and p.link_fees and mult_f:
                    g_fees = wage + p.link_fees * (a_f / flows["vol_fees"][q - 4] - 1 - wage)
                elif gvw is None and p.link_fees:
                    g_fees = wage + p.fees_gvw[q] + p.link_fees * (a_f / flows["vol_fees"][q - 4] - 1 - wage)
            if p.ins_line is not None:              # база страхования по своему ключу (К2)
                self.line_avg(p.ins_line, "vol_ins", q, st, E0, loans, funds_w, iea_avg, avg)
            if mult_f:                              # Р5-6: (1 + рост базы)(1 + корень)
                fees = flows["fees"][q - 4] * (1 + g_fees) * (1 + p.fees_gvw[q])
            else:
                fees = flows["fees"][q - 4] * (1 + g_fees)
            vol_c = None
            if p.opex_w is not None:
                # база расходов по себестоимости книг (М§4.7): средние книг квартала, балансирующие — как в ЧПД
                vol_c = sum(w_b * avg[b] for b, w_b in p.opex_w.items())
                flows["vol_opex"][q] = vol_c
                v_ex_c = vol_c / flows["vol_opex"][q - 4] - 1 - wage
                opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex_c) * (1 + p.opex_real[q])
            elif p.link_opex:
                opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex) * (1 + p.opex_real[q])
            else:
                opex = flows["opex"][q - 4] * (1 + wage) * (1 + p.opex_real[q])
            if p.root_mult and p.link_ins:          # Р5-6: корень страхования множителем
                ins = flows["ins"][q - 4] * (1 + wage + p.link_ins * v_ex) * (1 + p.ins_gvw[q])
            elif p.root_mult:
                ins = flows["ins"][q - 4] * (1 + wage) * (1 + p.ins_gvw[q])
            elif p.link_ins:
                ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q] + p.link_ins * v_ex)
            else:
                ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q])
            if p.line_shares is not None:           # смесь базы расходов: доли на базах строк (К2, М§4.7)
                a_c = p.mix_keep * (vol_c if p.opex_w is not None else vol)
                for line, share in p.line_shares.items():
                    src, a0 = p.mix_src[line]
                    nom = None if p.share_nominal is None else p.share_nominal.get(line)
                    if nom is None:
                        a_c += share * p.mix_b0 * flows[src][q] / a0
                    elif p.link_line:               # Р10-5: франшиза формой строки — Φ г/г за связью λ с корнем κ
                        lam_l, kap_l, phi_name = nom
                        phi = flows[phi_name][q - 4] * link_growth(flows[src][q] / flows[src][q - 4], wage, lam_l,
                                                                   kap_l[q], p.root_mult)
                        flows[phi_name][q] = phi
                        a_c += share * p.mix_b0 * phi
                    else:                           # Р8-6: λ — за базой строки, 1 − λ — номинал мира с корнем κ
                        lam_l, kap_l, nom_name = nom
                        h_nom = flows[nom_name][q - 4] * (1 + wage) * (1 + kap_l[q])
                        flows[nom_name][q] = h_nom
                        a_c += share * p.mix_b0 * flows[src][q] / a0 * lam_l + share * p.mix_b0 * (1 - lam_l) * h_nom
                flows["vol_mix"][q] = a_c
                v_ex_m = a_c / flows["vol_mix"][q - 4] - 1 - wage
                opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex_m) * (1 + p.opex_real[q])
            if p.ins_line is not None and p.link_ins:
                v_ex_i = flows["vol_ins"][q] / flows["vol_ins"][q - 4] - 1 - wage
                if p.root_mult:
                    ins = flows["ins"][q - 4] * (1 + wage + p.link_ins * v_ex_i) * (1 + p.ins_gvw[q])
                else:
                    ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q] + p.link_ins * v_ex_i)
            if slot is not None and p.line_flows:
                memo[(slot, LINES)] = {name: flows[name][q] for name in p.line_flows}
            if slot is not None:
                # балансирующие книги в записи — ещё как до шага: их остатки и средние у каждой оценки свои
                memo[slot] = (top_up, dict(E), FR, c, loans, fv, loans_ac, funds, wh_base, OA, OL, AL, kept_avg,
                              fv_avg, ac_avg, llp, fvc, vol, fees, opex, ins) + ((vol_c,) if p.opex_w is not None else ())
        elif vol is not None:
            flows["vol"][q] = vol
        if same is not None and vol_c is not None:
            flows["vol_opex"][q] = vol_c
        if same is not None and p.line_flows:
            for name, value in memo[(slot, LINES)].items():
                flows[name][q] = value
        idx = w.price_index[q]
        noncore = p.noncore_q[year] * idx
        misc = p.misc_q[(year, h)] * idx
        tenor = w.ofz[p.fvoci_tenor]
        dy = tenor[q] - (tenor[q - 1] if q > 1 else p.y_tenor0)
        fvr = -p.fvtpl_duration * dy * p.fvtpl_share * avg[SECURITIES] if p.fvr_on else 0.0
        one_off = self.rg.one_off_amount if q == self.rg.one_off_q else 0.0
        pbt = nii - llp - fvc + fees + ins + misc + fvr + noncore - opex + one_off
        tau_s = p.tau_stat[year]
        tau_e = tau_s + p.tax_gap
        tax = tau_e * pbt
        ot = p.ot_amount if q == p.ot_q else 0.0
        ni = pbt - tax - ot
        # доля неконтролирующих (pnl.nci_share) или, при pnl.nci_real (Р11-3), рубли якоря × индекс цен мира
        ni_sh = ni * (1 - p.nci_share) if p.nci_q is None else ni - p.nci_q[(year, h)] * idx
        # 6. капитал
        fvoci_avg = p.fvoci_share * avg[SECURITIES]
        R = st.R * (1 - QUARTER_YEARS / p.fvoci_maturity) - p.fvoci_duration * dy * fvoci_avg * (1 - tau_s)
        oci = R - st.R
        cpn = p.coupon_annual if h == p.coupon_quarter else 0.0
        om = p.other_movements[q]
        ci = ni_sh - cpn * (1 - tau_s) + oci + om
        BV = st.BV + ci - div_decl
        if bb:
            BV -= bb                            # выкуп — распределение акционерам, не совокупный доход (М§5.6)
        # 7. окончательный баланс при BV_q
        la = fixed_liab + wh_base + BV - nonbal_assets
        extra = max(0.0, la_min - la)
        la += extra
        E[SECURITIES] = p.sec_share * la
        E[LIQUIDITY] = la - E[SECURITIES]
        E[WHOLESALE] = wh_base + extra
        assets = loans - AL + E[SECURITIES] + E[LIQUIDITY] + OA
        liab_eq = funds + E[WHOLESALE] + OL + DP + BV + p.af.at1 + p.af.nci
        # 8. RWA и нормативы
        reg = st.reg
        if parts is not None:
            reg = reg + [(q, part_reg, a) for a, _, part_reg in parts if a]
        elif div_decl:
            reg = reg + [(q, reg_q if reg_q is not None else q, div_decl)]
        dpreg = dpreg_at(reg, q)
        back = after_audit_start(h, p.cap.audit_cutoffs)
        flows["ni_sh"][q] = ni_sh
        e_unaud = sum([flows["ni_sh"][q - j] for j in range(back + 1)])
        g_q = None if p.guar is None else self.guarantee(E, fees, q)       # RWA гарантий (К5, М§4.11)
        if p.cash is None:
            rwa = p.rwa_w.rwa(E, E[SECURITIES], E[LIQUIDITY], OA, p.dn[q], self.x[q], guar=g_q)   # кредитные книги — из E
        elif p.cash.shift_q is None:            # деньги со своей плотностью (К8, М§4.11)
            rwa = p.rwa_w.rwa(E, E[SECURITIES], E[LIQUIDITY], OA, p.dn[q], self.x[q], guar=g_q, cash=cash)
        else:                                   # и вытесненная часть прочих активов (Р6-1; та же строка у лёгкой оценки)
            rwa = p.rwa_w.rwa(E, E[SECURITIES], E[LIQUIDITY], OA, p.dn[q], self.x[q], guar=g_q, cash=cash,
                              cash_shift=p.cash.shift_q[q] * loans)
        if self.rg.rwa_mult is not None:
            rwa *= self.rg.rwa_mult[q]          # множитель режима — на всех RWA клетки (М§4.11)
        rt_ = ratios(p.cap, bv=BV, dpreg=dpreg, reserve=R, unaudited=e_unaud, t2=p.t2[q], rwa=rwa,
                     ded_pp20=self.sc.ded_pp20[q], ded_pp11=self.sc.ded_pp11[q])
        if light:
            return {"n20": rt_.n20, "n11": rt_.n11, "n11_star": rt_.n11_star, "rwa": rwa, "_rate": rate}
        # запись и переход
        flows["fees"][q], flows["opex"][q], flows["ins"][q] = fees, opex, ins
        st.E, st.rate, st.FR, st.c = E, rate, FR, c
        st.AL, st.OA, st.OL, st.DP, st.BV, st.R = AL, OA, OL, DP, BV, R
        st.reg, st.wh_extra, st.q = [entry for entry in reg if entry[1] > q], extra, q
        if parts is not None:
            for a, part_pay, _ in parts:
                if a and part_pay != q:
                    st.pay[part_pay] = st.pay.get(part_pay, 0.0) + a
        elif div_decl and pq != q:
            st.pay[pq] = st.pay.get(pq, 0.0) + div_decl
        income_base = nii + fees + ins + misc + fvr
        return {
            "bv": BV, "ni_sh": ni_sh, "ni": ni, "pbt": pbt, "nii": nii, "llp": llp, "fvc": fvc,
            "fees": fees, "opex": opex, "ins": ins, "misc": misc, "noncore": noncore, "fvr": fvr,
            "one_off": one_off, "tax": tax, "ot": ot, "oci": oci, "coupon": cpn, "om": om, "ci": ci,
            "div": div_decl, "dp": DP, "dpreg": dpreg, "pay": pay, "reserve": R,
            "rwa": rwa, "k20": rt_.k20, "k11": rt_.k11, "n20": rt_.n20, "n11": rt_.n11,
            "ded20": rt_.ded20, "ded11": rt_.ded11, "e_unaudited": e_unaud,
            "req20": self.sc.req20[q], "req11": self.sc.req11[q], "floor20": self.sc.floor20[q],
            "floor11": self.sc.floor11[q], "loans": loans, "loans_ac": loans_ac, "loans_fv": fv,
            "funds": funds, "funds_retail": FR, "iea": sum([E[b] for b in roles.assets]),
            "iea_avg": iea_avg, "loans_ac_avg": ac_avg, "loans_fv_avg": fv_avg, "assets": assets,
            "liabilities_equity": liab_eq, "securities": E[SECURITIES], "liquidity": E[LIQUIDITY],
            "wholesale": E[WHOLESALE], "wholesale_extra": extra, "other_assets": OA,
            "other_liabilities": OL, "allowance": AL, "current_share": c,
            "nim": nii / iea_avg / dt, "cor": llp / ac_avg / dt,
            "cir": opex / income_base if income_base else float("nan"),
            "roe_q": ci / st_bv_prev if (st_bv_prev := BV - ci + div_decl) else float("nan"),
            "k_q": 0.0, "key": key, "tau_stat": tau_s, "tau_eff": tau_e,
            "int_income": income, "int_expense": expense, "dia": dia, "overlay": ov,
            "la_headroom": max(0.0, la - p.liquid_min * assets),
            "_rate": rate, "_avg": avg, "_bal": E,
            "n11_star": rt_.n11_star,
            "lam": 1.0 if lam is None else lam, "catch_up": sum(top_up.values()) if top_up else 0.0,
            "loans_potential": loans, "req20_glide": self.req20g[q], "req11_glide": self.req11g[q],
            **({} if p.book_rel is None else {"cor_mix0": self.cor[q], "llp_mix0": self.cor[q] * ac_avg * dt}),
            **({} if p.opex_w is None and p.line_shares is None else {
                "vol_opex": vol_c if p.line_shares is None else flows["vol_mix"][q]}),
            **({} if p.fees_line is None else {"vol_fees": flows["vol_fees"][q]}),
            **({} if p.ins_line is None else {"vol_ins": flows["vol_ins"][q]}),
            **({} if p.share_nominal is None else {nom[2]: flows[nom[2]][q] for nom in p.share_nominal.values()}),
            **({} if p.driver_roots is None or p.k6_line is not None else self.driver_ends(E, q)),
            **({} if p.k6_line is None else self.k6_line_rows(E, q)),
            **({} if p.bb is None else {"bb": bb}),
            **({} if g_q is None else {"rwa_guar": g_q * p.dn[q] * self.x[q] * (
                1.0 if self.rg.rwa_mult is None else self.rg.rwa_mult[q])}),
            **({} if p.cash is None else {"cash": cash}),
        }

    # ------------------------------------------------------------ стационарные ставки книг (К4, М§7)
    def target_rates(self, q: int) -> dict[str, float]:
        """Цели ставок книг квартала q — ставки при ρ = 1 (М§4.4): актив ref_W + s − φ_A (ref_W − ref_H) у книг Φ_A,
        пассив β ref_W + s + φ_L X_W у пассивов с phi; у книги с долей сжатия (Р11-1) — ещё − share (ref_W − ref_H). То
        же выражение, что подстройка ставки в шаге."""
        p, w = self.p, self.w
        out = {}
        for b in p.roles.names:
            spec = p.books[b]
            ref = w.ref(spec["ref"])[q]
            s = p.spreads[b][q]
            if b in p.phi_share:                # Р11-1
                s -= p.phi_share[b] * (ref - self.wh.ref(spec["ref"])[q])
            if spec["side"] == "asset":
                if spec.get("phi"):
                    s -= p.phi_assets * (ref - self.wh.ref(spec["ref"])[q])
                out[b] = ref + s
            else:
                if p.phi_liab and spec.get("phi"):
                    s += p.phi_liab * self.x_w[q]
                out[b] = float(spec["beta"]) * ref + s
        return out

    # ------------------------------------------------------------ базы строк и RWA гарантий (К2, К5)
    def line_avg(self, lb: LineBase, key: str, q: int, st: State, E0: Mapping[str, float], loans: float, funds: float,
                 iea_avg: float, avg: Mapping[str, float]) -> float:
        """A^ℓ_q — средний остаток базы строки за квартал q (К2, М§4.7), пишется в ряд `key`: кредиты и средства —
        полусумма концов (как база link_base), процентные активы — ĪEA шага, книги — Σ ω Ē (балансирующие — средние
        ЧПД), номинал — A^N_q = A^N_(q−4) (1 + wage_W,q). Средний остаток не больше нуля — отказ с меткой клетки."""
        roles, flows = self.p.roles, self.flows
        if lb.kind == "loans":
            got = (sum(E0[b] for b in roles.loans) + loans) / 2
        elif lb.kind == "funds":                # Р11-2: при funds_scope: clients — без книг К6 (`funds` — их конец)
            got = (st.FR + sum(E0[b] for b in (roles.corp_funds if self.p.wh_corp is None else self.p.wh_corp))
                   + funds) / 2
        elif lb.kind == "iea":
            got = iea_avg
        elif lb.kind == "nominal":
            got = flows[key][q - 4] * (1 + self.w.wage[q])
        else:
            got = sum([w * avg[b] for b, w in lb.weights.items()])
        if not (got > 0 and flows[key][q - 4] > 0):
            raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: средний остаток базы строки ({key}) за "
                            f"{self.tl.period(q)} или год назад не больше нуля — рост строки не определён (М§4.7)")
        flows[key][q] = got
        return got

    def drive(self, E0: Mapping[str, float], E: dict[str, float], q: int) -> None:
        """Книги-обязательства за драйвером строки (К6, М§4.3): E_b,q = E_b,q−1 (1 + wage_W,q)^((1 − λ)/4) (D_q /
        D_q−1)^λ — λ — связь строки, D — уровень базы строки на концах кварталов (кредиты, номинал или книги вне
        балансирующих; база готова раньше: кредитные книги и средства физлиц квартала уже посчитаны). При ключе
        `volumes.liability_driver_roots` (Р9-1) номинальная часть несёт корень строки-драйвера: × (1 + ρ_q)^(1 − λ) —
        отдельным множителем после прежней строки (при λ = 1 и ρ = 0 множитель ровно 1).

        При `volumes.line_link_form: line` (Р10-5, проход ядра 8) — форма строки: индекс строки-драйвера на концах
        Ψ_q = Ψ_(q−4) × g(D_q / D_(q−4), w_q, λ, ρ_q) (`link_growth`; D_(q−4) — внутренний ряд лага, Ψ — ряд клетки),
        E_b,q = E_b,0 × Ψ_q у каждой ведомой книги строки; цепь «квартал к кварталу» не считается."""
        wage = self.w.wage[q]
        p = self.p
        if p.k6_line is not None:               # Р10-5: книги К6 формой строки — Ψ г/г на концах кварталов
            flows, psi = self.flows, {}
            for line, (lam, rho, lb) in p.k6_line.items():
                d_now, d_back = self.base_end(lb, E, q), flows[LAG_END_FLOWS[line]][q - 4]
                if not (d_now > 0 and d_back > 0):
                    raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: уровень базы строки {line} "
                                    f"(драйвер книг К6) за {self.tl.period(q)} или год назад не больше нуля (Р10-5, М§4.3)")
                psi[line] = flows[PSI_FLOWS[line]][q - 4] * link_growth(d_now / d_back, wage, lam, rho[q], p.root_mult)
                flows[LAG_END_FLOWS[line]][q] = d_now
                flows[PSI_FLOWS[line]][q] = psi[line]
            for b in p.driven:
                E[b] = p.af.balances[b] * psi[p.k6_books[b]]
            return
        roots = p.driver_roots
        for b, (lb, lam) in p.driven.items():
            d_now, d_prev = self.base_end(lb, E, q), self.base_end(lb, E0, q - 1)
            if not (d_now > 0 and d_prev > 0):
                raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: уровень драйвера книги {b} за "
                                f"{self.tl.period(q)} или квартал раньше не больше нуля (М§4.3)")
            E[b] = E0[b] * (1 + wage) ** ((1 - lam) * QUARTER_YEARS) * (d_now / d_prev) ** lam
            if roots is not None and b in roots:    # Р9-1: корень номинальной части книги К6
                E[b] *= (1 + roots[b][1][q]) ** (1 - lam)

    def driver_ends(self, E: Mapping[str, float], q: int) -> dict[str, float]:
        """Ряды клетки vol_end_<строка> (Р9-1): D^ℓ_q — уровень базы строки-драйвера книг К6 с корнем на конец квартала
        q (`base_end` на принятых остатках квартала) — то, что читает правило ρ листа вывода."""
        p = self.p
        return {END_FLOWS[line]: self.base_end(p.driven[b][0], E, q) for b, (line, _) in p.driver_roots.items()}

    def k6_line_rows(self, E: Mapping[str, float], q: int) -> dict[str, float]:
        """Ряды клетки книг К6 формой строки (Р10-5): vol_psi_<строка> — индекс Ψ^ℓ_q, vol_end_<строка> — D^ℓ_q, уровень
        базы строки на конец квартала по принятым остаткам (`base_end`) — то, что читает правило ρ листа вывода."""
        p = self.p
        out = {PSI_FLOWS[line]: self.flows[PSI_FLOWS[line]][q] for line in p.k6_line}
        out.update({END_FLOWS[line]: self.base_end(v[2], E, q) for line, v in p.k6_line.items()})
        return out

    def nominal_end(self, q: int) -> float:
        """Номинал на конец квартала (база строки `nominal`, К2): D^N_q = D^N_(q−1) (1 + wage_W,q)^(1/4), D^N_0 = 1."""
        got = self._nominal
        if got is None:
            wage, acc, out = self.w.wage, 1.0, [1.0]
            for x in range(1, self.tl.Q + 1):
                acc *= (1 + wage[x]) ** QUARTER_YEARS
                out.append(acc)
            got = self._nominal = tuple(out)
        return got[q]

    def base_end(self, lb: LineBase, E: Mapping[str, float], q: int) -> float:
        """D^ℓ_q — уровень базы строки на конец квартала q (К2): кредиты, средства клиентов, процентные активы
        конечного баланса, Σ ω E книг или номинал."""
        roles = self.p.roles
        if lb.kind == "loans":
            return sum([E[b] for b in roles.loans])
        if lb.kind == "funds":                  # Р11-2: при funds_scope: clients — без книг К6
            return sum([E[b] for b in (roles.funds if self.p.funds_words is None else self.p.funds_words)])
        if lb.kind == "iea":
            return sum([E[b] for b in roles.assets])
        if lb.kind == "nominal":
            return self.nominal_end(q)
        return sum([w * E[b] for b, w in lb.weights.items()])

    def cash_end(self, E: Mapping[str, float], q: int) -> float:
        """C_q = c D_q — неработающие деньги на конец квартала q за уровнем драйвера на конец квартала (К8, М§4.3):
        средства клиентов (с ведомыми книгами К6), кредиты или веса книг — остатки квартала, уже посчитанные шагом.
        Уровень драйвера не больше нуля — отказ с меткой клетки и кварталом."""
        d = self.base_end(self.p.cash.base, E, q)
        if not d > 0:
            raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: уровень драйвера неработающих денег за "
                            f"{self.tl.period(q)} {d:g} не больше нуля (К8, М§4.3)")
        if self.p.cash.share_q is None:
            return self.p.cash.share * d
        return self.p.cash.share_q[q] * d    # доля пути квартала q (Р6-1)

    def guarantee(self, E: Mapping[str, float], fees: float, q: int) -> float:
        """G_q = G_0 × D^G_q / D^G_0 (К5, М§4.11): драйвер — уровень базы на конец квартала (`fees_base` — база
        комиссий, `fees_component` — база компоненты смеси, Р5-5) или комиссии четырёх кварталов по квартал q
        включительно (`fees_line`; кварталы до якоря — факт). Уровень драйвера не больше нуля — отказ с меткой клетки
        и кварталом."""
        gd, flows = self.p.guar, self.flows
        if gd.driver in GUARANTEE_LEVEL_DRIVERS:
            d = self.base_end(gd.base, E, q)
        else:
            d = fees + flows["fees"][q - 1] + flows["fees"][q - 2] + flows["fees"][q - 3]
        if not d > 0:
            raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: уровень драйвера RWA гарантий за "
                            f"{self.tl.period(q)} {d:g} не больше нуля (М§4.11)")
        return gd.g0 * d / gd.d0

    # ------------------------------------------------------------ год Y: решение о дивиденде
    def year_base(self, year: int) -> float:
        p, tl = self.p, self.tl
        qs = tl.quarters_of_year(year)
        ni = 0.0
        for q in qs:
            if q not in self.flows["ni_sh"]:
                raise FactsError(f"нет ЧП акционерам за {tl.period(q)} для базы выплаты {year}")
            ni += self.flows["ni_sh"][q]
        cpn = sum(p.coupon_annual for q in qs if self.hs.get(q, tl.h(q)) == p.coupon_quarter)
        return base_of_year(ni, cpn, p.tau_stat[year], p.policy.deduct_at1_after_tax)

    def trial(self, st: State, q_a: int, year: int) -> list[Checkpoint]:
        """Пробный проход q_A … последняя точка проверки с Div_Y = 0 (М§5.3 п. 1)."""
        p, tl = self.p, self.tl
        pay_year = year + 1
        cps = [tl.index(period_str(pay_year, h)) for h in p.policy.checkpoints]
        cps = sorted(c for c in cps if c >= q_a)
        last = min(max(cps) if cps else tl.Q, tl.Q)
        cps = [c for c in cps if c <= tl.Q] or [last]
        trial_state = st.clone()
        saved = {k: dict(v) for k, v in self.flows.items() if k in STEP_FLOWS}
        out = []
        for qq in range(q_a, last + 1):
            row = self.step(trial_state, qq, 0.0)
            if qq in cps:
                out.append(Checkpoint(n20=row["n20"], n11=row["n11"], rwa=row["rwa"],
                                      floor20=row["floor20"], req11=row["req11"]))
        for k, v in saved.items():
            self.flows[k] = v
        return out

    # ------------------------------------------------------------ квартальный календарь (М§5.7)
    def quarter_base(self, idx: int) -> float:
        """База дивиденда за квартал прибыли с номером `idx`: средняя по окну W последних кварталов прибыли
        акционеров (за вычетом купона бессрочных инструментов после налога, если политика его вычитает);
        кварталы не позже якоря — факт, позже — ряд клетки (М§5.7.3)."""
        p, tl = self.p, self.tl
        pol, ni = p.policy, self.flows["ni_sh"]
        window = range(idx - pol.window + 1, idx + 1)
        total = 0.0
        for x in window:
            if x not in ni:
                raise FactsError(f"нет прибыли акционеров за {tl.period(x)} для базы дивиденда за "
                                 f"{tl.period(idx)} (М§5.7.3)")
            total += ni[x]
            if pol.deduct_at1_after_tax and tl.h(x) == p.coupon_quarter:
                total -= p.coupon_annual * (1 - p.tau_stat[tl.year(x)])
        return total / len(window)

    def probe(self, st: State, q: int, parts: tuple = ()) -> dict[str, float]:
        """Оценка шага квартала q на копии состояния, без записи (приём пробного прохода): состояние и ряды
        клетки остаются как до оценки. `parts` — дивиденды квартала, с которыми считается оценка."""
        row = self.step(st.clone(), q, sum(a for a, _, _ in parts), parts=parts)
        for name in STEP_FLOWS:
            if name in self.flows:
                self.flows[name].pop(q, None)
        return row

    def quarter_room(self, st: State, q: int, reg_parts: tuple) -> tuple[float, float]:
        """Запас капитала квартала q под решения модели без ограничения роста (М§5.7.4 п. 4) — пара
        (H_ref, H_fin): оценка шага с записями реестра и без решений модели, одна точка — конец квартала,
        отчётные нормативы против требований; без ограничения роста оба запаса равны. При ограничении роста
        запасы меряет `quarter_constrained` (М§4.13.2): по требованию с глиссадой и Н20.1 с прибылью периода."""
        p = self.p
        row = self.probe(st, q, reg_parts)
        point = Checkpoint(n20=row["n20"], n11=row["n11"], rwa=row["rwa"], floor20=row["floor20"],
                           req11=row["req11"])
        room = headroom((point,), p.policy.steps[0].threshold, p.cap.buffer20)
        return room, room

    def run_quarterly(self, last: int) -> tuple[list[dict], list[Decision], State]:
        """Проход при квартальном календаре (М§5.7.4): в квартале q — записи реестра и решения модели за
        открытые кварталы прибыли с этим кварталом решения; квартал считается один раз с суммой дивидендов."""
        p = self.p
        pol, cal = p.policy, p.calendar
        st = initial_state(p)
        rows: list[dict] = []
        decisions: list[Decision] = []
        shock_year = self.rg.shock_year
        for q in range(1, last + 1):
            n_q = p_bar = None
            if p.bb is not None:                # выкуп квартала — до решений: они на акциях клетки (М§5.6)
                p_bar, n_q = self.buyback_quarter(st, q)
            due = cal.by_q.get(q)
            if not due:
                row = self.step(st, q, 0.0)
                row["div_model"] = 0.0
                if n_q is not None:
                    self.buyback_after(st, row, q, p_bar, n_q)
                rows.append(row)
                continue
            shock = shock_year is not None and self.years[q] == shock_year
            bases = [self.quarter_base(o.idx) for o in due]
            room = final = float("inf")
            n_dec = pol.n_out if n_q is None else n_q
            if any(o.dps is None for o in due) and not (shock and pol.skip_in_shock):
                reg_parts = tuple((o.dps * n_dec / THOUSAND, o.q_pay, o.q_reg) for o in due if o.dps is not None)
                room, final = self.quarter_room(st, q, reg_parts)
            decs = decide_quarter(pol, q=q, due=due, bases=bases, headroom=room, headroom_final=final,
                                  deferred=st.D, shock=shock, n_out=n_q)
            st.D = decs[-1].deferred_after
            decisions.extend(decs)
            parts = tuple((d.div, o.q_pay, o.q_reg) for d, o in zip(decs, due))
            row = self.step(st, q, sum(d.div for d in decs), parts=parts)
            row["div_model"] = sum(d.div for d in decs if d.source != "register")
            if n_q is not None:
                self.buyback_after(st, row, q, p_bar, n_q)
            rows.append(row)
        return rows, decisions, st

    # ------------------------------------------------------------ выкуп по цене мира (М§5.6)
    def buyback_quarter(self, st: State, q: int) -> tuple[float, float]:
        """Выкуп квартала q до решений о дивиденде (М§5.6): сумма B_q (в год шока режима при skip_in_shock_year —
        ноль), цена покупок P̄_q — закрытые к дате книги кварталы по рынку (closed_prices или цена книги), квартал даты
        книги и позже — форвард с середины квартала P⁺_(q−1)(1 + k_b,q / 2), правило market — цена книги; акции клетки
        на конец квартала N_c,q = N_c,q−1 − 1000 B_q / P̄_q. Сумма квартала остаётся в клетке для шага (`bb_q`)."""
        bb, tl = self.p.bb, self.tl
        if st.p_plus is None:
            st.p_plus = self.p_start            # P⁺ до квартала даты книги — начало форварда P_s
        b = bb.amount[q]
        if bb.skip and self.rg.shock_year is not None and self.years[q] == self.rg.shock_year:
            b = 0.0
        if bb.rule == MARKET:
            p_bar = bb.p_book
        elif q < bb.qb:
            p_bar = bb.closed.get(q, bb.p_book)
        else:
            p_bar = st.p_plus * (1 + bb.disc[self.world].k[q] / 2)
        label = f"{self.world}/{self.regime}/{self.scenario}"
        if b and not p_bar > 0:                 # цена читается только в квартале покупок
            raise BookError(f"клетка {label}: цена выкупа за {tl.period(q)} {p_bar:.6g} ₽ — не больше нуля (М§5.6)")
        n_out = st.n_out - THOUSAND * b / p_bar
        if not n_out > 0:
            raise BookError(f"клетка {label}: акций в обращении после выкупа за {tl.period(q)} не осталось (М§5.6)")
        self.bb_q = b
        return p_bar, n_out

    def buyback_after(self, st: State, row: dict, q: int, p_bar: float, n_out: float) -> None:
        """После шага квартала q (М§5.6): акции клетки, дивиденд на внешнюю акцию d_q = Div_q × 1000 / N_c,q и форвард
        цены P⁺_q = P⁺_(q−1)(1 + k_b,q) − d_q − d^R_q (с квартала даты книги; у правила market — цена книги)."""
        bb = self.p.bb
        d_ext = row["div"] * THOUSAND / n_out
        if bb.rule != MARKET and q >= bb.qb:
            st.p_plus = st.p_plus * (1 + bb.disc[self.world].k[q]) - d_ext - bb.bridge_dps.get(q, 0.0)
        st.n_out = n_out
        row.update(n_out=n_out, p_bar=p_bar, p_plus=st.p_plus, d_ext=d_ext)
        self.bb_q = 0.0

    def fresh_flows(self) -> None:
        """Ряды «к тому же кварталу» и прибыль — с фактов (q ≤ 0), без рядов прохода (повтор прохода клетки)."""
        p = self.p
        self.flows = {k: dict(v) for k, v in p.hist.items()}
        if p.link_base:
            self.flows["vol"] = dict(p.hist_vol)
        if p.opex_w is not None:
            self.flows["vol_opex"] = dict(p.hist_vol_opex)
        self.line_flows()
        self.dps_year = {}                      # память DPS по годам прибыли (жетон, К1) — с начала прохода

    def line_flows(self) -> None:
        """Ряды баз строк по своим ключам и смеси базы расходов — с фактов (К2, М§4.7): A^F_x, A^I_x, A^C_x, x ≤ 0; при
        ключе Р8-6 — и номинальная часть франшизы строки H^ℓ_x = A^ℓ_x / A^ℓ_0 (при форме строки, Р10-5, — Φ^ℓ_x с той же
        историей); при книгах К6 формой строки — уровень базы строки на концах фактов D^ℓ_x и Ψ^ℓ_x = D^ℓ_x / D^ℓ_0."""
        p = self.p
        if p.fees_line is not None:
            self.flows["vol_fees"] = dict(p.fees_line.hist)
        if p.ins_line is not None:
            self.flows["vol_ins"] = dict(p.ins_line.hist)
        if p.line_shares is not None:
            self.flows["vol_mix"] = dict(p.hist_vol_mix)
        for name, hist in p.hist_share_nominal.items():     # Р8-6: номинальная часть франшизы строки H^ℓ_x, x ≤ 0
            self.flows[name] = dict(hist)
        for name, hist in p.hist_k6_line.items():           # Р10-5: D^ℓ_x и Ψ^ℓ_x книг К6 формой строки, x ≤ 0
            self.flows[name] = dict(hist)

    def book_date_price(self, rows: list[dict]) -> float:
        """S_c на дату книги (М§5.6, правило «цена = стоимость клетки»): оценка прохода дисконтом мира на дату книги."""
        p, bb = self.p, self.p.bb
        disc = bb.disc[self.world]
        inputs, _ = terminal_inputs(p, self, rows)
        if p.fixed_growth_share is None:
            term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple, k_t=disc.k_t,
                            symmetric=p.fade_symmetric, **terminal_keys(p))
        else:
            term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple, k_t=disc.k_t,
                            symmetric=p.fade_symmetric, lam_f=p.fixed_growth_share, parts=p.fixed_parts,
                            **terminal_keys(p))
        val = value_cell(q0=bb.qb, elapsed=bb.e_book, disc=disc, bv=(p.af.bv,) + tuple(r["bv"] for r in rows),
                         ci=(0.0,) + tuple(r["ci"] for r in rows), div=(0.0,) + tuple(r["div"] for r in rows),
                         term=term, bb=(0.0,) + tuple(r["bb"] for r in rows),
                         d_ext=(0.0,) + tuple(r["d_ext"] for r in rows), n_t=rows[-1]["n_out"], n_out=p.af.n_out)
        return val.s_price

    def run_cell_value(self) -> tuple[list[dict], list[Decision], State]:
        """Правило цены выкупа «стоимость клетки» (М§5.6, справочно): начало форварда P_s — неподвижная точка
        P_s = S_c(дата книги); с P_s = P_b до |ΔP_s| ≤ 1e-9 P_s, не больше 30 повторов прохода."""
        start = self.p.bb.p_book
        self.fixed_point = True
        try:
            for it in range(1, BB_MAX_ITER + 1):
                self.p_start, self.unsolved, self.bb_q = start, [], 0.0
                self.fresh_flows()
                rows, decisions, st = self.run()
                s = self.book_date_price(rows)
                if abs(s - start) <= BB_TOL * abs(start):
                    self.bb_iterations = it
                    return rows, decisions, st
                start = s
        finally:
            self.fixed_point = False
        raise BookError(f"клетка {self.world}/{self.regime}/{self.scenario}: цена выкупа «стоимость клетки» не сошлась "
                        f"за {BB_MAX_ITER} повторов прохода (М§5.6)")

    # ------------------------------------------------------------ жетон DPS (К1, М§4.13.2 п. 2а)
    def token_need(self, due: tuple, first: list, carrier: int, n_c: float):
        """Недостача года прибыли носителя до жетона (`model.dividends.token_need`): base_Y — сумма баз кварталов года
        (М§5.7.3: прибыль акционеров за вычетом купона AT1 после налога, если политика его вычитает; кварталы не
        позже якоря — факт), S_Y — DPS закрытых кварталов года, решений года в прошлых кварталах клетки (память
        `dps_year`) и базовые дивиденды решений года в этом квартале на акцию клетки."""
        p, tl = self.p, self.tl
        pol, ni = p.policy, self.flows["ni_sh"]
        year = due[carrier].year
        base_y = 0.0
        for x in tl.quarters_of_year(year):
            if x not in ni:
                raise FactsError(f"нет прибыли акционеров за {tl.period(x)} для жетона DPS {year} года (М§4.13.2)")
            base_y += ni[x]
            if pol.deduct_at1_after_tax and tl.h(x) == p.coupon_quarter:
                base_y -= p.coupon_annual * (1 - p.tau_stat[tl.year(x)])
        same = sum(d.base_div for d, o in zip(first, due) if o.year == year) * THOUSAND / n_c
        return token_need(min_dps=p.min_dps[year], base_year=base_y, n_iss=pol.n_iss, n_c=n_c,
                          closed_dps=p.calendar.closed_dps.get(year, 0.0), prior_dps=self.dps_year.get(year, 0.0),
                          same_dps=same)

    def floor_room(self, row: Mapping[str, float], q: int) -> float:
        """Запас над требованием без запаса менеджмента и без глиссады (К1): min_j (N_j − req⁰_j,q) × RWA; req⁰_20 =
        max(порог политики, пол Н20.0), req⁰_11 = пол Н20.1; N_11 — Н20.1 с прибылью периода (как у ограничения роста)."""
        sc, rwa = self.sc, row["rwa"]
        req20 = max(self.p.policy.steps[0].threshold, sc.floor20[q])
        return min((row["n20"] - req20) * rwa, (row["n11_star"] - sc.floor11[q]) * rwa)

    # ------------------------------------------------------------ рост, ограниченный капиталом (М§4.13)
    def evaluate(self, st: State, q: int, parts: tuple, lam: float,
                 extra: Mapping[str, float] | None = None, *, memo: dict | None = None, light: bool = False
                 ) -> tuple[dict[str, float], State | None, dict[str, float] | None]:
        """Оценка шага Ш(λ, c, D) (М§4.13.1): расчёт квартала q на копии состояния, без записи, — кредитные
        книги при доле прироста `lam` и навёрстывании `extra`, дивиденды квартала — `parts`. Возвращает строку
        квартала, состояние после шага и значения рядов-баз квартала: принятую оценку записывает `accept`.
        `memo` — память оценок этого квартала с состояния `st` (`step`). `light` — оценка только ради запаса
        капитала: в строке — нормативы и RWA, состояния и рядов-баз нет (None); записью шага она не бывает."""
        # оценка «только нормативы» состояние не пишет (кроме множителей года гайденса) — копия ей не нужна
        after = st if light and self.years[q] != self.p.guidance_year else st.clone()
        rates = self.rates.get(q)               # ставки книг квартала — одни на все его оценки
        row = self.step(after, q, sum([a for a, _, _ in parts]), parts=parts, lam=lam, top_up=extra, rates=rates,
                        memo=memo, light=light)
        if rates is None:
            self.rates[q] = row["_rate"]
        if light:
            for name in STEP_FLOWS:
                if name in self.flows:
                    self.flows[name].pop(q, None)
            return row, None, None
        kept = {name: self.flows[name].pop(q) for name in STEP_FLOWS if name in self.flows}
        return row, after, kept

    def accept(self, q: int, kept: Mapping[str, float]) -> None:
        """Запись принятой оценки шага: её ряды-базы квартала становятся рядами клетки."""
        for name, value in kept.items():
            self.flows[name][q] = value

    def room(self, row: Mapping[str, float], q: int) -> tuple[float, float]:
        """Запасы ограничения роста по оценке шага, млрд ₽ (М§4.13.1): H_j = (N_j − req*_j,q) × RWA. N_20 —
        отчётный Н20.0; N_11 — Н20.1 с прибылью периода («пила» неаудированной прибыли в ограничение не входит);
        требование — с глиссадой."""
        rwa = row["rwa"]
        return (row["n20"] - self.req20g[q]) * rwa, (row["n11_star"] - self.req11g[q]) * rwa

    def checked(self, st: State, q: int, parts: tuple, lam: float, *, memo: dict | None = None
                ) -> tuple[tuple, tuple[float, float], int]:
        """Полная оценка шага при доле прироста `lam` (М§4.13.2 п. 4): оценка, отклонения нормативов от требования
        φ_j = N_j − req*_j,q и номер связывающего норматива (при равенстве — Н20.0)."""
        done = self.evaluate(st, q, parts, lam, memo=memo)
        row = done[0]
        gaps = (row["n20"] - self.req20g[q], row["n11_star"] - self.req11g[q])
        return done, gaps, 0 if gaps[0] <= gaps[1] else 1

    def quarter_constrained(self, st: State, q: int, star: Mapping[str, float], n_out: float | None = None
                            ) -> tuple[dict[str, float], list[Decision], State]:
        """Квартал q при ограничении роста капиталом (М§4.13.2): дивиденд и доля прироста кредитных книг — вместе.
        `star` — уровни книг на потенциальном пути на конец q − 1. Возвращает строку квартала, решения и состояние
        на конец q; принятая оценка шага и есть его запись. `n_out` — акции клетки в квартале решения (выкуп,
        М§5.6)."""
        p, gr = self.p, self.p.growth
        pol, lam_min = p.policy, gr.lam_min
        due = p.calendar.by_q.get(q, ())
        in_shock = self.rg.shock_year == self.years[q]         # год шока отменяет решения модели квартала
        bases = [self.quarter_base(o.idx) for o in due]
        n_dec = pol.n_out if n_out is None else n_out
        reg_parts = tuple((o.dps * n_dec / THOUSAND, o.q_pay, o.q_reg) for o in due if o.dps is not None)
        fac = self.growth_factors(self.years[q])
        can_cut = lam_min < 1.0 and any(f > 1.0 for f in fac.values())
        memo: dict = {}                         # память оценок шага квартала: все они — с состояния `st`
        modelled = any(o.dps is None for o in due) and not (in_shock and pol.skip_in_shock)
        # При решениях модели оценки без них нужны ради запаса капитала — считаются только нормативы; записью
        # шага такая оценка становится, лишь когда все решения модели — ноль, и тогда считается заново (п. 7).
        probe = modelled
        # 1. оценка при полном росте
        full = self.evaluate(st, q, reg_parts, 1.0, memo=memo, light=probe)
        h_full = self.room(full[0], q)
        # 2. базовый дивиденд — в пределах запаса своего порядка
        low = h_low = None
        if modelled and gr.dividend_first and can_cut:
            low = self.evaluate(st, q, reg_parts, lam_min, memo=memo, light=probe)
            h_low = self.room(low[0], q)
        h_ref = min(h_full) if h_low is None else min(h_low)
        first = quarter_bases(pol, due=due, bases=bases, headroom=h_ref, shock=in_shock, payout=self.payout,
                              n_out=n_out).shares
        # 2а. жетон DPS (К1): недостача года прибыли носителя до жетона — если запас над требованием без запаса
        # менеджмента при наименьшей доле прироста её покрывает; раньше роста (рост урезается под жетон)
        token, tok = 0.0, {}
        if p.min_dps is not None and modelled:
            carrier = token_carrier(due, in_shock, pol)
            if carrier is not None:
                need = self.token_need(due, first, carrier, n_dec).need
                if need > 0:
                    if low is None and can_cut:
                        low = self.evaluate(st, q, reg_parts, lam_min, memo=memo, light=probe)
                        h_low = self.room(low[0], q)
                    floor_row = (low if can_cut else full)[0]
                    h_floor = self.floor_room(floor_row, q)
                    if h_floor >= sum(d.base_div for d in first if d.source == "model") + need:
                        token = need
                    tok = {"token": token, "token_carrier": carrier, "headroom_floor": h_floor}
        base_parts = tuple((d.base_div, o.q_pay, o.q_reg) for d, o in zip(first, due))
        if token:
            base_parts = tuple((a + token, pq, rq) if i == tok["token_carrier"] else (a, pq, rq)
                               for i, (a, pq, rq) in enumerate(base_parts))
        # дивиденд решений модели, который снижает норматив уже в этом квартале (ι_p = 1)
        same_q = sum(d.base_div for d, o in zip(first, due) if d.source == "model" and o.q_reg == q)
        if token and due[tok["token_carrier"]].q_reg == q:
            same_q += token
        # 3. доля прироста — закрытая формула по двум оценкам
        g_full = (h_full[0] - same_q, h_full[1] - same_q)
        g_low = None
        lam = 1.0
        if can_cut and min(g_full) < 0:
            if low is None:
                low = self.evaluate(st, q, reg_parts, lam_min, memo=memo, light=probe)
                h_low = self.room(low[0], q)
            g_low = (h_low[0] - same_q, h_low[1] - same_q)
            lam = min(1.0, max(lam_min, min(growth_share(g_low[j], g_full[j], lam_min) for j in (0, 1))))
        # 4. проверка полной оценкой и не больше одного шага секущей по связывающему нормативу
        done = h_fin = None
        if lam_min < lam < 1.0:
            done, gaps, j = self.checked(st, q, base_parts, lam, memo=memo)
            if abs(gaps[j]) > gr.tol:
                r = gaps[j] * done[0]["rwa"]
                end, g_end = (lam_min, g_low[j]) if r < 0 else (1.0, g_full[j])
                if g_end * r < 0:
                    lam = min(1.0, max(lam_min, lam - r * (end - lam) / (g_end - r)))
                    done, gaps, j = self.checked(st, q, base_parts, lam, memo=memo)
                if abs(gaps[j]) > gr.tol:
                    self.unsolved.append((self.tl.period(q), gaps[j]))
            h_fin = min(gaps[i] * done[0]["rwa"] + same_q for i in (0, 1))
        elif lam < 1.0:
            h_fin = min(h_low)                  # λ* = λ_min: проверки нет, норматив может остаться ниже требования
        # 5. навёрстывание — при полном росте и запасе, раньше выплаты избытка
        plain, extra = full, None               # оценка без решений модели при итоговых объёмах
        if lam == 1.0 and min(g_full) >= 0 and gr.catch_up > 0:
            want = {b: gr.catch_up * QUARTER_YEARS * (star[b] - st.E[b]) * fac[b] for b in p.roles.loans
                    if star[b] > st.E[b]}
            if want:
                more = self.evaluate(st, q, reg_parts, 1.0, want, memo=memo, light=probe)
                h_more = self.room(more[0], q)
                g_more = (h_more[0] - same_q, h_more[1] - same_q)
                if min(g_more) >= 0:
                    plain, extra = more, want
                else:
                    theta = min(g_full[j] / (g_full[j] - g_more[j]) for j in (0, 1) if g_more[j] < 0)
                    theta = min(1.0, max(0.0, theta))
                    if theta > 0:
                        part = {b: theta * add for b, add in want.items()}
                        check = self.evaluate(st, q, reg_parts, 1.0, part, memo=memo, light=probe)
                        if min(self.room(check[0], q)) - same_q >= -gr.tol * check[0]["rwa"]:
                            plain, extra = check, part
        # 6. догоняющая выплата и избыток — после навёрстывания и только при неурезанном росте
        if lam == 1.0:
            h_fin = min(self.room(plain[0], q))
        decs = decide_quarter(pol, q=q, due=due, bases=bases, headroom=h_ref, headroom_final=h_fin,
                              payout=self.payout, **tok,
                              deferred=st.D, shock=in_shock, growth_cut=lam < 1.0, n_out=n_out)
        # 7. запись шага: принятая оценка при итоговых объёмах и дивидендах
        if done is None:
            if all(d.div == 0.0 for d in decs if d.source != "register"):
                done = plain if lam == 1.0 else low
                if done[1] is None:             # считались только нормативы — запись шага при тех же объёмах
                    done = self.evaluate(st, q, reg_parts, lam, extra, memo=memo)
            else:
                done = self.evaluate(st, q, tuple((d.div, o.q_pay, o.q_reg) for d, o in zip(decs, due)), lam, extra,
                                     memo=memo)
        row, after, kept = done
        self.accept(q, kept)
        if decs:
            after.D = decs[-1].deferred_after
        if p.min_dps is not None:               # память DPS по годам прибыли (жетон, К1)
            for d in decs:
                if d.source in ("model", "register"):
                    self.dps_year[d.year] = self.dps_year.get(d.year, 0.0) + d.dps
        row["lam"] = lam
        row["div_model"] = sum(d.div for d in decs if d.source != "register")
        return row, decs, after

    def run_constrained(self, last: int) -> tuple[list[dict], list[Decision], State]:
        """Проход при ограничении роста капиталом (М§4.13): квартал за кварталом — `quarter_constrained`; рядом
        ведётся потенциальный путь кредитных книг E*_b (рост без ограничения)."""
        loans = self.p.roles.loans
        st = initial_state(self.p)
        star = {b: st.E[b] for b in loans}
        rows: list[dict] = []
        decisions: list[Decision] = []
        for q in range(1, last + 1):
            n_q = p_bar = None
            if self.p.bb is not None:           # выкуп квартала — до решений: они на акциях клетки (М§5.6)
                p_bar, n_q = self.buyback_quarter(st, q)
            if n_q is None:
                row, decs, st = self.quarter_constrained(st, q, star)
            else:
                row, decs, st = self.quarter_constrained(st, q, star, n_q)
            if n_q is not None:
                self.buyback_after(st, row, q, p_bar, n_q)
            fac = self.growth_factors(self.years[q])
            star = {b: star[b] * fac[b] for b in loans}
            row["loans_potential"] = sum(star.values())
            decisions.extend(decs)
            rows.append(row)
        return rows, decisions, st

    def run(self, until: int | None = None) -> tuple[list[dict], list[Decision], State]:
        p, tl = self.p, self.tl
        if p.bb is not None and p.bb.rule == CELL_VALUE and until is None and not self.fixed_point:
            return self.run_cell_value()
        if p.growth is not None:
            return self.run_constrained(tl.Q if until is None else min(tl.Q, until))
        if p.calendar is not None:
            return self.run_quarterly(tl.Q if until is None else min(tl.Q, until))
        st = initial_state(p)
        rows: list[dict] = []
        decisions: list[Decision] = []
        pol = p.policy
        paid_year = p.af.dividends_payable_year
        last = tl.Q if until is None else min(tl.Q, until)
        for q in range(1, last + 1):
            div_decl, pay_q, reg_q, by_model = 0.0, None, None, 0.0
            if self.hs[q] == pol.agm_quarter:
                year = self.years[q] - 1
                if year >= p.anchor_year - 1 and year != paid_year:
                    base = self.year_base(year)
                    declared = p.register.get(year)
                    shock = self.rg.shock_year is not None and year + 1 == self.rg.shock_year
                    points: list[Checkpoint] = []
                    if declared is None and not (shock and pol.skip_in_shock):
                        points = self.trial(st, q, year)
                    dec = decide(pol, year=year, base=base, points=points, buffer20=p.cap.buffer20,
                                 deferred=st.D, shock=shock, declared_dps=declared)
                    st.D = dec.deferred_after
                    decisions.append(dec)
                    div_decl = dec.div
                    by_model = 0.0 if dec.source == "register" else dec.div
                    pay_q = max(q, p.pay_q_by_year.get(year, tl.index(period_str(year + 1, pol.pay_quarter))))
                    reg_q = max(q, p.reg_q_by_year.get(year, tl.index(period_str(year + 1, pol.reg_quarter))))
            row = self.step(st, q, div_decl, pay_q, reg_q)
            row["div_model"] = by_model
            rows.append(row)
        return rows, decisions, st


def quarter_fields(p: Prepared) -> tuple[str, ...]:
    """Ряды кварталов полной клетки: `QUARTER_FIELDS` и ряды ключей прохода — только при своём ключе книги (без ключа
    ряды клетки прежние)."""
    out = QUARTER_FIELDS
    if p.book_rel is not None:
        out += BOOK_REL_FIELDS
    if p.opex_w is not None or p.line_shares is not None:
        out += OPEX_W_FIELDS
    if p.fees_line is not None:
        out += ("vol_fees",)
    if p.ins_line is not None:
        out += ("vol_ins",)
    if p.share_nominal is not None:                 # Р8-6: номинальная часть франшизы строки H^ℓ (Р10-5: Φ^ℓ)
        out += tuple(nom[2] for nom in p.share_nominal.values())
    if p.k6_line is not None:                       # Р10-5: уровень базы строки на конце квартала D^ℓ и индекс Ψ^ℓ
        out += tuple(END_FLOWS[line] for line in p.k6_line) + tuple(PSI_FLOWS[line] for line in p.k6_line)
    elif p.driver_roots is not None:                # Р9-1: уровень базы строки-драйвера книг К6 на конец квартала
        out += tuple(dict.fromkeys(END_FLOWS[line] for line, _ in p.driver_roots.values()))
    if p.bb is not None:
        out += BB_FIELDS
    if p.guar is not None:
        out += GUAR_FIELDS
    if p.cash is not None:
        out += CASH_FIELDS
    return out


def anchor_row(p: Prepared, ctx: "RunContext", scenario: str) -> dict[str, float | None]:
    """Строка q = 0 (якорь): балансы и нормативы из фактов, потоки квартала якоря — факт ОПУ."""
    af, roles, tl = p.af, p.roles, p.timeline
    sc = p.scenarios[scenario]
    st = initial_state(p)
    loans = sum(af.balances[b] for b in roles.loans)
    loans_ac = loans - af.fv_loans
    dpreg = dpreg_at(st.reg, 0) if st.reg else 0.0
    ay, aq = parse_period(tl.anchor)
    back = after_audit_start(aq, p.cap.audit_cutoffs)
    try:
        e0 = sum(p.hist["ni_sh"][-j] for j in range(back + 1))
    except KeyError:
        e0 = None
    x0 = 1.0
    rwa0 = p.rwa_w.rwa({b: af.balances[b] for b in roles.loans}, af.balances[SECURITIES],
                       af.balances[LIQUIDITY], af.other_assets, p.dn[0], x0, guar=p.rwa_w.guar_g0)
    rt_ = ratios(p.cap, bv=af.bv, dpreg=dpreg, reserve=af.fvoci_reserve, unaudited=e0 or 0.0,
                 t2=p.t2[0], rwa=rwa0, ded_pp20=sc.ded_pp20[0], ded_pp11=sc.ded_pp11[0])
    h = p.hist
    row: dict[str, float | None] = {k: None for k in QUARTER_FIELDS}
    row.update({
        "bv": af.bv, "reserve": af.fvoci_reserve, "dp": af.dividends_payable, "dpreg": dpreg,
        "rwa": rwa0, "k20": rt_.k20, "n20": rt_.n20, "ded20": rt_.ded20, "ded11": rt_.ded11,
        "k11": rt_.k11 if e0 is not None else None, "n11": rt_.n11 if e0 is not None else None,
        "e_unaudited": e0, "req20": sc.req20[0], "req11": sc.req11[0], "floor20": sc.floor20[0],
        "floor11": sc.floor11[0], "loans": loans, "loans_ac": loans_ac, "loans_fv": af.fv_loans,
        "funds": sum(af.balances[b] for b in roles.funds),
        "funds_retail": sum(af.balances[b] for b in roles.retail),
        "iea": sum(af.balances[b] for b in roles.assets), "securities": af.balances[SECURITIES],
        "liquidity": af.balances[LIQUIDITY], "wholesale": af.balances[WHOLESALE],
        "other_assets": af.other_assets, "other_liabilities": af.other_liabilities,
        "allowance": af.allowance, "current_share": st.c,
        "nii": h["nii"].get(0), "llp": h["llp"].get(0), "fees": h["fees"].get(0),
        "opex": h["opex"].get(0), "ins": h["ins"].get(0), "misc": h["misc"].get(0),
        "noncore": h["noncore"].get(0), "pbt": h["pbt"].get(0), "tax": h["tax"].get(0),
        "ni": h["ni"].get(0), "ni_sh": h["ni_sh"].get(0),
        # рост по капиталу (М§4.13.3): потенциальный путь начинается с якоря; требование — с глиссадой
        "loans_potential": loans,
        "req20_glide": p.glide[scenario][0][0] if p.growth is not None else sc.req20[0],
        "req11_glide": p.glide[scenario][1][0] if p.growth is not None else sc.req11[0],
        "n11_star": None if e0 is None else rt_.n11_star,
    })
    if p.bb is not None:
        row["n_out"] = af.n_out                 # выкуп (М§5.6): акции в обращении якоря
    if p.guar is not None:
        row["rwa_guar"] = p.guar.g0             # RWA гарантий якоря (К5, М§4.11)
    if p.cash is not None:
        row["cash"] = p.cash.c0                 # неработающие деньги якоря (К8, М§4.3)
    if p.k6_line is not None:                   # Р10-5: D^ℓ_0 — уровень базы строки якоря, Ψ^ℓ_0 = 1
        row.update({END_FLOWS[line]: v[2].end0 for line, v in p.k6_line.items()})
        row.update({PSI_FLOWS[line]: 1.0 for line in p.k6_line})
    elif p.driver_roots is not None:            # Р9-1: D^ℓ_0 — уровень базы строки-драйвера якоря
        row.update({END_FLOWS[line]: p.driven[b][0].end0 for b, (line, _) in p.driver_roots.items()})
    return row


def shared_anchor_row(p: Prepared, ctx: Any, scenario: str, shared: dict | None) -> dict[str, float | None]:
    """Строка якоря сценария капитала — одна у клеток прогона (её только читают); без `shared` — своя."""
    if shared is None:
        return anchor_row(p, ctx, scenario)
    row = shared.get((ANCHOR, scenario))
    if row is None:
        row = shared[(ANCHOR, scenario)] = anchor_row(p, ctx, scenario)
    return row


def preliminary_paths(ctx: "RunContext", world: str, regime: str, scenario: str, until: int, *,
                      shared: dict | None = None) -> dict[str, tuple[float, ...]]:
    """CoR и ЧПМ движка клетки без отклонений A-P2u (δ ≡ 0) по q = 1…until (М§12, x⁰).

    Кварталы до `until` считаются так же, как в полном проходе (проход последовательный,
    пробный проход дивиденда смотрит вперёд сам), поэтому x⁰ не зависит от `until`. `shared` — общее клеток
    предварительного прохода (`_Cell`)."""
    cell = _Cell(ctx, world, regime, scenario, preliminary=True, shared=shared)
    rows, _, _ = cell.run(until=until)
    return {"cor": (0.0,) + tuple(r["cor"] for r in rows), "nim": (0.0,) + tuple(r["nim"] for r in rows)}


def terminal_inputs(p: Prepared, cell: _Cell, rows: list[dict]) -> tuple[dict[str, float], float]:
    """Входы терминала из прохода клетки (М§7) — всё, кроме дисконта и параметров терминала книги (рост,
    угасание, множитель избытка); рядом — Н20.1 с прибылью периода на конце сетки."""
    tl = p.timeline
    Q = tl.Q
    last = rows[-1]
    L = tl.year(Q)
    pbt_l = sum(r["pbt"] for q, r in zip(range(1, Q + 1), rows) if tl.year(q) == L)
    n11_star = n11_audited(last["k11"], last["e_unaudited"], last["rwa"], p.cap.gap11, cell.sc.ded_pp11[Q])
    y_bal = p.sec_share * last["_rate"][SECURITIES] + (1 - p.sec_share) * last["_rate"][LIQUIDITY]
    n20_t, n11_t = last["n20"], n11_star
    if last["dpreg"]:
        # дивиденды, решённые в последних кварталах сетки: из BV ушли, в регуляторном капитале ещё стоят —
        # без вычета терминал раздал бы их второй раз, как избыток (М§7)
        n20_t -= last["dpreg"] / last["rwa"]
        n11_t -= last["dpreg"] / last["rwa"]
    inputs = dict(n20=n20_t, req20=last["req20"], n11_star=n11_t, req11=last["req11"],
                  rwa=last["rwa"], bv_q=last["bv"], pbt_last_year=pbt_l, y_balancing=y_bal,
                  c_wholesale=last["_rate"][WHOLESALE], headroom=last["la_headroom"], tau_eff=last["tau_eff"],
                  nci_share=p.nci_share, coupon_annual=p.coupon_annual, tau_stat=last["tau_stat"],
                  lt_inflation=cell.w.lt_inflation, min_share=p.liquid_min,
                  wholesale_extra=last["wholesale_extra"])
    if p.nci_q is not None:                 # Р11-3: НДУ года L в рублях (номинал мира; ν_L не множит — строка не по дням)
        inputs["nci_l"] = sum(p.nci_q[(tl.year(q), tl.h(q))] * cell.w.price_index[q]
                              for q in range(1, Q + 1) if tl.year(q) == L)
    if p.stationary_rates:                  # терминал от стационарных ставок книг (К4, М§7)
        cell.stationary = stationary_terminal(p, cell, rows)
        inputs.update(pbt_last_year=pbt_l + cell.stationary["d_nii_l"], y_balancing=cell.stationary["y_bal"],
                      c_wholesale=cell.stationary["c_wh"])
    if p.year_basis == MEAN:                # год терминала по средней длине года (К-Т2а, М§7)
        d_nii = cell.stationary["d_nii_l"] if p.stationary_rates else 0.0
        pbt_t, cell.year_node = mean_year(p, rows, pbt_l, d_nii)
        inputs.update(pbt_last_year=pbt_t, year_factor=cell.year_node["psi"])
    if p.fixed_growth_share is not None:
        inputs["fixed"] = fixed_inputs(p, cell, rows)
    return inputs, n11_star


def mean_year(p: Prepared, rows: list[dict], pbt_l: float, d_nii: float) -> tuple[float, dict[str, float]]:
    """Год терминала по средней длине года (К-Т2а, М§7): проценты считаются по дням (act/365), и високосный год L
    несёт 366/365 годовой ставки — свойство конвенции в явных годах (М§0.3), а вечный поток терминала — средний год.
    Дневные строки года L (ЧПД с АСВ и наложением ЧПМ, резервы, FVC; DW_L) и ΔNII*_L (К4) — × ν_L = 365,2425 / D_L;
    строки не по дням (комиссии, страхование, расходы, «прочее», пакет, FVR) — как есть: их год — четыре квартала роста
    г/г. PBT^T_L = PBT_L + (ν_L − 1) DW_L + ν_L ΔNII*_L; годовые ставки за T (Y_X, блок К-Т) — × ψ = 365,2425 / 365.
    Возвращает PBT^T_L и узел клетки: дни года L, ν_L, ψ, DW_L и поправку adj = PBT^T_L − PBT_L − ΔNII*_L."""
    tl = p.timeline
    Q = tl.Q
    L = tl.year(Q)
    qs = [q for q in range(1, Q + 1) if tl.year(q) == L]
    days = sum(tl.days[q - 1] for q in qs)
    nu = MEAN_YEAR * len(qs) / 4 / days          # средняя длина кварталов года L к их дням
    dw = sum(rows[q - 1]["nii"] - rows[q - 1]["llp"] - rows[q - 1]["fvc"] for q in qs)
    pbt_t = pbt_l + (nu - 1) * dw + nu * d_nii
    return pbt_t, {"days_l": days, "nu_l": nu, "psi": MEAN_YEAR / DAYS_IN_YEAR, "day_weighted_l": dw,
                   "adj": pbt_t - pbt_l - d_nii}


def stationary_terminal(p: Prepared, cell: _Cell, rows: list[dict]) -> dict[str, float]:
    """Вход терминала при полной подстройке ставок книг (К4, М§7): ΔNII*_L = Σ_(q ∈ L) [Σ_актив (y*_b,q − y_b,q) Ē_b,q −
    Σ_пассив (c*_b,q − c_b,q) Ē_b,q] × d_q / 365 — ЧПД года L по целям ставок книг (у балансирующих средние — как в ЧПД
    шага); смесь балансирующих и ставка опта за T — по целям квартала Q. Явные кварталы не меняются. Рядом —
    прежние лаговые ставки (печать)."""
    tl = p.timeline
    Q = tl.Q
    L = tl.year(Q)
    roles = p.roles
    d_nii = 0.0
    for q, r in zip(range(1, Q + 1), rows):
        if tl.year(q) != L:
            continue
        goal = cell.target_rates(q)
        rate, avg = r["_rate"], r["_avg"]
        gap = sum([(goal[b] - rate[b]) * avg[b] for b in roles.assets])
        gap -= sum([(goal[b] - rate[b]) * avg[b] for b in roles.liabilities])
        d_nii += gap * tl.days[q - 1] / DAYS_IN_YEAR
    goal, last = cell.target_rates(Q), rows[-1]["_rate"]
    sec = p.sec_share
    return {"d_nii_l": d_nii, "y_bal": sec * goal[SECURITIES] + (1 - sec) * goal[LIQUIDITY], "c_wh": goal[WHOLESALE],
            "y_bal_lagged": sec * last[SECURITIES] + (1 - sec) * last[LIQUIDITY], "c_wh_lagged": last[WHOLESALE]}


def fixed_inputs(p: Prepared, cell: _Cell, rows: list[dict]) -> FixedInputs:
    """Входы блока постоянных в рублях частей терминала из прохода клетки (М§7): постоянные прочие активы и их RWA на
    конце сетки, капитал на рубль RWA по обоим нормативам (требование сценария, разрывы и вычеты якоря), инструменты
    капитала, постоянные пассивы якоря, строки ОПУ в реальных рублях года L."""
    tl, cap, sc = p.timeline, p.cap, cell.sc
    Q = tl.Q
    L = tl.year(Q)
    mult = cell.rg.rwa_mult[Q] if cell.rg.rwa_mult is not None else 1.0
    r_f = p.rwa_w.other_assets_fixed * p.oa_fixed * p.dn[Q] * cell.x[Q] * mult if p.oa_fixed else 0.0
    dp_fix = 0.0
    if p.calendar is not None:                       # постоянное обязательство: не выплачивается (М§5.7.4)
        dp_fix = p.af.dividends_payable - sum(amount for _, _, amount in p.calendar.payable)
    year_l = [r for q, r in zip(range(1, Q + 1), rows) if tl.year(q) == L]
    return FixedInputs(
        f_a=p.oa_fixed, r_f=r_f,
        kappa20=sc.req20[Q] - (cap.gap20 - sc.ded_pp20[Q]) + cap.ded20_0 / cap.rwa0,
        kappa11=sc.req11[Q] - (cap.gap11 - sc.ded_pp11[Q]) + cap.ded11_0 / cap.rwa0,
        at1=cap.at1, t2=p.t2[Q], nci=p.af.nci, dp_fix=dp_fix,
        misc_l=sum(r["misc"] for r in year_l), nc_l=sum(r["noncore"] for r in year_l))


def path_flags(p: Prepared, cell: _Cell, rows: list[dict], decisions: list[Decision]
               ) -> tuple[set[str], str | None]:
    """Флаги прохода клетки (от оценки не зависят) и квартал первого разрыва к полу норматива."""
    tl = p.timeline
    # нормативы после дивидендов, разрыв к полу
    gap = None
    for q, r in zip(range(1, tl.Q + 1), rows):
        if r["n20"] < r["floor20"] or r["n11"] < r["floor11"]:
            gap = tl.period(q)
            break
    flags = set()
    if gap is not None:
        flags.add("capital_gap")
    for dec in decisions:
        flags.update(dec.flags)
    if any(r["lam"] < 1 - LAM_TOL for r in rows):
        flags.add("growth_cut")
    if cell.unsolved:
        flags.add("growth_solver")
    return flags, gap


def value_path(ctx: "RunContext", world: str, inputs: Mapping[str, float], bv: tuple, ci: tuple, div: tuple,
               bb: tuple | None = None, d_ext: tuple | None = None, n_t: float | None = None):
    """Терминал и оценка клетки по её проходу (М§6–§7): дисконт мира, рост, угасание и множитель избытка — из
    контекста прогона, остальное — из прохода. Одна функция у полной клетки и у лёгкой клетки сводки. `bb`, `d_ext`,
    `n_t` — выкуп по цене мира (М§5.6): суммы, дивиденд на внешнюю акцию клетки, акции клетки на конце сетки."""
    p, disc = ctx.prep, ctx.discounts[world]
    if p.fixed_growth_share is None:
        term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple, k_t=disc.k_t,
                        symmetric=p.fade_symmetric, **terminal_keys(p))
    else:                                           # блок постоянных частей терминала (М§7)
        term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, multiple=p.multiple, k_t=disc.k_t,
                        symmetric=p.fade_symmetric, lam_f=p.fixed_growth_share, parts=p.fixed_parts,
                        **terminal_keys(p))
    if bb is None:
        val = value_cell(q0=ctx.clock.q0, elapsed=ctx.clock.elapsed, disc=disc, bv=bv, ci=ci, div=div,
                         term=term)
    else:
        val = value_cell(q0=ctx.clock.q0, elapsed=ctx.clock.elapsed, disc=disc, bv=bv, ci=ci, div=div, term=term,
                         bb=bb, d_ext=d_ext, n_t=n_t, n_out=p.af.n_out)
    return term, val


def terminal_keys(p: Prepared) -> dict[str, Any]:
    """Параметры оценки К-Т2 у терминала (М§7) — только при своих ключах книги (без ключей — пусто: прежний вызов):
    s = Y(L) − Y_a — лет явного участка после года-якоря угасания (К-Т2в); ставка фондирования блока К-Т по правилу
    балансирующих статей (К-Т2б; только при блоке)."""
    out: dict[str, Any] = {}
    if p.fade_anchor is not None:
        out["fade_s"] = p.timeline.last_year - p.fade_anchor
    if p.fixed_funding == FUNDING_BALANCING and p.fixed_growth_share is not None:
        out["funding"] = FUNDING_BALANCING
    return out


def labelled_value(ctx: "RunContext", world: str, label: str, inputs: Mapping[str, float], bv: tuple, ci: tuple,
                   div: tuple, **buyback: Any):
    """`value_path` клетки с её меткой в отказе оценки (М§7: капитал бизнеса за T не больше нуля)."""
    try:
        return value_path(ctx, world, inputs, bv, ci, div, **buyback)
    except BookError as exc:
        raise BookError(f"клетка {label}: {exc}") from None


# Ряды кварталов, которых хватает лёгкой клетке: оценке — BV, мосту — дивиденды, годовым рядам роста — кредиты.
SUMMARY_FIELDS = ("bv", "div_model", "loans", "loans_potential", "catch_up", "lam")


@dataclass(frozen=True)
class CellPath:
    """Проход клетки, сжатый до входов оценки (М§6–§7) и сводки прогона полосы (М§10). От дисконта, угасания
    избыточной доходности и множителя избытка капитала терминала, весов миров, вероятностей, даты оценки и
    дисконта за управление проход не зависит: пока входы прохода те же (`model.grid.path_keys`), он считается
    один раз, а оценка — заново. Реальный рост терминала проход читает — путями миров (рост кредита сходится к
    росту терминала мира)."""
    world: str
    regime: str
    scenario: str
    bv: tuple[float, ...]                  # BV на конец квартала, q = 0…Q
    ci: tuple[float, ...]                  # совокупный доход квартала (q = 0 — ноль)
    div: tuple[float, ...]                 # уменьшение BV дивидендами (q = 0 — ноль)
    div_model: tuple[float | None, ...]    # часть дивиденда, решённая моделью (q = 0 — None)
    terminal: Mapping[str, float]          # входы терминала из прохода (`terminal_inputs`)
    n11_star: float
    n20_min: float
    n11_min: float
    gap_period: str | None
    flags: frozenset[str]                  # флаги прохода; `roe_below_k` добавляет оценка
    cut_share: tuple[float | None, ...]    # доля урезанного роста по годам клетки (М§4.13.3)
    solver: tuple[tuple[str, float], ...] = ()
    # выкуп по цене мира (М§5.6); без ключа — пусто
    bb: tuple[float, ...] = ()             # B_q (q = 0 — ноль)
    d_ext: tuple[float, ...] = ()          # дивиденд на внешнюю акцию клетки d_q (q = 0 — ноль)
    n_t: float | None = None               # акции клетки на конце сетки


def cell_path(ctx: Any, world: str, regime: str, scenario: str, *, shared: dict | None = None) -> CellPath:
    """Проход клетки (W, r, s) для сводки прогона. `ctx` — входы прохода (`model.grid.PathInputs`) или контекст
    прогона: проход читает только подготовку, пути миров, отклонения A-P2u и валютный индекс. `shared` — общее
    клеток прогона (`_Cell`)."""
    p = ctx.prep
    cell = _Cell(ctx, world, regime, scenario, shared=shared)
    rows, decisions, _ = cell.run()
    full = [shared_anchor_row(p, ctx, scenario, shared)] + rows
    quarters = {k: tuple(map(methodcaller("get", k), full)) for k in SUMMARY_FIELDS}
    inputs, n11_star = terminal_inputs(p, cell, rows)
    flags, gap = path_flags(p, cell, rows, decisions)
    years = tuple(range(p.anchor_year, p.timeline.last_year + 1))
    bb = {} if p.bb is None else buyback_series(rows)
    return CellPath(
        world=world, regime=regime, scenario=scenario, bv=quarters["bv"],
        ci=(0.0,) + tuple(r["ci"] for r in rows), div=(0.0,) + tuple(r["div"] for r in rows),
        div_model=quarters["div_model"], terminal=inputs, n11_star=n11_star,
        n20_min=min(r["n20"] for r in rows), n11_min=min(r["n11"] for r in rows), gap_period=gap,
        flags=frozenset(flags), cut_share=growth_rows(p, quarters, years)["cut_share"],
        solver=tuple(cell.unsolved), **bb)


def buyback_series(rows: list[dict]) -> dict[str, Any]:
    """Входы оценки выкупа по цене мира из прохода клетки (М§5.6): B_q, d_q (q = 0 — ноль) и акции на конце сетки."""
    return {"bb": (0.0,) + tuple(r["bb"] for r in rows), "d_ext": (0.0,) + tuple(r["d_ext"] for r in rows),
            "n_t": rows[-1]["n_out"]}


def summary_cell(ctx: "RunContext", path: CellPath) -> CellResult:
    """Лёгкая клетка — оценка готового прохода в контексте прогона: стоимость, терминал, флаги и то из рядов,
    что читают слои, мост и сводка прогона (`model.uncertainty.run_summary`). Рядов по кварталам и годам,
    книг и решений у неё нет — полную клетку считает `run_cell`."""
    bb = {} if not path.bb else {"bb": path.bb, "d_ext": path.d_ext, "n_t": path.n_t}
    term, val = labelled_value(ctx, path.world, f"{path.world}/{path.regime}/{path.scenario}", path.terminal,
                               path.bv, path.ci, path.div, **bb)
    flags = set(path.flags)
    if term.roe_t < term.k_t:
        flags.add("roe_below_k")
    return CellResult(
        world=path.world, regime=path.regime, scenario=path.scenario,
        quarters={"bv": path.bv, "div": (None,) + path.div[1:], "div_model": path.div_model}, annual={}, dps={},
        v_ri=val.v_ri, v_ddm=val.v_ddm, bv_v=val.bv_v, x_t=term.x_t, roe_t=term.roe_t, k_t=term.k_t,
        g_t=term.g_t, tv_ri=term.tv_ri, terminal_share=val.terminal_share,
        n20_min=path.n20_min, n11_min=path.n11_min, gap_period=path.gap_period, flags=frozenset(flags),
        tv_ddm=term.tv_ddm, pv_ri_explicit=val.pv_ri_explicit, pv_terminal=val.pv_terminal,
        roe_t_raw=term.roe_raw, g_capped=term.g_capped, bv_star=term.bv_star, n11_star=path.n11_star,
        y_x=term.y_x, la_headroom=path.terminal["headroom"],
        growth={"cut_share": path.cut_share}, solver=path.solver, terminal_fixed=term.fixed,
        v_hat=val.v_price, s_price=val.s_price, n_t=path.n_t, pv_buyback=val.pv_buyback, terminal_fade=term.fade_cal)


def run_cell(ctx: "RunContext", world: str, regime: str, scenario: str, *, summary: bool = False,
             shared: dict | None = None) -> CellResult:
    """Клетка (W, r, s): квартальный проход, терминал, RI и DDM (М§4–§7). `summary` — лёгкая клетка для сводки
    прогона полосы (`summary_cell`): те же проход и оценка, без рядов по кварталам и годам. `shared` — общее
    клеток прогона (`_Cell`)."""
    if summary:
        return summary_cell(ctx, cell_path(ctx, world, regime, scenario, shared=shared))
    p = ctx.prep
    cell = _Cell(ctx, world, regime, scenario, shared=shared)
    rows, decisions, st = cell.run()
    disc: Discount = ctx.discounts[world]
    row0 = shared_anchor_row(p, ctx, scenario, shared)
    full = [row0] + rows
    quarters = {k: tuple(map(methodcaller("get", k), full)) for k in quarter_fields(p)}
    quarters["k_q"] = tuple(disc.k)
    books = {b: {"rate": (p.af.rates[b],) + tuple(r["_rate"][b] for r in rows),
                 "avg": (None,) + tuple(r["_avg"][b] for r in rows),
                 "balance": (p.af.balances[b],) + tuple(r["_bal"][b] for r in rows)}
             for b in p.roles.names}
    # терминал (М§7)
    last = rows[-1]
    inputs, n11_star = terminal_inputs(p, cell, rows)
    bv = quarters["bv"]
    ci = (0.0,) + tuple(r["ci"] for r in rows)
    div = (0.0,) + tuple(r["div"] for r in rows)
    bb = {} if p.bb is None else buyback_series(rows)
    term, val = labelled_value(ctx, world, f"{world}/{regime}/{scenario}", inputs, bv, ci, div, **bb)
    n20s = [r["n20"] for r in rows]
    n11s = [r["n11"] for r in rows]
    flags, gap = path_flags(p, cell, rows, decisions)
    if term.roe_t < term.k_t:
        flags.add("roe_below_k")
    cal = p.calendar
    if cal is None:
        dps = {dec.year: dec.dps for dec in decisions}
        dps_pol = {dec.year: pool_policy(p.policy, dec.year, dec.base) * 1000 / p.af.n_iss for dec in decisions}
        dps_q, dps_pol_q = {}, {}
    else:
        # по кварталам прибыли — решения клетки; по годам — сумма четырёх кварталов: открытые — решения,
        # закрытые — строки истории дивидендов (М§5.7.5)
        dps_q = {dec.period: dec.dps for dec in decisions}
        dps_pol_q = {dec.period: pool_policy(p.policy, dec.year, dec.base) * 1000 / p.af.n_iss for dec in decisions}
        dps = {y: cal.closed_dps[y] + sum(dps_q[per] for per in cal.year_periods[y]) for y in cal.years}
        dps_pol = {y: cal.closed_dps[y] + sum(dps_pol_q[per] for per in cal.year_periods[y]) for y in cal.years}
    annual, years = annual_rows(p, quarters, dps)
    return CellResult(
        world=world, regime=regime, scenario=scenario, quarters=quarters, annual=annual, dps=dps,
        v_ri=val.v_ri, v_ddm=val.v_ddm, bv_v=val.bv_v, x_t=term.x_t, roe_t=term.roe_t, k_t=term.k_t,
        g_t=term.g_t, tv_ri=term.tv_ri, terminal_share=val.terminal_share,
        n20_min=min(n20s), n11_min=min(n11s), gap_period=gap, flags=frozenset(flags),
        years=years, tv_ddm=term.tv_ddm, pv_ri_explicit=val.pv_ri_explicit, pv_terminal=val.pv_terminal,
        roe_t_raw=term.roe_raw, g_capped=term.g_capped, bv_star=term.bv_star,
        decisions=tuple(decisions), dps_policy=dps_pol, ci_q0=ci[ctx.clock.q0], n11_star=n11_star,
        y_x=term.y_x, la_headroom=last["la_headroom"],
        real_rate=float(ctx.book.get(f"worlds.{world}.zero_curve.LT")) - cell.w.lt_inflation,
        books=books, dps_q=dps_q, dps_policy_q=dps_pol_q,
        growth=growth_rows(p, quarters, years), solver=tuple(cell.unsolved),
        pv_ri_q=tuple(r * d for r, d in zip(val.ri, disc.dfq)), terminal_fixed=term.fixed,
        v_hat=val.v_price, s_price=val.s_price, n_t=bb.get("n_t"), pv_buyback=val.pv_buyback,
        terminal_stationary=cell.stationary, terminal_year=cell.year_node, terminal_fade=term.fade_cal,
    )


def growth_rows(p: Prepared, quarters: Mapping[str, tuple], years: tuple[int, ...]
                ) -> dict[str, tuple[float | None, ...]]:
    """Годовые ряды роста кредитных книг клетки (М§4.13.3): потенциальный и фактический рост суммы кредитных
    книг конца года к концу прошлого; доля урезанного роста на конец года; навёрстанное за год; наименьшая за
    год доля прироста. Знаменатель года якоря — факт конца прошлого года (`balance.history`); нет узла — роста
    года якоря нет."""
    tl = p.timeline
    loans, potential = quarters["loans"], quarters["loans_potential"]
    out: dict[str, list[float | None]] = {k: [] for k in GROWTH_FIELDS}
    for y in years:
        qs = tl.quarters_of_year(y)
        end, prev = qs[-1], qs[0] - 1
        inside = [q for q in qs if 1 <= q <= tl.Q]
        if end > tl.Q or not inside:            # год без конца на сетке или без кварталов сетки — значений нет
            for k in GROWTH_FIELDS:
                out[k].append(None)
            continue
        if prev >= 0:
            base, base_potential = loans[prev], potential[prev]
        else:
            base = base_potential = p.hist_bal.get(prev, {}).get("loans")
        out["potential"].append(None if base_potential is None else potential[end] / base_potential - 1)
        out["actual"].append(None if base is None else loans[end] / base - 1)
        out["cut_share"].append(1 - loans[end] / potential[end])
        out["catch_up"].append(sum(quarters["catch_up"][q] for q in inside))
        out["lam_min"].append(min(quarters["lam"][q] for q in inside))
    return {k: tuple(v) for k, v in out.items()}


def annual_rows(p: Prepared, quarters: Mapping[str, tuple], dps: Mapping[int, float]
                ) -> tuple[dict[str, tuple[float | None, ...]], tuple[int, ...]]:
    """Годовые ряды клетки (П§2 grid.cells[].annual): год якоря — факт отчётных кварталов + клетка.

    Годовые отношения — сумма кварталов к среднему пяти концов кварталов года (М§0.3);
    концы до якоря — `balance.history` фактов (если конца нет — среднее доступных).
    """
    tl = p.timeline
    years = tuple(range(p.anchor_year, tl.last_year + 1))
    out: dict[str, list[float | None]] = {k: [] for k in ("ni_sh", "roe", "cor", "nim", "cir", "n20",
                                                          "n11", "dps", "payout")}
    hist = p.hist
    Q = tl.Q

    def flow(name: str, q: int) -> float | None:
        if q >= 1:
            return quarters[name][q]
        return hist.get(name, {}).get(q)

    for y in years:
        qs = tl.quarters_of_year(y)
        ends = [q for q in [qs[0] - 1] + qs if q <= Q]

        def total(name: str) -> float | None:
            vals = [flow(name, q) for q in qs]
            return None if any(v is None for v in vals) else sum(vals)

        def mean_end(name: str) -> float | None:
            vals = []
            for q in ends:
                v = quarters[name][q] if q >= 0 else p.hist_bal.get(q, {}).get(name)
                if v is not None:
                    vals.append(v)
            return sum(vals) / len(vals) if vals else None

        ni = total("ni_sh")
        bv_avg = mean_end("bv")
        out["ni_sh"].append(ni)
        out["roe"].append(None if ni is None or not bv_avg else ni / bv_avg)
        llp, ac = total("llp"), mean_end("loans_ac")
        out["cor"].append(None if llp is None or not ac else llp / ac)
        nii, iea = total("nii"), mean_end("iea")
        out["nim"].append(None if nii is None or not iea else nii / iea)
        parts = [total(k) for k in ("nii", "fees", "ins", "misc")]
        opex = total("opex")
        if opex is None or any(v is None for v in parts):
            out["cir"].append(None)
        else:
            fvr = sum(quarters["fvr"][q] or 0.0 for q in qs if q >= 1)
            out["cir"].append(opex / (sum(parts) + fvr))
        last_q = qs[-1]
        out["n20"].append(quarters["n20"][last_q] if 0 <= last_q <= Q else None)
        out["n11"].append(quarters["n11"][last_q] if 0 <= last_q <= Q else None)
        d = dps.get(y)
        out["dps"].append(d)
        out["payout"].append(None if d is None or not ni else d * p.af.n_iss / 1000 / ni)
    if "bb" in quarters:                        # выкуп по цене мира (М§5.6): сумма кварталов сетки года
        out["buyback"] = [sum(quarters["bb"][q] for q in tl.quarters_of_year(y) if 1 <= q <= Q)
                          if any(1 <= q <= Q for q in tl.quarters_of_year(y)) else None for y in years]
    return {k: tuple(v) for k, v in out.items()}, years
