import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  alertKey,
  edgarLinks,
  earningsStrip,
  eventsToIcs,
  findDesk,
  freshAlerts,
  heatTone,
  loadChartPrefs,
  loadDeskLayout,
  loadRecentTickers,
  loadTickerNote,
  loadWatchColumns,
  muteAlert,
  notifyAlerts,
  optionsSnapshot,
  pushRecentTicker,
  rrgLayout,
  rrgPoints,
  saveChartPrefs,
  saveDesk,
  saveDeskLayout,
  saveTickerNote,
  sectorHeatmap,
  toggleWatchColumn,
  visibleAlerts,
  volumeRatio,
  vsSpyDay,
} from "../src/marketDesk.js";

describe("marketDesk", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => window.localStorage.clear());

  it("toggles watchlist columns and keeps price", () => {
    expect(loadWatchColumns()).toEqual(["price", "change", "volume"]);
    const next = toggleWatchColumn("ytd");
    expect(next).toContain("ytd");
    expect(next[0]).toBe("price");
    expect(toggleWatchColumn("price", next)).toEqual(next);
  });

  it("builds a sector heat map and RRG quadrants", () => {
    const heat = sectorHeatmap([
      { ticker: "A", sector: "Tech", change_pct: 3 },
      { ticker: "B", sector: "Tech", change_pct: 1 },
      { ticker: "C", sector: "Energy", change_pct: -2 },
    ]);
    expect(heat[0].sector).toBe("Tech");
    expect(heat[0].avg).toBe(2);
    expect(heatTone(3)).toBe(1);
    expect(heatTone(-3)).toBe(-1);

    const points = rrgPoints([
      { ticker: "NVDA", vs_spy_1y: 20, vs_spy_1m: 4 },
      { ticker: "X", vs_spy_1y: -8, vs_spy_1m: 2 },
      { ticker: "Y", vs_spy_1y: 5, vs_spy_1m: -1 },
    ]);
    expect(points.find((row) => row.ticker === "NVDA").quadrant).toBe("leading");
    expect(points.find((row) => row.ticker === "X").quadrant).toBe("improving");
    expect(points.find((row) => row.ticker === "Y").quadrant).toBe("weakening");
    expect(rrgLayout(points).coords).toHaveLength(3);
  });

  it("summarizes earnings surprises and revisions", () => {
    const strip = earningsStrip({
      earnings: {
        next_date: "2026-09-11",
        next_estimated: true,
        past: [
          { period: "Q2", surprise_pct: 8, eps: 1.2, estimate: 1.1 },
          { period: "Q1", surprise_pct: -2, eps: 0.9, estimate: 0.92 },
        ],
      },
      analysis: {
        quarterly: [{ consensus: 1.3, revisions_up: 6, revisions_down: 2 }],
      },
    }, { now: Date.parse("2026-09-08T12:00:00Z") });
    expect(strip.days).toBe(3);
    expect(strip.lastSurprise).toBe(8);
    expect(strip.revisionNet).toBe(4);
    expect(strip.avgSurprise).toBe(3);
  });

  it("builds EDGAR deep links and desk snapshots", () => {
    const links = edgarLinks("nvda");
    expect(links.map((row) => row.form)).toEqual(["EDGAR", "10-K", "10-Q", "8-K"]);
    expect(links[2].url).toContain("type=10-Q");
    expect(volumeRatio(20, 10)).toBe(2);
    expect(vsSpyDay(3, 1)).toBe(2);

    saveDesk("Tape", { ticker: "NVDA", panel: "hp", chartRange: "1d" });
    expect(findDesk("Tape")?.ticker).toBe("NVDA");
  });

  it("snoozes alerts and notifies only fresh ones", () => {
    const alert = { ticker: "NVDA", kind: "gap_up" };
    expect(alertKey(alert)).toBe("NVDA:gap_up:");
    muteAlert(alert, { minutes: 60, now: 1_000 });
    expect(visibleAlerts([alert], undefined, 1_000 + 10_000)).toEqual([]);
    expect(visibleAlerts([alert], undefined, 1_000 + 61 * 60_000)).toEqual([alert]);

    const sent = [];
    const first = freshAlerts([alert], { now: 5_000 });
    notifyAlerts(first, { notify: (payload) => sent.push(payload) });
    expect(sent).toHaveLength(1);
    expect(freshAlerts([alert], { now: 6_000 })).toEqual([]);
  });

  it("tracks recents, notes, chart prefs, ICS, and options snapshot", () => {
    expect(pushRecentTicker("nvda")).toEqual(["NVDA"]);
    expect(pushRecentTicker("AAPL")[0]).toBe("AAPL");
    expect(loadRecentTickers()).toContain("NVDA");
    saveTickerNote("NVDA", "watch breakout");
    expect(loadTickerNote("NVDA")).toBe("watch breakout");
    saveChartPrefs({ sma200: true, logScale: true });
    expect(loadChartPrefs()).toMatchObject({ sma200: true, logScale: true });
    expect(loadDeskLayout()).toEqual({ expanded: false });
    saveDeskLayout({ expanded: true });
    expect(loadDeskLayout()).toEqual({ expanded: true });
    const ics = eventsToIcs([
      { date: "2026-09-11", ticker: "NVDA", kind: "earnings", title: "Print" },
    ]);
    expect(ics).toContain("BEGIN:VEVENT");
    expect(ics).toContain("SUMMARY:NVDA · earnings · Print");
    const snap = optionsSnapshot(
      {
        rows: [
          {
            expiry: "2026-09-20",
            strike: 100,
            call_volume: 20,
            put_volume: 10,
            call_oi: 50,
            put_oi: 25,
          },
        ],
      },
      101,
    );
    expect(snap.nearestExpiry).toBe("2026-09-20");
    expect(snap.atmStrike).toBe(100);
    expect(snap.putCallVolume).toBe(0.5);
  });
});
