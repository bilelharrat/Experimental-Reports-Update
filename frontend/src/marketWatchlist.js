/** Shared Market pins, heuristic alerts, and user alert rules. */

import { scheduleDeskSync } from "./deskSync.js";

const PINNED_KEY = "bsh.marketPinnedTickers";
const RULES_KEY = "bsh.marketAlertRules";
const HP_KEY = "bsh.marketHpCompare";
/** Same symbol rule the server applies to quotes and to saved desk prefs. */
export const TICKER_RE = /^[A-Z0-9][A-Z0-9.-]{0,15}$/;

function readPinned() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(PINNED_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .map((ticker) => String(ticker || "").trim().toUpperCase())
      .filter((ticker) => TICKER_RE.test(ticker));
  } catch {
    return [];
  }
}

function writePinned(tickers) {
  try {
    window.localStorage.setItem(PINNED_KEY, JSON.stringify([...tickers]));
  } catch {
    // ignore
  }
  scheduleDeskSync();
}

export function loadPinnedTickers() {
  return readPinned();
}

export function togglePinnedTicker(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!TICKER_RE.test(symbol)) return readPinned();
  const next = new Set(readPinned());
  if (next.has(symbol)) next.delete(symbol);
  else next.add(symbol);
  const list = [...next];
  writePinned(list);
  return list;
}

export function isPinnedTicker(ticker, pinned = readPinned()) {
  return pinned.includes(String(ticker || "").trim().toUpperCase());
}

/** Light alert heuristics for watchlist rows that already have quotes. */
export function watchlistAlerts(rows = []) {
  const alerts = [];
  for (const row of rows || []) {
    const change = Number(row?.change);
    const last = Number(row?.last);
    const high = Number(row?.weekHigh);
    const low = Number(row?.weekLow);
    if (Number.isFinite(change) && Math.abs(change) >= 5) {
      alerts.push({
        ticker: row.ticker,
        kind: change >= 0 ? "gap_up" : "gap_down",
        change,
      });
    }
    if (
      Number.isFinite(last) &&
      Number.isFinite(high) &&
      Number.isFinite(low) &&
      high > low
    ) {
      const pct = ((last - low) / (high - low)) * 100;
      if (pct >= 97) alerts.push({ ticker: row.ticker, kind: "near_high", pct });
      if (pct <= 3) alerts.push({ ticker: row.ticker, kind: "near_low", pct });
    }
  }
  return alerts.slice(0, 8);
}

function normalizeRule(row) {
  const ticker = String(row?.ticker || "").trim().toUpperCase();
  const kind = String(row?.kind || "").trim().toLowerCase();
  if (!ticker || !["pct", "earnings", "volume", "price", "sma_cross"].includes(kind)) {
    return null;
  }
  const threshold = Number(row?.threshold);
  const window = Number(row?.window);
  return {
    id: String(row?.id || `${ticker}-${kind}-${Date.now()}`),
    ticker,
    kind,
    threshold: Number.isFinite(threshold) ? threshold : defaultThreshold(kind),
    window: Number.isFinite(window) && window > 0 ? window : kind === "sma_cross" ? 50 : null,
    direction: String(row?.direction || "above").toLowerCase() === "below" ? "below" : "above",
    enabled: row?.enabled !== false,
  };
}

function defaultThreshold(kind) {
  if (kind === "pct") return 5;
  if (kind === "earnings") return 3;
  if (kind === "volume") return 2;
  if (kind === "price") return 0;
  if (kind === "sma_cross") return 50;
  return 0;
}

function readRules() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(RULES_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw.map(normalizeRule).filter(Boolean);
  } catch {
    return [];
  }
}

function writeRules(rules) {
  try {
    window.localStorage.setItem(RULES_KEY, JSON.stringify(rules));
  } catch {
    // ignore
  }
  scheduleDeskSync();
}

export function loadAlertRules() {
  return readRules();
}

export function upsertAlertRule(rule) {
  const nextRule = normalizeRule(rule);
  if (!nextRule) return readRules();
  const rest = readRules().filter(
    (row) => !(row.ticker === nextRule.ticker && row.kind === nextRule.kind),
  );
  const next = [nextRule, ...rest].slice(0, 40);
  writeRules(next);
  return next;
}

export function removeAlertRule(id) {
  const next = readRules().filter((row) => row.id !== id);
  writeRules(next);
  return next;
}

export function ensureDefaultAlertRules(tickers = []) {
  const existing = readRules();
  const have = new Set(existing.map((row) => `${row.ticker}:${row.kind}`));
  let changed = false;
  const next = [...existing];
  for (const ticker of tickers || []) {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol) continue;
    for (const kind of ["pct", "earnings", "volume"]) {
      const key = `${symbol}:${kind}`;
      if (have.has(key)) continue;
      next.push(
        normalizeRule({
          ticker: symbol,
          kind,
          threshold: defaultThreshold(kind),
          id: `${symbol}-${kind}`,
        }),
      );
      have.add(key);
      changed = true;
    }
  }
  if (changed) writeRules(next.slice(0, 40));
  return readRules();
}

/**
 * Evaluate user rules against watchlist rows + optional earnings / chart maps.
 * earningsByTicker: { NVDA: "2026-09-12" }
 * chartPointsByTicker: { NVDA: [{close, ...}] }
 */
export function evaluateAlertRules(
  rows = [],
  rules = [],
  { earningsByTicker = {}, chartPointsByTicker = {}, now = Date.now() } = {},
) {
  const byTicker = new Map(
    (rows || []).map((row) => [String(row.ticker || "").toUpperCase(), row]),
  );
  const alerts = [];
  for (const rule of rules || []) {
    if (!rule?.enabled) continue;
    const row = byTicker.get(rule.ticker);
    if (!row) continue;
    if (rule.kind === "pct") {
      const change = Number(row.change);
      if (Number.isFinite(change) && Math.abs(change) >= Number(rule.threshold)) {
        alerts.push({
          ticker: rule.ticker,
          kind: change >= 0 ? "rule_pct_up" : "rule_pct_down",
          change,
          threshold: rule.threshold,
          ruleId: rule.id,
        });
      }
    } else if (rule.kind === "volume") {
      const volume = Number(row.volume);
      const avg = Number(row.avgVolume);
      const mult = Number(rule.threshold) || 2;
      if (Number.isFinite(volume) && Number.isFinite(avg) && avg > 0 && volume >= avg * mult) {
        alerts.push({
          ticker: rule.ticker,
          kind: "rule_volume",
          volume,
          avgVolume: avg,
          threshold: mult,
          ruleId: rule.id,
        });
      }
    } else if (rule.kind === "earnings") {
      const dateStr = earningsByTicker[rule.ticker];
      if (!dateStr) continue;
      const stamp = Date.parse(dateStr);
      if (!Number.isFinite(stamp)) continue;
      const days = Math.ceil((stamp - now) / 86400000);
      if (days >= 0 && days <= Number(rule.threshold)) {
        alerts.push({
          ticker: rule.ticker,
          kind: "rule_earnings",
          days,
          date: String(dateStr).slice(0, 10),
          threshold: rule.threshold,
          ruleId: rule.id,
        });
      }
    } else if (rule.kind === "price") {
      const last = Number(row.last);
      const level = Number(rule.threshold);
      if (!Number.isFinite(last) || !Number.isFinite(level)) continue;
      const hit = rule.direction === "below" ? last <= level : last >= level;
      if (hit) {
        alerts.push({
          ticker: rule.ticker,
          kind: rule.direction === "below" ? "rule_price_below" : "rule_price_above",
          last,
          threshold: level,
          ruleId: rule.id,
        });
      }
    } else if (rule.kind === "sma_cross") {
      const points = chartPointsByTicker[rule.ticker] || [];
      const window = Number(rule.window) || Number(rule.threshold) || 50;
      const last = Number(row.last ?? points[points.length - 1]?.close);
      if (!Number.isFinite(last) || points.length < window) continue;
      let sum = 0;
      let count = 0;
      for (let i = points.length - window; i < points.length; i += 1) {
        const close = Number(points[i]?.close);
        if (!Number.isFinite(close)) continue;
        sum += close;
        count += 1;
      }
      if (count < window) continue;
      const sma = sum / count;
      const prevClose = Number(points[points.length - 2]?.close);
      const prevSlice = points.slice(-(window + 1), -1);
      let prevSum = 0;
      let prevCount = 0;
      for (const point of prevSlice) {
        const close = Number(point?.close);
        if (!Number.isFinite(close)) continue;
        prevSum += close;
        prevCount += 1;
      }
      const prevSma = prevCount ? prevSum / prevCount : null;
      const aboveNow = last >= sma;
      const abovePrev =
        Number.isFinite(prevClose) && Number.isFinite(prevSma) ? prevClose >= prevSma : null;
      const crossed =
        abovePrev == null
          ? rule.direction === "below"
            ? last <= sma
            : last >= sma
          : rule.direction === "below"
            ? abovePrev && !aboveNow
            : !abovePrev && aboveNow;
      if (crossed) {
        alerts.push({
          ticker: rule.ticker,
          kind: rule.direction === "below" ? "rule_sma_below" : "rule_sma_above",
          last,
          sma,
          window,
          threshold: window,
          ruleId: rule.id,
        });
      }
    }
  }
  return alerts.slice(0, 16);
}

export function mergeAlerts(...lists) {
  const seen = new Set();
  const out = [];
  for (const list of lists) {
    for (const alert of list || []) {
      const key = `${alert.ticker}:${alert.kind}:${alert.ruleId || ""}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(alert);
    }
  }
  return out.slice(0, 16);
}

/** HP compare tickers persisted beside pins. */
export function loadHpCompare() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(HP_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .map((ticker) => String(ticker || "").trim().toUpperCase())
      .filter(Boolean)
      .slice(0, 4);
  } catch {
    return [];
  }
}

export function saveHpCompare(tickers = []) {
  const list = [...new Set(
    (tickers || [])
      .map((ticker) => String(ticker || "").trim().toUpperCase())
      .filter(Boolean),
  )].slice(0, 4);
  try {
    window.localStorage.setItem(HP_KEY, JSON.stringify(list));
  } catch {
    // ignore
  }
  scheduleDeskSync();
  return list;
}

export function toggleHpCompare(ticker, current = loadHpCompare()) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return current;
  const set = new Set(current);
  if (set.has(symbol)) set.delete(symbol);
  else if (set.size < 4) set.add(symbol);
  return saveHpCompare([...set]);
}

const GROUPS_KEY = "bsh.marketPinGroups";
export const WATCH_GROUPS = ["Core", "Risk", "Macro", "Default"];

function readGroups() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(GROUPS_KEY) || "{}");
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    const out = {};
    for (const [ticker, group] of Object.entries(raw)) {
      const symbol = String(ticker || "").trim().toUpperCase();
      const label = String(group || "Default").trim() || "Default";
      if (symbol) out[symbol] = label;
    }
    return out;
  } catch {
    return {};
  }
}

function writeGroups(map) {
  try {
    window.localStorage.setItem(GROUPS_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
  scheduleDeskSync();
}

export function loadPinGroups() {
  return readGroups();
}

export function setPinGroup(ticker, group = "Default") {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return readGroups();
  const next = { ...readGroups() };
  next[symbol] = String(group || "Default").trim() || "Default";
  writeGroups(next);
  return next;
}

export function pinGroupFor(ticker, groups = readGroups()) {
  const symbol = String(ticker || "").trim().toUpperCase();
  return groups[symbol] || "Default";
}

export function groupPinnedTickers(tickers = [], groups = readGroups()) {
  const buckets = new Map(WATCH_GROUPS.map((name) => [name, []]));
  for (const ticker of tickers || []) {
    const symbol = String(ticker || "").trim().toUpperCase();
    if (!symbol) continue;
    const group = pinGroupFor(symbol, groups);
    if (!buckets.has(group)) buckets.set(group, []);
    buckets.get(group).push(symbol);
  }
  return [...buckets.entries()]
    .filter(([, list]) => list.length)
    .map(([group, list]) => ({ group, tickers: list }));
}
