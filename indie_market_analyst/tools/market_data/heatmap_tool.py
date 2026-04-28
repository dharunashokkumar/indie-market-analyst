"""Index / sector heatmap tool.

Reads the curated constituent lists from ``config/indices.yaml`` and batch-fetches
day-change percentages from yfinance. Returns a strict
``IndexHeatmapSnapshot`` so the same payload flows through chat-side tool calls
and the dashboards REST endpoint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
import yfinance as yf
from agents import function_tool

from indie_market_analyst.core.schemas import HeatmapCell, IndexHeatmapSnapshot

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "indices.yaml"


def _load_universe() -> dict[str, list[dict[str, str]]]:
    with _CONFIG_PATH.open() as fh:
        data = yaml.safe_load(fh) or {}
    return {
        "nifty50": data.get("nifty50", []),
        "banknifty": data.get("banknifty", []),
        "sectors": data.get("sectors", []),
    }


def _fetch_quotes(symbols: list[str], as_of: str) -> dict[str, HeatmapCell]:
    """Batch-fetch 2-day closes for all symbols; compute change_pct."""
    if not symbols:
        return {}
    df = yf.download(
        tickers=symbols, period="5d", interval="1d",
        progress=False, group_by="ticker", auto_adjust=False, threads=True,
    )
    out: dict[str, HeatmapCell] = {}
    for sym in symbols:
        last: float | None = None
        change_pct: float | None = None
        try:
            if len(symbols) == 1:
                closes = df["Close"].dropna()
            else:
                closes = df[sym]["Close"].dropna()
            if len(closes) >= 2:
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                change_pct = ((last - prev) / prev * 100.0) if prev else None
            elif len(closes) == 1:
                last = float(closes.iloc[-1])
        except (KeyError, IndexError, ValueError):
            last = None
            change_pct = None
        out[sym] = HeatmapCell(
            symbol=sym, name=sym, last=last, change_pct=change_pct,
            as_of_utc=as_of, source="yfinance",
        )
    return out


def _materialize(group: list[dict[str, str]], quotes: dict[str, HeatmapCell]) -> list[HeatmapCell]:
    cells: list[HeatmapCell] = []
    for item in group:
        sym = item["symbol"]
        q = quotes.get(sym)
        if q is None:
            continue
        cells.append(q.model_copy(update={"name": item.get("name", sym)}))
    return cells


def _snapshot() -> IndexHeatmapSnapshot:
    universe = _load_universe()
    as_of = datetime.now(UTC).isoformat()
    all_symbols = sorted({
        item["symbol"]
        for group in universe.values()
        for item in group
    })
    quotes = _fetch_quotes(all_symbols, as_of)
    return IndexHeatmapSnapshot(
        nifty50=_materialize(universe["nifty50"], quotes),
        banknifty=_materialize(universe["banknifty"], quotes),
        sectors=_materialize(universe["sectors"], quotes),
        as_of_utc=as_of,
        source="yfinance",
    )


@function_tool
def get_index_heatmap() -> IndexHeatmapSnapshot:
    """Snapshot Nifty50/BankNifty constituents and Nifty sectoral indices.

    Returns day-change % for each constituent and each sector index. Data
    sourced from yfinance. Safe to call from chat for end-of-day market tone.
    """
    return _snapshot()


TOOLS = [get_index_heatmap]
