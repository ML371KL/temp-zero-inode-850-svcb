"""Строки чувствительности выпуска — оценщик срединных прогонов (М§8.3, §10) — на фикстуре формы образца.

Тест считает три малые полосы (книга и две сдвинутые книги) — секунды: в набор такта сервера он не входит (цель
времени набора — ops/budgets.json), идёт в CI и в полном прогоне. Остальные тесты выпуска того же раздела —
`tests/test_core2_w3.py`.
"""

from __future__ import annotations

import pytest

from model import payload as P
from model import uncertainty as U
from model.grid import bank_language, live_from_book
from tests.support_core import fixture_book, fixture_facts
from tests.support_core2 import sensitivity_rows


def test_bank_language_sensitivities_are_the_estimator_of_the_middle_draws():
    """М§8.3, §10: строки «₽ за 0,1 п.п. CoR / ЧПМ» и «₽ за 1 п.п. ROE» — оценщик срединных прогонов (среднее
    попарных сдвигов прогонов с рангом в окне), а не разность двух медиан; сдвиг уровня CoR доходит до кредитов
    по СС."""
    book, facts = fixture_book(), fixture_facts()
    live = live_from_book(book, facts)
    x, rows = sensitivity_rows(book, facts, live, 6, workers=1)
    rel, run, band = x.rel, x.run, x.band
    window = U.rank_window(rel.book)
    s = rel.sensitivities
    assert len(rows) == P.LAMBDA_STEPS + 1
    for lam, at in zip(P._lambda_grid(run.lam), rows):
        base = band.exact_centres(lam)
        for kind in ("cor", "nim"):
            shift = U.median_shift(base, s[kind]["band"].exact_centres(lam), window)
            assert at[f"rub_per_01pp_{kind}"] == pytest.approx(shift * 0.001 / s[kind]["step"], abs=0.006)
        assert at["rub_per_01pp_cor"] < 0 < at["rub_per_01pp_nim"]
        d_roe = bank_language(s["nim"]["run"], lam)["roe_tc"] - bank_language(run, lam)["roe_tc"]
        shift = U.median_shift(base, s["nim"]["band"].exact_centres(lam), window)
        assert at["rub_per_1pp_roe"] == pytest.approx(shift / d_roe * s["roe_pp"], abs=0.006)
    # опора FVC стоит на значениях книги (М§4.6): на сдвинутой книге FVC клеток больше
    assert s["cor"]["run"].ctx.book.base is rel.book.base and s["cor"]["band"].s == band.s     # те же точки гиперкуба
    tl = run.ctx.timeline
    a, b = run.cells[0], s["cor"]["run"].cells[0]
    assert b.quarters["fvc"][tl.Q] > a.quarters["fvc"][tl.Q]
