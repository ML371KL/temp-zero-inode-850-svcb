"""Правило регномера для тестов литералов эмитента — ядро, индикаторы, витрина.

Регномер эмитента в общем коде запрещён: он читается из книги (`meta.company.cbr_regnum`). Длинный
некруглый регномер (2673, 1481) тесты ищут числом с границами слова — в коде такому числу взяться
неоткуда. Регномер, похожий на обычное число кода (`plain_regnum`: короче четырёх знаков или круглый —
кончается двумя нулями: 1000, 100, 1), так искать нельзя: `THOUSAND = 1000`, `x * 1000 / n` и «1000
прогонов» — не регномер, и тест краснел бы на собственном коде. Такой регномер ищется иначе:

* **строковым литералом** — строка в кавычках, равная регномеру (`"1000"`, `'1000'`);
* **числом в контексте** — в той же или в соседней строке исходника стоит слово о регномере
  (`REGNUM_WORDS`: `regnum`, `reg_num`, `RegNumber`, `regn`, `reg_no`, `regno`, `registration`,
  `license` / `licence`, `bank_id`, `cbr_bank`, теги службы форм `CredorgNumber` / `CredprgNumber`,
  параметр адреса `…id=`, «рег.», «рег. №», «регномер», «регистрационный», «лицензия»):
  `regnum = 1000`, `{"cbr_regnum": 1000}`, `"…?regn=1000"`, `"<CredorgNumber>1000</CredorgNumber>"`,
  `"…?id=1000"`, `# банк, рег. № 1000`. Число читается и в записи с подчёркиванием (`1_000`);
* **числом в вызове** (исходники Python, `regnum_call_hits`) — константа, равная регномеру, передана
  функции на место параметра, имя которого — слово о регномере: `dates_request("101", 1000)` при
  `def dates_request(form, regnum)`. Слова рядом может не быть вовсе — параметр называет определение.

Правило выбирают данные книги, а не имя банка: у книги с длинным некруглым регномером поведение
прежнее. Это тот же приём, что у короткого тикера (тикер из одной буквы ищется только строковым
литералом): слово, которое совпадает с обычными именами и числами кода, проверяется там, где оно
может быть только литералом эмитента.

Чего правило не видит (и не может, не краснея на своём коде): регномер голым числом без слова о
регномере в той же или соседней строке и не на месте параметра-регномера (`x = 1000`), число,
собранное арифметикой, и запись в другой системе счисления.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Mapping

PLAIN_REGNUM_DIGITS = 4          # регномер короче — обычное число кода
# Слова, рядом с которыми число — регномер (регистр не важен): имена переменных и ключей, теги службы
# форм регулятора (регномер уходит в запрос в теге; у тега дат — с опечаткой службы), параметр адреса
# с идентификатором, слова комментариев и подписей.
REGNUM_WORDS = (r"(?:reg_?num|regn(?![a-z])|reg_?no(?![a-z])|reg_?code|registration|cred[op]rg|licen[cs]e"
                r"|bank_?(?:id|code|num|no)(?![a-z])|cbr_?(?:bank|id|code|org)(?![a-z])|[?&][\w.\-]*id="
                r"|рег\.|рег\s*№|регномер|регистрационн|лицензи)")
_WORD = re.compile(rf"(?i){REGNUM_WORDS}")


def plain_regnum(regnum) -> bool:
    """Регномер выглядит обычным числом кода: короче четырёх знаков или кончается двумя нулями."""
    digits = str(regnum).strip()
    return len(digits) < PLAIN_REGNUM_DIGITS or digits.endswith("00")


def _bare(digits: str) -> str:
    """Число отдельным словом: не часть имени, не часть большего числа и не целая часть дроби. Между
    цифрами допускается подчёркивание записи чисел (`1_000`)."""
    return rf"(?<![\w.]){'_?'.join(re.escape(d) for d in digits)}(?![\w]|[.,]\d)"


def regnum_patterns(regnum) -> list[re.Pattern]:
    """Шаблоны регномера-«обычного числа»: строковый литерал, равный регномеру, и число в строке со словом о
    регномере или в соседней с ней (слово — до числа или после него). Совпадение второго шаблона — кусок
    текста от слова до числа."""
    digits = str(regnum).strip()
    bare = _bare(digits)
    near = r"[^\n]*?(?:\n[^\n]*?)?"            # до конца строки и, если надо, в следующую
    return [re.compile(rf"""(["'`])\s*{re.escape(digits)}\s*\1"""),
            re.compile(rf"(?i){REGNUM_WORDS}{near}{bare}|{bare}{near}{REGNUM_WORDS}")]


def regnum_hits(source: str, regnum) -> list[tuple[int, str]]:
    """Находки регномера-«обычного числа» в тексте: (номер строки, чем найден)."""
    digits = str(regnum).strip()
    quoted, context = regnum_patterns(digits)
    out = []
    for m in quoted.finditer(source):
        out.append((source.count("\n", 0, m.start()) + 1, f"регномер «{digits}» строковым литералом"))
    for m in context.finditer(source):
        out.append((source.count("\n", 0, m.start()) + 1, f"регномер «{digits}» рядом со словом о регномере"))
    return sorted(set(out))


# ------------------------------------------------------------------ число в вызове (Python)

def regnum_parameters(sources: Iterable[str]) -> dict[str, dict]:
    """Функции исходников Python с параметром-регномером: имя функции → {"positions": места параметра в
    вызове, "names": имена параметра}. Параметр — регномер, если его имя — слово о регномере. У метода
    (первый параметр `self` или `cls`) место считается без него. Одноимённые функции складываются."""
    out: dict[str, dict] = {}
    for source in sources:
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = [a.arg for a in node.args.posonlyargs + node.args.args]
            shift = 1 if positional[:1] in (["self"], ["cls"]) else 0
            for i, name in enumerate(positional):
                if _WORD.search(name):
                    spec = out.setdefault(node.name, {"positions": set(), "names": set()})
                    spec["positions"].add(i - shift)
                    spec["names"].add(name)
            for a in node.args.kwonlyargs:
                if _WORD.search(a.arg):
                    out.setdefault(node.name, {"positions": set(), "names": set()})["names"].add(a.arg)
    return out


def regnum_call_hits(source: str, regnum, parameters: Mapping[str, Mapping]) -> list[tuple[int, str]]:
    """Находки регномера-«обычного числа» в вызовах исходника Python: константа, равная регномеру (числом
    или строкой), на месте параметра-регномера функции из `parameters` (`regnum_parameters`) либо
    именованным аргументом, имя которого — слово о регномере."""
    digits = str(regnum).strip()

    def is_regnum(node) -> bool:
        if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
            return False
        value = node.value
        return (isinstance(value, int) and str(value) == digits) or (isinstance(value, str) and value.strip() == digits)

    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        spec = parameters.get(name) or {"positions": (), "names": ()}
        found = [a for i, a in enumerate(node.args) if i in spec["positions"] and is_regnum(a)]
        found += [k.value for k in node.keywords
                  if k.arg and (k.arg in spec["names"] or _WORD.search(k.arg)) and is_regnum(k.value)]
        out += [(a.lineno, f"регномер «{digits}» аргументом вызова {name}") for a in found]
    return sorted(set(out))
