"""Перевывод книги одной командой: от «поменяли суждение в шаблоне книги» до «новый заголовок и проверки».

    python -B ops/tools/rederive.py [--dry-run] [--centre-only] [--no-derive] [--no-quick] [--serial] [--exact]
                                    [--runs N] [--workers N] [--no-variants] [--no-classes] [--label МЕТКА]
                                    [--compare МЕТКА] [--dir КАТАЛОГ]
    python -B ops/tools/rederive.py --show МЕТКА [--compare МЕТКА]

Часть чисел книги — не суждения, а числа, подобранные под суждения: корни расходов под цель расходов к доходам,
ближний путь маржи, концы осей, траектория инструментов капитала (docs/MODEL.md §3.5). Подбор делает лист книги
(`data/assumptions/evidence/path/`); команда его зовёт, а не повторяет, и ни одного правила модели и подбора не
меняет. Что такое шаг, в какой ключ шаблона ложится его число, в каких пределах число разумно — описание рядом с
листом (`derive_spec.py`): у другой книги переписываются лист и описание, команда — нет.

Путь команды:
  1. сборка машинной книги из шаблона в рабочий каталог запуска (суждение правят в шаблоне);
  2. подбор: лист выводит числа центра до сходимости, затем концы осей и проверки — на записанных числах центра
     (фазы описания; `--serial` — один запуск листа со всеми шагами, запись та же). Подбор делается один раз, для
     центра: полоса, оси и справочные варианты выведенные числа не пересчитывают;
  3. остановка, если подбор не сошёлся, невязка правила больше допуска, число вышло за свой коридор или суждение,
     которое лист держит константой, разошлось с книгой, — в шаблон тогда не пишется ничего;
  4. запись в шаблон — точечная и точная: по каждому числу печатается «было → стало», в тексте шаблона меняются
     только сами числа и дата пометки «ВЫВЕДЕНО НА ЯДРЕ»; повторный разбор сверяет, что изменились ровно намеченные
     ключи и ровно на намеченные значения, а текст вне заменённых мест цел. После записи шаблон равен записи
     вывода во ВСЕХ выведенных числах (в точности записи) — команда это сверяет, иначе не пишет ничего: ни одно
     число не пропускается поодиночке. Дрожание последнего знака между повторными запусками (лист на записанной
     книге делает ещё один круг связанных шагов) гасит правило сходимости: если книга уже несёт запись вывода
     (шаблон равен записи вывода дерева во всех выведенных числах), а повторный вывод отличается от неё только
     дрожанием — сдвигом чисел центра не больше зоны сходимости описания и вызванным им сдвигом чисел шагов после
     центра не больше той же зоны, — вывод признаётся сошедшимся к записанному: «изменений нет», не пишется ни
     шаблон, ни запись вывода, числа в зоне печатаются отдельно. Любое отличие сверх этого — и пишется всё.
     Правило не отличит дрожание от настоящего сдвига той же величины (суждение поправили так мало, что все
     числа ушли не дальше единицы знака): ключ `--exact` пишет любое отличие, правило сходимости не применяя;
     Пороги и коридоры гейтов (ключи под `checks`, кроме полей окна фактов) команда СВЕРЯЕТ с правилом листа,
     но не пишет: порог гейта, который сам идёт за результатом, ничего не сторожит. Расхождение печатается
     отдельным блоком, стоит красным флагом и строкой в листе решения; перенести порог — решение ведущего;
     ведущий может решить и иначе: пороги, названные описанием вывода (`GATE_RULES`), команда ПИШЕТ по правилу
     листа (решения ведущего № 10, Р10-16: пороги после правок книги пишет команда, ведущий не переносит руками) —
     «было → стало» в блоке записи с пометкой «порог гейта по правилу листа», как всякое выведенное число;
     Файлы-спутники шаблона (описание, `COMPANIONS`): YAML рядом с шаблоном, в который те же выведенные числа
     пишутся тем же точечным способом — по адресу от корня файла, с коридором и сверкой повторным разбором
     (так живут подмены книги, ждущие ядра: их числа — того же вывода и руками не правятся). Спутник пишется,
     когда его числа не равны записи вывода, которая лежит (или ляжет) в дереве; сухой прогон кладёт его в
     рабочий каталог запуска;
  5. пересборка машинной книги и проверка схемы; запись листа вывода — рядом с листом (она пишется вместе с
     шаблоном, а без правки шаблона — когда запись дерева не равна новой записи листа или её нет);
  6. быстрые числа: точка по сетке и малая полоса (`--runs` прогонов, `--workers` процессов, зерно книги) —
     ПРЕДВАРИТЕЛЬНО: медиана малой полосы стоит рядом с медианой полной, а не равна ей;
  7. приёмочные проверки чисел одним блоком: уровни слоя «рыночные ставки как есть» против окна фактов; модальная
     клетка, слои и смесь заголовка рядом с окном; предельная экономика роста; знаки; порядок (ROE, P/B, P/E);
     цена правил и развилок; сработавшие гейты с объяснениями; листы приёмочных проверок книги (описание,
     `ACCEPTANCE`) — сверка пути года якоря с фактами и проверки до счёта оценки; затем проверки классов ошибок в
     модели (PLAYBOOK §2а, `ops/tools/class_checks.py` отдельным процессом на той же книге; законные связи и допуски —
     `data/assumptions/class_checks.yaml`): тождества капитала и баланса, числа одной клетки, продление явных лет,
     оси в центре и на концах, переходные слагаемые, центры по правилам устава;
  8. итог «было → стало» против прошлого запуска (запись каждого запуска — `var/rederive/<метка>.json`, вне git)
     и блок для листа решения (`<метка>.md`).

КРАСНЫЕ ФЛАГИ печатаются первой строкой итога, числом и перечнем, и тем же перечнем стоят в клетке «Проверки»
листа решения. Флаг — каждое отклонение блока приёмочных проверок: уровень слоя условий окна вне окна (маржа,
стоимость риска, расходы к доходам); модальная клетка, ожидание слоёв или смесь заголовка вне окна; цель расходов
к доходам вне допуска; предельная экономика роста вне нормы (якорь расходится с фактом сегмента; мир, где
предельный кредит не окупает капитал; лист не отработал); невыполненный гейт знака; гейт без действующего
объяснения; нарушенный инвариант; каждое срабатывание проверки классов ошибок (и блок классов, который не отработал;
«правил нет» у класса 6 до устава и «не проверялось» у пустой проверки — не флаг, но и не зелёно; строка класса несёт
счёт проверенного) — и порог гейта, не равный правилу листа (шаг 4). Строки «флагов нет» рядом с
отклонением того же запуска не бывает: блок и флаги читают одни и те же условия.

Режимы: `--dry-run` — весь путь на пробной книге рабочего каталога, в дерево под git не пишется ничего;
`--centre-only` — пробный счёт решения: лист выводит только центр (первая фаза описания — малая доля времени
листа), книга — пробная, в дерево не пишется ничего; точка, уровни, знаки и развилки верны для нового центра, а
малая полоса стоит на прежних концах осей — её медиана только ориентир;
`--no-derive` — без подбора: быстрые числа и проверки на книге как есть; `--no-quick` — только подбор и запись;
`--no-classes` — без блока проверок классов ошибок (он идёт после приёмочных проверок; на книге Т около 20 с на
четырёх процессах `--workers`);
`--show` — напечатать сохранённый запуск и сравнить с другим, ничего не считая. Сравнение по умолчанию — с прошлым
запуском, а без него — с таблицами книги (`data/assumptions/results.json`).

Коды возврата: 0 — путь пройден; 1 — остановка (подбор не сошёлся, коридор, невязка, запись не прошла сверку,
книга не собралась); 2 — негодные входы (нет описания, листа, метки) или ядро ещё не исполняет ветви книги;
3 — путь пройден, но нарушен инвариант ядра.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OK, STOPPED, BAD_INPUT, INVARIANT = 0, 1, 2, 3
SCHEMA = "rederive-v1"
DEFAULT_RUNS = 400              # малая полоса: несколько сотен прогонов — видны медиана, перекос и знаки осей
DEFAULT_WORKERS = 4             # процессов полосы и фаз подбора: тяжёлые прогоны на машине идут по очереди
WORKERS_ENV = "BANK_WORKERS"    # число процессов полосы читает ядро (docs/INTERFACES.md §8)
HEARTBEAT = 30.0                # с: строка «подбор идёт» — лист считает минуты
SHEET_NOT_READY = 2             # код листа: ядро ещё не исполняет ветви книги
EQUAL = 1e-9                    # числа шаблона записаны не точнее девяти знаков: ближе — одно число
DECIMALS = 9
BOOTSTRAP = 200                 # повторных выборок для оценки ошибки медианы малой полосы
MARK = re.compile(r"(?:ВЫВЕДЕНО|ВЫВОДИТСЯ) НА ЯДРЕ(?: \d{2}\.\d{2}\.\d{4})?")
MARK_TEXT = "ВЫВЕДЕНО НА ЯДРЕ {date}"
COMMENT_LINE = re.compile(r"^\s*#")
PLAIN_KEY = re.compile(r"^[A-Za-z_][\w.\-]*$")
YAML_WORDS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}
LATEST = "latest"               # слово ключа --compare: прошлый запуск
RESULTS = "results"             # слово ключа --compare: таблицы книги
LEVEL_LAYER = "macro_neutral"   # слой, чьи условия ближе всего к окну фактов (гейт window_backtest)
# Пороги и коридоры гейтов — начала адресов шаблона, которые команда сверяет с правилом листа, но не пишет; поля окна
# фактов — факты, а не пороги по результату: они пишутся. Описание вывода может назвать свои (`GATES`, `GATE_FACTS`).
GATES = (("checks",),)
GATE_FACTS = (("checks", "window_backtest"),)
GATE_RULES = ()                 # пороги гейтов, которые команда пишет по правилу листа (Р10-16): называет описание вывода
# Правило инструмента для цены справочных вариантов (решения ведущего № 10, Р10-15; № 11, Р11-6 — ПО ДЕЙСТВИЮ, а не по адресу
# подмены): цена варианта — точка книги с его подменами на ВЫВЕДЕННЫХ ЧИСЛАХ ЦЕНТРА (κ и ρ — неподвижные точки на пути кредитных книг
# и базе страхования — заморожены). Вариант, у которого ожидание кредитных книг или базы страхования слоя M (слой «рыночные ставки
# как есть») в ЛЮБОМ квартале до 4-го квартала VARIANT_PATH_UNTIL отходит от центра больше VARIANT_PATH_TOL, этой точкой не
# оценивается — его цена только сухим перевыводом (развилка как центр шаблона, forks_rd): «rd». Инструмент меряет отход сам, для
# каждого варианта (полная сетка варианта, ряды клеток loans и vol_ins); главные развилки устава §6 (описание вывода, MAIN_FORKS) —
# «rd» всегда. Прочие — «frozen» с пометкой «κ, ρ заморожены». Было (Р10-15) — правило по адресу подмены (VARIANT_RD): оно
# пропускало варианты, двигающие путь кредитов через капитал, ставки или баланс (обзор sweep11: 29 из 36 вариантов двигают путь
# больше 0,1 %, адрес узнавал 0).
# ПРАВКА 28.10.2026 (решения ведущего № 12, Р12-7; поток book12): ВСЕ варианты книги — только сухим перевыводом (forks_rd); категория
# «frozen, точка записи» упразднена: правило Р11-6 «по действию» не видело канала перевывода (clients_all «−0,00» против сухого
# −0,17 / −0,15). Замер отхода пути слоя M остаётся печатью (справочно); точка варианта на выведенных числах центра ценой не
# печатается ни у одного варианта.
VARIANT_PATH_TOL = 0.001        # 0,1 % ожидания ряда слоя M
VARIANT_PATH_UNTIL = 2029       # по 4-й квартал года включительно
VARIANT_PATH_LAYER = "macro_neutral"
VARIANT_PATH_SERIES = {"loans": "кредитных книг", "vol_ins": "базы страхования"}
CLASS_TOOL = ROOT / "ops" / "tools" / "class_checks.py"     # проверки классов ошибок в модели (PLAYBOOK §2а)
CLASS_CONFIG = "class_checks.yaml"                         # законные связи и допуски — рядом с книгой
CLASS_VERDICT = {"ok": "зелёно", "fired": "СРАБОТАЛА — находка для перепроверки", "no_rules": "правил нет — не зелёно",
                 "waiting": "ждёт прохода ядра", "error": "НЕ ОТРАБОТАЛА"}
CENTRE_ONLY = ("ПРОБНЫЙ СЧЁТ ЦЕНТРА: концы осей и проверки листа не выводились — точка, уровни, знаки и развилки верны "
               "для нового центра; малая полоса стоит на прежних концах осей: её медиана и полоса — ориентир")


class Stopped(Exception):
    """Остановка пути: в шаблон не пишется ничего — код 1."""


class Refused(Exception):
    """Негодные входы — код 2."""


# ------------------------------------------------------------------ дерево и описание


@dataclass(frozen=True)
class Tree:
    """Где лежат книга, факты, лист и записи запусков: дерево репозитория либо его копия (тесты, проба)."""
    root: Path = ROOT

    @property
    def book_dir(self) -> Path:
        return self.root / "data" / "assumptions"

    @property
    def template(self) -> Path:
        return self.book_dir / "assumptions_template.yaml"

    @property
    def book_yaml(self) -> Path:
        return self.book_dir / "assumptions.yaml"

    @property
    def book_json(self) -> Path:
        return self.book_dir / "assumptions.json"

    @property
    def facts(self) -> Path:
        return self.root / "data" / "facts"

    @property
    def sheet_dir(self) -> Path:
        return self.book_dir / "evidence" / "path"

    @property
    def state(self) -> Path:
        return self.root / "var" / "rederive"


def forget_foreign_siblings(folder: Path) -> None:
    """Модуль книги импортирует лист рядом обычным `import` (описание вывода — `import derive_on_engine`): модуль
    с тем же именем, уже загруженный из ДРУГОГО дерева (копии книги во временном каталоге), забывается — иначе
    описание этого дерева читало бы лист и его записи `out/` чужого дерева."""
    for sibling in folder.glob("*.py"):
        cached = sys.modules.get(sibling.stem)
        where = getattr(cached, "__file__", None) if cached is not None else None
        if where and Path(where).resolve() != sibling.resolve():
            del sys.modules[sibling.stem]


def load_module(path: Path, name: str):
    """Модуль книги по пути (не пакет): лист, описание, сборщик; байткод в дерево книги не пишется."""
    if not path.exists():
        raise Refused(f"нет файла {path.name} ({path.parent})")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    forget_foreign_siblings(path.parent)
    sys.path.insert(0, str(path.parent))
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
        sys.path.remove(str(path.parent))
    return module


def load_spec(tree: Tree):
    """Описание вывода рядом с листом; без обязательных имён — отказ с названным именем."""
    spec = load_module(tree.sheet_dir / "derive_spec.py", "rederive_spec")
    missing = [name for name in ("SHEET", "STEPS", "PHASES", "WRITES", "SAME", "RESIDUALS", "RECORD") if not hasattr(spec, name)]
    if missing:
        raise Refused("в описании вывода нет: " + ", ".join(missing))
    return spec


# ------------------------------------------------------------------ числа и адреса


def ru(x: Any, nd: int = 2) -> str:
    """Число для печати итога: запятая, разрядка пробелом, минус — знаком минуса."""
    if x is None:
        return "—"
    return f"{float(x):,.{nd}f}".replace(",", " ").replace(".", ",").replace("-", "−")


def pc(x: Any, nd: int = 2) -> str:
    return "—" if x is None else ru(100 * float(x), nd) + " %"


def delta(x: Any, nd: int = 2, scale: float = 1.0) -> str:
    if x is None:
        return "—"
    return ("+" if float(x) >= 0 else "−") + ru(abs(float(x)) * scale, nd)


def number_text(v: Any) -> str:
    """Число так, как оно стоит в шаблоне: без экспоненты, не точнее девяти знаков, целое — целым."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Stopped(f"в шаблон пишутся только числа, а не {v!r}")
    if isinstance(v, int):
        return str(v)
    text = f"{v:.{DECIMALS}f}".rstrip("0")
    text = text + "0" if text.endswith(".") else text
    return "0.0" if float(text) == 0 else text


def flow_text(value: Any) -> str:
    """Словарь или список в строку потока YAML: ключ, который YAML прочёл бы не строкой (год, слово-константа), —
    в кавычках."""
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            key = str(k)
            plain = PLAIN_KEY.match(key) and key.lower() not in YAML_WORDS
            parts.append(f"{key if plain else json.dumps(key, ensure_ascii=False)}: {flow_text(v)}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(flow_text(v) for v in value) + "]"
    return number_text(value)


def same(a: Any, b: Any) -> bool:
    """Одно ли это значение в точности записи шаблона."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= EQUAL
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def address_words(address: Sequence[Any]) -> str:
    """Адрес описания словами: `valuation.uncertainty.axes[paths.0=opex.volume_link].low`."""
    out = ""
    for part in address:
        if isinstance(part, Mapping):
            out += "[" + ", ".join(f"{k}={v}" for k, v in part.items()) + "]"
        elif isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out


def at(obj: Any, path: Sequence[Any]) -> Any:
    """Значение по месту в записи листа или в разобранном шаблоне; нет — KeyError с местом."""
    node = obj
    for part in path:
        try:
            node = node[part]
        except (KeyError, IndexError, TypeError):
            raise KeyError(address_words(path)) from None
    return node


def put(obj: Any, path: Sequence[Any], value: Any) -> None:
    node = obj
    for part in path[:-1]:
        node = node.setdefault(part, {}) if isinstance(node, dict) else node[part]
    node[path[-1]] = value


_CONSTRUCT = yaml.constructor.SafeConstructor()


def construct(node: yaml.Node) -> Any:
    """Значение узла YAML так, как его прочтёт книга."""
    return _CONSTRUCT.construct_object(node, deep=True)


def locate(root: yaml.Node, address: Sequence[Any]) -> tuple[yaml.Node, tuple]:
    """Узел шаблона по адресу описания и его место в разобранном шаблоне (отбор списка — номером)."""
    node, path = root, []
    for i, part in enumerate(address):
        here = address_words(address[:i + 1])
        if isinstance(part, Mapping):
            if not isinstance(node, yaml.SequenceNode):
                raise Stopped(f"шаблон, {here}: отбор по полям — только в списке")
            hits = [j for j, item in enumerate(node.value) if all(_field(item, k) == v for k, v in part.items())]
            if len(hits) != 1:
                raise Stopped(f"шаблон, {here}: элементов списка с такими полями {len(hits)} — нужен один")
            node = node.value[hits[0]]
            path.append(hits[0])
        elif isinstance(part, int):
            if not isinstance(node, yaml.SequenceNode) or not 0 <= part < len(node.value):
                raise Stopped(f"шаблон, {here}: нет элемента списка с этим номером")
            node = node.value[part]
            path.append(part)
        else:
            if not isinstance(node, yaml.MappingNode):
                raise Stopped(f"шаблон, {here}: выше ключа — не словарь")
            hits = [(construct(k), v) for k, v in node.value if str(construct(k)) == str(part)]
            if len(hits) != 1:
                raise Stopped(f"шаблон, {here}: ключей {len(hits)} — нужен один")
            path.append(hits[0][0])
            node = hits[0][1]
    return node, tuple(path)


def _field(item: yaml.Node, dotted: str) -> Any:
    """Поле элемента списка по точечному пути (`paths.0`); нет — None."""
    node = item
    for part in str(dotted).split("."):
        if isinstance(node, yaml.MappingNode):
            hits = [v for k, v in node.value if str(construct(k)) == part]
            node = hits[0] if len(hits) == 1 else None
        elif isinstance(node, yaml.SequenceNode) and part.isdigit() and int(part) < len(node.value):
            node = node.value[int(part)]
        else:
            node = None
        if node is None:
            return None
    return construct(node)


# ------------------------------------------------------------------ план записи


@dataclass
class Leaf:
    """Одно число шаблона: было, стало, место в тексте."""
    subkey: str                     # подключ траектории; у числа — пусто
    path: tuple                     # место в разобранном шаблоне
    old: Any
    new: Any
    span: tuple[int, int]           # место старого значения в тексте шаблона
    differs: bool                   # отличается в точности записи
    near: bool                      # отличается, но не больше зоны сходимости описания (число найдено итерацией)
    whole: bool = False             # состав ключей изменился: узел пишется целиком

    @property
    def text(self) -> str:
        return flow_text(self.new)


@dataclass
class Item:
    """Запись описания на шаблоне: её числа. Пишется каждое число, отличное от шаблона, — поодиночке числа не
    пропускаются; `keep` ставит правило сходимости всему запуску сразу (`settled`): повторный вывод сошёлся к
    записанному — не пишется ничего."""
    entry: Mapping[str, Any]
    where: str
    line: int                       # строка ключа в шаблоне (с нуля)
    leaves: list[Leaf] = field(default_factory=list)
    keep: bool = False              # вывод сошёлся к записанному: числа ключа остаются как в шаблоне и в записи дерева
    verify: bool = False            # порог гейта: сверяется с правилом листа, не пишется никогда
    gate_rule: bool = False         # порог гейта, который команда пишет по правилу листа (GATE_RULES, Р10-16)
    old: Any = None                 # значение ключа в шаблоне
    new: Any = None                 # значение ключа по записи листа

    @property
    def differs(self) -> list[Leaf]:
        return [leaf for leaf in self.leaves if leaf.differs]

    @property
    def rewrite(self) -> bool:
        return not self.verify and not self.keep and bool(self.differs)

    @property
    def written(self) -> list[Leaf]:
        return self.differs if self.rewrite else []

    @property
    def jitter(self) -> list[Leaf]:
        """Числа в зоне сходимости, оставленные правилом сходимости как в шаблоне."""
        return self.differs if self.keep and not self.verify else []

    @property
    def gap(self) -> bool:
        """Порог гейта в книге не равен правилу листа."""
        return self.verify and bool(self.differs)


def source_value(record: Mapping[str, Any], source: Any) -> Any:
    """Число записи листа по месту описания (кортеж) либо функцией описания."""
    return source(record) if callable(source) else at(record, source)


def plan_item(root: yaml.Node, entry: Mapping[str, Any], value: Any) -> Item:
    """Сопоставление записи описания с шаблоном: по каждому числу — было, стало, место."""
    node, path = locate(root, entry["address"])
    where = address_words(entry["address"])
    zone = float(entry.get("deadband", 0.0)) * float(entry.get("unit", 0.0))      # зона сходимости: 0 — число не итерации
    item = Item(entry=entry, where=where, line=node.start_mark.line, old=construct(node), new=copy.deepcopy(value))

    def leaf(subkey: str, sub: yaml.Node, sub_path: tuple, new: Any) -> Leaf:
        if not isinstance(sub, yaml.ScalarNode) or isinstance(new, (dict, list, tuple)):
            raise Stopped(f"шаблон, {where}{'.' + subkey if subkey else ''}: ждали число, а не вложенный узел")
        old = construct(sub)
        differs = not same(old, new)
        numeric = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (old, new))
        near = differs and numeric and abs(float(new) - float(old)) <= zone + 1e-12
        return Leaf(subkey, sub_path, old, new, (sub.start_mark.index, sub.end_mark.index), differs, near)

    def whole() -> Leaf:
        return Leaf("*", path, construct(node), copy.deepcopy(value), (node.start_mark.index, node.end_mark.index),
                    True, False, whole=True)

    if isinstance(node, yaml.ScalarNode):
        item.leaves.append(leaf("", node, path, value))
    elif isinstance(node, yaml.MappingNode):
        if not isinstance(value, Mapping):
            raise Stopped(f"шаблон, {where}: в шаблоне траектория, лист дал {value!r}")
        have = {str(construct(k)): (construct(k), v) for k, v in node.value}
        if set(have) != {str(k) for k in value}:
            item.leaves.append(whole())
        else:
            for k, new in value.items():
                key, sub = have[str(k)]
                item.leaves.append(leaf(str(k), sub, path + (key,), new))
    elif isinstance(node, yaml.SequenceNode):
        if not isinstance(value, (list, tuple)):
            raise Stopped(f"шаблон, {where}: в шаблоне список, лист дал {value!r}")
        if len(node.value) != len(value):
            item.leaves.append(whole())
        else:
            for i, (sub, new) in enumerate(zip(node.value, value)):
                item.leaves.append(leaf(str(i), sub, path + (i,), new))
    return item


def verify_only(spec: Any, entry: Mapping[str, Any]) -> bool:
    """Порог или коридор гейта: адрес записи начинается с адреса гейтов (`GATES`) и не лежит ни в полях окна фактов
    (`GATE_FACTS`), ни в порогах, которые описание отдаёт команде (`GATE_RULES`, Р10-16). Такое число команда сверяет с
    правилом листа, но не пишет."""
    address = tuple(entry["address"])

    def under(prefixes: Sequence[Sequence[Any]]) -> bool:
        return any(address[:len(p)] == tuple(p) for p in prefixes)

    return under(getattr(spec, "GATES", GATES)) and not under(getattr(spec, "GATE_FACTS", GATE_FACTS)) \
        and not under(getattr(spec, "GATE_RULES", GATE_RULES))


def gate_rule(spec: Any, entry: Mapping[str, Any]) -> bool:
    """Порог гейта, который команда пишет по правилу листа (`GATE_RULES` описания; решения ведущего № 10, Р10-16)."""
    address = tuple(entry["address"])
    return any(address[:len(p)] == tuple(p) for p in getattr(spec, "GATE_RULES", GATE_RULES))


def corridor_of(entry: Mapping[str, Any], subkey: str, where: str) -> tuple[float | None, float | None, str]:
    """Коридор числа: первая подошедшая маска описания; маски нет — описание неполно."""
    for mask, low, high, why in entry.get("corridor") or ():
        if fnmatch.fnmatchcase(subkey, mask):
            return low, high, why
    raise Stopped(f"описание вывода: у {where}{'.' + subkey if subkey else ''} нет коридора — описание неполно")


def corridor_breaks(item: Item) -> list[str]:
    """Числа записи вне своего коридора — по всем числам ключа, а не только по переписанным."""
    out = []
    for lf in item.leaves:
        values = lf.new.items() if lf.whole and isinstance(lf.new, Mapping) else \
            enumerate(lf.new) if lf.whole else [(lf.subkey, lf.new)]
        for subkey, value in values:
            low, high, why = corridor_of(item.entry, str(subkey), item.where)
            if low is None and high is None:
                continue
            if not (isinstance(value, (int, float)) and float(low) - 1e-12 <= float(value) <= float(high) + 1e-12):
                name = item.where + (f".{subkey}" if str(subkey) else "")
                out.append(f"{name} = {value} вне коридора {low}…{high} (шаг {item.entry['step']}): {why}")
    return out


def mark_edits(text: str, items: Sequence[Item], date: str) -> list[tuple[tuple[int, int], str, Item]]:
    """Правки пометок у переписанных ключей: в комментарии ключа (хвост его строки и строки-продолжения) первая
    пометка получает дату запуска. Ключ описан с пометкой, а её нет — правки нет (команда скажет об этом)."""
    lines = text.splitlines(keepends=True)
    starts = [0]
    for ln in lines:
        starts.append(starts[-1] + len(ln))
    edits = []
    for item in items:
        if not item.entry.get("mark") or not item.rewrite:
            continue
        last = item.line
        while last + 1 < len(lines) and COMMENT_LINE.match(lines[last + 1]):
            last += 1
        block_from = starts[item.line] + max(lines[item.line].find("#"), 0)
        found = MARK.search(text, block_from, starts[last + 1])
        if found and found.group(0) != MARK_TEXT.format(date=date):
            edits.append(((found.start(), found.end()), MARK_TEXT.format(date=date), item))
    return edits


def has_mark(text: str, item: Item) -> bool:
    lines = text.splitlines()
    last = item.line
    while last + 1 < len(lines) and COMMENT_LINE.match(lines[last + 1]):
        last += 1
    return bool(MARK.search("\n".join(lines[item.line:last + 1])))


def _outside(text: str, spans: Sequence[tuple[int, int]]) -> list[str]:
    """Куски текста вне названных мест, по порядку."""
    out, cursor = [], 0
    for start, end in spans:
        out.append(text[cursor:start])
        cursor = end
    return out + [text[cursor:]]


def patch(text: str, items: Sequence[Item], date: str) -> tuple[str, list[str]]:
    """Точечная правка текста шаблона и её сверка повторным разбором. → (новый текст, строки о пометках).

    Меняются только места чисел переписанных ключей и дата их пометки. Сверка: разобранный новый шаблон равен
    разобранному прежнему с намеченными заменами — ни одного другого ключа, ни одного другого значения; текст
    вне заменённых мест (все комментарии) совпадает со старым знак в знак."""
    edits: list[tuple[tuple[int, int], str]] = [(lf.span, lf.text) for item in items for lf in item.written]
    marks = mark_edits(text, items, date)
    edits += [(span, new) for span, new, _ in marks]
    edits.sort()
    for (a, b), (c, d) in zip([e[0] for e in edits], [e[0] for e in edits][1:]):
        if c < b:
            raise Stopped("запись в шаблон: места замен пересекаются — описание называет один ключ дважды")
    out, spans, cursor, pos = [], [], 0, 0
    for (start, end), new in edits:
        out += [text[cursor:start], new]
        pos += start - cursor
        spans.append((pos, pos + len(new)))
        pos += len(new)
        cursor = end
    out.append(text[cursor:])
    new_text = "".join(out)
    # сверка 1: текст вне замен цел — оба текста режутся по своим местам замен
    if _outside(text, [span for span, _ in edits]) != _outside(new_text, spans):
        raise Stopped("запись в шаблон: текст вне заменённых чисел изменился — запись отменена")
    # сверка 2: повторный разбор — изменились ровно намеченные ключи и ровно на намеченные значения
    expected = yaml.safe_load(text)
    for item in items:
        for lf in item.written:
            written = yaml.safe_load(lf.text)
            if not same(written, lf.new):
                raise Stopped(f"запись в шаблон: {item.where} — записанное {lf.text} не равно выведенному {lf.new!r}")
            put(expected, lf.path, written)
    if yaml.safe_load(new_text) != expected:
        raise Stopped("запись в шаблон: повторный разбор дал не те ключи или не те значения — запись отменена")
    notes = [f"{item.where}: пометка «{text[span[0]:span[1]]}» → «{new}»" for span, new, item in marks]
    notes += [f"{item.where}: у ключа нет пометки «ВЫВЕДЕНО НА ЯДРЕ» — добавить руками"
              for item in items if item.entry.get("mark") and item.rewrite and not has_mark(text, item)]
    return new_text, notes


# ------------------------------------------------------------------ подбор: запуск листа


def run_sheet(tree: Tree, spec: Any, book: Path, work: Path, *, serial: bool, workers: int, say: Callable[[str], None],
              centre_only: bool = False) -> tuple[dict, list[dict], str]:
    """Вывод на ядре листом описания на книге `book`. → (запись листа, фазы с временем, печать листа).

    Фазы описания: центр — один процесс; фазы после центра стартуют с его записанных чисел (`--start`) и идут
    одновременно, не больше `workers` процессов. `serial` — один запуск листа со всеми шагами. Запись фаз
    складывается в запись одного запуска; ключи фазы обязаны совпасть с ключами центра. `centre_only` — только
    фазы центра: концы осей и проверки листа не выводятся (пробный счёт решения)."""
    sheet = tree.sheet_dir / spec.SHEET
    if not sheet.exists():
        raise Refused(f"нет листа вывода {spec.SHEET}")
    phases = [{"name": "all", "title": "все шаги одним запуском листа", "steps": tuple(spec.STEPS), "after": None}] \
        if serial else [dict(p) for p in spec.PHASES]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    started = time.monotonic()

    def start(phase: dict) -> None:
        phase["out"], phase["log"] = work / f"derive_{phase['name']}.json", work / f"derive_{phase['name']}.txt"
        cmd = [sys.executable, "-B", str(sheet), "--book", str(book), "--facts", str(tree.facts),
               "--steps", ",".join(phase["steps"]), "--out", str(phase["out"])]
        if phase.get("after"):
            cmd += ["--start", str(work / f"derive_{phase['after']}.json")]
        phase["t0"] = time.monotonic()
        phase["handle"] = open(phase["log"], "w", encoding="utf-8", newline="\n")
        phase["proc"] = subprocess.Popen(cmd, cwd=str(tree.root), env=env, stdout=phase["handle"], stderr=subprocess.STDOUT)
        say(f"  фаза {phase['name']} — {phase['title']}: шаги {', '.join(phase['steps'])}")

    def wait(group: list[dict]) -> None:
        beat = time.monotonic()
        try:
            while any(p["proc"].poll() is None for p in group):
                time.sleep(0.25)
                for p in group:                             # время фазы — до её собственного конца, а не конца группы
                    if p["proc"].poll() is not None:
                        p.setdefault("seconds", time.monotonic() - p["t0"])
                if time.monotonic() - beat >= HEARTBEAT:
                    beat = time.monotonic()
                    say(f"  … подбор идёт: {time.monotonic() - started:.0f} с ("
                        + ", ".join(p["name"] for p in group if p["proc"].poll() is None) + ")")
        except BaseException:
            for p in group:
                if p["proc"].poll() is None:
                    p["proc"].kill()
            raise
        finally:
            for p in group:
                if p["proc"].poll() is not None:
                    p["handle"].close()
        for p in group:
            p.setdefault("seconds", time.monotonic() - p["t0"])
            code = p["proc"].returncode
            text = p["log"].read_text(encoding="utf-8")
            if code != 0:
                tail = "\n".join("    " + ln for ln in text.splitlines()[-12:])
                if code == SHEET_NOT_READY:
                    raise Refused(f"лист вывода, фаза {p['name']}: ядро ещё не исполняет ветви книги\n{tail}")
                raise Stopped(f"лист вывода, фаза {p['name']}: код {code}\n{tail}")
            p["record"] = json.loads(p["out"].read_text(encoding="utf-8"))
            say(f"  фаза {p['name']}: готово за {p['seconds']:.0f} с")

    first = [p for p in phases if not p.get("after")]
    later = [] if centre_only else [p for p in phases if p.get("after")]
    phases = first + later
    for p in first:                                         # центр — по одному, по порядку описания
        start(p)
        wait([p])
    for i in range(0, len(later), max(1, workers)):         # после центра — одновременно, не больше workers
        group = later[i:i + max(1, workers)]
        for p in group:
            start(p)
        wait(group)
    centre = first[0]["record"]
    record = {k: copy.deepcopy(v) for k, v in centre.items() if k != "evaluations"}
    for p in later:
        if "keys" in p["record"] and "keys" in centre and p["record"]["keys"] != centre["keys"]:
            raise Stopped(f"лист вывода, фаза {p['name']}: её ключи не равны ключам центра — фаза пересчитала центр "
                          "иначе; запись не складывается (запуск с --serial покажет, чья запись верна)")
        for path in p.get("take") or ():
            try:
                put(record, path, copy.deepcopy(at(p["record"], path)))
            except KeyError as exc:
                raise Stopped(f"лист вывода, фаза {p['name']}: в записи нет узла {exc}") from None
    counts = [p["record"].get("evaluations") or {} for p in phases]
    record["evaluations"] = {k: sum(int(c.get(k, 0)) for c in counts) for k in ("cells", "grids")}
    printed = "".join(f"— фаза {p['name']}: {p['title']} —\n" + p["log"].read_text(encoding="utf-8") for p in phases) \
        if len(phases) > 1 else phases[0]["log"].read_text(encoding="utf-8")
    info = [{"name": p["name"], "steps": list(p["steps"]), "seconds": round(p["seconds"], 1),
             "evaluations": p["record"].get("evaluations")} for p in phases]
    return record, info, printed


# ------------------------------------------------------------------ подбор: приёмка записи листа


def check_record(spec: Any, record: Mapping[str, Any], template: Mapping[str, Any], root: yaml.Node,
                 steps: Sequence[str], dry_run: bool = False) -> tuple[list[Item], list[str], list[str]]:
    """Запись листа против описания. → (план записи по ключам, нарушения, строки сверок).

    Нарушение останавливает запись: подбор не сошёлся, невязка правила больше допуска, число вне коридора,
    суждение листа разошлось с книгой, соотношение между числами нарушено. Запись шага, которого в запуске не
    было, пропускается. Сверка с полем `book_only` описания (решения ведущего № 12, Р12-8: страж отбора окон строк-долей по
    границе ROE) останавливает только запись книги; в сухом прогоне (развилка как центр копии) она печатается — отбор окон по
    своей границе ROE развилки — часть её действия, его применяет инструмент развилок."""
    bad: list[str] = []
    notes: list[str] = []
    ran = set(steps)
    for res in spec.RESIDUALS:
        if res["step"] not in ran:
            continue
        try:
            if "flag" in res:
                ok = at(record, res["flag"]) is True
                if not ok and dry_run and res.get("book_only"):
                    notes.append(f"НЕТ  {res['name']} — сухой прогон: печать, не остановка (Р12-8; отбор применяет инструмент развилок)")
                    continue
                notes.append(f"{'ок ' if ok else 'НЕТ'}  {res['name']}")
                if not ok:
                    bad.append(f"{res['name']}: не выполнено ({res['why']})")
                continue
            value = float(at(record, res["value"]))
            target = res["target"]
            target = float(target if isinstance(target, (int, float)) else at(record, target))
        except KeyError as exc:
            bad.append(f"{res['name']}: в записи листа нет узла {exc}")
            continue
        ok = abs(value - target) <= float(res["tol"]) + 1e-15
        notes.append(f"{'ок ' if ok else 'НЕТ'}  {res['name']}: {value:.6f} при цели {target:.6f}, допуск {res['tol']:g}")
        if not ok:
            bad.append(f"{res['name']}: {value:.6f} при цели {target:.6f}, допуск {res['tol']:g} ({res['why']})")
    if "convergence" in record:
        rounds = record["convergence"]["rounds"]
        notes.append("сходимость связанных шагов: " + " → ".join(f"{r['max_relative_change']:.1e}" for r in rounds)
                     + f" при пороге {record['convergence']['tol']:g}; кругов {len(rounds)}")
    for entry in spec.SAME:
        if entry["step"] not in ran:
            continue
        try:
            node, _ = locate(root, entry["address"])
            want = source_value(record, entry["source"])
        except KeyError as exc:
            bad.append(f"{address_words(entry['address'])}: в записи листа нет узла {exc}")
            continue
        if not same(construct(node), want):
            bad.append(f"{address_words(entry['address'])}: в книге {construct(node)!r}, у листа {want!r} — "
                       f"{entry['rule']}; суждение записано в двух местах по-разному")
    items: list[Item] = []
    for entry in spec.WRITES:
        if entry["step"] not in ran:
            continue
        try:
            value = source_value(record, entry["source"])
        except KeyError as exc:
            bad.append(f"{address_words(entry['address'])}: в записи листа нет узла {exc}")
            continue
        item = plan_item(root, entry, value)
        item.verify = verify_only(spec, entry)
        item.gate_rule = gate_rule(spec, entry)
        bad += corridor_breaks(item)
        items.append(item)
    relations = getattr(spec, "relations", None)
    if relations is not None:
        bad += list(relations(record, template))
    return items, bad, notes


def plan_companions(tree: Tree, spec: Any, record: Mapping[str, Any], steps: Sequence[str]) -> tuple[list[dict], list[str]]:
    """Файлы-спутники шаблона (описание, `COMPANIONS`): план записи выведенных чисел в YAML рядом с шаблоном.
    → ([{file, path, text, items}], нарушения). Запись шага, которого в запуске не было, пропускается; нет файла,
    нет узла записи листа, число вне коридора — нарушение (запись всего запуска останавливается)."""
    out: list[dict] = []
    bad: list[str] = []
    ran = set(steps)
    for cfg in getattr(spec, "COMPANIONS", ()) or ():
        entries = [e for e in cfg["writes"] if e["step"] in ran]
        if not entries:
            continue
        path = tree.book_dir / cfg["file"]
        if not path.exists():
            bad.append(f"файл-спутник {cfg['file']}: нет файла рядом с шаблоном")
            continue
        text = read_text(path)
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        items: list[Item] = []
        for entry in entries:
            try:
                value = source_value(record, entry["source"])
            except KeyError as exc:
                bad.append(f"файл-спутник {cfg['file']}, {address_words(entry['address'])}: в записи листа нет узла {exc}")
                continue
            item = plan_item(root, entry, value)
            bad += [f"файл-спутник {cfg['file']}: {line}" for line in corridor_breaks(item)]
            items.append(item)
        out.append({"file": cfg["file"], "path": path, "text": text, "items": items})
    return out, bad


def record_gaps(spec: Any, record: Mapping[str, Any], root: yaml.Node, steps: Sequence[str]) -> list[str]:
    """Где шаблон не равен записи вывода — по всем выведенным числам (записи описания шагов `steps`, которые команда
    пишет; пороги гейтов сюда не входят), в точности записи. Пусто — шаблон и запись сходятся."""
    out = []
    for entry in spec.WRITES:
        if entry["step"] not in steps or verify_only(spec, entry):
            continue
        where = address_words(entry["address"])
        try:
            item = plan_item(root, entry, source_value(record, entry["source"]))
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            out.append(f"{where}: в записи вывода нет узла ({exc})")
            continue
        except Stopped as exc:
            out.append(str(exc))
            continue
        out += [f"{where}{'.' + lf.subkey if lf.subkey and not lf.whole else ''}: в шаблоне {flow_text(lf.old)}, в записи "
                f"вывода {lf.text}" for lf in item.differs]
    return out


def same_numbers(spec: Any, a: Mapping[str, Any], b: Mapping[str, Any], steps: Sequence[str], *, gates: bool) -> bool:
    """Равны ли две записи вывода в числах описания: `gates` — в порогах гейтов (сверяются, не пишутся), иначе — в
    числах, которые команда пишет. Узла нет в одной из записей — не равны."""
    for entry in spec.WRITES:
        if entry["step"] not in steps or verify_only(spec, entry) is not gates:
            continue
        try:
            if not same(source_value(a, entry["source"]), source_value(b, entry["source"])):
                return False
        except (KeyError, IndexError, TypeError, AttributeError):
            return False
    return True


def committed_record(tree: Tree, spec: Any) -> dict | None:
    """Запись вывода дерева рядом с листом; нет файла или он не читается — None."""
    path = tree.sheet_dir / spec.RECORD["out"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def settled(spec: Any, items: Sequence[Item], committed: Mapping[str, Any] | None, record: Mapping[str, Any],
            root: yaml.Node, steps: Sequence[str]) -> bool:
    """Правило сходимости повторного вывода: сошёлся ли новый вывод к уже записанному.

    Лист на записанной книге делает ещё один круг связанных шагов, и числа, найденные итерацией, могут сдвинуться
    на единицу последнего знака — в пределах порога сходимости листа. Это дрожание гасится не пропуском отдельных
    чисел (тогда шаблон расходится с записью вывода), а решением обо всём запуске сразу. Вывод сошёлся, когда:
      1) книга уже несёт запись вывода — шаблон равен записи вывода дерева во всех выведенных числах, а пороги
         гейтов по правилу листа в записи дерева те же, что в новой (иначе запись дерева устарела и пишется заново);
      2) каждое отличие нового вывода — не больше зоны сходимости описания (`deadband` единиц последнего знака; у
         числа без зоны — доли, окно фактов — любое отличие настоящее);
      3) сдвинулось хотя бы одно число центра: числа шагов после центра — функция записанного центра, и при том же
         центре любое их отличие — не дрожание, а другая книга или другие факты.
    Тогда не пишется ничего: и шаблон, и запись вывода дерева остаются равными друг другу. Иначе пишется всё."""
    moved = [item for item in items if item.differs and not item.verify]
    if not moved or committed is None or not all(leaf.near for item in moved for leaf in item.differs):
        return False
    centre = {step for phase in spec.PHASES if not phase.get("after") for step in phase["steps"]}
    if not any(item.entry["step"] in centre for item in moved):
        return False
    return not record_gaps(spec, committed, root, steps) and same_numbers(spec, committed, record, steps, gates=True)


def print_plan(items: Sequence[Item], say: Callable[[str], None]) -> dict[str, int]:
    """«Было → стало» по каждому выведенному числу; ключ без изменений — одной строкой."""
    count = {"keys": 0, "numbers": 0, "jitter": 0, "total": 0, "gaps": 0}
    say("ВЫВЕДЕННЫЕ ЧИСЛА: было → стало (шаг · ключ — правило)")
    for item in items:
        if item.verify:
            continue
        count["total"] += len(item.leaves)
        head = f"  {item.entry['step']:<12} {item.where}"
        if not item.rewrite:
            jit = item.jitter
            count["jitter"] += len(jit)
            only = item.leaves[0] if len(item.leaves) == 1 and not item.leaves[0].whole else None
            say(head + ("" if only is None else f": {flow_text(only.old)}") + " — без изменений"
                + ("" if not jit else f"; в зоне сходимости ({item.entry.get('deadband', 0):g} ед. знака "
                                      f"{item.entry.get('unit', 0):g}) — вывод сошёлся к записанному, не переписано: "
                   + ", ".join(f"{lf.subkey or 'число'} {flow_text(lf.old)} → {lf.text}" for lf in jit)))
            continue
        count["keys"] += 1
        say(head + f" — {item.entry['rule']}" + (" [порог гейта по правилу листа — пишет команда, Р10-16]" if item.gate_rule else ""))
        for lf in item.written:
            count["numbers"] += 1
            if lf.whole:
                say(f"      состав ключей изменился — узел пишется целиком:\n        было  {flow_text(lf.old)}\n        стало {lf.text}")
                continue
            change = ""
            if all(isinstance(x, (int, float)) for x in (lf.old, lf.new)):
                d = float(lf.new) - float(lf.old)
                change = f"   ({d:+.{DECIMALS}f}".rstrip("0").rstrip(".") + (f"; {100 * d / abs(lf.old):+.1f} %" if lf.old else "") + ")"
            say(f"      {lf.subkey or 'число':<10} {flow_text(lf.old):>14} → {lf.text:<14}{change}")
        rest = len(item.leaves) - len(item.written)
        if rest:
            say(f"      остальные числа ключа ({rest}) — без изменений")
    gates = [item for item in items if item.verify]
    if gates:
        say("ПОРОГИ ГЕЙТОВ: сверено с правилом листа, НЕ ПИШЕТСЯ (порог не идёт за результатом сам — перенос решает ведущий)")
        for item in gates:
            count["gaps"] += item.gap
            say(f"  {item.entry['step']:<12} {item.where}: " + (
                f"РАСХОДИТСЯ — в книге {flow_text(item.old)}, правило листа даёт {flow_text(item.new)} ({item.entry['rule']})"
                if item.gap else f"{flow_text(item.old)} — равен правилу листа"))
    return count


# ------------------------------------------------------------------ быстрые числа


def quick_numbers(tree: Tree, book_path: Path, *, runs: int, workers: int, variants: bool, today: dt.date,
                  clock: Callable[[str, float], None], say: Callable[[str], None],
                  main_forks: Sequence[str] = ()) -> dict[str, Any]:
    """Точка по сетке, малая полоса и числа приёмочных проверок на книге `book_path` — функциями ядра, теми же, что
    считают таблицы книги и выпуск. Подбор здесь не делается: книга читается как есть."""
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.book_results import reference_variants, variant_book
    from model.checks import check_gates, check_invariants, gate_statuses, load_gate_explanations, sign_numbers
    from model.grid import bank_language, live_from_book, modal_cell, point_probabilities, run_grid
    from model.levels import LEVEL_ROWS, cir_lt_value, funds_cost_to_key, levels, mix_year, stationary_nim

    os.environ[WORKERS_ENV] = str(workers)
    t = time.monotonic()
    facts = load_facts(tree.facts)
    book = load_book(book_path, facts=facts)
    live = live_from_book(book, facts)
    main = str(book.get("meta.company.main_ticker"))
    run = run_grid(book, facts, live)
    lam = run.lam
    clock("сетка: точка и слои", time.monotonic() - t)
    say(f"  точка по сетке: {ru(run.point)} ₽ (низ {ru(run.low)}, верх {ru(run.high)}, λ = {lam:g})")

    t = time.monotonic()
    band = U.band(book, facts, live, draws=runs, workers=workers)
    head = band.headline(lam, live.prices, main)
    centres = band.centres(lam)
    rng = random.Random(band.seed)
    medians = sorted(U.quantile(sorted(rng.choices(centres, k=len(centres))), band.levels()[2]) for _ in range(BOOTSTRAP))
    mean = sum(medians) / len(medians)
    error = (sum((m - mean) ** 2 for m in medians) / (len(medians) - 1)) ** 0.5
    clock(f"малая полоса: прогонов {runs}, процессов {workers}", time.monotonic() - t)
    say(f"  малая полоса: медиана {ru(head['median'])} ₽, полоса 80 % {ru(head['band80'][0])}–{ru(head['band80'][1])} ₽")
    market = float(head["market"])
    headline = {"point": run.point, "low": run.low, "high": run.high, "lambda": lam, "median": head["median"],
                "band80": list(head["band80"]), "band50": list(head["band50"]), "mean": head["mean"], "market": market,
                "p_below_market": head["p_below_market"], "median_to_market": head["median"] / market - 1,
                "point_to_market": run.point / market - 1, "median_error": error, "draws": band.draws, "seed": band.seed,
                "print_step": band.print_step,
                "contributions": [{"name": c["name"], "share": c["share"], "rank_corr": c["rank_corr"]}
                                  for c in band.contributions(lam)[:8]]}

    t = time.monotonic()
    signs = sign_numbers(run)
    findings = check_invariants(run, band) + check_gates(run, band=band, **signs)
    statuses = {s.name: s for s in gate_statuses(findings, load_gate_explanations(tree.book_dir / "gate_explanations.yaml",
                                                                                   today=today), today=today)}
    clock("гейты и инварианты (с числами гейтов знака)", time.monotonic() - t)
    checks = []
    for f in findings:
        st = statuses.get(f.name)
        checks.append({"name": f.name, "kind": f.kind, "fired": bool(f.fired), "mass": f.mass, "message": f.message,
                       "status": None if st is None else st.status,
                       "valid_until": None if st is None or st.valid_until is None else st.valid_until.isoformat()})

    t = time.monotonic()
    tl = run.ctx.timeline
    key = modal_cell(book, run.ctx.posterior)
    probs = {"modal_cell": {c.key: (1.0 if c.key == key else 0.0) for c in run.cells},
             "analytical": dict(run.layers["analytical"].prob), "point": point_probabilities(run),
             LEVEL_LAYER: dict(run.layers[LEVEL_LAYER].prob)}
    node = levels(run)
    level_rows, window, years = {}, None, []
    if node is not None:
        years, window = list(node["years"]), node.get("window")
        for name in LEVEL_ROWS:
            row = node["rows"][name]
            roe = [mix_year(run, probs[name], y)["roe"] for y in years]
            level_rows[name] = {"title": row["title"], "nim": row["nim"], "cor": row["cor"], "cir": row["cir"],
                                "loans_share": row["loans_share"],
                                "roe": None if any(v is None for v in roe) else sum(roe) / len(roe)}
    bank = bank_language(run)
    # Сверка порядка — обе стороны на одном делителе: акции в обращении на дату фактов (как капитализация рынка), а не
    # делитель ядра после пути выкупа (решения ведущего Совкомбанка № 2, А6). V0 / BV ядра — справочно (`fair_pb_v0`).
    n_out = float(run.ctx.prep.af.n_out)
    order = {"fair_pb": run.point * n_out / 1000 / bank["bv_v"], "fair_pb_v0": bank["fair_pb_point"], "market_pb": bank["market_pb"],
             "roe_tc": bank["roe_tc"], "k_tc": bank["k_tc"], "shares": n_out, "divisor": run.divisor, "years": {}}
    for y in (tl.anchor_year, tl.anchor_year + 1):
        row = mix_year(run, probs["point"], y)
        ni = row["flows"]["ni_sh"]
        eps = None if ni is None or not n_out else ni * 1000 / n_out
        order["years"][str(y)] = {"roe": row["roe"], "eps": eps, "pe_point": None if not eps else run.point / eps,
                                  "pe_median": None if not eps else head["median"] / eps,
                                  "pe_market": None if not eps else market / eps}
    layers = {k: {"title": L.title, "price": L.price, "pb": L.pb, "roe_tc": L.roe_tc, "k_tc": L.k_tc}
              for k, L in run.layers.items()}
    cell = run.cell(*key)
    out = {"book_version": str(book.get("meta.version")), "book_date": str(book.get("meta.date")), "book_digest": book.digest,
           "headline": headline, "layers": layers, "checks": checks,
           "levels": {"from_year": None if node is None else node["from_year"], "to_year": None if node is None else node["to_year"],
                      "cell": "/".join(key), "rows": level_rows, "window": window},
           "modal_cell": {"cell": "/".join(key), "roe_t": cell.roe_t, "k_t": cell.k_t, "terminal_share": cell.terminal_share},
           "order": order, "cir_lt": cir_lt_value(run), "nim_stationary": stationary_nim(run.ctx),
           "funds_cost_to_key": funds_cost_to_key(run), "sign_test": signs["volume_sign"], "stress_sign": signs["stress_sign"]}
    clock("уровни, порядок, узлы гейтов уровней", time.monotonic() - t)
    if variants:
        t = time.monotonic()
        out["reference_variants"] = reference_variants(book, facts, live, run)
        specs = {str(v["id"]): v for v in (book.opt("valuation.reference_variants") or [])}
        base_paths = layer_paths(run)
        for r in out["reference_variants"] or []:              # Р11-6: правило инструмента по действию — замер отхода пути слоя M
            vrun = run_grid(variant_book(book, specs[r["id"]]), facts, live)
            r["path_dev"] = path_deviation(base_paths, layer_paths(vrun))
            r["main_fork"] = r["id"] in set(main_forks)
            r["price_rule"] = variant_rule(r["path_dev"], main=r["main_fork"])
        clock("цена правил и развилок: справочные варианты", time.monotonic() - t)
    else:
        out["reference_variants"] = None
    U.close_pool()
    return json.loads(json.dumps(out, ensure_ascii=False, default=_plain))


def _plain(o: Any) -> Any:
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    return str(o)


def marginal_numbers(tree: Tree, spec: Any, book_path: Path, work: Path) -> dict[str, Any] | None:
    """Лист предельной экономики роста на книге `book_path` (в свой каталог листа он не пишет): по мирам —
    доходность предельной единицы роста против стоимости капитала, на якоре — против факта сегмента отчётности."""
    cfg = getattr(spec, "MARGINAL", None)
    if cfg is None:
        return None
    out = work / "marginal_out.json"
    done = subprocess.run([sys.executable, "-B", str(tree.sheet_dir / cfg["sheet"]), "--book", str(book_path),
                           "--facts", str(tree.facts), "--out", str(out)], cwd=str(tree.root), capture_output=True, text=True,
                          encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if done.returncode != 0:
        return {"error": (done.stdout + done.stderr).strip().splitlines()[-1:] or ["лист не отработал"], "title": cfg["title"]}
    record = json.loads(out.read_text(encoding="utf-8"))
    rows = {}
    for world, table in at(record, cfg["table"]).items():
        rows[world] = [{"year": r["year"], "value": r[cfg["value"]], "segment_basis": r.get(cfg["segment_basis"]),
                        "hurdle": r[cfg["hurdle"]],
                        # верхний край нормы (описание, `ceiling`; решения ведущего Совкомбанка № 5, Р5-11): нет — только нижний
                        "ceiling": (r.get(cfg["ceiling"]) if cfg.get("ceiling") else None)} for r in table]
    anchor = dict(at(record, cfg["anchor"]))
    slack = float(cfg.get("anchor_slack", 0.0))
    anchor["ok"] = bool(anchor["model_min"] >= anchor["segment_low"] - slack and anchor["model_max"] <= anchor["segment_high"] + slack)
    words = {k: cfg[k] for k in ("second", "anchor_words", "verdict", "tail") if k in cfg}     # слова книги; нет — слова команды
    out = {"title": cfg["title"], "rows": rows, "anchor": anchor, "words": words}
    # розница корзиной (описание, `retail`; решения ведущего Совкомбанка № 6, Р6-5): норма устава §4 — не ниже 5 %, выше 30 % — признак
    # ошибки калибровки; судится КАЖДЫЙ год листа в каждом мире (флаг круга 5 «розница выше 30 %» стоял в 2027 и 2030 годах)
    if cfg.get("retail"):
        rc = cfg["retail"]
        lo, hi = (float(x) for x in rc["norm"])
        rt = {world: [{"year": r["year"], "value": r[rc.get("value", cfg["value"])]} for r in table]
              for world, table in at(record, rc["table"]).items()}
        out["retail"] = {"title": rc["title"], "norm": [lo, hi], "rows": rt,
                         "outside": [{"world": w, "year": r["year"], "value": r["value"]} for w, t in rt.items() for r in t
                                     if not lo <= r["value"] <= hi]}
    return out


def acceptance_numbers(tree: Tree, spec: Any, book_path: Path, work: Path) -> list[dict[str, Any]]:
    """Листы приёмочных проверок книги (описание, `ACCEPTANCE`): каждый лист считает на книге `book_path` свои строки
    {name, value, low, high, ok, words} и пишет их записью JSON; в каталог листа он не пишет."""
    out = []
    for n, cfg in enumerate(getattr(spec, "ACCEPTANCE", ()) or ()):
        target = work / f"acceptance_{n}.json"
        done = subprocess.run([sys.executable, "-B", str(tree.sheet_dir / cfg["sheet"]), "--book", str(book_path),
                               "--facts", str(tree.facts), "--out", str(target)], cwd=str(tree.root), capture_output=True, text=True,
                              encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if done.returncode != 0:
            out.append({"title": cfg["title"], "sheet": cfg["sheet"], "rows": [],
                        "error": (done.stdout + done.stderr).strip().splitlines()[-1:] or ["лист не отработал"]})
            continue
        record = json.loads(target.read_text(encoding="utf-8"))
        out.append({"title": cfg["title"], "sheet": cfg["sheet"], "rows": list(record.get("rows") or []), "error": None})
    return out


def class_numbers(tree: Tree, book_path: Path, work: Path, workers: int = 1) -> dict[str, Any]:
    """Проверки классов ошибок в модели (PLAYBOOK §2а) на книге `book_path` — отдельным процессом: подмены входов
    клеток живут в его памяти и в процесс команды не попадают; законные связи и допуски — файл рядом с книгой дерева;
    `workers` — его рабочих процессов (запись та же при любом числе).
    → {error, config, checks, flags, model_untouched, seconds}; не отработал — `error` (это красный флаг)."""
    config = tree.book_dir / CLASS_CONFIG
    target = work / "class_checks.json"
    empty = {"config": None, "checks": [], "flags": [], "model_untouched": None, "seconds": None}
    if not config.exists():
        return dict(empty, error=[f"нет файла законных связей и допусков {CLASS_CONFIG} рядом с книгой"])
    done = subprocess.run([sys.executable, "-B", str(CLASS_TOOL), "--book", str(book_path), "--facts", str(tree.facts),
                           "--config", str(config), "--json", str(target), "--quiet", "--workers", str(workers)],
                          cwd=str(tree.root), capture_output=True,
                          text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if done.returncode not in (0, 1) or not target.exists():
        return dict(empty, error=(done.stdout + done.stderr).strip().splitlines()[-1:] or ["инструмент не отработал"])
    record = json.loads(target.read_text(encoding="utf-8"))
    return {"error": None, "config": record["config"], "checks": record["checks"], "flags": record["flags"],
            "model_untouched": record["model_untouched"], "seconds": record["seconds"]["total"]}


def class_verdict(c: Mapping[str, Any]) -> str:
    """Вердикт строки класса в листе решения: пустая проверка («правил нет», «не проверялось») — её слова и «не
    зелёно»."""
    if c["status"] == "no_rules":
        return f"{c['status_words']} — не зелёно"
    return CLASS_VERDICT.get(c["status"], c["status_words"])


def class_flags(now: Mapping[str, Any]) -> list[str]:
    """Красные флаги блока проверок классов: каждое срабатывание; блок, который не отработал, — тоже флаг."""
    cl = now.get("classes")
    if not cl:
        return []
    if cl.get("error"):
        return ["проверки классов ошибок не отработали: " + " ".join(cl["error"])]
    return list(cl.get("flags") or [])


def results_as_run(tree: Tree) -> dict[str, Any] | None:
    """Таблицы книги (`results.json`, полная полоса) в виде записи запуска — мерка первого запуска."""
    path = tree.book_dir / "results.json"
    if not path.exists():
        return None
    r = json.loads(path.read_text(encoding="utf-8"))
    h = r["headline"]
    market = float(h["market"])
    lv = r.get("levels") or {}
    quick = {"book_version": r.get("book_version"), "book_digest": r.get("reference_variants_book"),
             "headline": {"point": h["point"], "low": h["low"], "high": h["high"], "median": h["median"], "band80": h["band80"],
                          "mean": h["mean"], "market": market, "p_below_market": h["p_below_market"],
                          "median_to_market": h["median"] / market - 1, "point_to_market": h["point"] / market - 1,
                          "draws": h["draws"], "seed": h["seed"], "median_error": None},
             "layers": {k: {"title": v["title"], "price": v["price"], "pb": v["pb"], "roe_tc": v["roe_tc"], "k_tc": v["k_tc"]}
                        for k, v in r["layers"].items()},
             "checks": [dict(c, status=None, valid_until=None) for c in r["checks"]],
             "levels": {"from_year": lv.get("from_year"), "to_year": lv.get("to_year"), "cell": lv.get("cell"),
                        "rows": {k: {"title": v["title"], "nim": v["nim"], "cor": v["cor"], "cir": v["cir"],
                                     "loans_share": v["loans_share"], "roe": None} for k, v in (lv.get("rows") or {}).items()},
                        "window": lv.get("window")},
             "order": None, "sign_test": r.get("sign_test"), "stress_sign": r.get("stress_sign"),
             "reference_variants": r.get("reference_variants"), "funds_cost_to_key": r.get("funds_cost_to_key")}
    return {"schema": SCHEMA, "label": "таблицы книги (results.json)", "quick": quick, "marginal": None,
            "mode": {"runs": h["draws"]}, "derive": None}


# ------------------------------------------------------------------ приёмочные проверки и итог


def layer_paths(run: Any, *, until_year: int = VARIANT_PATH_UNTIL, layer: str = VARIANT_PATH_LAYER) -> dict[str, list | None]:
    """Ожидание рядов VARIANT_PATH_SERIES слоя `layer` по кварталам 1 … 4-й квартал `until_year` (вероятности слоя — своего прогона)."""
    from model.levels import expect
    prob = dict(run.layers[layer].prob)
    last = run.ctx.timeline.quarters_of_year(until_year)[-1]
    have = run.cells[0].quarters
    return {name: ([expect(run, prob, name, q) for q in range(1, last + 1)] if name in have else None) for name in VARIANT_PATH_SERIES}


def path_deviation(base: Mapping[str, Any], other: Mapping[str, Any]) -> dict[str, Any]:
    """Наибольший по кварталам модуль относительного отхода ожидания каждого ряда варианта от центра и квартал, где он достигнут
    (номер квартала прогноза, 1 — первый). Ряда нет в книге — None (не судится)."""
    out: dict[str, Any] = {}
    for name in VARIANT_PATH_SERIES:
        a, b = base.get(name), other.get(name)
        if a is None or b is None:
            out[name] = None
            continue
        devs = [abs(y / x - 1.0) if x else (0.0 if not y else math.inf) for x, y in zip(a, b) if x is not None and y is not None]
        k = max(range(len(devs)), key=devs.__getitem__) if devs else None
        out[name] = None if k is None else {"max": devs[k], "q": k + 1}
    return out


def variant_rule(dev: Mapping[str, Any], *, main: bool = False, tol: float = VARIANT_PATH_TOL) -> str:
    """Р12-7 (решения ведущего № 12): ВСЕ варианты книги — «rd», цена только сухим перевыводом (forks_rd); категории «frozen» (точка
    на выведенных числах центра) больше нет — какой бы ни был замер отхода пути слоя M и главная ли это развилка. Было (Р11-6) —
    «rd» при отходе больше `tol` или у главной развилки, иначе «frozen». Аргументы оставлены: замер печатается справочно."""
    return "rd"


def variant_mark(r: Mapping[str, Any]) -> str:
    """Пометка строки варианта: правило цены и замер отхода."""
    rule = r.get("price_rule")
    if rule is None:
        return ""
    dev = r.get("path_dev") or {}
    measured = "; ".join(f"{VARIANT_PATH_SERIES[k]} {100 * v['max']:.2f} % (кв. {v['q']})" for k, v in dev.items() if v)
    if rule == "rd":
        why = "главная развилка устава §6" if r.get("main_fork") else "все варианты книги — Р12-7"
        return f"НЕ ЦЕНА ({why}; отход слоя M до {VARIANT_PATH_UNTIL}К4: {measured or '—'}) — цена только сухим перевыводом, forks_rd"
    return f"κ, ρ заморожены (отход слоя M: {measured or '—'})"


VARIANT_WORDS = {"frozen": "κ, ρ заморожены (категория упразднена Р12-7)",
                 "rd": "НЕ ЦЕНА — цена только сухим перевыводом (forks_rd; все варианты книги — Р12-7)"}


def by_price(rows: Any) -> list:
    """Строки вариантов в порядке таблиц книги и выпуска: по модулю цены, строки без цены (варианта нет в записи
    сухого перевывода — `d_point` пуст, М§14.5) — последними."""
    from model.book_results import by_price as order
    return order(rows)


def unpriced(r: Mapping[str, Any]) -> str:
    """Слова строки без цены — её причина из таблиц книги («без цены: …»)."""
    return " ".join(str(r.get("why") or "без цены").split())


def flags_of(now: Mapping[str, Any]) -> list[str]:
    """Красные флаги запуска: то, что ведущий обязан увидеть первым, — КАЖДОЕ отклонение блока приёмочных проверок
    (те же условия, что печатает `print_acceptance`: `outside`, `off_target`, `pays`) и порог гейта, не равный
    правилу листа. Порядок — как в блоке; нарушенный инвариант — первым."""
    out = [gate_gap_words(row) for row in (now.get("derive") or {}).get("unwritten") or []]
    q = now.get("quick")
    if q is None:
        return out + class_flags(now)
    for c in q["checks"]:
        if c["kind"] == "invariant" and c["fired"]:
            out.append(f"НАРУШЕН инвариант {c['name']}: {c['message']}")
    rows, window = q["levels"]["rows"], q["levels"]["window"] or {}
    span = lambda k, nd: f"{pc(window[k]['min'], nd)}–{pc(window[k]['max'], nd)}"  # noqa: E731
    if rows:
        row = rows[LEVEL_LAYER]                             # (а) уровень слоя условий окна: маржа, стоимость риска, расходы
        for k, title, nd in LEVEL_METRICS:
            if outside(row[k], window.get(k)):
                out.append(f"уровень в условиях окна фактов ВНЕ окна: {title} слоя «{row['title']}» {pc(row[k], nd)} при окне "
                           f"{span(k, nd)}" + (" (маржу гейт window_backtest не сверяет — отклонение видно только здесь)"
                                               if k == "nim" else ""))
        for name, r in rows.items():                        # (б) модальная клетка, ожидание слоёв, смесь заголовка
            for k, title, nd in LEVEL_METRICS[1:]:
                if name != LEVEL_LAYER and outside(r[k], window.get(k)):
                    out.append(f"{r['title']} ВНЕ окна фактов: {title} {pc(r[k], nd)} при окне {span(k, nd)}")
    cir = q.get("cir_lt")
    if cir and off_target(cir):
        out.append(f"цель расходов к доходам (гейт cir_lt, {cir['subject']}) ВНЕ допуска: {pc(cir['value'])} при цели "
                   f"{pc(cir['target'], 1)} ± {ru(100 * cir['tolerance'], 1)} п.п.")
    growth = now.get("marginal") or {}                      # (в) миры, где предельный кредит не окупает капитал
    verdict, tail = marginal_words(growth)
    for world, table in (growth.get("rows") or {}).items():
        if not pays(table):
            out.append(f"предельная экономика роста, мир {world}: {tail} {verdict[1]} — {pc(table[-1]['value'], 1)} при "
                       f"стоимости капитала {pc(table[-1]['hurdle'], 1)} ({table[-1]['year']})")
        elif above_norm(table):
            out.append(f"предельная экономика роста, мир {world}: {tail} {norm_word(table, verdict)} — {pc(table[-1]['value'], 1)} "
                       f"при верхнем крае нормы {pc(table[-1]['ceiling'], 1)} ({table[-1]['year']})")
    status = {c["name"]: c for c in q["checks"]}

    def explained(name: str) -> str:
        c = status.get(name) or {}
        until = "" if not c.get("valid_until") else f" до {c['valid_until']}"
        return "" if not c.get("status") else f"; {STATUS_WORDS.get(c['status'], c['status'])}{until}"

    st, ss = q.get("sign_test"), q.get("stress_sign")       # (г) знаки
    if st and not st["ok"]:
        out.append(f"гейт знака volume_sign НЕ выполнен: снятие остановки кредита и поправок роста меняет точку на "
                   f"{delta(st['d_point'])} ₽" + explained("volume_sign"))
    if ss and not ss["ok"]:
        out.append(f"гейт знака stress_sign НЕ выполнен: наибольшее превышение {ru(ss['max_excess'], 1)} млрд ₽"
                   + explained("stress_sign"))
    for c in q["checks"]:
        if c["kind"] == "gate" and c["fired"] and c["status"] not in ("explained", None):
            out.append(f"гейт {c['name']} сработал без действующего объяснения ({STATUS_WORDS.get(c['status'], c['status'])})")
    m = now.get("marginal")
    if m and not m.get("error") and (m.get("retail") or {}).get("outside"):
        r = m["retail"]
        out.append(f"предельная экономика роста: {r['title']} ВНЕ нормы устава §4 ({pc(r['norm'][0], 0)}…{pc(r['norm'][1], 0)} — признак "
                   "ошибки калибровки): " + "; ".join(f"мир {x['world']} {x['year']} — {pc(x['value'], 1)}" for x in r["outside"]))
    if m and m.get("error"):
        out.append("лист предельной экономики роста не отработал: " + " ".join(m["error"]))
    elif m and not m["anchor"]["ok"]:
        a = m["anchor"]
        w = (m.get("words") or {}).get("anchor_words")
        out.append(f"предельная экономика роста: {w[0]} {pc(a['model_min'], 1)}–{pc(a['model_max'], 1)} {w[1]} — {w[3]}" if w else
                   f"предельная экономика роста на якоре расходится с фактом сегмента: модель {pc(a['model_min'], 1)}–"
                   f"{pc(a['model_max'], 1)} при {pc(a['segment_low'], 1)}–{pc(a['segment_high'], 1)} у сегмента")
    for block in now.get("acceptance") or []:
        if block.get("error"):
            out.append(f"лист приёмочных проверок {block['sheet']} не отработал: " + " ".join(block["error"]))
        for row in block["rows"]:
            if not row.get("ok", True):
                out.append(f"проверка книги не пройдена — {row['name']}: {row.get('words', '')}")
    # Р11-6: вариант «rd» остаётся в книге, но его точка — не цена: печать числа — только из сухого перевывода (forks_rd); сам по себе
    # он не флаг (было Р10-15 — «снять из книги»). Флаг — только если замера отхода у варианта нет (правило не применено).
    for r in q.get("reference_variants") or []:
        if r.get("price_rule") is None:
            out.append(f"справочный вариант {r['id']}: нет замера отхода пути слоя M — правило цены варианта (Р11-6) не применено")
    return out + class_flags(now)


def print_flags(flags: Sequence[str], say: Callable[[str], None]) -> None:
    """Первая строка итога: красные флаги числом и перечнем."""
    say("КРАСНЫЕ ФЛАГИ: нет" if not flags else f"КРАСНЫЕ ФЛАГИ — {len(flags)}:")
    for line in flags:
        say("  • " + line)


def flags_cell(flags: Sequence[str]) -> str:
    """Красные флаги одной клеткой таблицы листа решения: числом и перечнем."""
    if not flags:
        return "красных флагов нет"
    return f"красных флагов — {len(flags)}: " + "; ".join(" ".join(str(line).replace("|", "¦").split()) for line in flags)


def gate_gap_words(row: Mapping[str, Any]) -> str:
    """Порог гейта в книге не равен правилу листа — строкой для флагов и листа решения."""
    return (f"порог гейта {row['key']}: в книге {flow_text(row['book'])}, правило листа даёт {flow_text(row['sheet'])} — не "
            "переписан: пороги гейтов команда сверяет, но не пишет")


STATUS_WORDS = {"explained": "объяснение действует", "unexplained": "объяснения нет", "expired": "срок объяснения истёк",
                "mass_off": "масса вне коридора объяснения", "quiet": "тих", None: "—"}


LEVEL_METRICS = (("nim", "ЧПМ", 2), ("cor", "CoR", 2), ("cir", "C/I", 1))     # поле уровня, имя в печати, знаков


def inside(x: Any, w: Mapping[str, Any] | None) -> str:
    if x is None or not w or w.get("min") is None:
        return ""
    return "в окне" if w["min"] <= x <= w["max"] else "ВНЕ окна"


def outside(x: Any, w: Mapping[str, Any] | None) -> bool:
    """Число вне окна фактов (окна или числа нет — не отклонение)."""
    return inside(x, w) == "ВНЕ окна"


def off_target(cir: Mapping[str, Any]) -> bool:
    """Гейт цели расходов к доходам вне своего допуска."""
    return abs(cir["value"] - cir["target"]) > cir["tolerance"]


def pays(table: Sequence[Mapping[str, Any]]) -> bool:
    """Предельный кредит к концу сетки окупает стоимость капитала (то же условие печатает блок (в))."""
    return table[-1]["value"] > table[-1]["hurdle"]


def above_norm(table: Sequence[Mapping[str, Any]]) -> bool:
    """Предельная единица к концу сетки ВЫШЕ верхнего края нормы (у описания с `ceiling`; решения ведущего Совкомбанка № 5,
    Р5-11: норма устава §4 — k мира ± 5 п.п., выход за верх — тот же признак ошибки калибровки, что и за низ)."""
    ceiling = table[-1].get("ceiling")
    return ceiling is not None and table[-1]["value"] > ceiling


def norm_word(table: Sequence[Mapping[str, Any]], verdict: Sequence[str]) -> str:
    """Слово вердикта нормы: в норме / ниже нижнего края / выше верхнего края (третье слово книги, нет — слово команды)."""
    if not pays(table):
        return verdict[1]
    if above_norm(table):
        return verdict[2] if len(verdict) > 2 else "ВЫШЕ нормы"
    return verdict[0]


def in_norm(table: Sequence[Mapping[str, Any]]) -> bool:
    """Внутри нормы с обеих сторон (без верхнего края — только окупаемость)."""
    return pays(table) and not above_norm(table)


def marginal_words(m: Mapping[str, Any] | None) -> tuple[Sequence[str], str]:
    """Слова вердикта и места сравнения листа предельной экономики: слова книги (узел `words` записи листа), а нет —
    слова команды."""
    words = (m or {}).get("words") or {}
    return words.get("verdict", ("окупает", "НЕ окупает")), words.get("tail", "в конце сетки")


def print_acceptance(now: Mapping[str, Any], say: Callable[[str], None]) -> None:
    """Блок приёмочных проверок чисел (а)–(ж)."""
    q, m = now["quick"], now.get("marginal")
    lv = q["levels"]
    rows, window = lv["rows"], lv["window"] or {}
    say("")
    say("ПРИЁМОЧНЫЕ ПРОВЕРКИ ЧИСЕЛ")
    if rows:
        span = lambda k, nd: "—" if not window.get(k) or window[k].get("min") is None else \
            f"{pc(window[k]['min'], nd)} … {pc(window[k]['max'], nd)} (среднее {pc(window[k].get('mean'), nd)})"  # noqa: E731
        row = rows[LEVEL_LAYER]
        gate = next((c for c in q["checks"] if c["name"] == "window_backtest"), None)
        say(f"(а) уровни в условиях окна фактов — слой «{row['title']}», средние {lv['from_year']}–{lv['to_year']} годов, упр. базис:")
        for k, title, nd in LEVEL_METRICS:
            say(f"      {title:<4} {pc(row[k], nd):>9}   окно {span(k, nd)}   {inside(row[k], window.get(k))}"
                + ("   (маржу гейт не сверяет: её сдвигает состав баланса клеток)" if k == "nim" else ""))
        say("      гейт window_backtest: " + ("ключа гейта в книге нет" if gate is None else "сработал" if gate["fired"] else "тих"))
        say(f"(б) модальная клетка {lv['cell']} / ожидание слоёв / смесь заголовка рядом с окном фактов:")
        say(f"      {'':<28}{'ЧПМ':>9}{'CoR':>9}{'C/I':>9}{'ROE':>9}{'кредиты в проц. активах':>26}")
        for name, r in rows.items():
            say(f"      {r['title']:<28}{pc(r['nim']):>9}{pc(r['cor']):>9}{pc(r['cir'], 1):>9}{pc(r['roe'], 1):>9}{pc(r['loans_share'], 1):>26}")
        say(f"      {'окно фактов: низ':<28}{pc((window.get('nim') or {}).get('min')):>9}{pc((window.get('cor') or {}).get('min')):>9}"
            f"{pc((window.get('cir') or {}).get('min'), 1):>9}{'—':>9}{pc((window.get('loans_share') or {}).get('window'), 1):>26}")
        say(f"      {'окно фактов: верх':<28}{pc((window.get('nim') or {}).get('max')):>9}{pc((window.get('cor') or {}).get('max')):>9}"
            f"{pc((window.get('cir') or {}).get('max'), 1):>9}{'—':>9}{pc((window.get('loans_share') or {}).get('anchor'), 1) + ' (якорь)':>26}")
        marks = [f"{rows[n]['title']}: {t} {inside(rows[n][k], window.get(k))}" for n in rows for k, t, _ in LEVEL_METRICS[1:]
                 if outside(rows[n][k], window.get(k))]
        say("      " + ("стоимость риска и расходы к доходам всех строк — внутри окна фактов" if not marks else "; ".join(marks)))
    else:
        say("(а), (б) узла уровней нет: в книге нет ключа окна фактов")
    cir = q.get("cir_lt")
    if cir:
        say(f"      цель расходов к доходам (гейт cir_lt, {cir['subject']}): {pc(cir['value'])} при цели {pc(cir['target'], 1)} ± "
            f"{ru(100 * cir['tolerance'], 1)} п.п. — " + ("ВНЕ допуска" if off_target(cir) else "в допуске"))
    if m is None:
        say("(в) предельная экономика роста: листа в описании нет")
    elif m.get("error"):
        say("(в) предельная экономика роста: лист не отработал — " + " ".join(m["error"]))
    else:
        a = m["anchor"]
        w = m.get("words") or {}
        aw = w.get("anchor_words") or ("якорь: модель", "при факте сегмента отчётности", "сопоставимо", "РАСХОДИТСЯ")
        second, verdict, tail = w.get("second", "базис сегмента"), w.get("verdict", ("окупает", "НЕ окупает")), w.get("tail", "в конце сетки")
        say(f"(в) предельная экономика роста — {m['title']}:")
        say(f"      {aw[0]} {pc(a['model_min'], 1)}–{pc(a['model_max'], 1)} {aw[1]} "
            f"{pc(a['segment_low'], 1)}–{pc(a['segment_high'], 1)} — " + (aw[2] if a["ok"] else aw[3]))
        for world, table in m["rows"].items():
            say(f"      мир {world}: " + "; ".join(
                f"{r['year']} — {pc(r['value'], 1)}" + ("" if r["segment_basis"] is None else f" ({second} {pc(r['segment_basis'], 1)})")
                for r in table) + f"; стоимость капитала {pc(table[-1]['hurdle'], 1)}"
                + ("" if table[-1].get("ceiling") is None else f", верхний край нормы {pc(table[-1]['ceiling'], 1)}")
                + f" — {tail} " + norm_word(table, verdict))
        r = m.get("retail")
        if r:
            say(f"      {r['title']} (норма {pc(r['norm'][0], 0)}…{pc(r['norm'][1], 0)}, каждый год листа): " + "; ".join(
                f"мир {world} " + ", ".join(f"{x['year']} {pc(x['value'], 1)}" for x in t) for world, t in r["rows"].items())
                + (" — в норме" if not r["outside"] else " — ВНЕ нормы: " + ", ".join(f"{x['world']} {x['year']}" for x in r["outside"])))
    say("(г) знаки:")
    st = q.get("sign_test")
    if st:
        say(f"      volume_sign: снятие остановки кредита и поправок роста меняет точку на {delta(st['d_point'])} ₽; миры "
            + ", ".join(f"{w} {delta(v)}" for w, v in st["d_world"].items()) + " — " + ("выполнен" if st["ok"] else "НЕ выполнен"))
    ss = q.get("stress_sign")
    if ss:
        say(f"      stress_sign: убыток больше на {ru(ss['loss']['step'], 0)} млрд ₽ — стоимость растёт в {len(ss['loss']['cells'])} клетках; "
            f"прибыль растёт с требованием в {len(ss['requirement']['cells'])} парах сценариев; наибольшее превышение "
            f"{ru(ss['max_excess'], 1)} млрд ₽ — " + ("выполнен" if ss["ok"] else "НЕ выполнен"))
    if not st and not ss:
        say("      гейтов знака в книге нет")
    order = q.get("order")
    if order:
        say("(д) порядок заголовка:")
        say(f"      справедливый P/B точки {ru(order['fair_pb'])} при рыночном {ru(order['market_pb'])} — оба на акциях в обращении"
            + ("" if order.get("shares") is None else f" ({ru(order['shares'], 1)} млн; V0 / BV ядра на делителе после выкупа — "
                                                       f"{ru(order.get('fair_pb_v0'))})") + "; ROE после фазы роста "
            f"{pc(order['roe_tc'], 1)} при стоимости капитала {pc(order['k_tc'], 1)}")
        for y, r in order["years"].items():
            say(f"      {y}: ROE смеси заголовка {pc(r['roe'], 1)}; P/E точки {ru(r['pe_point'], 1)}, медианы {ru(r['pe_median'], 1)}, "
                f"рынка {ru(r['pe_market'], 1)} (прибыль на акцию {ru(r['eps'])} ₽)")
    variants = q.get("reference_variants")
    if variants:
        say("(е) цена правил и развилок — справочные варианты (точка, ₽ на акцию; к точке книги):")
        for r in by_price(variants):
            shown = "      —  " if r.get("price_rule") == "rd" or r.get("d_point") is None else f"{delta(r['d_point']):>9}"
            say(f"      {shown}   {r['title']}" + (f"  [{variant_mark(r)}]" if r.get("price_rule") else "")
                + (f" — {unpriced(r)}" if r.get("d_point") is None else ""))
        rd = [r for r in variants if r.get("price_rule") == "rd"]
        if rd:
            say(f"      вариантов «rd» (Р12-7: все варианты книги) — {len(rd)} из {len(variants)}: их точка на замороженных κ, ρ не "
                "печатается как цена; цена — таблица forks_rd (сухой перевывод)")
    else:
        say("(е) цена правил и развилок: не считалась (ключ --no-variants) или вариантов в книге нет")
    fired = [c for c in q["checks"] if c["kind"] == "gate" and c["fired"]]
    gates = [c for c in q["checks"] if c["kind"] == "gate"]
    broken = [c for c in q["checks"] if c["kind"] == "invariant" and c["fired"]]
    say(f"(ж) гейты: сработало {len(fired)} из {len(gates)}; инварианты: нарушено {len(broken)} из "
        f"{sum(1 for c in q['checks'] if c['kind'] == 'invariant')}")
    for c in fired:
        until = "" if not c.get("valid_until") else f", до {c['valid_until']}"
        say(f"      {c['name']:<20} масса {ru(c['mass'], 3) if c['mass'] is not None else '—':>6}   "
            f"{STATUS_WORDS.get(c['status'], c['status'])}{until}")
        say(f"          {c['message'][:300]}")
    for c in broken:
        say(f"      НАРУШЕН {c['name']}: {c['message'][:300]}")
    for block in now.get("acceptance") or []:
        say(f"(з) проверки книги — {block['title']}:")
        if block.get("error"):
            say("      лист не отработал — " + " ".join(block["error"]))
        for row in block["rows"]:
            say(f"      {'ок ' if row.get('ok', True) else 'НЕТ'}  {row['name']}: {row.get('words', '')}")


def print_classes(now: Mapping[str, Any], say: Callable[[str], None]) -> None:
    """Блок проверок классов ошибок в модели (PLAYBOOK §2а): класс, вердикт, первые находки и замечания."""
    cl = now.get("classes")
    if cl is None:
        return
    say("")
    say("ПРОВЕРКИ КЛАССОВ ОШИБОК В МОДЕЛИ (PLAYBOOK §2а)"
        + (f" · файл связей: {cl['config'].get('status') or '—'}" if cl.get("config") else ""))
    if cl.get("error"):
        say("  НЕ ОТРАБОТАЛИ: " + " ".join(cl["error"]))
        return
    for c in cl["checks"]:
        say(f"  класс {c['cls']} — {c['title']}: {c['status_words']}" + (f" ({c['tally']})" if c.get("tally") else "")
            + (f" — находок {c['count']}" if c["count"] else "") + f" [{c['seconds']:.1f} с]")
        for line in c["findings"][:3]:
            say("      • " + line)
        if c["count"] > 3:
            say(f"      … ещё {c['count'] - 3} (запись запуска, блок classes)")
        for line in c["notes"]:
            say("      ~ " + line)
    if cl.get("model_untouched") is False:
        say("  ИНСТРУМЕНТ ИЗМЕНИЛ МОДЕЛЬ: сетка книги после проверок не равна сетке до них")


def compare_rows(now: Mapping[str, Any], was: Mapping[str, Any] | None) -> list[tuple[str, Any, Any, str]]:
    """Строки «было → стало» по заголовку и проверкам: (что, было, стало, вид печати)."""
    q = now["quick"]
    w = (was or {}).get("quick") or {}
    rows: list[tuple[str, Any, Any, str]] = []
    get = lambda d, *path: _get(d, path)  # noqa: E731
    for title, path, kind in (("точка, ₽", ("headline", "point"), "rub"), ("медиана, ₽", ("headline", "median"), "rub"),
                              ("полоса 80 %: низ, ₽", ("headline", "band80", 0), "rub"),
                              ("полоса 80 %: верх, ₽", ("headline", "band80", 1), "rub"),
                              ("среднее прогонов, ₽", ("headline", "mean"), "rub"),
                              ("медиана к цене рынка", ("headline", "median_to_market"), "pct"),
                              ("точка к цене рынка", ("headline", "point_to_market"), "pct"),
                              ("доля прогонов ниже рынка", ("headline", "p_below_market"), "pct"),
                              ("слой «свой взгляд»: цена, ₽", ("layers", "analytical", "price"), "rub"),
                              (f"слой условий окна ({LEVEL_LAYER}): цена, ₽", ("layers", LEVEL_LAYER, "price"), "rub")):
        rows.append((title, get(w, *path), get(q, *path), kind))
    for name, row in (q["levels"]["rows"] or {}).items():
        for k, t in (("nim", "ЧПМ"), ("cor", "CoR"), ("cir", "C/I"), ("roe", "ROE")):
            rows.append((f"уровни · {row['title']}: {t}", get(w, "levels", "rows", name, k), row[k], "pct"))
    if q.get("cir_lt"):
        rows.append(("гейт цели расходов к доходам: число", get(w, "cir_lt", "value"), q["cir_lt"]["value"], "pct"))
    if q.get("sign_test"):
        rows.append(("знак объёмных эффектов: сдвиг точки, ₽", get(w, "sign_test", "d_point"), q["sign_test"]["d_point"], "rub"))
    if q.get("stress_sign"):
        rows.append(("знак стресса: наибольшее превышение, млрд ₽", get(w, "stress_sign", "max_excess"), q["stress_sign"]["max_excess"], "rub"))
    if q.get("order"):
        rows.append(("справедливый P/B точки", get(w, "order", "fair_pb"), q["order"]["fair_pb"], "rub"))
        for y, r in q["order"]["years"].items():
            rows.append((f"P/E точки на прибыль {y} года", get(w, "order", "years", y, "pe_point"), r["pe_point"], "rub"))
    m, wm = now.get("marginal") or {}, (was or {}).get("marginal") or {}
    for world, table in (m.get("rows") or {}).items():
        old = (wm.get("rows") or {}).get(world)
        rows.append((f"предельный кредит, мир {world}, {table[-1]['year']} год", None if not old else old[-1]["value"], table[-1]["value"], "pct"))
    old_variants = {r["id"]: r for r in (w.get("reference_variants") or [])}
    for r in q.get("reference_variants") or []:
        rows.append((f"развилка · {r['title'][:60]}", (old_variants.get(r["id"]) or {}).get("d_point"), r["d_point"], "rub"))
    return rows


def _get(d: Any, path: Sequence[Any]) -> Any:
    for part in path:
        if isinstance(d, Mapping) and part in d:
            d = d[part]
        elif isinstance(d, list) and isinstance(part, int) and part < len(d):
            d = d[part]
        else:
            return None
    return d


def print_compare(now: Mapping[str, Any], was: Mapping[str, Any] | None, say: Callable[[str], None]) -> None:
    q = now["quick"]
    h = q["headline"]
    say("")
    say(f"ЗАГОЛОВОК — ПРЕДВАРИТЕЛЬНО, {h['draws']} прогонов (зерно {h['seed']}; ошибка медианы от числа прогонов — около "
        f"±{ru(h.get('median_error'), 1)} ₽, оценка сверху без учёта расслоения выборки)")
    say(f"  точка {ru(h['point'])} ₽; медиана {ru(h['median'])} ₽; полоса 80 % {ru(h['band80'][0])}–{ru(h['band80'][1])} ₽; "
        f"среднее {ru(h['mean'])} ₽")
    say(f"  к цене рынка {ru(h['market'])} ₽: медиана {delta(h['median_to_market'], 1, 100)} %, точка {delta(h['point_to_market'], 1, 100)} %; "
        f"доля прогонов ниже рынка {pc(h['p_below_market'], 1)}")
    say("  вклады осей в полосу: " + "; ".join(f"{c['name'][:38]} {ru(c['share'], 2)}" for c in h.get("contributions", [])[:5]))
    say("")
    if was is None:
        say("БЫЛО → СТАЛО: сравнивать не с чем (нет прошлого запуска и таблиц книги)")
        return
    wh = (was.get("quick") or {}).get("headline") or {}
    say(f"БЫЛО → СТАЛО против «{was.get('label')}»" + (f" ({wh.get('draws')} прогонов)" if wh.get("draws") else ""))
    if wh.get("draws") and wh["draws"] != h["draws"]:
        say(f"  ВНИМАНИЕ: число прогонов разное ({wh['draws']} и {h['draws']}) — выборки не общие: разность медиан и полос несёт "
            "ошибку обеих выборок; точка, уровни и развилки от числа прогонов не зависят")
    for title, old, new, kind in compare_rows(now, was):
        if new is None and old is None:
            continue
        scale, unit, nd = (100.0, " п.п.", 2) if kind == "pct" else (1.0, "", 2)
        fmt = (lambda v: pc(v)) if kind == "pct" else (lambda v: ru(v))  # noqa: E731
        d = "" if old is None or new is None else f"   {delta(float(new) - float(old), nd, scale)}{unit}"
        say(f"  {title:<62}{fmt(old):>12} → {fmt(new):<12}{d}")
    old_fired = {c["name"] for c in (was.get("quick") or {}).get("checks", []) if c["kind"] == "gate" and c["fired"]}
    new_fired = {c["name"] for c in q["checks"] if c["kind"] == "gate" and c["fired"]}
    say("  гейты: " + ("сработавшие те же" if old_fired == new_fired else
                       "новые — " + (", ".join(sorted(new_fired - old_fired)) or "нет") + "; замолчали — "
                       + (", ".join(sorted(old_fired - new_fired)) or "нет")))


def brief(now: Mapping[str, Any], was: Mapping[str, Any] | None) -> str:
    """Блок для листа решения (шаблон семейства, разделы 2, 2а, 3, 4) — markdown, готовый к вставке."""
    q, m = now["quick"], now.get("marginal")
    h = q["headline"]
    wh = ((was or {}).get("quick") or {}).get("headline") or {}
    col = lambda f, src: "—" if not src else f(src)  # noqa: E731
    band = lambda s: f"{ru(s['band80'][0], 0)}–{ru(s['band80'][1], 0)} ₽"  # noqa: E731
    both = lambda s: f"{ru(s['median'])} / {ru(s['point'])} ₽"  # noqa: E731
    lines = ["## 2. Заголовок", "",
             f"| | Сейчас ({now['label']}) | Прошлый лист ({(was or {}).get('label', '—')}) |", "|---|---|---|",
             f"| Медиана / точка | {both(h)} | {col(both, wh)} |",
             f"| Полоса 80 % | {band(h)} | {col(band, wh)} |",
             f"| К цене рынка ({ru(h['market'])} ₽) | медиана {delta(h['median_to_market'], 1, 100)} %, точка "
             f"{delta(h['point_to_market'], 1, 100)} %; ниже рынка {pc(h['p_below_market'], 0)} прогонов | "
             + col(lambda s: f"медиана {delta(s['median_to_market'], 1, 100)} %, точка {delta(s['point_to_market'], 1, 100)} %; "
                             f"ниже рынка {pc(s['p_below_market'], 0)} прогонов", wh) + " |", ""]
    d = now.get("derive") or {}
    changed = [c for c in d.get("changes", []) if c["written"]]
    if d.get("ran"):
        keys = sorted({c["key"] for c in changed})
        lines.append("Что изменилось: " + (f"перевыведено чисел — {len(changed)} в {len(keys)} ключах ({', '.join(keys)})."
                                           if changed else "выведенные числа книги не изменились.")
                     + " Разложение сдвига по суждениям — последовательной заменой, заполняет ведущий.")
        for row in d.get("unwritten") or []:
            lines += ["", "Не переписано командой — решение ведущего: " + gate_gap_words(row)
                      + f" (правило: {row['rule']}). Перенести порог в шаблон руками либо изменить правило листа."]
    else:
        lines.append("Что изменилось: подбор не запускался — числа книги как есть.")
    lines += ["", f"Числа — сетка и малая полоса на {h['draws']} прогонов (зерно {h['seed']}); ПРЕДВАРИТЕЛЬНО: ошибка медианы от "
                  f"числа прогонов — около ±{ru(h.get('median_error'), 1)} ₽."
                  + (" " + CENTRE_ONLY + "." if (now.get("mode") or {}).get("centre_only") else ""), "",
              "## 2а. Пробные счёты этого круга", "",
              "| Что пробовали | Правило, из которого это следует | Заголовок | Проверки раздела 3 | Принято? |", "|---|---|---|---|---|"]
    lines.append(f"| запуск «{now['label']}» | | точка {ru(h['point'])} ₽, медиана {ru(h['median'])} ₽ | "
                 + flags_cell(now.get("flags") or []) + " | |")
    lv = q["levels"]
    rows, window = lv["rows"], lv["window"] or {}
    w = lambda k, nd=2: "—" if not window.get(k) or window[k].get("min") is None else f"{pc(window[k]['min'], nd)}–{pc(window[k]['max'], nd)}"  # noqa: E731
    lines += ["", "## 3. Приёмочные проверки чисел", "", "| Проверка | Результат | Норма | Вывод |", "|---|---|---|---|"]
    if rows:
        r = rows[LEVEL_LAYER]
        verdict = [f"{t} {inside(r[k], window.get(k))}" for k, t, _ in LEVEL_METRICS if inside(r[k], window.get(k))]
        lines.append(f"| Уровни в условиях окна фактов | слой «{r['title']}», {lv['from_year']}–{lv['to_year']}: ЧПМ {pc(r['nim'])}, CoR {pc(r['cor'])}, "
                     f"C/I {pc(r['cir'], 1)} | окно: ЧПМ {w('nim')}, CoR {w('cor')}, C/I {w('cir', 1)} | {'; '.join(verdict)} |")
        mix = "; ".join(f"{rows[n]['title']}: ЧПМ {pc(rows[n]['nim'])}, CoR {pc(rows[n]['cor'])}, C/I {pc(rows[n]['cir'], 1)}, ROE {pc(rows[n]['roe'], 1)}"
                        for n in rows if n != LEVEL_LAYER)
        out = [f"{rows[n]['title']}: {t}" for n in rows if n != LEVEL_LAYER for k, t, _ in LEVEL_METRICS[1:]
               if outside(rows[n][k], window.get(k))]
        lines.append(f"| Модальная клетка / ожидание слоёв / смесь заголовка | {mix} | внутри диапазона фактов | "
                     + ("CoR и C/I внутри окна" if not out else "ВНЕ окна — " + ", ".join(out)) + " |")
    if m and m.get("error"):
        lines.append("| Предельная экономика роста | лист не отработал: " + " ".join(m["error"]) + " | | проверки НЕТ |")
    elif m:
        verdict, tail = marginal_words(m)
        unpaid = [wd for wd, t in m["rows"].items() if not pays(t)]
        above = [wd for wd, t in m["rows"].items() if above_norm(t)]
        lines.append(f"| Предельный кредит против стоимости капитала по мирам | {tail}: "
                     + "; ".join(f"мир {wd} — {norm_word(t, verdict)}" for wd, t in m["rows"].items())
                     + " | отдача выше стоимости капитала"
                     + (" и не выше верхнего края нормы" if any(t[-1].get("ceiling") is not None for t in m["rows"].values()) else "")
                     + " | "
                     + (f"{verdict[0]} во всех мирах" if not unpaid and not above else
                        "; ".join(([f"{verdict[1]}: " + ", ".join(unpaid)] if unpaid else [])
                                  + ([f"{verdict[2] if len(verdict) > 2 else 'ВЫШЕ нормы'}: " + ", ".join(above)] if above else [])))
                     + " |")
    if m and not m.get("error"):
        a = m["anchor"]
        late = "; ".join(f"мир {wd}: {pc(t[-1]['value'], 1)} при стоимости капитала {pc(t[-1]['hurdle'], 1)}" for wd, t in m["rows"].items())
        aw = (m.get("words") or {}).get("anchor_words")
        lines.append(f"| Предельная экономика роста | {aw[0]}: {pc(a['model_min'], 1)}–{pc(a['model_max'], 1)}; {late} | "
                     f"{aw[1]}: {pc(a['segment_low'], 1)}–{pc(a['segment_high'], 1)} | {aw[2] if a['ok'] else aw[3]} |" if aw else
                     f"| Предельная экономика роста | якорь: {pc(a['model_min'], 1)}–{pc(a['model_max'], 1)}; конец сетки — {late} | "
                     f"факт сегмента по отчётности {pc(a['segment_low'], 1)}–{pc(a['segment_high'], 1)} | "
                     + ("на якоре сопоставимо" if a["ok"] else "на якоре РАСХОДИТСЯ") + " |")
    for block in now.get("acceptance") or []:
        failed = [row["name"] for row in block["rows"] if not row.get("ok", True)]
        lines.append(f"| Проверки книги: {block['title']} | строк {len(block['rows'])} | каждая — в своих пределах | "
                     + ("пройдены" if not failed and not block.get("error") else "НЕ пройдены — " + "; ".join(failed or block["error"])) + " |")
    cl = now.get("classes")
    if cl and cl.get("error"):
        lines.append("| Проверки классов ошибок (PLAYBOOK §2а) | не отработали: " + " ".join(cl["error"]).replace("|", "¦")
                     + " | | проверки НЕТ |")
    elif cl:
        norm = "по уставу" + (" (заготовка до устава)" if "заготовка" in str((cl.get("config") or {}).get("status")) else "")
        for c in cl["checks"]:
            found = "; ".join(" ".join(str(x).replace("|", "¦").split()) for x in c["findings"][:2])
            lines.append(f"| Класс {c['cls']}: {c['title']} | {c['status_words']}"
                         + (f" ({c['tally']})" if c.get("tally") else "")
                         + (f" — находок {c['count']}: {found}" if c["count"] else "") + f" | {norm} | "
                         + class_verdict(c) + " |")
    signs = []
    if q.get("sign_test"):
        signs.append(f"объёмные эффекты: точка {delta(q['sign_test']['d_point'])} ₽ — " + ("выполнен" if q["sign_test"]["ok"] else "НЕ выполнен"))
    if q.get("stress_sign"):
        signs.append(f"стресс: превышение {ru(q['stress_sign']['max_excess'], 1)} млрд ₽ — " + ("выполнен" if q["stress_sign"]["ok"] else "НЕ выполнен"))
    status = {c["name"]: c for c in q["checks"]}
    fired_signs = [f"`{name}` сработал: {STATUS_WORDS.get(status[name]['status'], '—')}" for name in ("volume_sign", "stress_sign")
                   if name in status and status[name]["fired"]]
    lines.append(f"| Знаки (убыток, требование, стоимость риска) | {'; '.join(signs) or '—'} | ухудшение не повышает оценку | "
                 + ("; ".join(fired_signs) if fired_signs else "гейты знака тихи" if signs else "") + " |")
    if q.get("order"):
        o = q["order"]
        pe = "; ".join(f"P/E на прибыль {y} года {ru(r['pe_point'], 1)} (рынок {ru(r['pe_market'], 1)})" for y, r in o["years"].items())
        lines.append(f"| Сверка порядка с книгой-образцом и целями аналитиков | P/B точки {ru(o['fair_pb'])} (рынок {ru(o['market_pb'])}); "
                     f"ROE после фазы роста {pc(o['roe_tc'], 1)} при стоимости капитала {pc(o['k_tc'], 1)}; {pe} | — | |")
    fired = [c for c in q["checks"] if c["kind"] == "gate" and c["fired"]]
    lines += ["", f"Сработавшие гейты ({len(fired)}): " + ("нет." if not fired else "; ".join(
        f"`{c['name']}` (масса {ru(c['mass'], 2) if c['mass'] is not None else '—'}, {STATUS_WORDS.get(c['status'], c['status'])})" for c in fired) + ".")]
    lines += ["", "## 4. Развилки с ценой", "", "| Правило или развилка | Цена, ₽ заголовка | Назван ли владельцу |", "|---|---|---|"]
    for r in by_price(q.get("reference_variants") or []):
        price = ("— (forks_rd)" if r.get("price_rule") == "rd" else
                 unpriced(r).replace("|", "¦") if r.get("d_point") is None else delta(r["d_point"]))
        lines.append(f"| {r['title']}" + (f" ({variant_mark(r)})" if r.get("price_rule") else "") + f" | {price} | |")
    if not q.get("reference_variants"):
        lines.append("| (справочные варианты не считались) | | |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ записи запусков


def read_run(state: Path, label: str) -> dict:
    path = state / f"{label}.json"
    if not path.exists():
        raise Refused(f"нет записи запуска «{label}» в {state}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run(state: Path, but: str | None = None) -> dict | None:
    """Прошлый запуск с быстрыми числами — последний по времени конца."""
    runs = []
    for path in sorted(state.glob("*.json")) if state.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("schema") == SCHEMA and data.get("quick") and data.get("label") != but:
            runs.append(data)
    return max(runs, key=lambda r: r.get("finished", "")) if runs else None


def baseline(tree: Tree, state: Path, compare: str | None, label: str, version: str | None = None) -> dict | None:
    """С чем сравнивать запуск. Таблицы книги другой версии (`version` — версия книги запуска) меркой по умолчанию
    не служат: это таблицы другой книги; названные явно (`--compare results`) — берутся как есть."""
    if compare in (None, LATEST):
        was = latest_run(state, but=label)
        if was is None:
            was = results_as_run(tree)
            if was is not None and version is not None and str(was["quick"].get("book_version")) != str(version):
                was = None
        return was
    if compare == RESULTS:
        return results_as_run(tree)
    return read_run(state, compare)


# ------------------------------------------------------------------ путь команды


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_text(path: Path, text: str) -> None:
    """Запись файла дерева целиком или никак: рядом — временный файл, затем замена."""
    tmp = path.with_name(path.name + ".rederive-tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def run(*, tree: Tree | None = None, dry_run: bool = False, derive: bool = True, quick: bool = True, serial: bool = False,
        centre_only: bool = False, exact: bool = False,
        runs: int = DEFAULT_RUNS, workers: int = DEFAULT_WORKERS, variants: bool = True, classes: bool = True,
        label: str | None = None,
        compare: str | None = None, state: Path | None = None, today: dt.date | None = None,
        sheet: Callable[..., tuple[dict, list[dict], str]] | None = None, say: Callable[[str], None] = print) -> tuple[int, dict]:
    """Весь путь команды. → (код возврата, запись запуска). `sheet` — подмена запуска листа (тесты): функция с
    подписью `run_sheet`; `today` — дата пометки и объяснений гейтов; `exact` — писать любое отличие, не применяя
    правило сходимости повторного вывода; `classes` — блок проверок классов ошибок после приёмочных проверок."""
    tree = tree or Tree()
    today = today or dt.date.today()
    state = state or tree.state
    label = label or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if not re.fullmatch(r"[\w.\-]+", label) or label in (LATEST, RESULTS):
        raise Refused(f"метка запуска «{label}»: буквы, цифры, точка, дефис и подчёркивание; не «{LATEST}» и не «{RESULTS}»")
    if runs < 2 or workers < 1:
        raise Refused("--runs — не меньше двух прогонов, --workers — не меньше одного процесса")
    if centre_only and (serial or not derive):
        raise Refused("--centre-only — это подбор одной фазой центра: с --serial и --no-derive не сочетается")
    dry_run = dry_run or centre_only                        # книга с новым центром и прежними концами осей — только пробная
    work = state / label
    if work.exists():
        shutil.rmtree(work)
    (work / "before").mkdir(parents=True)
    (work / "after").mkdir()
    started = dt.datetime.now()
    timings: list[dict] = []
    t_all = time.monotonic()

    def clock(name: str, seconds: float) -> None:
        timings.append({"step": name, "seconds": round(seconds, 1)})

    now: dict[str, Any] = {"schema": SCHEMA, "label": label, "started": started.isoformat(timespec="seconds"),
                           "mode": {"dry_run": dry_run, "derive": derive, "quick": quick, "serial": serial, "runs": runs,
                                    "workers": workers, "variants": variants, "centre_only": centre_only, "classes": classes},
                           "derive": None, "quick": None, "marginal": None, "acceptance": [], "classes": None, "flags": [],
                           "timings": timings}
    spec = load_spec(tree)
    build = load_module(tree.book_dir / "build_assumptions.py", "rederive_build")
    say(f"ПЕРЕВЫВОД КНИГИ · запуск «{label}»" + (" · ПРОБНЫЙ СЧЁТ ЦЕНТРА" if centre_only else "")
        + (" · СУХОЙ ПРОГОН: в дерево не пишется ничего" if dry_run else "")
        + ("" if derive else " · без подбора: книга как есть"))

    # 1. машинная книга из шаблона — в рабочий каталог: лист читает её, а не файл дерева
    t = time.monotonic()
    template_text = read_text(tree.template)
    try:
        book_yaml, book_json, _ = build.render(tree.template)
    except build.BuildError as exc:
        raise Stopped(f"сборка машинной книги из шаблона: {exc}") from exc
    stale = [p.name for p, text in ((tree.book_yaml, book_yaml), (tree.book_json, book_json))
             if not p.exists() or p.read_text(encoding="utf-8") != text]
    before = work / "before" / "assumptions.yaml"
    (work / "before" / "assumptions_template.yaml").write_bytes(tree.template.read_bytes())
    before.write_text(book_yaml, encoding="utf-8", newline="\n")
    clock("сборка машинной книги из шаблона", time.monotonic() - t)
    say("1. машинная книга собрана из шаблона" + ("; файлы дерева с ней совпадают" if not stale else
                                                  f"; файлы дерева устарели ({', '.join(stale)}): шаблон правили после сборки"))
    new_text, items, record, printed, plan_count = template_text, [], None, "", None
    if derive:
        # 2. подбор листом — один раз, для центра
        say("2. подбор на ядре (лист " + spec.SHEET + ")")
        t = time.monotonic()
        record, phases, printed = (sheet or run_sheet)(tree, spec, before, work, serial=serial, workers=workers, say=say,
                                                       **({"centre_only": True} if centre_only else {}))
        clock("подбор: лист вывода на ядре" + (" (один запуск)" if serial else f" (фазы: {', '.join(p['name'] for p in phases)})"),
              time.monotonic() - t)
        for p in phases:
            clock(f"  фаза {p['name']} ({', '.join(p['steps'])})", p["seconds"])
        (work / "derive_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        steps = sorted({s for p in phases for s in p["steps"]})
        # 3. приёмка записи листа: сходимость, невязки, коридоры, суждения листа
        root = yaml.compose(template_text, Loader=yaml.SafeLoader)
        items, bad, notes = check_record(spec, record, yaml.safe_load(template_text), root, steps, dry_run=dry_run)
        companions, companion_bad = plan_companions(tree, spec, record, steps)
        bad += companion_bad
        committed = committed_record(tree, spec)
        converged = not bad and not exact and settled(spec, items, committed, record, root, steps)   # всему запуску сразу
        for item in items:
            item.keep = converged
        if converged:                                       # в дереве остаётся прежняя запись вывода: спутник сверяется с ней
            companions, _ = plan_companions(tree, spec, committed, steps)
        say("3. приёмка записи листа")
        for line in notes:
            say("  " + line)
        plan_count = print_plan(items, say)
        now["derive"] = {"ran": True, "steps": steps, "phases": phases, "convergence": record.get("convergence"),
                         "evaluations": record.get("evaluations"), "stopped": bad, "converged": converged, "exact": exact,
                         "changes": [{"key": item.where, "subkey": lf.subkey, "step": item.entry["step"], "rule": item.entry["rule"],
                                      "old": lf.old, "new": lf.new, "written": item.rewrite}
                                     for item in items if not item.verify for lf in item.leaves if lf.differs],
                         # пороги гейтов, которые правило листа даёт другими: сверены, не переписаны
                         "unwritten": [{"key": item.where, "step": item.entry["step"], "rule": item.entry["rule"],
                                        "book": item.old, "sheet": item.new} for item in items if item.gap]}
        now["flags"] = flags_of(now)
        if bad:
            say("")
            say("ОСТАНОВКА — в шаблон не записано ничего:")
            for line in bad:
                say("  • " + line)
            now.update(exit_code=STOPPED, finished=dt.datetime.now().isoformat(timespec="seconds"))
            state.mkdir(parents=True, exist_ok=True)        # запись остановленного запуска — с причинами остановки
            (state / f"{label}.json").write_text(json.dumps(now, ensure_ascii=False, indent=1, default=_plain) + "\n",
                                                 encoding="utf-8", newline="\n")
            raise Stopped("подбор не принят: " + "; ".join(bad)[:400])
        # 4. точечная запись в текст шаблона и её сверка повторным разбором
        new_text, mark_notes = patch(template_text, items, today.strftime("%d.%m.%Y"))
        changed = new_text != template_text
        # сверка 3: шаблон после записи равен записи вывода во всех выведенных числах — той, что будет лежать в дереве
        gaps = record_gaps(spec, committed if converged else record, yaml.compose(new_text, Loader=yaml.SafeLoader), steps)
        if gaps:
            raise Stopped("запись в шаблон: шаблон после записи не равен записи вывода — запись отменена: " + "; ".join(gaps[:6]))
        say("4. запись в шаблон: "
            + (f"ключей {plan_count['keys']}, чисел {plan_count['numbers']}; повторный разбор сверен: изменились ровно "
               "намеченные ключи, текст вне замен цел; шаблон равен записи вывода во всех выведенных числах" if changed else
               "изменений нет — повторный вывод сошёлся к записанному: шаблон равен записи вывода дерева, новые числа "
               f"отличаются от неё не больше зоны сходимости (чисел — {plan_count['jitter']}; перечень выше); ни шаблон, ни "
               "запись вывода не тронуты (записать и их — ключ --exact)" if converged else
               "изменений нет — все выведенные числа шаблона равны записи вывода")
            + ("" if not plan_count["gaps"] else f"; порогов гейтов, не равных правилу листа, — {plan_count['gaps']}: не "
                                                 "переписаны (блок «ПОРОГИ ГЕЙТОВ» выше)"))
        for line in mark_notes:
            say("  " + line)
        # 4а. файлы-спутники шаблона: те же выведенные числа, та же точечная запись и сверка повторным разбором
        for comp in companions:
            comp["new_text"], _ = patch(comp["text"], comp["items"], today.strftime("%d.%m.%Y"))
            comp["changed"] = comp["new_text"] != comp["text"]
            keys = [item for item in comp["items"] if item.rewrite]
            numbers = sum(len(lf.new) if lf.whole and isinstance(lf.new, (Mapping, list, tuple)) else 1 for item in keys for lf in item.written)
            say(f"   файл-спутник {comp['file']}: " + (f"ключей {len(keys)}, чисел {numbers}; повторный разбор сверен" if comp["changed"]
                                                       else "изменений нет — числа равны записи вывода"))
            for item in keys:
                say(f"      {item.entry['step']:<12} {item.where} — {item.entry['rule']}")
        now["derive"]["companions"] = [{"file": comp["file"], "changed": comp["changed"],
                                        "keys": [item.where for item in comp["items"] if item.rewrite]} for comp in companions]
    else:
        changed, converged, committed, companions = False, False, None, []
    # 5. пересборка машинной книги и проверка схемы — на пробной книге рабочего каталога
    t = time.monotonic()
    after_template = work / "after" / "assumptions_template.yaml"
    with open(after_template, "w", encoding="utf-8", newline="") as fh:
        fh.write(new_text)
    try:
        new_yaml, new_json, _ = build.render(after_template)
    except build.BuildError as exc:
        raise Stopped(f"сборка машинной книги из нового шаблона: {exc}") from exc
    after = work / "after" / "assumptions.yaml"
    after.write_text(new_yaml, encoding="utf-8", newline="\n")
    from model.book import load_book, load_facts
    from model.book_schema import BookError, FactsError
    try:
        book = load_book(after, facts=load_facts(tree.facts))
    except (BookError, FactsError) as exc:
        raise Stopped(f"новая машинная книга не проходит схему: {exc}") from exc
    clock("пересборка машинной книги и проверка схемы", time.monotonic() - t)
    now["book"] = {"version": str(book.get("meta.version")), "date": str(book.get("meta.date")), "digest": book.digest,
                   "template_sha256_before": sha256(template_text), "template_sha256": sha256(new_text)}
    wrote: list[str] = []
    for comp in companions:                                 # пробная копия спутника — рядом с пробной книгой запуска
        with open(work / "after" / Path(comp["file"]).name, "w", encoding="utf-8", newline="") as fh:
            fh.write(comp["new_text"])
    if not dry_run:
        if changed:
            write_text(tree.template, new_text)
            wrote.append(tree.template.name)
        for comp in companions:
            if comp["changed"]:
                write_text(comp["path"], comp["new_text"])
                wrote.append(comp["file"])
        for path, text in ((tree.book_yaml, new_yaml), (tree.book_json, new_json)):
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8", newline="\n")
                wrote.append(path.name)
        # запись вывода рядом с листом: вместе с шаблоном; без правки шаблона — когда запись дерева с ним не сходится
        # или её нет (иначе шаблон и запись остались бы разными навсегда). Сошедшийся повторный вывод её не трогает
        full = record is not None and set(spec.STEPS) <= set(now["derive"]["steps"])
        stale = full and not changed and not converged and (committed is None or not all(
            same_numbers(spec, committed, record, now["derive"]["steps"], gates=gates) for gates in (False, True)))
        if stale:
            say("  запись вывода дерева " + ("отсутствует" if committed is None else "не равна новой записи листа в числах описания")
                + " — записывается заново (шаблон уже равен новому выводу)")
        if full and (changed or stale):
            start = {k: copy.deepcopy(_dotted(yaml.safe_load(book_yaml), k)) for k in record.get("keys", {})}
            for name, text in ((spec.RECORD["out"], json.dumps(record, ensure_ascii=False, indent=1) + "\n"),
                               (spec.RECORD["print"], printed),
                               (spec.RECORD["start"], json.dumps({"keys": start, "before": start}, ensure_ascii=False, indent=1) + "\n")):
                target = tree.sheet_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
                wrote.append(f"evidence/path/{name}")
    now["wrote"] = wrote
    say("5. машинная книга пересобрана, схема пройдена (книга " + now["book"]["version"] + " от " + now["book"]["date"] + "); "
        + ("сухой прогон — файлы дерева не тронуты" if dry_run else "записано: " + (", ".join(wrote) or "ничего — файлы дерева уже такие")))
    code = OK
    was = None
    if quick:
        # 6–7. быстрые числа и приёмочные проверки — на новой книге
        say(f"6. быстрые числа: сетка и малая полоса (прогонов {runs}, процессов {workers})")
        now["quick"] = quick_numbers(tree, after, runs=runs, workers=workers, variants=variants, today=today, clock=clock, say=say,
                                     main_forks=tuple(getattr(spec, "MAIN_FORKS", ()) or ()) if spec is not None else ())
        t = time.monotonic()
        now["marginal"] = marginal_numbers(tree, spec, after, work)
        clock("лист предельной экономики роста", time.monotonic() - t)
        t = time.monotonic()
        now["acceptance"] = acceptance_numbers(tree, spec, after, work)
        if now["acceptance"]:
            clock("листы приёмочных проверок книги", time.monotonic() - t)
        if classes:
            say("7а. проверки классов ошибок в модели (PLAYBOOK §2а) — отдельным процессом на той же книге")
            t = time.monotonic()
            now["classes"] = class_numbers(tree, after, work, workers)
            clock("проверки классов ошибок в модели (PLAYBOOK §2а)", time.monotonic() - t)
        now["flags"] = flags_of(now)
        if any(c["kind"] == "invariant" and c["fired"] for c in now["quick"]["checks"]):
            code = INVARIANT
        was = baseline(tree, state, compare, label, version=now["quick"]["book_version"])
        say("")
        print_flags(now["flags"], say)
        if centre_only:
            say("")
            say(CENTRE_ONLY)
        print_compare(now, was, say)
        tables = results_as_run(tree)
        if tables and tables["quick"]["book_digest"] == now["quick"]["book_digest"]:
            gap = now["quick"]["headline"]["point"] - tables["quick"]["headline"]["point"]
            say(f"  сверка с таблицами книги (results.json — та же книга): точка {ru(tables['quick']['headline']['point'])} ₽ против "
                f"{ru(now['quick']['headline']['point'])} ₽ — " + ("совпадает до копейки" if abs(gap) < 0.005 else f"РАСХОДИТСЯ на {delta(gap)} ₽")
                + f"; медиана полной полосы {ru(tables['quick']['headline']['median'])} ₽ ({tables['quick']['headline']['draws']} прогонов) "
                  f"против {ru(now['quick']['headline']['median'])} ₽ малой")
        print_acceptance(now, say)
        print_classes(now, say)
    now["exit_code"] = code
    now["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    clock("весь путь", time.monotonic() - t_all)
    say("")
    say("ВРЕМЯ ПО ШАГАМ, с")
    for row in timings:
        say(f"  {row['seconds']:>8.1f}  {row['step']}")
    unwritten = (now["derive"] or {}).get("unwritten") or []
    if derive and (changed or unwritten):
        say("")
        say("ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ (команда этого не делает):")
        for row in unwritten:
            say("  • " + gate_gap_words(row) + ". Решение ведущего: перенести порог в шаблон руками либо изменить правило "
                "листа; пока порог книги не равен правилу листа, тесты, сверяющие этот ключ шаблона с записью вывода, красные")
        for line in getattr(spec, "REMINDERS", ()) if changed else ():
            say("  • " + line)
    state.mkdir(parents=True, exist_ok=True)
    (state / f"{label}.json").write_text(json.dumps(now, ensure_ascii=False, indent=1, default=_plain) + "\n", encoding="utf-8", newline="\n")
    if quick:
        text = brief(now, was)
        (state / f"{label}.md").write_text(text, encoding="utf-8", newline="\n")
        say("")
        say(f"БЛОК ДЛЯ ЛИСТА РЕШЕНИЯ (файл {label}.md рядом с записью запуска)")
        say(text.rstrip("\n"))
    say("")
    say(f"запись запуска: {(state / (label + '.json')).relative_to(tree.root) if state.is_relative_to(tree.root) else state / (label + '.json')}"
        f"; рабочий каталог запуска (книга до и после, печать листа) — рядом, каталог «{label}»")
    return code, now


def _dotted(book: Mapping[str, Any], dotted: str) -> Any:
    node: Any = book
    for part in dotted.split("."):
        node = node[part]
    return node


def show(state: Path, tree: Tree, label: str, compare: str | None, say: Callable[[str], None] = print) -> int:
    """Сохранённый запуск и его сравнение с другим — без счёта."""
    now = read_run(state, label)
    if not now.get("quick"):
        raise Refused(f"запуск «{label}» без быстрых чисел: показывать нечего")
    was = baseline(tree, state, compare, label)
    now["flags"] = flags_of(now)                            # по числам записи: запись прежней команды несла не все флаги
    say(f"ЗАПУСК «{label}» от {now.get('started')}")
    print_flags(now["flags"], say)
    print_compare(now, was, say)
    print_acceptance(now, say)
    print_classes(now, say)
    say("")
    say(brief(now, was).rstrip("\n"))
    return OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rederive.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="весь путь на пробной книге; в дерево под git не пишется ничего")
    ap.add_argument("--centre-only", action="store_true",
                    help="пробный счёт решения: лист выводит только центр; книга пробная, в дерево не пишется ничего")
    ap.add_argument("--no-derive", action="store_true", help="без подбора: быстрые числа и проверки на книге как есть")
    ap.add_argument("--no-quick", action="store_true", help="только подбор и запись: без быстрых чисел и проверок")
    ap.add_argument("--serial", action="store_true", help="подбор одним запуском листа со всеми шагами (без фаз описания)")
    ap.add_argument("--exact", action="store_true",
                    help="писать любое отличие от шаблона: правило сходимости повторного вывода не применяется")
    ap.add_argument("--runs", type=int, default=DEFAULT_RUNS, help=f"прогонов малой полосы (по умолчанию {DEFAULT_RUNS})")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help=f"процессов полосы и фаз подбора (по умолчанию {DEFAULT_WORKERS})")
    ap.add_argument("--no-variants", action="store_true", help="не считать цену правил и развилок (справочные варианты)")
    ap.add_argument("--no-classes", action="store_true",
                    help="без проверок классов ошибок в модели (PLAYBOOK §2а; блок после приёмочных проверок)")
    ap.add_argument("--label", help="метка запуска — имя его записи (по умолчанию — дата и время)")
    ap.add_argument("--compare", help=f"с чем сравнивать: метка запуска, «{LATEST}» — прошлый запуск (по умолчанию), "
                                      f"«{RESULTS}» — таблицы книги")
    ap.add_argument("--show", metavar="МЕТКА", help="напечатать сохранённый запуск и сравнение, ничего не считая")
    ap.add_argument("--dir", type=Path, help="каталог записей запусков (по умолчанию var/rederive)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    tree = Tree()
    state = args.dir or tree.state
    lines: list[str] = []

    def say(line: str = "") -> None:
        lines.append(line)
        print(line, flush=True)

    try:
        if args.show:
            return show(state, tree, args.show, args.compare, say)
        code, now = run(tree=tree, dry_run=args.dry_run, derive=not args.no_derive, quick=not args.no_quick, serial=args.serial,
                        centre_only=args.centre_only, exact=args.exact,
                        runs=args.runs, workers=args.workers, variants=not args.no_variants, classes=not args.no_classes,
                        label=args.label,
                        compare=args.compare, state=state, say=say)
        (state / f"{now['label']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return code
    except Refused as exc:
        print(f"НЕГОДНЫЕ ВХОДЫ: {exc}", file=sys.stderr)
        return BAD_INPUT
    except Stopped as exc:
        print(f"ОСТАНОВКА: {exc}", file=sys.stderr)
        return STOPPED


if __name__ == "__main__":
    raise SystemExit(main())
