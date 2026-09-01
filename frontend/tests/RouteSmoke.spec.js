import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import StockResearchView from "../src/views/StockResearchView.vue";
import ResearchView from "../src/views/ResearchView.vue";
import InnovationLabView from "../src/views/InnovationLabView.vue";
import SettingsView from "../src/views/SettingsView.vue";
import SourceLibraryView from "../src/views/SourceLibraryView.vue";
import CompetitorDetailView from "../src/views/CompetitorDetailView.vue";
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
    getCompanyNewsFeed: vi.fn(),
    getCompanyIndustryView: vi.fn(),
    getCompetitorDetail: vi.fn(),
    workspaceSettings: vi.fn(),
    updateWorkspaceSettings: vi.fn(),
    regenAllCompanies: vi.fn(),
    trader: { refreshAll: vi.fn() },
    userCenter: vi.fn(),
    analyticsSummary: vi.fn(),
    options: vi.fn(),
    listThreads: vi.fn(),
    listFiles: vi.fn(),
    listCompanyDocuments: vi.fn(),
    updateDocumentMetadata: vi.fn(),
    setDocumentUseInReport: vi.fn(),
    uploadFile: vi.fn(),
    deleteFile: vi.fn(),
    fileUrl: vi.fn((companyId, fileId) => `/api/companies/${companyId}/files/${fileId}`),
    researchFileUrl: vi.fn((companyId, fileId) => `/api/companies/${companyId}/research-files/${fileId}`),
    uploadResearchFile: vi.fn(),
    deleteResearchFile: vi.fn(),
    generateResearchFileSummary: vi.fn(),
    listResearchFiles: vi.fn(),
    listCompanyReports: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    studioInvestigate: vi.fn(),
    studioGenerate: vi.fn(),
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
      refineRisk: vi.fn(),
      approve: vi.fn(),
      streamUrl: vi.fn(() => "/stream"),
    },
    memoEditor: {
      get: vi.fn(),
      patchCard: vi.fn(),
      moveCard: vi.fn(),
      patchBullet: vi.fn(),
      diveDeeper: vi.fn(),
      selectConclusion: vi.fn(),
      rerunSection: vi.fn(),
      patchAppendixBlock: vi.fn(),
      exportProjection: vi.fn(),
      history: vi.fn(),
      createTask: vi.fn(),
      updateTask: vi.fn(),
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
      { path: "/trader-stats", name: "trader-stats", component: { template: "<div>Stats</div>" } },
      { path: "/innovation-lab", name: "innovation-lab", component: InnovationLabView },
      { path: "/settings", name: "settings", component: SettingsView },
      { path: "/user", name: "user-center", redirect: { name: "settings" } },
      { path: "/source-library", name: "source-library", component: SourceLibraryView },
      { path: "/companies/:companyId/competitors/:competitorId", name: "competitor-detail", component: CompetitorDetailView, props: true },
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
      company_type: "private",
    });
    api.getCompanyNewsFeed.mockResolvedValue({
      rows: [
        {
          id: "news-1",
          title: "Generalist source update",
          summary: "Source-backed update.",
          published_at: "2026-07-03",
          category: "press",
          source_class: "third-party market data",
          tags: ["press"],
        },
      ],
      filters: { categories: ["press"], tags: ["press"] },
      empty_state: "",
    });
    api.getCompanyIndustryView.mockResolvedValue({
      title: "Generalist sector context",
      summary: "Sector context.",
      metrics: [{ label: "Sector TAM", value: "$45B", source_class: "third-party market data" }],
      expert_opinions: [],
      public_comps: [
        {
          id: "nextnav",
          name: "NextNav",
          ticker: "NN",
          exchange: "NASDAQ",
          change: "+2.4%",
          note: "Public comp.",
          sparkline: [1, 2, 3],
          source_class: "public filing",
        },
      ],
      sector_signals: [{ id: "signal-1", category: "demand", signal: "Demand signal", implication: "Supports thesis." }],
    });
    api.getCompetitorDetail.mockResolvedValue({
      company: { id: "generalist", name: "Generalist", category: "AI" },
      competitor: {
        id: "nextnav",
        name: "NextNav",
        status: "Public",
        ticker: "NN",
        exchange: "NASDAQ",
        category: "Terrestrial PNT",
        description: "Public comp.",
        metrics: [{ label: "Market cap", value: "Public market", source_class: "public filing" }],
        source_refs: [{ title: "Public comp set", source_class: "public filing" }],
      },
      head_to_head: [{ label: "Positioning", company: "Company", competitor: "Competitor" }],
      placeholders: [{ id: "benchmark", title: "Benchmark", status: "placeholder adapter", body: "Pending." }],
    });
    api.workspaceSettings.mockResolvedValue({
      account: {
        email: "shared-token session",
        role: "admin",
        plan: "Enterprise workspace adapter",
        permissions: ["admin:read", "settings:update"],
      },
      preferences: {
        weekly_summary: true,
        stock_auto_refresh: true,
        agent_alerts: true,
        compact_density: false,
        language: "en",
      },
      adapter_scope: "local workspace preferences adapter",
    });
    api.updateWorkspaceSettings.mockImplementation((patch) =>
      Promise.resolve({
        account: {
          email: "shared-token session",
          role: "admin",
          plan: "Enterprise workspace adapter",
          permissions: ["admin:read", "settings:update"],
        },
        preferences: {
          weekly_summary: true,
          stock_auto_refresh: true,
          agent_alerts: true,
          compact_density: Boolean(patch.compact_density),
          language: patch.language || "en",
        },
        adapter_scope: "local workspace preferences adapter",
      }),
    );
    api.userCenter.mockResolvedValue({
      account: {
        name: "Shared Workspace",
        email: "shared-token session",
        workspace: "Berkeley Summit House Research Center",
        role: "admin",
        plan: "Enterprise workspace adapter",
        permissions: ["admin:read"],
      },
      team: { licensed_seats: 1, active_users: 1, members: [] },
      status: { research_engine: "ready", memo_generation: "ready", document_index: "ready" },
      usage: { analytics_events: 2, company_count: 1, report_count: 0 },
      analytics: {
        copilot_task_acceptance: { acceptance_rate: 1 },
        source_coverage: { coverage: 1 },
        time_to_first_memo: { median_minutes: null },
      },
    });
    api.options.mockResolvedValue({
      report_types: [
        "Investment Report (Auto)",
        "Investment Memo (Late-Stage)",
      ],
      audiences: ["Internal"],
      languages: ["en"],
    });
    api.listThreads.mockResolvedValue([]);
    api.listFiles.mockResolvedValue([]);
    api.listCompanyDocuments.mockResolvedValue({
      rows: [],
      groups: [],
      categories: [],
      source_classes: [],
      filters: { languages: [], statuses: [] },
      unresolved_intake_count: 0,
    });
    api.listResearchFiles.mockResolvedValue([]);
    api.listCompanyReports.mockResolvedValue([]);
    api.memoAnalysis.get.mockResolvedValue(memoSession());
    api.memoAnalysis.runTool.mockResolvedValue(memoSession());
    api.memoAnalysis.getEvidenceMatrix.mockResolvedValue({ claim_count: 0, claims: [] });
    api.memoAnalysis.runLedger.mockResolvedValue([]);
    api.memoEditor.get.mockResolvedValue({
      company_id: "generalist",
      company_name: "Generalist",
      version_id: "v1",
      status: "draft",
      sections: {
        executive_summary: {
          title: "Executive Summary",
          status: "ready_for_input",
          body: "Summary",
          recommendation: "Conditional",
          round: "Pending",
          top_gate: "Validate sources",
          source_class: "BSH primary diligence",
        },
        investment_thesis: { title: "Investment Thesis", status: "ready_for_input", cards: [] },
        risks_mitigations: { title: "Risks and Mitigations", status: "ready_for_input", cards: [] },
        conclusion: {
          title: "Conclusion",
          status: "ready_for_input",
          selected_option_id: "conditional",
          options: [],
        },
        appendix: { title: "Appendix", status: "ready_for_input", blocks: [] },
      },
    });
    api.memoEditor.history.mockResolvedValue({
      versions: [],
      audit_records: [],
      memo_tasks: [],
    });
    api.memoEditor.createTask.mockResolvedValue({ id: "task-1", status: "proposed" });
    api.memoEditor.updateTask.mockResolvedValue({ id: "task-1", status: "accepted" });
  });

  it("renders the Stock Research route shell", async () => {
    const wrapper = await mountRoute("/stock-research");

    expect(wrapper.text()).toContain("Stock Research");
    expect(wrapper.text()).toContain("Latest Weekly Aggregate");
    expect(wrapper.text()).toContain("Data health");
  });

  it("renders the Memo Tools analysis route shell", async () => {
    api.listCompanyReports.mockResolvedValue([
      {
        id: "memo-1",
        kind: "investment_memo_latestage",
        status: "complete",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Internal",
        language: "en",
        updated_at: "2026-08-01T00:00:00Z",
        resume_available: false,
      },
    ]);
    const wrapper = await mountRoute("/research/generalist?tab=analysis");

    expect(wrapper.text()).toContain("Generalist");
    expect(wrapper.text()).toContain("Overview");
    expect(wrapper.text()).toContain("Files");
    expect(wrapper.text()).toContain("Report");
    const topTabs = wrapper
      .findAll('[role="tablist"]')
      .at(0)
      ?.findAll('[role="tab"]')
      .map((tab) => tab.text());
    expect(topTabs).toEqual(["Overview", "Files", "Report"]);
    expect(wrapper.text()).toContain("Core Memo Workflow");
    expect(wrapper.text()).toContain("Evidence, Ledger, And Source Boundaries");
  });

  it("renders company pages at the production base-relative URL", async () => {
    api.listCompanyReports.mockResolvedValue([
      {
        id: "memo-1",
        kind: "investment_memo_latestage",
        status: "complete",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Internal",
        language: "en",
        updated_at: "2026-08-01T00:00:00Z",
        resume_available: false,
      },
    ]);
    const wrapper = await mountRoute("/generalist?tab=analysis");

    expect(wrapper.text()).toContain("Generalist");
    expect(wrapper.text()).toContain("Core Memo Workflow");
  });

  it("starts a deep investigation from the studio CTA", async () => {
    api.studioInvestigate.mockResolvedValue({
      id: "studio-1",
      kind: "investment_memo_latestage",
      memo_mode: "studio",
      status: "analyzing",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      stage: "Deep investigation — running analysis passes",
    });
    const wrapper = await mountRoute("/research/generalist");
    const memoTab = wrapper
      .findAll("button")
      .find((button) => button.text() === "Report");
    await memoTab.trigger("click");
    await flushPromises();

    const investigateButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Start Deep Investigate");
    expect(investigateButton).toBeTruthy();
    await investigateButton.trigger("click");
    await flushPromises();

    expect(api.studioInvestigate).toHaveBeenCalledWith({
      company_id: "generalist",
      report_type: "Investment Report (Auto)",
    });
    expect(api.generateReport).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("renders new PRD foundation top-level routes", async () => {
    let wrapper = await mountRoute("/innovation-lab");
    expect(wrapper.text()).toContain("Labs");
    expect(wrapper.text()).toContain("Daily sources");
    wrapper.unmount();

    wrapper = await mountRoute("/settings");
    expect(wrapper.text()).toContain("Settings");
    expect(wrapper.text()).toContain("System");
    expect(wrapper.text()).toContain("Advanced tools");
    expect(wrapper.text()).toContain("Workbench");
    expect(wrapper.text()).toContain("Stats");
    expect(wrapper.text()).toContain("Labs");
    wrapper.unmount();

    wrapper = await mountRoute("/user");
    expect(wrapper.text()).toContain("Profile");
    wrapper.unmount();

    wrapper = await mountRoute("/source-library");
    expect(wrapper.text()).toContain("Source Library & Appendix");
    expect(wrapper.text()).toContain("intentionally separate");
    wrapper.unmount();

    wrapper = await mountRoute("/companies/generalist/competitors/nextnav");
    expect(wrapper.text()).toContain("Generalist vs NextNav");
    expect(wrapper.text()).toContain("Head-to-head");
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
    expect(wrapper.text()).toContain("Start fresh");
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
      .find((button) => button.text().includes("Resume"));
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

    const wrapper = await mountRoute("/research/generalist?tab=memo");

    expect(api.listCompanyReports).toHaveBeenCalledWith("generalist");
    expect(api.getReport).toHaveBeenCalledWith("report-1");
    expect(wrapper.text()).toContain("Resume");
    expect(wrapper.text()).toContain("Start fresh");
    wrapper.unmount();
  });

  it("opens analysis markdown artifacts in the viewer drawer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () => "# Claim register\n\n- claim one",
        arrayBuffer: async () => new ArrayBuffer(8),
      })),
    );
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
      run_dir: "data/memos/generalist/run",
      resume_available: false,
      analysis_artifacts: [
        {
          label: "Claim register",
          filename: "claim_register.md",
          download_url:
            "/api/reports/report-1/download?artifact=analysis&file=claim_register.md",
        },
      ],
    });
    const wrapper = await mountRoute("/research/generalist?report=report-1");

    const chip = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Claim register"));
    expect(chip).toBeTruthy();
    await chip.trigger("click");
    await vi.dynamicImportSettled();
    await flushPromises();

    expect(document.querySelector("[role='dialog']")).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith(
      "/api/reports/report-1/download?artifact=analysis&file=claim_register.md",
    );
    expect(document.body.innerHTML).toContain("<h1>Claim register</h1>");
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

    expect(wrapper.text()).toContain("Available draft files remain visible for review");
    expect(wrapper.text()).toContain("Review summary");
    expect(wrapper.text()).not.toContain("sell_side_voice_violation");
    expect(wrapper.text()).not.toContain("The recommendation is Proceed if confirmed");
    expect(wrapper.text()).not.toContain("data/memos/generalist/run");
    // DOCX downloads moved to the Files tab; the Document view no longer
    // renders its own download anchors.
    expect(hrefs).not.toContain("/api/reports/report-1/download?language=en");
    wrapper.unmount();
  });

  it("renders completed memo warnings with gate findings", async () => {
    api.getReport.mockResolvedValue({
      id: "report-warning",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "complete_with_warnings",
      progress: 100,
      stage: "Memo ready (quality warnings)",
      quality_warnings: ["Chinese memo parity gate found 1 P0 finding."],
      memo_quality_lint: { status: "passed", findings: [] },
      memo_chinese_parity: {
        status: "failed",
        findings: [
          {
            severity: "P0",
            code: "zh_core_section_missing",
            location: "executive_summary",
            snippet: "executive_summary",
          },
        ],
      },
    });

    const wrapper = await mountRoute("/research/generalist?report=report-warning");

    expect(wrapper.text()).toContain("Memo ready with quality warnings");
    expect(wrapper.text()).toContain("zh_core_section_missing");
    expect(wrapper.text()).toContain("executive_summary");
    wrapper.unmount();
  });

  it("shows generated memo download links in the documents library", async () => {
    const report = {
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
    };
    api.listCompanyReports.mockResolvedValue([report]);
    api.listCompanyDocuments.mockResolvedValue({
      rows: [
        {
          id: "generated_report:report-1",
          backend: "generated_report",
          backend_label: "Generated Reports",
          record_id: "report-1",
          title: "Investment Memo (Late-Stage)",
          filename: "Investment Memo (Late-Stage).memo",
          kind: "memo",
          type_badge: "MEMO",
          category: "memos",
          category_label: "Memos",
          source_class: "generated memo",
          source_class_label: "generated memo",
          language: "en",
          status: "failed_quality_gate",
          captured_at: "2026-06-23T11:14:02Z",
          provenance: { origin: "Generated memo", source_class: "generated memo" },
          source_refs: [{ title: "Generated memo", source_class: "generated memo" }],
          source_traces: [],
          source_trace_count: 0,
          editable_metadata: false,
          report,
          download_urls: report.download_urls,
          record: { id: "report-1" },
        },
      ],
      groups: [
        {
          id: "memos",
          label: "Memos",
          count: 1,
          rows: [
            {
              id: "generated_report:report-1",
              backend: "generated_report",
              backend_label: "Generated Reports",
              record_id: "report-1",
              title: "Investment Memo (Late-Stage)",
              filename: "Investment Memo (Late-Stage).memo",
              kind: "memo",
              type_badge: "MEMO",
              category: "memos",
              category_label: "Memos",
              source_class: "generated memo",
              source_class_label: "generated memo",
              language: "en",
              status: "failed_quality_gate",
              captured_at: "2026-06-23T11:14:02Z",
              provenance: { origin: "Generated memo", source_class: "generated memo" },
              source_refs: [{ title: "Generated memo", source_class: "generated memo" }],
              source_traces: [],
              source_trace_count: 0,
              editable_metadata: false,
              report,
              download_urls: report.download_urls,
              record: { id: "report-1" },
            },
          ],
        },
      ],
      categories: [{ id: "memos", label: "Memos" }],
      source_classes: ["generated memo"],
      filters: { languages: ["en"], statuses: ["failed_quality_gate"] },
      unresolved_intake_count: 0,
    });

    const wrapper = await mountRoute("/research/generalist?tab=documents");
    const hrefs = wrapper.findAll("a").map((a) => a.attributes("href"));

    expect(wrapper.text()).toContain("Generated Memos");
    expect(wrapper.text()).toContain("EN");
    expect(wrapper.text()).toContain("ZH");
    expect(hrefs).toContain("/api/reports/report-1/download?language=en");
    expect(hrefs).toContain("/api/reports/report-1/download?language=zh");
    wrapper.unmount();
  });

  it("returns failed memo runs to the investigation workflow", async () => {
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
    api.studioInvestigate.mockResolvedValue({
      id: "studio-2",
      kind: "investment_memo_latestage",
      memo_mode: "studio",
      status: "analyzing",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
    });
    const wrapper = await mountRoute("/research/generalist?report=report-1");
    const redoButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Start fresh"));

    expect(redoButton).toBeTruthy();
    await redoButton.trigger("click");
    await flushPromises();

    expect(api.resumeReport).not.toHaveBeenCalled();
    expect(api.generateReport).not.toHaveBeenCalled();
    // Redo in the default Studio Review mode starts a fresh deep
    // investigation.
    expect(api.studioInvestigate).toHaveBeenCalled();
    wrapper.unmount();
  });

  it("surfaces a parked studio investigation after a reload", async () => {
    const parked = {
      id: "studio-4",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      memo_mode: "studio",
      status: "awaiting_studio",
      progress: 55,
      stage: "Investigation complete — review the studio cards",
      studio_investigation: {
        completed_at: "2026-09-01T20:02:51Z",
        seeded_revision_id: "rev-0010",
      },
      updated_at: "2026-09-01T20:02:51Z",
      run_dir: "data/memos/generalist/run",
      resume_available: false,
      analysis_artifacts: [],
    };
    api.listCompanyReports.mockResolvedValue([parked]);
    api.getReport.mockResolvedValue(parked);

    // Plain navigation, no ?report= — a fresh page after a restart.
    const wrapper = await mountRoute("/research/generalist");
    const memoTab = wrapper
      .findAll("button")
      .find((button) => button.text() === "Report");
    await memoTab.trigger("click");
    await flushPromises();

    // The parked investigation is still the active context: the next
    // step is Generate, not a fresh Deep Investigate.
    expect(wrapper.text()).toContain("Cards ready");
    const generateButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Generate Report");
    expect(generateButton).toBeTruthy();
    expect(
      wrapper
        .findAll("button")
        .find((button) => button.text() === "Start Deep Investigate"),
    ).toBeFalsy();
    wrapper.unmount();
  });

  it("defaults the Report tab to Studio after a document deep link", async () => {
    api.getReport.mockResolvedValue({
      id: "memo-1",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      status: "complete",
      progress: 100,
      stage: "Memo ready",
      content_en: "Memo body.",
      run_dir: "data/memos/generalist/run",
      resume_available: false,
      analysis_artifacts: [],
    });
    const wrapper = await mountRoute("/research/generalist?report=memo-1");
    const stageButton = (label) =>
      wrapper.findAll('[role="tab"]').find((tab) => tab.text() === label);

    // The deep link (Files library) opens the document once...
    expect(stageButton("Document").attributes("data-selected")).toBe("true");

    // ...but a later click on the Report tab lands on Studio.
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Overview")
      .trigger("click");
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((button) => button.text() === "Report")
      .trigger("click");
    await flushPromises();

    expect(stageButton("Studio").attributes("data-selected")).toBe("true");
    expect(stageButton("Document").attributes("data-selected")).toBe("false");
    wrapper.unmount();
  });

  it("shows a parked studio investigation as cards-ready and generates from it", async () => {
    api.getReport.mockResolvedValue({
      id: "studio-3",
      company_id: "generalist",
      company_name: "Generalist",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      kind: "investment_memo_latestage",
      memo_mode: "studio",
      status: "awaiting_studio",
      progress: 55,
      stage: "Investigation complete — review the studio cards",
      studio_investigation: {
        completed_at: "2026-09-01T20:02:51Z",
        pass_ok: [],
        pass_failed: [],
        seeded_revision_id: "rev-0010",
      },
      run_dir: "data/memos/generalist/run",
      resume_available: false,
      analysis_artifacts: [],
    });
    api.studioGenerate.mockResolvedValue({
      id: "studio-3",
      kind: "investment_memo_latestage",
      memo_mode: "studio",
      status: "analyzing",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      stage: "Generating memo from studio cards",
    });
    const wrapper = await mountRoute("/research/generalist?report=studio-3");

    // Parked, not running: the card review is the next step.
    expect(wrapper.text()).toContain("Cards ready");
    expect(wrapper.text()).not.toContain("Live progress is in the Jobs rail.");
    const generateButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "Generate Report");
    expect(generateButton).toBeTruthy();
    await generateButton.trigger("click");
    await flushPromises();

    expect(api.studioGenerate).toHaveBeenCalledWith("studio-3");
    expect(api.generateReport).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("shows generate request failures while the company page remains loaded", async () => {
    const err = Object.assign(
      new Error('400 Bad Request: {"detail":"Settings file missing"}'),
      { status: 400 },
    );
    api.generateReport.mockRejectedValue(err);
    api.options.mockResolvedValue({
      report_types: ["Investment Memo (Late-Stage)", "Investment Report"],
      audiences: ["Internal"],
      languages: ["en"],
    });

    const wrapper = await mountRoute("/research/generalist");
    const memoTab = wrapper
      .findAll("button")
      .find((button) => button.text() === "Report");
    expect(memoTab).toBeTruthy();
    await memoTab.trigger("click");
    await flushPromises();

    await wrapper.find("select").setValue("Investment Report");
    const generateButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Generate report"));

    expect(generateButton).toBeTruthy();
    await generateButton.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Memo generation request failed");
    expect(wrapper.text()).toContain("The memo could not be started");
    expect(wrapper.text()).not.toContain("Settings file missing");
    expect(wrapper.text()).not.toContain("HTTP 400");
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
    api.listCompanyReports.mockResolvedValue([
      {
        id: "memo-1",
        kind: "investment_memo_latestage",
        status: "complete",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Internal",
        language: "en",
        updated_at: "2026-08-01T00:00:00Z",
        resume_available: false,
      },
    ]);

    const wrapper = await mountRoute("/research/private-with-ticker?tab=analysis");
    await flushPromises();

    expect(wrapper.text()).toContain("Private Ticker Co");
    expect(wrapper.text()).toContain("Report");
    expect(wrapper.text()).toContain("Core Memo Workflow");
    expect(api.memoAnalysis.get).toHaveBeenCalledWith("private-with-ticker");
  });
});
