"""Проверки мира уровня ключа цели ЧПМ, окна фактов узла уровней, строк обратного расчёта с уточнением на полной
полосе, справочных вариантов с подписью и отпечатком книги и слов гейтов — на фикстуре `tests/fixtures/core_t`.

Одни и те же проверки зовут тесты (`tests/test_core_t_w6.py`, `tests/test_core2_t_w6.py`) и мутационный набор
(`tests/mutations.py`); каждая — тождество или закрытая формула, выведенная из книги, фактов и рядов клеток
независимо от кода ядра:

* **мир уровня** (М§4.5): при ключе `nii.transmission.level_world` ключ цели ЧПМ — стационарная маржа названного
  мира на составе баланса якоря; книга с ключом уровня и ключом цели, равным стационарной марже этого мира у
  прежней книги, даёт ту же сетку; на оси передачи неподвижен мир уровня; сдвиг ключа цели сдвигает стационарную
  маржу мира уровня ровно на себя;
* **окно фактов** (М§14.5): подузел `window` узла уровней — числа книги и доля кредитов якоря по состоянию якоря;
  в сообщении гейта окна маржа слоя стоит рядом с наибольшим кварталом окна — сведением, не условием;
* **обратный расчёт** (М§11.2, §11.3): список строк с уточнением на полной полосе; элементы премий роста,
  названные книгой фактом, строка «без опережающего роста» не снимает;
* **премия средств клиентов по кварталам** (М§4.3): квартал, заданный в траектории премии ключом квартала или
  полугодия, растёт с премией этого ключа; квартал без такого ключа и траектория без них — с премией года;
* **справочные варианты** (М§14.5): подпись строки, порядок по модулю цены, сверка отпечатка книги;
* **слова**: число и порог гейта стоимости средств — одним числом знаков; маржа якоря в сообщении гейта стыка —
  подписью книги с отчётной величиной; узел выпуска без слоя индикаторов; счётчики сводки контрольной модели.

Ключей этих механик в книге фикстуры нет (нет ключа — прежнее поведение): проверки включают их подменой.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
from typing import Any

from model import book_results as BR
from model import payload as P
from model import reverse as R
from model import uncertainty as U
from model.book import book_from_dict
from model.book_schema import paths_key
from model.checks import check_invariants
from model.grid import derived_values, modal_cell, point_probabilities, run_grid, sensitivity_overrides
from model.levels import (FUNDING_METRICS, LEVEL_ROWS, funding_path, funds_cost_to_key, judged_nim, level_nim, levels,
                          window_facts)
from model.nii import (NIM_KEY, level_for_stationary, level_world, nim_key_for_stationary, nss_value,
                       solve_transmission)
from tests import support_core_t3 as S
from tests import support_core_t4 as S4
from tests import support_core_t5 as S5
from tests.support_core import fixture_run
from tests.support_core2 import TODAY, contract, outputs
from tests.support_core_t import DROP, book_live, put, t_dict, t_facts

close = S.close
gate, refused = S4.gate, S4.refused
with_keys = S5.with_keys

LEVEL = "nii__transmission__level_world"
KEY = "nii__nim_lt_target_mgmt"
T_STAR = "nii__transmission__target"
WINDOW = S5.WINDOW
REFINE, FACTS = "valuation__reverse_dcf__refine_rows", "valuation__reverse_dcf__premium_facts"
VARIANTS = S5.VARIANTS
ANCHOR_LABEL = "meta__labels__gates"
ABSENT_LABEL = "meta__labels__nowcast__absent"
# Окно фактов фикстуры (значения проверки, не книги): наименьший и наибольший квартал по марже, средние, доля
# кредитов окна.
WINDOW_FACTS = {"nim": [0.0921, 0.1034], "means": {"nim": 0.0987, "cor": 0.0512, "cir": 0.471}, "loans_share": 0.612}


def stationary_mgmt(run, world: str) -> float:
    """Стационарная маржа мира на составе якоря при решённых σ0 и φ, упр. базис — прямой счёт стационара."""
    tr = run.ctx.transmission
    return run.ctx.bridge.to_mgmt_nim(nss_value(run.ctx.book, t_facts(), world, 0.0, tr.sigma0, tr.phi, tr.sigma0_liab))


# ------------------------------------------------------------------ мир уровня ключа цели ЧПМ


def check_level_world() -> None:
    """Ключ уровня: ключ цели ЧПМ — стационарная маржа названного мира. Книга с ключом уровня и ключом цели, равным
    стационарной марже этого мира у прежней книги, решается теми же σ0 и φ и даёт ту же сетку; мир уровня, равный
    миру-опоре, — прежнее решение бит в бит; уровень мира-опоры выводится линейно — тем же выводом, что ключ под
    стационар мира; инвариант решения судит мир уровня."""
    facts = t_facts()
    plain = S.grid_of()
    book, br, tr = plain.ctx.book, plain.ctx.bridge, plain.ctx.transmission
    ref = str(book.get("nii.transmission.reference_world"))
    key = float(book.get(NIM_KEY.replace("__", ".")))
    assert level_world(book) is None and tr.level_world == ref and tr.reference_level == tr.target_eng
    assert level_nim(plain.ctx) is None and "level_world" not in derived_values(plain.ctx)["nii"]
    want = {w: stationary_mgmt(plain, w) for w in book.get("worlds.ids")}
    assert close(want[ref], key, abs_=1e-12) and abs(want["M"] - key) > 1e-4 and abs(want["N"] - key) > 1e-4
    # мир уровня — мир-опора: то же решение бит в бит
    same = solve_transmission(S.book_of(**{LEVEL: ref}), facts, br)
    assert (same.sigma0, same.sigma0_liab, same.phi, same.delta0) == (tr.sigma0, tr.sigma0_liab, tr.phi, tr.delta0)
    assert same.level_world == ref and same.reference_level == tr.target_eng
    for world in ("M", "N"):
        keyed = S.book_of(**{LEVEL: world, KEY: want[world]})
        got = solve_transmission(keyed, facts, br)
        assert got.level_world == world and got.reference_world == ref
        assert close(got.target_eng, br.to_engine_nim(want[world]), abs_=1e-15)
        assert close(got.reference_level, tr.target_eng, abs_=1e-12), world       # уровень мира-опоры выведен
        for name in ("sigma0", "sigma0_liab", "phi", "delta0", "t_real"):
            assert close(getattr(got, name), getattr(tr, name), abs_=1e-12), (world, name)
        for w in want:                              # стационарные маржи всех миров — прежние
            assert close(br.to_mgmt_nim(got.nss[w]), want[w], abs_=1e-12), (world, w)
        # вывод ключа под стационар мира и решатель с ключом уровня — одно и то же
        assert close(nim_key_for_stationary(book, facts, br, world, want[world]), key, abs_=1e-12)
        assert close(nim_key_for_stationary(keyed, facts, br, world, want[world] + 0.003), want[world] + 0.003,
                     abs_=1e-12)
    # другая цель: стационар мира уровня равен ключу цели, мир-опора получает выведенный уровень
    goal = want["M"] + 0.004
    moved = S.book_of(**{LEVEL: "M", KEY: goal})
    got = solve_transmission(moved, facts, br)
    direct = br.to_mgmt_nim(nss_value(moved, facts, "M", 0.0, got.sigma0, got.phi, got.sigma0_liab))
    assert close(direct, goal, abs_=1e-12) and close(br.to_mgmt_nim(got.nss["M"]), goal, abs_=1e-12)
    by_key = nim_key_for_stationary(book, facts, br, "M", goal)
    assert close(br.to_mgmt_nim(got.reference_level), by_key, abs_=1e-12) and abs(by_key - goal) > 1e-4
    old = solve_transmission(S.book_of(**{KEY: by_key}), facts, br)
    for name in ("sigma0", "sigma0_liab", "phi"):
        assert close(getattr(got, name), getattr(old, name), abs_=1e-12), name
    assert close(got.t_real, float(book.get("nii.transmission.target")), abs_=1e-12)
    # сетка: книга с ключом уровня и прежним стационаром мира — те же клетки
    grid = S.grid_of(**{LEVEL: "M", KEY: want["M"]})
    for a, b in zip(grid.cells, plain.cells):
        assert close(a.v_ri, b.v_ri, rel=1e-9) and close(a.quarters["nim"][-1], b.quarters["nim"][-1], rel=1e-9), a.label
    assert close(grid.point, plain.point, rel=1e-9)
    solved = next(f for f in check_invariants(grid) if f.name == "transmission_solved")
    assert not solved.fired and "мира M равен цели" in solved.message
    assert f"мира {ref} равен цели" in next(f for f in check_invariants(plain) if f.name == "transmission_solved").message
    # линейный вывод уровня — одна функция: корень линейной функции находится точно, плоская — отказ
    line = lambda x: 0.02 + 0.7 * x  # noqa: E731
    assert close(level_for_stationary(line, 0.1, 0.001, 0.09, "проверка"), 0.1, abs_=1e-12)
    refused(lambda: level_for_stationary(lambda x: 0.05, 0.1, 0.001, 0.09, "проверка"), "не зависит")
    refused(lambda: S.book_of(**{LEVEL: "X"}), "nii.transmission.level_world")


def check_level_world_axes() -> None:
    """Что читает и двигает ключ цели при ключе уровня: на оси передачи неподвижен мир уровня (без ключа — мир-опора);
    сдвиг ключа цели строки чувствительности сдвигает стационарную маржу мира уровня ровно на себя; узел суждения об
    уровне и узел выводимых величин несут мир, стационарную маржу и выведенный уровень мира-опоры."""
    facts = t_facts()
    plain = S.grid_of()
    book, br = plain.ctx.book, plain.ctx.bridge
    ref = str(book.get("nii.transmission.reference_world"))
    world = "M"
    key = stationary_mgmt(plain, world)
    keyed = S.book_of(**{LEVEL: world, KEY: key})
    t_star = float(book.get("nii.transmission.target"))
    base_plain, base_keyed = solve_transmission(book, facts, br), solve_transmission(keyed, facts, br)
    for step in (-0.05, 0.05):
        free = solve_transmission(S.book_of(**{T_STAR: t_star + step}), facts, br)
        held = solve_transmission(S.book_of(**{LEVEL: world, KEY: key, T_STAR: t_star + step}), facts, br)
        assert close(free.nss[ref], base_plain.nss[ref], abs_=1e-12) and abs(free.nss[world] - base_plain.nss[world]) > 1e-4
        assert close(held.nss[world], base_keyed.nss[world], abs_=1e-12) and abs(held.nss[ref] - base_keyed.nss[ref]) > 1e-4
        assert close(held.t_real, t_star + step, abs_=1e-12)
    # строка чувствительности: ключ цели сдвинут на шаг книги — стационарная маржа мира уровня сдвинута на него же
    ov = sensitivity_overrides(keyed, "nim")
    step = float(keyed.get("valuation.sensitivities.nim_pp"))
    assert close(ov[NIM_KEY] - key, step, abs_=1e-15)
    shifted = solve_transmission(keyed.with_overrides(ov), facts, br)
    assert close(shifted.nss[world] - base_keyed.nss[world], step, abs_=1e-12)
    # узлы: суждение об уровне и выводимые величины
    run = S.grid_of(**{LEVEL: world, KEY: key})
    node = level_nim(run.ctx)
    assert node == {"world": world, "value": br.to_mgmt_nim(run.ctx.transmission.nss[world]), "key": key,
                    "reference_world": ref, "reference_value": br.to_mgmt_nim(run.ctx.transmission.reference_level)}
    assert close(node["value"], key, abs_=1e-12) and close(node["reference_value"], float(book.get(NIM_KEY)), abs_=1e-12)
    assert judged_nim(run.ctx) == {"world": world, "value": node["value"]}
    d = derived_values(run.ctx)["nii"]
    assert (d["level_world"], d["reference_world"]) == (world, ref)
    assert close(d["reference_level_mgmt"], node["reference_value"], abs_=1e-15)
    assert close(d["reference_level"], br.to_engine_nim(node["reference_value"]), abs_=1e-12)
    assert close(d["target_eng"], br.to_engine_nim(key), abs_=1e-15)
    # гейт стационарной маржи, пока книга его несёт, сверяет тождество и называет мир уровня ключа
    gated = with_keys(run, **{S5.NIM_ST: {"world": world, "target": key, "tolerance": 0.0005}})
    found = gate(gated, "nim_stationary")
    assert not found.fired and f"(уровень мира {world})" in found.message
    assert judged_nim(gated.ctx)["world"] == world


def check_level_world_row() -> None:
    """Строка обратного расчёта по ключу цели ЧПМ у книги с ключом уровня: стационарная маржа мира уровня на
    книге (при корне — пусто, пока корня нет) — та же величина, что значение книги строки; печатаемой маржи
    модальной клетки у строки нет; у прочих строк и без сетки полей нет."""
    plain = S.grid_of()
    key = stationary_mgmt(plain, "M")
    run = S.grid_of(**{LEVEL: "M", KEY: key})
    rows = R.not_computed(run.ctx.book, "проверка", run=run)["rows"]
    row = next(r for r in rows if R.NIM_PATH in r["paths"])
    assert close(row["stationary_book"], key, abs_=1e-12) and close(row["stationary_book"], row["book"], abs_=1e-12)
    assert row["stationary_solved"] is None and "printed_book" not in row and "levels_solved" not in row
    assert all("stationary_book" not in r for r in rows if R.NIM_PATH not in r["paths"])
    assert all("stationary_book" not in r for r in R.not_computed(run.ctx.book, "проверка")["rows"])
    windowed = with_keys(run, **{WINDOW: S5.FINAL_KEYS["checks.window_backtest"]})
    row = next(r for r in R.not_computed(windowed.ctx.book, "проверка", run=windowed)["rows"] if R.NIM_PATH in r["paths"])
    assert row["levels_solved"] is None and close(row["stationary_book"], key, abs_=1e-12)
    old = next(r for r in R.not_computed(plain.ctx.book, "проверка", run=plain)["rows"] if R.NIM_PATH in r["paths"])
    assert "printed_book" in old and "stationary_book" not in old           # без ключа уровня — прежние поля


# ------------------------------------------------------------------ окно фактов узла уровней


def check_window_node() -> None:
    """Подузел `window` узла уровней: числа окна — поля книги (наименьший и наибольший квартал и среднее по марже,
    стоимости риска и расходам к доходам; доля кредитов окна), доля кредитов якоря — состояние якоря; строк и
    порядка узла подузел не меняет. В сообщении гейта окна маржа слоя стоит рядом с наибольшим кварталом окна —
    сведением: срабатывание гейта от окна маржи не зависит. Без полей окна подузла нет, сообщение прежнее."""
    plain = S.grid_of()
    first = 2030
    base = {"from_year": first, "cor": [0.0, 1.0], "cir": [0.0, 2.0]}
    bare = with_keys(plain, **{WINDOW: base})
    node0 = levels(bare)
    assert "window" not in node0 and window_facts(bare) is None and window_facts(plain) is None
    run = with_keys(plain, **{WINDOW: {**base, **WINDOW_FACTS}})
    node = levels(run)
    assert node["order"] == list(LEVEL_ROWS) and set(node["rows"]) == set(LEVEL_ROWS)
    assert {k: v for k, v in node.items() if k != "window"} == node0
    af = plain.ctx.prep.af
    books = plain.ctx.book.get("nii.books")
    assets = [b for b, spec in books.items() if spec["side"] == "asset"]
    loans = [b for b in assets if not books[b].get("balancing")]
    anchor = sum(af.balances[b] for b in loans) / sum(af.balances[b] for b in assets)
    win = node["window"]
    assert win["nim"] == {"min": 0.0921, "max": 0.1034, "mean": 0.0987}
    assert win["cor"] == {"min": 0.0, "max": 1.0, "mean": 0.0512} and win["cir"] == {"min": 0.0, "max": 2.0, "mean": 0.471}
    assert win["loans_share"]["window"] == 0.612 and close(win["loans_share"]["anchor"], anchor, rel=1e-12)
    first_quarter = plain.cells[0].quarters["loans"][1] / plain.cells[0].quarters["iea"][1]
    assert 0.3 < anchor < 0.95 and abs(anchor - first_quarter) > 1e-4      # якорь — не конец первого квартала сетки
    assert R.levels_brief(node) == R.levels_brief(node0)              # уровни при корне подузла не несут
    # поля окна необязательны поодиночке: чего книга не называет, того в подузле нет числом
    only = levels(with_keys(plain, **{WINDOW: {**base, "nim": WINDOW_FACTS["nim"]}}))["window"]
    assert only["nim"] == {"min": 0.0921, "max": 0.1034, "mean": None} and only["cor"]["mean"] is None
    assert only["loans_share"]["window"] is None and close(only["loans_share"]["anchor"], anchor, rel=1e-12)
    # сообщение гейта: маржа — рядом с наибольшим кварталом окна, и только сведением
    quiet, named = gate(bare, "window_backtest"), gate(run, "window_backtest")
    assert "наибольшем квартале окна" not in quiet.message and "гейтом не сверяется" in quiet.message
    assert "наибольшем квартале окна фактов 10,34 %" in named.message and "гейтом не сверяется" in named.message
    assert named.message.replace("наибольшем квартале окна фактов 10,34 % и ", "") == quiet.message
    assert (named.fired, named.mass, named.detail["outside"]) == (quiet.fired, quiet.mass, quiet.detail["outside"]) == (
        False, 0.0, [])
    # окно маржи целиком ниже и целиком выше маржи слоя: гейт молчит в обоих случаях
    layer = node["rows"]["macro_neutral"]["nim"]
    for low, high in ((round(layer - 0.03, 4), round(layer - 0.01, 4)), (round(layer + 0.01, 4), round(layer + 0.03, 4))):
        found = gate(with_keys(plain, **{WINDOW: {**base, "nim": [low, high]}}), "window_backtest")
        assert not found.fired and found.mass == 0.0 and found.detail["outside"] == []
        assert f"наибольшем квартале окна фактов {100 * high:.2f} %".replace(".", ",") in found.message
    refused(lambda: S.book_of(**{WINDOW: {**base, "nim": [0.11, 0.09]}}), "checks.window_backtest.nim")
    refused(lambda: S.book_of(**{WINDOW: {**base, "means": {"nim": 0.1, "cor": 0.05}}}), "checks.window_backtest.means")
    refused(lambda: S.book_of(**{WINDOW: {**base, "loans_share": 1.2}}), "checks.window_backtest.loans_share")


def check_level_years_and_cost_base() -> None:
    """Участок уровней — только полные годы сетки: первый год не раньше года якоря даёт участок с первого года
    без отчётных кварталов; стоимость риска года смеси — к кредитам по амортизированной стоимости (на фикстуре
    первой формы у неё есть кредиты по справедливой стоимости, и база стоимости риска от всех кредитов отлична)."""
    plain = S.grid_of()
    tl = plain.ctx.timeline
    assert any(q < 1 for q in tl.quarters_of_year(tl.anchor_year))       # год якоря — с отчётными кварталами
    full = list(range(tl.anchor_year + 1, tl.last_year + 1))
    assert levels(plain, tl.anchor_year)["years"] == full == levels(plain, tl.anchor_year + 1)["years"]
    for k in ("nim", "cor", "cir"):
        assert levels(plain, tl.anchor_year)["rows"]["point"][k] == levels(plain, tl.anchor_year + 1)["rows"]["point"][k]
    counted = funds_cost_to_key(with_keys(plain, **{S5.FUNDS: {"max": 1.0, "from_year": tl.anchor_year}}))
    assert counted["from_year"] == tl.anchor_year and counted["to_year"] == tl.last_year
    assert close(counted["by_world"]["M"]["ratio"], S5.funds_ratio(plain, "M", tl.anchor_year + 1), rel=1e-10)
    # стоимость риска года смеси — резервы к кредитам по амортизированной стоимости
    first = fixture_run()
    ftl, br = first.ctx.timeline, first.ctx.bridge
    year = ftl.last_year
    qs = ftl.quarters_of_year(year)
    ends = [qs[0] - 1] + qs
    prob = first.layers["macro_neutral"].prob
    e = lambda name, q: sum(prob[c.key] * c.quarters[name][q] for c in first.cells)  # noqa: E731
    llp = sum(e("llp", q) for q in qs)
    by_ac = br.to_mgmt_cor(llp / (sum(e("loans_ac", q) for q in ends) / 5))
    by_all = br.to_mgmt_cor(llp / (sum(e("loans", q) for q in ends) / 5))
    got = levels(first, year)["rows"]["macro_neutral"]["cor"]
    assert close(got, by_ac, rel=1e-10) and abs(by_ac - by_all) > 1e-5


# ------------------------------------------------------------------ обратный расчёт


def check_refine_rows() -> None:
    """Список строк обратного расчёта с уточнением на полной полосе: без ключа — любая строка (образец); с ключом —
    только названные; ключ, которого нет среди строк книги, и повтор — отказ; ключи строк — ключи осей."""
    plain = S.book_of()
    axes = plain.get("valuation.reverse_dcf.axes")
    keys = [U.axis_key(ax) for ax in axes]
    assert keys == [paths_key(ax["paths"]) for ax in axes] and len(keys) >= 3
    assert paths_key(["a.b"]) == "a.b" and paths_key(["a.x.c", "a.y.c"]) == "a.*.c" and paths_key(["a.b", "a.b.c"]) == "a.b+"
    assert R.refine_rows(plain) is None
    assert R.refines_on_full_band(None, keys[0]) and R.refines_on_full_band(None, "нет такой")
    named = S.book_of(**{REFINE: [keys[1], keys[0]]})
    chosen = R.refine_rows(named)
    assert chosen == frozenset(keys[:2])
    assert R.refines_on_full_band(chosen, keys[0]) and R.refines_on_full_band(chosen, keys[1])
    assert not R.refines_on_full_band(chosen, keys[2])
    assert R.refine_rows(S.book_of(**{REFINE: []})) == frozenset()
    assert not R.refines_on_full_band(frozenset(), keys[0])
    refused(lambda: S.book_of(**{REFINE: ["no.such.row"]}), "valuation.reverse_dcf.refine_rows", "no.such.row")
    refused(lambda: S.book_of(**{REFINE: [keys[0], keys[0]]}), "повтор ключа строки")


def check_refine_rows_run() -> None:
    """Обратный расчёт на двух строках с решениями внутри диапазона: без ключа обе уточняются на полной полосе; с
    ключом — только названная, вторая несёт корень подвыборки (`gap_basis: subsample`) и пометку «в диапазоне» по
    нему; узел называет список строк, слова метода — правило; полных сеток на уточнение уходит меньше. Книга
    проверки несёт ключ уровня: стационарная маржа мира уровня у строки ключа цели при корне равна самому корню,
    на книге — значению книги; рядом — уровни после фазы роста при корне."""
    keys = {**S4.SMALL_BAND, LEVEL: "M", KEY: stationary_mgmt(S.grid_of(), "M"),
            WINDOW: S5.FINAL_KEYS["checks.window_backtest"]}
    base = S.book_of(**keys)
    facts = t_facts()
    live0 = book_live(base)
    nim = next(a for a in base.get("valuation.reverse_dcf.axes") if R.NIM_PATH in a["paths"])
    erp = next(a for a in base.get("valuation.reverse_dcf.axes") if "valuation.erp" in a["paths"])
    b_nim, b_erp = float(base.get(R.NIM_PATH)), float(base.get("valuation.erp"))
    axes = [{**nim, "search": [b_nim - 0.02, b_nim + 0.03], "range": [b_nim - 0.02, b_nim + 0.03]},
            {**erp, "search": [0.02, 0.25], "range": [0.02, 0.25]}]
    rows_key = [U.axis_key(a) for a in axes]

    def setup(price: float | None = None, **more: Any):
        book = S.book_of(**keys, **more, **{"valuation__reverse_dcf__axes": axes, "valuation__reverse_dcf__bank_rows": []})
        live = live0 if price is None else dataclasses.replace(live0, prices={t: price for t in live0.prices})
        band = U.band(book, facts, live, draws=4, workers=1)
        return book, live, band, U.MedianAnchor(book, facts, live, band, base=band)

    book, _, _, anchor = setup()
    price = anchor.at(R.reverse_trial(book, book.get("valuation.reverse_dcf.axes")[0], b_nim + 0.006, follow=True))["central"]

    def solve(**more: Any) -> dict:
        bk, live, band, anc = setup(price, **more)
        return R.reverse_dcf(bk, facts, live, band, anchor=anc)

    every = solve()
    assert "refine_rows" not in every and "названные книгой" not in every["method"]
    assert [r["gap_basis"] for r in every["rows"]] == ["full", "full"] and all(r["in_range"] for r in every["rows"])
    one = solve(**{REFINE: [rows_key[0]]})
    first, second = one["rows"]
    assert one["refine_rows"] == [rows_key[0]] and "названные книгой (1 из 2)" in one["method"]
    assert first["gap_basis"] == "full" and second["gap_basis"] == "subsample"
    assert second["status"] == "solved" and second["in_range"] is True and second["converged"] is True
    assert close(first["solved"], every["rows"][0]["solved"], abs_=1e-9)
    assert abs(second["solved"] - b_erp) > 1e-4 and close(second["solved"], every["rows"][1]["solved"], abs_=5e-3)
    assert 0 < one["full_grids"] < every["full_grids"]
    # строка ключа цели читает ключ как уровень мира уровня: суждение при корне — сам корень
    assert close(first["stationary_book"], b_nim, abs_=1e-12) and close(first["stationary_solved"], first["solved"], abs_=1e-9)
    assert abs(first["stationary_solved"] - b_nim) > 1e-3 and "printed_solved" not in first
    assert set(first["levels_solved"]) == set(LEVEL_ROWS) and "stationary_book" not in second
    none = solve(**{REFINE: []})
    assert none["refine_rows"] == [] and [r["gap_basis"] for r in none["rows"]] == ["subsample", "subsample"]
    assert none["full_grids"] == 0 and "(0 из 2)" in none["method"]
    text = BR.render_run_output({**_tables_stub(), "reverse_dcf": one}, book)
    assert text.count("оценка по подвыборке") == 1


def _tables_stub() -> dict:
    """Наименьшие таблицы книги для печати сводки: быстрые таблицы фикстуры (обратного расчёта в них нет)."""
    return dict(_fast_tables())


@functools.lru_cache(maxsize=None)
def _fast_tables() -> dict:
    import json
    res = BR.book_results(S.book_of(), t_facts(), slow=False)
    return json.loads(json.dumps(res, default=BR._default))


def check_premium_facts() -> None:
    """Строка «без опережающего роста»: без ключа премии роста снимаются целиком; элемент траектории премии,
    названный книгой фактом, остаётся как в книге — остальные ключи той же траектории и прочие траектории
    обнуляются; путь вне траекторий премий, `LT_from` и несуществующий элемент — отказ."""
    plain = S.book_of()
    fact = "volumes.funds_share_drift.retail.2026"
    was = float(plain.get(fact))
    assert was != 0.0 and R.premium_facts(plain) == frozenset()
    every = R.no_premium_overrides(plain)
    assert every["volumes.funds_share_drift.retail"]["2026"] == 0.0
    keyed = S.book_of(**{FACTS: [fact]})
    assert R.premium_facts(keyed) == frozenset([fact])
    kept = R.no_premium_overrides(keyed)
    assert kept["volumes.funds_share_drift.retail"]["2026"] == was
    assert set(kept) == set(every)
    for path, traj in kept.items():
        for k, v in traj.items():
            if (path, k) == ("volumes.funds_share_drift.retail", "2026"):
                continue
            assert v == every[path][k] and (v == 0.0 or k == "LT_from"), (path, k)
    assert kept["volumes.funds_share_drift.corporate"]["2026"] == 0.0 and kept["volumes.loan_share_drift.corporate"]["2026"] == 0.0
    assert keyed.with_overrides(kept).get(fact) == was                # книга с подменой проходит схему
    refused(lambda: S.book_of(**{FACTS: ["credit.kappa"]}), "valuation.reverse_dcf.premium_facts")
    refused(lambda: S.book_of(**{FACTS: ["volumes.funds_share_drift.retail.LT_from"]}), "premium_facts")
    refused(lambda: S.book_of(**{FACTS: ["volumes.funds_share_drift.retail.2099"]}), "premium_facts")
    refused(lambda: S.book_of(**{FACTS: ["volumes.funds_share_drift.retail"]}), "premium_facts")


def check_premium_facts_row() -> None:
    """Банковская строка «стоимость без опережающего роста» на книге с названным фактом: точка книги, в которой
    сняты премии роста, кроме факта, — и она отлична от точки со снятым фактом."""
    fact = "volumes.funds_share_drift.retail.2026"
    facts = t_facts()
    keyed = S.book_of(**{FACTS: [fact], "valuation__reverse_dcf__bank_rows": ["value_without_excess_growth"]})
    run = run_grid(keyed, facts, book_live(keyed))
    row = R.bank_rows(keyed, facts, run.ctx.live, run, {}, follow=True)[0]
    zero = {"2026": 0.0, "2027": 0.0, "LT": 0.0, "LT_from": 2032}
    manual = {f"volumes__loan_share_drift__{s}": zero for s in ("corporate", "mortgage", "retail_other")}
    manual["volumes__funds_share_drift__corporate"] = zero
    manual["volumes__funds_share_drift__retail"] = {**zero, "2026": float(keyed.get(fact))}
    want = S.grid_of(**manual).point
    every = S.grid_of(**{**manual, "volumes__funds_share_drift__retail": zero}).point
    assert close(row["implied"], want, rel=1e-9) and abs(want - every) > 0.05
    assert close(row["delta"], want - run.point, abs_=1e-9)


# ------------------------------------------------------------------ премия роста средств клиентов по кварталам (М§4.3)


def check_funds_premium_by_quarter() -> None:
    """Премия роста средств клиентов, заданная ключом квартала или полугодия: средства сегмента за квартал растут
    множителем ((1 + рост сектора мира в году) × (1 + премия квартала))^(1/4), где премия квартала — значение его
    ключа квартала (затем ключа полугодия), а у квартала без такого ключа — значение года траектории. Траектория с
    одними ключами лет читается по годам, как раньше; другой сегмент и кварталы после года конца премии ключ не
    задевает."""
    from model.paths import Trajectory

    plain = S.grid_of()
    book, tl = plain.ctx.book, plain.ctx.timeline
    assert plain.ctx.prep.funds_drift_q == {}                         # ключей кварталов нет — таблицы кварталов нет
    base = dict(book.source["volumes"]["funds_share_drift"]["retail"])
    until = int(book.get("volumes.share_drift_until"))
    q1, q2 = tl.period(1), tl.period(2)
    year_of = lambda q: int(tl.period(q)[:4])  # noqa: E731
    a, b, late = -0.20, 0.03, 0.11
    late_q = f"{until + 1}Q2"
    cases = {"первый квартал": {q1: a, **base},
             "два квартала без ключа года": {q1: a, q2: b, **{k: v for k, v in base.items() if k != str(year_of(1))}},
             "полугодие": {f"{year_of(1)}H{1 if int(q1[5]) <= 2 else 2}": a, **base},
             "квартал после года конца премии": {late_q: late, **base}}
    for title, traj in cases.items():
        run = S.grid_of(volumes__funds_share_drift__retail=traj)
        t = Trajectory(traj)
        halves = {f"{y}H{h}" for y, h in t.halves}
        for key in (("N", "norm", "schedule"), ("M", "crisis", "strict")):
            c, c0 = run.cell(*key), plain.cell(*key)
            world = run.ctx.worlds[key[0]]
            funds = c.quarters["funds_retail"]
            for q in range(1, min(tl.Q, tl.index(late_q) + 1 if title.startswith("квартал после") else 6) + 1):
                per, y = tl.period(q), year_of(q)
                keyed = per in traj or f"{y}H{1 if int(per[5]) <= 2 else 2}" in halves
                premium = (t.value(y, int(per[5])) if keyed else t.year_value(y)) if y <= until else 0.0
                want = ((1 + world.funds_growth["retail"][y]) * (1 + premium)) ** 0.25
                assert close(funds[q] / funds[q - 1], want, rel=1e-12), (title, key, per)
            corp, corp0 = c.books["corp_funds"]["balance"], c0.books["corp_funds"]["balance"]
            assert all(close(corp[q] / corp[q - 1], corp0[q] / corp0[q - 1], rel=1e-12) for q in (1, 2, 3)), (title, key)
    # ключ квартала сильнее ключа полугодия, ключ полугодия — сильнее ключа года
    half = f"{year_of(1)}H{1 if int(q1[5]) <= 2 else 2}"
    run = S.grid_of(volumes__funds_share_drift__retail={q1: a, half: b, **base})
    c = run.cell("H", "norm", "mid")
    growth = run.ctx.worlds["H"].funds_growth["retail"][year_of(1)]
    funds = c.quarters["funds_retail"]
    assert close(funds[1] / funds[0], ((1 + growth) * (1 + a)) ** 0.25, rel=1e-12)
    if year_of(2) == year_of(1) and (int(q2[5]) <= 2) == (int(q1[5]) <= 2):
        assert close(funds[2] / funds[1], ((1 + growth) * (1 + b)) ** 0.25, rel=1e-12)


# ------------------------------------------------------------------ справочные варианты


NOTED = [{**S5.VARIANT_LIST[0]}, {**S5.VARIANT_LIST[1], "note": "Клетка варианта печатает уровень окна во всех мирах"},
         {**S5.VARIANT_LIST[2]}]


def variants_tables(book, d_points=(1.5, -40.0, 7.25)) -> dict:
    """Таблицы книги со справочными вариантами в порядке списка книги и её отпечатком."""
    rows = [{"id": v["id"], "title": "старое название", "point": 400.0 + d, "d_point": d,
             **({"note": "старая подпись"} if "note" in v else {})}
            for v, d in zip(book.opt("valuation.reference_variants") or [], d_points)]
    return {"book_version": str(book.get("meta.version")), "headline": {"point": 400.0}, "reference_variants": rows,
            BR.VARIANTS_BOOK: book.digest}


def check_variants_note_and_order() -> None:
    """Справочные варианты: строка таблиц несёт подпись книги, только когда она есть; таблицы — в порядке списка
    книги; выпуск и сводка печатают строки по убыванию модуля цены правила, подпись и название — книги."""
    facts = t_facts()
    plain = S.grid_of(**{S5.FADE: 0.5})
    short = S.book_of(**{S5.FADE: 0.5, VARIANTS: NOTED[:2]})
    rows = BR.reference_variants(short, facts, plain.ctx.live, plain)
    assert [r["id"] for r in rows] == [v["id"] for v in NOTED[:2]]
    assert [r.get("note") for r in rows] == [None, NOTED[1]["note"]] and "note" not in rows[0]
    book = S.book_of(**{S5.FADE: 0.5, VARIANTS: NOTED})
    ranked = BR.by_price([{"id": "a", "d_point": 1.5}, {"id": "b", "d_point": -40.0}, {"id": "c", "d_point": 7.25},
                          {"id": "d", "d_point": -7.25}])
    assert [r["id"] for r in ranked] == ["b", "c", "d", "a"]
    table = variants_tables(book)
    node, why = P.reference_variants_state(book, table)
    assert why is None and node["point"] == 400.0
    assert [r["id"] for r in node["rows"]] == [NOTED[1]["id"], NOTED[2]["id"], NOTED[0]["id"]]
    assert [r["d_point"] for r in node["rows"]] == [-40.0, 7.25, 1.5]
    assert [r["title"] for r in node["rows"]] == [NOTED[1]["title"], NOTED[2]["title"], NOTED[0]["title"]]
    assert node["rows"][0]["note"] == NOTED[1]["note"] and all("note" not in r for r in node["rows"][1:])
    assert P.reference_variants_table(book, table) == node
    refused(lambda: S.book_of(**{VARIANTS: [{**S5.VARIANT_LIST[0], "note": ""}]}), "note")


def check_variants_fingerprint() -> None:
    """Выпуск берёт справочные варианты только из таблиц, посчитанных на этой же книге: при другом отпечатке книги
    (подмена варианта сменилась без пересборки таблиц), без отпечатка, при другой версии и другом списке узла нет,
    а причина названа словами. Нет списка в книге — ни узла, ни причины."""
    book = S.book_of(**{VARIANTS: NOTED})
    table = variants_tables(book)
    assert P.reference_variants_state(book, table)[1] is None
    changed = [dict(v) for v in NOTED]
    changed[1] = {**changed[1], "overrides": {"credit.kappa": 0.3}}          # тот же идентификатор, другая подмена
    other = S.book_of(**{VARIANTS: changed})
    assert other.digest != book.digest and other.get("meta.version") == book.get("meta.version")
    node, why = P.reference_variants_state(other, table)
    assert node is None and "отпечаток книги не совпал" in why
    assert P.reference_variants_table(other, table) is None
    node, why = P.reference_variants_state(book, {k: v for k, v in table.items() if k != BR.VARIANTS_BOOK})
    assert node is None and "отпечаток" in why
    assert "другой версии" in P.reference_variants_state(book, {**table, "book_version": "другая"})[1]
    assert "не по списку" in P.reference_variants_state(book, {**table, "reference_variants": table["reference_variants"][::-1]})[1]
    assert "не по списку" in P.reference_variants_state(book, {k: v for k, v in table.items() if k != "headline"})[1]
    assert P.reference_variants_state(S.book_of(), table) == (None, None)


def check_tables_fingerprint() -> None:
    """Таблицы книги несут отпечаток книги рядом со справочными вариантами — и только с ними."""
    plain = _fast_tables()
    assert BR.VARIANTS_BOOK not in plain and "reference_variants" not in plain
    book = S.book_of(**{VARIANTS: NOTED})
    live = book_live(book)
    run = run_grid(book, t_facts(), live)
    rows = BR.reference_variants(book, t_facts(), live, run)
    table = {"book_version": str(book.get("meta.version")), "headline": {"point": run.point}, "reference_variants": rows,
             BR.VARIANTS_BOOK: book.digest}
    node, why = P.reference_variants_state(book, table)
    assert why is None and [abs(r["d_point"]) for r in node["rows"]] == sorted((abs(r["d_point"]) for r in node["rows"]),
                                                                              reverse=True)


# ------------------------------------------------------------------ слова гейтов


def check_funds_cost_digits() -> None:
    """Сообщение гейта стоимости средств клиентов печатает отношения миров и порог одним числом знаков — тремя:
    запас до порога читается из сообщения."""
    plain = S.grid_of()
    first = 2030
    want = {w: S5.funds_ratio(plain, w, first) for w in plain.ctx.book.get("worlds.ids")}
    top = max(want.values())
    limit = round(top + 0.0055, 4)
    found = gate(with_keys(plain, **{S5.FUNDS: {"max": limit, "from_year": first}}), "funds_cost_to_key")
    assert not found.fired
    assert f"при пороге {limit:.3f}".replace(".", ",") in found.message
    for w, v in want.items():
        assert f"{v:.3f}".replace(".", ",") in found.message, w
    assert f"{top:.3f}" != f"{limit:.3f}"                             # число и порог различимы в сообщении


def check_anchor_margin_words() -> None:
    """Маржа якоря в сообщении гейта стыка ближнего пути: без подписи книги — прежние слова; с подписью — маржа по
    книгам ядра через мост (с ней сравнивает гейт) и отчётная упр. маржа квартала якоря из фактов; срабатывание,
    масса и порог от подписи не зависят."""
    plain = S.grid_of()
    facts, br = t_facts(), plain.ctx.bridge
    old = gate(plain, "nim_path_joint")
    by_books = br.to_mgmt_nim(facts.need("nii_books", "nim_eng_q"))
    reported = facts.v("mgmt_quarterly", f"quarters.{plain.ctx.timeline.anchor}.nim")
    assert reported is not None and abs(reported - by_books) > 1e-5
    pct = lambda x, n=2: f"{100 * x:.{n}f}".replace(".", ",") + " %"  # noqa: E731
    assert f"из ЧПМ якоря ({pct(by_books)}) и ЧПМ" in old.message
    label = {"nim_anchor": "ЧПМ якоря по книгам ядра через мост ({value}; отчётная — {reported})"}
    run = S.grid_of(**{ANCHOR_LABEL: label})
    new = gate(run, "nim_path_joint")
    words = f"ЧПМ якоря по книгам ядра через мост ({pct(by_books)}; отчётная — {pct(reported, 1)})"
    assert f"из {words} и ЧПМ" in new.message
    assert new.message.replace(words, f"ЧПМ якоря ({pct(by_books)})") == old.message
    assert (new.fired, new.mass, new.cells, new.detail) == (old.fired, old.mass, old.cells, old.detail)
    refused(lambda: S.book_of(**{ANCHOR_LABEL: {"nim_anchor": "ЧПМ якоря ({fact})"}}), "meta.labels.gates.nim_anchor")


def check_control_summary_counts() -> None:
    """Сводка сверки с контрольной моделью в выпуске: счётчики отвечают строкам — сверенных строк не меньше
    показанных, вне допуска не меньше показанных вне допуска, «всё в допуске» — только без строк вне допуска;
    дата, на которой стоят числа сводки, — дата."""
    row = {"what": "строка", "unit": "bn", "core": 1.0, "control": 1.0, "diff": 0.0, "diff_rel": 0.0, "tol": 0.01,
           "tol_kind": "rel", "ok": True}
    good = {"as_of": "2026-10-02", "commit": None, "book_version": "1.0", "all_ok": True, "n_rows": 5200, "n_bad": 0,
            "valuation_date": "2026-10-01", "rows": [row, dict(row)]}
    problems = P._control_summary_problems
    assert problems(good) == [] and problems(None) == [] and problems({"as_of": "2026-10-02", "commit": None, "rows": [row]}) == []
    assert any("n_rows" in x for x in problems({**good, "n_rows": 1}))
    bad_row = {**row, "ok": False}
    assert problems({**good, "all_ok": False, "n_bad": 3, "rows": [row, bad_row]}) == []
    assert any("n_bad" in x for x in problems({**good, "all_ok": False, "n_bad": 0, "rows": [row, bad_row]}))
    assert any("all_ok" in x for x in problems({**good, "n_bad": 2}))
    assert any("n_bad" in x for x in problems({**good, "all_ok": False, "n_bad": 6000}))
    assert any("valuation_date" in x for x in problems({**good, "valuation_date": "вчера"}))


def check_release_words() -> None:
    """Слова сборки (чистые функции): замечание о справочных вариантах, которых выпуск не взял, — причина и что
    сделать, без причины замечания нет; слова выпуска без слоя индикаторов — подпись книги, только когда выходов
    слоя индикаторов у сборки нет."""
    assert P.variants_remark(None) == []
    remark = P.variants_remark("таблицы книги посчитаны на другой книге")
    assert len(remark) == 1 and "справочные варианты в выпуск не взяты: таблицы книги посчитаны на другой книге" in remark[0]
    assert "model.book_results" in remark[0]
    words = "Выпуск собран без слоя индикаторов: блока нет"
    labelled, bare = S.book_of(**{ABSENT_LABEL: words}), S.book_of()
    assert P.absent_words(labelled, None) == words and P.absent_words(bare, None) is None
    assert P.absent_words(labelled, object()) is None and P.absent_words(bare, object()) is None


# ------------------------------------------------------------------ узлы выпуска


def level_keys(**extra: Any) -> dict[str, Any]:
    """Ключи панели фикстуры без гейта стационарной маржи и с ключом уровня: ключ цели — стационарная маржа мира M."""
    plain = S.grid_of(**{S5.KAPPA_WORLD: "M"})
    keys = {k: v for k, v in S5.keyed().items() if k != S5.NIM_ST}
    keys[WINDOW] = {**S5.FINAL_KEYS["checks.window_backtest"], **WINDOW_FACTS}
    keys[VARIANTS] = NOTED
    return {**keys, LEVEL: "M", KEY: stationary_mgmt(plain, "M"), **extra}


def release_of(book, *, out=None, results=None):
    from model.checks import check_gates
    from model.live import apply_live
    from tests.support_core2 import CONTROL_FIXTURE, explained
    facts = t_facts()
    results = variants_tables(book) if results is None else results
    if out is None:
        expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
        rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                             draws=4, control_model=CONTROL_FIXTURE, results=results)
    else:
        live, _ = apply_live(book, facts, out, today=TODAY, previous={})
        expl = explained(check_gates(run_grid(book, facts, live), today=TODAY), today=TODAY)
        rel = P.make_release(live=True, fast=True, today=TODAY, book=book, facts=facts, outputs=out, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE, results=results)
    return rel, P.build_payload(rel)


@functools.lru_cache(maxsize=None)
def level_release():
    """Быстрый выпуск фикстуры с ключом уровня, окном фактов, вариантами с подписью и подписью выпуска без слоя
    индикаторов."""
    return release_of(S.book_of(**level_keys(**{ABSENT_LABEL: "Выпуск собран без слоя индикаторов: блока нет"})))


def check_release_level_nodes() -> None:
    """Узлы выпуска: суждение об уровне маржи рядом с ключом цели (мир, стационарная маржа, выведенный уровень
    мира-опоры), та же маржа у строки обратного расчёта по ключу цели, подпись строки чувствительности называет
    мир; окно фактов — подузлом узла уровней; варианты — по модулю цены, с подписью; контракт выполнен."""
    rel, d = level_release()
    assert S5.unknown(contract(d)) == []
    tr = d["nii"]["transmission"]
    node = level_nim(rel.run.ctx)
    assert tr["level"] == {"world": "M", "value": S5.approx(node["value"], abs=5.1e-7), "reference_world": node["reference_world"],
                           "reference_value": S5.approx(node["reference_value"], abs=5.1e-7)}
    assert "nim_stationary" not in tr and tr["nim_lt_target_mgmt"] == S5.approx(tr["level"]["value"], abs=1e-6)
    assert abs(tr["level"]["reference_value"] - tr["level"]["value"]) > 1e-4
    row = next(r for r in d["reverse_dcf"]["rows"] if R.NIM_PATH in r["paths"])
    assert row["stationary_book"] == S5.approx(row["book"], abs=1e-9) and row["stationary_solved"] is None
    assert row["levels_solved"] is None and "printed_book" not in row
    basis = d["fair_value"]["bank_first_line"]["sensitivity_basis"]
    assert "стационарная маржа мира M на составе баланса якоря — сдвинут" in basis
    win = d["paths"]["levels"]["window"]
    want = window_facts(rel.run)
    assert win["nim"] == {"min": 0.0921, "max": 0.1034, "mean": 0.0987} and win["loans_share"]["window"] == 0.612
    assert win["loans_share"]["anchor"] == S5.approx(want["loans_share"]["anchor"], abs=5.1e-7)
    assert d["paths"]["levels"]["order"] == list(LEVEL_ROWS) and set(d["paths"]["levels"]["rows"]) == set(LEVEL_ROWS)
    variants = d["book"]["reference_variants"]["rows"]
    assert [r["d_point"] for r in variants] == [-40.0, 7.25, 1.5] and variants[0]["note"] == NOTED[1]["note"]
    assert rel.remarks == []
    message = next(g for g in d["checks"]["gates"] if g["name"] == "window_backtest")["message"]
    assert "наибольшем квартале окна фактов 10,34 %" in message
    # без ключей — узлов нет
    _, plain = S5.keyed_release()
    assert "level" not in plain["nii"]["transmission"] and "window" not in plain["paths"]["levels"]
    assert "absent" not in plain["nowcast"] and "refine_rows" not in plain["reverse_dcf"]


def check_funding_path() -> None:
    """Путь фондирования (ключ коридора гейта доли оптового фондирования): кредиты к средствам клиентов и доля
    оптового фондирования на дату якоря и на конец каждого года сетки. Смесь — отношение ожидаемых остатков под
    вероятностями точки, модальная клетка — её собственные остатки; доля оптового фондирования — определение
    гейта `wholesale_share`. Без ключа узла нет."""
    run = S.grid_of()
    node = funding_path(run)
    ctx = run.ctx
    tl = ctx.timeline
    years = list(range(tl.anchor_year, tl.last_year + 1))
    ends = [tl.quarters_of_year(y)[-1] for y in years]
    prob = point_probabilities(run)
    c = run.cell(*modal_cell(ctx.book, ctx.posterior))
    assert set(node) == {"years", "cell", "anchor", "mix", "modal_cell"}
    assert node["years"] == years and node["cell"] == c.label and len(ends) > 5
    mean = lambda name, q: sum(prob[x.key] * float(x.quarters[name][q]) for x in run.cells)  # noqa: E731
    row = lambda name, q: float(c.quarters[name][q])  # noqa: E731
    for part, at in (("mix", mean), ("modal_cell", row)):
        assert set(node[part]) == set(FUNDING_METRICS)
        for i, q in enumerate(ends):
            loans, funds, wholesale = at("loans", q), at("funds", q), at("wholesale", q)
            assert close(node[part]["loans_to_funds"][i], loans / funds, rel=1e-12), (part, i)
            assert close(node[part]["wholesale_share"][i], wholesale / (funds + wholesale), rel=1e-12), (part, i)
    last = ends[-1]
    # смесь — под вероятностями точки (не слоя) и отношением ожиданий, а не ожиданием отношений клеток
    layer = run.layers["analytical"].prob
    by_layer = (sum(layer[x.key] * float(x.quarters["loans"][last]) for x in run.cells)
                / sum(layer[x.key] * float(x.quarters["funds"][last]) for x in run.cells))
    of_ratios = sum(prob[x.key] * float(x.quarters["loans"][last]) / float(x.quarters["funds"][last]) for x in run.cells)
    got = node["mix"]["loans_to_funds"][-1]
    assert abs(got - by_layer) > 1e-9 and abs(got - of_ratios) > 1e-9
    assert abs(got - node["modal_cell"]["loans_to_funds"][-1]) > 1e-9
    # доля оптового фондирования — к сумме средств клиентов и оптового фондирования, как у гейта
    assert abs(node["modal_cell"]["wholesale_share"][-1] - row("wholesale", last) / row("funds", last)) > 1e-6
    lo, hi = (float(v) for v in ctx.book.get("checks.wholesale_share"))
    assert not gate(run, "wholesale_share").fired
    assert all(lo <= v <= hi for part in ("mix", "modal_cell") for v in node[part]["wholesale_share"])
    # якорь — состояние на дату якоря, общее для клеток, а не конец первого квартала сетки и не конец года якоря
    assert close(node["anchor"]["loans_to_funds"], row("loans", 0) / row("funds", 0), rel=1e-12)
    assert close(node["anchor"]["wholesale_share"], row("wholesale", 0) / (row("funds", 0) + row("wholesale", 0)), rel=1e-12)
    assert abs(node["anchor"]["loans_to_funds"] - row("loans", 1) / row("funds", 1)) > 1e-9
    assert all(close(float(x.quarters["loans"][0]), row("loans", 0), rel=1e-12) for x in run.cells)
    # без ключа коридора узла нет
    assert fixture_run().ctx.book.opt("checks.wholesale_share") is None and funding_path(fixture_run()) is None


def check_release_funding_and_names() -> None:
    """Узлы выпуска: путь фондирования (`paths.funding`) — числа ядра с хранимой точностью; мир, в котором стоят
    пути CoR режимов (`regimes.reference_world`), — при ключе мира-опоры κ-добавки; заголовок инварианта передачи
    у книги с миром уровня называет этот мир. Без ключей узлов нет, заголовок прежний."""
    rel, d = level_release()
    assert S5.unknown(contract(d)) == []
    want, got = funding_path(rel.run), d["paths"]["funding"]
    assert set(got) == {"years", "cell", "anchor", "mix", "modal_cell"}
    assert (got["years"], got["cell"]) == (want["years"], want["cell"]) and got["cell"] == d["paths"]["modal_cell"]["cell"]
    for k in FUNDING_METRICS:
        assert got["anchor"][k] == S5.approx(want["anchor"][k], abs=5.1e-7)
        for part in ("mix", "modal_cell"):
            assert got[part][k] == [S5.approx(v, abs=5.1e-7) for v in want[part][k]] and len(got[part][k]) == len(got["years"])
    ends = [a["loans_end"] / a["funds_end"] for a in d["paths"]["annual"]]
    assert got["mix"]["loans_to_funds"] == [S5.approx(v, abs=2e-4) for v in ends]      # те же остатки, что в годовом пути
    assert d["regimes"]["reference_world"] == "M" == rel.book.get("credit.kappa_reference_world")
    title = {i["name"]: i["title"] for i in d["checks"]["invariants"]}["transmission_solved"]
    lt_level = rel.book.label("terms.lt_level")
    assert title == f"Передача ставки решена: ЧПМ {lt_level} мира M и реализованная передача равны книге"
    assert title != P.INVARIANT_TITLES["transmission_solved"] and "мире H" not in title
    # без ключа мира уровня заголовок прежний; без мира-опоры κ узла нет; без коридора гейта нет пути фондирования
    _, keyed = S5.keyed_release()
    assert {i["name"]: i["title"] for i in keyed["checks"]["invariants"]}["transmission_solved"] == P.INVARIANT_TITLES[
        "transmission_solved"]
    data = t_dict()
    put(data, "checks.wholesale_share", DROP)
    _, bare = S5.release_of(book_from_dict(data, facts=t_facts()))
    assert "funding" not in bare["paths"] and "reference_world" not in bare["regimes"]
    assert S5.unknown(contract(bare)) == []


def check_release_without_indicators() -> None:
    """Выпуск, собранный без слоя индикаторов, называет это узлом `nowcast.absent` — словами подписи книги; без
    подписи узла нет; у выпуска со слоем индикаторов узла нет и при подписи."""
    _, d = level_release()
    assert d["nowcast"]["absent"] == "Выпуск собран без слоя индикаторов: блока нет"
    assert d["nowcast"]["admission"]["events_needed"] is None and d["nowcast"]["retro"]["periods"] == []
    book = S.book_of(**{ABSENT_LABEL: "Выпуск собран без слоя индикаторов: блока нет"})
    px = {t: float(v) for t, v in book.get("meta.market_price").items()}
    out = outputs({t: [(TODAY, px[t])] for t in px}, register=[])
    _, live = release_of(book, out=out)
    assert "absent" not in live["nowcast"]
    _, bare = release_of(S.book_of())
    assert "absent" not in bare["nowcast"]


def check_release_stale_variants() -> None:
    """Таблицы книги, посчитанные на другой книге: выпуск справочных вариантов не несёт, а сборка называет это
    замечанием — не отказом и не тревогой."""
    book = S.book_of(**{VARIANTS: NOTED})
    stale = {**variants_tables(book), BR.VARIANTS_BOOK: "0" * 64}
    rel, d = release_of(book, results=stale)
    assert "reference_variants" not in d["book"] and len(rel.remarks) == 1
    assert "справочные варианты в выпуск не взяты" in rel.remarks[0] and "отпечаток книги не совпал" in rel.remarks[0]
    assert P.alerts(rel, d) == [] or all("вариант" not in a for a in P.alerts(rel, d))
    fresh, d2 = release_of(book)
    assert fresh.remarks == [] and len(d2["book"]["reference_variants"]["rows"]) == len(NOTED)
    broken = copy.deepcopy(d2)
    broken["checks"]["control_model"] = {**(broken["checks"]["control_model"] or {"as_of": "2026-10-02", "commit": None,
                                                                                   "rows": []}), "n_rows": -1}
    assert any("checks.control_model.n_rows" in x for x in P._check_problems(broken))
