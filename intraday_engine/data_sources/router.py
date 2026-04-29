"""Settings-driven router for intraday data sources."""

from __future__ import annotations

from intraday_engine.data_sources.base import (
    Candle,
    DataSource,
    DataSourceError,
    PreOpenRow,
    QuoteSnapshot,
    SourceName,
    SurveillanceEntry,
)
from intraday_engine.data_sources.nse_direct import NseDirectSource
from intraday_engine.data_sources.settings_store import IntradaySettings, load_settings
from intraday_engine.data_sources.yfinance_source import YFinanceSource
from intraday_engine.storage.candle_cache import (
    read_cached_candles,
    ttl_for_interval,
    write_cached_candles,
)


def get_data_source(
    source: SourceName | None = None,
    *,
    settings: IntradaySettings | None = None,
) -> DataSource:
    config = settings or load_settings()
    source_name = source or config.default_source
    if source_name == "nse_direct":
        return NseDirectSource(config)
    if source_name == "yfinance":
        return YFinanceSource()
    raise DataSourceError(f"unknown intraday data source: {source_name}")


def fetch_candles(
    symbol: str,
    *,
    interval: str = "5m",
    lookback: str = "5d",
    source: SourceName | None = None,
    use_cache: bool = True,
) -> list[Candle]:
    settings = load_settings()
    primary_name = source or settings.default_source
    if use_cache:
        cached = read_cached_candles(
            symbol,
            interval,
            source=primary_name,
            lookback=lookback,
            max_age_seconds=ttl_for_interval(interval),
        )
        if cached is not None:
            return cached

    primary = get_data_source(primary_name, settings=settings)
    try:
        candles = primary.fetch_candles(symbol, interval=interval, lookback=lookback)
    except Exception as primary_error:
        if primary_name == settings.fallback_source:
            raise
        fallback = get_data_source(settings.fallback_source, settings=settings)
        try:
            candles = fallback.fetch_candles(symbol, interval=interval, lookback=lookback)
        except Exception as fallback_error:
            raise DataSourceError(
                f"{primary_name} failed ({primary_error}); "
                f"{settings.fallback_source} failed ({fallback_error})"
            ) from fallback_error

    if use_cache:
        actual_source = candles[-1].source if candles else primary_name
        write_cached_candles(
            symbol,
            interval,
            candles,
            source=actual_source,
            lookback=lookback,
        )
    return candles


def fetch_quote(symbol: str, *, source: SourceName | None = None) -> QuoteSnapshot:
    settings = load_settings()
    primary_name = source or settings.default_source
    primary = get_data_source(primary_name, settings=settings)
    try:
        return primary.fetch_quote(symbol)
    except Exception:
        if primary_name == settings.fallback_source:
            raise
        return get_data_source(settings.fallback_source, settings=settings).fetch_quote(symbol)


def fetch_preopen(source: SourceName | None = None) -> list[PreOpenRow]:
    return get_data_source(source).fetch_preopen()


def fetch_asm_gsm(source: SourceName | None = "nse_direct") -> list[SurveillanceEntry]:
    return get_data_source(source).fetch_asm_gsm()
