# -*- coding: utf-8 -*-
"""Контрольная модель: ключи четвёртого прохода ядра Совкомбанка (core-pass4) своим счётом.

Ключи (решения ведущего № 5; методика — spec.yaml прохода 4, пример — tests/fixtures/core_pass4/example.json, копия примера
методики; книга ключей — tests/fixtures/core_pass4/book_keys_pass4.yaml, копия фрагмента книги методики, тест сливает её с
книгой репозитория):

* Р5-4 — сложение связок (`valuation.uncertainty.bundle_compose: additive`): несколько осей-связок двигают один путь
  слагаемыми «конец − центр», центр — значение пути в корневой книге. Полосы у контрольной модели нет: правило М§10 она
  читает своей функцией `c_bundle_draw` (подмены при положениях осей) и `c_bundle_corners` (углы общих путей); подмены
  сверяются с ядром на точках гиперкуба, книга угла (все связки на ±1) считается обычной сеткой и сверяется с ядром
  в допусках C§5.
* Р5-5 — драйвер RWA гарантий — компонента смеси базы комиссий (`capital.rwa.guarantees.driver: fees_component`,
  `…component`).
* Р5-6 — корень комиссий и страхования множителем (`volumes.line_root_form: multiplicative`).

Без ключей контрольная модель считает бит в бит прежние числа — это держит сводка (tests/independent_model.py на книге
репозитория) и тесты «ключ нейтрален» ниже. Сверка с ядром (метка ci_only) требует ядра с проходом 4: нет ядра, его
функции или ключа в схеме ядра — провал, не пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import functools
import importlib
import itertools
import json
import math
import operator
import random

import pytest
import yaml

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
    from tests import test_control_t as tct
    from tests import test_control_pass1 as tp1
    from tests import test_control_pass2 as tp2
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_t as tct                        # type: ignore[no-redef]
    import test_control_pass1 as tp1                    # type: ignore[no-redef]
    import test_control_pass2 as tp2                    # type: ignore[no-redef]

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass4"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass4.yaml"
CELLS = tp2.CELLS
UNC = "valuation.uncertainty"
DRAWS = 20                     # точек гиперкуба сверки подмен с ядром (spec.yaml прохода 4: 20 точек)
DRAW_TOL = 1e-15               # подмены: относительная разность к масштабу слагаемых пути

rel, close, cells_of, numbers, put = tp2.rel, tp2.close, tp2.cells_of, tp2.numbers, tp2.put


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _str_keys(node):
    """Ключи года фрагмента (YAML-числа) → строки, как в книге репозитория."""
    if isinstance(node, dict):
        return {(str(k) if isinstance(k, int) and not isinstance(k, bool) else k): _str_keys(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_str_keys(x) for x in node]
    return node


def keyed_book(book: dict) -> dict:
    """Книга с ключами прохода 4 в центре: книга репозитория + фрагмент методики. Скаляры и траектории фрагмента
    заменяют свои узлы; оси — по первому пути, имени или набору путей (новая ось — в конец списка); справочные варианты
    фрагмента книге сверки
    не нужны (контрольная модель их не читает)."""
    if _book_carries_pass4_keys(book):
        # книга репозитория уже несёт ключи прохода 4 (интеграция круга 5): книга ключей — она сама; фрагмент методики
        # снят с книги c709f22 (ось базы страхования круга 4 — mix.retail / mix.loans) и к книге круга 5 не прикладывается
        return copy.deepcopy(book)
    frag = _str_keys(yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8")))
    out = copy.deepcopy(book)

    def merge(dst: dict, src: dict, path: str):
        for k, v in src.items():
            here = f"{path}.{k}" if path else str(k)
            if here == f"{UNC}.axes":
                axes = dst.setdefault("axes", [])
                for ax in v:
                    idx = [i for i, a in enumerate(axes) if a["paths"][0] == ax["paths"][0] or a["name"] == ax["name"]
                           or set(a["paths"]) == set(ax["paths"])]
                    if idx:
                        axes[idx[0]] = copy.deepcopy(ax)
                    else:
                        axes.append(copy.deepcopy(ax))
            elif here == "valuation.reference_variants":
                continue
            elif isinstance(v, dict) and isinstance(dst.get(k), dict) and not _is_traj(v):
                merge(dst[k], v, here)
            else:
                dst[k] = copy.deepcopy(v)

    merge(out, frag, "")
    return out


def _book_carries_pass4_keys(book: dict) -> bool:
    """Все три ключа прохода 4 стоят в книге в центре: Р5-4 additive, Р5-5 fees_component, Р5-6 multiplicative."""
    def get(path):
        cur = book
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur
    return (get(f"{UNC}.bundle_compose") == "additive" and get("capital.rwa.guarantees.driver") == "fees_component"
            and get("volumes.line_root_form") == "multiplicative")


def _is_traj(node: dict) -> bool:
    return any(str(k) in ("LT", "LT_from") or str(k)[:4].isdigit() for k in node)


def axes_of(book: dict) -> list:
    return list(cm.c_bget(book, f"{UNC}.axes"))


def with_compose(book: dict, mode) -> dict:
    out = copy.deepcopy(book)
    if mode is tct.DROP:
        out["valuation"]["uncertainty"].pop("bundle_compose", None)
    else:
        out["valuation"]["uncertainty"]["bundle_compose"] = mode
    return out


def lhs_positions(book: dict, n: int) -> list[list[float]]:
    """Положения осей на n точках латинского гиперкуба книги по тексту М§10 (перестановки всех осей, затем u, затем
    треугольное s(u)) — вход сверки подмен, не допущение."""
    m = len(axes_of(book))
    rng = random.Random(cm.c_bget(book, f"{UNC}.seed"))
    perms = []
    for _ in range(m):
        p = list(range(n))
        rng.shuffle(p)
        perms.append(p)
    out = []
    for i in range(n):
        u = [(perms[j][i] + rng.random()) / n for j in range(m)]
        out.append([math.sqrt(2.0 * x) - 1.0 if x < 0.5 else 1.0 - math.sqrt(2.0 * (1.0 - x)) for x in u])
    return out


@pytest.fixture(scope="module")
def form():
    return tct.t_book(), tct.t_facts()


@pytest.fixture(scope="module")
def hist(form):
    """Факты формы панели с остатками книг на концах кварталов до якоря (база комиссий — смесь весов книг)."""
    book, facts = form
    return tp1.history_books(book, facts)


@pytest.fixture(scope="module")
def repo():
    return tcm._inputs()


# ============================================================================ Р5-4 — сложение связок


def example_axes(ex: dict) -> tuple[list, list]:
    """Оси примера bundle_sum (example.json): по одной оси на слагаемое, путь — путь примера, конец стороны s — из
    примера; другой конец в этих положениях не читается (NaN — громко, если прочтётся)."""
    path, axes, s = ex["path"], [], []
    for t in ex["terms"]:
        side = "high" if t["s"] >= 0 else "low"
        if t["kind"] == cm.AXIS_SHIFT:
            ax = {"name": t["axis"], "kind": cm.AXIS_SHIFT, "paths": [path], "low": math.nan, "high": math.nan}
            ax[side] = t["end"]
        else:
            ax = {"name": t["axis"], "kind": cm.AXIS_BUNDLE, "paths": [path], "low": {path: math.nan},
                  "high": {path: math.nan}}
            ax[side] = {path: t["end"]}
        axes.append(ax)
        s.append(t["s"])
    return axes, s


def path_book(path: str, value: float, compose=cm.COMPOSE_ADDITIVE) -> dict:
    """Книга из одного пути траектории (и ключа правила связок)."""
    head, key = path.rsplit(".", 1)
    book = {"valuation": {"uncertainty": {} if compose is None else {"bundle_compose": compose}}}
    cur = book
    for part in head.split("."):
        cur = cur.setdefault(part, {})
    cur.update({key: value, "LT": 0.0, "LT_from": 2030})
    return book


@pytest.mark.tact
def test_p4_bundle_example_by_own_code():
    """Пример bundle_sum своим кодом: путь opex.real_growth.2028 несут три связки (М13 s = −0,6, база страхования +0,3, база
    комиссий −1,0) и сдвиг уровня расходов (+0,5); значение — центр + сдвиг + Σ |s|(конец − центр) = 0,00686, приращения
    слагаемых — примера (1e-15); перестановка осей — те же биты; копия с подменой пути 0,0050 при центре корневой книги
    0,0039 — 0,00796 (подмена сохраняется целиком); без ключа — отказ общего пути."""
    ex = example()["bundle_sum"]
    axes, s = example_axes(ex)
    root = path_book(ex["path"], ex["centre"])
    value = cm.c_bundle_draw(root, axes, s)[ex["path"]]
    assert rel(value, ex["value"]) <= 1e-15
    for ax, sj, t in zip(axes, s, ex["terms"]):
        one = cm.c_bundle_draw(root, [ax], [sj])[ex["path"]]
        assert abs((one - ex["centre"]) - t["increment"]) <= 1e-18, t["axis"]
    for perm in itertools.permutations(range(len(axes))):
        assert cm.c_bundle_draw(root, [axes[i] for i in perm], [s[i] for i in perm])[ex["path"]] == value
    trial = path_book(ex["path"], ex["trial_centre"])
    assert rel(cm.c_bundle_draw(trial, axes, s, root=root)[ex["path"]], ex["trial_value"]) <= 1e-15
    with pytest.raises(cm.ControlInputError, match="bundle_compose"):
        cm.c_bundle_draw(path_book(ex["path"], ex["centre"], compose=None), axes, s)


@pytest.mark.tact
def test_p4_bundle_sum_is_exact_in_any_order():
    """Три связки с приращениями 1e16, 1, −1e16 на одном пути с центром 0: сумма — fsum, точная (1) при любом порядке
    осей; наивная сумма в части порядков дала бы 0."""
    path = "opex.real_growth.2028"
    ends = (1e16, 1.0, -1e16)
    axes = [{"name": f"ось {i}", "kind": cm.AXIS_BUNDLE, "paths": [path], "low": {path: 0.0}, "high": {path: e}}
            for i, e in enumerate(ends)]
    book = path_book(path, 0.0)
    for perm in itertools.permutations(range(3)):
        assert cm.c_bundle_draw(book, [axes[i] for i in perm], [1.0] * 3)[path] == 1.0
    naive = {functools.reduce(operator.add, (ends[i] for i in perm), 0.0) for perm in itertools.permutations(range(3))}
    assert naive != {1.0}


@pytest.mark.tact
def no_shared_bundles(axes: list) -> list:
    """Оси без общих путей у связок: связка, чей путь уже несёт связка выше по списку, уходит (вход теста)."""
    out, seen = [], set()
    for ax in axes:
        if ax["kind"] == cm.AXIS_BUNDLE:
            if seen & set(ax["paths"]):
                continue
            seen |= set(ax["paths"])
        out.append(ax)
    return out


def test_p4_bundle_zero_single_and_trial_centre(repo):
    """На осях книги репозитория без общих путей у связок: все s = 0 — значения книги бит в бит; ключ additive и без
    ключа — те же подмены бит в бит на 50 точках гиперкуба (путь одной связки — прежнее правило); на копии с подменой δ
    пути связки при ключе подмена сохраняется целиком (v − v_корня = δ при любом s), без ключа стягивается множителем
    (1 − |s|) — флаг F1 методики."""
    book, _ = repo
    plain = with_compose(book, tct.DROP)
    keyed = with_compose(book, cm.COMPOSE_ADDITIVE)
    axes = no_shared_bundles(axes_of(book))
    plain["valuation"]["uncertainty"]["axes"] = keyed["valuation"]["uncertainty"]["axes"] = axes
    zero = cm.c_bundle_draw(keyed, axes, [0.0] * len(axes))
    assert zero and all(v == cm.c_bnum(keyed, p) for p, v in zero.items())
    for s in lhs_positions(keyed, 50):
        assert cm.c_bundle_draw(keyed, axes, s) == cm.c_bundle_draw(plain, axes, s)
    j = next(i for i, a in enumerate(axes) if a["kind"] == cm.AXIS_BUNDLE)
    path = axes[j]["paths"][-1]
    delta = 0.01 * (abs(cm.c_bnum(book, path)) or 1.0)
    for sj in (-1.0, -0.4, 0.0, 0.7, 1.0):
        s = [0.0] * len(axes)
        s[j] = sj
        for root_book, kept in ((keyed, 1.0), (plain, 1.0 - abs(sj))):
            trial = cm.c_apply_overrides(root_book, {path: cm.c_bnum(root_book, path) + delta})
            v_root = cm.c_bundle_draw(root_book, axes, s)[path]
            v_trial = cm.c_bundle_draw(trial, axes, s, root=root_book)[path]
            assert close(v_trial - v_root, kept * delta, 1e-12), (sj, kept)


@pytest.mark.tact
def test_p4_bundle_refusals():
    """Отказы: общий путь двух связок без ключа (и при exclusive); общий путь связки с осью вида value или внутри словаря
    оси вида dict — при любом правиле; ключ null или вне перечня; концы связки не по её путям, путь повторяется, путь —
    LT_from или не число книги; число положений не равно числу осей; вид оси не из перечня."""
    path = "opex.real_growth.2028"
    two = [{"name": n, "kind": cm.AXIS_BUNDLE, "paths": [path], "low": {path: 0.0}, "high": {path: 0.01}}
           for n in ("a", "b")]
    for mode in (None, cm.COMPOSE_EXCLUSIVE):
        with pytest.raises(cm.ControlInputError, match="bundle_compose"):
            cm.c_bundle_draw(path_book(path, 0.004, compose=mode), two, [0.5, 0.5])
    assert cm.c_bundle_draw(path_book(path, 0.004), two, [0.5, 0.5])[path] == pytest.approx(0.004 + 2 * 0.5 * 0.006)
    value = {"name": "v", "kind": cm.AXIS_VALUE, "paths": [path], "low": 0.0, "high": 0.01}
    words = {"name": "d", "kind": cm.AXIS_DICT, "paths": ["opex.real_growth"], "low": {}, "high": {}}
    for mode in (None, cm.COMPOSE_ADDITIVE):
        for other in (value, words):
            with pytest.raises(cm.ControlInputError, match="value или dict"):
                cm.c_bundle_draw(path_book(path, 0.004, compose=mode), [two[0], other], [0.5, 0.0])
    for bad in (None, "sum", 1):
        book = path_book(path, 0.004)
        book["valuation"]["uncertainty"]["bundle_compose"] = bad
        with pytest.raises(cm.ControlInputError, match="bundle_compose"):
            cm.c_bundle_draw(book, two[:1], [0.5])
    broken = [dict(two[0], high={path: 0.01, "opex.real_growth.2029": 0.0}),
              dict(two[0], paths=[path, path]),
              dict(two[0], paths=["opex.real_growth.LT_from"], low={"opex.real_growth.LT_from": 0},
                   high={"opex.real_growth.LT_from": 1}),
              dict(two[0], paths=["opex.real_growth"], low={"opex.real_growth": 0.0}, high={"opex.real_growth": 0.01}),
              dict(two[0], kind="slider")]
    for ax in broken:
        with pytest.raises(cm.ControlInputError):
            cm.c_bundle_draw(path_book(path, 0.004), [ax], [0.5])
    with pytest.raises(cm.ControlInputError, match="положений"):
        cm.c_bundle_draw(path_book(path, 0.004), two, [0.5])


@pytest.mark.tact
def test_p4_bundle_corners_by_own_code():
    """Правило углов: у числа, которое несут две и более оси-приращения, углы — c + Σ min(0, Δ_low, Δ_high) и
    c + Σ max(0, Δ_low, Δ_high) (Δ связки — конец − центр, Δ сдвига — его конец); сдвиг траектории идёт в её ключи; число
    одной оси углов не имеет."""
    path, c = "opex.real_growth.2028", 0.0039
    book = path_book(path, c)
    book["opex"]["real_growth"]["2029"] = 0.0039
    a = {"name": "a", "kind": cm.AXIS_BUNDLE, "paths": [path], "low": {path: 0.0049}, "high": {path: 0.0029}}
    b = {"name": "b", "kind": cm.AXIS_BUNDLE, "paths": [path, "opex.real_growth.2029"],
         "low": {path: 0.0019, "opex.real_growth.2029": 0.0}, "high": {path: 0.0061, "opex.real_growth.2029": 0.01}}
    sh = {"name": "s", "kind": cm.AXIS_SHIFT, "paths": ["opex.real_growth"], "low": -0.0015, "high": 0.0066}
    corners = cm.c_bundle_corners(book, [a, b, sh])
    lo = c + min(0.0, 0.0049 - c, 0.0029 - c) + min(0.0, 0.0019 - c, 0.0061 - c) + min(0.0, -0.0015, 0.0066)
    hi = c + max(0.0, 0.0049 - c, 0.0029 - c) + max(0.0, 0.0019 - c, 0.0061 - c) + max(0.0, -0.0015, 0.0066)
    assert corners[path] == pytest.approx((lo, hi), rel=1e-15)
    assert corners["opex.real_growth.2029"] == pytest.approx((c - 0.0039 - 0.0015, c + 0.0061 + 0.0066), rel=1e-15)
    assert set(corners) == {path, "opex.real_growth.2029"}                  # LT несёт один сдвиг — углов нет
    assert path not in cm.c_bundle_corners(book, [a])


def test_p4_corners_of_the_keyed_book(repo):
    """Углы сложения осей на книге ключей (книга репозитория + фрагмент методики) и на книге репозитория с ключом: у
    каждого числа, которое несут две и более оси-приращения, наименьшее и наибольшее значение в области (веса драйвера
    расходов ≥ 0, CoR ≥ 0, доли смесей в [0; 1]); книги, где все такие числа стоят на нижнем, затем на верхнем углу,
    проходят проверки входа контрольной модели."""
    book, facts = repo
    for b in (keyed_book(book), with_compose(book, cm.COMPOSE_ADDITIVE)):
        corners = cm.c_bundle_corners(b, axes_of(b))
        assert corners, "общих путей нет — правилу углов нечего проверять"
        for p, (lo, hi) in corners.items():
            assert lo <= cm.c_bnum(b, p) <= hi, p
            if p.startswith("opex.volume_weights.") or ".cor." in p:
                assert lo >= 0.0, (p, lo)
            if ".mix." in p and p.endswith(".share"):
                assert 0.0 <= lo and hi <= 1.0, (p, lo, hi)
        for side in (0, 1):
            cm.c_control_context(cm.c_apply_overrides(b, {p: v[side] for p, v in corners.items()}), facts)


# ---------------------------------------------------------------------------- Р5-4: сверка с ядром (ci_only)


def core_modules():
    """Модули ядра для сверки подмен: книга и полоса; нет модуля или функции — провал."""
    try:
        book_mod = importlib.import_module("model.book")
        unc = importlib.import_module("model.uncertainty")
    except Exception as exc:
        pytest.fail(f"ядро не импортируется ({type(exc).__name__}: {exc}): сверять подмены не с чем")
    for mod, name in ((book_mod, "book_from_dict"), (book_mod, "load_facts"), (unc, "draw_overrides")):
        if not hasattr(mod, name):
            pytest.fail(f"в ядре нет {mod.__name__}.{name}: сверять подмены не с чем")
    return book_mod, unc


def core_book_of(book_mod, raw: dict, facts):
    try:
        return book_mod.book_from_dict(copy.deepcopy(raw), facts=facts)
    except Exception as exc:
        pytest.fail(f"ядро не приняло книгу (проход 4 в ядре?): {type(exc).__name__}: {str(exc)[:500]}")


def draw_gap(mine: dict, core_book, raw: dict) -> list[tuple]:
    """Расхождения подмен: число, своё, ядра, отношение к масштабу (значение книги, своё, ядра)."""
    out = []
    for p, v in mine.items():
        c = float(core_book.get(p))
        scale = max(abs(cm.c_bnum(raw, p)), abs(v), abs(c))
        if abs(v - c) > DRAW_TOL * scale:
            out.append((p, v, c, abs(v - c) / scale))
    return out


@pytest.mark.ci_only
def test_p4_bundle_draws_match_core(repo):
    """Подмены c_bundle_draw против draw_overrides ядра (листья книги после подмен) на 20 точках гиперкуба: книга ключей
    (общие пути связок, ключ additive), её копия с подменами ключа ЧПМ, CoR LT нормы и корня расходов 2028 года (центр
    приращения — корневая книга), книга репозитория без ключа (оси без общих путей у связок) и её копия (центр — сама
    копия) — до 1e-15 к масштабу."""
    book, _ = repo
    book_mod, unc = core_modules()
    core_facts = tcm._core_facts(book_mod)
    keyed = keyed_book(book)
    plain = with_compose(book, tct.DROP)
    plain["valuation"]["uncertainty"]["axes"] = no_shared_bundles(axes_of(plain))
    shifted = {"nii.nim_lt_target_mgmt": cm.c_bnum(keyed, "nii.nim_lt_target_mgmt") + 0.002,
               "regimes.norm.cor.LT": cm.c_bnum(keyed, "regimes.norm.cor.LT") + 0.002, "opex.real_growth.2028": 0.005}
    checked = 0
    for raw, ov in ((keyed, {}), (keyed, shifted), (plain, {}), (plain, shifted)):
        root = core_book_of(book_mod, raw, core_facts)
        trial = root.with_overrides(ov) if ov else root
        trial_raw = cm.c_apply_overrides(raw, ov)
        core_axes = list(root.get(f"{UNC}.axes"))
        for s in lhs_positions(raw, DRAWS):
            mine = cm.c_bundle_draw(trial_raw, axes_of(raw), s, root=raw)
            got = trial.with_overrides(unc.draw_overrides(trial, core_axes, s))
            bad = draw_gap(mine, got, trial_raw)
            assert not bad, bad[:10]
            checked += len(mine)
    assert checked > 0


def core_run_on(book_obj, core_facts):
    grid_mod = importlib.import_module("model.grid")
    try:
        return grid_mod.run_grid(book_obj, core_facts)
    except Exception as exc:
        pytest.fail(f"ядро не посчитало книгу — сверять не с чем: {type(exc).__name__}: {str(exc)[:500]}")


def reconcile_ok(run, ctl) -> None:
    """Сверка М§17 на ядре: строки вне допуска — только класс Р6-9 (`tcm.fail_off_rows`, Д16); V0 слоёв не совпадают до 1e-9."""
    tcm.fail_off_rows(run, ctl, tcm.compare_with_core(run, ctl))
    assert not tcm.exact_match(run, ctl)


@pytest.mark.ci_only
def test_p4_control_matches_core_on_the_keyed_book(repo):
    """Книга ключей (все три ключа прохода 4 в центре): вся сверка М§17 в допусках, V0 слоёв не совпадают до 1e-9.

    ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 8, Р8-9; ops/expected_counts.json → known_failures): на книге p3 @ 48f3ca2
    вне допуска 3 строки RWA гарантий конца 2027 (M/downturn/mid и strict) и 2028 (strict) — класс урезанного роста
    Р6-9 (годовая форма контроля в клетках урезанного роста). Сторож класса —
    tests/test_control_pass6.py::test_p6_control_rows_off_are_the_growth_cut_class[book] (книга ключей прохода 4 —
    сама книга репозитория: 612,52 против 606,27, 1,03 %)."""
    book, facts = repo
    keyed = keyed_book(book)
    ctl = cm.c_control_run(keyed, facts)
    run = tcm.core_run_of(keyed)
    reconcile_ok(run, ctl)


def corner_runs(repo, sign: float, *, growth_off: bool = False):
    """Книга угла (все связки книги ключей на конце sign, прочие оси — книга) у обеих моделей: (прогон ядра, прогон
    контроля). growth_off — у обеих ограничение роста капиталом выключено подменой одного пути
    capital.growth_constraint.enabled (проба причины: строки за урезанием роста)."""
    book, facts = repo
    book_mod, unc = core_modules()
    core_facts = tcm._core_facts(book_mod)
    keyed = keyed_book(book)
    axes = axes_of(keyed)
    root = core_book_of(book_mod, keyed, core_facts)
    core_axes = list(root.get(f"{UNC}.axes"))
    s = [sign if a["kind"] == cm.AXIS_BUNDLE else 0.0 for a in axes]
    corner = cm.c_apply_overrides(keyed, cm.c_bundle_draw(keyed, axes, s))
    base = keyed
    ov = dict(unc.draw_overrides(root, core_axes, s))
    if growth_off:
        corner = tct.put(corner, "capital.growth_constraint.enabled", False)
        base = tct.put(keyed, "capital.growth_constraint.enabled", False)
        ov["capital.growth_constraint.enabled"] = False
    ctl = cm.c_control_run(corner, facts, base_book=base)
    run = core_run_on(root.with_overrides(ov), core_facts)
    return run, ctl


# Известные расхождения контроля с ядром на тестовой книге угла +1 (решение ведущего 29.10.2026: числа книги не задевают,
# разбираются ноябрьской версией книги; долг — справочник панели, раздел долгов). strict: починка — снять метку.
XFAIL_CORNER_PLUS1_TV = pytest.mark.xfail(strict=True, reason=(
    "известное расхождение контроля с ядром на тестовой книге угла +1 круга 12: 3 строки «терминальная стоимость с "
    "капиталом» вне класса Р6-9 (M/downturn/schedule 5,0 %, M/downturn/mid 3,0 %, M/crisis/schedule 3,1 % при допуске "
    "3 %); группа tv не входит в строки за путём кредитов, без ограничения роста M/crisis/strict 5,3 %; числа книги не "
    "задевает — разбор ноябрьской версией книги"))


@pytest.mark.ci_only
@pytest.mark.parametrize("sign", [pytest.param(-1.0, id="s-1"),
                                  pytest.param(1.0, id="s+1", marks=XFAIL_CORNER_PLUS1_TV)])
def test_p4_corner_books_match_core(repo, sign):
    """Книга угла: все связки книги ключей на одном конце (прочие оси — книга). Контрольная модель считает книгу, которую
    дали её подмены, ядро — свою книгу с подменами полосы; сверка М§17 в допусках, прежних.

    ИЗВЕСТНЫЙ КРАСНЫЙ (решения ведущего № 6, Р6-9; ops/expected_counts.json → known_failures): на книге p3 @ 837590f угол +1
    — 23 строки вне допуска из 14 536 (RWA гарантий, рост баз комиссий и страхования, ведомая книга страховых, резерв по
    книгам; клетки M/downturn/schedule, mid, strict и M/crisis/schedule, годы 2032–2036), угол −1 — 4 из 14 449 (стоимость и
    цена клетки M/norm/schedule и M/downturn/schedule, 3,1–3,2 % при допуске 3 %). Причина — годовая форма контроля в
    клетках урезанного роста: рост урезан капиталом у обеих моделей во всех годах этих клеток, доля прироста кварталов —
    у контроля по профилю прибыли годовой строки; фактический рост года расходится до 0,9 п.п. и доля урезанного роста до
    0,007 (допуски 3 п.п. и 0,05), а строки за путём кредитов — уровни конца года и рост баз — копят разницу уровня кредитов
    к допускам 0,5 п.п., 1 % и 2 %; у клеток со стоимостью около четверти капитала (угол −1) 0,4 % уровня кредитов — 3,2 %
    стоимости. При выключенном ограничении роста у обеих моделей эти строки совпадают до машинной точности, а класс держит
    test_p4_corner_books_off_rows_are_the_growth_cut_class."""
    run, ctl = corner_runs(repo, sign)
    reconcile_ok(run, ctl)


# класс Р6-9 и строки за путём кредитов — в tests/test_control_model.py (сверки М§17 на ядре судят им же, Д16)
BEHIND_GROWTH = tcm.BEHIND_GROWTH
growth_cut_class = tcm.growth_cut_class


def cut_dividend_class(ctl, rows: list[dict], off: list[dict]) -> list[dict]:
    """Строки `off` (вне допуска за путём кредитов на книге без ограничения роста), которые НЕ объясняет класс «дивиденд
    срезан до запаса» (Д16; упрощение контроля в docs/CONTROL-MODEL.md: срезанный дивиденд равен малой разности запаса и
    повторяет расхождение норматива квартала; его строки судятся полом 0,3 п.п. × RWA квартала решения). Строка стоимости
    клетки (cell) или цены клетки на оставшуюся акцию (bb_s_price) объяснена, если рост и RWA этой клетки у моделей в
    допусках (строки growth_actual, cut_share, rwa клетки — все ok), а расхождение не больше суммы расхождений срезанных
    дивидендов клетки (строки div с меткой cut; у цены на акцию — та же сумма на акцию в обращении). Остальные строки —
    как есть. Угол −1 круга 12 (Д16): M/downturn — стоимость клетки 77,93 против 75,45 млрд ₽ (разность 2,476 одна в трёх
    сценариях) при срезанном дивиденде 2026 года 14,85 против 11,59 млрд."""
    per_share = 1000.0 / ctl["ctx"]["A"]["N_out"]
    stray = []
    for r in off:
        tag = r.get("cell")
        if r.get("group") not in ("cell", "bb_s_price") or tag is None or r["diff"] is None:
            stray.append(r)
            continue
        mine = [x for x in rows if x.get("cell") == tag]
        same = all(x["ok"] for x in mine if x.get("group") in ("growth_actual", "cut_share", "rwa"))
        dv = sum(abs(x["diff"]) for x in mine if x.get("group") == "div" and x.get("cut") and x["diff"] is not None)
        if not (same and dv > 0.0 and abs(r["diff"]) <= dv * (per_share if r["group"] == "bb_s_price" else 1.0)):
            stray.append(r)
    return stray



@pytest.mark.ci_only
@pytest.mark.parametrize("sign", [pytest.param(-1.0, id="s-1"),
                                  pytest.param(1.0, id="s+1", marks=XFAIL_CORNER_PLUS1_TV)])
def test_p4_corner_books_off_rows_are_the_growth_cut_class(repo, sign):
    """Сторож известного красного test_p4_corner_books_match_core (Р6-9): на книге угла все строки вне допуска — класс
    «годовая форма контроля в клетках урезанного роста» (growth_cut_class), иного расхождения нет; при выключенном
    ограничении роста у обеих моделей строки за путём кредитов (рост баз, RWA гарантий, опт, ведомая книга, деньги,
    резерв, стоимость и цена клетки, ROE терминала) — в допусках М§17, кроме стоимости и цены клетки, которые
    объясняет класс «дивиденд срезан до запаса» (`cut_dividend_class`, Д16)."""
    run, ctl = corner_runs(repo, sign)
    rows = tcm.compare_with_core(run, ctl)
    stray = growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
    run0, ctl0 = corner_runs(repo, sign, growth_off=True)
    rows0 = tcm.compare_with_core(run0, ctl0)
    off = cut_dividend_class(ctl0, rows0, [r for r in rows0 if not r["ok"] and r.get("group") in BEHIND_GROWTH])
    assert not off, tcm._fail_lines(off)


# ============================================================================ Р5-5 — драйвер RWA гарантий: компонента смеси


FEES_MIX = {"mix": {"corporate": {"share": 0.7, "base": {"corp_loans": 1.0}},
                    "retail": {"share": 0.3, "base": {"cards": 1.0, "cash_loans": 1.0, "auto": 1.0, "mortgage": 1.0}}}}


def with_component(book: dict, facts: dict, *, mix=None, component="corporate", driver="fees_component", link0=False):
    """Фикстура формы панели с гарантиями (tests/test_control_pass2.with_guarantees) и драйвером-компонентой; mix — база
    комиссий fees.volume_base (по умолчанию FEES_MIX, вход теста); component=None — поля нет."""
    b2, f2 = tp2.with_guarantees(book, facts, driver=driver, base=copy.deepcopy(FEES_MIX if mix is None else mix),
                                 link0=link0)
    if component is not None:
        b2["capital"]["rwa"]["guarantees"]["component"] = component
    return b2, f2


@pytest.mark.tact
def test_p4_k5_example_by_own_code(repo):
    """Пример k5 своим кодом на книге и фактах репозитория (драйвер fees_component, компонента corporate — {corp_loans: 1}):
    G_0 = (N_нф × CCF_нф + N_ф × CCF_ф) × вес (1e-12), D^G_0 — кредиты юрлиц якоря; G_q = G_0 × E_corp,q / E_corp,0 по
    кредитам юрлиц клетки примера (1e-12); остатки прочих книг на G не влияют; прочие компоненты и доли смеси — тоже."""
    book, facts = repo
    k5 = example()["k5"]
    b2 = copy.deepcopy(book)
    b2["capital"]["rwa"]["guarantees"].update(driver="fees_component", component="corporate")
    A = cm.c_anchor_state(b2, facts)
    B, _ = cm.c_resolve_anchor_keys(b2, A)
    books, dens = B["nii"]["books"], cm.c_bget(B, "capital.rwa.density")
    rule = cm.c_guarantee_rule(B, A, books, dens, cm.c_bopt(B, "volumes.link_base", "loans"))
    assert rel(rule["g0"], k5["G0"]) <= 1e-12
    assert rel(A["E0"]["corp_loans"], k5["E_corp_0"]) <= 1e-12
    loans = [b for b, sp in books.items() if sp.get("sector")]
    biz = cm.c_client_funds(books)
    assets = [b for b, sp in books.items() if sp["side"] == cm.LOANS_SIDE]
    for row in k5["rows"]:
        for scale in (1.0, 1.7):                                    # прочие книги — любые
            E = {b: v * scale for b, v in A["E0"].items()}
            E["corp_loans"] = row["E_corp_q"]
            lvl = cm.c_base_level(rule["spec"], E, loans=loans, biz=biz, assets=assets, nominal=1.0)
            assert rel(rule["g0"] * lvl / rule["d0"], row["G_q_component"]) <= 1e-12, row["q"]
    other = copy.deepcopy(b2)
    mix = other["fees"]["volume_base"]["mix"]
    for i, name in enumerate(mix):                                  # другие доли смеси — те же веса компоненты
        mix[name]["share"] = 1.0 if i == 0 else 0.0
    rule2 = cm.c_guarantee_rule(other, A, books, dens, "loans")
    assert rule2["spec"]["w"] == rule["spec"]["w"] and rule2["d0"] == rule["d0"]


def test_p4_k5_neutral_cases_are_bit_for_bit(form, hist):
    """G1–G3. Смесь из одной компоненты: fees_component ≡ fees_base бит в бит; смесь двух компонент на верхнем конце
    (доля компоненты 1) — то же; поле component при fees_base и fees_line не читается (даже неверное имя) — числа как без
    поля. На форме панели (связь комиссий фикстуры, база — смесь), клетки расчётов."""
    book, facts = form[0], hist
    one = {"mix": {"corporate": {"share": 1.0, "base": {"corp_loans": 1.0}}}}
    top = {"mix": {"corporate": {"share": 1.0, "base": {"corp_loans": 1.0}},
                   "retail": {"share": 0.0, "base": {"cards": 1.0, "cash_loans": 1.0, "auto": 1.0, "mortgage": 1.0}}}}
    for mix in (one, top):
        _, base = cells_of(*with_component(book, facts, mix=mix, driver="fees_base", component=None))
        _, comp = cells_of(*with_component(book, facts, mix=mix))
        for key in CELLS:
            assert numbers(comp[key]) == numbers(base[key]), key
    for driver in ("fees_base", "fees_line"):
        _, plain = cells_of(*with_component(book, facts, driver=driver, component=None))
        _, junk = cells_of(*with_component(book, facts, driver=driver, component="no_such_component"))
        for key in CELLS:
            assert numbers(junk[key]) == numbers(plain[key]), (driver, key)


def test_p4_k5_component_ignores_the_mix_shares(form, hist):
    """G4: G_q / E_corp,q = G_0 / E_corp,0 на концах лет и кварталов прохода капитала в клетках при двух разных долях смеси
    (связь комиссий фикстуры: доли меняют комиссии, прибыль и путь кредитов — но не отношение гарантий к кредитам юрлиц);
    у драйвера fees_base отношение от долей зависит."""
    book, facts = form[0], hist
    other = {"mix": {"corporate": {"share": 0.2, "base": {"corp_loans": 1.0}},
                     "retail": {"share": 0.8, "base": {"cards": 1.0, "cash_loans": 1.0, "auto": 1.0, "mortgage": 1.0}}}}
    seen = []
    for mix in (None, other):
        ctx, cells = cells_of(*with_component(book, facts, mix=mix))
        unit = ctx["guar"]["g0"] / ctx["A"]["E0"]["corp_loans"]
        for key in CELLS:
            for r in cells[key]["rows"]:
                assert rel(r["guar"] / r["books_end"]["corp_loans"], unit) <= 1e-12, key
        seen.append(cells)
    assert any(seen[0][k]["rows"][-1]["loans"] != seen[1][k]["rows"][-1]["loans"] for k in CELLS), \
        "доли смеси не меняют путь кредитов — проверка G4 вырождена"
    _, base = cells_of(*with_component(book, facts, driver="fees_base", component=None))
    assert any(not close(r["guar"] / r["books_end"]["corp_loans"], unit, 1e-6)
               for k in CELLS for r in base[k]["rows"])


def test_p4_k5_component_on_the_carved_book_is_no_key(form, hist):
    """G5, G6: компонента — сама книга выреза ({corp_loans: 1}): RWA якоря, RWA концов лет и кварталов, капитал и
    стоимость клеток — как без гарантий (1e-12, относительно)."""
    book, facts = form[0], hist
    ctx0, plain = cells_of(*tp2.with_guarantees(book, facts, enabled=False, base=copy.deepcopy(FEES_MIX), link0=False))
    ctx, comp = cells_of(*with_component(book, facts))
    assert rel(ctx["rwa0"], ctx0["rwa0"]) <= 1e-12
    for key in CELLS:
        assert rel(comp[key]["v_ri"], plain[key]["v_ri"]) <= 1e-12, key
        for r, r0 in zip(comp[key]["rows"], plain[key]["rows"]):
            assert rel(r["rwa"], r0["rwa"]) <= 1e-12 and rel(r["bv"], r0["bv"]) <= 1e-12, key
            for x, x0 in zip(r["quarters"], r0["quarters"]):
                assert rel(x["rwa"], x0["rwa"]) <= 1e-12, key


@pytest.mark.tact
def test_p4_k5_refusals(form, hist):
    """Отказы fees_component: нет поля component, имя — не строка или пустое; база комиссий — слово или веса книг (не
    смесь) или ключа нет; имени нет в смеси; смесь не проходит правил К2б (сумма долей не 1). Выключено — ключ не читается."""
    book, facts = form[0], hist
    bad = [with_component(book, facts, component=None), with_component(book, facts, component=7),
           with_component(book, facts, component=""), with_component(book, facts, mix="loans"),
           with_component(book, facts, mix={"corp_loans": 1.0}),
           with_component(book, facts, component="sme"),
           with_component(book, facts, mix={"mix": {"corporate": {"share": 0.6, "base": {"corp_loans": 1.0}}}})]
    b_none, f_none = with_component(book, facts)
    b_none["fees"].pop("volume_base")
    bad.append((b_none, f_none))
    for b, f in bad:
        with pytest.raises(cm.ControlInputError, match=r"capital\.rwa\.guarantees|fees\.volume_base"):
            cm.c_control_context(b, f)
    b_off, f_off = with_component(book, facts, component=None)
    b_off["capital"]["rwa"]["guarantees"]["enabled"] = False
    assert cm.c_control_context(b_off, f_off)["guar"] is None


# ============================================================================ Р5-6 — корень строки множителем


def with_root_form(book: dict, form_value) -> dict:
    return put(book, "volumes.line_root_form", form_value)


@pytest.mark.tact
def test_p4_mult_example_by_own_code():
    """Пример mult (клетка H/soft/mid ядра, кварталы 2027Q3–Q4): F_q = F_(q−4) × (1 + wage + связь × (v − wage)) × (1 +
    корень), v = A_q / A_(q−4) − 1 — комиссии и страхование (1e-12 к формуле и к ядру примера); при связи 0 множитель базы —
    1 + wage (I5)."""
    mult = example()["mult"]
    checked = 0
    for row in mult["rows"]:
        for line, link, r in (("fees", mult["link_fees"], row["r_fees"]), ("ins", mult["link_ins"], row["r_ins"])):
            node = row[line]
            if node["F_q_minus_4"] is None:
                continue
            v = node["A_q"] / node["A_q_minus_4"] - 1.0
            mine = node["F_q_minus_4"] * cm.c_base_factor(row["wage"], link, v) * (1.0 + r)
            assert rel(mine, node["F_q_mult_formula"]) <= 1e-12, (row["period"], line)
            assert rel(mine, node["F_q_mult_core"]) <= 1e-12, (row["period"], line)
            checked += 1
        assert cm.c_base_factor(row["wage"], 0.0, 0.3) == 1.0 + row["wage"]
        assert cm.c_base_factor(row["wage"], 1.0, None) == 1.0 + row["wage"]
    assert checked == 4


def test_p4_mult_neutral_cases_are_bit_for_bit(form):
    """I1, I2, I6: additive ≡ без ключа бит в бит; корни 0 (комиссии и страхование) — multiplicative ≡ additive бит в бит
    при связях фикстуры и при нулевых связях; год переопределения комиссий корня не несёт ни в одной форме: комиссии
    кварталов года — комиссии тех же кварталов прошлого года × (1 + переопределение) (1e-15)."""
    book, facts = form
    _, plain = cells_of(book, facts)
    _, add = cells_of(with_root_form(book, "additive"), facts)
    for key in CELLS:
        assert numbers(add[key]) == numbers(plain[key]), key
    zero = put(put(book, "fees.growth_vs_wages", {"LT": 0.0}), "other.insurance_growth_vs_wages", {"LT": 0.0})
    for z in (zero, put(put(zero, "fees.volume_link", 0.0), "other.insurance_volume_link", 0.0)):
        _, a = cells_of(with_root_form(z, "additive"), facts)
        _, m = cells_of(with_root_form(z, "multiplicative"), facts)
        for key in CELLS:
            assert numbers(m[key]) == numbers(a[key]), key
    y_ov = cm.c_per_parse(book["meta"]["anchor_period"])[0] + 2
    ov_book = put(book, "fees.growth_override", {str(y_ov): 0.05})
    for form_value in ("additive", "multiplicative"):
        ctx, cells = cells_of(with_root_form(ov_book, form_value), facts)
        years = [p["year"] for p in ctx["periods"]]
        for key in CELLS:
            by_year = dict(zip(years, cells[key]["rows"]))
            for f, f0 in zip(by_year[y_ov]["fees_q"], by_year[y_ov - 1]["fees_q"], strict=True):
                assert rel(f, f0 * 1.05) <= 1e-15, (form_value, key)


def class2_ratios(ctx: dict, cells: list, line: str) -> dict:
    """Отношение строки к средней её базы по годам клеток: {клетка: {год: строка / (кварталов × средняя базы)}}."""
    years = [p["year"] for p in ctx["periods"]]
    out = {}
    for c in cells:
        out[(c["world"], c["regime"], c["scenario"])] = {
            y: r[line] / (len(p["quarters"]) * r[f"vol_{line}"]) for y, p, r in zip(years, ctx["periods"], c["rows"])}
    return out


def test_p4_mult_class2_on_the_book(repo):
    """I3, I4 (класс 2) на книге репозитория со связями 1 и смесями баз: при множителе отношение строки к её базе в году
    якоря одно во всех 36 клетках (1e-12), а в годах, чей прошлый год — полный период сетки, растёт ровно на корень:
    отношение_Y / отношение_(Y−1) = 1 + корень_Y в каждой клетке (1e-12) — у комиссий и страхования. Без ключа (сумма)
    отношения расходятся между клетками и растут на корень / (1 + рост базы): проверка различает формы."""
    book, facts = repo
    # решения ведущего № 7, Р7-3: связь страхования книги 0,5 (доля «кредитного» страхования); тождество — о форме корня при
    # связи 1, поэтому книгу со связями 1 тест строит сам (прочие ключи — книги репозитория)
    book = copy.deepcopy(book)
    book["fees"]["volume_link"] = 1.0
    book["other"]["insurance_volume_link"] = 1.0
    for line, key in (("fees", "fees.volume_link"), ("ins", "other.insurance_volume_link")):
        assert cm.c_bnum(book, key) == 1.0, f"{key}: связь книги не 1 — тождество класса 2 не про эту книгу"
    traj = {"fees": cm.c_bget(book, "fees.growth_vs_wages"), "ins": cm.c_bget(book, "other.insurance_growth_vs_wages")}
    res = cm.c_control_run(with_root_form(book, "multiplicative"), facts)
    base = (tcm.shared_control() if not cm.c_root_mult(book)
            else cm.c_control_run(with_root_form(book, "additive"), facts))
    y0 = res["ctx"]["anchor"][0]
    for line in ("fees", "ins"):
        mult = class2_ratios(res["ctx"], res["cells"], line)
        add = class2_ratios(base["ctx"], base["cells"], line)
        first = [v[y0] for v in mult.values()]
        assert max(first) / min(first) - 1.0 <= 1e-12, line
        first_add = [v[y0] for v in add.values()]
        assert max(first_add) / min(first_add) - 1.0 > 1e-6, line
        worst_add = 0.0
        for cell, by_year in mult.items():
            for y in sorted(by_year):
                if y < y0 + 2:
                    continue
                root = cm.c_traj_mean(traj[line], y, range(1, cm.QY + 1))
                assert rel(by_year[y] / by_year[y - 1], 1.0 + root) <= 1e-12, (line, cell, y)
                worst_add = max(worst_add, rel(add[cell][y] / add[cell][y - 1], 1.0 + root))
        assert worst_add > 1e-6, line


@pytest.mark.tact
def test_p4_mult_refusals(form):
    """volumes.line_root_form: null или значение вне перечня — отказ; additive и нет ключа — сумма, multiplicative — множитель."""
    book, facts = form
    for bad in (None, "product", 1):
        with pytest.raises(cm.ControlInputError, match="line_root_form"):
            cm.c_root_mult(with_root_form(book, bad))
    assert cm.c_root_mult(book) is False and cm.c_root_mult(with_root_form(book, "additive")) is False
    assert cm.c_root_mult(with_root_form(book, "multiplicative")) is True
