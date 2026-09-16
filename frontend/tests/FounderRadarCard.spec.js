import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import FounderRadarCard from "../src/components/research/FounderRadarCard.vue";
import { api } from "../src/api.js";

vi.mock("../src/api.js", () => {
  const mock = {
    getFounderDossier: vi.fn(),
    deepSearchFounder: vi.fn(),
  };
  return { default: mock, api: mock };
});

const dossier = {
  company_id: "zainar-inc",
  founders: [
    {
      name: "Daniel Jacker",
      role: "Co-founder & CEO",
      bio: "Leads PNT architecture.",
      pedigree_tags: ["Stanford"],
      education: null,
      past_companies: ["Acme"],
      prior_exits: "Sold Acme",
      linkedin_url: "https://linkedin.com/in/daniel",
      profile_url: null,
    },
  ],
  advisors_and_board: [
    { name: "Steve Jurvetson", role: "Board Member", bio: null, profile_url: "https://future.ventures" },
  ],
  team_headcount: {
    employee_count_estimate: "50-200",
    engineering_pct: 60,
    gtm_sales_pct: null,
    operations_pct: null,
    open_roles_count: 4,
    hiring_velocity: null,
  },
  developer_traction: null,
  is_deep_audited: false,
};

describe("FounderRadarCard (Team tab)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders leadership, board and headcount from the founder dossier", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    const wrapper = mount(FounderRadarCard, { props: { companyId: "zainar-inc", company: {} } });
    await flushPromises();

    expect(api.getFounderDossier).toHaveBeenCalledWith("zainar-inc");
    const leadership = wrapper.find('[data-testid="founder-leadership"]');
    expect(leadership.exists()).toBe(true);
    expect(leadership.text()).toContain("Daniel Jacker");
    expect(leadership.text()).toContain("Co-founder & CEO");
    expect(leadership.text()).toContain("Leads PNT architecture.");
    expect(leadership.text()).toContain("Ex-Acme");
    expect(leadership.text()).toContain("Stanford");
    expect(leadership.find('a[href="https://linkedin.com/in/daniel"]').exists()).toBe(true);

    const board = wrapper.find('[data-testid="founder-board"]');
    expect(board.text()).toContain("Steve Jurvetson");
    expect(board.find('a[href="https://future.ventures"]').exists()).toBe(true);

    const headcount = wrapper.find('[data-testid="founder-headcount"]');
    expect(headcount.text()).toContain("50-200");
    expect(headcount.text()).toContain("60%");
    expect(headcount.text()).toContain("4 open roles");
    expect(wrapper.find('[data-testid="founder-empty"]').exists()).toBe(false);
  });

  it("falls back to the company record's people while the dossier is unavailable", async () => {
    api.getFounderDossier.mockRejectedValue(new Error("boom"));
    const wrapper = mount(FounderRadarCard, {
      props: {
        companyId: "acme",
        company: {
          team_profiles: [{ name: "Ada Example", role: "CEO" }],
          board_investors: [{ name: "Grace Board", role: "Director" }],
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Ada Example");
    expect(wrapper.text()).toContain("Grace Board");
    expect(wrapper.find('[data-testid="founder-load-failed"]').exists()).toBe(false);
  });

  it("shows a retryable error when the dossier fails and the record has no people", async () => {
    api.getFounderDossier.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(dossier);
    const wrapper = mount(FounderRadarCard, { props: { companyId: "acme", company: {} } });
    await flushPromises();

    const failed = wrapper.find('[data-testid="founder-load-failed"]');
    expect(failed.exists()).toBe(true);
    await failed.find("button").trigger("click");
    await flushPromises();

    expect(api.getFounderDossier).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[data-testid="founder-load-failed"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("Daniel Jacker");
  });

  it("shows the empty state when the record has nobody", async () => {
    api.getFounderDossier.mockResolvedValue({ ...dossier, founders: [], advisors_and_board: [], team_headcount: null });
    const wrapper = mount(FounderRadarCard, { props: { companyId: "acme", company: {} } });
    await flushPromises();
    expect(wrapper.find('[data-testid="founder-empty"]').exists()).toBe(true);
  });

  it("refresh re-reads the record through deep-search", async () => {
    api.getFounderDossier.mockResolvedValue({ ...dossier, founders: [] });
    api.deepSearchFounder.mockResolvedValue(dossier);
    const wrapper = mount(FounderRadarCard, { props: { companyId: "zainar-inc", company: {} } });
    await flushPromises();
    expect(wrapper.text()).not.toContain("Daniel Jacker");

    await wrapper.find('[data-testid="founder-refresh"]').trigger("click");
    await flushPromises();
    expect(api.deepSearchFounder).toHaveBeenCalledWith("zainar-inc");
    expect(wrapper.text()).toContain("Daniel Jacker");
  });
});
