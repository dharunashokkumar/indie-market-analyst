from __future__ import annotations

from datetime import UTC, datetime, timedelta

from intraday_engine.data_sources.base import Candle
from intraday_engine.detectors import DETECTOR_NAMES, run_all_detectors
from intraday_engine.detectors.breakout import detect as detect_breakout
from intraday_engine.detectors.flag import detect as detect_flag
from intraday_engine.detectors.momentum import detect as detect_momentum
from intraday_engine.detectors.orb import detect as detect_orb
from intraday_engine.detectors.short_cover import detect as detect_short_cover
from intraday_engine.detectors.vwap_reclaim import detect as detect_vwap_reclaim

BASE_TS = datetime(2026, 4, 29, 9, 15, tzinfo=UTC)


def _candle(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 1_000.0,
) -> Candle:
    return Candle(
        timestamp=BASE_TS + timedelta(minutes=5 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="yfinance",
    )


def test_orb_detector_fires_on_opening_range_breakout():
    candles = [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 101.2, 99.8, 100.6),
        _candle(2, 100.6, 101.4, 100.2, 101.0),
        _candle(3, 101.0, 101.5, 100.7, 101.2),
        _candle(4, 101.2, 101.7, 100.9, 101.1),
        _candle(5, 101.1, 101.6, 100.8, 101.0),
        _candle(6, 101.0, 104.0, 100.9, 103.8, 4_000),
    ]

    fired = detect_orb(candles)
    quiet = detect_orb(candles[:-1] + [_candle(6, 101.0, 101.4, 100.9, 101.2, 4_000)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_vwap_reclaim_detector_fires_on_fresh_reclaim():
    candles = [
        _candle(0, 100.0, 100.5, 99.5, 100.0),
        _candle(1, 100.0, 100.0, 99.0, 99.5),
        _candle(2, 99.5, 99.8, 98.9, 99.1),
        _candle(3, 99.1, 99.4, 98.7, 99.0),
        _candle(4, 99.0, 103.0, 100.8, 102.0, 5_000),
    ]

    fired = detect_vwap_reclaim(candles)
    quiet = detect_vwap_reclaim(candles[:-1] + [_candle(4, 99.0, 99.5, 98.9, 99.2, 5_000)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_breakout_detector_fires_on_volume_confirmed_high_break():
    candles = [
        _candle(i, 100 + i * 0.02, 101.0, 99.5, 100.2, 1_000)
        for i in range(24)
    ]
    candles.append(_candle(24, 100.2, 103.5, 100.0, 103.0, 4_500))

    fired = detect_breakout(candles)
    quiet = detect_breakout(candles[:-1] + [_candle(24, 100.2, 100.8, 100.0, 100.5, 4_500)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_flag_detector_fires_on_tight_continuation_break():
    candles = [
        _candle(0, 100.0, 100.8, 99.8, 100.6),
        _candle(1, 100.6, 101.3, 100.5, 101.1),
        _candle(2, 101.1, 101.8, 101.0, 101.6),
        _candle(3, 101.6, 102.2, 101.5, 102.0),
        _candle(4, 102.0, 102.25, 101.7, 102.05),
        _candle(5, 102.05, 102.2, 101.65, 101.9),
        _candle(6, 101.9, 102.15, 101.7, 102.0),
        _candle(7, 102.0, 102.3, 101.8, 102.1),
        _candle(8, 102.1, 103.4, 102.0, 103.1, 4_000),
    ]

    fired = detect_flag(candles)
    quiet = detect_flag(candles[:-1] + [_candle(8, 102.1, 102.25, 101.9, 102.0, 4_000)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_momentum_detector_fires_on_price_move_with_volume_burst():
    candles = [
        _candle(0, 100.0, 100.5, 99.8, 100.1),
        _candle(1, 100.1, 100.8, 100.0, 100.6),
        _candle(2, 100.6, 101.4, 100.5, 101.1),
        _candle(3, 101.1, 102.4, 101.0, 102.2, 4_000),
    ]

    fired = detect_momentum(candles)
    quiet = detect_momentum(candles[:-1] + [_candle(3, 101.1, 102.4, 101.0, 102.2, 1_000)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_short_cover_detector_fires_on_rebound_from_intraday_low():
    candles = [
        _candle(0, 100.0, 100.2, 99.0, 99.2),
        _candle(1, 99.2, 99.5, 97.4, 97.8),
        _candle(2, 97.8, 98.2, 96.0, 96.5),
        _candle(3, 96.5, 98.4, 96.2, 98.0),
        _candle(4, 98.0, 99.0, 97.7, 98.4),
        _candle(5, 98.4, 101.0, 98.2, 100.8, 4_500),
    ]

    fired = detect_short_cover(candles)
    quiet = detect_short_cover(candles[:-1] + [_candle(5, 98.4, 99.0, 98.2, 98.5, 4_500)])

    assert fired.fired is True
    assert fired.direction == "LONG"
    assert quiet.fired is False


def test_detector_runner_returns_all_required_detectors():
    candles = [
        _candle(i, 100 + i * 0.1, 100.8 + i * 0.1, 99.8 + i * 0.1, 100.3 + i * 0.1)
        for i in range(12)
    ]

    results = run_all_detectors(candles)

    assert [result.name for result in results] == list(DETECTOR_NAMES)
    assert all(0 <= result.strength <= 1 for result in results)
