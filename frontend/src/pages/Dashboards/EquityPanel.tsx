import { useEffect, useMemo, useRef, useState } from "react";
import {
  AreaSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import {
  getBenchmark,
  getRun,
  listRuns,
  type BacktestRunBlob,
  type BenchmarkPoint,
  type RunRow,
} from "../../lib/api";

function toTime(dateStr: string): UTCTimestamp {
  return Math.floor(new Date(dateStr + "T00:00:00Z").getTime() / 1000) as UTCTimestamp;
}

function drawdownSeries(curve: { date: string; equity: number }[]) {
  let peak = -Infinity;
  return curve.map((p) => {
    peak = Math.max(peak, p.equity);
    const dd = peak === 0 ? 0 : (p.equity - peak) / peak;
    return { time: toTime(p.date), value: dd * 100 };
  });
}

function chartColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    text: style.getPropertyValue("--text").trim() || "#1d1c1a",
    border: style.getPropertyValue("--border").trim() || "#eceae2",
    accent: style.getPropertyValue("--accent").trim() || "#d97757",
    danger: style.getPropertyValue("--danger").trim() || "#b91c1c",
    muted: style.getPropertyValue("--text-muted").trim() || "#6e6a62",
    bg: style.getPropertyValue("--surface").trim() || "#ffffff",
  };
}

function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(2)}%`;
}
function formatNum(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toFixed(2);
}

export function EquityPanel() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [blob, setBlob] = useState<BacktestRunBlob | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkPoint[] | null>(null);
  const [showBenchmark, setShowBenchmark] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const equitySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const drawdownSeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const benchmarkSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    listRuns().then((rows) => {
      const backtests = rows.filter((r) => r.kind === "backtest");
      setRuns(backtests);
      if (backtests.length > 0) setSelectedId(backtests[0].id);
    });
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    setBenchmark(null);
    setShowBenchmark(false);
    getRun(selectedId)
      .then((res) => {
        if (!res) {
          setError("Run not found");
          setBlob(null);
        } else {
          setBlob(res.blob);
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [selectedId]);

  useEffect(() => {
    if (!containerRef.current || !blob) return;
    const colors = chartColors();
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: colors.bg },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border, timeVisible: false },
    });
    const equity = chart.addSeries(LineSeries, {
      color: colors.accent,
      lineWidth: 2,
      priceScaleId: "right",
    });
    equity.setData(
      blob.equity_curve.map((p) => ({ time: toTime(p.date), value: p.equity })),
    );
    const drawdown = chart.addSeries(AreaSeries, {
      topColor: `${colors.danger}55`,
      bottomColor: `${colors.danger}11`,
      lineColor: colors.danger,
      lineWidth: 1,
      priceScaleId: "drawdown",
    });
    drawdown.setData(drawdownSeries(blob.equity_curve));
    chart.priceScale("drawdown").applyOptions({
      scaleMargins: { top: 0.75, bottom: 0 },
      borderColor: colors.border,
    });

    chartRef.current = chart;
    equitySeriesRef.current = equity;
    drawdownSeriesRef.current = drawdown;
    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
      equitySeriesRef.current = null;
      drawdownSeriesRef.current = null;
      benchmarkSeriesRef.current = null;
    };
  }, [blob]);

  useEffect(() => {
    if (!chartRef.current || !blob) return;
    if (!showBenchmark) {
      if (benchmarkSeriesRef.current) {
        chartRef.current.removeSeries(benchmarkSeriesRef.current);
        benchmarkSeriesRef.current = null;
      }
      return;
    }
    let cancelled = false;
    (async () => {
      let points: BenchmarkPoint[] | null = benchmark;
      if (!points && selectedId) {
        const fetched = await getBenchmark(selectedId);
        if (cancelled) return;
        if (fetched) {
          points = fetched.points;
          setBenchmark(fetched.points);
        }
      }
      if (!points || !chartRef.current || !blob) return;
      const colors = chartColors();
      const base = blob.initial_capital;
      const series = chartRef.current.addSeries(LineSeries, {
        color: colors.muted,
        lineWidth: 1,
        lineStyle: 1, // dashed
        priceScaleId: "right",
      });
      series.setData(
        points.map((p: BenchmarkPoint) => ({
          time: toTime(p.date),
          value: p.normalized * base,
        })),
      );
      benchmarkSeriesRef.current = series;
    })();
    return () => { cancelled = true; };
  }, [showBenchmark, blob, selectedId, benchmark]);

  const metrics = blob?.metrics ?? {};
  const metricsStrip = useMemo(
    () => [
      { label: "CAGR", value: formatPct(metrics.annualized_return) },
      { label: "Sharpe", value: formatNum(metrics.sharpe) },
      { label: "Sortino", value: formatNum(metrics.sortino) },
      { label: "Max DD", value: formatPct(metrics.max_drawdown) },
      { label: "Ann. Vol", value: formatPct(metrics.volatility_annualized) },
    ],
    [metrics],
  );

  if (runs.length === 0) {
    return (
      <div className="panel-empty">
        <p>No backtest runs yet.</p>
        <code>make seed-runs</code>
        <p className="panel-empty-hint">seeds a 1y SMA(20/50) run on RELIANCE.NS.</p>
      </div>
    );
  }

  return (
    <div className="equity-panel">
      <div className="panel-toolbar">
        <label>
          <span className="toolbar-label">Run</span>
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {runs.map((r) => {
              const sym = r.summary?.symbol ?? r.id.slice(0, 8);
              const strat = r.summary?.strategy ?? "";
              const label = strat ? `${sym} • ${strat}` : sym;
              return (
                <option key={r.id} value={r.id}>
                  {label} — {new Date(r.created_at * 1000).toLocaleDateString()}
                </option>
              );
            })}
          </select>
        </label>
        <label className="toolbar-toggle">
          <input
            type="checkbox"
            checked={showBenchmark}
            onChange={(e) => setShowBenchmark(e.target.checked)}
          />
          <span>Nifty50 overlay</span>
        </label>
      </div>

      <div className="metrics-strip">
        {metricsStrip.map((m) => (
          <div key={m.label} className="metrics-cell">
            <div className="metrics-label">{m.label}</div>
            <div className="metrics-value">{m.value}</div>
          </div>
        ))}
      </div>

      <div className="equity-chart" ref={containerRef} />
      {loading && <div className="panel-status">Loading…</div>}
      {error && <div className="panel-status error">{error}</div>}
    </div>
  );
}
