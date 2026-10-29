"""Витрина и контракт выпуска svcb-v1 (docs/PAYLOAD.md, docs/DASHBOARD.md §2).

* витрина читает только объявленные блоки (`d.<блок>` — из REQUIRED_TOP_LEVEL П§1) и поля,
  которые есть в выпуске; снятые поля (П§6) не читает;
* фронт ничего не считает, кроме λ: суммы — только в сглаживании плотности, прогоны —
  только в правиле λ, потенциал, P/B, доходности и запасы — поля выпуска;
* шаг ползунка — сетка `by_lambda`; правило λ на прогонах выпуска даёт строки таблицы;
* генератор tests/web/make_sample.py даёт две формы выпуска, обе держат контракт (блоки, хэш и
  размер П§0.4, тождества П§7) и совпадают с генератором:
  форма панели — tests/fixtures/payload-sample.json: один тикер, делитель, дивиденды по периодам,
  требование с глиссадой, рост, «цена правила», путь к терминалу, мост трёх прибылей, месячная
  таблица, пределы обратного расчёта, запас второго норматива, строка против требования, база
  суммы дивиденда, оси-связки, числа гейтов знака, узлы «на чём стоит заголовок» (суждение о
  марже, уровни, модальная клетка, справочные варианты, запас до требования с глиссадой); поля
  каркаса, которым нечего нести, пусты (П§9);
  общая форма без узлов панели — tests/web/payload-generic.json: две категории акций, годовая
  выплата, релиз РСБУ; на ней держатся проверки печати общего каркаса (волны W1–W4);
* печатаемые строки выпуска — словами для владельца (П§0.2): без кортежей, e-нотации, меток класса,
  путей к листам, рабочих пометок, дат без года и версий без имени, без имён методов и полей API.

Метка `tact` — у быстрых тестов без документов и без ядра (INTERFACES §9); сверка с
`validate` ядра и тесты по тексту PAYLOAD (`docs`) идут в CI.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PAYLOAD_DOC = ROOT / "docs" / "PAYLOAD.md"
FIXTURE = ROOT / "tests" / "fixtures" / "payload-sample.json"
GENERIC = ROOT / "tests" / "web" / "payload-generic.json"
SCHEMA = "svcb-v1"
GENERATOR = ROOT / "tests" / "web" / "make_sample.py"
MAX_BYTES = 500_000


def code_only(text: str) -> str:
    out = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", out)


APP_CODE = code_only(APP)


def function_body(name: str) -> str:
    begin = APP_CODE.index(f"function {name}(")
    tail = re.search(r"(?m)^(?:function |async function |const |let )", APP_CODE[begin + 1:])
    return APP_CODE[begin:begin + 1 + tail.start()] if tail else APP_CODE[begin:]


def required_top_level() -> list[str]:
    """Блоки П§1 — первая колонка таблицы раздела «Верхние блоки»."""
    text = PAYLOAD_DOC.read_text(encoding="utf-8")
    part = text[text.index("## 1. Верхние блоки"):text.index("## 2. Поля блоков")]
    blocks = re.findall(r"^\| `([a-z_]+)` \|", part, re.M)
    assert len(blocks) == 28, f"в П§1 ожидалось 28 блоков, найдено {len(blocks)}"
    return blocks


def fixture() -> dict:
    """Форма панели — основная фикстура."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def generic() -> dict:
    """Общая форма без узлов панели."""
    return json.loads(GENERIC.read_text(encoding="utf-8"))


FORMS = pytest.mark.parametrize("form", [fixture, generic], ids=["panel", "generic"])


# ── витрина читает только объявленное ──

@pytest.mark.docs
def test_frontend_reads_only_declared_blocks():
    used = set(re.findall(r"(?<![\w$.])d\.([A-Za-z_]\w*)", APP_CODE))
    assert used, "витрина не читает ни одного блока через d.<блок>"
    assert used <= set(required_top_level()), f"необъявленные блоки: {sorted(used - set(required_top_level()))}"
    try:
        from model.payload import REQUIRED_TOP_LEVEL
    except ImportError:
        return
    assert set(REQUIRED_TOP_LEVEL) == set(required_top_level()), "список блоков ядра и П§1 разошёлся"


@pytest.mark.tact
def test_frontend_reads_fields_that_the_release_has():
    """Каждое `d.<блок>.<поле>` — поле синтетического выпуска (он собран по П§2)."""
    d = fixture()
    used = set(re.findall(r"(?<![\w$.])d\.([a-z_]+)\.([a-z_0-9]+)\b", APP_CODE))
    assert used, "регулярка ничего не нашла — поменялось соглашение `d` = выпуск"
    for block, field in sorted(used):
        node = d.get(block)
        assert isinstance(node, dict) and field in node, f"d.{block}.{field}: такого поля в выпуске нет"


@pytest.mark.docs
def test_frontend_does_not_read_removed_fields():
    """Поля П§6 (EV, колл Мертона, долг, цели по брокерам) витрина не читает."""
    text = PAYLOAD_DOC.read_text(encoding="utf-8")
    part = text[text.index("## 6. Снятые поля"):text.index("## 7. `validate`")]
    top = re.search(r"\| верхний уровень \| (.*?) \|", part).group(1)
    for name in re.findall(r"`(\w+)`", top):
        assert not re.search(rf"(?<![\w$.])d\.{name}\b", APP_CODE), f"витрина читает снятый блок {name}"
    specific = set()
    for row in re.findall(r"^\| `(?:fair_value|layers\.\*|grid\.cells\[\]|market|dividends|nowcast|book)` \| (.*?) \|", part, re.M):
        specific |= set(re.findall(r"`(\w+)`", row))
    generic = {"d", "ev", "interest", "margin", "strike", "claims"}
    for name in sorted(specific - generic):
        assert not re.search(rf"\.{name}\b", APP_CODE), f"витрина читает снятое поле {name}"
    assert not re.search(r"company\)?\.ticker\b", APP_CODE), "тикеры — списком и при одной категории: tickers и main_ticker"
    assert "brokers.rows" not in APP_CODE and not re.search(r"\bb\.rows\b", function_body("brokersCard")), "цели по брокерам — только агрегаты"
    assert "sections" in specific and "sections" not in fixture()["book"], "строки книги по разделам сняты (В7): ни витрина, ни фикстура"


@pytest.mark.docs
def test_basis_codes_of_the_contract_have_words():
    """Каждый код базиса П§0.2 — в словаре витрины: код без подписи на экран не выходит (№ 62)."""
    text = PAYLOAD_DOC.read_text(encoding="utf-8")
    line = text[text.index("* **Базис.**"):text.index("* **Нераскрытое")]
    codes = set(re.findall(r"`([a-z]+)`\s+\(", line))
    assert {"ifrs", "ras", "mgmt", "engine", "regulatory", "sector"} <= codes, codes
    basis = re.search(r"const BASIS = \{(.*?)\};", APP_CODE).group(1)
    assert codes <= set(re.findall(r"(\w+): \"", basis)), codes - set(re.findall(r"(\w+): \"", basis))
    for d in (fixture(), generic()):
        used = {i["basis"] for i in d["guidance"]["items"]} | {t["basis"] for t in d["indicators"]["tiles"]} | {d["meta"]["basis"], d["grid"]["basis"]}
        assert used <= set(re.findall(r"(\w+): \"", basis)), used


# ── фронт ничего не считает, кроме λ ──

@pytest.mark.tact
def test_the_front_computes_nothing_but_the_books_lambda_rule():
    assert APP_CODE.count("low_draws") == APP_CODE.count("head.low_draws"), "прогоны читаются только из заголовка"
    readers = {m.group(1) for m in re.finditer(r"function (\w+)\(", APP_CODE)
               if "low_draws" in function_body(m.group(1))}
    assert readers <= {"centresAt", "hero"}, f"прогоны читают {sorted(readers)}"
    dist = function_body("distributionChart")
    reducers = [m.start() for m in re.finditer(r"\.reduce\(", APP_CODE)]
    start = APP_CODE.index("function distributionChart(")
    assert all(start <= pos < start + len(dist) for pos in reducers), "суммы — только в сглаживании плотности"
    for forbidden in ("/ market", "/ price", "/ mk.price", "/ d.market.price", "cap /", ".cap /", "- bv_v", "- row.bv_v", "median / ",
                      "printed_median /", "/ head.market", ".dps /", "n20_post_dividend -", "- a.req20_now", "* N_out", "shares.outstanding_mln /"):
        assert forbidden not in APP_CODE, f"витрина считает сама: «{forbidden}»"
    hero = function_body("hero")
    assert "row.p_below_market" in hero and "row.market_percentile" in hero and "row.upside" in hero
    assert "g.sum_signed" in function_body("governanceCard"), "итог дисконта — число выпуска"
    for field in ("n20_headroom", "market_pb", "fair_pb_median", "excess_market", "dividend_yield_fwd", "yield"):
        assert field in APP_CODE, field


@pytest.mark.tact
def test_the_slider_rebuilds_the_median_from_the_release_draws():
    q = function_body("quantile7")
    assert "(n - 1) * q" in q and "Math.floor(h)" in q and "Math.min(lo + 1, n - 1)" in q
    assert "lo + lam * (head.high_draws[i] - lo)" in function_body("centresAt")
    at = function_body("headlineAt")
    assert "roundHalfUp(" in at and "head.print_step" in at and all(x in at for x in ("q(0.5)", "q(0.1)", "q(0.9)", "q(0.25)", "q(0.75)"))
    assert "roundHalfEven" not in APP_CODE, "печать — половиной вверх, как ядро"
    assert re.search(r"function roundHalfUp\(x\) \{\s*return Math\.floor\(x \+ 0\.5", APP_CODE)
    assert "view.low + lam * (view.high - view.low)" in function_body("pointAt")


@pytest.mark.tact
def test_the_sliders_steps_are_the_lambda_grid():
    assert "step: String(lambdaStep(d))" in function_body("hero"), "шаг ползунка — lambda_step выпуска"
    assert "lambda_step" in function_body("lambdaStep")
    d = fixture()
    head = d["fair_value"]["headline"]
    step = head["lambda_step"]
    for key in ("headline", "bank_first_line"):
        rows = (head if key == "headline" else d["fair_value"]["bank_first_line"])["by_lambda"]
        grid = [round(r["lambda"], 9) for r in rows]
        want = [round(i * step, 9) for i in range(round(1 / step) + 1)]
        assert all(g in grid for g in want), f"{key}.by_lambda не покрывает сетку ползунка"
    assert abs(step * 20 - 1) < 1e-12


# ── правило λ на прогонах фикстуры ──

def _q7(values, q):
    n = len(values)
    h = (n - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, n - 1)
    return values[lo] + (h - lo) * (values[hi] - values[lo])


def _half_up(x, step):
    return float((Decimal(repr(x)) / Decimal(repr(step))).quantize(Decimal(1), rounding=ROUND_HALF_UP) * Decimal(repr(step)))


def _at(head, lam):
    c = sorted(a + lam * (b - a) for a, b in zip(head["low_draws"], head["high_draws"]))
    return c


@pytest.mark.tact
@FORMS
def test_the_lambda_rule_reproduces_the_headline_and_the_table(form):
    d = form()
    head = d["fair_value"]["headline"]
    lam = head["own_macro_confidence"]
    c = _at(head, lam)
    assert abs(_q7(c, 0.5) - head["median"]) <= 0.005
    assert abs(_q7(c, 0.1) - head["band80"][0]) <= 0.005 and abs(_q7(c, 0.9) - head["band80"][1]) <= 0.005
    assert head["printed_median"] == _half_up(head["median"], head["print_step"])
    assert head["printed_band80"] == [_half_up(v, head["print_step"]) for v in head["band80"]]
    main = d["meta"]["company"]["main_ticker"]
    for row in head["by_lambda"]:
        c = _at(head, row["lambda"])
        for q, key in ((0.5, "median"), (0.1, "p10"), (0.25, "p25"), (0.75, "p75"), (0.9, "p90")):
            assert abs(_q7(c, q) - row[key]) <= 0.005, (row["lambda"], key)
        assert abs(sum(1 for v in c if v < d["market"]["prices"][main]["price"]) / len(c) - row["p_below_market"]) <= 1e-6
    book = next(r for r in head["by_lambda"] if abs(r["lambda"] - lam) < 1e-9)
    assert book["median"] == head["median"] and book["p_below_market"] == head["p_below_market"]


# ── синтетический выпуск держит контракт ──

HASH_EXCLUDED_META = ("generated_at", "published_at", "payload_sha256", "previous_sha256", "bytes")


def _content(payload):
    p = json.loads(json.dumps(payload, ensure_ascii=False))
    for k in HASH_EXCLUDED_META:
        p["meta"].pop(k, None)
    p["live"].pop("fetched_at", None)
    p["nowcast"]["journal"].pop("releases", None)
    for e in p["nowcast"]["journal"].get("entries", []):
        e.pop("release_sha", None)
    p.pop("changes", None)
    p.pop("valuation_history", None)
    return p


def _finite(node, where="выпуск"):
    if isinstance(node, float):
        assert math.isfinite(node), where
    elif isinstance(node, dict):
        for k, v in node.items():
            _finite(v, f"{where}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _finite(v, f"{where}[{i}]")


@pytest.mark.docs
@FORMS
def test_the_sample_release_follows_the_contract(form):
    d = form()
    assert d["schema"] == SCHEMA
    assert [b for b in required_top_level() if b not in d] == []
    _finite(d)
    meta = d["meta"]
    compact = dict(d, meta={k: v for k, v in meta.items() if k not in ("published_at", "bytes")})
    size = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    assert meta["bytes"] == size <= MAX_BYTES, (meta["bytes"], size)
    canon = json.dumps(_content(d), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert meta["payload_sha256"] == hashlib.sha256(canon).hexdigest(), "хэш содержания (П§0.4)"
    company = meta["company"]
    assert company["main_ticker"] in company["tickers"] and "ticker" not in company
    for key in ("market_by_ticker", "p_below_by_ticker", "upside"):
        assert set(d["fair_value"]["headline"][key]) == set(company["tickers"]), key
    assert d["market"]["price"] == d["market"]["prices"][company["main_ticker"]]["price"]
    assert len(d["fair_value"]["headline"]["low_draws"]) == len(d["fair_value"]["headline"]["high_draws"]) == d["fair_value"]["headline"]["draws"]
    assert "rows" not in d["market"]["brokers"], "цели по брокерам — только агрегаты"


@pytest.mark.tact
@FORMS
def test_the_sample_release_keeps_the_identities(form):
    """Тождества П§7, которые витрина печатает рядом друг с другом."""
    d = form()
    fv = d["fair_value"]
    lam = fv["own_macro_confidence"]
    assert abs(fv["central"] - (fv["low"] + lam * (fv["high"] - fv["low"]))) <= 0.01
    mix = d["layers"]["headline_mix"]
    assert abs(mix["price"] - fv["central"]) <= 0.01
    wf = {r["key"]: r["amount"] for r in mix["waterfall"]}
    assert abs(wf["bv_v"] + wf["pv_ri_explicit"] + wf["pv_terminal"] - wf["v0"]) <= 0.05
    assert abs(wf["v0"] + wf["governance"] + wf["bridge"] - wf["equity"]) <= 0.05
    shares, g, pend = d["meta"]["shares"], d["meta"]["governance_discount"], fv["bridge"]["pending_dividend"]
    n_div = shares.get("divisor_mln", shares["outstanding_mln"])                       # делитель выпуска (М§8.4)
    assert abs(mix["price"] - ((mix["v0"] - pend) * (1 - g) + pend + mix["bridge"]) * 1000 / n_div) <= 0.02, "цена смеси — формулой М§8.2 на делителе"
    assert abs(d["market"]["multiples"]["bv_per_share"] - fv["bank_first_line"]["bv_v"] * 1000 / n_div) <= 0.01
    assert abs(fv["bridge"]["amount"] - sum(r["amount"] * r["sign"] for r in fv["bridge"]["rows"])) <= 0.05
    for key in ("analytical", "market_implied", "macro_neutral"):
        L = d["layers"][key]
        assert abs(sum(L["world_weights"].values()) - 1) <= 1e-9
        assert abs(L["v0"] - (L["bv_v"] + L["pv_ri_explicit"] + L["pv_terminal"])) <= 0.05
    for p in ("p_analytical", "p_market_implied", "p_neutral"):
        assert abs(sum(c[p] for c in d["grid"]["cells"]) - 1) <= 1e-5, p
    assert len({(c["world"], c["regime"], c["scenario"]) for c in d["grid"]["cells"]}) == 36
    b = d["capital"]["bridge"]
    assert abs(b["start"] + sum(r["pp"] for r in b["rows"]) - b["end"]) <= 1e-6
    for row in d["paths"]["roe_tree"]:
        assert abs(row["roa"] * row["leverage"] - row["roe"]) <= 1e-5
    assert abs(sum(c["share"] for c in fv["headline"]["contributions"]) - 1) <= 1e-6
    bfl = fv["bank_first_line"]
    assert abs(bfl["market_pb"] - d["market"]["cap"] / bfl["bv_v"]) <= 1e-4 and bfl["market_pb"] == d["market"]["multiples"]["pb"]
    assert abs(bfl["excess_market"] - (d["market"]["cap"] - bfl["bv_v"])) <= 0.05
    assert abs(fv["rates_view"]["rub"] - (fv["rates_view"]["high"] - fv["rates_view"]["low"])) <= 0.01
    assert d["governance"]["sum_signed"] == d["governance"]["discount"]
    for r in d["dividends"]["register"]:
        assert 0 < r["dps"] < 0.5 * d["market"]["price"] and r["ex_date"] == r["record_date"]
    if d["dividends"]["policy"].get("history_test", "exact") == "exact":
        assert all(r["ok"] for r in d["dividends"]["formula_check"]) and {2024, 2025} <= {r["year"] for r in d["dividends"]["formula_check"]}
    else:                                              # вид теста `cap`: формулы «до копейки» нет, тест несут строки потолка
        assert d["dividends"]["formula_check"] == [] and any(r["complete"] and r["ok"] for r in d["dividends"]["cap_check"])
    assert d["checks"]["invariants_broken"] == 0
    for g in d["checks"]["gates"]:
        if g["fired"]:
            assert g["explanation"] and g["valid_until"] >= d["meta"]["valuation_date"], g["name"]
    assert abs(sum(r["prior"] for r in d["regimes"]["rows"].values()) - 1) <= 1e-9
    assert abs(sum(r["posterior"] for r in d["regimes"]["rows"].values()) - 1) <= 1e-5


@pytest.mark.tact
def test_the_generic_form_speaks_the_w1_contract():
    """Общая форма — в полях и единицах волны W1 каркаса."""
    d = generic()
    t = d["nii"]["transmission"]
    assert 0.05 < t["roe_equiv"] < 5, "roe_equiv — п.п. ROE на 1 п.п. ключевой (доля на долю)"
    lo, hi = t["pairs_range"]
    keys = [p["key_from"] for p in t["pairs"]] + [t["pairs"][-1]["key_to"]]
    assert keys == sorted(keys) and all(p["inside"] == (lo <= p["value"] <= hi) for p in t["pairs"])
    retro = d["nowcast"]["retro"]
    for block in [retro, *retro["by_horizon"].values()]:
        assert set(block["rmse"]) == set(block["bias"]) == set(block["n"]) <= set(block["titles"])
        for k, bias in block["bias"].items():
            errs = [p["benchmarks"][k] - p["actual"] for p in block["periods"] if k in p["benchmarks"]]
            assert len(errs) == block["n"][k] and abs(sum(errs) / len(errs) - bias) <= 0.01, f"смещение {k} — млрд ₽ (эталон − факт)"
    nx = d["dividends"]["next_expected"]
    annual = d["dividends"]["policy"].get("frequency") == "annual" and "model_quarters" in d["dividends"]
    main = nx["dps_mean"] if annual else nx["dps_policy"]
    assert nx["status"] != "model" or nx["dps"] == main, "главная цифра без объявления — DPS политики (годовой плательщик — ожидание)"
    assert nx["dps_mean"] <= nx["dps_policy"] and 0 <= nx["p_cancel"] <= 1
    assert d["nowcast"]["year"]["dps_model"] == nx["dps_policy"] and d["market"]["multiples"]["dividend_yield_fwd"] == nx["yield"]
    assert {"n1_0", "n1_2"} <= set(d["capital"]["titles"])
    kinds = {i["key"]: i["kind"] for i in d["guidance"]["items"]}
    assert kinds["n20_0"] == "min" and set(kinds.values()) <= {"point", "min", "max", "range"}
    rows = d["judgements"]["rows"]
    assert all(isinstance(j["in_band"], bool) for j in rows)
    assert all(j["share"] is None and j["rank_corr"] is None for j in rows if not j["in_band"])
    assert all(j["in_band"] for j in rows), "книга 1.2: все оси в полосе (В1)"
    assert {c["judgement_key"] for c in d["fair_value"]["headline"]["contributions"]} <= {j["id"] for j in rows if j["in_band"]}
    assert all(isinstance(a["cir_mgmt"], float) for a in d["paths"]["annual"])
    near = d["regimes"]["near_nim_shift"]
    assert near[0]["period"] == d["meta"]["first_period"] and near[-1]["value"] == 0
    gates = {g["name"]: g for g in d["checks"]["gates"]}
    assert {"nim_path_joint", "transmission_pairs"} <= set(gates)
    assert all(len(g["cell_list"]) <= 10 and set(g["corridor"]) == {"text", "value"} for g in gates.values())
    assert "ni_jump" in {f["name"] for f in d["checks"]["flags"]}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["nowcast"]["admission"]["earliest_decision"])
    assert {"tau_eff", "days"} <= set(d["next_report"]["expectation"]) and "snapshot" in d["changes"]


UNIT_CODES = {"pct", "share", "pp", "bp", "bn", "rub", "price", "number", "years", "level", "mix", "dict", "count", "version", "date", "period"}
SERVICE_TEXT = re.compile(r"(?<![\w.])[a-z]+(?:_[a-z0-9]+)+(?![\w])|\b(?:true|false|inf)\b|\b\d{4}[MQ]\d{1,2}\b|\(-?inf|valuation\.uncertainty")


def _printed_strings(node, key=None):
    """Строки выпуска, которые витрина печатает как есть (П§0.2): title, name, note, message, detail, source, equation."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _printed_strings(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _printed_strings(v, key)
    elif isinstance(node, str) and key in ("title", "name", "note", "message", "detail", "source", "equation", "what", "explanation", "scope_note", "valid_until_note"):
        if not (key == "name" and re.fullmatch(r"[a-z0-9_]+", node)):       # имя проверки или гейта — ключ, печатается его `title`
            yield key, node


@pytest.mark.tact
def test_the_generic_form_speaks_the_w2_contract():
    """Общая форма — в полях и формах волны W2 каркаса."""
    d = generic()
    # № 58, В7: строк книги по разделам нет; источник суждения — словами
    assert "sections" not in d["book"]
    rows = d["judgements"]["rows"]
    for j in rows:
        assert j["source"] and len(j["source"]) <= 80 and not j["source"].startswith("valuation."), j["id"]
        want = None if j["kind"] == "dict" else (j["price_high"] + j["price_low"] - 2 * d["fair_value"]["central"]) / 6
        assert (j["mean_shift"] is None) == (want is None) and (want is None or abs(j["mean_shift"] - want) <= 0.01), j["id"]
    off = d["judgements"]["off_band_shift"]
    assert set(off) == {"rub", "limit", "axes"} and off["axes"] == sum(1 for j in rows if not j["in_band"])
    assert abs(off["rub"] - sum(j["mean_shift"] or 0 for j in rows if not j["in_band"])) <= 1e-9
    assert off["limit"] == d["fair_value"]["headline"]["print_step"] / 2
    # № 25, № 12: D_pend и слагаемое опорного капитала
    assert d["fair_value"]["bridge"]["pending_dividend"] == 0.0 and "v0_agm_adjustment" in d["fair_value"]["jump_guard"]
    # № 59: число клеток и их список
    gap = d["capital"]["capital_gap"]
    assert isinstance(gap["cells"], int) and isinstance(gap["cell_list"], list) and len(gap["cell_list"]) == min(gap["cells"], 10)
    # № 14: отмена кризисом — не урезание капиталом
    assert not any({"dividend_cut", "crisis_skip"} <= set(c["flags"]) for c in d["grid"]["cells"])
    # № 17, № 62: сектор и нормативы — своими базисами; «лучше сектора» не сравнивается
    items = {i["key"]: i for i in d["guidance"]["items"]}
    assert items["n20_0"]["basis"] == "regulatory" and all(i["scope"] in ("group", "sector") for i in items.values())
    for i in items.values():
        assert (i["scope"] == "sector") == (i["basis"] == "sector") == (i["relation"] in ("in_line", "above")), i["key"]
        if i["relation"] == "above":
            assert i["status"] == "n/a" and i["mass_outside"] is None
    assert {r["key"] for r in d["guidance"]["revisions"]} <= set(items)
    # № 16, № 19, № 22: эквивалент — уровень; ЧПМ режимы не учит при равных ожиданиях; местный наклон и размах
    nr = d["next_report"]
    ni = nr["expectation"]["ni"]
    for kind in ("cor", "nim"):
        eq = nr["neutral"][kind]["ni_equivalent"]
        assert abs(eq / ni - 1) < 0.1, f"{kind}: ni_equivalent — ЧП квартала при нейтральном значении, рядом с expectation.ni"
        table = nr[f"{kind}_table"]
        assert nr["reaction"][kind] == {"d_median_min": min(r["d_median"] for r in table), "d_median_max": max(r["d_median"] for r in table)}
        assert nr["slope"][f"at_{kind}"] in ("neutral", "expectation")
    assert len({r["nim_mgmt"] for r in nr["expectation"]["by_regime"]}) == 1 and nr["neutral"]["nim"]["ni_equivalent"] == ni
    assert len({json.dumps(r["posterior"], sort_keys=True) for r in nr["nim_table"]}) == 1, "строки ЧПМ вероятностей режимов не меняют"
    # № 15: сверка — в единицах строки, с видом допуска
    cm = d["checks"]["control_model"]["rows"]
    for r in cm:
        assert r["unit"] in UNIT_CODES and r["tol_kind"] in ("rel", "abs") and abs(r["diff"] - (r["control"] - r["core"])) <= 1e-6, r["what"]
        assert r["diff_rel"] is None if r["core"] == 0 else abs(r["diff_rel"] - (r["control"] / r["core"] - 1)) <= 1e-6, r["what"]
    assert any(abs(r["diff"]) > 1 and r["ok"] for r in cm), "есть строка с |diff| > 1 в допуске: абсолютная разность — не проценты"
    assert {r["tol_kind"] for r in cm} == {"rel", "abs"} and any("tol_abs" in r for r in cm)
    # № 33: срок политики — дата утверждения + 3 года; коды книги — как у ядра
    pol = d["dividends"]["policy"]
    assert pol["valid_until"] == f"{int(pol['approved'][:4]) + 3}{pol['approved'][4:]}" and pol["valid_until_note"]
    assert pol["base"] == "ifrs_ni_shareholders" and pol["divisor"] == "issued" and pol["crisis"]["catch_up"] is True
    # № 44, № 46: консенсус — только T-30; запись журнала несёт версию книги
    retro = d["nowcast"]["retro"]["by_horizon"]
    assert "consensus" in retro["T-30"]["rmse"] and "consensus" not in retro["T-90"]["rmse"] and "consensus" not in retro["T-90"]["titles"]
    assert all("consensus" not in p["benchmarks"] for p in retro["T-90"]["periods"])
    assert all("book_version" in e for e in d["nowcast"]["journal"]["entries"])
    # № 60: у месячных плиток дата — период; мин и макс — за окно истории
    monthly = [t for t in d["indicators"]["tiles"] if t["date"] and re.fullmatch(r"\d{4}M\d{2}", t["date"])]
    assert len(monthly) >= 4
    for t in d["indicators"]["tiles"]:
        if t["status"] != "missing":
            assert t["min"]["value"] == min(t["history"]["value"]) and t["max"]["value"] == max(t["history"]["value"]), t["id"]
            assert t["min"]["date"] in t["history"]["date"] and t["date"] == t["history"]["date"][-1]
    # В2, В8: окно наблюдений, год шока сдвигом, сдвиг спредов по сторонам баланса, пол LT-спреда
    crisis = d["regimes"]["rows"]["crisis"]["crisis"]
    assert d["regimes"]["update"]["window_obs"] == 4 and crisis["shock_year"] == int(d["meta"]["anchor_period"][:4]) + crisis["shock_year_offset"]
    t = d["nii"]["transmission"]
    assert 0 <= t["sigma0_split"] <= 1 and t["sigma0"] * t["sigma0_liab"] <= 0
    for b in d["nii"]["books"]:
        assert set(b["spread_lt_world"]) == set(d["worlds"]["order"]), b["key"]
        assert b["spread_floor"] is None or min(b["spread_lt_world"].values()) >= b["spread_floor"], f"{b['key']}: гейт lt_spread_floor в фикстуре тих"
    assert sum(1 for b in d["nii"]["books"] if b["spread_floor"] is not None) == 3
    gates = {g["name"] for g in d["checks"]["gates"]}
    assert {"lt_spread_floor", "off_band_shift"} <= gates and len(gates) == 19
    # № 28, № 68: пояснения строк разложения; строка фактов — период
    assert all("note" in r for r in d["changes"]["vs_previous"]["rows"]) and d["changes"]["vs_previous"]["walk_book"] == []
    assert any("входит в строку" in r["note"] for r in d["changes"]["vs_previous"]["rows"])
    facts = next(r for r in d["inputs"]["rows"] if r["key"] == "facts")
    assert facts["unit"] == "period" and re.fullmatch(r"\d{4}Q[1-4]", facts["value"])
    assert d["governance"]["discount"] == d["meta"]["governance_discount"] == 0.004      # В16


@pytest.mark.tact
def test_the_generic_form_speaks_the_w3_contract():
    """Общая форма — в полях и формах волны W3 каркаса."""
    d = generic()
    money = 0.05
    # № 83: строка FVC и разовые статьи; строки года сходятся к прибыли до налога (П§7 п. 11)
    for a in d["paths"]["annual"]:
        rows = a["nii"] - a["llp"] - a["fvc"] + a["fees"] + a["insurance"] + a["other"] + a["noncore"] - a["opex"] + a["one_off"]
        assert abs(a["pbt"] - rows) <= money, a["year"]
    assert any(a["one_off"] for a in d["paths"]["annual"]) and all(a["fvc"] > 0 for a in d["paths"]["annual"])
    # № 82: год нау-каста — на одном слое: без новости dps = dps_model; ошибка года шире квартальной; интервал — dps ± выплата с ошибки
    y, q = d["nowcast"]["year"], d["nowcast"]["quarter"]["by_target"]["ni_q"]
    per_share = lambda bn: bn * y["payout"] * 1000 / d["meta"]["shares"]["issued_mln"]  # noqa: E731
    assert abs(y["ni_year"] - (y["ni_fact"] + y["ni_quarter"] + y["ni_rest"])) <= money and abs(y["base"] - (y["ni_year"] - y["at1_coupon_after_tax"])) <= money
    assert q["deviation"] != 0 and abs((y["dps"] - y["dps_model"]) - per_share(q["deviation"])) <= 2e-4, "нау-каст двигает год только своим отклонением"
    assert y["ni_year_se"] > q["std_error"] and abs((y["dps_interval"][1] - y["dps_interval"][0]) / 2 - per_share(y["ni_year_se"])) <= 2e-4
    cor = d["nowcast"]["quarter"]["by_target"]["cor_q"]
    assert cor["interval"] is None and cor["std_error"] is None and cor["forecast"] == cor["expectation"], "нау-каст без моста — ожидание модели, без интервала"
    # № 84: провалы истории — по базисам, диапазоны одного базиса не пересекаются; годовые упр. метрики — годовой узел
    gaps = d["history"]["gaps"]
    assert {g["basis"] for g in gaps} == {"ifrs", "mgmt"} and len(gaps) == len({g["basis"] for g in gaps})
    quarters = {x["period"]: x for x in d["history"]["quarters"]}
    span = lambda g: g["period"].split("–")  # noqa: E731
    for g in gaps:
        lo, hi = span(g)
        for period, row in quarters.items():
            inside = lo <= period <= hi
            value = row["ifrs"]["ni_sh"] if g["basis"] == "ifrs" else row["mgmt"]["nim"]
            assert (value is None) == inside, (g["basis"], period)
    mgmt = [x["mgmt"]["nim"] for x in d["history"]["quarters"]]
    first_gap = mgmt.index(None)
    assert first_gap > 0 and any(v is not None for v in mgmt[first_gap:]), "провал упр. метрик — в середине ряда: линия рвётся"
    assert all(a["mgmt"]["nim"] is not None for a in d["history"]["annual"]), "год с неполными кварталами несёт годовой узел фактов, а не среднее трёх кварталов"
    # № 98: единицы плиток — коды П§0.2, базис — коды (рынок — market, нормативы банка — regulatory)
    tiles = {t["id"]: t for t in d["indicators"]["tiles"]}
    assert {t["unit"] for t in tiles.values()} == {"bn", "share", "price", "level"} and all(t["unit"] in UNIT_CODES for t in tiles.values())
    assert tiles["n1_0"]["basis"] == tiles["n1_1"]["basis"] == "regulatory" and tiles["f123_capital"]["basis"] == "ras"
    assert {t["basis"] for t in tiles.values()} == {"ras", "regulatory", "market"}
    # № 100: дата формы ЦБ — окно оценки, не точная дата
    form = next(e for e in d["calendar"]["events"] if e["kind"] == "form102")
    ras = d["calendar"]["next_ras"]
    assert form["precision"] == "window" and form["confirmed"] is False and form["earliest"] == form["date"] == ras["form102_date_est"] < form["latest"] == ras["form102_latest_est"]
    # В12: сжатие φ — по сторонам баланса; флаг phi — у книг обеих сторон; кредитная маржа миров
    t = d["nii"]["transmission"]
    assert abs(t["phi_assets"] - t["phi_split"] * t["phi"]) <= 1e-6 and t["phi_liab"] > 0 and set(t["loan_margin"]) == set(d["worlds"]["order"])
    assert {b["side"] for b in d["nii"]["books"] if b["phi"]} == {"asset", "liability"}
    # В15, № 87: пол вероятности режима; слагаемое сторожа без записи реестра
    assert 0 < d["regimes"]["update"]["floor_share"] < 1
    assert {"unregistered_dividend", "unregistered_dps"} <= set(d["fair_value"]["jump_guard"])
    # В17: истекающее объяснение и истёкшая политика — флаги; первый поднят вместе с признаком гейта
    flags = {f["name"]: f for f in d["checks"]["flags"]}
    assert {"explanation_expiring", "policy_expired"} <= set(flags)
    assert flags["explanation_expiring"]["raised"] == any(g["fired"] and g["expiring"] for g in d["checks"]["gates"])
    assert flags["policy_expired"]["raised"] == (d["dividends"]["policy"]["valid_until"] < d["meta"]["valuation_date"])
    # № 102: «оценка капитала» в мосте; снимки гайденса по датам — смен значения меньше, чем строк
    titles = {r["key"]: r["title"] for r in d["layers"]["headline_mix"]["waterfall"]}
    assert titles["v0"] == "Оценка капитала V0" and not any("тоимость капитала V0" in v for v in titles.values())
    rev = d["guidance"]["revisions"]
    dates = sorted({r["date"] for r in rev})
    assert len(rev) == len(dates) * len(d["guidance"]["items"]) and len(dates) >= 3
    changes = sum(1 for a in rev for b in rev if a["key"] == b["key"] and dates.index(b["date"]) == dates.index(a["date"]) + 1 and a["value"] != b["value"])
    assert 0 < changes < len(d["guidance"]["items"])
    # № 99, № 101: единица оси — код (срок — years, коэффициент — number); оси-словари несут оба конца по ключам; строка без оси в обратном расчёте
    rows = {j["id"]: j for j in d["judgements"]["rows"]}
    assert rows["fvoci_maturity"]["unit"] == "years" and rows["kappa"]["unit"] == "number"
    dicts = [j for j in rows.values() if j["kind"] == "dict"]
    assert len(dicts) == 2 and all(set(j["book"]) == set(j["low"]) == set(j["high"]) for j in dicts)
    reg = next(r for r in d["reverse_dcf"]["rows"] if r["key"] == "reg_mix")
    assert reg["range"][0] == reg["range"][1] and reg["solved"] is None and reg["status"] == "unreachable"
    # № 105: в истории дивидендов есть нулевой год и год с выплатой меньше рубля
    dps = [h["dps"] for h in d["dividends"]["history"]]
    assert 0.0 in dps and any(0 < v < 1 for v in dps)
    assert d["nii"]["disclosed"]["nii_per_100bp"] is None and d["nii"]["disclosed"]["src"], "нераскрытое — null с причиной (№ 103)"
    assert d["meta"]["book_version"] == "1.3"


@pytest.mark.tact
def test_the_generic_form_speaks_the_w4_contract():
    """Общая форма после проверки W3 каркаса (печать по виду допуска, источники словами, счётчики)."""
    d = generic()
    # P4, verify-num № 7: дисконт за управление 0,004 — и ключ, и сумма каналов, и строки суждений и обратного расчёта
    g = d["governance"]
    assert g["discount"] == g["sum_signed"] == d["meta"]["governance_discount"] == 0.004
    assert abs(sum(c["value"] * c["sign"] for c in g["components"]) - g["discount"]) <= 1e-12, "сумма каналов равна дисконту"
    assert next(j for j in d["judgements"]["rows"] if j["id"] == "governance")["book"] == 0.004
    assert next(x for x in d["reverse_dcf"]["rows"] if x["key"] == "governance")["book"] == 0.004
    # P7, verify-deploy № 6: сдвиг доли в сверке — единицей `pp` (как у писателя сводки); шум счёта в разности — не ноль в данных
    cm = d["checks"]["control_model"]["rows"]
    shifts = [x for x in cm if x["unit"] == "pp"]
    assert len(shifts) >= 2 and all(x["tol_kind"] == "abs" for x in shifts) and any("σ0" in x["what"] for x in shifts)
    assert any(0 < abs(x["diff"]) < x["tol"] * 1e-6 and x["ok"] for x in shifts), "есть строка, где разность — шум счёта: на экране она ноль"
    # P7, verify-deploy № 4: ось в годах с дробным концом — «2,5 года»
    axis = next(j for j in d["judgements"]["rows"] if j["id"] == "fvoci_maturity")
    assert axis["unit"] == "years" and axis["low"] != int(axis["low"]) and axis["book"] == int(axis["book"])
    # P1, P7: источник истории дивидендов — решение собрания и раскрытие, сверка с брокерским календарём — словами
    sources = {h["src"] for h in d["dividends"]["history"]}
    assert len(sources) == 2 and all("собрани" in x and "раскрытие эмитента" in x for x in sources) and any("брокерским календарём" in x for x in sources)
    # P7, verify-deploy № 5: счётчики проверок — 2 сработавших гейта, 1 поднятый флаг; сработавшие гейты фикстуры считают клетки
    fired = [x for x in d["checks"]["gates"] if x["fired"]]
    assert len(fired) == 2 and all(x["cells"] > 0 for x in fired) and sum(1 for f in d["checks"]["flags"] if f["raised"]) == 1


@pytest.mark.tact
def test_the_panel_form_carries_the_panel_nodes():
    """Форма панели (П§2 «?», П§9): одна категория акций, делитель, дивиденды по периодам, узлы капитала и роста,
    путь к терминалу, мост трёх прибылей, месячная таблица; поля каркаса, которым нечего нести, пусты."""
    d = fixture()
    money = 0.05
    company, shares = d["meta"]["company"], d["meta"]["shares"]
    main = company["main_ticker"]
    assert company["tickers"] == [main] and [c["class"] for c in company["share_classes"]] == ["ordinary"]
    for node in (shares["by_ticker"], d["market"]["prices"], d["market"]["cap_by_ticker"], d["market"]["price_history"], d["fair_value"]["headline"]["upside"],
                 d["valuation_history"]["price"], d["live"]["prices"], d["dividends"]["next_expected"]["yield"]):
        assert list(node) == [main]
    # делитель и подписи базиса
    assert shares["divisor_basis"] == "issued" and shares["divisor_mln"] == shares["issued_mln"] - shares["economic_treasury_mln"] > shares["outstanding_mln"]
    assert shares["divisor_label"] == d["meta"]["basis_labels"]["divisor"] and set(d["meta"]["basis_labels"]) == {"profit", "roe", "divisor", "dividend_issued", "dividend_outstanding"}
    assert abs(d["market"]["cap"] - d["market"]["price"] * shares["divisor_mln"] / 1000) <= money
    assert [a["kind"] for a in shares["corporate_actions"]].count("split") == 1 and all(("factor" in a) == (a["kind"] == "split") for a in shares["corporate_actions"])
    issuer = d["history"]["ltm"]["roe_issuer"]
    assert set(issuer) == {"value", "as_of", "label"} and issuer["value"] != d["history"]["ltm"]["roe"]
    # дивиденды по периодам
    dv = d["dividends"]
    period = re.compile(r"\d{4}Q[1-4]")
    for rows in (dv["register"], dv["history"], d["market"]["ex_dividend"], d["fair_value"]["bridge"]["rows"]):
        assert rows and all(period.fullmatch(r["period"]) and r["label"].startswith("за ") and int(r["period"][:4]) == r["year"] for r in rows)
    assert len({r["period"] for r in dv["history"]}) == len(dv["history"]) > len({r["year"] for r in dv["history"]}), "в году несколько решений"
    assert 3 <= len(d["market"]["ex_dividend"]) <= 4, "три-четыре экс-даты за 12 месяцев"
    assert all(r["dps_pre_split"] is None and r["split_factor"] == 1 if r["period"] >= "2026Q1" else abs(r["dps_pre_split"] - r["dps"] * r["split_factor"]) <= 1e-9
               for r in dv["history"]) and all(r["dps_preferred"] is None and r["payout_ratio"] is None for r in dv["history"])
    pol = dv["policy"]
    assert pol["history_test"] == "cap" and pol["frequency"] == "quarterly" and pol["threshold"] == 0 and pol["steps"] == [] and pol["valid_until"] is None and pol["valid_until_note"]
    assert dv["formula_check"] == [] and len(dv["ladder"]) == 1 and d["capital"]["policy_threshold"] == 0
    for row in dv["cap_check"]:
        assert abs(row["share"] - row["pool"] / row["ni_shareholders"]) <= 1e-6 and (row["ok"] is None) == (not row["complete"]) and row["cap"] == pol["cap"]
    quarters = dv["model_quarters"]
    assert quarters and all(q["decision_period"] >= q["period"] and q["pay_period"] >= q["decision_period"] and q["dps_p10"] <= q["dps"] <= q["dps_p90"] for q in quarters)
    opened, decided = [q for q in quarters if not q["declared"]], {q["period"]: q for q in quarters if q["declared"]}
    assert all(q["dps"] <= q["dps_policy"] for q in opened) and not {q["period"] for q in opened} & {r["period"] for r in dv["register"] + dv["history"]}, \
        "открытые кварталы пути модели — без записи"
    # решённый квартал — как в настоящем выпуске: и в истории, и в реестре, и строкой пути (DPS решения рядом с DPS политики)
    assert set(decided) == {r["period"] for r in dv["register"]} <= {r["period"] for r in dv["history"]}
    assert all(decided[r["period"]]["dps"] == r["dps"] != decided[r["period"]]["dps_policy"] and r["decided_date"] for r in dv["register"])
    assert any(len(r["sources"]) == 3 for r in dv["register"]) and any(len(r["sources"]) == 2 for r in dv["register"]), "счёт источников записи — два и три"
    nx = dv["next_expected"]
    record = next(r for r in dv["register"] if r["period"] == nx["period"])
    assert nx["yield_period"] == "quarter" and nx["status"] == record["status"] and nx["dps"] == record["dps"] and nx["label"] == record["label"]
    assert abs(nx["yield"][main] - nx["dps"] / d["market"]["price"]) <= 1e-6 and nx["condition"]["threshold"] == 0
    known = {q["period"]: q["dps_policy"] for q in opened} | {r["period"]: r["dps"] for r in dv["register"]}
    start = sorted(known).index(nx["period"])
    four = sum(known[p] for p in sorted(known)[start:start + 4])
    assert abs(d["market"]["multiples"]["dividend_yield_fwd"][main] - four / d["market"]["price"]) <= 1e-4, "доходность вперёд — четыре ближайших квартала"
    annual = {a["year"]: a for a in d["history"]["annual"]}
    by_year = {}
    for r in dv["history"]:
        by_year.setdefault(r["year"], []).append(r)
    for year, rows in by_year.items():
        complete = any(r["period"].endswith("Q4") for r in rows) and len(rows) == 4
        assert (annual.get(year, {}).get("dps") is not None) == complete, year      # незавершённого года в годовой истории нет
        if complete:
            assert abs(annual[year]["dps"] - sum(r["dps"] for r in rows)) <= 1e-9
    # капитал: требование с глиссадой, рост, цена правила
    cap = d["capital"]
    req, growth = cap["requirement"], cap["growth"]
    n = len(req["periods"])
    assert n == 14 and all(len(v) == n for v in req["mix"].values()) and all(len(v) == n for s in req["by_scenario"].values() for v in s.values())
    assert all(g >= f for g, f in zip(req["mix"]["req20_glide"], req["mix"]["req20"])) and req["mix"]["req20_glide"] != req["mix"]["req20"], "глиссада набирает ступень заранее"
    assert all(len(growth[k]) == len(growth["years"]) for k in ("potential", "actual", "cut_share", "catch_up", "lam_min", "p_cut"))
    assert all(a is None or a <= p for a, p in zip(growth["actual"], growth["potential"])) and growth["order"] in ("dividend_first", "growth_first")
    assert len(growth["quarters"]["lam"]) == len(growth["quarters"]["periods"]) == 14 and set(growth["by_scenario"]) == set(cap["scenarios"])
    rules = cap["rule_price"]["rows"]
    assert [r["key"] for r in rules] == ["unconstrained", "dividend_first", "growth_first"] and [r["current"] for r in rules].count(True) == 1
    # книга с записью сухого перевывода: разности с точкой и медианой книги, медианы в рублях нет; без цены — причина
    assert all("median" not in r and ("why" in r) == (r["d_point"] is None) for r in rules) and all(r["d_point"] == r["d_median"] == 0.0 for r in rules if r["current"])
    anchor = cap["anchor"]
    assert anchor["estimated"] is True and anchor["at1"] == 0 and "n10_bank" not in anchor and cap["observed"]["n1_0"] is None and cap["observed"]["n1_2"] is None
    # находка A14: рост года якоря — число (факт конца прошлого года в фактах есть); навёрстывания нет
    assert isinstance(growth["potential"][0], float) and growth["catch_up_rate"] == 0 and not any(growth["catch_up"]) and growth["cut_share"] == sorted(growth["cut_share"])
    assert growth["p_cut"].index(max(growth["p_cut"])) > 0 and growth["lam_min"].index(min(growth["lam_min"])) > 0, "экстремумы рядов — не в году якоря"
    assert abs(anchor["n20_headroom"] - (anchor["n20_post_dividend"] - anchor["req20_now"])) <= 1e-6
    # путь к терминалу, три прибыли, пределы обратного расчёта
    fade = d["paths"]["fade"]
    assert fade["years"] == [a["year"] for a in d["paths"]["annual"]] and all(len(fade[k]) == len(fade["years"]) for k in ("roe", "bv_growth", "k"))
    assert fade["roe_t"] < fade["roe_t_raw"] and fade["roe_t"] == d["paths"]["terminal"]["roe_t"] and all(a["fvc"] == 0 for a in d["paths"]["annual"])
    for row in d["history"]["three_profits"]:
        assert abs(row["ni_shareholders"] - (row["ni_total"] - row["ni_nci"])) <= money
        assert abs(row["ni_operating"] - (row["ni_shareholders"] - row["stake_effect"] - row["debt_interest_effect"])) <= money, row["period"]
    bank = {r["key"]: r for r in d["reverse_dcf"]["bank_rows"]}
    assert set(bank) == {"implied_roe_through_cycle", "implied_cost_of_equity", "market_cap_minus_bv", "value_without_excess_growth", "book_value_per_share", "excess_return_years"}
    years = bank["excess_return_years"]
    cum = [r["pv_excess_cum"] for r in years["by_year"]]
    assert years["unit"] == "years" and cum == sorted(cum) and cum[years["implied"] - 1] >= years["market_excess"] > cum[years["implied"] - 2]
    assert abs(bank["book_value_per_share"]["implied"] - d["market"]["multiples"]["bv_per_share"]) <= 0.01 and "rub_per_1pp_buffer" in d["fair_value"]["bank_first_line"]
    # ближайший отчёт: месячная таблица панели, прогноз равен ожиданию модели
    nc = d["nowcast"]
    assert nc["months"]["rows"] == [] and nc["quarter"]["months"] == [] and len(nc["ops"]["rows"]) == 15 and "0,85–6,6" in nc["ops"]["note"]
    for target in nc["quarter"]["by_target"].values():
        assert target["ras_estimate"] is None and target["bridge"] is None and target["ras_bridged"] is None and target["w"] == 0 and target["forecast"] == target["expectation"]
    year = nc["year"]
    assert year["at1_coupon_after_tax"] == 0 and year["dps"] == year["dps_model"] and abs(year["ni_year"] - (year["ni_fact"] + year["ni_quarter"] + year["ni_rest"])) <= money
    # DPS года: «по политике» — сумма DPS политики четырёх кварталов; ожидание по клеткам — ниже (находка A15)
    first = dv["model"][0]
    assert abs(year["dps"] - sum(q["dps_policy"] for q in quarters if q["period"].startswith(str(year["year"])))) <= 1e-9 and first["dps_policy"] == year["dps"]
    assert abs(first["dps"] - sum(q["dps"] for q in quarters if q["period"].startswith(str(year["year"])))) <= 1e-4 and first["dps"] < first["dps_policy"]
    assert first["dps"] == d["paths"]["annual"][0]["dps"]
    months = [r["month"] for r in nc["ops"]["rows"]]
    assert months == sorted(months) and [x["month"] for x in nc["form102"]] == months[-3:] and nc["form102"][-1]["ok"] is None
    ras = d["calendar"]["next_ras"]
    assert ras["enters_via"] == "form102" and ras["date"] == ras["form102_date_est"] < ras["form102_latest_est"]
    events = d["calendar"]["events"]
    kinds = {e["kind"] for e in events}
    assert {"ops_release", "form102", "form805", "ifrs", "databook", "dividend_decision", "record", "pay", "call_option", "deal", "regulation", "cbr_rate"} <= kinds
    assert not kinds & {"agm", "ras", "investor_day"}, "виды годового собрания и релиза РСБУ принадлежат общей форме"
    for e in events:
        if e.get("estimated"):
            assert e["confirmed"] is False and e["precision"] == "window" and e["earliest"] <= e["date"] <= e["latest"], e["id"]
        assert ("in_book" in e) == (e["kind"] == "deal")
    assert {e["id"] for e in events if e["kind"] in ("record", "pay")} == {f"record-{nx['period']}", f"pay-{nx['period']}"}
    # проверки: гейты панели в конце списка, флаги панели — только поднятыми
    gates = [g["name"] for g in d["checks"]["gates"]]
    assert len(gates) == 28 and gates[-9:] == ["growth_cut", "step_dividend", "cir_lt", "wholesale_share", "payout_cap", "volume_sign", "stress_sign",
                                               "window_backtest", "funds_cost_to_key"]
    flags = d["checks"]["flags"]
    assert [f["name"] for f in flags[-2:]] == ["deal_pending", "capital_estimated"] and all(f["raised"] for f in flags[-2:]) and len(flags) == 11
    titles = {i["name"]: i["title"] for i in d["checks"]["invariants"]}
    assert "потолка политики" in titles["dps_history"] and "делитель" in titles["exdate_jump"]
    cells = d["grid"]["cells"]
    assert any("growth_cut" in c["flags"] for c in cells) and sum("growth_solver" in c["flags"] for c in cells) == 1 and d["grid"]["scenario_order"] == ["schedule", "mid", "strict"]
    items = {i["key"]: i for i in d["guidance"]["items"]}
    assert list(items) == ["op_np_growth", "dps_growth", "roe_target", "nim", "cor_max", "cir"] and "strategy" not in d["guidance"]
    assert all(items[k]["guidance"] is None and items[k]["status"] == "n/a" and items[k]["mass_outside"] is None for k in ("nim", "cor_max", "cir"))
    # находка A16: цель ROE эмитента стоит в другом базисе — путь модели не подставляется, строка не сравнивается; «нужно в остатке» у строк роста ядро не считает
    roe = items["roe_target"]
    assert roe["guidance"] == 0.3 and roe["model_year"] is None and roe["status"] == "n/a" and roe["mass_outside"] is None and "операционному капиталу" in roe["title"]
    assert all(i["required_rest"] is None for i in items.values())
    first_seen = {}
    for rev in d["guidance"]["revisions"]:
        first_seen[rev["key"]] = min(first_seen.get(rev["key"], rev["date"]), rev["date"])
    assert min(first_seen.values()) == first_seen["roe_target"] < first_seen["op_np_growth"], "цель без года названа раньше гайденса года (находка A47)"
    assert all(isinstance(j["in_band"], bool) and j["source"] and len(j["source"]) <= 80 for j in d["judgements"]["rows"])
    tiles = {t["id"]: t for t in d["indicators"]["tiles"]}
    assert tiles["ops_clients"]["unit"] == "number" and tiles["ops_clients"]["basis"] == "mgmt" and "не группы" in tiles["ops_np"]["note"]
    assert {t["basis"] for t in tiles.values()} == {"mgmt", "ras", "regulatory", "market"} and re.fullmatch(r"\d{4}Q[1-4]", tiles["n20_1"]["date"])
    assert set(d["meta"]["terms"]) == {"lt_level", "profit_short", "noncore", "cir", "roe_lt", "stake"} and all(d["meta"]["terms"].values()), "словарь терминов книги (П§2 meta.terms)"
    assert not re.search(r"сквозь цикл|ГОСА", json.dumps(d, ensure_ascii=False)), "термин общей формы в форму панели не попадает"


@pytest.mark.tact
def test_the_panel_form_carries_the_nodes_of_the_sixth_decisions():
    """Узлы панели (П§2, П§9): запас второго норматива, строка против требования и подписи двух строк Н20.1, база суммы
    дивиденда и окно доходности за 12 месяцев, суждение о марже ключом уровня, оси-связки, числа гейтов знака."""
    d = fixture()
    money = 0.05
    main = d["meta"]["company"]["main_ticker"]
    # капитал: запас второго норматива — число выпуска; с требованием сравнивается названная строка
    cap = d["capital"]
    anchor, req = cap["anchor"], cap["requirement"]
    assert abs(anchor["n11_headroom"] - (anchor["n11_bank"]["value"] - anchor["req11_now"])) <= 1e-6
    assert req["compare"] == {"n20": "n20", "n11": "n11_star"} and all(v in req["mix"] for v in req["compare"].values()) and set(req["notes"]) == {"n11_star", "n11"}
    assert len(req["years_mix"]["n11_star"]) == len(cap["years"]) and all(s >= n for s, n in zip(req["mix"]["n11_star"], req["mix"]["n11"]))
    assert any(n < g < s for n, g, s in zip(req["mix"]["n11"], req["mix"]["req11_glide"], req["mix"]["n11_star"])), \
        "случай проверки: отчётный норматив ниже требования с глиссадой, норматив с прибылью периода — выше"
    # дивиденды: база суммы и окно доходности за 12 месяцев
    dv, bridge, labels = d["dividends"], d["fair_value"]["bridge"], d["meta"]["basis_labels"]
    assert dv["amount_basis"] == "issued" and bridge["amount_basis"] == "outstanding" and labels["dividend_issued"] != labels["dividend_outstanding"]
    shares = d["meta"]["shares"]
    assert all(abs(r["amount"] - r["dps"] * shares["issued_mln"] / 1000) <= money for r in dv["register"])
    assert all(abs(r["amount"] - r["dps"] * shares["outstanding_mln"] / 1000) <= money for r in bridge["rows"])
    window = dv["yield_ltm_periods"]
    known = {r["period"]: r["dps"] for r in dv["history"]} | {r["period"]: r["dps"] for r in dv["register"] if r["status"] in ("declared", "paid")}
    assert len(window) == 4 and window == sorted(known)[-4:], "четыре последних объявленных квартала прибыли"
    assert abs(dv["yield_ltm"][main] - sum(known[p] for p in window) / d["market"]["price"]) <= 1e-6
    assert dv["yield_ltm"] == d["market"]["multiples"]["dividend_yield_ltm"]
    split = next(a for a in shares["corporate_actions"] if a["kind"] == "split")
    assert isinstance(split["factor"], (int, float)) and not isinstance(split["factor"], bool) and split["factor"] > 0
    # маржа после фазы роста: ключ цели — само суждение книги (стационарная маржа мира уровня); уровень мира-опоры — выведенное число
    trans = d["nii"]["transmission"]
    judged = trans["level"]
    assert set(judged) == {"world", "value", "reference_world", "reference_value"} and judged["value"] == trans["nim_lt_target_mgmt"]
    assert "nim_lt_printed" not in trans and "nim_stationary" not in trans, "у книги с ключом уровня узла гейта стационарной маржи нет"
    assert {judged["world"], judged["reference_world"]} <= set(d["worlds"]["order"]) and judged["world"] != judged["reference_world"] and judged["reference_value"] != judged["value"]
    rows = d["reverse_dcf"]["rows"]
    nim_rows = [r for r in rows if "stationary_book" in r]
    assert len(nim_rows) == 1 and nim_rows[0]["paths"] == ["nii.nim_lt_target_mgmt"] and nim_rows[0]["book"] == trans["nim_lt_target_mgmt"]
    assert nim_rows[0]["stationary_book"] == judged["value"] and nim_rows[0]["stationary_solved"] == nim_rows[0]["solved"] and "printed_book" not in nim_rows[0], \
        "стационарная маржа мира уровня равна значению книги и корню строки"
    assert set(nim_rows[0]["levels_solved"]) == set(d["paths"]["levels"]["order"])
    # список строк с уточнением на полной полосе: у прочих решение — корень подвыборки
    named = d["reverse_dcf"]["refine_rows"]
    assert named and set(named) < {r["key"] for r in rows} and all(r["gap_basis"] == ("full" if r["key"] in named and r["solved"] is not None else "subsample") for r in rows)
    assert any(r["status"] == "solved" and r["key"] not in named for r in rows), "случай проверки: решённая строка вне списка — «оценка по подвыборке»"
    edge = [r for r in rows if r.get("reason")]
    assert edge and all(r["status"] == "unreachable" and r["solved"] is None for r in edge), "корень на краю отрезка поиска решением не считается"
    # оси-связки: строка — значением и концами первого пути; вторая связка — премия роста средств клиентов: уровень первого года — число, а не сдвиг
    bundles = [j for j in d["judgements"]["rows"] if j["kind"] == "bundle"]
    assert {b["id"] for b in bundles} == {"flex", "funds_premium"}
    for b in bundles:
        assert all(list(b["ends"][k]) == b["paths"] for k in ("book", "low", "high")) and len(b["paths"]) > 1
        assert [b["book"], b["low"], b["high"]] == [b["ends"][k][b["paths"][0]] for k in ("book", "low", "high")]
        assert b["in_band"] and isinstance(b["mean_shift"], float) and not any(r["paths"] == b["paths"] for r in rows), "связка — не строка обратного расчёта"
        assert any(c["judgement_key"] == b["id"] and c["name"] == b["name"] for c in d["fair_value"]["headline"]["contributions"])
    premium = next(b for b in bundles if b["id"] == "funds_premium")
    assert premium["unit"] == "pp" and premium["book"] == 0 and premium["low"] < 0 < premium["high"], "центр премии — уровень первого пути (находка A17)"
    # гейты знака и цели маржи: в общем списке; узел числа и гейт — об одном
    checks = d["checks"]
    gates = {g["name"]: g for g in checks["gates"]}
    for name in ("volume_sign", "stress_sign"):
        assert gates[name]["fired"] is (not checks[name]["ok"]) and gates[name]["explanation"] and gates[name]["valid_until"] and gates[name]["message"]
    vs = checks["volume_sign"]
    assert abs(vs["d_point"] - (vs["point_free"] - vs["point"])) <= 0.005 and set(vs["d_world"]) == set(d["worlds"]["order"])
    assert "nim_stationary" not in gates and "nim_lt" not in gates and "наибольшем квартале окна фактов" in gates["window_backtest"]["message"]
    assert gates["funds_cost_to_key"]["fired"] is (not checks["funds_cost_to_key"]["ok"]) and set(checks["funds_cost_to_key"]["by_world"]) == set(d["worlds"]["order"])
    assert checks["stress_sign"]["mass_basis"] == "point" and checks["stress_sign"]["mass_analytical"] != checks["stress_sign"]["mass"] and "под вероятностями точки" in gates["stress_sign"]["message"]
    assert gates["stress_sign"]["mass"] == checks["stress_sign"]["mass"] and checks["stress_sign"]["max_excess"] == max(
        [c["dv"] for c in checks["stress_sign"]["loss"]["cells"]] + [c["d_profit"] for c in checks["stress_sign"]["requirement"]["cells"]])
    # слова: термины книги — в словаре выпуска; слов прежних волн в печатаемых строках нет
    assert {"cir", "roe_lt", "stake"} <= set(d["meta"]["terms"]) and gates["cir_range"]["title"].startswith(d["meta"]["terms"]["cir"])
    text = json.dumps(d, ensure_ascii=False)
    assert not re.search(r"как у образца|Этап 1:|CIR", text), "слова прежних волн в выпуск не идут"


@pytest.mark.tact
def test_the_front_reads_the_nodes_of_the_sixth_decisions_and_computes_none_of_them():
    """Витрина печатает числа и слова узлов решений № 6 из выпуска: запас второго норматива не вычитает, базу суммы дивиденда,
    термины книги и подписи строк Н20.1 не сочиняет, новые гейты печатает общим списком — без их имён в карточке проверок."""
    for field in ("n11_headroom", "nim_lt_printed", "printed_book", "printed_solved", "nim_stationary", "level", "reference_world", "reference_value", "stationary_book",
                  "stationary_solved", "levels_solved", "refine_rows",
                  "amount_basis", "yield_ltm_periods", "compare", "notes", "n11_star", "terms"):
        assert re.search(rf"\.{field}\b", APP_CODE), field
    assert "- anchor.req11_now" not in APP_CODE and "- a.req11_now" not in APP_CODE and "value - " not in function_body("passportRow"), "запас — число выпуска"
    for word in ("на акции в обращении", "на все размещённые", "неаудированного", "его сравнивает", "Яндекс", "после фазы роста"):
        assert word not in APP_CODE, f"слово выпуска в коде витрины: «{word}»"
    term = function_body("term")
    assert "terms" in term and all(f'term("{k}"' in APP_CODE for k in ("lt_level", "roe_lt", "cir", "noncore")), "термины книги — из словаря выпуска"
    # «stake» и «profit_short» печатал только мост трёх прибылей формы Т — карточка снята с витрины (DASHBOARD §1)
    assert APP_CODE.count('"C/I"') == 1 and "CIR" not in APP_CODE, "слово отношения расходов к доходам — термин книги, родовое — в одном месте"
    gates = function_body("gatesCard")
    assert not re.search(r"nim_lt|nim_stationary|window_backtest|funds_cost|volume_sign|stress_sign", gates), "новые гейты — в общем списке, без особых слов"
    assert all(f'gateNote(d, "{k}")' in APP_CODE for k in ("volume_sign", "stress_sign", "window_backtest", "nim_stationary")), "объяснение гейта — и в карточке его темы"
    assert all(f'"{k}"' in function_body("transmissionCard") for k in ("nim_lt", "nim_stationary", "funds_cost_to_key")) and "gateNote(d, k)" in function_body("transmissionCard")
    rule = function_body("rulePriceCard")
    assert "ruText(r.title)" in rule and "unconstrained" not in APP_CODE, "строки «цены правила» — подписями выпуска"
    assert 'r.kind === "bundle"' in function_body("judgementsCard") and "ends" not in function_body("judgementsCard"), "связка печатается первым путём: словари концов на экран не идут"
    path = function_body("ratioPathCard")
    assert 'obj(R.compare).n11 === "n11_star"' in path and "notes.n11_star" in path and "notes.n11)" in path
    assert "splitText" in function_body("sharesCard") and "isNum(a.factor)" in APP_CODE


@pytest.mark.tact
def test_the_panel_form_carries_the_nodes_the_headline_stands_on():
    """Узлы «на чём стоит заголовок» (П§2): уровни после фазы роста четырёх строк с долей кредитов и окно фактов — мерка для них,
    модальная клетка рядом с путём смеси, справочные варианты из таблиц книги по модулю цены, запас якоря до требования с глиссадой,
    счётчики сводки контрольной модели; числа согласованы с соседними узлами."""
    d = fixture()
    paths = d["paths"]
    lv, mc = paths["levels"], paths["modal_cell"]
    assert lv["order"] == ["modal_cell", "analytical", "point", "macro_neutral"] and set(lv["rows"]) == set(lv["order"]) and lv["to_year"] == d["grid"]["years"][-1]
    assert all(set(r) == {"title", "nim", "cor", "cir", "loans_share"} and r["title"] for r in lv["rows"].values())
    tail = [a for a in paths["annual"] if lv["from_year"] <= a["year"] <= lv["to_year"]]
    for key, field in (("nim", "nim_mgmt"), ("cor", "cor_mgmt"), ("cir", "cir_mgmt")):
        assert abs(lv["rows"]["point"][key] - sum(a[field] for a in tail) / len(tail)) <= 1e-6, f"смесь заголовка: {key} — среднее её годовых строк"
    shares = [lv["rows"][k]["loans_share"] for k in lv["order"]]
    assert shares == sorted(shares, reverse=True) and [lv["rows"][k]["nim"] for k in lv["order"]] == sorted((lv["rows"][k]["nim"] for k in lv["order"]), reverse=True), \
        "больше кредитов в процентных активах — выше маржа: состав баланса клетки"
    # окно фактов — отдельный подузел, не строка: наименьший, наибольший и средний квартал, доля кредитов окна и якоря
    win = lv["window"]
    assert set(win) == {"nim", "cor", "cir", "loans_share"} and "window" not in lv["rows"] and "window" not in lv["order"]
    assert all(set(win[k]) == {"min", "max", "mean"} and win[k]["min"] < win[k]["mean"] < win[k]["max"] for k in ("nim", "cor", "cir"))
    assert set(win["loans_share"]) == {"window", "anchor"} and win["loans_share"]["window"] < win["loans_share"]["anchor"] < min(shares)
    assert min(r["nim"] for r in lv["rows"].values()) > win["nim"]["max"], "случай проверки: маржа всех строк выше наибольшего квартала окна"
    gate = next(g for g in d["checks"]["gates"] if g["name"] == "window_backtest")
    assert gate["corridor"]["value"]["cor"] == [win["cor"]["min"], win["cor"]["max"]] and gate["corridor"]["value"]["cir"] == [win["cir"]["min"], win["cir"]["max"]]
    cell = next(c for c in d["grid"]["cells"] if f"{c['world']}/{c['regime']}/{c['scenario']}" == mc["cell"])
    assert mc["cell"] == lv["cell"] and mc["price"] == cell["price"] and mc["p_analytical"] == cell["p_analytical"] and 0 < mc["p_point"] < mc["p_analytical"]
    assert mc["years"] == [a["year"] for a in paths["annual"]] and len(mc["ni_sh"]) == len(mc["years"]) and mc["ni_sh"] != [a["ni_sh"] for a in paths["annual"]]
    book = d["book"]["reference_variants"]
    assert book["point"] == d["fair_value"]["central"] and len(book["rows"]) == 10 and len({r["id"] for r in book["rows"]}) == 10
    # книга с записью сухого перевывода развилок (М§14.5): строка без цены — последней, с причиной; у прочих — разность медиан
    priced = [r for r in book["rows"] if r["d_point"] is not None]
    assert book["rows"][len(priced):] == [r for r in book["rows"] if r["d_point"] is None] and all(r["why"] and r["point"] is None for r in book["rows"][len(priced):])
    assert all(isinstance(r["d_median"], float) and "why" not in r for r in priced) and book["basis"]
    moves = [abs(r["d_point"]) for r in priced]
    assert moves == sorted(moves, reverse=True) and book["rows"][0]["note"] and sum("note" in r for r in book["rows"]) == 1, \
        "строки — по убыванию модуля цены, главная развилка первой; подпись строки — там, где книга её дала"
    cm = d["checks"]["control_model"]
    assert cm["book_version"] == d["meta"]["book_version"] and cm["valuation_date"] <= cm["as_of"] and cm["n_rows"] > len(cm["rows"]) and cm["n_bad"] == 0 and cm["all_ok"] is True
    assert all(abs(r["point"] - book["point"] - r["d_point"]) <= 0.011 and r["title"] and not re.search(r"[a-z_]{4,}|κ|σ|φ", r["title"]) for r in priced), \
        "строка варианта — словами: точка и её разность с точкой книги"
    assert any(r["d_point"] < 0 for r in priced) and any(r["d_point"] > 0 for r in priced)
    anchor, req = d["capital"]["anchor"], d["capital"]["requirement"]
    assert anchor["req20_glide_next"] == req["mix"]["req20_glide"][0] and anchor["req20_glide_period"] == req["periods"][0]
    assert abs(anchor["n20_headroom_glide"] - (anchor["n20_post_dividend"] - anchor["req20_glide_next"])) <= 1e-6 and anchor["n20_headroom_glide"] < anchor["n20_headroom"]
    ym = req["years_mix"]
    assert len(ym["req20_glide"]) == len(d["capital"]["years"]) and all(g >= y for g, y in zip(ym["req20_glide"], d["capital"]["mix"]["req20"])) \
        and ym["req20_glide"] != d["capital"]["mix"]["req20"], "годовой ряд требования с глиссадой — не ниже требования года и не равен ему"


@pytest.mark.tact
def test_the_front_prints_what_the_headline_stands_on_and_computes_none_of_it():
    """Витрина печатает суждение о марже, уровни с окном фактов, путь модальной клетки, цену правил и запас до требования с глиссадой
    числами выпуска: карточки рисуются по своим узлам, разностей и средних витрина не считает, слов о мире суждения и правилах в коде нет."""
    levels, variants = function_body("levelsCard"), function_body("variantsCard")
    assert "if (!keys.length) return null;" in levels and "if (!rows.length) return null;" in variants, "карточка рисуется по своему узлу"
    for field in ("loans_share", "p_point", "p_analytical", "from_year", "to_year", "window", "anchor", "reference_value"):
        assert re.search(rf"\.{field}\b", levels), field
    assert "nimNode(d)" in levels and "worldName(d, s.world)" in levels and "worldName(d, s.reference_world)" in levels and "nimTol(s)" in levels
    assert "x.target" in APP_CODE[APP_CODE.index("nimTol = "):][:120] and "x.tolerance" in APP_CODE[APP_CODE.index("nimTol = "):][:120]
    # окно фактов: числа подузла; фразу о марже включает сравнение чисел выпуска (минимум строк против наибольшего квартала окна), а не код
    assert "L.window ?" in levels and "x.min" in levels and "x.max" in levels and "x.mean" in levels and 'low("nim") > W.nim.max' in levels \
        and 'low("loans_share") > Math.max(ls.window, ls.anchor)' in levels and not re.search(r"\.(?:nim|cor|cir|max|min|mean|window|anchor) (?:[-/]|\* (?!100))", levels), \
        "окно печатается как пришло (доля — в процентах): разностей и отношений с ним витрина не считает"
    limits = function_body("limitsCard")
    assert "r.delta" in limits and "printed_median" not in limits and not re.search(r"implied [-/]|[-/] (?:point|price)\b", limits), \
        "разность с точкой — поле строки выпуска; медианы полосы на шкале пределов нет"
    by = function_body("bySample")
    assert "refine_rows" in by and "named.includes(r.key)" in by and 'r.status === "solved"' in by
    control = function_body("controlCard")
    assert all(f"cm.{k}" in control for k in ("book_version", "valuation_date", "n_rows", "n_bad", "as_of")), "счётчики и дата чисел сводки — поля выпуска"
    notes = APP_CODE[APP_CODE.index("const rowNotes = "):][:200]       # подписи строки — помощник rowNotes (М§14.5: и причина «без цены», пометки)
    assert "nowcast).absent" in function_body("countdownCard") and ("r.note" in variants or ("rowNotes(r)" in variants and "r.note" in notes))         and ".sort(" not in variants, "порядок строк вариантов — выпуска"
    assert "worldName(d, w)" in function_body("cellName") and '"Свой вес"' not in APP_CODE and 'layerTitle(d, l)' in function_body("worldsCard"), "имена миров и слоёв — из выпуска"
    assert "r.d_point" in variants and "v.point" in variants and "ruText(r.title)" in variants and " - " not in variants, "разность с точкой книги — число выпуска"
    assert "levelsCard(d)" in function_body("screenOverview") and "levelsCard(d, true)" in function_body("screenBook") and "variantsCard(d)" in function_body("screenBook")
    for word in ("Рыночный как есть", "Модальная клетка", "Свой макро-взгляд", "Угасание избыточной доходности в"):
        assert word not in APP_CODE, f"слово выпуска в коде витрины: «{word}»"
    for field in ("req20_glide_next", "req20_glide_period", "n20_headroom_glide"):
        assert re.search(rf"\.{field}\b", APP_CODE), field
    assert "n20_post_dividend -" not in APP_CODE and "- a.req20_glide_next" not in APP_CODE and "- anchor.req20_glide_next" not in APP_CODE
    path = function_body("ratioPathCard")
    assert "ym.req20_glide" in path and "с глиссадой" in path and "требование года, без глиссады" in path
    growth = function_body("growthCard")
    assert 'worst("p_cut", 1)' in growth and 'worst("lam_min", -1)' in growth and "G.catch_up_rate > 0" in growth and "findIndex" not in growth, \
        "плитки роста — экстремумы рядов, а не первый год с числом"
    assert "dpsExpected(d, year)" in function_body("reportTeaser") and "dpsExpected(d, y)" in function_body("yearDpsCard") and "m.dps < m.dps_policy" in function_body("dpsExpected")
    assert 'basisName("ifrs")' not in function_body("yearDpsCard") and 'basisName("ifrs")' not in function_body("retroBenchmarksCard"), "базис прибыли квартала — из цели выпуска"
    assert "guidanceSince(g)" in function_body("guidanceCard") and "items.some((r) => isNum(r.required_rest))" in function_body("guidanceCard")
    assert not re.search(r"A-[A-Z]\d|k_T|g_T|ROE'_T", APP_CODE), "служебные обозначения и коды разделов книги в словах витрины не стоят"


# Служебный текст в печатаемых строках (П§0.2, AUDIT-2 № 73, № 96): те же запреты, что у общего теста текста экранов.
WORKING_TEXT = {
    "кортеж": re.compile(r"\(\d{4}, \d+, [A-Z]{3,}"),
    "e-нотация": re.compile(r"(?<![\w.,])\d(?:[.,]\d+)?e[-−+]?\d{1,3}(?!\w)"),
    "метка класса допущения": re.compile(r"\[(?:В|Ф|Р|НП)\]"),
    "хвост sha256": re.compile(r"sha256 [0-9a-f]{8,}"),
    "путь к листу или файл": re.compile(r"(?<![\w/.])[a-z][a-z\d_]*(?:/[a-z\d_.-]+)+|(?<!\w)[\w.-]+\.(?:json|ya?ml|pdf|md|xlsx?|csv|txt|py)(?!\w)"),
    "рабочая пометка": re.compile(r"ведущ|первичк|антибот|без токена", re.I),
    "имя метода или поля API": re.compile(r"(?<!\w)(?:Get|List|Post|Find)[A-Z][A-Za-z]+|(?<!\w)[a-z]+(?:[A-Z][a-z\d]+)+(?!\w)|[A-Z][a-z]+Service(?![^\W\d_])|(?<!\w)API(?!\w)"),
    "версия без имени": re.compile(r"850oa \d+[.,]\d"),
    "дата без года": re.compile(r"(?<![\d.,§\w-])(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])(?![\d.]|\.\d|\s?%)"),
    "процент без пробела или с точкой": re.compile(r"\d\.\d+\s?%|\d%"),
    "падеж после числа на 1": re.compile(r"в (?:\d*[02-9])?1 (?:клетках|кварталах)"),
    "число прогонов без разрядки": re.compile(r"\d{4,} прогон"),
    "падеж после дробного числа": re.compile(r"\d,\d+ (?:год|лет|день|дней)(?![а-яё])"),
}
PRINTED_KEYS = ("title", "name", "note", "message", "detail", "source", "src", "equation", "what", "explanation", "scope_note", "valid_until_note",
                "basis", "event", "reason", "text", "condition", "rule", "method", "definition", "summary")


def _working_text(payload) -> list[str]:
    found = []

    def walk(node, key=None, where="выпуск"):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, key, f"{where}[{i}]")
        elif isinstance(node, str) and key in PRINTED_KEYS:
            for rule, pattern in WORKING_TEXT.items():
                hit = pattern.search(node)
                if hit:
                    found.append(f"{where}: {rule} — «{hit.group(0)}» в «{node[:100]}»")

    walk(payload)
    return found


@pytest.mark.tact
@FORMS
def test_the_printed_strings_of_the_sample_are_words_for_the_owner(form):
    """В печатаемых строках обеих форм нет кортежей, e-нотации, меток класса допущения, хвостов sha256, путей к листам
    и файлам, рабочих пометок, дат без года, версий без имени, процентов без пробела, имён методов и полей API,
    пометок о токене; после дробного числа — «года»."""
    assert _working_text(form()) == []


@pytest.mark.tact
@pytest.mark.parametrize("field, text, rule", [
    ("note", "дата календаря эмитента в T-Invest (2026, 3, QUARTER; ≈10-е число — РСБУ)", "кортеж"),
    ("detail", "Nss(H) = цель (6.9e-18), T_real = T* (3.7e-16)", "e-нотация"),
    ("note", "дата — оценка [В]; новая политика входит новой версией книги", "метка класса допущения"),
    ("src", "презентация 2К26, с. 24, sha256 d17d36167137507e", "хвост sha256"),
    ("basis", "других изъятий нет; evidence/governance", "путь к листу или файл"),
    ("src", "факты capital.json (Н20.0 группы, Н1.1 банка)", "путь к листу или файл"),
    ("explanation", "порог — вопрос ведущему (М§4.4–§4.5)", "рабочая пометка"),
    ("source", "частота эпизодов; первичку собрать", "рабочая пометка"),
    ("note", "прецедент 28.10.2025; IR-страница закрыта антиботом", "рабочая пометка"),
    ("source", "850oa 1.6; DESIGN §3.4", "версия без имени"),
    ("source", "решение владельца 30.09; ось 0,049–0,062", "дата без года"),
    ("scope_note", "прогноз сектора обновлён к 29.04", "дата без года"),
    ("title", "Доля 50% прибыли", "процент без пробела или с точкой"),
    ("message", "P/B клетки вне коридора мира в 1 клетках", "падеж после числа на 1"),
    ("detail", "во всех клетках сетки и 2000 прогонов полосы", "число прогонов без разрядки"),
    ("src", "календарь дивидендов брокера (снимок 30.09.2026, без токена)", "рабочая пометка"),
    ("src", "брокер: GetPayouts, снимок 30.09.2026", "имя метода или поля API"),
    ("src", "брокер, CalendarService, снимок 30.09.2026", "имя метода или поля API"),
    ("src", "payoutNet 33,30 ₽, cutoffDate 11.07.2024", "имя метода или поля API"),
    ("src", "API брокера, снимок 30.09.2026", "имя метода или поля API"),
    ("source", "дюрация портфеля: 1,6 год … 2,4 года", "падеж после дробного числа"),
    ("note", "срок — около 2,5 лет", "падеж после дробного числа"),
])
def test_the_text_rules_catch_the_working_notes_of_the_second_audit(field, text, rule):
    """Правила ловят строки, которые второй аудит нашёл на экранах выпуска (сначала красное — потом правка источника)."""
    found = _working_text({"x": {field: text}})
    assert found and rule in found[0], found


@pytest.mark.tact
@pytest.mark.parametrize("text", [
    "решение владельца 30.09.2026; ось 0,049–0,062", "запись семейства book-1.6 от 21.09.2026", "ЧПМ 6,58–6,63 % против ≈6,2 %",
    "наибольшая относительная разность 1,8·10⁻¹²", "п. 6.4 Положения: срок — 3 года", "Н20.0 после выплаты не ниже 13,3 %",
    "в 21 клетке и 4 кварталах", "ЦБ, форма 0409135", "рост г/г +25 % при ключевой 14,62 % → 14,00 %", "оценка по прошлым годам: 06.12.2023, 10.12.2025",
    "решение годового общего собрания акционеров от 30.06.2026 (раскрытие эмитента); сверено с брокерским календарём дивидендов",
    "дюрация 1,6 года; сроки портфеля 2,5–6 лет; от 2,5 до 6 лет", "T-Invest, 18:49 МСК", "МСФО 6М26 с. 5, 68; презентация 2К26 с. 21", "β_E к индексу ММВБ; ROE'_T выше g_T",
])
def test_the_text_rules_leave_ordinary_words_alone(text):
    assert _working_text({"x": {"note": text}}) == []


@pytest.mark.tact
@FORMS
def test_the_sample_release_carries_no_service_text(form):
    """П§0.2: единицы — из кодов; в строках, которые витрина печатает как есть, нет имён полей и ключей, true/false, inf и кодов периодов."""
    d = form()

    def units(node, where="выпуск"):
        if isinstance(node, dict):
            if isinstance(node.get("unit"), str) and where.split(".")[0] not in ("meta",):
                assert node["unit"] in UNIT_CODES, f"{where}: единица «{node['unit']}» не из кодов П§0.2"
            for k, v in node.items():
                units(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                units(v, f"{where}[{i}]")

    units(d)
    for key, text in _printed_strings(d):
        hit = SERVICE_TEXT.search(re.sub(r"\S+\.(?:json|pdf|ya?ml|md)\b", " ", text))
        assert not hit, f"{key}: служебный текст «{hit.group(0)}» в «{text[:120]}»"


@pytest.mark.tact
def test_the_sample_release_matches_its_generator():
    done = subprocess.run([sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


@FORMS
def test_the_sample_release_passes_the_core_validate(form):
    """Обе формы выпуска годны по `model/payload.py::validate`; имя схемы передаётся явно — книга репозитория не читается."""
    try:
        from model.payload import validate
    except ImportError:
        pytest.skip("model/payload.py нет: сверка с validate — после интеграции")
    problems = validate(form(), schema=SCHEMA)
    assert problems == [], problems[:10]
