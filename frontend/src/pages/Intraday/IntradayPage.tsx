import { useEffect, useMemo, useState } from "react";
import {
  getIntradayChart,
  getIntradayPicksToday,
  getIntradaySettings,
  type IntradayChartResponse,
  type IntradayModeId,
  type IntradayScanRequest,
  type IntradaySource,
  type IntradayUniverse,
} from "../../lib/api";
import { CandleChart } from "./components/CandleChart";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";
import {
  DEFAULT_OVERLAYS,
  OverlayToggles,
  type OverlayState,
} from "./components/OverlayToggles";
import { PicksTable } from "./components/PicksTable";
import { TriggerControls } from "./components/TriggerControls";
import { useScanPolling } from "./hooks/useScanPolling";

export function IntradayPage({
  fixedMode = null,
}: {
  fixedMode?: IntradayModeId | null;
}) {
  const [universe, setUniverse] = useState<IntradayUniverse>("nifty500");
  const [source, setSource] = useState<IntradaySource>("nse_direct");
  const [modeOverride, setModeOverride] = useState<IntradayModeId | null>(fixedMode);
  const [intervalSeconds, setIntervalSeconds] = useState(60);
  const [autoPoll, setAutoPoll] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [chart, setChart] = useState<IntradayChartResponse | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [overlays, setOverlays] = useState<OverlayState>(DEFAULT_OVERLAYS);

  useEffect(() => {
    let active = true;
    getIntradaySettings().then((settings) => {
      if (!active || !settings) return;
      setUniverse(settings.default_universe);
      setSource(settings.default_source);
      setIntervalSeconds(settings.auto_poll_interval_seconds);
    }).catch(() => {});
    getIntradayPicksToday().then((rows) => {
      if (!active || rows.length === 0) return;
      setScan(rows[0]);
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (fixedMode) setModeOverride(fixedMode);
  }, [fixedMode]);

  const request: IntradayScanRequest = useMemo(
    () => ({
      universe,
      source,
      mode_override: modeOverride ?? undefined,
      interval: "5m",
      lookback: "20d",
      merge_movers: true,
      enforce_liquidity: true,
    }),
    [modeOverride, source, universe],
  );

  const { scan, loading, error, runScan, setScan } = useScanPolling({
    request,
    autoPoll,
    intervalSeconds,
  });

  const visiblePicks = scan?.picks ?? [];
  const watchOnly = scan?.watch_only ?? [];
  const errorCount = scan?.errors.length ?? 0;

  useEffect(() => {
    const nextSymbol = visiblePicks[0]?.symbol ?? watchOnly[0]?.symbol ?? null;
    setSelectedSymbol((current) => {
      if (!nextSymbol) return null;
      const stillPresent = [...visiblePicks, ...watchOnly].some((pick) => pick.symbol === current);
      return stillPresent ? current : nextSymbol;
    });
  }, [scan?.scan_id, visiblePicks, watchOnly]);

  useEffect(() => {
    if (!selectedSymbol) {
      setChart(null);
      return;
    }
    let active = true;
    setChartLoading(true);
    getIntradayChart({ symbol: selectedSymbol, interval: "5m", lookback: "20d", source })
      .then((result) => {
        if (active) setChart(result);
      })
      .catch(() => {
        if (active) setChart(null);
      })
      .finally(() => {
        if (active) setChartLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedSymbol, source]);

  return (
    <div className="intraday-page">
      <IntradayNav />
      <ModeHeader mode={scan?.mode ?? null} modeOverride={modeOverride} />

      <TriggerControls
        universe={universe}
        source={source}
        modeOverride={modeOverride}
        intervalSeconds={intervalSeconds}
        autoPoll={autoPoll}
        loading={loading}
        modeLocked={Boolean(fixedMode)}
        onUniverseChange={setUniverse}
        onSourceChange={setSource}
        onModeOverrideChange={setModeOverride}
        onIntervalChange={setIntervalSeconds}
        onAutoPollChange={setAutoPoll}
        onRun={() => { runScan(); }}
      />

      <div className="intraday-scan-meta">
        <span>Scan {scan?.scan_id ?? "pending"}</span>
        <span>Picks {visiblePicks.length}</span>
        <span>Watch {watchOnly.length}</span>
        <span>Errors {errorCount}</span>
      </div>

      {(error || errorCount > 0) && (
        <div className="panel-status error">
          {error ?? `${errorCount} symbol fetch errors`}
        </div>
      )}

      <div className="intraday-live-shell">
        <PicksTable
          picks={visiblePicks}
          watchOnly={watchOnly}
          selectedSymbol={selectedSymbol}
          onSelect={setSelectedSymbol}
        />
        <div className="intraday-chart-column">
          <OverlayToggles value={overlays} onChange={setOverlays} />
          <CandleChart chart={chart} overlays={overlays} loading={chartLoading} />
        </div>
      </div>
    </div>
  );
}
