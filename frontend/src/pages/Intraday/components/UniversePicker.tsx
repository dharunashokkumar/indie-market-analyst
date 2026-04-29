import { useEffect, useMemo, useState } from "react";
import {
  getIntradayUniverses,
  type IntradayUniverse,
  type IntradayUniverseOption,
} from "../../../lib/api";

const FALLBACK_UNIVERSES: IntradayUniverseOption[] = [
  {
    id: "nifty50",
    label: "Nifty 50",
    description: "Large-cap Nifty 50 constituents.",
    size: 50,
    available: true,
    source: "static_csv",
    static_path: null,
    merge_movers_default: true,
  },
  {
    id: "nifty200",
    label: "Nifty 200",
    description: "Nifty 200 broad large and mid-cap universe.",
    size: 200,
    available: true,
    source: "static_csv",
    static_path: null,
    merge_movers_default: true,
  },
  {
    id: "nifty500",
    label: "Nifty 500",
    description: "Broad Nifty 500 cash-equity universe.",
    size: 500,
    available: true,
    source: "static_csv",
    static_path: null,
    merge_movers_default: true,
  },
  {
    id: "fno",
    label: "F&O list",
    description: "NSE cash symbols with active equity derivatives eligibility.",
    size: 0,
    available: true,
    source: "static_csv",
    static_path: null,
    merge_movers_default: true,
  },
  {
    id: "full_nse",
    label: "Full NSE cash",
    description: "All checked-in NSE cash-equity symbols.",
    size: 0,
    available: true,
    source: "local_csv",
    static_path: null,
    merge_movers_default: true,
  },
  {
    id: "custom_csv",
    label: "Custom CSV",
    description: "User-provided CSV with at least a symbol column.",
    size: 0,
    available: false,
    source: "custom_csv",
    static_path: null,
    merge_movers_default: true,
  },
];

export function UniversePicker({
  value,
  onChange,
  disabled = false,
  showMeta = true,
}: {
  value: IntradayUniverse;
  onChange: (value: IntradayUniverse) => void;
  disabled?: boolean;
  showMeta?: boolean;
}) {
  const [options, setOptions] = useState<IntradayUniverseOption[]>(FALLBACK_UNIVERSES);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const rows = await getIntradayUniverses();
        if (active && rows.length) {
          setOptions(rows);
        }
      } catch {
        if (active) setOptions(FALLBACK_UNIVERSES);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  const selected = useMemo(
    () => options.find((option) => option.id === value),
    [options, value],
  );

  return (
    <div className="intraday-universe-picker">
      <select
        value={value}
        disabled={disabled || loading}
        onChange={(event) => onChange(event.target.value as IntradayUniverse)}
      >
        {options.map((option) => (
          <option key={option.id} value={option.id} disabled={!option.available}>
            {option.label}
            {option.size ? ` (${option.size.toLocaleString()})` : ""}
          </option>
        ))}
      </select>
      {showMeta && selected && (
        <div className="intraday-field-hint">
          {selected.available ? selected.description : "CSV not uploaded yet"}
        </div>
      )}
    </div>
  );
}
