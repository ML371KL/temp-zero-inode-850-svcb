"""История рядов для плиток, ретро-проверки и нау-каста: `data/indicators/seed/*.json` из листов этапа 1.

`python -m indicators.seed [--check] [--only имя,…] [--skip имя,…]` читает листы этапа 1 из
`$BANK_HANDOFF_DIR` (в CI и на сервере не задаётся: файлы истории закоммичены) и пишет:

* `monthly_release.json` — месячный релиз эмитента по месяцам (`stage1/ras/ops_release_monthly_wide.csv`):
  метрики `sources.yaml → monthly.metrics`, с месяца, с которого у главной метрики один периметр;
  день релиза и момент публикации;
* `ifrs_quarters.json` — прибыль квартала в определении книги, цель `ni_q` (`stage1/mgmt/mgmt_kpi.csv`:
  напечатанное значение, а где его нет — точное), и день выхода отчёта
  (`stage1/ras/door_results_classified.csv`: пресс-релиз МСФО; отметка позже даты, напечатанной в самом
  релизе, — перезаливка: тогда день — дата релиза по листу `stage1/mgmt/guidance.csv`);
* `mgmt_quarters.json` — ЧПМ и CoR квартала, упр. базис (`stage1/mgmt/mgmt_kpi.csv`);
* `consensus.json` — консенсус прибыли квартала (вносится оператором: `record-consensus`);
* `form102.json` — форма 0409102 банка нарастающим: прибыль, прибыль до налога, ЧПД с корректировками,
  резервы нетто, расходы (`stage1/ras/cbr_f102_summary.csv`);
* `form135.json`, `form123.json` — нормативы Н1.x и капитал банка (`cbr_f135_wide.csv`, `cbr_f123_wide.csv`);
* `group_forms.json` — формы банковской группы 0409805 и 0409803 по кварталам (`group_f805.csv`,
  `group_f803.csv`);
* `form101.json` — процентные активы банка на конец месяца по форме 0409101 (`stage1/ras/raw/101/*.xml`)
  по определению фактов (`data/facts/bridge_ras_ifrs.json → iea.codes`); без определения файл не строится,
  а построенный под другое определение в ряды не идёт (`form101_fits`).

**Раскладка `soap`** (`sources.yaml → seed.layout: soap`; эмитент без месячного релиза и без листов этапа 1 в
форме образца): формы ЦБ банка и группы — сохранённые ответы SOAP самой службы (`seed.forms`: папки передачи с
файлами `f<форма>_reg<регномер>_<дата>.xml` и `f805_reg<регномер>_<ГГГГММ>_par<1|4>.xml`), разобранные тем же кодом,
что у сборщиков (`cbr_forms`, `cbr_group`: определение ЧПД — настройкой); прибыль квартала цели `ni_q` — узел фактов
`pnl_quarterly.<квартал>.<seed.profit_node>`, ЧПМ и стоимость риска — `mgmt_quarterly` (напечатанное, а где его нет —
точное); дни отчётов — лист календаря эмитента (`seed.release_calendar`: строки `ifrs_quarter` и `ifrs_fy` со статусом
`fact`). Месячного релиза нет — `monthly_release` пуст; процентных активов в фактах нет — `form101` пуст.

Сырых ответов брокера в истории нет. `--check` — пересборка совпадает с файлами (выход 1 при расхождении).
`import_to_store` кладёт историю в ряды хранилища с моментом, когда число стало известно (день релиза,
отчёта или верхняя оценка дня выкладки формы), — чтобы «что было известно на дату» было честным и
для истории.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from indicators import cbr_forms, config, journal, nowcast, periods, release_watch
from indicators.store import Point, Store

SEED_FILES = ("monthly_release", "ifrs_quarters", "mgmt_quarters", "consensus", "form102", "form135", "form123",
              "group_forms", "form101")
# Колонка листа месячного релиза → метрика ряда.
MONTHLY_COLUMNS = {"clients_total": "clients_total_mn", "clients_active": "clients_active_mn",
                   "loans_gross": "loans_gross_bn", "loans_retail": "loans_retail_bn",
                   "loans_business": "loans_business_bn", "funds_total": "customer_funds_bn",
                   "funds_retail": "funds_retail_bn", "funds_business": "funds_business_bn",
                   "np_ytd": "ras_profit_ytd_bn", "cap_base": "capital_cet1_bn", "cap_main": "capital_tier1_bn",
                   "cap_total": "capital_total_bn", "n1_0": "n1_0_pct", "n1_1": "n1_1_pct", "n1_2": "n1_2_pct"}
F102_COLUMNS = {"ni_ytd": "ni_ytd_bn", "pretax_ytd": "pretax_ytd_bn", "nii_ytd": "nii_adj_ytd_bn",
                "prov_ytd": "provisions_net_ytd_bn", "opex_ytd": "opex_admin_ytd_bn"}
F135_COLUMNS = {"n1_0": "n1_0_pct", "n1_1": "n1_1_pct", "n1_2": "n1_2_pct"}
F123_COLUMNS = {"capital_total": "capital_total_th", "capital_base": "cet1_th", "capital_additional": "at1_th",
                "capital_tier2": "tier2_th"}
F805_COLUMNS = {"n20_0": "n20_0_pct", "n20_1": "n20_1_pct", "n20_2": "n20_2_pct",
                "capital_total": "capital_total_th", "capital_base": "cet1_th"}
F803_COLUMNS = {"ni_ytd": "net_profit_ytd_th", "nii_ytd": "nii_ytd_th"}
PROFIT_METRIC, NIM_METRIC, COR_METRIC, EXACT = "op_np", "nim", "cor_total", "_exact"
KEEP_FORM_MONTHS = 36         # форм банка в истории: хватает на профиль «год назад» и ретро
KEEP_GROUP_QUARTERS = 13      # кварталов форм группы
FORM_KNOWN_DAYS = 25          # верхняя оценка дня выкладки формы банка: 26-е число месяца формы
GROUP_KNOWN_DAYS = 75         # верхняя оценка дня выкладки формы группы после конца квартала
REPORT_MAX_DAYS = 120         # отметка двери позже — переписана при перезаливке, днём отчёта не служит
PRESS_DOC = re.compile(r"primary/(\d{4}Q[1-4])_ifrs_press\.pdf")   # пресс-релиз МСФО квартала в листах этапа 1
DOOR_STAMP, PRINTED_DATE = "отметка публикации пресс-релиза МСФО", "дата пресс-релиза МСФО"
# Момент известности — 10:00 МСК дня релиза или отчёта (07:00 UTC).
KNOWN_AT_UTC = "T07:00:00+00:00"


def handoff() -> Path:
    value = os.environ.get(config.HANDOFF_ENV)
    if not value:
        raise SystemExit(f"нужна переменная {config.HANDOFF_ENV} (папка передачи с листами этапа 1)")
    return Path(value)


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _num(x: str | None) -> float | None:
    x = (x or "").strip()
    return float(x) if x else None


def _share(x: str | None) -> float | None:
    v = _num(x)
    return None if v is None else round(v / 100.0, 10)


def _bn(x: str | None) -> float | None:
    v = _num(x)
    return None if v is None else round(v * cbr_forms.THOUSAND_TO_BN, 6)


def build_monthly(root: Path) -> dict[str, Any]:
    spec = release_watch.monthly(config.sources())
    months: dict[str, Any] = {}
    for r in _rows(root / "stage1/ras/ops_release_monthly_wide.csv"):
        if _num(r.get(MONTHLY_COLUMNS.get(spec.main, ""))) is None:
            continue                    # главной метрики нет: месяц другого периметра в ряд не идёт
        m = periods.from_stage1_month(r["month"])
        release = r.get("release_date") or None
        stamp = (r.get("published_at_door_utc") or "")[:19]
        near = bool(stamp and release and abs((date.fromisoformat(stamp[:10]) - date.fromisoformat(release)).days) <= 3)
        values = {}
        for metric in spec.metrics:
            column = MONTHLY_COLUMNS.get(metric)
            v = _share(r.get(column)) if metric in release_watch.SHARE_METRICS else _num(r.get(column))
            if v is not None:
                values[metric] = {"v": v, "src": f"месячный релиз эмитента за {r['month']}, sha256 {r['sha256'][:12]}"}
        months[m] = {"release_date": release, "published_at": f"{stamp}+00:00" if near else None, "values": values}
    return {"basis": "mgmt", "prefix": spec.prefix,
            "units": {"money": "RUB bn", "percent": "доли", "clients": "млн"},
            "note": ("остатки — по внутренней методике эмитента; прибыль — банка по РСБУ с начала года; капитал и "
                     "нормативы — банка"),
            "source": "stage1/ras/ops_release_monthly_wide.csv (разбор PDF месячных релизов, этап 1)",
            "months": dict(sorted(months.items()))}


def _printed_dates(root: Path) -> dict[str, str]:
    """Квартал → дата, напечатанная в пресс-релизе МСФО квартала: день события у строк листа гайденса, чей
    документ — этот пресс-релиз."""
    out: dict[str, str] = {}
    path = root / "stage1/mgmt/guidance.csv"
    if not path.exists():
        return out
    for r in _rows(path):
        m = PRESS_DOC.fullmatch(r.get("doc") or "")
        day = (r.get("as_of") or "")[:10]
        if m and day:
            out[m.group(1)] = min(out.get(m.group(1), day), day)
    return out


def _report_dates(root: Path) -> dict[str, tuple[str, str]]:
    """Квартал → (день выхода пресс-релиза МСФО, откуда он): отметка двери (переписанные отметки отброшены), а
    если отметка позже даты, напечатанной в релизе, — эта дата (папку перезалили на следующий день). Квартал
    без отметки двери дня не получает."""
    out: dict[str, str] = {}
    path = root / "stage1/ras/door_results_classified.csv"
    if not path.exists():
        return {}
    for r in _rows(path):
        if r.get("kind") != "ifrs_results" or r.get("doc") != "press" or not periods.is_quarter(r.get("period") or ""):
            continue
        day = (r.get("published_msk") or "")[:10]
        if day and 0 < (date.fromisoformat(day) - periods.quarter_end(r["period"])).days <= REPORT_MAX_DAYS:
            out[r["period"]] = min(out.get(r["period"], day), day)
    printed = _printed_dates(root)
    return {q: (printed[q], PRINTED_DATE) if periods.quarter_end(q).isoformat() < printed.get(q, day) < day
            else (day, DOOR_STAMP) for q, day in out.items()}


def _kpi(root: Path, metric: str, convert: Callable[[str], float | None]) -> dict[str, dict[str, Any]]:
    """Квартальные значения метрики листа упр. метрик: напечатанное, а где его нет — точное."""
    printed: dict[str, dict[str, Any]] = {}
    exact: dict[str, dict[str, Any]] = {}
    for r in _rows(root / "stage1/mgmt/mgmt_kpi.csv"):
        if r["metric"] not in (metric, metric + EXACT) or not periods.is_quarter(r["period"]):
            continue
        v = convert(r["value"])
        if v is None:
            continue
        where = ("справочник аналитика эмитента" if r["metric"] != metric
                 else "презентация МСФО" if "presentation" in r["doc"] else "пресс-релиз МСФО")
        place = f"с. {r['page']}" if r["page"].isdigit() else r["page"]
        node = {"v": v, "src": f"{where}, {place}, sha256 {r['sha256'][:12]}"}
        (printed if r["metric"] == metric else exact)[r["period"]] = node
    return {q: printed.get(q) or exact[q] for q in sorted(set(printed) | set(exact))}


def build_ifrs(root: Path) -> dict[str, Any]:
    dates = _report_dates(root)
    quarters = {q: {"value": node, "report_date": dict(zip(("v", "src"), dates.get(q, (None, "не найдена"))))}
                for q, node in _kpi(root, PROFIT_METRIC, _num).items()}
    return {"unit": "RUB bn", "target": "ni_q",
            "source": "stage1/mgmt/mgmt_kpi.csv (прибыль квартала в определении книги); дни отчётов — "
                      "stage1/ras/door_results_classified.csv, дата релиза — stage1/mgmt/guidance.csv",
            "quarters": quarters}


def build_mgmt(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, metric in (("nim", NIM_METRIC), ("cor", COR_METRIC)):
        for q, node in _kpi(root, metric, _share).items():
            out.setdefault(q, {})[key] = node
    return {"basis": "mgmt", "unit": "share", "source": "stage1/mgmt/mgmt_kpi.csv (ЧПМ и стоимость риска квартала)",
            "quarters": dict(sorted(out.items()))}


def build_consensus(root: Path) -> dict[str, Any]:
    return {"unit": "RUB bn", "target": "ni_q",
            "source": "истории консенсуса нет: вносится оператором перед отчётом (record-consensus)", "quarters": {}}


def _last(rows: list[dict[str, str]], n: int, key: str = "form_date") -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: r[key])[-n:]


def build_form102(root: Path) -> dict[str, Any]:
    digests = {r["form_date"]: r["sha256"] for r in _rows(root / "stage1/ras/cbr_f102_monthly.csv")}
    out: dict[str, Any] = {}
    for r in _last(_rows(root / "stage1/ras/cbr_f102_summary.csv"), KEEP_FORM_MONTHS):
        entry = {"form_date": r["form_date"], "sha256": digests.get(r["form_date"], "")}
        for key, column in F102_COLUMNS.items():
            v = _num(r.get(column))
            if v is not None:
                entry[key] = round(v, 6)
        if len(entry) > 2:
            out[periods.form_month(r["form_date"])] = entry
    return {"basis": "ras", "unit": "RUB bn", "source": "stage1/ras/cbr_f102_summary.csv (ЦБ SOAP Data102FXML)",
            "note": "дата формы — на 1-е число месяца после месяца данных; момент первой выкладки до запуска "
                    "сборщика неизвестен; резервы и расходы — плюс значит расход",
            "months": dict(sorted(out.items()))}


def _form_wide(root: Path, name: str, columns: dict[str, str], convert: Callable, unit: str, title: str) -> dict:
    out: dict[str, Any] = {}
    for r in _last(_rows(root / f"stage1/ras/{name}"), KEEP_FORM_MONTHS):
        entry = {"form_date": r["form_date"], "sha256": r.get("sha256", "")}
        for key, column in columns.items():
            v = convert(r.get(column))
            if v is not None:
                entry[key] = v
        if len(entry) > 2:
            out[periods.form_month(r["form_date"])] = entry
    return {"basis": "ras", "unit": unit, "source": f"stage1/ras/{name} ({title})",
            "note": "дата формы — на 1-е число месяца после месяца данных; момент первой выкладки до запуска "
                    "сборщика неизвестен", "months": dict(sorted(out.items()))}


def build_form135(root: Path) -> dict[str, Any]:
    return _form_wide(root, "cbr_f135_wide.csv", F135_COLUMNS, _share, "share", "ЦБ SOAP Data135FormFullXML")


def build_form123(root: Path) -> dict[str, Any]:
    return _form_wide(root, "cbr_f123_wide.csv", F123_COLUMNS, _bn, "RUB bn", "ЦБ SOAP Data123FormFullXML")


def build_group(root: Path) -> dict[str, Any]:
    quarters: dict[str, Any] = {}
    for form, name, columns in (("f805", "group_f805.csv", F805_COLUMNS), ("f803", "group_f803.csv", F803_COLUMNS)):
        for r in _last(_rows(root / f"stage1/ras/{name}"), KEEP_GROUP_QUARTERS, key="period_end"):
            q = periods.quarter_of(date.fromisoformat(r["period_end"]))
            values = {}
            for key, column in columns.items():
                v = _share(r.get(column)) if column.endswith("_pct") else _bn(r.get(column))
                if v is not None:
                    values[key] = v
            if values:
                entry = quarters.setdefault(q, {"period_end": r["period_end"]})
                entry[form] = {**values, "sha256": r.get("sha256", "")[:16]}
    return {"basis": "банковская группа по ЦБ", "units": {"money": "RUB bn", "percent": "доли"},
            "source": "stage1/ras/group_f805.csv, group_f803.csv (страницы форм группы на сайте ЦБ; числа совпадают "
                      "с ответами SOAP)",
            "note": "день первого появления формы до запуска сборщика неизвестен",
            "quarters": dict(sorted(quarters.items()))}


def build_form101(root: Path) -> dict[str, Any] | None:
    definition = (config.bridge_ras_ifrs() or {}).get("iea")
    if not isinstance(definition, dict) or not definition.get("codes"):
        return None
    months: dict[str, Any] = {}
    for path in sorted((root / "stage1/ras/raw/101").glob("*.xml")):
        body = path.read_bytes()
        iea = cbr_forms.f101_derived(cbr_forms.parse_f101(body), iea=definition).get("iea")
        if iea is None:
            continue
        months[periods.form_month(path.stem)] = {"form_date": path.stem,
                                                  "sha256": hashlib.sha256(body).hexdigest()[:16],
                                                  "iea": round(iea, 6)}
    values = {m: e["iea"] for m, e in months.items()}
    quarters = {}
    for q in sorted({periods.quarter_of_month(m) for m in months}):
        avg = nowcast.iea_quarter_mean(values, q)
        if avg is not None:
            quarters[q] = {"iea_avg": round(avg, 6), "months": nowcast.iea_months(q)}
    return {"basis": "ras", "unit": "RUB bn",
            "definition": ("процентные активы банка по форме 0409101 — коды фактов "
                           "(data/facts/bridge_ras_ifrs.json → iea.codes, codes_required); среднее квартала — "
                           "(конец прошлого квартала + конец квартала) / 2"),
            "codes": definition.get("codes"), "codes_required": definition.get("codes_required"),
            "source": "stage1/ras/raw/101/*.xml (ЦБ SOAP Data101FNewXML)",
            "note": "дата формы — на 1-е число месяца после месяца данных; момент первой выкладки до запуска "
                    "сборщика неизвестен", "months": dict(sorted(months.items())), "quarters": quarters}


# ------------------------------------------------------------------ раскладка `soap`: ответы службы ЦБ и факты

SOAP_FORM = re.compile(r"^f(?P<form>\d{3})_reg(?P<reg>\d+)_(?P<day>\d{4}-\d{2}-\d{2})\.xml$")
GROUP_FORM = re.compile(r"^f805_reg(?P<reg>\d+)_(?P<dt>\d{6})_par(?P<par>[14])\.xml$")
FORM_NOTE = "дата формы — на 1-е число месяца после месяца данных; момент первой выкладки до запуска сборщика неизвестен"


def _soap_dirs(root: Path) -> list[Path]:
    return [root / str(d) for d in config.setting("seed.forms") or []]


def _soap_bank(root: Path, form: str) -> dict[str, Path]:
    """Дата формы → файл ответа службы (первая папка с этой датой)."""
    regnum = str(config.company()["cbr_regnum"])
    out: dict[str, Path] = {}
    for d in _soap_dirs(root):
        for path in sorted(d.glob(f"f{form}_reg{regnum}_*.xml")):
            m = SOAP_FORM.match(path.name)
            if m and m.group("form") == form:
                out.setdefault(m.group("day"), path)
    return dict(sorted(out.items()))


def build_soap_form(root: Path, form: str) -> dict[str, Any]:
    """Формы банка 102 / 135 / 123 из ответов службы — разбор сборщика (`cbr_forms`), последние `KEEP_FORM_MONTHS`."""
    unit = "share" if form == "135" else "RUB bn"
    months: dict[str, Any] = {}
    files = _soap_bank(root, form)
    for day, path in list(files.items())[-KEEP_FORM_MONTHS:]:
        body = path.read_bytes()
        entry: dict[str, Any] = {"form_date": day, "sha256": hashlib.sha256(body).hexdigest()}
        for sid, value in cbr_forms._series_points(form, day, body, "").items():
            if value is not None:
                entry[sid.rsplit(".", 1)[-1]] = round(float(value), 6)
        if len(entry) > 2:
            months[periods.form_month(day)] = entry
    where = ", ".join(sorted({str(p.parent.relative_to(root)).replace("\\", "/") for p in files.values()}))
    note = FORM_NOTE + ("; резервы и расходы — плюс значит расход; ЧПД — итоги разделов настройки "
                        "cbr_forms.nii_sections" if form == "102" else "")
    return {"basis": "ras", "unit": unit, "source": f"{where}: ответы ЦБ SOAP формы 0409{form} (разбор сборщика)",
            "note": note, "months": months}


def build_soap_group(root: Path) -> dict[str, Any]:
    """Форма группы 0409805 из ответов службы (раздел 1 — капитал, раздел 4 — нормативы); последние
    `KEEP_GROUP_QUARTERS` кварталов с числами (форма 0409803 в передаче не сохранялась)."""
    from indicators import cbr_group  # noqa: PLC0415 — ленивый импорт: история нужна только команде сборки

    regnum = str(config.company()["cbr_regnum"])
    parts: dict[str, dict[str, Path]] = {}
    for d in _soap_dirs(root):
        for path in sorted(d.glob(f"f805_reg{regnum}_*_par*.xml")):
            m = GROUP_FORM.match(path.name)
            if m:
                parts.setdefault(m.group("dt"), {}).setdefault(m.group("par"), path)
    quarters: dict[str, Any] = {}
    for dt, got in sorted(parts.items()):
        if set(got) != {"1", "4"}:
            continue
        bodies = {"par1": got["1"].read_bytes(), "par4": got["4"].read_bytes()}
        values = {k: v for k, v in cbr_group.series_points("805", bodies).items() if v is not None}
        if not values or values.get("cbr.f805.n20_0") is None:
            continue                                  # ответ без чисел: формы за период нет
        q = cbr_group.period_of(dt)
        digest = hashlib.sha256(bodies["par1"] + bodies["par4"]).hexdigest()[:16]
        quarters[q] = {"period_end": periods.quarter_end(q).isoformat(),
                       "f805": {**{k.rsplit(".", 1)[-1]: round(float(v), 6) for k, v in values.items()},
                                "sha256": digest}}
    keep = dict(list(quarters.items())[-KEEP_GROUP_QUARTERS:])
    return {"basis": "банковская группа по ЦБ", "units": {"money": "RUB bn", "percent": "доли"},
            "source": "ответы ЦБ SOAP формы 0409805 (разделы 1 и 4; разбор сборщика)",
            "note": "день первого появления формы до запуска сборщика неизвестен; ЦБ не раскрывает формы группы "
                    "эмитента с 2-го квартала 2025 года", "quarters": keep}


def _calendar_dates(root: Path) -> dict[str, tuple[str, str]]:
    """Квартал → (день выхода отчёта МСФО, источник) по листу календаря эмитента (`seed.release_calendar`)."""
    name = config.setting("seed.release_calendar")
    out: dict[str, tuple[str, str]] = {}
    if not name or not (root / str(name)).exists():
        return out
    for r in _rows(root / str(name)):
        if r.get("event") in ("ifrs_quarter", "ifrs_fy") and r.get("status") == "fact" and r.get("period"):
            out.setdefault(r["period"], (r["date"], f"{name}: {r.get('source') or 'календарь эмитента'}"[:160]))
    return out


def _fact_node(node: Any) -> dict[str, Any] | None:
    if not isinstance(node, dict) or node.get("v") is None:
        return None
    return {"v": round(float(node["v"]), 6), "src": str(node.get("src") or node.get("calc") or "факты книги")[:160]}


def build_facts_ifrs(root: Path) -> dict[str, Any]:
    """Прибыль квартала цели `ni_q` из фактов книги (`pnl_quarterly.<квартал>.<seed.profit_node>`) и день отчёта."""
    node_name = str(config.setting("seed.profit_node", "ni_shareholders"))
    dates = _calendar_dates(root)
    facts = config.facts_file("pnl_quarterly") or {}
    quarters = {}
    for q, row in sorted((facts.get("quarters") or {}).items()):
        node = _fact_node((row or {}).get(node_name))
        if node is None:
            continue
        quarters[q] = {"value": node, "report_date": dict(zip(("v", "src"), dates.get(q, (None, "не найдена"))))}
    return {"unit": "RUB bn", "target": "ni_q",
            "source": f"data/facts/pnl_quarterly.json ({node_name}: прибыль квартала в определении книги); дни "
                      f"отчётов — {config.setting('seed.release_calendar') or 'нет листа'}",
            "quarters": quarters}


def build_facts_mgmt(root: Path) -> dict[str, Any]:
    """ЧПМ и стоимость риска квартала (упр.) из фактов книги: напечатанное, а где его нет — точное."""
    facts = config.facts_file("mgmt_quarterly") or {}
    out: dict[str, Any] = {}
    for q, row in sorted((facts.get("quarters") or {}).items()):
        for key in ("nim", "cor"):
            node = _fact_node((row or {}).get(key)) or _fact_node((row or {}).get(key + EXACT))
            if node is not None:
                out.setdefault(q, {})[key] = node
    return {"basis": "mgmt", "unit": "share", "source": "data/facts/mgmt_quarterly.json (ЧПМ и стоимость риска квартала)",
            "quarters": out}


def build_empty_monthly(root: Path) -> dict[str, Any]:
    spec = release_watch.monthly(config.sources())
    return {"basis": "ras", "prefix": spec.prefix,
            "source": "месячного релиза у эмитента нет (ни МСФО, ни РСБУ): месяц входит формами ЦБ банка",
            "months": {}}


def build_empty_form101(root: Path) -> dict[str, Any]:
    definition = (config.bridge_ras_ifrs() or {}).get("iea")
    if isinstance(definition, dict) and definition.get("codes"):
        raise SystemExit("seed: в фактах есть определение процентных активов — форма 0409101 строится раскладкой "
                         "образца (stage1/ras/raw/101), а не пустым файлом")
    return {"basis": "ras", "unit": "RUB bn", "codes": None, "codes_required": None,
            "source": "процентные активы банка по форме 0409101 не размечены в фактах (bridge_ras_ifrs.iea.codes): "
                      "истории нет", "months": {}, "quarters": {}}


SOAP_BUILDERS: dict[str, Callable[[Path], dict[str, Any] | None]] = {
    "monthly_release": build_empty_monthly, "ifrs_quarters": build_facts_ifrs, "mgmt_quarters": build_facts_mgmt,
    "consensus": lambda root: build_consensus(root), "form102": lambda root: build_soap_form(root, "102"),
    "form135": lambda root: build_soap_form(root, "135"), "form123": lambda root: build_soap_form(root, "123"),
    "group_forms": build_soap_group, "form101": build_empty_form101}


BUILDERS: dict[str, Callable[[Path], dict[str, Any] | None]] = {
    "monthly_release": build_monthly, "ifrs_quarters": build_ifrs, "mgmt_quarters": build_mgmt,
    "consensus": build_consensus, "form102": build_form102, "form135": build_form135, "form123": build_form123,
    "group_forms": build_group, "form101": build_form101}


def build_all(root: Path, names: tuple[str, ...] = SEED_FILES) -> dict[str, dict[str, Any]]:
    """Файлы истории по именам; файл, которому не из чего строиться (нет определения фактов), пропускается.
    Раскладка — настройка `seed.layout` (`soap` — ответы службы ЦБ и факты, без неё — листы этапа 1 образца)."""
    builders = SOAP_BUILDERS if config.setting("seed.layout") == "soap" else BUILDERS
    out = {}
    for name in names:
        built = builders[name](root)
        if built is not None:
            out[name] = built
    return out


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m indicators.seed")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", help="только эти файлы истории (через запятую)")
    ap.add_argument("--skip", help="без этих файлов истории (через запятую)")
    args = ap.parse_args(argv)
    only = {x for x in (args.only or "").split(",") if x}
    skip = {x for x in (args.skip or "").split(",") if x}
    unknown = sorted((only | skip) - set(SEED_FILES))
    if unknown:
        print(f"нет файла истории {', '.join(unknown)}; есть: {', '.join(SEED_FILES)}", file=sys.stderr)
        return 64
    names = tuple(n for n in SEED_FILES if (not only or n in only) and n not in skip)
    built = build_all(handoff(), names)
    bad = []
    for name, obj in built.items():
        path = config.SEED_DIR / f"{name}.json"
        text = dump(obj)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                bad.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if bad:
        print("история расходится со сборкой: " + ", ".join(bad), file=sys.stderr)
        return 1
    print("история: " + ", ".join(built) + ("" if len(built) == len(names) else
                                            "; пропущено (не из чего строить): "
                                            + ", ".join(n for n in names if n not in built)))
    return 0


# ------------------------------------------------------------------ импорт в хранилище

def _at(day: str | None, shift_days: int = 0) -> str | None:
    if not day:
        return None
    return (date.fromisoformat(day) + timedelta(days=shift_days)).isoformat() + KNOWN_AT_UTC


def form101_fits(data: dict | None) -> bool:
    """История формы 101 построена под нынешнее определение процентных активов фактов (`iea.codes`,
    `codes_required`). Под другое — в ряды не идёт: ряд `cbr.f101.iea` смешал бы два определения."""
    definition = (config.bridge_ras_ifrs() or {}).get("iea")
    if not data or not isinstance(definition, dict) or not definition.get("codes"):
        return False
    return (data.get("codes") == definition.get("codes")
            and data.get("codes_required") == definition.get("codes_required"))


def import_to_store(store: Store, seed_dir: Path | None = None) -> list[str]:
    """История в ряды хранилища (идемпотентно: одинаковые точки не дублируются)."""
    touched: list[str] = []
    monthly = config.load_seed("monthly_release", seed_dir) or {}
    prefix = str(monthly.get("prefix") or release_watch.DEFAULT_PREFIX)
    spec = release_watch.Monthly(prefix=prefix)
    by_metric: dict[str, list[Point]] = {}
    for m, entry in (monthly.get("months") or {}).items():
        at = entry.get("published_at") or _at(entry.get("release_date")) \
            or _at(periods.month_end(m).isoformat(), FORM_KNOWN_DAYS)
        for metric, node in entry["values"].items():
            by_metric.setdefault(metric, []).append(Point(m, node["v"], at, "ok", "seed: " + node["src"][:120]))
    for metric, pts in by_metric.items():
        store.upsert(spec.series(metric), pts, basis=str(monthly.get("basis") or "ras"),
                     label=f"месячный релиз эмитента: {metric}", unit=spec.unit(metric))
        touched.append(spec.series(metric))
    targets = journal.targets()
    ifrs = config.load_seed("ifrs_quarters", seed_dir) or {}
    report_dates = {q: (e.get("report_date") or {}).get("v") for q, e in (ifrs.get("quarters") or {}).items()}
    pts = []
    for q, e in (ifrs.get("quarters") or {}).items():
        at = _at(report_dates.get(q)) or _at(periods.quarter_end(q).isoformat(), 60)
        pts.append(Point(q, e["value"]["v"], at, "ok", "seed: " + e["value"]["src"]))
    if pts:
        # Момент точки — выход отчёта: по нему ретро знает, что было известно на дату.
        store.upsert("actual.ni_q", pts, basis=targets["ni_q"]["basis"], unit="RUB bn", label=targets["ni_q"]["title"])
        touched.append("actual.ni_q")
    mgmt = config.load_seed("mgmt_quarters", seed_dir) or {}
    for key in ("nim", "cor"):
        pts = []
        for q, e in (mgmt.get("quarters") or {}).items():
            if key in e:
                at = _at(report_dates.get(q)) or _at(periods.quarter_end(q).isoformat(), 60)
                pts.append(Point(q, e[key]["v"], at, "ok", "seed: " + e[key]["src"]))
        if pts:
            store.upsert(f"actual.{key}_q", pts, basis="mgmt", unit="share", label=targets[f"{key}_q"]["title"])
            touched.append(f"actual.{key}_q")
    cons = config.load_seed("consensus", seed_dir) or {}
    pts = [Point(q, e["v"], _at(report_dates.get(q), -1) or _at(periods.quarter_end(q).isoformat(), 55), "ok",
                 "seed: " + e["src"][:120]) for q, e in (cons.get("quarters") or {}).items()]
    if pts:
        store.upsert("consensus.ni_q", pts, basis=targets["ni_q"]["basis"], unit="RUB bn",
                     label="консенсус прибыли квартала")
        touched.append("consensus.ni_q")
    # Формы банка. Момент первой выкладки до запуска сборщика неизвестен: берётся верхняя оценка
    # (26-е число месяца формы), чтобы история не знала больше, чем знала на деле.
    for name, form, unit in (("form102", "102", "RUB bn"), ("form135", "135", "share"), ("form123", "123", "RUB bn"),
                             ("form101", "101", "RUB bn")):
        data = config.load_seed(name, seed_dir) or {}
        if name == "form101" and not form101_fits(data):
            continue
        by_key: dict[str, list[Point]] = {}
        for m, e in (data.get("months") or {}).items():
            at = _at(e["form_date"], FORM_KNOWN_DAYS)
            for key, value in e.items():
                if key in ("form_date", "sha256"):
                    continue
                by_key.setdefault(key, []).append(
                    Point(m, value, at, "ok", f"seed: 0409{form} на {e['form_date']}, sha256 {str(e['sha256'])[:12]}"))
        for key, pts in by_key.items():
            sid = f"cbr.f{form}.{key}"
            store.upsert(sid, pts, basis="ras", unit=unit, label=f"форма 0409{form}: {key}")
            touched.append(sid)
    # Формы банковской группы: момент — верхняя оценка дня выкладки после конца квартала.
    group = config.load_seed("group_forms", seed_dir) or {}
    by_sid: dict[str, list[Point]] = {}
    for q, e in (group.get("quarters") or {}).items():
        at = _at(periods.quarter_end(q).isoformat(), GROUP_KNOWN_DAYS)
        for form in ("f805", "f803"):
            for key, value in (e.get(form) or {}).items():
                if key != "sha256":
                    by_sid.setdefault(f"cbr.{form}.{key}", []).append(
                        Point(q, value, at, "ok", f"seed: 0409{form[1:]} группы за {q}, sha256 {e[form].get('sha256', '')}"))
    for sid, pts in by_sid.items():
        store.upsert(sid, pts, basis="regulatory" if ".n20_" in sid else "group",
                     unit="share" if ".n20_" in sid else "RUB bn", label=f"форма банковской группы: {sid}")
        touched.append(sid)
    return touched


if __name__ == "__main__":
    raise SystemExit(main())
