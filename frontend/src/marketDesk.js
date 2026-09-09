/** Desk-level Market helpers: columns, heatmap, RRG, filings, desks, earnings. */

import { scheduleDeskSync } from "./deskSync.js";

export const WATCH_COLUMN_IDS = [
  "price",
  "change",
  "ytd",
  "vs_spy",
  "volume",
  "vol_ratio",
  "next_earn",
  "earn_days",
  "rsi",
  "range_pos",
];

const DEFAULT_WATCH_COLUMNS = ["price", "change", "volume"];
const COLS_KEY = "bsh.marketWatchColumns";
const MUTES_KEY = "bsh.marketAlertMutes";
const NOTIFIED_KEY = "bsh.marketAlertNotified";
const HISTORY_KEY = "bsh.marketAlertHistory";
const DESKS_KEY = "bsh.marketDesks";

function readJson(key, fallback) {
  try {
    const raw = JSON.parse(window.localStorage.getItem(key) || "null");
    return raw == null ? fallback : raw;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore
  }
  scheduleDeskSync();
}

export function loadWatchColumns() {
  const raw = readJson(COLS_KEY, DEFAULT_WATCH_COLUMNS);
  const ids = (Array.isArray(raw) ? raw : DEFAULT_WATCH_COLUMNS)
    .map((id) => String(id))
    .filter((id) => WATCH_COLUMN_IDS.includes(id));
  return ids.length ? ids : [...DEFAULT_WATCH_COLUMNS];
}

export function saveWatchColumns(ids = DEFAULT_WATCH_COLUMNS) {
  const next = [...new Set((ids || []).filter((id) => WATCH_COLUMN_IDS.includes(id)))];
  const saved = next.length ? next : [...DEFAULT_WATCH_COLUMNS];
  writeJson(COLS_KEY, saved);
  return saved;
}

export function toggleWatchColumn(id, current = loadWatchColumns()) {
  const key = String(id || "");
  if (!WATCH_COLUMN_IDS.includes(key) || key === "price") return current;
  const set = new Set(current);
  if (set.has(key)) {
    if (set.size <= 1) return current;
    set.delete(key);
  } else {
    set.add(key);
  }
  return saveWatchColumns(["price", ...WATCH_COLUMN_IDS.filter((col) => col !== "price" && set.has(col))]);
}

export function volumeRatio(volume, avgVolume) {
  const vol = Number(volume);
  const avg = Number(avgVolume);
  if (!Number.isFinite(vol) || !Number.isFinite(avg) || avg <= 0) return null;
  return vol / avg;
}

export function vsSpyDay(change, spyChange) {
  const a = Number(change);
  const b = Number(spyChange);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return a - b;
}

export function daysUntil(dateStr, now = Date.now()) {
  const stamp = Date.parse(dateStr);
  if (!Number.isFinite(stamp)) return null;
  return Math.ceil((stamp - now) / 86400000);
}

/** Compact earnings + revision strip from workspace earnings/analysis. */
export function earningsStrip(workspace = {}, { now = Date.now() } = {}) {
  const earn = workspace?.earnings || {};
  const analysis = workspace?.analysis || {};
  const past = earn.past || [];
  const last = past[0] || null;
  const nextQ = (analysis.quarterly || [])[0] || null;
  const nextY = (analysis.yearly || [])[0] || null;
  const forecast = nextQ || nextY || null;
  const days = daysUntil(earn.next_date, now);
  const surprises = past
    .map((row) => Number(row.surprise_pct))
    .filter(Number.isFinite);
  const avgSurprise =
    surprises.length > 0
      ? surprises.reduce((sum, n) => sum + n, 0) / surprises.length
      : null;
  const up = Number(forecast?.revisions_up);
  const down = Number(forecast?.revisions_down);
  return {
    nextDate: earn.next_date || null,
    nextEstimated: Boolean(earn.next_estimated),
    days,
    lastSurprise: last?.surprise_pct ?? null,
    lastEps: last?.eps ?? null,
    lastEstimate: last?.estimate ?? null,
    lastPeriod: last?.period || null,
    consensus: forecast?.consensus ?? null,
    revisionsUp: Number.isFinite(up) ? up : null,
    revisionsDown: Number.isFinite(down) ? down : null,
    revisionNet:
      Number.isFinite(up) && Number.isFinite(down) ? up - down : null,
    avgSurprise,
    beatCount: surprises.filter((n) => n > 0).length,
    printCount: surprises.length,
  };
}

export function sectorHeatmap(rows = [], { minCount = 2 } = {}) {
  const buckets = new Map();
  for (const row of rows || []) {
    const sector = String(row?.sector || "").trim() || "Unknown";
    const change = Number(row?.change_pct ?? row?.change);
    if (!Number.isFinite(change)) continue;
    const bucket = buckets.get(sector) || { sector, changeSum: 0, count: 0, leaders: [] };
    bucket.changeSum += change;
    bucket.count += 1;
    bucket.leaders.push({
      ticker: row.ticker,
      name: row.name,
      change,
    });
    buckets.set(sector, bucket);
  }
  return [...buckets.values()]
    .filter((row) => row.count >= minCount)
    .map((row) => {
      const avg = row.changeSum / row.count;
      row.leaders.sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
      return {
        sector: row.sector,
        count: row.count,
        avg,
        leader: row.leaders[0] || null,
      };
    })
    .sort((a, b) => Math.abs(b.avg) - Math.abs(a.avg))
    .slice(0, 12);
}

export function heatTone(avg) {
  const n = Number(avg);
  if (!Number.isFinite(n)) return 0;
  return Math.max(-1, Math.min(1, n / 3));
}

/**
 * RRG-lite: x = vs SPY 1Y (strength), y = vs SPY 1M (momentum).
 * Leading / Weakening / Lagging / Improving.
 */
export function rrgPoints(rows = []) {
  const points = [];
  for (const row of rows || []) {
    const x = Number(row.vs_spy_1y);
    const y = Number(row.vs_spy_1m);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    let quadrant = "lagging";
    if (x >= 0 && y >= 0) quadrant = "leading";
    else if (x >= 0 && y < 0) quadrant = "weakening";
    else if (x < 0 && y >= 0) quadrant = "improving";
    points.push({
      ticker: row.ticker,
      x,
      y,
      quadrant,
    });
  }
  return points;
}

export function rrgLayout(points = [], { size = 220, pad = 22 } = {}) {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const maxAbs = Math.max(8, ...xs.map(Math.abs), ...ys.map(Math.abs), 1);
  const inner = size - pad * 2;
  const mid = size / 2;
  const scale = (inner / 2) / maxAbs;
  return {
    size,
    pad,
    mid,
    maxAbs,
    scale,
    coords: points.map((point) => ({
      ...point,
      cx: mid + point.x * scale,
      cy: mid - point.y * scale,
    })),
  };
}

/** Build short RRG trails from peer OHLC vs SPY closes (last N weekly samples). */
export function rrgTrails(rows = [], { steps = 4, stepDays = 5 } = {}) {
  const spy = (rows || []).find((row) => String(row?.ticker || "").toUpperCase() === "SPY");
  const spyPoints = spy?.points || [];
  if (spyPoints.length < stepDays * 2) return [];

  const periodRet = (points, days, endIndex) => {
    if (!points?.length || endIndex < 1) return null;
    const end = points[Math.min(endIndex, points.length - 1)];
    const endClose = Number(end?.close);
    if (!Number.isFinite(endClose) || endClose === 0) return null;
    const endT = Number(end?.t);
    const target = endT - days * 86_400;
    let startClose = null;
    for (const point of points) {
      const t = Number(point?.t);
      const close = Number(point?.close);
      if (!Number.isFinite(t) || !Number.isFinite(close)) continue;
      if (t <= target) startClose = close;
    }
    if (!Number.isFinite(startClose) || startClose === 0) startClose = Number(points[0]?.close);
    if (!Number.isFinite(startClose) || startClose === 0) return null;
    return ((endClose - startClose) / startClose) * 100;
  };

  const trails = [];
  for (const row of rows || []) {
    const ticker = String(row?.ticker || "").toUpperCase();
    if (!ticker || ticker === "SPY" || !row.points?.length) continue;
    const path = [];
    for (let step = steps - 1; step >= 0; step -= 1) {
      const endIndex = Math.max(0, row.points.length - 1 - step * stepDays);
      const spyEnd = Math.max(0, spyPoints.length - 1 - step * stepDays);
      const asset1y = periodRet(row.points, 252, endIndex);
      const spy1y = periodRet(spyPoints, 252, spyEnd);
      const asset1m = periodRet(row.points, 21, endIndex);
      const spy1m = periodRet(spyPoints, 21, spyEnd);
      if (![asset1y, spy1y, asset1m, spy1m].every(Number.isFinite)) continue;
      path.push({
        x: asset1y - spy1y,
        y: asset1m - spy1m,
      });
    }
    if (path.length >= 2) trails.push({ ticker, path });
  }
  return trails;
}

export function edgarLinks(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return [];
  const browse = (type) => {
    const params = new URLSearchParams({
      action: "getcompany",
      ticker: symbol,
      owner: "include",
      count: "10",
    });
    if (type) params.set("type", type);
    return `https://www.sec.gov/cgi-bin/browse-edgar?${params.toString()}`;
  };
  return [
    { id: "all", form: "EDGAR", url: browse("") },
    { id: "10-k", form: "10-K", url: browse("10-K") },
    { id: "10-q", form: "10-Q", url: browse("10-Q") },
    { id: "8-k", form: "8-K", url: browse("8-K") },
  ];
}

function normalizeDesk(row) {
  const name = String(row?.name || "").trim();
  if (!name) return null;
  return {
    id: String(row?.id || `desk-${Date.now()}`),
    name,
    ticker: String(row?.ticker || "").trim().toUpperCase() || null,
    panel: String(row?.panel || ""),
    workspaceTab: String(row?.workspaceTab || ""),
    chartRange: String(row?.chartRange || "1d"),
    hpCompare: Array.isArray(row?.hpCompare)
      ? row.hpCompare.map((t) => String(t).toUpperCase()).filter(Boolean).slice(0, 4)
      : [],
    newsScope: String(row?.newsScope || "all"),
    calendarFilter: String(row?.calendarFilter || "all"),
    screen: row?.screen || null,
    tab: String(row?.tab || ""),
    twoUp: Boolean(row?.twoUp),
    secondaryTicker: String(row?.secondaryTicker || "").trim().toUpperCase() || null,
    watchGroupFilter: String(row?.watchGroupFilter || "all"),
    watchColumns: Array.isArray(row?.watchColumns) ? row.watchColumns.map(String) : null,
    corrBench: String(row?.corrBench || "SPY").trim().toUpperCase() || "SPY",
    pairMode: String(row?.pairMode || "diff"),
    scrollY: Number.isFinite(Number(row?.scrollY)) ? Number(row.scrollY) : null,
  };
}

export function loadDesks() {
  const raw = readJson(DESKS_KEY, []);
  return (Array.isArray(raw) ? raw : []).map(normalizeDesk).filter(Boolean);
}

export function saveDesk(name, state = {}) {
  const desk = normalizeDesk({ ...state, name, id: `desk-${Date.now()}` });
  if (!desk) return loadDesks();
  const next = [desk, ...loadDesks().filter((row) => row.name !== desk.name)].slice(0, 10);
  writeJson(DESKS_KEY, next);
  return next;
}

export function deleteDesk(id) {
  const next = loadDesks().filter((row) => row.id !== id);
  writeJson(DESKS_KEY, next);
  return next;
}

export function findDesk(idOrName, desks = loadDesks()) {
  const key = String(idOrName || "").trim().toLowerCase();
  if (!key) return null;
  return desks.find((row) => row.id === idOrName) || desks.find((row) => row.name.toLowerCase() === key) || null;
}

export function loadAlertMutes() {
  const raw = readJson(MUTES_KEY, []);
  return (Array.isArray(raw) ? raw : [])
    .map((row) => ({
      key: String(row?.key || ""),
      until: Number(row?.until) || 0,
    }))
    .filter((row) => row.key);
}

export function saveAlertMutes(mutes = []) {
  writeJson(MUTES_KEY, mutes);
  return mutes;
}

export function alertKey(alert) {
  return `${alert?.ticker || ""}:${alert?.kind || ""}:${alert?.ruleId || ""}`;
}

export function muteAlert(alert, { minutes = 60, now = Date.now() } = {}) {
  const key = alertKey(alert);
  if (!key || key === "::") return loadAlertMutes();
  const rest = loadAlertMutes().filter((row) => row.key !== key);
  const next = [...rest, { key, until: now + minutes * 60_000 }];
  recordAlertHistory([alert], {
    now,
    action: minutes >= 60 * 12 ? "muted" : "snoozed",
    detail: `${minutes}m`,
  });
  return saveAlertMutes(next);
}

export function unmuteAlert(alert) {
  const key = alertKey(alert);
  return saveAlertMutes(loadAlertMutes().filter((row) => row.key !== key));
}

export function visibleAlerts(alerts = [], mutes = loadAlertMutes(), now = Date.now()) {
  const blocked = new Set(
    (mutes || []).filter((row) => Number(row.until) > now).map((row) => row.key),
  );
  return (alerts || []).filter((alert) => !blocked.has(alertKey(alert)));
}

export function freshAlerts(alerts = [], { now = Date.now(), windowMs = 4 * 3600_000 } = {}) {
  const seen = readJson(NOTIFIED_KEY, {});
  const next = { ...(seen && typeof seen === "object" ? seen : {}) };
  const fresh = [];
  for (const alert of alerts || []) {
    const key = alertKey(alert);
    const last = Number(next[key]);
    if (Number.isFinite(last) && now - last < windowMs) continue;
    next[key] = now;
    fresh.push(alert);
  }
  writeJson(NOTIFIED_KEY, next);
  if (fresh.length) recordAlertHistory(fresh, { now, action: "fired" });
  return fresh;
}

export function loadAlertHistory() {
  const raw = readJson(HISTORY_KEY, []);
  return (Array.isArray(raw) ? raw : [])
    .map((row) => ({
      id: String(row?.id || ""),
      key: String(row?.key || ""),
      ticker: String(row?.ticker || "").toUpperCase(),
      kind: String(row?.kind || ""),
      action: String(row?.action || "fired"),
      at: Number(row?.at) || 0,
      detail: String(row?.detail || ""),
    }))
    .filter((row) => row.key && row.at)
    .sort((a, b) => b.at - a.at)
    .slice(0, 100);
}

export function recordAlertHistory(alerts = [], { now = Date.now(), action = "fired", detail = "" } = {}) {
  const prev = loadAlertHistory();
  const rows = (alerts || []).map((alert, index) => ({
    id: `${alertKey(alert)}:${now}:${index}`,
    key: alertKey(alert),
    ticker: String(alert?.ticker || "").toUpperCase(),
    kind: String(alert?.kind || ""),
    action,
    at: now,
    detail: detail || String(alert?.threshold ?? ""),
  }));
  const next = [...rows, ...prev].slice(0, 100);
  writeJson(HISTORY_KEY, next);
  return next;
}

export function clearAlertHistory() {
  writeJson(HISTORY_KEY, []);
  return [];
}

export function notifyAlerts(alerts = [], { title = "Market alerts", notify } = {}) {
  if (!alerts.length) return 0;
  const send =
    notify ||
    ((payload) => {
      if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
      try {
        new Notification(payload.title, { body: payload.body, silent: true });
      } catch {
        // ignore
      }
    });
  const body = alerts
    .slice(0, 4)
    .map((alert) => `${alert.ticker} ${alert.kind}`)
    .join(" · ");
  send({ title, body });
  return alerts.length;
}

export function requestAlertPermission() {
  if (typeof Notification === "undefined") return Promise.resolve("unsupported");
  if (Notification.permission !== "default") return Promise.resolve(Notification.permission);
  return Notification.requestPermission();
}

const RECENTS_KEY = "bsh.marketRecentTickers";
const LAST_DESK_KEY = "bsh.marketLastDesk";
const NOTES_KEY = "bsh.marketTickerNotes";
const CHART_PREFS_KEY = "bsh.marketChartPrefs";
const DESK_LAYOUT_KEY = "bsh.marketDeskLayout";

export function loadRecentTickers() {
  const raw = readJson(RECENTS_KEY, []);
  return (Array.isArray(raw) ? raw : [])
    .map((ticker) => String(ticker || "").trim().toUpperCase())
    .filter(Boolean)
    .slice(0, 12);
}

export function pushRecentTicker(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return loadRecentTickers();
  const next = [symbol, ...loadRecentTickers().filter((row) => row !== symbol)].slice(0, 12);
  writeJson(RECENTS_KEY, next);
  return next;
}

export function loadLastDeskId() {
  return String(readJson(LAST_DESK_KEY, "") || "");
}

export function setLastDeskId(id) {
  const value = String(id || "");
  writeJson(LAST_DESK_KEY, value);
  return value;
}

export function loadTickerNotes() {
  const raw = readJson(NOTES_KEY, {});
  return raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
}

export function loadTickerNote(ticker) {
  const symbol = String(ticker || "").trim().toUpperCase();
  return String(loadTickerNotes()[symbol] || "");
}

export function saveTickerNote(ticker, text = "") {
  const symbol = String(ticker || "").trim().toUpperCase();
  if (!symbol) return loadTickerNotes();
  const next = { ...loadTickerNotes() };
  const value = String(text || "").trim();
  if (value) next[symbol] = value;
  else delete next[symbol];
  writeJson(NOTES_KEY, next);
  return next;
}

export function loadChartPrefs() {
  const raw = readJson(CHART_PREFS_KEY, {});
  return {
    sma20: raw?.sma20 !== false,
    sma50: raw?.sma50 !== false,
    sma200: Boolean(raw?.sma200),
    vwap: raw?.vwap !== false,
    logScale: Boolean(raw?.logScale),
    volume: raw?.volume !== false,
    rsi: Boolean(raw?.rsi),
  };
}

export function saveChartPrefs(prefs = {}) {
  const next = { ...loadChartPrefs(), ...prefs };
  writeJson(CHART_PREFS_KEY, next);
  return next;
}

export function loadDeskLayout() {
  const raw = readJson(DESK_LAYOUT_KEY, {});
  return {
    // Split quote + tape is the default; expand stretches the desk full-width.
    expanded: Boolean(raw?.expanded),
  };
}

export function saveDeskLayout(prefs = {}) {
  const next = { ...loadDeskLayout(), ...prefs };
  writeJson(DESK_LAYOUT_KEY, next);
  return next;
}

function icsStamp(dateStr, timeStr = null) {
  const day = String(dateStr || "").slice(0, 10).replace(/-/g, "");
  if (!/^\d{8}$/.test(day)) return null;
  if (!timeStr) return { value: day, allDay: true };
  const match = String(timeStr).match(/(\d{1,2}):(\d{2})/);
  if (!match) return { value: day, allDay: true };
  const hh = String(Number(match[1])).padStart(2, "0");
  const mm = match[2];
  return { value: `${day}T${hh}${mm}00`, allDay: false };
}

export function eventsToIcs(events = [], { calendarName = "BSH EVTS" } = {}) {
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//BSH Research//Market EVTS//EN",
    `X-WR-CALNAME:${calendarName}`,
  ];
  events.forEach((event, index) => {
    const start = icsStamp(event?.date, event?.time);
    if (!start) return;
    const summary = [event.ticker, event.kind || "event", event.title]
      .filter(Boolean)
      .join(" · ")
      .replace(/[,;]/g, " ");
    lines.push("BEGIN:VEVENT");
    lines.push(`UID:bsh-evts-${index}-${start.value}@bsh`);
    lines.push(start.allDay ? `DTSTART;VALUE=DATE:${start.value}` : `DTSTART:${start.value}`);
    if (start.allDay) {
      const next = new Date(`${String(event.date).slice(0, 10)}T12:00:00Z`);
      next.setUTCDate(next.getUTCDate() + 1);
      lines.push(`DTEND;VALUE=DATE:${next.toISOString().slice(0, 10).replace(/-/g, "")}`);
    }
    lines.push(`SUMMARY:${summary}`);
    lines.push("END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return `${lines.join("\r\n")}\r\n`;
}

export function downloadIcs(events = [], filename = "bsh-evts.ics") {
  const blob = new Blob([eventsToIcs(events)], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Options chain snapshot from Nasdaq-style rows. */
export function optionsSnapshot(options = {}, lastPrice = null) {
  const rows = options?.rows || [];
  if (!rows.length) {
    return {
      nearestExpiry: null,
      atmStrike: null,
      callVolume: 0,
      putVolume: 0,
      callOi: 0,
      putOi: 0,
      putCallVolume: null,
      putCallOi: null,
      rowCount: 0,
    };
  }
  const last = Number(lastPrice);
  const expiries = [...new Set(rows.map((row) => row.expiry).filter(Boolean))].sort();
  const nearestExpiry = expiries[0] || null;
  const near = nearestExpiry ? rows.filter((row) => row.expiry === nearestExpiry) : rows;
  let atm = near[0] || rows[0];
  if (Number.isFinite(last)) {
    atm = [...near].sort((a, b) => Math.abs(Number(a.strike) - last) - Math.abs(Number(b.strike) - last))[0];
  }
  const asNum = (value) => {
    const n = Number(String(value ?? "").replace(/,/g, ""));
    return Number.isFinite(n) ? n : 0;
  };
  let callVolume = 0;
  let putVolume = 0;
  let callOi = 0;
  let putOi = 0;
  for (const row of rows) {
    callVolume += asNum(row.call_volume);
    putVolume += asNum(row.put_volume);
    callOi += asNum(row.call_oi);
    putOi += asNum(row.put_oi);
  }
  return {
    nearestExpiry,
    atmStrike: atm?.strike ?? null,
    callVolume,
    putVolume,
    callOi,
    putOi,
    putCallVolume: callVolume > 0 ? putVolume / callVolume : null,
    putCallOi: callOi > 0 ? putOi / callOi : null,
    rowCount: rows.length,
  };
}
