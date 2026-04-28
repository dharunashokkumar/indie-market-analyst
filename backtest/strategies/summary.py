"""Deterministic, beginner-friendly summaries for a single strategy run and
for the aggregate of running all strategies on one symbol.

No LLM. Pure rule-based text generation from metrics + signal state."""

from __future__ import annotations

from typing import Any


def _confidence(sharpe: float, trades: int, signal_age: int) -> str:
    """High when the strategy has good past Sharpe AND a recently established
    signal; low when sample is tiny or returns were poor."""
    if trades < 3:
        return "low"
    if sharpe >= 1.0 and signal_age >= 1:
        return "high"
    if sharpe >= 0.3:
        return "medium"
    return "low"


def _direction_phrase(signal: str) -> str:
    return {
        "LONG": "may go UP",
        "SHORT": "may go DOWN",
        "FLAT": "is UNCERTAIN",
    }[signal]


def _verdict_line(signal: str, symbol: str) -> str:
    if signal == "LONG":
        return f"BUY signal — the strategy thinks {symbol} will rise in the near term."
    if signal == "SHORT":
        return f"SELL signal — the strategy thinks {symbol} will fall in the near term."
    return f"WAIT signal — the strategy doesn't see a clear move in {symbol} right now."


def summarize_run(blob: dict[str, Any], current_signal: str,
                  signal_age: int, last_close: float) -> dict[str, Any]:
    """Build the engine summary for a single strategy backtest."""
    metrics = blob.get("metrics") or {}
    sharpe = float(metrics.get("sharpe") or 0.0)
    cagr = float(metrics.get("annualized_return") or 0.0)
    max_dd = float(metrics.get("max_drawdown") or 0.0)
    n_trades = len(blob.get("trades") or [])
    symbol = blob.get("symbol") or "the stock"

    confidence = _confidence(sharpe, n_trades, signal_age)
    headline = _verdict_line(current_signal, symbol)
    direction = _direction_phrase(current_signal)

    sharpe_note = (
        "above 1.0 is considered good"
        if sharpe >= 1.0 else
        "between 0 and 1 is okay" if sharpe >= 0 else
        "negative means it lost money"
    )
    performance = (
        f"Backtest over {blob.get('start_date', '?')} to {blob.get('end_date', '?')}: "
        f"about {cagr * 100:+.1f}% per year, "
        f"worst drop {max_dd * 100:.1f}%, "
        f"{n_trades} trade{'s' if n_trades != 1 else ''}. "
        f"Sharpe {sharpe:+.2f} ({sharpe_note})."
    )

    age_phrase = (
        "just changed today" if signal_age == 0 else
        f"steady for {signal_age} bar{'s' if signal_age != 1 else ''}"
    )

    beginner = (
        f"Right now the strategy says {symbol} {direction}. "
        f"This signal {age_phrase}. "
        f"Confidence based on the backtest is {confidence}. "
    )
    if confidence == "low":
        beginner += "Don't bet only on this — combine with other strategies."
    elif confidence == "high":
        beginner += "The strategy has a solid track record on this stock historically."
    else:
        beginner += "Track record is okay but not great. Treat as a hint, not a rule."

    return {
        "headline": headline,
        "direction": direction,
        "verdict": "BUY" if current_signal == "LONG"
                   else "SELL" if current_signal == "SHORT"
                   else "WAIT",
        "confidence": confidence,
        "performance": performance,
        "beginner_takeaway": beginner,
        "last_close": last_close,
    }


def aggregate_runs(per_strategy: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the list of per-strategy result dicts into one verdict.
    Each item must have keys: name, label, current_signal, sharpe, max_drawdown,
    annualized_return, signal_age_bars, error?"""
    ok = [r for r in per_strategy if not r.get("error")]
    longs = [r for r in ok if r["current_signal"] == "LONG"]
    shorts = [r for r in ok if r["current_signal"] == "SHORT"]
    flats = [r for r in ok if r["current_signal"] == "FLAT"]

    n = len(ok)
    n_long, n_short, n_flat = len(longs), len(shorts), len(flats)

    if n == 0:
        verdict = "NO_DATA"
        plain = "All strategies failed to run. Try a different symbol."
        confidence = "low"
    elif n_long > n_short and n_long >= max(n_flat, 1):
        verdict = "MOSTLY_BULLISH"
        plain = (f"{n_long} of {n} strategies say BUY. The price is more likely "
                 "to rise than fall in the near term.")
        confidence = "high" if n_long >= 0.6 * n else "medium"
    elif n_short > n_long and n_short >= max(n_flat, 1):
        verdict = "MOSTLY_BEARISH"
        plain = (f"{n_short} of {n} strategies say SELL. The price is more likely "
                 "to fall than rise in the near term.")
        confidence = "high" if n_short >= 0.6 * n else "medium"
    else:
        verdict = "MIXED"
        plain = (f"Strategies disagree (BUY={n_long}, SELL={n_short}, WAIT={n_flat}). "
                 "No clear consensus — wait for a clearer setup.")
        confidence = "low"

    # Top 3 by Sharpe (only positive Sharpes considered "trustworthy")
    by_sharpe = sorted(
        [r for r in ok if (r.get("sharpe") or 0) > 0],
        key=lambda r: -(r["sharpe"] or 0),
    )[:3]

    beginner = plain
    if by_sharpe:
        names = ", ".join(b["label"] for b in by_sharpe)
        beginner += f" The most trustworthy strategies on this stock historically: {names}."

    return {
        "verdict": verdict,
        "confidence": confidence,
        "long_count": n_long,
        "short_count": n_short,
        "flat_count": n_flat,
        "total": n,
        "plain": plain,
        "beginner_takeaway": beginner,
        "top_by_sharpe": [
            {"name": r["name"], "label": r["label"], "sharpe": r["sharpe"],
             "current_signal": r["current_signal"]}
            for r in by_sharpe
        ],
    }
