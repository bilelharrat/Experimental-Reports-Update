import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { ref } from "vue";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

const mockApi = vi.hoisted(() => ({
  listReports: vi.fn(),
  getReport: vi.fn(),
  listActiveJobs: vi.fn(),
  cancelReportRun: vi.fn(),
  resumeReport: vi.fn(),
  dismissReport: vi.fn(),
  me: vi.fn(),
  recordReportEvent: vi.fn(),
  listReportComments: vi.fn(),
  addReportComment: vi.fn(),
  resolveReportComment: vi.fn(),
  setReportReview: vi.fn(),
  getReportDiff: vi.fn(),
  reportExportUrl: (id, language = "en", artifact = "memo") =>
    `/api/reports/${id}/download?language=${language}&artifact=${artifact}&purpose=export`,
  reportPdfUrl: (id, language = "en", artifact = "memo") =>
    `/api/reports/${id}/preview?language=${language}&artifact=${artifact}`,
  reportBundleUrl: (id, format = "all") => `/api/reports/${id}/bundle?format=${format}`,
}));

vi.mock("../src/api.js", () => ({
  api: mockApi,
  withApiToken: (path) => path,
}));

import ReportsView from "../src/views/ReportsView.vue";
import { activeJobs } from "../src/activeJobs.js";
import { setAppLanguage } from "../src/state.js";
import { resetReportSession } from "../src/components/reports/reportSession.js";
import {
  ANTHROPIC_COMPLETE,
  FAILED_DISMISSED,
  KO_BUFFETT,
  ZAINAR_ANALYSIS_ARTIFACTS,
  ZAINAR_WARNINGS,
  pausedReport,
  runningReport,
  withReport,
} from "./fixtures/reportSummaries.js";
import {
  CIENET_LATE_NEW,
  CIENET_LATE_OLD,
  GOOGLE_BUY,
  GOOGLE_PASS,
  OXY_PASS,
  PLACEHOLDER_FINANCIAL,
} from "./fixtures/reportReader.js";

// An admin's permissions (GET /api/auth/me).
const ALL_PERMISSIONS = [
  "admin:read",
  "desk:write",
  "documents:delete",
  "memo:approve",
  "memo:edit",
  "memo:export",
  "settings:update",
  "sources:edit",
  "tasks:action",
  "users:manage",
];

// Real ReportSummary records (see fixtures/reportSummaries.js), newest first
// as the API lists them.
const sampleReports = () => [
  withReport(ANTHROPIC_COMPLETE),
  withReport(ZAINAR_WARNINGS),
  withReport(KO_BUFFETT),
  withReport(FAILED_DISMISSED),
];

async function createTestRouter(initialQuery = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/reports", name: "reports", component: ReportsView },
      { path: "/:companyId", name: "research", component: { template: "<div />" } },
    ],
  });
  await router.push({ path: "/reports", query: initialQuery });
  await router.isReady();
  return router;
}

let wrapper;

async function mountReports({ query = {}, provide = {} } = {}) {
  const router = await createTestRouter(query);
  wrapper = mount(ReportsView, {
    attachTo: document.body,
    global: { plugins: [router], provide },
  });
  await flushPromises();
  return { router, wrapper };
}

function textResponse(text) {
  return {
    ok: true,
    status: 200,
    text: () => Promise.resolve(text),
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
  };
}

function stubMatchMedia(matches) {
  window.matchMedia = (query) => ({
    matches: matches(query),
    media: query,
    addEventListener() {},
    removeEventListener() {},
  });
}

const articleFor = (w, id) => w.find(`article[data-report-id="${id}"]`);
const settle = async () => {
  await flushPromises();
  await new Promise((resolve) => setTimeout(resolve, 20));
  await flushPromises();
};

describe("ReportsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    resetReportSession();
    delete window.matchMedia;
    activeJobs.value = [];
    setAppLanguage("en");
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(textResponse(`# Paper\n\n${url}`))));
    mockApi.me.mockResolvedValue({ role: "admin", permissions: [...ALL_PERMISSIONS] });
    mockApi.recordReportEvent.mockResolvedValue({ recorded: true });
    mockApi.listReportComments.mockResolvedValue({ items: [], open_count: 0, open_comments: 0, open_flags: 0 });
    mockApi.listReports.mockResolvedValue(sampleReports());
    mockApi.listActiveJobs.mockResolvedValue([]);
    mockApi.getReport.mockImplementation((id) =>
      Promise.resolve({
        ...sampleReports().find((r) => r.id === id),
        stream_url: `/api/memos/${id}/stream`,
        log_url: `/api/jobs/log?path=memo:${id}`,
        analysis_artifacts: id === ZAINAR_WARNINGS.id ? [...ZAINAR_ANALYSIS_ARTIFACTS] : [],
      }),
    );
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    setAppLanguage("en");
  });

  it("lists the real records, keeping a cleared failure out of the way", async () => {
    await mountReports();

    expect(mockApi.listReports).toHaveBeenCalled();
    expect(wrapper.text()).toContain("Research Reports");
    expect(wrapper.text()).toContain("Anthropic");
    expect(wrapper.text()).toContain("ZaiNar, Inc.");
    expect(wrapper.text()).toContain("Coca Cola Co");
    // The dismissed failure is behind "Show dismissed", not first in line.
    expect(wrapper.findAll("article")).toHaveLength(3);
    expect(wrapper.get('[data-testid="reports-count"]').text()).toBe("3 reports");
    const toggle = wrapper.get('[data-testid="reports-show-dismissed"]');
    expect(toggle.text()).toBe("Show dismissed (1)");

    await toggle.trigger("click");
    expect(wrapper.findAll("article")).toHaveLength(4);
    expect(articleFor(wrapper, FAILED_DISMISSED.id).text()).toContain("Dismissed");
    expect(wrapper.get('[data-testid="reports-show-dismissed"]').text()).toBe("Hide dismissed");
  });

  it("labels types from report_type, with the Buffett memo's new name", async () => {
    await mountReports();
    expect(articleFor(wrapper, KO_BUFFETT.id).text()).toContain("Buffett-Method Memo");
    expect(articleFor(wrapper, ANTHROPIC_COMPLETE.id).text()).toContain("Investment Memo (Late-Stage)");
    expect(wrapper.text()).not.toContain("Investment Memo Latestage");

    // The type filter uses the same labels, the wire values untouched.
    const options = wrapper.get('[data-testid="reports-kind-filter"]').findAll("option");
    const byValue = Object.fromEntries(options.map((o) => [o.attributes("value"), o.text()]));
    expect(byValue["Buffett Investment Memo"]).toBe("Buffett-Method Memo");
    expect(byValue["Investment Memo (Late-Stage)"]).toBe("Investment Memo (Late-Stage)");

    setAppLanguage("zh");
    await flushPromises();
    expect(articleFor(wrapper, KO_BUFFETT.id).text()).toContain("巴菲特方法备忘录");
  });

  it("filters reports by search query", async () => {
    await mountReports();
    await wrapper.find('input[type="text"]').setValue("Coca");
    await flushPromises();

    const articles = wrapper.findAll("article");
    expect(articles.length).toBe(1);
    expect(articles[0].text()).toContain("Coca Cola Co");
  });

  it("filters reports by company selector", async () => {
    await mountReports();
    await wrapper.findAll("select")[0].setValue("zainar-inc");
    await flushPromises();

    const articles = wrapper.findAll("article");
    expect(articles.length).toBe(1);
    expect(articles[0].text()).toContain("ZaiNar, Inc.");
  });

  it("files complete_with_warnings under Attention and a running memo under Running", async () => {
    mockApi.listReports.mockResolvedValue([...sampleReports(), runningReport()]);
    await mountReports();
    const selects = wrapper.findAll("select");
    const statusSelect = selects[selects.length - 1];

    await statusSelect.setValue("needs_attention");
    await flushPromises();
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual([ZAINAR_WARNINGS.id]);

    // "analyzing" is a live run, not a finished one.
    await statusSelect.setValue("running");
    await flushPromises();
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual(["run000000001"]);
  });

  it("selects a report into the viewer and supports ?id deep links", async () => {
    const { router } = await mountReports();
    // The newest report with a document opens first.
    expect(wrapper.get('[data-testid="reports-viewer"]').text()).toContain("Anthropic — Investment Memo (Late-Stage)");

    await articleFor(wrapper, KO_BUFFETT.id).trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.id).toBe(KO_BUFFETT.id);
    expect(wrapper.get('[data-testid="reports-viewer"]').text()).toContain("Coca Cola Co — Buffett-Method Memo");

    wrapper.unmount();
    await mountReports({ query: { id: KO_BUFFETT.id } });
    expect(wrapper.get('[data-testid="reports-viewer"]').text()).toContain("Coca Cola Co — Buffett-Method Memo");
  });

  it("renders Monogram for each report with correct company info", async () => {
    await mountReports();
    const monograms = wrapper.findAllComponents({ name: "Monogram" });
    expect(monograms.length).toBeGreaterThanOrEqual(3);
    const zainar = monograms.find((m) => m.props("company")?.id === "zainar-inc");
    expect(zainar).toBeTruthy();
    expect(zainar.props("company").name).toBe("ZaiNar, Inc.");
  });

  it("collapses the reports list to a rail and remembers it", async () => {
    await mountReports();

    const aside = wrapper.find("aside");
    expect(aside.classes()).toContain("w-80");
    expect(wrapper.findAll("article").length).toBeGreaterThan(0);

    await wrapper.find('[data-testid="reports-list-collapse"]').trigger("click");
    await flushPromises();

    // Collapsed: a 44px rail, no rows, and a control to bring them back.
    expect(wrapper.find("aside").classes()).toContain("w-[44px]");
    expect(wrapper.findAll("article").length).toBe(0);
    const rail = wrapper.find('[data-testid="reports-list-expand"]');
    expect(rail.exists()).toBe(true);
    // The rail still says how many reports are hidden behind it.
    expect(rail.text()).toContain("reports");

    // And it carries one company logo per report — the sidebar's collapsed
    // rail, for documents — rather than an empty strip. The open report's
    // mark is the selected one, and a mark opens its report.
    const marks = wrapper.findAll('[data-testid="reports-rail"] button');
    expect(marks.length).toBe(wrapper.vm.filteredReports.length);
    expect(marks.length).toBeGreaterThan(0);
    expect(marks.filter((m) => m.attributes("data-selected") === "true")).toHaveLength(1);
    expect(marks[0].findComponent({ name: "Monogram" }).exists()).toBe(true);
    await marks[marks.length - 1].trigger("click");
    await flushPromises();
    expect(
      wrapper.findAll('[data-testid="reports-rail"] button')
        .findIndex((m) => m.attributes("data-selected") === "true"),
    ).toBe(marks.length - 1);
    expect(window.localStorage.getItem("bsh.reportsListCollapsed")).toBe("1");

    await rail.trigger("click");
    await flushPromises();
    expect(wrapper.find("aside").classes()).toContain("w-80");
    expect(wrapper.findAll("article").length).toBeGreaterThan(0);
    expect(window.localStorage.getItem("bsh.reportsListCollapsed")).toBe("0");
  });

  it("keeps the title, search, filters and actions on the list, nothing above the panes", async () => {
    const openReportCustomizer = vi.fn();
    await mountReports({ query: { company: "zainar-inc" }, provide: { openReportCustomizer } });

    // The document pane runs from the top: no header row above the panes.
    expect(wrapper.element.querySelector(":scope > header")).toBeNull();
    const header = wrapper.get('[data-testid="reports-list-header"]');
    expect(header.get("h1").text()).toBe("Research Reports");
    expect(header.find('input[type="text"]').exists()).toBe(true);
    expect(header.findAll("select").length).toBe(3);

    // Filtered to ZaiNar: the count says how many of all the reports show.
    expect(wrapper.get('[data-testid="reports-count"]').text()).toBe("1 of 3 reports");

    // Generate starts a report for the company the list is filtered to.
    await wrapper.get('[data-testid="reports-generate"]').trigger("click");
    expect(openReportCustomizer).toHaveBeenCalledWith("zainar-inc");

    mockApi.listReports.mockClear();
    await wrapper.get('[data-testid="reports-refresh"]').trigger("click");
    await flushPromises();
    expect(mockApi.listReports).toHaveBeenCalledTimes(1);
  });

  it("links a company's desk only when the company is in the workspace", async () => {
    const workspaceCompanies = ref([{ id: "zainar-inc", name: "ZaiNar, Inc." }]);
    await mountReports({ query: { id: ZAINAR_WARNINGS.id }, provide: { workspaceCompanies } });

    // Open Studio lives in the row's overflow menu.
    const studioLink = async (id) => {
      await articleFor(wrapper, id).get('[data-testid="report-row-more"]').trigger("click");
      const found = articleFor(wrapper, id).find('[data-testid="report-open-studio"]').exists();
      await articleFor(wrapper, id).get('[data-testid="report-row-more"]').trigger("click");
      return found;
    };
    expect(articleFor(wrapper, ZAINAR_WARNINGS.id).find('[data-testid="report-open-studio"]').exists()).toBe(false);
    expect(await studioLink(ZAINAR_WARNINGS.id)).toBe(true);
    // Anthropic and Coca-Cola were never added here: no link to a stranger's desk.
    expect(await studioLink(ANTHROPIC_COMPLETE.id)).toBe(false);
    expect(await studioLink(KO_BUFFETT.id)).toBe(false);
    expect(wrapper.find('[data-testid="viewer-company-link"]').exists()).toBe(true);

    await articleFor(wrapper, KO_BUFFETT.id).trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="viewer-company-link"]').exists()).toBe(false);
  });

  it("reads the quality chip from the gate blocks and never prints a 0% fact check", async () => {
    mockApi.listReports.mockResolvedValue([
      withReport(ANTHROPIC_COMPLETE),
      withReport(ZAINAR_WARNINGS, { memo_fact_check: { status: "no_figures", checked: 0, unsupported: 0, coverage_pct: null } }),
      withReport(KO_BUFFETT, {
        // A thin corpus: checked figures, but coverage is "not checkable".
        memo_fact_check: { status: "not_checkable", checked: 12, coverage_pct: null, thin_corpus: true },
      }),
      withReport(runningReport({ id: "fc0000000001", status: "complete", download_urls: { en: "/x" } }), {
        memo_fact_check: {
          status: "warn",
          checked: 40,
          verified: 12,
          found_elsewhere: 20,
          derived: 3,
          company_reported: 0,
          registry_only: 2,
          not_traced: 3,
          unsupported: 2,
          coverage_pct: 88,
          thin_corpus: false,
          basis: "tiered",
        },
      }),
    ]);
    await mountReports();

    expect(articleFor(wrapper, ANTHROPIC_COMPLETE.id).get('[data-testid="quality-chip"]').text()).toBe("Checked");
    expect(articleFor(wrapper, ZAINAR_WARNINGS.id).get('[data-testid="quality-chip"]').text()).toBe("1 P0");
    // The Buffett record carries no gate blocks: no chip rather than a guess.
    expect(articleFor(wrapper, KO_BUFFETT.id).find('[data-testid="quality-chip"]').exists()).toBe(false);

    // The fact check says what it found, honestly — never a "traced" %.
    const fact = (id) => articleFor(wrapper, id).get('[data-testid="fact-check-chip"]');
    // A memo that predates the check says so.
    expect(fact(ANTHROPIC_COMPLETE.id).text()).toBe("Checks not run");
    expect(fact(ANTHROPIC_COMPLETE.id).attributes("data-state")).toBe("not_run");
    expect(fact(ZAINAR_WARNINGS.id).text()).toBe("No figures to check");
    // A thin corpus is not checkable, never 0%.
    expect(fact(KO_BUFFETT.id).text()).toBe("Not checkable: no sources on file");
    // A real check: the verified figures and the untraced ones, the tiers on hover.
    const checked = fact("fc0000000001");
    expect(checked.text()).toBe("12 of 40 verified · 3 not traced");
    expect(checked.attributes("title")).toContain("Found elsewhere in sources on file: 20");
    expect(checked.attributes("title")).toContain("Matches registry, not evidence: 2");
    expect(wrapper.text()).not.toMatch(/\d+% traced/);
  });

  it("shows a running report's status card, with a two-step Cancel", async () => {
    mockApi.listReports.mockResolvedValue([runningReport(), ...sampleReports()]);
    mockApi.cancelReportRun.mockResolvedValue({ status: "failed_during_analysis" });
    await mountReports({ query: { id: "run000000001" } });

    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.attributes("data-state")).toBe("running");
    expect(card.text()).toContain("This report is being written");
    expect(card.text()).toContain("Stage: Phase 2 - Parallel analysis passes");
    expect(card.text()).toContain("40% done");
    expect(wrapper.text()).not.toContain("Select a report to view");

    const cancel = wrapper.get('[data-testid="viewer-status-cancel"]');
    await cancel.trigger("click");
    expect(mockApi.cancelReportRun).not.toHaveBeenCalled();
    expect(cancel.text()).toBe("Click again to confirm");
    mockApi.listReports.mockClear();
    await cancel.trigger("click");
    await flushPromises();
    expect(mockApi.cancelReportRun).toHaveBeenCalledWith("run000000001");
    // The list reloads to show what the cancel did.
    expect(mockApi.listReports).toHaveBeenCalled();
  });

  it("opens a cleared failure from a link, with its status card and no Resume", async () => {
    await mountReports({ query: { id: FAILED_DISMISSED.id } });

    // The link revealed the dismissed rows so the report is on the list.
    expect(articleFor(wrapper, FAILED_DISMISSED.id).exists()).toBe(true);
    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.attributes("data-state")).toBe("failed");
    expect(card.text()).toContain("Memo generation failed");
    expect(card.text()).toContain("Analysis crashed");
    expect(card.text()).toContain("This failure record was cleared");
    expect(wrapper.find('[data-testid="viewer-status-resume"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="viewer-status-dismiss"]').exists()).toBe(false);
  });

  it("offers Resume and Dismiss on a resumable failure, each asking twice", async () => {
    const failed = withReport(FAILED_DISMISSED, {
      id: "fail00000001",
      dismissed_at: null,
      resume_available: true,
      failure_phase: "renderer_contract",
      failure_detail: "RuntimeError: section 'investment_risk' has no risk card",
    });
    mockApi.listReports.mockResolvedValue([failed, ...sampleReports()]);
    mockApi.resumeReport.mockResolvedValue({ id: failed.id, status: "queued" });
    mockApi.dismissReport.mockResolvedValue({ id: failed.id });
    await mountReports({ query: { id: failed.id } });

    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.text()).toContain("Memo rendering failed");
    expect(wrapper.get('[data-testid="viewer-status-detail"]').text()).toContain("has no risk card");

    const resume = wrapper.get('[data-testid="viewer-status-resume"]');
    await resume.trigger("click");
    expect(mockApi.resumeReport).not.toHaveBeenCalled();
    expect(resume.text()).toContain("Click again to resume");
    await resume.trigger("click");
    await flushPromises();
    expect(mockApi.resumeReport).toHaveBeenCalledWith(failed.id);

    const dismiss = wrapper.get('[data-testid="viewer-status-dismiss"]');
    await dismiss.trigger("click");
    expect(mockApi.dismissReport).not.toHaveBeenCalled();
    await dismiss.trigger("click");
    await flushPromises();
    expect(mockApi.dismissReport).toHaveBeenCalledWith(failed.id);
  });

  it("shows a paused run's English memo and continues it in two clicks, from the row or the viewer", async () => {
    const paused = pausedReport();
    mockApi.listReports.mockResolvedValue([paused, ...sampleReports()]);
    mockApi.resumeReport.mockResolvedValue({ id: paused.id, status: "resuming" });
    await mountReports({ query: { id: paused.id } });

    // The row: its own chip, never "Running", and the primary action.
    const row = articleFor(wrapper, paused.id);
    expect(row.get('[data-testid="report-status-paused"]').text()).toBe("English ready — paused");
    expect(row.text()).not.toContain("Running");
    const rowContinue = row.get('[data-testid="report-continue"]');
    expect(rowContinue.text()).toBe("Continue (Chinese + IC memo)");

    // The viewer: the English document opens, with the strip above it.
    expect(fetch).toHaveBeenCalledWith(paused.download_urls.en);
    expect(wrapper.find('[data-testid="viewer-status"]').exists()).toBe(false);
    const strip = wrapper.get('[data-testid="viewer-paused"]');
    expect(strip.text()).toContain("English ready — paused");
    expect(strip.text()).toContain("Continuing writes the Chinese version, the artifacts and the IC memo");
    expect(strip.get('[data-testid="viewer-quality-metrics"]').text()).toBe("Quality72% traced1 over cap0 conflicting4% repeated");
    // The English gate's warning is named with its new label.
    expect(wrapper.get('[data-testid="viewer-warning-item"]').text()).toContain("Length over target");

    const stripContinue = strip.get('[data-testid="viewer-status-resume"]');
    expect(stripContinue.text()).toBe("Continue (Chinese + IC memo)");
    await stripContinue.trigger("click");
    expect(mockApi.resumeReport).not.toHaveBeenCalled();
    expect(stripContinue.text()).toBe("Click again to continue — this runs the model");
    await stripContinue.trigger("click");
    await flushPromises();
    expect(mockApi.resumeReport).toHaveBeenCalledWith(paused.id);

    mockApi.resumeReport.mockClear();
    mockApi.listReports.mockClear();
    await rowContinue.trigger("click");
    expect(mockApi.resumeReport).not.toHaveBeenCalled();
    expect(rowContinue.text()).toBe("Click again to continue — this runs the model");
    // The click stays on the button: the row does not re-select.
    await rowContinue.trigger("click");
    await flushPromises();
    expect(mockApi.resumeReport).toHaveBeenCalledWith(paused.id);
    expect(mockApi.listReports).toHaveBeenCalled();
  });

  it("files a paused run under Attention, not Running", async () => {
    const paused = pausedReport();
    mockApi.listReports.mockResolvedValue([paused, runningReport(), ...sampleReports()]);
    await mountReports();
    const selects = wrapper.findAll("select");
    const statusSelect = selects[selects.length - 1];

    await statusSelect.setValue("needs_attention");
    await flushPromises();
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual([paused.id, ZAINAR_WARNINGS.id]);
    await statusSelect.setValue("running");
    await flushPromises();
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual(["run000000001"]);
  });

  it("speaks Chinese on a paused row", async () => {
    setAppLanguage("zh");
    const paused = pausedReport();
    mockApi.listReports.mockResolvedValue([paused, ...sampleReports()]);
    await mountReports({ query: { id: paused.id } });
    const row = articleFor(wrapper, paused.id);
    expect(row.get('[data-testid="report-status-paused"]').text()).toBe("英文版已就绪——已暂停");
    expect(row.get('[data-testid="report-continue"]').text()).toBe("继续生成（中文版 + 投委会备忘录）");
    expect(wrapper.get('[data-testid="viewer-quality-metrics"]').text()).toBe("质量72% 可溯源1 节超篇幅0 处数字冲突4% 重复");
    expect(wrapper.get('[data-testid="viewer-warning-item"]').text()).toContain("篇幅超出目标");
  });

  it("says plainly when a finished report has no document", async () => {
    const placeholder = withReport(KO_BUFFETT, {
      id: "f831d124b01d",
      report_type: "Financial Analysis",
      kind: null,
      download_urls: null,
      stage: "Complete",
    });
    mockApi.listReports.mockResolvedValue([placeholder]);
    await mountReports({ query: { id: placeholder.id } });

    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.attributes("data-state")).toBe("docless");
    expect(card.text()).toContain("This report has no document");
    expect(card.text()).toContain("Reports of this type are not available yet");
  });

  it("names the gate, language and section of a warning, and never switches language", async () => {
    await mountReports({ query: { id: ZAINAR_WARNINGS.id } });

    const banner = wrapper.get('[data-testid="viewer-warnings"]');
    expect(banner.text()).toContain("Memo ready with quality warnings");
    const item = banner.get('[data-testid="viewer-warning-item"]');
    expect(item.text()).toContain("Chinese parity");
    expect(item.text()).toContain("中文");
    expect(item.text()).toContain("Financial Forecast & Valuation");
    expect(item.text()).toContain("P0");
    // No Resume from the banner: a paid re-run cannot fix a checker bug.
    expect(banner.text()).not.toContain("Resume");

    // The dot sits on the flagged language; the document stays in English.
    expect(wrapper.get('[data-testid="viewer-source-zh"]').find('[data-testid="viewer-warning-dot"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="viewer-source-en"]').find('[data-testid="viewer-warning-dot"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="viewer-source-en"]').attributes("aria-pressed")).toBe("true");
    expect(fetch).toHaveBeenCalledWith(ZAINAR_WARNINGS.download_urls.en);
  });

  it("opens in the app's language and keeps ?lang in the URL without history entries", async () => {
    setAppLanguage("zh");
    const { router } = await mountReports({ query: { id: ANTHROPIC_COMPLETE.id } });
    expect(fetch).toHaveBeenLastCalledWith(ANTHROPIC_COMPLETE.download_urls.zh);
    // Dates follow the UI language.
    expect(articleFor(wrapper, ANTHROPIC_COMPLETE.id).text()).toContain("2026年9月");

    const pushSpy = vi.spyOn(router, "push");
    const replaceSpy = vi.spyOn(router, "replace");
    await wrapper.get('[data-testid="viewer-source-en"]').trigger("click");
    await flushPromises();
    expect(fetch).toHaveBeenLastCalledWith(ANTHROPIC_COMPLETE.download_urls.en);
    expect(router.currentRoute.value.query.lang).toBe("en");
    expect(replaceSpy).toHaveBeenCalled();
    expect(pushSpy).not.toHaveBeenCalled();

    // ?lang wins over the app language on the next report.
    await articleFor(wrapper, ZAINAR_WARNINGS.id).trigger("click");
    await flushPromises();
    expect(fetch).toHaveBeenLastCalledWith(ZAINAR_WARNINGS.download_urls.en);
  });

  it("labels the internal document as the IC memo", async () => {
    const withIc = withReport(ANTHROPIC_COMPLETE, {
      download_urls: {
        ...ANTHROPIC_COMPLETE.download_urls,
        internal: `/api/reports/${ANTHROPIC_COMPLETE.id}/download?artifact=internal`,
      },
    });
    mockApi.listReports.mockResolvedValue([withIc]);
    await mountReports({ query: { id: withIc.id } });
    expect(wrapper.get('[data-testid="viewer-source-internal"]').text()).toBe("IC memo");
    expect(articleFor(wrapper, withIc.id).text()).toContain("IC memo");
    expect(wrapper.text()).not.toContain("INTERNAL");
  });

  it("reloads itself when a memo run leaves the shared jobs poll", async () => {
    const running = [{ kind: "memo", report_id: "run000000001", title: "Memo" }];
    mockApi.listActiveJobs.mockResolvedValue(running);
    activeJobs.value = running;
    await mountReports();
    mockApi.listReports.mockClear();

    // Still running: no reload.
    activeJobs.value = [{ kind: "memo", report_id: "run000000001", title: "Memo" }];
    await flushPromises();
    expect(mockApi.listReports).not.toHaveBeenCalled();

    // Finished: the list reloads, riding the rail's poll rather than its own.
    activeJobs.value = [];
    await flushPromises();
    expect(mockApi.listReports).toHaveBeenCalledTimes(1);
    expect(mockApi.listActiveJobs.mock.calls.length).toBeLessThanOrEqual(1);
  });

  it("lists working papers, opens one by ?paper and marks a pass that did not run", async () => {
    fetch.mockImplementation((url) =>
      Promise.resolve(
        textResponse(
          String(url).includes("growth_bridge")
            ? "# Growth bridge\n\n## Status\n\nPass failed: claude exited 143\n"
            : "# Countercase\n\n| Claim | Finding |\n|---|---|\n| a | b |\n",
        ),
      ),
    );
    const { router } = await mountReports({ query: { id: ZAINAR_WARNINGS.id } });
    expect(mockApi.getReport).toHaveBeenCalledTimes(1);
    expect(mockApi.getReport).toHaveBeenCalledWith(ZAINAR_WARNINGS.id);

    await wrapper.get('[data-testid="viewer-papers"]').trigger("click");
    const menu = wrapper.get('[data-testid="viewer-papers-menu"]');
    expect(menu.text()).toContain("Countercase analysis");
    await menu.get('[data-testid="viewer-paper-countercase.md"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.paper).toBe("countercase.md");
    expect(wrapper.html()).toContain("<table>");
    expect(wrapper.get('[data-testid="viewer-export"]').attributes("download")).toBe("countercase.md");
    expect(wrapper.find('[data-testid="viewer-warnings"]').exists()).toBe(false);

    // A failed pass's stub is never printed.
    await wrapper.get('[data-testid="viewer-papers"]').trigger("click");
    await wrapper.get('[data-testid="viewer-paper-growth_bridge.md"]').trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="viewer-paper-not-run"]').text()).toContain("Pass did not run");
    expect(wrapper.text()).not.toContain("claude exited 143");

    await wrapper.get('[data-testid="viewer-paper-back"]').trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.paper).toBeUndefined();
    // Back to the memo reuses the cached detail.
    expect(mockApi.getReport).toHaveBeenCalledTimes(1);
  });

  it("notes in Chinese that the working papers are English-only", async () => {
    setAppLanguage("zh");
    await mountReports({ query: { id: ZAINAR_WARNINGS.id, paper: "countercase.md" } });
    expect(wrapper.get('[data-testid="viewer-paper-english-only"]').text()).toBe("工作底稿仅有英文版。");
  });

  it("shows one pane at a time below lg, with Back to the list", async () => {
    stubMatchMedia((query) => !query.includes("1024"));
    const { router } = await mountReports();
    expect(wrapper.find('[data-testid="reports-list"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="reports-viewer"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="reports-list"]').classes()).toContain("w-full");

    await articleFor(wrapper, KO_BUFFETT.id).trigger("click");
    await settle();
    expect(router.currentRoute.value.query.id).toBe(KO_BUFFETT.id);
    expect(wrapper.find('[data-testid="reports-list"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="reports-viewer"]').exists()).toBe(true);

    await wrapper.get('[data-testid="viewer-back"]').trigger("click");
    await settle();
    expect(router.currentRoute.value.query.id).toBeUndefined();
    expect(wrapper.find('[data-testid="reports-list"]').exists()).toBe(true);
  });

  it("takes the same viewer to full screen and back", async () => {
    await mountReports({ query: { id: ANTHROPIC_COMPLETE.id } });
    const viewerUid = wrapper.findComponent({ name: "DocumentViewerWindow" }).vm.$.uid;
    const fetchesBefore = fetch.mock.calls.length;

    await wrapper.get('[data-testid="viewer-fullscreen"]').trigger("click");
    await flushPromises();
    const layer = document.body.querySelector(".reports-viewer-fullscreen");
    expect(layer).not.toBeNull();
    expect(layer.parentElement).toBe(document.body);
    // The same component instance: nothing was re-fetched or re-rendered.
    expect(wrapper.findComponent({ name: "DocumentViewerWindow" }).vm.$.uid).toBe(viewerUid);
    expect(fetch.mock.calls.length).toBe(fetchesBefore);
    expect(layer.querySelector('[data-testid="viewer-fullscreen"]').getAttribute("aria-pressed")).toBe("true");

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(document.body.querySelector(".reports-viewer-fullscreen")).toBeNull();
  });

  it("says what each memo concludes: its call, its opening line and a clean company name", async () => {
    mockApi.listReports.mockResolvedValue([
      withReport(GOOGLE_PASS),
      withReport(OXY_PASS),
      withReport(PLACEHOLDER_FINANCIAL),
    ]);
    await mountReports({ query: { id: GOOGLE_PASS.id } });

    const google = articleFor(wrapper, GOOGLE_PASS.id);
    expect(google.get('[data-testid="report-verdict"]').text()).toBe("Pass · buy ≤ $215");
    expect(google.get('[data-testid="report-verdict"]').attributes("title")).toContain(
      "Buy price: $215 per share or less",
    );
    expect(google.get('[data-testid="report-headline"]').text()).toMatch(/^I think the core business/);
    // The EN / ZH chips that repeated the download links are gone; the links stay.
    const loose = google.findAll("span").filter((s) => ["EN", "ZH"].includes(s.text()) && !s.element.closest("a"));
    expect(loose).toHaveLength(0);
    expect(google.findAll('[data-testid^="report-download-"]')).toHaveLength(2);
    // A finished memo reads its review state, not "Ready".
    expect(google.get('[data-testid="report-review"]').text()).toBe("Draft");
    expect(google.text()).not.toContain("Ready");

    // EDGAR's state suffix is not part of the name.
    const oxy = articleFor(wrapper, OXY_PASS.id);
    expect(oxy.text()).toContain("Occidental Petroleum Corp");
    expect(oxy.text()).not.toContain("/De/");
    expect(oxy.get('[data-testid="report-verdict"]').text()).toBe("Pass · buy ≤ $45");

    // A placeholder record says plainly that it holds no document.
    const placeholder = articleFor(wrapper, PLACEHOLDER_FINANCIAL.id);
    expect(placeholder.get('[data-testid="report-status-docless"]').text()).toBe("No document");
    expect(placeholder.find('[data-testid="report-verdict"]').exists()).toBe(false);
    expect(placeholder.find('[data-testid^="report-download-"]').exists()).toBe(false);

    // The viewer header carries the call and the review state too.
    const meta = wrapper.get('[data-testid="viewer-meta"]');
    expect(meta.get('[data-testid="viewer-verdict"]').text()).toBe("Pass · buy ≤ $215");
    expect(meta.get('[data-testid="viewer-review"]').text()).toBe("Draft");
    expect(meta.get('[data-testid="viewer-freshness"]').text()).toMatch(/^Written Aug 25 · \d+ days ago$/);

    setAppLanguage("zh");
    await flushPromises();
    expect(google.get('[data-testid="report-verdict"]').text()).toBe("暂不买入 · 买入价 ≤ $215");
    expect(google.get('[data-testid="report-headline"]').text()).toMatch(/^我认为核心业务/);
    expect(placeholder.get('[data-testid="report-status-docless"]').text()).toBe("无文档");
  });

  it("finds memos by their call and headline", async () => {
    mockApi.listReports.mockResolvedValue([withReport(GOOGLE_PASS), withReport(OXY_PASS), withReport(ANTHROPIC_COMPLETE)]);
    await mountReports();
    await wrapper.find('input[type="text"]').setValue("franchises");
    await flushPromises();
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual([GOOGLE_PASS.id]);
  });

  it("folds older versions under the latest and marks a call that changed", async () => {
    mockApi.listReports.mockResolvedValue([
      withReport(GOOGLE_PASS),
      withReport(GOOGLE_BUY),
      withReport(CIENET_LATE_NEW),
      withReport(CIENET_LATE_OLD),
    ]);
    await mountReports();

    // Only the latest of each pair is on the list, tagged Latest.
    expect(wrapper.findAll("article").map((a) => a.attributes("data-report-id"))).toEqual([
      GOOGLE_PASS.id,
      CIENET_LATE_NEW.id,
    ]);
    const google = articleFor(wrapper, GOOGLE_PASS.id);
    expect(google.get('[data-testid="report-latest"]').text()).toBe("Latest");
    // The Buy → Pass flip 18 hours apart is an unstable call.
    const changed = google.get('[data-testid="report-changed-from"]');
    expect(changed.text()).toBe("Unstable call · was Buy");
    expect(changed.attributes("data-unstable")).toBe("true");
    expect(changed.attributes("title")).toContain("18 hours");
    // CIeNET's two memos made no call: no chip claims one changed.
    expect(articleFor(wrapper, CIENET_LATE_NEW.id).find('[data-testid="report-changed-from"]').exists()).toBe(false);

    const toggle = google.get('[data-testid="report-earlier-toggle"]');
    expect(toggle.text()).toBe("1 earlier version");
    await toggle.trigger("click");
    const older = articleFor(wrapper, GOOGLE_BUY.id);
    expect(older.attributes("data-nested")).toBe("true");
    expect(older.get('[data-testid="report-version"]').text()).toBe("Version 1 of 2");
    expect(older.get('[data-testid="report-verdict"]').text()).toBe("Buy · up to $360");
    expect(google.get('[data-testid="report-earlier-toggle"]').text()).toBe("Hide earlier versions");

    // A link to an older version opens its group.
    wrapper.unmount();
    await mountReports({ query: { id: CIENET_LATE_OLD.id } });
    expect(articleFor(wrapper, CIENET_LATE_OLD.id).exists()).toBe(true);
    expect(articleFor(wrapper, CIENET_LATE_OLD.id).attributes("data-selected")).toBe("true");
  });

  it("shows the review state and the open flags on a row", async () => {
    mockApi.listReports.mockResolvedValue([
      withReport(GOOGLE_PASS, {
        review_state: "approved",
        reviewer_name: "Bilel Harrat",
        reviewed_at: "2026-09-22T10:00:00+00:00",
        open_flags: 2,
        memo_quality_lint: { status: "passed", finding_count: 0, p0_count: 0, findings: [] },
      }),
    ]);
    await mountReports();
    const row = articleFor(wrapper, GOOGLE_PASS.id);
    expect(row.get('[data-testid="report-review"]').text()).toBe("Approved by Bilel Harrat");
    const flags = row.get('[data-testid="report-open-flags"]');
    expect(flags.text()).toBe("2");
    expect(flags.attributes("title")).toBe("2 open flags");
    // Next to the quality chip.
    const chips = row.findAll("span").map((s) => s.attributes("data-testid")).filter(Boolean);
    expect(chips.indexOf("report-open-flags")).toBe(chips.indexOf("quality-chip") + 1);
  });

  it("makes row downloads explicit exports, and hides them without memo:export", async () => {
    mockApi.listReports.mockResolvedValue([withReport(GOOGLE_PASS)]);
    await mountReports();
    const link = articleFor(wrapper, GOOGLE_PASS.id).get('[data-testid="report-download-zh"]');
    expect(link.attributes("href")).toBe(`/api/reports/${GOOGLE_PASS.id}/download?language=zh&artifact=memo&purpose=export`);
    // jsdom cannot follow a download; the click handler is what is under test.
    link.element.addEventListener("click", (event) => event.preventDefault());
    await link.trigger("click");
    expect(mockApi.recordReportEvent).toHaveBeenCalledWith(GOOGLE_PASS.id, "report_downloaded", {
      language: "zh",
      source: "reports_list:docx",
    });

    wrapper.unmount();
    resetReportSession();
    mockApi.me.mockResolvedValue({ role: "research_ops", permissions: ["memo:edit", "tasks:action"] });
    await mountReports({ query: { id: GOOGLE_PASS.id } });
    expect(articleFor(wrapper, GOOGLE_PASS.id).find('[data-testid^="report-download-"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="viewer-export"]').exists()).toBe(false);
  });

  it("keeps the IC memo from readers without edit access", async () => {
    const withIc = withReport(ANTHROPIC_COMPLETE, {
      download_urls: {
        ...ANTHROPIC_COMPLETE.download_urls,
        internal: `/api/reports/${ANTHROPIC_COMPLETE.id}/download?artifact=internal`,
      },
    });
    mockApi.listReports.mockResolvedValue([withIc]);
    mockApi.me.mockResolvedValue({ role: "guest", permissions: [] });
    await mountReports({ query: { id: withIc.id } });
    expect(wrapper.find('[data-testid="viewer-source-internal"]').exists()).toBe(false);
  });

  it("copies a report's link from the row menu", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    try {
      mockApi.listReports.mockResolvedValue([withReport(GOOGLE_PASS)]);
      await mountReports();
      const row = articleFor(wrapper, GOOGLE_PASS.id);
      await row.get('[data-testid="report-row-more"]').trigger("click");
      await row.get('[data-testid="report-copy-link"]').trigger("click");
      await flushPromises();
      expect(writeText).toHaveBeenCalledTimes(1);
      expect(writeText.mock.calls[0][0]).toMatch(new RegExp(`/reports\\?id=${GOOGLE_PASS.id}&lang=en$`));
      expect(row.get('[data-testid="report-copy-link"]').text()).toBe("Link copied");
    } finally {
      delete navigator.clipboard;
    }
  });

  it("records a report as opened once per report and language", async () => {
    await mountReports({ query: { id: KO_BUFFETT.id } });
    expect(mockApi.recordReportEvent).toHaveBeenCalledWith(KO_BUFFETT.id, "report_opened", {
      language: "en",
      source: "deep_link",
    });

    await articleFor(wrapper, ANTHROPIC_COMPLETE.id).trigger("click");
    await settle();
    expect(mockApi.recordReportEvent).toHaveBeenCalledWith(ANTHROPIC_COMPLETE.id, "report_opened", {
      language: "en",
      source: "reports_list",
    });
    // Back to the first report: already recorded this session.
    await articleFor(wrapper, KO_BUFFETT.id).trigger("click");
    await settle();
    const opens = mockApi.recordReportEvent.mock.calls.filter(
      ([id, event]) => id === KO_BUFFETT.id && event === "report_opened",
    );
    expect(opens).toHaveLength(1);
  });
});
