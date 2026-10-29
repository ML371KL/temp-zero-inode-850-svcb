# -*- coding: utf-8 -*-
"""Команда перевывода книги `ops/tools/rederive.py`: точечная запись выведенных чисел в шаблон, остановки и сухой
прогон. Лист вывода здесь не запускается (минуты): на его месте — запись вывода, лежащая в дереве, и её правленые
копии («подменённый расчёт»); быстрые числа (сетка и полоса) эти тесты не считают. Что команда на книге дерева не
меняет ни одного числа, держит запись вывода дерева: описание рядом с листом, шаблон и запись обязаны сходиться.
В рабочую копию тесты не пишут: запуск с записью идёт только на копии книги и фактов во временном каталоге, на самом
дереве — только сухой прогон."""
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
SHEET_DIR = BOOK / "evidence" / "path"
TODAY = dt.date(2031, 2, 3)                      # дата пометки в тестах: в шаблоне её быть не может
TRACKED = ("assumptions_template.yaml", "assumptions.yaml", "assumptions.json", "evidence/path/out/derive_out.json",
           "evidence/path/out/derive_out.txt", "evidence/path/out/derive_start.json")


def _load():
    spec = importlib.util.spec_from_file_location("tool_rederive", ROOT / "ops" / "tools" / "rederive.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = _load()


def committed_record() -> dict:
    return json.loads((SHEET_DIR / "out" / "derive_out.json").read_text(encoding="utf-8"))


def substituted(record: dict):
    """Подменённый расчёт: вместо запуска листа — готовая запись (все шаги описания)."""
    def sheet(tree, spec, book, work, *, serial, workers, say, centre_only=False):
        steps = list(spec.PHASES[0]["steps"]) if centre_only else list(spec.STEPS)
        got = {k: v for k, v in copy.deepcopy(record).items() if not centre_only or k not in ("ends", "need")}
        return got, [{"name": "centre" if centre_only else "all", "steps": steps, "seconds": 0.0,
                      "evaluations": record.get("evaluations")}], "печать подменённого расчёта\n"
    return sheet


def snapshot(book_dir: Path) -> dict[str, bytes]:
    return {name: (book_dir / name).read_bytes() for name in TRACKED}


BASE = committed_record()["keys"]                       # числа записи вывода дерева (книга Совкомбанка, круг 3)
# Решения ведущего № 3, Р2: корни расходов — 2026 (правило года якоря) и один переходный 2027–2029; с 2030 года и LT — 0
# (коридор описания LT 0…0). Сдвиг «в единицу знака» — у ключа 2026 года (было — LT).
# Решения ведущего № 4, Р4-3 (поток book4): у корней расходов — квартальные ключи 2027 года (ступени периметра 2027К1, 2027К2 сверх
# корня группы) без ключа года; корень группы 2027–2029 — ключи 2027К3…2029 (здесь — ключ 2028 года)
OPEX_G0, OPEX_26 = BASE["opex.real_growth"]["2028"], BASE["opex.real_growth"]["2026"]
OPEX_GROUP = [k for k in BASE["opex.real_growth"] if k not in ("2026", "LT", "LT_from")]
# порог гейта доли опта в книге — как в шаблоне дерева (решения ведущего Совкомбанка № 5, Р5-11: перенесён по правилу листа на
# [0,08; 0,26]); тесты судят, что команда его сверяет и НЕ пишет, а не само число
WHOLESALE_BOOK = yaml.safe_load((BOOK / "assumptions_template.yaml").read_text(encoding="utf-8"))["checks"]["wholesale_share"]
FEES_26 = BASE["fees.growth_vs_wages"]["2026"]
OPEX_26_MOVED, FEES_26_MOVED = round(OPEX_26 - 0.0001, 4), round(FEES_26 - 0.0001, 4)


def moved_record() -> dict:
    """Запись вывода с другими корнями расходов и другим вычетом якоря — в коридорах описания (числа дерева — из его записи
    вывода: корни расходов 2027–2029 года и 2026 года, вычет якоря Н1.0, спред комиссий 2026 года; корень и спред 2026 года — сдвиг
    в единицу знака)."""
    record = committed_record()
    keys = record["keys"]
    for year in OPEX_GROUP:
        keys["opex.real_growth"][year] = 0.0131
    keys["opex.real_growth"]["2026"] = OPEX_26_MOVED      # сдвиг в единицу знака: пишется вместе с ключом
    keys["capital.n20.deductions_anchor"] = 25.7
    keys["fees.growth_vs_wages"]["2026"] = FEES_26_MOVED  # сдвиг в единицу знака: пишется, как любое отличие
    record["ends"]["wholesale_share"]["corridor"] = [0.07, 0.41]
    return record


@pytest.fixture()
def tree(tmp_path):
    """Копия книги и фактов дерева: команда пишет в неё, а не в рабочую копию."""
    root = tmp_path / "tree"
    keep = {"path", "nii"}                        # лист вывода и листы приёмки бэктеста маржи (описание: ACCEPTANCE)
    shutil.copytree(BOOK, root / "data" / "assumptions", ignore=lambda d, names: (
        {n for n in names if n not in keep and n != "README.md"} if Path(d) == BOOK / "evidence"
        else {n for n in names if n == "__pycache__"}))
    shutil.copytree(ROOT / "data" / "facts", root / "data" / "facts")
    return R.Tree(root=root)


# ------------------------------------------------------------ описание рядом с листом


def test_the_description_names_the_steps_of_the_sheet_and_a_corridor_for_every_number():
    """Описание не знает шагов сверх листа; фазы покрывают все шаги листа; у каждого числа записи вывода дерева есть
    коридор, и оно в нём лежит; запись вывода дерева на шаблоне дерева не меняет ни одного числа."""
    spec = R.load_spec(R.Tree())
    steps = set(spec.STEPS)
    assert {e["step"] for e in spec.WRITES + spec.SAME + spec.RESIDUALS} <= steps
    assert {s for p in spec.PHASES for s in p["steps"]} == steps
    assert [p["name"] for p in spec.PHASES if not p.get("after")] == ["centre"]
    assert all(p["after"] == "centre" and p["take"] for p in spec.PHASES if p.get("after"))
    text = R.read_text(R.Tree().template)
    record = committed_record()
    items, bad, notes = R.check_record(spec, record, yaml.safe_load(text), yaml.compose(text, Loader=yaml.SafeLoader),
                                       sorted(steps))
    assert bad == [] and all(line.startswith("ок") or "сходимость" in line for line in notes), (bad, notes)
    assert len(items) == len(spec.WRITES) and not any(item.rewrite or item.jitter for item in items)
    assert sum(len(item.leaves) for item in items) > 100, "траектории сверяются по каждому числу"
    assert {r["id"] for r in yaml.safe_load(text)["valuation"]["reference_variants"]} >= {"funds_premium_need"}
    new_text, marks = R.patch(text, items, "03.02.2031")
    assert new_text == text and marks == []


# ------------------------------------------------------------ точечная запись


def test_the_point_edit_keeps_every_comment_and_changes_only_the_planned_keys():
    """Правка шаблона — только места чисел: строки без выведенного ключа совпадают знак в знак, комментарии целы,
    разобранный шаблон отличается ровно намеченными ключами и ровно на намеченные значения; дата пометки обновлена
    у переписанного ключа и не тронута у остальных."""
    spec, text = R.load_spec(R.Tree()), R.read_text(R.Tree().template)
    record = moved_record()
    items, bad, _ = R.check_record(spec, record, yaml.safe_load(text), yaml.compose(text, Loader=yaml.SafeLoader),
                                   list(spec.STEPS))
    assert bad == []
    new_text, marks = R.patch(text, items, TODAY.strftime("%d.%m.%Y"))
    old, new = yaml.safe_load(text), yaml.safe_load(new_text)
    want = copy.deepcopy(old)
    want["opex"]["real_growth"].update({**{k: 0.0131 for k in OPEX_GROUP}, "2026": OPEX_26_MOVED})
    want["capital"]["n20"]["deductions_anchor"] = 25.7
    want["fees"]["growth_vs_wages"]["2026"] = FEES_26_MOVED   # единица последнего знака: число пишется, а не пропускается
    # решения ведущего № 10, Р10-16: коридор wholesale_share описание книги отдаёт команде (GATE_RULES) — пишется по правилу листа
    want["checks"]["wholesale_share"] = [0.07, 0.41]
    assert new["checks"]["wholesale_share"] == [0.07, 0.41], "коридор гейта из GATE_RULES пишется по правилу листа (Р10-16)"
    assert [(item.where, item.new) for item in items if item.gap] == []
    assert [item.where for item in items if item.gate_rule and item.written] == ["checks.wholesale_share"]
    assert new == want and old["fees"]["growth_vs_wages"]["2026"] == FEES_26
    before, after = text.splitlines(), new_text.splitlines()
    assert len(before) == len(after)
    touched = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    heads = sorted(before[i].split("#")[0].strip().split(":")[0] or "#" for i in touched)
    assert heads == ["#", "#", "#", "deductions_anchor", "growth_vs_wages", "real_growth", "wholesale_share"], heads   # четыре ключа и три строки с пометкой
    comment = lambda line: line[line.index("#"):] if "#" in line else ""  # noqa: E731
    dated = [i for i in touched if "НА ЯДРЕ" in before[i]]
    assert len(dated) == 3 and all("ВЫВЕДЕНО НА ЯДРЕ 03.02.2031" in after[i] for i in dated) and len(marks) == 3
    assert all(comment(before[i]) == comment(after[i]) for i in touched if i not in dated), "комментарии целы"
    assert new_text.count("ВЫВЕДЕНО НА ЯДРЕ 03.02.2031") == 3
    assert new_text.count("#") == text.count("#") and len(new_text) - len(text) < 40
    assert not any(item.jitter for item in items), "поодиночке числа не пропускаются: шаблон после записи равен записи вывода"
    assert R.record_gaps(spec, record, yaml.compose(new_text, Loader=yaml.SafeLoader), list(spec.STEPS)) == []


def test_numbers_are_written_the_way_the_template_writes_them():
    assert [R.number_text(v) for v in (1.0, 0.7, -0.0064, -0.009995, 123.182, 2030, -0.0, 0.048160000000000004)] == \
        ["1.0", "0.7", "-0.0064", "-0.009995", "123.182", "2030", "0.0", "0.04816"]
    assert R.flow_text({"2026Q3": -0.0064, "2026": 0.5, "LT": 0.0, "LT_from": 2030, "opex.volume_link": 0.3}) == \
        '{"2026Q3": -0.0064, "2026": 0.5, LT: 0.0, LT_from: 2030, opex.volume_link: 0.3}'
    assert yaml.safe_load(R.flow_text({"2026": 1.5, "no": 2.0})) == {"2026": 1.5, "no": 2.0}, "ключ читается строкой"
    with pytest.raises(R.Stopped):
        R.number_text("0.5")


def test_a_trajectory_with_other_keys_is_rewritten_whole_and_a_wrong_address_is_refused():
    text = ("a:\n  path: {\"2026\": 1.0, LT: 2.0}   # [Р] ВЫВОДИТСЯ НА ЯДРЕ — правило\n  rows:\n"
            "    - {id: x, low: 0.1}   # первый\n    - {id: y, low: 0.2}   # второй\n")
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    entry = {"step": "s", "address": ("a", "path"), "unit": 0.1, "rule": "правило", "mark": True,
             "corridor": [("*", 0.0, 9.0, "проба")]}
    item = R.plan_item(root, entry, {"2026": 1.0, "2027": 1.5, "LT": 2.0})
    assert item.rewrite and item.leaves[0].whole and R.corridor_breaks(item) == []
    row = R.plan_item(root, {"step": "s", "address": ("a", "rows", {"id": "y"}, "low"), "unit": 0.1, "rule": "конец",
                             "corridor": [("", 0.0, 1.0, "проба")]}, 0.3)
    new_text, marks = R.patch(text, [item, row], "03.02.2031")
    assert yaml.safe_load(new_text) == {"a": {"path": {"2026": 1.0, "2027": 1.5, "LT": 2.0},
                                              "rows": [{"id": "x", "low": 0.1}, {"id": "y", "low": 0.3}]}}
    assert "# [Р] ВЫВЕДЕНО НА ЯДРЕ 03.02.2031 — правило" in new_text and "# первый" in new_text and "# второй" in new_text
    assert len(marks) == 1
    for address in (("a", "nowhere"), ("a", "rows", {"id": "z"}, "low"), ("a", "rows", 7), ("a", "path", {"id": "x"})):
        with pytest.raises(R.Stopped):
            R.locate(root, address)
    with pytest.raises(R.Stopped, match="нет коридора"):
        R.corridor_breaks(R.plan_item(root, {**entry, "corridor": [("LT", 0.0, 9.0, "только LT")]}, {"2026": 1.0, "LT": 2.0}))


# ------------------------------------------------------------ остановки на подменённом расчёте


@pytest.mark.parametrize("spoil,words", [
    (lambda r: r["convergence"].update(converged=False), "сходимость связанных шагов"),
    (lambda r: r["keys"]["opex.real_growth"].update({"2027": 0.5}), "вне коридора"),
    (lambda r: r["keys"].update({"capital.n20.deductions_anchor": 500.0}), "вне коридора"),
    (lambda r: r["frozen_check"]["levels"]["opex"].update({"2029": 0.01}), "уровень к своей базе"),
    (lambda r: r["anchor"].update(n20_ok=False), "якорь воспроизводит Н1.0"),
    (lambda r: r["level"].update(world="M"), "суждение записано в двух местах"),
    (lambda r: r["keys"].update({"nii.phi_split": 0.8}), "вне своей оси"),
    (lambda r: r["ends"].pop("level_axes"), "в записи листа нет узла"),
])
def test_the_command_stops_and_writes_nothing(spoil, words, tree, capsys):
    """Подбор не сошёлся, число вне коридора, невязка правила, суждение листа разошлось с книгой, центр вне своей
    оси, в записи нет узла — остановка с названной причиной; ни шаблон, ни книга, ни запись вывода не тронуты
    (запуск — с записью, на копии дерева)."""
    record = committed_record()
    spoil(record)
    before = snapshot(tree.book_dir)
    with pytest.raises(R.Stopped):
        R.run(tree=tree, quick=False, label="stop", sheet=substituted(record), today=TODAY)
    assert snapshot(tree.book_dir) == before
    printed = capsys.readouterr().out
    assert "ОСТАНОВКА — в шаблон не записано ничего" in printed and words in printed, printed[-1500:]
    saved = json.loads((tree.state / "stop.json").read_text(encoding="utf-8"))
    assert saved["exit_code"] == R.STOPPED and any(words in line for line in saved["derive"]["stopped"])


def test_the_command_line_answers_a_stop_with_code_one(tmp_path, monkeypatch, capsys):
    record = committed_record()
    record["convergence"]["converged"] = False
    monkeypatch.setattr(R, "run_sheet", substituted(record))
    assert R.main(["--dry-run", "--no-quick", "--label", "stop", "--dir", str(tmp_path / "runs")]) == R.STOPPED
    assert "ОСТАНОВКА" in capsys.readouterr().err
    assert R.main(["--show", "нет-такой", "--dir", str(tmp_path / "runs")]) == R.BAD_INPUT
    assert R.main(["--dry-run", "--no-quick", "--label", "latest", "--dir", str(tmp_path / "runs")]) == R.BAD_INPUT


# ------------------------------------------------------------ сухой прогон и запись


def test_the_dry_run_writes_nothing_into_the_tree(tmp_path, capsys):
    """Сухой прогон печатает, что изменилось бы, и собирает пробную книгу в каталоге запуска; дерево цело."""
    before = snapshot(BOOK)
    listing = sorted(p.relative_to(BOOK).as_posix() for p in BOOK.rglob("*") if "__pycache__" not in p.parts)
    code, now = R.run(dry_run=True, quick=False, label="dry", state=tmp_path / "runs", sheet=substituted(moved_record()),
                      today=TODAY)
    assert code == R.OK and now["wrote"] == [] and snapshot(BOOK) == before
    assert sorted(p.relative_to(BOOK).as_posix() for p in BOOK.rglob("*") if "__pycache__" not in p.parts) == listing
    printed = capsys.readouterr().out
    assert "СУХОЙ ПРОГОН" in printed and f"{OPEX_G0} → 0.0131" in printed and "сухой прогон — файлы дерева не тронуты" in printed
    trial = yaml.safe_load((tmp_path / "runs" / "dry" / "after" / "assumptions.yaml").read_text(encoding="utf-8"))
    assert trial["opex"]["real_growth"]["2028"] == 0.0131 and trial["worlds"]["overlay"]["sha256"]
    saved = json.loads((tmp_path / "runs" / "dry.json").read_text(encoding="utf-8"))
    written = [c for c in saved["derive"]["changes"] if c["written"]]
    # Р10-16: коридор wholesale_share книга отдаёт команде (GATE_RULES описания) — пишется, как всякое выведенное число
    assert {c["key"] for c in written} == {"opex.real_growth", "capital.n20.deductions_anchor", "fees.growth_vs_wages",
                                           "checks.wholesale_share"}
    assert [c["key"] for c in saved["derive"]["changes"] if not c["written"]] == []
    assert saved["derive"]["unwritten"] == [], "порогов, которые сверяются и не пишутся, у книги нет (Р10-16)"
    assert trial["checks"]["wholesale_share"] == [0.07, 0.41] and len(saved["flags"]) == 0


def test_the_trial_of_the_centre_writes_nothing_and_leaves_the_axis_ends_alone(tree, capsys):
    """Пробный счёт решения: лист выводит только центр, книга — пробная (новый центр, прежние концы осей), дерево
    не тронуто даже без ключа сухого прогона; записи шагов, которых не было, в план не входят."""
    before = snapshot(tree.book_dir)
    code, now = R.run(tree=tree, centre_only=True, quick=False, label="trial", sheet=substituted(moved_record()), today=TODAY)
    assert code == R.OK and now["wrote"] == [] and now["mode"]["dry_run"] and snapshot(tree.book_dir) == before
    assert {c["key"] for c in now["derive"]["changes"] if c["written"]} == {"opex.real_growth", "capital.n20.deductions_anchor",
                                                                            "fees.growth_vs_wages"}
    assert "ends" not in now["derive"]["steps"] and "need" not in now["derive"]["steps"]
    trial = yaml.safe_load((tree.state / "trial" / "after" / "assumptions.yaml").read_text(encoding="utf-8"))
    assert trial["opex"]["real_growth"]["2028"] == 0.0131 and trial["checks"]["wholesale_share"] == WHOLESALE_BOOK
    assert "ПРОБНЫЙ СЧЁТ ЦЕНТРА" in capsys.readouterr().out
    for clash in ({"serial": True}, {"derive": False}):
        with pytest.raises(R.Refused):
            R.run(tree=tree, centre_only=True, quick=False, label="clash", sheet=substituted(moved_record()), **clash)


def test_on_the_book_of_the_tree_the_command_changes_nothing(tree, tmp_path, capsys):
    """Запись вывода дерева на шаблоне дерева: «изменений нет» — в сухом прогоне на самом дереве и при записи на
    его копии."""
    before, copied = snapshot(BOOK), snapshot(tree.book_dir)
    assert before == copied
    for where, dry in ((R.Tree(), True), (tree, False)):
        code, now = R.run(tree=where, dry_run=dry, quick=False, label=f"same-{dry}", state=tmp_path / "runs",
                          sheet=substituted(committed_record()), today=TODAY)
        assert code == R.OK and now["wrote"] == [] and now["derive"]["changes"] == []
        assert now["book"]["template_sha256"] == now["book"]["template_sha256_before"]
    assert snapshot(BOOK) == before and snapshot(tree.book_dir) == copied
    assert capsys.readouterr().out.count("изменений нет — все выведенные числа шаблона равны записи вывода") == 2


def test_the_write_rebuilds_the_book_and_the_record_and_the_second_run_changes_nothing(tree, tmp_path, capsys):
    """Запись: шаблон, машинная книга (схема пройдена) и запись вывода рядом с листом — одним запуском; повторный
    запуск с той же записью листа не меняет ничего; без подбора команда только пересобирает устаревшую книгу."""
    record = moved_record()
    before = snapshot(tree.book_dir)
    code, now = R.run(tree=tree, quick=False, label="write", sheet=substituted(record), today=TODAY)
    assert code == R.OK and set(now["wrote"]) == {"assumptions_template.yaml", "assumptions.yaml", "assumptions.json",
                                                   "evidence/path/out/derive_out.json", "evidence/path/out/derive_out.txt",
                                                   "evidence/path/out/derive_start.json"}
    after = snapshot(tree.book_dir)
    # запись старта — числа шаблона ДО вывода: если прошлая запись дерева тоже стартовала с них (перевывод, который поменял только
    # пороги гейтов, — поток book4, cir_lt), файл совпадает байт в байт законно; его содержание сверяется ниже
    assert all(after[name] != before[name] for name in TRACKED if name != "evidence/path/out/derive_start.json")
    book = yaml.safe_load(after["assumptions.yaml"].decode("utf-8"))
    assert book["opex"]["real_growth"]["2029"] == 0.0131 and book["capital"]["n20"]["deductions_anchor"] == 25.7
    assert json.loads(after["assumptions.json"].decode("utf-8")) == book
    assert json.loads(after["evidence/path/out/derive_out.json"].decode("utf-8")) == record
    start = json.loads(after["evidence/path/out/derive_start.json"].decode("utf-8"))
    assert start["keys"] == start["before"] and start["keys"]["opex.real_growth"]["2029"] == OPEX_G0, "старт — числа до вывода"
    assert set(start["keys"]) == set(record["keys"])
    assert b"\r" not in after["assumptions_template.yaml"] and not list(tree.book_dir.glob("*.rederive-tmp"))
    assert "ОСТАЛОСЬ СДЕЛАТЬ РУКАМИ" in capsys.readouterr().out
    code, again = R.run(tree=tree, quick=False, label="again", sheet=substituted(record), today=TODAY)
    assert code == R.OK and again["wrote"] == [] and snapshot(tree.book_dir) == after
    assert again["derive"]["changes"] == [], "после записи шаблон равен записи вывода: повторный запуск отличий не находит"
    # шаблон поправили руками мимо сборки: без подбора команда пересобирает книгу и больше ничего не трогает
    text = R.read_text(tree.template).replace("erp: 0.0557", "erp: 0.0561")
    R.write_text(tree.template, text)
    code, plain = R.run(tree=tree, derive=False, quick=False, label="plain", today=TODAY)
    assert code == R.OK and plain["wrote"] == ["assumptions.yaml", "assumptions.json"] and plain["derive"] is None
    assert yaml.safe_load(tree.book_yaml.read_text(encoding="utf-8"))["valuation"]["erp"] == 0.0561
    assert R.read_text(tree.template) == text


def test_a_book_that_fails_the_schema_is_not_written(tree, capsys):
    """Выведенные числа, с которыми книга не проходит схему (ключ года — не среднее кварталов), в дерево не попадают."""
    record = committed_record()
    record["keys"]["regimes.near_nim_shift"]["2027Q1"] = -0.0125
    before = snapshot(tree.book_dir)
    with pytest.raises(R.Stopped, match="не проходит схему"):
        R.run(tree=tree, quick=False, label="schema", sheet=substituted(record), today=TODAY)
    assert snapshot(tree.book_dir) == before


# ------------------------------------------------------------ фазы листа

FAKE_SHEET = '''# -*- coding: utf-8 -*-
import argparse, json, os, sys
from pathlib import Path
ap = argparse.ArgumentParser()
for name in ("--book", "--facts", "--steps", "--out", "--start"):
    ap.add_argument(name)
a = ap.parse_args()
steps = a.steps.split(",")
mode = os.environ.get("FAKE_SHEET_MODE", "")
if mode == "not-ready":
    print("ядро ещё не исполняет ветви книги")
    sys.exit(2)
if mode == "fail" and "ends" in steps:
    print("ОТКАЗ вывода: корня нет")
    sys.exit(1)
out = {"evaluations": {"cells": len(steps), "grids": 10 * len(steps)}}
if a.start:
    out["keys"] = json.loads(Path(a.start).read_text(encoding="utf-8"))["keys"]
    if mode == "drift" and "ends" in steps:
        out["keys"] = {"x": 2.0}
else:
    out.update(keys={"x": 1.0}, splits={"axis_phi": [0.0, 1.0], "phi_split": 0.5}, convergence={"converged": True})
if "ends" in steps:
    out.update(ends={"window": [1, 2]}, splits={"axis_phi": [0.3, 1.0]})
if "need" in steps:
    out["need"] = {"level": 0.05}
print("шаги:", a.steps)
Path(a.out).write_text(json.dumps(out), encoding="utf-8")
'''


@pytest.fixture()
def fake(tmp_path):
    tree = R.Tree(root=tmp_path / "tree")
    tree.sheet_dir.mkdir(parents=True)
    tree.facts.mkdir(parents=True)
    (tree.sheet_dir / "fake_sheet.py").write_text(FAKE_SHEET, encoding="utf-8")
    spec = types.SimpleNamespace(SHEET="fake_sheet.py", STEPS=("centre_a", "centre_b", "ends", "need"), PHASES=(
        {"name": "centre", "title": "центр", "steps": ("centre_a", "centre_b"), "after": None},
        {"name": "ends", "title": "концы", "steps": ("ends",), "after": "centre", "take": (("ends",), ("splits", "axis_phi"))},
        {"name": "need", "title": "проверка", "steps": ("need",), "after": "centre", "take": (("need",),)}))
    work = tmp_path / "work"
    work.mkdir()
    return tree, spec, work


def test_the_phases_of_the_sheet_fold_into_the_record_of_one_run(fake, monkeypatch):
    """Фазы после центра стартуют с его записи; в общую запись идут названные узлы фаз, счёт прогонов складывается;
    один запуск со всеми шагами — одна фаза."""
    tree, spec, work = fake
    said: list[str] = []
    record, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=said.append)
    assert record == {"keys": {"x": 1.0}, "splits": {"axis_phi": [0.3, 1.0], "phi_split": 0.5}, "convergence": {"converged": True},
                      "ends": {"window": [1, 2]}, "need": {"level": 0.05}, "evaluations": {"cells": 4, "grids": 40}}
    assert [p["name"] for p in phases] == ["centre", "ends", "need"] and all(p["seconds"] >= 0 for p in phases)
    assert "— фаза ends: концы —" in printed and "шаги: need" in printed
    one, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=True, workers=2, say=said.append)
    assert [p["name"] for p in phases] == ["all"] and one["need"] == {"level": 0.05} and "шаги: centre_a,centre_b,ends,need" in printed
    centre, phases, printed = R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=said.append,
                                          centre_only=True)
    assert [p["name"] for p in phases] == ["centre"] and "ends" not in centre and centre["splits"]["axis_phi"] == [0.0, 1.0]
    assert centre["evaluations"] == {"cells": 2, "grids": 20} and "ends" not in printed


@pytest.mark.parametrize("mode,error,words", [("drift", "Stopped", "её ключи не равны ключам центра"),
                                               ("fail", "Stopped", "корня нет"), ("not-ready", "Refused", "ядро ещё не")])
def test_a_phase_that_recomputes_the_centre_or_fails_stops_the_command(fake, monkeypatch, mode, error, words):
    tree, spec, work = fake
    monkeypatch.setenv("FAKE_SHEET_MODE", mode)
    with pytest.raises(getattr(R, error), match=words):
        R.run_sheet(tree, spec, work / "book.yaml", work, serial=False, workers=2, say=lambda line: None)


# ------------------------------------------------------------ итог и лист решения


def test_the_tables_of_the_book_serve_as_the_first_baseline_and_the_brief_has_the_four_sections(tmp_path):
    """Без прошлого запуска мерка — таблицы книги; блок листа решения несёт разделы 2, 2а, 3 и 4 шаблона семейства;
    сравнение двух запусков печатает разности."""
    tables = R.results_as_run(R.Tree())
    results = json.loads((BOOK / "results.json").read_text(encoding="utf-8"))
    assert tables["quick"]["headline"]["point"] == results["headline"]["point"]
    assert R.baseline(R.Tree(), tmp_path / "нет", None, "x")["label"] == tables["label"]
    now = copy.deepcopy(tables)
    now.update(label="проба", flags=[], derive={"ran": True, "changes": [{"key": "opex.real_growth", "written": True}]},
               marginal={"title": "проба", "anchor": {"model_min": 0.34, "model_max": 0.35, "segment_low": 0.34, "segment_high": 0.36,
                                                      "ok": True},
                         "rows": {"M": [{"year": 2036, "value": 0.02, "segment_basis": 0.14, "hurdle": 0.22}]}})
    now["quick"]["headline"].update(point=320.0, median=305.0, median_error=1.5, point_to_market=0.18, median_to_market=0.12)
    now["quick"]["order"] = {"fair_pb": 1.1, "market_pb": 0.9, "roe_tc": 0.2, "k_tc": 0.19,
                             "years": {"2026": {"roe": 0.27, "eps": 77.0, "pe_point": 4.2, "pe_median": 4.0, "pe_market": 3.5}}}
    text = R.brief(now, tables)
    for head in ("## 2. Заголовок", "## 2а. Пробные счёты этого круга", "## 3. Приёмочные проверки чисел", "## 4. Развилки с ценой"):
        assert head in text, head
    assert "305,00 / 320,00 ₽" in text and "| Уровни в условиях окна фактов |" in text and "| Предельная экономика роста |" in text
    assert text.count("\n| ") > 15 and "opex.real_growth" in text
    # Строка варианта без цены (его нет в записи сухого перевывода — d_point пуст, Д1) не роняет ни лист, ни печать
    # проверок: идёт после строк с ценой и несёт свою причину.
    gone = copy.deepcopy(now)
    probe = gone["quick"]["reference_variants"][0]
    probe.update(point=None, d_point=None, why="без цены: проба причины")
    section = R.brief(gone, tables).split("## 4. Развилки с ценой", 1)[1]
    cells = [line.rsplit(" | ", 2)[-2] for line in section.splitlines() if line.startswith("| ") and line.count(" | ") >= 2]
    without = [cell.startswith("без цены") for cell in cells]
    assert any(without) and without == sorted(without), cells
    assert f"| {probe['title']} | без цены: проба причины | |" in section
    said_v: list[str] = []
    R.print_acceptance(gone, said_v.append)
    assert any(probe["title"] in line and line.endswith("— без цены: проба причины") for line in said_v), said_v
    rows = {title: (old, new) for title, old, new, _ in R.compare_rows(now, tables)}
    assert rows["точка, ₽"] == (results["headline"]["point"], 320.0) and rows["медиана, ₽"][1] == 305.0
    said: list[str] = []
    R.print_compare(now, tables, said.append)
    R.print_acceptance(now, said.append)
    printed = "\n".join(said)
    assert "БЫЛО → СТАЛО против «таблицы книги (results.json)»" in printed and "ПРЕДВАРИТЕЛЬНО" in printed
    assert "(а) уровни в условиях окна фактов" in printed and "(ж) гейты: сработало" in printed
    (tmp_path / "runs").mkdir()
    for run in (dict(tables, label="first", finished="2031-02-03T10:00:00"), dict(now, label="second", finished="2031-02-03T11:00:00")):
        (tmp_path / "runs" / f"{run['label']}.json").write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    assert R.latest_run(tmp_path / "runs")["label"] == "second" and R.latest_run(tmp_path / "runs", but="second")["label"] == "first"
    assert R.show(tmp_path / "runs", R.Tree(), "second", "first", said.append) == R.OK
    assert "БЫЛО → СТАЛО против «first»" in "\n".join(said)
