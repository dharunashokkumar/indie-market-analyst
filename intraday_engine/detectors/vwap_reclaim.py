"""VWAP reclaim and rejection detector."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors.base import (
    cumulative_vwap,
    fired_result,
    last_volume_ratio,
    neutral_result,
    pct_change,
    sorted_candles,
)
from intraday_engine.output_schema import DetectorResult

NAME = "vwap_reclaim"


def detect(candles: Sequence[Candle]) -> DetectorResult:
    rows = sorted_candles(candles)
    if len(rows) < 4:
        return neutral_result(NAME, "need at least four candles for VWAP reclaim")

    vwaps = cumulative_vwap(rows)
    previous = rows[-2]
    last = rows[-1]
    previous_vwap = vwaps[-2]
    last_vwap = vwaps[-1]
    volume_ratio = last_volume_ratio(rows)
    distance = abs(pct_change(last_vwap, last.close))

    if previous.close <= previous_vwap and last.close > last_vwap:
        strength = 0.45 + min(0.30, distance * 40) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="LONG",
            strength=strength,
            reason="close reclaimed VWAP after trading below it",
            metadata={
                "vwap": last_vwap,
                "previous_vwap": previous_vwap,
                "volume_ratio": volume_ratio,
                "distance_from_vwap": distance,
            },
        )

    if previous.close >= previous_vwap and last.close < last_vwap:
        strength = 0.45 + min(0.30, distance * 40) + min(0.25, volume_ratio / 8)
        return fired_result(
            NAME,
            direction="SHORT",
            strength=strength,
            reason="close lost VWAP after trading above it",
            metadata={
                "vwap": last_vwap,
                "previous_vwap": previous_vwap,
                "volume_ratio": volume_ratio,
                "distance_from_vwap": distance,
            },
        )

    return neutral_result(
        NAME,
        "no fresh VWAP reclaim or loss",
        {
            "vwap": last_vwap,
            "previous_vwap": previous_vwap,
            "volume_ratio": volume_ratio,
            "last_close": last.close,
        },
    )
