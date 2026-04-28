"""Scan engine + endpoint tests with a fake yfinance loader."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtest import runner as backtest_runner, scans as scan_engine
from backtest.loaders import registry as loader_registry
from indie_market_analyst import api_server
from indie_market_analyst.memory.store import MemoryStore


def _uptrend(n: int = 280) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({
        "open": np.r_[close[0], close[:-1]],
        "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, 1_000_000.0),
        "source": "fixture",
    }, index=idx)


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    df = _uptrend()
    real_yf = loader_registry._loaders.get("yfinance")
    loader_registry.register("yfinance", lambda **kw: df.copy())

    store = MemoryStore(db_path=tmp_path / "scan.db")
    monkeypatch.setattr(api_server, "get_store", lambda: store)
    monkeypatch.setattr(backtest_runner, "get_store", lambda: store)

    # Re-target scans dir to a tmp path so tests don't pollute the repo
    monkeypatch.setattr(scan_engine, "_SCANS_DIR", tmp_path / "scans")
    (tmp_path / "scans").mkdir()
    scan_engine._reset_state()

    yield
    if real_yf is not None:
        loader_registry.register("yfinance", real_yf)
    scan_engine._reset_state()


def test_universes_endpoint():
    client = TestClient(api_server.app)
    r = client.get("/strategy/universes")
    assert r.status_code == 200
    items = r.json()
    ids = {it["id"] for it in items}
    assert {"nifty50", "all_nse", "top200", "banknifty"}.issubset(ids)


def test_scan_unknown_universe(fake_env):
    client = TestClient(api_server.app)
    r = client.post("/strategy/scan", json={"universe": "no_such"})
    assert r.status_code == 400


def test_scan_runs_and_completes(fake_env):
    client = TestClient(api_server.app)
    # tiny universe via banknifty (12 stocks) is still slow with the fake loader
    r = client.post("/strategy/scan", json={"universe": "banknifty"})
    assert r.status_code == 200
    sid = r.json()["scan_id"]
    scan_engine._wait_done(sid, timeout=60.0)

    r = client.get(f"/strategy/scan/{sid}")
    assert r.status_code == 200
    state = r.json()
    assert state["status"] == "completed"
    assert state["done"] == 12
    assert len(state["results"]) == 12
    s = state["summary"]
    assert s["total_companies"] == 12
    # synthetic uptrend → all should be bullish
    assert s["total_bullish"] >= 1
    assert s["market_mood"] in {"BULLISH", "NEUTRAL", "BEARISH"}
    assert "beginner_takeaway" in s
    # Light listing call should NOT include per_strategy
    assert "per_strategy" not in state["results"][0]


def test_scan_full_includes_per_strategy(fake_env):
    client = TestClient(api_server.app)
    r = client.post("/strategy/scan", json={"universe": "banknifty"})
    sid = r.json()["scan_id"]
    scan_engine._wait_done(sid, timeout=60.0)

    r = client.get(f"/strategy/scan/{sid}", params={"full": True})
    state = r.json()
    assert "per_strategy" in state["results"][0]
    assert len(state["results"][0]["per_strategy"]) == 12


def test_scan_persists_json(fake_env):
    client = TestClient(api_server.app)
    r = client.post("/strategy/scan", json={"universe": "banknifty"})
    sid = r.json()["scan_id"]
    scan_engine._wait_done(sid, timeout=60.0)

    path = scan_engine.scans_dir() / f"scan_{sid}.json"
    assert path.exists()
    import json as _json
    data = _json.loads(path.read_text())
    assert data["scan_id"] == sid
    assert data["status"] == "completed"


def test_scan_list_endpoint(fake_env):
    client = TestClient(api_server.app)
    r = client.post("/strategy/scan", json={"universe": "banknifty"})
    sid = r.json()["scan_id"]
    scan_engine._wait_done(sid, timeout=60.0)

    r = client.get("/strategy/scan")
    rows = r.json()
    assert any(row["scan_id"] == sid for row in rows)
