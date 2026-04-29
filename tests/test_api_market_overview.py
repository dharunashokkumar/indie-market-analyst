from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from indie_market_analyst import api_server


class _Digest:
    def model_dump(self, mode: str = "json"):
        return {
            "items": [
                {
                    "title": "Nifty holds gains as banks lead",
                    "link": "https://example.com/nifty",
                    "published_utc": "2026-04-29T05:00:00+00:00",
                    "summary": "",
                    "source": "test_rss",
                    "sentiment": "bull",
                }
            ],
            "total": 1,
            "bullish": 1,
            "bearish": 0,
            "neutral": 0,
            "overall_sentiment": "bullish",
            "sentiment_score": 1.0,
            "as_of_utc": "2026-04-29T05:00:00+00:00",
            "sources_used": ["test_rss"],
        }


def _all_indices():
    return [
        {
            "index": "NIFTY 50",
            "last": 22500,
            "variation": 100,
            "percentChange": 0.45,
            "previousClose": 22400,
            "high": 22580,
            "low": 22380,
            "timeVal": "29-Apr-2026 15:30:00",
        },
        {
            "index": "NIFTY BANK",
            "last": 48000,
            "variation": -120,
            "percentChange": -0.25,
            "previousClose": 48120,
            "high": 48200,
            "low": 47750,
            "timeVal": "29-Apr-2026 15:30:00",
        },
        {
            "index": "NIFTY IT",
            "last": 36000,
            "variation": 180,
            "percentChange": 0.5,
            "previousClose": 35820,
            "high": 36100,
            "low": 35700,
            "timeVal": "29-Apr-2026 15:30:00",
        },
    ]


def _constituents(index: str):
    assert index == "NIFTY 500"
    return {
        "advance": {"advances": "2", "declines": "1", "unchanged": "0"},
        "data": [
            {
                "symbol": "GAIN",
                "lastPrice": 110,
                "previousClose": 100,
                "pChange": 10,
                "dayHigh": 112,
                "dayLow": 99,
                "totalTradedVolume": 1000,
                "totalTradedValue": 110000,
                "meta": {"companyName": "Gain Limited"},
            },
            {
                "symbol": "RELIANCE",
                "lastPrice": 2500,
                "previousClose": 2475,
                "pChange": 1.01,
                "dayHigh": 2520,
                "dayLow": 2460,
                "totalTradedVolume": 5000,
                "totalTradedValue": 12500000,
                "meta": {"companyName": "Reliance Industries Limited"},
            },
            {
                "symbol": "LOSE",
                "lastPrice": 90,
                "previousClose": 100,
                "pChange": -10,
                "dayHigh": 101,
                "dayLow": 89,
                "totalTradedVolume": 2000,
                "totalTradedValue": 180000,
                "meta": {"companyName": "Lose Limited"},
            },
        ],
    }


def _chart(index: str):
    start = 1_777_435_500_000
    base = {
        "NIFTY 50": 22400,
        "NIFTY BANK": 48120,
        "NIFTY IT": 35820,
    }.get(index, 1000)
    return {
        "grapthData": [
            [start, base],
            [start + 900_000, base + 40],
            [start + 1_800_000, base + 10],
            [start + 2_700_000, base + 80],
        ]
    }


def test_market_overview_uses_nse_and_rss(monkeypatch, tmp_path):
    monkeypatch.setattr(api_server, "MARKET_OVERVIEW_CACHE_PATH", tmp_path / "overview.json")
    monkeypatch.setattr(api_server, "fetch_all_indices", _all_indices)
    monkeypatch.setattr(api_server, "fetch_index_constituents", _constituents)
    monkeypatch.setattr(api_server, "fetch_index_chart", _chart)
    monkeypatch.setattr(api_server, "fetch_market_news", lambda **kwargs: _Digest())

    body = TestClient(api_server.app).get("/market/overview").json()

    assert body["source"] == "nseindia+rss"
    assert body["universe"] == "NIFTY 500"
    assert body["indices"][0]["source"] == "nseindia"
    assert body["indices"][0]["change_pct"] == 0.0045000000000000005
    assert body["watchlist"][0]["symbol"] == "RELIANCE"
    assert body["top_gainers"][0]["symbol"] == "GAIN"
    assert body["top_losers"][0]["symbol"] == "LOSE"
    assert body["breadth"] == {
        "advances": 2,
        "declines": 1,
        "unchanged": 0,
        "total": 3,
    }
    assert body["news"]["items"][0]["title"] == "Nifty holds gains as banks lead"
    assert len(body["indices"][0]["sparkline"]) == 4


def test_market_overview_serves_off_market_cache(monkeypatch, tmp_path):
    payload = {
        "indices": [{"symbol": "^NSEI", "sparkline": []}],
        "watchlist": [],
        "most_traded": [],
        "top_volume": [],
        "top_gainers": [],
        "top_losers": [],
        "sectors": [],
        "breadth": {"advances": 0, "declines": 0, "unchanged": 0, "total": 0},
        "news": {"items": [], "total": 0},
        "as_of_utc": "2026-04-29T14:30:00+00:00",
        "source": "nseindia+rss",
    }
    cache_path = tmp_path / "overview.json"
    cache_path.write_text(
        api_server.json.dumps(
            {
                "written_at_utc": "2026-04-29T14:30:00+00:00",
                "market_date_ist": "2026-04-29",
                "market_open": False,
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "MARKET_OVERVIEW_CACHE_PATH", cache_path)
    monkeypatch.setattr(
        api_server,
        "_market_now_ist",
        lambda now_utc: datetime(2026, 4, 29, 20, 0, tzinfo=api_server.NSE_MARKET_TZ),
    )
    monkeypatch.setattr(
        api_server,
        "fetch_all_indices",
        lambda: (_ for _ in ()).throw(AssertionError("cache should be used")),
    )

    body = TestClient(api_server.app).get("/market/overview").json()

    assert body == payload


def test_market_overview_serves_fresh_market_cache(monkeypatch, tmp_path):
    now_utc = datetime.now(UTC)
    now_ist = api_server._market_now_ist(now_utc)
    payload = {
        "indices": [{"symbol": "^NSEI", "sparkline": []}],
        "watchlist": [],
        "most_traded": [],
        "top_volume": [],
        "top_gainers": [],
        "top_losers": [],
        "sectors": [],
        "breadth": {"advances": 0, "declines": 0, "unchanged": 0, "total": 0},
        "news": {"items": [], "total": 0},
        "as_of_utc": now_utc.isoformat(),
        "source": "nseindia+rss",
    }
    cache_path = tmp_path / "overview.json"
    cache_path.write_text(
        api_server.json.dumps(
            {
                "written_at_utc": now_utc.isoformat(),
                "market_date_ist": now_ist.date().isoformat(),
                "market_open": True,
                "payload": payload,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "MARKET_OVERVIEW_CACHE_PATH", cache_path)
    monkeypatch.setattr(api_server, "_is_nse_market_open", lambda now_ist: True)
    monkeypatch.setattr(
        api_server,
        "fetch_all_indices",
        lambda: (_ for _ in ()).throw(AssertionError("fresh 15m cache should be used")),
    )

    body = TestClient(api_server.app).get("/market/overview").json()

    assert body == payload
