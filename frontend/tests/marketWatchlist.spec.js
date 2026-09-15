import { describe, expect, it, beforeEach, afterEach } from "vitest";
import {
  ensureDefaultAlertRules,
  evaluateAlertRules,
  isPinnedTicker,
  loadHpCompare,
  loadPinnedTickers,
  mergeAlerts,
  toggleHpCompare,
  togglePinnedTicker,
  watchlistAlerts,
} from "../src/marketWatchlist.js";
import {
  deleteSavedScreen,
  findSavedScreen,
  loadSavedScreens,
  saveScreen,
} from "../src/marketScreens.js";
import { bookConcentration, bookPnl, upsertBookLot } from "../src/marketBook.js";

describe("marketWatchlist", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("pins and unpins tickers in localStorage", () => {
    expect(loadPinnedTickers()).toEqual([]);
    expect(togglePinnedTicker("nvda")).toEqual(["NVDA"]);
    expect(isPinnedTicker("NVDA")).toBe(true);
    expect(togglePinnedTicker("NVDA")).toEqual([]);
  });

  it("only pins symbols the server accepts", () => {
    expect(togglePinnedTicker("^vix")).toEqual([]);
    expect(togglePinnedTicker("brk b")).toEqual([]);
    expect(togglePinnedTicker("brk.b")).toEqual(["BRK.B"]);
    window.localStorage.setItem("bsh.marketPinnedTickers", JSON.stringify(["aapl", "^GSPC", "", 7, "RDS-A"]));
    expect(loadPinnedTickers()).toEqual(["AAPL", "7", "RDS-A"]);
  });

  it("rejects book lots with a negative cost basis", () => {
    expect(upsertBookLot({ ticker: "NVDA", shares: 10, cost: -5 })).toEqual([]);
    expect(upsertBookLot({ ticker: "NVDA", shares: 10, cost: 0 })).toEqual([
      { ticker: "NVDA", companyId: null, shares: 10, cost: 0 },
    ]);
  });

  it("flags gap moves and 52-week extremes", () => {
    const alerts = watchlistAlerts([
      { ticker: "AAA", change: 6.2, last: 100, weekHigh: 101, weekLow: 50 },
      { ticker: "BBB", change: -0.5, last: 51, weekHigh: 200, weekLow: 50 },
    ]);
    expect(alerts.map((row) => row.kind)).toEqual(["gap_up", "near_high", "near_low"]);
  });

  it("evaluates pct / volume / earnings rules", () => {
    ensureDefaultAlertRules(["NVDA"]);
    const rules = [
      { id: "1", ticker: "NVDA", kind: "pct", threshold: 5, enabled: true },
      { id: "2", ticker: "NVDA", kind: "volume", threshold: 2, enabled: true },
      { id: "3", ticker: "NVDA", kind: "earnings", threshold: 3, enabled: true },
    ];
    const rows = [
      { ticker: "NVDA", change: 6, volume: 5e6, avgVolume: 2e6 },
    ];
    const alerts = evaluateAlertRules(rows, rules, {
      earningsByTicker: { NVDA: "2026-09-10" },
      now: Date.parse("2026-09-08T12:00:00Z"),
    });
    expect(alerts.map((row) => row.kind)).toEqual([
      "rule_pct_up",
      "rule_volume",
      "rule_earnings",
    ]);
    expect(mergeAlerts(watchlistAlerts(rows), alerts).length).toBeGreaterThan(0);
  });

  it("persists HP compare tickers", () => {
    expect(loadHpCompare()).toEqual([]);
    expect(toggleHpCompare("spy")).toEqual(["SPY"]);
    expect(toggleHpCompare("QQQ")).toEqual(["SPY", "QQQ"]);
    expect(toggleHpCompare("SPY")).toEqual(["QQQ"]);
  });
});

describe("marketScreens", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("saves and finds EQS presets", () => {
    const screens = saveScreen("Mega up", {
      sector: "Technology",
      cap: "mega",
      minChange: "2",
      minVolume: "",
      query: "",
    });
    expect(screens[0].name).toBe("Mega up");
    expect(findSavedScreen("Mega up")?.filters.cap).toBe("mega");
    expect(deleteSavedScreen(screens[0].id)).toEqual([]);
    expect(loadSavedScreens()).toEqual([]);
  });
});

describe("marketBook", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("marks lots to market and summarizes concentration", () => {
    upsertBookLot({ ticker: "NVDA", shares: 10, cost: 100 });
    const pnl = bookPnl(
      [{ ticker: "NVDA", shares: 10, cost: 100 }],
      { NVDA: { last_price: 110, change_pct_1d: 10 } },
    );
    expect(pnl.marketValue).toBe(1100);
    expect(pnl.unrealized).toBe(100);
    expect(pnl.dayPnl).toBeCloseTo(100, 5);

    const lens = bookConcentration(
      [{ id: "nvda", name: "NVIDIA", ticker: "NVDA", sector: "Tech" }],
      { NVDA: { last_price: 110, change_pct_1d: 2, beta: 1.4 } },
    );
    expect(lens.sectorMix[0].sector).toBe("Tech");
    expect(lens.avgBeta).toBeCloseTo(1.4);
    expect(lens.movers[0].ticker).toBe("NVDA");
  });
});
