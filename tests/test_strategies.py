"""Contract + directional tests for the 12 v1 strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.strategies import STRATEGIES


def _ohlcv(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    high = close * 1.01
    low = close * 0.99
    open_ = np.r_[close[0], close[:-1]]
    vol = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _uptrend(n: int = 400) -> pd.DataFrame:
    return _ohlcv(np.linspace(100.0, 200.0, n))


def _downtrend(n: int = 400) -> pd.DataFrame:
    return _ohlcv(np.linspace(200.0, 100.0, n))


def _sine(n: int = 400, amp: float = 10.0) -> pd.DataFrame:
    t = np.arange(n)
    return _ohlcv(150.0 + amp * np.sin(t / 10.0))


def test_registry_has_all_twelve():
    expected = {
        # trend
        "sma_crossover", "ema_crossover", "macd_signal_cross",
        # mean reversion
        "rsi_reversion", "bollinger_reversion", "zscore_reversion",
        # breakout
        "donchian_breakout", "atr_breakout", "high_52w_breakout",
        # momentum
        "roc_momentum", "stochastic_oscillator", "adx_trend",
    }
    assert set(STRATEGIES.keys()) == expected


@pytest.mark.parametrize("name", sorted(["sma_crossover", "ema_crossover", "macd_signal_cross",
                                         "rsi_reversion", "bollinger_reversion", "zscore_reversion",
                                         "donchian_breakout", "atr_breakout", "high_52w_breakout",
                                         "roc_momentum", "stochastic_oscillator", "adx_trend"]))
def test_strategy_contract(name: str):
    df = _uptrend()
    spec = STRATEGIES[name]
    sig = spec.fn(df, **spec.default_params)
    assert isinstance(sig, pd.Series)
    assert len(sig) == len(df)
    assert (sig.index == df.index).all()
    uniq = set(sig.dropna().unique())
    assert uniq.issubset({-1.0, 0.0, 1.0}), f"{name} produced {uniq}"
    assert not sig.isna().any(), f"{name} left NaNs"


def test_trend_strategies_long_in_uptrend():
    df = _uptrend()
    for name in ("sma_crossover", "ema_crossover", "macd_signal_cross"):
        sig = STRATEGIES[name].fn(df, **STRATEGIES[name].default_params)
        # the latter half should be predominantly long (1.0)
        late = sig.iloc[len(sig) // 2:]
        assert (late == 1.0).mean() > 0.7, f"{name} not long in uptrend"


def test_trend_strategies_flat_or_short_in_downtrend():
    df = _downtrend()
    for name in ("sma_crossover", "ema_crossover", "macd_signal_cross"):
        sig = STRATEGIES[name].fn(df, **STRATEGIES[name].default_params)
        late = sig.iloc[len(sig) // 2:]
        assert (late == 1.0).mean() < 0.1, f"{name} stayed long in downtrend"


def test_high_52w_breakout_triggers_in_steady_uptrend():
    df = _uptrend()
    sig = STRATEGIES["high_52w_breakout"].fn(df)
    # In a strict uptrend, every bar past the warmup is at/above the rolling max.
    late = sig.iloc[260:]
    assert (late == 1.0).mean() > 0.9


def test_zscore_reversion_fires_on_oscillator():
    df = _sine(n=400, amp=20.0)
    sig = STRATEGIES["zscore_reversion"].fn(df, length=20, threshold=1.0)
    assert (sig == 1.0).any()
    assert (sig == -1.0).any()
