"""Price-and-volume momentum detector."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors.base import (
    fired_result,
    last_volume_ratio,
    neutral_result,
    session_pct_change,
    sorted_candles,
)
from intraday_engine.output_schema import DetectorResult

NAME = "momentum"


def detect(
    candles: Sequence[Candle],
    *,
    min_abs_pct_change: float = 0.01,
    min_volume_ratio: float = 2.0,
) -> DetectorResult:
    rows = sorted_candles(candles)
    if len(rows) < 3:
        return neutral_result(NAME, "not enough candles for momentum")

    move = session_pct_change(rows)
    volume_ratio = last_volume_ratio(rows)
    metadata = {
        "pct_change": move,
        "volume_ratio": volume_ratio,
        "min_abs_pct_change": min_abs_pct_change,
        "min_volume_ratio": min_volume_ratio,
    }

    if move >= min_abs_pct_change and volume_ratio >= min_volume_ratio:
        strength = 0.45 + min(0.30, move * 10) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="positive session move with volume expansion",
            metadata=metadata,
        )

    if move <= -min_abs_pct_change and volume_ratio >= min_volume_ratio:
        strength = 0.45 + min(0.30, abs(move) * 10) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="SHORT",
            strength=strength,
            reason="negative session move with volume expansion",
            metadata=metadata,
        )

    return neutral_result(NAME, "price move or volume expansion below threshold", metadata)
