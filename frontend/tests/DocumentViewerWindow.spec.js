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
