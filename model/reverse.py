"""Обратный расчёт медианы: что в цене (М§11) и банковские строки.

Для каждой оси `valuation.reverse_dcf.axes` — значение ОДНОГО суждения, при котором
печатаемая медиана равна цене главного тикера; остальное разыгрывается как в полосе.

* Вид оси: `value` — значение ключей; `shift` — сдвиг траекторий (кроме `LT_from`); `mix` —
  каждая строка `joint.reg_prob_given_regime` → (1 − x) × книга + x × `toward`.
* Суждение подменяется в книге ДО полосы: у оси, которая есть в полосе, проверяемое значение —
  центр розыгрыша, а граница, которую он пересёк, следует за ним (`reverse_bounds: follow_center`);
  ось, которой в полосе нет, стоит на проверяемом значении. Строки осей полосы и осей вне её
  решаются поэтому по-разному, и решения разных строк не перемножаются (оговорка — в `method`).
  При ключе книги `valuation.reverse_dcf.axis_follow: both` за проверяемым значением идут ОБА конца
  оси вида `value` — ось сдвигается вместе с центром и сохраняет свою форму (концы не выходят из
  отрезка поиска строки): у решения за краем диапазона ось не становится односторонней. Без ключа
  (`near`) — прежнее правило. Связка полосы (`bundle`) осью строки не считается.
* Поиск (перенос 850oa): точечное решение — бисекция на `search` (≤ 40 шагов, стоп
  `search_tol_rub`); медиана — на подвыборке `subsample` с привязкой к печатаемой
  (`MedianAnchor`): старт — точечное решение, отодвинутое в 9/4 раза, секущая наружу до
  смены знака, обратная квадратичная интерполяция внутри; нет смены знака — «недостижимо».
  Корень на краю отрезка поиска (кроме значения книги) — тоже «недостижимо в поиске»: край —
  предел, до которого книга считает значение осмысленным, а не решение (`reason` строки).
  Решение внутри диапазона книги уточняется на полной полосе (секущая, не больше
  min(`median_refine`, 2) полос; невязка в стопе — уточнение кончено, М§11.2);
  решение — точка с наименьшей невязкой, невязка печатается. При ключе книги
  `valuation.reverse_dcf.edge_refine_rub` так же уточняется и решение подвыборки за краем диапазона,
  если невязка подвыборки на ближнем краю диапазона по модулю не больше порога ключа: пометку
  «в диапазоне / вне» у такой строки ставит корень полной полосы, а не ошибка подвыборки.
  При ключе книги `valuation.reverse_dcf.refine_rows` (список ключей строк) на полной полосе уточняются
  только названные строки; у прочих решение — корень подвыборки: строка несёт `gap_basis: "subsample"`,
  пометку «в диапазоне» ставит он же, а узел называет список (`refine_rows`). Без ключа — все строки.
* «В диапазоне книги» (`in_range`) — только о корне: решение с невязкой в стопе лежит в диапазоне;
  у несошедшегося уточнения — и лучшее приближение, и оценка корня секущей лежат в диапазоне.
  Приближение внутри диапазона при корне за его краем печатается «вне диапазона».
* Строка по ключу цели ЧПМ печатает и само суждение о марже, а не только ключ. У книги с ключом
  `checks.nim_stationary` — стационарную маржу мира-цели гейта, а без него у книги с ключом уровня
  `nii.transmission.level_world` — стационарную маржу мира уровня (ключ цели — она сама): на книге
  (`stationary_book`) и при корне (`stationary_solved`) и, при ключе `checks.window_backtest`, уровни после
  фазы роста при корне (`levels_solved`; один счёт сетки). Иначе у книги с ключом `checks.nim_lt` —
  печатаемую маржу модальной клетки после фазы роста: на книге (`printed_book`) и при корне (`printed_solved`;
  один счёт сетки).
* Банковские строки: вменённый ROE сквозь цикл (строка ЧПМ), вменённая стоимость капитала
  (строка ERP; k_T по мирам и λ-смесь), рынок: Cap − BV против V − BV точки. Пределы и срок второй формы
  банка (М§11.3; строки — по списку книги): стоимость без опережающего роста — точка книги с нулевой премией
  роста (элементы премий, названные книгой фактом, — `valuation.reverse_dcf.premium_facts` — не снимаются);
  капитал без премии — капитал на акцию делителя; срок избыточной доходности в цене — номер первого
  года, на котором накопленная приведённая стоимость остаточного дохода смеси заголовка не меньше Cap − BV.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable, Mapping, Sequence

from model.book import Book, Facts
from model.book_schema import BookError
from model.checks import grouped, num
from model.grid import (NIM_LT, THOUSAND, GridRun, LiveInputs, bank_language, printed_nim_lt, run_grid,
                        sensitivity_overrides)
from model.levels import LEVEL_METRICS, WINDOW_BACKTEST, judged_nim, levels
from model.paths import shift_trajectory
from model import uncertainty as U

__all__ = ["reverse_dcf", "reverse_overrides", "reverse_trial", "solve_outward", "bracketed",
           "bisect_point", "root_in_range", "SEED_FACTOR", "MAX_STEPS", "BISECT_STEPS", "MAX_REFINE",
           "not_computed", "axis_follow", "FOLLOW_NEAR", "FOLLOW_BOTH", "EDGE_REASON", "NIM_PATH",
           "on_search_edge", "near_range_edge", "EDGE_REFINE", "levels_brief", "refine_rows", "REFINE_ROWS",
           "refines_on_full_band", "no_premium_overrides", "premium_facts", "PREMIUM_FACTS"]

SEED_FACTOR = 9 / 4          # старт поиска медианы дальше от книги, чем точечное решение (850oa)
MAX_STEPS = 12               # предел пересчётов медианы на один корень
BISECT_STEPS = 40            # бисекция точки (М§11.2)
MAX_REFINE = 2               # уточнение на полной полосе — не больше двух шагов (М§11.2)
ERP_PATH = "valuation.erp"
NIM_PATH = "nii.nim_lt_target_mgmt"          # ключ цели ЧПМ: его строка печатает и маржу модальной клетки (М§11.2)
AXIS_FOLLOW = "valuation.reverse_dcf.axis_follow"
FOLLOW_NEAR, FOLLOW_BOTH = "near", "both"    # какие концы оси полосы идут за проверяемым значением (М§11.2)
EDGE_REASON = "корень на краю отрезка поиска"
EDGE_REFINE = "valuation.reverse_dcf.edge_refine_rub"   # порог невязки подвыборки на краю диапазона, ₽ (М§11.2)
REFINE_ROWS = "valuation.reverse_dcf.refine_rows"       # ключи строк, корень которых уточняется на полной полосе
PREMIUM_FACTS = "valuation.reverse_dcf.premium_facts"   # ключи времени премий роста, названные книгой фактом (М§11.3)

NAMED_LITERALS = {
    2.25: "SEED_FACTOR: старт поиска медианы — точечное решение × 9/4 (перенос 850oa)",
}


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


# ------------------------------------------------------------------ подмены


def reverse_overrides(book: Book, ax: Mapping[str, Any], v: float) -> dict[str, Any]:
    """Подмены книги для значения v оси обратного расчёта."""
    kind = ax.get("kind", "value")
    out: dict[str, Any] = {}
    for path in ax["paths"]:
        if kind == "value":
            out[path] = float(v)
        elif kind == "shift":
            out[path] = shift_trajectory(book.get(path), float(v))
        elif kind == "mix":
            table = book.get(path)
            toward = ax.get("toward") or {}
            out[path] = {r: {s: (1 - v) * float(row[s]) + v * float(toward[s]) for s in row}
                         for r, row in table.items()}
        else:
            raise BookError(f"ось обратного расчёта {ax.get('name')!r}: незнакомый kind {kind!r}")
    return out


def _book_value(book: Book, ax: Mapping[str, Any]) -> float:
    return float(book.get(ax["paths"][0])) if ax.get("kind", "value") == "value" else 0.0


def _band_axis(book: Book, path: str) -> int | None:
    for j, ax in enumerate(book.get("valuation.uncertainty.axes") or []):
        if ax.get("kind") == "value" and path in ax.get("paths", []):
            return j
    return None


def axis_follow(book: Book) -> str:
    """Какие концы оси полосы идут за проверяемым значением — ключ книги `valuation.reverse_dcf.axis_follow`;
    без ключа — `near`: только граница, которую значение пересекло (М§11.2)."""
    return str(book.opt(AXIS_FOLLOW, FOLLOW_NEAR))


def reverse_trial(book: Book, ax: Mapping[str, Any], v: float, *, follow: bool) -> Book:
    """Книга с суждением оси на значении v; граница оси полосы следует за центром. При `axis_follow: both` за
    центром идут оба конца: ось сдвигается на (v − книга) и остаётся в отрезке поиска строки."""
    ov = reverse_overrides(book, ax, v)
    if follow and ax.get("kind", "value") == "value":
        both = axis_follow(book) == FOLLOW_BOTH
        book_axes = list(book.get("valuation.uncertainty.axes"))
        axes = copy.deepcopy(book_axes)
        step = v - _book_value(book, ax)        # сдвиг центра: от значения книги на первом пути строки
        moved = False
        for path in ax["paths"]:
            j = _band_axis(book, path)
            if j is not None:
                low, high = float(book_axes[j]["low"]), float(book_axes[j]["high"])
                if both:
                    lo, hi = (float(x) for x in ax["search"])
                    axes[j]["low"], axes[j]["high"] = min(max(low + step, lo), v), max(min(high + step, hi), v)
                else:
                    axes[j]["low"], axes[j]["high"] = min(low, v), max(high, v)
                moved = True
        if moved:
            ov["valuation.uncertainty.axes"] = axes
    return U.trial_book(book, ov)


# ------------------------------------------------------------------ поиск корня


def bracketed(g: Callable[[float], float], a: float, fa: float, b: float, fb: float, c: float | None,
              fc: float | None, steps: int, tol: float) -> tuple[float, int, bool]:
    """Корень g на [a; b] (fa, fb разных знаков): обратная квадратичная по трём точкам, иначе секущая.

    → (корень, пересчётов, найден ли в допуске); не сошлось — оценка секущей (не проверена)."""
    used = 0
    for _ in range(steps):
        x = None
        if c is not None and fc is not None and len({fa, fb, fc}) == 3:
            x = (a * fb * fc / ((fa - fb) * (fa - fc)) + b * fa * fc / ((fb - fa) * (fb - fc))
                 + c * fa * fb / ((fc - fa) * (fc - fb)))
            if not min(a, b) < x < max(a, b):
                x = None
        if x is None:
            x = (a * fb - b * fa) / (fb - fa)
        fx = g(x)
        used += 1
        if abs(fx) <= tol:
            return x, used, True
        if (fx > 0) == (fa > 0):
            c, fc, a, fa = a, fa, x, fx
        else:
            c, fc, b, fb = b, fb, x, fx
    return (a * fb - b * fa) / (fb - fa), used, False


def solve_outward(g: Callable[[float], float], b: float, gb: float, x1: float, end: float, *, tol: float,
                  steps: int = MAX_STEPS) -> tuple[float | None, int]:
    """Корень g между b и `end`: старт x1, секущая наружу до смены знака, затем `bracketed`.

    g не меняет знак до `end` — None («недостижимо в поиске»)."""
    if abs(gb) <= tol:
        return b, 0
    prev, xa, fa, x, used = None, b, gb, x1, 0
    direction = _sign(end - b)
    while used < steps:
        fx = g(x)
        used += 1
        if abs(fx) <= tol:
            return x, used
        if (fx > 0) != (fa > 0):
            c, fc = prev if prev else (None, None)
            root, more, _ = bracketed(g, xa, fa, x, fx, c, fc, steps - used, tol)
            return root, used + more
        if x == end:
            return None, used
        nxt = x - fx * (x - xa) / (fx - fa) if fx != fa else math.inf
        if not math.isfinite(nxt) or (nxt - x) * direction <= 0:
            nxt = x + (x - xa)
        nxt = min(nxt, end) if direction > 0 else max(nxt, end)
        prev, xa, fa, x = (xa, fa), x, fx, nxt
    return None, used


def bisect_point(g: Callable[[float], float], lo: float, hi: float, *, tol: float,
                 steps: int = BISECT_STEPS) -> tuple[float | None, float | None]:
    """Бисекция на [lo; hi] (≤ steps шагов, стоп |g| ≤ tol) → (корень, невязка); нет смены знака — (None, None)."""
    flo, fhi = g(lo), g(hi)
    if abs(flo) <= tol:
        return lo, flo
    if abs(fhi) <= tol:
        return hi, fhi
    if flo * fhi > 0:
        return None, None
    best = (lo, flo) if abs(flo) < abs(fhi) else (hi, fhi)
    for _ in range(steps):
        mid = (lo + hi) / 2
        fm = g(mid)
        if abs(fm) < abs(best[1]):
            best = (mid, fm)
        if abs(fm) <= tol:
            return mid, fm
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return best


class _Recorder:
    """Функция невязки с журналом вычисленных точек (x → невязка)."""

    def __init__(self, fn: Callable[[float], float]):
        self.fn, self.seen = fn, {}

    def __call__(self, x: float) -> float:
        if x not in self.seen:
            self.seen[x] = self.fn(x)
        return self.seen[x]

    def best(self) -> tuple[float, float] | None:
        return min(self.seen.items(), key=lambda kv: abs(kv[1])) if self.seen else None


# ------------------------------------------------------------------ строки


def levels_brief(node: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Уровни после фазы роста коротко: строка узла уровней → {ЧПМ, CoR, C/I, доля кредитов} без рядов по годам."""
    return {key: {k: row[k] for k in LEVEL_METRICS} for key, row in node["rows"].items()}


def _printed(book: Book, ax: Mapping[str, Any], run: GridRun | None) -> dict[str, Any]:
    """Поля суждения о марже у строки по ключу цели ЧПМ (М§11.2, §14.2). У книги с ключом `checks.nim_stationary`
    или с ключом уровня `nii.transmission.level_world` — стационарная маржа мира суждения на книге (при корне —
    пусто, пока корня нет; `model.levels.judged_nim`) и, при ключе `checks.window_backtest`, место под уровни
    после фазы роста при корне; иначе у книги с ключом `checks.nim_lt` — печатаемая маржа модальной клетки на
    книге. У прочих строк и у книги без этих ключей — пусто."""
    judged = None if run is None or NIM_PATH not in ax["paths"] else judged_nim(run.ctx)
    if judged is not None:
        out = {"stationary_book": judged["value"], "stationary_solved": None}
        if book.opt(WINDOW_BACKTEST) is not None:
            out["levels_solved"] = None
        return out
    if run is None or NIM_PATH not in ax["paths"] or book.opt(NIM_LT) is None:
        return {}
    return {"printed_book": printed_nim_lt(run)["value"], "printed_solved": None}


def _printed_at_root(printed: dict[str, Any], at_root: GridRun) -> None:
    """Суждение о марже при корне строки цели ЧПМ — по сетке книги с корнем (один счёт сетки)."""
    if "stationary_book" in printed:
        printed["stationary_solved"] = judged_nim(at_root.ctx)["value"]
        if "levels_solved" in printed:
            printed["levels_solved"] = levels_brief(levels(at_root))
    else:
        printed["printed_solved"] = printed_nim_lt(at_root)["value"]


def not_computed(book: Book, reason: str, *, run: GridRun | None = None) -> dict[str, Any]:
    """Блок П§2 reverse_dcf быстрой сборки: строки «не считалось» с причиной. `run` — сетка книги: строка по
    ключу цели ЧПМ несёт печатаемую маржу модальной клетки на книге (при корне — `null`)."""
    rows = []
    for ax in book.get("valuation.reverse_dcf.axes") or []:
        rows.append({"key": U.axis_key(ax), "name": ax["name"], "kind": ax.get("kind", "value"),
                     "unit": ax.get("unit", ""), "paths": list(ax["paths"]), "book": _book_value(book, ax),
                     "range": [float(x) for x in ax["range"]], "solved": None, "delta": None, "in_range": False,
                     "status": "not_computed", "gap": None, "point_solved": None, "point_status": "not_computed",
                     "reason": reason, **_printed(book, ax, run)})
    bank = [{"key": k, "title": bank_title(book, k), "unit": BANK_UNITS.get(k, ""), "book": None,
             "implied": None, "delta": None, "status": "not_computed", "reason": reason}
            for k in book.get("valuation.reverse_dcf.bank_rows") or []]
    return {"target": None, "number": "median", "method": reason, "rows": rows, "bank_rows": bank}


BANK_TITLES = {
    "implied_roe_through_cycle": "Вменённый ROE {lt_level}",
    "implied_cost_of_equity": "Вменённая стоимость капитала",
    "market_cap_minus_bv": "Рынок: капитализация − капитал",
    # пределы и срок второй формы банка (М§11.3)
    "value_without_excess_growth": "Стоимость без опережающего роста",
    "book_value_per_share": "Капитал без премии",
    "excess_return_years": "В цене — лет избыточной доходности",
}
PREMIUM_PATHS = ("volumes.loan_share_drift", "volumes.funds_share_drift")     # премии роста к сектору (М§4.3)


def bank_title(book: Book, key: str) -> str:
    """Заголовок банковской строки: слова кода с термином книги (`meta.labels.terms.lt_level`, М§0.6)."""
    return BANK_TITLES.get(key, key).format(lt_level=book.label("terms.lt_level"))


BANK_UNITS = {"implied_roe_through_cycle": "доля", "implied_cost_of_equity": "доля",
              "market_cap_minus_bv": "млрд ₽", "value_without_excess_growth": "₽", "book_value_per_share": "₽",
              "excess_return_years": "лет"}


def premium_facts(book: Book) -> frozenset[str]:
    """Элементы траекторий премий роста, которые книга называет фактом, а не суждением о будущем, — ключ книги
    `valuation.reverse_dcf.premium_facts`: список путей вида `<премия>.<сектор>.<ключ времени>` (например, ключ
    года якоря премии средств клиентов, внесённый по месячным фактам). Нет ключа — пусто: строка «без
    опережающего роста» снимает все ключи (образец). Путь вне траекторий премий или без числа в книге — отказ."""
    paths = [str(p) for p in book.opt(PREMIUM_FACTS) or ()]
    for p in paths:
        head, _, last = p.rpartition(".")
        root = head.rpartition(".")[0]
        if root not in PREMIUM_PATHS or last == "LT_from" or not isinstance(book.opt(head), Mapping) \
                or not isinstance(book.opt(p), (int, float)) or isinstance(book.opt(p), bool):
            raise BookError(f"{PREMIUM_FACTS}: {p} — не элемент траектории премии роста "
                            f"({', '.join(PREMIUM_PATHS)}; М§11.3)")
    return frozenset(paths)


def no_premium_overrides(book: Book) -> dict[str, Any]:
    """Подмены книги «опережающий рост кончился сегодня» (М§11.3): премии роста кредитов и средств клиентов —
    нули по всем ключам (у словаря траекторий — по каждому сектору, у числа — само число). Траектория сектора
    остаётся траекторией с теми же ключами времени (нули; `LT_from` — как в книге): на её элементах могут стоять
    пути оси-связки полосы (М§10), и книга с подменой обязана проходить ту же схему. Элементы, названные книгой
    фактом (`valuation.reverse_dcf.premium_facts`), остаются как в книге: строка снимает суждение об
    опережающем росте, а не уже случившийся приток или отток."""
    kept = premium_facts(book)
    out: dict[str, Any] = {}
    for path in PREMIUM_PATHS:
        value = book.get(path)
        if isinstance(value, Mapping):
            out.update({f"{path}.{key}": ({k: (v if k == "LT_from" or f"{path}.{key}.{k}" in kept else 0.0)
                                          for k, v in sector.items()}
                                         if isinstance(sector, Mapping) else 0.0)
                        for key, sector in value.items()})
        else:
            out[path] = 0.0
    return out


def excess_by_year(run: GridRun, lam: float | None = None) -> list[dict[str, Any]]:
    """Накопленная приведённая стоимость остаточного дохода смеси заголовка по годам, млрд ₽ (М§11.3):
    PV_Y = Σ_c P(c) × Σ RI_c,q × DF_v(τ_q) по кварталам от квартала даты оценки до конца года Y; последняя
    строка — с терминалом (год после последнего года явного участка). Вероятности клеток — λ-смесь слоёв."""
    lam = run.lam if lam is None else lam
    lo, hi = run.layers["macro_neutral"].prob, run.layers["analytical"].prob
    prob = {c.key: lo[c.key] + lam * (hi[c.key] - lo[c.key]) for c in run.cells}
    tl, q0 = run.ctx.timeline, run.ctx.clock.q0
    rows, total = [], 0.0
    for year in range(tl.year(q0), tl.last_year + 1):
        qs = [q for q in tl.quarters_of_year(year) if q0 <= q <= tl.Q]
        total += sum(prob[c.key] * c.pv_ri_q[q] for c in run.cells for q in qs)
        rows.append({"year": year, "pv_excess_cum": total})
    total += sum(prob[c.key] * c.pv_terminal for c in run.cells)
    rows.append({"year": tl.last_year + 1, "pv_excess_cum": total})
    return rows


def excess_years(by_year: Sequence[Mapping[str, Any]], market_excess: float | None) -> int | None:
    """Сколько лет избыточной доходности модели оплачено рыночной ценой (М§11.3): номер первой строки, на
    которой накопленная стоимость не меньше рыночной Cap − BV_v; 0 — пока рынок платит не больше капитала;
    None — не хватает и строки с терминалом (или капитализации нет)."""
    if market_excess is None:
        return None
    if market_excess <= 0:
        return 0
    return next((i for i, r in enumerate(by_year, 1) if r["pv_excess_cum"] >= market_excess), None)


def _full_gap(trial: Book, facts: Facts, live: LiveInputs, band: U.Band, anchor: U.MedianAnchor, lam: float,
              px: float) -> float:
    """Невязка медианы полной полосы книги `trial` к цене (одна полоса `band.draws` прогонов)."""
    full = U.band(trial, facts, live, draws=band.draws, like=band)
    anchor.full_grids += full.draws
    return full.medians(lam)["central"] - px


def _refine_full(g: Callable[[float], float], b: float, gb: float, x: float, lo: float, hi: float, steps: int,
                 tol: float) -> tuple[float, float, float]:
    """Уточнение корня на полной полосе (М§11.2): секущая от точки книги (b, gb) через решение подвыборки x,
    не больше `steps` пересчётов `g`, шаги не выходят из [lo; hi]; невязка в стопе `tol` — уточнение кончено.

    → (решение — вычисленная точка с наименьшей невязкой, её невязка, оценка корня секущей по двум последним
    точкам). Оценка нужна, когда уточнение не сошлось: по ней видно, по какую сторону края диапазона корень."""
    pts = [(b, gb)]
    estimate = x
    for _ in range(steps):
        gx = g(x)
        pts.append((x, gx))
        (xb, fb), (xa, fa) = pts[-2], pts[-1]
        estimate = min(max(xa - fa * (xa - xb) / (fa - fb) if fa != fb else xa, lo), hi)
        if abs(gx) <= tol:
            break
        x = estimate
    value, gap = min(pts[1:], key=lambda t: abs(t[1]))
    return value, gap, (value if abs(gap) <= tol else estimate)


def on_search_edge(value: float | None, book_value: float, lo: float, hi: float) -> bool:
    """Корень стоит на краю отрезка поиска (М§11.2): поиск упёрся в край, решением он не считается —
    «недостижимо в поиске». Значение книги на краю отрезка (медиана уже равна цене) — решение."""
    return value is not None and value != book_value and value in (lo, hi)


def near_range_edge(book: Book, gap_at: Callable[[float], float], value: float, low: float, high: float) -> bool:
    """Решение подвыборки стоит за краем диапазона книги, но не дальше её собственной ошибки (М§11.2): при ключе
    книги `valuation.reverse_dcf.edge_refine_rub` невязка подвыборки `gap_at` на ближнем краю диапазона по
    модулю не больше порога ключа (один пересчёт подвыборки). Такое решение уточняется на полной полосе
    наравне с решением внутри диапазона. Нет ключа или решение внутри диапазона — False."""
    limit = book.opt(EDGE_REFINE)
    if limit is None or low <= value <= high:
        return False
    return abs(gap_at(high if value > high else low)) <= float(limit)


def refine_rows(book: Book) -> frozenset[str] | None:
    """Строки обратного расчёта, корень которых уточняется на полной полосе (М§11.2), — ключ книги
    `valuation.reverse_dcf.refine_rows`: список ключей строк (`rows[].key`). Нет ключа — None: уточняется любая
    строка по правилу диапазона (образец). Ключ, которого нет среди строк книги, — отказ."""
    named = book.opt(REFINE_ROWS)
    if named is None:
        return None
    keys = {U.axis_key(ax) for ax in book.get("valuation.reverse_dcf.axes") or []}
    lost = [str(k) for k in named if str(k) not in keys]
    if lost:
        raise BookError(f"{REFINE_ROWS}: нет строки обратного расчёта с ключом {', '.join(lost)} (М§11.2)")
    return frozenset(str(k) for k in named)


def refines_on_full_band(named: frozenset[str] | None, key: str) -> bool:
    """Уточняется ли корень строки `key` на полной полосе: строку называет список книги (`refine_rows`); списка
    нет (None) — любая строка, как у образца."""
    return named is None or key in named


def root_in_range(value: float | None, gap: float | None, estimate: float | None, low: float, high: float,
                  tol: float) -> bool:
    """«В диапазоне книги» — о корне, а не о приближении (М§11.2): решение с невязкой в стопе лежит в
    [low; high]; у несошедшегося уточнения в диапазоне лежат и приближение, и оценка корня секущей."""
    if value is None or not low <= value <= high:
        return False
    if gap is None or abs(gap) <= tol or estimate is None:
        return True
    return low <= estimate <= high


def reverse_dcf(book: Book, facts: Facts, live: LiveInputs, band: U.Band, *,
                anchor: U.MedianAnchor | None = None, run: GridRun | None = None) -> dict[str, Any]:
    """П§2 reverse_dcf: строки по осям книги и банковские строки (М§11)."""
    main = str(book.get("meta.company.main_ticker"))
    px = float(live.prices[main])
    lam = band.lam
    tol = float(book.get("valuation.headline.search_tol_rub"))
    follow = book.get("valuation.uncertainty.reverse_bounds") == "follow_center"
    refine = min(int(book.get("valuation.uncertainty.median_refine")), MAX_REFINE)
    sub = int(book.get("valuation.reverse_dcf.subsample"))
    run = run or run_grid(book, facts, live)
    if anchor is None or anchor.n != sub:
        anchor = U.MedianAnchor(book, facts, live, band, n=sub)
    median_full = band.medians(lam)["central"]
    median_gap = median_full - px
    point_gap = run.point - px
    rows, solutions = [], {}
    named = refine_rows(book)                   # строки с уточнением на полной полосе; None — все (образец)
    paths: dict = {}                            # проходы клеток сеток поиска: суждение вне прохода — одна оценка
    for ax in book.get("valuation.reverse_dcf.axes") or []:
        kind = ax.get("kind", "value")
        b = _book_value(book, ax)
        lo, hi = (float(x) for x in ax["search"])
        rlo, rhi = (float(x) for x in ax["range"])

        def trial(v: float, ax=ax) -> Book:
            return reverse_trial(book, ax, v, follow=follow)

        pg = _Recorder(lambda v, trial=trial: run_grid(trial(v), facts, live, summary=True,
                                                       paths=paths).point - px)
        p, p_gap = bisect_point(pg, lo, hi, tol=tol)
        mg = _Recorder(lambda v, trial=trial: anchor.at(trial(v), lam=lam)["central"] - px)
        mg.seen[b] = median_gap
        if p is not None:
            sense = _sign(p - b) * _sign(-point_gap)
        else:
            sense = _sign(pg(hi) - pg(lo))
        direction = sense * _sign(-median_gap)
        value, used = None, 0
        if abs(median_gap) <= tol:
            value = b
        elif direction:
            end = hi if direction > 0 else lo
            x1 = end if p is None else b + direction * SEED_FACTOR * abs(p - b)
            x1 = min(x1, hi) if direction > 0 else max(x1, lo)
            value, used = solve_outward(mg, b, median_gap, x1, end, tol=tol)
        gap, basis, estimate = None, "subsample", None
        if value is not None:
            gap = mg(value)
            full = refines_on_full_band(named, U.axis_key(ax))   # строку не назвал ключ книги — корень подвыборки
            if (refine > 0 and value != b and full
                    and (rlo <= value <= rhi or near_range_edge(book, mg, value, rlo, rhi))):
                value, gap, estimate = _refine_full(
                    lambda x, trial=trial: _full_gap(trial(x), facts, live, band, anchor, lam, px),
                    b, median_gap, value, lo, hi, refine, tol)
                basis = "full"
        else:
            near = mg.best()
            gap = None if near is None else near[1]
        # корень на краю отрезка поиска (не значение книги) — не решение: поиск упёрся в край (М§11.2)
        edge = on_search_edge(value, b, lo, hi)
        if edge:
            value, estimate = None, None
        status = "solved" if value is not None else "unreachable"
        solutions[U.axis_key(ax)] = (ax, value)
        row = {
            "key": U.axis_key(ax), "name": ax["name"], "kind": kind, "unit": ax.get("unit", ""),
            "paths": list(ax["paths"]), "book": b, "range": [rlo, rhi], "search": [lo, hi],
            "solved": value, "delta": None if value is None else value - b,
            "in_range": root_in_range(value, gap, estimate, rlo, rhi, tol), "status": status, "gap": gap,
            "gap_basis": basis, "converged": not edge and gap is not None and abs(gap) <= tol, "point_solved": p,
            "point_gap": p_gap, "point_status": "solved" if p is not None else "unreachable", "evaluations": used,
        }
        if edge:
            row["reason"] = EDGE_REASON
        printed = _printed(book, ax, run)
        if printed and value is not None:       # суждение о марже при корне — один счёт сетки
            _printed_at_root(printed, run_grid(trial(value), facts, live))
        rows.append({**row, **printed})
    bank = bank_rows(book, facts, live, run, solutions, follow=follow, paths=paths)
    method = (f"медиана — подвыборка {grouped(sub)} прогонов с общими случайными числами и поправкой к полной "
              f"медиане; поиск — секущая наружу и обратная квадратичная, стоп {num(tol, 2)} ₽; решение внутри "
              f"диапазона книги уточняется на полной полосе ({grouped(band.draws)} прогонов, шагов — не больше "
              f"{refine}, до невязки в стопе), пометка «в диапазоне книги» относится к корню, а не к приближению; "
              f"точка — бисекция ≤ {BISECT_STEPS} шагов. Ось полосы разыгрывается вокруг проверяемого значения, "
              "ось вне полосы стоит на нём: строки решаются по-разному, и решения разных строк не перемножаются")
    if axis_follow(book) == FOLLOW_BOTH:
        method += ("; за проверяемым значением идут оба конца оси — она сдвигается вместе с центром и остаётся в "
                   "отрезке поиска строки; корень на краю отрезка поиска решением не считается")
    if book.opt(EDGE_REFINE) is not None:
        method += ("; решение подвыборки за краем диапазона уточняется на полной полосе, когда невязка подвыборки "
                   f"на краю диапазона не больше {num(float(book.opt(EDGE_REFINE)), 2)} ₽")
    out = {"target": px, "number": "median", "method": method, "rows": rows, "bank_rows": bank,
           "subsample": sub, "evaluations": anchor.evaluations, "full_grids": anchor.full_grids}
    if named is not None:                       # список книги: прочие строки — оценка по подвыборке
        out["method"] += (f"; на полной полосе уточняются только строки, названные книгой ({len(named)} из "
                          f"{len(rows)}): у прочих решение и пометка «в диапазоне книги» — оценка по подвыборке")
        out["refine_rows"] = [r["key"] for r in rows if r["key"] in named]
    return out


def _row_for(book: Book, solutions: Mapping[str, tuple], paths: Sequence[str]):
    for key, (ax, value) in solutions.items():
        if any(p in ax["paths"] for p in paths):
            return ax, value
    return None, None


def bank_rows(book: Book, facts: Facts, live: LiveInputs, run: GridRun,
              solutions: Mapping[str, tuple], *, follow: bool, paths: dict | None = None) -> list[dict[str, Any]]:
    """Банковские строки М§11.3 по списку `valuation.reverse_dcf.bank_rows`. Сетки строк — лёгкие; `paths` —
    хранилище проходов клеток поиска (`model.grid.run_grid`)."""
    lam = run.lam
    paths = {} if paths is None else paths
    base = bank_language(run, lam)
    out = []
    worlds = list(book.get("worlds.ids"))

    def k_by_world(r: GridRun) -> dict[str, float]:
        return {w: sum(c.k_t for c in r.cells if c.world == w) / sum(1 for c in r.cells if c.world == w)
                for w in worlds}

    for key in book.get("valuation.reverse_dcf.bank_rows") or []:
        row = {"key": key, "title": bank_title(book, key), "unit": BANK_UNITS.get(key, "")}
        if key == "implied_roe_through_cycle":
            ax, value = _row_for(book, solutions, list(sensitivity_overrides(book, "nim")))
            implied = None
            if ax is not None and value is not None:
                implied = bank_language(run_grid(reverse_trial(book, ax, value, follow=follow), facts, live,
                                                 summary=True, paths=paths), lam)["roe_tc"]
            row.update(book=base["roe_tc"], implied=implied,
                       delta=None if implied is None else implied - base["roe_tc"],
                       status="solved" if implied is not None else "unreachable",
                       row=None if ax is None else U.axis_key(ax))
        elif key == "implied_cost_of_equity":
            ax, value = _row_for(book, solutions, [ERP_PATH])
            implied, by_world = None, None
            if ax is not None and value is not None:
                r2 = run_grid(reverse_trial(book, ax, value, follow=follow), facts, live, summary=True,
                              paths=paths)
                implied, by_world = bank_language(r2, lam)["k_tc"], k_by_world(r2)
            row.update(book=base["k_tc"], implied=implied,
                       delta=None if implied is None else implied - base["k_tc"],
                       status="solved" if implied is not None else "unreachable",
                       by_world=by_world, book_by_world=k_by_world(run),
                       row=None if ax is None else U.axis_key(ax))
        elif key == "market_cap_minus_bv":
            cap = base["market_cap"]
            implied = None if cap is None else cap - base["bv_v"]
            row.update(book=base["excess_point"], implied=implied,
                       delta=None if implied is None else implied - base["excess_point"],
                       status="computed" if implied is not None else "unreachable")
        elif key == "value_without_excess_growth":
            flat = run_grid(book.with_overrides(no_premium_overrides(book)), facts, live, summary=True).point
            row.update(book=run.point, implied=flat, delta=flat - run.point, status="solved")
        elif key == "book_value_per_share":
            per_share = base["bv_v"] * THOUSAND / run.divisor
            row.update(book=run.point, implied=per_share, delta=per_share - run.point, status="solved")
        elif key == "excess_return_years":
            cap = base["market_cap"]
            market_excess = None if cap is None else cap - base["bv_v"]
            by_year = excess_by_year(run, lam)
            years = excess_years(by_year, market_excess)
            row.update(book=None, implied=years, delta=None, status="solved" if years is not None else "unreachable",
                       by_year=by_year, market_excess=market_excess)
        else:
            raise BookError(f"valuation.reverse_dcf.bank_rows: незнакомая строка {key!r}")
        out.append(row)
    return out
