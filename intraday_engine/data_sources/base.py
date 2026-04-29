"""Shared data-source contracts for intraday market data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceName = Literal["nse_direct", "yfinance"]


class DataSourceError(RuntimeError):
    """Raised when a data source cannot satisfy a fetch request."""


class MarketDataModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Candle(MarketDataModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: SourceName


class QuoteSnapshot(MarketDataModel):
    symbol: str
    ltp: float
    prev_close: float | None = None
    pct_change: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None
    turnover: float | None = None
    as_of: datetime
    source: SourceName
    raw: dict[str, Any] = Field(default_factory=dict)


class PreOpenRow(MarketDataModel):
    symbol: str
    ltp: float | None = None
    indicative_open: float | None = None
    pct_change: float | None = None
    volume: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SurveillanceEntry(MarketDataModel):
    symbol: str
    list_type: Literal["ASM", "GSM"]
    stage: str | None = None
    as_of: datetime
    source: SourceName = "nse_direct"
    raw: dict[str, Any] = Field(default_factory=dict)


class DataSource(ABC):
    name: SourceName

    @abstractmethod
    def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "5m",
        lookback: str = "5d",
    ) -> list[Candle]:
        """Fetch OHLCV candles for one symbol."""

    @abstractmethod
    def fetch_quote(self, symbol: str) -> QuoteSnapshot:
        """Fetch a live quote snapshot for one symbol."""

    @abstractmethod
    def fetch_preopen(self) -> list[PreOpenRow]:
        """Fetch NSE pre-open rows when the source supports them."""

    @abstractmethod
    def fetch_asm_gsm(self) -> list[SurveillanceEntry]:
        """Fetch ASM/GSM surveillance rows when the source supports them."""
