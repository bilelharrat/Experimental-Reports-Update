import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive } from "vue";
import HomeView from "../src/views/HomeView.vue";
import SubmitLinkTool from "../src/components/SubmitLinkTool.vue";
import UploadResearchTool from "../src/components/UploadResearchTool.vue";
import AddHormuzResearchTool from "../src/components/AddHormuzResearchTool.vue";
import { api } from "../src/api.js";

const push = vi.fn();
const mockRoute = reactive({ query: {} });

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
  useRoute: () => mockRoute,
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../src/api.js", () => ({
  api: {
    autocompleteCompanies: vi.fn(),
    selectCompany: vi.fn(),
    startDeepSearch: vi.fn(),
    searchStreamUrl: vi.fn(),
    trader: { refreshAll: vi.fn() },
    regenAllCompanies: vi.fn(),
    linkPreview: vi.fn(),
    createNews: vi.fn(),
    uploadExternalResearch: vi.fn(),
    createHormuz: vi.fn(),
  },
}));

describe("HomeView M1 layout and search", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockRoute.query = {};
    api.autocompleteCompanies.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is search-first with glass intake actions under the field", () => {
    const wrapper = mount(HomeView);

    expect(wrapper.text()).toContain("Find a Company");
    expect(wrapper.text()).toContain("Link");
    expect(wrapper.text()).toContain("File");
    expect(wrapper.text()).toContain("Note");
    expect(wrapper.text()).toContain("Library");
    expect(wrapper.text()).not.toContain("Quick Add");
    expect(wrapper.text()).not.toContain("Operations");
  });

  it("opens an exact autocomplete company instead of starting deep search", async () => {
    api.autocompleteCompanies.mockResolvedValue([
      {
        id: "zainar-inc",
        name: "ZaiNar, Inc.",
        source: "local",
        sector: "Physical AI",
      },
    ]);
    const wrapper = mount(HomeView);

    await wrapper.find("input[type='search']").setValue("ZaiNar");
    await vi.advanceTimersByTimeAsync(240);
    await flushPromises();

    const suggestion = wrapper
      .findAll("button")
      .find((button) => button.text().includes("ZaiNar, Inc."));
    expect(suggestion).toBeTruthy();

    await suggestion.trigger("mousedown");

    expect(push).toHaveBeenCalledWith({
      name: "research",
      params: { companyId: "zainar-inc" },
    });
    expect(api.startDeepSearch).not.toHaveBeenCalled();
  });

  it("shows unresolved Quick Add assignment confirmation for submitted links", async () => {
    api.linkPreview.mockResolvedValue({
      final_url: "https://example.com/research",
      domain: "example.com",
      title: "Generic market update",
      description: "A market note without a company match.",
      text_chars: 1200,
    });
    api.createNews.mockResolvedValue({
      id: "news-1",
      kind: "news",
      status: "queued",
      intake_assignment: {
        status: "unresolved",
        category_label: "External Reports",
        company_reason: "No high-confidence company match.",
      },
    });
    mockRoute.query = { intake: "link" };
    const wrapper = mount(HomeView, {
      global: {
        stubs: {
          "router-link": {
            props: ["to"],
            template: "<a><slot /></a>",
          },
        },
      },
    });
    await flushPromises();
    await wrapper
      .findComponent(SubmitLinkTool)
      .find("input[type='text']")
      .setValue("https://example.com/research");
    await wrapper.findAll("form")[1].trigger("submit");
    await flushPromises();
    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Accept"))
      .trigger("click");
    await flushPromises();

    expect(api.createNews).toHaveBeenCalledWith("https://example.com/research");
    expect(wrapper.text()).toContain("Needs assignment review");
    expect(wrapper.text()).toContain("External Reports");
    expect(wrapper.text()).toContain("No high-confidence company match.");
    expect(push).not.toHaveBeenCalledWith({
      name: "external-news",
      params: { id: "news-1" },
    });
  });
});

describe("HomeView ?intake= deep-links", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRoute.query = {};
    api.autocompleteCompanies.mockResolvedValue([]);
  });

  it("opens the Submit Link tool at ?intake=link", async () => {
    mockRoute.query = { intake: "link" };
    const wrapper = mount(HomeView);
    await flushPromises();

    expect(wrapper.findComponent(SubmitLinkTool).props("expanded")).toBe(true);
    expect(wrapper.findComponent(UploadResearchTool).props("expanded")).toBe(false);
    expect(wrapper.findComponent(AddHormuzResearchTool).props("expanded")).toBe(false);
  });

  it("opens the Upload Research tool at ?intake=upload", async () => {
    mockRoute.query = { intake: "upload" };
    const wrapper = mount(HomeView);
    await flushPromises();

    expect(wrapper.findComponent(UploadResearchTool).props("expanded")).toBe(true);
    expect(wrapper.findComponent(SubmitLinkTool).props("expanded")).toBe(false);
  });

  it("opens the internal note tool at ?intake=note and reacts to navigation", async () => {
    const wrapper = mount(HomeView, {
      global: {
        stubs: {
          "router-link": {
            props: ["to"],
            template: "<a><slot /></a>",
          },
        },
      },
    });
    await flushPromises();
    expect(wrapper.findComponent(AddHormuzResearchTool).exists()).toBe(false);

    // Toolbar Quick Add navigates to /?intake=note on the same
    // mounted view — the watcher must pick up the query change.
    mockRoute.query = { intake: "note" };
    await flushPromises();
    expect(wrapper.findComponent(AddHormuzResearchTool).props("expanded")).toBe(true);
  });
});
