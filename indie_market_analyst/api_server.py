"""FastAPI gateway. SSE-streamed chat + run/session read APIs."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

from .agent.orchestrator import run_turn
from .data.instruments import instrument_groups, search_instruments
from .data.universes import get_universe, universe_options
from .memory.store import get_store
from .tools.market_data.heatmap_tool import _snapshot as heatmap_snapshot

load_dotenv()

app = FastAPI(title="indie-market-analyst", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    {"symbol": "^NSEI", "name": "Nifty 50", "exchange": "NSE", "currency": "POINTS"},
    {"symbol": "^BSESN", "name": "Sensex", "exchange": "BSE", "currency": "POINTS"},
    {"symbol": "^NSEBANK", "name": "Nifty Bank", "exchange": "NSE", "currency": "POINTS"},
    {"symbol": "^CNXIT", "name": "Nifty IT", "exchange": "NSE", "currency": "POINTS"},
]

MARKET_WATCHLIST_SPECS: list[dict[str, str]] = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "currency": "INR"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "currency": "INR"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank", "exchange": "NSE", "currency": "INR"},
    {"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "currency": "INR"},
    {"symbol": "TCS.NS", "name": "TCS", "exchange": "NSE", "currency": "INR"},
    {"symbol": "SBIN.NS", "name": "State Bank of India", "exchange": "NSE", "currency": "INR"},
]

MARKET_TRADING_SPECS: list[dict[str, str]] = [
    *MARKET_WATCHLIST_SPECS,
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel", "exchange": "NSE", "currency": "INR"},
    {"symbol": "ITC.NS", "name": "ITC", "exchange": "NSE", "currency": "INR"},
    {"symbol": "LT.NS", "name": "L&T", "exchange": "NSE", "currency": "INR"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank", "exchange": "NSE", "currency": "INR"},
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors", "exchange": "NSE", "currency": "INR"},
    {"symbol": "ONGC.NS", "name": "ONGC", "exchange": "NSE", "currency": "INR"},
    {"symbol": "TATASTEEL.NS", "name": "Tata Steel", "exchange": "NSE", "currency": "INR"},
    {"symbol": "ADANIPORTS.NS", "name": "Adani Ports", "exchange": "NSE", "currency": "INR"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance", "exchange": "NSE", "currency": "INR"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharma", "exchange": "NSE", "currency": "INR"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki", "exchange": "NSE", "currency": "INR"},
    {"symbol": "NTPC.NS", "name": "NTPC", "exchange": "NSE", "currency": "INR"},
]


def _market_specs_unique(specs: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for spec in specs:
        symbol = spec["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(spec)
    return out


def _history_frame_for_symbol(df: pd.DataFrame, symbol: str, multi: bool) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    if not multi:
        return df
    try:
        frame = df[symbol]
        return frame if isinstance(frame, pd.DataFrame) else None
    except KeyError:
        return None


def _market_quote_from_frame(
    spec: dict[str, str],
    frame: pd.DataFrame | None,
) -> dict[str, Any] | None:
    if frame is None or frame.empty or "Close" not in frame.columns:
        return None
    closes = frame["Close"].dropna()
    if closes.empty:
        return None

    last_idx = closes.index[-1]
    last_price = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else last_price
    change_pct = (last_price - prev_close) / prev_close if prev_close else 0.0

    last_row = frame.loc[last_idx]
    volume = (
        float(last_row["Volume"])
        if "Volume" in frame.columns and pd.notna(last_row["Volume"])
        else 0.0
    )
    day_high = (
        float(last_row["High"])
        if "High" in frame.columns and pd.notna(last_row["High"])
        else last_price
    )
    day_low = (
        float(last_row["Low"])
        if "Low" in frame.columns and pd.notna(last_row["Low"])
        else last_price
    )
    sparkline = [
        {
            "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
            "value": float(value),
        }
        for idx, value in closes.tail(8).items()
    ]

    return {
        **spec,
        "last_price": last_price,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "day_high": day_high,
        "day_low": day_low,
        "volume": volume,
        "turnover": last_price * volume if volume else 0.0,
        "as_of": str(last_idx.date()) if hasattr(last_idx, "date") else str(last_idx),
        "source": "yfinance",
        "sparkline": sparkline,
    }


def _market_batch_quotes(specs: list[dict[str, str]]) -> list[dict[str, Any]]:
    specs = _market_specs_unique(specs)
    symbols = [spec["symbol"] for spec in specs]
    if not symbols:
        return []
    df = yf.download(
        tickers=symbols,
        period="8d",
        interval="1d",
        progress=False,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
    )
    multi = len(symbols) > 1
    quotes: list[dict[str, Any]] = []
    for spec in specs:
        quote = _market_quote_from_frame(
            spec,
            _history_frame_for_symbol(df, spec["symbol"], multi),
        )
        if quote is not None:
            quotes.append(quote)
    return quotes


def _market_numeric(value: Any, fallback: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else fallback


@app.get("/market/overview")
def market_overview():
    specs = _market_specs_unique([
        *MARKET_INDEX_SPECS,
        *MARKET_WATCHLIST_SPECS,
        *MARKET_TRADING_SPECS,
    ])
    try:
        quotes = _market_batch_quotes(specs)
    except Exception as e:
        raise HTTPException(502, f"market data fetch failed: {e}") from e

    by_symbol = {q["symbol"]: q for q in quotes}
    indices = [by_symbol[s["symbol"]] for s in MARKET_INDEX_SPECS if s["symbol"] in by_symbol]
    watchlist = [by_symbol[s["symbol"]] for s in MARKET_WATCHLIST_SPECS if s["symbol"] in by_symbol]
    trading = [by_symbol[s["symbol"]] for s in MARKET_TRADING_SPECS if s["symbol"] in by_symbol]
    volume_rows = [q for q in trading if q.get("volume")]

    try:
        heatmap = heatmap_snapshot()
        sectors = [
            {
                "symbol": c.symbol,
                "name": c.name,
                "exchange": "NSE",
                "currency": "POINTS",
                "last_price": c.last,
                "prev_close": None,
                "change_pct": (c.change_pct / 100.0) if c.change_pct is not None else None,
                "day_high": None,
                "day_low": None,
                "volume": 0,
                "turnover": 0,
                "as_of": c.as_of_utc,
                "source": c.source,
                "sparkline": [],
            }
            for c in heatmap.sectors
        ]
        breadth_cells = [c for c in heatmap.nifty50 if c.change_pct is not None]
        advances = sum(1 for c in breadth_cells if (c.change_pct or 0) > 0)
        declines = sum(1 for c in breadth_cells if (c.change_pct or 0) < 0)
        unchanged = max(len(heatmap.nifty50) - advances - declines, 0)
    except Exception:
        sectors = []
        advances = sum(1 for q in trading if (q.get("change_pct") or 0) > 0)
        declines = sum(1 for q in trading if (q.get("change_pct") or 0) < 0)
        unchanged = max(len(trading) - advances - declines, 0)

    return {
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
        "breadth": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "total": advances + declines + unchanged,
        },
        "as_of_utc": datetime.now(UTC).isoformat(),
        "source": "yfinance",
    }


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
