"""Shared detector contracts and runner harness."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from statistics import mean
from typing import TYPE_CHECKING

from intraday_engine.data_sources.base import Candle
from intraday_engine.ist_clock import to_ist
from intraday_engine.output_schema import DetectorDirection, DetectorResult

if TYPE_CHECKING:
    DetectorFn = Callable[[Sequence[Candle]], DetectorResult]

DETECTOR_NAMES = (
    "orb",
    "vwap_reclaim",
    "breakout",
    "flag",
    "momentum",
    "short_cover",
)


def neutral_result(
    name: str,
    reason: str,
    metadata: dict[str, object] | None = None,
) -> DetectorResult:
    return DetectorResult(
        name=name,
        fired=False,
        strength=0.0,
        direction="NEUTRAL",
        reason=reason,
        metadata=metadata or {},
    )


def fired_result(
    name: str,
    *,
    direction: DetectorDirection,
    strength: float,
    reason: str,
    metadata: dict[str, object] | None = None,
) -> DetectorResult:
    if direction == "NEUTRAL":
        return neutral_result(name, reason, metadata)
    return DetectorResult(
        name=name,
        fired=True,
        strength=clamp(strength),
        direction=direction,
        reason=reason,
        metadata=metadata or {},
    )


def run_all_detectors(candles: Sequence[Candle]) -> list[DetectorResult]:
    """Run all required P1 setup detectors in a stable order."""
    from intraday_engine.detectors.breakout import detect as detect_breakout
    from intraday_engine.detectors.flag import detect as detect_flag
    from intraday_engine.detectors.momentum import detect as detect_momentum
    from intraday_engine.detectors.orb import detect as detect_orb
    from intraday_engine.detectors.short_cover import detect as detect_short_cover
    from intraday_engine.detectors.vwap_reclaim import detect as detect_vwap_reclaim

    detectors: tuple[Callable[[Sequence[Candle]], DetectorResult], ...] = (
        detect_orb,
        detect_vwap_reclaim,
        detect_breakout,
        detect_flag,
        detect_momentum,
        detect_short_cover,
    )
    return [detector(sorted_candles(candles)) for detector in detectors]


def fired(results: Sequence[DetectorResult]) -> list[DetectorResult]:
    return [result for result in results if result.fired]


def sorted_candles(candles: Sequence[Candle]) -> list[Candle]:
    return sorted(candles, key=lambda candle: candle.timestamp)


def latest_session_candles(candles: Sequence[Candle]) -> list[Candle]:
    rows = sorted_candles(candles)
    if not rows:
        return []
    latest_day = to_ist(rows[-1].timestamp).date()
    return [candle for candle in rows if to_ist(candle.timestamp).date() == latest_day]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def pct_change(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start


def avg_volume(candles: Sequence[Candle], *, exclude_last: bool = True) -> float:
    rows = candles[:-1] if exclude_last else candles
    volumes = [candle.volume for candle in rows if candle.volume > 0]
    return mean(volumes) if volumes else 0.0


def last_volume_ratio(candles: Sequence[Candle]) -> float:
    if not candles:
        return 0.0
    return safe_ratio(candles[-1].volume, avg_volume(candles))


def daily_volume_ratio(candles: Sequence[Candle], *, lookback_days: int = 20) -> float:
    rows = sorted_candles(candles)
    if not rows:
        return 0.0

    by_day: dict[date, float] = {}
    for candle in rows:
        day = to_ist(candle.timestamp).date()
        by_day[day] = by_day.get(day, 0.0) + max(0.0, candle.volume)

    latest_day = to_ist(rows[-1].timestamp).date()
    current_volume = by_day.get(latest_day, 0.0)
    prior_days = sorted(day for day in by_day if day < latest_day)
    prior_volumes = [by_day[day] for day in prior_days[-lookback_days:] if by_day[day] > 0]
    baseline = mean(prior_volumes) if prior_volumes else 0.0
    if baseline <= 0:
        return last_volume_ratio(latest_session_candles(rows) or rows)
    return safe_ratio(current_volume, baseline)


def session_pct_change(candles: Sequence[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    return pct_change(candles[0].open, candles[-1].close)


def bars_for_minutes(candles: Sequence[Candle], minutes: int) -> int:
    if len(candles) < 2:
        return max(1, minutes // 5)
    deltas: list[float] = []
    ordered = sorted_candles(candles)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        delta = current.timestamp - previous.timestamp
        if delta > timedelta(0):
            deltas.append(delta.total_seconds() / 60)
    interval = min(deltas) if deltas else 5
    if interval <= 0:
        interval = 5
    return max(1, round(minutes / interval))


def cumulative_vwap(candles: Sequence[Candle]) -> list[float]:
    vwaps: list[float] = []
    price_volume_sum = 0.0
    volume_sum = 0.0
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3
        volume = max(0.0, candle.volume)
        price_volume_sum += typical * volume
        volume_sum += volume
        vwaps.append(price_volume_sum / volume_sum if volume_sum > 0 else typical)
    return vwaps
