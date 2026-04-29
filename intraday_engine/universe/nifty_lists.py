"""Static Nifty index universe loaders."""

from __future__ import annotations

from typing import Literal

from intraday_engine.storage.paths import UNIVERSE_DIR
from intraday_engine.universe.custom_csv import UniverseRow, read_universe_csv

NiftyUniverseName = Literal["nifty50", "nifty200", "nifty500"]

NIFTY_FILES: dict[NiftyUniverseName, str] = {
    "nifty50": "nifty50.csv",
    "nifty200": "nifty200.csv",
    "nifty500": "nifty500.csv",
}

NIFTY_LABELS: dict[NiftyUniverseName, str] = {
    "nifty50": "Nifty 50",
    "nifty200": "Nifty 200",
    "nifty500": "Nifty 500",
}


def load_nifty_list(name: NiftyUniverseName) -> list[UniverseRow]:
    """Load one of the checked-in Nifty constituent CSVs."""
    path = UNIVERSE_DIR / NIFTY_FILES[name]
    return read_universe_csv(path, source=path.stem)


def nifty_path(name: NiftyUniverseName):
    return UNIVERSE_DIR / NIFTY_FILES[name]
