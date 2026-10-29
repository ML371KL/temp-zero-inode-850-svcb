"""Худший по времени случай сборки выпуска — на цене у медианы; в памяти, ничего не пишет.

    python ops/tools/worst_build.py [--side both|up|down] [--stops K] [--price ЦЕНА] [--fast] [--json файл]

Время сборки зависит от цены. Строка обратного расчёта, у которой решение попадает в диапазон
книги, уточняется на полной полосе (docs/MODEL.md §11) — до `valuation.uncertainty.median_refine`
полных полос на строку; книга может назвать уточняемые строки списком
(`valuation.reverse_dcf.refine_rows`) — остальные тогда несут корень подвыборки и в счёт не идут. Чем ближе цена к медиане оценки, тем больше строк решается внутри
диапазона; на самой медиане поиска нет вовсе (решение каждой строки — значение книги): это
лучший случай, а не худший. Худший — цена рядом с медианой, за стопом поиска: в диапазоне все
строки, у которых он это допускает.

Инструмент собирает полный выпуск на цене, дате и реестре книги (как сборка с `--book-only`),
заменив цену главного тикера ценой «медиана ± K стопов поиска» (`valuation.headline.search_tol_rub`;
K — `--stops`, по умолчанию 2) — выше и ниже медианы: диапазоны строк несимметричны. У каждой
сборки он называет время, число строк, уточнённых на полной полосе, и число полных сеток, а затем
достраивает время до оценки сверху: каждая такая строка — с полным числом шагов уточнения (рядом
с медианой уточнение часто кончается за один шаг, дальше от неё — за два). Время одной полной
полосы меряется отдельным счётом. Итог — наибольшая из оценок сторон: она и ложится в бюджет
(`ops/budgets.json` → `basis.build_worst_s`; ops/README.md §5, шаг 8, и §9). Число шагов поиска на
подвыборке в оценку не входит — оно в запасе бюджета.

Сборка идёт в памяти: каталог состояния, клон данных и последняя принятая цена не трогаются,
файлов инструмент не пишет (кроме `--json`). `--price` — одна сборка на названной цене;
`--fast` — быстрая сборка без поисков: проверка самого инструмента, замером не служит.

Время и память меряет `ops/tools/measure.py`, число процессов полосы — `BANK_WORKERS`:

    BANK_WORKERS=4 python ops/tools/measure.py -- python ops/tools/worst_build.py

Коды возврата: 0 — выпуски собраны; 1 — сборка отказала (причина названа, время до отказа
напечатано); 2 — нет входов (книга, факты, цена).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OK, FAILED, BAD_INPUT = 0, 1, 2
FULL_BASIS = "full"             # строка обратного расчёта, уточнённая на полной полосе (`gap_basis`)
SIDES = {"up": (1,), "down": (-1,), "both": (1, -1)}
DEFAULT_STOPS = 2.0             # цена — в стольких стопах поиска от медианы: ближе одного стопа поиска нет


class Refused(Exception):
    """Нет входов — код 2."""


def with_price(book, price: float):
    """Книга, в которой цена главного тикера заменена; остальное — как было."""
    main = str(book.get("meta.company.main_ticker"))
    prices = dict(book.get("meta.market_price"))
    if main not in prices:
        raise Refused(f"в книге нет цены главного тикера ({main})")
    if not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):
        raise Refused(f"цена {price!r} — не положительное число")
    prices[main] = float(price)
    return book.with_overrides({"meta.market_price": prices})


def refined(payload: dict) -> tuple[int, int, int]:
    """(строк обратного расчёта по осям книги, из них уточнено на полной полосе, полных сеток) собранного
    выпуска. Банковские строки блока в счёт не входят: они считаются из решений строк осей, без поиска."""
    block = payload.get("reverse_dcf") or {}
    rows = list(block.get("rows") or ())
    full = sum(1 for row in rows if row.get("gap_basis") == FULL_BASIS)
    return len(rows), full, int(block.get("full_grids") or 0)


def upper_bound(seconds: float, rows_full: int, full_grids: int, *, draws: int, refine: int,
                band_seconds: float) -> float:
    """Время сборки, достроенное до худшего: каждая строка, уточнённая на полной полосе, — с полным
    числом шагов уточнения. Недостающие полосы = строки × шаги − уже посчитанные полные сетки / прогоны."""
    missing = max(0.0, rows_full * refine - full_grids / draws)
    return seconds + missing * band_seconds


def measure_band(book, facts, draws: int) -> tuple[float, float]:
    """(медиана полной полосы на книге, время её счёта, с) — та же полоса, что считает сборка."""
    from model import uncertainty as U
    from model.grid import live_from_book

    started = time.monotonic()
    band = U.band(book, facts, live_from_book(book, facts), draws=draws)
    return float(band.medians(band.lam)["central"]), time.monotonic() - started


def build_at(book, facts, price: float, *, fast: bool) -> dict:
    """Одна сборка выпуска в памяти на цене `price`: время и счёт уточнений."""
    from model import payload as P

    started = time.monotonic()
    release = P.make_release(live=False, fast=fast, book=with_price(book, price), facts=facts)
    payload = P.build_payload(release)
    seconds = time.monotonic() - started
    rows, full, grids = refined(payload)
    return {"price": float(price), "seconds": round(seconds, 1), "reverse_rows": rows, "reverse_rows_full": full,
            "full_grids": grids, "median": payload["fair_value"]["headline"]["median"]}


def run(*, side: str = "both", stops: float = DEFAULT_STOPS, price: float | None = None, fast: bool = False,
        say=print) -> dict:
    """Замер худшего случая: полоса, сборки на ценах у медианы, оценка сверху. `say` — печать по ходу."""
    from model import reverse as RV
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.book_schema import BookError, FactsError

    if price is not None and not (math.isfinite(price) and price > 0):
        raise Refused(f"--price: цена {price!r} — не положительное число")
    if price is None and not stops > 1:
        raise Refused("--stops: цена ближе одного стопа к медиане поиска не запускает — нужно больше 1")
    try:
        facts = load_facts()
        book = load_book(facts=facts)
        draws = int(U.FAST_DRAWS if fast else book.get("valuation.uncertainty.draws"))
        # шагов уточнения на строку: ключ книги, но не больше предела ядра
        refine = min(int(book.get("valuation.uncertainty.median_refine")), int(RV.MAX_REFINE))
        stop = float(book.get("valuation.headline.search_tol_rub"))
    except (BookError, FactsError) as exc:
        raise Refused(f"книга или факты не читаются: {exc}") from exc
    median, band_seconds = measure_band(book, facts, draws)
    say(f"полоса: {draws} прогонов за {band_seconds:.0f} с; медиана {median:.2f} ₽; стоп поиска {stop:g} ₽, "
        f"шагов уточнения на строку — до {refine}")
    if price is not None:
        prices = [(float(price), "названная цена")]
    else:
        prices = [(median + sign * stops * stop, f"медиана {'+' if sign > 0 else '−'} {stops:g} стопа поиска")
                  for sign in SIDES[side]]
    rows = []
    for value, words in prices:
        row = build_at(book, facts, value, fast=fast)
        row["bound"] = round(upper_bound(row["seconds"], row["reverse_rows_full"], row["full_grids"], draws=draws,
                                         refine=refine, band_seconds=band_seconds), 1)
        rows.append(row)
        say(f"цена {value:.2f} ₽ ({words}): сборка {row['seconds']:.0f} с; строк обратного расчёта на полной "
            f"полосе — {row['reverse_rows_full']} из {row['reverse_rows']}, полных сеток {row['full_grids']}; с "
            f"полным числом шагов уточнения — не дольше {row['bound']:.0f} с")
    return {"fast": fast, "draws": draws, "refine": refine, "stop": stop, "median": round(median, 4),
            "band_seconds": round(band_seconds, 1), "builds": rows,
            "worst_seconds": math.ceil(max(row["bound"] for row in rows))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="worst_build.py",
                                 description="худший по времени случай сборки: цена у медианы, сборка в памяти")
    ap.add_argument("--side", choices=sorted(SIDES), default="both",
                    help="с какой стороны от медианы ставить цену (по умолчанию — обе сборки)")
    ap.add_argument("--stops", type=float, default=DEFAULT_STOPS,
                    help="расстояние цены от медианы в стопах поиска обратного расчёта (больше 1)")
    ap.add_argument("--price", type=float, help="одна сборка на этой цене главного тикера, ₽")
    ap.add_argument("--fast", action="store_true", help="быстрая сборка без поисков: проверка инструмента, не замер")
    ap.add_argument("--json", type=Path, help="записать итог в файл")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    started = time.monotonic()

    def say(line: str) -> None:
        print(line, flush=True)

    try:
        result = run(side=args.side, stops=args.stops, price=args.price, fast=args.fast, say=say)
    except Refused as exc:
        print(f"ОТКАЗ: {exc}", file=sys.stderr)
        return BAD_INPUT
    except Exception as exc:  # noqa: BLE001 — отказ сборки: причина и время до него нужны замеру
        print(f"ПРОВАЛ: сборка на цене у медианы отказала через {time.monotonic() - started:.0f} с: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return FAILED
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    if args.fast:
        print("быстрая сборка: инструмент работает; замером худшего случая это не служит")
    else:
        print(f"худший случай: сборка не дольше {result['worst_seconds']} с — в бюджет, basis.build_worst_s "
              "(вместе с числом процессов этого замера)")
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
