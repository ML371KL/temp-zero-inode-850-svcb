# -*- coding: utf-8 -*-
"""Сборщик фактов Совкомбанка в сухом прогоне перезаякоривания: режим `build_facts.py --expected` и файл отчёта квартала.

`--expected` строит факты следующего квартала из фактов якоря и отчёта квартала (`quarter-report/1`) — вторая,
независимая от `ops/tools/reanchor.py` сборка тех же правил переноса (М§15.2): ядро обязано прочесть из обеих
одно состояние якоря (`reanchor.py --compare-facts`). Быстрые тесты (`tact`) — без прогона сетки, на отчёте,
собранном из закоммиченных фактов и перенесённом на следующий квартал (дивиденд за год выплачен, остаток к выплате —
ноль, баланс сведён ликвидностью): состав и тождества новых фактов, ставки якоря несут весь ЧПД, решение собрания и
список «объявлено, не выплачено», пометка оценки нормативов, отказы. Тест с прогоном сетки (`ci_only`) — на настоящей
книге: три квартала подряд факты сборщика и рабочие факты кандидата дают ядру одно состояние и одну точку.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from model.book import Facts, anchor_facts, canonical_json, load_book, load_facts
from model.grid import run_grid
from tests.support_core import real_book_or_skip
from tests.test_reanchor import R, scene_of

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data" / "facts"
BUILDER = ROOT / "ops" / "tools" / "build_facts.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_facts_for_reanchor", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


B = _builder()


def committed() -> dict[str, dict]:
    return {k: json.loads((FACTS / f"{k}.json").read_text(encoding="utf-8")) for k in B.BUILT}


def next_report() -> dict:
    """Отчёт квартала якоря из закоммиченных фактов, перенесённый на следующий квартал: числа те же, период и дата —
    следующие; дивиденд за прошлый год выплачен (остаток к выплате — ноль, ликвидность меньше на ту же сумму); решений
    собраний в квартале нет; норматив — после вычета дивиденда."""
    facts = committed()
    report = B.report_from_facts(facts, source="тест: факты якоря как отчёт следующего квартала")
    period = B.q_next(report["period"])
    report.update(period=period, as_of=B.q_end(period).isoformat(), dividend_decisions=[])
    b = report["balance"]
    b["books"]["liquidity"] -= b["dividends_payable"]
    b.update(dividends_payable=0.0, dividends_payable_declared=[])
    b.pop("dividends_payable_year")
    report["capital"]["n20_pre_dividend"] = False
    return report


def as_facts(files: dict[str, dict]) -> Facts:
    return Facts(root=Path("expected"), files=dict(files), digest=hashlib.sha256(canonical_json(files)).hexdigest())


# ------------------------------------------------------------------ без прогона сетки (такт)


@tact
def test_the_quarter_report_names_the_decision_of_the_quarter_and_the_annual_payable():
    """Файл отчёта квартала из фактов якоря называет решение собрания, принятое в квартале якоря (периодом прибыли —
    четвёртым кварталом года, с днём решения и датами), год дивиденда к выплате и постоянную часть прочих активов;
    состав читает `reanchor.py`."""
    facts = committed()
    report = B.report_from_facts(facts, source="тест")
    period, as_of = facts["anchor"]["period"], facts["anchor"]["as_of"]
    opened = B.q_end(B.q_prev(period)).isoformat()
    want = [h["period"] for h in facts["dividends"]["history"] if opened < h["decided_date"] <= as_of]
    assert [d["period"] for d in report["dividend_decisions"]] == want and want, "в квартале якоря было решение собрания"
    for d in report["dividend_decisions"]:
        assert set(d) <= set(R.DECISION_REQUIRED + R.DECISION_OPTIONAL) and set(R.DECISION_REQUIRED) <= set(d)
        assert opened < d["decided_date"] <= as_of
    assert report["balance"]["dividends_payable_year"] == facts["balance"]["dividends_payable_year"]
    assert report["balance"]["other_assets_fixed"] == facts["balance"]["other_assets_fixed"]["v"]
    assert set(report) - set(R.TOP_REQUIRED) <= set(R.TOP_OPTIONAL)
    for name, (required, optional) in R.SECTIONS.items():
        assert set(required) <= set(report[name]) <= set(required + optional), name
    B.check_report_shape(report)


@tact
def test_expected_facts_of_the_next_quarter_keep_the_identities():
    """Факты следующего квартала из фактов якоря и отчёта квартала: якорь, прямые книги (13), тождество баланса,
    ставки якоря несут весь ЧПД, квартал добавлен в истории (и остатки книг прежнего якоря — концом квартала),
    нормативы банка соло, дивиденд выплачен — годового остатка нет, запись реестра выпала. Вход не меняется."""
    prev, report = committed(), next_report()
    before = copy.deepcopy(prev)
    files, checks = B.expected_facts(prev, report, name="report.json", sha="ab" * 32)
    assert prev == before and all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
    period = report["period"]
    assert files["anchor"]["period"] == period and files["anchor"]["expected"]["from_anchor"] == prev["anchor"]["period"]
    assert tuple(files) == B.BUILT
    bal, nb = files["balance"], files["nii_books"]
    assert {b: bal["books"][b]["v"] for b in B.BOOKS} == pytest.approx(report["balance"]["books"])
    assets = sum(bal["books"][b]["v"] for b in B.ASSET_BOOKS) - bal["allowance_ac"]["v"] + bal["other_assets"]["v"]
    assert bal["total_assets"]["v"] == pytest.approx(assets) == pytest.approx(
        bal["total_liabilities"]["v"] + bal["equity"]["total"]["v"], abs=1e-6)
    assert bal["securities"]["fvoci_debt"]["v"] + bal["securities"]["fvoci_repo"]["v"] == pytest.approx(report["balance"]["fvoci"])
    for book, nodes in B.BOOK_NODES.items():
        got = sum(B.dig(bal, p)["v"] for p in nodes)
        assert got == pytest.approx(report["balance"]["books"][book], abs=1e-6), book
    assert set(bal["history"]) - set(prev["balance"]["history"]) == {period}
    assert set(bal["history"][prev["anchor"]["period"]]["books"]) == set(B.BOOKS)
    row = bal["history"][period]
    assert row["loans"]["v"] == pytest.approx(sum(report["balance"]["books"][b] for b in B.LOANS))
    assert row["loans_ac_gross"]["v"] == row["loans"]["v"] and row["funds"]["v"] > 0
    assert bal["dividends_payable"]["v"] == 0 and "dividends_payable_year" not in bal
    # ставки якоря несут весь ЧПД
    assert nb["rates_carry_residual"] is True and nb["period"] == period
    days = nb["days"]["v"]
    carried = sum((1 if b in B.ASSET_BOOKS else -1) * nb["books"][b]["rate_anchor"]["v"] * nb["books"][b]["balance_avg"]["v"]
                  for b in B.BOOKS) * days / 365 - nb["dia_q"]["v"]
    assert carried == pytest.approx(report["pnl"]["nii"], abs=1e-4)
    # ОПУ, капитал, мосты
    q = files["pnl_quarterly"]["quarters"][period]
    assert q["ni_shareholders"]["v"] == report["pnl"]["ni_shareholders"] and q["ni_nci"]["v"] == pytest.approx(
        report["pnl"]["ni"] - report["pnl"]["ni_shareholders"])
    cap = files["capital"]
    assert cap["n20_0"]["value"]["v"] == report["capital"]["n20_0"] == cap["n1_0_bank"]["v"] and cap["n20_0"]["estimated"] is False
    assert cap["n1_1_bank"]["value"]["v"] == report["capital"]["n1_1_bank"] and cap["n1_1_bank"]["slot_metric"] == "Н1.2"
    assert cap["history"][-1]["period"] == period and "core_form_check" not in cap
    assert cap["at1"]["amount"]["v"] == report["balance"]["at1"]
    br = files["bridge_mgmt_ifrs"]
    for x in ("cor", "nim", "cir"):
        assert br[x]["history"][-1]["period"] == period and br[x]["window"] == [prev["bridge_mgmt_ifrs"][x]["window"][0], period]
        assert br[x]["n"]["v"] == prev["bridge_mgmt_ifrs"][x]["n"]["v"] + 1
    assert br["nim"]["method"] == "ratio" and abs(br["nim"]["history"][-1]["gap_x4"]["v"] - 1) < 0.5
    # дивиденды: запись реестра с экс-датой до новой даты фактов выпала
    assert files["dividends"]["register_seed"] == [] and "register_seed_note" not in files["dividends"]
    # узлы калибровки, календарь, аналоги — как прежде
    for k in B.CARRIED:
        assert files[k] == prev[k], k
    # ядро читает эти факты
    core = as_facts(files)
    from tests.support_core import REAL_BOOK
    if REAL_BOOK.exists():
        book = load_book(REAL_BOOK, facts=load_facts(FACTS))
        af = anchor_facts(core, book.get("nii.books"))
        assert af.period == period and af.bv == report["balance"]["bv_common"]


@tact
def test_expected_facts_carry_estimates_declared_dividends_and_refuse_a_wrong_report():
    prev, report = committed(), next_report()
    estimate = {slot: {"bank_value": report["capital"][slot] - 0.003, "spread": 0.003, "spread_as_of": prev["anchor"]["as_of"]}
                for slot in ("n20_0", "n1_1_bank")}
    rep = copy.deepcopy(report)
    rep["capital"].update(estimated=True, estimate=estimate)
    rep["pnl"]["estimated"] = True
    after = B.q_end(B.q_next(rep["period"])).replace(day=10).isoformat()
    decided = B.q_end(rep["period"]).replace(day=15).isoformat()
    rep["dividend_decisions"] = [{"period": rep["period"], "dps": 0.1, "decided_date": decided, "record_date": after,
                                  "pay_date": after}]
    rep["balance"]["dividends_payable_declared"] = [{"period": rep["period"], "amount": 2.2}]
    rep["balance"].update(dividends_payable=2.2, dividends_payable_year=int(rep["period"][:4]))
    rep["balance"]["books"]["liquidity"] += 2.2
    files, checks = B.expected_facts(prev, rep, name="report.json", sha="cd" * 32)
    assert all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
    cap = files["capital"]
    for slot in ("n20_0", "n1_1_bank"):
        assert cap[slot]["estimated"] is True and cap[slot]["value"]["estimated"] is True
        assert cap[slot]["estimate"]["bank_value"]["v"] == estimate[slot]["bank_value"]
    assert files["pnl_quarterly"]["quarters"][rep["period"]]["ni_shareholders"]["estimated"] is True
    assert [(x["period"], x["amount"]["v"]) for x in files["balance"]["dividends_payable_declared"]] == [(rep["period"], 2.2)]
    assert files["balance"]["dividends_payable_year"] == int(rep["period"][:4])
    hist = {h["period"]: h for h in files["dividends"]["history"]}
    assert hist[rep["period"]]["decided_date"] == decided
    assert hist[rep["period"]]["pool_declared"]["v"] == pytest.approx(0.1 * files["shares"]["dividend_eligible"]["v"] / 1000)
    assert rep["period"] in {s["period"] for s in files["dividends"]["register_seed"]}, "сумма объявлена, не выплачена"
    for change, fragment in ((lambda x: x.update(period=prev["anchor"]["period"]), "следующего"),
                             (lambda x: x.update(extra=1), "незнакомый ключ extra"),
                             (lambda x: x["balance"]["books"].pop("insurance_liab"), "balance.books.insurance_liab"),
                             (lambda x: x["capital"].pop("estimate"), "capital.estimate"),
                             (lambda x: x.update(as_of=prev["anchor"]["as_of"]), "не конец квартала"),
                             (lambda x: x["dividend_decisions"][0].update(decided_date=prev["anchor"]["as_of"]), "позже")):
        bad = copy.deepcopy(rep)
        change(bad)
        with pytest.raises(B.BuildError) as exc:
            B.expected_facts(prev, bad, name="report.json", sha="cd" * 32)
        assert fragment in str(exc.value), str(exc.value)
    unbalanced = copy.deepcopy(report)
    unbalanced["balance"]["other_assets"] += 10
    assert not all(ok for _, ok, _ in B.expected_facts(prev, unbalanced, name="report.json", sha="cd" * 32)[1])


@tact
def test_rates_carry_the_residual_from_the_first_reanchored_quarter():
    """Закоммиченные факты — якорь книги: ставки книг без остатка ЧПД; с первого перенесённого квартала ставки книг
    активов несут и проценты вне книг — то же правило, что у `reanchor.py`."""
    nb = json.loads((FACTS / "nii_books.json").read_text(encoding="utf-8"))
    assert nb["rates_carry_residual"] is False
    interest = {b: (10.0 if b in B.ASSET_BOOKS else 4.0) for b in B.BOOKS}
    income, expense = 10.0 * len(B.ASSET_BOOKS), 4.0 * len(B.LIAB_BOOKS)
    residual, scale = B.carry_scale(interest, income - expense - 1.0 + 2.0, 1.0)
    assert residual == pytest.approx(2.0) and scale == pytest.approx(1 + 2.0 / income)


@tact
def test_the_expected_mode_writes_only_outside_the_canon(tmp_path):
    """`--expected ФАЙЛ --out КАТАЛОГ`: все файлы фактов (календарь, аналоги и узлы калибровки — как прежде); без --out
    или в data/facts — отказ; папка передачи не нужна; повтор с `--check` — совпадение."""
    report = tmp_path / "report.json"
    report.write_text(json.dumps(next_report(), ensure_ascii=False), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "BANK_HANDOFF_DIR"} | {"PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, "-B", str(BUILDER), *a], cwd=ROOT, env=env, capture_output=True,   # noqa: E731
                                    text=True, encoding="utf-8")
    for args in (("--expected", str(report)), ("--expected", str(report), "--out", str(FACTS))):
        res = run(*args)
        assert res.returncode == 1 and "только в --out" in res.stderr
    out = tmp_path / "facts"
    res = run("--expected", str(report), "--out", str(out))
    assert res.returncode == 0, res.stderr[-1500:]
    assert sorted(p.stem for p in out.glob("*.json")) == sorted(B.BUILT)
    assert all(b"\r\n" not in p.read_bytes() for p in out.glob("*.json"))
    assert json.loads((out / "calendar.json").read_text(encoding="utf-8")) == json.loads(
        (FACTS / "calendar.json").read_text(encoding="utf-8"))
    assert run("--expected", str(report), "--out", str(out), "--check").returncode == 0
    assert "--expected" in run("--help").stdout
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({**next_report(), "period": "1999Q4"}), encoding="utf-8")
    res = run("--expected", str(wrong), "--out", str(out))
    assert res.returncode == 1 and "ПРОВАЛ" in res.stderr


# ------------------------------------------------------------------ с прогоном сетки (CI)


def manual_valuation_step(book):
    """Ручной шаг перезаякоривания книги с выкупом по цене мира (М§5.6, `docs/REANCHOR.md`): дата оценки, дата книги и
    цена выкупа (`meta.market_price` — цена дня; в сухом прогоне — та же книжная, живой цены нет) переходят вместе на дату
    сухого прогона следующего квартала; дата уже не раньше — книга как есть."""
    from datetime import timedelta
    v = R.period_end(str(book.get("meta.first_period"))) + timedelta(days=2)
    if str(book.get("meta.valuation_date")) >= v.isoformat():
        return book
    prices = {str(t): float(p) for t, p in book.get("meta.market_price").items()}
    return book.with_overrides({"meta.valuation_date": v.isoformat(), "meta.date": v.isoformat(), "meta.market_price": prices})


@ci_only
def test_the_collector_and_the_tool_give_the_core_one_anchor_three_quarters_in_a_row():
    """Настоящая книга, три ожидаемых отчёта подряд: факты `build_facts.py --expected` и рабочие факты кандидата
    `reanchor.py` — одно состояние якоря (сверка `--compare-facts` пуста) и одна точка на книге-кандидате; на смене года
    якоря концы прошлого года — прежний якорь, окно моста ЧПМ продлено кварталом. Выкуп по цене мира (М3, М§5.6): перенос
    якоря дату оценки книги не двигает (дата и цена книги — одна пара); между кварталами цепочки дата оценки, дата книги и
    цена выкупа двигаются вместе — ручным шагом `docs/REANCHOR.md` (иначе дата оценки раньше даты фактов следующего якоря)."""
    book, facts = real_book_or_skip()
    prev = {k: copy.deepcopy(facts.files[k]) for k in B.BUILT}
    seen_year = False
    for _ in range(3):
        book = manual_valuation_step(book)
        s = scene_of(book, facts)
        files, checks = B.expected_facts(prev, s.expected, name="expected.json", sha="ef" * 32)
        assert all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]
        canon = as_facts(files)
        assert R.compare_facts(s.book, s.cand.facts, canon) == [], s.period
        run = run_grid(s.cand.book, canon, R.live_at(s.cand.book, canon, s.v))
        assert run.point == pytest.approx(s.run_e.point, abs=1e-4), s.period
        seen_year |= bool(s.cand.derived["year_shift"])
        if s.cand.derived["year_shift"]:
            assert files["balance"]["prev_year_end"]["as_of"] == prev["anchor"]["as_of"]
            assert files["bridge_mgmt_ifrs"]["nim"]["window"] == [prev["bridge_mgmt_ifrs"]["nim"]["window"][0], s.period]
        book, facts, prev = s.cand.book, s.cand.facts, files
    assert seen_year, "цепочка прошла смену года якоря"
