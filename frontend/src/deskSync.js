/**
 * Desk state sync — mirrors market-desk localStorage to the server.
 *
 * Watchlists, pin groups, book lots, notes, saved desks, alert rules, and
 * chart prefs all live in localStorage (see DESK_KEYS). That made the desk
 * disposable: clear the cache or open a second machine and it's empty.
 * This module keeps a server copy via /api/desk/prefs:
 *
 * - `initDeskSync()` (App startup): pull the server blob and merge it per
 *   key. The server value wins for every key this browser has not changed
 *   since its last sync (so data saved from the Mac or another browser is
 *   adopted); the local value wins only for keys with unsynced local edits.
 *   The merged state is then pushed back.
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

export const SYNCED_MARK_KEY = "bsh.deskSync.synced";
export const DESK_SYNC_EVENT = "bsh:desk-synced";

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

function serialize(value) {
  try {
    return JSON.stringify(value);
  } catch {
    return undefined;
  }
}

function readSyncedMarks() {
  const marks = readKey(SYNCED_MARK_KEY);
  return marks && typeof marks === "object" && !Array.isArray(marks) ? marks : {};
}

/** Record `data` as the state known to be on the server. */
function markSynced(data) {
  const marks = {};
  for (const key of DESK_KEYS) {
    if (key in data) {
      const text = serialize(data[key]);
      if (text !== undefined) marks[key] = text;
    }
  }
  writeKey(SYNCED_MARK_KEY, marks);
}

/** True when the local value of `key` differs from its last-synced value. */
export function isDeskKeyDirty(key, marks = readSyncedMarks()) {
  const local = readKey(key);
  if (local === undefined) return false;
  if (!(key in marks)) return false;
  return serialize(local) !== marks[key];
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

/**
 * Merge a server snapshot into localStorage. The server value is adopted
 * for keys missing locally and for keys whose local value is unchanged
 * since the last sync; keys with unsynced local edits keep the local value.
 */
export function mergeDeskState(data = {}) {
  const marks = readSyncedMarks();
  const applied = [];
  for (const key of DESK_KEYS) {
    if (!(key in data)) continue;
    const local = readKey(key);
    if (local !== undefined) {
      if (isDeskKeyDirty(key, marks)) continue;
      if (serialize(local) === serialize(data[key])) continue;
    }
    writeKey(key, data[key]);
    applied.push(key);
  }
  return applied;
}

function notifySynced(applied) {
  if (!applied.length || typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent(DESK_SYNC_EVENT, { detail: { keys: applied } }));
  } catch {
    // Non-browser environment.
  }
}

async function pushNow() {
  const snapshot = snapshotDeskState();
  try {
    await api.saveDeskPrefs(snapshot);
    markSynced(snapshot);
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

/** Pull server state once per app load, merge per key, push the result. */
export async function initDeskSync() {
  if (initialized || typeof window === "undefined") return [];
  initialized = true;
  let applied = [];
  let serverData = {};
  try {
    const payload = await api.deskPrefs();
    serverData = payload?.data || {};
    applied = mergeDeskState(serverData);
  } catch {
    return applied;
  }
  markSynced(serverData);
  notifySynced(applied);
  scheduleDeskSync();
  return applied;
}

/** Test hook. */
export function resetDeskSyncForTests() {
  initialized = false;
  if (typeof window !== "undefined") window.clearTimeout(pushTimer);
  pushTimer = 0;
}
