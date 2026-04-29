"""Short-covering proxy detector using only price and volume."""

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

NAME = "short_cover"


def detect(
    candles: Sequence[Candle],
    *,
    min_rebound_from_low: float = 0.012,
    min_volume_ratio: float = 2.0,
) -> DetectorResult:
    rows = sorted_candles(candles)
    if len(rows) < 6:
        return neutral_result(NAME, "not enough candles for short-cover proxy")

    last = rows[-1]
    previous = rows[-2]
    session_open = rows[0].open
    day_low = min(candle.low for candle in rows[:-1])
    day_low_index = min(range(len(rows[:-1])), key=lambda idx: rows[idx].low)
    rebound = pct_change(day_low, last.close)
    opening_drop = pct_change(session_open, day_low)
    volume_ratio = last_volume_ratio(rows)
    closes_near_high = safe_ratio(last.close - day_low, max(last.high - day_low, 0.01)) >= 0.65
    metadata = {
        "day_low": day_low,
        "day_low_index": day_low_index,
        "opening_drop": opening_drop,
        "rebound_from_low": rebound,
        "recovered_above_open": last.close > session_open,
        "volume_ratio": volume_ratio,
        "closes_near_high": closes_near_high,
    }

    if (
        opening_drop < 0
        and rebound >= min_rebound_from_low
        and last.close > previous.close
        and last.close > session_open
        and volume_ratio >= min_volume_ratio
        and closes_near_high
    ):
        strength = 0.48 + min(0.25, rebound * 10) + min(0.17, volume_ratio / 8)
        strength += min(0.10, abs(opening_drop) * 6)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="stock rebounded sharply from intraday low on expanded volume",
            metadata=metadata,
        )

    return neutral_result(NAME, "no high-volume rebound from intraday low", metadata)
