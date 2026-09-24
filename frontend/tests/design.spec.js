import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_DESIGN, DESIGNS, design, initDesign, desksAsTabs, setDesign } from "../src/design.js";

// Bureau (the page on the desk) is the default design; Folio and Summit
// Glass stay one click away in Settings. The choice is an attribute on
// <html> that bureau.css and folio.css scope themselves under, and the
// browser chrome takes the matching ground.

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

  it("wears Bureau unless told otherwise", () => {
    expect(DEFAULT_DESIGN).toBe("bureau");
    expect(DESIGNS).toEqual(["bureau", "folio", "glass"]);
    initDesign();
    expect(document.documentElement.dataset.design).toBe("bureau");
    expect(desksAsTabs.value).toBe(true);
    // The browser chrome takes the desk's green.
    expect(themeColors()).toEqual(["#0f1f1a", "#080d0b"]);
  });

  it("switches to Folio, remembers it, and repaints the browser chrome", () => {
    setDesign("folio");
    expect(design.value).toBe("folio");
    expect(desksAsTabs.value).toBe(false);
    expect(document.documentElement.dataset.design).toBe("folio");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("folio");
    expect(themeColors()).toEqual(["#f4f2ed", "#161513"]);
  });

  it("switches to Summit Glass, remembers it, and repaints the browser chrome", () => {
    setDesign("glass");
    expect(design.value).toBe("glass");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("glass");
    expect(themeColors()).toEqual(["#f4f4f6", "#111113"]);
  });

  it("falls back to Bureau for a value it doesn't know", () => {
    setDesign("glass");
    setDesign("neon");
    expect(design.value).toBe("bureau");
    expect(document.documentElement.dataset.design).toBe("bureau");
  });

  it("is applied before first paint by index.html, from the same key", () => {
    const html = readFileSync(INDEX_HTML, "utf8");
    expect(html).toContain('var design = "bureau"');
    expect(html).toContain('localStorage.getItem("bsh.research.design")');
    expect(html).toContain('chosen === "folio" || chosen === "glass"');
    expect(html).toContain('setAttribute("data-design", design)');
    // The chrome color is set before first paint too, for every design.
    expect(html).toContain('content="#0f1f1a"');
    for (const ground of ["#0f1f1a", "#080d0b", "#f4f2ed", "#161513", "#f4f4f6", "#111113"]) {
      expect(html).toContain(`"${ground}"`);
    }
  });
});
