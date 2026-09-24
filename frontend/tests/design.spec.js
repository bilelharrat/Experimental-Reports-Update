import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  BUREAU_DESKS,
  BUREAU_DESK_COLORS,
  DEFAULT_BUREAU_DESK,
  DEFAULT_DESIGN,
  DESIGNS,
  bureauDesk,
  design,
  desksAsTabs,
  initDesign,
  setBureauDesk,
  setDesign,
} from "../src/design.js";

// Summit Glass (the original) is the default design; Bureau and Folio stay
// one click away in Settings. The choice is an attribute on <html> that
// bureau.css and folio.css scope themselves under, and the browser chrome
// takes the matching ground. Bureau's desk color is a second attribute,
// data-desk, with Onyx & White the default.

const HERE = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = path.join(HERE, "..", "index.html");
const DESKS_CSS = path.join(HERE, "..", "src", "bureau-desks.css");

function themeColors() {
  return [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => m.getAttribute("content"));
}

/** Run index.html's own pre-paint script, as the browser does before first paint. */
function runPrePaint() {
  const html = readFileSync(INDEX_HTML, "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  delete document.documentElement.dataset.design;
  delete document.documentElement.dataset.desk;
  new Function(script)();
  return {
    design: document.documentElement.dataset.design,
    desk: document.documentElement.dataset.desk,
    chrome: themeColors(),
  };
}

const hexToTriplet = (hex) => [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16)).join(" ");

describe("design", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.head.innerHTML = `
      <meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
      <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000" />`;
    delete document.documentElement.dataset.design;
    delete document.documentElement.dataset.desk;
    setDesign(DEFAULT_DESIGN);
    setBureauDesk(DEFAULT_BUREAU_DESK);
    window.localStorage.clear();
  });

  it("wears Summit Glass unless told otherwise", () => {
    expect(DEFAULT_DESIGN).toBe("glass");
    expect(DESIGNS).toEqual(["glass", "bureau", "folio"]);
    initDesign();
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(desksAsTabs.value).toBe(false);
    expect(themeColors()).toEqual(["#f4f4f6", "#111113"]);
  });

  it("switches to Bureau, remembers it, and gives the browser chrome its desk", () => {
    setDesign("bureau");
    expect(design.value).toBe("bureau");
    expect(desksAsTabs.value).toBe(true);
    expect(document.documentElement.dataset.design).toBe("bureau");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("bureau");
    // Onyx & White: a white desk by day, a black one by night.
    expect(themeColors()).toEqual(["#ffffff", "#050505"]);
  });

  it("switches to Folio, remembers it, and repaints the browser chrome", () => {
    setDesign("folio");
    expect(design.value).toBe("folio");
    expect(desksAsTabs.value).toBe(false);
    expect(document.documentElement.dataset.design).toBe("folio");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("folio");
    expect(themeColors()).toEqual(["#f4f2ed", "#161513"]);
  });

  it("switches back to Summit Glass, remembers it, and repaints the browser chrome", () => {
    setDesign("folio");
    setDesign("glass");
    expect(design.value).toBe("glass");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("glass");
    expect(themeColors()).toEqual(["#f4f4f6", "#111113"]);
  });

  it("falls back to Summit Glass for a value it doesn't know", () => {
    setDesign("bureau");
    setDesign("neon");
    expect(design.value).toBe("glass");
    expect(document.documentElement.dataset.design).toBe("glass");
  });

  it("keeps a design this browser already chose", async () => {
    window.localStorage.setItem("bsh.research.design", "bureau");
    vi.resetModules();
    const fresh = await import("../src/design.js");
    expect(fresh.design.value).toBe("bureau");
  });
});

describe("Bureau's desk color", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.head.innerHTML = `
      <meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
      <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000" />`;
    setDesign("bureau");
    setBureauDesk(DEFAULT_BUREAU_DESK);
    window.localStorage.clear();
  });

  it("is Onyx & White unless told otherwise, and one of seven", () => {
    expect(DEFAULT_BUREAU_DESK).toBe("onyx");
    expect(BUREAU_DESKS).toEqual(["onyx", "green", "maroon", "navy", "aubergine", "tobacco", "graphite"]);
    expect(Object.keys(BUREAU_DESK_COLORS).sort()).toEqual([...BUREAU_DESKS].sort());
    initDesign();
    expect(document.documentElement.dataset.desk).toBe("onyx");
    expect(bureauDesk.value).toBe("onyx");
  });

  it("applies a desk at once, remembers it, and repaints the browser chrome", () => {
    setBureauDesk("maroon");
    expect(bureauDesk.value).toBe("maroon");
    expect(document.documentElement.dataset.desk).toBe("maroon");
    expect(window.localStorage.getItem("bsh.research.bureauDesk")).toBe("maroon");
    expect(themeColors()).toEqual(["#50121e", "#16060a"]);

    // Today's bottle green is still there.
    setBureauDesk("green");
    expect(document.documentElement.dataset.desk).toBe("green");
    expect(themeColors()).toEqual(["#0f1f1a", "#080d0b"]);
  });

  it("falls back to Onyx & White for a desk it doesn't know", () => {
    setBureauDesk("navy");
    setBureauDesk("chartreuse");
    expect(bureauDesk.value).toBe("onyx");
    expect(document.documentElement.dataset.desk).toBe("onyx");
    setBureauDesk(undefined);
    expect(bureauDesk.value).toBe("onyx");
  });

  it("keeps the desk while another design is on, for when Bureau comes back", () => {
    setDesign("folio");
    setBureauDesk("tobacco");
    expect(document.documentElement.dataset.desk).toBe("tobacco");
    // The chrome follows the design that is on: Folio's paper, not the desk.
    expect(themeColors()).toEqual(["#f4f2ed", "#161513"]);
    setDesign("bureau");
    expect(themeColors()).toEqual(["#362212", "#0b0805"]);
  });

  it("reads the stored desk at start and ignores one it doesn't know", async () => {
    window.localStorage.setItem("bsh.research.bureauDesk", "graphite");
    vi.resetModules();
    let fresh = await import("../src/design.js");
    expect(fresh.bureauDesk.value).toBe("graphite");

    window.localStorage.setItem("bsh.research.bureauDesk", "chartreuse");
    vi.resetModules();
    fresh = await import("../src/design.js");
    expect(fresh.bureauDesk.value).toBe("onyx");
  });

  it("has a day and a night in bureau-desks.css for every desk but the green", () => {
    const css = readFileSync(DESKS_CSS, "utf8");
    // bureau.css is written in the green: it needs no overrides.
    expect(css).not.toContain('[data-desk="green"]');
    for (const id of BUREAU_DESKS.filter((desk) => desk !== "green")) {
      const [day, night] = BUREAU_DESK_COLORS[id].desk;
      const dayBlock = css.match(new RegExp(`\\[data-desk="${id}"\\]:not\\(\\.dark\\) \\{([^}]*)\\}`));
      const nightBlock = css.match(new RegExp(`\\[data-desk="${id}"\\]\\.dark \\{([^}]*)\\}`));
      expect(dayBlock, id).not.toBeNull();
      expect(nightBlock, id).not.toBeNull();
      // The swatches and the browser chrome show the desk the stylesheet paints.
      expect(dayBlock[1]).toContain(`--bureau-frame: ${hexToTriplet(day)};`);
      expect(nightBlock[1]).toContain(`--bureau-frame: ${hexToTriplet(night)};`);
    }
  });
});

describe("before first paint (index.html)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.head.innerHTML = `
      <meta name="theme-color" media="(prefers-color-scheme: light)" content="#ffffff" />
      <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#000000" />`;
  });

  it("wears Summit Glass on a fresh browser, with Onyx & White ready for Bureau", () => {
    expect(runPrePaint()).toEqual({ design: "glass", desk: "onyx", chrome: ["#f4f4f6", "#111113"] });
  });

  it("applies the stored design and desk from the same keys as design.js", () => {
    window.localStorage.setItem("bsh.research.design", "bureau");
    window.localStorage.setItem("bsh.research.bureauDesk", "maroon");
    expect(runPrePaint()).toEqual({ design: "bureau", desk: "maroon", chrome: ["#50121e", "#16060a"] });

    window.localStorage.setItem("bsh.research.design", "folio");
    expect(runPrePaint()).toEqual({ design: "folio", desk: "maroon", chrome: ["#f4f2ed", "#161513"] });
  });

  it("falls back to Summit Glass and Onyx & White for values it doesn't know", () => {
    window.localStorage.setItem("bsh.research.design", "neon");
    window.localStorage.setItem("bsh.research.bureauDesk", "chartreuse");
    expect(runPrePaint()).toMatchObject({ design: "glass", desk: "onyx" });

    window.localStorage.setItem("bsh.research.design", "bureau");
    window.localStorage.setItem("bsh.research.bureauDesk", "__proto__");
    expect(runPrePaint()).toEqual({ design: "bureau", desk: "onyx", chrome: ["#ffffff", "#050505"] });
  });

  it("knows every desk design.js knows, in the same colors", () => {
    for (const id of BUREAU_DESKS) {
      window.localStorage.setItem("bsh.research.design", "bureau");
      window.localStorage.setItem("bsh.research.bureauDesk", id);
      expect(runPrePaint(), id).toEqual({ design: "bureau", desk: id, chrome: BUREAU_DESK_COLORS[id].desk });
    }
  });
});
