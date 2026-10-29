"""Развилки книги сухим перевыводом: цена справочного варианта и замыкания капитала — запись `forks_rd.json`.

    python -B ops/tools/forks.py run [--commit REF] [--runs N] [--workers N] [--out КАТАЛОГ] [--crn ФАЙЛ] МЕТКА=ПРАВКА …
    python -B ops/tools/forks.py record [--runs ФАЙЛ …] [--legacy ФАЙЛ …] [--legacy-books КАТАЛОГ …] [--accept ПУТЬ=ПОЧЕМУ …]
                                        [--write]
    python -B ops/tools/forks.py --check

Цена варианта книги (MODEL §14.5) — не точка книги с подменами на замороженных выведенных числах, а книга, перевыведенная
под вариант как под центр шаблона: вариант кладётся в шаблон копии дерева, лист вывода выводит под него корни, концы осей
и проверки (`ops/tools/rederive.py --dry-run`), и на пробной книге считаются точка по сетке и малая полоса. Так меряется и
цена замыкания капитала («цена правила», три замыкания `capital.growth_constraint`). Вариант, который лист перевести не
может (остановка вывода, гейт, отбор окон роли «центр»), — строка «без цены — причина». Запись лежит рядом с книгой, книга
называет её ключом `valuation.reference_record`; таблицы книги (`model.book_results`) берут из неё разности точки и
медианы. Запись несёт ЧИСЛОВОЙ отпечаток книги (`model.book_results.book_numbers` — значения ключей, а не слова): запись
от другой книги таблицы не печатают.

`run` — по метке на развилку: копия дерева коммита (`git archive`) → правка → сухой перевывод (`--no-quick --no-classes`)
→ правило отбора окон развилки (запись концов листа: окно роли «центр», чей отбор по своей границе ROE развилки изменился, —
без цены; изменились только окна роли «ось» — цена с пометкой) → числа на пробной книге в копии (`_numbers`: точка, цены
миров, масса капитального разрыва слоя «свой взгляд», малая полоса на общих случайных числах). Итог — `<out>/runs.json`
(дописывается по меткам), пробные книги — `<out>/books/<метка>.yaml`.
Правки (через «+»): `base` — книга как есть; `var:<id>` — подмены варианта книги (`valuation.reference_variants`) как центр
шаблона; `rule:<замыкание>` — подмены «цены правила» (`unconstrained`, `dividend_first`, `growth_first`); имя из описания
вывода (`FORK_PATCHES` в `derive_spec.py`) — правка листа или оси, которой нужен вариант (центр маржи, допуски концов).
Общие случайные числа: столбцы выборки — по осям базы (`--crn` или блок `crn` записи; ось узнаётся по виду и первому пути),
новые оси — своя выборка (зерно книги + 7), как у полос, которыми мерили развилки круга.

`record` — запись `data/assumptions/forks_rd.json` из итогов `run` (и прежних итогов той же формы — `--legacy`, сводка
`forks_summary.json`): строка на вариант книги и на замыкание капитала, правка — по описанию вывода (`FORKS`, иначе
`var:<id>`; замыкания — `RULE_FORKS`). Разности — к базе тех же общих случайных чисел; база нового прогона и прежняя должны
совпасть бит в бит. Вариант без цены несёт причину словами описания (`FORK_WHY`) — без слов запись не пишется. Отпечаток —
книги дерева; пробная книга базы обязана совпасть с ней числами (иначе отказ, кроме путей `--accept ПУТЬ=ПОЧЕМУ`, которые
лист вывода и оценка не читают — причина пишется в запись). Без `--write` запись печатается, файл не пишется.

`--check` — отпечаток записи против книги дерева: 0 — та же книга, 1 — другая или записи нет.
Вне сети; ничего не публикует. Тяжёлый прогон (сухой перевывод и малая полоса на развилку) — по одному на машине.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOOK_DIR = ROOT / "data" / "assumptions"
RECORD = BOOK_DIR / "forks_rd.json"
SCHEMA = "forks-rd-v1"
AX = "valuation.uncertainty.axes"
GROWTH = "capital.growth_constraint"
RUNS = 600                      # малая полоса развилки: прогонов (общие случайные числа)
NEW_AXES_SEED = 7               # новые оси — своя выборка: зерно книги + 7
PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
WORDS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


# ------------------------------------------------------------------ шаблон копии: точечная запись значения по пути книги


def _flow(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Mapping):
        return "{" + ", ".join(f"{k if PLAIN.match(str(k)) and str(k).lower() not in WORDS else json.dumps(str(k), ensure_ascii=False)}"
                               f": {_flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float):
        t = f"{v:.9f}".rstrip("0")
        return t + "0" if t.endswith(".") else t
    return str(v)


def _construct(node: yaml.Node) -> Any:
    return yaml.constructor.SafeConstructor().construct_object(node, deep=True)


def set_path(template: Path, dotted: str, value: Any) -> None:
    """Узел шаблона по точечному пути книги → значение (текст вне узла цел); ключа нет — дописывается в словарь-родитель."""
    text = template.read_text(encoding="utf-8")
    node, parts = yaml.compose(text, Loader=yaml.SafeLoader), dotted.split(".")
    for i, part in enumerate(parts):
        if isinstance(node, yaml.SequenceNode) and part.isdigit():
            node = node.value[int(part)]
            continue
        if not isinstance(node, yaml.MappingNode):
            raise SystemExit(f"forks: путь {dotted}: «{part}» — не словарь шаблона")
        hits = [(k, v) for k, v in node.value if str(_construct(k)) == part]
        if not hits:
            if i != len(parts) - 1:
                raise SystemExit(f"forks: в шаблоне нет ключа {dotted} (часть «{part}»)")
            if node.flow_style:
                end = node.end_mark.index - 1
                text = text[:end] + (", " if node.value else "") + f"{part}: {_flow(value)}" + text[end:]
            else:
                first = node.value[0][0]
                pos = first.start_mark.index - first.start_mark.column
                text = text[:pos] + " " * first.start_mark.column + f"{part}: {_flow(value)}\n" + text[pos:]
            template.write_text(text, encoding="utf-8", newline="\n")
            return
        node = hits[0][1]
    text = text[:node.start_mark.index] + _flow(value) + text[node.end_mark.index:]
    template.write_text(text, encoding="utf-8", newline="\n")


def set_axis(template: Path, first_path: str, fields: Mapping[str, Any]) -> None:
    """Поля оси полосы (по первому пути) в шаблоне: строка оси — поточная запись `- {…}`."""
    lines = template.read_text(encoding="utf-8").split("\n")
    hits = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*- )(\{.*\})(\s*#.*)?$", line)
        if m:
            d = yaml.safe_load(m.group(2))
            if isinstance(d, dict) and d.get("paths") and str(d["paths"][0]) == first_path and "kind" in d:
                hits.append((i, m, d))
    if len(hits) != 1:
        raise SystemExit(f"forks: ось с первым путём {first_path}: строк в шаблоне {len(hits)}, нужна одна")
    i, m, d = hits[0]
    d.update(fields)
    lines[i] = m.group(1) + _flow(d) + (m.group(3) or "")
    template.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ описание вывода и правки развилок


def load_spec(book_dir: Path):
    """Описание вывода книги (`evidence/path/derive_spec.py`) — модуль по пути; байткод в дерево не пишется."""
    path = book_dir / "evidence" / "path" / "derive_spec.py"
    spec = importlib.util.spec_from_file_location("forks_spec", path)
    module = importlib.util.module_from_spec(spec)
    for sibling in path.parent.glob("*.py"):              # лист рядом, загруженный из другого дерева, — забыть
        cached = sys.modules.get(sibling.stem)
        where = getattr(cached, "__file__", None) if cached is not None else None
        if where and Path(where).resolve() != sibling.resolve():
            del sys.modules[sibling.stem]
    sys.path.insert(0, str(path.parent))
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = keep
        sys.path.remove(str(path.parent))
    return module


def rule_overrides(key: str, book: Mapping[str, Any]) -> dict[str, Any]:
    """Подмены замыкания капитала (как `model.book_results.rule_closures`): unconstrained — выключатель, два других — порядок."""
    spec = (book.get("capital") or {}).get("growth_constraint")
    if spec is None:
        raise SystemExit("forks: в книге нет объекта capital.growth_constraint — замыканий нет")
    if key == "unconstrained":
        return {} if spec.get("enabled") is not True else {f"{GROWTH}.enabled": False}
    if key not in ("dividend_first", "growth_first"):
        raise SystemExit(f"forks: незнакомое замыкание {key!r}")
    out = {} if spec.get("enabled") is True and spec.get("order") == key else {f"{GROWTH}.order": key}
    if spec.get("enabled") is not True:
        out[f"{GROWTH}.enabled"] = True
    return out


def apply_fork(copy: Path, fork: str, patches: Mapping[str, Any]) -> list[str]:
    """Правка развилки в копии дерева; итог — строки журнала. Части — через «+»."""
    book_dir = copy / "data" / "assumptions"
    template = book_dir / "assumptions_template.yaml"
    log = []
    for part in fork.split("+"):
        name, _, arg = part.partition(":")
        book = yaml.safe_load(template.read_text(encoding="utf-8"))
        if name == "base":
            continue
        if name == "var":
            hits = [v for v in book["valuation"].get("reference_variants") or [] if str(v["id"]) == arg]
            if len(hits) != 1:
                raise SystemExit(f"forks: варианта {arg!r} в книге нет")
            for path, value in hits[0]["overrides"].items():
                set_path(template, path, value)
                log.append(f"{part}: {path} = {_flow(value)}")
        elif name == "rule":
            for path, value in rule_overrides(arg, book).items():
                set_path(template, path, value)
                log.append(f"{part}: {path} = {_flow(value)}")
        elif name in patches:
            p = patches[name]
            for rel, old, new in p.get("text", ()):
                target = book_dir / rel
                s = target.read_text(encoding="utf-8")
                if s.count(old) != 1:
                    raise SystemExit(f"forks: правка {name}: в {rel} место правки встречается {s.count(old)} раз (нужно 1)")
                target.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
                log.append(f"{name}: {rel} — {old.strip()[:60]} → {new.strip()[:60]}")
            for path, value in (p.get("book") or {}).items():
                set_path(template, path, value)
                log.append(f"{name}: {path} = {_flow(value)}")
            for first, fields in (p.get("axis") or {}).items():
                set_axis(template, first, fields)
                log.append(f"{name}: ось {first} — {_flow(fields)}")
        else:
            raise SystemExit(f"forks: незнакомая правка {part!r} (есть base, var:<id>, rule:<замыкание>, "
                             + ", ".join(sorted(patches)) + ")")
    return log


# ------------------------------------------------------------------ общие случайные числа и числа пробной книги


def crn_block(base_book: Path) -> dict[str, Any]:
    """Блок общих случайных чисел: оси базы (вид, первый путь) по порядку книги базы."""
    data = json.loads(base_book.read_text(encoding="utf-8")) if base_book.suffix == ".json" else yaml.safe_load(
        base_book.read_text(encoding="utf-8"))
    axes = data["valuation"]["uncertainty"]["axes"]
    return {"base_axes": [[str(a["kind"]), str(a["paths"][0])] for a in axes], "alias": [], "new_axes_seed": NEW_AXES_SEED}


def _numbers(book_path: Path, facts_dir: Path, crn: Mapping[str, Any], runs: int, workers: int) -> dict[str, Any]:
    """Числа пробной книги — функциями ядра копии: точка по сетке, цены миров, масса капитального разрыва и малая полоса
    на общих случайных числах (столбцы — по осям базы, новые оси — своя выборка)."""
    import pickle
    from model import uncertainty as U
    from model.book import load_book, load_facts
    from model.grid import live_from_book, run_grid

    facts = load_facts(facts_dir)
    book = load_book(book_path, facts=facts)
    live = live_from_book(book, facts)
    t = time.time()
    grid = run_grid(book, facts, live)
    axes = [dict(a) for a in book.get(AX)]
    for a in axes:
        U._check_axis(a)
    alias = {tuple(a): tuple(b) for a, b in crn.get("alias") or []}
    ident = lambda a: alias.get((str(a["kind"]), str(a["paths"][0])), (str(a["kind"]), str(a["paths"][0])))  # noqa: E731
    base = [tuple(x) for x in crn["base_axes"]]
    seed = int(book.get("valuation.uncertainty.seed"))
    p0 = U.draw_points(runs, len(base), seed)
    col = {b: j for j, b in enumerate(base)}
    new = [i for i, a in enumerate(axes) if ident(a) not in col]
    extra = U.draw_points(runs, len(new), seed + int(crn.get("new_axes_seed", NEW_AXES_SEED))) if new else [[] for _ in range(runs)]
    pos = {i: k for k, i in enumerate(new)}
    points = [[p0[r][col[ident(a)]] if ident(a) in col else extra[r][pos[i]] for i, a in enumerate(axes)] for r in range(runs)]
    blob = pickle.dumps((book, facts, live, list(axes), False), protocol=pickle.HIGHEST_PROTOCOL)
    rows = U._pool_map(U._band_worker, blob, [(s, None) for s in points], workers)
    if rows is None:
        rows = U.band_chunk(book, facts, live, axes, points)
    step = U.draw_step(book)
    band = U.Band(axes=tuple(axes), s=tuple(tuple(p) for p in points),
                  low_draws=U.stored_draws([r["low"] for r in rows], step),
                  high_draws=U.stored_draws([r["high"] for r in rows], step), draw_step=step, draws=len(points), seed=seed,
                  lam=float(book.get("joint.own_macro_confidence")),
                  print_step=float(book.get("valuation.headline.print_step")),
                  quantiles=tuple(float(q) for q in book.get("valuation.uncertainty.quantiles")),
                  ceiling_x_market=float(book.get("valuation.headline.ceiling_x_market")), rows=tuple(rows))
    st = band.stats(grid.lam)
    la = grid.layers["analytical"]
    worlds = {}
    for w in la.world_weights:
        ww = la.world_weights[w]
        v = sum(la.prob[c.key] / ww * c.v_price for c in grid.cells if c.world == w and la.prob[c.key])
        worlds[w] = round(grid.price_of(v), 4)
    U.close_pool()
    return {"point": round(grid.point, 6), "median": st["median"], "p10": st["p10"], "p90": st["p90"], "mean": round(st["mean"], 4),
            "worlds": worlds, "capital_gap_mass": la.capital_gap_mass, "axes": len(axes),
            "new_axes": [str(axes[i]["name"]) for i in new], "runs": runs, "seconds": round(time.time() - t, 1)}


# ------------------------------------------------------------------ run


def _sh(args: list[str], cwd: Path, log: Path, env: Mapping[str, str], timeout: int) -> int:
    with open(log, "w", encoding="utf-8") as fh:
        try:
            return subprocess.run(args, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, env=dict(env), timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return 124


def _why_failed(log: Path) -> list[str]:
    keys = ("ОТКАЗ", "ОСТАНОВКА", "срабатывает", "Traceback", "не сошёлся", "вне коридора", "•", "Error")
    return [ln.strip()[:400] for ln in log.read_text(encoding="utf-8", errors="replace").splitlines() if any(k in ln for k in keys)][:8]


def _pct(x: Any) -> str:
    return f"{100 * float(x):.2f}".replace(".", ",") + " %"


def selection_words(bound: Any, changed: Mapping[str, Mapping[str, Any]]) -> str | None:
    """Пометка цены, у которой по своей границе ROE развилки изменился отбор окон только роли «ось»."""
    if not changed:
        return None
    inside = lambda w: w.get("inside", w.get("inside_variant"))  # noqa: E731
    return ("отбор окон уровня по границе ROE варианта " + _pct(bound) + " меняет только ось (ось — книги): "
            + ", ".join(f"окно {n} {'входит' if inside(w) else 'выпадает'} (ROE {_pct(w.get('roe'))})" for n, w in changed.items()))


def selection(ends: Mapping[str, Any]) -> tuple[bool, str | None, dict]:
    """Правило отбора окон развилки по записи концов листа (граница ROE развилки): окно роли «центр», чей отбор
    изменился, — без цены; изменились только окна роли «ось» — цена с пометкой; не изменилось — цена."""
    rb = ends.get("roe_bound") or {}
    changed = {n: w for n, w in (rb.get("windows") or {}).items() if w.get("inside") != w.get("used_by_book")}
    if any("центр" in str(w.get("role")) for w in changed.values()):
        return False, ("по своей границе ROE развилки " + _pct(rb.get("bound")) + " изменился отбор окон роли «центр»: "
                       + ", ".join(f"{n} (ROE {_pct(w.get('roe'))})" for n, w in changed.items())), changed
    return True, selection_words(rb.get("bound"), changed), changed


def cmd_run(a: argparse.Namespace) -> int:
    out = Path(a.out).resolve()
    (out / "books").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", a.commit], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if a.crn:
        crn = crn_block(Path(a.crn)) if not a.crn.endswith(".crn.json") else json.loads(Path(a.crn).read_text(encoding="utf-8"))
    elif RECORD.exists():
        crn = json.loads(RECORD.read_text(encoding="utf-8"))["crn"]
    else:
        raise SystemExit("forks: нет блока общих случайных чисел — ни --crn, ни записи forks_rd.json")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", BANK_WORKERS=str(a.workers))
    (out / "crn.json").write_text(json.dumps(crn, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    res_p = out / "runs.json"
    for item in a.items:
        label, _, fork = item.partition("=")
        if not label or not fork:
            raise SystemExit(f"forks: «{item}» — нужно МЕТКА=ПРАВКА")
        t0 = time.time()
        copy = out / "copies" / label
        shutil.rmtree(copy, ignore_errors=True)
        copy.mkdir(parents=True)
        raw = subprocess.run(["git", "archive", a.commit, "model", "data", "ops", "pytest.ini"], cwd=ROOT, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
            tf.extractall(copy, filter="fully_trusted")
        spec = load_spec(copy / "data" / "assumptions")
        row: dict[str, Any] = {"fork": fork, "commit": commit, "date": dt.date.today().isoformat()}
        row["patch_log"] = apply_fork(copy, fork, getattr(spec, "FORK_PATCHES", {}) or {})
        log = out / "logs" / f"{label}.rederive.txt"
        rc = _sh([sys.executable, "-B", "ops/tools/rederive.py", "--dry-run", "--no-quick", "--no-classes", "--workers", str(a.workers),
                  "--label", f"forks-{label}"], copy, log, env, 3600)
        work = copy / "var" / "rederive" / f"forks-{label}"
        after = work / "after" / "assumptions.yaml"
        if rc != 0 or not after.exists():
            row.update(status="no_price", rc=rc, detail=_why_failed(log))
            print(f"{label} ({fork}): сухой перевывод остановлен, код {rc} — без цены", flush=True)
        else:
            ends_p = work / "derive_ends.json"
            ends = json.loads(ends_p.read_text(encoding="utf-8")).get("ends", {}) if ends_p.exists() else {}
            price, words, changed = selection(ends)
            row.update(roe_bound=(ends.get("roe_bound") or {}).get("bound"), selection=words,
                       windows_changed={n: {k: w.get(k) for k in ("roe", "role", "inside", "used_by_book")} for n, w in changed.items()},
                       phi=[(ends.get("phi_axis") or {}).get(k) for k in ("centre", "low", "high")])
            shutil.copy(after, out / "books" / f"{label}.yaml")
            crn_p = copy / "forks.crn.json"
            crn_p.write_text(json.dumps(crn, ensure_ascii=False), encoding="utf-8")
            num_p = copy / "forks.numbers.json"
            rc2 = _sh([sys.executable, "-B", "ops/tools/forks.py", "_numbers", "--book", str(after), "--facts", str(copy / "data" / "facts"),
                       "--crn", str(crn_p), "--runs", str(a.runs), "--workers", str(a.workers), "--out", str(num_p)],
                      copy, out / "logs" / f"{label}.numbers.txt", env, 5400)
            if rc2 != 0 or not num_p.exists():
                row.update(status="no_numbers", rc=rc2)
                print(f"{label} ({fork}): числа пробной книги не посчитаны, код {rc2}", flush=True)
            else:
                row.update(json.loads(num_p.read_text(encoding="utf-8")))
                row["status"] = "price" if price else "no_price"
                print(f"{label} ({fork}): точка {row['point']:.6f} медиана {row['median']:.4f} миры {row['worlds']} "
                      f"разрыв {row['capital_gap_mass']:.4f}" + ("" if price else " — без цены (отбор окон)"), flush=True)
        row["seconds"] = round(time.time() - t0)
        res = json.loads(res_p.read_text(encoding="utf-8")) if res_p.exists() else {}
        res[label] = row
        res_p.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        if not a.keep:
            shutil.rmtree(copy, ignore_errors=True)
    return 0


# ------------------------------------------------------------------ record и --check


def _norm_fork(patches: str | None) -> str:
    """Правка прежнего итога (поле patches сводки) → правка инструмента: «,» → «+», closure — порядок «дивиденд первым»."""
    parts = [p for p in str(patches or "").split(",") if p]
    if not parts:
        return "base"
    return "+".join("rule:dividend_first" if p == "closure" else p for p in parts)


def _grid_of(book_path: Path) -> dict[str, Any]:
    """Точка и масса капитального разрыва пробной книги на фактах дерева (сверка прежнего итога)."""
    from model.book import load_book, load_facts
    from model.grid import live_from_book, run_grid
    facts = load_facts()
    book = load_book(book_path, facts=facts)
    g = run_grid(book, facts, live_from_book(book, facts))
    return {"point": g.point, "capital_gap_mass": g.layers["analytical"].capital_gap_mass}


def _numbers_of(book: Any) -> dict[str, Any]:
    from model.book_results import book_numbers
    return book_numbers(book)


def _flat(x: Any, p: str = "") -> dict[str, Any]:
    if isinstance(x, Mapping):
        out: dict[str, Any] = {}
        for k, v in x.items():
            out.update(_flat(v, f"{p}.{k}" if p else str(k)))
        return out
    if isinstance(x, list):
        out = {}
        for i, v in enumerate(x):
            out.update(_flat(v, f"{p}[{i}]"))
        return out
    return {p: x}


def cmd_record(a: argparse.Namespace) -> int:
    from model.book import load_book, load_facts
    from model.book_results import RECORD_KEY, book_numbers, numbers_view, rule_closures
    facts = load_facts()
    book = load_book(facts=facts)
    spec = load_spec(BOOK_DIR)
    forks = dict(getattr(spec, "FORKS", {}) or {})
    rule_forks = dict(getattr(spec, "RULE_FORKS", {}) or {})
    why_words = dict(getattr(spec, "FORK_WHY", {}) or {})
    marks = dict(getattr(spec, "FORK_MARKS", {}) or {})
    rows: dict[str, dict] = {}                       # правка → строка итога
    sources: dict[str, str] = {}
    books: dict[str, Path] = {}
    bases: dict[str, Path] = {}                      # источник → пробная книга его базы (сверка отпечатка)
    crn = json.loads(Path(a.crn).read_text(encoding="utf-8")) if a.crn else None
    for p in a.legacy or []:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        legacy = {"base0": data["base0"], **data["forks"]}
        for label, r in legacy.items():
            fork = "base" if label == "base0" else _norm_fork(r.get("patches"))
            rows.setdefault(fork, dict(r, label=label))
            sources.setdefault(fork, f"{Path(p).name} ({label})")
            for d in a.legacy_books or []:
                if (Path(d) / f"{label}.after.yaml").exists():
                    books.setdefault(fork, Path(d) / f"{label}.after.yaml")
        for d in a.legacy_books or []:
            if (Path(d) / "base0.after.yaml").exists():
                bases.setdefault(f"{Path(p).name} @ {Path(d).as_posix()}", Path(d) / "base0.after.yaml")
    for p in a.runs or []:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        for label, r in data.items():
            fork = r["fork"]
            if fork in rows and "point" in r and "point" in rows[fork]:
                old = rows[fork]
                if abs(float(old["point"]) - float(r["point"])) > 1e-6 or round(float(old["median"]), 4) != round(float(r["median"]), 4):
                    raise SystemExit(f"forks: правка {fork}: новый прогон ({r['point']}, {r['median']}) не равен прежнему "
                                     f"({old['point']}, {old['median']}) — запись не пишется")
            rows[fork] = dict(r, label=label)
            sources[fork] = f"ops/tools/forks.py @ {r.get('commit')} ({label}, {r.get('date')})"
            if (Path(p).parent / "books" / f"{label}.yaml").exists():
                books[fork] = Path(p).parent / "books" / f"{label}.yaml"
                if fork == "base":
                    bases[f"ops/tools/forks.py @ {r.get('commit')}"] = books[fork]
    for p in a.runs or []:
        crn_p = Path(p).parent / "crn.json"
        if crn_p.exists() and crn is None:
            crn = json.loads(crn_p.read_text(encoding="utf-8"))
    if crn is None and RECORD.exists():
        crn = json.loads(RECORD.read_text(encoding="utf-8")).get("crn")
    if crn is None:
        raise SystemExit("forks: нет блока общих случайных чисел (crn.json рядом с итогом run или запись)")
    base = rows.get("base")
    if base is None or "point" not in base:
        raise SystemExit("forks: нет базы (правка base) — разности не к чему считать")
    # отпечаток: книга дерева против пробной книги базы
    now = book_numbers(book)
    accepted = dict(x.split("=", 1) for x in a.accept or [])
    differences = []
    if not bases:
        raise SystemExit("forks: нет пробной книги базы — отпечаток не с чем сверить")
    fb = _flat(numbers_view(book))
    for src, path in bases.items():
        base_book = load_book(path, facts=facts)
        if book_numbers(base_book) == now:
            continue
        fa = _flat(numbers_view(base_book))
        for k in sorted(set(fa) | set(fb)):
            if fa.get(k, "<нет>") != fb.get(k, "<нет>"):
                if k not in accepted:
                    raise SystemExit(f"forks: книга дерева расходится с книгой прогонов ({src}) числом {k}: {fa.get(k, '<нет>')} → "
                                     f"{fb.get(k, '<нет>')} — запись не пишется (путь, который лист вывода и оценка не читают, — "
                                     "ключом --accept ПУТЬ=ПОЧЕМУ)")
                if not any(x["path"] == k and x["runs"] == fa.get(k) for x in differences):
                    differences.append({"path": k, "runs": fa.get(k), "book": fb.get(k), "why": accepted[k]})

    def row_of(key: str, fork: str) -> dict[str, Any]:
        r = rows.get(fork)
        if r is None:
            return {"fork": fork, "why": None, "missing": True}
        out: dict[str, Any] = {"fork": fork, "source": sources[fork]}
        priced = "point" in r and (r.get("is_price", r.get("status") in ("price", "ok")) is not False) \
            and r.get("status") not in ("no_price", "no_numbers", "без цены", "без цены (справочно)")
        if not priced:
            words = why_words.get(key)
            if not words:
                raise SystemExit(f"forks: у строки {key} ({fork}) нет цены, а слов причины в описании вывода (FORK_WHY) нет")
            out["why"] = words
            return out
        out.update(point=round(float(r["point"]), 6), median=float(r["median"]),
                   d_point=round(float(r["point"]) - float(base["point"]), 4), d_median=round(float(r["median"]) - float(base["median"]), 4),
                   d_worlds={w: round(float(v) - float(base["worlds"][w]), 4) for w, v in r["worlds"].items()})
        mark = selection_words(r.get("roe_bound"), r.get("windows_changed") or {})
        if mark and not any(part in fork.split("+") for part in marks):
            out["mark"] = mark
        for part, words in marks.items():
            if part in fork.split("+"):
                out["median_mark"] = words
        return out

    variants = {}
    for v in book.opt("valuation.reference_variants") or []:
        vid = str(v["id"])
        variants[vid] = row_of(vid, forks.get(vid, f"var:{vid}"))
    rule = {}
    plan = rule_closures(book)
    if plan is not None:
        current, closures = plan
        for key in closures:
            fork = "base" if key == current else rule_forks.get(key, f"rule:{key}")
            r = row_of(key, fork)
            if "point" in r and fork in books:
                g = _grid_of(books[fork])
                if abs(g["point"] - r["point"]) > 1e-6:
                    raise SystemExit(f"forks: замыкание {key}: точка пробной книги {g['point']} на фактах дерева не равна "
                                     f"записанной {r['point']} — запись не пишется")
                r["capital_gap_mass"] = g["capital_gap_mass"]
            elif "point" in r and "capital_gap_mass" in rows.get(fork, {}):
                r["capital_gap_mass"] = rows[fork]["capital_gap_mass"]
            rule[key] = r
    missing = sorted(k for k, r in {**variants, **rule}.items() if r.get("missing"))
    if missing:
        raise SystemExit("forks: нет итога развилки для строк " + ", ".join(missing) + " — сначала run")
    record = {
        "schema": SCHEMA,
        "book": {"version": str(book.get("meta.version")), "numbers": now, "key": RECORD_KEY},
        "how": ("сухой перевывод: вариант — центр шаблона копии дерева, лист вывода перевыводит корни, концы осей и проверки "
                "(ops/tools/rederive.py --dry-run); точка — сетка пробной книги; медиана — малая полоса на общих случайных "
                f"числах ({int(base.get('runs', RUNS) or RUNS)} прогонов); разности — к базе тех же чисел"),
        "base": {"point": round(float(base["point"]), 6), "median": float(base["median"]), "worlds": base["worlds"],
                 "runs": int(base.get("runs", RUNS) or RUNS), "source": sources["base"]},
        "crn": crn,
        "differences": differences,
        "variants": variants,
        "rule_price": rule,
    }
    text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
    priced = sum(1 for r in {**variants, **rule}.values() if "d_point" in r)
    print(f"запись: вариантов {len(variants)}, замыканий {len(rule)}; с ценой {priced}, без цены "
          f"{len(variants) + len(rule) - priced}; отпечаток книги {now[:16]}…; отличий от книги прогонов {len(differences)}")
    if a.write:
        RECORD.write_text(text, encoding="utf-8", newline="\n")
        print(f"записано: {RECORD.relative_to(ROOT).as_posix()}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_check() -> int:
    from model.book import load_book, load_facts
    from model.book_results import reference_record
    book = load_book(facts=load_facts())
    record, why = reference_record(book)
    if record is None or why is not None:
        print(f"запись сухого перевывода: {why or 'книга не называет запись'}")
        return 1
    print(f"запись сухого перевывода — этой книги (отпечаток {record['book']['numbers'][:16]}…)")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--check"]:
        return cmd_check()
    ap = argparse.ArgumentParser(prog="python -B ops/tools/forks.py", description="развилки книги сухим перевыводом")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--commit", default="HEAD")
    r.add_argument("--runs", type=int, default=RUNS)
    r.add_argument("--workers", type=int, default=int(os.environ.get("BANK_WORKERS", "4")))
    r.add_argument("--out", default=str(ROOT / "var" / "forks"))
    r.add_argument("--crn", help="книга базы общих случайных чисел (.json/.yaml) или готовый блок (*.crn.json)")
    r.add_argument("--keep", action="store_true", help="не стирать копию дерева")
    r.add_argument("items", nargs="+")
    c = sub.add_parser("record")
    c.add_argument("--runs", action="append")
    c.add_argument("--legacy", action="append")
    c.add_argument("--legacy-books", action="append")
    c.add_argument("--accept", action="append")
    c.add_argument("--crn", help="блок общих случайных чисел (*.crn.json); нет — crn.json рядом с итогом run или запись")
    c.add_argument("--write", action="store_true")
    n = sub.add_parser("_numbers")
    n.add_argument("--book", required=True)
    n.add_argument("--facts", required=True)
    n.add_argument("--crn", required=True)
    n.add_argument("--runs", type=int, default=RUNS)
    n.add_argument("--workers", type=int, default=4)
    n.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        Path(a.out).mkdir(parents=True, exist_ok=True)
        rc = cmd_run(a)
        return rc
    if a.cmd == "record":
        return cmd_record(a)
    res = _numbers(Path(a.book), Path(a.facts), json.loads(Path(a.crn).read_text(encoding="utf-8")), a.runs, a.workers)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
