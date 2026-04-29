import { useEffect, useMemo, useState } from "react";
import {
  exportMetricsUrl,
  exportTradesUrl,
  getRun,
  listRuns,
  type BacktestRunBlob,
  type RunRow,
} from "../../lib/api";
import {
  CostBreakdownCard,
  MetricsBox,
  TradeLog,
  formatNum,
  formatPct,
} from "./_runDetail";
import { CompanyLogo } from "../../components/CompanyLogo";

function cleanSymbol(symbol: string): string {
  return symbol.replace(/\.NS$/i, "").replace(/\.BO$/i, "").replace(/^\^/, "");
}

function SymbolWithLogo({ symbol, size = 22 }: { symbol: string; size?: number }) {
  return (
    <div className="run-symbol">
      <CompanyLogo
        symbol={symbol}
        exchange={symbol.toUpperCase().endsWith(".BO") ? "BSE" : "NSE"}
        size={size}
      />
      <span>{cleanSymbol(symbol)}</span>
    </div>
  );
}

export function BacktestsPanel() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blob, setBlob] = useState<BacktestRunBlob | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listRuns().then((rows) => {
      const backtests = rows.filter((r) => r.kind === "backtest");
      setRuns(backtests);
    });
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setBlob(null);
      return;
    }
    setLoading(true);
    getRun(selectedId)
      .then((r) => setBlob(r?.blob ?? null))
      .finally(() => setLoading(false));
  }, [selectedId]);

  const selected = useMemo(
    () => runs.find((r) => r.id === selectedId) ?? null,
    [runs, selectedId],
  );

  if (runs.length === 0) {
    return (
      <div className="panel-empty">
        <p>No backtest runs yet.</p>
        <code>make seed-runs</code>
      </div>
    );
  }

  return (
    <div className="backtests-panel">
      <div className="backtests-list">
        <table className="runs-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Strategy</th>
              <th>Period</th>
              <th className="num">Sharpe</th>
              <th className="num">Max DD</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => {
              const s = r.summary ?? {};
              return (
                <tr
                  key={r.id}
                  className={selectedId === r.id ? "selected" : ""}
                  onClick={() => setSelectedId(r.id)}
                >
                  <td>
                    {s.symbol ? <SymbolWithLogo symbol={s.symbol} /> : r.id.slice(0, 8)}
                  </td>
                  <td>{s.strategy ?? "—"}</td>
                  <td>{s.period ?? "—"}</td>
                  <td className="num">{formatNum(s.sharpe)}</td>
                  <td className="num">{formatPct(s.max_drawdown)}</td>
                  <td>{new Date(r.created_at * 1000).toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="backtests-detail">
          <div className="backtests-detail-header">
            <div className="backtests-title">
              {selected.summary?.symbol && (
                <CompanyLogo
                  symbol={selected.summary.symbol}
                  exchange={selected.summary.symbol.toUpperCase().endsWith(".BO") ? "BSE" : "NSE"}
                  size={34}
                />
              )}
              <div>
                <h3>{selected.summary?.symbol ? cleanSymbol(selected.summary.symbol) : selected.id.slice(0, 8)}</h3>
                <div className="muted">
                  {selected.summary?.strategy ?? "—"} • {selected.summary?.period ?? "—"}
                </div>
              </div>
            </div>
            {blob && (
              <div className="export-buttons">
                <a
                  className="export-btn"
                  href={exportTradesUrl(selected.id)}
                  download
                >
                  Trades CSV
                </a>
                <a
                  className="export-btn"
                  href={exportMetricsUrl(selected.id)}
                  download={`metrics_${selected.id.slice(0, 8)}.json`}
                >
                  Metrics JSON
                </a>
              </div>
            )}
          </div>

          {loading && <div className="panel-status">Loading…</div>}
          {blob && (
            <>
              <div className="detail-grid">
                <CostBreakdownCard blob={blob} />
                <MetricsBox blob={blob} />
              </div>
              <TradeLog trades={blob.trades} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
