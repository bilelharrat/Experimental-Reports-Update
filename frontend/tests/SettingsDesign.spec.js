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
import { BUREAU_DESKS, DEFAULT_BUREAU_DESK, setBureauDesk, setDesign } from "../src/design.js";
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
    setDesign("bureau");
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue({ set: false, stages: {}, context: {} });
    apiMock.me.mockResolvedValue({ permissions: [] });
  });

  afterEach(() => {
    setDesign("bureau");
    setBureauDesk(DEFAULT_BUREAU_DESK);
    window.localStorage.removeItem("bsh.research.design");
    window.localStorage.removeItem("bsh.research.bureauDesk");
    setAppLanguage("en");
  });

  it("offers Bureau, Folio and Summit Glass, with Bureau chosen", async () => {
    const wrapper = await mountSettings();
    const bureau = wrapper.get('[data-testid="settings-design-bureau"]');
    const folio = wrapper.get('[data-testid="settings-design-folio"]');
    const glass = wrapper.get('[data-testid="settings-design-glass"]');
    expect(bureau.text()).toBe("Bureau");
    expect(folio.text()).toBe("Folio");
    expect(glass.text()).toBe("Summit Glass");
    expect(bureau.attributes("data-selected")).toBe("true");
    expect(folio.attributes("data-selected")).toBe("false");
    expect(glass.attributes("data-selected")).toBe("false");
  });

  it("switches the whole app between the three designs", async () => {
    const wrapper = await mountSettings();
    await wrapper.get('[data-testid="settings-design-glass"]').trigger("click");
    expect(document.documentElement.dataset.design).toBe("glass");
    expect(wrapper.get('[data-testid="settings-design-glass"]').attributes("data-selected")).toBe("true");
    await wrapper.get('[data-testid="settings-design-folio"]').trigger("click");
    expect(document.documentElement.dataset.design).toBe("folio");
    await wrapper.get('[data-testid="settings-design-bureau"]').trigger("click");
    expect(document.documentElement.dataset.design).toBe("bureau");
    expect(wrapper.get('[data-testid="settings-design-bureau"]').attributes("data-selected")).toBe("true");
  });

  it("names Bureau in Chinese too", async () => {
    setAppLanguage("zh");
    const wrapper = await mountSettings();
    expect(wrapper.get('[data-testid="settings-design-bureau"]').text()).toBe("Bureau 书案");
  });
});

describe("Settings desk color", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    setDesign("bureau");
    setBureauDesk(DEFAULT_BUREAU_DESK);
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue({ set: false, stages: {}, context: {} });
    apiMock.me.mockResolvedValue({ permissions: [] });
  });

  afterEach(() => {
    setDesign("bureau");
    setBureauDesk(DEFAULT_BUREAU_DESK);
    window.localStorage.removeItem("bsh.research.design");
    window.localStorage.removeItem("bsh.research.bureauDesk");
    setAppLanguage("en");
  });

  const picker = (wrapper) => wrapper.find('[data-testid="bureau-desk-picker"]');

  it("offers the seven desks as a radio group while Bureau is on, Onyx & White chosen", async () => {
    const wrapper = await mountSettings();
    expect(picker(wrapper).exists()).toBe(true);
    expect(picker(wrapper).element.tagName).toBe("FIELDSET");
    expect(picker(wrapper).get("legend").text()).toBe("Desk color");

    const radios = picker(wrapper).findAll('input[type="radio"]');
    expect(radios.map((radio) => radio.element.value)).toEqual(BUREAU_DESKS);
    // One group: the arrow keys move between the desks.
    expect(new Set(radios.map((radio) => radio.attributes("name"))).size).toBe(1);

    const onyx = wrapper.get('[data-testid="bureau-desk-onyx"]');
    expect(onyx.text()).toBe("Onyx & White");
    expect(onyx.attributes("data-selected")).toBe("true");
    expect(onyx.get("input").element.checked).toBe(true);
    expect(wrapper.get('[data-testid="bureau-desk-green"]').text()).toBe("Bottle green");
    expect(wrapper.get('[data-testid="bureau-desk-green"]').attributes("data-selected")).toBe("false");
  });

  it("shows only while Bureau is the design", async () => {
    const wrapper = await mountSettings();
    expect(picker(wrapper).exists()).toBe(true);
    await wrapper.get('[data-testid="settings-design-folio"]').trigger("click");
    expect(picker(wrapper).exists()).toBe(false);
    await wrapper.get('[data-testid="settings-design-glass"]').trigger("click");
    expect(picker(wrapper).exists()).toBe(false);
    await wrapper.get('[data-testid="settings-design-bureau"]').trigger("click");
    expect(picker(wrapper).exists()).toBe(true);
  });

  it("applies a desk the moment it is chosen", async () => {
    const wrapper = await mountSettings();
    await wrapper.get('[data-testid="bureau-desk-maroon"] input').setValue(true);
    expect(document.documentElement.dataset.desk).toBe("maroon");
    expect(window.localStorage.getItem("bsh.research.bureauDesk")).toBe("maroon");
    expect(wrapper.get('[data-testid="bureau-desk-maroon"]').attributes("data-selected")).toBe("true");
    expect(wrapper.get('[data-testid="bureau-desk-onyx"]').attributes("data-selected")).toBe("false");

    await wrapper.get('[data-testid="bureau-desk-green"] input').setValue(true);
    expect(document.documentElement.dataset.desk).toBe("green");
  });

  it("names the desks in Chinese too", async () => {
    setAppLanguage("zh");
    const wrapper = await mountSettings();
    expect(picker(wrapper).get("legend").text()).toBe("书案颜色");
    expect(wrapper.get('[data-testid="bureau-desk-onyx"]').text()).toBe("Onyx & White 黑白");
  });
});
