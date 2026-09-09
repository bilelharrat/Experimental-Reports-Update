import { describe, expect, it } from "vitest";
import {
  assembleDeskNews,
  filterDeskNews,
  indexQuoteCards,
  inferNewsCategory,
  matchCompaniesForNews,
  newsAgeParts,
  quoteBoardRows,
  quoteGainers,
  quoteLosers,
  quoteMostActive,
  quoteMovers,
  lookupQuoteMatches,
  filterScreenerRows,
} from "../src/homeDesk.js";

const zainar = {
  id: "zainar-inc",
  name: "ZaiNar, Inc.",
  ticker: "",
  company_news: [
    {
      title: "ZaiNar emerges from stealth with $100M+",
      published_at: "2026-02-19",
      category: "fundraising",
      summary: "Stealth exit.",
    },
  ],
};
const nvda = {
  id: "nvda",
  name: "NVIDIA",
  ticker: "NVDA",
  recent_news: [{ headline: "NVIDIA launches new chip", date: "2026-09-01" }],
};

describe("homeDesk", () => {
  it("classifies funding and matches book companies", () => {
    expect(inferNewsCategory({ title: "Acme raises Series C at $4B valuation" })).toBe(
      "funding",
    );
    const matched = matchCompaniesForNews(
      { title: "NVIDIA supply chain update", summary: "NVDA foundry mix" },
      [zainar, nvda],
    );
    expect(matched.map((c) => c.id)).toEqual(["nvda"]);
  });

  it("assembles feed plus company headlines and filters by book/market", () => {
    const rows = assembleDeskNews({
      feed: [
        {
          id: "n1",
          kind: "news",
          title: "Fed holds rates as inflation cools",
          captured_at: "2026-09-02",
          summary: "Macro print.",
        },
        {
          id: "n2",
          kind: "news",
          title: "ZaiNar selected for Tokyo GX program",
          captured_at: "2026-09-03",
          company: "ZaiNar, Inc.",
        },
      ],
      companies: [zainar, nvda],
    });
    expect(rows.some((r) => r.title.includes("Tokyo"))).toBe(true);
    expect(rows.some((r) => r.title.includes("stealth"))).toBe(true);
    expect(rows.some((r) => r.title.includes("chip"))).toBe(true);

    const book = filterDeskNews(rows, { scope: "book", bookIds: ["zainar-inc"] });
    expect(book.every((r) => r.companyIds.includes("zainar-inc"))).toBe(true);

    const market = filterDeskNews(rows, { scope: "market" });
    expect(market.some((r) => /Fed/.test(r.title))).toBe(true);
    expect(market.every((r) => r.market)).toBe(true);
  });

  it("ranks quote movers by absolute move", () => {
    const movers = quoteMovers(
      [nvda, { id: "tsm", name: "TSMC", ticker: "TSM" }],
      {
        NVDA: { change_pct_1d: 1.2, last_price: 180 },
        TSM: { change_pct_1d: -4.5, last_price: 140 },
      },
    );
    expect(movers[0].ticker).toBe("TSM");
    expect(movers[0].change).toBe(-4.5);
  });

  it("splits board quotes into gainers and losers", () => {
    const rows = quoteBoardRows(
      {
        NVDA: { change_pct_1d: 1.2, last_price: 180, currency: "USD" },
        TSM: { change_pct_1d: -4.5, last_price: 140, currency: "USD" },
        SPY: { change_pct_1d: 0.4, last_price: 520, currency: "USD" },
      },
      [nvda, { id: "tsm", name: "TSMC", ticker: "TSM" }],
    );
    expect(quoteGainers(rows).map((row) => row.ticker)).toEqual(["NVDA", "SPY"]);
    expect(quoteLosers(rows).map((row) => row.ticker)).toEqual(["TSM"]);
    expect(indexQuoteCards({ SPY: { last_price: 520, change_pct_1d: 0.4 } })[0]).toMatchObject({
      ticker: "SPY",
      last: 520,
      change: 0.4,
    });
  });

  it("ranks most-active quotes by volume and matches ticker search", () => {
    const rows = quoteBoardRows(
      {
        NVDA: { change_pct_1d: 1.2, last_price: 180, volume: 40_000_000 },
        TSM: { change_pct_1d: -4.5, last_price: 140, volume: 9_000_000 },
        SPY: { change_pct_1d: 0.4, last_price: 520, volume: 80_000_000 },
      },
      [nvda, { id: "tsm", name: "TSMC", ticker: "TSM" }],
    );
    expect(quoteMostActive(rows).map((row) => row.ticker)).toEqual(["SPY", "NVDA", "TSM"]);
    expect(lookupQuoteMatches("nvidia", [nvda]).map((row) => row.ticker)).toEqual(["NVDA"]);
    expect(lookupQuoteMatches("AAPL", [nvda])[0]).toMatchObject({
      ticker: "AAPL",
      kind: "ticker",
    });
  });

  it("summarizes story age for Apple-style bylines", () => {
    const now = Date.parse("2026-09-03T12:00:00Z");
    expect(newsAgeParts("2026-09-03T11:50:00Z", now)).toEqual({ unit: "minutes", n: 10 });
    expect(newsAgeParts("2026-09-03T10:00:00Z", now)).toEqual({ unit: "hours", n: 2 });
  });

  it("filters screener rows by sector, cap, change, and volume", () => {
    const rows = [
      {
        ticker: "AAA",
        name: "Alpha",
        sector: "Technology",
        market_cap: 300e9,
        change_pct: 4,
        volume: 2_000_000,
      },
      {
        ticker: "BBB",
        name: "Beta",
        sector: "Energy",
        market_cap: 5e9,
        change_pct: -1,
        volume: 100_000,
      },
    ];
    expect(
      filterScreenerRows(rows, {
        sector: "Technology",
        cap: "mega",
        minChange: 2,
        minVolume: 1_000_000,
      }).map((row) => row.ticker),
    ).toEqual(["AAA"]);
  });
});
