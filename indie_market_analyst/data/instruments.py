"""Strategy dashboard instrument catalog.

NSE company shares still come from the checked-in NSE equity CSV. The other
asset classes are small curated Yahoo Finance symbol sets so the strategy
runner can reuse the existing yfinance loader without paid APIs.
"""

from __future__ import annotations

from typing import Any

from .nse_universe import load_nse_universe, search as search_nse

AssetRow = dict[str, str]

GROUPS: list[dict[str, str]] = [
    {
        "id": "equity",
        "label": "Company Equity Shares",
        "description": "NSE-listed company shares.",
        "source": "NSE list + yfinance OHLCV",
    },
    {
        "id": "commodity",
        "label": "Commodities",
        "description": "Liquid global futures proxies for metals and energy.",
        "source": "yfinance futures",
    },
    {
        "id": "mutual_fund",
        "label": "Mutual Funds & ETFs",
        "description": "Indian exchange-traded fund proxies with daily prices.",
        "source": "NSE/yfinance",
    },
    {
        "id": "global_index",
        "label": "Global Indices",
        "description": "Major US, European, and Asian market indices.",
        "source": "yfinance indices",
    },
    {
        "id": "indian_index",
        "label": "Indian Indices",
        "description": "Broad Indian equity benchmarks and sectors.",
        "source": "NSE/yfinance indices",
    },
    {
        "id": "crypto",
        "label": "Crypto",
        "description": "Major crypto USD pairs.",
        "source": "yfinance crypto",
    },
]


def _row(
    symbol: str,
    yahoo_symbol: str,
    name: str,
    currency: str,
    exchange: str,
) -> AssetRow:
    return {
        "symbol": symbol,
        "yahoo_symbol": yahoo_symbol,
        "name": name,
        "series": "",
        "isin": "",
        "listed_on": "",
        "currency": currency,
        "exchange": exchange,
    }


CURATED: dict[str, list[AssetRow]] = {
    "commodity": [
        _row("GOLD", "GC=F", "Gold Futures", "USD", "COMEX"),
        _row("SILVER", "SI=F", "Silver Futures", "USD", "COMEX"),
        _row("COPPER", "HG=F", "Copper Futures", "USD", "COMEX"),
        _row("CRUDE", "CL=F", "WTI Crude Oil Futures", "USD", "NYMEX"),
        _row("NATGAS", "NG=F", "Natural Gas Futures", "USD", "NYMEX"),
    ],
    "mutual_fund": [
        _row("NIFTYBEES", "NIFTYBEES.NS", "Nippon India ETF Nifty 50 BeES", "INR", "NSE"),
        _row("BANKBEES", "BANKBEES.NS", "Nippon India ETF Bank BeES", "INR", "NSE"),
        _row("JUNIORBEES", "JUNIORBEES.NS", "Nippon India ETF Junior BeES", "INR", "NSE"),
        _row("GOLDBEES", "GOLDBEES.NS", "Nippon India ETF Gold BeES", "INR", "NSE"),
        _row("LIQUIDBEES", "LIQUIDBEES.NS", "Nippon India ETF Liquid BeES", "INR", "NSE"),
        _row("MON100", "MON100.NS", "Motilal Oswal NASDAQ 100 ETF", "INR", "NSE"),
    ],
    "global_index": [
        _row("SP500", "^GSPC", "S&P 500", "POINTS", "S&P Dow Jones"),
        _row("NASDAQ", "^IXIC", "NASDAQ Composite", "POINTS", "NASDAQ"),
        _row("DOW", "^DJI", "Dow Jones Industrial Average", "POINTS", "S&P Dow Jones"),
        _row("FTSE100", "^FTSE", "FTSE 100", "POINTS", "LSE"),
        _row("DAX", "^GDAXI", "DAX Performance Index", "POINTS", "XETRA"),
        _row("NIKKEI225", "^N225", "Nikkei 225", "POINTS", "TSE"),
        _row("HANGSENG", "^HSI", "Hang Seng Index", "POINTS", "HKEX"),
    ],
    "indian_index": [
        _row("NIFTY50", "^NSEI", "Nifty 50", "POINTS", "NSE"),
        _row("BANKNIFTY", "^NSEBANK", "Nifty Bank", "POINTS", "NSE"),
        _row("SENSEX", "^BSESN", "BSE Sensex", "POINTS", "BSE"),
        _row("NIFTYIT", "^CNXIT", "Nifty IT", "POINTS", "NSE"),
    ],
    "crypto": [
        _row("BTC", "BTC-USD", "Bitcoin USD", "USD", "Crypto"),
        _row("ETH", "ETH-USD", "Ethereum USD", "USD", "Crypto"),
        _row("SOL", "SOL-USD", "Solana USD", "USD", "Crypto"),
        _row("BNB", "BNB-USD", "BNB USD", "USD", "Crypto"),
        _row("XRP", "XRP-USD", "XRP USD", "USD", "Crypto"),
        _row("ADA", "ADA-USD", "Cardano USD", "USD", "Crypto"),
        _row("DOGE", "DOGE-USD", "Dogecoin USD", "USD", "Crypto"),
    ],
}


def instrument_groups() -> list[dict[str, Any]]:
    """Return metadata for the strategy page asset-class selector."""
    equity_count = int(len(load_nse_universe()))
    out: list[dict[str, Any]] = []
    for group in GROUPS:
        group_id = group["id"]
        count = equity_count if group_id == "equity" else len(CURATED.get(group_id, []))
        out.append({**group, "count": count})
    return out


def search_instruments(asset_type: str, q: str = "", limit: int = 20) -> list[dict[str, str]]:
    """Search the selected asset class and normalize rows for the frontend."""
    asset_type = (asset_type or "equity").strip().lower()
    limit = max(1, min(int(limit), 100))
    if asset_type == "equity":
        rows = search_nse(q, limit=limit)
        return [
            {
                **row,
                "asset_type": "equity",
                "currency": "INR",
                "exchange": "NSE",
                "source": "nse_csv+yfinance",
            }
            for row in rows
        ]

    if asset_type not in CURATED:
        valid = ", ".join(group["id"] for group in GROUPS)
        raise ValueError(f"unknown asset_type: {asset_type}. Valid: {valid}")

    query = (q or "").strip().lower()
    rows = CURATED[asset_type]
    if query:
        rows = [
            row for row in rows
            if query in row["symbol"].lower()
            or query in row["yahoo_symbol"].lower()
            or query in row["name"].lower()
            or query in row["exchange"].lower()
        ]
    return [
        {
            **row,
            "asset_type": asset_type,
            "source": "yfinance",
        }
        for row in rows[:limit]
    ]
