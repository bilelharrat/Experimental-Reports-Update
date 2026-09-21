/**
 * US market brief helpers for Pulse — indexes, sector ETFs, breadth, and
 * movers assembled from live quotes + Nasdaq screeners.
 */

import {
  MARKET_INDEX_TICKERS,
  WEI_TICKERS,
  indexQuoteCards,
  quoteBoardRows,
  quoteGainers,
  quoteLosers,
  quoteMostActive,
} from "./homeDesk.js";

/** Core US indexes + style factors for the Pulse tape. */
export const PULSE_INDEX_TICKERS = [
  { ticker: "SPY", label: "S&P 500" },
  { ticker: "QQQ", label: "Nasdaq 100" },
  { ticker: "DIA", label: "Dow 30" },
  { ticker: "IWM", label: "Russell 2000" },
  { ticker: "RSP", label: "Equal-weight S&P" },
  { ticker: "MTUM", label: "Momentum" },
  { ticker: "VLUE", label: "Value" },
  { ticker: "USMV", label: "Min vol" },
];

/** GICS sector ETF proxies (SPDR Select). */
export const PULSE_SECTOR_ETFS = [
  { ticker: "XLK", label: "Technology" },
  { ticker: "XLF", label: "Financials" },
  { ticker: "XLE", label: "Energy" },
  { ticker: "XLV", label: "Health Care" },
  { ticker: "XLI", label: "Industrials" },
  { ticker: "XLY", label: "Consumer Disc." },
  { ticker: "XLP", label: "Consumer Staples" },
  { ticker: "XLU", label: "Utilities" },
  { ticker: "XLB", label: "Materials" },
  { ticker: "XLRE", label: "Real Estate" },
  { ticker: "XLC", label: "Communication" },
];

export const PULSE_MACRO_TICKERS = [
  { ticker: "TLT", label: "Long bonds" },
  { ticker: "IEF", label: "7–10y Treasuries" },
  { ticker: "HYG", label: "HY credit" },
  { ticker: "LQD", label: "IG credit" },
  { ticker: "UUP", label: "US Dollar" },
  { ticker: "USO", label: "Crude oil" },
  { ticker: "GLD", label: "Gold" },
  { ticker: "VIXY", label: "Vol" },
  { ticker: "BITO", label: "Bitcoin" },
];

export function pulseQuoteUniverse() {
  const seen = new Set();
  const out = [];
  for (const def of [
    ...PULSE_INDEX_TICKERS,
    ...PULSE_SECTOR_ETFS,
    ...PULSE_MACRO_TICKERS,
    ...MARKET_INDEX_TICKERS,
  ]) {
    const ticker = String(def.ticker || "").toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    out.push(ticker);
  }
  for (const ticker of WEI_TICKERS) {
    const symbol = String(ticker || "").toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
  }
  return out;
}

export function sectorRotationRows(quotes = {}, defs = PULSE_SECTOR_ETFS) {
  return indexQuoteCards(quotes, defs)
    .filter((row) => row.last != null)
    .sort((a, b) => (b.change ?? -Infinity) - (a.change ?? -Infinity));
}

export function macroTapeRows(quotes = {}, defs = PULSE_MACRO_TICKERS) {
  return indexQuoteCards(quotes, defs);
}

export function styleFactorRows(quotes = {}) {
  return indexQuoteCards(quotes, PULSE_INDEX_TICKERS);
}

// The Nasdaq screener (/api/quotes/screeners) sends `change_pct`; quote rows
// send `change_pct_1d`. Reading only the latter counted every screener row as
// missing, so Pulse showed 0 advancers and 0 decliners on a normal day.
function dayChange(row) {
  const value = row?.change_pct_1d ?? row?.change_pct;
  return value == null || value === "" ? NaN : Number(value);
}

export function marketBreadthFromUniverse(universe = []) {
  const rows = (universe || []).filter((row) => Number.isFinite(dayChange(row)));
  let up = 0;
  let down = 0;
  let flat = 0;
  let nearHigh = 0;
  let withHigh = 0;
  for (const row of rows) {
    const change = dayChange(row);
    if (change > 0.05) up += 1;
    else if (change < -0.05) down += 1;
    else flat += 1;
    const last = Number(row.last_price ?? row.last);
    const high = Number(row.high_52w ?? row.year_high);
    if (Number.isFinite(last) && Number.isFinite(high) && high > 0) {
      withHigh += 1;
      if (last / high >= 0.95) nearHigh += 1;
    }
  }
  const total = rows.length;
  return {
    total,
    up,
    down,
    flat,
    nearHigh,
    advanceDecline: down > 0 ? up / down : up > 0 ? up : null,
    pctUp: total ? (up / total) * 100 : null,
    // Only over rows that carry a 52-week high: the screener has none, and
    // "0% near highs" would be a claim, not an absence of data.
    pctNearHigh: withHigh ? (nearHigh / withHigh) * 100 : null,
  };
}

export function screenerMoverLists(screeners = {}, limit = 8) {
  const gainers = (screeners.gainers || []).slice(0, limit);
  const losers = (screeners.losers || []).slice(0, limit);
  const active = (screeners.active || screeners.most_active || []).slice(0, limit);
  return { gainers, losers, active };
}

export function quoteMoverLists(quotes = {}, companies = [], limit = 8) {
  const rows = quoteBoardRows(quotes, companies);
  return {
    gainers: quoteGainers(rows, limit),
    losers: quoteLosers(rows, limit),
    active: quoteMostActive(rows, limit),
  };
}

export function calendarWeekBuckets(events = [], now = new Date()) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const day = start.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  start.setDate(start.getDate() + mondayOffset);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
  const byDay = days.map((d) => {
    const key = d.toISOString().slice(0, 10);
    return {
      date: key,
      label: d.toLocaleDateString(undefined, { weekday: "short", month: "2-digit", day: "2-digit" }),
      events: [],
    };
  });
  const index = new Map(byDay.map((row) => [row.date, row]));
  for (const event of events || []) {
    const key = String(event?.date || "").slice(0, 10);
    const bucket = index.get(key);
    if (bucket) bucket.events.push(event);
  }
  return byDay;
}

export function postureFromBreadth(breadth = {}, spyChange = null) {
  const pctUp = breadth.pctUp;
  const spy = Number(spyChange);
  if (Number.isFinite(pctUp) && pctUp >= 62 && (!Number.isFinite(spy) || spy >= 0)) {
    return "risk_on";
  }
  if (Number.isFinite(pctUp) && pctUp <= 38 && (!Number.isFinite(spy) || spy <= 0)) {
    return "risk_off";
  }
  if (Number.isFinite(pctUp) && Number.isFinite(spy) && ((pctUp >= 55 && spy < 0) || (pctUp <= 45 && spy > 0))) {
    return "mixed";
  }
  return "neutral";
}

export function rankedSignalSlice(payload, limit = 8) {
  const signals = payload?.sections?.ranked_signals || [];
  return signals.slice(0, limit);
}

export function changedSinceSlice(payload) {
  return payload?.sections?.changed_since_last_week || {};
}

/**
 * Outcome stats for the signal ledger: how many scored calls landed.
 *
 * A call is "scored" when the server attached `score_pct` (positive means
 * the direction was right — bearish calls invert the raw move). Watch
 * entries and entries without prices are counted but not scored.
 */
export function ledgerHitStats(entries = []) {
  const scored = (entries || []).filter(
    (row) => Number.isFinite(Number(row?.score_pct)),
  );
  const hits = scored.filter((row) => Number(row.score_pct) > 0);
  const avgScore = scored.length
    ? scored.reduce((sum, row) => sum + Number(row.score_pct), 0) / scored.length
    : null;
  return {
    total: (entries || []).length,
    scored: scored.length,
    hits: hits.length,
    hitRate: scored.length ? (hits.length / scored.length) * 100 : null,
    avgScore,
  };
}

/**
 * Reading time for a brief, in whole minutes (at least one). English reads
 * at ~230 words a minute; Chinese has no spaces to count, so it is measured
 * in characters at ~400 a minute.
 */
export function briefReadMinutes(parts = [], lang = "en") {
  const text = (parts || []).filter(Boolean).join(" ");
  if (!text.trim()) return 0;
  const units =
    lang === "zh"
      ? (text.match(/[㐀-鿿]/g) || []).length
      : text.split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(units / (lang === "zh" ? 400 : 230)));
}
