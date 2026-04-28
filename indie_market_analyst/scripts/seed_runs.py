"""Seed the SQLite `runs` table with real backtests so the dashboards UI has
data to render on a fresh clone.

By default seeds a basket of five liquid Nifty50 symbols (RELIANCE, TCS,
HDFCBANK, INFY, ITC) each with SMA(20/50) long-only, 1y daily. Symbols can be
overridden on the command line.

    uv run python -m indie_market_analyst.scripts.seed_runs
    uv run python -m indie_market_analyst.scripts.seed_runs RELIANCE.NS TCS.NS
"""

from __future__ import annotations

import sys

import pandas as pd

from backtest.loaders import yfinance_loader as _yf_loader  # noqa: F401  -- registers loader
from backtest.loaders.registry import load
from backtest.runner import run

DEFAULT_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]


def _sma_crossover_signals(close: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    sma_fast = close.rolling(fast).mean()
    sma_slow = close.rolling(slow).mean()
    sig = (sma_fast > sma_slow).astype(float)  # 1.0 long, 0.0 flat
    return sig.fillna(0.0)


def _seed_one(symbol: str, period: str) -> str | None:
    df = load("yfinance", symbol=symbol, period=period, interval="1d")
    if df.empty:
        print(f"  skip {symbol}: no data", file=sys.stderr)
        return None
    signals = _sma_crossover_signals(df["close"])
    blob = run(
        symbol=symbol, signals=signals,
        period=period, interval="1d",
        strategy="sma_crossover_20_50",
        session_id="system",
    )
    print(
        f"  {symbol:14s} sharpe={blob['metrics']['sharpe']:+.3f}  "
        f"max_dd={blob['metrics']['max_drawdown']:+.3f}  "
        f"costs=₹{blob['costs']['total']:.2f}  run={blob['run_id'][:8]}"
    )
    return blob["run_id"]


def main(symbols: list[str] | None = None, period: str = "1y") -> list[str]:
    syms = symbols or DEFAULT_SYMBOLS
    print(f"seeding {len(syms)} backtest(s), period={period} ...")
    ids: list[str] = []
    for s in syms:
        rid = _seed_one(s, period)
        if rid:
            ids.append(rid)
    print(f"done: {len(ids)} run(s) persisted.")
    return ids


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0].lower() in {"-h", "--help"}:
        print(__doc__)
        sys.exit(0)
    main(symbols=args or None)
