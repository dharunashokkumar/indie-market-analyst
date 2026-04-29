"""FastAPI gateway. SSE-streamed chat + run/session read APIs."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backtest import runner as backtest_runner, scans as scan_engine
from backtest.loaders.mcx_loader import get_mcx_icomdex, get_mcx_quote, is_mcx_symbol
from backtest.loaders.registry import load as load_ohlcv
from backtest.strategies import STRATEGIES
from backtest.strategies.summary import aggregate_runs, summarize_run
from intraday_engine.api.routes import router as intraday_router

from .agent.orchestrator import run_turn
from .data.instruments import instrument_groups, search_instruments
from .data.universes import get_universe, universe_options
from .memory.store import get_store
from .tools.market_data.heatmap_tool import _snapshot as heatmap_snapshot
from .tools.market_data.news_tool import fetch_market_news
from .tools.market_data.nse_scraper import (
    fetch_all_indices,
    fetch_index_chart,
    fetch_index_constituents,
)

load_dotenv()

app = FastAPI(title="indie-market-analyst", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(intraday_router)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    team: str | None = None


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def gen():
        async for ev in run_turn(req.message, session_id=req.session_id, team_override=req.team):
            payload: Any = ev.data
            if not isinstance(payload, (str, dict, list, int, float, bool)) and payload is not None:
                payload = str(payload)
            yield {"event": ev.kind, "data": json.dumps(payload, default=str)}
    return EventSourceResponse(gen())


@app.get("/sessions")
def list_sessions(limit: int = 200):
    return get_store().list_sessions(limit=limit)


@app.get("/sessions/search")
def search_sessions(q: str = "", limit: int = 50):
    return get_store().search_messages(q, limit=limit)


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    ok = get_store().delete_session(session_id)
    if not ok:
        raise HTTPException(404, "unknown session")
    return {"ok": True, "id": session_id}


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    store = get_store()
    if not store.session_exists(session_id):
        raise HTTPException(404, "unknown session")
    return store.get_messages(session_id)


@app.get("/runs")
def list_runs(session_id: str | None = None, limit: int = 50):
    """List runs newest-first. Includes a summary row extracted from the blob
    (symbol / strategy / period / sharpe / max_drawdown) when available, so the
    dashboards list view doesn't need a second round-trip per row."""
    store = get_store()
    rows = store.list_runs(session_id=session_id, limit=limit)
    out = []
    for row in rows:
        summary: dict[str, Any] = {}
        if row["kind"] == "backtest":
            full = store.get_run(row["id"])
            if full and isinstance(full.get("blob"), dict):
                b = full["blob"]
                metrics = b.get("metrics") or {}
                summary = {
                    "symbol": b.get("symbol"),
                    "strategy": b.get("strategy"),
                    "period": b.get("period"),
                    "start_date": b.get("start_date"),
                    "end_date": b.get("end_date"),
                    "sharpe": metrics.get("sharpe"),
                    "max_drawdown": metrics.get("max_drawdown"),
                }
        out.append({**row, "summary": summary})
    return out


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    r = get_store().get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    return r


@app.get("/runs/{run_id}/metrics.json")
def get_run_metrics(run_id: str):
    r = get_store().get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    blob = r.get("blob") or {}
    metrics = blob.get("metrics") or {}
    return metrics


@app.get("/runs/{run_id}/trades.csv")
def get_run_trades_csv(run_id: str):
    r = get_store().get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    blob = r.get("blob") or {}
    trades: list[dict[str, Any]] = blob.get("trades") or []
    buf = io.StringIO()
    fieldnames = [
        "entry_date", "exit_date", "side", "entry_price", "exit_price",
        "qty", "pnl", "cost", "return_pct",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for t in trades:
        writer.writerow({k: t.get(k) for k in fieldnames})
    csv_bytes = buf.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trades_{run_id[:8]}.csv"'},
    )


@app.get("/runs/{run_id}/benchmark")
def get_run_benchmark(run_id: str, benchmark: str = "^NSEI"):
    """Return the benchmark close series aligned to the run's date range.

    Skips (204) if fewer than 80% of the run's dates have matching benchmark
    closes.
    """
    r = get_store().get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    blob = r.get("blob") or {}
    curve = blob.get("equity_curve") or []
    if not curve:
        return Response(status_code=204)
    dates = [pt["date"] for pt in curve]
    start = blob.get("start_date") or dates[0]
    end = blob.get("end_date") or dates[-1]
    try:
        hist = yf.download(
            tickers=benchmark, start=start, end=end, interval="1d",
            progress=False, auto_adjust=False, threads=False,
        )
    except Exception:
        return Response(status_code=204)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return Response(status_code=204)
    closes = hist["Close"].dropna()
    series = pd.Series(
        closes.values.ravel() if hasattr(closes, "values") else list(closes),
        index=[str(idx.date()) for idx in closes.index],
    )
    matched = sum(1 for d in dates if d in series.index)
    if matched / max(len(dates), 1) < 0.8:
        return Response(status_code=204)
    base = None
    for d in dates:
        if d in series.index:
            base = float(series[d])
            break
    if not base:
        return Response(status_code=204)
    points = []
    for d in dates:
        if d in series.index:
            val = float(series[d])
            points.append({"date": d, "value": val, "normalized": val / base})
    return {"benchmark": benchmark, "points": points, "start_date": start, "end_date": end}


# ---------- Strategy dashboard ----------


class StrategyRunRequest(BaseModel):
    symbol: str
    strategy: str
    params: dict[str, float | int] | None = None
    period: str = "2y"
    interval: str = "1d"
    capital: float = 1_00_000.0
    session_id: str | None = None


def _strategy_loader_for_symbol(symbol: str) -> tuple[str, str]:
    if is_mcx_symbol(symbol):
        return "mcx", "mcxlib"
    return "yfinance", "yfinance"


@app.get("/strategy/symbols")
def strategy_symbols(q: str = "", limit: int = 25, asset_type: str = "equity"):
    try:
        return search_instruments(asset_type, q=q, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/strategy/instrument-groups")
def strategy_instrument_groups():
    return instrument_groups()


@app.get("/strategy/list")
def strategy_list():
    out = []
    for spec in STRATEGIES.values():
        out.append({
            "name": spec.name,
            "category": spec.category,
            "label": spec.label,
            "description": spec.description,
            "default_params": spec.default_params,
        })
    out.sort(key=lambda s: (s["category"], s["name"]))
    return out


@app.get("/strategy/quote/{symbol}")
def strategy_quote(symbol: str):
    """Lightweight quote snapshot for the instrument card."""
    loader_name, source = _strategy_loader_for_symbol(symbol)
    if loader_name == "mcx":
        try:
            return get_mcx_quote(symbol)
        except Exception as e:
            raise HTTPException(502, f"data fetch failed: {e}") from e

    try:
        df = load_ohlcv(loader_name, symbol=symbol, period="5d", interval="1d")
    except Exception as e:
        raise HTTPException(502, f"data fetch failed: {e}") from e
    if df is None or df.empty:
        raise HTTPException(404, f"no quote data for {symbol}")
    last = df.iloc[-1]
    prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
    last_close = float(last["close"])
    change_pct = (last_close - prev_close) / prev_close if prev_close else 0.0
    return {
        "symbol": symbol,
        "last_price": last_close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "day_high": float(last["high"]),
        "day_low": float(last["low"]),
        "volume": float(last.get("volume", 0.0)),
        "as_of": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        "source": source,
    }


@app.get("/strategy/mcx/icomdex")
def strategy_mcx_icomdex():
    """MCX iCOMDEX index snapshots keyed by commodity (GOLD, SILVER, ...)."""
    try:
        return get_mcx_icomdex()
    except Exception as e:
        raise HTTPException(502, f"icomdex fetch failed: {e}") from e


@app.get("/strategy/fx/usdinr")
def strategy_usdinr():
    """Latest USD/INR display conversion rate from yfinance."""
    try:
        df = load_ohlcv("yfinance", symbol="INR=X", period="5d", interval="1d")
    except Exception as e:
        raise HTTPException(502, f"fx fetch failed: {e}") from e
    if df is None or df.empty:
        raise HTTPException(404, "no USD/INR data")
    last = df.iloc[-1]
    return {
        "pair": "USDINR",
        "rate": float(last["close"]),
        "as_of": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        "source": "yfinance",
    }


# ---------- Market overview dashboard ----------


MARKET_INDEX_SPECS: list[dict[str, str]] = [
    {
        "nse_index": "NIFTY 50",
        "symbol": "^NSEI",
        "name": "Nifty 50",
        "exchange": "NSE",
        "currency": "POINTS",
    },
    {
        "nse_index": "NIFTY BANK",
        "symbol": "^NSEBANK",
        "name": "Nifty Bank",
        "exchange": "NSE",
        "currency": "POINTS",
    },
    {
        "nse_index": "NIFTY NEXT 50",
        "symbol": "^NIFTYNEXT50",
        "name": "Nifty Next 50",
        "exchange": "NSE",
        "currency": "POINTS",
    },
    {
        "nse_index": "NIFTY IT",
        "symbol": "^CNXIT",
        "name": "Nifty IT",
        "exchange": "NSE",
        "currency": "POINTS",
    },
]

MARKET_WATCHLIST_SYMBOLS: dict[str, str] = {
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "INFY": "Infosys",
    "TCS": "TCS",
    "SBIN": "State Bank of India",
}

MARKET_SECTOR_INDEX_SPECS: list[dict[str, str]] = [
    {"nse_index": "NIFTY IT", "symbol": "^CNXIT", "name": "Nifty IT"},
    {"nse_index": "NIFTY BANK", "symbol": "^NSEBANK", "name": "Nifty Bank"},
    {"nse_index": "NIFTY AUTO", "symbol": "^CNXAUTO", "name": "Nifty Auto"},
    {"nse_index": "NIFTY PHARMA", "symbol": "^CNXPHARMA", "name": "Nifty Pharma"},
    {"nse_index": "NIFTY FMCG", "symbol": "^CNXFMCG", "name": "Nifty FMCG"},
    {"nse_index": "NIFTY METAL", "symbol": "^CNXMETAL", "name": "Nifty Metal"},
    {"nse_index": "NIFTY ENERGY", "symbol": "^CNXENERGY", "name": "Nifty Energy"},
    {"nse_index": "NIFTY REALTY", "symbol": "^CNXREALTY", "name": "Nifty Realty"},
    {"nse_index": "NIFTY PSU BANK", "symbol": "^CNXPSUBANK", "name": "Nifty PSU Bank"},
]

MARKET_UNIVERSE_CANDIDATES = ("NIFTY 500", "NIFTY 200", "NIFTY 50")
MARKET_OVERVIEW_CACHE_PATH = Path("data") / "market_overview_cache.json"
MARKET_OVERVIEW_OPEN_TTL_SECONDS = 15 * 60
MARKET_OVERVIEW_SPARKLINE_LIMIT = 72
MARKET_OVERVIEW_QUOTE_LIST_KEYS = (
    "indices",
    "watchlist",
    "most_traded",
    "top_volume",
    "top_gainers",
    "top_losers",
    "sectors",
)
NSE_MARKET_TZ = ZoneInfo("Asia/Kolkata")
NSE_MARKET_OPEN = time(9, 15)
NSE_MARKET_CLOSE = time(15, 30)


def _market_now_ist(now_utc: datetime) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    return now_utc.astimezone(NSE_MARKET_TZ)


def _is_nse_market_open(now_ist: datetime) -> bool:
    if now_ist.weekday() >= 5:
        return False
    current_time = now_ist.time()
    return NSE_MARKET_OPEN <= current_time <= NSE_MARKET_CLOSE


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _read_market_overview_cache() -> dict[str, Any] | None:
    try:
        raw = MARKET_OVERVIEW_CACHE_PATH.read_text(encoding="utf-8")
        cache = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    return cache if isinstance(cache, dict) else None


def _market_cache_payload(cache: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = cache.get("payload") if isinstance(cache, dict) else None
    return payload if isinstance(payload, dict) else None


def _market_cache_age_seconds(cache: dict[str, Any], now_utc: datetime) -> float | None:
    written_at = _parse_utc_datetime(cache.get("written_at_utc"))
    if written_at is None:
        return None
    return max(0.0, (now_utc - written_at).total_seconds())


def _market_cached_payload_is_usable(
    cache: dict[str, Any] | None,
    now_utc: datetime,
    now_ist: datetime,
) -> bool:
    if _market_cache_payload(cache) is None:
        return False

    cache_date = str(cache.get("market_date_ist") or "")
    today = now_ist.date().isoformat()
    if cache_date != today:
        return False

    market_open_now = _is_nse_market_open(now_ist)
    cache_was_market_open = bool(cache.get("market_open"))
    if not market_open_now:
        return not cache_was_market_open

    age = _market_cache_age_seconds(cache, now_utc)
    return cache_was_market_open and age is not None and age < MARKET_OVERVIEW_OPEN_TTL_SECONDS


def _write_market_overview_cache(
    payload: dict[str, Any],
    now_utc: datetime,
    now_ist: datetime,
) -> None:
    cache = {
        "written_at_utc": now_utc.isoformat(),
        "market_date_ist": now_ist.date().isoformat(),
        "market_open": _is_nse_market_open(now_ist),
        "ttl_seconds_when_open": MARKET_OVERVIEW_OPEN_TTL_SECONDS,
        "payload": payload,
    }
    try:
        MARKET_OVERVIEW_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = MARKET_OVERVIEW_CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2, default=str), encoding="utf-8")
        tmp.replace(MARKET_OVERVIEW_CACHE_PATH)
    except OSError:
        pass


def _nse_index_key(value: Any) -> str:
    return " ".join(str(value or "").upper().split())


def _market_float_value(value: Any, fallback: float | None = None) -> float | None:
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "NA", "N/A"}:
        return fallback
    try:
        return float(text)
    except ValueError:
        return fallback


def _market_int_value(value: Any, fallback: int | None = None) -> int | None:
    number = _market_float_value(value)
    return int(number) if number is not None else fallback


def _market_float(row: dict[str, Any], *keys: str, fallback: float | None = None) -> float | None:
    for key in keys:
        value = _market_float_value(row.get(key))
        if value is not None:
            return value
    return fallback


def _market_text(row: dict[str, Any], *keys: str, fallback: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _market_change_ratio(
    last_price: float | None,
    prev_close: float | None,
    raw_pct: float | None,
) -> float | None:
    if raw_pct is not None:
        return raw_pct / 100.0
    if last_price is None or prev_close in (None, 0):
        return None
    return (last_price - prev_close) / prev_close


def _market_sparkline(prev_close: float | None, last_price: float | None) -> list[dict[str, Any]]:
    if prev_close is None or last_price is None:
        return []
    return [
        {"date": "previous", "value": prev_close},
        {"date": "last", "value": last_price},
    ]


def _thin_sparkline(points: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    if limit <= 2:
        return points[-limit:]
    step = (len(points) - 1) / (limit - 1)
    indexes = sorted({round(i * step) for i in range(limit)})
    return [points[i] for i in indexes]


def _normalize_sparkline_points(points: Any) -> list[dict[str, Any]]:
    if not isinstance(points, list):
        return []
    normalized: list[dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        value = _market_float_value(point.get("value"))
        if value is None:
            continue
        date = str(point.get("date") or point.get("time") or "").strip()
        normalized.append({"date": date or "point", "value": value})
    return normalized


def _sparkline_point_market_date(point: dict[str, Any]) -> str | None:
    dt = _parse_utc_datetime(point.get("date"))
    if dt is None:
        return None
    return _market_now_ist(dt).date().isoformat()


def _trim_sparkline_to_market_date(
    points: list[dict[str, Any]],
    market_date_ist: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for point in points:
        date_label = str(point.get("date") or "")
        if date_label == "previous":
            out.append(point)
            continue
        if _sparkline_point_market_date(point) == market_date_ist:
            out.append(point)
    return out


def _dedupe_sparkline(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for point in points:
        if out and out[-1].get("date") == point.get("date"):
            out[-1] = point
            continue
        out.append(point)
    return out


def _sparkline_from_nse_chart_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_points = (
        payload.get("grapthData")
        or payload.get("graphData")
        or payload.get("data")
        or payload.get("values")
        or []
    )
    if not isinstance(raw_points, list):
        return []

    points: list[dict[str, Any]] = []
    for raw in raw_points:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        value = _market_float_value(raw[1])
        if value is None:
            continue
        raw_time = raw[0]
        if isinstance(raw_time, (int, float)):
            seconds = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
            date = datetime.fromtimestamp(seconds, tz=UTC).isoformat()
        else:
            date = str(raw_time)
        points.append({"date": date, "value": value})
    return _thin_sparkline(_dedupe_sparkline(points), MARKET_OVERVIEW_SPARKLINE_LIMIT)


def _market_index_chart_sparklines() -> dict[str, list[dict[str, Any]]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for spec in MARKET_INDEX_SPECS:
        try:
            payload = fetch_index_chart(spec["nse_index"])
        except Exception:
            continue
        sparkline = _sparkline_from_nse_chart_payload(payload)
        if len(sparkline) >= 3:
            by_symbol[spec["symbol"]] = sparkline
    return by_symbol


def _fallback_range_sparkline(quote: dict[str, Any], now_utc: datetime) -> list[dict[str, Any]]:
    last_price = _market_float_value(quote.get("last_price"))
    prev_close = _market_float_value(quote.get("prev_close"), last_price)
    day_low = _market_float_value(quote.get("day_low"), min(prev_close or 0, last_price or 0))
    day_high = _market_float_value(quote.get("day_high"), max(prev_close or 0, last_price or 0))
    if last_price is None or prev_close is None or day_low is None or day_high is None:
        return []
    if day_high <= day_low:
        return _market_sparkline(prev_close, last_price)

    mid = (prev_close + last_price) / 2
    if last_price >= prev_close:
        values = [prev_close, day_low, mid, day_high, last_price]
    else:
        values = [prev_close, day_high, mid, day_low, last_price]
    labels = ["previous", "range-a", "range-b", "range-c", now_utc.isoformat()]
    return [{"date": label, "value": value} for label, value in zip(labels, values, strict=True)]


def _cached_sparklines_by_symbol(cache: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    payload = _market_cache_payload(cache)
    if payload is None:
        return {}
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for key in MARKET_OVERVIEW_QUOTE_LIST_KEYS:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for quote in rows:
            if not isinstance(quote, dict):
                continue
            symbol = str(quote.get("symbol") or "")
            sparkline = _normalize_sparkline_points(quote.get("sparkline"))
            if not symbol or len(sparkline) < 2:
                continue
            if len(sparkline) > len(by_symbol.get(symbol, [])):
                by_symbol[symbol] = sparkline
    return by_symbol


def _merge_quote_sparkline(
    quote: dict[str, Any],
    cached_sparkline: list[dict[str, Any]],
    now_utc: datetime,
    now_ist: datetime,
) -> list[dict[str, Any]]:
    current = _normalize_sparkline_points(quote.get("sparkline"))
    if len(current) >= 3 and current[-1].get("date") not in {"range-c", "last"}:
        return _thin_sparkline(current, MARKET_OVERVIEW_SPARKLINE_LIMIT)

    market_date = now_ist.date().isoformat()
    history = _trim_sparkline_to_market_date(cached_sparkline, market_date)
    if not history and current:
        history = [current[0]]

    last_price = _market_float_value(quote.get("last_price"))
    if last_price is not None:
        history.append({"date": now_utc.isoformat(), "value": last_price})
    history = _dedupe_sparkline(history)
    if len(history) >= 3:
        return _thin_sparkline(history, MARKET_OVERVIEW_SPARKLINE_LIMIT)
    return _fallback_range_sparkline(quote, now_utc)


def _apply_market_sparklines(
    payload: dict[str, Any],
    previous_cache: dict[str, Any] | None,
    now_utc: datetime,
    now_ist: datetime,
) -> None:
    cached = _cached_sparklines_by_symbol(previous_cache)
    for key in MARKET_OVERVIEW_QUOTE_LIST_KEYS:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for quote in rows:
            if not isinstance(quote, dict):
                continue
            symbol = str(quote.get("symbol") or "")
            quote["sparkline"] = _merge_quote_sparkline(
                quote,
                cached.get(symbol, []),
                now_utc,
                now_ist,
            )


def _market_numeric(value: Any, fallback: float = 0.0) -> float:
    number = _market_float_value(value)
    return number if number is not None else fallback


def _quote_from_nse_index(spec: dict[str, str], row: dict[str, Any]) -> dict[str, Any] | None:
    last_price = _market_float(row, "last", "lastPrice", "ltp")
    change_abs = _market_float(row, "variation", "change")
    prev_close = _market_float(row, "previousClose", "prevClose")
    if prev_close is None and last_price is not None and change_abs is not None:
        prev_close = last_price - change_abs
    raw_pct = _market_float(row, "percentChange", "pChange")
    change_pct = _market_change_ratio(last_price, prev_close, raw_pct)
    if last_price is None:
        return None
    return {
        "symbol": spec["symbol"],
        "name": spec["name"],
        "exchange": spec.get("exchange", "NSE"),
        "currency": spec.get("currency", "POINTS"),
        "last_price": last_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "day_high": _market_float(row, "high", "dayHigh", fallback=last_price),
        "day_low": _market_float(row, "low", "dayLow", fallback=last_price),
        "volume": 0,
        "turnover": 0,
        "as_of": _market_text(row, "lastUpdateTime", "timestamp", "timeVal"),
        "source": "nseindia",
        "sparkline": _market_sparkline(prev_close, last_price),
    }


def _quote_from_nse_equity(
    row: dict[str, Any],
    name_overrides: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    symbol = _market_text(row, "symbol").upper()
    if not symbol or (" " in symbol and not row.get("meta")):
        return None
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    name = (
        (name_overrides or {}).get(symbol)
        or _market_text(meta, "companyName")
        or _market_text(row, "companyName", "name", fallback=symbol)
    )
    last_price = _market_float(row, "lastPrice", "last", "ltp")
    change_abs = _market_float(row, "change", "variation")
    prev_close = _market_float(row, "previousClose", "prevClose")
    if prev_close is None and last_price is not None and change_abs is not None:
        prev_close = last_price - change_abs
    raw_pct = _market_float(row, "pChange", "percentChange")
    change_pct = _market_change_ratio(last_price, prev_close, raw_pct)
    if last_price is None:
        return None
    volume = _market_float(row, "totalTradedVolume", "quantityTraded", "volume", fallback=0) or 0
    turnover = _market_float(row, "totalTradedValue", "turnover")
    if turnover is None:
        turnover = last_price * volume if volume else 0
    return {
        "symbol": symbol,
        "name": name,
        "exchange": "NSE",
        "currency": "INR",
        "last_price": last_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "day_high": _market_float(row, "dayHigh", "high", fallback=last_price),
        "day_low": _market_float(row, "dayLow", "low", fallback=last_price),
        "volume": volume,
        "turnover": turnover,
        "as_of": _market_text(row, "lastUpdateTime", "timestamp", "timeVal"),
        "source": "nseindia",
        "sparkline": _market_sparkline(prev_close, last_price),
    }


def _rows_from_nse_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("data", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _market_indices_from_nse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index = {_nse_index_key(row.get("index")): row for row in rows}
    quotes: list[dict[str, Any]] = []
    for spec in MARKET_INDEX_SPECS:
        row = by_index.get(_nse_index_key(spec["nse_index"]))
        if row:
            quote = _quote_from_nse_index(spec, row)
            if quote:
                quotes.append(quote)
    return quotes


def _market_sectors_from_nse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index = {_nse_index_key(row.get("index")): row for row in rows}
    quotes: list[dict[str, Any]] = []
    for spec in MARKET_SECTOR_INDEX_SPECS:
        row = by_index.get(_nse_index_key(spec["nse_index"]))
        if row:
            quote = _quote_from_nse_index(
                {
                    **spec,
                    "exchange": "NSE",
                    "currency": "POINTS",
                },
                row,
            )
            if quote:
                quotes.append(quote)
    return quotes


def _market_trading_quotes_from_nse() -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    last_error: Exception | None = None
    for index in MARKET_UNIVERSE_CANDIDATES:
        try:
            payload = fetch_index_constituents(index)
        except Exception as e:  # pragma: no cover - exercised via endpoint failure handling
            last_error = e
            continue
        quotes = [
            quote
            for row in _rows_from_nse_payload(payload)
            if (quote := _quote_from_nse_equity(row, MARKET_WATCHLIST_SYMBOLS)) is not None
        ]
        if quotes:
            return index, payload, quotes
    if last_error is not None:
        raise last_error
    raise RuntimeError("NSE returned no market universe rows")


def _market_breadth_from_payload(
    payload: dict[str, Any],
    quotes: list[dict[str, Any]],
) -> dict[str, int]:
    advance = payload.get("advance") if isinstance(payload.get("advance"), dict) else {}
    advances = _market_int_value(advance.get("advances"))
    declines = _market_int_value(advance.get("declines"))
    unchanged = _market_int_value(advance.get("unchanged"), 0)
    if advances is None or declines is None:
        advances = sum(1 for q in quotes if (q.get("change_pct") or 0) > 0)
        declines = sum(1 for q in quotes if (q.get("change_pct") or 0) < 0)
        unchanged = max(len(quotes) - advances - declines, 0)
    unchanged = unchanged or 0
    return {
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "total": advances + declines + unchanged,
    }


def _empty_news_digest() -> dict[str, Any]:
    return {
        "items": [],
        "total": 0,
        "bullish": 0,
        "bearish": 0,
        "neutral": 0,
        "overall_sentiment": "neutral",
        "sentiment_score": 0.0,
        "as_of_utc": datetime.now(UTC).isoformat(),
        "sources_used": [],
    }


def _build_market_overview(
    previous_cache: dict[str, Any] | None,
    now_utc: datetime,
    now_ist: datetime,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        all_index_rows = fetch_all_indices()
    except Exception as e:
        all_index_rows = []
        errors.append(f"indices: {e}")

    try:
        universe_name, universe_payload, trading = _market_trading_quotes_from_nse()
    except Exception as e:
        universe_name = ""
        universe_payload = {}
        trading = []
        errors.append(f"universe: {e}")

    if not all_index_rows and not trading:
        detail = "; ".join(errors) or "NSE returned no market data"
        raise HTTPException(502, f"NSE market data fetch failed: {detail}")

    indices = _market_indices_from_nse(all_index_rows)
    index_sparklines = _market_index_chart_sparklines()
    for quote in indices:
        sparkline = index_sparklines.get(quote["symbol"])
        if sparkline:
            quote["sparkline"] = sparkline

    sectors = sorted(
        _market_sectors_from_nse(all_index_rows),
        key=lambda q: _market_numeric(q.get("change_pct")),
        reverse=True,
    )
    by_symbol = {q["symbol"]: q for q in trading}
    watchlist = [by_symbol[symbol] for symbol in MARKET_WATCHLIST_SYMBOLS if symbol in by_symbol]
    volume_rows = [q for q in trading if q.get("volume")]
    breadth = _market_breadth_from_payload(universe_payload, trading)

    try:
        news = fetch_market_news(limit=9).model_dump(mode="json")
    except Exception:
        news = _empty_news_digest()

    payload = {
        "indices": indices,
        "watchlist": watchlist,
        "most_traded": sorted(volume_rows, key=lambda q: q.get("turnover") or 0, reverse=True)[:6],
        "top_volume": sorted(volume_rows, key=lambda q: q.get("volume") or 0, reverse=True)[:6],
        "top_gainers": sorted(
            trading,
            key=lambda q: _market_numeric(q.get("change_pct"), -99.0),
            reverse=True,
        )[:6],
        "top_losers": sorted(
            trading,
            key=lambda q: _market_numeric(q.get("change_pct"), 99.0),
        )[:6],
        "sectors": sorted(
            sectors,
            key=lambda q: _market_numeric(q.get("change_pct")),
            reverse=True,
        ),
        "breadth": breadth,
        "news": news,
        "universe": universe_name,
        "as_of_utc": now_utc.isoformat(),
        "source": "nseindia+rss",
    }
    _apply_market_sparklines(payload, previous_cache, now_utc, now_ist)
    return payload


@app.get("/market/overview")
def market_overview():
    now_utc = datetime.now(UTC)
    now_ist = _market_now_ist(now_utc)
    cache = _read_market_overview_cache()
    if _market_cached_payload_is_usable(cache, now_utc, now_ist):
        cached = _market_cache_payload(cache)
        if cached is not None:
            return cached

    try:
        payload = _build_market_overview(cache, now_utc, now_ist)
    except HTTPException:
        cached = _market_cache_payload(cache)
        if cached is not None:
            return cached
        raise
    except Exception as e:
        cached = _market_cache_payload(cache)
        if cached is not None:
            return cached
        raise HTTPException(502, f"market overview fetch failed: {e}") from e

    _write_market_overview_cache(payload, now_utc, now_ist)
    return payload


def _signal_label_and_age(signals) -> tuple[str, int]:
    if len(signals) == 0:
        return "FLAT", 0
    last_sig = float(signals.iloc[-1])
    label = "LONG" if last_sig > 0 else ("SHORT" if last_sig < 0 else "FLAT")
    age = 0
    for i in range(len(signals) - 1, 0, -1):
        if float(signals.iloc[i]) == float(signals.iloc[i - 1]):
            age += 1
        else:
            break
    return label, age


def _run_one(symbol: str, strategy_name: str, df, *,
             period: str, interval: str, capital: float,
             session_id: str, persist: bool = True,
             param_overrides: dict | None = None) -> dict:
    spec = STRATEGIES[strategy_name]
    params = {**spec.default_params, **(param_overrides or {})}
    signals = spec.fn(df, **params)
    blob = backtest_runner.run(
        symbol=symbol, signals=signals,
        period=period, interval=interval,
        initial_capital=capital,
        strategy=strategy_name,
        session_id=session_id,
        persist=persist,
        data=df,
    )
    label, age = _signal_label_and_age(signals)
    last_close = float(df["close"].iloc[-1])
    summary = summarize_run(blob, label, age, last_close)
    return {
        "run": blob,
        "current_signal": label,
        "signal_age_bars": age,
        "last_close": last_close,
        "engine_summary": summary,
    }


@app.post("/strategy/run")
def strategy_run(req: StrategyRunRequest):
    if req.strategy not in STRATEGIES:
        raise HTTPException(400, f"unknown strategy: {req.strategy}")
    loader_name, _source = _strategy_loader_for_symbol(req.symbol)
    try:
        df = load_ohlcv(loader_name, symbol=req.symbol, period=req.period, interval=req.interval)
    except Exception as e:
        raise HTTPException(502, f"data fetch failed: {e}") from e
    if df is None or df.empty:
        raise HTTPException(404, f"no data for {req.symbol}")

    return _run_one(
        req.symbol, req.strategy, df,
        period=req.period, interval=req.interval,
        capital=req.capital,
        session_id=req.session_id or "strategy_dashboard",
        param_overrides=req.params,
    )


class StrategyRunAllRequest(BaseModel):
    symbol: str
    period: str = "2y"
    interval: str = "1d"
    capital: float = 1_00_000.0
    session_id: str | None = None
    persist: bool = False  # batch runs default to NOT persisting (12 rows is noisy)


@app.post("/strategy/run_all")
def strategy_run_all(req: StrategyRunAllRequest):
    """Run every registered strategy on `symbol` and return per-strategy results
    plus an aggregate verdict. One data fetch is shared across all 12 runs."""
    loader_name, _source = _strategy_loader_for_symbol(req.symbol)
    try:
        df = load_ohlcv(loader_name, symbol=req.symbol, period=req.period, interval=req.interval)
    except Exception as e:
        raise HTTPException(502, f"data fetch failed: {e}") from e
    if df is None or df.empty:
        raise HTTPException(404, f"no data for {req.symbol}")

    per_strategy: list[dict] = []
    for name, spec in STRATEGIES.items():
        try:
            res = _run_one(
                req.symbol, name, df,
                period=req.period, interval=req.interval,
                capital=req.capital,
                session_id=req.session_id or "strategy_dashboard_batch",
                persist=req.persist,
            )
            metrics = res["run"].get("metrics") or {}
            per_strategy.append({
                "name": name,
                "label": spec.label,
                "category": spec.category,
                "current_signal": res["current_signal"],
                "signal_age_bars": res["signal_age_bars"],
                "sharpe": metrics.get("sharpe"),
                "max_drawdown": metrics.get("max_drawdown"),
                "annualized_return": metrics.get("annualized_return"),
                "trades": len(res["run"].get("trades") or []),
                "engine_summary": res["engine_summary"],
            })
        except Exception as e:
            per_strategy.append({
                "name": name, "label": spec.label, "category": spec.category,
                "current_signal": "FLAT", "signal_age_bars": 0,
                "sharpe": None, "max_drawdown": None, "annualized_return": None,
                "trades": 0, "error": str(e),
            })

    aggregate = aggregate_runs(per_strategy)
    return {
        "symbol": req.symbol,
        "period": req.period,
        "last_close": float(df["close"].iloc[-1]),
        "per_strategy": per_strategy,
        "aggregate": aggregate,
    }


# ---------- Market scan ----------


class StartScanRequest(BaseModel):
    universe: str = "nifty50"
    period: str = "1y"
    interval: str = "1d"


@app.get("/strategy/universes")
def list_universes():
    return universe_options()


@app.post("/strategy/scan")
def scan_start(req: StartScanRequest):
    try:
        items = get_universe(req.universe)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not items:
        raise HTTPException(400, "empty universe")
    scan_id = scan_engine.start_scan(items, universe_name=req.universe,
                                     period=req.period, interval=req.interval)
    return {"scan_id": scan_id, "universe_size": len(items),
            "universe": req.universe, "started_at": scan_engine.get_scan(scan_id)["started_at"]}


@app.get("/strategy/scan")
def scan_list(limit: int = 30):
    return scan_engine.list_scans(limit=limit)


@app.get("/strategy/scan/{scan_id}")
def scan_get(scan_id: str, full: bool = False):
    state = scan_engine.get_scan(scan_id, include_per_strategy=full)
    if state is None:
        raise HTTPException(404, "unknown scan")
    return state


@app.post("/strategy/scan/{scan_id}/cancel")
def scan_cancel(scan_id: str):
    ok = scan_engine.cancel_scan(scan_id)
    if not ok:
        raise HTTPException(404, "scan not running")
    return {"ok": True, "scan_id": scan_id}


@app.get("/indices/heatmap")
def get_indices_heatmap():
    snap = heatmap_snapshot()
    return snap.model_dump(mode="json")


@app.get("/artifacts/{path:path}")
def get_artifact(path: str):
    # Only allow serving from runs/
    safe = Path("runs") / path
    if not safe.resolve().is_file() or "runs" not in str(safe.resolve()):
        raise HTTPException(404, "not found")
    return FileResponse(str(safe))


@app.get("/health")
def health():
    return {"status": "ok"}
