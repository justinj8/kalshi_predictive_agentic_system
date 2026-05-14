export function fmtMoney(v?: number | null, places = 2): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  return `${sign}$${abs.toLocaleString(undefined, {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}`;
}

export function fmtPct(v?: number | null, places = 2): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `${v.toFixed(places)}%`;
}

export function fmtSignedPct(v?: number | null, places = 2): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const s = v > 0 ? "+" : "";
  return `${s}${v.toFixed(places)}%`;
}

export function fmtTicker(ticker?: string): string {
  if (!ticker) return "—";
  return ticker.length > 22 ? ticker.slice(0, 21) + "…" : ticker;
}

export function fmtTimeAgo(iso?: string): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function fmtClock(d?: Date | null): string {
  const dd = d ?? new Date();
  const hh = String(dd.getUTCHours()).padStart(2, "0");
  const mm = String(dd.getUTCMinutes()).padStart(2, "0");
  const ss = String(dd.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function fmtPrice(v?: number | null): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  // Kalshi prices stored 0..1
  return `${(v * 100).toFixed(1)}¢`;
}

export function sideColor(side?: string): string {
  if (!side) return "text-f1-gray";
  const s = side.toLowerCase();
  if (s === "yes" || s === "long") return "text-f1-mint";
  if (s === "no" || s === "short") return "text-f1-red";
  return "text-f1-chalk";
}
