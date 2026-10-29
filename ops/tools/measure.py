"""Замер времени и памяти команды вместе с её дочерними процессами.

    python ops/tools/measure.py [--json файл] [--every секунды] -- <команда …>

Запускает команду, раз в `--every` секунд (по умолчанию 1) обходит дерево её процессов и запоминает
пик суммы памяти дерева, наибольший процесс и число процессов. По окончании печатает итог одной
строкой и, с `--json`, пишет его в файл. Код возврата — код самой команды.

Память процесса: Linux — доля процесса в общих страницах (PSS, `/proc/<pid>/smaps_rollup`; нет
доступа — резидентная память RSS), Windows — рабочий набор. Сумма PSS по дереву близка к тому,
что systemd засчитывает юниту (`MemoryHigh`, `MemoryMax`); сумма RSS выше — общие страницы
рабочих процессов в ней посчитаны по разу на процесс.

Зачем: потолки юнитов (`RuntimeMaxSec`, `MemoryHigh`, `MemoryMax`) и число процессов полосы
(`BANK_WORKERS`) стоят на времени и памяти сборки выпуска. Сборка меряется руками, вне systemd —
до первого выпуска через юнит и до включения таймеров; числа ложатся в `ops/budgets.json`
(ops/README.md §5 и §9). Стандартная библиотека, без зависимостей.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MB = 2 ** 20
KB = 2 ** 10


# ------------------------------------------------------------------ Linux: /proc

def _linux_parents() -> dict[int, int]:
    """PID → PID родителя по `/proc/<pid>/stat` (имя процесса в скобках может нести пробелы)."""
    out: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue                                   # процесс кончился между обходом и чтением
        tail = stat.rsplit(")", 1)[-1].split()
        if len(tail) >= 2 and tail[1].lstrip("-").isdigit():
            out[int(entry.name)] = int(tail[1])
    return out


def _linux_memory(pid: int) -> tuple[int, str]:
    """(байты, вид): PSS из `smaps_rollup`, иначе RSS из `statm`; процесса нет — (0, «rss»)."""
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Pss:"):
                return int(line.split()[1]) * KB, "pss"
    except OSError:
        pass
    try:
        pages = int(Path(f"/proc/{pid}/statm").read_text(encoding="utf-8").split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE"), "rss"
    except (OSError, ValueError, IndexError):
        return 0, "rss"


# ------------------------------------------------------------------ Windows: Toolhelp и PSAPI

def _windows_api():
    import ctypes
    import ctypes.wintypes as wt

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wt.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel.Process32First.argtypes = [wt.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32Next.argtypes = [wt.HANDLE, ctypes.POINTER(Entry)]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(Counters), wt.DWORD]
    return ctypes, kernel, psapi, Entry, Counters


def _windows_parents() -> dict[int, int]:
    ctypes, kernel, _, Entry, _ = _windows_api()
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)              # TH32CS_SNAPPROCESS
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    out: dict[int, int] = {}
    more = kernel.Process32First(snapshot, ctypes.byref(entry))
    while more:
        out[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
        more = kernel.Process32Next(snapshot, ctypes.byref(entry))
    kernel.CloseHandle(snapshot)
    return out


def _windows_memory(pid: int) -> tuple[int, str]:
    ctypes, kernel, psapi, _, Counters = _windows_api()
    handle = kernel.OpenProcess(0x1000, False, pid)                 # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return 0, "working_set"
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    got = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    kernel.CloseHandle(handle)
    return (int(counters.WorkingSetSize) if got else 0), "working_set"


# ------------------------------------------------------------------ замер

def tree(root: int, parents: dict[int, int]) -> list[int]:
    """Процесс и все его потомки по таблице «PID → PID родителя»."""
    out, frontier = [root], {root}
    while frontier:
        frontier = {pid for pid, parent in parents.items() if parent in frontier and pid not in out}
        out += sorted(frontier)
    return out


def sample(root: int) -> tuple[list[int], str]:
    """Память процессов дерева сейчас, байты (без кончившихся), и вид меры."""
    if os.name == "nt":
        parents, memory = _windows_parents(), _windows_memory
    else:
        parents, memory = _linux_parents(), _linux_memory
    got = [memory(pid) for pid in tree(root, parents)]
    sizes = [size for size, _ in got if size]
    kinds = {kind for size, kind in got if size}
    return sizes, ("rss" if "rss" in kinds else next(iter(kinds), "rss"))


def measure(command: list[str], *, every: float = 1.0) -> dict:
    """Запускает команду и возвращает итог замера (ключи — в шапке файла и в `report`)."""
    started = time.monotonic()
    process = subprocess.Popen(command)
    peak_tree = peak_one = peak_count = 0
    kind = ""
    while True:
        sizes, seen = sample(process.pid)
        if sizes:
            kind = "rss" if "rss" in (kind, seen) else seen
            peak_tree = max(peak_tree, sum(sizes))
            peak_one = max(peak_one, max(sizes))
            peak_count = max(peak_count, len(sizes))
        try:
            process.wait(timeout=every)
            break
        except subprocess.TimeoutExpired:
            continue
    return {"command": list(command), "returncode": process.returncode,
            "seconds": round(time.monotonic() - started, 1),
            "peak_tree_mb": round(peak_tree / MB, 1), "peak_process_mb": round(peak_one / MB, 1),
            "peak_processes": peak_count, "memory": kind or None,
            "workers": os.environ.get("BANK_WORKERS") or None}


def report(result: dict) -> str:
    kinds = {"pss": "PSS", "rss": "RSS", "working_set": "рабочий набор"}
    workers = f"; BANK_WORKERS={result['workers']}" if result.get("workers") else ""
    return (f"замер: {result['seconds']:.0f} с; пик памяти дерева {result['peak_tree_mb']:.0f} МБ "
            f"({kinds.get(result['memory'], 'нет данных')}, процессов до {result['peak_processes']}), наибольший "
            f"процесс {result['peak_process_mb']:.0f} МБ{workers}; код команды {result['returncode']}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command: list[str] = []
    if "--" in argv:
        at = argv.index("--")
        argv, command = argv[:at], argv[at + 1:]
    ap = argparse.ArgumentParser(prog="measure.py", description="время и память команды с дочерними процессами",
                                 usage="measure.py [--json файл] [--every секунды] -- <команда …>")
    ap.add_argument("--json", type=Path, help="записать итог замера в файл")
    ap.add_argument("--every", type=float, default=1.0, help="шаг опроса памяти, с")
    args = ap.parse_args(argv)
    if not command:
        ap.error("нет команды: measure.py [--json файл] -- <команда …>")
    if args.every <= 0:
        ap.error("--every: шаг опроса — положительное число секунд")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        result = measure(command, every=args.every)
    except OSError as exc:
        print(f"команда не запущена: {exc}", file=sys.stderr)
        return 127
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(report(result), flush=True)
    return int(result["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
