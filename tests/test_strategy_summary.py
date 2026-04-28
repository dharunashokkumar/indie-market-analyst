"""Tests for the deterministic engine summary + run-all aggregator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtest import runner as backtest_runner
from backtest.loaders import registry as loader_registry
from backtest.strategies.summary import aggregate_runs, summarize_run
from indie_market_analyst import api_server
from indie_market_analyst.memory.store import MemoryStore


def test_summarize_run_long_high_confidence():
    blob = {
        "symbol": "TCS",
        "start_date": "2024-01-01",
        "end_date": "2025-01-01",
        "metrics": {"sharpe": 1.8, "annualized_return": 0.22, "max_drawdown": -0.08},
        "trades": [{}] * 14,
    }
    s = summarize_run(blob, "LONG", signal_age=5, last_close=4000.0)
    assert s["verdict"] == "BUY"
    assert s["confidence"] == "high"
    assert "TCS" in s["headline"]
    assert "may go UP" in s["direction"]


def test_summarize_run_short_low_confidence_few_trades():
    blob = {
        "symbol": "X", "start_date": "a", "end_date": "b",
        "metrics": {"sharpe": -0.5, "annualized_return": -0.1, "max_drawdown": -0.3},
        "trades": [{}, {}],
    }
    s = summarize_run(blob, "SHORT", signal_age=0, last_close=100.0)
    assert s["verdict"] == "SELL"
    assert s["confidence"] == "low"
    assert "Don't bet only on this" in s["beginner_takeaway"]


def test_summarize_run_flat_wait_verdict():
    blob = {
        "symbol": "X", "start_date": "a", "end_date": "b",
        "metrics": {"sharpe": 0.5, "annualized_return": 0.05, "max_drawdown": -0.1},
        "trades": [{}] * 5,
    }
    s = summarize_run(blob, "FLAT", signal_age=10, last_close=100.0)
    assert s["verdict"] == "WAIT"


def test_aggregate_runs_mostly_bullish():
    rows = (
        [{"name": f"s{i}", "label": f"L{i}", "current_signal": "LONG",
          "sharpe": 1.0 + i * 0.1, "annualized_return": 0.1, "max_drawdown": -0.05,
          "signal_age_bars": 1} for i in range(8)]
        + [{"name": "x", "label": "X", "current_signal": "FLAT",
            "sharpe": 0.0, "annualized_return": 0, "max_drawdown": 0, "signal_age_bars": 0}]
        * 4
    )
    agg = aggregate_runs(rows)
    assert agg["verdict"] == "MOSTLY_BULLISH"
    assert agg["long_count"] == 8
    assert agg["confidence"] == "high"
    assert len(agg["top_by_sharpe"]) == 3
    assert agg["top_by_sharpe"][0]["sharpe"] >= agg["top_by_sharpe"][-1]["sharpe"]


def test_aggregate_runs_mixed():
    rows = [
        {"name": "a", "label": "A", "current_signal": "LONG", "sharpe": 0.5,
         "annualized_return": 0, "max_drawdown": 0, "signal_age_bars": 0},
        {"name": "b", "label": "B", "current_signal": "SHORT", "sharpe": 0.5,
         "annualized_return": 0, "max_drawdown": 0, "signal_age_bars": 0},
        {"name": "c", "label": "C", "current_signal": "FLAT", "sharpe": 0.5,
         "annualized_return": 0, "max_drawdown": 0, "signal_age_bars": 0},
    ]
    agg = aggregate_runs(rows)
    assert agg["verdict"] == "MIXED"
    assert agg["confidence"] == "low"


def test_aggregate_runs_handles_errors():
    rows = [
        {"name": "a", "label": "A", "current_signal": "LONG", "sharpe": 1.5,
         "annualized_return": 0.1, "max_drawdown": -0.05, "signal_age_bars": 1},
        {"name": "b", "label": "B", "error": "boom",
         "current_signal": "FLAT", "sharpe": None, "annualized_return": None,
         "max_drawdown": None, "signal_age_bars": 0},
    ]
    agg = aggregate_runs(rows)
    assert agg["total"] == 1
    assert agg["verdict"] == "MOSTLY_BULLISH"


# ---------- /strategy/run_all integration ----------

def _synthetic_uptrend(n: int = 320) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({
        "open": np.r_[close[0], close[:-1]],
        "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, 1_000_000.0),
        "source": "fixture",
    }, index=idx)


@pytest.fixture
def fake_loader_and_store(tmp_path, monkeypatch):
    df = _synthetic_uptrend()
    real_yf = loader_registry._loaders.get("yfinance")
    loader_registry.register("yfinance", lambda **kw: df.copy())
    store = MemoryStore(db_path=tmp_path / "agg.db")
    monkeypatch.setattr(api_server, "get_store", lambda: store)
    monkeypatch.setattr(backtest_runner, "get_store", lambda: store)
    yield store
    if real_yf is not None:
        loader_registry.register("yfinance", real_yf)


def test_strategy_run_includes_engine_summary(fake_loader_and_store):
    client = TestClient(api_server.app)
    r = client.post("/strategy/run", json={"symbol": "FAKE.NS", "strategy": "sma_crossover"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "engine_summary" in body
    es = body["engine_summary"]
    assert es["verdict"] in {"BUY", "SELL", "WAIT"}
    assert es["confidence"] in {"low", "medium", "high"}
    assert "beginner_takeaway" in es and len(es["beginner_takeaway"]) > 30


def test_strategy_run_all_returns_aggregate(fake_loader_and_store):
    store = fake_loader_and_store
    client = TestClient(api_server.app)
    r = client.post("/strategy/run_all", json={"symbol": "FAKE.NS"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["per_strategy"]) == 12
    assert "aggregate" in body
    agg = body["aggregate"]
    assert agg["verdict"] in {"MOSTLY_BULLISH", "MOSTLY_BEARISH", "MIXED", "NO_DATA"}
    assert agg["long_count"] + agg["short_count"] + agg["flat_count"] == agg["total"]
    # default persist=False — store should be empty
    assert len(store.list_runs(limit=20)) == 0


def test_strategy_run_all_persist_true(fake_loader_and_store):
    store = fake_loader_and_store
    client = TestClient(api_server.app)
    r = client.post("/strategy/run_all", json={"symbol": "FAKE.NS", "persist": True})
    assert r.status_code == 200
    assert len(store.list_runs(limit=20)) == 12
