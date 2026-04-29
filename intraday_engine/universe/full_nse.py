"""Full NSE cash universe loader."""

from __future__ import annotations

from intraday_engine.storage.paths import NSE_EQUITY_LIST_PATH, UNIVERSE_DIR
from intraday_engine.universe.custom_csv import UniverseRow, read_universe_csv

FULL_NSE_PATH = UNIVERSE_DIR / "full_nse.csv"


def load_full_nse() -> list[UniverseRow]:
    """Load the full cash universe, preferring the intraday snapshot."""
    path = FULL_NSE_PATH if FULL_NSE_PATH.exists() else NSE_EQUITY_LIST_PATH
    return read_universe_csv(path, source="full_nse")
