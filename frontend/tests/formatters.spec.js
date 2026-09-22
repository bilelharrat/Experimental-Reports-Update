import { describe, expect, it } from "vitest";

import {
  accountInitials,
  companyInitials,
  displayNameFromEmail,
  formatCompactNumber,
  formatIsoDate,
  formatMetricValue,
  humanizeStatus,
  isPendingValue,
  normalizeReportStatus,
} from "../src/formatters.js";

describe("user-facing formatters", () => {
  it("compacts large financial values and preserves metric meaning", () => {
    expect(formatCompactNumber(1_250_000_000, { currency: true })).toBe("$1.3B");
    expect(formatCompactNumber(12_500_000)).toBe("12.5M");
    expect(formatMetricValue("CAGR", 24)).toBe("+24%");
    expect(formatMetricValue("Revenue", 450_000_000)).toBe("$450M");
  });

  it("renders pending values quietly", () => {
    expect(isPendingValue("unknown/pending")).toBe(true);
    expect(formatCompactNumber("source pending")).toBe("—");
  });

  it("normalizes dates and backend statuses", () => {
    expect(formatIsoDate("2026-07-20T19:22:00Z")).toBe("2026-07-20");
    expect(humanizeStatus("failed_during_analysis")).toBe("Failed");
    expect(humanizeStatus("ready_for_input", "待处理", "zh")).toBe("等待输入");
  });

  it("buckets report statuses as the Reports page does", () => {
    expect(normalizeReportStatus("complete")).toBe("complete");
    expect(normalizeReportStatus("complete_with_warnings")).toBe("needs_attention");
    expect(normalizeReportStatus("awaiting_studio")).toBe("needs_attention");
    expect(normalizeReportStatus("failed_during_analysis")).toBe("failed");
    expect(normalizeReportStatus("queued")).toBe("running");
  });

  it("builds display names and initials from emails", () => {
    expect(displayNameFromEmail("bilel.harrat@bshventures.com")).toBe("Bilel Harrat");
    expect(accountInitials("bilel.harrat@bshventures.com")).toBe("BH");
    expect(accountInitials("Bilel Harrat")).toBe("BH");
    expect(accountInitials("elina.sun@bshfoundation.org")).toBe("ES");
    expect(accountInitials("robert@bshventures.com")).toBe("RO");
    expect(accountInitials("")).toBe("?");
  });

  it("builds compact company rail initials without color cues", () => {
    expect(companyInitials({ name: "ZaiNar, Inc." })).toBe("ZI");
    expect(companyInitials({ name: "Acme Inc." })).toBe("AI");
    expect(companyInitials({ name: "OpenAI" })).toBe("OA");
    expect(companyInitials({ name: "NVIDIA" })).toBe("NV");
    expect(companyInitials({ name: "Taiwan Semiconductor", ticker: "TSM" })).toBe("TS");
    expect(companyInitials({ name: "G" })).toBe("G");
    expect(companyInitials({})).toBe("?");
  });
});
