"""Universe composition for intraday scans."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from intraday_engine.data_sources.settings_store import UniverseName
from intraday_engine.storage.paths import ROOT_DIR, UNIVERSE_DIR
from intraday_engine.universe.custom_csv import (
    CUSTOM_CSV_PATH,
    UniverseRow,
    load_custom_csv,
)
from intraday_engine.universe.fno_list import FNO_PATH, load_fno_list
from intraday_engine.universe.full_nse import FULL_NSE_PATH, load_full_nse
from intraday_engine.universe.nifty_lists import (
    NIFTY_FILES,
    load_nifty_list,
)
from intraday_engine.universe.top_movers import fetch_top_movers

UniverseSource = Literal["static_csv", "custom_csv", "local_csv"]


class UniverseSymbol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    yahoo_symbol: str
    name: str
    series: str = "EQ"
    isin: str = ""
    industry: str = ""
    source: str = ""
    as_of: str = ""


class UniverseOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UniverseName
    label: str
    description: str
    size: int
    available: bool = True
    source: UniverseSource
    static_path: str | None = None
    merge_movers_default: bool = True


class BuiltUniverse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UniverseName
    label: str
    symbols: list[UniverseSymbol] = Field(default_factory=list)
    base_count: int
    movers_count: int = 0
    total_count: int
    merge_movers: bool = True


UNIVERSE_META: dict[UniverseName, dict[str, str]] = {
    "nifty50": {
        "label": "Nifty 50",
        "description": "Large-cap Nifty 50 constituents.",
    },
    "nifty200": {
        "label": "Nifty 200",
        "description": "Nifty 200 broad large and mid-cap universe.",
    },
    "nifty500": {
        "label": "Nifty 500",
        "description": "Broad Nifty 500 cash-equity universe.",
    },
    "fno": {
        "label": "F&O list",
        "description": "NSE cash symbols with active equity derivatives eligibility.",
    },
    "full_nse": {
        "label": "Full NSE cash",
        "description": "All checked-in NSE cash-equity symbols.",
    },
    "custom_csv": {
        "label": "Custom CSV",
        "description": "User-provided CSV with at least a symbol column.",
    },
}


def list_universes() -> list[UniverseOption]:
    """Return dropdown metadata and current symbol counts."""
    return [
        _option("nifty50", UNIVERSE_DIR / NIFTY_FILES["nifty50"], "static_csv"),
        _option("nifty200", UNIVERSE_DIR / NIFTY_FILES["nifty200"], "static_csv"),
        _option("nifty500", UNIVERSE_DIR / NIFTY_FILES["nifty500"], "static_csv"),
        _option("fno", FNO_PATH, "static_csv"),
        _option("full_nse", FULL_NSE_PATH, "local_csv"),
        _option("custom_csv", CUSTOM_CSV_PATH, "custom_csv"),
    ]


def build_universe(
    name: UniverseName,
    *,
    merge_movers: bool = True,
    custom_csv_path: Path | str | None = None,
) -> BuiltUniverse:
    """Build a scan universe, always de-duplicating on NSE symbol."""
    base = _load_base_universe(name, custom_csv_path=custom_csv_path)
    base_count = len(base)
    movers: list[UniverseRow] = []
    if merge_movers:
        try:
            movers = fetch_top_movers()
        except Exception:
            movers = []

    merged = _dedupe([*base, *movers])
    meta = UNIVERSE_META[name]
    return BuiltUniverse(
        id=name,
        label=meta["label"],
        symbols=[UniverseSymbol.model_validate(row) for row in merged],
        base_count=base_count,
        movers_count=max(0, len(merged) - base_count),
        total_count=len(merged),
        merge_movers=merge_movers,
    )


def _load_base_universe(
    name: UniverseName,
    *,
    custom_csv_path: Path | str | None = None,
) -> list[UniverseRow]:
    if name in NIFTY_FILES:
        return load_nifty_list(name)  # type: ignore[arg-type]
    if name == "fno":
        return load_fno_list()
    if name == "full_nse":
        return load_full_nse()
    if name == "custom_csv":
        return load_custom_csv(custom_csv_path)
    raise ValueError(f"unknown universe: {name}")


def _option(
    name: UniverseName,
    path: Path,
    source: UniverseSource,
) -> UniverseOption:
    rows: list[UniverseRow] = []
    available = path.exists()
    if available:
        try:
            rows = _load_base_universe(name)
        except Exception:
            available = False
    meta = UNIVERSE_META[name]
    return UniverseOption(
        id=name,
        label=meta["label"],
        description=meta["description"],
        size=len(rows),
        available=available,
        source=source,
        static_path=_display_path(path),
    )


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


def _display_path(path: Path) -> str:
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)
