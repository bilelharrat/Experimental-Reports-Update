import { describe, expect, it } from "vitest";
import {
  buildTickerTape,
  displayTicker,
  homeTapeTickers,
  quoteStaleness,
  TAPE_BENCHMARK_TICKERS,
} from "../src/liveTicker.js";

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

describe("homeTapeTickers", () => {
  const privateOnly = [{ id: "zainar-inc", name: "ZaiNar, Inc.", company_type: "private" }];

  it("prefers public workspace companies", () => {
    const book = [...privateOnly, { id: "nvda", name: "NVIDIA", ticker: "nvda", company_type: "public" }];
    expect(homeTapeTickers(book, ["AMD"])).toEqual(["NVDA"]);
  });

  it("leads with Market watchlist pins, then benchmarks, when the book has no public names", () => {
    expect(homeTapeTickers(privateOnly, ["amd", "AMD", "brk.b", "spy"])).toEqual([
      "AMD",
      "BRK.B",
      ...TAPE_BENCHMARK_TICKERS,
    ]);
  });

  it("falls back to benchmarks when there are no pins either", () => {
    expect(homeTapeTickers(privateOnly, [])).toEqual(TAPE_BENCHMARK_TICKERS);
    expect(homeTapeTickers([], undefined)).toEqual(TAPE_BENCHMARK_TICKERS);
  });

  it("builds tape rows for tickers without a workspace company", () => {
    const rows = buildTickerTape(privateOnly, { SPY: { last_price: 761.2, change_pct_1d: -0.4 } }, ["SPY"]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ ticker: "SPY", name: "SPY", companyId: undefined, lastPrice: "$761.2", day: -0.4, up: false });
  });
});
