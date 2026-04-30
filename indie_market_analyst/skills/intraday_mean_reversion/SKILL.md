# Intraday Mean Reversion chat skill

This skill is for the optional AI-assisted chat. It does not power the
deterministic `/intraday` scanner in `intraday_engine/`.

You are evaluating **intraday mean-reversion** setups on NSE equities.

## Core heuristics

1. Universe: liquid Nifty-500 names; skip symbols with ADV < 5 cr.
2. Signal: 15m RSI(14) < 30 **and** price below 20-SMA on 15m **and** in an
   oversold stretch of the broader daily trend (reject names in a strong daily
   downtrend with RSI(14) < 40 on daily).
3. Target: revert to the 20-SMA on 15m (or +1% from entry, whichever first).
4. Stop: 1 × ATR(14) on 15m below entry.
5. Time stop: close by 15:10 IST if target not hit.

## Rules

- Always call `get_history` on a fresh 15m window before recommending.
- Always quote the exact RSI, SMA, and close values used — never round them off
  without showing the raw numbers.
- Reject any setup where earnings are within ±2 sessions.
- Position size via fixed-fractional (risk ≤ 0.5% of capital) — do not hard-code
  lot sizes; ask.
