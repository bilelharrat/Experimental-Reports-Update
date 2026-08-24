import { describe, expect, it } from "vitest";

import {
  formatCompactNumber,
  formatIsoDate,
  formatMetricValue,
  humanizeStatus,
  isPendingValue,
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
    expect(humanizeStatus("failed_during_analysis")).toBe("Needs attention");
    expect(humanizeStatus("ready_for_input", "待处理", "zh")).toBe("等待输入");
  });
});
