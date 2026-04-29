"""Mode 4 post-market review."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from intraday_engine.data_sources.base import SourceName
from intraday_engine.data_sources.router import fetch_candles
from intraday_engine.detectors.base import sorted_candles
from intraday_engine.ist_clock import mode_context, to_ist
from intraday_engine.output_schema import Direction, ModeContext, StrictModel, utc_now
from intraday_engine.storage.paths import REVIEWS_DIR, ensure_intraday_dirs
from intraday_engine.storage.picks import market_day, read_day_scans

ReviewOutcome = Literal["worked", "missed", "flat", "no_data"]


class PostMarketReviewRow(StrictModel):
    symbol: str
    direction: Direction
    probability: float
    scan_ltp: float
    close_ltp: float | None = None
    directional_move_pct: float | None = None
    favorable_excursion_pct: float | None = None
    adverse_excursion_pct: float | None = None
    outcome: ReviewOutcome
    scan_id: str
    notes: str


class PostMarketReview(StrictModel):
    market_date: str
    mode: ModeContext
    as_of: str
    rows: list[PostMarketReviewRow] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, int] = Field(default_factory=dict)


def run_post_market(
    *,
    source: SourceName | None = None,
    refresh: bool = False,
) -> PostMarketReview:
    cached = read_post_market_review()
    if cached is not None and not refresh:
        return cached

    scans = read_day_scans()
    rows: list[PostMarketReviewRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for scan in scans:
        for pick in scan.picks:
            if pick.symbol in seen:
                continue
            seen.add(pick.symbol)
            try:
                rows.append(_review_pick(scan.scan_id, pick, source=source or scan.source))
            except Exception as exc:
                errors.append(f"{pick.symbol}: {exc}")
                rows.append(
                    PostMarketReviewRow(
                        symbol=pick.symbol,
                        direction=pick.direction,
                        probability=pick.probability,
                        scan_ltp=pick.ltp,
                        outcome="no_data",
                        scan_id=scan.scan_id,
                        notes="Could not load day candles for review.",
                    )
                )

    summary = {
        "worked": sum(1 for row in rows if row.outcome == "worked"),
        "missed": sum(1 for row in rows if row.outcome == "missed"),
        "flat": sum(1 for row in rows if row.outcome == "flat"),
        "no_data": sum(1 for row in rows if row.outcome == "no_data"),
    }
    review = PostMarketReview(
        market_date=market_day(),
        mode=mode_context(mode_override="4", data_freshness="EOD", source=source),
        as_of=utc_now().isoformat(),
        rows=rows,
        summary=summary,
        errors=errors,
        metadata={"scan_count": len(scans), "reviewed_count": len(rows)},
    )
    write_post_market_review(review)
    return review


def read_post_market_review(day: str | None = None) -> PostMarketReview | None:
    path = _review_path(day)
    if not path.exists():
        return None
    try:
        return PostMarketReview.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_post_market_review(review: PostMarketReview) -> PostMarketReview:
    ensure_intraday_dirs()
    path = _review_path(review.market_date)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(review.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return review


def _review_path(day: str | None = None):
    ensure_intraday_dirs()
    return REVIEWS_DIR / f"{day or market_day()}.json"


def _review_pick(scan_id: str, pick, *, source: SourceName | str | None) -> PostMarketReviewRow:
    candles = sorted_candles(
        fetch_candles(
            pick.symbol,
            interval="5m",
            lookback="5d",
            source=source if source in {"nse_direct", "yfinance"} else None,
        )
    )
    if not candles:
        raise ValueError("no candles")
    scan_time = _scan_time_from_pick(pick)
    session_rows = [
        candle for candle in candles
        if to_ist(candle.timestamp).date().isoformat() == market_day()
        and (scan_time is None or candle.timestamp >= scan_time)
    ]
    if not session_rows:
        session_rows = [
            candle for candle in candles
            if to_ist(candle.timestamp).date().isoformat() == market_day()
        ] or candles
    close_ltp = session_rows[-1].close
    high = max(candle.high for candle in session_rows)
    low = min(candle.low for candle in session_rows)
    if pick.direction == "LONG":
        directional_move = (close_ltp - pick.ltp) / pick.ltp if pick.ltp else 0.0
        favorable = (high - pick.ltp) / pick.ltp if pick.ltp else 0.0
        adverse = (pick.ltp - low) / pick.ltp if pick.ltp else 0.0
    else:
        directional_move = (pick.ltp - close_ltp) / pick.ltp if pick.ltp else 0.0
        favorable = (pick.ltp - low) / pick.ltp if pick.ltp else 0.0
        adverse = (high - pick.ltp) / pick.ltp if pick.ltp else 0.0
    outcome = _classify_outcome(directional_move, favorable, adverse)
    return PostMarketReviewRow(
        symbol=pick.symbol,
        direction=pick.direction,
        probability=pick.probability,
        scan_ltp=pick.ltp,
        close_ltp=close_ltp,
        directional_move_pct=directional_move,
        favorable_excursion_pct=favorable,
        adverse_excursion_pct=adverse,
        outcome=outcome,
        scan_id=scan_id,
        notes=_notes_for_outcome(outcome),
    )


def _scan_time_from_pick(pick) -> datetime | None:
    raw = pick.metadata.get("last_candle_at") if isinstance(pick.metadata, dict) else None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def _classify_outcome(
    directional_move: float,
    favorable: float,
    adverse: float,
) -> ReviewOutcome:
    if directional_move >= 0.005 or favorable >= 0.01:
        return "worked"
    if directional_move <= -0.005 or adverse >= 0.01:
        return "missed"
    return "flat"


def _notes_for_outcome(outcome: ReviewOutcome) -> str:
    if outcome == "worked":
        return "Moved in the scan direction after selection."
    if outcome == "missed":
        return "Moved against the scan direction after selection."
    if outcome == "flat":
        return "No decisive post-scan follow-through."
    return "Review unavailable."
