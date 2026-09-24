import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";

import {
  DEFAULT_DESIGN,
  DESIGNS,
  design,
  desksAsTabs,
  forcesDark,
  initDesign,
  setDesign,
} from "../src/design.js";
import { appearance, initAppearance, isDark, setAppearance } from "../src/appearance.js";

// Reactor (the workshop heads-up display) is the default design; Bureau,
// Folio and Summit Glass stay one click away in Settings. The choice is an
// attribute on <html> that each design's stylesheet scopes itself under,
// and the browser chrome takes the matching ground.

const INDEX_HTML = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "index.html");

function themeColors() {
  return [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => m.getAttribute("content"));
}

describe("design", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.head.innerHTML = `
      <meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
      <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000" />`;
    delete document.documentElement.dataset.design;
    setDesign(DEFAULT_DESIGN);
    window.localStorage.clear();
  });

  it("wears Reactor unless told otherwise", () => {
    expect(DEFAULT_DESIGN).toBe("reactor");
    expect(DESIGNS).toEqual(["reactor", "bureau", "folio", "glass"]);
    initDesign();
    expect(document.documentElement.dataset.design).toBe("reactor");
    // The browser chrome takes the workshop's black, in either appearance.
    expect(themeColors()).toEqual(["#03060b", "#03060b"]);
  });

  it("sets the desks as tabs under Reactor and Bureau only", () => {
    const tabbed = {};
    for (const name of DESIGNS) {
      setDesign(name);
      tabbed[name] = desksAsTabs.value;
    }
    expect(tabbed).toEqual({ reactor: true, bureau: true, folio: false, glass: false });
  });

  it("is dark-only under Reactor alone", () => {
    const dark = {};
    for (const name of DESIGNS) {
      setDesign(name);
      dark[name] = forcesDark.value;
    }
    expect(dark).toEqual({ reactor: true, bureau: false, folio: false, glass: false });
  });

  it("switches to Bureau, remembers it, and repaints the browser chrome", () => {
    setDesign("bureau");
    expect(design.value).toBe("bureau");
    expect(document.documentElement.dataset.design).toBe("bureau");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("bureau");
    expect(themeColors()).toEqual(["#0f1f1a", "#080d0b"]);
  });

  it("switches to Folio and to Summit Glass", () => {
    setDesign("folio");
    expect(document.documentElement.dataset.design).toBe("folio");
    expect(themeColors()).toEqual(["#f4f2ed", "#161513"]);
    setDesign("glass");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("glass");
    expect(themeColors()).toEqual(["#f4f4f6", "#111113"]);
  });

  it("falls back to Reactor for a value it doesn't know", () => {
    setDesign("glass");
    setDesign("neon");
    expect(design.value).toBe("reactor");
    expect(document.documentElement.dataset.design).toBe("reactor");
  });

  it("is applied before first paint by index.html, from the same key", () => {
    const html = readFileSync(INDEX_HTML, "utf8");
    expect(html).toContain('var design = "reactor"');
    expect(html).toContain('localStorage.getItem("bsh.research.design")');
    expect(html).toContain('chosen === "bureau" || chosen === "folio" || chosen === "glass"');
    expect(html).toContain('setAttribute("data-design", design)');
    // Reactor is dark before first paint whatever the appearance says.
    expect(html).toContain('if (design === "reactor") dark = true;');
    // The chrome color is set before first paint too, for every design.
    expect(html).toContain('content="#03060b"');
    for (const ground of ["#03060b", "#0f1f1a", "#080d0b", "#f4f2ed", "#161513", "#f4f4f6", "#111113"]) {
      expect(html).toContain(`"${ground}"`);
    }
  });
});

describe("appearance under a dark-only design", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    setDesign("bureau");
    setAppearance("light");
    initAppearance();
  });

  it("keeps the page dark under Reactor whatever Appearance says, and lets go after", async () => {
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    setDesign("reactor");
    await nextTick();
    expect(isDark.value).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    // Choosing Light again under Reactor keeps it dark but is remembered…
    setAppearance("light");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(appearance.value).toBe("light");
    expect(window.localStorage.getItem("bsh.research.appearance")).toBe("light");

    // …and applies as soon as a design with a light appearance is back.
    setDesign("bureau");
    await nextTick();
    expect(isDark.value).toBe(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
