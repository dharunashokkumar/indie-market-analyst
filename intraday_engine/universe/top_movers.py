"""NSE top-mover fetchers used to widen scan universes."""

from __future__ import annotations

from typing import Any, Literal

from intraday_engine.data_sources.nse_direct import NseDirectSource
from intraday_engine.data_sources.settings_store import IntradaySettings
from intraday_engine.universe.custom_csv import UniverseRow, row_from_symbol

MoverBucket = Literal["top_gainers", "top_losers", "most_active_value"]

GAINERS_LOSERS_PATH = "/api/live-analysis-variations"
MOST_ACTIVE_PATH = "/api/live-analysis-most-active-securities"


def fetch_top_movers(
    *,
    limit_per_bucket: int = 20,
    settings: IntradaySettings | None = None,
) -> list[UniverseRow]:
    """Fetch NSE gainers, losers, and most-active-by-value symbols."""
    source = NseDirectSource(settings=settings)
    rows: list[UniverseRow] = []
    rows.extend(_fetch_variation_bucket(source, "gainers", "top_gainers", limit_per_bucket))
    rows.extend(_fetch_variation_bucket(source, "loosers", "top_losers", limit_per_bucket))
    rows.extend(_fetch_most_active(source, limit_per_bucket))
    return _dedupe(rows)


def _fetch_variation_bucket(
    source: NseDirectSource,
    index: str,
    bucket: MoverBucket,
    limit: int,
) -> list[UniverseRow]:
    payload = source._get_json(  # noqa: SLF001 - internal intraday NSE helper reuse.
        GAINERS_LOSERS_PATH,
        params={"index": index, "type": "allSec"},
    )
    records = _variation_records(payload)
    rows: list[UniverseRow] = []
    for raw in records[:limit]:
        row = row_from_symbol(
            str(raw.get("symbol") or ""),
            name=str(raw.get("symbol") or ""),
            series=str(raw.get("series") or "EQ"),
            source=f"nse_{bucket}",
            as_of=str(payload.get("timestamp") or ""),
        )
        if row is None:
            continue
        row["industry"] = bucket
        rows.append(row)
    return rows


def _fetch_most_active(source: NseDirectSource, limit: int) -> list[UniverseRow]:
    payload = source._get_json(  # noqa: SLF001 - internal intraday NSE helper reuse.
        MOST_ACTIVE_PATH,
        params={"index": "value"},
    )
    records = payload.get("data")
    if not isinstance(records, list):
        return []
    rows: list[UniverseRow] = []
    for raw in records[:limit]:
        if not isinstance(raw, dict):
            continue
        row = row_from_symbol(
            str(raw.get("symbol") or ""),
            name=str(raw.get("symbol") or ""),
            source="nse_most_active_value",
            as_of=str(payload.get("timestamp") or ""),
        )
        if row is None:
            continue
        row["industry"] = "most_active_value"
        rows.append(row)
    return rows


def _variation_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("allSec", "FOSec", "NIFTY"):
        bucket = payload.get(key)
        if not isinstance(bucket, dict):
            continue
        data = bucket.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    data = payload.get("data")
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _dedupe(rows: list[UniverseRow]) -> list[UniverseRow]:
    out: list[UniverseRow] = []
    seen: set[str] = set()
    for row in rows:
        symbol = row["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(row)
    return out
