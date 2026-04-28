"""End-to-end backtest orchestrator (imperative)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from indie_market_analyst.core.schemas import (
    BacktestRunBlob,
    CostBreakdown,
    EquityPoint,
)
from indie_market_analyst.memory.store import get_store

from . import loaders  # noqa: F401  -- registers loaders
from .engines.equity_engine import BacktestResult, run_equity
from .loaders.registry import load
from .metrics import summary
from .trades import derive_trades


def _equity_points(equity: pd.Series) -> list[EquityPoint]:
    out: list[EquityPoint] = []
    for idx, val in equity.items():
        d = idx.date() if hasattr(idx, "date") else idx
        out.append(EquityPoint(date=str(d), equity=float(val)))
    return out


def run(
    symbol: str, signals: pd.Series, *,
    period: str = "1y", interval: str = "1d",
    initial_capital: float = 1_00_000.0, intraday: bool = False,
    loader: str = "yfinance", out_dir: str | Path = "runs",
    session_id: str = "system", strategy: str = "custom",
    persist: bool = True,
    data: pd.DataFrame | None = None,
) -> dict[str, Any]:
    df = (
        data.copy()
        if data is not None
        else load(loader, symbol=symbol, period=period, interval=interval)
    )
    result: BacktestResult = run_equity(df, signals, initial_capital, intraday=intraday)
    stats = summary(result.equity_curve, result.returns)
    trades = derive_trades(
        result.positions, df["close"], result.cost_series,
        initial_capital=initial_capital,
    )

    equity_points = _equity_points(result.equity_curve)
    run_id = str(uuid.uuid4())
    start_date = equity_points[0].date if equity_points else ""
    end_date = equity_points[-1].date if equity_points else ""

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    artifact_path = Path(out_dir) / f"backtest_{run_id[:8]}.json"

    blob = BacktestRunBlob(
        run_id=run_id,
        symbol=symbol,
        strategy=strategy,
        period=period,
        interval=interval,
        initial_capital=initial_capital,
        intraday=intraday,
        as_of_utc=datetime.now(UTC).isoformat(),
        start_date=start_date,
        end_date=end_date,
        metrics=stats,
        costs=CostBreakdown(**result.cost_breakdown),
        turnover=float(result.turnover),
        trades=trades,
        equity_curve=equity_points,
        artifact_path=str(artifact_path),
    )
    blob_dict = blob.model_dump(mode="json")
    artifact_path.write_text(json.dumps(blob_dict, indent=2))

    if persist:
        get_store().save_run(
            session_id=session_id, kind="backtest", status="ok", blob=blob_dict,
            run_id=run_id,
        )
    return blob_dict
