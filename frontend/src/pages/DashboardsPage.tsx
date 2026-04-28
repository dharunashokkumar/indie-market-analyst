import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EquityPanel } from "./Dashboards/EquityPanel";
import { BacktestsPanel } from "./Dashboards/BacktestsPanel";
import { HeatmapPanel } from "./Dashboards/HeatmapPanel";

type TabId = "equity" | "backtests" | "heatmap";
const TABS: { id: TabId; label: string }[] = [
  { id: "equity", label: "Equity" },
  { id: "backtests", label: "Backtests" },
  { id: "heatmap", label: "Heatmap" },
];

function asTab(v: string | null): TabId {
  return v === "backtests" || v === "heatmap" ? v : "equity";
}

export function DashboardsPage() {
  const [params, setParams] = useSearchParams();
  const initial = useMemo(() => asTab(params.get("tab")), [params]);
  const [tab, setTab] = useState<TabId>(initial);

  useEffect(() => {
    setTab(initial);
  }, [initial]);

  const selectTab = (next: TabId) => {
    setTab(next);
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  return (
    <div className="dashboards">
      <header className="dashboards-header">
        <h2>Dashboards</h2>
        <div className="dashboards-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`dashboards-tab${tab === t.id ? " active" : ""}`}
              onClick={() => selectTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>
      <div className="dashboards-panel">
        {tab === "equity" && <EquityPanel />}
        {tab === "backtests" && <BacktestsPanel />}
        {tab === "heatmap" && <HeatmapPanel />}
      </div>
    </div>
  );
}
