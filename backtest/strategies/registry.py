"""Strategy registry — name → StrategySpec."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

SignalFn = Callable[..., pd.Series]


@dataclass(frozen=True)
class StrategySpec:
    name: str
    category: str          # "trend" | "mean_reversion" | "breakout" | "momentum"
    label: str             # human-friendly display name
    description: str
    fn: SignalFn
    default_params: dict[str, Any] = field(default_factory=dict)


STRATEGIES: dict[str, StrategySpec] = {}


def register(spec: StrategySpec) -> None:
    if spec.name in STRATEGIES:
        raise ValueError(f"duplicate strategy registration: {spec.name}")
    STRATEGIES[spec.name] = spec
