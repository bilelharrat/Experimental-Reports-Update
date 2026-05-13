// Pure helpers for the public-company trader view (see
// docs/public-company-trader-view.md §6). Kept out of TraderView.vue so
// they're unit-testable from vitest.

// Per-card staleness thresholds in milliseconds. The table here is the
// authoritative spec for the colored badge on each card.
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

export const STALENESS = {
  price_card:     { fresh: 1 * HOUR_MS,  warn: 4 * HOUR_MS },
  momentum_card:  { fresh: 4 * HOUR_MS,  warn: 24 * HOUR_MS },
  sentiment_card: { fresh: 24 * HOUR_MS, warn: 7 * DAY_MS },
  heat_card:      { fresh: 6 * HOUR_MS,  warn: 24 * HOUR_MS },
  catalysts:      { fresh: 24 * HOUR_MS, warn: 7 * DAY_MS },
  trader_news:    { fresh: 6 * HOUR_MS,  warn: 24 * HOUR_MS },
};

/**
 * Given an ISO timestamp and a card name, return one of "fresh" |
 * "warn" | "stale" | "unknown".
 */
export function cardStaleness(refreshedAtISO, card) {
  if (!refreshedAtISO) return "unknown";
  const ts = Date.parse(refreshedAtISO);
  if (!Number.isFinite(ts)) return "unknown";
  const cfg = STALENESS[card];
  if (!cfg) return "unknown";
  const age = Date.now() - ts;
  if (age < cfg.fresh) return "fresh";
  if (age < cfg.warn) return "warn";
  return "stale";
}

/**
 * Color suffix the UI uses for staleness chips. "ok" maps to green-ish,
 * "warn" yellow, "stale" red.
 */
export function stalenessColor(bucket) {
  if (bucket === "fresh") return "fresh";
  if (bucket === "warn") return "warn";
  if (bucket === "stale") return "stale";
  return "unknown";
}

/**
 * Format an ISO timestamp as "8 min ago", "2h ago", "3d ago", etc.
 * Returns empty string when input is missing.
 */
export function relativeAge(iso) {
  if (!iso) return "";
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (seconds < 60) return "just now";
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 4) return `${weeks}w ago`;
  return new Date(ts).toISOString().slice(0, 10);
}

/**
 * Render a percent number as a signed string with one decimal:
 *   1.82 → "+1.8%", -3.45 → "-3.5%", 0 → "0.0%", null → "—".
 */
export function fmtPct(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const s = n.toFixed(1);
  if (n > 0) return `+${s}%`;
  return `${s}%`;
}

/**
 * Format a price with currency. Picks 2 decimals for >=1, 4 for sub-$1
 * (penny-stock display).
 */
export function fmtPrice(v, currency) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const cur = currency || "USD";
  const symbol = cur === "USD" ? "$" : "";
  const digits = n >= 1 ? 2 : 4;
  return `${symbol}${n.toFixed(digits)}`;
}

/**
 * Render a price-change sign + class hint for coloring the price card.
 *   positive → "up", negative → "down", zero/null → "flat".
 */
export function changeBias(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
}

/**
 * Compact integer formatter for analyst-distribution chips: 18 → "18".
 * (Trivial today; lives here so tests cover the contract and we can
 * swap in K/M scaling later.)
 */
export function fmtCount(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return String(Math.round(n));
}
