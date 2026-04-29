"""ASM/GSM surveillance tagging with daily JSON cache."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from intraday_engine.data_sources.base import DataSource, SurveillanceEntry
from intraday_engine.data_sources.nse_direct import NseDirectSource
from intraday_engine.ist_clock import to_ist
from intraday_engine.storage.paths import FILTERS_DIR, ensure_intraday_dirs


class AsmGsmSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_date: str
    fetched_at: datetime
    entries: list[SurveillanceEntry] = Field(default_factory=list)


def cache_path(market_date: str | None = None) -> Path:
    ensure_intraday_dirs()
    day = market_date or to_ist().date().isoformat()
    return FILTERS_DIR / f"asm_gsm_{day}.json"


def load_cached_snapshot(market_date: str | None = None) -> AsmGsmSnapshot | None:
    path = cache_path(market_date)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AsmGsmSnapshot.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def write_snapshot(snapshot: AsmGsmSnapshot) -> AsmGsmSnapshot:
    path = cache_path(snapshot.market_date)
    payload = snapshot.model_dump(mode="json")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return snapshot


def fetch_snapshot(
    *,
    force_refresh: bool = False,
    source: DataSource | None = None,
    market_date: str | None = None,
) -> AsmGsmSnapshot:
    """Load today's surveillance snapshot, fetching from NSE when uncached."""
    day = market_date or to_ist().date().isoformat()
    if not force_refresh:
        cached = load_cached_snapshot(day)
        if cached is not None:
            return cached

    data_source = source or NseDirectSource()
    entries = data_source.fetch_asm_gsm()
    snapshot = AsmGsmSnapshot(
        market_date=day,
        fetched_at=datetime.now(UTC),
        entries=entries,
    )
    return write_snapshot(snapshot)


def tags_by_symbol(entries: list[SurveillanceEntry]) -> dict[str, list[str]]:
    tags: dict[str, list[str]] = {}
    for entry in entries:
        symbol = entry.symbol.strip().upper()
        if not symbol:
            continue
        tag = entry.list_type if not entry.stage else f"{entry.list_type}:{entry.stage}"
        tags.setdefault(symbol, [])
        if tag not in tags[symbol]:
            tags[symbol].append(tag)
    return tags


def load_tags(
    *,
    force_refresh: bool = False,
    source: DataSource | None = None,
    market_date: str | None = None,
) -> dict[str, list[str]]:
    try:
        snapshot = fetch_snapshot(
            force_refresh=force_refresh,
            source=source,
            market_date=market_date,
        )
    except Exception:
        return {}
    return tags_by_symbol(snapshot.entries)
