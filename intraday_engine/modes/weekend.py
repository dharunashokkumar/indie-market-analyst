"""Mode 7 weekend planning snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yfinance as yf
from pydantic import Field

from intraday_engine.data_sources.nse_direct import NseDirectSource
from intraday_engine.ist_clock import mode_context, to_ist
from intraday_engine.output_schema import (
    DetectorDirection,
    ModeContext,
    ScanResult,
    StrictModel,
    utc_now,
)
from intraday_engine.storage.paths import PICKS_DIR, WEEKEND_DIR, ensure_intraday_dirs


class WeekendCue(StrictModel):
    label: str
    symbol: str
    weekly_change_pct: float | None = None
    last: float | None = None
    source: str = "yfinance"
    status: str = "ok"


class WeekendWatchItem(StrictModel):
    symbol: str
    bias: DetectorDirection
    probability: float
    reason: str
    source_scan_id: str


class WeekendSnapshot(StrictModel):
    week_key: str
    mode: ModeContext
    as_of: str
    global_cues: list[WeekendCue] = Field(default_factory=list)
    fii_dii_summary: dict[str, Any] = Field(default_factory=dict)
    earnings_calendar: list[dict[str, Any]] = Field(default_factory=list)
    watchlist: list[WeekendWatchItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, int] = Field(default_factory=dict)


WEEKEND_CUES = (
    ("Nifty 50", "^NSEI"),
    ("Bank Nifty", "^NSEBANK"),
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Brent crude", "BZ=F"),
    ("USDINR", "INR=X"),
)


def run_weekend(*, refresh: bool = False) -> WeekendSnapshot:
    cached = read_weekend_snapshot()
    if cached is not None and not refresh:
        return cached

    errors: list[str] = []
    global_cues = _fetch_weekend_cues(errors)
    fii_dii_summary = _fetch_weekly_fii_dii(errors)
    earnings_calendar = _fetch_earnings_calendar(errors)
    watchlist = _recent_scan_watchlist()
    snapshot = WeekendSnapshot(
        week_key=week_key(),
        mode=mode_context(mode_override="7", data_freshness="EOD", source="yfinance+nse_direct"),
        as_of=utc_now().isoformat(),
        global_cues=global_cues,
        fii_dii_summary=fii_dii_summary,
        earnings_calendar=earnings_calendar,
        watchlist=watchlist,
        errors=errors,
        metadata={
            "watchlist_count": len(watchlist),
            "earnings_count": len(earnings_calendar),
        },
    )
    write_weekend_snapshot(snapshot)
    return snapshot


def week_key(value: datetime | None = None) -> str:
    current = to_ist(value)
    year, week, _ = current.isocalendar()
    return f"{year}-{week:02d}"


def read_weekend_snapshot(key: str | None = None) -> WeekendSnapshot | None:
    path = _snapshot_path(key)
    if not path.exists():
        return None
    try:
        return WeekendSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_weekend_snapshot(snapshot: WeekendSnapshot) -> WeekendSnapshot:
    ensure_intraday_dirs()
    path = _snapshot_path(snapshot.week_key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return snapshot


def _snapshot_path(key: str | None = None):
    ensure_intraday_dirs()
    return WEEKEND_DIR / f"{key or week_key()}.json"


def _fetch_weekend_cues(errors: list[str]) -> list[WeekendCue]:
    cues: list[WeekendCue] = []
    for label, symbol in WEEKEND_CUES:
        try:
            frame = yf.Ticker(symbol).history(period="7d", interval="1d", auto_adjust=False)
            if frame is None or frame.empty or "Close" not in frame:
                raise ValueError("no yfinance history")
            close = frame["Close"].dropna()
            if close.empty:
                raise ValueError("no close data")
            first = float(close.iloc[0])
            last = float(close.iloc[-1])
            cues.append(
                WeekendCue(
                    label=label,
                    symbol=symbol,
                    weekly_change_pct=(last - first) / first if first else None,
                    last=last,
                )
            )
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            cues.append(WeekendCue(label=label, symbol=symbol, status="unavailable"))
    return cues


def _fetch_weekly_fii_dii(errors: list[str]) -> dict[str, Any]:
    try:
        payload = NseDirectSource()._get_json("/api/fiidiiTradeReact")
    except Exception as exc:
        errors.append(f"fii_dii: {exc}")
        return {"source": "nse_direct", "status": "unavailable", "rows": []}
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    return {"source": "nse_direct", "status": "ok", "rows": rows}


def _fetch_earnings_calendar(errors: list[str]) -> list[dict[str, Any]]:
    try:
        payload = NseDirectSource()._get_json(
            "/api/event-calendar",
            params={"index": "equities"},
        )
    except Exception as exc:
        errors.append(f"earnings_calendar: {exc}")
        return []
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    return [row for row in rows if isinstance(row, dict)][:40]


def _recent_scan_watchlist(limit: int = 10) -> list[WeekendWatchItem]:
    picks: list[WeekendWatchItem] = []
    seen: set[str] = set()
    for scan in _recent_scans():
        for pick in sorted(scan.picks, key=lambda item: item.probability, reverse=True):
            if pick.symbol in seen:
                continue
            seen.add(pick.symbol)
            picks.append(
                WeekendWatchItem(
                    symbol=pick.symbol,
                    bias=pick.direction,
                    probability=pick.probability,
                    reason="High-probability intraday setup from the latest stored scans.",
                    source_scan_id=scan.scan_id,
                )
            )
            if len(picks) >= limit:
                return picks
    return picks


def _recent_scans() -> list[ScanResult]:
    ensure_intraday_dirs()
    rows: list[ScanResult] = []
    for day_dir in sorted(PICKS_DIR.glob("*"), reverse=True):
        if not day_dir.is_dir():
            continue
        for scan_file in sorted(day_dir.glob("scan_*.json"), reverse=True):
            try:
                rows.append(ScanResult.model_validate_json(scan_file.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        if len(rows) >= 20:
            break
    rows.sort(key=lambda scan: scan.created_at, reverse=True)
    return rows


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
