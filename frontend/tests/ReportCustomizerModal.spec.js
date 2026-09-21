import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { ref } from "vue";
import ReportCustomizerModal from "../src/components/ReportCustomizerModal.vue";

const apiMock = vi.hoisted(() => ({
  generateReport: vi.fn(),
  studioInvestigate: vi.fn(),
  listCompanyDocuments: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    generateReport: apiMock.generateReport,
    studioInvestigate: apiMock.studioInvestigate,
    listCompanyDocuments: apiMock.listCompanyDocuments,
  },
  withApiToken: (url) => url,
}));

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

describe("ReportCustomizerModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMock.listCompanyDocuments.mockResolvedValue({
      groups: [{ id: "uploaded-documents", rows: [ANALYSED_DOC] }],
    });
  });

  it("renders modal with company info and default blueprint tab", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("NVIDIA Corp.");
    expect(wrapper.text()).toContain("NVDA");
    expect(wrapper.text()).toContain("Blueprint & Framing");
    expect(wrapper.text()).toContain("Auto Full IC");
    expect(wrapper.text()).toContain("Buffett Fundamental");
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
    const studio = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Interactive Studio Review"));
    await studio.trigger("click");

    const launchBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Launch Studio Investigation"));
    expect(launchBtn).toBeDefined();

    await launchBtn.trigger("click");
    await flushPromises();

    expect(apiMock.studioInvestigate).toHaveBeenCalledWith({
      company_id: "nvda",
      report_type: "Investment Report (Auto)",
    });
    expect(wrapper.emitted("created")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("defaults to the brief and to bilingual, and locks the single languages", async () => {
    // Both defaults follow what the pipeline really does: the brief is the
    // document people finish, and memo_prep writes an English and a Chinese
    // docx on every run regardless of this picker.
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.text()).toContain("Executive Brief");
    expect(wrapper.text()).toContain("Bilingual (EN + ZH)");
    // One-Click is the default, so the launch button is the memo one.
    expect(
      wrapper
        .findAll("button")
        .some((b) => b.text().includes("Generate Research Memo")),
    ).toBe(true);

    const disabled = wrapper
      .findAll("button")
      .filter((b) => b.attributes("disabled") !== undefined)
      .map((b) => b.text());
    expect(disabled.some((label) => label.includes("English only"))).toBe(true);
    expect(disabled.some((label) => label.includes("中文 only"))).toBe(true);
  });

  it("only ever sends report types and audiences the API accepts", async () => {
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
    const AUDIENCES = ["LP", "Assistant", "Partner", "Internal"];
    apiMock.generateReport.mockResolvedValue({ id: "rep_1" });

    const wrapper = mountModal();
    await flushPromises();
    const archetypeButtons = wrapper
      .findAll("button")
      .filter((b) => /Auto Full IC|Late-Stage IC|Buffett Fundamental|Financial Audit|Market Analysis|Background Dossier/.test(b.text()));
    expect(archetypeButtons.length).toBeGreaterThanOrEqual(6);

    for (const archetype of archetypeButtons.slice(0, 6)) {
      apiMock.generateReport.mockClear();
      await archetype.trigger("click");
      const launchBtn = wrapper
        .findAll("button")
        .find((b) => b.text().includes("Generate Research Memo"));
      await launchBtn.trigger("click");
      await flushPromises();
      const sent = apiMock.generateReport.mock.calls[0]?.[0];
      expect(REPORT_TYPES).toContain(sent.report_type);
      expect(AUDIENCES).toContain(sent.audience);
    }
  });

  it("locks Memo Studio for blueprints it cannot run", async () => {
    // memo_prep.is_memo_report_type accepts only the auto and late-stage
    // memos, and the studio endpoint rejects the Buffett memo on top.
    const wrapper = mountModal();
    await flushPromises();
    const nav = wrapper.findAll("nav button");
    await nav[1].trigger("click");

    const studioBtn = () =>
      wrapper
        .findAll("button")
        .find((b) => b.text().includes("Interactive Studio Review"));
    expect(studioBtn().attributes("disabled")).toBeUndefined();

    await nav[0].trigger("click");
    const marketAnalysis = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Market Analysis"));
    await marketAnalysis.trigger("click");
    await nav[1].trigger("click");
    expect(studioBtn().attributes("disabled")).toBeDefined();
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
    const oneClick = wrapper
      .findAll("button")
      .find((b) => b.text().includes("One-Click Autonomous"));
    await oneClick.trigger("click");
    const launchBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Generate Research Memo"));
    await launchBtn.trigger("click");
    await flushPromises();

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
    expect(wrapper.text()).toContain("No analysed documents yet");
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(0);
  });

  it("launches autonomous report generation when One-Click is selected", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_999", status: "running" });
    const wrapper = mountModal();

    // Switch to Engine tab and select One-Click Autonomous
    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");

    const oneClickBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("One-Click Autonomous"));
    expect(oneClickBtn).toBeDefined();
    await oneClickBtn.trigger("click");

    // Bottom button should now say "Generate Research Memo"
    const launchBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Generate Research Memo"));
    expect(launchBtn).toBeDefined();

    await launchBtn.trigger("click");
    await flushPromises();

    expect(apiMock.generateReport).toHaveBeenCalledWith({
      company_id: "nvda",
      report_type: "Investment Report (Auto)",
      audience: "Internal",
      language: "en",
      // The brief is the default scope now: it is the one that gets read
      // end to end, and the full IC runs past forty pages.
      report_mode: "compact",
      // Balanced is the default tier: the top model still writes the memo.
      quality: "balanced",
      // Claude is the default engine; the toggle opts a run into Gemini.
      engine: "claude",
      // Nothing deselected, so the run reads the whole research folder.
      evidence_files: null,
    });
    expect(wrapper.emitted("created")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("sends the Gemini engine when the toggle is switched", async () => {
    apiMock.generateReport.mockResolvedValue({ id: "rep_1000", status: "running" });
    const wrapper = mountModal();

    const navButtons = wrapper.findAll("nav button");
    await navButtons[1].trigger("click");

    const gemini = wrapper.find('[data-testid="engine-gemini"]');
    expect(gemini.exists()).toBe(true);
    await gemini.trigger("click");

    const oneClickBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("One-Click Autonomous"));
    await oneClickBtn.trigger("click");
    const launchBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Generate Research Memo"));
    await launchBtn.trigger("click");
    await flushPromises();

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
