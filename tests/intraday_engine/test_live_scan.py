from __future__ import annotations

from datetime import UTC, datetime, timedelta

from intraday_engine.data_sources.base import Candle
from intraday_engine.modes import live_scan
from intraday_engine.modes.live_scan import LiveScanRequest, build_overlays, run_live_scan
from intraday_engine.storage import picks as picks_storage
from intraday_engine.universe.builder import BuiltUniverse, UniverseSymbol


def _candle(index: int, close: float, volume: float = 200_000.0) -> Candle:
    base = datetime(2026, 4, 29, 9, 15, tzinfo=UTC)
    return Candle(
        timestamp=base + timedelta(minutes=5 * index),
        open=close - 0.2,
        high=close + 0.6,
        low=close - 0.6,
        close=close,
        volume=volume,
        source="yfinance",
    )


def _scan_candles() -> list[Candle]:
    candles = [_candle(index, 100 + index * 0.03) for index in range(24)]
    candles.append(_candle(24, 104.0, 750_000.0))
    return candles


def test_live_scan_builds_pick_and_persists_json(tmp_path, monkeypatch):
    symbol = UniverseSymbol(symbol="TEST", yahoo_symbol="TEST.NS", name="Test Ltd")
    universe = BuiltUniverse(
        id="nifty50",
        label="Nifty 50",
        symbols=[symbol],
        base_count=1,
        movers_count=0,
        total_count=1,
        merge_movers=False,
    )
    monkeypatch.setattr(live_scan, "build_universe", lambda *_, **__: universe)
    monkeypatch.setattr(live_scan, "fetch_candles", lambda *_, **__: _scan_candles())
    monkeypatch.setattr(picks_storage, "PICKS_DIR", tmp_path)

    result = run_live_scan(
        LiveScanRequest(
            universe="nifty50",
            source="yfinance",
            mode_override="2",
            merge_movers=False,
            max_symbols=1,
        )
    )
    stored = picks_storage.read_scan_result(result.scan_id)

    assert result.picks
    assert result.picks[0].symbol == "TEST"
    assert len(result.picks[0].detectors_fired) >= 2
    assert result.picks[0].volume_x_avg >= 3.0
    assert stored is not None
    assert stored.scan_id == result.scan_id


def test_chart_overlays_include_vwap_orb_and_moving_average():
    candles = _scan_candles()

    overlays = build_overlays(candles)

    assert len(overlays.vwap) == len(candles)
    assert len(overlays.orb_high) == len(candles)
    assert len(overlays.orb_low) == len(candles)
    assert overlays.ma20
