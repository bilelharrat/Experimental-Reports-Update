import { describe, expect, it } from "vitest";

import { POLL_MAX_FAILURES, pollDelayMs } from "../src/pollBackoff.js";

describe("report poll backoff policy", () => {
  it("polls at 1s while healthy", () => {
    expect(pollDelayMs(0)).toBe(1000);
  });

  it("backs off 1s -> 2s -> 5s as failures stack", () => {
    expect(pollDelayMs(1)).toBe(1000);
    expect(pollDelayMs(2)).toBe(2000);
    expect(pollDelayMs(3)).toBe(5000);
    expect(pollDelayMs(4)).toBe(5000);
  });

  it("gives up only after several consecutive failures", () => {
    // One blip during a 30-minute run must never kill the progress UI.
    expect(POLL_MAX_FAILURES).toBeGreaterThanOrEqual(3);
  });
});
