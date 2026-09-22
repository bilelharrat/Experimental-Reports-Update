import { describe, expect, it, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, ref } from "vue";

const replace = vi.fn();
const route = reactive({ query: {} });

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  useRoute: () => route,
}));

vi.mock("../src/api.js", () => ({
  api: {
    quotesNews: vi.fn(),
    prewarmNewsBriefs: vi.fn().mockResolvedValue({ queued: 0 }),
    getNewsBrief: vi.fn().mockRejectedValue({ status: 404, message: "missing" }),
    postNewsBrief: vi.fn().mockResolvedValue({ kind: "basic", what_happened: "Body." }),
    newsBriefRefreshStatus: vi.fn().mockResolvedValue({ running: false, interval_hours: 6 }),
    getAutoUpdates: vi.fn().mockResolvedValue({ channels: [] }),
  },
}));

import { api } from "../src/api.js";
import HomeNewsDesk from "../src/components/HomeNewsDesk.vue";

// The sidebar's News row opens the desk on one company (`?company=`), and a
// link that names a headline leads with it (`?story=`).

const minutesAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();

let workspaceNews;

function mountDesk() {
  workspaceNews = ref([
    { id: "n1", kind: "news", title: "Microsoft ships a new Surface", captured_at: minutesAgo(1) },
    { id: "n2", kind: "news", title: "Intel cuts a fab plan", captured_at: minutesAgo(2) },
  ]);
  return mount(HomeNewsDesk, {
    global: {
      provide: {
        workspaceCompanies: ref([
          { id: "msft", name: "Microsoft Corp", ticker: "MSFT" },
          { id: "intc", name: "Intel Corp", ticker: "INTC" },
        ]),
        workspaceNews,
        workspaceResearch: ref([]),
        workspaceLiveNews: ref([]),
      },
    },
  });
}

describe("HomeNewsDesk on one company", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.query = {};
    api.quotesNews.mockResolvedValue({
      items: [
        {
          id: "live-9",
          kind: "live_news",
          ticker: "MSFT",
          title: "Microsoft signs a sovereign cloud deal",
          source: "Yahoo Finance",
          published_at: minutesAgo(30),
        },
      ],
    });
  });

  it("adds the company's own ticker headlines and leads with the story picked", async () => {
    route.query = { company: "msft", story: "live:live-9" };
    const wrapper = mountDesk();
    await flushPromises();

    expect(api.quotesNews).toHaveBeenCalledWith({ tickers: ["MSFT"], limit: 30 });
    // Newer, but not the story the link names.
    expect(wrapper.find(".news-lead-title").text()).toBe("Microsoft signs a sovereign cloud deal");
    expect(wrapper.text()).toContain("Microsoft ships a new Surface");
    expect(wrapper.text()).not.toContain("Intel cuts a fab plan");
  });

  it("holds the picked story while the list changes before it arrives", async () => {
    let deliver;
    api.quotesNews.mockReturnValue(new Promise((resolve) => (deliver = resolve)));
    route.query = { company: "msft", story: "live:live-9" };
    const wrapper = mountDesk();
    await flushPromises();
    expect(wrapper.find(".news-lead-title").text()).toBe("Microsoft ships a new Surface");

    // The app's poll lands first…
    workspaceNews.value = [
      ...workspaceNews.value,
      { id: "n3", kind: "news", title: "Microsoft trims a team", captured_at: minutesAgo(3) },
    ];
    await flushPromises();
    // …then the ticker's own headlines, with the story.
    deliver({
      items: [
        {
          id: "live-9",
          kind: "live_news",
          ticker: "MSFT",
          title: "Microsoft signs a sovereign cloud deal",
          published_at: minutesAgo(30),
        },
      ],
    });
    await flushPromises();
    expect(wrapper.find(".news-lead-title").text()).toBe("Microsoft signs a sovereign cloud deal");
  });

  it("clearing the company drops the story too", async () => {
    route.query = { company: "msft", story: "live:live-9", tab: "news" };
    const wrapper = mountDesk();
    await flushPromises();
    await wrapper.find('[data-testid="news-company-focus-clear"]').trigger("click");

    expect(replace).toHaveBeenCalledWith({ query: { tab: "news" } });
  });

  it("asks the wire for nothing extra without a company", async () => {
    const wrapper = mountDesk();
    await flushPromises();

    expect(api.quotesNews).not.toHaveBeenCalled();
    expect(wrapper.find(".news-lead-title").text()).toBe("Microsoft ships a new Surface");
  });
});
