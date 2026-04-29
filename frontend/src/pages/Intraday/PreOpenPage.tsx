import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  getIntradayPreOpen,
  type IntradayPreOpenSnapshot,
} from "../../lib/api";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";

function formatPct(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number | null) {
  return value === null ? "-" : value.toFixed(value >= 1000 ? 1 : 2);
}

export function PreOpenPage() {
  const [snapshot, setSnapshot] = useState<IntradayPreOpenSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await getIntradayPreOpen(refresh));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="intraday-page">
      <IntradayNav />
      <ModeHeader mode={snapshot?.mode ?? null} modeOverride="1B" />
      <div className="intraday-page-toolbar">
        <div>
          <strong>Pre-open auction</strong>
          <span>{snapshot?.rows.length ?? 0} rows</span>
        </div>
        <button
          type="button"
          className="intraday-icon-text-btn"
          onClick={() => load(true)}
          disabled={loading}
        >
          <RefreshCw size={15} />
          {loading ? "Loading" : "Refresh"}
        </button>
      </div>

      {error && <div className="panel-status error">{error}</div>}

      <section className="intraday-mode-panel">
        <h3>Top auction reads</h3>
        <div className="intraday-simple-table">
          <div className="intraday-simple-head five">
            <span>Symbol</span>
            <span>Bias</span>
            <span>Move</span>
            <span>LTP</span>
            <span>Volume</span>
          </div>
          {(snapshot?.watchlist ?? []).map((row) => (
            <div className="intraday-simple-row five" key={row.symbol}>
              <strong>{row.symbol}</strong>
              <span>{row.bias}</span>
              <span className={row.pct_change && row.pct_change < 0 ? "is-down" : "is-up"}>
                {formatPct(row.pct_change)}
              </span>
              <span>{formatPrice(row.ltp)}</span>
              <span>{row.volume?.toLocaleString() ?? "-"}</span>
            </div>
          ))}
          {snapshot && snapshot.watchlist.length === 0 && (
            <div className="intraday-empty-state">No pre-open rows available.</div>
          )}
        </div>
      </section>

      {snapshot && snapshot.errors.length > 0 && (
        <div className="panel-status error">{snapshot.errors.join(" | ")}</div>
      )}
    </div>
  );
}
