import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import StockResearchView from "../src/views/StockResearchView.vue";
import { api } from "../src/api.js";

vi.mock("vue-router", () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("../src/api.js", () => ({
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
  },
}));

const payload = {
  summary: {
    tracker_count: 3,
    tracker_counts_by_type: { macro: 1, industry: 1, company: 1 },
    due_count: 2,
    stale_count: 1,
    open_review_item_count: 1,
    missing_source_warning_count: 1,
    work_product_count: 1,
    source_count: 2,
  },
  trackers: [
    {
      id: "us-macro",
      type: "macro",
      display_name: "US Macro Tracker",
      status: "active",
      is_stale: false,
      latest_thesis: "Macro thesis.",
      freshness_policy: {},
    },
    {
      id: "nvidia",
      type: "company",
      display_name: "NVIDIA",
      status: "active",
      is_stale: true,
      latest_thesis: "Company thesis.",
      freshness_policy: {},
    },
  ],
  sources: [
    {
      id: "src-1",
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      title: "Transcript",
      source_type: "link",
      relevance: "earnings",
      extraction_status: "ready",
      created_at: "2026-06-13T12:00:00Z",
      chunks: [{ excerpt: "Management commentary excerpt." }],
    },
    {
      id: "src-missing",
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      title: "Deleted source",
      source_type: "file",
      relevance: "earnings",
      extraction_status: "missing",
      missing_reason: "Stored file is missing from tracker source folder.",
      created_at: "2026-06-13T12:00:00Z",
      chunks: [],
    },
  ],
  runs: [
    {
      run_id: "run-1",
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      status: "done",
      source_count: 1,
      confidence: 0.5,
      thesis: "Company thesis.",
      created_at: "2026-06-13T12:00:00Z",
      source_traces: [
        {
          source_title: "Transcript",
          locator: "document",
          excerpt: "Management commentary excerpt.",
        },
      ],
      report_markdown: "# NVIDIA Tracker Report\n\nCompany report body.",
      knowledge_updates: [
        {
          id: "ku-source-baseline",
          text: "Prefer tracker-owned source manifests.",
          review_status: "open",
        },
      ],
    },
    {
      run_id: "run-failed",
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      status: "error",
      source_count: 1,
      confidence: null,
      thesis: "",
      created_at: "2026-06-13T13:00:00Z",
      knowledge_updates: [],
    },
    {
      run_id: "run-running",
      tracker_id: "us-macro",
      tracker_name: "US Macro Tracker",
      status: "running",
      source_count: 0,
      confidence: null,
      thesis: "Run in progress.",
      created_at: "2026-06-13T14:00:00Z",
      knowledge_updates: [],
    },
  ],
  latest_aggregate: {
    period_id: "2026-06-08_to_2026-06-14",
    included_tracker_run_ids: ["nvidia:run-1"],
    modules: {
      macro: [
        {
          tracker_id: "us-macro",
          thesis: "Macro liquidity is watchful.",
          source_traces: [],
        },
      ],
      industry: [],
      company: [
        {
          tracker_id: "nvidia",
          thesis: "Company AI demand remains the core debate.",
          source_traces: [
            {
              source_id: "src-1",
              source_title: "Transcript",
              locator: "document",
            },
          ],
        },
      ],
      cross_tracker: [],
      watchlist: [],
    },
    excluded_tracker_warnings: [
      { tracker_id: "us-macro", warning: "No latest tracker output for this period." },
    ],
    missing_source_warnings: [
      { tracker_id: "nvidia", description: "Official transcript missing." },
    ],
    ranked_signals: [
      {
        id: "sig-1",
        observation: "AI infrastructure demand remains the key signal.",
        source_tracker_id: "nvidia",
        tracker_run_id: "run-1",
        direction: "watch",
        source_traces: [
          {
            source_id: "src-1",
            source_title: "Transcript",
            locator: "document",
            excerpt: "Management commentary excerpt.",
          },
        ],
      },
    ],
    markdown: "# Weekly",
    html_blocks: [{ kind: "markdown", body: "HTML-ready weekly block." }],
  },
  latest_strategy_map: {
    period_id: "2026-06-08_to_2026-06-14",
    nodes: [
      {
        id: "node-ai",
        label: "AI infrastructure",
        posture: "watch",
        qualitative_action: "monitor",
        source_traces: [
          {
            source_id: "src-1",
            source_title: "Transcript",
            locator: "document",
            excerpt: "Management commentary excerpt.",
          },
        ],
      },
    ],
    edges: [
      {
        id: "edge-ai-supply",
        from: "node-ai",
        to: "node-supply",
        relationship: "supply-chain link",
        source_traces: [
          {
            source_id: "src-1",
            source_title: "Transcript",
            locator: "document",
            excerpt: "Supply-chain timing affects AI infrastructure demand.",
          },
        ],
      },
    ],
    diff: [{ id: "node-ai", label: "AI infrastructure", state: "new" }],
    contradictions: [
      {
        id: "contra-1",
        description: "Demand signal conflicts with supply-chain checks.",
        source_traces: [
          { source_title: "Transcript", locator: "document" },
        ],
      },
    ],
  },
  work_products: [
    {
      artifact_id: "tracker_run:nvidia:run-1",
      artifact_type: "tracker_report",
      title: "NVIDIA tracker report",
      status: "needs_review",
      version: 2,
      reviewer: "Serena",
      tracker_id: "nvidia",
      period_id: "2026-06-08_to_2026-06-14",
      supersedes: "tracker_run:nvidia:prior",
      superseded_by: "tracker_run:nvidia:next",
      source_trace_count: 1,
      confidence: 0.5,
      updated_at: "2026-06-13T12:00:00Z",
      export_paths: {
        json: "data/stock_research/trackers/nvidia/runs/run-1/tracker_output.json",
        markdown: "data/stock_research/trackers/nvidia/runs/run-1/report.md",
      },
    },
  ],
  review_items: [
    {
      id: "missing:nvidia:run-1",
      title: "No official source attached",
      item_type: "missing_source",
      status: "open",
      artifact_id: "tracker_run:nvidia:run-1",
      severity: "medium",
      source_refs: [
        {
          source_title: "Transcript",
          locator: "document",
        },
      ],
    },
  ],
  evaluation: {
    runs: [
      {
        tracker_id: "nvidia",
        tracker_name: "NVIDIA",
        run_id: "run-1",
        duration_ms: 42,
        source_count: 1,
        evidence_coverage: 1,
        contradiction_count: 0,
        missing_source_count: 1,
        reviewer_score: null,
        reviewer_scores: {},
      },
    ],
  },
};

describe("StockResearchView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.stockResearch.dashboard.mockResolvedValue(payload);
    api.stockResearch.runSelectedTrackers.mockResolvedValue({});
    api.stockResearch.addLinkSource.mockResolvedValue({});
    api.stockResearch.addNoteSource.mockResolvedValue({});
    api.stockResearch.uploadSource.mockResolvedValue({});
    api.stockResearch.updateReviewItem.mockResolvedValue({});
    api.stockResearch.updateWorkProduct.mockResolvedValue({});
    api.stockResearch.updateRunReview.mockResolvedValue({});
    api.stockResearch.cancelRun.mockResolvedValue({});
    api.stockResearch.retryRun.mockResolvedValue({});
    api.stockResearch.retryAggregate.mockResolvedValue({});
    api.stockResearch.retryStrategyMap.mockResolvedValue({});
    api.stockResearch.reviewKnowledgeUpdate.mockResolvedValue({});
  });

  it("renders dashboard summary and tracker table", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    expect(wrapper.text()).toContain("Stock Research");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("Latest Weekly Aggregate");

    await wrapper.findAll("button").find((button) => button.text() === "Trackers").trigger("click");
    expect(wrapper.text()).toContain("US Macro Tracker");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Company thesis.");
  });

  it("runs selected trackers and refreshes the payload", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Trackers").trigger("click");
    const boxes = wrapper.findAll("input[type='checkbox']");
    await boxes[0].setValue(true);
    await wrapper.findAll("button").find((button) => button.text() === "Run Selected").trigger("click");
    await flushPromises();

    expect(api.stockResearch.runSelectedTrackers).toHaveBeenCalledWith(["us-macro"]);
    expect(api.stockResearch.dashboard).toHaveBeenCalledTimes(2);
  });

  it("renders aggregate, strategy, review, products, and evaluation tabs", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Weekly Aggregate").trigger("click");
    expect(wrapper.text()).toContain("Macro liquidity is watchful.");
    let selects = wrapper.findAll("select");
    await selects[0].setValue("company");
    expect(wrapper.text()).toContain("Company AI demand remains the core debate.");
    expect(wrapper.text()).not.toContain("Macro liquidity is watchful.");
    expect(wrapper.text()).toContain("AI infrastructure demand remains the key signal.");
    expect(wrapper.text()).toContain("Official transcript missing.");
    expect(wrapper.text()).toContain("HTML-ready weekly block.");

    await wrapper.findAll("button").find((button) => button.text() === "Strategy Map").trigger("click");
    expect(wrapper.text()).toContain("AI infrastructure");
    expect(wrapper.text()).toContain("Research guidance only");
    expect(wrapper.text()).toContain("Source Inspector");
    expect(wrapper.text()).toContain("Management commentary excerpt.");
    expect(wrapper.text()).toContain("supply-chain link");
    expect(wrapper.text()).toContain("Demand signal conflicts with supply-chain checks.");

    await wrapper.findAll("button").find((button) => button.text() === "Work Products").trigger("click");
    expect(wrapper.text()).toContain("NVIDIA tracker report");
    selects = wrapper.findAll("select");
    await selects[0].setValue("tracker_report");
    await selects[1].setValue("needs_review");
    await selects[2].setValue("nvidia");
    await selects[3].setValue("2026-06-08_to_2026-06-14");
    expect(wrapper.text()).toContain("tracker_run:nvidia:run-1");
    expect(wrapper.text()).toContain("v2");
    expect(wrapper.text()).toContain("Serena");
    expect(wrapper.text()).toContain("supersedes tracker_run:nvidia:prior");
    expect(wrapper.text()).toContain("superseded by tracker_run:nvidia:next");
    expect(wrapper.text()).toContain("markdown");
    await wrapper.find("button[title='Pin']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.updateWorkProduct).toHaveBeenCalledWith(
      "tracker_run:nvidia:run-1",
      { pinned: true },
    );
    await wrapper.find("button[title='Approve']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.updateWorkProduct).toHaveBeenCalledWith(
      "tracker_run:nvidia:run-1",
      { status: "approved", review_state: "resolved" },
    );
    await wrapper.find("button[title='Archive']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.updateWorkProduct).toHaveBeenCalledWith(
      "tracker_run:nvidia:run-1",
      { archived: true, status: "archived" },
    );

    await wrapper.findAll("button").find((button) => button.text() === "Review Queue").trigger("click");
    expect(wrapper.text()).toContain("No official source attached");
    selects = wrapper.findAll("select");
    await selects[1].setValue("missing_source");
    expect(wrapper.text()).toContain("tracker_run:nvidia:run-1");
    expect(wrapper.text()).toContain("Transcript");
    await wrapper.find("input[placeholder='Review rationale']").setValue("Reviewed missing source.");
    await wrapper.find("button[title='Waive']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.updateReviewItem).toHaveBeenCalledWith(
      "missing:nvidia:run-1",
      { status: "waived", rationale: "Reviewed missing source." },
    );

    await wrapper.findAll("button").find((button) => button.text() === "Evaluation").trigger("click");
    expect(wrapper.text()).toContain("42 ms");
    expect(wrapper.text()).toContain("Prefer tracker-owned source manifests.");
  });

  it("submits source upload, link, and note assignments", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Sources").trigger("click");

    await wrapper.find("input[placeholder='File title']").setValue("Uploaded transcript");
    const file = new File(["source text"], "transcript.txt", { type: "text/plain" });
    const fileInput = wrapper.find("input[type='file']");
    Object.defineProperty(fileInput.element, "files", {
      configurable: true,
      value: [file],
    });
    await fileInput.trigger("change");
    await wrapper.findAll("button").find((button) => button.text() === "Upload File").trigger("click");
    await flushPromises();
    expect(api.stockResearch.uploadSource).toHaveBeenCalledWith({
      file,
      trackerIds: ["us-macro"],
      title: "Uploaded transcript",
      priority: "user_provided",
      relevance: "this_week_input",
    });

    await wrapper.find("input[placeholder='Link title']").setValue("Company transcript");
    await wrapper.find("input[placeholder='https://source.example']").setValue("https://example.com/transcript");
    await wrapper.find("textarea[placeholder='Source notes']").setValue("Official transcript notes.");
    await wrapper.findAll("button").find((button) => button.text() === "Attach Link").trigger("click");
    await flushPromises();
    expect(api.stockResearch.addLinkSource).toHaveBeenCalledWith({
      title: "Company transcript",
      url: "https://example.com/transcript",
      notes: "Official transcript notes.",
      priority: "user_provided",
      relevance: "this_week_input",
      tracker_ids: ["us-macro"],
    });

    await wrapper.find("input[placeholder='Note title']").setValue("Analyst note");
    await wrapper.find("textarea[placeholder='Analyst note']").setValue("Manual tracker note.");
    await wrapper.findAll("button").find((button) => button.text() === "Add Note").trigger("click");
    await flushPromises();
    expect(api.stockResearch.addNoteSource).toHaveBeenCalledWith({
      title: "Analyst note",
      body: "Manual tracker note.",
      priority: "user_provided",
      relevance: "this_week_input",
      tracker_ids: ["us-macro"],
    });
  });

  it("renders source states and supports retry and knowledge review controls", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Sources").trigger("click");
    expect(wrapper.text()).toContain("missing");
    expect(wrapper.text()).toContain("Stored file is missing from tracker source folder.");

    await wrapper.findAll("button").find((button) => button.text() === "Runs").trigger("click");
    expect(wrapper.text()).toContain("Latest Report");
    expect(wrapper.text()).toContain("Company report body.");
    expect(wrapper.text()).toContain("Current vs Previous");
    expect(wrapper.text()).toContain("running");
    await wrapper.find("button[title='Cancel run']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.cancelRun).toHaveBeenCalledWith("us-macro", "run-running");
    await wrapper.find("button[title='Retry run']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.retryRun).toHaveBeenCalledWith("nvidia", "run-failed");

    await wrapper.find("button[title='Accept knowledge update']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.reviewKnowledgeUpdate).toHaveBeenCalledWith(
      "nvidia",
      "run-1",
      "ku-source-baseline",
      { status: "resolved", rationale: "" },
    );

    await wrapper.findAll("button").find((button) => button.text() === "Weekly Aggregate").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Retry").trigger("click");
    await flushPromises();
    expect(api.stockResearch.retryAggregate).toHaveBeenCalledWith("2026-06-08_to_2026-06-14");
  });

  it("saves run reviewer scores from the evaluation table", async () => {
    const wrapper = mount(StockResearchView);
    await flushPromises();

    await wrapper.findAll("button").find((button) => button.text() === "Evaluation").trigger("click");
    const scoreInputs = wrapper.findAll("input[type='number']");
    for (const [index, value] of ["4", "5", "3", "4", "4"].entries()) {
      await scoreInputs[index].setValue(value);
    }
    await wrapper.find("input[placeholder='Review notes']").setValue("Good source trace coverage.");
    await wrapper.find("button[title='Save run review']").trigger("click");
    await flushPromises();

    expect(api.stockResearch.updateRunReview).toHaveBeenCalledWith(
      "nvidia",
      "run-1",
      {
        factual_accuracy: 4,
        usefulness: 5,
        source_quality: 3,
        writing_quality: 4,
        actionability: 4,
        review_notes: "Good source trace coverage.",
      },
    );

    await wrapper.find("button[title='Reject lesson']").trigger("click");
    await flushPromises();
    expect(api.stockResearch.reviewKnowledgeUpdate).toHaveBeenCalledWith(
      "nvidia",
      "run-1",
      "ku-source-baseline",
      { status: "rejected", rationale: "" },
    );
  });
});
