import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  get: vi.fn(),
  runTool: vi.fn(),
  patchArtifact: vi.fn(),
  patchTask: vi.fn(),
  runTask: vi.fn(),
  runSelectedTasks: vi.fn(),
  cancelTask: vi.fn(),
  getEvidenceMatrix: vi.fn(),
  runLedger: vi.fn(),
  refineRisk: vi.fn(),
  approve: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: { memoAnalysis: m },
}));

import MemoAnalysisDashboard from "../src/components/MemoAnalysisDashboard.vue";

function baseSession(overrides = {}) {
  return {
    id: "session-1",
    status: "draft",
    approved_for_memo: false,
    tools: [],
    readiness: {
      score: 7,
      total: 9,
      pct: 7 / 9,
      ready_for_approval: false,
      ready_for_memo: false,
      approval_blockers: [
        {
          id: "chart-gap-chart-adoption-ladder",
          kind: "additional_area",
          label: "Chart data incomplete: Deployment / Adoption Ladder",
        },
      ],
      gates: [
        { id: "thesis_spine", label: "Thesis spine drafted", status: "done" },
        { id: "approved", label: "Final memo generation approved", status: "missing" },
      ],
    },
    additional_areas: [
      {
        id: "chart-gap-chart-adoption-ladder",
        severity: "medium",
        area: "Chart data incomplete: Deployment / Adoption Ladder",
        why_it_matters: "Customer production evidence is missing.",
        status: "open",
      },
    ],
    artifacts: {
      input_manifest: {
        research_files: [
          { id: "source-1", filename: "pitchbook.pdf" },
        ],
      },
      thesis_spine: {
        approved: true,
        investment_highlights: [],
        investment_risks: [],
        top_gating_questions: [],
      },
      research_tasks: { tasks: [] },
    },
    ...overrides,
  };
}

function riskSession(overrides = {}) {
  return baseSession({
    artifacts: {
      ...baseSession().artifacts,
      strategic_risks: {
        risks: [
          {
            id: "risk-1",
            title: "Customer proof",
            decision_question: "Is production adoption verified?",
            why_it_matters: "Unproven adoption can delay revenue.",
            mitigation_or_monitoring: "Track production renewals.",
            status: "unresearched",
          },
        ],
      },
    },
    ...overrides,
  });
}

const emptyMatrix = {
  claim_count: 0,
  claims: [],
};

function mountDashboard() {
  return mount(MemoAnalysisDashboard, {
    props: { companyId: "generalist" },
  });
}

describe("MemoAnalysisDashboard", () => {
  let wrapper;

  beforeEach(() => {
    vi.clearAllMocks();
    m.get.mockResolvedValue(baseSession());
    m.getEvidenceMatrix.mockResolvedValue(emptyMatrix);
    m.patchArtifact.mockImplementation(() => Promise.resolve(baseSession({
      readiness: {
        ...baseSession().readiness,
        ready_for_approval: true,
        approval_blockers: [],
      },
      additional_areas: [
        {
          ...baseSession().additional_areas[0],
          status: "waived",
          rationale: "Waived for draft.",
        },
      ],
    })));
    m.patchTask.mockImplementation(() => Promise.resolve(baseSession()));
    m.runSelectedTasks.mockImplementation(() => Promise.resolve(baseSession({
      batch: {
        launched_task_ids: ["task-1"],
        concurrency: 2,
        statuses: { "task-1": "launched" },
      },
    })));
    m.cancelTask.mockImplementation(() => Promise.resolve(baseSession()));
    m.runLedger.mockResolvedValue([
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
        source_count: 1,
        evidence_coverage: 1,
        estimated_cost_usd: 0,
      },
    ]);
  });

  afterEach(() => {
    wrapper?.unmount();
  });

  it("allows report generation while approval blockers remain, then saves a waiver", async () => {
    m.get.mockResolvedValue(riskSession());
    wrapper = mountDashboard();
    await flushPromises();

    const approveButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Approve analysis"));
    const generateButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Generate report"));

    expect(approveButton.attributes("disabled")).toBeDefined();
    expect(generateButton.attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).toContain("Approval blockers");
    expect(wrapper.text()).toContain("Memo Run Ledger");
    expect(wrapper.text()).toContain("research task");

    await generateButton.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("generate-memo")[0]).toEqual(["session-1"]);

    await wrapper.find("textarea").setValue("Waived for draft.");
    const waiveButton = wrapper.findAll("button")
      .find((button) => button.text() === "Waive");
    await waiveButton.trigger("click");
    await flushPromises();

    expect(m.patchArtifact).toHaveBeenCalledWith(
      "generalist",
      "readiness_reviews",
      {
        items: [
          {
            id: "chart-gap-chart-adoption-ladder",
            status: "waived",
            rationale: "Waived for draft.",
          },
        ],
      },
    );
  });

  it("starts the strategic investigation before report generation", async () => {
    const generated = riskSession();
    m.runTool.mockResolvedValue(generated);
    wrapper = mountDashboard();
    await flushPromises();

    const startButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Start investigation"));
    await startButton.trigger("click");
    await flushPromises();

    expect(m.runTool).toHaveBeenCalledWith("generalist", "strategic_risk_mapper");
    expect(wrapper.text()).toContain("Customer proof");
    expect(wrapper.text()).toContain("Generate report");
  });

  it("saves edited risk cards and priorities before generating", async () => {
    const generated = riskSession();
    m.get.mockResolvedValue(generated);
    m.patchArtifact.mockImplementation((companyId, artifactName, patch) =>
      Promise.resolve(
        artifactName === "strategic_risks"
          ? riskSession({
              artifacts: {
                ...riskSession().artifacts,
                strategic_risks: patch,
              },
            })
          : generated,
      ),
    );
    wrapper = mountDashboard();
    await flushPromises();

    await wrapper.find("#risk-title-risk-1").setValue("Customer production proof");
    const generateButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Generate report"));
    await generateButton.trigger("click");
    await flushPromises();

    expect(m.patchArtifact).toHaveBeenNthCalledWith(
      1,
      "generalist",
      "strategic_risks",
      expect.objectContaining({
        risks: [expect.objectContaining({ title: "Customer production proof" })],
      }),
    );
    expect(m.patchArtifact).toHaveBeenNthCalledWith(
      2,
      "generalist",
      "risk_priorities",
      expect.objectContaining({ priorities: expect.any(Array) }),
    );
    expect(wrapper.emitted("generate-memo")[0]).toEqual(["session-1"]);
  });

  it("patches selected source ids for a task", async () => {
    m.get.mockResolvedValue(baseSession({
      artifacts: {
        ...baseSession().artifacts,
        research_tasks: {
          tasks: [
            {
              id: "task-1",
              title: "Customer depth",
              prompt: "Check customer evidence.",
              priority: "high",
              status: "not_started",
              selected_source_ids: [],
            },
          ],
        },
      },
    }));
    wrapper = mountDashboard();
    await flushPromises();

    const sourceLabel = wrapper.findAll("label")
      .find((label) => label.text().includes("pitchbook.pdf"));
    await sourceLabel.find("input").setValue(true);
    await flushPromises();

    expect(m.patchTask).toHaveBeenCalledWith(
      "generalist",
      "task-1",
      { selected_source_ids: ["source-1"] },
    );
  });

  it("runs selected memo research tasks", async () => {
    m.get.mockResolvedValue(baseSession({
      artifacts: {
        ...baseSession().artifacts,
        research_tasks: {
          tasks: [
            {
              id: "task-1",
              title: "Customer depth",
              prompt: "Check customer evidence.",
              priority: "high",
              status: "not_started",
              selected_source_ids: ["source-1"],
            },
          ],
        },
      },
    }));
    wrapper = mountDashboard();
    await flushPromises();

    const runButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Run selected"));
    await runButton.trigger("click");
    await flushPromises();

    expect(m.runSelectedTasks).toHaveBeenCalledWith("generalist", true);
  });

  it("saves the selected completed memo for grading", async () => {
    m.get.mockResolvedValue(baseSession({
      tools: [
        {
          name: "memo_grader",
          label: "Memo Grader",
          description: "Grade completed memos.",
          stage: "after_memo",
          status: "not_started",
        },
      ],
      completed_memo_runs: [
        { id: "report-1", run_id: "run-1" },
      ],
      artifacts: {
        ...baseSession().artifacts,
        memo_grader: { selected_report_id: null },
      },
    }));
    wrapper = mountDashboard();
    await flushPromises();

    await wrapper.find("select").setValue("report-1");
    await flushPromises();

    expect(m.patchArtifact).toHaveBeenCalledWith(
      "generalist",
      "memo_grader",
      {
        selected_report_id: "report-1",
        updated_at: expect.any(String),
      },
    );
  });

  it("saves benchmark row edits", async () => {
    m.get.mockResolvedValue(baseSession({
      artifacts: {
        ...baseSession().artifacts,
        benchmark_dashboard: {
          summary: "Benchmark summary",
          public_comps: [
            {
              id: "comp-1",
              company: "Rockwell",
              ticker: "ROK",
              revenue_growth_pct: 8,
              gross_margin_pct: 41,
              ev_revenue: 4,
              fcf_margin_pct: 16,
              sell_side_theme: "Industrial automation.",
              confidence: "medium",
            },
          ],
          benchmark_gaps: [],
          must_prove: [],
        },
      },
    }));
    wrapper = mountDashboard();
    await flushPromises();

    const companyInput = wrapper.findAll("input")
      .find((input) => input.element.value === "Rockwell");
    await companyInput.setValue("Rockwell Automation");
    const saveButton = wrapper.findAll("button")
      .find((button) => button.text().includes("Save benchmark"));
    await saveButton.trigger("click");
    await flushPromises();

    expect(m.patchArtifact).toHaveBeenCalledWith(
      "generalist",
      "benchmark_dashboard",
      expect.objectContaining({
        public_comps: [
          expect.objectContaining({ company: "Rockwell Automation" }),
        ],
      }),
    );
  });

  it("renders structured task evidence and matrix filters", async () => {
    m.get.mockResolvedValue(baseSession({
      artifacts: {
        ...baseSession().artifacts,
        research_tasks: {
          tasks: [
            {
              id: "task-1",
              title: "Deployment proof",
              prompt: "Check deployment evidence.",
              priority: "high",
              status: "done",
              answer: "Deployment depth remains unproven.",
              confidence: "medium",
              sources_checked: ["customer-note.md"],
              supporting_evidence: [
                {
                  filename: "customer-note.md",
                  locator: "p.2",
                  excerpt: "Only pilots were confirmed.",
                },
              ],
              contradicting_evidence: [],
              open_questions: ["Need contracted ARR by customer."],
            },
          ],
        },
      },
    }));
    m.getEvidenceMatrix.mockResolvedValue({
      claim_count: 2,
      claims: [
        {
          claim: "Matrix-only mixed claim.",
          status: "mixed",
          confidence: "medium",
          source_coverage: {
            supporting_count: 1,
            contradicting_count: 1,
            missing_count: 1,
          },
          supporting_evidence: [
            { locator: "p.2", excerpt: "Only pilots were confirmed." },
          ],
          contradicting_evidence: [],
        },
        {
          claim: "ARR evidence is missing.",
          status: "missing",
          confidence: "low",
          source_coverage: {
            supporting_count: 0,
            contradicting_count: 0,
            missing_count: 1,
          },
          supporting_evidence: [],
          contradicting_evidence: [],
        },
      ],
    });
    wrapper = mountDashboard();
    await flushPromises();

    expect(wrapper.text()).toContain("Deployment depth remains unproven.");
    expect(wrapper.text()).toContain("Only pilots were confirmed.");
    expect(wrapper.text()).toContain("Need contracted ARR by customer.");

    const missingFilter = wrapper.findAll("button")
      .find((button) => button.text() === "missing");
    await missingFilter.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("ARR evidence is missing.");
    expect(wrapper.text()).not.toContain("Matrix-only mixed claim.");
  });

  it("renders the memo toolbox catalog, review queue, and source boundaries", async () => {
    m.get.mockResolvedValue(baseSession({
      tools: [
        {
          name: "chart_spec_builder",
          label: "Chart Spec Builder",
          description: "Build chart plans.",
          stage: "optional",
          status: "running",
        },
      ],
      completed_memo_runs: [
        { id: "report-1", run_id: "memo-run-1" },
      ],
      artifacts: {
        ...baseSession().artifacts,
        strategic_risks: {
          risks: [
            {
              id: "risk-1",
              title: "Customer proof",
              decision_question: "Is production adoption verified?",
            },
          ],
        },
        research_tasks: {
          tasks: [
            {
              id: "task-1",
              title: "Customer depth",
              prompt: "Verify production deployment.",
              priority: "high",
              status: "done",
              answer: "Deployment depth remains unproven.",
              confidence: "low",
              supporting_evidence: [
                {
                  filename: "customer-note.txt",
                  locator: "Page 4",
                  excerpt: "Only pilots were confirmed.",
                  confidence: "medium",
                },
              ],
              contradicting_evidence: [],
              open_questions: ["Need contracted ARR by customer."],
            },
          ],
        },
        infographic_source_brief: {
          summary: "Use source-backed visuals only.",
          confidence: "medium",
          compact_claims: [
            {
              id: "claim-1",
              claim: "Production adoption is verified.",
              evidence_status: "mixed",
            },
          ],
          missing_evidence: ["Contracted ARR by customer."],
          no_go_claims: ["Do not visualize pilots as production adoption."],
          reviewer_prompts: [
            {
              id: "source-prompt-1",
              prompt: "Choose whether to include pilot logos.",
              required: true,
              status: "needs_review",
            },
          ],
        },
        chart_specs: {
          specs: [
            {
              id: "chart-1",
              title: "Deployment proof ladder",
              purpose: "Separate pilots from production.",
              include_in_final_memo: true,
              information_gaps: ["ARR bridge."],
              reviewer_prompts: [
                {
                  id: "chart-prompt-1",
                  prompt: "Choose visual mode.",
                  required: true,
                  status: "needs_review",
                },
              ],
            },
          ],
        },
        memo_grader: {
          status: "graded",
          completed_report_id: "report-1",
          completed_run_id: "memo-run-1",
          missing_diligence: ["Customer concentration needs proof."],
          rewrite_guidance: ["Tighten the risk framing."],
          lessons_for_future_memo_runs: ["Require source evidence for customer claims."],
          lessons_path: "data/serena_training/generalist/serena_memo_lessons.md",
          source_files_reviewed: ["memo-run-1.md"],
          confidence: "medium",
        },
        memo_packet: "# Packet\n",
      },
    }));
    m.getEvidenceMatrix.mockResolvedValue({
      claim_count: 1,
      claims: [
        {
          claim: "ARR evidence is missing.",
          status: "missing",
          confidence: "low",
          source_coverage: {
            supporting_count: 0,
            contradicting_count: 0,
            missing_count: 1,
          },
          supporting_evidence: [],
          contradicting_evidence: [],
        },
      ],
    });

    wrapper = mountDashboard();
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain("Core Memo Workflow");
    expect(text).toContain("Memo Tools Toolbox");
    expect(text).toContain("Deliverables");
    expect(text).toContain("Review Queue");
    expect(text).toContain("Source Evidence Drawer");
    expect(text).toContain("Source And Evidence Boundaries");
    expect(text).toContain("analysis_session:session-1");
    expect(text).toContain("research_task:task-1");
    expect(text).toContain("memo-run-1");
    expect(text).toContain("customer-note.txt");
    expect(text).toContain("Only pilots were confirmed.");
    expect(text).toContain("Contracted ARR by customer.");
    expect(text).toContain("Customer concentration needs proof.");
    expect(text).toContain("Require source evidence for customer claims.");
    expect(text).toContain("data/uploads/generalist/");
    expect(text).toContain("data/stock_research/");
    expect(text).toContain("excluded");
  });

  it("renders infographic source brief, chart planning metadata, and narrative transitions", async () => {
    m.get.mockResolvedValue(baseSession({
      artifacts: {
        ...baseSession().artifacts,
        infographic_source_brief: {
          summary: "Use source-backed visuals only.",
          confidence: "medium",
          compact_claims: [
            {
              id: "claim-1",
              claim: "Only pilots were confirmed.",
              evidence_status: "partial",
              confidence: "high",
              prohibited_for_visuals: false,
              source_traces: [
                {
                  locator: "customer-note.md",
                  excerpt: "Pilot evidence is documented.",
                  confidence: "high",
                },
              ],
            },
          ],
          numeric_metrics: [
            {
              id: "metric-1",
              label: "Confirmed pilots",
              value: 3,
              unit: "customers",
              period: "2026",
            },
          ],
          missing_evidence: ["Contracted ARR by customer."],
          no_go_claims: ["Do not visualize pilots as production adoption."],
          visual_opportunities: [
            {
              id: "visual-1",
              title: "Pilot-to-production ladder",
              rationale: "Separates pilots from production.",
            },
          ],
          reviewer_prompts: [
            {
              id: "prompt-1",
              prompt: "Choose overlay or text-in-image.",
              required: true,
              resolved_choice: null,
              status: "needs_review",
            },
          ],
        },
        chart_specs: {
          specs: [
            {
              id: "chart-1",
              title: "Deployment proof ladder",
              purpose: "Separate pilots from production adoption.",
              recommended_visual_format: "ladder infographic",
              image_generation_mode: "no_text_overlay",
              source_availability: "partial",
              include_in_final_memo: true,
              final_memo_inclusion_state: "include",
              status: "draft",
              text_overlay_plan: {
                headline: "Pilots are not production",
                callouts: ["Evidence gap remains"],
                safe_copy_length: "Short overlay copy.",
              },
              required_metrics: [
                {
                  id: "metric-arr",
                  label: "Latest ARR",
                  value: null,
                  unit: "USD",
                  source_available: false,
                },
              ],
              information_gaps: ["ARR bridge."],
              reviewer_prompts: [
                {
                  id: "prompt-mode",
                  prompt: "Choose visual mode.",
                  required: true,
                  resolved_choice: null,
                  status: "needs_review",
                },
              ],
              source_traces: [
                {
                  locator: "memo",
                  excerpt: "Production adoption is not yet sourced.",
                  confidence: "medium",
                },
              ],
              design_prompt: {
                composition: "Use a simple adoption ladder.",
              },
            },
          ],
        },
        narrative_hooks: {
          summary: "Source-backed hooks.",
          openings: [
            {
              id: "opening-1",
              text: "Start with deployment proof.",
              tone: "direct",
              confidence: "medium",
              status: "draft",
              overclaiming_risk: "Do not imply ARR is verified.",
              paired_infographic_ids: ["chart-1"],
            },
          ],
          transitions: [
            {
              id: "transition-1",
              text: "The diligence burden shifts from story to proof.",
              tone: "evidence_bridge",
              confidence: "medium",
              status: "draft",
              overclaiming_risk: "Keep as framing.",
            },
          ],
          endings: [
            {
              id: "ending-1",
              text: "Stay conditional until proof arrives.",
              tone: "conditional",
              confidence: "medium",
              status: "draft",
              overclaiming_risk: "Avoid implying a final pass.",
            },
          ],
          selected_opening_id: "opening-1",
          selected_transition_id: "transition-1",
          selected_ending_id: "ending-1",
          reviewer_prompts: [
            {
              id: "narrative-prompt",
              prompt: "Choose tone aggressiveness.",
              required: false,
              resolved_choice: "direct",
              status: "resolved",
            },
          ],
        },
      },
    }));
    wrapper = mountDashboard();
    await flushPromises();

    expect(wrapper.text()).toContain("Only pilots were confirmed.");
    expect(wrapper.text()).toContain("Contracted ARR by customer.");
    expect(wrapper.text()).toContain("Do not visualize pilots as production adoption.");
    expect(wrapper.text()).toContain("Deployment proof ladder");
    expect(wrapper.text()).toContain("no text overlay");
    expect(wrapper.text()).toContain("Pilots are not production");
    expect(wrapper.text()).toContain("Production adoption is not yet sourced.");
    expect(wrapper.text()).toContain("The diligence burden shifts from story to proof.");
    expect(wrapper.text()).toContain("Choose tone aggressiveness.");

    const saveHooks = wrapper.findAll("button")
      .find((button) => button.text().includes("Save hooks"));
    await saveHooks.trigger("click");
    await flushPromises();

    expect(m.patchArtifact).toHaveBeenCalledWith(
      "generalist",
      "narrative_hooks",
      expect.objectContaining({
        selected_transition_id: "transition-1",
        openings: expect.any(Array),
        transitions: expect.any(Array),
        endings: expect.any(Array),
      }),
    );
  });
});
