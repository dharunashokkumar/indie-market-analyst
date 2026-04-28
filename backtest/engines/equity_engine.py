"""Minimal vectorized daily-bar equity backtester.

Signals: a pandas Series indexed by date with values in {-1, 0, 1}
(short/flat/long). Prices: a DataFrame with a ``close`` column.

Costs are applied per turnover, using the Indian cost model in ``_market_hooks``.
Per-component cost totals are preserved on the result so downstream UIs can
render a breakdown card; the engine also keeps a per-bar aggregate cost series
used for net-return computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ._market_hooks import CostConfig, costs_equity

_COST_COMPONENTS = ("brokerage", "stt", "stamp", "exch", "sebi", "gst")


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series
    cost_series: pd.Series          # per-bar total cost (INR)
    turnover: float
    total_costs: float
    cost_breakdown: dict[str, float] = field(default_factory=dict)


def run_equity(
    prices: pd.DataFrame,
    signals: pd.Series,
    initial_capital: float = 1_00_000.0,
    intraday: bool = False,
    cost_cfg: CostConfig | None = None,
) -> BacktestResult:
    if "close" not in prices.columns:
        raise ValueError("prices DataFrame must have a 'close' column")
    close = prices["close"].astype(float)
    pos = signals.reindex(close.index).fillna(0.0)

    gross_ret = pos.shift(1).fillna(0.0) * close.pct_change().fillna(0.0)
    trade_value = close * pos.diff().abs().fillna(0.0) * initial_capital / close.iloc[0]
    per_side = trade_value / 2.0

    totals = dict.fromkeys(_COST_COMPONENTS, 0.0)
    totals["total"] = 0.0
    per_bar_total: list[float] = []
    for v in per_side:
        if v > 0:
            c = costs_equity(v, v, intraday=intraday, cfg=cost_cfg)
            for k in _COST_COMPONENTS:
                totals[k] += c[k]
            totals["total"] += c["total"]
            per_bar_total.append(c["total"])
        else:
            per_bar_total.append(0.0)
    cost_series = pd.Series(per_bar_total, index=close.index)
    net_ret = gross_ret - (cost_series / initial_capital)

    equity = (1.0 + net_ret).cumprod() * initial_capital
    return BacktestResult(
        equity_curve=equity,
        returns=net_ret,
        positions=pos,
        cost_series=cost_series,
        turnover=float(pos.diff().abs().sum()),
        total_costs=float(totals["total"]),
        cost_breakdown={k: float(v) for k, v in totals.items()},
    )
