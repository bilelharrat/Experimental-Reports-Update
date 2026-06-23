import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import StockResearchView from "../src/views/StockResearchView.vue";
import ResearchView from "../src/views/ResearchView.vue";
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
    getReport: vi.fn(),
    generateReport: vi.fn(),
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
    expect(wrapper.text()).toContain("Core Memo Workflow");
    expect(wrapper.text()).toContain("Evidence, Ledger, And Source Boundaries");
  });

  it("renders company pages at the production base-relative URL", async () => {
    const wrapper = await mountRoute("/generalist?tab=analysis");

    expect(wrapper.text()).toContain("Generalist");
    expect(wrapper.text()).toContain("Core Memo Workflow");
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
