"""Mode 1A pre-market snapshot and watchlist seed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import yfinance as yf
from pydantic import Field

from intraday_engine.data_sources.nse_direct import NseDirectSource
from intraday_engine.ist_clock import freshness_label, mode_context
from intraday_engine.output_schema import DetectorDirection, ModeContext, StrictModel, utc_now
from intraday_engine.storage.paths import PREMARKET_DIR, ensure_intraday_dirs
from intraday_engine.storage.picks import market_day, read_day_scans


class MarketCue(StrictModel):
    group: Literal["global", "adr", "fx_commodity"]
    label: str
    symbol: str
    last: float | None = None
    change_pct: float | None = None
    source: str = "yfinance"
    as_of: str | None = None
    status: str = "ok"


class PremarketWatchItem(StrictModel):
    symbol: str
    bias: DetectorDirection = "NEUTRAL"
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str
    source: str


class PreMarketSnapshot(StrictModel):
    market_date: str
    mode: ModeContext
    as_of: str
    global_cues: list[MarketCue] = Field(default_factory=list)
    adrs: list[MarketCue] = Field(default_factory=list)
    fx_commodities: list[MarketCue] = Field(default_factory=list)
    fii_dii: dict[str, Any] = Field(default_factory=dict)
    watchlist: list[PremarketWatchItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


GLOBAL_CUES = (
    ("Gift Nifty proxy", "^NSEI"),
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Dow Jones", "^DJI"),
    ("Nikkei 225", "^N225"),
    ("Hang Seng", "^HSI"),
    ("Kospi", "^KS11"),
)

ADR_CUES = (
    ("Infosys ADR", "INFY", "INFY"),
    ("HDFC Bank ADR", "HDB", "HDFCBANK"),
    ("ICICI Bank ADR", "IBN", "ICICIBANK"),
    ("Wipro ADR", "WIT", "WIPRO"),
)

FX_COMMODITY_CUES = (
    ("USDINR", "INR=X"),
    ("Brent crude", "BZ=F"),
    ("US 10Y yield", "^TNX"),
)


def run_pre_market(*, refresh: bool = False) -> PreMarketSnapshot:
    cached = read_pre_market_snapshot()
    if cached is not None and not refresh:
        return cached

    errors: list[str] = []
    global_cues = _fetch_cues("global", [(label, symbol) for label, symbol in GLOBAL_CUES], errors)
    adrs = _fetch_cues("adr", [(label, symbol) for label, symbol, _ in ADR_CUES], errors)
    fx_commodities = _fetch_cues("fx_commodity", list(FX_COMMODITY_CUES), errors)
    fii_dii = _fetch_fii_dii(errors)
    watchlist = _build_watchlist(adrs)
    if not watchlist:
        watchlist = _recent_pick_watchlist()

    freshest = _freshest_timestamp([*global_cues, *adrs, *fx_commodities])
    snapshot = PreMarketSnapshot(
        market_date=market_day(),
        mode=mode_context(
            mode_override="1A",
            data_freshness=freshness_label(freshest) if freshest else "EOD",
            source="yfinance+nse_direct",
        ),
        as_of=utc_now().isoformat(),
        global_cues=global_cues,
        adrs=adrs,
        fx_commodities=fx_commodities,
        fii_dii=fii_dii,
        watchlist=watchlist,
        errors=errors,
        metadata={"watchlist_seed_count": len(watchlist)},
    )
    write_pre_market_snapshot(snapshot)
    return snapshot


def read_pre_market_snapshot(day: str | None = None) -> PreMarketSnapshot | None:
    path = _snapshot_path(day)
    if not path.exists():
        return None
    try:
        return PreMarketSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_pre_market_snapshot(snapshot: PreMarketSnapshot) -> PreMarketSnapshot:
    ensure_intraday_dirs()
    path = _snapshot_path(snapshot.market_date)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return snapshot


def read_premarket_watchlist(day: str | None = None) -> list[str]:
    snapshot = read_pre_market_snapshot(day)
    if snapshot is None:
        return []
    return [item.symbol for item in snapshot.watchlist]


def _snapshot_path(day: str | None = None):
    ensure_intraday_dirs()
    return PREMARKET_DIR / f"{day or market_day()}.json"


def _fetch_cues(
    group: Literal["global", "adr", "fx_commodity"],
    rows: list[tuple[str, str]],
    errors: list[str],
) -> list[MarketCue]:
    cues: list[MarketCue] = []
    for label, symbol in rows:
        try:
            cues.append(_fetch_yahoo_cue(group, label, symbol))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            cues.append(
                MarketCue(
                    group=group,
                    label=label,
                    symbol=symbol,
                    status="unavailable",
                )
            )
    return cues


def _fetch_yahoo_cue(
    group: Literal["global", "adr", "fx_commodity"],
    label: str,
    symbol: str,
) -> MarketCue:
    frame = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
    if frame is None or frame.empty or "Close" not in frame:
        raise ValueError("no yfinance history")
    close = frame["Close"].dropna()
    if close.empty:
        raise ValueError("no close data")
    last = float(close.iloc[-1])
    previous = float(close.iloc[-2]) if len(close) >= 2 else last
    change_pct = (last - previous) / previous if previous else None
    timestamp = frame.index[-1].to_pydatetime()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return MarketCue(
        group=group,
        label=label,
        symbol=symbol,
        last=last,
        change_pct=change_pct,
        as_of=timestamp.isoformat(),
    )


def _fetch_fii_dii(errors: list[str]) -> dict[str, Any]:
    try:
        payload = NseDirectSource()._get_json("/api/fiidiiTradeReact")
    except Exception as exc:
        errors.append(f"fii_dii: {exc}")
        return {"source": "nse_direct", "status": "unavailable", "rows": []}
    rows = payload.get("data") if isinstance(payload.get("data"), list) else []
    return {"source": "nse_direct", "status": "ok", "rows": rows}


def _build_watchlist(adrs: list[MarketCue]) -> list[PremarketWatchItem]:
    mapped = {adr_symbol: nse_symbol for _, adr_symbol, nse_symbol in ADR_CUES}
    watchlist: list[PremarketWatchItem] = []
    for cue in adrs:
        if cue.change_pct is None:
            continue
        nse_symbol = mapped.get(cue.symbol)
        if not nse_symbol or abs(cue.change_pct) < 0.005:
            continue
        bias: DetectorDirection = "LONG" if cue.change_pct > 0 else "SHORT"
        watchlist.append(
            PremarketWatchItem(
                symbol=nse_symbol,
                bias=bias,
                probability=min(0.65, 0.35 + abs(cue.change_pct) * 10),
                reason=f"{cue.label} moved {cue.change_pct * 100:.2f}%.",
                source="adr",
            )
        )
    return watchlist[:5]


def _recent_pick_watchlist() -> list[PremarketWatchItem]:
    seen: set[str] = set()
    watchlist: list[PremarketWatchItem] = []
    for scan in read_day_scans():
        for pick in scan.picks:
            if pick.symbol in seen:
                continue
            seen.add(pick.symbol)
            watchlist.append(
                PremarketWatchItem(
                    symbol=pick.symbol,
                    bias=pick.direction,
                    probability=pick.probability,
                    reason="Carried forward from the latest intraday scan.",
                    source="recent_scan",
                )
            )
            if len(watchlist) >= 5:
                return watchlist
    return watchlist


def _freshest_timestamp(cues: list[MarketCue]) -> datetime | None:
    freshest: datetime | None = None
    for cue in cues:
        if not cue.as_of:
            continue
        try:
            timestamp = datetime.fromisoformat(cue.as_of)
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if freshest is None or timestamp > freshest:
            freshest = timestamp
    return freshest
