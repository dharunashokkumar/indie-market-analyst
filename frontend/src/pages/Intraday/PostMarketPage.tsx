import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  getIntradayPostMarket,
  type IntradayPostMarketReview,
} from "../../lib/api";
import { IntradayNav } from "./components/IntradayNav";
import { ModeHeader } from "./components/ModeHeader";

function formatPct(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number | null) {
  return value === null ? "-" : value.toFixed(value >= 1000 ? 1 : 2);
}

export function PostMarketPage() {
  const [review, setReview] = useState<IntradayPostMarketReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (refresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setReview(await getIntradayPostMarket(refresh));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="intraday-page">
      <IntradayNav />
      <ModeHeader mode={review?.mode ?? null} modeOverride="4" />
      <div className="intraday-page-toolbar">
        <div>
          <strong>Post-market review</strong>
          <span>{review?.market_date ?? "today"}</span>
        </div>
        <button
          type="button"
          className="intraday-icon-text-btn"
          onClick={() => load(true)}
          disabled={loading}
        >
          <RefreshCw size={15} />
          {loading ? "Loading" : "Refresh"}
        </button>
      </div>

      {error && <div className="panel-status error">{error}</div>}

      <div className="intraday-scan-meta">
        <span>Worked {review?.summary.worked ?? 0}</span>
        <span>Missed {review?.summary.missed ?? 0}</span>
        <span>Flat {review?.summary.flat ?? 0}</span>
        <span>No data {review?.summary.no_data ?? 0}</span>
      </div>

      <section className="intraday-mode-panel">
        <h3>Review rows</h3>
        <div className="intraday-simple-table">
          <div className="intraday-simple-head review">
            <span>Symbol</span>
            <span>Side</span>
            <span>Prob</span>
            <span>Scan</span>
            <span>Close</span>
            <span>Move</span>
            <span>Outcome</span>
          </div>
          {(review?.rows ?? []).map((row) => (
            <div className="intraday-simple-row review" key={`${row.scan_id}-${row.symbol}`}>
              <strong>{row.symbol}</strong>
              <span>{row.direction}</span>
              <span>{formatPct(row.probability)}</span>
              <span>{formatPrice(row.scan_ltp)}</span>
              <span>{formatPrice(row.close_ltp)}</span>
              <span>{formatPct(row.directional_move_pct)}</span>
              <span className={`outcome-pill ${row.outcome}`}>{row.outcome}</span>
            </div>
          ))}
          {review && review.rows.length === 0 && (
            <div className="intraday-empty-state">No stored picks to review.</div>
          )}
        </div>
      </section>
    </div>
  );
}
