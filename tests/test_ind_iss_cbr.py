"""Сборщики рынка и ставок: MOEX ISS и ЦБ на сохранённых ответах."""

from __future__ import annotations

import json
from datetime import date

import pytest

from indicators import cbr, config, iss
from indicators.sources import OK, Context
from indicators.store import Store
from tests.support_ind import FIX, FakeGetter, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта (W1/C1)


def _json(rel):
    return json.loads((FIX / rel).read_text(encoding="utf-8"))


def test_parse_quotes_takes_last_trade_or_previous_close():
    q = iss.parse_quotes(_json("iss/quotes.json"), "TQBR")
    assert {"T", "VTBR"} <= set(q)
    for t, row in q.items():
        assert row["price"] > 0 and row["date"] and row["source"] == "iss:TQBR"


def test_parse_history_and_zcyc():
    rows, cursor = iss.parse_history_page(_json("iss/history_T_0.json"))
    assert rows[0] == {"date": "2026-04-13", "close": 3120.0}
    assert cursor is None or cursor[0] == 0
    curve = iss.parse_zcyc(_json("iss/zcyc.json"))
    assert curve["as_of"] == "2026-09-30"
    assert curve["nodes"]["1"] == pytest.approx(0.137069) and set(curve["nodes"]) == {"1", "3", "5", "10"}


def test_zcyc_in_percent_units_is_refused():
    payload = _json("iss/zcyc.json")
    payload["yearyields"]["data"] = [[r[0], r[1], r[2], r[3] * 100] for r in payload["yearyields"]["data"]]
    with pytest.raises(iss.IssError):
        iss.parse_zcyc(payload)


def test_cbr_parsers():
    kr = cbr.parse_key_rate((FIX / "cbr/key_rate.xml").read_bytes())
    assert kr == sorted(kr) and kr[-1] == ("2026-09-30", 0.14)
    s = cbr.key_rate_summary(dict(kr))
    assert s["value"] == 0.14 and s["date"] == "2026-09-30" and s["since"] <= s["date"]
    ru = cbr.parse_ruonia((FIX / "cbr/ruonia.xml").read_bytes())
    assert 0.03 < ru[-1][1] < 0.4 and ru[-1][2] > 0
    bl = cbr.parse_bliquidity((FIX / "cbr/bliquidity.xml").read_bytes())
    assert bl[-1] == ("2026-09-30", 3223.4)
    dep = cbr.parse_deposits((FIX / "cbr/deposits_top10.html").read_text(encoding="utf-8"))
    assert dep[-1] == ("2026-09-11", 0.13005)
    assert cbr.decade_date("III.08.2026") == "2026-08-21"


def test_key_rate_since_is_the_change_day():
    s = cbr.key_rate_summary({"2026-07-01": 0.15, "2026-07-27": 0.14, "2026-09-30": 0.14})
    assert s == {"value": 0.14, "date": "2026-09-30", "since": "2026-07-27"}


def _ctx(store, getter):
    return Context(store=store, today=date(2026, 10, 1), company=config.company(), cfg=config.sources(),
                   getter=getter, peer_tickers=())


def test_iss_and_cbr_collectors_write_series_and_raw(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    g = FakeGetter()
    r = iss.collect(_ctx(store, g))
    assert r.status == OK, r.reasons
    assert store.load("iss.price.T").latest().value > 0
    assert store.load("iss.zcyc.10").latest().value == pytest.approx(0.168282)
    closes = store.load("iss.close.T").history()
    # закрытия до первого торгового дня после дробления лежат в ряду уже пересчитанными (коэффициент — из фактов)
    assert closes["2026-04-16"] == pytest.approx(320.4) and closes["2026-04-17"] == 321.4
    assert max(closes.values()) < 400 and store.raw_days("iss")
    raw = next(f for f in store.raw_files("iss") if f.name.startswith("history_T"))
    assert b"3204" in store.read_raw(raw)                     # сырой ответ — как есть
    r = cbr.collect(_ctx(store, g))
    assert r.status == OK, r.reasons
    assert store.load("cbr.key_rate").latest().value == 0.14
    assert store.load("cbr.bliquidity").latest().value == 3223.4
    cbr_calls = [c for c in g.calls if "cbr.ru" in c["url"]]
    assert cbr_calls and all(c["headers"].get("SOAPAction", "").startswith("http://web.cbr.ru/")
                             for c in cbr_calls if c["data"])


def test_cbr_page_fallback_when_soap_fails(monkeypatch, tmp_path):
    from indicators import http

    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    page = b"<table><tr><td>27.07.2026</td><td>14,00</td></tr><tr><td>30.09.2026</td><td>14,00</td></tr></table>"
    g = FakeGetter(overrides={"<KeyRate": http.FetchError("x", 503, "HTTP 503"), "hd_base/KeyRate": page})
    r = cbr.collect(_ctx(store, g))
    assert store.load("cbr.key_rate").latest().value == 0.14
    assert any("страница" in x for x in r.reasons)


def test_split_adjust_divides_closes_before_the_first_trade_day():
    """Пересчёт на дробление: дата и коэффициент — только из фактов (`shares.json → corporate_actions`)."""
    rows = [{"date": "2026-04-16", "close": 3204.0}, {"date": "2026-04-17", "close": 321.4}]
    actions = config.corporate_actions(FIX / "facts")
    assert [a["kind"] for a in actions] == ["issue", "split"]
    assert iss.split_adjust(rows, actions) == [{"date": "2026-04-16", "close": pytest.approx(320.4)},
                                              {"date": "2026-04-17", "close": 321.4}]
    assert iss.split_adjust(rows, []) == rows and iss.split_adjust(rows, [{"kind": "issue", "date": "2024-08-15"}]) == rows
    node = [{"kind": "split", "factor": {"v": 10}, "first_trade_date": "2026-04-17"}]      # узел факта вместо числа
    assert iss.split_adjust(rows, node)[0]["close"] == pytest.approx(320.4)
    twice = actions + [{"kind": "split", "factor": 2, "first_trade_date": "2026-05-01"}]
    assert [r["close"] for r in iss.split_adjust(rows, twice)] == [pytest.approx(160.2), pytest.approx(160.7)]
    assert config.splits(FIX / "facts") == [{"date": "2026-04-15", "first_trade_date": "2026-04-17", "factor": 10.0}]
