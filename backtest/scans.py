"""Market-wide scanner: run every strategy on every symbol in a chosen universe.

Runs in a background thread; persists incremental results to JSON in
``data/scans/scan_<id>.json`` so the UI can poll for progress and reload past
scans on restart."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .loaders.registry import load as load_ohlcv
from .runner import run as run_backtest
from .strategies import STRATEGIES
from .strategies.summary import aggregate_runs

_SCANS_DIR = Path(__file__).resolve().parent.parent / "data" / "scans"
_SCANS_DIR.mkdir(parents=True, exist_ok=True)

_STATE: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_PERSIST_EVERY = 5  # write JSON every N companies

# Cap how often we save metrics-on-disk for active scans
_VALID_VERDICTS = {"MOSTLY_BULLISH", "MOSTLY_BEARISH", "MIXED", "NO_DATA"}


def _now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _signal_label_age(signals) -> tuple[str, int]:
    if len(signals) == 0:
        return "FLAT", 0
    last = float(signals.iloc[-1])
    label = "LONG" if last > 0 else ("SHORT" if last < 0 else "FLAT")
    age = 0
    for i in range(len(signals) - 1, 0, -1):
        if float(signals.iloc[i]) == float(signals.iloc[i - 1]):
            age += 1
        else:
            break
    return label, age


def _path_for(scan_id: str) -> Path:
    return _SCANS_DIR / f"scan_{scan_id}.json"


def _save(scan_id: str) -> None:
    with _LOCK:
        snapshot = json.loads(json.dumps(_STATE.get(scan_id, {}), default=str))
    _path_for(scan_id).write_text(json.dumps(snapshot, indent=2))


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    bullish = [r for r in results if r["aggregate"]["verdict"] == "MOSTLY_BULLISH"]
    bearish = [r for r in results if r["aggregate"]["verdict"] == "MOSTLY_BEARISH"]
    mixed = [r for r in results if r["aggregate"]["verdict"] == "MIXED"]

    def score(r: dict[str, Any]) -> int:
        a = r["aggregate"]
        return a["long_count"] - a["short_count"]

    ranked = sorted(results, key=score, reverse=True)
    top_bullish = [
        {"symbol": r["symbol"], "name": r.get("name", ""),
         "score": score(r), "last_close": r.get("last_close"),
         "long_count": r["aggregate"]["long_count"],
         "short_count": r["aggregate"]["short_count"]}
        for r in ranked[:10] if score(r) > 0
    ]
    top_bearish = [
        {"symbol": r["symbol"], "name": r.get("name", ""),
         "score": score(r), "last_close": r.get("last_close"),
         "long_count": r["aggregate"]["long_count"],
         "short_count": r["aggregate"]["short_count"]}
        for r in reversed(ranked[-10:]) if score(r) < 0
    ]

    total = len(results)
    pct_b = (len(bullish) / total * 100) if total else 0.0
    pct_s = (len(bearish) / total * 100) if total else 0.0

    if total == 0:
        market_mood = "UNKNOWN"
        beginner = "No companies completed."
    elif pct_b >= 25 and len(bullish) > len(bearish) * 1.5:
        market_mood = "BULLISH"
        beginner = (f"The market looks BULLISH — {len(bullish)} of {total} companies "
                    f"({pct_b:.0f}%) show buy signals across most strategies.")
    elif pct_s >= 25 and len(bearish) > len(bullish) * 1.5:
        market_mood = "BEARISH"
        beginner = (f"The market looks BEARISH — {len(bearish)} of {total} companies "
                    f"({pct_s:.0f}%) show sell signals across most strategies.")
    else:
        market_mood = "NEUTRAL"
        beginner = (f"The market is mostly UNDECIDED — {len(bullish)} bullish, "
                    f"{len(bearish)} bearish, {len(mixed)} mixed of {total}. "
                    "No clear direction across most stocks.")

    return {
        "total_companies": total,
        "total_bullish": len(bullish),
        "total_bearish": len(bearish),
        "total_mixed": len(mixed),
        "pct_bullish": round(pct_b, 1),
        "pct_bearish": round(pct_s, 1),
        "market_mood": market_mood,
        "beginner_takeaway": beginner,
        "top_bullish": top_bullish,
        "top_bearish": top_bearish,
    }


def _scan_one(symbol: str, period: str, interval: str) -> dict[str, Any]:
    df = load_ohlcv("yfinance", symbol=symbol, period=period, interval=interval)
    if df is None or df.empty:
        raise ValueError("no data")
    per_strategy: list[dict[str, Any]] = []
    for name, spec in STRATEGIES.items():
        try:
            sig = spec.fn(df, **spec.default_params)
            blob = run_backtest(
                symbol=symbol, signals=sig,
                period=period, interval=interval,
                strategy=name, persist=False,
                session_id="scan",
                data=df,
            )
            label, age = _signal_label_age(sig)
            metrics = blob.get("metrics") or {}
            per_strategy.append({
                "name": name, "label": spec.label, "category": spec.category,
                "current_signal": label, "signal_age_bars": age,
                "sharpe": metrics.get("sharpe"),
                "max_drawdown": metrics.get("max_drawdown"),
                "annualized_return": metrics.get("annualized_return"),
                "trades": len(blob.get("trades") or []),
            })
        except Exception as e:
            per_strategy.append({
                "name": name, "label": spec.label, "category": spec.category,
                "current_signal": "FLAT", "signal_age_bars": 0,
                "sharpe": None, "max_drawdown": None, "annualized_return": None,
                "trades": 0, "error": str(e),
            })
    agg = aggregate_runs(per_strategy)
    return {
        "symbol": symbol,
        "last_close": float(df["close"].iloc[-1]),
        "aggregate": agg,
        "per_strategy": per_strategy,
    }


def _worker(scan_id: str, items: list[dict[str, str]], period: str, interval: str) -> None:
    for i, row in enumerate(items):
        sym = row["yahoo_symbol"]
        name = row.get("name", "")
        try:
            res = _scan_one(sym, period, interval)
            res["name"] = name
            with _LOCK:
                _STATE[scan_id]["results"].append(res)
        except Exception as e:
            with _LOCK:
                _STATE[scan_id]["errors"].append({"symbol": sym, "name": name, "error": str(e)})
        with _LOCK:
            _STATE[scan_id]["done"] = i + 1
            _STATE[scan_id]["last_symbol"] = sym
            if _STATE[scan_id].get("cancel"):
                _STATE[scan_id]["status"] = "cancelled"
                break
        if (i + 1) % _PERSIST_EVERY == 0:
            _save(scan_id)

    with _LOCK:
        st = _STATE[scan_id]
        if st.get("status") == "running":
            st["status"] = "completed"
        st["completed_at"] = _now_utc()
        st["summary"] = _build_summary(st["results"])
    _save(scan_id)


def start_scan(items: list[dict[str, str]], *, universe_name: str,
               period: str = "1y", interval: str = "1d") -> str:
    scan_id = uuid.uuid4().hex[:10]
    with _LOCK:
        _STATE[scan_id] = {
            "scan_id": scan_id,
            "started_at": _now_utc(),
            "completed_at": None,
            "universe_name": universe_name,
            "universe_size": len(items),
            "done": 0,
            "last_symbol": None,
            "period": period,
            "interval": interval,
            "status": "running",
            "results": [],
            "errors": [],
            "summary": None,
            "cancel": False,
        }
    _save(scan_id)
    t = threading.Thread(
        target=_worker, args=(scan_id, items, period, interval),
        daemon=True, name=f"scan-{scan_id}",
    )
    t.start()
    return scan_id


def get_scan(scan_id: str, *, include_per_strategy: bool = False) -> dict[str, Any] | None:
    """Return scan state. If `include_per_strategy=False`, strips the heavy
    per_strategy detail from each row (still includes aggregate verdict)."""
    with _LOCK:
        state = _STATE.get(scan_id)
        if state is not None:
            data = json.loads(json.dumps(state, default=str))
        else:
            data = None
    if data is None:
        path = _path_for(scan_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
    if not include_per_strategy:
        for r in data.get("results", []):
            r.pop("per_strategy", None)
    return data


def list_scans(limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    paths = sorted(_SCANS_DIR.glob("scan_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    for path in paths:
        try:
            data = json.loads(path.read_text())
            out.append({
                "scan_id": data.get("scan_id"),
                "started_at": data.get("started_at"),
                "completed_at": data.get("completed_at"),
                "status": data.get("status"),
                "universe_name": data.get("universe_name"),
                "universe_size": data.get("universe_size"),
                "done": data.get("done"),
                "summary": data.get("summary"),
            })
        except Exception:
            continue
    return out


def cancel_scan(scan_id: str) -> bool:
    with _LOCK:
        if scan_id in _STATE and _STATE[scan_id]["status"] == "running":
            _STATE[scan_id]["cancel"] = True
            return True
    return False


def scans_dir() -> Path:
    return _SCANS_DIR


# Test/utility hook
def _reset_state() -> None:
    with _LOCK:
        _STATE.clear()


def _wait_done(scan_id: str, timeout: float = 30.0) -> None:
    """Block until a scan finishes (test helper)."""
    start = time.time()
    while time.time() - start < timeout:
        with _LOCK:
            st = _STATE.get(scan_id, {})
            if st.get("status") in ("completed", "cancelled", "failed"):
                return
        time.sleep(0.05)
    raise TimeoutError(f"scan {scan_id} did not finish within {timeout}s")
