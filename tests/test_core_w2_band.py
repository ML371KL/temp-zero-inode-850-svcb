"""Сдвиг положения оси и диагностика осей вне полосы (М§10) — на фикстуре формы образца.

Тест считает сетки на концах осей и малую полосу — секунды: в набор такта сервера он не входит (цель времени
набора — ops/budgets.json), идёт в CI и в полном прогоне. Остальные тесты того же раздела —
`tests/test_core_w2.py`.
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest

from model import uncertainty as U
from model.checks import check_gates
from model.grid import run_grid
from model.timeline import make_timeline
from tests.support_core import fixture_book, fixture_facts
from tests.test_core_w2 import _live


def test_mean_shift_and_the_off_band_diagnostic():
    """М§10: сдвиг положения оси = (цена_high + цена_low − 2 × точка) / 6; Σ по осям вне полосы — диагностика
    и гейт `off_band_shift` (|Σ| > print_step / 2); у книги со всеми осями в полосе гейт молчит."""
    book, facts = fixture_book(), fixture_facts()
    live = _live(book, make_timeline(book).end(0) + timedelta(days=30))
    run = run_grid(book, facts, live)
    assert book.get("valuation.uncertainty.off_band_axes") == []
    quiet = next(x for x in check_gates(run) if x.name == "off_band_shift")
    assert not quiet.fired and quiet.mass == 0.0
    assert U.off_band_shift(book, facts, live, run.point) == {
        "rub": 0.0, "limit": float(book.get("valuation.headline.print_step")) / 2, "axes": 0}
    axes = copy.deepcopy(book.get("valuation.uncertainty.axes"))
    names = ("Налог: сдвиг ставки", "ERP")
    off = [a for a in axes if a["name"] in names]
    assert len(off) == 2
    few = [a for a in axes if a["name"] not in names][:3] + [a for a in axes if a["kind"] == "dict"][:1]
    b2 = book.with_overrides({"valuation.uncertainty.axes": few, "valuation.uncertainty.off_band_axes": off})
    run2 = run_grid(b2, facts, live)
    assert run2.point == run.point
    shifts = []
    for ax in off:
        lo = run_grid(U.trial_book(b2, U.axis_overrides(b2, ax, -1.0)), facts, live).point
        hi = run_grid(U.trial_book(b2, U.axis_overrides(b2, ax, 1.0)), facts, live).point
        shifts.append((hi + lo - 2 * run.point) / 6)
        assert U.mean_shift(run.point, lo, hi) == pytest.approx(shifts[-1], rel=1e-12)
    diag = U.off_band_shift(b2, facts, live, run2.point)
    assert diag["axes"] == 2 and diag["rub"] == pytest.approx(sum(shifts), rel=1e-12)
    assert shifts[0] < 0                                               # налоговая ось односторонняя — тянет вниз
    f = next(x for x in check_gates(run2) if x.name == "off_band_shift")          # без диагностики — считает сам
    assert f.fired == (abs(sum(shifts)) > diag["limit"]) and f.detail["rub"] == pytest.approx(sum(shifts))
    for rub, fired in ((diag["limit"] * 1.01, True), (-diag["limit"] * 1.01, True), (diag["limit"] * 0.99, False)):
        g = next(x for x in check_gates(run2, off_band={**diag, "rub": rub}) if x.name == "off_band_shift")
        assert g.fired == fired and g.mass == (1.0 if fired else 0.0) and "вне полосы" in g.message
    band = U.band(b2, facts, live, draws=4, workers=1)
    rows = U.judgements(b2, facts, live, band, point=run2.point)
    out = [r for r in rows if not r["in_band"]]
    assert len(out) == 2 and all(r["share"] is None and r["rank_corr"] is None for r in out)
    assert sum(r["mean_shift"] for r in out) == pytest.approx(diag["rub"], rel=1e-12)
    assert U.off_band_shift(b2, facts, live, run2.point, rows)["rub"] == pytest.approx(diag["rub"], rel=1e-12)
    for r in rows:
        if r["kind"] == "dict":
            assert r["mean_shift"] is None
        else:
            assert r["mean_shift"] == pytest.approx((r["price_high"] + r["price_low"] - 2 * run2.point) / 6)
        assert r["source"] == f"book-{b2.get('meta.version')}, ось „{r['name']}“"       # у JSON-книги комментариев нет


def test_judgement_source_is_the_book_comment_without_marks(tmp_path):
    text = (
        "valuation:                       # оценка (MODEL §8)\n"
        "  erp: 0.0557                    # A-V2: премия за риск [Ф: решение владельца 30.09.2026; ось 0,049–0,062]\n"
        "  beta_e: 0.83                   # A-V1: бета, недели [Р: market — 0,826, se 0,053, n 157;\n"
        "                                 #   окна 2 года 0,835, 5 лет 0,996 без 24.02–31.03.2022; ось 0,70–1,05]\n"
        "  terminal:\n"
        "    fade: 1.0                    # угасание избыточной доходности\n"
        "tax:\n"
        "  one_off: {year: 2027, amount: 200.0, prob: 0.0}   # разовый налог [В: DESIGN §4 — P 0–30 % × 100–300; центр 0]\n"
        "  statutory: {\"2026\": 0.25, LT: 0.25}   # явные оси tax.statutory и tax.one_off [В]\n"
        "# ---------------- раздел\n"
        "other:\n"
        "  misc_net_real: {LT: -200.0}    # «прочее», млрд ₽ в год\n"
        "    # отдельная строка, не продолжение\n"
    )
    path = tmp_path / "book.yaml"
    path.write_text(text, encoding="utf-8")
    book = copy.copy(fixture_book())
    object.__setattr__(book, "path", path)
    notes = U.book_notes(book)
    assert notes["valuation.erp"].startswith("A-V2") and "окна 2 года" in notes["valuation.beta_e"]
    assert "раздел" not in " ".join(notes.values()) and "отдельная строка" not in notes["other.misc_net_real"]
    src = lambda paths, name="ось": U.judgement_source(book, {"paths": paths, "name": name}, notes)  # noqa: E731
    assert src(["valuation.erp"]) == "решение владельца 30.09.2026; ось 0,049–0,062"
    # по границе фразы, ≤ 80; фраза с датой без года («24.02») — служебный текст (П§0.2), опускается
    assert src(["valuation.beta_e"]) == "market — 0,826, se 0,053, n 157; ось 0,70–1,05"
    assert src(["valuation.terminal.fade"]) == "угасание избыточной доходности"       # нет метки — текст комментария
    assert src(["tax.one_off.prob"]) == "DESIGN §4 — P 0–30 % × 100–300; центр 0"    # поиск по префиксу пути
    assert src(["other.misc_net_real.LT"]) == "«прочее», млрд ₽ в год"
    version = book.get("meta.version")
    assert src(["tax.statutory"], "Налог") == f"book-{version}, ось „Налог“"          # служебные имена — не источник
    assert src(["valuation.headline.print_step"], "Шаг") == f"book-{version}, ось „Шаг“"    # выше 2-го уровня не ищет
    long = U.source_text("[Р: " + "слово " * 30 + "]")
    assert len(long) <= 80 and long.endswith("…")
    assert U.source_text("A-N2: ЧПМ сквозь цикл [В]") == "A-N2: ЧПМ сквозь цикл"
    assert U.book_notes(fixture_book()) == {}
