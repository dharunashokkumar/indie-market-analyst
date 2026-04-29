"""Pydantic contracts for the deterministic intraday scanner."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["LONG", "SHORT"]
DetectorDirection = Literal["LONG", "SHORT", "NEUTRAL"]
ModeId = Literal["1A", "1B", "2", "3", "4", "5", "6", "7"]
MarketState = Literal[
    "PRE_MARKET",
    "PRE_OPEN",
    "OPEN",
    "LAST_HOUR",
    "POST_MARKET",
    "CLOSED",
    "WEEKEND",
]
Conviction = Literal["fire", "confirm", "watch"]
ActivePickStatus = Literal["active", "working", "fading", "flat", "stale", "error"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_scan_id() -> str:
    return uuid4().hex[:10]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectorResult(StrictModel):
    name: str
    fired: bool
    strength: float = Field(ge=0.0, le=1.0)
    direction: DetectorDirection = "NEUTRAL"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Pick(StrictModel):
    symbol: str
    direction: Direction
    probability: float = Field(ge=0.0, le=1.0)
    detectors_fired: list[str] = Field(default_factory=list)
    detector_results: list[DetectorResult] = Field(default_factory=list)
    volume_x_avg: float = Field(ge=0.0)
    pct_change: float
    ltp: float = Field(ge=0.0)
    conviction: Conviction
    asm_gsm_tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Deliberately no entry, target, or stop fields; execution risk stays user-managed.


class ActivePick(StrictModel):
    active_id: str
    scan_id: str | None = None
    symbol: str
    pick: Pick
    activated_at: datetime = Field(default_factory=utc_now)
    status: ActivePickStatus = "active"
    last_ltp: float | None = Field(default=None, ge=0.0)
    last_checked_at: datetime | None = None
    move_from_scan_pct: float | None = None
    source: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModeContext(StrictModel):
    mode_id: ModeId
    mode_label: str
    market_state: MarketState
    ist_time: datetime
    is_market_day: bool
    data_freshness: str = "unknown"
    source: str | None = None


class ScanError(StrictModel):
    symbol: str | None = None
    stage: str
    message: str


class ScanResult(StrictModel):
    scan_id: str = Field(default_factory=new_scan_id)
    universe: str
    source: str
    interval: str = "5m"
    mode: ModeContext
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    picks: list[Pick] = Field(default_factory=list)
    watch_only: list[Pick] = Field(default_factory=list)
    errors: list[ScanError] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
