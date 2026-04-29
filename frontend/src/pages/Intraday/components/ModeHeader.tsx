import { useEffect, useMemo, useState } from "react";
import { Activity, Clock3, Database } from "lucide-react";
import {
  getIntradayMode,
  type IntradayModeContext,
  type IntradayModeId,
} from "../../../lib/api";

function formatIst(value: Date) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(value);
}

function cleanState(value: string) {
  return value.replaceAll("_", " ");
}

export function ModeHeader({
  mode,
  modeOverride,
}: {
  mode: IntradayModeContext | null;
  modeOverride: IntradayModeId | null;
}) {
  const [now, setNow] = useState(() => new Date());
  const [detected, setDetected] = useState<IntradayModeContext | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    getIntradayMode(modeOverride).then((row) => {
      if (active) setDetected(row);
    }).catch(() => {
      if (active) setDetected(null);
    });
    return () => {
      active = false;
    };
  }, [modeOverride]);

  const current = mode ?? detected;
  const items = useMemo(
    () => [
      { icon: <Clock3 size={15} />, label: `IST ${formatIst(now)}` },
      {
        icon: <Activity size={15} />,
        label: current ? cleanState(current.market_state) : "MARKET STATE",
      },
      {
        icon: <Database size={15} />,
        label: current ? current.data_freshness : "freshness unknown",
      },
      { icon: null, label: current ? current.mode_label : "Mode detecting" },
      { icon: null, label: current?.source ? `Source ${current.source}` : "Source pending" },
    ],
    [current, now],
  );

  return (
    <header className="intraday-mode-header">
      {items.map((item) => (
        <div className="intraday-mode-chip" key={item.label}>
          {item.icon}
          <span>{item.label}</span>
        </div>
      ))}
    </header>
  );
}
