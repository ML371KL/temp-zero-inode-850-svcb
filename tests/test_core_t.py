"""Фикстура формы Т (`tests/fixtures/core_t`): схема принимает всю форму, ядро считает её целиком.

Полная книга фикстуры: один тикер, 12 книг ЧПД прямыми узлами фактов, подписи формы Т, делитель «размещённые»,
связь с объёмом, премии роста по секторам, постоянные прочие активы, множитель RWA режима, тест истории вида
`cap`, квартальный календарь дивидендов, рост, ограниченный капиталом, гейты и банковские строки второй формы.
Ветвей, принятых схемой и не исполняемых ядром, сейчас нет: проекция (`tests/support_core_t.py`) совпадает с
полной книгой; сам механизм отказа «не реализовано» проверяется на подставной ветви. Формулы «прежней ветви»
(каждая ветвь формы Т нейтральна) сверяются на `plain_dict`; ветви по одной — `tests/test_core_t_w1.py`
(волна 1), `tests/test_core_t_w2.py` (квартальные дивиденды) и `tests/test_core_t_w3.py` (рост по капиталу).
"""

from __future__ import annotations

import copy

import pytest

from model import book_schema as BS
from model.book import anchor_facts, book_from_dict, lower_first
from model.book_schema import (PENDING, PENDING_BANK_ROWS, PENDING_GUIDANCE_KEYS, BookError, pending, read_paths,
                               validate)
from model.checks import check_gates, check_invariants
from model.grid import market_cap, run_grid
from model.timeline import QUARTER_YEARS
from tests.support_core_t import (DROP, NEUTRAL, NEUTRAL_BANK_ROWS, NEUTRAL_GUIDANCE_KEYS, OFF, PENDING_BRANCHES,
                                  book_live, neutral_book, neutral_dict, neutral_run, plain_book, plain_dict,
                                  plain_run, put, t_dict, t_facts)

pytestmark = pytest.mark.tact

LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")
FUNDS = ("retail_current", "retail_term", "corp_funds")


# ------------------------------------------------------------------ схема: вся форма принята, ветви названы


def test_the_whole_t_form_is_in_the_schema():
    """Книга формы Т проходит схему целиком, и ядро её исполняет: ветвей «не реализовано» в ней нет."""
    data = t_dict()
    validate(data)
    assert data["meta"]["company"]["tickers"] == ["T"] and len(data["nii"]["books"]) == 12
    assert pending(data) == [] and not PENDING and not PENDING_BANK_ROWS and not PENDING_GUIDANCE_KEYS
    book = book_from_dict(data, facts=t_facts())
    assert book.get("capital.growth_constraint.enabled") is True and neutral_dict() == data


def test_pending_names_exactly_the_branches_the_projection_neutralises():
    """Перечень нереализованных ветвей схемы и перечень нейтральных значений проекции — одно и то же: ветвь,
    снятая из `PENDING`, обязана уйти и из `NEUTRAL` (иначе проекция молча держала бы её выключенной)."""
    named = {line.split(":")[0].split(" = ")[0] for line in pending(t_dict())}
    assert set(PENDING) <= named                                # полная книга включает каждую такую ветвь
    neutral = {("dividends.calendar.frequency" if k == "dividends.calendar" else k) for k in NEUTRAL}
    assert neutral == set(PENDING) and set(NEUTRAL) == set(PENDING_BRANCHES) <= set(OFF)
    assert set(NEUTRAL_GUIDANCE_KEYS) == set(PENDING_GUIDANCE_KEYS)
    assert set(NEUTRAL_BANK_ROWS) == set(PENDING_BANK_ROWS)
    rest = named - set(PENDING)
    assert all(r.startswith(("checks.guidance_items[", "valuation.reverse_dcf.bank_rows[")) for r in rest), sorted(rest)
    # ветви, исполняемые ядром, проекция держит включёнными — как в полной книге
    full, proj = t_dict(), neutral_dict()
    for dotted in set(OFF) - set(NEUTRAL):
        head, _, last = dotted.rpartition(".")
        node_full, node_proj = full, proj
        for part in head.split("."):
            node_full, node_proj = node_full[part], node_proj[part]
        assert node_proj[last] == node_full[last] != OFF[dotted], dotted
    assert proj["checks"]["guidance_items"] == full["checks"]["guidance_items"]
    assert proj["valuation"]["uncertainty"]["axes"] == full["valuation"]["uncertainty"]["axes"]


def test_a_pending_branch_refuses_until_the_core_runs_it(monkeypatch):
    """Механизм отказа «не реализовано» (подставная ветвь: в схеме таких сейчас нет): включённая ветвь из
    `PENDING` — отказ с её путём при загрузке книги; проверка одной формы (`pending_ok`) её принимает;
    нейтральное значение — не отказ."""
    path = "capital.growth_constraint.enabled"
    monkeypatch.setitem(BS.PENDING, path, (lambda v: v is True, "подставная ветвь"))
    data = t_dict()
    assert [ln for ln in pending(data) if ln.startswith(path)], pending(data)
    validate(data, pending_ok=True)
    with pytest.raises(BookError) as exc:
        book_from_dict(data, facts=t_facts())
    assert path in str(exc.value) and "не реализовано" in str(exc.value)
    assert pending(put(data, path, False)) == []
    book_from_dict(data, facts=t_facts())


def test_pending_guidance_keys_and_bank_rows_refuse(monkeypatch):
    """То же по элементам перечней: узел гайденса и банковская строка, названные нереализованными."""
    data = t_dict()
    assert pending(data) == []
    monkeypatch.setattr(BS, "PENDING_GUIDANCE_KEYS", ("roe_target",))
    monkeypatch.setattr(BS, "PENDING_BANK_ROWS", ("excess_return_years",))
    lines = pending(data)
    assert len(lines) == 2 and all("не реализовано" in ln for ln in lines)
    assert any(ln.startswith("checks.guidance_items[") for ln in lines)
    assert any(ln.startswith("valuation.reverse_dcf.bank_rows[") for ln in lines)


def test_neutral_values_of_new_keys_keep_the_previous_branch():
    """Нейтральное значение поведенческого ключа — то же, что его отсутствие: нули связей и премии,
    `outstanding`, нулевая поправка делителя, `exact`, `annual`, множитель RWA, равный единице, нулевые
    постоянные прочие активы, выключенный рост по капиталу — числа сетки те же до последнего знака."""
    data = plain_dict()
    for dotted, value in (("valuation.shares_basis", "outstanding"), ("valuation.share_count_adj", 0.0),
                          ("dividends.policy.history_test", "exact"), ("dividends.calendar.frequency", "annual"),
                          ("regimes.crisis.rwa_density_mult", {"2026": 1.0, "2027": 1.0, "LT": 1.0, "LT_from": 2030}),
                          ("regimes.norm.rwa_density_mult", 1.0), ("volumes.link_base", "funds"),
                          ("dividends.policy.cap", 0.30)):
        put(data, dotted, value)
    assert pending(data) == []
    book = book_from_dict(data, facts=t_facts())
    assert book.get("capital.growth_constraint.enabled") is False
    assert book.get("capital.growth_constraint.catch_up_rate") == 0.25          # поля выключателя остаются числами
    off = "capital.growth_constraint.catch_up_rate"
    assert off not in read_paths(book.data) and "capital.growth_constraint.enabled" in read_paths(book.data)
    base = plain_run()
    again = run_grid(book, t_facts(), book_live(book))
    assert again.point == base.point and again.divisor == base.divisor == base.shares_out
    for a, b in zip(again.cells, base.cells):
        assert a.v_ri == b.v_ri and a.quarters == b.quarters and a.dps == b.dps
    bare = plain_dict()                                                         # и без самих ключей — то же
    for dotted in ("valuation.share_count_adj", "volumes.link_base", "dividends.policy.cap", "volumes.other_assets_fixed",
                   "fees.volume_link", "other.insurance_volume_link", "opex.volume_link"):
        put(bare, dotted, DROP)
    bare["valuation"]["uncertainty"]["axes"] = [a for a in bare["valuation"]["uncertainty"]["axes"]
                                                if "valuation.share_count_adj" not in a["paths"]]
    del bare["capital"]["rwa"]["density"]["other_assets_fixed"]
    none = book_from_dict(bare, facts=t_facts())
    again = run_grid(none, t_facts(), book_live(none))
    assert again.point == base.point and [c.quarters for c in again.cells] == [c.quarters for c in base.cells]


def _fails(data, *fragments):
    with pytest.raises(BookError) as exc:
        validate(data, pending_ok=True)
    for fr in fragments:
        assert fr in str(exc.value), str(exc.value)


def test_mutual_constraints_of_the_t_form():
    """Взаимные ограничения ключей формы Т (М прил. A): отказ схемы до расчёта — и при проверке одной формы."""
    full = t_dict

    def changed(*pairs):
        data = full()
        for dotted, value in pairs:
            put(data, dotted, value)
        return data

    drop = pytest.importorskip("tests.support_core_t").DROP
    # делитель
    two = changed(("meta.company.tickers", ["T", "TP"]), ("meta.company.share_classes", {"T": "ordinary", "TP": "preferred"}),
                  ("meta.market_price", {"T": 330.0, "TP": 320.0}))
    _fails(two, "valuation.shares_basis", "одном тикере")
    for bad in (0.5, -0.5, 0.7):
        _fails(changed(("valuation.share_count_adj", bad)), "valuation.share_count_adj")
    # тест истории выплат
    _fails(changed(("dividends.policy.cap", drop)), "dividends.policy.cap", "history_test")
    for bad in (0.0, 1.2):
        _fails(changed(("dividends.policy.cap", bad)), "dividends.policy.cap")
    # календарь: ключи квартального режима обязательны, ключи годового — неактивны
    for key in ("decision_lag_quarters", "reg_deduction_lag_quarters", "payment_lag_quarters", "checkpoints_ahead"):
        _fails(changed((f"dividends.calendar.{key}", drop)), f"dividends.calendar.{key}", "нет ключа")
    for key, value in (("agm_quarter", 2), ("reg_deduction_quarter", 3), ("payment_quarter", 3), ("checkpoints", [3, 4])):
        _fails(changed((f"dividends.calendar.{key}", value)), f"dividends.calendar.{key}", "неактивного режима")
        validate(changed((f"dividends.calendar.{key}", None)), pending_ok=True)        # null — можно
    _fails(changed(("dividends.calendar.checkpoints_ahead", 1)), "checkpoints_ahead", "только 0")
    _fails(changed(("dividends.policy.steps", [{"payout": 0.25, "threshold": 0.1}])), "dividends.policy.steps")
    _fails(changed(("dividends.calendar.decision_lag_quarters", {"1": 2, "2": 2, "3": 1})), "карта лагов")
    _fails(changed(("dividends.calendar.decision_lag_quarters", {"1": 2, "2": 2, "3": 1, "4": 5})), "decision_lag_quarters.4")
    _fails(changed(("dividends.calendar.decision_lag_quarters", 0)), "decision_lag_quarters")
    validate(changed(("dividends.calendar.decision_lag_quarters", 2)), pending_ok=True)       # число — тоже лаг
    annual = plain_dict()
    for key, value in (("dividends.calendar.decision_lag_quarters", 2), ("dividends.calendar.payment_lag_quarters", 2),
                       ("dividends.calendar.checkpoints_ahead", 0), ("dividends.policy.base_window_quarters", 4)):
        _fails(put(copy.deepcopy(annual), key, value), key, "неактивного режима")
    _fails(put(copy.deepcopy(annual), "dividends.calendar.agm_quarter", drop), "dividends.calendar.agm_quarter", "нет ключа")
    # связь с объёмом
    for key in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link"):
        _fails(changed((key, 1.2)), key)
        _fails(changed((key, -0.1)), key)
    _fails(changed(("volumes.link_base", "assets")), "volumes.link_base")
    # премия роста: словарь — ровно по набору
    drift = full()["volumes"]["loan_share_drift"]
    _fails(changed(("volumes.loan_share_drift", {k: v for k, v in drift.items() if k != "mortgage"})), "ровно с ключами")
    _fails(changed(("volumes.loan_share_drift", {**drift, "auto": 0.1})), "ровно с ключами")
    _fails(changed(("volumes.funds_share_drift", {"retail": 0.1})), "volumes.funds_share_drift", "ровно с ключами")
    _fails(changed(("volumes.loan_share_drift.corporate", {"2026": 0.2, "LT_from": 2040})), "LT_from")
    # постоянные прочие активы
    _fails(changed(("capital.rwa.density.other_assets_fixed", drop)), "capital.rwa.density.other_assets_fixed")
    _fails(changed(("volumes.other_assets_fixed", -1.0)), "volumes.other_assets_fixed")
    _fails(changed(("capital.rwa.density.sme_loans", drop)), "capital.rwa.density.sme_loans", "нет ключа")
    # множитель RWA режима
    mult = "regimes.crisis.rwa_density_mult"
    _fails(changed((mult, {"2026": 1.0, "2027": 0.0, "LT": 1.0, "LT_from": 2030})), mult, "больше нуля")
    _fails(changed((mult, {"2026": 0.8, "2027": 0.9, "LT": 1.0, "LT_from": 2030})), mult, "года шока 2027")
    _fails(changed((mult, {"2026": 1.0, "2028": 0.9, "LT": 1.0, "LT_from": 2030})), mult, "года шока 2027")
    axes = full()["valuation"]["uncertainty"]["axes"]
    moved = [dict(a, paths=[f"{mult}.2026"]) if a["paths"] == [f"{mult}.2027"] else a for a in axes]
    _fails(changed(("valuation.uncertainty.axes", moved)), "только для года шока 2027")
    validate(changed(("regimes.norm.rwa_density_mult", {"2026": 1.0, "2028": 0.95, "LT": 1.0})), pending_ok=True)
    # рост по капиталу
    gc = "capital.growth_constraint"
    for key in ("order", "min_growth_scale", "lookahead_quarters", "glide_pp_per_quarter", "catch_up_rate", "tol"):
        _fails(changed((f"{gc}.{key}", drop)), f"{gc}.{key}", "нет ключа")
        free = [a for a in axes if f"{gc}.{key}" not in a["paths"]]       # ось требует существующего пути
        validate(changed((f"{gc}.enabled", False), (f"{gc}.{key}", drop), ("valuation.uncertainty.axes", free)),
                 pending_ok=True)                                           # выключен — поле не обязательно
    for key, bad in (("min_growth_scale", 1.5), ("lookahead_quarters", 13), ("lookahead_quarters", 2.5),
                     ("glide_pp_per_quarter", -0.001), ("catch_up_rate", 1.1), ("tol", 0.0), ("order", "equal")):
        _fails(changed((f"{gc}.{key}", bad)), f"{gc}.{key}")
        _fails(changed((f"{gc}.enabled", False), (f"{gc}.{key}", bad)), f"{gc}.{key}")          # границы — при любом enabled
    _fails(changed(("volumes.guidance_year", 2026)), "volumes.guidance_year", "раньше года")
    on_annual = plain_dict(on=("capital.growth_constraint.enabled",))
    _fails(on_annual, "capital.growth_constraint.enabled", "quarterly")
    # коридоры новых гейтов
    _fails(changed(("checks.cir_lt.from_year", 2040)), "checks.cir_lt.from_year", "вне лет сетки")
    _fails(changed(("checks.wholesale_share", [0.25, 0.05])), "checks.wholesale_share")
    _fails(changed(("checks.growth_cut.max_cut_share", 1.5)), "checks.growth_cut.max_cut_share")
    _fails(changed(("checks.step_dividend.max_lam_drop", -0.1)), "checks.step_dividend.max_lam_drop")
    _fails(changed(("valuation.reverse_dcf.bank_rows", ["implied_roe"])), "implied_roe")


# ------------------------------------------------------------------ факты формы Т: 12 книг прямыми узлами, один тикер


def test_anchor_facts_of_the_t_form():
    """Остатки книг — прямыми узлами `balance.books.<b>`; отдельной книги кредитов по справедливой стоимости
    нет; акции — одного класса; `anchor`-ключи — закрытыми формулами на этих узлах (М прил. A, B)."""
    book, facts = plain_book(), t_facts()
    af = anchor_facts(facts, book.get("nii.books"))
    bal = {b: facts.need("balance", f"books.{b}") for b in book.get("nii.books")}
    assert dict(af.balances) == bal and len(bal) == 12
    assert af.fv_book is None and af.fv_loans == 0.0
    assert af.n_out_preferred is None and af.n_out_ordinary == af.n_out == facts.need("shares", "outstanding_total")
    assert af.dividends_payable_year is None and af.at1 == 0.0 and af.coupon_annual == 0.0
    loans, funds = sum(bal[b] for b in LOANS), sum(bal[b] for b in FUNDS)
    liquid = bal["securities"] + bal["liquidity"]
    f = float(book.get("capital.n20.fvoci_recognition"))
    e0 = sum(facts.need("pnl_quarterly", f"quarters.{p}.ni_shareholders") for p in ("2026Q1", "2026Q2"))
    expect = {
        "credit.allowance_ratio": facts.need("balance", "allowance_ac") / loans,
        "nii.retail_current_share.c_ref": bal["retail_current"] / (bal["retail_current"] + bal["retail_term"]),
        "nii.retail_current_share.key_ref": facts.need("nii_books", "key_avg_anchor_q"),
        "volumes.wholesale_to_funds": bal["wholesale"] / funds,
        "volumes.securities_share_of_liquid": bal["securities"] / liquid,
        "volumes.other_assets_to_loans": facts.need("balance", "other_assets") / loans,
        "volumes.other_liabilities_to_loans": facts.need("balance", "other_liabilities") / loans,
        "oci.fvoci_share": (facts.need("balance", "securities.fvoci_debt") + facts.need("balance", "securities.fvoci_repo"))
        / bal["securities"],
        "oci.fvtpl_bond_share": facts.need("balance", "securities.fvtpl_bonds") / bal["securities"],
        "capital.n20.deductions_anchor": af.bv - facts.need("capital", "basel.cet1"),
        "capital.n11.deductions_anchor": af.bv - (1 - f) * af.fvoci_reserve - e0 - facts.need("capital", "bank_base_capital"),
    }
    assert set(book.anchors) == set(expect)
    for key, value in expect.items():
        assert book.anchors[key] == pytest.approx(value, rel=1e-12), key
    total = loans - af.allowance + liquid + af.other_assets
    assert total == pytest.approx(facts.need("balance", "total_assets"))
    assert total == pytest.approx(funds + bal["wholesale"] + af.other_liabilities + af.dividends_payable + af.bv + af.nci)


# ------------------------------------------------------------------ проекция: сетка на 12 книгах и одном тикере


def test_projection_runs_and_keeps_the_identities():
    run = neutral_run()
    assert len(run.cells) == 36 and run.ctx.prep.roles.loans == LOANS and run.ctx.prep.roles.corp_funds == ("corp_funds",)
    broken = {f.name: f.message for f in check_invariants(run) if f.fired}
    assert not broken, broken                                    # тест истории формы Т — `cap`: потолок выдержан
    plain = {f.name: f.message for f in check_invariants(plain_run()) if f.fired}
    # без ключа — формула «до копейки»: она читает поля строк истории первой формы
    assert set(plain) == {"dps_history"} and "не выполнена" in plain["dps_history"]
    for c in run.cells:
        assert set(c.books) == set(run.ctx.book.get("nii.books"))
        for q in range(1, run.ctx.timeline.Q + 1):
            assert c.quarters["assets"][q] == pytest.approx(c.quarters["liabilities_equity"][q], rel=1e-12)
            assert c.quarters["loans"][q] == pytest.approx(sum(c.books[b]["balance"][q] for b in LOANS), rel=1e-12)
            assert c.quarters["loans_fv"][q] == 0.0
    af = run.ctx.prep.af
    price = float(run.ctx.book.get("meta.market_price.T"))
    assert run.shares_out == af.n_out and run.divisor == af.n_iss            # делитель формы Т — размещённые акции
    assert market_cap(run) == pytest.approx(price * run.divisor / 1000)
    assert market_cap(plain_run()) == pytest.approx(price * af.n_out / 1000)         # один тикер: Cap — по его классу


def test_plain_volumes_follow_the_sector_of_the_book():
    """Год гайденса роста — до якоря: ни в одном квартале сетки ветвь гайденса не срабатывает, книга растёт
    с сектором мира (`sme_loans` — с корпоративным, хотя её сегмент риска — розница); без ключей формы Т
    прочие активы и комиссии — прежними формулами (М§4.3, §4.7)."""
    run, book, facts = plain_run(), plain_book(), t_facts()
    tl = run.ctx.timeline
    assert int(book.get("volumes.guidance_year")) < tl.year(1)
    oa_ratio = float(book.get("volumes.other_assets_to_loans"))
    gvw = float(book.get("fees.growth_vs_wages.LT"))
    fees_base = facts.need("pnl_quarterly", f"quarters.{tl.period(1 - 4)}.fees_net")
    for w in book.get("worlds.ids"):
        c, wp = run.cell(w, "norm", "schedule"), run.ctx.worlds[w]
        for b in LOANS:
            sector = book.get(f"nii.books.{b}.sector")
            for q in (1, 2, 5):
                step = c.books[b]["balance"][q] / c.books[b]["balance"][q - 1]
                assert step == pytest.approx((1 + wp.credit_growth[sector][tl.year(q)]) ** QUARTER_YEARS, rel=1e-12), (w, b, q)
        assert book.get("nii.books.sme_loans.cor_segment") == "retail"
        assert c.books["sme_loans"]["balance"][1] / c.books["sme_loans"]["balance"][0] == pytest.approx(
            c.books["corp_loans"]["balance"][1] / c.books["corp_loans"]["balance"][0], rel=1e-12)
        for q in range(1, tl.Q + 1):
            assert c.quarters["other_assets"][q] == pytest.approx(oa_ratio * c.quarters["loans"][q], rel=1e-12)
        assert c.quarters["fees"][1] == pytest.approx(fees_base * (1 + wp.wage[1] + gvw), rel=1e-12)


def test_projection_prints_the_words_of_the_t_form():
    """Сообщения проверок на проекции говорят словами книги формы Т: термин долгосрочного уровня, слово прибыли,
    подписи кредитных книг со строчной буквы (аббревиатура внутри подписи сохраняет регистр)."""
    run, book = neutral_run(), neutral_book()
    inv = {f.name: f for f in check_invariants(run)}
    gates = {f.name: f for f in check_gates(run)}
    lt, profit = book.label("terms.lt_level"), book.label("terms.profit_short")
    assert (lt, profit) == ("после фазы роста", "операционная прибыль")
    assert f"ЧПМ {lt} мира" in inv["transmission_solved"].message and lt in gates["nim_path_joint"].message
    assert profit in gates["ni_jump"].message                     # и в строке находки, и в строке «не найдено»
    names = [lower_first(book.book_name(b)) for b in LOANS]
    assert "кредиты МСБ" in names and "корпоративные кредиты и лизинг" in names
    floor = gates["lt_spread_floor"]
    assert floor.fired and any(n in floor.message for n in names)
    assert not any(book.book_name(b) in floor.message for b in LOANS)                 # с прописной — не печатается
    # гейт гайденса сравнивает узлы роста формы Т; узлы без числа эмитента и цель ROE в него не входят
    assert set(gates["guidance_gap"].detail["bands"]) == {"op_np_growth", "dps_growth"}


# ------------------------------------------------------------------ полная книга формы Т


def test_quarterly_calendar_decides_every_profit_quarter():
    """Квартальный календарь исполняется: решение — за каждый открытый квартал прибыли; записи реестра фактов
    несут объявленный DPS своих кварталов (подробно — `tests/test_core_t_w2.py`)."""
    from model.grid import live_from_book
    book = neutral_book()
    run = run_grid(book, t_facts(), live_from_book(book, t_facts()))
    c = run.cell("N", "norm", "schedule")
    assert {"2026Q1", "2026Q2", "2026Q3", "2026Q4"} <= set(c.dps_q)
    assert c.dps_q["2026Q2"] == pytest.approx(4.70) and all(d.period for d in c.decisions)
    assert not [f.name for f in check_invariants(run) if f.fired]


def test_the_full_t_book_runs():
    """Полная книга с ростом, ограниченным капиталом: инварианты целы, доля прироста — в [0; 1], решатель
    сошёлся во всех клетках (подробно — `tests/test_core_t_w3.py`)."""
    from model.grid import live_from_book
    book = book_from_dict(t_dict(), facts=t_facts())
    run = run_grid(book, t_facts(), live_from_book(book, t_facts()))
    assert not [f.name for f in check_invariants(run) if f.fired]
    for c in run.cells:
        assert all(0.0 <= x <= 1.0 for x in c.quarters["lam"][1:]) and "growth_solver" not in c.flags
