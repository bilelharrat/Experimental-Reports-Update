import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import NewsDeskView from "../src/views/NewsDeskView.vue";
import { api } from "../src/api.js";
import { companyViews, trackedCompanyIds } from "../src/state.js";

const push = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: {} }),
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../src/api.js", () => ({
  api: {
    liveQuotes: vi.fn(),
    researchPages: { marketPulse: vi.fn() },
    prewarmNewsBriefs: vi.fn().mockResolvedValue({ queued: 0, started: false }),
    getNewsBrief: vi.fn().mockRejectedValue({ status: 404, message: "missing" }),
    postNewsBrief: vi.fn().mockResolvedValue({
      what_happened: "Expanded desk briefing body.",
      why_it_matters: "Investment read.",
      context: [],
      watch_next: [],
      sources: [],
    }),
    newsBriefStatuses: vi.fn().mockResolvedValue({ ready: 0, items: [] }),
    newsBriefRefreshStatus: vi.fn().mockResolvedValue({
      running: false,
      interval_hours: 6,
      next_refresh_at: null,
    }),
    startNewsBriefRefresh: vi.fn().mockResolvedValue({
      started: true,
      running: false,
      interval_hours: 6,
    }),
  },
}));

function mountDesk() {
  return mount(NewsDeskView, {
    global: {
      provide: {
        workspaceCompanies: [],
        workspaceNews: [
          {
            id: "macro-1",
            kind: "news",
            title: "Fed holds rates as inflation cools",
            captured_at: "2026-09-02",
            summary: "Policy stay.",
          },
        ],
        workspaceLoading: false,
      },
      stubs: {
        RouterLink: { props: ["to"], template: "<a><slot /></a>" },
      },
    },
  });
}

describe("NewsDeskView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    companyViews.value = { nvda: 3 };
    trackedCompanyIds.value = new Set(["nvda"]);
    api.liveQuotes.mockResolvedValue({
      quotes: {
        NVDA: { ticker: "NVDA", last_price: 180.5, change_pct_1d: 2.5, currency: "USD" },
      },
    });
    api.researchPages.marketPulse.mockResolvedValue({
      summary: { signal_count: 1, top_signal: "Semis lead" },
      sections: {
        market_regime: {
          posture: "risk-on",
          breadth: { positive_signals: 4, negative_signals: 1, neutral_signals: 0 },
        },
        ranked_signals: [{ signal_id: "s1", signal: "Semis lead", direction: "bullish" }],
      },
    });
  });

  it("reads like Apple News: large title, following, hero story, markets", async () => {
    const wrapper = mount(NewsDeskView, {
      global: {
        provide: {
          workspaceCompanies: [
            {
              id: "nvda",
              name: "NVIDIA",
              ticker: "NVDA",
              industry: "Semis",
              company_news: [
                {
                  title: "NVIDIA launches new chip",
                  published_at: "2026-09-01",
                  category: "product",
                  summary: "Data-center SKU.",
                },
              ],
            },
          ],
          workspaceNews: [
            {
              id: "macro-1",
              kind: "news",
              title: "Fed holds rates as inflation cools",
              captured_at: "2026-09-02",
              summary: "Policy stay.",
            },
          ],
          workspaceLoading: false,
        },
        stubs: {
          RouterLink: { props: ["to"], template: "<a><slot /></a>" },
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("News");
    expect(wrapper.text()).toContain("Following");
    expect(wrapper.text()).toContain("Markets");
    expect(wrapper.text()).toContain("Watchlist");
    expect(wrapper.text()).toContain("NVIDIA launches new chip");
    expect(wrapper.text()).toContain("Fed holds rates as inflation cools");
    expect(wrapper.text()).toContain("Read Story");
    expect(wrapper.text()).toContain("Policy stay.");

    const chip = wrapper
      .findAll("button")
      .find((el) => el.text().includes("NVIDIA launches new chip"));
    await chip.trigger("click");
    expect(wrapper.text()).toContain("Data-center SKU.");

    const following = wrapper
      .findAll("button")
      .find((el) => el.text() === "Following");
    await following.trigger("click");
    expect(wrapper.text()).toContain("NVIDIA launches new chip");
    expect(wrapper.text()).not.toContain("Fed holds rates as inflation cools");
  });

  it("opening stories never asks for an AI write", async () => {
    const wrapper = mountDesk();
    await flushPromises();

    expect(api.prewarmNewsBriefs).toHaveBeenCalled();
    expect(api.postNewsBrief).toHaveBeenCalled();
    for (const [body] of api.postNewsBrief.mock.calls) {
      expect(body.refresh).toBe(false);
    }
    expect(api.startNewsBriefRefresh).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("AI briefs refresh every 6 hours");
    wrapper.unmount();
  });

  it("warns before an AI refresh or rewrite and stops when cancelled", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const wrapper = mountDesk();
    await flushPromises();
    const refreshAll = wrapper
      .findAll("button")
      .find((el) => el.text() === "Refresh AI briefs now");
    const rewrite = wrapper
      .findAll("button")
      .find((el) => el.text() === "Regenerate briefing");

    await refreshAll.trigger("click");
    await rewrite.trigger("click");
    await flushPromises();
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(confirm.mock.calls[0][0]).toContain("cost tokens");
    // A cadence is on, so the dialog may promise a schedule.
    expect(confirm.mock.calls[0][0]).toContain("every 6 hours");
    expect(api.startNewsBriefRefresh).not.toHaveBeenCalled();
    expect(api.postNewsBrief.mock.calls.some(([body]) => body.refresh)).toBe(false);

    confirm.mockReturnValue(true);
    await refreshAll.trigger("click");
    await flushPromises();
    expect(api.startNewsBriefRefresh).toHaveBeenCalledTimes(1);
    const [body] = api.startNewsBriefRefresh.mock.calls[0];
    expect(body.items[0].title).toBe("Fed holds rates as inflation cools");

    confirm.mockRestore();
    wrapper.unmount();
  });

  it("never promises an automatic refresh while the bar is on Manual", async () => {
    api.newsBriefRefreshStatus.mockResolvedValue({
      running: false,
      cadence: "manual",
      interval_hours: 0,
      next_refresh_at: null,
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const wrapper = mountDesk();
    await flushPromises();

    const refreshAll = wrapper
      .findAll("button")
      .find((el) => el.text() === "Refresh AI briefs now");
    await refreshAll.trigger("click");
    await flushPromises();

    const shown = confirm.mock.calls[0][0];
    expect(shown).toContain("cost tokens");
    expect(shown).toContain("Automatic refresh is off");
    expect(shown).not.toContain("every 6 hours");
    expect(shown).not.toContain("every 0 hours");
    expect(api.startNewsBriefRefresh).not.toHaveBeenCalled();

    confirm.mockRestore();
    wrapper.unmount();
  });
});
