/**
 * Appearance (light / dark / auto).
 *
 * The dark palette existed in style.css from the start but nothing ever
 * applied the `.dark` class, so the app was effectively light-only. Apple
 * defaults to light mode, with an explicit system/dark override available.
 *
 * NOTE: index.html runs an inline copy of `resolve()` before first paint to
 * avoid a white flash on load. Keep the two in sync.
 */
import { computed, ref } from "vue";

const STORAGE_KEY = "bsh.research.appearance";
export const APPEARANCES = ["auto", "light", "dark"];

const media =
  typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return APPEARANCES.includes(raw) ? raw : "light";
  } catch {
    // Private browsing / storage disabled.
    return "light";
  }
}

export const appearance = ref(readStored());
export const isDark = computed(() => resolve(appearance.value));

function resolve(pref) {
  if (pref === "dark") return true;
  if (pref === "light") return false;
  return media ? media.matches : false;
}

function apply() {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", isDark.value);
}

export function setAppearance(next) {
  appearance.value = APPEARANCES.includes(next) ? next : "auto";
  try {
    localStorage.setItem(STORAGE_KEY, appearance.value);
  } catch {
    // Preference is best-effort; the in-memory value still drives the UI.
  }
  apply();
}

export function initAppearance() {
  apply();
  // Follow the system in "auto" mode, including live changes at sunset.
  media?.addEventListener?.("change", () => {
    if (appearance.value === "auto") apply();
  });
}
