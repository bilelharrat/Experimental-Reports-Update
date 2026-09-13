/**
 * Desk state sync — mirrors market-desk localStorage to the server.
 *
 * Watchlists, pin groups, book lots, notes, saved desks, alert rules, and
 * chart prefs all live in localStorage (see DESK_KEYS). That made the desk
 * disposable: clear the cache or open a second machine and it's empty.
 * This module keeps a server copy via /api/desk/prefs:
 *
 * - `initDeskSync()` (App startup): pull the server blob; any key the
 *   local browser is missing gets filled from the server, then the merged
 *   state is pushed back. Local values win on conflict — the machine you
 *   are typing on is the source of truth.
 * - `scheduleDeskSync()` (called by the storage helpers after each write):
 *   debounced push of the full desk snapshot.
 *
 * Everything is fire-and-forget: the desk keeps working from localStorage
 * when the server is unreachable, and sync retries on the next write.
 */

import { api } from "./api.js";

export const DESK_KEYS = [
  "bsh.marketPinnedTickers",
  "bsh.marketPinGroups",
  "bsh.marketAlertRules",
  "bsh.marketHpCompare",
  "bsh.marketWatchColumns",
  "bsh.marketAlertMutes",
  "bsh.marketAlertHistory",
  "bsh.marketDesks",
  "bsh.marketRecentTickers",
  "bsh.marketLastDesk",
  "bsh.marketTickerNotes",
  "bsh.marketChartPrefs",
  "bsh.marketDeskLayout",
  "bsh.newsDesk.expanded",
  "bsh.bookLots",
];

const PUSH_DEBOUNCE_MS = 2500;

let pushTimer = 0;
let initialized = false;

function readKey(key) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw == null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function writeKey(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota/private mode — desk still works in-memory for the session.
  }
}

/** Current desk state as a plain object (only keys that exist locally). */
export function snapshotDeskState(keys = DESK_KEYS) {
  const data = {};
  for (const key of keys) {
    const value = readKey(key);
    if (value !== undefined) data[key] = value;
  }
  return data;
}

/** Restore a snapshot into localStorage. `overwrite` replaces local keys. */
export function applyDeskState(data = {}, { overwrite = false } = {}) {
  const applied = [];
  for (const key of DESK_KEYS) {
    if (!(key in data)) continue;
    if (!overwrite && readKey(key) !== undefined) continue;
    writeKey(key, data[key]);
    applied.push(key);
  }
  return applied;
}

async function pushNow() {
  try {
    await api.saveDeskPrefs(snapshotDeskState());
  } catch {
    // Offline or auth expired — next write retries.
  }
}

/** Debounced server push; storage helpers call this after every write. */
export function scheduleDeskSync() {
  if (typeof window === "undefined") return;
  window.clearTimeout(pushTimer);
  pushTimer = window.setTimeout(pushNow, PUSH_DEBOUNCE_MS);
}

/** Pull server state once per app load, fill gaps locally, push merge. */
export async function initDeskSync() {
  if (initialized || typeof window === "undefined") return [];
  initialized = true;
  let applied = [];
  try {
    const payload = await api.deskPrefs();
    applied = applyDeskState(payload?.data || {});
  } catch {
    return applied;
  }
  scheduleDeskSync();
  return applied;
}

/** Test hook. */
export function resetDeskSyncForTests() {
  initialized = false;
  if (typeof window !== "undefined") window.clearTimeout(pushTimer);
  pushTimer = 0;
}
