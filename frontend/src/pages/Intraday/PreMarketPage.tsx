import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  getIntradayPreMarket,
  type IntradayMarketCue,
  type IntradayPreMarketSnapshot,
} from "../../lib/api";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";

function formatNumber(value: number | null) {
  if (value === null) return "-";
  return value.toFixed(Math.abs(value) >= 1000 ? 1 : 2);
}

function formatPct(value: number | null) {
  if (value === null) return "-";
  return `${(value * 100).toFixed(2)}%`;
}

function CueTable({ rows }: { rows: IntradayMarketCue[] }) {
  return (
    <div className="intraday-simple-table">
      <div className="intraday-simple-head four">
        <span>Name</span>
        <span>Symbol</span>
        <span>Last</span>
        <span>Move</span>
      </div>
      {rows.map((row) => (
        <div className="intraday-simple-row four" key={`${row.group}-${row.symbol}`}>
          <strong>{row.label}</strong>
          <span>{row.symbol}</span>
          <span>{formatNumber(row.last)}</span>
          <span className={row.change_pct && row.change_pct < 0 ? "is-down" : "is-up"}>
            {row.status === "ok" ? formatPct(row.change_pct) : row.status}
          </span>
        </div>
      ))}
    </div>
  );
}

export function PreMarketPage() {
  const [snapshot, setSnapshot] = useState<IntradayPreMarketSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await getIntradayPreMarket(refresh));
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
      <ModeHeader mode={snapshot?.mode ?? null} modeOverride="1A" />
      <div className="intraday-page-toolbar">
        <div>
          <strong>Pre-market</strong>
          <span>{snapshot?.market_date ?? "today"}</span>
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

      <div className="intraday-mode-grid">
        <section className="intraday-mode-panel">
          <h3>Global cues</h3>
          <CueTable rows={snapshot?.global_cues ?? []} />
        </section>
        <section className="intraday-mode-panel">
          <h3>ADRs</h3>
          <CueTable rows={snapshot?.adrs ?? []} />
        </section>
        <section className="intraday-mode-panel">
          <h3>FX and commodities</h3>
          <CueTable rows={snapshot?.fx_commodities ?? []} />
        </section>
        <section className="intraday-mode-panel">
          <h3>Watchlist seed</h3>
          <div className="intraday-stack">
            {(snapshot?.watchlist ?? []).map((item) => (
              <div className="intraday-summary-row" key={item.symbol}>
                <strong>{item.symbol}</strong>
                <span>{item.bias}</span>
                <span>{item.probability === null ? "-" : formatPct(item.probability)}</span>
                <em>{item.reason}</em>
              </div>
            ))}
            {snapshot && snapshot.watchlist.length === 0 && (
              <div className="intraday-empty-state">No watchlist seed yet.</div>
            )}
          </div>
        </section>
      </div>

      {snapshot && snapshot.errors.length > 0 && (
        <div className="panel-status error">{snapshot.errors.slice(0, 3).join(" | ")}</div>
      )}
    </div>
  );
}
