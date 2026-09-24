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
import { setAppLanguage } from "../src/state.js";

// The workspace's memo template: the standard 5-section memo, or the
// founder's IC template (v2), the server's default since v2 was turned on.
// GET /api/workspace/settings reports the one in force as
// memo_template_effective; PATCH takes {memo_template}.

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

const checked = (wrapper) =>
  wrapper.findAll('[role="radio"]').filter((b) => b.attributes("aria-checked") === "true")
    .map((b) => b.attributes("data-testid"));

describe("Settings memo template", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue({ set: false, stages: {}, context: {} });
    apiMock.me.mockResolvedValue({ permissions: [] });
  });

  afterEach(() => setAppLanguage("en"));

  it("reads an unset template as the IC template, the server's default, and says whom it applies to", async () => {
    const wrapper = await mountSettings();
    const section = wrapper.get('[data-testid="settings-reports"]');
    expect(section.text()).toContain("Memo template");
    expect(section.text()).toContain("Standard memo (v1)");
    expect(section.text()).toContain("Founder's IC template (default)");
    // The IC template is no longer a beta that "may fail more often".
    expect(section.text()).not.toMatch(/beta|signed off/i);
    expect(section.text()).toContain("Buffett-Method memos are unaffected");
    expect(checked(wrapper)).toEqual(["memo-template-ic_v2"]);
  });

  it("shows the standard memo when the workspace chose it", async () => {
    apiMock.workspaceSettings.mockResolvedValue({
      account: {},
      preferences: {},
      memo_template: "standard",
      memo_template_effective: "standard",
    });
    const wrapper = await mountSettings();
    expect(checked(wrapper)).toEqual(["memo-template-standard"]);
  });

  it("saves the standard memo through PATCH", async () => {
    apiMock.updateWorkspaceSettings.mockResolvedValue({
      account: {},
      preferences: {},
      memo_template: "standard",
      memo_template_effective: "standard",
    });
    const wrapper = await mountSettings();
    await wrapper.get('[data-testid="memo-template-standard"]').trigger("click");
    await flushPromises();
    expect(apiMock.updateWorkspaceSettings).toHaveBeenCalledWith({ memo_template: "standard" });
    expect(checked(wrapper)).toEqual(["memo-template-standard"]);
    expect(wrapper.find('[data-testid="memo-template-not-saved"]').exists()).toBe(false);
  });

  it("says so when the server does not keep the choice", async () => {
    // A server without the field accepts the PATCH and ignores it.
    apiMock.updateWorkspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    const wrapper = await mountSettings();
    await wrapper.get('[data-testid="memo-template-standard"]').trigger("click");
    await flushPromises();
    expect(checked(wrapper)).toEqual(["memo-template-ic_v2"]);
    expect(wrapper.get('[data-testid="memo-template-not-saved"]').text()).toContain(
      "runs still use the template marked here",
    );
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const wrapper = await mountSettings();
    const section = wrapper.get('[data-testid="settings-reports"]');
    expect(section.text()).toContain("备忘录模板");
    expect(section.text()).toContain("标准备忘录（v1）");
    expect(section.text()).toContain("创始人投委会模板（默认）");
  });
});
