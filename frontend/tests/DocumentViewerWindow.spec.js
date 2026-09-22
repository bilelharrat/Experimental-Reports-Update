import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

import DocumentViewerWindow from "../src/components/DocumentViewerWindow.vue";

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
