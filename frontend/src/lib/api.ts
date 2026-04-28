import { fetchEventSource } from "@microsoft/fetch-event-source";

export type ToolCallStart = {
  call_id: string | null;
  name: string | null;
  arguments: Record<string, unknown>;
};

export type ToolCallEnd = {
  call_id: string | null;
  name: string | null;
  result: unknown;
  duration_ms: number | null;
};

export type StreamEvent =
  | { kind: "delta"; data: string }
  | { kind: "reasoning_delta"; data: string }
  | { kind: "tool_call_start"; data: ToolCallStart }
  | { kind: "tool_call_end"; data: ToolCallEnd }
  | { kind: "handoff"; data: { to?: string; team?: string; session_id?: string } }
  | { kind: "agent_updated"; data: { name: string } }
  | { kind: "final"; data: { markdown: string; session_id: string } }
  | { kind: "error"; data: string };

export async function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (ev: StreamEvent) => void,
  opts?: { team?: string; signal?: AbortSignal }
) {
  await fetchEventSource("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, team: opts?.team }),
    signal: opts?.signal,
    onmessage(ev) {
      try {
        const parsed = JSON.parse(ev.data);
        onEvent({ kind: ev.event as StreamEvent["kind"], data: parsed } as StreamEvent);
      } catch {
        onEvent({ kind: ev.event as StreamEvent["kind"], data: ev.data } as StreamEvent);
      }
    },
    onerror(err) {
      onEvent({ kind: "error", data: String(err) });
      throw err;
    },
  });
}

export type SessionSummary = {
  id: string;
  created_at: number;
  last_activity: number;
  message_count: number;
  preview: string;
  title: string;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  payload: Record<string, unknown>;
  created_at: number;
};

export async function listSessions(limit = 200): Promise<SessionSummary[]> {
  const r = await fetch(`/sessions?limit=${limit}`);
  if (!r.ok) return [];
  return r.json();
}

export async function searchSessions(q: string, limit = 50) {
  const r = await fetch(`/sessions/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  if (!r.ok) return [];
  return r.json() as Promise<
    { session_id: string; snippet: string; at: number; role: string }[]
  >;
}

export async function deleteSession(id: string): Promise<boolean> {
  const r = await fetch(`/sessions/${id}`, { method: "DELETE" });
  return r.ok;
}

export async function getSessionMessages(id: string): Promise<StoredMessage[]> {
  const r = await fetch(`/sessions/${id}/messages`);
  if (!r.ok) return [];
  return r.json();
}

export type RunSummary = {
  symbol?: string | null;
  strategy?: string | null;
  period?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  sharpe?: number | null;
  max_drawdown?: number | null;
};

export type RunRow = {
  id: string;
  kind: string;
  status: string;
  session_id: string;
  created_at: number;
  summary?: RunSummary;
};

export async function listRuns(): Promise<RunRow[]> {
  const r = await fetch("/runs");
  if (!r.ok) return [];
  return r.json();
}

export type EquityPoint = { date: string; equity: number };
export type TradeRecord = {
  entry_date: string;
  exit_date: string;
  side: "long" | "short";
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  cost: number;
  return_pct: number;
};
export type CostBreakdown = {
  brokerage: number;
  stt: number;
  stamp: number;
  exch: number;
  sebi: number;
  gst: number;
  total: number;
};
export type BacktestRunBlob = {
  run_id: string;
  symbol: string;
  strategy: string;
  period: string;
  interval: string;
  initial_capital: number;
  intraday: boolean;
  as_of_utc: string;
  source: string;
  start_date: string;
  end_date: string;
  metrics: Record<string, number>;
  costs: CostBreakdown;
  turnover: number;
  trades: TradeRecord[];
  equity_curve: EquityPoint[];
  artifact_path: string | null;
};

export async function getRun(
  id: string
): Promise<{ id: string; blob: BacktestRunBlob } | null> {
  const r = await fetch(`/runs/${id}`);
  if (!r.ok) return null;
  return r.json();
}

export type BenchmarkPoint = { date: string; value: number; normalized: number };
export async function getBenchmark(
  runId: string,
  benchmark = "^NSEI"
): Promise<{ benchmark: string; points: BenchmarkPoint[] } | null> {
  const r = await fetch(`/runs/${runId}/benchmark?benchmark=${encodeURIComponent(benchmark)}`);
  if (r.status === 204 || !r.ok) return null;
  return r.json();
}

export type HeatmapCell = {
  symbol: string;
  name: string;
  last: number | null;
  change_pct: number | null;
  as_of_utc: string;
  source: string;
};
export type HeatmapSnapshot = {
  nifty50: HeatmapCell[];
  banknifty: HeatmapCell[];
  sectors: HeatmapCell[];
  as_of_utc: string;
  source: string;
};
export async function getHeatmap(): Promise<HeatmapSnapshot | null> {
  const r = await fetch("/indices/heatmap");
  if (!r.ok) return null;
  return r.json();
}

// ---------- Strategy dashboard ----------

export type NseSymbolRow = {
  symbol: string;
  yahoo_symbol: string;
  name: string;
  series: string;
  isin: string;
  listed_on: string;
};

export async function searchSymbols(q: string, limit = 25): Promise<NseSymbolRow[]> {
  const url = `/strategy/symbols?q=${encodeURIComponent(q)}&limit=${limit}`;
  const r = await fetch(url);
  if (!r.ok) return [];
  return r.json();
}

export type Quote = {
  symbol: string;
  last_price: number;
  prev_close: number;
  change_pct: number;
  day_high: number;
  day_low: number;
  volume: number;
  as_of: string;
  source: string;
};

export async function getQuote(symbol: string): Promise<Quote | null> {
  const r = await fetch(`/strategy/quote/${encodeURIComponent(symbol)}`);
  if (!r.ok) return null;
  return r.json();
}

export type StrategyCategory = "trend" | "mean_reversion" | "breakout" | "momentum";

export type StrategyEntry = {
  name: string;
  category: StrategyCategory;
  label: string;
  description: string;
  default_params: Record<string, number>;
};

export async function listStrategies(): Promise<StrategyEntry[]> {
  const r = await fetch("/strategy/list");
  if (!r.ok) return [];
  return r.json();
}

export type EngineSummary = {
  headline: string;
  direction: string;
  verdict: "BUY" | "SELL" | "WAIT";
  confidence: "low" | "medium" | "high";
  performance: string;
  beginner_takeaway: string;
  last_close: number;
};

export type StrategyRunResponse = {
  run: BacktestRunBlob;
  current_signal: "LONG" | "FLAT" | "SHORT";
  signal_age_bars: number;
  last_close: number;
  engine_summary: EngineSummary;
};

export type PerStrategyResult = {
  name: string;
  label: string;
  category: StrategyCategory;
  current_signal: "LONG" | "FLAT" | "SHORT";
  signal_age_bars: number;
  sharpe: number | null;
  max_drawdown: number | null;
  annualized_return: number | null;
  trades: number;
  engine_summary?: EngineSummary;
  error?: string;
};

export type AggregateResult = {
  verdict: "MOSTLY_BULLISH" | "MOSTLY_BEARISH" | "MIXED" | "NO_DATA";
  confidence: "low" | "medium" | "high";
  long_count: number;
  short_count: number;
  flat_count: number;
  total: number;
  plain: string;
  beginner_takeaway: string;
  top_by_sharpe: { name: string; label: string; sharpe: number;
                   current_signal: "LONG" | "FLAT" | "SHORT" }[];
};

export type StrategyRunAllResponse = {
  symbol: string;
  period: string;
  last_close: number;
  per_strategy: PerStrategyResult[];
  aggregate: AggregateResult;
};

export async function runAllStrategies(args: {
  symbol: string;
  period?: string;
  interval?: string;
  capital?: number;
}): Promise<StrategyRunAllResponse> {
  const r = await fetch("/strategy/run_all", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`/strategy/run_all failed (${r.status}): ${text}`);
  }
  return r.json();
}

export async function runStrategy(args: {
  symbol: string;
  strategy: string;
  params?: Record<string, number>;
  period?: string;
  interval?: string;
  capital?: number;
  session_id?: string | null;
}): Promise<StrategyRunResponse> {
  const r = await fetch("/strategy/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`/strategy/run failed (${r.status}): ${text}`);
  }
  return r.json();
}

// ---------- Market scan ----------

export type UniverseOption = {
  id: string;
  label: string;
  size: number;
  eta_minutes: number;
  description: string;
};

export type ScanCompanyAggregate = {
  verdict: "MOSTLY_BULLISH" | "MOSTLY_BEARISH" | "MIXED" | "NO_DATA";
  confidence: "low" | "medium" | "high";
  long_count: number;
  short_count: number;
  flat_count: number;
  total: number;
  beginner_takeaway: string;
  top_by_sharpe: { name: string; label: string; sharpe: number;
                   current_signal: "LONG" | "FLAT" | "SHORT" }[];
};

export type ScanCompanyRow = {
  symbol: string;
  name?: string;
  last_close: number;
  aggregate: ScanCompanyAggregate;
};

export type ScanSummary = {
  total_companies: number;
  total_bullish: number;
  total_bearish: number;
  total_mixed: number;
  pct_bullish: number;
  pct_bearish: number;
  market_mood: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  beginner_takeaway: string;
  top_bullish: { symbol: string; name?: string; score: number;
                 last_close?: number; long_count: number; short_count: number }[];
  top_bearish: { symbol: string; name?: string; score: number;
                 last_close?: number; long_count: number; short_count: number }[];
};

export type ScanState = {
  scan_id: string;
  started_at: string;
  completed_at: string | null;
  universe_name: string;
  universe_size: number;
  done: number;
  last_symbol: string | null;
  period: string;
  interval: string;
  status: "running" | "completed" | "cancelled" | "failed";
  results: ScanCompanyRow[];
  errors: { symbol: string; name?: string; error: string }[];
  summary: ScanSummary | null;
};

export async function listUniverses(): Promise<UniverseOption[]> {
  const r = await fetch("/strategy/universes");
  return r.ok ? r.json() : [];
}

export async function startScan(args: {
  universe: string; period?: string; interval?: string;
}): Promise<{ scan_id: string; universe_size: number; universe: string; started_at: string }> {
  const r = await fetch("/strategy/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) throw new Error(`/strategy/scan failed (${r.status}): ${await r.text()}`);
  return r.json();
}

export async function getScan(scanId: string): Promise<ScanState | null> {
  const r = await fetch(`/strategy/scan/${scanId}`);
  return r.ok ? r.json() : null;
}

export async function listScans(): Promise<Array<{
  scan_id: string; started_at: string; completed_at: string | null;
  status: string; universe_name: string; universe_size: number; done: number;
  summary: ScanSummary | null;
}>> {
  const r = await fetch("/strategy/scan");
  return r.ok ? r.json() : [];
}

export async function cancelScan(scanId: string): Promise<boolean> {
  const r = await fetch(`/strategy/scan/${scanId}/cancel`, { method: "POST" });
  return r.ok;
}

export function exportTradesUrl(runId: string): string {
  return `/runs/${runId}/trades.csv`;
}
export function exportMetricsUrl(runId: string): string {
  return `/runs/${runId}/metrics.json`;
}
