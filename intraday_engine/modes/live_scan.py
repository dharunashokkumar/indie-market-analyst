"""Mode 2 live-scan orchestration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from pydantic import Field, field_validator

from intraday_engine.data_sources.base import Candle, SourceName
from intraday_engine.data_sources.router import fetch_candles
from intraday_engine.data_sources.settings_store import UniverseName, load_settings
from intraday_engine.detectors import run_all_detectors
from intraday_engine.detectors.base import (
    bars_for_minutes,
    cumulative_vwap,
    daily_volume_ratio,
    fired,
    latest_session_candles,
    session_pct_change,
    sorted_candles,
)
from intraday_engine.filters.apply import apply_filters
from intraday_engine.ist_clock import freshness_label, mode_context, to_ist
from intraday_engine.output_schema import (
    DetectorDirection,
    DetectorResult,
    Pick,
    ScanError,
    ScanResult,
    StrictModel,
    utc_now,
)
from intraday_engine.scoring import (
    classify_direction,
    conviction_for_probability,
    probability_score,
)
from intraday_engine.storage.picks import append_scan_result
from intraday_engine.universe.builder import UniverseSymbol, build_universe

MIN_DETECTORS_FIRED = 2
MIN_VOLUME_X_AVG = 3.0
MIN_PROBABILITY = 0.30
TOP_PICK_LIMIT = 5
WATCH_ONLY_LIMIT = 20
DEFAULT_SCAN_CONCURRENCY = 8


class LiveScanRequest(StrictModel):
    universe: UniverseName | None = None
    source: SourceName | None = None
    source_override: SourceName | None = None
    mode: str | int | None = None
    mode_override: str | int | None = None
    interval: str = "5m"
    lookback: str = "20d"
    merge_movers: bool = True
    max_symbols: int | None = Field(default=None, ge=1, le=3000)
    enforce_liquidity: bool = True
    min_detectors_fired: int = Field(default=MIN_DETECTORS_FIRED, ge=1, le=6)
    min_volume_x_avg: float = Field(default=MIN_VOLUME_X_AVG, ge=0.0)
    min_probability: float = Field(default=MIN_PROBABILITY, ge=0.0, le=1.0)
    top_pick_limit: int = Field(default=TOP_PICK_LIMIT, ge=1, le=20)
    watch_only_limit: int = Field(default=WATCH_ONLY_LIMIT, ge=0, le=100)
    include_premarket_watchlist: bool = True
    scan_concurrency: int = Field(default=DEFAULT_SCAN_CONCURRENCY, ge=1, le=32)

    @field_validator("interval", "lookback")
    @classmethod
    def clean_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("value cannot be empty")
        return clean

    @property
    def selected_source(self) -> SourceName | None:
        return self.source_override or self.source

    @property
    def selected_mode(self) -> str | int | None:
        return self.mode_override or self.mode


class OverlayPoint(StrictModel):
    time: datetime
    value: float


class DetectorOverlayPoint(StrictModel):
    time: datetime
    detector: str
    direction: DetectorDirection
    strength: float
    reason: str | None = None


class ChartOverlays(StrictModel):
    vwap: list[OverlayPoint] = Field(default_factory=list)
    orb_high: list[OverlayPoint] = Field(default_factory=list)
    orb_low: list[OverlayPoint] = Field(default_factory=list)
    prev_day_high: list[OverlayPoint] = Field(default_factory=list)
    prev_day_low: list[OverlayPoint] = Field(default_factory=list)
    ma20: list[OverlayPoint] = Field(default_factory=list)
    ma50: list[OverlayPoint] = Field(default_factory=list)
    volume_ma: list[OverlayPoint] = Field(default_factory=list)
    pivot: list[OverlayPoint] = Field(default_factory=list)
    r1: list[OverlayPoint] = Field(default_factory=list)
    s1: list[OverlayPoint] = Field(default_factory=list)
    detector_points: list[DetectorOverlayPoint] = Field(default_factory=list)


class ChartResponse(StrictModel):
    symbol: str
    interval: str
    source: str
    candles: list[Candle]
    overlays: ChartOverlays
    detector_results: list[DetectorResult]
    as_of: datetime


def run_live_scan(request: LiveScanRequest | None = None) -> ScanResult:
    request = request or LiveScanRequest()
    settings = load_settings()
    universe_name = request.universe or settings.default_universe
    source_name = request.selected_source or settings.default_source
    universe = build_universe(universe_name, merge_movers=request.merge_movers)
    seeded_symbols, premarket_seed_count = _with_premarket_seed(universe.symbols, request)
    symbols = seeded_symbols[: request.max_symbols] if request.max_symbols else seeded_symbols

    candles_by_symbol: dict[str, list[Candle]] = {}
    errors: list[ScanError] = []
    latest_candle_at: datetime | None = None
    max_workers = min(request.scan_concurrency, max(1, len(symbols)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_fetch_symbol_candles, item, request=request, source=source_name)
            for item in symbols
        ]
        for future in as_completed(futures):
            symbol, candles, error = future.result()
            if error is not None:
                errors.append(error)
                continue
            if not candles:
                errors.append(
                    ScanError(symbol=symbol, stage="candles", message="no candles returned")
                )
                continue
            candles_by_symbol[symbol] = candles
            if latest_candle_at is None or candles[-1].timestamp > latest_candle_at:
                latest_candle_at = candles[-1].timestamp

    filter_result = apply_filters(
        symbols,
        candles_by_symbol=candles_by_symbol,
        enforce_liquidity=request.enforce_liquidity,
    )
    source_counts = Counter(candles[-1].source for candles in candles_by_symbol.values() if candles)
    result_source = source_counts.most_common(1)[0][0] if source_counts else source_name

    candidates: list[Pick] = []
    watch_candidates: list[Pick] = []
    for item in filter_result.symbols:
        candles = candles_by_symbol.get(item.symbol)
        if not candles:
            continue
        pick = pick_for_symbol(
            item.symbol,
            candles=candles,
            asm_gsm_tags=item.asm_gsm_tags,
        )
        if pick is None:
            continue
        if _passes_hard_filter(pick, request):
            candidates.append(pick)
        else:
            watch_candidates.append(pick)

    candidates.sort(key=lambda pick: pick.probability, reverse=True)
    top_picks = candidates[: request.top_pick_limit]
    selected_symbols = {pick.symbol for pick in top_picks}
    watch_only = [
        pick for pick in [*candidates[request.top_pick_limit :], *watch_candidates]
        if pick.symbol not in selected_symbols
    ][: request.watch_only_limit]

    created_at = utc_now()
    result = ScanResult(
        universe=universe_name,
        source=result_source,
        interval=request.interval,
        mode=mode_context(
            mode_override=request.selected_mode or "2",
            data_freshness=freshness_label(latest_candle_at),
            source=result_source,
        ),
        created_at=created_at,
        completed_at=utc_now(),
        picks=top_picks,
        watch_only=watch_only,
        errors=errors,
        metadata={
            "base_count": universe.base_count,
            "movers_count": universe.movers_count,
            "premarket_seed_count": premarket_seed_count,
            "total_universe_count": universe.total_count,
            "attempted_count": len(symbols),
            "scan_concurrency": max_workers,
            "candles_loaded_count": len(candles_by_symbol),
            "source_counts": dict(source_counts),
            "filter_output_count": filter_result.output_count,
            "filter_rejected_count": len(filter_result.rejected),
            "asm_gsm_tagged_count": filter_result.asm_gsm_tagged_count,
            "hard_filter": {
                "min_detectors_fired": request.min_detectors_fired,
                "min_volume_x_avg": request.min_volume_x_avg,
                "min_probability": request.min_probability,
            },
        },
    )
    return append_scan_result(result)


def _fetch_symbol_candles(
    item: UniverseSymbol,
    *,
    request: LiveScanRequest,
    source: SourceName,
) -> tuple[str, list[Candle] | None, ScanError | None]:
    symbol = item.symbol.upper()
    try:
        candles = sorted_candles(
            fetch_candles(
                symbol,
                interval=request.interval,
                lookback=request.lookback,
                source=source,
            )
        )
    except Exception as exc:
        return symbol, None, ScanError(symbol=symbol, stage="candles", message=str(exc))
    if not candles:
        return (
            symbol,
            None,
            ScanError(symbol=symbol, stage="candles", message="no candles returned"),
        )
    return symbol, candles, None


def build_chart_response(
    symbol: str,
    *,
    interval: str = "5m",
    lookback: str = "20d",
    source: SourceName | None = None,
) -> ChartResponse:
    clean_symbol = symbol.strip().upper()
    candles = sorted_candles(
        fetch_candles(clean_symbol, interval=interval, lookback=lookback, source=source)
    )
    signal_rows = latest_session_candles(candles) or candles
    detector_results = run_all_detectors(signal_rows)
    return ChartResponse(
        symbol=clean_symbol,
        interval=interval,
        source=candles[-1].source if candles else (source or load_settings().default_source),
        candles=candles,
        overlays=build_overlays(candles, detector_results),
        detector_results=detector_results,
        as_of=utc_now(),
    )


def build_overlays(
    candles: Sequence[Candle],
    detector_results: Sequence[DetectorResult] | None = None,
) -> ChartOverlays:
    rows = sorted_candles(candles)
    if not rows:
        return ChartOverlays()

    vwap_points = _session_vwap_points(rows)
    orb_high, orb_low = _orb_lines(rows)
    prev_high, prev_low, pivot, r1, s1 = _previous_day_lines(rows)
    detector_points = [
        DetectorOverlayPoint(
            time=rows[-1].timestamp,
            detector=result.name,
            direction=result.direction,
            strength=result.strength,
            reason=result.reason,
        )
        for result in (detector_results or [])
        if result.fired
    ]
    return ChartOverlays(
        vwap=vwap_points,
        orb_high=orb_high,
        orb_low=orb_low,
        prev_day_high=prev_high,
        prev_day_low=prev_low,
        ma20=_moving_average(rows, 20, "close"),
        ma50=_moving_average(rows, 50, "close"),
        volume_ma=_moving_average(rows, 20, "volume"),
        pivot=pivot,
        r1=r1,
        s1=s1,
        detector_points=detector_points,
    )


def pick_for_symbol(
    symbol: str,
    *,
    candles: Sequence[Candle],
    asm_gsm_tags: Sequence[str],
) -> Pick | None:
    rows = sorted_candles(candles)
    signal_rows = latest_session_candles(rows) or rows
    detector_results = run_all_detectors(signal_rows)
    fired_results = fired(detector_results)
    if not fired_results:
        return None

    direction = classify_direction(detector_results)
    if direction is None:
        return None

    volume_x_avg = daily_volume_ratio(rows)
    pct = session_pct_change(signal_rows)
    probability = probability_score(
        detector_results,
        volume_x_avg=volume_x_avg,
        pct_change=pct,
    )
    conviction = conviction_for_probability(probability)
    if conviction is None:
        return None

    last = signal_rows[-1]
    return Pick(
        symbol=symbol,
        direction=direction,
        probability=probability,
        detectors_fired=[result.name for result in fired_results],
        detector_results=detector_results,
        volume_x_avg=volume_x_avg,
        pct_change=pct,
        ltp=last.close,
        conviction=conviction,
        asm_gsm_tags=list(asm_gsm_tags),
        metadata={
            "candle_count": len(rows),
            "signal_candle_count": len(signal_rows),
            "last_candle_at": last.timestamp.isoformat(),
            "volume_average_basis": "20d_daily_volume",
        },
    )


def _passes_hard_filter(pick: Pick, request: LiveScanRequest) -> bool:
    return (
        len(pick.detectors_fired) >= request.min_detectors_fired
        and pick.volume_x_avg >= request.min_volume_x_avg
        and pick.probability >= request.min_probability
    )


def _with_premarket_seed(
    symbols: Sequence[UniverseSymbol],
    request: LiveScanRequest,
) -> tuple[list[UniverseSymbol], int]:
    rows = list(symbols)
    if not request.include_premarket_watchlist:
        return rows, 0
    try:
        from intraday_engine.modes.pre_market import read_premarket_watchlist
    except Exception:
        return rows, 0

    try:
        seeds = read_premarket_watchlist()
    except Exception:
        return rows, 0

    seen = {item.symbol.upper() for item in rows}
    added = 0
    for symbol in seeds:
        clean_symbol = symbol.strip().upper()
        if not clean_symbol or clean_symbol in seen:
            continue
        rows.append(
            UniverseSymbol(
                symbol=clean_symbol,
                yahoo_symbol=f"{clean_symbol}.NS",
                name=clean_symbol,
                source="premarket_seed",
            )
        )
        seen.add(clean_symbol)
        added += 1
    return rows, added


_pick_for_symbol = pick_for_symbol


def _moving_average(
    candles: Sequence[Candle],
    period: int,
    field: str,
) -> list[OverlayPoint]:
    points: list[OverlayPoint] = []
    values = [float(getattr(candle, field)) for candle in candles]
    for index in range(period - 1, len(candles)):
        window = values[index - period + 1 : index + 1]
        points.append(OverlayPoint(time=candles[index].timestamp, value=sum(window) / period))
    return points


def _session_vwap_points(candles: Sequence[Candle]) -> list[OverlayPoint]:
    points: list[OverlayPoint] = []
    session: list[Candle] = []
    current_day = None

    for candle in candles:
        day = to_ist(candle.timestamp).date()
        if current_day is None:
            current_day = day
        if day != current_day:
            points.extend(
                OverlayPoint(time=row.timestamp, value=value)
                for row, value in zip(session, cumulative_vwap(session), strict=True)
            )
            session = []
            current_day = day
        session.append(candle)

    if session:
        points.extend(
            OverlayPoint(time=row.timestamp, value=value)
            for row, value in zip(session, cumulative_vwap(session), strict=True)
        )
    return points


def _line_points(candles: Sequence[Candle], value: float) -> list[OverlayPoint]:
    return [OverlayPoint(time=candle.timestamp, value=value) for candle in candles]


def _orb_lines(
    candles: Sequence[Candle],
    opening_minutes: int = 30,
) -> tuple[list[OverlayPoint], list[OverlayPoint]]:
    session = latest_session_candles(candles) or list(candles)
    opening_bars = bars_for_minutes(session, opening_minutes)
    if len(session) < opening_bars:
        return [], []
    opening = session[:opening_bars]
    high = max(candle.high for candle in opening)
    low = min(candle.low for candle in opening)
    return _line_points(session, high), _line_points(session, low)


def _previous_day_lines(
    candles: Sequence[Candle],
) -> tuple[
    list[OverlayPoint],
    list[OverlayPoint],
    list[OverlayPoint],
    list[OverlayPoint],
    list[OverlayPoint],
]:
    current_day = to_ist(candles[-1].timestamp).date()
    previous_rows = [
        candle for candle in candles
        if to_ist(candle.timestamp).date() < current_day
    ]
    if not previous_rows:
        return [], [], [], [], []

    previous_day = max(to_ist(candle.timestamp).date() for candle in previous_rows)
    session = [
        candle for candle in previous_rows
        if to_ist(candle.timestamp).date() == previous_day
    ]
    if not session:
        return [], [], [], [], []
    high = max(candle.high for candle in session)
    low = min(candle.low for candle in session)
    close = session[-1].close
    pivot = (high + low + close) / 3
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    return (
        _line_points(candles, high),
        _line_points(candles, low),
        _line_points(candles, pivot),
        _line_points(candles, r1),
        _line_points(candles, s1),
    )
