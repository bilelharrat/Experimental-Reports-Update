import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

// The three panes are `defineAsyncComponent`s, and their dynamic import fires
// even though each is stubbed below. Left real, those imports pull in ~5,000
// lines plus live-quote polling and land after the environment is torn down.
// Mocking the modules keeps the loader instant and the teardown quiet.
const pane = (name) => ({ default: { name, template: `<div data-pane="${name}" />` } });
vi.mock("../src/views/MarketRadarView.vue", () => pane("MarketRadarView"));
vi.mock("../src/views/WeeklySummaryView.vue", () => pane("WeeklySummaryView"));
vi.mock("../src/views/NewsDeskView.vue", () => pane("NewsDeskView"));

import MarketsView from "../src/views/MarketsView.vue";

// Market, Pulse and News share one component with a tab bar, and each also
// has its own sidebar row and its own page. Two things matter here: each tab
// lives at its own PATH — the sidebar's glider keys off
// `router-link-exact-active`, which ignores the query, so switching tab has to
// move to that tab's page for its row to light up — and only the selected tab
// is mounted, because MarketRadarView alone is ~3,600 lines and each view
// installs its own large-title scroll observer.

const MacTabBarStub = {
  props: ["items", "modelValue"],
  emits: ["update:modelValue"],
  template:
    '<div><button v-for="i in items" :key="i.id" :data-tab="i.id"' +
    ' :data-active="i.id === modelValue"' +
    " @click=\"$emit('update:modelValue', i.id)\">{{ i.label }}</button></div>",
};

async function mountMarkets(query = {}, name = null) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/markets", name: "markets", component: MarketsView },
      { path: "/market-radar", name: "market-radar", component: MarketsView, meta: { tab: "market" } },
      { path: "/weekly-summary", name: "weekly-summary", component: MarketsView, meta: { tab: "pulse" } },
      { path: "/news-desk", name: "news-desk", component: MarketsView, meta: { tab: "news" } },
    ],
  });
  router.push(name ? { name, query } : { name: "markets", query });
  await router.isReady();
  const wrapper = mount(MarketsView, {
    global: {
      plugins: [router],
      stubs: {
        MacTabBar: MacTabBarStub,
        MarketRadarView: true,
        WeeklySummaryView: true,
        NewsDeskView: true,
      },
    },
  });
  // The three panes are `defineAsyncComponent`s, and their dynamic import
  // starts even though each is stubbed. Let those imports settle inside the
  // test: an import that lands after teardown is an unhandled rejection.
  await flushPromises();
  return { wrapper, router };
}

function activeTab(wrapper) {
  return wrapper
    .findAll("[data-tab]")
    .find((b) => b.attributes("data-active") === "true")
    ?.attributes("data-tab");
}

describe("MarketsView", () => {
  it("offers the three tabs in order and defaults to Market", async () => {
    const { wrapper } = await mountMarkets();
    expect(
      wrapper.findAll("[data-tab]").map((b) => b.attributes("data-tab")),
    ).toEqual(["market", "pulse", "news"]);
    expect(activeTab(wrapper)).toBe("market");
  });

  it("reads the active tab from the query", async () => {
    const { wrapper } = await mountMarkets({ tab: "news" });
    expect(activeTab(wrapper)).toBe("news");
  });

  it("falls back to Market for an unknown tab", async () => {
    const { wrapper } = await mountMarkets({ tab: "nonsense" });
    expect(activeTab(wrapper)).toBe("market");
  });

  it("reads the active tab from the page it is mounted at", async () => {
    const { wrapper } = await mountMarkets({}, "weekly-summary");
    expect(activeTab(wrapper)).toBe("pulse");
  });

  it("moves to the tab's own page, so its sidebar row lights up", async () => {
    const { wrapper, router } = await mountMarkets({ panel: "wei" }, "market-radar");
    await wrapper.find('[data-tab="pulse"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("weekly-summary");
    expect(router.currentRoute.value.path).toBe("/weekly-summary");
    // The page carries the tab now; everything else in the query survives.
    expect(router.currentRoute.value.query).toEqual({ panel: "wei" });
  });
});
