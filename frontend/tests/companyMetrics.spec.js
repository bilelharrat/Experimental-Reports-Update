import { describe, expect, it } from "vitest";

import {
  companyMetricHistories,
  companySummaryMetrics,
  inferredMetricLabelKey,
  inferredMetricSourceKey,
} from "../src/companyMetrics.js";

describe("companySummaryMetrics", () => {
  it("uses supplied diligence metrics without modification", () => {
    const metrics = [{ label: "ARR", value: "$24M", source_class: "BSH diligence" }];
    expect(companySummaryMetrics({ metrics })).toBe(metrics);
  });

  it("builds public-company KPIs from earnings and public research", () => {
    const result = companySummaryMetrics({
      status: "public",
      ticker: "MSFT",
      latest_earnings: {
        period: "Q3 FY2026",
        revenue_yoy: "$82.9B, +18% YoY",
      },
      trader_snapshot: {
        price_card: { as_of: "2026-07-23" },
        heat_card: { valuation: { ev_revenue_current: 9.1 } },
        research_overview: {
          financial_quality: {
            metrics: [{ label_en: "Operating margin (FY2025)", value: "~45.6%" }],
          },
        },
      },
    });

    expect(result.map(({ label, value }) => ({ label, value }))).toEqual([
      { label: "Quarterly Revenue", value: "$82.9B" },
      { label: "YoY Growth", value: 18 },
      { label: "EV / Revenue", value: "9.1x" },
      { label: "Operating Margin", value: "~45.6%" },
    ]);
    expect(result.every((metric) => metric.source_class !== "source pending")).toBe(true);
    expect(result.map((metric) => metric.label_key)).toEqual([
      "company.metric_quarterly_revenue",
      "company.metric_yoy_growth",
      "company.metric_ev_revenue",
      "company.metric_operating_margin",
    ]);
    expect(result.map((metric) => metric.source_key)).toEqual([
      "company.metric_source_earnings",
      "company.metric_source_earnings",
      "company.metric_source_public_market",
      "company.metric_source_filings",
    ]);
  });

  it("uses the funding record for private-company valuation", () => {
    const result = companySummaryMetrics({
      status: "private",
      latest_funding: { post_money_usd: "$1B", date: "2026-02-19" },
    });
    expect(result[2]).toMatchObject({
      label: "Valuation",
      value: "$1B",
      source_class: "company record",
      as_of: "2026-02-19",
    });
  });

  it("infers localization keys for supplied diligence metrics", () => {
    expect(inferredMetricLabelKey("ARR")).toBe("company.metric_arr");
    expect(inferredMetricLabelKey("YoY Growth")).toBe("company.metric_yoy_growth");
    expect(inferredMetricSourceKey("BSH PRD reference package")).toBe(
      "company.metric_source_bsh_prd",
    );
    expect(inferredMetricSourceKey("Stealth-exit funding disclosure")).toBe(
      "company.metric_source_stealth_funding",
    );
  });

  it("labels the seeded demo values as a placeholder that is not evidence", () => {
    // server/seed_data/company_records.yaml: the class on the value, the
    // longer label on its source ref.
    expect(inferredMetricSourceKey("demo placeholder (v2 design mock)")).toBe(
      "company.metric_source_demo_placeholder",
    );
    expect(inferredMetricSourceKey("Demo placeholder (v2 design mock) — not evidence")).toBe(
      "company.metric_source_demo_placeholder",
    );
  });

  it("builds chart series from metric_history when available", () => {
    const series = companyMetricHistories({
      metric_history: [
        {
          id: "arr",
          label: "ARR",
          label_key: "company.metric_arr",
          points: [
            { period: "2023", value: "$8M" },
            { period: "2024", value: "$14M" },
            { period: "2025", value: "$24M" },
          ],
        },
      ],
    });
    expect(series).toHaveLength(1);
    expect(series[0].points).toHaveLength(3);
    expect(series[0].points[2].value).toBe(24_000_000);
  });
});
