import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { CompanyLogo } from "../../components/CompanyLogo";
import { getHeatmap, type HeatmapCell, type HeatmapSnapshot } from "../../lib/api";

function cellColor(change: number | null | undefined): string {
  if (change === null || change === undefined || !Number.isFinite(change)) {
    return "var(--surface-2)";
  }
  const clamped = Math.max(-3, Math.min(3, change));
  const intensity = Math.min(Math.abs(clamped) / 3, 1);
  const alpha = 0.15 + intensity * 0.55;
  const color = clamped >= 0
    ? `rgba(34, 139, 68, ${alpha.toFixed(2)})`   // green
    : `rgba(185, 28, 28, ${alpha.toFixed(2)})`;  // red
  return color;
}

function formatChange(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function cleanSymbol(symbol: string): string {
  return symbol.replace(/\.NS$/i, "").replace(/\.BO$/i, "").replace(/^\^/, "");
}

function HeatmapIdentity({ cell }: { cell: HeatmapCell }) {
  const isIndex = cell.symbol.startsWith("^");
  const symbol = cleanSymbol(cell.symbol);
  return (
    <div className="heatmap-identity">
      {!isIndex && (
        <CompanyLogo
          symbol={cell.symbol}
          name={cell.name}
          exchange={cell.symbol.endsWith(".BO") ? "BSE" : "NSE"}
          size={22}
        />
      )}
      <div className="heatmap-copy">
        <div className="heatmap-name">{cell.name}</div>
        <div className="heatmap-symbol">{symbol}</div>
      </div>
    </div>
  );
}

function Grid({ title, cells }: { title: string; cells: HeatmapCell[] }) {
  if (!cells.length) return null;
  return (
    <section className="heatmap-section">
      <h3>{title}</h3>
      <div className="heatmap-grid">
        {cells.map((c) => (
          <div
            key={c.symbol}
            className="heatmap-cell"
            style={{ background: cellColor(c.change_pct) }}
            title={`${c.name} (${c.symbol})`}
          >
            <HeatmapIdentity cell={c} />
            <div className="heatmap-change">{formatChange(c.change_pct)}</div>
            {c.last !== null && c.last !== undefined && (
              <div className="heatmap-last">{c.last.toFixed(2)}</div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export function HeatmapPanel() {
  const [snap, setSnap] = useState<HeatmapSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const timerRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await getHeatmap();
      if (!s) setError("Failed to load heatmap");
      else setSnap(s);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(() => {
      refresh();
    }, 60_000);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, [autoRefresh, refresh]);

  return (
    <div className="heatmap-panel">
      <div className="panel-toolbar">
        <button
          type="button"
          className="refresh-btn"
          onClick={refresh}
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? "spinning" : ""} />
          Refresh
        </button>
        <label className="toolbar-toggle">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          <span>Auto-refresh (60s)</span>
        </label>
        {snap && (
          <span className="muted heatmap-asof">
            as of {new Date(snap.as_of_utc).toLocaleString()} • source {snap.source}
          </span>
        )}
      </div>

      {error && <div className="panel-status error">{error}</div>}
      {snap && (
        <>
          <Grid title="Nifty 50 constituents" cells={snap.nifty50} />
          <Grid title="Bank Nifty constituents" cells={snap.banknifty} />
          <Grid title="Sectoral indices" cells={snap.sectors} />
        </>
      )}
      {!snap && !error && loading && (
        <div className="panel-status">Loading heatmap…</div>
      )}
    </div>
  );
}
