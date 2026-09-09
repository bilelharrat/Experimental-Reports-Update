/** EQS-style saved screener presets (client-only). */

const SCREENS_KEY = "bsh.marketSavedScreens";

function readScreens() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(SCREENS_KEY) || "[]");
    if (!Array.isArray(raw)) return [];
    return raw
      .map((row) => normalizeScreen(row))
      .filter(Boolean);
  } catch {
    return [];
  }
}

function writeScreens(screens) {
  try {
    window.localStorage.setItem(SCREENS_KEY, JSON.stringify(screens));
  } catch {
    // ignore
  }
}

function normalizeScreen(row) {
  const name = String(row?.name || "").trim();
  if (!name) return null;
  const id = String(row?.id || `screen-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`);
  return {
    id,
    name,
    filters: {
      sector: String(row?.filters?.sector || ""),
      cap: String(row?.filters?.cap || ""),
      minChange: row?.filters?.minChange ?? "",
      minVolume: row?.filters?.minVolume ?? "",
      query: String(row?.filters?.query || ""),
    },
  };
}

export function loadSavedScreens() {
  return readScreens();
}

export function saveScreen(name, filters = {}) {
  const screen = normalizeScreen({ name, filters, id: `screen-${Date.now()}` });
  if (!screen) return readScreens();
  const next = [screen, ...readScreens().filter((row) => row.name !== screen.name)].slice(0, 12);
  writeScreens(next);
  return next;
}

export function deleteSavedScreen(id) {
  const next = readScreens().filter((row) => row.id !== id);
  writeScreens(next);
  return next;
}

export function findSavedScreen(idOrName, screens = readScreens()) {
  const key = String(idOrName || "").trim().toLowerCase();
  if (!key) return null;
  return (
    screens.find((row) => row.id === idOrName) ||
    screens.find((row) => row.name.toLowerCase() === key) ||
    null
  );
}

/** Encode live EQS filters into shareable route query fields. */
export function screenFiltersToQuery(filters = {}) {
  const query = {};
  if (filters.sector) query.eqsSector = String(filters.sector);
  if (filters.cap) query.eqsCap = String(filters.cap);
  if (filters.minChange !== "" && filters.minChange != null) {
    query.eqsMinChange = String(filters.minChange);
  }
  if (filters.minVolume !== "" && filters.minVolume != null) {
    query.eqsMinVolume = String(filters.minVolume);
  }
  if (filters.query) query.eqsQ = String(filters.query);
  return query;
}

export function screenFiltersFromQuery(query = {}) {
  return {
    sector: String(query.eqsSector || ""),
    cap: String(query.eqsCap || ""),
    minChange: query.eqsMinChange ?? "",
    minVolume: query.eqsMinVolume ?? "",
    query: String(query.eqsQ || ""),
  };
}

export function hasScreenQuery(query = {}) {
  return Boolean(
    query.screen ||
      query.eqsSector ||
      query.eqsCap ||
      query.eqsMinChange ||
      query.eqsMinVolume ||
      query.eqsQ,
  );
}
