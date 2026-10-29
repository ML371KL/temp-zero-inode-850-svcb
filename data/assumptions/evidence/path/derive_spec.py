# -*- coding: utf-8 -*-
"""Описание вывода на ядре для команды перевывода книги (`ops/tools/rederive.py`) — КНИГА СОВКОМБАНКА (фаза 3, 21.10.2026).

Правил шагов здесь нет — они в листе рядом (`derive_on_engine.py`). Здесь то, чего лист не знает: адрес числа в шаблоне,
точность его записи, коридор разумного и невязки правил, при которых запись останавливается. Команда берёт перечень шагов,
их порядок, ключи записи и коридоры ОТСЮДА (интерфейс описания — как у книги Т: SHEET, STEPS, LINKED, RECORD, PHASES,
WRITES, SAME, RESIDUALS, relations(), DEADBAND_UNITS, GATES, GATE_FACTS, COMPANIONS, MARGINAL, ACCEPTANCE, REMINDERS).

Шаги Совкомбанка (порядок engine-port §5 и задания сборщика): мост упр. ↔ движок (ключ уровня и цель передачи из суждений
в опр. банка) → вычеты и плотность якоря числами → ближние ключи спредов книг → проверка уровня → доли σ0 и φ → ближний сдвиг
маржи на ожидании слоя «свой взгляд» (решения № 9, класс 2; было — модальная клетка) → корни расходов, комиссий и страхования
под уровни устава к средним активам в слое «рыночные ставки как есть» (рост г/г года якоря — ожидание слоя «свой взгляд») →
решатель на оси передачи → концы осей и проверки (нужда баланса премии средств — на ожидании слоя «свой взгляд», Р9-2).

Адрес — кортеж: строка — ключ словаря, число — номер в списке, словарь — отбор элемента списка по его полям. Место числа в
записи листа — кортеж либо функция от записи. Коридор — список (маска подключа, низ, верх, почему): первая подошедшая маска;
у числа подключ пуст; маска без низа и верха — «коридора нет» (число не выводится, а переносится).
"""
from __future__ import annotations

from pathlib import Path

import derive_on_engine as sheet

GATES = (("checks",),)
GATE_FACTS = (("checks", "window_backtest"), ("checks", "cir_lt"))   # Р4-10: цель cir_lt — из уровня окна на базе М13 (не порог)
# Решения ведущего № 10, Р10-16: пороги гейтов после правок книги пишет КОМАНДА по правилу листа (ведущий не переносит руками) —
# коридор доли оптового фондирования и порог стоимости средств к ключевой (наибольший квартал окна R на величине числа гейта ядра)
GATE_RULES = (("checks", "wholesale_share"), ("checks", "funds_cost_to_key", "max"))
SHEET = "derive_on_engine.py"
# Решения ведущего № 11, Р11-6: главные развилки устава §6 — всегда сухим перевыводом (forks_rd), какой бы ни был замер отхода пути:
# маржа (№ 1), стоимость риска (№ 3), M&A (№ 4), выкуп (№ 5); замыкание капитала (№ 2, closure_as_t) — в книге не стоит (Р11-14)
MAIN_FORKS = ("margin_hump_new_level", "margin_middle", "cor_retail_tail", "serial_acquirer", "buyback_none")

# Развилки книги сухим перевыводом (инструмент `ops/tools/forks.py`, запись `data/assumptions/forks_rd.json`; MODEL §14.5): цена
# варианта — книга, перевыведенная под вариант как центр шаблона копии дерева. Правка строки таблиц — `FORKS` (нет строки — подмены
# варианта книги `var:<id>`), замыкания капитала — `RULE_FORKS` (замыкание книги — сама книга, `base`). Правки, которых подменами
# книги не выразить, — `FORK_PATCHES`: текст листа вывода в копии (пути — от каталога книги), значения шаблона, поля оси полосы.
FORK_PATCHES = {
    # маржа устава §6 (№ 1): уровень мира — константы листа, ось уровня сдвинута вместе с центром, передача — центр оси
    "hump": {"why": "«горб» 2026 года — новый уровень: мир M, ЧПМ опр. банка 6,8 %, передача −0,10",
             "text": [('evidence/path/derive_on_engine.py', 'NIM_BANK_N = 0.0717 ', 'NIM_BANK_N = 0.068 '),
                  ('evidence/path/derive_on_engine.py', 'NIM_BANK_AXIS = (0.0692, 0.0728) ', 'NIM_BANK_AXIS = (0.065500, 0.069100) '),
                  ('evidence/path/derive_on_engine.py', 'LEVEL_WORLD_EXPECTED = "N" ', 'LEVEL_WORLD_EXPECTED = "M" '),
                  ('evidence/path/derive_on_engine.py', 'TRANSMISSION_BANK = -0.06 ', 'TRANSMISSION_BANK = -0.1 ')],
             "book": {"nii.transmission.level_world": "M"}},
    "middle": {"why": "середина: мир M, ЧПМ опр. банка 6,4 %, передача −0,06",
               "text": [('evidence/path/derive_on_engine.py', 'NIM_BANK_N = 0.0717 ', 'NIM_BANK_N = 0.064 '),
                  ('evidence/path/derive_on_engine.py', 'NIM_BANK_AXIS = (0.0692, 0.0728) ', 'NIM_BANK_AXIS = (0.061500, 0.065100) '),
                  ('evidence/path/derive_on_engine.py', 'LEVEL_WORLD_EXPECTED = "N" ', 'LEVEL_WORLD_EXPECTED = "M" ')],
               "book": {"nii.transmission.level_world": "M"}},
    "nimL": {"why": "уровень мира N на составе окна L: ЧПМ опр. банка 6,60 %",
             "text": [('evidence/path/derive_on_engine.py', 'NIM_BANK_N = 0.0717 ', 'NIM_BANK_N = 0.066 '),
                  ('evidence/path/derive_on_engine.py', 'NIM_BANK_AXIS = (0.0692, 0.0728) ', 'NIM_BANK_AXIS = (0.063500, 0.067100) ')]},
    "bridgelit": {"why": "мост банк ↔ движок буквально: ключ 0,0717, передача −0,0501; ось уровня и передачи — те же сдвиги от центра",
                  "text": [('evidence/path/derive_on_engine.py',
                            "    key = round(key_of(t, NIM_BANK_N, world), 6)\n    target = round(target_of(t, TRANSMISSION_BANK), 6)\n"
                            "    key_axis = [round(key_of(t, x, world), 6) for x in NIM_BANK_AXIS]\n"
                            "    tr_axis = [round(target_of(t, x), 6) for x in TRANSMISSION_BANK_AXIS]\n",
                            "    key = 0.0717\n    target = -0.0501\n"
                            "    key_axis = [round(key + key_of(t, x, world) - key_of(t, NIM_BANK_N, world), 6) for x in NIM_BANK_AXIS]\n"
                            "    tr_axis = [round(target + target_of(t, x) - target_of(t, TRANSMISSION_BANK), 6) for x in TRANSMISSION_BANK_AXIS]\n")]},
    # корень ρ книги К6 не выводится: ρ остаётся как в шаблоне (вариант k6_root_off — нули)
    "norho": {"why": "корень ρ книги страховых не выводится",
              "text": [('evidence/path/derive_spec.py', "_DRIVER_ROOTS = _template_value(" "sheet.DRIVER_ROOTS) or {}", "_DRIVER_ROOTS = {}"),   # строка разбита: текст правки — не место правки
                       ('evidence/path/derive_on_engine.py',
                        "    v = book_opt(eng, DRIVER_ROOTS)\n    led = {str(x) for x in (book_opt(eng, \"volumes.liability_drivers\") or {}).values()}\n"
                        "    return [str(k) for k in (v or {}) if str(k) in led]",
                        "    return []")]},
    # допуски концов связок κ и ρ вдвое — только для цены развилки, чей перевод останавливают только они (центр сошёлся):
    # точка — точная цена (концы осей точку не двигают), медиана — с пометкой
    "looseends": {"why": "допуски концов связок κ и ρ вдвое",
                  "text": [('evidence/path/derive_on_engine.py', "KAPPA_END_TOL = 5e-5 ", "KAPPA_END_TOL = 1e-4 "),
                           ('evidence/path/derive_on_engine.py', "LEVEL_END_TOL = 1e-4 ", "LEVEL_END_TOL = 2e-4 ")]},
    # ось структурной доли опта — на той же величине, что центр варианта: средства с книгой страховых (0,0437 … 0,1403)
    "k3core": {"why": "ось структурной доли опта на средствах с книгой страховых",
               "axis": {"volumes.wholesale_structural_to_funds": {"low": 0.0437, "high": 0.1403}}},
}
FORKS = {
    "margin_hump_new_level": "hump", "margin_middle": "middle", "nim_level_window_composition": "nimL", "bridge_literal": "bridgelit",
    "buyback_none": "var:buyback_none+looseends", "cash_displaced_as_money": "var:cash_displaced_as_money+looseends",
    "insurance_liab_as_funds": "var:insurance_liab_as_funds+k3core", "clients_all": "var:clients_all+k3core",
    "k6_root_off": "var:k6_root_off+norho",
}
RULE_FORKS = {"unconstrained": "rule:unconstrained", "dividend_first": "rule:dividend_first"}
# строка без цены — причина словами (печатается на витрине); без слов запись не пишется
FORK_WHY = {
    "nim_level_window_composition": ("без цены: вариант несовместим с гейтом стоимости средств клиентов к ключевой — на всей оси "
                                     "доли сжатия маржи (0,17…0,64) стоимость средств выше порога 0,876, центра в области гейта нет"),
    "cash_displaced_as_money": ("без цены: книга под вариант не перевыводится — корни строк на концах осей-связок расходятся с "
                                "правилом листа (2,9·10⁻⁴) и при вдвое большем допуске"),
}
# пометка медианы строки, посчитанной с правкой
FORK_MARKS = {
    "looseends": "медиана — при вдвое большем допуске корней строк на концах осей-связок (центр сошёлся; точка — точная цена)",
    "k3core": "медиана — с осью структурной доли опта на средствах с книгой страховых (0,0437…0,1403), как у центра варианта",
}
RECORD = {"out": "out/derive_out.json", "print": "out/derive_out.txt", "start": "out/derive_start.json"}
STEPS = sheet.STEPS
LINKED = sheet.LINKED

# Центр — один процесс (мост, якорь, ближние спреды, уровень, связанные шаги до сходимости, решатель на оси передачи).
# Концы осей и проверки — на записанных числах центра (--start). Шаг splits в фазе концов нужен: низ оси доли φ берётся из
# узла этого шага.
PHASES = (
    {"name": "centre", "title": "центр: мост, якорь, ближние спреды, связанные шаги до сходимости, ось передачи",
     "steps": ("bridge", "anchor", "near_spreads", "level", "splits", "near", "levels", "share_roots", "transmission"), "after": None},
    {"name": "ends", "title": "концы осей и проверки на записанных числах центра",
     "steps": ("splits", "ends"), "after": "centre", "take": (("ends",), ("splits", "axis_phi"))},
)

DEADBAND_UNITS = 1.0
ANCHOR_YEAR = "2026"
AXES = ("valuation", "uncertainty", "axes")
REVERSE = ("valuation", "reverse_dcf", "axes")
VARIANTS = ("valuation", "reference_variants")
SHARE = [("", 0.0, 1.0, "доля: вне отрезка 0…1 — счёт сломан")]
PERIOD_KEYS = "2*"
NO_CORRIDOR = "число листа не выводит — переносится из книги"


def _key(path: str) -> tuple:
    return ("keys", path)


def _axis_shift(node: str) -> callable:
    """Концы оси вида shift на ключе уровня или передачи: конец − центр."""
    def get(record: dict) -> list:
        if node == "level":
            return list(record["bridge"]["key_axis_shift"])
        tr = record["transmission"]
        centre = tr["rows"]["centre"]["target"]
        return [round(tr["axis"][0] - centre, 6), round(tr["axis"][1] - centre, 6)]
    return get


def _end(fn, i: int):
    return lambda record: fn(record)[i]


def _beta_end(end: str):
    def get(record: dict) -> dict:
        v = record["bridge"]["beta_ends"][end]
        p = "nii.books.insurance_liab"
        return {f"{p}.beta": v["beta"], f"{p}.spread.2026": v["spread_2026"], f"{p}.spread.2027": v["spread_2027"],
                f"{p}.spread.2028": v["c_lt"], f"{p}.spread.2029": v["c_lt"], f"{p}.spread.2030": v["c_lt"],
                f"{p}.spread.LT": v["c_lt"], "nii.nim_lt_target_mgmt": v["key"], "nii.transmission.target": v["target"]}
    return get


def _need_overrides(record: dict) -> dict:
    need = record["ends"]["need"]
    return {f"{path}.{year}": round(need["level"] * share, 4) for path in sheet.PREMIUM_PATHS for year, share in need["shape"].items()}


_SPREAD = [("2026", -0.30, 0.30, "ближний ключ спреда: дальше ±30 п.п. — ставка якоря или опора мира сломаны"),
           ("2027", -0.30, 0.30, "середина между ключом 2026 года и калибровкой 2028 года"),
           ("*", None, None, NO_CORRIDOR)]
_DENSITY = [("corp_loans", 0.5, 2.0, "плотность корпоративной книги: остаток RWA якоря; вне 0,5…2,0 — плотности листа капитала не "
                                     "сходятся со знаменателем Н1.0"),
            ("*", None, None, NO_CORRIDOR)]
_OPEX = [("2026", -0.10, 0.06, "корень года якоря: дальше — расходы 2П2026 уходят от правила года якоря больше сезонности"),
         ("2027Q1", -0.04, 0.12, "корень группы + ступень периметра 2027К1 (расходы КЛСЖ и КЛМС за полный квартал к факту 1К2026; ряд "
                                 "perimeter, Р4-3): дальше +12 п.п. — ступень больше четверти расходов квартала, искать ошибку в ряде"),
         ("2027Q2", -0.04, 0.08, "корень группы + ступень периметра 2027К2 (49/91 расходов КЛМС к факту 2К2026; Р4-3)"),
         ("LT_from", None, None, NO_CORRIDOR),
         ("LT", 0.0, 0.0, "с 2030 года корня нет — правило Р2 (связь 1)"),
         (PERIOD_KEYS, -0.04, 0.04, "корень группы лет: дальше ±4 п.п. в год четыре года подряд — уровень устава не согласован с путём баланса")]
_FEES = [("2026", -0.20, 0.20, "корень года якоря: факт 2К2026 −6,5 %, 1П2026 +8,9 % (резерв по гарантиям)"),
         ("LT_from", None, None, NO_CORRIDOR),
         ("LT", 0.0, 0.0, "с 2030 года корня нет — правило Р2 (связь 1)"),
         (PERIOD_KEYS, -0.05, 0.05, "корень группы лет: дальше ±5 п.п. в год — уровень устава не согласован с путём баланса")]
_INS = [("2026", -0.40, 0.05, "корень года якоря: факт 2К2026 −18,5 % г/г (первый квартал нового периметра) минус рост зарплат мира"),
        ("LT_from", None, None, NO_CORRIDOR),
        ("LT", 0.0, 0.0, "с 2030 года корня нет — правило Р2 (связь 1)"),
        ("2027Q1", -0.05, 0.45, "корень группы + ступень периметра 2027К1 (КЛСЖ и выручка КЛМС к факту 1К2026 без них; ряд perimeter, "
                                "Р4-3; центр ≈ +0,17, верх связок ≈ +0,27): дальше +45 п.п. — искать ошибку в ряде или базе"),
        ("2027Q2", -0.05, 0.30, "корень группы + ступень периметра 2027К2 (49/91 выручки КЛМС к факту 2К2026; Р4-3)"),
        (PERIOD_KEYS, -0.05, 0.20, "корень группы лет: дальше +20 п.п. в год — уровень окна R далёк от уровня 1П2026; искать ошибку "
                                   "в базе (ступени периметра — в масках 2027Q1, 2027Q2 выше)")]
_NEAR = [("LT", 0.0, 0.0, "с года схода сдвига нет — правило шага"),
         ("LT_from", sheet.NEAR_LAST_YEAR + 1, sheet.NEAR_LAST_YEAR + 1, "год схода — год после последнего года сдвига"),
         (PERIOD_KEYS, -0.02, 0.02, "сдвиг маржи квартала: дальше ±2 п.п. — механика книг расходится с нау-кастом больше чем на треть "
                                    "уровня маржи; искать ошибку в книгах ЧПД")]
_WINDOW = [("*", 0.0, 1.0, "отношение окна фактов — доля")]
_LEVEL_AXIS = [("", -0.30, 0.40, "сдвиг группы 2027–2029: уровень окна R на конце оси — в пределах ±30–40 п.п. роста в год")]
# Р8-6 (решения ведущего № 8; проход ядра 6): корень κ номинальной части франшизы строки — рост базы строки слоя M к росту зарплат
# мира M; коридор спецификации core-pass6 (sheet_and_rederive.derive_spec_derived)
_KAPPA = [("LT_from", None, None, NO_CORRIDOR),
          ("LT", 0.0, 0.0, "с 2030 года κ = 0 — номинальная часть растёт с зарплатами мира (класс 5)"),
          (PERIOD_KEYS, -0.30, 0.20, "корень номинальной части франшизы: дальше — рост базы строки слоя M расходится с зарплатами "
                                     "больше чем на 20–30 п.п. в год; искать ошибку в базе строки или в ряде")]
_KAPPA_END = ("*line_share_roots*", -0.30, 0.20, "κ на конце оси-связки (Р8-6): корень номинальной части франшизы тем же правилом")
# Р9-1 (решения ведущего № 9; проход ядра 7): корень ρ номинальной части книг К6 — рост базы строки на концах кварталов слоя M к росту
# зарплат мира M в квартальном выражении; коридор спецификации core-pass7 (sheet_and_rederive.derive_spec_derived): коридор κ в
# квартальном выражении (1 − 0,30)^(1/4) − 1 … 1,20^(1/4) − 1
_RHO = [("LT_from", None, None, NO_CORRIDOR),
        ("LT", 0.0, 0.0, "с 2030 года ρ = 0 — номинальная часть книги К6 растёт с зарплатами мира (класс 5)"),
        (PERIOD_KEYS, -0.085, 0.045, "корень номинальной части книги К6 — коридор κ в квартальном выражении: (1 − 0,30)^(1/4) − 1 … "
                                     "1,20^(1/4) − 1")]
_RHO_END = ("*liability_driver_roots*", -0.085, 0.045, "ρ на конце оси-связки (Р9-1): корень номинальной части книги К6 тем же правилом")

def _template_axis_kinds() -> dict[str, str]:
    """Первый путь оси шаблона → вид оси (связки, которых может не быть в шаблоне до правки)."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "assumptions_template.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return {str(a["paths"][0]): str(a["kind"]) for a in data["valuation"]["uncertainty"]["axes"]}
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return {}


def _template_axis_firsts() -> set[str]:
    """Первые пути осей шаблона дерева (оси, которых может не быть: связки баз строк К2б — с интеграцией прохода ядра 3).
    Запись концов такой оси описание даёт только при оси в шаблоне (иначе адрес записи не найдётся и запись остановится)."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "assumptions_template.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return {str(a["paths"][0]) for a in data["valuation"]["uncertainty"]["axes"]}
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return set()


_FIRSTS = _template_axis_firsts()


def _template_value(dotted: str):
    """Значение ключа шаблона дерева (None — нет ключа или шаблон не читается)."""
    import yaml
    path = Path(__file__).resolve().parents[2] / "assumptions_template.yaml"
    try:
        node = yaml.safe_load(path.read_text(encoding="utf-8"))
        for part in dotted.split("."):
            node = node[part]
        return node
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return None


_SHARE_ROOTS = _template_value(sheet.SHARE_ROOTS) or {}          # Р8-6: строки ключа шаблона (нет ключа — записи и невязки нет)
_DRIVER_ROOTS = _template_value(sheet.DRIVER_ROOTS) or {}        # Р9-1: строки ключа ρ шаблона (нет ключа — записи и невязки нет)
# Р12-9 (решения ведущего № 12): только строки, которые ведут книгу К6 (volumes.liability_drivers шаблона) — вариант без ведомой книги
# (insurance_liab_as_funds) ρ не пишет; у книги — те же строки
_DRIVER_ROOTS = {ln: v for ln, v in _DRIVER_ROOTS.items() if ln in {str(x) for x in (_template_value("volumes.liability_drivers") or {}).values()}}
_INS_LINK = _template_value("other.insurance_volume_link")
_INS_LINK = 0.0 if _INS_LINK is None else float(_INS_LINK)
# Р10-5 (решения ведущего № 10; проход ядра 8): при форме строки (volumes.line_link_form: line) ρ — корень г/г, как κ: коридор κ, а
# не квартальный (спецификация core-pass8, corridors_derive_spec; с квартальным коридором запись останавливается на 2026К4 −0,0883);
# тексты правил κ и ρ — по форме
_LINK_LINE = _template_value(sheet.LINK_FORM) == "line"
if _LINK_LINE:
    _RHO = [_RHO[0], _RHO[1], (PERIOD_KEYS, -0.30, 0.20, "корень книги К6 формой строки — корень г/г (Р10-5): коридор κ")]
    _RHO_END = ("*liability_driver_roots*", -0.30, 0.20, "ρ на конце оси-связки формой строки (Р10-5): корень г/г — коридор κ")
_KAPPA_RULE = ("κ — корень г/г франшизы формой строки (Р10-5): Φ_q = Φ_(q−4) g(A_q / A_(q−4), w, λ, κ_q); правило листа последовательно "
               "по кварталам до 2029К4 — в слое M E_M[Φ_q] = E_M[A_q] / A_0; с 2030 года 0" if _LINK_LINE else
               "κ — рост базы строки слоя M к росту зарплат мира M по кварталам до 2029К4: в условиях окна номинальная часть франшизы "
               "идёт за базой строки (Р8-6; E_M[H_q] = E_M[A_q] / A_0); с 2030 года 0")
_RHO_RULE = ("ρ — корень г/г книги К6 формой строки (Р10-5): Ψ_q = Ψ_(q−4) g(D_q / D_(q−4), w, λ, ρ_q) на концах кварталов; правило "
             "листа последовательно по кварталам до 2029К4 — в слое M E_M[Ψ_q] = E_M[D_q] / D_0 (= E_M[К6_q] / К6_0); с 2030 года 0; "
             "совместно с κ" if _LINK_LINE else
             "ρ — рост базы строки на концах кварталов в слое M к росту зарплат мира M в квартальном выражении до 2029К4: в условиях "
             "окна номинальная часть книги К6 идёт за базой строки (Р9-1; N^ρ,M_q = E_M[D_q] / D_0); с 2030 года 0; совместно с κ")
_BASE_AXES = tuple((name, first) for name in ("fees", "ins") for first in sorted(_FIRSTS)
                   if first.startswith(sheet.LINE_BASE_PATHS[name] + ".mix."))


WRITES = (
    # ---- bridge: ключ уровня и цель передачи — суждения опр. банка точным мостом в базис ядра
    {"step": "bridge", "address": ("nii", "nim_lt_target_mgmt"), "source": _key(sheet.NIM_KEY), "unit": 1e-6, "mark": True,
     "rule": "7,17 % опр. банка мира N (устав §3; решения № 1, п. 1): (банк × R − ife_N × l_ins) / b",
     "corridor": [("", 0.06, 0.09, "ключ ядра уровня мира N: дальше — мост банк ↔ движок сломан")]},
    {"step": "bridge", "address": ("nii", "transmission", "target"), "source": _key("nii.transmission.target"), "unit": 1e-6, "mark": True,
     "rule": "передача −0,06 опр. банка (устав §3): банк × R − β_ins × l_ins",
     "corridor": [("", -0.20, 0.05, "цель передачи в базисе движка: дальше — мост сломан")]},
    *({"step": "bridge", "address": AXES + ({"paths.0": sheet.NIM_KEY}, end), "source": _end(_axis_shift("level"), i), "unit": 1e-6,
       "rule": f"ось уровня (вид shift): {'низ 6,92' if i == 0 else 'верх 7,28'} % опр. банка тем же мостом минус центр",
       "corridor": [("", -0.01, 0.01, "сдвиг ключа уровня на конце оси")]} for i, end in enumerate(("low", "high"))),
    {"step": "bridge", "address": REVERSE + ({"paths.0": sheet.NIM_KEY}, "range"), "source": ("bridge", "key_axis"), "unit": 1e-6,
     "rule": "диапазон строки обратного расчёта — концы оси уровня в ключе ядра", "corridor": [("*", 0.05, 0.10, "ключ ядра")]},
    *({"step": "bridge", "address": AXES + ({"paths.0": "nii.books.insurance_liab.beta"}, end), "source": _beta_end(end), "unit": 1e-6,
       "rule": f"ось-связка β книги страховых, конец {end}: β, спред LT подбором той же постановки, что центр (с переоценкой, Б4), ближние "
               "ключи A-N1n, ключ уровня и цель передачи при β конца",
       "corridor": [("*beta", 0.5, 0.8, "β книги страховых — ось решений № 1, п. 6"),
                    ("*spread*", -0.08, 0.0, "спред книги страховых к ключевой"),
                    ("nii.nim_lt_target_mgmt", 0.06, 0.09, "ключ ядра"), ("nii.transmission.target", -0.20, 0.05, "цель передачи")]}
      for end in ("low", "high")),
    # ---- anchor: вычеты и плотность якоря
    {"step": "anchor", "address": ("capital", "rwa", "density"), "source": _key("capital.rwa.density"), "unit": 1e-6, "mark": True,
     "rule": "плотность корпоративной книги закрывает RWA якоря на знаменатель Н1.0 банка; прочие — лист capital", "corridor": _DENSITY},
    {"step": "anchor", "address": ("capital", "n20", "deductions_anchor"), "source": _key("capital.n20.deductions_anchor"), "unit": 0.001,
     "mark": True, "rule": "Ded20_0 = капитал МСФО к нормативу + AT1 + инструменты якоря − собственные средства банка (числом, урок ВТБ)",
     "corridor": [("", 0.0, 100.0, "вычет якоря Н1.0: отрицательный или больше пятой части капитала — сломан мост МСФО ↔ норматив")]},
    {"step": "anchor", "address": ("capital", "n11", "deductions_anchor"), "source": _key("capital.n11.deductions_anchor"), "unit": 0.001,
     "mark": True, "rule": "Ded11_0 = капитал МСФО к нормативу − неаудированная прибыль − основной капитал банка (слот n1_1 — Н1.2)",
     "corridor": [("", -50.0, 100.0, "вычет якоря Н1.2")]},
    # класс ловушки with_overrides (решения ведущего № 2, А1): спутники якоря у оси признания фонда ССПСД и у варианта годового аудита
    *({"step": "anchor", "address": AXES + ({"paths.0": "capital.n20.fvoci_recognition"}, end),
       "source": (lambda end: lambda record: record["anchor"]["fvoci_axis_ends"][end])(end), "unit": 0.001,
       "rule": f"ось-связка признания фонда ССПСД, конец {end}: доля f конца и вычеты якоря Ded20_0, Ded11_0 тем же правилом при f конца "
               "(якорь Н1.0 и Н1.2 — факт на обоих концах)",
       "corridor": [("*fvoci_recognition", 0.0, 1.0, "доля признания — от нуля до единицы"),
                    ("*n20.deductions_anchor", 0.0, 100.0, "вычет якоря Н1.0"), ("*n11.deductions_anchor", -50.0, 100.0, "вычет якоря Н1.2")]}
      for end in ("low", "high")),
    {"step": "anchor", "address": VARIANTS + ({"id": "audit_cutoffs_annual"}, "overrides", "capital.n11.deductions_anchor"),
     "source": ("anchor", "ded11_annual"), "unit": 0.001,
     "rule": "вариант «прибыль в основном капитале только после годового аудита»: Ded11_0 тем же правилом при E_0 отсечек [4]",
     "corridor": [("", -60.0, 100.0, "вычет якоря Н1.2 варианта")]},
    # ---- near_spreads: ближние ключи спредов книг (A-N1n)
    *({"step": "near_spreads", "address": ("nii", "books", name, "spread"), "source": _key(f"nii.books.{name}.spread"), "unit": 1e-5,
       "mark": False, "rule": "A-N1n: «2026» — ставка якоря минус опора мира H в 3К2026 (у пассива — с β); «2027» — середина до 2028",
       "corridor": _SPREAD}
      for name in ("auto", "mortgage", "cash_loans", "cards", "corp_loans", "securities", "liquidity", "retail_current", "retail_term",
                   "corp_term", "corp_current", "wholesale", "insurance_liab")),
    # ---- splits
    {"step": "splits", "address": ("nii", "sigma0_split"), "source": _key("nii.sigma0_split"), "unit": 0.01, "mark": True,
     "rule": "доля сдвига σ0 на кредитных книгах — середина области 0 … наибольшая доля, при которой гейт пола спреда проходит в "
             "мире-опоре (свидетельств раскладки нет; решения № 10, Р10-4)", "corridor": SHARE},
    {"step": "splits", "address": ("nii", "phi_split"), "source": _key("nii.phi_split"), "unit": 0.01, "mark": True,
     "rule": "доля сжатия φ по типу центра (решения № 11, раздел А): тип Б — совместный подбор «по истории» (сжатие истории ÷ φ "
             "решателя), если он внутри оси; вне области гейтов — ближайшая точка области (решения № 12, Р12-4; было — тип В, середина "
             "оси): ось — диапазон оценок φ листа nii, обрезанный гейтами пола спреда и стоимости средств к ключевой (Р10-4)", "corridor": SHARE},
    {"step": "splits", "address": AXES + ({"paths.0": "nii.sigma0_split"}, "low"), "source": ("splits", "axis_sigma0", 0), "unit": 0.01,
     "rule": "ось доли σ0: низ — весь сдвиг на средствах клиентов", "corridor": SHARE},
    {"step": "splits", "address": AXES + ({"paths.0": "nii.sigma0_split"}, "high"), "source": ("splits", "axis_sigma0", 1), "unit": 0.01,
     "rule": "ось доли σ0: верх — предел гейта пола спреда в мире-опоре (Р10-4)", "corridor": SHARE},
    {"step": "ends", "address": AXES + ({"paths.0": "nii.phi_split"}, "low"), "source": ("splits", "axis_phi", 0), "unit": 0.01,
     "rule": "ось доли φ: низ — низ оценок листа nii, обрезанный гейтом стоимости средств к ключевой (Р10-4)", "corridor": SHARE},
    {"step": "ends", "address": AXES + ({"paths.0": "nii.phi_split"}, "high"), "source": ("splits", "axis_phi", 1), "unit": 0.01,
     "rule": "ось доли φ: верх — верх оценок листа nii, обрезанный пределом гейта пола спреда (Р10-4)", "corridor": SHARE},
    # ---- near
    {"step": "near", "address": ("regimes", "near_nim_shift"), "source": _key("regimes.near_nim_shift"), "unit": 1e-6, "deadband": 2.0,
     "mark": True, "rule": "3К2026 — нау-каст 7,45 % опр. банка; сдвиг затухает линейно к нулю к 2030К1 (механика книг остаётся)",
     "corridor": _NEAR},
    # ---- levels
    {"step": "levels", "address": ("opex", "real_growth"), "source": _key("opex.real_growth"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
     "mark": True, "rule": "2026 — рост г/г 3–4 кв. = середина факта 2К и 1П2026 к фактическим кварталам прошлого года на периметре "
                           "якоря; 2027К1, 2027К2 — ступени периметра сверх корня (ряд perimeter, Р4-3); 2027–2029 — расходы к своей базе "
                           "в слое M = середине свидетельств (тип В, форма А2 — решения № 12, Р12-1, Р12-1а, Р12-2: уровень года якоря целиком — "
                           "1П факт, 2П по правилу «середина», база — среднее 4 кварталов — и среднее окна R на той же базе и периметре якоря — "
                           "среднее скользящих 4 кварталов, Р6-2) в 2029 году; "
                           "с 2030 года и LT — 0 (связь 1; решения № 3, Р2)",
     "corridor": _OPEX},
    {"step": "levels", "address": ("fees", "growth_vs_wages"), "source": _key("fees.growth_vs_wages"), "unit": 1e-4, "deadband": DEADBAND_UNITS,
     "mark": True, "rule": "2026 — рост г/г 3–4 кв. = середина факта 2К и 1П2026; 2027–2029 — комиссии с резервом по гарантиям к своей "
                           "базе (смесь по месту выручки) в слое M = середине свидетельств (тип В, форма А2 — решения № 12, Р12-1, Р12-1а, Р12-2: "
                           "уровень года якоря целиком — 1П факт, 2П по правилу «середина», база — среднее 4 кварталов — и среднее окна R на "
                           "той же базе — среднее скользящих 4 кварталов, Р6-2) "
                           "в 2029 году; с 2030 года и LT — 0 (связь 1; Р2)",
     "corridor": _FEES},
    {"step": "levels", "address": ("other", "insurance_growth_vs_wages"), "source": _key("other.insurance_growth_vs_wages"), "unit": 1e-6,
     "deadband": 100.0, "mark": True,
     "rule": "2026 — рост г/г 3–4 кв. = середина факта 2К и 1П2026 на периметре якоря (правило года якоря «середина» — решения № 12, "
             "Р12-2; было — факт 2К2026); 2027К1, 2027К2 — ступени периметра сверх корня (КЛСЖ, КЛМС по "
             "датам контроля; ряд perimeter, Р4-3); 2027–2029 — страхование и "
             "небанковское без финрасходов к своей базе (база роста строки, К2: other.insurance_volume_base — розничные кредиты) в слое M = середине свидетельств (уровень 2026 года целиком: 1П факт, 2П "
             "по правилу года якоря «середина», база — среднее 4 кварталов; и среднее окна R на той же базе — среднее скользящих 4 кварталов, "
             "Р6-2; тип В, форма А2 — решения № 2, А2; № 12, Р12-1, Р12-1а) в 2029 году; "
             "с 2030 года и LT — 0 (связь 1; Р2)", "corridor": _INS},
    # ---- share_roots (Р8-6, проход ядра 6): корень κ номинальной части франшизы строки — только если ключ уже в шаблоне
    *({"step": "share_roots", "address": ("opex", "line_share_roots", line), "source": ("keys", sheet.SHARE_ROOTS, line), "unit": 1e-6,
       "deadband": 2.0, "mark": True, "rule": _KAPPA_RULE, "corridor": _KAPPA}
      for line in _SHARE_ROOTS),
    # ---- share_roots (Р9-1, проход ядра 7): корень ρ номинальной части книг К6 — та же неподвижная точка, что κ; только если ключ в шаблоне
    *({"step": "share_roots", "address": ("volumes", "liability_driver_roots", line), "source": ("keys", sheet.DRIVER_ROOTS, line),
       "unit": 1e-6, "deadband": 2.0, "mark": True, "rule": _RHO_RULE, "corridor": _RHO}
      for line in _DRIVER_ROOTS),
    # ---- transmission: ось цели передачи (вид shift) и строка обратного расчёта
    *({"step": "transmission", "address": AXES + ({"paths.0": "nii.transmission.target"}, end), "source": _end(_axis_shift("transmission"), i),
       "unit": 1e-6, "rule": f"ось передачи (вид shift): {'низ −0,15' if i == 0 else 'верх +0,03'} опр. банка мостом минус центр; не дальше "
                             "наибольшей цели, которую решатель решает (коридор ±0,20 — решения № 12, Р12-8а: при центре на верху оси +0,03 "
                             "низ оси даёт сдвиг −0,156; было ±0,15)", "corridor": [("", -0.20, 0.20, "сдвиг цели передачи")]}
      for i, end in enumerate(("low", "high"))),
    {"step": "transmission", "address": REVERSE + ({"paths.0": "nii.transmission.target"}, "range"), "source": ("transmission", "axis"),
     "unit": 1e-6, "rule": "диапазон строки обратного расчёта — концы оси передачи", "corridor": [("*", -0.25, 0.10, "цель передачи")]},
    # ---- ends: концы осей уровней, коридор опта (сверка), окно фактов, нужда баланса
    *({"step": "ends", "address": AXES + ({"paths.0": path}, end), "source": ("ends", "level_axes", name, end), "unit": 1e-4,
       "deadband": DEADBAND_UNITS, "rule": f"ось уровня {name}: сдвиг ключей группы 2027–2029 под {'нижний' if end == 'low' else 'верхний'} "
                                          "конец по правилу листа (у всех трёх строк — свидетельства центра: уровень года якоря целиком и "
                                          "среднее окна R, решения № 12, Р12-1, Р12-1а) в 2029 году, та же база", "corridor": _LEVEL_AXIS}
      for name, path in (("opex", "opex.real_growth.2027Q1"), ("fees", "fees.growth_vs_wages.2027"),
                         ("ins", "other.insurance_growth_vs_wages.2027Q1")) for end in ("low", "high")),
    *({"step": "ends", "address": AXES + ({"paths.0": "opex.volume_weights.auto"}, end), "source": ("ends", "m13_axis", end),
       "unit": 1e-4, "rule": f"ось-связка весов М13, конец {end} («{'только кредиты' if end == 'low' else 'баланс'}» схемы по ключам книги — "
                             "m13_scheme листа): веса листа m13_cost_bases.py и корни расходов 2026–2029, выведенные на них правилом "
                             "центра (решения № 3, Р1; № 4, Р4-1, Р4-2)",
       "corridor": [_KAPPA_END, _RHO_END, ("*volume_weights*", 0.0, 6.0, "вес себестоимости книги к корпоративному кредиту"),
                    ("*real_growth*", -0.12, 0.20, "корень расходов на конце оси")]} for end in ("low", "high")),
    # ---- ends: концы осей-связок баз строк (К2б; решения ведущего № 4, Р4-1, Р4-2) — только если ось уже в шаблоне
    *({"step": "ends", "address": AXES + ({"paths.0": first}, end), "source": ("ends", "base_axes", name, end), "unit": 1e-4,
       "rule": f"ось-связка базы строки {name} (смесь баз, конец {end}): доли смеси конца и корни строки 2026–2029 (и корни расходов, "
               "если франшиза строки — доля базы расходов), выведенные на них правилом центра",
       "corridor": [_KAPPA_END, _RHO_END, ("*.share", 0.0, 1.0, "доля компоненты смеси"), ("*.2026", -0.40, 0.30, "корень года якоря на конце оси базы"),
                    ("*", -0.15, 0.40, "корень группы лет на конце оси базы (у страхования 2027К1 — со ступенью периметра)")]}
      for name, first in _BASE_AXES for end in ("low", "high")),
    # ---- Р7-3 (решения ведущего № 7; класс 4, как у осей баз): концы оси-связки связи страхования с базой — связь конца и корни
    #      строки 2026–2029, выведенные на ней правилом центра (шаг листа ends_link_axis) — только если ось уже в шаблоне
    *({"step": "ends", "address": AXES + ({"paths.0": sheet.LINK_AXIS_FIRST}, end), "source": ("ends", "link_axis", end), "unit": 1e-4,
       "rule": f"ось-связка связи страхования с базой (доля «кредитного» страхования в строке), конец {end}: связь конца и корни строки "
               "2026–2029, выведенные на ней правилом центра (рост г/г года якоря; уровень к своей базе в слое M в 2029 году — центр; Р7-3)",
       "corridor": [_KAPPA_END, _RHO_END, ("*volume_link", 0.0, 1.0, "связь строки с базой — доля"), ("*.2026", -0.40, 0.30, "корень года якоря на конце оси связи"),
                    ("*2027Q1", -0.05, 0.45, "корень группы + ступень периметра 2027К1 на конце оси связи"),
                    ("*", -0.15, 0.40, "корень группы лет на конце оси связи")]}
      for end in ("low", "high") if sheet.LINK_AXIS_FIRST in _FIRSTS),
    # ---- Р6-7 (решения ведущего № 6; флаг 4 интеграции круга 5, класс 4): концы оси интенсивности окон CoR и четырёх осей периметра
    #      окна R выводит команда (шаги листа ends_cor_intensity, ends_perimeter) — только если ось уже в шаблоне
    *({"step": "ends", "address": AXES + ({"paths.0": sheet.INTENSITY_AXIS_FIRST}, end), "source": ("ends", "cor_intensity", end),
       "unit": 1e-6, "rule": f"ось-связка интенсивности состава окон CoR, конец {end} ({'МСФО' if end == 'low' else 'датабук'}): ключ "
                             "режима центра × I_mid / I_источника своего окна (факты credit_products.intensity; Р4-13, Р6-7)",
       "corridor": [("*", 0.0, 0.15, "стоимость риска режима на составе якоря")]}
      for end in ("low", "high") if sheet.INTENSITY_AXIS_FIRST in _FIRSTS),
    *({"step": "ends", "address": AXES + ({"paths.0": first}, end),
       "source": (lambda g, end: lambda record: record["ends"]["perimeter_axes"][g][end]["values"])(g, end), "unit": 1e-4,
       "rule": f"ось-связка периметра окна R ({g}), конец {end}: корни строк 2026–2029 и ступени 2027К1–К2 на конце ряда периметра "
               "(прочие связки — центр), выведенные правилом центра (Р5-3, Р6-7)",
       "corridor": [_KAPPA_END, _RHO_END, ("*.2026", -0.40, 0.30, "корень года якоря на конце оси периметра"),
                    ("*2027Q1", -0.05, 0.45, "корень группы + ступень периметра 2027К1"),
                    ("*", -0.15, 0.40, "корень группы лет на конце оси периметра (у 2027К2 — со ступенью)")]}
      for g, first in sheet.PERIM_AXES.items() if first in _FIRSTS for end in ("low", "high")),
    # ---- Р4-11: концы оси-связки CCF — масштаб и плотности листа (книга), corp_loans — закрытие RWA якоря на конце
    *({"step": "anchor", "address": AXES + ({"paths.0": "capital.rwa.guarantees.ccf.nonfinancial"}, end), "source": ("anchor", "ccf_axis_ends", end),
       "unit": 1e-6, "rule": f"ось-связка CCF гарантий, конец {end}: CCF, масштаб и плотности листа rwa_density_k5.py; плотность corp_loans "
                            "тем же правилом закрытия RWA якоря, что в центре (Р4-11)",
       "corridor": [("*ccf*", 0.0, 1.0, "CCF"), ("*corp_loans", 0.5, 2.0, "плотность корпоративной книги"), ("*", 0.0, 3.0, "плотность книги")]}
      for end in ("low", "high") if _template_axis_kinds().get("capital.rwa.guarantees.ccf.nonfinancial") == "bundle"),
    # ---- Р4-10: цель гейта cir_lt — C/I слоя M при расходах в центре уровня к базе М13 (тип В, А2 — Р12-1, Р12-1а); допуск — концы
    #      оси уровня расходов (сами прочтения: уровень года якоря целиком и среднее окна R)
    {"step": "ends", "address": ("checks", "cir_lt", "target"), "source": ("ends", "cir_lt", "target"), "unit": 1e-4,
     "rule": "C/I слоя «рыночные ставки как есть» 2033–2036 при расходах в центре уровня к базе М13 (Р4-10; центр — тип В, форма "
             "А2: середина уровня года якоря целиком и среднего окна R — решения № 12, Р12-1, Р12-1а)",
     "corridor": [("", 0.30, 0.70, "C/I слоя")]},
    {"step": "ends", "address": ("checks", "cir_lt", "tolerance"), "source": ("ends", "cir_lt", "tolerance"), "unit": 1e-3,
     "rule": "допуск гейта cir_lt — C/I на концах оси уровня расходов (сами прочтения центра: уровень года якоря целиком и среднее "
             "окна R на базе М13 — Р12-1, Р12-1а; Р4-10)",
     "corridor": [("", 0.0, 0.05, "допуск C/I")]},
    {"step": "ends", "address": ("checks", "wholesale_share"), "source": ("ends", "wholesale_share", "corridor"), "unit": 0.01,
     "rule": "коридор гейта: доля якоря минус 5 п.п. — наибольшая доля на конец года по клеткам плюс 5 п.п.",
     "corridor": [("0", 0.0, 0.30, "низ коридора — у доли якоря"),
                  ("1", 0.10, 0.70, "оптовое фондирование выше 70 % фондирования — искать разрыв роста кредитов и средств клиентов")]},
    {"step": "ends", "address": ("checks", "funds_cost_to_key", "max"), "source": ("ends", "funds_cost_gate", "max"), "unit": 0.001,
     "rule": "порог гейта стоимости средств к ключевой — наибольший квартал окна R на той же величине, что число гейта ядра (лист nii: "
             "средства ядра с книгой К6 0,870; средства клиентов без К6 0,876 — при ключе ядра checks.client_funds: clients; Р10-1, Р10-16)",
     "corridor": [("", 0.70, 1.00, "стоимость средств к ключевой — окно R 0,79–0,88")]},
    *({"step": "ends", "address": ("checks", "window_backtest", name, i), "source": ("ends", "window", name, end), "unit": 1e-4,
       "rule": f"окно фактов R: {'наименьший' if end == 'min' else 'наибольший'} квартал ({name}"
               + ("; на составе якоря — Σ w0 × CoR книг, факты credit_products (решения № 3, Р3)" if name == "cor" else "") + ")",
       "corridor": _WINDOW}
      for name in ("cor", "cir", "nim") for i, end in enumerate(("min", "max"))),
    *({"step": "ends", "address": ("checks", "window_backtest", "means", name), "source": ("ends", "window", name, "mean"), "unit": 1e-4,
       "rule": f"окно фактов R: среднее скользящих 4 кварталов — равный вес календарных кварталов, Р6-2 ({name}" + ("; на составе якоря, Р3" if name == "cor" else "") + ")",
       "corridor": _WINDOW} for name in ("cor", "cir", "nim")),
    {"step": "ends", "address": ("checks", "window_backtest", "loans_share"), "source": ("ends", "window", "loans_share"), "unit": 1e-3,
     "rule": "окно фактов R: доля кредитных книг в процентных активах движка — среднее скользящих 4 кварталов (средние остатки, сумма к "
             "сумме внутри; Р6-2) "
             "(решения № 2, А5: слой M — с окном R)", "corridor": _WINDOW},
    *({"step": "ends", "address": VARIANTS + ({"id": "cor_retail_tail"}, "overrides", f"regimes.{r}.cor"),
       "source": ("ends", "retail_tail", f"regimes.{r}.cor"), "unit": 1e-4,
       "rule": f"вариант «розничный хвост»: путь режима {r} центра + 0,3 п.п. на составе окна R (устав §6, № 3) ÷ I окна R — на "
               "составе якоря, как пути (решения № 3, Р3) — поверх чисел центра",
       "corridor": [("LT_from", None, None, NO_CORRIDOR), ("*", 0.0, 0.10, "стоимость риска режима с хвостом")]}
      for r in sheet.REGIMES),
    # ---- обзор sweep11 (класс 4; решения ведущего № 11, раздел А — тип В): концы оси премии средств — диапазон прочтений «факты» и
    #      «нужда» на той же величине (было — отступы ±5 / ±5 / ±3 п.п. вокруг центра книги Т); нужду пишет тот же шаг ends_need
    *({"step": "ends", "address": AXES + ({"paths.0": sheet.PREMIUM_PATHS[0] + ".2027"}, end),
       "source": (lambda end: lambda record: record["ends"]["need"]["axis"][end])(end), "unit": 1e-4, "deadband": DEADBAND_UNITS,
       "rule": f"ось премии средств клиентов, конец {end}: {'наименьшее' if end == 'low' else 'наибольшее'} из прочтений «факты» (среднее "
               "окон 4 кварталов к сектору) и «нужда» (ожидание слоя «свой взгляд») по сегменту в 2027 году; 2028–2029 — × 0,66 / 0,34",
       "corridor": [("*", -0.20, 0.20, "премия роста средств клиентов дальше ±20 п.п. в год — прочтение сломано")]}
      for end in ("low", "high")),
    {"step": "ends", "address": VARIANTS + ({"id": "funds_premium_need"}, "overrides"), "source": _need_overrides, "unit": 1e-4,
     "deadband": DEADBAND_UNITS, "rule": "справочный вариант: премия средств клиентов на уровне нужды баланса в форме оси премии книги — "
                                         "нужда на ожидании слоя «свой взгляд» (Р9-2); центр премии книги — середина фактов и этой нужды "
                                         "(правило класса 6 читает нужду из варианта)",
     "corridor": [("*", -0.20, 0.20, "премия роста средств клиентов дальше ±20 п.п. в год — баланс клетки не сходится суждениями о росте")]},
)

# Суждения, которые лист держит константой: расхождение с книгой — остановка.
SAME = (
    {"step": "level", "address": ("nii", "transmission", "level_world"), "source": ("level", "world"),
     "rule": "мир уровня — суждение устава (окно L — мир N): лист его читает и не меняет"},
)

RESIDUALS = (
    {"step": "ends", "name": "отбор окон строк-долей (НДУ, франшиза страхования) равен правилу границы ROE модели (Р11-8)",
     "flag": ("ends", "roe_bound", "ok"), "book_only": True,
     "why": "окна книги (правила class_checks.yaml, MODEL_WINDOWS_ONLY листа М13) — те, чей ROE без "
            "разовых не ниже наименьшего ROE слоёв модели; граница сдвинулась — отбор пересматривается. Страж действует только на "
            "книгу (решения № 12, Р12-8): в развилке отбор по её своей границе — часть её действия (инструмент развилок). Р12-8а: "
            "изменилось только окно роли «ось» — цена с пометкой «ось НДУ — книги; отбор окон варианта: …»; изменилось окно роли «центр» "
            "(НДУ — центр, франшиза М13 — центр и ось) — «без цены — причина»; у развилки «строки уровня по правилу строк-долей» отбор — "
            "по границе ROE книги с пометкой о границе варианта. Лист решения № 12, С-5: конвенции типа Е считаются при отборе окон "
            "книги (конвенция меняет вероятность, а не условия окон), влияние своей границы варианта — пометкой. С-4: вариант, у "
            "которого сошёлся центр, а перевод останавливают только допуски концов связок κ/ρ, печатает точную цену по точке (концы "
            "осей точку не двигают) и медиану с пометкой «концы связок κ/ρ с допуском вдвое»; не сходится и с допуском вдвое — «без "
            "цены — причина». С-3: у варианта, меняющего величину К3, ось К3 — на той же величине, что центр варианта (класс 4)"},
    {"step": "levels", "name": "сходимость связанных шагов", "flag": ("convergence", "converged"),
     "why": "порог и число кругов — листа; не сошлось — числа не пишутся"},
    {"step": "bridge", "name": "спред LT книги страховых равен подбору центра (та же постановка, что у концов оси β)",
     "flag": ("bridge", "ins_fit_centre", "c_ok"), "why": "концы оси-связки β выводятся той же функцией подбора (Б4)"},
    {"step": "level", "name": "стационарная маржа мира уровня равна ключу", "flag": ("level", "stationary_ok"),
     "why": "ключ — перевод суждения: решатель передачи обязан его воспроизвести"},
    {"step": "anchor", "name": "якорь воспроизводит Н1.0 банка", "flag": ("anchor", "n20_ok"), "why": "вычет Ded20_0 выведен под факт"},
    {"step": "anchor", "name": "якорь воспроизводит Н1.2 банка", "flag": ("anchor", "n11_ok"), "why": "вычет Ded11_0 выведен под факт"},
    {"step": "near", "name": "ЧПМ 3К2026 ожидания слоя «свой взгляд» — нау-каст (решения № 9, класс 2; было — модальная клетка)",
     "value": ("frozen_check", "near_q3"), "target": ("frozen_check", "near_target"), "tol": 3e-6, "why": "сдвиг записан шестью знаками"},
    *({"step": "levels", "name": f"{name}: уровень к своей базе в 2029 году (год корня)", "value": ("frozen_check", "levels", name, "2029"),
       "target": 0.0, "tol": 4e-5, "why": "корни записаны четырьмя знаками: до 0,004 п.п. уровня"} for name in ("opex", "fees", "ins")),
    *({"step": "levels", "name": f"{name}: уровень к своей базе после 2029 года — стационар без корня (наибольшее отклонение 2030–2036)"
               + (" — на пробе со связью 1 (Р7-3: связь строки < 1)" if name == "ins" and _INS_LINK < 1.0 else ""),
       "value": ("frozen_check", "levels", name, "max_tail_dev"), "target": 0.0, "tol": 2e-4,
       "why": "Р2: связь 1 держит отношение строки к базе квартал к тому же кварталу; дрожь — сезонные веса средних (до 0,02 п.п.); Р7-3: "
              "при связи < 1 отношение к базе дрейфует на (1 − связь)(зарплаты − рост базы) — суждение о связи, не корень; отсутствие "
              "корня после 2029 года судится на пробе со связью 1 (те же корни), отношение к базе в условиях окна (слой M) — в году корня"}
      for name in ("opex", "fees", "ins")),
    *({"step": "levels", "name": "ins: уровень к своей базе в слое M 2030–2036 при связи < 1 — внутри диапазона свидетельств уровня "
                                 "(концы оси уровня; наибольший выход)",
       "value": ("frozen_check", "levels", "ins", "tail_outside_range"), "target": 0.0, "tol": 0.0,
       "why": "Р7-3: дрейф отношения строки к своей базе после 2029 года — от связи < 1; в условиях окна (слой M) отношение судится "
              "диапазоном свидетельств центра (уровень 2026 года целиком по правилу года якоря … среднее окна R; Р12-1а)"} for _ in ((),) if _INS_LINK < 1.0),
    *({"step": "levels", "name": f"{name}: рост г/г года якоря", "value": ("frozen_check", "levels", name, "anchor_growth_miss"),
       "target": 0.0, "tol": 5e-4, "why": "корень года якоря записан четырьмя знаками: 0,05 п.п. роста"} for name in ("opex", "fees", "ins")),
    *({"step": "share_roots", "name": f"κ {line}: " + ("франшиза формой строки в слое M — за базой строки до "
                                                     f"{sheet.SHARE_ROOT_LAST} (Р10-5)" if _LINK_LINE else
                                                     f"номинальная часть франшизы в слое M — за базой строки до {sheet.SHARE_ROOT_LAST} (Р8-6)"),
       "value": ("frozen_check", "share_roots", line, "max_dev"), "target": 0.0, "tol": 1e-5,
       "why": "κ записан 6 знаками; невязка — max|" + ("E_M[Φ_q]" if _LINK_LINE else "E_M[H_q]") + " − E_M[A_q] / A_0| на записанных "
              "ключах (обратная связь через капитал)"}
      for line in _SHARE_ROOTS),
    *({"step": "share_roots", "name": f"κ {line}: запись равна правилу листа на записанных ключах (неподвижная точка)",
       "value": ("frozen_check", "share_roots", line, "rule_change"), "target": 0.0, "tol": 2e-6,
       "why": "κ — неподвижная точка правила: на записанных ключах правило даёт тот же κ (6 знаков; ±1 в последнем знаке)"}
      for line in _SHARE_ROOTS),
    *({"step": "share_roots", "name": f"ρ {line}: книга К6 в слое M — " + ("индекс формы строки" if _LINK_LINE else "номинальная часть")
               + f" за базой строки до {sheet.SHARE_ROOT_LAST} (" + ("Р10-5" if _LINK_LINE else "Р9-1") + ")",
       "value": ("frozen_check", "driver_roots", line, "max_dev"), "target": 0.0, "tol": 1e-5,
       "why": "ρ записан 6 знаками; невязка — max|" + ("E_M[Ψ_q]" if _LINK_LINE else "N^ρ,M_q") + " − E_M[D_q] / D_0| на записанных "
              "ключах (обратная связь через капитал)"}
      for line in _DRIVER_ROOTS),
    *({"step": "share_roots", "name": f"ρ {line}: запись равна правилу листа на записанных ключах (неподвижная точка с κ)",
       "value": ("frozen_check", "driver_roots", line, "rule_change"), "target": 0.0, "tol": 2e-6,
       "why": "ρ — неподвижная точка правила вместе с κ: на записанных ключах правило даёт тот же ρ (6 знаков; ±1 в последнем знаке)"}
      for line in _DRIVER_ROOTS),
    *({"step": "share_roots", "name": f"ρ {line}: печать формы — " + ("книга К6 против базы" if _LINK_LINE else "Йенсен цепной формы")
               + f" E_M[К6_q]/К6_0 ÷ E_M[D_q]/D_0 − 1 до {sheet.SHARE_ROOT_LAST}",
       "value": ("frozen_check", "driver_roots", line, "jensen"), "target": 0.0, "tol": sheet.JENSEN_TOL,
       "why": ("форма строки (Р10-5) держит книгу линейно по Ψ: E_M[К6_q]/К6_0 = E_M[Ψ_q] — до округления записи ρ (прототип ≈ 5e-7)"
               if _LINK_LINE else
               "не невязка правила: цепная форма держит ожидание ПРОИЗВЕДЕНИЯ, книга К6 — нелинейная функция D (спецификация "
               "прохода 7: замер 9,2e-4 при допуске 2e-3)")}
      for line in _DRIVER_ROOTS),
    # Р9-1 на концах — та же форма, что κ концов (Р9-7): судится правило на записанных числах конца против записи; невязка уровня
    # N^ρ,M − E_M[D]/D_0 на концах печатается в записи (rho_ends.max_dev_max; интеграция круга 9: до 6,8e-5 — у κ та же невязка
    # E_M[H] − E_M[A]/A_0 на тех же концах до 6,4e-5 и не судится); допуск невязки уровня концов — решение ведущего
    *({"step": "ends", "name": "ρ на концах связок: правило на записанных числах конца против записи (Р9-1; форма и допуск — как κ, Р9-7)",
       "value": ("ends", "rho_ends", "rule_change_max"), "target": 0.0, "tol": sheet.KAPPA_END_TOL,
       "why": "ρ концов — та же проверка, что κ концов (корни конца записаны 4 знаками и двигают путь баланса)"}
      for _ in ((),) if _DRIVER_ROOTS),
    *({"step": "ends", "name": "κ на концах связок: правило на записанных числах конца против записи (Р8-6; допуск концов — Р9-7)",
       "value": ("ends", "kappa_ends", "rule_change_max"), "target": 0.0, "tol": sheet.KAPPA_END_TOL,
       "why": "решения ведущего № 9, Р9-7: корни конца записаны 4 знаками и двигают путь баланса — κ конца до 3,2e-5 от правила "
              "(центр — 1e-5 и 2e-6: там κ перевыводится на записанных ключах)"} for _ in ((),) if _SHARE_ROOTS),
    # Р10-13 (решения ведущего № 10): на концах связок судятся ОБА числа — правило против записи (выше, 5e-5) и невязка уровня
    # (κ: E_M[H] или E_M[Φ] − E_M[A]/A_0; ρ: N^ρ,M или E_M[Ψ] − E_M[D]/D_0) — допуск 1e-4 (sheet.LEVEL_END_TOL)
    *({"step": "ends", "name": "κ на концах связок: невязка уровня в слое M на записанных числах конца (Р10-13)",
       "value": ("ends", "kappa_ends", "max_dev_max"), "target": 0.0, "tol": sheet.LEVEL_END_TOL,
       "why": "решения ведущего № 10, Р10-13: судятся оба числа концов; уровень — корни конца записаны 4 знаками, κ — 6 "
              "(прототип прохода 8: до 3,17e-5)"} for _ in ((),) if _SHARE_ROOTS),
    *({"step": "ends", "name": "ρ на концах связок: невязка уровня в слое M на записанных числах конца (Р10-13)",
       "value": ("ends", "rho_ends", "max_dev_max"), "target": 0.0, "tol": sheet.LEVEL_END_TOL,
       "why": "решения ведущего № 10, Р10-13: судятся оба числа концов (прототип прохода 8: до 3,45e-5; цепь — до 6,8e-5)"}
      for _ in ((),) if _DRIVER_ROOTS),
    {"step": "transmission", "name": "мир уровня неподвижен на оси цели передачи", "flag": ("transmission", "level_world_fixed"),
     "why": "ось передачи несёт только различие маржи между мирами"},
)


def relations(record: dict, template: dict) -> list[str]:
    bad = []
    keys, splits = record.get("keys") or {}, record.get("splits") or {}
    if "axis_phi" in splits and "nii.phi_split" in keys:
        low, high = splits["axis_phi"]
        if not low <= keys["nii.phi_split"] <= high:
            bad.append(f"доля φ {keys['nii.phi_split']} вне своей оси {low}…{high}")
        else:
            # решения ведущего № 11, раздел А (уточняет Р10-4): тип Б — совместный подбор «по истории» на сетке доли, если он внутри
            # оси (область гейтов его не обрезает); иначе (решения № 12, Р12-4) — ближайшая точка области: конец оси со стороны
            # подбора (до шага сетки доли). Было (№ 11) — тип В, середина оси
            bh = splits.get("phi_by_history")
            by_grid = None if bh is None else round(round(float(bh) / 0.01) * 0.01, 6)
            if by_grid is not None and low <= by_grid <= high:
                if abs(keys["nii.phi_split"] - by_grid) > 0.0051:
                    bad.append(f"доля φ {keys['nii.phi_split']} не равна совместному подбору «по истории» {bh} внутри оси {low}…{high} "
                               "(тип Б, решения № 11, раздел А)")
            elif by_grid is not None and abs(keys["nii.phi_split"] - (low if by_grid < low else high)) > 0.0051:
                bad.append(f"доля φ {keys['nii.phi_split']} не на ближайшей границе своей оси {low}…{high}: подбор «по истории» {bh} вне "
                           "области гейтов — центр — ближайшая точка области (решения № 12, Р12-4)")
    if "axis_sigma0" in splits and "nii.sigma0_split" in keys and abs(sum(splits["axis_sigma0"]) / 2 - keys["nii.sigma0_split"]) > 0.0051:
        bad.append(f"доля σ0 {keys['nii.sigma0_split']} не на середине своей оси {splits['axis_sigma0']} (Р10-4)")
    tr = record.get("transmission")
    if tr is not None:
        target = tr["rows"]["centre"]["target"]
        if not tr["axis"][0] <= target <= tr["axis"][1]:
            bad.append(f"цель передачи {target} вне своей оси {tr['axis']}")
        unsolved = [n for n, r in tr["rows"].items() if not r["solved"]]
        if unsolved:
            bad.append("решатель передачи не решил цель: " + ", ".join(unsolved))
    ends = record.get("ends") or {}
    if "wholesale_share" in ends and not ends["wholesale_share"]["corridor"][0] < ends["wholesale_share"]["corridor"][1]:
        bad.append(f"коридор доли оптового фондирования пуст: {ends['wholesale_share']['corridor']}")
    for name, node in (ends.get("window") or {}).items():
        if isinstance(node, dict) and "mean" in node and not node["min"] <= node["mean"] <= node["max"]:
            bad.append(f"окно фактов, {name}: среднее вне концов")
    for name, node in (ends.get("level_axes") or {}).items():   # Р4-3 (скептик econ3-classes, класс 4): охват — на НЕокруглённых
        lo, hi = node.get("low_raw", node["low"]), node.get("high_raw", node["high"])
        if not lo < 0 < hi:
            bad.append(f"ось уровня {name}: концы {lo:+.6f}…{hi:+.6f} не охватывают центр")
    try:                                                    # Р1: веса книги — центр листа m13_cost_bases.py (класс 6)
        fees = (template.get("fees") or {}).get("volume_base", (template.get("volumes") or {}).get("link_base", "loans"))
        shares = (template.get("opex") or {}).get("line_shares")
        centre, _ = sheet.m13_scheme_of(fees, shares)       # Р4-1, Р4-2: схема — по ключам книги (франшиза в одном месте)
        want = sheet.m13_weights(centre)
        have = {str(b): float(v) for b, v in (template.get("opex") or {}).get("volume_weights", {}).items()}
        off = {b: (have.get(b), v) for b, v in want.items() if abs(float(have.get(b, -1.0)) - v) > 5e-5}
        if off:
            bad.append(f"веса М13 книги не равны центру листа m13_cost_bases.py ({centre}): {off}")
        if shares:                                          # доли франшиз — пул листа той же схемы (класс 6)
            want_sh = sheet.m13_line_shares(centre)
            off = {k: (shares.get(k), v) for k, v in want_sh.items() if abs(float(shares.get(k, 0.0)) - v) > 5e-5}
            if off:
                bad.append(f"доли франшиз opex.line_shares не равны пулу листа m13_cost_bases.py ({centre}): {off}")
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        bad.append(f"веса М13: лист m13_cost_bases.py не читается или схема книги не поддержана — {exc}")
    return bad


COMPANIONS = ()
MARGINAL = {                                       # решения ведущего № 2, А3: лист предельной экономики под Совкомбанк (устав §4)
    "sheet": "marginal_loan.py",
    "table": ("marginal", "kb_unit"),              # мир → строки лет: предельная единица роста устава — ЕДИНИЦА СЕГМЕНТА КБ (решения
                                                   #   ведущего № 4, Р4-4; устав §4 изменён): кредит юрлиц + средства юрлиц в отношении
                                                   #   сегмента + гарантии с комиссиями; кредит на опте — справочно (corp_loans записи)
    "value": "return_segment_basis",               # базис сегмента после налога (капитал фондирует часть кредита) — мерка устава §4
    "segment_basis": "return_no_capital_credit",   # рядом: весь рубль оплачен по цене фондирования
    "hurdle": "hurdle_norm",                       # нижний край нормы устава §4: k мира − 5 п.п.
    "ceiling": "ceiling_norm",                     # верхний край нормы устава §4: k мира + 5 п.п. — команда флагует и выход за верх
                                                   #   (решения ведущего № 5, Р5-11; круг 4: мир N 22,0 % при верхнем крае 19,1 % флага не дал)
    "anchor": ("anchor_check",),                   # {model_min, model_max, segment_low, segment_high}: якорь против сегмента КБ
    "anchor_slack": 0.0,
    # розница корзиной — норма устава §4 «не ниже 5 %, выше 30 % — признак ошибки калибровки» в каждом году листа (решения ведущего
    # № 6, Р6-5: команда флагует розницу выше 30 % и ниже 5 %; круг 5 — лист печатал до 32,4 %, команда молчала)
    "retail": {"table": ("marginal", "retail_basket"), "value": "return_segment_basis", "norm": (0.05, 0.30),
               "title": "розница корзиной (базис сегмента после налога)"},
    "title": "единица сегмента КБ (кредит + средства юрлиц 1 : 1,361 + гарантии с комиссиями) на базисе сегмента после налога против "
             "k мира ± 5 п.п. (устав §4, Р4-4) — ожидание мира (слой «свой взгляд» внутри мира; решения № 9, класс 2; модальная "
             "клетка — в записи листа рядом); кредит юрлиц на опте, розница корзиной, книги — в записи листа",
    "second": "без кредита за капитал",
    "anchor_words": ("якорь: единица сегмента КБ на базисе сегмента", "при сегменте «Корпоративный бизнес» на капитале и вычете единицы "
                     "(Р6-6: одна мерка с обеих сторон)", "сопоставимо",
                     "РАСХОДИТСЯ на одной мерке (Р6-6) — остаток назван строками ОПУ на рубль кредита (лист §4, anchor_lines и "
                     "anchor_residual): комиссии сегмента выше (3,37 / 2,72 % кредита в FY2025 / 1П2026), валютный и прочий доход "
                     "сегмента 0,52 / 0,44 % (у модели — «прочее» в реальных рублях, с объёмом не растёт), расходы сегмента ниже "
                     "(3,44 / 2,40 %)"),
    "verdict": ("в норме устава §4", "НИЖЕ нормы устава §4", "ВЫШЕ нормы устава §4"),
    "tail": "в конце сетки базис сегмента (норма — k мира ± 5 п.п.; «стоимость капитала» в строке — нижний край, k мира минус 5 п.п.)",
}
ACCEPTANCE = (
    {"title": "мерки маржи в условиях своих окон (опр. банка, точный мост) и сверка порядка на одном делителе "
              "(решения ведущего № 2, А5, А6)", "sheet": "acceptance.py"},
    # решения ведущего № 12, Р12-5 (устав §5 1(б) переписан; поток book12): бэктест ПУТИ МАРЖИ — (i) совместный подбор книг листа
    # этапа 1 и (ii) путь ЧПМ банка в модели (наклоны и лаги ядра, остатки фактов; уровень — подбором на окне: уровень судит 1(а),
    # 1(б) судит путь — лист решения № 12, С-2) по фактической ключевой 2023К1–2026К2; норма 0,3 п.п. на каждом плече; (ii) «старт
    # от якоря» — печать справочно; отклонение (ii) — с ценами развилок передачи «на верху оси» и «середина трёх прочтений» (С-1).
    # Наклоны отдельных книг между мирами — распределение передачи решателем (связь устава §8), не предмет проверки
    {"title": "бэктест пути маржи (устав §5 1(б); Р12-5): (i) совместный подбор и (ii) путь ЧПМ в модели — плечи L, W4, спуск, C "
              "не больше 0,3 п.п.", "sheet": "../nii/backtest_path.py"},
)

REMINDERS = (
    "слова комментариев шаблона у переписанных ключей несут числа прежнего вывода — сверить руками",
    "справочные варианты, которым нужны свои выведенные числа (уровень в мире M, мост буквально), перевыводятся отдельно",
    "лист предельной экономики роста marginal_loan.py — по книгам ядра: после слияния М7 и М13 он читает их ключи сам (проверить печать)",
    "таблицы книги (model.book_results без --fast), числа в документах и сводка контрольной модели — после того как число устоялось",
)
