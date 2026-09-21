import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import ResearchDeskView from "../src/views/ResearchDeskView.vue";
import CompanyDossierView from "../src/components/research/CompanyDossierView.vue";
import UnifiedProfileCard from "../src/components/research/UnifiedProfileCard.vue";
import DealPipelineCard from "../src/components/research/DealPipelineCard.vue";
import EarningsFilingsCard from "../src/components/research/EarningsFilingsCard.vue";
import CapTableCard from "../src/components/research/CapTableCard.vue";
import VCRatiosCard from "../src/components/research/VCRatiosCard.vue";
import RecordDecisionModal from "../src/components/research/RecordDecisionModal.vue";
import api from "../src/api.js";

vi.mock("../src/api.js", () => {
  const mock = {
    listCompanies: vi.fn(),
    getCompanyProfile: vi.fn(),
    getDealPipeline: vi.fn(),
    getCompanyEarningsFilings: vi.fn(),
    updateDealPipeline: vi.fn(),
    getCompanyComps: vi.fn(),
    getFounderDossier: vi.fn(),
    deepSearchFounder: vi.fn(),
    getMemoNumberLint: vi.fn(),
    getReports: vi.fn(),
    decisionRecords: {
      list: vi.fn(),
      add: vi.fn(),
      remove: vi.fn(),
    },
  };
  return {
    default: mock,
    api: mock,
  };
});

describe("ResearchDeskView", () => {
  const mockCompanies = [
    {
      id: "acme-corp",
      name: "Acme Corp",
      ticker: "ACME",
      sector: "Enterprise Software",
      status: "Public",
      market_cap: 12500000000,
      deal_stage: "Technical Diligence",
      is_modified: true,
    },
    {
      id: "globex",
      name: "Globex Corporation",
      ticker: "GBX",
      sector: "Fintech",
      status: "Private",
      valuation: 450000000,
      deal_stage: "Partner Intro",
      is_modified: false,
    },
    {
      id: "initech",
      name: "Initech",
      ticker: "INTC",
      sector: "Enterprise Software",
      status: "Public",
      deal_stage: "Sourced",
      is_modified: false,
    },
  ];

  let router;

  beforeEach(() => {
    vi.clearAllMocks();
    api.listCompanies.mockResolvedValue({ companies: mockCompanies });
    api.getCompanyProfile.mockResolvedValue({
      public_facts: { price: 152.4, ticker: "ACME", market_cap: 12500000000 },
      private_facts: { arr: 45000000, runway: 18, mark: 12500000000 },
      process_facts: { stage: "Technical Diligence", latest_decision: "Invest" },
    });
    api.getDealPipeline.mockResolvedValue({
      stage: "Technical Diligence",
      warmth_score: 85,
      deal_lead: "Sarah",
    });
    api.updateDealPipeline.mockResolvedValue({
      stage: "Term Sheet / IC",
      warmth_score: 90,
    });
    api.getReports.mockResolvedValue([
      { id: "rep-1", title: "Q3 Investment Memo", status: "complete" },
    ]);
    api.decisionRecords.list.mockResolvedValue([
      { id: "dec-1", type: "invest", rationale: "Strong moat", created_at: "2026-03-01" },
    ]);
    api.getMemoNumberLint.mockResolvedValue({ warnings: [] });
    api.getCompanyComps.mockResolvedValue({ peers: [] });
    api.getFounderDossier.mockResolvedValue({ founders: [] });
    api.getCompanyEarningsFilings.mockResolvedValue({ ticker: "ACME", earnings: null, filings: [] });

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/research-desk", name: "research-desk", component: ResearchDeskView },
        { path: "/research-desk/:companyId", name: "research-desk-company", component: ResearchDeskView },
        { path: "/reports", name: "reports", component: { template: "<div>Reports</div>" } },
        { path: "/:companyId", name: "research", component: { template: "<div>Research</div>" } },
      ],
    });
  });

  it("switches dossier tabs cleanly", async () => {
    const wrapper = mount(CompanyDossierView, {
      props: {
        companyId: "acme-corp",
        company: mockCompanies[0],
      },
      global: {
        plugins: [router],
        stubs: {
          Monogram: true,
          CompanyFollowButton: true,
        },
      },
    });

    await flushPromises();

    // In Overview tab by default. Acme is listed, so its Overview leads
    // with earnings and filings rather than a VC deal pipeline.
    expect(wrapper.findComponent(UnifiedProfileCard).exists()).toBe(true);
    expect(wrapper.findComponent(EarningsFilingsCard).exists()).toBe(true);
    expect(wrapper.findComponent(DealPipelineCard).exists()).toBe(false);

    // Switch to Cap table tab
    const capTabBtn = wrapper.findAll("button").find((b) => b.text().toLowerCase().includes("cap table") || b.text().includes("股权结构"));
    expect(capTabBtn).toBeDefined();
    await capTabBtn.trigger("click");
    await flushPromises();

    expect(wrapper.findComponent(CapTableCard).exists()).toBe(true);
    expect(wrapper.findComponent(UnifiedProfileCard).exists()).toBe(false);

    // Switch to Ratios tab
    const ratiosTabBtn = wrapper.findAll("button").find((b) => b.text().toLowerCase().includes("ratios") || b.text().includes("指标比率"));
    expect(ratiosTabBtn).toBeDefined();
    await ratiosTabBtn.trigger("click");
    await flushPromises();

    expect(wrapper.findComponent(VCRatiosCard).exists()).toBe(true);
  });

  it("keeps the deal pipeline on a private company's Overview", async () => {
    const wrapper = mount(CompanyDossierView, {
      props: { companyId: "globex", company: mockCompanies[1] },
      global: { plugins: [router], stubs: { Monogram: true, CompanyFollowButton: true } },
    });
    await flushPromises();
    expect(wrapper.findComponent(DealPipelineCard).exists()).toBe(true);
    expect(wrapper.findComponent(EarningsFilingsCard).exists()).toBe(false);
  });

  it("still offers a listed company's pipeline on the Pipeline tab", async () => {
    const wrapper = mount(CompanyDossierView, {
      props: { companyId: "acme-corp", company: mockCompanies[0] },
      global: { plugins: [router], stubs: { Monogram: true, CompanyFollowButton: true } },
    });
    await flushPromises();
    const pipelineTab = wrapper
      .findAll("button")
      .find((b) => b.text().trim().toLowerCase() === "pipeline" || b.text().includes("管线"));
    expect(pipelineTab).toBeDefined();
    await pipelineTab.trigger("click");
    await flushPromises();
    expect(wrapper.findComponent(DealPipelineCard).exists()).toBe(true);
  });

  it("records a decision through the \u2318D sheet", async () => {
    api.decisionRecords.add.mockResolvedValue({ id: "dec-2", verdict: "watch" });

    const wrapper = mount(RecordDecisionModal, {
      props: {
        isOpen: true,
        company: mockCompanies[0],
        reports: [{ id: "rep-1", title: "Q3 Investment Memo", status: "complete" }],
      },
      global: {
        plugins: [router],
      },
    });

    await flushPromises();

    // Enter the rationale and submit "Record Watch"
    const textarea = wrapper.find("textarea");
    await textarea.setValue("Super strong retention and product velocity.");
    const saveBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Record Watch") || b.text().includes("记录观察"));
    expect(saveBtn).toBeDefined();
    await saveBtn.trigger("click");
    await flushPromises();

    expect(api.decisionRecords.add).toHaveBeenCalledWith(
      "acme-corp",
      expect.objectContaining({
        verdict: "watch",
        explanation: "Super strong retention and product velocity.",
        report_id: "rep-1",
      }),
    );
    const payload = api.decisionRecords.add.mock.calls[0][1];
    expect(payload.decided_at).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00Z$/);
    expect(wrapper.emitted("saved")).toBeTruthy();
  });
});
