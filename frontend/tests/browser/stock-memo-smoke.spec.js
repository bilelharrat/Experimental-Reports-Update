import { expect, test } from "@playwright/test";

const stockPayload = {
  summary: {
    tracker_count: 2,
    tracker_counts_by_type: { macro: 1, industry: 0, company: 1 },
    due_count: 1,
    stale_count: 0,
    open_review_item_count: 1,
    missing_source_warning_count: 1,
    work_product_count: 1,
    source_count: 1,
    doctor_error_count: 0,
    doctor_warning_count: 0,
    run_ledger_count: 2,
  },
  trackers: [
    {
      id: "us-macro",
      type: "macro",
      display_name: "US Macro Tracker",
      status: "active",
      is_stale: false,
      latest_thesis: "Liquidity is watchful.",
      freshness_policy: {},
    },
    {
      id: "nvidia",
      type: "company",
      display_name: "NVIDIA",
      status: "active",
      is_stale: false,
      latest_thesis: "AI demand remains the core debate.",
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
      created_at: "2026-06-14T12:00:00Z",
      chunks: [{ excerpt: "Management commentary excerpt." }],
    },
  ],
  runs: [
    {
      run_id: "run-1",
      tracker_id: "nvidia",
      tracker_name: "NVIDIA",
      status: "done",
      source_count: 1,
      confidence: 0.75,
      thesis: "Company AI demand remains the core debate.",
      report_markdown: "# NVIDIA tracker report",
      created_at: "2026-06-14T12:00:00Z",
      source_traces: [{ source_id: "src-1", source_title: "Transcript", locator: "p.1", excerpt: "Management commentary excerpt." }],
      knowledge_updates: [{ id: "ku-1", text: "Prefer source manifests.", review_status: "open" }],
    },
  ],
  latest_aggregate: {
    period_id: "2026-06-08_to_2026-06-14",
    included_tracker_run_ids: ["nvidia:run-1"],
    modules: {
      macro: [{ tracker_id: "us-macro", thesis: "Macro liquidity is watchful.", source_traces: [] }],
      industry: [],
      company: [{ tracker_id: "nvidia", thesis: "Company AI demand remains the core debate.", source_traces: [{ source_title: "Transcript" }] }],
      cross_tracker: [],
      watchlist: [],
    },
    excluded_tracker_warnings: [],
    missing_source_warnings: [{ tracker_id: "nvidia", description: "Official transcript missing." }],
    ranked_signals: [{ id: "sig-1", source_tracker_id: "nvidia", observation: "AI infrastructure demand remains the key signal.", direction: "watch", source_traces: [{ source_title: "Transcript", locator: "p.1", excerpt: "Management commentary excerpt." }] }],
    markdown: "# Weekly aggregate",
    html_blocks: [{ kind: "markdown", body: "HTML-ready block." }],
  },
  latest_strategy_map: {
    period_id: "2026-06-08_to_2026-06-14",
    nodes: [{ id: "node-ai", label: "AI infrastructure", posture: "watch", qualitative_action: "monitor", source_traces: [{ source_title: "Transcript", locator: "p.1", excerpt: "Demand remains strong." }] }],
    edges: [{ id: "edge-ai", from: "node-ai", to: "node-supply", relationship: "supply-chain link", source_traces: [{ source_title: "Transcript", locator: "p.2", excerpt: "Supply timing matters." }] }],
    diff: [{ id: "node-ai", label: "AI infrastructure", state: "new" }],
    contradictions: [{ id: "contra-1", description: "Demand conflicts with supply-chain checks.", source_traces: [{ source_title: "Transcript", locator: "p.3" }] }],
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
      source_trace_count: 1,
      confidence: 0.75,
      updated_at: "2026-06-14T12:00:00Z",
      export_paths: { markdown: "report.md" },
    },
  ],
  review_items: [
    {
      id: "missing:nvidia:run-1",
      title: "No official source attached",
      item_type: "missing_source",
      status: "open",
      severity: "medium",
      artifact_id: "tracker_run:nvidia:run-1",
      source_refs: [{ source_title: "Transcript", locator: "p.1" }],
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
        source_quality: { average: 0.8 },
        evidence_coverage: 0.7,
        contradiction_count: 0,
        missing_source_count: 1,
        reviewer_score: null,
        reviewer_scores: {},
      },
    ],
    run_ledger: [
      {
        ledger_id: "stock_research:stock_tracker:nvidia:run-1",
        workspace: "stock_research",
        job_kind: "stock_tracker",
        artifact_id: "tracker_run:nvidia:run-1",
        tracker_id: "nvidia",
        run_id: "run-1",
        status: "done",
        updated_at: "2026-06-14T12:00:00Z",
        duration_ms: 42,
        source_count: 1,
        evidence_coverage: 0.7,
        estimated_cost_usd: 0,
      },
    ],
  },
  hypotheses: {
    summary: {
      vintage_count: 1,
      hypothesis_count: 1,
      pending_count: 0,
      training_eligible_count: 1,
    },
    vintages: [
      {
        vintage_date: "2026-06-14",
        vintage_kind: "forward_live",
        hypothesis_count: 1,
        outcome_count: 1,
        pending_count: 0,
        training_eligible_count: 1,
      },
    ],
    rows: [
      {
        hypothesis_id: "hyp-live",
        vintage_date: "2026-06-14",
        vintage_kind: "forward_live",
        ticker: "NVDA",
        claim: "AI demand remains resilient.",
        direction: "bullish",
        outcome: {
          directional_result: "hit",
          relative_return_pct: 8,
          eligible_for_training: true,
        },
      },
    ],
    calibration: [{ eligible_outcome_count: 1 }],
  },
};

const memoSession = {
  id: "session-1",
  status: "draft",
  company_id: "generalist",
  approved_for_memo: false,
  has_unapproved_work: true,
  completed_memo_runs: [{ id: "report-1", run_id: "memo-run-1" }],
  tools: [
    { name: "chart_spec_builder", label: "Chart Spec Builder", description: "Build chart plans.", status: "not_started" },
    { name: "memo_grader", label: "Memo Grader", description: "Grade completed memos.", status: "done" },
  ],
  readiness: {
    score: 7,
    total: 9,
    pct: 7 / 9,
    ready_for_approval: false,
    ready_for_memo: false,
    approval_blockers: [{ id: "chart-gap", kind: "additional_area", label: "Chart data incomplete" }],
    gates: [{ id: "thesis", label: "Thesis spine drafted", status: "done" }],
  },
  additional_areas: [{ id: "chart-gap", severity: "medium", area: "Chart data incomplete", why_it_matters: "Customer evidence is missing.", status: "open" }],
  artifacts: {
    input_manifest: { research_files: [{ id: "source-1", filename: "pitchbook.pdf" }] },
    strategic_risks: { risks: [{ id: "risk-1", title: "Customer proof", status: "open", decision_question: "Is production adoption verified?", why_it_matters: "It gates the memo." }] },
    risk_priorities: { priorities: [{ risk_id: "risk-1", rank: 1, selected: true }] },
    thesis_spine: { approved: true, investment_highlights: [{ id: "h1", claim: "Source-backed upside.", detail: "Evidence detail." }], investment_risks: [], top_gating_questions: [] },
    research_tasks: { tasks: [{ id: "task-1", title: "Deployment proof", priority: "high", status: "not_started", source_type: "research", prompt: "Check deployment evidence.", selected_source_ids: ["source-1"], answer: "Deployment depth remains unproven.", confidence: "medium", supporting_evidence: [{ filename: "customer-note.md", excerpt: "Only pilots were confirmed." }], open_questions: ["Need contracted ARR by customer."] }] },
    infographic_source_brief: { summary: "Use source-backed visuals only.", confidence: "medium", compact_claims: [{ id: "claim-1", claim: "Only pilots were confirmed.", evidence_status: "partial", confidence: "high", source_traces: [{ locator: "customer-note.md", excerpt: "Pilot evidence is documented." }] }], missing_evidence: ["Contracted ARR by customer."], no_go_claims: ["Do not visualize pilots as production adoption."], reviewer_prompts: [{ id: "prompt-1", prompt: "Choose overlay mode.", required: true }] },
    chart_specs: { specs: [{ id: "chart-1", title: "Deployment proof ladder", purpose: "Separate pilots from production.", source_availability: "partial", include_in_final_memo: true, reviewer_prompts: [{ id: "prompt-2", prompt: "Choose visual mode.", required: true }], source_traces: [{ locator: "memo", excerpt: "Production adoption is not yet sourced." }] }] },
    narrative_hooks: { selected_opening_id: "opening-1", selected_ending_id: "ending-1", openings: [{ id: "opening-1", text: "Start with deployment proof.", tone: "direct" }], endings: [{ id: "ending-1", text: "Stay conditional.", tone: "conditional" }], reviewer_prompts: [{ id: "prompt-3", prompt: "Choose tone aggressiveness.", resolved_choice: "direct" }] },
    benchmark_dashboard: { summary: "Benchmark summary", public_comps: [{ id: "comp-1", company: "Rockwell", ticker: "ROK", confidence: "medium" }], benchmark_gaps: ["ARR bridge."], must_prove: ["Production adoption."] },
    memo_grader: { status: "graded", completed_report_id: "report-1", confidence: "medium", lessons_for_future_memo_runs: ["Require source traces."] },
    memo_packet: "# Packet",
  },
};

const evidenceMatrix = {
  claim_count: 2,
  claims: [
    {
      claim: "Deployment evidence is mixed.",
      status: "mixed",
      confidence: "medium",
      source_coverage: { supporting_count: 1, contradicting_count: 1, missing_count: 0 },
      supporting_evidence: [{ task_id: "task-1", task_title: "Deployment proof", locator: "p.2", excerpt: "Only pilots were confirmed." }],
      contradicting_evidence: [],
    },
    {
      claim: "ARR evidence is missing.",
      status: "missing",
      confidence: "low",
      source_coverage: { supporting_count: 0, contradicting_count: 0, missing_count: 1 },
      supporting_evidence: [],
      contradicting_evidence: [],
    },
  ],
};

const memoRunLedger = [
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
    source_count: 1,
    evidence_coverage: 1,
    estimated_cost_usd: 0,
  },
];

async function mockApi(page) {
  const calls = [];
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "bsh.research.session",
      JSON.stringify({ token: "browser-smoke", expires_at: "2099-01-01T00:00:00Z" }),
    );
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    calls.push({ method: request.method(), path });
    const json = (body) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (path === "/api/auth/me") return json({ email: "browser@example.com" });
    if (path === "/api/reports") return json([]);
    if (path === "/api/external/feed") return json([]);
    if (path === "/api/external/hormuz") return json([]);
    if (path === "/api/jobs/active") return json([]);
    if (path === "/api/stock-research") return json(stockPayload);
    if (path.startsWith("/api/stock-research/")) return json(stockPayload);
    if (path === "/api/companies/generalist") {
      return json({ id: "generalist", name: "Generalist", files: [], report_type: "Investment Memo (Late-Stage)" });
    }
    if (path === "/api/companies/public-ticker") {
      return json({
        id: "public-ticker",
        name: "Public Ticker Co",
        ticker: "PTCO",
        company_type: "public",
        status: "public",
        files: [],
        trader_snapshot: null,
      });
    }
    if (path === "/api/options") {
      return json({ report_types: ["Investment Memo (Late-Stage)"], audiences: ["Internal"], languages: ["en"] });
    }
    if (path === "/api/companies/generalist/threads") return json([]);
    if (path === "/api/companies/public-ticker/threads") return json([]);
    if (path === "/api/companies/generalist/memo-analysis") return json(memoSession);
    if (path === "/api/companies/generalist/memo-analysis/run-ledger") return json(memoRunLedger);
    if (path === "/api/companies/generalist/evidence-matrix") return json(evidenceMatrix);
    if (path.startsWith("/api/companies/generalist/memo-analysis/")) return json(memoSession);
    return json({});
  });
  return calls;
}

test("stock research tabs render and source forms submit against mocked API", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/research/stock-research");

  await expect(page.getByRole("heading", { name: "Stock Research" })).toBeVisible();
  await expect(page.getByText("Latest Weekly Aggregate")).toBeVisible();

  await page.getByRole("button", { name: "Trackers" }).click();
  await expect(page.getByText("AI demand remains the core debate.")).toBeVisible();
  await page.getByRole("button", { name: "Sources" }).click();
  await expect(page.getByText("Transcript")).toBeVisible();
  await page.getByRole("button", { name: "Runs" }).click();
  await expect(page.getByText("NVIDIA tracker report")).toBeVisible();
  await expect(page.getByText("Normalized Run Ledger")).toBeVisible();
  await page.getByRole("button", { name: "Weekly Aggregate" }).click();
  await expect(page.getByText("AI infrastructure demand remains the key signal.")).toBeVisible();
  await page.getByRole("button", { name: "Strategy Map" }).click();
  await expect(page.getByText("Demand conflicts with supply-chain checks.")).toBeVisible();
  await page.getByRole("button", { name: "Work Products" }).click();
  await expect(page.getByText("NVIDIA tracker report")).toBeVisible();
  await page.getByRole("button", { name: "Review Queue" }).click();
  await expect(page.getByText("No official source attached")).toBeVisible();
  await page.getByRole("button", { name: "Evaluation" }).click();
  await expect(page.getByText("42 ms")).toBeVisible();
  await page.getByRole("button", { name: "Hypotheses" }).click();
  await expect(page.getByText("AI demand remains resilient.")).toBeVisible();
  await expect(page.getByText("forward_live")).toBeVisible();

  await page.getByRole("button", { name: "Sources" }).click();
  await page.getByPlaceholder("Link title").fill("Company transcript");
  await page.getByPlaceholder("https://source.example").fill("https://example.com/transcript");
  await page.getByPlaceholder("Source notes").fill("Official transcript notes.");
  await page.getByRole("button", { name: "Attach Link" }).click();

  await page.getByPlaceholder("Note title").fill("Analyst note");
  await page.getByPlaceholder("Analyst note").fill("Manual tracker note.");
  await page.getByRole("button", { name: "Add Note" }).click();

  await page.getByPlaceholder("File title").fill("Uploaded transcript");
  await page.locator("input[type='file']").setInputFiles({
    name: "transcript.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("source text"),
  });
  await page.getByRole("button", { name: "Upload File" }).click();

  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/link").length).toBe(1);
  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/note").length).toBe(1);
  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/upload").length).toBe(1);
});

test("memo tools analysis route renders panels and submits a mocked task action", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/research/research/generalist?tab=analysis");

  await expect(page.getByRole("heading", { name: "Memo Studio" })).toBeVisible();
  await expect(page.getByText("Memo Tools Toolbox")).toBeVisible();
  await expect(page.getByText("Memo Run Ledger")).toBeVisible();
  await expect(page.getByText("Deployment depth remains unproven.").first()).toBeVisible();
  await expect(page.getByText("Deployment evidence is mixed.")).toBeVisible();
  await expect(page.getByText("Choose visual mode.").first()).toBeVisible();
  await expect(page.getByText("Require source traces.").first()).toBeVisible();

  await page.getByRole("button", { name: "Run selected" }).click();
  await expect.poll(() =>
    calls.filter((call) => call.path === "/api/companies/generalist/memo-analysis/research-tasks/run-selected").length,
  ).toBe(1);
  await expect(page).toHaveURL(/\/research\/research\/generalist\?tab=analysis/);
});

test("public ticker analysis deep link hides memo tools", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/research/research/public-ticker?tab=analysis");

  await expect(page.getByText("Public Ticker Co")).toBeVisible();
  await expect(page.getByRole("button", { name: "Memo Studio" })).toHaveCount(0);
  await expect(page.getByText("Memo Tools Toolbox")).toHaveCount(0);
  await expect(page).toHaveURL(/\/research\/research\/public-ticker$/);
  expect(calls.some((call) => call.path.includes("/memo-analysis"))).toBe(false);
});
