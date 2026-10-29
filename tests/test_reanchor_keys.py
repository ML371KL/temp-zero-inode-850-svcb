# -*- coding: utf-8 -*-
"""Перезаякоривание и ключи книги второй формы (`ops/tools/reanchor.py`, М§15.2): что инструмент делает с книгой,
которая несёт ось-связку, мир-опору κ-добавки, гейты целей-суждений, справочные варианты и пометки чисел,
выведенных на ядре.

Ключи включаются подменой в книгах фикстур (`tests/fixtures/core`, `tests/fixtures/core_t`): книга без ключа
ведёт себя как у панели-образца, и это тоже проверяется. Быстрые тесты (метка `tact`) — чистые функции и один
сухой прогон на малой фикстуре; прогоны на форме панели — `ci_only`.

* **Ось-связка** (вид `bundle`, М§10): концы — словари «путь → значение». Конец идёт за центром тем же правилом,
  что у оси вида `value`; ключи словарей переименовываются вместе с годом шока; путь, пересчитанный переносом
  без правила для конца, и связка по ключам ближнего пути ЧПМ — отказ с причиной.
* **Мир-опора κ** (`credit.kappa_reference_world`): добавка от реальной ставки закрываемого квартала — любого
  знака; у нового якоря её нет (история до сетки у миров общая), поэтому прежняя книга сверяется с кандидатом
  без неё, а её цена стоит отдельной строкой разложения.
* **Цели-суждения** (`checks.nim_stationary`, `checks.cir_lt`, `checks.nim_lt`): инструмент их не трогает,
  печатает число гейта до и после рядом с допуском и раскладывает сдвиг маржи на путь и мост.
* **Мир уровня маржи** (`nii.transmission.level_world`): ключ цели ЧПМ — стационарная маржа названного мира на
  составе баланса якоря. Скаляры пути сохраняются, ключ переписывается на состав нового якоря; гейт
  стационарной маржи в том же мире идёт за ключом и не срабатывает; печатаются прежнее и новое значение и слова
  о том, что пересмотр уровня — решение новой версии книги.
* **Строки уточнения корня** (`valuation.reverse_dcf.refine_rows`), **окно фактов** (`checks.window_backtest`),
  ключи закрытого квартала премии роста: идут за своими осями либо называются в ручных шагах.
* **Ручные шаги — по книге**: перечень чисел, выведенных на ядре, читается из пометок шаблона книги; подмены
  справочных вариантов по переписанным ключам и ось-связка премии роста называются.

Даты тестов — от периодов книги фикстуры, не от «сегодня».
"""
from __future__ import annotations

import copy
from functools import lru_cache
from types import SimpleNamespace

import pytest

from model.book import BookError, book_from_dict
from model.credit import bridge_from_facts
from model.grid import make_context, run_grid
from model.nii import solve_transmission
from tests.support_core import book_with, fixture_dict, fixture_facts
from tests.support_core_t import put, t_dict, t_facts
from tests.test_reanchor import CELLS, R, scene, scene_of
from tests.test_reanchor_t import CELLS as T_CELLS
from tests.test_reanchor_t import NO_CATCH_UP

tact = pytest.mark.tact
ci_only = pytest.mark.ci_only

REF = "M"                                    # мир-опора κ и мир гейта стационарной маржи в тестах
PREMIUM = "volumes.funds_share_drift"


def axes_book(axes: list, **sections) -> dict:
    """Словарь с осями полосы и названными разделами — ровно то, что читают функции осей."""
    return {"valuation": {"uncertainty": {"axes": axes, "off_band_axes": []}, "reverse_dcf": {"axes": []}}, **sections}


def keyed_book(changes: dict):
    """Книга фикстуры общей формы с ключами второй формы, которых в ней нет."""
    return book_from_dict(book_with(changes), facts=fixture_facts())


# ------------------------------------------------------------------ ось-связка


@tact
def test_the_ends_of_a_bundle_follow_the_centre_by_the_rule_of_the_carry():
    """Связка применяется приращением к значению книги: когда перенос пересчитал значение, конец оси по этому
    пути переходит в `стало + k × (конец − было)` — множитель у цен и плотностей, сдвиг у поправок, с областью
    определения у долей. Пути, которых перенос не трогал, и оси других видов остаются как были."""
    bundle = {"name": "связка", "kind": "bundle", "paths": ["a.x", "a.t.2027", "b.y"],
              "low": {"a.x": 8.0, "a.t.2027": 1.0, "b.y": 0.3}, "high": {"a.x": 12.0, "a.t.2027": 3.0, "b.y": 0.7}}
    value = {"name": "число", "kind": "value", "paths": ["c.z"], "low": 0.5, "high": 1.5}
    X = axes_book([bundle, value], a={"x": 10.0, "t": {"2027": 2.0, "LT": 5.0}}, b={"y": 0.5}, c={"z": 1.0})
    centers = R._bundle_centers(X, ("a",))
    assert centers == {"a.x": 10.0, "a.t.2027": 2.0}
    X["a"]["x"] = 11.0                       # чистый множитель 1,1
    X["a"]["t"]["2027"] = 2.5                # сумма года якоря: центр ушёл не множителем
    R._follow_centers(X, centers, 1.1)
    assert bundle["low"] == pytest.approx({"a.x": 8.8, "a.t.2027": 2.5 + 1.1 * (1.0 - 2.0), "b.y": 0.3})
    assert bundle["high"] == pytest.approx({"a.x": 13.2, "a.t.2027": 2.5 + 1.1 * (3.0 - 2.0), "b.y": 0.7})
    before = copy.deepcopy(bundle)
    R._scale_axes(X, ("a", "c"), 2.0)        # множитель осей: связка — своим правилом, смешанные пути ей не отказ
    assert bundle == before and (value["low"], value["high"]) == (1.0, 3.0)
    R._remap_axes(X, "b.y", 0.5, 0.6)        # сдвиг центра: конец идёт за ним
    assert (bundle["low"]["b.y"], bundle["high"]["b.y"]) == pytest.approx((0.4, 0.8))
    R._remap_axes(X, "b.y", 0.6, 0.9, 1.0, (0.0, 1.0))
    assert (bundle["low"]["b.y"], bundle["high"]["b.y"]) == pytest.approx((0.7, 1.0)), "конец не выходит из области"
    assert bundle["low"]["a.x"] == pytest.approx(8.8) and value["paths"] == ["c.z"]
    X["a"]["x"] = "anchor"
    with pytest.raises(R.ReportError, match="не число"):
        R._follow_centers(X, {"a.x": 11.0}, 1.0)


@tact
def test_a_bundle_on_a_key_the_carry_recomputes_without_a_rule_is_refused():
    """Сторож: центр ушёл, а правила для конца нет — отказ с названным путём, а не кандидат с осью мимо центра.
    Пути под корнями, которые инструмент переносит сам, и нетронутые пути проходят."""
    carried = R.GAPS[0][0]
    bundle = {"name": "связка", "kind": "bundle", "paths": ["b.y", carried],
              "low": {"b.y": 0.3, carried: -0.003}, "high": {"b.y": 0.7, carried: 0.003}}
    old = axes_book([bundle], b={"y": 0.5}, capital={"n20": {"gap_pp": 0.0}})
    X = copy.deepcopy(old)
    R.check_bundles(X, old)
    X["capital"]["n20"]["gap_pp"] = 0.01     # поправка норматива: правило есть (сдвиг вместе с центром)
    R.check_bundles(X, old)
    X["b"]["y"] = 0.6
    with pytest.raises(R.ReportError) as exc:
        R.check_bundles(X, old)
    assert "ось-связка двигает b.y" in str(exc.value) and "0.5 → 0.6" in str(exc.value)
    assert set(R.BUNDLE_CARRIED) >= set(R.PRICE_INDEXED) | {R.DENSITY} | set(R.TRANSMISSION_KEYS)


@tact
def test_the_keys_of_a_bundle_are_renamed_with_the_shock_year():
    """Смена года якоря: путь связки по ключу кризисной траектории переименован вместе с ключом — и в `paths`, и
    в словарях обоих концов; значение то же, поэтому сторож связок его не трогает (с картой переименований)."""
    X = fixture_dict()
    crisis = next(r for r in X["regimes"]["ids"] if "shock_year_offset" in X["regimes"][r])
    path, other = f"regimes.{crisis}.loan_growth_adj.2029", "nii.dia_rate"
    axis = {"name": "связка кризиса", "kind": "bundle", "paths": [path, other],
            "low": {path: 0.0, other: 0.004}, "high": {path: 0.02, other: 0.006}, "dist": "triangular"}
    X["valuation"]["uncertainty"]["axes"].append(axis)
    book_from_dict(X, facts=fixture_facts())                     # такая связка проходит схему книги
    old = copy.deepcopy(X)
    renamed = R.shift_crisis(X, 1)
    new = f"regimes.{crisis}.loan_growth_adj.2030"
    assert renamed[path] == new and axis["paths"] == [new, other]
    assert axis["low"] == {new: 0.0, other: 0.004} and axis["high"] == {new: 0.02, other: 0.006}
    assert R._leaf(X, new) == R._leaf(old, path) and R._leaf(X, path) != R._leaf(old, path)
    R.check_bundles(X, old, renamed)
    with pytest.raises(R.ReportError, match="ось-связка двигает"):
        R.check_bundles(X, old)                                  # без карты прежнего значения ключа не найти
    assert R.shift_crisis(copy.deepcopy(old), 0) == {}


@tact
def test_a_bundle_on_the_near_path_is_refused_with_the_reason():
    """Ближний путь ЧПМ перенос пишет заново — другими ключами: концы связки для новых ключей придумать нечем."""
    near = R.NEAR
    axis = {"name": "сход связкой", "kind": "bundle", "paths": [f"{near}.2027", "nii.dia_rate"],
            "low": {f"{near}.2027": -0.002, "nii.dia_rate": 0.004}, "high": {f"{near}.2027": 0.002, "nii.dia_rate": 0.006}}
    X = axes_book([axis], regimes={"near_nim_shift": {}})
    with pytest.raises(R.ReportError) as exc:
        R.set_near(X, {"2027Q1": 0.0, "2027Q2": 0.0, "2027Q3": 0.0, "2027Q4": 0.0, "2027": 0.0, "LT": 0.0})
    assert "ось-связка двигает ключи ближнего пути ЧПМ" in str(exc.value) and "сход связкой" in str(exc.value)


@ci_only
def test_a_book_with_a_bundle_is_carried_to_the_new_anchor():
    """Сухой прогон книги со связкой по ценам якоря, плотности RWA и поправке норматива: кандидат читается ядром,
    концы связки пересчитаны вместе с центрами — у суммы года якоря, закрытой остатком к факту, отклонение конца
    от центра умножено на индекс цен, — путь, которого перенос не трогает, остался как был."""
    data = fixture_dict()
    density = f"{R.DENSITY}.{next(iter(data['capital']['rwa']['density']))}"
    gap, free = R.GAPS[1][0], "nii.dia_rate"
    year = int(str(data["meta"]["first_period"])[:4])
    prices = [f"{R.NONCORE}.{year}", f"{R.NONCORE}.2030"]
    paths = prices + [density, gap, free]
    center = {p: R._leaf(data, p) for p in paths}
    axis = {"name": "связка якоря", "kind": "bundle", "paths": paths, "dist": "triangular",
            "low": {p: center[p] - abs(center[p]) * 0.2 for p in paths},
            "high": {p: center[p] + abs(center[p]) * 0.2 for p in paths}}
    data["valuation"]["uncertainty"]["axes"].append(axis)
    book = book_from_dict(data, facts=fixture_facts())
    s = scene_of(book, fixture_facts())
    (got,) = [a for a in s.cand.data["valuation"]["uncertainty"]["axes"] if a["kind"] == "bundle"]
    assert got["paths"] == paths and set(got["low"]) == set(got["high"]) == set(paths)
    now = {p: R._leaf(s.cand.data, p) for p in paths}
    factor, k = s.cand.derived["price_index"], s.cand.derived["rwa_factor"]
    assert now[prices[0]] != pytest.approx(center[prices[0]] * factor, abs=1e-3), "год якоря закрыт остатком к факту"
    slope = {prices[0]: factor, prices[1]: factor, density: k, gap: 1.0, free: 1.0}
    for end in ("low", "high"):
        for p in paths:
            assert got[end][p] - now[p] == pytest.approx(slope[p] * (axis[end][p] - center[p]), abs=2e-6), (end, p)
    assert (now[free], got["low"][free]) == (center[free], axis["low"][free])
    assert now[density] == pytest.approx(center[density] * k, abs=1e-6) and now[prices[1]] == pytest.approx(
        center[prices[1]] * factor, abs=1e-5)
    changed = {R.dotted(p) for p, _, _ in s.cand.changes}
    assert any("[связка якоря].low" in p for p in changed) and all(R.reason(p) for p in changed)


# ------------------------------------------------------------------ мир-опора κ


@lru_cache(maxsize=None)
def kappa_scene() -> SimpleNamespace:
    return scene_of(keyed_book({R.KAPPA_WORLD: REF}), fixture_facts())


@tact
def test_with_a_reference_world_the_addon_of_the_closed_quarter_is_history():
    """Мир-опора κ: добавка κ × (rr мира − rr опоры) — любого знака. У нового якоря закрытый квартал — история,
    общая для миров, и добавки квартала 1 + L нет: путь прежней книги, с которым сверяется кандидат, пересчитан
    без неё — только в мирах, где она была, и только в этом квартале."""
    s = kappa_scene()
    book = s.book
    kappa, lag = float(book.get("credit.kappa")), int(book.get("credit.real_rate_lag_q"))
    rr = {w: p.real_key[1] for w, p in s.run_plus.ctx.worlds.items()}
    adds = R.lost_kappa_adds(book, s.run_plus)
    assert adds == pytest.approx({w: kappa * (rr[w] - rr[REF]) for w in rr if w != REF})
    assert min(adds.values()) < 0 < max(adds.values()), "на фикстуре есть миры по обе стороны от опоры"
    q = 1 + lag
    for key in CELLS:                        # по клетке каждого мира: выше опоры, ниже опоры, сама опора
        hist = R.history_run(book, s.run_plus, key)
        assert hist is not s.run_plus and [c.key for c in hist.cells] == [key]
        assert R.lost_kappa_adds(book, hist) == {} and R.history_run(book, hist, key) is hist, "повторно снимать нечего"
        old, new = s.run_plus.cell(*key), hist.cell(*key)
        if old.world == REF:
            assert new is old
            continue
        assert new.quarters["cor"][q] == pytest.approx(old.quarters["cor"][q] - adds[old.world], abs=1e-12)
        assert all(new.quarters["cor"][j] == pytest.approx(old.quarters["cor"][j], abs=1e-12)
                   for j in range(1, len(old.quarters["cor"])) if j != q), old.label
        assert (new.v_ri > old.v_ri) == (adds[old.world] > 0), "снятый расход поднимает стоимость, снятая скидка — опускает"
    assert {key[0] for key in CELLS} == set(rr), "клетки теста — по одной на мир"
    notes = [w for w in s.cand.warnings if "κ-добавка" in w]
    assert len(notes) == 1 and f"к миру-опоре {REF}" in notes[0] and "история до сетки" in notes[0]
    assert s.run_plus.ctx.timeline.period(q) in notes[0] and "эффект в строке «механика»" not in notes[0]
    for w, v in adds.items():
        assert f"{w}: {v * 100:+.2f} п.п." in notes[0]
    plain = scene()                          # книга без ключа: опора — базовый мир, добавка только вверх
    assert R.lost_kappa_adds(plain.book, plain.run_plus) == {}
    assert R.history_run(plain.book, plain.run_plus) is plain.run_plus


@ci_only
def test_the_history_row_is_priced_apart_and_mechanics_stays_zero():
    """Строка «история до сетки» — цена снятой добавки; клетка на своём пути сверяется с прежней книгой без неё и
    сохраняет стоимость. Строки разложения складываются: обучение → история → механика → выпуклость → сюрприз."""
    s = kappa_scene()
    result = R.attribution(s.book, s.facts, s.expected, valuation_date=s.v)
    mech = result["mechanics"]
    assert len(mech["rows"]) == len(s.run_plus.cells)
    assert mech["history"] and mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 10, mech["worst"]
    adds = R.lost_kappa_adds(s.book, s.run_plus)
    for r in mech["rows"]:
        world = r["key"][0]
        assert r["base"] == pytest.approx(r["old"] * (1 + r["history"]))
        assert (r["history"] == 0.0) == (world == REF) and (world == REF or (r["history"] > 0) == (adds[world] > 0))
    steps = result["steps"]
    assert set(steps) == {"rolled", "learning", "history", "mechanics", "expected", "candidate"}
    assert steps["history"]["point"] == pytest.approx(
        R._priced(s.run_plus, {r["key"]: r["base"] for r in mech["rows"]})["point"])
    step = float(s.book.get("valuation.headline.print_step"))
    assert abs(steps["mechanics"]["point"] - steps["history"]["point"]) <= 0.01 * step
    assert result["history"]["adds"] == adds and result["history"]["world"] == REF
    text = R.report_text(s.book, result)
    for fragment in ("(история до сетки — общая для миров)", "**История до сетки.**", "без κ-добавки закрытого квартала",
                     "изменение к базе", "допуск 0,1 % — выполнен"):
        assert fragment in text, fragment
    order = [text.index(title) for title in ("(обучение)", "(история до сетки — общая для миров)", "(механика, ≈ 0)",
                                             "(выпуклость)", "(сюрприз факта)")]
    assert order == sorted(order), "строки разложения — в порядке шагов"
    plain = R.report_text(scene().book, R.attribution(scene().book, scene().facts, scene().expected,
                                                      valuation_date=scene().v, cells=False))
    assert "История до сетки" not in plain and "история до сетки" not in plain


# ------------------------------------------------------------------ цели-суждения гейтов


@lru_cache(maxsize=None)
def stationary_scene() -> tuple[SimpleNamespace, dict]:
    ctx = scene().run_plus.ctx
    gate = {"world": REF, "target": round(ctx.bridge.to_mgmt_nim(ctx.transmission.nss[REF]), 6), "tolerance": 0.0005}
    return scene_of(keyed_book({R.NIM_STATIONARY: gate}), fixture_facts()), gate


@tact
def test_the_target_of_the_stationary_margin_is_reported_and_never_moved():
    """Гейт стационарной маржи: цель — суждение книги на составе якоря. Перенос сохраняет скаляры пути, поэтому
    число гейта на новом якоре сдвигается на состав баланса и на мост — инструмент печатает сдвиг с разложением,
    порядок действий, а цель и допуск не трогает. У книги без ключа ничего этого нет."""
    s, gate = stationary_scene()
    st = s.cand.derived["stationary"]
    assert s.cand.data["checks"]["nim_stationary"] == gate, "цель и допуск — суждение книги"
    old, new = s.run_plus.ctx, s.run_e.ctx
    assert st["world"] == REF and st["before"] == pytest.approx(gate["target"], abs=1e-6)
    assert st["value"] == pytest.approx(new.bridge.to_mgmt_nim(new.transmission.nss[REF]))
    assert st["d_engine"] == pytest.approx(new.transmission.nss[REF] - old.transmission.nss[REF])
    assert st["value"] - st["before"] == pytest.approx(st["d_engine"] + st["d_bridge"])
    assert abs(st["d_engine"]) > 10 * abs(st["d_bridge"]) > 0, "на ожидаемом отчёте сдвиг — состав баланса; мост — мал"
    assert R._sigmas(new.transmission) == pytest.approx(R._sigmas(old.transmission), abs=2e-6)
    assert st["fired"] == (abs(st["value"] - gate["target"]) > gate["tolerance"])
    notes = [w for w in s.cand.warnings if w.startswith(R.NIM_STATIONARY)]
    assert len(notes) == 1 and ("срабатывает" in notes[0]) == st["fired"]
    for fragment in ("Цель гейта — суждение книги", f"`{R.NIM_TARGET}`", "Порядок: (1)", "(2) ключ выводится на ядре заново",
                     "«суждения книги»", "маржа движка", "мост упр. ↔ движок"):
        assert fragment in notes[0], fragment
    plain = scene()
    assert plain.cand.derived["stationary"] is None
    assert not any(w.startswith(R.NIM_STATIONARY) for w in plain.cand.warnings)
    # число гейта — в проверках ядра на кандидате, сработал он или нет
    was, now = R.core_checks(s.run_a, s.v), R.core_checks(s.run_e, s.v)
    row = now["targets"]["nim_stationary"]
    assert (row["value"], row["target"], row["tolerance"]) == pytest.approx((st["value"], gate["target"], gate["tolerance"]))
    assert row["engine"] == pytest.approx(new.transmission.nss[REF]) and row["fired"] == st["fired"]
    text = "\n".join(R.target_lines(was, now))
    assert "| `nim_stationary` |" in text and "Сдвиг числа `nim_stationary`:" in text and "п.п.." not in text
    assert R.core_checks(plain.run_e, plain.v)["targets"] == {} and R.core_checks(plain.run_e, plain.v)["levels"] is None


@tact
def test_the_targets_section_reads_as_a_table():
    """Раздел целей отчёта кандидата: число до и после, цель с допуском, запас до границы или выход за неё,
    разложение сдвига маржи на маржу движка и мост, узел уровней после фазы роста."""
    was = {"targets": {"nim_stationary": {"value": 0.111, "target": 0.111, "tolerance": 0.0005, "engine": 0.1098},
                       "cir_lt": {"value": 0.47, "target": 0.47, "tolerance": 0.01}},
           "levels": {"rows": {"modal_cell": {"nim": 0.1110, "cor": 0.05, "cir": 0.46, "loans_share": 0.75}}}}
    now = {"targets": {"nim_stationary": {"value": 0.11212, "target": 0.111, "tolerance": 0.0005, "engine": 0.11105},
                       "cir_lt": {"value": 0.471, "target": 0.47, "tolerance": 0.01},
                       "new_gate": {"value": 0.2, "target": 0.2, "tolerance": 0.0}},
           "levels": {"from_year": 2030, "to_year": 2036, "cell": "H/norm/mid", "order": ["modal_cell", "macro_neutral"],
                      "rows": {"modal_cell": {"title": "Модальная клетка", "nim": 0.1107, "cor": 0.05, "cir": 0.465,
                                              "loans_share": 0.753},
                               "macro_neutral": {"title": "Рыночные ставки как есть", "nim": 0.105, "cor": 0.052,
                                                 "cir": None, "loans_share": 0.7}}}}
    text = "\n".join(R.target_lines(was, now))
    for fragment in ("| `nim_stationary` | 11,100 % | 11,212 % | 11,10 % ± 0,05 п.п. | вне допуска на 0,062 п.п. |",
                     "| `cir_lt` | 47,000 % | 47,100 % | 47,00 % ± 1,00 п.п. | 0,900 п.п. |",
                     "| `new_gate` | — | 20,000 % |",
                     "Сдвиг числа `nim_stationary`: +0,112 п.п., из них маржа движка +0,125 п.п., мост упр. ↔ движок "
                     "-0,013 п.п.;",
                     "среднее за 2030–2036 годы (прежняя книга → кандидат); модальная клетка — H/norm/mid",
                     "| Модальная клетка | 11,10 % → 11,07 % | 5,00 % → 5,00 % | 46,0 % → 46,5 % | 75,0 % → 75,3 % |",
                     "| Рыночные ставки как есть | 10,50 % | 5,20 % | — | 70,0 % |"):
        assert fragment in text, fragment
    assert "Сдвиг числа `cir_lt`" not in text, "разложение на путь и мост — только у целей маржи"
    assert R.target_lines({"targets": {}, "levels": None}, {"targets": {}, "levels": None}) == []
    assert "книга на оценке → кандидат" in "\n".join(R.target_lines(was, now, "книга на оценке"))


# ------------------------------------------------------------------ мир уровня маржи


def level_dict(*, gate: str | None = REF, split: float | None = None, phi_split: float | None = None) -> dict:
    """Книга фикстуры общей формы в записи с миром уровня: ключ цели ЧПМ — стационарная маржа мира `REF` на
    составе баланса якоря (та же передача, что у фикстуры: ключ — её же стационар, шесть знаков), оси по ключу —
    вокруг него. `gate` — мир гейта стационарной маржи с целью, равной его стационару (None — гейта нет)."""
    data, facts = fixture_dict(), fixture_facts()
    for path, value in ((R.SPLIT, split), (R.PHI_SPLIT, phi_split)):
        if value is not None:
            R._set(data, path, value)
    ctx = make_context(book_from_dict(data, facts=facts), facts)
    margin = {w: round(ctx.bridge.to_mgmt_nim(v), 6) for w, v in ctx.transmission.nss.items()}
    shift = margin[REF] - float(R._get(data, R.NIM_TARGET))
    R._set(data, R.LEVEL_WORLD, REF)
    R._set(data, R.NIM_TARGET, margin[REF])
    for _, axes, keys in R._axis_lists(data):
        for axis in axes:
            if axis.get("paths") == [R.NIM_TARGET]:
                R._move_axis(axis, keys, lambda v: round(v + shift, 6))
    if gate is not None:
        data["checks"]["nim_stationary"] = {"world": gate, "target": margin[gate], "tolerance": 0.0005}
    return data


@lru_cache(maxsize=None)
def level_scene(gate: str | None = REF) -> SimpleNamespace:
    return scene_of(book_from_dict(level_dict(gate=gate), facts=fixture_facts()), fixture_facts())


@tact
def test_the_level_key_is_rewritten_to_the_new_anchor_and_its_gate_stays_silent():
    """Ключ цели ЧПМ в мире уровня — суждение на составе баланса якоря. Перенос сохраняет скаляры пути и
    переписывает ключ на состав нового якоря: он равен стационарной марже мира уровня по счёту ядра — и той же,
    что у кандидата той же книги в записи образца. Гейт стационарной маржи в том же мире сверяет то же число:
    его цель идёт за ключом, и на кандидате он не срабатывает. Печатаются прежнее и новое значение с разложением
    сдвига и слова: это запись прежнего суждения, пересмотр уровня — решение новой версии книги."""
    s, plain = level_scene(), scene()
    old, new = s.run_plus.ctx, s.run_e.ctx
    assert R._sigmas(new.transmission) == pytest.approx(R._sigmas(old.transmission), abs=2e-6)
    assert R._sigmas(old.transmission) == pytest.approx(R._sigmas(plain.run_plus.ctx.transmission), abs=2e-6), \
        "та же передача, что у фикстуры в записи образца"
    lv = s.cand.derived["level"]
    key_old, key_new = lv["key"]
    assert (lv["world"], key_old) == (REF, float(s.book.get(R.NIM_TARGET))) and key_new == R._get(s.cand.data, R.NIM_TARGET)
    assert abs(key_new - key_old) > 100 * R.LEVEL_TOL, "состав баланса нового якоря другой — ключ переписан"
    assert lv["value"] == pytest.approx(lv["key"], abs=R.LEVEL_TOL), "ключ — стационарная маржа мира уровня по счёту ядра"
    assert lv["value"][1] == pytest.approx(new.bridge.to_mgmt_nim(new.transmission.nss[REF]))
    assert lv["value"][1] - lv["value"][0] == pytest.approx(lv["d_engine"] + lv["d_bridge"])
    assert lv["d_engine"] == pytest.approx(new.transmission.nss[REF] - old.transmission.nss[REF])
    ref = new.transmission.reference_world
    assert lv["reference_world"] == ref != REF
    assert lv["reference"][1] == pytest.approx(new.bridge.to_mgmt_nim(new.transmission.nss[ref]))
    # та же книга в записи образца: её кандидат несёт уровень мира-опоры, а стационар мира уровня у него — тот же
    other = plain.run_e.ctx
    assert key_new == pytest.approx(other.bridge.to_mgmt_nim(other.transmission.nss[REF]), abs=3e-6)
    assert lv["reference"][1] == pytest.approx(R._get(plain.cand.data, R.NIM_TARGET), abs=3e-6)
    step = float(s.book.get("valuation.headline.print_step"))
    assert abs(s.run_e.point - plain.run_e.point) <= 0.01 * step and abs(s.run_plus.point - plain.run_plus.point) <= 0.01 * step
    # гейт в мире уровня: цель — то же суждение и идёт за ключом; мир и допуск не тронуты; гейт молчит
    gate = s.cand.data["checks"]["nim_stationary"]
    assert gate == {"world": REF, "target": key_new, "tolerance": 0.0005} and lv["gate"] == (key_old, key_new)
    st = s.cand.derived["stationary"]
    assert st["fired"] is False and abs(st["value"] - st["target"]) <= R.LEVEL_TOL
    checks = R.core_checks(s.run_e, s.v)
    assert "nim_stationary" not in checks["gates"] and checks["targets"]["nim_stationary"]["fired"] is False
    assert checks["error"] is None and checks["invariants"] == []
    # слова: прежнее и новое значение, разложение, чьё это решение; порядка «вывести ключ из цели» здесь нет
    (note,) = [w for w in s.cand.warnings if w.startswith(R.NIM_TARGET + " — уровень маржи")]
    for fragment in (f"мира {REF}", f"`{R.LEVEL_WORLD}`", f"{R._pct(key_old, 3)} → {R._pct(key_new, 3)}", "маржа движка",
                     "мост упр. ↔ движок", f"уровень мира-опоры решателя {ref}", "запись прежнего суждения",
                     "Пересмотр уровня по новому окну фактов", "решение новой версии книги", "«суждения книги»",
                     f"Гейт `{R.NIM_STATIONARY}`", "гейт от него не срабатывает"):
        assert fragment in note, fragment
    assert "ВНИМАНИЕ" not in note and not any(w.startswith(R.NIM_STATIONARY) for w in s.cand.warnings)
    changed = {R.dotted(p): (a, b) for p, a, b in s.cand.changes}
    assert changed[R.NIM_TARGET] == (key_old, key_new) and changed[R.GATE_TARGET] == (key_old, key_new)
    assert "то же суждение, что ключ уровня маржи" in R.reason(R.GATE_TARGET)
    assert f"{R.NIM_STATIONARY}.world" not in changed and f"{R.NIM_STATIONARY}.tolerance" not in changed
    # концы оси уровня несут прежние скаляры: ось перенесена тем же правилом, что ключ
    (axis_old,) = [a for a in s.book.source["valuation"]["uncertainty"]["axes"] if a["paths"] == [R.NIM_TARGET]]
    (axis_new,) = [a for a in s.cand.data["valuation"]["uncertainty"]["axes"] if a["paths"] == [R.NIM_TARGET]]
    for end in ("low", "high"):
        end_old = solve_transmission(old.book.with_overrides({R.NIM_TARGET: axis_old[end]}), s.facts, old.bridge)
        Y = copy.deepcopy(s.cand.data)
        R._set(Y, R.NIM_TARGET, axis_new[end])
        end_new = solve_transmission(book_from_dict(Y, facts=s.cand.facts), s.cand.facts, new.bridge)
        assert R._sigmas(end_new) == pytest.approx(R._sigmas(end_old), abs=6e-6), end


@ci_only
def test_the_level_record_keeps_every_cell_and_the_report_prints_the_key():
    """Инвариант «механика ≈ 0» в записи с миром уровня — на всех клетках сетки; отчёт кандидата печатает строку
    «уровень маржи» и цель гейта-тождества «было → стало»."""
    s = level_scene()
    key_old, key_new = s.cand.derived["level"]["key"]
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v)
    assert len(mech["rows"]) == len(s.run_plus.cells) and mech["ok"]
    assert abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 10, mech["worst"]
    text = R.report_text(s.book, R.attribution(s.book, s.facts, s.expected, valuation_date=s.v, cells=False))
    assert f"- уровень маржи — ключ `{R.NIM_TARGET}`, стационарная маржа мира {REF}" in text
    assert "не пересмотр уровня" in text and "п.п.." not in text
    assert (f"| `nim_stationary` | {R._pct(key_old, 3)} | {R._pct(key_new, 3)} | {R._pct(key_old, 3)} → "
            f"{R._pct(key_new, 3)} ± 0,05 п.п. |") in text, "цель гейта-тождества: было → стало"


@tact
def test_without_the_gate_key_the_level_key_is_carried_just_the_same():
    """Книга без гейта стационарной маржи (суждение записано одним ключом): срабатывать нечему, ключ переписан
    так же, слова те же — без фразы о гейте. Гейт в другом мире — отдельное суждение: цель не тронута."""
    s, gated = level_scene(None), level_scene()
    lv = s.cand.derived["level"]
    assert "nim_stationary" not in s.cand.data["checks"] and s.cand.derived["stationary"] is None and lv["gate"] is None
    assert lv["key"] == gated.cand.derived["level"]["key"], "тот же перенос ключа, что у книги с гейтом"
    assert R._sigmas(s.run_e.ctx.transmission) == pytest.approx(R._sigmas(s.run_plus.ctx.transmission), abs=2e-6)
    checks = R.core_checks(s.run_e, s.v)
    assert "nim_stationary" not in checks["targets"] and "nim_stationary" not in checks["gates"]
    (note,) = [w for w in s.cand.warnings if w.startswith(R.NIM_TARGET + " — уровень маржи")]
    assert "решение новой версии книги" in note and "Гейт" not in note
    assert not any(R.dotted(p).startswith(R.NIM_STATIONARY) for p, _, _ in s.cand.changes)
    # чистые функции: цель гейта идёт за ключом только в мире уровня и тем же сдвигом
    kept = {R.NIM_TARGET: (0.111, 0.1121, 1.0)}
    X = {"nii": {"transmission": {"level_world": REF}}, "checks": {"nim_stationary": {"world": REF, "target": 0.1105,
                                                                                    "tolerance": 0.0005}}}
    assert R.carry_level_gate(X, kept) == pytest.approx((0.1105, 0.1116)), "разница цели и ключа прежней книги сохранена"
    assert X["checks"]["nim_stationary"] == {"world": REF, "target": pytest.approx(0.1116), "tolerance": 0.0005}
    for other in ({"nii": {"transmission": {"level_world": REF}}, "checks": {"nim_stationary": {"world": "H", "target": 0.113}}},
                  {"nii": {"transmission": {}}, "checks": {"nim_stationary": {"world": REF, "target": 0.111}}},
                  {"nii": {"transmission": {"level_world": REF}}, "checks": {}}):
        before = copy.deepcopy(other)
        assert R.carry_level_gate(other, kept) is None and other == before
    st = {"world": "H", "value": 0.1142, "target": 0.113, "tolerance": 0.0005, "before": 0.1131, "d_engine": 0.0012,
          "d_bridge": -0.0001, "fired": True}
    apart = R.stationary_note(st, level={"world": REF})
    assert "отдельное суждение книги о марже мира H" in apart and "Порядок: (1)" not in apart and "срабатывает" in apart
    assert "Порядок: (1)" in R.stationary_note(st), "книга без мира уровня: ключ выводится из цели гейта — прежний порядок"
    quiet = R.level_note({"world": REF, "key": (0.111, 0.111), "value": (0.111, 0.111), "d_engine": 0.0, "d_bridge": 0.0,
                          "reference_world": "H", "reference": (0.113, 0.114), "gate": None})
    assert "Ключ оставлен числом прежней книги" in quiet and "переписал" not in quiet
    broken = R.level_note({"world": REF, "key": (0.111, 0.112), "value": (0.111, 0.1125), "d_engine": 0.001,
                           "d_bridge": 0.0005, "reference_world": "H", "reference": (0.113, 0.114), "gate": None})
    assert "ВНИМАНИЕ" in broken and "в канон не переносить" in broken
    assert scene().cand.derived["level"] is None, "книга без ключа мира уровня: ключ цели — уровень мира-опоры, как у образца"


@ci_only
@pytest.mark.parametrize("split,phi_split", [(0.09, 0.0), (1.0, 0.62), (0.0, 0.3)])
def test_keep_in_the_level_record_holds_the_scalars_at_any_shares(split, phi_split):
    """Запись с миром уровня при любых долях: скаляры пути — прежние, ключ — стационарная маржа мира уровня,
    концы осей по ключу и по цели передачи несут прежние скаляры (вдоль оси передачи неподвижен ключ уровня, и
    уровень мира-опоры идёт за целью), доли на краях остаются на краях."""
    facts = fixture_facts()
    old = book_from_dict(level_dict(gate=None, split=split, phi_split=phi_split), facts=facts)
    s = scene_of(old, facts)
    was, bridge = s.run_plus.ctx.transmission, bridge_from_facts(s.cand.facts)
    now = solve_transmission(s.cand.book, s.cand.facts, bridge)
    assert R._sigmas(now) == pytest.approx(R._sigmas(was), abs=2e-6)
    assert bridge.to_mgmt_nim(now.nss[REF]) == pytest.approx(R._get(s.cand.data, R.NIM_TARGET), abs=R.LEVEL_TOL)
    for path, edge in ((R.SPLIT, split), (R.PHI_SPLIT, phi_split)):
        assert (R._get(s.cand.data, path) == edge) == (edge in (0.0, 1.0)), path
    for path in (R.NIM_TARGET, R.T_TARGET):
        (axis_old,) = [a for a in s.book.source["valuation"]["uncertainty"]["axes"] if a["paths"] == [path]]
        (axis_new,) = [a for a in s.cand.data["valuation"]["uncertainty"]["axes"] if a["paths"] == [path]]
        for end in ("low", "high"):
            end_old = solve_transmission(s.run_plus.ctx.book.with_overrides({path: axis_old[end]}), facts, s.run_plus.ctx.bridge)
            Y = copy.deepcopy(s.cand.data)
            R._set(Y, path, axis_new[end])
            end_new = solve_transmission(book_from_dict(Y, facts=s.cand.facts), s.cand.facts, bridge)
            assert R._sigmas(end_new) == pytest.approx(R._sigmas(end_old), abs=1e-5), (path, end)
            if path == R.T_TARGET:               # вдоль оси передачи мир уровня стоит на месте — на обоих якорях
                assert bridge.to_mgmt_nim(end_new.nss[REF]) == pytest.approx(R._get(s.cand.data, R.NIM_TARGET), abs=R.LEVEL_TOL)
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=CELLS)
    assert mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 5, mech["worst"]


@ci_only
def test_resolve_leaves_the_level_key_and_the_target_of_its_gate():
    """Диагностика `resolve` у книги с миром уровня: ключ, цель гейта-тождества и оси — числа прежней книги,
    скаляры ядро решает под ключ заново на новом составе; слова говорят, что ключ оставлен."""
    s = level_scene()
    cand = R.reanchor(s.book, s.facts, s.expected, valuation_date=s.v, base_run=s.run_plus, transmission=R.RESOLVE)
    for path in R.TRANSMISSION_KEYS + (R.GATE_TARGET,):
        assert R._get(cand.data, path) == R._get(s.book.source, path), path
    run = run_grid(cand.book, cand.facts, s.live_e)
    assert R._sigmas(run.ctx.transmission) != pytest.approx(R._sigmas(s.run_plus.ctx.transmission), abs=1e-5)
    lv = cand.derived["level"]
    assert lv["key"][0] == lv["key"][1] and lv["gate"] is None and lv["value"][1] == pytest.approx(lv["key"][1], abs=1e-9)
    (note,) = [w for w in cand.warnings if w.startswith(R.NIM_TARGET + " — уровень маржи")]
    assert "Ключ оставлен числом прежней книги" in note
    assert abs(run.point - s.run_plus.point) > 10 * abs(s.run_e.point - s.run_plus.point), "сдвиг без новости — в механике"
    text = R.report_text(s.book, R.attribution(s.book, s.facts, s.expected, valuation_date=s.v, cells=False,
                                               transmission=R.RESOLVE))
    assert "ключ оставлен числом прежней книги, скаляры пути решены под него заново" in text
    assert "не пересмотр уровня" not in text


@tact
def test_refine_rows_follow_the_rows_of_the_reverse_calculation():
    """Строки с уточнением корня на полной полосе названы ключами строк — путями осей обратного расчёта: когда
    перенос переименовал пути оси, имя строки идёт за ней; строка снятой оси уходит с предупреждением; книга без
    ключа и перечень, которого перенос не коснулся, не меняются."""
    crisis, level = "regimes.crisis.cor.2027", R.NIM_TARGET
    X = axes_book([])
    X["valuation"]["reverse_dcf"]["axes"] = [
        {"name": "уровень", "kind": "value", "paths": [level]},
        {"name": "шок", "kind": "value", "paths": [crisis]},
        {"name": "сход", "kind": "shift", "paths": [f"{R.NEAR}.2027", f"{R.NEAR}.2028"]}]
    before = R._row_keys(X)
    rows = [key for _, key in before]
    assert rows[:2] == [level, crisis] and rows[2].startswith(R.NEAR)
    X["valuation"]["reverse_dcf"]["refine_rows"] = list(rows) + ["чужая строка"]
    refine = copy.deepcopy(X["valuation"]["reverse_dcf"]["refine_rows"])
    warnings: list[str] = []
    R.carry_refine_rows(X, refine, before, warnings)
    assert X["valuation"]["reverse_dcf"]["refine_rows"] == refine and not warnings, "нечего переносить — перечень тот же"
    axes = X["valuation"]["reverse_dcf"]["axes"]
    axes[1]["paths"] = ["regimes.crisis.cor.2028"]           # год шока сдвинут вместе с годом якоря
    axes.remove(axes[2])                                     # ось по закрытым ключам ближнего пути снята
    R.carry_refine_rows(X, refine, before, warnings)
    assert X["valuation"]["reverse_dcf"]["refine_rows"] == [level, "regimes.crisis.cor.2028", "чужая строка"]
    assert len(warnings) == 1 and warnings[0].startswith(R.REFINE_ROWS) and rows[2] in warnings[0]
    R.carry_refine_rows(X, refine, before)                   # повтор от перечня прежней книги — тот же итог
    assert X["valuation"]["reverse_dcf"]["refine_rows"] == [level, "regimes.crisis.cor.2028", "чужая строка"]
    plain = axes_book([])
    R.carry_refine_rows(plain, None, R._row_keys(plain), warnings)
    assert "refine_rows" not in plain["valuation"]["reverse_dcf"] and len(warnings) == 1
    assert "ключами строк" in R.reason(R.REFINE_ROWS)


@ci_only
def test_a_book_with_refine_rows_carries_them_through_the_change_of_the_anchor_year():
    """Через сам перенос: перечень строк уточнения, названный по оси кризисного ключа, после смены года якоря
    называет ту же ось её новым ключом; строка по ключу уровня — прежняя. Кандидат читается ядром."""
    data = level_dict(gate=None)
    crisis = next(r for r in data["regimes"]["ids"] if "shock_year_offset" in data["regimes"][r])
    year = int(str(data["meta"]["anchor_period"])[:4]) + int(data["regimes"][crisis]["shock_year_offset"])
    path = f"regimes.{crisis}.nim_shift.{year}"
    assert R._leaf(data, path) is not None, "у фикстуры есть ключ года шока"
    data["valuation"]["reverse_dcf"]["axes"].append(
        {"name": "Сдвиг ЧПМ года шока", "kind": "value", "paths": [path], "search": [-0.02, 0.01],
         "range": [-0.006, -0.002], "unit": "п.п."})
    data["valuation"]["reverse_dcf"]["refine_rows"] = [R.NIM_TARGET, path]
    try:
        book, facts = book_from_dict(data, facts=fixture_facts()), fixture_facts()
    except BookError as exc:
        if "refine_rows" not in str(exc):
            raise
        pytest.skip(f"ядро ещё не знает ключ {R.REFINE_ROWS}: {str(exc).splitlines()[-1]}")
    renamed = None
    for _ in range(4):                           # до отчёта, который меняет год якоря
        s = scene_of(book, facts)
        rows = s.cand.data["valuation"]["reverse_dcf"]["refine_rows"]
        if s.cand.derived["year_shift"]:
            renamed = f"regimes.{crisis}.nim_shift.{year + 1}"
            assert rows == [R.NIM_TARGET, renamed]
            assert any(R.dotted(p).startswith(R.REFINE_ROWS) for p, _, _ in s.cand.changes)
            break
        assert rows == [R.NIM_TARGET, path]
        book, facts = s.cand.book, s.cand.facts
    assert renamed is not None, "цепочка дошла до смены года якоря"


@tact
def test_the_window_of_facts_is_named_with_the_quarter_of_the_report_beside_it():
    """Окно фактов книги — запись окна прежней книги: перенос его не трогает, называет поля, ставит упр. числа
    квартала отчёта рядом с краями окна и говорит, чьё решение — продлить окно. Строка окна узла уровней
    печатается под таблицей уровней, какой бы вид ни имели её величины."""
    X = {"checks": {"window_backtest": {"from_year": 2030, "cor": [0.047, 0.067], "cir": [0.46, 0.483],
                                        "nim": [0.1002, 0.1159], "means": {"nim": 0.1075, "cor": 0.057, "cir": 0.47},
                                        "loans_share": 0.636}}}
    report = {"period": "2026Q3", "mgmt": {"nim": 0.1171, "cor": 0.052, "cir": 0.455}}
    note = R.window_note(X, report)
    for fragment in (f"окно фактов (`{R.WINDOW_BACKTEST}`: cor, cir, nim, means, loans_share)", "запись окна прежней книги",
                     "Квартал отчёта 2026Q3, упр.:", "ЧПМ 11,71 % — выше наибольшего квартала окна (10,02 %…11,59 %)",
                     "CoR 5,20 % — внутри окна (4,70 %…6,70 %)", "C/I 45,50 % — ниже наименьшего квартала окна",
                     "решение новой версии книги, не перенос"):
        assert fragment in note, fragment
    bare = R.window_note({"checks": {"window_backtest": {"from_year": 2030, "cor": [0.047, 0.067], "cir": [0.46, 0.483]}}},
                         {"period": "2026Q3", "mgmt": {"nim": 0.1171, "cor": 0.052}})
    assert "ЧПМ" not in bare and "CoR 5,20 %" in bare and "C/I" not in bare and "loans_share" not in bare
    assert X["checks"]["window_backtest"]["loans_share"] == 0.636
    assert "Квартал отчёта" not in R.window_note(X) and R.window_note({"checks": {}}, report) is None
    assert X["checks"]["window_backtest"]["nim"] == [0.1002, 0.1159], "поля окна не тронуты"
    steps = R.manual_steps(scene().book, {**copy.deepcopy(scene().cand.data), "checks": {
        **scene().cand.data["checks"], **X["checks"]}}, changes=scene().cand.changes, report=report)
    assert sum(w.startswith("окно фактов") for w in steps) == 1
    assert not any(w.startswith("окно фактов") for w in scene().cand.warnings), "нет ключа окна — нет и шага"
    levels = {"from_year": 2030, "to_year": 2036, "cell": "H/norm/mid", "order": ["macro_neutral"],
              "rows": {"macro_neutral": {"title": "Рыночные ставки как есть", "nim": 0.118, "cor": 0.052, "cir": 0.47,
                                         "loans_share": 0.75}},
              "window": {"nim": {"min": 0.1002, "max": 0.1159, "mean": 0.1075},
                         "cor": {"min": 0.047, "max": 0.067, "mean": None}, "cir": {"min": None, "max": None, "mean": 0.47},
                         "loans_share": {"window": 0.636, "anchor": 0.687}}}
    was = copy.deepcopy(levels)
    was["window"]["loans_share"]["anchor"] = 0.677
    text = "\n".join(R.target_lines({"targets": {}, "levels": was}, {"targets": {}, "levels": levels}))
    assert ("| Окно фактов книги: наименьший…наибольший квартал | 10,02 %…11,59 %, среднее 10,75 % | 4,70 %…6,70 % | "
            "среднее 47,0 % | окно 63,6 %, якорь 67,7 % → 68,7 % |" in text), text
    del levels["window"]
    assert "Окно фактов книги" not in "\n".join(R.target_lines({"targets": {}, "levels": was}, {"targets": {}, "levels": levels}))
    assert R._window_cell(None, 2) == "—" and R._window_cell({"min": None, "max": None, "mean": None}, 2) == "—"
    assert R._window_cell({"window": None, "anchor": 0.687}, 1) == "якорь 68,7 %"


@tact
def test_variants_on_the_keys_the_carry_rewrites_are_listed_and_closed_quarter_keys_of_the_premium_are_named():
    """Справочные варианты книги об уровнях: подмена, которая ложится на ключ, переписанный переносом (ключ
    уровня маржи, цель передачи, ближний путь — ключом или целиком, ключ спреда от ставки якоря), названа с
    путями; подмена по ключу, которого перенос не трогал (LT-спред книги, премия), — нет. Ключи закрытого
    квартала премии роста названы: новая книга их не читает."""
    X = copy.deepcopy(scene().cand.data)
    X["valuation"]["reference_variants"] = [
        {"id": "no_near_shift", "title": "ближнего сдвига нет", "overrides": {R.NEAR: {"LT": 0.0}}},
        {"id": "q3_gap_stays", "title": "расхождение не сходит", "overrides": {f"{R.NEAR}.2027": -0.004, f"{R.NEAR}.LT": -0.004}},
        {"id": "transmission_structural", "title": "передача на уровне структурной оценки", "overrides": {R.T_TARGET: 0.12}},
        {"id": "wholesale_bond", "title": "фондирование по облигационной ставке",
         "overrides": {"nii.books.wholesale.spread.LT": 0.015}},
        {"id": "wholesale_path", "title": "спред фондирования целиком", "overrides": {"nii.books.wholesale.spread": {"LT": 0.015}}},
        {"id": "window_level_in_modal_cell", "title": "уровень окна — в модальной клетке",
         "overrides": {R.NIM_TARGET: 0.1004, R.LEVEL_WORLD: "H", R.PHI_SPLIT: 0.17}},
        {"id": "funds_premium_facts", "title": "премия на уровне фактов", "overrides": {f"{PREMIUM}.retail.2027": -0.034}}]
    changes = [(("nii", "nim_lt_target_mgmt"), 0.111, 0.1121), (("nii", "transmission", "target"), 0.06, 0.0601),
               (("nii", "phi_split"), 0.62, 0.621), (("regimes", "near_nim_shift", "2027"), -0.001, -0.0012),
               (("regimes", "near_nim_shift", "2027Q1"), None, -0.002), (("nii", "books", "wholesale", "spread", "2026"), -0.003, -0.0031),
               (("meta", "anchor_period"), "a", "b")]
    note = R.variant_note(X, changes)
    for fragment in (f"«no_near_shift» — `{R.NEAR}`", f"«q3_gap_stays» — `{R.NEAR}.2027`",
                     f"«transmission_structural» — `{R.T_TARGET}`", "«wholesale_path» — `nii.books.wholesale.spread`",
                     f"«window_level_in_modal_cell» — `{R.NIM_TARGET}`, `{R.PHI_SPLIT}`", "инструмент их не трогает",
                     "пересчитать на новом якоре"):
        assert fragment in note, fragment
    assert "wholesale_bond" not in note and "funds_premium_facts" not in note and f"`{R.NEAR}.LT`" not in note
    assert R.LEVEL_WORLD not in note, "мир уровня перенос не переписывает"
    # ключи закрытого квартала премии роста: книга, которая пишет год якоря кварталами
    X["volumes"]["funds_share_drift"] = {"retail": {"2026Q3": -0.12, "2026Q4": -0.03, "2027": 0.0, "LT": 0.0},
                                         "corporate": {"2026Q3": -0.10, "2026Q4": -0.02, "2027": 0.0, "LT": 0.0}}
    quarters = R.premium_note(X, "2026Q3", "2026Q4")
    assert quarters.startswith("премия роста к сектору — суждение книги") and R.PREMIUM_FACTS not in quarters
    X["valuation"]["reverse_dcf"]["premium_facts"] = [f"{PREMIUM}.retail.2026Q3"]
    assert f"снять (вместе с их записями в `{R.PREMIUM_FACTS}`)" in R.premium_note(X, "2026Q3", "2026Q4")
    assert f"Ключи закрытого квартала ({PREMIUM}.corporate.2026Q3, {PREMIUM}.retail.2026Q3) новая книга не читает" in quarters
    assert "2026Q4)" not in quarters and "по правилу книги от фактов закрытых месяцев" in quarters
    X["valuation"]["uncertainty"]["axes"].append({
        "name": "премия средств", "kind": "bundle", "paths": [f"{PREMIUM}.retail.2027"],
        "low": {f"{PREMIUM}.retail.2027": -0.05}, "high": {f"{PREMIUM}.retail.2027": 0.05}})
    both = R.premium_note(X, "2026Q3", "2026Q4")
    assert "«премия средств»" in both and "Ключи закрытого квартала" in both and "оставшиеся кварталы года" in both
    later = R.premium_note(X, "2026Q4", "2027Q1")
    assert f"{PREMIUM}.retail.2026Q4" in later and "2026Q3" not in later, "назван ключ закрытого квартала — и только он"
    assert "Ключи закрытого квартала" not in R.premium_note(X, "2027Q1", "2027Q2")


# ------------------------------------------------------------------ ручные шаги — по книге


TEMPLATE = '''# Метки комментариев:
#   ВЫВЕДЕНО НА ЯДРЕ — число зависит от пути баланса клетки: его вывела одна команда
meta:
  version: "1"                       # версия
nii:
  nim_lt_target_mgmt: 0.1            # A-N2: ключ цели [Р]
                                     #   ВЫВЕДЕНО НА ЯДРЕ 01.01.2026 — лист вывода; число заморожено
  sigma0_split: 1.0                  # ВЫВОДИТСЯ НА ЯДРЕ — до вывода
  transmission:
    target: 0.03                     # суждение
regimes:
  near_nim_shift: {"2026Q3": -0.003, LT: 0.0}
                                     # ближний сдвиг
                                     #   ВЫВЕДЕНО НА ЯДРЕ — путь года якоря
volumes:
  funds_share_drift:                 # премия средств клиентов — суждение книги
    retail: {"2026": 0.01, LT: 0.0}
  # ВЫВЕДЕНО НА ЯДРЕ — заголовок следующего ключа, а не комментарий ключа retail
  lt_from: 2033
# раздел оценки: слова ВЫВЕДЕНО НА ЯДРЕ в заголовке раздела ключам не принадлежат
valuation:
  axes:
    - {name: "связка", kind: bundle}   # концы оси — ВЫВЕДЕНО НА ЯДРЕ для своего конца
  erp: 0.05
'''


@tact
def test_numbers_derived_on_the_core_are_read_from_the_marks_of_the_book():
    """Перечень чисел, выведенных на ядре, — по самой книге: ключи шаблона с пометкой на своей строке или на
    строках-продолжениях комментария. Легенда, заголовок раздела, заголовок следующего ключа и комментарий
    элемента списка ключу не принадлежат. В шаблоне книги эмитента премия роста средств клиентов среди них не
    стоит: она — суждение."""
    assert R.derived_on_core(TEMPLATE) == ["nii.nim_lt_target_mgmt", "nii.sigma0_split", "regimes.near_nim_shift"]
    assert R.derived_on_core("meta:\n  version: 1\n") == []
    if R.TEMPLATE.exists():
        template = R.TEMPLATE.read_text(encoding="utf-8")
        marked = R.derived_on_core(template)
        assert R.NEAR in marked, marked
        # ключ цели ЧПМ выведен на ядре, пока суждение о марже записано не им (образец). У книги с ключом мира уровня
        # он — само суждение; у книги Совкомбанка — запись суждения в определении банка (уровень мира N) в единицах
        # ядра, выведенная точным мостом (пометка «ВЫВЕДЕНО НА ЯДРЕ», шаг bridge листа вывода): обе формы допустимы
        own = R._get(R.yaml.safe_load(template), R.LEVEL_WORLD) is not None
        assert own or R.NIM_TARGET in marked, (own, marked)
        assert not any(R._under(key, R.PREMIUMS) for key in marked), marked


def manual_case() -> tuple[dict, list]:
    """Кандидат общей формы с ключами второй формы и перечень того, что перенос изменил."""
    X = copy.deepcopy(scene().cand.data)
    X["checks"]["cir_lt"] = {"target": 0.47, "tolerance": 0.01, "from_year": 2033, "scope": R.MARKET_LAYER}
    X["checks"]["wholesale_share"] = [0.08, 0.30]
    X["valuation"]["reference_variants"] = [
        {"id": "kappa0", "title": "κ = 0", "overrides": {"credit.kappa": 0.0, "opex.real_growth.2027": 0.01}},
        {"id": "window_h", "title": "уровень окна — в модальной клетке мира-опоры",
         "overrides": {R.NIM_TARGET: 0.06, f"{R.NEAR}.2027": 0.0, "regimes.crisis.one_off_loss": {"period": "2027Q1"}}}]
    X["volumes"]["funds_share_drift"] = {"retail": {"2026": 0.01, "2027": 0.0, "2028": 0.0, "LT": 0.0, "LT_from": 2032}}
    X["valuation"]["uncertainty"]["axes"].append({
        "name": "премия средств", "kind": "bundle", "paths": [f"{PREMIUM}.retail.2027", f"{PREMIUM}.retail.2028"],
        "low": {f"{PREMIUM}.retail.2027": -0.05, f"{PREMIUM}.retail.2028": -0.05},
        "high": {f"{PREMIUM}.retail.2027": 0.05, f"{PREMIUM}.retail.2028": 0.05}})
    changes = [(("nii", "nim_lt_target_mgmt"), 0.06, 0.061), (("regimes", "near_nim_shift", "2027"), None, 0.001),
               (("regimes", "crisis", "one_off_loss", "period"), "2027Q1", "2028Q1"), (("meta", "anchor_period"), "a", "b")]
    return X, changes


@tact
def test_manual_steps_name_what_the_keys_of_the_book_require():
    """Ручные шаги — по ключам книги. Числа, выведенные на ядре: перечень из пометок шаблона, что из него перенос
    переписал (запись, а не вывод), оси по этим ключам, коридор оптового фондирования. Справочные варианты:
    названы подмены по переписанным ключам. Ось-связка премии роста: не тронута, назван ключ года. Область цели
    C/I — слой. У книги без этих ключей шаги — как у панели-образца."""
    s = scene()
    plain = R.manual_steps(s.book, s.cand.data, changes=s.cand.changes)
    words = ("выведенные на ядре", "справочные варианты", "премия роста", R.CIR_LT)
    assert not any(word in step for step in plain for word in words), plain
    X, changes = manual_case()
    marked = [R.NIM_TARGET, R.NEAR, "opex.real_growth"]
    steps = R.manual_steps(s.book, X, marked=marked, changes=changes, first_new="2026Q4")
    (derived,) = [w for w in steps if "выведенные на ядре" in w]
    assert all(f"`{key}`" in derived for key in marked) and "пометка «ВЫВЕДЕНО НА ЯДРЕ»" in derived
    assert f"переписал на новый якорь `{R.NIM_TARGET}`, `{R.NEAR}` (" in derived, "запись прежнего числа, не новый вывод"
    assert PREMIUM not in derived and "премия" not in derived, "премия роста средств клиентов — суждение, не вывод"
    assert "«ЧПМ сквозь цикл (A-N2)»" in derived and f"коридор `{R.WHOLESALE_SHARE}`" in derived
    assert "листом книги в его порядке" in derived and "«суждения книги»" in derived
    (variants,) = [w for w in steps if w.startswith("справочные варианты")]
    assert f"«window_h» — `{R.NIM_TARGET}`, `{R.NEAR}.2027`, `regimes.crisis.one_off_loss`" in variants
    assert "kappa0" not in variants and "инструмент их не трогает" in variants
    assert X["valuation"]["reference_variants"][1]["overrides"][R.NIM_TARGET] == 0.06
    (premium,) = [w for w in steps if w.startswith("премия роста")]
    assert "«премия средств»" in premium and "Ключ 2026 года" in premium and "оставшиеся кварталы года" in premium
    later = R.premium_note(X, "2026Q4", "2027Q1")
    assert "Первым прогнозным стал 2027 год" in later and f"{PREMIUM}.retail.2027" in later and "решение книги" in later
    assert any(w.startswith(R.CIR_LT) and R.MARKET_LAYER in w and "opex.real_growth" in w for w in steps)
    # без пометок шаблона: общими словами — и только у книги с ростом, ограниченным капиталом
    assert R.derived_note(s.book, X, None, changes) is None and R.derived_note(s.book, X, [], changes) is None
    untouched = R.derived_note(s.book, X, ["opex.real_growth"], changes)
    assert "Перенос якоря их не трогает." in untouched and "переписал" not in untouched
    assert R.variant_note(X, [(("meta", "version"), "1", "2")]) is None
    assert R.premium_note(s.cand.data, "2026Q3", "2026Q4") is None, "нет связки по премии — нет и шага"


# ------------------------------------------------------------------ форма панели с ключами второй формы


@lru_cache(maxsize=None)
def t_scene() -> SimpleNamespace:
    """Сухой прогон на фикстуре формы панели, которой подменой даны ключи второй формы: мир-опора κ, гейты целей
    (стационарная маржа, печатаемая маржа, C/I по слою), узел уровней, справочные варианты, ось-связка премии."""
    facts, data = t_facts(), t_dict()
    for path, value in NO_CATCH_UP:
        put(data, path, value)
    ctx = make_context(book_from_dict(data, facts=facts), facts)
    level = round(ctx.bridge.to_mgmt_nim(ctx.transmission.nss[REF]), 6)
    keys = {R.KAPPA_WORLD: REF,
            R.NIM_STATIONARY: {"world": REF, "target": level, "tolerance": 0.0005},
            "checks.nim_lt": {"target": 0.1076, "tolerance": 0.001, "from_year": 2030},
            R.CIR_LT: {"target": 0.47, "tolerance": 0.01, "from_year": 2033, "scope": R.MARKET_LAYER},
            R.WINDOW_BACKTEST: {"from_year": 2030, "cor": [0.0, 1.0], "cir": [0.0, 1.0]},
            R.VARIANTS: [{"id": "kappa0", "title": "κ = 0", "overrides": {"credit.kappa": 0.0}},
                         {"id": "window_h", "title": "уровень окна — в модальной клетке мира-опоры",
                          "overrides": {R.NIM_TARGET: 0.105}}]}
    for path, value in keys.items():
        put(data, path, value)
    paths = [f"{PREMIUM}.retail.2027", f"{PREMIUM}.corporate.2027"]
    center = {p: R._leaf(data, p) for p in paths}
    data["valuation"]["uncertainty"]["axes"].append({
        "name": "Премия роста средств клиентов", "kind": "bundle", "paths": paths, "dist": "triangular",
        "low": {p: center[p] - 0.05 for p in paths}, "high": {p: center[p] + 0.05 for p in paths}})
    s = scene_of(book_from_dict(data, facts=facts), facts)
    s.keys, s.axis = keys, copy.deepcopy(data["valuation"]["uncertainty"]["axes"][-1])
    return s


@ci_only
def test_the_quarterly_form_with_the_new_keys_keeps_the_invariant():
    """Форма панели с миром-опорой κ: клетки на своём пути сохраняют стоимость против прежней книги без добавки
    закрытого квартала — и там, где рост ограничен капиталом (добавка меняет прибыль, капитал и рост: ближняя
    калибровка ЧПМ не должна подгонять кандидата под путь, которого у него нет)."""
    s = t_scene()
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=T_CELLS)
    assert mech["history"] and mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 5, mech["rows"]
    moved = {r["key"][0]: r["history"] for r in mech["rows"]}
    assert moved[REF] == 0.0 and all(v != 0.0 for w, v in moved.items() if w != REF), moved
    assert not any("не сошлась" in w for w in s.cand.warnings)


@ci_only
def test_the_quarterly_form_with_the_level_world_keeps_the_invariant_and_its_gate_silent():
    """Форма панели в записи с миром уровня (и миром-опорой κ): ключ — стационарная маржа мира окна на составе
    якоря; клетки на своём пути сохраняют стоимость и там, где рост ограничен капиталом; ключ кандидата равен
    стационарной марже мира уровня по счёту ядра, гейт стационарной маржи в том же мире молчит; подмена
    справочного варианта по ключу уровня названа; строка уточнения корня по ключу уровня — прежняя; окно фактов
    книги не тронуто, упр. числа квартала отчёта стоят рядом с его краями, доля кредитов якоря в строке окна
    узла уровней — уже нового якоря."""
    facts, data = t_facts(), t_dict()
    for path, value in NO_CATCH_UP:
        put(data, path, value)
    ctx = make_context(book_from_dict(data, facts=facts), facts)
    key = round(ctx.bridge.to_mgmt_nim(ctx.transmission.nss[REF]), 6)
    shift = key - float(R._get(data, R.NIM_TARGET))
    for path, value in {R.KAPPA_WORLD: REF, R.LEVEL_WORLD: REF, R.NIM_TARGET: key,
                        R.NIM_STATIONARY: {"world": REF, "target": key, "tolerance": 0.0005},
                        R.WINDOW_BACKTEST: {"from_year": 2030, "cor": [0.0, 1.0], "cir": [0.0, 1.0], "nim": [0.10, 0.116],
                                            "means": {"nim": 0.1075, "cor": 0.057, "cir": 0.47}, "loans_share": 0.636},
                        R.REFINE_ROWS: [R.NIM_TARGET],
                        R.VARIANTS: [{"id": "window_h", "title": "уровень окна — в модальной клетке мира-опоры",
                                      "overrides": {R.NIM_TARGET: round(key - 0.01, 6)}}]}.items():
        put(data, path, value)
    window = copy.deepcopy(R._get(data, R.WINDOW_BACKTEST))
    for _, axes, keys in R._axis_lists(data):
        for axis in axes:
            if axis.get("paths") == [R.NIM_TARGET]:
                R._move_axis(axis, keys, lambda v: round(v + shift, 6))
    s = scene_of(book_from_dict(data, facts=facts), facts)
    old, new = s.run_plus.ctx, s.run_e.ctx
    assert R._sigmas(new.transmission) == pytest.approx(R._sigmas(old.transmission), abs=2e-6)
    lv = s.cand.derived["level"]
    assert lv["key"][0] == key != lv["key"][1] and lv["value"] == pytest.approx(lv["key"], abs=R.LEVEL_TOL)
    assert s.cand.data["checks"]["nim_stationary"] == {"world": REF, "target": lv["key"][1], "tolerance": 0.0005}
    checks = R.core_checks(s.run_e, s.v)
    assert checks["error"] is None and checks["invariants"] == [] and "nim_stationary" not in checks["gates"]
    mech = R.cell_mechanics(s.book, s.facts, s.run_plus, s.obs, s.v, cells=T_CELLS)
    assert mech["history"] and mech["ok"] and abs(mech["worst"]["rel"]) <= R.MECHANICS_TOL / 5, mech["rows"]
    assert not any("не сошлась" in w for w in s.cand.warnings)
    (variants,) = [w for w in s.cand.warnings if w.startswith("справочные варианты")]
    assert f"«window_h» — `{R.NIM_TARGET}`" in variants
    assert sum(w.startswith(R.NIM_TARGET + " — уровень маржи") for w in s.cand.warnings) == 1
    assert R._get(s.cand.data, R.REFINE_ROWS) == [R.NIM_TARGET] and R._get(s.cand.data, R.WINDOW_BACKTEST) == window
    (note,) = [w for w in s.cand.warnings if w.startswith("окно фактов")]
    assert f"Квартал отчёта {s.period}, упр.: ЧПМ {R._pct(s.expected['mgmt']['nim'])} — " in note
    was = R.core_checks(s.run_a, s.v)
    share = [c["levels"]["window"]["loans_share"] for c in (was, checks)]
    assert share[0]["window"] == share[1]["window"] == 0.636 and share[0]["anchor"] != share[1]["anchor"]
    text = "\n".join(R.target_lines(was, checks))
    assert ("| Окно фактов книги: наименьший…наибольший квартал | 10,00 %…11,60 %, среднее 10,75 % |" in text
            and f"окно 63,6 %, якорь {R._pct(share[0]['anchor'], 1)} → {R._pct(share[1]['anchor'], 1)} |" in text), text


@ci_only
def test_the_candidate_of_the_quarterly_form_carries_judgements_untouched_and_names_them():
    """Суждения книги перенос не трогает: цели и допуски гейтов, подмены справочных вариантов, ключи премии роста и
    концы её оси-связки. Каждое названо в ручных шагах; числа гейтов-целей и уровни после фазы роста печатаются
    до и после."""
    s = t_scene()
    X = s.cand.data
    for path in (R.NIM_STATIONARY, "checks.nim_lt", R.CIR_LT, R.WINDOW_BACKTEST, R.VARIANTS, R.KAPPA_WORLD):
        assert R._leaf(X, path) == s.keys[path], path
    assert X["valuation"]["uncertainty"]["axes"][-1] == s.axis
    assert X["volumes"]["funds_share_drift"] == s.book.source["volumes"]["funds_share_drift"]
    starts = {"справочные варианты": "«window_h»", "премия роста": "«Премия роста средств клиентов»",
              R.CIR_LT: R.MARKET_LAYER, R.NIM_STATIONARY: "Порядок: (1)", "числа книги, выведенные на ядре": "README"}
    for start, fragment in starts.items():
        (note,) = [w for w in s.cand.warnings if w.startswith(start)]
        assert fragment in note, note
    (variants,) = [w for w in s.cand.warnings if w.startswith("справочные варианты")]
    assert "kappa0" not in variants
    was, now = R.core_checks(s.run_a, s.v), R.core_checks(s.run_e, s.v)
    assert now["error"] is None and set(now["targets"]) == {"nim_stationary", "nim_lt", "cir_lt"}
    printed = now["targets"]["nim_lt"]
    assert printed["engine"] == pytest.approx(s.run_e.ctx.bridge.to_engine_nim(printed["value"]))
    assert set(now["levels"]["rows"]) == {"modal_cell", "analytical", "point", "macro_neutral"}
    result = R.attribution(s.book, s.facts, s.expected, valuation_date=s.v, cells=False,
                           marked=[R.NIM_TARGET, "opex.real_growth"])
    text = R.report_text(s.book, result)
    for fragment in ("Цели книги, которые сверяют её гейты", "| `nim_stationary` |", "| `cir_lt` |", "| `nim_lt` |",
                     "Сдвиг числа `nim_lt`:", "Сдвиг числа `nim_stationary`:", "Уровни после фазы роста",
                     "| Рыночные ставки как есть |", "(история до сетки — общая для миров)",
                     f"выведенные на ядре (в шаблоне — пометка «ВЫВЕДЕНО НА ЯДРЕ»): `{R.NIM_TARGET}`, `opex.real_growth`",
                     "у гейта знака стресса — под вероятностями точки"):
        assert fragment in text, fragment
    assert "Сдвиг числа `cir_lt`" not in text and "п.п.." not in text
