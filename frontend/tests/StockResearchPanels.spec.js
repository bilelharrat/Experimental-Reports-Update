import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import StockAggregatePanel from "../src/components/stock/StockAggregatePanel.vue";
import StockEvaluationPanel from "../src/components/stock/StockEvaluationPanel.vue";
import StockReviewQueuePanel from "../src/components/stock/StockReviewQueuePanel.vue";
import StockRunsPanel from "../src/components/stock/StockRunsPanel.vue";
import StockSourceIntakePanel from "../src/components/stock/StockSourceIntakePanel.vue";
import StockStrategyMapPanel from "../src/components/stock/StockStrategyMapPanel.vue";
import StockTrackerRegistryPanel from "../src/components/stock/StockTrackerRegistryPanel.vue";

const tracker = {
  id: "nvidia",
  type: "company",
  display_name: "NVIDIA",
  status: "active",
  is_stale: true,
  latest_thesis: "Company thesis.",
  freshness_policy: { next_due_run: "2026-06-14T12:00:00Z" },
};

const run = {
  run_id: "run-1",
  tracker_id: "nvidia",
  tracker_name: "NVIDIA",
  status: "done",
  source_count: 1,
  confidence: 0.8,
  thesis: "Company thesis.",
  created_at: "2026-06-14T12:00:00Z",
  report_markdown: "# Report",
  source_traces: [{ source_id: "src-1", source_title: "Transcript", locator: "p1", excerpt: "Evidence." }],
  knowledge_updates: [{ id: "ku-1", text: "Keep source manifests.", review_status: "open" }],
};

describe("Stock Research panel components", () => {
  it("renders tracker registry states and emits action events", async () => {
    const empty = mount(StockTrackerRegistryPanel, {
      props: { trackers: [], selectedTrackerIds: [], busy: false },
    });
    expect(empty.text()).toContain("No trackers yet.");

    const wrapper = mount(StockTrackerRegistryPanel, {
      props: { trackers: [tracker], selectedTrackerIds: ["nvidia"], busy: false },
    });
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Company thesis.");

    await wrapper.find("input[type='checkbox']").setValue(false);
    await wrapper.find("button[title='Run tracker']").trigger("click");
    await wrapper.find("button[title='Disable tracker']").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Import Companies").trigger("click");

    expect(wrapper.emitted("toggle-tracker")[0]).toEqual(["nvidia"]);
    expect(wrapper.emitted("run-tracker")[0]).toEqual(["nvidia"]);
    expect(wrapper.emitted("disable-tracker")[0]).toEqual(["nvidia"]);
    expect(wrapper.emitted("import-company-trackers")).toHaveLength(1);
  });

  it("renders source intake states and emits draft and submit events", async () => {
    const empty = mount(StockSourceIntakePanel, {
      props: {
        trackers: [tracker],
        sources: [],
        sourceTrackerIds: [],
        fileForm: {},
        linkForm: {},
        noteForm: {},
        busy: false,
      },
    });
    expect(empty.text()).toContain("No tracker-owned sources yet.");

    const file = new File(["source"], "source.txt", { type: "text/plain" });
    const wrapper = mount(StockSourceIntakePanel, {
      props: {
        trackers: [tracker],
        sources: [
          {
            id: "src-1",
            tracker_id: "nvidia",
            tracker_name: "NVIDIA",
            title: "Transcript",
            source_type: "link",
            extraction_status: "missing",
            relevance: "earnings",
            missing_reason: "Stored file is missing.",
            created_at: "2026-06-14T12:00:00Z",
          },
        ],
        sourceTrackerIds: ["nvidia"],
        fileForm: { title: "", file },
        linkForm: { title: "", url: "https://example.com", notes: "" },
        noteForm: { title: "", body: "Manual note." },
        busy: false,
      },
    });

    expect(wrapper.text()).toContain("Transcript");
    expect(wrapper.text()).toContain("Stored file is missing.");
    await wrapper.find("input[type='checkbox']").setValue(false);
    await wrapper.find("input[placeholder='File title']").setValue("Uploaded transcript");
    await wrapper.find("input[placeholder='Link title']").setValue("Company transcript");
    await wrapper.find("textarea[placeholder='Analyst note']").setValue("Updated note.");
    await wrapper.find("input[type='file']").trigger("change");
    await wrapper.findAll("button").find((button) => button.text() === "Upload File").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Attach Link").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Add Note").trigger("click");

    expect(wrapper.emitted("toggle-source-tracker")[0]).toEqual(["nvidia"]);
    expect(wrapper.emitted("update-file-form")[0][0]).toMatchObject({ title: "Uploaded transcript" });
    expect(wrapper.emitted("update-link-form")[0][0]).toMatchObject({ title: "Company transcript" });
    expect(wrapper.emitted("update-note-form")[0][0]).toMatchObject({ body: "Updated note." });
    expect(wrapper.emitted("file-picked")).toHaveLength(1);
    expect(wrapper.emitted("submit-file-source")).toHaveLength(1);
    expect(wrapper.emitted("submit-link-source")).toHaveLength(1);
    expect(wrapper.emitted("submit-note-source")).toHaveLength(1);
  });

  it("renders run rows and emits orchestration events", async () => {
    const empty = mount(StockRunsPanel, {
      props: { runs: [], selectedRun: null, selectedRunDiff: [], busy: false },
    });
    expect(empty.text()).toContain("No tracker runs yet.");

    const running = { ...run, run_id: "run-running", status: "running", knowledge_updates: [] };
    const failed = { ...run, run_id: "run-failed", status: "error", knowledge_updates: [] };
    const wrapper = mount(StockRunsPanel, {
      props: {
        runs: [run, failed, running],
        selectedRun: run,
        selectedRunDiff: [{ field: "Thesis", current: "Now", previous: "Before" }],
        busy: false,
      },
    });

    expect(wrapper.text()).toContain("Latest Report");
    expect(wrapper.text()).toContain("Current: Now");
    await wrapper.findAll("button").find((button) => button.text() === "Run Aggregate").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Run Strategy").trigger("click");
    await wrapper.find("button[title='Accept knowledge update']").trigger("click");
    await wrapper.find("button[title='Retry run']").trigger("click");
    await wrapper.find("button[title='Cancel run']").trigger("click");
    await wrapper.findAll("button[title='Show run details']")[1].trigger("click");

    expect(wrapper.emitted("run-aggregate")).toHaveLength(1);
    expect(wrapper.emitted("run-strategy-map")).toHaveLength(1);
    expect(wrapper.emitted("review-knowledge-update")[0]).toEqual([run, run.knowledge_updates[0], "resolved"]);
    expect(wrapper.emitted("retry-run")[0]).toEqual([failed]);
    expect(wrapper.emitted("cancel-run")[0]).toEqual([running]);
    expect(wrapper.emitted("select-run")[0]).toEqual(["run-failed"]);
  });

  it("renders aggregate states and emits filter and action events", async () => {
    const empty = mount(StockAggregatePanel, {
      props: {
        aggregate: null,
        aggregateWarnings: [],
        aggregateModuleRows: [],
        filteredAggregateSignals: [],
        aggregateModuleFilter: "all",
        aggregateDirectionFilter: "all",
        busy: false,
      },
    });
    expect(empty.text()).toContain("No weekly aggregate yet.");

    const wrapper = mount(StockAggregatePanel, {
      props: {
        aggregate: {
          period_id: "2026-06-08_to_2026-06-14",
          included_tracker_run_ids: ["nvidia:run-1"],
          excluded_tracker_warnings: [{}],
          markdown: "# Weekly",
          html_blocks: [{ kind: "markdown", body: "HTML-ready block." }],
        },
        aggregateWarnings: [{ kind: "missing source", tracker_id: "nvidia", title: "Official transcript missing." }],
        aggregateModuleRows: [{ id: "company:nvidia", module: "company", tracker_id: "nvidia", title: "Company signal.", source_count: 1 }],
        filteredAggregateSignals: [{ id: "sig-1", source_tracker_id: "nvidia", observation: "Demand signal.", direction: "watch", source_traces: run.source_traces }],
        aggregateModuleFilter: "all",
        aggregateDirectionFilter: "all",
        busy: false,
      },
    });

    expect(wrapper.text()).toContain("Company signal.");
    expect(wrapper.text()).toContain("Demand signal.");
    await wrapper.findAll("select")[0].setValue("company");
    await wrapper.findAll("select")[1].setValue("watch");
    await wrapper.findAll("button").find((button) => button.text() === "Run Aggregate").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Retry").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Cancel").trigger("click");

    expect(wrapper.emitted("update:aggregate-module-filter")[0]).toEqual(["company"]);
    expect(wrapper.emitted("update:aggregate-direction-filter")[0]).toEqual(["watch"]);
    expect(wrapper.emitted("run-aggregate")).toHaveLength(1);
    expect(wrapper.emitted("retry-aggregate")).toHaveLength(1);
    expect(wrapper.emitted("cancel-aggregate")).toHaveLength(1);
  });

  it("renders strategy map states and emits action events", async () => {
    const empty = mount(StockStrategyMapPanel, {
      props: {
        strategyMap: null,
        strategyNodes: [],
        strategySourceRows: [],
        strategyContradictions: [],
        busy: false,
      },
    });
    expect(empty.text()).toContain("No strategy map yet.");

    const wrapper = mount(StockStrategyMapPanel, {
      props: {
        strategyMap: { period_id: "2026-06-14", diff: [{ id: "node-ai", label: "AI", state: "new" }] },
        strategyNodes: [{ id: "node-ai", label: "AI infrastructure", posture: "watch", qualitative_action: "monitor", source_traces: run.source_traces }],
        strategySourceRows: [{ id: "node:node-ai:0", kind: "node", label: "AI infrastructure", trace: run.source_traces[0] }],
        strategyContradictions: [{ id: "c-1", description: "Demand conflicts with supply.", source_traces: run.source_traces }],
        busy: false,
      },
    });

    expect(wrapper.text()).toContain("AI infrastructure");
    expect(wrapper.text()).toContain("Demand conflicts with supply.");
    await wrapper.findAll("button").find((button) => button.text() === "Run Strategy Map").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Retry").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Cancel").trigger("click");

    expect(wrapper.emitted("run-strategy-map")).toHaveLength(1);
    expect(wrapper.emitted("retry-strategy-map")).toHaveLength(1);
    expect(wrapper.emitted("cancel-strategy-map")).toHaveLength(1);
  });

  it("renders review queue states and emits filter and review events", async () => {
    const empty = mount(StockReviewQueuePanel, {
      props: {
        items: [],
        reviewTypes: [],
        reviewFilter: "open",
        reviewTypeFilter: "all",
        reviewRationale: "",
      },
    });
    expect(empty.text()).toContain("No review items.");

    const item = {
      id: "missing:nvidia:run-1",
      title: "No official source attached",
      item_type: "missing_source",
      status: "open",
      severity: "medium",
      artifact_id: "tracker_run:nvidia:run-1",
      source_refs: [{ source_title: "Transcript", locator: "p1" }],
    };
    const wrapper = mount(StockReviewQueuePanel, {
      props: {
        items: [item],
        reviewTypes: ["missing_source"],
        reviewFilter: "open",
        reviewTypeFilter: "all",
        reviewRationale: "",
      },
    });

    expect(wrapper.text()).toContain("No official source attached");
    await wrapper.findAll("select")[0].setValue("all");
    await wrapper.findAll("select")[1].setValue("missing_source");
    await wrapper.find("input[placeholder='Review rationale']").setValue("Reviewed.");
    await wrapper.find("button[title='Resolve']").trigger("click");
    await wrapper.find("button[title='Waive']").trigger("click");
    await wrapper.find("button[title='Reject']").trigger("click");

    expect(wrapper.emitted("update:review-filter")[0]).toEqual(["all"]);
    expect(wrapper.emitted("update:review-type-filter")[0]).toEqual(["missing_source"]);
    expect(wrapper.emitted("update:review-rationale")[0]).toEqual(["Reviewed."]);
    expect(wrapper.emitted("update-review")).toEqual([
      [item, "resolved"],
      [item, "waived"],
      [item, "rejected"],
    ]);
  });

  it("renders evaluation states and emits reviewer events", async () => {
    const empty = mount(StockEvaluationPanel, {
      props: {
        filteredEvaluationRows: [],
        trackerMetricRows: [],
        knowledgeReviewRows: [],
        evaluationTrackerIds: [],
        evaluationTrackerFilter: "all",
        runReviewScoreFields: [],
        runReviewDraft: () => ({ review_notes: "" }),
        busy: false,
      },
    });
    expect(empty.text()).toContain("No tracker trend rows yet.");
    expect(empty.text()).toContain("No evaluation rows yet.");
    expect(empty.text()).toContain("No proposed lessons yet.");

    const row = {
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      run_id: "run-1",
      duration_ms: 42,
      source_count: 1,
      source_quality: { average: 0.75 },
      evidence_coverage: 0.5,
      contradiction_count: 0,
      missing_source_count: 1,
      reviewer_score: null,
    };
    const runReviewDraft = vi.fn(() => ({
      factual_accuracy: "",
      review_notes: "",
    }));
    const lesson = { id: "ku-1", text: "Keep source manifests.", tracker_id: "nvidia", tracker_name: "NVIDIA", run_id: "run-1", review_status: "open" };
    const wrapper = mount(StockEvaluationPanel, {
      props: {
        filteredEvaluationRows: [row],
        trackerMetricRows: [{ tracker_id: "nvidia", tracker_name: "NVIDIA", runs: 1, avg_coverage: 0.5, missing_total: 1, avg_reviewer: null, latest_at: "2026-06-14T12:00:00Z" }],
        knowledgeReviewRows: [lesson],
        evaluationTrackerIds: ["nvidia"],
        evaluationTrackerFilter: "all",
        runReviewScoreFields: [{ id: "factual_accuracy", label: "Fact" }],
        runReviewDraft,
        busy: false,
      },
    });

    expect(wrapper.text()).toContain("42 ms");
    expect(wrapper.text()).toContain("Keep source manifests.");
    await wrapper.find("select").setValue("nvidia");
    await wrapper.find("input[type='number']").setValue("4");
    await wrapper.find("input[placeholder='Review notes']").setValue("Good trace coverage.");
    await wrapper.find("button[title='Save run review']").trigger("click");
    await wrapper.find("button[title='Reject lesson']").trigger("click");

    expect(wrapper.emitted("update:evaluation-tracker-filter")[0]).toEqual(["nvidia"]);
    expect(wrapper.emitted("set-run-review-score")[0]).toEqual([row, "factual_accuracy", "4"]);
    expect(wrapper.emitted("set-run-review-notes")[0]).toEqual([row, "Good trace coverage."]);
    expect(wrapper.emitted("save-run-review")[0]).toEqual([row]);
    expect(wrapper.emitted("review-knowledge-update")[0]).toEqual([lesson, lesson, "rejected"]);
  });
});
