import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const apiMock = vi.hoisted(() => ({
  listCompanyReports: vi.fn(),
  studioGenerate: vi.fn(),
  listActiveJobs: vi.fn().mockResolvedValue([]),
  putTrackingWatchlist: vi.fn().mockResolvedValue({ company_ids: [] }),
  getTrackingWatchlist: vi.fn().mockResolvedValue({ company_ids: [] }),
}));

vi.mock("../src/api.js", () => ({
  api: apiMock,
  default: apiMock,
  withApiToken: (u) => u,
}));

import ReportsMemosCard from "../src/components/research/ReportsMemosCard.vue";
import CompanyDossierView from "../src/components/research/CompanyDossierView.vue";
import { trackedCompanyIds } from "../src/state.js";
import {
  FAILED_DISMISSED,
  KO_BUFFETT,
  ZAINAR_WARNINGS,
  runningReport,
  withReport,
} from "./fixtures/reportSummaries.js";

const studioParked = () =>
  withReport(ZAINAR_WARNINGS, {
    id: "studio000001",
    status: "awaiting_studio",
    stage: "Cards ready for review",
    memo_mode: "studio",
    download_urls: null,
    memo_quality_lint: null,
    memo_chinese_parity: null,
    quality_warnings: null,
  });

function mountCard(reports, props = {}) {
  return mount(ReportsMemosCard, {
    props: { companyId: "zainar-inc", reports, ...props },
  });
}

const row = (wrapper, id) => wrapper.get(`[data-report-id="${id}"]`);

describe("ReportsMemosCard", () => {
  it("reads real report records the way MacReport does", () => {
    const wrapper = mountCard([
      withReport(ZAINAR_WARNINGS),
      withReport(KO_BUFFETT, { company_id: "zainar-inc" }),
      runningReport({ id: "run000000001", company_id: "zainar-inc" }),
    ]);

    // The title is the report's type, never its id.
    expect(row(wrapper, ZAINAR_WARNINGS.id).get('[data-testid="memo-row-title"]').text()).toBe(
      "Investment Memo (Late-Stage)",
    );
    expect(row(wrapper, KO_BUFFETT.id).get('[data-testid="memo-row-title"]').text()).toBe("Buffett-Method Memo");
    expect(wrapper.text()).not.toContain(ZAINAR_WARNINGS.id);

    // A delivered memo with warnings is openable, labelled for attention —
    // and never offered "Follow run".
    const zainar = row(wrapper, ZAINAR_WARNINGS.id);
    expect(zainar.get('[data-testid="memo-row-status"]').text()).toBe("Attention");
    expect(zainar.find('[data-testid="memo-row-read"]').exists()).toBe(true);
    expect(zainar.find('[data-testid="memo-row-follow"]').exists()).toBe(false);
    expect(zainar.text()).toContain("Internal IC");

    expect(row(wrapper, KO_BUFFETT.id).get('[data-testid="memo-row-status"]').text()).toBe("Ready");

    // A live run follows into the Reports viewer's status card.
    const running = row(wrapper, "run000000001");
    expect(running.get('[data-testid="memo-row-status"]').text()).toBe("Running");
    running.get('[data-testid="memo-row-follow"]').trigger("click");
    expect(wrapper.emitted("open-memo")[0][0].id).toBe("run000000001");
  });

  it("shows the memo's call and its review state, and a placeholder's missing document", async () => {
    const { GOOGLE_PASS, PLACEHOLDER_FINANCIAL } = await import("./fixtures/reportReader.js");
    const wrapper = mountCard([
      withReport(GOOGLE_PASS, {
        company_id: "zainar-inc",
        review_state: "approved",
        reviewer_name: "Bilel Harrat",
      }),
      withReport(PLACEHOLDER_FINANCIAL, { company_id: "zainar-inc" }),
    ]);
    const google = row(wrapper, GOOGLE_PASS.id);
    expect(google.get('[data-testid="memo-row-verdict"]').text()).toBe("Pass · buy ≤ $215");
    expect(google.get('[data-testid="memo-row-review"]').text()).toBe("Approved by Bilel Harrat");
    const placeholder = row(wrapper, PLACEHOLDER_FINANCIAL.id);
    expect(placeholder.get('[data-testid="memo-row-status"]').text()).toBe("No document");
    expect(placeholder.find('[data-testid="memo-row-read"]').exists()).toBe(false);
  });

  it("keeps a cleared failure off the desk", () => {
    const wrapper = mountCard([withReport(FAILED_DISMISSED, { company_id: "zainar-inc" }), withReport(ZAINAR_WARNINGS)]);
    expect(wrapper.find(`[data-report-id="${FAILED_DISMISSED.id}"]`).exists()).toBe(false);
    expect(wrapper.text()).toContain("1 dossiers on file");
  });

  it("asks twice before Synthesize starts a paid run", async () => {
    const wrapper = mountCard([studioParked()]);
    const button = wrapper.get('[data-testid="memo-row-synthesize"]');
    expect(button.text()).toBe("Synthesize Memo");

    await button.trigger("click");
    expect(wrapper.emitted("synthesize")).toBeUndefined();
    expect(button.text()).toBe("Click again to synthesize — this runs the model");

    await button.trigger("click");
    expect(wrapper.emitted("synthesize")[0][0].id).toBe("studio000001");
  });
});

describe("CompanyDossierView reports", () => {
  const stubs = {
    UnifiedProfileCard: true,
    SignalScoreCard: true,
    EarningsFilingsCard: true,
    DealPipelineCard: true,
    CompsRailCard: true,
    CapTableCard: true,
    FounderRadarCard: true,
    VCRatiosCard: true,
    DecisionsCard: true,
    ICPrepCard: true,
    ICRoomCard: true,
    NumberLintCard: true,
    ThesisTrackerCard: true,
    CompanyCommentsCard: true,
    FactLedgerCard: true,
    UnifiedDocumentsView: true,
    RecordDecisionModal: {
      props: ["reports"],
      template: '<div data-testid="decision-modal" :data-titles="reports.map((r) => r.title + \'|\' + r.can_open).join(\';\')" />',
    },
    MemoStudioEditor: {
      props: ["reports"],
      template: '<div data-testid="memo-studio" :data-count="reports.length" />',
    },
  };

  let wrapper;

  async function mountDossier() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/:companyId", name: "research", component: { template: "<div />" } },
        { path: "/reports", name: "reports", component: { template: "<div />" } },
      ],
    });
    await router.push("/zainar-inc?section=memos");
    await router.isReady();
    wrapper = mount(CompanyDossierView, {
      props: { companyId: "zainar-inc", company: { id: "zainar-inc", name: "ZaiNar, Inc." } },
      global: { plugins: [router], stubs },
    });
    await flushPromises();
    return { router };
  }

  beforeEach(() => {
    vi.clearAllMocks();
    trackedCompanyIds.value = new Set();
    apiMock.listCompanyReports.mockResolvedValue([withReport(ZAINAR_WARNINGS), studioParked()]);
    apiMock.studioGenerate.mockResolvedValue({ id: "studio000001", status: "generating" });
  });

  afterEach(() => {
    wrapper?.unmount();
    trackedCompanyIds.value = new Set();
  });

  it("loads the company's reports from the endpoint that exists", async () => {
    await mountDossier();
    expect(apiMock.listCompanyReports).toHaveBeenCalledWith("zainar-inc");
    expect(wrapper.find(`[data-report-id="${ZAINAR_WARNINGS.id}"]`).exists()).toBe(true);
    // The decision sheet gets a readable title and whether a document is on file.
    const titles = wrapper.get('[data-testid="decision-modal"]').attributes("data-titles");
    expect(titles).toContain("Investment Memo (Late-Stage) · 2026-08-31|true");
  });

  it("starts a parked studio run's memo from the card, then reloads the list", async () => {
    await mountDossier();
    const synth = wrapper.get('[data-testid="memo-row-synthesize"]');
    await synth.trigger("click");
    expect(apiMock.studioGenerate).not.toHaveBeenCalled();
    apiMock.listCompanyReports.mockClear();
    await synth.trigger("click");
    await flushPromises();
    expect(apiMock.studioGenerate).toHaveBeenCalledWith("studio000001");
    expect(apiMock.listCompanyReports).toHaveBeenCalledWith("zainar-inc");
  });

  it("follows the company through the sidebar's follow list", async () => {
    await mountDossier();
    const more = wrapper.findAll("button").find((b) => b.attributes("title") === "More actions");
    await more.trigger("click");
    const follow = wrapper.findAll(".mac-menu-item").find((b) => b.text() === "Follow on Pipeline");
    await follow.trigger("click");
    expect(trackedCompanyIds.value.has("zainar-inc")).toBe(true);
  });
});
