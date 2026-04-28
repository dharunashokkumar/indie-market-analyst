"""NSE equity universe — checked-in CSV, in-memory cached."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

_CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "nse_equity_list.csv"


@lru_cache(maxsize=1)
def load_nse_universe() -> pd.DataFrame:
    df = pd.read_csv(_CSV_PATH, dtype=str).fillna("")
    df["symbol_lc"] = df["symbol"].str.lower()
    df["name_lc"] = df["name"].str.lower()
    return df


def search(q: str, limit: int = 20) -> list[dict[str, str]]:
    """Substring search over symbol and name. Symbol prefix-matches rank first."""
    df = load_nse_universe()
    q = (q or "").strip().lower()
    if not q:
        head = df.head(limit)
        return _to_rows(head)
    sym_prefix = df[df["symbol_lc"].str.startswith(q)]
    sym_contains = df[
        df["symbol_lc"].str.contains(q, regex=False)
        & ~df.index.isin(sym_prefix.index)
    ]
    name_contains = df[
        df["name_lc"].str.contains(q, regex=False)
        & ~df.index.isin(sym_prefix.index)
        & ~df.index.isin(sym_contains.index)
    ]
    out = pd.concat([sym_prefix, sym_contains, name_contains]).head(limit)
    return _to_rows(out)


def _to_rows(df: pd.DataFrame) -> list[dict[str, str]]:
    cols = ["symbol", "yahoo_symbol", "name", "series", "isin", "listed_on"]
    return df[cols].to_dict(orient="records")
