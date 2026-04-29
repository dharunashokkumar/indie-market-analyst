"""Custom and generic CSV universe loading."""

from __future__ import annotations

import csv
from pathlib import Path

from intraday_engine.storage.paths import UNIVERSE_DIR

UniverseRow = dict[str, str]

CUSTOM_CSV_PATH = UNIVERSE_DIR / "custom.csv"

CSV_COLUMNS = (
    "symbol",
    "yahoo_symbol",
    "name",
    "series",
    "isin",
    "industry",
    "source",
    "as_of",
)

_ALIASES = {
    "symbol": ("symbol", "Symbol", "SYMBOL", "ticker", "Ticker", "security_symbol"),
    "yahoo_symbol": ("yahoo_symbol", "Yahoo Symbol", "yahoo", "yf_symbol"),
    "name": ("name", "Name", "Company Name", "company", "companyName"),
    "series": ("series", "Series", "SERIES"),
    "isin": ("isin", "ISIN", "ISIN Code", "isin_code"),
    "industry": ("industry", "Industry", "sector", "Sector"),
    "source": ("source", "Source"),
    "as_of": ("as_of", "As Of", "asOf", "date"),
}


def load_custom_csv(path: Path | str | None = None) -> list[UniverseRow]:
    """Load a user-provided CSV with at least a symbol-like column."""
    csv_path = Path(path) if path is not None else CUSTOM_CSV_PATH
    if not csv_path.exists():
        return []
    return read_universe_csv(csv_path, source="custom_csv")


def save_custom_csv(csv_text: str) -> int:
    """Persist and validate the user-provided custom universe CSV."""
    clean_text = csv_text.strip()
    if not clean_text:
        raise ValueError("CSV content is empty")
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_CSV_PATH.with_suffix(".tmp")
    tmp.write_text(f"{clean_text}\n", encoding="utf-8")
    rows = read_universe_csv(tmp, source="custom_csv")
    if not rows:
        tmp.unlink(missing_ok=True)
        raise ValueError("CSV must contain at least one valid symbol")
    tmp.replace(CUSTOM_CSV_PATH)
    return len(rows)


def read_universe_csv(path: Path, *, source: str | None = None) -> list[UniverseRow]:
    """Read a symbol universe CSV into normalized row dictionaries."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    out: list[UniverseRow] = []
    seen: set[str] = set()
    for raw in rows:
        symbol = _symbol(_first(raw, "symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        yahoo_symbol = _text(_first(raw, "yahoo_symbol")) or f"{symbol}.NS"
        out.append(
            {
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "name": _text(_first(raw, "name")) or symbol,
                "series": (_text(_first(raw, "series")) or "EQ").upper(),
                "isin": _text(_first(raw, "isin")).upper(),
                "industry": _text(_first(raw, "industry")),
                "source": source or _text(_first(raw, "source")) or path.stem,
                "as_of": _text(_first(raw, "as_of")),
            }
        )
    return out


def row_from_symbol(
    symbol: str,
    *,
    name: str | None = None,
    series: str = "EQ",
    isin: str = "",
    industry: str = "",
    source: str = "",
    as_of: str = "",
) -> UniverseRow | None:
    clean_symbol = _symbol(symbol)
    if not clean_symbol:
        return None
    return {
        "symbol": clean_symbol,
        "yahoo_symbol": f"{clean_symbol}.NS",
        "name": _text(name) or clean_symbol,
        "series": _text(series).upper() or "EQ",
        "isin": _text(isin).upper(),
        "industry": _text(industry),
        "source": _text(source),
        "as_of": _text(as_of),
    }


def _first(row: dict[str, str | None], field: str) -> str:
    for key in _ALIASES[field]:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _symbol(value: str | None) -> str:
    text = _text(value).upper()
    if text.endswith(".NS"):
        text = text[:-3]
    return text


def _text(value: object) -> str:
    return str(value or "").strip()
