# -*- coding: utf-8 -*-
"""Инструменты оператора `ops/tools/`: числа в документах, прогулка книги,
миры семейства, проба источников (адрес PDF эмитента — из затравки, дымовая проверка
распознавания), замер времени и памяти команды, худший по времени случай сборки
(цена у медианы), параллельный прогон набора тестов частями CI и мутации с записью
исходов. Сети нет: проба ходит в фикстуры индикаторов. Инструмент бюджета
проверяют tests/test_ops_units.py и tests/test_ops_ci.py."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "ops" / "tools"
FIXTURE_BOOK = ROOT / "tests" / "fixtures" / "core" / "book.json"
FIXTURE_FACTS = ROOT / "tests" / "fixtures" / "core" / "facts"
BOOK = ROOT / "data" / "assumptions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ render_numbers

render_numbers = _load("render_numbers")
RESULTS = {"headline": {"printed_median": 350.0, "band80": [300.25, 410.0], "p_below": 0.123},
           "reverse_dcf": {"rows": [{"axis": "ERP", "value": -0.0186}, {"axis": "ROE", "value": None}]},
           "cells": [{"cell": {"world": "M", "regime": "norm"}, "v": 12345.678}]}


@pytest.mark.parametrize("path,fmt,text", [
    ("headline.printed_median", "r0", "350"),
    ("headline.band80[0]", "r1", "300,2"),
    ("headline.p_below", "p1", "12,3"),
    ("reverse_dcf.rows[axis=ERP].value", "sp2", "−1,86"),
    ("reverse_dcf.rows[axis=ROE].value", "sp2n", "недостижимо"),
    ("cells[cell.world=M&cell.regime=norm].v", "r0", "12 346"),
])
def test_marks_resolve_and_format_like_the_documents(path, fmt, text):
    assert render_numbers.formatted(render_numbers.resolve(RESULTS, path), fmt) == text


def test_render_rewrites_values_and_reports_broken_marks():
    doc = "Медиана ≈<!--=headline.printed_median r0-->1<!--/--> ₽, `<!--=x r0-->пример<!--/-->`.\n"
    new, errors = render_numbers.render(doc, RESULTS)
    assert errors == [] and "<!--=headline.printed_median r0-->350<!--/-->" in new
    assert "`<!--=x r0-->пример<!--/-->`" in new, "метка в коде — пример синтаксиса"
    _, errors = render_numbers.render("x <!--=нет.пути r0-->1<!--/-->\n", RESULTS)
    assert errors and "нет ключа" in errors[0]
    _, errors = render_numbers.render("<!--=headline.printed_median r0-->1<!--/--> в начале\n", RESULTS)
    assert errors and "в начале строки" in errors[0]


def test_render_check_on_a_tree(tmp_path, capsys):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    assert render_numbers.main(["--check", "--root", str(root)]) == 0, "меток нет — сверять нечего"
    doc = root / "docs" / "X.md"
    doc.write_text("Медиана ≈<!--=headline.printed_median r0-->1<!--/--> ₽\n", encoding="utf-8")
    assert render_numbers.main(["--check", "--root", str(root)]) == 1, "метки есть, результатов нет"
    (root / "data" / "assumptions").mkdir(parents=True)
    (root / "data" / "assumptions" / "results.json").write_text(json.dumps(RESULTS), encoding="utf-8")
    assert render_numbers.main(["--check", "--root", str(root)]) == 1
    assert "устарел: docs/X.md" in capsys.readouterr().err
    assert render_numbers.main(["--root", str(root)]) == 0
    assert "≈<!--=headline.printed_median r0-->350<!--/--> ₽" in doc.read_text(encoding="utf-8")
    assert render_numbers.main(["--check", "--root", str(root)]) == 0


# ------------------------------------------------------------ walk_book

@pytest.fixture(scope="module")
def walk_book():
    return _load("walk_book")


def _steps(tmp_path: Path, steps) -> Path:
    path = tmp_path / "steps.yaml"
    path.write_text(yaml.safe_dump(steps, allow_unicode=True), encoding="utf-8")
    return path


def test_the_walk_between_two_books_converges(tmp_path, walk_book, capsys):
    end = json.loads(FIXTURE_BOOK.read_text(encoding="utf-8"))
    end["valuation"]["beta_e"] = round(end["valuation"]["beta_e"] + 0.05, 4)
    end["valuation"]["erp"] = round(end["valuation"]["erp"] + 0.003, 5)
    (tmp_path / "end.json").write_text(json.dumps(end, ensure_ascii=False), encoding="utf-8")
    steps = _steps(tmp_path, [{"name": "β", "from_end": ["valuation.beta_e"]},
                              {"name": "ERP", "from_end": ["valuation.erp"]}])
    code = walk_book.main(["--start", str(FIXTURE_BOOK), "--end", str(tmp_path / "end.json"),
                           "--steps", str(steps), "--facts", str(FIXTURE_FACTS),
                           "--json", str(tmp_path / "walk.json")])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "последний шаг = прямой расчёт конечной книги: ДА" in out
    assert "книга после шагов = конечная книга целиком: ДА" in out
    rows = json.loads((tmp_path / "walk.json").read_text(encoding="utf-8"))["rows"]
    assert [r["step"] for r in rows] == ["старт", "β", "ERP"]
    assert rows[1]["point"] < rows[0]["point"], "выше β — выше стоимость капитала, ниже точка"

    partial = _steps(tmp_path, [{"name": "только β", "from_end": ["valuation.beta_e"]}])
    code = walk_book.main(["--start", str(FIXTURE_BOOK), "--end", str(tmp_path / "end.json"),
                           "--steps", str(partial), "--facts", str(FIXTURE_FACTS)])
    assert code == 1 and "конечная книга целиком: НЕТ" in capsys.readouterr().out


def test_a_step_that_breaks_the_book_is_refused(tmp_path, walk_book, capsys):
    steps = _steps(tmp_path, [{"name": "незнакомый ключ", "set": {"valuation.no_such_key": 1}}])
    code = walk_book.main(["--start", str(FIXTURE_BOOK), "--end", str(FIXTURE_BOOK),
                           "--steps", str(steps), "--facts", str(FIXTURE_FACTS)])
    assert code == 2
    assert "шаг 1 «незнакомый ключ»" in capsys.readouterr().err
    bad = _steps(tmp_path, [{"name": "без правок"}])
    assert walk_book.main(["--start", str(FIXTURE_BOOK), "--end", str(FIXTURE_BOOK),
                           "--steps", str(bad), "--facts", str(FIXTURE_FACTS)]) == 2


# ------------------------------------------------------------ refresh_worlds

@pytest.fixture(scope="module")
def refresh_worlds():
    return _load("refresh_worlds")


def _needs_book():
    if not (BOOK / "assumptions.yaml").exists() or not (BOOK / "worlds_source.json").exists():
        pytest.skip("книги 1.0 ещё нет в data/assumptions/ (поток book)")


def test_the_world_canon_holds(refresh_worlds, capsys):
    _needs_book()
    assert refresh_worlds.main(["--check"]) == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert "рецепт воспроизводит worlds_source.json" in out and "воспроизводится сборкой" in out


def test_a_broken_record_breaks_the_canon(refresh_worlds, tmp_path):
    _needs_book()
    book = tmp_path / "assumptions"
    shutil.copytree(BOOK, book, ignore=shutil.ignore_patterns("evidence", "__pycache__"))
    record = json.loads((book / "worlds_source.json").read_text(encoding="utf-8"))
    record["rows"][0]["key_avg"] = record["rows"][0]["key_avg"] + 1.0
    (book / "worlds_source.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    problems, _ = refresh_worlds.check_canon(book)
    assert any("рецепт не воспроизводит" in p for p in problems), problems
    assert any("sha256" in p for p in problems), problems


def test_a_candidate_of_the_same_record_changes_nothing(refresh_worlds, tmp_path):
    _needs_book()
    record = tmp_path / "record"
    record.mkdir()
    shutil.copyfile(BOOK / "worlds_source.json", record / "worlds_source.json")
    before = {p.name: p.read_bytes() for p in BOOK.iterdir() if p.is_file()}
    out = tmp_path / "candidate"
    assert refresh_worlds.main(["--record", str(record), "--out", str(out)]) == 0
    assert (out / "assumptions.candidate.yaml").read_text(encoding="utf-8") == \
        (BOOK / "assumptions.yaml").read_text(encoding="utf-8")
    report = (out / "CANDIDATE.md").read_text(encoding="utf-8")
    assert "Что меняется в записи (0)" in report and "| точка при λ книги, ₽ |" in report
    assert {p.name: p.read_bytes() for p in BOOK.iterdir() if p.is_file()} == before, "книга не тронута"


def test_the_candidate_never_writes_into_the_book(refresh_worlds, tmp_path, capsys):
    _needs_book()
    record = tmp_path / "record"
    record.mkdir()
    shutil.copyfile(BOOK / "worlds_source.json", record / "worlds_source.json")
    assert refresh_worlds.main(["--record", str(record), "--out", str(BOOK / "candidate")]) == 1
    assert "не пишет в книгу" in capsys.readouterr().err
    assert not (BOOK / "candidate").exists()


def test_the_candidate_template_changes_only_the_record_lines(refresh_worlds):
    _needs_book()
    text = (BOOK / "assumptions_template.yaml").read_text(encoding="utf-8")
    new = refresh_worlds.candidate_template(text, sha="f" * 64, asof="2026-10-24", curve_date="2026-10-23")
    changed = [(a, b) for a, b in zip(text.splitlines(), new.splitlines()) if a != b]
    assert len(text.splitlines()) == len(new.splitlines())
    assert {a.split(":")[0].strip() for a, _ in changed} <= {"sha256", "record_asof", "curve_date", "curve_as_of"}
    assert any('"' + "f" * 64 + '"' in b for _, b in changed)


# ------------------------------------------------------------ probe

@pytest.fixture
def probe(monkeypatch, tmp_path):
    from tests.support_ind import use_fixtures

    use_fixtures(monkeypatch, tmp_path, token=False)
    return _load("probe")


def _fake_tls(host, context):
    if context is None:
        import ssl

        raise ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")
    return "Russian Trusted Root CA"


PDF = b"%PDF-1.7 fixture"
DOCS = {"dataservice": b'[{"id": 1, "category_name": "x"}]', "/static/documents/": PDF}


def test_the_probe_walks_every_source_through_the_collector_road(probe, monkeypatch):
    from tests.support_ind import FakeGetter

    getter = FakeGetter(overrides=DOCS)
    rows = probe.run(getter=getter, tls=_fake_tls)
    by = {(r.probe, r.what): r for r in rows}
    assert {r.probe for r in rows} == set(probe.PROBES)
    forms = [r for r in rows if r.probe == "cbr_forms"]
    assert len(forms) == 4 and all(r.ok for r in forms), [r.note for r in forms]
    assert {r.what.split()[0] for r in forms} == {f"GetDatesForF{f}" for f in probe.FORMS}
    for r in rows:
        if r.probe != "tinvest":
            assert r.ok, (r.probe, r.what, r.note)
    assert by[("tinvest", "TLS с закреплённым корнем")].ok
    assert "как ожидается" in by[("tinvest", "TLS без закреплённого корня (справочно)")].note
    share = by[("tinvest", "ShareBy главного тикера (токен из окружения)")]
    assert not share.ok and "TINVEST_TOKEN" in share.note
    table = probe.table(rows)
    assert table.count("\n") == len(rows) + 1 and "| НЕТ " in table
    assert all("?" not in r.target for r in rows), "адреса без строки запроса"


def test_the_probe_of_the_group_forms_needs_numbers_not_a_status_code(probe):
    """Формы банковской группы: код организации, перечень периодов, форма 0409805 за последний период —
    проба засчитана, только когда в форме есть итог капитала и Н20.0 числами."""
    from tests.support_ind import FIX, FakeGetter

    rows = probe.run(["cbr_group"], getter=FakeGetter(), tls=_fake_tls)
    assert [r.what.split()[0].rstrip(":") for r in rows] == ["RegNumToIntCode", "GetPeriodsOfDocuments", "GetF805Xml"]
    assert all(r.ok for r in rows), [r.note for r in rows]
    assert "последний 2026Q2" in rows[1].note and "0409805 — 10" in rows[1].note
    assert "капитал 680.0 млрд ₽" in rows[2].note and "Н20.0 12.80%" in rows[2].note
    empty = {("CreditOrgInfo", "<par>1</par>"): (FIX / "cbr_group/f805_absent_par1.xml").read_bytes(),
             ("CreditOrgInfo", "<par>4</par>"): (FIX / "cbr_group/f805_absent_par4.xml").read_bytes()}
    rows = probe.run(["cbr_group"], getter=FakeGetter(overrides=empty), tls=_fake_tls)
    assert [r.ok for r in rows] == [True, True, False] and "чисел в форме нет" in rows[2].note      # код ответа — 200
    stub = probe.run(["cbr_group"], getter=FakeGetter(overrides={"GetPeriodsOfDocuments": b"<html>stub</html>"}),
                     tls=_fake_tls)
    assert [r.ok for r in stub] == [True, False, False] and "не перечень" in stub[1].note


def test_the_probe_of_the_issuer_documents(probe, tmp_path):
    """Документы эмитента: страница пресс-релизов, каждая папка двери на рабочем хосте, первая папка — на
    запасном хосте с закреплённым корнем, документ месячного релиза с рабочего хоста."""
    from indicators import config, http
    from tests.support_ind import FakeGetter

    cfg = config.sources()
    getter = FakeGetter(overrides=DOCS)
    rows = probe.probe_issuer_docs(getter, cfg=cfg, state=tmp_path / "нет")
    assert all(r.ok and r.probe == "issuer_docs" for r in rows), [(r.what, r.note) for r in rows if not r.ok]
    whats = [r.what for r in rows]
    folders = cfg["issuer_docs"]["door"]["folders"]
    assert whats[0] == "страница пресс-релизов" and len([w for w in whats if w.startswith("дверь документов: ")]) == len(folders)
    assert "записей 3, месячных релизов 1" in rows[0].note
    spare = next(r for r in rows if "запасном хосте" in r.what)
    assert spare.target.startswith("cfg.tbank.ru/")
    assert http.tls_context("https://cdn.tbank-online.com/x") is None          # рабочим хостам чужой корень не нужен
    doc = rows[-1]
    assert doc.what == probe.DOCS_WHAT and doc.target.startswith("cdn.tbank-online.com/static/documents/")
    assert "адрес из списка эмитента (2026M09)" in doc.note and "PDF, sha256" in doc.note
    assert all("?" not in r.target for r in rows)
    # порядок адреса: --pdf → состояние сборщика → список эмитента
    listed = [{"url": "https://cdn.tbank-online.com/static/documents/a.pdf", "kind": "ops_release", "date": "2026-10-23",
               "period": "2026M09"},
              {"url": "https://cdn.tbank-online.com/static/documents/b.pdf", "kind": "ifrs_press", "date": "2026-11-19"}]
    empty = tmp_path / "state"
    assert probe.doc_address(cfg, state=empty, listed=listed) == (listed[0]["url"], "адрес из списка эмитента (2026M09)")
    assert probe.doc_address(cfg, state=empty, listed=listed[1:]) == (None, "адреса нет")
    (empty / "issuer_docs").mkdir(parents=True)
    known = "https://cdn.tbank-online.com/static/documents/c.pdf"
    (empty / "issuer_docs" / "index.json").write_text(json.dumps({
        known: {"kind": "ops_release", "listed": "2026-11-24"},
        "https://cdn.tbank-online.com/static/documents/d.pdf": {"kind": "meeting_minutes", "listed": "2026-12-20"}}),
        encoding="utf-8")
    assert probe.doc_address(cfg, state=empty, listed=listed) == (known, "адрес сборщика (состояние)")
    assert probe.doc_address(cfg, pdf="https://cdn.tbank-online.com/x.pdf", state=empty, listed=listed) == (
        "https://cdn.tbank-online.com/x.pdf", "адрес из --pdf")
    # страница вместо файла, чужой хост и молчащий источник — строка «НЕТ» с причиной, а не падение
    page = probe.probe_issuer_docs(FakeGetter(overrides={"/static/documents/": b"<html>404</html>"}), cfg=cfg,
                                   state=tmp_path / "нет")
    assert not page[-1].ok and "ответ не PDF" in page[-1].note
    alien = probe.probe_issuer_docs(FakeGetter(overrides=DOCS), cfg=cfg, pdf="https://files.example.org/x.pdf")
    assert not alien[-1].ok and "не на хосте эмитента" in alien[-1].note
    dead = FakeGetter(overrides={"/press-releases/": http.FetchError("x", 503, "HTTP 503"),
                                 "getFolderTree": http.FetchError("x", 503, "HTTP 503")})
    rows = probe.probe_issuer_docs(dead, cfg=cfg, state=tmp_path / "нет")
    assert not any(r.ok for r in rows) and "--pdf" in rows[-1].note and rows[0].status == "503"


def test_the_probe_names_a_failure_instead_of_falling(probe):
    from tests.support_ind import FakeGetter
    from indicators import http

    getter = FakeGetter(overrides={"iss.moex.com": http.FetchError("https://iss.moex.com/x", 503, "HTTP 503"),
                                   "/static/documents/": http.FetchError("https://cdn.example/x.pdf", 404, "HTTP 404")})
    rows = probe.run(["iss", "issuer_docs"], getter=getter, tls=_fake_tls)
    iss_rows = [r for r in rows if r.probe == "iss"]
    assert iss_rows and all(not r.ok and r.status == "503" for r in iss_rows)
    doc = [r for r in rows if r.probe == "issuer_docs"][-1]
    assert not doc.ok and doc.status == "404", "файл не отдаётся — строка «НЕТ» с кодом, а не падение"


@pytest.mark.tact
def test_the_probe_passes_on_the_empty_state_of_a_fresh_server(monkeypatch, tmp_path, capsys):
    """Приёмка установки: проба без аргументов на пустом состоянии кончается кодом 0, когда источники
    исправны, — адрес документа эмитента берётся из только что снятого списка, и строка таблицы говорит,
    откуда он. Пробы распознавания нет: документы эмитента с текстовым слоем."""
    from tests.support_ind import FakeGetter, use_fixtures

    state = use_fixtures(monkeypatch, tmp_path, token=True)
    probe = _load("probe")
    assert not state.exists(), "состояние пусто: сборщик ничего не находил"
    rows = probe.run(getter=FakeGetter(overrides=DOCS), tls=_fake_tls)
    assert all(r.ok for r in rows), [(r.probe, r.what, r.note) for r in rows if not r.ok]
    doc = [r for r in rows if r.probe == "issuer_docs"][-1]
    assert "адрес из списка эмитента" in doc.note
    assert probe.EXTRA_PROBES == () and {"issuer_docs", "cbr_group"} <= set(probe.PROBES)
    monkeypatch.setattr(probe, "run", lambda only, pdf=None: rows)
    assert probe.main([]) == 0
    assert f"проб {len(rows)}, прошли {len(rows)}" in capsys.readouterr().out


def test_the_probe_never_prints_the_token(probe, monkeypatch, capsys):
    from tests.support_ind import FAKE_TOKEN, FakeGetter

    monkeypatch.setenv("TINVEST_TOKEN", FAKE_TOKEN)
    rows = probe.run(["tinvest"], getter=FakeGetter(), tls=_fake_tls)
    assert all(r.ok for r in rows), [r.note for r in rows]
    text = probe.table(rows) + json.dumps([r.__dict__ for r in rows], ensure_ascii=False)
    assert FAKE_TOKEN not in text


def test_the_probe_command_line(probe, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(probe, "run", lambda only, pdf=None: [
        probe.Row("iss", "котировки", "iss.moex.com/x", True, "200", 0.1, 10, "ок")])
    assert probe.main(["--only", "iss", "--json", str(tmp_path / "p.json")]) == 0
    assert "проб 1, прошли 1" in capsys.readouterr().out
    assert json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))[0]["probe"] == "iss"
    assert probe.main(["--only", "нет_такой"]) == 64
    assert probe.main(["--only", "issuer_docs", "cbr_group"]) == 0


# ------------------------------------------------------------ measure

def test_the_measure_reports_time_and_the_memory_of_the_process_tree(tmp_path, capsys):
    """Замер сборки до установки юнитов (ops/README.md §5): время, пик памяти дерева процессов — команды
    вместе с дочерними, — наибольший процесс; код возврата — код самой команды."""
    measure = _load("measure")
    child = "import time; held = bytearray(b'x') * (48 * 2**20); time.sleep(1.5)"
    parent = ("import subprocess, sys, time; held = bytearray(b'x') * (24 * 2**20); "
              f"child = subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(1.0); child.wait(); sys.exit(3)")
    out = tmp_path / "measure.json"
    code = measure.main(["--json", str(out), "--every", "0.1", "--", sys.executable, "-c", parent])
    result = json.loads(out.read_text(encoding="utf-8"))
    assert code == 3 == result["returncode"] and result["command"][-1] == parent
    assert result["peak_processes"] >= 2 and result["peak_process_mb"] >= 40
    assert result["peak_tree_mb"] >= result["peak_process_mb"] + 20, "память дерева — сумма по процессам"
    assert 1.0 <= result["seconds"] < 60 and result["memory"] in ("pss", "rss", "working_set")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("замер: ") and "пик памяти дерева" in line and line.endswith("код команды 3")
    assert measure.report({**result, "workers": "4"}).count("; BANK_WORKERS=4; код команды 3") == 1
    # дерево — процесс и все его потомки; чужие процессы в него не входят
    assert measure.tree(1, {2: 1, 3: 2, 4: 9, 9: 9}) == [1, 2, 3]
    assert measure.main(["--", "команды-с-таким-именем-нет"]) == 127
    with pytest.raises(SystemExit):
        measure.main(["--json", str(out)])


# ------------------------------------------------------------ worst_build

def test_the_worst_build_bound_completes_the_refinement_steps():
    """Оценка сверху времени сборки (ops/README.md §9): каждая строка обратного расчёта, уточнённая на полной
    полосе, — с полным числом шагов уточнения. Недостающие полосы добавляются временем одной полной полосы;
    уже посчитанные второй раз не считаются."""
    worst = _load("worst_build")
    # пять строк в диапазоне, шагов до двух — десять полос; посчитано семь (14 000 сеток по 2 000) — не хватает трёх
    assert worst.upper_bound(900.0, 5, 14000, draws=2000, refine=2, band_seconds=90.0) == pytest.approx(1170.0)
    assert worst.upper_bound(900.0, 5, 20000, draws=2000, refine=2, band_seconds=90.0) == 900.0   # все шаги сделаны
    assert worst.upper_bound(270.0, 0, 0, draws=2000, refine=2, band_seconds=90.0) == 270.0       # уточнять нечего
    payload = {"reverse_dcf": {"rows": [{"gap_basis": "full"}, {"gap_basis": "subsample"}],
                               "bank_rows": [{"key": "строка банка"}], "full_grids": 4000}}
    assert worst.refined(payload) == (2, 1, 4000) and worst.refined({}) == (0, 0, 0)   # банковские строки — не поиск
    assert worst.DEFAULT_STOPS > 1, "ближе одного стопа к медиане поиска нет: это лучший случай, а не худший"


@pytest.mark.ci_only
def test_the_worst_build_runs_in_memory_at_the_prices_near_the_median(tmp_path, monkeypatch, capsys):
    """Худший случай сборки меряется подменой цены (ops/README.md §5, шаг 8): инструмент ставит цену главного
    тикера книги рядом с медианой — выше и ниже, дальше стопа поиска — и собирает выпуск в памяти, не трогая
    состояние. Быстрая сборка проверяет сам инструмент; цену ближе одного стопа он не ставит."""
    worst = _load("worst_build")
    state = tmp_path / "state"
    monkeypatch.setenv("BANK_STATE_DIR", str(state))
    out = tmp_path / "worst.json"
    assert worst.main(["--fast", "--json", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    up, down = result["builds"]
    assert result["fast"] and result["stop"] > 0 and result["refine"] >= 1
    assert up["price"] == pytest.approx(result["median"] + worst.DEFAULT_STOPS * result["stop"], abs=1e-3)
    assert down["price"] == pytest.approx(result["median"] - worst.DEFAULT_STOPS * result["stop"], abs=1e-3)
    assert result["worst_seconds"] >= max(up["bound"], down["bound"]) >= max(up["seconds"], down["seconds"])
    assert up["reverse_rows"] == down["reverse_rows"] > 0
    assert not state.exists() or not any(state.iterdir()), "сборка в памяти: каталог состояния не тронут"
    text = capsys.readouterr().out
    assert text.count("\nцена ") == 2 and "замером худшего случая это не служит" in text
    assert worst.main(["--fast", "--stops", "1"]) == 2 and "поиска не запускает" in capsys.readouterr().err
    assert worst.main(["--fast", "--price", "0"]) == 2 and "не положительное число" in capsys.readouterr().err


# ------------------------------------------------------------ ptest

def test_the_parallel_run_splits_the_files_by_the_measured_time():
    """Делёж файлов тестов на процессы (ops/tools/ptest.py): каждый файл — ровно в одном процессе, самый долгий
    файл — в самом свободном, файл без замера получает медиану замеренных; от порядка входа делёж не зависит."""
    ptest = _load("ptest")
    files = [f"tests/test_{c}.py" for c in "abcdefg"]
    durations = {files[0]: {"rest": 100.0, "tact": 5.0}, files[1]: {"rest": 60.0}, files[2]: {"rest": 50.0},
                 files[3]: {"rest": 10.0, "tact": 90.0}, files[4]: {"rest": 10.0}, files[5]: {"rest": 0.0, "tact": 3.0}}
    weight = ptest.weights(files, durations, with_tact=False)
    assert weight[files[6]] == 30.0 and weight[files[3]] == 10.0, "новый файл — медиана; такт в весе «остального» не идёт"
    shards = ptest.split(files, weight, 3)
    assert shards == [[files[0]], [files[1], files[3], files[4]], [files[2], files[5], files[6]]]
    assert ptest.split(list(reversed(files)), weight, 3) == shards
    # без -j процессов берётся не больше, чем нужно, чтобы часть шла не дольше своего самого долгого файла
    assert ptest.enough(files, weight, 7) == 3 and ptest.enough(files, weight, 2) == 2
    assert ptest.enough(files[:1], weight, 7) == 1 and ptest.enough(files, dict.fromkeys(files, 1.0), 4) == 4
    whole = ptest.weights(files, durations, with_tact=True)
    assert whole[files[3]] == 100.0 and whole[files[6]] == 55.0, "целевой прогон гоняет и тесты такта файла"
    assert ptest.split(files[:2], weight, 7) == [[files[0]], [files[1]]], "пустых процессов нет"
    assert ptest.weights(files[:2], {}, with_tact=False) == {files[0]: 1.0, files[1]: 1.0}
    assert weight[files[5]] == ptest.LEAST and ptest.split(files[:3], dict.fromkeys(files, 0.0), 3) == [
        [files[0]], [files[1]], [files[2]]], "файлы без веса расходятся по процессам, а не ложатся в один"


def test_the_parallel_run_follows_the_parts_of_ci():
    """Весь набор идёт теми же частями, что в CI: «остальное» — процессами, файлы со своим пулом (полная полоса,
    тест мутаций) — по одному, файл с часами — без соседей, набор сервера — одним процессом и последним.
    Каждый файл тестов стоит ровно в одном процессе; выражения отбора — те, что собирает шаг CI."""
    ptest = _load("ptest")
    from tests.test_ops_tact_suite import tact_expression

    files = ptest.test_files()
    assert files == sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py"))
    parts = ptest.classify(files)
    assert sorted(parts["rest"] + parts["pools"] + parts["clocks"]) == files
    assert ptest.MUTATION_FILE in parts["pools"] and "tests/test_core_speed.py" in parts["clocks"]
    fixture = "parallel" + "_band"        # без самого слова: иначе этот файл сам числился бы файлом со своим пулом
    band = [name for name in files if fixture in (ROOT / name).read_text(encoding="utf-8")]
    assert band and set(band) <= set(parts["pools"]), "полная полоса пулом — без соседей"
    assert "tests/test_ops_tools.py" in parts["rest"]
    tact, full = tact_expression(), "not network and not archive"
    assert (ptest.tact_expression(), ptest.default_expression()) == (tact, full)
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'rest="' + ptest.rest_expression(full, "$tact") + '"' in ci and 'rest="$rest and not deadline"' in ci
    # файлы из списка `alone` замеров (тест упёрся в потолок времени под соседями) идут без соседей, как файлы с пулом
    alone = ptest.load_alone()
    parts = ptest.classify(files, alone=alone)
    assert set(alone) <= set(parts["pools"]) and sorted(parts["rest"] + parts["pools"] + parts["clocks"]) == files
    assert ptest.classify(files[:3], alone=files[:1])["pools"][:1] == files[:1]
    mode, steps, census = ptest.plan(workers=3)
    assert mode == "full" and census == [(full, [], [])], "весь набор — один сбор полного отбора по всему каталогу тестов"
    assert [job.part for job in steps[0]] == ["rest"] * 3 and all(len(step) == 1 for step in steps[1:])
    assert [step[0].part for step in steps[1:]] == ["pools"] * len(parts["pools"]) + ["clocks", "tact"]
    assert [step[0].files for step in steps[1:-2]] == [[name] for name in parts["pools"]]
    assert all(job.expression == f"{full} and not ({tact})" for step in steps[:-1] for job in step)
    assert (steps[-1][0].files, steps[-1][0].expression) == ([], f"({tact})")
    assert sorted(name for step in steps[:-1] for job in step for name in job.files) == files
    labels = [job.label for step in steps for job in step]
    assert len(set(labels)) == len(labels), "метка процесса — имя его каталога временных файлов и журнала"
    # «в будущем» — без тестов сроков, как в CI; пропуск теста мутаций; целевой прогон — отбор pytest.ini, без такта
    _, steps, census = ptest.plan(workers=2, future=True)
    assert steps[0][0].expression == f"{full} and not ({tact}) and not deadline"
    assert census == [(f"{full} and not deadline", [], [])]
    # весь набор с пропущенной частью сверяется со сбором ОСТАВШИХСЯ частей: «остальное» — по всему каталогу тестов
    # без файлов пропущенных частей (тест в файле вне частей остаётся в составе — и будет назван потерянным), такт —
    # сбором набора сервера
    rest = f"{full} and not ({tact})"
    _, steps, census = ptest.plan(workers=2, skip={"mutations", "tact"})
    assert not [job for step in steps for job in step if ptest.MUTATION_FILE in job.files or job.part == "tact"]
    assert census == [(rest, [], [ptest.MUTATION_FILE])]
    _, steps, census = ptest.plan(workers=2, skip={"mutations"})
    assert census == [(rest, [], [ptest.MUTATION_FILE]), (f"({tact})", [], [])]
    _, steps, census = ptest.plan(workers=2, skip={"rest", "pools", "clocks"})
    assert [job.part for step in steps for job in step] == ["tact"]
    assert census == [(rest, [], files), (f"({tact})", [], [])], "файлы всех пропущенных частей — вне состава"
    _, steps, census = ptest.plan(workers=2, skip={"clocks"})
    assert census[0] == (rest, [], parts["clocks"]) and len(census) == 2
    _, steps, census = ptest.plan(workers=2, skip={"mutations"}, patterns=["tests/test_core_mutations.py",
                                                                           "tests/test_core_paths.py"])
    assert census == [(full, ["tests/test_core_paths.py"], [])], "целевой прогон сверяет состав вошедших файлов"
    mode, steps, census = ptest.plan(workers=2, patterns=["tests/test_ops_tact*.py", "tests/test_core_speed.py"])
    named = ["tests/test_core_speed.py", "tests/test_ops_tact.py", "tests/test_ops_tact_suite.py"]
    assert mode == "files" and census == [(full, named, [])]
    assert [(job.part, job.expression) for step in steps for job in step] == [("rest", full)] * 2 + [("clocks", full)]
    with pytest.raises(ptest.Refused, match="нет файла тестов"):
        ptest.plan(workers=2, patterns=["tests/test_нет_такого.py"])
    _, steps, _ = ptest.plan()
    assert 1 <= len(steps[0]) <= ptest.default_workers() <= 7, "без -j — по ядрам, но не больше нужного"


JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_ok" time="1.5" />
<testcase classname="tests.test_a" name="test_bad" time="0.5"><failure message="x">текст</failure></testcase>
<testcase classname="tests.test_a.TestC" name="test_err[1]" time="0.25"><error message="x">текст</error></testcase>
<testcase classname="tests.test_b" name="test_skip" time="0"><skipped type="pytest.skip" message="m">s</skipped></testcase>
<testcase classname="tests.test_b" name="test_xfail" time="0"><skipped type="pytest.xfail" message="m" /></testcase>
<testcase classname="tests.test_b" name="test_two" time="0.5"><failure message="x" /></testcase>
<testcase classname="tests.test_b" name="test_two" time="0.25"><error message="разбор" /></testcase>
<testcase classname="tests.test_b.TestD" name="test_cap[a]" time="0"><failure message="subprocess.TimeoutExpired: Command x timed out after 300 seconds">    def test_cap(self, a):
&gt;       subprocess.run(x, timeout=300)

tests\\test_b.py:7:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
E           subprocess.TimeoutExpired: Command x timed out after 300 seconds

C:\\Python312\\Lib\\subprocess.py:1593: TimeoutExpired</failure></testcase>
<testcase classname="tests.test_b" name="test_fixture" time="0"><error message="failed on setup with &quot;subprocess.TimeoutExpired: Command y timed out after 300 seconds&quot;">E       subprocess.TimeoutExpired: Command y timed out after 300 seconds

tests\\test_b.py:12: TimeoutExpired</error></testcase>
<testcase classname="tests.test_b" name="test_worded" time="0"><failure message="AssertionError: сосед стёр мой файл (это не subprocess.TimeoutExpired: Command x timed out, а гонка)&#10;assert False">E       AssertionError: сосед стёр мой файл (это не subprocess.TimeoutExpired: Command x timed out, а гонка)
E       assert False

tests\\test_b.py:16: AssertionError</failure></testcase>
<testcase classname="tests.test_b" name="test_headed" time="0"><failure message="subprocess.TimeoutExpired: Command z timed out after 300 seconds">E       AssertionError: subprocess.TimeoutExpired: Command z timed out after 300 seconds

tests\\test_b.py:20: AssertionError</failure></testcase>
<testcase classname="tests.test_b" name="test_wrapped" time="0"><failure message="RuntimeError: обёртка: Command x timed out after 300 seconds">E           subprocess.TimeoutExpired: Command x timed out after 300 seconds
E           RuntimeError: обёртка: Command x timed out after 300 seconds

tests\\test_b.py:26: RuntimeError</failure></testcase>
</testsuite></testsuites>
"""


def test_the_parallel_run_reads_the_outcome_of_every_test(tmp_path):
    """Итог процесса — junit-файл pytest: исход каждого теста (у теста с провалом и ошибкой разбора — тяжёлый) и
    время файла. Сводный итог: тест в двух процессах, тест, потерянный против сбора, и лишний — провал прогона.
    Провал по потолку времени подпроцесса узнаётся по типу исключения в записи junit, а не по слову в тексте."""
    ptest = _load("ptest")
    path = tmp_path / "junit.xml"
    path.write_text(JUNIT, encoding="utf-8")
    tests, times, capped = ptest.read_junit(path)
    assert tests == {"tests.test_a::test_ok": "passed", "tests.test_a::test_bad": "failed",
                     "tests.test_a.TestC::test_err[1]": "error", "tests.test_b::test_skip": "skipped",
                     "tests.test_b::test_xfail": "xfailed", "tests.test_b::test_two": "error",
                     "tests.test_b.TestD::test_cap[a]": "failed", "tests.test_b::test_fixture": "error",
                     "tests.test_b::test_worded": "failed", "tests.test_b::test_headed": "failed",
                     "tests.test_b::test_wrapped": "failed"}
    assert times == {"tests/test_a.py": 2.25, "tests/test_b.py": 0.75}
    # на повтор без соседей — только провал с ТИПОМ исключения потолка времени подпроцесса (в теле теста и в его
    # подготовке): голова сообщения и последняя строка трассы сразу. Утверждение со словом в сообщении, сообщение,
    # начатое с имени класса, и обёртка над потолком повтора не получают
    assert capped == {"tests.test_b.TestD::test_cap[a]", "tests.test_b::test_fixture"}
    assert "--tb=long" in ptest.command(ptest.Job("rest", "rest-1", [], "x"), tmp_path, tmp_path / "t"), (
        "тип исключения читается по последней строке трассы: её стиль закреплён")
    assert ptest.address("tests.test_b.TestD::test_cap[a]") == "tests/test_b.py::TestD::test_cap[a]"
    assert all(ptest.junit_id(ptest.address(ident)) == ident for ident in tests)
    assert ptest.junit_id("tests/test_a.py::TestC::test_err[1]") == "tests.test_a.TestC::test_err[1]"
    assert ptest.junit_id("tests/test_b.py::test_p[a::b/c.py]") == "tests.test_b::test_p[a::b/c.py]"
    collected = "tests/test_a.py::test_ok\ntests/test_a.py::TestC::test_err[1]\n\n2 tests collected in 0.10s\n"
    assert ptest.read_collected(collected) == {"tests.test_a::test_ok", "tests.test_a.TestC::test_err[1]"}
    green = ptest.Job("rest", "rest-1", ["tests/test_a.py"], "x", returncode=0, tests={"tests.test_a::test_ok": "passed"})
    other = ptest.Job("tact", "tact", [], "(x)", returncode=0, tests={"tests.test_c::test_ok": "skipped"})
    expected = {"tests.test_a::test_ok", "tests.test_c::test_ok"}
    result = ptest.summary([green, other], {"rest": 2.0, "tact": 1.0}, workers=2, total=3.0, mode="full", expected=expected)
    assert ptest.verdict(result) == 0 and result["counts"]["passed"] == 1 and result["collected"] == 2
    line = ptest.final_line(result)
    assert line.startswith("итог: 1 passed, 1 skipped; тестов 2 за 3 с (процессов 2; остальное 2 с, такт 1 с)")
    assert line.endswith("состав равен сбору (2)")
    # тест в двух процессах; потерянный и лишний против сбора; упавший; процесс без итога — каждый краснит прогон
    twice = ptest.summary([green, green], {}, workers=1, total=1.0, mode="files", expected={"tests.test_a::test_ok"})
    assert twice["twice"] == ["tests.test_a::test_ok"] and ptest.verdict(twice) == 1
    lost = ptest.summary([green], {}, workers=1, total=1.0, mode="full", expected=expected | {"tests.test_d::test_x"})
    assert lost["lost"] == ["tests.test_c::test_ok", "tests.test_d::test_x"] and ptest.verdict(lost) == 1
    extra = ptest.summary([green, other], {}, workers=1, total=1.0, mode="full", expected={"tests.test_a::test_ok"})
    assert extra["extra"] == ["tests.test_c::test_ok"] and "СОСТАВ НЕ РАВЕН СБОРУ" in ptest.final_line(extra)
    red = ptest.Job("rest", "rest-2", ["tests/test_a.py"], "x", returncode=1, tests=tests)
    failed = ptest.summary([red], {}, workers=1, total=1.0, mode="files")
    assert failed["failed"] == ["tests.test_a.TestC::test_err[1]", "tests.test_a::test_bad",
                                "tests.test_b.TestD::test_cap[a]", "tests.test_b::test_fixture", "tests.test_b::test_headed",
                                "tests.test_b::test_two", "tests.test_b::test_worded", "tests.test_b::test_wrapped"]
    assert ptest.verdict(failed) == 1 and "состав не сверялся" in ptest.final_line(failed)
    # повтор без соседей: исход повтора заменяет прежний, «дважды» не считается, а итог называет ОБА исхода
    alone = ptest.Job("rest", ptest.ALONE, ["tests/test_b.py::TestD::test_cap[a]", "tests/test_b.py::test_fixture"], "x",
                      returncode=1, again=True,
                      tests={"tests.test_b.TestD::test_cap[a]": "passed", "tests.test_b::test_fixture": "error"})
    again = ptest.summary([red, alone], {}, workers=2, total=1.0, mode="files")
    assert again["retried"] == {"tests.test_b.TestD::test_cap[a]": ["failed", "passed"],
                                "tests.test_b::test_fixture": ["error", "error"]} and again["twice"] == []
    assert again["tests"]["tests.test_b.TestD::test_cap[a]"] == "passed" and len(again["failed"]) == 7
    assert ("повторов без соседей — 2 (под соседями error, один error — 1; под соседями failed, один passed — 1)"
            in ptest.final_line(again))
    # процесс без junit-файла — сбой при ЛЮБОМ коде возврата (pytest пишет junit и при пустом отборе, код 5)
    for code in (3, 5, 0):
        silent = ptest.Job("rest", "rest-3", ["tests/test_a.py"], "x", returncode=code, note=f"нет итога pytest (код {code})")
        assert ptest.broken(silent) and ptest.verdict(ptest.summary([silent], {}, workers=1, total=1.0, mode="files")) == 1
    assert not ptest.broken(ptest.Job("rest", "rest-4", ["tests/test_a.py"], "x", returncode=5)), "пустой отбор с итогом"
    assert ptest.verdict(ptest.summary([], {}, workers=1, total=1.0, mode="files")) == 5, "пустой отбор — код pytest"
    # сверка двух итогов: файл итога и junit-файл одиночного прогона
    out = tmp_path / "summary.json"
    out.write_text(json.dumps(failed), encoding="utf-8")
    assert ptest.compare(ptest.read_result(out), ptest.read_result(path)) == []
    assert ptest.main(["--compare", str(out), str(path)]) == 0
    assert ptest.compare({"a": "passed", "b": "passed"}, {"a": "failed", "c": "passed"}) == [
        "только в первом: b (passed)", "только во втором: c (passed)", "исход passed против failed: a"]
    other_out = tmp_path / "other.json"
    other_out.write_text(json.dumps(result), encoding="utf-8")
    assert ptest.main(["--compare", str(out), str(other_out)]) == 1
    assert ptest.main(["--skip", "нет_такой_части"]) == 2 and ptest.main(["-j", "0"]) == 2
    assert ptest.main(["--no-collect", "tests/test_ops_tools.py"]) == 2, "ключа, выключающего сверку состава, нет"
    assert ptest.main(["--save-durations", "tests/test_ops_tools.py"]) == 2, "замеры — только со всего набора"
    # журналы старых прогонов стираются, но каталог моложе суток — никогда: его прогон может ещё идти
    import os

    runs = tmp_path / "runs"
    runs.mkdir()
    now = runs.stat().st_mtime
    for i in range(8):
        (runs / f"run-{i}").mkdir()
        stamp = now - (0 if i >= 6 else 3 * 24 * 3600 - i)
        os.utime(runs / f"run-{i}", (stamp, stamp))
    ptest._prune(runs, now)
    assert sorted(p.name for p in runs.iterdir()) == [f"run-{i}" for i in range(3, 8)]
    for i in range(8, 16):
        (runs / f"run-{i}").mkdir()
    ptest._prune(runs, now)
    assert len(list(runs.iterdir())) == 10, "свежие каталоги остаются, сколько бы их ни было; старые ушли"


# Маленькое дерево для сквозного прогона: тест такта, упавший тест, тест, который в первый раз упирается в потолок
# времени подпроцесса, а во второй проходит; тест, который в первый раз падает обычным утверждением со словом потолка
# в сообщении (повтора ему не положено); параметры, пропуск, тест сети (вне отбора); файл с часами.
SMALL_TREE = {
    "pytest.ini": """[pytest]
testpaths = tests
addopts = -q -m "not network" --strict-markers
markers =
    tact: такт
    network: сеть
""",
    "ops/run.sh": 'TACT_TESTS="tact and not network"\n',
    "tests/test_one.py": """import pathlib
import subprocess

import pytest


@pytest.mark.tact
def test_fast():
    pass


def test_slow(tmp_path):
    (tmp_path / "x").write_text("x")


def test_red():
    assert 1 == 2


def test_capped():
    once = pathlib.Path("var/once.flag")
    if not once.exists():
        once.write_text("x")
        raise subprocess.TimeoutExpired("команда", 300)


def test_worded():
    once = pathlib.Path("var/worded.flag")
    if not once.exists():
        once.write_text("x")
        raise AssertionError("сосед стёр мой файл (это не subprocess.TimeoutExpired: Command x timed out, а гонка)")
""",
    "tests/test_two.py": """import pytest


@pytest.mark.parametrize("n", [1, 2])
def test_n(n):
    assert n


@pytest.mark.network
def test_net():
    raise AssertionError("сеть не ходит")


def test_skipped():
    pytest.skip("причина")
""",
    "tests/test_watch.py": """import time


def test_clock():
    assert time.ЧАСЫ() > 0
""",
}


@pytest.mark.ci_only
def test_the_parallel_run_end_to_end_on_a_small_tree(tmp_path, monkeypatch):
    """Прогон на маленьком дереве: два процесса «остального», повтор без соседей теста, упавшего по потолку времени
    подпроцесса (и только его: утверждение со словом потолка в сообщении остаётся провалом), файл с часами отдельно,
    набор такта последним; каждый тест прошёл ровно один раз, состав равен сбору, упавший тест назван, каталоги
    временных файлов и замки стёрты, длительности файлов записаны по частям. Состав сверяется и в прогоне с
    пропущенной частью; процесс pytest без итога — сбой и при коде 5."""
    ptest = _load("ptest")
    root = tmp_path / "tree"
    (root / "var").mkdir(parents=True)
    for name, text in SMALL_TREE.items():
        (root / name).parent.mkdir(exist_ok=True)
        # слово-признак часов — не литералом: иначе этот файл сам числился бы файлом с часами
        (root / name).write_text(text.replace("ЧАСЫ", "perf_" + "counter"), encoding="utf-8")
    lines: list[str] = []
    result, jobs, run_dir = ptest.run(root=root, workers=2, say=lines.append)
    assert [(job.part, job.files) for job in jobs] == [
        ("rest", ["tests/test_one.py"]), ("rest", ["tests/test_two.py"]), ("rest", ["tests/test_one.py::test_capped"]),
        ("clocks", ["tests/test_watch.py"]), ("tact", [])]
    # тест, упавший по потолку времени подпроцесса рядом с соседями, прошёл повтором без них — и так записан; тест,
    # упавший утверждением со словом потолка в сообщении, повтора не получил и остался провалом
    assert result["retried"] == {"tests.test_one::test_capped": ["failed", "passed"]} and jobs[2].again
    assert result["tests"] == {
        "tests.test_one::test_capped": "passed",
        "tests.test_one::test_fast": "passed", "tests.test_one::test_red": "failed", "tests.test_one::test_slow": "passed",
        "tests.test_one::test_worded": "failed",
        "tests.test_two::test_n[1]": "passed", "tests.test_two::test_n[2]": "passed",
        "tests.test_two::test_skipped": "skipped", "tests.test_watch::test_clock": "passed"}
    assert result["failed"] == ["tests.test_one::test_red", "tests.test_one::test_worded"] and ptest.verdict(result) == 1
    assert "повторов без соседей — 1 (под соседями failed, один passed — 1)" in ptest.final_line(result)
    assert (result["collected"], result["lost"], result["extra"], result["twice"], result["broken"]) == (9, [], [], [], [])
    assert list(result["parts"]) == ["rest", "clocks", "tact"] and result["mode"] == "full"
    assert [job.returncode for job in jobs] == [1, 0, 0, 0, 0]
    assert sorted(p.name for p in (root / "var").iterdir()) == ["once.flag", "ptest", "worded.flag"], (
        "каталоги временных файлов процессов и их замки стёрты")
    assert sorted(p.name for p in run_dir.iterdir()) == sorted(
        ["collect.log"] + [f"{job.label}.{kind}" for job in jobs for kind in ("log", "xml")])
    assert any(line.startswith("  rest-1: 1 passed, 3 failed за ") for line in lines), lines
    assert "повтор без соседей: тестов, упавших по потолку времени подпроцесса, — 1" in lines
    saved = json.loads(ptest.save_durations(jobs, root, result["retried"]).read_text(encoding="utf-8"))
    assert set(saved["files"]) == {"tests/test_one.py", "tests/test_two.py", "tests/test_watch.py"}
    assert all(set(row) == {"rest", "tact"} for row in saved["files"].values())
    assert ptest.load_durations(root) == saved["files"]
    # файл теста, упавшего по потолку времени рядом с соседями, запомнен: дальше он идёт без соседей с самого начала
    assert saved["alone"] == ["tests/test_one.py"] == ptest.load_alone(root)
    _, steps, _ = ptest.plan(root=root, workers=2)
    assert [(job.part, job.files) for step in steps for job in step] == [
        ("rest", ["tests/test_two.py"]), ("pools", ["tests/test_one.py"]), ("clocks", ["tests/test_watch.py"]), ("tact", [])]
    assert json.loads(ptest.save_durations(jobs, root).read_text(encoding="utf-8"))["alone"] == ["tests/test_one.py"]
    # целевой прогон тех же файлов — отбор pytest.ini одним выражением, без шага такта
    result, jobs, _ = ptest.run(root=root, workers=4, patterns=["tests/test_t*.py", "tests/test_one.py"], say=lines.append)
    assert result["mode"] == "files" and [job.part for job in jobs] == ["rest", "pools"] and result["collected"] == 8
    assert result["counts"]["passed"] == 6 and result["failed"] == ["tests.test_one::test_red"] and not result["retried"]
    # весь набор с пропущенной частью сверяется со сбором оставшихся частей: файлы пропущенной части — вне состава
    # (tests/test_one.py теперь в списке alone — часть pools), остальное и такт сошлись со сбором
    result, jobs, run_dir = ptest.run(root=root, workers=2, skip={"pools"}, say=lines.append)
    assert [job.part for job in jobs] == ["rest", "clocks", "tact"] and ptest.verdict(result) == 0
    assert (result["collected"], result["lost"], result["extra"]) == (5, [], []) and sum(result["counts"].values()) == 5
    assert "состав равен сбору (5)" in ptest.final_line(result)
    assert {"collect.log", "collect-2.log"} <= {p.name for p in run_dir.iterdir()}, "сбор «остального» и сбор такта"
    # тест в файле, которого нет ни в одной части (подкаталог), потерян — провал и с пропущенной частью, и когда
    # остался один такт; раньше такой прогон печатал «состав не сверялся» и кончался кодом 0
    (root / "tests" / "sub").mkdir()
    (root / "tests" / "sub" / "test_deep.py").write_text("def test_deep():\n    assert False\n", encoding="utf-8")
    for skip, ran in (({"tact"}, 8), ({"rest", "pools", "clocks"}, 1)):
        result, _, _ = ptest.run(root=root, workers=2, skip=skip, say=lines.append)
        assert result["lost"] == ["tests.sub.test_deep::test_deep"] and ptest.verdict(result) == 1, skip
        assert sum(result["counts"].values()) == ran and result["collected"] == ran + 1, skip
        assert f"СОСТАВ НЕ РАВЕН СБОРУ ({ran + 1})" in ptest.final_line(result)
    shutil.rmtree(root / "tests" / "sub")
    # процесс pytest, умерший без итога с кодом 5 («отбор пуст»), — сбой прогона, а его тесты потеряны
    (root / "tests" / "test_exit.py").write_text(
        "import os\n\n\ndef test_exit():\n    os._exit(int(os.environ['SMALL_EXIT']))\n\n\ndef test_after():\n    pass\n",
        encoding="utf-8")
    monkeypatch.setenv("SMALL_EXIT", "5")
    result, jobs, _ = ptest.run(root=root, workers=2, patterns=["tests/test_exit.py", "tests/test_two.py"], say=lines.append)
    dead = next(job for job in jobs if job.files == ["tests/test_exit.py"])
    assert dead.returncode == 5 and not dead.tests and ptest.broken(dead)
    assert result["broken"] == [f"{dead.label}: нет итога pytest (код 5), журнал — {dead.label}.log"]
    assert result["lost"] == ["tests.test_exit::test_after", "tests.test_exit::test_exit"] and ptest.verdict(result) == 1
    assert result["counts"]["passed"] == 2 and ptest.final_line(result).startswith("итог: ПРОВАЛ — ")


def test_the_cleanup_never_removes_a_directory_locked_by_a_live_run(tmp_path):
    """Каталог временных файлов, замок которого держит живой прогон pytest (tests/conftest.py), — чужой: уборка
    инструмента не стирает ни его, ни замок, а процесс, которому каталог достался занятым, помечен сбоем. Свой
    каталог (замок свободен) стирается вместе с замком."""
    from tests import conftest

    ptest = _load("ptest")
    root = tmp_path / "tree"
    run_dir = root / "var" / "ptest" / "run-abcd"
    (root / "tests").mkdir(parents=True)
    run_dir.mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")       # свой корень: настройки рабочей копии не читаются
    (root / "tests" / "test_quiet.py").write_text("def test_quiet():\n    pass\n", encoding="utf-8")
    job = ptest.Job("rest", "rest-1", ["tests/test_quiet.py"], "not network", key="r1")
    base = ptest.basetemp_of(root, run_dir, job.key)
    assert base == root / "var" / "pytest-abcd-r1"
    (base / "песочница-соседа").mkdir(parents=True)
    lock = base.parent / (base.name + ".lock")
    with open(lock, "a+b") as held:                      # сосед: тот же замок, что ставит прогону conftest
        assert conftest._lock_file(held) is True
        assert ptest.held_by_another(base) and ptest._remove(base) is False
        assert (base / "песочница-соседа").is_dir() and lock.is_file(), "каталог и замок соседа целы"
        lines: list[str] = []
        ptest.run_jobs([job], run_dir, root=root, say=lines.append)
        assert (base / "песочница-соседа").is_dir() and lock.is_file(), "уборка после процесса чужой каталог не тронула"
        assert "занят другим прогоном" in job.note and ptest.broken(job) and "не стёрт" in lines[-1]
    assert not ptest.held_by_another(base) and ptest._remove(base) is True      # замок отпущен: каталог ничей
    assert not base.exists() and not lock.exists()
    assert ptest._remove(base) is True and not ptest.held_by_another(tmp_path / "нет-такого")


# ------------------------------------------------------------ pmut

def test_the_mutation_shards_cover_every_mutant_once():
    """Шарды мутантов по номеру в списке (ops/tools/pmut.py): N шардов вместе дают весь список, каждый мутант —
    ровно в одном; число подпроцессов по умолчанию — то же, что у теста мутаций."""
    import os

    from tests.mutations import MUTATIONS

    pmut = _load("pmut")
    for n in (1, 3, 4, 7):
        shards = [pmut.chosen(list(MUTATIONS), shard=(k, n)) for k in range(1, n + 1)]
        ids = [m.id for shard in shards for m in shard]
        assert sorted(ids) == sorted(m.id for m in MUTATIONS) and len(set(ids)) == len(ids)
        assert all(MUTATIONS.index(m) % n == k for k, shard in enumerate(shards) for m in shard)
    assert pmut.parse_shard("2/4") == (2, 4) and pmut.parse_shard(None) == (1, 1)
    for bad in ("0/4", "5/4", "x", "1/0", "1-4"):
        with pytest.raises(pmut.Refused):
            pmut.parse_shard(bad)
    assert [m.id for m in pmut.chosen(list(MUTATIONS), only=["M17", "M01"])] == ["M01", "M17"]
    with pytest.raises(pmut.Refused, match="нет мутантов"):
        pmut.chosen(list(MUTATIONS), only=["M0"])
    test = (ROOT / "tests" / "test_core_mutations.py").read_text(encoding="utf-8")
    assert "workers = max(1, min(8, (os.cpu_count() or 2) - 1))" in test
    assert pmut.default_workers() == max(1, min(8, (os.cpu_count() or 2) - 1))


def test_a_mutant_is_caught_by_the_rule_of_the_test(tmp_path, monkeypatch):
    """«Пойман» у инструмента — правило теста: упала проверка с именем без подчёркивания. Падение подготовки, сбой
    подпроцесса и потолок времени поимкой не считаются; сбой среды идёт на повтор, а не в «не пойман»."""
    from tests import conftest
    from tests import test_core_mutations as test

    pmut, ptest = _load("pmut"), _load("ptest")
    assert pmut.judged({"a": "ok", "b": "AssertionError: 1"}) == {
        "caught": True, "by": {"b": "AssertionError: 1"}, "trouble": None, "checks": 2}
    for result, retry in (({"_setup": "KeyError: x"}, False), ({"_crash": "Traceback"}, True),
                          ({pmut.TIMEOUT: "долго"}, True), ({"a": "ok"}, False)):
        row = pmut.judged(result)
        assert not row["caught"] and pmut.needs_retry(row) is retry, result
    stale = pmut.judged({"_only": "нет проверок: x", "a": "AssertionError: 1"})
    assert stale["caught"] and not pmut.needs_retry(stale), "имя из устаревшей записи поимке не мешает"
    # окружение подпроцессов проверок — то же, что ставит тестам conftest; запись теста — того же вида
    assert (pmut.STATE_ENV, pmut.DATA_REPO_ENV, pmut.TOKEN_ENV, pmut.WORKERS_ENV) == (
        conftest.STATE_ENV, conftest.DATA_REPO_ENV, conftest.TOKEN_ENV, conftest.WORKERS_ENV)
    assert (ptest.MUTATION_RECORD_ENV, pmut.TEST_SCHEMA) == (test.RECORD_ENV, test.RECORD_SCHEMA)
    # быстрый круг: прежняя проверка не упала — мутанту идёт полный набор, а не «не пойман»
    calls = []

    def checks(target, timeout, only=None):
        calls.append(only)
        return {"a": "ok"} if only else {"a": "ok", "b": "AssertionError: 1"}

    monkeypatch.setattr(pmut, "_checks", checks)
    from tests.mutations import MUTATIONS

    work = tmp_path / "мутанты"
    row = pmut.one(MUTATIONS[0], work, timeout=1.0, known=["a"])
    assert calls == [["a"], None] and row["ran"] == "all" and row["caught"] and row["by"] == {"b": "AssertionError: 1"}
    assert row["left"] == [] and (work / MUTATIONS[0].id / MUTATIONS[0].path).is_file()
    calls.clear()
    monkeypatch.setattr(pmut, "_checks", lambda target, timeout, only=None: {"a": "AssertionError: 2"})
    row = pmut.one(MUTATIONS[0], work, timeout=1.0, known=["a"])
    assert row["ran"] == ["a"] and row["caught"]


def _mutation_record(pmut, shard: str, rows: dict, core: bool = True) -> dict:
    mutants = {name: {"title": name, "path": "model/x.py", "caught": bool(by), "by": by, "trouble": None, "checks": 3,
                      "ran": "all", "left": [], "seconds": 1.0, "attempts": 1} for name, by in rows.items()}
    original = {"ok": True, "failed": {}, "trouble": None, "checks": 3, "seconds": 1.0} if core else None
    return {"schema": pmut.SCHEMA, "fingerprint": "f", "shard": shard, "workers": 2, "timeout": 300.0, "known": False,
            "seconds": 5.0, "state_left": [], "original": original, "mutants": mutants}


def test_the_mutation_records_merge_and_compare(tmp_path, monkeypatch):
    """Записи шардов сводятся в одну (все шарды, каждый мутант один раз); две записи сверяются: то же «пойман», те же
    проверки. Запись самого теста и запись «мутант → проверки» читаются тем же языком."""
    pmut = _load("pmut")
    one = _mutation_record(pmut, "1/2", {"M01": {"a": "AssertionError: 1"}, "M03": {"a": "x", "b": "y"}})
    two = _mutation_record(pmut, "2/2", {"M02": {"c": "AssertionError: 3"}}, core=False)
    whole = pmut.merge([two, one])
    assert list(whole["mutants"]) == ["M01", "M02", "M03"] and whole["shard"] == "1/1" and whole["original"]["ok"]
    assert pmut.verdict(whole, whole=True) == 0 and pmut.verdict(two, whole=True) == 1 and pmut.verdict(two) == 0
    assert pmut.final_line(whole).startswith("итог: мутантов 3, поймано 3, не поймано 0, без решения 0; подлинное ядро: "
                                             "3 проверок ok")
    for records, words in (([one], "нужны все шарды"), ([one, one], "нужны все шарды"),
                           ([one, {**two, "fingerprint": "g"}], "разных деревьев"),
                           ([one, {**two, "mutants": one["mutants"]}], "в двух шардах")):
        with pytest.raises(pmut.Refused, match=words):
            pmut.merge(records)
    assert pmut.compare(whole, pmut.merge([one, two])) == ([], [])
    # непойманный мутант, сбой среды, след в каталоге и проваленное ядро — каждый красит запись
    missed = _mutation_record(pmut, "1/1", {"M01": {}})
    assert pmut.findings(missed)["missed"] == ["M01"] and pmut.verdict(missed) == 1
    missed["mutants"]["M01"]["trouble"] = pmut.TIMEOUT + ": долго"
    assert pmut.findings(missed)["undecided"] == ["M01"] and not pmut.findings(missed)["missed"]
    dirty = _mutation_record(pmut, "1/1", {"M01": {"a": "x"}})
    dirty["mutants"]["M01"]["left"] = ["latest.json"]
    assert pmut.findings(dirty)["left"] == ["M01"] and pmut.verdict(dirty) == 1
    # сверка: другое «пойман», другой состав проверок — расхождение; другой текст — замечание
    other = _mutation_record(pmut, "1/1", {"M01": {"a": "AssertionError: 2"}, "M02": {}, "M03": {"a": "x"}})
    diffs, notes = pmut.compare(whole, other)
    assert [line.split(":")[0] for line in diffs] == ["M02", "M03"] and notes == ["M01: другой текст у проверок ['a']"]
    # строка быстрого круга сверяется среди запускавшихся проверок; шард — по общим мутантам
    quick = _mutation_record(pmut, "1/1", {"M01": {"a": "AssertionError: 1"}, "M02": {"c": "AssertionError: 3"},
                                            "M03": {"b": "y"}})
    quick["mutants"]["M03"]["ran"] = ["b"]
    assert pmut.compare(whole, quick) == ([], [])
    diffs, notes = pmut.compare(whole, one)
    assert diffs == [] and len(notes) == 1 and "сверены общие мутанты (2)" in notes[0]
    # запись теста (итог каждой проверки) и запись «мутант → проверки»
    from tests import test_core_mutations as test

    raw = tmp_path / "mutants.json"
    monkeypatch.setenv(test.RECORD_ENV, str(raw))
    test._record("original", {"a": "ok", "b": "ok", "c": "ok"})
    test._record("mutants", {"M02": {"a": "ok", "b": "ok", "c": "AssertionError: 3"},
                             "M01": {"a": "AssertionError: 1", "b": "ok", "c": "ok"},
                             "M03": {"a": "x", "b": "y", "c": "ok"}})
    record = pmut.read_record(raw)
    assert list(record["mutants"]) == ["M01", "M02", "M03"] and record["original"]["ok"] and pmut.verdict(record, whole=True) == 0
    assert pmut.compare(whole, record)[0] == []
    known = pmut.known_of(record)
    assert known["mutants"] == {"M01": ["a"], "M02": ["c"], "M03": ["a", "b"]} and known["schema"] == pmut.KNOWN_SCHEMA
    stored = tmp_path / "known.json"
    stored.write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")
    back = pmut.read_record(stored)
    assert {name: sorted(row["by"]) for name, row in back["mutants"].items()} == known["mutants"]
    assert pmut.compare(whole, back)[0] == [] and pmut.main(["--compare", str(raw), str(stored)]) == 0
    monkeypatch.delenv(test.RECORD_ENV)
    test._record("original", {"a": "не пишется"})
    assert json.loads(raw.read_text(encoding="utf-8"))["original"] == {"a": "ok", "b": "ok", "c": "ok"}
    stored.write_text("{}", encoding="utf-8")
    assert pmut.main(["--compare", str(raw), str(stored)]) == 2 and pmut.main(["--shard", "5/4"]) == 2


def test_the_mutation_record_carries_the_fingerprint_of_the_tree_at_the_run(tmp_path, monkeypatch, capsys):
    """Запись мутаций несёт отпечаток дерева на момент ПРОГОНА, а не чтения: тест ставит его, когда пишет запись,
    инструмент — до первого мутанта; при чтении отпечаток не досчитывается. В отпечаток входят ядро, набор мутаций,
    опоры и фикстуры проверок. Быстрый круг сверяет отпечаток записи поимок с деревом и говорит о расхождении; запись
    поимок несёт отпечаток записи, из которой сделана, а не дерева в день сохранения."""
    from tests import test_core_mutations as test
    from tests.mutations import MUTATIONS

    pmut = _load("pmut")
    root = tmp_path / "tree"
    files = {"model/x.py": "a = 1\n", "tests/mutations.py": "", "tests/support_core.py": "", "tests/fixtures/core/book.json": "{}",
             "tests/fixtures/core_t/facts/f.json": "{}", "tests/fixtures/ind/x.json": "{}", "model/__pycache__/x.pyc": "кэш"}
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    seen = [pmut.fingerprint(root)]
    for name in ("tests/fixtures/ind/x.json", "model/__pycache__/x.pyc"):      # чужая фикстура и кэш байт-кода — не в счёт
        (root / name).write_text("изменено", encoding="utf-8")
        assert pmut.fingerprint(root) == seen[0], name
    for name in ("model/x.py", "tests/mutations.py", "tests/support_core.py", "tests/fixtures/core/book.json",
                 "tests/fixtures/core_t/facts/f.json"):
        (root / name).write_text("изменено", encoding="utf-8")
        seen.append(pmut.fingerprint(root))
    assert len(set(seen)) == len(seen), "каждый файл ядра, набора, опор и фикстур проверок меняет отпечаток"
    # запись теста: отпечаток дерева ставит сам тест в момент прогона
    tree = pmut.fingerprint()
    raw = tmp_path / "mutants.json"
    monkeypatch.setenv(test.RECORD_ENV, str(raw))
    test._record("original", {"a": "ok"})
    test._record("mutants", {"M01": {"a": "AssertionError: 1"}})
    stored = json.loads(raw.read_text(encoding="utf-8"))
    assert stored["fingerprint"] == tree and set(stored) == {"schema", "fingerprint", "original", "mutants"}
    assert pmut.read_record(raw)["fingerprint"] == tree == pmut.read_record(raw, root)["fingerprint"]
    # запись прежней версии теста — без отпечатка: чтение его не досчитывает, на каком бы дереве её ни читали
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({k: v for k, v in stored.items() if k != "fingerprint"}), encoding="utf-8")
    assert pmut.read_record(legacy)["fingerprint"] == "" == pmut.read_record(legacy, root)["fingerprint"]
    diffs, notes = pmut.compare(pmut.read_record(raw), pmut.read_record(legacy))
    assert diffs == [] and notes == ["отпечаток дерева есть не у обеих записей: с одного ли дерева они сняты, сказать нельзя"]
    # узлы, снятые на другом дереве, не продолжаются: запись начинается заново
    raw.write_text(json.dumps(dict(stored, fingerprint="0" * 64)), encoding="utf-8")
    test._record("mutants", {"M02": {"a": "AssertionError: 2"}})
    again = json.loads(raw.read_text(encoding="utf-8"))
    assert again["fingerprint"] == tree and "original" not in again and list(again["mutants"]) == ["M02"]
    # быстрый круг: отпечаток записи поимок против дерева
    assert pmut.known_note({"fingerprint": tree}, tree) == "" and "нет отпечатка дерева" in pmut.known_note({}, tree)
    assert "снята с ДРУГОГО дерева" in pmut.known_note({"fingerprint": "0" * 64}, tree)
    monkeypatch.setattr(pmut, "test_environment", lambda state: None)
    monkeypatch.setattr(pmut, "one", lambda m, work, *, timeout, known=None: {
        "title": m.title, "path": m.path, "caught": True, "by": {"a": "x"}, "trouble": None, "checks": 1,
        "ran": sorted(known or []) or "all", "left": [], "seconds": 0.0, "attempts": 1})
    name = MUTATIONS[0].id
    lines: list[str] = []
    record = pmut.run(only=[name], known={"fingerprint": "0" * 64, "mutants": {name: {"by": {"a": ""}}}}, workers=1,
                      runs=tmp_path / "pmut", say=lines.append)
    assert record["fingerprint"] == tree and "снята с ДРУГОГО дерева" in record["known_note"]
    assert any(line.startswith("ВНИМАНИЕ: запись быстрого круга снята с ДРУГОГО дерева") for line in lines), lines
    lines.clear()
    record = pmut.run(only=[name], known={"fingerprint": tree, "mutants": {name: {"by": {"a": ""}}}}, workers=1,
                      runs=tmp_path / "pmut", say=lines.append)
    assert "known_note" not in record and "fingerprint_end" not in record and not any("ВНИМАНИЕ" in line for line in lines)
    # запись поимок несёт отпечаток ЗАПИСИ, а не дерева в день сохранения; о расхождении сказано
    monkeypatch.setattr(pmut, "ROOT", tmp_path / "repo")             # запись поимок — не в рабочую копию
    saved = tmp_path / "repo" / pmut.KNOWN
    full = _mutation_record(pmut, "1/1", {"M01": {"a": "AssertionError: 1"}})
    for stamp, words in ((tree, None), ("0" * 64, "запись снята с другого дерева"), ("", "в записи нет отпечатка дерева")):
        source = tmp_path / "full.json"
        source.write_text(json.dumps(dict(full, fingerprint=stamp)), encoding="utf-8")
        assert pmut.main(["--save-known", str(source)]) == 0
        printed = capsys.readouterr().out
        assert json.loads(saved.read_text(encoding="utf-8"))["fingerprint"] == stamp
        assert ("ВНИМАНИЕ" not in printed) if words is None else (f"ВНИМАНИЕ: {words}" in printed), printed
    # дерево, менявшееся во время прогона, названо в записи, и в запись поимок такая запись не идёт
    stamps = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(pmut, "fingerprint", lambda root=None: next(stamps))
    record = pmut.run(only=[name], workers=1, runs=tmp_path / "pmut", say=lines.append)
    assert (record["fingerprint"], record["fingerprint_end"]) == ("a" * 64, "b" * 64)
    assert any("дерево менялось во время прогона" in line for line in lines)
    saved.unlink()
    source.write_text(json.dumps(dict(full, fingerprint="a" * 64, fingerprint_end="b" * 64)), encoding="utf-8")
    assert pmut.main(["--save-known", str(source)]) == 2 and not saved.exists()
    assert "дерево менялось во время прогона" in capsys.readouterr().err


@pytest.mark.ci_only
def test_the_quick_circle_runs_the_known_checks_of_a_mutant(tmp_path):
    """Быстрый круг на настоящем мутанте: по записи ему запускается одна прежняя проверка — и ловит его; каталог
    мутанта и каталог состояния проверки не трогают. Проверки по именам — ключ `--only` набора мутаций: порядок
    прежний, имя, которого нет, — не «ok» и не поимка."""
    from tests.mutations import MUTATIONS, run_checks_in

    pmut = _load("pmut")
    assert run_checks_in(None, only=["kappa_zero_in_n", "нет_такой"]) == {
        "_only": "нет проверок: нет_такой", "kappa_zero_in_n": "ok"}
    target = next(m for m in MUTATIONS if m.id == "M06")
    known = pmut.from_known({"mutants": {target.id: ["dps_is_pool_over_issued"]}})
    lines: list[str] = []
    record = pmut.run(only=[target.id], known=known, workers=2, runs=tmp_path / "pmut", say=lines.append)
    row = record["mutants"][target.id]
    assert row["caught"] and list(row["by"]) == ["dps_is_pool_over_issued"] and row["ran"] == ["dps_is_pool_over_issued"]
    assert (row["left"], record["state_left"], row["attempts"], record["original"]) == ([], [], 1, None)
    assert record["known"] and record["fingerprint"] == pmut.fingerprint() and pmut.verdict(record) == 0
    assert not any((tmp_path / "pmut").iterdir()), "каталог прогона стёрт"
    assert any(f"{target.id}: пойман (1: dps_is_pool_over_issued)" in line for line in lines), lines


# ------------------------------------------------------------ короткий итог прогонов (PLAYBOOK §6)

def test_the_short_summary_counts_against_the_expected_file(tmp_path):
    """Счётчики прогона против `ops/expected_counts.json`: строка режима (весь набор, с пропуском частей, «в будущем»;
    целевой прогон — без ожидаемых, его состав сверен со сбором); нет файла, нет строки, «не замерено» — сверки нет, и
    это сказано словами; расхождение — «НЕ РАВНЫ ОЖИДАЕМЫМ». Заготовка дерева названа «не замерено», пока замер
    полного прогона не записал числа."""
    ptest = _load("ptest")
    assert ptest.mode_key(whole=True) == "full"
    assert ptest.mode_key(whole=True, skip={"mutations"}) == "full --skip mutations"
    assert ptest.mode_key(whole=True, skip={"tact", "clocks"}, future=True) == "full --skip clocks,tact --future"
    assert ptest.mode_key(whole=False, skip={"tact"}) is None
    (tmp_path / "ops").mkdir()
    assert ptest.expected_counts(tmp_path)[0] is None and "нет файла" in ptest.expected_counts(tmp_path)[1]
    doc = {"status": "замерено", "mutations": {"full": {"total": 3, "killed": 3, "survived": 0}},
           "tests": {"full": {"collected": 5, "passed": 4, "skipped": 1, "xfailed": 0, "failed": 0, "error": 0}}}
    (tmp_path / ptest.EXPECTED).write_text(json.dumps(doc), encoding="utf-8")
    expected, why = ptest.expected_counts(tmp_path, "tests", "full")
    assert why == "" and expected["collected"] == 5
    assert "целевой прогон" in ptest.expected_counts(tmp_path, "tests", None)[1]
    assert "нет строки «full --future»" in ptest.expected_counts(tmp_path, "tests", "full --future")[1]
    result = {"collected": 5, "counts": {"passed": 4, "xfailed": 0, "skipped": 1, "failed": 0, "error": 0}}

    def line_of(result, expected, why):
        return ptest.counts_line(ptest.counts_of(result), expected, why, title="счётчики тестов", words=ptest.COUNT_WORDS)

    line, same = line_of(result, expected, why)
    assert same and line.startswith("счётчики тестов: собрано 5 (ожидалось 5), прошло 4 (ожидалось 4), пропущено 1 ")
    assert line.endswith("равны ожидаемым")
    result["counts"].update(passed=3, skipped=2)                 # тест ушёл в пропуск: исход зелёный, счёт — нет
    line, same = line_of(result, expected, why)
    assert not same and "НЕ РАВНЫ ОЖИДАЕМЫМ" in line and "пропущено 2 (ожидалось 1)" in line
    doc["status"] = ptest.NOT_MEASURED
    (tmp_path / ptest.EXPECTED).write_text(json.dumps(doc), encoding="utf-8")
    line, same = line_of(result, *ptest.expected_counts(tmp_path, "tests", "full"))
    assert same and "сверки с ожидаемыми нет" in line and "НЕ ЗАМЕРЕНЫ" in line
    tree = json.loads((ROOT / "ops" / "expected_counts.json").read_text(encoding="utf-8"))
    assert {"full", "full --skip mutations"} <= set(tree["tests"]) and set(tree["mutations"]) == {"full"}
    assert tree["status"] != ptest.NOT_MEASURED or ptest.expected_counts(ROOT, "tests", "full")[0] is None
    assert tree["reason"], "ожидаемые счётчики меняются только правкой с причиной"


def _junit(tmp_path: Path) -> Path:
    path = tmp_path / "junit-fixture.xml"
    path.write_text(JUNIT, encoding="utf-8")
    return path


def test_the_short_summary_prints_every_failure_whole_and_the_full_log_on_trouble(tmp_path, monkeypatch, capsys):
    """Короткий итог `ptest.py`: каждый отказ — целиком (сообщение и трасса из junit), счётчики против ожидаемых и
    мутации по записи теста; полный журнал — файлом всегда, на экран — при коде не 0, при счётчиках, не равных
    ожидаемым, и по `--full`. Код возврата — вердикт тестов: сверка счётчиков его не меняет."""
    ptest = _load("ptest")
    # без ожидаемых счётчиков (нет файла), а не по файлу дерева: его статус меняется замером, тест — нет
    monkeypatch.setattr(ptest, "EXPECTED", str(tmp_path / "expected_counts.json"))
    assert ptest.read_failures(_junit(tmp_path))["tests.test_a::test_bad"] == "[failure] x\nтекст"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    junit = run_dir / "rest-1.xml"
    junit.write_text('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
                     '<testcase classname="tests.test_a" name="test_ok" time="0.1" />'
                     '<testcase classname="tests.test_a" name="test_red" time="0.1"><failure message="AssertionError: '
                     'assert 1 == 2">def test_red():\n&gt;       assert 1 == 2\nE       assert 1 == 2\n\ntests\\test_a.py:5: '
                     'AssertionError</failure></testcase></testsuite></testsuites>', encoding="utf-8")
    (run_dir / "rest-1.log").write_text("ЖУРНАЛ ПРОЦЕССА rest-1\n", encoding="utf-8")
    (run_dir / "collect.log").write_text("tests/test_a.py::test_ok\ntests/test_a.py::test_red\n", encoding="utf-8")
    (run_dir / "mutants.json").write_text(json.dumps({"mutants": {"M01": {"a": "ok", "b": "AssertionError: 1"},
                                                                  "M02": {"a": "ok", "_crash": "упал"}}}), encoding="utf-8")
    job = ptest.Job("rest", "rest-1", ["tests/test_a.py"], "x", returncode=1)
    job.tests, job.times, job.capped = ptest.read_junit(junit)
    job.failures = ptest.read_failures(junit)
    ids = {"tests.test_a::test_ok", "tests.test_a::test_red"}

    def fake_run(**kwargs):
        mode = "files" if kwargs["patterns"] else "full"
        return ptest.summary([job], {"rest": 1.0}, workers=1, total=1.0, mode=mode, expected=ids), [job], run_dir

    monkeypatch.setattr(ptest, "run", fake_run)
    assert ptest.main(["tests/test_a.py"]) == 1
    out = capsys.readouterr().out
    assert "упал: tests.test_a::test_red (failed)\n    [failure] AssertionError: assert 1 == 2\n    def test_red():" in out
    assert "    tests\\test_a.py:5: AssertionError" in out, "трасса — целиком"
    assert "сверки с ожидаемыми нет: целевой прогон" in out
    assert "мутации (запись теста в прогоне): всего 2, убито 1, выжило 1" in out
    assert "ПОЛНЫЙ ЖУРНАЛ (код 1):" in out and "ЖУРНАЛ ПРОЦЕССА rest-1" in out
    assert out.rstrip().splitlines()[-1].startswith("итог: ПРОВАЛ — ")
    full = (run_dir / ptest.FULL_LOG).read_text(encoding="utf-8")
    assert "===== collect.log =====" in full and "===== rest-1 (остальное; код 1; файлы: tests/test_a.py) =====" in full
    # зелёный прогон: полного журнала на экране нет — только файлом; --full печатает и его
    job.tests, job.failures, job.returncode = {"tests.test_a::test_ok": "passed", "tests.test_a::test_red": "passed"}, {}, 0
    assert ptest.main(["tests/test_a.py"]) == 0
    out = capsys.readouterr().out
    assert "ПОЛНЫЙ ЖУРНАЛ" not in out and "упал:" not in out and (run_dir / ptest.FULL_LOG).is_file()
    assert ptest.main(["--full", "tests/test_a.py"]) == 0 and "ПОЛНЫЙ ЖУРНАЛ (по ключу --full):" in capsys.readouterr().out
    # весь набор: счётчики не равны ожидаемым — полный журнал на экране, а код возврата — прежний вердикт тестов
    counts = {"tests": {"collected": 2, "passed": 2, "skipped": 1, "xfailed": 0, "failed": 0, "error": 0},
              "mutations": {"total": 2, "killed": 1, "survived": 1}}
    monkeypatch.setattr(ptest, "expected_counts", lambda kind="tests", key="full": (
        (counts[kind], "") if key == "full" else (None, "нет строки")))
    assert ptest.main([]) == 0
    out = capsys.readouterr().out
    assert "прошло 2 (ожидалось 2), пропущено 0 (ожидалось 1)" in out and "НЕ РАВНЫ ОЖИДАЕМЫМ" in out
    assert "мутации (запись теста в прогоне): всего 2 (ожидалось 2), убито 1 (ожидалось 1), выжило 1 (ожидалось 1)" in out
    assert "ПОЛНЫЙ ЖУРНАЛ (код 0, счётчики не равны ожидаемым):" in out


def test_the_short_summary_checks_the_names_of_the_known_failures(tmp_path, monkeypatch, capsys):
    """Упавшие сверяются с `known_failures` файла ожидаемых ПО ИМЕНАМ, а не только числом (находка В-2 проверки
    фазы 0): известный красный починен, а упал другой тест — счёт тот же, но строка счётчиков «НЕ РАВНЫ ОЖИДАЕМЫМ»,
    новый — «НОВЫЙ КРАСНЫЙ», починенный — «починен, переписать счётчики», полный журнал на экране. Известный
    красный, который шёл и не упал (и без нового красного), — тоже расхождение: код 0, а полный журнал есть.
    Известный, которого в прогоне нет, не сверяется; без списка (не замерено) — сверки имён нет, это сказано."""
    ptest = _load("ptest")
    (tmp_path / "ops").mkdir()
    doc = {"status": "замерено",
           "known_failures": {"tests/test_a.py::test_known": "ждёт книгу", "tests/test_z.py::test_far": "не в прогоне"},
           "tests": {"full": {"collected": 3, "passed": 2, "skipped": 0, "xfailed": 0, "failed": 1, "error": 0}}}
    (tmp_path / ptest.EXPECTED).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    known, why = ptest.known_failures(tmp_path)
    assert why == "" and set(known) == set(doc["known_failures"])
    expected = ptest.expected_counts(tmp_path, "tests", "full")[0]

    def result_of(**tests):
        tests = {f"tests.test_a::{name}": outcome for name, outcome in tests.items()}
        bad = sorted(k for k, v in tests.items() if v in ("failed", "error"))
        return {"collected": len(tests), "counts": ptest.count(tests), "failed": bad, "tests": tests}

    def check(result):
        names, names_same = ptest.known_names(result, known, why)
        line, same = ptest.counts_line(ptest.counts_of(result), expected, "", title="счётчики тестов",
                                       words=ptest.COUNT_WORDS, names_same=names_same)
        return line, same, names

    # как в файле: упал известный — равны, строка-пояснение с причиной; далёкий известный не в прогоне — молчит
    line, same, names = check(result_of(test_known="failed", test_ok="passed", test_new="passed"))
    assert same and line.endswith("— равны ожидаемым")
    assert names == ["известный красный: tests.test_a::test_known — ждёт книгу"]
    # подмена: известный зелёный, упал другой — числа те же, а строка НЕ РАВНЫ, оба имени названы
    line, same, names = check(result_of(test_known="passed", test_ok="passed", test_new="failed"))
    assert not same and "упало 1 (ожидалось 1)" in line
    assert line.endswith("числа равны, но упавшие не те, что в known_failures, — НЕ РАВНЫ ОЖИДАЕМЫМ "
                         f"({ptest.EXPECTED}; меняются только отдельной правкой с причиной)")
    assert names[0] == f"НОВЫЙ КРАСНЫЙ: tests.test_a::test_new — его нет в known_failures ({ptest.EXPECTED})"
    assert names[1].startswith("известный красный починен (исход passed): tests.test_a::test_known — переписать")
    assert not any("test_far" in name for name in names)
    # ошибка подготовки нового теста — тоже красный; пропуск известного — «починен» с исходом
    names, names_same = ptest.known_names(result_of(test_known="skipped", test_new="error"), known, why)
    assert not names_same and names[0].startswith("НОВЫЙ КРАСНЫЙ: tests.test_a::test_new")
    assert "починен (исход skipped)" in names[1]
    # без списка: файла нет / не замерено — сверки имён нет; при упавших это сказано
    assert ptest.known_failures(tmp_path / "нет")[0] is None
    doc["status"] = ptest.NOT_MEASURED
    (tmp_path / ptest.EXPECTED).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    none, none_why = ptest.known_failures(tmp_path)
    assert none is None and "НЕ ЗАМЕРЕНЫ" in none_why
    names, names_same = ptest.known_names(result_of(test_new="failed"), none, none_why)
    assert names_same and names == [f"имена упавших не сверены с известными красными: {none_why}"]
    assert ptest.known_names(result_of(test_new="passed"), none, none_why) == ([], True)
    # файл дерева: каждый известный красный — адрес теста pytest с причиной
    tree, tree_why = ptest.known_failures(ROOT)
    assert tree_why == "" and all("::" in name and name.startswith("tests/") and reason for name, reason in tree.items())

    # через main: весь набор по файлу ожидаемых во временном каталоге (run подменён готовым итогом)
    doc["status"] = "замерено"
    (tmp_path / ptest.EXPECTED).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ptest, "EXPECTED", str(tmp_path / ptest.EXPECTED))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "collect.log").write_text("ЖУРНАЛ СБОРА\n", encoding="utf-8")
    current = {}

    def fake_run(**kwargs):
        return dict(current, schema=ptest.SCHEMA, mode="full", workers=1, seconds=1.0, parts={"rest": 1.0}, twice=[],
                    retried={}, lost=[], extra=[], broken=[], jobs=[],
                    failures={ident: "AssertionError: x" for ident in current["failed"]}), [], run_dir

    monkeypatch.setattr(ptest, "run", fake_run)
    current.update(result_of(test_known="passed", test_ok="passed", test_new="failed"))
    assert ptest.main([]) == 1
    out = capsys.readouterr().out
    assert "упал: tests.test_a::test_new (failed)" in out and "НОВЫЙ КРАСНЫЙ: tests.test_a::test_new" in out
    assert "числа равны, но упавшие не те, что в known_failures, — НЕ РАВНЫ ОЖИДАЕМЫМ" in out
    assert "известный красный починен (исход passed): tests.test_a::test_known" in out
    assert "ПОЛНЫЙ ЖУРНАЛ (код 1, счётчики не равны ожидаемым):" in out
    # починен без нового красного: код 0 (вердикт тестов), а полный журнал есть — файл ожидаемых переписать
    current.clear()
    current.update(result_of(test_known="passed", test_ok="passed", test_new="passed"))
    assert ptest.main([]) == 0
    out = capsys.readouterr().out
    assert "починен (исход passed)" in out and "ПОЛНЫЙ ЖУРНАЛ (код 0, счётчики не равны ожидаемым):" in out
    # как в файле — «равны ожидаемым», известный назван с причиной; код — вердикт (1: красный есть)
    current.clear()
    current.update(result_of(test_known="failed", test_ok="passed", test_new="passed"))
    assert ptest.main([]) == 1
    out = capsys.readouterr().out
    assert "— равны ожидаемым" in out and "известный красный: tests.test_a::test_known — ждёт книгу" in out
    assert "НОВЫЙ КРАСНЫЙ" not in out and "ПОЛНЫЙ ЖУРНАЛ (код 1):" in out
    # целевой прогон: чисел для сверки нет, имена — сверяются
    current.update(result_of(test_known="failed", test_new="failed"))
    assert ptest.main(["tests/test_a.py"]) == 1
    out = capsys.readouterr().out
    assert "сверки с ожидаемыми нет: целевой прогон" in out and "НОВЫЙ КРАСНЫЙ: tests.test_a::test_new" in out


def test_the_plan_of_a_run_starts_nothing(capsys):
    """`ptest.py --plan`: части, процессы и файлы с весом по замерам, сборы состава — без единого процесса pytest."""
    ptest = _load("ptest")
    runs = ROOT / ptest.RUNS
    before = sorted(p.name for p in runs.iterdir()) if runs.exists() else []
    assert ptest.main(["--plan", "tests/test_ops_tools.py", "tests/test_core_mutations.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("план: целевой прогон; шагов 2")
    assert any(line.startswith("    rest-1 (~") and line.endswith("tests/test_ops_tools.py") for line in out), out
    assert any(line.startswith("    pools-1 (~") and line.endswith("tests/test_core_mutations.py") for line in out), out
    assert out[-1].startswith("  сбор состава: отбор «") and out[-1].endswith("»; файлов 2")
    after = sorted(p.name for p in runs.iterdir()) if runs.exists() else []
    assert after == before, "план не заводит каталог прогона"


def test_the_short_summary_of_mutations_and_the_honest_refusal_of_the_quick_circle(tmp_path, monkeypatch, capsys):
    """`pmut.py`: строки мутантов по одному — в полный журнал (на экран — с `--verbose`); на экране — каждый отказ
    целиком (непойманный мутант с его правкой), счётчики против ожидаемых, полный журнал при коде не 0 и при
    счётчиках, не равных ожидаемым (код — прежний вердикт). Быстрый круг без записи поимок этого дерева (нет файла,
    заготовка «не замерено») — отказ с причиной, код 2."""
    from tests.mutations import MUTATIONS

    pmut = _load("pmut")
    assert pmut.expected_counts(tmp_path)[0] is None and "нет файла" in pmut.expected_counts(tmp_path)[1]
    # дальше — без ожидаемых счётчиков (нет файла), а не по файлу дерева: его статус меняется замером, тест — нет
    monkeypatch.setattr(pmut, "EXPECTED", str(tmp_path / "expected_counts.json"))
    first, second = MUTATIONS[0], MUTATIONS[1]
    record = _mutation_record(pmut, "1/1", {first.id: {"a": "AssertionError: 1"}, second.id: {}})
    record["mutants"][second.id]["title"] = second.title

    def fake_run(**kwargs):
        kwargs["say"]("прогон: шапка")
        kwargs["progress"](f"  {first.id}: пойман")
        return record

    monkeypatch.setattr(pmut, "run", fake_run)
    out_file = tmp_path / "запись.json"
    assert pmut.main(["--json", str(out_file)]) == 1
    out = capsys.readouterr().out
    head = out.split("ПОЛНЫЙ ЖУРНАЛ")[0]
    assert "прогон: шапка" in head and f"  {first.id}: пойман" not in head, "строки мутантов — в журнал, не на экран"
    assert f"не пойман: {second.id} «{second.title}»: все проверки ok\n  правка {second.path}: «{second.find}»" in out
    assert "мутации: всего 2, убито 1, выжило 1, без решения 0 — сверки с ожидаемыми нет" in out
    assert "ПОЛНЫЙ ЖУРНАЛ (код 1)" in out and f"  {first.id}: пойман" in out.split("ПОЛНЫЙ ЖУРНАЛ")[1]
    log = out_file.with_suffix(".log").read_text(encoding="utf-8")
    assert f"  {first.id}: пойман" in log and log.rstrip().splitlines()[-1].startswith("итог: мутантов 2, поймано 1")
    # зелёная запись против ожидаемых: равны — короткий итог; не равны — полный журнал, код тот же
    record["mutants"][second.id].update(caught=True, by={"b": "AssertionError: 2"})
    monkeypatch.setattr(pmut, "expected_counts", lambda root=None, key="full": ({"total": 2, "killed": 2, "survived": 0}, ""))
    assert pmut.main(["--json", str(out_file)]) == 0
    out = capsys.readouterr().out
    assert "мутации: всего 2 (ожидалось 2), убито 2 (ожидалось 2), выжило 0 (ожидалось 0), без решения 0 — равны ожидаемым" in out
    assert "ПОЛНЫЙ ЖУРНАЛ" not in out and f"{first.id}: пойман" not in out
    assert pmut.main(["--json", str(out_file), "--verbose"]) == 0 and f"  {first.id}: пойман" in capsys.readouterr().out
    monkeypatch.setattr(pmut, "expected_counts", lambda root=None, key="full": ({"total": 3, "killed": 3, "survived": 0}, ""))
    assert pmut.main(["--json", str(out_file)]) == 0
    assert "ПОЛНЫЙ ЖУРНАЛ (код 0, счётчики не равны ожидаемым)" in capsys.readouterr().out
    # быстрый круг: нет записи поимок — отказ; заготовка без мутантов — отказ
    assert pmut.main(["--known", str(tmp_path / "нет.json")]) == 2
    assert "нет записи поимок" in capsys.readouterr().err
    empty = tmp_path / "known.json"
    empty.write_text(json.dumps({"schema": pmut.KNOWN_SCHEMA, "status": "не замерено", "fingerprint": "", "mutants": {}}),
                     encoding="utf-8")
    assert pmut.main(["--known", str(empty)]) == 2 and "пуста (не замерено)" in capsys.readouterr().err
    tree = json.loads((ROOT / pmut.KNOWN).read_text(encoding="utf-8"))
    assert tree["schema"] == pmut.KNOWN_SCHEMA
    if not tree["mutants"]:                  # до замера полного прогона мутаций на этом дереве — заготовка, отказ
        assert tree["status"] == "не замерено" and pmut.main(["--known"]) == 2
