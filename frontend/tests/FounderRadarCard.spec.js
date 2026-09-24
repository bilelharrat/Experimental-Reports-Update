import { describe, expect, it, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import FounderRadarCard from "../src/components/research/FounderRadarCard.vue";
import { api } from "../src/api.js";
import { researchingCompanies } from "../src/founderResearch.js";

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
      education: "Stanford",
      past_companies: ["Acme"],
      prior_exits: "Sold Acme",
      linkedin_url: "https://linkedin.com/in/daniel",
      profile_url: null,
    },
  ],
  advisors_and_board: [
    {
      name: "Steve Jurvetson",
      role: "Board Member",
      bio: null,
      pedigree_tags: [],
      past_companies: [],
      profile_url: "https://future.ventures",
    },
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

function mountCard(companyId = "zainar-inc", company = {}) {
  return mount(FounderRadarCard, { props: { companyId, company } });
}

describe("FounderRadarCard (the desk's Team tab)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    researchingCompanies.clear();
  });

  it("reads the founder dossier for the company it is given", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    mountCard();
    await flushPromises();
    expect(api.getFounderDossier).toHaveBeenCalledWith("zainar-inc");
  });

  it("renders the people, the board and the headcount the record carries", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    const wrapper = mountCard();
    await flushPromises();

    const text = wrapper.text();
    // Leadership, with the detail the dossier merges in from team_profiles.
    expect(text).toContain("Daniel Jacker");
    expect(text).toContain("Co-founder & CEO");
    expect(text).toContain("Leads PNT architecture.");
    expect(text).toContain("Stanford");
    // The board is its own section, not folded into leadership.
    expect(text).toContain("Steve Jurvetson");
    // Headcount comes off the record, not a guess.
    expect(text).toContain("50-200");
    expect(text).toContain("60");

    // Links are real links out to the person.
    expect(wrapper.find('a[href="https://linkedin.com/in/daniel"]').exists()).toBe(true);
    expect(wrapper.find('a[href="https://future.ventures"]').exists()).toBe(true);
  });

  it("lists each person once, in the section they belong to", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    const wrapper = mountCard();
    await flushPromises();
    expect(wrapper.text().match(/Daniel Jacker/g)).toHaveLength(1);
    expect(wrapper.text().match(/Steve Jurvetson/g)).toHaveLength(1);
  });

  it("offers a retry when the dossier cannot be read", async () => {
    api.getFounderDossier.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(dossier);
    const wrapper = mountCard("acme");
    await flushPromises();

    const retry = wrapper.findAll("button").find((b) => b.text().trim() === "Retry");
    expect(retry).toBeTruthy();

    await retry.trigger("click");
    await flushPromises();
    expect(api.getFounderDossier).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Daniel Jacker");
  });

  it("says so plainly when the record has nobody on it", async () => {
    api.getFounderDossier.mockResolvedValue({
      ...dossier,
      founders: [],
      advisors_and_board: [],
      team_headcount: null,
      developer_traction: null,
    });
    const wrapper = mountCard("acme");
    await flushPromises();
    expect(wrapper.text()).not.toContain("Daniel Jacker");
    expect(wrapper.text()).toContain("No people");
  });

  it("researches the team through deep-search when asked", async () => {
    api.getFounderDossier.mockResolvedValue({ ...dossier, founders: [] });
    api.deepSearchFounder.mockResolvedValue(dossier);
    const wrapper = mountCard();
    await flushPromises();
    expect(wrapper.text()).not.toContain("Daniel Jacker");

    const refresh = wrapper.find('[data-testid="founder-research"]');
    expect(refresh.exists()).toBe(true);
    await refresh.trigger("click");
    await flushPromises();

    expect(api.deepSearchFounder).toHaveBeenCalledWith("zainar-inc");
    expect(wrapper.text()).toContain("Daniel Jacker");
  });

  it("reloads when the desk switches company", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    const wrapper = mountCard();
    await flushPromises();

    await wrapper.setProps({ companyId: "globex" });
    await flushPromises();
    expect(api.getFounderDossier).toHaveBeenLastCalledWith("globex");
  });

  it("says why a refresh produced nothing instead of failing silently", async () => {
    // The server degrades rather than throwing: a failed pass returns 200
    // with `research_error` set, so the caught-exception path never fires.
    api.getFounderDossier.mockResolvedValue(dossier);
    api.deepSearchFounder.mockResolvedValue({
      ...dossier,
      engine: "gemini",
      research_error: "gemini HTTP 400 — API key not valid",
    });
    const wrapper = mount(FounderRadarCard, {
      props: { companyId: "zainar-inc", company: {} },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="founder-research-error"]').exists()).toBe(false);

    const refresh = wrapper.find('[data-testid="founder-research"]');
    await refresh.trigger("click");
    await flushPromises();

    const banner = wrapper.find('[data-testid="founder-research-error"]');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain("API key not valid");
    // A failed pass still shows the people it already had.
    expect(wrapper.text()).toContain("Daniel Jacker");
  });

  it("researches without asking to confirm — it's the cheapest, fastest Gemini tier", async () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    api.getFounderDossier.mockResolvedValue(dossier);
    api.deepSearchFounder.mockResolvedValue({ ...dossier, source: "research" });
    const wrapper = mount(FounderRadarCard, {
      props: { companyId: "zainar-inc", company: {} },
    });
    await flushPromises();
    const refresh = wrapper.find('[data-testid="founder-research"]');
    await refresh.trigger("click");
    await flushPromises();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(api.deepSearchFounder).toHaveBeenCalledWith("zainar-inc");
  });

  it("shows which engine answered and how many sources it read", async () => {
    api.getFounderDossier.mockResolvedValue({
      ...dossier,
      engine: "gemini",
      model: "gemini-3.8-flash",
      is_deep_audited: true,
      sources: [
        { title: "ZaiNar team", url: "https://zainar.example/team" },
        { title: "Crunchbase", url: "https://crunchbase.example/zainar" },
      ],
      research_error: null,
    });
    const wrapper = mount(FounderRadarCard, {
      props: { companyId: "zainar-inc", company: {} },
    });
    await flushPromises();
    const provenance = wrapper.find('[data-testid="founder-provenance"]');
    expect(provenance.text()).toContain("gemini");
    expect(provenance.text()).toContain("read 2 source(s)");
  });

  it("marks a sourceless fallback rather than implying it was audited", async () => {
    api.getFounderDossier.mockResolvedValue({
      ...dossier,
      engine: "claude",
      model: null,
      is_deep_audited: false,
      sources: [],
      research_error: null,
    });
    const wrapper = mount(FounderRadarCard, {
      props: { companyId: "zainar-inc", company: {} },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="founder-provenance"]').text()).toContain(
      "no sources reported",
    );
  });

  it("names the button for what it does: paid web research", async () => {
    api.getFounderDossier.mockResolvedValue(dossier);
    const wrapper = mountCard();
    await flushPromises();
    const button = wrapper.find('[data-testid="founder-research"]');
    expect(button.text()).toBe("Research team");
    expect(button.attributes("title")).toMatch(/Gemini/);
  });

  it("does not draw a late result over the company the desk moved to", async () => {
    // The research takes about a minute; the reader switches company meanwhile.
    let finish;
    api.deepSearchFounder.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    api.getFounderDossier.mockImplementation(async (id) =>
      id === "globex"
        ? { ...dossier, company_id: "globex", founders: [{ name: "Hank Scorpio", role: "CEO" }] }
        : { ...dossier, founders: [] },
    );
    const wrapper = mountCard();
    await flushPromises();
    await wrapper.find('[data-testid="founder-research"]').trigger("click");
    await wrapper.setProps({ companyId: "globex" });
    await flushPromises();

    // Globex is not the one being researched: its button is free.
    const button = wrapper.find('[data-testid="founder-research"]');
    expect(button.text()).toBe("Research team");
    expect(button.attributes("disabled")).toBeUndefined();

    finish(dossier); // ZaiNar's result lands
    await flushPromises();
    expect(wrapper.text()).toContain("Hank Scorpio");
    expect(wrapper.text()).not.toContain("Daniel Jacker");
  });

  it("shows the research still running when the reader comes back, then the result", async () => {
    let finish;
    api.deepSearchFounder.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    api.getFounderDossier.mockResolvedValue({ ...dossier, founders: [] });
    const wrapper = mountCard();
    await flushPromises();
    await wrapper.find('[data-testid="founder-research"]').trigger("click");

    // The card is re-rendered for this company (a tab switch and back).
    wrapper.unmount();
    const again = mountCard();
    await flushPromises();
    expect(again.find('[data-testid="founder-research"]').text()).toMatch(/Researching/);

    // The server cached the pass; the new card reads it when it finishes.
    api.getFounderDossier.mockResolvedValue(dossier);
    finish(dossier);
    await flushPromises();
    expect(again.text()).toContain("Daniel Jacker");
    expect(again.find('[data-testid="founder-research"]').text()).toBe("Research team");
  });
});
