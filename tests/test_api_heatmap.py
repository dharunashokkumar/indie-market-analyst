"""Tests for GET /indices/heatmap — schema + strictness."""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from indie_market_analyst import api_server
from indie_market_analyst.tools.market_data import heatmap_tool


def _fake_download(**kwargs):
    """Return a multi-ticker yfinance-style DataFrame with 5 close bars."""
    tickers = kwargs["tickers"]
    if isinstance(tickers, str):
        tickers = [tickers]
    idx = pd.date_range("2024-04-01", periods=5, freq="B")
    frames = {}
    rng = np.random.default_rng(1)
    for i, sym in enumerate(tickers):
        closes = 100.0 + np.cumsum(rng.normal(0.5, 1.0, size=5))
        df = pd.DataFrame(
            {
                "Open": closes,
                "High": closes + 1,
                "Low": closes - 1,
                "Close": closes,
                "Volume": [1000 + i] * 5,
            },
            index=idx,
        )
        frames[sym] = df
    if len(tickers) == 1:
        return frames[tickers[0]]
    return pd.concat(frames, axis=1)


def test_heatmap_endpoint_schema(monkeypatch):
    monkeypatch.setattr(heatmap_tool.yf, "download", _fake_download)
    client = TestClient(api_server.app)
    r = client.get("/indices/heatmap")
    assert r.status_code == 200
    body = r.json()
    for group in ("nifty50", "banknifty", "sectors"):
        assert group in body
        assert isinstance(body[group], list)
        assert len(body[group]) > 0
        cell = body[group][0]
        assert set(cell.keys()) == {
            "symbol", "name", "last", "change_pct", "as_of_utc", "source",
        }
        assert cell["source"] == "yfinance"
        assert cell["as_of_utc"]


def test_heatmap_change_pct_computed(monkeypatch):
    monkeypatch.setattr(heatmap_tool.yf, "download", _fake_download)
    client = TestClient(api_server.app)
    body = client.get("/indices/heatmap").json()
    # At least the first cell should have a numeric change_pct
    cells = body["nifty50"]
    with_change = [c for c in cells if c["change_pct"] is not None]
    assert len(with_change) > 0
