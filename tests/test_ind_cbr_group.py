"""Формы банковской группы 0409805/803/802: перечень периодов, признак наличия, день первого появления, винтажи.

Фикстуры — сочинённые ответы в формате службы ЦБ (`tests/fixtures/ind/cbr_group/`).
"""

from __future__ import annotations

from datetime import date

import pytest

from indicators import cbr_group, config, http
from indicators.sources import FAILED, IRRECOVERABLE, OK, Context, verdict
from indicators.store import PROTECTED_SOURCES, Point, Store
from tests.support_ind import FIX, FakeGetter, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта


def _b(name):
    return (FIX / "cbr_group" / name).read_bytes()


def _ctx(store, getter, today):
    return Context(store=store, today=today, company=config.company(), cfg=config.sources(), getter=getter)


def test_periods_and_request_dates():
    listing = cbr_group.parse_periods(_b("periods.xml"))
    assert set(listing) == {"805", "803", "802"} and listing["805"][-1] == "202606" and len(listing["805"]) == 10
    assert cbr_group.period_of("202606") == "2026Q2" and cbr_group.dt_of("2025Q4") == "202512"
    assert cbr_group.request_stamp("202606") == "2026-06-01T00:00:00"     # первое число отчётного месяца
    assert cbr_group.parse_intcode(_b("intcode.xml")) == "1000000002673"
    with pytest.raises(cbr_group.GroupFormError):
        cbr_group.parse_periods(b"<html>stub</html>")                    # заглушка — не «новых форм нет»
    ops = [(part, op) for part, op, _ in cbr_group.form_requests("805", "2673", "202606")]
    assert ops == [("par1", "GetF805Xml"), ("par4", "GetF805Xml")]
    assert cbr_group.form_requests("803", "2673", "202606")[0][1:] == (
        "Data803FXML", "<CredorgNumber>2673</CredorgNumber><Dt>2026-06-01T00:00:00</Dt>")
    assert cbr_group.awaited(date(2026, 10, 7)) == "202609" and cbr_group.awaited(date(2026, 1, 5)) == "202512"


def test_presence_is_a_number_not_a_status_code():
    """Формы нет — ответ тоже с кодом 200: пустая строка итога и пустой раздел нормативов. Признак наличия —
    число в строке итога капитала и в Н20.0."""
    there = {"par1": _b("f805_202606_par1.xml"), "par4": _b("f805_202606_par4.xml")}
    gone = {"par1": _b("f805_absent_par1.xml"), "par4": _b("f805_absent_par4.xml")}
    assert cbr_group.present("805", there) == (True, "") and cbr_group.present("805", gone) == (False, "")
    half = {"par1": there["par1"], "par4": gone["par4"]}
    assert cbr_group.present("805", half) == (False, "есть не всё: нет Н20.0")
    assert cbr_group.present("803", {"doc": _b("f803_202606.xml")})[0]
    assert not cbr_group.present("803", {"doc": _b("f80x_absent.xml")})[0]
    assert cbr_group.present("802", {"doc": _b("f802_202606.xml")})[0]
    points = cbr_group.series_points("805", there)
    assert points == {"cbr.f805.capital_total": pytest.approx(680.0), "cbr.f805.capital_base": pytest.approx(488.0),
                      "cbr.f805.n20_0": pytest.approx(0.128), "cbr.f805.n20_1": pytest.approx(0.093),
                      "cbr.f805.n20_2": pytest.approx(0.115)}
    assert cbr_group.series_points("803", {"doc": _b("f803_202606.xml")}) == {
        "cbr.f803.ni_ytd": pytest.approx(74.0), "cbr.f803.nii_ytd": pytest.approx(252.0)}   # раздел I, не II
    assert cbr_group.series_points("802", {"doc": _b("f802_202606.xml")}) == {}
    assert cbr_group.parse_f805_norms(there["par4"])["Н20.4"] is None                        # не раскрыто — null


def test_collect_bootstrap_then_the_awaited_quarter_appears(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    # 07.10.2026: форма за третий квартал ещё не вышла — период в перечне не назван, ответ пуст
    hidden = {("CreditOrgInfo", "2026-09-01T00:00:00</dateTime><par>1"): _b("f805_absent_par1.xml"),
              ("CreditOrgInfo", "2026-09-01T00:00:00</dateTime><par>4"): _b("f805_absent_par4.xml"),
              ("CreditOrgInfo", "<Dt>2026-09-01T00:00:00"): _b("f80x_absent.xml")}
    g = FakeGetter(overrides=hidden, moment="2026-10-07T05:00:00+00:00")
    r = cbr_group.collect(_ctx(store, g, date(2026, 10, 7)))
    assert r.status == OK and not r.reasons, r.reasons            # ожидаемой формы нет — это не отказ
    index = cbr_group.load_index(store)
    assert index["internal_code"] == "1000000002673" and index["regnum"] == "2673"
    f805 = index["forms"]["805"]
    assert f805["202403"]["note"] == "до запуска сборщика" and not f805["202403"]["parsed"]
    assert f805["202606"]["parsed"] and f805["202606"]["first_seen"] is None       # вышла до запуска сборщика
    assert f805["202609"] == {"first_seen": None, "fetched": "2026-10-07T05:00:00+00:00", "parsed": False}
    assert store.load("cbr.f805.n20_0").history() == {
        "2025Q3": pytest.approx(0.118), "2025Q4": pytest.approx(0.124), "2026Q1": pytest.approx(0.129),
        "2026Q2": pytest.approx(0.128)}                           # последние периоды перечня; старше — затравка
    assert store.load("cbr.f803.ni_ytd").value_as_of("2026Q2") == pytest.approx(74.0)
    asked = "".join(c["data"].decode() for c in g.calls if c["data"])
    assert "<RegNumber>2673</RegNumber>" in asked and "<InternalCode>1000000002673</InternalCode>" in asked
    assert store.raw_days("cbr_group") and cbr_group.SOURCE in PROTECTED_SOURCES and cbr_group.SOURCE in IRRECOVERABLE

    # 20.11.2026: форма пришла с числами — день первого появления, точки рядов, событие в данных такта
    g2 = FakeGetter(moment="2026-11-20T05:00:00+00:00")
    r2 = cbr_group.collect(_ctx(store, g2, date(2026, 11, 20)))
    assert r2.status == OK and sorted(r2.data["appeared"]) == ["802:2026Q3", "803:2026Q3", "805:2026Q3"]
    assert cbr_group.first_seen(store, "805", "2026Q3") == "2026-11-20T05:00:00+00:00"
    assert cbr_group.first_seen(store, "805", "2026Q2") is None
    n20 = store.load("cbr.f805.n20_0")
    assert n20.value_as_of("2026Q3", "2026-11-19") is None and n20.value_as_of("2026Q3") == pytest.approx(0.127)
    assert not any("RegNumToIntCode" in c["headers"].get("SOAPAction", "") for c in g2.calls)   # код — из индекса
    # тот же день ещё раз — вчерашние формы не перекачиваются
    g3 = FakeGetter(moment="2026-11-20T09:00:00+00:00")
    cbr_group.collect(_ctx(store, g3, date(2026, 11, 20)))
    assert [c for c in g3.calls if "GetF805Xml" in c["headers"].get("SOAPAction", "")] == []

    # через неделю — перекачка последних периодов; изменённый ответ — новый винтаж рядом с прежним
    changed = _b("f805_202609_par4.xml").replace(b'FAKT_ZN="12.700"', b'FAKT_ZN="12.650"')
    g4 = FakeGetter(overrides={("CreditOrgInfo", "2026-09-01T00:00:00</dateTime><par>4"): changed},
                    moment="2026-11-27T05:00:00+00:00")
    r4 = cbr_group.collect(_ctx(store, g4, date(2026, 11, 27)))
    assert "805:202609" in r4.data.get("revised", [])
    n20 = store.load("cbr.f805.n20_0")
    assert n20.value_as_of("2026Q3", "2026-11-26") == pytest.approx(0.127)
    assert n20.value_as_of("2026Q3", "2026-11-27") == pytest.approx(0.1265)
    assert cbr_group.first_seen(store, "805", "2026Q3") == "2026-11-20T05:00:00+00:00"


def test_a_stub_or_a_dead_service_is_a_failure_with_a_retry(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "state")
    down = FakeGetter(overrides={"GetPeriodsOfDocuments": http.FetchError(cbr_group.URL, 503, "HTTP 503")})
    r = cbr_group.collect(_ctx(store, down, date(2026, 10, 7)))
    assert r.status == FAILED and r.retry and verdict([r]).code == 3 and verdict([r]).retry
    stub = FakeGetter(overrides={"GetPeriodsOfDocuments": b"<html>maintenance</html>"})
    r = cbr_group.collect(_ctx(store, stub, date(2026, 10, 7)))
    assert r.status == FAILED and r.retry and "не перечень" in r.detail
    page = FakeGetter(overrides={("CreditOrgInfo", "<par>4</par>"): b"<html>maintenance</html>"})
    r = cbr_group.collect(_ctx(store, page, date(2026, 10, 7)))
    assert r.reasons and all("заглушка" in x for x in r.reasons) and r.retry
    assert not cbr_group.load_index(store)["forms"]["805"]["202606"]["parsed"]       # версией заглушка не стала


def test_estimate_before_the_form_is_out(tmp_path):
    """До выхода формы: норматив банка на конец квартала плюс разность «группа − банк» на последнюю общую дату."""
    store = Store(tmp_path)
    at = "2026-08-20T07:00:00+00:00"
    store.upsert("cbr.f805.n20_0", [Point("2026Q1", 0.1299, at), Point("2026Q2", 0.1293, at)])
    store.upsert("cbr.f805.n20_1", [Point("2026Q2", 0.0940, at)])
    store.upsert("cbr.f135.n1_0", [Point("2026M06", 0.12547, at), Point("2026M09", 0.1270, "2026-10-26T07:00:00+00:00")])
    store.upsert("cbr.f135.n1_1", [Point("2026M06", 0.09094, at), Point("2026M09", 0.0890, "2026-10-26T07:00:00+00:00")])
    got = cbr_group.estimate(store, "2026Q3")
    assert got["n20_0"] == {"value": pytest.approx(0.1270 + 0.1293 - 0.12547), "bank_value": 0.1270,
                            "spread": pytest.approx(0.00383), "spread_as_of": "2026-06-30"}
    assert got["n20_1"]["value"] == pytest.approx(0.0890 + 0.0940 - 0.09094) and "n20_2" not in got
    assert cbr_group.estimate(store, "2026Q3", as_of="2026-10-20") == {}      # норматива банка ещё не было
    assert cbr_group.main(["2026"]) == 64
