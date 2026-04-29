"""MCX India OHLCV loader backed by ``mcxlib``.

Treats every supported MCX symbol as a futures contract. The loader picks the
active near-month FUTCOM contract, auto-rolls a few business days before
expiry, and exposes contract metadata (expiry, lot/unit, open interest) so the
UI can render real futures information instead of a generic "spot" tile.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

from .registry import register


@dataclass(frozen=True)
class MCXCommodity:
    symbol: str
    commodity: str
    display_unit: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    roll_days_before_expiry: int = 2


MCX_COMMODITIES: dict[str, MCXCommodity] = {
    "GOLD": MCXCommodity("GOLD", "GOLD", "10 GRMS"),
    "GOLDM": MCXCommodity("GOLDM", "GOLDM", "10 GRMS"),
    "GOLDGUINEA": MCXCommodity("GOLDGUINEA", "GOLDGUINEA", "8 GRMS"),
    "GOLDPETAL": MCXCommodity("GOLDPETAL", "GOLDPETAL", "1 GRMS"),
    "GOLDTEN": MCXCommodity("GOLDTEN", "GOLDTEN", "10 GRMS"),
    "SILVER": MCXCommodity("SILVER", "SILVER", "1 KGS"),
    "SILVERM": MCXCommodity("SILVERM", "SILVERM", "1 KGS"),
    "SILVERMIC": MCXCommodity("SILVERMIC", "SILVERMIC", "1 KGS"),
    "COPPER": MCXCommodity("COPPER", "COPPER", "1 KGS"),
    "CRUDEOIL": MCXCommodity("CRUDEOIL", "CRUDEOIL", "1 BBL", ("CRUDE", "CRUDE OIL")),
    "CRUDEOILM": MCXCommodity("CRUDEOILM", "CRUDEOILM", "1 BBL"),
    "NATURALGAS": MCXCommodity(
        "NATURALGAS", "NATURALGAS", "1 mmBtu", ("NATGAS", "NATURAL GAS")
    ),
    "NATGASMINI": MCXCommodity("NATGASMINI", "NATGASMINI", "1 mmBtu"),
}

MCX_ALIASES: dict[str, str] = {
    alias: spec.symbol
    for spec in MCX_COMMODITIES.values()
    for alias in (spec.symbol, spec.commodity, *spec.aliases)
}

ICOMDEX_INSTRUMENT_TO_SYMBOL: dict[str, str] = {
    "MCXMCXGOLDEX": "GOLD",
    "MCXMCXSILVDEX": "SILVER",
    "MCXMCXCOPRDEX": "COPPER",
    "MCXMCXCRUDEX": "CRUDEOIL",
    "MCXMCXNGASDEX": "NATURALGAS",
    "MCXMCXBULLDEX": "BULLION",
    "MCXMCXMETLDEX": "BASE_METAL",
    "MCXMCXENRGDEX": "ENERGY",
    "MCXMCXCOMPDEX": "COMPOSITE",
}

_BHAV_COPY_CACHE: dict[str, pd.DataFrame] = {}
_BHAV_COPY_CACHE_LOCK = threading.RLock()
_BHAV_COPY_MAX_WORKERS = 4

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")
_PERIOD_RE = re.compile(r"^(?P<count>\d+)(?P<unit>d|wk|mo|y)$", re.IGNORECASE)


def _norm_token(value: Any) -> str:
    return _NON_ALNUM_RE.sub("", str(value or "")).upper()


def _norm_column(value: Any) -> str:
    return _NON_ALNUM_RE.sub("", str(value or "")).lower()


def resolve_mcx_symbol(symbol: str) -> MCXCommodity | None:
    key = _norm_token(symbol)
    canonical = MCX_ALIASES.get(key)
    return MCX_COMMODITIES.get(canonical or "")


def is_mcx_symbol(symbol: str) -> bool:
    return resolve_mcx_symbol(symbol) is not None


def _start_for_period(period: str, end: date) -> date:
    period_key = (period or "1y").strip().lower()
    if period_key == "ytd":
        return date(end.year, 1, 1)
    if period_key == "max":
        return (pd.Timestamp(end) - pd.DateOffset(years=5)).date()

    match = _PERIOD_RE.match(period_key)
    if not match:
        raise ValueError(f"unsupported MCX period: {period}")

    count = int(match.group("count"))
    unit = match.group("unit").lower()
    end_ts = pd.Timestamp(end)
    if unit == "d":
        start = end - timedelta(days=count)
    elif unit == "wk":
        start = end - timedelta(weeks=count)
    elif unit == "mo":
        start = (end_ts - pd.DateOffset(months=count)).date()
    elif unit == "y":
        start = (end_ts - pd.DateOffset(years=count)).date()
    else:
        raise ValueError(f"unsupported MCX period unit: {unit}")

    return min(start, end - timedelta(days=1))


def _find_column(
    df: pd.DataFrame,
    candidates: tuple[str, ...],
    *,
    required: bool = True,
    label: str,
) -> str | None:
    by_norm = {_norm_column(col): col for col in df.columns}
    for candidate in candidates:
        found = by_norm.get(_norm_column(candidate))
        if found is not None:
            return str(found)
    if required:
        cols = ", ".join(str(col) for col in df.columns)
        raise ValueError(f"MCX data missing {label} column. Columns: {cols}")
    return None


def _numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "--": pd.NA, "nan": pd.NA, "None": pd.NA})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _parse_mcx_dates(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    def fill(mask: pd.Series, date_format: str) -> None:
        pending = mask & parsed.isna()
        if pending.any():
            parsed.loc[pending] = pd.to_datetime(
                values.loc[pending],
                errors="coerce",
                format=date_format,
            )

    fill(values.str.match(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d")
    fill(values.str.match(r"^\d{4}/\d{2}/\d{2}$"), "%Y/%m/%d")
    fill(values.str.match(r"^\d{8}$"), "%Y%m%d")
    fill(values.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$"), "%m/%d/%Y")
    fill(values.str.match(r"^\d{1,2}[A-Za-z]{3}\d{4}$"), "%d%b%Y")
    fill(values.str.match(r"^\d{1,2} [A-Za-z]{3} \d{4}$"), "%d %b %Y")

    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            values.loc[missing],
            errors="coerce",
            format="mixed",
            dayfirst=True,
        )
    return parsed


def _filter_commodity_rows(df: pd.DataFrame, spec: MCXCommodity) -> pd.DataFrame:
    """Keep only FUTCOM rows whose Symbol exactly matches ``spec.symbol``.

    Aliases are intentionally NOT included here — they only resolve user input.
    Including them silently mixes different products (e.g. SILVER vs SILVERMIC).
    """
    commodity_col = _find_column(
        df,
        (
            "Symbol",
            "Commodity",
            "CommodityName",
            "Commodity Name",
            "Product",
            "ProductName",
            "Product Name",
        ),
        label="commodity",
    )
    target = _norm_token(spec.symbol)
    filtered = df[df[commodity_col].map(_norm_token) == target].copy()
    if filtered.empty:
        raise ValueError(f"no MCX rows found for {spec.symbol}")

    instrument_col = _find_column(
        filtered,
        ("InstrumentName", "Instrument Name", "Instrument", "InstrumentType", "Instrument Type"),
        required=False,
        label="instrument",
    )
    if instrument_col:
        inst = filtered[instrument_col].map(_norm_token)
        futures = filtered[inst.str.contains("FUT", na=False) & ~inst.str.contains("OPT", na=False)]
        if not futures.empty:
            filtered = futures.copy()

    return filtered


def _pick_near_month(
    frame: pd.DataFrame,
    *,
    today: pd.Timestamp,
    roll_days: int,
    expiry_col: str = "_expiry",
    volume_col: str = "volume",
) -> pd.Series:
    """Pick the active near-month row from ``frame``.

    Rules:
      1. Drop rows whose expiry is in the past.
      2. Sort by expiry ascending.
      3. If the soonest expiry is within ``roll_days`` business days and the
         next expiry has positive volume, roll to the next expiry.
      4. Tie-break ties on expiry by highest volume.
    """
    if expiry_col not in frame.columns:
        return frame.iloc[0]

    active = frame[frame[expiry_col].notna() & (frame[expiry_col] >= today)]
    if active.empty:
        return frame.iloc[0]

    ordered = active.sort_values(
        [expiry_col, volume_col] if volume_col in active.columns else [expiry_col],
        ascending=[True, False] if volume_col in active.columns else [True],
    )

    near = ordered.iloc[0]
    if roll_days > 0 and len(ordered) >= 2:
        days_to_expiry = (near[expiry_col] - today).days
        if days_to_expiry <= roll_days:
            next_row = ordered.iloc[1]
            next_vol = next_row.get(volume_col, 0) if volume_col in ordered.columns else 0
            if pd.notna(next_vol) and float(next_vol) > 0:
                return next_row
    return near


def _normalize_mcx_history(raw: pd.DataFrame, spec: MCXCommodity, interval: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError(f"empty MCX data for {spec.symbol}")

    frame = _filter_commodity_rows(raw.copy(), spec)

    date_col = _find_column(
        frame,
        ("Date", "TradeDate", "Trade Date", "TradingDate", "Trading Date"),
        label="date",
    )
    open_col = _find_column(frame, ("Open", "OpenPrice", "Open Price"), label="open")
    high_col = _find_column(frame, ("High", "HighPrice", "High Price"), label="high")
    low_col = _find_column(frame, ("Low", "LowPrice", "Low Price"), label="low")
    close_col = _find_column(
        frame,
        ("Close", "ClosePrice", "Close Price", "SettlementPrice", "Settlement Price"),
        label="close",
    )
    volume_col = _find_column(
        frame,
        (
            "Volume",
            "Volume(Lots)",
            "Volume Lots",
            "TradedQty",
            "Traded Qty",
            "TradedQuantity",
            "Traded Quantity",
            "NoOfContracts",
            "No Of Contracts",
        ),
        required=False,
        label="volume",
    )
    expiry_col = _find_column(
        frame,
        ("ExpiryDate", "Expiry Date", "Expiry", "ContractExpiry", "Contract Expiry"),
        required=False,
        label="expiry",
    )

    frame["_date"] = _parse_mcx_dates(frame[date_col])
    frame["_trade_day"] = frame["_date"].dt.normalize()
    frame["open"] = _numeric(frame[open_col])
    frame["high"] = _numeric(frame[high_col])
    frame["low"] = _numeric(frame[low_col])
    frame["close"] = _numeric(frame[close_col])
    frame["volume"] = _numeric(frame[volume_col]) if volume_col else 0.0

    if expiry_col:
        frame["_expiry"] = _parse_mcx_dates(frame[expiry_col]).dt.normalize()
    else:
        frame["_expiry"] = pd.NaT

    frame = frame.dropna(subset=["_trade_day", "open", "high", "low", "close"])
    if frame.empty:
        raise ValueError(f"no usable MCX OHLCV rows for {spec.symbol}")

    if frame["_expiry"].notna().any():
        rows: list[pd.Series] = []
        for trade_day, group in frame.groupby("_trade_day", sort=True):
            picked = _pick_near_month(
                group,
                today=trade_day,
                roll_days=spec.roll_days_before_expiry,
            )
            rows.append(picked)
        frame = pd.DataFrame(rows)
    else:
        # No expiry column: fall back to one row per trade day, highest volume.
        frame = (
            frame.sort_values(["_trade_day", "volume"], ascending=[True, False])
            .drop_duplicates("_trade_day", keep="first")
        )

    out = (
        frame.set_index("_trade_day")[["open", "high", "low", "close", "volume"]]
        .sort_index()
    )
    out = out[~out.index.duplicated(keep="last")]
    out.index = pd.to_datetime(out.index)

    interval_key = (interval or "1d").strip().lower()
    if interval_key in {"1d", "1day", "d", "day"}:
        result = out
    elif interval_key in {"1wk", "1w", "wk", "week", "weekly"}:
        result = out.resample("W-FRI").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        )
        result = result.dropna(subset=["open", "high", "low", "close"])
    else:
        raise ValueError("MCX loader supports daily and weekly intervals only")

    result["source"] = "mcxlib"
    return result


def _resolve_trade_date(today: date, max_lookback: int = 5) -> tuple[str, bool]:
    """Find the most recent date for which an MCX bhav copy exists.

    Returns ``(YYYY-MM-DD, estimated)`` where ``estimated`` is True only if all
    bhav copy lookups failed and we fell back to ``today``.
    """
    import mcxlib

    cursor = today
    for _ in range(max_lookback + 1):
        key = cursor.strftime("%Y%m%d")
        with _BHAV_COPY_CACHE_LOCK:
            cached = _BHAV_COPY_CACHE.get(key)
        if cached is not None and not cached.empty:
            return cursor.isoformat(), False
        try:
            df = mcxlib.get_bhav_copy(trade_date=key, instrument="FUTCOM")
        except Exception:
            df = None
        if df is not None and not df.empty:
            with _BHAV_COPY_CACHE_LOCK:
                _BHAV_COPY_CACHE[key] = df.copy()
            return cursor.isoformat(), False
        cursor -= timedelta(days=1)
    return today.isoformat(), True


def _expiry_iso(expiry: Any) -> str | None:
    if expiry is None or pd.isna(expiry):
        return None
    try:
        return pd.Timestamp(expiry).date().isoformat()
    except Exception:
        return None


def _expiry_display(expiry: Any) -> str | None:
    if expiry is None or pd.isna(expiry):
        return None
    try:
        return pd.Timestamp(expiry).strftime("%d%b%Y").upper()
    except Exception:
        return None


def get_mcx_quote(symbol: str) -> dict[str, Any]:
    spec = resolve_mcx_symbol(symbol)
    if spec is None:
        raise ValueError(f"unsupported MCX commodity symbol: {symbol}")

    import mcxlib

    frame = _filter_commodity_rows(mcxlib.get_market_watch(), spec)

    expiry_col = _find_column(
        frame,
        ("ExpiryDate", "Expiry Date", "Expiry", "ContractExpiry", "Contract Expiry"),
        required=False,
        label="expiry",
    )
    if expiry_col:
        frame["_expiry"] = _parse_mcx_dates(frame[expiry_col]).dt.normalize()

    ltp_col = _find_column(frame, ("LTP", "LastTradedPrice", "Last Traded Price"), label="ltp")
    open_col = _find_column(frame, ("Open", "OpenPrice", "Open Price"), label="open")
    high_col = _find_column(frame, ("High", "HighPrice", "High Price"), label="high")
    low_col = _find_column(frame, ("Low", "LowPrice", "Low Price"), label="low")
    prev_col = _find_column(
        frame,
        ("PreviousClose", "Previous Close", "PrevClose", "Prev Close", "Close"),
        label="previous close",
    )
    volume_col = _find_column(
        frame,
        ("Volume", "Vol", "Volume Lots"),
        required=False,
        label="volume",
    )
    pct_col = _find_column(
        frame,
        ("PercentChange", "Percent Change", "% Change"),
        required=False,
        label="percent change",
    )
    oi_col = _find_column(
        frame,
        ("OpenInterest", "Open Interest", "OI"),
        required=False,
        label="open interest",
    )
    unit_col = _find_column(
        frame,
        ("Unit", "ContractUnit", "Contract Unit"),
        required=False,
        label="unit",
    )
    instrument_col = _find_column(
        frame,
        ("InstrumentName", "Instrument Name", "Instrument", "InstrumentType", "Instrument Type"),
        required=False,
        label="instrument",
    )

    frame["last_price"] = _numeric(frame[ltp_col])
    frame["open"] = _numeric(frame[open_col])
    frame["high"] = _numeric(frame[high_col])
    frame["low"] = _numeric(frame[low_col])
    frame["prev_close"] = _numeric(frame[prev_col])
    frame["volume"] = _numeric(frame[volume_col]) if volume_col else 0.0

    frame = frame.dropna(subset=["last_price", "prev_close"])
    if frame.empty:
        raise ValueError(f"no usable MCX quote rows for {spec.symbol}")

    today = pd.Timestamp(date.today()).normalize()
    if "_expiry" in frame.columns and frame["_expiry"].notna().any():
        row = _pick_near_month(
            frame,
            today=today,
            roll_days=spec.roll_days_before_expiry,
        )
    else:
        row = frame.sort_values("volume", ascending=False).iloc[0]

    last_price = float(row["last_price"])
    prev_close = float(row["prev_close"])
    if pct_col:
        pct = _numeric(pd.Series([row[pct_col]])).iloc[0]
        change_pct = float(pct) / 100 if pd.notna(pct) else 0.0
    else:
        change_pct = (last_price - prev_close) / prev_close if prev_close else 0.0

    expiry_value = row["_expiry"] if "_expiry" in row.index else None
    open_interest_raw = (
        _numeric(pd.Series([row[oi_col]])).iloc[0] if oi_col and oi_col in row.index else None
    )
    if unit_col and pd.notna(row.get(unit_col)):
        unit_value = str(row[unit_col]).strip() or spec.display_unit
    else:
        unit_value = spec.display_unit
    if instrument_col and pd.notna(row.get(instrument_col)):
        instrument_value = str(row[instrument_col]).strip() or "FUTCOM"
    else:
        instrument_value = "FUTCOM"

    as_of, estimated = _resolve_trade_date(date.today())

    return {
        "symbol": spec.symbol,
        "last_price": last_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "day_high": float(row["high"]) if pd.notna(row["high"]) else last_price,
        "day_low": float(row["low"]) if pd.notna(row["low"]) else last_price,
        "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
        "as_of": as_of,
        "as_of_estimated": estimated,
        "source": "mcxlib",
        "expiry": _expiry_display(expiry_value),
        "expiry_iso": _expiry_iso(expiry_value),
        "unit": unit_value or spec.display_unit,
        "open_interest": (
            float(open_interest_raw)
            if open_interest_raw is not None and pd.notna(open_interest_raw)
            else None
        ),
        "instrument": instrument_value or "FUTCOM",
        "contract_symbol": spec.symbol,
    }


def get_mcx_icomdex() -> dict[str, dict[str, Any]]:
    """Return MCX iCOMDEX index snapshots keyed by commodity (GOLD, SILVER, ...)."""
    import mcxlib

    df = mcxlib.get_mcx_icomdex_indices()
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = _norm_token(row.get("Instrument_Code", ""))
        symbol = ICOMDEX_INSTRUMENT_TO_SYMBOL.get(code)
        if symbol is None:
            continue
        ltp = _numeric(pd.Series([row.get("LTP")])).iloc[0]
        if pd.isna(ltp):
            continue
        out[symbol] = {
            "symbol": symbol,
            "instrument_code": str(row.get("Instrument_Code", "")).strip(),
            "display_name": str(row.get("Instrument_Display_Name", "")).strip(),
            "ltp": float(ltp),
            "open": float(_numeric(pd.Series([row.get("Open")])).iloc[0] or 0.0),
            "high": float(_numeric(pd.Series([row.get("High")])).iloc[0] or 0.0),
            "low": float(_numeric(pd.Series([row.get("Low")])).iloc[0] or 0.0),
            "close": float(_numeric(pd.Series([row.get("Close")])).iloc[0] or 0.0),
            "percent_change": float(
                _numeric(pd.Series([row.get("PercentChange")])).iloc[0] or 0.0
            ),
        }
    return out


def _fetch_mcx_history(start: date, end: date) -> pd.DataFrame:
    import mcxlib

    def fetch_one(date_key: str) -> pd.DataFrame:
        with _BHAV_COPY_CACHE_LOCK:
            cached = _BHAV_COPY_CACHE.get(date_key)
        if cached is not None:
            return cached.copy()

        df = mcxlib.get_bhav_copy(
            trade_date=date_key,
            instrument="FUTCOM",
        )
        with _BHAV_COPY_CACHE_LOCK:
            _BHAV_COPY_CACHE[date_key] = df.copy()
        return df

    date_keys = [trade_day.strftime("%Y%m%d") for trade_day in pd.bdate_range(start=start, end=end)]
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    max_workers = min(_BHAV_COPY_MAX_WORKERS, len(date_keys))
    with ThreadPoolExecutor(max_workers=max_workers or 1) as executor:
        futures = {executor.submit(fetch_one, date_key): date_key for date_key in date_keys}
        for future in as_completed(futures):
            date_key = futures[future]
            try:
                df = future.result()
            except Exception as exc:
                errors.append(f"{date_key}: {exc}")
                continue
            if df is not None and not df.empty:
                frames.append(df)

    if not frames:
        detail = "; ".join(errors[-3:]) if errors else "MCX returned no rows"
        raise ValueError(f"MCX historical fetch failed: {detail}")
    return pd.concat(frames, ignore_index=True)


def load_mcx(symbol: str, period: str = "1y", interval: str = "1d", **_: Any) -> pd.DataFrame:
    spec = resolve_mcx_symbol(symbol)
    if spec is None:
        raise ValueError(f"unsupported MCX commodity symbol: {symbol}")

    end = date.today()
    start = _start_for_period(period, end)
    raw = _fetch_mcx_history(start, end)
    return _normalize_mcx_history(raw, spec, interval)


register("mcx", load_mcx)
