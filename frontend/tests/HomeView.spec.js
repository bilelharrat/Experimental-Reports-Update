import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import HomeView from "../src/views/HomeView.vue";
import { api } from "../src/api.js";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
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
    api.autocompleteCompanies.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("places Quick Add directly after the search form before operations", () => {
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
    const form = wrapper.find("form");
    const quickAdd = form.element.nextElementSibling;

    expect(quickAdd?.textContent).toContain("Quick Add");
    expect(quickAdd?.textContent).toContain("Submit a link");
    expect(quickAdd?.textContent).toContain("Upload external research");
    expect(quickAdd?.textContent).toContain("Add research");
    expect(quickAdd?.textContent).toContain("Source library & appendix");
    expect(wrapper.text().indexOf("Quick Add")).toBeLessThan(
      wrapper.text().indexOf("Operations"),
    );
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

    await wrapper
      .findAll("button")
      .find((button) => button.text().includes("Submit a link"))
      .trigger("click");
    await wrapper.find("input[type='url']").setValue("https://example.com/research");
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
