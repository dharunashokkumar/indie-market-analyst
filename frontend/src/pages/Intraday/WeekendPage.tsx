import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  getIntradayWeekend,
  type IntradayWeekendSnapshot,
} from "../../lib/api";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";

function formatPct(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(2)}%`;
}

export function WeekendPage() {
  const [snapshot, setSnapshot] = useState<IntradayWeekendSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await getIntradayWeekend(refresh));
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
      <ModeHeader mode={snapshot?.mode ?? null} modeOverride="7" />
      <div className="intraday-page-toolbar">
        <div>
          <strong>Weekend planner</strong>
          <span>{snapshot?.week_key ?? "this week"}</span>
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
          <h3>Weekly cues</h3>
          <div className="intraday-simple-table">
            <div className="intraday-simple-head four">
              <span>Name</span>
              <span>Symbol</span>
              <span>Last</span>
              <span>Week</span>
            </div>
            {(snapshot?.global_cues ?? []).map((row) => (
              <div className="intraday-simple-row four" key={row.symbol}>
                <strong>{row.label}</strong>
                <span>{row.symbol}</span>
                <span>{row.last?.toFixed(2) ?? "-"}</span>
                <span>{row.status === "ok" ? formatPct(row.weekly_change_pct) : row.status}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="intraday-mode-panel">
          <h3>Next watchlist</h3>
          <div className="intraday-stack">
            {(snapshot?.watchlist ?? []).map((item) => (
              <div className="intraday-summary-row" key={item.symbol}>
                <strong>{item.symbol}</strong>
                <span>{item.bias}</span>
                <span>{formatPct(item.probability)}</span>
                <em>{item.reason}</em>
              </div>
            ))}
            {snapshot && snapshot.watchlist.length === 0 && (
              <div className="intraday-empty-state">No stored scan picks for next week.</div>
            )}
          </div>
        </section>

        <section className="intraday-mode-panel">
          <h3>Earnings calendar</h3>
          <div className="intraday-stack">
            {(snapshot?.earnings_calendar ?? []).slice(0, 12).map((row, index) => (
              <div className="intraday-summary-row" key={`${index}-${String(row.symbol ?? "")}`}>
                <strong>{String(row.symbol ?? row.companyName ?? row.company ?? "-")}</strong>
                <span>{String(row.purpose ?? row.subject ?? row.event ?? "event")}</span>
                <em>{String(row.date ?? row.exDate ?? row.boardMeetingDate ?? "")}</em>
              </div>
            ))}
            {snapshot && snapshot.earnings_calendar.length === 0 && (
              <div className="intraday-empty-state">No NSE calendar rows available.</div>
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
