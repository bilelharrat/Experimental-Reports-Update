import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { ref } from "vue";
import ReportCustomizerModal from "../src/components/ReportCustomizerModal.vue";
import { setAppLanguage } from "../src/state.js";

const apiMock = vi.hoisted(() => ({
  generateReport: vi.fn(),
  studioInvestigate: vi.fn(),
  listCompanyDocuments: vi.fn(),
  workspaceSettings: vi.fn(),
  reportReadiness: vi.fn(),
  reportEstimates: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    generateReport: apiMock.generateReport,
    studioInvestigate: apiMock.studioInvestigate,
    listCompanyDocuments: apiMock.listCompanyDocuments,
    workspaceSettings: apiMock.workspaceSettings,
    reportReadiness: apiMock.reportReadiness,
    reportEstimates: apiMock.reportEstimates,
  },
  withApiToken: (url) => url,
}));

// GET /api/reports/readiness for a company that is ready on Claude.
function readyFor(companyId, patch = {}) {
  return {
    engine: "claude",
    ready: true,
    blockers: [],
    warnings: [],
    suggest_engine: null,
    company: { id: companyId, exists: true, name: companyId, real_name: true },
    engines: { claude: { available: true, limited: false, limit: null }, gemini: { available: true } },
    checked_at: "2026-09-22T23:48:25+00:00",
    ...patch,
  };
}

// GET /api/reports/estimates as the live server answered on 2026-09-22.
const ESTIMATES = {
  min_samples: 3,
  cost_basis: "api_equivalent",
  cost_note:
    "API-equivalent cost reported by the engine. Claude runs use the subscription and draw on its weekly allowance.",
  estimates: [
    {
      report_type: "Buffett Investment Memo",
      model_quality: "best",
      structure_mode: "full",
      engine: "claude",
      samples: 8,
      duration_ms: { median: 453707.5, min: 320913.0, max: 730229.0 },
      cost_usd: { median: 2.525, min: 1.1361, max: 3.0968 },
      cost_samples: 8,
      unpriced: false,
      cost_basis: "api_equivalent",
    },
    {
      report_type: "Investment Memo (Late-Stage)",
      model_quality: "best",
      structure_mode: "full",
      engine: "claude",
      samples: 5,
      duration_ms: { median: 1487133.0, min: 1159304.0, max: 2341864.0 },
      cost_usd: { median: 10.1076, min: 6.088, max: 17.6073 },
      cost_samples: 5,
      unpriced: false,
      cost_basis: "api_equivalent",
    },
  ],
};

// One analysed document, the shape evidence_store.list_documents returns.
const ANALYSED_DOC = {
  record_id: "an1",
  backend: "background_documents",
  title: "deck_analysis.md",
  filename: "deck_analysis.md",
  analysis_of: "src1",
  uploaded_at: "2026-09-15T10:00:00Z",
};

function mountModal(props = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: { template: "<div />" } },
      { path: "/research/:companyId", name: "research", component: { template: "<div />" } },
    ],
  });

  const mockCompanies = ref([
    { id: "nvda", name: "NVIDIA Corp.", ticker: "NVDA", sector: "Semiconductors" },
    { id: "aapl", name: "Apple Inc.", ticker: "AAPL", sector: "Consumer Tech" },
  ]);

  return mount(ReportCustomizerModal, {
    props: {
      open: true,
      initialCompanyId: "nvda",
      ...props,
    },
    global: {
      plugins: [router],
      provide: {
        workspaceCompanies: mockCompanies,
      },
      stubs: {
        Monogram: { template: '<div class="monogram-stub" />' },
      },
    },
  });
}

const buttonWith = (wrapper, text) =>
  wrapper.findAll("button").find((b) => b.text().includes(text));

async function launch(wrapper) {
  await wrapper.get('[data-testid="customizer-launch"]').trigger("click");
  await flushPromises();
}

describe("ReportCustomizerModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.listCompanyDocuments.mockResolvedValue({
      groups: [{ id: "uploaded-documents", rows: [ANALYSED_DOC] }],
    });
    // Settings before the template field existed: no memo_template at all,
    // which reads as the server's default, the IC template.
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportReadiness.mockImplementation((companyId) => Promise.resolve(readyFor(companyId)));
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
  });

  afterEach(() => setAppLanguage("en"));

  it("renders modal with company info and default blueprint tab", async () => {
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.text()).toContain("NVIDIA Corp.");
    expect(wrapper.text()).toContain("NVDA");
    expect(wrapper.text()).toContain("Blueprint & Framing");
    expect(wrapper.text()).toContain("Auto-Stage Memo");
    expect(wrapper.text()).toContain("Buffett-Method Memo");
    // The tagline is built from the choices, not from invented page counts.
    const tagline = wrapper.get('[data-testid="customizer-tagline"]').text();
    expect(tagline).toBe("Auto-Stage Memo · Internal IC · IC template · Brief · Autonomous");
    expect(tagline).not.toMatch(/\dp\b/);
  });

  it("switches tabs between blueprint, engine, and evidence", async () => {
    const wrapper = mountModal();
    const navButtons = wrapper.findAll("nav button");
    expect(navButtons).toHaveLength(3);

    // Click Engine & Quality tab
    await navButtons[1].trigger("click");
    expect(wrapper.text()).toContain("Interactive Studio Review");
    expect(wrapper.text()).toContain("Best Frontier");

    // Click Evidence Sources tab — it lists this company's analysed
    // documents, not a fixed menu of source categories.
    await navButtons[2].trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Evidence Repository Attachments");
    expect(wrapper.text()).toContain("deck_analysis.md");
  });

  it("offers no control the pipeline cannot receive", async () => {
    // The Directives & Focus tab was removed because launchReport sends
    // company_id, report_type, audience, language, report_mode and quality
    // and nothing else — a steering box, diligence pillars and a sector
    // picker all changed exactly nothing. The sector lens also competed
    // with the live company type.
    const wrapper = mountModal();
    for (const gone of [
      "Directives & Focus",
      "Analyst Steering Instructions",
      "Strategic Diligence Pillars",
      "Moat Durability",
      "Sector-Specific Diligence Lens",
      "Enterprise B2B SaaS",
    ]) {
      expect(wrapper.text()).not.toContain(gone);
    }
    expect(wrapper.find("textarea").exists()).toBe(false);
  });

  it("launches studio investigation when Interactive Studio Review is selected", async () => {
    apiMock.studioInvestigate.mockResolvedValue({ session_id: "sess_123" });
    const wrapper = mountModal();

    // One-Click is the default now, so this mode has to be chosen.
    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");
    await buttonWith(wrapper, "Interactive Studio Review").trigger("click");

    const launchBtn = wrapper.get('[data-testid="customizer-launch"]');
    expect(launchBtn.text()).toBe("Launch Studio Investigation for NVIDIA Corp.");
    await launch(wrapper);

    expect(apiMock.studioInvestigate).toHaveBeenCalledWith({
      company_id: "nvda",
      report_type: "Investment Report (Auto)",
    });
    expect(wrapper.emitted("created")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("defaults to bilingual and shows the standard memo's one length, disabled", async () => {
    // memo_prep writes an English and a Chinese docx on every run, and the
    // standard memo has a single structure: neither control pretends.
    apiMock.workspaceSettings.mockResolvedValue({
      memo_template: "standard",
      memo_template_effective: "standard",
      preferences: {},
    });
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.text()).toContain("Bilingual (EN + ZH)");
    expect(wrapper.get('[data-testid="customizer-launch"]').text()).toBe(
      "Generate Research Memo for NVIDIA Corp.",
    );

    const locked = wrapper.get('[data-testid="length-locked"]');
    expect(locked.attributes("disabled")).toBeDefined();
    expect(locked.text()).toContain("Standard (5 sections)");
    expect(locked.text()).toContain("About 6,000–9,000 words including tables.");
    expect(wrapper.get('[data-testid="length-lock-reason"]').text()).toContain("founder's IC template");
    expect(wrapper.find('[data-testid="length-modes"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain("40+ pages");

    const disabled = wrapper
      .findAll("button")
      .filter((b) => b.attributes("disabled") !== undefined)
      .map((b) => b.text());
    expect(disabled.some((label) => label.includes("English only"))).toBe(true);
    expect(disabled.some((label) => label.includes("中文 only"))).toBe(true);
  });

  it("only ever sends report types and audiences the API accepts, and never a placeholder type", async () => {
    // The modal used to send its own slugs ("memo_late_stage", "internal"),
    // so every launch came back 400 Invalid report_type. These lists are
    // server/api.py REPORT_TYPES and AUDIENCES verbatim.
    const REPORT_TYPES = [
      "Investment Report (Auto)",
      "Investment Memo (Late-Stage)",
      "Buffett Investment Memo",
      "Background",
      "Financial Analysis",
      "Market Analysis",
    ];
    const PLACEHOLDER_TYPES = ["Financial Analysis", "Market Analysis", "Background"];
    const AUDIENCES = ["LP", "Assistant", "Partner", "Internal"];
    apiMock.generateReport.mockResolvedValue({ id: "rep_1" });

    const wrapper = mountModal();
    await flushPromises();
    const enabled = ["auto", "investment_memo_late_stage", "buffett_memo"];
    for (const id of enabled) {
      apiMock.generateReport.mockClear();
      await wrapper.get(`[data-testid="archetype-${id}"]`).trigger("click");
      await launch(wrapper);
      const sent = apiMock.generateReport.mock.calls[0]?.[0];
      expect(REPORT_TYPES).toContain(sent.report_type);
      expect(AUDIENCES).toContain(sent.audience);
    }

    // The three placeholder types are shown, disabled, and cannot be chosen.
    for (const id of ["deep_dive", "market_analysis", "background"]) {
      const card = wrapper.get(`[data-testid="archetype-${id}"]`);
      expect(card.attributes("disabled")).toBeDefined();
      expect(card.text()).toContain("Not available yet");
      apiMock.generateReport.mockClear();
      await card.trigger("click");
      await launch(wrapper);
      const sent = apiMock.generateReport.mock.calls[0]?.[0];
      expect(PLACEHOLDER_TYPES).not.toContain(sent?.report_type);
    }
  });

  it("says what each audience produces, and that the IC memo stays inside BSH", async () => {
    const wrapper = mountModal();
    const text = wrapper.text();
    expect(text).toContain("The LP memo, plus an internal IC decision memo that never leaves BSH.");
    expect(text).toContain("The IC memo is one extra paid call.");
    expect(text).toContain("The LP memo only");
    expect(text).toContain("No IC memo, and no extra call.");
    expect(text).not.toContain("Direct, unvarnished analytical rigor");

    apiMock.generateReport.mockResolvedValue({ id: "rep_lp" });
    await buttonWith(wrapper, "LPs and co-investors").trigger("click");
    await launch(wrapper);
    expect(apiMock.generateReport).toHaveBeenCalledWith(expect.objectContaining({ audience: "LP" }));
  });

  it("locks Memo Studio for blueprints it cannot run", async () => {
    // memo_prep.is_memo_report_type accepts only the auto and late-stage
    // memos, and the studio endpoint rejects the Buffett memo on top.
    const wrapper = mountModal();
    await flushPromises();
    const nav = wrapper.findAll("nav button");
    await nav[1].trigger("click");

    const studioBtn = () => buttonWith(wrapper, "Interactive Studio Review");
    expect(studioBtn().attributes("disabled")).toBeUndefined();

    await nav[0].trigger("click");
    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");
    await nav[1].trigger("click");
    expect(studioBtn().attributes("disabled")).toBeDefined();
  });

  it("locks length and quality for the Buffett memo, with the reason, and hides the template", async () => {
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.find('[data-testid="template-choice"]').exists()).toBe(true);

    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");
    expect(wrapper.find('[data-testid="template-choice"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="length-locked"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="length-lock-reason"]').text()).toBe(
      "Buffett-method memos run at one fixed length and quality.",
    );

    await wrapper.findAll("nav button")[1].trigger("click");
    for (const id of ["balanced", "best", "economy"]) {
      expect(wrapper.get(`[data-testid="quality-${id}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.get('[data-testid="quality-lock-reason"]').text()).toBe(
      "Buffett-method memos run at one fixed length and quality.",
    );

    apiMock.generateReport.mockResolvedValue({ id: "rep_b" });
    await launch(wrapper);
    const sent = apiMock.generateReport.mock.calls[0][0];
    expect(sent.report_type).toBe("Buffett Investment Memo");
    // The template does not apply to a Buffett memo, so none is sent.
    expect(sent).not.toHaveProperty("memo_template");
  });

  it("starts from the workspace's template and switches it for this run only", async () => {
    apiMock.workspaceSettings.mockResolvedValue({
      memo_template: "ic_v2",
      memo_template_effective: "ic_v2",
      preferences: {},
    });
    apiMock.generateReport.mockResolvedValue({ id: "rep_v2" });
    const wrapper = mountModal();
    await flushPromises();

    expect(wrapper.get('[data-testid="template-ic_v2"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-testid="template-default-hint"]').text()).toContain(
      "Workspace default: Founder's IC template",
    );
    // On the IC template the length control is live, and the tagline says so.
    expect(wrapper.find('[data-testid="length-locked"]').exists()).toBe(false);
    await wrapper.get('[data-testid="length-full"]').trigger("click");
    expect(wrapper.get('[data-testid="customizer-tagline"]').text()).toBe(
      "Auto-Stage Memo · Internal IC · IC template · Full IC · Autonomous",
    );
    await launch(wrapper);
    // Untouched, the template is the server's to apply: nothing is sent.
    const first = apiMock.generateReport.mock.calls.at(-1)[0];
    expect(first.report_mode).toBe("full");
    expect(first).not.toHaveProperty("memo_template");

    // Back to the standard memo for one run: the length control locks again.
    await wrapper.setProps({ open: false });
    await wrapper.setProps({ open: true });
    await flushPromises();
    await wrapper.get('[data-testid="template-standard"]').trigger("click");
    expect(wrapper.get('[data-testid="length-locked"]').exists()).toBe(true);
    await launch(wrapper);
    // The standard memo has one length, so the run is filed as full.
    expect(apiMock.generateReport).toHaveBeenLastCalledWith(
      expect.objectContaining({ memo_template: "standard", report_mode: "full" }),
    );
  });

  it("never pins a run to a template when Settings cannot be read", async () => {
    apiMock.workspaceSettings.mockRejectedValue(new Error("offline"));
    apiMock.generateReport.mockResolvedValue({ id: "rep_x" });
    const wrapper = mountModal();
    await flushPromises();
    // Shown as the server's default, and left to the server to apply.
    expect(wrapper.get('[data-testid="template-ic_v2"]').attributes("aria-pressed")).toBe("true");
    await launch(wrapper);
    expect(apiMock.generateReport.mock.calls[0][0]).not.toHaveProperty("memo_template");
  });

  it("opens on no company rather than a silent default, and names the company it will run on", async () => {
    const wrapper = mountModal({ initialCompanyId: null });
    await flushPromises();
    expect(wrapper.text()).toContain("Select Company");
    const launchBtn = wrapper.get('[data-testid="customizer-launch"]');
    expect(launchBtn.attributes("disabled")).toBeDefined();
    expect(launchBtn.text()).toBe("Generate Research Memo");

    // Pick Apple, close, reopen without a company: the pick does not linger.
    await wrapper.findAll("header button")[0].trigger("click");
    await buttonWith(wrapper, "Apple Inc.").trigger("click");
    expect(wrapper.get('[data-testid="customizer-launch"]').text()).toBe(
      "Generate Research Memo for Apple Inc.",
    );
    await wrapper.setProps({ open: false });
    await wrapper.setProps({ open: true });
    await flushPromises();
    expect(wrapper.text()).toContain("Select Company");
    expect(wrapper.get('[data-testid="customizer-launch"]').attributes("disabled")).toBeDefined();
  });

  it("shows a launch error whole instead of one truncated line", async () => {
    const detail =
      "400 Bad Request: Company 'nvda' has no research files yet.\nUpload a deck or run Analyze in the Files tab first.";
    apiMock.generateReport.mockRejectedValue(new Error(detail));
    const wrapper = mountModal();
    await flushPromises();
    await launch(wrapper);
    const banner = wrapper.get('[data-testid="customizer-error"]');
    expect(banner.text()).toContain("Upload a deck or run Analyze in the Files tab first.");
    expect(banner.find("span").classes()).toContain("whitespace-pre-wrap");
    expect(banner.find(".truncate").exists()).toBe(false);
  });

  it("speaks Chinese when the app does", async () => {
    setAppLanguage("zh");
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.text()).toContain("巴菲特方法备忘录");
    expect(wrapper.text()).toContain("暂未开放");
    expect(wrapper.text()).toContain("创始人投委会模板");
    expect(wrapper.text()).toContain("执行简报");
    expect(wrapper.get('[data-testid="customizer-launch"]').text()).toBe("为NVIDIA Corp.生成研究备忘录");
  });

  it("sends only the analysed documents left checked", async () => {
    apiMock.listCompanyDocuments.mockResolvedValue({
      groups: [
        {
          id: "uploaded-documents",
          rows: [
            ANALYSED_DOC,
            { ...ANALYSED_DOC, record_id: "an2", title: "memo_analysis.md" },
          ],
        },
      ],
    });
    apiMock.generateReport.mockResolvedValue({ id: "rep_1" });
    const wrapper = mountModal();
    await flushPromises();

    const navButtons = wrapper.findAll("nav button");
    await navButtons[2].trigger("click");
    await flushPromises();

    // Everything starts checked; uncheck the second document.
    const boxes = wrapper.findAll('input[type="checkbox"]');
    expect(boxes).toHaveLength(2);
    await boxes[1].setValue(false);

    await navButtons[1].trigger("click");
    await buttonWith(wrapper, "One-Click Autonomous").trigger("click");
    await launch(wrapper);

    expect(apiMock.generateReport).toHaveBeenCalledWith(
      expect.objectContaining({ evidence_files: ["an1"] }),
    );
  });

  it("says so plainly when a company has nothing analysed yet", async () => {
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [] });
    const wrapper = mountModal();
    await flushPromises();
    const navButtons = wrapper.findAll("nav button");
    await navButtons[2].trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="customizer-built-from"]').text()).toBe(
      "Web research only: nothing analysed is on file for this company yet. Upload files in the Files tab and run Analyze on them.",
    );
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(0);
  });

  it("launches autonomous report generation when One-Click is selected", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_999", status: "running" });
    const wrapper = mountModal();
    await flushPromises();

    // Switch to Engine tab and select One-Click Autonomous
    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");
    await buttonWith(wrapper, "One-Click Autonomous").trigger("click");
    await launch(wrapper);

    expect(apiMock.generateReport).toHaveBeenCalledWith({
      company_id: "nvda",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      // The IC template's default length.
      report_mode: "compact",
      // Balanced is the default tier: the top model still writes the memo.
      quality: "balanced",
      // Claude is the default engine; the toggle opts a run into Gemini.
      engine: "claude",
      // Nothing deselected, so the run reads the whole research folder.
      evidence_files: null,
      // Run controls at their defaults: no pause, the server's ceiling.
      pause_after_english: false,
      cost_ceiling_usd: null,
      // No template picked here: the server applies the workspace's.
    });
    expect(wrapper.emitted("created")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("sends the run controls: pause after English and a spend ceiling", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_rc" });
    const wrapper = mountModal();
    await flushPromises();
    await wrapper.findAll("nav button")[1].trigger("click");

    const controls = wrapper.get('[data-testid="run-controls"]');
    expect(controls.text()).toContain("Pause after English");
    expect(controls.text()).toContain("Read the English before paying for the Chinese, artifacts and IC memo");
    expect(controls.text()).toContain("Spend ceiling");
    const ceiling = wrapper.get('[data-testid="cost-ceiling"]');
    // The server's default shows as the placeholder, never as a value.
    expect(ceiling.attributes("placeholder")).toBe("60");
    expect(ceiling.element.value).toBe("");

    await wrapper.get('[data-testid="pause-after-english"]').setValue(true);
    await ceiling.setValue("25");
    expect(wrapper.get('[data-testid="customizer-pause-pill"]').text()).toBe("Pauses after English");
    expect(wrapper.get('[data-testid="customizer-estimate"]').text()).toContain("stops at $25");

    await launch(wrapper);
    expect(apiMock.generateReport).toHaveBeenCalledWith(
      expect.objectContaining({ pause_after_english: true, cost_ceiling_usd: 25 }),
    );
  });

  it("sends no ceiling for a blank or impossible amount, and says so", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_rc2" });
    const wrapper = mountModal();
    await flushPromises();
    await wrapper.findAll("nav button")[1].trigger("click");

    const ceiling = wrapper.get('[data-testid="cost-ceiling"]');
    await ceiling.setValue("-3");
    expect(wrapper.get('[data-testid="cost-ceiling-invalid"]').text()).toBe(
      "Enter a positive amount, or leave it blank for the default.",
    );
    expect(wrapper.get('[data-testid="customizer-estimate"]').text()).not.toContain("stops at");
    await launch(wrapper);
    expect(apiMock.generateReport).toHaveBeenLastCalledWith(
      expect.objectContaining({ pause_after_english: false, cost_ceiling_usd: null }),
    );

    await ceiling.setValue("");
    expect(wrapper.find('[data-testid="cost-ceiling-invalid"]').exists()).toBe(false);
  });

  it("locks the run controls while Memo Studio is chosen", async () => {
    const wrapper = mountModal({ initialGenerationMode: "studio_review" });
    await flushPromises();
    expect(wrapper.get('[data-testid="run-controls-lock-reason"]').text()).toContain("Memo Studio runs on Claude");
    expect(wrapper.get('[data-testid="pause-after-english"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="cost-ceiling"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="customizer-pause-pill"]').exists()).toBe(false);
  });

  it("sends the Gemini engine when the toggle is switched", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_1000", status: "running" });
    const wrapper = mountModal();

    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");

    const gemini = wrapper.find('[data-testid="engine-gemini"]');
    expect(gemini.exists()).toBe(true);
    await gemini.trigger("click");

    await buttonWith(wrapper, "One-Click Autonomous").trigger("click");
    await launch(wrapper);

    expect(apiMock.generateReport).toHaveBeenCalledWith(
      expect.objectContaining({ engine: "gemini" }),
    );
  });

  // The quality tiers are Claude model/effort pairs and a Gemini run drops
  // them, so the selector must not look live once Gemini is picked.
  it("disables the quality tiers while Gemini is the engine", async () => {
    const wrapper = mountModal();

    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");

    const tierIds = ["balanced", "best", "economy"];
    for (const id of tierIds) {
      expect(wrapper.find(`[data-testid="quality-${id}"]`).attributes("disabled")).toBeUndefined();
    }

    await wrapper.find('[data-testid="engine-gemini"]').trigger("click");
    for (const id of tierIds) {
      expect(wrapper.find(`[data-testid="quality-${id}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.text()).toContain("Gemini runs one model");

    // Switching back hands the choice straight back.
    await wrapper.find('[data-testid="engine-claude"]').trigger("click");
    for (const id of tierIds) {
      expect(wrapper.find(`[data-testid="quality-${id}"]`).attributes("disabled")).toBeUndefined();
    }
  });

  it("opens on Memo Studio review when the desk asks for a Deep Investigate", async () => {
    const wrapper = mountModal({ open: false });
    expect(wrapper.text()).not.toContain("Studio Paused");

    await wrapper.setProps({ open: true, initialGenerationMode: "studio_review" });
    await flushPromises();

    expect(wrapper.text()).toContain("Studio Paused");
  });

  it("keeps One-Click as the default otherwise", async () => {
    const wrapper = mountModal({ open: false });
    await wrapper.setProps({ open: true });
    await flushPromises();
    expect(wrapper.text()).toContain("Autonomous");
  });
});

// ---------------------------------------------------------------------------
// Before spending: the pre-flight, the estimate, which entity, and what the
// run will be built from (verified.md R35 B/C, G3 FIX 3, G1 FIX 5).
// ---------------------------------------------------------------------------

// Workspace records as GET /api/companies sends them (identity fields from
// the live registry, 2026-09-22).
const WORKSPACE = [
  {
    id: "zainar-inc",
    name: "ZaiNar, Inc.",
    website: "https://zainartech.com",
    logo_domain: "zainartech.com",
    status: "private",
    company_type: "private",
  },
  {
    id: "msft",
    name: "Microsoft Corp",
    legal_name: "Microsoft Corporation",
    ticker: "MSFT",
    exchange: "NASDAQ",
    website: "https://www.microsoft.com",
    status: "public",
    company_type: "public",
  },
  {
    id: "github-inc",
    name: "GitHub",
    legal_name: "GitHub, Inc.",
    disambiguator: "Microsoft subsidiary, developer platform",
    website: "https://github.com",
    parent_company: "Microsoft",
    status: "subsidiary",
    company_type: "private",
  },
  {
    id: "cienet",
    name: "CIeNET Technologies",
    legal_name: "CIeNET Technologies (Beijing) Co., Ltd.",
    parent_company: "ALTEN",
    status: "subsidiary",
  },
  {
    id: "openai-foundation",
    name: "OpenAI Foundation",
    status: "nonprofit",
  },
];

function mountOn(companyId, props = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: { template: "<div />" } },
      { path: "/research/:companyId", name: "research", component: { template: "<div />" } },
    ],
  });
  return mount(ReportCustomizerModal, {
    props: { open: true, initialCompanyId: companyId, ...props },
    global: {
      plugins: [router],
      provide: { workspaceCompanies: ref(WORKSPACE) },
      stubs: { Monogram: { template: '<div class="monogram-stub" />' } },
    },
  });
}

const preflight = (wrapper) => wrapper.find('[data-testid="customizer-preflight"]');
const estimateLine = (wrapper) => wrapper.find('[data-testid="customizer-estimate"]');

// Claude out of usage until an hour from now, Gemini ready.
function claudeLimited(companyId) {
  const resetAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  return readyFor(companyId, {
    ready: false,
    blockers: [
      {
        code: "claude_limited",
        en: "Claude has hit its usage limit.",
        zh: "Claude 已达到使用上限。",
        reset_at: resetAt,
      },
    ],
    suggest_engine: "gemini",
    engines: {
      claude: { available: true, limited: true, limit: { reset_at: resetAt } },
      gemini: { available: true },
    },
  });
}

describe("ReportCustomizerModal pre-flight", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [{ id: "uploaded-documents", rows: [ANALYSED_DOC] }] });
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    apiMock.reportReadiness.mockImplementation((companyId, engine) =>
      Promise.resolve(engine === "gemini" ? readyFor(companyId, { engine: "gemini" }) : claudeLimited(companyId)),
    );
  });

  afterEach(() => setAppLanguage("en"));

  it("says Claude is limited, when it resets, and offers Gemini without switching", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_1" });
    const wrapper = mountOn("zainar-inc");
    await flushPromises();

    expect(apiMock.reportReadiness).toHaveBeenCalledWith("zainar-inc", "claude");
    const row = wrapper.get('[data-testid="preflight-blocker-claude_limited"]');
    expect(row.text()).toContain("Claude has hit its usage limit.");
    expect(row.text()).toMatch(/Resets .+\(in (60 min|1 hr)\.?\)\./);

    // Offered, not done: the engine is still Claude until the analyst clicks.
    await wrapper.findAll("nav button")[1].trigger("click");
    expect(wrapper.get('[data-testid="engine-claude"]').attributes("aria-pressed")).toBe("true");
    await launch(wrapper);
    expect(apiMock.generateReport.mock.calls[0][0].engine).toBe("claude");

    await wrapper.get('[data-testid="preflight-switch-gemini"]').trigger("click");
    await flushPromises();
    expect(apiMock.reportReadiness).toHaveBeenLastCalledWith("zainar-inc", "gemini");
    expect(wrapper.find('[data-testid="preflight-blocker-claude_limited"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="engine-gemini"]').attributes("aria-pressed")).toBe("true");
    await launch(wrapper);
    expect(apiMock.generateReport.mock.calls[1][0].engine).toBe("gemini");
  });

  it("keeps Generate live: the pre-flight is advice, not a gate", async () => {
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    expect(preflight(wrapper).exists()).toBe(true);
    expect(wrapper.get('[data-testid="customizer-launch"]').attributes("disabled")).toBeUndefined();
  });

  it("shows the server's warnings", async () => {
    apiMock.reportReadiness.mockResolvedValue(
      readyFor("zainar-inc", {
        warnings: [
          {
            code: "company_name_unconfirmed",
            en: "The company record has no proper name yet; check it is the right company.",
            zh: "该公司记录尚无正式名称，请确认公司是否正确。",
          },
        ],
      }),
    );
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    expect(wrapper.get('[data-testid="preflight-warning-company_name_unconfirmed"]').text()).toContain(
      "check it is the right company",
    );
  });

  it("never offers Gemini for a Buffett-method memo, which runs on Claude only", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_b" });
    const wrapper = mountOn("msft");
    await flushPromises();
    // Pick Gemini first, then the Buffett memo: the engine locks to Claude.
    await wrapper.findAll("nav button")[1].trigger("click");
    await wrapper.get('[data-testid="engine-gemini"]').trigger("click");
    await wrapper.findAll("nav button")[0].trigger("click");
    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");
    await flushPromises();

    expect(apiMock.reportReadiness).toHaveBeenLastCalledWith("msft", "claude");
    const row = wrapper.get('[data-testid="preflight-blocker-claude_limited"]');
    expect(row.text()).toContain("Buffett-method memos run on Claude only.");
    expect(wrapper.find('[data-testid="preflight-switch-gemini"]').exists()).toBe(false);

    await wrapper.findAll("nav button")[1].trigger("click");
    expect(wrapper.get('[data-testid="engine-gemini"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="engine-claude"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-testid="engine-lock-reason"]').text()).toBe("Buffett-method memos run on Claude only.");
    await launch(wrapper);
    expect(apiMock.generateReport.mock.calls[0][0].engine).toBe("claude");
  });

  it("stays quiet when the readiness check cannot answer", async () => {
    apiMock.reportReadiness.mockRejectedValue(new Error("offline"));
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    expect(preflight(wrapper).exists()).toBe(false);
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    const row = wrapper.get('[data-testid="preflight-blocker-claude_limited"]');
    expect(row.text()).toContain("Claude 已达到使用上限。");
    expect(row.text()).toContain("恢复。");
    expect(wrapper.get('[data-testid="preflight-switch-gemini"]').text()).toBe("改用 Gemini 引擎");
  });
});

describe("ReportCustomizerModal estimate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [] });
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    apiMock.reportReadiness.mockImplementation((companyId) => Promise.resolve(readyFor(companyId)));
  });

  afterEach(() => setAppLanguage("en"));

  it("says there is no estimate at a setting nobody has run", async () => {
    // Auto · Balanced · IC Brief: no finished run has these settings.
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    expect(estimateLine(wrapper).text()).toBe("No runs at this setting yet");
  });

  it("gives the typical time and the API-equivalent cost where there are enough runs", async () => {
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    await wrapper.get('[data-testid="archetype-investment_memo_late_stage"]').trigger("click");
    await wrapper.get('[data-testid="length-full"]').trigger("click");
    await wrapper.findAll("nav button")[1].trigger("click");
    await wrapper.get('[data-testid="quality-best"]').trigger("click");

    const line = estimateLine(wrapper);
    expect(line.text()).toBe(
      "Typically 20–40 min · about $10 API-equivalent, drawn from the Claude weekly allowance · from 5 runs",
    );
    expect(line.attributes("title")).toContain("weekly allowance");
  });

  it("keys a Buffett memo the way its record is stored", async () => {
    // memo_prep keeps no quality or length on a Buffett record, so its
    // runs are filed under best / full whatever the tiers say.
    const wrapper = mountOn("msft");
    await flushPromises();
    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");
    expect(estimateLine(wrapper).text()).toBe(
      "Typically 5–12 min · about $2.53 API-equivalent, drawn from the Claude weekly allowance · from 8 runs",
    );
  });

  it("shows nothing when the estimates cannot be read, and nothing for a Studio run", async () => {
    apiMock.reportEstimates.mockRejectedValue(new Error("offline"));
    const offline = mountOn("zainar-inc");
    await flushPromises();
    expect(estimateLine(offline).exists()).toBe(false);

    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    const studio = mountOn("zainar-inc", { initialGenerationMode: "studio_review" });
    await flushPromises();
    expect(estimateLine(studio).exists()).toBe(false);
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const wrapper = mountOn("msft");
    await flushPromises();
    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");
    expect(estimateLine(wrapper).text()).toBe(
      "通常需 5–12 分钟 · 约 $2.53（API 等价成本，计入 Claude 每周额度） · 基于 8 次运行",
    );
  });
});

describe("ReportCustomizerModal: which entity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [] });
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    apiMock.reportReadiness.mockImplementation((companyId) => Promise.resolve(readyFor(companyId)));
  });

  afterEach(() => setAppLanguage("en"));

  it("names the legal entity, what it is and its domain in the header", async () => {
    const wrapper = mountOn("github-inc");
    await flushPromises();
    expect(wrapper.get('[data-testid="customizer-identity"]').text()).toBe(
      "GitHub, Inc. · Microsoft subsidiary, developer platform · github.com",
    );
  });

  it("asks whether to run on the parent, and switches only when asked", async () => {
    const wrapper = mountOn("github-inc");
    await flushPromises();
    const note = wrapper.get('[data-testid="preflight-note-parent"]');
    expect(note.text()).toContain("Subsidiary of Microsoft — run on Microsoft?");
    // Not a gate: Generate stays live on GitHub.
    expect(wrapper.get('[data-testid="customizer-launch"]').text()).toBe("Generate Research Memo for GitHub");

    await wrapper.get('[data-testid="note-run-on-parent"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="customizer-launch"]').text()).toBe(
      "Generate Research Memo for Microsoft Corp",
    );
    expect(apiMock.reportReadiness).toHaveBeenLastCalledWith("msft", "claude");
  });

  it("names a parent the workspace does not have, without a link", async () => {
    const wrapper = mountOn("cienet");
    await flushPromises();
    expect(wrapper.get('[data-testid="preflight-note-parent"]').text()).toContain(
      "Subsidiary of ALTEN — run on ALTEN? It is not in this workspace yet.",
    );
    expect(wrapper.find('[data-testid="note-run-on-parent"]').exists()).toBe(false);
  });

  it("says a nonprofit has nothing to buy", async () => {
    const wrapper = mountOn("openai-foundation");
    await flushPromises();
    expect(wrapper.get('[data-testid="preflight-note-nonprofit"]').text()).toContain("it has no shares to buy");
  });

  it("points a listed company at the Buffett-method memo, and moves only on a click", async () => {
    const wrapper = mountOn("msft");
    await flushPromises();
    expect(wrapper.get('[data-testid="preflight-note-listed"]').text()).toContain(
      "built to value a public stock",
    );
    expect(wrapper.get('[data-testid="archetype-auto"]').attributes("aria-pressed")).toBe("true");
    await wrapper.get('[data-testid="note-use-buffett"]').trigger("click");
    expect(wrapper.get('[data-testid="archetype-buffett_memo"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.find('[data-testid="preflight-note-listed"]').exists()).toBe(false);
  });

  it("shows each company's identity in the picker", async () => {
    const wrapper = mountOn(null);
    await flushPromises();
    await wrapper.findAll("header button")[0].trigger("click");
    const row = wrapper.findAll("header button").find((b) => b.text().startsWith("GitHub"));
    expect(row.text()).toContain("GitHub, Inc. · Microsoft subsidiary, developer platform · github.com");
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const wrapper = mountOn("github-inc");
    await flushPromises();
    expect(wrapper.get('[data-testid="preflight-note-parent"]').text()).toContain(
      "Microsoft 旗下子公司——是否改为研究 Microsoft？",
    );
    expect(wrapper.get('[data-testid="note-run-on-parent"]').text()).toBe("改为研究 Microsoft Corp");
  });
});

describe("ReportCustomizerModal locks what a run cannot use", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [] });
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    apiMock.reportReadiness.mockImplementation((companyId) => Promise.resolve(readyFor(companyId)));
  });

  it("locks the audience for a Buffett-method memo, which has no IC memo", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_b" });
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    await wrapper.get('[data-testid="audience-LP"]').trigger("click");
    await wrapper.get('[data-testid="archetype-buffett_memo"]').trigger("click");

    for (const id of ["Internal", "Partner", "LP", "Assistant"]) {
      expect(wrapper.get(`[data-testid="audience-${id}"]`).attributes("disabled")).toBeDefined();
    }
    expect(wrapper.get('[data-testid="audience-lock-reason"]').text()).toBe(
      "A Buffett-method memo is one document for every reader and has no IC memo, so there is no audience to choose.",
    );
    // No audience in the run's description either.
    expect(wrapper.get('[data-testid="customizer-tagline"]').text()).toBe("Buffett-Method Memo · Autonomous");
    await launch(wrapper);
    expect(apiMock.generateReport.mock.calls[0][0].audience).toBe("Internal");

    // Back to a memo with an audience: the analyst's pick is still there.
    await wrapper.get('[data-testid="archetype-auto"]').trigger("click");
    expect(wrapper.get('[data-testid="audience-LP"]').attributes("aria-pressed")).toBe("true");
  });

  it("locks what Memo Studio ignores, with the reason", async () => {
    const wrapper = mountOn("zainar-inc", { initialGenerationMode: "studio_review" });
    await flushPromises();
    // Engine & Quality: Studio runs on Claude at the top tier.
    expect(wrapper.get('[data-testid="engine-gemini"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="quality-best"]').attributes("aria-pressed")).toBe("true");
    expect(wrapper.get('[data-testid="quality-lock-reason"]').text()).toContain("Memo Studio runs on Claude");
    // Blueprint: audience, template and length are the workspace's.
    await wrapper.findAll("nav button")[0].trigger("click");
    expect(wrapper.get('[data-testid="audience-Internal"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="audience-lock-reason"]').text()).toContain("internal IC");
    expect(wrapper.get('[data-testid="template-standard"]').attributes("disabled")).toBeDefined();
    expect(wrapper.get('[data-testid="template-default-hint"]').text()).toContain(
      "Memo Studio writes on the workspace template",
    );
    expect(wrapper.get('[data-testid="length-locked"]').text()).toContain("Full IC Report");
  });
});

describe("ReportCustomizerModal: built from", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    apiMock.workspaceSettings.mockResolvedValue({ preferences: {} });
    apiMock.reportEstimates.mockResolvedValue(ESTIMATES);
    apiMock.reportReadiness.mockImplementation((companyId) => Promise.resolve(readyFor(companyId)));
  });

  afterEach(() => setAppLanguage("en"));

  async function evidenceTab(rows) {
    apiMock.listCompanyDocuments.mockResolvedValue({ groups: [{ id: "uploaded-documents", rows }] });
    const wrapper = mountOn("zainar-inc");
    await flushPromises();
    await wrapper.findAll("nav button")[2].trigger("click");
    await flushPromises();
    return wrapper;
  }

  const builtFrom = (wrapper) => wrapper.get('[data-testid="customizer-built-from"]').text();

  it("counts the analysed documents the run will read", async () => {
    const wrapper = await evidenceTab([ANALYSED_DOC, { ...ANALYSED_DOC, record_id: "an2", title: "model_analysis.md" }]);
    expect(builtFrom(wrapper)).toBe("Built from 2 analysed documents, plus web research.");

    await wrapper.findAll('input[type="checkbox"]')[1].setValue(false);
    expect(builtFrom(wrapper)).toBe("Built from 1 of 2 analysed documents, plus web research.");

    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false);
    expect(builtFrom(wrapper)).toBe("Web research only: no analysed document is selected.");
  });

  it("warns when the memo would rest on web research alone", async () => {
    const wrapper = await evidenceTab([]);
    expect(builtFrom(wrapper)).toBe(
      "Web research only: nothing analysed is on file for this company yet. Upload files in the Files tab and run Analyze on them.",
    );
    // Nothing to select: no Select all, no second empty message.
    expect(wrapper.text()).not.toContain("Select all");
    expect(wrapper.text()).not.toContain("No analysed documents yet");
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    const wrapper = await evidenceTab([ANALYSED_DOC]);
    expect(builtFrom(wrapper)).toBe("依据 1 份已分析文档及网络研究撰写。");
  });
});
