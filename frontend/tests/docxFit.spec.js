import { describe, expect, it } from "vitest";
import { clampZoom, docxPageWidth, fitZoom, nextZoomStep } from "../src/docxFit.js";

const section = (width) => ({ style: { width } });

describe("fitting a Word page to the viewer", () => {
  it("reads the page's own width from docx-preview's inline style", () => {
    expect(docxPageWidth(section("612pt"))).toBe(816); // US Letter
    expect(docxPageWidth(section("8.5in"))).toBe(816);
    expect(Math.round(docxPageWidth(section("21cm")))).toBe(794); // A4
    expect(docxPageWidth(section("700px"))).toBe(700);
  });

  it("falls back to a Letter page when the width can't be read", () => {
    expect(docxPageWidth(null)).toBe(816);
    expect(docxPageWidth(section(""))).toBe(816);
    expect(docxPageWidth(section("auto"))).toBe(816);
  });

  it("scales the page to the width there is", () => {
    expect(fitZoom(1224, 816)).toBe(1.5);
    expect(fitZoom(816, 816)).toBe(1);
  });

  it("shrinks for a narrow viewer and stops growing on a very wide one", () => {
    expect(fitZoom(600, 816)).toBeCloseTo(0.735, 3);
    expect(fitZoom(200, 816)).toBe(0.5);
    expect(fitZoom(3000, 816)).toBe(1.75);
  });

  it("leaves the page alone until it can be measured", () => {
    expect(fitZoom(0, 816)).toBe(1);
    expect(fitZoom(1000, 0)).toBe(1);
  });

  it("steps a hand-picked zoom the way Preview does, within 50% and 300%", () => {
    expect(nextZoomStep(1, 1)).toBe(1.1);
    expect(nextZoomStep(1, -1)).toBe(0.9);
    // From an in-between zoom (a pinch, or fit), the next step up or down.
    expect(nextZoomStep(1.156, 1)).toBe(1.25);
    expect(nextZoomStep(1.156, -1)).toBe(1.1);
    expect(nextZoomStep(3, 1)).toBe(3);
    expect(nextZoomStep(0.5, -1)).toBe(0.5);
    expect(clampZoom(9)).toBe(3);
    expect(clampZoom(0.1)).toBe(0.5);
    expect(clampZoom("nope")).toBe(1);
  });
});
