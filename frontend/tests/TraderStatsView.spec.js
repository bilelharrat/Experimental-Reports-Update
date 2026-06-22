import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import TraderStatsView from "../src/views/TraderStatsView.vue";
import { api } from "../src/api.js";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a href='#'><slot /></a>",
  },
}));

vi.mock("../src/api.js", () => ({
  api: {
    trader: {
      stats: vi.fn(),
    },
  },
}));

const statsPayload = {
  totals: {
    recorded_count: 1,
    total_tokens: 24000,
    average_change_pct: 4.25,
    failed_section_count: 1,
    cost_usd: 1.23,
  },
  items: [
    {
      company_id: "nvidia",
      ticker: "NVDA",
      company_name: "NVIDIA",
      latest_record: {
        status: "done",
        refreshed_at: "2026-06-17T12:00:00Z",
        duration_ms: 62000,
        cost_usd: 0.42,
        token_usage: {
          total_tokens: 24000,
          by_thread: [{ thread: "heat_card", total_tokens: 12000, duration_ms: 30000 }],
        },
        change_summary: {
          change_pct: 4.25,
          changed_sections: ["heat_card", "research_overview"],
          highlights: ["Heat card changed."],
        },
        failed_sections: [{ thread: "catalysts", error: "Timed out fetching catalysts." }],
      },
      history: [
        {
          recorded_at: "2026-06-17T12:00:00Z",
          duration_ms: 62000,
          cost_usd: 0.42,
          token_usage: { total_tokens: 24000 },
          change_summary: { change_pct: 4.25 },
          failed_sections: [{ thread: "catalysts", error: "Timed out fetching catalysts." }],
        },
      ],
    },
  ],
};

describe("TraderStatsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.trader.stats.mockResolvedValue(statsPayload);
  });

  it("keeps cost out of the high-level dashboard and folds status into the symbol row", async () => {
    const wrapper = mount(TraderStatsView);
    await flushPromises();

    const topMetrics = wrapper.find("[aria-live='polite']");
    expect(topMetrics.text()).toContain("Symbols");
    expect(topMetrics.text()).toContain("Tokens");
    expect(topMetrics.text()).toContain("Failed sections");
    expect(topMetrics.text()).not.toContain("Cost");

    const headers = wrapper.findAll("thead th").map((header) => header.text());
    expect(headers).not.toContain("Status");
    expect(wrapper.text()).toContain("partial");
    expect(wrapper.text()).toContain("catalysts");
    expect(wrapper.text()).toContain("Timed out fetching catalysts.");
  });
});
