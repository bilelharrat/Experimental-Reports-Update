import { describe, expect, it } from "vitest";
import {
  briefReadMinutes,
  calendarWeekBuckets,
  ledgerHitStats,
  marketBreadthFromUniverse,
  postureFromBreadth,
  pulseQuoteUniverse,
  screenerMoverLists,
  sectorRotationRows,
} from "../src/marketPulseDesk.js";

describe("marketPulseDesk", () => {
  it("builds a deduped US quote universe covering indexes, sectors, and macro", () => {
    const tickers = pulseQuoteUniverse();
    expect(tickers).toContain("SPY");
    expect(tickers).toContain("IWM");
    expect(tickers).toContain("XLK");
    expect(tickers).toContain("XLF");
    expect(tickers).toContain("TLT");
    expect(tickers).toContain("VIXY");
    expect(new Set(tickers).size).toBe(tickers.length);
  });

  it("ranks sector ETFs by daily change", () => {
    const rows = sectorRotationRows({
      XLK: { last_price: 200, change_pct_1d: 1.2 },
      XLE: { last_price: 90, change_pct_1d: -0.8 },
      XLF: { last_price: 40, change_pct_1d: 0.4 },
    });
    expect(rows[0].ticker).toBe("XLK");
    expect(rows.at(-1).ticker).toBe("XLE");
  });

  it("summarizes Nasdaq universe breadth", () => {
    const breadth = marketBreadthFromUniverse([
      { change_pct_1d: 1.2, last_price: 98, high_52w: 100 },
      { change_pct_1d: -0.5, last_price: 50, high_52w: 80 },
      { change_pct_1d: 0.01, last_price: 10, high_52w: 20 },
    ]);
    expect(breadth.up).toBe(1);
    expect(breadth.down).toBe(1);
    expect(breadth.flat).toBe(1);
    expect(breadth.nearHigh).toBe(1);
    expect(breadth.pctUp).toBeCloseTo(33.333, 1);
  });

  it("reads the Nasdaq screener's own row shape", () => {
    // /api/quotes/screeners rows: `change_pct` and `last`, no 52-week high.
    // Reading only `change_pct_1d` made Pulse show 0 advancers and 0 decliners.
    const breadth = marketBreadthFromUniverse([
      { ticker: "A", change_pct: 3.3, last: 161.7 },
      { ticker: "B", change_pct: -1.1, last: 20 },
      { ticker: "C", change_pct: 0.4, last: 5 },
      { ticker: "D", change_pct: null, last: 9 },
    ]);
    expect(breadth.total).toBe(3);
    expect(breadth.up).toBe(2);
    expect(breadth.down).toBe(1);
    expect(breadth.pctUp).toBeCloseTo(66.667, 1);
    // no row carries a 52-week high: that is n/a, not "0% near highs"
    expect(breadth.pctNearHigh).toBeNull();
  });

  it("maps posture from breadth and SPY", () => {
    expect(postureFromBreadth({ pctUp: 70 }, 0.5)).toBe("risk_on");
    expect(postureFromBreadth({ pctUp: 30 }, -0.4)).toBe("risk_off");
    expect(postureFromBreadth({ pctUp: 50 }, 0)).toBe("neutral");
  });

  it("slices screener movers and buckets calendar days", () => {
    const movers = screenerMoverLists(
      {
        gainers: [{ ticker: "AAA" }, { ticker: "BBB" }],
        losers: [{ ticker: "CCC" }],
        active: [{ ticker: "DDD" }],
      },
      1,
    );
    expect(movers.gainers).toHaveLength(1);
    expect(movers.losers[0].ticker).toBe("CCC");

    const localMonday = new Date(2026, 8, 7, 12, 0, 0); // Sep 7 2026 local
    const days = calendarWeekBuckets(
      [
        { date: "2026-09-08", ticker: "AAPL", kind: "earnings" },
        { date: "2026-09-20", ticker: "MSFT", kind: "earnings" },
      ],
      localMonday,
    );
    expect(days).toHaveLength(7);
    const tue = days.find((day) => day.date === "2026-09-08");
    expect(tue?.events[0]?.ticker).toBe("AAPL");
    expect(days.every((day) => day.events.every((ev) => ev.ticker !== "MSFT"))).toBe(true);
  });

  it("scores signal ledger hit rate", () => {
    const stats = ledgerHitStats([
      { score_pct: 4 },
      { score_pct: -2 },
      { score_pct: 1 },
      { direction: "watch" },
    ]);
    expect(stats.total).toBe(4);
    expect(stats.scored).toBe(3);
    expect(stats.hits).toBe(2);
    expect(stats.hitRate).toBeCloseTo((2 / 3) * 100);
    expect(stats.avgScore).toBeCloseTo(1);
  });
});

describe("morning brief reading time", () => {
  it("estimates reading time by words, or by characters in Chinese", () => {
    expect(briefReadMinutes([])).toBe(0);
    expect(briefReadMinutes(["a few words"])).toBe(1);
    expect(briefReadMinutes([Array(1380).fill("word").join(" ")])).toBe(6);
    expect(briefReadMinutes(["市".repeat(2000)], "zh")).toBe(5);
  });
});
