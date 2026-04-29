"""Impulse-and-flag continuation detector."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors.base import (
    fired_result,
    last_volume_ratio,
    neutral_result,
    pct_change,
    safe_ratio,
    sorted_candles,
)
from intraday_engine.output_schema import DetectorResult

NAME = "flag"


def detect(
    candles: Sequence[Candle],
    *,
    impulse_bars: int = 4,
    consolidation_bars: int = 4,
    min_impulse_pct: float = 0.012,
    max_consolidation_pct: float = 0.012,
) -> DetectorResult:
    rows = sorted_candles(candles)
    required = impulse_bars + consolidation_bars + 1
    if len(rows) < required:
        return neutral_result(NAME, "not enough candles for impulse and flag")

    impulse = rows[-required : -(consolidation_bars + 1)]
    consolidation = rows[-(consolidation_bars + 1) : -1]
    last = rows[-1]
    impulse_move = pct_change(impulse[0].open, impulse[-1].close)
    consolidation_high = max(candle.high for candle in consolidation)
    consolidation_low = min(candle.low for candle in consolidation)
    consolidation_mid = max((consolidation_high + consolidation_low) / 2, 0.01)
    consolidation_width = safe_ratio(consolidation_high - consolidation_low, consolidation_mid)
    volume_ratio = last_volume_ratio(rows)
    metadata = {
        "impulse_pct": impulse_move,
        "consolidation_width_pct": consolidation_width,
        "consolidation_high": consolidation_high,
        "consolidation_low": consolidation_low,
        "volume_ratio": volume_ratio,
    }

    tight_enough = consolidation_width <= max_consolidation_pct
    if impulse_move >= min_impulse_pct and tight_enough and last.close > consolidation_high:
        extension = safe_ratio(last.close - consolidation_high, consolidation_high)
        strength = 0.48 + min(0.22, impulse_move * 8) + min(0.15, extension * 25)
        strength += min(0.15, volume_ratio / 10)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="bullish impulse paused in a tight flag and broke upward",
            metadata=metadata,
        )

    if impulse_move <= -min_impulse_pct and tight_enough and last.close < consolidation_low:
        extension = safe_ratio(consolidation_low - last.close, consolidation_low)
        strength = 0.48 + min(0.22, abs(impulse_move) * 8) + min(0.15, extension * 25)
        strength += min(0.15, volume_ratio / 10)
        return fired_result(
            NAME,
            direction="SHORT",
            strength=strength,
            reason="bearish impulse paused in a tight flag and broke downward",
            metadata=metadata,
        )

    return neutral_result(NAME, "no tight continuation flag break", metadata)
