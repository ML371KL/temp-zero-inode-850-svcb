# -*- coding: utf-8 -*-
"""Проверки классов ошибок в модели `ops/tools/class_checks.py` (PLAYBOOK §2а): на книге дерева зелёные классы
остаются зелёными и модель не меняется; подложенное нарушение каждого класса ловится. Мутации — подменой функций ядра
в процессе теста (`monkeypatch`, снимается после теста) или подменой книги и файла связей; ядро и книга на диске не
меняются. Ради времени тесты считают книгу дерева с малым набором осей (их подмножество книги) и малым набором
возмущений; полный прогон — сама команда (десятки секунд)."""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "ops" / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


C = _load("class_checks")
R = _load("rederive")

from model import cell as cellmod  # noqa: E402
from model import grid as gridmod  # noqa: E402
from model import uncertainty as U  # noqa: E402
from model.book import load_book, load_facts  # noqa: E402
from model.grid import live_from_book, make_context  # noqa: E402

# Малый набор осей книги Совкомбанка: значение, сдвиг, словарь, связка, значение на ключе режима — все виды осей книги; оси
# со спутниками (дисконт за управление → каналы, файл связей `axes.companions`) у книги нет — тестовая ось на ключе книги
# (итог 0, один канал 0) добавляется к малому набору.
SMALL_AXES = ("ERP", "Отклонение выплаты от центра", "Веса миров", "Запас менеджмента над требованием",
              "Кризис: сдвиг ЧПМ 2027")
GOVERNANCE_AXIS = {"name": "Дисконт за управление (тестовая ось)", "kind": "value", "paths": ["valuation.governance.discount"],
                   "low": -0.05, "high": 0.05, "dist": "triangular", "unit": "pct"}
GOVERNANCE_CHANNEL = {"id": "test", "name": "тестовый канал", "value": 0.0, "sign": 1.0, "basis": "тест"}
CLASSES = {1: "identities", 2: "cross_cell", 3: "horizon", 4: "axes", 5: "transitional", 6: "centres"}


@pytest.fixture(scope="module")
def facts():
    return load_facts()


@pytest.fixture(scope="module")
def book(facts):
    return load_book(facts=facts)


@pytest.fixture(scope="module")
def small(book):
    """Книга дерева с подмножеством осей полосы и тестовой осью дисконта за управление: сетка та же (оси её не трогают,
    канал с нулём — дисконт тот же), проход по осям короче."""
    axes = [ax for ax in book.get("valuation.uncertainty.axes") if str(ax["name"]).startswith(SMALL_AXES)]
    assert len(axes) == len(SMALL_AXES), [ax["name"] for ax in axes]
    assert float(book.get("valuation.governance.discount")) == 0.0 and not book.get("valuation.governance.components")
    return book.with_overrides({"valuation.uncertainty.axes": axes + [dict(GOVERNANCE_AXIS)],
                                "valuation.governance.components": [dict(GOVERNANCE_CHANNEL)]})


def config(**sections) -> dict:
    """Файл связей дерева с заменой разделов."""
    cfg = copy.deepcopy(C.load_config(C.CONFIG))
    cfg.pop("book_slopes", None)              # наклоны книг ЧПД (Р11-1) судит свой тест (test_core_p9); здесь — только названные разделы
    cfg.pop("centre_template", None)          # ключи с центром шаблона судит свой тест (класс 6, centre_keys); здесь — только названные разделы
    cfg["centres"] = []                       # правила центров книги (устав §3, класс 6) судят свои тесты: оси малого набора их
    #                                           не покрывают; здесь — только названные разделы
    for name, value in sections.items():
        cfg[name] = value
    return cfg


def quiet_cross_cell(**over) -> dict:
    """Раздел класса 2 без возмущений: каждый тест включает своё."""
    cfg = copy.deepcopy(C.load_config(C.CONFIG)["cross_cell"])
    cfg.update(isolation=False, cells=[], cell_inputs=[], book_inputs=[])
    cfg.update(over)
    return cfg


def one(out: dict, cls: int) -> dict:
    return next(c for c in out["checks"] if c["cls"] == cls)


def run(book, facts, cfg, *classes):
    return C.run_checks(book, facts, cfg, only=classes, say=lambda _: None)


# ------------------------------------------------------------ файл связей дерева


def test_the_config_of_the_tree_names_known_links_and_series_and_the_centre_rules_of_the_charter(book, facts):
    """Файл связей дерева — устав Совкомбанка §8 и решения ведущего: связи и ряды переходных слагаемых — из словаря
    инструмента (каждый селектор читается на подготовке прогона книги), правила центров (устав §3, класс 6) есть,
    законные связи без проверки инструментом названы с решением и ценой (или без цены)."""
    cfg = C.load_config(C.CONFIG)
    assert "устав Совкомбанка §8" in cfg["status"] and "решения ведущего" in cfg["status"] and "заготовка" not in cfg["status"]
    assert set(cfg["cross_cell"]["legal_links"]) <= set(C.LINKS)
    assert {s["input"] for s in cfg["cross_cell"]["cell_inputs"]} <= set(C.CELL_INPUTS)
    ctx = make_context(book, facts, live_from_book(book, facts))
    for rule in cfg["transitional"]:
        C.series_items(ctx, str(rule["series"]))
    assert cfg["centres"] and all(rule.get("type") for rule in cfg["centres"])
    for name, link in cfg["cross_cell"]["named_links"].items():
        assert link["what"] and link["decision"] and "price_point" in link, name


# ------------------------------------------------------------ книга дерева: зелёное и модель не тронута


def test_on_the_book_of_the_tree_the_green_classes_stay_green_and_the_model_is_untouched(small, facts):
    """Классы 1, 2, 4, 5 на книге дерева зелёные (малый набор возмущений и осей), класс 6 — «правил нет» (не зелёно и
    не флаг); подмены инструмента сняты — сетка книги после проверок та же бит в бит."""
    cross = quiet_cross_cell(isolation=True, cells=["N/soft/schedule", "H/norm/mid", "M/crisis/strict"],
                             cell_inputs=C.load_config(C.CONFIG)["cross_cell"]["cell_inputs"],
                             book_inputs=[{"path": "regimes.{regime}.cor", "shift": 0.002},
                                          {"path": "worlds.{world}.real_key", "shift": 0.01}])
    out = run(small, facts, config(cross_cell=cross), 1, 2, 4, 5, 6)
    status = {c["cls"]: c["status"] for c in out["checks"]}
    assert status == {1: C.OK, 2: C.OK, 4: C.OK, 5: C.OK, 6: C.NO_RULES}, [c["findings"][:3] for c in out["checks"]]
    assert out["flags"] == [] and out["model_untouched"] is True
    assert out["point"] == out["point_after"]
    assert cellmod._Cell.__init__ is cellmod._Cell.__dict__["__init__"]
    cross_numbers = one(out, 2)["numbers"]
    assert cross_numbers["isolation"]["differ"] == [] and cross_numbers["cell_runs"] == 3 * 4
    assert one(out, 2)["tally"] == (f"клеток одна — {cross_numbers['isolation']['cells']}, подмен входа клетки — 12, "
                                    f"возмущений книги — {len(cross_numbers['book_inputs'])}")
    empty = [r["name"] for r in one(out, 5)["numbers"]["centre"] if not r["values"]]
    rules = len(C.load_config(C.CONFIG)["transitional"])
    assert one(out, 5)["tally"] == f"правил {rules}, из них без рядов (не проверялось) — {len(empty)}"
    assert [n for n in one(out, 5)["notes"] if "не проверялось" in n] == [
        n for n in one(out, 5)["notes"] if any(f"«{name}»" in n for name in empty)]
    links = {link for row in cross_numbers["book_inputs"] for link in row["links"]}
    assert {"regime", "world", "kappa_reference_world"} <= links, "мир-опора κ-добавки несёт возмущение во все миры"


# ------------------------------------------------------------ класс 1


def test_class_one_catches_regulatory_capital_that_does_not_follow_the_ifrs_capital(book, facts, monkeypatch):
    """Мутация: капитал Н20.0 на 0,5 млрд ₽ выше формулы из капитала МСФО (суждение действует только в одной форме
    капитала). Инварианты ядра её не видят, тождество класса 1 — видит."""
    real = cellmod.ratios

    def ratios(c, **kw):
        out = real(c, **kw)
        return out._replace(k20=out.k20 + 0.5)

    monkeypatch.setattr(cellmod, "ratios", ratios)
    out = run(book, facts, config(identities={"rel_tol": 1e-9, "at_axis_ends": False}), 1)
    chk = one(out, 1)
    assert chk["status"] == C.FIRED
    assert all("инвариант ядра" not in line for line in chk["findings"])
    assert any("капитал норматива из капитала МСФО" in line and "K20" in line for line in chk["findings"])


def test_class_one_capital_identity_carries_the_buyback():
    """Выкуп по цене мира (ключ `dividends.buyback`, М§5.6) — распределение акционерам вне совокупного дохода: тождество
    капитала года класса 1 вычитает его, как ядро (`bv_identity`); без вычета каждая клетка с выкупом — ложная находка
    (проверка прохода ядра 1, core-verify)."""
    from tests import support_core_p1 as P1
    grid = P1._bb_grid()
    rows = [(at, lhs, rhs) for name, at, lhs, rhs in C.identity_rows(grid) if name == "capital_year"]
    assert rows and all(C.residual(lhs, rhs) <= 1e-9 for _, lhs, rhs in rows), rows[:3]
    tl = grid.ctx.timeline
    moved = [c for c in grid.cells if any(c.quarters["bb"][q] for q in range(1, tl.Q + 1))]
    assert len(moved) == len(grid.cells)     # выкуп есть в каждой клетке: проверка не холостая


def test_class_one_catches_dividends_payable_out_of_step_with_the_decisions(book, facts, monkeypatch):
    """Мутация: выплата квартала в ряду клетки на 1 млрд ₽ больше той, что ушла из обязательства (дивиденд действует
    на одной стороне баланса)."""
    real = cellmod._Cell.step

    def step(self, *a, **kw):
        row = real(self, *a, **kw)
        if "pay" in row:
            row["pay"] += 1.0
        return row

    monkeypatch.setattr(cellmod._Cell, "step", step)
    out = run(book, facts, config(identities={"rel_tol": 1e-9, "at_axis_ends": False}), 1)
    chk = one(out, 1)
    assert chk["status"] == C.FIRED
    assert any("дивиденды к выплате" in line for line in chk["findings"])


def test_class_one_checks_the_ends_of_the_axes_too(small, facts, monkeypatch):
    """Мутация действует только на конце оси ERP (капитал норматива уходит от формулы при ERP выше книги): тождества
    центра зелёные, тождества конца — нет."""
    real = cellmod.ratios
    erp = float(small.get("valuation.erp"))

    def ratios(c, **kw):
        out = real(c, **kw)
        return out._replace(k20=out.k20 + 0.5) if ERP_NOW["value"] > erp else out

    ERP_NOW = {"value": erp}
    real_make = gridmod.make_context

    def make_context_(book, *a, **kw):
        ERP_NOW["value"] = float(book.get("valuation.erp"))
        return real_make(book, *a, **kw)

    monkeypatch.setattr(cellmod, "ratios", ratios)
    monkeypatch.setattr(gridmod, "make_context", make_context_)
    out = run(small, facts, config(identities={"rel_tol": 1e-9, "at_axis_ends": True}), 1)
    lines = one(out, 1)["findings"]
    assert lines and all(line.startswith("ось «ERP") and "конец high" in line for line in lines)


# ------------------------------------------------------------ класс 2


def test_class_two_catches_a_run_cache_that_carries_one_regime_into_others(book, facts, monkeypatch):
    """Мутация: потенциальные множители роста — общие у клеток мира, а не мира и режима (рубли первой клетки мира
    уходят во все). Ловят обе проверки: клетка одна не равна себе в сетке, а возмущение поправки роста одного режима
    меняет клетки других режимов без канала."""
    real = cellmod._Cell.__init__

    def init(self, ctx, world, regime, scenario, *, preliminary=False, shared=None):
        real(self, ctx, world, regime, scenario, preliminary=preliminary, shared=shared)
        if shared is not None:
            self.factors = shared.setdefault(("leak", world), {})

    monkeypatch.setattr(cellmod._Cell, "__init__", init)
    cross = quiet_cross_cell(isolation=True, book_inputs=[{"path": "regimes.soft.loan_growth_adj", "shift": 0.01}])
    chk = one(run(book, facts, config(cross_cell=cross), 2), 2)
    assert chk["status"] == C.FIRED
    assert any("посчитанная одна, не равна себе" in line for line in chk["findings"])
    assert any("regimes.soft.loan_growth_adj" in line and "без канала" in line for line in chk["findings"])


def test_class_two_catches_a_cell_input_that_reaches_the_other_cells_of_its_world(book, facts, monkeypatch):
    """Мутация: клетки мира берут путь CoR первой клетки мира (её объект — в общих величинах прогона). Возмущение CoR
    одной клетки (подменой в процессе) меняет все клетки её мира — находка класса 2."""
    real_init, real_step = cellmod._Cell.__init__, cellmod._Cell.step

    def init(self, ctx, world, regime, scenario, *, preliminary=False, shared=None):
        real_init(self, ctx, world, regime, scenario, preliminary=preliminary, shared=shared)
        self._leader = self if shared is None else shared.setdefault(("leader", world), self)

    def step(self, *a, **kw):
        self.cor = self._leader.cor
        return real_step(self, *a, **kw)

    monkeypatch.setattr(cellmod._Cell, "__init__", init)
    monkeypatch.setattr(cellmod._Cell, "step", step)
    cross = quiet_cross_cell(cells=["N/soft/schedule"], cell_inputs=[{"input": "cor", "size": 0.002}])
    chk = one(run(book, facts, config(cross_cell=cross), 2), 2)
    assert chk["status"] == C.FIRED
    assert any(line.startswith("вход «cor» клетки N/soft/schedule") and "меняет другие клетки" in line
               for line in chk["findings"])


def test_class_two_reads_the_legal_links_from_the_config(book, facts):
    """Связь, которой нет среди законных в файле, — находка: без мира-опоры κ-добавки возмущение реальной ставки мира M
    меняет клетки миров N и H по незаконной связи; с ней — зелёно."""
    path = [{"path": "worlds.M.real_key", "shift": 0.01}]
    lawful = quiet_cross_cell(book_inputs=path)
    assert one(run(book, facts, config(cross_cell=lawful), 2), 2)["status"] == C.OK
    links = {k: v for k, v in lawful["legal_links"].items() if k != "kappa_reference_world"}
    chk = one(run(book, facts, config(cross_cell=dict(lawful, legal_links=links)), 2), 2)
    assert chk["status"] == C.FIRED
    assert any("которой нет среди законных: kappa_reference_world" in line for line in chk["findings"])


def test_class_two_without_a_single_perturbation_is_not_checked_rather_than_green(book, facts, capsys):
    """Находка В-3 проверки фазы 0: раздел cross_cell без сверки клетки одной, без подмен входов и без возмущений книги —
    статус «не проверялось» (no_rules: не зелёно и не флаг), а не «зелёно»; в строке класса — счёт клеток, подмен и
    возмущений (и в печати инструмента). Одна подмена — уже проверка: зелёно, со счётом."""
    out = run(book, facts, config(cross_cell=quiet_cross_cell()), 2)
    chk = one(out, 2)
    assert chk["status"] == C.NO_RULES and chk["status_words"] == C.NOT_CHECKED and out["flags"] == []
    assert chk["tally"] == "клеток одна — не сверялись, подмен входа клетки — 0, возмущений книги — 0"
    assert any("проверка пустая" in note for note in chk["notes"])
    C.report(out, quiet=True)
    assert ("класс 2 — " + C.CLASS_TITLES[2] + ": не проверялось (клеток одна — не сверялись, подмен входа клетки — 0, "
            "возмущений книги — 0)") in capsys.readouterr().out
    # только список клеток без входов — тоже пусто; одна подмена — уже проверка
    assert one(run(book, facts, config(cross_cell=quiet_cross_cell(cells=["N/soft/schedule"])), 2), 2)["status"] == C.NO_RULES
    chk = one(run(book, facts, config(cross_cell=quiet_cross_cell(
        cells=["N/soft/schedule"], cell_inputs=[{"input": "cor", "size": 0.002}])), 2), 2)
    assert chk["status"] == C.OK and chk["status_words"] == C.STATUS_WORDS[C.OK]
    assert chk["tally"] == "клеток одна — не сверялись, подмен входа клетки — 1, возмущений книги — 0"


def test_the_cell_input_substitution_is_undone_and_reaches_only_its_cell(book, facts):
    """Подмена входа клетки живёт только внутри менеджера: после него класс клетки — исходный, а сетка под подменой
    меняет ровно одну клетку."""
    bench = C.make_bench(book, facts, config())
    before = cellmod._Cell.__init__
    with C.perturbed_cell(("H", "downturn", "mid"), "deduction", 0.002):
        changed = bench.changed(bench.run())
    assert cellmod._Cell.__init__ is before
    assert changed == {("H", "downturn", "mid")}
    with pytest.raises(C.Refused):
        with C.perturbed_cell(("H", "downturn", "mid"), "нет такого", 0.1):
            pass


# ------------------------------------------------------------ класс 3


def test_class_three_catches_a_terminal_that_continues_the_explicit_years_in_another_form(book, facts, monkeypatch):
    """Мутация: терминал берёт прибыль последнего года явного участка на 20 % выше, чем её считает явный участок.
    Продление явных лет на год тогда сдвигает точку заметно сильнее, чем на книге как есть; допуск теста — сдвиг книги
    как есть плюс шаг печати, без мутации проверка зелёная, с мутацией — срабатывает."""
    loose = config(horizon={"extend_years": 1, "tol_print_steps": 1000.0})
    rows = one(run(book, facts, loose, 3), 3)["numbers"]["rows"]
    step = float(book.get("valuation.headline.print_step"))
    tol = max(abs(r["delta"]) for r in rows.values()) + step   # сдвиг книги как есть плюс шаг печати (цена ≈ 15 ₽)
    tight = config(horizon={"extend_years": 1, "tol_print_steps": tol / step})
    assert one(run(book, facts, tight, 3), 3)["status"] == C.OK
    real = cellmod.terminal_inputs

    def terminal_inputs(p, cell, rows_):
        inputs, n11 = real(p, cell, rows_)
        return dict(inputs, pbt_last_year=inputs["pbt_last_year"] * 1.2), n11

    monkeypatch.setattr(cellmod, "terminal_inputs", terminal_inputs)
    chk = one(run(book, facts, tight, 3), 3)
    assert chk["status"] == C.FIRED and any(line.startswith("точка") for line in chk["findings"])


def test_the_longer_book_moves_only_the_horizon_and_the_new_half_years_of_the_worlds(book):
    """Продление явных лет — подмена книги: год `meta.last_period` позже, у траекторий миров — новые полугодия значением
    последнего; прочие ключи книги те же."""
    longer = C.extended_book(book, 1)
    last = str(book.get("meta.last_period"))
    assert str(longer.get("meta.last_period")) == f"{int(last[:4]) + 1}{last[4:]}"
    moved = C.changed_leaves(book.data, longer.data)
    assert "meta.last_period" in moved
    others = [m for m in moved if m != "meta.last_period"]
    assert others and all(m.startswith("worlds.") and m.endswith((f"{int(last[:4]) + 1}H1", f"{int(last[:4]) + 1}H2"))
                          for m in others)


# ------------------------------------------------------------ класс 4


def test_class_four_catches_an_axis_that_is_off_the_centre(small, facts, monkeypatch):
    """Мутация: ось вида value в положении 0 даёт значение книги плюс 1e-12 (ось задана на величине, которая в центре
    не равна центру). Ловят обе сверки центра: ключи книги и точка бит в бит."""
    real = U.axis_overrides

    def axis_overrides(book_, ax, s):
        out = real(book_, ax, s)
        if s == 0 and ax["kind"] == "value":
            out = {k: v + 1e-12 for k, v in out.items()}
        return out

    monkeypatch.setattr(U, "axis_overrides", axis_overrides)
    chk = one(run(small, facts, config(), 4), 4)
    assert chk["status"] == C.FIRED
    assert any(line.startswith("ось «ERP") and "в центре меняет ключи книги" in line for line in chk["findings"])
    assert any("не равны книге бит в бит" in line for line in chk["findings"])


def test_class_four_catches_an_axis_end_that_moves_an_undeclared_key(small, facts, monkeypatch):
    """Мутация: подмена книги на конце оси ERP заодно сдвигает β_E (ось меняет не только объявленный ключ); спутник
    дисконта за управление — каналы — законен по файлу, а без записи в файле — тоже находка."""
    real = U.consistent_overrides

    def consistent_overrides(book_, overrides):
        out = real(book_, overrides)
        if "valuation.erp" in out and out["valuation.erp"] != book_.get("valuation.erp"):
            out["valuation.beta_e"] = float(book_.get("valuation.beta_e")) + 0.01
        return out

    monkeypatch.setattr(U, "consistent_overrides", consistent_overrides)
    chk = one(run(small, facts, config(), 4), 4)
    assert chk["status"] == C.FIRED
    assert any(line.startswith("ось «ERP") and "valuation.beta_e" in line for line in chk["findings"])
    assert not any("Дисконт за управление" in line for line in chk["findings"])
    monkeypatch.setattr(U, "consistent_overrides", real)
    chk = one(run(small, facts, config(axes={"companions": {}}), 4), 4)
    assert any(line.startswith("ось «Дисконт за управление") and "valuation.governance.components" in line
               for line in chk["findings"])


# ------------------------------------------------------------ класс 5


def test_class_five_catches_a_transitional_term_left_on_after_its_window(small, facts, monkeypatch):
    """Ближний сдвиг ЧПМ, не сошедший к нулю: подменой книги (LT ≠ 0) и мутацией подготовки прогона (ряд, как его
    читает ядро, продолжает последнее значение ближнего пути). Ловит и центр, и концы осей."""
    off = small.with_overrides({"regimes.near_nim_shift.LT": 0.0005})
    chk = one(run(off, facts, config(), 5), 5)
    assert chk["status"] == C.FIRED
    assert any(line.startswith("Ближний сдвиг ЧПМ") for line in chk["findings"])
    assert any(line.startswith("ось «") for line in chk["findings"]), "и на концах осей"
    real = gridmod.prepare

    def prepare(*a, **kw):
        p = real(*a, **kw)
        tl = p.timeline
        keep = next(p.near[q] for q in range(tl.Q, 0, -1) if p.near[q] != 0.0) if any(p.near) else 0.001
        until = max(q for q in range(tl.Q + 1) if tl.year(q) <= 2029)
        return dataclasses.replace(p, near=tuple(x if q <= until else keep for q, x in enumerate(p.near)))

    monkeypatch.setattr(gridmod, "prepare", prepare)
    chk = one(run(small, facts, config(), 5), 5)
    assert chk["status"] == C.FIRED and any(line.startswith("Ближний сдвиг ЧПМ") for line in chk["findings"])


def test_class_five_rules_read_neutral_last_and_absent(book, facts):
    """Правило «last» сверяет ряд со значением последнего квартала сетки, «absent» — что слагаемого вне окна нет;
    окно короче ряда — находка (спреды книг сходятся к LT только с года LT_from)."""
    ctx = make_context(book, facts, live_from_book(book, facts))
    broken, stats = C.transitional_breaks(ctx, {"name": "спреды", "series": "spreads.*", "neutral": "last", "until": 2026})
    assert broken and stats["outside"] > 0 and stats["max_outside"] > 0
    broken, _ = C.transitional_breaks(ctx, {"name": "кризис", "series": "regimes.crisis.override", "neutral": "absent",
                                            "until": 2026})
    assert broken and all("вне окна его быть не должно" in line for line in broken)


def test_class_five_refuses_a_selector_of_a_regime_or_book_that_is_not_in_the_book(book, facts, tmp_path):
    """Находка В-4 проверки фазы 0: режим, книга ЧПД, сектор, сегмент или сценарий селектора, которых нет в книге, —
    отказ (код 2), а не пустой перечень рядов и «зелёно». Звёздочка и имя из книги — читаются."""
    ctx = make_context(book, facts, live_from_book(book, facts))
    p = ctx.prep
    for selector in ("regimes.нет.override", "deviations.нет", "spreads.нет", "glide.нет.n20", "loan_drift.нет",
                     "funds_drift.нет"):
        with pytest.raises(C.Refused, match="а в книге такого нет"):
            C.series_items(ctx, selector)
    regime, spread, scenario = next(iter(p.regimes)), next(iter(p.spreads)), next(iter(p.scenarios))
    for selector in (f"regimes.{regime}.override", f"deviations.{regime}", f"spreads.{spread}", f"glide.{scenario}",
                     "regimes.*.cor", "spreads.*", "funds_drift.retail"):
        C.series_items(ctx, selector)
    bad = tmp_path / "links.yaml"
    bad.write_text('transitional:\n  - {name: "нет такого режима", series: "regimes.нет.override", neutral: absent, '
                   'until: 2026}\n', encoding="utf-8")
    assert C.main(["--only", "5", "--config", str(bad), "--quiet"]) == 2


def test_class_five_names_a_rule_without_values_as_not_checked(small, facts, monkeypatch, capsys):
    """Правило, у чьих рядов в центре нет ни одного значения, не проверялось: замечание с именем и счёт таких правил в
    строке класса; другие правила проверены — класс по ним (зелёно). Все правила такие — класс «не проверялось» (не
    зелёно и не флаг). Пустой ряд здесь — подменой чтения рядов: на книге он бывает по делу (наблюдений A-P2u нет)."""
    real = C.series_items
    monkeypatch.setattr(C, "series_items", lambda ctx, sel: {"пусто": []} if sel == "near" else real(ctx, sel))
    rules = [{"name": "Пустое", "series": "near", "neutral": 0.0, "until": 2029},
             {"name": "Сдвиг ЧПМ режима", "series": "regimes.*.nim_shift", "neutral": "last", "until": 2028}]
    chk = one(run(small, facts, config(transitional=rules), 5), 5)
    assert chk["status"] == C.OK, chk["findings"][:3]
    assert chk["tally"] == "правил 2, из них без рядов (не проверялось) — 1"
    assert chk["notes"] == ["правило «Пустое» не проверялось: в центре у рядов «near» нет ни одного значения (рядов 1)"]
    out = run(small, facts, config(transitional=rules[:1]), 5)
    chk = one(out, 5)
    assert chk["status"] == C.NO_RULES and chk["status_words"] == C.NOT_CHECKED and out["flags"] == []
    assert chk["tally"] == "правил 1, из них без рядов (не проверялось) — 1"
    assert any("проверка пустая" in note for note in chk["notes"])
    C.report(out, quiet=True)
    assert "не проверялось (правил 1, из них без рядов (не проверялось) — 1)" in capsys.readouterr().out
    # без перечня — по-прежнему «правил нет»
    chk = one(run(small, facts, config(transitional=[]), 5), 5)
    assert chk["status"] == C.NO_RULES and chk["status_words"] == "правил нет" and chk["tally"] == "правил 0"


# ------------------------------------------------------------ класс 6


def test_class_six_prints_no_rules_until_the_charter_and_judges_the_rules_once_given(book, facts):
    """Без таблицы устава — «правил нет» (не зелёно и не флаг); правила устава сверяют центр книги: середина диапазона
    свидетельств, середина концов оси, среднее, медиана, число."""
    out = run(book, facts, config(centres=[], centre_types=False), 6)
    assert one(out, 6)["status"] == C.NO_RULES and out["flags"] == []
    key = "valuation.terminal.fade"   # ключ с осью вида value (у передачи ключевой книги Совкомбанка ось — сдвиг)
    target = float(book.get(key))
    [ax] = [a for a in book.get("valuation.uncertainty.axes") if a["kind"] == "value" and a["paths"] == [key]]
    off_mid = abs((float(ax["low"]) + float(ax["high"])) / 2 - target)
    rules = [{"key": key, "rule": "midpoint", "lo": 0.0, "hi": 2 * target, "tol": 1e-12},
             {"key": key, "rule": "axis_midpoint", "tol": off_mid + 1e-12},
             {"key": key, "rule": "mean", "values": [0.0, target, 2 * target], "tol": 1e-12},
             {"key": key, "rule": "median", "values": [0.0, target, 9.0], "tol": 1e-12},
             {"key": key, "rule": "value", "value": target}]
    assert one(run(book, facts, config(centres=rules, centre_types=False), 6), 6)["status"] == C.OK
    off = rules + [{"key": "valuation.erp", "rule": "midpoint", "lo": 0.0, "hi": 0.1, "tol": 1e-9, "source": "устав §1"}]
    out = run(book, facts, config(centres=off, centre_types=False), 6)
    chk = one(out, 6)
    assert chk["status"] == C.FIRED and chk["count"] == 1 and "valuation.erp" in chk["findings"][0]
    assert len(out["flags"]) == 1 and out["flags"][0].startswith("класс 6")


def test_class_six_judges_the_type_of_every_rule_and_of_every_axis_of_the_book(book, facts):
    """Решения ведущего Совкомбанка № 11, раздел А: у каждого правила класса 6 — тип центра (А–Е; не суждения — «факт», «тождество»);
    у каждой оси книги — правило-суждение с типом на её ключе или на её конце (выражение книги называет первый путь оси или её имя;
    поле axis). Правило без типа, тип не из таблицы и ось без правила с типом — находка (красный флаг); «факт» и «тождество» ось не
    покрывают. Без centre_types в файле связей проверка типов не делается."""
    axes = list(book.get("valuation.uncertainty.axes"))
    erp = next(a for a in axes if a["paths"][0] == "valuation.erp")
    covered = []
    for a in axes:
        first = str(a["paths"][0])
        if a is erp:
            continue
        covered.append({"key": f"конец оси {a['name']}", "rule": "value", "type": "В", "value": 0.0, "tol": 1e30,
                        "book_expr": f"0.0 * sum([1 for a in B('valuation.uncertainty.axes') if a['paths'][0] == '{first}'])"})
    erp_rule = {"key": "valuation.erp", "rule": "value", "type": "Е", "value": float(book.get("valuation.erp")), "tol": 1e-12}
    assert one(run(book, facts, config(centres=covered + [erp_rule], centre_types=True), 6), 6)["status"] == C.OK
    # ось без правила-суждения: правило на её ключе — «тождество», не тип центра
    out = run(book, facts, config(centres=covered + [dict(erp_rule, type="тождество")], centre_types=True), 6)
    chk = one(out, 6)
    assert chk["status"] == C.FIRED and chk["count"] == 1 and "valuation.erp" in chk["findings"][0] and chk["findings"][0].startswith("ось «")
    assert chk["numbers"]["types"]["axes_without_type"] == 1 and out["flags"][0].startswith("класс 6")
    # правило без типа и тип не из таблицы — по находке на каждое; ось ERP при этом не покрыта
    bare = {k: v for k, v in erp_rule.items() if k != "type"}
    chk = one(run(book, facts, config(centres=covered + [bare, dict(erp_rule, type="Ж")], centre_types=True), 6), 6)
    assert chk["count"] == 3 and sum("правило класса 6 без типа центра" in f for f in chk["findings"]) == 2
    # имя оси в выражении книги покрывает ось; поле axis — тоже
    by_name = {"key": "конец ERP", "rule": "value", "type": "Е", "value": 0.0, "tol": 1e30,
               "book_expr": f"0.0 * sum([1 for a in B('valuation.uncertainty.axes') if a['name'] == '{erp['name']}'])"}
    assert one(run(book, facts, config(centres=covered + [by_name], centre_types=True), 6), 6)["status"] == C.OK
    by_field = {"key": "ERP", "rule": "value", "type": "Е", "value": 0.0, "tol": 1e30, "axis": "valuation.erp", "book_expr": "0.0"}
    assert one(run(book, facts, config(centres=covered + [by_field], centre_types=True), 6), 6)["status"] == C.OK
    # без centre_types — типы не судятся
    assert one(run(book, facts, config(centres=covered + [bare], centre_types=False), 6), 6)["status"] == C.OK
    assert C.CENTRE_TYPES == ("А", "Б", "В", "Г", "Д", "Е") and set(C.OTHER_TYPES) == {"факт", "тождество"}


def test_the_config_of_the_tree_gives_every_rule_a_type_and_every_axis_a_typed_rule(book, facts):
    """Файл связей дерева (решения № 11, раздел А): centre_types включён, у каждого правила — тип из таблицы, ни одной оси книги без
    правила-суждения с типом."""
    cfg = C.load_config(C.CONFIG)
    assert cfg.get("centre_types") is True
    assert all(r.get("type") in C.CENTRE_TYPES + C.OTHER_TYPES for r in cfg["centres"])
    chk = C.Check(6, "centres", "")
    t = C.type_scan(book, cfg["centres"], chk)
    assert t["axes_without_type"] == 0 and chk.count == 0, chk.findings[:3]
    # ключи с центром без оси (метка суждения шаблона; проверка исполнения круга 11) — тоже с правилом и типом
    assert cfg.get("centre_template")
    chk = C.Check(6, "centres", "")
    t = C.type_scan(book, cfg["centres"], chk, (C.ROOT / cfg["centre_template"]).read_text(encoding="utf-8"))
    assert t["centre_keys"] > 50 and t["centre_keys_without_type"] == 0 and chk.count == 0, chk.findings[:3]


def test_class_six_judges_keys_with_a_centre_and_no_axis_by_the_judgment_tag_of_the_template(book, facts):
    """Решения № 11, раздел А, «тип — у каждого ключа с центром или осью»: ключ шаблона с меткой суждения [В…] / [Р/В…] в комментарии
    строки — ключ с центром; правило с типом на нём, его предке или потомке (или формула правила читает ключ) его покрывает; иначе —
    находка. Строки списков и комментарии — не ключи."""
    text = chr(10).join([
        "joint:",
        "  regime_prob: {soft: 0.34}   # частоты [Р/В: годы банка]",
        "  reg_prob_given_regime:      # [В: как в книге Т]",
        "    crisis: {mid: 0.25}       # [В: как в книге Т]",
        "  world_prob: {N: 0.35}       # [Ф: запись семейства]",
        "  # tagged: 1                 # [В] — комментарий",
        "  axes:",
        "    - {name: x, low: 1}       # [В: ось]",
        "valuation:",
        "  erp: 0.0557                 # [В]",
    ])
    keys = C.centre_keys(text)
    assert keys == [(2, "joint.regime_prob"), (3, "joint.reg_prob_given_regime"), (4, "joint.reg_prob_given_regime.crisis"),
                    (10, "valuation.erp")]
    rules = [{"key": "joint.reg_prob_given_regime", "rule": "value", "type": "Е", "value": 0.0},
             {"key": "вероятность", "rule": "value", "type": "В", "value": 0.0, "book_expr": "B('joint.regime_prob')['soft'] * 0"}]
    assert C.rule_covers(rules[0], "joint.reg_prob_given_regime.crisis") and C.rule_covers(rules[1], "joint.regime_prob")
    chk = C.Check(6, "centres", "")
    t = C.type_scan(book, rules, chk, text)
    assert t["centre_keys"] == 4 and t["centre_keys_without_type"] == 1 and chk.count >= 1
    assert any(f.startswith("ключ с центром valuation.erp") for f in chk.findings)
    # без шаблона ключи с центром не судятся (поле centre_template файла связей)
    chk = C.Check(6, "centres", "")
    assert "centre_keys" not in C.type_scan(book, rules, chk, None)


# ------------------------------------------------------------ командная строка и запись


def test_the_command_line_writes_the_record_and_answers_with_codes(tmp_path, capsys):
    target = tmp_path / "classes.json"
    assert C.main(["--only", "6", "--json", str(target)]) == 0
    rec = json.loads(target.read_text(encoding="utf-8"))
    assert rec["schema"] == C.SCHEMA and rec["model_untouched"] is True and rec["flags"] == []
    assert [c["key"] for c in rec["checks"]] == ["centres"] and rec["checks"][0]["status"] == C.OK
    assert "класс 6 — центр суждения равен правилу устава: зелёно" in capsys.readouterr().out   # правила устава — зелёные
    assert C.main(["--only", "7"]) == 2
    assert C.main(["--config", str(tmp_path / "нет.yaml")]) == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("cross_cell: {legal_links: {nowhere: x}}\n", encoding="utf-8")
    assert C.main(["--only", "2", "--config", str(bad)]) == 2


def test_the_parallel_run_writes_the_same_record_as_the_sequential_one(small, tmp_path):
    """PLAYBOOK §6: задачи по рабочим процессам дают ту же запись, что подряд (кроме времени) — и на зелёной книге, и
    со срабатываниями (ближний сдвиг ЧПМ не сходит к нулю: находки центра и концов осей идут в том же порядке)."""
    import subprocess
    import yaml
    off = small.with_overrides({"regimes.near_nim_shift.LT": 0.0005})
    book_file = tmp_path / "book.yaml"
    book_file.write_text(yaml.safe_dump(dict(off.data), allow_unicode=True, sort_keys=False), encoding="utf-8")
    cfg = config(cross_cell=quiet_cross_cell(cells=["N/soft/schedule", "M/crisis/mid"],
                                             cell_inputs=[{"input": "cor", "size": 0.002},
                                                          {"input": "requirement", "size": 0.005}]))
    cfg_file = tmp_path / "links.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    records = []
    for workers in (1, 2):
        target = tmp_path / f"run-{workers}.json"
        done = subprocess.run([sys.executable, "-B", str(TOOLS / "class_checks.py"), "--book", str(book_file),
                               "--config", str(cfg_file), "--only", "2,4,5", "--workers", str(workers), "--quiet",
                               "--json", str(target)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                              env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
        assert done.returncode == 1, done.stdout + done.stderr
        rec = json.loads(target.read_text(encoding="utf-8"))
        rec.pop("seconds")
        assert rec.pop("workers") == workers
        for c in rec["checks"]:
            c.pop("seconds")
        records.append(rec)
    assert records[0] == records[1]
    assert one(records[0], 5)["status"] == C.FIRED and one(records[0], 2)["numbers"]["cell_runs"] == 4


def test_every_firing_is_a_red_flag_and_rules_absent_is_not():
    checks = [{"cls": 1, "key": "identities", "title": "t1", "status": C.OK, "count": 0, "findings": []},
              {"cls": 3, "key": "horizon", "title": "t3", "status": C.FIRED, "count": 3, "findings": ["а", "б", "в"]},
              {"cls": 5, "key": "transitional", "title": "t5", "status": C.ERROR, "count": 1, "findings": ["г"]},
              {"cls": 6, "key": "centres", "title": "t6", "status": C.NO_RULES, "count": 0, "findings": []}]
    flags = C.flag_lines(checks)
    assert len(flags) == 2
    assert flags[0].startswith("класс 3") and "находок 3" in flags[0] and flags[0].endswith("…")
    assert flags[1].startswith("класс 5") and "НЕ ОТРАБОТАЛА" in flags[1]


# ------------------------------------------------------------ блок перевывода книги


def classes_block(status: str = C.FIRED) -> dict:
    return {"error": None, "config": {"status": "заготовка"}, "model_untouched": True, "seconds": 1.0,
            "checks": [{"cls": 3, "key": "horizon", "title": C.CLASS_TITLES[3], "status": status,
                        "status_words": C.STATUS_WORDS[status], "count": 1 if status == C.FIRED else 0,
                        "findings": ["точка: 1 → 2 ₽"] if status == C.FIRED else [], "notes": [], "numbers": {},
                        "seconds": 0.1}],
            "flags": C.flag_lines([{"cls": 3, "key": "horizon", "title": C.CLASS_TITLES[3], "status": status,
                                    "count": 1, "findings": ["точка: 1 → 2 ₽"]}])}


def test_the_rederive_command_carries_the_class_flags_into_its_flags_print_and_brief():
    """Блок проверок классов в команде перевывода: каждое срабатывание — красный флаг итога и строка в клетке
    «Проверки» листа решения; блок печатается после приёмочных проверок и строками раздела 3 листа решения."""
    tables = R.results_as_run(R.Tree())
    now = dict(copy.deepcopy(tables), label="classes", flags=[], acceptance=[], classes=classes_block())
    flags = R.flags_of(now)
    assert any(line.startswith("класс 3") for line in flags)
    said: list[str] = []
    R.print_classes(now, said.append)
    assert any("ПРОВЕРКИ КЛАССОВ ОШИБОК" in line for line in said)
    assert any("класс 3" in line and "СРАБОТАЛА" in line for line in said)
    now["flags"] = flags
    text = R.brief(now, None)
    assert "| Класс 3:" in text and "СРАБОТАЛА" in text
    green = dict(now, classes=classes_block(C.OK))
    assert not any(line.startswith("класс 3") for line in R.flags_of(green))


def test_the_rederive_block_prints_the_tally_and_not_checked_as_not_green():
    """Строка класса в блоке перевывода и в листе решения несёт счёт проверенного; пустая проверка («не проверялось»)
    — не флаг и не «зелёно»: её слова и «не зелёно»."""
    tables = R.results_as_run(R.Tree())
    tally = "клеток одна — не сверялись, подмен входа клетки — 0, возмущений книги — 0"
    block = {"error": None, "config": {"status": "заготовка"}, "model_untouched": True, "seconds": 1.0, "flags": [],
             "checks": [{"cls": 2, "key": "cross_cell", "title": C.CLASS_TITLES[2], "status": C.NO_RULES,
                         "status_words": C.NOT_CHECKED, "tally": tally, "count": 0, "findings": [],
                         "notes": ["проверка пустая"], "numbers": {}, "seconds": 0.1}]}
    now = dict(copy.deepcopy(tables), label="classes", flags=[], acceptance=[], classes=block)
    assert not any(line.startswith("класс 2") for line in R.flags_of(now))
    said: list[str] = []
    R.print_classes(now, said.append)
    assert any(line.startswith(f"  класс 2 — {C.CLASS_TITLES[2]}: не проверялось ({tally})") for line in said), said
    text = R.brief(dict(now, flags=R.flags_of(now)), None)
    assert f"| Класс 2: {C.CLASS_TITLES[2]} | не проверялось ({tally}) |" in text
    assert "| не проверялось — не зелёно |" in text


def test_the_rederive_command_flags_class_checks_that_did_not_run(tmp_path):
    """Нет файла связей в дереве — блок не отработал, и это красный флаг, а не тишина."""
    tree = R.Tree(root=tmp_path / "tree")
    (tree.book_dir).mkdir(parents=True)
    got = R.class_numbers(tree, tree.book_yaml, tmp_path)
    assert got["error"] and got["checks"] == []
    now = {"derive": None, "quick": None, "classes": got}
    assert any("проверки классов ошибок не отработали" in line for line in R.flags_of(now))


def test_class_six_formula_rules_read_the_facts_and_the_book(facts, book):
    """Правило центра `facts` (решения ведущего Совкомбанка № 2, В9): формула считает центр из файлов фактов (F — узел, Q — ряд
    кварталов) и книги (B); book_expr заменяет значение книги формулой; ошибка формулы — отказ, а не молчаливое «зелёно»."""
    q = facts.file("mgmt_quarterly")["quarters"]
    want = sum(float(q[p]["cor_exact"]["v"]) for p in sorted(q) if "2024Q2" <= p <= "2026Q2") / 9
    rule = {"key": "regimes.norm.cor.2027", "rule": "facts", "expr": "mean(Q('mgmt_quarterly', 'cor_exact', '2024Q2', '2026Q2'))"}
    assert C.centre_expected(book, rule, facts) == pytest.approx(want, abs=1e-15)
    assert C.formula_value(book, facts, "B('credit.kappa') + F('balance', 'iea') * 0", "проба") == pytest.approx(float(book.get("credit.kappa")))
    with pytest.raises(C.Refused):
        C.formula_value(book, facts, "__import__('os')", "проба")
    with pytest.raises(C.Refused):
        C.centre_expected(book, rule, None)
    assert "facts" in C.RULES
