import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

const mockApi = vi.hoisted(() => ({
  me: vi.fn(),
  recordReportEvent: vi.fn(),
  listReportComments: vi.fn(),
  addReportComment: vi.fn(),
  resolveReportComment: vi.fn(),
  setReportReview: vi.fn(),
  getReportDiff: vi.fn(),
  reportExportUrl: (id, language = "en") => `/api/reports/${id}/download?language=${language}&purpose=export`,
  reportPdfUrl: (id, language = "en") => `/api/reports/${id}/preview?language=${language}`,
  reportBundleUrl: (id, format = "all") => `/api/reports/${id}/bundle?format=${format}`,
}));

vi.mock("../src/api.js", () => ({
  api: mockApi,
  default: mockApi,
  withApiToken: (path) => path,
}));

import ReportCommentsPanel from "../src/components/reports/ReportCommentsPanel.vue";
import DocumentViewerWindow from "../src/components/DocumentViewerWindow.vue";
import DocumentViewerDrawer from "../src/components/DocumentViewerDrawer.vue";
import { resetReportSession, sessionPermissions } from "../src/components/reports/reportSession.js";
import { setAppLanguage } from "../src/state.js";
import { withReport } from "./fixtures/reportSummaries.js";
import { GOOGLE_PASS } from "./fixtures/reportReader.js";

// Comments as the firm store keeps them (server/firm.py add_comment).
const COMMENTS = () => ({
  report_id: GOOGLE_PASS.id,
  items: [
    {
      id: "cmt-flag000001",
      author: "bilel@bsh.example",
      author_handle: "bilel",
      text: "Flagged: wrong number",
      target: { kind: "section", ref: GOOGLE_PASS.id, label: "I. Investment Decision" },
      parent_id: null,
      created_at: "2026-09-22T10:00:00Z",
      resolved_at: null,
      resolved_by: null,
      flag: "wrong_number",
      quote: "roughly $349 a share and about $4.3 trillion of equity value",
      language: "en",
    },
    {
      id: "cmt-note000002",
      author: "ada@bsh.example",
      author_handle: "ada",
      text: "Check the buy price against the June quote.",
      target: { kind: "report", ref: GOOGLE_PASS.id, label: "" },
      parent_id: null,
      created_at: "2026-09-22T11:00:00Z",
      resolved_at: null,
      resolved_by: null,
    },
    {
      id: "cmt-reply00003",
      author: "bilel@bsh.example",
      author_handle: "bilel",
      text: "Done — it matches.",
      target: { kind: "report", ref: GOOGLE_PASS.id, label: "" },
      parent_id: "cmt-note000002",
      created_at: "2026-09-22T11:30:00Z",
      resolved_at: null,
      resolved_by: null,
    },
    {
      id: "cmt-old0000004",
      author: "ada@bsh.example",
      author_handle: "ada",
      text: "Tone is fine now.",
      target: { kind: "report", ref: GOOGLE_PASS.id, label: "" },
      parent_id: null,
      created_at: "2026-09-21T09:00:00Z",
      resolved_at: "2026-09-21T12:00:00Z",
      resolved_by: "bilel@bsh.example",
      flag: "tone",
    },
  ],
  open_count: 2,
  open_comments: 1,
  open_flags: 1,
});

let wrapper;

describe("ReportCommentsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
    mockApi.listReportComments.mockResolvedValue(COMMENTS());
    mockApi.addReportComment.mockResolvedValue({ id: "cmt-new" });
    mockApi.resolveReportComment.mockResolvedValue({ id: "cmt-flag000001" });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  function mountPanel(props = {}) {
    wrapper = mount(ReportCommentsPanel, {
      props: {
        report: withReport(GOOGLE_PASS),
        language: "en",
        section: { key: "bsh_sec_2", label: "II. The Business" },
        canEdit: true,
        ...props,
      },
    });
    return wrapper;
  }

  it("lists open comments and flags with their quote and section, resolved ones folded", async () => {
    mountPanel();
    await flushPromises();
    expect(mockApi.listReportComments).toHaveBeenCalledWith(GOOGLE_PASS.id);
    const items = wrapper.findAll('[data-testid="comment-item"]');
    expect(items).toHaveLength(2);
    const flag = items[0];
    expect(flag.get('[data-testid="comment-flag"]').text()).toBe("Wrong number");
    expect(flag.get('[data-testid="comment-quote"]').text()).toContain("roughly $349 a share");
    expect(flag.get('[data-testid="comment-section"]').text()).toBe("I. Investment Decision");
    expect(flag.text()).toContain("@bilel");
    expect(flag.text()).toContain("English");
    // The reply sits under its comment.
    expect(items[1].text()).toContain("Done — it matches.");
    expect(wrapper.find('[data-testid="comment-resolved"]').exists()).toBe(false);

    await wrapper.get('[data-testid="comments-toggle-resolved"]').trigger("click");
    const resolved = wrapper.get('[data-testid="comment-resolved"]');
    expect(resolved.text()).toContain("Tone is fine now.");
    expect(resolved.text()).toContain("Resolved by bilel@bsh.example");

    await flag.get('[data-testid="comment-section"]').trigger("click");
    expect(wrapper.emitted("go-to-section")[0]).toEqual(["I. Investment Decision"]);
  });

  it("adds a comment tied to the section on screen, or to the whole report", async () => {
    mountPanel();
    await flushPromises();
    await wrapper.get('[data-testid="comment-text"]').setValue("The owner-earnings bridge skips D&A.");
    await wrapper.get('[data-testid="comment-form"]').trigger("submit");
    await flushPromises();
    expect(mockApi.addReportComment).toHaveBeenCalledWith(GOOGLE_PASS.id, {
      text: "The owner-earnings bridge skips D&A.",
      kind: "section",
      label: "II. The Business",
      language: "en",
    });
    expect(wrapper.emitted("changed")).toBeTruthy();
    expect(mockApi.listReportComments).toHaveBeenCalledTimes(2);

    await wrapper.get('[data-testid="comment-on-section"]').setValue(false);
    expect(wrapper.get('[data-testid="comment-target"]').text()).toBe("On the whole report");
    await wrapper.get('[data-testid="comment-text"]').setValue("General note.");
    await wrapper.get('[data-testid="comment-send"]').trigger("click");
    await wrapper.get('[data-testid="comment-form"]').trigger("submit");
    await flushPromises();
    expect(mockApi.addReportComment).toHaveBeenLastCalledWith(GOOGLE_PASS.id, {
      text: "General note.",
      kind: "report",
      label: "",
      language: "en",
    });
  });

  it("resolves a comment", async () => {
    mountPanel();
    await flushPromises();
    await wrapper.findAll('[data-testid="comment-resolve"]')[0].trigger("click");
    await flushPromises();
    expect(mockApi.resolveReportComment).toHaveBeenCalledWith(GOOGLE_PASS.id, "cmt-flag000001");
    expect(wrapper.emitted("changed")).toBeTruthy();
  });

  it("is read-only without edit access", async () => {
    mountPanel({ canEdit: false });
    await flushPromises();
    expect(wrapper.find('[data-testid="comment-form"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="comment-resolve"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="comments-read-only"]').text()).toBe("Adding comments and flags needs edit access.");
  });

  it("posts a flag with its quote, type, section and language", async () => {
    mountPanel({
      flagDraft: { quote: "It is about 2% of a single quarter's run-rate.", label: "V. Risks", language: "zh" },
    });
    await flushPromises();
    const form = wrapper.get('[data-testid="flag-form"]');
    expect(form.get('[data-testid="flag-quote"]').text()).toBe("It is about 2% of a single quarter's run-rate.");
    expect(form.get('[data-testid="flag-where"]').text()).toBe("V. Risks · Chinese document");
    await form.get('[data-testid="flag-type-unsupported"]').trigger("click");
    expect(form.get('[data-testid="flag-type-unsupported"]').attributes("aria-checked")).toBe("true");
    await form.get('[data-testid="flag-note"]').setValue("No source for 2%.");
    await form.trigger("submit");
    await flushPromises();
    expect(mockApi.addReportComment).toHaveBeenCalledWith(GOOGLE_PASS.id, {
      text: "No source for 2%.",
      kind: "section",
      label: "V. Risks",
      flag: "unsupported",
      quote: "It is about 2% of a single quarter's run-rate.",
      language: "zh",
    });
    expect(wrapper.emitted("flag-done")[0]).toEqual([{ sent: true }]);
  });

  it("speaks Chinese", async () => {
    setAppLanguage("zh");
    mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain("评论与标记");
    expect(wrapper.get('[data-testid="comment-flag"]').text()).toBe("数字有误");
    setAppLanguage("en");
  });
});

// jsdom has no layout: paragraphs sit where data-y says, relative to the
// viewer's scroll offset.
function layoutByDataY() {
  const original = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function getBoundingClientRect() {
    if (this.dataset && this.dataset.y !== undefined) {
      const area = this.closest('[data-testid="viewer-scroll"]');
      const top = Number(this.dataset.y) - (area ? area.scrollTop : 0);
      return { top, bottom: top + 20, left: 0, right: 600, width: 600, height: 20, x: 0, y: top };
    }
    return original.call(this);
  };
  return () => {
    HTMLElement.prototype.getBoundingClientRect = original;
  };
}

const PAGE = `
  <div class="docx-wrapper"><section class="docx" style="width: 612pt">
    <p data-y="0">Cover</p>
    <p data-y="100"><span id="bsh_sec_1"></span><span>I. EXECUTIVE SUMMARY</span></p>
    <p data-y="200" id="first-body">We recommend participating in the SPV.</p>
    <p data-y="900"><span id="bsh_sec_2"></span><span>II. COMPANY OVERVIEW</span></p>
    <p data-y="1000" id="second-body">ZaiNar reported $12M of revenue in 2025.</p>
  </section></div>`;

function selectText(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

describe("Flagging a passage in the viewer", () => {
  let restoreLayout;

  beforeEach(() => {
    vi.clearAllMocks();
    resetReportSession();
    setAppLanguage("en");
    window.localStorage.clear();
    restoreLayout = layoutByDataY();
    docx.renderAsync.mockImplementation((_buffer, container) => {
      container.innerHTML = PAGE;
      return Promise.resolve();
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(8), text: async () => "" }),
      ),
    );
    mockApi.recordReportEvent.mockResolvedValue({ recorded: true });
    mockApi.listReportComments.mockResolvedValue({ items: [] });
    mockApi.addReportComment.mockResolvedValue({ id: "cmt-new" });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    restoreLayout();
    window.getSelection().removeAllRanges();
    docx.renderAsync.mockImplementation(() => Promise.resolve());
  });

  async function mountViewer(permissions) {
    const report = withReport(GOOGLE_PASS);
    wrapper = mount(DocumentViewerWindow, {
      attachTo: document.body,
      props: {
        title: "Memo",
        reportId: report.id,
        report,
        permissions,
        sources: [
          { key: "EN", label: "EN", url: report.download_urls.en, kind: "docx" },
          { key: "ZH", label: "ZH", url: report.download_urls.zh, kind: "docx" },
        ],
      },
      global: { stubs: { RouterLink: true } },
    });
    await flushPromises();
    await new Promise((resolve) => setTimeout(resolve, 30));
    await flushPromises();
  }

  it("flags selected text under its heading, in the language on screen", async () => {
    await mountViewer(["memo:edit"]);
    const area = wrapper.get('[data-testid="viewer-scroll"]');
    selectText(area.element.querySelector("#second-body"));
    await area.trigger("mouseup");
    const button = wrapper.get('[data-testid="viewer-flag-selection"]');
    expect(button.text()).toBe("Flag");

    await button.trigger("click");
    await flushPromises();
    const panel = wrapper.get('[data-testid="viewer-side-panel"]');
    expect(panel.attributes("data-panel")).toBe("comments");
    expect(panel.get('[data-testid="flag-quote"]').text()).toBe("ZaiNar reported $12M of revenue in 2025.");
    expect(panel.get('[data-testid="flag-where"]').text()).toBe("II. COMPANY OVERVIEW · English document");

    await panel.get('[data-testid="flag-form"]').trigger("submit");
    await flushPromises();
    expect(mockApi.addReportComment).toHaveBeenCalledWith(GOOGLE_PASS.id, {
      text: "",
      kind: "section",
      label: "II. COMPANY OVERVIEW",
      flag: "wrong_number",
      quote: "ZaiNar reported $12M of revenue in 2025.",
      language: "en",
    });
    expect(wrapper.find('[data-testid="flag-form"]').exists()).toBe(false);
    // The list reloads; the page hears about it so the row's count updates.
    expect(wrapper.emitted("report-changed").some(([payload]) => payload.action === "comments")).toBe(true);
  });

  it("offers no Flag without edit access, and none for a selection outside the memo", async () => {
    await mountViewer(["memo:export"]);
    const area = wrapper.get('[data-testid="viewer-scroll"]');
    selectText(area.element.querySelector("#first-body"));
    await area.trigger("mouseup");
    expect(wrapper.find('[data-testid="viewer-flag-selection"]').exists()).toBe(false);
    wrapper.unmount();

    await mountViewer(["memo:edit"]);
    selectText(wrapper.get("header").element);
    await wrapper.get('[data-testid="viewer-scroll"]').trigger("mouseup");
    expect(wrapper.find('[data-testid="viewer-flag-selection"]').exists()).toBe(false);
  });

  it("opens the comments from the line under the header, with the open count", async () => {
    const report = withReport(GOOGLE_PASS, { open_comments: 1, open_flags: 2 });
    wrapper = mount(DocumentViewerWindow, {
      attachTo: document.body,
      props: {
        title: "Memo",
        report,
        permissions: ["memo:edit"],
        sources: [{ key: "EN", url: report.download_urls.en, kind: "docx" }],
      },
      global: { stubs: { RouterLink: true } },
    });
    await flushPromises();
    const toggle = wrapper.get('[data-testid="viewer-comments-toggle"]');
    expect(toggle.get('[data-testid="viewer-comments-count"]').text()).toBe("3");
    await toggle.trigger("click");
    await flushPromises();
    expect(wrapper.get('[data-testid="comments-panel"]').exists()).toBe(true);
    expect(mockApi.listReportComments).toHaveBeenCalledWith(GOOGLE_PASS.id);
  });
});

describe("Flagging a passage in the drawer", () => {
  let restoreLayout;

  beforeEach(() => {
    vi.clearAllMocks();
    resetReportSession();
    restoreLayout = layoutByDataY();
    docx.renderAsync.mockImplementation((_buffer, container) => {
      container.innerHTML = PAGE;
      return Promise.resolve();
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(8), text: async () => "" }),
      ),
    );
    mockApi.addReportComment.mockResolvedValue({ id: "cmt-new" });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    restoreLayout();
    window.getSelection().removeAllRanges();
    docx.renderAsync.mockImplementation(() => Promise.resolve());
  });

  it("finds the memo from its URL, and flags a selection", async () => {
    mockApi.me.mockResolvedValue({ permissions: ["memo:edit", "memo:export"] });
    // The real Teleport (to body): VTU's teleport stub swaps the element the
    // docx was rendered into, so the drawer is read through the document.
    wrapper = mount(DocumentViewerDrawer, {
      attachTo: document.body,
      props: {
        title: "Google — Memo",
        sources: [
          { key: "EN", url: "/api/reports/3cb7ec52fa15/download?language=en", kind: "docx" },
          { key: "ZH", url: "/api/reports/3cb7ec52fa15/download?language=zh", kind: "docx" },
          { key: "INTERNAL", url: "/api/reports/3cb7ec52fa15/download?artifact=internal", kind: "docx" },
        ],
      },
    });
    await flushPromises();
    await new Promise((resolve) => setTimeout(resolve, 30));
    await flushPromises();
    const $ = (selector) => document.body.querySelector(selector);
    expect(sessionPermissions.value).toEqual(["memo:edit", "memo:export"]);
    // The internal document is the IC memo.
    expect($('[data-testid="drawer-source-internal"]').textContent.trim()).toBe("IC memo");
    // Its Export is an explicit export.
    expect($('[data-testid="drawer-export"]').getAttribute("href")).toBe(
      "/api/reports/3cb7ec52fa15/download?language=en&purpose=export",
    );

    const area = $('[data-testid="drawer-scroll"]');
    selectText(area.querySelector("#first-body"));
    area.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    await flushPromises();
    $('[data-testid="drawer-flag-selection"]').click();
    await flushPromises();
    $('[data-testid="flag-type-unclear"]').click();
    await flushPromises();
    $('[data-testid="flag-form"]').dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flushPromises();
    expect(mockApi.addReportComment).toHaveBeenCalledWith("3cb7ec52fa15", {
      text: "",
      kind: "section",
      label: "I. EXECUTIVE SUMMARY",
      flag: "unclear",
      quote: "We recommend participating in the SPV.",
      language: "en",
    });
    expect($('[data-testid="drawer-flag-sent"]').textContent.trim()).toBe("Flagged. It's in the comments.");
  });

  it("hides a memo's Export without memo:export", async () => {
    mockApi.me.mockResolvedValue({ permissions: ["memo:edit"] });
    wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: { sources: [{ key: "EN", url: "/api/reports/r1/download?language=en", kind: "docx" }] },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="drawer-export"]').exists()).toBe(false);
  });
});
