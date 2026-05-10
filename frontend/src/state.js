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
