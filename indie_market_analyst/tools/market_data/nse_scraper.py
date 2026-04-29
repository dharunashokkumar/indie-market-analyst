"""NSE public endpoints. No API key required.

Respect rate limits — NSE returns 401 rapidly if cookies aren't warmed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from agents import function_tool
from pydantic import BaseModel

_BASE_URL = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _client() -> httpx.Client:
    c = httpx.Client(headers=_HEADERS, timeout=15.0, follow_redirects=True)
    # warm cookies
    try:
        c.get("https://www.nseindia.com/")
    except Exception:
        pass
    return c


def _get_json(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    c = _client()
    try:
        r = c.get(f"{_BASE_URL}{path}", params=params)
        r.raise_for_status()
        data = r.json()
    finally:
        c.close()
    return data if isinstance(data, dict) else {}


def fetch_all_indices() -> list[dict[str, Any]]:
    """Raw NSE all-indices payload rows."""
    data = _get_json("/api/allIndices")
    rows = data.get("data", [])
    return rows if isinstance(rows, list) else []


def fetch_index_constituents(index: str = "NIFTY 50") -> dict[str, Any]:
    """Raw NSE equity-stockIndices payload for an index/sector basket."""
    return _get_json("/api/equity-stockIndices", params={"index": index})


def fetch_index_chart(index: str = "NIFTY 50") -> dict[str, Any]:
    """Raw NSE intraday chart payload for an index."""
    return _get_json("/api/chart-databyindex", params={"index": index, "indices": "true"})


class IndexSnapshot(BaseModel):
    index: str
    last: float
    change: float
    pct_change: float
    as_of_utc: str
    source: str = "nseindia"


@function_tool
def get_index_snapshot(index: str = "NIFTY 50") -> IndexSnapshot:
    """Fetch a live index snapshot from NSE (e.g. ``NIFTY 50``, ``NIFTY BANK``)."""
    for row in fetch_all_indices():
        if row.get("index", "").upper() == index.upper():
            return IndexSnapshot(
                index=row["index"],
                last=float(row["last"]),
                change=float(row["variation"]),
                pct_change=float(row["percentChange"]),
                as_of_utc=datetime.now(UTC).isoformat(),
            )
    raise ValueError(f"index {index!r} not found in NSE allIndices response")


class AdvanceDecline(BaseModel):
    advances: int
    declines: int
    unchanged: int
    ratio: float
    as_of_utc: str
    source: str = "nseindia"


@function_tool
def get_advance_decline() -> AdvanceDecline:
    """Return today's NSE advance/decline breadth (uses the marketStatus endpoint)."""
    data = _get_json("/api/market-data-pre-open", params={"key": "NIFTY"})
    adv = dec = unch = 0
    for row in data.get("data", []):
        ch = row.get("metadata", {}).get("change")
        if ch is None:
            continue
        if ch > 0:
            adv += 1
        elif ch < 0:
            dec += 1
        else:
            unch += 1
    ratio = adv / dec if dec else float("inf")
    return AdvanceDecline(
        advances=adv, declines=dec, unchanged=unch, ratio=ratio,
        as_of_utc=datetime.now(UTC).isoformat(),
    )


TOOLS = [get_index_snapshot, get_advance_decline]
