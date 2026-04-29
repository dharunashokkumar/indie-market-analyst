"""Direction classifier for fired detector results."""

from __future__ import annotations

from collections.abc import Sequence

from intraday_engine.output_schema import DetectorResult, Direction


def direction_score(results: Sequence[DetectorResult]) -> dict[Direction, float]:
    scores: dict[Direction, float] = {"LONG": 0.0, "SHORT": 0.0}
    for result in results:
        if not result.fired or result.direction == "NEUTRAL":
            continue
        scores[result.direction] += result.strength
    return scores


def classify_direction(
    results: Sequence[DetectorResult],
    *,
    min_edge: float = 0.05,
) -> Direction | None:
    scores = direction_score(results)
    long_score = scores["LONG"]
    short_score = scores["SHORT"]
    if long_score <= 0 and short_score <= 0:
        return None
    if abs(long_score - short_score) < min_edge:
        return None
    return "LONG" if long_score > short_score else "SHORT"


def conflict_ratio(results: Sequence[DetectorResult]) -> float:
    scores = direction_score(results)
    total = scores["LONG"] + scores["SHORT"]
    if total <= 0:
        return 0.0
    return min(scores["LONG"], scores["SHORT"]) / total
