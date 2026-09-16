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
      report_type: "memo_late_stage",
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
      report_type: "memo_late_stage",
      audience: "internal",
      language: "en",
      // The brief is the default scope now: it is the one that gets read
      // end to end, and the full IC runs past forty pages.
      report_mode: "compact",
      // Balanced is the default tier: the top model still writes the memo.
      quality: "balanced",
      // Nothing deselected, so the run reads the whole research folder.
      evidence_files: null,
    });
    expect(wrapper.emitted("created")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });
});
