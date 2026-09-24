import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_DESIGN, DESIGNS, design, initDesign, setDesign } from "../src/design.js";

// Folio (paper and ink) is the default design; Summit Glass stays one click
// away in Settings. The choice is an attribute on <html> that folio.css
// scopes itself under, and the browser chrome takes the matching ground.

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

  it("wears Folio unless told otherwise", () => {
    expect(DEFAULT_DESIGN).toBe("folio");
    expect(DESIGNS).toEqual(["folio", "glass"]);
    initDesign();
    expect(document.documentElement.dataset.design).toBe("folio");
    expect(themeColors()).toEqual(["#f4f2ed", "#161513"]);
  });

  it("switches to Summit Glass, remembers it, and repaints the browser chrome", () => {
    setDesign("glass");
    expect(design.value).toBe("glass");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(window.localStorage.getItem("bsh.research.design")).toBe("glass");
    expect(themeColors()).toEqual(["#f4f4f6", "#111113"]);
  });

  it("falls back to Folio for a value it doesn't know", () => {
    setDesign("glass");
    setDesign("neon");
    expect(design.value).toBe("folio");
    expect(document.documentElement.dataset.design).toBe("folio");
  });

  it("is applied before first paint by index.html, from the same key", () => {
    const html = readFileSync(INDEX_HTML, "utf8");
    expect(html).toContain('localStorage.getItem("bsh.research.design") === "glass"');
    expect(html).toContain('setAttribute("data-design", design)');
    expect(html).toContain('content="#f4f2ed"');
  });
});
