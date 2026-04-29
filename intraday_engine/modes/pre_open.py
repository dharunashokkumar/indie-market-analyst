"""Mode 1B pre-open auction snapshot."""

from __future__ import annotations

from pydantic import Field

from intraday_engine.data_sources.base import PreOpenRow, SourceName
from intraday_engine.data_sources.router import fetch_preopen
from intraday_engine.ist_clock import mode_context
from intraday_engine.output_schema import DetectorDirection, ModeContext, StrictModel, utc_now
from intraday_engine.storage.paths import PREMARKET_DIR, ensure_intraday_dirs
from intraday_engine.storage.picks import market_day


class PreOpenWatchItem(StrictModel):
    symbol: str
    bias: DetectorDirection = "NEUTRAL"
    pct_change: float | None = None
    ltp: float | None = None
    volume: float | None = None
    reason: str


class PreOpenSnapshotRow(StrictModel):
    symbol: str
    ltp: float | None = None
    indicative_open: float | None = None
    pct_change: float | None = None
    volume: float | None = None


class PreOpenSnapshot(StrictModel):
    market_date: str
    mode: ModeContext
    as_of: str
    rows: list[PreOpenSnapshotRow] = Field(default_factory=list)
    watchlist: list[PreOpenWatchItem] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, int] = Field(default_factory=dict)


def run_pre_open(
    *,
    source: SourceName | None = "nse_direct",
    refresh: bool = False,
) -> PreOpenSnapshot:
    cached = read_pre_open_snapshot()
    if cached is not None and not refresh:
        return cached

    errors: list[str] = []
    raw_rows: list[PreOpenRow] = []
    try:
        raw_rows = fetch_preopen(source=source)
    except Exception as exc:
        errors.append(str(exc))
    rows = [_compact_row(row) for row in raw_rows]
    watchlist = _build_watchlist(rows)
    snapshot = PreOpenSnapshot(
        market_date=market_day(),
        mode=mode_context(mode_override="1B", data_freshness="live", source=source),
        as_of=utc_now().isoformat(),
        rows=rows,
        watchlist=watchlist,
        errors=errors,
        metadata={"row_count": len(rows), "watchlist_count": len(watchlist)},
    )
    write_pre_open_snapshot(snapshot)
    return snapshot


def read_pre_open_snapshot(day: str | None = None) -> PreOpenSnapshot | None:
    path = _snapshot_path(day)
    if not path.exists():
        return None
    try:
        return PreOpenSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_pre_open_snapshot(snapshot: PreOpenSnapshot) -> PreOpenSnapshot:
    ensure_intraday_dirs()
    path = _snapshot_path(snapshot.market_date)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return snapshot


def _snapshot_path(day: str | None = None):
    ensure_intraday_dirs()
    return PREMARKET_DIR / f"preopen_{day or market_day()}.json"


def _compact_row(row: PreOpenRow) -> PreOpenSnapshotRow:
    return PreOpenSnapshotRow(
        symbol=row.symbol,
        ltp=row.ltp,
        indicative_open=row.indicative_open,
        pct_change=row.pct_change,
        volume=row.volume or _raw_volume(row),
    )


def _raw_volume(row: PreOpenRow) -> float | None:
    meta = row.raw.get("metadata") if isinstance(row.raw.get("metadata"), dict) else {}
    detail = row.raw.get("detail") if isinstance(row.raw.get("detail"), dict) else {}
    market = (
        detail.get("preOpenMarket")
        if isinstance(detail.get("preOpenMarket"), dict)
        else {}
    )
    for value in (
        meta.get("finalQuantity"),
        market.get("totalTradedVolume"),
        meta.get("quantity"),
    ):
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _build_watchlist(rows: list[PreOpenSnapshotRow]) -> list[PreOpenWatchItem]:
    ranked = sorted(
        rows,
        key=lambda row: (
            abs(row.pct_change or 0.0),
            row.volume or 0.0,
        ),
        reverse=True,
    )
    watchlist: list[PreOpenWatchItem] = []
    for row in ranked[:8]:
        bias: DetectorDirection = "NEUTRAL"
        if row.pct_change is not None and row.pct_change > 0.005:
            bias = "LONG"
        elif row.pct_change is not None and row.pct_change < -0.005:
            bias = "SHORT"
        watchlist.append(
            PreOpenWatchItem(
                symbol=row.symbol,
                bias=bias,
                pct_change=row.pct_change,
                ltp=row.ltp or row.indicative_open,
                volume=row.volume,
                reason="Ranked by indicative move and auction volume.",
            )
        )
    return watchlist
