// Per-account browser state.
//
// The app keeps some forty pieces of personal state in localStorage —
// recently opened companies, the welcome tour having been seen, the last
// company, favourites, market desks, alert rules, book lots — and none of
// it was scoped to who is signed in. A second account on the same browser
// inherited every bit of the first one's: it saw the other person's
// history and never got the first-time tour.
//
// The fix is a profile switch at the auth boundary. localStorage holds one
// account's state at a time and remembers whose (OWNER_KEY). When a
// different account signs in, the current state is stashed under its
// owner, that account's own stash (if any) is restored, and the caller
// reloads the page so every module re-reads a clean store. State written
// before this existed has no owner: it goes to a legacy stash that nobody
// inherits, so no account ever starts from someone else's.
//
// A few keys belong to the device, not the person, and never move: the
// session itself, the theme, the UI language and the sidebar's collapsed
// state.

const OWNER_KEY = "bsh.profile.owner";
const STASH_PREFIX = "bsh.profile.stash.";
const LEGACY_OWNER = "__legacy__";
const PROFILE_KEY_PREFIX = "bsh.";

export const DEVICE_KEYS = new Set([
  "bsh.research.session",
  "bsh.research.appearance",
  "bsh.appLanguage",
  "bsh.sidebarCollapsed",
]);

function _storage() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function _isProfileKey(key) {
  return (
    typeof key === "string" &&
    key.startsWith(PROFILE_KEY_PREFIX) &&
    !key.startsWith(STASH_PREFIX) &&
    key !== OWNER_KEY &&
    !DEVICE_KEYS.has(key)
  );
}

function _normalize(email) {
  return String(email || "").trim().toLowerCase();
}

/** Whose state localStorage currently holds, or null when it predates this. */
export function currentProfileOwner() {
  const ls = _storage();
  if (!ls) return null;
  return ls.getItem(OWNER_KEY) || null;
}

/**
 * Make localStorage hold `email`'s state. Returns true when a switch
 * happened — the caller must then reload, because modules read their keys
 * at import and are still holding the previous account's values.
 */
export function ensureProfileFor(email) {
  const ls = _storage();
  const account = _normalize(email);
  if (!ls || !account) return false;
  const owner = ls.getItem(OWNER_KEY) || null;
  if (owner === account) return false;

  // Stash what is here under whoever it belongs to.
  const snapshot = {};
  const doomed = [];
  for (let i = 0; i < ls.length; i += 1) {
    const key = ls.key(i);
    if (_isProfileKey(key)) {
      snapshot[key] = ls.getItem(key);
      doomed.push(key);
    }
  }
  try {
    ls.setItem(STASH_PREFIX + (owner || LEGACY_OWNER), JSON.stringify(snapshot));
  } catch {
    // Quota: the stash is a courtesy to the previous account; the switch
    // itself — a clean store for this one — still goes ahead.
  }
  for (const key of doomed) ls.removeItem(key);

  // Restore this account's own state, if it has been here before.
  const mineKey = STASH_PREFIX + account;
  const mine = ls.getItem(mineKey);
  if (mine) {
    try {
      const parsed = JSON.parse(mine);
      for (const [key, value] of Object.entries(parsed || {})) {
        if (_isProfileKey(key) && typeof value === "string") ls.setItem(key, value);
      }
    } catch {
      // A corrupt stash is dropped rather than half-applied.
    }
    ls.removeItem(mineKey);
  }

  ls.setItem(OWNER_KEY, account);
  return true;
}

/** The app's client base path ("/research/" here), for a hard navigation. */
export function appBasePath() {
  const base = import.meta.env?.BASE_URL || "/";
  return base.endsWith("/") ? base : `${base}/`;
}
