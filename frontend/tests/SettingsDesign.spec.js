import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const apiMock = vi.hoisted(() => ({
  workspaceSettings: vi.fn(),
  updateWorkspaceSettings: vi.fn(),
  userCenter: vi.fn(),
  getFundPolicy: vi.fn(),
  me: vi.fn(),
}));

vi.mock("../src/api.js", () => ({ api: apiMock, withApiToken: (u) => u }));

import SettingsView from "../src/views/SettingsView.vue";
import { setDesign } from "../src/design.js";
import { setAppLanguage } from "../src/state.js";

async function mountSettings() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/settings", name: "settings", component: SettingsView },
      { path: "/account/password", name: "change-password", component: { template: "<div />" } },
      { path: "/accounts", name: "accounts", component: { template: "<div />" } },
      { path: "/login", name: "login", component: { template: "<div />" } },
      { path: "/stock-research", name: "stock-research", component: { template: "<div />" } },
      { path: "/trader-stats", name: "trader-stats", component: { template: "<div />" } },
      { path: "/innovation-lab", name: "innovation-lab", component: { template: "<div />" } },
    ],
  });
  await router.push("/settings");
  await router.isReady();
  const wrapper = mount(SettingsView, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("Settings design switch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    setDesign("folio");
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue({ set: false, stages: {}, context: {} });
    apiMock.me.mockResolvedValue({ permissions: [] });
  });

  afterEach(() => {
    setDesign("folio");
    window.localStorage.removeItem("bsh.research.design");
    setAppLanguage("en");
  });

  it("offers Folio and Summit Glass, with Folio chosen", async () => {
    const wrapper = await mountSettings();
    const folio = wrapper.get('[data-testid="settings-design-folio"]');
    const glass = wrapper.get('[data-testid="settings-design-glass"]');
    expect(folio.text()).toBe("Folio");
    expect(glass.text()).toBe("Summit Glass");
    expect(folio.attributes("data-selected")).toBe("true");
    expect(glass.attributes("data-selected")).toBe("false");
  });

  it("switches the whole app to Summit Glass and back", async () => {
    const wrapper = await mountSettings();
    await wrapper.get('[data-testid="settings-design-glass"]').trigger("click");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(wrapper.get('[data-testid="settings-design-glass"]').attributes("data-selected")).toBe("true");
    await wrapper.get('[data-testid="settings-design-folio"]').trigger("click");
    expect(document.documentElement.dataset.design).toBe("folio");
  });
});
