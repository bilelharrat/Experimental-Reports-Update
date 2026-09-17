import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { ref } from "vue";
import ReportCustomizerModal from "../src/components/ReportCustomizerModal.vue";

const apiMock = vi.hoisted(() => ({
  generateReport: vi.fn(),
  studioInvestigate: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    generateReport: apiMock.generateReport,
    studioInvestigate: apiMock.studioInvestigate,
  },
  withApiToken: (url) => url,
}));

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
  });

  it("renders modal with company info and default blueprint tab", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("NVIDIA Corp.");
    expect(wrapper.text()).toContain("NVDA");
    expect(wrapper.text()).toContain("Blueprint & Framing");
    expect(wrapper.text()).toContain("Auto Full IC");
    expect(wrapper.text()).toContain("Buffett Fundamental");
  });

  it("switches tabs between blueprint, engine, directives, and evidence", async () => {
    const wrapper = mountModal();
    const navButtons = wrapper.findAll("nav button");

    // Click Engine & Quality tab
    await navButtons[1].trigger("click");
    expect(wrapper.text()).toContain("Interactive Studio Review");
    expect(wrapper.text()).toContain("Best Frontier");

    // Click Directives & Focus tab
    await navButtons[2].trigger("click");
    expect(wrapper.text()).toContain("Analyst Steering Instructions");
    expect(wrapper.text()).toContain("Strategic Diligence Pillars");
    expect(wrapper.text()).toContain("Moat Durability");

    // Click Evidence Sources tab
    await navButtons[3].trigger("click");
    expect(wrapper.text()).toContain("Evidence Repository Attachments");
    expect(wrapper.text()).toContain("Company SEC & Regulatory Filings");
  });

  it("toggles diligence pillars and applies suggestion chips", async () => {
    const wrapper = mountModal();
    const navButtons = wrapper.findAll("nav button");
    await navButtons[2].trigger("click"); // Directives tab

    // Click a suggestion chip
    const chip = wrapper.find("button.rounded-full");
    expect(chip.exists()).toBe(true);
    await chip.trigger("click");

    const textarea = wrapper.find("textarea");
    expect(textarea.element.value).toContain("Scrutinize pricing power against open-source threats");

    // Toggle pillar
    const bigTechButton = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Big Tech Threat"));
    expect(bigTechButton).toBeDefined();
    await bigTechButton.trigger("click");
    expect(bigTechButton.classes()).toContain("bg-accent");
  });

  it("launches studio investigation when Interactive Studio Review is selected", async () => {
    apiMock.studioInvestigate.mockResolvedValue({ session_id: "sess_123" });
    const wrapper = mountModal();

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
      report_mode: "full",
      quality: "best",
      // Claude is the default engine; the toggle opts a run into Gemini.
      engine: "claude",
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
});
