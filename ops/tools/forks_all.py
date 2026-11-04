# -*- coding: utf-8 -*-
"""Все развилки книги сухим перевыводом и запись `forks_rd.json` одной командой (шаг приёма миров).

    python -B ops/tools/forks_all.py [--commit REF] [--threads N] [--workers N] [--out КАТАЛОГ] [--only МЕТКА,…]

Перечень — из книги и описания вывода (как у `forks.py record`): каждый справочный вариант
(`valuation.reference_variants`; правка — `FORKS`, иначе `var:<id>`), каждое замыкание капитала «цены правила»
(`RULE_FORKS`, замыкание книги — `base`) и база. Метки делятся на `--threads` очередей; очередь — один процесс
`forks.py run` со своим каталогом (`--workers` процессов полосы), очереди идут одновременно. Затем
`forks.py record --runs <очередь>/runs.json … --write` и `forks.py --check`. Машина общая: по умолчанию 2 очереди × 2
процесса. Код — 0, если запись написана и это запись книги дерева.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FORKS = ROOT / "ops" / "tools" / "forks.py"
# долгие развилки (сухой перевывод с правкой листа, допуски концов) — в начало очередей
HEAVY = ("looseends", "hump", "middle", "nimL", "bridgelit", "norho", "k3core")


SPEC = "data/assumptions/evidence/path/derive_spec.py"
WORDS_ONLY = ("FORK_WHY", "FORK_MARKS")              # слова записи развилок: на сухой перевывод не влияют


def spec_core(rev: str) -> str:
    """Описание вывода коммита без слов записи развилок (их правка не повод перевыводить развилки)."""
    text = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{SPEC}"], capture_output=True, text=True,
                          encoding="utf-8").stdout
    for name in WORDS_ONLY:
        a = text.find(f"\n{name} = {{")
        if a >= 0:
            b = text.find("\n}\n", a)
            text = text[:a] + text[b + 3:]
    return "\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("#"))   # и без строк-комментариев


def plan() -> list[tuple[str, str]]:
    from model.book import load_book, load_facts
    from model.book_results import rule_closures
    sys.path.insert(0, str(ROOT / "data" / "assumptions" / "evidence" / "path"))
    spec_p = ROOT / "data" / "assumptions" / "evidence" / "path" / "derive_spec.py"
    sp = importlib.util.spec_from_file_location("_forks_all_spec", spec_p)
    spec = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(spec)
    book = load_book(facts=load_facts())
    forks, rule_forks = dict(getattr(spec, "FORKS", {}) or {}), dict(getattr(spec, "RULE_FORKS", {}) or {})
    items = [("base", "base")]
    for v in book.opt("valuation.reference_variants") or []:
        vid = str(v["id"])
        items.append((vid, forks.get(vid, f"var:{vid}")))
    closures = rule_closures(book)
    if closures is not None:
        current, keys = closures
        items += [(k, rule_forks.get(k, f"rule:{k}")) for k in keys if k != current]
    seen, out = set(), []
    for label, fork in items:
        if fork not in seen:
            seen.add(fork)
            out.append((label, fork))
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--workers", type=int, default=int(os.environ.get("BANK_WORKERS", "2")))
    ap.add_argument("--out", type=Path, default=ROOT / "var" / "forks-adopt")
    ap.add_argument("--only")
    ap.add_argument("--reuse", action="store_true",
                    help="готовые итоги прежнего запуска в --out (тот же коммит или коммит с той же книгой, фактами и ядром) не "
                         "перезапускать: продолжение после сбоя записи")
    ap.add_argument("--check", action="store_true",
                    help="ничего не пишет: 0 — запись forks_rd.json этой книги и (если итоги прогонов в --out есть) равна "
                         "записи, которую дали бы эти итоги со словами описания вывода сейчас")
    a = ap.parse_args(argv)
    if a.check:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        c = subprocess.run([sys.executable, "-B", str(FORKS), "--check"], cwd=ROOT, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        print((c.stdout or "").strip(), flush=True)
        runs = sorted(a.out.glob("q*/runs.json"))
        if c.returncode != 0 or not runs:
            if not runs and c.returncode == 0:
                print("итогов прогонов рядом нет — сверка по числовому отпечатку", flush=True)
            return c.returncode
        rec = [sys.executable, "-B", str(FORKS), "record"] + [x for p in runs for x in ("--runs", str(p))]
        r = subprocess.run(rec, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print((r.stdout or "") + (r.stderr or ""), flush=True)
            return 1
        now = json.loads((ROOT / "data" / "assumptions" / "forks_rd.json").read_text(encoding="utf-8"))
        same = json.loads(r.stdout.split("\n", 1)[1]) == now
        print("запись развилок равна итогам прогонов и словам описания" if same else
              "запись развилок НЕ равна записи из итогов прогонов (слова описания вывода сменились?)", flush=True)
        return 0 if same else 1
    items = plan()
    if a.only:
        keep = set(a.only.split(","))
        items = [x for x in items if x[0] in keep or x[0] == "base"]
    items.sort(key=lambda x: (x[0] != "base", not any(h in x[1] for h in HEAVY)))
    done = {}
    if a.reuse:
        for p in sorted(a.out.glob("q*/runs.json")):
            for label, row in json.loads(p.read_text(encoding="utf-8")).items():
                same = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", str(row.get("commit")), "HEAD", "--",
                                       "data/assumptions/assumptions.json", "data/facts", "model",
                                       "data/assumptions/evidence/path", f":(exclude){SPEC}"]).returncode == 0 \
                    and spec_core(str(row.get("commit"))) == spec_core("HEAD")
                if same and row.get("status") in ("price", "no_price") and "point" in row:
                    done[label] = p.parent
        print(f"готовые итоги той же книги: {len(done)} — не перезапускаются", flush=True)
    else:
        shutil.rmtree(a.out, ignore_errors=True)
    items = [x for x in items if x[0] not in done]
    queues: list[list[tuple[str, str]]] = [[] for _ in range(max(1, a.threads))]
    for i, it in enumerate(items):
        queues[i % len(queues)].append(it)
    procs = []
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", BANK_WORKERS=str(a.workers))
    for i, q in enumerate(queues):
        if not q:
            continue
        d = a.out / f"q{i}"
        d.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-B", str(FORKS), "run", "--commit", a.commit, "--workers", str(a.workers), "--out", str(d)]
        cmd += [f"{label}={fork}" for label, fork in q]
        log = open(d / "run.log", "w", encoding="utf-8")
        procs.append((d, log, subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)))
        print(f"очередь {i}: {len(q)} развилок — {', '.join(l for l, _ in q)}", flush=True)
    bad = 0
    for d, log, p in procs:
        rc = p.wait()
        log.close()
        bad += rc != 0
        print(f"{d.name}: код {rc}", flush=True)
    print(f"развилки: {len(items)} за {round(time.time() - t0)} с", flush=True)
    if bad:
        return 1
    rec = [sys.executable, "-B", str(FORKS), "record", "--write"]
    for p in sorted(a.out.glob("q*/runs.json")):          # все очереди — и с итогами прежнего запуска (--reuse)
        rec += ["--runs", str(p)]
    r = subprocess.run(rec, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or "").splitlines()[-2:] if r.returncode == 0 else (r.stdout or "") + (r.stderr or ""), flush=True)
    if r.returncode != 0:
        return 1
    c = subprocess.run([sys.executable, "-B", str(FORKS), "--check"], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print((c.stdout or "").strip(), flush=True)
    return c.returncode


if __name__ == "__main__":
    sys.exit(main())
