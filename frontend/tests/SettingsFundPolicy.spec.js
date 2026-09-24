import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const apiMock = vi.hoisted(() => ({
  workspaceSettings: vi.fn(),
  updateWorkspaceSettings: vi.fn(),
  userCenter: vi.fn(),
  getFundPolicy: vi.fn(),
  updateFundPolicy: vi.fn(),
  me: vi.fn(),
}));

vi.mock("../src/api.js", () => ({ api: apiMock, withApiToken: (u) => u }));

import SettingsView from "../src/views/SettingsView.vue";
import { setAppLanguage } from "../src/state.js";

// Settings → Fund return policy (server/fund_policy.py, GET/PUT
// /api/settings/fund-policy). Per stage: target MOIC, target IRR %, longest
// hold, largest position as % of fund, gross or net. It starts unset and
// nothing reaches a memo until a stage has a MOIC or IRR target. Admins and
// partners (settings:update, read from /api/auth/me) edit it; everyone else
// reads it.

const UNSET = {
  set: false,
  stages: { early: null, growth: null, late: null },
  updated_at: null,
  updated_by: null,
  context: { fund_size_musd: 100, check_size_min_musd: 1, check_size_max_musd: 5 },
};

const LATE_SET = {
  set: true,
  stages: {
    early: null,
    growth: null,
    late: { target_moic: 2, target_irr_pct: 20, max_hold_years: 5, max_position_pct: 10, basis: "net" },
  },
  updated_at: "2026-09-22T18:00:00Z",
  updated_by: "benma@bshventures.com",
  context: { fund_size_musd: 100, check_size_min_musd: 1, check_size_max_musd: 5 },
};

const ADMIN = ["admin:read", "settings:update", "memo:approve"];
const ANALYST = ["sources:edit", "memo:export", "memo:edit", "tasks:action", "desk:write"];

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

const section = (wrapper) => wrapper.get('[data-testid="settings-fund-policy"]');
const field = (wrapper, stage, key) => wrapper.get(`[data-testid="fund-policy-${stage}-${key}"]`);
const saveButton = (wrapper) => wrapper.get('[data-testid="fund-policy-save"]');

describe("Settings fund return policy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.userCenter.mockResolvedValue({ account: { email: "qa@bsh.org" } });
    apiMock.workspaceSettings.mockResolvedValue({ account: {}, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue(UNSET);
    apiMock.me.mockResolvedValue({ role: "admin", permissions: ADMIN });
  });

  afterEach(() => setAppLanguage("en"));

  it("says plainly that no hurdle is set, and what setting one does", async () => {
    const wrapper = await mountSettings();
    const text = section(wrapper).text();
    expect(text).toContain("Fund return policy");
    expect(wrapper.get('[data-testid="fund-policy-state"]').text()).toBe("Not set");
    expect(text).toContain("state the hurdle and flag any call whose base case misses it");
    expect(text).toContain("Until you set one, nothing changes");
    for (const stage of ["early", "growth", "late"]) {
      expect(wrapper.get(`[data-testid="fund-policy-${stage}-state"]`).text()).toBe("Not set");
    }
    // Fund and check size are context from their own settings, not inputs.
    expect(wrapper.get('[data-testid="fund-policy-context"]').text()).toContain(
      "fund size $100M; check size $1M–$5M",
    );
    // Nothing changed yet, so nothing to save.
    expect(saveButton(wrapper).attributes("disabled")).toBeDefined();
  });

  it("saves a stage's hurdle for an admin, and only the stages with numbers", async () => {
    apiMock.updateFundPolicy.mockResolvedValue(LATE_SET);
    const wrapper = await mountSettings();

    await field(wrapper, "late", "target_moic").setValue("2");
    await field(wrapper, "late", "target_irr_pct").setValue("20");
    await field(wrapper, "late", "max_hold_years").setValue("5");
    await field(wrapper, "late", "max_position_pct").setValue("10");
    await wrapper.get('[data-testid="fund-policy-late-basis-net"]').trigger("click");
    expect(saveButton(wrapper).attributes("disabled")).toBeUndefined();

    await saveButton(wrapper).trigger("click");
    await flushPromises();

    expect(apiMock.updateFundPolicy).toHaveBeenCalledWith({
      stages: {
        early: null,
        growth: null,
        late: { target_moic: 2, target_irr_pct: 20, max_hold_years: 5, max_position_pct: 10, basis: "net" },
      },
    });
    expect(wrapper.get('[data-testid="fund-policy-state"]').text()).toBe("In force");
    expect(wrapper.get('[data-testid="fund-policy-late-state"]').text()).toBe("Set");
    expect(wrapper.get('[data-testid="fund-policy-early-state"]').text()).toBe("Not set");
    expect(wrapper.get('[data-testid="fund-policy-saved"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="fund-policy-updated"]').text()).toBe(
      "Last saved 2026-09-22 by benma@bshventures.com.",
    );
  });

  it("clears a stage whose numbers are all removed", async () => {
    apiMock.getFundPolicy.mockResolvedValue(LATE_SET);
    apiMock.updateFundPolicy.mockResolvedValue(UNSET);
    const wrapper = await mountSettings();
    expect(field(wrapper, "late", "target_moic").element.value).toBe("2");

    for (const key of ["target_moic", "target_irr_pct", "max_hold_years", "max_position_pct"]) {
      await field(wrapper, "late", key).setValue("");
    }
    await saveButton(wrapper).trigger("click");
    await flushPromises();
    expect(apiMock.updateFundPolicy).toHaveBeenCalledWith({
      stages: { early: null, growth: null, late: null },
    });
    expect(wrapper.get('[data-testid="fund-policy-state"]').text()).toBe("Not set");
  });

  it("refuses numbers outside the server's ranges before sending them", async () => {
    const wrapper = await mountSettings();
    await field(wrapper, "growth", "target_moic").setValue("0.5");
    expect(wrapper.get('[data-testid="fund-policy-growth-error"]').text()).toBe(
      "Target MOIC must be a number from 1 to 50.",
    );
    expect(saveButton(wrapper).attributes("disabled")).toBeDefined();
    await saveButton(wrapper).trigger("click");
    expect(apiMock.updateFundPolicy).not.toHaveBeenCalled();

    await field(wrapper, "growth", "target_moic").setValue("3");
    expect(wrapper.find('[data-testid="fund-policy-growth-error"]').exists()).toBe(false);
    expect(saveButton(wrapper).attributes("disabled")).toBeUndefined();
  });

  it("says why a save failed, and keeps the draft", async () => {
    const err = Object.assign(new Error("400 Bad Request"), {
      status: 400,
      detail: { detail: "target IRR % must be between 0 and 500" },
    });
    apiMock.updateFundPolicy.mockRejectedValue(err);
    const wrapper = await mountSettings();
    await field(wrapper, "early", "target_irr_pct").setValue("40");
    await saveButton(wrapper).trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="fund-policy-error"]').text()).toBe(
      "Could not save the policy: target IRR % must be between 0 and 500",
    );
    expect(field(wrapper, "early", "target_irr_pct").element.value).toBe("40");
  });

  it("is read-only for anyone without settings:update", async () => {
    apiMock.me.mockResolvedValue({ role: "analyst", permissions: ANALYST });
    // The account block may claim more; /api/auth/me decides.
    apiMock.workspaceSettings.mockResolvedValue({ account: { permissions: ADMIN }, preferences: {} });
    apiMock.getFundPolicy.mockResolvedValue(LATE_SET);
    const wrapper = await mountSettings();

    expect(section(wrapper).find("input").exists()).toBe(false);
    expect(wrapper.find('[data-testid="fund-policy-save"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="fund-policy-read-only"]').text()).toBe(
      "Only admins and partners can change the policy.",
    );
    const late = wrapper.get('[data-testid="fund-policy-late"]').text();
    for (const value of ["2x", "20%", "5 years", "10% of fund", "Net"]) {
      expect(late).toContain(value);
    }
    expect(wrapper.get('[data-testid="fund-policy-early"]').text()).toContain("Not set");
  });

  it("falls back to the account's permissions when /api/auth/me is unavailable", async () => {
    apiMock.me.mockRejectedValue(new Error("offline"));
    apiMock.workspaceSettings.mockResolvedValue({ account: { permissions: ADMIN }, preferences: {} });
    const wrapper = await mountSettings();
    expect(wrapper.find('[data-testid="fund-policy-late-target_moic"]').exists()).toBe(true);
  });

  it("says so when the policy cannot be loaded", async () => {
    apiMock.getFundPolicy.mockRejectedValue(new Error("500"));
    const wrapper = await mountSettings();
    expect(wrapper.get('[data-testid="fund-policy-load-failed"]').text()).toBe(
      "Could not load the fund policy.",
    );
    // The rest of Settings still works.
    expect(wrapper.find('[data-testid="settings-reports"]').exists()).toBe(true);
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    apiMock.me.mockResolvedValue({ role: "analyst", permissions: ANALYST });
    apiMock.getFundPolicy.mockResolvedValue(LATE_SET);
    const wrapper = await mountSettings();
    const text = section(wrapper).text();
    expect(text).toContain("基金回报门槛");
    expect(wrapper.get('[data-testid="fund-policy-state"]').text()).toBe("已生效");
    expect(text).toContain("目标 MOIC");
    expect(wrapper.get('[data-testid="fund-policy-late"]').text()).toContain("2 倍");
    expect(wrapper.get('[data-testid="fund-policy-late"]').text()).toContain("净收益");
    expect(text).toContain("只有管理员和合伙人可以修改回报门槛。");
  });
});
