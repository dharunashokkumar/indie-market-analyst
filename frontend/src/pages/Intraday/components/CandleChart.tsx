import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import type {
  IntradayChartResponse,
  IntradayOverlayPoint,
} from "../../../lib/api";
import type { OverlayState } from "./OverlayToggles";

function toTime(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

function chartColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    text: style.getPropertyValue("--text").trim() || "#1d1c1a",
    border: style.getPropertyValue("--border").trim() || "#eceae2",
    bg: style.getPropertyValue("--surface").trim() || "#ffffff",
    up: "#16803c",
    down: "#b42318",
    vwap: "#2563eb",
    orb: "#7c3aed",
    previous: "#6b7280",
    ma20: "#d97706",
    ma50: "#0891b2",
    pivot: "#475569",
    volume: "#94a3b8",
  };
}

function lineData(points: IntradayOverlayPoint[]) {
  return points.map((point) => ({ time: toTime(point.time), value: point.value }));
}

export function CandleChart({
  chart,
  overlays,
  loading,
}: {
  chart: IntradayChartResponse | null;
  overlays: OverlayState;
  loading: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || !chart || chart.candles.length === 0) return undefined;
    const colors = chartColors();
    const instance = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: colors.bg },
        textColor: colors.text,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: {
        borderColor: colors.border,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const candles = instance.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderVisible: false,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
    });
    candles.setData(
      chart.candles.map((candle) => ({
        time: toTime(candle.timestamp),
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })),
    );

    const addLine = (
      points: IntradayOverlayPoint[],
      color: string,
      lineStyle = 0,
      priceScaleId = "right",
      lineWidth: 1 | 2 = 1,
    ) => {
      if (points.length === 0) return;
      const series = instance.addSeries(LineSeries, {
        color,
        lineWidth,
        lineStyle,
        priceScaleId,
      });
      series.setData(lineData(points));
    };

    if (overlays.volume) {
      const volume = instance.addSeries(HistogramSeries, {
        color: `${colors.volume}88`,
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      volume.setData(
        chart.candles.map((candle) => ({
          time: toTime(candle.timestamp),
          value: candle.volume,
          color: candle.close >= candle.open ? `${colors.up}55` : `${colors.down}55`,
        })),
      );
      instance.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
        borderColor: colors.border,
      });
      addLine(chart.overlays.volume_ma, colors.volume, 1, "volume");
    }

    if (overlays.vwap) addLine(chart.overlays.vwap, colors.vwap, 0, "right", 2);
    if (overlays.orb) {
      addLine(chart.overlays.orb_high, colors.orb, 2);
      addLine(chart.overlays.orb_low, colors.orb, 2);
    }
    if (overlays.prevDay) {
      addLine(chart.overlays.prev_day_high, colors.previous, 1);
      addLine(chart.overlays.prev_day_low, colors.previous, 1);
    }
    if (overlays.ma20) addLine(chart.overlays.ma20, colors.ma20);
    if (overlays.ma50) addLine(chart.overlays.ma50, colors.ma50);
    if (overlays.pivots) {
      addLine(chart.overlays.pivot, colors.pivot, 3);
      addLine(chart.overlays.r1, colors.pivot, 2);
      addLine(chart.overlays.s1, colors.pivot, 2);
    }

    instance.timeScale().fitContent();
    return () => instance.remove();
  }, [chart, overlays]);

  const detectorPoints = useMemo(
    () => chart?.overlays.detector_points ?? [],
    [chart],
  );

  return (
    <div className="intraday-chart-panel">
      <div className="intraday-chart-title">
        <strong>{chart?.symbol ?? "Chart"}</strong>
        {chart && <span>{chart.interval} · {chart.source}</span>}
      </div>
      <div className="intraday-chart-canvas" ref={containerRef}>
        {!chart && <div className="intraday-empty-state">Select a pick.</div>}
        {chart && chart.candles.length === 0 && (
          <div className="intraday-empty-state">No candles returned.</div>
        )}
        {loading && <div className="intraday-chart-loading">Loading</div>}
      </div>
      {detectorPoints.length > 0 && (
        <div className="intraday-detector-strip">
          {detectorPoints.map((point) => (
            <span key={`${point.detector}-${point.direction}`}>
              {point.detector} {point.direction} {(point.strength * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
