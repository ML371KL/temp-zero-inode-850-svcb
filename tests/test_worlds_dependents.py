# -*- coding: utf-8 -*-
"""Сторож приёма миров ставок: книга стоит на версии своего состояния, а манифест знает всех, кто читает миры.

ЗАЧЕМ. Мир ставок семейства 850 пересобирается один раз в общем источнике (`temp-zero-inode-850-worlds`), а книга
принимает версию командой `ops/tools/adopt_worlds.py` по манифесту `data/assumptions/worlds_dependents.yaml`. Команда
пересчитывает только то, что названо в манифесте. Поэтому здесь сторожится:
  * копии файлов версии (запись, рецепт, входы, описание, надстройка) равны хэшам состояния `worlds_state.json`, а при
    доступном источнике — его файлам с правилами манифеста; ключи происхождения шаблона — индексу версии;
  * правила манифеста на мирах книги дают ровно числа шаблона (числа, зависящие от миров, — не литералы тестов, а выход
    правил: запись сменили, а числа нет — красный тест);
  * каждый лист и инструмент дерева, который читает запись миров, надстройку или их копии, назван в манифесте
    (`readers`): новый читатель миров без строки манифеста — красный тест.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "tools"))
import adopt_worlds as A  # noqa: E402

READS_WORLDS = re.compile(r"worlds_source|worlds_bank\.json|bank_overlay_draft|world_paths|worlds_state")


@pytest.fixture(scope="module")
def manifest():
    return A.load_manifest(ROOT)


@pytest.fixture(scope="module")
def source():
    try:
        return A.Source(A.find_source(None))
    except (A.Stop, OSError):
        return None                                   # CI: источника рядом нет — сверка по хэшам состояния и правилам


def test_the_book_stands_on_the_version_of_its_state(manifest, source):
    assert A.check(manifest, source, ROOT) == []


def test_the_template_names_the_record_of_the_state(manifest):
    state = A.read_state(ROOT)
    tpl = yaml.safe_load((ROOT / manifest["template"]).read_text(encoding="utf-8"))
    assert tpl["worlds"]["source"]["sha256"] == state["record_sha256"]
    assert tpl["worlds"]["source"]["record_asof"] == state["record_asof"]
    assert tpl["worlds"]["source"]["curve_date"] == tpl["meta"]["curve_as_of"] == state["curve_date"]


def test_every_reader_of_the_worlds_is_in_the_manifest(manifest):
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.py"], capture_output=True, text=True,
                           encoding="utf-8").stdout.split()
    readers = [f for f in files if not f.startswith("tests/")
               and READS_WORLDS.search((ROOT / f).read_text(encoding="utf-8", errors="ignore"))]
    missing = sorted(set(readers) - set(manifest["readers"]))
    assert not missing, f"читают миры, но не названы в манифесте (readers): {missing}"
    gone = sorted(f for f in manifest["readers"] if not (ROOT / f).exists())
    assert not gone, f"в манифесте названы несуществующие файлы: {gone}"


def test_the_manifest_steps_name_what_exists(manifest):
    ids = {s["id"] for s in A.walk_steps(manifest["steps"])}
    for s in A.walk_steps(manifest["steps"]):
        if s["kind"] == "rule":
            mod = A.load_module(ROOT / s["module"], f"guard_{s['id'].replace('-', '_')}")
            assert callable(getattr(mod, s["function"], None)), s["id"]
        if s["kind"] in ("set",):
            assert (ROOT / s["file"]).exists(), s["id"]
    for f, r in manifest["readers"].items():
        assert not r.get("step") or r["step"] in ids, (f, r.get("step"))


# ------------------------------------------------------------------ правила книги на записи 1.4 (tests/fixtures/worlds_1_4)
FIX = ROOT / "tests" / "fixtures" / "worlds_1_4"


def test_the_rules_give_the_book_0_1_numbers_on_the_record_1_4():
    """Правила книги (ops/tools/worlds_rules.py) на записи миров 1.4 и её надстройке дают числа книги 0.1 бит в бит:
    дальние ключи спредов, пути CoR и концы оси κ, мост вариантов уровня маржи. Так проверено, что правило — то самое,
    которым писались числа книги, а не подгонка под новую запись (центр премии средств читает нужду книги — его сверяет
    test_the_book_stands_on_the_version_of_its_state)."""
    import worlds_rules as W
    ctx = W.tree_ctx(ROOT, FIX / "worlds_source.json", FIX / "worlds_bank.json")
    want = json.loads((FIX / "rules_book_0_1.json").read_text(encoding="utf-8"))["rules"]
    assert A.sha256_bytes((FIX / "worlds_source.json").read_bytes()) == want_sha("1.4")
    for name, numbers in want.items():
        got = {".".join(map(str, k)) if isinstance(k, tuple) else k: v for k, v in W.RULES[name](ctx)["values"].items()}
        assert got == numbers, name


def want_sha(v: str) -> str:
    return {"1.4": "7296567d5200b5599efd0989de6ed8c8461d56c5c5dda244ab7d622303969fec"}[v]


def test_the_far_spread_rule_is_the_stage1_sheet_rule():
    """Дальние ключи: s_y = c + остаток 4 кв. + (a − 1) · середина полугодий опоры года, LT — последнее полугодие; книги
    активов с наклоном 1 от миров не зависят."""
    import worlds_rules as W
    world = {"key_rate": {"2028H1": 0.10, "2028H2": 0.12, "2029H1": 0.09, "2029H2": 0.09, "2030H1": 0.08, "2030H2": 0.08,
                          "2036H2": 0.07}}
    books = {"x": {"side": "asset", "ref": "key"}, "y": {"side": "asset", "ref": "key"}, "z": {"side": "liability", "ref": "key"}}
    joint = {"joint": {"x": {"a": 0.5, "c": 0.02}, "y": {"a": 1.0, "c": 0.03}, "z": {"a": 0.8, "c": -0.01}},
             "resid_last4_joint": {"x": 0.001, "y": -0.002, "z": 0.0}}
    far = W.far_spread_values(world, books, joint, "2036H2")
    assert far == {"x": {"2028": -0.034, "2029": -0.024, "2030": -0.019, "LT": -0.014},
                   "y": {"2028": 0.028, "2029": 0.028, "2030": 0.028, "LT": 0.028}}


def test_the_engine_bumps_the_book_version_once_per_worlds_version(tmp_path):
    """Номер книги при приёме — младший разряд + 1; повтор приёма той же версии номер не двигает (неподвижная точка)."""
    assert A.bump("0.1") == "0.2" and A.bump("1.9") == "1.10" and A.bump("3") == "4"
    prev = {"version": "1.7", "book": {"from": "0.1", "version": "0.2", "from_worlds": "1.4", "from_commit": "abc"}}
    assert A.book_block(tmp_path, {"book_version": "meta.version"}, prev, "1.7") == prev["book"]
    assert A.book_block(tmp_path, {}, prev, "1.8") is None


def test_the_engine_writes_numbers_inside_lists(tmp_path):
    """Точечная запись правила — и в элементы списков (оси полосы, варианты), с адресом-кортежем; соседний текст цел."""
    f = tmp_path / "t.yaml"
    f.write_text("a:\n  axes:\n    - {name: x, low: {k.1: 0.5, k.2: 1.0}}   # конец\n    - {name: y, low: {k.1: 2.0}}\n",
                 encoding="utf-8")
    ch = A.set_values(f, {("a", "axes", 0, "low", "k.2"): 1.25, ("a", "axes", 1, "low", "k.1"): 2.0}, {("a", "axes", 0, "low", "k.2"): 6})
    assert ch == {"a.axes.0.low.k.2": (1.0, 1.25)}
    assert f.read_text(encoding="utf-8").splitlines()[2] == "    - {name: x, low: {k.1: 0.5, k.2: 1.25}}   # конец"
