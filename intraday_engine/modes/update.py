"""Mode 6 active-pick status updates."""

from __future__ import annotations

from pydantic import field_validator

from intraday_engine.data_sources.base import SourceName
from intraday_engine.data_sources.router import fetch_quote
from intraday_engine.ist_clock import freshness_label, mode_context
from intraday_engine.output_schema import (
    ActivePick,
    ActivePickStatus,
    ModeContext,
    Pick,
    StrictModel,
    utc_now,
)
from intraday_engine.storage.picks import find_pick, read_active, upsert_active_pick, write_active


class ActivePickRequest(StrictModel):
    symbol: str
    scan_id: str | None = None
    pick: Pick | None = None
    source: SourceName | None = None

    @field_validator("symbol")
    @classmethod
    def clean_symbol(cls, value: str) -> str:
        clean = value.strip().upper()
        if not clean:
            raise ValueError("symbol is required")
        return clean


class ActivePicksResponse(StrictModel):
    mode: ModeContext
    active: list[ActivePick]
    as_of: str


def mark_active_pick(request: ActivePickRequest) -> ActivePicksResponse:
    pick = request.pick or find_pick(request.symbol, scan_id=request.scan_id)
    if pick is None:
        raise ValueError(f"pick not found for {request.symbol}")
    upsert_active_pick(pick, scan_id=request.scan_id)
    return recompute_active_picks(source=request.source)


def recompute_active_picks(source: SourceName | None = None) -> ActivePicksResponse:
    records = read_active()
    updated: list[ActivePick] = []
    freshest = None
    for record in records:
        try:
            quote = fetch_quote(record.symbol, source=source)
            freshest = quote.as_of if freshest is None or quote.as_of > freshest else freshest
            status, move, message = _status_from_quote(record.pick, quote.ltp)
            updated.append(
                record.model_copy(
                    update={
                        "status": status,
                        "last_ltp": quote.ltp,
                        "last_checked_at": utc_now(),
                        "move_from_scan_pct": move,
                        "source": quote.source,
                        "message": message,
                    }
                )
            )
        except Exception as exc:
            updated.append(
                record.model_copy(
                    update={
                        "status": "error",
                        "last_checked_at": utc_now(),
                        "message": str(exc),
                    }
                )
            )
    if updated:
        write_active(updated)
    return ActivePicksResponse(
        mode=mode_context(
            mode_override="6",
            data_freshness=freshness_label(freshest),
            source=source,
        ),
        active=updated,
        as_of=utc_now().isoformat(),
    )


def _status_from_quote(pick: Pick, ltp: float) -> tuple[ActivePickStatus, float, str]:
    if pick.ltp <= 0:
        return "stale", 0.0, "Original scan price unavailable."
    raw_move = (ltp - pick.ltp) / pick.ltp
    directional_move = raw_move if pick.direction == "LONG" else -raw_move
    if directional_move >= 0.005:
        return "working", directional_move, "Moving in the scan direction."
    if directional_move <= -0.005:
        return "fading", directional_move, "Moving against the scan direction."
    if abs(directional_move) < 0.0015:
        return "flat", directional_move, "Near the original scan price."
    return "active", directional_move, "Still active, no decisive move yet."
