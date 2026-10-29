"""T-Invest: токен только из окружения, разбор ответов, в выпуск — только агрегаты целей брокеров.

Фикстуры — синтетика в формате ответа T-Invest: условия брокера запрещают публиковать ответы API.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from indicators import config, tinvest
from indicators.sources import MISSING, OK, Context
from indicators.store import Store
from tests.support_ind import FAKE_TOKEN, FIX, FakeGetter, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта


def _json(name):
    return json.loads((FIX / "tinvest" / name).read_text(encoding="utf-8"))


def _ctx(store, getter=None):
    return Context(store=store, today=date(2026, 10, 26), company=config.company(), cfg=config.sources(),
                   getter=getter, peer_tickers=tuple(config.peer_tickers()))


def test_quotation_and_last_prices():
    assert tinvest.quotation({"units": "272", "nano": 700000000}) == pytest.approx(272.7)
    assert tinvest.quotation(None) is None
    p = tinvest.parse_last_prices(_json("last_prices.json"))
    main = p[_json("shareby_T.json")["instrument"]["uid"]]
    assert main == {"price": pytest.approx(319.5), "date": "2026-10-26", "time": "12:53", "ticker": "T"}


def test_dividend_records_by_year_and_without_a_period():
    """Годовой реестр: год прибыли — год реестра минус лаг. Квартальный: периода брокер не отдаёт — год и
    период пусты, их присваивает реестр; DPS — как в ответе. Запись в валюте в реестр не идёт."""
    annual = tinvest.parse_dividends(_json("dividends_T.json"))
    last = annual[-1]
    assert last["dps"] == pytest.approx(4.7) and last["record_date"] == "2026-10-12"
    assert last["ex_date"] == last["record_date"] and last["year"] == 2025 and last["status"] == "declared"
    assert last["last_buy_date"] == "2026-10-09" and last["pay_date"] == "2026-10-26"
    assert last["decided_date"] is None                   # дата решения в ответе ненадёжна (М§15)
    assert last["sources"] == ["T-Invest"]                # слово источника реестра
    assert tinvest.parse_dividends(_json("dividends_T.json"), profit_year_lag=0)[-1]["year"] == 2026
    rows = tinvest.parse_dividends(_json("dividends_T.json"), period_rule="quarterly")
    assert [r["record_date"] for r in rows] == ["2026-01-08", "2026-05-25", "2026-08-10", "2026-10-12"]
    assert all(r["year"] is None and r["period"] is None for r in rows)
    assert [r["dps"] for r in rows] == [pytest.approx(x) for x in (3.6, 4.5, 4.6, 4.7)]
    foreign = {"dividends": [
        {"dividendNet": {"currency": "usd", "units": "0", "nano": 24000000}, "recordDate": "2021-03-24T00:00:00Z"},
        {"dividendNet": {"currency": "RUB", "units": "4", "nano": 700000000}, "recordDate": "2026-10-12T00:00:00Z"},
        {"dividendNet": {"units": "4", "nano": 600000000}, "recordDate": "2026-08-10T00:00:00Z"}]}
    assert [(r["record_date"], r["dps"]) for r in tinvest.parse_dividends(foreign, period_rule="quarterly")] == [
        ("2026-08-10", pytest.approx(4.6)), ("2026-10-12", pytest.approx(4.7))]


def test_reports_deduplicated_and_brokers_aggregated():
    reports = tinvest.parse_reports(_json("reports_T.json"))
    assert [r["date"] for r in reports if r["year"] == 2026 and r["num"] == 2] == ["2026-08-11"]
    agg = tinvest.brokers_aggregate(_json("forecast_T.json"), as_of="2026-10-26")
    assert agg["n"] == 5 and agg["min"] == 290 and agg["max"] == 420 and agg["median"] == 380
    assert agg["recommendations"] == {"buy": 3, "hold": 1, "sell": 1}
    assert "Брокер" not in json.dumps(agg, ensure_ascii=False)           # имена и цели по брокерам не выходят


def test_no_token_means_missing_source(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path, token=False)
    g = FakeGetter()
    r = tinvest.collect(_ctx(Store(tmp_path / "state"), g))
    assert r.status == MISSING and not g.calls


def test_collect_writes_series_and_keeps_the_token_out_of_files(monkeypatch, tmp_path):
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    g = FakeGetter()
    r = tinvest.collect(_ctx(store, g))
    assert r.status == OK, r.reasons
    assert store.load("tinvest.price.T").latest().value == pytest.approx(319.5)
    assert store.load("tinvest.price.T").latest().note == "12:53"
    assert store.load("tinvest.price.VTBR").latest().value == pytest.approx(81.5)       # цена аналога
    held = store.read_state("tinvest/dividends.json")["by_ticker"]["T"]
    assert held[-1]["dps"] == pytest.approx(4.7) and held[-1]["period"] is None        # реестр ведётся по кварталам
    assert store.read_state("tinvest/brokers_T.json")["n"] == 5
    assert all(c["headers"]["Authorization"] == "Bearer " + FAKE_TOKEN for c in g.calls)
    for f in state.rglob("*"):
        if f.is_file():
            assert FAKE_TOKEN.encode() not in f.read_bytes(), f
    assert store.raw_days("tinvest")
