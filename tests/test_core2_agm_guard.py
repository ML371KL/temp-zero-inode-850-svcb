"""Сторож заголовка на стыке квартала собрания и экс-даты (М§14.4) — два сценария с несколькими выпусками подряд.

Каждый сценарий собирает несколько быстрых выпусков — секунды: в набор такта сервера они не входят (цель времени
набора — ops/budgets.json), идут в CI и в полном прогоне. Остальные тесты сторожа заголовка — в такте
(`tests/test_core2_w2.py`, `tests/test_core2_w3.py`, `tests/test_core2_payload.py`).
"""

from __future__ import annotations

import copy
from datetime import timedelta

import pytest

from model import payload as P
from model.grid import run_grid
from model.timeline import make_timeline
from tests.support_core import fixture_book, fixture_facts
from tests.test_core2_w2 import _payload, _register_row
from tests.test_core2_w3 import _flag, _release


def test_jump_guard_is_silent_across_the_agm_quarter_end_and_the_ex_date():
    """№ 12 (М§14.4): на E_qA дивиденд переходит из V0 в мост, на экс-дате уходит из моста — сторож смотрит
    V0 + B с поправкой на экс-даты и молчит на всей цепочке E_qA − 1 → E_qA → экс-дата − 1 → экс-дата."""
    book, facts = fixture_book(), fixture_facts()
    tl = make_timeline(book)
    year = tl.anchor_year
    end = tl.end(tl.index(f"{year + 1}Q{book.get('dividends.calendar.agm_quarter')}"))
    ex = end + timedelta(days=18)
    base = run_grid(book, facts)
    policy = sum(c.dps_policy[year] for c in base.cells) / len(base.cells)
    dps = round(1.02 * policy, 2)                                   # объявлено на 2 % выше политики
    reg = [_register_row(year, dps, ex)]
    days = [end - timedelta(days=1), end, ex - timedelta(days=1), ex]
    prev, chain = None, []
    for day in days:
        rel, d = _payload(day, reg, prev)
        chain.append((rel, d))
        prev = d
    amount = dps * chain[0][0].run.shares_out / 1000
    limit = float(book.get("valuation.headline.jump_guard.v0_pct"))
    for i in range(1, len(chain)):
        jg = chain[i][1]["fair_value"]["jump_guard"]
        assert jg["reason"] == "within_limit", (days[i], jg)
        assert abs(jg["v0_change"]) < 0.01 and abs(jg["median_change"]) < 0.01
        inv = next(x for x in chain[i][1]["checks"]["invariants"] if x["name"] == "jump_guard")
        assert inv["ok"] and "в пределах порога" in inv["detail"]
    v0 = [d["layers"]["analytical"]["v0"] for _, d in chain]
    bridge = [d["fair_value"]["bridge"]["amount"] for _, d in chain]
    pend = [d["fair_value"]["bridge"]["pending_dividend"] for _, d in chain]
    assert bridge == pytest.approx([0.0, amount, amount, 0.0], abs=0.01)
    assert pend == pytest.approx([amount, 0.0, 0.0, 0.0], abs=0.01)
    drop = v0[1] / v0[0] - 1                                         # один V0 падает на вычтенный дивиденд
    assert drop == pytest.approx(-amount / v0[0], abs=2e-3) and abs(drop) > 0.6 * limit
    jg_end = chain[1][1]["fair_value"]["jump_guard"]
    assert jg_end["v0_agm_adjustment"] == 0.0 and jg_end["exdate_adjustment"] == 0.0
    jg_ex = chain[3][1]["fair_value"]["jump_guard"]
    assert jg_ex["exdate_adjustment"] == pytest.approx(dps, abs=0.01)
    assert jg_ex["v0_agm_adjustment"] == pytest.approx(0.0, abs=0.02)        # мост прошлого выпуска − дивиденд экс-даты
    med = [d["fair_value"]["headline"]["median"] for _, d in chain]
    assert med[3] - med[2] == pytest.approx(-dps, abs=0.5)                   # скачок на экс-дату = −DPS
    assert abs(chain[1][0].run.point - chain[0][0].run.point) < 1e-3 * chain[1][0].run.point   # E_qA: перекат


def test_jump_guard_is_silent_across_the_agm_quarter_end_without_a_register_record():
    """М§14.4: без записи реестра клетки на E_qA вычитают дивиденд модели сами; сторож сравнивает V0 + B + U
    (U — этот дивиденд) и медиану с u на акцию — и молчит на цепочке E_qA − 1 → E_qA → E_qA + 30 дней; об
    отсутствующей записи сообщает флаг `dividend_register`, а не сторож."""
    book = fixture_book()
    tl = make_timeline(book)
    agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
    end = tl.end(agm_q)
    days = [end - timedelta(days=1), end, end + timedelta(days=30)]
    prev, chain = None, []
    for day in days:
        rel, d = _release(day, previous=prev)
        chain.append((rel, d))
        prev = d
    limit = float(book.get("valuation.headline.jump_guard.v0_pct"))
    u = [d["fair_value"]["jump_guard"]["unregistered_dividend"] for _, d in chain]
    u_ps = [d["fair_value"]["jump_guard"]["unregistered_dps"] for _, d in chain]
    assert u[0] == 0.0 and u[1] > 0 and u[2] == pytest.approx(u[1], rel=0.02) and u_ps[1] > 0
    v0 = [d["layers"]["analytical"]["v0"] for _, d in chain]
    drop = v0[1] / v0[0] - 1
    assert drop == pytest.approx(-u[1] / v0[0], abs=2e-3) and abs(drop) > 0.6 * limit       # один V0 упал бы за порог
    for i, roll in ((1, 0.002), (2, 0.02)):                # за день — перекат дня, за 30 дней — перекат месяца
        jg = chain[i][1]["fair_value"]["jump_guard"]
        assert jg["reason"] == "within_limit", (days[i], jg)
        assert abs(jg["v0_change"]) < roll and abs(jg["median_change"]) < roll + 0.01
        inv = next(x for x in chain[i][1]["checks"]["invariants"] if x["name"] == "jump_guard")
        assert inv["ok"]
    med = [d["fair_value"]["headline"]["median"] for _, d in chain]
    assert med[1] + u_ps[1] == pytest.approx(med[0], rel=0.02)
    # об отсутствующей записи сообщает флаг реестра (тревога) — после конца квартала ГОСА
    assert _flag(chain[2][1], "dividend_register")["raised"] and not _flag(chain[0][1], "dividend_register")["raised"]
    assert any("реестра" in a for a in P.alerts(*chain[2]))
    # проверка, что тест видит именно поправку U: «прошлый U», завышенный на дивиденд, даёт скачок за порогом
    bare = copy.copy(chain[1][0])
    stale = copy.deepcopy(chain[0][1])
    stale["fair_value"]["jump_guard"]["unregistered_dividend"] = u[1]
    stale["fair_value"]["jump_guard"]["unregistered_dps"] = u_ps[1]
    bare.previous = stale
    jg = P.build_payload(bare)["fair_value"]["jump_guard"]
    assert abs(jg["v0_change"]) > 0.6 * limit
