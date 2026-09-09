import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  DESK_KEYS,
  applyDeskState,
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
