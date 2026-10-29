# -*- coding: utf-8 -*-
"""Сборщик шаблона книги Совкомбанка из фрагментов листов этапа 1 (фаза 3, 21.10.2026) — разовый запуск.

Шаблон `data/assumptions/assumptions_template.yaml` собирается текстом: каркас `template_skeleton.yaml` (meta, joint,
заголовки разделов) с метками вида `#{{FRAG <файл>|<ключ>}}` — на место метки встаёт раздел фрагмента листа КАК ЕСТЬ
(значения и комментарии-источники потоков); `<ключ>` — верхний ключ фрагмента (`nii`) или подблок второго уровня
(`joint.regime_prob`). Метки `#{{WORLDS_PART}}`, `#{{VALUATION_PART}}`, `#{{CHECKS_PART}}` — часть миров шаблона Т (запись
семейства без изменений) и части сборщика `valuation_part.yaml`, `checks_part.yaml`.

После сборки шаблон правят руками и командой перевывода (ops/tools/rederive.py); повторный запуск сборщика затрёт эти
правки — он нужен только как запись того, из чего шаблон родился.

Запуск из корня рабочей копии:
  python -B data/assumptions/evidence/assemble/assemble_template.py [--stage1 ПУТЬ] [--out ПУТЬ] [--worlds-from ПУТЬ]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STAGE1 = ROOT.parents[1] / "svcb-850-handoff" / "stage1"
PARTS = {"#{{VALUATION_PART}}": "valuation_part.yaml", "#{{CHECKS_PART}}": "checks_part.yaml"}
MARK = re.compile(r"^(\s*)#\{\{FRAG ([^|]+)\|([^}]+)\}\}\s*$")


def top_section(lines: list[str], key: str) -> list[str]:
    """Раздел верхнего ключа: строка `key:` и всё до следующей строки с непробельным первым знаком."""
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^{re.escape(key)}:(\s|$)", ln)), None)
    if start is None:
        raise KeyError(key)
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln and not ln[0].isspace():
            break
        out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return out


def sub_section(lines: list[str], top: str, sub: str) -> list[str]:
    """Подблок `top.sub`: строка `  sub:` внутри раздела `top` и строки с отступом больше двух."""
    sec = top_section(lines, top)
    start = next((i for i, ln in enumerate(sec) if re.match(rf"^  {re.escape(sub)}:(\s|$)", ln)), None)
    if start is None:
        raise KeyError(f"{top}.{sub}")
    out = [sec[start]]
    for ln in sec[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip(" "))) <= 2:
            break
        out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return out


def fragment(stage1: Path, name: str, key: str) -> list[str]:
    lines = (stage1 / name).read_text(encoding="utf-8").splitlines()
    parts = key.split(".")
    if len(parts) == 1:
        return top_section(lines, parts[0])
    if len(parts) == 2:
        return sub_section(lines, parts[0], parts[1])
    raise ValueError(f"ключ {key}: поддерживаются верхний ключ и подблок второго уровня")


def worlds_part(source: Path) -> list[str]:
    """Блок миров шаблона Т (запись семейства) — без изменений, от заголовка раздела до метки WORLDS_BANK."""
    lines = source.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("# ---") and "МИРЫ" in ln)
    end = next(i for i, ln in enumerate(lines) if ln.strip() == "#{{WORLDS_BANK}}")
    return lines[start:end + 1]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="сборка шаблона книги Совкомбанка из фрагментов листов этапа 1")
    ap.add_argument("--stage1", type=Path, default=STAGE1)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "assumptions" / "assumptions_template.yaml")
    ap.add_argument("--worlds-from", type=Path, default=ROOT / "data" / "assumptions" / "assumptions_template.yaml",
                    help="шаблон, из которого берётся блок миров (по умолчанию — текущий шаблон дерева)")
    a = ap.parse_args(argv)
    worlds = worlds_part(a.worlds_from)
    out: list[str] = []
    used: list[str] = []
    for ln in (HERE / "template_skeleton.yaml").read_text(encoding="utf-8").splitlines():
        m = MARK.match(ln)
        if m:
            name, key = m.group(2).strip(), m.group(3).strip()
            out += fragment(a.stage1, name, key)
            used.append(f"{name}|{key}")
        elif ln.strip() == "#{{WORLDS_PART}}":
            out += worlds
        elif ln.strip() in PARTS:
            for part in (HERE / PARTS[ln.strip()]).read_text(encoding="utf-8").rstrip("\n").splitlines():
                pm = MARK.match(part)
                if pm:
                    out += fragment(a.stage1, pm.group(2).strip(), pm.group(3).strip())
                    used.append(f"{pm.group(2).strip()}|{pm.group(3).strip()}")
                else:
                    out.append(part)
        else:
            out.append(ln)
    text = "\n".join(out) + "\n"
    a.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"шаблон: {a.out} — {len(out)} строк; фрагментов {len(used)}:")
    for u in used:
        print("  ", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
