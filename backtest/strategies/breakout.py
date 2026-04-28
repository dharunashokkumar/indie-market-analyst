"""Breakout strategies."""

from __future__ import annotations

import pandas as pd

from .registry import StrategySpec, register
from .utils import atr


def donchian_breakout(df: pd.DataFrame, length: int = 20) -> pd.Series:
    upper = df["high"].rolling(length, min_periods=length).max().shift(1)
    lower = df["low"].rolling(length, min_periods=length).min().shift(1)
    close = df["close"]
    sig = pd.Series(0.0, index=df.index)
    sig[close > upper] = 1.0
    sig[close < lower] = -1.0
    return sig.fillna(0.0)


def atr_breakout(df: pd.DataFrame, length: int = 14, mult: float = 2.0) -> pd.Series:
    a = atr(df, length=length)
    prev_close = df["close"].shift(1)
    upper = prev_close + mult * a
    lower = prev_close - mult * a
    close = df["close"]
    sig = pd.Series(0.0, index=df.index)
    sig[close > upper] = 1.0
    sig[close < lower] = -1.0
    return sig.fillna(0.0)


def high_52w_breakout(df: pd.DataFrame, length: int = 252) -> pd.Series:
    rolling_high = df["close"].rolling(length, min_periods=max(20, length // 4)).max()
    sig = (df["close"] >= rolling_high).astype(float)
    return sig.fillna(0.0)


register(StrategySpec(
    name="donchian_breakout", category="breakout", label="Donchian Channel Breakout",
    description="Long on N-bar high break, short on N-bar low break.",
    fn=donchian_breakout, default_params={"length": 20},
))
register(StrategySpec(
    name="atr_breakout", category="breakout", label="ATR Breakout",
    description="Long when close exceeds prev close + N×ATR; short on the opposite.",
    fn=atr_breakout, default_params={"length": 14, "mult": 2.0},
))
register(StrategySpec(
    name="high_52w_breakout", category="breakout", label="52-Week High Breakout",
    description="Long when close is at/above the 52-week high.",
    fn=high_52w_breakout, default_params={"length": 252},
))
