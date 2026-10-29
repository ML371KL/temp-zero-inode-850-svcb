# -*- coding: utf-8 -*-
"""Контрольная модель: ключ шестого прохода ядра Совкомбанка (core-pass6) своим счётом и флаг 6 круга 7.

Ключ (решения ведущего № 8, Р8-6; методика — spec.yaml прохода 6, пример — tests/fixtures/core_pass6/example.json, копия
примера методики; фрагмент книги — tests/fixtures/core_pass6/book_keys_pass6.yaml, копия фрагмента методики; числа κ
фрагмента тест подставляет в книгу репозитория, пока она ключа не несёт; книгу с ключом тест судит её же κ):

* Р8-6 — франшиза строки в смеси базы расходов идёт за связью строки (`opex.line_share_roots` {fees, insurance →
  траектория κ}): Φ_q = λ A_q / A_0 + (1 − λ) H_q, H_q = H_(q−4) (1 + рост зарплат мира) (1 + κ_q), H_x = A_x / A_0 до
  якоря; λ — связь самой строки; κ — корень номинальной части, общий для миров (0 с 2030 года).
* Флаг 6 круга 7 (Р8-6: «при связи 0 — ядро, контроль и текст М§4.7 согласованы»): своя база строки читается и при связи
  строки 0, если её читает доля франшизы строки в смеси расходов; счёт непрерывен по связи у нуля.

Без ключа контрольная модель считает бит в бит прежние числа — это держит сводка (tests/independent_model.py на книге
репозитория) и тесты «ключ нейтрален» ниже. Сверка с ядром (метка ci_only): случаи без ключа (книга, конец оси связи 0) —
на ядре дерева; случаи с ключом требуют ядра с проходом 6 — нет ядра, его функции или ключа в схеме ядра — провал, не
пропуск (tests/conftest.py).
"""

from __future__ import annotations

import copy
import functools
import json
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

FIXTURES = cm.ROOT / "tests" / "fixtures" / "core_pass6"
EXAMPLE = FIXTURES / "example.json"
KEYS_BOOK = FIXTURES / "book_keys_pass6.yaml"
# книга репозитория с круга 10 несёт форму строки прохода 8 (volumes.line_link_form: line) — её κ корень г/г; проход 6 судит
# смесь уровней франшизы (форма mixed): κ формы уровней — неподвижная точка листа без ключа формы на книге своего круга
# (круг 12 — сухой перевывод r12mixed), как у проходов 7 и 8
MIXED_KEYS = cm.ROOT / "tests" / "fixtures" / "core_pass8" / "book_keys_mixed_r12.yaml"
KEY_HEAD, KEY = "opex", "line_share_roots"
ROOTS = f"{KEY_HEAD}.{KEY}"
LINK_I = "other.insurance_volume_link"
LINK_AXIS = LINK_I                                       # первый путь связки оси связи страхования (Р7-3)
BASE_AXIS = "other.insurance_volume_base.mix.corporate.share"   # первый путь связки оси базы страхования (Р5-1)
LAYER_M = "macro_neutral"
NEUTRAL_UNTIL = 2029                                     # κ — переход до 2029К4, с 2030 года 0
DROP = object()

rel, numbers = tp2.rel, tp2.numbers


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def fr(s: str) -> Fraction:
    return Fraction(s)


@functools.lru_cache(maxsize=None)
def _book_kappa():
    """κ страхования ключа книги репозитория (машинная книга каталога данных сверки) или None — книга ключа не несёт."""
    book, _ = tcm._inputs()
    return ((book.get(KEY_HEAD) or {}).get(KEY) or {}).get("insurance")


@functools.lru_cache(maxsize=None)
def _book_line() -> bool:
    """Книга репозитория несёт форму строки прохода 8 (volumes.line_link_form: line)."""
    book, _ = tcm._inputs()
    return (book.get("volumes") or {}).get("line_link_form") == "line"


def kappa() -> dict:
    """κ страхования: ключ книги репозитория, если книга его уже несёт (поток книги ставит κ, выведенный листом для этой
    книги), иначе — фрагмента методики (центр книги p3 @ 48f3ca2; 14 кварталов 2026Q3…2029Q4, LT 0 с 2030). Фрагмент —
    неподвижная точка правила листа только на своей книге: на книге другого круга без ключа нейтральность слоя M с ним не
    держится (тест слоя M ниже краснеет — законный сигнал «κ перевывести»), а книгу с ключом тест судит её же κ. У книги
    формы строки (проход 8) κ книги — корень г/г: κ формы уровней — фикстура `MIXED_KEYS`."""
    if _book_line():
        return dict(yaml.safe_load(MIXED_KEYS.read_text(encoding="utf-8"))[KEY_HEAD][KEY]["insurance"])
    own = _book_kappa()
    if own is not None:
        return copy.deepcopy(own)
    frag = yaml.safe_load(KEYS_BOOK.read_text(encoding="utf-8"))
    return dict(frag[KEY_HEAD][KEY]["insurance"])


def plain(book: dict) -> dict:
    """Книга без ключа Р8-6 (поток книги может его уже нести) и без путей κ в осях; в форме прохода 6 — без ключей
    проходов 8 и 9, как у проходов 7 и 8 (форма строки, книги средств клиентов в гейтах, область гейта стоимости средств;
    funds_scope: clients схема пускает только с client_funds: clients — снимается вместе с ним и вариантами на его пути)."""
    out = copy.deepcopy(book)
    out[KEY_HEAD].pop(KEY, None)
    out.get("volumes", {}).pop("line_link_form", None)
    out["checks"].pop("client_funds", None)
    (out["checks"].get("funds_cost_to_key") or {}).pop("scope", None)
    out.get("volumes", {}).pop("funds_scope", None)
    _val = out.get("valuation") or {}
    if isinstance(_val.get("reference_variants"), list):
        _val["reference_variants"] = [v for v in _val["reference_variants"]
                                      if "volumes.funds_scope" not in (v.get("overrides") or {})]
    for ax in out["valuation"]["uncertainty"]["axes"]:
        if ax.get("kind") == cm.AXIS_BUNDLE and any(str(p).startswith(ROOTS + ".") for p in ax["paths"]):
            ax["paths"] = [p for p in ax["paths"] if not str(p).startswith(ROOTS + ".")]
            for end in ("low", "high"):
                ax[end] = {k: v for k, v in ax[end].items() if not str(k).startswith(ROOTS + ".")}
    return out


def keyed(book: dict, roots=DROP, **paths) -> dict:
    """Книга с ключом: κ страхования `kappa()` — книги, если она несёт ключ, иначе фрагмента (roots — свой узел ключа
    целиком) и подмены точечных путей paths (ключ пути — точки через «__»)."""
    out = copy.deepcopy(book)
    out[KEY_HEAD][KEY] = {"insurance": kappa()} if roots is DROP else copy.deepcopy(roots)
    for dotted, v in paths.items():
        out = tp2.put(out, dotted.replace("__", "."), v)
    return out


def put(book: dict, dotted: str, value) -> dict:
    return tp2.put(book, dotted, value)


def axis_end(book: dict, first: str, which: str) -> dict:
    """Подмены конца связки оси (по первому пути): путь → значение конца."""
    ax = next(a for a in book["valuation"]["uncertainty"]["axes"] if a["paths"][0] == first)
    return dict(ax[which])


def at_end(book: dict, first: str, which: str) -> dict:
    return cm.c_apply_overrides(book, axis_end(book, first, which))


@pytest.fixture(scope="module")
def repo():
    book, facts = tcm._inputs()
    return plain(book), facts


@pytest.fixture(scope="module")
def runs(repo):
    """Прогоны книги репозитория без ключа и с ключом в центре (κ `kappa()`, связь страхования книги)."""
    book, facts = repo
    return cm.c_control_run(book, facts), cm.c_control_run(keyed(book), facts)


def layer_p(ctl: dict, layer: str) -> dict:
    """Вероятности клеток слоя: вес мира слоя × вероятность режима × P(сценарий | режим) — как у слоёв модели."""
    ctx = ctl["ctx"]
    B = ctx["B"]
    lw = cm.c_layer_weights(B)[layer]
    prs = cm.c_bget(B, "joint.reg_prob_given_regime")
    return {(c["world"], c["regime"], c["scenario"]): lw.get(c["world"], 0.0) * ctx["posterior"][c["regime"]]
            * float(prs[c["regime"]][c["scenario"]]) for c in ctl["cells"]}


def tag(c: dict) -> tuple:
    return c["world"], c["regime"], c["scenario"]


def years_of(ctl: dict) -> list[int]:
    return [p["year"] for p in ctl["ctx"]["periods"]]


# ============================================================================ пример (формула)


@pytest.mark.tact
def test_p6_example_formula_by_own_code():
    """Пример Р8-6 (example.json, formula) своим счётом в точной записи (1e-12): H — история A / A_0 и рекурсия
    c_franchise_h; смесь c_opex_mix с номинальной частью {строка: (λ, H)} — A^C кварталов 1…8, рост г/г; без ключа —
    прежняя смесь; на якоре A^C_0 = B^C_0, история смеси прежняя. Связь 1 — смесь с ключом бит в бит прежняя; связь 0 — Φ =
    H; κ правилом листа — H = A / A_0 и смесь как без ключа."""
    f = example()["formula"]
    inp = f["inputs"]
    a = {int(x): fr(v) for x, v in inp["A_I"].items()}
    b = {int(x): fr(v) for x, v in inp["B_C"].items()}
    af = {int(x): fr(v) for x, v in inp["A_F"].items()}
    w = {int(q): fr(v) for q, v in inp["wage"].items()}
    shares = {"fees": float(fr(inp["s_F"])), "ins": float(fr(inp["s_I"]))}
    a0 = {"fees": float(af[0]), "ins": float(a[0])}
    for name, case in f["cases"].items():
        lam = float(fr(case["lambda"]))
        kap = {int(q): float(fr(v)) for q, v in case["kappa"].items()}
        h = {x: float(a[x]) / a0["ins"] for x in range(-3, 1)}
        for q in range(1, 9):
            h[q] = cm.c_franchise_h(h[q - 4], float(w[q]), kap[q])
        for x, v in case["H"].items():
            assert rel(h[int(x)], float(fr(v))) <= 1e-12, (name, x)
        mix, old = {}, {}
        for x in range(-3, 9):
            cur = {"fees": float(af[x]), "ins": float(a[x])}
            nom = {"ins": (lam, h[x])} if x >= 1 else None
            mix[x] = cm.c_opex_mix(shares, float(b[x]), float(b[0]), cur, a0, nom)
            old[x] = cm.c_opex_mix(shares, float(b[x]), float(b[0]), cur, a0)
            assert rel(mix[x], float(fr(case["A_C"][str(x)]))) <= 1e-12, (name, x)
            assert rel(old[x], float(fr(case["A_C_without_key"][str(x)]))) <= 1e-12, (name, x)
            if x >= 1:
                phi = (mix[x] - (1.0 - shares["fees"] - shares["ins"]) * float(b[x])
                       - shares["fees"] * float(b[0]) * cur["fees"] / a0["fees"]) / (shares["ins"] * float(b[0]))
                assert abs(phi - float(fr(case["Phi"][str(x)]))) <= 1e-12, (name, x)
        for q in range(1, 9):
            want = float(fr(case["A_C_growth"][str(q)]))
            assert abs(mix[q] / mix[q - 4] - 1.0 - want) <= 1e-12, (name, q)
        assert mix[0] == float(b[0]) and all(mix[x] == old[x] for x in range(-3, 1)), name
        if lam == 1.0:
            assert all(mix[x] == old[x] for x in range(-3, 9)), name          # бит в бит
        if lam == 0.0:
            for q in range(1, 9):
                cur = {"fees": float(af[q]), "ins": float(a[q])}
                bare = cm.c_opex_mix({"fees": shares["fees"]}, float(b[q]), float(b[0]), cur, a0)
                bare += -shares["ins"] * float(b[q]) + shares["ins"] * float(b[0]) * h[q]
                assert rel(mix[q], bare) <= 1e-12, (name, q)                  # Φ = H
        if case["checks"].get("rule_H_is_base"):
            assert all(rel(h[q], float(a[q]) / a0["ins"]) <= 1e-12 for q in range(1, 9)), name
            assert all(rel(mix[q], old[q]) <= 1e-12 for q in range(1, 9)), name


@pytest.mark.tact
def test_p6_mix_term_order_is_the_old_line_at_link_one():
    """Слагаемые франшизы с ключом — s B^C_0 A / A_0 × λ и s B^C_0 (1 − λ) H: при λ = 1 смесь бит в бит прежняя на любых
    числах (множитель 1,0 и слагаемое 0,0), при λ = 0 — ровно s B^C_0 H; номинальная часть без доли (s = 0) смесь не
    меняет."""
    import random
    rng = random.Random(6)
    for _ in range(200):
        shares = {"fees": rng.uniform(0.0, 0.4), "ins": rng.uniform(0.0, 0.4)}
        b_c, b0 = rng.uniform(1e2, 1e4), rng.uniform(1e2, 1e4)
        a = {"fees": rng.uniform(1.0, 5e3), "ins": rng.uniform(1.0, 5e3)}
        a0 = {"fees": rng.uniform(1.0, 5e3), "ins": rng.uniform(1.0, 5e3)}
        h = rng.uniform(0.5, 3.0)
        old = cm.c_opex_mix(shares, b_c, b0, a, a0)
        assert cm.c_opex_mix(shares, b_c, b0, a, a0, {"ins": (1.0, h)}) == old
        assert cm.c_opex_mix(shares, b_c, b0, a, a0, {"ins": (1.0, h), "fees": (1.0, 2.0 * h)}) == old
        zero = cm.c_opex_mix(shares, b_c, b0, a, a0, {"ins": (0.0, h)})
        want = (1.0 - sum(shares.values())) * b_c + shares["fees"] * b0 * a["fees"] / a0["fees"] + shares["ins"] * b0 * h
        assert rel(zero, want) <= 1e-14
        none = {"fees": shares["fees"], "ins": 0.0}
        assert cm.c_opex_mix(none, b_c, b0, a, a0, {"ins": (0.3, h)}) == cm.c_opex_mix(none, b_c, b0, a, a0)


# ============================================================================ чтение ключа и флаг 6 (контекст)


@pytest.mark.tact
def test_p6_key_is_read_only_with_a_franchise_share(repo):
    """Ключ читается для строки, когда читаются доли (связь расходов > 0) и доля строки > 0; λ — связь самой строки.
    Нет ключа и пустой словарь — None (прежняя смесь); доля страхования 0 или связь расходов 0 — ключ неактивного режима
    (не читается, отказа нет); строка комиссий с ключом — со своей связью."""
    book, facts = repo
    traj = kappa()
    assert cm.c_control_context(book, facts)["share_nominal"] is None
    assert cm.c_control_context(keyed(book, roots={}), facts)["share_nominal"] is None
    ctx = cm.c_control_context(keyed(book), facts)
    lam_i = cm.c_bnum(book, LINK_I)
    assert ctx["share_nominal"] == {"ins": (lam_i, traj)} and 0.0 < lam_i < 1.0
    both = cm.c_control_context(keyed(book, roots={"insurance": traj, "fees": 0.01}), facts)["share_nominal"]
    assert both == {"ins": (lam_i, traj), "fees": (cm.c_bnum(book, "fees.volume_link"), 0.01)}
    assert cm.c_control_context(keyed(book, opex__line_shares__insurance=0.0), facts)["share_nominal"] is None
    off = cm.c_control_context(keyed(book, opex__volume_link=0.0), facts)
    assert off["share_nominal"] is None and off["line_shares"] is None
    for lam in (0.0, 1.0, 0.37):
        got = cm.c_control_context(keyed(book, **{LINK_I.replace(".", "__"): lam}), facts)["share_nominal"]
        assert got == {"ins": (lam, traj)}, lam


@pytest.mark.tact
def test_p6_refusals(repo):
    """Отказы формы ключа — всегда, и в неактивном режиме (связь расходов 0): null; не словарь; строка не fees /
    insurance; траектория null, логическое, строка, без значений ({} и только LT_from), неразборный ключ времени, значение
    не число, LT_from не год."""
    book, facts = repo
    bads = [None, [0.0], "kappa", {"opex": {"LT": 0.0}}, {"insurance": None}, {"insurance": True},
            {"insurance": "-0.1"}, {"insurance": {}}, {"insurance": {"LT_from": 2030}},
            {"insurance": {"2026-Q3": -0.1, "LT": 0.0}}, {"insurance": {"2026Q3": None, "LT": 0.0}},
            {"insurance": {"2026Q3": "x", "LT": 0.0}}, {"insurance": {"2026Q3": -0.1, "LT": 0.0, "LT_from": 2030.5}}]
    for bad in bads:
        for extra in ({}, {"opex__volume_link": 0.0}, {"opex__line_shares__insurance": 0.0}):
            with pytest.raises(cm.ControlInputError):
                cm.c_control_context(keyed(book, roots=bad, **extra), facts)
    with pytest.raises(cm.ControlInputError, match="null"):
        cm.c_control_context(keyed(book, roots=None), facts)
    with pytest.raises(cm.ControlInputError, match="без значений"):
        cm.c_control_context(keyed(book, roots={"insurance": {}}), facts)
    ok = cm.c_control_context(keyed(book, roots={"insurance": -0.05}), facts)["share_nominal"]
    assert ok["ins"][1] == -0.05                                          # число — траектория


@pytest.mark.tact
def test_p6_flag6_own_base_is_read_by_the_franchise_share_at_link_zero(repo):
    """Флаг 6 круга 7: своя база строки читается при связи строки 0, если её читает доля франшизы строки (доля > 0 при
    связи расходов > 0), — та же база, что при связи > 0; без доли (доля 0 или связь расходов 0) при связи 0 — не
    читается. Доли разбираются раньше баз. Так же у комиссий."""
    book, facts = repo
    at_half = cm.c_control_context(book, facts)["line_base"]
    assert at_half["ins"] is not None and at_half["fees"] is not None
    zero = cm.c_control_context(put(book, LINK_I, 0.0), facts)["line_base"]
    assert zero["ins"] == at_half["ins"]
    assert cm.c_control_context(put(put(book, LINK_I, 0.0), "opex.line_shares.insurance", 0.0),
                                facts)["line_base"]["ins"] is None
    assert cm.c_control_context(put(put(book, LINK_I, 0.0), "opex.volume_link", 0.0), facts)["line_base"]["ins"] is None
    fees0 = cm.c_control_context(put(book, "fees.volume_link", 0.0), facts)["line_base"]
    assert fees0["fees"] == at_half["fees"]
    assert cm.c_control_context(put(put(book, "fees.volume_link", 0.0), "opex.line_shares.fees", 0.0),
                                facts)["line_base"]["fees"] is None


# ============================================================================ клетки (вне такта)


def test_p6_flag6_link_zero_is_continuous(repo):
    """Флаг 6: стоимость клеток непрерывна по связи страхования у нуля — связь 0 и 1e-9 без ключа и с ключом (1e-8
    относительно; до правки контроль на связи 0 брал для франшизы volumes.link_base — скачок в клетках); у единицы с
    ключом — 1 − 1e-9 и 1 (1e-8)."""
    book, facts = repo
    for base in (book, keyed(book)):
        for lo, hi in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
            if base is book and lo > 0.5:
                continue
            _, a = tp2.cells_of(put(base, LINK_I, lo), facts)
            _, b = tp2.cells_of(put(base, LINK_I, hi), facts)
            for key in tp2.CELLS:
                assert rel(a[key]["v_price"], b[key]["v_price"]) <= 1e-8, (lo, key)


def test_p6_key_at_link_one_share_zero_and_empty_dict_are_bit_for_bit(repo):
    """Связь страхования 1: книга с ключом ≡ без ключа во всех 36 клетках бит в бит (кроме печати H), точка та же.
    Пустой словарь ≡ без ключа; доля франшизы страхования 0 и связь расходов 0 — ключ не читается: клетки бит в бит."""
    book, facts = repo
    one = put(book, LINK_I, 1.0)
    a, b = cm.c_control_run(one, facts), cm.c_control_run(keyed(one), facts)
    assert a["point"] == b["point"] and a["low"] == b["low"] and a["high"] == b["high"]
    for ca, cb in zip(a["cells"], b["cells"]):
        assert tag(ca) == tag(cb)
        mine = numbers(cb)
        for r in mine[1]:
            assert "franchise_h" in r
            r.pop("franchise_h")
        assert mine == numbers(ca), tag(ca)
    for variant in ({"roots": {}}, {"opex__line_shares__insurance": 0.0}, {"opex__volume_link": 0.0}):
        with_key = keyed(book, **variant)
        _, x = tp2.cells_of(with_key, facts)
        _, y = tp2.cells_of(plain(with_key), facts)
        for key in tp2.CELLS:
            assert numbers(x[key]) == numbers(y[key]), (variant, key)


def test_p6_nominal_part_recursion_in_cells(runs):
    """В каждой клетке и каждом квартале H = H того же квартала прошлого года × (1 + рост зарплат мира клетки) × (1 + κ
    квартала) ровно (бит в бит); квартал прошлого года до якоря — A / A_0 базы строки по фактам (полусумма концов); с 2030
    года κ = 0 — H растёт ровно с зарплатами мира."""
    _, ctl = runs
    ctx = ctl["ctx"]
    B, anchor = ctx["B"], ctx["anchor"]
    spec = ctx["line_base"]["ins"]
    a0 = cm.c_base_hist_avg(ctx, spec, *anchor)
    lam, traj = ctx["share_nominal"]["ins"]
    for c in ctl["cells"]:
        h = {}
        for i, p in enumerate(ctx["periods"]):
            seq = c["rows"][i]["franchise_h"]["ins"]
            assert len(seq) == p["n"]
            for j, q in enumerate(p["quarters"]):
                y = p["year"]
                h[(y, q)] = seq[j]
                back = h[(y - 1, q)] if (y - 1, q) > anchor else cm.c_base_hist_avg(ctx, spec, y - 1, q) / a0
                wage = cm.c_world_quarter(B, c["world"], "wage_growth", y, q)
                root = cm.c_traj_at(traj, y, q)
                assert seq[j] == back * (1.0 + wage) * (1.0 + root), (tag(c), y, q)
                if y > NEUTRAL_UNTIL:
                    assert root == 0.0 and seq[j] == back * (1.0 + wage) * 1.0, (tag(c), y, q)
                elif (y, q) > anchor:
                    assert root == float(traj[f"{y}Q{q}"]), (y, q)


# Известное расхождение (решение ведущего 29.10.2026: числа книги не задевает, разбор ноябрьской версией книги; долг —
# справочник панели, раздел долгов). strict: починка — снять метку.
@pytest.mark.xfail(strict=True, reason=(
    "известное расхождение: нейтральность ключа κ в слое M у контроля на книге Совкомбанка — 0,049 % в 2028 и 0,08 % в "
    "2029 году при допуске 0,03 % (плечо франшизы s(1 − λ) 0,117 против 0,078 у книги, на которой ставили допуск); "
    "допуск — решение ведущего, числа книги не задевает — разбор ноябрьской версией книги"))
def test_p6_layer_m_mix_is_neutral_and_franchise_drifts_like_the_line(runs):
    """Слой «рыночные ставки как есть» до 2029 года: ожидание смеси базы расходов с ключом — то же, что без ключа, до
    0,03 % (методика: обратная связь через капитал; у контроля ещё годовая форма средних базы против κ ядра). По мирам
    франшиза дрейфует как строка страхования: (Φ^W / A^W) / (Φ^M / A^M) против (строка^W / A^W) / (строка^M / A^M) —
    до 2e-3 в 2029 и 2036 годах (без ключа франшиза по мирам не дрейфовала бы вовсе, а строка дрейфует на проценты — сам
    экземпляр класса 1)."""
    plain_run, ctl = runs
    pm = layer_p(ctl, LAYER_M)
    ys = years_of(ctl)
    for i, y in enumerate(ys):
        if y > NEUTRAL_UNTIL:
            break
        ea = sum(pm[tag(c)] * c["rows"][i]["vol_opex"] for c in plain_run["cells"])
        eb = sum(pm[tag(c)] * c["rows"][i]["vol_opex"] for c in ctl["cells"])
        assert abs(eb / ea - 1.0) <= 3e-4, y
    ctx = ctl["ctx"]
    a0 = cm.c_base_hist_avg(ctx, ctx["line_base"]["ins"], *ctx["anchor"])
    lam = ctx["share_nominal"]["ins"][0]
    prs = cm.c_bget(ctx["B"], "joint.reg_prob_given_regime")

    def by_world(i, w):
        """(Φ / A, строка / A) мира: ожидания по клеткам мира (режим × сценарий), A — средняя базы строки к A_0."""
        cells = [c for c in ctl["cells"] if c["world"] == w]
        pr = {tag(c): ctx["posterior"][c["regime"]] * float(prs[c["regime"]][c["scenario"]]) for c in cells}
        base = sum(pr[tag(c)] * c["rows"][i]["vol_ins"] / a0 for c in cells)
        line = sum(pr[tag(c)] * c["rows"][i]["ins"] for c in cells)
        phi = sum(pr[tag(c)] * (lam * c["rows"][i]["vol_ins"] / a0
                                + (1.0 - lam) * sum(c["rows"][i]["franchise_h"]["ins"]) / cm.QY) for c in cells)
        return phi / base, line / base

    for y in (NEUTRAL_UNTIL, ys[-1]):
        i = ys.index(y)
        fm, lm = by_world(i, "M")
        for w in ("N", "H"):
            fw, lw = by_world(i, w)
            assert abs((fw / fm) / (lw / lm) - 1.0) <= 2e-3, (y, w)
            assert abs(lw / lm - 1.0) > 1e-2, (y, w)                 # строка по мирам дрейфует — есть что сверять


# ============================================================================ сверка с ядром (ci_only)


def _cases(book: dict) -> dict:
    """Книги сверки: без ключа — книга и конец оси связи 0 (флаг 6); с ключом κ центра — центр, концы оси связи (0 и 1)
    и концы оси базы страхования."""
    return {"book": book, "link0": at_end(book, LINK_AXIS, "low"),
            "centre_key": keyed(book), "link0_key": keyed(at_end(book, LINK_AXIS, "low")),
            "link1_key": keyed(at_end(book, LINK_AXIS, "high")),
            "base_low_key": keyed(at_end(book, BASE_AXIS, "low")),
            "base_high_key": keyed(at_end(book, BASE_AXIS, "high"))}


CASES = ("book", "link0", "centre_key", "link0_key", "link1_key", "base_low_key", "base_high_key")


@pytest.mark.ci_only
@pytest.mark.parametrize("case", CASES, ids=CASES)
def test_p6_control_rows_off_are_the_growth_cut_class(repo, case):
    """Сверка М§17 книги репозитория без ключа и на конце оси связи 0 (флаг 6) и книг с ключом Р8-6 (центр, концы осей
    связи и базы страхования): строки вне допуска — только класс Р6-9 (годовая форма контроля в клетках урезанного роста;
    tests/test_control_pass4.growth_cut_class), V0 слоёв не совпадают до 1e-9. Это сторож известных красных Р8-9
    (решения ведущего № 8; ops/expected_counts.json → known_failures): строгие тесты книги репозитория красны тремя
    строками RWA гарантий конца 2027 (M/downturn/mid и strict) и 2028 (strict), 612,52 против 606,27 (1,03 % при допуске
    1 %).

    Прототипы методики (22.10.2026): вне допуска во всех случаях 3 строки RWA гарантий M/downturn 2027–2028 — книга 14 578
    строк, центр с ключом 14 562, конец связи 0 без ключа 14 008 (до правки контроля 456 / 267 — флаг 6), с ключом 14 445,
    конец связи 1 14 663, концы оси базы 14 562 и 14 472."""
    book, facts = repo
    b = _cases(book)[case]
    ctl = cm.c_control_run(b, facts)
    run = tcm.core_run_of(copy.deepcopy(b))
    rows = tcm.compare_with_core(run, ctl)
    stray = tp4.growth_cut_class(run, ctl, rows)
    assert not stray, tcm._fail_lines(stray)
    assert not tcm.exact_match(run, ctl)
