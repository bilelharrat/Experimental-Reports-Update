import { describe, expect, it } from "vitest";

import { localizedChangeHighlights } from "../src/traderStatsI18n.js";

const translations = {
  "trader_stats.field_last_price": "最新价格",
  "trader_stats.field_ma_crossover": "均线交叉",
  "trader_stats.field_next_catalyst": "下一催化剂",
  "trader_stats.field_change": "{field}：{before} → {after}",
  "trader_stats.field_updated": "{field}：已更新",
  "trader_stats.value_none": "暂无",
  "trader_stats.value_golden_cross": "金叉",
  "trader_stats.delta_catalysts_added": "新增催化剂：{count} 项",
  "trader_stats.delta_news_added": "新增交易新闻：{count} 条",
};

function t(key, vars = {}) {
  return (translations[key] || key).replace(/\{(\w+)\}/g, (_, name) => vars[name]);
}

describe("localizedChangeHighlights", () => {
  const record = {
    change_summary: {
      field_changes: [
        { field: "Last price", before: 327.74, after: 321.66 },
        { field: "MA crossover", before: "golden_cross", after: null },
        {
          field: "Next catalyst",
          before: "FQ3 earnings release",
          after: "Q3 FY2026 earnings",
        },
      ],
      highlights: [
        "Last price: 327.74 -> 321.66",
        "Catalysts added: 2026-07-30: Earnings, 2026-09-09: iPhone event",
        "Trader news added: 2026-07-21: Apple earnings due",
      ],
    },
  };

  it("preserves stored highlights in English", () => {
    expect(localizedChangeHighlights(record, "en", t)).toBe(
      record.change_summary.highlights,
    );
  });

  it("uses structured changes and localized counts in Chinese", () => {
    expect(localizedChangeHighlights(record, "zh", t)).toEqual([
      "最新价格：327.74 → 321.66",
      "均线交叉：金叉 → 暂无",
      "下一催化剂：已更新",
      "新增催化剂：2 项",
      "新增交易新闻：1 条",
    ]);
  });
});
