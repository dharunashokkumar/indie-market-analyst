import type { BacktestRunBlob, TradeRecord } from "../../lib/api";

export function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(2)}%`;
}
export function formatNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}
export function formatINR(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `₹${v.toFixed(2)}`;
}

export function CostBreakdownCard({ blob }: { blob: BacktestRunBlob }) {
  const c = blob.costs;
  const rows: { label: string; value: number }[] = [
    { label: "Brokerage", value: c.brokerage },
    { label: "STT", value: c.stt },
    { label: "Stamp duty", value: c.stamp },
    { label: "Exchange txn", value: c.exch },
    { label: "SEBI fee", value: c.sebi },
    { label: "GST", value: c.gst },
  ];
  return (
    <div className="cost-breakdown">
      <div className="cost-breakdown-header">Cost breakdown</div>
      <table>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="num">{formatINR(r.value)}</td>
            </tr>
          ))}
          <tr className="cost-total">
            <td>Total</td>
            <td className="num">{formatINR(c.total)}</td>
          </tr>
        </tbody>
      </table>
      <div className="cost-breakdown-hint">
        Per-component costs from the Indian cost model (STT, stamp duty, exchange
        txn, SEBI fee, GST, Zerodha-style brokerage).
      </div>
    </div>
  );
}

export function MetricsBox({ blob }: { blob: BacktestRunBlob }) {
  return (
    <div className="metrics-box">
      <div className="metrics-box-header">Summary metrics</div>
      <dl>
        <dt>CAGR</dt>
        <dd>{formatPct(blob.metrics.annualized_return)}</dd>
        <dt>Sharpe</dt>
        <dd>{formatNum(blob.metrics.sharpe)}</dd>
        <dt>Sortino</dt>
        <dd>{formatNum(blob.metrics.sortino)}</dd>
        <dt>Max DD</dt>
        <dd>{formatPct(blob.metrics.max_drawdown)}</dd>
        <dt>Ann. Vol</dt>
        <dd>{formatPct(blob.metrics.volatility_annualized)}</dd>
        <dt>Turnover</dt>
        <dd>{formatNum(blob.turnover, 1)}</dd>
      </dl>
    </div>
  );
}

export function TradeLog({ trades }: { trades: TradeRecord[] }) {
  if (trades.length === 0) {
    return <div className="panel-status">No closed trades in this run.</div>;
  }
  return (
    <div className="trade-log-wrap">
      <table className="trade-log-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Exit</th>
            <th className="num">Entry price</th>
            <th className="num">Exit price</th>
            <th className="num">Qty</th>
            <th className="num">P&amp;L</th>
            <th className="num">Cost</th>
            <th className="num">Return</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>
                <span className={`trade-side trade-side-${t.side}`}>{t.side}</span>
              </td>
              <td>{t.entry_date}</td>
              <td>{t.exit_date}</td>
              <td className="num">{formatNum(t.entry_price)}</td>
              <td className="num">{formatNum(t.exit_price)}</td>
              <td className="num">{formatNum(t.qty, 0)}</td>
              <td className={`num ${t.pnl >= 0 ? "pos" : "neg"}`}>{formatINR(t.pnl)}</td>
              <td className="num">{formatINR(t.cost)}</td>
              <td className={`num ${t.return_pct >= 0 ? "pos" : "neg"}`}>
                {formatPct(t.return_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
