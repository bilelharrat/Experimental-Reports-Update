import { describe, expect, it } from "vitest";
import {
  breadthStrip,
  earningsCountdown,
  enrichScreenerRow,
  expectedMove,
  gapSplit,
  headlineReaction,
  macroWeekGrid,
  pairSpreadSeries,
  periodReturn,
  researchHitsForTicker,
  returnLadder,
  taggingFilingSnips,
  volumeProfile,
  vwapBands,
} from "../src/marketAnalytics.js";

const points = Array.from({ length: 40 }, (_, index) => ({
  t: 1_700_000_000 + index * 86_400,
  open: 100 + index * 0.2,
  high: 101 + index * 0.2,
  low: 99 + index * 0.2,
  close: 100 + index,
  volume: 1000 + index * 10,
}));

describe("marketAnalytics", () => {
  it("builds a return ladder and period returns", () => {
    const ladder = returnLadder(points, { "1d": 1.5 });
    expect(ladder.find((row) => row.id === "1d").value).toBe(1.5);
    expect(ladder.find((row) => row.id === "1y").value).not.toBeNull();
    expect(periodReturn(points, { days: 5 })).toBeCloseTo(
      ((points[39].close - points[34].close) / points[34].close) * 100,
    );
  });

  it("splits overnight gap from session move", () => {
    const split = gapSplit({ open: 102, previousClose: 100, last: 105 });
    expect(split.gap).toBeCloseTo(2);
    expect(split.session).toBeCloseTo((3 / 102) * 100);
    expect(split.day).toBeCloseTo(5);
  });

  it("computes volume profile and VWAP bands", () => {
    const profile = volumeProfile(points, { buckets: 8 });
    expect(profile).toHaveLength(8);
    expect(profile.some((row) => row.volume > 0)).toBe(true);
    const bands = vwapBands(points);
    expect(bands[bands.length - 1].vwap).toBeTruthy();
    expect(bands[bands.length - 1].upper1).toBeGreaterThan(bands[bands.length - 1].vwap);
  });

  it("builds pair spread series", () => {
    const b = points.map((row) => ({ ...row, close: row.close - 5 }));
    const diff = pairSpreadSeries(points, b, { mode: "diff" });
    expect(diff[0].close).toBeCloseTo(5);
    const ratio = pairSpreadSeries(points, b, { mode: "ratio" });
    expect(ratio[0].close).toBeCloseTo(points[0].close / b[0].close);
  });

  it("summarizes watchlist breadth", () => {
    const breadth = breadthStrip(
      [
        { ticker: "A", change: 2, last: 110, weekHigh: 112, weekLow: 90 },
        { ticker: "B", change: -1, last: 80, weekHigh: 120, weekLow: 70 },
      ],
      { A: points },
      { smaWindow: 10 },
    );
    expect(breadth.advancers).toBe(1);
    expect(breadth.decliners).toBe(1);
    expect(breadth.aboveSmaPct).not.toBeNull();
  });

  it("finds research hits and tags filings", () => {
    const hits = researchHitsForTicker({
      ticker: "NVDA",
      news: [{ id: 1, title: "NVDA beats", url: "https://x" }],
      research: [{ id: 2, title: "Chip cycle", summary: "about nvda" }],
      companies: [{ id: "nvda", ticker: "NVDA", name: "NVIDIA" }],
    });
    expect(hits.some((row) => row.kind === "company")).toBe(true);
    expect(hits.length).toBeGreaterThan(1);
    const filings = taggingFilingSnips([
      { title: "NVDA files 8-K on guidance", category: "filings" },
      { title: "Random headline" },
    ], { ticker: "NVDA" });
    expect(filings[0].form).toMatch(/8-?K/i);
  });

  it("builds macro week grid and earnings countdown", () => {
    const now = Date.parse("2026-09-08T12:00:00Z");
    const grid = macroWeekGrid(
      [{ date: "2026-09-09", kind: "macro", title: "CPI" }],
      { now },
    );
    expect(grid.days).toHaveLength(7);
    expect(grid.days.some((day) => day.events.length)).toBe(true);
    expect(earningsCountdown("2026-09-11", now).days).toBe(3);
  });

  it("enriches screener rows", () => {
    const row = enrichScreenerRow(
      {
        ticker: "NVDA",
        last: 110,
        weekHigh: 120,
        weekLow: 100,
        volume: 2e6,
        avgVolume: 1e6,
      },
      { chartPoints: points, earningsDate: "2026-09-11", now: Date.parse("2026-09-08T12:00:00Z") },
    );
    expect(row.volRatio).toBe(2);
    expect(row.earnDays).toBe(3);
    expect(row.rangePos).toBeCloseTo(50);
    expect(row.rsi).not.toBeNull();
  });

  it("prices ATM straddle expected move", () => {
    const now = Date.parse("2026-09-08T12:00:00Z");
    const move = expectedMove(
      [
        {
          expiry: "2026-09-19",
          strike: 100,
          call_bid: 2.4,
          call_ask: 2.6,
          put_bid: 2.1,
          put_ask: 2.3,
        },
        {
          expiry: "2026-09-19",
          strike: 110,
          call_bid: 1,
          call_ask: 1.2,
          put_bid: 4,
          put_ask: 4.2,
        },
      ],
      100,
      { now },
    );
    expect(move.strike).toBe(100);
    expect(move.straddle).toBeCloseTo(4.7);
    expect(move.movePct).toBeCloseTo(4.7);
    expect(move.days).toBe(11);
  });

  it("measures headline reaction from chart points", () => {
    const aligned = [
      { t: 1_731_542_400, close: 100 }, // 2024-11-14 00:00Z
      { t: 1_731_628_800, close: 110 }, // 2024-11-15 00:00Z
    ];
    expect(headlineReaction("2024-11-14T00:00:00Z", aligned)).toBeCloseTo(10);
    expect(headlineReaction("2020-01-01T00:00:00Z", aligned)).toBeNull();
  });
});
