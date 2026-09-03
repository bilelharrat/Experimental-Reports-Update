import { describe, expect, it } from "vitest";
import {
  assembleDeskNews,
  filterDeskNews,
  inferNewsCategory,
  matchCompaniesForNews,
  newsAgeParts,
  quoteMovers,
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

  it("summarizes story age for Apple-style bylines", () => {
    const now = Date.parse("2026-09-03T12:00:00Z");
    expect(newsAgeParts("2026-09-03T11:50:00Z", now)).toEqual({ unit: "minutes", n: 10 });
    expect(newsAgeParts("2026-09-03T10:00:00Z", now)).toEqual({ unit: "hours", n: 2 });
  });
});
