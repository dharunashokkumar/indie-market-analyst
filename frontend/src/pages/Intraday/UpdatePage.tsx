import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import {
  getIntradayActivePicks,
  getIntradayPicksToday,
  postIntradayActivePick,
  type IntradayActivePicksResponse,
  type IntradayPick,
  type IntradayScanResult,
  type IntradaySource,
} from "../../lib/api";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";

function formatPct(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number | null) {
  return value === null ? "-" : value.toFixed(value >= 1000 ? 1 : 2);
}

export function UpdatePage() {
  const [source, setSource] = useState<IntradaySource>("yfinance");
  const [active, setActive] = useState<IntradayActivePicksResponse | null>(null);
  const [scans, setScans] = useState<IntradayScanResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const latestPicks = useMemo(() => scans[0]?.picks ?? [], [scans]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [activeRows, scanRows] = await Promise.all([
        getIntradayActivePicks(source),
        getIntradayPicksToday(),
      ]);
      setActive(activeRows);
      setScans(scanRows);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [source]);

  const markActive = async (pick: IntradayPick) => {
    const scanId = scans[0]?.scan_id ?? null;
    setError(null);
    try {
      const rows = await postIntradayActivePick({
        symbol: pick.symbol,
        scan_id: scanId,
        pick,
        source,
      });
      setActive(rows);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="intraday-page">
      <IntradayNav />
      <ModeHeader mode={active?.mode ?? null} modeOverride="6" />
      <div className="intraday-page-toolbar">
        <div>
          <strong>Active picks</strong>
          <span>{active?.active.length ?? 0} tracked</span>
        </div>
        <label className="intraday-inline-select">
          <span>Source</span>
          <select
            value={source}
            onChange={(event) => setSource(event.target.value as IntradaySource)}
          >
            <option value="nse_direct">NSE direct</option>
            <option value="yfinance">yfinance</option>
          </select>
        </label>
        <button
          type="button"
          className="intraday-icon-text-btn"
          onClick={load}
          disabled={loading}
        >
          <RefreshCw size={15} />
          {loading ? "Loading" : "Refresh"}
        </button>
      </div>

      {error && <div className="panel-status error">{error}</div>}

      <section className="intraday-mode-panel">
        <h3>Status</h3>
        <div className="intraday-simple-table">
          <div className="intraday-simple-head active">
            <span>Symbol</span>
            <span>Side</span>
            <span>Scan</span>
            <span>Last</span>
            <span>Move</span>
            <span>Status</span>
          </div>
          {(active?.active ?? []).map((row) => (
            <div className="intraday-simple-row active" key={row.active_id}>
              <strong>{row.symbol}</strong>
              <span>{row.pick.direction}</span>
              <span>{formatPrice(row.pick.ltp)}</span>
              <span>{formatPrice(row.last_ltp)}</span>
              <span>{formatPct(row.move_from_scan_pct)}</span>
              <span className={`outcome-pill ${row.status}`}>{row.status}</span>
            </div>
          ))}
          {active && active.active.length === 0 && (
            <div className="intraday-empty-state">No active picks marked.</div>
          )}
        </div>
      </section>

      <section className="intraday-mode-panel">
        <h3>Latest scan picks</h3>
        <div className="intraday-stack">
          {latestPicks.map((pick) => (
            <div className="intraday-summary-row" key={pick.symbol}>
              <strong>{pick.symbol}</strong>
              <span>{pick.direction}</span>
              <span>{formatPct(pick.probability)}</span>
              <button
                type="button"
                className="intraday-icon-text-btn compact"
                onClick={() => markActive(pick)}
              >
                <Plus size={14} />
                Track
              </button>
            </div>
          ))}
          {!loading && latestPicks.length === 0 && (
            <div className="intraday-empty-state">No latest scan picks found.</div>
          )}
        </div>
      </section>
    </div>
  );
}
