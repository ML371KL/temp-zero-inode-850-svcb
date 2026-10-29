# -*- coding: utf-8 -*-
"""Контрольная модель на фикстуре формы образца (tests/fixtures/core): годовая ветвь (docs/MODEL.md §17) —
решение о дивиденде раз в год, таблица состава книг образца, книга кредитов по справедливой стоимости.

* «Ключа нет — прежняя ветвь»: поведенческие ключи панели в нейтральных значениях дают тот же расчёт, что
  книга без них, бит в бит.
* Случаи набора машинной книги, которые книга панели пропускает, исполняются здесь — на каталоге-заготовке,
  собранном из фикстуры: годовая ветвь (метка annual_only в tests/test_control_model.py: конец квартала
  собрания и D_pend, ввод ε, цена с объявленным дивидендом, даты записи реестра, мост до экс-даты) и строка
  FVC кредитов по справедливой стоимости (перечень FAIR_VALUE_TESTS там же).
* Две правки без ключей: остатки книг прямыми узлами balance.books.<b> при любом наборе кредитных книг;
  решение о дивиденде внутри неполного года якоря.
* Сверка с ядром (метка ci_only; ядро импортируется только в момент теста) — в допусках М§17.
* Сводка сверки data/checks/control_model.json: графа контрольной модели воспроизводится, пока в data/
  лежит книга той же версии; числа контрольной модели в документах — метками из этой сводки
  (источник `control:` инструмента ops/tools/render_numbers.py).
"""

from __future__ import annotations

import copy
import importlib
import importlib.util
import inspect
import json
import math
import shutil
import sys

import pytest
import yaml

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]

FIXTURE = cm.ROOT / "tests" / "fixtures" / "core"
REGRESSION_REL, REGRESSION_ABS = 1e-12, 1e-10          # допуск регрессии книги (М§18)
AGM_LATE = {3: {"agm_quarter": 3, "reg_deduction_quarter": 4, "payment_quarter": 4, "checkpoints": [4]},
            4: {"agm_quarter": 4, "reg_deduction_quarter": 4, "payment_quarter": 4, "checkpoints": [4]}}


def form_book() -> dict:
    return json.loads((FIXTURE / "book.json").read_text(encoding="utf-8"))


def form_facts() -> dict:
    return cm.c_facts_bundle(FIXTURE / "facts")


@pytest.fixture(scope="module")
def inputs():
    return form_book(), form_facts()


@pytest.fixture(scope="module")
def control(inputs):
    book, facts = inputs
    try:
        return cm.c_control_run(book, facts)
    except cm.ControlUnsupported as exc:
        pytest.fail(f"контрольная модель не считает книгу формы образца: {exc}")


def _values(res: dict) -> list:
    return [(c["v_ri"], c["bv_v"], c["x_t"], [r["bv"] for r in c["rows"]], [r["rwa"] for r in c["rows"]],
             [r["pbt"] for r in c["rows"]], [r["div"] for r in c["rows"]]) for c in res["cells"]]


# ============================================================================ годовая ветвь на форме образца


@pytest.mark.tact
def test_sample_form_runs_on_the_annual_branch(control):
    """Форма образца: годовая ветвь, таблица состава книг, одна книга с долей кредитов по справедливой
    стоимости; DDM = RI и тождество капитала в каждой клетке; решение о дивиденде — раз в год."""
    ctx = control["ctx"]
    assert not control["quarterly"] and control["growth_rule"] is None
    assert not ctx["A"]["direct_books"] and len(ctx["fv"]) == 1
    assert control["divisor"] == control["shares_out"] and control["history_test"] == cm.HIST_EXACT
    for c in control["cells"]:
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        bv = ctx["A"]["BV"]
        for r in c["rows"]:
            assert math.isclose(bv + r["ci"] - r["div"], r["bv"], rel_tol=1e-9)
            assert "quarters" not in r and len(r["div_list"]) <= 1
            bv = r["bv"]
        assert set(c["decisions"]) == set(range(control["years"][0], control["years"][-1]))


# вне такта сервера: годовую ветвь книга репозитория не исполняет — её тесты на фикстуре идут в CI
def test_no_new_key_means_the_sample_branch(inputs, control):
    """Поведенческий ключ панели в нейтральном значении — тот же расчёт, что без ключа, бит в бит (М§0.6):
    годовой календарь, выключенное ограничение роста, делитель «в обращении», нулевые связи с объёмом и
    постоянные прочие активы, тест истории вида exact."""
    book, facts = inputs
    b = copy.deepcopy(book)
    b["dividends"]["calendar"]["frequency"] = "annual"
    b["dividends"]["policy"]["history_test"] = cm.HIST_EXACT
    b["valuation"]["shares_basis"] = "outstanding"
    b["fees"]["volume_link"] = 0.0
    b["other"]["insurance_volume_link"] = 0.0
    b["opex"]["volume_link"] = 0.0
    b["volumes"]["other_assets_fixed"] = 0.0
    b["capital"]["growth_constraint"] = {"enabled": False, "order": cm.ORDER_DIV_FIRST, "min_growth_scale": 0.0,
                                         "lookahead_quarters": 8, "glide_pp_per_quarter": 0.0025,
                                         "catch_up_rate": 0.25, "tol": 0.0001}
    same = cm.c_control_run(b, facts)
    assert _values(same) == _values(control)
    assert (same["point"], same["low"], same["high"]) == (control["point"], control["low"], control["high"])
    assert same["dps_history"] == control["dps_history"]


# ============================================================================ случаи годовой ветви набора машинной книги


@pytest.fixture(scope="module")
def sample_data(tmp_path_factory):
    """Каталог-заготовка формы образца: assumptions/assumptions.yaml и facts/ — как каталог данных сверки."""
    root = tmp_path_factory.mktemp("sample_form")
    (root / "assumptions").mkdir()
    (root / "assumptions" / "assumptions.yaml").write_text(
        yaml.safe_dump(form_book(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    shutil.copytree(FIXTURE / "facts", root / "facts")
    return root


def sample_form_cases() -> list:
    """Случаи набора машинной книги, которые исполняются на форме образца: каждый тест годовой ветви (метка
    annual_only) с каждым значением его параметра и тесты строки FVC (перечень FAIR_VALUE_TESTS). Метка ci_only
    случая — как у теста (сверка с ядром); прочие случаи идут вне такта: ветви, которых книга репозитория не
    исполняет, такт сервера не проверяет."""
    out = []
    names = sorted(name for name, fn in vars(tcm).items() if getattr(fn, "annual_only", False))
    for name in names + list(tcm.FAIR_VALUE_TESTS):
        marks = list(getattr(getattr(tcm, name), "pytestmark", []))
        ci = [pytest.mark.ci_only] if any(m.name == "ci_only" for m in marks) else []
        grids = [m for m in marks if m.name == "parametrize"]
        if not grids:
            out.append(pytest.param(name, {}, id=name, marks=ci))
            continue
        (grid,) = grids
        arg, values = grid.args
        tags = grid.kwargs.get("ids") or [str(v) for v in values]
        out.extend(pytest.param(name, {arg: value}, id=f"{name}[{tag}]", marks=ci) for value, tag in zip(values, tags))
    return out


@pytest.mark.parametrize("name, params", sample_form_cases())
def test_book_suite_case_on_the_sample_form(sample_data, monkeypatch, name, params):
    """Тест набора машинной книги — на форме образца: тело теста исполняется на каталоге-заготовке из фикстуры;
    книга и прогон — этого каталога. Тест годовой ветви идёт без пропуска по календарю книги; пропуск внутри
    тела — провал: случай обязан исполниться хотя бы здесь."""
    monkeypatch.setenv(tcm.DATA_DIR_ENV, str(sample_data))
    test = getattr(tcm, name)
    body = getattr(test, "__wrapped__", test)
    book, facts = tcm._inputs()
    assert not cm.c_is_quarterly(book), "каталог-заготовка формы образца обязан идти годовой ветвью"
    args = dict(params)
    for arg in inspect.signature(body).parameters:
        if arg == "inputs":
            args[arg] = (book, facts)
        elif arg == "control":
            args[arg] = tcm.shared_control()
    try:
        body(**args)
    except pytest.skip.Exception as exc:
        pytest.fail(f"случай набора машинной книги на форме образца пропущен, а не исполнен: {exc}")


@pytest.mark.tact
def test_every_skipped_book_suite_test_has_its_case(control):
    """Каждый тест набора машинной книги, который книга панели пропускает, исполняется на форме образца: случаи
    годовой ветви собраны по метке annual_only, тесты строки FVC — по перечню; тело каждого доступно, причина
    пропуска называет тест, который исполняет случай здесь; у формы образца кредиты по справедливой стоимости
    есть, и строка FVC включена."""
    annual = sorted(name for name, fn in vars(tcm).items() if getattr(fn, "annual_only", False))
    assert annual, "в наборе машинной книги нет тестов годовой ветви"
    cases = [c.values[0] for c in sample_form_cases()]
    assert sorted(set(cases)) == sorted(annual + list(tcm.FAIR_VALUE_TESTS)) and len(cases) >= len(set(cases))
    assert all(callable(getattr(tcm, name).__wrapped__) for name in annual)
    assert all(callable(getattr(tcm, name)) for name in tcm.FAIR_VALUE_TESTS)
    for reason in (tcm.ANNUAL_ONLY, tcm.NO_FAIR_VALUE):
        assert test_book_suite_case_on_the_sample_form.__name__ in reason
    assert control["ctx"]["fv"] and cm.c_bnum(control["ctx"]["B"], "credit.fv_loans_factor") > 0.0


# ============================================================================ остатки книг прямыми узлами


def _without_fair_value(book: dict, facts: dict) -> tuple[dict, dict]:
    """Вариант формы образца без отдельной механики кредитов по справедливой стоимости: они внутри
    корпоративной книги (как у панели), ключ fv_share снят."""
    b, f = copy.deepcopy(book), copy.deepcopy(facts)
    fv_book = next(name for name, sp in b["nii"]["books"].items() if "fv_share" in sp)
    b["nii"]["books"][fv_book].pop("fv_share")
    fair = f["balance"]["loans_fvtpl"]["v"]
    f["balance"]["loans_ac_gross"]["commercial"]["v"] += fair
    f["balance"]["loans_fvtpl"]["v"] = 0.0
    return b, f


# вне такта сервера: годовую ветвь книга репозитория не исполняет — её тесты на фикстуре идут в CI
def test_direct_nodes_give_the_same_books_as_the_table(inputs):
    """Остатки якоря прямыми узлами balance.books.<b> — при любом наборе книг: те же остатки, что даёт
    таблица состава книг образца, дают тот же расчёт бит в бит; имя корпоративной книги не зашито."""
    book, facts = _without_fair_value(*inputs)
    table = cm.c_control_run(book, facts)
    assert not table["ctx"]["A"]["direct_books"] and not table["ctx"]["fv"]
    direct_facts = copy.deepcopy(facts)
    direct_facts["balance"]["books"] = {b: {"v": v, "calc": "тест: остаток таблицы состава книг"}
                                        for b, v in table["ctx"]["A"]["E0"].items()}
    direct = cm.c_control_run(book, direct_facts)
    assert direct["ctx"]["A"]["direct_books"]
    assert _values(direct) == _values(table)
    assert direct["derived"] == table["derived"]
    # другой набор кредитных книг: книга переименована, вторая разделена на две — расчёт идёт
    b2, f2 = copy.deepcopy(book), copy.deepcopy(direct_facts)
    books, nodes = b2["nii"]["books"], f2["balance"]["books"]
    loans = [name for name, sp in books.items() if sp.get("sector")]
    old, split = loans[0], loans[-1]
    order = {}
    for name, sp in books.items():
        if name == old:
            order["big_business"] = sp
        elif name == split:
            order[split] = sp
            order[split + "_b"] = copy.deepcopy(sp)
        else:
            order[name] = sp
    b2["nii"]["books"] = order
    nodes["big_business"] = nodes.pop(old)
    half = nodes[split]["v"] / 2.0
    nodes[split] = {"v": half, "calc": "тест"}
    nodes[split + "_b"] = {"v": half, "calc": "тест"}
    f2["nii_books"]["books"]["big_business"] = f2["nii_books"]["books"].pop(old)
    f2["nii_books"]["books"][split + "_b"] = copy.deepcopy(f2["nii_books"]["books"][split])
    dens = b2["capital"]["rwa"]["density"]
    dens["big_business"], dens[split + "_b"] = dens.pop(old), dens[split]
    other = cm.c_control_run(b2, f2)
    assert len(other["ctx"]["loans"]) == len(loans) + 1
    # разделённая пополам книга с теми же параметрами — тот же портфель: оценка та же до округления
    assert other["point"] == pytest.approx(table["point"], rel=1e-9)
    # книги нет ни в узлах, ни в таблице — громкий отказ входа, а не «не поддержано»
    lost = copy.deepcopy(f2)
    lost["balance"]["books"].pop("big_business")
    with pytest.raises(cm.ControlInputError):
        cm.c_control_run(b2, lost)


# ============================================================================ решение в неполном году якоря


def _agm_after_anchor(book: dict, facts: dict, quarter: int) -> tuple[dict, dict]:
    """Вариант: годовое собрание — в квартале года якоря после якоря; дивиденд за прошлый год ещё не
    объявлен (остаток к выплате якоря относится к более раннему году прибыли)."""
    b, f = copy.deepcopy(book), copy.deepcopy(facts)
    b["dividends"]["calendar"] = dict(AGM_LATE[quarter])
    f["balance"]["dividends_payable_year"] = cm.c_per_parse(b["meta"]["anchor_period"])[0] - 2
    return b, f


# вне такта сервера: годовую ветвь книга репозитория не исполняет — её тесты на фикстуре идут в CI
@pytest.mark.parametrize("quarter", sorted(AGM_LATE))
def test_decision_inside_the_incomplete_anchor_year(inputs, control, quarter):
    """Решение о дивиденде в неполном году якоря принимается в своём квартале: собрание после якоря
    решает за прошлый год на фактах его прибыли; дивиденд уходит из капитала в этом квартале."""
    book, facts = _agm_after_anchor(*inputs, quarter)
    res = cm.c_control_run(book, facts)
    ctx = res["ctx"]
    y0 = ctx["anchor"][0]
    stub = ctx["periods"][0]
    assert stub["stub"] and quarter in stub["quarters"]
    for c in res["cells"][::5]:
        d = c["decisions"][y0 - 1]
        fact = sum(ctx["A"]["pnl"][f"{y0 - 1}Q{q}"]["ni_shareholders"] for q in range(1, cm.QY + 1))
        if d["kind"] == "policy":
            assert d["base"] <= fact + 1e-9                         # база — факт прибыли года (за вычетом купона)
        row = c["rows"][0]
        assert row["div"] == d["div"] > 0.0
        assert row["div_list"] == [(stub["quarters"].index(quarter), d["div"])]
        assert math.isclose(ctx["A"]["BV"] + row["ci"] - row["div"], row["bv"], rel_tol=1e-9)
        assert abs(c["v_ddm"] - c["v_ri"]) <= 1e-9 * max(1.0, abs(c["v_ri"]))
        assert set(c["decisions"]) == {y0 - 1} | set(control["cells"][0]["decisions"])
    # факты говорят, что дивиденд за прошлый год уже объявлен, — второго решения в году якоря нет
    declared = copy.deepcopy(facts)
    declared["balance"]["dividends_payable_year"] = y0 - 1
    again = cm.c_control_run(book, declared)
    assert all(y0 - 1 not in c["decisions"] and c["rows"][0]["div"] == 0.0 for c in again["cells"])


# ============================================================================ сверка с ядром (в момент теста)


def _core_run(book: dict, facts_dir, facts_patch=None):
    try:
        book_mod, grid_mod = importlib.import_module("model.book"), importlib.import_module("model.grid")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc})")
    try:
        facts = book_mod.load_facts(facts_dir)
        return grid_mod.run_grid(book_mod.book_from_dict(book, facts=facts), facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу формы образца: {type(exc).__name__}: {str(exc)[:500]}")


@pytest.mark.ci_only
def test_control_matches_core_on_the_sample_form(inputs, control):
    book, _ = inputs
    run = _core_run(book, FIXTURE / "facts")
    rows = tcm.compare_with_core(run, control)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк\n" + tcm._fail_lines(bad)
    assert not tcm.exact_match(run, control), "V0 слоёв совпали с ядром до 1e-9 — общий код"


@pytest.mark.ci_only
@pytest.mark.parametrize("quarter", sorted(AGM_LATE))
def test_control_matches_core_with_the_decision_in_the_anchor_year(inputs, tmp_path, quarter):
    """Решение в неполном году якоря — в допусках М§17 против ядра (факты варианта — во временном каталоге)."""
    book, facts = _agm_after_anchor(*inputs, quarter)
    folder = tmp_path / "facts"
    folder.mkdir()
    for name, tree in facts.items():
        (folder / f"{name}.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    run = _core_run(book, folder)
    ctl = cm.c_control_run(book, facts)
    rows = tcm.compare_with_core(run, ctl)
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"вне допусков М§17: {len(bad)} из {len(rows)} строк\n" + tcm._fail_lines(bad)
    y0 = ctl["ctx"]["anchor"][0]
    assert any(r["what"].startswith(f"DPS за {y0 - 1}") for r in rows)


# ============================================================================ регрессия сводки сверки


# вне такта сервера: регрессия файла сводки против кода — дело CI; в такте она платила бы за два прогона
# сетки чисел гейта знака объёмных эффектов
def test_checks_file_control_column_is_reproduced():
    """Графа контрольной модели в сводке data/checks/control_model.json воспроизводится в допуске
    регрессии, пока в data/ лежит книга той же версии (слова и значения строк — от контрольной модели; ядро — только для
    числа строк: правило ПОРОГ и строки за решениями обеих моделей). Сводку другой версии книги перевыпускает интеграция."""
    if tcm.data_dir() is not None:
        pytest.skip("сводка относится к книге репозитория, а прогон идёт на каталоге-заготовке")
    if not tcm.CHECKS_JSON.exists():
        pytest.skip("сводки сверки ещё нет (её пишет интеграция)")
    doc = json.loads(tcm.CHECKS_JSON.read_text(encoding="utf-8"))
    try:
        book, facts = cm.c_book_machine(), cm.c_facts_bundle()
    except cm.ControlInputError as exc:
        pytest.fail(f"нет машинной книги или фактов ({exc})")
    if str(doc.get("book_version")) != str(book["meta"]["version"]):
        pytest.skip(f"сводка — книги {doc.get('book_version')}, в data/ — книга {book['meta']['version']}: "
                    f"сводку перевыпускает интеграция")
    ctl = tcm.shared_control()
    rows = tcm.compare_with_core(tcm._stub_core(ctl, 1.0), ctl)
    n_stub = len(rows)
    if any(r["what"].startswith(tcm.SIGN_WORDS) for r in doc["rows"]):
        # строки чисел гейта знака объёмных эффектов писатель сводки добавляет у книги с ключом гейта
        sign = tcm.shared_gates()["volume_sign"]
        rows += tcm.gate_rows(sign, sign)
    if any(r["what"].startswith(tcm.LEVEL_WORDS) for r in doc["rows"]):
        # строки уровней слоя «рыночные ставки как есть» — у книги с ключом checks.window_backtest
        window = cm.c_window_backtest(ctl)
        assert window is not None, "в сводке есть строки уровней, а в книге нет ключа checks.window_backtest"
        # «ядро» строк уровней — числа самой контрольной модели в форме узла ядра: при множителях CoR по книгам
        # (credit.book_relative) реализованная CoR — cor, CoR на составе якоря — cor_mix0 (у контроля это cor_realized и
        # cor); иначе строки «на составе якоря» нет у заглушки, и её слов нет среди строк
        core_like = dict(window)
        if "cor_realized" in window:
            core_like.update(cor=window["cor_realized"], cor_mix0=window["cor"])
        rows += tcm.level_rows(core_like, window)
    if any(r["what"] == tcm.CIR_GOAL_WORDS for r in doc["rows"]):
        goal = cm.c_cir_level(ctl)
        assert goal is not None and goal["scope"] == cm.SCOPE_MARKET
        rows.append(tcm.cir_goal_row(goal["value"], goal["value"]))
    mine = {r["what"]: r for r in rows}
    # число строк сводки — от дискретных решений ядра (Д16): строки у порога не судятся (правило ПОРОГ, Р4-16; у книги
    # Совкомбанка 1 367 строк клеток, 9,5 %, и строка-сторож доли), строка «DPS года с жетоном» есть, только когда жетон
    # уплатили обе модели. Заглушка (ядро = контроль) этого не воспроизводит — число строк судится прогоном ядра, как
    # пишет сводку checks_document (судимые строки сверки + строки гейтов и уровней); значения графы — заглушкой
    run, why = tcm._core_grid()
    if run is None:
        pytest.fail(f"число строк сводки сверять не с чем: {why}")
    judged, _ = tcm.reconcile(run, ctl)
    assert len(judged) + (len(rows) - n_stub) == doc["n_rows"], "число строк сверки изменилось"
    mine.update({r["what"]: r for r in judged if r["group"] == "threshold"})   # строки правила ПОРОГ — от прогона ядра
    prefix = "худшая строка: "
    for r in doc["rows"]:
        what = r["what"][len(prefix):] if r["what"].startswith(prefix) else r["what"]
        assert what in mine, f"строки сводки нет у контрольной модели: {what}"
        got, want = mine[what]["control"], r["control"]
        assert (got is None) == (want is None), what
        if want is not None:
            assert abs(got - want) <= max(REGRESSION_ABS, REGRESSION_REL * abs(want)), (what, got, want)
        assert mine[what]["unit"] == r["unit"] and mine[what]["tol_kind"] == r["tol_kind"]


# ============================================================================ числа контрольной модели в документах


CONTROL_DOC = cm.ROOT / "docs" / "CONTROL-MODEL.md"


def _render_tool():
    """Инструмент чисел в документах (ops/tools/render_numbers.py) — модулем, без запуска."""
    name = "tool_render_numbers_control"
    spec = importlib.util.spec_from_file_location(name, cm.ROOT / "ops" / "tools" / "render_numbers.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.tact
def test_document_marks_read_the_reconciliation_summary(tmp_path, capsys):
    """Метка с приставкой `control:` читает сводку сверки data/checks/control_model.json: строка — по её словам,
    графа — число контрольной модели или ядра, счётчики — из корня файла. Результаты книги таким меткам не
    нужны; нет файла сводки, а метка есть, — ошибка метки, как и строка, которой в сводке нет."""
    tool = _render_tool()
    summary = {"n_rows": 10121, "n_bad": 0,                                   # входы теста
               "rows": [{"what": "цена: точка при λ книги", "core": 316.105, "control": 316.717},
                        {"what": "V0 слоя «свой макро-взгляд»", "core": 1020.64, "control": 1022.92}]}
    text = ("Точка <!--=control:rows[what=цена: точка при λ книги].control r2-->0<!--/--> ₽ при "
            "<!--=control:rows[what=цена: точка при λ книги].core r2-->0<!--/--> ₽ у ядра; слой — "
            "<!--=control:rows[what=V0 слоя «свой макро-взгляд»].control r1-->0<!--/-->; строк "
            "<!--=control:n_rows r0-->0<!--/-->." + chr(10))
    new, errors = tool.render(text, None, {"control": summary})
    assert errors == []
    for piece in ("-->316,72<!--/-->", "-->316,11<!--/-->", "-->1 022,9<!--/-->", "-->10 121<!--/-->"):
        assert piece in new, piece
    _, errors = tool.render(text, None, {})
    assert len(errors) == 4 and all("нет файла источника data/checks/control_model.json" in e for e in errors)
    _, errors = tool.render("x <!--=control:rows[what=нет такой строки].control r2-->0<!--/-->" + chr(10), None,
                            {"control": summary})
    assert errors and "строк 0, нужна одна" in errors[0]
    _, errors = tool.render("x <!--=control:нет_ключа r0-->0<!--/-->" + chr(10), None, {"control": summary})
    assert errors and "control_model.json" in errors[0]
    # дерево: документ с метками только на сводку обходится без результатов книги
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "X.md").write_text(text, encoding="utf-8")
    assert tool.main(["--check", "--root", str(root)]) == 1           # файла сводки нет
    (root / "data" / "checks").mkdir(parents=True)
    (root / "data" / "checks" / "control_model.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    assert tool.main(["--check", "--root", str(root)]) == 1 and "устарел: docs/X.md" in capsys.readouterr().err
    assert tool.main(["--root", str(root)]) == 0 and tool.main(["--check", "--root", str(root)]) == 0
    assert "-->316,72<!--/-->" in (root / "docs" / "X.md").read_text(encoding="utf-8")
    # метка на результаты книги рядом — результаты книги нужны
    (root / "docs" / "Y.md").write_text("Медиана <!--=headline.printed_median r0-->1<!--/--> ₽" + chr(10), encoding="utf-8")
    assert tool.main(["--check", "--root", str(root)]) == 1
    assert "docs/Y.md" in capsys.readouterr().err


@pytest.mark.docs
def test_control_document_numbers_are_marks_on_the_summary():
    """docs/CONTROL-MODEL.md: числа контрольной модели на книге стоят метками на сводку сверки и на неё
    разрешаются; меток на результаты книги в документе нет (графа ядра — из той же сводки, один снимок)."""
    if not tcm.CHECKS_JSON.exists():
        pytest.skip("сводки сверки ещё нет (её пишет интеграция)")
    tool = _render_tool()
    text = CONTROL_DOC.read_text(encoding="utf-8")
    specs = [spec for line in text.split(chr(10)) for spec, _ in tool.MARK.findall(tool.CODE.sub("", line))]
    assert len(specs) >= 10 and all(tool.SOURCE.match(spec) for spec in specs), [x for x in specs if not tool.SOURCE.match(x)]
    assert any("цена: точка при λ книги].control" in spec for spec in specs)
    summary = json.loads(tcm.CHECKS_JSON.read_text(encoding="utf-8"))
    _, errors = tool.render(text, None, {"control": summary})
    assert errors == [], errors
