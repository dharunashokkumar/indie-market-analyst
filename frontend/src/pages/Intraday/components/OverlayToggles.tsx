export type OverlayState = {
  vwap: boolean;
  orb: boolean;
  prevDay: boolean;
  ma20: boolean;
  ma50: boolean;
  volume: boolean;
  pivots: boolean;
};

export const DEFAULT_OVERLAYS: OverlayState = {
  vwap: true,
  orb: true,
  prevDay: true,
  ma20: true,
  ma50: true,
  volume: true,
  pivots: true,
};

const OPTIONS: { key: keyof OverlayState; label: string }[] = [
  { key: "vwap", label: "VWAP" },
  { key: "orb", label: "ORB H/L" },
  { key: "prevDay", label: "Prev H/L" },
  { key: "ma20", label: "20-DMA" },
  { key: "ma50", label: "50-DMA" },
  { key: "volume", label: "Volume MA" },
  { key: "pivots", label: "Pivots" },
];

export function OverlayToggles({
  value,
  onChange,
}: {
  value: OverlayState;
  onChange: (value: OverlayState) => void;
}) {
  return (
    <div className="intraday-overlay-toggles">
      {OPTIONS.map((option) => (
        <label key={option.key}>
          <input
            type="checkbox"
            checked={value[option.key]}
            onChange={(event) => (
              onChange({ ...value, [option.key]: event.target.checked })
            )}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </div>
  );
}
