import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertCircle, Square } from "lucide-react";
import {
  cancelScan,
  getScan,
  listUniverses,
  startScan,
  type ScanCompanyRow,
  type ScanState,
  type UniverseOption,
} from "../lib/api";
import { CompanyLogo } from "./CompanyLogo";

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toFixed(0)}%`;
}
function fmtINR(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `₹${v.toFixed(2)}`;
}
function verdictClass(v: string): string {
  if (v === "MOSTLY_BULLISH") return "verdict-buy";
  if (v === "MOSTLY_BEARISH") return "verdict-sell";
  return "verdict-wait";
}
function moodClass(mood: string): string {
  if (mood === "BULLISH") return "mood-bull";
  if (mood === "BEARISH") return "mood-bear";
  return "mood-neutral";
}

type SortKey = "score" | "long" | "short" | "symbol" | "last_close";

function ResultsTable({ rows }: { rows: ScanCompanyRow[] }) {
  const [filter, setFilter] = useState("");
  const [verdictFilter, setVerdictFilter] = useState<"ALL" | "MOSTLY_BULLISH" | "MOSTLY_BEARISH" | "MIXED">("ALL");
  const [sort, setSort] = useState<SortKey>("score");

  const filtered = useMemo(() => {
    let out = rows;
    if (verdictFilter !== "ALL") out = out.filter((r) => r.aggregate.verdict === verdictFilter);
    if (filter) {
      const q = filter.toLowerCase();
      out = out.filter((r) =>
        r.symbol.toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q),
      );
    }
    const sorted = [...out];
    sorted.sort((a, b) => {
      const sa = scoreOf(a, sort), sb = scoreOf(b, sort);
      if (sort === "symbol") return String(sa).localeCompare(String(sb));
      return (Number(sb) || 0) - (Number(sa) || 0);
    });
    return sorted;
  }, [rows, filter, verdictFilter, sort]);

  return (
    <div className="scan-table-wrap">
      <div className="scan-table-controls">
        <input
          type="text"
          placeholder="Filter by symbol or name…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <select value={verdictFilter} onChange={(e) => setVerdictFilter(e.target.value as never)}>
          <option value="ALL">All verdicts</option>
          <option value="MOSTLY_BULLISH">Bullish only</option>
          <option value="MOSTLY_BEARISH">Bearish only</option>
          <option value="MIXED">Mixed only</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          <option value="score">Sort: Net BUY-SELL</option>
          <option value="long">Sort: Most BUY signals</option>
          <option value="short">Sort: Most SELL signals</option>
          <option value="last_close">Sort: Price</option>
          <option value="symbol">Sort: Symbol (A-Z)</option>
        </select>
        <span className="muted">{filtered.length} of {rows.length}</span>
      </div>
      <table className="scan-table">
        <thead>
          <tr>
            <th></th>
            <th>Symbol</th>
            <th>Name</th>
            <th>Verdict</th>
            <th className="num">BUY</th>
            <th className="num">SELL</th>
            <th className="num">WAIT</th>
            <th className="num">Last</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((r) => (
            <tr key={r.symbol}>
              <td><CompanyLogo symbol={r.symbol} name={r.name} exchange="NSE" size={20} /></td>
              <td className="mono">{r.symbol}</td>
              <td className="ellipsis">{r.name}</td>
              <td>
                <span className={`verdict-badge ${verdictClass(r.aggregate.verdict)}`}>
                  {shortVerdict(r.aggregate.verdict)}
                </span>
              </td>
              <td className="num pos">{r.aggregate.long_count}</td>
              <td className="num neg">{r.aggregate.short_count}</td>
              <td className="num">{r.aggregate.flat_count}</td>
              <td className="num">{fmtINR(r.last_close)}</td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr><td colSpan={8} className="muted" style={{ textAlign: "center", padding: 12 }}>No matches.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function scoreOf(r: ScanCompanyRow, key: SortKey): number | string {
  switch (key) {
    case "score": return r.aggregate.long_count - r.aggregate.short_count;
    case "long": return r.aggregate.long_count;
    case "short": return r.aggregate.short_count;
    case "last_close": return r.last_close;
    case "symbol": return r.symbol;
  }
}
function shortVerdict(v: string): string {
  if (v === "MOSTLY_BULLISH") return "BULLISH";
  if (v === "MOSTLY_BEARISH") return "BEARISH";
  if (v === "MIXED") return "MIXED";
  return "—";
}

function MoodHero({ state }: { state: ScanState }) {
  const s = state.summary;
  if (!s) return null;
  return (
    <div className={`mood-hero ${moodClass(s.market_mood)}`}>
      <div className="mood-label">Market mood</div>
      <div className="mood-value">{s.market_mood}</div>
      <div className="mood-takeaway">{s.beginner_takeaway}</div>
      <div className="mood-counts">
        <div className="mood-count pos">
          <strong>{s.total_bullish}</strong>
          <span>going UP</span>
        </div>
        <div className="mood-count neg">
          <strong>{s.total_bearish}</strong>
          <span>going DOWN</span>
        </div>
        <div className="mood-count">
          <strong>{s.total_mixed}</strong>
          <span>UNCERTAIN</span>
        </div>
      </div>
      <div className="mood-bar" aria-label="bullish vs bearish percentage">
        <div className="mood-bar-bull" style={{ width: `${s.pct_bullish}%` }} />
        <div className="mood-bar-bear" style={{ width: `${s.pct_bearish}%` }} />
      </div>
      <div className="mood-bar-legend">
        <span className="pos">{s.pct_bullish.toFixed(0)}% bullish</span>
        <span className="neg">{s.pct_bearish.toFixed(0)}% bearish</span>
      </div>
    </div>
  );
}

function TopList({ title, rows, kind }: {
  title: string;
  rows: { symbol: string; name?: string; score: number; last_close?: number;
          long_count: number; short_count: number }[];
  kind: "bull" | "bear";
}) {
  if (rows.length === 0) {
    return (
      <div className="top-list">
        <div className="top-list-title">{title}</div>
        <div className="muted" style={{ padding: 8 }}>None this scan.</div>
      </div>
    );
  }
  return (
    <div className="top-list">
      <div className="top-list-title">{title}</div>
      <ol>
        {rows.map((r) => (
          <li key={r.symbol}>
            <CompanyLogo symbol={r.symbol} name={r.name} exchange="NSE" size={22} />
            <div className="top-list-meta">
              <span className="mono">{r.symbol}</span>
              <span className="muted ellipsis">{r.name}</span>
            </div>
            <div className={kind === "bull" ? "score pos" : "score neg"}>
              {kind === "bull" ? "+" : ""}{r.score}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function MarketScanPanel() {
  const [universes, setUniverses] = useState<UniverseOption[]>([]);
  const [universe, setUniverse] = useState<string>("nifty50");
  const [period, setPeriod] = useState<string>("1y");
  const [scanState, setScanState] = useState<ScanState | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    listUniverses().then(setUniverses);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPolling = (scanId: string) => {
    stopPoll();
    const tick = async () => {
      const s = await getScan(scanId);
      if (!s) return;
      setScanState(s);
      if (s.status !== "running") stopPoll();
    };
    void tick();
    pollRef.current = window.setInterval(tick, 2000);
  };

  const handleStart = async () => {
    setErr(null);
    setBusy(true);
    setScanState(null);
    try {
      const { scan_id } = await startScan({ universe, period });
      startPolling(scan_id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    if (!scanState) return;
    await cancelScan(scanState.scan_id);
  };

  const universeMeta = universes.find((u) => u.id === universe);
  const progressPct = scanState
    ? Math.round((scanState.done / Math.max(scanState.universe_size, 1)) * 100)
    : 0;

  return (
    <section className="market-scan">
      <div className="market-scan-header">
        <div>
          <h3><Activity size={16} /> Scan the whole market</h3>
          <p className="muted">
            Run all 12 strategies on every company in the chosen universe, then see one big
            verdict: which stocks are likely to go UP, DOWN, or stay UNDECIDED.
          </p>
        </div>
        <div className="market-scan-controls">
          <select
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            disabled={scanState?.status === "running"}
          >
            {universes.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label} — {u.size} stocks (~{u.eta_minutes} min)
              </option>
            ))}
          </select>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            disabled={scanState?.status === "running"}
          >
            <option value="6mo">6 months</option>
            <option value="1y">1 year</option>
            <option value="2y">2 years</option>
          </select>
          {scanState?.status === "running" ? (
            <button type="button" className="run-all-btn" onClick={handleCancel}>
              <Square size={14} /> Stop
            </button>
          ) : (
            <button
              type="button"
              className="run-all-btn"
              onClick={handleStart}
              disabled={busy}
            >
              {busy ? "Starting…" : "🔥 Scan now"}
            </button>
          )}
        </div>
      </div>

      {universeMeta && !scanState && (
        <div className="scan-warning">
          <AlertCircle size={14} />
          <span>
            <strong>{universeMeta.label}</strong> — {universeMeta.description} Estimated time:{" "}
            <strong>~{universeMeta.eta_minutes} min</strong>. The scan runs in the background;
            you can keep using other parts of the app.
          </span>
        </div>
      )}

      {err && <div className="panel-status err">{err}</div>}

      {scanState && (
        <div className="scan-progress-block">
          <div className="scan-progress-meta">
            <strong>
              {scanState.status === "running" ? "Scanning" : scanState.status === "completed" ? "Done" : "Stopped"}
            </strong>
            <span className="muted">
              {scanState.done}/{scanState.universe_size} stocks
              {scanState.last_symbol && scanState.status === "running" && (
                <> • last: <span className="mono">{scanState.last_symbol}</span></>
              )}
            </span>
            <span className="muted" style={{ marginLeft: "auto" }}>
              ID: <span className="mono">{scanState.scan_id}</span>
            </span>
          </div>
          <div className="scan-progress-bar">
            <div className="scan-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      )}

      {scanState && scanState.summary && (
        <div className="scan-results">
          <MoodHero state={scanState} />
          <div className="scan-toplists">
            <TopList title="Top 10 likely to go UP" rows={scanState.summary.top_bullish} kind="bull" />
            <TopList title="Top 10 likely to go DOWN" rows={scanState.summary.top_bearish} kind="bear" />
          </div>
          <ResultsTable rows={scanState.results} />
          {scanState.errors.length > 0 && (
            <details className="scan-errors">
              <summary>{scanState.errors.length} stocks failed (click to expand)</summary>
              <ul>
                {scanState.errors.slice(0, 50).map((e) => (
                  <li key={e.symbol}><span className="mono">{e.symbol}</span> — {e.error}</li>
                ))}
              </ul>
            </details>
          )}
          <div className="muted" style={{ fontSize: 11 }}>
            Saved to <span className="mono">data/scans/scan_{scanState.scan_id}.json</span>
          </div>
        </div>
      )}
    </section>
  );
}
