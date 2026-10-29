"""Конфигурация индикаторов: эмитент из книги, строки сборщиков, факты, каталог состояния.

Индикаторы не импортируют ядро (INTERFACES §5): `meta.company` книги читается
здесь напрямую через PyYAML. Всё, что называет эмитента (имя, тикеры, регномер,
строки поиска новостей, шаблоны адресов документов), приходит из книги и
`data/indicators/sources.yaml`; в коде пакета литералов эмитента нет.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOOK_PATH = ROOT / "data" / "assumptions" / "assumptions.yaml"
# Запасной путь: без машинной книги `meta.company` и подписи берутся из её
# исходника-черновика — блок эмитента в них один и тот же.
BOOK_DRAFT_PATH = ROOT / "data" / "assumptions" / "assumptions.draft.yaml"
FACTS_DIR = ROOT / "data" / "facts"
SOURCES_PATH = ROOT / "data" / "indicators" / "sources.yaml"
SEED_DIR = ROOT / "data" / "indicators" / "seed"

COMPANY_FIELDS = ("name", "tickers", "main_ticker", "cbr_regnum", "fiscal_year_end")
# Переменные окружения пакета — без префикса банка (INTERFACES §8, W1/C5): копия под
# другой банк меняет только книгу, факты и sources.yaml. Токен T-Invest — `tinvest.TOKEN_ENV`.
STATE_ENV = "BANK_STATE_DIR"
HANDOFF_ENV = "BANK_HANDOFF_DIR"


class ConfigError(ValueError):
    """Нет книги, блока эмитента или файла конфигурации."""


def state_dir() -> Path:
    """Каталог состояния: `$BANK_STATE_DIR` или `var/state` репозитория (INTERFACES §7.1)."""
    value = os.environ.get(STATE_ENV)
    return Path(value) if value else ROOT / "var" / "state"


def _read_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def book_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return BOOK_PATH if BOOK_PATH.exists() else BOOK_DRAFT_PATH


def company(path: Path | None = None) -> dict[str, Any]:
    """`meta.company` книги: {name, tickers, main_ticker, cbr_regnum, fiscal_year_end}."""
    p = book_path(path)
    if not p.exists():
        raise ConfigError(f"нет книги {p.name}: эмитент для сборщиков неизвестен")
    data = _read_yaml(p) or {}
    block = (data.get("meta") or {}).get("company")
    if not isinstance(block, dict):
        raise ConfigError(f"{p.name}: нет блока meta.company")
    missing = [k for k in COMPANY_FIELDS if block.get(k) in (None, "", [])]
    if missing:
        raise ConfigError(f"{p.name}: в meta.company нет {', '.join(missing)}")
    out = dict(block)
    out["tickers"] = [str(t) for t in block["tickers"]]
    out["main_ticker"] = str(block["main_ticker"])
    out["cbr_regnum"] = str(block["cbr_regnum"])
    if out["main_ticker"] not in out["tickers"]:
        raise ConfigError("meta.company.main_ticker не входит в tickers")
    return out


@lru_cache(maxsize=4)
def _book_cached(path: str, stamp: int) -> Any:
    return _read_yaml(Path(path)) or {}


def book_value(dotted: str, path: Path | None = None) -> Any:
    """Значение книги по точечному пути (YAML без импорта ядра); нет книги или ключа — None."""
    p = book_path(path)
    if not p.exists():
        return None
    node: Any = _book_cached(str(p), p.stat().st_mtime_ns)
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@lru_cache(maxsize=4)
def _sources_cached(path: str) -> dict[str, Any]:
    data = _read_yaml(Path(path))
    if not isinstance(data, dict):
        raise ConfigError(f"{Path(path).name}: ожидался словарь")
    return data


def sources(path: Path | None = None) -> dict[str, Any]:
    """`data/indicators/sources.yaml` — строки эмитента для сборщиков."""
    p = Path(path or SOURCES_PATH)
    if not p.exists():
        raise ConfigError(f"нет файла {p.name}")
    return _sources_cached(str(p))


def setting(dotted: str, default: Any = None, path: Path | None = None) -> Any:
    """Значение `sources.yaml` по точечному пути; нет ключа — `default`."""
    node: Any = sources(path)
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def fill(template: str, **values: Any) -> str:
    """Подстановка `{ticker}`, `{regnum}`, `{year}` … в строку из sources.yaml."""
    return str(template).format(**values)


def facts_file(name: str, facts_dir: Path | None = None) -> dict | None:
    """Файл фактов `data/facts/<name>.json` или None, если его ещё нет."""
    p = Path(facts_dir or FACTS_DIR) / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def peer_tickers(facts_dir: Path | None = None) -> list[str]:
    """Тикеры банков-аналогов из `facts/peers.json` (нет файла — пусто)."""
    data = facts_file("peers", facts_dir) or {}
    return [str(b["ticker"]) for b in data.get("banks") or [] if b.get("ticker")]


def bridge_ras_ifrs(facts_dir: Path | None = None) -> dict | None:
    """Сезонный мост прибыли РСБУ → МСФО (`facts/bridge_ras_ifrs.json`) или None."""
    return facts_file("bridge_ras_ifrs", facts_dir)


def calendar_events(facts_dir: Path | None = None) -> list[dict]:
    """События `facts/calendar.json` (нет файла — пусто)."""
    data = facts_file("calendar", facts_dir) or {}
    return list(data.get("events") or [])


def node_value(node: Any) -> Any:
    """Значение узла факта `{v, src|calc}`; не узел — как есть."""
    return node.get("v") if isinstance(node, dict) and "v" in node else node


def corporate_actions(facts_dir: Path | None = None) -> list[dict]:
    """Корпоративные события `facts/shares.json → corporate_actions` (нет файла или узла — пусто)."""
    data = facts_file("shares", facts_dir) or {}
    return [dict(a) for a in data.get("corporate_actions") or [] if isinstance(a, dict)]


def splits(facts_dir: Path | None = None) -> list[dict]:
    """Дробления из фактов: `{date, first_trade_date, factor}`. Цена биржи (и запись брокера, если он отдаёт
    размер как объявлен) пересчитывается по первому торговому дню с новой ценой, сумма на акцию из документа
    или новости — по дню дробления."""
    out = []
    for a in corporate_actions(facts_dir):
        factor, day = node_value(a.get("factor")), a.get("first_trade_date") or a.get("date")
        number = isinstance(factor, (int, float)) and not isinstance(factor, bool)
        if a.get("kind") == "split" and day and number and factor > 0:
            out.append({"date": str(a.get("date") or day)[:10], "first_trade_date": str(day)[:10],
                        "factor": float(factor)})
    return sorted(out, key=lambda a: a["first_trade_date"])


def dividend_calendar(path: Path | None = None) -> dict[str, Any]:
    """`dividends.calendar` книги и первый квартал сетки `meta.first_period` (ключ `first_period`)."""
    block = book_value("dividends.calendar", path)
    out = dict(block) if isinstance(block, dict) else {}
    first = book_value("meta.first_period", path)
    if first:
        out["first_period"] = str(first)
    return out


def closed_through(facts_dir: Path | None = None, path: Path | None = None) -> str | None:
    """Последний закрытый квартал прибыли: самая поздняя строка `facts/dividends.json → history` с решением
    не позже `meta.facts_date` книги (правило закрытого квартала, М§5.7). Нет строки или даты — None."""
    facts_date = book_value("meta.facts_date", path)
    data = facts_file("dividends", facts_dir) or {}
    if not facts_date:
        return None
    day = str(facts_date)[:10]
    closed = [str(row.get("period")) for row in data.get("history") or []
              if isinstance(row, dict) and row.get("period") and row.get("decided_date")
              and str(node_value(row.get("decided_date")))[:10] <= day]
    return max(closed) if closed else None


def register_seed(facts_dir: Path | None = None) -> list[dict]:
    """Стартовый реестр фактов `facts/dividends.json → register_seed` — записи, с которых начинает ядро
    (`model/live.py`): узлы `{v, src|calc}` развёрнуты в значения. Нет файла или узла — пусто."""
    data = facts_file("dividends", facts_dir) or {}
    return [{k: node_value(v) for k, v in rec.items()} for rec in data.get("register_seed") or []
            if isinstance(rec, dict)]


def load_seed(name: str, seed_dir: Path | None = None) -> dict | None:
    """Файл истории `data/indicators/seed/<name>.json` или None."""
    p = Path(seed_dir or SEED_DIR) / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
