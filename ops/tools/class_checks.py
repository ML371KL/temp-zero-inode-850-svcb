"""Проверки классов ошибок в модели (PLAYBOOK семейства, §2а «Проверки классов в модели») — на сетке, без полосы.

    python -B ops/tools/class_checks.py [--book ФАЙЛ] [--facts КАТАЛОГ] [--config ФАЙЛ] [--only 1,2,…] [--json ФАЙЛ]
                                        [--workers N] [--quiet]

Шесть классов ошибок, которые у панели ВТБ находились по одному экземпляру за круг (PLAYBOOK §2а), проверяются на
модели одним запуском, функциями ядра (`model/`), которое инструмент не правит:

  1. капитал и баланс сходятся в каждой клетке и каждом году: инварианты ядра (`model.checks.check_invariants`:
     bv_identity, balance_identity, pnl_identity, ddm_equals_ri — как есть, не повторяя) и сверх них — тождество
     капитала по годам, дивиденды к выплате, фонд FVOCI, капитал норматива из капитала МСФО (две формы одного
     капитала), состав баланса из книг, решения о дивиденде и уменьшение капитала, терминал (TV_DDM = BV_Q + TV_RI,
     BV* = BV_Q − X_T); то же — на обоих концах каждой оси полосы;
  2. числа одной клетки не переносятся на другие: (а) каждая клетка, посчитанная одна (свои общие величины прогона),
     равна себе в сетке бит в бит; (б) возмущение входа одной клетки (CoR, сдвиг ЧПМ, требование, вычет сценария —
     подменой в процессе инструмента) меняет только её; (в) возмущение пути режима, сценария или мира через книгу
     меняет только клетки каналов, по которым оно прошло, и каждый такой канал — законная связь файла; без (а), без
     единой подмены и без единого возмущения — «не проверялось», а не «зелёно»; в строке класса — счёт всех трёх;
  3. продление явных лет на год (ключ книги `meta.last_period`; новые полугодия миров — значением последнего, как их
     читает терминал) меняет точку и оба слоя не больше допуска;
  4. каждая ось полосы в центре даёт точку и клетки бит в бит — одна и все оси разом, как прогон полосы, — а на концах
     меняет ровно объявленные ключи книги (и законных спутников файла);
  5. переходные слагаемые (перечень файла; ряды — как их читает ядро, среди них путь доли неработающих денег
     `cash_share` = c_q − c_Q, Р6-1) нейтральны вне лет окна — в центре и на концах осей; селектор с режимом, книгой,
     сектором или сценарием, которых нет в книге, — отказ (код 2); правило, у чьих рядов в центре нет ни одного
     значения, — замечание «не проверялось» и счёт таких правил в строке класса (все правила такие — класс «не
     проверялось»);
  6. центр суждения равен правилу устава (таблица файла; пустая — «правил нет», а не «зелёно»).

Законные связи, допуски, перечень переходных слагаемых и правила центров — суждения устава калибровки панели
(`data/assumptions/class_checks.yaml`); до устава там заготовки с пометкой. Срабатывание — находка для перепроверки, а
не повод подгонять модель: инструмент ничего не пишет в дерево (запись — только в названный `--json`), подмены живут
только в его процессе и снимаются, а в конце он пересчитывает сетку книги и сверяет точку и клетки с первыми бит в бит.

Машинное время (PLAYBOOK §6): подмены входов клеток, оси в центре и концы осей — независимые задачи; `--workers N`
раздаёт их рабочим процессам частями и сводит по порядку задач, поэтому запись запуска та же при любом числе процессов
(сверено с последовательным прогоном; тест). На книге Т: около минуты подряд, около 20 с на семи процессах.

Коды возврата: 0 — ни одна проверка не сработала; 1 — сработала или не отработала хотя бы одна; 2 — негодные входы.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import math
import pickle
import re
import struct
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model import cell as cellmod  # noqa: E402
from model import uncertainty as U  # noqa: E402
from model.book import LIQUIDITY, SECURITIES, WHOLESALE, Book, load_book, load_facts  # noqa: E402
from model.book_schema import BookError, FactsError  # noqa: E402
from model.cell import Prepared, run_cell  # noqa: E402
from model.checks import check_invariants, ddm_ri_max  # noqa: E402
from model.grid import GridRun, live_from_book, run_grid  # noqa: E402
from model.nii import REFERENCE_REGIME  # noqa: E402
from model.paths import shift_trajectory  # noqa: E402
from model.worlds import BASE_WORLD  # noqa: E402

SCHEMA = "class-checks-v1"
CONFIG = ROOT / "data" / "assumptions" / "class_checks.yaml"
OK, FIRED, NO_RULES, WAITING, ERROR = "ok", "fired", "no_rules", "waiting", "error"
STATUS_WORDS = {OK: "зелёно", FIRED: "СРАБОТАЛА", NO_RULES: "правил нет", WAITING: "ждёт прохода ядра",
                ERROR: "НЕ ОТРАБОТАЛА"}
CLASS_TITLES = {
    1: "капитал и баланс сходятся в каждой клетке и каждом году",
    2: "числа одной клетки не переносятся на другие клетки, кроме законных связей",
    3: "продление явных лет на год не меняет оценку в пределах допуска",
    4: "ось в центре равна центру бит в бит и меняет объявленный ключ книги",
    5: "переходное слагаемое нейтрально вне лет окна фактов",
    6: "центр суждения равен правилу устава",
}
ALL_CLASSES = (1, 2, 3, 4, 5, 6)
CORE_IDENTITIES = ("bv_identity", "balance_identity", "pnl_identity", "ddm_equals_ri")
# Законные связи, которые инструмент умеет узнавать по каналу (М§3–§4, §12); файл устава отмечает, какие законны.
LINKS = ("world", "regime", "scenario", "a_p2u", "transmission", "reference_world", "kappa_reference_world")
SCOPE_LINKS = ("world", "regime", "scenario")   # связь «общий мир, режим, сценарий» — круг клеток самого возмущения
COMMON = "common"                         # канал «общая величина подготовки» — законным в файле не бывает
CELL_INPUTS = ("cor", "nim_shift", "requirement", "deduction")
# Поля подготовки прогона, которые выводит решение передачи ставки (М§4.5): канал «transmission».
TRANSMISSION_FIELDS = frozenset({"spreads", "phi", "phi_assets", "phi_liab", "phi_weights", "reference_world"})
RULES = ("midpoint", "axis_midpoint", "mean", "median", "value")
# Решения ведущего Совкомбанка № 11, раздел А: тип центра у каждого правила класса 6 — оценщик устава для этой величины. Суждения:
# А — статистика окна (Р6-2), Б — совместный подбор той же механикой, что ядро, В — середина диапазона прочтений без оценщика,
# Г — одно чистое наблюдение (ось 0 … двойное), Д — свидетельств нет (середина области), Е — конвенция семейства. Не суждения:
# «факт» (факт якоря или сборщика) и «тождество» (сумма, форма, определение варианта, число, выведенное правилом). Правило без
# типа и ось книги без правила-суждения с типом — находка класса 6 («ключ с центром или осью без типа — красный»).
CENTRE_TYPES = ("А", "Б", "В", "Г", "Д", "Е")
OTHER_TYPES = ("факт", "тождество")
TYPE_WORDS = {"А": "статистика окна", "Б": "совместный подбор", "В": "середина прочтений", "Г": "одно наблюдение",
              "Д": "середина области", "Е": "конвенция семейства", "факт": "факт", "тождество": "тождество"}
AXIS_IN_EXPR = re.compile(r"a\['paths'\]\[0\] == '([^']+)'")
# Ключ с центром (решения ведущего Совкомбанка № 11, раздел А: «тип — у каждого ключа книги с центром или осью»; проверка исполнения
# круга 11 — инструмент судил только оси): строка ключа шаблона книги, комментарий которой несёт метку суждения [В…] или [Р/В…]
# (легенда меток — шапка шаблона; шаблон — поле centre_template файла связей). Ключ с центром без правила класса 6 с типом — находка (ключ правила — сам ключ, его предок
# или потомок; либо формула правила читает ключ или его потомка через B()/O()).
JUDGMENT_TAG = re.compile(r"\[(?:В|Р/В)[\]:,\s]")
KEY_LINE = re.compile(r'^(\s*)("?[A-Za-z0-9_]+"?):(?:\s+(.*))?$')
BOOK_REF = re.compile(r"""\b[BO]\('([^']+)'""")
AXIS_NAME_IN_EXPR = re.compile(r"a\['name'\] == '([^']+)'")
NOT_CHECKED = "не проверялось"            # слова статуса NO_RULES у класса, чьи правила есть, а проверять нечего
KEEP = 200                                # находок одной проверки в записи (счётчик — полный)
SHOW = 4                                  # находок одной проверки на экране


class Refused(Exception):
    """Негодные входы — код 2."""


# ------------------------------------------------------------------ результат проверки


@dataclass
class Check:
    cls: int
    key: str
    title: str
    status: str = OK
    count: int = 0                         # находок всего
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    numbers: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    words: str = ""                        # свои слова статуса (пусто — STATUS_WORDS)

    def fire(self, line: str | Callable[[], str]) -> None:
        """Находка; строка — сама или функцией (её зовут, только пока находка ложится в запись)."""
        self.count += 1
        if len(self.findings) < KEEP:
            self.findings.append(line() if callable(line) else line)
        if self.status == OK:
            self.status = FIRED

    def fail(self, line: str) -> None:
        self.fire(line)
        self.status = ERROR

    def part(self) -> dict[str, Any]:
        """Находки части проверки простыми данными — так задача отдаёт их из рабочего процесса."""
        return {"status": self.status, "count": self.count, "findings": list(self.findings)}

    def absorb(self, part: Mapping[str, Any]) -> None:
        """Находки части проверки (одна задача — ось, конец оси, вход клетки) — по порядку задач, как при счёте подряд."""
        for line in part["findings"]:
            if len(self.findings) < KEEP:
                self.findings.append(line)
        self.count += part["count"]
        if part["status"] == ERROR or (part["status"] == FIRED and self.status == OK):
            self.status = part["status"]

    def record(self) -> dict[str, Any]:
        return {"cls": self.cls, "key": self.key, "title": self.title, "status": self.status,
                "status_words": self.words or STATUS_WORDS[self.status], "tally": tally(self.key, self.numbers),
                "count": self.count, "findings": self.findings, "notes": self.notes, "numbers": self.numbers,
                "seconds": round(self.seconds, 2)}

    def not_checked(self, note: str) -> None:
        """Правила есть, а проверять нечего: статус NO_RULES словами «не проверялось» (не зелёно и не флаг)."""
        if self.status == OK:
            self.status, self.words = NO_RULES, NOT_CHECKED
        self.notes.append(note)


def tally(key: str, n: Mapping[str, Any]) -> str:
    """Счёт проверки для строки класса (инструмент, блок перевывода, лист решения): сколько проверено на деле —
    зелёный статус без счёта не отличить от пустой проверки. Классы 2 и 5; у прочих — пусто."""
    if key == "cross_cell":
        iso = n.get("isolation")
        return (f"клеток одна — {iso['cells'] if iso else 'не сверялись'}, подмен входа клетки — {n.get('cell_runs', 0)}, "
                f"возмущений книги — {len(n.get('book_inputs') or [])}")
    if key == "transitional" and "rules" in n:
        empty = sum(1 for r in n.get("centre", []) if not r.get("values"))
        return f"правил {n['rules']}" + (f", из них без рядов (не проверялось) — {empty}" if n["rules"] else "")
    return ""


def flag_lines(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Красные флаги: каждое срабатывание (и каждая проверка, которая не отработала) — строкой с числом находок и
    первыми из них."""
    out = []
    for c in checks:
        if c["status"] not in (FIRED, ERROR):
            continue
        head = (f"класс {c['cls']} ({c['title']}): проверка {c['key']} {STATUS_WORDS[c['status']]} — находок "
                f"{c['count']}")
        first = "; ".join(c["findings"][:2])
        out.append(head + (": " + first if first else "") + (" …" if c["count"] > 2 else ""))
    return out


# ------------------------------------------------------------------ общие помощники


def bits(x: float) -> str:
    """Число бит в бит (шестнадцатеричная запись double)."""
    return struct.pack("<d", float(x)).hex()


def rub(x: float, nd: int = 2) -> str:
    """Разность для печати: знак, запятая, минус — знаком минуса."""
    return f"{x:+.{nd}f}".replace(".", ",").replace("-", "−")


def num(x: float, nd: int = 2) -> str:
    """Число для печати: запятая, минус — знаком минуса."""
    return f"{x:.{nd}f}".replace(".", ",").replace("-", "−")


def canon(x: Any) -> Any:
    """Каноническая запись величины для отпечатка: множества — по порядку, словари — по ключам, классы данных —
    по полям; числа — как есть (запись pickle хранит double бит в бит)."""
    if isinstance(x, (frozenset, set)):
        return ("set",) + tuple(sorted(canon(v) for v in x))
    if isinstance(x, Mapping):
        return ("map",) + tuple((str(k), canon(v)) for k, v in sorted(x.items(), key=lambda kv: str(kv[0])))
    if isinstance(x, (list, tuple)):
        return tuple(canon(v) for v in x)
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return (type(x).__name__,) + tuple((f.name, canon(getattr(x, f.name))) for f in dataclasses.fields(x))
    return x


def fingerprint(obj: Any) -> bytes:
    return hashlib.sha256(pickle.dumps(canon(obj), protocol=pickle.HIGHEST_PROTOCOL)).digest()


def same_object(a: Any, b: Any) -> bool:
    return fingerprint(a) == fingerprint(b)


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Листья дерева книги по точечным путям (индекс списка — числом, как в путях книги)."""
    out: dict[str, Any] = {}
    if isinstance(obj, Mapping):
        if not obj and prefix:
            out[prefix] = {}
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        if not obj and prefix:
            out[prefix] = []
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}.{i}" if prefix else str(i)))
    else:
        out[prefix] = obj
    return out


def leaf_equal(a: Any, b: Any) -> bool:
    """Значения листа равны: числа — по значению (целое 1 и 1.0 — одно число; NaN равен NaN), прочее — ==."""
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return a == b
    return type(a) is type(b) and a == b


def changed_leaves(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    fa, fb = flatten(before), flatten(after)
    return sorted(k for k in set(fa) | set(fb) if k not in fa or k not in fb or not leaf_equal(fa[k], fb[k]))


def under(leaf: str, path: str) -> bool:
    return leaf == path or leaf.startswith(path + ".")


def cell_keys(book: Book) -> list[tuple[str, str, str]]:
    return [(w, r, s) for w in book.get("worlds.ids") for r in book.get("regimes.ids")
            for s in book.get("capital.reg_scenarios.ids")]


def label(key: Sequence[str]) -> str:
    return "/".join(key)


def listed(items: Sequence[str], n: int = 6) -> str:
    items = list(items)
    return ", ".join(items[:n]) + (f" и ещё {len(items) - n}" if len(items) > n else "")


# ------------------------------------------------------------------ стенд: книга, факты, сетка книги


@dataclass
class Bench:
    book: Book
    facts: Any
    live: Any
    cfg: Mapping[str, Any]
    base: GridRun
    prints: dict[tuple[str, str, str], bytes]
    keys: list[tuple[str, str, str]]

    def run(self, book: Book | None = None) -> GridRun:
        return run_grid(book if book is not None else self.book, self.facts, self.live)

    def changed(self, run: GridRun) -> set[tuple[str, str, str]]:
        return {c.key for c in run.cells if fingerprint(c) != self.prints[c.key]}

    def blob(self) -> bytes:
        """Книга, факты и файл связей — для рабочих процессов: каждый строит свой стенд сам (та же сетка книги)."""
        return pickle.dumps((self.book, self.facts, self.cfg), protocol=pickle.HIGHEST_PROTOCOL)


def make_bench(book: Book, facts: Any, cfg: Mapping[str, Any]) -> Bench:
    live = live_from_book(book, facts)
    base = run_grid(book, facts, live)
    return Bench(book=book, facts=facts, live=live, cfg=cfg, base=base,
                 prints={c.key: fingerprint(c) for c in base.cells}, keys=cell_keys(book))


def all_axes(book: Book) -> list[Mapping[str, Any]]:
    """Оси полосы и оси вне полосы — по порядку книги."""
    return list(book.get("valuation.uncertainty.axes")) + list(U.off_band_axes(book))


# ------------------------------------------------------------------ класс 1: тождества капитала и баланса


IDENTITIES = {
    "capital_year": "капитал на конец года = на конец прошлого + совокупный доход − дивиденды года (− выкуп акций)",
    "dividends_payable": "дивиденды к выплате: на конец = на начало + решённые − выплаченные",
    "fvoci_reserve": "OCI квартала = изменение фонда FVOCI внутри капитала",
    "regulatory_capital": "капитал норматива из капитала МСФО: вычеты, неаудированная прибыль, инструменты, Н20.0 и Н20.1",
    "balance_composition": "итоги баланса — из остатков книг: кредиты, средства клиентов, процентные активы, активы, пассивы",
    "dividend_decisions": "уменьшение капитала дивидендами квартала = сумма решений квартала",
    "terminal": "терминал: TV_DDM = BV_Q + TV_RI, BV* = BV_Q − X_T",
}


def identity_rows(run: GridRun) -> Iterator[tuple[str, str, float, float]]:
    """(тождество, где, левая часть, правая часть) по клеткам, кварталам и годам сетки — из рядов клетки и
    постоянных подготовки прогона; формулы — М§4.9–§4.11, §5.7, §7."""
    ctx = run.ctx
    p: Prepared = ctx.prep
    tl, cap, roles = ctx.timeline, p.cap, p.roles
    Q = tl.Q
    for c in run.cells:
        v = c.quarters
        lab = c.label
        sc = p.scenarios[c.scenario]
        for y in range(tl.anchor_year, tl.last_year + 1):
            qs = [q for q in tl.quarters_of_year(y) if 1 <= q <= Q]
            if not qs:
                continue
            flow = sum(v["ci"][q] - v["div"][q] for q in qs)
            if "bb" in v:                       # выкуп по цене мира — распределение акционерам, не CI (М§5.6)
                flow -= sum(v["bb"][q] for q in qs)
            yield "capital_year", f"{lab} {y}", v["bv"][qs[-1]], v["bv"][qs[0] - 1] + flow
        by_q: dict[int, float] = defaultdict(float)
        quarterly = p.calendar is not None
        if quarterly:
            for d in c.decisions:
                if d.q is not None:
                    by_q[d.q] += d.div
        for q in range(1, Q + 1):
            where = f"{lab} {tl.period(q)}"
            yield "dividends_payable", where, v["dp"][q], v["dp"][q - 1] + v["div"][q] - v["pay"][q]
            yield "fvoci_reserve", where, v["oci"][q], v["reserve"][q] - v["reserve"][q - 1]
            bvreg = v["bv"][q] + v["dpreg"][q] - (1 - cap.fvoci_recognition) * v["reserve"][q]
            rwa = v["rwa"][q]
            yield "regulatory_capital", where + " K20", v["k20"][q], bvreg - v["ded20"][q] + cap.at1 + p.t2[q]
            yield ("regulatory_capital", where + " K11", v["k11"][q],
                   bvreg - max(v["e_unaudited"][q], 0.0) - v["ded11"][q])
            yield "regulatory_capital", where + " вычет Н20.0", v["ded20"][q], cap.ded20_0 * rwa / cap.rwa0
            yield "regulatory_capital", where + " вычет Н20.1", v["ded11"][q], cap.ded11_0 * rwa / cap.rwa0
            yield "regulatory_capital", where + " Н20.0", v["n20"][q], v["k20"][q] / rwa + cap.gap20 - sc.ded_pp20[q]
            yield "regulatory_capital", where + " Н20.1", v["n11"][q], v["k11"][q] / rwa + cap.gap11 - sc.ded_pp11[q]
            bal = {b: c.books[b]["balance"][q] for b in roles.names}
            loans = sum(bal[b] for b in roles.loans)
            funds = sum(bal[b] for b in roles.funds)
            yield "balance_composition", where + " кредиты", v["loans"][q], loans
            yield "balance_composition", where + " средства клиентов", v["funds"][q], funds
            yield "balance_composition", where + " процентные активы", v["iea"][q], sum(bal[b] for b in roles.assets)
            yield ("balance_composition", where + " активы", v["assets"][q],
                   loans - v["allowance"][q] + bal[SECURITIES] + bal[LIQUIDITY] + v["other_assets"][q])
            yield ("balance_composition", where + " пассивы и капитал", v["liabilities_equity"][q],
                   funds + bal[WHOLESALE] + v["other_liabilities"][q] + v["dp"][q] + v["bv"][q] + p.af.at1 + p.af.nci)
            if quarterly:
                yield "dividend_decisions", where, v["div"][q], by_q.get(q, 0.0)
        yield "terminal", f"{lab} TV_DDM", c.tv_ddm, v["bv"][Q] + c.tv_ri
        yield "terminal", f"{lab} BV*", c.bv_star, v["bv"][Q] - c.x_t


def residual(lhs: float, rhs: float) -> float:
    scale = max(1.0, abs(lhs), abs(rhs))
    r = abs(lhs - rhs) / scale
    return r if r == r else math.inf


def scan_identities(run: GridRun, chk: Check, tol: float, where: str, worst: dict[str, float]) -> int:
    """Тождества одной сетки: инварианты ядра и тождества класса; → число проверенных равенств."""
    for f in check_invariants(run):
        if f.name in CORE_IDENTITIES and f.fired:
            chk.fire(f"{where}инвариант ядра {f.name}: {f.message}")
    worst["ddm_equals_ri"] = max(worst.get("ddm_equals_ri", 0.0), ddm_ri_max(run))
    n = 0
    for name, at, lhs, rhs in identity_rows(run):
        n += 1
        r = residual(lhs, rhs)
        worst[name] = max(worst.get(name, 0.0), r)
        if not r <= tol:
            chk.fire(lambda: f"{where}{IDENTITIES[name]} — {at}: {lhs:.10g} против {rhs:.10g} (невязка {r:.1e})")
    return n


# ------------------------------------------------------------------ класс 2: числа одной клетки


@contextlib.contextmanager
def perturbed_cell(target: tuple[str, str, str], kind: str, size: float) -> Iterator[None]:
    """Подмена входа одной клетки в процессе инструмента: после построения клетки `target` (основной проход, не
    предварительный проход A-P2u) её ряд входа сдвигается на `size` во всех кварталах сетки. Ядро не правится;
    подмена снимается на выходе."""
    if kind not in CELL_INPUTS:
        raise Refused(f"cross_cell.cell_inputs: незнакомый вход {kind!r} (знакомые: {', '.join(CELL_INPUTS)})")
    original = cellmod._Cell.__init__

    def shifted(series: Sequence[float]) -> tuple[float, ...]:
        return tuple(x + size if q >= 1 else x for q, x in enumerate(series))

    def init(self, ctx, world, regime, scenario, *, preliminary=False, shared=None):
        original(self, ctx, world, regime, scenario, preliminary=preliminary, shared=shared)
        if preliminary or (world, regime, scenario) != tuple(target):
            return
        if kind == "cor":
            self.cor = shifted(self.cor)
        elif kind == "nim_shift":
            self.nim_shift = shifted(self.nim_shift)
        elif kind == "requirement":
            self.req20g, self.req11g = shifted(self.req20g), shifted(self.req11g)
        else:
            self.sc = dataclasses.replace(self.sc, ded_pp20=shifted(self.sc.ded_pp20),
                                          ded_pp11=shifted(self.sc.ded_pp11))

    cellmod._Cell.__init__ = init
    try:
        yield
    finally:
        cellmod._Cell.__init__ = original


def cell_task(bench: Bench, key: tuple[str, str, str], kind: str, size: float) -> dict[str, Any]:
    """Вход `kind` одной клетки сдвинут на `size` подменой в процессе: меняется только она."""
    part = Check(2, "cross_cell", "")
    with perturbed_cell(key, kind, size):
        run = bench.run()
    changed = bench.changed(run)
    if key not in changed:
        part.fire(f"вход «{kind}» клетки {label(key)} не дошёл до её чисел (сдвиг {size:g})")
    other = sorted(changed - {key})
    if other:
        part.fire(f"вход «{kind}» клетки {label(key)} (сдвиг {size:g}) меняет другие клетки: "
                  f"{listed([label(k) for k in other])}")
    return part.part()


def channels(ctx0: Any, ctx1: Any, keys: Sequence[tuple[str, str, str]]) -> list[tuple[str, str, set]]:
    """Каналы, по которым возмущение книги дошло до клеток: (связь, что изменилось, клетки, которые это читают).
    Сравниваются подготовка прогона по полям (пути режимов и сценариев — по одному), пути и дисконты миров,
    отклонения и вероятности A-P2u."""
    out: list[tuple[str, str, set]] = []
    p0, p1 = ctx0.prep, ctx1.prep
    every = set(keys)
    of = lambda i, x: {k for k in keys if k[i] == x}  # noqa: E731
    for f in dataclasses.fields(Prepared):
        a, b = getattr(p0, f.name), getattr(p1, f.name)
        if f.name == "regimes":
            for r in sorted(set(a) | set(b)):
                if r not in a or r not in b or not same_object(a[r], b[r]):
                    out.append(("regime", f"путь режима {r}", of(1, r)))
        elif f.name in ("scenarios", "glide"):
            for s in sorted(set(a) | set(b)):
                if s not in a or s not in b or not same_object(a[s], b[s]):
                    out.append(("scenario", f"{'путь' if f.name == 'scenarios' else 'глиссада'} сценария {s}",
                                of(2, s)))
        elif not same_object(a, b):
            out.append(("transmission" if f.name in TRANSMISSION_FIELDS else COMMON, f"подготовка прогона: {f.name}",
                        every))
    ref = p1.reference_world
    kappa = p1.kappa_world or BASE_WORLD
    for w in ctx1.worlds:
        if w not in ctx0.worlds or not same_object(ctx0.worlds[w], ctx1.worlds[w]):
            out.append(("world", f"путь мира {w}", of(0, w)))
            if w == ref:
                out.append(("reference_world", f"мир-опора передачи {w}", every))
            if w == kappa:
                out.append(("kappa_reference_world", f"мир-опора κ-добавки {w}", every))
        if w not in ctx0.discounts or not same_object(ctx0.discounts[w], ctx1.discounts[w]):
            out.append(("world", f"дисконт мира {w}", of(0, w)))
    for r in sorted(set(ctx0.deviations) | set(ctx1.deviations)):
        if not same_object(ctx0.deviations.get(r), ctx1.deviations.get(r)):
            out.append(("a_p2u", f"отклонения A-P2u режима {r}", of(1, r)))
    if not same_object(ctx0.posterior, ctx1.posterior):
        out.append(("a_p2u", "вероятности режимов после наблюдений", set()))
    return out


def expand(path: str, book: Book) -> list[str]:
    ids = {"{world}": book.get("worlds.ids"), "{regime}": book.get("regimes.ids"),
           "{scenario}": book.get("capital.reg_scenarios.ids")}
    out = [path]
    for mark, values in ids.items():
        out = [p.replace(mark, str(v)) for p in out for v in values] if any(mark in p for p in out) else out
    return out


def class2(bench: Bench, chk: Check) -> None:
    cfg = bench.cfg.get("cross_cell") or {}
    legal = set((cfg.get("legal_links") or {}).keys())
    unknown = sorted(legal - set(LINKS))
    if unknown:
        raise Refused(f"cross_cell.legal_links: незнакомые связи {unknown} (знакомые: {', '.join(LINKS)})")
    chk.numbers["legal_links"] = sorted(legal)
    base = bench.base
    # (а) клетка одна — свои общие величины прогона
    if cfg.get("isolation", True):
        bad = []
        for c in base.cells:
            alone = run_cell(base.ctx, c.world, c.regime, c.scenario)
            if fingerprint(alone) != bench.prints[c.key]:
                bad.append(c.label)
                chk.fire(f"клетка {c.label}, посчитанная одна, не равна себе в сетке: V {alone.v_ri:.6f} против "
                         f"{c.v_ri:.6f} — общие величины прогона несут числа другой клетки")
        chk.numbers["isolation"] = {"cells": len(base.cells), "differ": bad}
    # (б) вход одной клетки — подменой в процессе (задачи — по рабочим процессам, если они есть)
    targets = bench.keys if cfg.get("cells", "all") == "all" else [tuple(str(x).split("/")) for x in cfg["cells"]]
    for key in targets:
        if key not in bench.prints:
            raise Refused(f"cross_cell.cells: нет клетки {label(key)}")
    items = [(key, str(spec["input"]), float(spec["size"])) for spec in cfg.get("cell_inputs") or [] for key in targets]
    for part in fan(bench, "cell", items):
        chk.absorb(part)
    chk.numbers["cell_runs"] = len(items)
    # (в) вход мира, режима, сценария — через книгу
    book_rows = []
    for spec in cfg.get("book_inputs") or []:
        for path in expand(str(spec["path"]), bench.book):
            size = float(spec["shift"])
            try:
                trial = bench.book.with_overrides({path: shift_trajectory(bench.book.get(path), size)})
                run = bench.run(trial)
            except (BookError, FactsError) as exc:
                chk.fail(f"возмущение {path} на {size:g}: книга не считается — {exc}")
                continue
            chans = channels(base.ctx, run.ctx, bench.keys)
            changed = bench.changed(run)
            reach = set().union(*(cells for _, _, cells in chans)) if chans else set()
            lawful = set().union(*(cells for link, _, cells in chans if link in legal)) if chans else set()
            scoped = set().union(*(cells for link, _, cells in chans if link in SCOPE_LINKS)) if chans else set()
            used = sorted({link for link, _, cells in chans
                           if cells & (changed if link in SCOPE_LINKS else changed - scoped)})
            row = {"path": path, "shift": size, "changed": len(changed), "links": used,
                   "channels": [what for _, what, _ in chans]}
            book_rows.append(row)
            if not changed:
                chk.fire(f"возмущение {path} на {size:g} не дошло ни до одной клетки")
            loose = sorted(changed - reach)
            if loose:
                chk.fire(f"возмущение {path} на {size:g} меняет клетки без канала: {listed([label(k) for k in loose])} "
                         "— перенос чисел мимо законных связей")
            illegal = sorted((changed & reach) - lawful)
            if illegal:
                links = sorted({link for link, _, cells in chans if link not in legal and cells & set(illegal)})
                chk.fire(f"возмущение {path} на {size:g} меняет клетки {listed([label(k) for k in illegal])} по связи, "
                         f"которой нет среди законных: {', '.join(links)}")
    chk.numbers["book_inputs"] = book_rows
    if not cfg.get("isolation", True) and not items and not book_rows and chk.status == OK:
        chk.not_checked("в разделе cross_cell нет ни подмен входов клеток, ни возмущений книги, а клетка одна не "
                        "сверяется (isolation: false) — проверка пустая, не зелёная")


# ------------------------------------------------------------------ класс 3: продление явных лет


def extended_book(book: Book, years: int) -> Book:
    """Книга с явным участком длиннее на `years` лет: `meta.last_period` — тот же квартал на `years` лет позже; новые
    полугодия траекторий миров — значением последнего полугодия (так их читает терминал, М§0.4, §7). Прочие
    траектории книги продолжаются своими правилами (LT и «последнее значение навсегда»)."""
    last = str(book.get("meta.last_period"))
    year, quarter = int(last[:4]), last[4:]
    ov: dict[str, Any] = {"meta.last_period": f"{year + years}{quarter}"}
    for w in book.get("worlds.ids"):
        for name, traj in (book.get(f"worlds.{w}") or {}).items():
            if not isinstance(traj, Mapping) or f"{year}H2" not in traj:
                continue
            for y in range(year + 1, year + years + 1):
                for h in ("H1", "H2"):
                    ov[f"worlds.{w}.{name}.{y}{h}"] = traj[f"{year}H2"]
    return book.with_overrides(ov, create=True)


def class3(bench: Bench, chk: Check) -> None:
    cfg = bench.cfg.get("horizon") or {}
    years = int(cfg.get("extend_years", 1))
    step = float(bench.book.get("valuation.headline.print_step"))
    tol = float(cfg.get("tol_print_steps", 0.5)) * step
    base = bench.base
    try:
        longer = extended_book(bench.book, years)
        run = bench.run(longer)
    except (BookError, FactsError) as exc:
        chk.fail(f"книга с явным участком длиннее на {years} г. не считается: {exc}")
        return
    prob = base.layers["analytical"].prob
    rows = {}
    for name, a, b in (("точка", base.point, run.point), ("низ (слой «рыночные ставки как есть»)", base.low, run.low),
                       ("верх (слой «свой взгляд»)", base.high, run.high)):
        rows[name] = {"book": a, "longer": b, "delta": b - a}
        if not abs(b - a) <= tol:
            chk.fire(f"{name}: {num(a)} → {num(b)} ₽ ({rub(b - a)} ₽, {rub(100 * (b / a - 1), 2)} %) при продлении "
                     f"явных лет на {years} г.; допуск ±{num(tol)} ₽")
    by_cell = {label(c.key): run.cell(*c.key).v_ri / c.v_ri - 1 for c in base.cells}
    worst = max(by_cell, key=lambda k: abs(by_cell[k]))
    d_roe = sum(prob[c.key] * (run.cell(*c.key).roe_t - c.roe_t) for c in base.cells)
    chk.numbers.update(years=years, tol_rub=tol, rows=rows, worst_cell=worst, worst_cell_rel=by_cell[worst],
                       roe_t_delta_analytical=d_roe, last_period=str(longer.get("meta.last_period")))
    chk.notes.append(f"наибольшее изменение клетки — {worst} {rub(100 * by_cell[worst], 2)} %; ROE_T слоя «свой "
                     f"взгляд» {rub(100 * d_roe, 3)} п.п. (за год явного участка доходность ещё "
                     f"{'снижается' if d_roe < 0 else 'растёт' if d_roe > 0 else 'не меняется'})")


# ------------------------------------------------------------------ класс 4: оси в центре и на концах


def centre_task(bench: Bench, index: int) -> dict[str, Any]:
    """Ось `index` (порядок `all_axes`) в положении 0: ключи книги те же, точка, слои и клетки — бит в бит."""
    part = Check(4, "axes", "")
    base, book = bench.base, bench.book
    ax = all_axes(book)[index]
    name = str(ax.get("name"))
    try:
        ov = U.axis_overrides(book, ax, 0.0)
        trial = U.trial_book(book, ov)
    except BookError as exc:
        part.fail(f"ось «{name}» в центре: подмена не строится — {exc}")
        return part.part()
    moved = changed_leaves(book.data, trial.data)
    if moved:
        part.fire(f"ось «{name}» в центре меняет ключи книги: {listed(moved)}")
    run = bench.run(trial)
    off = [n for n, a, b in (("точка", base.point, run.point), ("низ", base.low, run.low),
                             ("верх", base.high, run.high)) if bits(a) != bits(b)]
    if off:
        part.fire(f"ось «{name}» в центре: {', '.join(off)} не равны книге бит в бит (точка {run.point!r} против "
                  f"{base.point!r})")
    cells = sorted(bench.changed(run))
    if cells:
        part.fire(f"ось «{name}» в центре меняет клетки: {listed([label(k) for k in cells])}")
    return part.part()


def class4_centre(bench: Bench, chk: Check) -> None:
    base, book = bench.base, bench.book
    axes = all_axes(book)
    for part in fan(bench, "centre", [(i,) for i in range(len(axes))]):
        chk.absorb(part)
    band_axes = list(book.get("valuation.uncertainty.axes"))
    trial = U.draw_book(book, band_axes, [0.0] * len(band_axes))
    light = run_grid(trial, bench.facts, bench.live, summary=True)
    if bits(light.point) != bits(base.point):
        chk.fire(f"все оси полосы в центре разом (как прогон полосы): точка {light.point!r} против {base.point!r}")
    moved = changed_leaves(book.data, trial.data)
    if moved:
        chk.fire(f"все оси полосы в центре разом меняют ключи книги: {listed(moved)}")
    chk.numbers["axes"] = len(axes)


def class4_end(bench: Bench, chk: Check, ax: Mapping[str, Any], s: float, ov: Mapping[str, Any], trial: Book) -> None:
    """Конец оси: изменившиеся листья книги — ровно под объявленными путями оси и её законными спутниками; каждый
    объявленный путь, который подмена меняет, изменился."""
    companions = (bench.cfg.get("axes") or {}).get("companions") or {}
    declared = [str(p) for p in ax["paths"]]
    allowed = declared + [str(c) for p in declared for c in companions.get(p, [])]
    moved = changed_leaves(bench.book.data, trial.data)
    name, end = str(ax.get("name")), "high" if s > 0 else "low"
    extra = [leaf for leaf in moved if not any(under(leaf, p) for p in allowed)]
    if extra:
        chk.fire(f"ось «{name}», конец {end}: меняет ключи вне объявленных — {listed(extra)}")
    for path in declared:
        if path in ov and not same_value(ov[path], bench.book.get(path)) and not any(under(leaf, path) for leaf in moved):
            chk.fire(f"ось «{name}», конец {end}: объявленный ключ {path} в книге конца не изменился")


def same_value(a: Any, b: Any) -> bool:
    fa, fb = flatten({"x": a}), flatten({"x": b})
    return set(fa) == set(fb) and all(leaf_equal(fa[k], fb[k]) for k in fa)


# ------------------------------------------------------------------ класс 5: переходные слагаемые


def _per_quarter(ctx: Any, series: Sequence[float], name: str) -> list[tuple[str, int, Any, float]]:
    tl = ctx.timeline
    return [(f"{name} {tl.period(q)}", tl.year(q), q, float(series[q])) for q in range(1, tl.Q + 1)]


def _by_year(ctx: Any, table: Mapping[int, float], name: str) -> list[tuple[str, int, Any, float]]:
    tl = ctx.timeline
    return [(f"{name} {y}", int(y), int(y), float(v)) for y, v in sorted(table.items())
            if tl.anchor_year <= int(y) <= tl.last_year]


def _growth_effect(ctx: Any, kind: str) -> dict[str, list[tuple[str, int, Any, float]]]:
    """Эффект премии роста в годовом темпе — функциями клетки ядра (`loan_growth`, `funds_growth`): темп с премией
    книги минус темп той же клетки без премии; клетка — (первый мир, режим-опора передачи, первый сценарий)."""
    p = ctx.prep
    tl = ctx.timeline
    world = next(iter(ctx.worlds))
    regime = REFERENCE_REGIME if REFERENCE_REGIME in p.regimes else next(iter(p.regimes))
    scenario = next(iter(p.scenarios))
    if kind == "loan":
        bare = dataclasses.replace(p, loan_drift=None, loan_share_drift=0.0)
    else:
        bare = dataclasses.replace(p, funds_drift=None, funds_share_drift=0.0, funds_drift_q={})
    with_drift = cellmod._Cell(ctx, world, regime, scenario, preliminary=True)
    without = cellmod._Cell(dataclasses.replace(ctx, prep=bare), world, regime, scenario, preliminary=True)
    out: dict[str, list] = {}
    years = range(tl.anchor_year, tl.last_year + 1)
    if kind == "loan":
        for b in p.roles.loans:
            sector = str(p.books[b]["sector"])
            out.setdefault(sector, [(f"премия {sector} {y}", y, y, with_drift.loan_growth(b, y) - without.loan_growth(b, y))
                                    for y in years])
    else:
        for seg in ("retail", "corporate"):
            out[seg] = [(f"премия {seg} {y}К{n}", y, (y, n),
                         with_drift.funds_growth(seg, y, n) - without.funds_growth(seg, y, n))
                        for y in years for n in (1, 2, 3, 4) if 1 <= tl.index(f"{y}Q{n}") <= tl.Q]
    return out


def series_items(ctx: Any, selector: str) -> dict[str, list[tuple[str, int, Any, float]]]:
    """Ряды переходного слагаемого по селектору файла — как их читает ядро: {имя ряда: [(где, год, ключ, значение)]}.
    Ключ — квартал q или год; значение `None` у «absent» не бывает: такие ряды несут только годы, где слагаемое есть."""
    p: Prepared = ctx.prep
    head, _, rest = selector.partition(".")

    def known(names: Any, sel: str, what: str) -> None:
        """Селектор называет режим, книгу, сектор или сценарий, которых нет в книге, — отказ: опечатка давала бы
        пустой перечень рядов и молчаливое «зелёно»."""
        if sel not in ("", "*") and sel not in set(names):
            raise Refused(f"transitional: в селекторе {selector!r} {what} {sel!r}, а в книге такого нет "
                          f"(есть: {', '.join(map(str, names)) or '—'})")

    pick = lambda names: [n for n in names if rest in ("", "*") or n == rest.split(".")[0]]  # noqa: E731
    out: dict[str, list] = {}
    if head in ("near", "fees_gvw", "ins_gvw", "opex_real", "other_movements", "dn", "t2"):
        out[head] = _per_quarter(ctx, getattr(p, head), head)
    elif head == "loan_drift":
        effect = _growth_effect(ctx, "loan")
        known(effect, rest, "сектор кредитов")
        out = {k: v for k, v in effect.items() if rest in ("", "*") or k == rest}
    elif head == "funds_drift":
        effect = _growth_effect(ctx, "funds")
        known(effect, rest, "сегмент средств клиентов")
        out = {k: v for k, v in effect.items() if rest in ("", "*") or k == rest}
    elif head == "regimes":
        r_sel, _, what = rest.partition(".")
        known(p.regimes, r_sel, "режим")
        for r in [r for r in p.regimes if r_sel in ("", "*") or r == r_sel]:
            rg = p.regimes[r]
            name = f"{r}.{what}"
            if what == "loan_adj":
                out[name] = _by_year(ctx, rg.loan_adj, name)
            elif what == "override":
                out[name] = _by_year(ctx, rg.override, name)
            elif what == "one_off":
                out[name] = ([] if rg.one_off_q is None else
                             [(f"{name} {ctx.timeline.period(rg.one_off_q)}", ctx.timeline.year(rg.one_off_q),
                               rg.one_off_q, float(rg.one_off_amount))])
            elif what == "rwa_mult":
                if rg.rwa_mult is not None:
                    out[name] = _per_quarter(ctx, rg.rwa_mult, name)
            elif what == "nim_shift":
                out[name] = _per_quarter(ctx, rg.nim_shift, name)
            elif what == "cor":
                out[name] = _per_quarter(ctx, rg.cor_engine, name)
            else:
                raise Refused(f"transitional: незнакомый ряд режима {what!r}")
    elif head == "deviations":
        known(p.regimes, rest, "режим")
        for r, dev in ctx.deviations.items():
            if rest in ("", "*") or r == rest:
                for k in ("cor", "nim"):
                    if k in dev:
                        out[f"{r}.{k}"] = _per_quarter(ctx, dev[k], f"δ {r}.{k}")
    elif head == "spreads":
        known(p.spreads, rest.split(".")[0], "книга ЧПД со спредом")
        for b in pick(list(p.spreads)):
            out[b] = _per_quarter(ctx, p.spreads[b], f"спред {b}")
    elif head == "glide":
        known(p.scenarios, rest.split(".")[0], "сценарий капитала")
        if p.growth is not None:
            for s in pick(list(p.glide)):
                sc = p.scenarios[s]
                g20, g11 = p.glide[s]
                out[f"{s}.n20"] = _per_quarter(ctx, [a - b for a, b in zip(g20, sc.req20)], f"глиссада {s} Н20.0")
                out[f"{s}.n11"] = _per_quarter(ctx, [a - b for a, b in zip(g11, sc.req11)], f"глиссада {s} Н20.1")
    elif head == "tax_one_off":
        out["tax_one_off"] = ([] if p.ot_q is None else
                              [(f"разовый налог {ctx.timeline.period(p.ot_q)}", ctx.timeline.year(p.ot_q), p.ot_q,
                                float(p.ot_amount))])
    elif head == "share_root":
        # корень κ номинальной части франшизы строки в смеси базы расходов (Р8-6, проход ядра 6, М§4.7): ряд κ_q из
        # p.share_nominal {строка: (λ, κ_q, ряд H)}; без ключа (или ключ строкой не читается) — рядов нет, правило «не проверялось»
        nominal = getattr(p, "share_nominal", None) or {}
        if rest not in ("", "*", "fees", "insurance"):
            raise Refused(f"transitional: в селекторе {selector!r} строка {rest!r} — у ключа opex.line_share_roots строки fees, insurance")
        for line in [n for n in nominal if rest in ("", "*") or n == rest]:
            out[f"share_root.{line}"] = _per_quarter(ctx, list(nominal[line][1]), f"κ {line}")
    elif head == "driver_root":
        # корень ρ номинальной части книг К6 (Р9-1, проход ядра 7, М§4.3): ряд ρ_q из p.driver_roots {книга: (строка, ρ_q)};
        # без ключа (или ключ строкой ни одной книги не ведёт) — рядов нет, правило «не проверялось»
        roots = getattr(p, "driver_roots", None) or {}
        if rest not in ("", "*", "fees", "insurance"):
            raise Refused(f"transitional: в селекторе {selector!r} строка {rest!r} — у ключа volumes.liability_driver_roots строки fees, insurance")
        for b, (line, series) in roots.items():
            if rest in ("", "*") or line == rest:
                out[f"driver_root.{line}.{b}"] = _per_quarter(ctx, list(series), f"ρ {line} ({b})")
    elif head == "cash_share":
        # путь доли неработающих денег к доле книги (Р6-1, М§4.3): c_q − c_Q по кварталам; без доли книги (нет ключа К8,
        # share: anchor) ряда нет — правило «не проверялось»
        cash = p.cash
        if cash is not None and cash.share_q is not None:
            out[head] = _per_quarter(ctx, [c - cash.share_q[-1] for c in cash.share_q], "доля денег c_q − c_Q")
    else:
        raise Refused(f"transitional: незнакомый ряд {selector!r}")
    return out


def transitional_breaks(ctx: Any, rule: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Нарушения одного правила переходного слагаемого на подготовке прогона `ctx` и сводка: рядов, значений вне
    окна, ненейтральных значений в окне (слагаемое действует), наибольшее отклонение от нейтрального вне окна."""
    until = int(rule["until"])
    start = rule.get("from")
    tol = float(rule.get("tol", 0.0))
    neutral = rule.get("neutral", 0.0)
    out: list[str] = []
    stats = {"series": 0, "values": 0, "outside": 0, "active_inside": 0, "max_outside": 0.0}
    for name, items in series_items(ctx, str(rule["series"])).items():
        stats["series"] += 1
        stats["values"] += len(items)
        if not items:
            continue
        last = items[-1][3]
        for where, year, _, value in items:
            target = None if neutral == "absent" else last if neutral == "last" else float(neutral)
            inside = year <= until and (start is None or year >= int(start))
            if inside:
                if target is None or abs(value - target) > tol:
                    stats["active_inside"] += 1
                continue
            stats["outside"] += 1
            if target is None:
                out.append(f"{where}: {value:.6g} (слагаемое есть, а вне окна его быть не должно)")
                continue
            dev = abs(value - target)
            stats["max_outside"] = max(stats["max_outside"], dev if dev == dev else math.inf)
            if not dev <= tol:
                out.append(f"{where}: {value:.6g} при нейтральном {target:.6g}")
    return out, stats


def class5_scan(ctx: Any, chk: Check, rules: Sequence[Mapping[str, Any]], where: str, *, ends: bool) -> int:
    """Правила переходных слагаемых на подготовке прогона `ctx` (центр или конец оси) → число применённых правил.
    В центре сводка каждого правила ложится в числа проверки."""
    n = 0
    for rule in rules:
        if ends and rule.get("axis_ends", True) is False:
            continue
        n += 1
        broken, stats = transitional_breaks(ctx, rule)
        if not ends:
            chk.numbers.setdefault("centre", []).append(dict(stats, name=rule["name"], until=int(rule["until"])))
            if not stats["values"]:
                chk.notes.append(f"правило «{rule['name']}» не проверялось: в центре у рядов «{rule['series']}» нет ни "
                                 f"одного значения (рядов {stats['series']})")
        for line in broken[:SHOW]:
            chk.fire(f"{where}{rule['name']} — {line}")
        if len(broken) > SHOW:
            chk.fire(f"{where}{rule['name']} — ещё {len(broken) - SHOW} кварталов или лет вне окна не нейтральны")
    return n


# ------------------------------------------------------------------ класс 6: центры суждений


RULES = RULES + ("facts",)                 # правило центра формулой от фактов (решения ведущего Совкомбанка № 2, В9)


def _facts_value(node: Any) -> Any:
    return node["v"] if isinstance(node, Mapping) and "v" in node else node


def formula_scope(book: Book, facts: Any, transmission: Any = None) -> dict[str, Any]:
    """Имена формул правил центров (класс 6, правило `facts`): F(файл, путь…) — узел файла фактов; Q(файл, поле, от, до) —
    значения поля кварталов файла (узел `quarters`) от и до включительно; B(путь) — значение книги; O(путь, по умолчанию) —
    значение необязательного ключа книги (нет ключа — по умолчанию); mean, mid, min, max,
    sum, abs, round; roll4(ряд) — скользящие 4 квартала ряда (среднее четырёх значений), roll4r(числитель, знаменатель) —
    скользящие 4 квартала отношением сумма к сумме (решения ведущего Совкомбанка № 6, Р6-2: «среднее окна» — среднее с
    равным весом календарных кварталов, то есть mean(roll4(…)) или mean(roll4r(…))); lin(xs, ys, k) — ряд xs + k·ys
    поквартально (решения ведущего Совкомбанка № 7, Р7-1, Р7-2: очищенный ряд «прочего» — отчётная строка минус наклон ×
    переоценка; прибыль без разовых — ni − k·noncore_net); T(поле) — поле решённой передачи ставки сетки (М§4.5; решения ведущего
    Совкомбанка № 11, раздел А: центр типа Б доли φ — совместный подбор «по истории» ÷ φ решателя, T('phi')). Формула — выражение
    без побочных действий; встроенных имён Python, кроме названных, нет."""
    def F(name: str, *path: str) -> Any:
        node: Any = facts.file(name)
        for part in path:
            node = node[part]
        return _facts_value(node)

    def Q(name: str, field_: str, frm: str, to: str) -> list[float]:
        quarters = facts.file(name)["quarters"]
        return [float(_facts_value(quarters[p][field_])) for p in sorted(quarters) if frm <= p <= to
                and quarters[p].get(field_) is not None and _facts_value(quarters[p][field_]) is not None]

    def B(path: str) -> Any:
        return book.get(path)

    def T(name: str) -> float:
        """Поле решённой передачи ставки сетки (model.nii.Transmission): φ решателя и его доли — тип Б доли φ (раздел А)."""
        if transmission is None:
            raise ValueError("передача ставки сетки не передана — T() считается только в проверке класса 6 на решённой сетке")
        return float(getattr(transmission, name))

    def O(path: str, default: Any = None) -> Any:
        """Значение необязательного ключа книги; нет ключа — `default` (проход ядра 9: правило на величине ключа, Р11-2)."""
        return book.opt(path, default)

    def mean(xs: Any) -> float:
        xs = list(xs)
        return sum(xs) / len(xs)

    def mid(a: float, b: float) -> float:
        return (float(a) + float(b)) / 2

    def roll4(xs: Any) -> list[float]:
        xs = [float(x) for x in xs]
        if len(xs) < 4:
            raise ValueError(f"скользящие 4 квартала: в ряду {len(xs)} значений")
        return [sum(xs[i:i + 4]) / 4 for i in range(len(xs) - 3)]

    def roll4r(num: Any, den: Any) -> list[float]:
        num, den = [float(x) for x in num], [float(x) for x in den]
        if len(num) != len(den) or len(num) < 4:
            raise ValueError(f"скользящие 4 квартала отношением: рядов {len(num)} и {len(den)} значений")
        return [sum(num[i:i + 4]) / sum(den[i:i + 4]) for i in range(len(num) - 3)]

    def lin(xs: Any, ys: Any, k: float) -> list[float]:
        xs, ys = [float(x) for x in xs], [float(y) for y in ys]
        if len(xs) != len(ys):
            raise ValueError(f"lin: рядов {len(xs)} и {len(ys)} значений")
        return [x + float(k) * y for x, y in zip(xs, ys)]

    return {"F": F, "Q": Q, "B": B, "O": O, "T": T, "mean": mean, "mid": mid, "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
            "roll4": roll4, "roll4r": roll4r, "lin": lin}


def formula_value(book: Book, facts: Any, expr: str, what: str, transmission: Any = None) -> float:
    try:
        return float(eval(compile(str(expr), "<class_checks.yaml>", "eval"), {"__builtins__": {}},  # noqa: S307
                          formula_scope(book, facts, transmission)))
    except Exception as exc:  # noqa: BLE001
        raise Refused(f"centres: формула {what} не считается — {type(exc).__name__}: {exc}") from exc


def centre_expected(book: Book, rule: Mapping[str, Any], facts: Any = None, transmission: Any = None) -> float:
    kind = str(rule.get("rule"))
    if kind == "facts":
        if facts is None:
            raise Refused(f"centres: у ключа {rule.get('key')} правило facts, а фактов нет")
        return formula_value(book, facts, rule["expr"], f"центра {rule.get('key')}", transmission)
    if kind == "midpoint":
        return (float(rule["lo"]) + float(rule["hi"])) / 2
    if kind == "value":
        return float(rule["value"])
    if kind in ("mean", "median"):
        vals = sorted(float(v) for v in rule["values"])
        if not vals:
            raise Refused(f"centres: у ключа {rule.get('key')} пустой список values")
        if kind == "mean":
            return sum(vals) / len(vals)
        m = len(vals) // 2
        return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2
    if kind == "axis_midpoint":
        key = str(rule["key"])
        for ax in all_axes(book):
            if ax["kind"] == "value" and key in [str(p) for p in ax["paths"]]:
                return (float(ax["low"]) + float(ax["high"])) / 2
        raise Refused(f"centres: на ключе {key} нет оси вида value — правило axis_midpoint не применимо")
    raise Refused(f"centres: незнакомое правило {kind!r} (знакомые: {', '.join(RULES)})")


def rule_axes(rule: Mapping[str, Any]) -> set[str]:
    """Оси, которые правило судит (первый путь оси): явное поле `axis`, ось на ключе правила или ось, названная выражением книги
    правила (`a['paths'][0] == '…'` или `a['name'] == '…'` — имя ищется по книге вызывающим)."""
    out = {str(rule["axis"])} if rule.get("axis") else set()
    expr = str(rule.get("book_expr") or "")
    out |= set(AXIS_IN_EXPR.findall(expr))
    out |= {"name:" + n for n in AXIS_NAME_IN_EXPR.findall(expr)}
    return out


def centre_keys(text: str) -> list[tuple[int, str]]:
    """Ключи с центром в тексте шаблона книги: (строка, путь) у строк ключа с меткой суждения [В…] / [Р/В…] в комментарии строки.
    Путь — по отступам; строки списков («- {…}») и комментарии пропускаются (их ключи — не ключи книги с центром)."""
    stack: list[tuple[int, str]] = []
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        st = line.lstrip()
        if not st or st.startswith("#") or st.startswith("-"):
            continue
        m = KEY_LINE.match(line)
        if not m:
            continue
        ind, key = len(m.group(1)), m.group(2).strip('"')
        while stack and stack[-1][0] >= ind:
            stack.pop()
        stack.append((ind, key))
        rest = m.group(3) or ""
        if "#" in rest and JUDGMENT_TAG.search(rest[rest.index("#"):]):
            out.append((n, ".".join(k for _, k in stack)))
    return out


def rule_covers(rule: Mapping[str, Any], path: str) -> bool:
    """Правило судит ключ `path`: ключ правила — сам путь, его предок или потомок; формула правила читает путь или его потомка."""
    key = str(rule.get("key"))
    if key == path or key.startswith(path + ".") or path.startswith(key + "."):
        return True
    refs = BOOK_REF.findall(str(rule.get("book_expr") or "")) + BOOK_REF.findall(str(rule.get("expr") or ""))
    return any(r == path or r.startswith(path + ".") for r in refs) or str(rule.get("axis") or "") == path


def type_scan(book: Book, rules: Sequence[Mapping[str, Any]], chk: Check, template: str | None = None) -> dict[str, Any]:
    """Решения № 11, раздел А: у каждого правила — тип из таблицы типов; у каждой оси книги — правило-суждение с типом (ключ правила —
    путь оси или правило судит ось по её первому пути / имени); у каждого ключа с центром (метка суждения в шаблоне книги,
    `centre_keys`) — правило с типом (`rule_covers`). Нет — находка класса 6."""
    counts: dict[str, int] = defaultdict(int)
    covered: set[str] = set()
    for rule in rules:
        t = rule.get("type")
        if t not in CENTRE_TYPES + OTHER_TYPES:
            chk.fire(f"ключ {rule['key']}: правило класса 6 без типа центра" + ("" if t is None else f" (тип {t!r} не из таблицы)")
                     + " — решения № 11, раздел А: у каждого ключа с центром или осью — тип")
            continue
        counts[str(t)] += 1
        if t in CENTRE_TYPES:
            covered |= {str(rule["key"])} | rule_axes(rule)
    axes = all_axes(book)
    bare = []
    for ax in axes:
        paths = [str(p) for p in ax["paths"]]
        if not (set(paths) & covered or "name:" + str(ax["name"]) in covered):
            bare.append(ax)
            chk.fire(f"ось «{ax['name']}» (первый путь {paths[0]}): нет правила класса 6 с типом центра — ни на ключе оси, ни на её "
                     "концах (решения № 11, раздел А: ключ с осью без типа — красный)")
    out = {"by_type": dict(sorted(counts.items())), "axes": len(axes), "axes_without_type": len(bare)}
    if template is not None:
        typed = [r for r in rules if r.get("type") in CENTRE_TYPES + OTHER_TYPES]
        keys = centre_keys(template)
        lost = [(n, p) for n, p in keys if not any(rule_covers(r, p) for r in typed)]
        for n, p in lost:
            chk.fire(f"ключ с центром {p} (строка {n} шаблона, метка суждения): нет правила класса 6 с типом центра (решения № 11, "
                     "раздел А: ключ с центром без типа — красный)")
        out.update({"centre_keys": len(keys), "centre_keys_without_type": len(lost)})
    return out


# Наклоны книг ЧПД между мирами (решения ведущего № 11, Р11-1; проход ядра 9): тип ключа доли сжатия книги — таблица файла
# (раздел book_slopes), по-русски, как таблица раздела А: «Б» — совместный подбор с книгами ядра (наклон модели = joint.a),
# «Б/Φ_A» — книга Φ_A формой отклонения (наклон книги минус среднее Φ_A по весам якоря = то же у совместного подбора;
# среднее — φ_A решателя, тип В), «связь» — законная связь (устав §8), «решение» — решение ведущего (наклон не судится),
# «ждёт» — тип ждёт решения ведущего (находка). Книга с долей phi_share без типа «Б» или «Б/Φ_A» — находка.
SLOPE_TYPES = ("Б", "Б/Φ_A", "связь", "решение", "ждёт")
SLOPE_JOINT = "data/assumptions/evidence/nii/inputs/stage1/calib/nii/backtest/backtest_joint.json"
SLOPE_TOL = 5e-4                          # запись доли — 4 знака


def class6_slopes(bench: Bench, chk: Check) -> int:
    """Класс 6, Р11-1: наклон ставки (стоимости) каждой книги ЧПД к опоре между мирами — функция ядра
    model.nii.book_slopes на решённой передаче сетки — против совместного подбора листа nii (joint.a, вход листа бэктеста
    книг) по типу книги из раздела `book_slopes`. → число судимых книг (0 — раздела нет)."""
    node = bench.cfg.get("book_slopes")
    if not node:
        return 0
    from model.nii import book_slopes, phi_shares
    joint = json.loads((ROOT / str(node.get("joint", SLOPE_JOINT))).read_text(encoding="utf-8"))["joint"]
    tol = float(node.get("tol", SLOPE_TOL))
    types = {str(b): dict(v) for b, v in (node.get("books") or {}).items()}
    books = bench.book.get("nii.books")
    slopes = book_slopes(bench.book, bench.facts, bench.base.ctx.transmission)
    shares = phi_shares(books)
    bal = bench.base.ctx.prep.af.balances
    phi_a = [b for b in books if types.get(b, {}).get("type") == "Б/Φ_A"]
    tot = sum(bal[b] for b in phi_a)

    def mean_a(fn: Callable[[str], float]) -> float:
        return sum(bal[b] * fn(b) for b in phi_a) / tot if tot else 0.0

    m_model, m_joint = mean_a(lambda b: float(slopes[b])), mean_a(lambda b: float(joint[b]["a"]))
    rows = []
    for b in books:
        spec = types.get(b)
        kind = None if spec is None else str(spec.get("type"))
        model, a = slopes[b], (joint.get(b) or {}).get("a")
        dev = None
        if kind == "Б" and model is not None and a is not None:
            dev = model - float(a)
        elif kind == "Б/Φ_A" and model is not None and a is not None:
            dev = (model - m_model) - (float(a) - m_joint)
        rows.append({"book": b, "type": kind, "slope_model": model, "slope_joint": a, "dev": dev, "tol": tol,
                     "phi_share": shares.get(b, 0.0), "source": None if spec is None else spec.get("source")})
        a_txt = "—" if a is None else f"{float(a):.4f}"
        if spec is None:
            chk.fire(f"книга {b}: наклона к опоре между мирами нет в таблице типов (Р11-1, класс 6) — модель "
                     f"{model:.4f}, совместный подбор {a_txt}" + (f"; доля phi_share {shares[b]:g} без типа" if b in shares else ""))
        elif kind in ("Б", "Б/Φ_A") and (dev is None or abs(dev) > tol):
            what = "наклон" if kind == "Б" else "отклонение наклона от среднего Φ_A"
            chk.fire(f"книга {b} (тип {kind}): {what} модели против совместного подбора — "
                     + ("не определён" if dev is None else f"{dev:+.5f} (модель {model:.4f}, подбор {a_txt}; допуск {tol:g})")
                     + (f"; {spec['source']}" if spec.get("source") else ""))
        elif kind == "ждёт":
            chk.fire(f"книга {b}: тип наклона ждёт решения ведущего — модель {model:.4f}, совместный подбор {a_txt}"
                     + (f" ({spec['source']})" if spec.get("source") else ""))
        if b in shares and kind not in ("Б", "Б/Φ_A"):
            chk.fire(f"книга {b}: доля сжатия phi_share {shares[b]:g} — ключ типа Б (совместный подбор), а в таблице тип "
                     f"{kind!r} (Р11-1, класс 6)")
    chk.numbers["book_slopes"] = rows
    chk.numbers["phi_a_mean"] = {"model": m_model, "joint": m_joint}
    return len(rows)


def class6(bench: Bench, chk: Check) -> None:
    rules = list(bench.cfg.get("centres") or [])
    chk.numbers["rules"] = len(rules)
    slopes = class6_slopes(bench, chk)
    if not rules and not slopes:
        chk.status = NO_RULES
        chk.notes.append("таблицы правил центров нет (устав калибровки не принят) — проверка не зелёная, а пустая")
        return
    if bench.cfg.get("centre_types"):              # решения № 11, раздел А: тип у каждого правила и правило с типом у каждой оси
        tpl = bench.cfg.get("centre_template")      # шаблон книги с метками суждений: ключи с центром (поле файла связей)
        if tpl and not (ROOT / str(tpl)).is_file():
            raise Refused(f"centres: шаблона книги {tpl} нет — ключи с центром судить не по чему")
        chk.numbers["types"] = type_scan(bench.book, rules, chk, (ROOT / str(tpl)).read_text(encoding="utf-8") if tpl else None)
    rows = []
    tr = bench.base.ctx.transmission              # решённая передача сетки: T() формул (тип Б доли φ, раздел А)
    for rule in rules:
        key = str(rule["key"])
        if rule.get("rule") == "value" and isinstance(rule.get("value"), str) and not rule.get("book_expr"):
            # центр-слово (квартал доли денег книги share_from, Р6-1): равенство записи, допуска нет
            try:
                word = bench.book.get(key)
            except BookError as exc:
                chk.fail(f"ключ {key}: нет в книге — {exc}")
                continue
            rows.append({"key": key, "rule": "value", "type": rule.get("type"), "book": word, "expected": rule["value"], "tol": 0,
                         "source": rule.get("source")})
            if str(word) != rule["value"]:
                chk.fire(f"{key} = {word}, правило «value» даёт {rule['value']}"
                         + (f" ({rule['source']})" if rule.get("source") else ""))
            continue
        try:
            value = (formula_value(bench.book, bench.facts, rule["book_expr"], f"значения книги {key}", tr) if rule.get("book_expr")
                     else float(bench.book.get(key)))
        except (BookError, TypeError, ValueError) as exc:
            chk.fail(f"ключ {key}: значение книги не число — {exc}")
            continue
        want = centre_expected(bench.book, rule, bench.facts, tr)
        tol = float(rule.get("tol", 0.0))
        rows.append({"key": key, "rule": rule["rule"], "type": rule.get("type"), "book": value, "expected": want, "tol": tol,
                     "source": rule.get("source")})
        if not abs(value - want) <= tol:
            chk.fire(f"{key} = {value:.6g}, правило «{rule['rule']}» (тип {rule.get('type', '—')}) даёт {want:.6g} (допуск {tol:g}"
                     + (f"; {rule['source']}" if rule.get("source") else "") + ")")
    chk.numbers["rows"] = rows


# ------------------------------------------------------------------ проход по концам осей (классы 1, 4, 5)


def end_task(bench: Bench, index: int, s: float, want: tuple[int, ...]) -> dict[str, Any]:
    """Конец `s` оси `index`: книга конца (класс 4), полная сетка конца — тождества (класс 1), переходные слагаемые
    (класс 5) и точка конца. Сетка считается один раз на конец и сразу отпускается. → части проверок, наибольшие
    невязки, число равенств, точка конца и время (сетка — отдельно, `clocks[0]`)."""
    book, cfg = bench.book, bench.cfg
    ident = cfg.get("identities") or {}
    do1 = 1 in want and ident.get("at_axis_ends", True)
    parts = {k: Check(k, "", "") for k in want if k in (1, 4, 5)}
    clocks: dict[int, float] = {0: 0.0, 1: 0.0, 4: 0.0, 5: 0.0}
    out: dict[str, Any] = {"parts": parts, "worst": {}, "equalities": 0, "point": None, "clocks": clocks}
    ax = all_axes(book)[index]
    name, end = str(ax.get("name")), "high" if s > 0 else "low"
    t = time.monotonic()
    try:
        ov = U.axis_overrides(book, ax, s)
        trial = U.trial_book(book, ov)
    except BookError as exc:
        for part in parts.values():
            part.fail(f"ось «{name}», конец {end}: подмена не строится — {exc}")
        return plain(out)
    if 4 in parts:
        class4_end(bench, parts[4], ax, s, ov, trial)
        clocks[4] += time.monotonic() - t
    t = time.monotonic()
    try:
        run = bench.run(trial)
    except (BookError, FactsError) as exc:
        for part in parts.values():
            part.fail(f"ось «{name}», конец {end}: книга конца не считается — {exc}")
        return plain(out)
    clocks[0] += time.monotonic() - t
    out["point"] = run.point
    if do1:
        t = time.monotonic()
        out["equalities"] = scan_identities(run, parts[1], float(ident.get("rel_tol", 1e-9)),
                                            f"ось «{name}», конец {end}: ", out["worst"])
        clocks[1] += time.monotonic() - t
    if 5 in parts:
        t = time.monotonic()
        class5_scan(run.ctx, parts[5], list(cfg.get("transitional") or []), f"ось «{name}», конец {end}: ", ends=True)
        clocks[5] += time.monotonic() - t
    return plain(out)


def plain(out: dict[str, Any]) -> dict[str, Any]:
    """Итог задачи конца оси простыми данными (части проверок — словарями)."""
    return dict(out, parts={k: part.part() for k, part in out["parts"].items()})


def end_pass(bench: Bench, want: set[int], checks: Mapping[int, Check], clocks: dict[int, float]) -> None:
    """Оба конца каждой оси (`end_task`; задачи — по рабочим процессам, если они есть), сведённые по порядку осей:
    находки, наибольшие невязки, число сеток концов; оси, не двигающие точку ни на одном конце, — замечание класса 4."""
    axes = all_axes(bench.book)
    order = tuple(sorted(want & {1, 4, 5}))
    results = fan(bench, "end", [(i, s, order) for i in range(len(axes)) for s in (-1.0, 1.0)])
    ends, dead = 0, []
    worst: dict[str, float] = checks[1].numbers.setdefault("worst", {}) if 1 in want else {}
    for i, ax in enumerate(axes):
        pair = results[2 * i: 2 * i + 2]
        for res in pair:
            for k, part in res["parts"].items():
                checks[k].absorb(part)
            for k, v in res["worst"].items():
                worst[k] = max(worst.get(k, 0.0), v)
            if 1 in want:
                checks[1].numbers["equalities"] = checks[1].numbers.get("equalities", 0) + res["equalities"]
            for k, v in res["clocks"].items():
                clocks[k] += v
            ends += res["point"] is not None
        points = [res["point"] for res in pair]
        if all(x is not None and bits(x) == bits(bench.base.point) for x in points):
            dead.append(str(ax.get("name")))
    if 4 in want:
        checks[4].numbers["dead_axes"] = dead
        if dead:
            checks[4].notes.append("оси, не двигающие точку ни на одном конце (ядро не читает ключ или ключ под "
                                   "выключателем): " + listed(dead, 10))
    for k in want & {1, 5}:
        checks[k].numbers["axis_end_grids"] = ends


# ------------------------------------------------------------------ рабочие процессы


TASKS: dict[str, Callable[..., Any]] = {"cell": cell_task, "centre": centre_task, "end": end_task}
_FAN: dict[str, Any] = {"executor": None, "workers": 1}
_BENCH: dict[bytes, Bench] = {}


def fan(bench: Bench, name: str, items: Sequence[tuple]) -> list[Any]:
    """Задачи `name` по порядку `items`: подряд в этом процессе либо частями по рабочим процессам (`open_pool`);
    результаты — в том же порядке, поэтому запись запуска та же при любом числе процессов."""
    task, executor, k = TASKS[name], _FAN["executor"], _FAN["workers"]
    if executor is None or k <= 1 or len(items) < 2:
        return [task(bench, *it) for it in items]
    blob = bench.blob()
    n = min(len(items), 2 * k)                      # частей вдвое больше процессов: короткий хвост
    size = -(-len(items) // n)
    chunks = [list(items[i:i + size]) for i in range(0, len(items), size)]
    futures = [executor.submit(_worker, name, blob, chunk) for chunk in chunks]
    out: list[Any] = []
    for f in futures:
        out.extend(f.result())
    return out


def _worker(name: str, blob: bytes, chunk: list[tuple]) -> list[Any]:
    key = hashlib.sha256(blob).digest()
    bench = _BENCH.get(key)
    if bench is None:
        book, facts, cfg = pickle.loads(blob)
        _BENCH.clear()
        bench = _BENCH[key] = make_bench(book, facts, cfg)
    return [TASKS[name](bench, *it) for it in chunk]


@contextlib.contextmanager
def open_pool(workers: int) -> Iterator[None]:
    """Рабочие процессы (spawn) на время запуска; `workers` ≤ 1 — всё подряд в этом процессе."""
    if workers <= 1:
        yield
        return
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context
    executor = ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn"))
    _FAN.update(executor=executor, workers=workers)
    try:
        yield
    finally:
        _FAN.update(executor=None, workers=1)
        executor.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------------ запуск


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise Refused(f"нет файла законных связей и допусков {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(cfg, dict):
        raise Refused(f"{path.name}: ожидается словарь разделов")
    for rule in cfg.get("transitional") or []:
        for k in ("name", "series", "until"):
            if k not in rule:
                raise Refused(f"{path.name}: у переходного слагаемого {rule.get('name', '?')!r} нет поля {k}")
        n = rule.get("neutral", 0.0)
        if not (isinstance(n, (int, float)) and not isinstance(n, bool)) and n not in ("last", "absent"):
            raise Refused(f"{path.name}: neutral у {rule['name']!r} — число, last или absent")
    for rule in cfg.get("centres") or []:
        if rule.get("rule") not in RULES or "key" not in rule:
            raise Refused(f"{path.name}: правило центра {rule!r} — нужны key и rule из {', '.join(RULES)}")
    for b, spec in ((cfg.get("book_slopes") or {}).get("books") or {}).items():
        if not isinstance(spec, Mapping) or spec.get("type") not in SLOPE_TYPES:
            raise Refused(f"{path.name}: book_slopes.books.{b} — нужен type из {', '.join(SLOPE_TYPES)}")
    return cfg


def run_checks(book: Book, facts: Any, cfg: Mapping[str, Any], *, only: Sequence[int] = ALL_CLASSES,
               say: Callable[[str], None] = print) -> dict[str, Any]:
    """Все проверки классов `only` на книге → запись запуска (`SCHEMA`)."""
    want = set(only)
    t_all = time.monotonic()
    t = time.monotonic()
    bench = make_bench(book, facts, cfg)
    t_base = time.monotonic() - t
    checks = {k: Check(k, key, CLASS_TITLES[k]) for k, key in
              ((1, "identities"), (2, "cross_cell"), (3, "horizon"), (4, "axes"), (5, "transitional"), (6, "centres"))
              if k in want}
    clocks: dict[int, float] = defaultdict(float)
    rules = list(cfg.get("transitional") or [])
    init = cellmod._Cell.__init__
    try:
        if 1 in want:
            t = time.monotonic()
            worst: dict[str, float] = checks[1].numbers.setdefault("worst", {})
            checks[1].numbers["equalities"] = scan_identities(bench.base, checks[1],
                                                              float((cfg.get("identities") or {}).get("rel_tol", 1e-9)),
                                                              "", worst)
            clocks[1] += time.monotonic() - t
        if 5 in want:
            t = time.monotonic()
            checks[5].numbers["rules"] = len(rules)
            if not rules:
                checks[5].status = NO_RULES
                checks[5].notes.append("перечня переходных слагаемых нет — проверка пустая")
            class5_scan(bench.base.ctx, checks[5], rules, "", ends=False)
            clocks[5] += time.monotonic() - t
        for k, fn in ((2, class2), (3, class3), (6, class6)):
            if k in want:
                t = time.monotonic()
                try:
                    fn(bench, checks[k])
                except (BookError, FactsError) as exc:
                    checks[k].fail(f"проверка не отработала: {exc}")
                clocks[k] += time.monotonic() - t
        if 4 in want:
            t = time.monotonic()
            class4_centre(bench, checks[4])
            clocks[4] += time.monotonic() - t
        if (1 in want and (cfg.get("identities") or {}).get("at_axis_ends", True)) or want & {4, 5}:
            end_pass(bench, want, checks, clocks)
        if 5 in want and rules and not any(r["values"] for r in checks[5].numbers.get("centre", [])):
            checks[5].not_checked("ни у одного правила в центре нет значений рядов — проверка пустая, не зелёная")
    finally:
        restored = cellmod._Cell.__init__ is init           # подмены снимают свои менеджеры; здесь — сверка
        cellmod._Cell.__init__ = init
    # сверка: инструмент модель не изменил — сетка книги та же бит в бит
    again = bench.run()
    same = restored and bits(again.point) == bits(bench.base.point) and not bench.changed(again)
    for k, c in checks.items():
        c.seconds = clocks[k]
    records = [checks[k].record() for k in sorted(checks)]
    out = {"schema": SCHEMA, "book": {"version": str(book.get("meta.version")), "digest": book.digest},
           "config": {"status": cfg.get("status")}, "point": bench.base.point, "point_after": again.point,
           "model_untouched": same, "checks": records, "flags": flag_lines(records),
           "seconds": {"base_grid": round(t_base, 2), "axis_end_grids": round(clocks[0], 2),
                       "total": round(time.monotonic() - t_all, 2)}}
    if not same:
        out["flags"].insert(0, "инструмент изменил модель: сетка книги после проверок не равна сетке до них бит в бит")
    return out


def report(out: Mapping[str, Any], say: Callable[[str], None] = print, *, quiet: bool = False) -> None:
    say(f"ПРОВЕРКИ КЛАССОВ ОШИБОК В МОДЕЛИ (PLAYBOOK §2а) · книга {out['book']['version']} · файл связей: "
        f"{out['config'].get('status') or '—'}")
    say(f"  точка книги {out['point']!r} ₽; после проверок {out['point_after']!r} — "
        + ("модель не изменена (бит в бит)" if out["model_untouched"] else "МОДЕЛЬ ИЗМЕНЕНА"))
    for c in out["checks"]:
        head = f"  класс {c['cls']} — {c['title']}: {c['status_words']}" + (f" ({c['tally']})" if c.get("tally") else "")
        if c["status"] in (FIRED, ERROR):
            head += f" — находок {c['count']}"
        say(head + f" [{c['seconds']:.1f} с]")
        for line in c["findings"][:SHOW if quiet else 2 * SHOW]:
            say("      • " + line)
        shown = SHOW if quiet else 2 * SHOW
        if c["count"] > shown:
            say(f"      … ещё {c['count'] - shown} (полный перечень — запись --json)")
        for line in c["notes"]:
            say("      ~ " + line)
        if not quiet:
            for line in number_lines(c):
                say("      " + line)
    flags = out["flags"]
    say("КРАСНЫЕ ФЛАГИ классов: нет" if not flags else f"КРАСНЫЕ ФЛАГИ классов — {len(flags)}:")
    for line in flags:
        say("  • " + line)
    sec = out["seconds"]
    say(f"время: сетка книги {sec['base_grid']:.1f} с; сетки концов осей {sec.get('axis_end_grids', 0.0):.1f} с (общие для "
        f"классов 1, 4, 5); у классов и сеток — сумма времени задач по всем процессам; всего по часам {sec['total']:.1f} с"
        + (f" ({out['workers']} процессов)" if out.get("workers", 1) > 1 else ""))


def number_lines(c: Mapping[str, Any]) -> list[str]:
    n = c["numbers"]
    if c["key"] == "identities" and "worst" in n:
        worst = ", ".join(f"{k} {v:.1e}" for k, v in sorted(n["worst"].items()))
        return [f"равенств проверено {n.get('equalities', 0)}; сеток концов осей {n.get('axis_end_grids', 0)}; "
                f"наибольшие невязки: {worst}"]
    if c["key"] == "cross_cell":
        iso = n.get("isolation") or {}
        rows = n.get("book_inputs") or []
        links = sorted({link for r in rows for link in r["links"]})
        return [f"клеток одна — {iso.get('cells', 0)}; сеток с подменой входа клетки — {n.get('cell_runs', 0)}; "
                f"возмущений книги — {len(rows)} (связи, по которым прошли: {', '.join(links) or '—'})"]
    if c["key"] == "horizon" and "rows" in n:
        return [f"{name}: {num(r['book'])} → {num(r['longer'])} ₽ ({rub(r['delta'])})" for name, r in n["rows"].items()] + [
            f"допуск ±{num(n['tol_rub'])} ₽; явный участок до {n['last_period']}"]
    if c["key"] == "axes":
        return [f"осей {n.get('axes', 0)}: в центре — по одной и разом, на концах — состав изменённых ключей"]
    if c["key"] == "transitional":
        rows = [f"{r['name']}: рядов {r['series']}, значений {r.get('values', 0)}, в окне по {r['until']} г. действует "
                f"{r['active_inside']} знач., вне окна {r['outside']} знач., наибольшее отклонение {r['max_outside']:.1e}"
                for r in n.get("centre", [])]
        return [f"правил {n.get('rules', 0)}; сеток концов осей {n.get('axis_end_grids', 0)}"] + rows
    if c["key"] == "centres":
        t = n.get("types") or {}
        slopes = [f"наклонов книг {len(n['book_slopes'])}"] if n.get("book_slopes") else []
        if not t:
            return [f"правил {n.get('rules', 0)}"] + slopes
        kinds = "; ".join(f"{k} ({TYPE_WORDS.get(k, k)}) — {v}" for k, v in t["by_type"].items())
        return [f"правил {n.get('rules', 0)}; по типам центра (решения № 11, раздел А): {kinds}",
                f"осей книги {t['axes']}, без правила с типом — {t['axes_without_type']}"] + slopes
    return []


def parse_only(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ALL_CLASSES
    try:
        out = tuple(sorted({int(x) for x in raw.split(",") if x.strip()}))
    except ValueError as exc:
        raise Refused(f"--only: номера классов через запятую, получено {raw!r}") from exc
    if not out or not set(out) <= set(ALL_CLASSES):
        raise Refused(f"--only: классы 1–6, получено {raw!r}")
    return out


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="проверки классов ошибок в модели (PLAYBOOK §2а) — на сетке, без полосы")
    ap.add_argument("--book", help="машинная книга (по умолчанию — книга дерева)")
    ap.add_argument("--facts", help="каталог фактов (по умолчанию — факты дерева)")
    ap.add_argument("--config", help="файл законных связей и допусков (по умолчанию data/assumptions/class_checks.yaml)")
    ap.add_argument("--only", help="только эти классы: номера через запятую")
    ap.add_argument("--json", help="куда записать запись запуска (JSON)")
    ap.add_argument("--quiet", action="store_true", help="короче: без чисел проверок")
    ap.add_argument("--workers", type=int, default=1,
                    help="рабочих процессов для подмен входов клеток и осей (по умолчанию 1 — всё подряд; запись та же)")
    args = ap.parse_args(argv)
    try:
        only = parse_only(args.only)
        cfg = load_config(Path(args.config) if args.config else CONFIG)
        facts = load_facts(Path(args.facts) if args.facts else None)
        book = load_book(Path(args.book) if args.book else None, facts=facts)
        if args.workers < 1:
            raise Refused("--workers — не меньше одного процесса")
        with open_pool(args.workers):
            out = run_checks(book, facts, cfg, only=only)
            out["workers"] = args.workers
    except Refused as exc:
        print(f"отказ: {exc}", file=sys.stderr)
        return 2
    except (BookError, FactsError) as exc:
        print(f"отказ: книга или факты не читаются — {exc}", file=sys.stderr)
        return 2
    out["exit_code"] = 1 if out["flags"] else 0
    report(out, quiet=args.quiet)
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return out["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
