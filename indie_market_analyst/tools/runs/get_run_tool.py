"""`get_run` tool — fetch a persisted backtest blob by run row id.

Lets the strategy_explainer agent ground its commentary in the actual run."""

from __future__ import annotations

from typing import Any

from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field

from indie_market_analyst.memory.store import get_store


class RunSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    symbol: str
    strategy: str
    period: str
    start_date: str
    end_date: str
    metrics: dict[str, float] = Field(default_factory=dict)
    last_trade_count: int = 0


@function_tool
def get_run(run_id: str) -> RunSummaryResult:
    """Fetch a backtest run row by id and return a compact summary the agent can quote.

    Args:
        run_id: The SQLite `runs.id` value or the blob-internal `run.run_id` returned by
            `/strategy/run`.
    """
    row: dict[str, Any] | None = get_store().get_run(run_id)
    if not row:
        raise ValueError(f"unknown run: {run_id}")
    blob = row.get("blob") or {}
    return RunSummaryResult(
        run_id=run_id,
        symbol=blob.get("symbol", ""),
        strategy=blob.get("strategy", ""),
        period=blob.get("period", ""),
        start_date=blob.get("start_date", ""),
        end_date=blob.get("end_date", ""),
        metrics={k: float(v) for k, v in (blob.get("metrics") or {}).items() if v is not None},
        last_trade_count=len(blob.get("trades") or []),
    )


TOOLS = [get_run]
