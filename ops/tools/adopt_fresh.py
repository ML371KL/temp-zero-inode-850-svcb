# -*- coding: utf-8 -*-
"""Запись шага посчитана на нынешних входах: проверка `skip_if` команды приёма миров для записей, которые несут коммит
и день счёта (сводка контрольной модели): повтор такого шага на той же книге менял бы только их.

    python -B ops/tools/adopt_fresh.py ФАЙЛ ПОЛЕ ПУТЬ [ПУТЬ …]

Код 0 — запись `ФАЙЛ` (JSON) называет коммит в поле `ПОЛЕ`, и входы шага (`ПУТЬ …` — файлы и каталоги дерева) с этого
коммита не менялись ни в истории, ни в рабочей копии; 1 — записи нет, коммита нет или входы менялись. Ничего не пишет.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        print(__doc__)
        return 2
    rec, field, paths = ROOT / args[0], args[1], args[2:]
    if not rec.exists():
        print(f"нет записи {args[0]}")
        return 1
    commit = json.loads(rec.read_text(encoding="utf-8")).get(field)
    if not commit or subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"]).returncode != 0:
        print(f"{args[0]}: в поле {field} нет коммита дерева")
        return 1
    diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", commit, "--", *paths])
    if diff.returncode != 0:
        print(f"{args[0]}: входы шага менялись с {commit[:12]}")
        return 1
    print(f"{args[0]}: запись коммита {commit[:12]}, входы шага с тех пор не менялись")
    return 0


if __name__ == "__main__":
    sys.exit(main())
