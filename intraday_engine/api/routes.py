"""FastAPI routes for the intraday scanner."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import Field

from intraday_engine.data_sources.base import SourceName
from intraday_engine.data_sources.settings_store import (
    IntradayPublicSettings,
    IntradaySettingsUpdate,
    load_settings,
    public_settings,
    update_settings,
)
from intraday_engine.ist_clock import mode_context, normalize_mode_id
from intraday_engine.modes.last_hour import run_last_hour_scan
from intraday_engine.modes.live_scan import (
    ChartResponse,
    LiveScanRequest,
    build_chart_response,
    run_live_scan,
)
from intraday_engine.modes.post_market import PostMarketReview, run_post_market
from intraday_engine.modes.pre_market import PreMarketSnapshot, run_pre_market
from intraday_engine.modes.pre_open import PreOpenSnapshot, run_pre_open
from intraday_engine.modes.specific_stock import (
    SpecificStockRequest,
    SpecificStockResult,
    analyze_symbol,
)
from intraday_engine.modes.update import (
    ActivePickRequest,
    ActivePicksResponse,
    mark_active_pick,
    recompute_active_picks,
)
from intraday_engine.modes.weekend import WeekendSnapshot, run_weekend
from intraday_engine.output_schema import ModeContext, ScanResult, StrictModel
from intraday_engine.storage.picks import read_day_scans, read_scan_result
from intraday_engine.universe.builder import UniverseOption, list_universes
from intraday_engine.universe.custom_csv import CUSTOM_CSV_PATH, save_custom_csv

router = APIRouter(prefix="/intraday", tags=["intraday"])


class CustomCsvUploadRequest(StrictModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)


class CustomCsvUploadResponse(StrictModel):
    universe: str = "custom_csv"
    size: int
    path: str


@router.get("/mode", response_model=ModeContext)
def get_intraday_mode(mode_override: str | None = None) -> ModeContext:
    try:
        return mode_context(mode_override=mode_override)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/settings", response_model=IntradayPublicSettings)
def get_intraday_settings() -> IntradayPublicSettings:
    return public_settings(load_settings())


@router.put("/settings", response_model=IntradayPublicSettings)
def put_intraday_settings(update: IntradaySettingsUpdate) -> IntradayPublicSettings:
    try:
        return public_settings(update_settings(update))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/universes", response_model=list[UniverseOption])
def get_intraday_universes() -> list[UniverseOption]:
    return list_universes()


@router.post("/universes/custom-csv", response_model=CustomCsvUploadResponse)
def post_intraday_custom_csv(request: CustomCsvUploadRequest) -> CustomCsvUploadResponse:
    try:
        size = save_custom_csv(request.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomCsvUploadResponse(size=size, path=str(CUSTOM_CSV_PATH))


@router.post("/scan", response_model=ScanResult)
def post_intraday_scan(request: LiveScanRequest) -> ScanResult:
    try:
        selected_mode = normalize_mode_id(request.selected_mode or "2")
        if selected_mode == "3":
            return run_last_hour_scan(request)
        if selected_mode != "2":
            raise ValueError(f"mode {selected_mode} is not a scan mode; use its dedicated endpoint")
        return run_live_scan(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scan/{scan_id}", response_model=ScanResult)
def get_intraday_scan(scan_id: str) -> ScanResult:
    result = read_scan_result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return result


@router.get("/picks/today", response_model=list[ScanResult])
def get_intraday_picks_today() -> list[ScanResult]:
    return read_day_scans()


@router.get("/picks/active", response_model=ActivePicksResponse)
def get_intraday_active_picks(source: SourceName | None = None) -> ActivePicksResponse:
    return recompute_active_picks(source=source)


@router.post("/picks/active", response_model=ActivePicksResponse)
def post_intraday_active_pick(request: ActivePickRequest) -> ActivePicksResponse:
    try:
        return mark_active_pick(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/symbol/{symbol}", response_model=SpecificStockResult)
def get_intraday_symbol(
    symbol: str,
    interval: str = "5m",
    lookback: str = "20d",
    source: SourceName | None = None,
) -> SpecificStockResult:
    try:
        return analyze_symbol(
            SpecificStockRequest(
                symbol=symbol,
                interval=interval,
                lookback=lookback,
                source=source,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/premarket/today", response_model=PreMarketSnapshot)
def get_intraday_premarket_today(refresh: bool = False) -> PreMarketSnapshot:
    return run_pre_market(refresh=refresh)


@router.get("/preopen/today", response_model=PreOpenSnapshot)
def get_intraday_preopen_today(refresh: bool = False) -> PreOpenSnapshot:
    return run_pre_open(refresh=refresh)


@router.get("/postmarket/today", response_model=PostMarketReview)
def get_intraday_postmarket_today(refresh: bool = False) -> PostMarketReview:
    return run_post_market(refresh=refresh)


@router.get("/weekend/this", response_model=WeekendSnapshot)
def get_intraday_weekend_this(refresh: bool = False) -> WeekendSnapshot:
    return run_weekend(refresh=refresh)


@router.get("/chart/{symbol}", response_model=ChartResponse)
def get_intraday_chart(
    symbol: str,
    interval: str = "5m",
    lookback: str = "20d",
    source: SourceName | None = None,
) -> ChartResponse:
    try:
        return build_chart_response(
            symbol,
            interval=interval,
            lookback=lookback,
            source=source,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
