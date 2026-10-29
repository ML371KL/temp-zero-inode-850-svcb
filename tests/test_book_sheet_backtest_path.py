# -*- coding: utf-8 -*-
"""Лист приёмки «бэктест пути маржи» (устав §5 1(б) в редакции решений ведущего № 12, Р12-5; поток book12):
data/assumptions/evidence/nii/backtest_path.py. (i) — совместный подбор листа этапа 1 механикой панели воспроизводит запись листа
этапа 1; (ii) — путь ЧПМ банка в модели на наклонах ядра (book_slopes) и ρ книг, определение «c подбором» (уровень — подбором на
окне; лист решения № 12, С-2), «старт от якоря» (квартал якоря — факт) — справочно; описание вывода зовёт этот лист приёмкой
§5 1(б)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NII = ROOT / "data" / "assumptions" / "evidence" / "nii"


def _sheet():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(NII))
    spec = importlib.util.spec_from_file_location("sheet_backtest_path", NII / "backtest_path.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_path_backtest_joint_fit_reproduces_stage1_and_the_model_path_starts_at_the_anchor():
    from model.book import load_book, load_facts
    from model.nii import book_slopes, solve_transmission
    from model.credit import bridge_from_facts
    bt = _sheet()
    facts = load_facts(ROOT / "data" / "facts")
    book = load_book(None, facts=facts)
    res = bt.backtest_path(book, facts)
    for key, (title, _) in bt.LEGS.items():                 # (i): плечи листа этапа 1 — та же механика панели
        assert abs(res["legs_joint"][key]["max_abs"] - res["stage1_legs_joint"][title]) < 1e-12
    assert res["anchor"] == "2026Q2" and abs(res["nim_path"]["2026Q2"] - res["nim_actual"]["2026Q2"]) < 1e-12
    core = book_slopes(book, facts, solve_transmission(book, facts, bridge_from_facts(facts)))
    assert all(res["slope_model"][b] == core[b] for b in bt.BOOKS)
    rows = bt.rows_of(res)
    assert len(rows) == 9 and [r["ok"] for r in rows[:8]] == [r["value"] <= bt.NORM for r in rows[:8]]
    assert all("(i)" in r["name"] for r in rows[:4]) and all("(ii)" in r["name"] for r in rows[4:8])
    old = bt.BB.backtest(book, facts)["legs"]                # (ii) приёмки — «c подбором» (С-2); от якоря — справочно в словах
    for r, (key, _) in zip(rows[4:8], bt.LEGS.items()):
        assert r["value"] == old[key]["max_abs"] and "подбором на окне" in r["name"]
        assert f"старт от якоря {bt.pp(res['legs_path'][key]['max_abs'])}" in r["words"]
        if not r["ok"]:                                       # отклонение — с ценой обеих развилок передачи (Р12-5а, С-1)
            assert "на верху оси" in r["words"] and "середина трёх прочтений (−0,025)" in r["words"]
    spec = (ROOT / "data" / "assumptions" / "evidence" / "path" / "derive_spec.py").read_text(encoding="utf-8")
    assert '"sheet": "../nii/backtest_path.py"' in spec and '"sheet": "../nii/backtest_books.py"' not in spec
