import { describe, expect, it } from "vitest";
import {
  compactMoney,
  companyFacts,
  companyPeople,
  companyReports,
  deskCoverage,
  reportTitle,
  seriesChangePct,
  sparkAreaPaths,
  translatedField,
} from "../src/companyLauncher.js";
import { normalizeReportStatus } from "../src/formatters.js";

describe("company launcher helpers", () => {
  it("lists one company's reports, newest first", () => {
    const rows = companyReports(
      [
        { id: "a", company_id: "acme", created_at: "2026-08-01T00:00:00Z" },
        { id: "b", company_id: "other", created_at: "2026-09-09T00:00:00Z" },
        { id: "c", company_id: "acme", created_at: "2026-09-01T00:00:00Z" },
      ],
      "acme",
    );
    expect(rows.map((r) => r.id)).toEqual(["c", "a"]);
    expect(companyReports([{ id: "a", company_id: "acme" }], "")).toEqual([]);
  });

  it("titles a report by the server's label, else its kind", () => {
    expect(reportTitle({ report_type: "Buffett Investment Memo", kind: "buffett_memo" })).toBe(
      "Buffett Investment Memo",
    );
    expect(reportTitle({ kind: "investment_memo_latestage" })).toBe("Investment Memo Latestage");
  });

  it("buckets report statuses as the Reports page does", () => {
    expect(normalizeReportStatus("complete")).toBe("complete");
    expect(normalizeReportStatus("complete_with_warnings")).toBe("needs_attention");
    expect(normalizeReportStatus("awaiting_studio")).toBe("needs_attention");
    expect(normalizeReportStatus("failed_during_analysis")).toBe("failed");
    expect(normalizeReportStatus("queued")).toBe("running");
  });

  it("shortens plain dollar amounts and leaves the rest as written", () => {
    expect(compactMoney("$100,000,000+")).toBe("$100M+");
    expect(compactMoney("2500000")).toBe("$2.5M");
    expect(compactMoney("~$45B")).toBe("~$45B");
    expect(compactMoney("Series B")).toBe("Series B");
    expect(compactMoney(null)).toBe("");
  });

  it("leads a listed company's facts with market figures", () => {
    const facts = companyFacts(
      { founded_year: 1968, hq: "Santa Clara, California" },
      {
        market_cap: 212_555_000_000,
        pe_ratio: 24.42,
        fifty_two_week_low: 269.77,
        fifty_two_week_high: 447.03,
        dividend_yield: 0.0256,
        currency: "USD",
      },
    );
    expect(facts.map((f) => [f.key, f.value])).toEqual([
      ["market_cap", "$213B"],
      ["pe", "24.4"],
      ["range", "$269.77 – $447.03"],
      ["dividend", "2.56%"],
      ["founded", "1968"],
      ["hq", "Santa Clara, California"],
    ]);
  });

  it("leads a private company's facts with its metrics and money raised", () => {
    const facts = companyFacts({
      metrics: [
        { label: "ARR", value: "~$24M" },
        { label: "YoY Growth", value: "+180%" },
        { label: "Valuation", value: "$1.0B+" },
        { label: "TAM", value: "~$45B" },
      ],
      total_funding_usd: "$100,000,000+",
      founded_year: 2017,
      hq: "Belmont, California, USA",
    });
    expect(facts.map((f) => f.label || f.key)).toEqual([
      "ARR",
      "YoY Growth",
      "Valuation",
      "funding",
      "founded",
      "hq",
    ]);
    expect(facts[3].value).toBe("$100M+");
  });

  it("skips a P/E that means nothing and facts that are missing", () => {
    const facts = companyFacts({}, { pe_ratio: -57.4, market_cap: 0 });
    expect(facts).toEqual([]);
  });

  it("fills a bare listing's card with market detail after the record", () => {
    const facts = companyFacts(
      { founded_year: 1968 },
      {
        market_cap: 643_616_000_000,
        pe_ratio: -57.44,
        eps: -2.12,
        volume: 177_095_423,
        low: 114.93,
        high: 124.73,
        beta: 2.25,
        fifty_two_week_low: 28.73,
        fifty_two_week_high: 142.35,
      },
    );
    expect(facts.map((f) => [f.key, f.value])).toEqual([
      ["market_cap", "$644B"],
      ["range", "$28.73 – $142.35"],
      ["founded", "1968"],
      ["eps", "-$2.12"],
      ["volume", "177M"],
      ["day_range", "$114.93 – $124.73"],
      ["beta", "2.25"],
    ]);
  });

  it("stops at eight facts", () => {
    const facts = companyFacts(
      {
        metrics: [
          { label: "ARR", value: "$1M" },
          { label: "Growth", value: "+10%" },
        ],
        total_funding_usd: "5000000",
        founded_year: 2020,
        hq: "Austin",
        employee_band: "11-50",
        latest_funding: { round: "Seed" },
      },
      { market_cap: 1e9, pe_ratio: 12, fifty_two_week_low: 1, fifty_two_week_high: 2, volume: 10 },
    );
    expect(facts).toHaveLength(8);
    expect(facts.at(-1).key).toBe("hq");
  });

  it("counts what the desk holds, skipping what it lacks", () => {
    expect(
      deskCoverage({
        products: [{}, {}],
        competitors: [],
        key_people: [{}, {}, {}],
        team_profiles: [{}],
        board_investors: [{}],
      }),
    ).toEqual([
      { key: "products", count: 2 },
      { key: "people", count: 3 },
      { key: "investors", count: 1 },
    ]);
    expect(deskCoverage({})).toEqual([]);
  });

  it("names up to three people, without repeats", () => {
    const people = companyPeople({
      key_people: [
        { name: "Ada Park", role: "CEO" },
        { name: "Ben Ito", role: "CTO" },
      ],
      team_profiles: [
        { name: "ada park", role: "Co-founder" },
        { name: "Cy Moss", role: "CFO" },
        { name: "Di Lu", role: "COO" },
      ],
    });
    expect(people).toEqual([
      { name: "Ada Park", role: "CEO" },
      { name: "Ben Ito", role: "CTO" },
      { name: "Cy Moss", role: "CFO" },
    ]);
  });

  it("reads a company field in the reader's language", () => {
    const company = { language: "en", description: "English", translation: { description: "中文" } };
    expect(translatedField(company, "description", "en")).toBe("English");
    expect(translatedField(company, "description", "zh")).toBe("中文");
    expect(translatedField({ description: "Only" }, "description", "zh")).toBe("Only");
  });

  it("draws the price trace and measures its change", () => {
    expect(sparkAreaPaths([1])).toEqual({ line: "", area: "" });
    const { line, area } = sparkAreaPaths([10, 20, 15], { width: 100, height: 40, pad: 0 });
    expect(line).toBe("M0.0 40.0 L50.0 0.0 L100.0 20.0");
    expect(area).toBe(`${line} L100.0 40 L0.0 40 Z`);
    expect(seriesChangePct([100, 90, 125])).toBe(25);
    expect(seriesChangePct([100])).toBeNull();
  });
});
