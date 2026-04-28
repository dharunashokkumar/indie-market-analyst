"""FastAPI TestClient tests for the runs endpoints.

Satisfies the acceptance criterion: "Metrics displayed in panel 1/2 match
`backtest/metrics.py` output byte-for-byte — verified by a test that hits the
FastAPI endpoint."
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backtest.metrics import summary
from indie_market_analyst import api_server
from indie_market_analyst.memory.store import MemoryStore


def _seed_blob_and_store(tmp_path):
    db = tmp_path / "api_test.db"
    store = MemoryStore(db_path=db)
    idx = pd.date_range("2024-01-02", periods=50, freq="B")
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0.0005, 0.01, size=50), index=idx)
    equity = (1.0 + returns).cumprod() * 100_000.0
    metrics = summary(equity, returns)
    blob = {
        "run_id": "fixed-id",
        "symbol": "TEST",
        "strategy": "fixture",
        "period": "3mo",
        "interval": "1d",
        "initial_capital": 100_000.0,
        "intraday": False,
        "as_of_utc": "2024-04-01T00:00:00+00:00",
        "source": "backtest",
        "start_date": str(idx[0].date()),
        "end_date": str(idx[-1].date()),
        "metrics": metrics,
        "costs": {
            "brokerage": 0.0, "stt": 12.3, "stamp": 4.5,
            "exch": 1.2, "sebi": 0.1, "gst": 2.5, "total": 20.6,
        },
        "turnover": 5.0,
        "trades": [
            {
                "entry_date": "2024-01-02", "exit_date": "2024-01-10",
                "side": "long", "entry_price": 100.0, "exit_price": 103.0,
                "qty": 1000.0, "pnl": 2980.0, "cost": 20.0, "return_pct": 0.0298,
            },
        ],
        "equity_curve": [
            {"date": str(d.date()), "equity": float(v)}
            for d, v in equity.items()
        ],
        "artifact_path": None,
    }
    run_id = store.save_run("system", "backtest", "ok", blob)
    return store, run_id, metrics


def test_metrics_endpoint_matches_backtest_metrics(tmp_path, monkeypatch):
    store, run_id, metrics = _seed_blob_and_store(tmp_path)
    monkeypatch.setattr(api_server, "get_store", lambda: store)

    client = TestClient(api_server.app)
    r = client.get(f"/runs/{run_id}/metrics.json")
    assert r.status_code == 200
    # Byte-for-byte with backtest.metrics.summary()
    assert r.json() == metrics


def test_list_runs_includes_summary(tmp_path, monkeypatch):
    store, run_id, _ = _seed_blob_and_store(tmp_path)
    monkeypatch.setattr(api_server, "get_store", lambda: store)

    client = TestClient(api_server.app)
    r = client.get("/runs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == run_id
    assert row["summary"]["symbol"] == "TEST"
    assert row["summary"]["strategy"] == "fixture"
    assert "sharpe" in row["summary"]


def test_get_run_detail_returns_full_blob(tmp_path, monkeypatch):
    store, run_id, _ = _seed_blob_and_store(tmp_path)
    monkeypatch.setattr(api_server, "get_store", lambda: store)

    client = TestClient(api_server.app)
    r = client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["blob"]["symbol"] == "TEST"
    assert len(body["blob"]["equity_curve"]) == 50

    r = client.get("/runs/fixed-id")
    assert r.status_code == 200
    assert r.json()["id"] == run_id


def test_trades_csv_export(tmp_path, monkeypatch):
    store, run_id, _ = _seed_blob_and_store(tmp_path)
    monkeypatch.setattr(api_server, "get_store", lambda: store)

    client = TestClient(api_server.app)
    r = client.get(f"/runs/{run_id}/trades.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "entry_date,exit_date,side" in body.splitlines()[0]
    assert "long" in body
