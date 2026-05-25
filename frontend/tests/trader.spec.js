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

describe("cardStaleness (trading-session based)", () => {
  // NYSE close is 16:00 ET. May 2026 is EDT (UTC-4): Fri 2026-05-15
  // close = 20:00Z, Mon 2026-05-18 close = 20:00Z. Memorial Day 2026 =
  // Mon 2026-05-25 (market closed).
  afterEach(() => vi.useRealTimers());
  const at = (iso) => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(iso));
  };

  it("returns 'unknown' for null / unparseable input or unknown card", () => {
    at("2026-05-18T18:00:00Z");
    expect(cardStaleness(null, "price_card")).toBe("unknown");
    expect(cardStaleness("not-a-date", "price_card")).toBe("unknown");
    expect(cardStaleness("2026-05-18T17:55:00Z", "unknown_card")).toBe("unknown");
  });

  it("Friday-after-close run stays FRESH through the weekend until Monday's close", () => {
    const friAfterClose = "2026-05-15T20:30:00Z"; // 16:30 ET Fri
    at("2026-05-16T12:00:00Z"); // Saturday
    expect(cardStaleness(friAfterClose, "price_card")).toBe("fresh");
    at("2026-05-18T18:00:00Z"); // Mon 14:00 ET, before Mon close
    expect(cardStaleness(friAfterClose, "price_card")).toBe("fresh");
  });

  it("goes to WARN only once the next session has closed (≈1 trading day)", () => {
    const friAfterClose = "2026-05-15T20:30:00Z";
    at("2026-05-18T20:30:00Z"); // Mon, just after Mon 16:00 ET close
    expect(cardStaleness(friAfterClose, "price_card")).toBe("warn");
  });

  it("becomes STALE after a second session closes", () => {
    const friAfterClose = "2026-05-15T20:30:00Z";
    at("2026-05-19T21:00:00Z"); // Tue, after Tue close (2 sessions on)
    expect(cardStaleness(friAfterClose, "price_card")).toBe("stale");
  });

  it("holidays don't count: Fri-before-Memorial-Day fresh through the holiday Monday", () => {
    const friBeforeHoliday = "2026-05-22T20:30:00Z"; // Fri 16:30 ET
    at("2026-05-25T18:00:00Z"); // Memorial Day Mon (market closed)
    expect(cardStaleness(friBeforeHoliday, "heat_card")).toBe("fresh");
    at("2026-05-26T18:00:00Z"); // Tue 14:00 ET, before Tue close
    expect(cardStaleness(friBeforeHoliday, "heat_card")).toBe("fresh");
  });

  it("every card from the spec table is present", () => {
    for (const key of [
      "price_card", "momentum_card", "sentiment_card",
      "heat_card", "catalysts", "trader_news", "research_overview",
    ]) {
      expect(STALENESS[key]).toBeDefined();
    }
  });
});

describe("cardStaleness with authoritative market_session", () => {
  afterEach(() => vi.useRealTimers());
  const at = (iso) => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(iso));
  };

  it("uses market_session.next_close as the exact fresh boundary, overriding the rule calendar", () => {
    // Thu-after-close run. The built-in calendar would say the next
    // close is Fri 2026-05-22. But the exchange had an UNSCHEDULED
    // closure Fri, and Mon 2026-05-25 is Memorial Day — so the real
    // next session close is Tue 2026-05-26.
    const refreshed = "2026-05-21T20:30:00Z";
    const ms = { next_close: "2026-05-26T16:00:00-04:00" };
    at("2026-05-22T21:00:00Z"); // Fri, past the *rule* close
    expect(cardStaleness(refreshed, "price_card")).not.toBe("fresh"); // calendar-only
    expect(cardStaleness(refreshed, "price_card", ms)).toBe("fresh"); // authoritative
    at("2026-05-26T20:30:00Z"); // Tue, just after the real close
    expect(cardStaleness(refreshed, "price_card", ms)).toBe("warn");
  });

  it("ignores a bogus market_session (next_close <= refreshed) and falls back to the calendar", () => {
    const refreshed = "2026-05-15T20:30:00Z"; // Fri after close
    const bogus = { next_close: "2026-05-10T16:00:00-04:00" }; // before refresh
    at("2026-05-18T18:00:00Z"); // Mon before close
    expect(cardStaleness(refreshed, "price_card", bogus)).toBe("fresh");
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
