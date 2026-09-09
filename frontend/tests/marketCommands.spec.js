import { describe, expect, it } from "vitest";
import {
  parseMarketCommand,
  routeForMarketCommand,
  suggestMarketCommands,
} from "../src/marketCommands.js";

describe("marketCommands", () => {
  it("parses bare tickers and verb commands", () => {
    expect(parseMarketCommand("nvda")).toMatchObject({ action: "quote", ticker: "NVDA" });
    expect(parseMarketCommand("NEWS AAPL")).toMatchObject({ action: "news", ticker: "AAPL" });
    expect(parseMarketCommand("COMP MSFT")).toMatchObject({ action: "comp", ticker: "MSFT" });
    expect(parseMarketCommand("PEER NVDA")).toMatchObject({ action: "comp", ticker: "NVDA" });
    expect(parseMarketCommand("HP NVDA")).toMatchObject({ action: "hp", ticker: "NVDA" });
    expect(parseMarketCommand("FA AAPL")).toMatchObject({ action: "fa", ticker: "AAPL" });
    expect(parseMarketCommand("EQS")).toMatchObject({ action: "screener" });
    expect(parseMarketCommand("WEI")).toMatchObject({ action: "wei" });
    expect(parseMarketCommand("HEAT")).toMatchObject({ action: "heatmap" });
    expect(parseMarketCommand("RRG")).toMatchObject({ action: "rrg" });
    expect(parseMarketCommand("SESSION")).toMatchObject({ action: "session" });
    expect(parseMarketCommand("LOTS")).toMatchObject({ action: "lots" });
    expect(parseMarketCommand("TWO")).toMatchObject({ action: "two" });
    expect(parseMarketCommand("TWO AAPL")).toMatchObject({ action: "two", ticker: "AAPL" });
    expect(parseMarketCommand("ICS")).toMatchObject({ action: "ics" });
    expect(parseMarketCommand("NOTE NVDA")).toMatchObject({ action: "notes", ticker: "NVDA" });
    expect(parseMarketCommand("EVTS")).toMatchObject({ action: "calendar", ticker: null });
    expect(parseMarketCommand("TRACK")).toMatchObject({ action: "tracking" });
  });

  it("routes commands to Market panels", () => {
    expect(routeForMarketCommand(parseMarketCommand("NVDA"))).toEqual({
      name: "market-radar",
      query: { ticker: "NVDA" },
    });
    expect(routeForMarketCommand(parseMarketCommand("PEER NVDA"))).toEqual({
      name: "market-radar",
      query: { ticker: "NVDA", panel: "peers" },
    });
    expect(routeForMarketCommand(parseMarketCommand("HP NVDA"))).toEqual({
      name: "market-radar",
      query: { ticker: "NVDA", panel: "hp" },
    });
    expect(routeForMarketCommand(parseMarketCommand("FA"))).toEqual({
      name: "market-radar",
      query: { panel: "fa", tab: "financials" },
    });
    expect(routeForMarketCommand(parseMarketCommand("EQS"))).toEqual({
      name: "market-radar",
      query: { panel: "screener" },
    });
    expect(routeForMarketCommand(parseMarketCommand("EVTS"))).toEqual({
      name: "market-radar",
      query: { panel: "calendar" },
    });
    expect(routeForMarketCommand(parseMarketCommand("HEAT"))).toEqual({
      name: "market-radar",
      query: { panel: "heatmap" },
    });
    expect(routeForMarketCommand(parseMarketCommand("LOTS"))).toEqual({
      name: "tracking",
      query: { panel: "lots" },
    });
    expect(routeForMarketCommand(parseMarketCommand("TWO AAPL"))).toEqual({
      name: "market-radar",
      query: { ticker: "AAPL", two: "1" },
    });
    expect(routeForMarketCommand(parseMarketCommand("ICS"))).toEqual({
      name: "market-radar",
      query: { panel: "calendar", ics: "1" },
    });
    expect(routeForMarketCommand(parseMarketCommand("BRIEF"))).toEqual({
      name: "weekly-summary",
      query: { panel: "brief" },
    });
    expect(routeForMarketCommand(parseMarketCommand("SIG"))).toEqual({
      name: "research-page-market-pulse",
    });
    expect(routeForMarketCommand(parseMarketCommand("SET"))).toEqual({
      name: "settings",
    });
    expect(routeForMarketCommand(parseMarketCommand("ND"))).toEqual({
      name: "news-desk",
    });
  });

  it("suggests DES/NEWS/PEER for a ticker", () => {
    const rows = suggestMarketCommands("NVDA", {
      companies: [{ id: "nvda", name: "NVIDIA", ticker: "NVDA" }],
    });
    expect(rows.map((row) => row.action)).toContain("quote");
    expect(rows.map((row) => row.action)).toContain("news");
    expect(rows.map((row) => row.action)).toContain("comp");
    expect(rows.map((row) => row.action)).toContain("hp");
    expect(rows.some((row) => String(row.title).startsWith("PEER"))).toBe(true);
  });
});
