/** Client-side Market analytics: returns, gaps, breadth, pairs, calendar grids. */

import { movingAverage, relativeStrength } from "./quoteChart.js";

const MS_DAY = 86_400_000;

export const RETURN_LADDER_WINDOWS = [
  { id: "1d", labelKey: "radar.ret_1d", days: 1 },
  { id: "1w", labelKey: "radar.ret_1w", days: 7 },
  { id: "1m", labelKey: "radar.ret_1m", days: 30 },
  { id: "3m", labelKey: "radar.ret_3m", days: 90 },
  { id: "ytd", labelKey: "radar.ret_ytd", days: null },
  { id: "1y", labelKey: "radar.ret_1y", days: 365 },
  { id: "3y", labelKey: "radar.ret_3y", days: 365 * 3 },
];

function closeAtOrBefore(points, targetTs) {
  let best = null;
  for (const point of points || []) {
    const t = Number(point?.t);
    const close = Number(point?.close);
    if (!Number.isFinite(t) || !Number.isFinite(close)) continue;
    if (t <= targetTs) best = close;
  }
  return best;
}

export function periodReturn(points = [], { days = null, ytd = false, now = Date.now() } = {}) {
  const series = (points || [])
    .map((point) => ({ t: Number(point?.t), close: Number(point?.close) }))
    .filter((row) => Number.isFinite(row.t) && Number.isFinite(row.close));
  if (series.length < 2) return null;
  const last = series[series.length - 1].close;
  let startClose = null;
  if (ytd) {
    const year = new Date(now).getUTCFullYear();
    const ytdTs = Date.UTC(year, 0, 1) / 1000;
    startClose = closeAtOrBefore(series, ytdTs) ?? series[0].close;
  } else if (Number.isFinite(days) && days > 0) {
    const target = series[series.length - 1].t - days * 86_400;
    startClose = closeAtOrBefore(series, target);
    if (startClose == null) startClose = series[0].close;
  } else {
    startClose = series[0].close;
  }
  if (!Number.isFinite(startClose) || startClose === 0) return null;
  return ((last - startClose) / startClose) * 100;
}

/** Multi-horizon return ladder from chart points (+ optional peer API overrides). */
export function returnLadder(points = [], overrides = {}, { now = Date.now() } = {}) {
  return RETURN_LADDER_WINDOWS.map((window) => {
    const override = overrides[window.id];
    const value =
      Number.isFinite(Number(override))
        ? Number(override)
        : periodReturn(points, {
            days: window.days,
            ytd: window.id === "ytd",
            now,
          });
    return { id: window.id, labelKey: window.labelKey, value };
  });
}

/** Prior-close → open gap vs open → last session move. */
export function gapSplit({ open, previousClose, last } = {}) {
  const o = Number(open);
  const prev = Number(previousClose);
  const close = Number(last);
  const gap =
    Number.isFinite(o) && Number.isFinite(prev) && prev !== 0
      ? ((o - prev) / prev) * 100
      : null;
  const gapPts =
    Number.isFinite(o) && Number.isFinite(prev) ? o - prev : null;
  const session =
    Number.isFinite(close) && Number.isFinite(o) && o !== 0
      ? ((close - o) / o) * 100
      : null;
  const sessionPts =
    Number.isFinite(close) && Number.isFinite(o) ? close - o : null;
  const day =
    Number.isFinite(close) && Number.isFinite(prev) && prev !== 0
      ? ((close - prev) / prev) * 100
      : null;
  return { gap, gapPts, session, sessionPts, day, open: o, previousClose: prev, last: close };
}

/** Price-bucket volume profile for session charts. */
export function volumeProfile(points = [], { buckets = 16 } = {}) {
  const rows = (points || [])
    .map((point) => ({
      price: Number(point?.close ?? point?.high ?? point?.low),
      volume: Number(point?.volume),
    }))
    .filter((row) => Number.isFinite(row.price) && Number.isFinite(row.volume) && row.volume > 0);
  if (!rows.length) return [];
  const prices = rows.map((row) => row.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;
  const n = Math.max(4, Math.min(48, Number(buckets) || 16));
  const counts = Array.from({ length: n }, (_, index) => ({
    index,
    low: min + (span * index) / n,
    high: min + (span * (index + 1)) / n,
    volume: 0,
    mid: min + (span * (index + 0.5)) / n,
  }));
  for (const row of rows) {
    let idx = Math.floor(((row.price - min) / span) * n);
    if (idx >= n) idx = n - 1;
    if (idx < 0) idx = 0;
    counts[idx].volume += row.volume;
  }
  const maxVol = Math.max(...counts.map((row) => row.volume), 1);
  return counts.map((row) => ({
    ...row,
    share: row.volume / maxVol,
    pct: (row.volume / maxVol) * 100,
  }));
}

/** Session VWAP ± 1/2σ bands from typical price / volume. */
export function vwapBands(points = []) {
  let pv = 0;
  let vol = 0;
  let p2v = 0;
  const series = [];
  for (const point of points || []) {
    const high = Number(point?.high);
    const low = Number(point?.low);
    const close = Number(point?.close);
    const volume = Number(point?.volume);
    const typical =
      [high, low, close].every(Number.isFinite) ? (high + low + close) / 3 : close;
    if (!Number.isFinite(typical)) {
      series.push({ vwap: vol > 0 ? pv / vol : null, upper1: null, lower1: null, upper2: null, lower2: null });
      continue;
    }
    if (Number.isFinite(volume) && volume > 0) {
      pv += typical * volume;
      p2v += typical * typical * volume;
      vol += volume;
    }
    const vwap = vol > 0 ? pv / vol : null;
    const variance = vol > 0 ? p2v / vol - (vwap ?? 0) ** 2 : 0;
    const sigma = variance > 0 ? Math.sqrt(variance) : 0;
    series.push({
      vwap,
      upper1: vwap != null ? vwap + sigma : null,
      lower1: vwap != null ? vwap - sigma : null,
      upper2: vwap != null ? vwap + 2 * sigma : null,
      lower2: vwap != null ? vwap - 2 * sigma : null,
      sigma,
    });
  }
  return series;
}

/** Aligned A−B or A/B pair series from two OHLC point lists. */
export function pairSpreadSeries(pointsA = [], pointsB = [], { mode = "diff" } = {}) {
  const mapB = new Map();
  for (const point of pointsB || []) {
    const t = Number(point?.t);
    const close = Number(point?.close);
    if (Number.isFinite(t) && Number.isFinite(close)) mapB.set(t, close);
  }
  const out = [];
  for (const point of pointsA || []) {
    const t = Number(point?.t);
    const a = Number(point?.close);
    const b = mapB.get(t);
    if (!Number.isFinite(t) || !Number.isFinite(a) || !Number.isFinite(b)) continue;
    let value = null;
    if (mode === "ratio") value = b !== 0 ? a / b : null;
    else value = a - b;
    if (!Number.isFinite(value)) continue;
    out.push({ t, close: value, open: value, high: value, low: value, volume: null });
  }
  return out;
}

/** Watchlist breadth: advancers, above SMA50, near 52w highs. */
export function breadthStrip(rows = [], chartPointsByTicker = {}, { smaWindow = 50 } = {}) {
  const list = rows || [];
  let advancers = 0;
  let decliners = 0;
  let unchanged = 0;
  let aboveSma = 0;
  let smaSamples = 0;
  let nearHigh = 0;
  let nearLow = 0;
  let highSamples = 0;
  for (const row of list) {
    const change = Number(row?.change);
    if (Number.isFinite(change)) {
      if (change > 0.05) advancers += 1;
      else if (change < -0.05) decliners += 1;
      else unchanged += 1;
    }
    const points = chartPointsByTicker[row?.ticker] || [];
    if (points.length >= smaWindow) {
      const sma = movingAverage(points, smaWindow);
      const lastSma = sma[sma.length - 1];
      const last = Number(row?.last ?? points[points.length - 1]?.close);
      if (Number.isFinite(lastSma) && Number.isFinite(last)) {
        smaSamples += 1;
        if (last >= lastSma) aboveSma += 1;
      }
    }
    const high = Number(row?.weekHigh);
    const low = Number(row?.weekLow);
    const last = Number(row?.last);
    if (Number.isFinite(high) && Number.isFinite(low) && Number.isFinite(last) && high > low) {
      highSamples += 1;
      const pos = (last - low) / (high - low);
      if (pos >= 0.95) nearHigh += 1;
      if (pos <= 0.05) nearLow += 1;
    }
  }
  const total = list.length || 1;
  return {
    count: list.length,
    advancers,
    decliners,
    unchanged,
    advancePct: (advancers / total) * 100,
    aboveSma,
    aboveSmaPct: smaSamples ? (aboveSma / smaSamples) * 100 : null,
    nearHigh,
    nearLow,
    nearHighPct: highSamples ? (nearHigh / highSamples) * 100 : null,
  };
}

/** Match workspace research / news / companies for a ticker. */
export function researchHitsForTicker({
  ticker = "",
  name = "",
  news = [],
  research = [],
  companies = [],
  limit = 8,
} = {}) {
  const symbol = String(ticker || "").trim().toUpperCase();
  const needle = String(name || "").trim().toLowerCase();
  const hits = [];
  const push = (row) => {
    if (!row || hits.length >= limit) return;
    if (hits.some((item) => item.id === row.id)) return;
    hits.push(row);
  };
  for (const company of companies || []) {
    const ct = String(company?.ticker || "").trim().toUpperCase();
    if (symbol && ct === symbol) {
      push({
        id: `company:${company.id}`,
        kind: "company",
        title: company.name || ct,
        subtitle: ct,
        companyId: company.id,
        href: null,
      });
    }
  }
  const matchText = (row) => {
    const text = `${row?.title || ""} ${row?.summary || ""} ${row?.ticker || ""}`.toUpperCase();
    const hay = `${row?.title || ""} ${row?.summary || ""}`.toLowerCase();
    if (symbol && (text.includes(symbol) || String(row?.ticker || "").toUpperCase() === symbol)) {
      return true;
    }
    if (needle && needle.length >= 3 && hay.includes(needle)) return true;
    return false;
  };
  for (const item of research || []) {
    if (!matchText(item)) continue;
    push({
      id: `research:${item.id || item.url || item.title}`,
      kind: "research",
      title: item.title || item.name || "Research",
      subtitle: item.source || item.publisher || "",
      url: item.url || item.link || null,
      companyId: item.company_id || item.companyId || null,
      ts: item.ts || item.captured_at || null,
    });
  }
  for (const item of news || []) {
    if (!matchText(item)) continue;
    push({
      id: `news:${item.id || item.url || item.title}`,
      kind: "news",
      title: item.title || "Headline",
      subtitle: item.source || "",
      url: item.url || item.link || null,
      companyId: item.company_id || item.companyId || null,
      ts: item.ts || item.captured_at || null,
    });
  }
  return hits;
}

const FILING_FORM_RE = /\b(10-?K|10-?Q|8-?K|6-?K|20-?F|S-1|13[DFG]|DEF\s*14A|SC\s*13[DG]|4\b|3\b)\b/i;

export function taggingFilingSnips(rows = [], { ticker = "", name = "", limit = 8 } = {}) {
  const out = [];
  for (const row of rows || []) {
    const title = String(row?.title || "");
    const match = title.match(FILING_FORM_RE);
    const form = match ? match[1].toUpperCase().replace(/\s+/g, "") : null;
    const text = `${title} ${row?.summary || ""}`.toUpperCase();
    const symbol = String(ticker || "").trim().toUpperCase();
    if (symbol && !text.includes(symbol) && String(row?.ticker || "").toUpperCase() !== symbol) {
      const hay = `${title} ${row?.summary || ""}`.toLowerCase();
      if (!name || !hay.includes(String(name).toLowerCase())) continue;
    }
    out.push({
      ...row,
      form: form || row.form || null,
      isFiling: Boolean(form) || row.category === "filings",
    });
    if (out.length >= limit) break;
  }
  return out;
}

/** Group EVTS rows into a Mon–Sun week grid. */
export function macroWeekGrid(events = [], { now = Date.now() } = {}) {
  const date = new Date(now);
  const day = date.getUTCDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + mondayOffset));
  const days = Array.from({ length: 7 }, (_, index) => {
    const stamp = new Date(monday.getTime() + index * MS_DAY);
    const iso = stamp.toISOString().slice(0, 10);
    return {
      date: iso,
      weekday: stamp.getUTCDay(),
      label: stamp.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" }),
      events: [],
    };
  });
  const byDate = new Map(days.map((row) => [row.date, row]));
  for (const event of events || []) {
    const iso = String(event?.date || "").slice(0, 10);
    const bucket = byDate.get(iso);
    if (bucket) bucket.events.push(event);
  }
  return {
    start: days[0]?.date || null,
    end: days[6]?.date || null,
    days,
  };
}

export function earningsCountdown(dateStr, now = Date.now()) {
  const stamp = Date.parse(dateStr);
  if (!Number.isFinite(stamp)) return null;
  const days = Math.ceil((stamp - now) / MS_DAY);
  return { days, date: String(dateStr).slice(0, 10), urgent: days >= 0 && days <= 7 };
}

/** Enrich screener/universe rows with RSI / 52w distance / vol ratio / earn days. */
export function enrichScreenerRow(row = {}, {
  chartPoints = [],
  earningsDate = null,
  now = Date.now(),
} = {}) {
  const last = Number(row.last ?? row.last_price ?? row.close);
  const high = Number(row.weekHigh ?? row.fifty_two_week_high);
  const low = Number(row.weekLow ?? row.fifty_two_week_low);
  const volume = Number(row.volume);
  const avgVolume = Number(row.avgVolume ?? row.avg_volume);
  let rsi = null;
  if (chartPoints?.length >= 16) {
    const series = relativeStrength(chartPoints, 14);
    const lastRsi = series[series.length - 1];
    rsi = Number.isFinite(lastRsi) ? lastRsi : null;
  }
  const distHigh =
    Number.isFinite(last) && Number.isFinite(high) && high !== 0
      ? ((last - high) / high) * 100
      : null;
  const distLow =
    Number.isFinite(last) && Number.isFinite(low) && low !== 0
      ? ((last - low) / low) * 100
      : null;
  const rangePos =
    Number.isFinite(last) && Number.isFinite(high) && Number.isFinite(low) && high > low
      ? ((last - low) / (high - low)) * 100
      : null;
  const volRatio =
    Number.isFinite(volume) && Number.isFinite(avgVolume) && avgVolume > 0
      ? volume / avgVolume
      : null;
  const earn = earningsCountdown(earningsDate, now);
  return {
    ...row,
    rsi,
    distHigh,
    distLow,
    rangePos,
    volRatio,
    earnDays: earn?.days ?? null,
    earnDate: earn?.date ?? null,
    earnUrgent: Boolean(earn?.urgent),
  };
}

function optionMid(bid, ask, lastTrade) {
  const b = Number(bid);
  const a = Number(ask);
  if (Number.isFinite(b) && Number.isFinite(a) && b >= 0 && a >= b) return (a + b) / 2;
  const lt = Number(lastTrade);
  return Number.isFinite(lt) && lt > 0 ? lt : null;
}

/**
 * ATM-straddle expected move from the options chain.
 *
 * Uses the nearest expiry's strike closest to spot: call mid + put mid is
 * the market's priced-in move to that date. Returns null when the chain
 * lacks usable quotes.
 */
export function expectedMove(optionRows = [], last, { now = Date.now() } = {}) {
  const spot = Number(last);
  if (!Number.isFinite(spot) || spot <= 0) return null;
  const today = new Date(now);
  const candidates = [];
  for (const row of optionRows || []) {
    const strike = Number(row?.strike);
    const expiry = String(row?.expiry || "").trim();
    if (!Number.isFinite(strike) || !expiry) continue;
    const parsed = new Date(expiry);
    if (!Number.isFinite(parsed.getTime()) || parsed < today) continue;
    candidates.push({ row, strike, expiry, time: parsed.getTime() });
  }
  if (!candidates.length) return null;
  const nearestTime = Math.min(...candidates.map((c) => c.time));
  const chain = candidates.filter((c) => c.time === nearestTime);
  chain.sort((a, b) => Math.abs(a.strike - spot) - Math.abs(b.strike - spot));
  const atm = chain[0];
  const call = optionMid(atm.row.call_bid, atm.row.call_ask, atm.row.call_last);
  const put = optionMid(atm.row.put_bid, atm.row.put_ask, atm.row.put_last);
  if (call == null || put == null) return null;
  const straddle = call + put;
  if (!(straddle > 0)) return null;
  const days = Math.max(Math.round((nearestTime - now) / 86_400_000), 0);
  return {
    expiry: atm.expiry,
    strike: atm.strike,
    straddle,
    movePct: (straddle / spot) * 100,
    moveUsd: straddle,
    days,
  };
}

/**
 * Price reaction since a headline was captured, from cached chart points.
 * Returns pct move from the nearest point at/after capture to the last
 * print, or null when the series doesn't cover the capture time.
 */
export function headlineReaction(capturedAt, points = []) {
  const stamp = Date.parse(String(capturedAt || ""));
  if (!Number.isFinite(stamp) || !Array.isArray(points) || points.length < 2) return null;
  const series = points
    .map((point) => ({
      t: Number(point?.t) > 1e12 ? Number(point.t) : Number(point?.t) * 1000,
      close: Number(point?.close),
    }))
    .filter((point) => Number.isFinite(point.t) && Number.isFinite(point.close));
  if (series.length < 2) return null;
  const lastPoint = series[series.length - 1];
  if (stamp < series[0].t || stamp > lastPoint.t) return null;
  let base = null;
  for (const point of series) {
    if (point.t >= stamp) {
      base = point;
      break;
    }
  }
  if (!base || !base.close) return null;
  return ((lastPoint.close - base.close) / base.close) * 100;
}
