"""Opening-range breakout detector."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors.base import (
    bars_for_minutes,
    fired_result,
    last_volume_ratio,
    neutral_result,
    safe_ratio,
    sorted_candles,
)
from intraday_engine.output_schema import DetectorResult

NAME = "orb"


def detect(candles: Sequence[Candle], *, opening_minutes: int = 30) -> DetectorResult:
    rows = sorted_candles(candles)
    opening_bars = bars_for_minutes(rows, opening_minutes)
    if len(rows) <= opening_bars:
        return neutral_result(NAME, "not enough candles after opening range")

    opening = rows[:opening_bars]
    last = rows[-1]
    range_high = max(candle.high for candle in opening)
    range_low = min(candle.low for candle in opening)
    range_width = max(range_high - range_low, range_high * 0.001, 0.01)
    volume_ratio = last_volume_ratio(rows)

    if last.close > range_high:
        breakout_ratio = safe_ratio(last.close - range_high, range_width)
        strength = 0.45 + min(0.35, breakout_ratio * 0.35) + min(0.20, volume_ratio / 10)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="close broke above opening range high",
            metadata={
                "opening_minutes": opening_minutes,
                "range_high": range_high,
                "range_low": range_low,
                "volume_ratio": volume_ratio,
            },
        )

    if last.close < range_low:
        breakdown_ratio = safe_ratio(range_low - last.close, range_width)
        strength = 0.45 + min(0.35, breakdown_ratio * 0.35) + min(0.20, volume_ratio / 10)
        return fired_result(
            NAME,
            direction="SHORT",
            strength=strength,
            reason="close broke below opening range low",
            metadata={
                "opening_minutes": opening_minutes,
                "range_high": range_high,
                "range_low": range_low,
                "volume_ratio": volume_ratio,
            },
        )

    return neutral_result(
        NAME,
        "close remains inside opening range",
        {
            "opening_minutes": opening_minutes,
            "range_high": range_high,
            "range_low": range_low,
            "volume_ratio": volume_ratio,
        },
    )
