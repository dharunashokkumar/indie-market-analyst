"""IST clock helpers and mode auto-detection for intraday workflows."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from intraday_engine.output_schema import MarketState, ModeContext, ModeId

IST = ZoneInfo("Asia/Kolkata")

PRE_OPEN_START = time(9, 0)
MARKET_OPEN = time(9, 15)
LAST_HOUR_START = time(14, 30)
MARKET_CLOSE = time(15, 30)

MODE_LABELS: dict[ModeId, str] = {
    "1A": "Mode 1A - PRE-MARKET",
    "1B": "Mode 1B - PRE-OPEN",
    "2": "Mode 2 - LIVE",
    "3": "Mode 3 - LAST HOUR",
    "4": "Mode 4 - POST-MARKET",
    "5": "Mode 5 - SPECIFIC STOCK",
    "6": "Mode 6 - UPDATE",
    "7": "Mode 7 - WEEKEND",
}


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(value: datetime | None = None) -> datetime:
    if value is None:
        return now_ist()
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def is_market_day(value: datetime | None = None) -> bool:
    return to_ist(value).weekday() < 5


def market_state(value: datetime | None = None) -> MarketState:
    current = to_ist(value)
    if current.weekday() >= 5:
        return "WEEKEND"

    current_time = current.time()
    if current_time < PRE_OPEN_START:
        return "PRE_MARKET"
    if PRE_OPEN_START <= current_time < MARKET_OPEN:
        return "PRE_OPEN"
    if MARKET_OPEN <= current_time < LAST_HOUR_START:
        return "OPEN"
    if LAST_HOUR_START <= current_time <= MARKET_CLOSE:
        return "LAST_HOUR"
    if current_time > MARKET_CLOSE:
        return "POST_MARKET"
    return "CLOSED"


def auto_detect_mode(value: datetime | None = None) -> ModeId:
    state = market_state(value)
    if state == "WEEKEND":
        return "7"
    if state == "PRE_MARKET":
        return "1A"
    if state == "PRE_OPEN":
        return "1B"
    if state == "OPEN":
        return "2"
    if state == "LAST_HOUR":
        return "3"
    if state == "POST_MARKET":
        return "4"
    return "1A"


def normalize_mode_id(value: str | int) -> ModeId:
    raw = str(value).strip().upper()
    aliases = {
        "PRE_MARKET": "1A",
        "PRE-MARKET": "1A",
        "PREOPEN": "1B",
        "PRE_OPEN": "1B",
        "PRE-OPEN": "1B",
        "LIVE": "2",
        "LAST_HOUR": "3",
        "LAST-HOUR": "3",
        "POST_MARKET": "4",
        "POST-MARKET": "4",
        "SPECIFIC_STOCK": "5",
        "SPECIFIC-STOCK": "5",
        "UPDATE": "6",
        "WEEKEND": "7",
    }
    raw = aliases.get(raw, raw)
    if raw in MODE_LABELS:
        return raw  # type: ignore[return-value]
    raise ValueError(f"unknown intraday mode: {value}")


def freshness_label(fetched_at: datetime | None, value: datetime | None = None) -> str:
    if fetched_at is None:
        return "unknown"
    current = to_ist(value)
    fetched = to_ist(fetched_at)
    age_seconds = max(0, int((current - fetched).total_seconds()))
    if age_seconds <= 60:
        return "live"
    minutes = max(1, round(age_seconds / 60))
    return f"{minutes}m delayed"


def mode_context(
    value: datetime | None = None,
    *,
    mode_override: str | int | None = None,
    data_freshness: str = "unknown",
    source: str | None = None,
) -> ModeContext:
    current = to_ist(value)
    mode_id = (
        normalize_mode_id(mode_override)
        if mode_override is not None
        else auto_detect_mode(current)
    )
    return ModeContext(
        mode_id=mode_id,
        mode_label=MODE_LABELS[mode_id],
        market_state=market_state(current),
        ist_time=current,
        is_market_day=is_market_day(current),
        data_freshness=data_freshness,
        source=source,
    )
