import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

import DocumentViewerWindow from "../src/components/DocumentViewerWindow.vue";
import { jobLogRequest } from "../src/reportStatus.js";
import { ANTHROPIC_COMPLETE, FAILED_DISMISSED, pausedReport, runningReport, withReport } from "./fixtures/reportSummaries.js";
import { setAppLanguage } from "../src/state.js";

function fetchResponse({ text = "", buffer = new ArrayBuffer(8), ok = true } = {}) {
  return {
    ok,
    status: ok ? 200 : 500,
    text: async () => text,
    arrayBuffer: async () => buffer,
  };
}

describe("DocumentViewerWindow", () => {
  beforeEach(() => {
    docx.renderAsync.mockClear();
    vi.stubGlobal("fetch", vi.fn());
    window.localStorage.removeItem("bsh.docViewerZoom");
  });

  it("renders empty placeholder when no sources are provided", async () => {
    const wrapper = mount(DocumentViewerWindow, {
      props: {
        title: "",
        sources: [],
      },
      global: {
        stubs: { RouterLink: true },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Select a report to view");
  });

  it("renders markdown source and header controls", async () => {
    fetch.mockResolvedValue(
      fetchResponse({ text: "# Investment Memo\n\n- Strong growth\n" }),
    );
    const wrapper = mount(DocumentViewerWindow, {
      props: {
        title: "Acme Investment Memo",
        companyName: "Acme Inc.",
        companyId: "acme",
        sources: [{ key: "MD", url: "/api/reports/1/memo.md", kind: "md" }],
      },
      global: {
        stubs: {
          RouterLink: {
            template: "<a><slot /></a>",
          },
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Acme Investment Memo");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.html()).toContain("<h1>Investment Memo</h1>");
    expect(wrapper.html()).toContain("<li>Strong growth</li>");
  });

  it("keeps the header to one line, the company a link beside the title", async () => {
    fetch.mockResolvedValue(fetchResponse({ text: "# Memo" }));
    const wrapper = mount(DocumentViewerWindow, {
      props: {
        title: "Acme Inc. — Investment Memo",
        companyName: "Acme Inc.",
        companyId: "acme",
        date: "Sep 1, 2026",
        sources: [{ key: "MD", url: "/api/reports/1/memo.md", kind: "md" }],
      },
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    });
    await flushPromises();

    const header = wrapper.get("header");
    // The title names the company, so the link is its arrow, not the name again.
    expect(header.text().match(/Acme Inc\./g)).toHaveLength(1);
    const link = wrapper.get('[data-testid="viewer-company-link"]');
    expect(link.text()).toBe("");
    expect(link.attributes("aria-label")).toBe("Company Profile: Acme Inc.");
    expect(header.text()).toContain("Sep 1, 2026");
  });

  it("scales a Word page to fill the viewer's width", async () => {
    fetch.mockResolvedValue(fetchResponse());
    docx.renderAsync.mockImplementationOnce((_buffer, container) => {
      container.innerHTML = '<div class="docx-wrapper"><section class="docx" style="width: 612pt"></section></div>';
      return Promise.resolve();
    });
    // jsdom has no layout; give every element a width (jsdom's own clientWidth
    // lives on Element, so dropping this override restores it).
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 1224,
    });
    try {
      const wrapper = mount(DocumentViewerWindow, {
        props: { title: "Memo", sources: [{ key: "EN", url: "/memo.docx", kind: "docx" }] },
        global: { stubs: { RouterLink: true } },
      });
      await flushPromises();
      // A Letter page is 816px; 1224px of viewer makes it 1.5x.
      expect(wrapper.get('[data-testid="viewer-docx"]').element.style.zoom).toBe("1.5");
    } finally {
      delete HTMLElement.prototype.clientWidth;
    }
  });

  it("zooms by hand, by pinch, back to actual size and back to fit", async () => {
    fetch.mockResolvedValue(fetchResponse());
    docx.renderAsync.mockImplementation((_buffer, container) => {
      container.innerHTML = '<div class="docx-wrapper"><section class="docx" style="width: 612pt"></section></div>';
      return Promise.resolve();
    });
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 1224,
    });
    try {
      const wrapper = mount(DocumentViewerWindow, {
        props: { title: "Memo", sources: [{ key: "EN", url: "/memo.docx", kind: "docx" }] },
        global: { stubs: { RouterLink: true } },
      });
      await flushPromises();
      const zoom = () => wrapper.get('[data-testid="viewer-docx"]').element.style.zoom;
      const level = () => wrapper.get('[data-testid="viewer-zoom-level"]').text();
      const fit = () => wrapper.get('[data-testid="viewer-zoom-fit"]');

      // Fit to width by default.
      expect(level()).toBe("150%");
      expect(fit().attributes("aria-pressed")).toBe("true");

      await wrapper.get('[data-testid="viewer-zoom-in"]').trigger("click");
      expect(zoom()).toBe("1.75");
      expect(fit().attributes("aria-pressed")).toBe("false");
      expect(window.localStorage.getItem("bsh.docViewerZoom")).toBe("1.75");

      // The percentage is actual size; − steps down from there.
      await wrapper.get('[data-testid="viewer-zoom-level"]').trigger("click");
      expect(level()).toBe("100%");
      await wrapper.get('[data-testid="viewer-zoom-out"]').trigger("click");
      expect(level()).toBe("90%");

      // A trackpad pinch (ctrl + wheel) zooms; a plain scroll doesn't.
      const area = wrapper.get('[data-testid="viewer-docx"]').element.parentElement;
      area.dispatchEvent(new WheelEvent("wheel", { deltaY: 40, bubbles: true, cancelable: true }));
      await flushPromises();
      expect(level()).toBe("90%");
      const pinch = new WheelEvent("wheel", { deltaY: -50, ctrlKey: true, bubbles: true, cancelable: true });
      area.dispatchEvent(pinch);
      await flushPromises();
      expect(pinch.defaultPrevented).toBe(true);
      expect(level()).toBe("148%"); // 0.9 × e^0.5

      await fit().trigger("click");
      expect(level()).toBe("150%");
      expect(window.localStorage.getItem("bsh.docViewerZoom")).toBe("fit");
    } finally {
      delete HTMLElement.prototype.clientWidth;
      docx.renderAsync.mockImplementation(() => Promise.resolve());
    }
  });

  it("remembers a hand-picked zoom for the next document", async () => {
    window.localStorage.setItem("bsh.docViewerZoom", "1.25");
    fetch.mockResolvedValue(fetchResponse());
    const wrapper = mount(DocumentViewerWindow, {
      props: { title: "Memo", sources: [{ key: "EN", url: "/memo.docx", kind: "docx" }] },
      global: { stubs: { RouterLink: true } },
    });
    await flushPromises();
    expect(wrapper.get('[data-testid="viewer-zoom-level"]').text()).toBe("125%");
    expect(wrapper.get('[data-testid="viewer-docx"]').element.style.zoom).toBe("1.25");
  });

  it("renders docx source and switches language tabs", async () => {
    fetch.mockResolvedValue(fetchResponse());
    const wrapper = mount(DocumentViewerWindow, {
      props: {
        title: "Bilingual Report",
        sources: [
          { key: "EN", url: "/reports/memo_en.docx", kind: "docx" },
          { key: "ZH", url: "/reports/memo_zh.docx", kind: "docx" },
        ],
      },
      global: {
        stubs: { RouterLink: true },
      },
    });
    await flushPromises();

    expect(docx.renderAsync).toHaveBeenCalledTimes(1);
    expect(wrapper.findAll("button").filter((b) => b.text() === "ZH").length).toBe(1);

    const zhBtn = wrapper.findAll("button").find((b) => b.text() === "ZH");
    await zhBtn.trigger("click");
    await flushPromises();

    expect(docx.renderAsync).toHaveBeenCalledTimes(2);
  });

  it("emits open-fullscreen when clicking popout button", async () => {
    fetch.mockResolvedValue(fetchResponse());
    const wrapper = mount(DocumentViewerWindow, {
      props: {
        title: "Report Popout",
        sources: [{ key: "EN", url: "/reports/memo_en.docx", kind: "docx" }],
      },
      global: {
        stubs: { RouterLink: true },
      },
    });
    await flushPromises();

    const fullscreenBtn = wrapper.find('button[title="Full Screen"]');
    expect(fullscreenBtn.exists()).toBe(true);
    await fullscreenBtn.trigger("click");

    expect(wrapper.emitted("open-fullscreen")).toBeTruthy();
    expect(wrapper.emitted("open-fullscreen")[0][0].title).toBe("Report Popout");
  });
});

// jsdom has no layout: paragraphs carry their page position in data-y, and
// the scroll area (at the top of the viewport) reports them relative to its
// own scroll offset, which is what the outline and the anchors measure.
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

function page(body) {
  return (_buffer, container) => {
    container.innerHTML = `<div class="docx-wrapper"><section class="docx" style="width: 612pt">${body}</section></div>`;
    return Promise.resolve();
  };
}

const settle = async () => {
  await flushPromises();
  await new Promise((resolve) => setTimeout(resolve, 30));
  await flushPromises();
};

const BOOKMARKED_EN = `
  <p data-y="0">Cover</p>
  <p data-y="100"><span id="bsh_sec_1"></span><span>I. EXECUTIVE SUMMARY</span></p>
  <p data-y="900"><span id="bsh_sec_2"></span><span>II. COMPANY OVERVIEW</span></p>
  <p data-y="2000"><span id="bsh_sec_3"></span><span>III. INVESTMENT RISK</span></p>
  <p data-y="2500"><a href="#bsh_sec_2">Back to II</a> <a href="https://example.com/source">Source</a></p>`;
const BOOKMARKED_ZH = `
  <p data-y="0">封面</p>
  <p data-y="150"><span id="bsh_sec_1"></span><span>一、执行摘要</span></p>
  <p data-y="1300"><span id="bsh_sec_2"></span><span>二、公司概览</span></p>
  <p data-y="2600"><span id="bsh_sec_3"></span><span>三、投资风险</span></p>`;

describe("DocumentViewerWindow navigation", () => {
  let restoreLayout;

  beforeEach(() => {
    docx.renderAsync.mockReset();
    docx.renderAsync.mockImplementation(() => Promise.resolve());
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fetchResponse())));
    window.localStorage.removeItem("bsh.docViewerZoom");
    window.localStorage.removeItem("bsh.docViewerOutline");
    restoreLayout = layoutByDataY();
  });

  afterEach(() => {
    restoreLayout();
    jobLogRequest.value = null;
  });

  function mountViewer(props = {}) {
    return mount(DocumentViewerWindow, {
      attachTo: document.body,
      props: {
        title: "Memo",
        sources: [
          { key: "EN", url: "/memo_en.docx", kind: "docx" },
          { key: "ZH", url: "/memo_zh.docx", kind: "docx" },
        ],
        ...props,
      },
      global: { stubs: { RouterLink: true } },
    });
  }

  it("builds the outline from the renderer's section bookmarks and jumps to a section", async () => {
    docx.renderAsync.mockImplementation(page(BOOKMARKED_EN));
    const wrapper = mountViewer();
    await settle();

    await wrapper.get('[data-testid="viewer-outline-toggle"]').trigger("click");
    const outline = wrapper.get('[data-testid="viewer-outline"]');
    const entries = outline.findAll("button");
    expect(entries.map((b) => b.text())).toEqual([
      "I. EXECUTIVE SUMMARY",
      "II. COMPANY OVERVIEW",
      "III. INVESTMENT RISK",
    ]);
    expect(window.localStorage.getItem("bsh.docViewerOutline")).toBe("1");

    await wrapper.get('[data-testid="viewer-outline-bsh_sec_2"]').trigger("click");
    const area = wrapper.get('[data-testid="viewer-scroll"]').element;
    expect(area.scrollTop).toBe(892);
    expect(wrapper.emitted("change-section")[0]).toEqual(["bsh_sec_2"]);
    expect(wrapper.get('[data-testid="viewer-outline-bsh_sec_2"]').attributes("aria-current")).toBe("location");
    wrapper.unmount();
  });

  it("scrolls in-document links inside the viewer and opens web links in a new tab", async () => {
    docx.renderAsync.mockImplementation(page(BOOKMARKED_EN));
    const wrapper = mountViewer();
    await settle();

    const area = wrapper.get('[data-testid="viewer-scroll"]').element;
    const internal = area.querySelector('a[href="#bsh_sec_2"]');
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    internal.dispatchEvent(click);
    // The hash never reaches the router; the viewer scrolls itself.
    expect(click.defaultPrevented).toBe(true);
    expect(area.scrollTop).toBe(892);

    const external = area.querySelector('a[href^="https://"]');
    expect(external.getAttribute("target")).toBe("_blank");
    expect(external.getAttribute("rel")).toBe("noopener noreferrer");
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const outward = new MouseEvent("click", { bubbles: true, cancelable: true });
    external.dispatchEvent(outward);
    expect(outward.defaultPrevented).toBe(true);
    expect(open).toHaveBeenCalledWith("https://example.com/source", "_blank", "noopener,noreferrer");
    open.mockRestore();
    wrapper.unmount();
  });

  it("keeps the reader in the same section when switching EN to ZH", async () => {
    docx.renderAsync
      .mockImplementationOnce(page(BOOKMARKED_EN))
      .mockImplementationOnce(page(BOOKMARKED_ZH));
    const wrapper = mountViewer();
    await settle();

    const area = wrapper.get('[data-testid="viewer-scroll"]').element;
    // Halfway through section II in English (900 → 2000).
    area.scrollTop = 1450;
    await wrapper.get('[data-testid="viewer-source-zh"]').trigger("click");
    await settle();

    expect(docx.renderAsync).toHaveBeenCalledTimes(2);
    // Halfway through section II in Chinese (1300 → 2600).
    expect(area.scrollTop).toBe(1950);
    expect(wrapper.emitted("change-source").at(-1)[0]).toMatchObject({ key: "ZH", userInitiated: true });
    wrapper.unmount();
  });

  it("opens at the ?section= a link names", async () => {
    docx.renderAsync.mockImplementation(page(BOOKMARKED_EN));
    const wrapper = mountViewer({ initialSection: "bsh_sec_3" });
    await settle();
    expect(wrapper.get('[data-testid="viewer-scroll"]').element.scrollTop).toBe(1992);
    wrapper.unmount();
  });

  it("falls back to Word headings, then to an older memo's bold section titles", async () => {
    docx.renderAsync.mockImplementationOnce(
      page(`
        <p class="docx_heading1" data-y="100">I. Investment Decision</p>
        <p data-y="200">Body</p>
        <p class="docx_heading1" data-y="500">II. The Business</p>`),
    );
    const buffett = mountViewer({ sources: [{ key: "EN", url: "/buffett.docx", kind: "docx" }] });
    await settle();
    await buffett.get('[data-testid="viewer-outline-toggle"]').trigger("click");
    expect(buffett.findAll('[data-testid="viewer-outline"] button').map((b) => b.text())).toEqual([
      "I. Investment Decision",
      "II. The Business",
    ]);
    buffett.unmount();

    // A 2026-08 late-stage memo: plain paragraphs, the titles bold at 15pt,
    // the cover lines bold but larger, the sub-heads bold but body-sized.
    docx.renderAsync.mockImplementationOnce(
      page(`
        <p data-y="0"><span style="font-weight: bold; font-size: 18pt">BERKELEY SUMMIT HOUSE</span></p>
        <p data-y="20"><span style="font-weight: bold; font-size: 26pt">Anthropic, PBC</span></p>
        <p data-y="100"><span style="font-weight: bold; font-size: 15pt">I. EXECUTIVE SUMMARY</span></p>
        <p data-y="200"><span style="font-weight: bold; font-size: 10pt">Key Metrics Snapshot</span></p>
        <p data-y="300"><span style="font-weight: bold; font-size: 15pt">II. COMPANY OVERVIEW</span></p>
        <p data-y="400"><span>Body text that is not a heading.</span></p>
        <p data-y="500"><span style="font-weight: bold; font-size: 15pt">III. INVESTMENT HIGHLIGHTS</span></p>`),
    );
    const older = mountViewer({ sources: [{ key: "EN", url: "/older.docx", kind: "docx" }] });
    await settle();
    expect(older.findAll('[data-testid="viewer-outline"] button').map((b) => b.text())).toEqual([
      "I. EXECUTIVE SUMMARY",
      "II. COMPANY OVERVIEW",
      "III. INVESTMENT HIGHLIGHTS",
    ]);
    older.unmount();
  });

  it("lists a pass the server marks failed as not run, and never fetches its stub", async () => {
    docx.renderAsync.mockImplementation(page(BOOKMARKED_EN));
    const detail = {
      analysis_artifacts: [
        { label: "Countercase analysis", filename: "countercase.md", download_url: "/papers/countercase.md" },
        { label: "Growth bridge", filename: "growth_bridge.md", download_url: "/papers/growth_bridge.md", failed: true },
      ],
    };
    const wrapper = mountViewer({ detail, activePaper: "growth_bridge.md" });
    await settle();

    expect(wrapper.get('[data-testid="viewer-paper-not-run"]').text()).toContain("Pass did not run");
    expect(fetch).not.toHaveBeenCalledWith("/papers/growth_bridge.md");
    await wrapper.get('[data-testid="viewer-papers"]').trigger("click");
    const item = wrapper.get('[data-testid="viewer-paper-growth_bridge.md"]');
    expect(item.text()).toContain("Pass did not run");
    wrapper.unmount();
  });

  it("explains a failure in the server's words, with what it spent", async () => {
    const report = withReport(FAILED_DISMISSED, {
      dismissed_at: null,
      failure_kind: "provider_limit",
      failure_summary_en: "Claude reached its usage limit, so the run stopped.",
      failure_summary_zh: "Claude 已达到使用上限，运行因此停止。",
      failure_spend_usd: 3.456,
    });
    const wrapper = mountViewer({ sources: [], report });
    await settle();
    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.get('[data-testid="viewer-status-title"]').text()).toBe("Stopped at the model's usage limit");
    expect(card.get('[data-testid="viewer-status-summary"]').text()).toBe(
      "Claude reached its usage limit, so the run stopped.",
    );
    expect(card.get('[data-testid="viewer-status-spend"]').text()).toBe(
      "Spent before it stopped: $3.46 (API-equivalent)",
    );

    setAppLanguage("zh");
    await flushPromises();
    expect(card.get('[data-testid="viewer-status-summary"]').text()).toBe("Claude 已达到使用上限，运行因此停止。");
    setAppLanguage("en");
    wrapper.unmount();
  });

  it("asks the jobs rail to open a running report's live log", async () => {
    const report = runningReport();
    const wrapper = mountViewer({
      sources: [],
      report,
      detail: { ...report, log_url: `/api/jobs/log?path=memo:${report.id}`, stream_url: `/api/memos/${report.id}/stream` },
    });
    await settle();
    expect(wrapper.get('[data-testid="viewer-status"]').attributes("data-state")).toBe("running");
    await wrapper.get('[data-testid="viewer-status-log"]').trigger("click");
    expect(jobLogRequest.value.job).toMatchObject({
      kind: "memo",
      report_id: report.id,
      log_url: `/api/jobs/log?path=memo:${report.id}`,
    });
    wrapper.unmount();
  });

  it("shows a paused run without its document as a card whose action continues it", async () => {
    const report = pausedReport({ download_urls: null });
    fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      text: async () => "",
      arrayBuffer: async () => new ArrayBuffer(8),
    });
    const wrapper = mountViewer({ sources: [], report });
    await settle();

    const card = wrapper.get('[data-testid="viewer-status"]');
    expect(card.attributes("data-state")).toBe("paused");
    expect(card.get('[data-testid="viewer-status-title"]').text()).toBe("English ready — paused");
    expect(card.text()).toContain("Stage: English ready — review before Chinese");
    expect(card.get('[data-testid="viewer-quality-metrics"]').text()).toBe("Quality72% traced1 over cap0 conflicting4% repeated");
    expect(card.findAll('[data-testid="viewer-quality-metric"]')[0].attributes("title")).toBe(
      "The share of the memo's figures traced to a source on file or on the web.",
    );
    expect(wrapper.find('[data-testid="viewer-status-cancel"]').exists()).toBe(false);

    const resume = card.get('[data-testid="viewer-status-resume"]');
    expect(resume.text()).toBe("Continue (Chinese + IC memo)");
    await resume.trigger("click");
    expect(resume.text()).toBe("Click again to continue — this runs the model");
    expect(fetch.mock.calls.some(([url]) => String(url).includes("/resume"))).toBe(false);
    await resume.trigger("click");
    await settle();
    const call = fetch.mock.calls.find(([url]) => String(url).endsWith(`/api/reports/${report.id}/resume`));
    expect(call?.[1]?.method).toBe("POST");
    expect(wrapper.emitted("report-changed")?.[0]?.[0]).toMatchObject({ action: "resume", id: report.id });
    wrapper.unmount();
  });

  it("puts a finished memo's quality line beside its verdict and review", async () => {
    docx.renderAsync.mockImplementation(page("<p>Memo</p>"));
    const report = withReport(ANTHROPIC_COMPLETE, { quality_metrics: pausedReport().quality_metrics });
    const wrapper = mountViewer({
      report,
      sources: [{ key: "EN", url: "/memo_en.docx", kind: "docx" }],
    });
    await settle();
    const line = wrapper.get('[data-testid="viewer-meta"]').get('[data-testid="viewer-quality-metrics"]');
    expect(line.text()).toBe("Quality72% traced1 over cap0 conflicting4% repeated");
    expect(line.findAll('[data-testid="viewer-quality-metric"]')[3].attributes("title")).toBe(
      "The share of sentences that repeat another sentence of the memo.",
    );
    // No metrics recorded: no line.
    await wrapper.setProps({ report: withReport(ANTHROPIC_COMPLETE, {}) });
    expect(wrapper.find('[data-testid="viewer-quality-metrics"]').exists()).toBe(false);
    wrapper.unmount();
  });
});
