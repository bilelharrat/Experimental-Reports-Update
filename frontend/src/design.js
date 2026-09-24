/**
 * Design: Reactor (the workshop heads-up display), Bureau (the page on the
 * desk), Folio (paper and ink) or Summit Glass.
 *
 * Reactor is the default. Bureau, Folio and Summit Glass, the Mac twin the
 * app shipped with, stay one click away in Settings so they can be compared
 * on the same data. The choice is kept per browser.
 *
 * The design is an attribute on <html> (`data-design`), and reactor.css,
 * bureau.css and folio.css scope everything they change under it. Views
 * don't read the choice: they pick the design up from the stylesheet. The
 * shell is the exception — a design in DESK_TAB_DESIGNS (Reactor, Bureau)
 * sets the desks as tabs across the masthead (Sidebar.vue, App.vue) and
 * folds the company list to a rail (`companyIndexOpen` in state.js) — and a
 * design in DARK_ONLY_DESIGNS (Reactor) keeps the page dark whatever the
 * Appearance setting says (appearance.js).
 *
 * NOTE: index.html applies the stored choice before first paint so the page
 * never flashes another design. Keep the two in sync.
 */
import { computed, ref } from "vue";

const STORAGE_KEY = "bsh.research.design";
export const DESIGNS = ["reactor", "bureau", "folio", "glass"];
export const DEFAULT_DESIGN = "reactor";

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

/** Designs whose shell carries the desks as tabs across the masthead and
 *  keeps the company list as a rail of logos. */
export const DESK_TAB_DESIGNS = ["reactor", "bureau"];

/** True while such a design is on: the shell reads this to rearrange itself. */
export const desksAsTabs = computed(() => DESK_TAB_DESIGNS.includes(design.value));

/** Designs drawn in light on a dark field, which have no light appearance. */
export const DARK_ONLY_DESIGNS = ["reactor"];

/** True while such a design is on: appearance.js keeps the page dark. */
export const forcesDark = computed(() => DARK_ONLY_DESIGNS.includes(design.value));

// The browser chrome (Safari's bar, a phone's status area) takes the page's
// ground: Reactor's black, Bureau's green desk, Folio's paper, Summit's
// neutral. Mirrors index.html.
const THEME_COLORS = {
  reactor: { light: "#03060b", dark: "#03060b" },
  bureau: { light: "#0f1f1a", dark: "#080d0b" },
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
