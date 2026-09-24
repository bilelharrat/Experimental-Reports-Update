/**
 * Design: Folio (paper and ink) or Summit Glass.
 *
 * Folio is the default. Summit Glass, the Mac twin the app shipped with,
 * stays one click away in Settings while Folio is new, so the two can be
 * compared on the same data. The choice is kept per browser.
 *
 * The design is an attribute on <html> (`data-design`), and folio.css
 * scopes everything it changes under it. Nothing else in the app reads the
 * choice: every view picks the design up from the stylesheet.
 *
 * NOTE: index.html applies the stored choice before first paint so the page
 * never flashes the other design. Keep the two in sync.
 */
import { ref } from "vue";

const STORAGE_KEY = "bsh.research.design";
export const DESIGNS = ["folio", "glass"];
export const DEFAULT_DESIGN = "folio";

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return DESIGNS.includes(raw) ? raw : DEFAULT_DESIGN;
  } catch {
    // Private browsing / storage disabled.
    return DEFAULT_DESIGN;
  }
}

export const design = ref(readStored());

// The browser chrome (Safari's bar, a phone's status area) takes the page's
// ground: paper for Folio, Summit's neutral otherwise. Mirrors index.html.
const THEME_COLORS = {
  folio: { light: "#f4f2ed", dark: "#161513" },
  glass: { light: "#f4f4f6", dark: "#111113" },
};

function apply() {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.design = design.value;
  const colors = THEME_COLORS[design.value] || THEME_COLORS[DEFAULT_DESIGN];
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
    const dark = String(meta.getAttribute("media") || "").includes("dark");
    meta.setAttribute("content", dark ? colors.dark : colors.light);
  }
}

export function setDesign(next) {
  design.value = DESIGNS.includes(next) ? next : DEFAULT_DESIGN;
  try {
    localStorage.setItem(STORAGE_KEY, design.value);
  } catch {
    // Best-effort, like the appearance preference.
  }
  apply();
}

export function initDesign() {
  apply();
}
