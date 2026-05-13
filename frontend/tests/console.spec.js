// Pure-function tests for frontend/src/console.js.
// Mirrors §11.3 in docs/console-feature.md.

import { describe, expect, it } from "vitest";
import {
  usageToMeter,
  formatTokens,
  formatCost,
  validateAttachment,
  CONTEXT_WINDOW,
  WARNING_THRESHOLD,
  LOCK_THRESHOLD,
  ATTACHMENT_MAX_BYTES,
} from "../src/console.js";

describe("usageToMeter — token-math helper", () => {
  it("zero usage → 0% used, green / ok", () => {
    const m = usageToMeter(null);
    expect(m.used).toBe(0);
    expect(m.pct_used).toBe(0);
    expect(m.pct_free).toBe(1);
    expect(m.state).toBe("ok");
    expect(m.color).toBe("green");
  });

  it("sums input + cache_read + cache_creation (NOT output)", () => {
    const m = usageToMeter({
      input_tokens: 1000,
      output_tokens: 500,
      cache_read_input_tokens: 300_000,
      cache_creation_input_tokens: 25_000,
    });
    expect(m.used).toBe(326_000);
    expect(m.pct_used).toBeCloseTo(0.326, 5);
  });

  it("transitions to warning at exactly 75%", () => {
    const m = usageToMeter({
      input_tokens: CONTEXT_WINDOW * WARNING_THRESHOLD,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(m.state).toBe("warning");
    expect(m.color).toBe("yellow");
  });

  it("stays green just below the warning line", () => {
    const m = usageToMeter({
      input_tokens: CONTEXT_WINDOW * WARNING_THRESHOLD - 1,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(m.state).toBe("ok");
    expect(m.color).toBe("green");
  });

  it("locks at 90%", () => {
    const m = usageToMeter({
      input_tokens: CONTEXT_WINDOW * LOCK_THRESHOLD,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(m.state).toBe("locked");
    expect(m.color).toBe("red");
  });

  it("clamps pct_free at 0 once over the window", () => {
    const m = usageToMeter({
      input_tokens: CONTEXT_WINDOW * 1.1,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(m.pct_free).toBe(0);
  });
});

describe("formatTokens", () => {
  it("returns '0' for missing / zero", () => {
    expect(formatTokens(undefined)).toBe("0");
    expect(formatTokens(0)).toBe("0");
  });
  it("uses K for >=1_000 and M for >=1_000_000", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(12_400)).toBe("12K");
    expect(formatTokens(342_000)).toBe("342K");
    expect(formatTokens(1_050_000)).toBe("1.1M");
  });
});

describe("formatCost", () => {
  it("formats dollars with appropriate precision", () => {
    expect(formatCost(0.018)).toBe("$0.018");
    expect(formatCost(0.412)).toBe("$0.412");
    expect(formatCost(1.2)).toBe("$1.20");
    expect(formatCost(undefined)).toBe("$0.00");
  });
});

describe("validateAttachment", () => {
  it("rejects a missing file", () => {
    const err = validateAttachment(null);
    expect(err.code).toBe("missing");
  });

  it("rejects an oversize file", () => {
    const file = { name: "big.png", type: "image/png", size: ATTACHMENT_MAX_BYTES + 1 };
    const err = validateAttachment(file);
    expect(err.code).toBe("attachment_too_large");
  });

  it("accepts PNG / JPEG / WebP by MIME", () => {
    expect(
      validateAttachment({ name: "a.png", type: "image/png", size: 1000 }),
    ).toBeNull();
    expect(
      validateAttachment({ name: "a.jpg", type: "image/jpeg", size: 1000 }),
    ).toBeNull();
    expect(
      validateAttachment({ name: "a.webp", type: "image/webp", size: 1000 }),
    ).toBeNull();
  });

  it("accepts allowed extensions when MIME is missing", () => {
    expect(
      validateAttachment({ name: "a.png", type: "", size: 100 }),
    ).toBeNull();
  });

  it("rejects unsupported types", () => {
    expect(
      validateAttachment({ name: "a.gif", type: "image/gif", size: 100 }).code,
    ).toBe("attachment_type_not_allowed");
    expect(
      validateAttachment({ name: "a.svg", type: "image/svg+xml", size: 100 }).code,
    ).toBe("attachment_type_not_allowed");
  });
});
