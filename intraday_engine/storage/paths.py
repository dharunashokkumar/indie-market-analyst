"""Centralized filesystem paths for intraday JSON storage."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "intraday"
NSE_EQUITY_LIST_PATH = ROOT_DIR / "data" / "nse_equity_list.csv"

SETTINGS_PATH = DATA_DIR / "settings.json"
SETTINGS_EXAMPLE_PATH = DATA_DIR / "settings.example.json"
UNIVERSE_DIR = DATA_DIR / "universe"
FILTERS_DIR = DATA_DIR / "filters"
CACHE_DIR = DATA_DIR / "cache"
PICKS_DIR = DATA_DIR / "picks"
REVIEWS_DIR = DATA_DIR / "reviews"
PREMARKET_DIR = DATA_DIR / "premarket"
WEEKEND_DIR = DATA_DIR / "weekend"

ALL_DIRS = (
    DATA_DIR,
    UNIVERSE_DIR,
    FILTERS_DIR,
    CACHE_DIR,
    PICKS_DIR,
    REVIEWS_DIR,
    PREMARKET_DIR,
    WEEKEND_DIR,
)


def ensure_intraday_dirs() -> None:
    for path in ALL_DIRS:
        path.mkdir(parents=True, exist_ok=True)
