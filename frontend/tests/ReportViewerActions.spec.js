import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

const mockApi = vi.hoisted(() => ({
  me: vi.fn(),
  recordReportEvent: vi.fn(),
  setReportReview: vi.fn(),
  listReportComments: vi.fn(),
  addReportComment: vi.fn(),
  resolveReportComment: vi.fn(),
  getReportDiff: vi.fn(),
  cancelReportRun: vi.fn(),
  resumeReport: vi.fn(),
  dismissReport: vi.fn(),
  listActiveJobs: vi.fn(),
  reportExportUrl: (id, language = "en", artifact = "memo") =>
    `/api/reports/${id}/download?language=${language}&artifact=${artifact}&purpose=export`,
  reportPdfUrl: (id, language = "en", artifact = "memo") =>
    `/api/reports/${id}/preview?language=${language}&artifact=${artifact}`,
  reportBundleUrl: (id, format = "all") => `/api/reports/${id}/bundle?format=${format}`,
}));

vi.mock("../src/api.js", () => ({
  api: mockApi,
  default: mockApi,
  withApiToken: (path) => path,
}));

import DocumentViewerWindow from "../src/components/DocumentViewerWindow.vue";
import { resetReportSession } from "../src/components/reports/reportSession.js";
import { setAppLanguage } from "../src/state.js";
import { ZAINAR_WARNINGS, withReport } from "./fixtures/reportSummaries.js";
import { GOOGLE_BUY, GOOGLE_PASS } from "./fixtures/reportReader.js";

const ALL = ["memo:approve", "memo:edit", "memo:export", "tasks:action"];

function fetchResponse() {
  return {
    ok: true,
    status: 200,
    text: async () => "",
    arrayBuffer: async () => new ArrayBuffer(8),
  };
}

function sourcesFor(report, { pdf = {} } = {}) {
  return Object.entries(report.download_urls || {}).map(([key, url]) => ({
    key: key.toUpperCase(),
    label: key.toUpperCase(),
    url,
    kind: "docx",
    pdfUrl: pdf[key] || "",
  }));
}

let wrapper;

function mountViewer(props = {}) {
  const report = props.report || withReport(GOOGLE_PASS);
  wrapper = mount(DocumentViewerWindow, {
    attachTo: document.body,
    props: {
      title: "Google — Buffett-Method Memo",
      companyName: "Google",
      reportId: report.id,
      sources: sourcesFor(report),
      initialKey: "EN",
      report,
      permissions: ALL,
      ...props,
    },
    global: { stubs: { RouterLink: true } },
  });
  return wrapper;
}

const settle = async () => {
  await flushPromises();
  await new Promise((resolve) => setTimeout(resolve, 20));
  await flushPromises();
};

describe("DocumentViewerWindow — what the memo concludes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetReportSession();
    window.localStorage.clear();
    setAppLanguage("en");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fetchResponse())));
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-22T12:00:00"));
    mockApi.recordReportEvent.mockResolvedValue({ recorded: true });
    mockApi.listReportComments.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.useRealTimers();
    setAppLanguage("en");
  });

  it("puts the call, the review and the memo's age under the header", async () => {
    mountViewer();
    await settle();
    const meta = wrapper.get('[data-testid="viewer-meta"]');
    expect(meta.get('[data-testid="viewer-verdict"]').text()).toBe("Pass · buy ≤ $215");
    expect(meta.get('[data-testid="viewer-review"]').text()).toBe("Draft");
    const freshness = meta.get('[data-testid="viewer-freshness"]');
    expect(freshness.text()).toBe("Written Aug 25 · 28 days ago");
    expect(freshness.attributes("data-stale")).toBe("false");
    // The flip from Buy, 18 hours after the earlier memo.
    const changed = meta.get('[data-testid="viewer-changed-from"]');
    expect(changed.text()).toBe("Unstable call · was Buy");
    expect(changed.attributes("title")).toBe("The call flipped 18 hours after the previous memo.");

    setAppLanguage("zh");
    await flushPromises();
    expect(meta.get('[data-testid="viewer-verdict"]').text()).toBe("暂不买入 · 买入价 ≤ $215");
    expect(meta.get('[data-testid="viewer-freshness"]').text()).toBe("撰写于 8月25日 · 28 天前");
  });

  it("names a stale latest source and turns the line amber after 30 days", async () => {
    vi.setSystemTime(new Date("2026-10-05T12:00:00"));
    const report = withReport(ZAINAR_WARNINGS, {
      reader: { memo_as_of: "2026-08-31", evidence_latest: "2026-06-13", sources_dated: 10, sources_total: 10 },
    });
    mountViewer({ report, sources: sourcesFor(report) });
    await settle();
    const freshness = wrapper.get('[data-testid="viewer-freshness"]');
    expect(freshness.text()).toBe("Written Aug 31 · 35 days ago · latest source Jun 13");
    expect(freshness.attributes("data-stale")).toBe("true");
    expect(freshness.classes()).toContain("text-warning-ink");
  });

  it("draws the header logo from the same identity as the list row", async () => {
    const report = withReport(GOOGLE_PASS, {
      company_identity: { id: "google-llc", name: "Google", logo_domain: "abc.xyz", ticker: "GOOGL" },
    });
    mountViewer({ report, companyId: "google-llc" });
    await settle();
    const logo = wrapper.findAllComponents({ name: "Monogram" }).find((m) => m.attributes("data-testid") === "viewer-logo");
    expect(logo.props("company")).toMatchObject({
      id: "google-llc",
      name: "Google",
      logo_url: GOOGLE_PASS.logo_url,
      logo_domain: GOOGLE_PASS.logo_domain,
      company_identity: { logo_domain: "abc.xyz", ticker: "GOOGL" },
    });
    wrapper.unmount();

    // The page's own company object wins when it hands one over.
    mountViewer({ report, companyId: "google-llc", company: { id: "google-llc", name: "Google", logo_url: "/logo.svg" } });
    await settle();
    const handed = wrapper.findAllComponents({ name: "Monogram" }).find((m) => m.attributes("data-testid") === "viewer-logo");
    expect(handed.props("company").logo_url).toBe("/logo.svg");
  });

  it("says when the documents could not be re-stamped", async () => {
    const report = withReport(GOOGLE_PASS, { review_state: "approved", reviewer_name: "Ada", review_render_status: "failed" });
    mountViewer({ report });
    await settle();
    expect(wrapper.get('[data-testid="viewer-review"]').text()).toBe("Approved by Ada");
    const note = wrapper.get('[data-testid="viewer-review-render"]');
    expect(note.text()).toBe("Not re-stamped");
    expect(note.attributes("title")).toContain("could not be re-stamped");
  });
});

describe("DocumentViewerWindow — PDF, export, print and share", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetReportSession();
    window.localStorage.clear();
    setAppLanguage("en");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fetchResponse())));
    mockApi.recordReportEvent.mockResolvedValue({ recorded: true });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  it("opens a ready PDF in the browser's own viewer, and keeps the web render one click away", async () => {
    const report = withReport(GOOGLE_PASS, { pdf_status: { en: "ready", zh: "pending" } });
    mountViewer({
      report,
      sources: sourcesFor(report, { pdf: { en: "/api/reports/3cb7ec52fa15/preview?language=en&artifact=memo" } }),
    });
    await settle();
    const frame = wrapper.get('[data-testid="viewer-pdf"]');
    expect(frame.attributes("src")).toBe("/api/reports/3cb7ec52fa15/preview?language=en&artifact=memo");
    // The docx was never fetched: the PDF needs no second download.
    expect(fetch).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="viewer-mode-pdf"]').attributes("aria-pressed")).toBe("true");
    // Opened once the PDF loads.
    await frame.trigger("load");
    expect(mockApi.recordReportEvent).toHaveBeenCalledWith(report.id, "report_opened", {
      language: "en",
      source: "reports_viewer",
    });

    await wrapper.get('[data-testid="viewer-mode-web"]').trigger("click");
    await settle();
    expect(fetch).toHaveBeenCalledWith(report.download_urls.en);
    expect(wrapper.find('[data-testid="viewer-pdf"]').exists()).toBe(false);
    expect(window.localStorage.getItem("bsh.docViewerMode")).toBe("web");

    // Chinese has no PDF yet: it renders the docx, whatever the mode.
    await wrapper.get('[data-testid="viewer-mode-pdf"]').trigger("click");
    await settle();
    expect(wrapper.find('[data-testid="viewer-pdf"]').exists()).toBe(true);
    await wrapper.get('[data-testid="viewer-source-zh"]').trigger("click");
    await settle();
    expect(wrapper.find('[data-testid="viewer-pdf"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="viewer-mode"]').exists()).toBe(false);
    expect(fetch).toHaveBeenLastCalledWith(report.download_urls.zh);
  });

  it("renders a source of kind pdf as the PDF", async () => {
    mountViewer({
      report: null,
      sources: [{ key: "PDF", url: "/files/deck.pdf", kind: "pdf" }],
    });
    await settle();
    expect(wrapper.get('[data-testid="viewer-pdf"]').attributes("src")).toBe("/files/deck.pdf");
  });

  it("offers PDF, Word and both languages as explicit, logged exports", async () => {
    const report = withReport(GOOGLE_PASS, { pdf_status: { en: "ready", zh: "pending" } });
    mountViewer({ report });
    await settle();
    await wrapper.get('[data-testid="viewer-export"]').trigger("click");
    const menu = wrapper.get('[data-testid="viewer-export-menu"]');
    const pdf = menu.get('[data-testid="viewer-export-pdf"]');
    expect(pdf.text()).toContain("PDF (for sharing)");
    expect(pdf.attributes("href")).toBe(`/api/reports/${report.id}/preview?language=en&artifact=memo&purpose=export`);
    expect(pdf.attributes("download")).toBe("");
    expect(menu.get('[data-testid="viewer-export-docx"]').attributes("href")).toBe(
      `/api/reports/${report.id}/download?language=en&artifact=memo&purpose=export`,
    );
    // Only English has a PDF, so the bundle is the two Word files.
    const zip = menu.get('[data-testid="viewer-export-zip"]');
    expect(zip.text()).toContain("Both languages (.zip)");
    expect(zip.attributes("href")).toBe(`/api/reports/${report.id}/bundle?format=docx`);

    pdf.element.addEventListener("click", (event) => event.preventDefault());
    await pdf.trigger("click");
    expect(mockApi.recordReportEvent).toHaveBeenCalledWith(report.id, "report_downloaded", {
      language: "en",
      source: "reports_viewer:pdf",
    });
    expect(wrapper.find('[data-testid="viewer-export-menu"]').exists()).toBe(false);
  });

  it("drops the PDF option until its PDF is ready, and hides Export without memo:export", async () => {
    mountViewer();
    await settle();
    await wrapper.get('[data-testid="viewer-export"]').trigger("click");
    expect(wrapper.find('[data-testid="viewer-export-pdf"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="viewer-export-docx"]').exists()).toBe(true);
    wrapper.unmount();

    mountViewer({ permissions: ["memo:edit"] });
    await settle();
    expect(wrapper.find('[data-testid="viewer-export"]').exists()).toBe(false);
  });

  it("exports the IC memo as its own Word file", async () => {
    const report = withReport(GOOGLE_PASS, {
      download_urls: { ...GOOGLE_PASS.download_urls, internal: "/api/reports/3cb7ec52fa15/download?artifact=internal" },
    });
    mountViewer({ report, initialKey: "INTERNAL", sources: sourcesFor(report) });
    await settle();
    await wrapper.get('[data-testid="viewer-export"]').trigger("click");
    const items = wrapper.findAll('[data-testid^="viewer-export-"]').filter((el) => el.element.tagName === "A");
    expect(items.map((el) => el.attributes("href"))).toEqual([
      `/api/reports/${report.id}/download?language=en&artifact=internal&purpose=export`,
    ]);
  });

  it("prints the PDF itself, or the page with only the document on it", async () => {
    const report = withReport(GOOGLE_PASS, { pdf_status: { en: "ready" } });
    mountViewer({ report, sources: sourcesFor(report, { pdf: { en: "/pdf-en" } }) });
    await settle();
    const frameWindow = wrapper.get('[data-testid="viewer-pdf"]').element.contentWindow;
    const framePrint = vi.spyOn(frameWindow, "print").mockImplementation(() => {});
    await wrapper.get('[data-testid="viewer-more"]').trigger("click");
    await wrapper.get('[data-testid="viewer-print"]').trigger("click");
    expect(framePrint).toHaveBeenCalledTimes(1);

    await wrapper.get('[data-testid="viewer-mode-web"]').trigger("click");
    await settle();
    let printAttr = "";
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      printAttr = document.documentElement.dataset.bshPrint;
    });
    await wrapper.get('[data-testid="viewer-more"]').trigger("click");
    await wrapper.get('[data-testid="viewer-print"]').trigger("click");
    expect(print).toHaveBeenCalledTimes(1);
    expect(printAttr).toBe("document");
    // The docx render is what the print rules keep.
    expect(wrapper.get('[data-testid="viewer-docx"]').classes()).toContain("doc-print-target");
    window.dispatchEvent(new Event("afterprint"));
    expect(document.documentElement.dataset.bshPrint).toBeUndefined();
    print.mockRestore();
  });

  it("copies the report's link in the language on screen", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    try {
      mountViewer({ initialKey: "ZH" });
      await settle();
      await wrapper.get('[data-testid="viewer-more"]').trigger("click");
      await wrapper.get('[data-testid="viewer-copy-link"]').trigger("click");
      await flushPromises();
      expect(writeText.mock.calls[0][0]).toMatch(/\/reports\?id=3cb7ec52fa15&lang=zh$/);
      expect(wrapper.get('[data-testid="viewer-copy-link"]').text()).toBe("Link copied");
    } finally {
      delete navigator.clipboard;
    }
  });
});

describe("DocumentViewerWindow — review", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetReportSession();
    window.localStorage.clear();
    setAppLanguage("en");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fetchResponse())));
    mockApi.recordReportEvent.mockResolvedValue({ recorded: true });
    mockApi.setReportReview.mockResolvedValue({ ...GOOGLE_PASS, review_state: "approved" });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  async function openMore() {
    await wrapper.get('[data-testid="viewer-more"]').trigger("click");
  }

  it("offers approvers every move and analysts only a review request", async () => {
    mountViewer();
    await settle();
    await openMore();
    expect(wrapper.findAll('[data-testid^="viewer-review-"]').map((b) => b.attributes("data-testid"))).toEqual([
      "viewer-review-in_review",
      "viewer-review-approved",
      "viewer-review-withdrawn",
    ]);
    wrapper.unmount();

    mountViewer({ permissions: ["memo:edit", "memo:export"] });
    await settle();
    await openMore();
    expect(wrapper.findAll('[data-testid^="viewer-review-"]').map((b) => b.text())).toEqual(["Request review"]);
  });

  it("asks twice, then approves and tells the page", async () => {
    mountViewer();
    await settle();
    await openMore();
    const approve = wrapper.get('[data-testid="viewer-review-approved"]');
    await approve.trigger("click");
    expect(mockApi.setReportReview).not.toHaveBeenCalled();
    expect(approve.text()).toBe("Click again to approve");
    await approve.trigger("click");
    await flushPromises();
    expect(mockApi.setReportReview).toHaveBeenCalledWith(GOOGLE_PASS.id, { state: "approved" });
    expect(wrapper.emitted("report-changed").at(-1)[0]).toMatchObject({ action: "review", state: "approved" });
  });

  it("offers to approve anyway when comments or flags are open", async () => {
    const conflict = Object.assign(new Error("409 Conflict"), {
      status: 409,
      detail: { detail: "2 open comment(s) or flag(s) on this memo. Resolve them, or approve with acknowledge_open_comments." },
    });
    mockApi.setReportReview.mockRejectedValueOnce(conflict);
    mountViewer({ report: withReport(GOOGLE_PASS, { open_flags: 1, open_comments: 1 }) });
    await settle();
    await openMore();
    const approve = wrapper.get('[data-testid="viewer-review-approved"]');
    await approve.trigger("click");
    await approve.trigger("click");
    await flushPromises();

    const prompt = wrapper.get('[data-testid="viewer-review-prompt"]');
    expect(prompt.text()).toContain("2 comments or flags on this memo are still open.");
    await prompt.get('[data-testid="viewer-review-confirm"]').trigger("click");
    await flushPromises();
    expect(mockApi.setReportReview).toHaveBeenLastCalledWith(GOOGLE_PASS.id, {
      state: "approved",
      acknowledgeOpenComments: true,
    });
    expect(wrapper.find('[data-testid="viewer-review-prompt"]').exists()).toBe(false);
  });

  it("offers to re-stamp anyway when ink would drift", async () => {
    mockApi.setReportReview.mockRejectedValueOnce(
      Object.assign(new Error("409"), {
        status: 409,
        detail: { detail: "This memo has ink annotations that would drift on the re-stamped document. Send force=true to move the ink aside and re-render." },
      }),
    );
    mountViewer({ report: withReport(GOOGLE_PASS, { review_state: "approved" }) });
    await settle();
    await openMore();
    const withdraw = wrapper.get('[data-testid="viewer-review-withdrawn"]');
    await withdraw.trigger("click");
    await withdraw.trigger("click");
    await flushPromises();
    const prompt = wrapper.get('[data-testid="viewer-review-prompt"]');
    expect(prompt.text()).toContain("Someone has ink on this memo.");
    expect(prompt.get('[data-testid="viewer-review-confirm"]').text()).toBe("Re-stamp anyway");
    await prompt.get('[data-testid="viewer-review-confirm"]').trigger("click");
    await flushPromises();
    expect(mockApi.setReportReview).toHaveBeenLastCalledWith(GOOGLE_PASS.id, { state: "withdrawn", force: true });
  });

  it("says plainly when a review move fails", async () => {
    mockApi.setReportReview.mockRejectedValueOnce(
      Object.assign(new Error("403"), { status: 403, detail: { detail: "Permission denied: memo:approve" } }),
    );
    mountViewer();
    await settle();
    await openMore();
    const request = wrapper.get('[data-testid="viewer-review-in_review"]');
    await request.trigger("click");
    await request.trigger("click");
    await flushPromises();
    const prompt = wrapper.get('[data-testid="viewer-review-prompt"]');
    expect(prompt.text()).toContain("The review change didn't go through.");
    expect(prompt.find('[data-testid="viewer-review-confirm"]').exists()).toBe(false);
    await prompt.get('[data-testid="viewer-review-dismiss"]').trigger("click");
    expect(wrapper.find('[data-testid="viewer-review-prompt"]').exists()).toBe(false);
  });

  it("compares with the previous version from the line under the header", async () => {
    mockApi.getReportDiff.mockResolvedValue({
      report_id: GOOGLE_PASS.id,
      against_id: GOOGLE_BUY.id,
      current: { id: GOOGLE_PASS.id, created_at: GOOGLE_PASS.created_at },
      previous: { id: GOOGLE_BUY.id, created_at: GOOGLE_BUY.created_at },
      days_apart: 0.76,
      verdict: { current: "Pass", previous: "Buy", changed: true, unstable: true },
      tables: [],
      sources: null,
      spine: null,
      buffett: null,
      notes: [],
    });
    mountViewer({ previousVersion: withReport(GOOGLE_BUY) });
    await settle();
    const toggle = wrapper.get('[data-testid="viewer-changes-toggle"]');
    expect(toggle.attributes("title")).toMatch(/^Changes since Aug 2[45]$/);
    await toggle.trigger("click");
    await settle();
    expect(mockApi.getReportDiff).toHaveBeenCalledWith(GOOGLE_PASS.id, GOOGLE_BUY.id);
    expect(wrapper.get('[data-testid="viewer-side-panel"]').attributes("data-panel")).toBe("changes");
    expect(wrapper.get('[data-testid="changes-verdict"]').text()).toContain("Buy");
    expect(wrapper.get('[data-testid="changes-verdict"]').text()).toContain("Pass");
  });
});
