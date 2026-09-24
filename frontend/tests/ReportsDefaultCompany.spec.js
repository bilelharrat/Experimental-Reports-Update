import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/api.js", () => ({
  api: {
    listReports: vi.fn().mockResolvedValue([]),
    externalFeed: vi.fn().mockResolvedValue([]),
    listHormuz: vi.fn().mockResolvedValue([]),
    listCompanies: vi.fn().mockResolvedValue([
      { id: "zainar-inc", name: "ZaiNar, Inc.", status: "private" },
      { id: "nvda", name: "NVIDIA Corp.", ticker: "NVDA", status: "public" },
    ]),
    quotesNews: vi.fn().mockResolvedValue({ items: [] }),
    deskPrefs: vi.fn().mockResolvedValue({ updated_at: null, data: {} }),
    saveDeskPrefs: vi.fn().mockResolvedValue({ updated_at: "x", data: {} }),
    runAlertCheck: vi.fn().mockResolvedValue({ checked: 0, fired: [] }),
  },
}));

import App from "../src/App.vue";
import { session } from "../src/auth.js";
import { setLastCompanyId } from "../src/state.js";

// ⌘N, the app menu and the sidebar name no company, so the page decides:
// a company's own page, or the Reports desk filtered to one. They used to
// read only the route's params, so /reports?company=nvda opened on
// whichever company was picked last.

const CustomizerStub = {
  props: ["open", "initialCompanyId", "initialGenerationMode"],
  template:
    '<div data-testid="customizer" :data-open="String(open)" :data-company="initialCompanyId || \'\'" />',
};

async function mountApp(path) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: { template: "<div />" } },
      { path: "/login", name: "login", component: { template: "<div />" } },
      { path: "/reports", name: "reports", component: { template: "<div />" } },
      { path: "/:companyId", name: "research", component: { template: "<div />" } },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(App, {
    global: {
      plugins: [router],
      stubs: {
        Sidebar: { template: "<aside />" },
        ActiveJobsRail: { template: "<div />" },
        DeckSummaryModal: { template: "<div />" },
        CopilotPanel: { template: "<section />" },
        ReportCustomizerModal: CustomizerStub,
        Teleport: true,
      },
    },
  });
  await flushPromises();
  return wrapper;
}

async function pressCommandN() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "n", metaKey: true, bubbles: true }));
  await flushPromises();
}

function customizer(wrapper) {
  const el = wrapper.get('[data-testid="customizer"]');
  return { open: el.attributes("data-open"), company: el.attributes("data-company") };
}

describe("Generate report opens on the company the page names", () => {
  let wrapper;

  beforeEach(() => {
    session.value = {
      token: "test-token",
      email: "qa@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };
  });

  afterEach(() => {
    wrapper?.unmount();
    session.value = null;
    setLastCompanyId("");
  });

  it("uses the Reports desk's company filter", async () => {
    wrapper = await mountApp("/reports?company=nvda");
    await pressCommandN();
    expect(customizer(wrapper)).toEqual({ open: "true", company: "nvda" });
  });

  it("asks when the Reports desk shows every company", async () => {
    wrapper = await mountApp("/reports?company=all");
    await pressCommandN();
    expect(customizer(wrapper)).toEqual({ open: "true", company: "" });
  });

  it("asks off company pages rather than reusing the last company", async () => {
    setLastCompanyId("zainar-inc");
    wrapper = await mountApp("/");
    await pressCommandN();
    expect(customizer(wrapper)).toEqual({ open: "true", company: "" });
  });

  it("keeps a company page's own company", async () => {
    wrapper = await mountApp("/zainar-inc");
    await pressCommandN();
    expect(customizer(wrapper)).toEqual({ open: "true", company: "zainar-inc" });
  });

  it("does the same from the app menu", async () => {
    wrapper = await mountApp("/reports?company=nvda");
    await wrapper.get('[aria-label="Add"]').trigger("click");
    const generate = wrapper
      .findAll('[role="menuitem"]')
      .find((item) => item.text().includes("Generate report"));
    await generate.trigger("click");
    await flushPromises();
    expect(customizer(wrapper)).toEqual({ open: "true", company: "nvda" });
  });
});
