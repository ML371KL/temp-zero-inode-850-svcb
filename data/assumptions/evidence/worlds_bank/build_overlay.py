# -*- coding: utf-8 -*-
"""Банковская надстройка миров: лист надстройки этапа 1 → data/assumptions/worlds_bank.json (формат — MODEL прил. B).

Рост сектора у банков семейства один, поэтому файл обязан совпасть с надстройкой книги Сбербанка бит в бит
(sha256 6fb82a41…): лист этапа 1 несёт готовые пути по мирам (блок `sector.worlds`), скрипт их не пересчитывает, а
проверяет и переписывает в формат ядра:
  * мир N — середины диапазонов базового сценария ОНДКП 2027–2029 (блок `sector.cbr_ondkp_baseline`: организации,
    ИЖК, М2), «прочая розница» 2026–2027 — середины прогноза ЦБ по балансам (`sector.cbr_bank_review_forecast`),
    2028–2029 — (население − w·ИЖК)/(1 − w), w = 0,5806 (доля ИЖК в задолженности физлиц на 01.08.2026);
  * миры H и M — реальный рост базы при инфляции своего мира: g_W = (1 + g_N)·(1 + π_W)/(1 + π_N) − 1, π — средний
    ИПЦ мира за год по записи миров семейства; год якоря одинаков во всех мирах;
  * funds_growth.retail = funds_growth.corporate = М2 (раздельных рядов средств физлиц и бизнеса у ЦБ нет);
  * годы — от года якоря до последнего года прогноза ОНДКП (2026–2029); дальше ядро сводит рост объёмов к g_T мира
    к volumes.lt_from (MODEL §4.3).
Премии роста Т к сектору в надстройку не входят — они ключи книги (`volumes.loan_share_drift`, `funds_share_drift`);
их история (блоки `t_premium`, `funds` листа) — справка для текста книги.

Вход — копия листа этапа 1 `inputs/bank_overlay_draft.yaml` (имена локальных папок заменены относительными путями,
остальное — как в листе); первичка — ссылкой и sha256 в самом листе (meta.sources).
Запуск из корня репозитория:
  python data/assumptions/evidence/worlds_bank/build_overlay.py            # пишет worlds_bank.json
  python data/assumptions/evidence/worlds_bank/build_overlay.py --check    # сверка с файлом (выход 1 — расхождение)
  python data/assumptions/evidence/worlds_bank/build_overlay.py --sync     # обновить копию листа из $BANK_HANDOFF_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BOOK_DIR = HERE.parents[1]                       # data/assumptions
DRAFT = HERE / "inputs" / "bank_overlay_draft.yaml"
RECORD = BOOK_DIR / "worlds_source.json"
OUT = BOOK_DIR / "worlds_bank.json"
HANDOFF_DRAFT = ("stage1", "worlds", "bank_overlay_draft.yaml")   # относительно $BANK_HANDOFF_DIR

WORLDS = ("N", "H", "M")
GROUPS = (("credit_growth", ("corporate", "mortgage", "retail_other")), ("funds_growth", ("retail", "corporate")))
AS_OF = "2026-09-30"                             # титул ОНДКП: «Проект от 30 сентября 2026 года»
MORTGAGE_WEIGHT = 0.5806                         # доля ИЖК в задолженности физлиц на 01.08.2026 (dataservice ЦБ; лист этапа 1)
FAMILY_SHA256 = "6fb82a41c4aa558c1f9a11323c7602ea0feb82e09d7430e85d4ea696ed03037a"   # надстройка семейства (книга Сбербанка)
TOL = 6e-4                                       # сверка пути мира с пересчётом: округление середин до 0,01 п.п.

RECIPE = (
    "N — середины диапазонов базового сценария ОНДКП 2027–2029 (табл. 3.2, PDF-с. 73 / печ. 71), кроме «прочей "
    "розницы» 2026–2027 — прогноз ЦБ по балансам («Банковский сектор. II кв. 2026», PDF-с. 20 / печ. 19, sha256 "
    "ed4826f8…) и 2028–2029 — [Р] (население − w·ИЖК)/(1 − w), w = 0,5806 (доля ИЖК в задолженности ФЛ на "
    "01.08.2026, dataservice ЦБ). H и M — реальный рост базы при инфляции своего мира: g_W = (1 + g_N)·(1 + π_W)/"
    "(1 + π_N) − 1, π — средний ИПЦ мира за год по записи миров семейства (worlds_source.json, sha256 7296567d…); "
    "2026 — одинаково во всех мирах. credit_growth.corporate — «организации», mortgage — ИЖК, retail_other — "
    "«прочая розница»; funds_growth.retail = funds_growth.corporate = М2 (раздельных рядов нет); "
    "nominal_gdp_growth — справочно. Середины диапазонов → доли. Годы 2026–2029; после 2029 ядро сводит рост "
    "объёмов к g_T мира к volumes.lt_from (MODEL §4.3). Сборщик — "
    "data/assumptions/evidence/worlds_bank/build_overlay.py; вход — черновик надстройки этапа 1 "
    "(evidence/worlds_bank/inputs/bank_overlay_draft.yaml)."
)

# Имена локальных папок листа этапа 1 → относительные пути (публичный репозиторий). Имён папок здесь нет — только
# их вид: рабочая копия — каталог прямо перед «data/assumptions/», папка передачи кончается на «-handoff». Рецепт
# надстройки лист называет в рабочей копии книги-образца — ссылка получает пометку, чья это книга.
_NAME = r"[\w.-]+"
_START = r"(?<![\w./-])"                         # начало пути: перед именем нет ни имени, ни разделителя
_REPLACE = (
    (re.compile(_START + _NAME + "/(data/assumptions/evidence/worlds_bank/)"), r"\1 (как в книге Сбербанка)"),
    (re.compile(_START + _NAME + "/(data/assumptions/)"), r"\1"),
    (re.compile(_START + "(?:" + _NAME + "/)*" + _NAME + "-handoff/(primary/)"), r"\1"),
)


def sanitize(text: str) -> str:
    """Лист этапа 1 → копия для репозитория: только замена имён локальных папок относительными путями."""
    for pattern, new in _REPLACE:
        text = pattern.sub(new, text)
    return text


def split_head(text: str) -> tuple[str, str]:
    """Начальный блок комментариев листа и тело: шапка копии — этой книги (лист семейства несёт шапку книги-образца),
    сверяется и обновляется только тело."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("#"):
        i += 1
    return "\n".join(lines[:i]), "\n".join(lines[i:])


def _mid(rng) -> float:
    """[низ, верх] в % → середина в долях."""
    return (float(rng[0]) + float(rng[1])) / 2 / 100.0


def world_cpi(record: dict) -> dict:
    """Средний ИПЦ мира за год, % — среднее двух полугодий cpi_yoy_avg записи."""
    out = {}
    for w in WORLDS:
        rows = {r["period"]: r["cpi_yoy_avg"] for r in record["rows"] if r["world"] == w}
        years = sorted({int(p[:4]) for p in rows})
        out[w] = {y: round((rows[f"{y}H1"] + rows[f"{y}H2"]) / 2, 3) for y in years if f"{y}H1" in rows}
    return out


def verify_draft(draft: dict, record_bytes: bytes) -> list[str]:
    """Самопроверка листа: запись миров та же; мир N — середины первички; H и M — пересчёт N по инфляции мира."""
    bad = []
    sha = hashlib.sha256(record_bytes).hexdigest()
    if draft["meta"]["worlds_record"]["sha256"] != sha:
        bad.append(f"лист собран на другой записи миров: {draft['meta']['worlds_record']['sha256']} ≠ {sha}")
    sec = draft["sector"]
    worlds = sec["worlds"]
    n = worlds["N"]
    base, review = sec["cbr_ondkp_baseline"], sec["cbr_bank_review_forecast"]
    years = sorted(int(y) for y in n["credit_growth"]["corporate"])
    for y in years:
        checks = [("corporate", n["credit_growth"]["corporate"], _mid(base["organizations"][y])),
                  ("mortgage", n["credit_growth"]["mortgage"], _mid(base["mortgage"][y])),
                  ("funds", n["funds_growth"]["retail"], _mid(base["m2"][y]))]
        rng = review["other_retail"].get(y)
        if rng:
            checks.append(("retail_other", n["credit_growth"]["retail_other"], _mid(rng)))
        else:                                    # ряда «прочая розница» в ОНДКП нет: население без ИЖК
            hh, mort = _mid(base["households"][y]), _mid(base["mortgage"][y])
            checks.append(("retail_other", n["credit_growth"]["retail_other"],
                           (hh - MORTGAGE_WEIGHT * mort) / (1 - MORTGAGE_WEIGHT)))
        for name, path, exp in checks:
            if abs(float(path[str(y)]) - exp) > TOL:
                bad.append(f"N {y} {name}: {path[str(y)]} против первички {exp:.5f}")
    cpi = world_cpi(json.loads(record_bytes.decode("utf-8")))
    for w in ("H", "M"):
        for y in years:
            f = 1.0 if y == years[0] else (1 + cpi[w][y] / 100) / (1 + cpi["N"][y] / 100)
            pairs = [(f"{g}.{k}", worlds[w][g][k], n[g][k]) for g, keys in GROUPS for k in keys]
            pairs.append(("nominal_gdp_growth", worlds[w]["nominal_gdp_growth"], n["nominal_gdp_growth"]))
            for name, path, path_n in pairs:
                exp = (1 + float(path_n[str(y)])) * f - 1
                if abs(float(path[str(y)]) - exp) > TOL:
                    bad.append(f"{w} {y} {name}: {path[str(y)]} против пересчёта {exp:.5f}")
    for w in WORLDS:
        if worlds[w]["funds_growth"]["retail"] != worlds[w]["funds_growth"]["corporate"]:
            bad.append(f"{w}: funds_growth.retail ≠ funds_growth.corporate (оба — М2)")
    return bad


def build_overlay(draft: dict, record_bytes: bytes) -> dict:
    """Объект worlds_bank.json из листа надстройки."""
    bad = verify_draft(draft, record_bytes)
    if bad:
        raise ValueError("лист надстройки не проходит самопроверку:\n  " + "\n  ".join(bad))
    src = draft["meta"]["sources"]["ondkp"]
    worlds = {}
    for w in WORLDS:
        blk = draft["sector"]["worlds"][w]
        out: dict = {}
        for grp, keys in GROUPS:
            out[grp] = {k: {str(y): float(v) for y, v in sorted(blk[grp][k].items(), key=lambda kv: int(kv[0]))}
                        for k in keys}
        out["nominal_gdp_growth"] = {str(y): float(v) for y, v in
                                     sorted(blk["nominal_gdp_growth"].items(), key=lambda kv: int(kv[0]))}
        worlds[w] = out
    return {
        "schema": "worlds_bank-v1",
        "source": {"doc": src["file"], "url": src["url"], "sha256": src["sha256"], "as_of": AS_OF},
        "recipe": RECIPE,
        "worlds": worlds,
    }


def render(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def load_draft(path: Path = DRAFT) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_text() -> str:
    return render(build_overlay(load_draft(), RECORD.read_bytes()))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="сверить worlds_bank.json со сборкой")
    ap.add_argument("--sync", action="store_true", help="обновить копию листа из $BANK_HANDOFF_DIR")
    a = ap.parse_args(argv)
    if a.sync:
        root = os.environ.get("BANK_HANDOFF_DIR")
        if not root:
            print("нет BANK_HANDOFF_DIR — копию листа обновить не из чего")
            return 1
        text = Path(root, *HANDOFF_DRAFT).read_text(encoding="utf-8")
        DRAFT.parent.mkdir(parents=True, exist_ok=True)
        head = split_head(DRAFT.read_text(encoding="utf-8"))[0] if DRAFT.exists() else ""
        body = split_head(sanitize(text))[1]          # шапка копии — своя, тело — листа семейства
        DRAFT.write_text((head + "\n" if head else "") + body, encoding="utf-8", newline="\n")
        print("копия листа обновлена:", DRAFT.relative_to(BOOK_DIR).as_posix())
    text = build_text()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if sha != FAMILY_SHA256:
        print("ВНИМАНИЕ: надстройка отличается от надстройки семейства (sha256", sha[:8] + "…): сектор у банков один —",
              "расхождение объяснить в книге")
    if a.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("worlds_bank.json", "воспроизводится" if ok else "НЕ воспроизводится сборкой")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("записано:", OUT.relative_to(BOOK_DIR).as_posix(), "sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
