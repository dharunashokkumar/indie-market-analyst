import { useEffect, useState } from "react";

const LOGO_BASE_URL = "https://cdn.jsdelivr.net/gh/dharunashokkumar/indian-listed-company-logos@main";

function logoExchange(symbol: string, exchange?: string): "NSE" | "BSE" {
  const upperSymbol = symbol.trim().toUpperCase();
  const upperExchange = exchange?.trim().toUpperCase();
  if (upperSymbol.endsWith(".BO") || upperExchange === "BSE") return "BSE";
  return "NSE";
}

function logoTicker(symbol: string): string {
  return symbol
    .trim()
    .toUpperCase()
    .replace(/\.(NS|BO)$/i, "")
    .replace(/^\^/, "")
    .replace(/-/g, "_");
}

function logoUrl(symbol: string, exchange?: string): string {
  const market = logoExchange(symbol, exchange);
  const ticker = logoTicker(symbol);
  const file = encodeURIComponent(`${market}_${ticker}.svg`);
  return `${LOGO_BASE_URL}/${market.toLowerCase()}/${file}`;
}

function initials(name: string, symbol: string): string {
  const src = name?.trim() || symbol;
  const words = src.split(/\s+/).filter((w) => w && !/^(limited|ltd|the|of|and|&|company|co)$/i.test(w));
  if (words.length === 0) return symbol.slice(0, 2).toUpperCase();
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function bgColour(symbol: string): string {
  // Hash symbol to a hue → consistent colour per company.
  let hash = 0;
  for (let i = 0; i < symbol.length; i++) hash = (hash * 31 + symbol.charCodeAt(i)) | 0;
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 45%, 42%)`;
}

export function CompanyLogo({
  symbol, name, size = 28, exchange,
}: {
  symbol: string;
  name?: string;
  size?: number;
  exchange?: string;
}) {
  const [failed, setFailed] = useState(false);
  const cleanSymbol = logoTicker(symbol);

  useEffect(() => { setFailed(false); }, [symbol, exchange]);

  if (failed) {
    return (
      <div
        className="company-logo company-logo-fallback"
        style={{
          width: size, height: size,
          background: bgColour(cleanSymbol),
          fontSize: Math.round(size * 0.42),
        }}
        aria-hidden
      >
        {initials(name ?? "", cleanSymbol)}
      </div>
    );
  }
  return (
    <img
      className="company-logo"
      src={logoUrl(symbol, exchange)}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
