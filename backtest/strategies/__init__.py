"""Deterministic signal generators. Each strategy fn returns a pd.Series in {-1,0,1}
aligned to the input OHLCV frame's index."""

from __future__ import annotations

# Side-effect imports register strategies into STRATEGIES.
from . import breakout, mean_reversion, momentum, trend  # noqa: F401,E402
from .registry import STRATEGIES, StrategySpec, register  # noqa: F401

__all__ = ["STRATEGIES", "StrategySpec", "register"]
