"""Conviction tier mapping from probability."""

from __future__ import annotations

from intraday_engine.output_schema import Conviction


def conviction_for_probability(probability: float) -> Conviction | None:
    if probability >= 0.75:
        return "fire"
    if probability >= 0.50:
        return "confirm"
    if probability >= 0.30:
        return "watch"
    return None
