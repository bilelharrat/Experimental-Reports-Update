import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MemoBenchmarkPanel from "../src/components/memo/MemoBenchmarkPanel.vue";
import MemoChartPlansPanel from "../src/components/memo/MemoChartPlansPanel.vue";
import MemoEvidenceMatrixPanel from "../src/components/memo/MemoEvidenceMatrixPanel.vue";
import MemoGeneratedMemoControlsPanel from "../src/components/memo/MemoGeneratedMemoControlsPanel.vue";
import MemoNarrativeHooksPanel from "../src/components/memo/MemoNarrativeHooksPanel.vue";
import MemoReadinessPanel from "../src/components/memo/MemoReadinessPanel.vue";
import MemoResearchTasksPanel from "../src/components/memo/MemoResearchTasksPanel.vue";
import MemoRiskPriorityPanel from "../src/components/memo/MemoRiskPriorityPanel.vue";
import MemoSourceBriefPanel from "../src/components/memo/MemoSourceBriefPanel.vue";
import MemoToolLauncherPanel from "../src/components/memo/MemoToolLauncherPanel.vue";
import RunLedgerTable from "../src/components/RunLedgerTable.vue";

describe("Memo panel components", () => {
  it("renders generated memo controls and emits approval actions", async () => {
    const wrapper = mount(MemoGeneratedMemoControlsPanel, {
      props: {
        session: { id: "session-1", status: "draft" },
        approved: false,
        approving: false,
        loading: false,
        readyForApproval: true,
        canGenerateMemo: true,
        approvalTitle: "Approve analysis",
      },
    });

    expect(wrapper.text()).toContain("Memo Studio");
    expect(wrapper.text()).toContain("session-1");
    await wrapper.findAll("button").find((button) => button.text() === "Approve analysis").trigger("click");
    await wrapper.findAll("button").find((button) => button.text() === "Generate memo").trigger("click");

    expect(wrapper.emitted("approve")).toHaveLength(1);
    expect(wrapper.emitted("generate-memo")).toHaveLength(1);
  });

  it("renders normalized run ledger rows", () => {
    const wrapper = mount(RunLedgerTable, {
      props: {
        rows: [
          {
            ledger_id: "memo_tools:generalist:session-1:research_task:task-1",
            workspace: "memo_tools",
            job_kind: "research_task",
            artifact_id: "research_task:task-1",
            company_id: "generalist",
            session_id: "session-1",
            run_id: "session-1/task-1",
            status: "done",
            updated_at: "2026-06-14T12:00:00Z",
            duration_ms: 1234,
            source_count: 2,
            evidence_coverage: 0.5,
            estimated_cost_usd: 0.012,
          },
        ],
        title: "Memo Run Ledger",
      },
    });

    expect(wrapper.text()).toContain("Memo Run Ledger");
    expect(wrapper.text()).toContain("research task");
    expect(wrapper.text()).toContain("memo tools");
    expect(wrapper.text()).toContain("2 sources");
    expect(wrapper.text()).toContain("coverage 50%");
    expect(wrapper.text()).toContain("$0.01");
  });

  it("renders readiness blockers and emits readiness review actions", async () => {
    const area = {
      id: "gap-1",
      severity: "medium",
      area: "Chart data incomplete",
      why_it_matters: "Production evidence is missing.",
      status: "open",
    };
    const wrapper = mount(MemoReadinessPanel, {
      props: {
        readiness: {
          score: 1,
          total: 2,
          gates: [{ id: "thesis", label: "Thesis drafted", status: "done" }],
        },
        readinessPct: 50,
        readinessBlockers: [{ kind: "gap", id: "gap-1", label: "Resolve chart data" }],
        additionalAreas: [area],
        readinessReviewDraft: { "gap-1": "" },
        savingArtifact: null,
      },
    });

    expect(wrapper.text()).toContain("Approval blockers");
    await wrapper.find("textarea").setValue("Waived for draft.");
    await wrapper.findAll("button").find((button) => button.text() === "Waive").trigger("click");

    expect(wrapper.emitted("update-readiness-review-draft")[0]).toEqual(["gap-1", "Waived for draft."]);
    expect(wrapper.emitted("save-readiness-review")[0]).toEqual([area, "waived"]);
  });

  it("renders tool launcher and memo grader controls", async () => {
    const wrapper = mount(MemoToolLauncherPanel, {
      props: {
        tools: [
          {
            name: "memo_grader",
            label: "Memo Grader",
            description: "Grade completed memos.",
            stage: "after_memo",
            status: "done",
          },
        ],
        runningTool: null,
        savingArtifact: null,
        completedMemoRuns: [{ id: "report-1", run_id: "memo-run-1" }],
        memoGrader: {
          status: "graded",
          completed_report_id: "report-1",
          confidence: "medium",
          lessons_for_future_memo_runs: ["Require source evidence."],
        },
      },
    });

    expect(wrapper.text()).toContain("Memo Grader");
    expect(wrapper.text()).toContain("Require source evidence.");
    await wrapper.find("select").setValue("report-1");
    await wrapper.find("button[title='Run Memo Grader']").trigger("click");

    expect(wrapper.emitted("select-memo-for-grading")[0]).toEqual(["report-1"]);
    expect(wrapper.emitted("run-tool")[0]).toEqual(["memo_grader"]);
  });

  it("renders risk priority controls and emits save, move, and selection events", async () => {
    const risk = {
      id: "risk-1",
      title: "Customer proof",
      status: "open",
      decision_question: "Is production adoption verified?",
      why_it_matters: "It gates the memo.",
    };
    const wrapper = mount(MemoRiskPriorityPanel, {
      props: {
        risks: [risk],
        prioritizedRisks: [risk],
        riskPriorityMap: new Map([["risk-1", { rank: 1, selected: false }]]),
        riskPriorityDraft: [{ risk_id: "risk-1", rank: 1, selected: false }],
        savingArtifact: null,
        canMoveRisk: () => true,
      },
    });

    expect(wrapper.text()).toContain("Customer proof");
    await wrapper.find("button[title='Move risk down']").trigger("click");
    await wrapper.find("input[type='checkbox']").setValue(true);
    await wrapper.findAll("button").find((button) => button.text() === "Save priorities").trigger("click");

    expect(wrapper.emitted("move-risk-priority")[0]).toEqual(["risk-1", 1]);
    expect(wrapper.emitted("set-risk-selected")[0]).toEqual(["risk-1", true]);
    expect(wrapper.emitted("save-risk-priorities")).toHaveLength(1);
  });

  it("renders evidence matrix rows and emits filter updates", async () => {
    const wrapper = mount(MemoEvidenceMatrixPanel, {
      props: {
        evidenceMatrix: { claim_count: 1 },
        evidenceMatrixError: null,
        evidenceRows: [
          {
            claim: "ARR evidence is missing.",
            status: "missing",
            confidence: "low",
            source_coverage: { supporting_count: 0, contradicting_count: 0, missing_count: 1 },
            supporting_evidence: [{ locator: "p.2", excerpt: "Only pilots confirmed." }],
          },
        ],
        evidenceStatusFilter: "all",
      },
    });

    expect(wrapper.text()).toContain("ARR evidence is missing.");
    expect(wrapper.text()).toContain("Only pilots confirmed.");
    await wrapper.findAll("button").find((button) => button.text() === "missing").trigger("click");
    expect(wrapper.emitted("update:evidence-status-filter")[0]).toEqual(["missing"]);
  });

  it("renders research tasks and emits task action events", async () => {
    const task = {
      id: "task-1",
      title: "Deployment proof",
      priority: "high",
      status: "not_started",
      source_type: "research",
      prompt: "Check deployment evidence.",
      selected_source_ids: [],
      answer: "Deployment depth remains unproven.",
      supporting_evidence: [{ filename: "source.md", excerpt: "Only pilots confirmed." }],
      open_questions: ["Need contracted ARR."],
    };
    const runningTask = {
      ...task,
      id: "task-running",
      title: "Running deployment proof",
      status: "running",
      answer: "",
      supporting_evidence: [],
      open_questions: [],
    };
    const wrapper = mount(MemoResearchTasksPanel, {
      props: {
        tasks: [task, runningTask],
        sourceFiles: [{ id: "source-1", filename: "source.md" }],
        batchStatus: { launched_task_ids: ["task-1"], concurrency: 2, statuses: { "task-1": "launched" } },
        runningBatch: false,
        hasRunningTasks: false,
        runningTask: null,
        cancellingTask: null,
        savingTask: null,
      },
    });

    expect(wrapper.text()).toContain("Deployment depth remains unproven.");
    expect(wrapper.text()).toContain("Only pilots confirmed.");
    await wrapper.findAll("button").find((button) => button.text() === "Run selected").trigger("click");
    await wrapper.find("button[title='Run task']").trigger("click");
    await wrapper.find("button[title='Cancel task']").trigger("click");
    await wrapper.find("input[type='checkbox']").setValue(true);

    expect(wrapper.emitted("run-selected-tasks")).toHaveLength(1);
    expect(wrapper.emitted("run-research-task")[0]).toEqual(["task-1"]);
    expect(wrapper.emitted("cancel-research-task")[0]).toEqual(["task-running"]);
    expect(wrapper.emitted("toggle-task-source")[0]).toEqual([task, "source-1", true]);
  });

  it("renders source brief claims, operator notes, and source evidence", () => {
    const wrapper = mount(MemoSourceBriefPanel, {
      props: {
        sourceBrief: {
          summary: "Use source-backed visuals only.",
          confidence: "medium",
          compact_claims: [
            {
              id: "claim-1",
              claim: "Only pilots were confirmed.",
              evidence_status: "partial",
              confidence: "high",
              source_traces: [{ locator: "customer-note.md", excerpt: "Pilot evidence is documented." }],
            },
          ],
          missing_evidence: ["Contracted ARR by customer."],
          no_go_claims: ["Do not visualize pilots as production adoption."],
          visual_opportunities: [{ id: "visual-1", title: "Pilot ladder", rationale: "Separates pilots." }],
          reviewer_prompts: [{ id: "prompt-1", prompt: "Choose overlay mode.", required: true }],
        },
      },
    });

    expect(wrapper.text()).toContain("Only pilots were confirmed.");
    expect(wrapper.text()).toContain("Pilot evidence is documented.");
    expect(wrapper.text()).toContain("Choose overlay mode.");
  });

  it("renders chart plans, operator notes, and emits save", async () => {
    const wrapper = mount(MemoChartPlansPanel, {
      props: {
        chartSpecsDraft: [
          {
            id: "chart-1",
            title: "Deployment proof ladder",
            purpose: "Separate pilots from production.",
            image_generation_mode: "no_text_overlay",
            source_availability: "partial",
            include_in_final_memo: true,
            required_metrics: [{ id: "arr", label: "Latest ARR", value: null, source_available: false }],
            information_gaps: ["ARR bridge."],
            reviewer_prompts: [{ id: "prompt-1", prompt: "Choose visual mode.", required: true }],
            source_traces: [{ locator: "memo", excerpt: "Production adoption is not yet sourced." }],
          },
        ],
        savingArtifact: null,
      },
    });

    expect(wrapper.text()).toContain("Deployment proof ladder");
    expect(wrapper.text()).toContain("Choose visual mode.");
    expect(wrapper.text()).toContain("Production adoption is not yet sourced.");
    await wrapper.findAll("button").find((button) => button.text() === "Save charts").trigger("click");
    expect(wrapper.emitted("save-chart-specs")).toHaveLength(1);
  });

  it("renders narrative hooks and benchmark edits", async () => {
    const narrative = {
      selected_opening_id: "opening-1",
      selected_transition_id: "transition-1",
      selected_ending_id: "ending-1",
      openings: [{ id: "opening-1", text: "Start with deployment proof.", tone: "direct" }],
      transitions: [{ id: "transition-1", text: "The burden shifts to proof.", tone: "bridge" }],
      endings: [{ id: "ending-1", text: "Stay conditional.", tone: "conditional" }],
      reviewer_prompts: [{ id: "prompt-1", prompt: "Choose tone aggressiveness.", resolved_choice: "direct" }],
    };
    const narrativeWrapper = mount(MemoNarrativeHooksPanel, {
      props: { narrativeDraft: narrative, sessionId: "session-1", savingArtifact: null },
    });
    expect(narrativeWrapper.text()).toContain("The burden shifts to proof.");
    await narrativeWrapper.findAll("button").find((button) => button.text() === "Save hooks").trigger("click");
    expect(narrativeWrapper.emitted("save-narrative")).toHaveLength(1);

    const benchmarkDraft = {
      summary: "Benchmark summary",
      public_comps: [{ id: "comp-1", company: "Rockwell", ticker: "ROK", confidence: "medium" }],
      benchmark_gaps: ["ARR bridge."],
      must_prove: ["Production adoption."],
    };
    const benchmarkWrapper = mount(MemoBenchmarkPanel, {
      props: {
        benchmark: benchmarkDraft,
        benchmarkDraft,
        benchmarkView: benchmarkDraft,
        savingArtifact: null,
      },
    });
    await benchmarkWrapper.findAll("input").find((input) => input.element.value === "Rockwell").setValue("Rockwell Automation");
    await benchmarkWrapper.findAll("button").find((button) => button.text() === "Save benchmark").trigger("click");
    expect(benchmarkDraft.public_comps[0].company).toBe("Rockwell Automation");
    expect(benchmarkWrapper.emitted("save-benchmark")).toHaveLength(1);
  });
});
