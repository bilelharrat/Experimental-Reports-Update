import { beforeEach, describe, expect, it } from "vitest";

import {
  COPILOT_DEFAULT_WIDTH,
  COPILOT_MAX_WIDTH,
  COPILOT_MIN_WIDTH,
  clampCopilotWidth,
  fitCopilotWidth,
  readCopilotWidth,
  writeCopilotWidth,
} from "../src/copilotWidth.js";

describe("copilot rail width", () => {
  beforeEach(() => window.localStorage.clear());

  it("keeps a drag between the handles", () => {
    expect(clampCopilotWidth(500)).toBe(500);
    expect(clampCopilotWidth(10)).toBe(COPILOT_MIN_WIDTH);
    expect(clampCopilotWidth(5000)).toBe(COPILOT_MAX_WIDTH);
    expect(clampCopilotWidth("512")).toBe(512);
    expect(clampCopilotWidth("wide")).toBe(COPILOT_DEFAULT_WIDTH);
  });

  it("leaves the desk behind it usable", () => {
    // A 1440px window gives the rail at most 864px...
    expect(fitCopilotWidth(880, 1440)).toBe(864);
    // ...and a narrow one still gets a usable rail rather than a sliver.
    expect(fitCopilotWidth(720, 900)).toBe(540);
    expect(fitCopilotWidth(720, 400)).toBe(COPILOT_MIN_WIDTH);
  });

  it("remembers the width, and shrugs off a bad one", () => {
    expect(readCopilotWidth()).toBe(COPILOT_DEFAULT_WIDTH);
    writeCopilotWidth(640);
    expect(readCopilotWidth()).toBe(640);
    window.localStorage.setItem("bsh.copilot.width", "not-a-number");
    expect(readCopilotWidth()).toBe(COPILOT_DEFAULT_WIDTH);
  });
});
