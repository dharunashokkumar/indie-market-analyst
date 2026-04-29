"""Composite probability score for deterministic intraday picks."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.detectors.base import clamp, fired
from intraday_engine.output_schema import DetectorResult
from intraday_engine.scoring.direction import conflict_ratio


def probability_score(
    results: Sequence[DetectorResult],
    *,
    volume_x_avg: float = 0.0,
    pct_change: float = 0.0,
) -> float:
    fired_results = fired(results)
    if not fired_results:
        return 0.0

    average_strength = sum(result.strength for result in fired_results) / len(fired_results)
    detector_component = average_strength * 0.65
    detector_count_component = min(0.15, len(fired_results) * 0.05)
    volume_component = min(0.15, max(0.0, volume_x_avg - 1.0) / 4 * 0.15)
    move_component = min(0.05, abs(pct_change) / 0.03 * 0.05)
    raw = detector_component + detector_count_component + volume_component + move_component

    # When both sides fire, the setup can still be usable, but certainty should drop.
    penalty = conflict_ratio(fired_results) * 0.30
    return round(clamp(raw * (1 - penalty)), 4)
