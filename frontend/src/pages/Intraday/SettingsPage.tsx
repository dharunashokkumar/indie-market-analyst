import { useEffect, useMemo, useState } from "react";
import { Database, RefreshCw, Save, Settings2, Upload } from "lucide-react";
import {
  getIntradaySettings,
  updateIntradaySettings,
  uploadIntradayCustomCsv,
  type IntradaySettings,
  type IntradaySource,
} from "../../lib/api";
import { UniversePicker } from "./components/UniversePicker";

const SOURCE_OPTIONS: { id: IntradaySource; label: string }[] = [
  { id: "nse_direct", label: "NSE direct" },
  { id: "yfinance", label: "yfinance" },
];

const INTERVAL_OPTIONS: { seconds: IntradaySettings["auto_poll_interval_seconds"]; label: string }[] = [
  { seconds: 30, label: "30s" },
  { seconds: 60, label: "60s" },
  { seconds: 300, label: "5m" },
  { seconds: 900, label: "15m" },
];

const DEFAULT_SETTINGS: IntradaySettings = {
  default_source: "nse_direct",
  fallback_source: "yfinance",
  nse_cookies_configured: false,
  default_universe: "nifty500",
  auto_poll_interval_seconds: 60,
};

function sourceLabel(source: IntradaySource) {
  return SOURCE_OPTIONS.find((option) => option.id === source)?.label ?? source;
}

export function SettingsPage() {
  const [settings, setSettings] = useState<IntradaySettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingCsv, setUploadingCsv] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nseCookiesInput, setNseCookiesInput] = useState("");

  const cookieState = useMemo(
    () => (settings.nse_cookies_configured || nseCookiesInput.trim() ? "Configured" : "Empty"),
    [nseCookiesInput, settings.nse_cookies_configured],
  );

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const loaded = await getIntradaySettings();
      if (loaded) {
        setSettings(loaded);
        setNseCookiesInput("");
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setSaving(true);
    setStatus(null);
    setError(null);
    try {
      const update = {
        default_source: settings.default_source,
        fallback_source: settings.fallback_source,
        default_universe: settings.default_universe,
        auto_poll_interval_seconds: settings.auto_poll_interval_seconds,
        ...(nseCookiesInput.trim() ? { nse_cookies: nseCookiesInput } : {}),
      };
      const saved = await updateIntradaySettings(update);
      setSettings(saved);
      setNseCookiesInput("");
      setStatus("Saved");
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const uploadCustomCsv = async (file: File | null) => {
    if (!file) return;
    setUploadingCsv(true);
    setStatus(null);
    setError(null);
    try {
      const csvText = await file.text();
      const uploaded = await uploadIntradayCustomCsv(csvText);
      setSettings((s) => ({ ...s, default_universe: "custom_csv" }));
      setStatus(`Uploaded ${uploaded.size} symbols`);
    } catch (err) {
      setError(String(err));
    } finally {
      setUploadingCsv(false);
    }
  };

  return (
    <div className="intraday-settings">
      <header className="intraday-settings-header">
        <div>
          <h2>
            <Settings2 size={24} />
            Intraday Settings
          </h2>
          <div className="intraday-settings-meta">
            <span>Source: {sourceLabel(settings.default_source)}</span>
            <span>Fallback: {sourceLabel(settings.fallback_source)}</span>
            <span>NSE cookies: {cookieState}</span>
          </div>
        </div>
        <div className="intraday-settings-actions">
          <button
            type="button"
            className="intraday-icon-text-btn"
            onClick={load}
            disabled={loading || saving}
          >
            <RefreshCw size={15} />
            Refresh
          </button>
          <button
            type="button"
            className="intraday-primary-btn"
            onClick={save}
            disabled={loading || saving}
          >
            <Save size={15} />
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </header>

      <section className="intraday-settings-panel">
        <div className="intraday-settings-panel-title">
          <Database size={17} />
          Data Source
        </div>

        <div className="intraday-settings-grid">
          <label className="intraday-form-row">
            <span>Primary source</span>
            <div className="segmented-control">
              {SOURCE_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className={settings.default_source === option.id ? "active" : ""}
                  onClick={() => setSettings((s) => ({ ...s, default_source: option.id }))}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </label>

          <label className="intraday-form-row">
            <span>Fallback source</span>
            <select
              value={settings.fallback_source}
              onChange={(e) => (
                setSettings((s) => ({ ...s, fallback_source: e.target.value as IntradaySource }))
              )}
            >
              {SOURCE_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="intraday-form-row">
            <span>Default universe</span>
            <UniversePicker
              value={settings.default_universe}
              disabled={loading || saving}
              onChange={(default_universe) => setSettings((s) => ({ ...s, default_universe }))}
            />
          </label>

          <label className="intraday-form-row">
            <span>Auto-poll interval</span>
            <select
              value={settings.auto_poll_interval_seconds}
              onChange={(e) => (
                setSettings((s) => ({
                  ...s,
                  auto_poll_interval_seconds: Number(
                    e.target.value,
                  ) as IntradaySettings["auto_poll_interval_seconds"],
                }))
              )}
            >
              {INTERVAL_OPTIONS.map((option) => (
                <option key={option.seconds} value={option.seconds}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="intraday-form-row">
            <span>Custom CSV</span>
            <div className="intraday-file-upload">
              <Upload size={15} />
              <input
                type="file"
                accept=".csv,text/csv"
                disabled={uploadingCsv || saving || loading}
                onChange={(e) => uploadCustomCsv(e.target.files?.[0] ?? null)}
              />
            </div>
          </label>
        </div>

        <label className="intraday-form-row cookie-row">
          <span>NSE cookies</span>
          <textarea
            value={nseCookiesInput}
            spellCheck={false}
            onChange={(e) => setNseCookiesInput(e.target.value)}
            placeholder={
              settings.nse_cookies_configured
                ? "Cookie configured. Paste a new value to replace it."
                : "name=value; name2=value2"
            }
          />
        </label>

        {(loading || uploadingCsv || status || error) && (
          <div className={`panel-status${error ? " error" : ""}`}>
            {loading ? "Loading" : uploadingCsv ? "Uploading" : error ?? status}
          </div>
        )}
      </section>
    </div>
  );
}
