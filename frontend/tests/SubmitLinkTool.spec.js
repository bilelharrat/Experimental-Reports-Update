import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import SubmitLinkTool from "../src/components/SubmitLinkTool.vue";
import UploadResearchTool from "../src/components/UploadResearchTool.vue";
import { api } from "../src/api.js";

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("../src/api.js", () => ({
  api: {
    linkPreview: vi.fn(),
    createNews: vi.fn(),
    uploadExternalResearch: vi.fn(),
  },
}));

async function mountExpanded(Component) {
  const wrapper = mount(Component, { props: { expanded: true } });
  await flushPromises();
  return wrapper;
}

describe("SubmitLinkTool validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows an error on empty submit instead of silently returning", async () => {
    const wrapper = await mountExpanded(SubmitLinkTool);

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("Enter a URL to preview.");
    expect(api.linkPreview).not.toHaveBeenCalled();
  });

  it("shows an error for an invalid URL and never calls the API", async () => {
    const wrapper = await mountExpanded(SubmitLinkTool);

    await wrapper.find("input[type='text']").setValue("not-a-real-url-xyz");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("doesn't look like a valid URL");
    expect(api.linkPreview).not.toHaveBeenCalled();
  });

  it("previews a valid URL", async () => {
    api.linkPreview.mockResolvedValue({
      final_url: "https://example.com/a",
      domain: "example.com",
      title: "A",
    });
    const wrapper = await mountExpanded(SubmitLinkTool);

    await wrapper.find("input[type='text']").setValue("https://example.com/a");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(api.linkPreview).toHaveBeenCalledWith("https://example.com/a");
    expect(wrapper.text()).not.toContain("valid URL");
  });

  it("accepts a bare host the way the server does", async () => {
    api.linkPreview.mockResolvedValue({ final_url: "https://example.com" });
    const wrapper = await mountExpanded(SubmitLinkTool);

    await wrapper.find("input[type='text']").setValue("example.com/story");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(api.linkPreview).toHaveBeenCalledWith("example.com/story");
  });
});

describe("UploadResearchTool title field", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("leaves the title empty after picking a file (server defaults it)", async () => {
    const wrapper = await mountExpanded(UploadResearchTool);

    const fileInput = wrapper.find("input[type='file']");
    const f = new File(["x"], "my-deck.pdf", { type: "application/pdf" });
    Object.defineProperty(fileInput.element, "files", { value: [f] });
    await fileInput.trigger("change");

    const titleInput = wrapper.find("input[placeholder*='filename' i]");
    expect(titleInput.exists()).toBe(true);
    expect(titleInput.element.value).toBe("");

    // Typing produces only the typed text — no filename appended.
    await titleInput.setValue("Real Title");
    expect(titleInput.element.value).toBe("Real Title");
  });
});
