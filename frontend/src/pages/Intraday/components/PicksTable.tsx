import clsx from "clsx";
import type { IntradayPick } from "../../../lib/api";

function formatPct(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function formatPrice(value: number) {
  return value.toFixed(value >= 1000 ? 1 : 2);
}

function convictionLabel(value: IntradayPick["conviction"]) {
  if (value === "fire") return "High";
  if (value === "confirm") return "Confirm";
  return "Watch";
}

function PickRow({
  pick,
  selected,
  onSelect,
}: {
  pick: IntradayPick;
  selected: boolean;
  onSelect: (symbol: string) => void;
}) {
  return (
    <button
      type="button"
      className={clsx("intraday-pick-row", selected && "selected")}
      onClick={() => onSelect(pick.symbol)}
    >
      <span className="symbol-cell">
        <strong>{pick.symbol}</strong>
        {pick.asm_gsm_tags.length > 0 && <small>{pick.asm_gsm_tags.join(", ")}</small>}
      </span>
      <span className={clsx("direction-pill", pick.direction.toLowerCase())}>
        {pick.direction}
      </span>
      <span>{formatPct(pick.probability)}</span>
      <span className={clsx("conviction-pill", pick.conviction)}>
        {convictionLabel(pick.conviction)}
      </span>
      <span>{pick.volume_x_avg.toFixed(1)}x</span>
      <span>{formatPct(pick.pct_change)}</span>
      <span>{formatPrice(pick.ltp)}</span>
      <span className="detector-cell">{pick.detectors_fired.join(", ")}</span>
    </button>
  );
}

export function PicksTable({
  picks,
  watchOnly,
  selectedSymbol,
  onSelect,
}: {
  picks: IntradayPick[];
  watchOnly: IntradayPick[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
}) {
  return (
    <div className="intraday-picks-panel">
      <div className="intraday-table-header">
        <span>Symbol</span>
        <span>Side</span>
        <span>Prob</span>
        <span>Tier</span>
        <span>Vol</span>
        <span>Move</span>
        <span>LTP</span>
        <span>Detectors</span>
      </div>

      {picks.length === 0 ? (
        <div className="intraday-empty-state">No picks yet.</div>
      ) : (
        <div className="intraday-table-body">
          {picks.map((pick) => (
            <PickRow
              key={pick.symbol}
              pick={pick}
              selected={selectedSymbol === pick.symbol}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}

      {watchOnly.length > 0 && (
        <details className="intraday-watch-only">
          <summary>Watch-only ({watchOnly.length})</summary>
          <div className="intraday-table-body">
            {watchOnly.map((pick) => (
              <PickRow
                key={pick.symbol}
                pick={pick}
                selected={selectedSymbol === pick.symbol}
                onSelect={onSelect}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
