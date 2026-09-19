import { describe, expect, it } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

import MarketsView from "../src/views/MarketsView.vue";

// Market, Pulse and News used to be three sidebar rows and three routes for
// one idea. They are tabs now. Two things matter here: the tab lives in the
// QUERY — the sidebar's glider keys off `router-link-exact-active`, so a path
// segment would drop the Markets highlight the moment you changed tab — and
// only the selected tab is mounted, because MarketRadarView alone is ~3,600
// lines and each view installs its own large-title scroll observer.

const MacTabBarStub = {
  props: ["items", "modelValue"],
  emits: ["update:modelValue"],
  template:
    '<div><button v-for="i in items" :key="i.id" :data-tab="i.id"' +
    ' :data-active="i.id === modelValue"' +
    " @click=\"$emit('update:modelValue', i.id)\">{{ i.label }}</button></div>",
};

async function mountMarkets(query = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/markets", name: "markets", component: MarketsView }],
  });
  router.push({ name: "markets", query });
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

  it("keeps the tab in the query, so the Markets nav row stays active", async () => {
    const { wrapper, router } = await mountMarkets({ tab: "market" });
    await wrapper.find('[data-tab="pulse"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("markets");
    expect(router.currentRoute.value.path).toBe("/markets");
    expect(router.currentRoute.value.query.tab).toBe("pulse");
  });
});
