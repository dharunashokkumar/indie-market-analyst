"""TTL-aware JSON cache for intraday candles."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from intraday_engine.data_sources.base import Candle
from intraday_engine.ist_clock import to_ist
from intraday_engine.storage.paths import CACHE_DIR, ensure_intraday_dirs

INTERVAL_TTLS_SECONDS = {
    "5m": 60,
    "15m": 180,
}


def ttl_for_interval(interval: str) -> int:
    return INTERVAL_TTLS_SECONDS.get(interval, 60)


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip().upper()).strip("_")


def cache_path(
    symbol: str,
    interval: str,
    *,
    source: str | None = None,
    lookback: str | None = None,
    day: str | None = None,
) -> Path:
    ensure_intraday_dirs()
    market_day = day or to_ist().date().isoformat()
    source_part = _safe_part(source or "default")
    lookback_part = _safe_part(lookback or "default")
    file_name = (
        f"{source_part}_{_safe_part(symbol)}_"
        f"{_safe_part(interval)}_{lookback_part}_{market_day}.json"
    )
    return CACHE_DIR / file_name


def read_cached_candles(
    symbol: str,
    interval: str,
    *,
    source: str | None = None,
    lookback: str | None = None,
    max_age_seconds: int | None = None,
) -> list[Candle] | None:
    path = cache_path(symbol, interval, source=source, lookback=lookback)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    fetched_at_raw = data.get("ts_fetched")
    if not isinstance(fetched_at_raw, str):
        return None
    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)

    ttl = max_age_seconds if max_age_seconds is not None else ttl_for_interval(interval)
    age = (datetime.now(UTC) - fetched_at.astimezone(UTC)).total_seconds()
    if age > ttl:
        return None

    rows = data.get("candles")
    if not isinstance(rows, list):
        return None
    try:
        return [Candle.model_validate(row) for row in rows]
    except ValueError:
        return None


def write_cached_candles(
    symbol: str,
    interval: str,
    candles: list[Candle],
    *,
    source: str | None = None,
    lookback: str | None = None,
) -> None:
    path = cache_path(symbol, interval, source=source, lookback=lookback)
    payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        "source": source,
        "lookback": lookback,
        "ts_fetched": datetime.now(UTC).isoformat(),
        "candles": [candle.model_dump(mode="json") for candle in candles],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
