# -*- coding: utf-8 -*-
"""Быстрые числа книги для приёма миров (шаг `quick` манифеста; формат `850-worlds/model-kit/README.md`).

    python -B ops/tools/quick_numbers.py --out ФАЙЛ.json [--runs N] [--workers N]
    python -B ops/tools/quick_numbers.py --check-tables      # 0 — таблицы книги посчитаны на этой книге (и словах записи развилок)

Пишет JSON: `point`, `low`, `high` (точка по сетке и её концы при λ слоя — функции ядра, ₽ на акцию), `worlds` (цены
миров N, H, M слоя «свой макро-взгляд»), `median`, `print` (печать медианы на витрине), `band80`, `band50`, `runs`, `seed`,
`source`. Медиана и полоса — из таблиц книги (`results.json`), если таблицы посчитаны на этой книге (числовой отпечаток
книги и версия равны), иначе — малая полоса (`--runs` прогонов, зерно книги; `source: small_band`). Малая полоса
печатается всегда отдельным блоком `small` — её числа сравнимы между любыми двумя книгами одного числа прогонов.
Гейты таблиц — `gates_fired` (только если таблицы этой книги). Ничего, кроме `--out`, не пишет.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "data" / "assumptions" / "results.json"


def tables_of(book) -> dict | None:
    """Таблицы книги, если они посчитаны на этой книге (версия и числовой отпечаток), иначе None."""
    from model.book_results import book_numbers
    if not RESULTS.exists():
        return None
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    rec = res.get("reference_record") or {}
    if str(res.get("book_version")) != str(book.get("meta.version")) or rec.get("book_numbers") != book_numbers(book):
        return None
    forks = ROOT / "data" / "assumptions" / "forks_rd.json"         # слова «без цены» таблицы берут из записи развилок
    if forks.exists():
        words = {k: r.get("why") for k, r in (json.loads(forks.read_text(encoding="utf-8")).get("variants") or {}).items()}
        if any(words.get(v["id"]) and v.get("why") != words[v["id"]] for v in res.get("reference_variants") or []):
            return None
    return res


def numbers(runs: int, workers: int) -> dict:
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.grid import live_from_book, run_grid
    os.environ.setdefault("BANK_WORKERS", str(workers))
    facts = load_facts()
    book = load_book(facts=facts)
    live = live_from_book(book, facts)
    main = str(book.get("meta.company.main_ticker"))
    g = run_grid(book, facts, live)
    la = g.layers["analytical"]
    worlds = {}
    for w, ww in la.world_weights.items():
        v = sum(la.prob[c.key] / ww * c.v_price for c in g.cells if c.world == w and la.prob[c.key])
        worlds[w] = round(g.price_of(v), 4)
    band = U.band(book, facts, live, draws=runs, workers=workers)
    head = band.headline(g.lam, live.prices, main)
    U.close_pool()
    small = {"median": round(head["median"], 4), "print": head["printed_median"], "band80": [round(x, 4) for x in head["band80"]],
             "band50": [round(x, 4) for x in head["band50"]], "runs": band.draws, "seed": band.seed}
    out = {"book_version": str(book.get("meta.version")), "point": round(g.point, 4), "low": round(g.low, 4),
           "high": round(g.high, 4), "worlds": worlds, "small": small}
    tab = tables_of(book)
    if tab is not None:
        h = tab["headline"]
        out.update(median=round(h["median"], 4), print=h["printed_median"], band80=[round(x, 4) for x in h["band80"]],
                   band50=[round(x, 4) for x in h["band50"]], runs=int(h["draws"]), seed=int(h["seed"]), source="tables",
                   gates_fired=sorted(c["name"] for c in tab["checks"] if c.get("kind") == "gate" and c.get("fired")))
    else:
        out.update(median=small["median"], print=small["print"], band80=small["band80"], band50=small["band50"],
                   runs=small["runs"], seed=small["seed"], source="small_band")
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check-tables", action="store_true")
    ap.add_argument("--runs", type=int, default=400)
    ap.add_argument("--workers", type=int, default=int(os.environ.get("BANK_WORKERS", "2")))
    a = ap.parse_args(argv)
    if a.check_tables:
        from model.book import load_book, load_facts
        book = load_book(facts=load_facts())
        ok = tables_of(book) is not None
        print(f"таблицы книги {'— этой книги' if ok else 'НЕ этой книги (или их нет)'}: версия {book.get('meta.version')}")
        return 0 if ok else 1
    if a.out is None:
        ap.error("--out обязателен")
    res = numbers(a.runs, a.workers)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"книга {res['book_version']}: точка {res['point']:.2f} ₽ ({res['low']:.2f}–{res['high']:.2f}), медиана "
          f"{res['median']:.2f} ₽ (печать {res['print']}; {res['source']}), миры " +
          " / ".join(f"{w} {v:.2f}" for w, v in res["worlds"].items()) +
          f"; малая полоса {res['small']['runs']}: медиана {res['small']['median']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
