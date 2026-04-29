"""yfinance fallback data source for intraday candles and quotes."""

from __future__ import annotations

from datetime import UTC

import pandas as pd

from backtest.loaders.yfinance_loader import load_yfinance
from intraday_engine.data_sources.base import (
    Candle,
    DataSource,
    DataSourceError,
    PreOpenRow,
    QuoteSnapshot,
    SurveillanceEntry,
)


class YFinanceSource(DataSource):
    name = "yfinance"

    def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "5m",
        lookback: str = "5d",
    ) -> list[Candle]:
        yahoo_symbol = _to_yahoo_symbol(symbol)
        try:
            df = load_yfinance(yahoo_symbol, period=lookback, interval=interval)
        except Exception as exc:
            msg = f"yfinance candle fetch failed for {yahoo_symbol}: {exc}"
            raise DataSourceError(msg) from exc
        if df is None or df.empty:
            raise DataSourceError(f"yfinance returned no candles for {yahoo_symbol}")
        return _frame_to_candles(df)

    def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        candles = self.fetch_candles(symbol, interval="1d", lookback="5d")
        if not candles:
            raise DataSourceError(f"yfinance returned no quote for {symbol}")
        last = candles[-1]
        prev_close = candles[-2].close if len(candles) >= 2 else last.close
        pct_change = (last.close - prev_close) / prev_close if prev_close else None
        return QuoteSnapshot(
            symbol=_display_symbol(symbol),
            ltp=last.close,
            prev_close=prev_close,
            pct_change=pct_change,
            day_high=last.high,
            day_low=last.low,
            volume=last.volume,
            as_of=last.timestamp,
            source=self.name,
        )

    def fetch_preopen(self) -> list[PreOpenRow]:
        return []

    def fetch_asm_gsm(self) -> list[SurveillanceEntry]:
        return []


def _frame_to_candles(df: pd.DataFrame) -> list[Candle]:
    columns = {str(col).lower(): col for col in df.columns}
    required = ("open", "high", "low", "close")
    if any(col not in columns for col in required):
        raise DataSourceError("yfinance frame missing OHLC columns")

    candles: list[Candle] = []
    for idx, row in df.iterrows():
        ts = pd.Timestamp(idx).to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        volume_col = columns.get("volume")
        candles.append(
            Candle(
                timestamp=ts,
                open=_finite_float(row[columns["open"]]),
                high=_finite_float(row[columns["high"]]),
                low=_finite_float(row[columns["low"]]),
                close=_finite_float(row[columns["close"]]),
                volume=_finite_float(row[volume_col]) if volume_col else 0.0,
                source="yfinance",
            )
        )
    return candles


def _to_yahoo_symbol(symbol: str) -> str:
    raw = symbol.strip()
    upper = raw.upper()
    if upper.startswith("^") or "=" in upper or "." in upper:
        return raw
    return f"{raw}.NS"


def _display_symbol(symbol: str) -> str:
    upper = symbol.strip().upper()
    return upper[:-3] if upper.endswith(".NS") else upper


def _finite_float(value: object) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)
