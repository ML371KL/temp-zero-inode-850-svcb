# -*- coding: utf-8 -*-
"""Книга Совкомбанка (книга 0.1, итоговая книга круга 12): шаблон разбирается, сборка воспроизводит машинную книгу, все
пути прил. A MODEL и договора ключей есть и не null там, где ядро их читает, схема ядра принимает форму книги;
вероятности, оси полосы и строки обратного расчёта согласованы со значениями книги; решения ведущего № 12 и форма книги
второй формы банка (квартальный календарь дивидендов, рост по капиталу, выкуп, премии траекториями, оси-связки, числа
«выводится на ядре» — запись вывода) — числами книги. Тест формы образца (книга Т 1.0) переписан на форму Совкомбанка
в медленном круге (Д16): литералы Т — числами книги Совкомбанка, решения ведущего Т № 1–8 — решениями № 12 и замком формы.
Быстрые — метка `tact` (такт сервера); тесты `docs` такт не гоняет. Суждения, которые проверяются прогоном ядра, —
`tests/test_book_core.py`."""
from __future__ import annotations

import json
import re
from string import Formatter

import pytest
import yaml

try:
    from tests import support_book as S
except ImportError:                      # прогон без pytest.ini (pythonpath = .) и без tests/__init__.py
    import support_book as S

pytestmark = pytest.mark.tact

MARKS = ("  #{{WORLDS}}", "#{{WORLDS_BANK}}", "#{{OVERLAY_SHA256}}")
VERSION = "0.1"
SCHEMA = "svcb-v1"
RESULTS = S.BOOK_DIR / "results.json"
# Оси, которые из полосы не выводятся никогда (MODEL §10): односторонние рисковые — по путям ключей
NEVER_OFF_BAND = ("tax.statutory", "tax.one_off.prob", "regimes.crisis.one_off_loss.amount")
CREDIT_BOOKS = ("auto", "mortgage", "cash_loans", "cards", "corp_loans")
BOOKS = CREDIT_BOOKS + ("securities", "liquidity", "retail_current", "retail_term", "corp_term", "corp_current", "wholesale",
                        "insurance_liab")
# Ключи годового календаря дивидендов: в квартальном режиме не читаются и равны null (MODEL §5.7)
CALENDAR_ANNUAL = tuple(f"dividends.calendar.{k}" for k in ("agm_quarter", "reg_deduction_quarter", "payment_quarter", "checkpoints"))
# Ключи второй формы банка (договор ключей этапа 1, раздел 1): книга несёт их явно. «*» — любой хвост пути. Потолок выплаты
# к истории (dividends.policy.cap) — ключ правила history_test: cap, у книги Совкомбанка правила нет (тест ниже).
FORM_PATHS = (
    "meta.schema", "meta.labels.*", "nii.books.<b>.name", "valuation.shares_basis", "valuation.share_count_adj",
    "dividends.policy.history_test", "dividends.policy.base_window_quarters",
    "dividends.calendar.frequency", "dividends.calendar.decision_lag_quarters.*",
    "dividends.calendar.reg_deduction_lag_quarters", "dividends.calendar.payment_lag_quarters",
    "dividends.calendar.checkpoints_ahead", "fees.volume_link", "other.insurance_volume_link", "opex.volume_link",
    "volumes.link_base", "volumes.loan_share_drift.{corporate,mortgage,retail_other}.*",
    "volumes.funds_share_drift.{retail,corporate}.*", "volumes.other_assets_fixed",
    "capital.rwa.density.other_assets_fixed", "regimes.crisis.rwa_density_mult.*",
    "capital.growth_constraint.{enabled,order,min_growth_scale,lookahead_quarters,glide_pp_per_quarter,catch_up_rate,tol}",
    "checks.guidance_items", "checks.growth_cut.max_cut_share", "checks.step_dividend.max_lam_drop",
    "checks.cir_lt.{target,tolerance,from_year}", "checks.wholesale_share", "checks.mix_ratio_tolerance",
    "checks.manual_overdue_days.capital_form",
    "valuation.sensitivities.buffer_pp",
    # ключи прохода ядра 1 (Совкомбанк, 21.10.2026): приложение A называет их объектами раздела («объект `book_relative`
    # раздела `credit`»), а не путями — пути листьев здесь
    "credit.book_relative.enabled", "credit.book_relative.by_book.*", "opex.volume_weights.*",
    "dividends.buyback.amount.*", "dividends.buyback.{price,skip_in_shock_year}", "dividends.buyback.closed_prices.*",
    # ключи прохода ядра 2 (К1–К7; интеграция круга 3, 21.10.2026) — так же пути листьев
    "credit.allowance_by_book.enabled", "volumes.wholesale_structural_to_funds", "volumes.liability_drivers.*",
    "fees.volume_base", "other.insurance_volume_base.*", "capital.rwa.guarantees.{enabled,weight,carve_from,driver}",
    "capital.rwa.guarantees.notional.*", "capital.rwa.guarantees.ccf.*", "dividends.min_dps.*",
    "valuation.terminal.stationary_rates",
    # ключи прохода ядра 3 (К2б, К-Т2, К8; интеграция круга 4, 21.10.2026): доли франшиз в базе расходов (К2) — пути листьев
    "opex.line_shares.*",
    # ключ прохода ядра 4 (Р5-6; интеграция круга 5, 22.10.2026): приложение A называет его ключом раздела («ключ
    # `line_root_form` раздела `volumes`») — путь листа здесь
    "volumes.line_root_form",
    # ключ прохода ядра 6 (Р8-6; интеграция круга 8, 22.10.2026): приложение A называет его объектом раздела («объект
    # `line_share_roots` раздела `opex`») — пути листьев (траектория κ строки) здесь
    "opex.line_share_roots.*",
    # ключ прохода ядра 7 (Р9-1; интеграция круга 9, 27.10.2026): корень ρ номинальной части книг К6 по строке-драйверу —
    # пути листьев (траектория ρ строки) здесь
    "volumes.liability_driver_roots.*",
    # ключи прохода ядра 8 (Р10-5, Р10-6, Р10-1 ключ (3); интеграция круга 10, 28.10.2026): форма связи λ франшизы и книг К6,
    # область гейта стоимости средств, книги средств клиентов в числах гейтов — пути листьев
    "volumes.line_link_form", "checks.funds_cost_to_key.scope", "checks.client_funds",
)
# Подписи книги и поля подстановки каждой (договор ключей, раздел 1.3); у прочих подписей полей нет
LABEL_FIELDS = {
    "capital.anchor_src": {"date"}, "capital.anchor_src_estimated": {"date"}, "dividends.ladder_condition": {"threshold"},
    "dividends.pay_event": {"year", "period", "label"}, "register.flag_detail": {"gaps"},
    "register.gap_item": {"year", "period", "label", "decision_quarter", "end"}, "register.alert": {"detail"},
    "register.recommended_item": {"year", "period", "label", "dps"}, "register.rejected_item": {"year", "period", "label", "reason"},
    "register.overdue_item": {"year", "period", "label", "date"}, "register.record_words": {"year", "period", "label"},
    "register.collector_alarm": {"year", "period", "label", "end", "detail"},
    "gates.nim_anchor": {"value", "reported"},
    "periods.1": {"year"}, "periods.2": {"year"}, "periods.3": {"year"}, "periods.4": {"year"},
}
LABEL_GROUPS = {
    "capital": {"n20", "n11", "n11_observed", "n1_0", "n1_2", "n20_short", "n11_short", "anchor_src", "anchor_src_estimated",
                "observed_source"},
    "capital_bridge": {"dividend_accrual", "profit", "oci_other", "rwa_growth", "deductions", "other"},
    "dividends": {"ladder_condition", "ladder_residual_title", "ladder_residual_condition", "pay_event"},
    "register": {"flag_title", "flag_detail", "gap_item", "alert", "recommended_item", "rejected_item", "note", "overdue_item",
                 "record_words", "collector_alarm"},
    "flags": {"ras_mismatch"}, "gates": {"nim_anchor"}, "nowcast": {"targets", "ops_note", "absent"},
    "nextreport": {"fact_note", "guidance_note"},
    "terms": {"lt_level", "profit_short", "cir", "roe_lt", "stake"}, "corridors": {"guidance_gap"}, "periods": {"1", "2", "3", "4"},
    "basis": {"profit", "roe", "roe_issuer", "divisor", "dividend_issued", "dividend_outstanding"}, "peers": {"subject_basis"},
    "control": {"lines", "books"}, "rule_price": {"unconstrained"},
}
LABEL_GROUPS["terms"] = {"lt_level", "profit_short", "cir", "roe_lt"}      # у книги Совкомбанка пакета-доли нет (stake — Т)
CONTROL_LINES = {"nii", "llp", "fvc", "fees", "opex", "misc", "noncore", "pbt", "ni_sh", "ci", "div", "bv", "rwa", "n20", "n11",
                 "buyback"}
# Ключи, значение которых зависит от пути баланса клетки или задано правилом на выведенных числах: с пометкой в шаблоне
DERIVED_ON_ENGINE = ("sigma0_split:", "phi_split:", "near_nim_shift:", "growth_vs_wages:", "real_growth: {",
                     "line_share_roots:", "liability_driver_roots:", "insurance_growth_vs_wages:", "deductions_anchor:",
                     "nim_lt_target_mgmt:")
# класс «shift над безразмерным ключом» (лист решения № 12, С-6; tests/test_core2_payload.py): наклон передачи ключевой и вес
# бумаг М13 — безразмерное число
SHIFT_UNITLESS = ("nii.transmission.target", "opex.volume_weights.securities")
WINDOW = ("2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")   # окно фактов: кварталы после покупки Росбанка
TERM_OVER_LIQUID = 0.0079                                     # срочные вклады окна дороже ликвидных активов (лист evidence/nii)
BUNDLE_LINKS = ("opex.volume_link", "fees.volume_link")       # главные числа оси-связки гибкости; прочие пути — спутники
PREMIUM_YEARS = ("2027", "2028", "2029", "2030", "2031")      # годы премии роста средств клиентов на оси-связке
PREMIUM_ENDS = {"2027": 0.05, "2028": 0.05, "2029": 0.04, "2030": 0.03, "2031": 0.02}
ANCHOR_YEAR_QUARTERS = ("2026Q3", "2026Q4")                   # прогнозные кварталы года якоря: ключи премии средств клиентов по факту


@pytest.fixture(scope="module")
def book() -> dict:
    return S.built_book()


@pytest.fixture(scope="module")
def template_text() -> str:
    return (S.BOOK_DIR / "assumptions_template.yaml").read_text(encoding="utf-8")


def switched_off(book: dict) -> set[str]:
    """Ключи, которые ядро не читает: под выключателями и ключи неактивного режима календаря дивидендов."""
    off = S.switched_off(book)
    if book["dividends"]["calendar"].get("frequency") == "quarterly":
        off.update(CALENDAR_ANNUAL)
    return off


def expand(token: str, book: dict) -> list[str]:
    """Шаблон пути → конкретные пути книги; незнакомая подстановка в угловых скобках — пусто (не путь книги)."""
    out = S._expand(token.replace(", ", ","), book)
    return [p for p in out if "<" not in p]


def applies(path: str, book: dict) -> bool:
    """Условные ключи книг ЧПД (пассивы, активы, кредиты, балансирующие); ключ доли кредитов по справедливой
    стоимости необязателен — у книг Т его нет."""
    if re.match(r"nii\.books\.[^.]+\.fv_share$", path):
        return S.has(book, path)
    return S._applies(path, book)


def form_paths(book: dict) -> list[str]:
    out = []
    for tok in FORM_PATHS:
        out += expand(tok, book)
    return out


# ------------------------------------------------------------------ шаблон и сборка
def test_the_template_parses_and_carries_one_of_each_build_mark(template_text):
    data = yaml.safe_load(template_text)
    assert data["meta"]["version"] == VERSION and data["meta"]["schema"] == SCHEMA
    lines = template_text.splitlines()
    assert sum(1 for ln in lines if ln == "  #{{WORLDS}}") == 1
    assert sum(1 for ln in lines if ln == "#{{WORLDS_BANK}}") == 1
    assert sum(1 for ln in lines if "#{{OVERLAY_SHA256}}" in ln) == 1
    assert set(data["worlds"]) == {"source", "build", "quarter_rule", "ids", "overlay"}   # миры вписывает сборка
    assert "worlds_bank" not in data
    assert not any("@@" in ln for ln in lines)


def test_the_build_reproduces_the_committed_machine_book():
    y, j, _ = S.build_module().render()
    assert (S.BOOK_DIR / "assumptions.yaml").read_text(encoding="utf-8") == y
    assert (S.BOOK_DIR / "assumptions.json").read_text(encoding="utf-8") == j


def test_the_build_is_deterministic_and_json_equals_yaml():
    m = S.build_module()
    y1, j1, b1 = m.render()
    y2, j2, b2 = m.render()
    assert (y1, j1) == (y2, j2)
    assert json.loads(j1) == yaml.safe_load(y1) == b1
    assert not any(ln.rstrip() in MARKS for ln in y1.splitlines())


def test_the_build_check_mode_exits_zero():
    done = S.run_script(S.BOOK_DIR / "build_assumptions.py", "--check")
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_core_schema_accepts_the_form_of_the_book(book):
    """Схема ядра принимает форму книги. Пока ядро собирается, ветвь, которую схема уже знает, а ядро ещё не исполняет,
    отказом не считается (`pending_ok`); незнакомый ключ, неверный тип и нарушение взаимных ограничений — отказ всегда.
    Когда ядро исполняет все ветви, проверка становится полной."""
    from model import book_schema

    try:
        book_schema.validate(book, pending_ok=True)
    except TypeError:                                    # ядро собрано: проверки одной формы больше нет
        book_schema.validate(book)


# ------------------------------------------------------------------ полнота ключей
def test_every_key_of_the_second_bank_form_is_in_the_book_and_not_null(book):
    """Ключи договора (квартальный календарь, делитель, связь с объёмом, премии траекториями, рост по капиталу, новые
    гейты, подписи) стоят в книге явно и не null: ось полосы и подмена пути требуют существующего ключа. Потолок выплаты
    к истории (`dividends.policy.cap`) — ключ правила `history_test: cap` (книга Т); у книги Совкомбанка правила нет
    (`none`), и ключа нет."""
    paths = form_paths(book)
    assert len(paths) > 45
    missing = [p for p in paths if "*" not in p and not S.has(book, p)]
    nulls = [p for p in paths if "*" not in p and S.has(book, p) and S.get(book, p) is None]
    assert missing == [] and nulls == []
    for p in (p for p in paths if "*" in p):
        assert S.get(book, p.split(".*")[0]), p
    policy = book["dividends"]["policy"]
    assert ("cap" in policy) == (policy["history_test"] == "cap") and policy["history_test"] == "none"


@pytest.mark.docs
def test_every_app_a_path_is_in_the_book_and_not_null(book):
    paths = [p for tok in re.findall(r"`([^`]+)`", S.app_a_text())
             for p in _app_a_token(tok, book)]
    paths = list(dict.fromkeys(paths))
    assert len(paths) > 300
    off = switched_off(book)
    missing = [p for p in paths if "*" not in p and not S.has(book, p)]
    nulls = [p for p in paths if "*" not in p and S.has(book, p) and S.get(book, p) is None and p not in off]
    assert missing == [] and nulls == []
    for p in (p for p in paths if "*" in p):                      # словарь по годам — не пуст
        assert S.get(book, p.split(".*")[0]) is not None


def _app_a_token(tok: str, book: dict) -> list[str]:
    tok = tok.strip()
    if " " in tok.replace(", ", ",") or "." not in tok or tok.split(".")[0] not in S.TOP or "/" in tok:
        return []
    return [p for p in expand(tok, book) if applies(p, book)]


@pytest.mark.docs
def test_every_leaf_of_the_book_is_named_by_app_a_or_by_the_form(book):
    """Каждый лист книги назван приложением A методики либо перечнем ключей второй формы банка."""
    paths = [p for tok in re.findall(r"`([^`]+)`", S.app_a_text()) for p in _app_a_token(tok, book)] + form_paths(book)
    exact = [p for p in paths if "*" not in p]
    star = [p.split("*")[0] for p in paths if "*" in p]
    unnamed = [path for path, _ in S.leaves(book)
               if not any(path.split("[")[0] == p or path.split("[")[0].startswith(p + ".") for p in exact)
               and not any(path.startswith(s) for s in star)]
    assert unnamed == []


def test_nulls_only_under_switched_off_keys(book):
    """null — только под выключенными выключателями и у ключей неактивного режима календаря. Под выключателем, который
    включает справочный вариант книги, ключи несут числа — их читает вариант (у книги Совкомбанка: cor_segments_two —
    сегменты CoR, fvtpl_market_rho1 — переоценка бумаг по справедливой стоимости); под прочими выключенными — null.
    Выкуп акций включён (dividends.buyback), рост ограничен капиталом, докапитализации нет."""
    off = switched_off(book)
    nulls = {p for p, v in S.leaves(book) if v is None}
    turned_on = {sw for sw in S.SWITCHES for v in book["valuation"]["reference_variants"] if v["overrides"].get(sw) is True}
    assert turned_on == {"credit.segment_relative.enabled", "other.fvtpl_bond_reval"}
    for sw, keys in S.SWITCHES.items():
        assert S.get(book, sw) is False, sw
        for k in keys:
            assert (S.get(book, k) is None) == (sw not in turned_on), (sw, k)
    read = {k for sw in turned_on for k in S.SWITCHES[sw]}
    assert nulls == off - read, sorted(nulls ^ (off - read))
    assert book["capital"]["recapitalization"]["enabled"] is False
    assert book["dividends"]["buyback"]["enabled"] is True
    assert book["capital"]["growth_constraint"]["enabled"] is True


# ------------------------------------------------------------------ согласованность значений
def test_probability_tables_sum_to_one(book):
    j = book["joint"]
    tables = [j["world_prob"], j["world_prob_market_implied"], j["regime_prob"], *j["reg_prob_given_regime"].values()]
    for axis in book["valuation"]["uncertainty"]["axes"]:
        if axis["kind"] == "dict":
            tables += [axis["low"], axis["high"]]
    for t in tables:
        assert abs(sum(t.values()) - 1) < 1e-4, t
    for t in tables[:3] + list(j["reg_prob_given_regime"].values()):
        assert abs(sum(t.values()) - 1) < 1e-12, t
    assert set(j["regime_prob"]) == set(book["regimes"]["ids"])
    assert set(j["world_prob"]) == set(book["worlds"]["ids"])
    assert all(set(t) == set(book["capital"]["reg_scenarios"]["ids"]) for t in j["reg_prob_given_regime"].values())


def test_governance_discount_is_the_sum_of_channels(book):
    """Дисконт за управление — Σ знак × значение каналов (М§8.2). У книги Совкомбанка каналов нет: дисконт 0, мост его
    не применяет; ненулевой дисконт без каналов схема отвергает (tests/test_core2_uncertainty.py)."""
    g = book["valuation"]["governance"]
    assert abs(g["discount"] - sum(c["sign"] * c["value"] for c in g["components"])) < 1e-12
    assert g["components"] == [] and g["discount"] == 0.0 and book["bridge"]["governance_applies"] is False


def test_uncertainty_axes_hold_the_book_value_inside_their_range(book):
    """Оси полосы книги Совкомбанка: 62 оси (2 словаря, 18 связок), вне полосы — ни одной; имена без повторов; каждый
    путь есть и не null; у связки концы — словари ровно по путям, значение книги — между концами (края включены: у
    связок пути, которые одна сторона оси не двигает, стоят на значении книги), и связка двигает книгу в обе стороны:
    на нижнем конце хоть один путь не равен книге и на верхнем — тоже; у оси value книга — внутри [низ; верх]; у оси
    shift ноль — внутри."""
    unc = book["valuation"]["uncertainty"]
    assert len(unc["axes"]) == 62 and unc["off_band_axes"] == []
    assert sum(1 for a in unc["axes"] if a["kind"] == "dict") == 2 and sum(1 for a in unc["axes"] if a["kind"] == "bundle") == 18
    names = [a["name"] for a in unc["axes"]]
    assert len(set(names)) == len(names)
    for a in unc["axes"] + unc["off_band_axes"]:
        assert a["dist"] == "triangular" and a["kind"] in ("value", "shift", "dict", "bundle")
        for p in a["paths"]:
            assert S.has(book, p) and S.get(book, p) is not None, (a["name"], p)
        if a["kind"] == "bundle":
            assert set(a["low"]) == set(a["high"]) == set(a["paths"]) and len(set(a["paths"])) == len(a["paths"]), a["name"]
            for p in a["paths"]:                    # концы связок κ и ρ — запись вывода шестью знаками: дрожание 1e-6
                lo, hi, v = a["low"][p], a["high"][p], S.get(book, p)
                assert min(lo, hi) - 1e-6 <= v <= max(lo, hi) + 1e-6, (a["name"], p)
            assert any(a["low"][p] != S.get(book, p) for p in a["paths"]), a["name"]
            assert any(a["high"][p] != S.get(book, p) for p in a["paths"]), a["name"]
        if a["kind"] == "value":
            for p in a["paths"]:
                assert a["low"] <= S.get(book, p) <= a["high"], (a["name"], p)
        elif a["kind"] == "shift":
            assert a["low"] <= 0 <= a["high"], a["name"]


def test_reverse_dcf_axes_search_covers_range(book):
    """Строки обратного расчёта книги Совкомбанка — семь: уровень маржи мира N (ключ ядра), CoR сквозь цикл, передача,
    запас, выплата, β_E, ERP; обе стороны оси идут за проверяемым значением; решение у края диапазона уточняется на
    полной полосе; поиск накрывает диапазон; диапазон строки — ось полосы тех же путей (связка строкой не бывает); смеси
    сценариев капитала строкой у книги нет; банковские строки — шесть."""
    rev = book["valuation"]["reverse_dcf"]
    assert len(rev["axes"]) == 7 and rev["axis_follow"] == "both"
    assert rev["edge_refine_rub"] == book["valuation"]["headline"]["print_step"]
    assert rev["refine_rows"] == ["nii.nim_lt_target_mgmt", "regimes.*.cor.LT"]
    for a in rev["axes"]:
        assert a["kind"] in ("value", "shift", "mix")
        for p in a["paths"]:
            assert S.has(book, p), (a["name"], p)
        assert a["search"][0] <= a["range"][0] <= a["range"][1] <= a["search"][1], a["name"]
    names = {a["name"] for a in rev["axes"]}
    assert any("Выплата" in n for n in names) and any("Запас" in n for n in names) and any("ЧПМ мира N" in n for n in names)
    assert not any(a["kind"] == "mix" for a in rev["axes"])
    band = {tuple(a["paths"]): a for a in book["valuation"]["uncertainty"]["axes"]}
    for a in rev["axes"]:
        own = band.get(tuple(a["paths"]))
        if own is not None and own["kind"] == "value":
            assert a["range"] == [own["low"], own["high"]], a["name"]
    assert rev["bank_rows"] == ["implied_roe_through_cycle", "implied_cost_of_equity", "market_cap_minus_bv",
                                "value_without_excess_growth", "book_value_per_share", "excess_return_years"]


def test_issuer_trajectories_end_on_lt_levels_by_the_last_year(book):
    last_year = int(book["meta"]["last_period"][:4])
    for path, v in S.leaves({k: book[k] for k in book if k not in ("worlds", "worlds_bank")}):
        if path.endswith(".LT_from"):
            assert int(v) <= last_year, path
        m = re.search(r"\.(\d{4})(Q\d|H\d)$", path)
        if m:
            assert int(m.group(1)) != last_year, path                 # ключ квартала/полугодия в году last_period запрещён


def test_year_keys_are_the_means_of_their_quarter_keys(book):
    """Ключ года при четырёх квартальных ключах — их среднее (MODEL §0.4): иначе ядро отказывает."""
    def walk(node, path=""):
        if isinstance(node, dict):
            quarters: dict[str, list[float]] = {}
            for k, v in node.items():
                m = re.fullmatch(r"(\d{4})Q[1-4]", str(k))
                if m and isinstance(v, (int, float)):
                    quarters.setdefault(m.group(1), []).append(float(v))
            for y, vals in quarters.items():
                if len(vals) == 4 and y in node:
                    assert abs(sum(vals) / 4 - node[y]) < 1e-9, (path, y)
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
    walk({k: book[k] for k in book if k not in ("worlds", "worlds_bank")})


def test_meta_company_and_prices(book):
    meta = book["meta"]
    c = meta["company"]
    assert c == {"name": "Совкомбанк", "tickers": ["SVCB"], "main_ticker": "SVCB", "share_classes": {"SVCB": "ordinary"},
                 "cbr_regnum": 963, "fiscal_year_end": "12-31"}
    assert set(meta["market_price"]) == set(c["tickers"]) and meta["market_price"]["SVCB"] > 0
    for k in ("date", "facts_date", "valuation_date", "curve_as_of"):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta[k])
    assert meta["valuation_date"] == meta["date"] >= meta["facts_date"]
    assert (meta["facts_date"], meta["anchor_period"], meta["first_period"], meta["last_period"]) == \
        ("2026-06-30", "2026Q2", "2026Q3", "2036Q4")
    assert book["valuation"]["uncertainty"]["seed"] == int(meta["date"].replace("-", ""))    # зерно — дата книги
    assert "МСФО группы ПАО «Совкомбанк»" in meta["basis"] and "купон бессрочных — через капитал" in meta["basis"]


# ------------------------------------------------------------------ решения ведущего числами книги
def test_lead_decisions_12_are_in_the_book(book):
    """Решения ведущего № 12 (итоговая книга круга 12, число устоялось) — числами книги: вероятности режимов — строгое
    прочтение без лет покупок 2016 и 2018 (Р12-6); доля сжатия φ на кредитных книгах — ближайшая граница области гейтов
    (Р12-4: центр 0,48 при оценке «по истории» 0,4215, ось — к верху 0,63, несимметрия названа в записи вывода);
    подтверждения раздела Д — запас менеджмента 0,84 п.п. (ось 0,73…0,91, оба норматива), признание фонда ССПСД 0,4875
    (тип Г, ось 0…0,975), доля сжатия опта 0,2477 и ликвидности 0,1419; порог гейта m_crisis_vs_cbr — пол 12,0 % + запас
    книги 0,84 п.п. (медленный круг, Д4)."""
    assert book["joint"]["regime_prob"] == {"soft": 0.3188, "norm": 0.3187, "downturn": 0.2125, "crisis": 0.15}
    nii = book["nii"]
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    phi = axes["nii.phi_split"]
    assert nii["phi_split"] == phi["low"] == 0.48 and phi["high"] == 0.63 and phi["kind"] == "value"
    record = json.loads((S.EVIDENCE / "path" / "out" / "derive_out.json").read_text(encoding="utf-8"))["splits"]
    assert (record["phi_split"], record["phi_type"], record["phi_bound"], record["phi_by_history"]) == (0.48, "Б", "low", 0.4215)
    assert book["capital"]["mgmt_buffer"] == {"n20_0": 0.0084, "n1_1": 0.0084}
    buf = axes["capital.mgmt_buffer.n20_0"]
    assert buf["paths"][:2] == ["capital.mgmt_buffer.n20_0", "capital.mgmt_buffer.n1_1"]
    assert all((buf["low"][p], buf["high"][p]) == (0.0073, 0.0091) for p in buf["paths"][:2])
    assert book["capital"]["n20"]["fvoci_recognition"] == 0.4875
    fv = next(a for a in book["valuation"]["uncertainty"]["axes"] if "capital.n20.fvoci_recognition" in a["paths"])
    assert fv["kind"] == "bundle" and (fv["low"]["capital.n20.fvoci_recognition"], fv["high"]["capital.n20.fvoci_recognition"]) == (0.0, 0.975)
    assert nii["books"]["wholesale"]["phi_share"] == 0.2477 and nii["books"]["liquidity"]["phi_share"] == 0.1419
    assert book["checks"]["m_crisis_vs_cbr"]["n20_min"] == pytest.approx(0.12 + book["capital"]["mgmt_buffer"]["n20_0"], abs=1e-12)


def test_the_form_numbers_of_the_book(book):
    """Форма книги Совкомбанка числами (замок: смена любого числа — правка книги вместе с этим тестом): режимы и их
    имена, база CoR, сценарии капитала по режимам, наблюдаемые фильтра режимов; миры и их имена (одно имя — один мир,
    режим или сценарий); квартальный календарь дивидендов и выплата по политике; ограничение роста капиталом
    (сначала рост); выкуп по цене мира; делитель, β_E, ERP и терминал; уровень маржи — ключом самого суждения в мире N,
    мир отсчёта спредов H, мир-опора κ — M."""
    assert book["regimes"]["ids"] == ["soft", "norm", "downturn", "crisis"] and book["regimes"]["cor_basis"] == "mgmt"
    assert [book["regimes"][r]["name"] for r in book["regimes"]["ids"]] == \
        ["Мягкая посадка", "Нормализация", "Розничный спад", "Кризис"]
    for r in ("soft", "norm", "downturn"):
        assert book["joint"]["reg_prob_given_regime"][r] == {"schedule": 0.35, "mid": 0.45, "strict": 0.20}
    assert book["joint"]["reg_prob_given_regime"]["crisis"] == {"schedule": 0.70, "mid": 0.25, "strict": 0.05}
    obs = book["joint"]["regime_update"]["observables"]
    assert obs == {"cor": {"sigma_pp": 0.0087, "rho_q": 0.15}, "nim": {"sigma_pp": 0.0051, "rho_q": 0.29}}
    assert book["worlds"]["ids"] == ["N", "H", "M"] and book["joint"]["world_prob"] == {"N": 0.35, "H": 0.45, "M": 0.2}
    names = [book["worlds"][wd]["name"] for wd in book["worlds"]["ids"]]
    regimes = [book["regimes"][r]["name"] for r in book["regimes"]["ids"]]
    scenarios = [book["capital"]["reg_scenarios"][s]["name"] for s in book["capital"]["reg_scenarios"]["ids"]]
    assert names == ["Нормализация ставок", "Высокие ставки надолго", "Рыночный как есть"]
    assert len(set(names + regimes + scenarios)) == len(names + regimes + scenarios)
    d = book["dividends"]
    assert d["calendar"]["frequency"] == "quarterly"
    assert d["calendar"]["decision_lag_quarters"] == {"1": 4, "2": 4, "3": 3, "4": 2}
    assert (d["calendar"]["reg_deduction_lag_quarters"], d["calendar"]["payment_lag_quarters"], d["calendar"]["checkpoints_ahead"]) == (3, 3, 0)
    assert d["policy"]["payout"] == {"2026": 0.22069, "2027": 0.22069, "LT": 0.22069, "LT_from": 2028}
    assert (d["policy"]["metric"], d["policy"]["threshold"], d["policy"]["steps"], d["policy"]["divisor"]) == ("n20_0", 0.0, [], "issued")
    assert d["excess"] == {"from_profit_year": 2028, "epsilon": 0.5, "ramp_years": 3}
    assert d["crisis"] == {"skip_in_shock_year": True, "catch_up": False}
    assert (d["buyback"]["enabled"], d["buyback"]["price"]) == (True, "world_forward")
    gc = book["capital"]["growth_constraint"]
    assert gc == {"enabled": True, "order": "growth_first", "min_growth_scale": 0, "lookahead_quarters": 8,
                  "glide_pp_per_quarter": 0.00265, "catch_up_rate": 0.0, "tol": 0.0001}
    assert book["capital"]["reg_scenarios"]["ids"] == ["schedule", "mid", "strict"]
    val = book["valuation"]
    assert (val["shares_basis"], val["share_count_adj"], val["beta_e"], val["erp"]) == ("outstanding", 0.0, 0.91, 0.0557)
    assert (val["terminal"]["real_growth"], val["terminal"]["fade"], val["headline"]["print_step"]) == (0.015, 0.5, 0.1)
    assert val["uncertainty"]["draws"] == 2000 and val["uncertainty"]["draw_step"] == 0.01
    tr = book["nii"]["transmission"]
    assert (tr["level_world"], tr["reference_world"], book["credit"]["kappa_reference_world"]) == ("N", "H", "M")
    assert book["joint"]["macro_neutral_world"] == "M" and "nim_stationary" not in book["checks"]
    assert len(book["nii"]["books"]) == 13 and list(book["nii"]["books"]) == list(BOOKS)











def test_frozen_numbers_are_the_record_of_the_derivation(book):
    """Замороженные числа шаблона — запись вывода на ядре (`evidence/path/out/derive_out.json`): каждый выведенный ключ
    книги равен ключу записи (ключи года — до 1e-9: средние кварталов в шаблоне — девятью знаками); запись начата со
    значений `derive_start.json` (тот же набор ключей), сошлась и называет модальную клетку книги; уровень маржи — ключ
    книги в мире уровня, стационар мира уровня равен ключу; доли σ0 и φ и ось передачи — записи; поля окна фактов гейта
    окна — записи; коридор доли опта — записи; низ оси доли φ — граница области гейта стоимости средств записи."""
    out = S.EVIDENCE / "path" / "out"
    record = json.loads((out / "derive_out.json").read_text(encoding="utf-8"))
    first = json.loads((out / "derive_start.json").read_text(encoding="utf-8"))
    start, before = first["keys"], first["before"]
    keys = record["keys"]
    assert set(keys) == set(start) == set(before)
    j = book["joint"]
    world = max(j["world_prob"], key=j["world_prob"].get)
    regime = max(j["regime_prob"], key=j["regime_prob"].get)
    scenario = max(j["reg_prob_given_regime"][regime], key=j["reg_prob_given_regime"][regime].get)
    assert record["modal_cell"]["label"] == f"{world}/{regime}/{scenario}" == "H/soft/mid"
    assert record["convergence"]["converged"] and record["frozen_check"]["nim_stationary_ok"]
    level = record["level"]
    assert level["key"] == book["nii"]["nim_lt_target_mgmt"] and level["world"] == book["nii"]["transmission"]["level_world"]
    assert level["stationary"] == pytest.approx(level["key"], abs=1e-9) and level["stationary_ok"]
    assert level["reference_world"] == book["nii"]["transmission"]["reference_world"]
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    assert (record["splits"]["phi_split"], record["splits"]["sigma0_split"]) == (book["nii"]["phi_split"], book["nii"]["sigma0_split"])
    assert [axes["nii.transmission.target"][e] for e in ("low", "high")] == \
        [round(x - book["nii"]["transmission"]["target"], 6) for x in record["transmission"]["axis"]]
    assert record["transmission"]["level_world_fixed"] is True
    assert all(row["solved"] for row in record["transmission"]["rows"].values())
    phi, gate = record["ends"]["phi_axis"], book["checks"]["funds_cost_to_key"]
    assert (phi["low"], phi["high"]) == (axes["nii.phi_split"]["low"], axes["nii.phi_split"]["high"]) and phi["gate_max"] == gate["max"]
    assert phi["at_low"] <= gate["max"]
    assert book["checks"]["wholesale_share"] == record["ends"]["wholesale_share"]["corridor"]
    window, wb = record["ends"]["window"], book["checks"]["window_backtest"]
    assert (wb["cor"], wb["cir"]) == ([window["cor"]["min"], window["cor"]["max"]], [window["cir"]["min"], window["cir"]["max"]])
    assert wb["means"] == {k: window[k]["mean"] for k in ("nim", "cor", "cir")}
    for dotted, value in keys.items():
        node = book
        for part in dotted.split("."):
            node = node[part]
        if isinstance(value, dict):             # ключи года — средние кварталов: в шаблоне записаны девятью знаками
            assert set(node) == set(value) and all(node[k] == pytest.approx(value[k], abs=1e-9) for k in value), dotted
        else:
            assert node == value, dotted
    assert {k for k in keys if keys[k] != before[k]} == {"opex.line_share_roots", "volumes.liability_driver_roots",
                                                          "other.insurance_growth_vs_wages"}


def test_numbers_derived_on_the_engine_are_marked_in_the_template(template_text):
    """Числа, выведенные на ядре (записи вывода — `derive_out.json`; у книги Совкомбанка ключ уровня маржи — тоже вывод:
    мост от 7,17 % опр. банка), несут в шаблоне пометку «ВЫВОДИТСЯ НА ЯДРЕ» (до вывода) или «ВЫВЕДЕНО НА ЯДРЕ» (после) в
    своём блоке — строке ключа и блоке комментариев под ней (книга Совкомбанка пишет правки под ключом): число без
    пометки — число, которое при следующей версии книги забудут вывести заново. Ключи, записанные строкой книги
    (спреды книг ЧПД, плотности RWA, вычеты якоря), — пометка в блоке их раздела."""
    lines = template_text.splitlines()

    def block(i: int) -> str:
        """Строка ключа, её дочерние строки (отступ глубже) и комментарии под ними — до следующего ключа того же уровня."""
        indent = len(lines[i]) - len(lines[i].lstrip())
        k = i + 1
        while k < len(lines) and (lines[k].lstrip().startswith("#") or not lines[k].strip()
                                  or len(lines[k]) - len(lines[k].lstrip()) > indent):
            k += 1
        return "\n".join(lines[i:k])

    for key in DERIVED_ON_ENGINE:
        at = [i for i, ln in enumerate(lines) if ln.strip().startswith(key)]
        assert at, key
        assert any(re.search(r"ВЫВОДИТСЯ НА ЯДРЕ|ВЫВЕДЕНО НА ЯДРЕ", block(i)) for i in at), key


def test_crisis_keys_lie_in_the_shock_year(book):
    """Год шока = год якоря + `shock_year_offset`; квартальный профиль CoR кризиса, период разового убытка, первый
    год `loan_growth_override` и минимум множителя RWA лежат в году шока (иначе ядро отказывает `BookError`)."""
    crisis = book["regimes"]["crisis"]
    off = crisis["shock_year_offset"]
    assert isinstance(off, int) and not isinstance(off, bool) and off >= 1
    shock = int(book["meta"]["anchor_period"][:4]) + off
    assert crisis["one_off_loss"]["period"][:4] == str(shock)
    quarters = sorted(k for k in crisis["cor"] if "Q" in str(k))
    assert quarters == [f"{shock}Q{k}" for k in (1, 2, 3, 4)]
    assert min(int(y) for y in crisis["loan_growth_override"]) == shock
    mult = crisis["rwa_density_mult"]
    assert mult[str(shock)] == min(v for k, v in mult.items() if k != "LT_from") and mult[str(shock - 1)] == 1.0
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0].startswith("regimes.crisis.rwa_density_mult"))
    assert ax["paths"] == [f"regimes.crisis.rwa_density_mult.{shock}"] and ax["kind"] == "value" and ax["high"] == 1.0
    assert "rwa_density_mult" not in book["regimes"]["norm"]


def test_books_flags_and_spread_floors_are_consistent(book):
    """Тринадцать книг Совкомбанка: подпись у каждой; балансирующие книги сдвига σ0 и сжатия φ не несут; у обеих книг
    средств физлиц флаги одинаковы; книги со сжатием φ — среди книг со сдвигом (у автокредитов сдвиг без сжатия);
    книга страховых обязательств К6 — без сдвига и сжатия; полы спреда, плотности RWA и строки контроля — по пяти
    кредитным книгам; доли σ0 и φ лежат внутри своих осей."""
    nii = book["nii"]
    books = nii["books"]
    assert all(isinstance(v["name"], str) and v["name"].strip() for v in books.values())
    assert books["wholesale"]["name"] == "Оптовое фондирование" and not any("fv_share" in v for v in books.values())
    loans = [b for b, v in books.items() if "sector" in v]
    assert loans == list(CREDIT_BOOKS)
    assert [b for b, v in books.items() if v.get("balancing")] == ["securities", "liquidity", "wholesale"]
    assert not any(v["lt_shift"] or v["phi"] for v in books.values() if v.get("balancing"))
    assert books["retail_current"]["lt_shift"] is books["retail_term"]["lt_shift"]
    assert books["retail_current"]["phi"] is books["retail_term"]["phi"]
    assert {b for b, v in books.items() if v["phi"]} <= {b for b, v in books.items() if v["lt_shift"]}
    assert books["auto"]["lt_shift"] and not books["auto"]["phi"]
    assert not (books["insurance_liab"]["lt_shift"] or books["insurance_liab"]["phi"])
    for key in ("sigma0_split", "phi_split"):
        ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"] == [f"nii.{key}"])
        assert ax["kind"] == "value" and 0.0 <= ax["low"] <= nii[key] <= ax["high"] <= 1.0
    floors = book["checks"]["lt_spread_floor"]
    assert set(floors) == set(loans) and all(isinstance(v, float) and 0.0 <= v < 0.20 for v in floors.values())
    dens = book["capital"]["rwa"]["density"]
    assert set(dens) == set(loans) | {"securities", "liquidity", "other_assets", "other_assets_fixed", "cash_assets"}
    assert set(book["meta"]["labels"]["control"]["books"]) == set(loans)


# Единица оси для печати (MODEL §10, PAYLOAD §0.2): код и правило по ПУТЯМ оси, не по словам имени
AXIS_UNITS = {"pct", "pp", "number", "years", "bn"}
YEARS_PATHS = ("oci.fvoci_duration", "oci.fvoci_maturity")
PP_MARKS = ("_pp", "nim_shift", "mgmt_buffer", "spread")
BN_PATHS = ("regimes.crisis.one_off_loss.amount", "capital.n20.t2", "noncore.result_real", "other.misc_net_real",
            "dividends.buyback.amount")                                   # выкуп дочкой — в млрд ₽ за квартал (книга Совкомбанка)


def test_scalar_axes_carry_the_unit_of_their_paths(book):
    """У каждой скалярной оси — поле `unit` из кодов выпуска; у оси-словаря его нет. Сдвиг доли (вид `shift` на долях,
    пути с `_pp`, сдвиг ЧПМ режима, запас, спред) — `pp`; срок — `years`; суммы в млрд ₽ — `bn` по путям денежных ключей;
    коэффициент больше единицы процентом не печатается. Класс «shift над безразмерным ключом» (лист решения № 12, С-6):
    сдвиг наклона передачи ключевой и веса бумаг М13 — безразмерное число (`number`). Связка печатает единицу первого
    пути: связка с безразмерным первым путём (β книги К6, веса М13, доли баз) — `number`, даже если спутники — спреды."""
    for a in book["valuation"]["uncertainty"]["axes"]:
        if a["kind"] == "dict":
            assert "unit" not in a, a["name"]
            continue
        unit, paths = a.get("unit"), a["paths"]
        assert unit in AXIS_UNITS, (a["name"], unit)
        money = any(p.startswith(BN_PATHS) for p in paths)
        assert (unit == "bn") == money, a["name"]
        heads = paths[:1] if a["kind"] == "bundle" else paths
        unitless = a["kind"] == "shift" and paths[0] in SHIFT_UNITLESS       # по первому пути, как в выпуске (С-6)
        if not money and not unitless and (a["kind"] == "shift" or any(m in p for p in heads for m in PP_MARKS)):
            assert unit == "pp", a["name"]
        if unitless:
            assert unit == "number", a["name"]
        assert (unit == "years") == any(p in YEARS_PATHS for p in paths), a["name"]
        if unit in ("pct", "pp"):                     # у связки — концы первого пути (по нему печать)
            ends = [a[e][paths[0]] if a["kind"] == "bundle" else a[e] for e in ("low", "high")]
            assert max(abs(v) for v in ends) <= 1.0, a["name"]


def test_the_regime_floor_is_a_share_of_the_base_probability(book):
    ru = book["joint"]["regime_update"]
    share, prior = ru["floor_share"], book["joint"]["regime_prob"]
    assert isinstance(share, float) and 0.0 < share < 1.0 and ru["window_obs"] == 4 and ru["max_shift_pp"] == 0.05
    floors = {r: share * p for r, p in prior.items()}
    assert abs(sum(floors.values()) - share) < 1e-12
    assert floors["soft"] == pytest.approx(0.33 * 0.3188) and floors["crisis"] == pytest.approx(0.0495)
    assert all(floors[r] < prior[r] for r in prior)


def off_band_report(book: dict, rows: list, point: float) -> dict:
    """Три условия оси вне полосы (MODEL §10) по строкам цены ошибки суждения: (1) ожидаемая доля размах² / Σ размах²
    меньше 1 %; (2) |сдвиг положения оси| < print_step / 10; (3) |Σ сдвигов по осям вне полосы| ≤ print_step / 10.
    Сдвиг положения — (цена_high + цена_low − 2 × точка) / 6. Возвращает {имя оси или «Σ»: [что нарушено]}."""
    limit = book["valuation"]["headline"]["print_step"] / 10
    by_name = {r["name"]: r for r in rows}
    total = sum(r["swing"] ** 2 for r in rows if r.get("swing") is not None)
    bad, shifts = {}, 0.0
    for a in book["valuation"]["uncertainty"]["off_band_axes"]:
        r = by_name.get(a["name"])
        if r is None:
            bad[a["name"]] = ["нет строки цены ошибки суждения — нужен прогон ядра на этой книге"]
            continue
        shift = (r["price_high"] + r["price_low"] - 2 * point) / 6
        shifts += shift
        why = []
        if not r["swing"] ** 2 / total < 0.01:
            why.append("доля размаха не меньше 1 %")
        if not abs(shift) < limit:
            why.append(f"сдвиг положения {shift:+.2f} ₽")
        if a["kind"] == "dict" or any(p.startswith(NEVER_OFF_BAND) for p in a["paths"]):
            why.append("ось-словарь или односторонняя рисковая ось")
        if why:
            bad[a["name"]] = why
    if abs(shifts) > limit:
        bad["Σ"] = [f"сумма сдвигов положения {shifts:+.2f} ₽ больше {limit} ₽"]
    return bad


def test_off_band_axes_meet_the_three_conditions(book):
    """Ось вне полосы допустима только при трёх условиях MODEL §10 (у книги 1.0 список пуст — все оси в полосе).
    Проверка — по `results.json`; с непустым списком результаты обязаны быть этой книги."""
    off = book["valuation"]["uncertainty"]["off_band_axes"]
    names = {a["name"] for a in book["valuation"]["uncertainty"]["axes"]}
    assert not [a["name"] for a in off if a["name"] in names]
    if not off:
        return
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert res["book_version"] == book["meta"]["version"], "оси вне полосы проверяются по результатам этой книги"
    assert off_band_report(book, res["judgements"], res["headline"]["point"]) == {}


def test_the_off_band_rule_catches_an_asymmetric_and_a_wide_axis(book):
    """Правило на заглушке: узкая симметричная ось проходит; асимметричная, широкая, налоговая и сумма сдвигов — нет.
    Цены заглушки — в шагах печати книги (у книги Т шаг 5 ₽ при цене 400, у книги Совкомбанка 0,1 ₽): отступы от точки
    пересчитаны множителем шаг / 5, чтобы правило судило ту же форму, а не литерал шага Т."""
    step = book["valuation"]["headline"]["print_step"]
    unit = step / 5.0
    point = 400.0 * unit

    def row(name, lo, hi):                          # lo, hi — цены заглушки в рублях книги Т (точка 400, шаг 5)
        lo, hi = point + (lo - 400.0) * unit, point + (hi - 400.0) * unit
        return {"name": name, "price_low": lo, "price_high": hi, "swing": abs(hi - lo)}

    def variant(axes):
        b = {"valuation": {"headline": {"print_step": step}, "uncertainty": {"off_band_axes": axes}}}
        return off_band_report(b, rows, point)

    rows = [row("главная", 300.0, 520.0), row("узкая", 399.0, 401.0), row("асимметричная", 400.0, 400.0 - 5.0),
            row("широкая", 370.0, 430.0), row("налог", 400.0, 399.5), row("ещё узкая", 399.6, 400.2),
            row("вниз 1", 400.0, 398.2), row("вниз 2", 400.0, 398.4)]
    ax = {n: {"name": n, "kind": "value", "paths": ["x.y"]}
          for n in ("узкая", "асимметричная", "широкая", "ещё узкая", "вниз 1", "вниз 2")}
    ax["налог"] = {"name": "налог", "kind": "shift", "paths": ["tax.statutory"]}
    assert variant([ax["узкая"], ax["ещё узкая"]]) == {}
    assert list(variant([ax["асимметричная"]])) == ["асимметричная", "Σ"]
    assert list(variant([ax["широкая"]])) == ["широкая"]
    assert list(variant([ax["налог"]])) == ["налог"]
    assert list(variant([ax["вниз 1"], ax["вниз 2"]])) == ["Σ"]
    assert "нет строки" in variant([{"name": "новая", "kind": "value", "paths": ["x.y"]}])["новая"][0]


def test_the_near_nim_shift_covers_the_near_path_only(book):
    """Ближний сдвиг ЧПМ: квартальные ключи — от первого прогнозного квартала до конца 2029 года, ключ года — среднее
    своих квартальных ключей, с 2030 года — 0; путь сходит к нулю монотонно; у книги Совкомбанка оси на нём нет (путь
    выведен на ядре: ближний путь маржи — запись вывода); сдвиги ЧПМ режимов в году якоря — 0."""
    near = book["regimes"]["near_nim_shift"]
    first = book["meta"]["first_period"]
    q_keys = sorted(k for k in near if "Q" in k)
    y0 = int(first[:4])
    expected = [f"{y0}Q{k}" for k in range(int(first[5]), 5)] + [f"{y}Q{k}" for y in range(y0 + 1, 2030) for k in (1, 2, 3, 4)]
    assert q_keys == expected
    for y in sorted({k[:4] for k in q_keys}):
        qs = [near[k] for k in q_keys if k.startswith(y)]
        assert near[y] == pytest.approx(sum(qs) / len(qs), abs=1e-9), y
    assert near["LT"] == 0.0 and near["LT_from"] == 2030 and S.year_value({k: v for k, v in near.items() if "Q" not in k}, 2031) == 0.0
    vals = [near[k] for k in q_keys]
    assert all(abs(b) <= abs(a) for a, b in zip(vals, vals[1:]))
    assert not any(p.startswith("regimes.near_nim_shift") for a in book["valuation"]["uncertainty"]["axes"] for p in a["paths"])
    assert all(book["regimes"][r]["nim_shift"]["2026"] == 0.0 for r in book["regimes"]["ids"])


def test_value_axes_on_year_keys_do_not_meet_quarter_keys(book):
    """Ось `value` на ключе года траектории с квартальными ключами этого года — отказ ядра (MODEL §0.4); ось `shift`
    на таком году обязана двигать ключ года и все его квартальные ключи вместе (иначе ключ года перестаёт быть средним)."""
    unc = book["valuation"]["uncertainty"]
    for a in unc["axes"] + unc["off_band_axes"]:
        for p in a["paths"]:
            head, _, key = p.rpartition(".")
            if not (key.isdigit() and S.has(book, head) and isinstance(S.get(book, head), dict)):
                continue
            quarters = [f"{head}.{k}" for k in S.get(book, head) if str(k).startswith(key + "Q")]
            if a["kind"] == "value":
                assert not quarters, (a["name"], p)
            elif quarters:
                assert set(quarters) <= set(a["paths"]), (a["name"], p)


def test_the_capital_instruments_trajectory_is_quarterly_and_ends_flat(book):
    """Инструменты капитала банка (книга Совкомбанка: добавочный и дополнительный капитал без прибыли — бессрочные вне
    МСФО и субординированные займы, признание в последние пять лет линейно): траектория в рублях по концам кварталов от
    квартала якоря до года перед последним; последний год — ключом года, равным LT; путь не растёт (новых выпусков нет)
    и кончается плоско; ось — сдвиг всего пути кварталов, в млрд ₽."""
    t2 = book["capital"]["n20"]["t2"]
    first, last = book["meta"]["first_period"], int(book["meta"]["last_period"][:4])
    q_keys = [k for k in t2 if "Q" in k]
    y0 = int(first[:4])
    expected = [book["meta"]["anchor_period"]] + [f"{y0}Q{k}" for k in range(int(first[5]), 5)] \
        + [f"{y}Q{k}" for y in range(y0 + 1, last) for k in (1, 2, 3, 4)]
    assert q_keys == expected and t2[str(last)] == t2["LT"] and "LT_from" not in t2
    vals = [t2[k] for k in q_keys] + [t2["LT"]]
    assert all(b <= a for a, b in zip(vals, vals[1:])) and vals[-1] == vals[-2]
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0].startswith("capital.n20.t2"))
    assert (ax["kind"], ax["low"], ax["high"], ax["unit"]) == ("shift", -15.0, 15.0, "bn")
    assert ax["paths"] == [f"capital.n20.t2.{k}" for k in q_keys[1:] + [str(last), "LT"]]   # весь прогнозный путь


def test_premiums_are_trajectories_by_sector_and_end_by_the_drift_year(book):
    """Премии роста (MODEL §4.3): у кредитов — ровно три группы сектора, у средств — два сегмента; после
    `share_drift_until` премия равна нулю; ключи кредитов — 2026 и 2027 годы; у средств клиентов кварталы года якоря —
    0, годы 2027–2029 — центр; оси — связки по годам не позже `share_drift_until` (LT и ключи года якоря не трогают);
    механизм гайденса роста выключен."""
    v = book["volumes"]
    assert list(v["loan_share_drift"]) == ["corporate", "mortgage", "retail_other"]
    assert list(v["funds_share_drift"]) == ["retail", "corporate"]
    for traj in list(v["loan_share_drift"].values()) + list(v["funds_share_drift"].values()):
        assert traj["LT"] == 0.0 and traj["LT_from"] == v["share_drift_until"] + 1
    assert all(set(traj) == {"2026", "2027", "LT", "LT_from"} for traj in v["loan_share_drift"].values())
    for traj in v["funds_share_drift"].values():
        assert traj["2026Q3"] == traj["2026Q4"] == 0.0 and set(traj) == {"2026Q3", "2026Q4", "2027", "2028", "2029", "LT", "LT_from"}
    axes = {a["paths"][0]: a for a in book["valuation"]["uncertainty"]["axes"]}
    loans = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0].startswith("volumes.loan_share_drift"))
    funds = axes["volumes.funds_share_drift.retail.2027"]
    for ax in (loans, funds):
        assert ax["kind"] == "bundle" and ax["unit"] == "pp"
        assert all(p.rsplit(".", 1)[1].isdigit() and int(p.rsplit(".", 1)[1]) <= v["share_drift_until"] for p in ax["paths"])
        assert not any(p.endswith((".LT", ".2026", ".2026Q3", ".2026Q4")) for p in ax["paths"])
    assert v["guidance_year"] < int(book["meta"]["first_period"][:4])           # механизм гайденса роста выключен
    assert v["guidance_growth"] == {"corporate": 0.0, "retail": 0.0}


def test_misc_quarter_shares_and_the_volume_links(book):
    """Доли кварталов «прочего» — ровно по четверти; связи с объёмом (книга Совкомбанка): комиссии и расходы — 1 (за
    базой строки), страхование — 0,37 (Р7-3); переопределений роста комиссий нет; переоценки бумаг ССПУ нет."""
    shares = book["other"]["misc_quarter_shares"]
    assert list(shares) == ["1", "2", "3", "4"] and abs(sum(shares.values()) - 1.0) < 1e-9 and set(shares.values()) == {0.25}
    assert (book["fees"]["volume_link"], book["opex"]["volume_link"], book["other"]["insurance_volume_link"]) == (1.0, 1.0, 0.37)
    assert book["fees"]["growth_override"] == {} and book["other"]["fvtpl_bond_reval"] is False


def test_opex_roots_and_their_axis(book):
    """Корни реального роста расходов (книга Совкомбанка, тип В на двух прочтениях — Р12-1, Р12-1а): ключ года якоря,
    кварталы 2027 года, годы 2028–2029 — переход к уровню окна, с 2030 года 0; ось полосы сдвигает переход 2027–2029
    (кварталы 2027 года и годы 2028–2029 вместе); цель C/I сквозь цикл — в коридоре гейта долгосрочного C/I слоя
    «рыночные ставки как есть» с года `volumes.lt_from`."""
    og = book["opex"]["real_growth"]
    assert list(og) == ["2026", "2027Q1", "2027Q2", "2027Q3", "2027Q4", "2028", "2029", "LT", "LT_from"]
    assert og["LT"] == 0.0 and og["LT_from"] == 2030
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"]
              if a["paths"][0] == "opex.real_growth.2027Q1" and a["kind"] == "shift")
    assert ax["paths"] == [f"opex.real_growth.{k}" for k in ("2027Q1", "2027Q2", "2027Q3", "2027Q4", "2028", "2029")]
    assert ax["low"] < 0 < ax["high"] and ax["unit"] == "pp"
    cir = book["checks"]["cir_lt"]
    assert cir == {"target": 0.4834, "tolerance": 0.009, "from_year": 2033, "scope": "market_layer"}
    assert cir["from_year"] == book["volumes"]["lt_from"]


def test_the_labels_are_complete_and_carry_only_known_fields(book):
    """Подписи книги (MODEL §0.6): все группы и ключи договора, непустые строки; поля подстановки — только названные у
    ключа; набор строк сводки контрольной модели — шестнадцать (с выкупом). Слова книги Совкомбанка: «сквозь цикл»,
    делитель — акции в обращении, нормативы — Н1.0 и Н1.2."""
    labels = book["meta"]["labels"]
    assert set(labels) == set(LABEL_GROUPS)
    for group, keys in LABEL_GROUPS.items():
        assert set(labels[group]) == keys, group
    assert set(labels["control"]["lines"]) == CONTROL_LINES
    assert set(labels["nowcast"]["targets"]) == {"ni_q", "nim_q", "cor_q"}
    count = 0
    for path, value in S.leaves(labels):
        if path.endswith(".basis"):
            continue
        count += 1
        assert isinstance(value, str) and value.strip(), path
        fields = {name for _, name, spec, conv in Formatter().parse(value) if name is not None}
        assert fields <= LABEL_FIELDS.get(path, set()), (path, fields)
    assert count >= 44
    assert labels["terms"]["lt_level"] == "сквозь цикл" and labels["basis"]["divisor"] == "акции в обращении"
    assert labels["capital"]["n20_short"] == "Н1.0" and labels["capital"]["n11_short"] == "Н1.2"


def test_guidance_items_and_gate_corridors_have_valid_forms(book):
    """Узлы гайденса: без повторов, у узла гейта есть слова; коридоры гейтов — [мин < макс]; гейты второй формы."""
    ch = book["checks"]
    items = ch["guidance_items"]
    assert [i["key"] for i in items] == ["roe", "nim", "cor_max", "cir"]
    for i in items:
        assert set(i) == {"key", "path", "title", "words", "basis", "gate"} and i["path"] == f"items.{i['key']}" and i["basis"] == "mgmt"
        assert i["title"].strip() and (not i["gate"] or i["words"].strip())
    assert [i["gate"] for i in items] == [True, True, True, True]
    for key in ("roe_range", "cor_range", "nim_range", "cir_range", "terminal_share", "real_rate", "transmission_pairs", "wholesale_share"):
        lo, hi = ch[key]
        assert lo < hi, key
    assert 0 < ch["growth_cut"]["max_cut_share"] <= 1 and 0 < ch["step_dividend"]["max_lam_drop"] <= 1
    assert ch["manual_overdue_days"] == {"ifrs_fact": 7, "worlds_after_cbr": 21, "dividend_register": 5, "capital_form": 7}
    record = json.loads((S.EVIDENCE / "path" / "out" / "derive_out.json").read_text(encoding="utf-8"))
    anchor = record["ends"]["wholesale_share"]["anchor"]
    assert ch["wholesale_share"][0] < anchor < ch["wholesale_share"][1]                # якорь внутри коридора
    assert ch["nim_range"][0] <= book["nii"]["nim_lt_target_mgmt"] <= ch["nim_range"][1]
    assert ch["cir_range"][0] < ch["cir_lt"]["target"] < ch["cir_range"][1]
    for k in ("nim_path_joint", "ni_jump"):
        assert isinstance(ch[k]["quarters"], int) and 1 <= ch[k]["quarters"] <= 42
    lo, hi = book["valuation"]["sensitivities"]["rank_window"]
    assert 0.0 < lo < 0.5 < hi < 1.0 and book["valuation"]["sensitivities"]["buffer_pp"] == 0.01


def test_near_spread_keys_follow_the_anchor_rates(book):
    """Ближние ключи спредов (MODEL §4.4): ключ года якоря = ставка якоря − опора мира отсчёта в первом прогнозном
    квартале (у пассивов β × опора); следующий год — середина до калибровки года якоря + 2. Ставки якоря — факты
    `data/facts/nii_books.json`; пока в каталоге фактов нет книг Т, сверку несёт лист `evidence/nii`."""
    facts_path = S.FACTS_DIR / "nii_books.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))["books"] if facts_path.exists() else {}
    if not set(book["nii"]["books"]) <= set(facts):
        pytest.skip("в data/facts ещё нет ставок якоря двенадцати книг Т — сверку несёт лист evidence/nii")
    first = book["meta"]["first_period"]
    y0 = int(first[:4])
    half = f"{y0}H{1 if int(first[5]) <= 2 else 2}"
    ref_world = book["worlds"][book["nii"]["transmission"]["reference_world"]]
    field = {"key": "key_rate"}
    checked = []
    for b, spec in book["nii"]["books"].items():
        sp = spec["spread"]
        if not isinstance(sp, dict) or str(y0) not in sp:
            continue
        ref = ref_world[field.get(spec["ref"], spec["ref"])][half]
        beta = spec["beta"] if spec["side"] == "liability" else 1.0
        s0 = facts[b]["rate_anchor"]["v"] - beta * ref
        assert sp[str(y0)] == pytest.approx(s0, abs=6e-6), b
        mid = (sp[str(y0)] + S.year_value(sp, y0 + 2)) / 2
        assert sp[str(y0 + 1)] == pytest.approx(mid, abs=6e-6), b
        checked.append(b)
    assert set(CREDIT_BOOKS) <= set(checked)
