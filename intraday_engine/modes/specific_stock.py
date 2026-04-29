"""Mode 5 single-symbol analysis."""

from __future__ import annotations

from pydantic import field_validator

from intraday_engine.data_sources.base import SourceName
from intraday_engine.data_sources.router import fetch_candles
from intraday_engine.data_sources.settings_store import load_settings
from intraday_engine.detectors import run_all_detectors
from intraday_engine.detectors.base import sorted_candles
from intraday_engine.ist_clock import freshness_label, mode_context
from intraday_engine.modes.live_scan import ChartResponse, build_overlays, pick_for_symbol
from intraday_engine.output_schema import DetectorResult, ModeContext, Pick, StrictModel, utc_now


class SpecificStockRequest(StrictModel):
    symbol: str
    source: SourceName | None = None
    interval: str = "5m"
    lookback: str = "20d"

    @field_validator("symbol", "interval", "lookback")
    @classmethod
    def clean_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("value cannot be empty")
        return clean.upper() if value == value.upper() else clean


class SpecificStockResult(StrictModel):
    symbol: str
    source: str
    interval: str
    mode: ModeContext
    pick: Pick | None = None
    chart: ChartResponse
    detector_results: list[DetectorResult]
    as_of: str
    message: str | None = None


def analyze_symbol(request: SpecificStockRequest) -> SpecificStockResult:
    clean_symbol = request.symbol.strip().upper()
    settings = load_settings()
    source_name = request.source or settings.default_source
    candles = sorted_candles(
        fetch_candles(
            clean_symbol,
            interval=request.interval,
            lookback=request.lookback,
            source=source_name,
        )
    )
    detector_results = run_all_detectors(candles)
    pick = pick_for_symbol(clean_symbol, candles=candles, asm_gsm_tags=[])
    data_source = candles[-1].source if candles else source_name
    chart = ChartResponse(
        symbol=clean_symbol,
        interval=request.interval,
        source=data_source,
        candles=candles,
        overlays=build_overlays(candles, detector_results),
        detector_results=detector_results,
        as_of=utc_now(),
    )
    message = None if pick else "No qualifying directional setup from current candles."
    return SpecificStockResult(
        symbol=clean_symbol,
        source=data_source,
        interval=request.interval,
        mode=mode_context(
            mode_override="5",
            data_freshness=freshness_label(candles[-1].timestamp if candles else None),
            source=data_source,
        ),
        pick=pick,
        chart=chart,
        detector_results=detector_results,
        as_of=utc_now().isoformat(),
        message=message,
    )
