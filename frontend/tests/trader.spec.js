// Pure-function tests for frontend/src/trader.js.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  STALENESS,
  cardStaleness,
  stalenessColor,
  relativeAge,
  fmtPct,
  fmtPrice,
  fmtCount,
  changeBias,
} from "../src/trader.js";

describe("cardStaleness", () => {
  const FROZEN_NOW = Date.parse("2026-05-13T18:00:00Z");

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FROZEN_NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns 'unknown' for null / unparseable input", () => {
    expect(cardStaleness(null, "price_card")).toBe("unknown");
    expect(cardStaleness("not-a-date", "price_card")).toBe("unknown");
    expect(cardStaleness("2026-05-13T17:55:00Z", "unknown_card")).toBe("unknown");
  });

  it("price_card: <1h is fresh, 1-4h is warn, >=4h is stale", () => {
    expect(cardStaleness("2026-05-13T17:30:00Z", "price_card")).toBe("fresh");
    expect(cardStaleness("2026-05-13T15:30:00Z", "price_card")).toBe("warn");
    expect(cardStaleness("2026-05-13T13:00:00Z", "price_card")).toBe("stale");
  });

  it("sentiment_card is more forgiving than price (24h / 7d)", () => {
    expect(cardStaleness("2026-05-13T05:00:00Z", "sentiment_card")).toBe("fresh");
    expect(cardStaleness("2026-05-10T18:00:00Z", "sentiment_card")).toBe("warn");
    expect(cardStaleness("2026-04-01T18:00:00Z", "sentiment_card")).toBe("stale");
  });

  it("every card from the spec table is present", () => {
    for (const key of [
      "price_card", "momentum_card", "sentiment_card",
      "heat_card", "catalysts", "trader_news",
    ]) {
      expect(STALENESS[key]).toBeDefined();
    }
  });
});

describe("stalenessColor", () => {
  it("maps buckets to color labels", () => {
    expect(stalenessColor("fresh")).toBe("fresh");
    expect(stalenessColor("warn")).toBe("warn");
    expect(stalenessColor("stale")).toBe("stale");
    expect(stalenessColor("unknown")).toBe("unknown");
  });
});

describe("relativeAge", () => {
  const FROZEN_NOW = Date.parse("2026-05-13T18:00:00Z");

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FROZEN_NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("formats minutes, hours, days, weeks", () => {
    expect(relativeAge("2026-05-13T17:58:00Z")).toBe("2 min ago");
    expect(relativeAge("2026-05-13T15:00:00Z")).toBe("3h ago");
    expect(relativeAge("2026-05-10T18:00:00Z")).toBe("3d ago");
    expect(relativeAge("2026-04-20T18:00:00Z")).toBe("3w ago");
  });

  it("returns empty for missing / unparseable input", () => {
    expect(relativeAge(null)).toBe("");
    expect(relativeAge(undefined)).toBe("");
    expect(relativeAge("nonsense")).toBe("");
  });

  it("under a minute is 'just now'", () => {
    expect(relativeAge("2026-05-13T17:59:30Z")).toBe("just now");
  });
});

describe("fmtPct", () => {
  it("signs and rounds to one decimal", () => {
    expect(fmtPct(1.82)).toBe("+1.8%");
    expect(fmtPct(-3.45)).toBe("-3.5%");
    expect(fmtPct(0)).toBe("0.0%");
  });
  it("dashes out non-numeric input", () => {
    expect(fmtPct(null)).toBe("—");
    expect(fmtPct(undefined)).toBe("—");
    expect(fmtPct("nan")).toBe("—");
  });
});

describe("fmtPrice", () => {
  it("picks 2 decimals for >=1, 4 for sub-$1", () => {
    expect(fmtPrice(174.22, "USD")).toBe("$174.22");
    expect(fmtPrice(0.0042, "USD")).toBe("$0.0042");
  });
  it("dashes out non-numeric input", () => {
    expect(fmtPrice(null, "USD")).toBe("—");
  });
});

describe("changeBias", () => {
  it("buckets up / down / flat", () => {
    expect(changeBias(1.5)).toBe("up");
    expect(changeBias(-0.1)).toBe("down");
    expect(changeBias(0)).toBe("flat");
    expect(changeBias(null)).toBe("flat");
  });
});

describe("fmtCount", () => {
  it("rounds to a whole-number string", () => {
    expect(fmtCount(18)).toBe("18");
    expect(fmtCount(0)).toBe("0");
    expect(fmtCount(null)).toBe("—");
  });
});
