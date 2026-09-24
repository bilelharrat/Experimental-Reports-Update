/**
 * Appearance (light / dark / auto).
 *
 * Like the Mac terminal, the web app follows the system appearance by
 * default: dark only when the Mac itself is dark. An explicit Light or Dark
 * choice in Settings overrides it.
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
    return APPEARANCES.includes(raw) ? raw : "auto";
  } catch {
    // Private browsing / storage disabled.
    return "auto";
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
