import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import FilePreviewModal from "../src/components/FilePreviewModal.vue";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("FilePreviewModal", () => {
  it("renders Background Documents .md files as Markdown HTML", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => "# Markdown Title\n\n- rendered in popup",
      }),
    );

    mount(FilePreviewModal, {
      attachTo: document.body,
      props: {
        file: {
          id: "file-1",
          kind: "text",
          filename: "notes.md",
          size_bytes: 42,
        },
        previewUrl: "/api/companies/acme/research-files/file-1?inline=1",
        downloadUrl: "/api/companies/acme/research-files/file-1",
        previewableKinds: ["text"],
      },
    });

    await flushPromises();

    expect(fetch).toHaveBeenCalledWith(
      "/api/companies/acme/research-files/file-1?inline=1",
      expect.any(Object),
    );
    expect(document.body.textContent).toContain("Markdown Title");
    expect(document.body.textContent).toContain("rendered in popup");
    expect(document.body.textContent).not.toContain("Preview not available");
    expect(document.body.querySelector(".md-h1")?.textContent).toBe(
      "Markdown Title",
    );
  });

  it("opens a PDF at the page a citation names", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(["%PDF-1.7"]) }),
    );
    // jsdom has no object URLs.
    URL.createObjectURL = vi.fn(() => "blob:preview-1");
    URL.revokeObjectURL = vi.fn();

    const wrapper = mount(FilePreviewModal, {
      attachTo: document.body,
      props: {
        file: { id: "file-2", kind: "pdf", filename: "deck.pdf" },
        previewUrl: "/api/companies/acme/research-files/file-2?inline=1",
        previewableKinds: ["pdf"],
        page: "12",
      },
    });
    await flushPromises();
    const frame = () => document.body.querySelector("iframe")?.getAttribute("src");
    expect(frame()).toBe("blob:preview-1#page=12");

    // No page, or one that is not a number ("p.xii"), opens at the start.
    await wrapper.setProps({ page: "p.xii" });
    expect(frame()).toBe("blob:preview-1");

    wrapper.unmount();
    delete URL.createObjectURL;
    delete URL.revokeObjectURL;
  });
});
