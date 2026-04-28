"""Tests for backtest.runner.run persisting a full blob to SQLite."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import runner
from backtest.loaders.registry import register
from indie_market_analyst.memory.store import MemoryStore


def _synthetic_prices(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    close = 100 + np.cumsum(rng.normal(0, 1.0, size=n))
    return pd.DataFrame({"close": close}, index=idx)


def test_run_persists_full_blob(tmp_path, monkeypatch):
    db = tmp_path / "runs_test.db"
    store = MemoryStore(db_path=db)
    monkeypatch.setattr("backtest.runner.get_store", lambda: store)

    df = _synthetic_prices(120)
    register("synthetic", lambda **_: df)

    # Simple long-while-price-rose signals
    signals = (df["close"].diff().fillna(0.0) > 0).astype(float)

    out_dir = tmp_path / "runs"
    blob = runner.run(
        symbol="TEST",
        signals=signals,
        period="6mo",
        interval="1d",
        loader="synthetic",
        out_dir=out_dir,
        session_id="system",
        strategy="updays_long",
    )

    # Persisted in SQLite
    rows = store.list_runs()
    assert len(rows) == 1
    assert rows[0]["kind"] == "backtest"
    assert rows[0]["id"] == blob["run_id"]
    full = store.get_run(rows[0]["id"])
    assert full is not None
    persisted = full["blob"]

    # Shape checks: full curve, per-component costs, derived trades
    assert persisted["symbol"] == "TEST"
    assert persisted["strategy"] == "updays_long"
    assert len(persisted["equity_curve"]) == len(df)
    for key in ("brokerage", "stt", "stamp", "exch", "sebi", "gst", "total"):
        assert key in persisted["costs"]
    assert "trades" in persisted
    assert persisted["metrics"].keys() == blob["metrics"].keys()
    assert persisted["metrics"]["sharpe"] == blob["metrics"]["sharpe"]
    assert persisted["artifact_path"].endswith(".json")
