# -*- coding: utf-8 -*-
"""Независимая контрольная модель панели — ГОДОВАЯ, с квартальным проходом капитала (docs/MODEL.md §17).

Написана только по тексту docs/MODEL.md, книге (data/assumptions/) и фактам (data/facts/);
каталог ядра не импортируется и не читается (tests/test_control_independence.py). Шаг —
год: неполный год якоря — один период (доля года = оставшиеся кварталы / 4), далее годы до
года last_period, терминал М§7 в годовой форме. Две ветви — по ключам книги: без квартального
календаря дивидендов и без ограничения роста — годовая ветвь образца (решение раз в год); с ними —
годовые строки ОПУ и квартальный проход капитала внутри года (остатки кредитных книг, RWA, нормативы,
требование с глиссадой, решения о дивиденде, доля прироста и навёрстывание — по кварталам). Что
считается иначе, чем в ядре, и почему совпадение ожидается только в допусках — docs/CONTROL-MODEL.md.

Чисел книги и фактов в коде нет: только имена ключей и структурные константы (кварталов в
году, дней в году по act/365, млрд → млн, технические допуски итераций).

Запуск:
    python -B tests/independent_model.py                      сводка на машинной книге и фактах
    python -B tests/independent_model.py --json out.json      то же + полный результат в JSON
    python -B tests/independent_model.py --gates              то же + числа гейтов знака, печатаемая маржа и уровни
                                                              после фазы роста (М§14.2)
    python -B tests/independent_model.py --draft --worlds-lt N=<доля>,H=<доля> [--facts DIR]
        шаблон книги (assumptions_template.yaml) + миры из worlds_source.json и надстройка
        worlds_bank.json (узел LT кривой миров N и H — правило сборки семейства, передаётся явно;
        M — правило рецепта)
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import math
import sys
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK_DIR = ROOT / "data" / "assumptions"
BOOK_YAML = BOOK_DIR / "assumptions.yaml"
DRAFT_YAML = BOOK_DIR / "assumptions.draft.yaml"
TEMPLATE_YAML = BOOK_DIR / "assumptions_template.yaml"
WORLDS_SOURCE = BOOK_DIR / "worlds_source.json"
WORLDS_BANK = BOOK_DIR / "worlds_bank.json"
FACTS_DIR = ROOT / "data" / "facts"

LAYERS = ("analytical", "market_implied", "macro_neutral")
LAYER_OWN, LAYER_MARKET = LAYERS[0], LAYERS[-1]     # слои «свой взгляд» и «рыночные ставки как есть» (М§9)
# Миры из текста методики: реализованная передача — разность M и N (М§4.5); κ-добавка к CoR без ключа
# книги — относительно мира N и только вверх, с ключом credit.kappa_reference_world — относительно
# названного им мира-опоры, с любым знаком (М§4.6).
W_LOW = "N"
W_MKT = "M"
SCOPE_MARKET = "market_layer"       # checks.cir_lt.scope: цель C/I сверяется со слоем «рыночные ставки как есть»
SCOPE_MODAL = "modal_cell"          # явное имя умолчания: модальная клетка, как без ключа scope
FADE_SYMMETRIC = "symmetric"        # valuation.terminal.fade_mode справочного варианта таблиц книги (М§7)
MIX_MODAL, MIX_POINT = "modal", "point"     # смеси узла уровней сверх слоёв: модальная клетка и смесь точки
R_NORM = "norm"             # режим, к которому относится цель A-N2 и кредитная маржа стационара (М§4.5)
R_CRISIS = "crisis"         # режим с годом шока, разовым убытком и отменой выплаты (М§3.2, §5.3)
QY = 4                      # кварталов в году
DAYS_BASE = 365.0           # act/365 (М§0.3)
LOANS_SIDE = "asset"
RETAIL_CURRENT = "retail_current"   # книги ФЛ, доля которых — функция ключевой (М§4.3)
RETAIL_TERM = "retail_term"
CORP_LOANS = "corp_loans"           # таблица состава книг образца (ветвь его фактов, М§17)
SECURITIES = "securities"
LIQUIDITY = "liquidity"
WHOLESALE = "wholesale"
CORP_FUNDS = "corp_funds"
FIT_ITER = 60               # итераций фиксированной точки балансирующих статей, деления отрезка и года
FIT_TOL = 1e-11
PLAN_TOL = 1e-9             # сходимость квартального плана года (доли остатка книги; млрд ₽ дивиденда)
WH_NOISE = 1e-9             # добор опта на начало периода не больше 1e-9 × опт (не меньше 1e-9 млрд ₽) — шум суммирования, 0
FREQ_QUARTERLY = "quarterly"        # dividends.calendar.frequency (М§5.1)
ORDER_DIV_FIRST = "dividend_first"  # capital.growth_constraint.order (М§4.13)
ORDER_GROWTH_FIRST = "growth_first"
BASIS_ISSUED = "issued"             # valuation.shares_basis (М§8.4)
HIST_EXACT, HIST_CAP, HIST_NONE = "exact", "cap", "none"   # dividends.policy.history_test (М§5.2)
LINK_BASES = ("loans", "funds", "iea")                      # volumes.link_base (М§4.7)
OPEX_BASE = "opex_weighted"         # база расходов, взвешенная по себестоимости книг (ключ opex.volume_weights)
LINE_KEY, NOMINAL_KEY, MIX_KEY = "line", ("nominal",), ("opex_mix",)     # записи баз строк К2 по кварталам
FRANCHISE_NOM_KEY = "franchise_nominal"     # запись номинальной части франшизы строки H^ℓ по кварталам (Р8-6)
# Р10-5 (проход ядра 8, ключ volumes.line_link_form: line): франшиза строки и книга К6 — формой строки; записи по кварталам
FRANCHISE_PHI_KEY = "franchise_phi"         # франшиза строки Φ^ℓ квартала
FRANCHISE_BASE_KEY = "franchise_base"       # средняя базы строки A^ℓ квартала (г/г франшизы)
K6_PSI_KEY, K6_END_KEY = "k6_psi", "k6_end"  # индекс Ψ ведомой книги и уровень базы её строки D на конце квартала
LOAN_SECTORS = ("corporate", "mortgage", "retail_other")    # ключи словаря премии роста кредитов (М§4.3)
FUND_SEGMENTS = ("retail", "corporate")                     # ключи словаря премии средств клиентов
# Ключи третьего прохода ядра Совкомбанка (core-pass3): К-Т2 — терминал, сверенный с явными годами; К8 — деньги за своим
# драйвером; К2б — смесь баз строки.
MEAN_YEAR = 365.2425        # средняя длина года, дней (григорианская): вечный поток терминала — средний год (К-Т2а)
YEAR_BASES = ("calendar", "mean")                           # valuation.terminal.year_basis
YEAR_CALENDAR, YEAR_MEAN = YEAR_BASES
FUNDINGS = ("binary", "balancing")                          # valuation.terminal.fixed_funding
FUND_BINARY, FUND_BALANCING = FUNDINGS
RATES_LAGGED, RATES_STATIONARY = "lagged", "stationary"     # ставки терминала: конца Q или цели года L (К4)
BALANCING_BOOKS = (SECURITIES, LIQUIDITY, WHOLESALE)
CASH_WORDS = ("funds", "loans")     # драйвер денег К8 словом: средства клиентов или кредитные книги (иначе — веса книг)
MIX_FIELD = "mix"                   # форма смеси баз строки К2б: {mix: {имя: {share, base}}}
# Ключ пятого прохода ядра Совкомбанка (Р6-1): доля денег К8 — параметр книги, необязательные поля volumes.cash_assets
CASH_SHARE_FIELDS = ("share", "reserves", "share_from", "displaced_weight")


class ControlInputError(ValueError):
    """Книга или факты не дают того, что нужно контрольной модели (громкий отказ)."""


class ControlUnsupported(ValueError):
    """Ветка методики, которую контрольная модель не поддерживает. На настоящей книге — провал теста, не
    пропуск (М§17): отказ остаётся только у модулей, выключенных самой методикой (М§0.6)."""


# ============================================================================ ввод: книга

def _c_read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def c_book_machine(path: Path | None = None) -> dict:
    """Машинная книга data/assumptions/assumptions.yaml (миры и надстройка уже внутри)."""
    p = Path(path) if path else BOOK_YAML
    if not p.exists():
        raise ControlInputError(f"нет машинной книги {p.name}")
    return _c_read_yaml(p)


def c_book_from_draft(draft: Path | None = None, *, worlds_source: Path | None = None,
                    overlay: Path | None = None, curve_lt: dict | None = None) -> dict:
    """Шаблон книги (по умолчанию assumptions_template.yaml, иначе черновик) + блоки worlds.<W> и
    worlds_bank.<W> по таблице М§3.1 — независимая сборка машинной книги.

    Узел LT бескупонной кривой: M — правило рецепта (ОФЗ 10 лет последнего полугодия, до 0,1
    п.п.), N и H — правило сборки семейства (передаётся явно, в коде чисел нет). Строки-метки
    шаблона — комментарии YAML, поэтому шаблон читается как книга без миров.
    """
    src_book = Path(draft) if draft else (TEMPLATE_YAML if TEMPLATE_YAML.exists() else DRAFT_YAML)
    book = _c_read_yaml(src_book)
    src = json.loads(Path(worlds_source or WORLDS_SOURCE).read_text(encoding="utf-8"))
    ovl = json.loads(Path(overlay or WORLDS_BANK).read_text(encoding="utf-8"))
    curve_lt = dict(curve_lt or {})
    fields = {"key_rate": "key_avg", "cpi": "cpi_yoy_avg", "wage_growth": "nominal_wage_yoy",
              "ofz_1y": "ofz_1y", "ofz_3y": "ofz_3y", "ofz_5y": "ofz_5y", "ofz_10y": "ofz_10y",
              "real_key": "real_key_fwd12m"}
    pct = 100.0
    for w in book["worlds"]["ids"]:
        rows = [r for r in src["rows"] if r["world"] == w]
        blk = {"name": w}
        for key, col in fields.items():
            blk[key] = {r["period"]: r[col] / pct for r in rows}
        curve = {str(k): v / pct for k, v in src["fair_zero_curve_today"][w].items()}
        if w not in curve_lt:
            if w != W_MKT:
                raise ControlInputError(f"узел LT кривой мира {w}: передайте --worlds-lt")
            curve_lt[w] = round(rows[-1]["ofz_10y"], 1) / pct
        curve["LT"] = float(curve_lt[w])
        blk["zero_curve"] = curve
        blk["lt_inflation"] = src["lt_inflation"][w] / pct
        book["worlds"][w] = blk
    book["worlds_bank"] = {w: ovl["worlds"][w] for w in book["worlds"]["ids"]}
    return book


def c_bget(book: dict, dotted: str):
    """Значение книги по точечному пути; нет ключа — громкий отказ."""
    cur = book
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, dict) and part.isdigit() and int(part) in cur:
            cur = cur[int(part)]
        else:
            raise ControlInputError(f"в книге нет ключа {dotted}")
    return cur


def c_bnum(book: dict, dotted: str) -> float:
    v = c_bget(book, dotted)
    if v is None or isinstance(v, (dict, list, str, bool)):
        raise ControlInputError(f"ключ книги {dotted} — не число: {v!r}")
    return float(v)


def c_bopt(book: dict, dotted: str, default=None):
    """Необязательный (поведенческий) ключ книги: нет ключа или null — умолчание (М§0.6: «ключа нет»)."""
    cur = book
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return default if cur is None else cur


def c_is_quarterly(book: dict) -> bool:
    """Квартальный календарь дивидендов (М§5.7); без ключа frequency — годовой режим образца."""
    return c_bopt(book, "dividends.calendar.frequency") == FREQ_QUARTERLY


def c_growth_rule(book: dict):
    """Параметры ограничения роста капиталом (М§4.13) или None: объекта нет либо enabled: false."""
    gc = c_bopt(book, "capital.growth_constraint")
    if not isinstance(gc, dict) or not gc.get("enabled"):
        return None
    for key in ("order", "min_growth_scale", "lookahead_quarters", "glide_pp_per_quarter", "catch_up_rate", "tol"):
        if gc.get(key) is None:
            raise ControlInputError(f"capital.growth_constraint.{key}: нет поля при enabled: true (М§4.13)")
    if gc["order"] not in (ORDER_DIV_FIRST, ORDER_GROWTH_FIRST):
        raise ControlInputError("capital.growth_constraint.order — не dividend_first и не growth_first")
    lam_min, cu = float(gc["min_growth_scale"]), float(gc["catch_up_rate"])
    if not (0.0 <= lam_min <= 1.0 and 0.0 <= cu <= 1.0 and float(gc["glide_pp_per_quarter"]) >= 0.0
            and float(gc["tol"]) > 0.0 and int(gc["lookahead_quarters"]) >= 0):
        raise ControlInputError("capital.growth_constraint: поле вне границ (М§4.13)")
    if not c_is_quarterly(book):
        raise ControlInputError("ограничение роста требует квартального календаря дивидендов (М§4.13)")
    if int(c_bnum(book, "volumes.guidance_year")) >= c_per_parse(c_bget(book, "meta.first_period"))[0]:
        raise ControlInputError("ограничение роста при годе гайденса внутри сетки (М§4.3)")
    return {"order": gc["order"], "lam_min": lam_min, "ahead": int(gc["lookahead_quarters"]),
            "glide": float(gc["glide_pp_per_quarter"]), "catch_up": cu, "tol": float(gc["tol"])}


# ============================================================================ ввод: факты

def c_facts_bundle(root: Path | None = None) -> dict:
    """Все data/facts/*.json как словари {имя файла: содержимое}."""
    d = Path(root) if root else FACTS_DIR
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files:
        raise ControlInputError(f"нет фактов в {d}")
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in files}


def _c_dig(tree, dotted: str):
    cur = tree
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise ControlInputError(f"нет узла {dotted}")
    return cur


def c_fval(facts: dict, file: str, dotted: str, *, null_ok: bool = False):
    """Значение узла факта {v, src|calc}; null — отказ (null ≠ 0), если не разрешено явно."""
    if file not in facts:
        raise ControlInputError(f"нет файла фактов {file}.json")
    node = _c_dig(facts[file], dotted)
    val = node.get("v") if isinstance(node, dict) and "v" in node else node
    if val is None:
        if null_ok:
            return None
        raise ControlInputError(f"null в узле {file}:{dotted}")
    return val


def c_fnum(facts: dict, file: str, dotted: str) -> float:
    return float(c_fval(facts, file, dotted))


def _c_quarter_rows(pnl: dict) -> dict[str, dict]:
    """Кварталы pnl_quarterly.json в виде {период: {строка: узел}} (допускаются формы
    «словарь периодов» и «список записей с полем period»)."""
    for key in ("quarters", "periods", "rows", "data"):
        if key in pnl:
            body = pnl[key]
            break
    else:
        body = {k: v for k, v in pnl.items() if isinstance(k, str) and "Q" in k and k[:4].isdigit()}
    if isinstance(body, list):
        return {str(r["period"]): r for r in body}
    return {str(k): v for k, v in body.items()}


def _c_nodeval(node):
    if isinstance(node, dict):
        return node.get("v")
    return node


# ============================================================================ время

def c_per_parse(p: str) -> tuple[int, int]:
    """«2026Q3» → (2026, 3)."""
    y, q = str(p).upper().split("Q")
    return int(y), int(q)


def c_q_first_day(y: int, q: int) -> dt.date:
    return dt.date(y, 3 * (q - 1) + 1, 1)


def c_q_last_day(y: int, q: int) -> dt.date:
    ny, nq = (y + 1, 1) if q == QY else (y, q + 1)
    return c_q_first_day(ny, nq) - dt.timedelta(days=1)


def c_q_len(y: int, q: int) -> int:
    return (c_q_last_day(y, q) - c_q_first_day(y, q)).days + 1


def _c_as_date(x) -> dt.date:
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x))


def c_annual_periods(book: dict) -> list[dict]:
    """Периоды годовой модели: остаток года якоря (если он есть) и полные годы до last_period."""
    y0, qa = c_per_parse(c_bget(book, "meta.anchor_period"))
    yl, ql = c_per_parse(c_bget(book, "meta.last_period"))
    if ql != QY:
        raise ControlUnsupported("last_period должен кончать год (терминал — с года после него)")
    fy, fq = c_per_parse(c_bget(book, "meta.first_period"))
    nxt = (y0 + 1, 1) if qa == QY else (y0, qa + 1)
    if (fy, fq) != nxt:
        raise ControlInputError("first_period — не квартал после якоря")
    out = []
    if qa < QY:
        out.append({"year": y0, "quarters": tuple(range(qa + 1, QY + 1)), "stub": True})
    for y in range(y0 + 1, yl + 1):
        out.append({"year": y, "quarters": tuple(range(1, QY + 1)), "stub": False})
    for p in out:
        y = p["year"]
        p["n"] = len(p["quarters"])
        p["days"] = sum(c_q_len(y, q) for q in p["quarters"])
        p["start"] = c_q_first_day(y, p["quarters"][0])
        p["end"] = c_q_last_day(y, p["quarters"][-1])
        p["label"] = str(y)
    return out


# ============================================================================ траектории (М§0.4)

def _c_time_keys(traj: dict) -> dict[str, tuple[int, int, int]]:
    """Ключи времени траектории → (год, первый квартал, последний квартал)."""
    out = {}
    for k in traj:
        s = str(k)
        if s in ("LT", "LT_from"):
            continue
        if len(s) == 4 and s.isdigit():
            out[s] = (int(s), 1, QY)
        elif "Q" in s:
            y, q = c_per_parse(s)
            out[s] = (y, q, q)
        elif "H" in s:
            y, h = s.split("H")
            out[s] = (int(y), 2 * int(h) - 1, 2 * int(h))
        else:
            raise ControlInputError(f"ключ траектории не разбирается: {s}")
    return out


def c_traj_at(traj, y: int, q: int) -> float:
    """Значение траектории книги в квартале (y, q) по правилу М§0.4."""
    if traj is None:
        raise ControlInputError("null в траектории")
    if isinstance(traj, (int, float)) and not isinstance(traj, bool):
        return float(traj)
    if not isinstance(traj, dict):
        raise ControlInputError(f"траектория не словарь: {traj!r}")
    t = {str(k): v for k, v in traj.items()}
    for key in (f"{y}Q{q}", f"{y}H{1 if q <= 2 else 2}", str(y)):
        if key in t:
            return float(t[key])
    tk = _c_time_keys(t)
    years = sorted(v[0] for k, v in tk.items() if len(k) == 4)
    lt = t.get("LT")
    if not tk:
        if lt is None:
            raise ControlInputError("траектория без ключей времени и без LT")
        return float(lt)
    if years and years[0] < y < years[-1]:
        lo = max(v for v in years if v < y)
        hi = min(v for v in years if v > y)
        a, b = float(t[str(lo)]), float(t[str(hi)])
        return a + (b - a) * (y - lo) / (hi - lo)
    order = sorted(tk.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    first_key, (fy, fq, _) = order[0]
    if (y, q) < (fy, fq):
        return float(t[first_key])                               # правило 6
    if years and y > years[-1]:
        last = float(t[str(years[-1])])
        if lt is None:
            return last
        lt_from = t.get("LT_from")
        if lt_from is None or y >= int(lt_from):
            return float(lt)
        span = int(lt_from) - years[-1]
        return last + (float(lt) - last) * (y - years[-1]) / span
    # после последнего ключа полугодия/квартала (миры) — последнее значение
    last_key = order[-1][0]
    if lt is not None and not years:
        return float(lt)
    return float(t[last_key])


def c_traj_mean(traj, y: int, quarters) -> float:
    """Среднее траектории по кварталам периода (год или остаток года якоря)."""
    return sum(c_traj_at(traj, y, q) for q in quarters) / len(quarters)


def c_spread_at(ctx: dict, b: str, y: int, q: int) -> float:
    """Спред книги в квартале: s_b(q) = путь + σ_b × [lt_shift] × [Y(q) ≥ nii.sigma0_from] (М§4.4),
    σ_b = +σ0_A у активов и −σ0_L у пассивов (М§4.5).

    Сдвиг прибавляется к значению пути во всех кварталах с года sigma0_from, а не к ключу LT:
    ближний участок (до sigma0_from) держит калибровку к ставкам якоря."""
    sp = ctx["B"]["nii"]["books"][b]
    s = c_traj_at(sp["spread"], y, q)
    if sp.get("lt_shift") and y >= ctx["sigma0_from"]:
        s += ctx["tr"]["sigma0"] if sp["side"] == LOANS_SIDE else -ctx["tr"]["sigma0_liab"]
    return s


# ============================================================================ подмены осей полосы: сложение связок (М§10, Р5-4)
# Полосы контрольная модель не считает (§8 документа). Эти функции — её прочтение правила М§10 о том, какое значение
# получает путь книги при положениях осей s: им тест сверяет подмены ядра и строит книгу угла, которую модель считает
# обычной сеткой. Оси вида value и dict здесь только запрещают общий путь со связкой: их значения правило не меняет.

AXIS_KINDS = ("value", "shift", "bundle", "dict")
AXIS_VALUE, AXIS_SHIFT, AXIS_BUNDLE, AXIS_DICT = AXIS_KINDS
COMPOSE_MODES = ("exclusive", "additive")     # valuation.uncertainty.bundle_compose (Р5-4); нет ключа — exclusive
COMPOSE_EXCLUSIVE, COMPOSE_ADDITIVE = COMPOSE_MODES
TRAJ_FROM = "LT_from"                          # ключ траектории, который оси не водят (М§0.4, §10)


def c_bset(book: dict, dotted: str, value) -> None:
    """Записать значение по точечному пути книги-словаря: путь обязан существовать (ключи года — строкой или числом,
    как в книге); нет пути — отказ (М§10: путь оси обязан существовать в книге)."""
    parts = dotted.split(".")
    cur = book
    for i, part in enumerate(parts):
        if not isinstance(cur, dict):
            raise ControlInputError(f"в книге нет ключа {dotted}")
        key = part if part in cur else int(part) if part.isdigit() and int(part) in cur else None
        if key is None:
            raise ControlInputError(f"в книге нет ключа {dotted}")
        if i == len(parts) - 1:
            cur[key] = value
        else:
            cur = cur[key]


def c_apply_overrides(book: dict, ov: dict) -> dict:
    """Копия книги-словаря с подменами {точечный путь: значение}."""
    out = copy.deepcopy(book)
    for path, v in ov.items():
        c_bset(out, path, v)
    return out


def c_bundle_compose(B: dict) -> str:
    """Правило общего пути связок (ключ valuation.uncertainty.bundle_compose, решения № 5, Р5-4): exclusive (и нет ключа)
    — путь несёт одна связка, общий путь двух связок — отказ; additive — связки на общем пути складываются приращениями
    от центра корневой книги. null или значение вне перечня — отказ (М§0.1)."""
    node = c_bopt(B, "valuation.uncertainty") or {}
    if "bundle_compose" not in node:
        return COMPOSE_EXCLUSIVE
    mode = node["bundle_compose"]
    if mode not in COMPOSE_MODES:
        raise ControlInputError(f"valuation.uncertainty.bundle_compose: {mode!r} — не {', '.join(COMPOSE_MODES)} (М§10)")
    return mode


def c_axis_leaves(book: dict, path: str) -> list[str]:
    """Числа книги, которые несёт путь оси: сам путь (число) или все ключи траектории по этому пути, кроме LT_from
    (ось вида shift на траектории сдвигает их все, М§10)."""
    v = c_bget(book, path)
    if isinstance(v, dict):
        return [f"{path}.{k}" for k in v if str(k) != TRAJ_FROM]
    if not c_is_number(v):
        raise ControlInputError(f"путь оси {path}: значение книги — не число и не траектория ({v!r}) (М§10)")
    return [path]


def _c_axis_terms(book: dict, root: dict, axes: list, s: list, compose: str) -> tuple[dict, dict, set]:
    """Слагаемые осей по числам книги: сдвиги осей вида shift ({число: [сдвиг]}), приращения связок ({число: [(|s|, конец,
    центр)]}) и числа, которые держат оси вида value и dict. Проверки формы связки: концы названы ровно по путям, путь не
    повторяется, путь — число книги, не LT_from."""
    shifts, terms, pinned = {}, {}, set()
    if len(axes) != len(s):
        raise ControlInputError(f"положений осей {len(s)}, а осей {len(axes)}")
    for ax, sj in zip(axes, s):
        kind, paths = ax.get("kind"), list(ax.get("paths") or ())
        if kind not in AXIS_KINDS:
            raise ControlInputError(f"ось {ax.get('name')!r}: вид {kind!r} — не {', '.join(AXIS_KINDS)} (М§10)")
        a = abs(float(sj))
        if kind == AXIS_SHIFT:
            amount = a * float(ax["high"] if sj >= 0 else ax["low"])
            for p in paths:
                for leaf in c_axis_leaves(book, p):
                    shifts.setdefault(leaf, []).append(amount)
        elif kind == AXIS_BUNDLE:
            if len(set(paths)) != len(paths) or any(set(map(str, ax[end])) != set(paths) for end in ("low", "high")):
                raise ControlInputError(f"связка {ax.get('name')!r}: концы не названы ровно по её путям или путь "
                                        f"повторяется (М§10)")
            end = ax["high"] if sj >= 0 else ax["low"]
            for p in paths:
                if p.rsplit(".", 1)[-1] == TRAJ_FROM or c_axis_leaves(book, p) != [p]:
                    raise ControlInputError(f"связка {ax.get('name')!r}: путь {p} — не число книги (М§10)")
                centre = c_bnum(book if compose == COMPOSE_EXCLUSIVE else root, p)
                terms.setdefault(p, []).append((a, float(end[p]), centre))
        else:
            pinned |= set(paths)
    return shifts, terms, pinned


def _c_pinned(path: str, pinned: set) -> str | None:
    """Путь оси вида value или dict, который держит число path (сам путь или словарь, внутри которого оно лежит)."""
    for q in pinned:
        if path == q or path.startswith(q + ".") or q.startswith(path + "."):
            return q
    return None


def c_bundle_draw(book: dict, axes: list, s: list, root: dict | None = None) -> dict[str, float]:
    """Значения чисел книги, которые несут оси-приращения (связки и сдвиги), при положениях осей s (М§10, Р5-4).

    Число p получает значение книги b_p плюс сумму приращений осей, стоящих на нём: сдвиг оси вида shift — |s| × конец
    (на самом p или на траектории, ключом которой p является); приращение связки k — |s_k| × (e_k,p − c_p), конец e — из
    high при s ≥ 0, иначе из low. Центр c_p: при bundle_compose: additive — значение p в корневой книге root (книга до
    подмен; root = None — сама книга): связка — суждение о приращении пути от центра, на котором выведен её конец, и
    подмена пробной книги на её пути сохраняется целиком; при exclusive (и без ключа) — значение самой книги, общий путь
    двух связок — отказ. Сумма — math.fsum всех слагаемых (точная, от порядка осей не зависит). Общий путь связки с осью
    вида value или внутри словаря оси вида dict — отказ при любом правиле. Все s = 0 — значения книги бит в бит."""
    compose = c_bundle_compose(book)
    shifts, terms, pinned = _c_axis_terms(book, book if root is None else root, axes, s, compose)
    for p, ts in terms.items():
        if compose == COMPOSE_EXCLUSIVE and len(ts) > 1:
            raise ControlInputError(f"путь {p} несут {len(ts)} оси вида bundle — общий путь связок без "
                                    f"valuation.uncertainty.bundle_compose: {COMPOSE_ADDITIVE} (М§10)")
        held = _c_pinned(p, pinned)
        if held is not None:
            raise ControlInputError(f"путь {p} несут связка и ось вида value или dict ({held}) — значение задаёт одна ось "
                                    f"(М§10)")
    out = {}
    for p in sorted(set(shifts) | set(terms)):
        parts = [c_bnum(book, p), *shifts.get(p, ())]
        parts += [a * (e - c) for a, e, c in terms.get(p, ())]
        out[p] = math.fsum(parts)
    return out


def c_bundle_corners(book: dict, axes: list, root: dict | None = None) -> dict[str, tuple[float, float]]:
    """Углы сложения осей (М§10, Р5-4): у числа, которое несут две и более оси-приращения (связки и сдвиги, в том числе
    сдвиг траектории), — наименьшее и наибольшее значение при осях на концах: c + Σ min(0, Δ_low, Δ_high) и
    c + Σ max(0, Δ_low, Δ_high), Δ связки — конец − центр (центр по правилу c_bundle_draw), Δ сдвига — его конец."""
    compose = c_bundle_compose(book)
    lo_s, hi_s = [-1] * len(axes), [1] * len(axes)
    sh_lo, tr_lo, _ = _c_axis_terms(book, book if root is None else root, axes, lo_s, compose)
    sh_hi, tr_hi, _ = _c_axis_terms(book, book if root is None else root, axes, hi_s, compose)
    out = {}
    for p in set(sh_lo) | set(tr_lo):
        d_lo = list(sh_lo.get(p, ())) + [a * (e - c) for a, e, c in tr_lo.get(p, ())]
        d_hi = list(sh_hi.get(p, ())) + [a * (e - c) for a, e, c in tr_hi.get(p, ())]
        if len(d_lo) < 2:
            continue
        b = c_bnum(book, p)
        out[p] = (math.fsum([b, *(min(0.0, x, y) for x, y in zip(d_lo, d_hi))]),
                  math.fsum([b, *(max(0.0, x, y) for x, y in zip(d_lo, d_hi))]))
    return out


# ============================================================================ кривая и дисконт (М§0.5)

def _c_curve_nodes(curve: dict) -> tuple[list[tuple[float, float]], float]:
    nodes = sorted((float(k), float(v)) for k, v in curve.items() if str(k) != "LT")
    return nodes, float(curve["LT"])


def c_zero_at(curve: dict, t: float) -> float:
    """Бескупонная ставка мира на срок t (годовое начисление)."""
    nodes, lt = _c_curve_nodes(curve)
    if t <= nodes[0][0]:
        return nodes[0][1]
    for (t1, z1), (t2, z2) in zip(nodes, nodes[1:]):
        if t <= t2:
            return z1 + (z2 - z1) * (t - t1) / (t2 - t1)
    tn, zn = nodes[-1]
    return ((1.0 + zn) ** tn * (1.0 + lt) ** (t - tn)) ** (1.0 / t) - 1.0


def c_df_world(curve: dict, add: float, t: float) -> float:
    """DF_W(t) = (1 + z(t) + β_E·ERP)^(−t)."""
    if t == 0.0:
        return 1.0
    return (1.0 + c_zero_at(curve, t) + add) ** (-t)


class CDisc:
    """Дисконт от даты оценки с перекатом по форвардам: DF_v(τ) = DF(Δ + τ) / DF(Δ)."""

    def __init__(self, curve: dict, add: float, shift: float):
        self.curve, self.add, self.shift = curve, add, shift
        self.base = c_df_world(curve, add, shift)

    def __call__(self, tau: float) -> float:
        return c_df_world(self.curve, self.add, self.shift + tau) / self.base


# ============================================================================ якорь из фактов

def _c_sum_nodes(facts: dict, file: str, base: str, parts: list[str], notes: list) -> float:
    """Сумма узлов; null-узел — «отдельно не раскрыт, входит в соседний» (записывается в notes)."""
    total = 0.0
    for part in parts:
        v = c_fval(facts, file, f"{base}.{part}", null_ok=True)
        if v is None:
            notes.append(f"{file}:{base}.{part} = null (не раскрыто отдельно) — не суммируется")
            continue
        total += float(v)
    return total


def _c_book_rate(facts: dict, b: str) -> float:
    nb = facts.get("nii_books")
    if nb is None:
        raise ControlInputError("нет файла фактов nii_books.json")
    for root in (nb.get("books", {}), nb):
        if isinstance(root, dict) and b in root:
            return float(c_fval({"x": root}, "x", f"{b}.rate_anchor"))
    raise ControlInputError(f"нет ставки якоря книги {b} (nii_books.json)")


def _c_nb_node(facts: dict, name: str) -> float:
    nb = facts["nii_books"]
    for root in (nb, nb.get("anchor", {}), nb.get("totals", {})):
        if isinstance(root, dict) and name in root:
            return float(c_fval({"x": root}, "x", name))
    raise ControlInputError(f"нет узла nii_books.{name}")


PNL_LINES = ("nii", "fees_net", "llp_debt_fa", "insurance_net", "noncore_net", "opex", "pbt",
             "tax", "ni", "ni_shareholders", "misc_net")


def c_anchor_state(book: dict, facts: dict) -> dict:
    """Стартовое состояние якоря (М§4.1, прил. B) в единицах модели, с источником — фактами."""
    notes: list[str] = []
    bal = "balance"

    def c_lg(k):
        return c_fnum(facts, bal, f"loans_ac_gross.{k}")

    books = c_bget(book, "nii.books")
    for role in (SECURITIES, LIQUIDITY, WHOLESALE, RETAIL_CURRENT, RETAIL_TERM):
        if role not in books:
            raise ControlInputError(f"в nii.books нет книги роли {role} (М§4.1)")
    direct = isinstance(facts.get(bal, {}).get("books"), dict)
    if direct:
        # остатки якоря — прямыми узлами balance.books.<b> при любом составе книг (М§4.1 п. 2)
        E0 = {b: c_fnum(facts, bal, f"books.{b}") for b in books}
        fv_loans = None
        if any("fv_share" in sp for sp in books.values()):
            raise ControlInputError("fv_share у книги с остатками прямыми узлами: формулы вывода нет (М§4.1 п. 6)")
    else:
        # таблица состава книг образца — ветвь для его фактов (М§17)
        fv_loans = c_fnum(facts, bal, "loans_fvtpl")
        E0 = {
            CORP_LOANS: c_lg("commercial") + c_lg("project") + fv_loans,
            "mortgage": c_lg("mortgage_market"),
            "mortgage_sub": c_lg("mortgage_subsidized"),
            "retail_loans": c_lg("consumer") + c_lg("cards") + c_lg("auto"),
            SECURITIES: _c_sum_nodes(facts, bal, "securities",
                                   ["fvoci_debt", "fvoci_repo", "ac", "ac_repo", "fvtpl_bonds"], notes),
            LIQUIDITY: _c_sum_nodes(facts, bal, "liquidity",
                                  ["cash", "cbr", "due_from_banks", "reverse_repo"], notes),
            RETAIL_CURRENT: c_fnum(facts, bal, "funds.retail_current"),
            RETAIL_TERM: c_fnum(facts, bal, "funds.retail_term"),
            CORP_FUNDS: c_fnum(facts, bal, "funds.corp_current") + c_fnum(facts, bal, "funds.corp_term"),
            WHOLESALE: _c_sum_nodes(facts, bal, "wholesale",
                                  ["banks", "issued_debt", "subordinated", "repo_cbr"], notes),
        }
        for b in books:
            if b not in E0:
                raise ControlInputError(f"книга {b}: нет узла balance.books.{b}, а таблица состава книг "
                                        f"образца её не знает (М§4.1 п. 2, прил. B)")
    A = {"E0": E0, "notes": notes, "fv_loans": fv_loans, "direct_books": direct}
    A["rate0"] = {b: _c_book_rate(facts, b) for b in books}
    A["AL"] = abs(c_fnum(facts, bal, "allowance_ac"))
    A["OA"] = c_fnum(facts, bal, "other_assets")
    A["OL"] = c_fnum(facts, bal, "other_liabilities")
    A["DP"] = c_fnum(facts, bal, "dividends_payable")
    A["DP_year"] = _c_nodeval(facts[bal].get("dividends_payable_year"))          # признак годового режима (М§5.4)
    A["DP_declared"] = [{"period": str(_c_nodeval(it["period"])), "amount": float(_c_nodeval(it["amount"]))}
                        for it in (facts[bal].get("dividends_payable_declared") or [])]
    oaf = facts[bal].get("other_assets_fixed")
    A["OA_fixed_fact"] = None if oaf is None else _c_nodeval(oaf)
    # неработающие деньги якоря (узел balance.nonworking_money.total): читает только ключ volumes.cash_assets (К8)
    nwm = facts[bal].get("nonworking_money")
    A["cash_fact"] = _c_nodeval(nwm.get("total")) if isinstance(nwm, dict) and nwm.get("total") is not None else None
    # ФОР якоря (узел balance.nonworking_money.mandatory_reserves): читает только доля денег книги (Р6-1, reserves: anchor)
    A["cash_reserves_fact"] = (_c_nodeval(nwm.get("mandatory_reserves"))
                               if isinstance(nwm, dict) and nwm.get("mandatory_reserves") is not None else None)
    A["history"] = {str(per): {k: _c_nodeval(v) for k, v in rec.items()}
                    for per, rec in (facts[bal].get("history") or {}).items() if isinstance(rec, dict)}
    # остатки книг на концах кварталов до якоря (узел balance.history.<период>.books.<b>): база драйвера расходов,
    # взвешенного по себестоимости книг (ключ opex.volume_weights); null — нет числа (отказ при чтении)
    A["history_books"] = {str(per): {str(b): _c_nodeval(v) for b, v in rec["books"].items()}
                          for per, rec in (facts[bal].get("history") or {}).items()
                          if isinstance(rec, dict) and isinstance(rec.get("books"), dict)}
    # резерв по кредитным книгам на дату якоря (узел balance.allowance_books.<b>): читает только ключ
    # credit.allowance_by_book (К7); нет узла — None
    alb = facts[bal].get("allowance_books")
    A["allowance_books"] = None if not isinstance(alb, dict) else {str(b): _c_nodeval(v) for b, v in alb.items()}
    A["BV"] = c_fnum(facts, bal, "equity.bv_common")
    A["AT1"] = c_fnum(facts, bal, "equity.at1")
    A["NCI"] = c_fnum(facts, bal, "equity.nci")
    A["prev_corp"] = c_fnum(facts, bal, "prev_year_end.loans_corporate")
    A["prev_retail"] = c_fnum(facts, bal, "prev_year_end.loans_retail")
    A["fvoci_debt"] = (c_fnum(facts, bal, "securities.fvoci_debt")
                       + (c_fval(facts, bal, "securities.fvoci_repo", null_ok=True) or 0.0))
    A["fvtpl_bonds"] = c_fval(facts, bal, "securities.fvtpl_bonds", null_ok=True)
    # доля текущих счетов якоря: узел факта, а при null — из остатков книг средств физлиц (прил. B)
    share0 = _c_nb_opt(facts, "current_share_anchor")
    A["current_share"] = (float(share0) if share0 is not None
                          else E0[RETAIL_CURRENT] / (E0[RETAIL_CURRENT] + E0[RETAIL_TERM]))
    A["key_ref"] = _c_nb_node(facts, "key_avg_anchor_q")
    cap = "capital"
    A["cpn_annual"] = c_fnum(facts, cap, "at1.coupon_annual")
    A["cpn_quarter"] = int(c_fnum(facts, cap, "at1.coupon_quarter"))
    A["R0"] = c_fnum(facts, cap, "fvoci_reserve")
    # номиналы гарантий (узел capital.guarantees.<вид>): читает только ключ capital.rwa.guarantees (К5)
    gu = facts[cap].get("guarantees")
    A["guarantees"] = None if not isinstance(gu, dict) else {str(k): _c_nodeval(v) for k, v in gu.items()}
    A["curve0"] = {str(k): c_fnum(facts, cap, f"ofz_curve_anchor.{k}")
                   for k in _c_dig(facts[cap], "ofz_curve_anchor") if str(k)[:1].isdigit()}
    A["n20_fact"] = c_fnum(facts, cap, "n20_0.value")
    A["n11_fact"] = c_fnum(facts, cap, "n1_1_bank.value")
    A["rwa_basel"] = c_fnum(facts, cap, "basel.rwa")
    A["group_cet1"] = _c_nodeval(facts[cap].get("basel", {}).get("cet1"))
    A["base_capital"] = _c_nodeval(facts[cap].get("bank_base_capital"))
    sh = "shares"
    A["N_iss"] = c_fnum(facts, sh, "issued_total")
    A["N_out"] = c_fnum(facts, sh, "outstanding_total")
    A["N_div"] = c_divisor(book, facts, A["N_iss"], A["N_out"])
    A["bridge"] = {x: (str(c_fval(facts, "bridge_mgmt_ifrs", f"{x}.method")),
                       float(c_fval(facts, "bridge_mgmt_ifrs", f"{x}.value"))) for x in ("cor", "nim")}
    if isinstance(facts.get("bridge_mgmt_ifrs", {}).get("cir"), dict):
        # мост C/I нужен только уровням после фазы роста (ключи checks.window_backtest и checks.cir_lt)
        A["bridge"]["cir"] = (str(c_fval(facts, "bridge_mgmt_ifrs", "cir.method")),
                              float(c_fval(facts, "bridge_mgmt_ifrs", "cir.value")))
    rows = _c_quarter_rows(facts["pnl_quarterly"])
    A["pnl"] = {per: {line: _c_nodeval(rec[line]) for line in PNL_LINES if line in rec}
                for per, rec in rows.items()}
    dv = facts.get("dividends", {})
    A["div_history"] = dv.get("history", [])
    A["register"] = dv.get("register_seed", [])
    A["div_years"] = dv.get("years") or {}
    A["facts_date"] = _c_as_date(c_bget(book, "meta.facts_date"))
    A["anchor"] = c_per_parse(c_bget(book, "meta.anchor_period"))
    return A


def c_divisor(book: dict, facts: dict, n_iss: float, n_out: float) -> float:
    """Делитель «на акцию» N_div (М§8.4): база — акции в обращении (без ключа) или размещённые за вычетом
    экономически собственных; множитель (1 + share_count_adj) — только при ключе."""
    basis = c_bopt(book, "valuation.shares_basis")
    n_div = n_out
    if basis == BASIS_ISSUED:
        if len(c_bget(book, "meta.company.tickers")) != 1:
            raise ControlInputError("valuation.shares_basis: issued при двух и более тикерах (М§8.4)")
        node = facts.get("shares", {}).get("economic_treasury")
        n_div = n_iss - float(_c_nodeval(node) or 0.0)
    elif basis not in (None, "outstanding"):
        raise ControlInputError(f"valuation.shares_basis: {basis!r}")
    adj = c_bopt(book, "valuation.share_count_adj")
    if adj is not None:
        if not -0.5 < float(adj) < 0.5:
            raise ControlInputError("valuation.share_count_adj вне (−0,5; 0,5) (М§8.4)")
        n_div = n_div * (1.0 + float(adj))
    if n_div <= 0.0:
        raise ControlInputError("делитель N_div не положителен (М§8.4)")
    return n_div


def _c_nb_opt(facts: dict, name: str):
    """Узел nii_books.<name>, допускающий null (None — «считается из книг», прил. B)."""
    nb = facts.get("nii_books") or {}
    for root in (nb, nb.get("anchor", {}), nb.get("totals", {})):
        if isinstance(root, dict) and name in root:
            return _c_nodeval(root[name])
    return None


def c_fv_books(books: dict) -> list[str]:
    """Кредитные книги с долей кредитов по справедливой стоимости (ключ fv_share, М§4.6)."""
    return [b for b, sp in books.items() if sp.get("sector") and "fv_share" in sp]


def c_book_cor_mult(B: dict, A: dict, fv: dict) -> dict | None:
    """Множители CoR кредитных книг (ключ credit.book_relative, М§4.6): r̂_b = r_b / Σ_b' w_b',0 r_b', где w_b,0 —
    доля книги в кредитах по амортизированной стоимости якоря (остаток якоря за вычетом доли fv_share). На составе
    якоря общая CoR равна CoR клетки (путь + κ-добавка + отклонение A-P2u). Нормировка — по сырым значениям той книги,
    которую считает прогон (подмена множителя её повторяет). Нет ключа или enabled: false — None: прежняя ветвь
    (сегменты или общая CoR)."""
    node = c_bopt(B, "credit.book_relative")
    if node is None:
        return None
    if not isinstance(node, dict) or not isinstance(node.get("enabled"), bool):
        raise ControlInputError("credit.book_relative: нужен выключатель enabled (М§4.6)")
    if not node["enabled"]:
        return None
    if c_bopt(B, "credit.segment_relative.enabled"):
        raise ControlInputError("credit.book_relative и credit.segment_relative включены вместе: одно суждение — "
                                "одно место (М§4.6)")
    books = c_bget(B, "nii.books")
    loans = [b for b, sp in books.items() if sp.get("sector")]
    raw = node.get("by_book")
    if not isinstance(raw, dict) or sorted(str(b) for b in raw) != sorted(loans):
        raise ControlInputError("credit.book_relative.by_book: книги — не ровно кредитные книги nii.books (М§4.6)")
    vals = {}
    for b in loans:
        v = raw[b]
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) <= 0.0:
            raise ControlInputError(f"credit.book_relative.by_book.{b}: множитель — не число больше нуля (М§4.6)")
        vals[b] = float(v)
    ac0 = {b: A["E0"][b] * ((1.0 - fv[b]) if b in fv else 1.0) for b in loans}
    total = sum(ac0.values())
    mix = sum(ac0[b] / total * vals[b] for b in loans)
    return {b: vals[b] / mix for b in loans}


def c_opex_weights(B: dict, link_opex: float) -> dict | None:
    """Веса себестоимости книг драйвера расходов (ключ opex.volume_weights, М§4.7): книга nii.books (любой стороны) →
    вес ≥ 0, хотя бы один больше нуля. Читается только при связи расходов с объёмом больше нуля (как база связи);
    нет ключа или связи — None: база расходов — volumes.link_base, прежняя строка."""
    if not link_opex:
        return None
    raw = c_bopt(B, "opex.volume_weights")
    if raw is None:
        if "volume_weights" in (c_bopt(B, "opex") or {}):
            raise ControlInputError("opex.volume_weights: null (М§0.1: null ≠ 0)")
        return None
    books = c_bget(B, "nii.books")
    if not isinstance(raw, dict) or not raw:
        raise ControlInputError("opex.volume_weights: нужен словарь «книга → вес» (М§4.7)")
    out = {}
    for b, v in raw.items():
        if str(b) not in books:
            raise ControlInputError(f"opex.volume_weights: {b!r} — не книга nii.books (М§4.7)")
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) < 0.0:
            raise ControlInputError(f"opex.volume_weights.{b}: вес — не число ≥ 0 (М§4.7)")
        out[str(b)] = float(v)
    if not any(out.values()):
        raise ControlInputError("opex.volume_weights: все веса нулевые (М§4.7)")
    return out


def c_is_number(v) -> bool:
    """Число книги: int или float, не логическое и не null (М§0.1: null ≠ 0)."""
    return v is not None and not isinstance(v, bool) and isinstance(v, (int, float))


def c_wholesale_shares(B: dict) -> tuple[float, float]:
    """Доля опта к средствам клиентов: (база опта s, доля якоря s_A) (М§4.3, §4.10). Ключ
    volumes.wholesale_structural_to_funds (К3, решения № 3, Р4) — структурная часть опта (облигации,
    субординированный долг): опт квартала E_wh = s × средства + max(0, la_min − la⁰ − s × средства), то есть сверх
    структурной части опт и добирается при нехватке ликвидности, и гасится при её избытке. Это та же формула, что
    прежняя с базой s вместо доли якоря, — поэтому база опта модели просто s; доля якоря остаётся печати. Нет ключа —
    база = доля якоря (прежняя строка). Ключ не число или вне [0; s_A] — отказ: структурная часть больше
    фактического опта якоря дала бы скачок ликвидности в первом квартале."""
    anchor = c_bnum(B, "volumes.wholesale_to_funds")
    node = c_bopt(B, "volumes") or {}
    if "wholesale_structural_to_funds" not in node:
        return anchor, anchor
    s = node["wholesale_structural_to_funds"]
    if not c_is_number(s):
        raise ControlInputError("volumes.wholesale_structural_to_funds: не число (М§4.3)")
    if not 0.0 <= float(s) <= anchor:
        raise ControlInputError(f"volumes.wholesale_structural_to_funds = {s} вне [0; доля опта якоря {anchor}] (М§4.3)")
    return float(s), anchor


BASE_NOMINAL, BASE_WEIGHTS = "nominal", "weights"          # база строки К2: «номинал» и веса книг
BASE_KINDS = LINK_BASES + (BASE_NOMINAL,)
LINE_BASE_KEYS = {"fees": "fees.volume_base", "ins": "other.insurance_volume_base"}     # К2: база связи по строке


def c_base_spec(B: dict, raw, what: str, E0: dict | None = None) -> dict:
    """База связи строки с объёмом (К2, М§4.7): loans | funds | iea | nominal или веса {книга nii.books → ω ≥ 0} с
    хотя бы одним весом больше нуля; К2б — смесь баз {mix: {имя: {share, base}}}, компилируется по остаткам якоря E0 в
    веса книг (c_base_mix). Возвращает {"kind": …} (у весов — ещё "w")."""
    if isinstance(raw, dict) and MIX_FIELD in raw:
        return c_base_mix(B, raw, what, E0)
    if isinstance(raw, str):
        if raw not in BASE_KINDS:
            raise ControlInputError(f"{what}: {raw!r} — не {', '.join(BASE_KINDS)} и не веса книг (М§4.7)")
        return {"kind": raw}
    if not isinstance(raw, dict) or not raw:
        raise ControlInputError(f"{what}: база — имя или непустой словарь «книга → вес» (М§4.7)")
    books = c_bget(B, "nii.books")
    w = {}
    for b, v in raw.items():
        if str(b) not in books:
            raise ControlInputError(f"{what}: {b!r} — не книга nii.books (М§4.7)")
        if not c_is_number(v) or float(v) < 0.0:
            raise ControlInputError(f"{what}.{b}: вес — не число ≥ 0 (М§4.7)")
        w[str(b)] = float(v)
    if not any(w.values()):
        raise ControlInputError(f"{what}: все веса нулевые (М§4.7)")
    return {"kind": BASE_WEIGHTS, "w": w}


def c_base_mix(B: dict, raw: dict, what: str, E0: dict | None) -> dict:
    """Смесь баз строки (К2б, решения № 4, Р4-1, Р4-2): доля s_k строки якоря идёт за базой k — loans (кредитные книги),
    funds (средства клиентов: пара средств физлиц и средства бизнеса, с ведомыми книгами К6), iea (процентные активы)
    или веса книг. Компиляция по ОСТАТКАМ якоря E0: ω_b = Σ_k s_k ω^k_b / D^k_0, D^k_0 = Σ_b ω^k_b E_b,0 — тогда на концах
    кварталов D_q / D_0 = Σ_k s_k D^k_q / D^k_0 точно; дальше смесь — обычные веса книг (рост, К5, К6, история — по ним).
    Отказы: сумма долей не 1 (1e-9), доля вне [0; 1], компонента nominal (смесь с индексом нелинейна: «часть строки за
    зарплатами» — связь строки меньше 1), смесь в смеси, неизвестная база или книга, все веса 0, D^k_0 ≤ 0, пустая смесь."""
    if set(raw) != {MIX_FIELD} or not isinstance(raw[MIX_FIELD], dict) or not raw[MIX_FIELD]:
        raise ControlInputError(f"{what}: смесь баз — {{{MIX_FIELD}: {{имя: {{share, base}}}}}}, непустая (М§4.7)")
    if E0 is None:
        raise ControlInputError(f"{what}: смесь баз компилируется по остаткам якоря — их нет (М§4.7)")
    books = c_bget(B, "nii.books")
    words = {LINK_BASES[0]: [b for b, sp in books.items() if sp.get("sector")],
             LINK_BASES[1]: c_fund_word_books(B, books),          # Р11-2: при funds_scope: clients — без книг К6
             LINK_BASES[2]: [b for b, sp in books.items() if sp["side"] == LOANS_SIDE]}
    out, shares, total = {}, {}, 0.0
    for name, comp in raw[MIX_FIELD].items():
        label = f"{what}.{MIX_FIELD}.{name}"
        if not isinstance(comp, dict) or set(comp) != {"share", "base"}:
            raise ControlInputError(f"{label}: компонента — {{share, base}} (М§4.7)")
        share, base = comp["share"], comp["base"]
        if not c_is_number(share) or not 0.0 <= float(share) <= 1.0:
            raise ControlInputError(f"{label}.share: доля — число в [0; 1] (М§4.7)")
        if base == BASE_NOMINAL:
            raise ControlInputError(f"{label}.base: nominal в смеси — смесь с индексом зарплат нелинейна; часть строки за "
                                    f"зарплатами — связью строки с объёмом меньше 1 (М§4.7)")
        if isinstance(base, str):
            if base not in LINK_BASES:
                raise ControlInputError(f"{label}.base: {base!r} — не {', '.join(LINK_BASES)} и не веса книг (М§4.7)")
            w = {b: 1.0 for b in words[base]}
        elif isinstance(base, dict) and MIX_FIELD not in base:
            w = c_base_spec(B, base, f"{label}.base")["w"]
        else:
            raise ControlInputError(f"{label}.base: база компоненты — слово или веса книг (смесь в смеси нельзя, М§4.7)")
        d0 = sum(wb * E0[b] for b, wb in w.items() if wb)
        if not d0 > 0.0:
            raise ControlInputError(f"{label}: уровень базы компоненты на якоре D_0 = {d0} не больше нуля (М§4.7)")
        for b, wb in w.items():
            if wb:
                out[b] = out.get(b, 0.0) + float(share) * wb / d0
        shares[str(name)] = float(share)
        total += float(share)
    if abs(total - 1.0) > 1e-9:
        raise ControlInputError(f"{what}: сумма долей смеси {total} ≠ 1 (М§4.7)")
    return {"kind": BASE_WEIGHTS, "w": out, "mix": shares}


def c_line_base(B: dict, line: str, link_base: str, E0: dict | None = None) -> dict:
    """База строки ℓ (комиссии fees или страхование ins): свой ключ К2, без него — volumes.link_base (прежний ряд).
    Читается только там, где строке или ключам К5/К6 нужна база; null у ключа — отказ (М§0.1). Одна функция разрешения
    базы для строки, RWA гарантий (К5) и ведомой книги (К6); смесь К2б компилируется по остаткам якоря E0."""
    dotted = LINE_BASE_KEYS[line]
    head, key = dotted.rsplit(".", 1)
    node = c_bopt(B, head) or {}
    if key in node:
        if node[key] is None:
            raise ControlInputError(f"{dotted}: null (М§0.1: null ≠ значение по умолчанию)")
        return c_base_spec(B, node[key], dotted, E0)
    if link_base not in LINK_BASES:
        raise ControlInputError(f"volumes.link_base: {link_base!r} (М§4.7)")
    return {"kind": link_base}


def c_base_level(spec: dict, E: dict, *, loans, biz, assets, nominal: float) -> float:
    """Уровень базы строки на конце квартала D^ℓ (К2; читают К5 и К6): кредиты, средства клиентов (физлиц и бизнеса),
    процентные активы, Σ ω_b E_b по остаткам E или индекс «номинала» D^N (растёт с зарплатами мира, на якоре 1)."""
    kind = spec["kind"]
    if kind == LINK_BASES[0]:
        return sum(E[b] for b in loans)
    if kind == LINK_BASES[1]:
        return E[RETAIL_CURRENT] + E[RETAIL_TERM] + sum(E[b] for b in biz)
    if kind == LINK_BASES[2]:
        return sum(E[b] for b in assets)
    if kind == BASE_NOMINAL:
        return nominal
    return sum(w * E[b] for b, w in spec["w"].items() if w)


GUAR_KINDS = ("nonfinancial", "financial")
# драйвер суммы гарантий: база комиссий (К2), строка комиссий за год или одна компонента смеси базы комиссий (Р5-5)
GUAR_DRIVERS = ("fees_base", "fees_line", "fees_component")
GUAR_BASE_DRIVERS = (GUAR_DRIVERS[0], GUAR_DRIVERS[2])      # драйверы-уровни базы на конце квартала (не строка)


def c_guarantee_component(B: dict, node: dict, E0: dict) -> dict:
    """База драйвера гарантий fees_component (решения № 5, Р5-5): компонента c смеси fees.volume_base (К2б) — её база, как
    записана (слово loans | funds | iea или веса книг), без доли s_c и без прочих компонент: D^G_q = Σ_b ω^c_b E_b,q. Своя
    компиляция одной компоненты — смесь из неё одной с долей 1 (c_base_mix: веса ω^c_b / D^c_0; масштаб отношения
    D^G_q / D^G_0 не меняет). Вся смесь проверяется прежними правилами К2б. Отказы: нет поля component (или не строка),
    fees.volume_base не смесь (слово, веса книг, нет ключа), имени нет в смеси."""
    name = node.get("component")
    if not isinstance(name, str) or not name:
        raise ControlInputError("capital.rwa.guarantees.component: нужно имя компоненты смеси fees.volume_base при "
                                f"driver: {GUAR_DRIVERS[2]} (М§4.11)")
    head, key = LINE_BASE_KEYS["fees"].rsplit(".", 1)
    raw = (c_bopt(B, head) or {}).get(key)
    if not isinstance(raw, dict) or MIX_FIELD not in raw:
        raise ControlInputError(f"capital.rwa.guarantees.driver: {GUAR_DRIVERS[2]} читает компоненту смеси "
                                f"{LINE_BASE_KEYS['fees']}, а база комиссий книги — не смесь (М§4.11)")
    c_base_mix(B, raw, LINE_BASE_KEYS["fees"], E0)                  # смесь целиком — прежние правила К2б
    comps = raw[MIX_FIELD]
    if name not in comps:
        raise ControlInputError(f"capital.rwa.guarantees.component: {name!r} — не компонента смеси "
                                f"{LINE_BASE_KEYS['fees']} ({', '.join(map(str, comps))}) (М§4.11)")
    one = {MIX_FIELD: {name: {"share": 1, "base": comps[name]["base"]}}}
    return c_base_mix(B, one, f"capital.rwa.guarantees.component.{name}", E0)


def c_guarantee_rule(B: dict, A: dict, books: dict, dens: dict, link_base: str) -> dict | None:
    """Составляющая RWA гарантий (ключ capital.rwa.guarantees, К5, решения № 3, Р7): G_0 = (N_нф × CCF_нф + N_ф × CCF_ф)
    × вес — отдельная сумма RWA, вырезанная из плотности книги carve_from: ω′ = ω − G_0 / E_0 (RWA якоря не
    меняется). G_q = G_0 × D^G_q / D^G_0: D^G — уровень базы комиссий на конце квартала (fees_base; база — ключ К2
    fees.volume_base, без него volumes.link_base), строка комиссий за четыре квартала (fees_line) или уровень базы одной
    компоненты смеси базы комиссий (fees_component, поле component — имя компоненты; решения № 5, Р5-5). Поле component
    читается только при fees_component: у прочих драйверов это ключ неактивного режима. Номинал anchor — узел фактов
    capital.guarantees.<вид>. Нет ключа или enabled: false — None (прежние RWA)."""
    node = c_bopt(B, "capital.rwa.guarantees")
    if node is None:
        return None
    if not isinstance(node, dict) or not isinstance(node.get("enabled"), bool):
        raise ControlInputError("capital.rwa.guarantees: нужен выключатель enabled (М§0.1)")
    if not node["enabled"]:
        return None
    for key in ("notional", "ccf", "weight", "carve_from", "driver"):
        if node.get(key) is None:
            raise ControlInputError(f"capital.rwa.guarantees.{key}: нет поля при enabled: true (М§4.11)")
    g_sum = 0.0
    for kind in GUAR_KINDS:
        n = (node["notional"] or {}).get(kind) if isinstance(node["notional"], dict) else None
        if n == "anchor":
            n = (A.get("guarantees") or {}).get(kind)
            if not c_is_number(n):
                raise ControlInputError(f"capital.rwa.guarantees.notional.{kind}: anchor без узла фактов "
                                        f"capital.guarantees.{kind} (прил. B)")
        if not c_is_number(n) or float(n) < 0.0:
            raise ControlInputError(f"capital.rwa.guarantees.notional.{kind}: номинал — не число ≥ 0 (М§4.11)")
        ccf = node["ccf"].get(kind) if isinstance(node["ccf"], dict) else None
        if not c_is_number(ccf) or not 0.0 <= float(ccf) <= 1.0:
            raise ControlInputError(f"capital.rwa.guarantees.ccf.{kind}: CCF — число в [0; 1] (М§4.11)")
        g_sum += float(n) * float(ccf)
    weight = node["weight"]
    if not c_is_number(weight) or float(weight) <= 0.0:
        raise ControlInputError("capital.rwa.guarantees.weight: вес — число больше нуля (М§4.11)")
    carve = node["carve_from"]
    if carve not in books or not books[carve].get("sector"):
        raise ControlInputError(f"capital.rwa.guarantees.carve_from: {carve!r} — не кредитная книга (М§4.11)")
    driver = node["driver"]
    if driver not in GUAR_DRIVERS:
        raise ControlInputError(f"capital.rwa.guarantees.driver: {driver!r} — не {', '.join(GUAR_DRIVERS)} (М§4.11)")
    g0 = g_sum * float(weight)
    w_carved = float(dens[carve]) - g0 / A["E0"][carve]
    if w_carved < 0.0:
        raise ControlInputError(f"гарантий больше, чем RWA книги {carve}: плотность после выреза {w_carved} < 0 (М§4.11)")
    out = {"g0": g0, "carve": carve, "w_carved": w_carved, "driver": driver, "spec": None}
    if driver in GUAR_BASE_DRIVERS:
        out["spec"] = (c_line_base(B, "fees", link_base, A["E0"]) if driver == GUAR_DRIVERS[0]
                       else c_guarantee_component(B, node, A["E0"]))
        assets = [b for b, sp in books.items() if sp["side"] == LOANS_SIDE]
        out["d0"] = c_base_level(out["spec"], A["E0"], loans=[b for b, sp in books.items() if sp.get("sector")],
                                 biz=c_fund_biz(B, books), assets=assets, nominal=1.0)    # Р11-2: слово funds
    else:
        y0, qa = A["anchor"]
        out["d0"] = sum(_c_fact_line(A, "fees_net", *c_qback((y0, qa), j)) for j in range(QY))
    if not out["d0"] > 0.0:
        raise ControlInputError(f"драйвер гарантий на якоре D^G_0 = {out['d0']} не больше нуля (М§4.11)")
    return out


LINE_SHARE_KEYS = {"fees": "fees", "insurance": "ins"}       # opex.line_shares: строка книги → строка модели


def c_line_rules(B: dict, links: tuple, link_base: str, E0: dict | None = None) -> tuple[dict, dict | None]:
    """Базы связи строк с объёмом по ключам К2 (решения № 3, Р2) и доли расходов на драйверах строк opex.line_shares
    (франшиза; читаются при связи расходов больше нуля; доли в [0; 1), сумма < 1). Своя база строки читается при связи
    строки больше нуля И при доле франшизы строки больше нуля — при любой связи, и при связи 0 тоже (флаг 6 круга 7,
    решения № 8, Р8-6: франшиза в смеси расходов идёт за базой строки и тогда, когда сама строка с базой не связана;
    счёт непрерывен по связи у нуля). Доли разбираются раньше баз. Возвращает ({строка: своя база или None}, доли или
    None)."""
    shares = None
    node = c_bopt(B, "opex") or {}
    if links[2] and "line_shares" in node:
        raw = node["line_shares"]
        if not isinstance(raw, dict) or any(k not in LINE_SHARE_KEYS for k in raw):
            raise ControlInputError("opex.line_shares: словарь долей строк fees и insurance (М§4.7)")
        shares = {}
        for k, line in LINE_SHARE_KEYS.items():
            v = raw.get(k, 0.0)
            if not c_is_number(v) or not 0.0 <= float(v) < 1.0:
                raise ControlInputError(f"opex.line_shares.{k}: доля — число в [0; 1) (М§4.7)")
            shares[line] = float(v)
        if sum(shares.values()) >= 1.0:
            raise ControlInputError("opex.line_shares: сумма долей ≥ 1 (М§4.7)")
    own = {}
    for line, link in (("fees", links[0]), ("ins", links[1])):
        dotted = LINE_BASE_KEYS[line]
        head, key = dotted.rsplit(".", 1)
        wanted = bool(link) or (shares is not None and shares[line] > 0.0)
        own[line] = c_line_base(B, line, link_base, E0) if (wanted and key in (c_bopt(B, head) or {})) else None
    return own, shares


SHARE_ROOT_LINES = {"fees": ("fees", 0), "insurance": ("ins", 1)}   # opex.line_share_roots: строка → (строка модели, связь)


def c_traj_form(traj, what: str) -> None:
    """Форма траектории книги (М§0.4) без чтения значений: число (не логическое) или словарь с ключами времени и/или LT
    (LT_from — год); значения — числа. Траектория без значений, неразборный ключ, null — отказ."""
    if c_is_number(traj):
        return
    if not isinstance(traj, dict):
        raise ControlInputError(f"{what}: не траектория — {traj!r} (М§0.4)")
    t = {str(k): v for k, v in traj.items()}
    try:
        keys = _c_time_keys(t)
    except (ValueError, TypeError) as exc:
        raise ControlInputError(f"{what}: ключ времени траектории не разбирается ({exc}; М§0.4)") from None
    if any(not 1 <= q1 <= q2 <= QY for _, q1, q2 in keys.values()):
        raise ControlInputError(f"{what}: квартал или полугодие вне года в ключе траектории (М§0.4)")
    if not keys and "LT" not in t:
        raise ControlInputError(f"{what}: траектория без значений (нет ключей времени и LT, М§0.4)")
    for k, v in t.items():
        if k == "LT_from":
            if not c_is_number(v) or float(v) != int(v):
                raise ControlInputError(f"{what}.LT_from: не год — {v!r} (М§0.4)")
        elif not c_is_number(v):
            raise ControlInputError(f"{what}.{k}: значение траектории — не число: {v!r} (М§0.4)")


def c_share_nominal(B: dict, links: tuple, shares: dict | None) -> dict | None:
    """Франшиза строки за связью строки (ключ opex.line_share_roots {fees, insurance → траектория κ}, решения № 8,
    Р8-6). Доля s_ℓ базы расходов якоря на драйвере строки ℓ идёт так же, как сама строка: долей связи строки λ_ℓ — за
    базой строки, остальное — номиналом мира с корнем κ: Φ_q = λ A_q / A_0 + (1 − λ) H_q, H_q = H_(q−4) (1 + рост
    зарплат мира) (1 + κ_q), H_x = A_x / A_0 до якоря. λ_ℓ — связь самой строки (fees.volume_link,
    other.insurance_volume_link), не новый ключ. Форма ключа проверяется всегда (null, не словарь, строка не fees /
    insurance, траектория без значений — отказ); читается строка ключа, только когда читаются доли (связь расходов > 0)
    и её доля больше нуля — иначе ключ неактивного режима (варианты снимают долю франшизы). Пустой словарь — ключа нет.
    Возвращает {строка модели: (λ, траектория κ)} или None (прежняя смесь)."""
    node = c_bopt(B, "opex") or {}
    if "line_share_roots" not in node:
        return None
    raw = node["line_share_roots"]
    if raw is None:
        raise ControlInputError("opex.line_share_roots: null (М§0.1: null ≠ пустой словарь)")
    if not isinstance(raw, dict):
        raise ControlInputError("opex.line_share_roots: словарь «строка fees | insurance → траектория κ» (М§4.7)")
    for k, traj in raw.items():
        if k not in SHARE_ROOT_LINES:
            raise ControlInputError(f"opex.line_share_roots: {k!r} — не строка fees или insurance (М§4.7)")
        c_traj_form(traj, f"opex.line_share_roots.{k}")
    if shares is None:
        return None
    out = {}
    for k, traj in raw.items():
        line, idx = SHARE_ROOT_LINES[k]
        if shares[line] > 0.0:
            out[line] = (float(links[idx]), traj)
    return out or None


def c_franchise_h(back: float, wage: float, root: float) -> float:
    """Номинальная часть франшизы строки квартала (Р8-6): H_q = H_(q−4) × (1 + рост зарплат мира г/г) × (1 + κ_q)."""
    return back * (1.0 + wage) * (1.0 + root)


LINE_FORMS = ("mixed", "line")       # volumes.line_link_form: форма суждения «связь строки λ» у франшизы и К6 (Р10-5)


def c_line_link_form(B: dict) -> bool:
    """Одна форма связи строки λ (ключ volumes.line_link_form, решения № 10, Р10-5): line — франшиза строки в смеси базы
    расходов и книга К6 растут формой самой строки (смесь темпов г/г с корнем, c_link_growth); mixed и нет ключа —
    прежние формы (франшиза — смесь уровней Р8-6, К6 — цепь на концах Р9-1). Форма проверяется всегда: null и значение
    не из перечня — отказ (М§0.1). Читают ключ франшиза (там же, где Р8-6) и К6 (при активном К6); иначе — ключ
    неактивного режима, не отказ."""
    node = c_bopt(B, "volumes") or {}
    if "line_link_form" not in node:
        return False
    form = node["line_link_form"]
    if not isinstance(form, str) or form not in LINE_FORMS:
        raise ControlInputError(f"volumes.line_link_form: {form!r} — не {', '.join(LINE_FORMS)} (М§0.1, §4.7)")
    return form == LINE_FORMS[1]


FUNDS_SCOPES = ("modal_cell", "world_expectation")   # checks.funds_cost_to_key.scope: число гейта мира (Р10-6)
CLIENT_FUNDS_KINDS = ("all", "clients")               # checks.client_funds: «средства клиентов» гейтов (Р10-1, ключ (3))


def c_funds_keys(B: dict) -> dict:
    """Ключи прохода 8 в числах гейтов средств (решения № 10). checks.funds_cost_to_key.scope (Р10-6): число гейта мира —
    клетка «мир × модальный режим × модальный сценарий» (modal_cell, без ключа) или ожидание мира (world_expectation):
    отношение ожиданий процентов и остатков по клеткам мира с весами P(r) P(s | r). checks.client_funds (Р10-1): книги
    «средств клиентов» в числах гейтов funds_cost_to_key и wholesale_share и в пути фондирования — all (без ключа) — все
    книги средств, clients — без книг К6 (volumes.liability_drivers), когда К6 активен. Форма — всегда: null и значение не
    из перечня — отказ (М§0.1). → {scope, clients, keyed}: keyed — книга несёт хотя бы один из двух ключей (только тогда
    клетки пишут числа гейта стоимости средств; без ключей сводка прежняя)."""
    node = c_bopt(B, "checks") or {}
    fc = node.get("funds_cost_to_key")
    out = {"scope": FUNDS_SCOPES[0], "clients": False, "keyed": False}
    if isinstance(fc, dict) and "scope" in fc:
        if not isinstance(fc["scope"], str) or fc["scope"] not in FUNDS_SCOPES:
            raise ControlInputError(f"checks.funds_cost_to_key.scope: {fc['scope']!r} — не {', '.join(FUNDS_SCOPES)} "
                                    f"(М§0.1, §14.2)")
        out.update(scope=fc["scope"], keyed=True)
    if "client_funds" in node:
        kind = node["client_funds"]
        if not isinstance(kind, str) or kind not in CLIENT_FUNDS_KINDS:
            raise ControlInputError(f"checks.client_funds: {kind!r} — не {', '.join(CLIENT_FUNDS_KINDS)} (М§0.1, §14.2)")
        out.update(clients=kind == CLIENT_FUNDS_KINDS[1], keyed=True)
    return out


def c_link_growth(x: float, w: float, lam: float, r: float, mult: bool) -> float:
    """Рост «к тому же кварталу прошлого года» формой строки (Р10-5): x — база к тому же кварталу прошлого года, w —
    рост зарплат мира за год, λ — связь строки, r — корень. Множитель роста базы — та же функция, что у строки
    (c_base_factor: 1 + w + λ (x − 1 − w)); корень при volumes.line_root_form: multiplicative — множителем на всю смесь
    (1 + r), иначе — слагаемым (+ r). Одна функция у франшизы и книги К6."""
    f = c_base_factor(w, lam, x - 1.0)
    return f * (1.0 + r) if mult else f + r


def c_base_hist_end(ctx: dict, spec: dict, y: int, q: int) -> float:
    """Уровень базы строки на конце квартала (y, q) не позже якоря (К2): конец якоря — остатки якоря, раньше — факты
    balance.history (loans, funds, iea) или остатки книг balance.history.<период>.books (веса); «номинал» — 1. Нет
    числа — отказ."""
    A, kind = ctx["A"], spec["kind"]
    if kind == BASE_NOMINAL:
        return 1.0
    if (y, q) == ctx["anchor"]:
        # конец якоря базы funds — слово «средства клиентов» (Р11-2: при clients — без книг К6, как история фактов)
        return c_base_level(spec, A["E0"], loans=ctx["loans"], biz=ctx["fund_biz"],
                            assets=[b for b, sp in ctx["books"].items() if sp["side"] == LOANS_SIDE], nominal=1.0)
    if kind in LINK_BASES:
        val = A["history"].get(f"{y}Q{q}", {}).get(kind)
        if val is None:
            raise ControlInputError(f"нет конца квартала balance.history.{y}Q{q}.{kind} для базы строки (М§4.7)")
        return float(val)
    rec = A["history_books"].get(f"{y}Q{q}", {})
    total = 0.0
    for b, wb in spec["w"].items():
        if not wb:
            continue
        if rec.get(b) is None:
            raise ControlInputError(f"нет конца квартала balance.history.{y}Q{q}.books.{b} для базы строки (М§4.7)")
        total += wb * float(rec[b])
    return total


def c_base_hist_avg(ctx: dict, spec: dict, y: int, q: int) -> float:
    """Средняя базы строки за квартал (y, q) не позже якоря: полусумма концов (у «номинала» — 1)."""
    py, pq = (y - 1, QY) if q == 1 else (y, q - 1)
    return (c_base_hist_end(ctx, spec, py, pq) + c_base_hist_end(ctx, spec, y, q)) / 2.0


DRIVER_LINES = {"insurance": ("ins", 1), "fees": ("fees", 0)}     # строка-драйвер → (строка модели, номер связи)
DRIVER_ROOTS = "liability_driver_roots"       # volumes.liability_driver_roots: строка-драйвер → траектория ρ (Р9-1)


def c_driver_roots(B: dict) -> dict | None:
    """Корень номинальной части книг К6 по строке-драйверу (ключ volumes.liability_driver_roots {fees, insurance →
    траектория ρ}, решения № 9, Р9-1): форма ключа проверяется всегда — null (М§0.1: null ≠ пустой словарь), не словарь,
    строка не fees / insurance, траектория без значений или не траектория (М§0.4) — отказ. Нет ключа и пустой словарь —
    None (ключа нет); иначе — словарь ключа как есть (читает его c_driven_rule для ведомых книг своей строки)."""
    node = c_bopt(B, "volumes") or {}
    if DRIVER_ROOTS not in node:
        return None
    raw = node[DRIVER_ROOTS]
    if raw is None:
        raise ControlInputError(f"volumes.{DRIVER_ROOTS}: null (М§0.1: null ≠ пустой словарь)")
    if not isinstance(raw, dict):
        raise ControlInputError(f"volumes.{DRIVER_ROOTS}: словарь «строка fees | insurance → траектория ρ» (М§4.3)")
    for k, traj in raw.items():
        if k not in DRIVER_LINES:
            raise ControlInputError(f"volumes.{DRIVER_ROOTS}: {k!r} — не строка {' или '.join(DRIVER_LINES)} (М§4.3)")
        c_traj_form(traj, f"volumes.{DRIVER_ROOTS}.{k}")
    return raw or None


def c_driven_rule(B: dict, links: tuple, link_base: str, E0: dict | None = None) -> dict | None:
    """Книга-обязательство за драйвером строки (ключ volumes.liability_drivers, К6, решения № 3, Р8): книга растёт не с
    сектором средств бизнеса, а за «объёмной частью» строки — E_q = E_(q−1) (1 + wage_q)^((1 − λ)/4) (D_q / D_(q−1))^λ,
    λ — связь строки с объёмом, D — уровень базы строки на конце квартала (К2: своя база или volumes.link_base). Книга
    остаётся в средствах клиентов для сумм. Отказы: книга — не средства клиентов-бизнеса (актив, балансирующая, пара
    средств физлиц); база строки iea, funds, веса на балансирующих книгах или на самой книге — круг. Нет ключа или
    пустой словарь — None.

    Ключ volumes.liability_driver_roots (Р9-1, c_driver_roots): форма — всегда, и в неактивном режиме; ведомой книге,
    чья строка-драйвер есть в ключе, — d["root"] = траектория ρ строки: номинальная часть книги несёт корень, шаг
    × (1 + ρ_q)^(1 − λ). Книга без строки в ключе, снятый К6 (нет ключа К6 или пустой словарь) — ключ неактивного
    режима, не отказ."""
    roots = c_driver_roots(B)
    raw = c_bopt(B, "volumes.liability_drivers")
    if raw is None:
        if "liability_drivers" in (c_bopt(B, "volumes") or {}):
            raise ControlInputError("volumes.liability_drivers: null (М§0.1)")
        return None
    if not isinstance(raw, dict):
        raise ControlInputError("volumes.liability_drivers: словарь «книга → строка» (М§4.3)")
    if not raw:
        return None
    books = c_bget(B, "nii.books")
    biz = c_client_funds(books)
    balancing = (SECURITIES, LIQUIDITY, WHOLESALE)
    out = {}
    for b, line in raw.items():
        if b not in biz:
            raise ControlInputError(f"volumes.liability_drivers: {b!r} — не средства клиентов-бизнеса (М§4.3)")
        if line not in DRIVER_LINES:
            raise ControlInputError(f"volumes.liability_drivers.{b}: {line!r} — не {', '.join(DRIVER_LINES)} (М§4.3)")
        name, idx = DRIVER_LINES[line]
        spec = c_line_base(B, name, link_base, E0)
        if spec["kind"] in (LINK_BASES[1], LINK_BASES[2]):
            raise ControlInputError(f"volumes.liability_drivers.{b}: база строки {line} — {spec['kind']}: книга зависела бы "
                                    f"от баланса или от себя (М§4.3)")
        if spec["kind"] == BASE_WEIGHTS and any(spec["w"].get(x) for x in balancing + (b,)):
            raise ControlInputError(f"volumes.liability_drivers.{b}: веса базы строки {line} на балансирующих книгах или "
                                    f"на самой книге — круг (М§4.3)")
        out[b] = {"line": line, "lam": float(links[idx]), "spec": spec}
        if roots is not None and line in roots:
            out[b]["root"] = roots[line]                # Р9-1: корень номинальной части книги — ρ её строки
    return out


def c_driven_roots(drv: dict, y: int, qs) -> list[float] | None:
    """ρ кварталов qs года y ведомой книги (Р9-1): значения траектории ключа строки по правилу М§0.4 (c_traj_at); у
    книги без корня — None (прежняя строка)."""
    if "root" not in drv:
        return None
    return [c_traj_at(drv["root"], y, q) for q in qs]


def c_driven_path(drv: dict, start: float, levels: list, wage: list, roots: list | None = None) -> list[float]:
    """Путь книги за драйвером по концам кварталов (К6): levels — уровни базы строки D на концах кварталов (начало и
    конец каждого квартала, n + 1 точек), wage — рост зарплат мира кварталов. Связь 0 — рост с индексом зарплат, связь
    1 — ровно за драйвером. roots — ρ кварталов (Р9-1, ключ volumes.liability_driver_roots): номинальная часть книги
    несёт корень, шаг × (1 + ρ_j)^(1 − λ) отдельным множителем; None — прежняя строка (при λ = 1 и ρ = 0 множитель
    ровно 1,0)."""
    lam, path = drv["lam"], [start]
    for j, x in enumerate(wage):
        v = path[-1] * (1.0 + x) ** ((1.0 - lam) / QY) * (levels[j + 1] / levels[j]) ** lam
        if roots is not None:
            v *= (1.0 + roots[j]) ** (1.0 - lam)
        path.append(v)
    return path


def c_driven_line_rule(ctx: dict) -> bool:
    """Книга К6 формой строки (ключ volumes.line_link_form: line, Р10-5) при активном К6: ведомая книга b строки ℓ —
    E_b,q = E_b,0 × Ψ_q, Ψ_q = Ψ_(q−4) × c_link_growth(D_q / D_(q−4), w_q, λ, ρ_q, корень множителем), D — уровень базы
    строки на конце квартала (не средние: книга — остаток), ρ — ключ volumes.liability_driver_roots строки (нет строки в
    ключе — 0). История до якоря — концы фактов x = −3…0 (c_base_hist_end: loans | funds — balance.history, веса книг —
    balance.history.<период>.books, «номинал» — 1), Ψ_x = D_x / D_0; её записывает в книгу d["hist"] и d["d0"]. Нет конца
    истории — отказ входа (c_base_hist_end), D_x ≤ 0 — отказ. Без К6 или без ключа формы — False (прежняя цепь)."""
    drv = ctx.get("driven")
    if not (ctx.get("line_form") and drv):
        return False
    for b, d in drv.items():
        hist = {}
        for j in range(QY):
            yq = c_qback(ctx["anchor"], j)
            v = c_base_hist_end(ctx, d["spec"], *yq)
            if not v > 0.0:
                raise ControlInputError(f"уровень базы строки {d['line']} книги {b} на конце {yq[0]}Q{yq[1]} = {v} ≤ 0 "
                                        f"(Р10-5, М§4.3)")
            hist[yq] = v
        d["hist"], d["d0"] = hist, hist[ctx["anchor"]]
    return True


def c_driven_psi(ctx: dict, st: dict, b: str, d: dict, y: int, q: int, level: float, wage: float) -> float:
    """Ψ квартала (y, q) ведомой книги b формой строки (Р10-5): Ψ того же квартала прошлого года × c_link_growth(D_q /
    D того же квартала прошлого года, рост зарплат мира, λ, ρ_q, корень множителем). Квартал прошлого года после якоря —
    запись пути клетки (st["vend"]: D и Ψ конца квартала), до якоря — концы фактов, Ψ = D / D_0."""
    if (y - 1, q) > ctx["anchor"]:
        rec = st["vend"][(y - 1, q)]
        back_d, back_psi = rec[(K6_END_KEY, b)], rec[(K6_PSI_KEY, b)]
    else:
        back_d = d["hist"][(y - 1, q)]
        back_psi = back_d / d["d0"]
    root = c_traj_at(d["root"], y, q) if "root" in d else 0.0
    return back_psi * c_link_growth(level / back_d, wage, d["lam"], root, ctx["root_mult"])


def c_qback(yq: tuple, j: int) -> tuple[int, int]:
    """Квартал на j кварталов раньше (y, q)."""
    pos = yq[0] * QY + (yq[1] - 1) - j
    return pos // QY, pos % QY + 1


ALLOW_RESID_MAX = 0.05      # К7: остаток резерва вне книг — не больше этой доли резерва якоря (иначе факты не сходятся)


def c_allowance_rule(B: dict, A: dict, fv: dict) -> dict | None:
    """Резерв по книгам (ключ credit.allowance_by_book, К7, решения № 3, Р9): запас резерва следует за составом
    кредитов, как поток резервов множителей CoR по книгам. Покрытие книги якоря cov_b = A_b,0 / (E_b,0 − FV_b,0) —
    резерв книги из фактов balance.allowance_books.<b> к её кредитам по амортизированной стоимости; остаток вне книг
    R_0 = AL_0 − Σ_b A_b,0 (резерв облигаций по АС и т. п.) растёт с кредитами по АС. Нет ключа или enabled: false —
    None: прежняя строка AL = доля якоря × кредиты по АС. Нет узла у кредитной книги, резерв < 0 или не меньше
    кредитов книги, |R_0| больше 5 % AL_0 — отказ (нуля не подставлять)."""
    node = c_bopt(B, "credit.allowance_by_book")
    if node is None:
        return None
    if not isinstance(node, dict) or not isinstance(node.get("enabled"), bool):
        raise ControlInputError("credit.allowance_by_book: нужен выключатель enabled (М§0.1)")
    if not node["enabled"]:
        return None
    loans = [b for b, sp in c_bget(B, "nii.books").items() if sp.get("sector")]
    facts = A.get("allowance_books")
    if facts is None:
        raise ControlInputError("credit.allowance_by_book: нет узла фактов balance.allowance_books (М§4.3, прил. B)")
    allow = {}
    for b in loans:
        v = facts.get(b)
        if not c_is_number(v):
            raise ControlInputError(f"нет резерва книги balance.allowance_books.{b} (М§4.3, прил. B)")
        allow[b] = float(v)
    return c_allowance_cov({b: A["E0"][b] for b in loans}, allow, A["AL"], fv)


def c_allowance_cov(books0: dict, allow: dict, al0: float, fv: dict) -> dict:
    """Покрытия книг и остаток вне книг (К7) из остатков якоря books0, резерва по книгам allow и резерва якоря al0."""
    cov, ac0 = {}, 0.0
    for b, e in books0.items():
        ac = e * ((1.0 - fv[b]) if b in fv else 1.0)
        if not 0.0 <= allow[b] < ac:
            raise ControlInputError(f"резерв книги {b} = {allow[b]} вне [0; кредиты книги по АС {ac}) (М§4.3)")
        cov[b] = allow[b] / ac
        ac0 += ac
    resid = al0 - sum(allow.values())
    if abs(resid) > ALLOW_RESID_MAX * al0:
        raise ControlInputError(f"резерв по книгам не сходится с резервом якоря: остаток вне книг {resid} больше "
                                f"{ALLOW_RESID_MAX:.0%} резерва (М§4.3)")
    return {"cov": cov, "resid": resid, "ac0": ac0, "fv": dict(fv)}


def c_allowance_of(rule: dict, E: dict, ac: float) -> float:
    """AL = Σ_b cov_b (E_b − FV_b) + R_0 × кредиты по АС / кредиты по АС якоря (К7). E — остатки (на конце или средние)
    кредитных книг, ac — кредиты по АС того же момента."""
    fv = rule["fv"]
    return (sum(c * E[b] * ((1.0 - fv[b]) if b in fv else 1.0) for b, c in rule["cov"].items())
            + rule["resid"] * ac / rule["ac0"])


def c_cash_rule(B: dict, A: dict, books: dict) -> dict | None:
    """Неработающие деньги — актив со своим драйвером (ключ volumes.cash_assets, К8, решения № 4, Р4-6): деньги якоря
    C_0 (amount: число ≥ 0 или anchor — узел фактов balance.nonworking_money.total) идут за уровнем драйвера на концах
    кварталов, C = c × D, c = C_0 / D_0; драйвер — funds (средства клиентов: пара средств физлиц и средства бизнеса, с
    ведомыми книгами К6), loans (кредитные книги) или веса книг {книга: вес ≥ 0}. Прочие активы — растущая часть без денег
    (ρ − C_0 / L_0) × кредиты, деньги и постоянные: ρ = volumes.other_assets_to_loans не меняет смысла («растущие прочие
    активы с деньгами»), вычет C_0 / L_0 делает модель. RWA денег — своя плотность capital.rwa.density.cash_assets, у
    растущей части — плотность после выреза ω' = [ω (OA_0 − F_A) − ω_c C_0] / (OA_0 − F_A − C_0): RWA якоря тот же.
    Отказы: драйвер iea или веса на балансирующих книгах (круг через ликвидность), нет книги, все веса 0, D_0 ≤ 0; денег не
    меньше растущей части прочих активов, ρ − C_0 / L_0 < 0, ω' < 0; нет плотности денег. Нет ключа или null (ключ снят
    вариантом «деньги за кредитами», spec К8) — None.

    Доля денег книги (Р6-1, необязательные поля share, reserves, share_from, displaced_weight; правила — c_cash_share):
    при числовой доле правило несёт путь доли «path» (функции c_cash_c, c_cash_cut, c_cash_disp); без поля share и при
    share: anchor — прежняя ветвь (path = None), числа бит в бит прежние."""
    node = c_bopt(B, "volumes") or {}
    if node.get("cash_assets") is None:
        return None
    raw = node["cash_assets"]
    if (not isinstance(raw, dict) or not {"amount", "driver"} <= set(raw)
            or not set(raw) <= {"amount", "driver", *CASH_SHARE_FIELDS}):
        raise ControlInputError("volumes.cash_assets: объект {amount, driver[, share, reserves, share_from, "
                                "displaced_weight]} (М§4.3)")
    amount = raw["amount"]
    if amount == "anchor":
        amount = A.get("cash_fact")
        if not c_is_number(amount):
            raise ControlInputError("volumes.cash_assets.amount: anchor без узла фактов balance.nonworking_money.total "
                                    "(прил. B)")
    if not c_is_number(amount) or float(amount) < 0.0:
        raise ControlInputError(f"volumes.cash_assets.amount: {amount!r} — не число ≥ 0 (М§4.3)")
    c0 = float(amount)
    loans = [b for b, sp in books.items() if sp.get("sector")]
    drv = raw["driver"]
    if drv == CASH_WORDS[0]:
        weights = {b: 1.0 for b in c_fund_word_books(B, books)}       # Р11-2: при funds_scope: clients — без книг К6
    elif drv == CASH_WORDS[1]:
        weights = {b: 1.0 for b in loans}
    elif isinstance(drv, dict) and drv:
        weights = {}
        for b, v in drv.items():
            if str(b) not in books:
                raise ControlInputError(f"volumes.cash_assets.driver: {b!r} — не книга nii.books (М§4.3)")
            if str(b) in BALANCING_BOOKS:
                raise ControlInputError(f"volumes.cash_assets.driver: {b} — балансирующая книга: деньги шли бы за "
                                        f"ликвидностью, которая зависит от денег (круг, М§4.3)")
            if not c_is_number(v) or float(v) < 0.0:
                raise ControlInputError(f"volumes.cash_assets.driver.{b}: вес — не число ≥ 0 (М§4.3)")
            weights[str(b)] = float(v)
        if not any(weights.values()):
            raise ControlInputError("volumes.cash_assets.driver: все веса нулевые (М§4.3)")
    else:
        raise ControlInputError(f"volumes.cash_assets.driver: {drv!r} — не {', '.join(CASH_WORDS)} и не веса книг "
                                f"(iea — круг через ликвидность, М§4.3)")
    dens = c_bget(B, "capital.rwa.density")
    w_c = dens.get("cash_assets")
    if not c_is_number(w_c) or float(w_c) < 0.0:
        raise ControlInputError("capital.rwa.density.cash_assets: нет плотности денег при ключе volumes.cash_assets "
                                "(число ≥ 0, М§4.11)")
    E0 = A["E0"]
    d0 = sum(w * E0[b] for b, w in weights.items() if w)
    if not d0 > 0.0:
        raise ControlInputError(f"volumes.cash_assets: уровень драйвера на якоре D_0 = {d0} не больше нуля (М§4.3)")
    grow0 = A["OA"] - A["OA_fixed"]                     # растущая часть прочих активов якоря (с деньгами)
    if not c0 < grow0:
        raise ControlInputError(f"volumes.cash_assets: денег якоря {c0} не меньше растущей части прочих активов {grow0} "
                                f"(М§4.3)")
    cut = c0 / sum(E0[b] for b in loans)
    rho = c_bnum(B, "volumes.other_assets_to_loans")
    if rho - cut < 0.0:
        raise ControlInputError(f"volumes.cash_assets: растущие прочие активы без денег на рубль кредита "
                                f"ρ − C_0 / L_0 = {rho - cut} < 0 (М§4.3)")
    w_oa = float(dens["other_assets"])
    w_carved = (w_oa * grow0 - float(w_c) * c0) / (grow0 - c0)
    if w_carved < 0.0:
        raise ControlInputError(f"volumes.cash_assets: плотность растущих прочих активов после выреза денег {w_carved} "
                                f"< 0 (М§4.11)")
    rule = {"c0": c0, "d0": d0, "c": c0 / d0, "w": weights, "cut": cut, "w_cash": float(w_c), "w_rest": w_carved,
            "driver": drv}
    rule["path"] = c_cash_share(B, A, raw, rule, sum(E0[b] for b in loans), rho)
    return rule


def _c_is_period(v) -> bool:
    """Квартал книги вида «ГГГГQn» (строка): год из четырёх цифр, квартал 1…4."""
    if not isinstance(v, str):
        return False
    y, sep, q = v.partition("Q")
    return bool(sep) and len(y) == 4 and y.isdigit() and len(q) == 1 and q.isdigit() and 1 <= int(q) <= QY


def c_cash_share(B: dict, A: dict, raw: dict, rule: dict, l0: float, rho: float) -> dict | None:
    """Доля неработающих денег — параметр книги (Р6-1, решения ведущего № 6; методика core-pass5). Поля volumes.cash_assets:
    share — доля денег БЕЗ ФОР s* к уровню драйвера на конце квартала (число 0 ≤ s* < 1) или anchor (прежняя ветвь);
    reserves — ФОР якоря R_0 (число ≥ 0 или anchor — узел фактов balance.nonworking_money.mandatory_reserves); share_from —
    квартал ГГГГQn, с которого действует доля книги; displaced_weight — θ ∈ [0; 1], вес вытесненной части прочих активов
    (0 — как деньги, 1 — как растущие прочие без денег; поля нет — θ = 1).

    Путь (своё прочтение): s_0 = (C_0 − R_0) / D_0, r = R_0 / D_0 (ФОР — доля якоря к средствам), q_f — номер квартала
    share_from на сетке; s_k = s_0 + (s* − s_0) k / q_f до q_f, дальше s*; c_k = s_k + r, c_0 = C_0 / D_0 — факт якоря.
    Вычет из растущих прочих активов на рубль кредита — c_k D_0 / L_0 (на структуре якоря, общей для клеток); поправка RWA
    на рубль кредита — (1 − θ)(ω' − ω_c)(c_k − c_0) D_0 / L_0, ω' — вырез на раскладке факта (правило К8 выше).

    Правила: поля формы проверяются всегда; поля без share — отказ «читается только при share»; при share: anchor они не
    читаются (ключ неактивного режима) — None. При числовой доле нужны reserves и share_from; share_from — после квартала
    якоря и не позже meta.last_period; R_0 > C_0 — отказ; ρ′* = ρ − (s* + R_0 / D_0) D_0 / L_0 < 0 — отказ с числами."""
    share = raw.get("share")
    rest = [f for f in CASH_SHARE_FIELDS[1:] if f in raw]
    if "reserves" in raw and not (raw["reserves"] == "anchor" or (c_is_number(raw["reserves"])
                                                                 and float(raw["reserves"]) >= 0.0)):
        raise ControlInputError(f"volumes.cash_assets.reserves: {raw['reserves']!r} — не число ≥ 0 и не anchor (Р6-1)")
    if "share_from" in raw and not _c_is_period(raw["share_from"]):
        raise ControlInputError(f"volumes.cash_assets.share_from: {raw['share_from']!r} — не квартал ГГГГQn (Р6-1)")
    if "displaced_weight" in raw and not (c_is_number(raw["displaced_weight"])
                                          and 0.0 <= float(raw["displaced_weight"]) <= 1.0):
        raise ControlInputError(f"volumes.cash_assets.displaced_weight: {raw['displaced_weight']!r} — не число в [0; 1] "
                                f"(Р6-1)")
    if "share" not in raw:
        if rest:
            raise ControlInputError(f"volumes.cash_assets.{rest[0]}: читается только при share (Р6-1)")
        return None
    if share == "anchor":
        return None                                     # прежняя ветвь: прочие поля — ключ неактивного режима
    if not c_is_number(share) or not 0.0 <= float(share) < 1.0:
        raise ControlInputError(f"volumes.cash_assets.share: {share!r} — не число в [0; 1) и не anchor (Р6-1)")
    for f in ("reserves", "share_from"):
        if f not in raw:
            raise ControlInputError(f"volumes.cash_assets.{f}: нужен при числовой доле share — ФОР якоря и квартал доли "
                                    f"книги (Р6-1)")
    res = raw["reserves"]
    if res == "anchor":
        res = A.get("cash_reserves_fact")
        if not c_is_number(res):
            raise ControlInputError("volumes.cash_assets.reserves: anchor без узла фактов "
                                    "balance.nonworking_money.mandatory_reserves (прил. B)")
    r0, c0, d0 = float(res), rule["c0"], rule["d0"]
    if r0 > c0:
        raise ControlInputError(f"volumes.cash_assets.reserves: ФОР якоря {r0} больше денег якоря {c0} (Р6-1)")
    anchor = tuple(A["anchor"])
    q_f = c_qidx(anchor, *c_per_parse(raw["share_from"]))
    last = c_per_parse(c_bget(B, "meta.last_period"))
    if q_f < 1 or q_f > c_qidx(anchor, *last):
        raise ControlInputError(f"volumes.cash_assets.share_from: {raw['share_from']} — не после квартала якоря "
                                f"{anchor[0]}Q{anchor[1]} или позже meta.last_period {last[0]}Q{last[1]} (Р6-1)")
    s_star, r = float(share), r0 / d0
    rho_star = rho - (s_star + r) * d0 / l0
    if rho_star < 0.0:
        raise ControlInputError(f"volumes.cash_assets.share: денег книги больше растущей части прочих активов якоря — "
                                f"ρ′* = ρ − (s* + R_0 / D_0) D_0 / L_0 = {rho} − ({s_star} + {r0} / {d0}) × {d0} / {l0} = "
                                f"{rho_star} < 0 (Р6-1)")
    theta = float(raw.get("displaced_weight", 1.0))
    return {"s_star": s_star, "s0": (c0 - r0) / d0, "r": r, "r0": r0, "q_f": q_f, "l0": l0, "theta": theta,
            "k_disp": None if theta == 1.0 else (1.0 - theta) * (rule["w_rest"] - rule["w_cash"])}


def c_cash_c(rule: dict, k: int) -> float:
    """Доля денег с ФОР к уровню драйвера на конце квартала k сетки (якорь — 0): прежняя ветвь — c = C_0 / D_0 во всех
    кварталах; доля книги (Р6-1) — c_k = s_k + r по линейному пути к s* до квартала share_from, c_0 = C_0 / D_0."""
    p = rule.get("path")
    if p is None or k <= 0:
        return rule["c"]
    s = p["s_star"] if k >= p["q_f"] else p["s0"] + (p["s_star"] - p["s0"]) * k / p["q_f"]
    return s + p["r"]


def c_cash_cut(rule: dict, k: int) -> float:
    """Вычет денег из растущих прочих активов на рубль кредита на конце квартала k: прежняя ветвь — C_0 / L_0; доля
    книги — c_k D_0 / L_0 (структура якоря, общая для клеток; прочие активы OA = (ρ − вычет) L + C + F_A)."""
    p = rule.get("path")
    if p is None or k <= 0:
        return rule["cut"]
    return c_cash_c(rule, k) * rule["d0"] / p["l0"]


def c_cash_disp(rule: dict | None, k: int, loans: float) -> float | None:
    """Слагаемое RWA вытесненной части прочих активов на конце квартала k (до дрейфа, валютного индекса и множителя
    режима): (1 − θ)(ω' − ω_c) δ_k L, δ_k = (c_k − c_0) D_0 / L_0. Нет доли книги или θ = 1 — None (прежняя строка)."""
    p = None if rule is None else rule.get("path")
    if p is None or p["k_disp"] is None:
        return None
    return p["k_disp"] * (c_cash_c(rule, k) - rule["c"]) * rule["d0"] / p["l0"] * loans


def c_cash_level(rule: dict, E: dict) -> float:
    """Уровень драйвера денег D = Σ ω_b E_b по остаткам E (К8): концы кварталов или средние периода."""
    return sum(w * E[b] for b, w in rule["w"].items() if w)


def c_client_funds(books: dict) -> list[str]:
    """Небалансирующие пассивы, кроме пары средств физлиц, — средства клиентов-бизнеса (М§4.1 п. 1)."""
    return [b for b, sp in books.items()
            if sp["side"] != LOANS_SIDE and b not in (RETAIL_CURRENT, RETAIL_TERM, WHOLESALE)]


FUNDS_SCOPE_KINDS = ("all", "clients")      # volumes.funds_scope: «средства клиентов» балансовой механики (Р11-2)


def c_funds_scope(B: dict) -> list[str]:
    """Книги, которых нет в слове «средства клиентов» балансовой механики (ключ volumes.funds_scope, решения № 11, Р11-2;
    класс 1 — одно слово, одна величина с checks.client_funds): clients при активном К6 (непустой volumes.liability_drivers)
    — ведомые книги К6; all, нет ключа и clients без К6 (ключ неактивного режима) — пусто, прежние числа бит в бит. Слово
    читают база структурного опта К3 и опт в среднем балансирующих статей, якорь volumes.wholesale_to_funds, база строки
    funds (уровень на якоре, средние и концы кварталов пути, смесь К2б), драйвер денег К8 словом; строка баланса «средства»
    (тождество капитала и баланса) — все книги. Форма — всегда: null и значение не из перечня — отказ (М§0.1)."""
    node = c_bopt(B, "volumes") or {}
    if "funds_scope" not in node:
        return []
    v = node["funds_scope"]
    if not isinstance(v, str) or v not in FUNDS_SCOPE_KINDS:
        raise ControlInputError(f"volumes.funds_scope: {v!r} — не {', '.join(FUNDS_SCOPE_KINDS)} (М§0.1, §4.3)")
    drv = node.get("liability_drivers")
    if v == FUNDS_SCOPE_KINDS[0] or not isinstance(drv, dict) or not drv:
        return []
    return [str(b) for b in drv]


def c_fund_biz(B: dict, books: dict) -> list[str]:
    """Средства клиентов-бизнеса в слове «средства клиентов» балансовой механики: все (c_client_funds), при
    volumes.funds_scope: clients и активном К6 — без ведомых книг К6 (c_funds_scope)."""
    out = c_funds_scope(B)
    return [b for b in c_client_funds(books) if b not in out]


def c_fund_word_books(B: dict, books: dict) -> list[str]:
    """Книги слова «средства клиентов» балансовой механики (М§4.1, §4.3): пара средств физлиц и c_fund_biz."""
    return [RETAIL_CURRENT, RETAIL_TERM, *c_fund_biz(B, books)]


def c_unaudited_anchor(book: dict, A: dict):
    """E_0 — неаудированная прибыль на якоре по календарю аудитов (М§4.11); None — нет фактов кварталов."""
    cut = [int(c) for c in c_bget(book, "capital.n11.audit_cutoffs")]
    total = 0.0
    for yq in _c_unaudited_quarters(cut, *A["anchor"]):
        rec = A["pnl"].get(f"{yq[0]}Q{yq[1]}")
        if rec is None or rec.get("ni_shareholders") is None:
            return None
        total += float(rec["ni_shareholders"])
    return total


def c_resolve_anchor_keys(book: dict, A: dict) -> tuple[dict, dict]:
    """Книга с числами вместо "anchor" (формулы — прил. A М) и таблица выведенных значений."""
    B = copy.deepcopy(book)
    E0 = A["E0"]
    books = B["nii"]["books"]
    loans = [b for b, spec in books.items() if spec.get("sector")]
    sum_loans = sum(E0[b] for b in loans)
    loans_ac = sum_loans - A["fv_loans"] if A["fv_loans"] is not None else sum_loans
    biz = c_client_funds(books)
    k6_out = c_funds_scope(B)
    if k6_out:
        # Р11-2: якорь доли опта — опт / средства клиентов без ведомых книг К6 (та же величина, что база опта К3)
        funds = E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + sum(E0[b] for b in biz if b not in k6_out)
    elif biz == [CORP_FUNDS]:
        funds = E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + E0[CORP_FUNDS]
    else:
        funds = E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + sum(E0[b] for b in biz)
    la = E0[SECURITIES] + E0[LIQUIDITY]
    # постоянные прочие активы (М§4.3): число книги или узел фактов; без ключа — 0, и формула образца
    oaf_key = c_bopt(B, "volumes.other_assets_fixed")
    if oaf_key == "anchor":
        if A["OA_fixed_fact"] is None:
            raise ControlInputError("volumes.other_assets_fixed: anchor без узла balance.other_assets_fixed")
        oaf = float(A["OA_fixed_fact"])
    else:
        oaf = float(oaf_key or 0.0)
    if oaf < 0.0 or oaf > A["OA"]:
        raise ControlInputError("постоянные прочие активы вне [0; прочие активы якоря] (М§4.3)")
    A["OA_fixed"] = oaf
    formulas = {
        "credit.allowance_ratio": A["AL"] / loans_ac,
        "nii.retail_current_share.c_ref": A["current_share"],
        "nii.retail_current_share.key_ref": A["key_ref"],
        "volumes.wholesale_to_funds": E0[WHOLESALE] / funds,
        "volumes.securities_share_of_liquid": E0[SECURITIES] / la,
        "volumes.other_assets_fixed": oaf,
        "volumes.other_assets_to_loans": (A["OA"] - oaf) / sum_loans if oaf else A["OA"] / sum_loans,
        "volumes.other_liabilities_to_loans": A["OL"] / sum_loans,
        "oci.fvoci_share": A["fvoci_debt"] / E0[SECURITIES],
        "oci.fvtpl_bond_share": (A["fvtpl_bonds"] or 0.0) / E0[SECURITIES],
    }
    for b in c_fv_books(books):
        if A["fv_loans"] is not None:
            formulas[f"nii.books.{b}.fv_share"] = A["fv_loans"] / E0[b]
    # вычеты капитала якоря словом anchor (М§4.11, прил. A): Ded20_0 = BV − капитал группы без
    # регуляторных инструментов; Ded11_0 = BVreg − max(E_0, 0) − базовый капитал группы
    if c_bget(B, "capital.n20.deductions_anchor") == "anchor":
        if A["group_cet1"] is None:
            raise ControlInputError("capital.n20.deductions_anchor: anchor без узла capital.basel.cet1")
        formulas["capital.n20.deductions_anchor"] = A["BV"] - float(A["group_cet1"])
    if c_bget(B, "capital.n11.deductions_anchor") == "anchor":
        e0 = c_unaudited_anchor(B, A)
        if A["base_capital"] is None or e0 is None:
            raise ControlInputError("capital.n11.deductions_anchor: anchor без базового капитала группы "
                                    "или прибыли неаудированного периода якоря")
        bvreg0 = A["BV"] + c_dpreg_anchor(B, A) - (1.0 - c_bnum(B, "capital.n20.fvoci_recognition")) * A["R0"]
        formulas["capital.n11.deductions_anchor"] = bvreg0 - max(e0, 0.0) - float(A["base_capital"])
    derived = {}

    def c_walk(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():
                path = f"{prefix}.{k}" if prefix else str(k)
                if v == "anchor":
                    if path == "nii.transmission.weights":
                        continue                                # веса — структура якоря (М§4.5)
                    if path.startswith("meta.labels."):
                        continue                                # подпись, не ключ вывода
                    if path.startswith("capital.rwa.guarantees.notional."):
                        continue                                # номинал гарантий: узел фактов читает сам ключ К5
                    if path == "volumes.cash_assets.amount":
                        continue                                # деньги якоря: узел фактов читает сам ключ К8
                    if path in ("volumes.cash_assets.share", "volumes.cash_assets.reserves"):
                        continue                                # доля якоря и ФОР: читает сам ключ (Р6-1)
                    if path not in formulas:
                        raise ControlInputError(f"anchor-ключ без формулы: {path}")
                    node[k] = formulas[path]
                    derived[path] = formulas[path]
                else:
                    c_walk(v, path)

    c_walk(B, "")
    return B, derived


# ============================================================================ мост упр. ↔ движок (М§4.6)

def c_to_engine(A: dict, x: str, v: float) -> float:
    method, b = A["bridge"][x]
    if method == "additive":
        return v + b
    if method == "ratio":
        return v * b
    raise ControlInputError(f"метод моста {method}")


def c_to_mgmt(A: dict, x: str, v: float) -> float:
    if x not in A["bridge"]:
        raise ControlInputError(f"в фактах нет моста упр. ↔ движок для {x} (М§4.6)")
    method, b = A["bridge"][x]
    return v - b if method == "additive" else v / b


# ============================================================================ миры

def c_world_quarter(book: dict, w: str, field: str, y: int, q: int) -> float:
    return c_traj_at(c_bget(book, f"worlds.{w}.{field}"), y, q)


def c_ref_field(ref: str) -> str:
    return "key_rate" if ref == "key" else ref


def c_kappa_world(book: dict):
    """Мир-опора κ (ключ книги credit.kappa_reference_world): мир, в котором стоят уровни CoR режимов. Нет
    ключа — None: добавка образца, относительно мира N и только вверх."""
    ref = c_bopt(book, "credit.kappa_reference_world")
    if ref is not None and ref not in c_bget(book, "worlds.ids"):
        raise ControlInputError(f"credit.kappa_reference_world: {ref!r} — не мир из worlds.ids (М§4.6)")
    return ref


def c_kappa_spread(book: dict, w: str, y: int, q: int) -> float:
    """Разность реальных ставок квартала (y, q), на которую умножается κ в мире w (М§4.6). С миром-опорой —
    rr_w − rr_опоры с любым знаком: в мире-опоре ноль, в мире с меньшей реальной ставкой добавка
    отрицательна. Без ключа — max(0, rr_w − rr_N)."""
    rr = c_world_quarter(book, w, "real_key", y, q)
    ref = c_kappa_world(book)
    if ref is None:
        return max(0.0, rr - c_world_quarter(book, W_LOW, "real_key", y, q))
    return rr - c_world_quarter(book, ref, "real_key", y, q)


def c_g_terminal(book: dict, w: str) -> float:
    """g_T мира до защиты k_T − 0,0001 (М§7)."""
    return ((1.0 + c_bnum(book, f"worlds.{w}.lt_inflation"))
            * (1.0 + c_bnum(book, "valuation.terminal.real_growth")) - 1.0)


def c_overlay_growth(book: dict, w: str, group: str, name: str, y: int) -> float:
    """Рост надстройки миров года y; после последнего года — линейный сход к g_T к lt_from (М§4.3)."""
    table = {int(k): float(v) for k, v in c_bget(book, f"worlds_bank.{w}.{group}.{name}").items()}
    if y in table:
        return table[y]
    first, last = min(table), max(table)
    if y < first:
        return table[first]
    gt = c_g_terminal(book, w)
    lt_from = int(c_bnum(book, "volumes.lt_from"))
    if y >= lt_from:
        return gt
    return table[last] + (gt - table[last]) * (y - last) / (lt_from - last)


# ============================================================================ передача ставки (М§4.5)

PHI_SHARE = "phi_share"     # nii.books.<b>.phi_share: доля сжатия ставки книги к опоре между мирами (Р11-1)


def c_phi_shares(B: dict) -> dict[str, float]:
    """Доли сжатия ставки книги к её опоре между мирами (ключ nii.books.<b>.phi_share, решения № 11, Р11-1; класс 6,
    тип Б — совместный подбор листа бэктеста книг): у любой книги ЧПД — актива, пассива, балансирующей, пары средств
    физлиц. Цель ставки книги в мире W — прежняя минус share_b × (ref_b,W − ref_b,H): между мирами наклон актива к опоре
    1 − φ_A [Φ_A] − share, пассива β + φ_L dX/dref − share; в мире-опоре H слагаемое — ноль. Отказы: значение не число
    (null, логическое, строка — М§0.1), |share| ≥ 1 (ставка шла бы против опоры). 0 и нет поля — одна ветвь (книги в
    словаре нет). → {книга: доля ≠ 0}."""
    out = {}
    for b, sp in c_bget(B, "nii.books").items():
        if not isinstance(sp, dict) or PHI_SHARE not in sp:
            continue
        v = sp[PHI_SHARE]
        if not c_is_number(v):
            raise ControlInputError(f"nii.books.{b}.{PHI_SHARE}: {v!r} — не число (М§0.1, §4.4)")
        if not abs(float(v)) < 1.0:
            raise ControlInputError(f"nii.books.{b}.{PHI_SHARE} = {v}: |доля| ≥ 1 — ставка книги шла бы против опоры "
                                    f"(М§4.4)")
        if float(v) != 0.0:
            out[str(b)] = float(v)
    return out


def c_share_ref(b: str, sp: dict) -> str:
    """Опора, к которой стоит доля сжатия книги в стационаре (Р11-1): у пары средств физлиц — ключевая (их стоимость в
    стационаре — от ключевой мира, М§4.5), у прочих книг — своя опора ref."""
    return "key" if b in (RETAIL_CURRENT, RETAIL_TERM) else sp["ref"]


def c_share_term(share: float, ref_w: float, ref_h: float) -> float:
    """Слагаемое доли сжатия книги (Р11-1), которое вычитается из цели ставки актива и из стоимости пассива: share ×
    (опора мира − опора мира H) — в квартале пути и в стационаре (там опора мира со сдвигом δ). Одна функция у пути клетки,
    стационара решателя, эффективного LT-спреда и кредитной маржи."""
    return share * (ref_w - ref_h)


def c_transmission_ctl(book: dict, A: dict) -> dict:
    """σ0_A, σ0_L, φ, φ_A, φ_L, target_eng, T_real, T(W), пары, эффективные LT-спреды кредитных книг и
    кредитная маржа миров — замкнутое решение по стационарному ЧПМ (М§4.5). Сдвиг Δ0 делит
    nii.sigma0_split, сжатие φ — nii.phi_split: объём сжатия мира φ × C_W один при любой доле, доля p
    снимается со спредов кредитных книг Φ_A, остаток — добавка к стоимости пассивов Φ_L. Ключ цели
    (target_eng) — стационарный ЧПМ мира nii.transmission.level_world (nss_level); без ключа — мира-опоры."""
    books = c_bget(book, "nii.books")
    E0 = A["E0"]
    iea = sum(E0[b] for b, s in books.items() if s["side"] == LOANS_SIDE)
    yl, ql = c_per_parse(c_bget(book, "meta.last_period"))
    ref_w = c_bget(book, "nii.transmission.reference_world")

    def c_ref_lt(w, ref):
        return c_world_quarter(book, w, c_ref_field(ref), yl, ql)

    def c_s_lt(b):
        return c_traj_at(books[b]["spread"], yl, ql)

    c_ref = c_bnum(book, "nii.retail_current_share.c_ref")
    k_ref = c_bnum(book, "nii.retail_current_share.key_ref")
    psi = c_bnum(book, "nii.retail_current_share.psi")
    lo, hi = (float(x) for x in c_bget(book, "nii.retail_current_share.bounds"))
    dia = c_bnum(book, "nii.dia_rate")
    l_r = (E0[RETAIL_CURRENT] + E0[RETAIL_TERM]) / iea
    # Р11-1: доли сжатия книг к опоре между мирами; без ключа словарь пуст и ни одна строка ниже не меняется
    shr = c_phi_shares(book)

    def c_share_cut(b, w, d):
        # share_b × (ref_b,W + δ − ref_b,H) на LT-уровне: в мире-опоре H при δ = 0 — ноль
        ref = c_share_ref(b, books[b])
        return c_share_term(shr[b], c_ref_lt(w, ref) + d, c_ref_lt(ref_w, ref))

    def c_cstar(key):
        return min(hi, max(lo, c_ref - psi * (key - k_ref)))

    def c_cost_lt(b, base, sl, w=None, d=0.0):
        # стоимость пассива в стационаре: β × опора + s^LT − σ0_L × [lt_shift] (− доля сжатия книги, Р11-1)
        sp = books[b]
        cost = float(sp["beta"]) * base + c_s_lt(b) - (sl if sp.get("lt_shift") else 0.0)
        if w is not None and b in shr:
            cost -= c_share_cut(b, w, d)
        return cost

    def c_nss(w, d, sa, sl, ph):
        key = c_ref_lt(w, "key") + d
        tot = 0.0
        for b, sp in books.items():
            wgt = E0[b] / iea
            r_w = c_ref_lt(w, sp["ref"]) + d
            if sp["side"] == LOANS_SIDE:
                val = r_w + c_s_lt(b) + (sa if sp.get("lt_shift") else 0.0)
                if sp.get("phi"):
                    val -= ph * (r_w - c_ref_lt(ref_w, sp["ref"]))
                if b in shr:
                    val -= c_share_cut(b, w, d)
                tot += wgt * val
            elif b not in (RETAIL_CURRENT, RETAIL_TERM):
                tot -= wgt * c_cost_lt(b, r_w, sl, w, d)
        c = c_cstar(key)
        tot -= l_r * (c * c_cost_lt(RETAIL_CURRENT, key, sl, w, d) + (1.0 - c) * c_cost_lt(RETAIL_TERM, key, sl, w, d))
        tot -= dia * l_r
        return tot

    target = c_to_engine(A, "nim", c_bnum(book, "nii.nim_lt_target_mgmt"))
    split = c_bnum(book, "nii.sigma0_split")
    if not 0.0 <= split <= 1.0:
        raise ControlInputError("nii.sigma0_split вне [0; 1] (М прил. A)")
    # Δ0 — нужный сдвиг стационарного ЧПМ мира H (там сжатие φ равно нулю); долю split несут активы с
    # lt_shift, остаток — пассивы с lt_shift. Вес пассива в стационаре мира H: у средств ФЛ —
    # l_R × c*(key_H^LT) (текущие) и l_R × (1 − c*(key_H^LT)) (срочные), у прочих — l_b.
    base_ref = c_nss(ref_w, 0.0, 0.0, 0.0, 0.0)
    w_assets = sum(E0[b] / iea for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("lt_shift"))
    c_h = c_cstar(c_ref_lt(ref_w, "key"))
    w_liab = 0.0
    for b, s in books.items():
        if s["side"] == LOANS_SIDE or not s.get("lt_shift"):
            continue
        w_liab += l_r * c_h if b == RETAIL_CURRENT else l_r * (1.0 - c_h) if b == RETAIL_TERM else E0[b] / iea
    if split > 0.0 and w_assets == 0.0:
        raise ControlInputError("nii.sigma0_split > 0 без актива с lt_shift (М§4.5)")
    if split < 1.0 and w_liab == 0.0:
        raise ControlInputError("nii.sigma0_split < 1 без пассива с lt_shift (М§4.5)")
    dk = c_ref_lt(W_MKT, "key") - c_ref_lt(W_LOW, "key")
    if dk == 0.0:
        raise ControlInputError("передача не определена: key_M^LT = key_N^LT")
    dphi = sum(E0[b] / iea * (c_ref_lt(W_MKT, s["ref"]) - c_ref_lt(W_LOW, s["ref"]))
               for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("phi")) / dk
    if dphi == 0.0:
        raise ControlInputError("передача не определена: D = 0")
    t_star = c_bnum(book, "nii.transmission.target")

    def c_shifts(d0):
        # сдвиги спредов и сжатие при сдвиге Δ0 стационарного ЧПМ мира-опоры: (σ0_A, σ0_L, T при φ = 0, φ)
        sa = split * d0 / w_assets if split > 0.0 else 0.0
        sl = (1.0 - split) * d0 / w_liab if split < 1.0 else 0.0
        flat = (c_nss(W_MKT, 0.0, sa, sl, 0.0) - c_nss(W_LOW, 0.0, sa, sl, 0.0)) / dk
        return sa, sl, flat, (flat - t_star) / dphi

    # Чей уровень задаёт ключ цели (nii.transmission.level_world): без ключа — мира-опоры, и Δ0 — прямая
    # разность. С ключом ключ цели — стационарный ЧПМ названного мира на составе якоря: он линеен по Δ0
    # (σ0 и φ линейны по Δ0 и входят слагаемыми), поэтому Δ0 — из значения при Δ0 = 0 и отклика на единицу.
    level_w = c_bopt(book, "nii.transmission.level_world")
    if level_w is not None and level_w not in c_bget(book, "worlds.ids"):
        raise ControlInputError(f"nii.transmission.level_world: {level_w!r} — не мир из worlds.ids (М§4.5)")
    if level_w is None or level_w == ref_w:
        delta0 = target - base_ref
    else:
        def c_level(d0):
            sa, sl, _, ph = c_shifts(d0)
            return c_nss(level_w, 0.0, sa, sl, ph)

        at_zero = c_level(0.0)
        unit = c_level(1.0) - at_zero
        if unit == 0.0:
            raise ControlInputError(f"стационарный ЧПМ мира {level_w} не зависит от сдвига спредов (М§4.5)")
        delta0 = (target - at_zero) / unit
    sigma0, sigma0_l, t0, phi = c_shifts(delta0)
    t_real = (c_nss(W_MKT, 0.0, sigma0, sigma0_l, phi) - c_nss(W_LOW, 0.0, sigma0, sigma0_l, phi)) / dk
    h = c_bnum(book, "nii.transmission.fd_step")
    ids = list(c_bget(book, "worlds.ids"))
    t_loc = {w: (c_nss(w, h, sigma0, sigma0_l, phi) - c_nss(w, -h, sigma0, sigma0_l, phi)) / (2.0 * h)
             for w in ids}
    # Парные передачи соседних по key^LT миров (М§4.5): равные key^LT — пара не определена (None).
    key_lt = {w: c_ref_lt(w, "key") for w in ids}
    nss0 = {w: c_nss(w, 0.0, sigma0, sigma0_l, phi) for w in ids}
    # Раскладка сжатия (М§4.5): φ_A = p × φ — спреды кредитных книг Φ_A; φ_L = (1 − p) × φ × A / L —
    # добавка к стоимости пассивов Φ_L на единицу X_W = Σ ω_b × (ref_b,W − ref_b,H), ω_b = a_b / A.
    # Флаг phi у обеих книг средств ФЛ обязан совпадать: их веса в стационаре зависят от мира.
    p_split = c_bnum(book, "nii.phi_split")
    if not 0.0 <= p_split <= 1.0:
        raise ControlInputError("nii.phi_split вне [0; 1] (М прил. A)")
    if bool(books[RETAIL_CURRENT].get("phi")) != bool(books[RETAIL_TERM].get("phi")):
        raise ControlInputError("флаг phi у книг средств ФЛ разный (М§4.5)")
    phi_a_w = {b: E0[b] / iea for b, s in books.items() if s["side"] == LOANS_SIDE and s.get("phi")}
    a_sum = sum(phi_a_w.values())
    l_sum = sum(E0[b] / iea for b, s in books.items() if s["side"] != LOANS_SIDE and s.get("phi"))
    if p_split > 0.0 and a_sum == 0.0:
        raise ControlInputError("nii.phi_split > 0 без актива с phi (М§4.5)")
    if p_split < 1.0 and l_sum == 0.0:
        raise ControlInputError("nii.phi_split < 1 без пассива с phi (М§4.5)")
    phi_a = p_split * phi
    phi_l = (1.0 - p_split) * phi * a_sum / l_sum if p_split < 1.0 else 0.0
    omega = {b: v / a_sum for b, v in phi_a_w.items()}
    x_lt = {w: sum(omega[b] * (c_ref_lt(w, books[b]["ref"]) - c_ref_lt(ref_w, books[b]["ref"])) for b in omega)
            for w in ids}
    # Эффективный LT-спред кредитной книги к её опоре в стационаре мира (М§4.5, гейт lt_spread_floor):
    # s_eff = s^LT + σ0_A × [lt_shift] − φ_A × [b ∈ Φ_A] × (ref_W^LT − ref_H^LT) − share_b × (ref_W^LT − ref_H^LT) (Р11-1)
    lt_spread = {}
    for b, s in books.items():
        if not s.get("sector"):
            continue
        lt_spread[b] = {w: (c_s_lt(b) + (sigma0 if s.get("lt_shift") else 0.0)
                            - (phi_a * (c_ref_lt(w, s["ref"]) - c_ref_lt(ref_w, s["ref"])) if s.get("phi") else 0.0))
                        for w in ids}
        if b in shr:
            lt_spread[b] = {w: v - c_share_cut(b, w, 0.0) for w, v in lt_spread[b].items()}

    def c_nss_books(w):
        # стационарный ЧПМ «по книгам»: сжатие — долями φ_A (спреды Φ_A) и φ_L × X_W (стоимость Φ_L);
        # обязан совпасть с Nss(W, 0), где сжатие — одним слагаемым φ × C_W; доли книг (Р11-1) — у каждой книги своя,
        # у пары средств физлиц — у текущих и срочных (веса c*, 1 − c* — прежние)
        key = c_ref_lt(w, "key")
        c = c_cstar(key)
        tot = 0.0
        for b, sp in books.items():
            r_w = c_ref_lt(w, sp["ref"])
            if sp["side"] == LOANS_SIDE:
                val = r_w + c_s_lt(b) + (sigma0 if sp.get("lt_shift") else 0.0)
                if sp.get("phi"):
                    val -= phi_a * (r_w - c_ref_lt(ref_w, sp["ref"]))
                if b in shr:
                    val -= c_share_cut(b, w, 0.0)
                tot += E0[b] / iea * val
                continue
            wgt = l_r * c if b == RETAIL_CURRENT else l_r * (1.0 - c) if b == RETAIL_TERM else E0[b] / iea
            tot -= wgt * (c_cost_lt(b, r_w, sigma0_l, w) + (phi_l * x_lt[w] if sp.get("phi") else 0.0))
        return tot - dia * l_r

    # Кредитная маржа стационара мира (М§4.5): доходность кредитного портфеля − CoR режима norm с
    # κ-добавкой мира − смесь балансирующих активов (бумаги и ликвидность в долях LA)
    credit = [b for b, s in books.items() if s.get("sector")]
    cor_norm = c_traj_at(c_bget(book, f"regimes.{R_NORM}.cor"), yl, ql)
    if c_bget(book, "regimes.cor_basis") == "mgmt":
        cor_norm = c_to_engine(A, "cor", cor_norm)
    kap = c_bnum(book, "credit.kappa")
    sec = c_bnum(book, "volumes.securities_share_of_liquid")
    margin = {}

    def c_bal_rate(b, w):
        # ставка балансирующего актива в стационаре мира: опора + s^LT (− доля сжатия книги, Р11-1)
        rate = c_ref_lt(w, books[b]["ref"]) + c_s_lt(b)
        if b in shr:
            rate -= c_share_cut(b, w, 0.0)
        return rate

    for w in ids:
        yld = (sum(E0[b] * (c_ref_lt(w, books[b]["ref"]) + lt_spread[b][w]) for b in credit)
               / sum(E0[b] for b in credit))
        risk = cor_norm + kap * c_kappa_spread(book, w, yl, ql)
        bal = sec * c_bal_rate(SECURITIES, w) + (1.0 - sec) * c_bal_rate(LIQUIDITY, w)
        margin[w] = yld - risk - bal
    order = sorted(ids, key=lambda w: key_lt[w])
    pairs = {}
    for w1, w2 in zip(order, order[1:]):
        dkk = key_lt[w2] - key_lt[w1]
        pairs[f"{w1}_{w2}"] = None if dkk == 0.0 else (nss0[w2] - nss0[w1]) / dkk
    # ROE-эквивалент: T × IEA_0/BV_0 × (1 − τ_eff года last_period) — п.п. ROE на 1 п.п. ключевой
    tau_l = c_traj_at(c_bget(book, "tax.statutory"), yl, ql) + c_bnum(book, "tax.effective_gap")
    scale = iea / A["BV"] * (1.0 - tau_l)
    keyed = {}
    if shr:
        # Р11-1 (печать только при ключе): доли книг, слагаемое доли в стационаре мира −share × (ref_W^LT − ref_H^LT),
        # ставки книг в стационаре миров (цель ставки К4 за концом сетки — та же форма) и наклон книги к своей опоре между
        # мирами M и N: 1 − φ_A [Φ_A] − share у актива, β + φ_L dX/dref [Φ_L] − share у пассива
        def c_book_rate_lt(b, w):
            sp = books[b]
            if sp["side"] == LOANS_SIDE:
                r_w = c_ref_lt(w, sp["ref"])
                val = r_w + c_s_lt(b) + (sigma0 if sp.get("lt_shift") else 0.0)
                if sp.get("phi"):
                    val -= phi_a * (r_w - c_ref_lt(ref_w, sp["ref"]))
                if b in shr:
                    val -= c_share_cut(b, w, 0.0)
                return val
            return (c_cost_lt(b, c_ref_lt(w, c_share_ref(b, sp)), sigma0_l, w)
                    + (phi_l * x_lt[w] if sp.get("phi") else 0.0))

        rates = {b: {w: c_book_rate_lt(b, w) for w in ids} for b in books}
        slopes = {}
        for b, sp in books.items():
            ref = c_share_ref(b, sp)
            d_ref = c_ref_lt(W_MKT, ref) - c_ref_lt(W_LOW, ref)
            slopes[b] = None if d_ref == 0.0 else (rates[b][W_MKT] - rates[b][W_LOW]) / d_ref
        keyed = {"phi_shares": dict(shr), "share_lt": {b: {w: -c_share_cut(b, w, 0.0) for w in ids} for b in shr},
                 "book_rates_lt": rates, "book_slopes": slopes}
    return {**keyed, "sigma0": sigma0, "sigma0_liab": sigma0_l, "split": split, "delta0": delta0,
            "w_assets": w_assets, "w_liab": w_liab, "lt_spread": lt_spread,
            "phi": phi, "phi_split": p_split, "phi_assets": phi_a, "phi_liab": phi_l, "phi_weights": omega,
            "phi_a_sum": a_sum, "phi_l_sum": l_sum, "x_lt": x_lt, "loan_margin": margin,
            "nss_books": {w: c_nss_books(w) for w in ids},
            "target_eng": target, "t_real": t_real, "t_local": t_loc,
            "level_world": level_w or ref_w, "nss_level": nss0[level_w or ref_w],
            "nss_ref": nss0[ref_w], "nss": nss0, "key_lt": key_lt, "iea0": iea,
            "d_phi": dphi, "t_real_phi0": t0, "pairs": pairs, "roe_equiv": t_star * scale,
            "roe_equiv_pairs": {k: None if v is None else v * scale for k, v in pairs.items()}}


# ============================================================================ контекст прогона

def _c_pos(x: dt.date, anchor: tuple[int, int]) -> float:
    """Положение даты на линейке кварталов сетки (М§0.2) — одна функция для даты оценки и даты
    кривой, по конвенции «конец дня»: внутри квартала q — (q − 1) + (x − S_q)/d_q, на конце
    квартала pos(E_q) = q (квартал закрыт, как у S_(q+1)). q — номер квартала сетки: первый
    прогнозный — 1, раньше сетки — q ≤ 0."""
    y0, qa = anchor
    y, q = x.year, (x.month - 1) // 3 + 1
    qi = (y - y0) * QY + (q - qa)
    if x == c_q_last_day(y, q):
        return float(qi)
    return (qi - 1) + (x - c_q_first_day(y, q)).days / c_q_len(y, q)


def _c_clock(B: dict, periods: list[dict], v: dt.date) -> dict:
    """Дата оценки на годовой линейке (М§0.2): период p0 с v и число прошедших в нём кварталов
    pos (целые — закрытые, дробь — доля дней квартала q0); e = pos/n; начала периодов в годах от v
    по линейке 0,25 года на квартал."""
    facts_date = _c_as_date(c_bget(B, "meta.facts_date"))
    if v < facts_date:
        raise ControlInputError("дата оценки раньше даты фактов")
    anchor = c_per_parse(c_bget(B, "meta.anchor_period"))
    pos_abs = 0.0 if v == facts_date else _c_pos(v, anchor)
    first, p0 = 0.0, None
    for i, p in enumerate(periods):
        if first <= pos_abs < first + p["n"]:
            p0, pos = i, pos_abs - first
            break
        first += p["n"]
    if p0 is None:
        raise ControlInputError("дата оценки вне сетки (v ≥ E_Q)")
    t_start, t = {}, -pos / QY
    for i in range(p0, len(periods)):
        t_start[i] = t
        t += periods[i]["n"] / QY
    return {"v": v, "p0": p0, "pos": pos, "e": pos / periods[p0]["n"], "pos_abs": pos_abs,
            "t_start": t_start, "tau_end": {i: t_start[i] + periods[i]["n"] / QY for i in t_start}}


def _c_kappa_gap(B: dict, w: str, y: int, q: int, lag: int) -> float:
    """Разность реальных ставок κ-добавки квартала q − L (М§4.6): относительно мира-опоры книги с любым
    знаком, без ключа опоры — max(0, rr_W − rr_N); история до сетки — ноль (она у миров общая)."""
    y0, qa = c_per_parse(c_bget(B, "meta.anchor_period"))
    idx = (y - y0) * QY + (q - qa) - lag                # номер квартала сетки q − L
    if idx < 1:
        return 0.0                                      # история до сетки: rr одинакова во всех мирах
    yy, qq = y0 + (qa + idx - 1) // QY, (qa + idx - 1) % QY + 1
    return c_kappa_spread(B, w, yy, qq)


def _c_world_period(B: dict, w: str, p: dict, lag: int) -> dict:
    """Ряды мира за период по кварталам и κ-разрыв с лагом."""
    y, qs = p["year"], p["quarters"]
    out = {}
    for f in ("key_rate", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y", "cpi", "wage_growth", "real_key"):
        out[f] = [c_world_quarter(B, w, f, y, q) for q in qs]
    out["kappa_gaps"] = [_c_kappa_gap(B, w, y, q, lag) for q in qs]
    return out


def c_control_context(book: dict, facts: dict, *, valuation_date=None, base_book: dict | None = None) -> dict:
    """Всё общее для 36 клеток: якорь, выведенные ключи, передача, миры, дисконт, A-P2u.

    base_book — книга до подмен (М§4.6): по ней берётся путь режима-опоры FVC, который не сдвигается
    вместе с осями и чувствительностями; без неё книга — сама себе база."""
    A = c_anchor_state(book, facts)
    B, derived = c_resolve_anchor_keys(book, A)
    B0 = B if base_book is None else c_resolve_anchor_keys(base_book, A)[0]
    if c_bget(B, "capital.recapitalization.enabled"):
        raise ControlUnsupported("докапитализация включена — модуль не реализован (М§0.6)")
    if c_bopt(B, "valuation.terminal.fade_mode") == FADE_SYMMETRIC:
        # симметричное угасание — правило справочного варианта таблиц книги, а не точки книги (М§7, §17)
        raise ControlUnsupported("симметричное угасание (valuation.terminal.fade_mode) — справочный вариант: "
                                 "контрольная модель считает точку книги с односторонним угасанием")
    periods = c_annual_periods(B)
    y0, qa = c_per_parse(c_bget(B, "meta.anchor_period"))
    quarterly = c_is_quarterly(B)
    growth = c_growth_rule(B)
    tr = c_transmission_ctl(B, A)
    books = B["nii"]["books"]
    s0_from = int(c_bnum(B, "nii.sigma0_from"))
    if not periods[0]["year"] <= s0_from <= periods[-1]["year"]:
        raise ControlInputError("nii.sigma0_from вне годов first_period…last_period (М прил. A)")
    shares = {int(h): float(v) for h, v in c_bget(B, "other.misc_quarter_shares").items()}
    if sorted(shares) != list(range(1, QY + 1)) or abs(sum(shares.values()) - 1.0) > 1e-9:
        raise ControlInputError("other.misc_quarter_shares: нужны доли кварталов 1…4 с суммой 1 (М§4.7)")
    v = _c_as_date(valuation_date or c_bget(B, "meta.valuation_date"))
    clock = _c_clock(B, periods, v)
    lag = int(c_bnum(B, "credit.real_rate_lag_q"))
    worlds = list(c_bget(B, "worlds.ids"))
    wv = {w: [_c_world_period(B, w, p, lag) for p in periods] for w in worlds}
    add = c_bnum(B, "valuation.beta_e") * c_bnum(B, "valuation.erp")
    ca = _c_as_date(c_bget(B, "meta.curve_as_of"))
    # перекат (М§0.2): Δ = 0,25 × (pos(v) − pos(curve_as_of)) по линейке кварталов
    shift = (0.25 * (clock["pos_abs"] - _c_pos(ca, (y0, qa)))
             if (c_bget(B, "valuation.roll_along_forwards") and ca < v) else 0.0)
    disc = {w: CDisc(c_bget(B, f"worlds.{w}.zero_curve"), add, shift) for w in worlds}
    dens = c_bget(B, "capital.rwa.density")
    oaf = A["OA_fixed"]
    dens_oaf = 0.0
    if oaf:
        if dens.get("other_assets_fixed") is None:
            raise ControlInputError("постоянные прочие активы без плотности capital.rwa.density.other_assets_fixed")
        dens_oaf = float(dens["other_assets_fixed"])
        if dens_oaf < 0.0:
            raise ControlInputError("capital.rwa.density.other_assets_fixed отрицательна (М§4.11)")
    mults = {}
    for rid in c_bget(B, "regimes.ids"):
        mult = c_bopt(B, f"regimes.{rid}.rwa_density_mult")
        if mult is not None:
            vals = [mult] if not isinstance(mult, dict) else [v for k, v in mult.items() if str(k) != "LT_from"]
            if any(float(v) <= 0.0 for v in vals):
                raise ControlInputError(f"regimes.{rid}.rwa_density_mult: значение ≤ 0 (М§4.11)")
            mults[rid] = mult
    links = tuple(float(c_bopt(B, key, 0.0)) for key in ("fees.volume_link", "other.insurance_volume_link",
                                                        "opex.volume_link"))
    if any(not 0.0 <= x <= 1.0 for x in links):
        raise ControlInputError("связь с объёмом вне [0; 1] (М§4.7)")
    link_base = c_bopt(B, "volumes.link_base", LINK_BASES[0])
    if any(links) and link_base not in LINK_BASES:
        raise ControlInputError(f"volumes.link_base: {link_base!r} (М§4.7)")
    loans_ids = [b for b, sp in books.items() if sp.get("sector")]
    geo = {"books": books, "dens": dens, "oaf": oaf, "dens_oaf": dens_oaf, "rwa_mult": mults}
    guar = c_guarantee_rule(B, A, books, dens, link_base)
    cash = c_cash_rule(B, A, books)
    if cash is not None:
        geo["cash"] = cash          # К8: RWA якоря — с вырезом плотности растущих прочих активов и C_0 (равен прежнему)
    if guar is None:
        rwa0 = _c_rwa_of(geo, None, y0, qa, A["E0"], A["OA"], 1.0, 1.0,
                         cash=None if cash is None else cash["c0"])
    else:
        geo["guar"] = guar          # К5: RWA якоря — с вырезом плотности и G_0 (равен прежнему)
        rwa0 = _c_rwa_of(geo, None, y0, qa, A["E0"], A["OA"], 1.0, 1.0, guar=guar["g0"],
                         cash=None if cash is None else cash["c0"])
    gov = sum(float(c["sign"]) * float(c["value"]) for c in c_bget(B, "valuation.governance.components"))
    fv_ref = c_bget(B, "credit.fv_loans_ref")
    if fv_ref not in c_bget(B, "regimes.ids"):
        raise ControlInputError("credit.fv_loans_ref — не режим из regimes.ids (М§4.6)")
    ctx = {"A": A, "B": B, "derived": derived, "periods": periods, "tr": tr, "sigma0_from": s0_from,
           "misc_shares": shares, "clock": clock, "wv": wv, "disc": disc, "rwa0": rwa0, "worlds": worlds,
           "gov": c_bnum(B, "valuation.governance.discount"), "gov_sum": gov, "fv_ref": fv_ref, "B0": B0,
           "shock_year": c_shock_year(B),
           "posterior": dict(c_bget(B, "joint.regime_prob")), "dev": {}, "mu": {}, "anchor": (y0, qa),
           "quarterly": quarterly, "growth": growth, "links": links, "link_base": link_base,
           "loans": loans_ids, "biz": c_client_funds(books), "glide_memo": {},
           # Р11-2: слово «средства клиентов» балансовой механики — без ведомых книг К6 при funds_scope: clients
           "k6_out": c_funds_scope(B), "fund_biz": c_fund_biz(B, books),
           "fv": {b: c_bnum(B, f"nii.books.{b}.fv_share") for b in c_fv_books(books)},
           "Q": c_qidx((y0, qa), *c_per_parse(c_bget(B, "meta.last_period"))), **geo}
    ctx["guar"] = guar
    ctx["cash"] = cash
    ctx["book_rel"] = c_book_cor_mult(B, A, ctx["fv"])
    ctx["opex_w"] = c_opex_weights(B, links[2])
    ctx["line_base"], ctx["line_shares"] = c_line_rules(B, links, link_base, A["E0"])
    ctx["share_nominal"] = c_share_nominal(B, links, ctx["line_shares"])     # Р8-6: франшиза за связью строки
    ctx["root_mult"] = c_root_mult(B)              # Р5-6: корень комиссий и страхования множителем
    ctx["line_form"] = c_line_link_form(B)         # Р10-5: франшиза и К6 формой строки (форма ключа — всегда)
    ctx["k2"] = any(ctx["line_base"].values()) or ctx["line_shares"] is not None
    ctx["wtf"], ctx["wtf_anchor"] = c_wholesale_shares(B)
    ctx["wtf_key"] = "wholesale_structural_to_funds" in (c_bopt(B, "volumes") or {})
    ctx["allow"] = c_allowance_rule(B, A, ctx["fv"])
    ctx["driven"] = c_driven_rule(B, links, link_base, A["E0"])
    ctx["k6_line"] = c_driven_line_rule(ctx)       # Р10-5: К6 формой строки (при активном К6 и ключе формы)
    ctx["funds_keys"] = c_funds_keys(B)            # Р10-6, Р10-1: область гейта стоимости средств и «средства клиентов»
    ctx["nci_real"] = c_nci_real(B)                # Р11-3: неконтролирующие в реальных рублях (None — доля pnl.nci_share)
    # концы кварталов статей для уровня базы строки в квартальном проходе: К5 (драйвер — база комиссий), К6, К8 (драйвер
    # денег)
    ctx["base_ends"] = ctx.get("guar") is not None or bool(ctx["driven"]) or cash is not None
    ctx["term_fixed"] = c_terminal_fixed_rule(B)
    ctx["min_dps"] = c_min_dps_rule(B, growth, quarterly, [p["year"] for p in periods])
    ctx["stationary"] = c_stationary_rule(B)
    # К-Т2: год терминала, ставка фондирования блока К-Т, год-якорь угасания — параметры оценки (путь клеток не читает)
    ctx["year_basis"], ctx["funding"], ctx["fade_anchor"] = c_year_basis(B), c_fixed_funding(B), c_fade_anchor(B)
    if quarterly:
        if c_bopt(B, "dividends.policy.steps"):
            raise ControlInputError("непустой dividends.policy.steps в квартальном режиме (М§5.7.1)")
        ctx["divcal"] = c_div_calendar(B, A)
    ctx["bb"] = c_buyback_rule(ctx)
    ctx["bridge_amount"] = c_bridge_register(ctx)
    ctx["pending_amount"] = c_pending_register(ctx)
    c_regime_update_ctl(ctx)
    return ctx


def c_shock_year(B: dict) -> int:
    """Год шока кризиса = год якоря + regimes.crisis.shock_year_offset (М§3.2). Кризисные ключи
    привязаны к нему: квартальный профиль CoR, период разового убытка и первый год
    loan_growth_override обязаны лежать в году шока — иначе громкий отказ."""
    off = c_bget(B, "regimes.crisis.shock_year_offset")
    if isinstance(off, bool) or not isinstance(off, int) or off < 1:
        raise ControlInputError("regimes.crisis.shock_year_offset — целое ≥ 1 (М прил. A)")
    shock = c_per_parse(c_bget(B, "meta.anchor_period"))[0] + off
    cor = c_bget(B, "regimes.crisis.cor")
    if isinstance(cor, dict):
        for k, (ky, q1, q2) in _c_time_keys({str(k): v for k, v in cor.items()}).items():
            if q1 == q2 and ky != shock:
                raise ControlInputError(f"regimes.crisis.cor: квартальный ключ {k} вне года шока {shock}")
    if c_per_parse(c_bget(B, "regimes.crisis.one_off_loss.period"))[0] != shock:
        raise ControlInputError(f"regimes.crisis.one_off_loss.period вне года шока {shock}")
    over = c_bget(B, "regimes.crisis.loan_growth_override") or {}
    if over and min(int(k) for k in over) != shock:
        raise ControlInputError(f"regimes.crisis.loan_growth_override: первый год — не год шока {shock}")
    return shock


# ============================================================================ помощники клетки

def _c_fact_q(A: dict, line: str, y: int, q: int):
    rec = A["pnl"].get(f"{y}Q{q}")
    return None if rec is None else rec.get(line)


def _c_need_fact_q(A: dict, line: str, y: int, q: int) -> float:
    v = _c_fact_q(A, line, y, q)
    if v is None:
        raise ControlInputError(f"нет факта pnl_quarterly {y}Q{q}.{line}")
    return float(v)


def _c_fact_line(A: dict, line: str, y: int, q: int) -> float:
    """Факт строки в знаке движка: расходы — положительным числом (в отчётности — со знаком минус)."""
    v = _c_need_fact_q(A, line, y, q)
    return abs(v) if line == "opex" else v


def _c_floor(B: dict, s: str, which: str, y: int, q: int) -> float:
    base = c_bnum(B, f"capital.minimum.{which}")
    return base + sum(c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.{k}"), y, q)
                      for k in ("conservation", "sifi", "ccyb"))


def _c_partial(rho: float, n: int) -> tuple[float, float]:
    """Годовая агрегация подстройки ρ за n кварталов: (доля к цели на конец, средняя доля)."""
    lag = 1.0 - rho
    return 1.0 - lag ** n, 1.0 - sum(lag ** j for j in range(1, n + 1)) / n


def _c_path_mean(points: list[float]) -> float:
    """Средний остаток периода по остаткам на концах кварталов: среднее квартальных трапеций."""
    return sum((a + b) / 2.0 for a, b in zip(points, points[1:])) / (len(points) - 1)


def _c_geo_path(start: float, end: float, n: int) -> list[float]:
    """Остатки на концах кварталов периода при одном квартальном множителе (М§4.3): статья растёт от
    начала к концу периода геометрически — замкнутая форма, без прохода по кварталам клетки."""
    if start <= 0.0 or end <= 0.0:
        return [start + (end - start) * j / n for j in range(n + 1)]
    g = (end / start) ** (1.0 / n)
    return [start * g ** j for j in range(n + 1)]


def _c_unaudited_quarters(cutoffs: list[int], y: int, h: int) -> list[tuple[int, int]]:
    """Кварталы неаудированной прибыли на конец квартала (y, h) (М§4.11)."""
    yy, hh = y, h
    out = []
    while True:
        out.append((yy, hh))
        yy, hh = (yy - 1, QY) if hh == 1 else (yy, hh - 1)
        if hh in cutoffs:
            return out
        if len(out) > QY * 2:
            return out


# ============================================================================ клетка: один период

def _c_period(ctx: dict, cell: dict, st: dict, i: int, div: float, plan: dict | None = None) -> tuple[dict, dict]:
    """Годовой шаг клетки (порядок М§4.2 в годовом приближении). Возвращает (состояние, строка).

    plan — квартальный план года ветви с квартальным проходом капитала (М§17): пути кредитных книг по
    концам кварталов (loans; None — потенциальный прирост целиком) и решения о дивиденде года с кварталами
    решения, вычета и выплаты (divs). Без плана — годовая ветвь образца: одно решение div в квартал собрания."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    w, r, s = cell["world"], cell["regime"], cell["scenario"]
    y, qs, n = p["year"], p["quarters"], p["n"]
    frac, dfac = n / QY, p["days"] / DAYS_BASE
    wd = ctx["wv"][w][i]
    ref_w = c_bget(B, "nii.transmission.reference_world")
    wh = ctx["wv"][ref_w][i]
    books = B["nii"]["books"]
    y0, qa = ctx["anchor"]
    loans = [b for b, sp in books.items() if sp.get("sector")]
    biz, fv, oaf = ctx["biz"], ctx["fv"], ctx["oaf"]
    E, Ynew, row = dict(st["E"]), dict(st["y"]), {}

    def c_fv_part(vals):
        return sum(fv[b] * vals[b] for b in fv)

    # --- объёмы (М§4.3)
    gy = int(c_bnum(B, "volumes.guidance_year"))
    over = c_bget(B, "regimes.crisis.loan_growth_override") if r == R_CRISIS else {}
    over = {int(k): float(v) for k, v in (over or {}).items()}
    drift_until = int(c_bnum(B, "volumes.share_drift_until"))
    m_q = {}                                            # потенциальный прирост книги за квартал (М§4.13.1)
    for b in loans:
        sp = books[b]
        if y == gy:
            seg = sp["cor_segment"]
            if p["stub"]:
                start_seg = sum(st["E"][x] for x in loans if books[x]["cor_segment"] == seg)
                prev = A["prev_corp"] if seg == "corporate" else A["prev_retail"]
                mult = prev * (1.0 + c_bnum(B, f"volumes.guidance_growth.{seg}")) / start_seg
            else:
                mult = 1.0 + c_bnum(B, f"volumes.guidance_growth.{seg}")
            E[b] = st["E"][b] * mult
            m_q[b] = mult ** (1.0 / n) - 1.0
            continue
        if y in over:
            g = over[y]
        else:
            G = c_overlay_growth(B, w, "credit_growth", sp["sector"], y)
            d = c_premium(B, "volumes.loan_share_drift", LOAN_SECTORS, sp["sector"], y) if y <= drift_until else 0.0
            g = (1.0 + G) * (1.0 + d) - 1.0 + c_traj_mean(c_bget(B, f"regimes.{r}.loan_growth_adj"), y, qs)
        E[b] = st["E"][b] * (1.0 + g) ** frac
        m_q[b] = (1.0 + g) ** (1.0 / QY) - 1.0
    paths = plan.get("loans") if plan is not None else None
    if paths is not None:
        for b in loans:
            E[b] = paths[b][-1]
    fd = c_premium(B, "volumes.funds_share_drift", FUND_SEGMENTS, "retail", y, qs) if y <= drift_until else 0.0
    fd_c = c_premium(B, "volumes.funds_share_drift", FUND_SEGMENTS, "corporate", y, qs) if y <= drift_until else 0.0
    fr0 = st["E"][RETAIL_CURRENT] + st["E"][RETAIL_TERM]
    g_r = (1.0 + c_overlay_growth(B, w, "funds_growth", "retail", y)) * (1.0 + fd) - 1.0
    g_c = (1.0 + c_overlay_growth(B, w, "funds_growth", "corporate", y)) * (1.0 + fd_c) - 1.0
    fr1 = fr0 * (1.0 + g_r) ** frac
    for b in biz:
        E[b] = st["E"][b] * (1.0 + g_c) ** frac
    cf0, cf1 = sum(st["E"][b] for b in biz), sum(E[b] for b in biz)
    rcs = "nii.retail_current_share"
    lo, hi = (float(x) for x in c_bget(B, f"{rcs}.bounds"))
    share_target = sum(min(hi, max(lo, c_bnum(B, f"{rcs}.c_ref") - c_bnum(B, f"{rcs}.psi")
                                 * (k - c_bnum(B, f"{rcs}.key_ref")))) for k in wd["key_rate"]) / n
    rho_c = c_bnum(B, f"{rcs}.rho")
    c1 = st["c"] + _c_partial(rho_c, n)[0] * (share_target - st["c"])
    E[RETAIL_CURRENT], E[RETAIL_TERM] = c1 * fr1, (1.0 - c1) * fr1
    drv = ctx.get("driven")
    k6_rec = [{} for _ in range(n)] if ctx.get("k6_line") else None      # Р10-5: записи К6 кварталов периода
    if drv:
        # книги-обязательства за драйвером строки (К6): уровень базы строки на концах кварталов периода — кредитные
        # книги по плану (или геометрически), средства физлиц и прочие средства бизнеса — их пути, «номинал» — индекс
        wage_p = wd["wage_growth"]
        lp = {b: (paths[b] if paths is not None else _c_geo_path(st["E"][b], E[b], n)) for b in loans}
        frp = _c_geo_path(fr0, fr1, n)
        cp_ = [st["c"] + (1.0 - (1.0 - rho_c) ** j) * (share_target - st["c"]) for j in range(n + 1)]
        bp = {b: _c_geo_path(st["E"][b], E[b], n) for b in biz if b not in drv}
        noms, nm = [st.get("nom", 1.0)], st.get("nom", 1.0)
        for x in wage_p:
            nm *= (1.0 + x) ** (1.0 / QY)
            noms.append(nm)
        ends = [{**{b: lp[b][j] for b in loans}, **{b: bp[b][j] for b in bp}, RETAIL_CURRENT: cp_[j] * frp[j],
                 RETAIL_TERM: (1.0 - cp_[j]) * frp[j]} for j in range(n + 1)]
        drv_paths = {}
        for b, d in drv.items():
            levels = [c_base_level(d["spec"], e, loans=loans, biz=[x for x in biz if x not in drv],
                                   assets=loans, nominal=noms[j]) for j, e in enumerate(ends)]
            if min(levels) <= 0.0:
                raise ControlInputError(f"уровень драйвера книги {b} ≤ 0: клетка " + "/".join((w, r, s)) + f", {y} (М§4.3)")
            if k6_rec is not None:
                # Р10-5: книга формой строки — E_0 × Ψ на концах кварталов периода, Ψ г/г к тому же кварталу прошлого года;
                # D и Ψ конца квартала — в запись пути клетки (их читает и квартальный проход капитала)
                psi = [c_driven_psi(ctx, st, b, d, y, q, levels[j + 1], wage_p[j]) for j, q in enumerate(qs)]
                drv_paths[b] = [st["E"][b]] + [A["E0"][b] * x for x in psi]
                for j in range(n):
                    k6_rec[j][(K6_END_KEY, b)], k6_rec[j][(K6_PSI_KEY, b)] = levels[j + 1], psi[j]
            else:
                drv_paths[b] = c_driven_path(d, st["E"][b], levels, wage_p, c_driven_roots(d, y, qs))
            E[b] = drv_paths[b][-1]
        cf1 = sum(E[b] for b in biz)
    sum_loans = sum(E[b] for b in loans)
    loans_ac = sum_loans - c_fv_part(E) if fv else sum_loans
    wtf = ctx["wtf"]                                    # база опта: структурная доля (К3) или доля якоря
    r_oa, r_ol = c_bnum(B, "volumes.other_assets_to_loans"), c_bnum(B, "volumes.other_liabilities_to_loans")
    r_al = c_bnum(B, "credit.allowance_ratio")
    k6_out = ctx.get("k6_out") or []
    if k6_out:
        # Р11-2: база структурного опта — s × средства клиентов без ведомых книг К6 (строка баланса «средства» — все книги)
        cl1 = fr1 + sum(E[b] for b in ctx["fund_biz"])
    else:
        cl1 = fr1 + cf1
    wh_base = wtf * cl1
    OA = r_oa * sum_loans
    if oaf:
        OA = OA + oaf                                   # постоянные прочие активы не растут (М§4.3)
    OL = r_ol * sum_loans
    allow = ctx.get("allow")
    AL = r_al * loans_ac if allow is None else c_allowance_of(allow, E, loans_ac)     # К7: резерв по книгам
    # Средние остатки периода (М§0.3): небалансирующие статьи растут внутри периода одним квартальным
    # множителем, поэтому средний остаток — замкнутая сумма квартальных трапеций геометрического пути
    # (не полусумма начала и конца: та завышает средний остаток растущей статьи). Доля текущих счетов —
    # замкнутая подстройка к средней цели периода.
    fr_path = _c_geo_path(fr0, fr1, n)
    c_path = [st["c"] + (1.0 - (1.0 - rho_c) ** j) * (share_target - st["c"]) for j in range(n + 1)]
    # пути по концам кварталов периода: кредитные книги — план квартального прохода или геометрический
    # путь; средства клиентов-бизнеса — геометрический
    lpath = {b: (paths[b] if paths is not None else _c_geo_path(st["E"][b], E[b], n)) for b in loans}
    bpath = {b: _c_geo_path(st["E"][b], E[b], n) for b in biz}
    if drv:
        bpath.update(drv_paths)                         # К6: ведомые книги — свой путь по кварталам
    avg_nb = {b: _c_path_mean(lpath[b]) for b in loans}
    for b in biz:
        avg_nb[b] = _c_path_mean(bpath[b])
    avg_nb[RETAIL_CURRENT] = _c_path_mean([c * f for c, f in zip(c_path, fr_path)])
    avg_nb[RETAIL_TERM] = _c_path_mean([(1.0 - c) * f for c, f in zip(c_path, fr_path)])
    fr_avg = _c_path_mean(fr_path)
    cf_avg = sum(avg_nb[b] for b in biz)
    funds_avg = fr_avg + cf_avg
    loans_avg = sum(avg_nb[b] for b in loans)
    loans_ac_avg = loans_avg - c_fv_part(avg_nb) if fv else loans_avg
    funds0 = fr0 + cf0
    if k6_out:
        # Р11-2: средства клиентов без книг К6 — начало периода и средняя (база опта К3 и её кривизна в среднем LA)
        cl0 = fr0 + sum(st["E"][b] for b in ctx["fund_biz"])
        cl_avg = fr_avg + sum(avg_nb[b] for b in ctx["fund_biz"])
        funds_curve = (funds_avg - (funds0 + fr1 + cf1) / 2.0) + wtf * (cl_avg - (cl0 + cl1) / 2.0)
    else:
        cl0, cl_avg = funds0, funds_avg
        funds_curve = (1.0 + wtf) * (funds_avg - (funds0 + fr1 + cf1) / 2.0)
    loans0 = sum(st["E"][b] for b in loans)
    ac_start = loans0 - c_fv_part(st["E"]) if fv else loans0
    cash = ctx.get("cash")
    cash_path = None
    if cash is not None:
        # К8: деньги за своим драйвером — уровень драйвера на концах кварталов периода (кредитные книги — план или
        # геометрический путь, средства клиентов — их пути, ведомые книги К6 — свои), C = c × D; прочие активы —
        # растущая часть без денег (ρ − C_0 / L_0) × кредиты, деньги и постоянные; средние — по тем же путям
        ends_nb = [{**{b: lpath[b][j] for b in loans}, **{b: bpath[b][j] for b in biz},
                    RETAIL_CURRENT: c_path[j] * fr_path[j], RETAIL_TERM: (1.0 - c_path[j]) * fr_path[j]}
                   for j in range(n + 1)]
        levels = [c_cash_level(cash, e) for e in ends_nb]
        if min(levels) <= 0.0:
            raise ControlInputError("уровень драйвера денег ≤ 0: клетка " + "/".join((w, r, s)) + f", {y} (М§4.3)")
        if cash.get("path") is None:
            cash_path = [cash["c"] * d for d in levels]
            OA = (r_oa - cash["cut"]) * sum_loans + cash_path[-1] + oaf
        else:
            # доля денег книги (Р6-1): доля c_k и вычет c_k D_0 / L_0 на концах кварталов периода (номер квартала сетки)
            k_ends = [c_qidx(ctx["anchor"], y, qs[0]) - 1 + j for j in range(n + 1)]
            cash_c = [c_cash_c(cash, k) for k in k_ends]
            cut_path = [c_cash_cut(cash, k) for k in k_ends]
            cash_path = [c * d for c, d in zip(cash_c, levels)]
            OA = (r_oa - cut_path[-1]) * sum_loans + cash_path[-1] + oaf
    # поправка среднего балансирующих активов на кривизну небалансирующих статей: LA = пассивы без
    # балансирующих + капитал − прочие активы, а полусумма начала и конца у растущих статей — не среднее
    if allow is None:
        curve_la = (funds_curve
                    + (r_ol - r_oa - 1.0) * (loans_avg - (loans0 + sum_loans) / 2.0)
                    + r_al * (loans_ac_avg - (ac_start + loans_ac) / 2.0))
    else:
        # резерв по книгам (К7) линеен по остаткам книг: средний резерв — по средним книгам периода
        al_avg = c_allowance_of(allow, avg_nb, loans_ac_avg)
        al_start = c_allowance_of(allow, st["E"], ac_start)
        curve_la = (funds_curve
                    + (r_ol - r_oa - 1.0) * (loans_avg - (loans0 + sum_loans) / 2.0)
                    + (al_avg - (al_start + AL) / 2.0))
    extra0 = max(0.0, st["E"][WHOLESALE] - wtf * cl0)               # добор опта на начало периода
    if extra0 <= WH_NOISE * max(1.0, st["E"][WHOLESALE]):
        # шум суммирования разности E_wh − s × cl0 (~6e-14 при доборе конца прошлого периода ровно 0) — не добор: иначе
        # ложно включается ветвь «минимум связан на обоих концах» (допуск — решение ведущего Д16)
        extra0 = 0.0
    la0 = st["E"][SECURITIES] + st["E"][LIQUIDITY]
    assets_nb_avg = ((1.0 + r_oa) * loans_avg - r_al * loans_ac_avg if allow is None
                     else (1.0 + r_oa) * loans_avg - al_avg)
    if oaf:
        assets_nb_avg = assets_nb_avg + oaf
    if cash_path is not None:
        # К8: деньги вместо доли C_0 / L_0 растущих прочих активов — в среднем небалансирующих активов и в кривизне LA
        cash_avg = _c_path_mean(cash_path)
        if cash.get("path") is None:
            assets_nb_avg = assets_nb_avg - cash["cut"] * loans_avg + cash_avg
            curve_la = (curve_la + cash["cut"] * (loans_avg - (loans0 + sum_loans) / 2.0)
                        - (cash_avg - (cash_path[0] + cash_path[-1]) / 2.0))
        else:
            # доля книги (Р6-1): вычет меняется внутри периода — среднее трапеций произведения «вычет × кредиты», не
            # вычет × средние кредиты; кривизна LA — тем же путём
            cut_l = [x * sum(lpath[b][j] for b in loans) for j, x in enumerate(cut_path)]
            cut_avg = _c_path_mean(cut_l)
            assets_nb_avg = assets_nb_avg - cut_avg + cash_avg
            curve_la = (curve_la + (cut_avg - (cut_l[0] + cut_l[-1]) / 2.0)
                        - (cash_avg - (cash_path[0] + cash_path[-1]) / 2.0))
    cf_path = [sum(bpath[b][j] for b in biz) for j in range(n + 1)]
    loans_path = [sum(lpath[b][j] for b in loans) for j in range(n + 1)]
    # концы кварталов кредитов по амортизированной стоимости — знаменатель годовой CoR (М§0.3)
    ac_path = [sum(lpath[b][j] * ((1.0 - fv[b]) if b in fv else 1.0) for b in loans) for j in range(n + 1)]

    # --- ставки книг (М§4.4): средняя за период и на конец. Сжатие φ — двумя скалярами пути: φ_A снимает
    # спред кредитных книг Φ_A, φ_L × X_W,q удорожает пассивы Φ_L; X_W,q — разность опорных ставок книг
    # Φ_A мира и мира H с долями ω_b якоря (от текущего остатка кредитов добавка не зависит)
    phi_a, phi_l, omega = ctx["tr"]["phi_assets"], ctx["tr"]["phi_liab"], ctx["tr"]["phi_weights"]
    x_w = [sum(om * (wd[c_ref_field(books[b]["ref"])][j] - wh[c_ref_field(books[b]["ref"])][j])
               for b, om in omega.items()) for j in range(n)]
    # Р11-1: доля сжатия книги — share_b × (ref_W,q − ref_H,q) из цели ставки на обеих сторонах баланса, до ветви стороны
    # (цель К4 — та же: tbar — средняя цель периода)
    shr = ctx["tr"].get("phi_shares") or {}
    ybar, y_q, tbar = {}, {}, {}
    for b, sp in books.items():
        ref = c_ref_field(sp["ref"])
        tgt = []
        for j, q in enumerate(qs):
            rv = wd[ref][j]
            sv = c_spread_at(ctx, b, y, q)
            if b in shr:
                sv -= c_share_term(shr[b], rv, wh[ref][j])
            if sp["side"] == LOANS_SIDE:
                if sp.get("phi"):
                    sv -= phi_a * (rv - wh[ref][j])
                tgt.append(rv + sv)
            else:
                tgt.append(float(sp["beta"]) * rv + sv + (phi_l * x_w[j] if sp.get("phi") else 0.0))
        T = sum(tgt) / n
        tbar[b] = T                                     # цель книги периода (ставка при ρ = 1) — К4
        k_end, k_avg = _c_partial(float(sp["rho"]), n)
        Ynew[b] = st["y"][b] + k_end * (T - st["y"][b])
        ybar[b] = st["y"][b] + k_avg * (T - st["y"][b])
        # ставка квартала j периода — та же замкнутая подстройка к средней цели (среднее по j = ybar)
        y_q[b] = [st["y"][b] + (1.0 - (1.0 - float(sp["rho"])) ** (j + 1)) * (T - st["y"][b]) for j in range(n)]

    # --- строки, не зависящие от балансирующих статей
    days_q = [c_q_len(y, q) for q in qs]
    kap = c_bnum(B, "credit.kappa")
    dev = ctx["dev"].get(r, {})
    # CoR клетки по кварталам (М§4.6): путь режима через мост + κ-добавка мира + отклонение A-P2u;
    # за период — среднее по дням (резервы начисляются по дням, М§0.3)
    cor_prof = [c_cor_path_engine(ctx, r, y, q) + kap * wd["kappa_gaps"][j] + _c_dev_at(dev.get("cor"), y, q)
                for j, q in enumerate(qs)]
    cor_c = sum(c * d for c, d in zip(cor_prof, days_q)) / p["days"]
    d_nim = sum(_c_dev_at(dev.get("nim"), y, q) for q in qs) / n
    near = c_traj_mean(c_bget(B, "regimes.near_nim_shift"), y, qs)        # ближний сдвиг ЧПМ (М§3.2)
    seg_rel = {"corporate": 1.0, "retail": 1.0}
    if c_bget(B, "credit.segment_relative.enabled"):
        ac0 = {sg: sum(A["E0"][b] * ((1.0 - fv[b]) if b in fv else 1.0) for b in loans
                       if books[b]["cor_segment"] == sg) for sg in seg_rel}
        tot = sum(ac0.values())
        norm = sum(ac0[sg] / tot * c_bnum(B, f"credit.segment_relative.{sg}") for sg in seg_rel)
        seg_rel = {sg: c_bnum(B, f"credit.segment_relative.{sg}") / norm for sg in seg_rel}
    seg_cor = {sg: cor_c * seg_rel[sg] for sg in seg_rel}
    book_rel = ctx.get("book_rel")
    llp = 0.0
    if book_rel is None:
        for b in loans:
            share = (1.0 - fv[b]) if b in fv else 1.0
            llp += seg_cor[books[b]["cor_segment"]] * share * avg_nb[b] * dfac
    else:
        # множители CoR по книгам (ключ credit.book_relative): CoR книги — r̂_b × CoR клетки периода (κ-добавка и
        # отклонение A-P2u — внутри CoR клетки, множитель — на всю сумму); резервы на составе якоря — та же сумма
        # при r̂ ≡ 1 (CoR на составе якоря, ряд cor_mix0)
        llp_mix0 = 0.0
        for b in loans:
            share = (1.0 - fv[b]) if b in fv else 1.0
            llp += cor_c * book_rel[b] * share * avg_nb[b] * dfac
            llp_mix0 += cor_c * share * avg_nb[b] * dfac
        row.update(cor_mix0=cor_c, llp_mix0=llp_mix0, cor_book={b: cor_c * book_rel[b] for b in loans})
    # Кредитная переоценка кредитов по СС сверх опоры (М§4.6): FVC_q = f × (CoR_corporate,q − CoR_ref,q)
    # × Ē^СС_q × d_q/365. CoR_ref — путь режима-опоры книги до розыгрыша (книга-опора контекста) через
    # мост с той же сегментной поправкой, без κ-добавки и отклонения A-P2u (они — в CoR клетки и потому
    # действуют и на кредиты по СС); сдвиг путей CoR всех режимов опору не двигает.
    # Отклонение от опоры меняет величину и знак внутри года (профиль кризиса, затухание δ), поэтому
    # строка считается по кварталам: кредиты по СС растут внутри периода одним квартальным множителем.
    ref_prof = [c_cor_ref_engine(ctx, y, q) for q in qs]
    f_fv = c_bnum(B, "credit.fv_loans_factor")
    fv_avg_q, fvc_q = [0.0] * n, [0.0] * n              # у книги без fv_share строка FVC — ноль (М§4.6)
    for b, fvs in fv.items():
        ss0, ss1 = fvs * st["E"][b], fvs * E[b]
        ss_g = (ss1 / ss0) ** (1.0 / n) if ss0 > 0.0 and ss1 > 0.0 else 1.0
        rel_b = seg_rel[books[b]["cor_segment"]] if book_rel is None else book_rel[b]
        for j in range(n):
            avg_j = ss0 * ss_g ** j * (1.0 + ss_g) / 2.0                     # средние кредиты по СС квартала
            fv_avg_q[j] = fv_avg_q[j] + avg_j
            fvc_q[j] = fvc_q[j] + (f_fv * rel_b * (cor_prof[j] - ref_prof[j])
                                   * avg_j * days_q[j] / DAYS_BASE)
    fvc = sum(fvc_q)
    # ЧКД, расходы, страхование — г/г к тому же кварталу (М§0.3, §4.7): база — факт или квартал
    # прошлого года клетки; кварталы года хранятся в состоянии (сезонность переносится из истории)
    wage = wd["wage_growth"]
    # индекс «номинала» на концах кварталов периода (К2: база nominal, D^N_q = D^N_(q−1) (1 + wage)^(1/4), на якоре 1)
    nom_q, nom = [], st.get("nom", 1.0)
    for x in wage:
        nom *= (1.0 + x) ** (1.0 / QY)
        nom_q.append(nom)
    ov = {int(k): float(v) for k, v in (c_bget(B, "fees.growth_override") or {}).items()}
    fees_b = _c_yoy_quarters(ctx, st, "fees_net", y, qs)
    opex_b = _c_yoy_quarters(ctx, st, "opex", y, qs)
    ins_b = _c_yoy_quarters(ctx, st, "insurance_net", y, qs)
    link_f, link_i, link_c = ctx["links"]
    link_on = bool(link_f or link_i or link_c)
    rg = c_bget(B, "opex.real_growth")
    igw = c_bget(B, "other.insurance_growth_vs_wages")
    root_mult = ctx["root_mult"]

    def c_volume_lines(v, v_opex=None, v_line=None):
        """Комиссии, расходы и страхование кварталов периода (М§4.7). v — рост объёма периода (годовая
        форма связи с объёмом); None — связи нулевые, формулы образца. v_opex — рост базы расходов, взвешенной по
        себестоимости книг (ключ opex.volume_weights) или смеси расходов (opex.line_shares); None — та же база, что у
        комиссий и страхования. v_line — рост своих баз комиссий и страхования (К2: {строка: рост}; рост «номинала» —
        по кварталам, список). Корень строки (fees.growth_vs_wages, other.insurance_growth_vs_wages) — слагаемым роста,
        при ключе volumes.line_root_form: multiplicative — множителем (1 + корень) к росту базы (Р5-6, как у расходов);
        год переопределения комиссий корня не несёт ни в одной форме."""
        vo = v if v_opex is None else v_opex
        vf = v if v_line is None or v_line.get("fees") is None else v_line["fees"]
        vi = v if v_line is None or v_line.get("ins") is None else v_line["ins"]
        if y in ov and y == y0 and p["stub"]:
            # рост за год в году якоря: оставшиеся кварталы достраивают год до цели одним темпом
            full_prev = sum(_c_fact_line(A, "fees_net", y - 1, q) for q in range(1, QY + 1))
            done = sum(_c_fact_line(A, "fees_net", y, q) for q in range(1, qa + 1))
            g_rest = (full_prev * (1.0 + ov[y]) - done) / sum(fees_b) - 1.0
            f_q = [x * (1.0 + g_rest) for x in fees_b]
        elif y in ov:
            f_q = [x * (1.0 + ov[y]) for x in fees_b]
        elif root_mult:
            gvw = c_bget(B, "fees.growth_vs_wages")
            f_q = [fees_b[j] * c_base_factor(wage[j], link_f, None if vf is None else c_at(vf, j))
                   * (1.0 + c_traj_at(gvw, y, q)) for j, q in enumerate(qs)]
        elif vf is None or not link_f:
            gvw = c_bget(B, "fees.growth_vs_wages")
            f_q = [fees_b[j] * (1.0 + wage[j] + c_traj_at(gvw, y, q)) for j, q in enumerate(qs)]
        else:
            gvw = c_bget(B, "fees.growth_vs_wages")
            f_q = [fees_b[j] * (1.0 + wage[j] + c_traj_at(gvw, y, q) + link_f * (c_at(vf, j) - wage[j]))
                   for j, q in enumerate(qs)]
        if vo is None or not link_c:
            o_q = [x * (1.0 + wage[j]) * (1.0 + c_traj_at(rg, y, qs[j])) for j, x in enumerate(opex_b)]
        else:
            o_q = [x * (1.0 + wage[j] + link_c * (vo - wage[j])) * (1.0 + c_traj_at(rg, y, qs[j]))
                   for j, x in enumerate(opex_b)]
        if root_mult:
            i_q = [x * c_base_factor(wage[j], link_i, None if vi is None else c_at(vi, j))
                   * (1.0 + c_traj_at(igw, y, qs[j])) for j, x in enumerate(ins_b)]
        elif vi is None or not link_i:
            i_q = [x * (1.0 + wage[j] + c_traj_at(igw, y, qs[j])) for j, x in enumerate(ins_b)]
        else:
            i_q = [x * (1.0 + wage[j] + c_traj_at(igw, y, qs[j]) + link_i * (c_at(vi, j) - wage[j]))
                   for j, x in enumerate(ins_b)]
        return f_q, o_q, i_q

    def c_line_volumes():
        """Строки периода при ключах К2 (база связи по строке, доли расходов на драйверах строк) в годовой форме:
        рост своей базы строки — сумма средних кварталов периода к тем же кварталам прошлого года (loans, funds, iea —
        та же функция, что у volumes.link_base; веса — средние ЧПД балансирующих книг этой итерации; «номинал» — рост
        зарплат мира каждого квартала); смесь расходов A^C = (1 − s_F − s_I) B^C + s_F B^C_0 A^F / A^F_0 + s_I B^C_0
        A^I / A^I_0 по кварталам (средние периода на каждый квартал, у «номинала» — индекс квартала), её рост — так же;
        при ключе opex.line_share_roots у строки A^ℓ / A^ℓ_0 в смеси заменяет Φ^ℓ = λ A^ℓ / A^ℓ_0 + (1 − λ) H^ℓ (Р8-6), H^ℓ
        квартала — в записи базы. Возвращает строки кварталов и запись базы (средние кварталов для «к тому же кварталу» и
        печать)."""
        own, shares = ctx["line_base"], ctx["line_shares"]
        anchor = ctx["anchor"]
        label = "/".join((w, r, s))
        v_link = [None]

        def c_link_v():
            if v_link[0] is None:
                v_link[0] = v_now if v_now is not None else c_volume_growth(ctx, st, link_base, y, qs, iea * n)
            return v_link[0]

        def c_now(spec):
            """Средние базы по кварталам периода (годовая форма)."""
            kind = spec["kind"]
            if kind == LINK_BASES[0]:
                return [(a + b) / 2.0 for a, b in zip(loans_path, loans_path[1:])]
            if kind == LINK_BASES[1]:
                return [(a + b) / 2.0 for a, b in zip(funds_path, funds_path[1:])]
            if kind == LINK_BASES[2]:
                return [iea] * n
            if kind == BASE_NOMINAL:
                return [c_prev_q(spec, NOMINAL_KEY, q) * (1.0 + wage[j]) for j, q in enumerate(qs)]
            return [sum(w * avg[b] for b, w in spec["w"].items() if w)] * n

        def c_prev_q(spec, key, q):
            """Средняя базы того же квартала прошлого года: путь клетки (запись базы) или факты до якоря."""
            if (y - 1, q) > anchor:
                return st["vend"][(y - 1, q)][key]
            return c_base_hist_avg(ctx, spec, y - 1, q)

        def c_growth(spec, key, now):
            kind = spec["kind"]
            if kind == LINK_BASES[0] or kind == LINK_BASES[1]:
                return c_volume_growth(ctx, st, kind, y, qs, sum(now))
            if kind == LINK_BASES[2]:
                return c_volume_growth(ctx, st, kind, y, qs, iea * n)
            if kind == BASE_NOMINAL:
                return list(wage)                       # A^N_q / A^N_(q−4) − 1 = рост зарплат квартала (точно)
            prev = sum(c_prev_q(spec, key, q) for q in qs)
            if prev <= 0.0:
                raise ControlInputError(f"база строки прошлого года не положительна: клетка {label}, {y} (М§4.7)")
            return now[0] * n / prev - 1.0

        spec_of = {line: own[line] or {"kind": link_base} for line in ("fees", "ins")}
        store = [{} for _ in range(n)]
        v_line, prints = {}, {}
        for line in ("fees", "ins"):
            if own[line] is None:
                continue
            key = (LINE_KEY, line)
            now = c_now(own[line])
            if min(now) <= 0.0:
                raise ControlInputError(f"средняя базы строки {line} ≤ 0: клетка {label}, {y} (М§4.7)")
            v_line[line] = c_growth(own[line], key, now)
            prev = [c_prev_q(own[line], key, q) for q in qs]
            prints[line] = {"v": sum(now) / sum(prev) - 1.0, "vol": sum(now) / n}
            for j in range(n):
                store[j][key] = now[j]
        if any(sp["kind"] == BASE_NOMINAL for sp in spec_of.values()):
            nom_now = c_now({"kind": BASE_NOMINAL})
            for j in range(n):
                store[j][NOMINAL_KEY] = nom_now[j]
        v_base = None
        if any(own[line] is None for line in ("fees", "ins")) or (opex_w is None and shares is None):
            v_base = c_link_v()
        if opex_w is not None:
            w_now = sum(opex_w[b] * avg[b] for b in opex_w)
            v_op = c_volume_growth_weighted(ctx, st, y, qs, w_now * n)
            opex_spec, opex_now = {"kind": BASE_WEIGHTS, "w": opex_w}, [w_now] * n
            for j in range(n):
                store[j][OPEX_BASE] = w_now
        else:
            opex_spec = {"kind": link_base}
            opex_now = c_now(opex_spec)
            v_op = c_link_v()
        if shares is not None:
            # смесь расходов (франшиза): доли базы расходов якоря на драйверах строк; на якоре ступени нет
            b0 = c_base_hist_avg(ctx, opex_spec, *anchor)
            a0 = {line: c_base_hist_avg(ctx, spec_of[line], *anchor) for line in ("fees", "ins")}
            cur = {line: c_now(spec_of[line]) for line in ("fees", "ins")}
            nom_rule, fr_nom, nom_print = ctx.get("share_nominal"), [None] * n, None
            fr_phi, phi_print = [None] * n, None
            if nom_rule and ctx["line_form"]:
                # франшиза формой строки (Р10-5): Φ^ℓ — г/г к тому же кварталу прошлого года, Φ_(q−4) × c_link_growth(
                # A_q / A_(q−4), рост зарплат мира, λ, κ_q); A — средние базы строки кварталов периода (прошлый год — запись
                # пути клетки, до якоря — факты; там же Φ = A / A_0); H не считается
                phi_print = {}
                for line, (lam, traj) in nom_rule.items():
                    kp, ka = (FRANCHISE_PHI_KEY, line), (FRANCHISE_BASE_KEY, line)
                    seq = []
                    for j, q in enumerate(qs):
                        if (y - 1, q) > anchor:
                            back_phi, back_a = st["vend"][(y - 1, q)][kp], st["vend"][(y - 1, q)][ka]
                        else:
                            back_a = c_base_hist_avg(ctx, spec_of[line], y - 1, q)
                            back_phi = back_a / a0[line]
                        seq.append(back_phi * c_link_growth(cur[line][j] / back_a, wage[j], lam, c_traj_at(traj, y, q),
                                                            root_mult))
                    for j in range(n):
                        store[j][kp], store[j][ka] = seq[j], cur[line][j]
                    phi_print[line] = seq
                fr_phi = [{line: phi_print[line][j] for line in nom_rule} for j in range(n)]
            elif nom_rule:
                # франшиза за связью строки (Р8-6): номинальная часть H^ℓ — г/г к тому же кварталу прошлого года
                # (путь клетки — запись квартала; до якоря — A^ℓ / A^ℓ_0 фактов) × (1 + рост зарплат мира) (1 + κ)
                nom_print = {}
                for line, (lam, traj) in nom_rule.items():
                    key = (FRANCHISE_NOM_KEY, line)
                    seq = []
                    for j, q in enumerate(qs):
                        if (y - 1, q) > anchor:
                            back = st["vend"][(y - 1, q)][key]
                        else:
                            back = c_base_hist_avg(ctx, spec_of[line], y - 1, q) / a0[line]
                        seq.append(c_franchise_h(back, wage[j], c_traj_at(traj, y, q)))
                    for j in range(n):
                        store[j][key] = seq[j]
                    nom_print[line] = seq
                fr_nom = [{line: (nom_rule[line][0], nom_print[line][j]) for line in nom_rule} for j in range(n)]
            mix = [c_opex_mix(shares, opex_now[j], b0, {ln: cur[ln][j] for ln in cur}, a0, fr_nom[j], fr_phi[j])
                   for j in range(n)]
            prev = 0.0
            for q in qs:
                if (y - 1, q) > anchor:
                    prev += st["vend"][(y - 1, q)][MIX_KEY]
                else:
                    prev += c_opex_mix(shares, c_base_hist_avg(ctx, opex_spec, y - 1, q), b0,
                                       {ln: c_base_hist_avg(ctx, spec_of[ln], y - 1, q) for ln in cur}, a0)
            if prev <= 0.0 or min(mix) <= 0.0:
                raise ControlInputError(f"смесь базы расходов не положительна: клетка {label}, {y} (М§4.7)")
            v_op = sum(mix) / prev - 1.0
            prints["opex"] = {"v": v_op, "vol": sum(mix) / n}
            if nom_print is not None:
                prints["opex"]["nominal"] = nom_print       # H^ℓ кварталов периода — печать только при ключе (Р8-6)
            if phi_print is not None:
                prints["opex"]["phi"] = phi_print           # Φ^ℓ формы строки кварталов периода — только при ключе (Р10-5)
            for j in range(n):
                store[j][MIX_KEY] = mix[j]
        elif opex_w is not None:
            prints["opex"] = {"v": v_op, "vol": opex_now[0]}
        f_q, o_q, i_q = c_volume_lines(v_base, v_op, v_line)
        return f_q, o_q, i_q, store, prints

    # рост объёма периода v (М§4.7) — годовая форма: сумма средних остатков базы кварталов периода к
    # сумме тех же кварталов прошлого года; база iea считается в цикле баланса (зависит от LA)
    link_base = ctx["link_base"]
    if k6_out:
        # Р11-2: база строки funds (средние и концы кварталов) — слово «средства клиентов» без книг К6
        funds_path = [fr_path[j] + sum(bpath[b][j] for b in ctx["fund_biz"]) for j in range(n + 1)]
    else:
        funds_path = [a + b for a, b in zip(fr_path, cf_path)]
    v_now = None
    if link_on and link_base != LINK_BASES[-1]:
        ends = loans_path if link_base == LINK_BASES[0] else funds_path
        v_now = c_volume_growth(ctx, st, link_base, y, qs, sum((a + b) / 2.0 for a, b in zip(ends, ends[1:])))
    fees_q, opex_q, ins_q = c_volume_lines(v_now)
    fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
    opex_w = ctx.get("opex_w")
    w_avg = v_opex = None
    idx, I = [], st["I"]
    for j in range(n):
        I *= (1.0 + wd["cpi"][j]) ** (1.0 / QY)
        idx.append(I)
    # Годовые суммы книги (М§0.3, §4.7): квартал = год × доля квартала × индекс цен мира; у «прочего» —
    # доли other.misc_quarter_shares, у непрофильного — 1/4. В году якоря правила разные:
    # непрофильный результат закрывает год остатком (книга − факт отчётных кварталов, поровну на
    # оставшиеся кварталы); «прочее» остатком не закрывается — уровень книги × доля квартала, как в
    # любом году, сумма года — выход модели
    m_sh = ctx["misc_shares"]
    even = {h: 1.0 / QY for h in range(1, QY + 1)}
    nc_q = _c_book_quarters(ctx, p, idx, "noncore.result_real", even, residual_of="noncore_net")
    ms_q = _c_book_quarters(ctx, p, idx, "other.misc_net_real", m_sh)
    noncore, misc = sum(nc_q), sum(ms_q)
    one = 0.0
    if r == R_CRISIS:
        ol = c_bget(B, "regimes.crisis.one_off_loss")
        oy, oq = c_per_parse(ol["period"])
        if oy == y and oq in qs:
            one = float(ol["amount"])
    tau_stat = [c_traj_at(c_bget(B, "tax.statutory"), y, q) for q in qs]
    tau_eff = sum(tau_stat) / n + c_bnum(B, "tax.effective_gap")
    ot = 0.0
    if int(c_bnum(B, "tax.one_off.year")) == y and 1 in qs:
        ot = c_bnum(B, "tax.one_off.prob") * c_bnum(B, "tax.one_off.amount")
    if ctx.get("nci_real") is None:
        nci, nci_q = c_bnum(B, "pnl.nci_share"), None
    else:
        # Р11-3: неконтролирующие в реальных рублях — NCI_q = nci_real(Y) / 4 × I_W,q (как «прочее» с равными долями
        # кварталов); доля pnl.nci_share при ключе не читается (ключ неактивного режима)
        nci, nci_q = 0.0, _c_book_quarters(ctx, p, idx, "pnl.nci_real", even)
    tenor = c_bget(B, "oci.fvoci_tenor")
    y_end = wd[tenor][-1]
    y_prev = st["y_tenor"]
    M, D = c_bnum(B, "oci.fvoci_maturity"), c_bnum(B, "oci.fvoci_duration")
    pull = 1.0 - 0.25 / M
    # переоценка FVOCI по кварталам смены полугодия мира, с подтягиванием к номиналу до конца периода
    path_y = [y_prev] + list(wd[tenor])
    reval = sum((path_y[j + 1] - path_y[j]) * pull ** (n - 1 - j) for j in range(n))
    fvos = c_bnum(B, "oci.fvoci_share")
    cpn = A["cpn_annual"] if A["cpn_quarter"] in qs else 0.0
    cpn_tau = c_traj_at(c_bget(B, "tax.statutory"), y, A["cpn_quarter"]) if cpn else 0.0
    om = sum(c_traj_at(c_bget(B, "equity.other_movements"), y, q) for q in qs)
    nim_shift = c_traj_mean(c_bget(B, f"regimes.{r}.nim_shift"), y, qs)
    fvr_on = bool(c_bget(B, "other.fvtpl_bond_reval"))
    hq = qs[-1]
    paid_shift, dp_end, dpreg, left = 0.0, 0.0, 0.0, []
    if plan is None:
        agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
        pay_q = int(c_bnum(B, "dividends.calendar.payment_quarter"))
        reg_q = int(c_bnum(B, "dividends.calendar.reg_deduction_quarter"))
        declared_here = agm in qs       # и в неполном году якоря: решение — в своём квартале (М§17)
        # Дивиденды к выплате (М§5.4): каждая объявленная сумма несёт свои кварталы выплаты и вычета из
        # регуляторного капитала — по датам записи реестра (declared | paid), без записи или без даты в
        # ней — по календарю книги. Просроченная выплата (квартал записи раньше периода) уходит в первом
        # квартале.
        items = [dict(it) for it in st["pay"]]
        if declared_here and div:
            items.append({"amt": div, **_c_dividend_dates(ctx, y - 1)})
        div_list = [(qs.index(agm), div)] if (declared_here and div) else []
    else:
        # квартальный режим (М§5.7): очереди выплат и вычетов — номерами кварталов сетки; постоянная часть
        # остатка «дивиденды к выплате» якоря не выплачивается и в регуляторный капитал не возвращается
        items = []
        k_first = c_qidx(ctx["anchor"], y, qs[0])
        k_last = k_first + n - 1
        dp_end = st["dp_perm"]
        by_quarter = [0.0] * n
        for it in plan["divs"]:
            by_quarter[it["dec"] - k_first] += it["amt"]
        div = sum(by_quarter)
        div_list = [(j, amt) for j, amt in enumerate(by_quarter) if amt]
        for it in [dict(x) for x in st["dq"]] + [dict(x) for x in plan["divs"]]:
            if it["pay"] <= k_last:
                j_pay = max(it["pay"], k_first) - k_first
                paid_shift += ((n - (j_pay + 1) + 0.5) / n - 0.5) * it["amt"]
            else:
                dp_end += it["amt"]
            if it["reg"] > k_last:
                dpreg += it["amt"]
            if it["pay"] > k_last or it["reg"] > k_last:
                left.append(it)
    # Время капитальных потоков в среднем остатке балансирующих статей (М§4.2 шаг 5, §4.10):
    # предварительный баланс квартала — при BV_(q−1) − Div_q и DP_q, поэтому доход квартала j входит в
    # активы со следующего квартала — вес (n − j)/n (доход внутри года неравномерен: сезонность
    # расходов и комиссий, профиль CoR, — поэтому вес берётся по квартальному профилю дохода, а не
    # (n − 1)/(2n) равномерного); объявление дивиденда ликвидность не меняет, а выплата уменьшает её
    # уже на конец своего квартала — вес (n − j_выплаты + ½)/n. Оба — вместо ½ у полусуммы начала и конца.
    w_ci = [(n - (j + 1)) / n - 0.5 for j in range(n)]
    bb_q = None
    if ctx.get("bb") is not None:
        # выкуп акций (ключ dividends.buyback): деньги уходят из группы в квартале покупки — как выплата дивиденда,
        # BV и капитал норматива меньше рубль в рубль, в CI выкупа нет
        k_first = c_qidx(ctx["anchor"], y, qs[0])
        bb_q = [c_bb_amount(ctx, cell, k_first + j) for j in range(n)]
        paid_shift += sum(((n - (j + 1) + 0.5) / n - 0.5) * x for j, x in enumerate(bb_q))
    for it in items:
        when = it["pay"]
        if when is None:
            q_pay = pay_q if pay_q in qs else None
        elif when < (y, qs[0]):
            q_pay = qs[0]
        else:
            q_pay = when[1] if (when[0] == y and when[1] in qs) else None
        if q_pay is None:
            left.append(it)
            dp_end += it["amt"]
        else:
            paid_shift += ((n - (qs.index(q_pay) + 1) + 0.5) / n - 0.5) * it["amt"]
        # DPreg: + Div на конец квартала ГОСА, 0 с конца квартала отсечки (М§4.11, §5.4)
        reg = it["reg"] if it["reg"] is not None else (it["agm_year"], reg_q)
        if (it["agm_year"], agm) <= (y, hq) < reg:
            dpreg += it["amt"]
    at1, ncib = A["AT1"], A["NCI"]
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    ssl = c_bnum(B, "volumes.securities_share_of_liquid")
    dia = c_bnum(B, "nii.dia_rate")

    def c_grow_w(base, start, end):
        g = end / start if start > 0.0 and end > 0.0 else 1.0
        w = [b_ * g ** ((j + 0.5) / n) for j, b_ in enumerate(base)]
        tot = sum(w)
        return [x / tot for x in w] if tot else [d / p["days"] for d in days_q]

    if paths is None:
        w_cr = c_grow_w([c * d for c, d in zip(cor_prof, days_q)], sum(st["E"][b] for b in loans), sum_loans)
    else:
        # путь кредитов задан планом: вес квартала — CoR × дни × средний остаток кредитов квартала
        w_cr = [c * d * (a + b) / 2.0 for c, d, a, b in zip(cor_prof, days_q, loans_path, loans_path[1:])]
        tot_cr = sum(w_cr)
        w_cr = [x / tot_cr for x in w_cr] if tot_cr else [d / p["days"] for d in days_q]

    # --- балансирующие статьи и ОПУ: фиксированная точка по BV на конец (М§4.10 в годовом виде)
    bv_end = st["BV"] + st.get("ci_guess", 0.0) - div
    if bb_q is not None:
        bv_end -= sum(bb_q)
    ci = st.get("ci_guess", 0.0)
    ci_q = [ci / n] * n
    asset_books = [b for b, sp in books.items() if sp["side"] == LOANS_SIDE]
    one_at = c_per_parse(c_bget(B, "regimes.crisis.one_off_loss.period")) if one else None
    om_q = [c_traj_at(c_bget(B, "equity.other_movements"), y, q) for q in qs]
    ov_q = [c_traj_at(c_bget(B, "regimes.near_nim_shift"), y, q) + c_traj_at(c_bget(B, f"regimes.{r}.nim_shift"), y, q)
            + _c_dev_at(dev.get("nim"), y, q) for q in qs]              # сдвиги ЧПМ квартала (М§4.4)
    for _ in range(FIT_ITER):
        liab_nb = fr1 + cf1 + wh_base + OL + dp_end + at1 + ncib
        assets_nb = sum_loans - AL + OA
        la = liab_nb + bv_end - assets_nb
        la_min = m_liq * assets_nb / (1.0 - m_liq)
        extra = max(0.0, la_min - la)
        la = max(la, la_min)
        E[SECURITIES], E[LIQUIDITY], E[WHOLESALE] = ssl * la, (1.0 - ssl) * la, wh_base + extra
        avg = dict(avg_nb)
        shift_la = sum(w * c for w, c in zip(w_ci, ci_q)) - paid_shift + curve_la
        la_avg = (la0 + la) / 2.0 + shift_la
        extra_avg = (extra0 + extra) / 2.0
        if extra0 > 0.0 and extra > 0.0:
            # минимум ликвидности связывает на обоих концах периода: LA стоит на минимуме весь период, а
            # время капитальных потоков и кривизну несёт добор опта (он — разность минимума и свободной LA)
            la_avg = m_liq / (1.0 - m_liq) * assets_nb_avg
            extra_avg = la_avg - ((la0 - extra0 + la - extra) / 2.0 + shift_la)
        avg[SECURITIES], avg[LIQUIDITY] = ssl * la_avg, (1.0 - ssl) * la_avg
        avg[WHOLESALE] = wtf * cl_avg + extra_avg          # Р11-2: при clients — база опта на средствах клиентов
        iea = sum(avg[b] for b in asset_books)
        if ctx.get("k2"):
            # база связи по строке и смесь расходов (К2)
            fees_q, opex_q, ins_q, k2_store, k2_print = c_line_volumes()
            fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
        elif opex_w is not None:
            # драйвер расходов, взвешенный по себестоимости книг (ключ opex.volume_weights, М§4.7): средние остатки
            # периода всех книг с весом (балансирующих — этой итерации); рост — годовая форма, к тем же кварталам
            # прошлого года; комиссии и страхование — на базе volumes.link_base
            w_avg = sum(opex_w[b] * avg[b] for b in opex_w)
            v_opex = c_volume_growth_weighted(ctx, st, y, qs, w_avg * n)
            v_base = v_now if v_now is not None else c_volume_growth(ctx, st, link_base, y, qs, iea * n)
            fees_q, opex_q, ins_q = c_volume_lines(v_base, v_opex)
            fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
        elif link_on and v_now is None:
            # база объёма — средние процентные активы шага (М§4.7)
            fees_q, opex_q, ins_q = c_volume_lines(c_volume_growth(ctx, st, link_base, y, qs, iea * n))
            fees, opex, ins = sum(fees_q), sum(opex_q), sum(ins_q)
        inc = sum(ybar[b] * avg[b] for b in asset_books) * dfac
        exp_ = sum(ybar[b] * avg[b] for b in books if b not in asset_books) * dfac
        dia_amt = dia * fr_avg * dfac
        ovl = (near + nim_shift + d_nim) * iea * dfac      # ближний сдвиг + сдвиг режима + A-P2u (М§4.4)
        nii = inc - exp_ - dia_amt + ovl
        fvr = 0.0
        if fvr_on:
            fvr = -(c_bnum(B, "oci.fvtpl_bond_duration") * (y_end - y_prev)
                    * c_bnum(B, "oci.fvtpl_bond_share") * avg[SECURITIES])
        pbt = nii - llp - fvc + fees + ins + misc + fvr + noncore - opex + one
        tax = tau_eff * pbt
        ni = pbt - tax - ot
        ni_sh = ni * (1.0 - nci) if nci_q is None else ni - sum(nci_q)
        r_end = st["R"] * pull ** n - D * reval * fvos * avg[SECURITIES] * (1.0 - sum(tau_stat) / n)
        oci = r_end - st["R"]
        ci = ni_sh - cpn * (1.0 - cpn_tau) + oci + om
        # ЧПМ квартала внутри периода (ожидание A-P2u, М§12, и профиль ЧПД): ставки квартала y_q при
        # структуре баланса периода; сдвиги ЧПМ (ближний, режима, отклонение A-P2u) — квартала
        nim_q = []
        for j, q in enumerate(qs):
            d_rate = sum((y_q[b][j] - ybar[b]) * avg[b] * (1.0 if b in asset_books else -1.0) for b in books) / iea
            nim_q.append(nii / iea / dfac + d_rate + ov_q[j] - (near + nim_shift + d_nim))
        # профиль прибыли внутри периода (для времени капитальных потоков, E_q, точек проверки и
        # капитала на дату оценки): ЧКД, расходы, страхование, «прочее» и непрофильный — свои кварталы;
        # ЧПД — по дням × ЧПМ квартала × рост процентных активов внутри периода (геометрически от начала
        # к концу), резервы — по CoR квартала × дни × рост кредитов, FVC — свои кварталы, FVR — по дням;
        # разовый убыток и купон AT1 — в своих кварталах; фонд FVOCI — квартальной рекурсией М§4.9 на
        # среднем портфеле периода (OCI квартала — его приращение)
        w_nii = c_grow_w([d * m for d, m in zip(days_q, nim_q)] if min(nim_q) > 0.0 else days_q,
                         sum(st["E"][b] for b in asset_books), sum(E[b] for b in asset_books))
        r_q, rr = [], st["R"]
        for j in range(n):
            rr = rr * pull - D * (path_y[j + 1] - path_y[j]) * fvos * avg[SECURITIES] * (1.0 - sum(tau_stat) / n)
            r_q.append(rr)
        oci_q = [r_q[0] - st["R"]] + [r_q[j] - r_q[j - 1] for j in range(1, n)]
        ni_q, ci_q = {}, []
        for j, q in enumerate(qs):
            pbt_q = (nii * w_nii[j] + fvr * days_q[j] / p["days"] - llp * w_cr[j] - fvc_q[j]
                     + fees_q[j] + ins_q[j] + ms_q[j] + nc_q[j] - opex_q[j] + (one if one_at == (y, q) else 0.0))
            if nci_q is None:
                ni_q[(y, q)] = (pbt_q * (1.0 - tau_eff) - (ot if q == 1 else 0.0)) * (1.0 - nci)
            else:
                ni_q[(y, q)] = pbt_q * (1.0 - tau_eff) - (ot if q == 1 else 0.0) - nci_q[j]
            ci_q.append(ni_q[(y, q)] - (cpn * (1.0 - cpn_tau) if q == A["cpn_quarter"] else 0.0)
                        + oci_q[j] + om_q[j])
        new_bv = st["BV"] + ci - div
        if bb_q is not None:
            new_bv -= sum(bb_q)
        done = abs(new_bv - bv_end) <= FIT_TOL * max(1.0, abs(new_bv))
        bv_end = new_bv
        if done:
            break


    # --- RWA и нормативы (М§4.11–§4.12) на конец периода
    dens = c_bget(B, "capital.rwa.density")
    dn = st["Dn"] * ((1.0 + c_bnum(B, "capital.rwa.density_drift_rate")) ** frac
                     if y <= int(c_bnum(B, "capital.rwa.density_drift_until")) else 1.0)
    fxp, xf, xf_q = st["fxp"], 1.0, [1.0] * n
    if c_bget(B, "capital.rwa.fx.enabled"):
        fx, pistar = c_bnum(B, "capital.rwa.fx.share"), c_bnum(B, "capital.rwa.fx.foreign_inflation")
        for j in range(n):
            fxp *= ((1.0 + wd["cpi"][j]) / (1.0 + pistar)) ** (1.0 / QY)
            xf_q[j] = 1.0 - fx + fx * fxp
        xf = 1.0 - fx + fx * fxp
    gr = ctx.get("guar")
    g_end = None
    if gr is not None:
        # составляющая RWA гарантий (К5): G = G_0 × D^G / D^G_0 по драйверу на конце периода
        g_end = c_guarantee_amount(ctx, cell, st, gr, y, qs, n - 1, E, nom_q[-1], fees_q)
    disp_end = None if cash_path is None else c_cash_disp(cash, c_qidx(ctx["anchor"], y, qs[-1]), sum_loans)
    rwa = _c_rwa_of(ctx, r, y, hq, E, OA, dn, xf, guar=g_end, cash=None if cash_path is None else cash_path[-1],
                    disp=disp_end)
    drifting = y <= int(c_bnum(B, "capital.rwa.density_drift_until"))
    dn_q = [st["Dn"] * ((1.0 + c_bnum(B, "capital.rwa.density_drift_rate")) ** ((j + 1) / QY) if drifting else 1.0)
            for j in range(n)]
    cap = _c_capital(ctx, s, y, hq, bv_end, dpreg, r_end, rwa, {**st["ni_q"], **ni_q})
    row.update(nii=nii, llp=llp, fvc=fvc, fees=fees, opex=opex, ins=ins, misc=misc, noncore=noncore,
               fvr=fvr, one_off=one, pbt=pbt, tax=tax, ot=ot, ni=ni, ni_sh=ni_sh, oci=oci,
               cpn=cpn, cpn_net=cpn * (1.0 - cpn_tau), om=om, ci=ci, div=div, bv=bv_end, R=r_end, R_q=r_q,
               loans=sum_loans, loans_ac=loans_ac, iea=iea, iea_end=sum(E[b] for b in asset_books), funds=fr1 + cf1,
               securities=E[SECURITIES], liquidity=E[LIQUIDITY], wholesale=E[WHOLESALE],
               wholesale_extra=extra, oa=OA, ol=OL, al=AL, dp=dp_end, dpreg=dpreg, rwa=rwa,
               assets=sum_loans - AL + E[SECURITIES] + E[LIQUIDITY] + OA,
               liabilities=fr1 + cf1 + E[WHOLESALE] + OL + dp_end + bv_end + at1 + ncib,
               nim=nii / iea / dfac, nim_books=(nii - ovl) / iea / dfac, nim_q=nim_q,
               cor=cor_c, cor_mgmt=(c_to_mgmt(A, "cor", cor_c) if c_bget(B, "regimes.cor_basis") == "mgmt"
                                    else cor_c),
               cir=opex / (nii + fees + ins + misc + fvr) if (nii + fees + ins + misc + fvr) else None,
               roe=ni_sh / ((st["BV"] + bv_end) / 2.0), y_liq_end=Ynew[LIQUIDITY],
               y_sec_end=Ynew[SECURITIES], c_wh_end=Ynew[WHOLESALE],
               tau_eff=tau_eff, share_target=share_target, c=c1, ni_q=ni_q, ci_q=ci_q, shift_la=shift_la,
               near=near, nim_shift=nim_shift, misc_q=ms_q, noncore_q=nc_q, fvc_q=fvc_q,
               cor_q=cor_prof, cor_ref_q=ref_prof, idx_q=idx, fv_avg_q=fv_avg_q, days_q=days_q,
               loans_ac_avg=loans_ac_avg, paid_shift=paid_shift, curve_la=curve_la, la_avg=la_avg,
               wholesale_avg=avg[WHOLESALE], assets_nb_avg=assets_nb_avg, funds_avg=funds_avg,
               x_q=x_w, rates_end=dict(Ynew), div_list=div_list, m_q=m_q, fr_path=fr_path, cf_path=cf_path,
               loans_path=loans_path, loans_ac_ends=ac_path, dn_q=dn_q, xf_q=xf_q, v_volume=v_now,
               books_end={b: E[b] for b in loans}, dn_end=dn, xf_end=xf,
               fees_q=fees_q, opex_q=opex_q, ins_q=ins_q, **cap)
    if k6_out:
        # Р11-2 (печать только при ключе): средства клиентов без книг К6 — конец и средняя периода (база опта К3)
        row.update(clients=cl1, clients_avg=cl_avg)
    if nci_q is not None:
        # Р11-3 (печать только при ключе): НДУ в рублях — кварталы периода и сумма (номинал мира)
        row.update(nci=sum(nci_q), nci_q=nci_q)
    qv = dict(st["qv"])
    for j, q in enumerate(qs):
        qv[("fees_net", y, q)], qv[("opex", y, q)], qv[("insurance_net", y, q)] = fees_q[j], opex_q[j], ins_q[j]
    nst = {"E": E, "y": Ynew, "c": c1, "BV": bv_end, "R": r_end, "pay": left, "Dn": dn,
           "fxp": fxp, "I": I, "y_tenor": y_end, "D": st["D"], "ci_guess": ci,
           "ni_q": {**st["ni_q"], **ni_q}, "qv": qv}
    if plan is not None:
        nst.update(pay=[], dq=left, dp_perm=st["dp_perm"], Epot=st["Epot"])
    if link_on or k6_rec is not None:
        # концы кварталов базы объёма — для роста «к тому же кварталу прошлого года» (М§4.7)
        vend = dict(st.get("vend", {}))
        for j, q in enumerate(qs):
            vend[(y, q)] = {}
            if link_on:
                vend[(y, q)] = {LINK_BASES[0]: loans_path[j + 1], LINK_BASES[1]: funds_path[j + 1],
                                LINK_BASES[-1]: iea}
                if opex_w is not None and not ctx.get("k2"):
                    vend[(y, q)][OPEX_BASE] = w_avg     # взвешенная база расходов: средняя периода на квартал
                if ctx.get("k2"):
                    vend[(y, q)].update(k2_store[j])    # средние баз строк К2 по кварталам («к тому же кварталу»)
            if k6_rec is not None:
                vend[(y, q)].update(k6_rec[j])          # Р10-5: D и Ψ ведомых книг К6 на конце квартала
        nst["vend"] = vend
    if ctx.get("k2"):
        # печать базы строки: средняя периода на квартал и рост за год в годовой форме (К2)
        for line, out in k2_print.items():
            row[f"v_{line}"], row[f"vol_{line}"] = out["v"], out["vol"]
            if out.get("nominal") is not None:
                row["franchise_h"] = out["nominal"]     # Р8-6: номинальная часть франшизы {строка: H кварталов периода}
            if out.get("phi") is not None:
                row["franchise_phi"] = out["phi"]       # Р10-5: франшиза формы строки {строка: Φ кварталов периода}
    elif opex_w is not None:
        row.update(v_opex=v_opex, vol_opex=w_avg)
    if bb_q is not None:
        row.update(bb=sum(bb_q), bb_q=bb_q)
    if ctx.get("base_ends"):
        # концы кварталов статей, из которых ключи К5 и К6 собирают уровень базы строки в квартальном проходе
        nst["nom"] = nom_q[-1]
        ends = {RETAIL_CURRENT: [c * f for c, f in zip(c_path, fr_path)],
                RETAIL_TERM: [(1.0 - c) * f for c, f in zip(c_path, fr_path)], **bpath}
        row.update(nom_q=nom_q, nb_ends=ends)
    if g_end is not None:
        row.update(guar=g_end, rwa_guar=g_end * dn * xf * c_rwa_mult(ctx, r, y, hq))
    if drv:
        row["driven_end"] = {b: E[b] for b in drv}
    if cash_path is not None:
        row.update(cash=cash_path[-1], cash_ends=cash_path)      # К8: деньги на концах кварталов периода
        if cash.get("path") is not None:
            # доля книги (Р6-1): доли и вычеты на концах кварталов периода, слагаемое RWA вытесненной части конца
            row.update(cash_c=cash_c, cash_cut=cut_path, cash_disp=disp_end)
    if ctx.get("stationary"):
        # К4: ЧПД периода при полной подстройке ставок книг (ρ = 1) — годовая агрегация: средняя ставка книги
        # периода против средней цели периода на тех же средних остатках; балансирующие — средние ЧПД
        items = [(1.0 if b in asset_books else -1.0, tbar[b], ybar[b], avg[b], dfac) for b in books]
        row["stationary"] = {"d_nii": c_stationary_gap(items), "targets": dict(tbar), "ybar": dict(ybar),
                             "avg": {b: avg[b] for b in books}}
    if (ctx.get("funds_keys") or {}).get("keyed"):
        # Р10-6, Р10-1: проценты и остатки книг средств (пассивы без опта) периода × доля года — числа гейта стоимости
        # средств клиентов к ключевой (c_funds_cost_to_key); только при ключах прохода 8 в checks
        row["funds_cost"] = {b: (ybar[b] * avg[b] * dfac, avg[b] * dfac) for b in books
                             if b not in asset_books and b != WHOLESALE}
    return nst, row


def c_stationary_gap(items) -> float:
    """ΔNII* = Σ знак × (цель − ставка) × средний остаток × доля года (К4): items — пятёрки (знак: +1 актив, −1 пассив;
    цель книги — ставка при ρ = 1; ставка; средний остаток; доля года). Годовая строка даёт по одной пятёрке на книгу
    (средняя цель и средняя ставка периода), пример — по одной на квартал."""
    return sum(sign * (target - rate) * avg * dt for sign, target, rate, avg, dt in items)


def c_opex_mix(shares: dict, b_c: float, b_c0: float, a: dict, a0: dict, nom: dict | None = None,
               phi: dict | None = None) -> float:
    """Смесь базы расходов квартала (К2, opex.line_shares): A^C = (1 − s_F − s_I) B^C + Σ_ℓ s_ℓ B^C_0 Φ^ℓ — доля s_ℓ
    базы расходов якоря идёт за драйвером строки ℓ (франшиза); на якоре A^C_0 = B^C_0 (ступени нет). Без ключа
    opex.line_share_roots у строки Φ^ℓ = A^ℓ / A^ℓ_0 (прежняя строка); с ключом (nom: {строка: (λ, H)}, Р8-6)
    Φ^ℓ = λ A^ℓ / A^ℓ_0 + (1 − λ) H^ℓ — слагаемые s B^C_0 A / A_0 × λ и s B^C_0 (1 − λ) H: при λ = 1 бит в бит прежняя.
    Франшиза формой строки (phi: {строка: Φ}, Р10-5) — слагаемое s B^C_0 Φ без λ-слагаемых: Φ уже несёт связь строки."""
    out = (1.0 - sum(shares.values())) * b_c
    for line, share in shares.items():
        if phi is not None and line in phi:
            out += share * b_c0 * phi[line]
        elif nom is not None and line in nom:
            lam, h = nom[line]
            out += share * b_c0 * a[line] / a0[line] * lam + share * b_c0 * (1.0 - lam) * h
        else:
            out += share * b_c0 * a[line] / a0[line]
    return out


ROOT_FORMS = ("additive", "multiplicative")          # volumes.line_root_form: форма корня комиссий и страхования (Р5-6)


def c_root_mult(B: dict) -> bool:
    """Корень строки множителем (ключ volumes.line_root_form, решения № 5, Р5-6): multiplicative — рост комиссий и
    страхования к тому же кварталу (1 + рост базы)(1 + корень) − 1, как у расходов (М§4.7): при связи 1 отношение строки
    к её базе растёт ровно на корень в любом мире; additive и нет ключа — прежняя сумма «рост базы + корень». null или
    значение не из перечня — отказ (М§0.1)."""
    node = c_bopt(B, "volumes") or {}
    if "line_root_form" not in node:
        return False
    form = node["line_root_form"]
    if form not in ROOT_FORMS:
        raise ControlInputError(f"volumes.line_root_form: {form!r} — не {', '.join(ROOT_FORMS)} (М§4.7)")
    return form == ROOT_FORMS[1]


def c_base_factor(wage: float, link: float, v) -> float:
    """Множитель роста базы строки квартала без корня (Р5-6): 1 + рост зарплат + связь × (рост объёма − рост зарплат); без
    связи или без роста объёма — 1 + рост зарплат (М§4.7)."""
    if v is None or not link:
        return 1.0 + wage
    return 1.0 + wage + link * (v - wage)


def c_at(x, j: int):
    """Рост объёма квартала j: общий для периода (число) или свой у квартала (список, база «номинал» К2)."""
    return x[j] if isinstance(x, list) else x


PART_LETTERS = ("Q", "H")                 # буквы части года в ключе времени траектории: квартал и полугодие
PART_KEY_FORM = PART_LETTERS[0] + "n"      # форма хвоста ключа части года: буква и номер


def c_premium(B: dict, key: str, names: tuple, name: str, y: int, quarters=None) -> float:
    """Премия роста года (М§4.3): число (одна на все книги — форма образца) или словарь траекторий с
    ключами ровно names; значение словаря — значение траектории года. `quarters` — кварталы периода (их
    передаёт только премия средств клиентов): квартал, заданный в траектории ключом квартала или полугодия,
    читается этим ключом, квартал без такого ключа — значением года; премия периода — среднее его кварталов."""
    val = c_bget(B, key)
    if isinstance(val, dict):
        if sorted(str(k) for k in val) != sorted(names):
            raise ControlInputError(f"{key}: ключи словаря — не ровно {', '.join(names)} (М§4.3)")
        traj = val[name]
        timed = isinstance(traj, dict) and quarters is not None and any(c_premium_keyed(traj, y, q) for q in quarters)
        if not timed:
            return c_traj_mean(traj, y, range(1, QY + 1))
        plain = {k: v for k, v in traj.items() if not c_is_part_key(k)}      # значение года — без ключей частей года
        year = c_traj_mean(plain, y, range(1, QY + 1))
        return sum(c_traj_at(traj, y, q) if c_premium_keyed(traj, y, q) else year for q in quarters) / len(quarters)
    return c_bnum(B, key)


def c_is_part_key(key) -> bool:
    """Ключ квартала или полугодия траектории: год, буква части года (Q или H), номер части."""
    key = str(key)
    year, part = key[:-len(PART_KEY_FORM)], key[-len(PART_KEY_FORM):]
    return year.isdigit() and part[:len(PART_LETTERS[0])] in PART_LETTERS and part[len(PART_LETTERS[0]):].isdigit()


def c_premium_keyed(traj: dict, y: int, q: int) -> bool:
    """Квартал q года y задан в траектории ключом квартала или ключом своего полугодия."""
    names = {str(k) for k in traj}
    return f"{y}Q{q}" in names or f"{y}H{1 if q <= 2 else 2}" in names


def c_volume_growth(ctx: dict, st: dict, base: str, y: int, qs, now: float) -> float:
    """Рост объёма периода v (М§4.7) в годовой форме: now — сумма средних остатков базы по кварталам
    периода; делитель — та же сумма по тем же кварталам прошлого года (концы кварталов до якоря — факты
    balance.history, конец якоря — остатки якоря, позже — путь клетки)."""
    A, anchor = ctx["A"], ctx["anchor"]
    last = LINK_BASES[-1]

    def c_end(yy, qq):
        if (yy, qq) > anchor:
            return st["vend"][(yy, qq)][base]
        if (yy, qq) == anchor:
            E0, books = A["E0"], ctx["books"]
            if base == LINK_BASES[0]:
                return sum(E0[b] for b in ctx["loans"])
            if base == last:
                return sum(E0[b] for b, sp in books.items() if sp["side"] == LOANS_SIDE)
            return E0[RETAIL_CURRENT] + E0[RETAIL_TERM] + sum(E0[b] for b in ctx["fund_biz"])   # Р11-2: слово funds
        val = A["history"].get(f"{yy}Q{qq}", {}).get(base)
        if val is None:
            raise ControlInputError(f"нет конца квартала balance.history.{yy}Q{qq}.{base} для связи с объёмом (М§4.7)")
        return float(val)

    prev = 0.0
    for q in qs:
        yy, qq = y - 1, q
        if base == last and (yy, qq) > anchor:
            prev += st["vend"][(yy, qq)][base]          # средние процентные активы шага того квартала
            continue
        py, pq = (yy - 1, QY) if qq == 1 else (yy, qq - 1)
        prev += (c_end(py, pq) + c_end(yy, qq)) / 2.0
    if prev <= 0.0:
        raise ControlInputError("база объёма прошлого года не положительна (М§4.7)")
    return now / prev - 1.0


def c_weighted_end(ctx: dict, y: int, q: int) -> float:
    """Взвешенная база расходов на конце квартала (y, q) не позже якоря: Σ_b ω_b E_b — конец якоря из остатков
    якоря, раньше — из фактов balance.history.<период>.books.<b> (нет числа у книги с весом — отказ)."""
    A, w = ctx["A"], ctx["opex_w"]
    if (y, q) == ctx["anchor"]:
        return sum(w[b] * A["E0"][b] for b in w)
    rec = A["history_books"].get(f"{y}Q{q}", {})
    total = 0.0
    for b, wb in w.items():
        if not wb:
            continue
        val = rec.get(b)
        if val is None:
            raise ControlInputError(f"нет конца квартала balance.history.{y}Q{q}.books.{b} для драйвера расходов, "
                                    f"взвешенного по себестоимости книг (М§4.7)")
        total += wb * float(val)
    return total


def c_volume_growth_weighted(ctx: dict, st: dict, y: int, qs, now: float) -> float:
    """Рост базы расходов, взвешенной по себестоимости книг (ключ opex.volume_weights, М§4.7), в годовой форме: now —
    сумма взвешенных средних остатков кварталов периода; делитель — та же сумма тех же кварталов прошлого года.
    Квартал до якоря — полусумма взвешенных концов фактов по книгам, позже — средняя периода клетки того года."""
    anchor = ctx["anchor"]
    prev = 0.0
    for q in qs:
        yy = y - 1
        if (yy, q) > anchor:
            prev += st["vend"][(yy, q)][OPEX_BASE]
            continue
        py, pq = (yy - 1, QY) if q == 1 else (yy, q - 1)
        prev += (c_weighted_end(ctx, py, pq) + c_weighted_end(ctx, yy, q)) / 2.0
    if prev <= 0.0:
        raise ControlInputError("взвешенная база расходов прошлого года не положительна (М§4.7)")
    return now / prev - 1.0


def _c_rwa_of(ctx: dict, r, y: int, q: int, E: dict, OA: float, dn: float, xf: float, guar: float | None = None,
              cash: float | None = None, disp: float | None = None) -> float:
    """RWA (М§4.11): плотности книг и прочих активов × дрейф плотности × валютный индекс × множитель
    режима. Постоянные прочие активы входят со своей плотностью; r = None — RWA_0 якоря (без множителя). guar —
    составляющая гарантий G (К5): у книги выреза — плотность после выреза, G — под дрейф, валютный индекс и множитель
    режима, как вся сумма; без G (None) — RWA книг и прочих активов без гарантий. cash — деньги C (К8): у книги с ключом
    прочие активы делятся на растущую часть без денег (плотность после выреза), деньги (своя плотность) и постоянные;
    без C (None) — прежняя разбивка. disp — слагаемое вытесненной части прочих активов при доле денег книги (Р6-1,
    c_cash_disp): под дрейфом, валютным индексом и множителем режима, как вся сумма; None — прежняя строка."""
    dens, oaf = ctx["dens"], ctx["oaf"]
    gr = ctx.get("guar")
    if gr is None:
        base = sum(float(dens[b]) * E[b] for b in ctx["books"] if b in dens)
    else:
        base = sum((gr["w_carved"] if b == gr["carve"] else float(dens[b])) * E[b] for b in ctx["books"] if b in dens)
    cr = ctx.get("cash")
    if cr is not None and cash is not None:
        base = base + cr["w_rest"] * (OA - oaf - cash) + cr["w_cash"] * cash + ctx["dens_oaf"] * oaf
    elif oaf:
        base = base + float(dens["other_assets"]) * (OA - oaf) + ctx["dens_oaf"] * oaf
    else:
        base = base + float(dens["other_assets"]) * OA
    if guar is not None:
        base = base + guar
    if disp is not None:
        base = base + disp
    rwa = base * dn * xf
    mult = ctx["rwa_mult"].get(r) if r is not None else None
    if mult is not None:
        rwa = rwa * c_traj_at(mult, y, q)               # роспуск надбавок режима — на все RWA клетки
    return rwa


def c_rwa_mult(ctx: dict, r, y: int, q: int) -> float:
    """Множитель RWA режима в квартале (ключ regimes.<r>.rwa_density_mult); нет ключа у режима — 1."""
    mult = ctx["rwa_mult"].get(r) if r is not None else None
    return 1.0 if mult is None else c_traj_at(mult, y, q)


def c_fees_window(ctx: dict, st: dict, y: int, qs, fees_q: list, j: int) -> float:
    """Строка комиссий за четыре квартала, кончая кварталом j периода (драйвер гарантий fees_line, К5): кварталы
    периода — строка периода, прошлые кварталы клетки — ряд «к тому же кварталу» состояния, кварталы до якоря
    включительно — факты."""
    total = 0.0
    for back in range(QY):
        yy, qq = c_qback((y, qs[j]), back)
        if yy == y and qq in qs:
            total += fees_q[list(qs).index(qq)]
        elif (yy, qq) > ctx["anchor"]:
            total += st["qv"][("fees_net", yy, qq)]
        else:
            total += _c_fact_line(ctx["A"], "fees_net", yy, qq)
    return total


def c_guarantee_amount(ctx: dict, cell: dict, st: dict, gr: dict, y: int, qs, j: int, E: dict, nominal: float,
                       fees_q: list) -> float:
    """G на конце квартала j периода (К5): G_0 × D^G / D^G_0. Драйвер fees_base — уровень базы комиссий по остаткам E
    конца квартала (все книги) и индексу «номинала», fees_component — тем же правилом уровень базы компоненты смеси
    (Р5-5), fees_line — строка комиссий за четыре квартала. Драйвер ≤ 0 — отказ с меткой клетки и кварталом (рост
    гарантий не определён)."""
    if gr["driver"] in GUAR_BASE_DRIVERS:
        books = ctx["books"]
        d = c_base_level(gr["spec"], E, loans=ctx["loans"], biz=ctx["fund_biz"],        # Р11-2: слово funds
                         assets=[b for b, sp in books.items() if sp["side"] == LOANS_SIDE], nominal=nominal)
    else:
        d = c_fees_window(ctx, st, y, qs, fees_q, j)
    if not d > 0.0:
        raise ControlInputError(f"драйвер гарантий D^G = {d} не больше нуля: клетка "
                                + "/".join((cell["world"], cell["regime"], cell["scenario"])) + f", {y}Q{qs[j]} (М§4.11)")
    return gr["g0"] * d / gr["d0"]


def c_qidx(anchor: tuple, y: int, q: int) -> int:
    """Номер квартала (y, q) на сетке: якорь — 0, первый прогнозный — 1 (М§0.2)."""
    return (y - anchor[0]) * QY + (q - anchor[1])


def c_qper(anchor: tuple, k: int) -> tuple[int, int]:
    """Квартал сетки с номером k → (год, квартал в году)."""
    pos = anchor[0] * QY + (anchor[1] - 1) + k
    return pos // QY, pos % QY + 1


def c_qidx_of_date(anchor: tuple, d: dt.date) -> int:
    """Номер календарного квартала сетки, содержащего дату (М§5.7.2)."""
    return c_qidx(anchor, d.year, (d.month - 1) // 3 + 1)


def _c_dev_at(dv, y: int, q: int) -> float:
    """Затухающее отклонение A-P2u в квартале (y, q): ρ^k × m — от последнего наблюдения окна не позже
    этого квартала, k — кварталов после него (М§12). Квартал раньше первого наблюдения окна — ноль;
    наблюдённый квартал несёт своё отклонение, даже если за ним в окне есть более позднее."""
    if not dv:
        return 0.0
    last = None
    for ys, qs, m in dv["trail"]:
        if (ys, qs) <= (y, q):
            last = (ys, qs, m)
    if last is None:
        return 0.0
    return dv["rho"] ** ((y - last[0]) * QY + (q - last[1])) * last[2]


def c_cor_path_engine(ctx: dict, r: str, y: int, q: int) -> float:
    """Путь CoR режима в квартале в базисе движка (мост при cor_basis: mgmt, М§3.2, §4.6)."""
    c = c_traj_at(c_bget(ctx["B"], f"regimes.{r}.cor"), y, q)
    return c_to_engine(ctx["A"], "cor", c) if c_bget(ctx["B"], "regimes.cor_basis") == "mgmt" else c


def c_cor_ref_engine(ctx: dict, y: int, q: int) -> float:
    """Опора FVC в квартале (М§4.6): путь режима credit.fv_loans_ref книги-опоры — до розыгрыша осей,
    чувствительностей и поисков — в базисе движка."""
    B0 = ctx["B0"]
    c = c_traj_at(c_bget(B0, f"regimes.{ctx['fv_ref']}.cor"), y, q)
    return c_to_engine(ctx["A"], "cor", c) if c_bget(B0, "regimes.cor_basis") == "mgmt" else c


def _c_yoy_quarters(ctx: dict, st: dict, line: str, y: int, qs) -> list[float]:
    """База «к тому же кварталу прошлого года» по кварталам периода (М§0.3): факт до якоря
    включительно, иначе квартал прошлого года клетки."""
    A = ctx["A"]
    y0, qa = ctx["anchor"]
    out = []
    for q in qs:
        if (y - 1, q) <= (y0, qa):
            out.append(_c_fact_line(A, line, y - 1, q))
        else:
            out.append(st["qv"][(line, y - 1, q)])
    return out


def _c_book_quarters(ctx: dict, p: dict, idx: list[float], key: str, shares: dict,
                     residual_of: str | None = None) -> list[float]:
    """Годовая сумма книги по кварталам периода (М§0.3, §4.7): год × доля квартала × индекс цен.
    residual_of — строка фактов, которой год якоря закрывается остатком (книга − факт отчётных
    кварталов, по долям оставшихся кварталов): так считается непрофильный результат. Без неё
    («прочее») оставшиеся кварталы года якоря — та же формула, что в прочие годы."""
    B, A = ctx["B"], ctx["A"]
    y, qs = p["year"], p["quarters"]
    yearly = c_traj_mean(c_bget(B, key), y, range(1, QY + 1))
    if residual_of is None or not p["stub"]:
        return [yearly * shares[q] * idx[j] for j, q in enumerate(qs)]
    qa = ctx["anchor"][1]
    rest = yearly - sum(_c_fact_line(A, residual_of, y, q) for q in range(1, qa + 1))
    tot = sum(shares[q] for q in qs)
    if tot <= 0.0:
        raise ControlInputError(f"{key}: доли оставшихся кварталов года якоря в сумме 0 — остаток некуда разложить")
    return [rest * shares[q] / tot * idx[j] for j, q in enumerate(qs)]


def _c_capital(ctx: dict, s: str, y: int, h: int, bv: float, dpreg: float, R: float, rwa: float,
             ni_q: dict) -> dict:
    """K20, K11, Н20.0 и второй норматив (слот n11: отчётный и с прибылью периода), требования и полы в
    квартале (y, h) (М§4.11–§4.12)."""
    B = ctx["B"]
    f = c_bnum(B, "capital.n20.fvoci_recognition")
    bvreg = bv + dpreg - (1.0 - f) * R
    ratio = rwa / ctx["rwa0"]
    t2 = c_traj_at(c_bget(B, "capital.n20.t2"), y, h)
    k20 = bvreg - c_bnum(B, "capital.n20.deductions_anchor") * ratio + ctx["A"]["AT1"] + t2
    cut = [int(c) for c in c_bget(B, "capital.n11.audit_cutoffs")]
    e_q = _c_unaudited_quarters(cut, y, h)
    missing = [yq for yq in e_q if yq not in ni_q]
    if missing:
        raise ControlInputError(f"нет прибыли кварталов {missing} для E_q")
    e_un = sum(ni_q[yq] for yq in e_q)
    # из базового капитала исключается только прибыль неаудированного периода; убыток — уже в BV (М§4.11)
    e_out = e_un if e_un > 0.0 else 0.0
    k11 = bvreg - e_out - c_bnum(B, "capital.n11.deductions_anchor") * ratio
    dp20 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), y, h)
    dp11 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n1_1"), y, h)
    n20 = k20 / rwa + c_bnum(B, "capital.n20.gap_pp") - dp20
    n11 = k11 / rwa + c_bnum(B, "capital.n11.gap_pp") - dp11
    n11_star = (k11 + e_out) / rwa + c_bnum(B, "capital.n11.gap_pp") - dp11
    fl20, fl11 = _c_floor(B, s, "n20_0", y, h), _c_floor(B, s, "n1_1", y, h)
    return {"k20": k20, "k11": k11, "n20": n20, "n11": n11, "n11_star": n11_star, "e_unaudited": e_un,
            "floor20": fl20, "floor11": fl11,
            "req20": max(c_bnum(B, "dividends.policy.threshold"), fl20 + c_bnum(B, "capital.mgmt_buffer.n20_0")),
            "req11": fl11 + c_bnum(B, "capital.mgmt_buffer.n1_1")}


def _c_start_state(ctx: dict) -> dict:
    A, B = ctx["A"], ctx["B"]
    tenor = c_bget(B, "oci.fvoci_tenor")
    node = tenor.split("_")[1].rstrip("y")
    ni_q = {}
    for per, rec in A["pnl"].items():
        if rec.get("ni_shareholders") is not None:
            ni_q[c_per_parse(per)] = float(rec["ni_shareholders"])
    fr = A["E0"][RETAIL_CURRENT] + A["E0"][RETAIL_TERM]
    # дивиденд, объявленный до даты фактов, уже вычтен из BV якоря; сумма к выплате — факт баланса,
    # кварталы выплаты и вычета — по записи реестра за этот год прибыли (ГОСА — в году якоря, не позже
    # якоря: иначе контекст отказал бы), иначе по календарю (М§5.4)
    start = {"E": dict(A["E0"]), "y": dict(A["rate0"]), "c": A["E0"][RETAIL_CURRENT] / fr,
             "BV": A["BV"], "R": A["R0"], "Dn": 1.0, "fxp": 1.0, "I": 1.0,
             "y_tenor": A["curve0"][node], "D": 0.0, "ni_q": ni_q, "qv": {}}
    if ctx["quarterly"]:
        # состояние якоря квартального режима (М§5.7.4): объявленная часть остатка — в очередях выплат и
        # вычетов, остаток — постоянное обязательство; уровни потенциального пути — остатки якоря (М§4.13.1)
        cal = ctx["divcal"]
        start.update(pay=[], dq=[dict(it) for it in cal["queue0"]], dp_perm=cal["perm"],
                     Epot={b: A["E0"][b] for b in ctx["loans"]})
        return start
    profit_year = ctx["anchor"][0] - 1 if A["DP_year"] is None else int(A["DP_year"])
    start["pay"] = [{"amt": A["DP"], **_c_dividend_dates(ctx, profit_year)}] if A["DP"] else []
    return start


# ============================================================================ дивиденды (М§5) в годовом шаге

REGISTER_BINDING = ("declared", "paid")   # объявленное — обязательство; `recommended` — только плашка (М§15.1)


def _c_register_binding(ctx: dict) -> list[dict]:
    """Записи реестра с объявленным дивидендом (решение ГОСА принято: declared или уже paid)."""
    return [rec for rec in ctx["A"]["register"] if rec.get("status", "declared") in REGISTER_BINDING]


def _c_register_rec(ctx: dict, year: int):
    for rec in _c_register_binding(ctx):
        if int(_c_nodeval(rec.get("year"))) == year:
            return rec
    return None


def _c_register_dps(ctx: dict, year: int):
    rec = _c_register_rec(ctx, year)
    return None if rec is None else float(_c_nodeval(rec["dps"]))


def _c_dividend_dates(ctx: dict, profit_year: int) -> dict:
    """Кварталы выплаты и вычета из регуляторного капитала дивиденда за год прибыли (М§5.4): у
    объявленной записи реестра (declared | paid) даты записи сильнее календаря книги — выплата в
    квартале pay_date, вычет в квартале отсечки record_date; нет записи или даты — None (календарь)."""
    out = {"agm_year": profit_year + 1, "pay": None, "reg": None}
    rec = _c_register_rec(ctx, profit_year)
    if rec is None:
        return out
    for key, field in (("pay", "pay_date"), ("reg", "record_date")):
        val = _c_nodeval(rec.get(field))
        if val:
            d = _c_as_date(val)
            out[key] = (d.year, (d.month - 1) // 3 + 1)
    return out


def _c_decide(ctx: dict, cell: dict, st: dict, i: int) -> tuple[float, dict]:
    """Решение года прибыли Y = год периода − 1: пробный проход, запас H, ступени, кризис, реестр."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    yp = p["year"] - 1
    info = {"profit_year": yp}
    n_out, n_iss = A["N_out"], A["N_iss"]
    reg = _c_register_dps(ctx, yp)
    if reg is not None:
        info.update(kind="register", dps_register=reg)
        return reg * n_out / 1000.0, info
    if any((yp, q) not in st["ni_q"] for q in range(1, QY + 1)):
        raise ControlInputError(f"нет прибыли акционеров всех кварталов {yp} года для базы дивиденда (М§5.2)")
    ni_y = sum(v for (yy, _), v in st["ni_q"].items() if yy == yp)
    base = ni_y - (A["cpn_annual"] * (1.0 - c_traj_at(c_bget(B, "tax.statutory"), yp, A["cpn_quarter"]))
                   if c_bget(B, "dividends.policy.deduct_at1_after_tax") else 0.0)
    dev = c_traj_mean(c_bget(B, "dividends.payout_deviation"), yp, range(1, QY + 1))
    steps = c_bget(B, "dividends.policy.steps") or [
        {"payout": c_traj_mean(c_bget(B, "dividends.policy.payout"), yp, range(1, QY + 1)),
         "threshold": c_bnum(B, "dividends.policy.threshold")}]
    trial = _c_period(ctx, cell, st, i, 0.0)[1]
    cps = [int(c) for c in c_bget(B, "dividends.calendar.checkpoints")]
    y = p["year"]
    s = cell["scenario"]
    buf20 = c_bnum(B, "capital.mgmt_buffer.n20_0")
    hs = []
    for j, stp in enumerate(steps):
        pj = min(1.0, max(0.0, float(stp["payout"]) + dev))
        want = pj * max(0.0, base) * n_out / n_iss
        H = float("inf")
        for h in cps:
            # состояние в точке проверки h года y пробного прохода: капитал — BV начала года + CI
            # кварталов по h (квартальный профиль периода), фонд FVOCI — квартальная рекурсия, RWA —
            # геометрически между началом и концом года
            if h not in p["quarters"]:
                raise ControlInputError(f"точка проверки {h} вне кварталов периода {p['label']} (М§5.3)")
            j_h = p["quarters"].index(h)
            bv_h = st["BV"] + sum(trial["ci_q"][:j_h + 1])
            r_h = trial["R_q"][j_h]
            rwa_h = st["rwa"] * (trial["rwa"] / st["rwa"]) ** ((j_h + 1) / p["n"])
            ni_q = {**st["ni_q"], **trial["ni_q"]}
            cap = _c_capital(ctx, s, y, h, bv_h, 0.0, r_h, rwa_h, ni_q)
            req20 = max(float(stp["threshold"]), cap["floor20"] + buf20)
            H = min(H, (cap["n20"] - req20) * rwa_h, (cap["n11"] - cap["req11"]) * rwa_h)
        hs.append((want, H))
        if H >= want:
            base_div, H_used, step = want, H, j
            break
    else:
        want, H = hs[-1]
        base_div, H_used, step = max(0.0, min(want, H)), H, len(steps) - 1
    want1 = hs[0][0]
    info.update(kind="policy", base=base, want=want1, H=H_used, step=step, base_div=base_div)
    if (cell["regime"] == R_CRISIS and y == ctx["shock_year"]
            and c_bget(B, "dividends.crisis.skip_in_shock_year")):
        st["D"] += want1
        info.update(kind="crisis_skip")
        return 0.0, info
    catch = min(st["D"], max(0.0, H_used - base_div)) if c_bget(B, "dividends.crisis.catch_up") else 0.0
    eps = 0.0
    fy = int(c_bnum(B, "dividends.excess.from_profit_year"))
    if yp >= fy:
        # линейный ввод ε за ramp_years лет (М§5.3 п. 4): ε_Y = ε × min(1, (Y − from + 1)/ramp)
        ramp = int(c_bnum(B, "dividends.excess.ramp_years"))
        if ramp < 1:
            raise ControlInputError("dividends.excess.ramp_years — целое ≥ 1 (М прил. A)")
        eps = c_bnum(B, "dividends.excess.epsilon") * min(1.0, (yp - fy + 1) / ramp)
    exc = eps * max(0.0, H_used - base_div - catch)
    st["D"] -= catch
    info.update(catch=catch, excess=exc, eps=eps)
    return base_div + catch + exc, info


# ============================================================================ клетка целиком: путь, RI/DDM, терминал

def _c_cell_path(ctx: dict, cell: dict, upto_year: int | None = None) -> dict:
    """Годовой путь клетки и решения о дивидендах (до года upto_year включительно, если задан)."""
    B, A = ctx["B"], ctx["A"]
    st = _c_start_state(ctx)
    y0, qa = ctx["anchor"]
    cap0 = _c_capital(ctx, cell["scenario"], y0, qa, A["BV"], A["DP"], A["R0"], ctx["rwa0"], st["ni_q"])
    st["rwa"] = ctx["rwa0"]
    rows, decisions = [], {}
    if ctx["quarterly"]:
        # квартальный календарь (М§5.7) и рост, ограниченный капиталом (М§4.13): квартальный проход внутри года
        cap0 = _c_capital(ctx, cell["scenario"], y0, qa, A["BV"], c_dpreg_anchor(B, A), A["R0"], ctx["rwa0"],
                          st["ni_q"])
        if ctx.get("bb") is not None:
            # выкуп: акции клетки с фактов якоря, форвард — от P_s (цена книги; у правила cell_value — неподвижная точка)
            st["n_c"], st["p_plus"] = A["N_out"], cell.get("bb_start", ctx["bb"]["p_book"])
        made = []
        for i, p in enumerate(ctx["periods"]):
            if upto_year is not None and p["year"] > upto_year:
                break
            st, row = _c_year_quarterly(ctx, cell, st, i)
            st["rwa"] = row["rwa"]
            made.extend(row["decisions_q"])
            rows.append(row)
        out = {"rows": rows, "decisions": decisions, "anchor_capital": cap0, "decisions_q": made}
        if upto_year is None:
            out["decisions"] = c_profit_years(ctx, made)
        _c_year_margin(ctx, rows)
        return out
    agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
    for i, p in enumerate(ctx["periods"]):
        if upto_year is not None and p["year"] > upto_year:
            break
        div = 0.0
        if agm in p["quarters"] and not (p["stub"] and A["DP_year"] is not None
                                         and int(A["DP_year"]) == p["year"] - 1):
            # и в неполном году якоря: собрание после якоря решает в своём квартале (М§17), если факты не
            # говорят, что дивиденд за этот год прибыли уже объявлен и вычтен из BV якоря (М§5.4)
            div, info = _c_decide(ctx, cell, st, i)
            decisions[p["year"] - 1] = {**info, "div": div, "dps": div * 1000.0 / A["N_out"]}
        D_keep = st["D"]
        st, row = _c_period(ctx, cell, st, i, div)
        st["D"] = D_keep
        st["rwa"] = row["rwa"]
        row["D"] = D_keep
        rows.append(row)
    _c_year_margin(ctx, rows)
    return {"rows": rows, "decisions": decisions, "anchor_capital": cap0}


def _c_year_margin(ctx: dict, rows: list[dict]) -> None:
    """Годовые метрики движка по правилу печати (М§0.3): сумма года к среднему пяти концов кварталов — конец
    прошлого года и четыре конца года. ЧПМ — ЧПД к процентным активам, CoR — резервы к кредитам по
    амортизированной стоимости; C/I — расходы к доходу NII + F + INS + MISC + FVR (М§4.6). Концы кварталов —
    из квартального прохода капитала; у годовой ветви образца — геометрический путь между началом и концом
    года. Неполный год якоря значений не несёт (его годовая метрика смешивает факты отчётных кварталов,
    М§4.6)."""
    prev = ctx["tr"]["iea0"]
    for p, row in zip(ctx["periods"], rows):
        inner = ([x["iea"] for x in row["quarters"]] if "quarters" in row
                 else _c_geo_path(prev, row["iea_end"], p["n"])[1:])
        row["iea_ends"] = [prev] + inner
        row["income_cir"] = row["nii"] + row["fees"] + row["ins"] + row["misc"] + row["fvr"]
        row["nim_year"] = row["cor_year"] = row["cir_year"] = None
        if not p["stub"]:
            row["nim_year"] = row["nii"] / _c_ends_mean(row["iea_ends"])
            row["cor_year"] = row["llp"] / _c_ends_mean(row["loans_ac_ends"])
            row["cir_year"] = row["opex"] / row["income_cir"] if row["income_cir"] else None
        prev = row["iea_end"]


def _c_ends_mean(ends: list[float]) -> float:
    """Среднее концов кварталов года — знаменатель годового отношения (М§0.3)."""
    return sum(ends) / len(ends)


# ============================================================================ квартальный календарь дивидендов (М§5.7)

def c_div_calendar(B: dict, A: dict) -> dict:
    """Календарь квартального режима (М§5.7.2, §5.7.4), общий для клеток: правило закрытого квартала p_last
    по фактам, открытые кварталы прибыли с кварталами решения, вычета и выплаты (запись реестра сильнее
    карты лагов), состояние якоря — очереди объявленных дивидендов и постоянная часть остатка."""
    if "divcal" in A:
        return A["divcal"]
    anchor, facts_date = A["anchor"], A["facts_date"]
    cal = c_bget(B, "dividends.calendar")
    for key in ("decision_lag_quarters", "reg_deduction_lag_quarters", "payment_lag_quarters", "checkpoints_ahead"):
        if cal.get(key) is None:
            raise ControlInputError(f"dividends.calendar.{key}: нет ключа квартального режима (М§5.7.1)")
    if int(cal["checkpoints_ahead"]) != 0:
        raise ControlInputError("dividends.calendar.checkpoints_ahead: допустим только 0 (М§5.7.1)")
    lag_raw = cal["decision_lag_quarters"]
    if isinstance(lag_raw, dict):
        lags = {int(k): int(v) for k, v in lag_raw.items()}
        if sorted(lags) != list(range(1, QY + 1)):
            raise ControlInputError("dividends.calendar.decision_lag_quarters: ключи — не ровно 1…4 (М§5.7.1)")
    else:
        lags = {h: int(lag_raw) for h in range(1, QY + 1)}
    reg_lag, pay_lag = int(cal["reg_deduction_lag_quarters"]), int(cal["payment_lag_quarters"])
    if any(not 1 <= x <= QY for x in list(lags.values()) + [reg_lag, pay_lag]):
        raise ControlInputError("лаг календаря дивидендов вне 1…4 (М§5.7.1)")
    last_q = c_qidx(anchor, *c_per_parse(c_bget(B, "meta.last_period")))

    def c_day(rec, field):
        val = _c_nodeval(rec.get(field))
        return _c_as_date(val) if val else None

    def c_map(k):
        """Карта лагов квартала прибыли k: (квартал решения, вычета, выплаты)."""
        q_dec = k + lags[c_qper(anchor, k)[1]]
        return q_dec, max(q_dec, k + reg_lag), max(q_dec, k + pay_lag)

    # закрыт ли квартал прибыли до якоря, решает факт (М§5.7.2)
    closed, hist_dps = [], {}
    for rec in A["div_history"]:
        per = _c_nodeval(rec.get("period"))
        if not per:
            raise ControlInputError("строка dividends.history без квартала прибыли period (прил. B)")
        k = c_qidx(anchor, *c_per_parse(per))
        dps = _c_nodeval(rec.get("dps"))
        if dps is None:
            dps = _c_nodeval(rec.get("dps_ordinary"))
        hist_dps[k] = None if dps is None else float(dps)
        decided = c_day(rec, "decided_date")
        if decided is not None and decided <= facts_date:
            closed.append(k)
    if not closed:
        raise ControlInputError("в dividends.history нет решения не позже даты фактов: p_last не определён (М§5.7.2)")
    p_last = max(closed)
    register = {}
    for rec in A["register"]:
        if rec.get("status", "declared") not in REGISTER_BINDING:
            continue
        per = _c_nodeval(rec.get("period"))
        if not per:
            raise ControlInputError("запись реестра без квартала прибыли (М§5.7.6)")
        k = c_qidx(anchor, *c_per_parse(per))
        decided = c_day(rec, "decided_date")
        if k > p_last and decided is not None and decided <= facts_date:
            raise ControlInputError(f"запись реестра {per}: решение раньше даты фактов, а строки в истории "
                                    f"дивидендов нет (М§5.7.6)")
        q_dec, q_reg, q_pay = c_map(k)
        record, pay, ex = c_day(rec, "record_date"), c_day(rec, "pay_date"), c_day(rec, "ex_date")
        q_cell = max(1, q_dec, c_qidx_of_date(anchor, decided)) if decided is not None else max(1, q_dec)
        register[k] = {"p": k, "period": str(per), "dps": float(_c_nodeval(rec["dps"])), "q_cell": q_cell,
                       "R": c_qidx_of_date(anchor, record) if record is not None else q_reg,
                       "P": c_qidx_of_date(anchor, pay) if pay is not None else q_pay, "ex": ex}
    opened, by_q = {}, {}
    for k in range(p_last + 1, last_q):
        yy, hh = c_qper(anchor, k)
        q_dec, q_reg, q_pay = c_map(k)
        rec = register.get(k)
        q_cell = rec["q_cell"] if rec is not None else max(1, q_dec)
        if q_cell > last_q:
            continue                                    # решение остаётся терминалу (М§7)
        ent = {"p": k, "period": f"{yy}Q{hh}", "year": yy, "h": hh, "q_cell": q_cell,
               "q_reg": max(q_cell, rec["R"] if rec is not None else q_reg),
               "q_pay": max(q_cell, rec["P"] if rec is not None else q_pay),
               "dps_register": None if rec is None else rec["dps"]}
        opened[k] = ent
        by_q.setdefault(q_cell, []).append(ent)
    # состояние якоря: объявленные и не выплаченные дивиденды закрытых кварталов прибыли
    queue0, seen, total = [], set(), 0.0
    for it in A["DP_declared"]:
        k = c_qidx(anchor, *c_per_parse(it["period"]))
        if k > p_last:
            raise ControlInputError(f"balance.dividends_payable_declared: период {it['period']} не закрыт (М§5.7.4)")
        if k in seen:
            raise ControlInputError(f"balance.dividends_payable_declared: период {it['period']} повторяется")
        seen.add(k)
        rec = register.get(k)
        _, q_reg, q_pay = c_map(k)
        queue0.append({"amt": it["amount"], "dec": 0, "reg": rec["R"] if rec is not None else q_reg,
                       "pay": max(1, rec["P"] if rec is not None else q_pay)})
        total += it["amount"]
    if total > A["DP"] + 1e-9:
        raise ControlInputError("сумма balance.dividends_payable_declared больше остатка дивидендов к выплате")
    A["divcal"] = {"p_last": p_last, "open": opened, "by_q": by_q, "register": register, "queue0": queue0,
                   "perm": A["DP"] - total, "hist_dps": hist_dps, "last_q": last_q, "closed": sorted(closed)}
    return A["divcal"]


def c_dpreg_anchor(B: dict, A: dict) -> float:
    """DPreg на якоре (М§4.11): дивиденды, вычтенные из BV якоря, но ещё не вычтенные из регуляторного
    капитала. Квартальный режим — суммы очереди вычетов состояния якоря; годовой — остаток дивидендов к
    выплате (объявлен в квартал собрания, отсечка — позже якоря)."""
    if not c_is_quarterly(B):
        return A["DP"]
    return sum(it["amt"] for it in c_div_calendar(B, A)["queue0"] if it["reg"] >= 1)


def c_div_base(ctx: dict, ni_all: dict, k: int) -> float:
    """База решения за квартал прибыли k (М§5.7.3): средняя базы W последних кварталов; прибыль квартала
    не позже якоря — факт, позже — ряд клетки; купон бессрочных инструментов — в квартале его выплаты."""
    B, A, anchor = ctx["B"], ctx["A"], ctx["anchor"]
    window = int(c_bopt(B, "dividends.policy.base_window_quarters", 1))
    if not 1 <= window <= 2 * QY:
        raise ControlInputError("dividends.policy.base_window_quarters вне 1…8 (М§5.7.1)")
    deduct = bool(c_bget(B, "dividends.policy.deduct_at1_after_tax"))
    total = 0.0
    for x in range(k - window + 1, k + 1):
        yq = c_qper(anchor, x)
        if yq not in ni_all:
            raise ControlInputError(f"нет прибыли акционеров квартала {yq[0]}Q{yq[1]} для базы дивиденда (М§5.7.3)")
        total += ni_all[yq]
        if deduct and yq[1] == A["cpn_quarter"]:
            total -= A["cpn_annual"] * (1.0 - c_traj_at(c_bget(B, "tax.statutory"), yq[0], yq[1]))
    return total / window


def c_payout_share(B: dict, year: int) -> float:
    """Доля выплаты года прибыли (М§5.2): clip(payout + payout_deviation, 0, 1)."""
    return min(1.0, max(0.0, c_traj_mean(c_bget(B, "dividends.policy.payout"), year, range(1, QY + 1))
                        + c_traj_mean(c_bget(B, "dividends.payout_deviation"), year, range(1, QY + 1))))


def c_min_dps_rule(B: dict, growth, quarterly: bool, years) -> object:
    """Жетон DPS (ключ dividends.min_dps, К1, решения № 3, Р5): траектория по году прибыли, ₽ на акцию, ≥ 0. Читается
    только в машине роста — при квартальном календаре и включённом ограничении роста; иначе ключ неактивного режима
    (не читается, отказа нет). Нет ключа — None (прежняя ветвь). Не траектория или значение < 0 в каком-либо году
    прибыли сетки — отказ."""
    if not quarterly or growth is None:
        return None
    node = c_bopt(B, "dividends") or {}
    if "min_dps" not in node:
        return None
    traj = node["min_dps"]
    if not (c_is_number(traj) or isinstance(traj, dict)):
        raise ControlInputError("dividends.min_dps: не траектория (М§0.4)")
    raw = [traj] if not isinstance(traj, dict) else [v for k, v in traj.items() if str(k) != "LT_from"]
    if any(not c_is_number(v) or float(v) < 0.0 for v in raw):
        raise ControlInputError("dividends.min_dps: значение не число или < 0 (М§5.7)")
    for y in years:
        if c_traj_mean(traj, y, range(1, QY + 1)) < 0.0:
            raise ControlInputError(f"dividends.min_dps < 0 в году {y} (М§5.7)")
    return traj


def c_closed_dps(ctx: dict, year: int) -> float:
    """DPS закрытых кварталов прибыли года (строки истории, М§5.7.5): квартал со своей строкой — её DPS (строка без
    числа — отказ), закрытый квартал без строки, покрытый строкой более позднего квартала, — ноль."""
    cal, anchor = ctx["divcal"], ctx["anchor"]
    total = 0.0
    for h in range(1, QY + 1):
        k = c_qidx(anchor, year, h)
        if k > cal["p_last"]:
            continue
        if k in cal["hist_dps"]:
            if cal["hist_dps"][k] is None:
                raise ControlInputError(f"строка dividends.history закрытого квартала {year}Q{h} без DPS (М§5.7.5)")
            total += cal["hist_dps"][k]
        elif not any(later > k for later in cal["closed"]):
            raise ControlInputError(f"нет строки dividends.history закрытого квартала {year}Q{h} (М§5.7.5)")
    return total


def c_token_need(*, min_dps: float, base_year: float, n_iss: float, n_c: float, closed_dps: float, prior_dps: float,
                 same_dps: float) -> dict:
    """Недостача года прибыли до жетона (К1): m_Y = min(min_dps(Y), max(0, база года) × 1000 / N_iss) — жетон не больше
    прибыли года на размещённую акцию (убыток — ноль); S_Y = DPS закрытых кварталов + DPS решений года в прошлых
    кварталах клетки + DPS решений года в этом квартале (у модели — доли базового дивиденда); need = max(0, m_Y − S_Y)
    × N_c,q / 1000 (млрд ₽)."""
    m_y = min(min_dps, max(0.0, base_year) * 1000.0 / n_iss)
    s_y = closed_dps + prior_dps + same_dps
    return {"m_Y": m_y, "S_Y": s_y, "need": max(0.0, m_y - s_y) * n_c / 1000.0}


def c_token_paid(need: float, h_floor: float, model_base: float) -> float:
    """Жетон решения-носителя (К1): need, если need > 0 и запас над требованием без запаса менеджмента при наименьшей
    доле прироста покрывает базовый дивиденд модели квартала и жетон; иначе 0 («иначе — по правилу», частичного жетона
    нет)."""
    return need if need > 0.0 and h_floor >= model_base + need else 0.0


def c_excess_share(B: dict, year: int) -> float:
    """ε года прибыли с линейным вводом (М§5.6)."""
    start = int(c_bnum(B, "dividends.excess.from_profit_year"))
    if year < start:
        return 0.0
    ramp = int(c_bnum(B, "dividends.excess.ramp_years"))
    if ramp < 1:
        raise ControlInputError("dividends.excess.ramp_years — целое ≥ 1 (М прил. A)")
    return c_bnum(B, "dividends.excess.epsilon") * min(1.0, (year - start + 1) / ramp)


def _c_req_glide(ctx: dict, s: str, k: int) -> tuple[float, float]:
    """Требования квартала k с глиссадой (М§4.13.1): req*_j = max по h = 0…H ( r_j,min(k+h, Q) − h × δ ).
    Без ограничения роста — требования без глиссады."""
    memo = ctx["glide_memo"]
    if (s, k) not in memo:
        B, rule = ctx["B"], ctx["growth"]
        ahead = rule["ahead"] if rule else 0
        step = rule["glide"] if rule else 0.0
        best20 = best11 = None
        for h in range(ahead + 1):
            yy, qq = c_qper(ctx["anchor"], min(k + h, ctx["Q"]))
            r20 = max(c_bnum(B, "dividends.policy.threshold"),
                      _c_floor(B, s, "n20_0", yy, qq) + c_bnum(B, "capital.mgmt_buffer.n20_0")) - h * step
            r11 = _c_floor(B, s, "n1_1", yy, qq) + c_bnum(B, "capital.mgmt_buffer.n1_1") - h * step
            best20 = r20 if best20 is None else max(best20, r20)
            best11 = r11 if best11 is None else max(best11, r11)
        memo[(s, k)] = (best20, best11)
    return memo[(s, k)]


def _c_bisect(fn, lo: float, hi: float) -> float:
    """Корень невозрастающей функции на отрезке делением пополам: fn(lo) ≥ 0 > fn(hi); возвращает
    наибольшую точку с fn ≥ 0 (в пределах сходимости)."""
    for _ in range(FIT_ITER):
        mid = (lo + hi) / 2.0
        if fn(mid) >= 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= PLAN_TOL:
            break
    return lo


def _c_quarter_capital(ctx: dict, s: str, y: int, h: int, R: float, ni_q: dict):
    """Нормативы конца квартала (y, h) как функция капитала, DPreg и RWA (М§4.11–§4.12): всё, что от них
    не зависит (вычеты якоря, инструменты, неаудированная прибыль, поправки, требования), считается один
    раз на квартал. Возвращает функцию (bv, dpreg, rwa) → нормативы и требования."""
    B = ctx["B"]
    keep = (1.0 - c_bnum(B, "capital.n20.fvoci_recognition")) * R
    ded20, ded11 = c_bnum(B, "capital.n20.deductions_anchor"), c_bnum(B, "capital.n11.deductions_anchor")
    extra20 = ctx["A"]["AT1"] + c_traj_at(c_bget(B, "capital.n20.t2"), y, h)
    cut = [int(c) for c in c_bget(B, "capital.n11.audit_cutoffs")]
    e_q = _c_unaudited_quarters(cut, y, h)
    if any(yq not in ni_q for yq in e_q):
        raise ControlInputError(f"нет прибыли кварталов для E_q на {y}Q{h}")
    e_un = sum(ni_q[yq] for yq in e_q)
    e_out = e_un if e_un > 0.0 else 0.0
    adj20 = c_bnum(B, "capital.n20.gap_pp") - c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), y, h)
    adj11 = c_bnum(B, "capital.n11.gap_pp") - c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n1_1"), y, h)
    fl20, fl11 = _c_floor(B, s, "n20_0", y, h), _c_floor(B, s, "n1_1", y, h)
    req20 = max(c_bnum(B, "dividends.policy.threshold"), fl20 + c_bnum(B, "capital.mgmt_buffer.n20_0"))
    req11 = fl11 + c_bnum(B, "capital.mgmt_buffer.n1_1")
    rwa0 = ctx["rwa0"]

    def c_ratios(bv: float, dpreg: float, rwa: float) -> dict:
        bvreg = bv + dpreg - keep
        grow = rwa / rwa0
        k20 = bvreg - ded20 * grow + extra20
        k11 = bvreg - e_out - ded11 * grow
        return {"k20": k20, "k11": k11, "n20": k20 / rwa + adj20, "n11": k11 / rwa + adj11,
                "n11_star": (k11 + e_out) / rwa + adj11, "e_unaudited": e_un, "floor20": fl20, "floor11": fl11,
                "req20": req20, "req11": req11}

    return c_ratios


def _c_capital_pass(ctx: dict, cell: dict, st: dict, i: int, row: dict) -> tuple[dict, dict]:
    """Квартальный проход капитала внутри года (М§17; порядок М§5.7.4 и §4.13.2).

    По кварталам года: остатки кредитных книг, баланс и RWA на конец квартала, нормативы, требование с
    глиссадой, решения о дивиденде, доля прироста λ и навёрстывание. Совокупный доход и прибыль кварталов
    — профиль годовой строки row (её ОПУ посчитаны годовым шагом при прежнем плане года). Долю λ и долю
    навёрстывания θ контрольная модель ищет делением отрезка пополам по невязке условия роста, а не
    закрытой формулой с шагом секущей. Возвращает новый план года и выходы кварталов."""
    B, A, p = ctx["B"], ctx["A"], ctx["periods"][i]
    r, s = cell["regime"], cell["scenario"]
    y, qs, n = p["year"], p["quarters"], p["n"]
    loans, fv, oaf, rule, cal = ctx["loans"], ctx["fv"], ctx["oaf"], ctx["growth"], ctx["divcal"]
    allow, gr, drv = ctx.get("allow"), ctx.get("guar"), ctx.get("driven")
    cash = ctx.get("cash")
    min_dps = ctx.get("min_dps")
    dps_memo = dict(st.get("dps_year", {}))             # К1: DPS решений клетки по годам прибыли (память прохода)
    k_first = c_qidx(ctx["anchor"], y, qs[0])
    if drv:
        # К6: ведомые книги и уровни их драйверов на начало года (конец прошлого) — продолжаются квартал за кварталом
        wage_y = ctx["wv"][cell["world"]][i]["wage_growth"]
        start = {**{b: path[0] for b, path in row["nb_ends"].items()}, **{b: st["E"][b] for b in ctx["loans"]}}
        drv_prev = {b: st["E"][b] for b in drv}
        lev_prev = {b: c_base_level(d["spec"], start, loans=ctx["loans"],
                                    biz=[x for x in ctx["biz"] if x not in drv], assets=ctx["loans"],
                                    nominal=st.get("nom", 1.0)) for b, d in drv.items()}
    ni_all = {**st["ni_q"], **row["ni_q"]}
    m = row["m_q"]
    n_out, n_iss = A["N_out"], A["N_iss"]
    wtf = ctx["wtf"]                                    # база опта: структурная доля (К3) или доля якоря
    k6_out = ctx.get("k6_out") or []                    # Р11-2: книги К6 вне базы опта (при funds_scope: clients)
    r_oa, r_ol = c_bnum(B, "volumes.other_assets_to_loans"), c_bnum(B, "volumes.other_liabilities_to_loans")
    r_al = c_bnum(B, "credit.allowance_ratio")
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    ssl = c_bnum(B, "volumes.securities_share_of_liquid")
    outside = A["AT1"] + A["NCI"]
    skip_year = (r == R_CRISIS and y == ctx["shock_year"] and bool(c_bget(B, "dividends.crisis.skip_in_shock_year")))
    catch_on = bool(c_bget(B, "dividends.crisis.catch_up"))
    can_cut = rule is not None and rule["lam_min"] < 1.0 and any(m[b] > 0.0 for b in loans)
    E_prev, E_pot = {b: st["E"][b] for b in loans}, dict(st["Epot"])
    bv_prev, deferred, queue = st["BV"], st["D"], [dict(it) for it in st["dq"]]
    paths = {b: [st["E"][b]] for b in loans}
    year_divs, records, quarters = [], [], []
    bb = ctx.get("bb")
    if bb is not None:
        # выкуп по цене мира (М3): путь акций и форвард цены своей клетки; решения квартала — на акциях клетки
        n_c, p_plus = st["n_c"], st["p_plus"]
        label = "/".join((cell["world"], r, s))
    for j, q in enumerate(qs):
        k = k_first + j
        for b in loans:
            E_pot[b] = E_pot[b] * (1.0 + m[b])
        bb_amt = 0.0
        if bb is not None:
            bb_amt = row["bb_q"][j]
            p_bar = c_bb_price(bb, cell["world"], k, p_plus)
            n_c = c_bb_shares(n_c, bb_amt, p_bar, label, k)
            n_out = n_c
        todo = sorted(cal["by_q"].get(k, []), key=lambda e: e["p"])
        fixed = [{"amt": e["dps_register"] * n_out / 1000.0, "dec": k, "reg": e["q_reg"], "pay": e["q_pay"],
                  "p": e["p"]} for e in todo if e["dps_register"] is not None]
        own, calc_of = [], {}             # решения самой клетки (без записи реестра)
        for e in todo:
            base = c_div_base(ctx, ni_all, e["p"])
            pool = c_payout_share(B, e["year"]) * max(0.0, base)
            calc_of[e["p"]] = {"ent": e, "base": base, "pool": pool, "want": pool * n_out / n_iss}
            if e["dps_register"] is None:
                own.append(calc_of[e["p"]])
        live = [] if skip_year else own
        want_sum = sum(x["want"] for x in live)
        req20_g, req11_g = _c_req_glide(ctx, s, k)
        ratios = _c_quarter_capital(ctx, s, y, q, row["R_q"][j], ni_all)
        funds = row["fr_path"][j + 1] + row["cf_path"][j + 1]
        liab_fixed = funds + wtf * funds + outside

        def c_quarter_end(lam, extra_loans, model_divs):
            """Конец квартала на копии состояния: кредитные книги при доле прироста lam и добавке
            навёрстывания, дивиденды квартала — записи реестра и model_divs."""
            Eq = {b: E_prev[b] * (1.0 + (lam if m[b] > 0.0 else 1.0) * m[b]) + extra_loans.get(b, 0.0)
                  for b in loans}
            total = sum(Eq.values())
            liab_q, funds_q, drv_q, lev_q = liab_fixed, funds, None, None
            cl_q = funds                    # средства клиентов базы опта К3 (Р11-2: при clients — без книг К6)
            if drv:
                # К6: ведомые книги — за уровнем базы строки на конце квартала (кредитные книги квартала при доле
                # прироста lam, прочие статьи — концы кварталов годовой строки); средства клиентов — с ними
                ends = {**{b: path[j + 1] for b, path in row["nb_ends"].items() if b not in drv}, **Eq}
                drv_q, lev_q = {}, {}
                for b, d in drv.items():
                    lev_q[b] = c_base_level(d["spec"], ends, loans=loans, biz=[x for x in ctx["biz"] if x not in drv],
                                            assets=loans, nominal=row["nom_q"][j])
                    if lev_q[b] <= 0.0:
                        raise ControlInputError(f"уровень драйвера книги {b} ≤ 0: клетка "
                                                + "/".join((cell["world"], r, s)) + f", {y}Q{q} (М§4.3)")
                    if ctx.get("k6_line"):
                        # Р10-5: формой строки — Ψ г/г от D принятых остатков квартала к записи пути клетки
                        drv_q[b] = A["E0"][b] * c_driven_psi(ctx, st, b, d, y, q, lev_q[b], wage_y[j])
                    else:
                        drv_q[b] = c_driven_path(d, drv_prev[b], [lev_prev[b], lev_q[b]], [wage_y[j]],
                                                 c_driven_roots(d, y, [q]))[-1]
                cl_q = row["fr_path"][j + 1] + sum(path[j + 1] for b, path in row["nb_ends"].items()
                                                   if b in ctx["biz"] and b not in drv)
                funds_q = cl_q + sum(drv_q.values())
                if not k6_out:
                    cl_q = funds_q          # без ключа Р11-2 база опта — все средства, с книгами К6 (прежняя строка)
                liab_q = funds_q + wtf * cl_q + outside
            ac = total - sum(fv[b] * Eq[b] for b in fv) if fv else total
            decided = fixed + model_divs
            bv = bv_prev + row["ci_q"][j] - sum(d["amt"] for d in decided)
            if bb_amt:
                bv -= bb_amt                    # выкуп — из капитала в квартале покупки, рубль в рубль
            dp, dpreg = st["dp_perm"], 0.0
            for it in queue + decided:
                if it["pay"] > k:
                    dp += it["amt"]
                if it["reg"] > k:
                    dpreg += it["amt"]
            cash_q = None
            if cash is None:
                oa = r_oa * total + oaf
            else:
                # К8: деньги за уровнем драйвера на конце квартала — кредитные книги квартала при доле прироста lam,
                # ведомые книги К6 квартала, прочие статьи — концы кварталов годовой строки
                lev_c = c_cash_level(cash, {**{b: path[j + 1] for b, path in row["nb_ends"].items()}, **(drv_q or {}),
                                            **Eq})
                if lev_c <= 0.0:
                    raise ControlInputError("уровень драйвера денег ≤ 0: клетка " + "/".join((cell["world"], r, s))
                                            + f", {y}Q{q} (М§4.3)")
                cash_q = c_cash_c(cash, k) * lev_c        # доля книги (Р6-1) — c_k квартала; прежняя ветвь — c
                oa = (r_oa - c_cash_cut(cash, k)) * total + cash_q + oaf
            assets_nb = (total - r_al * ac + oa if allow is None
                         else total - c_allowance_of(allow, Eq, ac) + oa)     # К7: резерв по книгам квартала
            la = liab_q + r_ol * total + dp + bv - assets_nb
            la = max(la, m_liq * assets_nb / (1.0 - m_liq))
            bal = dict(Eq)
            bal[SECURITIES], bal[LIQUIDITY] = ssl * la, (1.0 - ssl) * la
            g_q = None
            if gr is not None:
                # составляющая RWA гарантий (К5) по драйверу на конце квартала: книги квартала, прочие статьи —
                # концы кварталов годовой строки, опт — структурная часть и добор до минимума ликвидности
                la_min = m_liq * assets_nb / (1.0 - m_liq)
                la_free = liab_q + r_ol * total + dp + bv - assets_nb
                ends = {**{b: path[j + 1] for b, path in row["nb_ends"].items()}, **(drv_q or {}), **bal,
                        WHOLESALE: wtf * cl_q + max(0.0, la_min - la_free)}
                g_q = c_guarantee_amount(ctx, cell, st, gr, y, qs, j, ends, row["nom_q"][j], row["fees_q"])
            rwa = _c_rwa_of(ctx, r, y, q, bal, oa, row["dn_q"][j], row["xf_q"][j], guar=g_q, cash=cash_q,
                            disp=c_cash_disp(cash, k, total))
            cp = ratios(bv, dpreg, rwa)
            if rule is None:
                # без ограничения роста запас — по отчётным нормативам и требованию без глиссады (М§5.7.4)
                room = ((cp["n20"] - cp["req20"]) * rwa, (cp["n11"] - cp["req11"]) * rwa)
            else:
                room = ((cp["n20"] - req20_g) * rwa, (cp["n11_star"] - req11_g) * rwa)
            return {"E": Eq, "loans": total, "bv": bv, "dp": dp, "dpreg": dpreg, "rwa": rwa, "cap": cp,
                    "room": room, "iea": total + la, "guar": g_q, "driven": drv_q, "levels": lev_q, "cash": cash_q}

        full = c_quarter_end(1.0, {}, [])
        lam, add, final = 1.0, {}, full
        if rule is None:
            h_ref = min(full["room"])
        else:
            low = c_quarter_end(rule["lam_min"], {}, []) if can_cut else full
            h_ref = min(low["room"]) if rule["order"] == ORDER_DIV_FIRST else min(full["room"])
        div_base = min(want_sum, max(0.0, h_ref)) if want_sum else 0.0
        token, carrier, tok = 0.0, None, None
        if min_dps is not None:
            # К1, жетон DPS (М§4.13.2 п. 2а): носитель — последнее неотменённое решение модели квартала за четвёртый
            # квартал прибыли; запас — над требованием без запаса менеджмента и глиссады при наименьшей доле прироста и
            # записях реестра (оценка low); жетон уступает не дивиденду, а росту
            tops = [x for x in live if x["ent"]["h"] == QY]
            if tops:
                carrier = tops[-1]
                yc = carrier["ent"]["year"]
                base_y = sum(c_div_base(ctx, ni_all, c_qidx(ctx["anchor"], yc, h)) for h in range(1, QY + 1))
                same = sum((div_base * x["want"] / want_sum if want_sum else 0.0) for x in live
                           if x["ent"]["year"] == yc) * 1000.0 / n_out
                same += sum(e["dps_register"] for e in todo if e["dps_register"] is not None and e["year"] == yc)
                tok = c_token_need(min_dps=c_traj_mean(min_dps, yc, range(1, QY + 1)), base_year=base_y, n_iss=n_iss,
                                   n_c=n_out, closed_dps=c_closed_dps(ctx, yc), prior_dps=dps_memo.get(yc, 0.0),
                                   same_dps=same)
                ev = low
                cpl = ev["cap"]
                req0_20 = max(c_bnum(B, "dividends.policy.threshold"), cpl["floor20"])
                tok["h_floor"] = min((cpl["n20"] - req0_20) * ev["rwa"], (cpl["n11_star"] - cpl["floor11"]) * ev["rwa"])
                tok["eval"] = {"n20": cpl["n20"], "n11_star": cpl["n11_star"], "rwa": ev["rwa"], "loans": ev["loans"],
                               "floor20": cpl["floor20"], "floor11": cpl["floor11"]}
                tok["model_base"] = div_base if want_sum else 0.0
                token = c_token_paid(tok["need"], tok["h_floor"], tok["model_base"])
                tok["token"] = token
        if rule is not None:
            # ι: часть базового дивиденда, чей вычет из регуляторного капитала приходится на этот квартал
            same_q = sum(div_base * x["want"] / want_sum for x in live if x["ent"]["q_reg"] == k) if want_sum else 0.0
            if token and carrier["ent"]["q_reg"] == k:
                same_q += token                         # К1: жетон носителя — в условии роста своего квартала вычета
            g_full = [h - same_q for h in full["room"]]
            g_low = [h - same_q for h in low["room"]]
            if can_cut and min(g_full) < 0.0:
                shares = []
                for a in range(len(g_full)):
                    if g_full[a] >= 0.0 or g_low[a] - g_full[a] <= PLAN_TOL:
                        shares.append(1.0)              # норматив не нарушен или урезание его не поправляет
                    elif g_low[a] <= 0.0:
                        shares.append(rule["lam_min"])
                    else:
                        shares.append(_c_bisect(lambda x, a=a: c_quarter_end(x, {}, [])["room"][a] - same_q,
                                                rule["lam_min"], 1.0))
                lam = min(shares)
                final = full if lam == 1.0 else low if lam == rule["lam_min"] else c_quarter_end(lam, {}, [])
            if lam == 1.0 and min(g_full) >= 0.0 and rule["catch_up"] > 0.0:
                # навёрстывание роста (М§4.13.2 п. 5): доля κ/4 разрыва с потенциальным путём, общей долей θ
                gap = {b: max(0.0, E_pot[b] - full["E"][b]) for b in loans}
                if any(v > 0.0 for v in gap.values()):
                    whole = {b: rule["catch_up"] / QY * gap[b] for b in loans}
                    tried = c_quarter_end(1.0, whole, [])
                    if min(tried["room"]) - same_q >= 0.0:
                        add, final = whole, tried
                    else:
                        theta = _c_bisect(lambda x: min(c_quarter_end(
                            1.0, {b: x * whole[b] for b in loans}, [])["room"]) - same_q, 0.0, 1.0)
                        add = {b: theta * whole[b] for b in loans}
                        final = c_quarter_end(1.0, add, [])
        h_fin = min(final["room"])
        cut = bool(live) and div_base < want_sum - 1e-9
        # догоняющая выплата и избыток — раз в год, в решении за четвёртый квартал прибыли, при λ* = 1
        catch = excess = 0.0
        top = [x for x in live if x["ent"]["h"] == QY]
        if top and lam == 1.0:
            if catch_on:
                catch = min(deferred, max(0.0, h_fin - div_base - token))
            excess = c_excess_share(B, top[0]["ent"]["year"]) * max(0.0, h_fin - div_base - token - catch)
        model_divs = []
        for e in todo:
            calc = calc_of[e["p"]]
            rec = {"period": e["period"], "year": e["year"], "h": e["h"], "q": k, "base": calc["base"],
                   "want": calc["want"], "headroom": h_ref, "headroom_final": h_fin, "base_div": 0.0,
                   "catch": 0.0, "excess": 0.0, "cut": False, "lam": lam,
                   "dps_policy": calc["pool"] * 1000.0 / n_iss, "deferred_before": deferred}
            if e["dps_register"] is not None:
                rec.update(source="register", div=e["dps_register"] * n_out / 1000.0)
                rec["base_div"] = rec["div"]
            elif skip_year:
                rec.update(source="crisis_skip", div=0.0)
                if catch_on:
                    deferred += calc["want"]
            else:
                rec["base_div"] = div_base * calc["want"] / want_sum if want_sum else 0.0
                if e["h"] == QY:
                    rec.update(catch=catch, excess=excess)
                    deferred -= catch
                if min_dps is not None:
                    rec["token"] = token if calc is carrier else 0.0
                    if calc is carrier:
                        rec["token_rule"] = dict(tok)
                rec.update(source="policy", cut=cut,
                           div=rec["base_div"] + rec.get("token", 0.0) + rec["catch"] + rec["excess"])
                if rec["div"]:
                    model_divs.append({"amt": rec["div"], "dec": k, "reg": e["q_reg"], "pay": e["q_pay"], "p": e["p"]})
            rec.update(dps=rec["div"] * 1000.0 / n_out, deferred_after=deferred)
            records.append(rec)
        if min_dps is not None:
            for rec in records[len(records) - len(todo):]:
                if rec["source"] in ("policy", "register"):
                    dps_memo[rec["year"]] = dps_memo.get(rec["year"], 0.0) + rec["dps"]
        end = c_quarter_end(lam, add, model_divs)
        cp = end["cap"]
        E_prev, bv_prev = end["E"], end["bv"]
        if drv:
            drv_prev, lev_prev = end["driven"], end["levels"]
        decided = fixed + model_divs
        year_divs.extend(decided)
        queue = [it for it in queue + decided if it["pay"] > k or it["reg"] > k]
        for b in loans:
            paths[b].append(end["E"][b])
        quarters.append({"q": k, "lam": lam, "loans": end["loans"], "loans_potential": sum(E_pot.values()),
                         "catch_up": sum(add.values()), "div_model": sum(d["amt"] for d in model_divs),
                         "div": sum(d["amt"] for d in decided), "bv": end["bv"], "rwa": end["rwa"],
                         "n20": cp["n20"], "n11": cp["n11"], "n11_star": cp["n11_star"],
                         "req20": cp["req20"], "req11": cp["req11"], "req20_glide": req20_g,
                         "req11_glide": req11_g, "dp": end["dp"], "dpreg": end["dpreg"],
                         "headroom": h_ref, "headroom_final": h_fin, "iea": end["iea"]})
        if gr is not None:
            quarters[-1].update(guar=end["guar"], rwa_guar=end["guar"] * row["dn_q"][j] * row["xf_q"][j]
                                * c_rwa_mult(ctx, r, y, q))
        if drv:
            quarters[-1]["driven"] = dict(end["driven"])
            if any("root" in d for d in drv.values()) or ctx.get("k6_line"):
                # Р9-1, Р10-5: уровень базы строки D ведомых книг на конце квартала — печать при ключе корня или формы
                # строки (без ключей поля нет)
                quarters[-1]["driven_level"] = dict(end["levels"])
        if cash is not None:
            quarters[-1]["cash"] = end["cash"]
        if bb is not None:
            # дивиденд квартала на внешнюю акцию d_q = Div_q × 1000 / N_c,q и форвард цены после него
            d_ext = sum(d["amt"] for d in decided) * 1000.0 / n_c
            p_plus = c_bb_forward(bb, cell["world"], k, p_plus, d_ext)
            quarters[-1].update(bb=bb_amt, p_bar=p_bar, n_out=n_c, d_ext=d_ext, p_plus=p_plus)
    plan = {"loans": paths, "divs": year_divs}
    info = {"quarters": quarters, "records": records, "deferred": deferred, "Epot": E_pot}
    if min_dps is not None:
        info["dps_year"] = dps_memo
    if bb is not None:
        info.update(n_c=n_c, p_plus=p_plus)
    return plan, info


def _c_plan_gap(old: dict, new: dict) -> float:
    """Наибольшее расхождение двух планов года: остатки кредитных книг — долей, дивиденды — млрд ₽."""
    if old["loans"] is None or len(old["divs"]) != len(new["divs"]):
        return float("inf")
    gap = 0.0
    for b, path in new["loans"].items():
        for a, c in zip(old["loans"][b], path):
            gap = max(gap, abs(c - a) / max(abs(c), 1.0))
    for a, c in zip(old["divs"], new["divs"]):
        if (a["dec"], a["reg"], a["pay"]) != (c["dec"], c["reg"], c["pay"]):
            return float("inf")
        gap = max(gap, abs(c["amt"] - a["amt"]))
    return gap


def _c_year_quarterly(ctx: dict, cell: dict, st: dict, i: int) -> tuple[dict, dict]:
    """Год ветви с квартальным проходом капитала (М§17): годовые строки ОПУ при плане года (пути кредитных
    книг и решения о дивиденде по кварталам) и квартальный проход, который этот план пересчитывает на
    профиле прибыли годовой строки, — до совпадения плана. Возвращает (состояние, строка)."""
    p = ctx["periods"][i]
    plan = {"loans": None, "divs": []}
    for turn in range(FIT_ITER):
        nst, row = _c_period(ctx, cell, st, i, 0.0, plan)
        new_plan, info = _c_capital_pass(ctx, cell, st, i, row)
        gap = _c_plan_gap(plan, new_plan)
        if gap <= PLAN_TOL:
            break
        if turn >= FIT_ITER // 2 and plan["loans"] is not None and math.isfinite(gap):
            # медленная сходимость: полшага к новому плану
            for b, path in new_plan["loans"].items():
                new_plan["loans"][b] = [(a + c) / 2.0 for a, c in zip(plan["loans"][b], path)]
        plan = new_plan
    qr = info["quarters"]
    A, y = ctx["A"], p["year"]
    pot_end, act_end = qr[-1]["loans_potential"], qr[-1]["loans"]
    if i == 0:
        # за год якоря знаменатель роста — факт конца прошлого года (М§4.13.3)
        prev = A["history"].get(f"{y - 1}Q{QY}", {}).get(LINK_BASES[0]) if p["stub"] else sum(st["Epot"].values())
        pot_prev = act_prev = None if prev is None else float(prev)
    else:
        pot_prev, act_prev = sum(st["Epot"].values()), sum(st["E"][b] for b in ctx["loans"])
    row.update(quarters=qr, decisions_q=info["records"], plan_gap=gap, plan_turns=turn + 1,
               lam_q=[x["lam"] for x in qr], lam_min=min(x["lam"] for x in qr),
               catch_up=sum(x["catch_up"] for x in qr), div_model=sum(x["div_model"] for x in qr),
               loans_potential=pot_end, cut_share=1.0 - act_end / pot_end,
               growth_potential=None if pot_prev is None else pot_end / pot_prev - 1.0,
               growth_actual=None if act_prev is None else act_end / act_prev - 1.0,
               req20_glide=qr[-1]["req20_glide"], req11_glide=qr[-1]["req11_glide"],
               potential_end=dict(info["Epot"]), D=info["deferred"])
    nst["Epot"], nst["D"] = info["Epot"], info["deferred"]
    if "dps_year" in info:
        nst["dps_year"] = info["dps_year"]              # К1: память DPS по годам прибыли — в следующий год клетки
    if "n_c" in info:
        # выкуп: акции клетки и форвард цены — в состояние следующего года; ряды кварталов — оценке
        nst["n_c"], nst["p_plus"] = info["n_c"], info["p_plus"]
        row.update(n_c_q=[x["n_out"] for x in qr], d_ext_q=[x["d_ext"] for x in qr],
                   p_bar_q=[x["p_bar"] for x in qr], p_plus_q=[x["p_plus"] for x in qr])
    return nst, row


def c_profit_years(ctx: dict, made: list[dict]) -> dict:
    """Дивиденд и DPS по годам прибыли (М§5.7.5): сумма четырёх кварталов прибыли года — открытый квартал
    по решению клетки, закрытый — по строке истории. Закрытый квартал без своей строки, покрытый строкой
    истории более позднего квартала (решение «за девять месяцев» — одна строка, период — последний из
    кварталов), даёт ноль: его дивиденд — в той строке. Строка без числа DPS — отказ (null ≠ 0). Год входит,
    если хотя бы один его квартал открыт и ни одно его решение не лежит за сеткой."""
    A, cal, anchor = ctx["A"], ctx["divcal"], ctx["anchor"]
    by_p = {c_qidx(anchor, *c_per_parse(d["period"])): d for d in made}
    out = {}
    for year in sorted({e["year"] for e in cal["open"].values()}):
        ks = [c_qidx(anchor, year, h) for h in range(1, QY + 1)]
        if any(k > cal["p_last"] and k not in cal["open"] for k in ks):
            continue
        parts, dps, div, policy = {}, 0.0, 0.0, 0.0
        for k in ks:
            per = f"{year}Q{c_qper(anchor, k)[1]}"
            if k in by_p:
                parts[per] = by_p[k]
                dps += by_p[k]["dps"]
                div += by_p[k]["div"]
                policy += by_p[k]["dps_policy"]
            else:
                if k in cal["hist_dps"]:
                    hist = cal["hist_dps"][k]
                    if hist is None:
                        raise ControlInputError(f"строка dividends.history закрытого квартала {per} без DPS (М§5.7.5)")
                elif any(later > k for later in cal["closed"]):
                    hist = 0.0                          # покрыт строкой истории более позднего квартала
                else:
                    raise ControlInputError(f"нет строки dividends.history закрытого квартала {per} (М§5.7.5)")
                dps += hist
                policy += hist
                div += hist * A["N_out"] / 1000.0
        last_q = max((d["q"] for d in parts.values()), default=0)
        out[year] = {"kind": "quarterly", "div": div, "dps": dps, "dps_policy": policy, "quarters": parts,
                     "decision_year": c_qper(anchor, last_q)[0],
                     "cut": any(d["cut"] for d in parts.values())}
    return out


def c_cell_annual(ctx: dict, world: str, regime: str, scenario: str) -> dict:
    """Клетка (W, r, s): годовой путь, дивиденды, V_RI и V_DDM (М§6), терминал (М§7)."""
    cell = {"world": world, "regime": regime, "scenario": scenario}
    bb = ctx.get("bb")
    if bb is not None and bb["rule"] == BB_CELL:
        cell["bb_start"], cell["bb_turns"] = c_bb_fixed_point(ctx, cell)
    path = _c_cell_path(ctx, cell)
    out = {**cell, **path, "years": [p["year"] for p in ctx["periods"]]}
    out.update(_c_value_cell(ctx, cell, path["rows"], path["decisions"]))
    return out


def c_bb_fixed_point(ctx: dict, cell: dict) -> tuple[float, int]:
    """Справочное правило выкупа cell_value (М3): P_s — неподвижная точка «цена = стоимость клетки на оставшуюся
    акцию на дату книги». P_s := P_b; повтор: путь клетки от P_s и оценка на часах даты книги → S_c; P_s := S_c — до
    |ΔP_s| ≤ 1e-9 × P_s, не больше 30 оборотов (иначе отказ). Возвращает (P_s, число оборотов)."""
    bb = ctx["bb"]
    at_book = {**ctx, "clock": bb["clock_b"], "disc": bb["disc_b"]}
    p = bb["p_book"]
    for turn in range(1, FIT_ITER // 2 + 1):
        path = _c_cell_path(ctx, {**cell, "bb_start": p})
        s = _c_value_cell(at_book, cell, path["rows"], path["decisions"])["s_price"]
        if abs(s - p) <= PLAN_TOL * abs(p):
            return s, turn
        p = s
    raise ControlInputError(f"цена выкупа «по стоимости клетки» не сошлась за {FIT_ITER // 2} оборотов: клетка "
                            + "/".join((cell["world"], cell["regime"], cell["scenario"])) + " (М§5.6)")


def _c_value_cell(ctx: dict, cell: dict, rows: list[dict], decisions: dict) -> dict:
    B, A = ctx["B"], ctx["A"]
    ck, periods = ctx["clock"], ctx["periods"]
    df = ctx["disc"][cell["world"]]
    p0 = ck["p0"]
    bv_prev = A["BV"] if p0 == 0 else rows[p0 - 1]["bv"]
    r0 = rows[p0]
    # капитал на дату оценки (М§6.1): закрытые кварталы периода p0 целиком и доля e_q квартала q0 —
    # по квартальному профилю CI; дивиденд — вычтен, если конец квартала решения не позже v (М§0.2)
    whole = int(ck["pos"])
    ci_to_v = sum(r0["ci_q"][:whole]) + ((ck["pos"] - whole) * r0["ci_q"][whole] if whole < len(r0["ci_q"]) else 0.0)
    bv_v = bv_prev + ci_to_v - sum(amt for j, amt in r0["div_list"] if ck["t_start"][p0] + 0.25 * (j + 1) <= 0.0)
    bb_on = ctx.get("bb") is not None
    if bb_on:
        # выкуп — распределение акционерам в квартале покупки, датирован его концом, как дивиденд (М§5.6)
        bv_v -= sum(x for j, x in enumerate(r0["bb_q"]) if ck["t_start"][p0] + 0.25 * (j + 1) <= 0.0)
    v_ri, v_ddm, pv_ri = bv_v, 0.0, 0.0
    s_items, pv_bb = [], 0.0
    for i in range(p0, len(periods)):
        row = rows[i]
        te = ck["tau_end"][i]
        d_end = df(te)
        corr = 0.0
        for j, div in row["div_list"]:
            # дивиденд датируется концом квартала решения; решений в году — от нуля до нескольких (М§6.3)
            ta = ck["t_start"][i] + 0.25 * (j + 1)
            if ta > 0.0:
                v_ddm += div * df(ta)
                corr += div * (df(ta) / d_end - 1.0)
                if bb_on:
                    s_items.append((df(ta), div, row["n_c_q"][j]))         # d_q — на акцию, оставшуюся в квартале
        if bb_on:
            for j, x in enumerate(row["bb_q"]):
                ta = ck["t_start"][i] + 0.25 * (j + 1)
                if x and ta > 0.0:
                    v_ddm += x * df(ta)
                    corr += x * (df(ta) / d_end - 1.0)
                    pv_bb += x * df(ta)
        if i == p0:
            k = 1.0 / d_end - 1.0
            ri = row["ci"] - ci_to_v - k * bv_v + corr
        else:
            k = df(ck["tau_end"][i - 1]) / d_end - 1.0
            ri = row["ci"] - k * rows[i - 1]["bv"] + corr
        row["k"], row["ri"] = k, ri
        pv_ri += ri * d_end
    last = rows[-1]
    tl = ck["tau_end"][len(periods) - 1]
    yl = periods[-1]["year"]
    mult = c_bnum(B, "valuation.terminal.excess_capital_multiple")
    n20_t, n11_t = last["n20"], last["n11_star"]
    if last["dpreg"]:
        # нормативы терминала — без дивидендов, вычтенных из BV, но ещё не из регуляторного капитала (М§7)
        n20_t, n11_t = n20_t - last["dpreg"] / last["rwa"], n11_t - last["dpreg"] / last["rwa"]
    x_t = mult * min((n20_t - last["req20"]) * last["rwa"],
                     (n11_t - last["req11"]) * last["rwa"])
    bv_star = last["bv"] - x_t
    k_t = df(tl) / df(tl + 1.0) - 1.0
    g_raw = c_g_terminal(B, cell["world"])
    g_t = min(g_raw, k_t - 0.0001)
    # Р11-3: при pnl.nci_real доля НДУ не читается — терминал вычитает NCI_L (номинал мира года L; ν_L не множит)
    nci_l = None if ctx.get("nci_real") is None else last["nci"]
    nci = c_bnum(B, "pnl.nci_share") if nci_l is None else 0.0
    # Доход на избыток — по маржинальной ставке балансирующих статей (М§7). Избыток: пока минимум
    # ликвидности не связывает — смесь доходностей бумаг и ликвидности на конце Q в их долях в LA,
    # дальше — ставка опта. Порог — не запас HLA, а H* = HLA / (1 − m): изъятый капитал уменьшает и LA, и
    # активы, от которых считается минимум. Недостаток — зеркально: добавленный капитал сначала гасит
    # добор опта WT (если минимум связывает), остальное ложится в балансирующие активы по смеси.
    m_liq = c_bnum(B, "volumes.liquid_min_share")
    hla = max(0.0, last["securities"] + last["liquidity"] - m_liq * last["assets"])
    h_star = hla / (1.0 - m_liq)
    wt = max(0.0, last["wholesale_extra"])
    sec = c_bnum(B, "volumes.securities_share_of_liquid")
    y_bal = sec * last["y_sec_end"] + (1.0 - sec) * last["y_liq_end"]
    c_wh, pbt_l, stat = last["c_wh_end"], last["pbt"], None
    if ctx.get("stationary"):
        # терминал от стационарных ставок (К4): PBT года L + ΔNII*_L, ставки балансирующих статей за T — цели года L
        # (ставка конца года годовой агрегации при ρ = 1); явные годы не меняются
        tg = last["stationary"]["targets"]
        stat = {"d_nii_l": last["stationary"]["d_nii"], "y_bal_lagged": y_bal, "c_wh_lagged": c_wh,
                "y_bal": sec * tg[SECURITIES] + (1.0 - sec) * tg[LIQUIDITY], "c_wh": tg[WHOLESALE]}
        y_bal, c_wh, pbt_l = stat["y_bal"], stat["c_wh"], pbt_l + stat["d_nii_l"]
    if x_t > 0.0:
        y_x = y_bal * min(x_t, h_star) + c_wh * max(0.0, x_t - h_star)
    else:
        y_x = -(c_wh * min(-x_t, wt) + y_bal * max(0.0, -x_t - wt))
    year = None
    if ctx.get("year_basis") == YEAR_MEAN:
        # К-Т2а: вечный поток терминала — средний год (c_terminal_year)
        year = c_terminal_year(periods[-1]["days"], last["nii"] - last["llp"] - last["fvc"],
                               stat["d_nii_l"] if stat is not None else 0.0)
        pbt_l = pbt_l + year["adj"]
        y_x = year["psi"] * y_x
    ni_t1 = c_ni_t1(pbt_l, g_t, y_x, last["tau_eff"], nci, nci_l)
    tau_stat_l = c_traj_at(c_bget(B, "tax.statutory"), yl, A["cpn_quarter"])
    ci_t1 = ni_t1 - A["cpn_annual"] * (1.0 - tau_stat_l)
    fade = c_bnum(B, "valuation.terminal.fade")
    fade_node = None
    if ctx.get("fade_anchor") is not None and yl - ctx["fade_anchor"] > 0:
        # К-Т2в: срок угасания — по календарю с года-якоря; явные годы после него уже прошли s лет схода
        phi_w, n_w = c_fade_calendar(fade, k_t, g_t, yl - ctx["fade_anchor"])
        fade_node = {"s": yl - ctx["fade_anchor"], "n": n_w, "phi": phi_w}
        fade = phi_w
    fixed = None
    if ctx.get("term_fixed") is None:
        roe_t_raw = ci_t1 / bv_star
        # угасание одностороннее (М§7): множитель действует только на положительный избыток ROE_T − k_T
        roe_t = k_t + fade * max(roe_t_raw - k_t, 0.0) + min(roe_t_raw - k_t, 0.0)
        tv_ri = (roe_t - k_t) * bv_star / (k_t - g_t)
        tv_ddm = x_t + (roe_t - g_t) * bv_star / (k_t - g_t)
    else:
        fixed = _c_terminal_fixed_cell(ctx, cell, last, x_t=x_t, n20_t=n20_t, n11_t=n11_t, ci_t1=ci_t1, k_t=k_t,
                                       g_t=g_t, fade=fade, y_bal=y_bal, wt=wt, tau_stat=tau_stat_l, c_wh=c_wh,
                                       h_star=h_star, psi=None if year is None else year["psi"], nci_l=nci_l)
        roe_t_raw, roe_t = fixed["roe_business"], fixed["roe_business_faded"]
        tv_ri, tv_ddm = fixed["tv_ri"], fixed["tv_ddm"]
    d_l = df(tl)
    v_ri = bv_v + pv_ri + d_l * tv_ri
    v_ddm += d_l * tv_ddm
    out = {} if fixed is None else {"terminal_fixed": fixed}
    if nci_l is not None:
        out["nci_l"] = nci_l                        # Р11-3: НДУ года L в рублях мира (печать только при ключе)
    if stat is not None:
        out["terminal_stationary"] = stat
    if year is not None:
        out["terminal_year"] = year
    if fade_node is not None:
        out["terminal_fade"] = fade_node
    if bb_on:
        # цена клетки на ОСТАВШУЮСЯ акцию (М3): дивиденды на внешнюю акцию кварталов и TV на акции конца сетки — за T
        # выкупа нет; «оценка в цене» V̂ = S × N_out / 1000 идёт в формулу цены М§8.2 вместо V_RI
        n_t = rows[-1]["n_c_q"][-1]
        s_price = c_bb_share_value(s_items, d_l, tv_ddm, n_t)
        out.update(n_t=n_t, s_price=s_price, v_price=s_price * A["N_out"] / 1000.0, pv_bb=pv_bb)
    else:
        out["v_price"] = v_ri                       # без выкупа — тот же объект, что V_RI (бит в бит)
    return {**out, "bv_v": bv_v, "v_ri": v_ri, "v_ddm": v_ddm, "pv_ri_explicit": pv_ri,
            "x_t": x_t, "hla": hla, "h_star": h_star, "wt": wt, "y_bal": y_bal, "y_x": y_x, "bv_star": bv_star,
            "k_t": k_t, "g_t": g_t, "g_t_capped": g_raw > k_t - 0.0001,
            "roe_t_raw": roe_t_raw, "roe_t": roe_t, "ni_t1": ni_t1, "ci_t1": ci_t1,
            "tv_ri": tv_ri, "tv_ddm": tv_ddm, "terminal_share": d_l * tv_ddm / v_ddm if v_ddm else None,
            "tau_l": tl, "df_l": d_l}


# ============================================================================ выкуп акций по цене мира (М§5.6, ключ dividends.buyback)

BB_RULES = ("world_forward", "cell_value", "market")
BB_FORWARD, BB_CELL, BB_MARKET = BB_RULES


def c_buyback_rule(ctx: dict):
    """Выкуп акций по цене мира (ключ dividends.buyback, М3): None — ключа нет или enabled: false (прежняя ветвь).

    Суммы B_q — траектория amount (млрд ₽ за квартал, ≥ 0 в каждом квартале сетки); цена покупок P̄_q: кварталы,
    закрытые к дате книги (q < q_b), — closed_prices или цена книги P_b; квартал даты книги — P_s(1 + k_b/2), дальше —
    P⁺_(q−1)(1 + k_b,q/2): середина оставшейся части квартала, простое начисление. Форвард P⁺_q = P⁺_(q−1)(1 + k_b,q)
    − d_q − d^R_q от даты и цены книги (не от живых входов): k_b — плата за капитал мира на дату книги (кривая мира
    + β_E·ERP, перекат по форвардам), d^R — DPS записей реестра закрытых кварталов прибыли (вычтены из BV в якоре) с
    экс-датой позже даты книги. Правило market — одна цена книги во всех кварталах (справочно); cell_value — P_s =
    неподвижная точка стоимости клетки на оставшуюся акцию (справочно). Только квартальный календарь."""
    B, A = ctx["B"], ctx["A"]
    node = c_bopt(B, "dividends.buyback")
    if node is None:
        return None
    if not isinstance(node, dict) or not isinstance(node.get("enabled"), bool):
        raise ControlInputError("dividends.buyback: нужен выключатель enabled (М§0.1)")
    if not node["enabled"]:
        return None
    if not ctx["quarterly"]:
        raise ControlInputError("выкуп по цене мира — только при квартальном календаре дивидендов (М§5.6)")
    for key in ("amount", "price"):
        if node.get(key) is None:
            raise ControlInputError(f"dividends.buyback.{key}: нет поля при enabled: true (М§5.6)")
    rule = node["price"]
    if rule not in BB_RULES:
        raise ControlInputError(f"dividends.buyback.price: {rule!r} — не {', '.join(BB_RULES)} (М§5.6)")
    skip = node.get("skip_in_shock_year", False)
    if not isinstance(skip, bool):
        raise ControlInputError("dividends.buyback.skip_in_shock_year: логическое (null ≠ false, М§0.1)")
    anchor, Q = ctx["anchor"], ctx["Q"]
    amounts = {}
    for k in range(1, Q + 1):
        amounts[k] = c_traj_at(node["amount"], *c_qper(anchor, k))
        if amounts[k] < 0.0:
            raise ControlInputError(f"dividends.buyback.amount < 0 в квартале {'Q'.join(map(str, c_qper(anchor, k)))}")
    prices = c_bget(B, "meta.market_price")
    p_book = prices.get(c_bget(B, "meta.company.main_ticker")) if isinstance(prices, dict) else None
    if p_book is None or isinstance(p_book, bool) or float(p_book) <= 0.0:
        raise ControlInputError("meta.market_price главного тикера — не цена больше нуля (М§5.6)")
    p_book = float(p_book)
    v_b = _c_as_date(c_bget(B, "meta.valuation_date"))
    clock_b = _c_clock(B, ctx["periods"], v_b)
    pos_b = clock_b["pos_abs"]
    q_b = int(math.floor(pos_b)) + 1                    # квартал даты книги по конвенции «конец дня» (М§0.2)
    closed = {}
    for per, price in (node.get("closed_prices") or {}).items():
        k = c_qidx(anchor, *c_per_parse(per))
        if not 1 <= k < q_b:
            raise ControlInputError(f"dividends.buyback.closed_prices.{per}: квартал не закрыт к дате книги или "
                                    f"раньше сетки (М§5.6)")
        if price is None or isinstance(price, bool) or float(price) <= 0.0:
            raise ControlInputError(f"dividends.buyback.closed_prices.{per}: цена — число больше нуля")
        closed[k] = float(price)
    ca = _c_as_date(c_bget(B, "meta.curve_as_of"))
    y0, qa = anchor
    shift = (0.25 * (pos_b - _c_pos(ca, (y0, qa))) if (c_bget(B, "valuation.roll_along_forwards") and ca < v_b)
             else 0.0)
    add = c_bnum(B, "valuation.beta_e") * c_bnum(B, "valuation.erp")
    disc_b, k_b = {}, {}
    for w in ctx["worlds"]:
        disc_b[w] = CDisc(c_bget(B, f"worlds.{w}.zero_curve"), add, shift)
        rates, prev = {}, 1.0
        for k in range(q_b, Q + 1):
            d = disc_b[w]((k - pos_b) * 0.25)
            rates[k] = prev / d - 1.0
            prev = d
        k_b[w] = rates
    d_r = {}
    cal = ctx["divcal"]
    for p_k, rec in cal["register"].items():
        if p_k <= cal["p_last"] and rec["ex"] is not None and rec["ex"] > v_b:
            kq = c_qidx_of_date(anchor, rec["ex"])
            d_r[kq] = d_r.get(kq, 0.0) + rec["dps"]
    return {"rule": rule, "amounts": amounts, "skip": skip, "p_book": p_book, "qb": q_b, "pos_b": pos_b,
            "closed": closed, "k": k_b, "dR": d_r, "clock_b": clock_b, "disc_b": disc_b, "v_b": v_b}


def c_bb_amount(ctx: dict, cell: dict, k: int) -> float:
    """B_q клетки в квартале сетки k: траектория книги; в году шока режима кризиса при skip_in_shock_year — ноль."""
    bb = ctx["bb"]
    if bb["skip"] and cell["regime"] == R_CRISIS and c_qper(ctx["anchor"], k)[0] == ctx["shock_year"]:
        return 0.0
    return bb["amounts"][k]


def c_bb_price(bb: dict, world: str, k: int, p_prev: float) -> float:
    """Цена покупок квартала k (P̄_k): p_prev — P⁺ прошлого квартала (до квартала даты книги включительно — P_s)."""
    if bb["rule"] == BB_MARKET:
        return bb["p_book"]
    if k < bb["qb"]:
        return bb["closed"].get(k, bb["p_book"])           # прошлые покупки — по рынку
    return p_prev * (1.0 + bb["k"][world][k] / 2.0)


def c_bb_forward(bb: dict, world: str, k: int, p_prev: float, d_ext: float) -> float:
    """P⁺_k — форвард цены после дивидендов квартала: рост с k_b мира минус дивиденд на внешнюю акцию d_k и DPS
    записей реестра d^R_k; до квартала даты книги цена стоит на P_s."""
    if bb["rule"] == BB_MARKET or k < bb["qb"]:
        return p_prev
    return p_prev * (1.0 + bb["k"][world][k]) - d_ext - bb["dR"].get(k, 0.0)


def c_bb_share_value(items, df_t: float, tv_ddm: float, n_t: float) -> float:
    """S_c — ₽ на оставшуюся акцию: Σ DF(τ_q) × Div_q × 1000 / N_c,q по дивидендам после даты оценки (items — тройки
    (DF, Div_q, N_c,q)) + DF(τ_Q) × 1000 × TV_DDM / N_c,Q (за T выкупа нет). Дивиденды акций, проданных в выкуп позже,
    оставшимся не засчитываются (econ1: прежнее V / N_T их засчитывало)."""
    return sum(d * div * 1000.0 / n for d, div, n in items) + df_t * 1000.0 * tv_ddm / n_t


def c_bb_shares(n_prev: float, amount: float, p_bar: float, label: str, k: int) -> float:
    """N_c,k = N_c,k−1 − 1000 B_k / P̄_k (млн шт.); в квартале покупки цена или остаток акций не больше нуля — отказ с
    меткой клетки. В квартале без покупки (B_k = 0) акций не покупается при любой цене: форвард рыночной цены от цены
    книги за вычетом дивидендов клетки может уйти ниже нуля, когда дивиденды клетки стоят больше цены книги, и это не
    отказ, а печать (ряд p_bar клетки)."""
    if not amount:
        return n_prev
    if not p_bar > 0.0:
        raise ControlInputError(f"цена выкупа не больше нуля: клетка {label}, квартал сетки {k} (М§5.6)")
    n = n_prev - 1000.0 * amount / p_bar
    if not n > 0.0:
        raise ControlInputError(f"акций в обращении не осталось: клетка {label}, квартал сетки {k} (М§5.6)")
    return n


# ============================================================================ постоянные в рублях части за концом сетки (М§7)

FIXED_PARTS = ("other_assets_fixed", "capital_instruments", "other_fixed_liabilities", "real_rubles")
PART_ASSETS, PART_INSTRUMENTS, PART_LIABILITIES, PART_REAL = FIXED_PARTS
BINDING_N20, BINDING_N11 = "n20", "n11"     # связывающий норматив терминала j* — слот капитала


def c_ni_t1(pbt_l: float, g: float, y_x: float, tau: float, nci: float, nci_l: float | None = None) -> float:
    """Прибыль акционеров первого года за T (М§7): (PBT^T_L (1 + g) − Y_X)(1 − τ)(1 − nci) — доля НДУ; при ключе
    pnl.nci_real (Р11-3, nci_l — НДУ года L в рублях мира) — (PBT^T_L (1 + g) − Y_X)(1 − τ) − NCI_L (1 + g): НДУ в рублях
    растут за T с g, как «прочее» в PBT (без блока К-Т или без его части real_rubles; блок забирает w-долю своей m_L)."""
    if nci_l is None:
        return (pbt_l * (1.0 + g) - y_x) * (1.0 - tau) * (1.0 - nci)
    return (pbt_l * (1.0 + g) - y_x) * (1.0 - tau) - nci_l * (1.0 + g)


def c_nci_real(B: dict):
    """Неконтролирующие доли в реальных рублях (ключ pnl.nci_real, решения № 11, Р11-3; образец — other.misc_net_real):
    траектория любого знака, млрд ₽ в год в ценах якоря. Квартал: NCI_q = nci_real(Y) / 4 × I_W,q (индекс цен мира клетки,
    I_W,0 = 1); NI акционеров ni_sh = ni − NCI; терминал: ni_T+1 = (PBT^T (1 + g) − Y_X)(1 − τ) − NCI_L (1 + g), блок К-Т с
    частью real_rubles — m_L = (misc_L + nc_L)(1 − τ) − NCI_L, налог блока (1 − τ). При ключе доля pnl.nci_share не
    читается (ключ неактивного режима, не отказ). Нет ключа — None (прежняя доля); null и не траектория — отказ (М§0.1,
    §0.4)."""
    node = c_bopt(B, "pnl") or {}
    if "nci_real" not in node:
        return None
    raw = node["nci_real"]
    if raw is None:
        raise ControlInputError("pnl.nci_real: null (М§0.1: null ≠ нет ключа)")
    c_traj_form(raw, "pnl.nci_real")
    return raw


def c_stationary_rule(B: dict) -> bool:
    """Терминал от стационарных ставок книг ЧПД (ключ valuation.terminal.stationary_rates, К4, решения № 3, Р6): ЧПД
    года L и ставки балансирующих статей за T — при полной подстройке ставок книг (цель квартала — ставка при ρ = 1).
    Нет ключа или false — прежний терминал; не логическое значение — отказ."""
    term = c_bopt(B, "valuation.terminal") or {}
    if "stationary_rates" not in term:
        return False
    if not isinstance(term["stationary_rates"], bool):
        raise ControlInputError("valuation.terminal.stationary_rates: логическое (М§7)")
    return term["stationary_rates"]


def c_year_basis(B: dict) -> str:
    """Год терминала (ключ valuation.terminal.year_basis, К-Т2а, решения № 4, Р4-5): calendar — PBT года L как есть
    (прежняя строка); mean — дневные строки года L (ЧПД, резервы, FVC) приведены к средней длине года, ставки дохода на
    избыток и блока К-Т — к среднему году act/365. Нет ключа — calendar; значение не из перечня (и null) — отказ."""
    term = c_bopt(B, "valuation.terminal") or {}
    if "year_basis" not in term:
        return YEAR_CALENDAR
    v = term["year_basis"]
    if not isinstance(v, str) or v not in YEAR_BASES:
        raise ControlInputError(f"valuation.terminal.year_basis: {v!r} — не {', '.join(YEAR_BASES)} (М§7)")
    return v


def c_fixed_funding(B: dict) -> str:
    """Ставка фондирования блока постоянных частей терминала (ключ valuation.terminal.fixed_funding, К-Т2б): binary —
    ставка опта, если добор опта на конце Q есть, иначе смесь балансирующих (прежняя строка); balancing — связанность
    минимума ликвидности после выплаты избытка X_T и его стоимость на постоянных активах. Читается только при блоке К-Т
    (λ_F < 1), как части блока; без блока — binary без чтения. Значение не из перечня — отказ."""
    if c_terminal_fixed_rule(B) is None:
        return FUND_BINARY
    term = c_bopt(B, "valuation.terminal") or {}
    if "fixed_funding" not in term:
        return FUND_BINARY
    v = term["fixed_funding"]
    if not isinstance(v, str) or v not in FUNDINGS:
        raise ControlInputError(f"valuation.terminal.fixed_funding: {v!r} — не {', '.join(FUNDINGS)} (М§7)")
    return v


def c_fade_anchor(B: dict):
    """Год-якорь угасания Y_a (ключ valuation.terminal.fade_anchor_year, К-Т2в): срок угасания суждения идёт по
    календарю с года Y_a, а явные годы после него уже прошли s = Y(L) − Y_a лет схода. Нет ключа — None (множитель книги
    как есть). Не целое или Y_a позже года конца сетки (срок начинался бы внутри явных лет) — отказ."""
    term = c_bopt(B, "valuation.terminal") or {}
    if "fade_anchor_year" not in term:
        return None
    v = term["fade_anchor_year"]
    if isinstance(v, bool) or not isinstance(v, int):
        raise ControlInputError(f"valuation.terminal.fade_anchor_year: {v!r} — не год (М§7)")
    yl = c_per_parse(c_bget(B, "meta.last_period"))[0]
    if v > yl:
        raise ControlInputError(f"valuation.terminal.fade_anchor_year = {v} позже года конца сетки {yl}: срок угасания "
                                f"начинался бы внутри явных лет (М§7)")
    return v


def c_forms(B: dict) -> dict:
    """Формы ключей книги для тождеств контрольной модели (решения № 4, Р4-16): s_eff — база опта к средствам клиентов
    (структурная доля К3, иначе доля якоря); rates — ставки терминала (stationary — цели года L при К4, иначе lagged —
    ставки конца Q); year_basis — год терминала (К-Т2а); funding — ставка фондирования блока К-Т (К-Т2б). B — книга с
    выведенными ключами (контекст прогона). Без ключей — прежние формы."""
    s_eff, _ = c_wholesale_shares(B)
    return {"s_eff": s_eff, "rates": RATES_STATIONARY if c_stationary_rule(B) else RATES_LAGGED,
            "year_basis": c_year_basis(B), "funding": c_fixed_funding(B)}


def c_terminal_year(days_l: int, dw: float, d_star: float) -> dict:
    """Год терминала «средний год» (К-Т2а): проценты act/365 в явных годах несут дни года L (у високосного — 366/365
    годовой ставки, М§0.3), а вечный поток терминала — средний год. Дневные строки года L DW_L (ЧПД с АСВ и наложением
    ЧПМ, резервы, FVC) и поправка К4 ΔNII*_L — к средней длине года множителем ν_L = 365,2425 / D_L: поправка PBT года
    терминала adj = (ν_L − 1)(DW_L + ΔNII*_L); ставки дохода на избыток и блока К-Т — к среднему году множителем
    ψ = 365,2425 / 365. Строки г/г (комиссии, страхование, расходы), «прочее», пакет и FVR не меняются."""
    nu = MEAN_YEAR / days_l
    return {"days_l": days_l, "nu_l": nu, "psi": MEAN_YEAR / DAYS_BASE, "day_weighted_l": dw,
            "adj": (nu - 1.0) * (dw + d_star)}


def c_fade_sum(n: float, k: float, g: float, s: float = 0.0) -> float:
    """Множитель угасания при сроке n лет и начале схода s (справочная формула М§7 с началом s, К-Т2в):
    (k − g)/(1 + k) × Σ_(t ≥ 1) max(0, 1 − (t − 1 + s)/n) × x^(t − 1), x = (1 + g)/(1 + k). Вес члена линеен по t до
    последнего положительного, поэтому сумма — замкнутая арифметико-геометрическая: m членов, Σ x^j и Σ j x^j."""
    if n <= s:
        return 0.0
    x = (1.0 + g) / (1.0 + k)
    m = math.ceil(n - s)                                # члены j = 0 … m − 1 (вес 1 − (j + s)/n > 0)
    geo = (1.0 - x ** m) / (1.0 - x)
    lin = (x - m * x ** m + (m - 1) * x ** (m + 1)) / (1.0 - x) ** 2
    return (k - g) / (1.0 + k) * ((1.0 - s / n) * geo - lin / n)


def c_fade_years(target: float, k: float, g: float) -> float:
    """Срок угасания мира n_W (лет): множитель книги — схождение с начала, c_fade_sum(n_W, k, g, 0) = target. Сумма
    растёт по n (от (k − g)/(1 + k) к 1), поэтому корень — делением отрезка пополам до 1e-12 доли срока; target ≥ 1 —
    срок бесконечен."""
    if target >= 1.0:
        return math.inf
    lo, hi = 0.0, 1.0
    for _ in range(FIT_ITER):
        if c_fade_sum(hi, k, g) >= target:
            break
        lo, hi = hi, 2.0 * hi
    for _ in range(2 * FIT_ITER):
        if hi - lo <= 1e-12 * hi:
            break
        mid = (lo + hi) / 2.0
        if c_fade_sum(mid, k, g) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def c_fade_calendar(fade: float, k: float, g: float, s: int) -> tuple[float, float | None]:
    """Множитель угасания φ_W с началом схода s (К-Т2в): s = 0 или fade ≥ 1 — множитель книги как есть (срок None);
    иначе срок мира n_W из схождения с начала и множитель того же срока с начала s. Возвращает (φ_W, n_W)."""
    if s == 0 or fade >= 1.0:
        return fade, None
    n = c_fade_years(fade, k, g)
    return c_fade_sum(n, k, g, s), n


def c_terminal_fixed_rule(B: dict):
    """Ключи блока постоянных частей терминала (М§7): valuation.terminal.fixed_growth_share — λ_F ∈ [0; 1], доля
    запаса постоянных частей, остающаяся в бизнесе; valuation.terminal.fixed_parts — какие части несёт блок (по
    умолчанию все четыре). Нет ключа λ_F или λ_F = 1 — None: прежняя ветвь терминала. Null у ключа — отказ."""
    term = c_bopt(B, "valuation.terminal") or {}
    parts = FIXED_PARTS
    if "fixed_parts" in term:
        raw = term["fixed_parts"]
        if (not isinstance(raw, list) or not raw or any(p not in FIXED_PARTS for p in raw)
                or len(set(raw)) != len(raw)):
            raise ControlInputError("valuation.terminal.fixed_parts: непустой список частей "
                                    + ", ".join(FIXED_PARTS) + " без повторов (М§7)")
        parts = tuple(raw)
    if "fixed_growth_share" not in term:
        return None
    lam = term["fixed_growth_share"]
    if lam is None or isinstance(lam, bool) or not isinstance(lam, (int, float)) or not 0.0 <= float(lam) <= 1.0:
        raise ControlInputError("valuation.terminal.fixed_growth_share: λ_F — число в [0; 1] (М§7)")
    if float(lam) == 1.0:
        return None
    return {"lam": float(lam), "parts": parts}


def c_terminal_fixed(*, lam: float, parts, x_t: float, binding: str, bv_q: float, ci_t1: float, k: float, g: float,
                     fade: float, kappa: float, r_f: float, f_a: float, at1: float, t2: float, nci_amt: float,
                     dp_fix: float, y_m: float, cpn: float, tau: float, tau_stat: float, nci: float, misc_l: float,
                     pi: float, label: str = "", m_f: float | None = None, psi: float | None = None,
                     nci_l: float | None = None) -> dict:
    """Блок постоянных в рублях частей терминала (М§7) своим счётом. Доля 1 − λ_F постоянных частей стоит вне бизнеса:
    номинальные части (прочие активы постоянной части, инструменты капитала, постоянные пассивы) не растут, капитала
    под рост не держат и не угасают; строки в реальных рублях («прочее» и пакет года L) остаются в избытке бизнеса,
    угасают с ним и растут с инфляцией мира. Капитал акционеров финансирует рост бизнеса, в том числе за инструменты.

    Капитал постоянных частей F_K = κ_j* R_F − χ (AT1 + T2) (χ — инструменты в связывающем нормативе; в K11 их нет),
    фондирование балансирующими статьями D_F = F_A − F_K − AT1 − (NCI + DP_fix), доход стоящей доли I_F = −y_m D_F
    (1 − τ)(1 − nci) − купон (1 − τ_stat); бизнес — капитал B = BV* − w F_K и доход CI_B: из CI_T+1 убран доход стоящей
    доли (образец вырастил PBT_L на g — убирается с множителем 1 + g; купон в CI_T+1 стоит плоско) и w-доля строк в
    реальных рублях. TV_RI = φ X_B + w (I_F − k F_K) / k; TV_DDM = X_T + BV* + TV_RI (тождество TV_DDM − TV_RI = BV_Q).
    misc_l — сумма строк «прочее» и пакета года L до налога. К-Т2: m_f — стоимость минимума ликвидности на постоянных
    активах до налога (К-Т2б, M_F), psi — множитель среднего года ставки фондирования (К-Т2а, ψ); стоимость стоящей доли
    ψ (y_m D_F + M_F) — в I_F и в CI_B вместо y_m D_F. Без них (None) — прежние строки.

    nci_l — НДУ года L в рублях мира (Р11-3, ключ pnl.nci_real; тогда nci = 0 — налог блока (1 − τ)): с частью real_rubles
    m_L = (misc_L + nc_L)(1 − τ) − NCI_L — w-доля НДУ уходит из растущей части в поток с инфляцией мира; без части
    real_rubles НДУ остаются в CI_T+1 и растут с g. None — прежние строки."""
    on = set(parts)
    w = 1.0 - lam
    bv_star = bv_q - x_t
    inst = PART_INSTRUMENTS in on
    chi = 1.0 if (inst and binding == BINDING_N20) else 0.0
    f_a_on = f_a if PART_ASSETS in on else 0.0
    f_k = (kappa * r_f if PART_ASSETS in on else 0.0) - chi * (at1 + t2)
    d_f = f_a_on - f_k - (at1 if inst else 0.0) - ((nci_amt + dp_fix) if PART_LIABILITIES in on else 0.0)
    keep = (1.0 - tau) * (1.0 - nci)
    cpn_net = cpn * (1.0 - tau_stat) if inst else 0.0
    carry = None
    if m_f is None and psi is None:
        i_f = -y_m * d_f * keep - cpn_net
    else:
        carry = (1.0 if psi is None else psi) * (y_m * d_f + (0.0 if m_f is None else m_f))
        i_f = -carry * keep - cpn_net
    m_l = misc_l * keep if PART_REAL in on else 0.0
    if nci_l is not None and PART_REAL in on:
        m_l = m_l - nci_l                           # Р11-3: НДУ в рублях — строка в реальных рублях после налога
    pi_t = min(pi, k - 0.0001)
    b = bv_star - w * f_k
    if not b > 0.0:
        raise ControlInputError(f"капитал бизнеса терминала B = BV* − (1 − λ_F) F_K ≤ 0, клетка {label} (М§7)")
    if carry is None:
        ci_b = ci_t1 + w * (1.0 + g) * y_m * d_f * keep + w * cpn_net - w * (1.0 + g) * m_l
    else:
        ci_b = ci_t1 + w * (1.0 + g) * carry * keep + w * cpn_net - w * (1.0 + g) * m_l
    x_b = (ci_b - k * b) / (k - g) + w * m_l * (1.0 + pi_t) / (k - pi_t)
    phi = fade if x_b > 0.0 else 1.0
    tv_ri = phi * x_b + w * (i_f - k * f_k) / k
    out = {"lam_f": lam, "parts": list(parts), "f_a": f_a_on, "r_f": r_f if PART_ASSETS in on else 0.0,
           "kappa": kappa, "binding": binding, "f_k": f_k, "d_f": d_f, "y_m": y_m, "i_f": i_f, "m_l": m_l,
           "business_capital": b, "ci_business": ci_b, "x_b": x_b, "phi": phi, "pi_t": pi_t,
           "roe_business": (ci_b + w * m_l * (1.0 + pi_t)) / b, "roe_business_faded": k + phi * x_b * (k - g) / b,
           "tv_ri": tv_ri, "tv_ddm": x_t + (bv_star + tv_ri)}
    if carry is not None:
        out.update(carry=carry, psi=psi, m_f=m_f)
    if nci_l is not None:
        out["nci_l"] = nci_l
    return out


def c_funding_after_payout(*, x_t: float, wt: float, h_star: float, y_bal: float, c_wh: float, m_liq: float,
                           f_a: float) -> dict:
    """Ставка фондирования блока постоянных частей терминала (К-Т2б, fixed_funding: balancing) — по правилу
    балансирующих статей после выплаты избытка (та же форма, что у дохода на избыток Y_X): избыток X_T > 0 сначала
    съедает запас H* = HLA / (1 − m), сверх него — добор опта; недостаток (X_T ≤ 0) сначала гасит добор опта WT_Q:
    WT* = WT_Q + max(0, X_T − H*) при X_T > 0, иначе max(0, WT_Q + X_T). Минимум связан после выплаты (WT* > 0) —
    постоянные активы финансирует опт по c_wh, и минимум ликвидности на них m F_A / (1 − m) берётся оптом и лежит в
    ликвидности по y_bal: стоимость M_F = (c_wh − y_bal) m / (1 − m) F_A до налога. Не связан — смесь балансирующих,
    M_F = 0. wt_z — WT* до обрезки нулём (величина решения у порога, правило ПОРОГ)."""
    if x_t > 0.0:
        wt_after, z = wt + max(0.0, x_t - h_star), wt + x_t - h_star
    else:
        wt_after, z = max(0.0, wt + x_t), wt + x_t
    bound = wt_after > 0.0
    return {"bound_after_payout": bound, "wt_after": wt_after, "wt_z": z, "y_m": c_wh if bound else y_bal,
            "min_liquidity": (c_wh - y_bal) * m_liq / (1.0 - m_liq) * f_a if bound else 0.0}


def _c_terminal_fixed_cell(ctx: dict, cell: dict, last: dict, *, x_t: float, n20_t: float, n11_t: float,
                           ci_t1: float, k_t: float, g_t: float, fade: float, y_bal: float, wt: float,
                           tau_stat: float, c_wh: float, h_star: float = 0.0, psi: float | None = None,
                           nci_l: float | None = None) -> dict:
    """Входы блока постоянных частей терминала из годовой строки последнего года клетки (М§7) и сам блок.

    j* — норматив с меньшим избытком над требованием (при равенстве — Н20.0); κ_j = требование − (поправка gap −
    вычет сценария конца Q) + вычеты якоря / RWA_0 — капитал акционеров на рубль RWA; R_F — RWA постоянных прочих
    активов конца года (своя плотность × дрейф × валютный индекс × множитель режима); T2 — конца Q; DP_fix —
    постоянная часть остатка «дивиденды к выплате» якоря (квартальный режим; у годового весь остаток выплачивается)."""
    B, A = ctx["B"], ctx["A"]
    rule = ctx["term_fixed"]
    p = ctx["periods"][-1]
    yl, hq = p["year"], p["quarters"][-1]
    s, r, w = cell["scenario"], cell["regime"], cell["world"]
    binding = BINDING_N20 if (n20_t - last["req20"]) <= (n11_t - last["req11"]) else BINDING_N11
    dp20 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n20_0"), yl, hq)
    dp11 = c_traj_at(c_bget(B, f"capital.reg_scenarios.{s}.deduction_pp.n1_1"), yl, hq)
    kap20 = (last["req20"] - (c_bnum(B, "capital.n20.gap_pp") - dp20)
             + c_bnum(B, "capital.n20.deductions_anchor") / ctx["rwa0"])
    kap11 = (last["req11"] - (c_bnum(B, "capital.n11.gap_pp") - dp11)
             + c_bnum(B, "capital.n11.deductions_anchor") / ctx["rwa0"])
    oaf = ctx["oaf"]
    r_f = _c_rwa_of(ctx, r, yl, hq, {b: 0.0 for b in ctx["books"]}, oaf, last["dn_end"], last["xf_end"]) if oaf else 0.0
    if ctx.get("funding") != FUND_BALANCING:
        y_m, m_f, funding = (c_wh if wt > 0.0 else y_bal), None, None
    else:
        funding = c_funding_after_payout(x_t=x_t, wt=wt, h_star=h_star, y_bal=y_bal, c_wh=c_wh,
                                         m_liq=c_bnum(B, "volumes.liquid_min_share"),
                                         f_a=oaf if PART_ASSETS in rule["parts"] else 0.0)
        y_m, m_f = funding["y_m"], funding["min_liquidity"]
    out = c_terminal_fixed(
        lam=rule["lam"], parts=rule["parts"], x_t=x_t, binding=binding, bv_q=last["bv"], ci_t1=ci_t1, k=k_t, g=g_t,
        fade=fade, kappa=kap20 if binding == BINDING_N20 else kap11, r_f=r_f, f_a=oaf, at1=A["AT1"],
        t2=c_traj_at(c_bget(B, "capital.n20.t2"), yl, hq), nci_amt=A["NCI"],
        dp_fix=ctx["divcal"]["perm"] if ctx["quarterly"] else 0.0,
        y_m=y_m, cpn=A["cpn_annual"], tau=last["tau_eff"], tau_stat=tau_stat,
        nci=c_bnum(B, "pnl.nci_share") if nci_l is None else 0.0, misc_l=last["misc"] + last["noncore"],
        pi=c_bnum(B, f"worlds.{w}.lt_inflation"), label="/".join((w, r, s)), m_f=m_f, psi=psi, nci_l=nci_l)
    if funding is not None:
        out.update({k: v for k, v in funding.items() if k != "y_m"})
    return out


# ============================================================================ мост до цены (М§8.1)

def _c_register_amounts(ctx: dict) -> list[tuple[float, dt.date, dt.date | None]]:
    """Объявленные дивиденды реестра: (сумма DPS × N_out / 1000, дата вычета из BV модели, экс-дата).
    Вычет из BV модели — дата фактов (дивиденд вычтен в якоре) или конец квартала ГОСА клетки (М§8.1)."""
    B, A = ctx["B"], ctx["A"]
    facts_date = _c_as_date(c_bget(B, "meta.facts_date"))
    out = []
    if ctx["quarterly"]:
        # строка на запись — на квартал прибыли (М§8.1): вычет из BV модели — дата фактов у закрытого
        # квартала, иначе конец квартала клетки q_cell(period)
        cal = ctx["divcal"]
        for k, rec in sorted(cal["register"].items()):
            cell_end = c_q_last_day(*c_qper(ctx["anchor"], rec["q_cell"]))
            out.append((rec["dps"] * A["N_out"] / 1000.0, facts_date if k <= cal["p_last"] else cell_end, rec["ex"]))
        return out
    agm = int(c_bnum(B, "dividends.calendar.agm_quarter"))
    for rec in _c_register_binding(ctx):
        agm_end = c_q_last_day(int(_c_nodeval(rec["year"])) + 1, agm)
        ex = rec.get("ex_date")
        out.append((float(_c_nodeval(rec["dps"])) * A["N_out"] / 1000.0,
                    facts_date if agm_end <= facts_date else agm_end,
                    _c_as_date(_c_nodeval(ex)) if ex else None))
    return out


def c_bridge_register(ctx: dict) -> float:
    """B(v): объявленные дивиденды реестра от модельного вычета из BV до экс-даты, млрд ₽."""
    v = ctx["clock"]["v"]
    return sum(amount * ((1.0 if deduct <= v else 0.0) - (1.0 if ex is not None and ex <= v else 0.0))
               for amount, deduct, ex in _c_register_amounts(ctx))


def c_pending_register(ctx: dict) -> float:
    """D_pend (М§8.2): объявленные дивиденды, которые клетки ещё не вычли из BV (v раньше вычета) —
    они внутри V0 и дисконта за управление не несут; номинал, как в мосте, млрд ₽."""
    v = ctx["clock"]["v"]
    return sum(amount for amount, deduct, _ in _c_register_amounts(ctx) if v < deduct)


# ============================================================================ A-P2u (М§12)

def _c_qindex(y: int, q: int) -> int:
    return y * QY + (q - 1)


def c_expectations_ctl(ctx: dict, quarters) -> dict:
    """Ожидания режимов μ_x,r(q) (М§12): среднее слоя «свой взгляд» (веса миров × P(s | r)) по
    клеткам режима без отклонений A-P2u. CoR — путь режима через мост плюс κ-добавка мира
    (поквартально, точно); ЧПМ — ЧПМ движка клетки с ближним сдвигом и сдвигом режима из
    предварительного прохода клеток до года последнего квартала (годовой шаг: ЧПМ квартала внутри
    периода — ставки квартала при структуре баланса периода). Ключ результата — (x, r, год, квартал)."""
    B = ctx["B"]
    quarters = sorted({(int(y), int(q)) for y, q in quarters})
    where = {p["year"]: p["quarters"] for p in ctx["periods"]}
    for y, q in quarters:
        if q not in where.get(y, ()):
            raise ControlInputError(f"наблюдение A-P2u {y}Q{q} вне прогнозных кварталов сетки")
    pw = {w: float(c_bget(B, "joint.world_prob").get(w, 0.0)) for w in ctx["worlds"]}
    prs = c_bget(B, "joint.reg_prob_given_regime")
    regimes, scen = list(c_bget(B, "regimes.ids")), list(c_bget(B, "capital.reg_scenarios.ids"))
    lag, kap = int(c_bnum(B, "credit.real_rate_lag_q")), c_bnum(B, "credit.kappa")
    saved, ctx["dev"] = ctx["dev"], {}                  # предварительный проход — без отклонений (δ ≡ 0)
    try:
        nim0 = {}
        for w in (w for w in ctx["worlds"] if pw[w]):
            for r in regimes:
                for s in scen:
                    rows = _c_cell_path(ctx, {"world": w, "regime": r, "scenario": s},
                                        upto_year=quarters[-1][0])["rows"]
                    for p, row in zip(ctx["periods"], rows):
                        for j, q in enumerate(p["quarters"]):
                            nim0[(w, r, s, p["year"], q)] = row["nim_q"][j]
    finally:
        ctx["dev"] = saved
    mu = {}
    for y, q in quarters:
        for r in regimes:
            mu[("cor", r, y, q)] = sum(pw[w] * (c_cor_path_engine(ctx, r, y, q) + kap * _c_kappa_gap(B, w, y, q, lag))
                                       for w in pw if pw[w])
            mu[("nim", r, y, q)] = sum(pw[w] * float(prs[r][s]) * nim0[(w, r, s, y, q)]
                                       for w in pw if pw[w] for s in scen)
    return mu


def _c_frozen_mu(ctx: dict, o: dict) -> dict:
    """Замороженные ожидания режимов наблюдения квартала не позже якоря (М§12): словари mu_cor,
    mu_nim {режим: μ} в базисе записи — через тот же мост, что и само наблюдение. Нет μ наблюдённой
    величины — громкий отказ."""
    A = ctx["A"]
    y, q = c_per_parse(o["period"])
    out = {}
    for x in ("cor", "nim"):
        if o.get(x) is None:
            continue
        table = o.get(f"mu_{x}")
        for r in c_bget(ctx["B"], "regimes.ids"):
            if not isinstance(table, dict) or table.get(r) is None:
                raise ControlInputError(f"наблюдение A-P2u {o['period']} (квартал не позже якоря) без mu_{x}.{r}")
            val = float(table[r])
            out[(x, r, y, q)] = c_to_engine(A, x, val) if o.get("basis", "engine") == "mgmt" else val
    return out


def c_regime_update_ctl(ctx: dict) -> None:
    """Вероятности режимов после квартальных наблюдений CoR и ЧПМ и затухающие отклонения (М§12).
    Априорные стационарны, память — окно: фильтр стартует с базовых вероятностей книги и пустого
    состояния и проходит только последние joint.regime_update.window_obs наблюдений."""
    B, A = ctx["B"], ctx["A"]
    ru = "joint.regime_update"
    window = c_bget(B, f"{ru}.window_obs")
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ControlInputError("joint.regime_update.window_obs — целое ≥ 1 (М прил. A)")
    floor_share = c_bnum(B, f"{ru}.floor_share")
    if not 0.0 <= floor_share <= 1.0:
        raise ControlInputError("joint.regime_update.floor_share вне [0; 1] (М прил. A)")
    obs = sorted(c_bget(B, f"{ru}.observations") or [], key=lambda o: c_per_parse(o["period"]))[-window:]
    prior = {r: float(v) for r, v in c_bget(B, "joint.regime_prob").items()}
    ctx["posterior"], ctx["dev"], ctx["mu"], ctx["updates"] = dict(prior), {}, {}, []
    if not obs:
        return
    # ожидания режимов: прогнозные кварталы — предварительный проход клеток; кварталы не позже якоря —
    # замороженные μ записи (их пишет перезаякоривание)
    ahead = [c_per_parse(o["period"]) for o in obs if c_per_parse(o["period"]) > ctx["anchor"]]
    mus = c_expectations_ctl(ctx, ahead) if ahead else {}
    for o in obs:
        if c_per_parse(o["period"]) <= ctx["anchor"]:
            mus.update(_c_frozen_mu(ctx, o))
    ctx["mu"] = mus
    sig = {x: c_bnum(B, f"{ru}.observables.{x}.sigma_pp") for x in ("cor", "nim")}
    rho = {x: c_bnum(B, f"{ru}.observables.{x}.rho_q") for x in ("cor", "nim")}
    cap = c_bnum(B, f"{ru}.max_shift_pp")
    floors = {r: floor_share * prior[r] for r in prior}
    state = {(x, r): None for x in ("cor", "nim") for r in prior}
    trail = {key: [] for key in state}
    post = dict(prior)
    for o in obs:
        y, q = c_per_parse(o["period"])
        qi = _c_qindex(y, q)
        like = {r: 1.0 for r in prior}
        for x in ("cor", "nim"):
            val = o.get(x)
            if val is None:
                continue
            val = float(val)
            if o.get("basis", "engine") == "mgmt":
                val = c_to_engine(A, x, val)
            se = float(o.get(f"se_{x}") or 0.0)
            for r in prior:
                dev = val - mus[(x, r, y, q)]
                prev = state[(x, r)]
                if prev is None:
                    k, err, P = 0, dev, sig[x] ** 2
                    m_prev = 0.0
                else:
                    k = qi - prev["qi"]
                    rk = rho[x] ** k
                    err = dev - rk * prev["m"]
                    P = sig[x] ** 2 * (1.0 - rho[x] ** (2 * k)) + rho[x] ** (2 * k) * prev["v"]
                    m_prev = rk * prev["m"]
                like[r] *= math.exp(-0.5 * err * err / (P + se * se))
                if se == 0.0:
                    m_new, v_new = dev, 0.0
                else:
                    wk = P / (P + se * se)
                    m_new, v_new = m_prev + wk * err, (1.0 - wk) * P
                state[(x, r)] = {"qi": qi, "m": m_new, "v": v_new, "y": y, "q": q}
                trail[(x, r)].append((y, q, m_new))
        tot = sum(post[r] * like[r] for r in post)
        raw = {r: post[r] * like[r] / tot for r in post}
        clipped = {r: post[r] + max(-cap, min(cap, raw[r] - post[r])) for r in post}
        z = sum(clipped.values())
        clipped = {r: c / z for r, c in clipped.items()}
        worst = max(abs(clipped[r] - post[r]) for r in post)
        if worst > cap + 1e-12:
            clipped = {r: post[r] + cap / worst * (clipped[r] - post[r]) for r in post}
        post = c_floor_probabilities(clipped, floors)       # пол — вслед за пределом сдвига
        ctx["updates"].append({"period": o["period"], "posterior": dict(post)})
    ctx["posterior"] = post
    for r in prior:
        ctx["dev"][r] = {}
        for x in ("cor", "nim"):
            stt = state[(x, r)]
            if stt is not None:
                ctx["dev"][r][x] = {"y": stt["y"], "q": stt["q"], "rho": rho[x], "m": stt["m"],
                                    "trail": trail[(x, r)]}


def c_floor_probabilities(prob: dict, floors: dict) -> dict:
    """Пол вероятности режима (М§12): режим ниже своего пола ставится на пол, остальные умножаются на
    общий множитель так, чтобы сумма была 1; если после этого ещё какой-то режим оказался ниже пола —
    он тоже ставится на пол, и шаг повторяется (режимов конечное число, сумма полов ≤ 1)."""
    out = dict(prob)
    pinned: set = set()
    while True:
        low = {r for r in out if r not in pinned and out[r] < floors[r]}
        if not low:
            return out
        pinned |= low
        free = [r for r in out if r not in pinned]
        room = 1.0 - sum(floors[r] for r in pinned)
        mass = sum(prob[r] for r in free)
        for r in pinned:
            out[r] = floors[r]
        for r in free:
            out[r] = prob[r] * room / mass if mass > 0.0 else 0.0


# ============================================================================ сетка, слои, точка (М§3, §8–§9)

def c_layer_weights(B: dict) -> dict[str, dict[str, float]]:
    return {"analytical": {w: float(v) for w, v in c_bget(B, "joint.world_prob").items()},
            "market_implied": {w: float(v) for w, v in c_bget(B, "joint.world_prob_market_implied").items()},
            "macro_neutral": {c_bget(B, "joint.macro_neutral_world"): 1.0}}


def c_price_of(v0: float, bridge: float, gov: float, n_div: float, pending: float = 0.0) -> float:
    """Цена (М§8.2): дисконт за управление — к V0 без объявленного дивиденда: ни мост B(v), ни
    сумма D_pend (объявлено, но ещё не вычтено из BV модели) дисконта не несут. Делится на N_div
    (М§8.4); суммы моста и D_pend — на акции в обращении, их делитель не трогает."""
    own = v0 - pending
    if own > 0.0:
        return (own * (1.0 - gov) + pending + bridge) * 1000.0 / n_div
    return (v0 + bridge) * 1000.0 / n_div


def c_control_run(book: dict | None = None, facts: dict | None = None, *, valuation_date=None,
                  base_book: dict | None = None) -> dict:
    """Вся контрольная модель: передача, 36 клеток, слои, низ/верх/точка при центральных значениях."""
    book = book if book is not None else c_book_machine()
    facts = facts if facts is not None else c_facts_bundle()
    ctx = c_control_context(book, facts, valuation_date=valuation_date, base_book=base_book)
    B, A = ctx["B"], ctx["A"]
    if c_bget(B, "dividends.policy.base") != "ifrs_ni_shareholders":
        raise ControlUnsupported("база дивиденда кроме ifrs_ni_shareholders не реализована")
    worlds = ctx["worlds"]
    regimes = list(c_bget(B, "regimes.ids"))
    scen = list(c_bget(B, "capital.reg_scenarios.ids"))
    cells = [c_cell_annual(ctx, w, r, s) for w in worlds for r in regimes for s in scen]
    lw = c_layer_weights(B)
    prs = c_bget(B, "joint.reg_prob_given_regime")
    layers = {}
    for name in LAYERS:
        P = {}
        for c in cells:
            P[(c["world"], c["regime"], c["scenario"])] = (
                lw[name].get(c["world"], 0.0) * ctx["posterior"][c["regime"]]
                * float(prs[c["regime"]][c["scenario"]]))
        v0 = sum(P[(c["world"], c["regime"], c["scenario"])] * c["v_price"] for c in cells)
        bv = sum(P[(c["world"], c["regime"], c["scenario"])] * c["bv_v"] for c in cells)
        layers[name] = {"prob_sum": sum(P.values()), "v0": v0, "bv_v": bv,
                        "price": c_price_of(v0, ctx["bridge_amount"], ctx["gov"], A["N_div"],
                                            ctx["pending_amount"]),
                        "bv_per_share": bv * 1000.0 / A["N_div"],
                        "pb": v0 / bv if bv else None}
    lam = c_bnum(B, "joint.own_macro_confidence")
    low, high = layers["macro_neutral"]["price"], layers["analytical"]["price"]
    for c in cells:
        c["price"] = c_price_of(c["v_price"], ctx["bridge_amount"], ctx["gov"], A["N_div"], ctx["pending_amount"])
        c["pb"] = c["v_price"] / c["bv_v"]
    res = {"ctx": ctx, "transmission": ctx["tr"], "cells": cells, "layers": layers,
            "low": low, "high": high, "lam": lam, "point": low + lam * (high - low),
            "bridge_amount": ctx["bridge_amount"], "pending_amount": ctx["pending_amount"],
            "governance": ctx["gov"], "shock_year": ctx["shock_year"],
            "posterior": ctx["posterior"], "derived": ctx["derived"],
            "shares_out": A["N_out"], "divisor": A["N_div"], "quarterly": ctx["quarterly"],
            "growth_rule": ctx["growth"], "history_test": c_history_kind(B),
            "dps_history": c_dps_history_ctl(B, facts),
            "years": [p["year"] for p in ctx["periods"]]}
    res["central"] = c_central_cell(res)
    return res


def c_central_cell(res: dict) -> dict:
    """Центральная клетка книги — правилом, не литералом (INTERFACES §4.6): мир с наибольшим весом слоя
    «свой взгляд», режим с наибольшей вероятностью после A-P2u, сценарий капитала с наибольшей
    P(s | r) у этого режима; при равенстве — первый по порядку книги."""
    B = res["ctx"]["B"]
    pw = c_bget(B, "joint.world_prob")

    def c_first_max(ids, weight):
        best = ids[0]
        for x in ids[1:]:
            if weight(x) > weight(best):
                best = x
        return best

    w = c_first_max(list(c_bget(B, "worlds.ids")), lambda x: float(pw.get(x, 0.0)))
    r = c_first_max(list(c_bget(B, "regimes.ids")), lambda x: res["posterior"][x])
    prs = c_bget(B, "joint.reg_prob_given_regime")[r]
    sc = c_first_max(list(c_bget(B, "capital.reg_scenarios.ids")), lambda x: float(prs[x]))
    return {"cell": (w, r, sc), "label": "/".join((w, r, sc)), "scenario_weight": float(prs[sc]),
            "probability": float(pw[w]) * res["posterior"][r] * float(prs[sc])}


def c_cell_of(res: dict, world: str, regime: str, scenario: str) -> dict:
    for c in res["cells"]:
        if (c["world"], c["regime"], c["scenario"]) == (world, regime, scenario):
            return c
    raise KeyError((world, regime, scenario))


# ============================================================================ гейты знака и печатаемая маржа (М§4.5, §14.2)

def c_world_price(res: dict, world: str) -> float:
    """Цена мира (М§8.2): оценка при P(W) = 1 с вероятностями режимов и сценариев прогона — той же формулой,
    что цена слоя, на делителе N_div (М§8.4)."""
    ctx = res["ctx"]
    prs = c_bget(ctx["B"], "joint.reg_prob_given_regime")
    v0 = sum(res["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]]) * c["v_price"]
             for c in res["cells"] if c["world"] == world)
    return c_price_of(v0, ctx["bridge_amount"], ctx["gov"], ctx["A"]["N_div"], ctx["pending_amount"])


def c_point_mass(res: dict) -> dict:
    """Вероятность клетки в точке (М§9): точка — смесь низа и верха с весом λ, поэтому вес мира —
    (1 − λ) × вес слоя «рыночные ставки как есть» + λ × вес слоя «свой взгляд»; режим и сценарий — как в слоях."""
    B = res["ctx"]["B"]
    weights = c_layer_weights(B)
    low, high = weights["macro_neutral"], weights["analytical"]
    prs = c_bget(B, "joint.reg_prob_given_regime")
    lam = res["lam"]
    out = {}
    for c in res["cells"]:
        world = (1.0 - lam) * low.get(c["world"], 0.0) + lam * high.get(c["world"], 0.0)
        out[(c["world"], c["regime"], c["scenario"])] = (world * res["posterior"][c["regime"]]
                                                         * float(prs[c["regime"]][c["scenario"]]))
    return out


def c_volume_sign(book: dict, facts: dict, res: dict | None = None, *, valuation_date=None) -> dict:
    """Числа гейта знака объёмных эффектов (М§4.5): сдвиг точки и цен миров при снятии остановки кредита в
    кризисе (loan_growth_override пуст) и поправок роста режимов (loan_growth_adj = 0). У книги с включённым
    ограничением роста обе стороны сравнения считаются при выключенном ограничении. res — готовый прогон
    этой книги: он служит базой, когда выключать нечего. У книги с ключом checks.volume_sign: {tol} (₽ на
    акцию) результат несёт допуск и условие гейта: ok ложно при сдвиге точки ниже −tol или сдвиге цены мира M
    ниже сдвига цены мира H больше чем на tol; без ключа гейта нет — только числа."""
    spec = c_bopt(book, "checks.volume_sign")
    tol = None
    if spec is not None:
        if not isinstance(spec, dict) or spec.get("tol") is None or float(spec["tol"]) < 0.0:
            raise ControlInputError("checks.volume_sign: нужен tol ≥ 0")
        tol = float(spec["tol"])
    base_book = copy.deepcopy(book)
    rule = c_bopt(base_book, "capital.growth_constraint")
    off = isinstance(rule, dict) and bool(rule.get("enabled"))
    if off:
        rule["enabled"] = False
    free_book = copy.deepcopy(base_book)
    free_book["regimes"][R_CRISIS]["loan_growth_override"] = {}
    for r in c_bget(free_book, "regimes.ids"):
        free_book["regimes"][r]["loan_growth_adj"] = 0.0
    if res is None or off:
        when = valuation_date if res is None else res["ctx"]["clock"]["v"]
        base = c_control_run(base_book, facts, valuation_date=when)
    else:
        base = res
    free = c_control_run(free_book, facts, valuation_date=base["ctx"]["clock"]["v"])
    ref_w = c_bget(base["ctx"]["B"], "nii.transmission.reference_world")
    d_point = free["point"] - base["point"]
    d_world = {w: c_world_price(free, w) - c_world_price(base, w) for w in base["ctx"]["worlds"]}
    ok = None if tol is None else not (d_point < -tol or d_world[W_MKT] < d_world[ref_w] - tol)
    return {"point": base["point"], "point_free": free["point"], "d_point": d_point, "d_world": d_world,
            "market_world": W_MKT, "reference_world": ref_w, "growth_constraint_off": off, "tol": tol, "ok": ok}


def c_stress_sign(book: dict, facts: dict, res: dict | None = None, *, valuation_date=None, tables=None):
    """Гейт знака стресса (ключ книги checks.stress_sign: {loss_step, tol}, оба — млрд ₽; нет ключа — None).

    (а) Убыток: сетка с разовым убытком режима шока, уменьшенным на loss_step (убыток больше); клетка режима
    шока нарушает, если её стоимость выше стоимости книги больше чем на tol. (б) Требование: в каждой паре
    «мир × режим» — по всем режимам, включая режим шока, — сценарий капитала с более высоким требованием Н20.0
    последнего года сетки нарушает, если его операционная прибыль акционеров последнего года выше, чем у
    сценария с более низким требованием, больше чем на tol. Считается на книге как она есть, с её правилом
    роста. Масса — вероятности точки нарушивших клеток (у пары — клетка более строгого сценария); наибольшее
    превышение — наибольший прирост стоимости или прибыли среди нарушений. В table — числа всех клеток и пар,
    не только нарушивших; tables — пара готовых таблиц (их числа от порога не зависят)."""
    spec = c_bopt(book, "checks.stress_sign")
    if spec is None:
        return None
    if not isinstance(spec, dict) or spec.get("loss_step") is None or spec.get("tol") is None:
        raise ControlInputError("checks.stress_sign: нужны loss_step и tol")
    step, tol = float(spec["loss_step"]), float(spec["tol"])
    if step <= 0.0 or tol < 0.0:
        raise ControlInputError("checks.stress_sign: loss_step > 0 и tol ≥ 0")
    if res is None:
        res = c_control_run(book, facts, valuation_date=valuation_date)
    by_loss, by_req = tables if tables is not None else _c_stress_tables(book, facts, res, step)
    bad_loss = [x for x in by_loss if x["dv"] > tol]
    bad_req = [x for x in by_req if x["d_profit"] > tol]
    cells = ({(x["world"], x["regime"], x["scenario"]) for x in bad_loss}
             | {(x["world"], x["regime"], x["stricter"]) for x in bad_req})
    weight = c_point_mass(res)
    excess = [x["dv"] for x in bad_loss] + [x["d_profit"] for x in bad_req]
    return {"loss": {"step": step, "cells": bad_loss, "table": by_loss},
            "requirement": {"cells": bad_req, "table": by_req}, "tol": tol,
            "mass": sum(weight[key] for key in cells), "max_excess": max(excess) if excess else 0.0,
            "worlds": [w for w in res["ctx"]["worlds"] if any(key[0] == w for key in cells)], "ok": not cells}


def _c_stress_tables(book: dict, facts: dict, res: dict, step: float) -> tuple[list, list]:
    """Числа гейта знака стресса: прирост стоимости каждой клетки режима шока при разовом убытке, увеличенном
    на step (пересчёт клеток режима шока на книге с подменой одного ключа), и разность прибыли последнего
    года в каждой паре сценариев с разным требованием Н20.0 последнего года во всех режимах каждого мира — по
    прогону книги res."""
    ctx = res["ctx"]
    scen = list(c_bget(ctx["B"], "capital.reg_scenarios.ids"))
    hit = copy.deepcopy(book)
    loss = hit["regimes"][R_CRISIS]["one_off_loss"]
    loss["amount"] = float(loss["amount"]) - step
    ctx_hit = c_control_context(hit, facts, valuation_date=ctx["clock"]["v"])
    by_loss = []
    for w in ctx["worlds"]:
        for s in scen:
            dv = c_cell_annual(ctx_hit, w, R_CRISIS, s)["v_price"] - c_cell_of(res, w, R_CRISIS, s)["v_price"]
            by_loss.append({"world": w, "regime": R_CRISIS, "scenario": s, "dv": dv})
    by_req = []
    for w in ctx["worlds"]:
        for r in c_bget(ctx["B"], "regimes.ids"):
            last = {s: c_cell_of(res, w, r, s)["rows"][-1] for s in scen}
            for upper in scen:
                for lower in scen:
                    if last[upper]["req20"] > last[lower]["req20"]:
                        by_req.append({"world": w, "regime": r, "stricter": upper, "looser": lower,
                                       "d_profit": last[upper]["ni_sh"] - last[lower]["ni_sh"]})
    return by_loss, by_req


def c_printed_margin(res: dict):
    """Печатаемая маржа после фазы роста (ключ книги checks.nim_lt: {target, tolerance, from_year}; нет ключа —
    None): среднее годовых ЧПМ упр. базиса модальной клетки за годы from_year … последний год сетки. Годовая
    ЧПМ — ЧПД года к среднему пяти концов кварталов процентных активов (М§0.3), в упр. базис — через мост."""
    ctx = res["ctx"]
    spec = c_bopt(ctx["B"], "checks.nim_lt")
    if spec is None:
        return None
    if not isinstance(spec, dict) or any(spec.get(k) is None for k in ("target", "tolerance", "from_year")):
        raise ControlInputError("checks.nim_lt: нужны target, tolerance и from_year")
    start = int(spec["from_year"])
    cell = c_cell_of(res, *res["central"]["cell"])
    by_year = {y: c_to_mgmt(ctx["A"], "nim", row["nim_year"]) for y, row in zip(res["years"], cell["rows"])
               if y >= start and row["nim_year"] is not None}
    if not by_year:
        raise ControlInputError("checks.nim_lt.from_year: на сетке нет полного года не раньше него")
    value = sum(by_year.values()) / len(by_year)
    target, tolerance = float(spec["target"]), float(spec["tolerance"])
    return {"cell": res["central"]["label"], "from_year": start, "target": target, "tolerance": tolerance,
            "value": value, "by_year": by_year, "ok": abs(value - target) <= tolerance}


# ============================================================================ уровни после фазы роста

def c_mix_weights(res: dict) -> dict[str, dict]:
    """Веса клеток четырёх смесей узла уровней: модальная клетка (вес 1), слой «свой взгляд», смесь точки и
    слой «рыночные ставки как есть». Вес клетки в слое — вес мира слоя × вероятность режима после A-P2u ×
    P(s | r) (М§3.4, §9); в смеси точки — λ-смесь двух слоёв."""
    B = res["ctx"]["B"]
    worlds = c_layer_weights(B)
    prs = c_bget(B, "joint.reg_prob_given_regime")

    def c_layer(name):
        return {(c["world"], c["regime"], c["scenario"]): (worlds[name].get(c["world"], 0.0)
                                                           * res["posterior"][c["regime"]]
                                                           * float(prs[c["regime"]][c["scenario"]]))
                for c in res["cells"]}

    return {MIX_MODAL: {tuple(res["central"]["cell"]): 1.0}, LAYER_OWN: c_layer(LAYER_OWN),
            MIX_POINT: c_point_mass(res), LAYER_MARKET: c_layer(LAYER_MARKET)}


def c_year_levels(res: dict, weight: dict) -> dict[int, dict]:
    """Годовые ЧПМ, CoR и C/I смеси клеток с весами weight, упр. базис: год → {nim, cor, cir}.

    Метрика смеси — отношение ожидаемых агрегатов: ожидание числителя к ожиданию знаменателя, а не ожидание
    отношений клеток. Числители — годовые суммы ЧПД, резервов и расходов; знаменатели ЧПМ и CoR — среднее
    пяти концов кварталов процентных активов и кредитов по амортизированной стоимости (М§0.3), знаменатель
    C/I — доход NII + F + INS + MISC + FVR (М§4.6). В упр. базис — через мост. Неполный год якоря значения не
    несёт. У смеси из одной клетки это годовые метрики самой клетки."""
    ctx = res["ctx"]
    A = ctx["A"]
    mix0 = ctx.get("book_rel") is not None
    out = {}
    for i, p in enumerate(ctx["periods"]):
        if p["stub"]:
            continue
        tot = dict.fromkeys(("nii", "iea", "llp", "loans", "opex", "income", "llp_mix0"), 0.0)
        for c in res["cells"]:
            k = weight.get((c["world"], c["regime"], c["scenario"]), 0.0)
            if not k:
                continue
            row = c["rows"][i]
            tot["nii"] += k * row["nii"]
            tot["iea"] += k * _c_ends_mean(row["iea_ends"])
            tot["llp"] += k * row["llp"]
            tot["loans"] += k * _c_ends_mean(row["loans_ac_ends"])
            tot["opex"] += k * row["opex"]
            tot["income"] += k * row["income_cir"]
            if mix0:
                tot["llp_mix0"] += k * row["llp_mix0"]
        if not (tot["iea"] and tot["loans"] and tot["income"]):
            raise ControlInputError(f"уровни года {p['year']}: у смеси нет веса или знаменатель — ноль")
        out[p["year"]] = {"nim": c_to_mgmt(A, "nim", tot["nii"] / tot["iea"]),
                          "cor": c_to_mgmt(A, "cor", tot["llp"] / tot["loans"]),
                          "cir": c_to_mgmt(A, "cir", tot["opex"] / tot["income"])}
        if mix0:
            # CoR на составе якоря (ключ credit.book_relative): резервы смеси при множителях книг, равных единице, к
            # тем же кредитам — её сверяют коридор CoR и гейт сверки с окном фактов
            out[p["year"]]["cor_mix0"] = c_to_mgmt(A, "cor", tot["llp_mix0"] / tot["loans"])
    return out


def c_levels(res: dict, from_year: int | None = None):
    """Уровни после фазы роста: простые средние годовых упр. ЧПМ, CoR и C/I за годы from_year … последний год
    сетки — для модальной клетки, слоя «свой взгляд», смеси точки и слоя «рыночные ставки как есть».
    from_year — аргумент или ключ книги checks.window_backtest.from_year; нет ни того, ни другого — None.
    → {from_year, years, mixes: {смесь: {nim, cor, cir, by_year}}}."""
    if from_year is None:
        spec = c_bopt(res["ctx"]["B"], "checks.window_backtest")
        if spec is None:
            return None
        if not isinstance(spec, dict) or spec.get("from_year") is None:
            raise ControlInputError("checks.window_backtest: нужен from_year")
        from_year = spec["from_year"]
    start = int(from_year)
    mixes, years = {}, []
    for name, weight in c_mix_weights(res).items():
        by_year = {y: v for y, v in c_year_levels(res, weight).items() if y >= start}
        if not by_year:
            raise ControlInputError("уровни после фазы роста: на сетке нет полного года не раньше from_year")
        years = sorted(by_year)
        mixes[name] = {x: sum(v[x] for v in by_year.values()) / len(by_year) for x in ("nim", "cor", "cir")}
        if res["ctx"].get("book_rel") is not None:
            mixes[name]["cor_mix0"] = sum(v["cor_mix0"] for v in by_year.values()) / len(by_year)
        mixes[name]["by_year"] = by_year
    return {"from_year": start, "years": years, "mixes": mixes}


def c_window_backtest(res: dict):
    """Гейт сверки с окном фактов (ключ книги checks.window_backtest: {from_year, cor: [низ, верх], cir: [низ,
    верх]}; нет ключа — None): уровни CoR и C/I слоя «рыночные ставки как есть» — средние за годы from_year …
    последний год сетки — внутри коридоров книги, края включены. Маржа гейтом не сверяется: она печатается."""
    spec = c_bopt(res["ctx"]["B"], "checks.window_backtest")
    if spec is None:
        return None
    lanes = {}
    for x in ("cor", "cir"):
        lane = spec.get(x) if isinstance(spec, dict) else None
        if not isinstance(lane, (list, tuple)) or len(lane) != 2 or float(lane[0]) > float(lane[1]):
            raise ControlInputError(f"checks.window_backtest.{x}: нужен коридор [низ, верх]")
        lanes[x] = (float(lane[0]), float(lane[1]))
    levels = c_levels(res)
    layer = levels["mixes"][LAYER_MARKET]
    if res["ctx"].get("book_rel") is None:
        bad = [x for x, (lo, hi) in lanes.items() if not lo <= layer[x] <= hi]
        return {"from_year": levels["from_year"], "years": levels["years"], "layer": LAYER_MARKET,
                "cor": layer["cor"], "cir": layer["cir"], "nim": layer["nim"], "cor_range": lanes["cor"],
                "cir_range": lanes["cir"], "outside": bad, "ok": not bad}
    # множители CoR по книгам: коридор CoR сверяется на составе якоря (окно фактов — состав банка), реализованная
    # CoR печатается рядом
    seen = {"cor": layer["cor_mix0"], "cir": layer["cir"]}
    bad = [x for x, (lo, hi) in lanes.items() if not lo <= seen[x] <= hi]
    return {"from_year": levels["from_year"], "years": levels["years"], "layer": LAYER_MARKET,
            "cor": seen["cor"], "cor_realized": layer["cor"], "cir": layer["cir"], "nim": layer["nim"],
            "cor_range": lanes["cor"], "cir_range": lanes["cir"], "outside": bad, "ok": not bad}


def c_cir_level(res: dict):
    """Уровень C/I, с которым сверяется цель книги (ключ checks.cir_lt: {target, tolerance, from_year} и
    необязательный scope; нет ключа — None): среднее годовых упр. C/I за годы from_year … последний год сетки.
    Без scope (или scope: modal_cell) — модальная клетка, как у образца; scope: market_layer — слой «рыночные
    ставки как есть», отношение ожидаемых агрегатов."""
    spec = c_bopt(res["ctx"]["B"], "checks.cir_lt")
    if spec is None:
        return None
    if not isinstance(spec, dict) or any(spec.get(k) is None for k in ("target", "tolerance", "from_year")):
        raise ControlInputError("checks.cir_lt: нужны target, tolerance и from_year")
    scope = spec.get("scope")
    if scope not in (None, SCOPE_MODAL, SCOPE_MARKET):
        raise ControlInputError(f"checks.cir_lt.scope: {scope!r}")
    mix = LAYER_MARKET if scope == SCOPE_MARKET else MIX_MODAL
    start = int(spec["from_year"])
    by_year = {y: v["cir"] for y, v in c_year_levels(res, c_mix_weights(res)[mix]).items() if y >= start}
    if not by_year:
        raise ControlInputError("checks.cir_lt.from_year: на сетке нет полного года не раньше него")
    value = sum(by_year.values()) / len(by_year)
    target, tolerance = float(spec["target"]), float(spec["tolerance"])
    return {"scope": scope, "mix": mix, "cell": res["central"]["label"] if mix == MIX_MODAL else None,
            "from_year": start, "target": target, "tolerance": tolerance, "value": value, "by_year": by_year,
            "ok": abs(value - target) <= tolerance}


# ============================================================================ средства клиентов: гейты и путь фондирования

def c_gate_funds_books(ctx: dict, clients: bool) -> list[str]:
    """Книги «средств клиентов» чисел гейтов (М§14.2): пассивы без балансирующей книги опта — средства физлиц и
    клиентов-бизнеса; при checks.client_funds: clients и активном К6 — без ведомых книг К6 (Р10-1: одна величина
    «средства клиентов» везде)."""
    books = ctx["B"]["nii"]["books"]
    out = [b for b, sp in books.items() if sp["side"] != LOANS_SIDE and b != WHOLESALE]
    if clients and ctx.get("driven"):
        out = [b for b in out if b not in ctx["driven"]]
    return out


def c_ratio_of_expectations(parts: dict, probs: dict) -> float:
    """Отношение ожиданий Σ P n / Σ P d по клеткам (parts: клетка → (n, d)); клетки без веса не входят."""
    num = math.fsum(probs[k] * n for k, (n, _) in parts.items() if probs.get(k))
    den = math.fsum(probs[k] * d for k, (_, d) in parts.items() if probs.get(k))
    return num / den


def c_world_key_mean(B: dict, world: str, years) -> float:
    """Средняя ключевая мира за годы years — по дням кварталов: Σ key_q d_q / Σ d_q."""
    num = den = 0.0
    for y in years:
        for q in range(1, QY + 1):
            d = c_q_len(y, q)
            num += c_world_quarter(B, world, "key_rate", y, q) * d
            den += d
    return num / den


def c_world_cell_probs(res: dict, world: str) -> dict:
    """Вероятности клеток мира P(r, s | w) = P(r) P(s | r): режим после A-P2u × P(сценарий | режим) — без веса мира
    (определены и у мира с нулевым весом слоя)."""
    prs = c_bget(res["ctx"]["B"], "joint.reg_prob_given_regime")
    return {(c["world"], c["regime"], c["scenario"]): res["posterior"][c["regime"]]
            * float(prs[c["regime"]][c["scenario"]]) for c in res["cells"] if c["world"] == world}


def c_funds_cost_to_key(res: dict, scope: str | None = None, clients: bool | None = None):
    """Число гейта стоимости средств клиентов к ключевой (ключ checks.funds_cost_to_key: {max, from_year}; числа клеток
    пишутся только при ключах прохода 8 checks.funds_cost_to_key.scope или checks.client_funds — без них None). Годы —
    полные годы от from_year до конца сетки; по клетке — Σ_y Σ_b ȳ_b Ē_b D_y / Σ_y Σ_b Ē_b D_y (годовая форма: средняя
    ставка книги периода × средний остаток × доля года), b — книги средств клиентов (c_gate_funds_books); ключевая мира
    — среднее по дням. scope (по умолчанию — ключ книги): modal_cell — клетка мира с модальным режимом и сценарием,
    world_expectation — отношение ожиданий по клеткам мира с весами P(r) P(s | r) (Р10-6; не ожидание отношений),
    модальная клетка печатается рядом. Гейт: ratio мира больше max; масса — вес таких миров слоя «свой взгляд»."""
    ctx = res["ctx"]
    B, keys = ctx["B"], ctx.get("funds_keys") or {}
    spec = c_bopt(B, "checks.funds_cost_to_key")
    if spec is None or not keys.get("keyed"):
        return None
    if not isinstance(spec, dict) or spec.get("max") is None or spec.get("from_year") is None:
        raise ControlInputError("checks.funds_cost_to_key: нужны max и from_year (М§14.2)")
    scope = keys["scope"] if scope is None else scope
    clients = keys["clients"] if clients is None else clients
    start = int(spec["from_year"])
    idx = [i for i, p in enumerate(ctx["periods"]) if not p["stub"] and p["year"] >= start]
    if not idx:
        raise ControlInputError("checks.funds_cost_to_key.from_year: на сетке нет полного года не раньше него")
    years = [ctx["periods"][i]["year"] for i in idx]
    fb = c_gate_funds_books(ctx, clients)
    parts = {(c["world"], c["regime"], c["scenario"]): (
        math.fsum(c["rows"][i]["funds_cost"][b][0] for i in idx for b in fb),
        math.fsum(c["rows"][i]["funds_cost"][b][1] for i in idx for b in fb)) for c in res["cells"]}
    _, r_m, s_m = res["central"]["cell"]
    by_world = {}
    for w in ctx["worlds"]:
        key = c_world_key_mean(B, w, years)
        expect = c_ratio_of_expectations(parts, c_world_cell_probs(res, w))
        n, d = parts[(w, r_m, s_m)]
        modal = n / d
        label = "/".join((w, r_m, s_m))
        node = {"cost": expect, "key": key, "ratio": expect / key, "cell": f"{w} · ожидание мира",
                "modal_cell": label, "modal_ratio": modal / key}
        if scope == FUNDS_SCOPES[0]:
            node.update(cost=modal, ratio=modal / key, cell=label, expectation_ratio=expect / key)
        by_world[w] = node
    mx = float(spec["max"])
    bad = [w for w, x in by_world.items() if x["ratio"] > mx]
    own = c_layer_weights(B)[LAYER_OWN]
    return {"from_year": start, "to_year": years[-1], "max": mx, "scope": scope, "clients": clients, "books": fb,
            "by_world": by_world, "worlds": bad, "mass": sum(float(own.get(w, 0.0)) for w in bad), "ok": not bad}


def c_funding_path(res: dict, clients: bool | None = None) -> dict:
    """Путь фондирования (М§14.5) и числа гейта wholesale_share (М§14.2) своим счётом: на дату якоря и на конец каждого
    года — кредиты к средствам клиентов и доля опта wholesale / (средства клиентов + опт); средства клиентов — книги
    c_gate_funds_books (при checks.client_funds: clients — без книг К6, Р10-1); у смеси точки — отношение ожидаемых
    остатков клеток, у модальной клетки — её остатки; cells — доли опта клеток по годам (гейт: вне коридора книги)."""
    ctx = res["ctx"]
    keys = ctx.get("funds_keys") or {}
    clients = keys.get("clients", False) if clients is None else clients
    drv = list(ctx.get("driven") or {}) if clients else []

    def c_ends(c, i):
        row = c["rows"][i]
        funds = row["funds"] - math.fsum(row["driven_end"][b] for b in drv)
        return row["loans"], funds, row["wholesale"]

    E0 = ctx["A"]["E0"]
    f0 = math.fsum(E0[b] for b in c_gate_funds_books(ctx, clients))
    l0 = math.fsum(E0[b] for b in ctx["loans"])
    out = {"years": list(res["years"]), "cell": res["central"]["label"], "clients": clients,
           "anchor": {"loans_to_funds": l0 / f0, "wholesale_share": E0[WHOLESALE] / (f0 + E0[WHOLESALE])}}
    pm = c_point_mass(res)
    modal = c_cell_of(res, *res["central"]["cell"])
    mix = {"loans_to_funds": [], "wholesale_share": []}
    mod = {"loans_to_funds": [], "wholesale_share": []}
    cells = {}
    for i in range(len(res["years"])):
        tot = [0.0, 0.0, 0.0]
        for c in res["cells"]:
            ends = c_ends(c, i)
            k = pm[(c["world"], c["regime"], c["scenario"])]
            for j in range(3):
                tot[j] += k * ends[j]
            cells.setdefault("/".join((c["world"], c["regime"], c["scenario"])), []).append(ends[2] / (ends[1] + ends[2]))
        mix["loans_to_funds"].append(tot[0] / tot[1])
        mix["wholesale_share"].append(tot[2] / (tot[1] + tot[2]))
        lo, fu, wh = c_ends(modal, i)
        mod["loans_to_funds"].append(lo / fu)
        mod["wholesale_share"].append(wh / (fu + wh))
    out.update(mix=mix, modal_cell=mod, cells=cells)
    return out


# ============================================================================ DPS истории (М§5.2, прил. C)

def c_history_kind(B: dict) -> str:
    """Вид теста истории выплат (М§5.2): exact без ключа, cap — потолок политики, none — выключен."""
    kind = c_bopt(B, "dividends.policy.history_test", HIST_EXACT)
    if kind not in (HIST_EXACT, HIST_CAP, HIST_NONE):
        raise ControlInputError(f"dividends.policy.history_test: {kind!r} (М§5.2)")
    return kind


def c_cap_history_ctl(B: dict, facts: dict) -> list[dict]:
    """Тест истории вида cap (М§5.2): по годам фактов dividends.years — сумма объявленных пулов решений
    года против потолка политики × отчётная прибыль акционеров; неполный год — диагностика (ok = None)."""
    cap = c_bopt(B, "dividends.policy.cap")
    if cap is None or not 0.0 < float(cap) <= 1.0:
        raise ControlInputError("dividends.policy.cap: нужен потолок в (0; 1] при тесте истории cap (М§5.2)")
    dv = facts.get("dividends", {})
    out = []
    for year, node in sorted((dv.get("years") or {}).items(), key=lambda kv: int(kv[0])):
        ni = _c_nodeval(node.get("ni_shareholders"))
        if ni is None:
            raise ControlInputError(f"dividends.years.{year}.ni_shareholders: null (М§5.2)")
        pool = 0.0
        for rec in dv.get("history", []):
            if int(_c_nodeval(rec.get("year"))) != int(year):
                continue
            part = _c_nodeval(rec.get("pool_declared"))
            if part is None:
                raise ControlInputError(f"строка dividends.history {rec.get('period')} без pool_declared (М§5.2)")
            pool += float(part)
        complete = bool(_c_nodeval(node.get("complete")))
        limit = float(cap) * float(ni)
        out.append({"year": int(year), "pool": pool, "ni_shareholders": float(ni),
                    "share": pool / float(ni) if float(ni) else None, "cap": float(cap), "limit": limit,
                    "complete": complete, "ok": (pool <= limit + 1e-9) if complete else None})
    return out


def c_dps_history_ctl(B: dict, facts: dict) -> list[dict]:
    """Тест истории выплат вида книги (М§5.2). exact — формула пула на фактах истории в точной десятичной
    арифметике, округление книги; cap — строки теста потолка; none — пусто."""
    kind = c_history_kind(B)
    if kind == HIST_CAP:
        return c_cap_history_ctl(B, facts)
    if kind == HIST_NONE:
        return []
    mode = c_bget(B, "dividends.policy.dps_rounding")
    n_iss = Decimal(str(c_fnum(facts, "shares", "issued_total")))
    out = []
    for rec in facts.get("dividends", {}).get("history", []):
        vals = {k: _c_nodeval(rec.get(k)) for k in ("year", "ni_shareholders", "at1_coupon",
                                                 "tax_statutory", "dps_ordinary")}
        if any(vals[k] is None for k in ("ni_shareholders", "at1_coupon", "tax_statutory")):
            continue
        year = int(vals["year"])
        payout = Decimal(str(c_traj_mean(c_bget(B, "dividends.policy.payout"), year, range(1, QY + 1))))
        base = (Decimal(str(vals["ni_shareholders"]))
                - Decimal(str(vals["at1_coupon"])) * (Decimal(1) - Decimal(str(vals["tax_statutory"]))))
        exact = payout * base * Decimal(1000) / n_iss
        rnd = ROUND_CEILING if mode == "ceil_kopeck" else ROUND_HALF_UP
        dps = exact.quantize(Decimal("0.01"), rounding=rnd)
        declared = vals["dps_ordinary"]
        out.append({"year": year, "exact": float(exact), "dps": float(dps),
                    "declared": None if declared is None else float(declared),
                    "ok": declared is not None and dps == Decimal(str(declared)).quantize(Decimal("0.01"))})
    return out


# ============================================================================ печать сводки

def _c_fmt(x, nd=1):
    return "—" if x is None else f"{x:,.{nd}f}".replace(",", " ")


def c_summary_lines(res: dict, central=None) -> list[str]:
    ctx = res["ctx"]
    rule = central is None
    central = tuple(res["central"]["cell"] if rule else central)
    A = ctx["A"]
    tr = res["transmission"]
    branch = ("годовая, квартальный проход капитала" + (", рост ограничен капиталом" if ctx["growth"] else "")
              if ctx["quarterly"] else "годовая")
    L = [f"Контрольная модель ({branch}), книга " + str(c_bget(ctx["B"], "meta.version")),
         f"дата оценки {ctx['clock']['v']}, период p0 = {ctx['periods'][ctx['clock']['p0']]['label']}, "
         f"e = {ctx['clock']['e']:.4f}",
         f"передача: σ0_A = {tr['sigma0']:.6f}, σ0_L = {tr['sigma0_liab']:.6f} (доля активов {tr['split']}, "
         f"к спредам с {ctx['sigma0_from']}), φ = {tr['phi']:.6f}, "
         f"T_real = {tr['t_real']:.6f}, target_eng = {tr['target_eng']:.6f}, T(W) = "
         + ", ".join(f"{w} {v:.4f}" for w, v in tr["t_local"].items()),
         f"раскладка сжатия: доля кредитных книг {tr['phi_split']}, φ_A = {tr['phi_assets']:.6f}, "
         f"φ_L = {tr['phi_liab']:.6f}; кредитная маржа стационара: "
         + ", ".join(f"{w} {v:.4f}" for w, v in tr["loan_margin"].items()),
         "эффективные LT-спреды: " + "; ".join(
             f"{b}: " + ", ".join(f"{w} {v:.4f}" for w, v in ws.items()) for b, ws in tr["lt_spread"].items()),
         "пары: " + ", ".join(f"{k} {'—' if v is None else f'{v:.6f}'}" for k, v in tr["pairs"].items())
         + f"; ROE-эквивалент T* = {tr['roe_equiv']:.4f}, пар: "
         + ", ".join(f"{k} {'—' if v is None else f'{v:.4f}'}" for k, v in tr["roe_equiv_pairs"].items()),
         f"RWA_0 модели = {_c_fmt(ctx['rwa0'])} (Базель {_c_fmt(A['rwa_basel'])})",
         f"вероятности режимов: " + ", ".join(f"{r} {p:.4f}" for r, p in res["posterior"].items()),
         f"мост B(v) = {_c_fmt(res['bridge_amount'], 2)}, D_pend = {_c_fmt(res['pending_amount'], 2)}, "
         f"дисконт за управление = {res['governance']:.4f}, год шока кризиса {res['shock_year']}"]
    if ctx.get("book_rel") is not None:
        L.append("множители CoR по книгам после нормировки на составе якоря: "
                 + ", ".join(f"{b} {v:.4f}" for b, v in ctx["book_rel"].items()))
    if tr.get("phi_shares"):
        # ключи прохода 9 — строки только при ключе (без ключей сводка прежняя)
        L.append("доли сжатия книг к опоре между мирами (Р11-1): " + ", ".join(
            f"{b} {v}" for b, v in tr["phi_shares"].items()) + "; наклон книг между мирами M и N: " + ", ".join(
            f"{b} {'—' if v is None else f'{v:.4f}'}" for b, v in tr["book_slopes"].items()))
    if ctx.get("k6_out"):
        L.append(f"средства клиентов балансовой механики (Р11-2) — без книг К6 {', '.join(ctx['k6_out'])}: доля опта якоря "
                 f"{ctx['wtf_anchor']:.6f}, база опта {ctx['wtf']}")
    if ctx.get("nci_real") is not None:
        L.append(f"неконтролирующие в реальных рублях (Р11-3): pnl.nci_real = {ctx['nci_real']} — доля pnl.nci_share не "
                 f"читается")
    for name in LAYERS:
        ly = res["layers"][name]
        L.append(f"слой {name}: V0 = {_c_fmt(ly['v0'])}, BV_v = {_c_fmt(ly['bv_v'])}, P/B = {ly['pb']:.3f}, "
                 f"цена = {ly['price']:.2f} ₽")
    L.append(f"низ = {res['low']:.2f} ₽, верх = {res['high']:.2f} ₽, λ = {res['lam']}, "
             f"точка = {res['point']:.2f} ₽")
    c = c_cell_of(res, *central)
    cap0 = c["anchor_capital"]
    L.append(f"якорь: Н20.0 модели {cap0['n20']:.4f} (факт {A['n20_fact']:.4f}), "
             f"второй норматив модели {cap0['n11']:.4f} (факт слота n1_1_bank {A['n11_fact']:.4f})")
    if rule:
        L.append(f"центральная клетка по правилу: {res['central']['label']}, вероятность в слое «свой взгляд» "
                 f"{res['central']['probability']:.4f}, вес сценария {res['central']['scenario_weight']:.2f}")
    L.append(f"клетка {'/'.join(central)}: V = {_c_fmt(c['v_ri'])}, V_DDM = {_c_fmt(c['v_ddm'])}, BV_v = {_c_fmt(c['bv_v'])}, "
             f"X_T = {_c_fmt(c['x_t'])}, запас LA над минимумом = {_c_fmt(c['hla'])} (порог связывания "
             f"{_c_fmt(c['h_star'])}), доход на избыток = "
             f"{_c_fmt(c['y_x'])} (ставка смеси {c['y_bal']:.4f}), ROE'_T = {c['roe_t']:.4f}, "
             f"k_T = {c['k_t']:.4f}, g_T = {c['g_t']:.4f}, "
             f"TV_RI = {_c_fmt(c['tv_ri'])}, доля терминала = {c['terminal_share']:.3f}")
    if "n_t" in c:
        bb = ctx["bb"]
        L.append(f"выкуп ({bb['rule']}, цена книги {bb['p_book']}, квартал даты книги {bb['qb']}): выкуплено "
                 + _c_fmt(sum(r["bb"] for r in c["rows"]), 2) + f" млрд ₽, акций на конец сетки {_c_fmt(c['n_t'], 3)} "
                 f"(в обращении на якоре {_c_fmt(A['N_out'], 3)}), цена клетки на оставшуюся акцию {c['s_price']:.4f} ₽; "
                 "цены покупок: " + ", ".join(f"{x:.3f}" for r in c["rows"] for x, b in zip(r["p_bar_q"], r["bb_q"]) if b))
    if "terminal_fixed" in c:
        t = c["terminal_fixed"]
        L.append(f"постоянные части терминала (λ_F = {t['lam_f']}, части: {', '.join(t['parts'])}): F_A {_c_fmt(t['f_a'])}, "
                 f"R_F {_c_fmt(t['r_f'])}, κ {t['kappa']:.4f} ({t['binding']}), F_K {_c_fmt(t['f_k'])}, "
                 f"D_F {_c_fmt(t['d_f'])}, I_F {_c_fmt(t['i_f'], 2)}, m_L {_c_fmt(t['m_l'], 2)}, B {_c_fmt(t['business_capital'])}, "
                 f"X_B {_c_fmt(t['x_b'])}, φ {t['phi']}")
    head = ["год", "ЧПД", "резервы", "FVC", "ЧКД", "расходы", "непроф.", "прочее", "PBT", "ЧП акц.", "CI", "BV",
            "RWA", "Н20.0", "Н20.1", "ЧПМ", "CoR", "ROE", "DPS за год"]
    L.append(" | ".join(head))
    for p, row in zip(ctx["periods"], c["rows"]):
        dec = c["decisions"].get(p["year"])
        L.append(" | ".join([p["label"] + ("*" if p["stub"] else ""), _c_fmt(row["nii"]), _c_fmt(row["llp"]),
                             _c_fmt(row["fvc"]),
                             _c_fmt(row["fees"]), _c_fmt(row["opex"]), _c_fmt(row["noncore"]), _c_fmt(row["misc"]),
                             _c_fmt(row["pbt"]), _c_fmt(row["ni_sh"]), _c_fmt(row["ci"]), _c_fmt(row["bv"]),
                             _c_fmt(row["rwa"]), f"{row['n20']:.4f}", f"{row['n11']:.4f}",
                             f"{row['nim']:.4f}", f"{row['cor']:.4f}", f"{row['roe']:.4f}",
                             "—" if dec is None else f"{dec['dps']:.2f}"]))
    if ctx["quarterly"]:
        L.append("год | рост кредитных книг: потенциальный | фактический | доля урезанного | min λ | "
                 "навёрстывание | треб. Н20.0 с глиссадой | Н20.1 с глиссадой | дивиденд модели")
        for p, row in zip(ctx["periods"], c["rows"]):
            L.append(" | ".join([p["label"] + ("*" if p["stub"] else ""),
                                 "—" if row["growth_potential"] is None else f"{row['growth_potential']:.4f}",
                                 "—" if row["growth_actual"] is None else f"{row['growth_actual']:.4f}",
                                 f"{row['cut_share']:.4f}", f"{row['lam_min']:.4f}", _c_fmt(row["catch_up"]),
                                 f"{row['req20_glide']:.4f}", f"{row['req11_glide']:.4f}", _c_fmt(row["div_model"], 2)]))
        L.append("DPS кварталов прибыли: " + ", ".join(
            f"{d['period']} {d['dps']:.2f} ({d['source']})" for d in c["decisions_q"]))
    L.append("клетки (V_RI, млрд ₽; цена ₽; |V_DDM/V_RI − 1|):")
    for cc in res["cells"]:
        L.append(f"  {cc['world']} {cc['regime']:<8} {cc['scenario']:<8} V = {_c_fmt(cc['v_ri'])} "
                 f"цена {cc['price']:.1f} P/B {cc['pb']:.3f} ROE'_T {cc['roe_t']:.4f} k_T {cc['k_t']:.4f} "
                 f"X_T {_c_fmt(cc['x_t'])} ddm {abs(cc['v_ddm'] / cc['v_ri'] - 1):.1e}")
    for h in res["dps_history"]:
        if res["history_test"] == HIST_CAP:
            verdict = "диагностика (год неполный)" if h["ok"] is None else "ok" if h["ok"] else "ПРЕВЫШЕНИЕ"
            L.append(f"потолок выплат {h['year']}: объявлено {_c_fmt(h['pool'], 3)}, отчётная прибыль акционеров "
                     f"{_c_fmt(h['ni_shareholders'], 3)}, доля {h['share']:.4f} при потолке {h['cap']}, {verdict}")
            continue
        L.append(f"DPS истории {h['year']}: формула {h['dps']:.2f} (точно {h['exact']:.5f}), "
                 f"объявлен {h['declared']}, {'ok' if h['ok'] else 'РАСХОЖДЕНИЕ'}")
    if res["divisor"] != res["shares_out"]:
        L.append(f"делитель N_div = {_c_fmt(res['divisor'], 3)} млн шт. (в обращении {_c_fmt(res['shares_out'], 3)})")
    return L


def c_gate_lines(book: dict, facts: dict, res: dict) -> list[str]:
    """Числа гейтов знака, печатаемая маржа и уровни после фазы роста строками сводки (ключ --gates): два-три
    прогона сетки сверх основного; уровни считаются по клеткам основного прогона."""
    sign = c_volume_sign(book, facts, res)
    L = ["знак объёмных эффектов" + (" (обе стороны — без ограничения роста)" if sign["growth_constraint_off"] else "")
         + f": точка {sign['point']:.2f} → {sign['point_free']:.2f} ₽, сдвиг {sign['d_point']:+.2f} ₽; миры: "
         + ", ".join(f"{w} {d:+.2f}" for w, d in sign["d_world"].items())
         + ("; ключа checks.volume_sign в книге нет — гейта нет" if sign["ok"] is None
            else f"; допуск {sign['tol']} ₽, условие гейта {'выполнено' if sign['ok'] else 'нарушено'}")]
    stress = c_stress_sign(book, facts, res)
    if stress is None:
        L.append("знак стресса: ключа checks.stress_sign в книге нет — гейта нет")
    else:
        L.append(f"знак стресса (убыток больше на {_c_fmt(stress['loss']['step'])} млрд ₽, допуск {stress['tol']} млрд ₽): "
                 f"клеток с ростом стоимости {len(stress['loss']['cells'])} из {len(stress['loss']['table'])}, "
                 f"пар сценариев с ростом прибыли {len(stress['requirement']['cells'])} из "
                 f"{len(stress['requirement']['table'])}; масса {stress['mass']:.4f}, наибольшее превышение "
                 f"{_c_fmt(stress['max_excess'], 2)} млрд ₽" + ("" if stress["ok"] else "; миры: " + ", ".join(stress["worlds"])))
        for x in stress["loss"]["cells"]:
            L.append(f"  убыток: {x['world']}/{x['regime']}/{x['scenario']} стоимость {x['dv']:+.2f} млрд ₽")
        for x in stress["requirement"]["cells"]:
            L.append(f"  требование: {x['world']}/{x['regime']} {x['stricter']} против {x['looser']} "
                     f"прибыль {x['d_profit']:+.2f} млрд ₽")
    margin = c_printed_margin(res)
    if margin is not None:
        L.append(f"печатаемая маржа после фазы роста, клетка {margin['cell']}, с {margin['from_year']} года: "
                 f"{margin['value']:.4f} при цели {margin['target']} ± {margin['tolerance']}")
    window = c_window_backtest(res)
    if window is not None:
        names = {MIX_MODAL: "модальная клетка", LAYER_OWN: "слой «свой взгляд»", MIX_POINT: "смесь точки",
                 LAYER_MARKET: "слой «рыночные ставки как есть»"}
        for mix, lv in c_levels(res)["mixes"].items():
            L.append(f"уровни с {window['from_year']} года, {names[mix]}: ЧПМ {lv['nim']:.4f}, CoR {lv['cor']:.4f}"
                     + (f" (на составе якоря {lv['cor_mix0']:.4f})" if "cor_mix0" in lv else "")
                     + f", C/I {lv['cir']:.4f}")
        L.append(f"сверка с окном фактов, слой «рыночные ставки как есть»: CoR "
                 + ("на составе якоря " if "cor_realized" in window else "") + f"{window['cor']:.4f} в коридоре "
                 f"{window['cor_range'][0]}…{window['cor_range'][1]}, C/I {window['cir']:.4f} в коридоре "
                 f"{window['cir_range'][0]}…{window['cir_range'][1]} — "
                 + ("выполнено" if window["ok"] else "нарушено: " + ", ".join(window["outside"])))
    level = c_cir_level(res)
    if level is not None:
        where = "слой «рыночные ставки как есть»" if level["cell"] is None else f"клетка {level['cell']}"
        L.append(f"уровень C/I для цели книги, {where}, с {level['from_year']} года: {level['value']:.4f} при цели "
                 f"{level['target']} ± {level['tolerance']}")
    fc = c_funds_cost_to_key(res)
    if fc is not None:
        # Р10-6, Р10-1 (ключи прохода 8 в checks): число гейта мира и модальная клетка рядом; без ключей строк нет
        who = "без книг К6" if fc["clients"] else "все книги средств"
        L.append(f"стоимость средств клиентов к ключевой ({'ожидание мира' if fc['scope'] == FUNDS_SCOPES[1] else 'модальная клетка'}"
                 f"; средства клиентов — {who}), {fc['from_year']}–{fc['to_year']}, порог {fc['max']}: "
                 + ", ".join(f"{w} {x['ratio']:.6f} (клетка {x['modal_cell']} {x['modal_ratio']:.6f})"
                             for w, x in fc["by_world"].items())
                 + (" — в пределах" if fc["ok"] else f" — выше порога: {', '.join(fc['worlds'])}, масса {fc['mass']:.4f}"))
    if (res["ctx"].get("funds_keys") or {}).get("keyed"):
        fp = c_funding_path(res)
        L.append(f"путь фондирования (средства клиентов — {'без книг К6' if fp['clients'] else 'все книги средств'}): "
                 f"доля опта на якоре {fp['anchor']['wholesale_share']:.4f}, смесь точки по годам "
                 + " ".join(f"{x:.4f}" for x in fp["mix"]["wholesale_share"])
                 + f"; наибольшая доля опта клетки {max(max(v) for v in fp['cells'].values()):.4f}")
    return L


def _c_jsonable(x):
    if isinstance(x, dict):
        return {str(k): _c_jsonable(v) for k, v in x.items() if k != "ctx"}
    if isinstance(x, (list, tuple)):
        return [_c_jsonable(v) for v in x]
    if isinstance(x, (dt.date,)):
        return x.isoformat()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def c_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Контрольная модель: годовая, с квартальным проходом капитала (М§17)")
    ap.add_argument("--book", help="машинная книга (по умолчанию data/assumptions/assumptions.yaml)")
    ap.add_argument("--draft", action="store_true", help="шаблон книги + миры и надстройка (своя сборка)")
    ap.add_argument("--worlds-lt", default="", help="узел LT кривой миров для --draft: N=<доля>,H=<доля>")
    ap.add_argument("--facts", help="каталог фактов (по умолчанию data/facts)")
    ap.add_argument("--date", help="дата оценки YYYY-MM-DD (по умолчанию — книги)")
    ap.add_argument("--json", help="записать полный результат в JSON")
    ap.add_argument("--gates", action="store_true", help="числа гейтов знака, печатаемая маржа и уровни после фазы роста (ещё два-три прогона)")
    a = ap.parse_args(argv)
    if a.draft:
        lt = {k: float(v) for k, v in (kv.split("=") for kv in a.worlds_lt.split(",") if kv)}
        book = c_book_from_draft(curve_lt=lt)
    else:
        book = c_book_machine(Path(a.book) if a.book else None)
    facts = c_facts_bundle(Path(a.facts) if a.facts else None)
    res = c_control_run(book, facts, valuation_date=a.date)
    for line in c_summary_lines(res) + (c_gate_lines(book, facts, res) if a.gates else []):
        print(line)
    if a.json:
        Path(a.json).write_bytes(json.dumps(_c_jsonable(res), ensure_ascii=False, indent=1).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(c_cli())
