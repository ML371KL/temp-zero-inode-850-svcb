# -*- coding: utf-8 -*-
"""Прогулка версии книги при приёме миров: файл шагов — из шагов манифеста приёма, расчёт — `ops/tools/walk_book.py`.

    python -B ops/tools/adopt_walk.py [--median] [--draws N]

Шаги прогулки — поля `walk` шагов манифеста `data/assumptions/worlds_dependents.yaml` по порядку (`walk.order`, иначе
порядок манифеста): `name` (поля индекса версии и манифеста в фигурных скобках: `{labels.walk_step}`, `{version}`,
`{book.version}`), `keys` — ключи книги, которые шаг берёт из конечной книги. Шаг с `rest: true` берёт все прочие
ключи, которыми книги расходятся (выведенные на ядре числа, концы осей, варианты): прогулка обязана сойтись — «книга
после шагов = конечная книга целиком». Стартовая книга — машинная книга коммита, с которого принята версия миров
(`worlds_state.json`, блок `book`), конечная — книга дерева.

Пишет `data/assumptions/evidence/path/inputs/walk_<было>_to_<стало>.yaml` (шаги) и `.../out/walk_<было>_to_<стало>.txt`
(печать прогулки); `var/adopt/walk.json` — строки для отчёта приёма. Код — код `walk_book.py` (0 — обе проверки «ДА»).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adopt_worlds as A  # noqa: E402

PATH_DIR = ROOT / "data" / "assumptions" / "evidence" / "path"


def leaves(d, prefix: str = "") -> dict:
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(leaves(v, f"{prefix}{k}."))
    else:
        out[prefix[:-1]] = d
    return out


def claimed(path: str, keys: list[str]) -> bool:
    return any(path == k or path.startswith(k + ".") for k in keys)


def rest_keys(start: dict, end: dict, taken: list[str]) -> list[str]:
    """Ключи, которыми книги расходятся вне шагов с явными ключами, — с точностью до второго уровня (ось или вариант —
    список: берётся целиком)."""
    a, b = leaves(start), leaves(end)
    diff = sorted(k for k in set(a) | set(b) if a.get(k, A) != b.get(k, A) and not claimed(k, taken))
    out = []
    for k in diff:
        parts = k.split(".")
        head = ".".join(parts[:2]) if len(parts) > 2 else k
        if parts[0] in ("valuation", "capital", "checks", "volumes", "regimes", "nii", "opex", "fees", "other") and len(parts) > 3:
            head = ".".join(parts[:3])
        if not claimed(head, taken) and head not in out:
            out.append(head)
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--median", action="store_true")
    ap.add_argument("--draws", type=int)
    a = ap.parse_args(argv)
    manifest = A.load_manifest(ROOT)
    state = A.read_state(ROOT)
    book = state.get("book") or {}
    if not book.get("from_commit"):
        print("ОТКАЗ: в состоянии нет блока book (с какой книги принята версия миров) — прогулку не от чего вести")
        return 2
    src = A.Source(A.find_source(None))
    v = str(state["version"])
    from_v = str(book.get("from_worlds") or v)
    ctx = A.context(manifest, src.entry(v), src.entry(from_v) if from_v in src.index["versions"] else None, v, from_v)
    ctx.update(A.book_ctx(book))
    var = ROOT / "var" / "adopt"
    var.mkdir(parents=True, exist_ok=True)
    start_p = var / f"book-{book['from']}.json"
    start_p.write_text(A.git(ROOT, "show", f"{book['from_commit']}:data/assumptions/assumptions.json"), encoding="utf-8")
    start = json.loads(start_p.read_text(encoding="utf-8"))
    end = json.loads((ROOT / "data" / "assumptions" / "assumptions.json").read_text(encoding="utf-8"))
    specs = [s for s in A.walk_steps(manifest["steps"]) if s.get("walk")]
    specs = sorted(enumerate(specs), key=lambda p: (p[1]["walk"].get("order", p[0]), p[0]))
    taken = [k for _, s in specs for k in s["walk"].get("keys", [])]
    steps = []
    for _, s in specs:
        w = s["walk"]
        keys = rest_keys(start, end, taken) if w.get("rest") else list(w["keys"])
        if keys:
            name = A.expand(w["name"], ctx)
            steps.append({"name": name[:1].upper() + name[1:], "from_end": keys})
    tag = f"{book['from']}_to_{book['version']}"
    steps_p = PATH_DIR / "inputs" / f"walk_{tag}.yaml"
    head = (f"# Прогулка книги {book['from']} → {book['version']} ({ctx.get('title', '')}): шаги ops/tools/walk_book.py по "
            f"шагам манифеста приёма миров {v} (ops/tools/adopt_walk.py; правится манифестом, не руками).\n")
    steps_p.write_text(head + yaml.safe_dump(steps, allow_unicode=True, sort_keys=False, width=10 ** 6), encoding="utf-8", newline="\n")
    cmd = [sys.executable, "-B", str(ROOT / "ops" / "tools" / "walk_book.py"), "--start", str(start_p),
           "--end", str(ROOT / "data" / "assumptions" / "assumptions.json"), "--steps", str(steps_p), "--json", str(var / "walk.json")]
    if a.median:
        cmd.append("--median")
    if a.draws:
        cmd += ["--draws", str(a.draws)]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = (p.stdout or "") + (p.stderr or "")
    (PATH_DIR / "out" / f"walk_{tag}.txt").write_text(out, encoding="utf-8", newline="\n")
    print(out.rstrip())
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
