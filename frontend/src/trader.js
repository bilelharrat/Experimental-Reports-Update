// Pure helpers for the public-company trader view (see
// docs/public-company-trader-view.md §6). Kept out of TraderView.vue so
// they're unit-testable from vitest.

import { sessionStaleness } from "./marketCalendar.js";

// Freshness is measured in *trading sessions*, not wall-clock. A
// snapshot stays "fresh" until the next NYSE session close after it was
// generated — so a run after Friday's close is good through Monday's
// close, and weekends/holidays don't count. See marketCalendar.js.
//
// Cards are still listed so the UI can iterate them and keep a per-card
// badge; the rule itself is unified (one snapshot, one session age).
export const STALENESS = {
  price_card: { sessions: 1 },
  momentum_card: { sessions: 1 },
  sentiment_card: { sessions: 1 },
  heat_card: { sessions: 1 },
  catalysts: { sessions: 1 },
  trader_news: { sessions: 1 },
};

/**
 * Given an ISO timestamp, a card name (kept for API stability), and the
 * snapshot's optional authoritative `market_session`, return "fresh" |
 * "warn" | "stale" | "unknown" based on how many trading sessions have
 * closed since the snapshot was generated.
 */
export function cardStaleness(refreshedAtISO, card, marketSession = null) {
  if (card && !STALENESS[card]) return "unknown";
  return sessionStaleness(refreshedAtISO, { marketSession });
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
