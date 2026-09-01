import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

import DocumentViewerDrawer from "../src/components/DocumentViewerDrawer.vue";

function fetchResponse({ text = "", buffer = new ArrayBuffer(8), ok = true } = {}) {
  return {
    ok,
    status: ok ? 200 : 500,
    text: async () => text,
    arrayBuffer: async () => buffer,
  };
}

describe("DocumentViewerDrawer", () => {
  beforeEach(() => {
    docx.renderAsync.mockClear();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("renders markdown sources as formatted HTML", async () => {
    fetch.mockResolvedValue(
      fetchResponse({ text: "# ZaiNar Notes\n\n- first point\n" }),
    );
    const wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: {
        title: "notes.md",
        sources: [{ key: "MD", url: "/files/notes.md", kind: "md" }],
      },
    });
    await flushPromises();

    expect(fetch).toHaveBeenCalledWith("/files/notes.md");
    expect(wrapper.html()).toContain("<h1>ZaiNar Notes</h1>");
    expect(wrapper.html()).toContain("<li>first point</li>");
    expect(wrapper.text()).toContain("notes.md");
  });

  it("keeps raw HTML in markdown inert", async () => {
    fetch.mockResolvedValue(
      fetchResponse({ text: "hello <script>window.pwned = 1</script>" }),
    );
    const wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: {
        sources: [{ key: "MD", url: "/files/sus.md", kind: "md" }],
      },
    });
    await flushPromises();

    expect(wrapper.html()).not.toContain("<script>");
    expect(wrapper.html()).toContain("&lt;script&gt;");
  });

  it("renders docx sources through docx-preview and switches tabs", async () => {
    fetch.mockResolvedValue(fetchResponse());
    const wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: {
        title: "Investment memo",
        sources: [
          { key: "EN", url: "/dl/en", kind: "docx" },
          { key: "ZH", url: "/dl/zh", kind: "docx" },
        ],
      },
    });
    await flushPromises();

    expect(fetch).toHaveBeenCalledWith("/dl/en");
    expect(docx.renderAsync).toHaveBeenCalledTimes(1);

    const zhTab = wrapper
      .findAll("button")
      .find((button) => button.text() === "ZH");
    expect(zhTab).toBeTruthy();
    await zhTab.trigger("click");
    await flushPromises();

    expect(fetch).toHaveBeenCalledWith("/dl/zh");
    expect(docx.renderAsync).toHaveBeenCalledTimes(2);
  });

  it("shows the error state when the fetch fails", async () => {
    fetch.mockResolvedValue(fetchResponse({ ok: false }));
    const wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: {
        sources: [{ key: "DOCX", url: "/dl/broken", kind: "docx" }],
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain(
      "This file could not be previewed here.",
    );
  });

  it("closes from the overlay and from Escape", async () => {
    fetch.mockResolvedValue(fetchResponse({ text: "x" }));
    const wrapper = mount(DocumentViewerDrawer, {
      global: { stubs: { teleport: true } },
      props: {
        sources: [{ key: "MD", url: "/files/x.md", kind: "md" }],
      },
    });
    await flushPromises();

    await wrapper.find(".bg-black\\/30").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(wrapper.emitted("close")).toHaveLength(2);
  });
});
