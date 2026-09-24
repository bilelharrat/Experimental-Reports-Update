import { describe, expect, it, vi, beforeEach, onTestFinished } from "vitest";
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
import {
  ANTHROPIC_COMPLETE,
  KO_BUFFETT,
  ZAINAR_WARNINGS,
  runningReport,
  withReport,
} from "./fixtures/reportSummaries.js";

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
    listCompanyReports: vi.fn(),
    studioGenerate: vi.fn(),
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
    // A real ReportSummary (GET /api/companies/{id}/reports), moved to Acme.
    api.listCompanyReports.mockResolvedValue([
      withReport(ANTHROPIC_COMPLETE, { company_id: "acme-corp", company_name: "Acme Corp" }),
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

  it("renders directory list and selects initial company", async () => {
    const wrapper = mount(ResearchDeskView, {
      props: {
        companies: mockCompanies,
        companyId: "acme-corp",
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

    // Check directory items
    const directory = wrapper.find("aside");
    expect(directory.text()).toContain("Acme Corp");
    expect(directory.text()).toContain("Globex Corporation");
    expect(directory.text()).toContain("Initech");

    // Dossier view for selected company should be present
    expect(wrapper.findComponent(CompanyDossierView).exists()).toBe(true);
    expect(wrapper.text()).toContain("Acme Corp");
  });

  it("collapses the directory to a rail of logos, as the Reports list does", async () => {
    window.localStorage.setItem("bsh.researchDirectoryCollapsed", "1");
    onTestFinished(() => window.localStorage.removeItem("bsh.researchDirectoryCollapsed"));
    const wrapper = mount(ResearchDeskView, {
      props: { companies: mockCompanies, companyId: "acme-corp" },
      global: { plugins: [router], stubs: { Monogram: true, CompanyFollowButton: true } },
    });
    await flushPromises();

    const marks = wrapper.findAll('[data-testid="research-directory-rail"] .reports-rail-mark');
    expect(marks.map((m) => m.attributes("aria-label"))).toEqual([
      "Acme Corp",
      "Globex Corporation",
      "Initech",
    ]);
    // The open company's logo sits lifted.
    expect(marks[0].attributes("data-selected")).toBe("true");

    // Each logo opens its company's dossier.
    await marks[1].trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.params.companyId).toBe("globex");

    // And the button at the top brings the full directory back.
    await wrapper.find('[data-testid="research-directory-expand"]').trigger("click");
    expect(wrapper.find('[data-testid="research-directory-rail"]').exists()).toBe(false);
  });

  it("filters companies by search query and sector", async () => {
    const wrapper = mount(ResearchDeskView, {
      props: {
        companies: mockCompanies,
        companyId: "acme-corp",
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

    const directory = wrapper.find("aside");

    // Search for 'Globex'
    const searchInput = wrapper.find('input[type="text"]');
    await searchInput.setValue("Globex");
    await flushPromises();

    expect(directory.text()).toContain("Globex Corporation");
    expect(directory.text()).not.toContain("Initech");

    // Clear search and filter by Sector
    await searchInput.setValue("");
    const sectorSelect = wrapper.find("select");
    await sectorSelect.setValue("Fintech");
    await flushPromises();

    expect(directory.text()).toContain("Globex Corporation");
    expect(directory.text()).not.toContain("Acme Corp");
  });

  it("filters companies when Diffs toggle is active", async () => {
    const wrapper = mount(ResearchDeskView, {
      props: {
        companies: mockCompanies,
        companyId: "acme-corp",
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

    const directory = wrapper.find("aside");

    // Click 'Diffs' button
    const diffsBtn = wrapper.findAll("button").find((b) => b.text().includes("Diffs") || b.text().includes("更新"));
    expect(diffsBtn).toBeDefined();
    await diffsBtn.trigger("click");
    await flushPromises();

    // Only Acme Corp has is_modified: true
    expect(directory.text()).toContain("Acme Corp");
    expect(directory.text()).not.toContain("Globex Corporation");
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
        // A real ReportSummary: the picker reads its documents, not a title.
        reports: [withReport(ANTHROPIC_COMPLETE, { id: "rep-1", company_id: "acme-corp" })],
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

  it("offers the memos on file by type and date, newest first", async () => {
    const wrapper = mount(RecordDecisionModal, {
      props: {
        isOpen: true,
        company: mockCompanies[0],
        reports: [
          withReport(ANTHROPIC_COMPLETE, { id: "older", created_at: "2026-08-01T10:00:00Z" }),
          // complete_with_warnings is a finished memo too.
          withReport(ZAINAR_WARNINGS, { id: "newer", created_at: "2026-09-01T10:00:00Z" }),
          // A run in flight, a placeholder with no document and a dismissed
          // memo are not something a decision can rest on.
          runningReport({ id: "running" }),
          withReport(KO_BUFFETT, { id: "stub", download_urls: null, preview_urls: null }),
          withReport(KO_BUFFETT, { id: "gone", dismissed_at: "2026-09-02T00:00:00Z" }),
        ],
      },
      global: { plugins: [router] },
    });
    await flushPromises();

    const options = wrapper.findAll("select option").map((o) => [o.attributes("value"), o.text()]);
    expect(options.map(([value]) => value)).toEqual(["", "newer", "older"]);
    expect(options[1][1]).toBe("Investment Memo (Late-Stage) · 2026-09-01");
    expect(options.map(([, text]) => text).join(" ")).not.toMatch(/undefined|older|newer/);
    // The newest memo is the one picked by default.
    expect(wrapper.get("select").element.value).toBe("newer");
  });
});

// Links into a company land on a desk that may already be open: the toolbar's
// Add, Warren's citations and edits, a job's View result. The dossier follows
// its URL on every navigation, not only when it mounts.
describe("CompanyDossierView follows its URL", () => {
  const companies = [
    { id: "globex", name: "Globex Corporation", status: "Private" },
    { id: "initech", name: "Initech", ticker: "INTC", status: "Public" },
  ];
  // The cards are stubs: these tests are about which ones show and what they
  // are handed, not what they fetch.
  const stubs = {
    UnifiedProfileCard: true,
    SignalScoreCard: true,
    EarningsFilingsCard: true,
    DealPipelineCard: true,
    CompsRailCard: true,
    CapTableCard: true,
    FounderRadarCard: true,
    VCRatiosCard: true,
    DecisionsCard: true,
    ReportsMemosCard: true,
    ICPrepCard: { template: '<div data-testid="ic-prep" />' },
    ICRoomCard: true,
    NumberLintCard: true,
    ThesisTrackerCard: true,
    CompanyCommentsCard: true,
    FactLedgerCard: true,
    RecordDecisionModal: true,
    UnifiedDocumentsView: {
      props: ["companyId", "refreshKey", "focus"],
      template:
        '<div data-testid="files" :data-refresh="refreshKey" :data-focus="JSON.stringify(focus)" />',
    },
    MemoStudioEditor: {
      props: ["companyId", "focus"],
      template: '<div data-testid="memo-studio" :data-focus="JSON.stringify(focus)" />',
    },
  };

  let router;

  beforeEach(() => {
    vi.clearAllMocks();
    api.listCompanies.mockResolvedValue(companies);
    api.listCompanyReports.mockResolvedValue([]);
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/research-desk", name: "research-desk", component: ResearchDeskView, props: true },
        {
          path: "/research-desk/:companyId",
          name: "research-desk-company",
          component: ResearchDeskView,
          props: true,
        },
        { path: "/reports", name: "reports", component: { template: "<div>Reports</div>" } },
        {
          path: "/:companyId",
          name: "research",
          component: ResearchDeskView,
          alias: "/research/:companyId",
          props: true,
        },
      ],
    });
  });

  async function openDesk(path) {
    await router.push(path);
    const wrapper = mount(
      { template: "<RouterView />" },
      { global: { plugins: [router], stubs } },
    );
    await flushPromises();
    return wrapper;
  }

  async function go(path) {
    await router.push(path);
    await flushPromises();
  }

  const activeTab = (wrapper) => wrapper.find(".mac-tab.is-active").text();
  const tab = (wrapper, label) => wrapper.findAll(".mac-tab").find((b) => b.text() === label);
  const focusOf = (wrapper, testId) =>
    JSON.parse(wrapper.find(`[data-testid="${testId}"]`).attributes("data-focus"));
  const url = () => router.currentRoute.value.fullPath;

  it("opens the section an old ?tab= names and rewrites the URL to ?section=", async () => {
    // A Memo Studio job's View result, as the jobs rail sent it before.
    const wrapper = await openDesk("/research/globex?tab=analysis");

    expect(activeTab(wrapper)).toBe("Decisions");
    expect(wrapper.find('[data-testid="ic-prep"]').exists()).toBe(true);
    // By path, so the /research/ alias keeps its URL.
    expect(url()).toBe("/research/globex?section=decisions");
  });

  it("moves an open desk to the tab a new link names and reloads Files for an upload", async () => {
    const wrapper = await openDesk("/globex");
    expect(activeTab(wrapper)).toBe("Overview");

    await go("/globex?section=files");
    expect(activeTab(wrapper)).toBe("Files");
    expect(wrapper.find('[data-testid="files"]').attributes("data-refresh")).toBe("0");

    // The toolbar's Add, finished while Files is already on screen.
    await go("/globex?section=files&files=1700000000000");
    expect(wrapper.find('[data-testid="files"]').attributes("data-refresh")).toBe("1");
    // Read once: a reload does not replay the stamp.
    expect(url()).toBe("/globex?section=files");
  });

  it("writes the tab it shows to the URL, so Back returns to the tab before", async () => {
    const wrapper = await openDesk("/globex");

    await tab(wrapper, "Files").trigger("click");
    await flushPromises();
    expect(url()).toBe("/globex?section=files");

    await go("/globex?section=decisions");
    expect(activeTab(wrapper)).toBe("Decisions");

    router.back();
    await flushPromises();
    expect(url()).toBe("/globex?section=files");
    expect(activeTab(wrapper)).toBe("Files");

    await tab(wrapper, "Overview").trigger("click");
    await flushPromises();
    expect(url()).toBe("/globex");
  });

  it("hands a cited file and an edited memo point to the cards that show them", async () => {
    const wrapper = await openDesk("/globex");

    await go("/globex?section=files&previewFile=f-1&previewPage=4");
    expect(activeTab(wrapper)).toBe("Files");
    expect(focusOf(wrapper, "files")).toMatchObject({ id: "f-1", page: "4", action: "preview" });
    expect(url()).toBe("/globex?section=files");

    // A deck summary job's View result names its deck.
    await go("/globex?section=files&file=deck-1");
    expect(focusOf(wrapper, "files")).toMatchObject({ id: "deck-1", action: "summary" });

    await go("/globex?section=memos&memoSection=risks_mitigations&memoBullet=b-2");
    expect(activeTab(wrapper)).toBe("Memo Studio");
    expect(focusOf(wrapper, "memo-studio")).toMatchObject({
      section: "risks_mitigations",
      bullet: "b-2",
    });
    expect(url()).toBe("/globex?section=memos");

    // Choosing a tab drops an ask the analyst has moved on from.
    await tab(wrapper, "Files").trigger("click");
    await flushPromises();
    expect(focusOf(wrapper, "files")).toBeNull();
  });

  it("reloads the memo list when a new run arrives with ?report=", async () => {
    const wrapper = await openDesk("/globex?section=memos");
    expect(api.listCompanyReports).toHaveBeenCalledTimes(1);
    expect(api.listCompanyReports).toHaveBeenCalledWith("globex");

    api.listCompanyReports.mockResolvedValue([
      runningReport({ id: "rep-2", company_id: "globex", company_name: "Globex Corporation" }),
    ]);
    await go("/globex?section=memos&report=rep-2");

    expect(api.listCompanyReports).toHaveBeenCalledTimes(2);
    // The run shows under Active Analysis Pipelines by its type and stage,
    // not by its id.
    expect(wrapper.text()).toContain("Investment Memo (Late-Stage)");
    expect(wrapper.text()).toContain("Phase 2 - Parallel analysis passes");
    expect(wrapper.text()).not.toContain("rep-2");
    expect(url()).toBe("/globex?section=memos");
  });

  it("keeps the tab when the directory picks another company, as the Mac does", async () => {
    const wrapper = await openDesk("/research-desk/globex?section=files");

    const initech = wrapper.findAll("button.mac-row").find((b) => b.text().includes("Initech"));
    await initech.trigger("click");
    await flushPromises();

    expect(activeTab(wrapper)).toBe("Files");
    expect(url()).toBe("/research-desk/initech?section=files");
  });

  it("never writes its tab into another page's URL", async () => {
    // The view transition keeps a desk mounted a moment after it is left.
    await router.push("/reports");
    const wrapper = mount(CompanyDossierView, {
      props: { companyId: "globex", company: companies[0] },
      global: { plugins: [router], stubs },
    });
    await flushPromises();

    await tab(wrapper, "Files").trigger("click");
    await flushPromises();

    expect(activeTab(wrapper)).toBe("Files");
    expect(url()).toBe("/reports");
  });
});
