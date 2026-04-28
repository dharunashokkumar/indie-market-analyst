"""Tests for backtest.trades.derive_trades."""

from __future__ import annotations

import pandas as pd

from backtest.trades import derive_trades


def _series(vals: list[float], dates: list[str]) -> pd.Series:
    return pd.Series(vals, index=pd.to_datetime(dates))


def test_flat_series_produces_no_trades():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    prices = _series([100.0, 101.0, 102.0], dates)
    positions = _series([0.0, 0.0, 0.0], dates)
    costs = _series([0.0, 0.0, 0.0], dates)
    assert derive_trades(positions, prices, costs) == []


def test_single_long_round_trip_pnl_and_side():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    prices = _series([100.0, 105.0, 110.0, 108.0], dates)
    positions = _series([0.0, 1.0, 1.0, 0.0], dates)
    costs = _series([0.0, 10.0, 0.0, 5.0], dates)  # entry + exit bar costs
    trades = derive_trades(positions, prices, costs, initial_capital=100_000.0)
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "long"
    assert t.entry_date == "2024-01-03"
    assert t.exit_date == "2024-01-05"
    assert t.entry_price == 105.0
    assert t.exit_price == 108.0
    assert t.cost == 15.0
    assert t.pnl == (108.0 - 105.0) * (100_000.0 / 100.0) - 15.0


def test_flip_long_to_short_splits_flip_bar_cost():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    prices = _series([100.0, 110.0, 120.0, 115.0], dates)
    positions = _series([1.0, 1.0, -1.0, -1.0], dates)  # open long, flip to short
    costs = _series([8.0, 0.0, 20.0, 0.0], dates)      # flip bar carries 20
    trades = derive_trades(positions, prices, costs, initial_capital=100_000.0)
    assert len(trades) == 2
    long_trade, short_trade = trades
    assert long_trade.side == "long"
    assert long_trade.cost == 8.0 + 10.0   # entry cost + half of flip cost
    assert short_trade.side == "short"
    # short still open at end of series: closed on last bar with 0 exit cost
    assert short_trade.entry_date == "2024-01-04"
    assert short_trade.exit_date == "2024-01-05"
    # short P&L is (entry - exit) * qty, qty = 100000 / 100 = 1000
    assert short_trade.pnl == (120.0 - 115.0) * 1000.0 - (10.0 + 0.0)


def test_short_round_trip():
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    prices = _series([200.0, 210.0, 190.0, 190.0], dates)
    positions = _series([0.0, -1.0, -1.0, 0.0], dates)
    costs = _series([0.0, 3.0, 0.0, 2.0], dates)
    trades = derive_trades(positions, prices, costs, initial_capital=200_000.0)
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "short"
    # qty = 200000 / 200 = 1000
    assert t.pnl == (210.0 - 190.0) * 1000.0 - 5.0
