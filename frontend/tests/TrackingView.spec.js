import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const apiMock = vi.hoisted(() => ({
  trackingRollup: vi.fn(),
  liveQuotes: vi.fn(),
}));
const push = vi.fn();

vi.mock("../src/api.js", () => ({
  api: {
    trackingRollup: apiMock.trackingRollup,
    liveQuotes: apiMock.liveQuotes,
  },
  withApiToken: (url) => url,
}));

vi.mock("vue-router", async () => {
  const actual = await vi.importActual("vue-router");
  return {
    ...actual,
    useRouter: () => ({ push }),
    useRoute: () => ({ query: {}, params: {}, name: "tracking" }),
  };
});

import TrackingView from "../src/views/TrackingView.vue";
import { trackedCompanyIds } from "../src/state.js";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

const companies = [
  {
    id: "zainar-inc",
    name: "ZaiNar, Inc.",
    status: "private",
    company_type: "private",
    industry: "Physical AI",
    description: "Radio positioning for machines.",
    hq: "Belmont, California",
    founded_year: 2017,
    employee_band: "50-200",
    website: "https://zainartech.com",
    key_people: [
      { name: "Daniel Jacker", role: "CEO" },
      { name: "Philip Kratz", role: "CTO" },
    ],
    highlight_2026: {
      headline: "Emerged from stealth at a $1B+ valuation",
      date: "2026-02-19",
    },
    latest_funding: {
      round: "Growth",
      amount_usd: "$100,000,000+",
      post_money_usd: "$1,000,000,000+",
      date: "2026-02-19",
    },
    metrics: [
      { label: "ARR", value: "~$24M", label_key: "company.metric_arr" },
      { label: "Valuation", value: "$1.0B+", label_key: "company.metric_valuation" },
    ],
    products: [{ name: "Physical AI Platform" }],
    competitors: [{ name: "NextNav" }],
  },
  {
    id: "nvda",
    name: "NVIDIA",
    ticker: "NVDA",
    status: "public",
    company_type: "public",
    sector: "Semis",
    description: "GPUs and AI infrastructure.",
    latest_earnings: {
      period: "Q4 FY26",
      revenue_yoy: "+22%",
      beat_or_miss: "beat",
    },
  },
];

const news = [
  {
    id: "n1",
    kind: "news",
    title: "NVIDIA announces new Blackwell chips",
    captured_at: new Date().toISOString(),
  },
];

function rollupFixture() {
  return {
    generated_at: "2026-08-31T22:00:00Z",
    companies: [
      {
        id: "zainar-inc",
        name: "ZaiNar, Inc.",
        bucket: "needs_action",
        price: null,
        memo: { total: 1, latest_status: "complete_with_warnings" },
        risks: { total: 4, researched: 1 },
        documents: { total: 3 },
        news: { recent_count: 2 },
        next_action: {
          kind: "memo_warnings",
          label: "Review quality warnings",
          route: { name: "research", params: { companyId: "zainar-inc" } },
        },
        attention: [
          {
            id: "zainar-inc:memo_warnings",
            company_id: "zainar-inc",
            company_name: "ZaiNar, Inc.",
            kind: "memo_warnings",
            severity: "medium",
            count: 2,
            label: "Memo completed with warnings",
            detail: "Quality warnings.",
            route: { name: "research", params: { companyId: "zainar-inc" } },
          },
        ],
      },
      {
        id: "nvda",
        name: "NVIDIA",
        bucket: "clear",
        price: { last_price: 142.3, change_pct_1d: 1.4, vs_sp500_30d_pct: 5.2 },
        memo: { total: 1, latest_status: "complete" },
        next_action: null,
        attention: [],
      },
    ],
    attention: [],
    totals: { company_count: 2, needs_action_count: 1, clear_company_count: 1 },
  };
}

function withQueue(fixture) {
  return {
    ...fixture,
    attention: fixture.companies.flatMap((company) => company.attention),
  };
}

let wrappers = [];

function mountView(provide = {}) {
  const wrapper = mount(TrackingView, {
    global: {
      stubs: { RouterLink: RouterLinkStub },
      provide: {
        workspaceCompanies: companies,
        workspaceNews: news,
        workspaceLoading: false,
        ...provide,
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

describe("TrackingView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    trackedCompanyIds.value = new Set();
    apiMock.trackingRollup.mockResolvedValue(withQueue(rollupFixture()));
    apiMock.liveQuotes.mockResolvedValue({
      quotes: {
        NVDA: {
          ticker: "NVDA",
          last_price: 180.5,
          change_pct_1d: 2.5,
          currency: "USD",
        },
      },
    });
  });

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount());
    wrappers = [];
  });

  it("shows the workspace book without requiring a follow list", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("ZaiNar, Inc.");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Radio positioning for machines.");
    expect(wrapper.text()).toContain("Belmont, California");
    expect(wrapper.text()).toContain("2017");
    expect(wrapper.text()).toContain("zainartech.com");
    expect(wrapper.text()).toContain("Daniel Jacker");
    expect(wrapper.text()).toContain("Philip Kratz");
    expect(wrapper.text()).toContain("Emerged from stealth at a $1B+ valuation");
    expect(wrapper.text()).toContain("Last round:");
    expect(wrapper.text()).toContain("Growth");
    expect(wrapper.text()).toContain("ARR");
    expect(wrapper.text()).toContain("~$24M");
    expect(wrapper.text()).toContain("Physical AI Platform");
    expect(wrapper.text()).toContain("NextNav");
    expect(wrapper.text()).toContain("Last earnings:");
    expect(wrapper.text()).toContain("Q4 FY26");
    expect(wrapper.text()).toContain("NVIDIA announces new Blackwell chips");
    expect(wrapper.text()).not.toContain("Nothing tracked yet");
    expect(apiMock.trackingRollup).toHaveBeenCalledWith(["nvda", "zainar-inc"]);
  });

  it("renders price and memo state once the rollup arrives", async () => {
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Live");
    expect(wrapper.text()).toContain("NVDA");
    expect(wrapper.text()).toContain("$180.5");
    expect(wrapper.text()).toContain("+2.5%");
    expect(wrapper.text()).toContain("30d vs S&P");
    expect(wrapper.text()).toContain("+5.2%");
    expect(wrapper.text()).not.toContain("$142.3");
    expect(wrapper.text()).toContain("1/4 researched");
    expect(wrapper.text()).toContain("2 news");
    expect(wrapper.text()).toContain("3 docs");
    expect(wrapper.text()).toContain("Review quality warnings");
    expect(apiMock.liveQuotes).toHaveBeenCalledWith(["NVDA"]);
  });

  it("opens a company workspace from a card", async () => {
    const wrapper = mountView();
    await flushPromises();

    const button = wrapper
      .findAll("button")
      .find((el) => el.text().includes("ZaiNar, Inc."));
    await button.trigger("click");
    expect(push).toHaveBeenCalledWith({
      name: "research",
      params: { companyId: "zainar-inc" },
    });
  });

  it("a ticker on the tape opens that stock on the Market desk", async () => {
    const wrapper = mountView();
    await flushPromises();

    const nvda = wrapper
      .find(".ticker-tape")
      .findAll("button")
      .find((el) => el.text().startsWith("NVDA"));
    await nvda.trigger("click");
    expect(push).toHaveBeenCalledWith({ name: "market-radar", query: { ticker: "NVDA" } });
  });

  it("can narrow the book to followed companies", async () => {
    trackedCompanyIds.value = new Set(["nvda"]);
    const wrapper = mountView();
    await flushPromises();

    const followed = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Followed"));
    await followed.trigger("click");
    await flushPromises();

    const names = wrapper.findAll("article").map((article) => article.text());
    expect(names.some((text) => text.includes("NVIDIA"))).toBe(true);
    expect(names.some((text) => text.includes("ZaiNar"))).toBe(false);
    expect(apiMock.trackingRollup).toHaveBeenLastCalledWith(["nvda"]);
  });

  it("offers a retry when the rollup request fails", async () => {
    apiMock.trackingRollup.mockRejectedValueOnce(new Error("boom"));
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Could not load tracking data.");
    expect(wrapper.text()).toContain("ZaiNar, Inc.");

    const retry = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Try again"));
    await retry.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("+2.5%");
    expect(wrapper.text()).toContain("$180.5");
  });
});
