"""История рядов `data/indicators/seed/`: у каждого числа источник, импорт идемпотентен, сборка воспроизводима."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from indicators import collect, config, periods, release_watch, seed
from indicators.store import Store
from tests.support_ind import use_fixtures, use_form_settings

MONTHLY_START = "2025M01"            # с этого месяца у остатков релиза один периметр


@pytest.mark.tact
def test_every_seed_number_has_a_source(monkeypatch):
    """История формы образца (`tests/fixtures/ind/form/seed/`): месячный релиз, формы банка и группы, кварталы."""
    use_form_settings(monkeypatch)
    for name in seed.SEED_FILES:
        assert config.load_seed(name) is not None and config.load_seed(name).get("source"), name
    spec = release_watch.monthly(config.sources())
    monthly = config.load_seed("monthly_release")
    assert monthly["prefix"] == spec.prefix and min(monthly["months"]) == MONTHLY_START
    for m, entry in monthly["months"].items():
        periods.parse_month(m)
        assert entry["release_date"] > periods.month_end(m).isoformat() and spec.main in entry["values"], m
        for metric, node in entry["values"].items():
            assert metric in spec.metrics and node["src"] and "sha256" in node["src"], (m, metric)
            if metric in release_watch.SHARE_METRICS:
                assert 0 < node["v"] < 0.3, (m, metric)            # доли, не проценты
    # показатель «без учёта разовых резервов» в ряд прибыли не входит: за эти месяцы прибыли в релизе нет
    assert "np_ytd" not in monthly["months"]["2025M02"]["values"] and "np_ytd" not in monthly["months"]["2025M03"]["values"]
    for q, e in config.load_seed("ifrs_quarters")["quarters"].items():
        periods.parse_quarter(q)
        assert e["value"]["src"] and "sha256" in e["value"]["src"] and 10 < e["value"]["v"] < 100
    for q, e in config.load_seed("mgmt_quarters")["quarters"].items():
        assert all(n["src"] for n in e.values())
        assert all(0 <= n["v"] < 0.2 for n in e.values())          # доли, не проценты
    f102 = config.load_seed("form102")["months"]
    last = f102[max(f102)]
    assert {"ni_ytd", "pretax_ytd", "nii_ytd", "prov_ytd", "opex_ytd"} <= set(last) and last["nii_ytd"] > last["ni_ytd"]
    for name, keys in (("form135", {"n1_0", "n1_1", "n1_2"}), ("form123", {"capital_total", "capital_base"})):
        rows = config.load_seed(name)["months"]
        assert keys <= set(rows[max(rows)]) and periods.form_month(rows[max(rows)]["form_date"]) == max(rows), name
    group = config.load_seed("group_forms")["quarters"]
    for q, e in group.items():
        periods.parse_quarter(q)
        assert 0.05 < e["f805"]["n20_0"] < 0.3 and e["f805"]["capital_total"] > e["f805"]["capital_base"], q
        assert e["f805"]["n20_1"] < e["f805"]["n20_0"] and "nii_ytd" in e["f803"], q
    assert config.load_seed("consensus")["quarters"] == {}          # консенсус — только ручной ввод
    f101 = config.load_seed("form101")
    assert f101["codes"] and f101["codes_required"]                 # определение, под которое построен ряд
    for m, e in f101["months"].items():
        assert e["iea"] > 0 and e["sha256"] and periods.form_month(e["form_date"]) == m, m
    for q, e in f101["quarters"].items():
        ends = [f101["months"][m]["iea"] for m in e["months"]]
        assert e["iea_avg"] == pytest.approx(sum(ends) / 2, abs=1e-5), q


@pytest.mark.tact
def test_the_history_of_this_copy_is_the_bank_forms_and_the_facts():
    """История этой копии (`data/indicators/seed/`, раскладка `soap`): месячного релиза нет; формы банка — из ответов
    службы ЦБ с sha256 файла; ЧПД формы 0409102 — с разделом 12000; прибыль квартала, ЧПМ и CoR — узлы фактов;
    формы группы — до 1-го квартала 2025 года (дальше ЦБ их не раскрывает); процентных активов в фактах нет."""
    assert config.setting("seed.layout") == "soap"
    for name in seed.SEED_FILES:
        assert config.load_seed(name) is not None and config.load_seed(name).get("source"), name
    assert config.load_seed("monthly_release")["months"] == {}
    assert config.load_seed("consensus")["quarters"] == {}
    f102 = config.load_seed("form102")["months"]
    for m, e in f102.items():
        assert periods.form_month(e["form_date"]) == m and len(e["sha256"]) == 64, m
    last = f102[max(f102)]
    assert {"ni_ytd", "pretax_ytd", "nii_ytd", "prov_ytd", "opex_ytd"} <= set(last) and last["nii_ytd"] > last["ni_ytd"]
    for name, keys in (("form135", {"n1_0", "n1_1", "n1_2"}), ("form123", {"capital_total", "capital_base"})):
        rows = config.load_seed(name)["months"]
        assert keys <= set(rows[max(rows)]) and periods.form_month(rows[max(rows)]["form_date"]) == max(rows), name
    n135 = config.load_seed("form135")["months"]
    assert all(0.05 < e["n1_0"] < 0.3 and e["n1_2"] <= e["n1_0"] for e in n135.values())       # доли, не проценты
    group = config.load_seed("group_forms")["quarters"]
    assert max(group) < config.setting("cbr_group.suspended_since")
    assert all(0.05 < e["f805"]["n20_0"] < 0.3 and e["f805"]["n20_1"] < e["f805"]["n20_0"] for e in group.values())
    for q, e in config.load_seed("ifrs_quarters")["quarters"].items():
        periods.parse_quarter(q)
        assert e["value"]["src"] and "sha256" in e["value"]["src"] and 0 < e["value"]["v"] < 100, q
        day = e["report_date"]["v"]
        assert day is None or day > periods.quarter_end(q).isoformat(), q                 # отчёт — после квартала
    for q, e in config.load_seed("mgmt_quarters")["quarters"].items():
        assert all(n["src"] and 0 <= n["v"] < 0.2 for n in e.values()), q
    assert config.load_seed("form101")["months"] == {} and not seed.form101_fits(config.load_seed("form101"))


@pytest.mark.tact
def test_form101_history_follows_the_facts_definition(monkeypatch, tmp_path):
    """История формы 101 идёт в ряды, только если построена под определение процентных активов фактов."""
    use_fixtures(monkeypatch, tmp_path)
    data = config.load_seed("form101")
    assert not seed.form101_fits(data)                               # у пробных фактов определение своё
    assert "cbr.f101.iea" not in seed.import_to_store(Store(tmp_path / "other"))
    store = Store(tmp_path / "mark")
    assert collect.ensure_seed(store) and not collect.ensure_seed(store)
    assert store.load("cbr.f101.iea") is None
    same = {"iea": {"codes": data["codes"], "codes_required": data["codes_required"]}}
    monkeypatch.setattr(config, "bridge_ras_ifrs", lambda facts_dir=None: same)
    assert seed.form101_fits(data) and not seed.form101_fits(None)
    assert collect.ensure_seed(store)                                # определение сменилось — история перечитана
    assert set(store.load("cbr.f101.iea").history()) == set(data["months"])
    assert not collect.ensure_seed(store)


@pytest.mark.tact
def test_seed_holds_no_raw_broker_answers():
    """В истории нет сырых ответов брокера и имён полей его ответа: только ряды с источником."""
    for path in sorted(config.SEED_DIR.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"dividendNet|recordDate|lastBuyDate|paymentDate|instrumentUid|targetPrice", text), path.name
        assert "invest-public-api" not in text, path.name


@pytest.mark.tact
def test_import_is_idempotent_and_dates_knowledge(monkeypatch, tmp_path):
    use_fixtures(monkeypatch, tmp_path)
    store = Store(tmp_path / "seeded")
    touched = seed.import_to_store(store)
    counts = {sid: len(store.load(sid).points) for sid in touched}
    seed.import_to_store(store)
    assert {sid: len(store.load(sid).points) for sid in touched} == counts
    assert {"ops.release.loans_gross", "ops.release.np_ytd", "actual.ni_q", "actual.nim_q", "actual.cor_q",
            "cbr.f102.ni_ytd", "cbr.f102.nii_ytd", "cbr.f135.n1_0", "cbr.f123.capital_total", "cbr.f805.n20_0",
            "cbr.f803.ni_ytd"} <= set(touched)
    monthly = config.load_seed("monthly_release")["months"]
    m = max(monthly)
    loans = store.load("ops.release.loans_gross")
    assert loans.first_seen(m)[:10] == monthly[m]["release_date"]            # момент — день релиза
    assert loans.meta["unit"] == "RUB bn" and store.load("ops.release.clients_total").meta["unit"] == "mn"
    assert store.load("ops.release.n1_0").meta["unit"] == "share"
    act = store.load("actual.ni_q")
    q = max(config.load_seed("ifrs_quarters")["quarters"])
    assert act.first_seen(q)[:10] == config.load_seed("ifrs_quarters")["quarters"][q]["report_date"]["v"]
    assert act.meta["basis"] == "mgmt"                                       # базис цели — подпись книги
    f102 = store.load("cbr.f102.ni_ytd")
    last = max(f102.history())
    assert f102.first_seen(last)[:10] > config.load_seed("form102")["months"][last]["form_date"]   # выкладка — позже даты формы
    n20 = store.load("cbr.f805.n20_0")
    last_q = max(n20.history())
    assert n20.first_seen(last_q)[:10] > periods.quarter_end(last_q).isoformat() and n20.meta["unit"] == "share"


@pytest.mark.archive
def test_seed_rebuild_matches_committed_files():
    root = os.environ.get("BANK_HANDOFF_DIR")
    if not root:
        pytest.skip("нужна папка передачи (BANK_HANDOFF_DIR)")
    built = seed.build_all(Path(root), tuple(n for n in seed.SEED_FILES if config.load_seed(n) is not None))
    assert built
    for name, obj in built.items():
        assert (config.SEED_DIR / f"{name}.json").read_text(encoding="utf-8") == seed.dump(obj), name
