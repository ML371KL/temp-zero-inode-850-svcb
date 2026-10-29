"""Такт индикаторов целиком на фикстурах: CLI, нау-каст с записью журнала, выходы для выпуска."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone

import pytest

from indicators import collect, http, outputs, record, sources, tinvest
from indicators import register as reg
from indicators.journal import Journal
from indicators.store import Store
from tests.support_ind import FAKE_TOKEN, FakeGetter, use_fixtures

pytestmark = pytest.mark.tact  # быстрые тесты такта

TODAY = date(2026, 10, 26)
MOMENT = "2026-10-26T06:00:00+00:00"
EXPECTATION = {"period": "2026Q3", "ni_q": 55.0, "nim_q_mgmt": 0.1120, "cor_q_mgmt": 0.0490}
TICKERS = ["T"]


def test_empty_state_never_raises_and_says_why(monkeypatch, tmp_path):
    state = use_fixtures(monkeypatch, tmp_path)
    out = outputs.release_inputs(tickers=TICKERS, peer_tickers=["VTBR"], state_dir=state, today=TODAY)
    assert {f.name for f in fields(outputs.IndicatorOutputs)} >= {"prices", "curve", "journal", "collector", "ops_months"}
    assert out.prices == {"T": ()} and out.curve is None and out.key_rate is None
    assert out.nowcast is None and out.register == () and out.brokers is None
    assert out.ras_months == () and out.ops_months == () and out.form102 == ()
    assert out.journal["entries"] == [] and out.admission["status"] == "collecting"
    assert out.admission["first_event"] and out.admission["earliest_decision"]
    assert any("цена T" in d for d in out.collector["degraded"])
    assert all(t["status"] == "missing" and t["reason"] for t in out.tiles)
    # причину плитки печатает витрина — словами, без идентификаторов рядов
    reasons = {t["id"]: t["reason"] for t in out.tiles}
    assert reasons["ops_loans_gross"] == "данных ещё нет: месячный релиз эмитента"
    assert reasons["f805_n20_0"] == "данных ещё нет: ЦБ, форма 0409805"
    assert not [x for x in reasons.values() if re.search(r"[a-z]\.[a-z]|_", x)]
    # срок решения за первый открытый квартал прошёл, записи нет — флаг реестра поднят словами книги
    flag = out.flags["dividend_register"]
    assert flag["raised"] and flag["detail"].startswith("нет записи реестра за первый квартал 2026 года к сроку решения")
    assert not (state / "journal.sqlite").exists()                    # только чтение


def _run_all(monkeypatch, tmp_path):
    state = use_fixtures(monkeypatch, tmp_path)
    g = FakeGetter(moment=MOMENT)
    code = collect.main(["collect"], getter=g, today=TODAY)
    assert code in (0, 3)
    monkeypatch.setenv("TINVEST_TOKEN", FAKE_TOKEN)                  # вечерний такт — новый процесс со своим токеном
    assert collect.main(["daily-indicators"], getter=g, today=TODAY) in (0, 3)
    store = Store(state)
    code = collect.run_nowcast(store, TODAY, expectation=EXPECTATION, book_version="1.0",
                               to_mgmt_nim=lambda v: v + 0.004)
    return state, store, code


def test_full_tact_and_release_inputs(monkeypatch, tmp_path):
    state, store, code = _run_all(monkeypatch, tmp_path)
    report = store.read_state("collector_report.json")
    assert report["mode"] == "daily-indicators" and report["sources"]["iss"] == "ok"
    assert report["sources"]["cbr_forms"] in ("ok", "degraded")        # формы не на все даты в фикстурах
    assert report["sources"]["tinvest"] == "ok" and report["sources"]["cbr_group"] == "ok"
    assert report["sources"]["issuer_docs"] == "ok" and report["sources"]["news"] == "ok"
    # в выпуск причины идут с названием сборщика словами; отчёт такта хранит имена сборщиков
    shown = outputs.release_inputs(tickers=TICKERS, state_dir=state, today=TODAY).collector["degraded"]
    assert not [d for d in shown if re.match(r"[a-z_]+: ", d)]
    assert outputs.degraded_words(["cbr_forms: форма 102: HTTP 500", "cbr_group: x", "issuer_docs: y", "прочее"]) == [
        "формы ЦБ: форма 102: HTTP 500", "формы банковской группы: x", "документы эмитента: y", "прочее"]
    assert set(outputs.COLLECTOR_WORDS) == set(sources.COLLECTORS) | {"release_watch", "register"}

    now = store.read_state("nowcast.json")
    assert now["period"] == "2026Q3" and now["horizon"] == "T-30" and now["book_version"] == "1.0"
    assert [t["key"] for t in now["targets"]] == ["ni_q", "nim_q", "cor_q"]
    assert now["targets"][0]["title"] == "Операционная прибыль акционеров за квартал (определение эмитента)"
    assert now["targets"][0]["basis"] == "mgmt"
    by = now["quarter"]["by_target"]
    # моста прибыли нет: прогноз всех целей равен ожиданию модели, вес оценки — ноль
    for key, name in (("ni_q", "ni_q"), ("nim_q", "nim_q_mgmt"), ("cor_q", "cor_q_mgmt")):
        assert by[key]["forecast"] == by[key]["expectation"] == EXPECTATION[name] and by[key]["w"] == 0.0, key
        assert by[key]["ras_estimate"] is None and by[key]["bridge"] is None and by[key]["ras_bridged"] is None, key
    assert now["quarter"]["months"] == [] and now["quarter"]["months_known"] == 0
    assert by["ni_q"]["basis"] == "mgmt" and "ожидание модели" in now["status"]["ni_q"]
    assert now["f102_nii"]["months_known"] == 2 and 0.08 < now["f102_nii"]["value"] < 0.15
    j = Journal(state / "journal.sqlite", readonly=True)
    rows = {r["target"]: r for r in j.forecasts()}
    assert {(r["target"], r["horizon"]) for r in rows.values()} == {("ni_q", "T-30"), ("nim_q", "T-30"), ("cor_q", "T-30")}
    assert all(r["benchmarks"]["model"] for r in rows.values())
    # эталоны журнала: модель, прошлый квартал, год назад × рост, гайденс роста года; у ЧПМ — форма 0409102
    assert set(rows["ni_q"]["benchmarks"]) == {"model", "prev_quarter", "same_quarter_last_year", "yoy_growth", "guidance"}
    assert rows["ni_q"]["benchmarks"]["guidance"] == pytest.approx(rows["ni_q"]["benchmarks"]["same_quarter_last_year"] * 1.2)
    assert rows["nim_q"]["benchmarks"]["f102_nii"] == pytest.approx(now["f102_nii"]["value"])
    assert "ras_bridge" not in rows["ni_q"]["benchmarks"] and "guidance" not in rows["nim_q"]["benchmarks"]
    assert j.frozen("ni_q", "2026Q3", "bridge") is None and j.frozen("nim_q", "2026Q3", "f102_profile")
    # эмитент ЧПМ года числом не называет — напоминания о гайденсе нет, код нау-каста чистый
    assert code == 0 and now["notes"] == []
    assert {r["book_version"] for r in rows.values()} == {"1.0"} and {r["release_sha"] for r in rows.values()} == {"0" * 12}
    collect.run_nowcast(store, TODAY, expectation={**EXPECTATION, "ni_q": 60.0})
    assert len(j.forecasts()) == 3                                     # повторный нау-каст новых строк не пишет

    out = outputs.release_inputs(tickers=TICKERS, peer_tickers=["VTBR"], state_dir=state, today=TODAY)
    last = out.prices["T"][-1]
    assert last.source == "tinvest" and last.price == pytest.approx(319.5) and last.time == "12:53"
    assert out.peer_prices["VTBR"].price == pytest.approx(81.5)
    assert out.curve["nodes"]["10"] == pytest.approx(0.168282)
    assert out.key_rate == {"value": 0.14, "date": "2026-09-30", "since": "2026-07-27"}
    # закрытия до дробления пересчитаны: в истории цен нет точек в десять раз выше
    assert dict(out.price_history["T"])["2026-04-16"] == pytest.approx(320.4) and max(v for _, v in out.price_history["T"]) < 400
    # реестр по кварталам прибыли: документ эмитента — первый источник, брокерский календарь — сверка
    reg_rows = {r["period"]: r for r in out.register}
    assert set(reg_rows) == {"2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"}
    # рекомендация за третий квартал известна только из новости ленты — запись «рекомендован», без дат
    q3 = reg_rows["2026Q3"]
    assert (q3["status"], q3["dps"], q3["sources"], q3["record_date"], q3["label"]) == (
        "recommended", 4.9, ["Коммерсантъ"], None, None)
    q2 = reg_rows["2026Q2"]
    assert (q2["year"], q2["dps"], q2["status"], q2["record_date"], q2["last_buy_date"], q2["pay_date"]) == (
        2026, 4.7, "paid", "2026-10-12", "2026-10-09", "2026-10-26")
    assert q2["label"] == "за полугодие 2026 года" and q2["decided_date"] == "2026-10-01"
    assert q2["sources"] == ["T-Invest", "документ эмитента"] and q2["notes"] == []
    # записи брокера без документа получили период по лагу; размер у брокера — в нынешних акциях, его не делят
    assert (reg_rows["2026Q1"]["dps"], reg_rows["2026Q1"]["status"], reg_rows["2026Q1"]["record_date"]) == (4.6, "paid", "2026-08-10")
    assert reg_rows["2025Q3"]["dps"] == pytest.approx(3.6) and reg_rows["2025Q4"]["dps"] == 4.5
    assert set(out.register[0]) == set(reg.KEEP) | {"notes"}
    assert out.flags["dividend_register"] == {"raised": False, "detail": ""}
    assert out.brokers["n"] == 5 and "Брокер" not in json.dumps(out.brokers, ensure_ascii=False)
    tiles = {t["id"]: t for t in out.tiles}
    assert tiles["key_rate"]["value"] == 0.14 and tiles["key_rate"]["since"] == "2026-07-27"
    assert tiles["price_T"]["status"] == "ok" and tiles["price_T"]["title"] == "Цена T"
    assert tiles["ops_loans_gross"]["date"] == "2026M09" and tiles["ops_loans_gross"]["value"] == 3700.0
    assert (tiles["ops_clients_total"]["unit"], tiles["ops_clients_total"]["basis"], tiles["ops_clients_total"]["value"]) == (
        "number", "mgmt", 57.3)
    assert tiles["ops_loans_gross"]["source"] == "месячный релиз эмитента"
    assert tiles["f805_n20_0"]["date"] == "2026Q3" and tiles["f805_n20_0"]["source"] == "ЦБ, форма 0409805"
    assert tiles["f805_n20_0"]["status"] == "ok" and tiles["f102_ni_ytd"]["note"].startswith("за шесть кварталов")
    assert len(tiles["ofz_10y"]["history"]["date"]) <= outputs.TILE_POINTS
    # месячная таблица: 15 месяцев главного ряда релиза; таблица релиза РСБУ другой копии пуста
    assert out.ras_months == () and len(out.ops_months) == 15
    sep = out.ops_months[-1]
    assert list(sep) == ["month", "published_at", "clients_total", "clients_active", "loans_gross", "loans_retail",
                         "loans_business", "funds_total", "funds_retail", "funds_business", "ras_ni_ytd", "ras_ni_m",
                         "f102_ni_ytd", "n1_0", "n1_1", "n1_2", "capital_total", "source"]
    assert (sep["month"], sep["loans_gross"], sep["ras_ni_ytd"], sep["capital_total"], sep["n1_0"]) == (
        "2026M09", 3700.0, 150.1, 700.0, pytest.approx(0.131))
    assert sep["source"] == "release:pdf" and sep["published_at"] and sep["f102_ni_ytd"] is None    # формы за сентябрь нет
    aug = out.ops_months[-2]
    assert aug["source"] == "seed" and aug["ras_ni_m"] == pytest.approx(aug["ras_ni_ytd"] - out.ops_months[-3]["ras_ni_ytd"])
    assert sep["ras_ni_m"] == pytest.approx(150.1 - aug["ras_ni_ytd"])
    assert all(r["ras_ni_m"] is None or r["ras_ni_m"] == round(r["ras_ni_m"], 6) for r in out.ops_months)
    jan = next(r for r in out.ops_months if r["month"] == "2026M01")
    assert jan["ras_ni_m"] == jan["ras_ni_ytd"]                        # январь — само значение
    # строки формы 0409102 и флаг — по месяцам месячной таблицы
    assert out.form102 and {r["month"] for r in out.form102} <= {r["month"] for r in out.ops_months}
    assert out.form102[-1]["release_ni"] is not None and out.flags["ras_mismatch"]["raised"] in (False, True)
    assert out.ras_schedule["month"] == "2026M10" and out.ras_schedule["enters_via"] == "form102"     # сентябрь уже принят
    assert out.nowcast["period"] == "2026Q3" and out.journal["total_entries"] == 3
    assert {e["book_version"] for e in out.journal["entries"]} == {"1.0"}
    assert out.retro["main"] == "model" and "ras_bridge" not in out.retro["rmse"]
    assert out.admission["status"] == "collecting"
    for f in state.rglob("*"):
        if f.is_file():
            assert FAKE_TOKEN.encode() not in f.read_bytes()


def test_tiles_window_is_a_year_to_the_last_point_and_money_is_rounded(monkeypatch, tmp_path):
    """Окно плитки — год до последней точки (месяц и квартал — по их концу); мин/макс — за окно; деньги — до 0,01."""
    state, store, _ = _run_all(monkeypatch, tmp_path)
    out = outputs.release_inputs(tickers=TICKERS, state_dir=state, today=TODAY)
    tiles = {t["id"]: t for t in out.tiles if t["status"] != "missing"}
    assert {"ops_loans_gross", "ops_np_ytd", "f102_ni_ytd", "f805_n20_0", "key_rate", "price_T"} <= set(tiles)
    for t in tiles.values():
        last = outputs._period_day(t["date"])
        days = [outputs._period_day(d) for d in t["history"]["date"]]
        assert all((last - d).days <= outputs.HISTORY_DAYS for d in days), t["id"]
        for edge in (t["min"], t["max"]):
            assert (last - outputs._period_day(edge["date"])).days <= outputs.HISTORY_DAYS, t["id"]
        assert t["min"]["value"] <= min(t["history"]["value"]) and t["max"]["value"] >= max(t["history"]["value"])
        if t["unit"] in outputs.MONEY_UNITS:
            numbers = [t["value"], t["min"]["value"], t["max"]["value"], t["change"], *t["history"]["value"]]
            assert all(v == round(v, 2) for v in numbers if v is not None), t["id"]
    month = tiles["ops_loans_gross"]
    assert month["date"] == "2026M09" and month["history"]["date"][0] == "2025M09"
    assert len(month["history"]["date"]) == 13                          # год по концам месяцев
    quarter = tiles["f805_n20_0"]
    assert quarter["history"]["date"] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"]      # год по концам кварталов


def test_the_journal_names_the_book_even_against_a_foreign_release(monkeypatch, tmp_path):
    """sha записи — чужой (прошлый) выпуск со своей книгой; книга ожидания пишется отдельно."""
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    (state / "release").mkdir(parents=True)
    (state / "release" / "latest.json").write_text(json.dumps({"meta": {
        "payload_sha256": "ab" * 32, "book_version": "1.1", "generated_at": "2026-10-25T18:00:00+00:00"}}),
        encoding="utf-8")
    collect.run_nowcast(store, TODAY, expectation=EXPECTATION, book_version="1.2", to_mgmt_nim=lambda v: v)
    rows = Journal(state / "journal.sqlite", readonly=True).forecasts()
    assert {r["release_sha"] for r in rows} == {"ab" * 6} and {r["book_version"] for r in rows} == {"1.2"}
    out = outputs.release_inputs(tickers=TICKERS, state_dir=state, today=TODAY)
    assert out.journal["releases"] == {"ab" * 6: {"book_version": "1.1", "generated_at": "2026-10-25T18:00:00+00:00"}}
    assert {e["book_version"] for e in out.journal["entries"]} == {"1.2"}


def test_guidance_comes_from_the_facts_with_its_moment(monkeypatch, tmp_path):
    """Гайденс года — число фактов, известное на дату; ручная запись важнее. Уровню нужна точка, росту годится
    и нижняя граница; узел с `null` значит «эмитент числа не называет»."""
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    kinds = collect.GROWTH_KINDS
    assert collect.guidance_point(store, "op_np_growth", 2026, "2026-10-01", kinds) == pytest.approx(0.20)
    assert collect.guidance_point(store, "op_np_growth", 2026, "2026-10-01") is None            # граница — не точка
    assert collect.guidance_point(store, "op_np_growth", 2026, "2026-03-01", kinds) is None     # ещё не дан
    assert collect.guidance_point(store, "op_np_growth", 2027, "2027-03-01", kinds) is None     # факты другого года
    assert collect.guidance_point(store, "roe_target", 2026, "2026-10-01") == pytest.approx(0.30)
    assert collect.guidance_point(store, "nim", 2026, "2026-10-01") is None and collect.guidance_declined("nim", 2026)
    assert not collect.guidance_declined("nim", 2027) and not collect.guidance_declined("op_np_growth", 2026)
    assert record.guidance_items()[-3:] == ("op_np_growth", "dps_growth", "roe_target")          # пункты книги
    assert collect.main(["record-guidance", "--year", "2027", "--item", "op_np_growth", "--value", "25%",
                         "--source", "пресс-релиз МСФО за год, с. 2"], today=TODAY) == 0
    # ручная запись несёт момент настенных часов (UTC) — читаем её на дату этого же момента
    day = date.fromisoformat(store.load("guidance.op_np_growth").point_as_of("2027").fetched_at[:10])
    assert collect.guidance_point(store, "op_np_growth", 2027, day.isoformat(), kinds) == pytest.approx(0.25)
    assert collect.guidance_point(store, "op_np_growth", 2027, (day - timedelta(days=1)).isoformat(), kinds) is None
    with pytest.raises(SystemExit):
        collect.main(["record-guidance", "--year", "2026", "--item", "np_growth", "--value", "5%", "--source", "x"],
                     today=TODAY)
    assert collect.main(["record-guidance", "--year", "2026", "--item", "nim", "--value", "11%",
                         "--source", "презентация, с. 23"], today=TODAY) == 0


@pytest.mark.parametrize("days_ahead", (0, 1, 30, 400))
def test_a_manual_record_is_known_from_the_day_of_its_own_moment(monkeypatch, tmp_path, days_ahead):
    """Момент ручной записи — настенные часы, а не `today` команды: при любом положении часов запись читается
    на дату своего момента и не читается днём раньше (тест не привязан к дате прогона)."""
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    wall = datetime(TODAY.year, TODAY.month, TODAY.day, 21, 30, tzinfo=timezone.utc) + timedelta(days=days_ahead)
    monkeypatch.setattr(record, "_now", lambda: wall.isoformat(timespec="seconds"))
    assert collect.main(["record-consensus", "--period", "2026Q3", "--value", "54,2", "--source", "опрос аналитиков"],
                        today=TODAY) == 0
    day = wall.date()
    consensus = store.load("consensus.ni_q")
    assert consensus.value_as_of("2026Q3", day.isoformat()) == pytest.approx(54.2) and consensus.meta["basis"] == "mgmt"
    assert consensus.value_as_of("2026Q3", (day - timedelta(days=1)).isoformat()) is None


def test_nowcast_warns_about_guidance_only_when_the_issuer_gives_one(monkeypatch, tmp_path, capsys):
    """Запись T-90 без гайденса года по ЧПМ — «ВНИМАНИЕ» и код 3, но только если факты не говорят, что эмитент
    числа не называет: у такого эмитента напоминать не о чем."""
    state = use_fixtures(monkeypatch, tmp_path)
    kw = {"expectation": EXPECTATION, "book_version": "1.0", "to_mgmt_nim": lambda v: v}
    far = date(2026, 8, 25)                                             # T-90 до отчёта 19.11
    assert collect.run_nowcast(Store(state), far, **kw) == 0
    row = Journal(state / "journal.sqlite", readonly=True).forecast("nim_q", "2026Q3", "T-90")
    assert "guidance" not in row["benchmarks"] and "f102_nii" in row["benchmarks"]
    capsys.readouterr()
    monkeypatch.setattr(collect, "guidance_declined", lambda item, year: False)
    other = Store(tmp_path / "other")
    assert collect.run_nowcast(other, far, **kw) == 3
    assert "нет гайденса года по ЧПМ" in capsys.readouterr().out and "ложится" in other.read_state("nowcast.json")["notes"][0]


def test_the_token_is_gone_before_foreign_input_is_parsed(monkeypatch, tmp_path):
    """В общем запуске сборщик T-Invest идёт первым, после него токена в окружении процесса нет."""
    import os

    use_fixtures(monkeypatch, tmp_path)
    inner = FakeGetter(moment=MOMENT)
    seen: list[tuple[bool, bool]] = []                               # (запрос к T-Invest, токен в окружении)

    def getter(url, **kw):
        seen.append(("invest-public-api" in url, bool(os.environ.get("TINVEST_TOKEN"))))
        return inner(url, **kw)

    collect.main(["collect"], getter=getter, today=TODAY)
    assert {tinvest_call for tinvest_call, _ in seen} == {True, False}
    assert all(has_token == to_tinvest for to_tinvest, has_token in seen)
    last_tinvest = max(i for i, (to_tinvest, _) in enumerate(seen) if to_tinvest)
    assert not any(to_tinvest for to_tinvest, _ in seen[last_tinvest + 1:]) and last_tinvest < len(seen) - 1
    assert "TINVEST_TOKEN" not in os.environ


def test_only_and_skip_split_the_tact_and_share_one_report(monkeypatch, tmp_path, capsys):
    """Сборщик T-Invest — отдельным запуском (`--only`), остальное — вторым (`--skip`); отчёт один."""
    state = use_fixtures(monkeypatch, tmp_path)
    store = Store(state)
    g = FakeGetter(moment=MOMENT)
    first = collect.main(["collect", "--only", "tinvest"], getter=g, today=TODAY)
    report = store.read_state("collector_report.json")
    assert first == 0 and [d["name"] for d in report["details"]] == ["tinvest"]
    assert all("invest-public-api" in c["url"] for c in g.calls)                       # токен нужен только здесь
    assert "release_watch" not in report                                               # шаги такта — во втором запуске
    g.calls.clear()
    second = collect.main(["collect", "--skip", "tinvest"], getter=g, today=TODAY)
    report = store.read_state("collector_report.json")
    assert not any("invest-public-api" in c["url"] for c in g.calls)
    assert {d["name"] for d in report["details"]} == {"tinvest", "cbr_forms", "cbr_group", "iss", "cbr", "news",
                                                      "issuer_docs", "release_watch", "register"}
    assert report["code"] == max(first, second) == 3 and report["sources"]["cbr_forms"] == "degraded"
    assert report["retry"] is True                                # формы ЦБ не на все даты: сетевой отказ (5xx)
    assert {d["name"]: d["retry"] for d in report["details"]}["tinvest"] is False
    assert report["release_watch"]["months"] and "streak" in report
    # принятый месячный релиз выпуск не будит; будят документы МСФО и документы о дивиденде
    assert report["release_watch"]["accepted"] == [] and report["ifrs_candidates"]
    assert any(m["month"] == "2026M09" and m["month_accepted"] for m in report["release_watch"]["months"])
    assert collect.main(["collect", "--only", "нет_такого"], getter=g, today=TODAY) == 1
    assert "нет сборщика" in capsys.readouterr().out
    assert collect.main(["collect", "--only", "issuer_docs,cbr_group"], getter=g, today=TODAY) in (0, 3)
    assert collect.selected("daily-indicators", None, "tinvest") == ("iss", "cbr")
    assert collect.selected("release-watch", "tinvest", None) == ()
    assert collect.selected("collect", "cbr_group,issuer_docs", None) == ("cbr_group", "issuer_docs")


def _quiet_register(store):
    """Реестр в порядке: первый открытый квартал закрыт выплаченной записью — тревоги реестра нет."""
    reg.record_manual(store, year=None, period="2026Q1", dps=4.6, status="declared", record_date="2026-08-10",
                      pay_date="2026-08-24", decided_date="2026-07-30", source="протокол", origin="issuer_docs")


def test_a_recoverable_source_alarms_only_on_the_third_tact_in_a_row(monkeypatch, tmp_path, capsys):
    """Ставки вкладов (плитка) не ответили — два такта код 0 и строка «такт k из 3», с третьего — тревога."""
    state = use_fixtures(monkeypatch, tmp_path, token=False)
    store = Store(state)
    _quiet_register(store)
    down = {"avgprocstav": http.FetchError("https://example.org/avgprocstav", 503, "HTTP 503")}
    codes = []
    for day in (1, 2, 2, 3, 4):                      # 02.10 — два запуска: повтор внутри такта счётчик не двигает
        code = collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(overrides=down),
                            today=date(2026, 10, day))
        report = store.read_state("collector_report.json")
        codes.append((code, report["streak"].get("cbr"), report["retry"]))
    assert codes == [(0, 1, False), (0, 2, False), (0, 2, False), (3, 3, False), (3, 4, False)]
    text = capsys.readouterr().out
    assert "cbr: деградация (такт 1 из 3)" in text and "cbr: деградация 3-й такт подряд — тревога" in text
    out = outputs.release_inputs(tickers=TICKERS, state_dir=state, today=date(2026, 10, 4))
    assert out.collector["streak"]["cbr"] == 4 and any("ставки вкладов" in d for d in out.collector["degraded"])
    assert out.collector["alarm"] == ["cbr"]
    assert collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(), today=date(2026, 10, 5)) == 0
    assert "cbr" not in store.read_state("collector_report.json")["streak"]


def test_the_build_is_told_which_sources_already_alarm(monkeypatch, tmp_path, capsys):
    """Сборка получает `collector.alarm` — источники, уже получившие код 3 у сборщиков; тревога реестра — сразу."""
    state = use_fixtures(monkeypatch, tmp_path, token=False)
    store = Store(state)
    assert outputs.release_inputs(tickers=TICKERS, state_dir=state, today=date(2026, 10, 1)).collector["alarm"] == []
    code = collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(), today=date(2026, 10, 1))
    got = outputs.release_inputs(tickers=TICKERS, state_dir=state, today=date(2026, 10, 1)).collector
    assert code == 3 and got["alarm"] == ["register"] and "ТРЕВОГА реестра" in capsys.readouterr().out
    assert any(d.startswith("реестр дивидендов: нет записи реестра за первый квартал 2026 года") for d in got["degraded"])
    _quiet_register(store)
    assert collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(), today=date(2026, 10, 2)) == 0
    # критический источник деградировал — тревога сразу, без счётчика
    quotes = {"/securities.json": b'{"marketdata": {"columns": [], "data": []}, "securities": {"columns": [], "data": []}}'}
    code = collect.main(["daily-indicators", "--skip", "tinvest"], getter=FakeGetter(overrides=quotes),
                        today=date(2026, 10, 6))
    report = store.read_state("collector_report.json")
    assert report["sources"]["iss"] != "ok" and "iss" in outputs.collector_alarm(report) and code in (1, 3)
    assert outputs.collector_alarm({}) == [] and outputs.collector_alarm({"details": [{"name": "x", "code": 0}]}) == []
    assert outputs.collector_alarm({"details": [{"name": "news", "code": 3}, {"name": "iss", "code": 1}]}) == ["news"]


def test_status_health_and_record_commands(monkeypatch, tmp_path, capsys):
    state, store, _ = _run_all(monkeypatch, tmp_path)
    assert collect.main(["status"], today=TODAY) == 0
    assert collect.main(["health"], today=TODAY) == 0
    assert (state / "state_size.log").exists()
    assert "задан" in capsys.readouterr().out
    assert collect.main(["record-consensus", "--period", "2026Q3", "--value", "54,2", "--source", "опрос"],
                        today=TODAY) == 0
    assert collect.main(["record-guidance", "--year", "2026", "--item", "roe_target", "--value", "30%",
                         "--source", "пресс-релиз МСФО, с. 2"], today=TODAY) == 0
    assert store.load("guidance.roe_target").value_as_of("2026") == pytest.approx(0.30)
    assert collect.main(["record-actual", "--target", "ni_q", "--period", "2026Q3", "--value", "56,3",
                         "--source", "пресс-релиз МСФО за III квартал, с. 3", "--reported-on", "2026-11-19"],
                        today=TODAY) == 0
    assert collect.main(["record-actual", "--target", "ni_q", "--period", "2026Q3", "--value", "57",
                         "--source", "исправление"], today=TODAY) == 1          # факт неснимаем
    actual = store.load("actual.ni_q")
    assert actual.value_as_of("2026Q3") == pytest.approx(56.3) and actual.meta["basis"] == "mgmt"
    assert actual.meta["label"] == "Операционная прибыль акционеров за квартал (определение эмитента)"
    assert collect.main(["record-actual", "--target", "nim_q", "--period", "2026Q3", "--value", "11,4%",
                         "--source", "пресс-релиз МСФО, с. 4"], today=TODAY) == 0
    # месячный релиз руками: метрики — из настройки
    assert collect.main(["record-ras", "--month", "2026M09", "--source", "релиз за сентябрь, с. 3",
                         "clients_total=57,4", "n1_1=8,9%"], today=TODAY) == 0
    assert store.load("ops.release.clients_total").value_as_of("2026M09") == pytest.approx(57.4)
    assert collect.main(["record-ras", "--month", "2026M09", "--source", "x", "nii_m=1"], today=TODAY) == 1
    # запасной ручной ввод дивиденда: квартал прибыли обязателен, год выводится из него
    capsys.readouterr()
    assert collect.main(["record-dividend", "--year", "2026", "--dps", "4,9", "--status", "recommended",
                         "--source", "пресс-релиз МСФО"], today=TODAY) == 1
    assert "нужен --period" in capsys.readouterr().out
    assert collect.main(["record-dividend", "--period", "2026Q3", "--label", "за девять месяцев 2026 года", "--dps", "4,9",
                         "--status", "recommended", "--decided", "2026-11-19", "--source", "пресс-релиз МСФО, с. 1"],
                        today=TODAY) == 0
    assert "record-dividend 2026Q3: recommended 4.9 ₽" in capsys.readouterr().out
    assert collect.main(["record-dividend", "--period", "2026Q3", "--dps", "4,9", "--status", "declared",
                         "--source", "протокол"], today=TODAY) == 1          # у решения нужна дата реестра
    rec = reg.manual_records(store)[-1]
    assert (rec["year"], rec["period"], rec["label"], rec["decided_date"], rec["origin"]) == (
        2026, "2026Q3", "за девять месяцев 2026 года", "2026-11-19", None)
    row = next(r for r in reg.build(store, ticker="T", today=date(2026, 11, 20), cfg=collect.config.sources(),
                                    splits=collect.config.splits()) if r["period"] == "2026Q3")
    # ту же рекомендацию называет и новость ленты — второй источник рядом с ручной записью
    assert (row["status"], row["sources"], row["recommended_date"]) == (
        "recommended", ["Коммерсантъ", "ручная запись"], "2026-11-19")


def test_open_period_follows_the_last_fact(monkeypatch, tmp_path):
    state, store, _ = _run_all(monkeypatch, tmp_path)
    assert collect.open_period(store, TODAY) == "2026Q3"
    assert collect.open_period(Store(tmp_path / "empty"), TODAY) == "2026Q3"      # без фактов — прошлый квартал
    assert collect.open_period(Store(tmp_path / "empty"), date(2026, 12, 1)) == "2026Q3"


def test_combine_is_re_exported_for_the_core():
    """Ядро берёт `combine` из `indicators/outputs.py` — одна точка входа индикаторов."""
    from indicators import nowcast

    assert outputs.combine is nowcast.combine and "combine" in outputs.__all__
    assert tinvest.TOKEN_ENV == "TINVEST_TOKEN"


def test_journal_benchmarks_are_named_by_the_retro_titles():
    """Названия эталонов записей журнала — в словаре названий ретро-проверки: витрина печатает название, а не
    ключ, и у эталона, которого в ретро-проверке нет; названия ретро-проверки не затираются."""
    from indicators.journal import BENCHMARK_TITLES

    retro_block = {"titles": {"prev_quarter": "своё название"}, "main": "prev_quarter"}
    journal = {"entries": [{"benchmarks": {"f102_nii": 0.126, "model": 0.115, "prev_quarter": 0.116}},
                           {"benchmarks": {"guidance": 54.2}}, {"benchmarks": None}]}
    out = outputs.with_journal_titles(retro_block, journal)
    assert out["main"] == "prev_quarter" and out["titles"]["prev_quarter"] == "своё название"
    assert {k: out["titles"][k] for k in ("f102_nii", "model", "guidance")} == {
        k: BENCHMARK_TITLES[k] for k in ("f102_nii", "model", "guidance")}
    assert all(re.search("[а-яё]", title) for title in out["titles"].values())      # слова, а не ключи
    assert retro_block["titles"] == {"prev_quarter": "своё название"}               # вход не меняется
    assert outputs.with_journal_titles({}, {"entries": []}) == {}                   # пустое состояние — как было
    # прочие поля ретро-проверки (счёт кварталов, главный эталон, горизонты) функция не трогает; эталон журнала
    # без названия в словаре остаётся ключом — видимой недоделкой, а не пропавшей строкой
    block = {"titles": {}, "n": {"model": 0}, "main": "model", "by_horizon": {"T-30": {"titles": {}}}}
    out = outputs.with_journal_titles(block, {"entries": [{"benchmarks": {"model": 1.0, "новый_эталон": 2.0}}]})
    assert {k: out[k] for k in ("n", "main", "by_horizon")} == {k: block[k] for k in ("n", "main", "by_horizon")}
    assert out["titles"] == {"model": BENCHMARK_TITLES["model"], "новый_эталон": "новый_эталон"}
