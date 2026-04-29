import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  BarChart3,
  Clock3,
  RefreshCw,
  Star,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { CompanyLogo } from "../../components/CompanyLogo";
import { getMarketOverview, type MarketOverview, type MarketQuote } from "../../lib/api";

function cleanSymbol(symbol: string): string {
  return symbol.replace(/\.NS$/i, "").replace(/^\^/, "");
}

function formatNumber(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(v);
}

function formatPrice(q: MarketQuote): string {
  if (q.last_price === null || q.last_price === undefined) return "—";
  if (q.currency === "INR") return `₹${formatNumber(q.last_price, q.last_price >= 1000 ? 0 : 2)}`;
  return formatNumber(q.last_price, q.last_price >= 1000 ? 2 : 2);
}

function formatAbsChange(q: MarketQuote): string {
  if (q.last_price === null || q.prev_close === null) return "—";
  const value = q.last_price - q.prev_close;
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}`;
}

function formatPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const pct = v * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function formatCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e7) return `${(v / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${(v / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

function formatTurnover(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `₹${formatCompact(v)}`;
}

function formatUpdated(asOf: string | null | undefined): string {
  if (!asOf) return "—";
  const d = new Date(asOf);
  if (Number.isNaN(d.getTime())) return asOf;
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function changeClass(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return "is-flat";
  return v > 0 ? "is-up" : "is-down";
}

function sparkPath(points: MarketQuote["sparkline"]): string {
  const values = points.map((p) => p.value).filter((v) => Number.isFinite(v));
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = 34 - ((v - min) / span) * 26;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function Sparkline({ quote }: { quote: MarketQuote }) {
  const path = sparkPath(quote.sparkline ?? []);
  return (
    <svg className="market-sparkline" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden>
      <path className="market-sparkline-area" d={path ? `${path} L 100 40 L 0 40 Z` : ""} />
      <path className="market-sparkline-line" d={path} />
    </svg>
  );
}

function ChangeBadge({ value }: { value: number | null | undefined }) {
  const Icon = (value ?? 0) >= 0 ? TrendingUp : TrendingDown;
  return (
    <span className={`market-change-badge ${changeClass(value)}`}>
      <Icon size={13} />
      {formatPct(value)}
    </span>
  );
}

function IndexCard({ quote }: { quote: MarketQuote }) {
  return (
    <article className={`market-index-card ${changeClass(quote.change_pct)}`}>
      <div className="market-index-card-top">
        <div>
          <div className="market-index-name">{quote.name}</div>
          <div className="market-index-exchange">{quote.exchange}</div>
        </div>
        <ChangeBadge value={quote.change_pct} />
      </div>
      <div className="market-index-price">{formatPrice(quote)}</div>
      <div className="market-index-delta">{formatAbsChange(quote)}</div>
      <Sparkline quote={quote} />
    </article>
  );
}

function QuoteIdentity({ quote, dense = false }: { quote: MarketQuote; dense?: boolean }) {
  const symbol = cleanSymbol(quote.symbol);
  const isIndex = quote.symbol.startsWith("^");
  return (
    <div className="market-quote-identity">
      {isIndex ? (
        <div className="market-index-avatar" aria-hidden>{symbol.slice(0, 2)}</div>
      ) : (
        <CompanyLogo
          symbol={quote.symbol}
          name={quote.name}
          exchange={quote.exchange}
          size={dense ? 24 : 30}
        />
      )}
      <div className="market-quote-copy">
        <div className="market-quote-name">{quote.name}</div>
        <div className="market-quote-symbol">{symbol} · {quote.exchange}</div>
      </div>
    </div>
  );
}

function QuoteRow({
  quote,
  metric,
  rank,
}: {
  quote: MarketQuote;
  metric: "price" | "turnover" | "volume";
  rank?: number;
}) {
  const metricValue = metric === "turnover"
    ? formatTurnover(quote.turnover)
    : metric === "volume"
      ? formatCompact(quote.volume)
      : formatPrice(quote);

  return (
    <div className="market-quote-row">
      {rank !== undefined && <div className="market-row-rank">{rank}</div>}
      <QuoteIdentity quote={quote} dense />
      <div className="market-row-numbers">
        <div className="market-row-price">{metricValue}</div>
        <div className={`market-row-change ${changeClass(quote.change_pct)}`}>
          {formatPct(quote.change_pct)}
        </div>
      </div>
    </div>
  );
}

function MarketPanel({
  title,
  subtitle,
  icon,
  rows,
  metric,
}: {
  title: string;
  subtitle: string;
  icon: ReactNode;
  rows: MarketQuote[];
  metric: "price" | "turnover" | "volume";
}) {
  return (
    <section className="market-panel">
      <div className="market-panel-header">
        <div>
          <h3>{icon}{title}</h3>
          <p>{subtitle}</p>
        </div>
      </div>
      <div className="market-quote-list">
        {rows.map((quote, index) => (
          <QuoteRow key={quote.symbol} quote={quote} metric={metric} rank={index + 1} />
        ))}
        {rows.length === 0 && <div className="market-empty-row">No market data.</div>}
      </div>
    </section>
  );
}

function WatchlistPanel({ rows }: { rows: MarketQuote[] }) {
  return (
    <section className="market-panel market-watchlist-panel">
      <div className="market-panel-header">
        <div>
          <h3><Star size={15} />Watchlist</h3>
          <p>Large-cap names</p>
        </div>
      </div>
      <div className="market-quote-list">
        {rows.map((quote) => (
          <QuoteRow key={quote.symbol} quote={quote} metric="price" />
        ))}
        {rows.length === 0 && <div className="market-empty-row">No watchlist data.</div>}
      </div>
    </section>
  );
}

function SectorBoard({ rows }: { rows: MarketQuote[] }) {
  const maxAbs = Math.max(0.01, ...rows.map((r) => Math.abs(r.change_pct ?? 0)));
  return (
    <section className="market-panel market-sector-panel">
      <div className="market-panel-header">
        <div>
          <h3><BarChart3 size={15} />Sector Moves</h3>
          <p>Nifty sector indices</p>
        </div>
      </div>
      <div className="market-sector-list">
        {rows.slice(0, 8).map((row) => {
          const width = `${Math.max(6, (Math.abs(row.change_pct ?? 0) / maxAbs) * 100)}%`;
          return (
            <div key={row.symbol} className="market-sector-row">
              <div className="market-sector-name">{row.name.replace("Nifty ", "")}</div>
              <div className="market-sector-track">
                <span className={changeClass(row.change_pct)} style={{ width }} />
              </div>
              <div className={`market-sector-change ${changeClass(row.change_pct)}`}>
                {formatPct(row.change_pct)}
              </div>
            </div>
          );
        })}
        {rows.length === 0 && <div className="market-empty-row">No sector data.</div>}
      </div>
    </section>
  );
}

function BreadthPanel({ overview }: { overview: MarketOverview }) {
  const { advances, declines, unchanged, total } = overview.breadth;
  const safeTotal = Math.max(total, 1);
  const advancePct = (advances / safeTotal) * 100;
  const declinePct = (declines / safeTotal) * 100;
  const tone = advances > declines ? "Positive Breadth" : declines > advances ? "Negative Breadth" : "Mixed Breadth";

  return (
    <section className="market-panel market-breadth-panel">
      <div className="market-panel-header">
        <div>
          <h3><Activity size={15} />Market Breadth</h3>
          <p>{tone}</p>
        </div>
      </div>
      <div className="market-breadth-stats">
        <div>
          <span>Advances</span>
          <strong className="is-up">{advances}</strong>
        </div>
        <div>
          <span>Declines</span>
          <strong className="is-down">{declines}</strong>
        </div>
        <div>
          <span>Unchanged</span>
          <strong>{unchanged}</strong>
        </div>
      </div>
      <div className="market-breadth-track" aria-label="Market breadth">
        <span className="market-breadth-up" style={{ width: `${advancePct}%` }} />
        <span className="market-breadth-down" style={{ width: `${declinePct}%` }} />
      </div>
      <div className="market-breadth-caption">
        {advancePct.toFixed(0)}% up · {declinePct.toFixed(0)}% down
      </div>
    </section>
  );
}

function LoadingPanel() {
  return (
    <div className="market-loading-grid">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="market-skeleton" />
      ))}
    </div>
  );
}

export function MarketOverviewPanel() {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMarketOverview();
      if (!data) {
        setError("Market overview data is unavailable.");
        return;
      }
      setOverview(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const status = useMemo(() => {
    if (!overview) return "Loading market data";
    const { advances, declines } = overview.breadth;
    if (advances > declines) return "Positive sentiment";
    if (declines > advances) return "Cautious sentiment";
    return "Balanced sentiment";
  }, [overview]);

  if (!overview && loading) {
    return (
      <div className="market-overview">
        <div className="market-overview-top">
          <div>
            <div className="market-eyebrow">India Markets</div>
            <h2>Market Dashboard</h2>
          </div>
          <button type="button" className="market-refresh-btn" disabled>
            <RefreshCw size={15} className="spinning" />
            Refresh
          </button>
        </div>
        <LoadingPanel />
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="market-overview">
        <div className="market-overview-top">
          <div>
            <div className="market-eyebrow">India Markets</div>
            <h2>Market Dashboard</h2>
          </div>
          <button type="button" className="market-refresh-btn" onClick={refresh} disabled={loading}>
            <RefreshCw size={15} className={loading ? "spinning" : ""} />
            Refresh
          </button>
        </div>
        <div className="panel-status error">{error ?? "Market overview data is unavailable."}</div>
      </div>
    );
  }

  return (
    <div className="market-overview">
      <div className="market-overview-top">
        <div>
          <div className="market-eyebrow">India Markets</div>
          <h2>Market Dashboard</h2>
        </div>
        <div className="market-top-actions">
          <div className="market-status-pill">
            <Activity size={14} />
            {status}
          </div>
          <div className="market-updated">
            <Clock3 size={14} />
            {formatUpdated(overview.as_of_utc)}
          </div>
          <button type="button" className="market-refresh-btn" onClick={refresh} disabled={loading}>
            <RefreshCw size={15} className={loading ? "spinning" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="panel-status error">{error}</div>}

      <section className="market-index-grid">
        {overview.indices.map((quote) => (
          <IndexCard key={quote.symbol} quote={quote} />
        ))}
      </section>

      <div className="market-layout">
        <div className="market-main-column">
          <div className="market-summary-grid">
            <BreadthPanel overview={overview} />
            <SectorBoard rows={overview.sectors} />
          </div>
          <MarketPanel
            title="Most Traded"
            subtitle="Highest turnover in the tracked large-cap set"
            icon={<Activity size={15} />}
            rows={overview.most_traded}
            metric="turnover"
          />
          <MarketPanel
            title="Top Intraday"
            subtitle="Best performers today"
            icon={<TrendingUp size={15} />}
            rows={overview.top_gainers}
            metric="price"
          />
        </div>

        <aside className="market-side-column">
          <WatchlistPanel rows={overview.watchlist} />
          <MarketPanel
            title="Top Volume"
            subtitle="Most shares exchanged"
            icon={<BarChart3 size={15} />}
            rows={overview.top_volume}
            metric="volume"
          />
          <MarketPanel
            title="Weak Today"
            subtitle="Largest downside moves"
            icon={<TrendingDown size={15} />}
            rows={overview.top_losers}
            metric="price"
          />
        </aside>
      </div>
    </div>
  );
}
