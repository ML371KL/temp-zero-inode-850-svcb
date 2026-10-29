"""Проверки седьмого прохода ядра Совкомбанка (core-pass7): книга страховых обязательств К6 несёт корень ρ номинальной
части (Р9-1, М§4.3; ключ `volumes.liability_driver_roots` {fees, insurance → траектория ρ}, необязательный).

Форма: книга b за драйвером строки ℓ растёт E_b,q = E_b,q−1 (1 + wage_W,q)^((1 − λ)/4) (D_q / D_q−1)^λ (1 + ρ_q)^(1 − λ),
то есть E_b,q / E_b,0 = (D_q / D_0)^λ (N^ρ_q)^(1 − λ), N^ρ_q = Π_(k ≤ q) (1 + wage_W,k)^(1/4) (1 + ρ_k); λ — связь строки, D —
уровень базы строки на конец квартала (ряд клетки `vol_end_<строка>`, только при ключе), ρ — корень строки, общий для
миров: лист выводит его так, что в слое «рыночные ставки как есть» номинал с корнем идёт за ожиданием базы строки на
концах кварталов (ρ_q = E_M[D_q] / E_M[D_(q−1)] / (1 + w^M_q)^(1/4) − 1 до 2029К4, дальше 0).

Одни и те же проверки зовут тесты (`tests/test_core_p7.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass7/example.json` — копия выхода
`example.py` агента методики, notes/core-pass7; ρ примера — `tests/fixtures/core_pass7/book_keys_pass7.yaml`), выведенные
из книги и фактов независимо от кода ядра. Ключа в книгах фикстур нет; книгу дерева проверки берут без ключа и без его
путей в осях и вариантах (нет ключа — прежняя ветвь кода, бит в бит) и включают ключ подменой. Базу строки (К2, смесь
К2б — компилированный словарь ядра) и прежнюю цепь К6 держат проверки проходов 2–3; здесь судится только новое: корень,
ряд уровня базы на концах кварталов и чтение ключа по строке.
"""

from __future__ import annotations

import copy
import functools
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

from tests import support_core_p3 as P3
from tests import support_core_p4 as P4
from tests import support_core_p6 as P6
from tests import support_core_t3 as S

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "core_pass7"
EXAMPLE, BOOK_KEYS = FIXTURE / "example.json", FIXTURE / "book_keys_pass7.yaml"
close = S.close
refused = P3.refused
KEY, DRIVERS = "volumes.liability_driver_roots", "volumes.liability_drivers"
LINK = {"fees": "fees.volume_link", "insurance": "other.insurance_volume_link"}
END = {"fees": "vol_end_fees", "insurance": "vol_end_ins"}     # D^ℓ_q на конец квартала — ряд клетки (Р9-1)
Q_END, LT_FROM = "2029Q4", 2030                                # корень ρ — до 2029К4, дальше 0 (правило листа)
MACRO = "macro_neutral"                                        # слой «рыночные ставки как есть» (слой M)
B6 = "insurance_liab"                                          # книга К6 Совкомбанка (за строкой страхования)
EX_BASE_POINT = 15.992912288690338                            # точка книги дерева без ключа (p3 @ 5e50bf9)
# Интеграция круга 10: книга дерева несёт форму строки прохода 8 (volumes.line_link_form: line) — её κ и ρ — корни г/г, для цепи К6
# (форма этого прохода) не годятся; κ формы уровней и ρ цепи — неподвижная точка листа без ключа формы на книге своего круга
# (фикстура круга 12 — сухой перевывод r12mixed; неподвижная точка только на своей книге: с новой книгой — новая фикстура)
MIXED_KEYS = ROOT / "tests" / "fixtures" / "core_pass8" / "book_keys_mixed_r12.yaml"
PASS8_KEYS = (("volumes", "line_link_form"), ("checks", "client_funds"))


@functools.lru_cache(maxsize=None)
def _mixed_text() -> str:
    import yaml
    return json.dumps(yaml.safe_load(MIXED_KEYS.read_text(encoding="utf-8")))


def tree_line_form() -> bool:
    """Книга дерева несёт форму строки прохода 8 — её κ и ρ корни г/г (интеграция круга 10)."""
    _, data = P4._real_book()
    return (data.get("volumes") or {}).get("line_link_form") == "line"


def mixed_roots() -> tuple[dict[str, Any], dict[str, Any]]:
    """κ формы уровней и ρ цепи книги круга 10 без ключа формы (фикстура MIXED_KEYS)."""
    d = json.loads(_mixed_text())
    return d["opex"]["line_share_roots"]["insurance"], d["volumes"]["liability_driver_roots"]["insurance"]
# фикстура `core_t` (связи 0,5 / 0,5 / 0,4) на фактах с историей книг: средства юрлиц — книга К6 за строкой страхования на
# базе «розничные кредитные книги» (веса книг)
T_K6 = {"volumes__liability_drivers": {"corp_funds": "insurance"}, "other__insurance_volume_base": P3.T_RETAIL}
# ρ фикстуры: кварталы до LT_from явно, дальше LT ≠ 0 (чтение проверки — ключ квартала или LT)
T_RHO = {"insurance": {"2026Q3": -0.03, "2026Q4": -0.02, "2027Q1": 0.01, "2027Q2": -0.015, "2027Q3": 0.005,
                       "2027Q4": -0.01, "LT": -0.004, "LT_from": 2028}}


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (ключ core7-spec): formula — цепь точными дробями; rule — правило ρ на двух клетках;
    core — сводка прототипа на книге дерева."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def _bank_rho_text() -> str:
    import yaml
    return json.dumps(yaml.safe_load(BOOK_KEYS.read_text(encoding="utf-8"))["volumes"][KEY.split(".")[1]]["insurance"])


def bank_rho() -> dict[str, Any]:
    """ρ книги дерева, если она несёт ключ Р9-1 (поток книги ставит ρ, выведенный листом вместе с κ этой книги), иначе — ρ
    примера (неподвижная точка методики на книге p3 @ 5e50bf9, κ книги; фрагмент книги прохода). Фрагмент — неподвижная
    точка только на своей книге: на книге другого круга слой M с ним у базы не держится (интеграция круга 9)."""
    _, data = P4._real_book()
    if tree_line_form():                                     # ρ книги — корень г/г формы строки (проход 8): ρ цепи — фикстура
        return copy.deepcopy(mixed_roots()[1])
    own = ((data.get("volumes") or {}).get(KEY.split(".")[1]) or {}).get("insurance")
    return copy.deepcopy(own) if own is not None else json.loads(_bank_rho_text())


def zero_of(traj: dict[str, Any]) -> dict[str, Any]:
    """Та же траектория с нулями во всех ключах (LT_from — прежний): 14 путей ρ = 0 — вариант k6_root_off."""
    return {k: (v if k == "LT_from" else 0.0) for k, v in traj.items()}


def t7(*, roots: Any = None, **changes: Any) -> Any:
    """Сетка фикстуры `core_t` с книгой К6 (`T_K6`) и ключом `roots` (None — без ключа); подмены — `__` вместо точки."""
    kw: dict[str, Any] = dict(T_K6)
    if roots is not None:
        kw["volumes__liability_driver_roots"] = roots
    kw.update(changes)
    return P3.mix_run(**kw)


def bank(roots: Any = None, **paths: Any) -> Any:
    """Сетка книги дерева с ключом `roots` (None — без ключа) и подменами точечных путей (`__` вместо точки). Книга — без
    ключа Р9-1, без его путей в осях и без вариантов, подменяющих его пути (`_bank_data`): «без ключа» — без него."""
    changes = [(k.replace("__", "."), json.dumps(v)) for k, v in paths.items()]
    if roots is not None:
        changes.append((KEY, json.dumps(roots)))
    return _bank_run(tuple(sorted(changes)))


def _keyed(path: Any) -> bool:
    return str(path) == KEY or str(path).startswith(KEY + ".")


def tree_scope() -> dict[str, Any]:
    """Интеграция круга 11: «средства клиентов» книги дерева (проход 9, Р11-2) — volumes.funds_scope: clients вместе с
    checks.client_funds: clients (схема ставит их вместе). Неподвижная точка κ, ρ книги дерева выведена на этих ключах: проверки
    неподвижной точки на книге дерева ставят их обратно (`_bank_data` их снимает как ключи прохода 8). Нет ключа — пусто."""
    _, data = P4._real_book()
    if (data.get("volumes") or {}).get("funds_scope") == "clients":
        return {"volumes__funds_scope": "clients", "checks__client_funds": "clients"}
    return {}


def strip_pass9(out: dict) -> None:
    """Интеграция круга 11: книга дерева несёт ключи прохода ядра 9. Ключ volumes.funds_scope: clients схема пускает только вместе
    с checks.client_funds: clients (ключ прохода 8, который «без ключа» снимает) — он снимается тоже, с вариантами на его пути.
    Доли сжатия книг phi_share и вариант pnl.nci_real схеме ключей прохода 8 не мешают и остаются (книга дерева)."""
    (out.get("volumes") or {}).pop("funds_scope", None)
    val = out.get("valuation", {})
    if isinstance(val.get("reference_variants"), list):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(str(k) == "volumes.funds_scope" for k in (v.get("overrides") or {}))]


@functools.lru_cache(maxsize=None)
def _bank_data() -> dict[str, Any]:
    """Исходный словарь книги дерева без ключа `volumes.liability_driver_roots`, без его путей в осях-связках и без
    справочных вариантов, подменяющих его пути (ρ на концах осей и вариант k6_root_off ставит поток книги вместе с
    ключом). Книга без ключа — та же, что книга дерева до потока (бит в бит)."""
    _, data = P4._real_book()
    out = copy.deepcopy(data)
    (out.get("volumes") or {}).pop(KEY.split(".")[1], None)
    for head, key in PASS8_KEYS:                             # ключи прохода 8 (интеграция круга 10): прежние формы этого прохода
        (out.get(head) or {}).pop(key, None)
    ((out.get("checks") or {}).get("funds_cost_to_key") or {}).pop("scope", None)
    strip_pass9(out)                                        # интеграция круга 11: и ключи прохода 9
    if tree_line_form():                                     # κ книги — корень г/г формы строки: κ формы уровней — фикстура
        out["opex"]["line_share_roots"]["insurance"] = copy.deepcopy(mixed_roots()[0])
    val = out.get("valuation", {})
    for ax in val.get("uncertainty", {}).get("axes", []):
        if any(_keyed(p) for p in ax.get("paths", [])):
            ax["paths"] = [p for p in ax["paths"] if not _keyed(p)]
            for end in ("low", "high"):
                if isinstance(ax.get(end), dict):
                    ax[end] = {k: v for k, v in ax[end].items() if not _keyed(k)}
    if isinstance(val.get("reference_variants"), list):
        val["reference_variants"] = [v for v in val["reference_variants"]
                                     if not any(_keyed(k) for k in (v.get("overrides") or {}))]
    return out


@functools.lru_cache(maxsize=None)
def _bank_run(changes: tuple = ()) -> Any:
    """Сетка книги `_bank_data` с подменами точечных путей `changes` ((путь, JSON значения), …)."""
    from model.book import book_from_dict
    from model.grid import live_from_book, run_grid
    from model.paths import set_path
    data = copy.deepcopy(_bank_data())
    for dotted, value in changes:
        set_path(data, dotted, json.loads(value))
    facts = P4._real_facts()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, live_from_book(book, facts))


def rho_ref(traj: Any, tl: Any) -> list[float | None]:
    """ρ_q, q = 0…Q, заново по записи траектории теста: число — на все кварталы; словарь — ключ квартала, с года LT_from
    — LT (квартал без ключа до LT_from — ошибка записи теста). q = 0 (якорь) не читается — None."""
    return P6.kappa_ref(traj, tl)


_same = P6._same


# ------------------------------------------------------------------ без ключа и нейтральные формы — бит в бит


def check_neutral_bank() -> None:
    """Книга дерева: без ключа рядов vol_end_* нет и поле подготовки пусто; пустой словарь ≡ без ключа (и отпечаток
    прохода тот же); ρ ≡ 0 во всех кварталах (вариант k6_root_off) ≡ без ключа (ряд vol_end_ins — только при ключе); К6
    снят (`volumes.liability_drivers: {}`) при ключе ≡ К6 снят без ключа (ключ неактивного режима, не отказ); ключ только
    у строки, которая ни одной книгой не ведёт (комиссии), ≡ без ключа; связь страхования 1 с ключом ≡ без ключа (точка,
    клетки, все ряды; кроме vol_end_ins)."""
    base = bank()
    rho = bank_rho()
    assert base.ctx.prep.driver_roots is None
    assert not set(END.values()) & set(base.cells[0].quarters)
    empty = bank({})
    assert empty.ctx.prep.driver_roots is None
    _same(empty, base)
    assert P3._path_key(empty) == P3._path_key(base)
    zero = bank({"insurance": zero_of(rho)})
    assert set(zero.ctx.prep.driver_roots) == {B6}
    _same(zero, base, extra=frozenset({END["insurance"]}))
    off, off_key = bank(volumes__liability_drivers={}), bank({"insurance": rho}, volumes__liability_drivers={})
    assert off_key.ctx.prep.driven is None and off_key.ctx.prep.driver_roots is None
    _same(off_key, off)
    fees = bank({"fees": rho})
    assert fees.ctx.prep.driver_roots is None
    _same(fees, base)
    one = {"other__insurance_volume_link": 1.0}
    keyed1 = bank({"insurance": rho}, **one)
    assert keyed1.ctx.prep.driven[B6][1] == 1.0 and keyed1.ctx.prep.driver_roots is not None
    _same(keyed1, bank(**one), extra=frozenset({END["insurance"]}))


def check_neutral_fixture() -> None:
    """Фикстура: пустой словарь ≡ без ключа; справочный вариант {volumes.liability_driver_roots: {}} подменой книги с
    ключом ≡ без ключа; ключ у строки комиссий при книге за страхованием ≡ без ключа; ключ двигает стоимость клеток."""
    from model.grid import run_grid
    from tests.support_core_t import book_live
    base = t7()
    assert base.ctx.prep.driver_roots is None and "vol_end_ins" not in base.cells[0].quarters
    _same(t7(roots={}), base)
    keyed = t7(roots=T_RHO)
    assert set(keyed.ctx.prep.driver_roots) == {"corp_funds"} and abs(keyed.point - base.point) > 1e-6
    variant = keyed.ctx.book.with_overrides({KEY: {}})
    _same(run_grid(variant, keyed.ctx.facts, book_live(variant)), base)
    fees_only = t7(roots={"fees": T_RHO["insurance"]})
    assert fees_only.ctx.prep.driver_roots is None
    _same(fees_only, base)


# ------------------------------------------------------------------ пример методики (формулы точными дробями)


def _fr(s: str) -> Fraction:
    return Fraction(s)


def check_example() -> None:
    """Пример Р9-1 (formula): цепь E_q = E_(q−1) (1 + w)^((1 − λ)/4) (D_q / D_(q−1))^λ (1 + ρ_q)^(1 − λ) при λ = 1/2 и
    рациональных корнях — заново точными дробями, равна числам примера; телескоп (E_q / E_0)^2 = (D_q / D_0) N^ρ_q ровно;
    при λ = 1 множитель корня ровно 1,0. rule: ρ правилом на двух клетках слоя — N^ρ,M = E_M[D] / D_0 ровно, Йенсен ≤ 0
    (степень λ вогнута). Книга дерева — книга примера (точка без ключа — число примера): точка с ρ примера — число
    примера бит в бит; ρ квартала 2026К3 — запись ключа, 2030К1 — 0."""
    ex = example()["formula"]
    lam, one_w, e0 = _fr(ex["lam"]), _fr(ex["one_plus_w"]), _fr(ex["E0"])
    g8 = Fraction(21, 20)
    assert g8 ** 8 == one_w and lam == Fraction(1, 2)
    d = [_fr(x) for x in ex["D"]]
    one_rho = [None] + [_fr(x) for x in ex["one_plus_rho"][1:]]
    root = [None] + [Fraction(math.isqrt(r.numerator), math.isqrt(r.denominator)) for r in one_rho[1:]]
    assert all(r * r == x for r, x in zip(root[1:], one_rho[1:]))
    e, n = [e0], [Fraction(1)]
    for q in range(1, len(d)):
        step = Fraction(math.isqrt((d[q] / d[q - 1]).numerator), math.isqrt((d[q] / d[q - 1]).denominator))
        assert step * step == d[q] / d[q - 1]
        e.append(e[-1] * g8 * step * root[q])          # (1 + w)^(1/8) (D_q / D_(q−1))^(1/2) (1 + ρ_q)^(1/2)
        n.append(n[-1] * g8 ** 2 * one_rho[q])          # (1 + w)^(1/4) (1 + ρ_q)
    assert [_fr(x) for x in ex["E"]] == e and [_fr(x) for x in ex["N_rho"]] == n
    assert all((e[q] / e0) ** 2 == (d[q] / d[0]) * n[q] for q in range(len(d))) and ex["telescoping_exact"] is True
    assert (1 + (-0.03)) ** (1.0 - 1.0) == 1.0 and ex["lam1_root_factor_is_one"] is True
    rule = example()["rule"]
    p = [_fr(x) for x in rule["p"]]
    cells = [[_fr(x) for x in c] for c in rule["D_cells"]]
    g4 = Fraction(21, 20)                               # (1 + w^M)^(1/4) примера
    em = [sum(pi * c[q] for pi, c in zip(p, cells)) for q in range(3)]
    rho = [None] + [em[q] / em[q - 1] / g4 - 1 for q in (1, 2)]
    nm = [Fraction(1)]
    for q in (1, 2):
        nm.append(nm[-1] * g4 * (1 + rho[q]))
    assert [_fr(x) for x in rule["E_M_D"]] == em and [_fr(x) for x in rule["rho"][1:]] == rho[1:]
    assert nm == [_fr(x) for x in rule["N_rho"]] and all(nm[q] == em[q] / em[0] for q in range(3))
    for q in range(3):
        k6 = sum(float(pi) * math.sqrt(float(c[q] / c[0])) * math.sqrt(float(nm[q])) for pi, c in zip(p, cells))
        assert close(k6, rule["E_M_K6_over_K6_0"][q], 1e-12), q
        assert k6 <= float(em[q] / em[0]) * (1 + 1e-15), q
    core = example()["core"]
    if bank().point == EX_BASE_POINT:
        run = bank({"insurance": bank_rho()})
        assert run.point == core["point"], (run.point, core["point"])
        series = run.ctx.prep.driver_roots[B6][1]
        tl = run.ctx.timeline
        assert series[tl.index("2026Q3")] == core["rho_series_2026Q3"] and series[tl.index("2030Q1")] == 0.0


# ------------------------------------------------------------------ ядро против формулы в каждой клетке и квартале


def _driver_level(prep: Any, c: Any, lb: Any, q: int, wage: Any) -> float:
    """D_q — уровень базы строки-драйвера на конец квартала своим счётом: кредиты — ряд loans клетки; веса книг — Σ ω E
    по остаткам книг клетки; номинал — Π (1 + wage)^(1/4); q = 0 — уровень якоря базы (lb.end0)."""
    if q == 0:
        return lb.end0
    if lb.kind == "loans":
        return c.quarters["loans"][q]
    if lb.kind == "nominal":
        out = 1.0
        for x in range(1, q + 1):
            out *= (1 + wage[x]) ** 0.25
        return out
    assert lb.kind == "books", lb.kind
    return sum(w * c.books[b]["balance"][q] for b, w in lb.weights.items())


def check_cells(run: Any, roots: dict[str, Any]) -> int:
    """Каждая клетка и квартал сетки `run` с ключом `roots`: ведомая книга строки ключа — цепь E_q = E_(q−1) (1 +
    wage)^((1 − λ)/4) (D_q / D_(q−1))^λ (1 + ρ_q)^(1 − λ) (1e-12; ρ — заново по записи ключа, λ — связь строки книги,
    wage — мир клетки) и телескоп E_q / E_0 = (D_q / D_0)^λ (N^ρ_q)^(1 − λ) (1e-10); ряд vol_end_<строка> — D_q своим
    счётом (1e-12), на якоре — уровень якоря базы ровно; книга строки вне ключа — прежняя цепь. Возвращает число
    сверенных кварталов книг с корнем."""
    ctx = run.ctx
    tl, prep, book = ctx.timeline, ctx.prep, ctx.book
    spec = book.opt(DRIVERS) or {}
    rho = {line: rho_ref(roots[line], tl) for line in roots}
    keyed = {str(b): line for b, line in spec.items() if line in roots}
    assert {b: line for b, (line, _) in (prep.driver_roots or {}).items()} == keyed
    n = 0
    for c in run.cells:
        wage = ctx.worlds[c.world].wage
        for b, line in spec.items():
            b = str(b)
            lb, lam = prep.driven[b]
            assert lam == float(book.get(LINK[line]))
            e = c.books[b]["balance"]
            d = [_driver_level(prep, c, lb, q, wage) for q in range(tl.Q + 1)]
            if b in keyed:
                ends = c.quarters[END[line]]
                assert ends[0] == lb.end0, (c.label, ends[0], lb.end0)
                nom = 1.0
            for q in range(1, tl.Q + 1):
                want = e[q - 1] * (1 + wage[q]) ** ((1 - lam) / 4) * (d[q] / d[q - 1]) ** lam
                if b in keyed:
                    r = rho[line][q]
                    want *= (1 + r) ** (1 - lam)
                    nom *= (1 + wage[q]) ** 0.25 * (1 + r)
                    tele = (d[q] / d[0]) ** lam * nom ** (1 - lam)
                    assert close(e[q] / e[0], tele, 1e-10), (c.label, b, q, e[q] / e[0], tele)
                    assert close(ends[q], d[q], 1e-12), (c.label, line, q, ends[q], d[q])
                    n += 1
                assert close(e[q], want, 1e-12), (c.label, b, q, e[q], want)
    return n


def check_grid() -> None:
    """Фикстура с ключом страхования (связь 0,5; база — розничные кредитные книги): ядро против формулы в каждой клетке
    и квартале; связь 0, 0,3 и 1 — та же формула (при связи 0 книга — номинал с корнем); ρ ≡ 0 и ρ числом — та же
    формула; книга за строкой комиссий (база — кредиты юрлиц) с ключом комиссий — ряд vol_end_fees и цепь с корнем;
    книга дерева с ρ примера — каждая клетка и квартал (36 × 42); лёгкая сетка (проходы полосы) с ключом — те же
    оценки."""
    from model.grid import run_grid
    from tests.support_core_t import book_live
    run = t7(roots=T_RHO)
    assert check_cells(run, T_RHO) == 36 * run.ctx.timeline.Q
    light = run_grid(run.ctx.book, run.ctx.facts, book_live(run.ctx.book), summary=True)
    assert light.point == run.point and [c.v_ri for c in light.cells] == [c.v_ri for c in run.cells]
    for link in (0.0, 0.3, 1.0):
        check_cells(t7(roots=T_RHO, other__insurance_volume_link=link), T_RHO)
    for roots in ({"insurance": zero_of(T_RHO["insurance"])}, {"insurance": 0.012}):
        check_cells(t7(roots=roots), roots)
    fees = {"fees": {"2026Q3": 0.02, "2026Q4": -0.01, "LT": 0.003, "LT_from": 2027}}
    frun = P3.mix_run(volumes__liability_drivers={"corp_funds": "fees"}, fees__volume_base={"corp_loans": 1.0},
                      volumes__liability_driver_roots=fees)
    assert {b: line for b, (line, _) in frun.ctx.prep.driver_roots.items()} == {"corp_funds": "fees"}
    assert "vol_end_fees" in frun.cells[0].quarters and "vol_end_ins" not in frun.cells[0].quarters
    check_cells(frun, fees)
    rho = {"insurance": bank_rho()}
    brun = bank(rho)
    assert brun.ctx.prep.driven[B6][0].kind == "books"
    assert check_cells(brun, rho) == 36 * brun.ctx.timeline.Q


def check_continuity() -> None:
    """Непрерывность по связи строки: точка при λ = 0 и 1e-9, 1 − 1e-9 и 1 — до 1e-8 относительно (фикстура и книга
    дерева с ρ примера)."""
    rho = {"insurance": bank_rho()}
    for make, roots in ((lambda r, **k: t7(roots=r, **k), T_RHO), (bank, rho)):
        for a, b in ((0.0, 1e-9), (1.0 - 1e-9, 1.0)):
            x = make(roots, other__insurance_volume_link=a).point
            y = make(roots, other__insurance_volume_link=b).point
            assert close(x, y, 1e-8), (a, b, x, y)


# ------------------------------------------------------------------ слой M: правило ρ, неподвижная точка, миры


def _layer(run: Any) -> list[tuple[float, Any]]:
    prob = run.layers[MACRO].prob
    return [(prob[c.key], c) for c in run.cells if prob[c.key]]


def _wage_m(run: Any) -> Any:
    ctx = run.ctx
    return ctx.worlds[str(ctx.book.get("joint.macro_neutral_world"))].wage


def rho_rule(run: Any, line: str = "insurance") -> dict[str, Any]:
    """ρ правилом листа на сетке `run`: ρ_q = E_M[D_q] / E_M[D_(q−1)] / (1 + w^M_q)^(1/4) − 1, q = 1…2029К4 (E_M[D_0] =
    D_0 — уровень якоря), 6 знаков; с 2030 года 0. E_M — ожидание ряда vol_end_<строка> клеток под вероятностями слоя M;
    w^M — рост зарплат мира слоя."""
    tl = run.ctx.timeline
    wage = _wage_m(run)
    layer = _layer(run)
    em = [sum(p * c.quarters[END[line]][q] for p, c in layer) for q in range(tl.index(Q_END) + 1)]
    out: dict[str, Any] = {tl.period(q): round(em[q] / em[q - 1] / (1 + float(wage[q])) ** 0.25 - 1, 6)
                           for q in range(1, len(em))}
    out.update(LT=0.0, LT_from=LT_FROM)
    return out


def fixed_point(make: Any, rounds: int = 6) -> tuple[Any, dict[str, Any], list[float]]:
    """Неподвижная точка ρ (как лист вывода): ρ = 0 → сетка с ключом → ρ правилом → … до сдвига 0 или `rounds` кругов;
    сетка последнего ρ, ρ и сдвиги кругов."""
    traj: dict[str, Any] = {"LT": 0.0, "LT_from": LT_FROM}
    shifts: list[float] = []
    for _ in range(rounds):
        new = rho_rule(make(traj))
        shifts.append(max(abs(v - traj.get(k, 0.0)) for k, v in new.items() if k not in ("LT", "LT_from")))
        traj = new
        if shifts[-1] == 0.0:
            break
    return make(traj), traj, shifts


def check_layer_m(run: Any, b: str, line: str = "insurance", top: float = 2e-3) -> tuple[float, float, float]:
    """Слой M на ρ записи: N^ρ,M_q = Π (1 + w^M)^(1/4) (1 + ρ) против E_M[D_q] / D_0 до 2029К4 — до 1e-5 (запись 6
    знаков); E_M[К6_q] / К6_0 = E_M[(D_q / D_0)^λ] (N^ρ,M_q)^(1 − λ) (номинал слоя один: мир слоя один) и Йенсен
    E_M[(D / D_0)^λ] ≤ (E_M[D] / D_0)^λ; печать 1 − E_M[К6_q] / К6_0 ÷ E_M[D_q] / D_0 — не выше `top` (книга дерева:
    2e-3) и не ниже −1e-5 (ниже нуля — только округление записи ρ); с 2030К1 в каждой клетке — прежняя цепь ровно (корень 0: множитель ровно
    1). Возвращает (невязку, наибольшую и наименьшую печать)."""
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    lb, lam = prep.driven[b]
    series = prep.driver_roots[b][1]
    wage = _wage_m(run)
    layer = _layer(run)
    d0, e0 = lb.end0, prep.af.balances[b]
    q_end = tl.index(Q_END)
    nom, resid, gaps = 1.0, 0.0, []
    for q in range(1, q_end + 1):
        nom *= (1 + wage[q]) ** 0.25 * (1 + series[q])
        ed = sum(p * c.quarters[END[line]][q] for p, c in layer) / d0
        ek = sum(p * c.books[b]["balance"][q] for p, c in layer) / e0
        epow = sum(p * (c.quarters[END[line]][q] / d0) ** lam for p, c in layer)
        assert close(ek, epow * nom ** (1 - lam), 1e-10), (tl.period(q), ek, epow * nom ** (1 - lam))
        assert epow <= ed ** lam * (1 + 1e-12), (tl.period(q), epow, ed ** lam)
        resid = max(resid, abs(nom - ed))
        gap = 1 - ek / ed
        assert -1e-5 <= gap <= top, (tl.period(q), gap)
        gaps.append(gap)
    assert resid <= 1e-5, resid
    assert all(series[q] == 0.0 for q in range(q_end + 1, tl.Q + 1))
    for c in run.cells:
        w, e, d = ctx.worlds[c.world].wage, c.books[b]["balance"], c.quarters[END[line]]
        for q in range(q_end + 1, tl.Q + 1):
            assert e[q] == e[q - 1] * (1 + w[q]) ** ((1 - lam) * 0.25) * (d[q] / d[q - 1]) ** lam, (c.label, q)
    return resid, max(gaps), min(gaps)


def check_layer_bank() -> None:
    """Книга дерева: на ρ примера — слой M (`check_layer_m`; печать Йенсена в [0; 2e-3]; без ключа слой M к 2029К4 выше
    базы больше чем на 10 %); неподвижная точка ρ правилом листа от ρ = 0 — сдвиги кругов убывают до 0, слой M на ней
    тот же; на книге примера (точка без ключа — число примера) неподвижная точка — ρ примера ровно."""
    rho = bank_rho()
    scope = tree_scope()                                       # интеграция круга 11: неподвижная точка — на средствах книги дерева
    run = bank({"insurance": rho}, **scope)
    _, top, low = check_layer_m(run, B6)
    assert 0.0 <= low and top <= 2e-3, (low, top)
    base = bank(**scope)
    prep, tl = base.ctx.prep, base.ctx.timeline
    q = tl.index(Q_END)
    layer = _layer(base)
    lb = prep.driven[B6][0]
    ed = sum(p * _driver_level(prep, c, lb, q, None) for p, c in layer) / lb.end0
    ek = sum(p * c.books[B6]["balance"][q] for p, c in layer) / prep.af.balances[B6]
    assert ek / ed > 1.10, ek / ed
    fp, traj, shifts = fixed_point(lambda t: bank({"insurance": t}, **scope))
    assert shifts[-1] == 0.0 and all(b <= a for a, b in zip(shifts, shifts[1:])), shifts
    check_layer_m(fp, B6)
    if base.point == EX_BASE_POINT:
        assert traj == rho, {k: (traj.get(k), rho.get(k)) for k in rho if traj.get(k) != rho.get(k)}


def check_layer_fixture() -> None:
    """Фикстура: неподвижная точка ρ страхования от ρ = 0 — сдвиги кругов убывают до 0; слой M (`check_layer_m`; разброс
    базы по клеткам фикстуры шире, чем у книги, — печать Йенсена до 1e-2; неравенство Йенсена — то же)."""
    fp, _, shifts = fixed_point(lambda t: t7(roots={"insurance": t}))
    assert shifts[-1] == 0.0 and all(b <= a for a, b in zip(shifts, shifts[1:])), shifts
    check_layer_m(fp, "corp_funds", top=1e-2)


def world_relations(run: Any, b: str = B6, years: tuple[int, ...] = (2029, 2036)
                    ) -> dict[tuple[int, str], tuple[float, float]]:
    """Миры на мере IV квартала (веса аналитического слоя внутри мира): книга К6 к своей базе — E_W[К6] / E_W[D] — и
    строка страхования к своей — E_W[INS] / E_W[A] (поток квартала к среднему остатку базы). {(год, мир): (К6, строка)}."""
    ctx = run.ctx
    tl = ctx.timeline
    la = run.layers["analytical"]
    out = {}
    for y in years:
        q = max(x for x in tl.quarters_of_year(y) if 1 <= x <= tl.Q)
        for w, ww in la.world_weights.items():
            cw = [(la.prob[c.key] / ww, c) for c in run.cells if c.world == w and la.prob[c.key]]
            k6 = sum(p * c.books[b]["balance"][q] for p, c in cw) / sum(p * c.quarters[END["insurance"]][q] for p, c in cw)
            line = sum(p * c.quarters["ins"][q] for p, c in cw) / sum(p * c.quarters["vol_ins"][q] for p, c in cw)
            out[(y, w)] = (k6, line)
    return out


def check_worlds_bank() -> None:
    """Книга дерева: ρ общий для миров — отношения миров к миру M у книги К6 (К6 / D) с ключом и без — до 5e-3 (ключ
    двигает их только обратной связью); дрейф 2036 / 2029 у К6 к своей базе и у строки к своей — тот же до 5e-3 (класс
    1: книга дрейфует по мирам, как строка); миры по-прежнему расходятся (не все отношения 1)."""
    rho = bank_rho()
    keyed = world_relations(bank({"insurance": rho}))
    plain = world_relations(bank({"insurance": zero_of(rho)}))
    for y in (2029, 2036):
        for w in ("N", "H"):
            rk = keyed[(y, w)][0] / keyed[(y, "M")][0]
            rp = plain[(y, w)][0] / plain[(y, "M")][0]
            assert abs(rk - rp) <= 5e-3, (y, w, rk, rp)
            assert abs(rk - 1) > 0.02, (y, w, rk)
    for w in ("N", "H", "M"):
        k6 = keyed[(2036, w)][0] / keyed[(2029, w)][0]
        line = keyed[(2036, w)][1] / keyed[(2029, w)][1]
        assert abs(k6 - line) <= 5e-3, (w, k6, line)


# ------------------------------------------------------------------ входы прохода, память шага, отказы


def check_fingerprint() -> None:
    """Ключ, ρ и связь строки — входы прохода каждого мира (`path_keys`): полоса по записям не возьмёт чужой проход."""
    run = t7(roots=T_RHO)
    assert P3._moves_every_world(run, t7())
    other = {"insurance": dict(T_RHO["insurance"], **{"2027Q2": -0.0151})}
    for alt in (t7(roots=other), t7(roots=T_RHO, other__insurance_volume_link=0.3), t7(roots={"insurance": 0.0})):
        assert P3._moves_every_world(alt, run)


def check_memo_and_light() -> None:
    """Память оценок шага (фикстура с ключом, ограничение роста режет рост): сетка с выключенной памятью ≡ сетка с
    памятью — бит в бит (все клетки и ряды, vol_end_ins тоже); оценка шага при другой доле прироста с той же памятью —
    те же остатки книги К6, ряд vol_end_ins и средства, что без памяти; ряд vol_end_* — не в STEP_FLOWS (уровень
    конца квартала — функция состояния) и не в рядах строк памяти."""
    import dataclasses

    from model.cell import STEP_FLOWS, _Cell, initial_state, run_cell
    run = t7(roots=T_RHO)
    ctx = run.ctx
    assert ctx.prep.growth is not None and not ctx.prep.memo_off and not ctx.prep.opex_w_bal
    off = dataclasses.replace(ctx, prep=dataclasses.replace(ctx.prep, memo_off=True))
    cut = 0
    for c in run.cells:
        d = run_cell(off, c.world, c.regime, c.scenario)
        assert d.v_ri == c.v_ri and d.quarters == c.quarters, c.label
        cut += any((x or 0.0) > 0 for x in c.growth["cut_share"])
    assert cut, "ограничение роста не режет рост — проверка памяти пуста"
    cell = _Cell(ctx, "M", "downturn", "mid")
    st = initial_state(ctx.prep)
    memo: dict = {}
    first = cell.evaluate(st, 1, (), 1.0, memo=memo)[0]
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    assert first["_bal"]["corp_funds"] != fresh["_bal"]["corp_funds"], "доля прироста не сдвигает ведомую книгу"
    for name in ("vol_end_ins", "funds", "wholesale"):
        assert second[name] == fresh[name], name
    assert second["_bal"]["corp_funds"] == fresh["_bal"]["corp_funds"]
    lb = ctx.prep.driven["corp_funds"][0]
    assert fresh["vol_end_ins"] == sum(w * fresh["_bal"][b] for b, w in lb.weights.items())
    assert not set(END.values()) & set(STEP_FLOWS) and not set(END.values()) & set(ctx.prep.line_flows)


def check_refusals() -> None:
    """Схема: null ключа и строки, не словарь, строка вне {fees, insurance}, траектория без значений, не число — отказ;
    пустой словарь и ключ неактивного режима (К6 нет, ключ строки без ведомой книги) — не отказ; подмена null — отказ."""
    def book(value: Any, **more: Any) -> Any:
        return S.book_of(**{"volumes__liability_driver_roots": value, **more})

    book(T_RHO)                                                                # форма верна (К6 у фикстуры нет)
    book({"insurance": 0.0, "fees": {"2026Q3": 0.01, "LT": 0.0, "LT_from": 2027}})
    book({})                                                                   # пустой словарь — нет ключа
    book({"fees": 0.01}, **T_K6)                                               # строка ключа книгой не ведёт
    refused(lambda: book(None), "volumes.liability_driver_roots: null в читаемом пути")
    refused(lambda: book({"insurance": None}), "volumes.liability_driver_roots.insurance: null в читаемом пути")
    refused(lambda: book(0.01), "volumes.liability_driver_roots: ожидается словарь")
    refused(lambda: book([0.01]), "volumes.liability_driver_roots: ожидается словарь")
    refused(lambda: book({"insurance": {}}), "траектория — число или непустой словарь")
    refused(lambda: book({"retail": 0.0}), "volumes.liability_driver_roots.retail: незнакомый ключ")
    refused(lambda: book({"insurance_liab": 0.0}), "volumes.liability_driver_roots.insurance_liab: незнакомый ключ")
    refused(lambda: book({"insurance": {"2026Q3": "минус", "LT": 0.0}}), "ожидается число")
    base = S.book_of()
    refused(lambda: base.with_overrides({KEY: None}, create=True), "null")
    assert base.with_overrides({KEY: {"insurance": 0.0}}, create=True).get(f"{KEY}.insurance") == 0.0


# ------------------------------------------------------------------ выпуск


def check_release_with_pass7_key() -> None:
    """Выпуск фикстуры с книгой К6 и ключом прохода 7: контракт выполнен; ряд клетки vol_end_ins — в клетках прогона."""
    from model import payload as P
    from model.book import book_from_dict
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, contract, explained
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import put, t_dict
    data = t_dict()
    changes = {"valuation__terminal__fixed_growth_share": 0.0, "checks__mix_ratio_tolerance": 0.002, **T_K6,
               "volumes__liability_driver_roots": T_RHO}
    for k, v in changes.items():
        put(data, k.replace("__", "."), v)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    run = run_grid(book, facts)
    assert run.ctx.prep.driver_roots is not None
    expl = explained(check_gates(run, today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    d = P.build_payload(rel)
    assert contract(d) == [], contract(d)[:5]
    for c in rel.run.cells:
        assert "vol_end_ins" in c.quarters
