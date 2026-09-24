/**
 * Design: Summit Glass (the original), Bureau (the page on the desk) or
 * Folio (paper and ink).
 *
 * Summit Glass, the Mac twin the app shipped with, is the default. Bureau
 * and Folio stay one click away in Settings and in the welcome tour's
 * "Choose a look" step, so the three can be compared on the same data. The
 * choice is kept per browser.
 *
 * The design is an attribute on <html> (`data-design`), and bureau.css and
 * folio.css scope everything they change under it. Views don't read the
 * choice: they pick the design up from the stylesheet. The shell is the one
 * exception — a design in DESK_TAB_DESIGNS (Bureau) sets the desks as tabs
 * across the masthead (Sidebar.vue, App.vue) and folds the company list to a
 * rail (`companyIndexOpen` in state.js).
 *
 * Bureau's desk, the frame the page lies on, comes in several colors
 * (BUREAU_DESKS). The desk is a second attribute on <html> (`data-desk`),
 * kept per browser like the design; bureau-desks.css scopes each color under
 * it. Onyx & White (a white desk by day, a black one by night) is the
 * default; bureau.css itself is written in the bottle green.
 *
 * NOTE: index.html applies both stored choices before first paint so the page
 * never flashes another design or desk. Keep the two in sync.
 */
import { computed, ref } from "vue";

const STORAGE_KEY = "bsh.research.design";
const DESK_STORAGE_KEY = "bsh.research.bureauDesk";

/** In the order Settings and the welcome tour offer them. */
export const DESIGNS = ["glass", "bureau", "folio"];
export const DEFAULT_DESIGN = "glass";

/** Bureau's desk colors, in the order Settings offers them. */
export const BUREAU_DESKS = ["onyx", "green", "maroon", "navy", "aubergine", "tobacco", "graphite"];
export const DEFAULT_BUREAU_DESK = "onyx";

/**
 * Each desk's ground and sheet as [by day, by night]: the swatches in
 * Settings and the welcome tour, and the browser chrome while Bureau is on.
 * Mirrors bureau.css (green), bureau-desks.css (the rest) and index.html.
 */
export const BUREAU_DESK_COLORS = {
  onyx: { desk: ["#ffffff", "#050505"], sheet: ["#f1f0ec", "#181818"] },
  green: { desk: ["#0f1f1a", "#080d0b"], sheet: ["#f7f4ec", "#151d1a"] },
  maroon: { desk: ["#50121e", "#16060a"], sheet: ["#f7f4ec", "#231318"] },
  navy: { desk: ["#101c34", "#060910"], sheet: ["#f7f4ec", "#141923"] },
  aubergine: { desk: ["#30162e", "#0c070c"], sheet: ["#f7f4ec", "#1e161e"] },
  tobacco: { desk: ["#362212", "#0b0805"], sheet: ["#f7f4ec", "#221b16"] },
  graphite: { desk: ["#1e2228", "#08090b"], sheet: ["#f7f4ec", "#191c22"] },
};

function readStored(key, allowed, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return allowed.includes(raw) ? raw : fallback;
  } catch {
    // Private browsing / storage disabled.
    return fallback;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Best-effort, like the appearance preference.
  }
}

export const design = ref(readStored(STORAGE_KEY, DESIGNS, DEFAULT_DESIGN));
export const bureauDesk = ref(readStored(DESK_STORAGE_KEY, BUREAU_DESKS, DEFAULT_BUREAU_DESK));

/** Designs whose shell carries the desks as tabs across the masthead and
 *  keeps the company list as a rail of logos. */
export const DESK_TAB_DESIGNS = ["bureau"];

/** True while such a design is on: the shell reads this to rearrange itself. */
export const desksAsTabs = computed(() => DESK_TAB_DESIGNS.includes(design.value));

// The browser chrome (Safari's bar, a phone's status area) takes the page's
// ground: Bureau's desk, Folio's paper, Summit's neutral. Mirrors index.html.
const THEME_COLORS = {
  folio: ["#f4f2ed", "#161513"],
  glass: ["#f4f4f6", "#111113"],
};

function themeColors() {
  if (design.value === "bureau") {
    return (BUREAU_DESK_COLORS[bureauDesk.value] || BUREAU_DESK_COLORS[DEFAULT_BUREAU_DESK]).desk;
  }
  return THEME_COLORS[design.value] || THEME_COLORS[DEFAULT_DESIGN];
}

function apply() {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.design = design.value;
  root.dataset.desk = bureauDesk.value;
  const [light, dark] = themeColors();
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
    const isDark = String(meta.getAttribute("media") || "").includes("dark");
    meta.setAttribute("content", isDark ? dark : light);
  }
}

export function setDesign(next) {
  design.value = DESIGNS.includes(next) ? next : DEFAULT_DESIGN;
  store(STORAGE_KEY, design.value);
  apply();
}

/** Bureau's desk color. It is kept (and set on <html>) whatever the design,
 *  so coming back to Bureau finds the desk it left. */
export function setBureauDesk(next) {
  bureauDesk.value = BUREAU_DESKS.includes(next) ? next : DEFAULT_BUREAU_DESK;
  store(DESK_STORAGE_KEY, bureauDesk.value);
  apply();
}

export function initDesign() {
  apply();
}
