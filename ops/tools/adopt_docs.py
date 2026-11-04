# -*- coding: utf-8 -*-
"""Документы версии книги при приёме миров — текст шаблоном, числа и даты — из книги, календаря фактов, записей
объяснений, таблиц книги и прогулки (шаг приёма миров).

    python -B ops/tools/adopt_docs.py [--check]

Пишет:
  * `docs/MANUAL.md` §10.9 — календарь ближайших отказов сборки (первые дни отказа — тем же счётом, что тест
    `test_ops_docs.py::test_the_manual_dates_the_nearest_build_refusals`: срок миров после следующего заседания Банка
    России с прогнозом, отчёт МСФО за квартал после якоря, сроки записей объяснений);
  * `docs/DECISIONS.md` — строку открытого вопроса «Пересборка миров семейства…» (тот же счёт);
  * `data/assumptions/V<версия>-CHANGES.md` — что изменилось против прежней книги: запись миров, правила, числа
    «было → стало» (таблицы книги прежнего коммита и дерева), прогулка по шагам, гейты;
  * `docs/CHANGELOG.md` — запись версии сверху (повтор приёма той же версии заменяет её, а не дописывает);
  * текст книги `ASSUMPTIONS-BOOK.md` (номер версии, раздел 10 о гейтах, строка таблицы версий) и строку таблицы версий
    `data/assumptions/README.md`.
Версия, с какой книги и какого коммита принята запись миров, дата приёма — блок `book` состояния
(`data/assumptions/worlds_state.json`). Случай, когда ближайший срок — миры (книга ещё не на новой записи), этим
шаблоном не пишется: отказ кодом 1. `--check` — ничего не пишет, код 1, если документы не равны шаблону.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adopt_worlds as A  # noqa: E402
from gate_texts import refusal_days  # noqa: E402

BOOK_DIR = ROOT / "data" / "assumptions"
MANUAL = ROOT / "docs" / "MANUAL.md"
DECISIONS = ROOT / "docs" / "DECISIONS.md"
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
CALENDAR = ROOT / "data" / "facts" / "calendar.json"
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


def d_ru(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def _half_up(x: float, nd: int):
    """Половина вверх по десятичной записи числа (327,025 → 327,03), а не по двоичной (формат Python дал бы 327,02)."""
    from decimal import ROUND_HALF_UP, Decimal
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)


def num(x: float, nd: int = 2) -> str:
    return f"{_half_up(x, nd):.{nd}f}".replace("-", "−").replace(".", ",")


def signed(x: float, nd: int = 2) -> str:
    return f"{_half_up(x, nd):+.{nd}f}".replace("-", "−").replace(".", ",")


def day_word(n: int) -> str:
    return "день" if n % 10 == 1 and n % 100 != 11 else ("дня" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "дней")


def wrap(text: str, width: int = 84) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False))


class Ctx:
    def __init__(self):
        self.book = yaml.safe_load((BOOK_DIR / "assumptions.yaml").read_text(encoding="utf-8"))
        self.state = A.read_state(ROOT)
        self.bk = self.state.get("book") or {}
        if not self.bk:
            raise SystemExit("ОТКАЗ: в состоянии нет блока book — версия книги при приёме миров неизвестна")
        self.notes = yaml.safe_load((BOOK_DIR / "gate_explanations.yaml").read_text(encoding="utf-8")) or {}
        self.events = json.loads(CALENDAR.read_text(encoding="utf-8"))["events"]
        self.days = refusal_days(self.book, self.notes)
        self.version = str(self.book["meta"]["version"])
        self.worlds = str(self.state["version"])
        self.curve = dt.date.fromisoformat(str(self.book["worlds"]["source"]["curve_date"]))
        old_tpl = yaml.safe_load(A.git(ROOT, "show", f"{self.bk['from_commit']}:data/assumptions/assumptions_template.yaml"))
        self.from_curve = dt.date.fromisoformat(str(old_tpl["worlds"]["source"]["curve_date"]))
        self.anchor = str(self.book["meta"]["anchor_period"])
        self.limit = self.days["explanations"] - dt.timedelta(days=1)

    def start(self, e: dict) -> dt.date:
        return dt.date.fromisoformat(str(e["latest"] if e.get("estimated") is True else e["date"]))

    def meetings(self) -> list[dict]:
        return sorted((e for e in self.events if e.get("kind") == "cbr_forecast"), key=self.start)

    def ifrs_event(self) -> dict:
        reps = [e for e in self.events if e.get("kind") == "ifrs" and str(e.get("covers") or "") > self.anchor]
        return min(reps, key=lambda e: str(e["covers"]))


# ------------------------------------------------------------------ MANUAL §10.9 и DECISIONS
def manual_block(c: Ctx) -> str:
    d = c.days
    if d["worlds"] <= d["ifrs"]:
        raise SystemExit("ОТКАЗ: ближайший срок — миры (книга не на новой записи миров): календарь этим шаблоном не пишется")
    y, q = int(c.anchor[:4]), int(c.anchor[-1])
    nxt = next(e for e in c.meetings() if c.start(e) > c.curve)
    prev = [e for e in c.meetings() if c.from_curve < c.start(e) <= c.curve]
    n = int(c.book["checks"]["manual_overdue_days"]["worlds_after_cbr"])
    nif = int(c.book["checks"]["manual_overdue_days"]["ifrs_fact"])
    ev = c.ifrs_event()
    cy, cq = int(ev["covers"][:4]), int(ev["covers"][-1])
    manual_until = dt.date.fromisoformat(str(c.notes["manual_input_overdue"]["valid_until"])) if "manual_input_overdue" in c.notes else None
    others = sorted({dt.date.fromisoformat(str(v["valid_until"])) for k, v in c.notes.items() if k != "manual_input_overdue"})
    intro = (f"**Календарь ближайших отказов сборки** — книга {c.version} (миры {c.worlds}, кривая {d_ru(c.curve)}) на якоре "
             f"{q}-го квартала {y} года. Даты считаются из названных файлов и двигаются вместе с ними. С первого дня отказа "
             "сборка выходит кодом 1 и витрина замирает на прежнем выпуске; суточный юнит после трёх прогонов встаёт "
             "(`start-limit-hit`, раздел 10.2), пересборка отвечает кодом 1, а задание CI «контракт выпуска» краснеет на "
             "каждом push.")
    if prev:
        pm = c.start(prev[-1])
        intro += (f" Срок миров после заседания {d_ru(pm)} (первый день отказа — {d_ru(pm + dt.timedelta(days=n + 1))}) "
                  f"снимает выкладка книги {c.version}: до неё на бою книга {c.bk['from']} с кривой {d_ru(c.from_curve)}, и "
                  "срок действует.")
    rows = {}
    latest = dt.date.fromisoformat(str(ev.get("latest") or ev["date"]))
    ifrs_text = (f"отчёт МСФО за {cq}-й квартал {cy} года не внесён: гейт `manual_input_overdue` срабатывает по этой ветви")
    src = (f"поздняя граница окна события `{ev['id']}` ({d_ru(latest)}; оценка дня отчёта — "
           f"{d_ru(dt.date.fromisoformat(str(ev['date'])))}) и {nif} {day_word(nif)} книги (`ifrs_fact`); объявит эмитент день "
           "отчёта и календарь его получит — срок считается от него")
    todo = (f"перезаякоривание на отчёт МСФО за {cq}-й квартал {cy} года (раздел 10.4). Не готово к сроку — запись объяснения "
            "`manual_input_overdue` на отчёт со сроком до перезаякоривания, не дальше срока прочих записей объяснений")
    if manual_until and manual_until + dt.timedelta(days=1) == d["ifrs"]:
        ifrs_text += (f"; в тот же день истекает запись объяснения `manual_input_overdue` (срок {d_ru(manual_until)}): она "
                      "называет только миры")
        src += (f"; срок записи — `valid_until` в `data/assumptions/gate_explanations.yaml` (плашка «объяснение истекает» "
                f"стоит в выпуске с {d_ru(manual_until - dt.timedelta(days=30))})")
    rows[d["ifrs"]] = f"| {d_ru(d['ifrs'])} | {ifrs_text} | {src} | {todo} |"
    for u in others:
        day = u + dt.timedelta(days=1)
        text = (f"| {d_ru(day)} | объяснения прочих сработавших гейтов: срок их записей книги — {d_ru(u)} включительно | "
                f"`valid_until` записей; плашка «объяснение истекает» стоит в выпуске с {d_ru(u - dt.timedelta(days=30))} | "
                f"перезаякоривание на отчёт МСФО за {cq}-й квартал {cy} года (раздел 10.4): объяснения пишутся заново на книге "
                "с новым якорем. Перезаякоривание к сроку не готово — новые записи со сроком для гейтов, причина которых "
                "осталась; у `guidance_gap` срок — не дальше дня отчёта |")
        rows[day] = rows[day][:-2] + "; " + text.split(" | ", 2)[1] + " |" if day in rows else text
    nm = c.start(nxt)
    rows[d["worlds"]] = (
        f"| {d_ru(d['worlds'])} | миры не пересобраны после заседания Банка России {d_ru(nm)}: кривая миров книги "
        f"{c.version} — от {d_ru(c.curve)} (запись миров {c.worlds}) | событие `{nxt['id']}` календаря фактов и {n} "
        f"{day_word(n)} книги (`worlds_after_cbr`); плашки нет | новая запись миров семейства с кривой не раньше {d_ru(nm)} и "
        "новая версия книги (раздел 10.5). Записи семейства к сроку нет — запись объяснения `manual_input_overdue` в "
        f"`data/assumptions/gate_explanations.yaml` с ожидаемой массой 1,0 и сроком не дальше {d_ru(c.limit)} — ближайшего "
        "срока записей объяснений (срок позже закрыл бы и другие ручные входы); к сроку миров его двигают вместе с "
        "переписанными объяснениями |")
    table = ["| Первый день отказа | Что просрочено | Откуда дата | Что сделать до этого дня |", "|---|---|---|---|"]
    table += [rows[k] for k in sorted(rows)]
    return wrap(intro) + "\n\n" + "\n".join(table) + "\n\n"


def manual_text(c: Ctx, text: str) -> str:
    a = text.index("**Календарь ближайших отказов сборки**")
    b = text.index("Дальше по календарю фактов:", a)
    out = text[:a] + manual_block(c) + text[b:]
    tail_a = out.index("Дальше по календарю фактов:")
    tail_b = out.index("\n\n", tail_a)
    tail = " ".join(out[tail_a:tail_b].split())
    tail = re.sub(r"; миры после следующего заседания с прогнозом \(\d\d\.\d\d\.\d{4}\) — с \d\d\.\d\d\.\d{4}\.", ".", tail)
    return out[:tail_a] + wrap(tail) + out[tail_b:]


def decisions_row(c: Ctx) -> str:
    d = c.days
    n = int(c.book["checks"]["manual_overdue_days"]["worlds_after_cbr"])
    past = [e for e in c.meetings() if c.start(e) <= c.curve]
    pm = c.start(past[-1])
    nm = c.start(next(e for e in c.meetings() if c.start(e) > c.curve))
    ev = c.ifrs_event()
    cy, cq = int(ev["covers"][:4]), int(ev["covers"][-1])
    if c.from_curve < pm:                    # прежняя книга стоит на кривой до заседания: на бою срок идёт до выкладки
        mu = (c.notes.get("manual_input_overdue") or {}).get("valid_until")
        held = (f"сборку держит запись объяснения до {d_ru(dt.date.fromisoformat(str(mu)))} включительно, дальше — отказ кодом 1"
                if mu else "без записи объяснения сборка отказывает кодом 1")
        before = (f"до выкладки книги {c.version} на бою книга {c.bk['from']} (кривая {d_ru(c.from_curve)}): с "
                  f"{d_ru(pm + dt.timedelta(days=n + 1))} на бою срабатывает гейт `manual_input_overdue`, {held}. После выкладки")
    else:                                    # прежняя книга уже на кривой после заседания
        before = (f"книга {c.bk['from']} на бою стоит на кривой {d_ru(c.from_curve)} — не раньше заседания, срок миров она "
                  f"держит сама. После выкладки книги {c.version}")
    return (f"| Пересборка миров семейства после заседания ЦБ {d_ru(pm)} — **книга {c.version} на мирах {c.worlds} (кривая "
            f"{d_ru(c.curve)}; ветка `worlds-{c.worlds}`), ждёт проверки и выкладки ведущим** | автор книги-источника "
            f"семейства, затем новая версия книги; выкладка — ведущий, до {d_ru(pm + dt.timedelta(days=n))} | {before} "
            f"действует запись, на которой стоит книга {c.version}, но не дольше 21 дня после следующего заседания с прогнозом "
            f"({d_ru(nm)}): с {d_ru(d['worlds'])} без новой записи миров (кривая не раньше {d_ru(nm)}) или записи объяснения "
            f"гейта `manual_input_overdue` сборка отказывает кодом 1. Запись объяснения — со сроком не дальше {d_ru(c.limit)}, "
            f"ближайшего срока записей объяснений: позже она скрыла бы невнесённый отчёт МСФО за {cq}К{cy} "
            "(`docs/MANUAL.md` §10.9). То же правило — после каждого заседания с прогнозом |")


def decisions_text(c: Ctx, text: str) -> str:
    lines = text.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.startswith("| Пересборка миров семейства")]
    if len(idx) != 1:
        raise SystemExit(f"ОТКАЗ: в DECISIONS строк «Пересборка миров семейства» {len(idx)}, нужна одна")
    lines[idx[0]] = decisions_row(c)
    return "\n".join(lines)


# ------------------------------------------------------------------ V<v>-CHANGES.md и CHANGELOG
def tables(rev: str | None) -> dict:
    text = A.git(ROOT, "show", f"{rev}:data/assumptions/results.json") if rev else (BOOK_DIR / "results.json").read_text(encoding="utf-8")
    return json.loads(text)


def numbers(res: dict) -> dict:
    h = res["headline"]
    w = {L: res["layers"][L] for L in res["layers"]}
    return {"median": h["median"], "print": h["printed_median"], "band80": h["band80"], "point": h["point"], "low": h["low"],
            "high": h["high"], "gates": sorted(x["name"] for x in res["checks"] if x.get("kind") == "gate" and x.get("fired")),
            "version": res["book_version"], "layers": w}


def changes(c: Ctx) -> str:
    before, after = numbers(tables(c.bk["from_commit"])), numbers(tables(None))
    walk_p = ROOT / "var" / "adopt" / "walk.json"
    walk = json.loads(walk_p.read_text(encoding="utf-8")) if walk_p.exists() else None
    out_txt = BOOK_DIR / "evidence" / "path" / "out" / f"walk_{c.bk['from']}_to_{c.version}.txt"
    lines = [f"# Книга {c.version} — что изменилось против {c.bk['from']}: миры ставок {c.worlds}", "",
             f"Новая версия книги — приём записи миров семейства {c.worlds} (кривая {d_ru(c.curve)}; прежняя — кривая "
             f"{d_ru(c.from_curve)}) командой `ops/tools/adopt_worlds.py --version {c.worlds}` по манифесту "
             "`data/assumptions/worlds_dependents.yaml`. Дата книги, дата оценки, цена и зерно — прежние; суждения книги не "
             "менялись: числа, зависящие от миров, пересчитаны правилами книги (`ops/tools/worlds_rules.py`) и выводом на ядре "
             "(`ops/tools/rederive.py`). Этот файл пишет `ops/tools/adopt_docs.py`.", "",
             "## Что пересчитано", "",
             "- запись миров, рецепт, входы и описание рецепта — побайтово из источника семейства; банковская надстройка — лист "
             "сектора семейства и `worlds_bank.json` версии;",
             "- ключи происхождения шаблона (дата кривых, хэш и дата записи, источник суждений);",
             "- дальние ключи спредов книг активов 2028–2030 и LT — правилом листа калибровки ЧПД на опоре мира H;",
             "- пути стоимости риска режимов и концы оси-связки κ — перенос κ по реальной ставке мира M (правила класса 6);",
             "- ключ уровня маржи справочных вариантов «другой уровень мира» — мостом листа при ключевой мира;",
             "- числа, выведенные на ядре (ближние ключи спредов, корни строк, концы осей, варианты, пороги по правилу листа), и "
             "центр премии средств клиентов — до неподвижной точки вывода;",
             "- развилки сухим перевыводом (`forks_rd.json`), таблицы книги, контрольная модель, числа документов, запись листа "
             "предельной экономики, объяснения гейтов.", "",
             "## Числа (таблицы книги, ₽ на акцию)", "", "| | было | стало |", "|---|---:|---:|",
             f"| медиана (печать) | {num(before['median'])} ({num(before['print'], 1)}) | {num(after['median'])} ({num(after['print'], 1)}) |",
             f"| полоса 80 % | {num(before['band80'][0], 1)}–{num(before['band80'][1], 1)} | {num(after['band80'][0], 1)}–{num(after['band80'][1], 1)} |",
             f"| точка | {num(before['point'])} | {num(after['point'])} |",
             f"| низ / верх точки | {num(before['low'])} / {num(before['high'])} | {num(after['low'])} / {num(after['high'])} |", ""]
    if walk:
        lines += ["## Прогулка (точка по шагам, ₽)", "", "| шаг | точка | сдвиг |" + (" медиана |" if "median" in walk["rows"][0] else ""),
                  "|---|---:|---:|" + ("---:|" if "median" in walk["rows"][0] else "")]
        prev = None
        for r in walk["rows"]:
            dp = "" if prev is None else signed(r["point"] - prev)
            lines.append(f"| {r['step']} | {num(r['point'])} | {dp} |" + (f" {num(r['median'])} |" if "median" in r else ""))
            prev = r["point"]
        lines += ["", f"Печать прогулки — `{out_txt.relative_to(ROOT).as_posix()}`; файл шагов — тот же каталог `inputs/`.", ""]
    gone = sorted(set(before["gates"]) - set(after["gates"]))
    new = sorted(set(after["gates"]) - set(before["gates"]))
    lines += ["## Гейты", "", f"- сработали: {', '.join(after['gates']) or '—'};",
              f"- новые: {', '.join(new) or 'нет'}; больше не срабатывают: {', '.join(gone) or 'нет'};",
              "- объяснения переписаны шаблоном `ops/tools/gate_texts.py` числами книги.", ""]
    return "\n".join(lines)


def changelog_text(c: Ctx, text: str) -> str:
    before, after = numbers(tables(c.bk["from_commit"])), numbers(tables(None))
    date = dt.date.fromisoformat(c.bk["date"])
    head = f"## {d_ru(date)} — книга {c.version}: миры ставок {c.worlds} одной командой приёма"
    body = [head, "",
            f"- **Миры** — запись семейства {c.worlds} (кривая {d_ru(c.curve)}; было — кривая {d_ru(c.from_curve)}) командой "
            f"`ops/tools/adopt_worlds.py --version {c.worlds}` по манифесту `data/assumptions/worlds_dependents.yaml`; "
            "правила чисел, зависящих от миров, — `ops/tools/worlds_rules.py` (дальние ключи спредов, пути CoR и концы κ, "
            "центр премии средств, мост вариантов уровня маржи), шаги — коммитами команды.",
            f"- **Числа** (таблицы книги): медиана {num(before['median'])} → {num(after['median'])} ₽ (печать "
            f"{num(before['print'], 1)} → {num(after['print'], 1)}), точка {num(before['point'])} → {num(after['point'])} ₽, "
            f"полоса 80 % {num(before['band80'][0], 1)}–{num(before['band80'][1], 1)} → {num(after['band80'][0], 1)}–"
            f"{num(after['band80'][1], 1)} ₽; разложение — `data/assumptions/V{c.version}-CHANGES.md`.",
            f"- Дата книги, оценки, цена и зерно — прежние; суждения не менялись.", ""]
    block = "\n".join(body)
    # повтор приёма той же версии заменяет строки записи, написанные шаблоном (до строки «Дата книги…»); строки,
    # дописанные в запись после (выкладка), остаются
    m = re.search(rf"^## \d\d\.\d\d\.\d{{4}} — книга {re.escape(c.version)}: миры ставок {re.escape(c.worlds)} .*?(?=^## )", text,
                  flags=re.M | re.S)
    if m:
        entry, last = m.group(0), body[-2] + "\n"
        tail = entry[entry.index(last) + len(last):] if last in entry else "\n"
        return text[:m.start()] + block + tail + text[m.end():]
    first = re.search(r"^## ", text, flags=re.M).start()
    return text[:first] + block + "\n" + text[first:]


def gates_word(n: int) -> str:
    return "гейт" if n % 10 == 1 and n % 100 != 11 else ("гейта" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "гейтов")


def version_row(c: Ctx, readme: bool) -> str:
    before, after = numbers(tables(c.bk["from_commit"])), numbers(tables(None))
    date = d_ru(dt.date.fromisoformat(c.bk["date"]))
    what = (f"миры семейства {c.worlds} (кривая {d_ru(c.curve)}) — команда приёма миров (`ops/tools/adopt_worlds.py`); суждения, "
            f"дата книги, цена и зерно — книги {c.bk['from']}; медиана {num(before['median'])} → {num(after['median'])} ₽ (печать "
            f"{num(before['print'], 1)} → {num(after['print'], 1)}), точка {num(before['point'])} → {num(after['point'])} ₽ "
            f"(`V{c.version}-CHANGES.md`)")
    return f"| {c.version} | {date} | {what} |"


def add_version_row(c: Ctx, text: str, readme: bool) -> str:
    lines = text.split("\n")
    row = version_row(c, readme)
    have = [i for i, ln in enumerate(lines) if ln.startswith(f"| {c.version} | ")]
    if have:
        lines[have[0]] = row
        return "\n".join(lines)
    prev = [i for i, ln in enumerate(lines) if ln.startswith(f"| {c.bk['from']} | ")]
    if not prev:
        raise SystemExit(f"ОТКАЗ: в таблице версий нет строки книги {c.bk['from']}")
    lines.insert(prev[-1] + 1, row)
    return "\n".join(lines)


def book_text(c: Ctx, text: str) -> str:
    """Текст книги: номер версии в заголовке и в шапке раздела 0, строка таблицы версий, раздел 10 о гейтах."""
    fired = numbers(tables(None))["gates"]
    date = d_ru(dt.date.fromisoformat(c.bk["date"]))
    text = re.sub(r"^(# Совкомбанк — книга допущений, версия )[0-9.]+", lambda m: m.group(1) + c.version, text, count=1, flags=re.M)
    text = re.sub(r"\*\*версия [0-9.]+ записана:\*\*\s+\d\d\.\d\d\.\d{4} \([^)]*\)",
                  f"**версия {c.version} записана:** {date} (миры семейства {c.worlds} — команда приёма миров)", text, count=1)
    text = re.sub(r"(> \*\*Числа раздела — выпуск ядра на книге )[0-9.]+(\*\*)", lambda m: m.group(1) + c.version + m.group(2), text,
                  count=1)
    text = re.sub(r"(\*\*тег версии:\*\* `book-)[0-9.]+(`)", lambda m: m.group(1) + c.version + m.group(2), text, count=1)
    others = sorted({str(v["valid_until"]) for k, v in c.notes.items() if k != "manual_input_overdue"})
    until = d_ru(dt.date.fromisoformat(others[0])) if others else "—"
    text = re.sub(r"На книге [0-9.]+ сработали \d+ гейт\w*, у всех объяснения действуют по\s+\d\d\.\d\d\.\d{4}:",
                  f"На книге {c.version} сработали {len(fired)} {gates_word(len(fired))}, у всех объяснения действуют по\n{until}:", text, count=1)
    d = c.days
    mu = c.notes.get("manual_input_overdue", {}).get("valid_until")
    ev = c.ifrs_event()
    para = (f"Гейт ручных входов `manual_input_overdue` по мирам молчит до {d_ru(d['worlds'] - dt.timedelta(days=1))}: книга "
            f"{c.version} стоит на записи миров семейства {c.worlds} (кривая {d_ru(c.curve)}); с {d_ru(d['ifrs'])} он сработает по "
            f"невнесённому отчёту МСФО за {ev['covers'][-1]}-й квартал {ev['covers'][:4]} года — его объяснение в книге "
            f"{c.version} стоит со сроком {d_ru(dt.date.fromisoformat(str(mu))) if mu else '—'} и называет только миры (календарь "
            "отказов — `docs/MANUAL.md` §10.9).")
    m = re.search(r"Гейт ручных входов `manual_input_overdue` [^\n]*(?:\n(?!\n)[^\n]*)*", text)
    if not m:
        raise SystemExit("ОТКАЗ: в тексте книги нет абзаца о гейте ручных входов")
    text = text[:m.start()] + wrap(para, 124) + text[m.end():]
    return add_version_row(c, text, readme=False)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    c = Ctx()
    targets = [(MANUAL, manual_text(c, MANUAL.read_text(encoding="utf-8"))),
               (DECISIONS, decisions_text(c, DECISIONS.read_text(encoding="utf-8"))),
               (BOOK_DIR / f"V{c.version}-CHANGES.md", changes(c) + "\n"),
               (CHANGELOG, changelog_text(c, CHANGELOG.read_text(encoding="utf-8"))),
               (BOOK_DIR / "ASSUMPTIONS-BOOK.md", book_text(c, (BOOK_DIR / "ASSUMPTIONS-BOOK.md").read_text(encoding="utf-8"))),
               (BOOK_DIR / "README.md", add_version_row(c, (BOOK_DIR / "README.md").read_text(encoding="utf-8"), readme=True))]
    stale = []
    for path, text in targets:
        now = path.read_text(encoding="utf-8") if path.exists() else None
        if now != text:
            stale.append(path.relative_to(ROOT).as_posix())
            if not a.check:
                path.write_text(text, encoding="utf-8", newline="\n")
    print(("устарели: " if a.check else "записано: ") + (", ".join(stale) or "—"))
    return 1 if a.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
