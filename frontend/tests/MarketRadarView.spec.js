import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import MarketRadarView from "../src/views/MarketRadarView.vue";
import { api } from "../src/api.js";

const push = vi.fn();
const replace = vi.fn();

vi.mock("vue-router", () => ({
  useRouter: () => ({ push, replace }),
  useRoute: () => ({ query: {} }),
  RouterLink: {
    props: ["to"],
    template: "<a><slot /></a>",
  },
}));

vi.mock("../src/api.js", () => ({
  api: {
    liveQuotes: vi.fn(),
    quoteChart: vi.fn(),
    quoteSearch: vi.fn(),
    quoteWorkspace: vi.fn(),
    quoteScreeners: vi.fn(),
    quotePeers: vi.fn(),
    quoteCalendar: vi.fn(),
    researchPages: { marketPulse: vi.fn() },
  },
}));

describe("MarketRadarView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.liveQuotes.mockResolvedValue({
      quotes: {
        SPY: { ticker: "SPY", last_price: 520.1, change_pct_1d: 0.4, currency: "USD", volume: 80_000_000 },
        QQQ: { ticker: "QQQ", last_price: 450.2, change_pct_1d: -0.2, currency: "USD", volume: 40_000_000 },
        DIA: { ticker: "DIA", last_price: 390.0, change_pct_1d: 0.1, currency: "USD", volume: 10_000_000 },
        IWM: { ticker: "IWM", last_price: 210.5, change_pct_1d: -0.5, currency: "USD", volume: 20_000_000 },
        NVDA: {
          ticker: "NVDA",
          last_price: 180.5,
          change_pct_1d: 2.5,
          currency: "USD",
          volume: 55_000_000,
          name: "NVIDIA Corporation",
        },
        TSM: { ticker: "TSM", last_price: 140.0, change_pct_1d: -3.1, currency: "USD", volume: 12_000_000 },
        AAPL: { ticker: "AAPL", last_price: 190.5, change_pct_1d: 1.3, currency: "USD", volume: 52_000_000 },
      },
    });
    api.quoteChart.mockResolvedValue({
      ticker: "SPY",
      last_price: 520.1,
      previous_close: 518.0,
      change: 2.1,
      change_pct_1d: 0.4,
      currency: "USD",
      points: [
        { t: 1_725_148_800, close: 518 },
        { t: 1_725_149_400, close: 520.1 },
      ],
    });
    api.quoteSearch.mockResolvedValue({
      matches: [{ ticker: "AAPL", name: "Apple Inc.", type: "equity" }],
    });
    api.quoteWorkspace.mockResolvedValue({
      ticker: "NVDA",
      profile: { companyName: "NVIDIA", description: "Chip designer." },
      summary: { lastSalePrice: "$520.10" },
      financials: { income: { headers: ["Period"], rows: [] } },
      analysis: { target: { mean: 200 }, earnings: [] },
      holders: { institutional: [] },
      options: { calls: [], puts: [] },
      earnings: {
        next_date: "2026-11-25",
        next_estimated: true,
        past: [{ period: "Jul 2026", reported: "2026-08-26", eps: 2.22 }],
      },
    });
    api.quotePeers.mockResolvedValue({
      ticker: "NVDA",
      primary: {
        ticker: "NVDA",
        last: 520,
        change_1d: 0.4,
        ret_1m: 5,
        ret_ytd: 40,
        ret_1y: 80,
        vs_spy_1y: 20,
        drawdown_1y: -12,
        market_cap: 2e12,
        sector: "Technology",
        revenue_growth: 65,
        gross_margin: 71,
        operating_margin: 60,
        pe_ratio: 45,
        spark: [100, 110, 120],
        points: [],
      },
      benchmark: {
        ticker: "SPY",
        last: 520,
        change_1d: 0.2,
        ret_1m: 2,
        ret_ytd: 10,
        ret_1y: 15,
        points: [],
      },
      peers: [
        {
          ticker: "AMD",
          last: 160,
          change_1d: 1.1,
          ret_1m: 8,
          ret_ytd: 20,
          ret_1y: 30,
          vs_spy_1y: 10,
          drawdown_1y: -18,
          market_cap: 2e11,
          points: [],
        },
      ],
    });
    api.quoteCalendar.mockResolvedValue({
      events: [
        {
          ticker: "NVDA",
          date: "2026-11-25",
          kind: "earnings",
          title: "Earnings",
          confirmed: false,
          time: null,
        },
        {
          ticker: null,
          name: "United States",
          date: "2026-09-10",
          kind: "macro",
          title: "CPI",
          confirmed: true,
          time: "12:30",
        },
      ],
      counts: { earnings: 1, dividends: 0, macro: 1 },
    });
    api.quoteScreeners.mockResolvedValue({
      gainers: [{ ticker: "XYZ", name: "XYZ Corp", last: 12, change_pct: 8 }],
      losers: [],
      active: [],
      universe: [
        {
          ticker: "XYZ",
          name: "XYZ Corp",
          last: 12,
          change_pct: 8,
          volume: 1000,
          sector: "Technology",
          market_cap: 5e9,
        },
      ],
      sectors: ["Technology"],
    });
    api.researchPages.marketPulse.mockResolvedValue({
      summary: { top_signal: "Semis lead" },
      sections: {
        market_regime: {
          posture: "risk-on",
          breadth: { positive_signals: 4, negative_signals: 1, neutral_signals: 0 },
        },
      },
    });
  });

  function mountRadar() {
    return mount(MarketRadarView, {
      global: {
        provide: {
          openCopilot: vi.fn(),
          workspaceCompanies: [
            { id: "nvda", name: "NVIDIA", ticker: "NVDA", company_type: "public" },
            { id: "tsm", name: "TSMC", ticker: "TSM", company_type: "public" },
          ],
          workspaceNews: [
            {
              id: "macro-1",
              kind: "news",
              title: "Fed holds rates as inflation cools",
              captured_at: "2026-09-02",
            },
          ],
          workspaceResearch: [],
          workspaceLoading: false,
        },
        stubs: {
          RouterLink: { props: ["to"], template: "<a><slot /></a>" },
        },
      },
    });
  }

  it("renders a Yahoo-style markets board with indexes, movers, and headlines", async () => {
    const wrapper = mountRadar();
    await flushPromises();

    expect(wrapper.text()).toContain("Market");
    expect(wrapper.text()).toContain("S&P 500");
    expect(wrapper.text()).toContain("SPY");
    expect(wrapper.text()).toContain("Gainers");
    expect(wrapper.text()).toContain("Losers");
    expect(wrapper.text()).toContain("Most Active");
    expect(wrapper.text()).toContain("Watchlist");
    expect(wrapper.text()).toContain("Screener");
    expect(wrapper.text()).toContain("Profile");
    expect(wrapper.text()).toContain("Statistics");
    expect(wrapper.text()).toContain("Financials");
    expect(wrapper.text()).toContain("COMP");
    expect(wrapper.text()).toContain("Why is this moving?");
    expect(wrapper.text()).toContain("EVTS");
    expect(wrapper.text()).toContain("NVDA");
    expect(api.quotePeers).toHaveBeenCalled();
    expect(api.quoteCalendar).toHaveBeenCalled();
    expect(wrapper.text()).toContain("Fed holds rates as inflation cools");
    expect(wrapper.text()).toContain("Risk-on");
    expect(wrapper.text()).toContain("1D");
    expect(api.quoteChart).toHaveBeenCalledWith("SPY", "1d");

    const losers = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Losers") && el.attributes("role") === "tab");
    await losers.trigger("click");
    expect(wrapper.text()).toContain("TSM");
  });

  it("searches for a ticker and loads that quote chart", async () => {
    const wrapper = mountRadar();
    await flushPromises();

    const input = wrapper.get("input[type='search']");
    await input.setValue("AAPL");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("AAPL");
    expect(api.quoteChart).toHaveBeenCalledWith("AAPL", "1d");

    const oneYear = wrapper
      .findAll("button")
      .find((el) => el.text() === "1Y");
    await oneYear.trigger("click");
    await flushPromises();
    expect(api.quoteChart).toHaveBeenCalledWith("AAPL", "1y");
    expect(api.quoteWorkspace).toHaveBeenCalledWith("AAPL");
  });

  it("loads the Nasdaq screener board", async () => {
    const wrapper = mountRadar();
    await flushPromises();

    const screener = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Screener") && el.attributes("role") === "tab");
    await screener.trigger("click");
    expect(wrapper.text()).toContain("XYZ");
    expect(api.quoteScreeners).toHaveBeenCalled();
  });

  it("defaults to a split desk and expands to full width", async () => {
    const wrapper = mountRadar();
    await flushPromises();

    const grid = wrapper.find(".grid.lg\\:grid-cols-12");
    expect(grid.exists()).toBe(true);
    expect(wrapper.find("#market-news").classes()).not.toContain("lg:col-span-2");

    const expand = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Expand"));
    expect(expand).toBeTruthy();
    await expand.trigger("click");
    await flushPromises();

    expect(wrapper.find(".grid.lg\\:grid-cols-12").exists()).toBe(false);
    expect(wrapper.find("#market-news").classes()).toContain("lg:col-span-2");
    expect(replace).toHaveBeenCalled();
    expect(replace.mock.calls.at(-1)[0].query.wide).toBe("1");

    const collapse = wrapper
      .findAll("button")
      .find((el) => el.text().includes("Collapse"));
    await collapse.trigger("click");
    await flushPromises();
    expect(wrapper.find(".grid.lg\\:grid-cols-12").exists()).toBe(true);
  });
});
