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
});
