import { useEffect, useState } from "react";

// Curated overrides for symbols whose Clearbit domain isn't `<symbol>.com`.
const DOMAIN_HINTS: Record<string, string> = {
  RELIANCE: "ril.com",
  TCS: "tcs.com",
  INFY: "infosys.com",
  HDFCBANK: "hdfcbank.com",
  ICICIBANK: "icicibank.com",
  KOTAKBANK: "kotak.com",
  AXISBANK: "axisbank.com",
  SBIN: "sbi.co.in",
  ITC: "itcportal.com",
  HINDUNILVR: "hul.co.in",
  LT: "larsentoubro.com",
  BAJFINANCE: "bajajfinserv.in",
  BHARTIARTL: "airtel.in",
  ASIANPAINT: "asianpaints.com",
  MARUTI: "marutisuzuki.com",
  TATAMOTORS: "tatamotors.com",
  TATASTEEL: "tatasteel.com",
  WIPRO: "wipro.com",
  HCLTECH: "hcltech.com",
  TECHM: "techmahindra.com",
  ADANIENT: "adani.com",
  ADANIPORTS: "adaniports.com",
  ULTRACEMCO: "ultratechcement.com",
  NESTLEIND: "nestle.in",
  TITAN: "titancompany.in",
  SUNPHARMA: "sunpharma.com",
  POWERGRID: "powergridindia.com",
  NTPC: "ntpc.co.in",
  ONGC: "ongcindia.com",
  COALINDIA: "coalindia.in",
  M_M: "mahindra.com", // MM in NSE
  JSWSTEEL: "jsw.in",
  GRASIM: "grasim.com",
  DRREDDY: "drreddys.com",
  CIPLA: "cipla.com",
  EICHERMOT: "eichermotors.com",
  HEROMOTOCO: "heromotocorp.com",
  BAJAJ_AUTO: "bajajauto.com",
  BAJAJFINSV: "bajajfinserv.in",
  DIVISLAB: "divislabs.com",
  BRITANNIA: "britannia.co.in",
  INDUSINDBK: "indusind.com",
  TATACONSUM: "tataconsumer.com",
  HDFCLIFE: "hdfclife.com",
  SBILIFE: "sbilife.co.in",
  UPL: "upl-ltd.com",
  APOLLOHOSP: "apollohospitals.com",
  PIDILITIND: "pidilite.com",
  DABUR: "dabur.com",
  GODREJCP: "godrejcp.com",
};

function logoUrl(symbol: string): string {
  const key = symbol.replace(/[-&]/g, "_").toUpperCase();
  const domain = DOMAIN_HINTS[key] ?? `${symbol.toLowerCase()}.com`;
  return `https://logo.clearbit.com/${domain}`;
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
  symbol, name, size = 28,
}: {
  symbol: string;
  name?: string;
  size?: number;
}) {
  const [failed, setFailed] = useState(false);
  // Reset on symbol change
  useEffect(() => { setFailed(false); }, [symbol]);

  if (failed) {
    return (
      <div
        className="company-logo company-logo-fallback"
        style={{
          width: size, height: size,
          background: bgColour(symbol),
          fontSize: Math.round(size * 0.42),
        }}
        aria-hidden
      >
        {initials(name ?? "", symbol)}
      </div>
    );
  }
  return (
    <img
      className="company-logo"
      src={logoUrl(symbol)}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
