"""Trend-following strategies."""

from __future__ import annotations

import pandas as pd

from .registry import StrategySpec, register
from .utils import to_signal


def sma_crossover(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    close = df["close"]
    f = close.rolling(fast, min_periods=fast).mean()
    s = close.rolling(slow, min_periods=slow).mean()
    return to_signal(f - s)


def ema_crossover(df: pd.DataFrame, fast: int = 12, slow: int = 26) -> pd.Series:
    close = df["close"]
    f = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    s = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    return to_signal(f - s)


def macd_signal_cross(df: pd.DataFrame, fast: int = 12,
                      slow: int = 26, signal: int = 9) -> pd.Series:
    close = df["close"]
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    return to_signal(macd - sig)


register(StrategySpec(
    name="sma_crossover", category="trend", label="SMA Crossover (20/50)",
    description="Long when fast SMA crosses above slow SMA.",
    fn=sma_crossover, default_params={"fast": 20, "slow": 50},
))
register(StrategySpec(
    name="ema_crossover", category="trend", label="EMA Crossover (12/26)",
    description="Long when fast EMA crosses above slow EMA.",
    fn=ema_crossover, default_params={"fast": 12, "slow": 26},
))
register(StrategySpec(
    name="macd_signal_cross", category="trend", label="MACD Signal Cross",
    description="Long when MACD line crosses above its signal line.",
    fn=macd_signal_cross, default_params={"fast": 12, "slow": 26, "signal": 9},
))
