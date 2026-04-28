"""Derive trade records from a signed positions series.

The vectorized engine in ``engines/equity_engine.py`` tracks positions in
``{-1, 0, 1}``. This module post-processes that series into discrete trade
records (entry bar, exit bar, side, P&L, allocated cost) so a UI can render a
trade log without a ledger-keeping engine rewrite.

Cost allocation: each time the position changes, the engine incurs a cost
on that bar. A closed long trade covers the entry bar (open) + exit bar
(close), so we split each bar's cost across the trade(s) that use it. A flip
(long -> short) shares the flip bar 50/50 between the closing trade and the
opening one.
"""

from __future__ import annotations

import pandas as pd

from indie_market_analyst.core.schemas import TradeRecord


def _to_date(idx) -> str:
    if hasattr(idx, "date"):
        return str(idx.date())
    return str(idx)


def derive_trades(
    positions: pd.Series,
    prices: pd.Series,
    cost_series: pd.Series,
    *,
    initial_capital: float = 1_00_000.0,
) -> list[TradeRecord]:
    """Walk the positions series and emit one TradeRecord per closed round-trip.

    Args:
        positions: signed position series in {-1, 0, 1}, indexed like ``prices``.
        prices: close-price series (same index).
        cost_series: per-bar total cost in INR (same index); from engine.
        initial_capital: used to convert position -> share-count analogue.
    """
    if len(positions) == 0:
        return []
    prices = prices.astype(float)
    pos = positions.reindex(prices.index).fillna(0.0).astype(float)
    costs = cost_series.reindex(prices.index).fillna(0.0).astype(float)

    qty = initial_capital / float(prices.iloc[0])

    trades: list[TradeRecord] = []
    current_side: int = 0
    entry_bar: int | None = None
    accrued_cost: float = 0.0

    values = pos.tolist()
    index = list(pos.index)

    def _close_trade(exit_bar_idx: int, split_cost: float) -> None:
        nonlocal current_side, entry_bar, accrued_cost
        if entry_bar is None or current_side == 0:
            return
        entry_price = float(prices.iloc[entry_bar])
        exit_price = float(prices.iloc[exit_bar_idx])
        gross = (exit_price - entry_price) * qty * current_side
        cost = accrued_cost + split_cost
        pnl = gross - cost
        notional = entry_price * qty
        ret_pct = (pnl / notional) if notional else 0.0
        trades.append(
            TradeRecord(
                entry_date=_to_date(index[entry_bar]),
                exit_date=_to_date(index[exit_bar_idx]),
                side="long" if current_side > 0 else "short",
                entry_price=entry_price,
                exit_price=exit_price,
                qty=qty,
                pnl=pnl,
                cost=cost,
                return_pct=ret_pct,
            )
        )
        current_side = 0
        entry_bar = None
        accrued_cost = 0.0

    for i, side in enumerate(values):
        side_int = int(side)
        if current_side == 0 and side_int != 0:
            current_side = side_int
            entry_bar = i
            accrued_cost = float(costs.iloc[i])
            continue
        if current_side != 0 and side_int == current_side:
            continue
        if current_side != 0 and side_int == 0:
            _close_trade(i, float(costs.iloc[i]))
            continue
        if current_side != 0 and side_int != 0 and side_int != current_side:
            # Flip: share this bar's cost between the closed trade and the new one.
            split = float(costs.iloc[i]) / 2.0
            _close_trade(i, split)
            current_side = side_int
            entry_bar = i
            accrued_cost = split

    if current_side != 0 and entry_bar is not None:
        # Close on the last bar if still open (no final flat).
        last = len(values) - 1
        _close_trade(last, 0.0)

    return trades
