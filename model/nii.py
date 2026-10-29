"""Книги ЧПД: ставки с лагом, доля текущих счетов, передача ставки (М§4.3–§4.5).

Ставка актива: y_q = y_(q−1) + ρ (ref_W,q + s̃_q − y_(q−1)), s̃ = s(q) − φ_A·[b ∈ Φ_A]·(ref_W − ref_H);
пассива: c_q = c_(q−1) + ρ (β ref_W,q + s(q) + φ_L·[b ∈ Φ_L]·X_W,q − c_(q−1)), X_W,q — разность
опорных ставок кредитных книг Φ_A мира W и мира H, взвешенная их долями ω_b на якоре.
Проценты — простые по дням (act/365). Передача ставки — явный ключ книги: из ЧПМ сквозь
цикл (A-N2, упр. базис → движок мостом) и реализованной передачи M − N (A-N3) замкнуто
выводятся сдвиг спредов σ0 и сжатие φ. Доля сжатия книги между мирами `nii.books.<b>.phi_share` (Р11-1, проход
ядра 9) вычитается из ставки любой книги слагаемым share_b (ref_W − ref_H) — в шаге, цели ставки, стационаре
(пара ФЛ — каждая книга своей долей), LT-спреде и кредитной марже; решатель замыкает T* через φ при любых долях,
наклон книги между мирами — `book_slopes`. Сдвиг Δ0 делит `nii.sigma0_split`: доля —
на доходности активов с `lt_shift` (σ0_A), остаток — на стоимость пассивов с `lt_shift`
(σ0_L, со знаком минус: оба слагаемых двигают ЧПМ в одну сторону). Сжатие φ делит
`nii.phi_split`: доля — в спредах активов с `phi` (φ_A), остаток — добавкой к стоимости
пассивов с `phi` (φ_L); объём сжатия мира φ × C_W от доли не зависит, поэтому Nss, T_real,
T(W) и парные передачи считаются по φ целиком. В пути сдвиг прибавляется к спредам во
всех кварталах с года `nii.sigma0_from` (М§4.4), в стационаре — к LT. Эффективный
LT-спред кредитной книги к опоре мира s_eff,b,W — вход гейта `lt_spread_floor`; кредитная
маржа стационара мира m_W — диагностика знака объёмных эффектов. Парные передачи
соседних по key^LT миров — диагностика и гейт (М§4.5).

Чей уровень задаёт ключ цели ЧПМ `nii.nim_lt_target_mgmt`, называет ключ книги
`nii.transmission.level_world`: стационарная маржа названного мира на составе баланса якоря равна
ключу, а уровень мира-опоры решатель находит сам — той же функцией, что выводит ключ под стационар
мира (`level_for_stationary`). Без ключа ключ цели — уровень мира-опоры (поведение образца).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping

from model.book import LIQUIDITY, SECURITIES, anchor_facts, book_roles
from model.book_schema import BookError
from model.credit import Bridge, cor_to_engine, kappa_gap, kappa_world
from model.paths import Trajectory, get_path
from model.timeline import Timeline, parse_period
from model.worlds import BASE_WORLD, MARKET_WORLD, check_family_worlds

if TYPE_CHECKING:
    from model.book import Book, Facts

# Режим, в котором откалиброваны уровни сквозь цикл: передача по клеткам, флаг ni_jump, кредитная маржа (М§4.5).
REFERENCE_REGIME = "norm"
# Мир, стационарную маржу которого задаёт ключ цели ЧПМ (М§4.5); нет ключа — мир-опора решателя.
LEVEL_WORLD = "nii.transmission.level_world"


def current_share_target(key: float, c_ref: float, psi: float, key_ref: float,
                         bounds: tuple[float, float]) -> float:
    """c*(ключевая) = clip(c_ref − ψ (key − key_ref), bounds) (М§4.3)."""
    lo, hi = bounds
    return min(hi, max(lo, c_ref - psi * (key - key_ref)))


def spread_paths(book: "Book", timeline: Timeline, sigma0: float, sigma0_liab: float = 0.0
                 ) -> dict[str, tuple[float, ...]]:
    """s_b(q) = path_value(spread, q) + σ_b × [lt_shift_b] × [Y(q) ≥ nii.sigma0_from], q = 0…Q (М§4.4);
    σ_b = +σ0_A у активов, −σ0_L у пассивов."""
    from_year = int(book.get("nii.sigma0_from"))
    out = {}
    for name, spec in book.get("nii.books").items():
        t = Trajectory(spec["spread"])
        sigma = sigma0 if spec["side"] == "asset" else -sigma0_liab
        shift = sigma if spec.get("lt_shift") else 0.0
        row = []
        for q in range(timeline.Q + 1):
            y, h = parse_period(timeline.period(q))
            row.append(t.value(y, h) + (shift if y >= from_year else 0.0))
        out[name] = tuple(row)
    return out


def pair_key(w1: str, w2: str) -> str:
    """Ключ парной передачи `<W1>_<W2>` (derived.nii.T_pairs, М прил. A)."""
    return f"{w1}_{w2}"


@dataclass(frozen=True)
class Transmission:
    sigma0: float                          # σ0_A — сдвиг спредов активов с lt_shift
    phi: float                             # φ — сжатие целиком (от nii.phi_split не зависит)
    target_eng: float                      # ключ цели ЧПМ в базисе движка — стационарная ЧПМ мира `level_world`
    t_real: float                          # реализованная M − N (= T*, инвариант)
    t_local: Mapping[str, float]           # локальная T(W) — диагностика
    roe_equiv: float
    t_target: float = 0.0                  # T* книги (nii.transmission.target)
    nss: Mapping[str, float] = field(default_factory=dict)   # Nss(W, 0) при решённых σ0, φ
    d: float = 0.0                         # знаменатель D замкнутого решения
    reference_world: str = ""
    pairs: Mapping[str, float | None] = field(default_factory=dict)   # "<W1>_<W2>" → T_pair соседних миров
    pairs_roe: Mapping[str, float | None] = field(default_factory=dict)   # то же в п.п. ROE на 1 п.п. ключевой
    key_lt: Mapping[str, float] = field(default_factory=dict)          # key_W^LT (ключевая мира в last_period)
    order: tuple[str, ...] = ()                                         # миры по возрастанию key^LT
    roe_factor: float = 0.0                                              # IEA_0/BV_0 × (1 − τ_eff,L)
    sigma0_liab: float = 0.0               # σ0_L — сдвиг спредов пассивов с lt_shift (0 при split = 1)
    split: float = 1.0                     # nii.sigma0_split: доля сдвига Δ0 на активах
    delta0: float = 0.0                    # Δ0 — нужный сдвиг стационарной ЧПМ мира H
    lt_spread: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    # кредитная книга → мир → эффективный LT-спред к опоре s_eff,b,W (М§4.5)
    phi_assets: float = 0.0                # φ_A = phi_split × φ — сжатие спредов кредитных книг с phi
    phi_liab: float = 0.0                  # φ_L — добавка к стоимости пассивов с phi на единицу X_W,q (0 при phi_split = 1)
    phi_split: float = 1.0                 # nii.phi_split: доля сжатия на активах
    phi_weights: Mapping[str, float] = field(default_factory=dict)   # ω_b — доли книг Φ_A в разности X_W,q (М§4.4)
    loan_margin: Mapping[str, float] = field(default_factory=dict)   # мир → кредитная маржа стационара m_W (М§4.5)
    x_lt: Mapping[str, float] = field(default_factory=dict)          # мир → X_W в стационаре (last_period)
    level_world: str = ""                  # мир, уровень которого задаёт ключ цели ЧПМ (`target_eng` — его стационар)
    reference_level: float = 0.0           # стационарная ЧПМ мира-опоры, движок: без ключа уровня — сам `target_eng`
    # проход ядра 9 (Р11-1): книга → мир → −phi_share_b × (ref_b,W^LT − ref_b,H^LT) — сдвиг ставки книги в стационаре мира
    # от доли сжатия книги (печать; у кредитных книг он уже в `lt_spread`); пусто — долей нет
    share_lt: Mapping[str, Mapping[str, float]] = field(default_factory=dict)


PHI_SHARE = "phi_share"                    # nii.books.<книга>.phi_share (Р11-1, проход ядра 9, М§4.4)


def phi_shares(books: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    """Доли сжатия книг между мирами `nii.books.<b>.phi_share` (Р11-1, проход ядра 9, М§4.4) — одна функция у решателя
    передачи, подготовки клетки, наклонов книг и печати: только книги с долей ≠ 0 (нет поля и 0 — одна ветвь, прежняя
    строка бит в бит). Ставка актива ref_W + s − φ_A [Φ_A] (ref_W − ref_H) − share_b (ref_W − ref_H), пассива β ref_W + s +
    φ_L [Φ_L] X_W − share_b (ref_W − ref_H) — в шаге, цели ставки (К4), стационаре решателя (пара ФЛ — каждая книга своей
    долей), LT-спреде гейта пола и кредитной марже стационара. В мире-опоре H слагаемое — ноль."""
    out: dict[str, float] = {}
    for b, spec in books.items():
        v = spec.get(PHI_SHARE)
        if v is not None and float(v) != 0.0:
            out[str(b)] = float(v)
    return out


class _Stationary:
    """Стационарный ЧПМ Nss(W, δ) на структуре якоря (М§4.5)."""

    def __init__(self, book: "Book", facts: "Facts"):
        books = book.get("nii.books")
        self.books = books
        self.roles = book_roles(books)
        af = anchor_facts(facts, books)
        iea = sum(af.balances[b] for b in self.roles.assets)
        self.iea0 = iea
        self.bv0 = af.bv
        self.w = {b: af.balances[b] / iea for b in self.roles.names}
        self.l_r = sum(self.w[b] for b in self.roles.retail)
        last = str(book.get("meta.last_period"))
        self.last = parse_period(last)
        self.ref_lt: dict[str, dict[str, float]] = {}
        for world in book.get("worlds.ids"):
            rates = {}
            for ref in ("key", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y"):
                path = f"worlds.{world}.key_rate" if ref == "key" else f"worlds.{world}.{ref}"
                rates[ref] = Trajectory(book.get(path)).value(*self.last)
            self.ref_lt[world] = rates
        self.s_lt = {b: Trajectory(books[b]["spread"]).value(*self.last) for b in self.roles.names}
        rcs = book.get("nii.retail_current_share")
        self.c_ref, self.psi = float(rcs["c_ref"]), float(rcs["psi"])
        self.key_ref, self.bounds = float(rcs["key_ref"]), tuple(rcs["bounds"])
        self.dia = float(book.get("nii.dia_rate"))
        self.share = phi_shares(books)          # Р11-1: книга → доля сжатия между мирами (только ≠ 0)

    def _shared(self, b: str, value: float, ref: float, ref_world: str) -> float:
        """Р11-1: ставка (стоимость) книги b за вычетом доли сжатия между мирами share_b (ref − ref_b,H^LT); без доли — как
        есть (прежняя строка)."""
        if b in self.share:
            value -= self.share[b] * (ref - self.ref_lt[ref_world][self.books[b]["ref"]])
        return value

    def nss(self, world: str, delta: float, sigma0: float, phi: float, ref_world: str,
            sigma0_liab: float = 0.0) -> float:
        books, w = self.books, self.w
        sl = {b: (sigma0_liab if books[b].get("lt_shift") else 0.0) for b in self.roles.liabilities}
        rw, rh = self.ref_lt[world], self.ref_lt[ref_world]
        total = 0.0
        for b in self.roles.assets:
            spec = books[b]
            ref = rw[spec["ref"]] + delta
            y = ref + self.s_lt[b] + (sigma0 if spec.get("lt_shift") else 0.0)
            if spec.get("phi"):
                y -= phi * (ref - rh[spec["ref"]])
            total += w[b] * self._shared(b, y, ref, ref_world)
        for b in self.roles.liabilities:
            if b in self.roles.retail:
                continue
            spec = books[b]
            ref = rw[spec["ref"]] + delta
            total -= w[b] * self._shared(b, float(spec["beta"]) * ref + self.s_lt[b] - sl[b], ref, ref_world)
        key = rw["key"] + delta
        c = current_share_target(key, self.c_ref, self.psi, self.key_ref, self.bounds)
        rc, rt = self.roles.retail
        ref_rc, ref_rt = rw[books[rc]["ref"]] + delta, rw[books[rt]["ref"]] + delta
        cost_rc = self._shared(rc, float(books[rc]["beta"]) * ref_rc + self.s_lt[rc] - sl[rc], ref_rc, ref_world)
        cost_rt = self._shared(rt, float(books[rt]["beta"]) * ref_rt + self.s_lt[rt] - sl[rt], ref_rt, ref_world)
        total -= self.l_r * (c * cost_rc + (1 - c) * cost_rt)
        total -= self.dia * self.l_r
        return total

    def liability_weight(self, world: str) -> float:
        """Σ l_b,W пассивов с lt_shift в стационаре мира: у средств ФЛ — l_R × c*(key^LT) и l_R × (1 − c*)."""
        key = self.ref_lt[world]["key"]
        c = current_share_target(key, self.c_ref, self.psi, self.key_ref, self.bounds)
        rc, rt = self.roles.retail
        total = 0.0
        for b in self.roles.liabilities:
            if not self.books[b].get("lt_shift"):
                continue
            total += self.l_r * c if b == rc else self.l_r * (1 - c) if b == rt else self.w[b]
        return total

    def phi_assets(self) -> tuple[str, ...]:
        """Φ_A — активы с `phi` (кредитные книги, кроме льготной ипотеки)."""
        return tuple(b for b in self.roles.assets if self.books[b].get("phi"))

    def phi_liabilities(self) -> tuple[str, ...]:
        """Φ_L — пассивы с `phi` (средства клиентов)."""
        return tuple(b for b in self.roles.liabilities if self.books[b].get("phi"))

    def compression(self, world: str, delta: float, ref_world: str) -> float:
        """C_W(δ) = Σ_{b ∈ Φ_A} a_b × (ref_b,W + δ − ref_b,H) — объём сжатия мира на единицу φ, в долях IEA."""
        rw, rh = self.ref_lt[world], self.ref_lt[ref_world]
        return sum(self.w[b] * (rw[self.books[b]["ref"]] + delta - rh[self.books[b]["ref"]])
                   for b in self.phi_assets())

    def phi_asset_weight(self) -> float:
        """A = Σ_{b ∈ Φ_A} a_b."""
        return sum(self.w[b] for b in self.phi_assets())

    def phi_liability_weight(self) -> float:
        """L = Σ_{b ∈ Φ_L} l_b: у книг средств ФЛ флаг одинаков, поэтому их вес — l_R и от мира не зависит."""
        rc, rt = self.roles.retail
        if bool(self.books[rc].get("phi")) != bool(self.books[rt].get("phi")):
            raise BookError(f"nii.books.{rc}.phi ≠ nii.books.{rt}.phi: у обеих книг средств ФЛ флаг одинаков (М§4.5)")
        return sum(self.w[b] for b in self.phi_liabilities())

    def lt_spreads(self, sigma0: float, phi_assets: float, ref_world: str) -> dict[str, dict[str, float]]:
        """s_eff,b,W = s_b^LT + σ0_A·[lt_shift_b] − φ_A·[b ∈ Φ_A]·(ref_b,W^LT − ref_b,H^LT) − share_b (ref_b,W^LT −
        ref_b,H^LT) кредитных книг (М§4.5; доля сжатия книги — Р11-1)."""
        out: dict[str, dict[str, float]] = {}
        for b in self.roles.loans:
            spec = self.books[b]
            row = {}
            for world, rates in self.ref_lt.items():
                s = self.s_lt[b] + (sigma0 if spec.get("lt_shift") else 0.0)
                if spec.get("phi"):
                    s -= phi_assets * (rates[spec["ref"]] - self.ref_lt[ref_world][spec["ref"]])
                row[world] = self._shared(b, s, rates[spec["ref"]], ref_world)
            out[b] = row
        return out

    def asset_rate(self, b: str, world: str, sigma0: float, phi_assets: float, ref_world: str) -> float:
        """Ставка актива в стационаре мира: ref^LT + s^LT + σ0_A·[lt_shift] − φ_A·[phi]·(ref_W^LT − ref_H^LT) −
        share_b (ref_W^LT − ref_H^LT)."""
        spec = self.books[b]
        ref = self.ref_lt[world][spec["ref"]]
        y = ref + self.s_lt[b] + (sigma0 if spec.get("lt_shift") else 0.0)
        if spec.get("phi"):
            y -= phi_assets * (ref - self.ref_lt[ref_world][spec["ref"]])
        return self._shared(b, y, ref, ref_world)

    def book_rate(self, b: str, world: str, tr: "Transmission") -> float:
        """Ставка (стоимость) книги b в стационаре мира при решённой передаче `tr` — та же форма, что цель ставки клетки
        (К4) в последнем квартале: актив — `asset_rate`; пассив β ref^LT + s^LT − σ0_L [lt_shift] + φ_L [phi] X_W^LT −
        share_b (ref_W^LT − ref_H^LT) (М§4.4; Р11-1)."""
        spec, ref_world = self.books[b], tr.reference_world
        if spec["side"] == "asset":
            return self.asset_rate(b, world, tr.sigma0, tr.phi_assets, ref_world)
        ref = self.ref_lt[world][spec["ref"]]
        c = float(spec["beta"]) * ref + self.s_lt[b] - (tr.sigma0_liab if spec.get("lt_shift") else 0.0)
        if tr.phi_liab and spec.get("phi"):
            c += tr.phi_liab * tr.x_lt[world]
        return self._shared(b, c, ref, ref_world)

    def share_lt(self, ref_world: str) -> dict[str, dict[str, float]]:
        """Р11-1: книга → мир → −share_b (ref_b,W^LT − ref_b,H^LT) — сдвиг ставки книги в стационаре мира (печать)."""
        return {b: {w: -v * (r[self.books[b]["ref"]] - self.ref_lt[ref_world][self.books[b]["ref"]])
                    for w, r in self.ref_lt.items()} for b, v in self.share.items()}


def level_world(book: "Book") -> str | None:
    """Мир, стационарную маржу которого на составе баланса якоря задаёт ключ цели ЧПМ, — ключ книги
    `nii.transmission.level_world`; нет ключа — None: ключ цели — уровень мира-опоры решателя (образец)."""
    world = book.opt(LEVEL_WORLD)
    return None if world is None else str(world)


def level_for_stationary(stationary: Callable[[float], float], start: float, step: float, target: float,
                         what: str) -> float:
    """Уровень, при котором стационарная маржа мира равна `target`; `stationary` — стационарная маржа как функция
    уровня. Она линейна по уровню (сдвиги σ0 и сжатие φ линейны по нему и входят в неё слагаемыми), поэтому
    корень берётся по двум её значениям — в `start` и в `start + step`. Одна функция у вывода ключа цели под
    стационар мира (`nim_key_for_stationary`) и у решателя передачи с ключом `nii.transmission.level_world`."""
    at_start, at_step = stationary(start), stationary(start + step)
    slope = (at_step - at_start) / step
    if slope == 0:
        raise BookError(f"{what} от ключа цели ЧПМ не зависит — ключ не определён")
    return start + (float(target) - at_start) / slope


def solve_transmission(book: "Book", facts: "Facts", bridge: Bridge) -> Transmission:
    """σ0_A, σ0_L и φ замкнуто по A-N2, `nii.sigma0_split` и A-N3 (реализованная передача M − N);
    BookError, если передача не определена. Ключ цели ЧПМ — стационарная маржа мира `nii.transmission.level_world`
    на составе баланса якоря (без ключа — мира-опоры): уровень мира-опоры под неё решатель находит сам."""
    check_family_worlds(book)
    st = _Stationary(book, facts)
    ref_world = str(book.get("nii.transmission.reference_world"))
    target_eng = bridge.to_engine_nim(float(book.get("nii.nim_lt_target_mgmt")))
    t_star = float(book.get("nii.transmission.target"))
    split = float(book.get("nii.sigma0_split"))
    if not 0.0 <= split <= 1.0:
        raise BookError(f"nii.sigma0_split = {split}: доля от 0 до 1 (М§4.5)")
    lt_weight = sum(st.w[b] for b in st.roles.assets if st.books[b].get("lt_shift"))
    liab_weight = st.liability_weight(ref_world)
    if split > 0 and lt_weight == 0:
        raise BookError("nii.sigma0_split > 0, а активов с lt_shift нет — σ0 активов не определён (М§4.5)")
    if split < 1 and liab_weight == 0:
        raise BookError("nii.sigma0_split < 1, а пассивов с lt_shift нет — σ0 пассивов не определён (М§4.5)")
    m, n = MARKET_WORLD, BASE_WORLD
    dkey = st.ref_lt[m]["key"] - st.ref_lt[n]["key"]
    if dkey == 0:
        raise BookError("ключевая миров M и N в last_period совпадает — передача не определена (М§4.5)")
    d = sum(st.w[b] * (st.ref_lt[m][st.books[b]["ref"]] - st.ref_lt[n][st.books[b]["ref"]])
            for b in st.roles.assets if st.books[b].get("phi")) / dkey
    if d == 0:
        raise BookError("D = 0: у книг с phi опоры миров M и N совпадают — φ не определено (М§4.5)")
    h = float(book.get("nii.transmission.fd_step"))

    def shifts(at: float) -> tuple[float, float, float, float]:
        """(Δ0, σ0_A, σ0_L, φ) при стационарной ЧПМ мира-опоры `at` (базис движка)."""
        delta = at - st.nss(ref_world, 0.0, 0.0, 0.0, ref_world)
        s_a = split * delta / lt_weight if split > 0 else 0.0
        s_l = (1 - split) * delta / liab_weight if split < 1 else 0.0
        flat = (st.nss(m, 0.0, s_a, 0.0, ref_world, s_l) - st.nss(n, 0.0, s_a, 0.0, ref_world, s_l)) / dkey
        return delta, s_a, s_l, (flat - t_star) / d

    # Уровень мира-опоры: сам ключ цели, а при ключе `level_world` — тот, при котором стационарная маржа
    # названного мира равна ключу цели (тот же линейный вывод, что у `nim_key_for_stationary`).
    level = level_world(book)
    if level is not None and level not in st.ref_lt:
        raise BookError(f"{LEVEL_WORLD} = {level!r}: нет среди worlds.ids (М§4.5)")
    reference_level = target_eng
    if level is not None and level != ref_world:
        def stationary(at: float) -> float:
            _, s_a, s_l, ph = shifts(at)
            return st.nss(level, 0.0, s_a, ph, ref_world, s_l)

        reference_level = level_for_stationary(stationary, target_eng, h, target_eng,
                                               f"стационарная маржа мира {level}")
    delta0, sigma0, sigma0_l, phi = shifts(reference_level)
    nss_of = lambda w, dlt, ph: st.nss(w, dlt, sigma0, ph, ref_world, sigma0_l)  # noqa: E731
    t_real = (nss_of(m, 0.0, phi) - nss_of(n, 0.0, phi)) / dkey
    p_split = float(book.get("nii.phi_split"))
    if not 0.0 <= p_split <= 1.0:
        raise BookError(f"nii.phi_split = {p_split}: доля от 0 до 1 (М§4.5)")
    a_phi, l_phi = st.phi_asset_weight(), st.phi_liability_weight()
    if p_split < 1 and l_phi == 0:
        raise BookError("nii.phi_split < 1, а пассивов с phi нет — добавка к стоимости пассивов не определена (М§4.5)")
    phi_a = p_split * phi
    phi_l = (1 - p_split) * phi * a_phi / l_phi if p_split < 1 else 0.0
    omega = {b: st.w[b] / a_phi for b in st.phi_assets()}
    t_local = {w: (nss_of(w, h, phi) - nss_of(w, -h, phi)) / (2 * h) for w in book.get("worlds.ids")}
    last_year = st.last[0]
    tau_eff = (Trajectory(book.get("tax.statutory")).year_value(last_year)
               + float(book.get("tax.effective_gap")))
    factor = st.iea0 / st.bv0 * (1 - tau_eff)
    roe_equiv = t_star * factor
    ids = tuple(book.get("worlds.ids"))
    nss = {w: nss_of(w, 0.0, phi) for w in ids}
    key_lt = {w: st.ref_lt[w]["key"] for w in ids}
    order = tuple(sorted(ids, key=lambda w: (key_lt[w], ids.index(w))))
    pairs: dict[str, float | None] = {}
    for w1, w2 in zip(order, order[1:]):
        dk = key_lt[w2] - key_lt[w1]
        pairs[pair_key(w1, w2)] = None if dk == 0 else (nss[w2] - nss[w1]) / dk
    pairs_roe = {k: None if v is None else v * factor for k, v in pairs.items()}
    return Transmission(sigma0=sigma0, phi=phi, target_eng=target_eng, t_real=t_real,
                        t_local=t_local, roe_equiv=roe_equiv, t_target=t_star, nss=nss, d=d,
                        reference_world=ref_world, pairs=pairs, pairs_roe=pairs_roe, key_lt=key_lt,
                        order=order, roe_factor=factor, sigma0_liab=sigma0_l, split=split, delta0=delta0,
                        lt_spread=st.lt_spreads(sigma0, phi_a, ref_world), phi_assets=phi_a, phi_liab=phi_l,
                        phi_split=p_split, phi_weights=omega,
                        loan_margin=_loan_margin(book, st, bridge, sigma0, phi_a, ref_world),
                        x_lt={w: st.compression(w, 0.0, ref_world) / a_phi for w in ids},
                        level_world=level or ref_world, reference_level=reference_level,
                        share_lt=st.share_lt(ref_world))


def book_slopes(book: "Book", facts: "Facts", tr: Transmission,
                worlds: tuple[str, str] = (BASE_WORLD, MARKET_WORLD)) -> dict[str, float | None]:
    """Наклон ставки (стоимости) каждой книги ЧПД к своей опоре между мирами (Р11-1, проход ядра 9, М§4.4): (r_b,M − r_b,N)
    / (ref_b,M^LT − ref_b,N^LT) на стационаре решённой передачи `tr` — 1 − φ_A [Φ_A] − share_b у актива, β + φ_L [Φ_L]
    dX/dref − share_b у пассива. Одна функция у проверок классов (наклон модели против совместного подбора), листа
    бэктеста книг и печати. Книга, у которой опоры миров совпадают, — None."""
    st = _Stationary(book, facts)
    lo, hi = worlds
    out: dict[str, float | None] = {}
    for b, spec in st.books.items():
        d = st.ref_lt[hi][spec["ref"]] - st.ref_lt[lo][spec["ref"]]
        out[b] = None if d == 0 else (st.book_rate(b, hi, tr) - st.book_rate(b, lo, tr)) / d
    return out


def _loan_margin(book: "Book", st: _Stationary, bridge: Bridge, sigma0: float, phi_assets: float,
                 ref_world: str) -> dict[str, float]:
    """Кредитная маржа стационара мира m_W (М§4.5): доходность кредитного портфеля − CoR режима `norm` с
    κ-добавкой мира (к миру-опоре книги `credit.kappa_reference_world` — любого знака; без ключа — к базовому
    миру, только вверх) − смесь балансирующих активов. Отрицательная — рост кредита в этом мире разрушает
    стоимость."""
    loans = st.roles.loans
    total = sum(st.w[b] for b in loans)
    cor_lt = cor_to_engine(book, bridge, Trajectory(book.get(f"regimes.{REFERENCE_REGIME}.cor")).value(*st.last))
    kappa = float(book.get("credit.kappa"))
    sec = float(book.get("volumes.securities_share_of_liquid"))
    real = {w: Trajectory(book.get(f"worlds.{w}.real_key")).value(*st.last) for w in book.get("worlds.ids")}
    ref = kappa_world(book)                     # мир-опора κ книги; нет ключа — базовый мир (прежнее правило)
    out = {}
    for w in book.get("worlds.ids"):
        rate = lambda b: st.asset_rate(b, w, sigma0, phi_assets, ref_world)  # noqa: E731
        loan_yield = sum(st.w[b] * rate(b) for b in loans) / total
        cor = cor_lt + kappa * kappa_gap(real[w], real[ref or BASE_WORLD], ref is not None)
        balancing = sec * rate(SECURITIES) + (1 - sec) * rate(LIQUIDITY)
        out[w] = loan_yield - cor - balancing
    return out


def nss_value(book: "Book", facts: "Facts", world: str, delta: float, sigma0: float, phi: float,
              sigma0_liab: float = 0.0) -> float:
    """Nss(W, δ) — для тестов и диагностик."""
    st = _Stationary(book, facts)
    return st.nss(world, delta, sigma0, phi, str(get_path(book.data, "nii.transmission.reference_world")),
                  sigma0_liab)


NIM_KEY = "nii.nim_lt_target_mgmt"           # ключ цели ЧПМ книги (упр. базис): стационарная маржа мира уровня


def nim_key_for_stationary(book: "Book", facts: "Facts", bridge: Bridge, world: str, target_mgmt: float) -> float:
    """Ключ цели ЧПМ (`nii.nim_lt_target_mgmt`), при котором стационарная маржа мира `world` на составе баланса
    якоря, переведённая мостом в упр. базис, равна `target_mgmt` (гейт `nim_stationary`, М§14.2). Стационарная
    маржа любого мира линейна по ключу: сдвиги σ0 и сжатие φ линейны по нему и входят в неё слагаемыми — поэтому
    корень берётся по двум решениям передачи (шаг ключа — `nii.transmission.fd_step` книги; линейный вывод —
    `level_for_stationary`, он же у решателя передачи). Остальные ключи книги (цель передачи, доли раскладки, мир
    уровня) — как в книге: у книги с ключом `nii.transmission.level_world`, равным `world`, ключ под цель — сама
    цель. Функцией пользуется лист книги, который выводит ключ из суждения о стационарной марже мира."""
    if world not in book.get("worlds.ids"):
        raise BookError(f"мир {world!r}: нет среди worlds.ids")
    key, step = float(book.get(NIM_KEY)), float(book.get("nii.transmission.fd_step"))

    def stationary(k: float) -> float:
        tr = solve_transmission(book.with_overrides({NIM_KEY: k}), facts, bridge)
        return bridge.to_mgmt_nim(tr.nss[world])

    return level_for_stationary(stationary, key, step, target_mgmt, f"стационарная маржа мира {world}")
