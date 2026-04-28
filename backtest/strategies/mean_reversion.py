"""Mean-reversion strategies."""

from __future__ import annotations

import pandas as pd

from .registry import StrategySpec, register
from .utils import rolling_zscore, rsi


def rsi_reversion(df: pd.DataFrame, length: int = 14,
                  lower: float = 30.0, upper: float = 70.0) -> pd.Series:
    r = rsi(df["close"], length=length)
    sig = pd.Series(0.0, index=df.index)
    sig[r < lower] = 1.0
    sig[r > upper] = -1.0
    return sig.fillna(0.0)


def bollinger_reversion(df: pd.DataFrame, length: int = 20, std_mult: float = 2.0) -> pd.Series:
    close = df["close"]
    mid = close.rolling(length, min_periods=length).mean()
    std = close.rolling(length, min_periods=length).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    sig = pd.Series(0.0, index=df.index)
    sig[close < lower] = 1.0
    sig[close > upper] = -1.0
    return sig.fillna(0.0)


def zscore_reversion(df: pd.DataFrame, length: int = 20, threshold: float = 2.0) -> pd.Series:
    z = rolling_zscore(df["close"], length=length)
    sig = pd.Series(0.0, index=df.index)
    sig[z < -threshold] = 1.0
    sig[z > threshold] = -1.0
    return sig.fillna(0.0)


register(StrategySpec(
    name="rsi_reversion", category="mean_reversion", label="RSI Reversion",
    description="Long when RSI < lower, short when RSI > upper.",
    fn=rsi_reversion, default_params={"length": 14, "lower": 30.0, "upper": 70.0},
))
register(StrategySpec(
    name="bollinger_reversion", category="mean_reversion", label="Bollinger Reversion",
    description="Long below lower band, short above upper band.",
    fn=bollinger_reversion, default_params={"length": 20, "std_mult": 2.0},
))
register(StrategySpec(
    name="zscore_reversion", category="mean_reversion", label="Z-Score Reversion",
    description="Long when rolling z-score < -threshold, short when > +threshold.",
    fn=zscore_reversion, default_params={"length": 20, "threshold": 2.0},
))
