# -*- coding: utf-8 -*-
"""Контрольная модель: ключ седьмого прохода ядра Совкомбанка (core-pass7) своим счётом.

Ключ (решения ведущего № 9, Р9-1; методика — spec.yaml прохода 7, пример — tests/fixtures/core_pass7/example.json, копия
примера методики; фрагмент книги — tests/fixtures/core_pass7/book_keys_pass7.yaml, копия фрагмента методики; числа ρ
фрагмента тест подставляет в книгу репозитория, пока она ключа не несёт; книгу с ключом тест судит её же ρ):

* Р9-1 — книга-обязательство за драйвером строки (К6, `volumes.liability_drivers`) несёт корень номинальной части по
  строке-драйверу (`volumes.liability_driver_roots` {fees, insurance → траектория ρ}): E_q = E_(q−1) (1 + w_q)^((1 − λ)/4)
  (D_q / D_(q−1))^λ (1 + ρ_q)^(1 − λ); λ — связь строки, D — база строки на конце квартала, ρ — общий для миров (кварталы
  до 2029К4, LT 0 с 2030 года). Ключ читается для ведомой книги, чья строка в нём есть, при активном К6; иначе — ключ
  неактивного режима, не отказ. Форма ключа проверяется всегда.

Без ключа контрольная модель считает бит в бит прежние числа — это держит сводка (tests/independent_model.py на книге
репозитория) и тесты «ключ нейтрален» ниже. Сверка с ядром (метка ci_only) с ключом требует ядра с проходом 7 — нет ядра,
его функции или ключа в схеме ядра — провал, не пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import functools
import json
import random
from fractions import Fraction

import pytest
import yaml

try:
    from tests import independent_model as cm
    from tests import test_control_model as tcm
    from tests import test_control_pass2 as tp2
    from tests import test_control_pass4 as tp4
except ImportError:                                     # pytest без пакета tests
    import independent_model as cm                      # type: ignore[no-redef]
    import test_control_model as tcm                    # type: ignore[no-redef]
    import test_control_pass2 as tp2                    # type: ignore[no-redef]
    import test_control_pass4 as tp4                    # type: ignore[no-redef]

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass7"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass7.yaml"
# интеграция круга 10: книга репозитория несёт форму строки прохода 8 — её κ и ρ корни г/г; для цепи К6 этого прохода — κ формы
# уровней и ρ цепи книги своего круга без ключа формы (неподвижная точка листа; круг 12 — сухой перевывод r12mixed)
MIXED_KEYS = cm.ROOT / "tests" / "fixtures" / "core_pass8" / "book_keys_mixed_r12.yaml"
KEY_HEAD, KEY = "volumes", "liability_driver_roots"
ROOTS = f"{KEY_HEAD}.{KEY}"
DRIVERS = "volumes.liability_drivers"
LINK_I = "other.insurance_volume_link"
LINK_AXIS = LINK_I                                       # первый путь связки оси связи страхования (Р7-3)
BASE_AXIS = "other.insurance_volume_base.mix.corporate.share"   # первый путь связки оси базы страхования (Р5-1)
LAYER_M = "macro_neutral"
NEUTRAL_UNTIL = 2029                                     # ρ — переход до 2029К4, с 2030 года 0
DROP = object()

rel, numbers = tp2.rel, tp2.numbers


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def fr(s: str) -> Fraction:
    return Fraction(s)


@functools.lru_cache(maxsize=None)
def _book_rho():
    """ρ страхования ключа книги репозитория (машинная книга каталога данных сверки) или None — книга ключа не несёт."""
    book, _ = tcm._inputs()
    return ((book.get(KEY_HEAD) or {}).get(KEY) or {}).get("insurance")


@functools.lru_cache(maxsize=None)
def _book_line() -> bool:
    """Книга репозитория несёт форму строки прохода 8 (volumes.line_link_form: line)."""
    book, _ = tcm._inputs()
    return (book.get(KEY_HEAD) or {}).get("line_link_form") == "line"


@functools.lru_cache(maxsize=None)
def _mixed() -> dict:
    return yaml.safe_load(MIXED_KEYS.read_text(encoding="utf-8"))


def rho() -> dict:
    """ρ страхования: ключ книги репозитория, если книга его уже несёт (поток книги ставит ρ, выведенный листом для этой
    книги), иначе — фрагмента методики (центр книги p3 @ 5e50bf9 с κ книги; 14 кварталов 2026Q3…2029Q4, LT 0 с 2030).
    Фрагмент — неподвижная точка правила листа только на своей книге: на книге другого круга без ключа слой M с ним у базы
    не держится (тест слоя M ниже краснеет — законный сигнал «ρ перевывести»), а книгу с ключом тест судит её же ρ."""
    if _book_line():                                  # ρ книги — корень г/г формы строки (проход 8): ρ цепи — фикстура круга 10
        return dict(_mixed()[KEY_HEAD][KEY]["insurance"])
    own = _book_rho()
    if own is not None:
        return copy.deepcopy(own)
    frag = yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8"))
    return dict(frag[KEY_HEAD][KEY]["insurance"])


def zero_rho() -> dict:
    """Те же ключи времени, ρ = 0 во всех кварталах (вариант k6_root_off: пути в связках целы)."""
    return {k: (v if k == "LT_from" else 0.0) for k, v in rho().items()}


def plain(book: dict) -> dict:
    """Книга без ключа Р9-1 (поток книги может его уже нести), без путей ρ в осях и без вариантов, подменяющих пути ρ."""
    out = copy.deepcopy(book)
    out[KEY_HEAD].pop(KEY, None)
    out[KEY_HEAD].pop("line_link_form", None)         # ключи прохода 8 (интеграция круга 10): прежние формы этого прохода
    out["checks"].pop("client_funds", None)
    (out["checks"].get("funds_cost_to_key") or {}).pop("scope", None)
    # интеграция круга 11: funds_scope: clients (проход 9) схема пускает только с client_funds: clients — снимается вместе с ним
    out.get("volumes", {}).pop("funds_scope", None)
    _val = out.get("valuation") or {}
    if isinstance(_val.get("reference_variants"), list):
        _val["reference_variants"] = [v for v in _val["reference_variants"]
                                      if "volumes.funds_scope" not in (v.get("overrides") or {})]
    if _book_line():                                  # κ книги — корень г/г формы строки: κ формы уровней — фикстура круга 10
        out["opex"]["line_share_roots"]["insurance"] = dict(_mixed()["opex"]["line_share_roots"]["insurance"])
    for ax in out["valuation"]["uncertainty"]["axes"]:
        if ax.get("kind") == cm.AXIS_BUNDLE and any(str(p).startswith(ROOTS + ".") for p in ax["paths"]):
            ax["paths"] = [p for p in ax["paths"] if not str(p).startswith(ROOTS + ".")]
            for end in ("low", "high"):
                ax[end] = {k: v for k, v in ax[end].items() if not str(k).startswith(ROOTS + ".")}
    val = out.get("valuation") or {}                  # и без справочных вариантов, подменяющих пути ρ (k6_root_off)
    if val.get("reference_variants"):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(str(k).startswith(ROOTS + ".") for k in (v.get("overrides") or {}))]
    return out


def keyed(book: dict, roots=DROP, **paths) -> dict:
    """Книга с ключом: ρ страхования `rho()` (roots — свой узел ключа целиком) и подмены точечных путей paths (ключ пути
    — точки через «__»)."""
    out = copy.deepcopy(book)
    out[KEY_HEAD][KEY] = {"insurance": rho()} if roots is DROP else copy.deepcopy(roots)
    for dotted, v in paths.items():
        out = tp2.put(out, dotted.replace("__", "."), v)
    return out


def put(book: dict, dotted: str, value) -> dict:
    return tp2.put(book, dotted, value)


def at_end(book: dict, first: str, which: str) -> dict:
    """Книга на конце связки оси (по первому пути): подмены конца."""
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0] == first)
    return cm.c_apply_overrides(book, dict(ax[which]))


def driven_book(book: dict) -> str:
    """Ведомая книга строки страхования (вход теста — книга репозитория ведёт одну книгу К6 этой строкой)."""
    books = [b for b, line in (book[KEY_HEAD].get("liability_drivers") or {}).items() if line == "insurance"]
    assert len(books) == 1, books
    return books[0]


def tag(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def years_of(ctl: dict) -> list[int]:
    return [p["year"] for p in ctl["ctx"]["periods"]]


def layer_p(ctl: dict, layer: str) -> dict:
    """Вероятности клеток слоя: вес мира слоя × вероятность режима × P(сценарий | режим) — как у слоёв модели."""
    ctx = ctl["ctx"]
    B = ctx["B"]
    lw = cm.c_layer_weights(B)[layer]
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")
    return {tag(c): lw.get(c["world"], 0.0) * ctx["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]])
            for c in ctl["cells"]}


def world_p(ctl: dict, world: str) -> dict:
    """Вероятности клеток мира (режим × сценарий)."""
    ctx = ctl["ctx"]
    prs = cm.c_bget(ctx["B"], "joint.reg_prob_given_regime")
    return {tag(c): ctx["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]])
            for c in ctl["cells"] if c["world"] == world}


def strip_levels(cell_numbers: list) -> list:
    """Числа клетки без печати D ведомых книг (поле driven_level кварталов есть только при ключе корня); копия — словари
    кварталов прогона общие с клеткой."""
    cell_numbers = copy.deepcopy(cell_numbers)
    for r in cell_numbers[1]:
        for x in r.get("quarters") or []:
            x.pop("driven_level", None)
    return cell_numbers


@pytest.fixture(scope="module")
def repo():
    book, facts = tcm._inputs()
    return plain(book), facts


@pytest.fixture(scope="module")
def runs(repo):
    """Прогоны книги репозитория без ключа и с ключом в центре (ρ `rho()`, связь страхования книги)."""
    book, facts = repo
    return cm.c_control_run(book, facts), cm.c_control_run(keyed(book), facts)


@pytest.fixture(scope="module")
def zero_run(repo):
    """Прогон книги с ключом ρ ≡ 0 (те же ключи времени): числа — прежние бит в бит, D ведомой книги — в печати."""
    book, facts = repo
    return cm.c_control_run(keyed(book, roots={"insurance": zero_rho()}), facts)


# ============================================================================ пример (формула и правило)


@pytest.mark.tact
def test_p7_example_formula_by_own_code():
    """Пример Р9-1 (example.json, formula) функцией c_driven_path (1e-12): цепь с корнем E_q при λ = ½ — точные дроби
    примера; телескоп (E_q / E_0)^2 = (D_q / D_0) N^ρ_q (запись примера N^ρ); связь 1 — корень не действует (бит в бит
    без корня); связь 0 — E_q / E_0 = N^ρ_q (1e-12); без корня и при ρ ≡ 0 — прежняя цепь бит в бит."""
    f = example()["formula"]
    lam, e0 = float(fr(f["lam"])), float(fr(f["E0"]))
    d = [float(fr(x)) for x in f["D"]]
    n = len(d) - 1
    wage = [float(fr(f["one_plus_w"])) - 1.0] * n
    roots = [float(fr(x)) - 1.0 for x in f["one_plus_rho"][1:]]
    path = cm.c_driven_path({"lam": lam}, e0, d, wage, roots)
    assert len(path) == n + 1 and path[0] == e0
    for q in range(n + 1):
        assert rel(path[q], float(fr(f["E"][q]))) <= 1e-12, q
        assert rel(path[q], f["E_float"][q]) <= 1e-12, q
        nr = float(fr(f["N_rho"][q]))
        assert rel((path[q] / e0) ** 2, d[q] / d[0] * nr) <= 1e-12, q
    old = cm.c_driven_path({"lam": lam}, e0, d, wage)
    assert cm.c_driven_path({"lam": lam}, e0, d, wage, [0.0] * n) == old
    assert cm.c_driven_path({"lam": lam}, e0, d, wage, None) == old
    one = cm.c_driven_path({"lam": 1.0}, e0, d, wage, roots)
    assert one == cm.c_driven_path({"lam": 1.0}, e0, d, wage)                  # бит в бит
    assert f["lam1_root_factor_is_one"] is True
    zero = cm.c_driven_path({"lam": 0.0}, e0, d, wage, roots)
    for q in range(n + 1):
        assert rel(zero[q] / e0, float(fr(f["N_rho"][q]))) <= 1e-12, q          # E / E_0 = N^ρ, от D не зависит
    assert f["telescoping_exact"] is True


@pytest.mark.tact
def test_p7_example_rule_on_two_cells_by_own_code():
    """Пример правила (example.json, rule) функцией c_driven_path на двух клетках слоя M (вероятности ¾ и ¼): при ρ
    правила номинал с корнем N^ρ = E_M[D] / D_0 ровно (запись примера), ожидание книги E_M[К6] / К6_0 — запись примера
    (1e-12), а разрыв Йенсена ≤ 0 (степень λ вогнута)."""
    r = example()["rule"]
    p = [float(fr(x)) for x in r["p"]]
    lam = float(fr(r["lam"]))
    cells = [[float(fr(x)) for x in c] for c in r["D_cells"]]
    roots = [float(fr(x)) for x in r["rho"][1:]]
    w = 1.05 ** 4 - 1.0                                                       # (1 + w^M)^(1/4) = 21/20 примера
    em_d = [sum(pi * c[q] for pi, c in zip(p, cells)) for q in range(3)]
    for q in range(3):
        assert rel(em_d[q], float(fr(r["E_M_D"][q]))) <= 1e-12
    paths = [cm.c_driven_path({"lam": lam}, 1.0, c, [w, w], roots) for c in cells]
    nom = cm.c_driven_path({"lam": 0.0}, 1.0, cells[0], [w, w], roots)
    for q in range(3):
        assert rel(nom[q], float(fr(r["N_rho"][q]))) <= 1e-12, q
        assert rel(nom[q], em_d[q] / em_d[0]) <= 1e-12, q                      # N^ρ,M = E_M[D] / D_0
        ek6 = sum(pi * path[q] for pi, path in zip(p, paths))
        assert rel(ek6, r["E_M_K6_over_K6_0"][q]) <= 1e-12, q
        gap = ek6 / (em_d[q] / em_d[0]) - 1.0
        assert abs(gap - r["jensen_gap"][q]) <= 1e-12 and gap <= 1e-15, q


@pytest.mark.tact
def test_p7_root_is_a_separate_multiplier():
    """Корень — отдельный множитель (1 + ρ)^(1 − λ) после прежней строки: на 200 случайных наборах roots=None и ρ ≡ 0 —
    прежний путь бит в бит, при λ = 1 корень не действует бит в бит, при λ = 0 путь — E_0 Π (1 + w)^(1/4) (1 + ρ) (1e-13),
    и путь с корнем — путь без корня × Π (1 + ρ)^(1 − λ) (1e-13)."""
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(1, 6)
        lam = rng.choice([0.0, 1.0, rng.uniform(0.0, 1.0)])
        start = rng.uniform(10.0, 500.0)
        levels = [rng.uniform(0.5, 3.0) for _ in range(n + 1)]
        wage = [rng.uniform(-0.02, 0.15) for _ in range(n)]
        roots = [rng.uniform(-0.05, 0.03) for _ in range(n)]
        old = cm.c_driven_path({"lam": lam}, start, levels, wage)
        assert cm.c_driven_path({"lam": lam}, start, levels, wage, None) == old
        assert cm.c_driven_path({"lam": lam}, start, levels, wage, [0.0] * n) == old
        new = cm.c_driven_path({"lam": lam}, start, levels, wage, roots)
        if lam == 1.0:
            assert new == old
        acc = 1.0
        for j in range(n):
            acc *= (1.0 + roots[j]) ** (1.0 - lam)
            assert rel(new[j + 1], old[j + 1] * acc) <= 1e-13
        if lam == 0.0:
            nom = start
            for j in range(n):
                nom *= (1.0 + wage[j]) ** 0.25 * (1.0 + roots[j])
            assert rel(new[-1], nom) <= 1e-13


# ============================================================================ чтение ключа и отказы (контекст)


@pytest.mark.tact
def test_p7_key_is_read_for_driven_books_of_its_line(repo):
    """Ключ читается для ведомой книги, чья строка-драйвер в нём есть, при активном К6: d["root"] — траектория ключа
    строки (та же при любой связи строки). Нет ключа и пустой словарь — корня нет; ключ только у комиссий (книга ведётся
    страхованием) — корня нет, отказа нет; К6 снят (пустой словарь книг) с ключом — книга грузится, ведомых книг нет.
    ρ квартала — значение траектории: ключи кварталов до 2029К4, LT 0 с 2030 года."""
    book, facts = repo
    b = driven_book(book)
    traj = rho()
    assert "root" not in cm.c_control_context(book, facts)["driven"][b]
    assert cm.c_driver_roots(keyed(book, roots={})) is None
    assert "root" not in cm.c_control_context(keyed(book, roots={}), facts)["driven"][b]
    drv = cm.c_control_context(keyed(book), facts)["driven"][b]
    assert drv["root"] == traj and drv["line"] == "insurance" and drv["lam"] == cm.c_bnum(book, LINK_I)
    assert "root" not in cm.c_control_context(keyed(book, roots={"fees": traj}), facts)["driven"][b]
    both = cm.c_control_context(keyed(book, roots={"fees": 0.01, "insurance": traj}), facts)["driven"][b]
    assert both["root"] == traj
    off = cm.c_control_context(put(keyed(book), DRIVERS, {}), facts)
    assert off["driven"] is None
    for lam in (0.0, 1.0, 0.37):
        got = cm.c_control_context(keyed(book, **{LINK_I.replace(".", "__"): lam}), facts)["driven"][b]
        assert got["root"] == traj and got["lam"] == lam, lam
    qs = {f"{y}Q{q}": cm.c_driven_roots(drv, y, [q])[0] for y in range(2026, 2037) for q in range(1, 5)}
    for k, v in traj.items():
        if "Q" in str(k):
            assert qs[str(k)] == float(v), k
    assert all(qs[f"{y}Q{q}"] == 0.0 for y in range(NEUTRAL_UNTIL + 1, 2037) for q in range(1, 5))
    assert cm.c_driven_roots({"lam": 0.5}, 2027, [1, 2]) is None
    assert cm.c_driven_roots(drv, 2027, [1, 2, 3, 4]) == [float(traj[f"2027Q{q}"]) for q in range(1, 5)]


@pytest.mark.tact
def test_p7_refusals(repo):
    """Отказы формы ключа — всегда, и в неактивном режиме (К6 снят; ключ строки, которая книгу не ведёт): null; не
    словарь; строка не fees / insurance; траектория null, логическое, строка, без значений ({} и только LT_from),
    неразборный ключ времени, значение не число, LT_from не год. Число — траектория."""
    book, facts = repo
    bads = [None, [0.0], "rho", {"insurance_liab": {"LT": 0.0}}, {"opex": 0.0}, {"insurance": None},
            {"insurance": True}, {"insurance": "-0.03"}, {"insurance": {}}, {"insurance": {"LT_from": 2030}},
            {"insurance": {"2026-Q3": -0.03, "LT": 0.0}}, {"insurance": {"2026Q3": None, "LT": 0.0}},
            {"insurance": {"2026Q3": "x", "LT": 0.0}}, {"insurance": {"2026Q3": -0.03, "LT": 0.0, "LT_from": 2030.5}},
            {"insurance": {"2026Q5": -0.03, "LT": 0.0}}, {"fees": {}}]
    for bad in bads:
        for extra in ({}, {"volumes__liability_drivers": {}}):
            with pytest.raises(cm.ControlInputError):
                cm.c_control_context(keyed(book, roots=bad, **extra), facts)
    with pytest.raises(cm.ControlInputError, match="null"):
        cm.c_control_context(keyed(book, roots=None), facts)
    with pytest.raises(cm.ControlInputError, match="без значений"):
        cm.c_control_context(keyed(book, roots={"insurance": {}}), facts)
    with pytest.raises(cm.ControlInputError, match="не строка"):
        cm.c_control_context(keyed(book, roots={"insurance_liab": 0.0}), facts)
    ok = cm.c_control_context(keyed(book, roots={"insurance": -0.01}), facts)["driven"][driven_book(book)]
    assert ok["root"] == -0.01 and cm.c_driven_roots(ok, 2031, [2]) == [-0.01]


# ============================================================================ клетки (вне такта)


def test_p7_neutral_cases_are_bit_for_bit(repo, runs, zero_run):
    """Бит в бит с прогоном без ключа (точка, низ, верх и числа всех 36 клеток; печать D ведомой книги снята): ρ ≡ 0
    во всех кварталах (вариант k6_root_off). На трёх клетках расчётов: пустой словарь; ключ только у комиссий (строка
    книгу не ведёт); К6 снят с ключом — как К6 снят без ключа."""
    book, facts = repo
    base, _ = runs
    assert (zero_run["point"], zero_run["low"], zero_run["high"]) == (base["point"], base["low"], base["high"])
    for ca, cb in zip(base["cells"], zero_run["cells"]):
        assert tag(ca) == tag(cb)
        assert strip_levels(numbers(cb)) == numbers(ca), tag(ca)
    _, cells0 = tp2.cells_of(book, facts)
    for variant in ({"roots": {}}, {"roots": {"fees": rho()}}):
        _, x = tp2.cells_of(keyed(book, **variant), facts)
        for key in tp2.CELLS:
            assert numbers(x[key]) == numbers(cells0[key]), (variant, key)
    off = put(book, DRIVERS, {})
    _, a = tp2.cells_of(off, facts)
    _, b = tp2.cells_of(keyed(off), facts)
    for key in tp2.CELLS:
        assert numbers(a[key]) == numbers(b[key]), key


def test_p7_key_at_link_one_is_bit_for_bit(repo):
    """Связь страхования 1: книга с ключом ≡ без ключа во всех 36 клетках бит в бит (печать D ведомой книги снята), точка,
    низ и верх те же: (1 + ρ)^0 = 1,0 ровно."""
    book, facts = repo
    one = put(book, LINK_I, 1.0)
    a, b = cm.c_control_run(one, facts), cm.c_control_run(keyed(one), facts)
    assert a["point"] == b["point"] and a["low"] == b["low"] and a["high"] == b["high"]
    for ca, cb in zip(a["cells"], b["cells"]):
        assert tag(ca) == tag(cb)
        assert strip_levels(numbers(cb)) == numbers(ca), tag(ca)


def test_p7_driven_book_recursion_in_cells(runs):
    """В каждой клетке и каждом квартале квартального прохода ведомая книга — прошлый квартал × (1 + рост зарплат мира
    клетки)^((1 − λ)/4) × (D_q / D_(q−1))^λ × (1 + ρ_q)^(1 − λ) (1e-12; D — печать уровня базы строки на конце квартала,
    D_0 — уровень якоря), ρ_q — ключ квартала, с 2030 года 0; конец года квартального прохода — остаток книги годовой
    строки (1e-9); корень действует (2026К3 — ρ ключа ≠ 0)."""
    _, ctl = runs
    ctx = ctl["ctx"]
    B = ctx["B"]
    b = driven_book(B)
    d = ctx["driven"][b]
    e0 = ctx["A"]["E0"][b]
    d0 = cm.c_base_level(d["spec"], ctx["A"]["E0"], loans=ctx["loans"], biz=[x for x in ctx["biz"] if x != b],
                         assets=ctx["loans"], nominal=1.0)
    traj = rho()
    seen = 0
    for c in ctl["cells"]:
        prev_e, prev_d = e0, d0
        for i, p in enumerate(ctx["periods"]):
            y, r = p["year"], c["rows"][i]
            assert len(r["quarters"]) == p["n"]
            for x, q in zip(r["quarters"], p["quarters"]):
                e, lev = x["driven"][b], x["driven_level"][b]
                wage = cm.c_world_quarter(B, c["world"], "wage_growth", y, q)
                root = traj.get(f"{y}Q{q}", 0.0) if y <= NEUTRAL_UNTIL else 0.0
                assert cm.c_traj_at(d["root"], y, q) == float(root), (y, q)
                want = (prev_e * (1.0 + wage) ** ((1.0 - d["lam"]) / cm.QY) * (lev / prev_d) ** d["lam"]
                        * (1.0 + float(root)) ** (1.0 - d["lam"]))
                assert rel(e, want) <= 1e-12, (tag(c), y, q)
                prev_e, prev_d = e, lev
                seen += 1
            assert rel(r["quarters"][-1]["driven"][b], r["driven_end"][b]) <= 1e-9, (tag(c), y)
    assert seen == len(ctl["cells"]) * sum(p["n"] for p in ctx["periods"])
    assert float(traj["2026Q3"]) != 0.0


def test_p7_link_zero_is_the_nominal_with_root(repo):
    """Связь страхования 0: ведомая книга — E_0 × N^ρ_q, N^ρ_q = Π (1 + рост зарплат мира)^(1/4) (1 + ρ_k) — от базы
    строки не зависит (1e-12) на концах кварталов и конце года; без ключа — индекс зарплат (1e-12)."""
    book, facts = repo
    zero = put(book, LINK_I, 0.0)
    b = driven_book(book)
    traj = rho()
    for case, roots in (("key", traj), ("nokey", None)):
        ctx, cells = tp2.cells_of(keyed(zero, roots={"insurance": roots}) if roots else zero, facts)
        e0 = ctx["A"]["E0"][b]
        for key, c in cells.items():
            nom = 1.0
            for p, r in zip(ctx["periods"], c["rows"]):
                for x, q in zip(r["quarters"], p["quarters"]):
                    w = cm.c_world_quarter(ctx["B"], key[0], "wage_growth", p["year"], q)
                    nom *= (1.0 + w) ** 0.25 * (1.0 + (cm.c_traj_at(traj, p["year"], q) if roots else 0.0))
                    assert rel(x["driven"][b] / e0, nom) <= 1e-12, (case, key, p["year"], q)
                assert rel(r["driven_end"][b] / e0, nom) <= 1e-12, (case, key, p["year"])


def test_p7_link_continuity(repo):
    """Стоимость клеток непрерывна по связи страхования с ключом у 0 и у 1: связь 0 и 1e-9, 1 − 1e-9 и 1 (1e-8
    относительно)."""
    book, facts = repo
    for lo, hi in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
        _, a = tp2.cells_of(keyed(book, **{LINK_I.replace(".", "__"): lo}), facts)
        _, b = tp2.cells_of(keyed(book, **{LINK_I.replace(".", "__"): hi}), facts)
        for key in tp2.CELLS:
            assert rel(a[key]["v_price"], b[key]["v_price"]) <= 1e-8, (lo, key)


def _layer_m_ratio(ctl: dict, b: str) -> dict:
    """Слой M, мера IV квартала: E_M[К6_y] / К6_0 ÷ E_M[D_y] / D_0 по годам (D — печать уровня базы строки)."""
    ctx = ctl["ctx"]
    pm = layer_p(ctl, LAYER_M)
    e0 = ctx["A"]["E0"][b]
    d0 = cm.c_base_level(ctx["driven"][b]["spec"], ctx["A"]["E0"], loans=ctx["loans"],
                         biz=[x for x in ctx["biz"] if x != b], assets=ctx["loans"], nominal=1.0)
    out = {}
    for i, y in enumerate(years_of(ctl)):
        ek = sum(pm[tag(c)] * c["rows"][i]["quarters"][-1]["driven"][b] for c in ctl["cells"]) / e0
        ed = sum(pm[tag(c)] * c["rows"][i]["quarters"][-1]["driven_level"][b] for c in ctl["cells"]) / d0
        out[y] = ek / ed
    return out


def test_p7_layer_m_book_stays_at_its_base(runs, zero_run):
    """Слой «рыночные ставки как есть» до 2029 года (мера IV квартала): с ключом E_M[К6] / К6_0 ÷ E_M[D] / D_0 у единицы
    — до 2e-3 (Йенсен методики ≤ 2e-3; ρ выведен на D ядра, у контроля D годовой формы: замер 4,9e-4 в 2027); с ρ ≡ 0 —
    книга выше базы больше чем на 3 % (сам экземпляр класса 1: 1,04 / 1,07 / 1,11 / 1,12). С 2030 года ρ = 0 — книга
    дрейфует к базе, как без ключа (отношение 2036 / 2029 с ключом и с ρ ≡ 0 — до 1e-2)."""
    _, ctl = runs
    b = driven_book(ctl["ctx"]["B"])
    key, old = _layer_m_ratio(ctl, b), _layer_m_ratio(zero_run, b)
    ys = years_of(ctl)
    for y in ys:
        if y > NEUTRAL_UNTIL:
            break
        assert abs(key[y] - 1.0) <= 2e-3, (y, key[y])
        assert old[y] - 1.0 > 3e-2, (y, old[y])
    last = ys[-1]
    assert abs((key[last] / key[NEUTRAL_UNTIL]) / (old[last] / old[NEUTRAL_UNTIL]) - 1.0) <= 1e-2


def test_p7_worlds_relative_to_layer_m_barely_move(runs, zero_run):
    """ρ общий для миров: отношение ожидания ведомой книги мира к слою M (мера IV квартала, 2029 и последний год) с
    ключом и с ρ ≡ 0 — до 5e-3 (только обратная связь через капитал; замер 1,7e-3)."""
    _, ctl = runs
    b = driven_book(ctl["ctx"]["B"])
    ys = years_of(ctl)

    def ratios(run):
        pm = layer_p(run, LAYER_M)
        out = {}
        for y in (NEUTRAL_UNTIL, ys[-1]):
            i = ys.index(y)
            em = sum(pm[tag(c)] * c["rows"][i]["quarters"][-1]["driven"][b] for c in run["cells"])
            for w in ("N", "H"):
                pw = world_p(run, w)
                ew = sum(pw[tag(c)] * c["rows"][i]["quarters"][-1]["driven"][b] for c in run["cells"] if tag(c) in pw)
                out[(w, y)] = ew / em
        return out

    a, z = ratios(ctl), ratios(zero_run)
    for k in a:
        assert abs(a[k] / z[k] - 1.0) <= 5e-3, k


# ============================================================================ сверка с ядром (ci_only)


def _cases(book: dict) -> dict:
    """Книги сверки с ключом ρ центра: центр, концы оси связи страхования (0 и 0,74) и концы оси базы страхования (на
    концах — ρ центра, пока книга не несёт путей ρ в связках)."""
    return {"centre_key": keyed(book), "link_low_key": keyed(at_end(book, LINK_AXIS, "low")),
            "link_high_key": keyed(at_end(book, LINK_AXIS, "high")),
            "base_low_key": keyed(at_end(book, BASE_AXIS, "low")),
            "base_high_key": keyed(at_end(book, BASE_AXIS, "high"))}


CASES = ("centre_key", "link_low_key", "link_high_key", "base_low_key", "base_high_key")


@pytest.mark.ci_only
@pytest.mark.parametrize("case", CASES, ids=CASES)
def test_p7_control_rows_off_are_the_growth_cut_class(repo, case):
    """Сверка М§17 книг с ключом Р9-1 (центр, концы осей связи и базы страхования; ρ центра): строки вне допуска — только
    класс Р6-9 (годовая форма контроля в клетках урезанного роста; tests/test_control_pass4.growth_cut_class), V0 слоёв
    не совпадают до 1e-9; строки ведомой книги (остаток конца года, ≤ 2 %) — все в допуске.

    Прототип методики (27.10.2026, p3 @ 5e50bf9, ρ конца в связке): центр 14 201 строка, вне допуска 0; конец связи 0 —
    14 114 / 0, 0,74 — 13 997 / 0; концы оси базы — 14 265 / 0 и 14 223 / 0; точки своего контроля — бит в бит с
    прототипом контроля методики."""
    book, facts = repo
    b = _cases(book)[case]
    ctl = cm.c_control_run(b, facts)
    run = tcm.core_run_of(copy.deepcopy(b))
    rows = tcm.compare_with_core(run, ctl)
    stray = tp4.growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
    driven = [r for r in rows if r.get("group") == "driven"]
    assert driven and all(r["ok"] for r in driven), tcm._fail_lines([r for r in driven if not r["ok"]])
    assert not tcm.exact_match(run, ctl)


@pytest.mark.ci_only
def test_p7_link_one_rows_off_are_those_without_key(repo):
    """Связь страхования 1 с ключом: строки сверки М§17 вне допуска — те же, что без ключа (ключ при связи 1 не действует
    ни в ядре, ни в контроле). Прототип методики: 14 513 строк, вне допуска 3 — терминальная стоимость M/downturn
    (schedule, strict) и M/crisis/strict, те же без ключа."""
    book, facts = repo
    one = put(book, LINK_I, 1.0)
    off = {}
    for name, b in (("nokey", one), ("key", keyed(one))):
        ctl = cm.c_control_run(b, facts)
        run = tcm.core_run_of(copy.deepcopy(b))
        rows = tcm.compare_with_core(run, ctl)
        off[name] = sorted((r["what"], r["core"], r["control"]) for r in rows if not r["ok"])
    assert off["key"] == off["nokey"]
