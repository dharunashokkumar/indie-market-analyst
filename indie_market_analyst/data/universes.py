"""Predefined symbol universes for the market scanner."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .nse_universe import load_nse_universe

_INDICES_PATH = Path(__file__).resolve().parents[2] / "config" / "indices.yaml"


@lru_cache(maxsize=4)
def get_universe(name: str) -> list[dict[str, str]]:
    """Return a list of {symbol, yahoo_symbol, name} for the named universe."""
    if name == "nifty50":
        return _from_indices_yaml("nifty50")
    if name == "banknifty":
        return _from_indices_yaml("banknifty")
    if name == "all_nse":
        return _from_nse_csv(limit=None)
    if name == "top200":
        return _from_nse_csv(limit=200)
    raise ValueError(f"unknown universe: {name}")


def universe_options() -> list[dict[str, object]]:
    """Metadata for the UI dropdown."""
    return [
        {"id": "nifty50", "label": "Nifty 50", "size": len(get_universe("nifty50")),
         "eta_minutes": 2,
         "description": "The 50 biggest Indian companies. Fastest scan."},
        {"id": "banknifty", "label": "Bank Nifty", "size": len(get_universe("banknifty")),
         "eta_minutes": 1,
         "description": "12 large banks only."},
        {"id": "top200", "label": "Top 200 NSE", "size": len(get_universe("top200")),
         "eta_minutes": 7,
         "description": "First 200 NSE-listed companies. Broader coverage."},
        {"id": "all_nse", "label": "All NSE (~2,300)", "size": len(get_universe("all_nse")),
         "eta_minutes": 40,
         "description": "EVERY listed NSE company. Slow — yfinance rate-limits often kick in."},
    ]


def _from_indices_yaml(key: str) -> list[dict[str, str]]:
    with _INDICES_PATH.open() as f:
        data = yaml.safe_load(f) or {}
    rows = data.get(key, [])
    out: list[dict[str, str]] = []
    for row in rows:
        sym = row["symbol"]
        # symbols here already include .NS suffix
        bare = sym[:-3] if sym.endswith(".NS") else sym
        out.append({"symbol": bare, "yahoo_symbol": sym, "name": row.get("name", bare)})
    return out


def _from_nse_csv(limit: int | None) -> list[dict[str, str]]:
    df = load_nse_universe()
    if limit is not None:
        df = df.head(limit)
    return df[["symbol", "yahoo_symbol", "name"]].to_dict(orient="records")
