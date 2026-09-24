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
    setDesign("reactor");
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue({ set: false, stages: {}, context: {} });
    apiMock.me.mockResolvedValue({ permissions: [] });
  });

  afterEach(() => {
    setDesign("reactor");
    window.localStorage.removeItem("bsh.research.design");
    setAppLanguage("en");
  });

  it("offers Reactor, Bureau, Folio and Summit Glass, with Reactor chosen", async () => {
    const wrapper = await mountSettings();
    const labels = {};
    const chosen = {};
    for (const name of ["reactor", "bureau", "folio", "glass"]) {
      const option = wrapper.get(`[data-testid="settings-design-${name}"]`);
      labels[name] = option.text();
      chosen[name] = option.attributes("data-selected");
    }
    expect(labels).toEqual({
      reactor: "Reactor",
      bureau: "Bureau",
      folio: "Folio",
      glass: "Summit Glass",
    });
    expect(chosen).toEqual({ reactor: "true", bureau: "false", folio: "false", glass: "false" });
  });

  it("switches the whole app between the designs", async () => {
    const wrapper = await mountSettings();
    for (const name of ["glass", "folio", "bureau", "reactor"]) {
      await wrapper.get(`[data-testid="settings-design-${name}"]`).trigger("click");
      expect(document.documentElement.dataset.design).toBe(name);
      expect(wrapper.get(`[data-testid="settings-design-${name}"]`).attributes("data-selected")).toBe("true");
    }
  });

  it("says Appearance can't lighten Reactor, and only while Reactor is on", async () => {
    const wrapper = await mountSettings();
    const note = () => wrapper.find('[data-testid="settings-appearance-forced"]');
    expect(note().exists()).toBe(true);
    expect(note().text()).toContain("Reactor is a night design");

    await wrapper.get('[data-testid="settings-design-bureau"]').trigger("click");
    expect(note().exists()).toBe(false);
  });

  it("names the designs in Chinese too", async () => {
    setAppLanguage("zh");
    const wrapper = await mountSettings();
    expect(wrapper.get('[data-testid="settings-design-reactor"]').text()).toBe("Reactor 反应堆");
    expect(wrapper.get('[data-testid="settings-design-bureau"]').text()).toBe("Bureau 书案");
  });
});
