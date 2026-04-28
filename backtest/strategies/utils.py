"""Shared indicator helpers for strategies. Pure pandas, no external deps."""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return true_range(df).rolling(length, min_periods=length).mean()


def rolling_zscore(s: pd.Series, length: int) -> pd.Series:
    mean = s.rolling(length, min_periods=length).mean()
    std = s.rolling(length, min_periods=length).std(ddof=0)
    return (s - mean) / std.replace(0, np.nan)


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Returns DataFrame with columns adx, plus_di, minus_di."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = ((up > down) & (up > 0)).astype(float) * up
    minus_dm = ((down > up) & (down > 0)).astype(float) * down
    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    plus_smooth = plus_dm.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    minus_smooth = minus_dm.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    plus_di = 100 * plus_smooth / atr_.replace(0, np.nan)
    minus_di = 100 * minus_smooth / atr_.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    return pd.DataFrame({"adx": adx_, "plus_di": plus_di, "minus_di": minus_di}, index=df.index)


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    """Returns DataFrame with columns k, d (percent K and percent D)."""
    low_min = df["low"].rolling(k, min_periods=k).min()
    high_max = df["high"].rolling(k, min_periods=k).max()
    span = (high_max - low_min).replace(0, np.nan)
    pct_k = 100 * (df["close"] - low_min) / span
    pct_d = pct_k.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"k": pct_k, "d": pct_d}, index=df.index)


def to_signal(series: pd.Series) -> pd.Series:
    """Coerce arbitrary numeric → {-1, 0, 1} float, NaN→0, indexed like input."""
    s = series.fillna(0.0)
    s = np.sign(s)
    return s.astype(float)
