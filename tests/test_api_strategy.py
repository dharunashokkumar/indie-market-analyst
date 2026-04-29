"""FastAPI TestClient tests for /strategy/* endpoints.

Uses fixture-registered data loaders (overriding the real ones) to keep the
suite hermetic — no network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backtest import runner as backtest_runner
from backtest.loaders import registry as loader_registry
from backtest.loaders.yfinance_loader import _to_yahoo_symbol
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
    real_mcx = loader_registry._loaders.get("mcx")
    loader_registry.register("yfinance", lambda **kw: df.copy())
    loader_registry.register("mcx", lambda **kw: df.copy())
    store = MemoryStore(db_path=tmp_path / "strat.db")
    monkeypatch.setattr(api_server, "get_store", lambda: store)
    monkeypatch.setattr(backtest_runner, "get_store", lambda: store)
    monkeypatch.setattr(api_server, "get_mcx_quote", lambda symbol: {
        "symbol": symbol,
        "last_price": 200.0,
        "prev_close": 198.0,
        "change_pct": 2.0 / 198.0,
        "day_high": 202.0,
        "day_low": 197.0,
        "volume": 10_000.0,
        "as_of": "2026-04-28",
        "source": "mcxlib",
    })
    yield store
    if real_yf is not None:
        loader_registry.register("yfinance", real_yf)
    if real_mcx is not None:
        loader_registry.register("mcx", real_mcx)


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
    assert all(row["asset_type"] == "equity" for row in rows)


def test_strategy_instrument_groups_include_requested_assets():
    client = TestClient(api_server.app)
    r = client.get("/strategy/instrument-groups")
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert {
        "equity", "commodity", "mutual_fund", "global_index", "indian_index", "crypto",
    }.issubset(ids)


def test_strategy_symbols_commodity_and_crypto():
    client = TestClient(api_server.app)
    commodity = client.get("/strategy/symbols", params={"asset_type": "commodity", "q": "gold"})
    assert commodity.status_code == 200
    assert commodity.json()[0]["yahoo_symbol"] == "GOLD"
    assert commodity.json()[0]["currency"] == "INR"
    assert commodity.json()[0]["source"] == "mcxlib"

    crypto = client.get("/strategy/symbols", params={"asset_type": "crypto", "q": "btc"})
    assert crypto.status_code == 200
    assert crypto.json()[0]["yahoo_symbol"] == "BTC-USD"


def test_strategy_symbols_unknown_asset_type():
    client = TestClient(api_server.app)
    r = client.get("/strategy/symbols", params={"asset_type": "unknown"})
    assert r.status_code == 400


def test_yfinance_loader_keeps_native_yahoo_symbols():
    assert _to_yahoo_symbol("RELIANCE") == "RELIANCE.NS"
    assert _to_yahoo_symbol("GC=F") == "GC=F"
    assert _to_yahoo_symbol("BTC-USD") == "BTC-USD"
    assert _to_yahoo_symbol("^NSEI") == "^NSEI"


def test_strategy_usdinr_endpoint(fake_loader_and_store):
    client = TestClient(api_server.app)
    r = client.get("/strategy/fx/usdinr")
    assert r.status_code == 200
    body = r.json()
    assert body["pair"] == "USDINR"
    assert body["rate"] > 0
    assert body["source"] == "yfinance"


def test_strategy_quote_commodity_uses_mcx_source(fake_loader_and_store):
    client = TestClient(api_server.app)
    r = client.get("/strategy/quote/GOLD")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "GOLD"
    assert body["last_price"] > 0
    assert body["source"] == "mcxlib"


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


def test_strategy_run_routes_commodity_to_mcx_loader(fake_loader_and_store):
    calls: list[dict] = []

    def mcx_loader(**kwargs):
        calls.append(kwargs)
        return _synthetic_uptrend()

    def yfinance_loader(**kwargs):
        raise AssertionError(f"commodity unexpectedly routed to yfinance: {kwargs}")

    loader_registry.register("mcx", mcx_loader)
    loader_registry.register("yfinance", yfinance_loader)

    client = TestClient(api_server.app)
    r = client.post("/strategy/run", json={
        "symbol": "GOLD",
        "strategy": "sma_crossover",
    })

    assert r.status_code == 200, r.text
    assert calls and calls[0]["symbol"] == "GOLD"


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
