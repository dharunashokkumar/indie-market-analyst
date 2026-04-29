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

export type AssetClassId =
  | "equity"
  | "commodity"
  | "mutual_fund"
  | "global_index"
  | "indian_index"
  | "crypto";

export type NseSymbolRow = {
  symbol: string;
  yahoo_symbol: string;
  name: string;
  series: string;
  isin: string;
  listed_on: string;
  asset_type?: AssetClassId;
  currency?: string;
  exchange?: string;
  source?: string;
};

export type InstrumentGroup = {
  id: AssetClassId;
  label: string;
  description: string;
  source: string;
  count: number;
};

export async function listInstrumentGroups(): Promise<InstrumentGroup[]> {
  const r = await fetch("/strategy/instrument-groups");
  if (!r.ok) return [];
  return r.json();
}

export async function searchSymbols(
  q: string,
  limit = 25,
  assetType: AssetClassId = "equity",
): Promise<NseSymbolRow[]> {
  const url = `/strategy/symbols?q=${encodeURIComponent(q)}&limit=${limit}`
    + `&asset_type=${encodeURIComponent(assetType)}`;
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
  sparkline?: { date: string; value: number }[];
  expiry?: string | null;
  expiry_iso?: string | null;
  unit?: string | null;
  open_interest?: number | null;
  instrument?: string | null;
  contract_symbol?: string | null;
  as_of_estimated?: boolean;
};

export async function getQuote(symbol: string): Promise<Quote | null> {
  const r = await fetch(`/strategy/quote/${encodeURIComponent(symbol)}`);
  if (!r.ok) return null;
  return r.json();
}

export type IcomdexEntry = {
  symbol: string;
  instrument_code: string;
  display_name: string;
  ltp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  percent_change: number;
};

export async function getMcxIcomdex(): Promise<Record<string, IcomdexEntry> | null> {
  const r = await fetch("/strategy/mcx/icomdex");
  if (!r.ok) return null;
  return r.json();
}

export type MarketQuote = {
  symbol: string;
  name: string;
  exchange: string;
  currency: "INR" | "POINTS" | string;
  last_price: number | null;
  prev_close: number | null;
  change_pct: number | null;
  day_high: number | null;
  day_low: number | null;
  volume: number;
  turnover: number;
  as_of: string;
  source: string;
  sparkline: { date: string; value: number }[];
};

export type MarketNewsItem = {
  title: string;
  link: string;
  published_utc: string | null;
  summary: string;
  source: string;
  sentiment: "bull" | "bear" | "neutral" | string;
};

export type MarketNewsDigest = {
  items: MarketNewsItem[];
  total: number;
  bullish: number;
  bearish: number;
  neutral: number;
  overall_sentiment: "bullish" | "bearish" | "mixed" | "neutral" | string;
  sentiment_score: number;
  as_of_utc: string;
  sources_used: string[];
};

export type MarketOverview = {
  indices: MarketQuote[];
  watchlist: MarketQuote[];
  most_traded: MarketQuote[];
  top_volume: MarketQuote[];
  top_gainers: MarketQuote[];
  top_losers: MarketQuote[];
  sectors: MarketQuote[];
  news: MarketNewsDigest;
  universe?: string;
  breadth: {
    advances: number;
    declines: number;
    unchanged: number;
    total: number;
  };
  as_of_utc: string;
  source: string;
};

export async function getMarketOverview(): Promise<MarketOverview | null> {
  const r = await fetch("/market/overview");
  if (!r.ok) return null;
  return r.json();
}

export type FxRate = {
  pair: "USDINR";
  rate: number;
  as_of: string;
  source: string;
};

export async function getUsdInrRate(): Promise<FxRate | null> {
  const r = await fetch("/strategy/fx/usdinr");
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

// ---------- Intraday scanner ----------

export type IntradaySource = "nse_direct" | "yfinance";
export type IntradayUniverse = "nifty50" | "nifty200" | "nifty500" | "fno" | "full_nse" | "custom_csv";
export type IntradayDirection = "LONG" | "SHORT";
export type IntradayDetectorDirection = IntradayDirection | "NEUTRAL";
export type IntradayModeId = "1A" | "1B" | "2" | "3" | "4" | "5" | "6" | "7";
export type IntradayMarketState =
  | "PRE_MARKET"
  | "PRE_OPEN"
  | "OPEN"
  | "LAST_HOUR"
  | "POST_MARKET"
  | "CLOSED"
  | "WEEKEND";
export type IntradayConviction = "fire" | "confirm" | "watch";

export type IntradaySettings = {
  default_source: IntradaySource;
  fallback_source: IntradaySource;
  nse_cookies_configured: boolean;
  default_universe: IntradayUniverse;
  auto_poll_interval_seconds: 30 | 60 | 300 | 900;
};

export type IntradaySettingsUpdate = {
  default_source?: IntradaySource;
  fallback_source?: IntradaySource;
  nse_cookies?: string;
  default_universe?: IntradayUniverse;
  auto_poll_interval_seconds?: 30 | 60 | 300 | 900;
};

export type IntradayUniverseOption = {
  id: IntradayUniverse;
  label: string;
  description: string;
  size: number;
  available: boolean;
  source: "static_csv" | "custom_csv" | "local_csv";
  static_path: string | null;
  merge_movers_default: boolean;
};

export type IntradayCustomCsvUploadResponse = {
  universe: "custom_csv";
  size: number;
  path: string;
};

export type IntradayModeContext = {
  mode_id: IntradayModeId;
  mode_label: string;
  market_state: IntradayMarketState;
  ist_time: string;
  is_market_day: boolean;
  data_freshness: string;
  source: string | null;
};

export type IntradayDetectorResult = {
  name: string;
  fired: boolean;
  strength: number;
  direction: IntradayDetectorDirection;
  reason: string | null;
  metadata: Record<string, unknown>;
};

export type IntradayPick = {
  symbol: string;
  direction: IntradayDirection;
  probability: number;
  detectors_fired: string[];
  detector_results: IntradayDetectorResult[];
  volume_x_avg: number;
  pct_change: number;
  ltp: number;
  conviction: IntradayConviction;
  asm_gsm_tags: string[];
  metadata: Record<string, unknown>;
};

export type IntradayScanError = {
  symbol: string | null;
  stage: string;
  message: string;
};

export type IntradayScanResult = {
  scan_id: string;
  universe: IntradayUniverse;
  source: IntradaySource;
  interval: string;
  mode: IntradayModeContext;
  created_at: string;
  completed_at: string | null;
  picks: IntradayPick[];
  watch_only: IntradayPick[];
  errors: IntradayScanError[];
  metadata: Record<string, unknown>;
};

export type IntradayScanRequest = {
  universe?: IntradayUniverse;
  source?: IntradaySource;
  source_override?: IntradaySource;
  mode?: IntradayModeId;
  mode_override?: IntradayModeId;
  interval?: string;
  lookback?: string;
  merge_movers?: boolean;
  max_symbols?: number;
  enforce_liquidity?: boolean;
  scan_concurrency?: number;
};

export type IntradayCandle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: IntradaySource;
};

export type IntradayOverlayPoint = {
  time: string;
  value: number;
};

export type IntradayDetectorOverlayPoint = {
  time: string;
  detector: string;
  direction: IntradayDetectorDirection;
  strength: number;
  reason: string | null;
};

export type IntradayChartOverlays = {
  vwap: IntradayOverlayPoint[];
  orb_high: IntradayOverlayPoint[];
  orb_low: IntradayOverlayPoint[];
  prev_day_high: IntradayOverlayPoint[];
  prev_day_low: IntradayOverlayPoint[];
  ma20: IntradayOverlayPoint[];
  ma50: IntradayOverlayPoint[];
  volume_ma: IntradayOverlayPoint[];
  pivot: IntradayOverlayPoint[];
  r1: IntradayOverlayPoint[];
  s1: IntradayOverlayPoint[];
  detector_points: IntradayDetectorOverlayPoint[];
};

export type IntradayChartResponse = {
  symbol: string;
  interval: string;
  source: string;
  candles: IntradayCandle[];
  overlays: IntradayChartOverlays;
  detector_results: IntradayDetectorResult[];
  as_of: string;
};

export type IntradayActivePickStatus =
  | "active"
  | "working"
  | "fading"
  | "flat"
  | "stale"
  | "error";

export type IntradayActivePick = {
  active_id: string;
  scan_id: string | null;
  symbol: string;
  pick: IntradayPick;
  activated_at: string;
  status: IntradayActivePickStatus;
  last_ltp: number | null;
  last_checked_at: string | null;
  move_from_scan_pct: number | null;
  source: string | null;
  message: string | null;
  metadata: Record<string, unknown>;
};

export type IntradayActivePicksResponse = {
  mode: IntradayModeContext;
  active: IntradayActivePick[];
  as_of: string;
};

export type IntradaySpecificStockResult = {
  symbol: string;
  source: string;
  interval: string;
  mode: IntradayModeContext;
  pick: IntradayPick | null;
  chart: IntradayChartResponse;
  detector_results: IntradayDetectorResult[];
  as_of: string;
  message: string | null;
};

export type IntradayMarketCue = {
  group: "global" | "adr" | "fx_commodity";
  label: string;
  symbol: string;
  last: number | null;
  change_pct: number | null;
  source: string;
  as_of: string | null;
  status: string;
};

export type IntradayPremarketWatchItem = {
  symbol: string;
  bias: IntradayDetectorDirection;
  probability: number | null;
  reason: string;
  source: string;
};

export type IntradayPreMarketSnapshot = {
  market_date: string;
  mode: IntradayModeContext;
  as_of: string;
  global_cues: IntradayMarketCue[];
  adrs: IntradayMarketCue[];
  fx_commodities: IntradayMarketCue[];
  fii_dii: Record<string, unknown>;
  watchlist: IntradayPremarketWatchItem[];
  errors: string[];
  metadata: Record<string, unknown>;
};

export type IntradayPreOpenRow = {
  symbol: string;
  ltp: number | null;
  indicative_open: number | null;
  pct_change: number | null;
  volume: number | null;
};

export type IntradayPreOpenWatchItem = {
  symbol: string;
  bias: IntradayDetectorDirection;
  pct_change: number | null;
  ltp: number | null;
  volume: number | null;
  reason: string;
};

export type IntradayPreOpenSnapshot = {
  market_date: string;
  mode: IntradayModeContext;
  as_of: string;
  rows: IntradayPreOpenRow[];
  watchlist: IntradayPreOpenWatchItem[];
  errors: string[];
  metadata: Record<string, number>;
};

export type IntradayPostMarketReviewRow = {
  symbol: string;
  direction: IntradayDirection;
  probability: number;
  scan_ltp: number;
  close_ltp: number | null;
  directional_move_pct: number | null;
  favorable_excursion_pct: number | null;
  adverse_excursion_pct: number | null;
  outcome: "worked" | "missed" | "flat" | "no_data";
  scan_id: string;
  notes: string;
};

export type IntradayPostMarketReview = {
  market_date: string;
  mode: IntradayModeContext;
  as_of: string;
  rows: IntradayPostMarketReviewRow[];
  summary: Record<string, number>;
  errors: string[];
  metadata: Record<string, number>;
};

export type IntradayWeekendCue = {
  label: string;
  symbol: string;
  weekly_change_pct: number | null;
  last: number | null;
  source: string;
  status: string;
};

export type IntradayWeekendWatchItem = {
  symbol: string;
  bias: IntradayDetectorDirection;
  probability: number;
  reason: string;
  source_scan_id: string;
};

export type IntradayWeekendSnapshot = {
  week_key: string;
  mode: IntradayModeContext;
  as_of: string;
  global_cues: IntradayWeekendCue[];
  fii_dii_summary: Record<string, unknown>;
  earnings_calendar: Record<string, unknown>[];
  watchlist: IntradayWeekendWatchItem[];
  errors: string[];
  metadata: Record<string, number>;
};

export async function getIntradaySettings(): Promise<IntradaySettings | null> {
  const r = await fetch("/intraday/settings");
  return r.ok ? r.json() : null;
}

export async function getIntradayMode(
  modeOverride?: IntradayModeId | null,
): Promise<IntradayModeContext | null> {
  const query = modeOverride ? `?mode_override=${encodeURIComponent(modeOverride)}` : "";
  const r = await fetch(`/intraday/mode${query}`);
  return r.ok ? r.json() : null;
}

export async function getIntradayUniverses(): Promise<IntradayUniverseOption[]> {
  const r = await fetch("/intraday/universes");
  return r.ok ? r.json() : [];
}

export async function uploadIntradayCustomCsv(
  csvText: string,
): Promise<IntradayCustomCsvUploadResponse> {
  const r = await fetch("/intraday/universes/custom-csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv_text: csvText }),
  });
  if (!r.ok) {
    throw new Error(`/intraday/universes/custom-csv failed (${r.status}): ${await r.text()}`);
  }
  return r.json();
}

export async function updateIntradaySettings(
  update: IntradaySettingsUpdate,
): Promise<IntradaySettings> {
  const r = await fetch("/intraday/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!r.ok) {
    throw new Error(`/intraday/settings failed (${r.status}): ${await r.text()}`);
  }
  return r.json();
}

export async function runIntradayScan(
  args: IntradayScanRequest,
): Promise<IntradayScanResult> {
  const r = await fetch("/intraday/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) {
    throw new Error(`/intraday/scan failed (${r.status}): ${await r.text()}`);
  }
  return r.json();
}

export async function getIntradayScan(scanId: string): Promise<IntradayScanResult | null> {
  const r = await fetch(`/intraday/scan/${encodeURIComponent(scanId)}`);
  return r.ok ? r.json() : null;
}

export async function getIntradayPicksToday(): Promise<IntradayScanResult[]> {
  const r = await fetch("/intraday/picks/today");
  return r.ok ? r.json() : [];
}

export async function getIntradayChart(args: {
  symbol: string;
  interval?: string;
  lookback?: string;
  source?: IntradaySource;
}): Promise<IntradayChartResponse | null> {
  const params = new URLSearchParams();
  if (args.interval) params.set("interval", args.interval);
  if (args.lookback) params.set("lookback", args.lookback);
  if (args.source) params.set("source", args.source);
  const query = params.toString();
  const r = await fetch(
    `/intraday/chart/${encodeURIComponent(args.symbol)}${query ? `?${query}` : ""}`,
  );
  return r.ok ? r.json() : null;
}

export async function getIntradaySpecificStock(args: {
  symbol: string;
  interval?: string;
  lookback?: string;
  source?: IntradaySource;
}): Promise<IntradaySpecificStockResult | null> {
  const params = new URLSearchParams();
  if (args.interval) params.set("interval", args.interval);
  if (args.lookback) params.set("lookback", args.lookback);
  if (args.source) params.set("source", args.source);
  const query = params.toString();
  const r = await fetch(
    `/intraday/symbol/${encodeURIComponent(args.symbol)}${query ? `?${query}` : ""}`,
  );
  return r.ok ? r.json() : null;
}

export async function getIntradayActivePicks(
  source?: IntradaySource,
): Promise<IntradayActivePicksResponse | null> {
  const query = source ? `?source=${encodeURIComponent(source)}` : "";
  const r = await fetch(`/intraday/picks/active${query}`);
  return r.ok ? r.json() : null;
}

export async function postIntradayActivePick(args: {
  symbol: string;
  scan_id?: string | null;
  pick?: IntradayPick;
  source?: IntradaySource;
}): Promise<IntradayActivePicksResponse> {
  const r = await fetch("/intraday/picks/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!r.ok) {
    throw new Error(`/intraday/picks/active failed (${r.status}): ${await r.text()}`);
  }
  return r.json();
}

export async function getIntradayPreMarket(
  refresh = false,
): Promise<IntradayPreMarketSnapshot | null> {
  const r = await fetch(`/intraday/premarket/today${refresh ? "?refresh=true" : ""}`);
  return r.ok ? r.json() : null;
}

export async function getIntradayPreOpen(
  refresh = false,
): Promise<IntradayPreOpenSnapshot | null> {
  const r = await fetch(`/intraday/preopen/today${refresh ? "?refresh=true" : ""}`);
  return r.ok ? r.json() : null;
}

export async function getIntradayPostMarket(
  refresh = false,
): Promise<IntradayPostMarketReview | null> {
  const r = await fetch(`/intraday/postmarket/today${refresh ? "?refresh=true" : ""}`);
  return r.ok ? r.json() : null;
}

export async function getIntradayWeekend(
  refresh = false,
): Promise<IntradayWeekendSnapshot | null> {
  const r = await fetch(`/intraday/weekend/this${refresh ? "?refresh=true" : ""}`);
  return r.ok ? r.json() : null;
}
