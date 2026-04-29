from __future__ import annotations

from intraday_engine.output_schema import DetectorResult
from intraday_engine.scoring import (
    classify_direction,
    conviction_for_probability,
    probability_score,
)


def _result(name: str, fired: bool, strength: float, direction: str) -> DetectorResult:
    return DetectorResult(
        name=name,
        fired=fired,
        strength=strength,
        direction=direction,  # type: ignore[arg-type]
    )


def test_scoring_returns_zero_for_no_fired_detectors():
    results = [
        _result("orb", False, 0.0, "NEUTRAL"),
        _result("momentum", False, 0.0, "NEUTRAL"),
    ]

    assert classify_direction(results) is None
    assert probability_score(results, volume_x_avg=5.0, pct_change=0.03) == 0.0
    assert conviction_for_probability(0.29) is None


def test_direction_classifier_returns_none_for_conflicting_tie():
    results = [
        _result("breakout", True, 0.70, "LONG"),
        _result("vwap_reclaim", True, 0.70, "SHORT"),
    ]

    assert classify_direction(results) is None
    assert probability_score(results, volume_x_avg=3.0, pct_change=0.02) < 0.70


def test_scoring_maps_majority_direction_and_conviction():
    results = [
        _result("orb", True, 0.82, "LONG"),
        _result("momentum", True, 0.76, "LONG"),
        _result("vwap_reclaim", False, 0.0, "NEUTRAL"),
    ]

    score = probability_score(results, volume_x_avg=4.0, pct_change=0.025)

    assert classify_direction(results) == "LONG"
    assert score >= 0.75
    assert conviction_for_probability(score) == "fire"
    assert conviction_for_probability(0.60) == "confirm"
    assert conviction_for_probability(0.35) == "watch"
