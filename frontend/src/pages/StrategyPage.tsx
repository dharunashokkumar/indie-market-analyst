import { useEffect, useMemo, useRef, useState } from "react";
import { Sparkles, X } from "lucide-react";
import {
  getQuote,
  listStrategies,
  runAllStrategies,
  runStrategy,
  searchSymbols,
  streamChat,
  type AggregateResult,
  type EngineSummary,
  type NseSymbolRow,
  type PerStrategyResult,
  type Quote,
  type StrategyCategory,
  type StrategyEntry,
  type StrategyRunResponse,
} from "../lib/api";
import { CompanyLogo } from "../components/CompanyLogo";
import { MarketScanPanel } from "../components/MarketScanPanel";
import {
  CostBreakdownCard,
  MetricsBox,
  TradeLog,
  formatNum,
  formatPct,
} from "./Dashboards/_runDetail";

const CATEGORY_ORDER: StrategyCategory[] = [
  "trend", "mean_reversion", "breakout", "momentum",
];
const CATEGORY_LABEL: Record<StrategyCategory, string> = {
  trend: "Trend",
  mean_reversion: "Mean Reversion",
  breakout: "Breakout",
  momentum: "Momentum",
};

function SignalPill({ signal, age }: { signal: "LONG" | "FLAT" | "SHORT"; age: number }) {
  return (
    <div className={`signal-pill signal-${signal.toLowerCase()}`}>
      <span className="signal-label">{signal}</span>
      <span className="signal-age">{age} bar{age === 1 ? "" : "s"}</span>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: "BUY" | "SELL" | "WAIT" }) {
  const cls = verdict === "BUY" ? "verdict-buy"
    : verdict === "SELL" ? "verdict-sell" : "verdict-wait";
  return <span className={`verdict-badge ${cls}`}>{verdict}</span>;
}

function ConfidenceBar({ confidence }: { confidence: "low" | "medium" | "high" }) {
  const w = confidence === "high" ? 100 : confidence === "medium" ? 60 : 25;
  return (
    <div className="confidence-bar" title={`${confidence} confidence`}>
      <div className={`confidence-fill confidence-${confidence}`} style={{ width: `${w}%` }} />
      <span className="confidence-label">{confidence}</span>
    </div>
  );
}

function EngineSummaryCard({ summary }: { summary: EngineSummary }) {
  return (
    <div className="engine-summary">
      <div className="engine-summary-head">
        <VerdictBadge verdict={summary.verdict} />
        <ConfidenceBar confidence={summary.confidence} />
      </div>
      <div className="engine-summary-headline">{summary.headline}</div>
      <div className="engine-summary-takeaway">{summary.beginner_takeaway}</div>
      <div className="engine-summary-perf">{summary.performance}</div>
    </div>
  );
}

function CompanyCard({ symbol, quote }: { symbol: NseSymbolRow; quote: Quote | null }) {
  return (
    <div className="company-card">
      <div className="company-card-head">
        <div className="company-card-id">
          <CompanyLogo symbol={symbol.symbol} name={symbol.name} size={42} />
          <div>
            <div className="company-symbol">{symbol.symbol}</div>
            <div className="company-name">{symbol.name}</div>
          </div>
        </div>
        {quote && (
          <div className={`company-price ${quote.change_pct >= 0 ? "pos" : "neg"}`}>
            <div className="price-last">₹{formatNum(quote.last_price)}</div>
            <div className="price-change">{formatPct(quote.change_pct)}</div>
          </div>
        )}
      </div>
      {quote && (
        <div className="company-stats">
          <div><label>High</label><span>₹{formatNum(quote.day_high)}</span></div>
          <div><label>Low</label><span>₹{formatNum(quote.day_low)}</span></div>
          <div><label>Vol</label><span>{Math.round(quote.volume).toLocaleString("en-IN")}</span></div>
          <div><label>As of</label><span>{quote.as_of}</span></div>
        </div>
      )}
    </div>
  );
}

function EquitySparkline({ blob }: { blob: StrategyRunResponse["run"] }) {
  const points = blob.equity_curve;
  if (points.length < 2) return null;
  const w = 600, h = 120, pad = 6;
  const xs = points.map((_, i) => pad + (i / (points.length - 1)) * (w - 2 * pad));
  const ys_raw = points.map((p) => p.equity);
  const min = Math.min(...ys_raw), max = Math.max(...ys_raw);
  const span = max - min || 1;
  const ys = ys_raw.map((v) => h - pad - ((v - min) / span) * (h - 2 * pad));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const last = ys_raw[ys_raw.length - 1];
  const start = ys_raw[0];
  const colour = last >= start ? "var(--success)" : "var(--danger)";
  return (
    <svg className="equity-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path d={path} fill="none" stroke={colour} strokeWidth={1.5} />
    </svg>
  );
}

function AggregatePanel({ result }: { result: { aggregate: AggregateResult; per_strategy: PerStrategyResult[] } }) {
  const { aggregate, per_strategy } = result;
  const verdictClass = aggregate.verdict === "MOSTLY_BULLISH" ? "verdict-buy"
    : aggregate.verdict === "MOSTLY_BEARISH" ? "verdict-sell"
    : "verdict-wait";
  return (
    <div className="aggregate-panel">
      <div className="aggregate-head">
        <span className={`verdict-badge ${verdictClass}`}>
          {aggregate.verdict.replace("_", " ")}
        </span>
        <ConfidenceBar confidence={aggregate.confidence} />
      </div>
      <div className="aggregate-counts">
        <div><strong>{aggregate.long_count}</strong> BUY</div>
        <div><strong>{aggregate.short_count}</strong> SELL</div>
        <div><strong>{aggregate.flat_count}</strong> WAIT</div>
        <div className="muted">of {aggregate.total} strategies</div>
      </div>
      <div className="aggregate-takeaway">{aggregate.beginner_takeaway}</div>

      <table className="aggregate-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Signal</th>
            <th className="num">Sharpe</th>
            <th className="num">Max DD</th>
            <th className="num">Trades</th>
          </tr>
        </thead>
        <tbody>
          {per_strategy.map((r) => (
            <tr key={r.name} className={r.error ? "row-err" : ""}>
              <td>{r.label}</td>
              <td>
                {r.error
                  ? <span className="muted">err</span>
                  : <SignalPill signal={r.current_signal} age={r.signal_age_bars} />}
              </td>
              <td className="num">{formatNum(r.sharpe)}</td>
              <td className="num">{formatPct(r.max_drawdown)}</td>
              <td className="num">{r.trades}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AiInsightsDrawer({
  open, onClose, runResult, symbol, strategy,
}: {
  open: boolean;
  onClose: () => void;
  runResult: StrategyRunResponse | null;
  symbol: string | null;
  strategy: string | null;
}) {
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastKey = useRef<string | null>(null);

  useEffect(() => {
    if (!open || !runResult || !symbol || !strategy) return;
    const key = `${runResult.run.run_id}:${strategy}`;
    if (lastKey.current === key && text) return;
    lastKey.current = key;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setText("");
    setErr(null);
    setStreaming(true);
    const prompt = `Explain run ${runResult.run.run_id} for ${symbol} using the ${strategy} strategy. Current signal is ${runResult.current_signal} (${runResult.signal_age_bars} bars). Sharpe ${runResult.run.metrics.sharpe?.toFixed(2)}, Max DD ${(runResult.run.metrics.max_drawdown * 100).toFixed(1)}%.`;

    streamChat(prompt, null, (ev) => {
      if (ev.kind === "delta") setText((t) => t + (ev.data as string));
      else if (ev.kind === "final") {
        const md = (ev.data as { markdown?: string }).markdown;
        if (md) setText(md);
        setStreaming(false);
      } else if (ev.kind === "error") {
        setErr(String(ev.data));
        setStreaming(false);
      }
    }, { team: "strategy_explainer", signal: ctrl.signal })
      .catch((e) => { if (!ctrl.signal.aborted) setErr(String(e)); })
      .finally(() => setStreaming(false));

    return () => ctrl.abort();
  }, [open, runResult, symbol, strategy, text]);

  if (!open) return null;
  return (
    <div className="ai-drawer-backdrop" onClick={onClose}>
      <aside className="ai-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="ai-drawer-head">
          <div className="ai-drawer-title">
            <Sparkles size={14} /> AI Insights
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {!runResult && <div className="panel-status">Run a strategy first to get AI commentary.</div>}
        {runResult && streaming && !text && <div className="panel-status">Thinking…</div>}
        {err && <div className="panel-status err">{err}</div>}
        {text && <div className="ai-drawer-body">{text}</div>}
      </aside>
    </div>
  );
}

export function StrategyPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NseSymbolRow[]>([]);
  const [selected, setSelected] = useState<NseSymbolRow | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [strategies, setStrategies] = useState<StrategyEntry[]>([]);
  const [activeStrategy, setActiveStrategy] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<StrategyRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [period, setPeriod] = useState("2y");
  const [barInterval, setBarInterval] = useState("1d");
  const [capital, setCapital] = useState(100000);

  const [aggregateResult, setAggregateResult] = useState<{
    aggregate: AggregateResult; per_strategy: PerStrategyResult[];
  } | null>(null);
  const [runningAll, setRunningAll] = useState(false);

  const [aiOpen, setAiOpen] = useState(false);

  useEffect(() => { listStrategies().then(setStrategies); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      searchSymbols(query, 50).then(setResults);
    }, 180);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!selected) { setQuote(null); return; }
    setQuote(null);
    getQuote(selected.yahoo_symbol).then(setQuote).catch(() => setQuote(null));
    setRunResult(null);
    setActiveStrategy(null);
    setAggregateResult(null);
    setAiOpen(false);
  }, [selected]);

  const grouped = useMemo(() => {
    const out: Record<StrategyCategory, StrategyEntry[]> = {
      trend: [], mean_reversion: [], breakout: [], momentum: [],
    };
    strategies.forEach((s) => out[s.category].push(s));
    return out;
  }, [strategies]);

  const handleRun = async (strat: StrategyEntry) => {
    if (!selected) return;
    setRunning(true);
    setActiveStrategy(strat.name);
    setRunError(null);
    setAggregateResult(null);
    try {
      const res = await runStrategy({
        symbol: selected.yahoo_symbol,
        strategy: strat.name,
        period, interval: barInterval, capital,
      });
      setRunResult(res);
    } catch (e) {
      setRunError(String(e));
      setRunResult(null);
    } finally {
      setRunning(false);
    }
  };

  const handleRunAll = async () => {
    if (!selected) return;
    setRunningAll(true);
    setRunError(null);
    setRunResult(null);
    setActiveStrategy(null);
    try {
      const res = await runAllStrategies({
        symbol: selected.yahoo_symbol,
        period, interval: barInterval, capital,
      });
      setAggregateResult({ aggregate: res.aggregate, per_strategy: res.per_strategy });
    } catch (e) {
      setRunError(String(e));
    } finally {
      setRunningAll(false);
    }
  };

  return (
    <div className="strategy-page">
      <div className="strategy-search-col">
        <input
          type="text"
          className="strategy-search"
          placeholder="Search NSE companies…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="strategy-symbol-list">
          {results.map((row) => (
            <button
              key={row.symbol}
              type="button"
              className={`strategy-symbol-row ${selected?.symbol === row.symbol ? "active" : ""}`}
              onClick={() => setSelected(row)}
            >
              <CompanyLogo symbol={row.symbol} name={row.name} size={28} />
              <div className="strategy-symbol-text">
                <span className="sym">{row.symbol}</span>
                <span className="nm">{row.name}</span>
              </div>
            </button>
          ))}
          {results.length === 0 && <div className="panel-status">No matches.</div>}
        </div>
      </div>

      <div className="strategy-main-col">
        <MarketScanPanel />

        {!selected && (
          <div className="panel-empty"><p>Or pick a company on the left to run individual strategies.</p></div>
        )}
        {selected && (
          <>
            <CompanyCard symbol={selected} quote={quote} />

            <div className="strategy-actions">
              <button
                type="button"
                className="run-all-btn"
                onClick={handleRunAll}
                disabled={runningAll || running}
              >
                {runningAll ? "Running all…" : "▶ Run all 12 strategies"}
              </button>
              <button
                type="button"
                className="ai-toggle-btn"
                onClick={() => setAiOpen(true)}
                disabled={!runResult}
                title={runResult ? "Open AI commentary" : "Run a single strategy first"}
              >
                <Sparkles size={14} /> AI Insights
              </button>
            </div>

            <div className="strategy-grid">
              {CATEGORY_ORDER.map((cat) => (
                <div key={cat} className="strategy-cat">
                  <div className="strategy-cat-label">{CATEGORY_LABEL[cat]}</div>
                  <div className="strategy-cat-buttons">
                    {grouped[cat].map((s) => (
                      <button
                        key={s.name}
                        type="button"
                        className={`strategy-btn ${activeStrategy === s.name ? "active" : ""}`}
                        onClick={() => handleRun(s)}
                        disabled={running || runningAll}
                        title={s.description}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <details
              className="strategy-advanced"
              open={showAdvanced}
              onToggle={(e) => setShowAdvanced((e.target as HTMLDetailsElement).open)}
            >
              <summary>Advanced controls</summary>
              <div className="strategy-advanced-row">
                <label>
                  Period
                  <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                    <option value="6mo">6 months</option>
                    <option value="1y">1 year</option>
                    <option value="2y">2 years</option>
                    <option value="5y">5 years</option>
                  </select>
                </label>
                <label>
                  Interval
                  <select value={barInterval} onChange={(e) => setBarInterval(e.target.value)}>
                    <option value="1d">Daily</option>
                    <option value="1wk">Weekly</option>
                  </select>
                </label>
                <label>
                  Capital (₹)
                  <input
                    type="number" min={1000} step={1000}
                    value={capital}
                    onChange={(e) => setCapital(Number(e.target.value) || 100000)}
                  />
                </label>
              </div>
            </details>

            {(running || runningAll) && (
              <div className="panel-status">
                {runningAll ? "Running all 12 strategies…" : "Running backtest…"}
              </div>
            )}
            {runError && <div className="panel-status err">{runError}</div>}

            {aggregateResult && !runningAll && (
              <AggregatePanel result={aggregateResult} />
            )}

            {runResult && !running && !aggregateResult && (
              <div className="strategy-result">
                <EngineSummaryCard summary={runResult.engine_summary} />

                <div className="strategy-result-header">
                  <SignalPill signal={runResult.current_signal} age={runResult.signal_age_bars} />
                  <div className="strategy-result-meta">
                    <strong>{runResult.run.strategy}</strong> on {runResult.run.symbol} •{" "}
                    {runResult.run.start_date} → {runResult.run.end_date}
                  </div>
                </div>
                <EquitySparkline blob={runResult.run} />
                <div className="detail-grid">
                  <CostBreakdownCard blob={runResult.run} />
                  <MetricsBox blob={runResult.run} />
                </div>
                <TradeLog trades={runResult.run.trades} />
              </div>
            )}
          </>
        )}
      </div>

      <AiInsightsDrawer
        open={aiOpen}
        onClose={() => setAiOpen(false)}
        runResult={runResult}
        symbol={selected?.yahoo_symbol ?? null}
        strategy={activeStrategy}
      />
    </div>
  );
}
