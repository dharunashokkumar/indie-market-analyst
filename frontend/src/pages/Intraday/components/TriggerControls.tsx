import { Play, RefreshCw } from "lucide-react";
import {
  type IntradayModeId,
  type IntradaySource,
  type IntradayUniverse,
} from "../../../lib/api";
import { UniversePicker } from "./UniversePicker";

const SOURCE_OPTIONS: { id: IntradaySource; label: string }[] = [
  { id: "nse_direct", label: "NSE direct" },
  { id: "yfinance", label: "yfinance" },
];

const INTERVAL_OPTIONS = [
  { seconds: 30, label: "30s" },
  { seconds: 60, label: "60s" },
  { seconds: 300, label: "5m" },
  { seconds: 900, label: "15m" },
];

const MODE_OPTIONS: { id: IntradayModeId | ""; label: string }[] = [
  { id: "", label: "Auto" },
  { id: "2", label: "Live scan" },
  { id: "3", label: "Last hour" },
];

export function TriggerControls({
  universe,
  source,
  modeOverride,
  intervalSeconds,
  autoPoll,
  loading,
  modeLocked = false,
  onUniverseChange,
  onSourceChange,
  onModeOverrideChange,
  onIntervalChange,
  onAutoPollChange,
  onRun,
}: {
  universe: IntradayUniverse;
  source: IntradaySource;
  modeOverride: IntradayModeId | null;
  intervalSeconds: number;
  autoPoll: boolean;
  loading: boolean;
  modeLocked?: boolean;
  onUniverseChange: (value: IntradayUniverse) => void;
  onSourceChange: (value: IntradaySource) => void;
  onModeOverrideChange: (value: IntradayModeId | null) => void;
  onIntervalChange: (value: number) => void;
  onAutoPollChange: (value: boolean) => void;
  onRun: () => void;
}) {
  return (
    <div className="intraday-trigger-controls">
      <label className="intraday-form-row">
        <span>Universe</span>
        <UniversePicker
          value={universe}
          onChange={onUniverseChange}
          disabled={loading}
          showMeta={false}
        />
      </label>

      <label className="intraday-form-row">
        <span>Source</span>
        <select
          value={source}
          disabled={loading}
          onChange={(event) => onSourceChange(event.target.value as IntradaySource)}
        >
          {SOURCE_OPTIONS.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="intraday-form-row">
        <span>Mode</span>
        <select
          value={modeOverride ?? ""}
          disabled={loading || modeLocked}
          onChange={(event) => (
            onModeOverrideChange(
              event.target.value ? event.target.value as IntradayModeId : null,
            )
          )}
        >
          {MODE_OPTIONS.map((option) => (
            <option key={option.id || "auto"} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="intraday-form-row">
        <span>Poll</span>
        <select
          value={intervalSeconds}
          disabled={loading}
          onChange={(event) => onIntervalChange(Number(event.target.value))}
        >
          {INTERVAL_OPTIONS.map((option) => (
            <option key={option.seconds} value={option.seconds}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="intraday-poll-toggle">
        <input
          type="checkbox"
          checked={autoPoll}
          disabled={loading}
          onChange={(event) => onAutoPollChange(event.target.checked)}
        />
        <RefreshCw size={15} />
        <span>Auto-poll</span>
      </label>

      <button
        type="button"
        className="intraday-primary-btn"
        disabled={loading}
        onClick={onRun}
      >
        <Play size={15} />
        {loading ? "Scanning" : "Run Scan"}
      </button>
    </div>
  );
}
