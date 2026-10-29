# -*- coding: utf-8 -*-
"""Предельная доходность кредита на капитал в арифметике книги Совкомбанка против стоимости капитала мира и факта сегмента
отчётности (устав §4; MODEL §14.2, гейт знака объёмных эффектов). Проверка, а не правило: ключей книги лист не пишет.
Переписан под Совкомбанк (решения ведущего № 2, А3): лист Т сверял розничную книгу Т с сегментом розницы Т.

Предельные единицы роста (устав §4): корпоративный кредит (56 % портфеля, весь прирост 1П2026), ипотека, автокредит, кредиты
наличными, карты рассрочки «Халва» и все кредитные книги пропорционально составу. Рубль прироста книг единицы на конец года в
каждой клетке мира; таблица листа (и норма устава §4, якорь, флаги команды) — ОЖИДАНИЕ МИРА: среднее строк клеток мира с
вероятностями слоя «свой взгляд» внутри мира (решения ведущего № 9, класс 2; PLAYBOOK §4, п. 2 — ожидание, а не самая
вероятная клетка; обзор sweep9, A14). Клетка «режим с наибольшей вероятностью × его модальный сценарий» (было — она одна) —
рядом, в записи marginal_modal_cell и в печати:
  * процентный доход — по ставкам книг клетки; фондирование — по состоянию клетки: пока ликвидные активы выше минимума, кредит
    замещает их (теряется их доходность); на минимуме — оптовое фондирование по ставке опта, ликвидные активы растут с активами;
  * резервы — CoR пути клетки × множитель книг единицы ТОЙ ЖЕ формы, что у ядра: множители книг (credit.book_relative, М7), если
    ключ включён, иначе сегментов (credit.segment_relative), нормированные на составе якоря; без схемы — общая CoR клетки;
  * расходы, услуги и страхование — связью строки с объёмом по ТОЙ ЖЕ базе, что у ядра: расходы — взвешенная база
    (opex.volume_weights, М13), если ключ есть, иначе volumes.link_base; комиссии — своя база (fees.volume_base, К2), иначе
    volumes.link_base; страхование и небанковское — своя база (other.insurance_volume_base, К2), иначе volumes.link_base (до
    интеграции круга 3 лист строку страхования не считал — класс 1: в ядре она растёт с базой, в листе нет): прирост базы на
    рубль кредита зависит от фондирования (кредит вместо ликвидных активов процентные активы не растит);
  * фондирование книгами-обязательствами за драйвером строки (К6): книга страховых растёт с базой страхования — рубль кредита
    её базы приносит пассив по ставке книги вместо опта или ликвидности;
  * резерв — покрытие книг единицы (К7, credit.allowance_by_book), иначе доля якоря; опт — по нужде сверх структурной доли
    (К3): кредит фондируется оптом, когда клетка добирает опт по нужде (ряд wholesale_extra), иначе — ликвидностью;
  * капитал — по плотностям книги (у книги выреза — после выреза гарантий, К5) и RWA гарантий за драйвером (база комиссий),
    приведённым к активам под риском клетки, под требование норматива с глиссадой за вычетом доли инструментов капитала:
    «капитал на рубль кредита по плотности».
Два базиса доходности после налога и доли неконтролирующих акционеров: «без кредита за капитал» и «базис сегмента» (капитал сам
фондирует часть кредита по цене фондирования). Норма устава §4: корпоративная книга — стоимость капитала мира ± 5 п.п.; розница —
не ниже 5 %; ниже 5 % или выше 30 % — признак ошибки калибровки.

ПРАВКА 21.10.2026 (решения ведущего № 4, Р4-4, Р4-15; устав §4 изменён; поток book4): норма КБ меряется ЕДИНИЦЕЙ СЕГМЕНТА —
рубль кредита юрлиц + средства юрлиц в отношении сегмента (f = средства / кредиты сегмента «Корпоративный бизнес» на якоре,
1,361; окно R 1,273…1,763 — справочно концами) + гарантии с комиссиями в отношении сегмента (в форме ядра: комиссии и RWA гарантий
идут за базой комиссий, К2/К2б, К5 — их несёт рубль кредита). Средства единицы фондируют её: при оптовом фондировании по нужде —
замещают опт (экономия ставки опта против ставки средств юрлиц клетки), при избытке ликвидности — идут в ликвидные активы
(доходность ликвидности, их RWA; структурный опт К3 растёт со средствами на долю s); расходы на средства — весом М13 книг средств
юрлиц. Факт сегмента по отчётности несёт франшизу средств и гарантий — сравнивать с ним кредит на опте без франшизы нельзя:
кредит юрлиц на опте — справочно. Розница — пропорциональной корзиной розничных книг (не ниже 5 %). Р4-15: «Халва» выше 30 % —
одинаковые на рубль расходы (веса М13 розницы) и страхование (база строки) у розничных книг; проверка розницы — корзиной.
С К8 (проход ядра 3) деньги идут за средствами: единица сегмента понесёт деньги на своих средствах (в ядре p3 — на кредите).
ПРАВКА 22.10.2026 (интеграция круга 6, класс 1 в проверке — экземпляр класса Р6-5): неработающие деньги К8 — В ФОРМЕ ЯДРА. Было:
кредит единицы нёс прочие активы долей книги ρ = volumes.other_assets_to_loans ВМЕСТЕ с деньгами (C_0 / L_0 = 5,6 % кредита) по
плотности книги ω_oa, а средства единицы КБ денег не несли — у ядра с К8 деньги идут за средствами клиентов (М§4.3): кредит несёт
растущие прочие без денег ρ′_q = ρ − c_q D_0 / L_0 по плотности выреза ω′_oa и слагаемое вытесненной части (1 − θ)(ω′_oa − ω_c) δ_q
(Р6-1), средства единицы — деньги c_q × средства по плотности ω_c; масштаб плотностей kscale — на той же формуле RWA, что у ядра.
Без ключа К8 (prep.cash нет) — прежняя строка.

Якорь — факт сегмента «Корпоративный бизнес» (примечание о сегментах МСФО; research/facts/svcb_quarterly.csv, seg_*): прибыль до
налога 2025 года и 1П2026 к капиталу сегмента. Капитал сегментов банк не раскрывает — оценка: средние кредиты сегмента × плотность
корпоративной книги × Н1.0 якоря. Сегмент несёт и доход фондирования средств юрлиц (2,1 трлн ₽ при 1,5 трлн кредитов), и гарантии:
предельный кредит обязан быть ниже среднего сегмента — сверка «сопоставимо по порядку», а не равенство.

ПРАВКА 22.10.2026 (решения ведущего № 6, Р6-5, Р6-6; проверки экономики круга 5 econ5-classes № 1, № 4, № 5 и econ5-blind F2, F3):
  * Р6-5 (класс 1): Δрасходы единиц — В ФОРМЕ ЯДРА: при долях франшиз в базе расходов (opex.line_shares) база — смесь
    A^C = (1 − Σ s) B^C + Σ s_ℓ B^C_0 A^ℓ / A^ℓ_0 (франшизы комиссий и страхования идут за базами своих строк, М§4.7; B^C — на
    нормированных весах ядра ω̂); было — за одной базой М13. Флаг «розница выше 30 %» круга 5 был артефактом этой формы;
  * команда перевывода судит розницу корзиной в КАЖДОМ году листа по норме устава §4 (не ниже 5 %, выше 30 % — признак ошибки);
  * Р6-6 (класс 4 в проверке): якорь сверяется с сегментом на ОДНОЙ мерке — капитал на рубль кредита и вычет (1 − τ)(1 − доля
    неконтролирующих) единицы с обеих сторон (было: капитал сегмента — кредиты × плотность × Н1.0, ×1,19 ниже; доля
    неконтролирующих — только у единицы); рядом — прибыль на рубль кредита по строкам ОПУ сегмента и единицы, остаток назван
    (комиссии сегмента, валюта и прочее, расходы). Прежняя мерка сегмента — в записи справочно.

ПРАВКА 28.10.2026 (решения ведущего № 10, Р10-5; проход ядра 8, М§4.7): при volumes.line_link_form: line франшиза строки в смеси
базы расходов — производная формы строки s B^C_0 λ (Φ̄ / Ā) dA (как строка: λ INS / A dA); было (смесь уровней) — s B^C_0 λ / A_0 dA.
Книги К6 — λ К6 / D dD, как прежде.

ПРАВКА 28.10.2026 (решения ведущего № 11, Р11-1, Р11-2; проход ядра 9): структурный опт К3 (s_w × средства единицы) стоит на
средствах клиентов, как в ядре при volumes.funds_scope: clients — ошибку класса 4 (s мерилась на средствах с книгой К6, а
единица несёт средства юрлиц) снимает ключ ядра; запасные ветви без К3 (доля якоря, нужда) и средняя база слова funds — на
книгах механики ядра (model.book.funds_books). Доли сжатия книг между мирами (phi_share) входят сами: лист читает ставки клеток.

Запуск из корня репозитория:
  python -B data/assumptions/evidence/path/marginal_loan.py            # печать и out/marginal_loan_out.{json,txt}
  python -B data/assumptions/evidence/path/marginal_loan.py --no-write
Код выхода: 0 — посчитано; 2 — ядро ещё не исполняет ветви книги; 1 — отказ книги, фактов или входов.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = (2026, 2027, 2030, 2036)         # год якоря, первый год после него, конец фазы роста, последний год сетки
PAIR_YEARS = (2028, 2030, 2033, 2036)    # годы опыта «книга против замыкания без ограничения роста»
NORM_BAND = 0.05                         # норма устава §4: корпоративная книга — стоимость капитала мира ± 5 п.п.
UNITS = (("kb_unit", "ЕДИНИЦА СЕГМЕНТА КБ: кредит юрлиц + средства юрлиц в отношении сегмента + гарантии с комиссиями (норма §4)",
          ("corp_loans",)),
         ("corp_loans", "корпоративный кредит на опте без франшизы (справочно, Р4-4)", ("corp_loans",)),
         ("retail_basket", "розница пропорционально (корзина розничных книг; норма §4 — не ниже 5 %)", ("auto", "mortgage", "cash_loans", "cards")),
         ("mortgage", "ипотека", ("mortgage",)), ("auto", "автокредиты", ("auto",)),
         ("cash_loans", "кредиты наличными", ("cash_loans",)),
         ("cards", "карты рассрочки «Халва» (Р4-15: выше 30 % — одинаковые на рубль расходы и страхование розничных книг)", ("cards",)),
         ("all_loans", "все кредитные книги пропорционально", None))
SEGMENT_BAL = HERE / "inputs" / "m13_segment_balances.csv"   # остатки сегментов на концы кварталов (кредиты, средства), млн ₽
CORP_FUNDS = ("corp_term", "corp_current")                  # книги средств юрлиц ядра


def segment_funds_ratio(anchor_date: str) -> dict:
    """Средства / кредиты сегмента «Корпоративный бизнес» (МСФО, примечание о сегментах; лист М13 inputs): на якоре — центр единицы
    (Р4-4: «в отношении сегмента», состав якоря); концы окна R (2024К1–2026К2) — справочно."""
    rows = [r for r in csv.DictReader(SEGMENT_BAL.open(encoding="utf-8")) if r["segment"] == "corp"]
    ratio = {r["date"]: float(r["funds"]) / float(r["loans"]) for r in rows}
    window = [v for d, v in ratio.items() if "2024-03-31" <= d <= anchor_date]
    return {"anchor": round(ratio[anchor_date], 6), "window_min": round(min(window), 6), "window_max": round(max(window), 6),
            "by_date": {d: round(v, 4) for d, v in sorted(ratio.items())}}
# Файл фактов передачи для сверки — только из $BANK_HANDOFF_DIR (как у тестов с меткой archive): лист не выходит из
# репозитория по относительному пути и не называет папку передачи; без переменной сверки нет, запись та же.
SEGMENT_FACTS = (Path(os.environ["BANK_HANDOFF_DIR"]) / "research" / "facts" / "svcb_quarterly.csv"
                 if os.environ.get("BANK_HANDOFF_DIR") else None)
# Факт сегмента «Корпоративный бизнес» [Ф: МСФО, примечание о сегментах; research/facts/svcb_quarterly.csv — seg_pbt_corp,
# seg_loans_corp]: прибыль до налога и кредиты сегмента на концы периодов, млрд ₽. Числа — здесь же (лист не зависит от
# каталога передачи): файл передачи сверяется, если доступен.
SEGMENT = {
    "FY2025": {"pbt": 80.831, "loans_open": 1182.501, "loans_close": 1543.942, "years": 1.0,
               "src": "FY2025_ifrs_fs.pdf, с. 36 (сегменты, 12М), с. 38–39 (кредиты сегментов)"},
    "1H2026": {"pbt": 37.532, "loans_open": 1543.942, "loans_close": 1529.121, "years": 0.5,
               "src": "2026Q2_ifrs_fs.pdf, с. 13 (сегменты, 6М), с. 15 (кредиты сегментов)"},
}


class NeedCore(RuntimeError):
    """Ядро не готово: нет ветви, ряда клетки или функции."""


def repo_root() -> Path:
    root = HERE
    while not (root / "model" / "book.py").exists():
        if root.parent == root:
            raise NeedCore("не найден каталог model/ выше листа — запуск из дерева репозитория")
        root = root.parent
    return root


def pc(x: float, n: int = 1) -> str:
    return f"{100 * float(x):.{n}f}"


def cor_multipliers(book, af, loans: tuple) -> dict:
    """Множители CoR кредитных книг в форме ядра, нормированные на составе якоря (Σ доля × множитель = 1)."""
    rel = book.opt("credit.book_relative")
    if rel is not None and rel.get("enabled"):
        raw = {b: float(rel["by_book"][b]) for b in loans}
    elif book.get("credit.segment_relative.enabled"):
        seg = {"corporate": float(book.get("credit.segment_relative.corporate")), "retail": float(book.get("credit.segment_relative.retail"))}
        raw = {b: seg[str(book.get(f"nii.books.{b}.cor_segment"))] for b in loans}
    else:
        return {b: 1.0 for b in loans}
    bal = {b: float(af.balances[b]) - (float(af.fv_loans) if b == af.fv_book else 0.0) for b in loans}
    norm = sum(bal[b] * raw[b] for b in loans) / sum(bal.values())
    return {b: raw[b] / norm for b in loans}


def marginal(run, book, cell, year: int, books: tuple, mult: dict, funds: float = 0.0) -> dict:
    """Рубль прироста кредита книг `books` в клетке на конец года `year`; `funds` — средства юрлиц единицы на рубль кредита (единица
    сегмента КБ, Р4-4): фондируют единицу (замещают опт по нужде или идут в ликвидность), несут свою ставку и расходы М13."""
    ctx = run.ctx
    tl, p = ctx.timeline, ctx.prep
    roles, dens = p.roles, book.get("capital.rwa.density")
    link_o, link_f = float(book.get("opex.volume_link")), float(book.get("fees.volume_link"))
    link_i = float(book.opt("other.insurance_volume_link") or 0.0)
    link_base = str(book.get("volumes.link_base"))
    weights = book.opt("opex.volume_weights")
    m_min = float(book.get("volumes.liquid_min_share"))
    liquid = [b for b in roles.assets if b not in roles.loans]
    q = cell.quarters
    qs = [k for k in tl.quarters_of_year(year) if 1 <= k <= tl.Q]
    last = qs[-1]
    bal = {b: cell.books[b]["balance"][last] for b in cell.books}
    avg = {b: sum(cell.books[b]["avg"][k] for k in qs) / len(qs) for b in cell.books}
    loans = sum(bal[b] for b in books)
    yld = sum(cell.books[b]["rate"][last] * bal[b] for b in books) / loans
    liq = sum(bal[b] for b in liquid)
    yld_liq = sum(cell.books[b]["rate"][last] * bal[b] for b in liquid) / liq
    r_wh = cell.books["wholesale"]["rate"][last]
    scale = 4 / len(qs)
    loans_avg = sum(q["loans_ac_avg"][k] for k in qs) / len(qs)
    cor_real = sum(q["llp"][k] for k in qs) * scale / loans_avg
    comp = sum(mult[b] * avg[b] for b in roles.loans) / sum(avg[b] for b in roles.loans)
    cor_path = cor_real / comp                             # CoR пути клетки на составе якоря (с κ и δ)
    cor = cor_path * sum(mult[b] * bal[b] for b in books) / loans
    opex = sum(q["opex"][k] for k in qs) * scale
    fees = sum(q["fees"][k] for k in qs) * scale
    ins = sum(q["ins"][k] for k in qs) * scale
    oa, ol = p.oa_ratio, p.ol_ratio
    k8 = getattr(p, "cash", None)                       # К8 в форме ядра (М§4.3, §4.11; интеграция круга 6)
    if k8 is not None:
        oa = k8.rho_q[last] if k8.rho_q is not None else k8.rho          # растущие прочие без денег на рубль кредита
        c_q = k8.share_q[last] if k8.share_q is not None else k8.share  # деньги на рубль средств клиентов
        w_oa, w_c = float(p.rwa_w.other_assets_cash), float(p.rwa_w.cash)
        shift = k8.shift_q[last] if k8.shift_q is not None else 0.0     # (1 − θ)(ω′_oa − ω_c) δ_q (Р6-1)
    else:
        c_q, w_oa, w_c, shift = 0.0, float(dens["other_assets"]), 0.0, 0.0
    # К7: резерв по книгам — покрытие книг единицы (остаток резерва вне книг R_0 — пропорционально кредитам, здесь не делится)
    al = (sum(p.allow_cov[b] * bal[b] for b in books) / loans if getattr(p, "allow_cov", None) is not None
          else p.allowance_ratio)
    tau = q["tau_eff"][last]
    # ПРАВКА 28.10.2026 (решения ведущего № 11, Р11-2; проход ядра 9): «средства» опта — книги слова funds механики ядра
    # (model.book.funds_books: при volumes.funds_scope: clients — средства клиентов без книг К6; без ключа — ряд funds клетки)
    from model.book import funds_books
    words = funds_books(roles, book)

    def funds_end(k: int) -> float:
        return q["funds"][k] if len(words) == len(roles.funds) else sum(cell.books[b]["balance"][k] for b in words)

    # опт по нужде (К3 — сверх структурной доли; без К3 — сверх доли якоря): кредит фондируется оптом, когда клетка его добирает
    at_floor = (q["wholesale_extra"][last] > 1e-9 if "wholesale_extra" in q
                else q["wholesale"][last] / funds_end(last) > q["wholesale"][0] / funds_end(0) * (1 + 1e-6))
    nonliq = (1 - al) + oa + c_q * funds                # деньги на средствах единицы (К8) — неработающий актив
    rw_loans = dict(p.rwa_w.loans)                      # плотности кредитных книг ядра (у книги выреза — после выреза, К5)
    dn = lambda b: float(rw_loans[b]) if b in rw_loans else float(dens[b])  # noqa: E731
    dens_l = sum(dn(b) * bal[b] for b in books) / loans
    dens_liq = sum(float(dens[b]) * bal[b] for b in liquid) / liq
    rwa = q["rwa"][last]
    g_rwa = float(q["rwa_guar"][last]) if "rwa_guar" in q and q["rwa_guar"][last] is not None else 0.0
    if k8 is not None:                                  # формула RWA ядра с К8: ω′_oa (OA − F_A − C) + ω_c C + слагаемое
        cash_q = float(q["cash"][last])
        rwa_formula = (sum(dn(b) * bal[b] for b in cell.books if b in dens)
                       + w_oa * (q["other_assets"][last] - (p.oa_fixed or 0) - cash_q) + w_c * cash_q
                       + shift * sum(bal[b] for b in roles.loans))
    else:
        rwa_formula = (sum(dn(b) * bal[b] for b in cell.books if b in dens)
                       + float(dens["other_assets"]) * (q["other_assets"][last] - (p.oa_fixed or 0)))
    oa_rwa = oa * w_oa + shift + c_q * funds * w_c       # RWA прочих активов и денег единицы на рубль кредита
    kscale = (rwa - g_rwa) / rwa_formula                # RWA гарантий несут те же множители (дрейф, валюта, режим)
    # К6: книги-обязательства за драйвером строки — пассив на рубль базы строки (связь × остаток книги / уровень базы)
    driven = getattr(p, "driven", None) or {}

    def d_end(lb, d_liquid_: float) -> float:
        """Прирост уровня базы строки на конец квартала на рубль кредита единицы (К2, К5, К6)."""
        if lb is None or lb.kind == "loans":
            return 1.0
        if lb.kind == "books":
            w = {b: float(lb.weights.get(b, 0.0)) for b in cell.books}
            return sum(w[b] * bal[b] for b in books) / loans + d_liquid_ * sum(w[b] * bal[b] for b in liquid) / liq
        if lb.kind == "iea":
            return 1.0 + d_liquid_
        return 0.0                                      # средства клиентов, номинал — кредит их не растит

    def level_end(lb) -> float:
        if lb is None or lb.kind == "loans":
            return sum(bal[b] for b in roles.loans)
        if lb.kind == "books":
            return sum(float(w) * bal[b] for b, w in lb.weights.items())
        if lb.kind == "iea":
            return sum(bal[b] for b in roles.assets)
        return 1.0

    def liab_driven(d_liquid_: float) -> tuple[float, float]:
        """Пассив книг-обязательств (К6) на рубль кредита и его ставка (средняя по книгам)."""
        amt, cost = 0.0, 0.0
        for b, (lb, lam) in driven.items():
            x = lam * bal[b] / level_end(lb) * d_end(lb, d_liquid_)
            amt += x
            cost += x * cell.books[b]["rate"][last]
        return amt, (cost / amt if amt else 0.0)

    cf_bal = sum(bal[b] for b in CORP_FUNDS)
    r_cf = sum(cell.books[b]["rate"][last] * bal[b] for b in CORP_FUNDS) / cf_bal if funds else 0.0
    s_struct = book.opt("volumes.wholesale_structural_to_funds")          # К3: структурный опт растёт со средствами
    s_w = float(s_struct) if s_struct is not None else float(q["wholesale"][0] / funds_end(0))
    if at_floor:
        d_liq = m_min / (1 - m_min) * nonliq
        dl, r_dl = liab_driven(d_liq)
        funded = nonliq + d_liq - ol - dl - funds       # оптовое фондирование на рубль кредита (средства единицы его замещают)
        d_rwa = (dens_l + oa_rwa + d_liq * dens_liq) * kscale
        d_nii, fund_rate = yld + d_liq * yld_liq - funded * r_wh - dl * r_dl - funds * r_cf, r_wh
        d_liquid = d_liq
    else:
        extra = funds * (1 + s_w)                        # средства единицы и структурный опт под них — в ликвидность
        dl, r_dl = liab_driven(-(nonliq - ol) + extra)
        funded = nonliq - ol - dl                       # из ликвидных активов
        d_rwa = (dens_l + oa_rwa - (funded - extra) * dens_liq) * kscale
        d_nii, fund_rate = yld - (funded - extra) * yld_liq - dl * r_dl - funds * r_cf - funds * s_w * r_wh, yld_liq
        d_liquid = extra - funded
    guar = getattr(p, "guar", None)
    if guar is not None and g_rwa:                      # К5: RWA гарантий за драйвером (база комиссий) на рубль кредита
        d_rwa += g_rwa / level_end(guar.base) * d_end(guar.base, d_liquid)
    # прирост базы связи с объёмом на рубль кредита и средняя база года — той же формы, что у ядра
    iea_avg = sum(avg[b] for b in roles.assets)
    funds_avg = sum(avg[b] for b in words)               # слово funds базы связи (Р11-2): книги механики ядра
    loans_avg_all = sum(avg[b] for b in roles.loans)

    def base_link(kind: str) -> tuple[float, float]:
        if kind == "iea":
            return 1.0 + d_liquid, iea_avg
        if kind == "loans":
            return 1.0, loans_avg_all
        if kind == "funds":
            return 0.0, funds_avg                       # прирост средств клиентов кредит не создаёт (фондирование — опт/ликвидность)
        raise RuntimeError(f"незнакомая база связи {kind!r}")

    def line_link(lb) -> tuple[float, float]:
        """Прирост средней базы строки на рубль кредита и средняя база года — своя база строки (К2) или link_base."""
        if lb is None:
            return base_link(link_base)
        if lb.kind == "books":
            w = {b: float(lb.weights.get(b, 0.0)) for b in cell.books}
            return (sum(w[b] * bal[b] for b in books) / loans + d_liquid * sum(w[b] * bal[b] for b in liquid) / liq,
                    sum(w[b] * avg[b] for b in cell.books))
        if lb.kind == "nominal":
            return 0.0, 1.0                             # номинал кредит не растит
        return base_link(lb.kind)

    def m13_link(w: dict) -> tuple[float, float]:
        """Прирост взвешенной базы М13 на рубль кредита единицы и её средняя года — на весах `w` (книги, средства юрлиц единицы)."""
        w = {b: float(w.get(b, 0.0)) for b in cell.books}
        w_book = sum(w[b] * bal[b] for b in books) / loans
        w_liq = sum(w[b] * bal[b] for b in liquid) / liq
        w_cf = sum(w[b] * bal[b] for b in CORP_FUNDS) / cf_bal
        return w_book + d_liquid * w_liq + funds * w_cf, sum(w[b] * avg[b] for b in cell.books)

    d_base_f, base_f = line_link(getattr(p, "fees_line", None))
    d_base_i, base_i = line_link(getattr(p, "ins_line", None))
    mix = None
    if getattr(p, "line_shares", None) and getattr(p, "opex_w", None) is not None:
        # ПРАВКА 22.10.2026 (решения ведущего № 6, Р6-5; проверки экономики econ5-classes № 1 и econ5-blind F2, класс 1): база
        # расходов — В ФОРМЕ ЯДРА, смесью с долями франшиз (opex.line_shares, М§4.7): A^C = (1 − Σ s) B^C + Σ s_ℓ B^C_0 A^ℓ / A^ℓ_0 —
        # B^C на нормированных весах ядра ω̂ (p.opex_w), A^ℓ — база строки (p.fees_line / p.ins_line), B^C_0, A^ℓ_0 — квартал якоря
        # (p.mix_b0, p.mix_src); средняя года — ряд vol_opex клетки (при долях франшиз он и есть смесь). Было: Δрасходы за одной
        # базой М13 (франшиза страхования и комиссий шла за весами книг, а не за базами строк) — ложный флаг «розница выше 30 %».
        d_b13, b13_avg = m13_link(p.opex_w)
        d_mix = p.mix_keep * d_b13
        parts = {"keep": p.mix_keep * d_b13}
        nominal = getattr(p, "share_nominal", None) or {}
        link_line = bool(getattr(p, "link_line", False))
        for line, share in p.line_shares.items():
            _src, a0 = p.mix_src[line]
            d_l = d_base_f if line == "fees" else d_base_i
            parts[line] = share * p.mix_b0 * d_l / a0
            if line in nominal and link_line:
                # ПРАВКА 28.10.2026 (решения ведущего № 10, Р10-5; проход ядра 8, М§4.7; класс 1): франшиза формой строки
                # Φ_q = Φ_(q−4) g(A_q / A_(q−4), w, λ, κ) — производная формы строки, как у самой строки (λ INS / A dA):
                # s B^C_0 λ (Φ̄ / Ā) dA, Φ̄ — средний индекс франшизы года (ряд vol_phi_<строка>), Ā — средняя база строки года
                lam_l, _, phi_name = nominal[line]
                phi_bar = sum(float(q[phi_name][k]) for k in qs) / len(qs)
                a_bar = base_f if line == "fees" else base_i
                parts[line] = share * p.mix_b0 * float(lam_l) * phi_bar / a_bar * d_l
            elif line in nominal:
                # ПРАВКА 22.10.2026 (решения ведущего № 8, Р8-6; проход ядра 6, М§4.7; поток integrate8; класс 1): франшиза строки
                # в смеси — за связью строки λ: с предельным кредитом растёт только доля λ (за базой строки), номинальная часть
                # 1 − λ (зарплаты мира с корнем κ) от кредита не зависит — та же форма, что строка (её Δвыручка — link_i × …)
                parts[line] *= float(nominal[line][0])
            d_mix += parts[line]
        base_o = sum(float(q["vol_opex"][k]) for k in qs) / len(qs)
        d_base_o = d_mix
        mix = {"base_avg": round(base_o, 3), "b13_avg": round(b13_avg, 3), "d_base": round(d_mix, 6),
               "parts": {k: round(v, 6) for k, v in parts.items()}}
    elif weights:
        d_base_o, base_o = m13_link(weights)
    else:
        d_base_o, base_o = base_link(link_base)
    d_opex, d_fees = link_o * opex / base_o * d_base_o, link_f * fees / base_f * d_base_f
    d_ins = link_i * ins / base_i * d_base_i
    cap = d_rwa * (q["req20_glide"][last] - p.t2[last] / rwa)
    pre = d_nii - cor - d_opex + d_fees + d_ins
    keep = (1 - tau) * (1 - p.nci_share)
    return {"year": year, "funded_by": "wholesale" if at_floor else "liquid", "funds_per_loan": round(funds, 6),
            "funds_rate": round(r_cf, 6),
            "loan_yield": round(yld, 6), "funding_rate": round(fund_rate, 6),
            "d_nii": round(d_nii, 6), "cor": round(cor, 6), "cor_path": round(cor_path, 6), "d_opex": round(d_opex, 6),
            "d_fees": round(d_fees, 6), "d_ins": round(d_ins, 6), "liab_driven": round(dl, 6), "allowance": round(al, 6),
            "pre_tax": round(pre, 6), "rwa_per_loan": round(d_rwa, 6), "capital": round(cap, 6),
            "return_no_capital_credit": round(pre * keep / cap, 6),
            "return_segment_basis": round((pre + cap * fund_rate) * keep / cap, 6),
            "return_segment_basis_pre_tax": round((pre + cap * fund_rate) / cap, 6),
            "cell_roe": round(cell.annual["roe"][cell.years.index(year)], 6), "cost_of_equity": round(cell.k_t, 6),
            "hurdle_norm": round(cell.k_t - NORM_BAND, 6),
            "ceiling_norm": round(cell.k_t + NORM_BAND, 6),          # верхний край нормы §4 (решения ведущего № 5, Р5-11)
            "pre_tax_segment_basis": round(pre + cap * fund_rate, 6),   # прибыль до налога на рубль кредита, базис сегмента (Р6-6)
            "keep": round(keep, 6),                                    # (1 − τ)(1 − доля неконтролирующих) — вычет единицы (Р6-6)
            "opex_mix": mix}                                           # база расходов в форме ядра (Р6-5): средняя года, прирост, части


def segment_fact(book, af, tax: float) -> dict:
    """КБ: прибыль до налога к оценке капитала сегмента (средние кредиты × плотность корпоративной книги × Н1.0 якоря)."""
    dens = float(book.get("capital.rwa.density")["corp_loans"])
    n20 = float(af.n20)
    out = {}
    for k, s in SEGMENT.items():
        cap = (s["loans_open"] + s["loans_close"]) / 2 * dens * n20
        pre = s["pbt"] / s["years"] / cap
        out[k] = {"pbt_annual": round(s["pbt"] / s["years"], 3), "capital_estimate": round(cap, 3), "pre_tax": round(pre, 6),
                  "after_tax": round(pre * (1 - tax), 6), "src": s["src"]}
    check = {}
    if SEGMENT_FACTS is not None and SEGMENT_FACTS.exists():   # сверка чисел листа с файлом фактов передачи (если задан)
        rows = {}
        with SEGMENT_FACTS.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["metric"] in ("seg_pbt_corp", "seg_loans_corp"):
                    rows[(r["period"], r["metric"])] = float(r["value"]) / 1000
        check = {"FY2025_pbt": rows.get(("2025M12", "seg_pbt_corp")), "1H2026_pbt": rows.get(("2026M6", "seg_pbt_corp")),
                 "loans_2026_06_30": rows.get(("2026-06-30", "seg_loans_corp"))}
    return {"by_period": out, "density_corp_loans": dens, "n20_anchor": n20, "tax": tax, "file_check": check}


SEGMENT_PNL = HERE / "inputs" / "m13_segment_pnl.csv"   # ОПУ сегментов МСФО (примечание о сегментах), млн ₽


def segment_lines(period: str) -> dict:
    """Строки ОПУ сегмента «Корпоративный бизнес» на рубль средних кредитов сегмента (решения ведущего № 6, Р6-6: печать «прибыль на
    рубль кредита» и разбор остатка): ЧПД с трансфертом (проценты + межсегментный доход − процентные расходы − межсегментный
    расход), комиссии нетто, валюта и прочие доходы, небанковское нетто, АСВ, расходы (персонал + прочие); неявная CoR — остаток
    до прибыли до налога факта."""
    rows = {r["period"]: r for r in csv.DictReader(SEGMENT_PNL.open(encoding="utf-8")) if r["segment"] == "corp"}
    r = {k: float(v) / 1000 for k, v in rows[period].items() if k not in ("period", "segment", "source")}
    s = SEGMENT[{"FY2025": "FY2025", "1H2026": "1H2026"}[period]]
    loans = (s["loans_open"] + s["loans_close"]) / 2
    y = s["years"]
    per = lambda x: x / y / loans  # noqa: E731
    out = {"nii_transfer": per(r["ii"] + r["interseg_rev"] - r["ie"] - r["interseg_exp"]), "fees": per(r["fee_inc"] - r["fee_exp"]),
           "fx_other": per(r["fx"] + r["oth_inc"]), "nonbank": per(r["nb_rev"] - r["nb_cost"]), "dia": per(r["dia"]),
           "opex": per(r["staff"] + r["other"]), "pbt": s["pbt"] / y / loans}
    out["cor_implied"] = (out["nii_transfer"] + out["fees"] + out["fx_other"] + out["nonbank"] - out["dia"] - out["opex"] - out["pbt"])
    return {k: round(v, 6) for k, v in out.items()}


def segment_same_measure(fact: dict, units: dict) -> dict:
    """Сегмент КБ на ТОЙ ЖЕ мерке, что единица сегмента КБ (решения ведущего № 6, Р6-6; проверки экономики econ5-classes № 4 и
    econ5-blind F3, класс 4 в проверке): капитал на рубль кредита — капитал единицы года якоря своего мира (RWA единицы с прочими
    активами, ликвидностью средств и гарантиями × требование с глиссадой за вычетом доли инструментов), вычет — тот же (1 − τ)(1 −
    доля неконтролирующих). Было: капитал сегмента — средние кредиты × плотность корпоративной книги × Н1.0 якоря (×1,19 ниже
    капитала единицы), доля неконтролирующих — только у единицы."""
    out = {}
    for k, s in SEGMENT.items():
        pre = s["pbt"] / s["years"] / ((s["loans_open"] + s["loans_close"]) / 2)
        out[k] = {"pbt_per_loan": round(pre, 6),
                  "by_world": {w: round(pre * u["keep"] / u["capital"], 6) for w, u in units.items()}}
    return out


def expect_row(rows: dict, prob: dict, modal_key) -> dict:
    """Ожидание строк клеток мира (вероятности слоя внутри мира): числа — среднее с весами; слова (чем фондируется) и база
    расходов — модальной клетки; вложенные словари чисел (концы отношения сегмента) — тем же средним."""
    total = sum(prob[k] for k in rows)
    base = rows[modal_key]
    out: dict = {}
    for f, v in base.items():
        if isinstance(v, bool) or f == "opex_mix":
            out[f] = v
        elif isinstance(v, (int, float)):
            out[f] = round(sum(prob[k] * float(r[f]) for k, r in rows.items()) / total, 6)
        elif isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values()):
            out[f] = {kk: round(sum(prob[k] * float(r[f][kk]) for k, r in rows.items()) / total, 6) for kk in v}
        else:
            out[f] = v
    out["year"] = base["year"]
    out["cells"] = len(rows)
    out["range_return_segment_basis"] = [round(min(r["return_segment_basis"] for r in rows.values()), 6),
                                         round(max(r["return_segment_basis"] for r in rows.values()), 6)]
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="предельная доходность кредита на капитал против стоимости капитала и сегмента")
    ap.add_argument("--book", type=Path, default=None, help="машинная книга (по умолчанию — data/assumptions/assumptions.yaml)")
    ap.add_argument("--facts", type=Path, default=None, help="каталог фактов (по умолчанию — data/facts)")
    ap.add_argument("--no-write", action="store_true", help="не писать out/marginal_loan_out.json и .txt")
    ap.add_argument("--out", type=Path, default=None, help="куда писать JSON (по умолчанию — out/marginal_loan_out.json листа)")
    ap.add_argument("--no-pair", action="store_true", help="без опыта «книга против замыкания без ограничения роста»")
    a = ap.parse_args(argv)
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text)

    try:
        root = repo_root()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            from model import book_schema
            from model.book import anchor_facts, load_book, load_facts
            from model.grid import modal_cell, run_grid
            from model.live import live_from_book
        except ImportError as exc:
            raise NeedCore(f"ядро ещё не исполняет ветви книги: {exc}") from exc
        facts = load_facts(a.facts)
        try:
            book = load_book(a.book, facts=facts)
        except book_schema.BookError as exc:
            if "не реализовано" in str(exc):
                raise NeedCore(str(exc)) from exc
            raise
        run = run_grid(book, facts, live_from_book(book, facts))
        _, regime, scenario = modal_cell(book, run.ctx.posterior)
        worlds = list(book.get("joint.world_prob"))
        cells = {w: run.cell(w, regime, scenario) for w in worlds}
        own = run.layers["analytical"].prob                 # вероятности слоя «свой взгляд»: ожидание мира — по клеткам мира
        af = anchor_facts(facts, book.get("nii.books"))
        roles = run.ctx.prep.roles
        mult = cor_multipliers(book, af, tuple(roles.loans))
        tax = float(book.get("tax.statutory")["LT"]) + float(book.get("tax.effective_gap"))
        fact = segment_fact(book, af, tax)
        out: dict = {"book_version": book.get("meta.version"), "book_date": str(book.get("meta.date")), "regime": regime,
                     "scenario": scenario, "cor_multipliers": {b: round(v, 6) for b, v in mult.items()},
                     "links": {"opex.volume_link": float(book.get("opex.volume_link")), "fees.volume_link": float(book.get("fees.volume_link")),
                               "volumes.link_base": str(book.get("volumes.link_base")),
                               "opex.volume_weights": book.opt("opex.volume_weights")},
                     "liquid_min_share": float(book.get("volumes.liquid_min_share")), "segment": fact, "marginal": {}, "pair": {},
                     "basis": "ожидание мира (слой «свой взгляд» внутри мира; решения № 9, класс 2); модальная клетка — marginal_modal_cell",
                     "marginal_modal_cell": {}}
        say(f"книга {out['book_version']} от {out['book_date']}; клетки: режим {regime}, сценарий {scenario}; связь расходов "
            f"{out['links']['opex.volume_link']} (база {'взвешенная, М13' if out['links']['opex.volume_weights'] else out['links']['volumes.link_base']}), "
            f"услуг {out['links']['fees.volume_link']}; множители CoR книг на составе якоря: "
            + ", ".join(f"{b} {v:.3f}" for b, v in mult.items()))
        seg_f = segment_funds_ratio(str(facts.plain("anchor", "facts_date")) if facts.has("anchor", "facts_date") else "2026-06-30")
        out["segment_funds_ratio"] = seg_f
        say(f"единица сегмента КБ (Р4-4): средства юрлиц на рубль кредита — {seg_f['anchor']:.3f} (сегмент на якоре; окно R "
            f"{seg_f['window_min']:.3f}…{seg_f['window_max']:.3f} — справочно концами)")
        for key, label, books in UNITS:
            books = tuple(roles.loans) if books is None else books
            say()
            say(f"{label}: мир год | доходность кредита / ставка фондирования (чем) | ΔЧПД, CoR, Δрасходы, Δуслуги, Δстрахование | до налога | "
                f"RWA на рубль, капитал | после налога: без кредита за капитал | базис сегмента (до налога) | ROE клетки, k; % кредита")
            out["marginal"][key] = {}
            out["marginal_modal_cell"][key] = {}
            for w in worlds:
                out["marginal"][key][w] = []
                out["marginal_modal_cell"][key][w] = []
                world_cells = [c for c in run.cells if c.world == w]
                for y in YEARS:
                    rows = {}
                    for c in world_cells:
                        m = marginal(run, book, c, y, books, mult, funds=seg_f["anchor"] if key == "kb_unit" else 0.0)
                        if key == "kb_unit":                # концы отношения сегмента — справочно (окно R)
                            m["ends"] = {e: marginal(run, book, c, y, books, mult, funds=seg_f[e])["return_segment_basis"]
                                         for e in ("window_min", "window_max")}
                        rows[c.key] = m
                    modal_m = rows[cells[w].key]
                    m = expect_row(rows, own, cells[w].key)
                    out["marginal"][key][w].append(m)
                    out["marginal_modal_cell"][key][w].append(modal_m)
                    say(f"  {w} {y}: {pc(m['loan_yield'], 2)} / {pc(m['funding_rate'], 2)} ({'опт' if m['funded_by'] == 'wholesale' else 'ликв.'}) | "
                        f"{pc(m['d_nii'], 2)} {pc(m['cor'], 2)} {pc(m['d_opex'], 2)} {pc(m['d_fees'], 2)} {pc(m['d_ins'], 2)} | {pc(m['pre_tax'], 2)} | "
                        f"{m['rwa_per_loan']:.3f}, {pc(m['capital'])} | {pc(m['return_no_capital_credit'])} | {pc(m['return_segment_basis'])} "
                        f"({pc(m['return_segment_basis_pre_tax'])}) | {pc(m['cell_roe'])} {pc(m['cost_of_equity'])} || модальная клетка "
                        f"{regime}/{scenario}: {pc(modal_m['return_segment_basis'])}; клетки мира {pc(m['range_return_segment_basis'][0])}…"
                        f"{pc(m['range_return_segment_basis'][1])}")
        say()
        fp = fact["by_period"]
        say("Сегмент «Корпоративный бизнес» (примечание о сегментах МСФО; капитал — оценка: средние кредиты × плотность "
            f"{fact['density_corp_loans']:.3f} × Н1.0 якоря {pc(fact['n20_anchor'], 2)} %): "
            + "; ".join(f"{k}: прибыль до налога {v['pbt_annual']} млрд ₽ в год на капитал {v['capital_estimate']:.1f} — {pc(v['pre_tax'])} % "
                        f"до налога, {pc(v['after_tax'])} % после" for k, v in fp.items()))
        corp = out["marginal"]["kb_unit"]                 # Р4-4: якорь и норма — единицей сегмента КБ
        first = [corp[w][0]["return_segment_basis"] for w in worlds]
        # ПРАВКА 22.10.2026 (решения ведущего № 6, Р6-6): сверка якоря — одна мерка капитала и вычета с обеих сторон; рядом — прибыль
        # на рубль кредита; остаток назван строками ОПУ сегмента против единицы
        same = segment_same_measure(fact, {w: {"capital": corp[w][0]["capital"], "keep": corp[w][0]["keep"]} for w in worlds})
        seg = [v for s in same.values() for v in s["by_world"].values()]
        seg_old = [v["after_tax"] for v in fp.values()]
        out["segment_same_measure"] = same
        out["anchor_check"] = {"model_min": min(first), "model_max": max(first), "segment_low": min(seg), "segment_high": max(seg),
                               "gap_to_segment_low": round(min(first) - min(seg), 6), "unit": "kb_unit",
                               "measure": "капитал и вычет единицы с обеих сторон (Р6-6)",
                               "segment_old_measure": [min(seg_old), max(seg_old)]}
        loan = [out["marginal"]["corp_loans"][w][0]["return_segment_basis"] for w in worlds]
        say(f"На якоре ({YEARS[0]} год) единица сегмента КБ на базисе сегмента даёт {pc(min(first))}–{pc(max(first))} % после налога "
            f"при {pc(min(seg))}–{pc(max(seg))} % у сегмента НА ТОЙ ЖЕ МЕРКЕ (капитал на рубль кредита и вычет (1 − τ)(1 − доля "
            f"неконтролирующих) — единицы, Р6-6; прежняя мерка — {pc(min(seg_old))}–{pc(max(seg_old))} %); кредит юрлиц на опте без "
            f"франшизы (справочно) — {pc(min(loan))}–{pc(max(loan))} %.")
        u0 = corp[worlds[0]][0]
        lines_seg = {k: segment_lines(k) for k in SEGMENT}
        unit_lines = {w: {"nii_transfer": corp[w][0]["d_nii"] + corp[w][0]["capital"] * corp[w][0]["funding_rate"],
                          "fees": corp[w][0]["d_fees"], "fx_other": 0.0, "nonbank": corp[w][0]["d_ins"], "opex": corp[w][0]["d_opex"],
                          "cor": corp[w][0]["cor"], "pbt": corp[w][0]["pre_tax_segment_basis"], "capital": corp[w][0]["capital"]}
                      for w in worlds}
        out["anchor_lines"] = {"segment": lines_seg, "unit_2026": {w: {k: round(v, 6) for k, v in d.items()} for w, d in unit_lines.items()}}
        say("Прибыль на рубль кредита (базис сегмента, до налога), % кредита: " + "; ".join(
            f"сегмент {k}: ЧПД с трансфертом {pc(v['nii_transfer'], 2)}, комиссии {pc(v['fees'], 2)}, валюта и прочее {pc(v['fx_other'], 2)}, "
            f"небанковское {pc(v['nonbank'], 2)}, АСВ {pc(v['dia'], 2)}, расходы {pc(v['opex'], 2)}, неявная CoR {pc(v['cor_implied'], 2)} → "
            f"прибыль до налога {pc(v['pbt'], 2)}" for k, v in lines_seg.items())
            + "; единица КБ 2026 (" + ", ".join(worlds) + "): " + " / ".join(
            f"ЧПД с кредитом за капитал {pc(d['nii_transfer'], 2)}, комиссии {pc(d['fees'], 2)}, страхование {pc(d['nonbank'], 2)}, "
            f"CoR {pc(d['cor'], 2)}, расходы {pc(d['opex'], 2)} → {pc(d['pbt'], 2)}" for d in unit_lines.values()))
        res_lines = {k: {"fees": v["fees"] - u0["d_fees"], "fx_other": v["fx_other"], "opex": -(v["opex"] - u0["d_opex"]),
                         "pbt": v["pbt"] - u0["pre_tax_segment_basis"]} for k, v in lines_seg.items()}
        out["anchor_residual"] = {k: {kk: round(vv, 6) for kk, vv in d.items()} for k, d in res_lines.items()}
        say("Остаток сегмента против единицы (мир " + worlds[0] + ", п.п. кредита): " + "; ".join(
            f"{k}: прибыль до налога {pc(d['pbt'], 2)}, из них комиссии {pc(d['fees'], 2)}, валюта и прочее {pc(d['fx_other'], 2)}, "
            f"расходы {pc(d['opex'], 2)}" for k, d in res_lines.items())
            + " (у единицы «прочего» нет: строка в реальных рублях, с объёмом не растёт; комиссии сегмента несут и расчётные услуги)")
        modal_corp = out["marginal_modal_cell"]["kb_unit"]
        say("Норма устава §4 (единица сегмента КБ — k ± 5 п.п.; розница — корзиной, не ниже 5 %), последний год сетки, базис сегмента, "
            "ОЖИДАНИЕ МИРА (модальная клетка — в скобках): "
            + "; ".join(f"{w}: единица КБ {pc(corp[w][-1]['return_segment_basis'])} % (модальная клетка "
                        f"{pc(modal_corp[w][-1]['return_segment_basis'])}; концы отношения сегмента "
                        f"{pc(corp[w][-1]['ends']['window_min'])}…{pc(corp[w][-1]['ends']['window_max'])}) при k {pc(corp[w][-1]['cost_of_equity'])} % — "
                        + ("в норме" if abs(corp[w][-1]['return_segment_basis'] - corp[w][-1]['cost_of_equity']) <= 0.05 else "ВНЕ нормы")
                        + f"; розница корзиной {pc(out['marginal']['retail_basket'][w][-1]['return_segment_basis'])} % (модальная клетка "
                        f"{pc(out['marginal_modal_cell']['retail_basket'][w][-1]['return_segment_basis'])})"
                        for w in worlds))
        if not a.no_pair:
            free = run_grid(book.with_overrides({"capital.growth_constraint.enabled": False}), facts, live_from_book(book, facts))
            tl = run.ctx.timeline
            say()
            say("Опыт на ядре (книга против замыкания без ограничения роста капиталом): прирост прибыли акционеров года к приросту "
                "среднего капитала года, %")
            for w in worlds:
                a_cell, b_cell = cells[w], free.cell(w, regime, scenario)
                row = {}
                for y in PAIR_YEARS:
                    qs = [k for k in tl.quarters_of_year(y) if 1 <= k <= tl.Q]
                    dn = sum(b_cell.quarters["ni_sh"][k] - a_cell.quarters["ni_sh"][k] for k in qs)
                    db = sum(b_cell.quarters["bv"][k] - a_cell.quarters["bv"][k] for k in qs) / len(qs)
                    row[str(y)] = round(dn / db, 6) if abs(db) > 1e-6 else None
                out["pair"][w] = {"d_ni_to_d_bv": row, "cost_of_equity": round(a_cell.k_t, 6),
                                  "value_book": round(a_cell.v_ri, 1), "value_unconstrained": round(b_cell.v_ri, 1)}
                say(f"  {a_cell.label}: " + "; ".join(f"{y}: {'—' if v is None else pc(v)}" for y, v in row.items())
                    + f" | k {pc(a_cell.k_t)} | стоимость клетки, млрд ₽: книга {a_cell.v_ri:.0f}, без ограничения {b_cell.v_ri:.0f}")
    except NeedCore as exc:
        print(f"нужна волна ядра: {exc}")
        return 2
    except Exception as exc:                                    # отказ книги, фактов или входов
        import traceback
        traceback.print_exc()
        print(f"ОТКАЗ: {type(exc).__name__}: {exc}")
        return 1
    if not a.no_write:
        target = a.out or HERE / "out" / "marginal_loan_out.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        target.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
