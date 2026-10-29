"""Закрытая схема книги (docs/MODEL.md, приложение A) и громкий отказ.

Ядро читает книгу только через известные пути. Незнакомый ключ, пропущенный
ключ, `null` в пути, который ядро читает (с учётом выключателей, М§0.1),
неразбираемый ключ траектории (М§0.4), незнакомые `kind`, `dist`, `base`,
`shortfall_rule`, `cor_basis` и включённый нереализованный модуль — отказ
`BookError` до расчёта. Схема — снимок приложения A, а не вывод из текущей
книги: опечатка в новой книге не узаконит сама себя.

Подстановки путей: `<W>` — `worlds.ids`, `<r>` — `regimes.ids`, `<s>` —
`capital.reg_scenarios.ids`, `<b>` — ключи `nii.books` (у `checks.lt_spread_floor` —
кредитные книги: с `sector`), `<t>` — `meta.company.tickers`, `<y>` — год.

Правила сверх формы (М прил. A): `nii.sigma0_from` — год от `first_period` до
`last_period`; `other.misc_quarter_shares` в сумме 1; `dividends.excess.ramp_years` ≥ 1;
оси вне полосы (`valuation.uncertainty.off_band_axes`) — только `value`, `shift` и `bundle`; у оси
вида `bundle` (связка, М§10) пути — числа книги (элемент траектории — точечным ключом, не `LT_from`),
концы — словари ровно по путям, а общий путь со связкой у оси вида `value`, `dict` или у другой связки —
отказ; ось вида `value` на ключе года траектории, у которой в этом году есть квартальные ключи, —
отказ (ключ года там — среднее кварталов, М§0.4). Режим с `shock_year_offset` (кризис):
сдвиг ≥ 1, квартальный профиль CoR, период разового убытка и первый год
`loan_growth_override` лежат в году шока = год якоря + сдвиг (М§3.2). `credit.fv_loans_ref`
— режим книги; `nii.sigma0_split` ∈ [0; 1], и на стороне, куда ложится сдвиг, есть книги с
`lt_shift` (М§4.5); `nii.phi_split` ∈ [0; 1], и на стороне, куда ложится сжатие, есть книги с
`phi`, а у обеих книг средств ФЛ флаг `phi` одинаков (М§4.5); `joint.regime_update.window_obs`
≥ 1 и `floor_share` ∈ [0; 1] (М§12); окно рангов `valuation.sensitivities.rank_window` —
0 ≤ нижний < верхний ≤ 1 (М§10); `valuation.next_report.value_tol` > 0 (М§13); единица оси
`unit` — код П§0.2; наблюдение квартала не позже якоря несёт замороженные `mu_cor`, `mu_nim`
наблюдённых величин, наблюдение прогнозного квартала — нет (М§12).

Описательные ключи (М§0.6) — `meta.schema`, `meta.labels.*`, `nii.books.<b>.name`,
`checks.guidance_items` — обязательны и умолчаний в коде не имеют: имя эмитента, его нормативов,
органа решения о дивиденде и его терминов живёт в книге. Подпись — шаблон `str.format` с полями,
названными у ключа; незнакомое поле — отказ. Поведенческие ключи второй формы банка (делитель,
квартальный календарь дивидендов, связь с объёмом, премия роста по секторам, постоянные прочие
активы, множитель RWA режима, рост по капиталу, новые гейты) необязательны: нет ключа — прежняя
ветвь кода. Так же необязательны мир-опора κ-добавки (`credit.kappa_reference_world` — мир книги),
вид угасания терминала (`valuation.terminal.fade_mode`), область гейта долгосрочного C/I
(`checks.cir_lt.scope`), сторожа уровней (`checks.nim_stationary` — мир книги, `checks.window_backtest`,
`checks.funds_cost_to_key` — первый год в пределах сетки), узел пути смеси точки
(`checks.point_path`), порог уточнения у края диапазона (`valuation.reverse_dcf.edge_refine_rub`) и
справочные варианты (`valuation.reference_variants`: идентификаторы различны; подмена ложится на
ключ книги или вводит ключ в существующий раздел, сам список не трогает; подпись строки `note`
необязательна). Так же необязательны: мир уровня ключа цели ЧПМ (`nii.transmission.level_world` — мир
книги); строки обратного расчёта с уточнением на полной полосе (`valuation.reverse_dcf.refine_rows` —
ключи строк книги) и элементы премий роста, названные фактом (`valuation.reverse_dcf.premium_facts` —
числа траекторий премий); окно фактов узла уровней (`checks.window_backtest.nim`, `.means`,
`.loans_share`); подписи `meta.labels.gates.nim_anchor` и `meta.labels.nowcast.absent`. Снятый ключ раздела
проверок (`RETIRED_CHECKS`) схема принимает, пока его несёт книга репозитория; ядро его не читает. Ключ неактивного режима календаря (`dividends.calendar.frequency`) отсутствует или
равен `null`; значение в нём — отказ. Ветвь, которую схема уже принимает, а ядро ещё не
исполняет, — отказ «не реализовано» (`PENDING`, функция `pending`); проверка одной формы —
`validate(data, pending_ok=True)`.

Модуль — низ графа зависимостей ядра: здесь же живут `BookError` и
`FactsError` (их реэкспортирует `model.book`).
"""

from __future__ import annotations

import copy
import math
import re
from datetime import date
from string import Formatter
from typing import Any, Callable, Iterable, Mapping


class BookError(ValueError):
    """Книга нарушает схему или правило методики (громкий отказ)."""


class FactsError(ValueError):
    """Нет файла, узла или числа факта, который нужен ядру."""


# ------------------------------------------------------------ ключи времени

QUARTER_KEY = re.compile(r"^(\d{4})Q([1-4])$")
HALF_KEY = re.compile(r"^(\d{4})H([12])$")
YEAR_KEY = re.compile(r"^(\d{4})$")
PERIOD = QUARTER_KEY
DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRAJ_WORDS = ("LT", "LT_from")


def parse_time_key(key: str) -> tuple[str, int, int]:
    """Ключ траектории → (вид, год, номер): ('Q', год, квартал), ('H', год,
    полугодие), ('Y', год, 0). Неразбираемый — BookError."""
    m = QUARTER_KEY.match(key)
    if m:
        return "Q", int(m.group(1)), int(m.group(2))
    m = HALF_KEY.match(key)
    if m:
        return "H", int(m.group(1)), int(m.group(2))
    m = YEAR_KEY.match(key)
    if m:
        return "Y", int(m.group(1)), 0
    raise BookError(f"ключ траектории «{key}» не разбирается ни одним правилом М§0.4")


def is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ------------------------------------------------------------ узлы схемы


class Spec:
    """Узел схемы: проверяет значение и перечисляет шаблоны путей."""

    nullable = False

    def check(self, value: Any, path: str, ctx: "Ctx") -> None:
        raise NotImplementedError

    def templates(self, prefix: str) -> Iterable[str]:
        yield prefix


class Leaf(Spec):
    def __init__(self, test: Callable[[Any], bool], what: str, nullable: bool = False):
        self.test, self.what, self.nullable = test, what, nullable

    def check(self, value, path, ctx):
        if value is None:
            if not (self.nullable or ctx.switched_off(path)):
                ctx.err(f"{path}: null в читаемом пути (null ≠ 0)")
            return
        if not self.test(value):
            ctx.err(f"{path}: ожидается {self.what}, в книге {value!r}")


class Enum(Spec):
    def __init__(self, *values: str):
        self.values = frozenset(values)

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        try:
            known = value in self.values
        except TypeError:                   # словарь или список на месте слова (вариант OneOf) — незнакомое значение
            known = False
        if not known:
            ctx.err(f"{path}: незнакомое значение {value!r} (известны: {', '.join(sorted(self.values))})")


class Traj(Spec):
    """Траектория эмитента: число или словарь ключей времени (М§0.4)."""

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if is_number(value):
            return
        if not isinstance(value, Mapping) or not value:
            ctx.err(f"{path}: траектория — число или непустой словарь, в книге {value!r}")
            return
        ctx.trajectory(path, value, world=False)


class WorldTraj(Spec):
    """Траектория мира: полугодовые ключи до last_period включительно."""

    def check(self, value, path, ctx):
        if not isinstance(value, Mapping) or not value:
            ctx.err(f"{path}: траектория мира — словарь полугодий, в книге {value!r}")
            return
        ctx.trajectory(path, value, world=True)


class Years(Spec):
    """Словарь-переопределение по годам (не траектория, М§0.4)."""

    def __init__(self, item: Spec | None = None):
        self.item = item or NUM

    def check(self, value, path, ctx):
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: словарь по годам, в книге {value!r}")
            return
        for k, v in value.items():
            if not YEAR_KEY.match(str(k)):
                ctx.err(f"{path}: ключ «{k}» — не год")
                continue
            self.item.check(v, f"{path}.{k}", ctx)

    def templates(self, prefix):
        yield f"{prefix}.<y>"


class ListOf(Spec):
    def __init__(self, item: Spec, min_len: int = 0, exact: int | None = None):
        self.item, self.min_len, self.exact = item, min_len, exact

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if not isinstance(value, (list, tuple)):
            ctx.err(f"{path}: ожидается список, в книге {value!r}")
            return
        if self.exact is not None and len(value) != self.exact:
            ctx.err(f"{path}: ожидается список из {self.exact} элементов")
        if len(value) < self.min_len:
            ctx.err(f"{path}: список короче {self.min_len}")
        for i, v in enumerate(value):
            self.item.check(v, f"{path}[{i}]", ctx)

    def templates(self, prefix):
        if isinstance(self.item, (Obj, MapOf)):
            yield from self.item.templates(f"{prefix}[]")
        else:
            yield f"{prefix}[]"


class Obj(Spec):
    """Словарь с известными ключами: `fields` — ключ → (узел, обязателен)."""

    def __init__(self, fields: Mapping[str, Spec], optional: Iterable[str] = ()):
        self.fields = dict(fields)
        self.optional = frozenset(optional)

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: ожидается словарь, в книге {value!r}")
            return
        for k in value:
            if k not in self.fields:
                ctx.err(f"{_join(path, k)}: незнакомый ключ (известны: {', '.join(sorted(self.fields))})")
        for k, spec in self.fields.items():
            p = _join(path, k)
            if k not in value:
                if k not in self.optional and not ctx.switched_off(p):
                    ctx.err(f"{p}: нет ключа")
                continue
            spec.check(value[k], p, ctx)

    def templates(self, prefix):
        for k, spec in self.fields.items():
            yield from spec.templates(_join(prefix, k))


class MapOf(Spec):
    """Словарь, ключи которого — множество подстановки (`<W>`, `<r>` …)."""

    def __init__(self, placeholder: str, item: Spec, fixed: Mapping[str, Spec] | None = None,
                 exact: bool = True, label: str | None = None, extra: Mapping[str, Spec] | None = None,
                 whole: bool = False):
        self.placeholder, self.item = placeholder, item
        self.fixed = dict(fixed or {})
        self.extra = dict(extra or {})         # известные ключи сверх подстановки: необязательны
        self.exact = exact
        self.label = label or placeholder      # имя подстановки в шаблоне пути (прил. A)
        self.whole = whole                     # сам словарь — тоже путь схемы (его выключает выключатель, М§0.1)

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: ожидается словарь, в книге {value!r}")
            return
        ids = ctx.ids.get(self.placeholder)
        for k, spec in self.fixed.items():
            if k not in value:
                ctx.err(f"{_join(path, k)}: нет ключа")
            else:
                spec.check(value[k], _join(path, k), ctx)
        for k, v in value.items():
            if k in self.fixed:
                continue
            if k in self.extra:
                self.extra[k].check(v, _join(path, k), ctx)
                continue
            if ids is not None and k not in ids:
                ctx.err(f"{_join(path, k)}: незнакомый ключ (подстановка {self.placeholder}: "
                        f"{', '.join(ids)})")
                continue
            self.item.check(v, _join(path, k), ctx)
        if self.exact and ids is not None:
            for k in ids:
                if k not in value:
                    ctx.err(f"{_join(path, k)}: нет ключа")

    def templates(self, prefix):
        if self.whole:
            yield prefix
        for k, spec in self.fixed.items():
            yield from spec.templates(_join(prefix, k))
        yield from self.item.templates(_join(prefix, self.label))
        for k, spec in self.extra.items():
            yield from spec.templates(_join(prefix, k))


class PeriodMap(Spec):
    """Словарь «квартал ГГГГQn → значение» (не траектория, М§0.4); сам словарь — тоже путь схемы (выключатель)."""

    def __init__(self, item: Spec):
        self.item = item

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: словарь по кварталам, в книге {value!r}")
            return
        for k, v in value.items():
            if not QUARTER_KEY.match(str(k)):
                ctx.err(f"{path}: ключ «{k}» — не квартал ГГГГQn")
                continue
            self.item.check(v, f"{path}.{k}", ctx)

    def templates(self, prefix):
        yield prefix
        yield f"{prefix}.<period>"


class OneOf(Spec):
    def __init__(self, *options: Spec):
        self.options = options

    def check(self, value, path, ctx):
        for opt in self.options:
            probe = Ctx(ctx.data, ctx.ids, ctx.off, ctx.last_year)
            opt.check(value, path, probe)
            if not probe.errors:
                ctx.traj.extend(probe.traj)
                return
        ctx.err(f"{path}: значение {value!r} не подходит ни под один вид")

    def templates(self, prefix):
        yield prefix


class Label(Spec):
    """Подпись книги (М§0.6): непустая строка-шаблон `str.format`; поля подстановки — только названные
    у ключа, без формата и преобразования (значения полей готовит код)."""

    def __init__(self, *fields: str):
        self.fields = frozenset(fields)

    def check(self, value, path, ctx):
        if not isinstance(value, str) or not value.strip():
            ctx.err(f"{path}: ожидается непустая строка подписи, в книге {value!r}")
            return
        try:
            parts = [(name, spec, conv) for _, name, spec, conv in Formatter().parse(value) if name is not None]
        except ValueError as exc:
            ctx.err(f"{path}: подпись не разбирается как шаблон подстановки ({exc})")
            return
        unknown = sorted({name for name, _, _ in parts} - self.fields)
        if unknown:
            known = ", ".join(sorted(self.fields)) or "нет"
            ctx.err(f"{path}: незнакомое поле подстановки {{{'}, {'.join(unknown)}}} (допустимы: {known})")
        if any(spec or conv for _, spec, conv in parts):
            ctx.err(f"{path}: поле подстановки — без формата и преобразования")


class Terms(Spec):
    """Словарь терминов книги для ядра и витрины (`meta.labels.terms`, М§0.6): обязательные ключи `required`
    и любые иные ключи-идентификаторы; каждое значение — подпись без полей подстановки."""

    KEY = re.compile(r"^[a-z][a-z0-9_]*$")

    def __init__(self, *required: str):
        self.required = required

    def check(self, value, path, ctx):
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: ожидается словарь, в книге {value!r}")
            return
        for k in self.required:
            if k not in value:
                ctx.err(f"{_join(path, k)}: нет ключа")
        for k, v in value.items():
            if not self.KEY.match(str(k)):
                ctx.err(f"{_join(path, str(k))}: ключ термина — строчные латинские буквы, цифры и подчёркивание")
                continue
            TERM.check(v, _join(path, str(k)), ctx)

    def templates(self, prefix):
        for k in self.required:
            yield _join(prefix, k)
        yield _join(prefix, "<term>")


class Drift(Spec):
    """Премия роста к сектору (М§4.3): число — одна на все книги; словарь — траектория на каждый ключ
    набора, ровно по набору."""

    def __init__(self, *keys: str):
        self.keys = keys

    def check(self, value, path, ctx):
        if is_number(value):
            return
        if value is None:
            ctx.err(f"{path}: null в читаемом пути")
            return
        if not isinstance(value, Mapping):
            ctx.err(f"{path}: число или словарь траекторий по ключам {', '.join(self.keys)}, в книге {value!r}")
            return
        if set(map(str, value)) != set(self.keys):
            ctx.err(f"{path}: словарь премии — ровно с ключами {', '.join(self.keys)}, в книге "
                    f"{', '.join(map(str, value)) or 'пусто'}")
            return
        for k in self.keys:
            TRAJ.check(value[k], _join(path, k), ctx)

    def templates(self, prefix):
        yield prefix
        for k in self.keys:
            yield _join(prefix, k)


class Lag(Spec):
    """Лаг решения о дивиденде (М§5.7): целое 1…4 или карта по номеру квартала прибыли — ровно "1"…"4"."""

    QUARTERS = ("1", "2", "3", "4")

    def check(self, value, path, ctx):
        if value is None:
            if not ctx.switched_off(path):
                ctx.err(f"{path}: null в читаемом пути")
            return
        if isinstance(value, Mapping):
            if set(map(str, value)) != set(self.QUARTERS):
                ctx.err(f"{path}: карта лагов — ровно с ключами 1, 2, 3, 4")
                return
            for k in self.QUARTERS:
                LAG_Q.check(value[k], _join(path, k), ctx)
            return
        LAG_Q.check(value, path, ctx)

    def templates(self, prefix):
        yield prefix
        for k in self.QUARTERS:
            yield _join(prefix, k)


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else str(key)


def _is_date(x: Any) -> bool:
    return isinstance(x, date) or (isinstance(x, str) and DATE_KEY.match(x) is not None)


NUM = Leaf(is_number, "число")
INT = Leaf(lambda x: isinstance(x, int) and not isinstance(x, bool), "целое")
YEAR = Leaf(lambda x: isinstance(x, int) and not isinstance(x, bool) and x > 0, "год (целое)")
STR = Leaf(lambda x: isinstance(x, str) and x != "", "строка")
BOOL = Leaf(lambda x: isinstance(x, bool), "true | false")
DATE = Leaf(_is_date, "дата ГГГГ-ММ-ДД")
PERIOD_S = Leaf(lambda x: isinstance(x, str) and QUARTER_KEY.match(x) is not None, "квартал ГГГГQn")
ANCHOR_NUM = Leaf(lambda x: is_number(x) or x == "anchor", "число или anchor")
PAIR = Leaf(lambda x: isinstance(x, (list, tuple)) and len(x) == 2 and all(map(is_number, x))
            and x[0] <= x[1], "[мин, макс]")
NUM_OR_NULL = Leaf(is_number, "число или null", nullable=True)
STR_LIST = ListOf(STR)
TRAJ = Traj()
QUARTER_NO = Leaf(lambda x: x in (1, 2, 3, 4) and not isinstance(x, bool), "номер квартала 1–4")
LAG_Q = Leaf(lambda x: isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 4, "целое 1…4")
SHARE_01 = Leaf(lambda x: is_number(x) and 0 <= x <= 1, "доля от 0 до 1")
NON_NEGATIVE = Leaf(lambda x: is_number(x) and x >= 0, "число ≥ 0")
POSITIVE = Leaf(lambda x: is_number(x) and x > 0, "число > 0")
NON_NEGATIVE_OR_ANCHOR = Leaf(lambda x: x == "anchor" or (is_number(x) and x >= 0), "число ≥ 0 или anchor")
# драйвер составляющей RWA гарантий (К5, М§4.11): уровень базы комиссий на конец квартала, строка комиссий за
# четыре квартала (форма скептика, справочно) или уровень базы одной компоненты смеси базы комиссий (Р5-5, проход
# ядра 4: компонента — поле `component`, читается только при этом драйвере)
GUARANTEE_DRIVERS = ("fees_base", "fees_line", "fees_component")
LINE_ROOT_FORMS = ("additive", "multiplicative")      # форма корня строк комиссий и страхования (Р5-6, М§4.7)
# форма связи λ у франшизы строки (Р8-6) и книг К6 (Р9-1) — проход ядра 8, Р10-5 (М§4.7): mixed (≡ нет ключа) — франшиза
# смесью уровней, книги К6 цепью на концах; line — обе формой строки (смесь темпов г/г 1 + w + λ(x − 1 − w) с корнем)
LINE_LINK_FORMS = ("mixed", "line")
BUNDLE_COMPOSE_FORMS = ("exclusive", "additive")      # связки на общем пути: отказ или сумма приращений (Р5-4, М§10)
BUNDLE_COMPOSE = "valuation.uncertainty.bundle_compose"
# база строки (К2, М§4.7): словом — кредиты, средства клиентов, процентные активы, номинал (индекс зарплат мира);
# словарём — веса книг ЧПД (как веса М13); смесью (К2б) — доли строки на якоре по базам-компонентам {mix: {имя: {share,
# base}}}, компонента — слово loans | funds | iea или веса книг (номинала в смеси нет: смесь с ним нелинейна). Словарь
# проверяется первым: слово против словаря — не сравнение множеств
LINE_BASE_COMPONENT = OneOf(MapOf("<b>", NON_NEGATIVE, exact=False), Enum("loans", "funds", "iea"))
LINE_BASE = OneOf(MapOf("<b>", NON_NEGATIVE, exact=False), Enum("loans", "funds", "iea", "nominal"),
                  Obj({"mix": MapOf("<k>", Obj({"share": SHARE_01, "base": LINE_BASE_COMPONENT}), exact=False)}))
SHARE_BELOW_1 = Leaf(lambda x: is_number(x) and 0 <= x < 1, "доля от 0 до 1 (меньше 1)")
# доля сжатия книги между мирами (Р11-1, проход ядра 9): число строго между −1 и 1
PHI_SHARE = Leaf(lambda x: is_number(x) and -1 < x < 1, "доля сжатия книги: число, |доля| < 1")
# драйвер неработающих денег (К8, М§4.3): средства клиентов или кредиты словом; словарь — веса книг ЧПД
CASH_DRIVERS = ("funds", "loans")
# доля неработающих денег без ФОР к уровню драйвера (Р6-1, проход ядра 5, М§4.3): число от 0 до 1 (без 1) или anchor —
# доля квартала якоря (прежняя ветвь К8, бит в бит)
CASH_SHARE = Leaf(lambda x: x == "anchor" or (is_number(x) and 0 <= x < 1), "доля от 0 до 1 (меньше 1) или anchor")
# поля ключа доли денег книги (Р6-1): читаются только при числовой доле `share`
CASH_SHARE_FIELDS = ("reserves", "share_from", "displaced_weight")
GUARANTEE_FIELDS = ("notional.nonfinancial", "notional.financial", "ccf.nonfinancial", "ccf.financial", "weight",
                    "carve_from", "driver")
TERM = Label()
SCHEMA_NAME = re.compile(r"^[a-z][a-z0-9]*-v[0-9]+$")
SCHEMA_ID = Leaf(lambda x: isinstance(x, str) and SCHEMA_NAME.match(x) is not None,
                 "имя схемы выпуска вида <слово>-v<номер>")
# Коды базисов строк выпуска (П§0.2): МСФО, РСБУ, упр., движок, регуляторный, сектор; `market` — рыночные
# ряды плиток индикаторов. Базис подписи и узла гайденса задаёт книга.
BASIS_CODES = ("ifrs", "ras", "mgmt", "engine", "regulatory", "sector", "market")
REFS = ("key", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y")
OFZ = ("ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y")
SHARE_MAP = Leaf(lambda x: isinstance(x, Mapping) and x and all(map(is_number, x.values())),
                 "словарь долей")

# Коды единиц строк выпуска (П§0.2; словарь витрины): pct и share — доля, pp — сдвиг доли, bp — базисные
# пункты, bn — млрд ₽, rub и price — ₽, number — число, mix — доля смеси, dict — словарь долей, count — штуки,
# version — как есть, years — годы, level — уровень индекса, date — дата, period — период.
UNIT_CODES = ("pct", "share", "pp", "bn", "rub", "number", "mix", "dict", "count", "version", "bp", "years",
              "level", "price", "date", "period")
# Слова единиц книги (поле `unit` строк обратного расчёта) → коды.
UNIT_WORDS = {"%": "pct", "доля": "pct", "доли": "dict", "п.п.": "pp", "": "number", "млрд ₽": "bn", "₽": "rub",
              "записей": "count", "version": "version", "лет": "years"}
# Пара книг средств ФЛ (М§4.1): (текущие, срочные) — их доля задаётся мостиком текущих счетов.
RETAIL_BOOKS = ("retail_current", "retail_term")

BOOK_FIELDS = {
    "name": Label(),
    "side": Enum("asset", "liability"),
    "ref": Enum(*REFS),
    "rho": NUM,
    "spread": Traj(),
    "beta": NUM,
    "phi": BOOL,
    "lt_shift": BOOL,
    "sector": Enum("corporate", "mortgage", "retail_other"),
    "cor_segment": Enum("corporate", "retail"),
    "balancing": BOOL,
    "fv_share": ANCHOR_NUM,
    # доля сжатия спреда книги к опоре между мирами (проход ядра 9, Р11-1, М§4.4): ставка книги и её цель уменьшаются на
    # phi_share × (ref_W − ref_H); любая книга ЧПД, любой знак, |доля| < 1 (иначе ставка шла бы против опоры); нет поля
    # и 0 — прежняя строка, бит в бит
    "phi_share": PHI_SHARE,
}
NII_BOOK = Obj(BOOK_FIELDS, optional=("beta", "phi", "sector", "cor_segment", "balancing", "fv_share", "phi_share"))

AXIS = Obj({
    "name": STR,
    "kind": Enum("value", "shift", "dict", "bundle"),
    "paths": ListOf(STR, min_len=1),
    "low": OneOf(NUM, SHARE_MAP),
    "high": OneOf(NUM, SHARE_MAP),
    "dist": Enum("triangular"),
    "unit": Enum(*UNIT_CODES),
}, optional=("unit",))
REVERSE_AXIS = Obj({
    "name": STR,
    "kind": Enum("value", "shift", "mix"),
    "paths": ListOf(STR, min_len=1),
    "search": PAIR,
    "range": PAIR,
    "unit": Leaf(lambda x: isinstance(x, str), "строка"),
    "toward": SHARE_MAP,
}, optional=("toward",))

# Какие концы оси полосы идут за проверяемым значением строки обратного расчёта (М§11.2): `near` — только
# граница, которую оно пересекло (и без ключа), `both` — оба конца: ось сдвигается вместе с центром.
AXIS_FOLLOW = ("near", "both")
# Справочный вариант (М§14.5): цена названного правила или развилки — точка книги с подменами по путям. Подмена —
# значение пути книги (число, строка, список или словарь траектории); путь может вводить необязательный ключ.
REFERENCE_VARIANT = Obj({
    "id": Leaf(lambda x: isinstance(x, str) and re.fullmatch(r"[a-z][a-z0-9_]*", x) is not None,
               "идентификатор варианта (латиница, цифры, подчёркивание)"),
    "title": STR,
    "overrides": Leaf(lambda x: isinstance(x, Mapping) and bool(x) and all(isinstance(k, str) and k for k in x)
                      and all(v is not None for v in x.values()), "непустой словарь «путь книги → значение»"),
    "note": STR,                           # подпись строки для владельца: что печатает вариант (необязательна)
}, optional=("note",))
# Область гейта долгосрочного C/I (М§14.2): модальная клетка (и без ключа) или слой «рыночные ставки как есть».
CIR_SCOPES = ("modal_cell", "market_layer")
# Область гейта стоимости средств клиентов к ключевой (М§14.2; проход ядра 8, Р10-6): клетка «мир × модальный режим ×
# модальный сценарий» (и без ключа) или ожидание мира (вероятности режимов и сценариев внутри мира).
FUNDS_COST_SCOPES = ("modal_cell", "world_expectation")
# Книги «средств клиентов» в числах гейтов ядра (М§14.2; проход ядра 8, Р10-1): все книги средств (и без ключа) или
# книги средств без ведомых книг К6 (`volumes.liability_drivers`).
CLIENT_FUNDS_SCOPES = ("all", "clients")
# «Средства клиентов» балансовой механики (проход ядра 9, Р11-2, М§4.10): все книги средств (и без ключа) или книги
# средств без ведомых книг К6 — база структурного опта К3, якорь доли опта и слово funds баз строк
FUNDS_SCOPES = ("all", "clients")
# Постоянные в рублях части за концом сетки (`valuation.terminal.fixed_parts`, М§7): постоянные прочие активы,
# инструменты капитала (AT1, T2), постоянные пассивы (неконтролирующие доли, постоянное обязательство дивидендов),
# строки ОПУ в реальных рублях («прочее», непрофильный результат).
FIXED_PARTS = ("other_assets_fixed", "capital_instruments", "other_fixed_liabilities", "real_rubles")
# Выкуп акций по цене мира (`dividends.buyback`, М§5.6): правила цены покупок и поля, которые выключает выключатель.
BUYBACK_PRICES = ("world_forward", "cell_value", "market")
BUYBACK_FIELDS = ("amount", "price", "closed_prices", "skip_in_shock_year")
# Шаги хранения прогонов полосы (`valuation.uncertainty.draw_step`, М§10), ₽ на акцию.
DRAW_STEPS = (0.1, 0.01, 0.001)
NAMED_LITERALS = {
    0.1: "DRAW_STEPS: шаг хранения прогонов полосы 0,1 ₽ (М§10)",
    0.01: "DRAW_STEPS: шаг хранения прогонов полосы 0,01 ₽ (М§10)",
    0.001: "DRAW_STEPS: шаг хранения прогонов полосы 0,001 ₽ (М§10)",
}
# Вид угасания избыточной доходности терминала (М§7): одностороннее (и без ключа) или при любом знаке избытка.
FADE_MODES = ("one_sided", "symmetric")
# Год терминала (К-Т2а, М§7): год L как есть (и без ключа) или средний год 365,2425 дня.
YEAR_BASES = ("calendar", "mean")
# Ставка фондирования блока постоянных частей (К-Т2б, М§7): прежняя (и без ключа) или по правилу балансирующих статей.
FIXED_FUNDINGS = ("binary", "balancing")
# Премии роста к сектору (М§4.3): их элементы книга может назвать фактом (`valuation.reverse_dcf.premium_facts`).
PREMIUM_ROOTS = ("volumes.loan_share_drift", "volumes.funds_share_drift")


def paths_key(paths: Iterable[str]) -> str:
    """Ключ оси по её путям — он же ключ строки обратного расчёта и суждения: путь книги; у нескольких путей —
    общий шаблон со `*` на различающихся местах (у путей разной длины — первый путь с «+»)."""
    paths = [str(p) for p in paths]
    if len(paths) == 1:
        return paths[0]
    parts = [p.split(".") for p in paths]
    if len({len(p) for p in parts}) != 1:
        return paths[0] + "+"
    return ".".join(col[0] if len(set(col)) == 1 else "*" for col in zip(*parts))


# Банковские строки обратного расчёта (М§11.3): три прежние и три строки пределов роста.
BANK_ROWS = ("implied_roe_through_cycle", "implied_cost_of_equity", "market_cap_minus_bv",
             "value_without_excess_growth", "book_value_per_share", "excess_return_years")

WORLD = Obj({
    "name": STR,
    "key_rate": WorldTraj(), "cpi": WorldTraj(), "wage_growth": WorldTraj(),
    "ofz_1y": WorldTraj(), "ofz_3y": WorldTraj(), "ofz_5y": WorldTraj(), "ofz_10y": WorldTraj(),
    "real_key": WorldTraj(),
    "zero_curve": Obj({"1": NUM, "3": NUM, "5": NUM, "10": NUM, "LT": NUM}),
    "lt_inflation": NUM,
})

REGIME = Obj({
    "name": STR,
    "cor": Traj(),
    "nim_shift": Traj(),
    "loan_growth_adj": Traj(),
    "loan_growth_override": Years(),
    "one_off_loss": Obj({"period": PERIOD_S, "amount": NUM}),
    "shock_year_offset": INT,
    "rwa_density_mult": Traj(),
}, optional=("loan_growth_override", "one_off_loss", "shock_year_offset", "rwa_density_mult"))

SCENARIO = Obj({
    "name": STR,
    "conservation": Traj(), "sifi": Traj(), "ccyb": Traj(),
    "deduction_pp": Obj({"n20_0": Traj(), "n1_1": Traj()}),
})

# Подписи выпуска, тревог реестра и сводки контрольной модели (М§0.6): обязательные ключи без умолчания.
# Поля записи реестра: год прибыли, квартал прибыли, слова решения.
_REC = ("year", "period", "label")
NOWCAST_TARGET = Obj({"title": Label(), "basis": Enum(*BASIS_CODES), "title_long": Label()})
RULE_CLOSURES = ("unconstrained", "dividend_first", "growth_first")   # замыкания «цены правила» (М§14.5)
CONTROL_LINES = ("nii", "llp", "fvc", "fees", "opex", "misc", "noncore", "pbt", "ni_sh", "ci", "div", "bv", "rwa",
                 "n20", "n11")
LABELS = Obj({
    "capital": Obj({"n20": Label(), "n11": Label(), "n11_observed": Label(), "n1_0": Label(), "n1_2": Label(),
                    "n20_short": Label(), "n11_short": Label(), "anchor_src": Label("date"),
                    "anchor_src_estimated": Label("date"), "observed_source": Label()}),
    "capital_bridge": Obj({k: Label() for k in ("dividend_accrual", "profit", "oci_other", "rwa_growth",
                                                "deductions", "other")}),
    "dividends": Obj({"ladder_condition": Label("threshold"), "ladder_residual_title": Label(),
                      "ladder_residual_condition": Label(), "pay_event": Label(*_REC)}),
    "register": Obj({"flag_title": Label(), "flag_detail": Label("gaps"),
                     "gap_item": Label(*_REC, "decision_quarter", "end"), "alert": Label("detail"),
                     "recommended_item": Label(*_REC, "dps"), "rejected_item": Label(*_REC, "reason"),
                     "note": Label(), "overdue_item": Label(*_REC, "date"), "record_words": Label(*_REC),
                     "collector_alarm": Label(*_REC, "end", "detail")}),
    "flags": Obj({"ras_mismatch": Label()}),
    # `ops_note` — подпись месячной таблицы операционных результатов выпуска (необязательна; без неё — null);
    # `absent` — слова выпуска, собранного без слоя индикаторов (необязательна; без неё узла `nowcast.absent` нет)
    "nowcast": Obj({"targets": Obj({"ni_q": NOWCAST_TARGET, "nim_q": NOWCAST_TARGET, "cor_q": NOWCAST_TARGET}),
                    "ops_note": Label(), "absent": Label()}, optional=("ops_note", "absent")),
    "nextreport": Obj({"fact_note": Label(), "guidance_note": Label()}),
    "terms": Terms("lt_level", "profit_short"),
    "corridors": Obj({"guidance_gap": Label()}),
    "periods": Obj({k: Label("year") for k in ("1", "2", "3", "4")}),
    "basis": Obj({"profit": Label(), "roe": Label(), "roe_issuer": Label(), "divisor": Label(),
                  "dividend_issued": Label(), "dividend_outstanding": Label()},
                 optional=("dividend_issued", "dividend_outstanding")),
    "peers": Obj({"subject_basis": Label()}),
    "control": Obj({"lines": Obj({**{k: Label() for k in CONTROL_LINES}, "buyback": Label()},
                                 optional=("buyback",)),
                    "books": MapOf("<loan>", Label(), label="<b>")}),
    # подписи строк «цены правила» (М§14.5): необязательны, без ключа — слова кода
    "rule_price": Obj({k: Label() for k in RULE_CLOSURES}, optional=RULE_CLOSURES),
    # слова сообщений гейтов (М§14.2): необязательны, без ключа — слова кода. `nim_anchor` — маржа якоря в
    # сообщении гейта `nim_path_joint`: `value` — по книгам ядра через мост (с ней сравнивает гейт), `reported` —
    # отчётная упр. маржа квартала якоря (её печатает экран истории)
    "gates": Obj({"nim_anchor": Label("value", "reported")}, optional=("nim_anchor",)),
}, optional=("rule_price", "gates"))

# Узлы гайденса (М§14.2): ключ строки выпуска задаёт и правило сравнения с путём модели. С путём клетки
# гейт `guidance_gap` сравнивает ключи `GUIDANCE_GATE_KEYS`; прочие — только строка выпуска.
GUIDANCE_ITEM_KEYS = ("roe", "nim", "cor_max", "cir", "fee_growth", "n20_0", "loan_growth_corporate",
                      "loan_growth_retail", "op_np_growth", "dps_growth", "roe_target")
GUIDANCE_GATE_KEYS = ("roe", "nim", "cor_max", "cir", "op_np_growth", "dps_growth")
GUIDANCE_ITEM = Obj({
    "key": Enum(*GUIDANCE_ITEM_KEYS),
    "path": Leaf(lambda x: isinstance(x, str) and x.startswith("items.") and len(x) > len("items."),
                 "путь узла гайденса вида items.<узел>"),
    "title": Label(), "words": Label(), "basis": Enum(*BASIS_CODES), "gate": BOOL,
}, optional=("words",))

# Ключи раздела проверок, снятые ядром: схема принимает их, пока их несёт книга репозитория, и ядро по ним
# ничего не считает. Строка уходит отсюда вместе с ключом книги (сторож — tests/test_core_real.py); новый ключ
# сюда не вносится.
RETIRED_CHECKS: tuple[str, ...] = ()
RETIRED_NODE = Leaf(lambda x: isinstance(x, Mapping), "словарь снятого ключа")

SPEC = Obj({
    "meta": Obj({
        "version": STR, "date": DATE, "facts_date": DATE, "anchor_period": PERIOD_S,
        "first_period": PERIOD_S, "last_period": PERIOD_S, "valuation_date": DATE,
        "curve_as_of": DATE, "market_price": MapOf("<t>", NUM), "basis": STR,
        "step": Enum("quarter"), "day_count": Enum("act365"),
        "schema": SCHEMA_ID, "labels": LABELS,
        "company": Obj({"name": STR, "tickers": ListOf(STR, min_len=1), "main_ticker": STR,
                        "cbr_regnum": Leaf(lambda x: isinstance(x, (int, str)) and not isinstance(x, bool),
                                           "регномер"),
                        "fiscal_year_end": STR,
                        "share_classes": MapOf("<t>", Enum("ordinary", "preferred"))}),
    }),
    "worlds": MapOf("<W>", WORLD, fixed={
        "source": Obj({"record": STR, "origin": STR, "record_asof": DATE, "curve_date": DATE,
                       "sha256": STR, "recipe": STR_LIST}),
        "build": Obj({"script": STR, "fields": STR_LIST}),
        "quarter_rule": Enum("half_year_value"),
        "ids": ListOf(STR, min_len=1),
        "overlay": Obj({"file": STR, "sha256": STR, "fields": STR_LIST}),
    }),
    "worlds_bank": MapOf("<W>", Obj({
        "credit_growth": Obj({"corporate": Years(), "mortgage": Years(), "retail_other": Years()}),
        "funds_growth": Obj({"retail": Years(), "corporate": Years()}),
        "nominal_gdp_growth": Years(),
    })),
    "joint": Obj({
        "world_prob": MapOf("<W>", NUM),
        "world_prob_market_implied": MapOf("<W>", NUM),
        "macro_neutral_world": STR,
        "own_macro_confidence": NUM,
        "regime_prob": MapOf("<r>", NUM),
        "reg_prob_given_regime": MapOf("<r>", MapOf("<s>", NUM)),
        "regime_update": Obj({
            "observables": Obj({"cor": Obj({"sigma_pp": NUM, "rho_q": NUM}),
                                "nim": Obj({"sigma_pp": NUM, "rho_q": NUM})}),
            "max_shift_pp": NUM,
            "window_obs": INT,
            "floor_share": NUM,
            "shrink_by_se": BOOL,
            "observations": ListOf(Obj({
                "period": PERIOD_S, "cor": NUM_OR_NULL, "nim": NUM_OR_NULL,
                "se_cor": NUM_OR_NULL, "se_nim": NUM_OR_NULL, "basis": Enum("mgmt", "engine"),
                "mu_cor": MapOf("<r>", NUM), "mu_nim": MapOf("<r>", NUM),
            }, optional=("mu_cor", "mu_nim"))),
        }),
    }),
    "regimes": MapOf("<r>", REGIME, fixed={"ids": ListOf(STR, min_len=1),
                                          "cor_basis": Enum("mgmt", "engine"),
                                          "near_nim_shift": Traj()}),
    "credit": Obj({
        "kappa": NUM, "real_rate_lag_q": INT,
        "segment_relative": Obj({"enabled": BOOL, "corporate": NUM, "retail": NUM}),
        "fv_loans_factor": NUM, "fv_loans_ref": STR, "allowance_ratio": ANCHOR_NUM,
        "kappa_reference_world": STR,      # мир, в котором стоят пути CoR режимов; нет ключа — N, добавка только вверх
        # множители CoR по кредитным книгам (М§4.6): нормировка на составе якоря; нет ключа или выключен — сегменты
        "book_relative": Obj({"enabled": BOOL, "by_book": MapOf("<loan>", POSITIVE, label="<b>", whole=True)}),
        # резерв по книгам (К7, М§4.6): покрытие книги якоря × остаток книги; нет ключа или выключен — доля якоря
        "allowance_by_book": Obj({"enabled": BOOL}),
    }, optional=("kappa_reference_world", "book_relative", "allowance_by_book")),
    "nii": Obj({
        "books": MapOf("<b>", NII_BOOK),
        # `level_world` — мир, стационарную маржу которого задаёт ключ цели ЧПМ; нет ключа — мир-опора решателя
        "transmission": Obj({"target": NUM, "reference_world": STR, "fd_step": NUM,
                             "weights": Enum("anchor"), "level_world": STR}, optional=("level_world",)),
        "nim_lt_target_mgmt": NUM,
        "sigma0_split": NUM,
        "phi_split": NUM,
        "sigma0_from": YEAR,
        "retail_current_share": Obj({"c_ref": ANCHOR_NUM, "key_ref": ANCHOR_NUM, "psi": NUM,
                                     "rho": NUM, "bounds": PAIR}),
        "dia_rate": NUM,
    }),
    "volumes": Obj({
        "guidance_year": YEAR,
        "guidance_growth": Obj({"corporate": NUM, "retail": NUM}),
        "loan_share_drift": Drift("corporate", "mortgage", "retail_other"),
        "funds_share_drift": Drift("retail", "corporate"), "share_drift_until": YEAR,
        "lt_from": YEAR, "wholesale_to_funds": ANCHOR_NUM, "liquid_min_share": NUM,
        "securities_share_of_liquid": ANCHOR_NUM, "other_assets_to_loans": ANCHOR_NUM,
        "other_liabilities_to_loans": ANCHOR_NUM,
        "link_base": Enum("loans", "funds", "iea"),
        "other_assets_fixed": Leaf(lambda x: x == "anchor" or (is_number(x) and x >= 0), "число ≥ 0 или anchor"),
        # структурная доля опта к средствам клиентов (К3, М§4.10): сверх неё опт идёт по нужде — добирается при
        # нехватке ликвидности и гасится при избытке; нет ключа — база опта = доля якоря `wholesale_to_funds`
        "wholesale_structural_to_funds": NON_NEGATIVE,
        # книги-обязательства за драйвером строки (К6, М§4.3): книга ЧПД → строка-драйвер; нет ключа — книга растёт с
        # сектором средств бизнеса
        "liability_drivers": MapOf("<b>", Enum("insurance", "fees"), exact=False),
        # неработающие деньги со своим драйвером (К8, М§4.3): сумма якоря (anchor — факты balance.nonworking_money.total)
        # и драйвер — средства клиентов, кредиты или веса книг; нет ключа — деньги в доле прочих активов к кредитам.
        # Р6-1 (проход ядра 5): доля денег без ФОР книги `share` (anchor — доля якоря, прежняя ветвь), ФОР якоря
        # `reserves` (anchor — факты balance.nonworking_money.mandatory_reserves), квартал доли книги `share_from` (путь
        # от доли якоря — линейно по кварталам), вес вытесненной части прочих активов `displaced_weight` (θ: 0 — как
        # деньги, 1 или нет поля — как прочие без денег); поля необязательны
        "cash_assets": Obj({"amount": NON_NEGATIVE_OR_ANCHOR,
                            "driver": OneOf(MapOf("<b>", NON_NEGATIVE, exact=False), Enum(*CASH_DRIVERS)),
                            "share": CASH_SHARE, "reserves": NON_NEGATIVE_OR_ANCHOR, "share_from": PERIOD_S,
                            "displaced_weight": SHARE_01},
                           optional=("share",) + CASH_SHARE_FIELDS),
        # форма корня строк комиссий и страхования (Р5-6, М§4.7): multiplicative — рост = (1 + рост базы)(1 + корень)
        # − 1, как у расходов; нет ключа или additive — прежняя сумма
        "line_root_form": Enum(*LINE_ROOT_FORMS),
        # корень ρ номинальной части книг К6 (Р9-1, проход ядра 7, М§4.3): строка-драйвер → траектория ρ; книга за
        # драйвером строки растёт E_q = E_(q−1) (1 + wage)^((1 − λ)/4) (D_q / D_(q−1))^λ (1 + ρ_q)^(1 − λ). Читается для
        # книги, чья строка-драйвер в ключе, при активном К6; иначе — ключ неактивного режима, не отказ. Пустой словарь
        # ≡ нет ключа
        "liability_driver_roots": Obj({"fees": Traj(), "insurance": Traj()}, optional=("fees", "insurance")),
        # форма связи λ франшизы строки и книг К6 (Р10-5, проход ядра 8, М§4.7): line — франшиза Φ и индекс книг К6 Ψ
        # растут формой строки g = 1 + w + λ(x − 1 − w) с корнем κ (ρ) по форме корня строки; mixed и нет ключа —
        # прежние формы. Франшиза читает ключ при ключе κ строки, книги К6 — при активном К6; иначе ключ неактивного
        # режима, не отказ
        "line_link_form": Enum(*LINE_LINK_FORMS),
        # «средства клиентов» балансовой механики (Р11-2, проход ядра 9, М§4.10): clients — база структурного опта К3,
        # якорь доли опта `wholesale_to_funds` и слово funds баз строк и драйвера денег — книги средств без ведомых книг
        # К6 (одно слово — одна величина с `checks.client_funds`); all и нет ключа — все книги средств. Без активного К6
        # clients — ключ неактивного режима, не отказ. Строка баланса (тождество капитала) — все книги средств всегда
        "funds_scope": Enum(*FUNDS_SCOPES),
    }, optional=("link_base", "other_assets_fixed", "wholesale_structural_to_funds", "liability_drivers",
                 "cash_assets", "line_root_form", "liability_driver_roots", "line_link_form", "funds_scope")),
    # `volume_base` — своя база связи строки (К2, М§4.7); нет ключа — `volumes.link_base`
    "fees": Obj({"growth_override": Years(), "growth_vs_wages": Traj(), "volume_link": SHARE_01,
                 "volume_base": LINE_BASE},
                optional=("volume_link", "volume_base")),
    # `volume_weights` — веса книг ЧПД в базе связи расходов с объёмом (себестоимость книг, М§4.7); нет ключа —
    # база `volumes.link_base`
    # `line_shares` — доли базы расходов якоря, идущие за базами строк комиссий и страхования (К2, М§4.7)
    # `line_share_roots` — корень κ номинальной части франшизы строки (Р8-6, проход ядра 6): франшиза строки в смеси
    # базы расходов идёт за связью строки — λ за базой строки, 1 − λ за номиналом мира с корнем κ (М§4.7). Читается
    # при доле строки > 0 (и связи расходов); иначе — ключ неактивного режима, не отказ. Пустой словарь ≡ нет ключа
    "opex": Obj({"real_growth": Traj(), "volume_link": SHARE_01,
                 "volume_weights": MapOf("<b>", NON_NEGATIVE, exact=False),
                 "line_shares": Obj({"fees": SHARE_BELOW_1, "insurance": SHARE_BELOW_1},
                                    optional=("fees", "insurance")),
                 "line_share_roots": Obj({"fees": Traj(), "insurance": Traj()}, optional=("fees", "insurance"))},
                optional=("volume_link", "volume_weights", "line_shares", "line_share_roots")),
    "noncore": Obj({"result_real": Traj(), "price_base_year": YEAR}),
    "other": Obj({"insurance_growth_vs_wages": Traj(), "misc_net_real": Traj(),
                  "misc_quarter_shares": Obj({"1": NUM, "2": NUM, "3": NUM, "4": NUM}),
                  "fvtpl_bond_reval": BOOL, "insurance_volume_link": SHARE_01, "insurance_volume_base": LINE_BASE},
                 optional=("insurance_volume_link", "insurance_volume_base")),
    # `nci_real` (Р11-3, проход ядра 9, М§4.8): неконтролирующие в реальных рублях — млрд ₽ в год в ценах якоря, как
    # `other.misc_net_real` (квартал — год / 4 × индекс цен мира); при ключе `nci_share` не читается (ключ неактивного
    # режима, не отказ)
    "pnl": Obj({"nci_share": NUM, "nci_real": Traj()}, optional=("nci_real",)),
    "tax": Obj({"statutory": Traj(), "effective_gap": NUM,
                "one_off": Obj({"year": YEAR, "amount": NUM, "prob": NUM})}),
    "oci": Obj({"fvoci_share": ANCHOR_NUM, "fvoci_duration": NUM, "fvoci_maturity": NUM,
                "fvoci_tenor": Enum(*OFZ), "fvtpl_bond_share": ANCHOR_NUM,
                "fvtpl_bond_duration": NUM}),
    "equity": Obj({"other_movements": Traj()}),
    "capital": Obj({
        "minimum": Obj({"n20_0": NUM, "n1_1": NUM}),
        "mgmt_buffer": Obj({"n20_0": NUM, "n1_1": NUM}),
        "reg_scenarios": MapOf("<s>", SCENARIO, fixed={"ids": ListOf(STR, min_len=1)}),
        "n20": Obj({"deductions_anchor": ANCHOR_NUM, "fvoci_recognition": NUM, "t2": Traj(),
                    "gap_pp": NUM}),
        "n11": Obj({"deductions_anchor": ANCHOR_NUM, "gap_pp": NUM,
                    "audit_cutoffs": ListOf(QUARTER_NO)}),
        "rwa": Obj({
            "density": MapOf("<rwa>", NUM, extra={"other_assets_fixed": NON_NEGATIVE, "cash_assets": NON_NEGATIVE}),
            "density_drift_rate": NUM, "density_drift_until": YEAR,
            "fx": Obj({"enabled": BOOL, "share": NUM, "foreign_inflation": NUM}),
            # составляющая RWA гарантий (К5, М§4.11): номиналы (anchor — факты capital.guarantees), CCF, вес (вес
            # риска × масштаб калибровки RWA), книга выреза из плотности, драйвер — база или строка комиссий
            "guarantees": Obj({
                "enabled": BOOL,
                "notional": Obj({"nonfinancial": NON_NEGATIVE_OR_ANCHOR, "financial": NON_NEGATIVE_OR_ANCHOR}),
                "ccf": Obj({"nonfinancial": SHARE_01, "financial": SHARE_01}),
                "weight": POSITIVE,
                "carve_from": STR,
                "driver": Enum(*GUARANTEE_DRIVERS),
                # Р5-5: имя компоненты смеси fees.volume_base.mix — драйвер fees_component; при других драйверах —
                # ключ неактивного режима, не читается (вариант книги меняет драйвер, не удаляя ключ)
                "component": STR,
            }, optional=("component",)),
        }, optional=("guarantees",)),
        "recapitalization": Obj({"enabled": BOOL}),
        "growth_constraint": Obj({
            "enabled": BOOL,
            "order": Enum("dividend_first", "growth_first"),
            "min_growth_scale": SHARE_01,
            "lookahead_quarters": Leaf(lambda x: isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 12,
                                       "целое 0…12"),
            "glide_pp_per_quarter": NON_NEGATIVE,
            "catch_up_rate": SHARE_01,
            "tol": POSITIVE,
        }),
    }, optional=("growth_constraint",)),
    "dividends": Obj({
        "policy": Obj({
            "name": STR,
            "base": Enum("ifrs_ni_shareholders", "ifrs_ni_adjusted"),
            "deduct_at1_after_tax": BOOL,
            "payout": Traj(),
            "metric": Enum("n20_0"),
            "threshold": NUM,
            "steps": ListOf(Obj({"payout": Traj(), "threshold": NUM})),
            "shortfall_rule": Enum("residual_above_requirement"),
            "divisor": Enum("issued"),
            "dps_rounding": Enum("ceil_kopeck", "half_up_kopeck"),
            "forecast_rounding": Enum("none"),
            "history_test": Enum("exact", "cap", "none"),
            "cap": Leaf(lambda x: is_number(x) and 0 < x <= 1, "доля: больше 0 и не больше 1"),
            "base_window_quarters": Leaf(lambda x: isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 8,
                                         "целое 1…8"),
        }, optional=("history_test", "cap", "base_window_quarters")),
        "payout_deviation": Traj(),
        "excess": Obj({"from_profit_year": YEAR, "epsilon": NUM, "ramp_years": INT}),
        "crisis": Obj({"skip_in_shock_year": BOOL, "catch_up": BOOL}),
        # жетон DPS за год прибыли, ₽ на акцию (К1, М§4.13.2 п. 2а): читается только при квартальном календаре и
        # включённом ограничении роста; нет ключа — прежняя ветвь
        "min_dps": Traj(),
        # выкуп акций по цене мира (М§5.6): сумма за квартал, правило цены, цены закрытых кварталов, год шока
        "buyback": Obj({"enabled": BOOL, "amount": Traj(), "price": Enum(*BUYBACK_PRICES),
                        "closed_prices": PeriodMap(POSITIVE), "skip_in_shock_year": BOOL},
                       optional=BUYBACK_FIELDS),
        "calendar": Obj({
            "frequency": Enum("annual", "quarterly"),
            "agm_quarter": QUARTER_NO,
            "reg_deduction_quarter": QUARTER_NO,
            "payment_quarter": QUARTER_NO,
            "checkpoints": ListOf(QUARTER_NO, min_len=1),
            "decision_lag_quarters": Lag(),
            "reg_deduction_lag_quarters": LAG_Q,
            "payment_lag_quarters": LAG_Q,
            "checkpoints_ahead": INT,
        }, optional=("frequency",)),
    }, optional=("min_dps",)),
    "bridge": Obj({"declared_dividends": Enum("register"), "governance_applies": BOOL}),
    "valuation": Obj({
        "shares_basis": Enum("outstanding", "issued"),
        "share_count_adj": Leaf(lambda x: is_number(x) and -0.5 < x < 0.5, "число между −0,5 и 0,5"),
        "beta_e": NUM, "erp": NUM, "roll_along_forwards": BOOL,
        "governance": Obj({"discount": NUM, "components": ListOf(Obj({
            "id": STR, "name": STR, "value": NUM, "sign": NUM, "basis": STR}))}),
        # `fixed_growth_share` — λ_F, доля запаса постоянных в рублях частей, остающаяся в бизнесе за концом сетки;
        # `fixed_parts` — какие части несёт блок (М§7); нет ключа — прежний терминал
        # `stationary_rates` — ЧПД года L и ставки балансирующих за T по целям ставок книг (К4, М§7); нет ключа или
        # false — прежний терминал
        # `year_basis` — год терминала (К-Т2а, М§7): mean — средний год 365,2425 дня; нет ключа или calendar — прежний
        # `fade_anchor_year` — год-якорь угасания (К-Т2в, М§7): срок схода избытка — после него; нет ключа — после T
        # `fixed_funding` — ставка фондирования блока К-Т (К-Т2б, М§7): balancing — по правилу балансирующих статей;
        # нет ключа или binary — прежняя; читается только при fixed_growth_share
        "terminal": Obj({"real_growth": NUM, "fade": NUM, "excess_capital_multiple": NUM,
                         "timing": Enum("year_end"), "fade_mode": Enum(*FADE_MODES),
                         "fixed_growth_share": SHARE_01,
                         "fixed_parts": ListOf(Enum(*FIXED_PARTS), min_len=1), "stationary_rates": BOOL,
                         "year_basis": Enum(*YEAR_BASES), "fade_anchor_year": YEAR,
                         "fixed_funding": Enum(*FIXED_FUNDINGS)},
                        optional=("fade_mode", "fixed_growth_share", "fixed_parts", "stationary_rates", "year_basis",
                                  "fade_anchor_year", "fixed_funding")),
        "headline": Obj({
            "print_step": NUM, "diagnostics": Enum("median"), "search_tol_rub": NUM,
            "jump_guard": Obj({"median_pct": NUM, "v0_pct": NUM}), "ceiling_x_market": NUM,
        }),
        "sensitivities": Obj({"cor_pp": NUM, "nim_pp": NUM, "roe_pp": NUM, "rank_window": PAIR,
                              "buffer_pp": POSITIVE}, optional=("buffer_pp",)),
        "uncertainty": Obj({
            "draws": INT, "seed": INT, "quantiles": ListOf(NUM, min_len=1), "median_draws": INT,
            "reverse_bounds": Enum("follow_center"), "median_refine": INT,
            "axes": ListOf(AXIS),
            "off_band_axes": ListOf(AXIS),
            # шаг хранения прогонов полосы, ₽ (М§10); нет ключа — 0,1 (`model.uncertainty.DRAW_STEP`)
            "draw_step": Leaf(lambda x: is_number(x) and x in DRAW_STEPS, "шаг хранения прогонов 0.1, 0.01 или 0.001"),
            # сложение связок на одном пути (Р5-4, М§10): additive — приращения «конец − центр» складываются; нет ключа
            # или exclusive — прежний отказ общему пути двух связок
            "bundle_compose": Enum(*BUNDLE_COMPOSE_FORMS),
        }, optional=("draw_step", "bundle_compose")),
        "reverse_dcf": Obj({
            "subsample": INT, "axes": ListOf(REVERSE_AXIS),
            "bank_rows": ListOf(Enum(*BANK_ROWS)),
            "axis_follow": Enum(*AXIS_FOLLOW),
            "edge_refine_rub": POSITIVE,   # решение подвыборки у края диапазона уточняется на полной полосе (М§11.2)
            "refine_rows": STR_LIST,       # ключи строк с уточнением на полной полосе; нет ключа — все строки (М§11.2)
            "premium_facts": STR_LIST,     # элементы премий роста, названные фактом: строка «без опережающего роста»
            #                                их не снимает (М§11.3)
        }, optional=("axis_follow", "edge_refine_rub", "refine_rows", "premium_facts")),
        "next_report": Obj({"period": PERIOD_S, "cor_values": ListOf(NUM, min_len=1),
                            "nim_values": ListOf(NUM, min_len=1), "search_pad": NUM,
                            "value_tol": NUM}),
        "reference_variants": ListOf(REFERENCE_VARIANT),      # справочные варианты таблиц книги (М§14.5)
        # запись сухого перевывода развилок — файл в каталоге книги: цены вариантов и «цены правила» берутся из неё (М§14.5)
        "reference_record": Leaf(lambda x: isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_\-]+\.json", x) is not None,
                                 "имя файла записи в каталоге книги (*.json)"),
    }, optional=("shares_basis", "share_count_adj", "reference_variants", "reference_record")),
    "checks": Obj({
        "ddm_ri_tol": NUM, "transmission_tol": NUM, "exdate_jump_tol": NUM,
        "pb_by_world": MapOf("<W>", PAIR),
        "roe_range": PAIR, "cor_range": PAIR, "nim_range": PAIR, "cir_range": PAIR,
        "roe_k_spread": Obj({"range": PAIR, "max_world_gap": NUM}),
        "terminal_share": PAIR, "real_rate": PAIR,
        "bridge_drift_pp": Obj({"cor": NUM, "nim": NUM}),
        "nim_path_joint": Obj({"quarters": INT, "tolerance": NUM}),
        "transmission_pairs": PAIR,
        "lt_spread_floor": MapOf("<loan>", NUM, label="<b>"),
        "ni_jump": Obj({"quarters": INT, "yoy": NUM, "key_tol": NUM}),
        "m_crisis_vs_cbr": Obj({"loan_growth": Years(PAIR), "cor_shock_year": NUM, "n20_min": NUM}),
        "manual_overdue_days": Obj({"ifrs_fact": INT, "worlds_after_cbr": INT, "dividend_register": INT,
                                    "capital_form": INT}, optional=("capital_form",)),
        "book_update": Obj({"shift_bp": NUM, "max_age_days": INT}),
        "guidance_items": ListOf(GUIDANCE_ITEM),
        "growth_cut": Obj({"max_cut_share": SHARE_01}),
        "step_dividend": Obj({"max_lam_drop": SHARE_01}),
        "cir_lt": Obj({"target": NUM, "tolerance": NON_NEGATIVE, "from_year": YEAR, "scope": Enum(*CIR_SCOPES)},
                      optional=("scope",)),
        "wholesale_share": PAIR,
        "mix_ratio_tolerance": POSITIVE,   # допуск сверки норматива смеси с ожиданием нормативов клеток (П§7 п. 10)
        "nim_lt": Obj({"target": NUM, "tolerance": NON_NEGATIVE, "from_year": YEAR}),
        "volume_sign": Obj({"tol": NON_NEGATIVE}),                          # ₽ на акцию
        "stress_sign": Obj({"loss_step": POSITIVE, "tol": NON_NEGATIVE}),   # млрд ₽
        "payout_cap": Obj({"tolerance": SHARE_01}),                         # доля прибыли года
        # стационарная маржа решателя передачи на составе якоря в мире `world`, упр. базис (М§14.2)
        "nim_stationary": Obj({"world": STR, "target": NUM, "tolerance": NON_NEGATIVE}),
        # уровни после фазы роста слоя «рыночные ставки как есть» против окна фактов; ключ включает узел уровней
        # `nim`, `means`, `loans_share` — окно фактов подузла `window` узла уровней: наименьший и наибольший квартал
        # окна по марже, средние окна (упр. базис) и доля кредитов в процентных активах окна (определение движка)
        "window_backtest": Obj({"from_year": YEAR, "cor": PAIR, "cir": PAIR, "nim": PAIR,
                                "means": Obj({"nim": NUM, "cor": NUM, "cir": NUM}), "loans_share": SHARE_01},
                               optional=("nim", "means", "loans_share")),
        # стоимость средств клиентов к ключевой ставке в клетке «мир × модальный режим × модальный сценарий» (scope
        # modal_cell и нет поля) или в ожидании мира (world_expectation — Р10-6, проход ядра 8)
        "funds_cost_to_key": Obj({"max": POSITIVE, "from_year": YEAR, "scope": Enum(*FUNDS_COST_SCOPES)},
                                 optional=("scope",)),
        "point_path": BOOL,                # узел таблиц книги «годовой путь смеси точки» (М§14.5)
        # книги «средств клиентов» в числах гейтов funds_cost_to_key, wholesale_share и пути фондирования (Р10-1, проход
        # ядра 8): clients — без ведомых книг К6; all и нет ключа — все книги средств
        "client_funds": Enum(*CLIENT_FUNDS_SCOPES),
        **{key: RETIRED_NODE for key in RETIRED_CHECKS},
    }, optional=("growth_cut", "step_dividend", "cir_lt", "wholesale_share", "mix_ratio_tolerance", "nim_lt",
                 "volume_sign", "stress_sign", "payout_cap", "nim_stationary", "window_backtest",
                 "funds_cost_to_key", "point_path", "client_funds") + RETIRED_CHECKS),
})

# Выключатель → ключи, которые он выключает (М§0.1, прил. A). При выключенном
# ключи не читаются и могут быть null; при включённом null в них — отказ.
SWITCHES: dict[str, tuple[str, ...]] = {
    "credit.segment_relative.enabled": ("credit.segment_relative.corporate",
                                        "credit.segment_relative.retail"),
    "credit.book_relative.enabled": ("credit.book_relative.by_book",),
    "credit.allowance_by_book.enabled": (),        # резерв по книгам (К7): полей нет, факты — balance.allowance_books
    "capital.rwa.fx.enabled": ("capital.rwa.fx.share", "capital.rwa.fx.foreign_inflation"),
    "capital.rwa.guarantees.enabled": tuple(f"capital.rwa.guarantees.{k}" for k in GUARANTEE_FIELDS),
    "other.fvtpl_bond_reval": ("oci.fvtpl_bond_duration",),
    "capital.recapitalization.enabled": (),
    "dividends.buyback.enabled": tuple(f"dividends.buyback.{k}" for k in BUYBACK_FIELDS),
    # рост по капиталу (М§4.13): при выключенном шесть полей не читаются и могут оставаться числами
    "capital.growth_constraint.enabled": tuple(f"capital.growth_constraint.{k}" for k in (
        "order", "min_growth_scale", "lookahead_quarters", "glide_pp_per_quarter", "catch_up_rate", "tol")),
}

# Календарь дивидендов (М§5.7): ключи годового режима и ключи квартального. Ключ неактивного режима
# отсутствует или равен null; значение в нём — отказ (книга не несёт молча то, что ядро не читает).
CALENDAR_MODE = "dividends.calendar.frequency"
CALENDAR_ANNUAL = tuple(f"dividends.calendar.{k}" for k in (
    "agm_quarter", "reg_deduction_quarter", "payment_quarter", "checkpoints"))
CALENDAR_QUARTERLY = tuple(f"dividends.calendar.{k}" for k in (
    "decision_lag_quarters", "reg_deduction_lag_quarters", "payment_lag_quarters", "checkpoints_ahead"))
QUARTERLY_ONLY = CALENDAR_QUARTERLY + ("dividends.policy.base_window_quarters",)

# Модули особых статей: ключ есть, модуля нет — включение до реализации — отказ.
UNIMPLEMENTED_SWITCHES = ("capital.recapitalization.enabled",)
# Значения, зарезервированные схемой, но не реализованные ядром.
UNIMPLEMENTED_VALUES = {"dividends.policy.base": ("ifrs_ni_adjusted",)}


def _nonzero(value: Any) -> bool:
    return is_number(value) and float(value) != 0.0


def _present(value: Any) -> bool:
    return value is not None


# Ветви второй формы банка, которые схема принимает, а ядро ещё не исполняет: путь → (значение включает
# ветвь?, что это). Включение — отказ «не реализовано»; нет ключа или нейтральное значение — прежнее
# поведение. Волна, которая реализует ветвь, снимает её строку здесь.
PENDING: dict[str, tuple[Callable[[Any], bool], str]] = {}
# То же по элементам: узлы гайденса и банковские строки обратного расчёта, которых ядро ещё не считает.
PENDING_GUIDANCE_KEYS: tuple[str, ...] = ()
PENDING_BANK_ROWS: tuple[str, ...] = ()

# Траектории, у которых LT_from и ключи в году last_period запрещены (М§0.4):
# всё, что проверяется узлом Traj (траектории эмитента).

KEYS: tuple[str, ...] = tuple(SPEC.templates(""))


# ------------------------------------------------------------ проверка


class Ctx:
    def __init__(self, data: Mapping, ids: Mapping[str, tuple[str, ...]], off: frozenset[str],
                 last_year: int | None):
        self.data, self.ids, self.off, self.last_year = data, ids, off, last_year
        self.errors: list[str] = []
        self.traj: list[str] = []

    def err(self, message: str) -> None:
        self.errors.append(message)

    def switched_off(self, path: str) -> bool:
        return path in self.off

    def trajectory(self, path: str, value: Mapping, *, world: bool) -> None:
        self.traj.append(path)
        for k, v in value.items():
            k = str(k)
            if k == "LT_from":
                if not (isinstance(v, int) and not isinstance(v, bool)):
                    self.err(f"{path}.LT_from: ожидается год, в книге {v!r}")
                elif not world and self.last_year is not None and v > self.last_year:
                    self.err(f"{path}.LT_from = {v} позже года last_period {self.last_year} (М§0.4)")
                continue
            if v is None:
                self.err(f"{path}.{k}: null в траектории")
                continue
            if not is_number(v):
                self.err(f"{path}.{k}: ожидается число, в книге {v!r}")
                continue
            if k == "LT":
                continue
            try:
                kind, year, _ = parse_time_key(k)
            except BookError as exc:
                self.err(f"{path}: {exc}")
                continue
            if world:
                if kind == "Q":
                    self.err(f"{path}.{k}: у траектории мира — ключи полугодий")
            elif kind in ("Q", "H") and self.last_year is not None and year == self.last_year:
                self.err(f"{path}.{k}: ключ квартала или полугодия в году last_period запрещён (М§0.4)")
        if not world:
            _check_year_means(path, value, self)
        elif self.last_year is not None and f"{self.last_year}H2" not in {str(k) for k in value}:
            self.err(f"{path}: траектория мира не доходит до {self.last_year}H2 (last_period)")


def _check_year_means(path: str, traj: Mapping, ctx: Ctx) -> None:
    """Ключ года при квартальных ключах — среднее года (М§0.4)."""
    quarters: dict[int, list[float]] = {}
    for k, v in traj.items():
        m = QUARTER_KEY.match(str(k))
        if m and is_number(v):
            quarters.setdefault(int(m.group(1)), []).append(float(v))
    for year, vals in quarters.items():
        yk = str(year)
        if yk in traj and len(vals) == 4 and is_number(traj[yk]):
            if abs(sum(vals) / 4 - float(traj[yk])) > 1e-9:
                ctx.err(f"{path}.{yk}: ключ года {traj[yk]} ≠ среднему кварталов {sum(vals) / 4:.6g}")


def _get(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _ids(data: Mapping, path: str, errors: list[str]) -> tuple[str, ...] | None:
    value = _get(data, path)
    if not isinstance(value, (list, tuple)) or not value or not all(isinstance(x, str) for x in value):
        errors.append(f"{path}: нужен непустой список строк")
        return None
    if len(set(value)) != len(value):
        errors.append(f"{path}: повторяющиеся значения")
    return tuple(value)


def switched_off_paths(data: Mapping) -> frozenset[str]:
    """Пути, выключенные выключателями книги (М§0.1)."""
    off: set[str] = set()
    for switch, keys in SWITCHES.items():
        if _get(data, switch) is False:
            off.update(keys)
    # ключи неактивного режима календаря дивидендов (М§5.7)
    off.update(CALENDAR_ANNUAL if _get(data, CALENDAR_MODE) == "quarterly" else QUARTERLY_ONLY)
    return frozenset(off)


def placeholder_ids(data: Mapping, errors: list[str] | None = None) -> dict[str, tuple[str, ...]]:
    errors = [] if errors is None else errors
    ids: dict[str, tuple[str, ...]] = {}
    for key, path in (("<W>", "worlds.ids"), ("<r>", "regimes.ids"),
                      ("<s>", "capital.reg_scenarios.ids"), ("<t>", "meta.company.tickers")):
        got = _ids(data, path, errors)
        if got is not None:
            ids[key] = got
    books = _get(data, "nii.books")
    if isinstance(books, Mapping) and books:
        ids["<b>"] = tuple(str(k) for k in books)
        assets = [str(k) for k, v in books.items()
                  if isinstance(v, Mapping) and v.get("side") == "asset"]
        ids["<rwa>"] = tuple(assets) + ("other_assets",)
        ids["<loan>"] = tuple(str(k) for k, v in books.items() if isinstance(v, Mapping) and "sector" in v)
    else:
        errors.append("nii.books: нужен непустой словарь книг")
    return ids


def _year_of(period: Any) -> int | None:
    if isinstance(period, str):
        m = QUARTER_KEY.match(period)
        if m:
            return int(m.group(1))
    return None


def pending(data: Mapping) -> list[str]:
    """Ветви, которые книга включает, а ядро ещё не исполняет (`PENDING`): строка на ключ, со словами
    «не реализовано». Пусто — книга считается ядром целиком."""
    out: list[str] = []

    def refuse(path: str, value: Any, what: str) -> None:
        shown = "" if isinstance(value, (Mapping, list)) else f" = {value!r}"
        out.append(f"{path}{shown}: {what} — не реализовано в ядре (ветвь принята схемой, включение запрещено)")

    for path, (enabled, what) in PENDING.items():
        value = _get(data, path)
        if value is not None and enabled(value):
            refuse(path, value, what)
    for i, item in enumerate(_get(data, "checks.guidance_items") or []):
        if isinstance(item, Mapping) and item.get("key") in PENDING_GUIDANCE_KEYS:
            refuse(f"checks.guidance_items[{i}].key", item.get("key"), "узел гайденса (М§14.2)")
    for i, row in enumerate(_get(data, "valuation.reverse_dcf.bank_rows") or []):
        if row in PENDING_BANK_ROWS:
            refuse(f"valuation.reverse_dcf.bank_rows[{i}]", row, "банковская строка обратного расчёта (М§11.3)")
    return out


def validate(data: Mapping, *, pending_ok: bool = False, corners: bool = True) -> None:
    """Громкий отказ BookError, если книга нарушает схему (инвариант book_schema). `pending_ok=True` —
    проверка одной формы: включённая, но ещё не реализованная ветвь (`pending`) отказом не считается.
    `corners=False` — без правила углов сложения связок (Р5-4, `_corner_rules`): так проверяется книга-копия, чьи
    значения — подмены прогона или варианта, а не центр связок."""
    if not isinstance(data, Mapping):
        raise BookError("книга — не словарь")
    errors = _book_errors(data, pending_ok=pending_ok)
    if corners and not errors:
        errors.extend(_corner_rules(data))
    if errors:
        shown = errors[:40]
        more = f"\n… и ещё {len(errors) - len(shown)}" if len(errors) > len(shown) else ""
        raise BookError("книга нарушает схему (М прил. A):\n" + "\n".join(shown) + more)


def _book_errors(data: Mapping, *, pending_ok: bool) -> list[str]:
    """Нарушения схемы книги строками: форма, правила сверх формы, невключаемые ветви (без правила углов)."""
    errors: list[str] = []
    ids = placeholder_ids(data, errors)
    off = switched_off_paths(data)
    last_year = _year_of(_get(data, "meta.last_period"))
    ctx = Ctx(data, ids, off, last_year)
    SPEC.check(data, "", ctx)
    errors.extend(ctx.errors)
    errors.extend(_semantic_errors(data, ids))
    if not pending_ok:
        errors.extend(pending(data))
    return errors


def _semantic_errors(data: Mapping, ids: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Правила сверх формы: модули, книги ЧПД, миры, оси, дисконт за управление."""
    out: list[str] = []
    for switch in UNIMPLEMENTED_SWITCHES:
        if _get(data, switch) is True:
            out.append(f"{switch}: модуль не реализован в ядре — включение запрещено")
    for path, values in UNIMPLEMENTED_VALUES.items():
        if _get(data, path) in values:
            out.append(f"{path} = {_get(data, path)!r}: зарезервировано, ядро не реализует")
    worlds = ids.get("<W>", ())
    for path in ("joint.macro_neutral_world", "nii.transmission.reference_world", "credit.kappa_reference_world",
                 "checks.nim_stationary.world", "nii.transmission.level_world"):
        value = _get(data, path)
        if isinstance(value, str) and worlds and value not in worlds:
            out.append(f"{path} = {value!r}: нет среди worlds.ids")
    first, last = _get(data, "meta.first_period"), _get(data, "meta.last_period")
    anchor = _get(data, "meta.anchor_period")
    if all(isinstance(x, str) and QUARTER_KEY.match(x) for x in (first, last, anchor)):
        fy, fq = map(int, QUARTER_KEY.match(first).groups())
        ay, aq = map(int, QUARTER_KEY.match(anchor).groups())
        if (fy * 4 + fq) != (ay * 4 + aq) + 1:
            out.append("meta.first_period: должен быть следующим кварталом после meta.anchor_period")
        if last < first and len(last) == len(first):
            out.append("meta.last_period раньше meta.first_period")
    books = _get(data, "nii.books")
    if isinstance(books, Mapping):
        out.extend(_book_rules(books))
    comps = _get(data, "valuation.governance.components")
    disc = _get(data, "valuation.governance.discount")
    if isinstance(comps, list) and is_number(disc):
        try:
            total = sum(float(c["sign"]) * float(c["value"]) for c in comps)
            if abs(total - float(disc)) > 1e-12:
                out.append(f"valuation.governance.discount = {disc} ≠ Σ sign × value = {total} (М§8.2)")
        except (KeyError, TypeError, ValueError):
            pass
    steps = _get(data, "dividends.policy.steps")
    if isinstance(steps, list) and len(steps) > 1:
        pays = [s.get("payout") for s in steps if isinstance(s, Mapping)]
        if all(is_number(p) for p in pays) and pays != sorted(pays, reverse=True):
            out.append("dividends.policy.steps: ступени — по убыванию доли выплаты")
    for i, axis in enumerate(_get(data, "valuation.uncertainty.axes") or []):
        out.extend(_axis_rules(data, axis, f"valuation.uncertainty.axes[{i}]"))
    band_paths = {str(p) for ax in _get(data, "valuation.uncertainty.axes") or [] if isinstance(ax, Mapping)
                  for p in ax.get("paths") or []}
    for i, axis in enumerate(_get(data, "valuation.uncertainty.off_band_axes") or []):
        where = f"valuation.uncertainty.off_band_axes[{i}]"
        out.extend(_axis_rules(data, axis, where))
        if isinstance(axis, Mapping):
            if axis.get("kind") not in OFF_BAND_KINDS:
                out.append(f"{where}.kind: вне полосы — только value, shift и bundle (М§10)")
            both = sorted(band_paths & {str(p) for p in axis.get("paths") or []})
            if both:
                out.append(f"{where}: путь {', '.join(both)} и в полосе, и вне полосы")
    out.extend(_bundle_rules(data))
    out.extend(_w1_rules(data, first, last))
    out.extend(_w2_rules(data, ids, anchor))
    out.extend(_w3_rules(data))
    for i, axis in enumerate(_get(data, "valuation.reverse_dcf.axes") or []):
        out.extend(_axis_rules(data, axis, f"valuation.reverse_dcf.axes[{i}]"))
    out.extend(_observation_rules(data, anchor, last))
    out.extend(_unit_interval_rules(data))
    out.extend(_form_rules(data, ids, first, last, anchor))
    out.extend(_pass9_rules(data))
    return out


def _pass9_rules(data: Mapping) -> list[str]:
    """Взаимные ограничения ключей девятого прохода ядра (Р11-2): «средства клиентов» — одно слово, одна величина. Ключ
    балансовой механики `volumes.funds_scope: clients` — только вместе с ключом гейтов `checks.client_funds: clients`
    (иначе база опта и якорь стоят на средствах без К6, а гейты судят средства с К6 — две величины под одним словом)."""
    out: list[str] = []
    if _get(data, "volumes.funds_scope") == "clients" and _get(data, "checks.client_funds") != "clients":
        out.append("volumes.funds_scope = 'clients' при checks.client_funds ≠ 'clients': «средства клиентов» балансовой "
                   "механики и гейтов — одна величина, ключи ставятся вместе (Р11-2, М§4.10)")
    return out


def _form_rules(data: Mapping, ids: Mapping[str, tuple[str, ...]], first: Any, last: Any, anchor: Any) -> list[str]:
    """Взаимные ограничения ключей второй формы банка (М прил. A): делитель, тест истории выплат, режим
    календаря дивидендов, постоянные прочие активы, множитель RWA режима, рост по капиталу, узлы гайденса,
    коридоры новых гейтов."""
    out: list[str] = []
    # делитель (М§8.4)
    if _get(data, "valuation.shares_basis") == "issued" and len(ids.get("<t>", ())) > 1:
        out.append("valuation.shares_basis = 'issued': у двух категорий акций одного делителя нет — "
                   "допустимо только при одном тикере (М§8.4)")
    # тест истории выплат (М§5.2)
    if _get(data, "dividends.policy.history_test") == "cap" and _get(data, "dividends.policy.cap") is None:
        out.append("dividends.policy.cap: нет ключа при history_test = 'cap' (М§5.2)")
    # режим календаря (М§5.7): значение в ключе неактивного режима
    quarterly = _get(data, CALENDAR_MODE) == "quarterly"
    for path in (CALENDAR_ANNUAL if quarterly else QUARTERLY_ONLY):
        if _get(data, path) is not None:
            out.append(f"{path}: ключ неактивного режима календаря ({'quarterly' if quarterly else 'annual'}) — "
                       "ядро его не читает, значение запрещено (М§5.7)")
    if quarterly:
        ahead = _get(data, "dividends.calendar.checkpoints_ahead")
        if isinstance(ahead, int) and not isinstance(ahead, bool) and ahead != 0:
            out.append(f"dividends.calendar.checkpoints_ahead = {ahead}: в квартальном режиме допустим только 0 — "
                       "пробных проходов вперёд нет (М§5.7)")
        if _get(data, "dividends.policy.steps"):
            out.append("dividends.policy.steps: ступени политики в квартальный режим не перенесены — "
                       "список обязан быть пустым (М§5.7)")
    # постоянные прочие активы (М§4.3, §4.11)
    fixed = _get(data, "volumes.other_assets_fixed")
    if (fixed == "anchor" or _nonzero(fixed)) and _get(data, "capital.rwa.density.other_assets_fixed") is None:
        out.append("capital.rwa.density.other_assets_fixed: нет ключа при ненулевых volumes.other_assets_fixed "
                   "(М§4.11)")
    # неработающие деньги со своим драйвером (К8, М§4.11): плотность денег — обязательна при ключе
    if _get(data, "volumes.cash_assets") is not None and _get(data, "capital.rwa.density.cash_assets") is None:
        out.append("capital.rwa.density.cash_assets: нет плотности неработающих денег при volumes.cash_assets "
                   "(К8, М§4.11)")
    out.extend(_cash_share_rules(data, anchor, last))
    out.extend(_guarantee_component_rules(data))
    out.extend(_rwa_mult_rules(data, ids, anchor))
    # жетон DPS (К1, М§4.13.2): значения траектории не меньше нуля
    tok = _get(data, "dividends.min_dps")
    values = [tok] if is_number(tok) else [v for k, v in tok.items() if str(k) != "LT_from" and is_number(v)] \
        if isinstance(tok, Mapping) else []
    if any(float(v) < 0 for v in values):
        out.append("dividends.min_dps: жетон DPS меньше нуля (М§4.13.2)")
    # структурная доля опта (К3, М§4.10): не больше доли якоря — иначе скачок ликвидности в первом квартале
    s_wh, s_anchor = _get(data, "volumes.wholesale_structural_to_funds"), _get(data, "volumes.wholesale_to_funds")
    if is_number(s_wh) and is_number(s_anchor) and float(s_wh) > float(s_anchor):
        out.append(f"volumes.wholesale_structural_to_funds = {s_wh}: структурная доля опта больше доли опта якоря "
                   f"volumes.wholesale_to_funds = {s_anchor} (М§4.10)")
    # выкуп по цене мира (М§5.6): сумма и правило цены, квартальный календарь, подпись строки сверки
    if _get(data, "dividends.buyback.enabled") is True:
        for k in ("amount", "price"):
            if _get(data, f"dividends.buyback.{k}") is None:
                out.append(f"dividends.buyback.{k}: нет ключа при включённом выкупе (М§5.6)")
        if not quarterly:
            out.append("dividends.buyback.enabled: выкуп по цене мира — только при "
                       "dividends.calendar.frequency = 'quarterly' (М§5.6)")
        if _get(data, "meta.labels.control.lines.buyback") is None:
            out.append("meta.labels.control.lines.buyback: нет подписи строки выкупа при включённом выкупе (М§0.6)")
    # год-якорь угасания (К-Т2в, М§7): не позже года last_period — иначе срок начинался бы внутри явных лет
    y_a, ly = _get(data, "valuation.terminal.fade_anchor_year"), _year_of(last)
    if is_number(y_a) and ly is not None and int(y_a) > ly:
        out.append(f"valuation.terminal.fade_anchor_year = {y_a}: год-якорь угасания позже года last_period {ly} — "
                   "срок угасания начинался бы внутри явных лет (М§7)")
    # части блока постоянных частей терминала (М§7): без повторов
    parts = _get(data, "valuation.terminal.fixed_parts")
    if isinstance(parts, list) and len(set(map(str, parts))) != len(parts):
        out.append("valuation.terminal.fixed_parts: часть повторяется (М§7)")
    # веса книг в базе связи расходов с объёмом (М§4.7): хотя бы один вес больше нуля
    weights = _get(data, "opex.volume_weights")
    if isinstance(weights, Mapping) and not any(is_number(v) and v > 0 for v in weights.values()):
        out.append("opex.volume_weights: все веса нулевые — базы связи расходов с объёмом нет (М§4.7)")
    # базы строк (К2, М§4.7): у весов хотя бы один вес больше нуля; доли расходов на базах строк — в сумме меньше 1
    for path in ("fees.volume_base", "other.insurance_volume_base"):
        base = _get(data, path)
        if isinstance(base, Mapping) and "mix" not in base and not any(is_number(v) and v > 0 for v in base.values()):
            out.append(f"{path}: все веса нулевые — базы строки нет (М§4.7)")
    shares = _get(data, "opex.line_shares")
    if isinstance(shares, Mapping) and sum(float(v) for v in shares.values() if is_number(v)) >= 1:
        out.append("opex.line_shares: сумма долей не меньше единицы — базы расходов не осталось (М§4.7)")
    # множители CoR по книгам (М§4.6): одно суждение — одно место — со схемой сегментов не включаются вместе
    if _get(data, "credit.book_relative.enabled") is True and _get(data, "credit.segment_relative.enabled") is True:
        out.append("credit.book_relative.enabled: множители CoR по книгам и множители сегментов "
                   "(credit.segment_relative.enabled) включены вместе — одно суждение живёт в одном месте (М§4.6)")
    # рост по капиталу (М§4.13)
    if _get(data, "capital.growth_constraint.enabled") is True:
        if not quarterly:
            out.append("capital.growth_constraint.enabled: рост по капиталу — только при "
                       "dividends.calendar.frequency = 'quarterly' (М§4.13)")
        gy, fy = _get(data, "volumes.guidance_year"), _year_of(first)
        if is_number(gy) and fy is not None and int(gy) >= fy:
            out.append(f"volumes.guidance_year = {gy}: при росте по капиталу год гайденса роста — раньше года "
                       f"first_period {fy} (М§4.13)")
    # узлы гайденса (М§14.2)
    seen: set[str] = set()
    for i, item in enumerate(_get(data, "checks.guidance_items") or []):
        if not isinstance(item, Mapping):
            continue
        where, key = f"checks.guidance_items[{i}]", item.get("key")
        if key in seen:
            out.append(f"{where}.key = {key!r}: повтор ключа")
        seen.add(key)
        if item.get("gate") is True:
            if not item.get("words"):
                out.append(f"{where}.words: нет слов сообщения гейта при gate: true")
            if key in GUIDANCE_ITEM_KEYS and key not in GUIDANCE_GATE_KEYS:
                out.append(f"{where}.gate: узел {key!r} с путём клетки не сравнивается — только строка выпуска")
    # коридоры новых гейтов (М§14.2)
    fy, ly = _year_of(first), _year_of(last)
    for gate in ("cir_lt", "nim_lt", "window_backtest", "funds_cost_to_key"):
        from_year = _get(data, f"checks.{gate}.from_year")
        if is_number(from_year) and fy is not None and ly is not None and not fy <= int(from_year) <= ly:
            out.append(f"checks.{gate}.from_year = {from_year}: вне лет сетки {fy}…{ly}")
    if _get(data, "checks.payout_cap") is not None and _get(data, "dividends.policy.history_test") != "cap":
        out.append("checks.payout_cap: допуск гейта потолка выплат — только при dividends.policy.history_test = "
                   "'cap' (М§14.2)")
    # справочные варианты (М§14.5): идентификаторы различны; подмена не трогает сам список и ложится на ключ
    # книги либо вводит новый ключ в существующий раздел (остальное судит схема на книге варианта)
    seen_ids: set[str] = set()
    for i, variant in enumerate(_get(data, "valuation.reference_variants") or []):
        if not isinstance(variant, Mapping):
            continue
        where = f"valuation.reference_variants[{i}]"
        if variant.get("id") in seen_ids:
            out.append(f"{where}.id = {variant.get('id')!r}: повтор идентификатора варианта")
        seen_ids.add(variant.get("id"))
        overrides = variant.get("overrides")
        for path in overrides if isinstance(overrides, Mapping) else ():
            head = str(path).rpartition(".")[0]
            if str(path).startswith("valuation.reference_variants"):
                out.append(f"{where}.overrides: путь {path} — список вариантов подменой не меняют")
            elif not head or not isinstance(_get(data, head), Mapping):
                out.append(f"{where}.overrides: путь {path} — раздела {head or path} в книге нет")
    # строки обратного расчёта с уточнением на полной полосе (М§11.2) — ключи строк книги, без повторов
    rows = {paths_key(ax["paths"]) for ax in _get(data, "valuation.reverse_dcf.axes") or []
            if isinstance(ax, Mapping) and isinstance(ax.get("paths"), list) and ax["paths"]}
    named = _get(data, "valuation.reverse_dcf.refine_rows")
    for i, key in enumerate(named if isinstance(named, list) else ()):
        if isinstance(key, str) and key not in rows:
            out.append(f"valuation.reverse_dcf.refine_rows[{i}] = {key!r}: нет строки обратного расчёта с таким "
                       "ключом (М§11.2)")
        if key in named[:i]:
            out.append(f"valuation.reverse_dcf.refine_rows[{i}] = {key!r}: повтор ключа строки")
    # элементы премий роста, названные фактом (М§11.3): число траектории премии сектора, не LT_from
    facts_named = _get(data, "valuation.reverse_dcf.premium_facts")
    for i, path in enumerate(facts_named if isinstance(facts_named, list) else ()):
        if not isinstance(path, str):
            continue
        head, _, last = path.rpartition(".")
        if (head.rpartition(".")[0] not in PREMIUM_ROOTS or last == "LT_from"
                or not isinstance(_get(data, head), Mapping) or not is_number(_get(data, path))):
            out.append(f"valuation.reverse_dcf.premium_facts[{i}] = {path!r}: не число траектории премии роста "
                       f"({', '.join(PREMIUM_ROOTS)}; М§11.3)")
    # подписи базы суммы дивиденда — только парой: выпуск несёт коды базы сумм, когда есть обе (М прил. A)
    pair = [_get(data, f"meta.labels.basis.{k}") is not None for k in ("dividend_issued", "dividend_outstanding")]
    if any(pair) and not all(pair):
        out.append("meta.labels.basis: подписи dividend_issued и dividend_outstanding задаются только парой")
    return out


def _rwa_mult_rules(data: Mapping, ids: Mapping[str, tuple[str, ...]], anchor: Any) -> list[str]:
    """Множитель RWA режима (М§4.11): значения > 0; у режима с годом шока наименьшее значение стоит на ключе
    года шока, и ось полосы водит только его."""
    out: list[str] = []
    anchor_year = _year_of(anchor)
    shock_of: dict[str, int | None] = {}
    for r in ids.get("<r>", ()):
        spec = _get(data, f"regimes.{r}")
        if not isinstance(spec, Mapping) or spec.get("rwa_density_mult") is None:
            continue
        where, mult = f"regimes.{r}.rwa_density_mult", spec["rwa_density_mult"]
        values = ({str(k): v for k, v in mult.items() if str(k) != "LT_from" and is_number(v)}
                  if isinstance(mult, Mapping) else {"": mult} if is_number(mult) else {})
        for k, v in values.items():
            if float(v) <= 0:
                out.append(f"{_join(where, k) if k else where} = {v}: множитель RWA — больше нуля (М§4.11)")
        off = spec.get("shock_year_offset")
        shock = anchor_year + off if isinstance(off, int) and not isinstance(off, bool) and anchor_year else None
        shock_of[where] = shock
        if shock is not None and isinstance(mult, Mapping) and values:
            low = min(float(v) for v in values.values())
            if str(shock) not in values or float(values[str(shock)]) > low:
                out.append(f"{where}: наименьшее значение множителя стоит не на ключе года шока {shock} (М§4.11)")
    for group in AXIS_ENDS:
        for i, axis in enumerate(_get(data, group) or []):
            for path in (axis.get("paths") or []) if isinstance(axis, Mapping) else []:
                head, _, last_key = str(path).rpartition(".")
                shock = shock_of.get(head)
                if shock is not None and YEAR_KEY.match(last_key) and int(last_key) != shock:
                    out.append(f"{group}[{i}]: путь {path} — ось множителя RWA режима допустима только для года "
                               f"шока {shock} (М§4.11)")
    return out


# Таблицы вероятностей книги (М§3.4, §9): каждое значение — вероятность.
PROBABILITY_TABLES = ("joint.world_prob", "joint.world_prob_market_implied", "joint.regime_prob",
                      "joint.reg_prob_given_regime")
# Доли книги с границами [0; 1] (у `nii.sigma0_split`, `nii.phi_split` и
# `joint.regime_update.floor_share` — свои правила выше).
UNIT_SHARES = {"joint.own_macro_confidence": "доверие своему взгляду на ставки λ (М§9)",
               "dividends.excess.epsilon": "доля выплаты избытка ε (М§5.3)"}
# Концы оси, которые подставляются в книгу как есть: у оси полосы — low и high, у оси обратного
# расчёта — отрезок поиска и таблица, к которой идёт смесь.
AXIS_ENDS = {"valuation.uncertainty.axes": ("low", "high"), "valuation.uncertainty.off_band_axes": ("low", "high"),
             "valuation.reverse_dcf.axes": ("search", "toward")}


def _outside_unit(path: str, value: Any, what: str) -> list[str]:
    """Числа значения (число, список или словарь любой глубины) вне [0; 1] — строками ошибок."""
    if isinstance(value, Mapping):
        return [e for k, v in value.items() for e in _outside_unit(f"{path}.{k}", v, what)]
    if isinstance(value, (list, tuple)):
        return [e for v in value for e in _outside_unit(path, v, what)]
    if is_number(value) and not 0 <= float(value) <= 1:
        return [f"{path} = {value}: {what} — от 0 до 1"]
    return []


def _under(path: str, roots: Iterable[str]) -> bool:
    return any(path == root or path.startswith(root + ".") for root in roots)


def _steps(value: Any) -> list[float]:
    """Приращения конца оси-сдвига: число (конец оси полосы) или пара чисел (отрезок поиска обратного расчёта)."""
    if is_number(value):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value if is_number(v)]
    return []


def _unit_interval_rules(data: Mapping) -> list[str]:
    """Вероятности и доли книги — в [0; 1] (М§3.4, §5.3, §9; сумму таблицы держит инвариант `probabilities`).

    Без правила отрицательная вероятность при сумме 1 давала отрицательные веса клеток, ε > 1 — выплату
    сверх запаса капитала, λ вне [0; 1] — точку за пределами слоёв. То же — концам осей, у которых путь —
    такая вероятность или доля: ось подставляет их в книгу (смесь оси словаря и смесь обратного расчёта —
    выпуклые). У оси вида «сдвиг» концы — приращения: в книгу ложится её значение плюс приращение, и
    проверяется оно — иначе книга прошла бы загрузку и не прошла прогон полосы. Вероятность таблицы
    сдвигом не водят: сумма таблицы перестала бы быть 1."""
    out: list[str] = []
    for table in PROBABILITY_TABLES:
        out.extend(_outside_unit(table, _get(data, table), "вероятность (М§3.4)"))
    for path, what in UNIT_SHARES.items():
        out.extend(_outside_unit(path, _get(data, path), what))
    bounded = tuple(PROBABILITY_TABLES) + tuple(UNIT_SHARES)
    for group, ends in AXIS_ENDS.items():
        for i, axis in enumerate(_get(data, group) or []):
            if not isinstance(axis, Mapping):
                continue
            hit = [p for p in map(str, axis.get("paths") or []) if _under(p, bounded)]
            if not hit:
                continue
            where = f"{group}[{i}]"
            if axis.get("kind") == "bundle":            # связка: концы — по путям, проверяется конец своего пути
                for end in ends:
                    table = axis.get(end)
                    for p in hit:
                        if isinstance(table, Mapping) and p in table:
                            out.extend(_outside_unit(f"{where}.{end}.{p}", table[p],
                                                     "конец оси вероятности или доли (М§10)"))
                continue
            if axis.get("kind") != "shift":
                for end in ends:
                    out.extend(_outside_unit(f"{where}.{end}", axis.get(end),
                                             "конец оси вероятности или доли (М§10, §11.1)"))
                continue
            for p in hit:
                if _under(p, PROBABILITY_TABLES):
                    out.append(f"{where}: ось-сдвиг по вероятности {p} — сумма таблицы перестала бы быть 1 "
                               "(М§3.4, §10)")
                    continue
                base = _get(data, p)
                if not is_number(base):
                    continue
                for end in ends:
                    for step in _steps(axis.get(end)):
                        if not 0 <= float(base) + step <= 1:
                            out.append(f"{where}.{end} = {step:g}: {p} = {base} со сдвигом — вне [0; 1] "
                                       "(М§10, §11.1)")
    return out


def _period_index(period: Any) -> int | None:
    if isinstance(period, str):
        m = QUARTER_KEY.match(period)
        if m:
            return int(m.group(1)) * 4 + int(m.group(2))
    return None


def _observation_rules(data: Mapping, anchor: Any, last: Any) -> list[str]:
    """Наблюдения A-P2u (М§12): погрешность у наблюдённой величины; квартал не позже якоря несёт
    замороженные ожидания режимов `mu_<x>` наблюдённых величин, прогнозный квартал — нет."""
    out: list[str] = []
    a, z = _period_index(anchor), _period_index(last)
    seen: set[str] = set()
    for i, obs in enumerate(_get(data, "joint.regime_update.observations") or []):
        if not isinstance(obs, Mapping):
            continue
        where = f"joint.regime_update.observations[{i}]"
        for x in ("cor", "nim"):
            if obs.get(x) is not None and obs.get(f"se_{x}") is None:
                out.append(f"{where}.se_{x}: null при наблюдённом {x}")
        per = obs.get("period")
        q = _period_index(per)
        if q is None or a is None:
            continue
        if per in seen:
            out.append(f"{where}.period = {per}: второе наблюдение того же квартала")
        seen.add(per)
        if z is not None and q > z:
            out.append(f"{where}.period = {per}: позже last_period (М§12)")
        for x in ("cor", "nim"):
            key = f"mu_{x}"
            if q <= a and obs.get(x) is not None and not isinstance(obs.get(key), Mapping):
                out.append(f"{where}.{key}: наблюдение квартала не позже якоря без замороженных ожиданий "
                           "режимов (их пишет перезаякоривание, М§12, §15.2)")
            if q > a and key in obs:
                out.append(f"{where}.{key}: у наблюдения прогнозного квартала ожидания режимов считает "
                           "ядро — ключа быть не должно (М§12)")
    return out


def _quarter_no(period: Any) -> int | None:
    """Номер квартала ГГГГQn сквозным счётом (год × 4 + квартал); не квартал — None."""
    m = QUARTER_KEY.match(period) if isinstance(period, str) else None
    return int(m.group(1)) * 4 + int(m.group(2)) if m else None


def _cash_share_rules(data: Mapping, anchor: Any, last: Any) -> list[str]:
    """Доля неработающих денег книги (Р6-1, проход ядра 5, М§4.3): при числовой доле `share` обязательны ФОР якоря
    `reserves` и квартал доли книги `share_from` — после квартала якоря и не позже `meta.last_period`; поля ключа доли без
    `share` — отказ (читаются только при доле); при `share: anchor` — прежняя ветвь К8: поля проверены формой, но не
    читаются."""
    key = "volumes.cash_assets"
    spec = _get(data, key)
    if not isinstance(spec, Mapping):
        return []
    share = spec.get("share")
    if share is None:
        extra = [f for f in CASH_SHARE_FIELDS if spec.get(f) is not None]
        return [f"{key}.{f}: читается только при доле денег книги {key}.share — без неё значение запрещено (Р6-1, "
                "М§4.3)" for f in extra]
    if share == "anchor":
        return []
    out: list[str] = []
    for f, words in (("reserves", "ФОР якоря"), ("share_from", "квартал доли книги")):
        if spec.get(f) is None:
            out.append(f"{key}.{f}: нет ключа при доле денег книги share = {share} — нужны ФОР якоря и квартал доли "
                       f"книги ({words}; Р6-1, М§4.3)")
    frm = spec.get("share_from")
    q_f, q_a, q_l = _quarter_no(frm), _quarter_no(anchor), _quarter_no(last)
    if q_f is not None and q_a is not None and q_f <= q_a:
        out.append(f"{key}.share_from = {frm}: квартал доли книги не позже квартала якоря {anchor} — путь доли идёт от "
                   "якоря (Р6-1, М§4.3)")
    if q_f is not None and q_l is not None and q_f > q_l:
        out.append(f"{key}.share_from = {frm}: квартал доли книги позже meta.last_period {last} (Р6-1, М§4.3)")
    return out


def _guarantee_component_rules(data: Mapping) -> list[str]:
    """Драйвер RWA гарантий `fees_component` (Р5-5, М§4.11): при включённом К5 поле `component` обязательно и названо
    среди компонент смеси `fees.volume_base.mix`; при других драйверах поле — ключ неактивного режима (не читается,
    значение допустимо)."""
    key = "capital.rwa.guarantees"
    if _get(data, f"{key}.enabled") is not True or _get(data, f"{key}.driver") != "fees_component":
        return []
    name, base = _get(data, f"{key}.component"), _get(data, "fees.volume_base")
    if name is None:
        return [f"{key}.component: нет ключа при driver = fees_component — компонента смеси базы комиссий не названа "
                "(Р5-5, М§4.11)"]
    if not (isinstance(base, Mapping) and isinstance(base.get("mix"), Mapping)):
        return [f"{key}.driver = fees_component: fees.volume_base — не смесь {{mix: …}}, компоненты нет (Р5-5, М§4.11)"]
    if str(name) not in base["mix"]:
        return [f"{key}.component = {name!r}: нет среди компонент смеси fees.volume_base.mix "
                f"({', '.join(map(str, base['mix']))}; Р5-5, М§4.11)"]
    return []


def _w3_rules(data: Mapping) -> list[str]:
    """Ключи W3 (М прил. A): доля сжатия φ на активах, пол вероятности режима, окно рангов оценщика
    срединных прогонов, допуск нейтрального значения."""
    out: list[str] = []
    split = _get(data, "nii.phi_split")
    books = _get(data, "nii.books")
    if is_number(split) and isinstance(books, Mapping):
        if not 0 <= float(split) <= 1:
            out.append(f"nii.phi_split = {split}: доля от 0 до 1 (М§4.5)")
        has = {side: any(isinstance(b, Mapping) and b.get("side") == side and b.get("phi") is True
                         for b in books.values()) for side in ("asset", "liability")}
        if float(split) > 0 and not has["asset"]:
            out.append("nii.phi_split > 0, а активов с phi нет (М§4.5)")
        if float(split) < 1 and not has["liability"]:
            out.append("nii.phi_split < 1, а пассивов с phi нет (М§4.5)")
    if isinstance(books, Mapping):
        flags = [bool(books[b].get("phi")) for b in RETAIL_BOOKS if isinstance(books.get(b), Mapping)]
        if len(set(flags)) > 1:
            out.append(f"nii.books.{RETAIL_BOOKS[0]}.phi ≠ nii.books.{RETAIL_BOOKS[1]}.phi: у обеих книг средств "
                       "ФЛ флаг одинаков — иначе объём сжатия зависел бы от раскладки (М§4.5)")
    share = _get(data, "joint.regime_update.floor_share")
    if is_number(share) and not 0 <= float(share) <= 1:
        out.append(f"joint.regime_update.floor_share = {share}: доля от 0 до 1 (М§12)")
    window = _get(data, "valuation.sensitivities.rank_window")
    if isinstance(window, (list, tuple)) and len(window) == 2 and all(map(is_number, window)):
        if not 0 <= float(window[0]) < float(window[1]) <= 1:
            out.append(f"valuation.sensitivities.rank_window = {list(window)}: нужно 0 ≤ нижний < верхний ≤ 1 (М§10)")
    tol = _get(data, "valuation.next_report.value_tol")
    if is_number(tol) and float(tol) <= 0:
        out.append(f"valuation.next_report.value_tol = {tol}: нужно число > 0 (М§13)")
    return out


def _w2_rules(data: Mapping, ids: Mapping[str, tuple[str, ...]], anchor: Any) -> list[str]:
    """Ключи W2 (М прил. A): окно A-P2u, режим-опора FVC, доля σ0 на активах, год шока кризиса."""
    out: list[str] = []
    n = _get(data, "joint.regime_update.window_obs")
    if isinstance(n, int) and not isinstance(n, bool) and n < 1:
        out.append(f"joint.regime_update.window_obs = {n}: нужно целое ≥ 1 (М§12)")
    ref = _get(data, "credit.fv_loans_ref")
    regimes = ids.get("<r>", ())
    if isinstance(ref, str) and regimes and ref not in regimes:
        out.append(f"credit.fv_loans_ref = {ref!r}: нет среди regimes.ids (М§4.6)")
    split = _get(data, "nii.sigma0_split")
    books = _get(data, "nii.books")
    if is_number(split) and isinstance(books, Mapping):
        if not 0 <= float(split) <= 1:
            out.append(f"nii.sigma0_split = {split}: доля от 0 до 1 (М§4.5)")
        has = {side: any(isinstance(b, Mapping) and b.get("side") == side and b.get("lt_shift") is True
                         for b in books.values()) for side in ("asset", "liability")}
        if float(split) > 0 and not has["asset"]:
            out.append("nii.sigma0_split > 0, а активов с lt_shift нет (М§4.5)")
        if float(split) < 1 and not has["liability"]:
            out.append("nii.sigma0_split < 1, а пассивов с lt_shift нет (М§4.5)")
    anchor_year = _year_of(anchor)
    for r in regimes:
        spec = _get(data, f"regimes.{r}")
        if not isinstance(spec, Mapping):
            continue
        where = f"regimes.{r}"
        off = spec.get("shock_year_offset")
        if off is None:
            for k in ("one_off_loss", "loan_growth_override"):
                if spec.get(k):
                    out.append(f"{where}.{k}: кризисный ключ без {where}.shock_year_offset (М§3.2)")
            continue
        if not isinstance(off, int) or isinstance(off, bool):
            continue
        if off < 1:
            out.append(f"{where}.shock_year_offset = {off}: нужно целое ≥ 1 (М§3.2)")
            continue
        if anchor_year is None:
            continue
        shock = anchor_year + off
        cor = spec.get("cor")
        if isinstance(cor, Mapping):
            wrong = sorted(str(k) for k in cor if QUARTER_KEY.match(str(k)) and int(str(k)[:4]) != shock)
            if wrong:
                out.append(f"{where}.cor: квартальные ключи {', '.join(wrong)} вне года шока {shock} (М§3.2)")
        one = spec.get("one_off_loss")
        if isinstance(one, Mapping) and _year_of(one.get("period")) not in (None, shock):
            out.append(f"{where}.one_off_loss.period = {one.get('period')}: вне года шока {shock} (М§3.2)")
        ov = spec.get("loan_growth_override")
        if isinstance(ov, Mapping) and ov:
            years = sorted(int(str(k)) for k in ov if YEAR_KEY.match(str(k)))
            if years and years[0] != shock:
                out.append(f"{where}.loan_growth_override: первый год {years[0]} — не год шока {shock} (М§3.2)")
    return out


def _w1_rules(data: Mapping, first: Any, last: Any) -> list[str]:
    """Ключи W1: год σ0, доли «прочего», ввод ε, число кварталов проверок (М прил. A)."""
    out: list[str] = []
    fy, ly = _year_of(first), _year_of(last)
    y0 = _get(data, "nii.sigma0_from")
    if is_number(y0) and fy is not None and ly is not None and not fy <= int(y0) <= ly:
        out.append(f"nii.sigma0_from = {y0}: вне лет сетки {fy}…{ly} (М§4.4)")
    shares = _get(data, "other.misc_quarter_shares")
    if isinstance(shares, Mapping) and all(is_number(shares.get(k)) for k in ("1", "2", "3", "4")):
        total = sum(float(shares[k]) for k in ("1", "2", "3", "4"))
        if abs(total - 1.0) > 1e-9:
            out.append(f"other.misc_quarter_shares: сумма долей {total:.9g} ≠ 1 (М§4.7)")
    for key in ("dividends.excess.ramp_years", "checks.nim_path_joint.quarters", "checks.ni_jump.quarters"):
        n = _get(data, key)
        if isinstance(n, int) and not isinstance(n, bool) and n < 1:
            out.append(f"{key} = {n}: нужно целое ≥ 1")
    return out


def _book_rules(books: Mapping) -> list[str]:
    out: list[str] = []
    for name, spec in books.items():
        if not isinstance(spec, Mapping):
            continue
        p = f"nii.books.{name}"
        side = spec.get("side")
        balancing = spec.get("balancing") is True
        if side == "liability":
            if "beta" not in spec:
                out.append(f"{p}.beta: нет ключа (пассив)")
            for k in ("sector", "cor_segment", "fv_share"):
                if k in spec:
                    out.append(f"{p}.{k}: ключ актива у пассива")
        elif side == "asset":
            if "phi" not in spec:
                out.append(f"{p}.phi: нет ключа (актив)")
            if "beta" in spec:
                out.append(f"{p}.beta: ключ пассива у актива")
            if not balancing:
                for k in ("sector", "cor_segment"):
                    if k not in spec:
                        out.append(f"{p}.{k}: нет ключа (кредитная книга)")
            elif "sector" in spec or "fv_share" in spec:
                out.append(f"{p}: у балансирующей книги нет сектора и доли СС")
    return out


OFF_BAND_KINDS = ("value", "shift", "bundle")       # виды осей, допустимые вне полосы (М§10)
BAND_GROUPS = ("valuation.uncertainty.axes", "valuation.uncertainty.off_band_axes")


def _paths_of(axis: Any) -> list[str]:
    return [str(p) for p in axis.get("paths") or []] if isinstance(axis, Mapping) else []


def _bundle_rules(data: Mapping) -> list[str]:
    """Оси-связки (М§10): концы `low` и `high` — словари «путь → значение» ровно по путям оси; путь связки не
    стоит ни на оси вида `value`, ни внутри словаря оси вида `dict`, ни на другой связке. С осью вида `shift`
    путь делить можно: приращения складываются. При сложении связок (ключ `bundle_compose: additive`, Р5-4) путь
    делят и связки между собой; тогда же первые пути осей попарно различны (`_first_path_rules`)."""
    out: list[str] = []
    axes = [(f"{group}[{i}]", axis) for group in BAND_GROUPS for i, axis in enumerate(_get(data, group) or [])
            if isinstance(axis, Mapping)]
    additive = _get(data, BUNDLE_COMPOSE) == "additive"
    if additive:
        out.extend(_first_path_rules(axes))
    for n, (where, axis) in enumerate(axes):
        paths = _paths_of(axis)
        bundle = axis.get("kind") == "bundle"
        for end in ("low", "high"):
            table = axis.get(end)
            if bundle and (not isinstance(table, Mapping) or set(map(str, table)) != set(paths)):
                out.append(f"{where}.{end}: у связки конец оси — словарь «путь → значение» ровно по путям оси (М§10)")
            if not bundle and axis.get("kind") in ("value", "shift") and isinstance(table, Mapping):
                out.append(f"{where}.{end}: у оси вида {axis.get('kind')} конец — число, в книге словарь")
        if not bundle:
            continue
        if len(set(paths)) != len(paths):
            out.append(f"{where}: путь связки повторяется (М§10)")
        for m, (other_where, other) in enumerate(axes):
            if m == n or other.get("kind") == "shift" or (other.get("kind") == "bundle" and (m < n or additive)):
                continue
            shared = [p for p in paths if any(p == o or p.startswith(o + ".") for o in _paths_of(other))]
            if shared:
                out.append(f"{where}: путь связки {', '.join(dict.fromkeys(shared))} стоит и на оси "
                           f"{other_where} вида {other.get('kind')} — приращение связки складывается только с "
                           "осью вида shift (М§10)")
    return out


def _first_path_rules(axes: list[tuple[str, Mapping]]) -> list[str]:
    """Сложение связок (Р5-4, М§10): первые пути осей попарно различны — первый путь есть адрес оси (лист вывода пишет
    концы связки по нему, печать и общие случайные числа инструментов — по виду и первому пути); повтор — отказ с
    обоими местами."""
    out: list[str] = []
    seen: dict[str, str] = {}
    for where, axis in axes:
        paths = _paths_of(axis)
        if not paths:
            continue
        if paths[0] in seen:
            out.append(f"{where}: первый путь {paths[0]} — тот же, что у оси {seen[paths[0]]}; при сложении связок "
                       "первый путь — адрес оси (лист вывода, печать, общие случайные числа), у каждой оси свой "
                       "(Р5-4, М§10)")
        else:
            seen[paths[0]] = where
    return out


def _corner_rules(data: Mapping) -> list[str]:
    """Правило углов сложения осей (Р5-4, М§10; только при `bundle_compose: additive`): путь p, который несут две и
    более оси-приращения полосы — связки (Δ на концах: конец − значение книги) и сдвиги (Δ — концы оси) на самом пути
    или на траектории, чьим элементом p является, — в углах v_min = c + Σ min(0, Δ_low, Δ_high) и v_max = c + Σ max(0,
    Δ_low, Δ_high) обязан проходить схему: книга-копия со всеми такими путями в углу v_min, затем в углу v_max,
    проверяется схемой (без этого правила). Судится книга, чьи значения — центр связок (загрузка книги); у копии
    (`Book.with_overrides`: прогон, вариант, строка обратного расчёта) значения — подмены, правило не применяется."""
    if _get(data, BUNDLE_COMPOSE) != "additive":
        return []
    axes = [axis for axis in _get(data, "valuation.uncertainty.axes") or [] if isinstance(axis, Mapping)]
    steps: dict[str, list[tuple[float, float]]] = {}
    for axis in axes:
        if axis.get("kind") != "bundle":
            continue
        for p in _paths_of(axis):
            c, lo, hi = _get(data, p), (axis.get("low") or {}).get(p), (axis.get("high") or {}).get(p)
            if all(is_number(x) for x in (c, lo, hi)):
                c = float(c)
                steps.setdefault(p, []).append(((c + (float(lo) - c)) - c, (c + (float(hi) - c)) - c))
    for p, got in steps.items():
        for axis in axes:
            if axis.get("kind") == "shift" and any(_under(p, [o]) for o in _paths_of(axis)):
                lo, hi = axis.get("low"), axis.get("high")
                if is_number(lo) and is_number(hi):
                    got.append((float(lo), float(hi)))
    shared = {p: got for p, got in steps.items() if len(got) >= 2}
    out: list[str] = []
    if not shared:
        return out
    for side, pick in (("v_min", min), ("v_max", max)):
        corner = copy.deepcopy(dict(data))
        values = {}
        for p, got in shared.items():
            values[p] = float(_get(data, p)) + math.fsum(pick(0.0, a, b) for a, b in got)
            _put(corner, p, values[p])
        for err in _book_errors(corner, pending_ok=True):
            hit = [p for p in shared if p in err] or sorted(shared)
            out.append(f"угол сложения осей на пути {', '.join(hit)} ({side} = "
                       f"{', '.join(f'{values[p]:.6g}' for p in hit)}): {err} (Р5-4, М§10)")
    return out


def _put(data: dict, path: str, value: Any) -> None:
    """Значение по точечному пути копии книги (путь существует: его значение прочитано `_get`)."""
    *head, last = path.split(".")
    cur = data
    for part in head:
        cur = cur[part]
    cur[last] = value


def _axis_rules(data: Mapping, axis: Any, where: str) -> list[str]:
    out: list[str] = []
    if not isinstance(axis, Mapping):
        return out
    kind = axis.get("kind")
    for path in axis.get("paths") or []:
        value = _get(data, str(path))
        if value is None:
            out.append(f"{where}: путь {path} не найден в книге")
            continue
        if kind == "bundle":
            if str(path).rpartition(".")[2] == "LT_from":
                out.append(f"{where}: путь {path} — год LT_from связкой не водят (М§10)")
            elif not is_number(value):
                out.append(f"{where}: путь {path} — не число (вид bundle: элемент траектории — точечным ключом)")
        if kind == "value" and not is_number(value):
            out.append(f"{where}: путь {path} — не число (вид value)")
        if kind in ("value", "bundle"):
            head, _, last_key = str(path).rpartition(".")
            parent = _get(data, head) if head else None
            if YEAR_KEY.match(last_key) and isinstance(parent, Mapping) and any(
                    QUARTER_KEY.match(str(k)) and str(k).startswith(last_key) for k in parent):
                out.append(f"{where}: путь {path} — ключ года траектории с квартальными ключами этого "
                           "года (ключ года — среднее кварталов, М§0.4)")
        if kind == "dict" and not isinstance(value, Mapping):
            out.append(f"{where}: путь {path} — не словарь долей (вид dict)")
        if kind == "mix" and not isinstance(value, Mapping):
            out.append(f"{where}: путь {path} — не таблица (вид mix)")
    return out


def read_paths(data: Mapping) -> list[str]:
    """Листовые пути книги, которые ядро читает при данных выключателях."""
    off = switched_off_paths(data)
    out: list[str] = []

    def walk(value: Any, path: str) -> None:
        if path in off:
            return
        if isinstance(value, Mapping):
            for k, v in value.items():
                walk(v, _join(path, str(k)))
        elif isinstance(value, list) and value and isinstance(value[0], Mapping):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")
        else:
            out.append(path)

    walk(data, "")
    return out
