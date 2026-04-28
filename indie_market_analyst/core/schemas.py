"""Universal Pydantic schemas passed between agents in the swarm.

Every specialist agent declares one of these (or a subclass) as its `output_type`
so handoffs carry typed data, not free prose.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# ---------- shared primitives ----------

class DataPoint(_Strict):
    """A single verified fact pulled from a tool call."""
    symbol: str
    field: str                        # e.g. "close", "volume", "oi", "iv"
    value: float
    as_of: datetime
    source: str                       # "yfinance" | "nse_bhavcopy" | "google_finance" | ...
    exchange: Literal["NSE", "BSE", "NFO", "BFO", "OTHER"] = "NSE"
    unit: str = "INR"


class ToolCallTrace(_Strict):
    tool: str
    args: dict[str, Any]
    ok: bool
    error: str | None = None
    at: datetime


# ---------- agent IO contracts ----------

class CollectorOutput(_Strict):
    """Raw, verified data scraped by the Collector agent."""
    session_id: str
    universe: list[str]               # symbols touched this run
    points: list[DataPoint]
    traces: list[ToolCallTrace] = Field(default_factory=list)


class VerifiedFacts(_Strict):
    """Collector output after the Verifier cross-checks sources."""
    session_id: str
    points: list[DataPoint]
    rejected: list[DataPoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Calculation(_Strict):
    name: str                         # "nifty_daily_return", "adv_decline_ratio", etc.
    value: float
    unit: str = ""
    inputs: list[str] = Field(default_factory=list)  # references to DataPoint ids


class CalculationBundle(_Strict):
    session_id: str
    calculations: list[Calculation]
    warnings: list[str] = Field(default_factory=list)


class ReportDraft(_Strict):
    """What the Report Writer hands back to the orchestrator."""
    session_id: str
    title: str
    markdown: str
    pdf_path: str | None = None


class AnalystTurn(_Strict):
    """Final user-facing response envelope."""
    session_id: str
    run_id: str
    message_markdown: str
    artifacts: list[str] = Field(default_factory=list)  # file paths
    used_tools: list[str] = Field(default_factory=list)


class EquityResearchNote(_Strict):
    """Structured output for the equity_researcher agent.

    Constrains the agent to return typed fields so it cannot emit free-form
    reasoning as the user-facing answer. A small formatter converts this to
    markdown downstream.
    """
    symbol: str
    exchange: Literal["NSE", "BSE", "NFO", "BFO", "OTHER"] = "NSE"
    as_of: datetime
    last_price: DataPoint
    technicals: list[DataPoint] = Field(default_factory=list)
    setup: str                              # short, plain-prose setup description
    invalidation: str                       # short, plain-prose invalidation level
    sources: list[str] = Field(default_factory=list)
    message_markdown: str | None = None     # optional pre-rendered markdown


# ---------- backtest persistence ----------

class EquityPoint(_Strict):
    date: str                               # ISO date (YYYY-MM-DD)
    equity: float


class CostBreakdown(_Strict):
    """Aggregated per-component cost totals for a full backtest."""
    brokerage: float = 0.0
    stt: float = 0.0
    stamp: float = 0.0
    exch: float = 0.0
    sebi: float = 0.0
    gst: float = 0.0
    total: float = 0.0


class TradeRecord(_Strict):
    """A synthesized trade derived from the positions series."""
    entry_date: str
    exit_date: str
    side: Literal["long", "short"]
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    cost: float
    return_pct: float


class BacktestRunBlob(_Strict):
    """Full backtest run payload persisted to the SQLite `runs` table."""
    run_id: str
    symbol: str
    strategy: str = "custom"
    period: str
    interval: str
    initial_capital: float
    intraday: bool
    as_of_utc: str
    source: str = "backtest"
    start_date: str
    end_date: str
    metrics: dict[str, float]               # matches backtest/metrics.summary() byte-for-byte
    costs: CostBreakdown
    turnover: float
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    artifact_path: str | None = None


# ---------- strategy dashboard ----------

class StrategySpec(_Strict):
    """Strategy registry entry exposed via /strategy/list."""
    name: str
    category: Literal["trend", "mean_reversion", "breakout", "momentum"]
    label: str
    description: str
    default_params: dict[str, float | int]


class StrategyRunResponse(_Strict):
    """POST /strategy/run response — full backtest blob + the live signal snapshot."""
    run: BacktestRunBlob
    current_signal: Literal["LONG", "FLAT", "SHORT"]
    signal_age_bars: int
    last_close: float


class StrategyExplanation(_Strict):
    """Output of the strategy_explainer swarm agent."""
    summary_markdown: str
    regime: Literal["trending", "ranging", "volatile", "quiet"]
    confidence: Literal["low", "medium", "high"]
    caveats: list[str] = Field(default_factory=list)


# ---------- heatmap ----------

class HeatmapCell(_Strict):
    symbol: str
    name: str
    last: float | None
    change_pct: float | None
    as_of_utc: str
    source: str = "yfinance"


class IndexHeatmapSnapshot(_Strict):
    """Point-in-time snapshot of Nifty50/BankNifty constituents + sectoral indices."""
    nifty50: list[HeatmapCell] = Field(default_factory=list)
    banknifty: list[HeatmapCell] = Field(default_factory=list)
    sectors: list[HeatmapCell] = Field(default_factory=list)
    as_of_utc: str
    source: str = "yfinance"
