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
    { name: "strategic_risk_mapper", label: "Strategic Risk Mapper", description: "Generate decision questions.", stage: "core", critical: true, status: "done", input_label: "Pick the questions that deserve diligence.", run_label: "Map risks" },
    { name: "priority_prompt_harness", label: "Risk Prioritizer", description: "Build diligence questions.", stage: "core", critical: true, status: "done", input_label: "Select sources and run only the questions that matter.", run_label: "Build diligence queue" },
    { name: "thesis_spine_builder", label: "Thesis Spine", description: "Draft memo-grade claims.", stage: "core", critical: true, status: "done", input_label: "Edit claims and gates.", run_label: "Draft thesis" },
    { name: "chart_spec_builder", label: "Chart Plan Builder", description: "Build chart plans.", stage: "optional", status: "not_started", run_label: "Plan visuals" },
    { name: "memo_grader", label: "Memo Grader", description: "Grade completed memos.", stage: "after_memo", status: "done", run_label: "Grade memo" },
  ],
  readiness: {
    score: 6,
    total: 7,
    pct: 6 / 7,
    ready_for_approval: true,
    ready_for_memo: false,
    approval_blockers: [],
    gates: [{ id: "thesis", label: "Thesis spine drafted", status: "done" }],
  },
  additional_areas: [],
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

// The app shell loads this list on every page (sidebar, jump menu, Research
// Desk), so it must be an array, and a company page only opens a company
// that is in it.
const companies = [
  { id: "generalist", name: "Generalist", files: [], report_type: "Investment Memo (Late-Stage)" },
  {
    id: "public-ticker",
    name: "Public Ticker Co",
    ticker: "PTCO",
    company_type: "public",
    status: "public",
    files: [],
    trader_snapshot: null,
  },
];

async function mockApi(page) {
  const calls = [];
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "bsh.research.session",
      JSON.stringify({ token: "browser-smoke", expires_at: "2099-01-01T00:00:00Z" }),
    );
    // The first-run welcome tour opens over every page until it is seen.
    window.localStorage.setItem("bsh.welcomeTourSeen", "999");
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
    if (path === "/api/companies") return json(companies);
    if (path === "/api/reports") return json([]);
    if (path === "/api/external/feed") return json([]);
    if (path === "/api/jobs/active") return json([]);
    if (path === "/api/stock-research") return json(stockPayload);
    if (path.startsWith("/api/stock-research/")) return json(stockPayload);
    const company = companies.find((item) => path === `/api/companies/${item.id}`);
    if (company) return json(company);
    if (path === "/api/companies/generalist/memo-analysis") return json(memoSession);
    // Firm-layer lists come back as { items }; the Decisions tab's IC room
    // and comments cards throw on a bare {}.
    if (path.endsWith("/ic/meetings") || path.endsWith("/comments")) return json({ items: [] });
    return json({});
  });
  return calls;
}

// An uncaught exception here nearly always means a mock no longer matches
// what a page reads. Fail on the exception by name: otherwise it surfaces as
// a missing heading, which is how a {} company list kept this file red for
// months.
let pageErrors = [];

test.beforeEach(({ page }) => {
  pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
});

test.afterEach(() => {
  expect(pageErrors).toEqual([]);
});

test("stock research tabs render and source forms submit against mocked API", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/research/stock-research");

  await expect(page.getByRole("heading", { name: "Stock Research" })).toBeVisible();
  await expect(page.getByText("Latest Weekly Aggregate")).toBeVisible();

  await page.getByRole("tab", { name: "Work" }).click();
  await page.getByRole("tab", { name: "Trackers" }).click();
  await expect(page.getByText("AI demand remains the core debate.")).toBeVisible();
  await page.getByRole("tab", { name: "Sources" }).click();
  await expect(page.getByText("Transcript")).toBeVisible();
  await page.getByRole("tab", { name: "Runs" }).click();
  await expect(page.getByText("NVIDIA tracker report")).toBeVisible();
  await expect(page.getByText("Run history")).toBeVisible();
  await page.getByRole("tab", { name: "Pulse" }).click();
  await page.getByRole("tab", { name: "Weekly Aggregate" }).click();
  await expect(page.getByText("AI infrastructure demand remains the key signal.")).toBeVisible();
  await page.getByRole("tab", { name: "Strategy Map" }).click();
  await expect(page.getByText("Demand conflicts with supply-chain checks.")).toBeVisible();
  await page.getByRole("tab", { name: "Work" }).click();
  await page.getByRole("tab", { name: "Deliverables" }).click();
  await expect(page.getByText("NVIDIA tracker report")).toBeVisible();
  await page.getByRole("tab", { name: "Review", exact: true }).click();
  await page.getByRole("tab", { name: "Review Queue" }).click();
  await expect(page.getByText("No official source attached")).toBeVisible();
  await page.getByRole("tab", { name: "Evaluation" }).click();
  await expect(page.getByText("42 ms")).toBeVisible();
  await page.getByRole("tab", { name: "Hypotheses" }).click();
  await expect(page.getByText("AI demand remains resilient.")).toBeVisible();
  await expect(page.getByText("forward_live")).toBeVisible();

  await page.getByRole("tab", { name: "Work" }).click();
  await page.getByRole("tab", { name: "Sources" }).click();
  await page.getByPlaceholder("Link title").fill("Company transcript");
  await page.getByPlaceholder("https://source.example").fill("https://example.com/transcript");
  await page.getByPlaceholder("Source notes").fill("Official transcript notes.");
  await page.getByRole("button", { name: "Attach Link" }).click();

  await page.getByPlaceholder("Note title").fill("Analyst note");
  await page.getByPlaceholder("Analyst note").fill("Manual tracker note.");
  await page.getByRole("button", { name: "Add Note" }).click();

  await page.getByPlaceholder("File title").fill("Uploaded transcript");
  // The app shell keeps hidden file inputs of its own (toolbar Add, pitch-deck
  // intake), so target the one in this page's "Assign Source" panel.
  const sourcePanel = page.locator("aside").filter({ has: page.getByRole("heading", { name: "Assign Source" }) });
  await sourcePanel.locator("input[type='file']").setInputFiles({
    name: "transcript.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("source text"),
  });
  await page.getByRole("button", { name: "Upload File" }).click();

  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/link").length).toBe(1);
  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/note").length).toBe(1);
  await expect.poll(() => calls.filter((call) => call.path === "/api/stock-research/sources/upload").length).toBe(1);
});

test("company desk IC prep loads the memo session and runs an analysis tool", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/research/research/generalist?section=decisions");

  await expect(page.getByRole("heading", { level: 1, name: "Generalist" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Decisions", exact: true })).toHaveClass(/is-active/);

  // IC prep stays collapsed until asked, because loading it opens a memo
  // session on the server.
  const icPrep = page.locator(".mac-card").filter({ has: page.getByText("IC prep", { exact: true }) });
  await expect(icPrep.getByText("Readiness gates, risk cards and analysis tools")).toBeVisible();
  expect(calls.some((call) => call.path === "/api/companies/generalist/memo-analysis")).toBe(false);

  await icPrep.getByRole("button", { name: "Load IC prep" }).click();
  await expect(icPrep.getByText("6/7 gates")).toBeVisible();
  await expect(icPrep.getByText("Thesis spine drafted")).toBeVisible();
  await expect(icPrep.getByText("Risk cards (1, 1 open)")).toBeVisible();
  await expect(icPrep.getByText("Customer proof")).toBeVisible();
  await expect(icPrep.getByText("Strategic Risk Mapper")).toBeVisible();

  // Chart Plan Builder is the only tool not run yet, so it holds the one "Run".
  await icPrep.getByRole("button", { name: "Run", exact: true }).click();
  await expect.poll(() =>
    calls.filter((call) =>
      call.method === "POST" && call.path === "/api/companies/generalist/memo-analysis/tools/chart_spec_builder/run",
    ).length,
  ).toBe(1);
  await expect(page).toHaveURL(/\/research\/research\/generalist\?section=decisions$/);
});

test("an old analysis deep link opens a public ticker's dossier on Decisions", async ({ page }) => {
  await mockApi(page);
  await page.goto("/research/research/public-ticker?tab=analysis");

  await expect(page.getByRole("heading", { level: 1, name: "Public Ticker Co" })).toBeVisible();
  await expect(page.getByText("PTCO · Public")).toBeVisible();
  // ?tab=analysis is where the jobs rail used to send Memo Studio jobs. Their
  // tools and risk research run and report in IC prep, under Decisions, as
  // on the Mac.
  await expect(page.getByRole("button", { name: "Decisions", exact: true })).toHaveClass(/is-active/);
  await expect(page.getByText("IC prep", { exact: true })).toBeVisible();
  // The desk rewrites the old tab to its own ?section= and keeps the path.
  await expect(page).toHaveURL(/\/research\/research\/public-ticker\?section=decisions$/);
});

test("the toolbar's Add uploads to the open desk, opens Files and lists the file", async ({ page }) => {
  await mockApi(page);
  const uploaded = [];
  let documentLoads = 0;
  const documentRow = (id, filename) => ({
    id: `background_documents:${id}`,
    backend: "background_documents",
    record_id: id,
    title: filename,
    filename,
    kind: "pdf",
    type_badge: "PDF",
    category: "company_materials",
    source_class: "company material",
    language: "en",
    status: "ready",
    captured_at: "2026-09-21T12:00:00Z",
    provenance: { origin: "Upload", source_class: "company material" },
    source_refs: [],
    source_traces: [],
    source_trace_count: 0,
    editable_metadata: true,
    use_in_report: true,
    use_in_report_locked: false,
    record: { id, filename, kind: "pdf", size_bytes: 1024 },
  });
  // Registered after mockApi, so these answer first.
  await page.route("**/api/companies/generalist/research-files", (route) => {
    const id = `upload-${uploaded.length + 1}`;
    uploaded.push(id);
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id }) });
  });
  await page.route("**/api/companies/generalist/documents", (route) => {
    documentLoads += 1;
    const rows = uploaded.map((id, i) => documentRow(id, `term-sheet-${i + 1}.pdf`));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        groups: [{ id: "company_materials", rows }],
        categories: [],
        source_classes: [],
        filters: { languages: [], statuses: [] },
        unresolved_intake_count: 0,
      }),
    });
  });
  const addFile = async (name) => {
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "Add to Generalist" }).click();
    await (await chooser).setFiles({ name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7") });
  };

  await page.goto("/research/research/generalist");
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveClass(/is-active/);

  // From Overview, the upload lands on Files with the new file listed.
  await addFile("term-sheet-1.pdf");
  await expect(page.getByRole("button", { name: "Files", exact: true })).toHaveClass(/is-active/);
  await expect(page.getByText("term-sheet-1.pdf").first()).toBeVisible();
  await expect(page).toHaveURL(/\/research\/research\/generalist\?section=files$/);

  // With Files already open, the next upload reloads the list in place.
  const loadsBefore = documentLoads;
  await addFile("term-sheet-2.pdf");
  await expect(page.getByText("term-sheet-2.pdf").first()).toBeVisible();
  expect(documentLoads).toBeGreaterThan(loadsBefore);
  expect(uploaded).toEqual(["upload-1", "upload-2"]);

  // The tab is in the URL, so Back returns to the tab before the upload.
  await page.goBack();
  await expect(page).toHaveURL(/\/research\/research\/generalist$/);
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toHaveClass(/is-active/);
});
