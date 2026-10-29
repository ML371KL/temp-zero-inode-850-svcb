"""Мутационный набор ядра (М§18): одна ошибка в коде — её обязан уронить
аналитический или инвариантный тест, не регрессия.

Мутация — правка ИСХОДНОГО КОДА копии `model/` (подменой входа можно проверить только,
что параметр читается, а не что он правильно применяется). Проверки ниже — тождества
или закрытые формулы, выведенные из книги и фактов независимо от ядра; регрессии
чисел книги и сверки с контрольной моделью среди них нет.

Механика (перенос 850oa `tests/mutations.py`): каталог `model/` копируется во
временный каталог, в копии правится одна строка, проверки запускаются подпроцессом
с копией первой в `sys.path` (`python -m tests.mutations --check`). Если строку-цель
переписали, мутацию перенацеливают, а не удаляют.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    id: str
    title: str
    path: str                              # путь от корня репозитория
    find: str
    replace: str


MUTATIONS: list[Mutation] = [
    Mutation("M01", "проценты за 0,25 года вместо дней квартала (act/365)", "model/cell.py",
             "dt = d / DAYS_IN_YEAR", "dt = QUARTER_YEARS"),
    Mutation("M02", "корень (1 + r)^0,25 − 1 вместо простого начисления в доходе активов", "model/cell.py",
             "income = sum(rate[b] * avg[b] for b in roles.assets) * dt",
             "income = sum(((1 + rate[b]) ** QUARTER_YEARS - 1) * avg[b] for b in roles.assets)"),
    Mutation("M03", "κ-добавка не относительно мира N", "model/credit.py",
             "out[q] = kappa * max(0.0, real_w[j] - real_n[j])", "out[q] = kappa * max(0.0, real_w[j])"),
    Mutation("M04", "OCI вне совокупного дохода", "model/cell.py",
             "ci = ni_sh - cpn * (1 - tau_s) + oci + om", "ci = ni_sh - cpn * (1 - tau_s) + om"),
    Mutation("M05", "купон AT1 без налогового эффекта", "model/cell.py",
             "ci = ni_sh - cpn * (1 - tau_s) + oci + om", "ci = ni_sh - cpn + oci + om"),
    Mutation("M06", "дивиденд на размещённые акции (с собственными)", "model/dividends.py",
             "ratio = policy.n_out / policy.n_iss", "ratio = 1.0"),
    Mutation("M07", "мост с дисконтом за управление", "model/grid.py",
             "return (core * (1 - governance) + pending + bridge_amount) * THOUSAND / shares_out",
             "return (core + pending + bridge_amount) * (1 - governance) * THOUSAND / shares_out"),
    Mutation("M08", "политика 50 % в терминале вместо капиталонейтральной выплаты", "model/valuation.py",
             "tv_ddm = x_t + (roe_t - g) * bv_star / (k_t - g)", "tv_ddm = x_t + 0.5 * roe_t * bv_star / (k_t - g)"),
    Mutation("M09", "предел сдвига A-P2u не на каждое наблюдение", "model/grid.py",
             "current = cap_shift(current, posterior, limit)", "current = posterior"),
    Mutation("M10", "φ не ноль в мире H (путь ставки клетки)", "model/cell.py",
             's -= phi * (ref - self.wh.ref(spec["ref"])[q])', "s -= phi * ref"),
    Mutation("M11", "φ не ноль в мире H (стационарный ЧПМ)", "model/nii.py",
             'y -= phi * (ref - rh[spec["ref"]])', "y -= phi * ref"),
    Mutation("M12", "мост CoR не применён к путям режимов", "model/credit.py",
             "return bridge.to_engine_cor(value)", "return value"),
    Mutation("M13", "мост CoR применён к путям режимов дважды", "model/credit.py",
             "return bridge.to_engine_cor(value)", "return bridge.to_engine_cor(bridge.to_engine_cor(value))"),
    Mutation("M14", "вычеты капитала без роста с RWA", "model/capital.py",
             "ded20 = c.ded20_0 * rwa / c.rwa0", "ded20 = c.ded20_0"),
    Mutation("M15", "прибыль года вне K11 без календаря аудитов", "model/cell.py",
             "back = after_audit_start(h, p.cap.audit_cutoffs)", "back = h - 1"),
    Mutation("M16", "дивиденд вычтен из регуляторного капитала в квартал ГОСА (без DPreg)", "model/cell.py",
             "dpreg = dpreg_at(reg, q)", "dpreg = 0.0"),
    Mutation("M17", "RI квартала оценки без доли (1 − e)", "model/valuation.py",
             "ri[q0] = (1 - e) * ci[q0] - k0 * bv_v", "ri[q0] = ci[q0] - k0 * bv_v"),
    Mutation("M18", "капитал на дату оценки без дохода прошедшей доли квартала", "model/valuation.py",
             "bv_v = bv[q0 - 1] + e * ci[q0]", "bv_v = bv[q0 - 1]"),
    Mutation("M19", "порядок случайных чисел полосы: по осям (X5), а не по прогонам (850oa)", "model/uncertainty.py",
             "return [[tri_s((perms[j][i] + rng.random()) / n) for j in range(n_axes)] for i in range(n)]",
             "return [list(r) for r in zip(*[[tri_s((perms[j][i] + rng.random()) / n) for i in range(n)] "
             "for j in range(n_axes)])]"),
    Mutation("M20", "тип квантилей не 7", "model/uncertainty.py", "h = (n - 1) * q", "h = n * q - 0.5"),
    Mutation("M21", "конец квартала — не конец дня (правило только для якоря)", "model/timeline.py",
             "if d == self.end(q):", "if d == self.end(0):"),
    Mutation("M22", "σ0 с первого прогнозного квартала, без nii.sigma0_from", "model/nii.py",
             "row.append(t.value(y, h) + (shift if y >= from_year else 0.0))", "row.append(t.value(y, h) + shift)"),
    Mutation("M23", "ε без линейного ввода за ramp_years", "model/dividends.py",
             "return self.epsilon * min(1.0, (year - self.excess_from + 1) / self.ramp_years)",
             "return self.epsilon"),
    Mutation("M24", "«прочее» без квартального профиля", "model/cell.py",
             "misc = p.misc_q[(year, h)] * idx", "misc = p.misc_q[(year, 1)] * idx"),
    Mutation("M25", "ожидание режима A-P2u — только мир N, не слой «свой взгляд»", "model/grid.py",
             'world_w = {w: float(book.get(f"joint.world_prob.{w}")) for w in book.get("worlds.ids")}',
             "world_w = {BASE_WORLD: 1.0}"),
    # --- волна W2 (аудит после W1; М§18, строка «Мутации»)
    Mutation("M26", "вычеты Ded11 без роста с RWA", "model/capital.py",
             "ded11 = c.ded11_0 * rwa / c.rwa0", "ded11 = c.ded11_0"),
    Mutation("M27", "терминал без вычета дохода на избыток", "model/valuation.py",
             "ni_t1 = (pbt_last_year * (1 + g) - y_x) * (1 - tau_eff) * (1 - nci_share)",
             "ni_t1 = pbt_last_year * (1 + g) * (1 - tau_eff) * (1 - nci_share)"),
    Mutation("M28", "доход на избыток по одной ставке ликвидности (без бумаг)", "model/cell.py",
             'y_bal = p.sec_share * last["_rate"][SECURITIES] + (1 - p.sec_share) * last["_rate"][LIQUIDITY]',
             'y_bal = last["_rate"][LIQUIDITY]'),
    Mutation("M29", "избыток сверх запаса ликвидности — не по ставке опта", "model/valuation.py",
             "return y_balancing * within + c_wholesale * (x_t - within)", "return y_balancing * x_t"),
    Mutation("M30", "взносы АСВ выключены", "model/cell.py", "dia = p.dia * fr_avg * dt", "dia = 0.0"),
    Mutation("M31", "κ-добавка без лага", "model/credit.py", "j = q - lag", "j = q"),
    Mutation("M32", "κ-добавка не в CoR", "model/cell.py",
             "self.cor = tuple(self.rg.cor_engine[q] + kap[q] + self.d_cor[q] for q in range(Q + 1))",
             "self.cor = tuple(self.rg.cor_engine[q] + self.d_cor[q] for q in range(Q + 1))"),
    Mutation("M33", "Δy первого квартала — от пути мира, а не от кривой якоря", "model/cell.py",
             "dy = tenor[q] - (tenor[q - 1] if q > 1 else p.y_tenor0)", "dy = tenor[q] - tenor[q - 1]"),
    Mutation("M34", "минимум ликвидности — к небалансирующим активам, а не ко всем", "model/cell.py",
             "la_min = p.liquid_min * nonbal_assets / (1 - p.liquid_min)", "la_min = p.liquid_min * nonbal_assets"),
    Mutation("M35", "FVC — на весь CoR, без опоры (двойной счёт уровня, уже лежащего в «прочем»)", "model/credit.py",
             "return factor * (cor_corporate - cor_ref) * fv_avg * dt", "return factor * cor_corporate * fv_avg * dt"),
    Mutation("M36", "опора FVC — режим клетки, а не credit.fv_loans_ref", "model/cell.py",
             "self.cor_ref = p.fv_ref_cor", "self.cor_ref = self.rg.cor_engine"),
    Mutation("M37", "«прочее» года якоря — остатком года (без вычитания факта ось не работает)", "model/cell.py",
             "    if rest_qs:             # остатком года закрывается только непрофильный результат (М§0.3)\n",
             "    if rest_qs:\n        for h in (1, 2, 3, 4):\n            misc_q[(ay, h)] = (misc_tab[ay] - "
             "need_hist(\"misc\", fact_qs)) / len(rest_qs)\n"),
    Mutation("M38", "объявленный, ещё не вычтенный дивиденд — под дисконтом за управление", "model/grid.py",
             'pending = sum(r["amount"] for r in brows if r["pending"])', "pending = 0.0"),
    Mutation("M39", "перекат pos(v) — по началу дня", "model/timeline.py",
             "roll = QUARTER_YEARS * (((q0 - 1) + e) - timeline.pos(curve))",
             "roll = QUARTER_YEARS * ((timeline.q_of_date(v) - 1 + (v - timeline.start(timeline.q_of_date(v))).days "
             "/ timeline.d(timeline.q_of_date(v))) - timeline.pos(curve))"),
    Mutation("M40", "фильтр A-P2u читает все наблюдения, без окна", "model/grid.py",
             "return _observations(book, bridge, timeline)[-n:]", "return _observations(book, bridge, timeline)"),
    Mutation("M41", "наблюдение не позже якоря — без замороженных ожиданий (μ = 0)", "model/grid.py",
             "dev = value - (frozen[r] if frozen is not None else mu[x][r][q])",
             "dev = value - (0.0 if frozen is not None else mu[x][r][q])"),
    Mutation("M42", "отмена дивиденда кризисом записана как урезание капиталом", "model/dividends.py",
             'deferred_after=deferred + want[0], source="crisis_skip", cut=False,',
             'deferred_after=deferred + want[0], source="crisis_skip", cut=True,'),
    Mutation("M43", "σ0 пассивов — с тем же знаком, что у активов", "model/nii.py",
             'sigma = sigma0 if spec["side"] == "asset" else -sigma0_liab',
             'sigma = sigma0 if spec["side"] == "asset" else sigma0_liab'),
    Mutation("M44", "σ0 пассивов не входит в стационарный ЧПМ", "model/nii.py",
             'sl = {b: (sigma0_liab if books[b].get("lt_shift") else 0.0) for b in self.roles.liabilities}',
             "sl = {b: 0.0 for b in self.roles.liabilities}"),
    Mutation("M45", "доля сдвига σ0 на активах не читается (всё на активах)", "model/nii.py",
             "s_a = split * delta / lt_weight if split > 0 else 0.0", "s_a = delta / lt_weight"),
    Mutation("M46", "эффективный LT-спред без сжатия φ", "model/nii.py",
             's -= phi_assets * (rates[spec["ref"]] - self.ref_lt[ref_world][spec["ref"]])', "s -= 0.0"),
    Mutation("M47", "край отрезка поиска нейтрального значения в допуске не принимается", "model/nextreport.py",
             "if abs(fe) <= tol:                       # край с невязкой в допуске — корень (ноль — с любой стороны)",
             "if False:"),
    Mutation("M48", "допуск точечного гайденса — вдесятеро шире", "model/checks.py",
             "return (v - float(tol), v + float(tol))", "return (v - 10 * float(tol), v + 10 * float(tol))"),
    Mutation("M49", "сдвиг положения оси — без точки (не от книги)", "model/uncertainty.py",
             "return (price_high + price_low - 2 * point) / MEAN_SHIFT_DIVISOR",
             "return (price_high + price_low) / MEAN_SHIFT_DIVISOR"),
    Mutation("M50", "год шока кризиса — год якоря (сдвиг не прибавлен)", "model/cell.py",
             "shock_year=None if offset is None else ay + int(offset),", "shock_year=None if offset is None else ay,"),
    # --- волна W3 (второй аудит, LEAD-DECISIONS-4; М§18, строка «Мутации»)
    Mutation("M51", "угасание симметричное (множитель действует и при ROE_T < k_T)", "model/valuation.py",
             "roe_t = k_t + fade * max(excess, 0.0) + min(excess, 0.0)", "roe_t = k_t + fade * excess"),
    Mutation("M52", "опора FVC сдвигается вместе с осью уровня CoR", "model/cell.py",
             "ref_book = book if book.base is None else book.base", "ref_book = book"),
    Mutation("M53", "пол вероятности режима не применён", "model/grid.py",
             "current = floor_shift(prior, current, floor)", "current = dict(current)"),
    Mutation("M54", "остаток сжатия φ не доходит до стоимости пассивов", "model/cell.py",
             "s += phi_l * self.x_w[q]", "s += 0.0"),
    Mutation("M55", "порог ликвидности терминала — HLA вместо HLA / (1 − доля)", "model/valuation.py",
             "limit = headroom / (1 - min_share)", "limit = headroom"),
    Mutation("M56", "добавка пассивов φ_L без отношения весов A / L", "model/nii.py",
             "phi_l = (1 - p_split) * phi * a_phi / l_phi if p_split < 1 else 0.0",
             "phi_l = (1 - p_split) * phi if p_split < 1 else 0.0"),
    Mutation("M57", "доля сжатия φ на активах не читается (всё на активах)", "model/nii.py",
             "phi_a = p_split * phi", "phi_a = phi"),
    Mutation("M58", "год с отчётными кварталами — средним мостом, без упр. факта", "model/grid.py",
             "    if all(q >= 1 for q in qs):\n        to_mgmt =", "    if True:\n        to_mgmt ="),
    Mutation("M59", "сторож заголовка: дивиденд без записи реестра не входит в сумму", "model/grid.py",
             'total += sum(prob[c.key] * float(c.quarters["div"][q] or 0.0) for c in cells)', "total += 0.0"),
    Mutation("M60", "недостаток капитала терминала не гасит добор опта", "model/valuation.py",
             "repaid = min(-x_t, wholesale_extra)", "repaid = 0.0"),
    Mutation("M61", "оценщик сдвига медианы — среднее по всей выборке, без окна рангов", "model/uncertainty.py",
             "chosen = [i for i in range(n) if lo <= (rk[i] - 1) / (n - 1) <= hi]", "chosen = list(range(n))"),
    Mutation("M62", "нейтральное значение «прилипает» к строке таблицы при смене знака", "model/nextreport.py",
             "    if cross is None:\n        near =", "    if True:\n        near ="),
    Mutation("M63", "квартал открытого нау-каста — прогнозом, а не отклонением от своего ожидания", "model/payload.py",
             'ni_q = x.E(x.p_mix, "ni_sh", qs) + deviation', 'ni_q = t1.get("forecast") if t1.get("forecast") is not None else e["ni"]'),
    # --- волна перед первым push (решения ведущего P4; М§18, строка «Мутации»)
    Mutation("M64", "уточнение корня обратного расчёта не делает шаг секущей (остаётся решение подвыборки)",
             "model/reverse.py", "            break\n        x = estimate", "            break\n        break"),
    Mutation("M65", "«в диапазоне книги» — о приближении, а не о корне", "model/reverse.py",
             "    return low <= estimate <= high", "    return True"),
    Mutation("M66", "нейтральное значение точки «прилипает» к строке таблицы при смене знака", "model/nextreport.py",
             "        root, _ = _refine(_Gap(pg), a, fa, b, fb, c, fc, POINT_STEPS, tol, value_tol)",
             "        root, _ = bisect_point(pg, a, b, tol=tol)"),
    Mutation("M67", "гейт пола спреда не смотрит на концы осей долей", "model/checks.py",
             "    corners = share_axis_ends(book)", "    corners = []"),
    # --- правки по внешнему аудиту 02.10.2026 (DECISIONS часть 12; М§18, строка «Мутации»)
    Mutation("M68", "убыток неаудированного периода возвращён в базовый капитал", "model/capital.py",
             "k11 = bvreg - max(unaudited, 0.0) - ded11", "k11 = bvreg - unaudited - ded11"),
    Mutation("M69", "N11* возвращает в базовый капитал и убыток периода", "model/capital.py",
             "return (k11 + max(unaudited, 0.0)) / rwa + gap11 - ded_pp11",
             "return (k11 + unaudited) / rwa + gap11 - ded_pp11"),
    Mutation("M70", "граница дивиденда — с добавкой догоняющей выплаты и избытка (проверка ничего не ловит)",
             "model/checks.py", "if d.div > max(0.0, h) + REL_TOL * max(1.0, abs(d.div)):",
             "if d.div > max(0.0, h) + d.catch + d.excess + REL_TOL * max(1.0, abs(d.div)):"),
    Mutation("M71", "инвариант вероятностей не видит отрицательного веса", "model/checks.py",
             "        if min(values) < 0:\n            negative.append(name)", "        pass"),
    Mutation("M72", "схема книги не ограничивает вероятности и доли отрезком [0; 1]", "model/book_schema.py",
             "    if is_number(value) and not 0 <= float(value) <= 1:\n        return [f\"{path} = {value}: {what} — от 0 до 1\"]",
             "    if False:\n        return []"),
    # --- литералы эмитента из книги и схема второй формы банка (М§0.6, прил. A)
    Mutation("M73", "имя схемы выпуска — константа кода, а не ключ книги", "model/payload.py",
             '    return str(book.get("meta.schema"))', '    return "fixed-v1"'),
    Mutation("M74", "подпись книги ЧПД в сообщении гейта — строчными целиком (аббревиатура теряет регистр)",
             "model/checks.py", "lower_first(book.book_name(b))", "book.book_name(b).lower()"),
    Mutation("M75", "гейт гайденса сравнивает все узлы перечня, не глядя на `gate`", "model/checks.py",
             '    items = [it for it in ctx.book.get("checks.guidance_items") if it.get("gate")]',
             '    items = [it for it in ctx.book.get("checks.guidance_items") if it.get("words")]'),
    Mutation("M76", "включённая нереализованная ветвь принимается молча", "model/book_schema.py",
             "    if not pending_ok:\n        errors.extend(pending(data))",
             "    if False:\n        errors.extend(pending(data))"),
    Mutation("M77", "незнакомое поле подстановки подписи не ловится", "model/book_schema.py",
             "        unknown = sorted({name for name, _, _ in parts} - self.fields)", "        unknown = []"),
    Mutation("M78", "значение в ключе неактивного режима календаря принимается", "model/book_schema.py",
             "        if _get(data, path) is not None:\n            out.append(f\"{path}: ключ неактивного режима",
             "        if False:\n            out.append(f\"{path}: ключ неактивного режима"),
    Mutation("M79", "слова периода записи реестра — всегда годовые", "model/book.py",
             '        return book.label(f"periods.{int(m.group(2))}", year=int(m.group(1)))',
             '        return book.label("periods.4", year=year)'),
    Mutation("M80", "название норматива в подписи коридора — литерал кода", "model/payload.py",
             'n20_short=book.label("capital.n20_short"),', 'n20_short="норматив",'),
    Mutation("M81", "делитель «размещённые» принят при двух тикерах", "model/book_schema.py",
             '    if _get(data, "valuation.shares_basis") == "issued" and len(ids.get("<t>", ())) > 1:', "    if False:"),
    Mutation("M82", "рост по капиталу принят без квартального календаря", "model/book_schema.py",
             '        if not quarterly:\n            out.append("capital.growth_constraint.enabled:',
             '        if False:\n            out.append("capital.growth_constraint.enabled:'),
    # --- вторая форма банка, волна 1 (М§8.4, §4.3, §4.7, §4.11, §5.2, §14.2): проверки — на фикстуре `core_t`
    Mutation("M83", "мост считает запись реестра на делитель вместо акций в обращении", "model/grid.py",
             "        amount = rec.dps * af.n_out / THOUSAND",
             "        amount = rec.dps * divisor(book, ctx.facts, af) / THOUSAND"),
    Mutation("M84", "делитель книги не доходит до цены", "model/grid.py",
             "    n_div = divisor(book, ctx.facts, af)", "    n_div = af.n_out"),
    Mutation("M85", "экономически собственные акции не вычитаются из делителя", "model/grid.py",
             "        base = af.n_iss - held", "        base = af.n_iss"),
    Mutation("M86", "поправка делителя не применяется", "model/grid.py",
             "    n_div = base if adj is None else base * (1 + float(adj))", "    n_div = base"),
    Mutation("M87", "капитализация при делителе «размещённые» — по акциям в обращении", "model/grid.py",
             '    if run.ctx.book.opt("valuation.shares_basis") == SHARES_ISSUED:', "    if False:"),
    Mutation("M88", "тест истории вида cap не видит превышения потолка", "model/dividends.py",
             '"ok": pool <= cap * ni + CAP_TOL if complete else None})', '"ok": True if complete else None})'),
    Mutation("M89", "вид теста истории выплат не читается из книги (всегда формула «до копейки»)", "model/dividends.py",
             '    return str(book.opt("dividends.policy.history_test", HISTORY_EXACT))', "    return HISTORY_EXACT"),
    Mutation("M90", "гейт потолка сравнивает с потолком уменьшение BV, а не сумму на все размещённые акции",
             "model/checks.py", "    gross = af.n_iss / af.n_out ", "    gross = 1.0 "),
    Mutation("M91", "связь комиссий с объёмом не читается", "model/cell.py",
             "                g_fees += p.link_fees * v_ex", "                g_fees += 0.0"),
    Mutation("M92", "связь расходов — суммой с реальным ростом, а не произведением", "model/cell.py",
             'opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex) * (1 + p.opex_real[q])',
             'opex = flows["opex"][q - 4] * (1 + wage + p.link_opex * v_ex + p.opex_real[q])'),
    Mutation("M93", "рост объёма — по остатку на конец квартала, а не по среднему остатку", "model/cell.py",
             "                vol = (sum(E0[b] for b in roles.loans) + loans) / 2", "                vol = loans"),
    Mutation("M94", "связь комиссий применяется и в году fees.growth_override", "model/cell.py",
             "            if gvw is None and p.link_fees:", "            if p.link_fees:"),
    Mutation("M95", "связь страхования с объёмом не читается", "model/cell.py",
             'ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q] + p.link_ins * v_ex)',
             'ins = flows["ins"][q - 4] * (1 + wage + p.ins_gvw[q])'),
    Mutation("M96", "премия роста кредитов — одна на все книги (сектор книги не читается)", "model/cell.py",
             "            d = p.loan_drift[sector][year] if year <= p.drift_until else 0.0",
             '            d = p.loan_drift["corporate"][year] if year <= p.drift_until else 0.0'),
    Mutation("M97", "премия роста средств клиентов по сегментам не читается", "model/cell.py",
             "            d = p.funds_drift[sector][year] if year <= p.drift_until else 0.0", "            d = 0.0"),
    Mutation("M98", "отношение прочих активов к кредитам — без вычета постоянной части (она растёт с кредитами)",
             "model/book.py", "(af.other_assets - oa_fixed) / loans_total if oa_fixed else af.other_assets / loans_total",
             "af.other_assets / loans_total"),
    Mutation("M99", "постоянная часть прочих активов не входит в баланс клетки", "model/cell.py",
             "            OA += p.oa_fixed ", "            OA += 0.0 "),
    Mutation("M100", "плотность постоянных прочих активов — как у растущих", "model/capital.py",
             "            base += self.other_assets * (other_assets - self.oa_fixed) + self.other_assets_fixed * self.oa_fixed",
             "            base += self.other_assets * other_assets"),
    Mutation("M101", "множитель RWA режима не читается", "model/cell.py",
             "            rwa *= self.rg.rwa_mult[q] ", "            rwa *= 1.0 "),
    Mutation("M102", "узел роста прибыли гайденса — уровень к базе, а не рост", "model/checks.py",
             'out["op_np_growth"] = None if ni is None else ni / bases["op_np_growth"] - 1',
             'out["op_np_growth"] = None if ni is None else ni / bases["op_np_growth"]'),
    Mutation("M103", "база роста дивиденда — последняя строка истории, а не сумма года", "model/checks.py",
             '        out["dps_growth"] = sum(dps)', '        out["dps_growth"] = dps[-1]'),
    Mutation("M104", "признак оценки норматива якоря не читается", "model/book.py",
             '    return isinstance(node, Mapping) and node.get("estimated") is True', "    return False"),
    Mutation("M105", "просрочка события-оценки меряется от даты составителя, а не от latest", "model/checks.py",
             '    raw = event.get("latest") if event.get("estimated") is True else event.get("date")',
             '    raw = event.get("date")'),
    Mutation("M106", "контракт выпуска сверяет формулу цены на акциях в обращении", "model/payload.py",
             '    n_div = shares.get("divisor_mln", shares["outstanding_mln"]) ', '    n_div = shares["outstanding_mln"] '),
    Mutation("M107", "капитал на акцию в выпуске — на акции в обращении", "model/payload.py",
             '"bv_per_share": R_PRICE(x.bl["bv_v"] * 1000 / x.n_div)', '"bv_per_share": R_PRICE(x.bl["bv_v"] * 1000 / x.n_out)'),
    Mutation("M108", "сторож заголовка: экс-даты на акцию — без пересчёта на делитель", "model/payload.py",
             "    adj_ps = adj * x.per_div ", "    adj_ps = adj "),
    Mutation("M109", "контракт требует формулу «до копейки» при любом виде теста истории", "model/payload.py",
             "    if kind == HISTORY_EXACT:                  # формула", "    if True:                  # формула"),
    Mutation("M110", "ROE эмитента — к капиталу на конец квартала якоря, а не к среднему пяти концов", "model/payload.py",
             '"value": R_SHARE(sum(profit) / (sum(equity) / len(equity)))', '"value": R_SHARE(sum(profit) / equity[0])'),
    Mutation("M111", "флаг объявленной сделки поднимается и для сделки, уже учтённой книгой", "model/payload.py",
             '    deals = [e for e in events if e.get("kind") == "deal" and e.get("in_book") is False]',
             '    deals = [e for e in events if e.get("kind") == "deal"]'),
    # --- вторая форма банка, волна 2: квартальный календарь дивидендов (М§5.7, §7, §8.1, §14–§15); проверки — на `core_t`
    Mutation("M112", "режим календаря дивидендов не читается (решение раз в год)", "model/dividends.py",
             "    if not is_quarterly(book):\n        return None", "    if True:\n        return None"),
    Mutation("M113", "карта лагов: один лаг решения на все кварталы прибыли года", "model/dividends.py",
             "        return idx + self.lags[h - 1]", "        return idx + self.lags[0]"),
    Mutation("M114", "лаг вычета из регуляторного капитала не читается (вычет в квартале решения)", "model/dividends.py",
             "        return max(self.q_dec(idx, h), idx + self.reg_lag)", "        return self.q_dec(idx, h)"),
    Mutation("M115", "лаг выплаты не читается (выплата в квартале решения)", "model/dividends.py",
             "        return max(self.q_dec(idx, h), idx + self.pay_lag)", "        return self.q_dec(idx, h)"),
    Mutation("M116", "квартал решения только по карте: решение «до якоря» по карте не вычитается из BV никогда",
             "model/dividends.py", "q, q_reg, q_pay, dps = max(1, rule.q_dec(idx, h)),", "q, q_reg, q_pay, dps = rule.q_dec(idx, h),"),
    Mutation("M117", "квартал прибыли закрывает любая строка истории, а не решение не позже даты фактов",
             "model/dividends.py", "        if day <= facts_date and (last is None or idx > last):",
             "        if last is None or idx > last:"),
    Mutation("M118", "база дивиденда — прибыль одного квартала при окне больше единицы", "model/cell.py",
             "        window = range(idx - pol.window + 1, idx + 1)", "        window = range(idx, idx + 1)"),
    Mutation("M119", "квартальное решение берёт прибыль с начала года, а не окна", "model/cell.py",
             "        window = range(idx - pol.window + 1, idx + 1)", "        window = range(idx - tl.h(idx) + 1, idx + 1)"),
    Mutation("M120", "избыток капитала платится в каждом квартале, а не раз в год", "model/dividends.py",
             "    annual = [i for i in live if due[i].h == LAST_QUARTER]", "    annual = list(live)"),
    Mutation("M121", "год шока не отменяет квартальные решения", "model/cell.py",
             "            shock = shock_year is not None and self.years[q] == shock_year", "            shock = False"),
    Mutation("M122", "год шока отменяет решения следующего года, а не принимаемые в нём", "model/cell.py",
             "            shock = shock_year is not None and self.years[q] == shock_year",
             "            shock = shock_year is not None and self.years[q] == shock_year + 1"),
    Mutation("M123", "две записи одного года схлопнуты: ключ записи — год прибыли", "model/dividends.py",
             "    return str(rec.period) if quarterly else int(rec.year)", "    return int(rec.year)"),
    Mutation("M124", "живой реестр сливает записи одного года при квартальном календаре", "model/live.py",
             '    return str(r["period"]) if quarterly and r.get("period") else int(r["year"])', '    return int(r["year"])'),
    Mutation("M125", "мост датирует вычет записи кварталом позже квартала решения", "model/grid.py",
             "        return tl.end(slot.q)", "        return tl.end(slot.q + 1)"),
    Mutation("M126", "мост: вычет записи закрытого квартала прибыли — по карте, а не с даты фактов", "model/grid.py",
             "    if cal.closed(idx):", "    if False:"),
    Mutation("M127", "запись реестра не заменяет дивиденд модели своего квартала", "model/dividends.py",
             "            dps = float(rec.dps)", "            dps = None"),
    Mutation("M128", "дивиденд записи реестра — на размещённые акции", "model/dividends.py",
             "            div = o.dps * n_c / THOUSAND", "            div = o.dps * policy.n_iss / THOUSAND"),
    Mutation("M129", "пул квартала уменьшает BV целиком (с частью на собственные акции)", "model/dividends.py",
             "    out_share = n_c / policy.n_iss ", "    out_share = 1.0 "),
    Mutation("M130", "отмена квартального решения кризисом записана как урезание капиталом", "model/dividends.py",
             'source="crisis_skip", cut=False, flags=("crisis_skip",), **common))',
             'source="crisis_skip", cut=True, flags=("crisis_skip",), **common))'),
    Mutation("M131", "сторож заголовка: дивиденд без записи реестра не входит в сумму (квартальный календарь)",
             "model/grid.py", 'total += sum(prob[c.key] * float(c.quarters["div_model"][q] or 0.0) for c in cells)',
             "total += 0.0"),
    Mutation("M132", "дивиденд без записи реестра считает и дивиденды записей", "model/grid.py",
             'total += sum(prob[c.key] * float(c.quarters["div_model"][q] or 0.0) for c in cells)',
             'total += sum(prob[c.key] * float(c.quarters["div"][q] or 0.0) for c in cells)'),
    Mutation("M133", "граница дивиденда квартала — с добавкой догоняющей выплаты и избытка (проверка ничего не ловит)",
             "model/checks.py", "        if base > max(0.0, ref) + tol or paid > max(0.0, ref, final) + tol:",
             "        if paid > max(0.0, ref, final) + sum(d.catch + d.excess + d.base_div for d in decs) + tol:"),
    Mutation("M134", "запас квартала меряется без записей реестра этого квартала", "model/cell.py",
             "        row = self.probe(st, q, reg_parts)", "        row = self.probe(st, q, ())"),
    Mutation("M135", "базовый дивиденд квартала не ограничен запасом", "model/dividends.py",
             "    div_base = min(total, max(0.0, headroom)) if live else 0.0", "    div_base = total if live else 0.0"),
    Mutation("M136", "терминал раздаёт как избыток дивиденды, ещё стоящие в регуляторном капитале", "model/cell.py",
             '    if last["dpreg"]:', "    if False:"),
    Mutation("M137", "постоянная часть дивидендов к выплате якоря выплачивается", "model/cell.py",
             "        for pq, rq, amount in p.calendar.payable:",
             "        for pq, rq, amount in p.calendar.payable + ((1, 0, af.dividends_payable - sum(a for _, _, a in "
             "p.calendar.payable)),):"),
    Mutation("M138", "объявленная часть дивидендов к выплате якоря не стоит в регуляторном капитале до вычета",
             "model/cell.py", "            if rq >= 1:\n                s.reg.append((0, rq, amount))",
             "            if False:\n                s.reg.append((0, rq, amount))"),
    Mutation("M139", "решение квартала вычтено из регуляторного капитала сразу (без очереди вычетов)", "model/cell.py",
             "            reg = reg + [(q, part_reg, a) for a, _, part_reg in parts if a]",
             "            reg = reg + [(q, q, a) for a, _, part_reg in parts if a]"),
    Mutation("M140", "решение квартала выплачено в квартале решения, а в квартал выплаты — ещё раз", "model/cell.py",
             "            pay += sum(a for a, part_pay, _ in parts if part_pay == q)",
             "            pay += sum(a for a, part_pay, _ in parts)"),
    Mutation("M141", "DPS года — без строк истории закрытых кварталов прибыли", "model/cell.py",
             "        dps = {y: cal.closed_dps[y] + sum(dps_q[per] for per in cal.year_periods[y]) for y in cal.years}",
             "        dps = {y: sum(dps_q[per] for per in cal.year_periods[y]) for y in cal.years}"),
    Mutation("M142", "флаг реестра: срок решения — следующий квартал, карта лагов не читается", "model/live.py",
             "            q = max(1, rule.q_dec(idx, tl.h(idx)))", "            q = max(1, idx + 1)"),
    Mutation("M143", "объявленная запись без квартала прибыли принимается при квартальном календаре", "model/live.py",
             '            if not period:\n                why = "нет квартала прибыли"',
             '            if False:\n                why = "нет квартала прибыли"'),
    Mutation("M144", "запись за открытый квартал с решением раньше даты фактов принимается", "model/live.py",
             "            elif (decided is not None and facts_date is not None and decided <= facts_date",
             "            elif (False and decided is not None and facts_date is not None and decided <= facts_date"),
    Mutation("M145", "гейт ручного входа не читает событие решения о дивиденде", "model/checks.py",
             "        elif (kind == DECISION_EVENT and cal is not None and covers and str(covers) not in periods",
             "        elif (False and kind == DECISION_EVENT and cal is not None and covers and str(covers) not in periods"),
    Mutation("M146", "гейт потолка не считает строки истории закрытых кварталов года", "model/checks.py",
             "                paid += closed[year]", "                paid += 0.0"),
    Mutation("M147", "контракт сверяет ближайшую выплату с записью года, а не периода", "model/payload.py",
             '        key = "period" if ne.get("period") is not None else "year" ', '        key = "year" '),
    Mutation("M148", "записи одного года прибыли в выпуске сворачиваются в одну (ключ — год)", "model/payload.py",
             '    return r.get("period") or int(r["year"])', '    return int(r["year"])'),
    Mutation("M149", "ближайшая выплата без записи — квартал, срок решения которого уже прошёл", "model/payload.py",
             "        slot = next((o for o in cal.open if o.dps is None and o.q >= q0), None)",
             "        slot = next((o for o in cal.open if o.dps is None), None)"),
    Mutation("M150", "выплата отчётных кварталов года — пулом на размещённые акции, а не оттоком", "model/payload.py",
             "                total += float(pool) * x.n_out / x.n_iss", "                total += float(pool)"),
    Mutation("M151", "нау-каст года: отклонение открытого квартала входит в DPS без окна базы", "model/payload.py",
             "        shift = deviation * hit / window", "        shift = deviation"),
    Mutation("M152", "строка лестницы с порогом 0 печатается", "model/payload.py",
             '        if not s["threshold"] > 0:\n            continue', '        if False:\n            continue'),
    Mutation("M153", "год истории без решения за четвёртый квартал прибыли печатает DPS", "model/payload.py",
             "            dps_year = sum(parts) if done and None not in parts else None",
             "            dps_year = sum(parts) if None not in parts else None"),
    Mutation("M154", "форвардная дивидендная доходность — одна квартальная выплата", "model/payload.py",
             "    for idx in range(first, first + 4):", "    for idx in range(first, first + 1):"),
    Mutation("M155", "годовой путь: «объявлен» — при записи хотя бы за один квартал года", "model/payload.py",
             '"declared": all(cal.periods[per].dps is not None for per in cal.year_periods[y])',
             '"declared": any(cal.periods[per].dps is not None for per in cal.year_periods[y])'),
    # --- вторая форма банка, волна 3: рост, ограниченный капиталом (М§4.13, §10, §11.3, §14.2, §14.5); проверки — на `core_t`
    Mutation("M156", "доля прироста λ применяется только к одной кредитной книге", "model/cell.py",
             "E[b] = E0[b] * fac[b] if lam == 1.0 or fac[b] <= 1.0 else E0[b] * (1 + lam * (fac[b] - 1))",
             "E[b] = E0[b] * fac[b] if lam == 1.0 or fac[b] <= 1.0 or b != roles.loans[0] else E0[b] * (1 + lam * (fac[b] - 1))"),
    Mutation("M157", "требование ограничения роста — без глиссады", "model/cell.py",
             "self.req20g, self.req11g = p.glide[scenario] if p.growth is not None else (self.sc.req20, self.sc.req11)",
             "self.req20g, self.req11g = self.sc.req20, self.sc.req11"),
    Mutation("M158", "глиссада видит только ступень следующего квартала", "model/capital.py",
             "for h in range(lookahead + 1)) for q in range(last + 1))",
             "for h in range(min(lookahead, 1) + 1)) for q in range(last + 1))"),
    Mutation("M159", "глиссада без набора δ за квартал: ступень требуется сразу на весь горизонт", "model/capital.py",
             "return tuple(max(req[min(q + h, last)] - h * glide for h in",
             "return tuple(max(req[min(q + h, last)] for h in"),
    Mutation("M160", "в запасе ограничения роста — отчётный Н20.1 вместо Н20.1 с прибылью периода", "model/cell.py",
             'return (row["n20"] - self.req20g[q]) * rwa, (row["n11_star"] - self.req11g[q]) * rwa',
             'return (row["n20"] - self.req20g[q]) * rwa, (row["n11"] - self.req11g[q]) * rwa'),
    Mutation("M161", "проверочная оценка сверяет отчётный Н20.1, а не Н20.1 с прибылью периода", "model/cell.py",
             'gaps = (row["n20"] - self.req20g[q], row["n11_star"] - self.req11g[q])',
             'gaps = (row["n20"] - self.req20g[q], row["n11"] - self.req11g[q])'),
    Mutation("M162", "навёрстывание роста — после выплаты избытка: избыток считается от запаса до навёрстывания",
             "model/cell.py", "            h_fin = min(self.room(plain[0], q))", "            h_fin = min(h_full)"),
    Mutation("M163", "навёрстывание не ограничено капиталом (доля θ всегда единица)", "model/cell.py",
             "                if min(g_more) >= 0:", "                if True:"),
    Mutation("M164", "навёрстывание — весь разрыв за квартал: скорость catch_up_rate не читается", "model/cell.py",
             "want = {b: gr.catch_up * QUARTER_YEARS * (star[b] - st.E[b]) * fac[b] for b in p.roles.loans",
             "want = {b: (star[b] - st.E[b]) * fac[b] for b in p.roles.loans"),
    Mutation("M165", "при dividend_first запас под дивиденд меряется при полном росте", "model/cell.py",
             "        if modelled and gr.dividend_first and can_cut:", "        if False:"),
    Mutation("M166", "при growth_first запас под дивиденд меряется при наименьшем росте", "model/cell.py",
             "        if modelled and gr.dividend_first and can_cut:", "        if modelled and can_cut:"),
    Mutation("M167", "дивиденд с более поздним вычетом из регуляторного капитала входит в условие роста квартала",
             "model/cell.py", 'if d.source == "model" and o.q_reg == q)', 'if d.source == "model")'),
    Mutation("M168", "при урезанном росте избыток выплачивается (остаток в пределах допуска — «избыток»)",
             "model/cell.py", "deferred=st.D, shock=in_shock, growth_cut=lam < 1.0, n_out=n_out)",
             "deferred=st.D, shock=in_shock, growth_cut=False, n_out=n_out)"),
    Mutation("M169", "потенциальный путь идёт за фактическим: навёрстывать нечего", "model/cell.py",
             "            star = {b: star[b] * fac[b] for b in loans}", "            star = {b: st.E[b] for b in loans}"),
    Mutation("M170", "доля урезанного роста — к фактическому портфелю, а не к потенциальному", "model/cell.py",
             '        out["cut_share"].append(1 - loans[end] / potential[end])',
             '        out["cut_share"].append(potential[end] / loans[end] - 1)'),
    Mutation("M171", "флаг клетки growth_cut не поднимается", "model/cell.py",
             '    if any(r["lam"] < 1 - LAM_TOL for r in rows):', "    if False:"),
    Mutation("M172", "год шока не отменяет решения модели при ограничении роста", "model/cell.py",
             "        in_shock = self.rg.shock_year == self.years[q] ", "        in_shock = False "),
    Mutation("M173", "закрытая формула доли прироста: наклон — по невязке полного роста", "model/cell.py",
             "    return lam_min + (1 - lam_min) * g_min / (g_min - g_full)",
             "    return lam_min + (1 - lam_min) * g_min / (-g_full)"),
    Mutation("M174", "шаг секущей не делается: отклонение больше допуска принимается", "model/cell.py",
             "                if g_end * r < 0:", "                if False:"),
    Mutation("M175", "гейт урезания роста смотрит долю последнего года, а не наибольшую", "model/checks.py",
             '        top = max(((v, y) for v, y in zip(c.growth["cut_share"], c.years) if v is not None), default=None)',
             '        top = next(((v, y) for v, y in reversed(list(zip(c.growth["cut_share"], c.years))) if v is not None), None)'),
    Mutation("M176", "гейт ступени смотрит только решения самого квартала ступени", "model/checks.py",
             "any(abs(d.q - s) <= 1 for s in steps)]", "any(d.q == s for s in steps)]"),
    Mutation("M177", "гейт ступени судит и клетки режима с годом шока", "model/checks.py",
             "        if prep.regimes[c.regime].shock_year is not None:\n            continue",
             "        if False:\n            continue"),
    Mutation("M178", "гейт ступени: падение доли прироста не читается", "model/checks.py",
             "                                        if s >= 2 and lam[s] < lam[s - 1] - float(drop)]",
             "                                        if False]"),
    Mutation("M179", "гейт долгосрочного C/I — в базисе движка, без моста", "model/levels.py",
             '    of_cell = [year_mgmt(ctx, "cir", y, c.annual["cir"][i], row) for i, y in enumerate(c.years) if y >= first]',
             '    of_cell = [c.annual["cir"][i] for i, y in enumerate(c.years) if y >= first]'),
    Mutation("M180", "доля оптового фондирования — к средствам клиентов без опта", "model/checks.py",
             '/ (client_funds_end(ctx, c, q) + c.quarters["wholesale"][q]) for q in ends]',
             '/ client_funds_end(ctx, c, q) for q in ends]'),
    Mutation("M181", "сводка прогона: масса урезанного роста — по флагу капитального разрыва", "model/uncertainty.py",
             'out["growth_cut_mass"] = sum(hi.prob[c.key] for c in run.cells if "growth_cut" in c.flags)',
             'out["growth_cut_mass"] = sum(hi.prob[c.key] for c in run.cells if "capital_gap" in c.flags)'),
    Mutation("M182", "«цена правила»: замыкание без ограничения считается на книге с ограничением",
             "model/book_results.py", 'closures: dict[str, dict[str, Any]] = {UNCONSTRAINED: {f"{GROWTH}.enabled": False}}',
             'closures: dict[str, dict[str, Any]] = {UNCONSTRAINED: {f"{GROWTH}.order": DIVIDEND_FIRST}}'),
    Mutation("M183", "«цена правила»: масса капитального разрыва — слой рыночных ставок", "model/book_results.py",
             'capital_gap_mass=grid.layers["analytical"].capital_gap_mass)',
             'capital_gap_mass=grid.layers["macro_neutral"].capital_gap_mass)'),
    Mutation("M184", "капитал без премии — на акции в обращении, а не на делитель", "model/reverse.py",
             '            per_share = base["bv_v"] * THOUSAND / run.divisor',
             '            per_share = base["bv_v"] * THOUSAND / run.shares_out'),
    Mutation("M185", "стоимость без опережающего роста: премия роста средств клиентов остаётся", "model/reverse.py",
             'PREMIUM_PATHS = ("volumes.loan_share_drift", "volumes.funds_share_drift") ',
             'PREMIUM_PATHS = ("volumes.loan_share_drift",) '),
    Mutation("M186", "срок избыточной доходности: строка терминала без терминала", "model/reverse.py",
             "    total += sum(prob[c.key] * c.pv_terminal for c in run.cells)", "    total += 0.0"),
    Mutation("M187", "остаточный доход по кварталам — без дисконта", "model/cell.py",
             "        pv_ri_q=tuple(r * d for r, d in zip(val.ri, disc.dfq)),", "        pv_ri_q=tuple(val.ri),"),
    Mutation("M188", "чувствительность к запасу капитала двигает один норматив", "model/grid.py",
             "        return {path: float(book.get(path)) + d for path in BUFFER_PATHS}",
             "        return {path: float(book.get(path)) + d for path in BUFFER_PATHS[:1]}"),
    Mutation("M189", "Н20.1 с прибылью периода в выпуске — отчётный Н20.1 смеси", "model/payload.py",
             '           "n11_star": [R_SHARE(with_profit(q)) for q in qs],',
             '           "n11_star": [R_SHARE(x.ratio(p, "n11", q)) for q in qs],'),
    Mutation("M190", "вероятность клеток с урезанным ростом — под весами смеси, а не слоя «свой взгляд»",
             "model/payload.py", "        p_cut.append(R_PROB(sum(x.p_an[c.key] for c in cut)) if qs else None)",
             "        p_cut.append(R_PROB(sum(x.p_mix[c.key] for c in cut)) if qs else None)"),
    Mutation("M191", "мост «три прибыли»: эффект пакета — из строки процентов по долгу", "model/payload.py",
             '                     "stake_effect": R_MONEY(_node_v(blk.get("adj_stake_sh"))),',
             '                     "stake_effect": R_MONEY(_node_v(blk.get("adj_interest_sh"))),'),
    Mutation("M192", "«цена правила» другой версии книги печатается в выпуске", "model/payload.py",
             '    if not isinstance(data, Mapping) or str(data.get("book_version")) != str(book.get("meta.version")):',
             "    if not isinstance(data, Mapping):"),
    Mutation("M193", "стоимость капитала неполного года пути — без приведения к году", "model/payload.py",
             "            row.append((disc.dfq[qs[0] - 1] / disc.dfq[qs[-1]]) ** (1 / span) - 1 if span > 0 else None)",
             "            row.append(disc.dfq[qs[0] - 1] / disc.dfq[qs[-1]] - 1 if span > 0 else None)"),
    Mutation("M194", "«₽ за 1 п.п. запаса капитала» — в масштабе 0,1 п.п.", "model/payload.py",
             '            U.median_shift(base, b["band"].exact_centres(lam), window) * PP1 / b["step"])',
             '            U.median_shift(base, b["band"].exact_centres(lam), window) * PP01 / b["step"])'),
    Mutation("M195", "контракт не сверяет длины массивов роста с осью лет", "model/payload.py",
             '        if any(len(v) != n for v in rows):\n            p.append("capital.growth: массивы не длины years")',
             '        if False:\n            p.append("capital.growth: массивы не длины years")'),
    # --- связка полосы, печатаемая маржа, гейты знака, потолок выплат, обратный расчёт (М§10, §11.2, §14.2)
    Mutation("M196", "связка применена значением, а не приращением (ось shift на том же пути затёрта)",
             "model/uncertainty.py", "                ov[path] = float(ov[path]) + step", "                ov[path] = value"),
    Mutation("M197", "связка затирает элемент траектории, сдвинутой осью shift, своим значением",
             "model/uncertainty.py",
             "                set_path(ov[home], tail, float(get_path(ov[home], tail)) + step)",
             "                set_path(ov[home], tail, value)"),
    Mutation("M198", "связка идёт к верхнему концу при любом знаке положения оси", "model/uncertainty.py",
             '            end = float((ax["high"] if s >= 0 else ax["low"])[path])',
             '            end = float(ax["high"][path])'),
    Mutation("M199", "схема принимает общий путь связки с осью вида value, dict или с другой связкой",
             "model/book_schema.py", "            if shared:\n                out.append(f\"{where}: путь связки",
             "            if False:\n                out.append(f\"{where}: путь связки"),
    Mutation("M200", "печатаемая маржа после фазы роста — в базисе движка, без моста", "model/grid.py",
             '        value = year_mgmt(ctx, "nim", y, c.annual["nim"][i], row) if y >= from_year else None',
             '        value = c.annual["nim"][i] if y >= from_year else None'),
    Mutation("M201", "печатаемая маржа — средняя всех лет сетки (первый год участка не читается)", "model/grid.py",
             '        value = year_mgmt(ctx, "nim", y, c.annual["nim"][i], row) if y >= from_year else None',
             '        value = year_mgmt(ctx, "nim", y, c.annual["nim"][i], row)'),
    Mutation("M202", "гейт цели печатаемой маржи — с допуском вдесятеро шире", "model/checks.py",
             '    fired = abs(mean - target) > tol\n    msg = (f"ЧПМ (упр.) модальной клетки',
             '    fired = abs(mean - target) > 10 * tol\n    msg = (f"ЧПМ (упр.) модальной клетки'),
    Mutation("M203", "допуск гейта знака объёмных эффектов не читается из книги", "model/grid.py",
             '    tol = SIGN_TOL if cfg is None else float(cfg["tol"])', "    tol = SIGN_TOL"),
    Mutation("M204", "гейт знака объёмных эффектов не срабатывает (число теста не читается)", "model/checks.py",
             '    fired = not st["ok"]\n    worlds = ', "    fired = False\n    worlds = "),
    Mutation("M205", "знак стресса: разовый убыток уменьшен, а не увеличен", "model/grid.py",
             'float(book.get(f"regimes.{r}.one_off_loss.amount")) - step',
             'float(book.get(f"regimes.{r}.one_off_loss.amount")) + step'),
    Mutation("M206", "знак стресса: более строгий и более мягкий сценарии переставлены", "model/grid.py",
             "                    if req[a] > req[b] + REQ_TOL and profit[a] - profit[b] > tol:",
             "                    if req[a] < req[b] - REQ_TOL and profit[a] - profit[b] > tol:"),
    Mutation("M207", "знак стресса: масса — под весами слоя «свой взгляд», а не точки", "model/grid.py",
             "    prob = point_probabilities(run)\n    bad = (", '    prob = run.layers["analytical"].prob\n    bad = ('),
    Mutation("M208", "знак стресса: требование не проверяется в клетках режима шока", "model/grid.py",
             "            profit = {s: run.cell(w, r, s).annual[\"ni_sh\"][-1] for s in scenarios}",
             "            if ctx.prep.regimes[r].shock_year is not None:\n                continue\n"
             "            profit = {s: run.cell(w, r, s).annual[\"ni_sh\"][-1] for s in scenarios}"),
    Mutation("M209", "гейт знака стресса не срабатывает", "model/checks.py",
             '    return Finding("stress_sign", "gate", not st["ok"], ', '    return Finding("stress_sign", "gate", False, '),
    Mutation("M210", "допуск гейта потолка выплат не читается из книги", "model/checks.py",
             '    slack = float(ctx.book.opt("checks.payout_cap.tolerance", 0.0))', "    slack = 0.0"),
    Mutation("M211", "закрытый квартал без своей строки истории — отказ, а не ноль", "model/dividends.py",
             "            if row is None:\n                # квартал покрыт",
             "            if row is None:\n                raise FactsError(f\"нет строки истории {tl.period(x)}\")\n"
             "            if row is None:\n                # квартал покрыт"),
    Mutation("M212", "строка истории закрытого квартала без DPS даёт ноль, а не отказ", "model/dividends.py",
             "            if dps is None:\n                raise FactsError(f\"dividends.history: в строке за закрытый",
             "            if dps is None:\n                continue\n            if dps is None:\n"
             "                raise FactsError(f\"dividends.history: в строке за закрытый"),
    Mutation("M213", "обратный расчёт: ключ «оба конца оси идут за центром» не читается", "model/reverse.py",
             "    return str(book.opt(AXIS_FOLLOW, FOLLOW_NEAR))", "    return FOLLOW_NEAR"),
    Mutation("M214", "обратный расчёт: сдвинутая ось выходит из отрезка поиска строки", "model/reverse.py",
             'axes[j]["low"], axes[j]["high"] = min(max(low + step, lo), v), max(min(high + step, hi), v)',
             'axes[j]["low"], axes[j]["high"] = low + step, high + step'),
    Mutation("M215", "обратный расчёт: корень на краю отрезка поиска принимается за решение", "model/reverse.py",
             "    return value is not None and value != book_value and value in (lo, hi)", "    return False"),
    Mutation("M216", "печатаемая маржа — у каждой строки обратного расчёта, а не у строки цели ЧПМ", "model/reverse.py",
             '    if run is None or NIM_PATH not in ax["paths"] or book.opt(NIM_LT) is None:',
             "    if run is None or book.opt(NIM_LT) is None:"),
    Mutation("M217", "слово отношения расходов к доходам — литерал кода (термин книги не читается)", "model/checks.py",
             '    return book.label_or("terms.cir", CIR_WORD)', "    return CIR_WORD"),
    Mutation("M218", "подпись строки «цены правила» — всегда слово кода", "model/book_results.py",
             '    return book.label_or(f"rule_price.{key}", RULE_TITLES[key])', "    return RULE_TITLES[key]"),
    Mutation("M219", "коэффициент дробления уходит в выпуск узлом факта", "model/payload.py",
             '**({"factor": _node_v(a["factor"])} if _node_v(a.get("factor")) is not None else {})}',
             '**({"factor": a["factor"]} if a.get("factor") is not None else {})}'),
    Mutation("M220", "контракт не сверяет тип коэффициента дробления", "model/payload.py",
             "        if factor is not None and (isinstance(factor, bool) or not isinstance(factor, (int, float)) or not factor > 0):",
             "        if False:"),
    Mutation("M221", "дивдоходность за 12 месяцев при квартальном календаре — по экс-датам окна", "model/payload.py",
             "    if x.cal is not None:\n        got = _declared_quarters(x)",
             "    if False:\n        got = _declared_quarters(x)"),
    Mutation("M222", "словарь терминов выпуска — только два обязательных термина книги", "model/payload.py",
             '    terms = {str(k): str(v) for k, v in book.get("meta.labels.terms").items()}',
             '    terms = {k: book.label(f"terms.{k}") for k in ("lt_level", "profit_short")}'),
    Mutation("M223", "узел требования называет сравниваемым отчётный норматив", "model/payload.py",
             'REQUIREMENT_COMPARE = {"n20": "n20", "n11": "n11_star"}', 'REQUIREMENT_COMPARE = {"n20": "n20", "n11": "n11"}'),
    Mutation("M224", "суммы моста подписаны базой размещённых акций", "model/payload.py",
             '**({"amount_basis": AMOUNT_OUTSTANDING} if _amount_basis(x.book) else {})',
             '**({"amount_basis": AMOUNT_ISSUED} if _amount_basis(x.book) else {})'),
    Mutation("M225", "узел числа гейта знака стресса несёт «выполнен» при нарушениях", "model/payload.py",
             '"mass": R_PROB(ss["mass"]), "max_excess": R_MONEY(ss["max_excess"]), "ok": bool(ss["ok"])}',
             '"mass": R_PROB(ss["mass"]), "max_excess": R_MONEY(ss["max_excess"]), "ok": True}'),
    Mutation("M226", "знак стресса (а): допуск роста стоимости не применён", "model/grid.py",
             "            if dv > tol:", "            if dv > 0.0:"),
    Mutation("M227", "потолок выплат: без допуска равенства", "model/checks.py",
             "            if paid > limit + REL_TOL * max(1.0, limit):", "            if paid > limit:"),
    Mutation("M228", "κ-добавка при названном мире-опоре — только вверх", "model/credit.py",
             "            out[q] = kappa * (real_w[j] - real_n[j])", "            out[q] = kappa * max(0.0, real_w[j] - real_n[j])"),
    Mutation("M229", "мир-опора κ не читается: добавка — от базового мира", "model/cell.py",
             "ctx.worlds[p.kappa_world or BASE_WORLD].real_key, Q,", "ctx.worlds[BASE_WORLD].real_key, Q,"),
    Mutation("M230", "кредитная маржа стационара — с прежней κ-добавкой при названном мире-опоре", "model/nii.py",
             "        cor = cor_lt + kappa * kappa_gap(real[w], real[ref or BASE_WORLD], ref is not None)",
             "        cor = cor_lt + kappa * max(0.0, real[w] - real[BASE_WORLD])"),
    Mutation("M231", "вид угасания терминала не читается из книги", "model/cell.py",
             "    if p.fixed_growth_share is None:\n        term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, "
             "multiple=p.multiple, k_t=disc.k_t,\n                        symmetric=p.fade_symmetric, **terminal_keys(p))",
             "    if p.fixed_growth_share is None:\n        term = terminal(**inputs, real_growth=p.real_growth, fade=p.fade, "
             "multiple=p.multiple, k_t=disc.k_t,\n                        symmetric=False, **terminal_keys(p))"),
    Mutation("M232", "симметричное угасание — как одностороннее", "model/valuation.py",
             "    if symmetric:\n        roe_t = k_t + fade * excess",
             "    if symmetric:\n        roe_t = k_t + fade * max(excess, 0.0) + min(excess, 0.0)"),
    Mutation("M233", "стационарная маржа гейта — в базисе движка, без моста", "model/levels.py",
             '    return {"world": world, "value": ctx.bridge.to_mgmt_nim(ctx.transmission.nss[world]),',
             '    return {"world": world, "value": ctx.transmission.nss[world],'),
    Mutation("M234", "гейт стационарной маржи — с допуском вдесятеро шире", "model/checks.py",
             '    fired = abs(value - target) > tol\n    msg = (f"стационарная ЧПМ',
             '    fired = abs(value - target) > 10 * tol\n    msg = (f"стационарная ЧПМ'),
    Mutation("M235", "строка уровней слоя «рыночные ставки как есть» — под весами слоя «свой взгляд»", "model/levels.py",
             '            "macro_neutral": (LAYER_TITLES["macro_neutral"], dict(run.layers["macro_neutral"].prob))}',
             '            "macro_neutral": (LAYER_TITLES["macro_neutral"], dict(run.layers["analytical"].prob))}'),
    Mutation("M236", "уровни — средняя всех лет сетки (первый год участка не читается)", "model/levels.py",
             "    return [y for y in range(max(int(from_year), tl.anchor_year), tl.last_year + 1)",
             "    return [y for y in range(tl.anchor_year, tl.last_year + 1)"),
    Mutation("M237", "доля кредитов — кредиты по амортизированной стоимости к процентным активам", "model/levels.py",
             '    pairs = [(mix.quarter_end("loans", q), mix.quarter_end("iea", q)) for q in [qs[0] - 1] + qs]',
             '    pairs = [(mix.quarter_end("loans_ac", q), mix.quarter_end("bv", q)) for q in [qs[0] - 1] + qs]'),
    Mutation("M238", "C/I года смеси — без переоценки облигаций в доходе", "model/levels.py",
             '           else f["nii"] + f["fees"] + f["ins"] + f["misc"] + fvr)', '           else f["nii"] + f["fees"] + f["ins"])'),
    Mutation("M239", "гейт окна фактов судит слой «свой взгляд»", "model/checks.py",
             '    row = node["rows"]["macro_neutral"]\n    bands = ', '    row = node["rows"]["analytical"]\n    bands = '),
    Mutation("M240", "гейт окна фактов не судит C/I", "model/checks.py",
             '    outside = [k for k in ("cor", "cir") if judged[k] is None or not bands[k][0] <= judged[k] <= bands[k][1]]',
             '    outside = [k for k in ("cor",) if judged[k] is None or not bands[k][0] <= judged[k] <= bands[k][1]]'),
    Mutation("M241", "область гейта долгосрочного C/I не читается: всегда модальная клетка", "model/levels.py",
             "    if scope == MARKET_LAYER:\n        prob = ", "    if False:\n        prob = "),
    Mutation("M242", "стоимость средств клиентов — по всем пассивам, с оптом", "model/levels.py",
             "    tl, funds = ctx.timeline, client_funds(ctx)", "    tl, funds = ctx.timeline, ctx.prep.roles.liabilities"),
    Mutation("M243", "стоимость средств клиентов — к ключевой ставке последнего квартала", "model/levels.py",
             "        key = sum(ctx.worlds[w].key[q] * tl.d(q) for q in qs) / sum(tl.d(q) for q in qs)",
             "        key = ctx.worlds[w].key[qs[-1]]"),
    Mutation("M244", "гейт стоимости средств клиентов: масса — единица, а не вес миров", "model/checks.py",
             '    return Finding("funds_cost_to_key", "gate", bool(bad), sum(float(weights.get(w, 0.0)) for w in bad),',
             '    return Finding("funds_cost_to_key", "gate", bool(bad), float(bool(bad)),'),
    Mutation("M245", "путь смеси точки — под весами слоя «свой взгляд»", "model/levels.py",
             "    prob = point_probabilities(run)\n    tl = ctx.timeline",
             '    prob = dict(run.layers["analytical"].prob)\n    tl = ctx.timeline'),
    Mutation("M246", "справочный вариант: разность — к нулю, а не к точке книги", "model/book_results.py",
             '               "d_point": grid.point - run.point}', '               "d_point": grid.point}'),
    Mutation("M247", "справочный вариант не может ввести необязательный ключ", "model/book_results.py",
             '        return book.with_overrides(dict(spec["overrides"]), create=True)',
             '        return book.with_overrides(dict(spec["overrides"]))'),
    Mutation("M248", "выпуск берёт справочные варианты таблицы другой версии книги", "model/payload.py",
             "    if str(data.get(\"book_version\")) != str(book.get(\"meta.version\")):\n"
             "        return None, \"таблицы книги — другой версии книги\"",
             "    if False:\n        return None, \"таблицы книги — другой версии книги\""),
    Mutation("M249", "масса знака стресса под весами слоя — под вероятностями точки", "model/grid.py",
             '            "mass": sum(prob[k] for k in bad), "mass_analytical": sum(own[k] for k in bad),',
             '            "mass": sum(prob[k] for k in bad), "mass_analytical": sum(prob[k] for k in bad),'),
    Mutation("M250", "передача убытка в стоимость — к убытку до налога", "model/grid.py",
             '                net = step * (1 - float(c.quarters["tau_eff"][q_loss])) * (1 - ctx.prep.nci_share)',
             "                net = step"),
    Mutation("M251", "обратный расчёт: порог уточнения у края диапазона не читается", "model/reverse.py",
             "    return abs(gap_at(high if value > high else low)) <= float(limit)", "    return True"),
    Mutation("M252", "обратный расчёт: невязка — на дальнем краю диапазона", "model/reverse.py",
             "    return abs(gap_at(high if value > high else low)) <= float(limit)",
             "    return abs(gap_at(low if value > high else high)) <= float(limit)"),
    Mutation("M253", "строка цели ЧПМ печатает маржу модальной клетки и при ключе стационарной маржи", "model/reverse.py",
             '    judged = None if run is None or NIM_PATH not in ax["paths"] else judged_nim(run.ctx)',
             "    judged = None"),
    Mutation("M254", "запас якоря «с глиссадой» — к требованию без глиссады", "model/payload.py",
             '        glide = x.E(x.p_an, "req20_glide", 1)', '        glide = x.E(x.p_an, "req20", 1)'),
    Mutation("M255", "уровни выпуска — без строки смеси заголовка под её весами", "model/levels.py",
             "            POINT: (LEVEL_TITLES[POINT], point_probabilities(run)),",
             '            POINT: (LEVEL_TITLES[POINT], dict(run.layers["macro_neutral"].prob)),'),
    Mutation("M256", "книга строки чувствительности не двигает ось за ключом", "model/payload.py",
             '    if kind != "cor" and axes_follow(book):', "    if False:"),
    Mutation("M257", "узел числа гейта стоимости средств несёт «выполнен» при превышении", "model/payload.py",
             '                         for w, row in fc["by_world"].items()}, "ok": bool(fc["ok"]),',
             '                         for w, row in fc["by_world"].items()}, "ok": True,'),
    Mutation("M258", "стоимость без опережающего роста: траектория премии сектора остаётся с премией", "model/reverse.py",
             '({k: (v if k == "LT_from" or f"{path}.{key}.{k}" in kept else 0.0)',
             '({k: (v)'),
    # ---------------------------------------------------------------- мир уровня ключа цели ЧПМ (М§4.5)
    Mutation("M259", "ключ уровня не читается: ключ цели — уровень мира-опоры", "model/nii.py",
             "    if level is not None and level != ref_world:", "    if False:"),
    Mutation("M260", "уровень мира-опоры — под стационар мира-опоры, а не мира уровня", "model/nii.py",
             "            return st.nss(level, 0.0, s_a, ph, ref_world, s_l)",
             "            return st.nss(ref_world, 0.0, s_a, ph, ref_world, s_l)"),
    Mutation("M261", "линейный вывод уровня — без наклона", "model/nii.py",
             "    return start + (float(target) - at_start) / slope", "    return start + (float(target) - at_start)"),
    Mutation("M262", "инвариант решения передачи судит мир-опору при ключе уровня", "model/checks.py",
             "    level = tr.level_world or tr.reference_world\n    nss_ref",
             "    level = tr.reference_world\n    nss_ref"),
    Mutation("M263", "узел суждения об уровне — стационарная маржа мира-опоры", "model/levels.py",
             '    return {"world": world, "value": br.to_mgmt_nim(tr.nss[world]), "key": float(ctx.book.get(NIM_KEY)),',
             '    return {"world": world, "value": br.to_mgmt_nim(tr.nss[tr.reference_world]), "key": float(ctx.book.get(NIM_KEY)),'),
    Mutation("M264", "выведенный уровень мира-опоры печатается в базисе движка", "model/levels.py",
             '            "reference_world": tr.reference_world, "reference_value": br.to_mgmt_nim(tr.reference_level)}',
             '            "reference_world": tr.reference_world, "reference_value": tr.reference_level}'),
    Mutation("M265", "выводимые величины не несут мир уровня", "model/grid.py",
             "    level = {} if level_world(ctx.book) is None else {", "    level = {} if True else {"),
    # ---------------------------------------------------------------- окно фактов и участок уровней (М§14.5)
    Mutation("M266", "доля кредитов якоря — по концу первого квартала сетки", "model/levels.py",
             '                            "anchor": float(anchor["loans"][0]) / float(anchor["iea"][0])}}',
             '                            "anchor": float(anchor["loans"][1]) / float(anchor["iea"][1])}}'),
    Mutation("M267", "наибольший квартал окна — наименьший", "model/levels.py",
             '        return {"min": None if span is None else float(span[0]), "max": None if span is None else float(span[1]),',
             '        return {"min": None if span is None else float(span[0]), "max": None if span is None else float(span[0]),'),
    Mutation("M268", "средние окна не читаются", "model/levels.py",
             '    means = cfg.get("means") or {}', "    means = {}"),
    Mutation("M269", "сообщение гейта окна: маржа — рядом с наименьшим кварталом", "model/checks.py",
             '    best = ((node.get("window") or {}).get("nim") or {}).get("max")',
             '    best = ((node.get("window") or {}).get("nim") or {}).get("min")'),
    Mutation("M270", "подузел окна — строкой узла уровней", "model/levels.py",
             '        out["window"] = window\n    return out', '        out["rows"]["window"] = window\n    return out'),
    Mutation("M271", "участок уровней берёт неполный год якоря", "model/levels.py",
             "            if all(1 <= q <= tl.Q for q in tl.quarters_of_year(y))]",
             "            if any(1 <= q <= tl.Q for q in tl.quarters_of_year(y))]"),
    Mutation("M272", "стоимость риска года смеси — ко всем кредитам, с кредитами по справедливой стоимости",
             "model/levels.py",
             '    avg_iea, avg_ac, avg_bv = (mix.year_mean_end(k, year) for k in ("iea", "loans_ac", "bv"))',
             '    avg_iea, avg_ac, avg_bv = (mix.year_mean_end(k, year) for k in ("iea", "loans", "bv"))'),
    # ---------------------------------------------------------------- обратный расчёт (М§11.2, §11.3)
    Mutation("M273", "список строк с уточнением не читается: уточняется любая строка", "model/reverse.py",
             "    return named is None or key in named", "    return True"),
    Mutation("M274", "список строк с уточнением: пустой список — как нет списка", "model/reverse.py",
             "    named = book.opt(REFINE_ROWS)\n    if named is None:", "    named = book.opt(REFINE_ROWS)\n    if not named:"),
    Mutation("M275", "элемент премии роста, названный фактом, снимается", "model/reverse.py",
             'or f"{path}.{key}.{k}" in kept else 0.0)', "else 0.0)"),
    Mutation("M276", "факт премии роста сохраняет ключ времени у всех траекторий", "model/reverse.py",
             'or f"{path}.{key}.{k}" in kept else 0.0)', 'or k in {p.rpartition(".")[2] for p in kept} else 0.0)'),
    # ---------------------------------------------------------------- справочные варианты (М§14.5)
    Mutation("M277", "выпуск берёт справочные варианты при другом отпечатке книги", "model/payload.py",
             "    if data.get(VARIANTS_BOOK) != book.digest:", "    if False:"),
    Mutation("M278", "справочные варианты выпуска — по цене со знаком, а не по модулю", "model/payload.py",
             'key=lambda r: (r["d_point"] is None, -abs(float(r["d_point"] or 0.0))))',
             'key=lambda r: (r["d_point"] is None, -float(r["d_point"] or 0.0)))'),
    Mutation("M279", "подпись строки варианта — из таблиц, а не из книги", "model/payload.py",
             '**({"note": str(s["note"])} if s.get("note") is not None else {})}',
             '**({"note": str(r["note"])} if r.get("note") is not None else {})}'),
    Mutation("M280", "таблицы книги: подпись варианта не переносится", "model/book_results.py",
             '        if spec.get("note") is not None:        # подпись строки — как в книге',
             "        if False:"),
    Mutation("M281", "сводка таблиц: варианты — в порядке возрастания модуля цены", "model/book_results.py",
             '    return sorted(rows, key=lambda r: (r.get("d_point") is None, -abs(float(r.get("d_point") or 0.0))))',
             '    return sorted(rows, key=lambda r: (r.get("d_point") is None, abs(float(r.get("d_point") or 0.0))))'),
    # ---------------------------------------------------------------- слова гейтов и узлы выпуска
    Mutation("M282", "порог гейта стоимости средств — двумя знаками при трёх у числа", "model/checks.py",
             """f"{parts} при пороге {num(got['max'], RATIO_DIGITS)}")""", """f"{parts} при пороге {num(got['max'], 2)}")"""),
    Mutation("M283", "подпись маржи якоря: отчётная величина — та же маржа через мост", "model/checks.py",
             'reported="не раскрыта" if reported is None else pct(reported, REPORTED_DIGITS))',
             'reported="не раскрыта" if reported is None else pct(value, REPORTED_DIGITS))'),
    Mutation("M284", "узел выпуска без слоя индикаторов — и у выпуска со слоем", "model/payload.py",
             "    return str(words) if indicators is None and words is not None else None",
             "    return str(words) if words is not None else None"),
    Mutation("M285", "контракт не сверяет число строк сводки контрольной модели", "model/payload.py",
             "or n_rows < len(rows)):", "or n_rows < 0):"),
    Mutation("M286", "устаревшие таблицы книги не оставляют замечания сборки", "model/payload.py",
             "    if why_not is not None:\n        out.append(f\"справочные варианты",
             "    if False:\n        out.append(f\"справочные варианты"),
    Mutation("M287", "ключ квартала премии средств клиентов не читается: премия года", "model/cell.py",
             "                d = keyed.get((year, quarter), d)", "                d = keyed.get((year, None), d)"),
    Mutation("M288", "ключ полугодия премии средств клиентов действует в другом полугодии", "model/cell.py",
             "for n in ((1, 2) if h == 1 else (3, 4))}", "for n in ((3, 4) if h == 1 else (1, 2))}"),
    Mutation("M289", "ключ квартала премии средств клиентов действует и после года конца премии", "model/cell.py",
             "            if keyed and year <= p.drift_until:", "            if keyed:"),
    Mutation("M290", "доля оптового фондирования пути — к средствам клиентов, а не к их сумме с оптовым фондированием",
             "model/levels.py", "\"wholesale_share\": wholesale / (funds + wholesale) if ok and funds + wholesale else None}",
             "\"wholesale_share\": wholesale / funds if ok and funds + wholesale else None}"),
    Mutation("M291", "путь фондирования смеси — под вероятностями слоя, а не точки", "model/levels.py",
             "    prob = point_probabilities(run)\n    mix = _Mix(run, prob)\n    c = run.cell(*modal_cell(ctx.book, ctx.posterior))\n"
             "    years = list(range(tl.anchor_year, tl.last_year + 1))\n    ends =",
             "    prob = dict(run.layers[\"analytical\"].prob)\n    mix = _Mix(run, prob)\n"
             "    c = run.cell(*modal_cell(ctx.book, ctx.posterior))\n"
             "    years = list(range(tl.anchor_year, tl.last_year + 1))\n    ends ="),
    Mutation("M292", "якорь пути фондирования — конец первого квартала сетки", "model/levels.py",
             "\"anchor\": of_cell(0), \"mix\": series(of_mix),", "\"anchor\": of_cell(1), \"mix\": series(of_mix),"),
    Mutation("M293", "путь фондирования печатается и без коридора гейта", "model/levels.py",
             "    if ctx.book.opt(WHOLESALE_SHARE) is None:\n        return None\n    tl = ctx.timeline\n"
             "    prob = point_probabilities(run)\n",
             "    if False:\n        return None\n    tl = ctx.timeline\n    prob = point_probabilities(run)\n"),
    Mutation("M294", "заголовок инварианта передачи не называет мир уровня", "model/payload.py",
             "    if name == \"transmission_solved\" and level_world(book) is not None:",
             "    if name == \"transmission_solved\" and level_world(book) is None:"),
    Mutation("M295", "мир уровней режимов печатается без ключа мира-опоры", "model/payload.py",
             "    ref = {} if kappa_world(b) is None else {\"reference_world\": kappa_world(b)}",
             "    ref = {\"reference_world\": kappa_world(b)}"),
    # --- первый проход ядра Совкомбанка (core-pass1: М4, М7, М13, терминал К-Т, М3; tests/support_core_p1.py)
    Mutation("M296", "шаг хранения прогонов не читается: всегда 0,1 ₽", "model/uncertainty.py",
             "    step = draw_step(book)\n", "    step = DRAW_STEP\n"),
    Mutation("M297", "прогоны в хранении — округление половиной к чётному", "model/uncertainty.py",
             "    return tuple(round_half_up(x, step) for x in values)",
             "    return tuple(float(Decimal(repr(float(x))).quantize(Decimal(repr(float(step))), "
             "rounding=\"ROUND_HALF_EVEN\")) for x in values)"),
    Mutation("M298", "валидатор выпуска: кратность прогонов — всегда шагу 0,1 ₽, поле draw_step не читается",
             "model/payload.py", "    grain = float(h.get(\"draw_step\", PRECISION[\"draw\"]))",
             "    grain = PRECISION[\"draw\"]"),
    Mutation("M299", "множители CoR по книгам: нормировка по составу квартала, а не якоря", "model/cell.py",
             "                    llp += cor * p.book_rel[b] * part * dt",
             "                    llp += cor * p.book_rel[b] * part * dt * ac_avg / sum(p.book_rel[x] * (avg[x] - "
             "(fv_avg if x == p.fv_book else 0.0)) for x in roles.loans)"),
    Mutation("M300", "множитель книги — только на путь режима, без κ-добавки и δ", "model/cell.py",
             "                    llp += cor * p.book_rel[b] * part * dt",
             "                    llp += (self.rg.cor_engine[q] * p.book_rel[b] + cor - self.rg.cor_engine[q]) * part * dt"),
    Mutation("M301", "FVC при множителях по книгам — без множителя книги с долей СС", "model/cell.py",
             "                cor_corp, ref_corp = cor * r_fv, self.cor_ref[q] * r_fv",
             "                cor_corp, ref_corp = cor, self.cor_ref[q]"),
    Mutation("M302", "доли якоря нормировки множителей — без вычета кредитов по СС", "model/cell.py",
             "    ac = {b: af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0) for b in roles.loans}",
             "    ac = {b: af.balances[b] for b in roles.loans}"),
    Mutation("M303", "гейт окна фактов при множителях по книгам — по реализованной CoR", "model/checks.py",
             "    judged = {\"cor\": row[\"cor_mix0\"] if mix0 else row[\"cor\"], \"cir\": row[\"cir\"]}",
             "    judged = {\"cor\": row[\"cor\"], \"cir\": row[\"cir\"]}"),
    Mutation("M304", "база расходов по книгам: история без весов", "model/cell.py",
             "    return w_hat, {x: sum(w_hat[b] * avg[x][b] for b in used) for x in range(-3, 1)}",
             "    return w_hat, {x: sum(avg[x][b] for b in used) for x in range(-3, 1)}"),
    Mutation("M305", "взвешенная база расходов — и у комиссий", "model/cell.py",
             "                v_ex_c = vol_c / flows[\"vol_opex\"][q - 4] - 1 - wage\n",
             "                v_ex_c = vol_c / flows[\"vol_opex\"][q - 4] - 1 - wage\n"
             "                fees = flows[\"fees\"][q - 4] * (1 + wage + p.fees_gvw[q] + p.link_fees * v_ex_c)\n"),
    Mutation("M306", "база расходов по книгам — по остаткам конца квартала, а не по средним", "model/cell.py",
             "                vol_c = sum(w_b * avg[b] for b, w_b in p.opex_w.items())",
             "                vol_c = sum(w_b * E[b] for b, w_b in p.opex_w.items())"),
    Mutation("M307", "память оценок шага переиспользует расходы при весе балансирующей книги", "model/cell.py",
             "p.link_base != \"iea\"\n                and not p.opex_w_bal):", "p.link_base != \"iea\"):"),
    Mutation("M308", "база расходов по книгам не в рядах-базах оценки шага", "model/cell.py",
             "STEP_FLOWS = (\"fees\", \"opex\", \"ins\", \"ni_sh\", \"vol\", \"vol_opex\")",
             "STEP_FLOWS = (\"fees\", \"opex\", \"ins\", \"ni_sh\", \"vol\")"),
    Mutation("M309", "веса книг пассивов в базе расходов не читаются", "model/cell.py",
             "                vol_c = sum(w_b * avg[b] for b, w_b in p.opex_w.items())",
             "                vol_c = sum(w_b * avg[b] for b, w_b in p.opex_w.items() if b in roles.assets)"),
    Mutation("M310", "блок постоянных частей терминала угасает вместе с бизнесом", "model/valuation.py",
             "    tv_ri = phi * x_b + w * (i_f - k * f_k) / k",
             "    tv_ri = phi * (x_b + w * (i_f - k * f_k) / k)"),
    Mutation("M311", "строки в реальных рублях за T — мимо угасания бизнеса", "model/valuation.py",
             "    x_b = (ci_b - k * b) / (k - g) + w * m_l * (1 + pi_t) / (k - pi_t)",
             "    x_b = (ci_b - k * b) / (k - g)\n    i_f = i_f + k * m_l * (1 + pi_t) / (k - pi_t)"),
    Mutation("M312", "купон AT1 за T растёт с g", "model/valuation.py",
             "    ci_b = ci_t1 + w * (1 + g) * y_m * d_f * tax + w * cpn - w * (1 + g) * m_l",
             "    ci_b = ci_t1 + w * (1 + g) * y_m * d_f * tax + w * (1 + g) * cpn - w * (1 + g) * m_l"),
    Mutation("M313", "инструменты капитала за T — без капитала Н20.0 (χ = 0)", "model/valuation.py",
             "    chi = 1.0 if (inst and j20) else 0.0",
             "    chi = 0.0"),
    Mutation("M314", "деньги AT1 в фондировании постоянных частей — дважды", "model/valuation.py",
             "    d_f = f_a - f_k - m_at1 - own",
             "    d_f = f_a - f_k - 2 * m_at1 - own"),
    Mutation("M315", "избыток бизнеса за T — с инфляцией вместо роста g", "model/valuation.py",
             "    x_b = (ci_b - k * b) / (k - g) + w * m_l * (1 + pi_t) / (k - pi_t)",
             "    x_b = (ci_b - k * b) / (k - pi_t) + w * m_l * (1 + pi_t) / (k - pi_t)"),
    Mutation("M316", "связывающий норматив блока — всегда Н20.0", "model/valuation.py",
             "    j20 = (n20 - req20) <= (n11_star - req11)",
             "    j20 = True"),
    Mutation("M317", "κ_20 блока — без вычетов якоря на рубль RWA", "model/cell.py",
             "        kappa20=sc.req20[Q] - (cap.gap20 - sc.ded_pp20[Q]) + cap.ded20_0 / cap.rwa0,",
             "        kappa20=sc.req20[Q] - (cap.gap20 - sc.ded_pp20[Q]),"),
    Mutation("M318", "κ_11 блока — без вычетов якоря на рубль RWA", "model/cell.py",
             "        kappa11=sc.req11[Q] - (cap.gap11 - sc.ded_pp11[Q]) + cap.ded11_0 / cap.rwa0,",
             "        kappa11=sc.req11[Q] - (cap.gap11 - sc.ded_pp11[Q]),"),
    Mutation("M319", "неконтролирующие доли — не в фондировании постоянных частей", "model/valuation.py",
             "    own = fixed.nci + fixed.dp_fix if \"other_fixed_liabilities\" in on else 0.0",
             "    own = fixed.dp_fix if \"other_fixed_liabilities\" in on else 0.0"),
    Mutation("M320", "λ_F читает проход клеток: входы прохода несут ключ числом", "model/grid.py",
             "        prep = dataclasses.replace(prep, fixed_growth_share=nan, fixed_parts=None,\n",
             "        prep = dataclasses.replace(prep, fixed_parts=None,\n"),
    Mutation("M321", "решения о дивиденде при выкупе — на акциях в обращении якоря, а не клетки", "model/dividends.py",
             "    out_share = n_c / policy.n_iss",
             "    out_share = policy.n_out / policy.n_iss"),
    Mutation("M322", "выкуп в совокупном доходе (как прочие движения капитала)", "model/cell.py",
             "        if bb:\n            BV -= bb",
             "        if bb:\n            ci -= bb\n            BV -= bb"),
    Mutation("M323", "стоимость на акцию при выкупе — V / N_T (дивиденды проданных акций — оставшимся)", "model/valuation.py",
             "    s = sum(d_ext[q] * dfq[q] for q in range(q0, Q + 1)) + dfq[Q] * 1000 * tv_ddm / n_t",
             "    s = (pv_div + dfq[Q] * tv_ddm) * 1000 / n_t"),
    Mutation("M324", "цена покупок — форвард конца квартала, а не середины", "model/cell.py",
             "            p_bar = st.p_plus * (1 + bb.disc[self.world].k[q] / 2)",
             "            p_bar = st.p_plus * (1 + bb.disc[self.world].k[q])"),
    Mutation("M325", "дивиденд квартала не вычитается из форварда цены", "model/cell.py",
             "            st.p_plus = st.p_plus * (1 + bb.disc[self.world].k[q]) - d_ext - bb.bridge_dps.get(q, 0.0)",
             "            st.p_plus = st.p_plus * (1 + bb.disc[self.world].k[q]) - bb.bridge_dps.get(q, 0.0)"),
    Mutation("M326", "плата за капитал цены выкупа — мира N у всех клеток", "model/cell.py",
             "            p_bar = st.p_plus * (1 + bb.disc[self.world].k[q] / 2)",
             "            p_bar = st.p_plus * (1 + bb.disc[BASE_WORLD].k[q] / 2)"),
    Mutation("M327", "акции на конце сетки одной клетки — у всех клеток прогона", "model/cell.py",
             "    bb = {} if p.bb is None else buyback_series(rows)\n    term, val = labelled_value(",
             "    bb = {} if p.bb is None else dict(buyback_series(rows), n_t=(shared if shared is not None else {}).setdefault(\"n_t\", rows[-1][\"n_out\"]))\n    term, val = labelled_value("),
    Mutation("M328", "закрытые к дате книги кварталы — по форварду, а не по цене рынка", "model/cell.py",
             "        elif q < bb.qb:\n            p_bar = bb.closed.get(q, bb.p_book)",
             "        elif q < 0:\n            p_bar = bb.closed.get(q, bb.p_book)"),
    Mutation("M329", "форвард выкупа — от живой цены, а не от цены книги", "model/grid.py",
             "    prep = prepare(book, facts, timeline, bridge, transmission, live.register)",
             "    prep = prepare(book.with_overrides({\"meta.market_price\": dict(live.prices)}), facts, timeline, bridge, transmission, live.register)"),
    Mutation("M330", "входы выкупа не в отпечатке прохода клеток", "model/grid.py",
             "    prep, ref = inputs.prep, inputs.prep.reference_world",
             "    prep, ref = dataclasses.replace(inputs.prep, bb=None), inputs.prep.reference_world"),
    Mutation("M331", "выкуп в год шока при skip_in_shock_year не снимается", "model/cell.py",
             "        if bb.skip and self.rg.shock_year is not None and self.years[q] == self.rg.shock_year:",
             "        if False:"),
    Mutation("M332", "шаг хранения прогонов не попал в выпуск", "model/payload.py",
             "        headline[\"draw_step\"] = band.draw_step",
             "        pass"),
    Mutation("M333", "мост норматива выпуска: выкуп не в строке «OCI и прочее» (уходит в остаток)", "model/payload.py",
             "        oci -= total(lambda c, q: Q(c, \"bb\", q))",
             "        oci -= 0.0"),
    Mutation("M334", "водопад смеси заголовка без строки выкупа", "model/payload.py",
             "        a_v0 = R_MONEY(a_bv + a_ri + a_t + a_bb)",
             "        a_v0 = R_MONEY(a_bv + a_ri + a_t)"),
    Mutation("M335", "слой сетки — по остаточному доходу, а не по оценке в цене при выкупе", "model/grid.py",
             "    v0 = sum(prob[c.key] * c.v_price for c in cells)",
             "    v0 = sum(prob[c.key] * c.v_ri for c in cells)"),
    Mutation("M336", "узел постоянных частей терминала не попал в клетки выпуска", "model/payload.py",
             "            **({} if c.terminal_fixed is None else {\"terminal_fixed\": _terminal_fixed(c.terminal_fixed)}),",
             "            **({}),"),
    Mutation("M337", "дивиденд записи закрытого квартала с экс-датой позже даты книги не снижает форвард выкупа",
             "model/cell.py", "        if calendar.closed(tl.index(str(period))):     # вычтен из BV в якоре",
             "        if False:     # вычтен из BV в якоре"),
    # --- независимая проверка прохода 1 (core-verify): таблицы книги при выкупе — одна форма оценки с выпуском
    Mutation("M338", "P/B клетки таблиц книги при выкупе — по остаточному доходу, а не по оценке в цене",
             "model/book_results.py", "\"bv_v\": c.bv_v, \"pb\": c.v_price / c.bv_v,",
             "\"bv_v\": c.bv_v, \"pb\": c.v_ri / c.bv_v,"),
    # --- второй проход ядра Совкомбанка (core-pass2: К1–К7; tests/support_core_p2.py)
    Mutation("M339", "К3: структурная доля опта не читается — база опта всегда доля якоря", "model/cell.py",
             "wh_to_funds=float(book.get(\"volumes.wholesale_to_funds\")) if wh_struct is None else wh_struct,",
             "wh_to_funds=float(book.get(\"volumes.wholesale_to_funds\")),"),
    Mutation("M340", "К3: опт сверх структурной доли не гасится — база шага по доле якоря", "model/cell.py",
             "wh_base = p.wh_to_funds * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))",
             "wh_base = (p.wh_anchor or p.wh_to_funds) * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))"),
    Mutation("M341", "К3: опт по нужде печатается сверх доли якоря, а не сверх структурной доли", "model/cell.py",
             "\"wholesale_extra\": extra, \"other_assets\": OA,",
             "\"wholesale_extra\": extra + ((p.wh_anchor or p.wh_to_funds) - p.wh_to_funds) * funds, "
             "\"other_assets\": OA,"),
    Mutation("M342", "К3: опт по нужде терминала (WT_Q) — сверх доли якоря", "model/cell.py",
             "                  wholesale_extra=last[\"wholesale_extra\"])",
             "                  wholesale_extra=last[\"wholesale_extra\"] + ((p.wh_anchor or p.wh_to_funds) - "
             "p.wh_to_funds) * last[\"funds\"])"),
    Mutation("M343", "К7: покрытие книги якоря — на остатке с кредитами по СС", "model/cell.py",
             "        ac = af.balances[b] - (af.fv_loans if b == af.fv_book else 0.0)\n        if not raw[b] < ac:",
             "        ac = af.balances[b]\n        if not raw[b] < ac:"),
    Mutation("M344", "К7: остаток резерва вне книг постоянен в рублях", "model/cell.py",
             "    return total + p.allow_resid * loans_ac / p.loans_ac0", "    return total + p.allow_resid"),
    Mutation("M345", "К7: резерв по книгам — по остаткам начала квартала", "model/cell.py",
             "AL = allowance_of(p, E, fv, loans_ac)", "AL = allowance_of(p, E0, fv, loans_ac)"),
    Mutation("M346", "К7: остаток резерва вне книг потерян", "model/cell.py",
             "    resid = af.allowance - sum(raw.values())", "    resid = 0.0 * af.allowance"),
    Mutation("M347", "К5: нет выреза гарантий из плотности книги (RWA якоря растёт на G_0)", "model/cell.py",
             "rw = carve_guarantees(rw, guar.g0, guar.carve, af.balances[guar.carve])",
             "rw = carve_guarantees(rw, guar.g0, guar.carve, float(\"inf\"))"),
    Mutation("M348", "К5: RWA гарантий без дрейфа плотности и валютного индекса", "model/capital.py",
             "        if guar is not None:\n            base += guar\n        return base * dn * x",
             "        if guar is not None:\n            return base * dn * x + guar\n        return base * dn * x"),
    Mutation("M349", "К5: драйвер гарантий — средний за квартал, а не уровень конца квартала", "model/cell.py",
             "g_q = None if p.guar is None else self.guarantee(E, fees, q)",
             "g_q = None if p.guar is None else (self.guarantee(E, fees, q) + self.guarantee(E0, fees, q - 1)) / 2"),
    Mutation("M350", "К5: G_0 без веса (масштаба калибровки RWA)", "model/capital.py",
             "            + float(n[\"financial\"]) * float(ccf[\"financial\"])) * float(spec[\"weight\"])",
             "            + float(n[\"financial\"]) * float(ccf[\"financial\"]))"),
    Mutation("M351", "К5: драйвер «база комиссий» — книга выреза (корпоративные кредиты)", "model/cell.py",
             "            d = self.base_end(gd.base, E, q)",
             "            d = E[gd.carve] * gd.d0 / self.p.af.balances[gd.carve]"),
    Mutation("M352", "К4: цели ставок книг — прошлого квартала (сдвиг на квартал)", "model/cell.py",
             "        goal = cell.target_rates(q)\n", "        goal = cell.target_rates(q - 1)\n"),
    Mutation("M353", "К4: ΔNII* — по остаткам конца квартала, а не по средним ЧПД", "model/cell.py",
             "        rate, avg = r[\"_rate\"], r[\"_avg\"]", "        rate, avg = r[\"_rate\"], r[\"_bal\"]"),
    Mutation("M354", "К4: ΔNII* — пассивы с плюсом", "model/cell.py",
             "        gap -= sum([(goal[b] - rate[b]) * avg[b] for b in roles.liabilities])",
             "        gap += sum([(goal[b] - rate[b]) * avg[b] for b in roles.liabilities])"),
    Mutation("M355", "К4: смесь балансирующих за T при ключе — по лаговым ставкам", "model/cell.py",
             "y_balancing=cell.stationary[\"y_bal\"],", "y_balancing=cell.stationary[\"y_bal_lagged\"],"),
    Mutation("M356", "К4: входы прохода не видят ключа (проход клеток полосы — без стационарных ставок)", "model/grid.py",
             "    prep = dataclasses.replace(ctx.prep, real_growth=nan, fade=nan, multiple=nan, fade_symmetric=False)",
             "    prep = dataclasses.replace(ctx.prep, real_growth=nan, fade=nan, multiple=nan, fade_symmetric=False, "
             "stationary_rates=False)"),
    Mutation("M358", "К2: комиссии при своей базе растут по link_base", "model/cell.py",
             "                    g_fees = wage + p.fees_gvw[q] + p.link_fees * (a_f / flows[\"vol_fees\"][q - 4] - 1 - wage)",
             "                    pass"),
    Mutation("M359", "К2: «номинал» — индекс к прошлому кварталу, а не к тому же кварталу прошлого года", "model/cell.py",
             "            got = flows[key][q - 4] * (1 + self.w.wage[q])",
             "            got = flows[key][q - 1] * (1 + self.w.wage[q]) ** 0.25"),
    Mutation("M360", "К2: смесь базы расходов без нормировки на якоре (ступень в первом квартале)", "model/cell.py",
             "                    a_c += share * p.mix_b0 * flows[src][q] / a0",
             "                    a_c += share * flows[src][q]"),
    Mutation("M361", "К2: ряды баз строк вне рядов-баз оценки шага", "model/cell.py",
             "STEP_FLOWS += (\"vol_fees\", \"vol_ins\", \"vol_mix\")", "STEP_FLOWS += ()"),
    Mutation("M362", "К2: память оценок шага переиспользует строку на базе с балансирующими книгами", "model/cell.py",
             "        if p.memo_off:", "        if False:"),
    Mutation("M363", "К2: веса балансирующих книг базы строки — по остатку начала квартала, а не по средним ЧПД",
             "model/cell.py", "            got = sum([w * avg[b] for b, w in lb.weights.items()])",
             "            got = sum([w * (E0[b] if b in BALANCING else avg[b]) for b, w in lb.weights.items()])"),
    Mutation("M364", "К2: страхование при своей базе растёт по link_base", "model/cell.py",
             "            if p.ins_line is not None and p.link_ins:", "            if False:"),
    Mutation("M365", "К6: ведомая книга — в памяти стороны средств (не пересчитывается при другой доле прироста)",
             "model/cell.py",
             "                E.update(books_side)\n                if p.driven is not None:",
             "                E.update(books_side)\n                if False:"),
    Mutation("M366", "К6: ведомая книга растёт и с сектором средств бизнеса, и с драйвером", "model/cell.py",
             "            E[b] = E0[b] * (1 + wage) ** ((1 - lam) * QUARTER_YEARS) * (d_now / d_prev) ** lam",
             "            E[b] = E[b] * (1 + wage) ** ((1 - lam) * QUARTER_YEARS) * (d_now / d_prev) ** lam"),
    Mutation("M367", "К6: связь строки-драйвера не читается (книга ровно за базой)", "model/cell.py",
             "            E[b] = E0[b] * (1 + wage) ** ((1 - lam) * QUARTER_YEARS) * (d_now / d_prev) ** lam",
             "            E[b] = E0[b] * (d_now / d_prev)"),
    Mutation("M368", "К6: драйвер книги — средний уровень квартала, а не конец", "model/cell.py",
             "            d_now, d_prev = self.base_end(lb, E, q), self.base_end(lb, E0, q - 1)",
             "            d_now, d_prev = (self.base_end(lb, E, q) + self.base_end(lb, E0, q - 1)) / 2, "
             "self.base_end(lb, E0, q - 1)"),
    Mutation("M369", "К1: жетон без условия пола (платится всегда)", "model/cell.py",
             "                    if h_floor >= sum(d.base_div for d in first if d.source == \"model\") + need:",
             "                    if True:"),
    Mutation("M370", "К1: пол жетона — требование с запасом менеджмента и глиссадой", "model/cell.py",
             "        return min((row[\"n20\"] - req20) * rwa, (row[\"n11_star\"] - sc.floor11[q]) * rwa)",
             "        return min(self.room(row, q))"),
    Mutation("M371", "К1: запас жетона — при полном росте, а не при наименьшей доле прироста", "model/cell.py",
             "                    floor_row = (low if can_cut else full)[0]", "                    floor_row = full[0]"),
    Mutation("M372", "К1: S_Y без решений года в прошлых кварталах клетки", "model/cell.py",
             "prior_dps=self.dps_year.get(year, 0.0)", "prior_dps=0.0"),
    Mutation("M373", "К1: жетон без капа прибылью года", "model/dividends.py",
             "    m_y = min(min_dps, max(0.0, base_year) * THOUSAND / n_iss)", "    m_y = min_dps"),
    Mutation("M374", "К1: жетон в каждом решении модели квартала, а не у носителя", "model/dividends.py",
             "            paid_token = token if i == carrier else 0.0", "            paid_token = token"),
    Mutation("M375", "К1: жетон не входит в условие роста (base_parts)", "model/cell.py",
             "        if token:\n            base_parts = tuple(", "        if False:\n            base_parts = tuple("),
    Mutation("M376", "К1: избыток носителя не за вычетом жетона", "model/dividends.py",
             "        exc = eps * max(0.0, h_fin - base_t - catch) if eps else 0.0",
             "        exc = eps * max(0.0, h_fin - div_base - catch) if eps else 0.0"),
    Mutation("M377", "К1: недостача года — на акциях в обращении якоря, а не клетки (выкуп)", "model/cell.py",
             "        return token_need(min_dps=p.min_dps[year], base_year=base_y, n_iss=pol.n_iss, n_c=n_c,",
             "        return token_need(min_dps=p.min_dps[year], base_year=base_y, n_iss=pol.n_iss, n_c=pol.n_out,"),
    Mutation("M378", "К1: память DPS по годам не сбрасывается при повторе прохода клетки", "model/cell.py",
             "        self.dps_year = {}                      # память DPS по годам прибыли (жетон, К1) — с начала прохода",
             "        pass"),
    Mutation("M357", "К4: ΔNII* — за два последних года сетки, а не за год L", "model/cell.py",
             "        if tl.year(q) != L:\n            continue\n        goal = cell.target_rates(q)",
             "        if tl.year(q) < L - 1:\n            continue\n        goal = cell.target_rates(q)"),
    # --- независимая проверка прохода 2 (core2-verify): пути, которых не держала ни одна проверка
    Mutation("M379", "К2/К6/К5: номинал на конец квартала — годовой рост зарплат за квартал", "model/cell.py",
             "                acc *= (1 + wage[x]) ** QUARTER_YEARS", "                acc *= (1 + wage[x])"),
    Mutation("M380", "К2: память оценок шага выключает только база комиссий, не страхования", "model/cell.py",
             "    if any(out[k].balancing for k in (\"fees_line\", \"ins_line\") if k in out):",
             "    if any(out[k].balancing for k in (\"fees_line\",) if k in out):"),
    # --- третий проход ядра Совкомбанка (core-pass3: К-Т2, К8, К2б; tests/support_core_p3.py)
    Mutation("M381", "К-Т2а: ν на весь PBT года L (с комиссиями, расходами и прочим)", "model/cell.py",
             "    pbt_t = pbt_l + (nu - 1) * dw + nu * d_nii", "    pbt_t = nu * pbt_l + nu * d_nii"),
    Mutation("M382", "К-Т2а: ν = 365 / дни года L вместо 365,2425 / дни", "model/cell.py",
             "    nu = MEAN_YEAR * len(qs) / 4 / days", "    nu = DAYS_IN_YEAR * len(qs) / 4 / days"),
    Mutation("M383", "К-Т2а: ΔNII*_L без ν", "model/cell.py",
             "    pbt_t = pbt_l + (nu - 1) * dw + nu * d_nii", "    pbt_t = pbt_l + (nu - 1) * dw + d_nii"),
    Mutation("M384", "К-Т2а: доход на избыток Y_X без ψ", "model/valuation.py",
             "        y_x *= year_factor", "        y_x *= 1.0"),
    Mutation("M385", "К-Т2а: фондирование стоящей доли блока К-Т без ψ", "model/valuation.py",
             "        drag = y_m * d_f * year_factor", "        drag = y_m * d_f"),
    Mutation("M386", "К-Т2а: год терминала вне входов прохода (кэш проходов отдаёт проход без поправки)",
             "model/grid.py",
             "    prep = dataclasses.replace(ctx.prep, real_growth=nan, fade=nan, multiple=nan, fade_symmetric=False)",
             "    prep = dataclasses.replace(ctx.prep, real_growth=nan, fade=nan, multiple=nan, fade_symmetric=False, "
             "year_basis=\"calendar\")"),
    Mutation("M387", "К-Т2в: срок n_W из множителя при s = 1, а не при s = 0", "model/valuation.py",
             "        if fade_of(mid, k, g) < fade:", "        if fade_of(mid, k, g, 1) < fade:"),
    Mutation("M388", "К-Т2в: множитель по календарю не читает s (φ_W = fade)", "model/valuation.py",
             "    return fade_of(fade_years(fade, k, g), k, g, s)", "    return fade_of(fade_years(fade, k, g), k, g, 0)"),
    Mutation("M389", "К-Т2в: s на год меньше (срок угасания — со следующего за якорем года)", "model/cell.py",
             "        out[\"fade_s\"] = p.timeline.last_year - p.fade_anchor",
             "        out[\"fade_s\"] = p.timeline.last_year - p.fade_anchor - 1"),
    Mutation("M390", "К-Т2в: год-якорь угасания во входах прохода (проход считается заново на каждый год-якорь)",
             "model/grid.py", "        prep = dataclasses.replace(prep, fade_anchor=None)", "        pass"),
    Mutation("M391", "К-Т2б: связанность минимума — по добору опта на конце Q, без выплаты избытка", "model/valuation.py",
             "        bound = wt_after > 0", "        bound = wholesale_extra > 0"),
    Mutation("M392", "К-Т2б: недостаток капитала не гасит добор опта", "model/valuation.py",
             "            wt_after = max(0.0, wholesale_extra + x_t)", "            wt_after = wholesale_extra"),
    Mutation("M393", "К-Т2б: порог связывания — сам запас HLA, без деления на 1 − m", "model/valuation.py",
             "            wt_after = wholesale_extra + max(0.0, x_t - headroom / (1 - min_share))",
             "            wt_after = wholesale_extra + max(0.0, x_t - headroom)"),
    Mutation("M394", "К-Т2б: минимум ликвидности на D_F, а не на постоянных активах F_A", "model/valuation.py",
             "        m_f = (c_wholesale - y_balancing) * min_share / (1 - min_share) * f_a if bound else 0.0",
             "        m_f = (c_wholesale - y_balancing) * min_share / (1 - min_share) * d_f if bound else 0.0"),
    Mutation("M395", "К-Т2б: минимум ликвидности без m / (1 − m)", "model/valuation.py",
             "        m_f = (c_wholesale - y_balancing) * min_share / (1 - min_share) * f_a if bound else 0.0",
             "        m_f = (c_wholesale - y_balancing) * f_a if bound else 0.0"),
    Mutation("M396", "К-Т2б: стоимость минимума ликвидности — не за средний год", "model/valuation.py",
             "        drag = (y_m * d_f + m_f) * year_factor", "        drag = y_m * d_f * year_factor + m_f"),
    Mutation("M397", "К-Т2б: ставка фондирования блока во входах прохода", "model/grid.py",
             "        prep = dataclasses.replace(prep, fixed_growth_share=nan, fixed_parts=None,\n"
             "                                   fixed_funding=FUNDING_BINARY)",
             "        prep = dataclasses.replace(prep, fixed_growth_share=nan, fixed_parts=None)"),
    Mutation("M398", "К8: деньги за кредитами при ключе (драйвер не читается)", "model/cell.py",
             "        d = self.base_end(self.p.cash.base, E, q)",
             "        d = sum([E[b] for b in self.p.roles.loans]) * self.p.cash.base.end0 / "
             "sum(self.p.af.balances[b] for b in self.p.roles.loans)"),
    Mutation("M399", "К8: ρ без вычета денег якоря (деньги дважды)", "model/cell.py",
             "                OA = p.cash.rho * loans + cash", "                OA = p.oa_ratio * loans + cash"),
    Mutation("M400", "К8: нет выреза плотности — деньги по плотности растущих прочих активов", "model/capital.py",
             "            base += (self.other_assets_cash * (other_assets - self.oa_fixed - cash) + self.cash * cash",
             "            base += (self.other_assets * (other_assets - self.oa_fixed - cash) + self.other_assets * cash"),
    Mutation("M401", "К8: драйвер денег — средний за квартал, а не уровень конца квартала", "model/cell.py",
             "                cash = self.cash_end(E, q)\n",
             "                cash = (self.cash_end(E, q) + self.cash_end(E0, q - 1)) / 2\n"),
    Mutation("M402", "К8: драйвер денег — прошлого квартала (E0 вместо E)", "model/cell.py",
             "                cash = self.cash_end(E, q)\n", "                cash = self.cash_end(E0, q - 1)\n"),
    Mutation("M403", "К8: драйвер «средства клиентов» без ведомых книг К6 (книги на уровне якоря)", "model/cell.py",
             "        d = self.base_end(self.p.cash.base, E, q)",
             "        d = self.base_end(self.p.cash.base, {**E, **{b: self.p.af.balances[b] for b in (self.p.driven or {})}}, q)"),
    Mutation("M404", "К2б: смесь без деления на уровень компоненты D^k_0 (доли уровней, а не доли строки)", "model/cell.py",
             "            out[b] = out.get(b, 0.0) + share * w / d0", "            out[b] = out.get(b, 0.0) + share * w"),
    Mutation("M405", "К2б: проверка суммы долей смеси снята", "model/cell.py",
             "    if abs(total - 1.0) > MIX_TOL:", "    if False:"),
    Mutation("M406", "К2б: RWA гарантий (К5) читает volumes.link_base, а не смесь комиссий", "model/cell.py",
             "        base = line_base(fees_base_spec(book, roles, af.balances), \"fees.volume_base\",",
             "        base = line_base(book.opt(\"volumes.link_base\", LINK_BASES[0]), \"fees.volume_base\","),
    Mutation("M407", "К2б: проверка круга К6 — по записи книги, до компиляции смеси", "model/cell.py",
             "        circle = lb.kind == \"books\" and bool(set(lb.weights) & set(map(str, spec)))",
             "        circle = lb.kind == \"books\" and MIX not in (book.opt(key) or \"\") and "
             "bool(set(lb.weights) & set(map(str, spec)))"),
    Mutation("M408", "К2б: слово funds в компоненте смеси — веса на кредитах", "model/cell.py",
             "    words = {\"loans\": roles.loans, \"funds\": roles.funds if funds is None else funds, \"iea\": roles.assets}",
             "    words = {\"loans\": roles.loans, \"funds\": roles.loans, \"iea\": roles.assets}"),
    Mutation("M409", "К2б: смесь комиссий компилируется по средним остаткам квартала якоря, а не по концу", "model/cell.py",
             "        fees_spec = resolve_line_base(book, FEES_BASE, roles=kw[\"roles\"], balances=kw[\"af\"].balances)",
             "        fees_spec = resolve_line_base(book, FEES_BASE, roles=kw[\"roles\"], balances={b: (e + kw[\"hist_books\"]"
             ".get(-1, {}).get(b, e)) / 2 for b, e in kw[\"af\"].balances.items()})"),
    Mutation("M410", "К-Т2а: узел года терминала не попал в клетки выпуска", "model/payload.py",
             "            **({} if c.terminal_year is None else {\"terminal_year\": _terminal_year(c.terminal_year)}),",
             "            **({}),"),
    Mutation("M411", "К-Т2в: узел угасания по календарю не попал в клетки выпуска", "model/payload.py",
             "            **({} if c.terminal_fade is None else {\"terminal_fade\": {",
             "            **({} if True else {\"terminal_fade\": {"),
    # --- независимая проверка прохода 3 (core3-verify): входы прохода — в отпечатке КАЖДОГО мира (path_keys), а не
    #     только мира-опоры; проход считается верно, но полоса на записях (band(like=…)) взяла бы чужой проход
    Mutation("M412", "К-Т2а: год терминала вне отпечатков миров (кэш проходов отдаёт проход без поправки)",
             "model/grid.py", "    common = dump((prep, inputs.deviations))",
             "    common = dump((dataclasses.replace(prep, year_basis=\"calendar\"), inputs.deviations))"),
    Mutation("M413", "К8: неработающие деньги вне отпечатков миров", "model/grid.py",
             "    common = dump((prep, inputs.deviations))",
             "    common = dump((dataclasses.replace(prep, cash=None), inputs.deviations))"),
    Mutation("M414", "К2б: база строки комиссий (смесь) вне отпечатков миров", "model/grid.py",
             "    common = dump((prep, inputs.deviations))",
             "    common = dump((dataclasses.replace(prep, fees_line=None), inputs.deviations))"),
    # --- четвёртый проход ядра Совкомбанка (core-pass4; tests/support_core_p4.py), в скобках — номер мутации
    #     спецификации notes/core-pass4/spec.yaml. Р5-5: драйвер RWA гарантий — компонента смеси базы комиссий
    Mutation("M415", "Р5-5 (M_p4_9): ветвь квартала «== fees_base» — компонента уходит в ветвь строки комиссий",
             "model/cell.py", "        if gd.driver in GUARANTEE_LEVEL_DRIVERS:", "        if gd.driver == \"fees_base\":"),
    Mutation("M416", "Р5-5 (M_p4_10): драйвер компоненты — вся смесь (доли s_k всех компонент)", "model/cell.py",
             "        base = line_base(comp, f\"{FEES_BASE}.{MIX}.{name}.base\",",
             "        base = line_base(fees_base_spec(book, roles, af.balances), f\"{FEES_BASE}.{MIX}.{name}.base\","),
    Mutation("M417", "Р5-5 (M_p4_11): D^G_0 — уровень всей смеси, D^G_q — компоненты", "model/cell.py",
             "        d0 = base.end0                            # D^c_0 — остатки якоря по весам компоненты",
             "        d0 = line_base(fees_base_spec(book, roles, af.balances), FEES_BASE, books=book.get(\"nii.books\"), "
             "roles=roles, af=af, hist_bal={}, hist_books={}, tl=tl, history=False).end0"),
    Mutation("M418", "Р5-5 (M_p4_12): поле component читается и при драйвере fees_base", "model/cell.py",
             "    if driver == \"fees_component\":", "    if spec.get(\"component\") is not None:"),
    # --- проход ядра 4, Р5-6: корень строк комиссий и страхования множителем
    Mutation("M419", "Р5-6 (M_p4_13): ключ формы корня не читается (корень слагаемым)", "model/cell.py",
             "        root_mult=book.opt(LINE_ROOT_FORM) == ROOT_MULTIPLICATIVE,", "        root_mult=False,"),
    Mutation("M420", "Р5-6 (M_p4_14): корень комиссий дважды — (1 + v + r)(1 + r)", "model/cell.py",
             "                    g_fees = wage + p.link_fees * (a_f / flows[\"vol_fees\"][q - 4] - 1 - wage)",
             "                    g_fees = wage + p.fees_gvw[q] + p.link_fees * (a_f / flows[\"vol_fees\"][q - 4] - 1 - wage)"),
    Mutation("M421", "Р5-6 (M_p4_15): корень комиссий в году переопределения", "model/cell.py",
             "            mult_f = p.root_mult and gvw is None", "            mult_f = p.root_mult"),
    Mutation("M422", "Р5-6 (M_p4_16): страхование со своей базой (К2) — корень слагаемым и при ключе", "model/cell.py",
             "                if p.root_mult:\n                    ins = flows[\"ins\"][q - 4] * (1 + wage + p.link_ins * v_ex_i)",
             "                if False:\n                    ins = flows[\"ins\"][q - 4] * (1 + wage + p.link_ins * v_ex_i)"),
    Mutation("M423", "Р5-6 (M_p4_17): форма корня вне отпечатков миров", "model/grid.py",
             "    common = dump((prep, inputs.deviations))",
             "    common = dump((dataclasses.replace(prep, root_mult=False), inputs.deviations))"),
    # --- проход ядра 4, Р5-4: сложение связок на общем пути
    Mutation("M424", "Р5-4 (M_p4_1): общий путь связок — значение последней связки (перезапись), а не сумма",
             "model/uncertainty.py", "            step = math.fsum(steps)", "            step = steps[-1]"),
    Mutation("M425", "Р5-4 (M_p4_2): центр приращения — значение подменённой книги, а не корневой",
             "model/uncertainty.py", "    root = book.base if book.base is not None else book\n    deltas",
             "    root = book\n    deltas"),
    Mutation("M426", "Р5-4 (M_p4_3): сумма приращений слева направо, без math.fsum", "model/uncertainty.py",
             "            step = math.fsum(steps)",
             "            step = 0.0\n            for x_ in steps:\n                step = step + x_"),
    Mutation("M427", "Р5-4 (M_p4_4): схема при ключе по-прежнему отказывает общему пути двух связок",
             "model/book_schema.py",
             "(other.get(\"kind\") == \"bundle\" and (m < n or additive))",
             "(other.get(\"kind\") == \"bundle\" and m < n)"),
    # M_p4_5 спецификации («путь одной связки — b + Δ вместо прежней строки») — эквивалентный мутант: в двоичной арифметике
    # с округлением к ближайшему fl(b + fl(fl(b + d) − b)) = fl(b + d), подмены те же бит в бит (3,2 млн случайных
    # проб — ни одного расхождения); вместо него — ветвь прежней строки на общем пути корневой книги
    Mutation("M428", "Р5-4: общий путь связок на корневой книге — ветвью одной связки (значение последней связки)",
             "model/uncertainty.py",
             "        if len(steps) == 1 and book.base is None:", "        if book.base is None:"),
    Mutation("M429", "Р5-4 (M_p4_6): правило углов не видит сдвиг траектории (только сам путь)", "model/book_schema.py",
             "            if axis.get(\"kind\") == \"shift\" and any(_under(p, [o]) for o in _paths_of(axis)):",
             "            if axis.get(\"kind\") == \"shift\" and p in _paths_of(axis):"),
    Mutation("M430", "Р5-4 (M_p4_7): правило первого пути и без ключа (ломает прежние книги)", "model/book_schema.py",
             "    if additive:\n        out.extend(_first_path_rules(axes))",
             "    if True:\n        out.extend(_first_path_rules(axes))"),
    Mutation("M431", "Р5-4: на книге-копии одна связка — приращение от значения копии (цена конца оси на копии)",
             "model/uncertainty.py",
             "            if book.base is not None and additive_bundles(book):",
             "            if False:"),
    # --- проход ядра 4, Р5-4: лист вывода — корни расходов в связке оси базы строки
    Mutation("M432", "Р5-4 (M_p4_8): лист кладёт корни расходов в связку и при неполном наборе путей",
             "data/assumptions/evidence/path/derive_on_engine.py",
             # строка правки — с текстом остановки Р5-4: та же строка проверки стоит выше в листе (Р8-6, κ строк), и
             # правка первого вхождения била бы не ту функцию (мутант выживал в CI 29.10.2026)
             "    if len(have) != len(keys):\n        raise RuntimeError(f\"ось «{ax['name']}» несёт часть корней расходов",
             "    if False:\n        raise RuntimeError(f\"ось «{ax['name']}» несёт часть корней расходов"),
    Mutation("M433", "Р5-4: инвариант book_schema судит углы сложения связок и у книги-копии (прогон, вариант)",
             "model/checks.py", "        validate(book.data, corners=book.base is None)",
             "        validate(book.data)"),
    # --- проход ядра 4, независимая проверка (core4-verify): ветви, которые проверки прохода не судили
    Mutation("M434", "Р5-6: страхование со связью через volumes.link_base — корень слагаемым и при ключе",
             "model/cell.py",
             "                ins = flows[\"ins\"][q - 4] * (1 + wage + p.link_ins * v_ex) * (1 + p.ins_gvw[q])",
             "                ins = flows[\"ins\"][q - 4] * (1 + wage + p.ins_gvw[q] + p.link_ins * v_ex)"),
    Mutation("M435", "Р5-4, лист: ось базы несёт корни расходов без доли франшизы строки — без остановки",
             "data/assumptions/evidence/path/derive_on_engine.py", "    if not has_share:\n", "    if False:\n"),
    # --- пятый проход ядра Совкомбанка (core-pass5; tests/support_core_p5.py): Р6-1 — доля неработающих денег К8
    #     параметром книги. M447 спецификации (среднее небалансирующих в годовом шаге) — мутация контрольной модели
    Mutation("M436", "Р6-1: путь без share_from — доля книги с q = 1 (шаг всегда)", "model/cell.py",
             "    s_q = [s_star if q >= q_f else", "    s_q = [s_star if q >= 1 else"),
    Mutation("M437", "Р6-1: c_q без ФОР (s_q вместо s_q + r)", "model/cell.py",
             "    share_q = (c_0,) + tuple(s + r for s in s_q)", "    share_q = (c_0,) + tuple(s for s in s_q)"),
    Mutation("M438", "Р6-1: ФОР постоянными рублями (C_q = s_q D_q + R_0)", "model/cell.py",
             "        return self.p.cash.share_q[q] * d    # доля пути квартала q (Р6-1)",
             "        return (self.p.cash.share_q[q] - self.p.cash.reserves) * d + self.p.cash.reserves * "
             "self.p.cash.base.end0"),
    Mutation("M439", "Р6-1: ρ′ не идёт за путём (ρ − C_0 / L_0 при деньгах по пути — разрыв баланса)", "model/cell.py",
             "                    OA = p.cash.rho_q[q] * loans + cash", "                    OA = p.cash.rho * loans + cash"),
    Mutation("M440", "Р6-1: вырез плотности на раскладке книги ((s* + r) D_0 вместо C_0) — форма Д1", "model/cell.py",
             "        rw = carve_cash(rw, float(book.get(CASH_DENSITY)), cash.c0, af.other_assets)",
             "        rw = carve_cash(rw, float(book.get(CASH_DENSITY)), cash.c0 if cash.share_q is None else "
             "cash.share_q[-1] * cash.base.end0, af.other_assets)"),
    Mutation("M441", "Р6-1: слагаемое вытесненной части с θ вместо (1 − θ)", "model/cell.py",
             "    k = (1.0 - cash.theta) * (rw.other_assets_cash - rw.cash)",
             "    k = cash.theta * (rw.other_assets_cash - rw.cash)"),
    Mutation("M442", "Р6-1: δ с долей книги вместо c_q (слагаемое целиком с q = 1)", "model/cell.py",
             "                delta_q=tuple((c - c_0) * d0 / l0 for c in share_q),",
             "                delta_q=tuple((share_q[-1] - c_0) * d0 / l0 for c in share_q),"),
    Mutation("M443", "Р6-1: слагаемое вытесненной части вне базы RWA (без дрейфа плотности и валютного индекса)",
             "model/capital.py",
             "            base += cash_shift\n        if guar is not None:\n            base += guar\n"
             "        return base * dn * x",
             "            pass\n        if guar is not None:\n            base += guar\n"
             "        return base * dn * x + (0.0 if cash_shift is None else cash_shift)"),
    Mutation("M444", "Р6-1: слагаемого нет в лёгкой оценке нормативов (рост, ограниченный капиталом)", "model/cell.py",
             "        elif p.cash.shift_q is None:            # деньги со своей плотностью (К8, М§4.11)",
             "        elif p.cash.shift_q is None or light:"),
    Mutation("M445", "Р6-1: share: anchor — доля C_0 / D_0 с ФОР по пути (ФОР дважды: s_0 + r)", "model/cell.py",
             "    if raw is None or raw == \"anchor\":",
             "    if raw == \"anchor\":\n        raw = c0 / lb.end0\n    if raw is None:"),
    Mutation("M446", "Р6-1: путь в рублях якоря (ΔC_q одинаковы во всех клетках) — класс 2", "model/cell.py",
             "        return self.p.cash.share_q[q] * d    # доля пути квартала q (Р6-1)",
             "        return self.p.cash.share * d + (self.p.cash.share_q[q] - self.p.cash.share) * "
             "self.p.cash.base.end0"),
    # --- шестой проход ядра Совкомбанка (core-pass6; tests/support_core_p6.py): Р8-6 — франшиза строки в смеси базы
    #     расходов за связью строки. M456 (контроль), M457 (лист §4), M458 (лист вывода) спецификации — мутации контрольной
    #     модели и листов; M459–M460 зарезервированы ключом Р8-6б (решение ведущего). M454 спецификации («ряд H не в
    #     STEP_FLOWS») числа не меняет — H не зависит от состояния шага (только H_(q−4), зарплаты мира и κ), пробы пишут то
    #     же число, — его ловит договор оценки шага (проба не оставляет ряда квартала, принятая оценка несёт его); рядом —
    #     M461 (H вне памяти оценок шага) и M462 (λ — связь расходов вместо связи строки)
    Mutation("M448", "Р8-6: номинальная часть без корня (κ не читается) — наивная форма", "model/cell.py",
             "                        h_nom = flows[nom_name][q - 4] * (1 + wage) * (1 + kap_l[q])",
             "                        h_nom = flows[nom_name][q - 4] * (1 + wage)"),
    Mutation("M449", "Р8-6: франшиза за цепью К6 без корня (V_q = V_(q−1)(1 + w)^((1−λ)/4)(A_q / A_(q−1))^λ) — форма "
             "econ7-classes", "model/cell.py",
             "                        h_nom = flows[nom_name][q - 4] * (1 + wage) * (1 + kap_l[q])\n"
             "                        flows[nom_name][q] = h_nom\n"
             "                        a_c += share * p.mix_b0 * flows[src][q] / a0 * lam_l + share * p.mix_b0 * "
             "(1 - lam_l) * h_nom",
             "                        h_nom = flows[nom_name][q - 1] * (1 + wage) ** ((1 - lam_l) * QUARTER_YEARS) * (\n"
             "                            flows[src][q] / flows[src][q - 1]) ** lam_l\n"
             "                        flows[nom_name][q] = h_nom\n"
             "                        a_c += share * p.mix_b0 * h_nom"),
    Mutation("M450", "Р8-6: λ и 1 − λ переставлены (λ H + (1 − λ) A / A_0)", "model/cell.py",
             "                        a_c += share * p.mix_b0 * flows[src][q] / a0 * lam_l + share * p.mix_b0 * "
             "(1 - lam_l) * h_nom",
             "                        a_c += share * p.mix_b0 * flows[src][q] / a0 * (1 - lam_l) + share * p.mix_b0 * "
             "lam_l * h_nom"),
    Mutation("M451", "Р8-6: история H = 1 (индекс номинала) вместо A_x / A_0 — сезонная ступень 2026К3–2027К2",
             "model/cell.py", "        hist_nom[name] = {x: a[x] / a[0] for x in range(-3, 1)}",
             "        hist_nom[name] = {x: 1.0 for x in range(-3, 1)}"),
    Mutation("M452", "Р8-6: H по зарплатам одного мира (мира-опоры передачи) во всех мирах — франшиза не дрейфует по "
             "мирам (класс 2)", "model/cell.py",
             "                        h_nom = flows[nom_name][q - 4] * (1 + wage) * (1 + kap_l[q])",
             "                        h_nom = flows[nom_name][q - 4] * (1 + self.wh.wage[q]) * (1 + kap_l[q])"),
    Mutation("M453", "Р8-6: κ читается годом (year_value: ключи кварталов не читаются)", "model/cell.py",
             "        nominal[line] = (lam_of[line], _series(roots[line], tl), name)",
             "        nominal[line] = (lam_of[line], tuple(Trajectory(roots[line]).year_value(tl.year(q)) "
             "for q in range(tl.Q + 1)), name)"),
    Mutation("M454", "Р8-6: ряд H не в STEP_FLOWS (проба и откат шага оставляют ряд квартала)", "model/cell.py",
             "STEP_FLOWS += tuple(NOM_FLOWS.values())", "STEP_FLOWS += ()"),
    Mutation("M455", "Р8-6: ключ читается и при доле франшизы строки 0 (номинальная часть без доли)", "model/cell.py",
             "    for line in shares:\n        if line not in roots:", "    for line in roots:\n        if line not in roots:"),
    Mutation("M461", "Р8-6: ряд H вне памяти оценок шага (повтор оценки из памяти не пишет H квартала)", "model/cell.py",
             "            flows += tuple(nom[2] for nom in nominal.values())", "            flows += ()"),
    Mutation("M462", "Р8-6: λ — связь расходов вместо связи строки (не одно суждение — одно место)", "model/cell.py",
             '    lam_of = {"fees": float(links["fees"]), "insurance": float(links["ins"])}',
             '    lam_of = {"fees": float(links["opex"]), "insurance": float(links["opex"])}'),
    # --- седьмой проход ядра Совкомбанка (core-pass7; tests/support_core_p7.py): Р9-1 — книга страховых К6 несёт корень ρ
    #     номинальной части. M460, M468, M469 спецификации — мутации листа вывода, M467 — контрольной модели; рядом —
    #     M470 (ряд уровня базы — средний остаток вместо конца квартала) и M471 (ряда уровня базы на якоре нет)
    Mutation("M459", "Р9-1: показатель λ вместо 1 − λ у корня ((1 + ρ)^λ)", "model/cell.py",
             "                E[b] *= (1 + roots[b][1][q]) ** (1 - lam)",
             "                E[b] *= (1 + roots[b][1][q]) ** lam"),
    Mutation("M463", "Р9-1: ρ читается годом (year_value: ключи кварталов не читаются)", "model/cell.py",
             "    out = {str(b): (str(line), _series(roots[line], tl)) for b, line in spec.items()",
             "    out = {str(b): (str(line), tuple(Trajectory(roots[line]).year_value(tl.year(q)) for q in range(tl.Q + 1)))"
             " for b, line in spec.items()"),
    Mutation("M464", "Р9-1: корень на весь шаг ((1 + ρ) без степени 1 − λ) — ломает бит в бит при λ = 1", "model/cell.py",
             "                E[b] *= (1 + roots[b][1][q]) ** (1 - lam)",
             "                E[b] *= (1 + roots[b][1][q])"),
    Mutation("M465", "Р9-1: ρ квартала со сдвигом (ρ_(q−1))", "model/cell.py",
             "                E[b] *= (1 + roots[b][1][q]) ** (1 - lam)",
             "                E[b] *= (1 + roots[b][1][q - 1]) ** (1 - lam)"),
    Mutation("M466", "Р9-1: ключ читается по книге без строки — корень чужой строки (комиссий) у книги страхования",
             "model/cell.py",
             "    out = {str(b): (str(line), _series(roots[line], tl)) for b, line in spec.items()\n"
             "           if line in roots and str(b) in driven}",
             "    out = {str(b): (str(line), _series(next(iter(roots.values())), tl)) for b, line in spec.items()\n"
             "           if str(b) in driven}"),
    Mutation("M470", "Р9-1: ряд vol_end_<строка> — средний остаток базы строки (ряд К2) вместо уровня на конец квартала "
             "(правило ρ встало бы на средние)", "model/cell.py",
             "        return {END_FLOWS[line]: self.base_end(p.driven[b][0], E, q) for b, (line, _) in p.driver_roots.items()}",
             "        return {END_FLOWS[line]: self.flows[\"vol_ins\" if line == \"insurance\" else \"vol_fees\"][q]\n"
             "                for b, (line, _) in p.driver_roots.items()}"),
    Mutation("M471", "Р9-1: ряда уровня базы на якоре нет (E_M[D_0] правила ρ не определён)", "model/cell.py",
             "        row.update({END_FLOWS[line]: p.driven[b][0].end0 for b, (line, _) in p.driver_roots.items()})",
             "        pass"),
    # --- восьмой проход ядра Совкомбанка (core-pass8; tests/support_core_p8.py): Р10-5 — франшиза строки и книга К6
    #     формой строки, Р10-6 — гейт funds_cost_to_key на ожидании мира, ключ (3) Р10-1 — средства клиентов без К6.
    #     M478–M480 — мутации листа вывода (файл листа — рядом с копией ядра); M484, M485 спецификации — мутации
    #     контрольной модели (не здесь)
    Mutation("M472", "Р10-5: франшиза при line считает H (форма уровней) — ключ не читается", "model/cell.py",
             "        link_line=lines.get(\"share_nominal\") is not None and form_line(book),",
             "        link_line=False,"),
    Mutation("M473", "Р10-5: g без root_mult (корень слагаемым при multiplicative)", "model/cell.py",
             "        return (1 + wage + lam * (ratio - 1 - wage)) * (1 + root)",
             "        return 1 + wage + root + lam * (ratio - 1 - wage)"),
    Mutation("M474", "Р10-5: Ψ на средних базы (полусумма концов квартала) вместо концов", "model/cell.py",
             "                d_now, d_back = self.base_end(lb, E, q), flows[LAG_END_FLOWS[line]][q - 4]",
             "                d_now, d_back = ((self.base_end(lb, E0, q - 1) + self.base_end(lb, E, q)) / 2,\n"
             "                                 flows[LAG_END_FLOWS[line]][q - 4])"),
    Mutation("M475", "Р10-5: история Ψ = 1 вместо D_x / D_0", "model/cell.py",
             "        hist[PSI_FLOWS[line]] = {x: ends[x] / ends[0] for x in range(-3, 1)}",
             "        hist[PSI_FLOWS[line]] = {x: 1.0 for x in range(-3, 1)}"),
    Mutation("M476", "Р10-5: ряд лага k6_end4 вне STEP_FLOWS (D_(q−4) — от последней оценки шага, а не принятой)",
             "model/cell.py",
             "STEP_FLOWS += tuple(PHI_FLOWS.values()) + tuple(PSI_FLOWS.values()) + tuple(LAG_END_FLOWS.values())",
             "STEP_FLOWS += tuple(PHI_FLOWS.values()) + tuple(PSI_FLOWS.values())"),
    Mutation("M477", "Р10-5: w одного мира (мира-опоры передачи) во всех клетках в g книги К6", "model/cell.py",
             "                psi[line] = flows[PSI_FLOWS[line]][q - 4] * link_growth(d_now / d_back, wage, lam, rho[q], "
             "p.root_mult)",
             "                psi[line] = flows[PSI_FLOWS[line]][q - 4] * link_growth(d_now / d_back, self.wh.wage[q], lam, "
             "rho[q], p.root_mult)"),
    Mutation("M478", "Р10-5, лист: κ при line — правило формы уровней E_M[A_q] / E_M[A_(q−4)] / (1 + w) − 1",
             "data/assumptions/evidence/path/derive_on_engine.py",
             "    if getattr(run.ctx.prep, \"link_line\", False):            # Р10-5: франшиза формой строки",
             "    if False:            # Р10-5: франшиза формой строки"),
    Mutation("M479", "Р10-5, лист: ρ при line — квартальное правило цепи", "data/assumptions/evidence/path/derive_on_engine.py",
             "    if getattr(prep, \"k6_line\", None) is not None:          # Р10-5: книги К6 формой строки",
             "    if False:          # Р10-5: книги К6 формой строки"),
    Mutation("M480", "Р10-13, лист: на концах связок судится только правило против записи (невязка уровня не судится)",
             "data/assumptions/evidence/path/derive_on_engine.py",
             "\"ok\": rc <= KAPPA_END_TOL and md <= LEVEL_END_TOL, \"rows\": rows}   # Р10-13: судятся оба",
             "\"ok\": rc <= KAPPA_END_TOL, \"rows\": rows}   # Р10-13: судятся оба"),
    Mutation("M481", "Р10-6: funds_cost_to_key при world_expectation — ожидание отношений вместо отношения ожиданий",
             "model/levels.py",
             "                num += pr[x.key] * i_x\n                den += pr[x.key] * b_x",
             "                num += pr[x.key] * i_x / b_x\n                den += pr[x.key]"),
    Mutation("M482", "Р10-6: scope книги не читается (модальная клетка при world_expectation)", "model/levels.py",
             "    scope = str(cfg.get(\"scope\", MODAL_CELL) if scope is None else scope)",
             "    scope = str(MODAL_CELL if scope is None else scope)"),
    # проход ядра 9 (Р11-2): исключение книг К6 — в одной функции model.book.client_books (её же читают гейты)
    Mutation("M483", "Р10-1, ключ (3): client_funds не исключает книги К6", "model/book.py",
             "    return tuple(b for b in roles.funds if b not in drivers)",
             "    return roles.funds"),
    # --- девятый проход ядра Совкомбанка (core-pass9; tests/support_core_p9.py): Р11-1 — доля сжатия книги между мирами,
    #     Р11-2 — опт и слово funds на средствах клиентов, Р11-3 — НДУ в реальных рублях. M500 — мутация листа бэктеста книг;
    #     M498, M499 спецификации — мутации контрольной модели (не здесь)
    Mutation("M486", "Р11-1: доля только в стационаре и цели ставки — шаг клетки без доли", "model/cell.py",
             "                if b in p.phi_share:            # Р11-1: доля сжатия книги между мирами (в мире-опоре H — ноль)\n"
             "                    s -= p.phi_share[b] * (ref - self.wh.ref(spec[\"ref\"])[q])\n",
             ""),
    Mutation("M487", "Р11-1: в стационаре Nss доля только у активов (пассивы вне пары без доли)", "model/nii.py",
             "            total -= w[b] * self._shared(b, float(spec[\"beta\"]) * ref + self.s_lt[b] - sl[b], ref, ref_world)",
             "            total -= w[b] * (float(spec[\"beta\"]) * ref + self.s_lt[b] - sl[b])"),
    Mutation("M488", "Р11-1: пара средств ФЛ в стационаре без доли", "model/nii.py",
             "        cost_rc = self._shared(rc, float(books[rc][\"beta\"]) * ref_rc + self.s_lt[rc] - sl[rc], ref_rc, ref_world)\n"
             "        cost_rt = self._shared(rt, float(books[rt][\"beta\"]) * ref_rt + self.s_lt[rt] - sl[rt], ref_rt, ref_world)",
             "        cost_rc = float(books[rc][\"beta\"]) * ref_rc + self.s_lt[rc] - sl[rc]\n"
             "        cost_rt = float(books[rt][\"beta\"]) * ref_rt + self.s_lt[rt] - sl[rt]"),
    Mutation("M489", "Р11-1: доля × (ref_W − ref_N) вместо ref_H в стационаре", "model/nii.py",
             "            value -= self.share[b] * (ref - self.ref_lt[ref_world][self.books[b][\"ref\"]])",
             "            value -= self.share[b] * (ref - self.ref_lt[\"N\"][self.books[b][\"ref\"]])"),
    Mutation("M490", "Р11-1: LT-спред гейта пола без доли (прежняя форма)", "model/nii.py",
             "                row[world] = self._shared(b, s, rates[spec[\"ref\"]], ref_world)",
             "                row[world] = s"),
    Mutation("M491", "Р11-1: цель ставки К4 (target_rates) без доли", "model/cell.py",
             "            if b in p.phi_share:                # Р11-1\n"
             "                s -= p.phi_share[b] * (ref - self.wh.ref(spec[\"ref\"])[q])\n",
             ""),
    Mutation("M492", "Р11-2: база структурного опта с книгой К6 при funds_scope: clients", "model/cell.py",
             "wh_base = p.wh_to_funds * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))",
             "wh_base = p.wh_to_funds * funds"),
    Mutation("M493", "Р11-2: якорь wholesale_to_funds с книгой К6 при clients", "model/book.py",
             "    funds_total = sum(af.balances[b] for b in funds_books(roles, data))",
             "    funds_total = sum(af.balances[b] for b in roles.funds)"),
    Mutation("M494", "Р11-2: строка баланса без книги К6 (тождество баланса)", "model/cell.py",
             "        fixed_liab = funds + OL + DP + p.af.at1 + p.af.nci",
             "        fixed_liab = funds_w + OL + DP + p.af.at1 + p.af.nci"),
    Mutation("M495", "Р11-3: доля nci_share читается при nci_real (терминал и stress_sign — долей)", "model/cell.py",
             "        nci_share=float(book.get(\"pnl.nci_share\")) if nci_q is None else 0.0,",
             "        nci_share=float(book.get(\"pnl.nci_share\")),"),
    Mutation("M496", "Р11-3: НДУ квартала без индекса цен мира", "model/cell.py",
             "ni - p.nci_q[(year, h)] * idx", "ni - p.nci_q[(year, h)]"),
    Mutation("M497", "Р11-3: блок К-Т без −NCI_L в m_L", "model/valuation.py",
             "        m_l -= nci_l", "        pass"),
    Mutation("M500", "Р11-1, лист: бэктест книг на наклонах совместного подбора вместо наклонов ядра",
             "data/assumptions/evidence/nii/backtest_books.py",
             "    a, rho, tr = model_slopes(book, facts)\n",
             "    a, rho, tr = model_slopes(book, facts)\n    a = {b: float(panel.joint[b][\"a\"]) for b in BOOKS}\n"),
    # проверка прохода 9 (core9-verify): экземпляры слова funds, которых книга дерева не трогает (t_p9_funds,
    # check_funds_memo_and_link_base)
    Mutation("M501", "Р11-2: база опта ветви памяти стороны средств с ведомыми книгами К6 — со всеми средствами",
             "model/cell.py",
             "                    wh_base = p.wh_to_funds * (funds if p.wh_corp is None else FR + sum([E[b] for b in p.wh_corp]))",
             "                    wh_base = p.wh_to_funds * funds"),
    Mutation("M502", "Р11-2: конец квартала базы строки словом funds (base_end) — все книги средств", "model/cell.py",
             "            return sum([E[b] for b in (roles.funds if self.p.funds_words is None else self.p.funds_words)])",
             "            return sum([E[b] for b in roles.funds])"),
    Mutation("M503", "Р11-2: конец якоря истории базы связи link_base funds — все книги средств", "model/cell.py",
             "\"funds\": sum(af.balances[b] for b in words),", "\"funds\": sum(af.balances[b] for b in roles.funds),"),
    Mutation("M504", "Р11-2: база объёма квартала link_base funds — начало квартала со всеми книгами ЮЛ", "model/cell.py",
             "                    vol = (st.FR + sum(E0[b] for b in (roles.corp_funds if p.wh_corp is None else p.wh_corp))",
             "                    vol = (st.FR + sum(E0[b] for b in roles.corp_funds)"),
]


def build_mutant(mutation: Mutation, target: Path) -> Path:
    """Копия `model/` в `target` с одной правкой."""
    dest = target / "model"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(ROOT / "model", dest, ignore=shutil.ignore_patterns("__pycache__"))
    path = target / mutation.path
    if not path.exists():                   # мутация вне ядра (лист вывода): файл — рядом с копией ядра, по своему пути
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / mutation.path, path)
    source = path.read_text(encoding="utf-8")
    if mutation.find not in source:
        raise AssertionError(f"{mutation.id}: строка для мутации не найдена в {mutation.path} — "
                             "мутацию надо перенацелить, а не удалить")
    path.write_text(source.replace(mutation.find, mutation.replace, 1), encoding="utf-8", newline="\n")
    return target


def run_checks_in(target: Path | None, timeout: float = 900.0, only: Iterable[str] | str | None = None) -> dict[str, str]:
    """Проверки подпроцессом; `target` — каталог мутанта (None — подлинное ядро). Имя → «ok» | причина.
    `only` — только названные проверки (перечень имён: быстрый круг `ops/tools/pmut.py`) либо строка — начало имён
    проверок (прогон выбранных мутантов одной темы); тест мутаций гоняет все."""
    env = dict(os.environ)
    paths = ([str(target)] if target is not None else []) + [str(ROOT)]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    names = [] if only is None else [f"--only={only}"] if isinstance(only, str) else ["--only", ",".join(only)]
    out = subprocess.run([sys.executable, "-B", "-m", "tests.mutations", "--check", *names], cwd=str(target or ROOT),
                         env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    for line in reversed(out.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return {"_crash": (out.stderr or out.stdout)[-800:]}


# ------------------------------------------------------------------ проверки (в подпроцессе)


def _checks() -> dict[str, Callable[[], None]]:
    import copy
    import math
    import random

    import model  # noqa: F401  — копия мутанта первой в sys.path
    from model import uncertainty as U
    from model.book import book_from_dict
    from model.cell import run_cell
    from model.checks import check_invariants
    from model.credit import kappa_addon
    from model.grid import DividendRecord, LiveInputs, cap_shift, make_context, run_grid, sensitivity_overrides
    from model.paths import Trajectory
    from model.worlds import BASE_WORLD
    from tests.support_core import fixture_book, fixture_facts

    book, facts = fixture_book(), fixture_facts()
    base = run_grid(book, facts)
    tl = base.ctx.timeline

    def close(a: float, b: float, rel: float = 1e-9, abs_: float = 1e-9) -> bool:
        return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))

    def invariants() -> None:
        fired = [f.name for f in check_invariants(base) if f.fired]
        assert not fired, fired

    def llp_shift_exact() -> None:
        x = 0.001
        shifted = run_grid(book.with_overrides(sensitivity_overrides(book, "cor", x)), facts)
        a, b = base.cell("M", "downturn", "strict"), shifted.cell("M", "downturn", "strict")
        for q in range(1, tl.Q + 1):
            expect = x * a.quarters["loans_ac_avg"][q] * tl.d(q) / 365
            assert close(b.quarters["llp"][q] - a.quarters["llp"][q], expect), q

    def interest_legs_simple() -> None:
        c = base.cell("H", "norm", "schedule")
        roles = base.ctx.prep.roles
        for q in range(1, tl.Q + 1):
            inc = sum(c.books[b]["rate"][q] * c.books[b]["avg"][q] for b in roles.assets) * tl.d(q) / 365
            exp = sum(c.books[b]["rate"][q] * c.books[b]["avg"][q] for b in roles.liabilities) * tl.d(q) / 365
            assert close(inc, c.quarters["int_income"][q]) and close(exp, c.quarters["int_expense"][q]), q
            nii = inc - exp - c.quarters["dia"][q] + c.quarters["overlay"][q]
            assert close(nii, c.quarters["nii"][q]), q

    def kappa_zero_in_n() -> None:
        p = base.ctx.prep
        n = base.ctx.worlds[BASE_WORLD].real_key
        assert all(v == 0.0 for v in kappa_addon(p.kappa, p.lag, n, n, tl.Q))

    def dps_is_pool_over_issued() -> None:
        n_iss = facts.need("shares", "issued_total")
        n_out = facts.need("shares", "outstanding_total")
        payout = Trajectory(book.get("dividends.policy.payout"))
        for c in base.cells:
            for d in c.decisions:
                if d.source == "model" and not d.cut and d.catch == 0 and d.excess == 0:
                    assert close(d.dps, payout.year_value(d.year) * d.base * 1000 / n_iss, rel=1e-9), d.year
                    assert close(d.div, d.dps * n_out / 1000), d.year

    def exdate_jump_with_governance() -> None:
        comp = [{"id": "t", "name": "т", "value": 0.05, "sign": 1, "basis": "проверка"}]
        b2 = book.with_overrides({"valuation.governance.discount": 0.05,
                                  "valuation.governance.components": comp})
        agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
        v = tl.end(agm_q) + timedelta(days=20)
        prices = {str(t): float(x) for t, x in book.get("meta.market_price").items()}
        out = []
        for ex in (v, v + timedelta(days=1)):
            rec = DividendRecord(year=tl.anchor_year, dps=40.0, status="declared", record_date=ex,
                                 last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                                 sources=("проверка",))
            live = LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=(rec,))
            out.append(run_grid(b2, facts, live).point)
        assert close(out[0] - out[1], -40.0, abs_=1e-6), out

    def h_world_independent_of_phi() -> None:
        ref = str(book.get("nii.transmission.reference_world"))
        other = run_grid(book.with_overrides({"nii.transmission.target": 0.12}), facts)
        assert not close(other.ctx.transmission.phi, base.ctx.transmission.phi)
        a, b = base.cell(ref, "norm", "schedule"), other.cell(ref, "norm", "schedule")
        for q in range(1, tl.Q + 1):
            assert close(a.quarters["nii"][q], b.quarters["nii"][q], rel=1e-12), q

    def cor_path_bridged_once() -> None:
        b_cor = facts.need("bridge_mgmt_ifrs", "cor.value")
        assert facts.plain("bridge_mgmt_ifrs", "cor.method") == "additive"
        assert book.get("regimes.cor_basis") == "mgmt"
        for r in book.get("regimes.ids"):
            t = Trajectory(book.get(f"regimes.{r}.cor"))
            c = base.cell(BASE_WORLD, r, "schedule")
            for q in range(1, tl.Q + 1):
                y, n = tl.year(q), tl.h(q)
                assert close(c.quarters["cor"][q], t.value(y, n) + b_cor, abs_=1e-12), (r, q)

    def deductions_scale_with_rwa() -> None:
        """Ded20 и Ded11 = вычеты якоря × RWA_q / RWA_0 (М§4.11)."""
        ded20 = float(book.get("capital.n20.deductions_anchor"))
        ded11 = float(book.get("capital.n11.deductions_anchor"))
        c = base.cell("H", "norm", "upper")
        rwa0 = c.quarters["rwa"][0]
        assert c.quarters["rwa"][tl.Q] > 1.5 * rwa0
        for q in range(0, tl.Q + 1):
            assert close(c.quarters["ded20"][q], ded20 * c.quarters["rwa"][q] / rwa0), q
            assert close(c.quarters["ded11"][q], ded11 * c.quarters["rwa"][q] / rwa0), q

    def unaudited_by_calendar() -> None:
        cut = [int(x) for x in book.get("capital.n11.audit_cutoffs")]
        c = base.cell("H", "norm", "schedule")
        hist = base.ctx.prep.hist["ni_sh"]
        ni = {q: (c.quarters["ni_sh"][q] if q >= 1 else hist[q]) for q in range(-7, tl.Q + 1)
              if q >= 1 or q in hist}
        for q in range(1, tl.Q + 1):
            total, j = 0.0, q
            while True:
                total += ni[j]
                j -= 1
                if tl.h(j) in cut:
                    break
            assert close(c.quarters["e_unaudited"][q], total), q

    def unaudited_loss_in_base_capital() -> None:
        """K11 = BVreg − max(E, 0) − Ded11: убыток неаудированного периода уменьшает базовый капитал сразу,
        исключается только прибыль; N11* возвращает в капитал ровно исключённое (М§4.11, §7)."""
        from model.capital import n11_audited
        f = float(book.get("capital.n20.fvoci_recognition"))
        losses = 0
        for c in base.cells:
            q_ = c.quarters
            for q in range(1, tl.Q + 1):
                e = q_["e_unaudited"][q]
                bvreg = q_["bv"][q] + q_["dpreg"][q] - (1 - f) * q_["reserve"][q]
                assert close(q_["k11"][q], bvreg - (e if e > 0 else 0.0) - q_["ded11"][q]), (c.label, q)
                losses += e < 0
            assert close(c.n11_star, q_["n11"][tl.Q] + max(q_["e_unaudited"][tl.Q], 0.0) / q_["rwa"][tl.Q]), c.label
        assert losses > 0                                   # в клетках кризиса есть квартал с убытком
        assert close(n11_audited(900.0, -50.0, 10000.0, 0.001, 0.002), 0.09 + 0.001 - 0.002, abs_=1e-15)
        assert close(n11_audited(900.0, 50.0, 10000.0, 0.001, 0.002), 0.095 + 0.001 - 0.002, abs_=1e-15)

    def dividend_bound_is_the_headroom() -> None:
        """Инвариант `dividend_bounds`: вся выплата года (базовая, догоняющая, доля избытка) не больше запаса
        капитала ступени; решение с выплатой на 1 млрд ₽ сверх запаса он называет (М§5.3 п. 4, §14.1)."""
        from dataclasses import replace
        cell = next(c for c in base.cells if any(d.source == "model" and d.excess > 0 for d in c.decisions))
        d = next(d for d in cell.decisions if d.source == "model" and d.excess > 0)
        h = d.headroom[d.step]
        over = replace(d, excess=d.excess + (h - d.div) + 1.0, div=h + 1.0)
        changed = replace(cell, decisions=tuple(over if x is d else x for x in cell.decisions))
        bad = replace(base, cells=tuple(changed if c is cell else c for c in base.cells))
        found = next(f for f in check_invariants(bad) if f.name == "dividend_bounds")
        assert found.fired, found.message

    def probabilities_are_not_negative() -> None:
        """Таблица вероятностей с суммой 1 и отрицательным весом: инвариант `probabilities` срабатывает на
        прогоне, схема книги — до расчёта; ε и λ вне [0; 1] схема тоже не принимает (М§3.4, §5.3, §9)."""
        from dataclasses import replace
        from model.book_schema import BookError
        layer = base.layers["analytical"]
        (k1, p1), (k2, p2) = list(layer.prob.items())[:2]
        prob = {**layer.prob, k1: -p1, k2: p2 + 2 * p1}
        bad = replace(base, layers={**base.layers, "analytical": replace(layer, prob=prob)})
        assert next(f for f in check_invariants(bad) if f.name == "probabilities").fired
        wp = {w: float(v) for w, v in book.get("joint.world_prob").items()}
        a, b = list(wp)[:2]
        moved = {**wp, a: -0.1, b: wp[a] + wp[b] + 0.1}
        for override in ({"joint.world_prob": moved}, {"dividends.excess.epsilon": 1.25},
                         {"joint.own_macro_confidence": 1.5}):
            try:
                book.with_overrides(override)
            except BookError:
                continue
            raise AssertionError(f"схема приняла {override}")

    def agm_quarter_neutral_for_capital() -> None:
        agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
        prices = {str(t): float(x) for t, x in book.get("meta.market_price").items()}
        v = base.ctx.live.valuation_date
        k20 = []
        for dps in (30.0, 60.0):
            rec = DividendRecord(year=tl.anchor_year, dps=dps, status="declared", record_date=None,
                                 last_buy_date=None, ex_date=None, pay_date=None, sources=("проверка",))
            live = LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=(rec,))
            k20.append(run_cell(make_context(book, facts, live), "H", "norm", "schedule").quarters["k20"][agm_q])
        assert close(k20[0], k20[1], rel=1e-12), k20

    def apu_cap_per_observation() -> None:
        from model.book import book_from_dict
        import copy
        data = copy.deepcopy(dict(book.source))
        limit = float(book.get("joint.regime_update.max_shift_pp"))
        prior = {r: float(book.get(f"joint.regime_prob.{r}")) for r in book.get("regimes.ids")}
        obs = [{"period": tl.period(q), "cor": 0.045, "nim": None, "se_cor": 0.0, "se_nim": None,
                "basis": "mgmt"} for q in (1, 2)]
        data["joint"]["regime_update"]["observations"] = obs[:1]
        one = make_context(book_from_dict(data, facts=facts), facts).posterior
        assert max(abs(one[r] - prior[r]) for r in prior) <= limit + 1e-12
        data["joint"]["regime_update"]["observations"] = obs
        two = make_context(book_from_dict(data, facts=facts), facts).posterior
        assert max(abs(two[r] - one[r]) for r in prior) <= limit + 1e-12
        assert max(abs(two[r] - prior[r]) for r in prior) > limit + 1e-9

    prices = {str(t): float(x) for t, x in book.get("meta.market_price").items()}

    def live_at(v, register=()) -> LiveInputs:
        return LiveInputs(valuation_date=v, prices=prices, price_dates={t: v for t in prices}, register=register)

    def ddm_ri_mid_quarter() -> None:
        """Дата оценки внутри квартала (0 < e < 1): DDM = RI и тождества держатся."""
        run = run_grid(book, facts, live_at(tl.start(2) + timedelta(days=40)))
        assert 0 < run.ctx.clock.elapsed < 1
        fired = [f.name for f in check_invariants(run) if f.fired]
        assert not fired, fired

    def lhs_order() -> None:
        """LHS в порядке 850oa (М§10): перестановки всех осей, затем по прогонам i и осям j."""
        n, m, seed = 6, 3, 11
        rng = random.Random(seed)
        perms = []
        for _ in range(m):
            p_ = list(range(n))
            rng.shuffle(p_)
            perms.append(p_)

        def tri(u: float) -> float:
            return math.sqrt(2 * u) - 1 if u < 0.5 else 1 - math.sqrt(2 * (1 - u))

        want = [[tri((perms[j][i] + rng.random()) / n) for j in range(m)] for i in range(n)]
        assert U.draw_points(n, m, seed) == want

    def quantile_type_7() -> None:
        xs = [1.0, 2.0, 4.0, 8.0, 16.0]
        for q, want in ((0.1, 1.4), (0.25, 2.0), (0.5, 4.0), (0.9, 12.8)):
            assert close(U.quantile(xs, q), want), (q, U.quantile(xs, q))

    def quarter_end_continuity() -> None:
        """Конец квартала ГОСА при записи реестра: E − 1, E, E + 1 — перекат, не DPS (М§0.2, §8.1)."""
        agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
        end = tl.end(agm_q)
        ex = end + timedelta(days=20)
        rec = DividendRecord(year=tl.anchor_year, dps=40.0, status="declared", record_date=ex,
                             last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                             sources=("проверка",))
        pts = [run_grid(book, facts, live_at(end + timedelta(days=d), (rec,))).point for d in (-1, 0, 1)]
        assert abs(pts[1] - pts[0]) < 1e-3 * pts[1] and abs(pts[2] - pts[1]) < 1e-3 * pts[1], pts

    def sigma0_from_year() -> None:
        """s_b(q) = путь + σ0 × [lt_shift] × [Y(q) ≥ nii.sigma0_from] (М§4.4)."""
        tr = base.ctx.transmission
        y0 = int(book.get("nii.sigma0_from"))
        assert tr.sigma0 != 0 and tr.sigma0_liab != 0
        for b, spec in book.get("nii.books").items():
            t = Trajectory(spec["spread"])
            sigma = tr.sigma0 if spec["side"] == "asset" else -tr.sigma0_liab       # у пассивов знак обратный
            for q in range(tl.Q + 1):
                y = tl.year(q)
                want = t.value(y, tl.h(q)) + (sigma if spec.get("lt_shift") and y >= y0 else 0.0)
                assert close(base.ctx.prep.spreads[b][q], want, abs_=1e-15), (b, q)

    def epsilon_ramp() -> None:
        """ε_Y = ε × min(1, (Y − from + 1) / ramp_years) на избытке над требованием (М§5.3 п. 4)."""
        eps = float(book.get("dividends.excess.epsilon"))
        start = int(book.get("dividends.excess.from_profit_year"))
        ramp = int(book.get("dividends.excess.ramp_years"))
        assert ramp > 1
        seen = 0
        for c in base.cells:
            for d in c.decisions:
                if d.source != "model":
                    continue
                e_y = eps * min(1.0, (d.year - start + 1) / ramp) if d.year >= start else 0.0
                want = e_y * max(0.0, d.headroom[d.step] - d.base_div - d.catch)
                assert close(d.excess, want, abs_=1e-9), (c.label, d.year)
                seen += d.year == start and want > 0
        assert seen

    def misc_quarter_profile() -> None:
        """«Прочее» квартала = годовая сумма × индекс цен × доля квартала (М§4.7)."""
        shares = {h: float(book.get(f"other.misc_quarter_shares.{h}")) for h in (1, 2, 3, 4)}
        assert len(set(shares.values())) > 1
        t = Trajectory(book.get("other.misc_net_real"))
        c = base.cell("H", "norm", "schedule")
        idx = base.ctx.worlds["H"].price_index
        for q in range(1, tl.Q + 1):                       # и в году якоря: остатком год не закрывается (М§0.3)
            y, h = tl.year(q), tl.h(q)
            annual = sum(t.value(y, k) for k in (1, 2, 3, 4)) / 4
            assert close(c.quarters["misc"][q], annual * shares[h] * idx[q]), q

    def apu_layer_average_is_observation() -> None:
        """В квартале наблюдения (se 0) среднее клеток режима слоя «свой взгляд» = наблюдению (М§12)."""
        data = copy.deepcopy(dict(book.source))
        data["joint"]["regime_update"]["observations"] = [
            {"period": tl.period(1), "cor": None, "nim": 0.058, "se_cor": None, "se_nim": 0.0, "basis": "mgmt"}]
        b2 = book_from_dict(data, facts=facts)
        run = run_grid(b2, facts)
        eng = run.ctx.bridge.to_engine_nim(0.058)
        pw = {w: float(b2.get(f"joint.world_prob.{w}")) for w in b2.get("worlds.ids")}
        table = b2.get("joint.reg_prob_given_regime")
        for r in b2.get("regimes.ids"):
            avg = sum(pw[c.world] * float(table[r][c.scenario]) * c.quarters["nim"][1]
                      for c in run.cells if c.regime == r)
            assert close(avg, eng, abs_=1e-12), (r, avg, eng)

    # ---------------------------------------------------------------- волна W2: закрытые формулы из книги и фактов

    def terminal_closed_form() -> None:
        """NI_T+1 = [PBT_L (1 + g_T) − Y_X] (1 − τ_eff)(1 − nci); Y_X — смесь бумаг и ликвидности, пока минимум
        ликвидности не связывает (порог H* = HLA / (1 − m)), дальше — ставка опта; недостаток капитала сначала
        гасит добор опта (М§7). Минимум поднят так, что на конце сетки он связывает."""
        Q, L = tl.Q, tl.last_year
        lm = 0.30
        run = run_grid(book.with_overrides({"volumes.liquid_min_share": lm}), facts)
        sec = float(book.get("volumes.securities_share_of_liquid"))
        wf = float(book.get("volumes.wholesale_to_funds"))
        nci = float(book.get("pnl.nci_share"))
        cpn = facts.need("capital", "at1.coupon_annual")
        above = repaid = 0
        for c in list(base.cells) + list(run.cells):
            m = lm if c in run.cells else float(book.get("volumes.liquid_min_share"))
            la = c.quarters["securities"][Q] + c.quarters["liquidity"][Q]
            h_star = max(0.0, la - m * c.quarters["assets"][Q]) / (1 - m)
            wt = max(0.0, c.quarters["wholesale"][Q] - wf * c.quarters["funds"][Q])
            y_bal = sec * c.books["securities"]["rate"][Q] + (1 - sec) * c.books["liquidity"]["rate"][Q]
            c_wh = c.books["wholesale"]["rate"][Q]
            x = c.x_t
            if x > 0:
                y_x = y_bal * min(x, h_star) + c_wh * max(0.0, x - h_star)
                above += x > h_star
            else:
                y_x = -(c_wh * min(-x, wt) + y_bal * max(0.0, -x - wt))
                repaid += wt > 1e-6
            pbt_l = sum(c.quarters["pbt"][q] for q in range(1, Q + 1) if tl.year(q) == L)
            ni = (pbt_l * (1 + c.g_t) - y_x) * (1 - c.quarters["tau_eff"][Q]) * (1 - nci)
            ci = ni - cpn * (1 - c.quarters["tau_stat"][Q])
            assert close(c.roe_t_raw * c.bv_star, ci, rel=1e-10), c.label
        assert above > 0 and repaid > 0                     # есть избыток сверх порога и недостаток с добором опта
        from model.valuation import excess_income           # сверх порога избыток гасит опт
        assert close(excess_income(100.0, 0.08, 0.15, 40.0), 0.08 * 40.0 + 0.15 * 60.0)
        assert close(excess_income(100.0, 0.08, 0.15, 40.0, 0.2), 0.08 * 50.0 + 0.15 * 50.0)     # H* = HLA / (1 − m)
        assert close(excess_income(-100.0, 0.08, 0.15, 0.0), -8.0)
        assert close(excess_income(-100.0, 0.08, 0.15, 0.0, 0.2, 30.0), -(0.15 * 30.0 + 0.08 * 70.0))

    def dia_leg_from_book() -> None:
        """Взносы АСВ = nii.dia_rate × средние средства ФЛ × d/365 — ставка из книги, не из ряда клетки."""
        rate = float(book.get("nii.dia_rate"))
        assert rate > 0
        c = base.cell("H", "norm", "schedule")
        for q in range(1, tl.Q + 1):
            avg = (c.quarters["funds_retail"][q - 1] + c.quarters["funds_retail"][q]) / 2
            assert close(c.quarters["dia"][q], rate * avg * tl.d(q) / 365), q

    def kappa_lag_closed_form() -> None:
        """κ × max(0, rr_W,(q−L) − rr_N,(q−L)) на синтетических путях с разностью в первые L кварталов."""
        rr_w = [0.0, 0.09, 0.08, 0.07, 0.06, 0.05, 0.02]
        rr_n = [0.0, 0.04, 0.05, 0.06, 0.07, 0.03, 0.03]
        want = (0.0, 0.0, 0.0, 0.5 * 0.05, 0.5 * 0.03, 0.5 * 0.01, 0.0)
        got = kappa_addon(0.5, 2, rr_w, rr_n, 6)
        assert all(close(a, b, abs_=1e-15) for a, b in zip(got, want)), got

    def cor_includes_kappa() -> None:
        """CoR клетки = путь режима через мост + κ-добавка мира (без наблюдений δ = 0)."""
        p = base.ctx.prep
        seen = 0.0
        for w in book.get("worlds.ids"):
            kap = kappa_addon(p.kappa, p.lag, base.ctx.worlds[w].real_key, base.ctx.worlds[BASE_WORLD].real_key, tl.Q)
            c = base.cell(w, "norm", "schedule")
            for q in range(1, tl.Q + 1):
                assert close(c.quarters["cor"][q], p.regimes["norm"].cor_engine[q] + kap[q], abs_=1e-12), (w, q)
            seen = max(seen, max(kap))
        assert seen > 0

    def first_dy_from_anchor_curve() -> None:
        """Фонд FVOCI первого квартала: Δy₁ = узел пути мира − узел кривой якоря (факт), не разность пути."""
        p = base.ctx.prep
        node = facts.need("capital", f"ofz_curve_anchor.{p.fvoci_tenor.split('_')[1].rstrip('y')}")
        r0 = facts.need("capital", "fvoci_reserve")
        for w in book.get("worlds.ids"):
            c = base.cell(w, "norm", "schedule")
            dy = base.ctx.worlds[w].ofz[p.fvoci_tenor][1] - node
            avg = p.fvoci_share * c.books["securities"]["avg"][1]
            want = r0 * (1 - 0.25 / p.fvoci_maturity) - p.fvoci_duration * dy * avg * (1 - c.quarters["tau_stat"][1])
            assert close(c.quarters["reserve"][1], want, rel=1e-10), w
            assert abs(dy - (base.ctx.worlds[w].ofz[p.fvoci_tenor][1] - base.ctx.worlds[w].ofz[p.fvoci_tenor][0])) > 1e-6

    def la_minimum_binds() -> None:
        """Где минимум связывает, LA = liquid_min_share × активы, а недостающее добрано оптом (М§4.10)."""
        lm = 0.30
        run = run_grid(book.with_overrides({"volumes.liquid_min_share": lm}), facts)
        c = run.cell("M", "soft", "schedule")
        extra = [q for q in range(1, tl.Q + 1) if c.quarters["wholesale_extra"][q] > 0]
        assert extra
        for q in extra:
            la = c.quarters["securities"][q] + c.quarters["liquidity"][q]
            assert close(la, lm * c.quarters["assets"][q], rel=1e-12), q

    def fvc_reference_regime() -> None:
        """FVC = factor × (CoR_corporate − CoR_ref) × Ē^СС × d/365; опора — путь режима credit.fv_loans_ref
        через мост: в клетке режима-опоры мира N — ноль, в кризисе — расход (М§4.6)."""
        from model.credit import regime_cor_engine
        ref = str(book.get("credit.fv_loans_ref"))
        factor = float(book.get("credit.fv_loans_factor"))
        assert factor > 0
        cor_ref = regime_cor_engine(book, base.ctx.bridge, ref, tl)
        assert all(v == 0.0 for v in base.cell(BASE_WORLD, ref, "schedule").quarters["fvc"][1:])
        for c in (base.cell("M", "crisis", "strict"), base.cell("H", "soft", "upper")):
            for q in range(1, tl.Q + 1):
                want = factor * (c.quarters["cor"][q] - cor_ref[q]) * c.quarters["loans_fv_avg"][q] * tl.d(q) / 365
                assert close(c.quarters["fvc"][q], want, rel=1e-9, abs_=1e-12), (c.label, q)
        shock = base.ctx.prep.regimes["crisis"].shock_year
        assert sum(base.cell(BASE_WORLD, "crisis", "schedule").quarters["fvc"][q] for q in tl.quarters_of_year(shock)) > 0

    def governed(g: float):
        comp = [{"id": "t", "name": "т", "value": g, "sign": 1, "basis": "проверка"}]
        return book.with_overrides({"valuation.governance.discount": g, "valuation.governance.components": comp})

    def pending_dividend_without_discount() -> None:
        """До E_qA объявленный дивиденд внутри V0, но вне дисконта: цена слоя = [(V0 − D)(1 − g) + D] / N,
        и на E_qA точка меняется на перекат, не на g × DPS (М§8.2)."""
        g, dps = 0.10, 40.0
        b2 = governed(g)
        agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
        end = tl.end(agm_q)
        ex = end + timedelta(days=20)
        rec = DividendRecord(year=tl.anchor_year, dps=dps, status="declared", record_date=ex,
                             last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                             sources=("проверка",))
        before, on = (run_grid(b2, facts, live_at(end + timedelta(days=d), (rec,))) for d in (-1, 0))
        amount = dps * before.shares_out / 1000
        lay = before.layers["analytical"]
        assert close(lay.price, ((lay.v0 - amount) * (1 - g) + amount) * 1000 / before.shares_out, rel=1e-12)
        assert abs(on.point - before.point) < 0.2 * g * dps, (before.point, on.point)

    def roll_is_end_of_day() -> None:
        """На E_q и S_(q+1) точка одна и та же: перекат и τ на одной линейке (М§0.2)."""
        end = tl.end(2)
        a, b = (run_grid(book, facts, live_at(end + timedelta(days=d))).point for d in (0, 1))
        assert close(a, b, rel=1e-12), (a, b)

    def observation(period: str, cor: float, **extra) -> dict:
        return {"period": period, "cor": cor, "nim": None, "se_cor": 0.0, "se_nim": None, "basis": "mgmt", **extra}

    def with_observations(obs: list, **over):
        return make_context(book.with_overrides({"joint.regime_update.observations": obs, **over}), facts)

    def apu_window() -> None:
        """Фильтр читает только последние window_obs наблюдений; априорные — базовые (М§12)."""
        n = int(book.get("joint.regime_update.window_obs"))
        obs = [observation(tl.period(q), v) for q, v in zip(range(1, n + 2), (0.010, 0.019, 0.013, 0.022, 0.016, 0.03))]
        full, last = with_observations(obs).posterior, with_observations(obs[1:]).posterior
        assert all(close(full[r], last[r], abs_=1e-15) for r in full), (full, last)

    def apu_frozen_expectations() -> None:
        """Наблюдение квартала якоря судится против замороженных ожиданий записи (М§12)."""
        regimes = list(book.get("regimes.ids"))
        mu = dict(zip(regimes, (0.011, 0.013, 0.016, 0.0165)))
        value = 0.0125
        ctx = with_observations([observation(tl.anchor, value, mu_cor=mu)])
        sigma = float(book.get("joint.regime_update.observables.cor.sigma_pp"))
        prior = {r: float(book.get(f"joint.regime_prob.{r}")) for r in regimes}
        like = {r: math.exp(-0.5 * (value - mu[r]) ** 2 / sigma ** 2) for r in regimes}
        norm = sum(prior[r] * like[r] for r in regimes)
        want = cap_shift(prior, {r: prior[r] * like[r] / norm for r in regimes},
                         float(book.get("joint.regime_update.max_shift_pp")))
        assert all(close(ctx.posterior[r], want[r], abs_=1e-12) for r in regimes), (ctx.posterior, want)

    def crisis_skip_is_not_a_cut() -> None:
        """Отмена выплаты в год шока — crisis_skip, не «капитал урезал выплату» (М§5.3 п. 5); год шока —
        год якоря + shock_year_offset."""
        shock = tl.anchor_year + int(book.get("regimes.crisis.shock_year_offset"))
        seen = 0
        for c in base.cells:
            for d in c.decisions:
                if d.source == "crisis_skip":
                    assert d.cut is False and "dividend_cut" not in d.flags and d.year + 1 == shock, (c.label, d.year)
                    seen += 1
        assert seen == sum(1 for c in base.cells if c.regime == "crisis")

    def sigma0_split_closed_form() -> None:
        """σ0_A = split × Δ0 / Σ a_b (активы с lt_shift); Nss(H, 0) = цель при любой доле (М§4.5)."""
        from model.book import anchor_facts, book_roles
        from model.nii import nss_value
        books = book.get("nii.books")
        af = anchor_facts(facts, books)
        roles = book_roles(books)
        iea = sum(af.balances[b] for b in roles.assets)
        a_sum = sum(af.balances[b] / iea for b in roles.assets if books[b].get("lt_shift"))
        ref = str(book.get("nii.transmission.reference_world"))
        tr = base.ctx.transmission
        delta0 = tr.target_eng - nss_value(book, facts, ref, 0.0, 0.0, 0.0)
        split = float(book.get("nii.sigma0_split"))
        assert 0 < split < 1
        assert close(tr.sigma0, split * delta0 / a_sum, abs_=1e-15)
        other = make_context(book.with_overrides({"nii.sigma0_split": 1.0}), facts).transmission
        assert close(other.sigma0, delta0 / a_sum, abs_=1e-15) and other.sigma0_liab == 0.0

    def lt_spread_closed_form() -> None:
        """s_eff,b,W = s_b^LT + σ0_A·[lt_shift] − φ_A·[b ∈ Φ_A]·(ref_W^LT − ref_H^LT) (М§4.5)."""
        tr = base.ctx.transmission
        last = str(book.get("meta.last_period"))
        y, h = int(last[:4]), int(last[-1])
        ref_w = str(book.get("nii.transmission.reference_world"))
        for b, row in tr.lt_spread.items():
            spec = book.get(f"nii.books.{b}")
            key = lambda w: f"worlds.{w}.key_rate" if spec["ref"] == "key" else f"worlds.{w}.{spec['ref']}"  # noqa: E731
            for w, got in row.items():
                want = Trajectory(spec["spread"]).value(y, h) + (tr.sigma0 if spec["lt_shift"] else 0.0)
                if spec["phi"]:
                    want -= tr.phi_assets * (Trajectory(book.get(key(w))).value(y, h)
                                             - Trajectory(book.get(key(ref_w))).value(y, h))
                assert close(got, want, abs_=1e-15), (b, w)
        assert 0 < tr.phi_assets < tr.phi                                # доля сжатия на активах — внутри (0; 1)

    def neutral_edge_tolerance() -> None:
        """Край отрезка поиска с |невязкой| в допуске — корень (М§13)."""
        from model.nextreport import _Gap, _neutral
        root, gap, err = _neutral([0.058, 0.061, 0.064], [-9.0, -6.0, -3.0], _Gap(lambda x: -0.25), 0.002, 0.5)
        assert err is None and close(root, 0.066, abs_=1e-12) and gap == -0.25, (root, gap, err)

    def guidance_point_tolerance() -> None:
        from model.checks import guidance_band
        lo, hi = guidance_band({"v": 0.2, "kind": "point", "text": "20%"})
        assert close(lo, 0.195, abs_=1e-12) and close(hi, 0.205, abs_=1e-12), (lo, hi)

    def mean_shift_formula() -> None:
        assert close(U.mean_shift(400.0, 380.0, 410.0), (410.0 + 380.0 - 800.0) / 6)

    # ---------------------------------------------------------------- волна W3: закрытые формулы из книги и фактов

    def lt_refs(world: str) -> dict[str, float]:
        """Опорные ставки мира в last_period (стационар) — из траекторий книги."""
        last = str(book.get("meta.last_period"))
        y, h = int(last[:4]), int(last[-1])
        return {ref: Trajectory(book.get(f"worlds.{world}.key_rate" if ref == "key" else f"worlds.{world}.{ref}")).value(y, h)
                for ref in ("key", "ofz_1y", "ofz_3y", "ofz_5y", "ofz_10y")}

    def anchor_weights():
        from model.book import anchor_facts, book_roles
        books = book.get("nii.books")
        af = anchor_facts(facts, books)
        roles = book_roles(books)
        iea = sum(af.balances[b] for b in roles.assets)
        return books, roles, {b: af.balances[b] / iea for b in roles.names}

    def phi_split_closed_form() -> None:
        """φ_A = p × φ, φ_L = (1 − p) × φ × A / L; добавка пассивов в стационаре L × φ_L × X_W равна остатку
        сжатия (1 − p) × φ × C_W; Nss, T_real и парные передачи от доли не зависят (М§4.5)."""
        books, roles, w = anchor_weights()
        tr = base.ctx.transmission
        p = float(book.get("nii.phi_split"))
        assert 0 < p < 1
        phi_a = [b for b in roles.assets if books[b].get("phi")]
        phi_l = [b for b in roles.liabilities if books[b].get("phi")]
        a_sum, l_sum = sum(w[b] for b in phi_a), sum(w[b] for b in phi_l)
        assert l_sum > 0 and abs(a_sum - l_sum) > 1e-3                   # отношение весов A / L — не единица
        assert close(tr.phi_assets, p * tr.phi, abs_=1e-15)
        assert close(tr.phi_liab, (1 - p) * tr.phi * a_sum / l_sum, abs_=1e-15)
        ref_w = str(book.get("nii.transmission.reference_world"))
        rh = lt_refs(ref_w)
        for world in book.get("worlds.ids"):
            rw = lt_refs(world)
            c_w = sum(w[b] * (rw[books[b]["ref"]] - rh[books[b]["ref"]]) for b in phi_a)
            x_w = c_w / a_sum
            assert close(l_sum * tr.phi_liab * x_w, (1 - p) * tr.phi * c_w, abs_=1e-15), world
        for other in (0.0, 1.0):
            t2 = make_context(book.with_overrides({"nii.phi_split": other}), facts).transmission
            assert t2.phi == tr.phi and t2.t_real == tr.t_real and dict(t2.nss) == dict(tr.nss)
            assert dict(t2.pairs) == dict(tr.pairs) and t2.sigma0 == tr.sigma0
        one = make_context(book.with_overrides({"nii.phi_split": 1.0}), facts).transmission
        assert one.phi_assets == one.phi and one.phi_liab == 0.0

    def phi_remainder_reaches_liabilities() -> None:
        """Ставка пассива с phi: c_q = c_(q−1) + ρ (β ref_W,q + s(q) + φ_L X_W,q − c_(q−1)), X_W,q — разность опор
        кредитных книг Φ_A мира и мира H с весами якоря (М§4.4); актива с phi — со сжатием φ_A."""
        books, roles, w = anchor_weights()
        tr = base.ctx.transmission
        assert tr.phi_liab != 0.0
        ref_w = str(book.get("nii.transmission.reference_world"))
        phi_a = [b for b in roles.assets if books[b].get("phi")]
        a_sum = sum(w[b] for b in phi_a)
        wm, wh = base.ctx.worlds["M"], base.ctx.worlds[ref_w]
        c = base.cell("M", "norm", "schedule")
        spreads = base.ctx.prep.spreads
        seen = 0.0
        for q in range(1, tl.Q + 1):
            x_q = sum(w[b] / a_sum * (wm.ref(books[b]["ref"])[q] - wh.ref(books[b]["ref"])[q]) for b in phi_a)
            seen = max(seen, abs(x_q))
            for b in roles.names:
                spec = books[b]
                ref = wm.ref(spec["ref"])[q]
                prev = c.books[b]["rate"][q - 1]
                if spec["side"] == "asset":
                    target = ref + spreads[b][q] - (tr.phi_assets * (ref - wh.ref(spec["ref"])[q]) if spec.get("phi") else 0.0)
                else:
                    target = float(spec["beta"]) * ref + spreads[b][q] + (tr.phi_liab * x_q if spec.get("phi") else 0.0)
                assert close(c.books[b]["rate"][q], prev + float(spec["rho"]) * (target - prev), abs_=1e-13), (b, q)
        assert seen > 0.01                                               # в мире M опоры кредитных книг выше мира H

    def fade_is_one_sided() -> None:
        """ROE'_T = k_T + fade × max(ROE_T − k_T, 0) + min(ROE_T − k_T, 0): fade < 1 не повышает оценку ни в одной
        клетке; при ROE_T ≥ k_T — прежняя формула; DDM = RI держится (М§7)."""
        faded = run_grid(book.with_overrides({"valuation.terminal.fade": 0.5}), facts)
        below = above = 0
        for a, b in zip(base.cells, faded.cells):
            assert close(a.roe_t_raw, b.roe_t_raw, rel=1e-12) and a.roe_t == a.roe_t_raw       # центр оси — 1
            if a.roe_t_raw < a.k_t:
                assert b.roe_t == b.roe_t_raw and close(b.v_ri, a.v_ri, rel=1e-12), a.label
                below += 1
            else:
                assert close(b.roe_t, b.k_t + 0.5 * (b.roe_t_raw - b.k_t), abs_=1e-15), a.label
                assert b.v_ri <= a.v_ri, a.label
                above += b.v_ri < a.v_ri
        assert below > 0 and above > 0
        assert not [f.name for f in check_invariants(faded) if f.fired]

    def fvc_reference_is_the_book_before_the_draw() -> None:
        """Сдвиг путей CoR всех режимов на x меняет FVC каждой клетки на factor × x × Ē^СС × d/365: опора FVC —
        путь режима-опоры книги до розыгрыша (М§4.6)."""
        x = 0.001
        factor = float(book.get("credit.fv_loans_factor"))
        shifted = run_grid(book.with_overrides(sensitivity_overrides(book, "cor", x)), facts)
        for a, b in zip(base.cells, shifted.cells):
            for q in range(1, tl.Q + 1):
                want = factor * x * a.quarters["loans_fv_avg"][q] * tl.d(q) / 365
                assert close(b.quarters["fvc"][q] - a.quarters["fvc"][q], want, abs_=1e-9), (a.label, q)
        assert shifted.ctx.book.base is book and book.base is None

    def regime_floor() -> None:
        """Пол вероятности режима: после каждого наблюдения P(r) ≥ floor_share × базовой, Σ = 1 (М§12)."""
        share = float(book.get("joint.regime_update.floor_share"))
        prior = {r: float(book.get(f"joint.regime_prob.{r}")) for r in book.get("regimes.ids")}
        assert 0 < share < 1
        obs = [observation(tl.period(q), 0.045) for q in range(1, 5)]            # четыре отчёта «кризис»
        ctx = with_observations(obs)
        hit = 0
        for u in ctx.updates:
            post = u["posterior_after"]
            assert close(sum(post.values()), 1.0, abs_=1e-12)
            for r in prior:
                assert post[r] >= share * prior[r] - 1e-15, (u["period"], r)
                hit += close(post[r], share * prior[r], abs_=1e-12)
        assert hit > 0                                                           # пол связал
        free = with_observations(obs, **{"joint.regime_update.floor_share": 0.0})
        assert min(free.posterior[r] / prior[r] for r in prior) < share          # без пола режим уходит ниже

    def year_with_reported_quarters() -> None:
        """Годовая упр. метрика года якоря — взвешенное среднее кварталов: отчётные — раскрытым упр. фактом
        истории моста, прогнозные — мостом (М§4.6)."""
        from model.checks import guidance_values
        from model.credit import mgmt_history
        year = tl.anchor_year
        c = base.cell("H", "norm", "schedule")
        got = guidance_values(base, c, year)
        hist = base.ctx.prep.hist_bal
        ac0 = base.ctx.prep.anchor_state["loans"] - base.ctx.prep.af.fv_loans
        mg = mgmt_history(facts, "cor")
        b_cor = facts.need("bridge_mgmt_ifrs", "cor.value")
        num = den = 0.0
        for q in tl.quarters_of_year(year):
            d = tl.d(q)
            if q <= 0:
                ends = [ac0 if j == 0 else hist[j]["loans_ac"] for j in (q - 1, q)]
                z, x = sum(ends) / 2 * d, mg[tl.period(q)]
            else:
                z = c.quarters["loans_ac_avg"][q] * d
                x = c.quarters["llp"][q] * 365 / d / c.quarters["loans_ac_avg"][q] - b_cor
            num, den = num + z * x, den + z
        assert close(got["cor_max"], num / den, abs_=1e-12)
        assert not close(got["cor_max"], c.annual["cor"][0] - b_cor, abs_=1e-5)   # не «год движка минус средний мост»

    def unregistered_dividend_closed_form() -> None:
        """U — дивиденд, вычтенный клетками на закрытых концах кварталов ГОСА без записи реестра (М§14.4)."""
        agm_q = tl.index(f"{tl.anchor_year + 1}Q{book.get('dividends.calendar.agm_quarter')}")
        run = run_grid(book, facts, live_at(tl.end(agm_q)))
        prob = run.layers["analytical"].prob
        want = sum(prob[c.key] * c.quarters["div"][agm_q] for c in run.cells)
        assert want > 0 and close(run.unregistered_dividend, want, rel=1e-12)
        before = run_grid(book, facts, live_at(tl.end(agm_q) - timedelta(days=1)))
        assert before.unregistered_dividend == 0.0
        ex = tl.end(agm_q) + timedelta(days=20)
        rec = DividendRecord(year=tl.anchor_year, dps=40.0, status="declared", record_date=ex,
                             last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                             sources=("проверка",))
        assert run_grid(book, facts, live_at(tl.end(agm_q), (rec,))).unregistered_dividend == 0.0

    def median_shift_window() -> None:
        """Оценщик срединных прогонов: среднее попарных разностей по прогонам с рангом в окне (М§10)."""
        base_c = [float(i) for i in range(10)]
        moved = [v + (5.0 if i < 2 or i > 7 else 1.0 + 0.1 * i) for i, v in enumerate(base_c)]
        got = U.median_shift(base_c, moved, (0.4, 0.6))
        assert close(got, (1.4 + 1.5) / 2), got                           # ранги 5 и 6 из 10: квантили 4/9 и 5/9
        by = list(reversed(base_c))
        assert close(U.median_shift(base_c, moved, (0.0, 0.25), by=by), (1.7 + 5.0 + 5.0) / 3)    # ранги — по `by`

    def neutral_search_goes_inside_the_bracket() -> None:
        """Строка таблицы с невязкой в рублёвом допуске корнем не считается, если между соседними строками
        невязка меняет знак: поиск идёт внутрь отрезка и останавливается по двум допускам (М§13)."""
        from model.nextreport import _Gap, _neutral
        slope, root_true = 1600.0, 0.06672
        g = _Gap(lambda x: slope * (x - root_true))
        values = [0.064, 0.067, 0.070]
        root, gap, err = _neutral(values, [g.fn(v) for v in values], g, 0.002, 0.5, 0.0001)
        assert err is None and abs(root - root_true) <= 0.0001 and abs(gap) <= 0.5, (root, gap)
        assert abs(g.fn(0.067)) <= 0.5 and root != 0.067                  # строка 0,067 — в рублёвом допуске, но не корень

    def refine_takes_the_secant_step() -> None:
        """Уточнение корня на полной полосе (М§11.2): невязка решения подвыборки вне стопа — шаг секущей от точки
        книги; на линейной невязке он попадает в корень. Невязка в стопе — уточнение кончено без второй полосы."""
        from model.reverse import _refine_full
        calls: list[float] = []

        def g(x: float) -> float:
            calls.append(x)
            return 1000.0 * (x - 0.0052)
        value, gap, estimate = _refine_full(g, 0.0, g(0.0), 0.0048, -0.01, 0.01, 2, 0.05)
        assert close(value, 0.0052, abs_=1e-12) and abs(gap) <= 1e-9 and close(estimate, value), (value, gap)
        assert calls[1:] == [0.0048, value]
        calls.clear()
        value, gap, estimate = _refine_full(g, 0.0, -5.2, 0.0048, -0.01, 0.01, 2, 0.5)
        assert (value, len(calls)) == (0.0048, 1) and close(gap, -0.4) and estimate == value

    def in_range_is_about_the_root() -> None:
        """«В диапазоне книги» — утверждение о корне (М§11.2): приближение внутри диапазона при оценке корня за
        его краем — «вне»; решение с невязкой в стопе судится само."""
        from model.reverse import _refine_full, root_in_range
        g = lambda x: 1000.0 * (x - 0.0052)                               # noqa: E731
        value, gap, estimate = _refine_full(g, 0.0, g(0.0), 0.0048, -0.01, 0.01, 1, 0.05)
        assert value == 0.0048 and abs(gap) > 0.05 and close(estimate, 0.0052, abs_=1e-12)
        assert not root_in_range(value, gap, estimate, -0.003, 0.005, 0.05)   # приближение внутри, корень — за краем
        assert root_in_range(value, gap, estimate, -0.003, 0.006, 0.05)       # и приближение, и оценка корня внутри
        assert root_in_range(0.0048, 0.01, 0.0048, -0.003, 0.005, 0.05)       # сошлось: судится решение
        assert not root_in_range(0.0052, 0.0, 0.0052, -0.003, 0.005, 0.05) and not root_in_range(None, None, None, 0, 1, 0.5)

    def point_neutral_goes_inside_the_bracket() -> None:
        """Нейтральное значение точки (М§13): строка таблицы с невязкой в рублёвом допуске корнем не считается,
        если между соседними строками невязка меняет знак."""
        from model.nextreport import _point_neutral
        slope, root_true = 1600.0, 0.06672
        pg = lambda x: slope * (x - root_true)                            # noqa: E731
        values = [0.064, 0.067, 0.070]
        root = _point_neutral(values, [pg(v) for v in values], pg, 0.002, 0.5, 0.0001)
        assert abs(pg(0.067)) <= 0.5 and abs(root - root_true) <= 0.0001 and root != 0.067, root

    def lt_floor_at_the_ends_of_share_axes() -> None:
        """Гейт `lt_spread_floor` проверяется и в углах области осей долей (М§4.5): пол, который выдерживают
        значения книги, но не выдерживает конец оси доли сжатия, — гейт срабатывает."""
        from model.checks import check_gates
        tr = base.ctx.transmission
        floors = {b: min(row.values()) - 1e-4 for b, row in tr.lt_spread.items()}
        axes = [a for a in book.get("valuation.uncertainty.axes")
                if not set(a["paths"]) & {"nii.sigma0_split", "nii.phi_split"}]
        axis = {"name": "доля сжатия", "kind": "value", "paths": ["nii.phi_split"],
                "low": float(book.get("nii.phi_split")), "high": 1.0, "dist": "triangular"}
        quiet = run_grid(book.with_overrides({"checks.lt_spread_floor": floors, "valuation.uncertainty.axes": axes}),
                         facts)
        gate = next(f for f in check_gates(quiet) if f.name == "lt_spread_floor")
        assert not gate.fired, gate.message
        wide = run_grid(book.with_overrides({"checks.lt_spread_floor": floors,
                                             "valuation.uncertainty.axes": axes + [axis]}), facts)
        gate = next(f for f in check_gates(wide) if f.name == "lt_spread_floor")
        assert tr.phi > 0 and float(book.get("nii.phi_split")) < 1.0
        assert gate.fired and gate.detail["axis_ends"], gate.message

    def nowcast_year_on_one_layer() -> None:
        """Без нау-каста квартал открытого периода в сумме года — квартал смеси заголовка: `dps` = `dps_model`
        (П§2 nowcast.year)."""
        from model import payload as P
        from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
        from model.checks import check_gates
        expl = explained(check_gates(base, today=TODAY))
        rel = P.make_release(live=False, fast=True, today=TODAY, book=book, facts=facts, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE)
        year = P.build_payload(rel)["nowcast"]["year"]
        assert year["dps"] is not None and close(year["dps"], year["dps_model"], abs_=1e-4), year

    # --- литералы эмитента из книги и схема второй формы банка (М§0.6, прил. A)

    def refused(data: dict, *fragments: str, pending_ok: bool = False) -> None:
        from model.book_schema import BookError, validate
        try:
            validate(data, pending_ok=pending_ok)
        except BookError as exc:
            assert all(fr in str(exc) for fr in fragments), str(exc)[:300]
            return
        raise AssertionError(f"схема приняла книгу, ждали отказ: {fragments}")

    def schema_name_is_the_key_of_the_book() -> None:
        """Имя схемы выпуска — `meta.schema`: его несёт выпуск и требует контракт (М§0.6)."""
        from model import payload as P
        b2 = book.with_overrides({"meta.schema": "probe-v3"})
        assert P.schema_name(b2) == "probe-v3" and P.schema_name(book) == book.get("meta.schema") != "probe-v3"
        assert any("probe-v3" in p for p in P.validate({"schema": P.schema_name(book)}, schema=P.schema_name(b2)))

    def book_title_keeps_abbreviations() -> None:
        """Подпись книги ЧПД в сообщении гейта — со строчной первой буквы, остальное как в книге."""
        from model.checks import check_gates
        loan = base.ctx.prep.roles.loans[0]
        b2 = book.with_overrides({f"nii.books.{loan}.name": "Кредиты МСБ и ЮЛ",
                                  "checks.lt_spread_floor": {b: 1.0 for b in base.ctx.prep.roles.loans}})
        gate = next(f for f in check_gates(run_grid(b2, facts)) if f.name == "lt_spread_floor")
        assert gate.fired and "кредиты МСБ и ЮЛ" in gate.message and "Кредиты МСБ" not in gate.message, gate.message

    def guidance_gate_reads_the_gate_flag() -> None:
        """Гейт гайденса берёт из перечня книги только пункты с `gate: true` (М§14.2)."""
        import dataclasses
        from model.checks import check_gates
        guid = copy.deepcopy(facts.files["guidance"])
        guid["items"]["roe"] = {**guid["items"]["roe"], "v": 0.95, "kind": "point", "tol": 0.001}
        f2 = dataclasses.replace(facts, files={**facts.files, "guidance": guid})
        on = next(f for f in check_gates(run_grid(book, f2)) if f.name == "guidance_gap")
        assert on.fired and "roe" in on.detail["bands"]
        items = [dict(it, gate=False) if it["key"] == "roe" else it for it in book.get("checks.guidance_items")]
        off = next(f for f in check_gates(run_grid(book.with_overrides({"checks.guidance_items": items}), f2))
                   if f.name == "guidance_gap")
        assert "roe" not in off.detail["bands"], off.detail

    def pending_branch_refuses() -> None:
        """Ветвь, принятая схемой и не исполняемая ядром, при включении — отказ «не реализовано». В схеме таких
        ветвей сейчас нет, поэтому механизм проверяется на подставной: выключатель роста по капиталу."""
        from model import book_schema as BS
        from tests.support_core_t import neutral_dict, t_dict
        full = t_dict()
        assert BS.pending(full) == [] and BS.pending(neutral_dict()) == []
        path = "capital.growth_constraint.enabled"
        BS.PENDING[path] = (lambda v: v is True, "подставная ветвь")
        try:
            assert BS.pending(full)
            refused(full, path, "не реализовано")
            BS.validate(full, pending_ok=True)
            full["capital"]["growth_constraint"]["enabled"] = False
            BS.validate(full)
        finally:
            del BS.PENDING[path]

    def label_fields_are_closed() -> None:
        """Поле подстановки подписи — только названное у ключа (М§0.6)."""
        data = copy.deepcopy(dict(book.source))
        data["meta"]["labels"]["capital"]["n20"] = "Норматив {year}"
        refused(data, "meta.labels.capital.n20", "незнакомое поле")

    def inactive_calendar_key_refuses() -> None:
        """Ключ неактивного режима календаря дивидендов со значением — отказ (М§5.7)."""
        data = copy.deepcopy(dict(book.source))
        assert data["dividends"]["calendar"].get("frequency", "annual") == "annual"
        data["dividends"]["calendar"]["decision_lag_quarters"] = 2
        refused(data, "dividends.calendar.decision_lag_quarters", "неактивного режима")

    def record_label_by_period() -> None:
        """Слова периода записи реестра — по номеру квартала прибыли и году периода (М§0.6)."""
        from model.book import record_label
        periods = book.get("meta.labels.periods")
        assert len(set(periods.values())) == 4
        for h in (1, 2, 3, 4):
            assert record_label(book, tl.anchor_year + 1, f"{tl.anchor_year}Q{h}") == periods[str(h)].format(
                year=tl.anchor_year), h

    def corridor_words_from_the_book() -> None:
        """Названия нормативов в подписи коридора гейта — ключи книги (М§0.6)."""
        from model import payload as P
        b2 = book.with_overrides({"meta.labels.capital.n20_short": "НОРМ-А", "meta.labels.capital.n11_short": "НОРМ-Б"})
        assert P._corridor(b2, "capital_gap")["text"] == "пол НОРМ-А и НОРМ-Б сценария после дивидендов"
        assert "НОРМ-А" in P._corridor(b2, "m_crisis_vs_cbr")["text"]

    def issued_divisor_needs_one_ticker() -> None:
        """Делитель «размещённые акции» — только при одном тикере (М§8.4)."""
        data = copy.deepcopy(dict(book.source))
        assert len(data["meta"]["company"]["tickers"]) > 1
        data["valuation"]["shares_basis"] = "issued"
        refused(data, "valuation.shares_basis", "одном тикере", pending_ok=True)

    def growth_constraint_needs_the_quarterly_calendar() -> None:
        """Рост по капиталу включается только при квартальном календаре дивидендов (М§4.13)."""
        from tests.support_core_t import plain_dict
        refused(plain_dict(on=("capital.growth_constraint.enabled",)), "capital.growth_constraint.enabled",
                "quarterly", pending_ok=True)

    # ---------------------------------------------------------------- вторая форма банка, волна 1 (фикстура core_t)

    from tests.support_core_t import book_live, plain_book, plain_run, t_facts

    T_BASIS, T_HISTORY, T_GUIDANCE = "valuation.shares_basis", "dividends.policy.history_test", "checks.guidance_items"
    T_LINKS = ("fees.volume_link", "other.insurance_volume_link", "opex.volume_link")

    def t_changed(file: str, change):
        """Факты фикстуры формы Т с правкой одного файла на месте его копии."""
        import dataclasses
        tf = t_facts()
        data = copy.deepcopy(tf.files[file])
        change(data)
        return dataclasses.replace(tf, files={**tf.files, file: data})

    def t_grid(tbook, tfacts=None, register=(), day=None):
        lv = book_live(tbook)
        if register or day is not None:
            v = day or lv.valuation_date
            lv = LiveInputs(valuation_date=v, prices=dict(lv.prices), price_dates={t: v for t in lv.prices},
                            register=tuple(register))
        return run_grid(tbook, tfacts or t_facts(), lv)

    def t_gate(run, name: str, **kw):
        from model.checks import check_gates
        return next((f for f in check_gates(run, **kw) if f.name == name), None)

    def t_divisor_scales_the_price() -> None:
        """N_div = (размещённые − экономически собственные) × (1 + поправка): цена в N_out / N_div раз ниже,
        капитализация — цена × N_div (М§8.3, §8.4)."""
        from model.grid import market_cap
        tf = t_facts()
        n_iss, n_out = tf.need("shares", "issued_total"), tf.need("shares", "outstanding_total")
        flat, run, tbook = plain_run(), plain_run((T_BASIS,)), plain_book((T_BASIS,))
        assert flat.divisor == flat.shares_out == n_out and run.divisor == n_iss and run.shares_out == n_out
        assert close(run.point, flat.point * n_out / n_iss, rel=1e-12)
        held = t_changed("shares", lambda d: d["economic_treasury"].update(v=85.0))
        assert t_grid(tbook, held).divisor == n_iss - 85.0
        moved = t_grid(tbook.with_overrides({"valuation.share_count_adj": 0.02}))
        assert close(moved.divisor, n_iss * 1.02, rel=1e-15) and close(moved.point, run.point / 1.02, rel=1e-12)
        price = float(tbook.get("meta.market_price.T"))
        assert close(market_cap(run), price * n_iss / 1000, rel=1e-12)
        assert close(market_cap(flat), price * n_out / 1000, rel=1e-12)

    def t_exdate_jump_on_the_divisor() -> None:
        """Скачок на экс-дату = −DPS × N_out / N_div: мост и вычет клетки — на акции в обращении (М§8.4)."""
        tbook = plain_book((T_BASIS,))
        ttl = plain_run().ctx.timeline
        agm_q = ttl.index(f"{ttl.anchor_year + 1}Q{tbook.get('dividends.calendar.agm_quarter')}")
        v = ttl.end(agm_q) + timedelta(days=20)
        runs = []
        for ex in (v, v + timedelta(days=1)):
            rec = DividendRecord(year=ttl.anchor_year, dps=40.0, status="declared", record_date=ex,
                                 last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=ex + timedelta(days=14),
                                 sources=("проверка",))
            runs.append(t_grid(tbook, register=(rec,), day=v))
        k = runs[0].shares_out / runs[0].divisor
        assert k < 0.99 and close(runs[0].point - runs[1].point, -40.0 * k, abs_=1e-6), [r.point for r in runs]
        assert close(runs[1].bridge_amount, 40.0 * runs[1].shares_out / 1000, rel=1e-12)

    def t_history_cap() -> None:
        """Тест истории вида `cap`: выплаты завершённого года не выше потолка политики от отчётной прибыли
        акционеров; неполный год — диагностика; год выше потолка — инвариант нарушен (М§5.2)."""
        def history(run):
            return next(f for f in check_invariants(run) if f.name == "dps_history")
        tbook = plain_book((T_HISTORY,))
        found = history(plain_run((T_HISTORY,)))
        rows = {r["year"]: r for r in found.detail["rows"]}
        assert not found.fired and rows[2025]["ok"] is True and rows[2026]["ok"] is None, found.message
        assert rows[2026]["share"] > rows[2026]["cap"]                     # неполный год выше потолка — не отказ
        assert close(rows[2025]["pool"], (3.30 + 3.50 + 3.60 + 4.50) * t_facts().need("shares", "issued_total") / 1000)
        over = t_changed("dividends", lambda d: d["years"]["2025"]["ni_shareholders"].update(v=130.0))
        assert history(t_grid(tbook, over)).fired

    def t_payout_cap_gate() -> None:
        """Гейт `payout_cap`: базовая выплата года на все размещённые акции — доля политики от прибыли; потолок
        чуть ниже доли — гейт срабатывает, потолок книги выше доли — молчит (М§14.2)."""
        tbook = plain_book((T_HISTORY,))
        payout = Trajectory(tbook.get("dividends.policy.payout")).year_value(plain_run().ctx.timeline.anchor_year)
        assert t_gate(plain_run(), "payout_cap") is None
        assert not t_gate(plain_run((T_HISTORY,)), "payout_cap").fired
        low = t_gate(t_grid(tbook.with_overrides({"dividends.policy.cap": payout - 0.005})), "payout_cap")
        assert low.fired and low.mass > 0.5, low.message

    def t_volume(c, ttl, q: int) -> float:
        tf = t_facts()
        end = lambda x: c.quarters["loans"][x] if x >= 0 else tf.need("balance", f"history.{ttl.period(x)}.loans")  # noqa: E731
        return (end(q - 1) + end(q)) / 2

    def t_flow(c, ttl, q: int, name: str, node: str, sign: int = 1) -> float:
        return c.quarters[name][q] if q >= 1 else sign * t_facts().need("pnl_quarterly", f"quarters.{ttl.period(q)}.{node}")

    def t_volume_link_closed_form() -> None:
        """Комиссии и страхование: × (1 + wage + спред + link × (v − wage)); расходы: × (1 + wage + link × (v −
        wage)) × (1 + real); v — рост г/г среднего остатка кредитных книг; год `fees.growth_override` связи к
        комиссиям не знает (М§4.7)."""
        tbook, run = plain_book(T_LINKS), plain_run(T_LINKS)
        ttl = run.ctx.timeline
        lf, li, lc = (float(tbook.get(k)) for k in T_LINKS)
        g_f, g_i = Trajectory(tbook.get("fees.growth_vs_wages")), Trajectory(tbook.get("other.insurance_growth_vs_wages"))
        real = Trajectory(tbook.get("opex.real_growth"))
        c, wage = run.cell("H", "soft", "mid"), run.ctx.worlds["H"].wage
        for q in (1, 2, 5, 9, ttl.Q):
            y, h = ttl.year(q), ttl.h(q)
            ex = t_volume(c, ttl, q) / t_volume(c, ttl, q - 4) - 1 - wage[q]
            assert abs(ex) > 1e-4
            fees = t_flow(c, ttl, q - 4, "fees", "fees_net") * (1 + wage[q] + g_f.value(y, h) + lf * ex)
            ins = t_flow(c, ttl, q - 4, "ins", "insurance_net") * (1 + wage[q] + g_i.value(y, h) + li * ex)
            opex = t_flow(c, ttl, q - 4, "opex", "opex", -1) * (1 + wage[q] + lc * ex) * (1 + real.value(y, h))
            assert close(c.quarters["fees"][q], fees, rel=1e-12) and close(c.quarters["ins"][q], ins, rel=1e-12), q
            assert close(c.quarters["opex"][q], opex, rel=1e-12), q
        year = ttl.anchor_year + 1
        over = t_grid(tbook.with_overrides({"fees.growth_override": {str(year): 0.10}})).cell("H", "soft", "mid")
        for q in ttl.quarters_of_year(year):
            assert close(over.quarters["fees"][q], t_flow(over, ttl, q - 4, "fees", "fees_net") * 1.10, rel=1e-12), q

    def t_premium_by_sector() -> None:
        """Книга растёт с премией своего сектора, средства клиентов — с премией своего сегмента (М§4.3)."""
        keys = ("volumes.loan_share_drift", "volumes.funds_share_drift")
        tbook, run = plain_book(keys), plain_run(keys)
        ttl = run.ctx.timeline
        c, world = run.cell("N", "norm", "schedule"), run.ctx.worlds["N"]
        y = ttl.year(1)
        loan = {s: Trajectory(t).year_value(y) for s, t in tbook.get("volumes.loan_share_drift").items()}
        funds = {s: Trajectory(t).year_value(y) for s, t in tbook.get("volumes.funds_share_drift").items()}
        assert len(set(loan.values())) == 3 and min(funds.values()) > 0
        adj = Trajectory(tbook.get("regimes.norm.loan_growth_adj")).year_value(y)
        for b in run.ctx.prep.roles.loans:
            sector = tbook.get(f"nii.books.{b}.sector")
            want = (1 + world.credit_growth[sector][y]) * (1 + loan[sector]) - 1 + adj
            assert close(c.books[b]["balance"][1] / c.books[b]["balance"][0], (1 + want) ** 0.25, rel=1e-12), b
        retail = c.quarters["funds_retail"][1] / c.quarters["funds_retail"][0]
        assert close(retail, ((1 + world.funds_growth["retail"][y]) * (1 + funds["retail"])) ** 0.25, rel=1e-12)
        corp = c.books["corp_funds"]["balance"][1] / c.books["corp_funds"]["balance"][0]
        assert close(corp, ((1 + world.funds_growth["corporate"][y]) * (1 + funds["corporate"])) ** 0.25, rel=1e-12)

    def t_rwa_base(tbook, c, q: int, fixed: float) -> float:
        dens = tbook.get("capital.rwa.density")
        total = sum(float(dens[b]) * c.books[b]["balance"][q] for b in c.books if "sector" in tbook.get(f"nii.books.{b}"))
        total += float(dens["securities"]) * c.quarters["securities"][q] + float(dens["liquidity"]) * c.quarters["liquidity"][q]
        return (total + float(dens["other_assets"]) * (c.quarters["other_assets"][q] - fixed)
                + float(dens["other_assets_fixed"]) * fixed)

    def t_fixed_other_assets() -> None:
        """OA_q = (прочие активы якоря − OA_fixed) / кредиты якоря × кредиты_q + OA_fixed; в RWA постоянная часть —
        со своей плотностью (М§4.3, §4.11)."""
        tf = t_facts()
        tbook = plain_book(("volumes.other_assets_fixed",)).with_overrides({"capital.rwa.density.other_assets_fixed": 0.4})
        run = t_grid(tbook)
        fixed = tf.need("balance", "other_assets_fixed")
        loans0 = sum(tf.need("balance", f"books.{b}") for b in run.ctx.prep.roles.loans)
        ratio = (tf.need("balance", "other_assets") - fixed) / loans0
        c = run.cell("H", "norm", "schedule")
        for q in (0, 1, 8, run.ctx.timeline.Q):
            assert close(c.quarters["other_assets"][q], ratio * c.quarters["loans"][q] + fixed, rel=1e-12), q
            assert close(c.quarters["rwa"][q], t_rwa_base(tbook, c, q, fixed), rel=1e-12), q
        assert close(run.ctx.prep.rwa0, t_rwa_base(tbook, c, 0, fixed), rel=1e-12)

    def t_regime_rwa_multiplier() -> None:
        """RWA клеток режима — база × множитель режима в квартале; прочие режимы не меняются (М§4.11)."""
        key = "regimes.crisis.rwa_density_mult"
        tbook, run, flat = plain_book((key,)), plain_run((key,)), plain_run()
        ttl = run.ctx.timeline
        mult = Trajectory(tbook.get(key))
        c = run.cell("N", "crisis", "mid")
        shock = run.ctx.prep.regimes["crisis"].shock_year
        for q in range(1, ttl.Q + 1):
            assert close(c.quarters["rwa"][q], t_rwa_base(tbook, c, q, 0.0) * mult.value(ttl.year(q), ttl.h(q)), rel=1e-12), q
        for q in ttl.quarters_of_year(shock):
            assert close(c.quarters["rwa"][q], 0.9 * flat.cell("N", "crisis", "mid").quarters["rwa"][q], rel=1e-12), q
        assert run.cell("N", "norm", "mid").quarters["rwa"] == flat.cell("N", "norm", "mid").quarters["rwa"]

    def t_guidance_growth_nodes() -> None:
        """Узлы роста гайденса: прибыль акционеров года клетки к сумме четырёх кварталов прошлого года минус 1;
        DPS года к сумме DPS строк истории за прошлый год минус 1 (М§14.2)."""
        from model.checks import guidance_bases, guidance_values
        tf, run = t_facts(), plain_run((T_GUIDANCE,))
        year = int(tf.plain("guidance", "year"))
        ni_prev = sum(tf.need("pnl_quarterly", f"quarters.{year - 1}Q{h}.ni_shareholders") for h in (1, 2, 3, 4))
        bases = guidance_bases(run, year, ("op_np_growth", "dps_growth"))
        assert close(bases["op_np_growth"], ni_prev) and close(bases["dps_growth"], 3.30 + 3.50 + 3.60 + 4.50)
        c = run.cell("H", "norm", "schedule")
        got = guidance_values(run, c, year, bases)
        assert close(got["op_np_growth"], c.annual["ni_sh"][0] / ni_prev - 1, rel=1e-12)
        assert close(got["dps_growth"], c.dps[year] / (3.30 + 3.50 + 3.60 + 4.50) - 1, rel=1e-12)
        assert set(t_gate(run, "guidance_gap").detail["bands"]) == {"op_np_growth", "dps_growth"}

    def t_estimated_capital() -> None:
        """Норматив якоря, стоящий оценкой, читается из фактов; просрочка формы с нормативами меряется от `latest`
        события-оценки и срабатывает только после срока книги (М§3.3, §14.2)."""
        import dataclasses
        from datetime import date as day_
        from model.book import anchor_facts
        est = t_changed("capital", lambda d: d["n20_0"].update(estimated=True))
        books = plain_book().get("nii.books")
        assert anchor_facts(est, books).estimated == ("n20_0",) and anchor_facts(t_facts(), books).estimated == ()
        event = {"id": "form805-2026Q2", "kind": "form805", "date": "2026-08-20", "title": "Форма с нормативами группы",
                 "covers": "2026Q2", "estimated": True, "earliest": "2026-08-10", "latest": "2026-09-05"}
        cal = dict(est.files["calendar"], events=[event])
        est = dataclasses.replace(est, files={**est.files, "calendar": cal})
        days = {**plain_book().get("checks.manual_overdue_days"), "capital_form": 7}
        run = t_grid(plain_book().with_overrides({"checks.manual_overdue_days": days}), est)
        assert not t_gate(run, "manual_input_overdue", today=day_(2026, 9, 12)).fired
        late = t_gate(run, "manual_input_overdue", today=day_(2026, 9, 13))
        assert late.fired and "форма с нормативами группы" in late.message, late.message

    def t_release_on_the_divisor() -> None:
        """Выпуск при делителе «размещённые»: капитал на акцию и формула цены контракта — на делителе; поправка
        сторожа заголовка на экс-дату — DPS × N_out / N_div; при тесте истории вида `cap` контракт формулы
        «до копейки» не требует; ROE эмитента — к среднему его капитала за пять концов кварталов; флаг сделки —
        только для сделки, которой нет в книге (М§8.4, §14.3, §14.4, §5.2; П§2)."""
        import dataclasses
        from model import payload as P
        from model.checks import check_gates
        from model.grid import bank_language
        from tests.support_core2 import CONTROL_FIXTURE, TODAY, explained
        tbook, tf = plain_book((T_BASIS, T_HISTORY)), t_facts()
        expl = explained(check_gates(run_grid(tbook, tf), today=TODAY))
        rel = P.make_release(live=False, fast=True, today=TODAY, book=tbook, facts=tf, explanations=expl, notes=[],
                             draws=4, control_model=CONTROL_FIXTURE)
        d = P.build_payload(rel)
        n_div, n_out = rel.run.divisor, rel.run.shares_out
        assert d["meta"]["shares"]["divisor_mln"] == n_div and not [x for x in P._point_problems(d) if "М§8.2" in x]
        assert close(d["market"]["multiples"]["bv_per_share"], bank_language(rel.run)["bv_v"] * 1000 / n_div, abs_=0.006)
        assert P._dividend_problems(d) == [] and d["dividends"]["formula_check"] == []
        mq = lambda per, k: tf.need("mgmt_quarterly", f"quarters.{per}.{k}")   # noqa: E731
        profit = sum(mq(per, "op_np_exact") for per in ("2025Q3", "2025Q4", "2026Q1")) + mq("2026Q2", "op_np")
        equity = (mq("2025Q2", "op_equity") + sum(mq(per, "op_equity_exact") for per in ("2025Q3", "2025Q4", "2026Q1", "2026Q2"))) / 5
        assert close(d["history"]["ltm"]["roe_issuer"]["value"], profit / equity, abs_=1e-6), d["history"]["ltm"]
        # флаг объявленной сделки — только пока книга её не учла
        names = lambda fx: [f["name"] for f in P._flags(P._Ctx(fx), rel.next_report)]  # noqa: E731
        assert names(rel)[-1] == "deal_pending"
        cal = copy.deepcopy(tf.files["calendar"])
        for event in cal["events"]:
            if event["kind"] == "deal":
                event["in_book"] = True
        done = copy.copy(rel)
        done.facts = dataclasses.replace(tf, files={**tf.files, "calendar": cal})
        assert "deal_pending" not in names(done)
        # прошлый выпуск до экс-даты строки истории: между выпусками — одна экс-дата с DPS 4,60 ₽
        ex = next(r for r in tf.files["dividends"]["history"] if r["period"] == "2026Q1")
        prev = copy.deepcopy(d)
        prev["meta"]["valuation_date"] = (P.to_date(ex["ex_date"]) - timedelta(days=5)).isoformat()
        rel.previous = prev
        jg, _ = P._jump_guard(P._Ctx(rel), d["fair_value"]["headline"]["median"])
        assert close(jg["exdate_adjustment"], round(4.60 * n_out / n_div, 2), abs_=1e-9), jg

    # ---------------------------------------------------------------- волна 2: квартальный календарь дивидендов (core_t)

    T_CAL = "dividends.calendar"
    T_REF, T_CRISIS = ("N", "norm", "schedule"), ("N", "crisis", "schedule")
    from datetime import date as day_

    def t_rec(period: str, dps: float, record, decided=None, pay=None, status: str = "declared", label=None):
        return DividendRecord(year=int(period[:4]), dps=dps, status=status, record_date=record,
                              last_buy_date=record - timedelta(days=3), ex_date=record, pay_date=pay,
                              sources=("проверка",), period=period, label=label, decided_date=decided)

    T_FOUR = (t_rec("2026Q1", 4.60, day_(2026, 8, 10), day_(2026, 7, 30), day_(2026, 8, 24), "paid"),
              t_rec("2026Q2", 4.70, day_(2026, 10, 12), day_(2026, 10, 1), day_(2026, 10, 26)),
              t_rec("2026Q3", 4.80, day_(2026, 12, 28), day_(2026, 12, 17), day_(2027, 1, 11)),
              t_rec("2026Q4", 5.00, day_(2027, 5, 24), day_(2027, 5, 13), day_(2027, 6, 7)))

    def t_cal_book(**changes):
        from tests.support_core_t import plain_dict, put
        data = plain_dict(on=(T_CAL,))
        for dotted, value in changes.items():
            put(data, dotted.replace("__", "."), value)
        return book_from_dict(data, facts=t_facts())

    def t_fact(period: str) -> float:
        return t_facts().need("pnl_quarterly", f"quarters.{period}.ni_shareholders")

    def t_broken(run) -> list[str]:
        return [f.name for f in check_invariants(run) if f.fired and f.name != "dps_history"]

    def t_quarter_calendar_by_the_lag_map() -> None:
        """Квартал решения — по карте лагов, не раньше первого прогнозного; закрыт квартал прибыли или нет, решает
        факт; каждый открытый квартал уменьшает BV ровно один раз (М§5.7.2)."""
        tbook, run = plain_book((T_CAL,)), plain_run((T_CAL,))
        ttl, n_out = run.ctx.timeline, t_facts().need("shares", "outstanding_total")
        lags = tbook.get("dividends.calendar.decision_lag_quarters")
        assert len(set(lags.values())) > 1
        cell = run.cell(*T_REF)
        assert [d.period for d in cell.decisions[:4]] == ["2026Q1", "2026Q2", "2026Q3", "2026Q4"]
        assert [d.q for d in cell.decisions[:4]] == [1, 2, 2, 4]
        for d in cell.decisions:
            idx = ttl.index(d.period)
            assert d.q == max(1, idx + lags[str(ttl.h(idx))]) and d.year == ttl.year(idx), d.period
        assert not t_broken(run)
        for lag in (1, 4):
            c = t_grid(t_cal_book(dividends__calendar__decision_lag_quarters=lag)).cell(*T_REF)
            assert c.decisions[0].period == "2026Q1" and c.decisions[0].q == max(1, lag - 1), lag
            paid = sum(c.quarters["div"][q] for q in range(1, ttl.Q + 1))
            assert close(paid, sum(c.dps_q.values()) * n_out / 1000, rel=1e-12)
        assert plain_run().ctx.prep.calendar is None and all(d.period is None for d in plain_run().cells[0].decisions)

    def t_quarter_queues() -> None:
        """У решения квартала свои кварталы вычета из регуляторного капитала и выплаты: по карте — через два
        квартала после квартала прибыли, не раньше квартала решения (М§5.7.2, §5.7.4 п. 6)."""
        run = plain_run((T_CAL,))
        cell, slots = run.cell(*T_REF), run.ctx.prep.calendar.periods
        got = {p: (slots[p].q, slots[p].q_reg, slots[p].q_pay) for p in ("2026Q1", "2026Q2", "2026Q3", "2026Q4")}
        assert got == {"2026Q1": (1, 1, 1), "2026Q2": (2, 2, 2), "2026Q3": (2, 3, 3), "2026Q4": (4, 4, 4)}, got
        d = {x.period: x for x in cell.decisions}
        q_ = cell.quarters
        payable = t_facts().need("balance", "dividends_payable")
        assert close(q_["dpreg"][2], d["2026Q3"].div, rel=1e-12) and q_["dpreg"][1] == 0.0 and q_["dpreg"][3] == 0.0
        assert close(q_["pay"][1], d["2026Q1"].div) and close(q_["pay"][2], d["2026Q2"].div)
        assert close(q_["pay"][3], d["2026Q3"].div) and close(q_["dp"][2], payable + d["2026Q3"].div)
        assert close(q_["dp"][1], payable) and close(q_["dp"][3], payable)

    def t_base_is_the_window_mean() -> None:
        """База квартального решения — средняя прибыль акционеров окна; пул — на размещённые акции, уменьшение BV —
        на акции в обращении (М§5.7.3)."""
        tbook, run = plain_book((T_CAL,)), plain_run((T_CAL,))
        tf = t_facts()
        n_iss, n_out = tf.need("shares", "issued_total"), tf.need("shares", "outstanding_total")
        assert int(tbook.get("dividends.policy.base_window_quarters")) == 4
        payout = Trajectory(tbook.get("dividends.policy.payout"))
        cell = run.cell(*T_REF)
        first, second, third = cell.decisions[:3]
        assert close(first.base, sum(t_fact(p) for p in ("2025Q2", "2025Q3", "2025Q4", "2026Q1")) / 4, rel=1e-12)
        assert close(second.base, sum(t_fact(p) for p in ("2025Q3", "2025Q4", "2026Q1", "2026Q2")) / 4, rel=1e-12)
        mean = (t_fact("2025Q4") + t_fact("2026Q1") + t_fact("2026Q2") + cell.quarters["ni_sh"][1]) / 4
        assert third.period == "2026Q3" and close(third.base, mean, rel=1e-12)
        for d in (first, second, third):
            assert close(d.dps, payout.year_value(d.year) * d.base * 1000 / n_iss, rel=1e-12), d.period
            assert close(d.div, d.dps * n_out / 1000, rel=1e-12) and not d.cut

    def t_excess_once_a_year() -> None:
        """Доля избытка — только в решении за четвёртый квартал прибыли (М§5.7.4 п. 5)."""
        tbook, run = plain_book((T_CAL,)), plain_run((T_CAL,))
        eps, start, ramp = (float(tbook.get("dividends.excess.epsilon")),
                            int(tbook.get("dividends.excess.from_profit_year")), int(tbook.get("dividends.excess.ramp_years")))
        seen = 0
        for c in run.cells:
            for d in c.decisions:
                if d.source != "model":
                    continue
                if not d.period.endswith("Q4"):
                    assert d.excess == 0.0 and d.catch == 0.0, (c.label, d.period)
                    continue
                base = sum(x.base_div for x in c.decisions if x.q == d.q and x.source == "model")
                e_y = eps * min(1.0, (d.year - start + 1) / ramp) if d.year >= start else 0.0
                assert close(d.excess, e_y * max(0.0, d.headroom_final - base - d.catch), abs_=1e-9), (c.label, d.period)
                seen += d.excess > 0
        assert seen

    def t_shock_year_cancels_quarterly_decisions() -> None:
        """Год шока отменяет решения модели, принимаемые в его кварталах; отмена — не срез капиталом (М§5.5)."""
        run = plain_run((T_CAL,))
        ttl = run.ctx.timeline
        shock = run.ctx.prep.regimes["crisis"].shock_year
        for c in run.cells:
            skipped = [d for d in c.decisions if d.source == "crisis_skip"]
            if c.regime != "crisis":
                assert not skipped, c.label
                continue
            assert [d.period for d in skipped] == ["2026Q4", "2027Q1", "2027Q2", "2027Q3"], c.label
            assert all(ttl.year(d.q) == shock and d.div == 0.0 and not d.cut and d.flags == ("crisis_skip",)
                       for d in skipped)

    def t_register_by_period() -> None:
        """Запись реестра заменяет дивиденд модели своего квартала прибыли; две записи одного года не схлопываются;
        дивиденд записи — на акции в обращении (М§5.7.4 п. 1, §5.7.6)."""
        from model.grid import live_from_book
        tbook, tf = plain_book((T_CAL,)), t_facts()
        n_out = tf.need("shares", "outstanding_total")
        run = run_grid(tbook, tf, live_from_book(tbook, tf))
        for c in run.cells[:6]:
            got = {d.period: d for d in c.decisions}
            for period, dps in (("2026Q1", 4.60), ("2026Q2", 4.70)):
                assert got[period].source == "register" and got[period].dps == dps, (c.label, period)
                assert close(got[period].div, dps * n_out / 1000, rel=1e-15)
            assert got["2026Q3"].source != "register"
            assert close(c.dps[2026], 4.60 + 4.70 + c.dps_q["2026Q3"] + c.dps_q["2026Q4"], rel=1e-12)
            assert close(c.quarters["div_model"][2], got["2026Q3"].div, rel=1e-12) and c.quarters["div_model"][1] == 0.0
        assert dict(run.ctx.prep.register) == {"2026Q1": 4.60, "2026Q2": 4.70}

    def t_room_of_the_quarter() -> None:
        """Запас квартала — оценка шага с записями реестра и без решений модели, одна точка; базовый дивиденд —
        min(Σ пулов, запас), между решениями — пропорционально; границы дивиденда — по суммам квартала (М§5.7.4, §14.1)."""
        from dataclasses import replace
        from model.cell import _Cell, initial_state
        tbook = plain_book((T_CAL,))
        run = t_grid(tbook, register=(T_FOUR[1],))
        cell, slots = run.cell(*T_REF), run.ctx.prep.calendar.periods
        walker, st = _Cell(run.ctx, *T_REF), initial_state(run.ctx.prep)
        first = tuple((d.div, slots[d.period].q_pay, slots[d.period].q_reg) for d in cell.decisions if d.q == 1)
        walker.step(st, 1, sum(a for a, _, _ in first), parts=first)
        reg = tuple((d.div, slots[d.period].q_pay, slots[d.period].q_reg) for d in cell.decisions
                    if d.q == 2 and d.source == "register")
        assert len(reg) == 1 and reg[0][2] == 2
        row = walker.step(st.clone(), 2, reg[0][0], parts=reg)
        room = min((row["n20"] - row["req20"]) * row["rwa"], (row["n11"] - row["req11"]) * row["rwa"])
        third = next(d for d in cell.decisions if d.period == "2026Q3")
        assert close(third.headroom[0], room, rel=1e-9) and third.headroom_final == third.headroom[0]
        # квартал с нехваткой и двумя решениями: сумма базовых дивидендов равна запасу, доли — по пулам
        base = plain_run((T_CAL,))
        crisis = base.cell(*T_CRISIS)
        by_q: dict = {}
        for d in crisis.decisions:
            if d.source == "model":
                by_q.setdefault(d.q, []).append(d)
        tight = [ds for ds in by_q.values() if len(ds) == 2 and ds[0].cut and sum(d.base_div for d in ds) > 1e-6]
        assert tight
        for ds in tight:
            h, want = ds[0].headroom[0], sum(d.want[0] for d in ds)
            assert 0 < h < want and close(sum(d.base_div for d in ds), h, rel=1e-12)
            assert all(close(d.base_div, h * d.want[0] / want, rel=1e-12) and d.cut for d in ds)
        assert not t_broken(base)
        # решение, которое вместе с соседним превышает запас, инвариант называет; избыток — внутри запаса
        a, b = next(ds for ds in by_q.values() if len(ds) == 2 and not ds[0].cut
                    and not any(d.period.endswith("Q4") for d in ds))
        grow = a.headroom[0] - (a.div + b.div) + 1.0
        assert a.div + grow < a.headroom[0]
        over = replace(a, base_div=a.base_div + grow, div=a.div + grow)
        changed = replace(crisis, decisions=tuple(over if d is a else d for d in crisis.decisions))
        bad = replace(base, cells=tuple(changed if c is crisis else c for c in base.cells))
        assert "dividend_bounds" in t_broken(bad)
        rich = next(c for c in base.cells if any(d.excess > 0 for d in c.decisions))
        d = next(d for d in rich.decisions if d.excess > 0)
        more = replace(d, excess=d.excess + (d.headroom[0] - d.div) + 1.0, div=d.headroom[0] + 1.0)
        changed = replace(rich, decisions=tuple(more if x is d else x for x in rich.decisions))
        bad = replace(base, cells=tuple(changed if c is rich else c for c in base.cells))
        assert "dividend_bounds" in t_broken(bad)

    def t_bridge_and_ex_dates_by_period() -> None:
        """Мост — строка на запись, вычет из BV модели — конец квартала клетки решения (у закрытого квартала прибыли —
        дата фактов); скачок на экс-дату = −DPS × N_out / N_div на каждой экс-дате года (М§8.1, §8.4)."""
        tbook = plain_book((T_CAL, T_BASIS))
        run = t_grid(tbook, register=T_FOUR[:2], day=day_(2026, 8, 20))
        rows = {r["period"]: r for r in run.bridge_rows}
        assert (rows["2026Q1"]["deducted_on"], rows["2026Q2"]["deducted_on"]) == (day_(2026, 9, 30), day_(2026, 12, 31))
        assert (rows["2026Q1"]["sign"], rows["2026Q1"]["pending"], rows["2026Q2"]["sign"]) == (-1, True, 0)
        closed = t_rec("2025Q4", 4.5, day_(2026, 7, 6), day_(2026, 5, 14), day_(2026, 7, 20), label="за 2025 год")
        row = t_grid(tbook, register=(closed,), day=day_(2026, 7, 2)).bridge_rows[0]
        assert (row["deducted_on"], row["sign"], row["pending"], row["label"]) == (day_(2026, 6, 30), 1, False, "за 2025 год")
        for i, rec in enumerate(T_FOUR):
            points = []
            for shift in (0, 1):
                ex = rec.ex_date + timedelta(days=shift)
                moved = DividendRecord(year=rec.year, dps=rec.dps, status=rec.status, record_date=ex,
                                       last_buy_date=ex - timedelta(days=1), ex_date=ex, pay_date=rec.pay_date,
                                       sources=rec.sources, period=rec.period, decided_date=rec.decided_date)
                last = t_grid(tbook, register=T_FOUR[:i] + (moved,) + T_FOUR[i + 1:], day=rec.ex_date)
                points.append(last.point)
            k = last.shares_out / last.divisor
            assert k < 0.99 and close(points[0] - points[1], -rec.dps * k, abs_=1e-7), (rec.period, points)

    def t_unregistered_dividend_by_quarters() -> None:
        """U — ожидание части дивиденда, решённой моделью, в закрытых к дате оценки кварталах сетки (М§14.4)."""
        tbook = plain_book((T_CAL,))
        ttl = plain_run((T_CAL,)).ctx.timeline
        run = t_grid(tbook, day=ttl.end(2))
        prob = run.layers["analytical"].prob
        want = sum(prob[c.key] * (c.quarters["div"][1] + c.quarters["div"][2]) for c in run.cells)
        assert want > 0 and close(run.unregistered_dividend, want, rel=1e-12)
        assert t_grid(tbook, day=ttl.end(1) - timedelta(days=1)).unregistered_dividend == 0.0
        with_records = t_grid(tbook, register=T_FOUR[:2], day=ttl.end(2))
        prob = with_records.layers["analytical"].prob
        third = sum(prob[c.key] * next(d.div for d in c.decisions if d.period == "2026Q3") for c in with_records.cells)
        assert third > 0 and close(with_records.unregistered_dividend, third, rel=1e-12)

    def t_terminal_without_pending_deduction() -> None:
        """Избыток капитала терминала — без дивидендов, решённых в последнем квартале сетки и ещё стоящих в
        регуляторном капитале; DDM = RI при решении в последнем квартале (М§7, §6.4)."""
        tbook, run = plain_book((T_CAL,)), plain_run((T_CAL,))
        ttl = run.ctx.timeline
        multiple = float(tbook.get("valuation.terminal.excess_capital_multiple"))
        for c in run.cells:
            q_ = c.quarters
            dpreg, rwa = q_["dpreg"][ttl.Q], q_["rwa"][ttl.Q]
            assert c.decisions[-1].q == ttl.Q and close(dpreg, c.decisions[-1].div, rel=1e-12), c.label
            x_t = multiple * min((q_["n20"][ttl.Q] - dpreg / rwa - q_["req20"][ttl.Q]) * rwa,
                                 (c.n11_star - dpreg / rwa - q_["req11"][ttl.Q]) * rwa)
            assert close(c.x_t, x_t, rel=1e-12), c.label
            assert abs(c.v_ddm - c.v_ri) <= 1e-12 * abs(c.v_ri), c.label
        assert any(c.decisions[-1].div > 1.0 for c in run.cells)

    def t_anchor_payable_state() -> None:
        """Состояние якоря: объявленная часть дивидендов к выплате — в очередях выплат и вычетов, остаток —
        постоянное обязательство (М§5.7.4)."""
        tbook = plain_book((T_CAL,))
        base = plain_run((T_CAL,))
        ttl = base.ctx.timeline
        payable = t_facts().need("balance", "dividends_payable")
        cell = base.cell(*T_REF)
        assert min(cell.quarters["dp"][q] for q in range(ttl.Q + 1)) >= payable - 1e-9
        declared = t_changed("balance", lambda d: d.update(dividends_payable_declared=[{"period": "2025Q4", "amount": 3.0}]))
        c = t_grid(tbook, declared).cell(*T_REF)
        assert close(c.quarters["dp"][1], payable - 3.0) and c.quarters["dpreg"][0] == 0.0
        assert close(c.quarters["pay"][1] - cell.quarters["pay"][1], 3.0, abs_=1e-6)
        rec = t_rec("2025Q4", 4.5, day_(2026, 7, 6), day_(2026, 5, 14), day_(2026, 10, 19))
        c2 = t_grid(tbook, declared, register=(rec,)).cell(*T_REF)
        assert c2.quarters["dpreg"][0] == 3.0 and close(c2.quarters["dp"][1], payable)
        assert close(c2.quarters["pay"][2] - c.quarters["pay"][2], 3.0, abs_=1e-6)

    def t_dps_of_the_year_with_closed_quarters() -> None:
        """DPS года — сумма четырёх кварталов прибыли: открытые — решения клетки, закрытые — строки истории;
        гейт потолка считает и их (М§5.7.5, §14.2)."""
        def closed(dps: float):
            def change(data):
                row = next(r for r in data["history"] if r["period"] == "2026Q1")
                row["decided_date"] = "2026-06-25"
                row["dps"]["v"] = dps
            return t_changed("dividends", change)

        tbook = plain_book((T_CAL, T_HISTORY))
        run = t_grid(tbook, closed(4.6))
        cell = run.cell(*T_REF)
        assert "2026Q1" not in cell.dps_q and cell.decisions[0].period == "2026Q2"
        assert close(cell.dps[2026], 4.6 + sum(cell.dps_q[f"2026Q{h}"] for h in (2, 3, 4)), rel=1e-12)
        assert "/".join(T_REF) not in t_gate(run, "payout_cap").cells
        fat = t_gate(t_grid(tbook, closed(15.0)), "payout_cap")
        assert fat.fired and "/".join(T_REF) in fat.cells and fat.mass > 0.99, fat.message

    def t_live_register_by_period() -> None:
        """Живой реестр при квартальном календаре: ключ записи — квартал прибыли; два правила годности; флаг
        реестра — по открытым кварталам и карте лагов (М§5.7.6, §15.1)."""
        from model.live import apply_live, check_register, register_gaps
        from tests.support_core2 import book_prices, outputs
        tbook, tf = plain_book((T_CAL,)), t_facts()
        src = ["manual: протокол собрания", "news: сообщение о решении"]
        q3 = {"year": 2026, "period": "2026Q3", "dps": 4.8, "status": "declared", "decided_date": "2026-10-05",
              "record_date": "2026-10-16", "last_buy_date": "2026-10-13", "ex_date": "2026-10-16",
              "pay_date": "2026-10-30", "sources": src}
        px = book_prices(tbook)
        day = day_(2026, 10, 14)
        live, report = apply_live(tbook, tf, outputs({t: [(day, px[t])] for t in px}, register=[q3]), today=day,
                                  previous={})
        assert [r.period for r in live.register] == ["2026Q1", "2026Q2", "2026Q3"], [r.period for r in live.register]
        assert [r["status"] for r in report.records] == ["paid", "declared", "declared"]
        no_period = {k: v for k, v in q3.items() if k != "period"}
        early = {**q3, "period": "2026Q1", "decided_date": "2026-06-25", "record_date": "2026-07-06",
                 "last_buy_date": "2026-07-03", "ex_date": "2026-07-06", "pay_date": "2026-07-20"}
        ok, bad = check_register([no_period, early, q3], price=330.0, quarterly=True, closed_period="2025Q4",
                                 facts_date=day_(2026, 6, 30))
        assert [r["period"] for r in ok] == ["2026Q3"] and len(bad) == 2, bad
        assert bad[0]["reason"] == "нет квартала прибыли" and "сначала правятся факты" in bad[1]["reason"]
        seeds = [{"period": p, "status": "declared"} for p in ("2026Q1", "2026Q2", "2026Q3")]
        assert register_gaps(tbook, seeds, day_(2027, 4, 5), tf) == []          # срок решения за 4К — конец 2К2027
        late = register_gaps(tbook, seeds, day_(2027, 7, 1), tf)
        assert len(late) == 1 and "2027Q2" in late[0] and "2027-06-30" in late[0], late
        assert len(register_gaps(tbook, [], day_(2026, 10, 1), tf)) == 1

    def t_decision_event_of_the_calendar() -> None:
        """Гейт ручного входа: событие «решение о дивиденде» за квартал прибыли просрочено, пока записи за него нет."""
        tbook = plain_book((T_CAL,))
        days = int(tbook.get("checks.manual_overdue_days.dividend_register"))
        today = day_(2026, 12, 31) + timedelta(days=days + 1)
        late = t_gate(t_grid(tbook), "manual_input_overdue", today=today)
        assert late.fired and "не в реестре" in late.message, late.message
        assert "не в реестре" not in t_gate(t_grid(tbook, register=(T_FOUR[2],)), "manual_input_overdue", today=today).message

    def t_release_by_periods() -> None:
        """Выпуск при квартальном календаре: записи одного года не сворачиваются; ближайшая выплата — по периоду;
        лестница без порога — одна строка; годовые суммы истории; выплата отчётных кварталов — оттоком; форвардная
        доходность — четыре квартала; нау-каст года — через окно базы (П§2, §7 п. 9)."""
        import dataclasses
        from model import payload as P
        from model.checks import check_gates
        from model.live import apply_live
        from tests.support_core2 import CONTROL_FIXTURE, book_prices, explained, outputs
        from tests.support_core_t import neutral_book
        tbook, tf = neutral_book(), t_facts()
        q3 = {"year": 2026, "period": "2026Q3", "label": "за девять месяцев 2026 года", "dps": 4.8, "status": "declared",
              "decided_date": "2026-10-05", "record_date": "2026-10-16", "last_buy_date": "2026-10-13",
              "ex_date": "2026-10-16", "pay_date": "2026-10-30",
              "sources": ["manual: протокол собрания", "news: сообщение о решении"]}
        px = book_prices(tbook)
        day = day_(2026, 10, 14)
        out = outputs({t: [(day, px[t])] for t in px}, register=[q3])
        live, _ = apply_live(tbook, tf, out, today=day, previous={})
        expl = explained(check_gates(run_grid(tbook, tf, live), today=day), today=day)
        rel = P.make_release(live=True, fast=True, today=day, book=tbook, facts=tf, outputs=out, explanations=expl,
                             notes=[], draws=4, control_model=CONTROL_FIXTURE)
        d = P.build_payload(rel)
        dv = d["dividends"]
        n_iss, n_out = tf.need("shares", "issued_total"), tf.need("shares", "outstanding_total")
        assert P._dividend_problems(d) == [], P._dividend_problems(d)
        assert dv["next_expected"]["period"] == "2026Q3" and dv["next_expected"]["dps"] == 4.8
        assert [e["period"] for e in d["market"]["ex_dividend"]] == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
        assert [(r["period"], r["in_bridge"]) for r in dv["register"]] == [("2026Q1", False), ("2026Q2", True),
                                                                          ("2026Q3", False)]
        assert [r["key"] for r in dv["ladder"]] == ["policy"] and dv["ladder"][0]["payout"] == 0.25
        model = {r["year"]: r for r in dv["model"]}
        assert model[2026]["declared"] is False
        mq = {r["period"]: r for r in dv["model_quarters"]}
        fwd = 4.8 + sum(mq[p]["dps_policy"] for p in ("2026Q4", "2027Q1", "2027Q2"))
        assert close(d["market"]["multiples"]["dividend_yield_fwd"]["T"], fwd / 330.0, abs_=2e-6)
        x = P._Ctx(rel)
        tl2 = rel.run.ctx.timeline
        decided = next(r for r in tf.files["dividends"]["history"] if r["period"] == "2025Q4")
        fact_qs = [q for q in tl2.quarters_of_year(2026) if q <= 0]
        assert close(P._fact_div_paid(x, 2026, fact_qs), decided["pool_declared"]["v"] * n_out / n_iss, rel=1e-12)
        # год без решения за четвёртый квартал прибыли — не завершён
        cut = copy.deepcopy(tf.files["dividends"])
        cut["history"] = [r for r in cut["history"] if r["period"] != "2025Q4"]
        short = copy.copy(rel)
        short.facts = dataclasses.replace(tf, files={**tf.files, "dividends": cut})
        annual = {r["year"]: r for r in P._history(P._Ctx(short))["annual"]}
        assert annual[2025]["dps"] is None and annual[2025]["payout"] is None
        assert close(annual[2024]["dps"], 9.25 + 3.20, rel=1e-12)
        # без записей: ближайшая выплата — первый открытый квартал, решение по которому не раньше квартала оценки
        bare = copy.copy(rel)
        bare.live = LiveInputs(valuation_date=day, prices=dict(live.prices), price_dates=dict(live.price_dates), register=())
        bare.run = run_grid(tbook, tf, bare.live)
        bare.live_report = dataclasses.replace(rel.live_report, records=[])
        ne = P._next_expected_quarterly(P._Ctx(bare))
        assert (ne["period"], ne["status"]) == ("2026Q2", "model") and bare.run.ctx.clock.q0 == 2, ne
        # нау-каст года: отклонение открытого квартала входит в базы решений модели, в окно которых он попадает
        plain_year = d["nowcast"]["year"]
        assert plain_year["dps"] == plain_year["dps_model"] == model[plain_year["year"]]["dps_policy"]
        period = d["nowcast"]["quarter"]["period"]
        expectation = d["next_report"]["expectation"]["ni"]
        target = {"ras_estimate": 1.0, "bridge": 1.0, "ras_bridged": expectation * 1.08, "w": 0.5, "rel_std_error": 0.03,
                  "sigma_ras": 0.03, "sigma_base": 0.06, "basis": "ifrs", "equation": "тест"}
        fed = copy.copy(rel)
        fed.indicators = outputs({t: [(day, px[t])] for t in px}, register=[q3], nowcast={
            "period": period, "ras": {"period": period, "targets": {"ni_q": target}, "months": [], "months_known": 2,
                                      "sigmas": {"base": 0.06}, "version": "тест"}})
        block = P._nowcast(P._Ctx(fed), dict(rel.next_report), dv["next_expected"])
        t1, year = block["quarter"]["by_target"]["ni_q"], block["year"]
        deviation = t1["forecast"] - t1["expectation"]
        open_idx, window = tl2.index(period), int(tbook.get("dividends.policy.base_window_quarters"))
        hit = sum(1 for o in rel.run.ctx.prep.calendar.open if o.year == year["year"] and o.dps is None
                  and o.idx - window + 1 <= open_idx <= o.idx)
        assert abs(deviation) > 0.5 and 0 < hit < window
        assert close(year["dps"] - plain_year["dps"], plain_year["payout"] * deviation * hit / window * 1000 / n_iss,
                     abs_=2e-4), (year["dps"], plain_year["dps"], deviation, hit)

    # ---------------------------------------------------------------- волна 3: рост, ограниченный капиталом (core_t)

    from tests import support_core_t3 as S3

    def t_growth_first_run():
        return S3.grid_of(**{"capital__growth_constraint__order": S3.GROWTH_FIRST})

    def t_growth_binding_ratio_equals_the_requirement() -> None:
        """Норматив связывающего равен требованию с глиссадой в допуске; решатель сошёлся — оба порядка (М§4.13.4)."""
        assert S3.check_binding(S3.grid_of()) > 100 and S3.check_binding(t_growth_first_run()) > 50
        assert not t_broken(S3.grid_of())

    def t_growth_requirement_glides() -> None:
        """Требование с глиссадой — формула М§4.13.1, и на примере методики."""
        from model.capital import glide_path
        S3.check_glide(S3.grid_of())
        req = [0.115] * 2 + [0.1225] * 4 + [0.135] * 6
        got = glide_path(req, 8, 0.0025)
        want = [0.12, 0.1225, 0.125, 0.1275, 0.13, 0.1325, 0.135, 0.135]
        assert all(close(a, b, abs_=1e-15) for a, b in zip(got, want)), got[:8]

    def t_growth_lambda_on_every_loan_book() -> None:
        """λ — одна на все кредитные книги; потенциальный путь — рост без ограничения (М§4.13.1)."""
        assert S3.check_lambda_on_all_books(S3.grid_of()) > 300

    def t_growth_step_is_the_final_step() -> None:
        """Запись шага — при итоговых объёмах и дивидендах; запас своего порядка и запас итоговых объёмов —
        оценки шага; избыток — после навёрстывания (М§4.13.2 пп. 2, 5–7)."""
        assert S3.check_replay(S3.grid_of()) > 100
        assert S3.check_replay(t_growth_first_run(), S3.REPLAY[:3]) > 60

    def t_growth_catch_up() -> None:
        """Навёрстывание — общая доля θ от (κ / 4) разрыва, пока норматив не ниже требования (М§4.13.2 п. 5)."""
        assert S3.check_catch_up(S3.grid_of()) > 300

    def t_growth_no_excess_when_cut() -> None:
        """При урезанном росте догоняющей выплаты и избытка нет (М§4.13.2 п. 6)."""
        assert S3.check_no_excess_when_cut() > 20

    def t_growth_secant_step() -> None:
        """Допуск строже отклонения закрытой формулы: шаг секущей доводит норматив до требования (М§4.13.2 п. 4)."""
        assert S3.check_binding(S3.grid_of(**{"capital__growth_constraint__tol": 1e-5})) > 100

    def t_growth_budget_of_step_evaluations() -> None:
        """В связывающем квартале шаг считается три раза; без решений модели и нехватки — один (М§4.13.2)."""
        S3.check_budget()

    def t_growth_shock_year_and_orders() -> None:
        """Год шока отменяет решения модели; порядок решает, что уступает первым (М§4.13, §5.5)."""
        S3.check_shock_year(S3.grid_of())
        S3.check_orders(S3.grid_of(), t_growth_first_run())

    def t_growth_outputs_and_gates() -> None:
        """Выходы клетки, гейты роста и сторожа правил книги, сводка прогона полосы (М§4.13.3, §10, §14.2)."""
        run = S3.grid_of()
        S3.check_outputs(run)
        S3.check_growth_gates(run)
        S3.check_summary(run)

    def t_growth_switch_and_steps() -> None:
        """Выключатель возвращает прежние числа; у ступеней пола дивиденд политики цел (М§4.13.4 пп. 3–4)."""
        run = S3.grid_of()
        S3.check_disabled(run)
        S3.check_steps(run)

    def t_rule_price_and_limits() -> None:
        """«Цена правила» и строки пределов обратного расчёта (М§11.3, §14.5)."""
        run = S3.grid_of()
        S3.check_rule_price(run)
        S3.check_limits(run)

    def t_release_of_the_growth_nodes() -> None:
        """Узлы панели в выпуске и чувствительность к запасу капитала (П§2, §7 п. 15; М§8.3)."""
        S3.check_release_nodes()
        S3.check_buffer_sensitivity()

    # ---------------------------------------------------------------- связка, гейты знака, обратный расчёт (core_t)

    from tests import support_core_t4 as S4

    def t_bundle_is_an_increment() -> None:
        """Связка: значение пути, сложение приращения со сдвигом оси shift, книга бит в бит в нуле, отказы (М§10)."""
        S4.check_bundle_values()
        S4.check_bundle_adds_to_shift()
        S4.check_bundle_zero_is_the_book()
        S4.check_bundle_refusals()

    def t_printed_margin_and_its_gate() -> None:
        """Печатаемая маржа после фазы роста — среднее годовых упр. ЧПМ модальной клетки; гейт `nim_lt` (М§14.2)."""
        S4.check_nim_lt()

    def t_sign_gates() -> None:
        """Гейты знака объёмных эффектов и знака стресса на построенных случаях (М§4.5, §14.2)."""
        S4.check_volume_sign_gate(extra=False)
        S4.check_stress_sign(extra=False)

    def t_payout_cap_tolerance() -> None:
        """Гейт потолка выплат: ровно на потолке — не превышение; допуск книги — в долях прибыли (М§14.2)."""
        S4.check_payout_cap_tolerance()

    def t_covered_quarter_gives_zero() -> None:
        """Закрытый квартал без своей строки истории даёт ноль; строка без DPS — отказ (М§5.7.5)."""
        S4.check_covered_quarter()

    def t_reverse_axis_and_the_edge_of_the_search() -> None:
        """Оба конца оси идут за проверяемым значением; корень на краю отрезка поиска; печатаемая маржа — у
        строки цели ЧПМ (М§11.2)."""
        S4.check_reverse_axis_follows()
        S4.check_edge_rule_and_printed_margin()

    def t_words_and_release_nodes() -> None:
        """Слова книги вместо литералов кода и узлы выпуска: коэффициент дробления, доходность за 12 месяцев,
        словарь терминов, база суммы дивиденда, сравниваемый норматив, числа гейтов знака (П§2, §7)."""
        S4.check_words_of_the_book()
        S4.check_release_nodes()

    # ---------------------------------------------------------------- мир-опора κ, уровни, варианты (core_t)

    from tests import support_core_t5 as S5

    def t_kappa_reference_world() -> None:
        """κ-добавка — к миру-опоре книги, любого знака; без ключа — к базовому миру, только вверх (М§4.6)."""
        S5.check_kappa_world()

    def t_fade_mode() -> None:
        """Угасание терминала при любом знаке избытка — только по ключу книги (М§7)."""
        S5.check_fade_symmetric()

    def t_level_gates() -> None:
        """Сторожа уровней на готовой сетке: стационарная маржа мира-цели, уровни слоя «рыночные ставки как есть»
        против окна фактов, область гейта долгосрочного C/I, стоимость средств клиентов к ключевой ставке (М§14.2)."""
        S5.check_nim_stationary()
        S5.check_levels()
        S5.check_cir_scope()
        S5.check_funds_cost()

    def t_point_path_and_variants() -> None:
        """Путь смеси точки рядом с модальной клеткой и справочные варианты таблиц книги (М§14.5)."""
        S5.check_point_path()
        S5.check_reference_variants()
        S5.check_variants_table()

    def t_range_edge_and_the_margin_fields() -> None:
        """Решение подвыборки у края диапазона; поля суждения о марже у строки цели ЧПМ (М§11.2)."""
        S5.check_near_range_edge()
        S5.check_stationary_fields()

    def t_release_nodes_of_the_levels() -> None:
        """Узлы выпуска: уровни и модальная клетка, числа сторожей, база массы знака стресса, варианты из таблиц
        книги, запас якоря с глиссадой, книга строки чувствительности (П§2, §7)."""
        S5.check_release_paths()
        S5.check_release_gate_numbers()
        S5.check_release_stress_basis()
        S5.check_release_variants_and_glide()
        S5.check_sensitivity_book()

    # ---------------------------------------------------------------- мир уровня, окно фактов, варианты (core_t)

    from tests import support_core_t6 as S6

    def t_level_world() -> None:
        """Ключ цели ЧПМ — стационарная маржа мира уровня; оси, чувствительность, узлы и строка обратного расчёта
        читают его так же (М§4.5, §11.2)."""
        S6.check_level_world()
        S6.check_level_world_axes()
        S6.check_level_world_row()

    def t_funds_premium_by_quarter() -> None:
        """Премия роста средств клиентов читается по кварталам, когда квартал задан ключом квартала или полугодия
        (М§4.3)."""
        S6.check_funds_premium_by_quarter()

    def t_window_of_facts() -> None:
        """Окно фактов — подузлом узла уровней и сведением в сообщении гейта; участок уровней — полные годы;
        стоимость риска года смеси — к кредитам по амортизированной стоимости (М§14.2, §14.5)."""
        S6.check_window_node()
        S6.check_level_years_and_cost_base()

    def t_refine_rows_and_premium_facts() -> None:
        """Список строк с уточнением на полной полосе; элементы премий роста, названные фактом (М§11.2, §11.3)."""
        S6.check_refine_rows()
        S6.check_premium_facts()

    def t_variants_note_order_and_fingerprint() -> None:
        """Справочные варианты: подпись, порядок по модулю цены, сверка отпечатка книги таблиц (М§14.5)."""
        S6.check_variants_note_and_order()
        S6.check_variants_fingerprint()

    def t_gate_words_and_release_remarks() -> None:
        """Знаки порога гейта стоимости средств, маржа якоря в сообщении гейта стыка, счётчики сводки контрольной
        модели, узел выпуска без слоя индикаторов и замечание сборки об устаревших таблицах (П§2, §7)."""
        S6.check_funds_cost_digits()
        S6.check_anchor_margin_words()
        S6.check_control_summary_counts()
        S6.check_release_words()

    def t_p1_draw_step() -> None:
        """Шаг хранения прогонов полосы — ключ книги: пример методики, полоса фикстуры, валидатор выпуска (М§10)."""
        from tests import support_core_p1 as P1
        P1.check_draw_step_example()
        P1.check_draw_step_band()
        P1.check_draw_step_validator()

    def t_p1_book_cor() -> None:
        """Множители CoR по кредитным книгам: пример методики, эквивалентности, резервы по книгам, гейт окна (М§4.6)."""
        from tests import support_core_p1 as P1
        P1.check_book_cor_example()
        P1.check_book_cor_schema()
        P1.check_book_cor_equivalences()
        P1.check_book_cor_quarters()
        P1.check_book_cor_gate_and_levels()

    def t_p1_opex_weights() -> None:
        """Драйвер расходов по себестоимости книг: пример методики, эквивалентности баз, тождество квартала, оценка шага
        без следов, отказы (М§4.7)."""
        from tests import support_core_p1 as P1
        P1.check_opex_weights_example()
        P1.check_opex_weights_quarters()
        P1.check_opex_weights_probe_leaves_no_trace()
        P1.check_opex_weights_equivalences()
        P1.check_opex_weights_refusals()

    def t_p1_terminal_block() -> None:
        """Постоянные в рублях части за концом сетки: пример методики, опорный счёт формул, сетка фикстуры (тождество,
        линейность, входы из прохода), ключи — параметры оценки (М§7)."""
        from tests import support_core_p1 as P1
        P1.check_terminal_example()
        P1.check_terminal_against_reference()
        P1.check_terminal_grid()
        P1.check_terminal_parts_and_pass()

    def t_p1_buyback() -> None:
        """Выкуп по цене мира: пример методики функциями ядра, нейтральность нулевой суммы, тождества и путь цены на
        сетке фикстуры, правила цены, год шока, ключ кэша проходов и живая цена, отказы (М§5.6)."""
        from tests import support_core_p1 as P1
        P1.check_buyback_example()
        P1.check_buyback_without_key_and_zero()
        P1.check_buyback_grid()
        P1.check_buyback_rules()
        P1.check_buyback_book_tables()
        P1.check_buyback_pass_key_and_live_price()
        P1.check_buyback_refusals()
        P1.check_buyback_bridge_dividend()

    def t_p1_release() -> None:
        """Выпуск со всеми ключами прохода: контракт, шаг хранения прогонов, узел постоянных частей терминала, оценка в
        цене клеток, годовая строка и мост норматива с выкупом (П§2)."""
        from tests import support_core_p1 as P1
        P1.check_release_with_pass_keys()

    def t_p2_wholesale() -> None:
        """К3: опт сверх структурной доли — пример методики, тождество с долей книги, гашение при избытке, WT_Q
        терминала, отказы (М§4.10)."""
        from tests import support_core_p2 as P2
        P2.check_wholesale_example()
        P2.check_wholesale_identity()
        P2.check_wholesale_quarters()
        P2.check_wholesale_refusals()

    def t_p2_allowance() -> None:
        """К7: резерв по книгам — пример методики, резерв якоря точно, равное покрытие — доля якоря, тождество квартала
        по остаткам книг, отказы фактов (М§4.6)."""
        from tests import support_core_p2 as P2
        P2.check_allowance_example()
        P2.check_allowance_anchor_and_equal_cover()
        P2.check_allowance_quarters()
        P2.check_allowance_refusals()

    def t_p2_guarantees() -> None:
        """К5: RWA гарантий — пример методики функциями ядра, тождество квартала (дрейф плотности, множитель режима),
        драйвер «строка комиссий» и база комиссий «номинал», номиналы из фактов, отказы (М§4.11)."""
        from tests import support_core_p2 as P2
        P2.check_guarantees_example()
        P2.check_guarantees_grid()
        P2.check_guarantees_fees_line()
        P2.check_guarantees_nominal_driver()
        P2.check_guarantees_anchor_and_refusals()

    def t_p2_stationary() -> None:
        """К4: терминал от стационарных ставок книг — пример методики, вход терминала по целям своего кода, явные ряды
        бит в бит, лёгкая сетка, ρ = 1 нейтрален (М§7)."""
        from tests import support_core_p2 as P2
        P2.check_stationary_example()
        P2.check_stationary_grid()
        P2.check_stationary_neutral_at_full_adjustment()

    def t_p2_lines() -> None:
        """К2: база связи по строке — пример методики, равносильности баз, тождество квартала (средства, номинал, смесь
        расходов), память шага и ряды-базы оценки, отказы; К5 с базой комиссий — книгой выреза (М§4.7, §4.11)."""
        from tests import support_core_p2 as P2
        P2.check_lines_example()
        P2.check_lines_equivalences()
        P2.check_lines_quarters()
        P2.check_lines_memo_and_trace()
        P2.check_lines_refusals()
        P2.check_guarantees_driver_is_the_carve_book()

    def t_p2_driven() -> None:
        """К6: книга-обязательство за драйвером строки — пример методики, тождество квартала при связи 0,5 / 0 / 1,
        драйвер на «номинале» при связи 0,5 и 1, память стороны средств, отказы (М§4.3)."""
        from tests import support_core_p2 as P2
        P2.check_driven_example()
        P2.check_driven_quarters()
        P2.check_driven_nominal()
        P2.check_driven_memo()
        P2.check_driven_refusals()

    def t_p2_token() -> None:
        """К1: жетон DPS — пример методики функциями ядра, тождества года с жетоном и отказа по полу на сетке (и при
        выкупе), нейтральность нуля, ключ неактивного режима, монотонность, сброс памяти при повторе (М§4.13.2)."""
        from tests import support_core_p2 as P2
        P2.check_token_example()
        P2.check_token_grid()
        P2.check_token_monotone()
        P2.check_token_memory_reset()

    def t_p3_year() -> None:
        """К-Т2а: год терминала по средней длине года (М§7)."""
        from tests import support_core_p3 as P3
        P3.check_year_example()
        P3.check_year_grid()
        P3.check_year_with_stationary_and_block()
        P3.check_year_not_leap()
        P3.check_year_schema()

    def t_p3_fade() -> None:
        """К-Т2в: угасание по календарю (М§7)."""
        from tests import support_core_p3 as P3
        P3.check_fade_example()
        P3.check_fade_grid()
        P3.check_fade_block_and_symmetric()
        P3.check_fade_schema()

    def t_p3_funding() -> None:
        """К-Т2б: ставка фондирования блока К-Т по правилу балансирующих статей (М§7, §4.10)."""
        from tests import support_core_p3 as P3
        P3.check_funding_example()
        P3.check_funding_grid()
        P3.check_funding_schema()

    def t_p3_cash() -> None:
        """К8: неработающие деньги за средствами клиентов (М§4.3, §4.11)."""
        from tests import support_core_p3 as P3
        P3.check_cash_example()
        P3.check_cash_grid()
        P3.check_cash_equivalences()
        P3.check_cash_memo()
        P3.check_cash_anchor_and_refusals()

    def t_p3_mix() -> None:
        """К2б: смесь баз строки (М§4.7)."""
        from tests import support_core_p3 as P3
        P3.check_mix_example()
        P3.check_mix_refusals()
        P3.check_mix_equivalences()
        P3.check_mix_guarantees_and_driven()
        P3.check_mix_shares_and_memo()

    def t_p3_release() -> None:
        """Выпуск с ключами третьего прохода: контракт, узлы клетки и поля блока К-Т — только при ключах (П§2)."""
        from tests import support_core_p3 as P3
        P3.check_release_with_pass3_keys()

    # ---------------------------------------------------------------- четвёртый проход ядра (core-pass4)

    def t_p4_k5() -> None:
        """Р5-5: драйвер RWA гарантий — компонента смеси базы комиссий: равносильности G1–G3, G/D^c от долей смеси не
        зависит (G4, G6), компонента = книга выреза ≡ К5 выключен (G5), отказы, пример, лист предельной экономики."""
        from tests import support_core_p4 as P4
        P4.check_k5_neutral()
        P4.check_k5_mix_invariance()
        P4.check_k5_carve_identity()
        P4.check_k5_refusals()
        P4.check_k5_example()
        P4.check_k5_marginal()

    def t_p4_mult() -> None:
        """Р5-6: корень множителем — равносильности I1, I2, I6; квартал I4, I5; класс 2 (I3); форма корня — вход
        прохода каждого мира (М§4.7)."""
        from tests import support_core_p4 as P4
        P4.check_mult_neutral()
        P4.check_mult_override_year()
        P4.check_mult_quarter()
        P4.check_mult_class2()
        P4.check_mult_fingerprint()

    def t_p4_bundle_sum() -> None:
        """Р5-4: связки на общем пути — сумма приращений от центра корневой книги, fsum, порядок осей не важен; без
        ключа — прежний отказ; на книге-копии подмена сохраняется; ноль — книга (М§10)."""
        from tests import support_core_p4 as P4
        P4.check_bundle_refusal_without_key()
        P4.check_bundle_sum()
        P4.check_bundle_sum_fsum()
        P4.check_bundle_trial_centre()
        P4.check_bundle_zero()
        P4.check_bundle_reverse_row_keeps_its_value()

    def t_p4_bundle_rules() -> None:
        """Р5-4: без общих путей — бит в бит; первый путь — свой у каждой оси (только при ключе); правило углов (со
        сдвигом траектории); value / dict — отказ; цена конца оси; полоса по записям; перенос якоря — концы двух связок
        общего пути идут за центром один раз (М§10, §15.2)."""
        from tests import support_core_p4 as P4
        P4.check_bundle_no_overlap_bit_for_bit()
        P4.check_bundle_first_path_unique()
        P4.check_bundle_corner_rule()
        P4.check_bundle_corners_only_on_the_root_book()
        P4.check_bundle_value_dict_overlap()
        P4.check_bundle_axis_end_price()
        P4.check_bundle_band_like()
        P4.check_reanchor_shared_path()

    def t_p4_sheet() -> None:
        """Р5-4, лист вывода: корни расходов на концах оси базы строки — в самой связке (все пути), записью рядом (ни
        одного), остановка (часть)."""
        from tests import support_core_p4 as P4
        P4.check_sheet_base_axis_opex()

    def t_p4_release() -> None:
        """Выпуск фикстуры со всеми ключами прохода 4 — контракт выполнен (узлов ключи не добавляют)."""
        from tests import support_core_p4 as P4
        P4.check_release_with_pass4_keys()

    # ---------------------------------------------------------------- пятый проход ядра (core-pass5)

    def t_p5_neutral() -> None:
        """Р6-1: share: anchor ≡ К8 без доли книги, θ = 1 ≡ поля нет — бит в бит; драйвер «кредиты» с share: anchor ≡
        К8 выключен (ловушка варианта cash_with_loans); книга Совкомбанка — share: anchor бит в бит, якорь — факт; доля
        книги подменой на книге с share: anchor — ядро читает узел ФОР само (≡ книга с выведенным ФОР, бит в бит)."""
        from tests import support_core_p5 as P5
        P5.check_neutral()
        P5.check_variant_trap()
        P5.check_neutral_bank()
        P5.check_overrides_reserves_anchor()

    def t_p5_example() -> None:
        """Р6-1: пример методики на книге Совкомбанка — путь, ρ′_q, слагаемое, вырез на факте, RWA квартала, θ —
        линейная смесь концов; θ = 0 с шагом ≡ вырез на раскладке книги (Д1) на книге Совкомбанка."""
        from tests import support_core_p5 as P5
        P5.check_example()
        P5.check_step_identity_bank()

    def t_p5_grid() -> None:
        """Р6-1: каждая клетка и квартал фикстуры — деньги по пути, прочие активы, RWA со слагаемым под дрейфом
        плотности, валютным индексом и множителем режима; θ = 0 с шагом ≡ вырез на раскладке книги (Д1)."""
        from tests import support_core_p5 as P5
        P5.check_grid()
        P5.check_step_identity()

    def t_p5_path() -> None:
        """Р6-1: путь доли (шаг, монотонность, доля книги с квартала share_from ровно), ряд класса 5 cash_share, входы
        прохода каждого мира."""
        from tests import support_core_p5 as P5
        P5.check_path()
        P5.check_fingerprint()

    def t_p5_memo() -> None:
        """Р6-1: память оценок шага и лёгкая оценка нормативов несут слагаемое вытесненной части."""
        from tests import support_core_p5 as P5
        P5.check_memo_and_light()

    def t_p5_refusals() -> None:
        """Р6-1: отказы схемы и ядра."""
        from tests import support_core_p5 as P5
        P5.check_refusals()

    # ---------------------------------------------------------------- шестой проход ядра (core-pass6)

    def t_p6_neutral() -> None:
        """Р8-6: пустой словарь ≡ без ключа; доля франшизы 0 и связь расходов 0 — ключ не читается; связь строки 1 с
        ключом ≡ без ключа — бит в бит (фикстура и книга дерева)."""
        from tests import support_core_p6 as P6
        P6.check_neutral()
        P6.check_neutral_bank()

    def t_p6_example() -> None:
        """Р8-6: пример методики точными дробями; ядро против формулы в каждой клетке книги дерева с κ примера."""
        from tests import support_core_p6 as P6
        P6.check_example()
        P6.check_grid_bank()

    def t_p6_grid() -> None:
        """Р8-6: ядро против формулы в каждой клетке и квартале фикстуры (связь страхования 0,5, 0, 0,3; κ = 0);
        непрерывность по связи у 0 и 1."""
        from tests import support_core_p6 as P6
        P6.check_grid()
        P6.check_continuity()

    def t_p6_layer() -> None:
        """Р8-6: неподвижная точка κ — слой M на базе строки до 2029К4, κ = 0 дальше; миры относительно слоя M у
        франшизы и строки — те же (книга дерева)."""
        from tests import support_core_p6 as P6
        P6.check_layer_fixture()
        P6.check_layer_and_worlds_bank()

    def t_p6_path() -> None:
        """Р8-6: ключ, κ и связь строки — входы прохода каждого мира."""
        from tests import support_core_p6 as P6
        P6.check_fingerprint()

    def t_p6_memo() -> None:
        """Р8-6: память оценок шага и лёгкая оценка несут номинальную часть; договор оценки шага (STEP_FLOWS)."""
        from tests import support_core_p6 as P6
        P6.check_memo_and_light()

    def t_p6_refusals() -> None:
        """Р8-6: отказы схемы; ключ неактивного режима — не отказ."""
        from tests import support_core_p6 as P6
        P6.check_refusals()

    # ---------------------------------------------------------------- седьмой проход ядра (core-pass7)

    def t_p7_neutral() -> None:
        """Р9-1: без ключа, {}, ρ ≡ 0, К6 снят, ключ строки без ведомой книги, связь строки 1 — бит в бит (книга дерева
        и фикстура)."""
        from tests import support_core_p7 as P7
        P7.check_neutral_bank()
        P7.check_neutral_fixture()

    def t_p7_example() -> None:
        """Р9-1: пример методики точными дробями (цепь, телескоп, правило ρ, Йенсен)."""
        from tests import support_core_p7 as P7
        P7.check_example()

    def t_p7_grid() -> None:
        """Р9-1: ядро против формулы в каждой клетке и квартале (фикстура: связь 0,5, 0, 0,3, 1; ρ ≡ 0 и числом; книга
        за строкой комиссий; книга дерева с ρ примера); ряд vol_end_*; непрерывность по связи у 0 и 1."""
        from tests import support_core_p7 as P7
        P7.check_grid()
        P7.check_continuity()

    def t_p7_layer() -> None:
        """Р9-1: слой M — номинал с корнем на ожидании базы до 2029К4, Йенсен, прежняя цепь с 2030 года; неподвижная
        точка ρ (книга дерева и фикстура)."""
        from tests import support_core_p7 as P7
        P7.check_layer_bank()
        P7.check_layer_fixture()

    def t_p7_worlds() -> None:
        """Р9-1: ρ общий для миров — отношения миров у К6 с ключом и без; дрейф К6 как у строки."""
        from tests import support_core_p7 as P7
        P7.check_worlds_bank()

    def t_p7_path() -> None:
        """Р9-1: ключ, ρ и связь строки — входы прохода каждого мира."""
        from tests import support_core_p7 as P7
        P7.check_fingerprint()

    def t_p7_memo() -> None:
        """Р9-1: память оценок шага несёт корень и ряд уровня базы; ряд vol_end_* вне STEP_FLOWS."""
        from tests import support_core_p7 as P7
        P7.check_memo_and_light()

    def t_p7_refusals() -> None:
        """Р9-1: отказы схемы; ключ неактивного режима — не отказ."""
        from tests import support_core_p7 as P7
        P7.check_refusals()

    # ---------------------------------------------------------------- восьмой проход ядра (core-pass8)

    def t_p8_neutral() -> None:
        """Р10-5, Р10-6, ключ (3): без ключей, mixed, modal_cell, all и line в неактивных режимах — бит в бит (книга
        дерева, Т-книга, фикстура)."""
        from tests import support_core_p8 as P8
        P8.check_neutral_bank()
        P8.check_neutral_fixture()

    def t_p8_example() -> None:
        """Р10-5, Р10-6: пример методики точными дробями (link_growth ядра, Φ, Ψ, правило κ, гейт мира)."""
        from tests import support_core_p8 as P8
        P8.check_example()

    def t_p8_grid() -> None:
        """Р10-5: ядро против формулы в каждой клетке и квартале (фикстура, книга дерева), Φ / INS одинаково, пределы
        λ = 0 и 1, непрерывность по связи."""
        from tests import support_core_p8 as P8
        P8.check_grid()
        P8.check_limits()
        P8.check_continuity()

    def t_p8_layer() -> None:
        """Р10-5: неподвижная точка κ, ρ правилом листа своим счётом, слой M, дрейф франшизы как у строки."""
        from tests import support_core_p8 as P8
        P8.check_layer_bank()
        P8.check_layer_fixture()
        P8.check_drift_bank()

    def t_p8_path() -> None:
        """Р10-5: ключ формы, κ, ρ и связь — входы прохода каждого мира."""
        from tests import support_core_p8 as P8
        P8.check_fingerprint()

    def t_p8_memo() -> None:
        """Р10-5: память оценок шага несёт Φ, Ψ и ряд лага D; ряд vol_end_* — вне STEP_FLOWS."""
        from tests import support_core_p8 as P8
        P8.check_memo()

    def t_p8_refusals() -> None:
        """Р10-5, Р10-6, ключ (3): отказы схемы; нет конца истории D — FactsError; D ≤ 0 — BookError с меткой клетки."""
        from tests import support_core_p8 as P8
        P8.check_refusals()

    def t_p8_gate() -> None:
        """Р10-6 и ключ (3): гейт мира — независимый счёт, срабатывание только на ожидании, нулевой вес мира; средства
        клиентов без К6 в обоих гейтах и пути фондирования."""
        from tests import support_core_p8 as P8
        P8.check_gate()
        P8.check_client_funds()

    def t_p8_sheet() -> None:
        """Лист вывода (Р10-5, Р10-6, Р10-13): κ и ρ формы строки, коридор ρ по форме, оба числа на концах, низ оси φ —
        функция ядра."""
        from tests import support_core_p8 as P8
        P8.check_sheet_roots()
        P8.check_sheet_spec()
        P8.check_sheet_ends()
        P8.check_sheet_phi_axis()

    # ---------------------------------------------------------------- девятый проход ядра (core-pass9)

    def t_p9_neutral() -> None:
        """Р11-1, Р11-2, Р11-3: без ключей, доли 0, all и clients без К6 — бит в бит (книга дерева, Т-книга)."""
        from tests import support_core_p9 as P9
        P9.check_neutral_bank()
        P9.check_neutral_fixture()

    def t_p9_example() -> None:
        """Пример методики точными дробями; якорь доли опта; терминал ядра с НДУ в рублях (NI_T+1, m_L, вклады в TV)."""
        from tests import support_core_p9 as P9
        P9.check_example()

    def t_p9_rates() -> None:
        """Р11-1: цели ставок, LT-спред, Nss по книгам, наклоны — свой счёт; шаг — рекурсия целей; T_real = T*; мир H."""
        from tests import support_core_p9 as P9
        P9.check_rates_bank()
        P9.check_h_world()

    def t_p9_funds() -> None:
        """Р11-2: опт − добор = s × средства клиентов, якорь, тождество баланса своим счётом, слово funds баз строк;
        память стороны средств, деньги К8 словом funds, база связи link_base funds (история и квартал)."""
        from tests import support_core_p9 as P9
        P9.check_funds_bank()
        P9.check_funds_words()
        P9.check_funds_memo_and_link_base()

    def t_p9_nci() -> None:
        """Р11-3: ni − ni_sh = НДУ × индекс цен мира, доля 0, NCI_L терминала, DDM = RI."""
        from tests import support_core_p9 as P9
        P9.check_nci_bank()

    def t_p9_refusals() -> None:
        """Отказы схемы трёх ключей и правило «одно слово — одна величина»."""
        from tests import support_core_p9 as P9
        P9.check_refusals()

    def t_p9_sheet() -> None:
        """Листы: бэктест книг на наклонах ядра, средства клиентов листов, класс 6 — наклоны книг по типам."""
        from tests import support_core_p9 as P9
        P9.check_sheet_backtest()
        P9.check_sheet_funds()
        P9.check_class_slopes()

    def t_funding_path_and_names() -> None:
        """Путь фондирования — отношение ожидаемых остатков под вероятностями точки и доля гейта; узлы выпуска и
        заголовок инварианта передачи — при своих ключах книги (М§14.5, П§2)."""
        S6.check_funding_path()
        S6.check_release_funding_and_names()

    return {f.__name__: f for f in (invariants, llp_shift_exact, interest_legs_simple, kappa_zero_in_n,
                                    dps_is_pool_over_issued, exdate_jump_with_governance,
                                    h_world_independent_of_phi, cor_path_bridged_once,
                                    deductions_scale_with_rwa, unaudited_by_calendar,
                                    unaudited_loss_in_base_capital, dividend_bound_is_the_headroom,
                                    probabilities_are_not_negative,
                                    agm_quarter_neutral_for_capital, apu_cap_per_observation,
                                    ddm_ri_mid_quarter, lhs_order, quantile_type_7, quarter_end_continuity,
                                    sigma0_from_year, epsilon_ramp, misc_quarter_profile,
                                    apu_layer_average_is_observation, terminal_closed_form, dia_leg_from_book,
                                    kappa_lag_closed_form, cor_includes_kappa, first_dy_from_anchor_curve,
                                    la_minimum_binds, fvc_reference_regime, pending_dividend_without_discount,
                                    roll_is_end_of_day, apu_window, apu_frozen_expectations,
                                    crisis_skip_is_not_a_cut, sigma0_split_closed_form, lt_spread_closed_form,
                                    neutral_edge_tolerance, guidance_point_tolerance, mean_shift_formula,
                                    phi_split_closed_form, phi_remainder_reaches_liabilities, fade_is_one_sided,
                                    fvc_reference_is_the_book_before_the_draw, regime_floor,
                                    year_with_reported_quarters, unregistered_dividend_closed_form,
                                    median_shift_window, neutral_search_goes_inside_the_bracket,
                                    nowcast_year_on_one_layer, refine_takes_the_secant_step,
                                    in_range_is_about_the_root, point_neutral_goes_inside_the_bracket,
                                    lt_floor_at_the_ends_of_share_axes,
                                    schema_name_is_the_key_of_the_book, book_title_keeps_abbreviations,
                                    guidance_gate_reads_the_gate_flag, pending_branch_refuses,
                                    label_fields_are_closed, inactive_calendar_key_refuses, record_label_by_period,
                                    corridor_words_from_the_book, issued_divisor_needs_one_ticker,
                                    growth_constraint_needs_the_quarterly_calendar,
                                    t_divisor_scales_the_price, t_exdate_jump_on_the_divisor, t_history_cap,
                                    t_payout_cap_gate, t_volume_link_closed_form, t_premium_by_sector,
                                    t_fixed_other_assets, t_regime_rwa_multiplier, t_guidance_growth_nodes,
                                    t_estimated_capital, t_release_on_the_divisor,
                                    t_quarter_calendar_by_the_lag_map, t_quarter_queues, t_base_is_the_window_mean,
                                    t_excess_once_a_year, t_shock_year_cancels_quarterly_decisions,
                                    t_register_by_period, t_room_of_the_quarter, t_bridge_and_ex_dates_by_period,
                                    t_unregistered_dividend_by_quarters, t_terminal_without_pending_deduction,
                                    t_anchor_payable_state, t_dps_of_the_year_with_closed_quarters,
                                    t_live_register_by_period, t_decision_event_of_the_calendar,
                                    t_release_by_periods,
                                    t_growth_binding_ratio_equals_the_requirement, t_growth_requirement_glides,
                                    t_growth_lambda_on_every_loan_book, t_growth_step_is_the_final_step,
                                    t_growth_catch_up, t_growth_no_excess_when_cut, t_growth_secant_step,
                                    t_growth_budget_of_step_evaluations, t_growth_shock_year_and_orders,
                                    t_growth_outputs_and_gates, t_growth_switch_and_steps, t_rule_price_and_limits,
                                    t_release_of_the_growth_nodes,
                                    t_bundle_is_an_increment, t_printed_margin_and_its_gate, t_sign_gates,
                                    t_payout_cap_tolerance, t_covered_quarter_gives_zero,
                                    t_reverse_axis_and_the_edge_of_the_search, t_words_and_release_nodes,
                                    t_kappa_reference_world, t_fade_mode, t_level_gates, t_point_path_and_variants,
                                    t_range_edge_and_the_margin_fields, t_release_nodes_of_the_levels,
                                    t_level_world, t_funds_premium_by_quarter, t_window_of_facts,
                                    t_refine_rows_and_premium_facts,
                                    t_variants_note_order_and_fingerprint, t_gate_words_and_release_remarks,
                                    t_funding_path_and_names, t_p1_draw_step,
                                    t_p1_book_cor, t_p1_opex_weights, t_p1_terminal_block,
                                    t_p1_buyback, t_p1_release, t_p2_wholesale, t_p2_allowance,
                                    t_p2_guarantees, t_p2_stationary, t_p2_lines, t_p2_driven, t_p2_token,
                                    t_p3_year, t_p3_fade, t_p3_funding, t_p3_cash, t_p3_mix,
                                    t_p3_release, t_p4_k5, t_p4_mult, t_p4_bundle_sum, t_p4_bundle_rules,
                                    t_p4_sheet, t_p4_release, t_p5_neutral, t_p5_example, t_p5_grid, t_p5_path,
                                    t_p5_memo, t_p5_refusals, t_p6_neutral, t_p6_example, t_p6_grid, t_p6_layer,
                                    t_p6_path, t_p6_memo, t_p6_refusals, t_p7_neutral, t_p7_example, t_p7_grid,
                                    t_p7_layer, t_p7_worlds, t_p7_path, t_p7_memo, t_p7_refusals, t_p8_neutral,
                                    t_p8_example, t_p8_grid, t_p8_layer, t_p8_path, t_p8_memo, t_p8_refusals,
                                    t_p8_gate, t_p8_sheet, t_p9_neutral, t_p9_example, t_p9_rates, t_p9_funds,
                                    t_p9_nci, t_p9_refusals, t_p9_sheet)}


def main(argv: list[str]) -> int:
    if "--check" not in argv:
        print("использование: python -m tests.mutations --check [--only проверка,проверка… | --only=НАЧАЛО_ИМЕНИ]")
        return 64
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv[:-1] else None
    prefix = next((a.split("=", 1)[1] for a in argv if a.startswith("--only=")), None)
    result: dict[str, str] = {}
    try:
        checks = _checks()
    except Exception as exc:                      # мутант может сломать и подготовку
        print(json.dumps({"_setup": f"{type(exc).__name__}: {exc}"[:500]}, ensure_ascii=False))
        return 0
    if only is not None:                          # порядок проверок — прежний; имени нет — не «ok» и не поимка
        unknown = sorted(only - set(checks))
        if unknown:
            result["_only"] = f"нет проверок: {', '.join(unknown)}"[:300]
        checks = {name: fn for name, fn in checks.items() if name in only}
    for name, fn in checks.items():
        if prefix is not None and not name.startswith(prefix):
            continue
        try:
            fn()
            result[name] = "ok"
        except Exception as exc:
            result[name] = f"{type(exc).__name__}: {exc}"[:300]
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
