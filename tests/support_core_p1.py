"""Проверки первого прохода ядра Совкомбанка (core-pass1): шаг хранения прогонов (М4), множители CoR по книгам (М7),
драйвер расходов по себестоимости книг (М13), постоянные в рублях части за концом сетки (терминал К-Т) и выкуп по
цене мира (М3).

Одни и те же проверки зовут тесты (`tests/test_core_p1.py`) и мутационный набор (`tests/mutations.py`); каждая —
тождество, закрытая формула или число примера методики (`tests/fixtures/core_pass1/example.json` — копия выхода
`example.py` агента методики, точная арифметика), выведенные независимо от кода ядра. Ключей прохода в книгах
фикстур нет (нет ключа — прежняя ветвь кода, бит в бит): проверки включают их подменой.
"""

from __future__ import annotations

import functools
import json
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from model import uncertainty as U
from model.book_schema import BookError
from tests import support_core_t3 as S
from tests.support_core import fixture_book, fixture_facts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "tests" / "fixtures" / "core_pass1" / "example.json"
close = S.close


@functools.lru_cache(maxsize=None)
def example() -> dict[str, Any]:
    """Пример методики прохода (точная арифметика): разделы m3, m4, m13, m7, terminal."""
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def num(x: Any) -> float:
    """Число примера: {v, exact} → точная дробь в float; число — как есть."""
    if isinstance(x, dict) and "exact" in x:
        return float(Fraction(x["exact"]))
    return float(x)


def refused(fn, words: str) -> None:
    """Отказ BookError со словами `words` в сообщении."""
    try:
        fn()
    except BookError as exc:
        assert words in str(exc), str(exc)[:400]
        return
    raise AssertionError(f"нет отказа «{words}»")


# ------------------------------------------------------------------ М4: шаг хранения прогонов (М§10)

DRAW_STEP = "valuation.uncertainty.draw_step"


def _half_up(x: float, step: str) -> float:
    """ROUND_HALF_UP(x / шаг) × шаг — своим кодом, в десятичной записи числа."""
    q = (Decimal(repr(x)) / Decimal(step)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(q * Decimal(step))


def _q7(values: list[float], q: float) -> float:
    s = sorted(values)
    h = (len(s) - 1) * q
    lo = int(h)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def check_draw_step_example() -> None:
    """Пример m4: прогоны в хранении при шаге 0,1 и 0,01 ₽ — округление половиной вверх (у 10,525 и 24,605 при шаге
    0,01 — ровно половина: вверх), медиана центров — квантиль тип 7 округлённых прогонов."""
    m4 = example()["m4"]
    lam = m4["lambda"]
    for step in ("0.1", "0.01"):
        want = m4[f"step_{step}"]
        lo, hi = U.stored_draws(m4["low"], float(step)), U.stored_draws(m4["high"], float(step))
        assert list(lo) == want["low_draws"] and list(hi) == want["high_draws"], (step, lo, hi)
        band = U.Band(axes=(), s=(), low_draws=lo, high_draws=hi, draws=len(lo), quantiles=(0.1, 0.25, 0.5, 0.75, 0.9),
                      lam=lam, draw_step=float(step))
        assert band.medians(lam)["central"] == want["median"], (step, band.medians(lam))


def check_draw_step_band() -> None:
    """Полоса фикстуры (6 прогонов): без ключа шаг 0,1 ₽ — и ключ 0,1 даёт те же массивы бит в бит; ключ 0,01 —
    те же точные сводки прогонов, каждый прогон в хранении — ROUND_HALF_UP точного до 0,01 (|ошибка| ≤ 0,005),
    медиана заголовка — квантиль тип 7 округлённых центров; шаг 0,05 схема не принимает."""
    book, facts = fixture_book(), fixture_facts()
    from model.grid import live_from_book
    live = live_from_book(book, facts)
    n = 6
    base = U.band(book, facts, live, draws=n, workers=1)
    assert base.draw_step == 0.1
    assert list(base.low_draws) == [_half_up(r["low"], "0.1") for r in base.rows]
    same = U.band(book.with_overrides({DRAW_STEP: 0.1}, create=True), facts, live, draws=n, workers=1)
    assert same.low_draws == base.low_draws and same.high_draws == base.high_draws and same.rows == base.rows
    fine = U.band(book.with_overrides({DRAW_STEP: 0.01}, create=True), facts, live, draws=n, workers=1)
    assert fine.draw_step == 0.01 and fine.rows == base.rows
    for kept, exact_key in ((fine.low_draws, "low"), (fine.high_draws, "high")):
        exact = [r[exact_key] for r in fine.rows]
        assert list(kept) == [_half_up(x, "0.01") for x in exact], exact_key
        assert all(abs(a - b) <= 0.005 + 1e-12 for a, b in zip(kept, exact))
    assert list(fine.low_draws) != list(base.low_draws)
    lam = fine.lam
    centres = [a + lam * (b - a) for a, b in zip(fine.low_draws, fine.high_draws)]
    assert fine.medians(lam)["central"] == _q7(centres, 0.5)
    refused(lambda: book.with_overrides({DRAW_STEP: 0.05}, create=True), "draw_step")


def check_draw_step_validator() -> None:
    """Валидатор выпуска: прогоны кратны шагу хранения — полю `headline.draw_step`, без поля — 0,1 ₽."""
    from model import payload as P
    d = json.loads((ROOT / "tests" / "fixtures" / "payload-sample.json").read_text(encoding="utf-8"))
    h = d["fair_value"]["headline"]
    grain = [x for x in P._headline_problems(d) if "шагу хранения" in x]
    assert grain == [], grain
    h["low_draws"][0] = round(h["low_draws"][0] + 0.05, 2)        # кратно 0,01, не кратно 0,1
    assert [x for x in P._headline_problems(d) if "шагу хранения 0.1" in x]
    h["draw_step"] = 0.01
    assert not [x for x in P._headline_problems(d) if "шагу хранения" in x]
    h["low_draws"][0] = h["low_draws"][0] + 0.003
    assert [x for x in P._headline_problems(d) if "шагу хранения 0.01" in x]


# ------------------------------------------------------------------ М7: множители CoR по книгам (М§4.6)

BOOK_REL = "credit.book_relative"
SEG = "credit.segment_relative"
DAYS = 365.0


class _Stub:
    """Книга-заглушка для функции нормировки: только ключ множителей по книгам."""

    def __init__(self, raw: dict[str, float], segments: bool = False):
        self.raw, self.segments = raw, segments

    def opt(self, path: str, default: Any = None) -> Any:
        return {"enabled": True, "by_book": dict(self.raw)} if path == BOOK_REL else default

    def get(self, path: str) -> Any:
        assert path == f"{SEG}.enabled", path
        return self.segments


def check_book_cor_example() -> None:
    """Пример m7 (факты якоря Совкомбанка): r̂_b = r_b / Σ w_b,0 r_b, Σ w r̂ = 1; резервы квартала Σ r̂ CoR Ē d/365 и
    реализованная CoR; книжная форма с множителями сегментов (0,55 / 1,60) — множители сегментной схемы; отказы."""
    from types import SimpleNamespace

    from model.cell import book_relative
    m7 = example()["m7"]
    anchor = {b: num(v) for b, v in m7["anchor_ac"].items()}
    raw = {b: num(v) for b, v in m7["raw"].items()}
    af = SimpleNamespace(balances=anchor, fv_loans=0.0, fv_book=None)
    roles = SimpleNamespace(loans=tuple(anchor))
    hat = book_relative(_Stub(raw), roles, af)
    for b, v in m7["normalized"].items():
        assert close(hat[b], num(v), 1e-12), (b, hat[b], num(v))
    total = sum(anchor.values())
    assert close(sum(anchor[b] / total * hat[b] for b in anchor), 1.0, 1e-12)
    qr = m7["quarter"]
    cor, dt = num(qr["cor_cell"]), num(qr["dt"])
    llp = sum(hat[b] * cor * num(a) * dt for b, a in qr["avg"].items())
    assert close(llp, num(qr["llp"]), 1e-12)
    assert close(llp / sum(num(a) for a in qr["avg"].values()) / dt, num(qr["cor_realized"]), 1e-12)
    seg_of = {"corp_loans": "corporate"}
    seg_raw = {b: (0.55 if seg_of.get(b) == "corporate" else 1.60) for b in anchor}
    eq = book_relative(_Stub(seg_raw), roles, af)
    want = m7["segment_equivalence"]["segment_mult"]
    for b in anchor:
        assert close(eq[b], num(want[seg_of.get(b, "retail")]), 1e-12), b
    refused(lambda: book_relative(_Stub(raw, segments=True), roles, af), "вместе")
    refused(lambda: book_relative(_Stub({**raw, "mortgage": 0.0}), roles, af), "не больше нуля")
    refused(lambda: book_relative(_Stub({b: v for b, v in raw.items() if b != "cards"}), roles, af), "не кредитные")


# сырые множители фикстуры `core` (четыре кредитные книги, кредиты по справедливой стоимости — в corp_loans)
CORE_RAW = {"corp_loans": 0.5, "mortgage": 0.4, "mortgage_sub": 0.9, "retail_loans": 2.5}
CORE_SEG = {"corp_loans": "corporate", "mortgage": "retail", "mortgage_sub": "retail", "retail_loans": "retail"}


def _core_book(key: str) -> Any:
    book = fixture_book()
    ov: dict[str, Any] = {}
    if key == "books":
        ov = {BOOK_REL: {"enabled": True, "by_book": dict(CORE_RAW)}}
    elif key == "books_as_segments":
        ov = {BOOK_REL: {"enabled": True, "by_book": {b: (0.55 if s == "corporate" else 1.6)
                                                      for b, s in CORE_SEG.items()}}}
    elif key == "segments":
        ov = {SEG: {"enabled": True, "corporate": 0.55, "retail": 1.6}}
    elif key == "books_equal":
        ov = {BOOK_REL: {"enabled": True, "by_book": {b: 3.7 for b in CORE_RAW}}}
    elif key == "books_off":
        ov = {BOOK_REL: {"enabled": False, "by_book": dict(CORE_RAW)}}
    return book.with_overrides(ov, create=True) if ov else book


@functools.lru_cache(maxsize=None)
def _core_grid(key: str) -> Any:
    from model.grid import run_grid
    return run_grid(_core_book(key), fixture_facts())


def _same_cells(a: Any, b: Any, rel: float, rows: tuple[str, ...] = ("llp", "fvc", "bv")) -> None:
    for x, y in zip(a.cells, b.cells):
        assert x.key == y.key
        assert close(x.v_ri, y.v_ri, rel) and close(x.v_ddm, y.v_ddm, rel), (x.label, x.v_ri, y.v_ri)
        for name in rows:
            for q in range(1, a.ctx.timeline.Q + 1):
                assert close(x.quarters[name][q], y.quarters[name][q], rel, 1e-12), (x.label, name, q)


def check_book_cor_equivalences() -> None:
    """Фикстура `core`: книжная форма с множителями сегментов (0,55 у кредитов юрлиц, 1,60 у розничных книг) —
    сегментная схема; все сырые множители равны — CoR как без схемы; выключатель выключен — прежняя ветвь бит в бит."""
    base = _core_grid("")
    _same_cells(_core_grid("books_as_segments"), _core_grid("segments"), 1e-12)
    _same_cells(_core_grid("books_equal"), base, 1e-12)
    off = _core_grid("books_off")
    assert [c.v_ri for c in off.cells] == [c.v_ri for c in base.cells] and off.point == base.point
    assert "cor_mix0" not in off.cells[0].quarters and "cor_mix0" not in base.cells[0].quarters


def check_book_cor_quarters() -> None:
    """Фикстура `core`, сырые множители по книгам: в каждой клетке и квартале резервы — Σ_b r̂_b CoR_c (Ē_b − F̄V_b)
    d/365, r̂ — от фактов якоря (кредиты по амортизированной стоимости); CoR_c — ряд cor_mix0, он же CoR клетки без
    схемы (наблюдений A-P2u у фикстуры нет: путь и κ-добавка); FVC — fv_factor × r̂ книги с долей СС × (CoR_c −
    опора) × F̄V d/365; резервы на составе якоря — CoR_c × кредиты АС × d/365."""
    run, plain = _core_grid("books"), _core_grid("")
    ctx = run.ctx
    af, tl = ctx.prep.af, ctx.timeline
    loans = tuple(CORE_RAW)
    ac0 = {b: af.balances[b] - (af.fv_loans if b == "corp_loans" else 0.0) for b in loans}
    tot = sum(ac0.values())
    norm = sum(ac0[b] / tot * CORE_RAW[b] for b in loans)
    hat = {b: CORE_RAW[b] / norm for b in loans}
    assert close(sum(ac0[b] / tot * hat[b] for b in loans), 1.0, 1e-12)
    assert af.fv_loans > 0 and ctx.prep.fv_book == "corp_loans"
    factor = float(ctx.book.get("credit.fv_loans_factor"))
    kappa_seen = False
    for c, p in zip(run.cells, plain.cells):
        for q in range(1, tl.Q + 1):
            d = tl.d(q) / DAYS
            cor = c.quarters["cor_mix0"][q]
            assert close(cor, p.quarters["cor"][q], 1e-12), (c.label, q)
            fv = c.quarters["loans_fv_avg"][q]
            want = sum(hat[b] * cor * (c.books[b]["avg"][q] - (fv if b == "corp_loans" else 0.0)) for b in loans) * d
            assert close(c.quarters["llp"][q], want, 1e-12, 1e-12), (c.label, q, c.quarters["llp"][q], want)
            ref = ctx.prep.fv_ref_cor[q]
            assert close(c.quarters["fvc"][q], factor * hat["corp_loans"] * (cor - ref) * fv * d, 1e-12, 1e-12)
            assert close(c.quarters["llp_mix0"][q], cor * c.quarters["loans_ac_avg"][q] * d, 1e-12, 1e-12)
            kappa_seen = kappa_seen or abs(cor - ctx.prep.regimes[c.regime].cor_engine[q]) > 1e-6
    assert kappa_seen, "у фикстуры нет клетки с κ-добавкой — проверка множителя на всю CoR пуста"


def check_book_cor_gate_and_levels() -> None:
    """Узел уровней при ключе несёт CoR на составе якоря (резервы при CoR клетки к кредитам АС); гейт окна фактов
    сверяет с коридором её, а не реализованную CoR, и печатает обе (М§4.6, §14.2); без ключа строки нет."""
    from model.checks import _window_backtest_gate
    from model.grid import run_grid
    from model.levels import levels
    y = _core_grid("").ctx.timeline.last_year - 2
    gate = {"checks.window_backtest": {"from_year": y, "cor": [0.0, 1.0], "cir": [0.0, 5.0]}}
    probe = _core_book("books").with_overrides(gate, create=True)
    run = run_grid(probe, fixture_facts())
    row = levels(run)["rows"]["macro_neutral"]
    assert "cor_mix0" in row and abs(row["cor_mix0"] - row["cor"]) > 1e-5, row
    tight = [row["cor_mix0"] - 1e-7, row["cor_mix0"] + 1e-7]
    run2 = run_grid(probe.with_overrides({"checks.window_backtest.cor": tight}), fixture_facts())
    f = _window_backtest_gate(run2)
    assert not f.fired and f.detail["cor_mix0"] == row["cor_mix0"] and f.detail["cor"] == row["cor"], f.message
    assert "на составе якоря" in f.message and "на составе клеток" in f.message
    plain = run_grid(fixture_book().with_overrides(gate, create=True), fixture_facts())
    assert "cor_mix0" not in levels(plain)["rows"]["macro_neutral"]


def check_book_cor_schema() -> None:
    """Схема ключа: выключатель выключен — множители не читаются (null допустим); включён вместе с сегментами,
    набор книг не равен кредитным книгам или множитель не больше нуля — отказ (М§4.6, прил. A)."""
    book = fixture_book()
    off = book.with_overrides({BOOK_REL: {"enabled": False, "by_book": None}}, create=True)
    assert off.get(f"{BOOK_REL}.enabled") is False
    on = {"enabled": True, "by_book": dict(CORE_RAW)}
    refused(lambda: book.with_overrides({BOOK_REL: on, SEG: {"enabled": True, "corporate": 0.55, "retail": 1.6}},
                                        create=True), "вместе")
    refused(lambda: book.with_overrides({BOOK_REL: {"enabled": True, "by_book": None}}, create=True), "null")
    short = {b: v for b, v in CORE_RAW.items() if b != "mortgage"}
    refused(lambda: book.with_overrides({BOOK_REL: {"enabled": True, "by_book": short}}, create=True), "mortgage")
    refused(lambda: book.with_overrides({BOOK_REL: {"enabled": True, "by_book": {**CORE_RAW, "mortgage": 0.0}}},
                                        create=True), "число > 0")


# ------------------------------------------------------------------ М13: драйвер расходов по себестоимости книг (М§4.7)

OPEX_W = "opex.volume_weights"
T_LOANS = ("cards", "cash_loans", "auto", "mortgage", "sme_loans", "corp_loans")
T_ASSETS = T_LOANS + ("securities", "liquidity")
T_FUNDS = ("retail_current", "retail_term", "corp_funds")
# веса проверки: кредитные книги дороже, ликвидность (балансирующая) — с весом, средства юрлиц — с весом
T_WEIGHTS = {"cards": 3.0, "cash_loans": 3.0, "auto": 2.0, "mortgage": 0.7, "sme_loans": 1.5, "corp_loans": 1.0,
             "liquidity": 0.5, "corp_funds": 0.25}


def check_opex_weights_example() -> None:
    """Пример m13: веса, нормированные на квартале якоря (ω̂ = ω Σ Ē_0 / Σ ω Ē_0), и взвешенная база истории A^C_x,
    x = −3…0, по концам кварталов книг (конец якоря — остатки якоря) — функцией ядра; отказы: книга не из книг ЧПД,
    все веса нулевые, нет конца квартала у книги с весом."""
    from model.cell import _weighted_history
    from model.timeline import make_timeline
    m13 = example()["m13"]
    ends = {b: [num(v) for v in row] for b, row in m13["inputs"]["ends_x_minus4_to_4"].items()}
    weights = {b: num(v) for b, v in m13["inputs"]["weights"].items()}
    books = {b: {} for b in ends}
    hist = {x: {b: ends[b][x + 4] for b in ends} for x in range(-4, 0)}
    anchor = {b: ends[b][4] for b in ends}
    tl = make_timeline(fixture_book())
    w_hat, base = _weighted_history(weights, books, hist, anchor, tl)
    norm = num(m13["norm_factor"])
    for b, v in m13["weights_normalized_at_anchor"].items():
        assert close(w_hat[b], num(v), 1e-12), (b, w_hat[b])
    for x in range(-3, 1):
        assert close(base[x], num(m13["weighted_base"][str(x)]) * norm, 1e-12), (x, base[x])
    assert close(base[0], sum((ends[b][3] + ends[b][4]) / 2 for b in ends), 1e-12)
    _, base7 = _weighted_history({b: 7 * w for b, w in weights.items()}, books, hist, anchor, tl)
    assert all(close(base7[x], base[x], 1e-12) for x in base)
    refused(lambda: _weighted_history({"nope": 1.0}, books, hist, anchor, tl), "не книги nii.books")
    refused(lambda: _weighted_history({b: 0.0 for b in weights}, books, hist, anchor, tl), "все веса нулевые")
    from model.book_schema import FactsError
    try:
        _weighted_history(weights, books, {x: {b: v for b, v in row.items() if b != "auto"} for x, row in hist.items()},
                          anchor, tl)
    except FactsError as exc:
        assert "auto" in str(exc)
    else:
        raise AssertionError("нет отказа FactsError при нехватке истории книги")


@functools.lru_cache(maxsize=None)
def t_facts_with_books() -> Any:
    """Факты фикстуры `core_t` с концами кварталов по книгам в истории баланса (`balance.history.<период>.books`):
    кредитные книги — в доле якоря от кредитов конца, прочие процентные активы — от разности процентных активов и
    кредитов, средства клиентов — от средств, опт — с шагом 3 % в квартал; узлы `loans` и `iea` истории — суммы тех
    же книг (история согласована с базами link_base)."""
    import copy

    from model.book import Facts, _digest
    from tests.support_core_t import t_facts
    facts = t_facts()
    files = copy.deepcopy(dict(facts.files))
    bal = files["balance"]
    anchor = {b: float(bal["books"][b]["v"]) for b in bal["books"]}
    loans0 = sum(anchor[b] for b in T_LOANS)
    other0 = sum(anchor[b] for b in T_ASSETS if b not in T_LOANS)
    funds0 = sum(anchor[b] for b in T_FUNDS)
    calc = "фикстура core_t: концы кварталов по книгам — синтетические, в доле якоря (тест М13)"
    for i, (period, row) in enumerate(sorted(bal["history"].items())):
        r_loans = float(row["loans"]["v"]) / loans0
        r_other = (float(row["iea"]["v"]) - float(row["loans"]["v"])) / other0
        r_funds = float(row["funds"]["v"]) / funds0
        ends = {}
        for b, v in anchor.items():
            ratio = (r_loans if b in T_LOANS else r_other if b in T_ASSETS else r_funds if b in T_FUNDS
                     else 1 - 0.03 * (len(bal["history"]) - 1 - i))
            ends[b] = v * ratio
        row["books"] = {b: {"v": v, "calc": calc} for b, v in ends.items()}
        row["loans"]["v"] = sum(ends[b] for b in T_LOANS)
        row["iea"]["v"] = sum(ends[b] for b in T_ASSETS)
    return Facts(root=facts.root, files=files, digest=_digest(files))


T_LINKS_OFF = {"fees.volume_link": 0.0, "other.insurance_volume_link": 0.0}


@functools.lru_cache(maxsize=None)
def _t_grid(key: str) -> Any:
    """Сетка фикстуры `core_t` на фактах с историей книг: `key` — набор ключей связи расходов."""
    from model.book import book_from_dict
    from model.grid import run_grid
    from tests.support_core_t import book_live, put, t_dict
    data = t_dict()
    ov: dict[str, Any] = {}
    if key in ("iea", "w_assets"):
        ov = {**T_LINKS_OFF, "volumes.link_base": "iea" if key == "iea" else "loans"}
        if key == "w_assets":
            ov[OPEX_W] = {b: 1.0 for b in T_ASSETS}
    elif key in ("loans", "w_loans"):
        ov = {**T_LINKS_OFF, "volumes.link_base": "loans"}
        if key == "w_loans":
            ov[OPEX_W] = {b: 1.0 for b in T_LOANS}
    elif key == "w":
        ov = {OPEX_W: dict(T_WEIGHTS)}
    elif key == "w7":
        ov = {OPEX_W: {b: 7 * w for b, w in T_WEIGHTS.items()}}
    for dotted, value in ov.items():
        put(data, dotted, value)
    facts = t_facts_with_books()
    book = book_from_dict(data, facts=facts)
    return run_grid(book, facts, book_live(book))


def _same_opex(a: Any, b: Any, rel: float) -> None:
    Q = a.ctx.timeline.Q
    for x, y in zip(a.cells, b.cells):
        assert close(x.v_ri, y.v_ri, rel), (x.label, x.v_ri, y.v_ri)
        for q in range(1, Q + 1):
            assert close(x.quarters["opex"][q], y.quarters["opex"][q], rel), (x.label, q)
            assert close(x.quarters["fees"][q], y.quarters["fees"][q], rel), (x.label, q)


def check_opex_weights_equivalences() -> None:
    """Фикстура `core_t`, связи комиссий и страхования выключены: веса 1 на процентных активах — расходы базы
    `iea`; веса 1 на кредитных книгах — расходы базы `loans`; веса × 7 — те же расходы (1e-12)."""
    _same_opex(_t_grid("w_assets"), _t_grid("iea"), 1e-12)
    _same_opex(_t_grid("w_loans"), _t_grid("loans"), 1e-12)
    _same_opex(_t_grid("w7"), _t_grid("w"), 1e-12)
    assert "vol_opex" in _t_grid("w").cells[0].quarters and "vol_opex" not in _t_grid("loans").cells[0].quarters


def check_opex_weights_quarters() -> None:
    """Фикстура `core_t`, веса книг с весом у ликвидности (балансирующая) и у средств юрлиц: в каждой клетке и квартале
    расходы — C_(q−4) (1 + wage + link (A^C_q / A^C_(q−4) − 1 − wage)) (1 + real), A^C_q = Σ ω̂_b Ē_b,q по средним
    книг клетки (балансирующие — средние квартала ЧПД), A^C_x≤0 — по концам кварталов фактов теми же весами;
    ω̂ — от квартала якоря; ряд vol_opex — A^C_q. Комиссии — по прежней базе связи (кредиты): веса их не трогают."""
    run = _t_grid("w")
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    facts = t_facts_with_books()
    bal = facts.file("balance")
    ends = {0: {b: float(bal["books"][b]["v"]) for b in T_WEIGHTS}}
    for period, row in bal["history"].items():
        x = tl.index(period)
        if x < 0:
            ends[x] = {b: float(row["books"][b]["v"]) for b in T_WEIGHTS}
    avg0 = {b: (ends[-1][b] + ends[0][b]) / 2 for b in T_WEIGHTS}
    norm = sum(avg0.values()) / sum(T_WEIGHTS[b] * avg0[b] for b in T_WEIGHTS)
    w_hat = {b: T_WEIGHTS[b] * norm for b in T_WEIGHTS}
    hist = {x: sum(w_hat[b] * (ends[x - 1][b] + ends[x][b]) / 2 for b in T_WEIGHTS) for x in range(-3, 1)}
    link = float(ctx.book.get("opex.volume_link"))
    link_f = float(ctx.book.get("fees.volume_link"))
    assert prep.opex_w_bal and link > 0 and link_f > 0
    for c in run.cells:
        wage = ctx.worlds[c.world].wage
        base = dict(hist)
        opex = {x: prep.hist["opex"][x] for x in range(-3, 1)}
        loans_end = {q: c.quarters["loans"][q] for q in range(0, tl.Q + 1)}
        for q in range(1, tl.Q + 1):
            base[q] = sum(w_hat[b] * c.books[b]["avg"][q] for b in T_WEIGHTS)
            assert close(c.quarters["vol_opex"][q], base[q], 1e-12), (c.label, q)
            want = opex[q - 4] * (1 + wage[q] + link * (base[q] / base[q - 4] - 1 - wage[q])) * (1 + prep.opex_real[q])
            assert close(c.quarters["opex"][q], want, 1e-12), (c.label, q, c.quarters["opex"][q], want)
            opex[q] = c.quarters["opex"][q]
            year = tl.year(q)
            if q >= 5 and year not in prep.fees_override:
                vol = (loans_end[q - 1] + loans_end[q]) / 2
                vol4 = (loans_end[q - 5] + loans_end[q - 4]) / 2
                g = wage[q] + prep.fees_gvw[q] + link_f * (vol / vol4 - 1 - wage[q])
                assert close(c.quarters["fees"][q], c.quarters["fees"][q - 4] * (1 + g), 1e-12), (c.label, q)


def check_opex_weights_refusals() -> None:
    """Книга с весами: книга не из книг ЧПД — отказ схемы; все веса нулевые — отказ; нет истории книг в фактах —
    FactsError; связь расходов нулевая — веса не читаются (история не нужна)."""
    from model.book import book_from_dict
    from model.book_schema import FactsError
    from model.grid import run_grid
    from tests.support_core_t import book_live, put, t_dict, t_facts
    data = t_dict()
    refused(lambda: book_from_dict(put(t_dict(), OPEX_W, {"nope": 1.0}), facts=t_facts()), "незнакомый ключ")
    refused(lambda: book_from_dict(put(t_dict(), OPEX_W, {"auto": 0.0}), facts=t_facts()), "все веса нулевые")
    book = book_from_dict(put(data, OPEX_W, dict(T_WEIGHTS)), facts=t_facts())
    try:
        run_grid(book, t_facts(), book_live(book))
    except FactsError as exc:
        assert "остатков книг" in str(exc), str(exc)
    else:
        raise AssertionError("нет FactsError без истории книг")
    off = book_from_dict(put(put(t_dict(), OPEX_W, dict(T_WEIGHTS)), "opex.volume_link", 0.0), facts=t_facts())
    plain = book_from_dict(put(t_dict(), "opex.volume_link", 0.0), facts=t_facts())
    a, b = run_grid(off, t_facts(), book_live(off)), run_grid(plain, t_facts(), book_live(plain))
    assert [c.v_ri for c in a.cells] == [c.v_ri for c in b.cells]


def check_opex_weights_probe_leaves_no_trace() -> None:
    """Оценка шага на копии состояния (запас квартала, оценки ограничения роста) не оставляет в клетке ряда базы
    расходов по книгам за свой квартал, а принятая оценка несёт его в рядах-базах (`STEP_FLOWS`, М§4.13.1): иначе
    рост «к тому же кварталу» через год читал бы базу чужой оценки."""
    from model.cell import STEP_FLOWS, _Cell, initial_state
    run = _t_grid("w")
    cell = _Cell(run.ctx, "N", "norm", "schedule")
    st = initial_state(run.ctx.prep)
    cell.probe(st, 1)
    assert 1 not in cell.flows["vol_opex"] and "vol_opex" in STEP_FLOWS
    row, after, kept = cell.evaluate(st, 1, (), 1.0)
    assert 1 not in cell.flows["vol_opex"] and "vol_opex" in kept
    light = cell.evaluate(st, 1, (), 1.0, light=True)
    assert light[1] is None and 1 not in cell.flows["vol_opex"]


# ------------------------------------------------------------------ терминал К-Т: постоянные в рублях части (М§7)

PARTS = ("other_assets_fixed", "capital_instruments", "other_fixed_liabilities", "real_rubles")
LAM_F = "valuation.terminal.fixed_growth_share"
FIXED_PARTS = "valuation.terminal.fixed_parts"


def _ref_block(t: dict, lam_f: float | None = None, parts: tuple = PARTS, symmetric: bool = False) -> dict:
    """Опорный счёт терминала своим кодом — формулы методики (spec.yaml keys.TERMINAL.formulas; как `example.py`):
    капитал — форма X = BV + [Н20.0] (AT1 + T2) − κ RWA, доход на избыток — смесь балансирующих (запас больше X_T)."""
    k, pi, fade = t["k_T"], t["pi"], t["fade"]
    g = (1 + pi) * (1 + t["real_growth"]) - 1
    x20 = t["BV_Q"] + t["AT1"] + t["T2_Q"] - t["kappa20"] * t["RWA_Q"]
    x11 = t["BV_Q"] - t["kappa11"] * t["RWA_Q"]
    x_t, j20 = min(x20, x11), x20 <= x11
    bv_star = t["BV_Q"] - x_t
    tau, nci, tau_s = t["tau_eff"], t["nci"], t["tau_stat"]
    y_x = t["y_bal"] * x_t if x_t > 0 else -(t["c_wh"] * min(-x_t, t["WT_Q"]) + t["y_bal"] * (-x_t - min(-x_t, t["WT_Q"])))
    ci_t1 = (t["PBT_L"] * (1 + g) - y_x) * (1 - tau) * (1 - nci) - t["CPN"] * (1 - tau_s)

    def faded(roe):
        ex = roe - k
        return k + fade * ex if symmetric else k + fade * max(ex, 0.0) + min(ex, 0.0)

    if lam_f is None:
        roe_p = faded(ci_t1 / bv_star)
        return {"TV_RI": (roe_p - k) * bv_star / (k - g), "TV_DDM": x_t + (roe_p - g) * bv_star / (k - g),
                "ROE_T": ci_t1 / bv_star, "ROE_T_faded": roe_p}
    w = 1 - lam_f
    on = set(parts)
    kappa = t["kappa20"] if j20 else t["kappa11"]
    f_a = t["OA_fixed"] if "other_assets_fixed" in on else 0.0
    r_f = t["R_F"] if "other_assets_fixed" in on else 0.0
    inst = "capital_instruments" in on
    chi = 1.0 if inst and j20 else 0.0
    own = t["NCI"] + t["DP_fix"] if "other_fixed_liabilities" in on else 0.0
    f_k = kappa * r_f - chi * (t["AT1"] + t["T2_Q"])
    d_f = f_a - f_k - (t["AT1"] if inst else 0.0) - own
    y_m = t["c_wh"] if t["WT_Q"] > 0 else t["y_bal"]
    tax = (1 - tau) * (1 - nci)
    cpn = t["CPN"] * (1 - tau_s) if inst else 0.0
    i_f = -y_m * d_f * tax - cpn
    m_l = (t["MISC_L"] + t["NC_L"]) * tax if "real_rubles" in on else 0.0
    b = bv_star - w * f_k
    ci_b = ci_t1 + w * (1 + g) * y_m * d_f * tax + w * cpn - w * (1 + g) * m_l
    pi_t = min(pi, k - 0.0001)
    x_b = (ci_b - k * b) / (k - g) + w * m_l * (1 + pi_t) / (k - pi_t)
    phi = fade if (symmetric or x_b > 0) else 1.0
    tv_ri = phi * x_b + w * (i_f - k * f_k) / k
    return {"TV_RI": tv_ri, "TV_DDM": t["BV_Q"] + tv_ri, "ROE_T": (ci_b + w * m_l * (1 + pi_t)) / b,
            "ROE_T_faded": k + phi * x_b * (k - g) / b, "F_K": f_k, "D_F": d_f, "I_F": i_f, "m_L": m_l, "B": b,
            "X_B": x_b, "phi": phi, "kappa": kappa, "j_star": "n20" if j20 else "n11", "y_m": y_m}


def _core_term(t: dict, lam_f: float | None = None, parts: tuple | None = None, symmetric: bool = False) -> Any:
    """Терминал ядра (`model.valuation.terminal`) на входах примера: норматив Н20.0 — (BV + AT1 + T2) / RWA против
    κ_20, Н20.1 — BV / RWA против κ_11; запас балансирующих активов больше избытка."""
    from model.valuation import FixedInputs, terminal
    fixed = FixedInputs(f_a=t["OA_fixed"], r_f=t["R_F"], kappa20=t["kappa20"], kappa11=t["kappa11"], at1=t["AT1"],
                        t2=t["T2_Q"], nci=t["NCI"], dp_fix=t["DP_fix"], misc_l=t["MISC_L"], nc_l=t["NC_L"])
    rwa = t["RWA_Q"]
    return terminal(n20=(t["BV_Q"] + t["AT1"] + t["T2_Q"]) / rwa, req20=t["kappa20"], n11_star=t["BV_Q"] / rwa,
                    req11=t["kappa11"], rwa=rwa, bv_q=t["BV_Q"], pbt_last_year=t["PBT_L"], y_balancing=t["y_bal"],
                    c_wholesale=t["c_wh"], headroom=1e9, tau_eff=t["tau_eff"], nci_share=t["nci"],
                    coupon_annual=t["CPN"], tau_stat=t["tau_stat"], lt_inflation=t["pi"],
                    real_growth=t["real_growth"], fade=t["fade"], multiple=1.0, k_t=t["k_T"], min_share=0.0,
                    wholesale_extra=t["WT_Q"], symmetric=symmetric, fixed=fixed if lam_f is not None else None,
                    lam_f=lam_f, parts=parts)


def _t_inputs() -> dict:
    return {k: num(v) for k, v in example()["terminal"]["inputs"].items()}


def check_terminal_example() -> None:
    """Пример терминала: прежняя ветвь и λ_F = 1 — те же числа (λ_F = 1 — прежняя строка бит в бит); λ_F = 0 и ½ —
    числа примера (1e-12); тождество TV_DDM − TV_RI = BV_Q; цены частей; линейность по λ_F; замкнутые формы при
    ROE_T < k_T; нейтральность бездоходного актива, оплаченного капиталом."""
    ex = example()["terminal"]
    t = _t_inputs()
    old, lam1 = _core_term(t), _core_term(t, 1.0)
    assert (lam1.tv_ri, lam1.tv_ddm, lam1.roe_t) == (old.tv_ri, old.tv_ddm, old.roe_t) and lam1.fixed is None
    assert close(old.tv_ri, num(ex["old"]["TV_RI"]), 1e-12) and close(old.tv_ddm, num(ex["old"]["TV_DDM"]), 1e-12)
    for key, lam in (("lam_0", 0.0), ("lam_half", 0.5)):
        got, want = _core_term(t, lam), ex[key]
        assert close(got.tv_ri, num(want["TV_RI"]), 1e-12), (key, got.tv_ri, num(want["TV_RI"]))
        assert close(got.tv_ddm - got.tv_ri, t["BV_Q"], 1e-12)
        assert close(got.roe_raw, num(want["ROE_T"]), 1e-12) and close(got.roe_t, num(want["ROE_T_faded"]), 1e-12)
        for name, field_ in (("F_K", "f_k"), ("D_F", "d_f"), ("I_F", "i_f"), ("m_L", "m_l"), ("B", "business_capital"),
                             ("X_B", "x_b"), ("phi", "phi"), ("kappa", "kappa"), ("y_m", "y_m")):
            assert close(got.fixed[field_], num(want[name]), 1e-12, 1e-12), (key, name)
        assert got.fixed["binding"] == want["j_star"]
    half, zero = _core_term(t, 0.5), _core_term(t, 0.0)
    if ex["linear_in_lambda_checked"]:
        assert close(half.tv_ri, (zero.tv_ri + old.tv_ri) / 2, 1e-12)
    for part, want in ex["price_by_part_lam_0_minus_old"].items():
        assert close(_core_term(t, 0.0, (part,)).tv_ri - old.tv_ri, num(want), 1e-12, 1e-12), part
    low = dict(t, PBT_L=150.0)
    forms = ex["closed_forms_roe_below_k"]
    cases = {"a_T2_only": dict(low, AT1=0.0, NCI=0.0, OA_fixed=0.0, R_F=0.0, MISC_L=0.0, CPN=0.0),
             "b_real_rubles_only": dict(low, AT1=0.0, T2_Q=0.0, NCI=0.0, OA_fixed=0.0, R_F=0.0, CPN=0.0),
             "c_fixed_asset_only": dict(low, AT1=0.0, T2_Q=0.0, NCI=0.0, MISC_L=0.0, CPN=0.0),
             "d_AT1_only": dict(low, T2_Q=0.0, NCI=0.0, OA_fixed=0.0, R_F=0.0, MISC_L=0.0)}
    for name, inputs in cases.items():
        delta = _core_term(inputs, 0.0).tv_ri - _core_term(inputs).tv_ri
        assert close(delta, num(forms[name]["delta"]), 1e-12, 1e-12), (name, delta)
    a = num(ex["neutral_asset"]["A"])
    neu = dict(t, OA_fixed=t["OA_fixed"] + a, R_F=t["R_F"] + a / t["kappa20"], BV_Q=t["BV_Q"] + a,
               RWA_Q=t["RWA_Q"] + a / t["kappa20"])
    n0 = _core_term(neu, 0.0)
    assert close(n0.tv_ddm, zero.tv_ddm, 1e-12) and close(zero.tv_ri - n0.tv_ri, a, 1e-12)


# наборы входов проверки против опорного счёта: связывает Н20.1; опт сверх минимума; низкая прибыль; угасание
# при любом знаке
def _variants() -> list[tuple[str, dict, bool]]:
    t = _t_inputs()
    return [("base", t, False), ("n11_binds", dict(t, kappa11=0.13, kappa20=0.12), False),
            ("wholesale", dict(t, WT_Q=30.0), False), ("low_roe", dict(t, PBT_L=150.0), False),
            ("symmetric_low", dict(t, PBT_L=150.0), True), ("dp_fix", dict(t, DP_fix=7.0), False)]


def check_terminal_against_reference() -> None:
    """Терминал ядра с блоком постоянных частей = опорный счёт формул методики своим кодом (1e-12) на наборах входов:
    связывает Н20.0 или Н20.1, опт сверх минимума (y_m — ставка опта), ROE ниже k, симметричное угасание, постоянное
    обязательство дивидендов; λ_F ∈ {0; 0,3; 1}; все части и каждая часть."""
    for name, t, sym in _variants():
        old_ref, old = _ref_block(t, symmetric=sym), _core_term(t, symmetric=sym)
        assert close(old.tv_ri, old_ref["TV_RI"], 1e-12), name
        for lam in (0.0, 0.3, 1.0):
            for parts in (PARTS,) + tuple((p,) for p in PARTS):
                got, ref = _core_term(t, lam, parts, sym), _ref_block(t, lam, parts, sym)
                assert close(got.tv_ri, ref["TV_RI"], 1e-12, 1e-12), (name, lam, parts, got.tv_ri, ref["TV_RI"])
                assert close(got.tv_ddm, ref["TV_DDM"], 1e-12, 1e-12), (name, lam, parts)
                assert close(got.roe_t, ref["ROE_T_faded"], 1e-12, 1e-12), (name, lam, parts)
                assert close(got.roe_raw, ref["ROE_T"], 1e-12, 1e-12), (name, lam, parts)
                if lam != 1.0:
                    assert got.fixed["binding"] == ref["j_star"], (name, lam)
    hard = dict(_t_inputs(), R_F=12000.0)
    refused(lambda: _core_term(hard, 0.0), "не больше нуля")


@functools.lru_cache(maxsize=None)
def _kt_grid(lam: float | None, parts: tuple | None = None) -> Any:
    keys: dict[str, Any] = {}
    if lam is not None:
        keys["valuation__terminal__fixed_growth_share"] = lam
    if parts is not None:
        keys["valuation__terminal__fixed_parts"] = list(parts)
    return S.grid_of(**keys)


def check_terminal_grid() -> None:
    """Фикстура `core_t` (постоянные прочие активы, T2, неконтролирующие доли, постоянное обязательство дивидендов):
    λ_F = 1 — сетка без ключа бит в бит; λ_F ∈ {0; ½} — в каждой клетке TV_DDM − TV_RI = BV_Q и V_DDM = V_RI, TV_RI
    линейна по λ_F в клетках одной ветви угасания; входы блока — из прохода: κ — убыль избытка норматива на рубль RWA
    (функция нормативов ядра), строки в реальных рублях — сумма «прочего» и непрофильного года L после налога и доли
    НДУ; узел клетки — только при ключе."""
    base, one = _kt_grid(None), _kt_grid(1.0)
    assert [c.v_ri for c in one.cells] == [c.v_ri for c in base.cells] and one.point == base.point
    assert all(c.terminal_fixed is None for c in one.cells + base.cells)
    zero, half = _kt_grid(0.0), _kt_grid(0.5)
    ctx = zero.ctx
    tl, prep = ctx.timeline, ctx.prep
    Q = tl.Q
    year_l = [q for q in range(1, Q + 1) if tl.year(q) == tl.year(Q)]
    linear = 0
    for c0, ch, c1 in zip(zero.cells, half.cells, base.cells):
        for c in (c0, ch):
            bv_q = c.quarters["bv"][Q]
            assert close(c.tv_ddm - c.tv_ri, bv_q, 1e-12, 1e-9), c.label
            assert close(c.v_ddm, c.v_ri, 1e-9), c.label
        blk = c0.terminal_fixed
        assert blk is not None and blk["parts"] == list(PARTS) and blk["lam_f"] == 0.0
        tax = (1 - c0.quarters["tau_eff"][Q]) * (1 - prep.nci_share)
        m_l = sum(c0.quarters["misc"][q] + c0.quarters["noncore"][q] for q in year_l) * tax
        assert close(blk["m_l"], m_l, 1e-12, 1e-12), c0.label
        _check_kappa(prep, c0)
        if (c0.terminal_fixed["x_b"] > 0) == (c1.roe_t_raw > c1.k_t) and ch.terminal_fixed["phi"] == c0.terminal_fixed["phi"]:
            assert close(ch.tv_ri, (c0.tv_ri + c1.tv_ri) / 2, 1e-9, 1e-9), ch.label
            linear += 1
    assert linear >= 10, linear
    tight = S.grid_of(valuation__terminal__fixed_growth_share=0.0, capital__n11__gap_pp=-0.04)
    assert any(c.terminal_fixed["binding"] == "n11" for c in tight.cells)
    for c in tight.cells:
        _check_kappa(tight.ctx.prep, c)


def _check_kappa(prep: Any, c: Any) -> None:
    """κ блока клетки — убыль избытка связывающего норматива (функция нормативов ядра) на рубль RWA на конце сетки."""
    from model.capital import ratios
    Q = prep.timeline.Q
    blk = c.terminal_fixed
    sc = prep.scenarios[c.scenario]
    row = dict(bv=c.quarters["bv"][Q], dpreg=c.quarters["dpreg"][Q], reserve=c.quarters["reserve"][Q],
               unaudited=c.quarters["e_unaudited"][Q], t2=prep.t2[Q], ded_pp20=sc.ded_pp20[Q], ded_pp11=sc.ded_pp11[Q])
    rwa = c.quarters["rwa"][Q]
    lo, hi = ratios(prep.cap, rwa=rwa, **row), ratios(prep.cap, rwa=rwa + 1.0, **row)
    req = sc.req20[Q] if blk["binding"] == "n20" else sc.req11[Q]
    n_lo, n_hi = (lo.n20, hi.n20) if blk["binding"] == "n20" else (lo.n11, hi.n11)
    kappa = (n_lo - req) * rwa - (n_hi - req) * (rwa + 1.0)
    assert close(blk["kappa"], kappa, 1e-6, 1e-9), (c.label, blk["binding"], blk["kappa"], kappa)


def check_terminal_parts_and_pass() -> None:
    """Ключи блока — параметры оценки: входы прохода несут λ_F «не числом» и без частей, отпечаток прохода при λ_F 0 и
    ½ один (проход не пересчитывается); части — в прогоне по книге; отказы схемы: λ_F вне [0; 1], незнакомая или
    повторная часть."""
    import math

    from model.grid import path_inputs, path_key
    zero, half = _kt_grid(0.0), _kt_grid(0.5)
    a, b = path_inputs(zero.ctx), path_inputs(half.ctx)
    assert math.isnan(a.prep.fixed_growth_share) and a.prep.fixed_parts is None
    assert path_key(a) == path_key(b) and zero.ctx.prep.fixed_growth_share == 0.0
    assert path_key(path_inputs(_kt_grid(None).ctx)) != path_key(a)       # без ключа проход не несёт входов блока
    only = _kt_grid(0.0, ("real_rubles",))
    assert all(c.terminal_fixed["parts"] == ["real_rubles"] and c.terminal_fixed["f_k"] == 0.0 for c in only.cells)
    refused(lambda: S.book_of(valuation__terminal__fixed_growth_share=1.2), "fixed_growth_share")
    refused(lambda: S.book_of(valuation__terminal__fixed_growth_share=0.0,
                              valuation__terminal__fixed_parts=["noise"]), "незнакомое значение")
    refused(lambda: S.book_of(valuation__terminal__fixed_growth_share=0.0,
                              valuation__terminal__fixed_parts=["real_rubles", "real_rubles"]), "повторяется")


# ------------------------------------------------------------------ М3: выкуп по цене мира (М§5.6)

BB = "dividends.buyback"
BB_LABEL = {"meta__labels__control__lines__buyback": "Выкуп акций"}
BB_AMOUNT = {"2026Q3": 2.0, "2026Q4": 3.0, "2027": 3.0, "2028": 3.0, "LT": 0.0, "LT_from": 2029}


def _example_path(rule: str = "world_forward", *, p_book: float | None = None, closed: dict | None = None,
                  amounts: dict | None = None, shock: tuple = (), p_start: float | None = None) -> list[dict]:
    """Квартальный путь выкупа примера m3 функциями клетки ядра (`_Cell.buyback_quarter`, `_Cell.buyback_after`) на
    клетке-заглушке: k_b, суммы, DPS решений (дивиденд квартала — DPS × N_c,q / 1000), мост d^R."""
    from types import SimpleNamespace as NS

    from model.cell import Buyback, _Cell
    inp = example()["m3"]["inputs"]
    Q = 6
    k = {int(q): num(v) for q, v in inp["k_book"].items()}
    amounts = {int(q): num(v) for q, v in inp["amounts_bn"].items()} if amounts is None else amounts
    p_b = num(inp["P_book"]) if p_book is None else p_book
    bb = Buyback(rule=rule, amount=tuple(amounts.get(q, 0.0) for q in range(Q + 1)), p_book=p_b, qb=int(inp["qb"]),
                 e_book=1 / 3, closed={1: 10.5} if closed is None else closed,
                 disc={"W": NS(k=tuple(k.get(q, 0.0) for q in range(Q + 1)))},
                 bridge_dps={int(q): num(v) for q, v in inp["bridge_dps"].items()}, skip=bool(shock))
    cell = NS(p=NS(bb=bb), tl=NS(period=lambda q: f"q{q}"), rg=NS(shock_year=2 if shock else None),
              years={q: (2 if q in shock else 1) for q in range(Q + 1)}, world="W", regime="r", scenario="s",
              p_start=p_b if p_start is None else p_start, bb_q=0.0)
    st = NS(p_plus=None, n_out=num(inp["N_out_0_mln"]))
    dps = {int(q): num(v) for q, v in inp["dps_policy"].items()}
    rows = []
    for q in range(1, Q + 1):
        p_bar, n = _Cell.buyback_quarter(cell, st, q)
        row = {"div": dps.get(q, 0.0) * n / 1000, "bb": cell.bb_q}
        _Cell.buyback_after(cell, st, row, q, p_bar, n)
        rows.append(row)
    return rows


def _example_value(rows: list[dict]) -> Any:
    """Оценка примера функцией ядра `value_cell` на дату книги (q0 = q_b = 2, e = 1/3; TV_DDM = 300)."""
    from types import SimpleNamespace as NS

    from model.valuation import value_cell
    inp = example()["m3"]["inputs"]
    kv = {int(q): num(v) for q, v in inp["k_valuation"].items()}
    dfq, d = [1.0] * 7, 1.0
    for q in range(2, 7):
        d = d / (1 + kv[q])
        dfq[q] = d
    k = tuple(kv.get(q, 0.0) for q in range(7))
    zeros = (0.0,) * 7
    return value_cell(q0=2, elapsed=1 / 3, disc=NS(dfq=tuple(dfq), k=k), bv=zeros, ci=zeros,
                      div=(0.0,) + tuple(r["div"] for r in rows), term=NS(tv_ri=0.0, tv_ddm=num(inp["TV_DDM_bn"])),
                      bb=(0.0,) + tuple(r["bb"] for r in rows), d_ext=(0.0,) + tuple(r["d_ext"] for r in rows),
                      n_t=rows[-1]["n_out"], n_out=num(inp["N_out_0_mln"])), dfq


def check_buyback_example() -> None:
    """Пример m3 функциями ядра: цена покупок (закрытый квартал — по рынку, квартал даты книги и позже — форвард с
    середины квартала), путь акций клетки, дивиденд на внешнюю акцию, форвард после дивидендов и моста; S_c, V̂_c,
    V_DDM, PV выкупа (1e-12); тождество оставшихся акций; правило market — N_T = N_0 − 1000 ΣB / P_b; без выкупа
    S = V_DDM × 1000 / N_0; год шока; покупка дешевле — S выше; неподвижная точка «стоимость клетки»."""
    m3 = example()["m3"]
    rows = _example_path()
    for got, want in zip(rows, m3["rows"]):
        for key, name in (("p_bar", "P_bar"), ("n_out", "N_out"), ("d_ext", "d_ext"), ("p_plus", "P_plus"),
                          ("div", "Div"), ("bb", "B")):
            assert close(got[key], num(want[name]), 1e-12, 1e-12), (want["q"], key, got[key], num(want[name]))
    val, dfq = _example_value(rows)
    v = m3["value"]
    assert close(val.s_price, num(v["S"]), 1e-12) and close(val.v_price, num(v["V_hat"]), 1e-12)
    assert close(val.v_ddm, num(v["V_DDM"]), 1e-12) and close(val.pv_buyback, num(v["PV_BB"]), 1e-12)
    n_t = rows[-1]["n_out"]
    sold = sum(dfq[q] * rows[q - 1]["d_ext"] * (rows[q - 1]["n_out"] - n_t) / 1000 for q in range(2, 7))
    assert close(val.s_price * n_t / 1000, val.v_ddm - val.pv_buyback - sold, 1e-12)
    mkt = _example_path("market")
    n0 = num(m3["inputs"]["N_out_0_mln"])
    total = sum(num(x) for x in m3["inputs"]["amounts_bn"].values())
    assert close(mkt[-1]["n_out"], n0 - 1000 * total / num(m3["inputs"]["P_book"]), 1e-12)
    assert all(r["p_bar"] == num(m3["inputs"]["P_book"]) for r in mkt)
    zero = _example_value(_example_path(amounts={}))[0]
    assert close(zero.s_price, zero.v_ddm * 1000 / n0, 1e-12) and close(zero.v_price, zero.v_ddm, 1e-12)
    shock = _example_path(shock=(3, 4))
    for got, want in zip(shock, m3["shock_skip_q3_q4"]["rows"]):
        assert close(got["n_out"], num(want["N_out"]), 1e-12) and close(got["bb"], num(want["B"]), 1e-12)
    cheap = _example_value(_example_path(p_book=9.0, closed={1: 10.5 * 0.9}))[0]
    assert cheap.s_price > val.s_price and close(cheap.s_price, num(m3["cheaper_price_raises_S"]["S_cheaper"]), 1e-12)
    start = 10.0
    for _ in range(60):
        s = _example_value(_example_path(p_start=start))[0].s_price
        if abs(s - start) < 1e-12:
            break
        start = s
    assert close(start, num(m3["cell_value_variant"]["P_start_fixed_point"]), 1e-9), start


@functools.lru_cache(maxsize=None)
def _bb_grid(rule: str | None = "world_forward", amount: Any = "center", **extra: Any) -> Any:
    keys: dict[str, Any] = {}
    if rule is not None:
        node = {"enabled": True, "price": rule, "amount": BB_AMOUNT if amount == "center" else amount}
        node.update({k: v for k, v in extra.items() if k in ("closed_prices", "skip_in_shock_year")})
        keys = {"dividends__buyback": node, **BB_LABEL}
    keys.update({k: v for k, v in extra.items() if "__" in k})
    return S.grid_of(**keys)


def check_buyback_without_key_and_zero() -> None:
    """Фикстура `core_t`: выключатель выключен — сетка без ключа бит в бит (рядов выкупа нет, оценка в цене — V_RI);
    сумма ≡ 0 при включённом ключе — цены и стоимости клеток те же (1e-12 отн.), S_c = V_DDM × 1000 / N_out."""
    base = S.grid_of()
    off = S.grid_of(dividends__buyback={"enabled": False})
    assert [c.v_ri for c in off.cells] == [c.v_ri for c in base.cells] and off.point == base.point
    assert all(c.v_price is c.v_ri and c.v_hat is None and "bb" not in c.quarters for c in base.cells)
    zero = _bb_grid(amount=0.0)
    assert close(zero.point, base.point, 1e-12) and close(zero.low, base.low, 1e-12)
    n0 = zero.ctx.prep.af.n_out
    for z, b in zip(zero.cells, base.cells):
        assert close(z.v_price, b.v_ri, 1e-12) and close(z.v_ddm, b.v_ddm, 1e-12), z.label
        assert close(z.s_price, z.v_ddm * 1000 / n0, 1e-12) and close(z.v_price, z.v_ddm, 1e-12), z.label


def check_buyback_grid() -> None:
    """Фикстура `core_t`, выкуп центра (2026Q3 — 2028) по форварду мира: в каждой клетке капитал — тождество с выкупом
    (выкуп — распределение, совокупный доход его не несёт), V_DDM = V_RI, тождество оставшихся акций, акции клетки не
    растут, цена покупок положительна, путь цены — форвард мира на дату книги (k_b — дисконт мира на дату книги):
    закрытый квартал — цена книги, квартал даты книги — с середины оставшейся части; решения модели — на акциях
    клетки: пул / N_iss = DPS, дивиденд = DPS × N_c,q / 1000; годовая строка выкупа — сумма кварталов года."""
    from model.checks import check_invariants
    from model.worlds import discount
    run = _bb_grid()
    ctx = run.ctx
    tl, prep = ctx.timeline, ctx.prep
    Q, qb = tl.Q, prep.bb.qb
    fired = [f.name for f in check_invariants(run) if f.fired]
    assert not fired, fired
    p_b = float(ctx.book.get("meta.market_price.T"))
    from model.timeline import make_clock, to_date
    clock_b = make_clock(ctx.book, tl, to_date(ctx.book.get("meta.valuation_date")))
    n_iss = prep.af.n_iss
    from model.paths import Trajectory
    pay = Trajectory(ctx.book.get("dividends.policy.payout"))
    disc_v = ctx.discounts
    for c in run.cells:
        q_ = c.quarters
        k_b = discount(ctx.book, c.world, clock_b).k
        p_plus = p_b
        for q in range(1, Q + 1):
            assert close(q_["ci"][q], q_["ni_sh"][q] - q_["coupon"][q] * (1 - q_["tau_stat"][q]) + q_["oci"][q]
                         + q_["om"][q], 1e-12, 1e-12), (c.label, q)
            assert close(q_["bv"][q], q_["bv"][q - 1] + q_["ci"][q] - q_["div"][q] - q_["bb"][q], 1e-12, 1e-9)
            assert q_["n_out"][q] <= q_["n_out"][q - 1]
            want_bar = p_b if q < qb else p_plus * (1 + k_b[q] / 2)
            assert close(q_["p_bar"][q], want_bar, 1e-12), (c.label, q, q_["p_bar"][q], want_bar)
            assert close(q_["n_out"][q], q_["n_out"][q - 1] - 1000 * q_["bb"][q] / want_bar, 1e-12), (c.label, q)
            d = q_["div"][q] * 1000 / q_["n_out"][q]
            assert close(q_["d_ext"][q], d, 1e-12, 1e-12)
            if q >= qb:
                p_plus = p_plus * (1 + k_b[q]) - d
            assert close(q_["p_plus"][q], p_plus, 1e-12, 1e-12), (c.label, q)
        assert close(c.v_ddm, c.v_ri, 1e-9), c.label
        dfq, q0 = disc_v[c.world].dfq, ctx.clock.q0
        n_t = q_["n_out"][Q]
        assert c.n_t == n_t
        sold = sum(dfq[q] * q_["d_ext"][q] * (q_["n_out"][q] - n_t) / 1000 for q in range(q0, Q + 1))
        assert close(c.s_price * n_t / 1000, c.v_ddm - c.pv_buyback - sold, 1e-9), c.label
        assert close(c.v_price, c.s_price * prep.af.n_out / 1000, 1e-12)
        for dec in c.decisions:
            if dec.source == "model" and not dec.cut and dec.catch == 0 and dec.excess == 0:
                n_q = q_["n_out"][dec.q]
                assert close(dec.div, dec.dps * n_q / 1000, 1e-12), (c.label, dec.period)
                assert close(dec.dps, pay.year_value(dec.year) * max(dec.base, 0.0) * 1000 / n_iss, 1e-9), (
                    c.label, dec.period)
        years = c.years
        for i, y in enumerate(years):
            qs = [q for q in tl.quarters_of_year(y) if 1 <= q <= Q]
            if qs:
                assert close(c.annual["buyback"][i], sum(q_["bb"][q] for q in qs), 1e-12)


def check_buyback_book_tables() -> None:
    """Таблицы книги (results.json) при выкупе: стоимость и P/B клетки — оценка в цене V̂ (одна форма с выпуском и
    гейтом P/B мира), рядом V_RI; слой несёт строку выкупа, и v0 = bv_v + pv_ri + pv_terminal + buyback_effect. Без
    ключа — прежние поля (P/B — V_RI / BV_v, строк выкупа нет)."""
    from model.book_results import _layer, result_cells
    run = _bb_grid()
    for row, c in zip(result_cells(run), run.cells):
        assert row["v"] == c.v_price and row["pb"] == c.v_price / c.bv_v and row["v_ri"] == c.v_ri, c.label
        assert c.v_price != c.v_ri, c.label
    for L in run.layers.values():
        node = _layer(L, True)
        assert close(node["v0"], node["bv_v"] + node["pv_ri_explicit"] + node["pv_terminal"] + node["buyback_effect"],
                     1e-12, 1e-9)
    base = S.grid_of()
    for row, c in zip(result_cells(base), base.cells):
        assert row["pb"] == c.v_ri / c.bv_v and "v_ri" not in row and "s_price" not in row, c.label
    assert all("buyback_effect" not in _layer(L) for L in base.layers.values())


def check_buyback_rules() -> None:
    """Правила цены: market — цена книги во всех кварталах и клетках, N_T = N_0 − 1000 ΣB / P_b (1e-12); покупка
    дешевле (цена книги ниже) — S_c выше в каждой клетке; cell_value — сходится: начало форварда — стоимость клетки на
    оставшуюся акцию на дату книги (дата книги = дата оценки фикстуры) до 1e-9; год шока при skip_in_shock_year — в
    клетках режима шока выкупа года шока нет, у прочих режимов есть."""
    mkt = _bb_grid("market")
    tl = mkt.ctx.timeline
    p_b = float(mkt.ctx.book.get("meta.market_price.T"))
    total = sum(mkt.ctx.prep.bb.amount[1:])
    for c in mkt.cells:
        assert all(c.quarters["p_bar"][q] == p_b for q in range(1, tl.Q + 1))
        assert close(c.n_t, mkt.ctx.prep.af.n_out - 1000 * total / p_b, 1e-12), c.label
    cheap = _bb_grid("market", **{"meta__market_price__T": p_b * 0.9})
    assert all(a.s_price > b.s_price for a, b in zip(cheap.cells, mkt.cells))
    cv = _bb_grid("cell_value")
    qb = cv.ctx.prep.bb.qb
    for c in cv.cells:
        k_b = cv.ctx.prep.bb.disc[c.world].k
        p_s = c.quarters["p_bar"][qb] / (1 + k_b[qb] / 2)
        assert close(p_s, c.s_price, 1e-8), (c.label, p_s, c.s_price)
    shock = _bb_grid(skip_in_shock_year=True)
    shock_year = {r: rp.shock_year for r, rp in shock.ctx.prep.regimes.items()}
    seen = False
    for c in shock.cells:
        y = shock_year[c.regime]
        for q in range(1, tl.Q + 1):
            want = 0.0 if y is not None and tl.year(q) == y else shock.ctx.prep.bb.amount[q]
            assert c.quarters["bb"][q] == want, (c.label, q)
            seen = seen or (y is not None and tl.year(q) == y and shock.ctx.prep.bb.amount[q] > 0)
    assert seen, "у фикстуры нет выкупа в год шока — проверка пуста"


def check_buyback_pass_key_and_live_price() -> None:
    """Входы прохода: при ключе смена ERP меняет отпечаток прохода (k_b — плата за капитал мира на дату книги), без
    ключа — нет; живая цена в проход не входит — стоимости клеток при другой живой цене те же."""
    from model.grid import LiveInputs, path_inputs, path_key, run_grid
    from tests.support_core_t import book_live
    erp = float(S.book_of().get("valuation.erp"))
    plain = S.grid_of()
    plain2 = S.grid_of(valuation__erp=erp + 0.01)
    assert path_key(path_inputs(plain.ctx)) == path_key(path_inputs(plain2.ctx))
    keyed = _bb_grid()
    keyed2 = _bb_grid(**{"valuation__erp": erp + 0.01})
    assert path_key(path_inputs(keyed.ctx)) != path_key(path_inputs(keyed2.ctx))
    book = keyed.ctx.book
    live = book_live(book)
    other = LiveInputs(valuation_date=live.valuation_date, prices={t: p * 1.3 for t, p in live.prices.items()},
                       price_dates=live.price_dates, register=live.register)
    moved = run_grid(book, keyed.ctx.facts, other)
    assert [c.v_price for c in moved.cells] == [c.v_price for c in keyed.cells]


def check_buyback_refusals() -> None:
    """Отказы: годовой календарь, сумма меньше нуля, закрытый квартал вне закрытых кварталов, нет суммы или правила,
    нет подписи строки сверки, незнакомое правило; акций не осталось — отказ с меткой клетки."""
    from model.book import book_from_dict
    from model.grid import run_grid
    from tests.support_core import book_with
    on = {"enabled": True, "price": "world_forward", "amount": 1.0}
    refused(lambda: book_from_dict(book_with({BB: on, "meta.labels.control.lines.buyback": "Выкуп"}),
                                   facts=fixture_facts()), "frequency = 'quarterly'")
    refused(lambda: S.book_of(dividends__buyback={"enabled": True, "price": "world_forward"}, **BB_LABEL),
            "dividends.buyback.amount: нет ключа")
    refused(lambda: S.book_of(dividends__buyback=on), "lines.buyback")
    refused(lambda: S.book_of(dividends__buyback={**on, "price": "bid"}, **BB_LABEL), "незнакомое значение")
    for node, words in (({**on, "amount": {"2027": -1.0, "LT": 0.0}}, "меньше нуля"),
                        ({**on, "closed_prices": {"2026Q4": 300.0}}, "вне закрытых"),
                        ({**on, "amount": 1e6}, "не осталось")):
        book = S.book_of(dividends__buyback=node, **BB_LABEL)
        refused(lambda: run_grid(book, _t_facts()), words)


def _t_facts() -> Any:
    from tests.support_core_t import t_facts
    return t_facts()


# ------------------------------------------------------------------ выпуск с ключами прохода (П§2)


@functools.lru_cache(maxsize=None)
def pass_release() -> tuple[Any, dict]:
    """Быстрый выпуск фикстуры `core_t` со всеми ключами прохода: шаг хранения прогонов 0,01 ₽, блок постоянных частей
    терминала (λ_F = 0), множители CoR по книгам, выкуп по цене мира."""
    from model import payload as P
    from model.checks import check_gates
    from model.grid import run_grid
    from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
    from tests.support_core_t import t_facts
    book = S.book_of(valuation__uncertainty__draw_step=0.01, valuation__terminal__fixed_growth_share=0.0,
                     credit__book_relative={"enabled": True, "by_book": {
                         "cards": 2.2, "cash_loans": 3.5, "auto": 1.1, "mortgage": 0.4, "sme_loans": 1.0,
                         "corp_loans": 0.5}},
                     dividends__buyback={"enabled": True, "price": "world_forward", "amount": BB_AMOUNT},
                     # норматив смеси против ожидания нормативов клеток (П§7 п. 10): разрыв у полной книги фикстуры и
                     # без ключей прохода — до 0,15 п.п. (2033), с ключами — до 0,16; допуск по умолчанию — 0,05
                     checks__mix_ratio_tolerance=0.002, **BB_LABEL)
    facts = t_facts()
    expl = explained(check_gates(run_grid(book, facts), today=TODAY), today=TODAY)
    rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl, notes=[],
                         draws=4, control_model=CONTROL_FIXTURE)
    return rel, P.build_payload(rel)


def check_release_with_pass_keys() -> None:
    """Выпуск с ключами прохода: контракт выполнен; заголовок несёт шаг хранения прогонов, и прогоны ему кратны;
    клетки — узел постоянных частей терминала и годовую строку выкупа; стоимость клетки в выпуске — оценка в цене;
    мост норматива сходится (start + Σ pp = end), строка «OCI и прочее» несёт выкуп смеси заголовка."""
    from model import payload as P
    from tests.support_core2 import contract
    rel, d = pass_release()
    problems = contract(d)
    assert problems == [], problems[:5]
    h = d["fair_value"]["headline"]
    assert h["draw_step"] == 0.01 and all(U.round_half_up(v, 0.01) == v for v in h["low_draws"] + h["high_draws"])
    cells = {(c["world"], c["regime"], c["scenario"]): c for c in d["grid"]["cells"]}
    for c in rel.run.cells:
        node = cells[c.key]
        assert node["terminal_fixed"]["lam_f"] == 0.0 and node["terminal_fixed"]["binding"] in ("n20", "n11")
        assert node["v"] == P.R_MONEY(c.v_price) and c.v_hat is not None
        assert node["annual"]["buyback"] == [P.rnd(v, P.PRECISION["money_cells"]) for v in c.annual["buyback"]]
    bridge = d["capital"]["bridge"]
    assert close(bridge["start"] + sum(r["pp"] for r in bridge["rows"]), bridge["end"], 1e-9, 1e-9)
    x = P._Ctx(rel)
    qe = int(rel.run.ctx.timeline.index(bridge["to"]))
    mix = sum(x.p_mix[c.key] * sum(float(c.quarters[k][q] or 0.0) * s for q in range(1, qe + 1)
                                   for k, s in (("oci", 1), ("om", 1), ("bb", -1))) for c in rel.run.cells)
    row = next(r for r in bridge["rows"] if r["key"] == "oci_other")
    assert row["amount"] == P.R_MONEY(mix) and mix < 0, (row, mix)


def check_buyback_bridge_dividend() -> None:
    """Мост форварда d^R (М§5.6): запись реестра закрытого квартала прибыли (дивиденд вычтен из BV в якоре) с экс-датой
    позже даты книги снижает форвард цены в квартале экс-даты ровно на свой DPS; до него путь тот же."""
    from datetime import date

    from model.grid import DividendRecord, LiveInputs, run_grid
    from tests.support_core_t import book_live
    base = _bb_grid()
    book = base.ctx.book
    tl = base.ctx.timeline
    p_last = base.ctx.prep.calendar.p_last
    ex = date(2026, 10, 15)
    rec = DividendRecord(year=tl.year(p_last), dps=2.5, status="declared", record_date=ex, last_buy_date=None,
                         ex_date=ex, pay_date=None, sources=(), period=tl.period(p_last))
    live = book_live(book)
    run = run_grid(book, base.ctx.facts, LiveInputs(valuation_date=live.valuation_date, prices=live.prices,
                                                    price_dates=live.price_dates, register=(rec,)))
    q_ex = tl.q_of_date(ex)
    assert run.ctx.prep.bb.bridge_dps == {q_ex: 2.5}
    for a, b in zip(run.cells, base.cells):
        for q in range(1, q_ex):
            assert a.quarters["p_plus"][q] == b.quarters["p_plus"][q], (a.label, q)
        assert close(a.quarters["p_plus"][q_ex], b.quarters["p_plus"][q_ex] - 2.5, 1e-12), a.label
