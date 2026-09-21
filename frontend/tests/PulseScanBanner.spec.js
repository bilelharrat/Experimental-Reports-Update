import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

// Every API call answers with empty data except the weekly summary under test.
const summaryFor = vi.hoisted(() => ({ value: null }));
vi.mock("../src/api.js", () => {
  // Callable at any depth (api.researchPages.marketPulse()), resolving empty.
  const deep = () =>
    new Proxy(() => Promise.resolve({}), {
      get: (_target, key) => (key === "then" ? undefined : deep()),
    });
  const weeklyStocks = {
    get: () => Promise.resolve({ summary: summaryFor.value }),
    refresh: () => Promise.resolve({}),
    streamUrl: () => "",
  };
  const known = { weeklyStocks, listActiveJobs: () => Promise.resolve([]) };
  const api = new Proxy(known, { get: (target, key) => (key in target ? target[key] : deep()) });
  return { api, default: api, withApiToken: (u) => u, userMessage: (e, f) => f };
});

import WeeklySummaryView from "../src/views/WeeklySummaryView.vue";

// When no AI can run, the Pulse dashboard now ranks this week's movers from
// market data instead of the fixed watchlist — and the banner has to say
// which of the two it is: real moves without catalysts, or a stand-in list.

function summary(mode) {
  return {
    schema_version: 2,
    scan_fallback: true,
    scan_mode: mode,
    week_label: "Week of September 21-21, 2026",
    market_pulse: "x",
    stocks: [],
    watchlist: [],
    summary_cards: [],
    sources: [],
  };
}

async function mountPulse(mode) {
  summaryFor.value = summary(mode);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/market-radar", name: "market-radar", component: { template: "<div />" } },
      { path: "/market-pulse", name: "research-page-market-pulse", component: { template: "<div />" } },
    ],
  });
  router.push("/");
  await router.isReady();
  const wrapper = mount(WeeklySummaryView, {
    global: { plugins: [router], stubs: { PulseECGIcon: true } },
  });
  await flushPromises();
  return wrapper;
}

describe("Pulse scan fallback banner", () => {
  it("says the moves are real when they were ranked from market data", async () => {
    const wrapper = await mountPulse("market_data");
    const banner = wrapper.get('[data-testid="pulse-scan-fallback"]').text();
    expect(banner).toContain("ranked from market data");
    expect(banner).toContain("price moves are real");
    expect(banner).not.toContain("static watchlist");
  });

  it("still warns when even market data failed and the fixed list stood in", async () => {
    const wrapper = await mountPulse("static");
    expect(wrapper.get('[data-testid="pulse-scan-fallback"]').text()).toContain("static watchlist");
  });
});
