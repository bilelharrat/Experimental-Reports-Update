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
