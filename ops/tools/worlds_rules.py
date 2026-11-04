# -*- coding: utf-8 -*-
"""Правила книги Совкомбанка для чисел, зависящих от миров ставок, — шаги `rule` манифеста приёма миров
(`data/assumptions/worlds_dependents.yaml`, команда `ops/tools/adopt_worlds.py`).

Правило — функция `f(ctx) -> {"file": шаблон, "values": {адрес: число}, "decimals": {адрес: знаков}}`; `ctx` — контекст
команды (`ctx.root` — корень дерева, `ctx.record` — запись миров дерева, `ctx.overlay` — надстройка банков). Адрес — ключ с
точками или кортеж (элементы списков осей и вариантов книги — номером). Правило считает число из записи миров, фактов и
суждений книги, а не переносит литерал: запись сменили — число сдвинулось; на записи, по которой стоит книга, правило даёт
ровно число шаблона (сторож `tests/test_worlds_dependents.py`, `adopt_worlds.py --check`).

Правила:
  far_spreads      дальние ключи спредов книг активов 2028–2030 и LT (лист калибровки ЧПД этапа 1, nii_block.py:
                   s_y = c_cur + (a − 1) · опора мира H года, LT — опора последнего полугодия сетки; c_cur = c + остаток
                   последних четырёх кварталов совместного подбора); входы a, c, остатки — копия бэктеста
                   `evidence/nii/inputs/.../backtest_joint.json` (опись SOURCES.json);
  cor_paths        пути стоимости риска режимов 2027–LT и концы оси-связки κ: правила класса 6 `class_checks.yaml`
                   (уровень окна + κ · I_R · (rr мира M года − rr окна)) / I окна) на мирах записи плюс остаток записи книги
                   0.1 против правила на записи 1.4 (в допуске правила; `worlds_rules.json`); кварталы 2027 года спада и
                   кризиса — сдвиг года каждому кварталу;
  funds_premium    центр премии роста средств клиентов 2027–2029 (правила класса 6: середина фактов и нужды баланса — варианта
                   funds_premium_need, который пишет вывод на ядре); после него — повтор вывода (цикл манифеста);
  bridge_variants  ключ уровня маржи справочных вариантов «другой уровень мира» точным мостом листа вывода (`key_of`) при мире
                   и ЧПМ опр. банка правки развилки этого варианта (`FORK_PATCHES` описания вывода).

    python -B ops/tools/worlds_rules.py --rests [--record ФАЙЛ --overlay ФАЙЛ]   # остатки CoR на записи книги (разово)
    python -B ops/tools/worlds_rules.py --show                                    # числа правил на дереве
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = "data/assumptions/assumptions_template.yaml"
JOINT = "data/assumptions/evidence/nii/inputs/stage1/calib/nii/backtest/backtest_joint.json"
RESTS = "data/assumptions/worlds_rules.json"
FAR_YEARS = (2028, 2029, 2030)
KAPPA = "credit.kappa"
PREMIUM = tuple(f"volumes.funds_share_drift.{seg}.{y}" for seg in ("retail", "corporate") for y in (2027, 2028, 2029))
NIM_KEY = "nii.nim_lt_target_mgmt"


# ------------------------------------------------------------------ книга в памяти
def _module(root: Path, rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, root / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


def _core(root: Path):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from model.book import book_from_dict, load_facts
    return book_from_dict, load_facts


def template(ctx) -> dict:
    return yaml.safe_load((Path(ctx.root) / TEMPLATE).read_text(encoding="utf-8"))


def machine(ctx) -> dict:
    """Машинная книга в памяти: шаблон дерева + миры записи `ctx.record` + надстройка `ctx.overlay` (правила сборщика
    `build_assumptions.py` — поле записи / 100, полугодия, узел LT); файлов не пишет и хэши не сверяет."""
    root = Path(ctx.root)
    ba = _module(root, "data/assumptions/build_assumptions.py", "_worlds_rules_build")
    raw = template(ctx)
    ids = list(raw["worlds"]["ids"])
    raw["worlds"].update(ba.world_blocks(ctx.record, raw["meta"], ids))
    raw["worlds_bank"] = ba.overlay_blocks(ctx.overlay, ids, raw["meta"])
    raw["worlds"]["overlay"]["sha256"] = hashlib.sha256(json.dumps(ctx.overlay, sort_keys=True).encode()).hexdigest()
    return raw


def book_of(ctx):
    book_from_dict, load_facts = _core(Path(ctx.root))
    facts = load_facts(Path(ctx.root) / "data" / "facts")
    return book_from_dict(machine(ctx), facts=facts), facts


def _halves(meta: dict) -> list[str]:
    y, q = int(meta["first_period"][:4]), int(meta["first_period"][5])
    y1, q1 = int(meta["last_period"][:4]), int(meta["last_period"][5])
    h, h1, out = (1 if q <= 2 else 2), (1 if q1 <= 2 else 2), []
    while (y, h) <= (y1, h1):
        out.append(f"{y}H{h}")
        y, h = (y, 2) if h == 1 else (y + 1, 1)
    return out


# ------------------------------------------------------------------ дальние ключи спредов
def far_spread_values(world: dict, books: dict, joint: dict, last_half: str) -> dict[str, dict[str, float]]:
    """Ключи спредов книг активов 2028–2030 и LT правилом листа калибровки ЧПД (nii_block.py): s_y = c_cur + (a − 1) ·
    середина полугодий года опоры мира H, LT — опора последнего полугодия сетки; c_cur = c + остаток 4 кварталов; 5 знаков."""
    out = {}
    for name, spec in books.items():
        if spec.get("side") != "asset" or name not in joint["joint"]:
            continue
        a = float(joint["joint"][name]["a"])
        c_cur = float(joint["joint"][name]["c"]) + float(joint["resid_last4_joint"][name])
        path = world["key_rate" if spec["ref"] == "key" else spec["ref"]]
        vals = {str(y): round(c_cur + (a - 1) * (path[f"{y}H1"] + path[f"{y}H2"]) / 2, 5) for y in FAR_YEARS}
        vals["LT"] = round(c_cur + (a - 1) * path[last_half], 5)
        out[name] = vals
    return out


def far_spreads(ctx) -> dict:
    raw = machine(ctx)
    joint = json.loads((Path(ctx.root) / JOINT).read_text(encoding="utf-8"))
    world = raw["worlds"][str(raw["nii"]["transmission"]["reference_world"])]
    far = far_spread_values(world, raw["nii"]["books"], joint, _halves(raw["meta"])[-1])
    values = {f"nii.books.{b}.spread.{k}": v for b, vals in far.items() for k, v in vals.items()}
    return {"file": TEMPLATE, "values": values, "decimals": {k: 5 for k in values}}


# ------------------------------------------------------------------ пути CoR режимов и концы оси κ
@lru_cache(maxsize=4)
def _cc(root: str):
    _core(Path(root))
    return _module(Path(root), "ops/tools/class_checks.py", "_worlds_rules_class_checks")


def cor_rules(root: Path) -> list[tuple[dict, list[str]]]:
    """Правила класса 6 путей CoR, читающие миры: (правило, ключи шаблона). Ключ года из среднего кварталов (`book_expr`
    со средним) — сдвиг года каждому кварталу."""
    cc = _cc(str(root))
    out = []
    for r in cc.load_config(cc.CONFIG)["centres"]:
        k = str(r.get("key", ""))
        if not (k.startswith("regimes.") and ".cor." in k and "worlds." in str(r.get("expr", ""))):
            continue
        keys = re.findall(r"B\('([^']+)'\)", r["book_expr"]) if r.get("book_expr") else [k]
        out.append((r, keys))
    return out


def kappa_axis(tpl: dict) -> tuple[int, dict]:
    axes = tpl["valuation"]["uncertainty"]["axes"]
    [(i, ax)] = [(i, a) for i, a in enumerate(axes) if a["paths"][0] == KAPPA]
    return i, ax


def cor_raw(ctx) -> dict[str, dict[str, float]]:
    """Правило класса 6 на мирах записи без остатка: {центр|low|high: {ключ: число}} (κ центра и концов оси κ)."""
    book, facts = book_of(ctx)
    cc = _cc(str(ctx.root))
    _, ax = kappa_axis(template(ctx))
    kappas = {"centre": float(book.get(KAPPA)), "low": float(ax["low"][KAPPA]), "high": float(ax["high"][KAPPA])}
    out = {}
    for end, kappa in kappas.items():
        b = book if end == "centre" else book.with_overrides({KAPPA: kappa})
        out[end] = {}
        for rule, keys in cor_rules(Path(ctx.root)):
            v = float(cc.formula_value(b, facts, rule["expr"], rule["key"]))
            for k in keys:
                out[end][k] = v
    return out


def cor_paths(ctx) -> dict:
    rests = json.loads((Path(ctx.root) / RESTS).read_text(encoding="utf-8"))["cor_rests"]
    raw = cor_raw(ctx)
    i, _ = kappa_axis(template(ctx))
    values, decimals = {}, {}
    for end, vals in raw.items():
        for k, v in vals.items():
            addr = k if end == "centre" else ("valuation", "uncertainty", "axes", i, end, k)
            values[addr] = round(v + float(rests[end][k]), 6) + 0.0
            decimals[addr] = 6
    return {"file": TEMPLATE, "values": values, "decimals": decimals}


def cor_rests(ctx) -> dict:
    """Остатки записи книги против правила на мирах `ctx` (разово, на записи, по которой стоит книга): число шаблона −
    правило. Правило переносит изменение записи миров, а округления листов круга остаются как были."""
    raw = cor_raw(ctx)
    tpl = template(ctx)
    _, ax = kappa_axis(tpl)
    have = {"centre": lambda k: _get(tpl, k), "low": lambda k: ax["low"][k], "high": lambda k: ax["high"][k]}
    return {end: {k: float(have[end](k)) - v for k, v in vals.items()} for end, vals in raw.items()}


def _get(d: dict, dotted: str):
    node = d
    for part in dotted.split("."):
        node = node[next((k for k in node if str(k) == part), part)]
    return node


# ------------------------------------------------------------------ премия роста средств клиентов
def funds_premium(ctx) -> dict:
    book, facts = book_of(ctx)
    cc = _cc(str(ctx.root))
    rules = {str(r.get("key")): r for r in cc.load_config(cc.CONFIG)["centres"]}
    values = {k: round(float(cc.formula_value(book, facts, rules[k]["expr"], k)), 4) + 0.0 for k in PREMIUM}
    return {"file": TEMPLATE, "values": values, "decimals": {k: 4 for k in values}}


# ------------------------------------------------------------------ мост справочных вариантов уровня маржи
def _patch_numbers(spec, fork: str, sheet) -> dict:
    """ЧПМ опр. банка, мир уровня и передача правки развилки (тексты `FORK_PATCHES`); нет правки — суждения листа."""
    got = {"bank": None, "world": sheet.LEVEL_WORLD_EXPECTED, "transmission": None}
    for part in fork.split("+"):
        for _, _, new in (spec.FORK_PATCHES.get(part) or {}).get("text", []):
            if m := re.match(r"NIM_BANK_N = ([0-9.]+) ", new):
                got["bank"] = float(m.group(1))
            if m := re.match(r'LEVEL_WORLD_EXPECTED = "(\w)" ', new):
                got["world"] = m.group(1)
            if m := re.match(r"TRANSMISSION_BANK = (-?[0-9.]+) ", new):
                got["transmission"] = float(m.group(1))
    return got


def bridge_variants(ctx) -> dict:
    root = Path(ctx.root)
    path_dir = root / "data" / "assumptions" / "evidence" / "path"
    _core(root)
    if str(path_dir) not in sys.path:
        sys.path.insert(0, str(path_dir))
    sheet = _module(root, "data/assumptions/evidence/path/derive_on_engine.py", "derive_on_engine")
    spec = _module(root, "data/assumptions/evidence/path/derive_spec.py", "_worlds_rules_derive_spec")
    from model.credit import bridge_from_facts
    book, facts = book_of(ctx)
    t = sheet.bank_terms(SimpleNamespace(facts=facts, bridge=bridge_from_facts(facts)), book)
    values = {}
    for i, v in enumerate(template(ctx)["valuation"]["reference_variants"]):
        fork = spec.FORKS.get(v["id"])
        ov = v.get("overrides") or {}
        if not fork or NIM_KEY not in ov:
            continue
        p = _patch_numbers(spec, fork, sheet)
        if p["bank"] is None:                 # правка не меняет уровень опр. банка (мост буквально и т. п.) — не мост мира
            continue
        values[("valuation", "reference_variants", i, "overrides", NIM_KEY)] = round(sheet.key_of(t, p["bank"], p["world"]), 6) + 0.0
        if p["transmission"] is not None and "nii.transmission.target" in ov:
            values[("valuation", "reference_variants", i, "overrides", "nii.transmission.target")] = \
                round(sheet.target_of(t, p["transmission"]), 6) + 0.0
    return {"file": TEMPLATE, "values": values, "decimals": {k: 6 for k in values}}


RULES = {"far_spreads": far_spreads, "cor_paths": cor_paths, "funds_premium": funds_premium, "bridge_variants": bridge_variants}


# ------------------------------------------------------------------ вход
def tree_ctx(root: Path = ROOT, record: Path | None = None, overlay: Path | None = None):
    rec = record or root / "data" / "assumptions" / "worlds_source.json"
    ov = overlay or root / "data" / "assumptions" / "worlds_bank.json"
    return SimpleNamespace(root=root, record=json.loads(rec.read_bytes().decode("utf-8")),
                           overlay=json.loads(ov.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rests", action="store_true", help="записать остатки путей CoR (worlds_rules.json) на записи дерева")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--record", type=Path)
    ap.add_argument("--overlay", type=Path)
    a = ap.parse_args(argv)
    ctx = tree_ctx(ROOT, a.record, a.overlay)
    if a.rests:
        st = json.loads((ROOT / "data" / "assumptions" / "worlds_state.json").read_text(encoding="utf-8"))
        tpl = template(ctx)
        doc = {"schema": "svcb-worlds-rules-v1",
               "cor_rests": {"from": {"book": str(tpl["meta"]["version"]), "worlds": str(st["version"]),
                                      "record_sha256": st["record_sha256"]},
                             "why": ("остаток записи пути CoR книги против правила класса 6 на записи миров книги (в допуске "
                                     "правила; округления листов круга): правило переносит изменение записи миров на число "
                                     "книги, не переписывая его формулой; при перезаякоривании пути пишутся заново и остатки "
                                     "пересчитываются этой командой"),
                             **cor_rests(ctx)}}
        (ROOT / RESTS).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"записано: {RESTS}")
        return 0
    for name, fn in RULES.items():
        res = fn(ctx)
        print(f"{name}: {len(res['values'])} чисел")
        for k, v in res["values"].items():
            print(f"  {'.'.join(map(str, k)) if isinstance(k, tuple) else k} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
