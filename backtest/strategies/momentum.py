"""Momentum / oscillator strategies."""

from __future__ import annotations

import pandas as pd

from .registry import StrategySpec, register
from .utils import adx, stochastic


def roc_momentum(df: pd.DataFrame, length: int = 20, threshold: float = 0.02) -> pd.Series:
    roc = df["close"].pct_change(periods=length)
    sig = pd.Series(0.0, index=df.index)
    sig[roc > threshold] = 1.0
    sig[roc < -threshold] = -1.0
    return sig.fillna(0.0)


def stochastic_oscillator(df: pd.DataFrame, k: int = 14, d: int = 3,
                          lower: float = 20.0, upper: float = 80.0) -> pd.Series:
    s = stochastic(df, k=k, d=d)
    sig = pd.Series(0.0, index=df.index)
    sig[s["k"] < lower] = 1.0
    sig[s["k"] > upper] = -1.0
    return sig.fillna(0.0)


def adx_trend(df: pd.DataFrame, length: int = 14, threshold: float = 25.0) -> pd.Series:
    a = adx(df, length=length)
    strong = a["adx"] > threshold
    sig = pd.Series(0.0, index=df.index)
    sig[strong & (a["plus_di"] > a["minus_di"])] = 1.0
    sig[strong & (a["minus_di"] > a["plus_di"])] = -1.0
    return sig.fillna(0.0)


register(StrategySpec(
    name="roc_momentum", category="momentum", label="Rate-of-Change Momentum",
    description="Long when N-bar ROC exceeds +threshold; short when below -threshold.",
    fn=roc_momentum, default_params={"length": 20, "threshold": 0.02},
))
register(StrategySpec(
    name="stochastic_oscillator", category="momentum", label="Stochastic Oscillator",
    description="Long when %K is oversold (<lower); short when overbought (>upper).",
    fn=stochastic_oscillator, default_params={"k": 14, "d": 3, "lower": 20.0, "upper": 80.0},
))
register(StrategySpec(
    name="adx_trend", category="momentum", label="ADX-Filtered Trend",
    description="Long when ADX>threshold and +DI>-DI; short on the inverse.",
    fn=adx_trend, default_params={"length": 14, "threshold": 25.0},
))
