"""Проверки второго прохода ядра Совкомбанка (core-pass2): опт сверх структурной доли (К3), резерв по книгам (К7), RWA
гарантий (К5), терминал от стационарных ставок книг (К4), база связи по строке (К2), книга-обязательство за драйвером
строки (К6) и жетон DPS в машине роста (К1).

Одни и те же проверки зовут тесты (`tests/test_core_p2.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass2/example.json` — копия выхода
`example.py` агента методики, точная арифметика), выведенные независимо от кода ядра. Ключей прохода в книгах фикстур
нет (нет ключа — прежняя ветвь кода, бит в бит): проверки включают их подменой.
"""

from __future__ import annotations

import copy
import functools
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from model.book_schema import BookError, FactsError
from tests import support_core_t3 as S
from tests.support_core import fixture_book, fixture_facts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests" / "fixtures" / "core_pass2" / "example.json"
close = S.close
DAYS = 365.0


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (точная арифметика): разделы k1 … k7."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def num(x: Any) -> float:
    """Число примера: {v, exact} → точная дробь в float; число — как есть."""
    if isinstance(x, dict) and "exact" in x:
        return float(Fraction(x["exact"]))
    return float(x)


def frac(x: Any) -> Fraction:
    """Число примера точной дробью."""
    if isinstance(x, dict) and "exact" in x:
        return Fraction(x["exact"])
    return Fraction(x)


def refused(fn, words: str, kind: type = BookError) -> None:
    """Отказ `kind` (BookError по умолчанию) со словами `words` в сообщении."""
    try:
        fn()
    except kind as exc:
        assert words in str(exc), str(exc)[:600]
        return
    raise AssertionError(f"нет отказа «{words}»")


def _grid(book: Any, facts: Any = None, live: Any = None) -> Any:
    from model.grid import run_grid
    return run_grid(book, facts if facts is not None else fixture_facts(), live)


def _same_bits(a: Any, b: Any, rows: tuple[str, ...] = ("bv", "div", "rwa", "wholesale", "liquidity")) -> None:
    """Две сетки — одни числа бит в бит: оценки клеток и названные ряды кварталов."""
    assert a.point == b.point and a.low == b.low and a.high == b.high, (a.point, b.point)
    for x, y in zip(a.cells, b.cells):
        assert x.key == y.key and x.v_ri == y.v_ri and x.v_ddm == y.v_ddm, (x.label, x.v_ri, y.v_ri)
        for name in rows:
            assert x.quarters[name] == y.quarters[name], (x.label, name)


def _path_key(run: Any) -> bytes:
    from model.grid import path_inputs, path_key
    return path_key(path_inputs(run.ctx))


# ------------------------------------------------------------------ К3: опт сверх структурной доли (М§4.10)

WH_S = "volumes.wholesale_structural_to_funds"
WH_A = "volumes.wholesale_to_funds"


def check_wholesale_example() -> None:
    """Пример k3: опт — структурная часть s × средства и часть по нужде max(0, la_min − la⁰ − s × средства); правило
    «полная база по якорю, затем гашение сверх s при избытке» — та же сумма (тождество); при нехватке — как прежняя
    формула, при большом избытке — только структурная часть."""
    k3 = example()["k3"]
    funds, s, s_a = frac(k3["funds"]), frac(k3["s_structural"]), frac(k3["s_anchor"])
    for name, case in k3["cases"].items():
        la0, la_min = frac(case["la0_without_wh"]), frac(case["la_min"])
        want = s * funds + max(Fraction(0), la_min - la0 - s * funds)
        assert frac(case["wholesale_k3"]) == want, name
        old = s_a * funds + max(Fraction(0), la_min - la0 - s_a * funds)
        assert frac(case["wholesale_old"]) == old, name
    assert frac(k3["cases"]["big_surplus"]["wholesale_k3"]) == s * funds
    assert k3["cases"]["shortage"]["wholesale_k3"] == k3["cases"]["shortage"]["wholesale_old"]


@functools.lru_cache(maxsize=None)
def _wh_runs() -> tuple[Any, Any, Any, Any, float]:
    """Фикстура `core`: без ключа; структурная доля — половина доли якоря; та же доля книгой `wholesale_to_funds`;
    структурная доля, равная доле якоря."""
    book = fixture_book()
    anchor = float(book.get(WH_A))
    s = anchor / 2
    return (_grid(book), _grid(book.with_overrides({WH_S: s}, create=True)),
            _grid(book.with_overrides({WH_A: s})), _grid(book.with_overrides({WH_S: anchor}, create=True)), s)


def check_wholesale_identity() -> None:
    """Без ключа и при s = доле якоря — бит в бит; К3(s) ≡ книга с `wholesale_to_funds = s` бит в бит (то же число в
    той же строке шага); входы прохода меняются со структурной долей (ключ кэша проходов)."""
    base, half, as_book, at_anchor, _ = _wh_runs()
    _same_bits(at_anchor, base)
    _same_bits(half, as_book)
    assert half.point != base.point
    assert _path_key(half) != _path_key(base) and _path_key(at_anchor) != _path_key(half)


def check_wholesale_quarters() -> None:
    """Структурная доля — половина доли якоря: в каждой клетке и квартале опт = s × средства + опт по нужде (ряд
    `wholesale_extra`), ликвидность не ниже минимума; опт по нужде больше нуля только там, где ликвидность стоит ровно
    на минимуме, а при ликвидности выше минимума опт — ровно структурная часть (гашение полное). Терминал читает опт по
    нужде конца сетки (WT_Q). На фикстуре есть кварталы обоих видов."""
    from model.cell import cell_path
    _, half, _, _, s = _wh_runs()
    ctx = half.ctx
    lm = float(ctx.book.get("volumes.liquid_min_share"))
    Q = ctx.timeline.Q
    seen = {"need": 0, "surplus": 0}
    for c in half.cells:
        qs = c.quarters
        for q in range(1, Q + 1):
            funds, wh, extra = qs["funds"][q], qs["wholesale"][q], qs["wholesale_extra"][q]
            la = qs["securities"][q] + qs["liquidity"][q]
            la_min = lm * (qs["loans"][q] - qs["allowance"][q] + qs["other_assets"][q]) / (1 - lm)
            assert close(wh, s * funds + extra, 1e-12), (c.label, q)
            assert extra >= 0 and la >= la_min * (1 - 1e-12), (c.label, q, la, la_min)
            if extra > 1e-9:
                assert close(la, la_min, 1e-9), (c.label, q)
                seen["need"] += 1
            elif la > la_min * (1 + 1e-9):
                assert close(wh, s * funds, 1e-12), (c.label, q)
                seen["surplus"] += 1
    assert seen["need"] and seen["surplus"], seen
    c = half.cell("H", "norm", "schedule")
    path = cell_path(ctx, c.world, c.regime, c.scenario)
    assert path.terminal["wholesale_extra"] == c.quarters["wholesale_extra"][Q]


def check_wholesale_refusals() -> None:
    """Отказы: s < 0 — схема; s больше доли якоря — схема на книге с выведенной долей и подготовка прогона."""
    book = fixture_book()
    anchor = float(book.get(WH_A))
    refused(lambda: book.with_overrides({WH_S: -0.01}, create=True), "число ≥ 0")
    refused(lambda: book.with_overrides({WH_S: anchor * 1.01}, create=True), "больше доли опта якоря")
    from types import SimpleNamespace

    from model.cell import wholesale_structural
    stub = SimpleNamespace(opt=lambda path, default=None: anchor * 1.5 if path == WH_S else default,
                           get=lambda path: anchor)
    refused(lambda: wholesale_structural(stub), "от нуля до доли опта якоря")


# ------------------------------------------------------------------ К7: резерв по книгам (М§4.6)

ALLOW = "credit.allowance_by_book"
# покрытия фикстуры `core` (резерв к остатку книги по амортизированной стоимости): юрлица, ипотека, льготная ипотека,
# розница; сумма по книгам — 97 % резерва якоря (остаток вне книг R_0 — 3 %)
CORE_COV = {"corp_loans": 0.03, "mortgage": 0.01, "mortgage_sub": 0.006, "retail_loans": 0.09}


def _with_facts(facts: Any, patch: dict[str, Any]) -> Any:
    """Копия фактов с заменой узлов `файл.путь` (значение `None` — снять узел)."""
    from model.book import Facts, _digest
    files = copy.deepcopy(dict(facts.files))
    for dotted, value in patch.items():
        file, _, path = dotted.partition(".")
        cur = files[file]
        *head, last = path.split(".")
        for part in head:
            cur = cur.setdefault(part, {})
        if value is None:
            cur.pop(last, None)
        else:
            cur[last] = value
    return Facts(root=facts.root, files=files, digest=_digest(files))


def _ac0(af: Any, b: str) -> float:
    return af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0)


@functools.lru_cache(maxsize=None)
def allowance_facts(kind: str = "books") -> Any:
    """Факты фикстуры `core` с резервом якоря по книгам: `books` — покрытия `CORE_COV`, нормированные на 97 % резерва
    якоря; `equal` — одно покрытие у всех книг, R_0 = 0 (прежнее правило долей якоря)."""
    from model.book import anchor_facts
    facts = fixture_facts()
    af = anchor_facts(facts, fixture_book().get("nii.books"))
    loans = tuple(CORE_COV)
    if kind == "equal":
        total = sum(_ac0(af, b) for b in loans)
        raw = {b: af.allowance * _ac0(af, b) / total for b in loans}
    else:
        rough = {b: CORE_COV[b] * _ac0(af, b) for b in loans}
        scale = 0.97 * af.allowance / sum(rough.values())
        raw = {b: v * scale for b, v in rough.items()}
    calc = "фикстура core: резерв якоря по книгам — синтетический (тест К7)"
    return _with_facts(facts, {"balance.allowance_books": {b: {"v": v, "calc": calc} for b, v in raw.items()}})


def _allow_book(on: bool = True) -> Any:
    return fixture_book().with_overrides({ALLOW: {"enabled": on}}, create=True)


@functools.lru_cache(maxsize=None)
def _allow_run(kind: str) -> Any:
    if kind == "plain":
        return _grid(fixture_book(), allowance_facts("books"))
    if kind == "off":
        return _grid(_allow_book(False), fixture_facts())
    return _grid(_allow_book(), allowance_facts(kind))


# книги второй строки пути примера k7: розница сжимается, юрлица и ипотека растут (example.py, k7_example)
K7_PATH = {"cash_loans": Fraction(250), "cards": Fraction(165), "corp_loans": Fraction(1850), "mortgage": Fraction(440)}


def check_allowance_example() -> None:
    """Пример k7: покрытие книги якоря, остаток вне книг, резерв пути Σ cov_b E_b + R_0 × кредиты / кредиты якоря,
    якорь — точно; равное покрытие — прежнее правило долей якоря; списания пути — AL_(q−1) + LLP − AL_q."""
    k7 = example()["k7"]
    books = {b: frac(v) for b, v in k7["books0"].items()}
    allow = {b: frac(v) for b, v in k7["allowance0_by_book"].items()}
    al0 = frac(k7["AL0"])
    cov = {b: allow[b] / books[b] for b in books}
    for b, v in k7["coverage"].items():
        assert cov[b] == frac(v), b
    resid = al0 - sum(allow.values())
    assert resid == frac(k7["residual"]) and abs(resid) <= al0 / 20
    loans0 = sum(books.values())
    llp = frac(k7["llp_quarter"])
    prev = None
    for row in k7["rows"]:
        path = books if row["q"] == 0 else {**books, **K7_PATH}
        loans = sum(path.values())
        al = sum(cov[b] * path[b] for b in books) + resid * loans / loans0
        assert frac(row["AL_k7"]) == al and frac(row["AL_old"]) == al0 / loans0 * loans, row["q"]
        if prev is not None:
            assert frac(row["writeoff_k7"]) == prev + llp - al
        prev = al
    assert frac(k7["rows"][0]["AL_k7"]) == al0
    flat = al0 / loans0
    assert sum(flat * v for v in K7_PATH.values()) + sum(flat * books[b] for b in books if b not in K7_PATH) == \
        flat * sum({**books, **K7_PATH}.values())


def check_allowance_anchor_and_equal_cover() -> None:
    """Формула резерва ядра на остатках якоря даёт резерв якоря (1e-12); равное покрытие книг при R_0 = 0 — прежнее
    правило долей якоря во всех клетках и кварталах (1e-12); выключатель выключен — прежняя ветвь бит в бит, фактов
    резерва по книгам не нужно; ключ меняет входы прохода."""
    from model.cell import allowance_of
    run = _allow_run("books")
    prep, af = run.ctx.prep, run.ctx.prep.af
    assert prep.allow_cov is not None and abs(prep.allow_resid) > 0
    assert close(allowance_of(prep, af.balances, af.fv_loans, prep.loans_ac0), af.allowance, 1e-12)
    eq, plain = _allow_run("equal"), _allow_run("plain")
    for x, y in zip(eq.cells, plain.cells):
        assert close(x.v_ri, y.v_ri, 1e-10), (x.label, x.v_ri, y.v_ri)
        for q in range(1, run.ctx.timeline.Q + 1):
            assert close(x.quarters["allowance"][q], y.quarters["allowance"][q], 1e-12), (x.label, q)
    _same_bits(_allow_run("off"), _grid(fixture_book()))
    assert _path_key(run) != _path_key(plain)


def check_allowance_quarters() -> None:
    """Покрытия фикстуры: в каждой клетке и квартале резерв — Σ cov_b (E_b,q − FV_b,q) + R_0 × кредиты АС_q / кредиты
    АС якоря по остаткам книг конца квартала (FV — у книги с долей по справедливой стоимости), cov_b и R_0 — по фактам
    якоря; состав портфеля сдвигается — резерв расходится с долей якоря."""
    run = _allow_run("books")
    ctx = run.ctx
    af, prep = ctx.prep.af, ctx.prep
    facts = allowance_facts("books")
    raw = {b: facts.need("balance", f"allowance_books.{b}") for b in CORE_COV}
    cov = {b: raw[b] / _ac0(af, b) for b in CORE_COV}
    resid = af.allowance - sum(raw.values())
    ac0 = sum(af.balances[b] for b in CORE_COV) - af.fv_loans
    moved = False
    for c in run.cells:
        for q in range(1, ctx.timeline.Q + 1):
            fv = c.quarters["loans_fv"][q]
            books = {b: c.books[b]["balance"][q] for b in CORE_COV}
            want = sum(cov[b] * (books[b] - (fv if b == prep.fv_book else 0.0)) for b in CORE_COV) \
                + resid * c.quarters["loans_ac"][q] / ac0
            assert close(c.quarters["allowance"][q], want, 1e-12), (c.label, q, c.quarters["allowance"][q], want)
            share = af.allowance / ac0 * c.quarters["loans_ac"][q]
            moved = moved or abs(c.quarters["allowance"][q] / share - 1) > 1e-4
    assert moved, "состав портфеля фикстуры не сдвигается — проверка покрытия по книгам пуста"


def check_allowance_refusals() -> None:
    """Отказы фактов: нет узла у кредитной книги; резерв книги меньше нуля или не меньше её остатка; сумма по книгам
    расходится с резервом якоря больше чем на 5 %."""
    from model.book import anchor_facts
    book = _allow_book()
    base = allowance_facts("books")
    af = anchor_facts(base, book.get("nii.books"))

    def node(v: float) -> dict:
        return {"v": v, "calc": "тест К7"}

    gone = _with_facts(base, {"balance.allowance_books.mortgage": None})
    refused(lambda: _grid(book, gone), "allowance_books.mortgage", FactsError)
    neg = _with_facts(base, {"balance.allowance_books.mortgage": node(-1.0)})
    refused(lambda: _grid(book, neg), "положительное число", FactsError)
    big = _with_facts(base, {"balance.allowance_books.mortgage": node(af.balances["mortgage"])})
    refused(lambda: _grid(book, big), "не меньше её остатка", FactsError)
    off = _with_facts(base, {"balance.allowance_books.retail_loans": node(
        base.need("balance", "allowance_books.retail_loans") + 0.09 * af.allowance)})
    refused(lambda: _grid(book, off), "больше чем на 5 %", FactsError)


# ------------------------------------------------------------------ К5: RWA гарантий (М§4.11)

GUAR = "capital.rwa.guarantees"
# путь примера k5 (example.py, k5_example): книга corp_loans, драйвер «база комиссий» (кредиты, концы кварталов),
# дрейф плотности; RWA прочих статей якоря — одной суммой
K5_CORP = (None, 1800.0, 1830.0, 1850.0)
K5_LOANS = (3157.45, 3200.0, 3290.0, 3380.0)
K5_DN = (1.0, 1.0, 0.99, 0.98)
K5_OTHER = 2100.0
T_NOTIONAL = {"nonfinancial": 300.0, "financial": 50.0}   # фикстура core_t: книга corp_loans мала (G_0 = 200)


def guarantee_spec(**kw: Any) -> dict:
    """Ключ гарантий проверки: нефинансовые 3000 × 0,5, финансовые 500 × 1,0, вес 1,0 (G_0 = 2000), вырез из
    corp_loans, драйвер — база комиссий."""
    spec = {"enabled": True, "notional": {"nonfinancial": 3000.0, "financial": 500.0},
            "ccf": {"nonfinancial": 0.5, "financial": 1.0}, "weight": 1.0, "carve_from": "corp_loans",
            "driver": "fees_base"}
    spec.update(kw)
    return spec


def check_guarantees_example() -> None:
    """Пример k5 функциями ядра: G_0 = (N_нф CCF_нф + N_ф CCF_ф) × вес; вырез ω′ = ω − G_0 / E_0; RWA якоря тот же;
    путь — RWA с G_q = G_0 × D_q / D_0 по базе комиссий (кредиты, концы кварталов); драйвер = книга выреза — прежние
    RWA (1e-12); отказы выреза."""
    from model.capital import RwaWeights, carve_guarantees, guarantees_g0
    k5 = example()["k5"]
    inp = {k: num(v) for k, v in k5["inputs"].items()}
    g0 = guarantees_g0({"notional": {"nonfinancial": inp["n_nf"], "financial": inp["n_f"]},
                        "ccf": {"nonfinancial": inp["ccf_nf"], "financial": inp["ccf_f"]}, "weight": inp["weight"]})
    assert close(g0, num(k5["G0"]), 1e-12)
    rw = RwaWeights(loans={"corp_loans": inp["w_corp"]}, securities=0.0, liquidity=0.0, other_assets=1.0)
    cut = carve_guarantees(rw, g0, "corp_loans", inp["e_corp0"])
    assert close(cut.loans["corp_loans"], num(k5["w_carved"]), 1e-12) and cut.guar_g0 == g0
    corp = (inp["e_corp0"],) + K5_CORP[1:]
    assert close(cut.rwa({"corp_loans": corp[0]}, 0.0, 0.0, K5_OTHER, 1.0, 1.0, guar=g0), num(k5["rwa0"]), 1e-12)
    assert close(rw.rwa({"corp_loans": corp[0]}, 0.0, 0.0, K5_OTHER, 1.0, 1.0), num(k5["rwa0"]), 1e-12)
    for q, row in enumerate(k5["rows"]):
        g = g0 * K5_LOANS[q] / K5_LOANS[0]
        assert close(g, num(row["G"]), 1e-12), q
        key = cut.rwa({"corp_loans": corp[q]}, 0.0, 0.0, K5_OTHER, K5_DN[q], 1.0, guar=g)
        old = rw.rwa({"corp_loans": corp[q]}, 0.0, 0.0, K5_OTHER, K5_DN[q], 1.0)
        assert close(key, num(row["rwa_key"]), 1e-12) and close(old, num(row["rwa_old"]), 1e-12), q
        same = cut.rwa({"corp_loans": corp[q]}, 0.0, 0.0, K5_OTHER, K5_DN[q], 1.0, guar=g0 * corp[q] / corp[0])
        assert close(same, old, 1e-12), q
    refused(lambda: carve_guarantees(rw, inp["w_corp"] * inp["e_corp0"] * 1.01, "corp_loans", inp["e_corp0"]),
            "меньше нуля")
    refused(lambda: carve_guarantees(rw, g0, "mortgage", inp["e_corp0"]), "не кредитная книга")


def _guar_book(base: Any, **kw: Any) -> Any:
    return base.with_overrides({GUAR: guarantee_spec(**kw)}, create=True)


@functools.lru_cache(maxsize=None)
def _t_base() -> tuple[Any, Any]:
    from model.book import book_from_dict
    from tests.support_core_t import t_dict, t_facts
    return book_from_dict(t_dict(), facts=t_facts()), t_facts()


def _t_grid(book: Any) -> Any:
    from tests.support_core_t import book_live
    return _grid(book, _t_base()[1], book_live(book))


@functools.lru_cache(maxsize=None)
def _guar_runs(fixture: str, driver: str = "fees_base") -> tuple[Any, Any]:
    """Сетка без ключа и с ключом гарантий: `core` — дрейф плотности RWA, `core_t` — множитель RWA кризиса."""
    if fixture == "core":
        book = fixture_book()
        return _grid(book), _grid(_guar_book(book, driver=driver))
    book = _t_base()[0]
    return _t_grid(book), _t_grid(_guar_book(book, driver=driver, notional=T_NOTIONAL))


def _density_index(book: Any, tl: Any) -> list[float]:
    rate = float(book.get("capital.rwa.density_drift_rate"))
    until = int(book.get("capital.rwa.density_drift_until"))
    out = [1.0]
    for q in range(1, tl.Q + 1):
        out.append(out[-1] * ((1 + rate) ** 0.25 if tl.year(q) <= until else 1.0))
    return out


def _check_guar_quarters(base: Any, run: Any, driver: Any, g0: float = 2000.0) -> bool:
    """RWA якоря тот же; в каждой клетке и квартале RWA = [Σ ω′_b E_b + ω_бум S + ω_ликв L + прочие + G_q] × Dn_q × X_q
    × M_r,q, ω′ у книги выреза — ω − G_0 / E_0 по плотностям книги; ряд rwa_guar = G_q Dn_q X_q M_r,q; `driver(c, q)` —
    D^G_q / D^G_0."""
    ctx = run.ctx
    book, tl, prep = ctx.book, ctx.timeline, ctx.prep
    assert book.get("capital.rwa.fx.enabled") is False
    af = prep.af
    dens = {k: float(v) for k, v in book.get("capital.rwa.density").items()}
    w = {b: dens[b] for b in prep.roles.loans}
    w["corp_loans"] = dens["corp_loans"] - g0 / af.balances["corp_loans"]
    assert close(prep.rwa0, base.ctx.prep.rwa0, 1e-12)
    dn = _density_index(book, tl)
    oa_fixed = prep.rwa_w.oa_fixed
    mult_seen = False
    for c, b in zip(run.cells, base.cells):
        assert close(c.quarters["rwa"][0], b.quarters["rwa"][0], 1e-12) and c.quarters["rwa_guar"][0] == g0
        mult = prep.regimes[c.regime].rwa_mult
        for q in range(1, tl.Q + 1):
            g = g0 * driver(c, q)
            m = 1.0 if mult is None else mult[q]
            mult_seen = mult_seen or m != 1.0
            other = c.quarters["other_assets"][q]
            oa = (dens["other_assets"] * (other - oa_fixed) + dens.get("other_assets_fixed", 0.0) * oa_fixed
                  if oa_fixed else dens["other_assets"] * other)
            base_rwa = (sum(w[x] * c.books[x]["balance"][q] for x in w) + oa + g
                        + dens["securities"] * c.quarters["securities"][q] + dens["liquidity"] * c.quarters["liquidity"][q])
            assert close(c.quarters["rwa"][q], base_rwa * dn[q] * m, 1e-12), (c.label, q, c.quarters["rwa"][q])
            assert close(c.quarters["rwa_guar"][q], g * dn[q] * m, 1e-12), (c.label, q)
    return mult_seen


def check_guarantees_grid() -> None:
    """Драйвер — база комиссий (у фикстур — кредиты): RWA по тождеству квартала с G_q = G_0 × кредиты_q / кредиты_0 на
    фикстуре `core` (дрейф плотности) и `core_t` (множитель RWA кризиса — и на гарантиях); выключатель выключен —
    бит в бит; CCF меняет входы прохода."""
    def loans_ratio(c: Any, q: int) -> float:
        return c.quarters["loans"][q] / c.quarters["loans"][0]
    base, run = _guar_runs("core")
    assert max(_density_index(run.ctx.book, run.ctx.timeline)) > 1.0
    _check_guar_quarters(base, run, loans_ratio)
    t_base, t_run = _guar_runs("core_t")
    g0_t = (T_NOTIONAL["nonfinancial"] * 0.5 + T_NOTIONAL["financial"] * 1.0) * 1.0
    assert _check_guar_quarters(t_base, t_run, loans_ratio, g0_t), "у фикстуры core_t нет множителя RWA режима"
    off = _grid(fixture_book().with_overrides({GUAR: guarantee_spec(enabled=False)}, create=True))
    _same_bits(off, base)
    assert "rwa_guar" not in base.cells[0].quarters
    other = _grid(_guar_book(fixture_book(), ccf={"nonfinancial": 0.35, "financial": 1.0}))
    assert _path_key(other) != _path_key(run) and other.point != run.point


def check_guarantees_fees_line() -> None:
    """Драйвер — строка комиссий за четыре квартала (форма скептика, справочно): G_q = G_0 × Σ F_(q−3…q) / Σ F_(−3…0),
    кварталы до якоря — факт."""
    _, run = _guar_runs("core", "fees_line")
    hist = run.ctx.prep.hist["fees"]

    def fees4(c: Any, q: int) -> float:
        f = {x: hist[x] for x in range(-3, 1)}
        f.update({x: c.quarters["fees"][x] for x in range(1, q + 1)})
        return sum(f[x] for x in range(q - 3, q + 1)) / sum(hist[x] for x in range(-3, 1))
    _check_guar_quarters(_guar_runs("core")[0], run, fees4)


def check_guarantees_nominal_driver() -> None:
    """База комиссий — «номинал» (К2): уровень драйвера на конец квартала D^N_q / D^N_0 = Π (1 + wage)^(1/4) своим
    счётом; RWA по тождеству квартала с G_q = G_0 × D^N_q (находка проверки прохода: путь уровня номинала на концах
    кварталов не держала ни одна проверка)."""
    base_book = fixture_book().with_overrides({FEES_B: "nominal"}, create=True)
    base, run = _grid(base_book), _grid(_guar_book(base_book))
    assert run.ctx.prep.guar.base.kind == "nominal" and run.ctx.prep.guar.d0 == 1.0

    def index(c: Any, q: int) -> float:
        return _wage_index(run.ctx.worlds[c.world].wage, q)
    _check_guar_quarters(base, run, index)


def check_guarantees_anchor_and_refusals() -> None:
    """Номиналы `anchor` — узлы фактов capital.guarantees (нет узла — FactsError); отказы схемы: CCF вне [0; 1],
    вес не больше нуля, номинал меньше нуля, незнакомый драйвер; книга выреза не кредитная, плотность после выреза
    меньше нуля — отказ подготовки."""
    from model.book import book_from_dict
    from tests.support_core import fixture_dict
    facts = _with_facts(fixture_facts(), {"capital.guarantees": {
        "nonfinancial": {"v": 3000.0, "calc": "тест К5"}, "financial": {"v": 500.0, "calc": "тест К5"}}})
    data = fixture_dict()
    data["capital"]["rwa"]["guarantees"] = guarantee_spec(notional={"nonfinancial": "anchor", "financial": "anchor"})
    book = book_from_dict(data, facts=facts)
    assert book.anchors["capital.rwa.guarantees.notional.nonfinancial"] == 3000.0
    _, run = _guar_runs("core")
    assert _grid(book, facts).point == run.point
    refused(lambda: book_from_dict(data, facts=fixture_facts()), "capital.guarantees", FactsError)
    base = fixture_book()
    refused(lambda: _guar_book(base, ccf={"nonfinancial": 1.2, "financial": 1.0}), "доля от 0 до 1")
    refused(lambda: _guar_book(base, weight=0.0), "число > 0")
    refused(lambda: _guar_book(base, notional={"nonfinancial": -1.0, "financial": 0.0}), "число ≥ 0 или anchor")
    refused(lambda: _guar_book(base, driver="loans"), "незнакомое значение")
    refused(lambda: _grid(_guar_book(base, carve_from="liquidity")), "не кредитная книга")
    huge = {"nonfinancial": 1e6, "financial": 0.0}
    refused(lambda: _grid(_guar_book(base, notional=huge)), "меньше нуля")


# ------------------------------------------------------------------ К4: терминал от стационарных ставок книг (М§7)

STAT = "valuation.terminal.stationary_rates"


def check_stationary_example() -> None:
    """Пример k4 (одна книга актива с ρ = 0,1): при постоянной цели вход терминала по стационарной ставке продлевается
    ровно с ростом остатков (NII*_L сетки на год длиннее = NII*_L × (1 + g)^4), без ключа — нет (лаг ставки у конца
    сетки, экземпляр класса 3); ρ = 1 — ΔNII* = 0; смесь балансирующих за T — по стационарным ставкам."""
    k4 = example()["k4"]
    inp = {k: frac(v) for k, v in k4["inputs"].items()}
    paths = {}
    for name, nq in (("grid", 8), ("extended", 12)):
        y, e, rows = inp["y0"], inp["e0"], []
        for _ in range(nq):
            e_new = e * (1 + inp["g_q"])
            y = y + inp["rho"] * (inp["target"] - y)
            rows.append((y, (e + e_new) / 2))
            e = e_new
        last = rows[-4:]
        nii = sum((r * a * inp["dt"] for r, a in last), Fraction(0))
        d_nii = sum(((inp["target"] - r) * a * inp["dt"] for r, a in last), Fraction(0))
        assert frac(k4["paths"][name]["NII_L"]) == nii and frac(k4["paths"][name]["dNII_star"]) == d_nii, name
        paths[name] = (nii, nii + d_nii)
    growth = frac(k4["growth_year"])
    assert paths["extended"][1] == paths["grid"][1] * growth and paths["extended"][0] != paths["grid"][0] * growth
    sec = Fraction(45, 100)
    assert frac(k4["y_balancing"]["stationary"]) == sec * Fraction(8, 100) + (1 - sec) * Fraction(7, 100)


def _targets(ctx: Any, world: str, q: int) -> dict[str, float]:
    """Цели ставок книг квартала — своим кодом по формулам М§4.4 (ставка при ρ = 1)."""
    prep, book = ctx.prep, ctx.book
    w, h = ctx.worlds[world], ctx.worlds[prep.reference_world]
    x_w = sum(wt * (w.ref(prep.books[b]["ref"])[q] - h.ref(prep.books[b]["ref"])[q])
              for b, wt in prep.phi_weights.items())
    out = {}
    for b, spec in book.get("nii.books").items():
        ref, s = w.ref(spec["ref"])[q], prep.spreads[b][q]
        if spec["side"] == "asset":
            out[b] = ref + s - (prep.phi_assets * (ref - h.ref(spec["ref"])[q]) if spec.get("phi") else 0.0)
        else:
            out[b] = float(spec["beta"]) * ref + s + (prep.phi_liab * x_w if spec.get("phi") else 0.0)
    return out


@functools.lru_cache(maxsize=None)
def _stat_runs(rho1: bool = False) -> tuple[Any, Any]:
    """Фикстура `core_t` (сжатие φ на обеих сторонах): без ключа и с ключом; `rho1` — у всех книг ρ = 1."""
    book = _t_base()[0]
    if rho1:
        book = book.with_overrides({f"nii.books.{b}.rho": 1.0 for b in book.get("nii.books")})
    return _t_grid(book), _t_grid(book.with_overrides({STAT: True}, create=True))


def check_stationary_grid() -> None:
    """Фикстура `core_t`: ряды явных кварталов с ключом — бит в бит как без него; вход терминала — PBT_L + ΔNII*_L,
    ΔNII*_L = Σ_(q ∈ L) [Σ_актив (y* − y) Ē − Σ_пассив (c* − c) Ē] d_q / 365 по целям своего кода; смесь балансирующих и
    ставка опта за T — по целям квартала Q; печать клетки несёт и прежние лаговые ставки; TV_DDM − TV_RI = BV_Q;
    лёгкая сетка (проходы через входы прохода) — те же оценки; ключ меняет входы прохода."""
    from model.cell import cell_path
    base, run = _stat_runs()
    ctx, bctx = run.ctx, base.ctx
    tl = ctx.timeline
    Q, L = tl.Q, tl.year(tl.Q)
    names = list(ctx.book.get("nii.books"))
    sides = {b: ctx.book.get(f"nii.books.{b}.side") for b in names}
    sec = ctx.prep.sec_share
    moved = False
    for c, b in zip(run.cells, base.cells):
        for name in ("bv", "ci", "div", "rwa", "n20", "nii", "pbt"):
            assert c.quarters[name] == b.quarters[name], (c.label, name)
        d_nii = 0.0
        for q in range(1, Q + 1):
            if tl.year(q) != L:
                continue
            goal = _targets(ctx, c.world, q)
            gap = sum((goal[x] - c.books[x]["rate"][q]) * c.books[x]["avg"][q] * (1 if sides[x] == "asset" else -1)
                      for x in names)
            d_nii += gap * tl.d(q) / DAYS
        st = c.terminal_stationary
        assert close(st["d_nii_l"], d_nii, 1e-9, 1e-9), (c.label, st["d_nii_l"], d_nii)
        goal_q = _targets(ctx, c.world, Q)
        assert close(st["y_bal"], sec * goal_q["securities"] + (1 - sec) * goal_q["liquidity"], 1e-12)
        assert close(st["c_wh"], goal_q["wholesale"], 1e-12)
        bp, kp = cell_path(bctx, b.world, b.regime, b.scenario), cell_path(ctx, c.world, c.regime, c.scenario)
        assert st["y_bal_lagged"] == bp.terminal["y_balancing"] and st["c_wh_lagged"] == bp.terminal["c_wholesale"]
        assert close(kp.terminal["pbt_last_year"], bp.terminal["pbt_last_year"] + d_nii, 1e-12, 1e-9)
        assert kp.terminal["y_balancing"] == st["y_bal"] and kp.terminal["c_wholesale"] == st["c_wh"]
        assert close(c.tv_ddm - c.tv_ri, c.quarters["bv"][Q], 1e-9), c.label
        moved = moved or abs(d_nii) > 1e-6
        assert b.terminal_stationary is None
    assert moved, "у фикстуры нет лага ставок к концу сетки — проверка пуста"
    assert run.point != base.point and _path_key(run) != _path_key(base)
    from model.grid import run_grid
    from tests.support_core_t import book_live
    summary = run_grid(ctx.book, _t_base()[1], book_live(ctx.book), summary=True)
    assert summary.point == run.point and [x.v_ri for x in summary.cells] == [x.v_ri for x in run.cells]


def check_stationary_neutral_at_full_adjustment() -> None:
    """ρ = 1 у всех книг: ставка квартала — цель, ΔNII* = 0 и оценки с ключом те же, что без него (1e-12)."""
    base, run = _stat_runs(rho1=True)
    for c, b in zip(run.cells, base.cells):
        assert abs(c.terminal_stationary["d_nii_l"]) <= 1e-9 * max(1.0, abs(c.quarters["nii"][-1])), c.label
        assert close(c.v_ri, b.v_ri, 1e-12), (c.label, c.v_ri, b.v_ri)


# ------------------------------------------------------------------ К2: база связи по строке (М§4.7)

FEES_B, INS_B, SHARES = "fees.volume_base", "other.insurance_volume_base", "opex.line_shares"
T_LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")
T_ASSETS = T_LOANS + ("securities", "liquidity")


def check_lines_example() -> None:
    """Пример k2: рост строки F_q = F_(q−4) (1 + wage + корень + связь (v − wage)), v — рост базы г/г; «номинал»
    (A^N_q = A^N_(q−4)(1 + wage)) ≡ связь 0 точно; связь 1 со своей базой — рост ровно за базой плюс корень; смесь базы
    расходов A^C = (1 − s) B^C + s B^C_0 A^F / A^F_0 — на якоре ступени нет, при s = 0 и при базе строки = базе
    расходов — прежний рост."""
    k2 = example()["k2"]
    wage = {int(q): frac(v) for q, v in k2["wage"].items()}
    gvw = {int(q): frac(v) for q, v in k2["gvw"].items()}
    prev = {int(x): frac(v) for x, v in k2["fees_prev_year"].items()}
    bases = {name: {int(x): frac(v) for x, v in series.items()} for name, series in k2["bases"].items()}
    for name, base in bases.items():
        for link in (Fraction(1), Fraction(3, 10), Fraction(0)):
            got = k2["fees"][f"{name}|link={link}"]
            for q in range(1, 5):
                v = base[q] / base[q - 4] - 1
                assert frac(got["v"][str(q)]) == v
                assert frac(got["F"][str(q)]) == prev[q - 4] * (1 + wage[q] + gvw[q] + link * (v - wage[q]))
    for q in range(1, 5):
        assert bases["nominal"][q] / bases["nominal"][q - 4] - 1 == wage[q]
        assert k2["fees"]["nominal|link=1"]["F"][str(q)] == k2["fees"]["loans|link=0"]["F"][str(q)]
    s = frac(k2["opex_mix_share"])
    loans, iea = bases["loans"], bases["iea"]
    b_c = {x: Fraction(3) * loans[x] / 2 + Fraction(7, 10) * (iea[x] - loans[x]) for x in loans}
    for name, fee_base in (("loans", loans), ("nominal", bases["nominal"])):
        a_c = {x: (1 - s) * b_c[x] + s * b_c[0] * fee_base[x] / fee_base[0] for x in loans}
        assert a_c[0] == b_c[0]
        for x, v in k2["opex_mix"][name]["A_C"].items():
            assert frac(v) == a_c[int(x)], (name, x)


@functools.lru_cache(maxsize=None)
def _lines_run(key: str) -> Any:
    """Сетка фикстуры `core_t` на фактах с историей книг (`support_core_p1.t_facts_with_books`): `key` — набор ключей
    баз строк."""
    from model.book import book_from_dict
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import book_live, put, t_dict
    ov: dict[str, Any] = {
        "": {},
        "fees_loans": {FEES_B: "loans", INS_B: "loans"},
        "fees_nominal": {FEES_B: "nominal"},
        "fees_link0": {"fees.volume_link": 0.0},
        "fees_w_loans": {FEES_B: {b: 1.0 for b in T_LOANS}},
        "fees_w_loans7": {FEES_B: {b: 7.0 for b in T_LOANS}},
        "fees_iea": {FEES_B: "iea"},
        "ins_iea": {INS_B: "iea"},
        "fees_w_assets": {FEES_B: {b: 1.0 for b in T_ASSETS}},
        "shares0": {SHARES: {"fees": 0.0}},
        "shares_same": {FEES_B: "loans", SHARES: {"fees": 0.2}},
        "funds_nominal": {FEES_B: "funds", INS_B: "nominal", SHARES: {"fees": 0.2, "insurance": 0.1}},
    }[key]
    data = t_dict()
    for dotted, value in ov.items():
        put(data, dotted, value)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    return _grid(book, facts, book_live(book))


def _same_lines(a: Any, b: Any, rel: float, rows: tuple[str, ...] = ("fees", "ins", "opex")) -> None:
    for x, y in zip(a.cells, b.cells):
        assert close(x.v_ri, y.v_ri, rel), (x.label, x.v_ri, y.v_ri)
        for name in rows:
            for q in range(1, a.ctx.timeline.Q + 1):
                assert close(x.quarters[name][q], y.quarters[name][q], rel), (x.label, name, q)


def check_lines_equivalences() -> None:
    """Фикстура `core_t` (связи 0,5 / 0,5 / 0,4 с базой loans): своя база, равная link_base, — бит в бит; «номинал» ≡
    связь 0 (1e-12); веса 1 на кредитных книгах ≡ loans, на процентных активах ≡ iea, веса × 7 — тот же рост (1e-12);
    доли расходов 0 и доля на базе, равной базе расходов, — прежний рост расходов (1e-12); смесь на якоре — без
    ступени; ключ меняет входы прохода."""
    base = _lines_run("")
    same = _lines_run("fees_loans")
    assert [c.v_ri for c in same.cells] == [c.v_ri for c in base.cells]
    for x, y in zip(same.cells, base.cells):
        assert x.quarters["fees"] == y.quarters["fees"] and x.quarters["ins"] == y.quarters["ins"], x.label
        assert x.quarters["vol_fees"][1:] == tuple(
            (x.quarters["loans"][q - 1] + x.quarters["loans"][q]) / 2 for q in range(1, base.ctx.timeline.Q + 1))
    _same_lines(_lines_run("fees_nominal"), _lines_run("fees_link0"), 1e-12)
    _same_lines(_lines_run("fees_w_loans"), base, 1e-12)
    _same_lines(_lines_run("fees_w_loans7"), _lines_run("fees_w_loans"), 1e-12)
    _same_lines(_lines_run("fees_w_assets"), _lines_run("fees_iea"), 1e-12)
    assert [c.v_ri for c in _lines_run("shares0").cells] == [c.v_ri for c in base.cells]
    _same_lines(_lines_run("shares_same"), base, 1e-12)
    prep = _lines_run("funds_nominal").ctx.prep
    assert close(prep.hist_vol_mix[0], prep.hist_vol[0], 1e-12) and prep.memo_off is False
    assert _path_key(_lines_run("fees_nominal")) != _path_key(base)
    assert "vol_fees" not in base.cells[0].quarters and "vol_ins" not in _lines_run("fees_nominal").cells[0].quarters


def _hist_avg(facts: Any, tl: Any, node: str, anchor_end: float) -> dict[int, float]:
    ends = {0: anchor_end}
    for period, row in facts.file("balance")["history"].items():
        x = tl.index(period)
        if x < 0:
            ends[x] = float(row[node]["v"])
    return {x: (ends[x - 1] + ends[x]) / 2 for x in range(-3, 1)}


def check_lines_quarters() -> None:
    """Комиссии на базе «средства клиентов», страхование на «номинале», доли расходов 0,2 / 0,1 на базах строк: в каждой
    клетке и квартале A^F_q — полусумма средств концов квартала, A^I_q = A^I_(q−4)(1 + wage) (A^I_x≤0 = 1), рост строки
    — wage + корень + связь (A_q / A_(q−4) − 1 − wage), смесь A^C_q = 0,7 B_q + 0,2 B_0 A^F_q / A^F_0 + 0,1 B_0 A^I_q /
    A^I_0 (B — база link_base, кредиты) и рост расходов по ней; ряды vol_fees, vol_ins, vol_opex — эти базы."""
    from tests.support_core_p1 import t_facts_with_books
    run = _lines_run("funds_nominal")
    ctx = run.ctx
    tl, prep, book = ctx.timeline, ctx.prep, ctx.book
    facts = t_facts_with_books()
    af = prep.af
    funds0 = sum(af.balances[b] for b in prep.roles.funds)
    loans0 = sum(af.balances[b] for b in prep.roles.loans)
    hf, hb = _hist_avg(facts, tl, "funds", funds0), _hist_avg(facts, tl, "loans", loans0)
    l_f, l_i, l_c = (float(book.get(k)) for k in ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link"))
    for c in run.cells:
        wage = ctx.worlds[c.world].wage
        a_f, a_i, b = dict(hf), {x: 1.0 for x in range(-3, 1)}, dict(hb)
        a_c = {x: 0.7 * b[x] + 0.2 * b[0] * a_f[x] / a_f[0] + 0.1 * b[0] * a_i[x] / a_i[0] for x in range(-3, 1)}
        f = {x: prep.hist["fees"][x] for x in range(-3, 1)}
        ins = {x: prep.hist["ins"][x] for x in range(-3, 1)}
        opex = {x: prep.hist["opex"][x] for x in range(-3, 1)}
        for q in range(1, tl.Q + 1):
            qs = c.quarters
            a_f[q] = (qs["funds"][q - 1] + qs["funds"][q]) / 2
            a_i[q] = a_i[q - 4] * (1 + wage[q])
            b[q] = (qs["loans"][q - 1] + qs["loans"][q]) / 2
            a_c[q] = 0.7 * b[q] + 0.2 * b[0] * a_f[q] / a_f[0] + 0.1 * b[0] * a_i[q] / a_i[0]
            assert close(qs["vol_fees"][q], a_f[q], 1e-12) and close(qs["vol_ins"][q], a_i[q], 1e-12), (c.label, q)
            assert close(qs["vol_opex"][q], a_c[q], 1e-12), (c.label, q)
            if tl.year(q) not in prep.fees_override:
                g = wage[q] + prep.fees_gvw[q] + l_f * (a_f[q] / a_f[q - 4] - 1 - wage[q])
                assert close(qs["fees"][q], f[q - 4] * (1 + g), 1e-12), (c.label, q)
            want_i = ins[q - 4] * (1 + wage[q] + prep.ins_gvw[q] + l_i * (a_i[q] / a_i[q - 4] - 1 - wage[q]))
            assert close(qs["ins"][q], want_i, 1e-12), (c.label, q)
            want_c = opex[q - 4] * (1 + wage[q] + l_c * (a_c[q] / a_c[q - 4] - 1 - wage[q])) * (1 + prep.opex_real[q])
            assert close(qs["opex"][q], want_c, 1e-12), (c.label, q, qs["opex"][q], want_c)
            f[q], ins[q], opex[q] = qs["fees"][q], qs["ins"][q], qs["opex"][q]


def check_lines_memo_and_trace() -> None:
    """База строки на процентных активах (балансирующие книги): память оценок шага выключена — оценка квартала с
    дивидендом после оценки без него та же, что без памяти (квартал с долей прироста 0,5); оценка шага на копии
    состояния не оставляет рядов баз строк, принятая — несёт их (`STEP_FLOWS`)."""
    from model.cell import STEP_FLOWS, _Cell, initial_state
    run = _lines_run("fees_iea")
    ctx = run.ctx
    assert ctx.prep.memo_off and ctx.prep.growth is not None
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(ctx.prep)
    parts = ((40.0, 1, 1),)
    memo: dict = {}
    cell.evaluate(st, 1, (), 0.5, memo=memo)
    with_memo = cell.evaluate(st, 1, parts, 0.5, memo=memo)[0]
    fresh = cell.evaluate(st, 1, parts, 0.5)[0]
    assert with_memo["fees"] == fresh["fees"] and with_memo["opex"] == fresh["opex"], (with_memo["fees"], fresh["fees"])
    # то же у страхования на процентных активах (база комиссий — прежняя link_base: кредиты): память выключает и
    # база страхования (находка проверки прохода — условие держала только база комиссий)
    ctx_i = _lines_run("ins_iea").ctx
    assert ctx_i.prep.memo_off and ctx_i.prep.fees_line is None and ctx_i.prep.ins_line.kind == "iea"
    cell_i = _Cell(ctx_i, "N", "norm", "mid")
    st_i = initial_state(ctx_i.prep)
    memo_i: dict = {}
    cell_i.evaluate(st_i, 1, (), 0.5, memo=memo_i)
    with_memo_i = cell_i.evaluate(st_i, 1, parts, 0.5, memo=memo_i)[0]
    fresh_i = cell_i.evaluate(st_i, 1, parts, 0.5)[0]
    assert with_memo_i["ins"] == fresh_i["ins"], (with_memo_i["ins"], fresh_i["ins"])
    cell2 =_Cell(_lines_run("funds_nominal").ctx, "N", "norm", "mid")
    st2 = initial_state(cell2.p)
    cell2.probe(st2, 1)
    assert all(1 not in cell2.flows[k] for k in ("vol_fees", "vol_ins", "vol_mix")) and "vol_mix" in STEP_FLOWS
    row, after, kept = cell2.evaluate(st2, 1, (), 1.0)
    assert {"vol_fees", "vol_ins", "vol_mix"} <= set(kept) and 1 not in cell2.flows["vol_fees"]
    cell2.evaluate(st2, 1, (), 1.0, light=True)
    assert 1 not in cell2.flows["vol_ins"]


def check_lines_refusals() -> None:
    """Отказы: незнакомое слово базы и книга не из книг ЧПД — схема; все веса нулевые; сумма долей расходов ≥ 1; доля 1;
    нет истории книг у весов — FactsError; связь строки нулевая — свой ключ не читается."""
    from model.book import book_from_dict
    from tests.support_core_t import book_live, put, t_dict, t_facts
    refused(lambda: book_from_dict(put(t_dict(), FEES_B, "gdp"), facts=t_facts()), "не подходит ни под один вид")
    refused(lambda: book_from_dict(put(t_dict(), FEES_B, {"nope": 1.0}), facts=t_facts()), "не подходит ни под один")
    refused(lambda: book_from_dict(put(t_dict(), INS_B, {"auto": 0.0}), facts=t_facts()), "все веса нулевые")
    refused(lambda: book_from_dict(put(t_dict(), SHARES, {"fees": 0.6, "insurance": 0.5}), facts=t_facts()),
            "сумма долей")
    refused(lambda: book_from_dict(put(t_dict(), SHARES, {"fees": 1.0}), facts=t_facts()), "меньше 1")
    book = book_from_dict(put(t_dict(), FEES_B, {b: 1.0 for b in T_LOANS}), facts=t_facts())
    refused(lambda: _grid(book, t_facts(), book_live(book)), "остатков книг", FactsError)
    off = book_from_dict(put(put(t_dict(), FEES_B, {b: 1.0 for b in T_LOANS}), "fees.volume_link", 0.0),
                         facts=t_facts())
    assert _grid(off, t_facts(), book_live(off)).ctx.prep.fees_line is None


def check_guarantees_driver_is_the_carve_book() -> None:
    """К5 с базой комиссий — книгой выреза (веса {corp_loans: 1}, К2): RWA в каждой клетке и квартале — как без ключа
    гарантий (1e-12): G_q растёт ровно с книгой, из плотности которой вырезан."""
    base = fixture_book().with_overrides({FEES_B: {"corp_loans": 1.0}}, create=True)
    plain, run = _grid(base), _grid(_guar_book(base))
    for c, b in zip(run.cells, plain.cells):
        for q in range(0, run.ctx.timeline.Q + 1):
            assert close(c.quarters["rwa"][q], b.quarters["rwa"][q], 1e-12), (c.label, q)
        assert close(c.v_ri, b.v_ri, 1e-11), c.label


# ------------------------------------------------------------------ К6: книга-обязательство за драйвером строки (М§4.3)

DRIVERS = "volumes.liability_drivers"


def check_driven_example() -> None:
    """Пример k6: E_q = E_(q−1) (1 + wage)^((1 − λ)/4) (D_q / D_(q−1))^λ; связь 1 — ровно за драйвером, связь 0 — ровно
    за зарплатами (1e-12)."""
    k6 = example()["k6"]
    e0, wage, drv = float(k6["E0"]), [float(w) for w in k6["wage"]], [float(d) for d in k6["driver_end"]]
    for lam, path in k6["paths"].items():
        lam_f, e = float(lam), e0
        for q in range(1, 5):
            e *= (1 + wage[q - 1]) ** ((1 - lam_f) / 4) * (drv[q] / drv[q - 1]) ** lam_f
            assert close(e, float(path[q - 1]), 1e-12), (lam, q)
    assert close(float(k6["paths"]["1.0"][-1]) / e0, drv[4] / drv[0], 1e-12)


@functools.lru_cache(maxsize=None)
def _driven_run(key: str) -> Any:
    """Фикстура `core_t` (память оценок шага включена: база link_base — кредиты): средства юрлиц — ведомая книга за
    строкой страхования на базе «кредиты» со связью 0,5 (`ins`), 0 (`ins0`), 1 (`ins1`); без ключа (``)."""
    book = _t_base()[0]
    ov: dict[str, Any] = {
        "": {},
        "ins": {DRIVERS: {"corp_funds": "insurance"}, INS_B: "loans"},
        "ins0": {DRIVERS: {"corp_funds": "insurance"}, INS_B: "loans", "other.insurance_volume_link": 0.0},
        "ins1": {DRIVERS: {"corp_funds": "insurance"}, INS_B: "loans", "other.insurance_volume_link": 1.0},
        # база строки-драйвера — «номинал» (центр фрагмента книги методики: страхование на номинале со связью 1)
        "nom05": {DRIVERS: {"corp_funds": "insurance"}, INS_B: "nominal"},
        "nom1": {DRIVERS: {"corp_funds": "insurance"}, INS_B: "nominal", "other.insurance_volume_link": 1.0},
    }[key]
    return _t_grid(book.with_overrides(ov, create=True) if ov else book)


def _wage_index(wage: Any, q: int) -> float:
    """Номинал на конец квартала q своим счётом: Π_(x ≤ q) (1 + wage_x)^(1/4), на якоре — 1 (М§4.7, К2)."""
    out = 1.0
    for x in range(1, q + 1):
        out *= (1 + wage[x]) ** 0.25
    return out


def check_driven_nominal() -> None:
    """Драйвер — строка страхования на «номинале» (уровень на конец квартала D^N_q = D^N_(q−1) (1 + wage)^(1/4)): при
    любой связи λ книга растёт ровно с индексом зарплат мира — E_q = E_(q−1) (1 + wage_q)^(1/4), E_q / E_0 = Π (1 +
    wage)^(1/4) (1e-12); при λ = 1 это «ровно за драйвером» (находка проверки прохода: путь уровня номинала на концах
    кварталов не держала ни одна проверка)."""
    for key, lam in (("nom05", 0.5), ("nom1", 1.0)):
        run = _driven_run(key)
        ctx = run.ctx
        assert ctx.prep.driven is not None and ctx.prep.driven["corp_funds"][1] == lam
        assert ctx.prep.driven["corp_funds"][0].kind == "nominal"
        for c in run.cells:
            wage = ctx.worlds[c.world].wage
            e = c.books["corp_funds"]["balance"]
            for q in range(1, ctx.timeline.Q + 1):
                assert close(e[q], e[q - 1] * (1 + wage[q]) ** 0.25, 1e-12), (key, c.label, q, e[q])
                assert close(e[q] / e[0], _wage_index(wage, q), 1e-12), (key, c.label, q)
    assert _path_key(_driven_run("nom1")) != _path_key(_driven_run("ins1"))


def check_driven_quarters() -> None:
    """Ведомая книга средств юрлиц: в каждой клетке и квартале E_q = E_(q−1) (1 + wage)^((1 − λ)/4) (L_q / L_(q−1))^λ
    по кредитам конца квартала, λ — связь страхования; при λ = 1 — E_q / E_0 = L_q / L_0, при λ = 0 — рост с индексом
    зарплат (1e-12); книга — в средствах клиентов (сумма книг средств)."""
    for key, lam in (("ins", 0.5), ("ins0", 0.0), ("ins1", 1.0)):
        run = _driven_run(key)
        ctx = run.ctx
        assert ctx.prep.driven is not None and ctx.prep.driven["corp_funds"][1] == lam
        funds_books = ctx.prep.roles.funds
        for c in run.cells:
            wage = ctx.worlds[c.world].wage
            e = c.books["corp_funds"]["balance"]
            loans = c.quarters["loans"]
            idx = 1.0
            for q in range(1, ctx.timeline.Q + 1):
                want = e[q - 1] * (1 + wage[q]) ** ((1 - lam) / 4) * (loans[q] / loans[q - 1]) ** lam
                assert close(e[q], want, 1e-12), (key, c.label, q, e[q], want)
                idx *= (1 + wage[q]) ** 0.25
                if lam == 1.0:
                    assert close(e[q] / e[0], loans[q] / loans[0], 1e-12), (c.label, q)
                if lam == 0.0:
                    assert close(e[q] / e[0], idx, 1e-12), (c.label, q)
                assert close(c.quarters["funds"][q], sum(c.books[b]["balance"][q] for b in funds_books), 1e-12)
    assert _path_key(_driven_run("ins")) != _path_key(_driven_run(""))


def check_driven_memo() -> None:
    """Память стороны средств клиентов квартала (одна на все доли прироста): ведомая книга от доли прироста зависит —
    оценка шага при другой доле с той же памятью даёт те же остатки и сумму средств, что без памяти."""
    from model.cell import _Cell, initial_state
    ctx = _driven_run("ins").ctx
    assert not ctx.prep.memo_off and ctx.prep.growth is not None and ctx.prep.link_base != "iea"
    cell = _Cell(ctx, "N", "norm", "mid")
    st = initial_state(ctx.prep)
    memo: dict = {}
    first = cell.evaluate(st, 1, (), 1.0, memo=memo)[0]
    second = cell.evaluate(st, 1, (), 0.3, memo=memo)[0]
    fresh = cell.evaluate(st, 1, (), 0.3)[0]
    assert first["_bal"]["corp_funds"] != fresh["_bal"]["corp_funds"], "доля прироста не сдвигает ведомую книгу"
    assert second["_bal"]["corp_funds"] == fresh["_bal"]["corp_funds"] and second["funds"] == fresh["funds"]
    assert second["wholesale"] == fresh["wholesale"]


def check_driven_refusals() -> None:
    """Отказы: ведомая книга — не небалансирующий пассив вне пары физлиц (средства физлиц, опт, кредит); база драйвера
    — процентные активы, средства клиентов, веса на балансирующей книге или на самой ведомой книге; незнакомая строка
    — схема."""
    from tests.support_core_p1 import t_facts_with_books
    from tests.support_core_t import book_live
    book, facts = _t_base()[0], t_facts_with_books()

    def run(ov: dict) -> Any:
        probe = book.with_overrides(ov, create=True)
        return _grid(probe, facts, book_live(probe))
    for b in ("retail_term", "wholesale", "cards"):
        refused(lambda b=b: run({DRIVERS: {b: "insurance"}}), "ведомая книга")
    for base in ("iea", "funds", {"liquidity": 1.0, "cards": 1.0}, {"corp_funds": 1.0, "cards": 1.0}):
        refused(lambda base=base: run({DRIVERS: {"corp_funds": "fees"}, FEES_B: base}), "круг")
    refused(lambda: book.with_overrides({DRIVERS: {"corp_funds": "loans"}}, create=True), "незнакомое значение")


# ------------------------------------------------------------------ К1: жетон DPS в машине роста (М§4.13.2 п. 2а)

MIN_DPS = "dividends__min_dps"
BB_KEYS = {"dividends__buyback": {"enabled": True, "price": "world_forward",
                                  "amount": {"2026Q3": 2.0, "2026Q4": 3.0, "2027": 3.0, "2028": 3.0, "LT": 0.0,
                                             "LT_from": 2029}},
           "meta__labels__control__lines__buyback": "Выкуп акций"}


def _token_policy() -> Any:
    """Политика примера k1 (размещённые 20 000 млн, в обращении 19 000 млн, доля 0,2, ε = 0,5 без ввода, без
    догоняющей) — на политике фикстуры `core_t` (карта лагов квартального календаря)."""
    import dataclasses

    from model.dividends import Step, make_policy
    from model.paths import Trajectory
    book = _t_base()[0]
    pol = make_policy(book, 20000.0, 19000.0)
    return dataclasses.replace(pol, steps=(Step(Trajectory(0.2), 0.0),), deviation=Trajectory(0.0), epsilon=0.5,
                               excess_from=2000, ramp_years=1, catch_up=False, skip_in_shock=True)


def check_token_example() -> None:
    """Пример k1 функциями ядра: недостача года до жетона (`token_need`: кап прибылью, S_Y из закрытых, прошлых и
    базовых дивидендов квартала) — четыре случая; решения квартала (`decide_quarter`) с жетоном у носителя (h = 4):
    дивиденд носителя = база + жетон + избыток, избыток — за вычетом жетона, год выходит ровно на жетон, флаг решения;
    носитель — последнее решение модели за четвёртый квартал прибыли, в год шока его нет."""
    from model.dividends import OpenQuarter, decide_quarter, token_carrier, token_need
    k1 = example()["k1"]
    inp = {k: v for k, v in k1["inputs"].items()}
    n_iss, n_c = num(inp["n_iss"]), num(inp["n_c"])
    model_base = num(k1["div_base"])
    for name, case in k1["cases"].items():
        base_year = num(inp["base_year"]) if name in ("room_ok", "room_short") else \
            (-3.0 if name == "loss_year" else 0.5)
        got = token_need(min_dps=0.35, base_year=base_year, n_iss=n_iss, n_c=n_c, closed_dps=0.0,
                         prior_dps=num(inp["prior_dps"]), same_dps=model_base * 1000 / n_c)
        assert close(got.m_y, num(case["m_Y"]), 1e-12, 1e-15) and close(got.s_y, num(case["S_Y"]), 1e-12), name
        assert close(got.need, num(case["need"]), 1e-12, 1e-15), (name, got.need)
        paid = got.need > 0 and num(case["h_floor"]) >= model_base + got.need
        assert paid == case["paid"], name
    pol = _token_policy()
    due = [OpenQuarter(idx=i, period=f"2026Q{h}", year=2026, h=h, q=5, q_reg=6, q_pay=6)
           for i, h in ((1, 2), (2, 3), (3, 4))]
    bases = [num(inp["base_q"][str(h)]) for h in (2, 3, 4)]
    assert token_carrier(due, False, pol) == 2 and token_carrier(due, True, pol) is None
    token = num(k1["cases"]["room_ok"]["token"])
    decs = decide_quarter(pol, q=5, due=due, bases=bases, headroom=num(inp["h_ref"]),
                          headroom_final=num(k1["excess_after_token"]["h_fin"]), deferred=0.0, shock=False,
                          token=token, token_carrier=2, headroom_floor=10.0)
    for d, share in zip(decs, k1["shares"]):
        assert close(d.base_div, num(share["div"]), 1e-12)
    carrier = decs[2]
    x = num(k1["excess_after_token"]["X"])
    assert close(carrier.excess, x, 1e-12) and carrier.token == token and "dividend_token" in carrier.flags
    assert close(carrier.div, num(k1["shares"][2]["div"]) + token + x, 1e-12) and carrier.headroom_floor == 10.0
    assert decs[0].token == decs[1].token == 0.0 and "dividend_token" not in decs[0].flags
    year = num(inp["prior_dps"]) + sum(d.base_div + d.token for d in decs) * 1000 / n_c
    assert close(year, 0.35, 1e-12) and close(year, num(k1["cases"]["room_ok"]["dps_year"]), 1e-12)
    plain = decide_quarter(pol, q=5, due=due, bases=bases, headroom=num(inp["h_ref"]),
                           headroom_final=num(k1["excess_after_token"]["h_fin"]), deferred=0.0, shock=False)
    assert close(plain[2].excess, 0.5 * (num(k1["excess_after_token"]["h_fin"]) - model_base), 1e-12)
    refused(lambda: decide_quarter(pol, q=5, due=due, bases=bases, headroom=2.0, deferred=0.0, shock=False,
                                   token=1.0, token_carrier=0), "не у носителя")


def _year_base(c: Any, prep: Any, tl: Any, year: int) -> float:
    total = 0.0
    for x in tl.quarters_of_year(year):
        total += c.quarters["ni_sh"][x] if x >= 1 else prep.hist["ni_sh"][x]
    return total


def _check_token_run(run: Any, min_dps: float) -> int:
    """Тождества жетона на сетке: год с жетоном — ровно m_Y по своему счёту (DPS закрытых кварталов + Σ (база + жетон)
    решений года на акцию клетки квартала решения); база решений квартала с жетоном — в пределах запаса над требованием
    без запаса менеджмента; отказ по полу — запас меньше; дивиденд квартала в рядах = сумма решений квартала; в год
    шока жетона нет; инварианты сетки (в том числе dividend_bounds) — тихо. Возвращает число жетонов."""
    from model.checks import check_invariants
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    n_iss = prep.af.n_iss
    assert prep.policy.deduct_at1_after_tax is False
    paid = refused_n = 0
    for c in run.cells:
        n_q = c.quarters.get("n_out")
        shares = (lambda q: n_q[q]) if n_q is not None else (lambda q: prep.af.n_out)
        by_year: dict[int, list] = {}
        for d in c.decisions:
            by_year.setdefault(d.year, []).append(d)
        shock = prep.regimes[c.regime].shock_year
        for q in range(1, tl.Q + 1):
            decs = [d for d in c.decisions if d.q == q]
            assert close(c.quarters["div"][q], sum(d.div for d in decs), 1e-9, 1e-9), (c.label, q)
        for d in c.decisions:
            if d.headroom_floor is None:
                continue
            assert shock is None or tl.year(d.q) != shock, (c.label, d.period)
            year = d.year
            m_y = min(min_dps, max(0.0, _year_base(c, prep, tl, year)) * 1000 / n_iss)
            closed = prep.calendar.closed_dps.get(year, 0.0)
            same_q = [x for x in c.decisions if x.q == d.q and x.source == "model"]
            model_base = sum(x.base_div for x in same_q)
            if d.token > 0:
                paid += 1
                s_y = closed + sum((x.base_div + x.token) * 1000 / shares(x.q) for x in by_year[year])
                assert close(s_y, m_y, 1e-9), (c.label, d.period, s_y, m_y)
                assert model_base + d.token <= d.headroom_floor * (1 + 1e-12) + 1e-9, (c.label, d.period)
            else:
                refused_n += 1
                s_y = closed + sum(x.base_div * 1000 / shares(x.q) for x in by_year[year])
                need = (m_y - s_y) * shares(d.q) / 1000
                assert need > 0 and d.headroom_floor < model_base + need, (c.label, d.period, need)
        if any(d.token > 0 for d in c.decisions):
            assert "dividend_token" in c.flags
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    assert paid and refused_n, (paid, refused_n)
    return paid


def _check_token_floor(run: Any, sample: int = 6) -> None:
    """Запас жетона H_fl своим счётом: проход клетки до квартала решения, оценка шага квартала при наименьшей доле
    прироста без решений модели (записей реестра у фикстуры нет), запас над требованием без запаса менеджмента и без
    глиссады — min((Н20.0 − max(порог политики, пол)) × RWA, (Н20.1 с прибылью периода − пол) × RWA)."""
    from model.cell import _Cell
    ctx = run.ctx
    thr = float(ctx.book.get("dividends.policy.threshold"))
    lam_min = float(ctx.book.get("capital.growth_constraint.min_growth_scale"))
    done = 0
    for c in run.cells:
        for d in c.decisions:
            if d.headroom_floor is None or done >= sample:
                continue
            cell = _Cell(ctx, c.world, c.regime, c.scenario)
            st = cell.run(until=d.q - 1)[2] if d.q > 1 else None
            if st is None:
                from model.cell import initial_state
                st = initial_state(ctx.prep)
            row = cell.evaluate(st, d.q, (), lam_min, light=True)[0]
            sc = cell.sc
            want = min((row["n20"] - max(thr, sc.floor20[d.q])) * row["rwa"],
                       (row["n11_star"] - sc.floor11[d.q]) * row["rwa"])
            assert close(d.headroom_floor, want, 1e-9, 1e-9), (c.label, d.period, d.headroom_floor, want)
            done += 1
    assert done == sample, done


def check_token_grid() -> None:
    """Фикстура `core_t` (рост по капиталу, «дивиденд первым»): жетон 60 ₽ на акцию — тождества `_check_token_run`
    (жетоны и отказы по полу есть); то же при выкупе по цене мира (акции клетки квартала решения); жетон 0 — бит в бит
    как без ключа; без ограничения роста ключ не читается; ключ меняет входы прохода."""
    from tests.support_core_t3 import grid_of
    run = grid_of(**{MIN_DPS: {"LT": 60.0}})
    _check_token_run(run, 60.0)
    _check_token_floor(run)
    _check_token_run(grid_of(**{MIN_DPS: {"LT": 60.0}}, **BB_KEYS), 60.0)
    base, zero = grid_of(), grid_of(**{MIN_DPS: {"LT": 0.0}})
    assert [c.v_ri for c in zero.cells] == [c.v_ri for c in base.cells] and zero.point == base.point
    assert all(c.dps == b.dps for c, b in zip(zero.cells, base.cells))
    off = {"capital__growth_constraint__enabled": False}
    assert grid_of(**off, **{MIN_DPS: {"LT": 60.0}}).point == grid_of(**off).point
    assert grid_of(**off, **{MIN_DPS: {"LT": 60.0}}).ctx.prep.min_dps is None
    assert _path_key(run) != _path_key(grid_of(**{MIN_DPS: {"LT": 30.0}}))
    refused(lambda: _t_base()[0].with_overrides({"dividends.min_dps": {"2027": -0.1, "LT": 0.3}}, create=True),
            "меньше нуля")


def check_token_monotone() -> None:
    """Больше жетон — дивиденд года не меньше: в первом году с жетоном в обоих прогонах (30 и 60 ₽) DPS при 60 ₽ не
    меньше, чем при 30 ₽ (при том же признаке жетона)."""
    from tests.support_core_t3 import grid_of
    lo, hi = grid_of(**{MIN_DPS: {"LT": 30.0}}), grid_of(**{MIN_DPS: {"LT": 60.0}})
    seen = 0
    for a, b in zip(lo.cells, hi.cells):
        ya = {d.year for d in a.decisions if d.token > 0}
        yb = {d.year for d in b.decisions if d.token > 0}
        both = sorted(ya & yb)
        if both:
            y = both[0]
            assert b.dps[y] >= a.dps[y] - 1e-9, (a.label, y, a.dps[y], b.dps[y])
            seen += 1
    assert seen


def check_token_memory_reset() -> None:
    """Повтор прохода клетки (неподвижная точка цены выкупа «стоимость клетки», М§5.6): память DPS по годам
    сбрасывается вместе с рядами — второй проход даёт те же решения и жетоны."""
    from model.cell import _Cell
    from tests.support_core_t3 import grid_of
    run = grid_of(**{MIN_DPS: {"LT": 60.0}})
    c = next(x for x in run.cells if any(d.token > 0 for d in x.decisions))
    cell = _Cell(run.ctx, c.world, c.regime, c.scenario)
    first = cell.run()[1]
    cell.fresh_flows()
    cell.unsolved = []
    second = cell.run()[1]
    assert [(d.period, d.token, d.dps) for d in first] == [(d.period, d.token, d.dps) for d in second]
    assert any(d.token > 0 for d in second)
