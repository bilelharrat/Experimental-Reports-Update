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
  },
}));

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
});
