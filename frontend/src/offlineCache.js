/**
 * Last-known quotes / desk snapshot for poor-network opens.
 * Never blocks the live path — write after success, read only as fallback.
 */

const QUOTES_KEY = "bsh.offline.quotes";
const BRIEF_KEY = "bsh.offline.briefs";
const MAX_BRIEFS = 24;

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode */
  }
}

export function cacheQuotes(quotes = {}, { asOf = null } = {}) {
  writeJson(QUOTES_KEY, {
    as_of: asOf || new Date().toISOString(),
    quotes: quotes || {},
  });
}

export function loadCachedQuotes() {
  const payload = readJson(QUOTES_KEY, null);
  if (!payload || typeof payload !== "object") return null;
  return payload;
}

export function cacheBrief(key, brief) {
  if (!key || !brief) return;
  const store = readJson(BRIEF_KEY, { items: {} });
  const items = store.items && typeof store.items === "object" ? store.items : {};
  items[String(key)] = { ...brief, cached_at: new Date().toISOString() };
  const keys = Object.keys(items);
  if (keys.length > MAX_BRIEFS) {
    keys
      .sort((a, b) => String(items[a]?.cached_at || "").localeCompare(String(items[b]?.cached_at || "")))
      .slice(0, keys.length - MAX_BRIEFS)
      .forEach((k) => delete items[k]);
  }
  writeJson(BRIEF_KEY, { items });
}

export function loadCachedBrief(key) {
  if (!key) return null;
  const store = readJson(BRIEF_KEY, { items: {} });
  return store.items?.[String(key)] || null;
}

export function briefCacheKey(title, company = null) {
  return `${String(title || "").trim().toLowerCase()}|${String(company || "").trim().toLowerCase()}`;
}
