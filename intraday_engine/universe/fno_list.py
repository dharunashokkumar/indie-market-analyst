"""Static NSE F&O universe loader."""

from __future__ import annotations

from intraday_engine.storage.paths import UNIVERSE_DIR
from intraday_engine.universe.custom_csv import UniverseRow, read_universe_csv

FNO_PATH = UNIVERSE_DIR / "fno.csv"


def load_fno_list() -> list[UniverseRow]:
    """Load the checked-in F&O securities list."""
    return read_universe_csv(FNO_PATH, source="fno")
