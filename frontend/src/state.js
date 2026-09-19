// Shared reactive state across components — small ad-hoc store, no Pinia
// dependency. Keeps the surface tiny: anything global goes here.

import { ref, watch } from "vue";

// The currently-open deck-summary modal target, or null.
// Shape: { companyId: string, file: object } where `file` matches the
// records returned by /api/companies/<id>/files. Setting this opens the
// modal globally (mounted once in App.vue); setting it back to null
// closes it.
export const activeSummaryTarget = ref(null);

export function openSummary(companyId, file) {
  activeSummaryTarget.value = { companyId, file };
}

export function closeSummary() {
  activeSummaryTarget.value = null;
}

// Global UI / preferred-content language. Persisted to localStorage so it
// survives reloads. Components that show bilingual content read this to
// pick a default; the per-page tab toggle on company pages can override.
const STORAGE_KEY = "bsh.appLanguage";

function _initialLanguage() {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "zh") return saved;
  } catch {
    // ignore — localStorage unavailable
  }
  return "en";
}

export const appLanguage = ref(_initialLanguage());

watch(appLanguage, (lang) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // ignore
  }
});

export function setAppLanguage(lang) {
  if (lang === "en" || lang === "zh") appLanguage.value = lang;
}

export function toggleAppLanguage() {
  appLanguage.value = appLanguage.value === "en" ? "zh" : "en";
}

// Source-list sidebar: expanded (named rows) vs collapsed (icon rail).
// Persisted so a collapsed Finder-style rail survives reloads.
const SIDEBAR_KEY = "bsh.sidebarCollapsed";

function _initialSidebarCollapsed() {
  try {
    return window.localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

export const sidebarCollapsed = ref(_initialSidebarCollapsed());

watch(sidebarCollapsed, (collapsed) => {
  try {
    window.localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
  } catch {
    // ignore
  }
});

export function setSidebarCollapsed(collapsed) {
  sidebarCollapsed.value = Boolean(collapsed);
}

export function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
}

// Last company workspace. Used after login so the app opens to the work,
// not the brochure Home screen. Clicking Home still goes to search/add.
const LAST_COMPANY_KEY = "bsh.lastCompanyId";

function _initialLastCompanyId() {
  try {
    return window.localStorage.getItem(LAST_COMPANY_KEY) || "";
  } catch {
    return "";
  }
}

export const lastCompanyId = ref(_initialLastCompanyId());

export function setLastCompanyId(id) {
  const next = String(id || "").trim();
  lastCompanyId.value = next;
  try {
    if (next) window.localStorage.setItem(LAST_COMPANY_KEY, next);
    else window.localStorage.removeItem(LAST_COMPANY_KEY);
  } catch {
    // ignore
  }
}

// Sidebar company-list preferences: sort order, follow set (Tracking), and
// per-company view counts. All persisted so the rail feels personal.
const COMPANY_SORT_KEY = "bsh.companySort";
const FAVORITES_KEY = "bsh.favoriteCompanies";
const TRACKED_KEY = "bsh.trackedCompanies";
const VIEWS_KEY = "bsh.companyViews";

export const COMPANY_SORTS = ["az", "za", "newest", "oldest", "views"];

function _readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function _writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore — localStorage unavailable
  }
}

function _initialCompanySort() {
  const saved = _readJson(COMPANY_SORT_KEY, "az");
  return COMPANY_SORTS.includes(saved) ? saved : "az";
}

export const companySort = ref(_initialCompanySort());

export function setCompanySort(sort) {
  if (COMPANY_SORTS.includes(sort)) {
    companySort.value = sort;
    _writeJson(COMPANY_SORT_KEY, sort);
  }
}

function _initialIdSet(key) {
  const saved = _readJson(key, []);
  return new Set(Array.isArray(saved) ? saved.map(String) : []);
}

export const favoriteCompanyIds = ref(_initialIdSet(FAVORITES_KEY));

const FOLLOW_MERGED_KEY = "bsh.followMergedV1";

function _initialFollowedIds() {
  const tracked = _initialIdSet(TRACKED_KEY);
  try {
    if (window.localStorage.getItem(FOLLOW_MERGED_KEY) === "1") return tracked;
    for (const id of _initialIdSet(FAVORITES_KEY)) {
      if (id) tracked.add(String(id));
    }
    _writeJson(TRACKED_KEY, [...tracked]);
    window.localStorage.setItem(FOLLOW_MERGED_KEY, "1");
  } catch {
    // ignore — localStorage unavailable
  }
  return tracked;
}

export const trackedCompanyIds = ref(_initialFollowedIds());

function _toggleIdIn(refSet, key, id) {
  const target = String(id || "").trim();
  if (!target) return;
  const next = new Set(refSet.value);
  if (next.has(target)) next.delete(target);
  else next.add(target);
  refSet.value = next;
  _writeJson(key, [...next]);
}

export function toggleFavoriteCompany(id) {
  _toggleIdIn(favoriteCompanyIds, FAVORITES_KEY, id);
}

export function toggleTrackedCompany(id) {
  _toggleIdIn(trackedCompanyIds, TRACKED_KEY, id);
  import("./trackingWatchlist.js").then((mod) => mod.schedulePushTrackingWatchlist());
}

export function toggleFollowCompany(id) {
  toggleTrackedCompany(id);
}

export const companyViews = ref(_readJson(VIEWS_KEY, {}));

export function recordCompanyView(id) {
  const target = String(id || "").trim();
  if (!target) return;
  const next = { ...companyViews.value };
  next[target] = (Number(next[target]) || 0) + 1;
  companyViews.value = next;
  _writeJson(VIEWS_KEY, next);
}

// Company-directory filters. These used to live inside ResearchDeskView,
// next to the directory column it owned; the column is now part of the
// sidebar, which is a different component, so the filters have to be
// somewhere both can see. Persisted, because a filter you set and then lose
// on navigation is worse than no filter.
const DESK_SECTOR_KEY = "bsh.deskSector";
const DESK_DIFFS_KEY = "bsh.deskDiffsOnly";

export const ALL_SECTORS = "All";

export const deskSector = ref(_readJson(DESK_SECTOR_KEY, ALL_SECTORS) || ALL_SECTORS);

export function setDeskSector(sector) {
  const next = String(sector || ALL_SECTORS);
  deskSector.value = next;
  _writeJson(DESK_SECTOR_KEY, next);
}

export const deskDiffsOnly = ref(Boolean(_readJson(DESK_DIFFS_KEY, false)));

export function setDeskDiffsOnly(on) {
  deskDiffsOnly.value = Boolean(on);
  _writeJson(DESK_DIFFS_KEY, deskDiffsOnly.value);
}

export function toggleDeskDiffsOnly() {
  setDeskDiffsOnly(!deskDiffsOnly.value);
}

/** Has this company been opened before?
 *
 * The desk kept its own `bsh.visitedCompanies` Set for exactly this, beside
 * the `companyViews` counter that already recorded it — one fact under two
 * keys, written from two places. `companyViews` wins: it is the one the
 * sidebar's "Most viewed" sort already reads, and App.vue records it on
 * every route change rather than only while the desk is mounted.
 */
export function hasVisitedCompany(id) {
  const key = String(id || "").trim();
  if (!key) return false;
  return (Number(companyViews.value[key]) || 0) > 0;
}

/** Whether a company should show under the "Diffs" filter: something has
 * changed on it, or it is worth attention and has never been opened. */
export function isCompanyModified(company) {
  if (!company) return false;
  if (company.is_modified || company.has_updates || company.modified) {
    return true;
  }
  if (hasVisitedCompany(company.id)) return false;
  return Boolean(company.reports_count > 0 || company.priority === "high");
}

export function postAuthPath(next) {
  if (
    typeof next === "string" &&
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.startsWith("/login")
  ) {
    if (next !== "/") return next;
  }
  const last = lastCompanyId.value;
  return last ? `/${encodeURIComponent(last)}` : "/";
}
