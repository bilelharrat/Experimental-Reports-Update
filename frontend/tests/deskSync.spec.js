import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api.js";
import {
  DESK_KEYS,
  SYNCED_MARK_KEY,
  applyDeskState,
  initDeskSync,
  mergeDeskState,
  resetDeskSyncForTests,
  snapshotDeskState,
} from "../src/deskSync.js";

describe("deskSync", () => {
  beforeEach(() => {
    resetDeskSyncForTests();
    window.localStorage.clear();
  });

  afterEach(() => {
    resetDeskSyncForTests();
    window.localStorage.clear();
  });

  it("snapshots only known desk keys that exist locally", () => {
    window.localStorage.setItem("bsh.marketPinnedTickers", JSON.stringify(["NVDA"]));
    window.localStorage.setItem("unrelated", JSON.stringify(1));
    expect(snapshotDeskState()).toEqual({
      "bsh.marketPinnedTickers": ["NVDA"],
    });
  });

  it("fills missing local keys from a server payload without overwriting", () => {
    window.localStorage.setItem("bsh.marketPinnedTickers", JSON.stringify(["AAPL"]));
    const applied = applyDeskState({
      "bsh.marketPinnedTickers": ["NVDA"],
      "bsh.bookLots": [{ ticker: "SPY", shares: 10, cost: 400 }],
    });
    expect(applied).toEqual(["bsh.bookLots"]);
    expect(JSON.parse(window.localStorage.getItem("bsh.marketPinnedTickers"))).toEqual(["AAPL"]);
    expect(JSON.parse(window.localStorage.getItem("bsh.bookLots"))[0].ticker).toBe("SPY");
  });

  it("overwrite mode replaces local keys", () => {
    window.localStorage.setItem("bsh.marketPinnedTickers", JSON.stringify(["AAPL"]));
    applyDeskState({ "bsh.marketPinnedTickers": ["NVDA"] }, { overwrite: true });
    expect(JSON.parse(window.localStorage.getItem("bsh.marketPinnedTickers"))).toEqual(["NVDA"]);
  });

  it("lists the durable desk key set", () => {
    expect(DESK_KEYS).toContain("bsh.marketAlertRules");
    expect(DESK_KEYS).toContain("bsh.bookLots");
  });
});

describe("deskSync merge", () => {
  beforeEach(() => {
    resetDeskSyncForTests();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetDeskSyncForTests();
    window.localStorage.clear();
  });

  it("server value wins for a key the local side has not changed since last sync", () => {
    const oldLots = [{ ticker: "SPY", shares: 10, cost: 400 }];
    const macLots = [...oldLots, { ticker: "KO", shares: 5, cost: 60 }];
    window.localStorage.setItem("bsh.bookLots", JSON.stringify(oldLots));
    window.localStorage.setItem(
      SYNCED_MARK_KEY,
      JSON.stringify({ "bsh.bookLots": JSON.stringify(oldLots) })
    );
    const applied = mergeDeskState({ "bsh.bookLots": macLots });
    expect(applied).toEqual(["bsh.bookLots"]);
    expect(JSON.parse(window.localStorage.getItem("bsh.bookLots"))).toEqual(macLots);
  });

  it("local value wins for a key with unsynced local edits", () => {
    const synced = ["AAPL"];
    window.localStorage.setItem("bsh.marketPinnedTickers", JSON.stringify(["AAPL", "TSLA"]));
    window.localStorage.setItem(
      SYNCED_MARK_KEY,
      JSON.stringify({ "bsh.marketPinnedTickers": JSON.stringify(synced) })
    );
    const applied = mergeDeskState({ "bsh.marketPinnedTickers": ["AAPL", "NVDA"] });
    expect(applied).toEqual([]);
    expect(JSON.parse(window.localStorage.getItem("bsh.marketPinnedTickers"))).toEqual(["AAPL", "TSLA"]);
  });

  it("stale localStorage with no sync history adopts the server key on init", async () => {
    const macRules = [{ id: "r1", ticker: "KO", kind: "price", threshold: 60 }];
    window.localStorage.setItem("bsh.marketAlertRules", JSON.stringify([]));
    window.localStorage.setItem("bsh.marketTickerNotes", JSON.stringify({ KO: "local only" }));
    vi.spyOn(api, "deskPrefs").mockResolvedValue({ data: { "bsh.marketAlertRules": macRules } });
    vi.spyOn(api, "saveDeskPrefs").mockResolvedValue({});
    const applied = await initDeskSync();
    expect(applied).toEqual(["bsh.marketAlertRules"]);
    expect(JSON.parse(window.localStorage.getItem("bsh.marketAlertRules"))).toEqual(macRules);
    expect(JSON.parse(window.localStorage.getItem("bsh.marketTickerNotes"))).toEqual({ KO: "local only" });
    expect(JSON.parse(window.localStorage.getItem(SYNCED_MARK_KEY))["bsh.marketAlertRules"]).toBe(
      JSON.stringify(macRules)
    );
  });
});
