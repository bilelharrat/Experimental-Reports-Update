// Component test for TraderView.vue — verifies the empty state vs the
// populated grid and the refresh button wiring. The api module is
// mocked so the component mounts without HTTP.

import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  refresh: vi.fn(() => Promise.resolve({
    job_id: "amd", status: "queued",
    stream_url: "/api/companies/amd/trader/refresh/stream",
  })),
  streamUrl: vi.fn(() => "/fake/stream"),
  getCompany: vi.fn(() => Promise.resolve({ id: "amd", trader_snapshot: null })),
}));

vi.mock("../src/api.js", () => ({
  api: {
    trader: { refresh: m.refresh, streamUrl: m.streamUrl },
    getCompany: m.getCompany,
  },
}));

class FakeEventSource {
  constructor() {
    this.onmessage = null;
    this.onerror = null;
  }
  close() {}
}
globalThis.EventSource = FakeEventSource;

import TraderView from "../src/components/TraderView.vue";

function mountWith(company) {
  return mount(TraderView, { props: { company } });
}

describe("TraderView empty state", () => {
  it("renders the 'no snapshot yet' hint when trader_snapshot is null", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: null,
    });
    expect(wrapper.text()).toContain("No trader snapshot yet");
  });
});

describe("TraderView populated state", () => {
  const snapshot = {
    refreshed_at: new Date().toISOString(),
    price_card: {
      last_price: 174.22, currency: "USD", as_of: "2026-05-13T15:59:00-04:00",
      change_pct_1d: 1.82, change_pct_5d: 4.10, change_pct_30d: 12.41,
      change_pct_ytd: 28.03, change_pct_1y: 47.55,
      vs_sector_30d_pct: 14.20, vs_sp500_30d_pct: 9.80,
    },
    momentum_card: {
      trend: "bullish", above_50dma: true, above_200dma: true,
      ma_crossover_recent: null, breakout_signals: ["5-day high"],
      notable_levels: { support: 162, resistance: 178.5 },
    },
    sentiment_card: {
      analyst_consensus: "Buy", coverage_count: 51,
      rating_distribution: {
        strong_buy: 18, buy: 20, hold: 12, sell: 1, strong_sell: 0,
      },
      target_price: { mean: 195, high: 230, low: 148 },
      recent_rating_changes: [],
    },
    heat_card: {
      rel_volume_20d: 1.4, iv_30d_pct: 42, iv_percentile_1y: 78,
      options_skew: "call_bid", news_flow_24h: 11,
      insider_activity_30d: { buys: 0, sells: 2, net_share_count_change: -45000 },
      short_interest_pct_float: 2.1, days_to_cover: 1.8,
      social_mentions_trend: "rising",
    },
    catalysts: [
      { date: "2026-07-30", type: "earnings", title: "Q2 2026 earnings",
        summary: "", est_impact: "high" },
    ],
    trader_news: [
      { headline: "Q1 beat", date: "2026-05-07", summary: "",
        bias: "positive", source_url: "https://example.com" },
    ],
  };

  it("renders the price card with the last price and a 1d return", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("$174.22");
    expect(text).toContain("+1.8%");
    expect(text).toContain("Buy");
    expect(text).toContain("Q2 2026 earnings");
    expect(text).toContain("Q1 beat");
  });

  it("clicking Refresh calls api.trader.refresh", async () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshot,
    });
    const button = wrapper.findAll("button")
      .find((b) => b.text().includes("Refresh"));
    expect(button).toBeTruthy();
    await button.trigger("click");
    await flushPromises();
    expect(m.refresh).toHaveBeenCalledWith("amd");
  });
});
