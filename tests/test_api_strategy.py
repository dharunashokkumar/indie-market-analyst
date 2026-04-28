"""FastAPI TestClient tests for /strategy/* endpoints.

Uses a fixture-registered "yfinance" loader (overriding the real one) to keep
the suite hermetic — no network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtest import runner as backtest_runner
from backtest.loaders import registry as loader_registry
from indie_market_analyst import api_server
from indie_market_analyst.memory.store import MemoryStore


def _synthetic_uptrend(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({
        "open": np.r_[close[0], close[:-1]],
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.full(n, 1_000_000.0),
        "source": "fixture",
    }, index=idx)


@pytest.fixture
def fake_loader_and_store(tmp_path, monkeypatch):
    df = _synthetic_uptrend()
    real_yf = loader_registry._loaders.get("yfinance")
    loader_registry.register("yfinance", lambda **kw: df.copy())
    store = MemoryStore(db_path=tmp_path / "strat.db")
    monkeypatch.setattr(api_server, "get_store", lambda: store)
    monkeypatch.setattr(backtest_runner, "get_store", lambda: store)
    yield store
    if real_yf is not None:
        loader_registry.register("yfinance", real_yf)


def test_strategy_list_returns_twelve():
    client = TestClient(api_server.app)
    r = client.get("/strategy/list")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 12
    names = {it["name"] for it in items}
    assert "sma_crossover" in names
    assert "adx_trend" in names
    for it in items:
        assert it["category"] in {"trend", "mean_reversion", "breakout", "momentum"}
        assert "label" in it and "default_params" in it


def test_strategy_symbols_search():
    client = TestClient(api_server.app)
    r = client.get("/strategy/symbols", params={"q": "reliance", "limit": 5})
    assert r.status_code == 200
    rows = r.json()
    assert any(row["symbol"] == "RELIANCE" for row in rows)


def test_strategy_run_sma_crossover(fake_loader_and_store):
    store = fake_loader_and_store
    client = TestClient(api_server.app)
    r = client.post("/strategy/run", json={
        "symbol": "FAKE.NS",
        "strategy": "sma_crossover",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_signal"] in {"LONG", "FLAT", "SHORT"}
    assert body["current_signal"] == "LONG"  # synthetic uptrend
    assert isinstance(body["signal_age_bars"], int) and body["signal_age_bars"] >= 0
    run = body["run"]
    assert run["symbol"] == "FAKE.NS"
    assert run["strategy"] == "sma_crossover"
    assert "sharpe" in run["metrics"]
    # persisted (store generates its own row id; just verify a backtest row exists)
    runs = store.list_runs(limit=10)
    assert len(runs) == 1
    assert runs[0]["kind"] == "backtest"


def test_strategy_run_unknown_strategy(fake_loader_and_store):
    client = TestClient(api_server.app)
    r = client.post("/strategy/run", json={"symbol": "FAKE.NS", "strategy": "no_such"})
    assert r.status_code == 400


def test_strategy_run_overrides_params(fake_loader_and_store):
    client = TestClient(api_server.app)
    r = client.post("/strategy/run", json={
        "symbol": "FAKE.NS", "strategy": "sma_crossover",
        "params": {"fast": 5, "slow": 10},
    })
    assert r.status_code == 200
    assert r.json()["run"]["strategy"] == "sma_crossover"
