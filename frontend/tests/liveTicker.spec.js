import { describe, expect, it } from "vitest";
import { displayTicker, quoteStaleness } from "../src/liveTicker.js";

describe("displayTicker", () => {
  const book = [
    {
      id: "googl",
      name: "Alphabet Inc.",
      ticker: "GOOGL",
      company_type: "public",
    },
    {
      id: "google-llc",
      name: "Google",
      ticker: null,
      company_type: "private",
      status: "subsidiary",
      parent_company: "Alphabet Inc.",
    },
    {
      id: "zainar-inc",
      name: "ZaiNar, Inc.",
      ticker: null,
      company_type: "private",
    },
  ];

  it("uses the company's own ticker when present", () => {
    expect(displayTicker(book[0], book)).toBe("GOOGL");
  });

  it("inherits the listed parent's ticker for a subsidiary", () => {
    expect(displayTicker(book[1], book)).toBe("GOOGL");
  });

  it("stays blank when there is no ticker and no listed parent", () => {
    expect(displayTicker(book[2], book)).toBe("");
  });
});

describe("quoteStaleness", () => {
  it("flags prints older than the stale window", () => {
    const now = Date.parse("2026-09-09T16:00:00Z");
    expect(quoteStaleness("2026-09-09T15:50:00Z", { now, staleMinutes: 20 })).toEqual({
      ageMinutes: 10,
      stale: false,
    });
    expect(quoteStaleness("2026-09-09T15:30:00Z", { now, staleMinutes: 20 }).stale).toBe(true);
    expect(quoteStaleness(null, { now })).toBeNull();
  });
});
