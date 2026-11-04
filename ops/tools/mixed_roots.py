# -*- coding: utf-8 -*-
"""Фикстура корней прежних форм для тестов проходов ядра 7 и 8 — неподвижная точка листа вывода на книге дерева в форме
`volumes.line_link_form: mixed` (шаг приёма миров: эталон, зависящий от миров, пишет команда).

    python -B ops/tools/mixed_roots.py [--commit REF] [--out ФАЙЛ] [--check]

Тесты проходов 7 и 8 (`tests/support_core_p7.py`, `tests/test_control_pass6/7/8.py`) судят прежние формы — цепь книги
страховых К6 и смесь уровней франшизы — на книге дерева. Книга дерева несёт форму строки, и её κ и ρ — корни г/г, для
прежних форм они не годятся; поэтому тесты берут κ формы уровней и ρ квартальной цепи из фикстуры
`tests/fixtures/core_pass8/book_keys_mixed_r12.yaml` — неподвижной точки листа на этой книге с ключом формы mixed. Числа
зависят от миров ставок (рост зарплат мира M, пути баланса): при новой записи миров фикстура пишется заново этим
инструментом. Как: копия дерева коммита (`git archive`), в шаблоне копии — `volumes.line_link_form: mixed`, сухой перевывод
`ops/tools/rederive.py --dry-run --no-quick --no-classes`, из пробной книги — `opex.line_share_roots.insurance` и
`volumes.liability_driver_roots.insurance` (текстом пробной книги). Шапка файла — прежняя. `--check` — ничего не пишет,
код 1, если фикстура не равна счёту.
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adopt_worlds as A  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "core_pass8" / "book_keys_mixed_r12.yaml"
KEYS = (("opex", "line_share_roots", "insurance"), ("volumes", "liability_driver_roots", "insurance"))
LABEL = "mixed-roots"


def flow_text(text: str, path: tuple) -> str:
    """Текст узла по адресу — как в пробной книге (формат записи вывода)."""
    root = yaml.compose(text)
    node = root
    for part in path:
        node = next(v for k, v in node.value if str(k.value) == part)
    return text[node.start_mark.index:node.end_mark.index]


def compute(commit: str, workers: int) -> tuple[dict[tuple, str], str]:
    work = ROOT / "var" / f"{LABEL}-{commit.replace('/', '_')}"
    shutil.rmtree(work, ignore_errors=True)
    copy = work / "copy"
    copy.mkdir(parents=True)
    raw = subprocess.run(["git", "archive", commit, "model", "data", "ops", "pytest.ini"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        tf.extractall(copy, filter="fully_trusted")
    tpl = copy / "data" / "assumptions" / "assumptions_template.yaml"
    A.set_values(tpl, {("volumes", "line_link_form"): "mixed"})
    env = dict(os.environ, PYTHONIOENCODING="utf-8", BANK_WORKERS=str(workers))
    log = work / "rederive.txt"
    with open(log, "w", encoding="utf-8") as fh:
        rc = subprocess.run([sys.executable, "-B", "ops/tools/rederive.py", "--dry-run", "--no-quick", "--no-classes",
                             "--workers", str(workers), "--label", LABEL], cwd=copy, stdout=fh, stderr=subprocess.STDOUT,
                            env=env).returncode
    after = copy / "var" / "rederive" / LABEL / "after" / "assumptions.yaml"
    if rc != 0 or not after.exists():
        raise SystemExit(f"сухой перевывод в форме mixed остановлен (код {rc}): {log}")
    text = after.read_text(encoding="utf-8")
    book = yaml.safe_load(text)
    state = A.read_state(copy) or {}
    origin = (f"# Перезапись: ops/tools/mixed_roots.py — книга {book['meta']['version']} на мирах {state.get('version', '?')} "
              "(шаг приёма миров; что и зачем — шапка выше).")
    return {k: flow_text(text, k) for k in KEYS}, origin


def render(old: str, found: dict[tuple, str], origin: str) -> str:
    head = "".join(ln + "\n" for ln in old.split("\n") if ln.startswith("#") and not ln.startswith("# Перезапись:"))
    head += origin + "\n"
    return (head + "opex:\n  line_share_roots:\n    insurance: " + found[KEYS[0]] + "\n"
            + "volumes:\n  liability_driver_roots:\n    insurance: " + found[KEYS[1]] + "\n")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--out", type=Path, default=FIXTURE)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("BANK_WORKERS", "2")))
    a = ap.parse_args(argv)
    found, origin = compute(a.commit, a.workers)
    new = render(FIXTURE.read_text(encoding="utf-8"), found, origin)
    now = a.out.read_text(encoding="utf-8") if a.out.exists() else None
    if a.check:                                       # сверяются числа; шапка — не предмет сверки
        def data(s):
            return [ln for ln in (s or "").split("\n") if not ln.startswith("#")]
        same = data(now) == data(new)
        print("фикстура корней прежних форм — " + ("неподвижная точка листа на книге" if same else "НЕ равна счёту"))
        return 0 if same else 1
    if now != new:
        a.out.write_text(new, encoding="utf-8", newline="\n")
    print(f"{'записано' if now != new else 'без изменений'}: {a.out.relative_to(ROOT).as_posix() if a.out.is_relative_to(ROOT) else a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
