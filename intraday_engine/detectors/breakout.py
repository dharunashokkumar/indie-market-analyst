"""Rolling high/low breakout detector with volume confirmation."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors.base import (
    fired_result,
    last_volume_ratio,
    neutral_result,
    safe_ratio,
    sorted_candles,
)
from intraday_engine.output_schema import DetectorResult

NAME = "breakout"


def detect(
    candles: Sequence[Candle],
    *,
    lookback_bars: int = 20,
    min_volume_ratio: float = 1.5,
) -> DetectorResult:
    rows = sorted_candles(candles)
    if len(rows) < max(6, lookback_bars // 2):
        return neutral_result(NAME, "not enough candles for rolling breakout")

    previous = rows[-(lookback_bars + 1) : -1] if len(rows) > lookback_bars else rows[:-1]
    if not previous:
        return neutral_result(NAME, "no prior candles for breakout comparison")

    last = rows[-1]
    prior_high = max(candle.high for candle in previous)
    prior_low = min(candle.low for candle in previous)
    prior_range = max(prior_high - prior_low, prior_high * 0.001, 0.01)
    volume_ratio = last_volume_ratio(rows)
    metadata = {
        "lookback_bars": len(previous),
        "prior_high": prior_high,
        "prior_low": prior_low,
        "volume_ratio": volume_ratio,
        "min_volume_ratio": min_volume_ratio,
    }

    if last.close > prior_high and volume_ratio >= min_volume_ratio:
        extension = safe_ratio(last.close - prior_high, prior_range)
        strength = 0.50 + min(0.25, extension * 0.40) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="close broke prior rolling high with volume confirmation",
            metadata=metadata,
        )

    if last.close < prior_low and volume_ratio >= min_volume_ratio:
        extension = safe_ratio(prior_low - last.close, prior_range)
        strength = 0.50 + min(0.25, extension * 0.40) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="SHORT",
            strength=strength,
            reason="close broke prior rolling low with volume confirmation",
            metadata=metadata,
        )

    return neutral_result(NAME, "no confirmed rolling high/low break", metadata)
