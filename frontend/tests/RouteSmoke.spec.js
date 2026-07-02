import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import StockResearchView from "../src/views/StockResearchView.vue";
import ResearchView from "../src/views/ResearchView.vue";
import InnovationLabView from "../src/views/InnovationLabView.vue";
import SettingsView from "../src/views/SettingsView.vue";
import UserCenterView from "../src/views/UserCenterView.vue";
import SourceLibraryView from "../src/views/SourceLibraryView.vue";
import { api } from "../src/api.js";

vi.mock("../src/api.js", () => ({
  withApiToken: (path) => path,
  api: {
    stockResearch: {
      dashboard: vi.fn(),
      runSelectedTrackers: vi.fn(),
      runDueTrackers: vi.fn(),
      runTracker: vi.fn(),
      runAggregate: vi.fn(),
      runStrategyMap: vi.fn(),
      addLinkSource: vi.fn(),
      addNoteSource: vi.fn(),
      uploadSource: vi.fn(),
      updateReviewItem: vi.fn(),
      updateWorkProduct: vi.fn(),
      updateRunReview: vi.fn(),
      disableTracker: vi.fn(),
      importCompanyTrackers: vi.fn(),
      cancelRun: vi.fn(),
      retryRun: vi.fn(),
      cancelAggregate: vi.fn(),
      retryAggregate: vi.fn(),
      cancelStrategyMap: vi.fn(),
      retryStrategyMap: vi.fn(),
      reviewKnowledgeUpdate: vi.fn(),
    },
    getCompany: vi.fn(),
    options: vi.fn(),
    listThreads: vi.fn(),
    listFiles: vi.fn(),
    uploadFile: vi.fn(),
    deleteFile: vi.fn(),
    fileUrl: vi.fn((companyId, fileId) => `/api/companies/${companyId}/files/${fileId}`),
    listResearchFiles: vi.fn(),
    listCompanyReports: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    resumeReport: vi.fn(),
    addThread: vi.fn(),
    memoAnalysis: {
      get: vi.fn(),
      getEvidenceMatrix: vi.fn(),
      runLedger: vi.fn(),
      runTool: vi.fn(),
      cancelTask: vi.fn(),
      runSelectedTasks: vi.fn(),
      patchArtifact: vi.fn(),
      patchTask: vi.fn(),
      approve: vi.fn(),
      streamUrl: vi.fn(() => "/stream"),
    },
  },
}));

function stockPayload() {
  return {
    summary: {
      tracker_count: 1,
      tracker_counts_by_type: { macro: 1, industry: 0, company: 0 },
      due_count: 0,
      stale_count: 0,
      open_review_item_count: 0,
      missing_source_warning_count: 0,
      work_product_count: 0,
      source_count: 0,
      doctor_error_count: 0,
      doctor_warning_count: 0,
      run_ledger_count: 1,
    },
    trackers: [
      {
        id: "us-macro",
        type: "macro",
        display_name: "US Macro Tracker",
        status: "active",
        freshness_policy: {},
      },
    ],
    sources: [],
    runs: [],
    latest_aggregate: null,
    latest_strategy_map: null,
    work_products: [],
    review_items: [],
    evaluation: { runs: [], run_ledger: [] },
    doctor: { status: "ok", summary: { error_count: 0, warning_count: 0 }, issues: [] },
  };
}

function memoSession() {
  return {
    id: "session-1",
    company_id: "generalist",
    approved_for_memo: false,
    has_unapproved_work: true,
    completed_memo_runs: [],
    tools: [],
    readiness: {
      score: 0,
      total: 1,
      pct: 0,
      gates: [],
      approval_blockers: [],
      ready_for_approval: false,
      ready_for_memo: false,
    },
    additional_areas: [],
    artifacts: {
      input_manifest: { research_files: [] },
      strategic_risks: { risks: [] },
      research_tasks: { tasks: [] },
      thesis_spine: { approved: false },
    },
  };
}

async function mountRouteWithRouter(path) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/stock-research", name: "stock-research", component: StockResearchView },
      { path: "/innovation-lab", name: "innovation-lab", component: InnovationLabView },
      { path: "/settings", name: "settings", component: SettingsView },
      { path: "/user", name: "user-center", component: UserCenterView },
      { path: "/source-library", name: "source-library", component: SourceLibraryView },
      { path: "/innovation-lab/hormuz", name: "hormuz-library", component: { template: "<div />" } },
      { path: "/innovation-lab/market-pulse", name: "research-page-market-pulse", component: { template: "<div />" } },
      { path: "/innovation-lab/evidence-matrix", name: "research-page-evidence-matrix", component: { template: "<div />" } },
      { path: "/innovation-lab/hypothesis-lab", name: "research-page-hypothesis-lab", component: { template: "<div />" } },
      {
        path: "/:companyId",
        name: "research",
        component: ResearchView,
        alias: "/research/:companyId",
        props: true,
      },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount({ components: { RouterView }, template: "<RouterView />" }, {
    global: { plugins: [router] },
  });
  await flushPromises();
  return { wrapper, router };
}

async function mountRoute(path) {
  const { wrapper } = await mountRouteWithRouter(path);
  return wrapper;
}

describe("route smoke tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.stockResearch.dashboard.mockResolvedValue(stockPayload());
    api.getCompany.mockResolvedValue({
      id: "generalist",
      name: "Generalist",
      files: [],
      report_type: "Investment Memo (Late-Stage)",
    });
    api.options.mockResolvedValue({
      report_types: ["Investment Memo (Late-Stage)"],
      audiences: ["Internal"],
      languages: ["en"],
    });
    api.listThreads.mockResolvedValue([]);
    api.listFiles.mockResolvedValue([]);
    api.listResearchFiles.mockResolvedValue([]);
    api.listCompanyReports.mockResolvedValue([]);
    api.memoAnalysis.get.mockResolvedValue(memoSession());
    api.memoAnalysis.getEvidenceMatrix.mockResolvedValue({ claim_count: 0, claims: [] });
    api.memoAnalysis.runLedger.mockResolvedValue([]);
  });

  it("renders the Stock Research route shell", async () => {
    const wrapper = await mountRoute("/stock-research");

    expect(wrapper.text()).toContain("Stock Research");
    expect(wrapper.text()).toContain("Latest Weekly Aggregate");
    expect(wrapper.text()).toContain("Data Doctor");
  });

  it("renders the Memo Tools analysis route shell", async () => {
    const wrapper = await mountRoute("/research/generalist?tab=analysis");

    expect(wrapper.text()).toContain("Generalist");
    expect(wrapper.text()).toContain("Overview");
    expect(wrapper.text()).toContain("Documents");
    expect(wrapper.text()).toContain("Memo Studio");
    expect(wrapper.text()).toContain("Company News");
    expect(wrapper.text()).toContain("Industry Views");
    expect(wrapper.text()).toContain("Core Memo Workflow");
    expect(wrapper.text()).toContain("Evidence, Ledger, And Source Boundaries");
  });

  it("renders company pages at the production base-relative URL", async () => {
    const wrapper = await mountRoute("/generalist?tab=analysis");

    expect(wrapper.text()).toContain("Generalist");
    expect(wrapper.text()).toContain("Core Memo Workflow");
  });

  it("renders new PRD foundation top-level routes", async () => {
    let wrapper = await mountRoute("/innovation-lab");
    expect(wrapper.text()).toContain("Innovation Lab");
    expect(wrapper.text()).toContain("Hormuz Source Library");
    wrapper.unmount();

    wrapper = await mountRoute("/settings");
    expect(wrapper.text()).toContain("Settings");
    expect(wrapper.text()).toContain("System Status");
    wrapper.unmount();

    wrapper = await mountRoute("/user");
    expect(wrapper.text()).toContain("User Center");
    wrapper.unmount();

    wrapper = await mountRoute("/source-library");
    expect(wrapper.text()).toContain("Source Library & Appendix");
    expect(wrapper.text()).toContain("intentionally separate");
    wrapper.unmount();
  });

  it("shows partial memo analysis artifacts for failed reports", async () => {
    api.getReport.mockResolvedValue({
      id: "report-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "failed_during_analysis",
      progress: 15,
      stage: "Claude skill run failed",
      failure_phase: "analysis",
      failure_detail: "Failed to authenticate. API Error: 403 Request not allowed",
      run_dir: "data/memos/generalist/run",
      resume_available: true,
      analysis_artifacts: [
        {
          label: "Arithmetic / pressure tests",
          filename: "pressure_tests.md",
          download_url:
            "/api/reports/report-1/download?artifact=analysis&file=pressure_tests.md",
        },
      ],
    });

    const wrapper = await mountRoute("/research/generalist?report=report-1");

    expect(wrapper.text()).toContain("Partial analysis artifacts");
    expect(wrapper.text()).toContain("Arithmetic / pressure tests");
    expect(wrapper.findAll("a").map((a) => a.attributes("href"))).toContain(
      "/api/reports/report-1/download?artifact=analysis&file=pressure_tests.md",
    );
    expect(wrapper.text()).toContain("Redo from scratch");
    api.resumeReport.mockResolvedValue({
      id: "report-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "analyzing",
      progress: 65,
      stage: "Resume queued",
      resume_available: false,
    });

    const resumeButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Resume memo run"));
    expect(resumeButton).toBeTruthy();
    await resumeButton.trigger("click");
    await flushPromises();
    expect(api.resumeReport).toHaveBeenCalledWith("report-1");
    wrapper.unmount();
  });

  it("surfaces the latest resumable memo when no report is selected", async () => {
    api.listCompanyReports.mockResolvedValue([
      {
        id: "report-1",
        company_id: "generalist",
        company_name: "Generalist",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Internal",
        language: "en",
        kind: "investment_memo_latestage",
        status: "failed_during_analysis",
        progress: 15,
        stage: "Memo resume failed",
        resume_available: true,
        created_at: "2026-06-23T09:04:06Z",
        updated_at: "2026-06-23T10:16:28Z",
      },
    ]);
    api.getReport.mockResolvedValue({
      id: "report-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "failed_during_analysis",
      progress: 15,
      stage: "Memo resume failed",
      failure_phase: "resume",
      failure_detail: "claude exited 143",
      run_dir: "data/memos/generalist/run",
      resume_available: true,
      analysis_artifacts: [
        {
          label: "Claim register",
          filename: "claim_register.md",
          download_url:
            "/api/reports/report-1/download?artifact=analysis&file=claim_register.md",
        },
      ],
    });

    const wrapper = await mountRoute("/research/generalist?tab=analysis");

    expect(api.listCompanyReports).toHaveBeenCalledWith("generalist");
    expect(api.getReport).toHaveBeenCalledWith("report-1");
    expect(wrapper.text()).toContain("Resume memo run");
    expect(wrapper.text()).toContain("Redo from scratch");
    wrapper.unmount();
  });

  it("shows gate diagnostics and preserved artifacts for failed quality gates", async () => {
    api.getReport.mockResolvedValue({
      id: "report-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "failed_quality_gate",
      progress: 98,
      stage: "Memo failed quality gate",
      failure_phase: "quality_gate",
      failure_detail: "Generated memo failed the DOCX quality gate with 1 P0 finding.",
      run_dir: "data/memos/generalist/run",
      artifacts_available: true,
      resume_available: false,
      download_urls: {
        en: "/api/reports/report-1/download?language=en",
      },
      memo_quality_lint: {
        status: "failed",
        finding_count: 1,
        p0_count: 1,
        findings: [
          {
            severity: "P0",
            code: "sell_side_voice_violation",
            location: "paragraph 1",
            snippet: "The recommendation is Proceed if confirmed",
            suggestion: "Use first-person sell-side memo language.",
          },
        ],
      },
    });

    const wrapper = await mountRoute("/research/generalist?report=report-1");
    const hrefs = wrapper.findAll("a").map((a) => a.attributes("href"));

    expect(wrapper.text()).toContain("Draft memo artifacts remain visible for debugging");
    expect(wrapper.text()).toContain("Gate diagnostics");
    expect(wrapper.text()).toContain("sell_side_voice_violation");
    expect(wrapper.text()).toContain("The recommendation is Proceed if confirmed");
    expect(hrefs).toContain("/api/reports/report-1/download?language=en");
    wrapper.unmount();
  });

  it("shows generated memo download links in the documents library", async () => {
    api.listCompanyReports.mockResolvedValue([
      {
        id: "report-1",
        company_id: "generalist",
        company_name: "Generalist",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Internal",
        language: "en",
        kind: "investment_memo_latestage",
        status: "failed_quality_gate",
        progress: 98,
        stage: "Memo failed quality gate",
        created_at: "2026-06-23T11:14:02Z",
        updated_at: "2026-06-23T11:14:02Z",
        download_urls: {
          en: "/api/reports/report-1/download?language=en",
          zh: "/api/reports/report-1/download?language=zh",
        },
      },
    ]);

    const wrapper = await mountRoute("/research/generalist?tab=documents");
    const hrefs = wrapper.findAll("a").map((a) => a.attributes("href"));

    expect(wrapper.text()).toContain("Generated reports");
    expect(wrapper.text()).toContain("EN");
    expect(wrapper.text()).toContain("ZH");
    expect(hrefs).toContain("/api/reports/report-1/download?language=en");
    expect(hrefs).toContain("/api/reports/report-1/download?language=zh");
    wrapper.unmount();
  });

  it("lets resumable failed reports be redone from scratch", async () => {
    api.getReport.mockResolvedValue({
      id: "report-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "failed_during_analysis",
      progress: 15,
      stage: "Claude skill run failed",
      failure_phase: "analysis",
      failure_detail: "Failed to authenticate. API Error: 403 Request not allowed",
      run_dir: "data/memos/generalist/run",
      resume_available: true,
      analysis_artifacts: [],
    });
    api.generateReport.mockResolvedValue({
      id: "report-2",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "analyzing",
      progress: 15,
      stage: "Running BSH investment memo skill",
    });

    const wrapper = await mountRoute("/research/generalist?report=report-1");
    const redoButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Redo from scratch"));

    expect(redoButton).toBeTruthy();
    await redoButton.trigger("click");
    await flushPromises();

    expect(api.resumeReport).not.toHaveBeenCalled();
    expect(api.generateReport).toHaveBeenCalledWith({
      company_id: "generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      analysis_session_id: null,
    });
    wrapper.unmount();
  });

  it("shows generate request failures while the company page remains loaded", async () => {
    const err = Object.assign(
      new Error('400 Bad Request: {"detail":"Settings file missing"}'),
      { status: 400 },
    );
    api.generateReport.mockRejectedValue(err);

    const wrapper = await mountRoute("/research/generalist");
    const memoTab = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Memo Studio"));
    expect(memoTab).toBeTruthy();
    await memoTab.trigger("click");
    await flushPromises();

    const generateButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Generate report"));

    expect(generateButton).toBeTruthy();
    await generateButton.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Memo generation request failed");
    expect(wrapper.text()).toContain("Settings file missing");
    expect(wrapper.text()).toContain("HTTP 400");
    wrapper.unmount();
  });

  it("hides Memo Studio for companies remembered as public tickers", async () => {
    api.getCompany.mockResolvedValue({
      id: "public-ticker",
      name: "Public Ticker Co",
      ticker: "PTCO",
      company_type: "public",
      status: "public",
      files: [],
    });

    const { wrapper, router } = await mountRouteWithRouter("/research/public-ticker?tab=analysis");
    await flushPromises();

    expect(wrapper.text()).toContain("Public Ticker Co");
    expect(wrapper.text()).not.toContain("Memo Studio");
    expect(wrapper.text()).not.toContain("Core Memo Workflow");
    expect(api.memoAnalysis.get).not.toHaveBeenCalled();
    expect(router.currentRoute.value.query.tab).toBeUndefined();
  });

  it("does not classify private companies from ticker text in the route", async () => {
    api.getCompany.mockResolvedValue({
      id: "private-with-ticker",
      name: "Private Ticker Co",
      ticker: "PTCO",
      company_type: "private",
      status: "private",
      files: [],
    });

    const wrapper = await mountRoute("/research/private-with-ticker?tab=analysis");
    await flushPromises();

    expect(wrapper.text()).toContain("Private Ticker Co");
    expect(wrapper.text()).toContain("Memo Studio");
    expect(wrapper.text()).toContain("Core Memo Workflow");
    expect(api.memoAnalysis.get).toHaveBeenCalledWith("private-with-ticker");
  });
});
