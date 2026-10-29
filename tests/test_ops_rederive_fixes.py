# -*- coding: utf-8 -*-
"""Команда перевывода книги `ops/tools/rederive.py` — правила записи и вывода проверок, принятые после независимой
проверки инструмента: запись в шаблон точная, и шаблон после неё равен записи вывода во всех выведенных числах;
дрожание последнего знака между повторными запусками гасит правило сходимости, а не пропуск отдельных чисел.

Тесты стоят на игрушечном дереве: копия книги и фактов рабочей копии во временном каталоге, а рядом — игрушечное
описание вывода из четырёх записей (траектория центра, число шага после центра, поле окна фактов, коридор гейта) и
подменённый расчёт. От описания вывода настоящей книги (`data/assumptions/evidence/path/derive_spec.py`) и от её листа
тесты не зависят: числа записи берутся от чисел шаблона копии (описание рабочей копии читает один сторож: пороги гейтов
в нём не записываемые). Лист вывода не запускается, быстрые числа не считаются; в рабочую копию тесты не пишут."""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "data" / "assumptions"
TODAY = dt.date(2031, 2, 3)                      # дата пометки в тестах: в шаблоне её быть не может
ROOTS = ("opex", "real_growth")                  # траектория центра игрушечного описания — ключ формы панели
UNIT = 1e-4                                      # единица последнего знака игрушечных записей с зоной сходимости


def _load():
    spec = importlib.util.spec_from_file_location("tool_rederive_fixes", ROOT / "ops" / "tools" / "rederive.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = _load()

# Игрушечное описание вывода: центр — траектория корней расходов (итерация: зона сходимости в единицу знака); после
# центра — число, найденное поиском корня (зона), поле окна фактов (зоны нет) и коридор гейта.
TOY_SPEC = '''# -*- coding: utf-8 -*-
SHEET = "toy_sheet.py"
RECORD = {"out": "out/derive_out.json", "print": "out/derive_out.txt", "start": "out/derive_start.json"}
STEPS = ("centre", "ends")
LINKED = ("centre",)
PHASES = ({"name": "centre", "title": "центр", "steps": ("centre",), "after": None},
          {"name": "ends", "title": "концы", "steps": ("ends",), "after": "centre", "take": (("ends",),)})
DEADBAND_UNITS = 1.0
WRITES = (
    {"step": "centre", "address": ("opex", "real_growth"), "source": ("keys", "opex.real_growth"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "mark": True, "rule": "корни расходов (проба)",
     "corridor": [("LT_from", None, None, "год — число книги"), ("*", -1.0, 1.0, "проба")]},
    {"step": "ends", "address": ("checks", "window_backtest", "loans_share"), "source": ("ends", "loans_share"), "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "число шага после центра, найденное поиском корня (проба)",
     "corridor": [("", 0.0, 1.0, "доля")]},
    {"step": "ends", "address": ("checks", "window_backtest", "means", "nim"), "source": ("ends", "nim_mean"), "unit": 1e-5,
     "rule": "окно фактов: среднее (проба)", "corridor": [("", 0.0, 1.0, "доля")]},
    {"step": "ends", "address": ("checks", "wholesale_share"), "source": ("ends", "wholesale"), "unit": 0.01,
     "rule": "коридор гейта по счёту ядра (проба)", "corridor": [("*", 0.0, 1.0, "доля")]},
)
SAME = ()
RESIDUALS = ()
'''
OUT = ("evidence/path/out/derive_out.json", "evidence/path/out/derive_out.txt", "evidence/path/out/derive_start.json")
BOOK_FILES = ("assumptions_template.yaml", "assumptions.yaml", "assumptions.json")


@pytest.fixture()
def tree(tmp_path):
    """Игрушечное дерево: копия книги и фактов рабочей копии и игрушечное описание вывода рядом с местом листа."""
    root = tmp_path / "tree"
    shutil.copytree(BOOK, root / "data" / "assumptions", ignore=lambda d, names: {n for n in names if n in ("evidence", "__pycache__")})
    shutil.copytree(ROOT / "data" / "facts", root / "data" / "facts")
    sheet_dir = root / "data" / "assumptions" / "evidence" / "path"
    sheet_dir.mkdir(parents=True)
    (sheet_dir / "derive_spec.py").write_text(TOY_SPEC, encoding="utf-8")
    return R.Tree(root=root)


def template(tree) -> dict:
    return yaml.safe_load(R.read_text(tree.template))


def book_record(tree) -> dict:
    """Запись вывода, равная шаблону игрушечного дерева: на ней команда не меняет ничего."""
    book = template(tree)
    window = book["checks"]["window_backtest"]
    return {"keys": {"opex.real_growth": copy.deepcopy(book["opex"]["real_growth"])},
            "ends": {"loans_share": window["loans_share"], "nim_mean": window["means"]["nim"],
                     "wholesale": list(book["checks"]["wholesale_share"])},
            "convergence": {"converged": True, "tol": 1e-4, "rounds": [{"round": 1, "max_relative_change": 5e-5, "at": "x"}]},
            "evaluations": {"cells": 1, "grids": 1}}


def years(record: dict) -> list[str]:
    """Годы траектории центра (без долгосрочного значения и года выхода на него)."""
    return [k for k in record["keys"]["opex.real_growth"] if not k.startswith("LT")]


def shifted(record: dict, *, roots: dict[str, float] | None = None, share: float = 0.0, mean: float = 0.0) -> dict:
    """Запись со сдвигами: `roots` — год траектории центра → сдвиг в единицах знака; `share` — сдвиг числа шага после
    центра в единицах знака; `mean` — сдвиг поля окна фактов (у него зоны сходимости нет)."""
    out = copy.deepcopy(record)
    for year, units in (roots or {}).items():
        out["keys"]["opex.real_growth"][year] = round(out["keys"]["opex.real_growth"][year] + units * UNIT, 6)
    out["ends"]["loans_share"] = round(out["ends"]["loans_share"] + share * UNIT, 6)
    out["ends"]["nim_mean"] = round(out["ends"]["nim_mean"] + mean, 6)
    return out


def substituted(record: dict):
    """Подменённый расчёт: вместо запуска листа — готовая запись (все шаги описания)."""
    def sheet(tree, spec, book, work, *, serial, workers, say, centre_only=False):
        return copy.deepcopy(record), [{"name": "all", "steps": list(spec.STEPS), "seconds": 0.0,
                                        "evaluations": record.get("evaluations")}], "печать подменённого расчёта\n"
    return sheet


def snapshot(tree) -> dict[str, bytes | None]:
    return {name: (tree.book_dir / name).read_bytes() if (tree.book_dir / name).exists() else None for name in BOOK_FILES + OUT}


def run(tree, record: dict, label: str, **kw):
    """Запуск команды на игрушечном дереве с подменённым расчётом. → (код, запись запуска, печать)."""
    lines: list[str] = []
    code, now = R.run(tree=tree, quick=False, label=label, sheet=substituted(record), today=TODAY, say=lines.append, **kw)
    return code, now, "\n".join(lines)


def derived(tree, record: dict) -> dict:
    """Выведенные числа, которые команда пишет: как они стоят в шаблоне дерева и в записи вывода."""
    book = template(tree)
    window = book["checks"]["window_backtest"]
    return {"шаблон": (book["opex"]["real_growth"], window["loans_share"], window["means"]["nim"]),
            "запись": (record["keys"]["opex.real_growth"], record["ends"]["loans_share"], record["ends"]["nim_mean"])}


def tree_record(tree) -> dict:
    return json.loads((tree.book_dir / OUT[0]).read_text(encoding="utf-8"))


def gaps(tree) -> list[str]:
    """Где шаблон дерева не равен записи вывода дерева — сверкой самой команды."""
    spec = R.load_spec(tree)
    return R.record_gaps(spec, tree_record(tree), yaml.compose(R.read_text(tree.template), Loader=yaml.SafeLoader), spec.STEPS)


# ------------------------------------------------------------ запись точная: шаблон равен записи вывода


def test_a_number_moved_by_exactly_one_unit_is_written_and_the_template_equals_the_record(tree):
    """Находка проверки: число, сдвинувшееся ровно на единицу последнего знака, в шаблон не писалось, а в запись вывода
    писалось — книга оставалась с числом прежнего вывода, а команда печатала «изменений нет». Теперь рядом с числами,
    сдвинувшимися далеко, пишется и число, сдвинувшееся на единицу знака: шаблон после записи равен записи вывода во
    всех выведенных числах, и повторный запуск с той же записью листа не меняет ничего."""
    base = book_record(tree)
    first, second, last = years(base)[1], years(base)[2], years(base)[-1]
    record = shifted(base, roots={first: 50, second: 50, last: 1}, share=1)      # два корня — далеко; корень и число шага
    before = snapshot(tree)                                                      # после центра — ровно на единицу знака
    code, now, printed = run(tree, record, "write")
    assert code == R.OK and set(now["wrote"]) == set(BOOK_FILES) | {"evidence/path/" + n.split("/", 2)[2] for n in OUT}
    assert derived(tree, record)["шаблон"] == derived(tree, record)["запись"], "шаблон равен записи вывода — число в число"
    assert tree_record(tree) == record and gaps(tree) == []
    book = template(tree)
    assert book["opex"]["real_growth"][last] == pytest.approx(base["keys"]["opex.real_growth"][last] + UNIT, abs=1e-12)
    assert book["checks"]["window_backtest"]["loans_share"] == pytest.approx(base["ends"]["loans_share"] + UNIT, abs=1e-12)
    changes = now["derive"]["changes"]
    assert len(changes) == 4 and all(c["written"] for c in changes) and not now["derive"]["converged"]
    assert "шаблон равен записи вывода во всех выведенных числах" in printed and "зоне сходимости" not in printed
    after = snapshot(tree)
    assert all(after[name] != before[name] for name in BOOK_FILES + OUT)
    code, again, printed = run(tree, record, "again")
    assert code == R.OK and again["wrote"] == [] and again["derive"]["changes"] == [] and snapshot(tree) == after
    assert "изменений нет — все выведенные числа шаблона равны записи вывода" in printed and gaps(tree) == []


def test_a_single_number_is_never_skipped_on_its_own():
    """План записи: число пишется, если отличается от шаблона в точности записи, — и на единицу знака тоже; зона
    сходимости описания числа не пропускает, она только помечает отличие как «в зоне» для решения обо всём запуске."""
    text = "a:\n  path: {\"2026\": 0.0100, LT: 0.0200}   # [Р] ВЫВЕДЕНО НА ЯДРЕ 01.01.2030 — правило\n  end: -0.015   # конец оси\n"
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    path = {"step": "s", "address": ("a", "path"), "unit": 1e-4, "deadband": 1.0, "mark": True, "rule": "правило",
            "corridor": [("*", -1.0, 1.0, "проба")]}
    end = {"step": "s", "address": ("a", "end"), "unit": 0.001, "deadband": 1.0, "rule": "конец", "corridor": [("", -1.0, 0.0, "проба")]}
    items = [R.plan_item(root, path, {"2026": 0.0101, "LT": 0.0200}), R.plan_item(root, end, -0.014)]
    assert [(lf.subkey, lf.differs, lf.near) for item in items for lf in item.leaves] == [
        ("2026", True, True), ("LT", False, False), ("", True, True)]
    assert all(item.rewrite and not item.jitter for item in items), "единица знака — не повод не писать"
    new_text, marks = R.patch(text, items, "03.02.2031")
    assert yaml.safe_load(new_text) == {"a": {"path": {"2026": 0.0101, "LT": 0.02}, "end": -0.014}} and len(marks) == 1
    far = R.plan_item(root, end, -0.013)
    plain = R.plan_item(root, {**end, "deadband": 0.0}, -0.014)
    assert (far.leaves[0].near, plain.leaves[0].near) == (False, False), "две единицы и число без зоны — вне зоны"
    for item in items:                                   # решение правила сходимости — всему запуску: не пишется ничего
        item.keep = True
    assert not any(item.rewrite or item.written for item in items) and [len(item.jitter) for item in items] == [1, 1]
    assert R.patch(text, items, "03.02.2031") == (text, [])


# ------------------------------------------------------------ правило сходимости повторного вывода


def test_a_repeat_run_that_differs_only_by_jitter_changes_nothing(tree):
    """Книга уже несёт запись вывода, а повторный вывод отличается от неё только дрожанием: число центра и число шага
    после центра сдвинулись на единицу последнего знака. Вывод сошёлся к записанному — не пишется ничего: и шаблон, и
    запись вывода дерева остаются как были и равными друг другу, числа в зоне напечатаны отдельно."""
    written = shifted(book_record(tree), roots={years(book_record(tree))[1]: 50})
    assert run(tree, written, "write")[0] == R.OK and gaps(tree) == []
    after = snapshot(tree)
    first, last = years(written)[1], years(written)[-1]
    jitter = shifted(written, roots={first: 1, last: -1}, share=-1)
    for label, dry in (("jitter-dry", True), ("jitter", False)):
        code, now, printed = run(tree, jitter, label, dry_run=dry)
        assert code == R.OK and now["wrote"] == [] and snapshot(tree) == after, label
        assert now["derive"]["converged"] and [c["written"] for c in now["derive"]["changes"]] == [False] * 3
        assert "изменений нет — повторный вывод сошёлся к записанному" in printed and "(чисел — 3; перечень выше)" in printed
        assert "записать и их — ключ --exact" in printed
        assert printed.count("в зоне сходимости (1 ед. знака 0.0001) — вывод сошёлся к записанному, не переписано") == 2
        assert now["book"]["template_sha256"] == now["book"]["template_sha256_before"]
    assert tree_record(tree) == written and gaps(tree) == [], "шаблон и запись вывода дерева равны по-прежнему"
    # правило не отличит дрожание от настоящего сдвига той же величины: ключ --exact пишет любое отличие
    code, now, printed = run(tree, jitter, "exact", exact=True)
    assert code == R.OK and not now["derive"]["converged"] and now["derive"]["exact"]
    assert [c["written"] for c in now["derive"]["changes"]] == [True] * 3 and tree_record(tree) == jitter and gaps(tree) == []
    assert "повторный вывод сошёлся" not in printed and "шаблон равен записи вывода во всех выведенных числах" in printed


TOY_TEXT = 'a:\n  path: {"2026": 0.0100, LT: 0.0200}\n  end: -0.015\n  fact: 0.5\nchecks:\n  gate: [0.1, 0.2]\n'
TOY_BOOK = {"keys": {"a.path": {"2026": 0.01, "LT": 0.02}}, "ends": {"end": -0.015, "fact": 0.5, "gate": [0.1, 0.2]}}


def _toy(zone: float = 1.0):
    """Описание и шаблон без книги: два числа центра и число шага после центра с зоной сходимости, число без зоны и
    коридор гейта."""
    spec = types.SimpleNamespace(
        PHASES=({"name": "centre", "steps": ("centre",), "after": None}, {"name": "ends", "steps": ("ends",), "after": "centre"}),
        WRITES=({"step": "centre", "address": ("a", "path"), "source": ("keys", "a.path"), "unit": 1e-4, "deadband": zone,
                 "rule": "центр", "corridor": [("*", -1.0, 1.0, "проба")]},
                {"step": "ends", "address": ("a", "end"), "source": ("ends", "end"), "unit": 0.001, "deadband": zone, "rule": "конец",
                 "corridor": [("", -1.0, 1.0, "проба")]},
                {"step": "ends", "address": ("a", "fact"), "source": ("ends", "fact"), "unit": 1e-5, "rule": "факт",
                 "corridor": [("", -1.0, 1.0, "проба")]},
                {"step": "ends", "address": ("checks", "gate"), "source": ("ends", "gate"), "unit": 0.01, "rule": "коридор гейта",
                 "corridor": [("*", 0.0, 1.0, "проба")]}))
    root = yaml.compose(TOY_TEXT, Loader=yaml.SafeLoader)

    def items(record):
        out = [R.plan_item(root, entry, R.source_value(record, entry["source"])) for entry in spec.WRITES]
        for item in out:
            item.verify = R.verify_only(spec, item.entry)
        return out
    return spec, root, items


def _record(centre=None, end=-0.015, fact=0.5, gate=(0.1, 0.2)) -> dict:
    return {"keys": {"a.path": centre or {"2026": 0.01, "LT": 0.02}}, "ends": {"end": end, "fact": fact, "gate": list(gate)}}


JITTER = {"2026": 0.0101, "LT": 0.02}                # число центра сдвинулось на единицу последнего знака


@pytest.mark.parametrize("name,new,committed,verdict", [
    ("дрожание центра и числа после центра", _record({"2026": 0.0101, "LT": 0.0199}, end=-0.014), TOY_BOOK, True),
    ("дрожание одного центра", _record(JITTER), TOY_BOOK, True),
    ("отличий нет", _record(), TOY_BOOK, False),
    ("число центра ушло на две единицы знака", _record({"2026": 0.0102, "LT": 0.0199}, end=-0.014), TOY_BOOK, False),
    ("число после центра ушло на две единицы знака", _record(JITTER, end=-0.013), TOY_BOOK, False),
    ("центр тот же: отличие числа после центра настоящее", _record(end=-0.014), TOY_BOOK, False),
    ("число без зоны отличается", _record(JITTER, fact=0.50001), TOY_BOOK, False),
    ("запись вывода дерева не равна шаблону", _record(JITTER), _record({"2026": 0.01, "LT": 0.0201}), False),
    ("записи вывода в дереве нет", _record(JITTER), None, False),
    ("в записи вывода дерева нет узла", _record(JITTER), {"keys": TOY_BOOK["keys"]}, False),
    # порог гейта не пишется и сходимости не мешает, пока правило листа даёт его тем же, что в записи дерева
    ("порог гейта книги не равен правилу листа, запись дерева несёт правило", _record(JITTER, gate=(0.1, 0.3)),
     _record(gate=(0.1, 0.3)), True),
    ("правило листа даёт порог гейта не тем, что в записи дерева: запись устарела", _record(JITTER, gate=(0.1, 0.3)),
     TOY_BOOK, False),
])
def test_the_convergence_rule_takes_only_the_jitter_of_a_written_book(name, new, committed, verdict):
    """Границы правила сходимости: вывод сошёлся к записанному только когда шаблон равен записи вывода дерева, каждое
    отличие — не больше зоны сходимости, и сдвинулось число центра. Отличие сверх зоны, отличие числа без зоны,
    отличие числа после центра при том же центре, запись дерева, не равная шаблону или устаревшая в порогах гейтов, —
    и пишется всё."""
    spec, root, items = _toy()
    steps = ("centre", "ends")
    assert R.settled(spec, items(new), committed, new, root, steps) is verdict, name
    assert R.record_gaps(spec, TOY_BOOK, root, steps) == []
    # без зоны в описании (deadband 0) дрожания нет вовсе: любое отличие пишется
    spec0, root0, items0 = _toy(zone=0.0)
    assert R.settled(spec0, items0(new), committed, new, root0, steps) is False


def test_a_move_beyond_the_jitter_writes_every_number_exactly(tree):
    """Рядом с настоящим сдвигом дрожание не выделяется: пишутся все отличия, и шаблон снова равен записи вывода.
    Так же — когда центр тот же, а число шага после центра сдвинулось на единицу знака: оно функция записанного центра,
    и его отличие — не дрожание."""
    written = shifted(book_record(tree), roots={years(book_record(tree))[1]: 50})
    assert run(tree, written, "write")[0] == R.OK
    first, last = years(written)[1], years(written)[-1]
    moved = shifted(written, roots={first: 2, last: 1}, share=1)                 # корень — на две единицы знака
    code, now, printed = run(tree, moved, "moved")
    assert code == R.OK and not now["derive"]["converged"] and [c["written"] for c in now["derive"]["changes"]] == [True] * 3
    assert tree_record(tree) == moved and gaps(tree) == [] and derived(tree, moved)["шаблон"] == derived(tree, moved)["запись"]
    end_only = shifted(moved, share=1)                                           # центр тот же
    code, now, printed = run(tree, end_only, "end-only")
    assert code == R.OK and not now["derive"]["converged"] and [c["key"] for c in now["derive"]["changes"]] == [
        "checks.window_backtest.loans_share"] and now["derive"]["changes"][0]["written"]
    assert tree_record(tree) == end_only and gaps(tree) == []
    fact = shifted(end_only, roots={first: 1}, mean=0.00001)                     # дрожание центра и новое число окна фактов
    code, now, printed = run(tree, fact, "fact")
    assert code == R.OK and not now["derive"]["converged"] and all(c["written"] for c in now["derive"]["changes"])
    assert tree_record(tree) == fact and gaps(tree) == []


def test_a_record_of_the_tree_that_differs_from_the_template_is_brought_back(tree):
    """Дерево, в котором шаблон и запись вывода разошлись (так его оставляла прежняя «мёртвая зона записи»), команда
    возвращает в согласие: дрожание тут не признаётся — пишется точно; а когда шаблон уже равен новому выводу и править
    в нём нечего, заново пишется сама запись вывода. Без записи вывода в дереве она пишется при первом же запуске."""
    base = book_record(tree)
    assert snapshot(tree)[OUT[0]] is None
    code, now, printed = run(tree, base, "first")                                # шаблон равен выводу, записи вывода нет
    assert code == R.OK and now["wrote"] == ["evidence/path/" + n.split("/", 2)[2] for n in OUT] and gaps(tree) == []
    assert "запись вывода дерева отсутствует — записывается заново" in printed
    assert "изменений нет — все выведенные числа шаблона равны записи вывода" in printed
    # прежняя команда: в запись вывода число записано, в шаблон — нет
    stuck = shifted(base, share=1)
    (tree.book_dir / OUT[0]).write_text(json.dumps(stuck, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert gaps(tree) == [f"checks.window_backtest.loans_share: в шаблоне {R.flow_text(base['ends']['loans_share'])}, в записи "
                          f"вывода {R.flow_text(stuck['ends']['loans_share'])}"]
    code, now, printed = run(tree, stuck, "unstick")                             # лист снова даёт число записи
    assert code == R.OK and "assumptions_template.yaml" in now["wrote"] and gaps(tree) == []
    assert template(tree)["checks"]["window_backtest"]["loans_share"] == stuck["ends"]["loans_share"]
    # шаблон равен новому выводу, а запись дерева — нет: шаблон не тронут, запись вывода переписана
    (tree.book_dir / OUT[0]).write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    assert gaps(tree) != []
    text = R.read_text(tree.template)
    code, now, printed = run(tree, stuck, "record-only")
    assert code == R.OK and now["wrote"] == ["evidence/path/" + n.split("/", 2)[2] for n in OUT] and R.read_text(tree.template) == text
    assert "запись вывода дерева не равна новой записи листа в числах описания — записывается заново" in printed
    assert tree_record(tree) == stuck and gaps(tree) == []
    # дрожание на дереве, где запись вывода не равна шаблону, не признаётся сходимостью: пишется точно
    (tree.book_dir / OUT[0]).write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    jitter = shifted(stuck, roots={years(stuck)[1]: 1})
    code, now, printed = run(tree, jitter, "no-settle")
    assert code == R.OK and not now["derive"]["converged"] and tree_record(tree) == jitter and gaps(tree) == []


# ------------------------------------------------------------ пороги гейтов сверяются, но не пишутся


def test_the_gate_thresholds_are_told_by_their_address():
    """Порог гейта узнаётся по адресу в шаблоне: ключи под `checks`, кроме полей окна фактов. Описание вывода может
    назвать свои адреса; описание, которое их не называет, получает умолчание команды — порог гейта не окажется
    записываемым оттого, что описание о нём забыло."""
    entry = lambda *address: {"address": address}  # noqa: E731
    bare = types.SimpleNamespace()
    for address, verdict in ((("checks", "wholesale_share"), True), (("checks", "pb_by_world", "N"), True),
                             (("checks", "cir_lt", "target"), True), (("checks", "window_backtest", "cor", 0), False),
                             (("checks", "window_backtest", "means", "nim"), False), (("opex", "real_growth"), False),
                             (("valuation", "uncertainty", "axes", {"paths.0": "checks.x"}, "low"), False)):
        assert R.verify_only(bare, entry(*address)) is verdict, address
    own = types.SimpleNamespace(GATES=(("limits",),), GATE_FACTS=())
    assert R.verify_only(own, entry("limits", "x")) and not R.verify_only(own, entry("checks", "wholesale_share"))
    spec = R.load_spec(R.Tree())                         # описание рабочей копии: пороги гейтов не пишутся
    # решения ведущего № 4, Р4-10: цель и допуск гейта cir_lt выводятся из уровня окна на базе М13 (GATE_FACTS описания) — пишутся
    # решения ведущего № 10, Р10-16: пороги, которые описание отдаёт команде (GATE_RULES), пишутся по правилу листа
    rules = tuple(tuple(p) for p in getattr(spec, "GATE_RULES", ()))
    ruled = lambda e: any(tuple(e["address"][:len(p)]) == p for p in rules)  # noqa: E731
    assert all(R.verify_only(spec, e) for e in spec.WRITES
               if e["address"][0] == "checks" and e["address"][1] not in ("window_backtest", "cir_lt") and not ruled(e))
    assert not any(R.verify_only(spec, e) for e in spec.WRITES if e["address"][:2] == ("checks", "cir_lt"))
    assert all(not R.verify_only(spec, e) and R.gate_rule(spec, e) for e in spec.WRITES if ruled(e))
    own_rules = types.SimpleNamespace(GATE_RULES=(("checks", "wholesale_share"),))
    assert not R.verify_only(own_rules, entry("checks", "wholesale_share")) and R.verify_only(own_rules, entry("checks", "pb_by_world", "N"))
    item = _toy()[2](_record(gate=(0.1, 0.3)))[-1]
    assert item.verify and item.gap and not item.rewrite and not item.written and not item.jitter
    assert (item.old, item.new) == ([0.1, 0.2], [0.1, 0.3])


def test_a_gate_corridor_is_verified_against_the_rule_of_the_sheet_and_never_written(tree):
    """Находка проверки: коридор гейта, который правило листа ставит по результату счёта, команда переписывала одной
    строкой среди прочих — порог шёл за результатом сам. Теперь порог гейта сверяется с правилом листа и не пишется:
    расхождение — отдельный блок печати, красный флаг запуска и напоминание; поле окна фактов рядом пишется как прежде.
    Запись вывода дерева остаётся записью листа."""
    base = book_record(tree)
    assert run(tree, base, "first")[0] == R.OK
    corridor = list(base["ends"]["wholesale"])
    moved = shifted(base, mean=0.00001)
    moved["ends"]["wholesale"] = [corridor[0], round(corridor[1] + 0.02, 2)]
    code, now, printed = run(tree, moved, "gate")
    book = template(tree)
    assert code == R.OK and book["checks"]["wholesale_share"] == corridor, "коридор гейта в шаблоне не тронут"
    assert book["checks"]["window_backtest"]["means"]["nim"] == moved["ends"]["nim_mean"], "поле окна фактов записано"
    assert [c["key"] for c in now["derive"]["changes"]] == ["checks.window_backtest.means.nim"]
    assert now["derive"]["unwritten"] == [{"key": "checks.wholesale_share", "step": "ends", "rule": "коридор гейта по счёту ядра (проба)",
                                           "book": corridor, "sheet": moved["ends"]["wholesale"]}]
    flag = (f"порог гейта checks.wholesale_share: в книге {R.flow_text(corridor)}, правило листа даёт "
            f"{R.flow_text(moved['ends']['wholesale'])} — не переписан: пороги гейтов команда сверяет, но не пишет")
    assert now["flags"] == [flag]
    assert "ПОРОГИ ГЕЙТОВ: сверено с правилом листа, НЕ ПИШЕТСЯ" in printed
    assert f"checks.wholesale_share: РАСХОДИТСЯ — в книге {R.flow_text(corridor)}, правило листа даёт" in printed
    assert "ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ" in printed and "Решение ведущего: перенести порог в шаблон руками" in printed
    assert tree_record(tree) == moved and gaps(tree) == [], "сверка шаблона с записью вывода пороги гейтов не берёт"
    # повторный запуск с той же записью листа: расхождение названо снова, не пишется ничего
    after = snapshot(tree)
    code, again, printed = run(tree, moved, "gate-again")
    assert again["wrote"] == [] and snapshot(tree) == after and again["flags"] == [flag] and again["derive"]["changes"] == []
    assert ("изменений нет — все выведенные числа шаблона равны записи вывода; порогов гейтов, не равных правилу листа, — 1: "
            "не переписаны") in printed
    # разошёлся один порог гейта: шаблон не тронут, а запись вывода дерева переписана — она запись листа
    wider = copy.deepcopy(moved)
    wider["ends"]["wholesale"] = [corridor[0], round(corridor[1] + 0.03, 2)]
    text = R.read_text(tree.template)
    code, only, printed = run(tree, wider, "gate-only")
    assert only["wrote"] == ["evidence/path/" + n.split("/", 2)[2] for n in OUT] and R.read_text(tree.template) == text
    assert tree_record(tree) == wider and len(only["flags"]) == 1 and "ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ" in printed
    # ведущий перенёс коридор руками: расхождения и флага нет, команда пересобрала книгу и больше ничего не тронула
    node, _ = R.locate(yaml.compose(text, Loader=yaml.SafeLoader), ("checks", "wholesale_share"))
    R.write_text(tree.template, text[:node.start_mark.index] + R.flow_text(wider["ends"]["wholesale"]) + text[node.end_mark.index:])
    code, done, printed = run(tree, wider, "gate-moved")
    assert code == R.OK and done["flags"] == [] and done["derive"]["unwritten"] == [] and done["derive"]["changes"] == []
    assert done["wrote"] == ["assumptions.yaml", "assumptions.json"] and "— равен правилу листа" in printed
    assert "ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ" not in printed
    assert template(tree)["checks"]["wholesale_share"] == wider["ends"]["wholesale"] == tree_record(tree)["ends"]["wholesale"]


def test_a_gate_corridor_outside_its_own_limits_still_stops_the_command(tree):
    """Порог гейта не пишется, но правило листа, давшее его вне коридора описания, — по-прежнему остановка: счёт сломан."""
    record = book_record(tree)
    record["ends"]["wholesale"] = [0.1, 1.5]
    before = snapshot(tree)
    with pytest.raises(R.Stopped, match="вне коридора"):
        run(tree, record, "broken")
    assert snapshot(tree) == before


# ------------------------------------------------------------ красные флаги: каждое отклонение блока проверок

WINDOW = {"nim": {"min": 0.10, "max": 0.11, "mean": 0.105}, "cor": {"min": 0.05, "max": 0.07, "mean": 0.06},
          "cir": {"min": 0.46, "max": 0.483, "mean": 0.47}, "loans_share": {"window": 0.70, "anchor": 0.72}}
MARKS = ("ВНЕ окна", "НЕ окупает", "ВЫШЕ нормы", "НЕ выполнен", "РАСХОДИТСЯ", "ВНЕ допуска", "НАРУШЕН", "не отработал", "объяснения нет",
         "срок объяснения истёк", "масса вне коридора объяснения")


def clean_run() -> dict:
    """Запись запуска с быстрыми числами, в которой блок приёмочных проверок чист: все уровни в окне, предельный
    кредит окупает капитал во всех мирах, гейты знака выполнены, сработавший гейт объяснён, инварианты целы."""
    row = lambda title: {"title": title, "nim": 0.105, "cor": 0.06, "cir": 0.47, "roe": 0.2, "loans_share": 0.7}  # noqa: E731
    quick = {
        "book_version": "0", "book_date": "2031-02-03", "book_digest": "проба",
        "headline": {"point": 320.0, "low": 280.0, "high": 380.0, "lambda": 0.5, "median": 305.0, "band80": [230.0, 390.0],
                     "band50": [270.0, 350.0], "mean": 310.0, "market": 270.0, "p_below_market": 0.24, "median_to_market": 0.13,
                     "point_to_market": 0.185, "median_error": 3.3, "draws": 400, "seed": 1, "print_step": 5, "contributions": []},
        "layers": {},
        "checks": [{"name": "ddm_equals_ri", "kind": "invariant", "fired": False, "mass": None, "message": "", "status": None,
                    "valid_until": None},
                   {"name": "window_backtest", "kind": "gate", "fired": False, "mass": 0.0, "message": "", "status": "quiet",
                    "valid_until": None},
                   {"name": "nim_path_joint", "kind": "gate", "fired": True, "mass": 0.4, "message": "масса", "status": "explained",
                    "valid_until": "2031-06-30"}],
        "levels": {"from_year": 2030, "to_year": 2036, "cell": "H/norm/mid", "window": copy.deepcopy(WINDOW),
                   "rows": {"modal_cell": row("Модальная клетка"), "analytical": row("Свой взгляд"), "point": row("Смесь заголовка"),
                            R.LEVEL_LAYER: row("Рыночные ставки как есть")}},
        "order": None, "reference_variants": None,
        "cir_lt": {"subject": "слой", "value": 0.471, "target": 0.47, "tolerance": 0.01},
        "sign_test": {"d_point": 4.2, "d_world": {"N": 1.0, "H": 6.0}, "ok": True},
        "stress_sign": {"loss": {"step": 10.0, "cells": []}, "requirement": {"cells": []}, "max_excess": 0.0, "ok": True}}
    marginal = {"title": "предельный кредит",
                "anchor": {"model_min": 0.34, "model_max": 0.35, "segment_low": 0.34, "segment_high": 0.36, "ok": True},
                "rows": {world: [{"year": 2036, "value": 0.20, "segment_basis": None, "hurdle": 0.15}] for world in ("N", "H", "M")}}
    return {"schema": R.SCHEMA, "label": "проба", "started": "2031-02-03T10:00:00", "finished": "2031-02-03T10:05:00",
            "quick": quick, "marginal": marginal, "derive": None, "mode": {"runs": 400}, "flags": []}


def acceptance(now: dict) -> str:
    said: list[str] = []
    R.print_acceptance(now, said.append)
    return "\n".join(said)


def _level(row: str, key: str, value: float):
    return lambda now: now["quick"]["levels"]["rows"][row].update({key: value})


def _check(name: str, **fields):
    return lambda now: next(c for c in now["quick"]["checks"] if c["name"] == name).update(fields)


DEVIATIONS = [
    ("маржа слоя условий окна вне окна", _level(R.LEVEL_LAYER, "nim", 0.1205), "ВНЕ окна",
     "уровень в условиях окна фактов ВНЕ окна: ЧПМ слоя «Рыночные ставки как есть» 12,05 %"),
    ("стоимость риска слоя условий окна вне окна", _level(R.LEVEL_LAYER, "cor", 0.08), "ВНЕ окна",
     "уровень в условиях окна фактов ВНЕ окна: CoR слоя «Рыночные ставки как есть» 8,00 %"),
    ("расходы к доходам слоя условий окна вне окна", _level(R.LEVEL_LAYER, "cir", 0.50), "ВНЕ окна",
     "уровень в условиях окна фактов ВНЕ окна: C/I слоя «Рыночные ставки как есть» 50,0 %"),
    ("модальная клетка вне окна", _level("modal_cell", "cir", 0.451), "ВНЕ окна", "Модальная клетка ВНЕ окна фактов: C/I 45,1 %"),
    ("ожидание слоёв вне окна", _level("analytical", "cor", 0.04), "ВНЕ окна", "Свой взгляд ВНЕ окна фактов: CoR 4,00 %"),
    ("смесь заголовка вне окна", _level("point", "cir", 0.49), "ВНЕ окна", "Смесь заголовка ВНЕ окна фактов: C/I 49,0 %"),
    ("цель расходов к доходам вне допуска", lambda now: now["quick"]["cir_lt"].update(value=0.49), "ВНЕ допуска",
     "цель расходов к доходам (гейт cir_lt, слой) ВНЕ допуска: 49,00 % при цели 47,0 % ± 1,0 п.п."),
    ("якорь предельной экономики расходится с сегментом", lambda now: now["marginal"]["anchor"].update(model_min=0.2, ok=False),
     "РАСХОДИТСЯ", "предельная экономика роста на якоре расходится с фактом сегмента"),
    ("предельный кредит не окупает капитал в одном из миров", lambda now: now["marginal"]["rows"]["M"][-1].update(value=0.022, hurdle=0.225),
     "НЕ окупает", "предельная экономика роста, мир M: в конце сетки НЕ окупает — 2,2 % при стоимости капитала 22,5 % (2036)"),
    # решения ведущего Совкомбанка № 5, Р5-11: норма §4 — k ± 5 п.п.; выход за ВЕРХНИЙ край — тоже флаг (круг 4: мир N 22,0 % при
    #   верхнем крае 19,1 % флага не дал)
    ("предельная единица выше верхнего края нормы в одном из миров", lambda now: now["marginal"]["rows"]["N"][-1].update(value=0.22, ceiling=0.191),
     "ВЫШЕ нормы", "предельная экономика роста, мир N: в конце сетки ВЫШЕ нормы — 22,0 % при верхнем крае нормы 19,1 % (2036)"),
    ("лист предельной экономики не отработал", lambda now: now.update(marginal={"error": ["ОТКАЗ: корня нет"], "title": "лист"}),
     "не отработал", "лист предельной экономики роста не отработал: ОТКАЗ: корня нет"),
    ("гейт знака объёмных эффектов не выполнен", lambda now: now["quick"]["sign_test"].update(d_point=-9.69, ok=False), "НЕ выполнен",
     "гейт знака volume_sign НЕ выполнен: снятие остановки кредита и поправок роста меняет точку на −9,69 ₽"),
    ("гейт знака стресса не выполнен", lambda now: now["quick"]["stress_sign"].update(max_excess=12.5, ok=False), "НЕ выполнен",
     "гейт знака stress_sign НЕ выполнен: наибольшее превышение 12,5 млрд ₽"),
    ("гейт без объяснения", _check("nim_path_joint", status="unexplained", valid_until=None), "объяснения нет",
     "гейт nim_path_joint сработал без действующего объяснения (объяснения нет)"),
    ("срок объяснения гейта истёк", _check("nim_path_joint", status="expired"), "срок объяснения истёк",
     "гейт nim_path_joint сработал без действующего объяснения (срок объяснения истёк)"),
    ("масса гейта вне коридора объяснения", _check("nim_path_joint", status="mass_off"), "масса вне коридора объяснения",
     "гейт nim_path_joint сработал без действующего объяснения (масса вне коридора объяснения)"),
    ("нарушен инвариант", _check("ddm_equals_ri", fired=True, message="клетка H: расхождение 0,4 %"), "НАРУШЕН",
     "НАРУШЕН инвариант ddm_equals_ri: клетка H: расхождение 0,4 %"),
]


def test_a_clean_run_has_no_red_flags_and_no_deviation_in_the_block():
    """Чистый запуск: в блоке приёмочных проверок нет ни одного отклонения — и флагов нет; сработавший гейт с
    действующим объяснением флагом не считается. Первая строка и клетка листа решения так и говорят."""
    now = clean_run()
    block = acceptance(now)
    assert R.flags_of(now) == [] and not any(mark in block for mark in MARKS), block
    assert "объяснение действует, до 2031-06-30" in block and "(ж) гейты: сработало 1 из 2" in block
    said: list[str] = []
    R.print_flags([], said.append)
    assert said == ["КРАСНЫЕ ФЛАГИ: нет"] and R.flags_cell([]) == "красных флагов нет"
    assert "| красных флагов нет | |" in R.brief(now, None)


@pytest.mark.parametrize("name,spoil,mark,flag", DEVIATIONS, ids=[row[0] for row in DEVIATIONS])
def test_every_deviation_of_the_acceptance_block_is_a_red_flag(name, spoil, mark, flag):
    """Находка проверки: строка «красных флагов нет» стояла рядом с отклонениями того же запуска. Каждое отклонение,
    которое печатает блок приёмочных проверок, — красный флаг: слова отклонения в блоке и флаг появляются вместе."""
    now = clean_run()
    spoil(now)
    block, flags = acceptance(now), R.flags_of(now)
    assert mark in block, f"{name}: блок приёмочных проверок печатает отклонение"
    assert len(flags) == 1 and flags[0].startswith(flag), (name, flags)
    said: list[str] = []
    R.print_flags(flags, said.append)
    assert said == ["КРАСНЫЕ ФЛАГИ — 1:", "  • " + flags[0]]
    cell = R.flags_cell(flags)
    assert cell.startswith("красных флагов — 1: ") and "|" not in cell and f"| {cell} | |" in R.brief(dict(now, flags=flags), None)


def test_the_block_never_shows_a_deviation_that_is_not_a_flag():
    """Все отклонения сразу: флагов столько же, сколько отклонений (инвариант — первым), и ни одно слово отклонения в
    блоке не остаётся без флага. Число вне окна, которого у книги нет, и число, которого нет, отклонением не считаются."""
    now = clean_run()
    apart = {"лист предельной экономики не отработал", "срок объяснения гейта истёк", "масса гейта вне коридора объяснения"}
    for name, spoil, _, _ in DEVIATIONS:                 # три случая исключают соседей: они проверены поодиночке
        if name not in apart:
            spoil(now)
    flags = R.flags_of(now)
    assert len(flags) == 14 and flags[0].startswith("НАРУШЕН инвариант") and len(set(flags)) == 14
    block = acceptance(now)
    assert block.count("НЕ окупает") == 1 and block.count("НЕ выполнен") == 2 and "РАСХОДИТСЯ" in block
    # блок (б) повторяет строку слоя условий окна: её CoR и C/I уже названы флагами блока (а)
    assert block.count("ВНЕ окна") == 3 + 5 and sum("ВНЕ окна" in flag for flag in flags) == 6
    quiet = clean_run()
    quiet["quick"]["levels"]["rows"][R.LEVEL_LAYER].update(nim=0.5, cor=None)
    quiet["quick"]["levels"]["window"].update(nim={"min": None, "max": None})
    assert R.flags_of(quiet) == [] and "ВНЕ окна" not in acceptance(quiet)
    bare = clean_run()
    bare["quick"]["levels"].update(rows={}, window=None)
    bare["quick"].update(cir_lt=None, sign_test=None, stress_sign=None)
    bare["marginal"] = None
    assert R.flags_of(bare) == [] and R.flags_of({"quick": None, "derive": None}) == []


def test_the_first_line_and_the_decision_sheet_print_the_flags_by_number_and_list(tree, monkeypatch):
    """Весь путь команды на игрушечном дереве с подменёнными быстрыми числами (отклонения книги Т из отчёта проверки:
    маржа слоя условий окна и C/I модальной клетки вне окна, предельный кредит не окупает капитал в двух мирах, гейт
    знака не выполнен) и порогом гейта, не равным правилу листа: первая строка итога и клетка «Проверки» листа решения
    печатают флаги числом и перечнем; показ сохранённого запуска считает флаги по его числам заново."""
    (tree.book_dir / "results.json").unlink()                # мерки «таблицы книги» у игрушечного дерева нет
    deviant = clean_run()
    for name, spoil, _, _ in DEVIATIONS:
        if name in ("маржа слоя условий окна вне окна", "модальная клетка вне окна", "гейт знака объёмных эффектов не выполнен",
                    "предельный кредит не окупает капитал в одном из миров"):
            spoil(deviant)
    deviant["marginal"]["rows"]["H"][-1].update(value=0.132, hurdle=0.185)
    monkeypatch.setattr(R, "quick_numbers", lambda *a, **k: copy.deepcopy(deviant["quick"]))
    monkeypatch.setattr(R, "marginal_numbers", lambda *a, **k: copy.deepcopy(deviant["marginal"]))
    monkeypatch.setattr(R, "class_numbers", lambda *a, **k: {"error": None, "config": None, "checks": [], "flags": []})
    record = book_record(tree)
    record["ends"]["wholesale"] = [record["ends"]["wholesale"][0], round(record["ends"]["wholesale"][1] + 0.02, 2)]
    lines: list[str] = []
    code, now = R.run(tree=tree, label="flags", sheet=substituted(record), today=TODAY, say=lines.append)
    flags = now["flags"]
    assert code == R.OK and len(flags) == 6 and flags[0].startswith("порог гейта checks.wholesale_share: в книге ")
    assert [flag.split(":")[0].split(" ВНЕ")[0] for flag in flags[1:]] == [
        "уровень в условиях окна фактов", "Модальная клетка", "предельная экономика роста, мир H",
        "предельная экономика роста, мир M", "гейт знака volume_sign НЕ выполнен"]
    at = lines.index("КРАСНЫЕ ФЛАГИ — 6:")
    assert lines[at + 1:at + 7] == ["  • " + flag for flag in flags] and "КРАСНЫЕ ФЛАГИ: нет" not in lines
    sheet = (tree.state / "flags.md").read_text(encoding="utf-8")
    row = next(line for line in sheet.splitlines() if line.startswith("| запуск «flags» |"))
    assert "| красных флагов — 6: порог гейта checks.wholesale_share" in row and row.count("|") == 6
    assert all(" ".join(flag.split()) in row for flag in flags), "клетка «Проверки» несёт перечень флагов"
    assert "Не переписано командой — решение ведущего: порог гейта checks.wholesale_share" in sheet
    assert ("| Предельный кредит против стоимости капитала по мирам | в конце сетки: мир N — окупает; мир H — НЕ окупает; "
            "мир M — НЕ окупает | отдача выше стоимости капитала | НЕ окупает: H, M |") in sheet
    assert "ЧПМ ВНЕ окна" in sheet and "Модальная клетка: C/I" in sheet
    saved = json.loads((tree.state / "flags.json").read_text(encoding="utf-8"))
    assert saved["flags"] == flags and saved["derive"]["unwritten"][0]["key"] == "checks.wholesale_share"
    # запись запуска прежней команды несла не все флаги: показ считает их по числам записи заново
    saved["flags"] = []
    (tree.state / "flags.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    shown: list[str] = []
    assert R.show(tree.state, tree, "flags", "flags", shown.append) == R.OK
    at = shown.index("КРАСНЫЕ ФЛАГИ — 6:")
    assert shown[at + 1:at + 7] == ["  • " + flag for flag in flags] and "красных флагов — 6: " in "\n".join(shown)


def test_variant_price_rule_is_dry_rederive_for_every_variant():
    """Решения ведущего № 12, Р12-7 (поток book12; было Р11-6 — по действию: «frozen» при отходе пути слоя M не больше 0,1 %): ВСЕ
    варианты книги — «rd», цена только сухим перевыводом; категория «frozen, точка записи» упразднена — правило по действию не
    видело канала перевывода (clients_all «−0,00» против сухого −0,17 / −0,15). Замер отхода остаётся печатью."""
    dev = lambda loans, ins: {"loans": None if loans is None else {"max": loans, "q": 3},  # noqa: E731
                              "vol_ins": None if ins is None else {"max": ins, "q": 5}}
    assert R.VARIANT_PATH_TOL == 0.001 and R.VARIANT_PATH_UNTIL == 2029 and R.VARIANT_PATH_LAYER == "macro_neutral"
    for d in (dev(0.0, 0.0), dev(0.001, 0.001), dev(0.0011, 0.0), dev(0.0, 0.0011), dev(None, 0.0), dev(None, 0.002)):
        assert R.variant_rule(d) == "rd" and R.variant_rule(d, main=True) == "rd"
    assert R.variant_rule(dev(0.0002, 0.0), tol=0.0001) == "rd"
    row = {"price_rule": "rd", "main_fork": False, "path_dev": dev(0.0, 0.0)}
    assert "Р12-7" in R.variant_mark(row) and "forks_rd" in R.variant_mark(row)


def test_variant_price_rule_main_forks_of_the_charter_are_always_dry_rederive():
    """Р11-6: главные развилки устава §6 — всегда сухим перевыводом, какой бы ни был замер; описание вывода книги их называет."""
    assert R.variant_rule({"loans": {"max": 0.0, "q": 1}, "vol_ins": {"max": 0.0, "q": 1}}, main=True) == "rd"
    spec = R.load_module(BOOK / "evidence" / "path" / "derive_spec.py", "rederive_spec_main_forks")
    ids = {str(v["id"]) for v in yaml.safe_load((BOOK / "assumptions_template.yaml").read_text(encoding="utf-8"))["valuation"]["reference_variants"]}
    assert set(spec.MAIN_FORKS) <= ids and {"cor_retail_tail", "serial_acquirer", "buyback_none"} <= set(spec.MAIN_FORKS)


def test_variant_path_deviation_is_the_largest_quarterly_relative_gap_of_each_series():
    """Р11-6: замер — наибольший по кварталам модуль относительного отхода ожидания ряда варианта от центра и квартал, где он
    достигнут; ряд без чисел (нет в книге) — None."""
    base = {"loans": [100.0, 110.0, 120.0], "vol_ins": [10.0, 10.0, 10.0]}
    other = {"loans": [100.0, 110.11, 119.0], "vol_ins": [10.0, 10.0, 10.0]}
    d = R.path_deviation(base, other)
    assert d["loans"]["q"] == 3 and abs(d["loans"]["max"] - 1.0 / 120.0) < 1e-15 and d["vol_ins"]["max"] == 0.0
    assert R.path_deviation({"loans": None, "vol_ins": [1.0]}, {"loans": None, "vol_ins": [1.0]})["loans"] is None


def test_variant_price_rule_measures_the_layer_m_path_of_the_book_itself():
    """Р11-6 на книге дерева: инструмент сам меряет отход пути слоя M по полной сетке варианта (кварталы 1 … 2029К4). Вариант
    оценки за концом сетки (угасание доходности) пути не трогает; вариант плотности RWA двигает путь кредитов через капитал
    (адрес подмены — не путь кредитов: правило по адресу его пропускало). Р12-7 (поток book12): правило цены у обоих — «rd» (все
    варианты — сухим перевыводом); замер отхода — печать (было: угасание — «frozen»)."""
    from model.book import load_book, load_facts
    from model.book_results import variant_book
    from model.grid import run_grid
    from model.live import live_from_book
    facts = load_facts(ROOT / "data" / "facts")
    book = load_book(BOOK / "assumptions.json", facts=facts)
    live = live_from_book(book, facts)
    base = R.layer_paths(run_grid(book, facts, live))
    last = run_grid(book, facts, live).ctx.timeline.quarters_of_year(2029)[-1]
    assert len(base["loans"]) == last and all(x > 0 for x in base["loans"]) and base["vol_ins"] is not None
    specs = {str(v["id"]): v for v in book.get("valuation.reference_variants")}
    rules = {}
    for vid in ("fade_symmetric", "density_drift_zero"):
        d = R.path_deviation(base, R.layer_paths(run_grid(variant_book(book, specs[vid]), facts, live)))
        rules[vid] = (R.variant_rule(d), d)
    assert rules["fade_symmetric"][0] == "rd" and rules["fade_symmetric"][1]["loans"]["max"] < 1e-12   # Р12-7: было «frozen»
    assert rules["density_drift_zero"][0] == "rd" and rules["density_drift_zero"][1]["loans"]["max"] > R.VARIANT_PATH_TOL
    assert set(specs["density_drift_zero"]["overrides"]) == {"capital.rwa.density_drift_rate"}


def test_roe_window_guard_stops_only_the_book_and_prints_in_a_dry_run():
    """Решения ведущего № 12, Р12-8 (поток book12): страж отбора окон строк-долей по границе ROE (Р11-8) действует только на книгу —
    запись шаблона останавливается; в сухом прогоне (развилка как центр копии) несовпадение отбора печатается, а не останавливает:
    отбор по своей границе ROE развилки — часть её действия (его применяет инструмент развилок)."""
    spec = types.SimpleNamespace(RESIDUALS=({"step": "ends", "name": "отбор окон (проба)", "flag": ("ends", "roe_bound", "ok"),
                                             "book_only": True, "why": "проба"},), SAME=(), WRITES=())
    record = {"ends": {"roe_bound": {"ok": False}}}
    root = yaml.compose("a: 1\n", Loader=yaml.SafeLoader)
    _, bad, notes = R.check_record(spec, record, {"a": 1}, root, ["ends"])
    assert bad and "отбор окон (проба)" in bad[0]
    _, bad, notes = R.check_record(spec, record, {"a": 1}, root, ["ends"], dry_run=True)
    assert bad == [] and any("сухой прогон" in n and "Р12-8" in n for n in notes)
    record["ends"]["roe_bound"]["ok"] = True
    _, bad, notes = R.check_record(spec, record, {"a": 1}, root, ["ends"], dry_run=True)
    assert bad == [] and notes[0].startswith("ок")
    real = R.load_spec(R.Tree())
    assert [r for r in real.RESIDUALS if r.get("flag") == ("ends", "roe_bound", "ok")][0].get("book_only") is True


def test_driver_roots_follow_the_led_k6_book_and_unrouted_bundle_paths_keep_the_run_value():
    """Решения ведущего № 12, Р12-9 (поток book12): ρ выводится только у строк, которые ведут книгу К6 (volumes.liability_drivers);
    у книги — та же строка (insurance). Пути κ/ρ связки, которые запуск не выводит, остаются на конце числом книги запуска
    (было — KeyError volumes.liability_driver_roots на концах связок у k6_root_off и insurance_liab_as_funds)."""
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("sheet_r12_9", BOOK / "evidence" / "path" / "derive_on_engine.py")
    sheet = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sheet)
    book = yaml.safe_load((BOOK / "assumptions_template.yaml").read_text(encoding="utf-8"))
    rho = book["volumes"]["liability_driver_roots"]
    values = {"volumes.liability_driver_roots": rho, "volumes.liability_drivers": book["volumes"]["liability_drivers"]}

    class Eng:
        overrides: dict = {}

        def value(self, path):
            return values.get(path)

    sheet.book_opt = lambda eng, path: (values.get(path) if path in values else  # noqa: E731
                                        float(rho["insurance"][path.split(".")[-1]]))
    eng = Eng()
    assert sheet.driver_root_lines(eng) == ["insurance"]
    values["volumes.liability_drivers"] = {}
    assert sheet.driver_root_lines(eng) == []
    sheet.share_root_lines = lambda eng: []  # noqa: E731
    paths = [f"volumes.liability_driver_roots.insurance.{k}" for k in rho["insurance"] if k not in ("LT", "LT_from")]
    vals: dict = {}
    sheet.end_share_roots(eng, {"name": "проба", "paths": ["other.insurance_volume_link"] + paths}, vals, {}, "low")
    assert set(vals) == set(paths) and all(vals[p] == float(rho["insurance"][p.split(".")[-1]]) for p in paths)
