"""yfinance OHLCV loader."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from .registry import register


def _to_yahoo_symbol(symbol: str, exchange: str = "NSE") -> str:
    raw = symbol.strip()
    upper = raw.upper()
    if (
        upper.startswith("^")
        or "=" in upper
        or "-" in upper
        or "." in upper
    ):
        return raw
    return f"{raw}.NS" if exchange == "NSE" else f"{raw}.BO"


def load_yfinance(symbol: str, period: str = "1y", interval: str = "1d",
                  exchange: str = "NSE") -> pd.DataFrame:
    yf_symbol = _to_yahoo_symbol(symbol, exchange=exchange)
    df = yf.Ticker(yf_symbol).history(period=period, interval=interval, auto_adjust=False)
    df.index = pd.to_datetime(df.index)
    df.columns = [c.lower() for c in df.columns]
    df["source"] = "yfinance"
    return df


register("yfinance", load_yfinance)
