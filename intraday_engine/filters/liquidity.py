"""Liquidity filters for intraday scan universes."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from intraday_engine.data_sources.base import Candle, QuoteSnapshot
from intraday_engine.ist_clock import to_ist

MIN_DAILY_TURNOVER_RUPEES = 50_000_000.0


class LiquidityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    passed: bool
    turnover: float | None = Field(default=None, ge=0.0)
    threshold: float = Field(default=MIN_DAILY_TURNOVER_RUPEES, ge=0.0)
    reason: str


def check_liquidity(
    symbol: str,
    *,
    quote: QuoteSnapshot | None = None,
    candles: Sequence[Candle] | None = None,
    min_turnover: float = MIN_DAILY_TURNOVER_RUPEES,
) -> LiquidityDecision:
    turnover = quote_turnover(quote)
    if turnover is None:
        turnover = candle_turnover(candles or [])
    clean_symbol = symbol.strip().upper()
    if turnover is None:
        return LiquidityDecision(
            symbol=clean_symbol,
            passed=False,
            turnover=None,
            threshold=min_turnover,
            reason="turnover_unavailable",
        )
    if turnover < min_turnover:
        return LiquidityDecision(
            symbol=clean_symbol,
            passed=False,
            turnover=turnover,
            threshold=min_turnover,
            reason="below_turnover_floor",
        )
    return LiquidityDecision(
        symbol=clean_symbol,
        passed=True,
        turnover=turnover,
        threshold=min_turnover,
        reason="ok",
    )


def quote_turnover(quote: QuoteSnapshot | None) -> float | None:
    if quote is None:
        return None
    if quote.turnover is not None and quote.turnover >= 0:
        return quote.turnover
    if quote.ltp >= 0 and quote.volume is not None and quote.volume >= 0:
        return quote.ltp * quote.volume
    return None


def candle_turnover(candles: Sequence[Candle]) -> float | None:
    if not candles:
        return None
    latest_day = to_ist(max(candles, key=lambda candle: candle.timestamp).timestamp).date()
    total = 0.0
    count = 0
    for candle in candles:
        if to_ist(candle.timestamp).date() != latest_day:
            continue
        if candle.volume < 0 or candle.close < 0:
            continue
        total += candle.close * candle.volume
        count += 1
    return total if count else None
