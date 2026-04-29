import { FormEvent, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import {
  getIntradaySpecificStock,
  searchSymbols,
  type IntradaySource,
  type IntradaySpecificStockResult,
  type NseSymbolRow,
} from "../../lib/api";
import { CandleChart } from "./components/CandleChart";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";
import {
  DEFAULT_OVERLAYS,
  OverlayToggles,
  type OverlayState,
} from "./components/OverlayToggles";

function formatPct(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : `${(value * 100).toFixed(2)}%`;
}

export function SymbolPage() {
  const { ticker } = useParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState(ticker ?? "");
  const [source, setSource] = useState<IntradaySource>("yfinance");
  const [matches, setMatches] = useState<NseSymbolRow[]>([]);
  const [result, setResult] = useState<IntradaySpecificStockResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overlays, setOverlays] = useState<OverlayState>(DEFAULT_OVERLAYS);

  const cleanTicker = useMemo(() => (ticker ?? "").trim().toUpperCase(), [ticker]);

  useEffect(() => {
    setQuery(ticker ?? "");
  }, [ticker]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setMatches([]);
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        setMatches(await searchSymbols(q, 8));
      } catch {
        setMatches([]);
      }
    }, 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!cleanTicker) {
      setResult(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    getIntradaySpecificStock({
      symbol: cleanTicker,
      interval: "5m",
      lookback: "20d",
      source,
    })
      .then((row) => {
        if (active) setResult(row);
      })
      .catch((err) => {
        if (active) {
          setResult(null);
          setError(String(err));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [cleanTicker, source]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const symbol = query.trim().toUpperCase();
    if (symbol) navigate(`/intraday/symbol/${encodeURIComponent(symbol)}`);
  };

  return (
    <div className="intraday-page">
      <IntradayNav />
      <ModeHeader mode={result?.mode ?? null} modeOverride="5" />

      <form className="intraday-symbol-search" onSubmit={submit}>
        <label className="intraday-form-row">
          <span>Symbol</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search NSE symbol"
          />
        </label>
        <label className="intraday-form-row">
          <span>Source</span>
          <select
            value={source}
            onChange={(event) => setSource(event.target.value as IntradaySource)}
          >
            <option value="nse_direct">NSE direct</option>
            <option value="yfinance">yfinance</option>
          </select>
        </label>
        <button type="submit" className="intraday-primary-btn">
          <Search size={15} />
          Analyze
        </button>
      </form>

      {error && <div className="panel-status error">{error}</div>}

      {matches.length > 0 && (
        <div className="intraday-symbol-matches">
          {matches.map((match) => (
            <button
              type="button"
              key={match.symbol}
              onClick={() => navigate(`/intraday/symbol/${encodeURIComponent(match.symbol)}`)}
            >
              <strong>{match.symbol}</strong>
              <span>{match.name}</span>
            </button>
          ))}
        </div>
      )}

      <div className="intraday-live-shell">
        <section className="intraday-mode-panel">
          <h3>{cleanTicker || "Symbol"}</h3>
          {result?.pick ? (
            <div className="intraday-symbol-card">
              <div>
                <span>Direction</span>
                <strong>{result.pick.direction}</strong>
              </div>
              <div>
                <span>Probability</span>
                <strong>{formatPct(result.pick.probability)}</strong>
              </div>
              <div>
                <span>Volume</span>
                <strong>{result.pick.volume_x_avg.toFixed(1)}x</strong>
              </div>
              <div>
                <span>Move</span>
                <strong>{formatPct(result.pick.pct_change)}</strong>
              </div>
              <div className="wide">
                <span>Detectors</span>
                <strong>{result.pick.detectors_fired.join(", ")}</strong>
              </div>
            </div>
          ) : (
            <div className="intraday-empty-state">
              {loading ? "Loading" : result?.message ?? "Search a symbol."}
            </div>
          )}
        </section>
        <div className="intraday-chart-column">
          <OverlayToggles value={overlays} onChange={setOverlays} />
          <CandleChart chart={result?.chart ?? null} overlays={overlays} loading={loading} />
        </div>
      </div>
    </div>
  );
}
