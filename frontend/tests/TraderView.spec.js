// Component test for TraderView.vue — verifies the empty state vs the
// populated grid and the refresh button wiring. The api module is
// mocked so the component mounts without HTTP.

import { afterEach, describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { appLanguage } from "../src/state.js";

const m = vi.hoisted(() => ({
  refresh: vi.fn(() => Promise.resolve({
    job_id: "amd", status: "queued",
    stream_url: "/api/companies/amd/trader/refresh/stream",
  })),
  refreshSections: vi.fn(() => Promise.resolve({
    job_id: "amd", status: "queued",
    stream_url: "/api/companies/amd/trader/refresh/stream",
  })),
  streamUrl: vi.fn(() => "/fake/stream"),
  getCompany: vi.fn(() => Promise.resolve({ id: "amd", trader_snapshot: null })),
}));

vi.mock("../src/api.js", () => ({
  api: {
    trader: {
      refresh: m.refresh,
      refreshSections: m.refreshSections,
      streamUrl: m.streamUrl,
    },
    getCompany: m.getCompany,
  },
}));

class FakeEventSource {
  constructor() {
    this.onmessage = null;
    this.onerror = null;
  }
  close() {}
}
globalThis.EventSource = FakeEventSource;

import TraderView from "../src/components/TraderView.vue";

function mountWith(company) {
  return mount(TraderView, { props: { company } });
}


async function openMarketDetail(wrapper) {
  const btn = wrapper.findAll("button").find((b) => /Market detail|市场详情/.test(b.text()));
  if (btn) await btn.trigger("click");
}

describe("TraderView empty state", () => {
  it("renders the 'no snapshot yet' hint when trader_snapshot is null", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: null,
    });
    expect(wrapper.text()).toContain("No market snapshot yet");
  });
});

describe("TraderView populated state", () => {
  const snapshot = {
    refreshed_at: new Date().toISOString(),
    price_card: {
      last_price: 174.22, currency: "USD", as_of: "2026-05-13T15:59:00-04:00",
      change_pct_1d: 1.82, change_pct_5d: 4.10, change_pct_30d: 12.41,
      change_pct_ytd: 28.03, change_pct_1y: 47.55,
      vs_sector_30d_pct: 14.20, vs_sp500_30d_pct: 9.80,
    },
    momentum_card: {
      trend: "bullish", above_50dma: true, above_200dma: true,
      ma_crossover_recent: null, breakout_signals: ["5-day high"],
      notable_levels: { support: 162, resistance: 178.5 },
    },
    sentiment_card: {
      analyst_consensus: "Buy", coverage_count: 51,
      rating_distribution: {
        strong_buy: 18, buy: 20, hold: 12, sell: 1, strong_sell: 0,
      },
      target_price: { mean: 195, high: 230, low: 148 },
      recent_rating_changes: [],
    },
    heat_card: {
      rel_volume_20d: 1.4, iv_30d_pct: 42, iv_percentile_1y: 78,
      options_skew: "call_bid", news_flow_24h: 11,
      insider_activity_30d: { buys: 0, sells: 2, net_share_count_change: -45000 },
      short_interest_pct_float: 2.1, days_to_cover: 1.8,
      social_mentions_trend: "rising",
    },
    catalysts: [
      { date: "2026-07-30", type: "earnings", title: "Q2 2026 earnings",
        summary: "", est_impact: "high" },
    ],
    trader_news: [
      { headline: "Q1 beat", date: "2026-05-07", summary: "",
        bias: "positive", source_url: "https://example.com" },
    ],
  };

  it("renders the price card with the last price and a 1d return", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("$174.22");
    expect(text).toContain("+1.8%");
    expect(text).toContain("Buy");
    expect(text).toContain("Q2 2026 earnings");
    expect(text).toContain("Q1 beat");
  });

  it("clicking Refresh calls api.trader.refresh", async () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshot,
    });
    const button = wrapper.findAll("button")
      .find((b) => b.text().includes("Refresh"));
    expect(button).toBeTruthy();
    await button.trigger("click");
    await flushPromises();
    expect(m.refresh).toHaveBeenCalledWith("amd");
  });

  it("renders failed section state and retries only that section", async () => {
    const wrapper = mountWith({
      id: "amd",
      name: "AMD",
      company_type: "public",
      trader_snapshot: {
        ...snapshot,
        section_status: {
          catalysts: {
            status: "failed",
            last_error: "stalled after 120s without output",
            retryable: true,
          },
        },
      },
    });

    expect(wrapper.text()).toContain("Upcoming catalysts");
    expect(wrapper.text()).toContain("stalled after 120s without output");

    const button = wrapper.findAll("button")
      .find((b) => b.text().includes("Retry section"));
    expect(button).toBeTruthy();
    await button.trigger("click");
    await flushPromises();
    expect(m.refreshSections).toHaveBeenCalledWith(
      "amd",
      ["catalysts"],
      { force: true, preserveExistingSections: true },
    );
  });
});

describe("TraderView Positioning Structure (heat_card v2)", () => {
  // The Heat card is now "Positioning Structure". Each section is
  // independently nullable + carries a declarative `confidence` enum +
  // bilingual `confidence_note_*`. The card renders only the sections
  // present; an "unavailable" section collapses to its confidence note.

  function snapshotWithHeat(heat, opts = {}) {
    return {
      refreshed_at: new Date().toISOString(),
      schema_version: opts.schema_version ?? 2,
      price_card: { last_price: 446.4, currency: "USD", as_of: null,
        change_pct_1d: null, change_pct_5d: null, change_pct_30d: null,
        change_pct_ytd: null, change_pct_1y: null,
        vs_sector_30d_pct: null, vs_sp500_30d_pct: null },
      momentum_card: { trend: null, above_50dma: null, above_200dma: null,
        ma_crossover_recent: null, breakout_signals: [],
        notable_levels: null },
      sentiment_card: { analyst_consensus: null, coverage_count: null,
        rating_distribution: null, target_price: null,
        recent_rating_changes: [] },
      heat_card: heat,
      catalysts: [],
      trader_news: [],
    };
  }

  const fullHeat = {
    anchored_vwaps: {
      current_price: 446.4,
      anchors: [
        { kind: "earnings", label_en: "Q1 earnings", label_zh: "一季报",
          date: "2026-05-05", price: 421.39 },
        { kind: "52w_high", label_en: "52-week high", label_zh: "52周高点",
          date: "2026-05-08", price: 469.22 },
      ],
      confidence: "medium",
      confidence_note_en: "Yahoo Finance closes.",
      confidence_note_zh: "雅虎财经收盘价。",
    },
    float_turnover_zones: {
      zones: [
        { low: 412, high: 425, pct_float: 22,
          note_en: "Post-earnings accumulation.",
          note_zh: "财报后吸筹。" },
      ],
      confidence: "low",
      confidence_note_en: "Estimated from volume profile.",
      confidence_note_zh: "基于成交量分布估算。",
    },
    holder_mix: {
      passive_pct: 35, long_only_pct: 28, hedge_fund_pct: 22,
      retail_pct: 10, insider_pct: 1.5, strategic_pct: 3.5,
      quality_label_en: "Passive anchor, HF overhang.",
      quality_label_zh: "被动资金锚定，对冲基金存在抛压。",
      confidence: "high",
      confidence_note_en: "Whalewisdom 13F.",
      confidence_note_zh: "Whalewisdom 13F 数据。",
    },
    options_positioning: {
      gamma_flip: null, put_wall: null, call_wall: null,
      regime_en: null, regime_zh: null,
      confidence: "unavailable",
      confidence_note_en: "SpotGamma pay-walled.",
      confidence_note_zh: "SpotGamma 付费墙。",
    },
    short_pressure: {
      si_pct_float: 2.2, days_to_cover: 0.8, borrow_rate_pct: 0.5,
      trend: "falling",
      note_en: "Low SI + low borrow.",
      note_zh: "空头持仓低，借券成本低。",
      confidence: "high",
      confidence_note_en: "FINRA SI + Iborrow.",
      confidence_note_zh: "FINRA + Iborrow。",
    },
    valuation: {
      ev_revenue_current: 12, ev_revenue_5y_percentile: 18,
      fwd_ev_ebitda: 22, peg: 1.4,
      note_en: "Downside compressed.",
      note_zh: "下行空间已压缩。",
      confidence: "high",
      confidence_note_en: "YCharts.",
      confidence_note_zh: "YCharts 数据。",
    },
    revisions: {
      eps_up_30d: 14, eps_down_30d: 3,
      eps_up_90d: 22, eps_down_90d: 8,
      direction: "up",
      note_en: "Momentum positive.",
      note_zh: "趋势偏正。",
      confidence: "medium",
      confidence_note_en: "Zacks.",
      confidence_note_zh: "Zacks 数据。",
    },
    next_catalyst: {
      label_en: "Q2 2026 earnings",
      label_zh: "二季度财报",
      date: "2026-07-30",
      implied_move_pct: 11,
      confidence: "high",
      confidence_note_en: "ATM straddle.",
      confidence_note_zh: "ATM跨式期权报价。",
    },
    support_confidence: {
      zones: [
        { low: 412, high: 425, confidence: "high",
          reasons_en: ["AVWAP earnings", "22% turnover"],
          reasons_zh: ["财报后VWAP", "22% 换手"] },
      ],
      confidence: "medium",
      confidence_note_en: "Weighted.",
      confidence_note_zh: "综合权重。",
    },
    fragility: {
      score: 55, rating: "medium",
      drivers_en: ["AI narrative ~55%", "HF crowded"],
      drivers_zh: ["AI叙事约55%", "对冲基金拥挤"],
      confidence: "medium",
      confidence_note_en: "Composite.",
      confidence_note_zh: "综合得出。",
    },
    repricing_risk: {
      positive_pct: 35, neutral_pct: 40, negative_pct: 25,
      note_en: "Earnings momentum tilts positive.",
      note_zh: "盈利动能偏正。",
      confidence: "medium",
      confidence_note_en: "Composite.",
      confidence_note_zh: "综合。",
    },
  };

  it("renders all eight sections + three composites when fully populated", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(fullHeat),
    });
    const text = wrapper.text();
    // Card title:
    expect(text).toContain("Positioning Structure");
    // Section markers visible:
    expect(text).toContain("Anchored cost basis");
    expect(text).toContain("Float turnover");
    expect(text).toContain("Holder mix");
    expect(text).toContain("Options regime");
    expect(text).toContain("Short pressure");
    expect(text).toContain("Valuation");
    expect(text).toContain("Revisions");
    expect(text).toContain("Next catalyst");
    expect(text).toContain("Support confidence");
    expect(text).toContain("Fragility");
    expect(text).toContain("Repricing risk");
    // Selected values:
    expect(text).toContain("$421.39");
    expect(text).toContain("Passive");
    expect(text).toContain("35%");
    expect(text).toContain("12.0×");
    expect(text).toContain("Implied move ±11.0%");
    expect(text).toContain("55/100");
  });

  it("collapses an `unavailable` section to its confidence_note", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(fullHeat),
    });
    const text = wrapper.text();
    // options_positioning is marked unavailable in the fixture — the
    // section renders the bilingual confidence_note rather than three
    // null-priced rows.
    expect(text).toContain("SpotGamma pay-walled.");
    expect(text).not.toContain("Gamma flip$");
  });

  it("hides individual sections entirely when their sub-object is null", () => {
    const partial = {
      ...fullHeat,
      anchored_vwaps: null,
      options_positioning: null,
      revisions: null,
    };
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(partial),
    });
    const text = wrapper.text();
    expect(text).not.toContain("Anchored cost basis");
    expect(text).not.toContain("Options regime");
    expect(text).not.toContain("Revisions");
    // Other sections still render.
    expect(text).toContain("Holder mix");
    expect(text).toContain("Short pressure");
  });

  it("shows the legacy-schema banner + force-refresh button when schema_version < 2", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(null, { schema_version: 1 }),
    });
    const text = wrapper.text();
    expect(text).toContain("Older snapshot");
    expect(text).toContain("Force refresh");
  });

  it("shows the empty state when heat_card is missing entirely", () => {
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(null),
    });
    const text = wrapper.text();
    expect(text).toContain("No positioning data yet");
  });

  it("renders Chinese labels when app language is zh", async () => {
    appLanguage.value = "zh";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(fullHeat),
    });
    const text = wrapper.text();
    expect(text).toContain("持仓结构");
    expect(text).toContain("锚定成本");
    expect(text).toContain("一季报");
    expect(text).toContain("被动");
    expect(text).toContain("SpotGamma 付费墙。");
  });

  it("re-renders trader-view content when appLanguage flips after mount", async () => {
    // Pins the live reactivity contract: the sidebar's EN/中 toggle
    // flips `appLanguage`, and every label + bilingual prose field
    // in the trader view must update without unmounting / remounting.
    appLanguage.value = "en";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: snapshotWithHeat(fullHeat),
    });
    // Sanity: mounted in English.
    let text = wrapper.text();
    expect(text).toContain("Positioning Structure");      // section label (t())
    expect(text).toContain("Anchored cost basis");
    expect(text).toContain("Q1 earnings");                // anchor label (pickLocalized)
    expect(text).toContain("Passive anchor, HF overhang."); // holder quality (pickLocalized)
    expect(text).not.toContain("持仓结构");

    // Flip global app language — emulates the user clicking
    // setAppLanguage('zh') from the sidebar.
    appLanguage.value = "zh";
    await flushPromises();
    await wrapper.vm.$nextTick();

    text = wrapper.text();
    // Static label re-translated via useT().
    expect(text).toContain("持仓结构");
    expect(text).toContain("锚定成本");
    // Bilingual prose re-picked via pickLocalized.
    expect(text).toContain("一季报");
    expect(text).toContain("被动资金锚定，对冲基金存在抛压。");
    // English shouldn't still be visible for fields we flipped.
    expect(text).not.toContain("Positioning Structure");
  });
});

describe("TraderView Research Overview", () => {
  const researchSnapshot = {
    refreshed_at: new Date().toISOString(),
    schema_version: 2,
    price_card: {
      last_price: 174.22, currency: "USD", as_of: null,
      change_pct_1d: null, change_pct_5d: null, change_pct_30d: null,
      change_pct_ytd: null, change_pct_1y: null,
      vs_sector_30d_pct: null, vs_sp500_30d_pct: null,
    },
    momentum_card: {
      trend: null, above_50dma: null, above_200dma: null,
      ma_crossover_recent: null, breakout_signals: [],
      notable_levels: null,
    },
    sentiment_card: {
      analyst_consensus: null, coverage_count: null,
      rating_distribution: null, target_price: null,
      recent_rating_changes: [],
    },
    heat_card: null,
    catalysts: [],
    trader_news: [],
    research_overview: {
      updated_at: new Date().toISOString(),
      business_mix: {
        headline_en: "Data center is the growth engine; gaming is the drag.",
        headline_zh: "数据中心是增长引擎，游戏业务拖累增长。",
        segments: [
          {
            name_en: "Data Center", name_zh: "数据中心",
            revenue_pct: 52, growth_pct: 47, signal: "growth_engine",
            note_en: "MI accelerators drive mix shift.",
            note_zh: "MI 加速器推动结构转变。",
          },
          {
            name_en: "Gaming", name_zh: "游戏",
            revenue_pct: 14, growth_pct: -22, signal: "drag",
            note_en: "Console cycle pressure.",
            note_zh: "主机周期带来压力。",
          },
        ],
        source_url: "https://example.com/segments",
        confidence: "high",
        confidence_note_en: "Company segment filing.",
        confidence_note_zh: "公司分部披露。",
      },
      financial_quality: {
        score: 74,
        summary_en: "Margins are improving while R&D remains high.",
        summary_zh: "利润率改善，同时研发投入仍高。",
        metrics: [
          {
            label_en: "Gross margin", label_zh: "毛利率",
            value: "54%", percentile: 70, direction: "strong",
            note_en: "Above peer median.",
            note_zh: "高于同业中位数。",
          },
        ],
        source_url: "https://example.com/financials",
        confidence: "medium",
        confidence_note_en: "Company financials and peer comps.",
        confidence_note_zh: "公司财务和同业对比。",
      },
      growth_durability: {
        thesis_en: "Growth depends on AI accelerator ramps.",
        thesis_zh: "增长取决于 AI 加速器爬坡。",
        horizons: [
          {
            period: "FY26", revenue_growth_pct: 28,
            eps_growth_pct: 36, margin_delta_bp: 180,
            note_en: "AI offsets PC normalization.",
            note_zh: "AI 抵消 PC 正常化。",
          },
        ],
        source_url: "https://example.com/estimates",
        confidence: "medium",
        confidence_note_en: "Consensus estimates.",
        confidence_note_zh: "市场一致预期。",
      },
      peer_context: {
        summary_en: "AMD screens higher growth, lower margin than NVDA.",
        summary_zh: "AMD 增速较高，但毛利率低于英伟达。",
        peers: [
          {
            ticker: "NVDA", company_en: "NVIDIA", company_zh: "英伟达",
            score: 92, revenue_growth_pct: 38, gross_margin_pct: 74,
            valuation_premium_pct: 120,
            note_en: "Best-in-class accelerator margin.",
            note_zh: "加速器利润率同业领先。",
          },
        ],
        source_url: "https://example.com/peers",
        confidence: "medium",
        confidence_note_en: "Public peer data.",
        confidence_note_zh: "公开同业数据。",
      },
      scenario_matrix: {
        summary_en: "Upside requires accelerator share gains.",
        summary_zh: "上行需要加速器份额提升。",
        scenarios: [
          {
            case: "bull", label_en: "Bull case", label_zh: "牛市情景",
            probability_pct: 30, implied_return_pct: 35,
            key_driver_en: "MI share accelerates.",
            key_driver_zh: "MI 份额加速提升。",
          },
          {
            case: "bear", label_en: "Bear case", label_zh: "熊市情景",
            probability_pct: 20, implied_return_pct: -28,
            key_driver_en: "GPU supply disappoints.",
            key_driver_zh: "GPU 供应不及预期。",
          },
        ],
        source_url: "https://example.com/scenarios",
        confidence: "low",
        confidence_note_en: "Desk scenario math.",
        confidence_note_zh: "交易台情景测算。",
      },
      diligence_questions: {
        summary_en: "The hard question is whether AI share gains persist.",
        summary_zh: "核心问题是 AI 份额提升能否持续。",
        questions: [
          {
            question_en: "Can AMD keep hyperscaler wins beyond pilot volume?",
            question_zh: "AMD 能否将超大客户试点量转化为持续订单？",
            why_it_matters_en: "Sustained orders decide AI revenue durability.",
            why_it_matters_zh: "持续订单决定 AI 收入可持续性。",
            severity: "critical",
            evidence_gap_en: "Customer-level disclosure remains limited.",
            evidence_gap_zh: "客户层面披露有限。",
          },
        ],
        source_url: "https://example.com/questions",
        confidence: "medium",
        confidence_note_en: "Cross-checked against filings and call.",
        confidence_note_zh: "对照文件和电话会。",
      },
    },
  };

  afterEach(() => {
    appLanguage.value = "en";
  });

  it("renders the second research card group with visual sections", () => {
    appLanguage.value = "en";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: researchSnapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("Research Overview");
    expect(text).toContain("Business mix");
    expect(text).toContain("Data Center");
    expect(text).toContain("Financial quality");
    expect(text).toContain("74/100");
    expect(text).toContain("Growth durability");
    expect(text).toContain("Peer context");
    expect(text).toContain("Scenario matrix");
    expect(text).toContain("Diligence questions");
    expect(text).toContain("Can AMD keep hyperscaler wins");
  });

  it("localizes research overview prose and labels", async () => {
    appLanguage.value = "zh";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: researchSnapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("研究概览");
    expect(text).toContain("业务结构");
    expect(text).toContain("数据中心");
    expect(text).toContain("财务质量");
    expect(text).toContain("增长持续性");
    expect(text).toContain("尽调问题");
    expect(text).toContain("AMD 能否将超大客户试点量转化为持续订单？");
  });
});

describe("TraderView bilingual rendering", () => {
  // The server emits paired `<base>_en` / `<base>_zh` for every prose
  // field plus a legacy single-language `<base>`. The component picks
  // the user's locale and falls back through the other language to the
  // legacy field, so each scenario below should pin down one branch of
  // that fallback.

  const bilingualSnapshot = {
    refreshed_at: new Date().toISOString(),
    available_languages: ["en", "zh"],
    price_card: {
      last_price: 174.22, currency: "USD", as_of: null,
      change_pct_1d: 1.82, change_pct_5d: null, change_pct_30d: null,
      change_pct_ytd: null, change_pct_1y: null,
      vs_sector_30d_pct: null, vs_sp500_30d_pct: null,
    },
    momentum_card: {
      trend: "bullish", trend_en: "Bullish", trend_zh: "看涨",
      above_50dma: true, above_200dma: true,
      ma_crossover_recent: null,
      breakout_signals: ["5-day high"],
      breakout_signals_en: ["5-day high"],
      breakout_signals_zh: ["创5日新高"],
      notable_levels: null,
    },
    sentiment_card: {
      analyst_consensus: "Buy",
      analyst_consensus_en: "Buy",
      analyst_consensus_zh: "买入",
      coverage_count: 12,
      rating_distribution: null,
      target_price: null,
      recent_rating_changes: [
        {
          firm: "MS",
          action: "Upgrade", action_en: "Upgrade", action_zh: "上调",
          from: "Hold", from_en: "Hold", from_zh: "持有",
          to: "Buy", to_en: "Buy", to_zh: "买入",
          date: "2026-05-08", target: 210,
        },
      ],
    },
    heat_card: null,
    catalysts: [
      {
        date: "2026-07-30", type: "earnings",
        title: "Q2 2026 earnings",
        title_en: "Q2 2026 earnings",
        title_zh: "2026年第二季度财报",
        summary: "After-hours; consensus EPS $1.28",
        summary_en: "After-hours; consensus EPS $1.28",
        summary_zh: "盘后发布；市场预期每股收益 1.28 美元。",
        est_impact: "high",
      },
    ],
    trader_news: [
      {
        headline: "Q1 beat on data-center",
        headline_en: "Q1 beat on data-center",
        headline_zh: "第一季度数据中心业务超预期",
        date: "2026-05-07",
        summary: "Data-center +47% YoY",
        summary_en: "Data-center +47% YoY",
        summary_zh: "数据中心业务同比增长47%。",
        bias: "positive",
        source_url: "https://example.com/q1",
      },
    ],
  };

  afterEach(() => {
    appLanguage.value = "en";
  });

  it("renders English text when app language is en", () => {
    appLanguage.value = "en";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: bilingualSnapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("Bullish");
    expect(text).toContain("5-day high");
    expect(text).toContain("Q2 2026 earnings");
    expect(text).toContain("Q1 beat on data-center");
    expect(text).toContain("Upgrade");
    expect(text).not.toContain("看涨");
    expect(text).not.toContain("买入");
    expect(text).not.toContain("创5日新高");
  });

  it("renders Chinese text when app language is zh", () => {
    appLanguage.value = "zh";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: bilingualSnapshot,
    });
    const text = wrapper.text();
    expect(text).toContain("看涨");
    expect(text).toContain("创5日新高");
    expect(text).toContain("买入");
    expect(text).toContain("2026年第二季度财报");
    expect(text).toContain("第一季度数据中心业务超预期");
    expect(text).toContain("上调");
    expect(text).not.toContain("Bullish");
    expect(text).not.toContain("Q1 beat on data-center");
  });

  it("falls back to legacy single-language fields when _en/_zh are missing", () => {
    // Old snapshots predate the bilingual contract. Chinese readers
    // should still see the legacy English copy rather than blanks.
    const legacy = {
      ...bilingualSnapshot,
      momentum_card: {
        ...bilingualSnapshot.momentum_card,
        trend_en: null, trend_zh: null,
        breakout_signals_en: [], breakout_signals_zh: [],
      },
      catalysts: [
        {
          date: "2026-07-30", type: "earnings",
          title: "Legacy earnings title",
          summary: "Legacy summary",
          est_impact: "high",
        },
      ],
      trader_news: [
        {
          headline: "Legacy headline",
          date: "2026-05-07",
          summary: "Legacy summary",
          bias: "positive",
          source_url: "https://example.com/legacy",
        },
      ],
    };
    appLanguage.value = "zh";
    const wrapper = mountWith({
      id: "amd", name: "AMD", company_type: "public",
      trader_snapshot: legacy,
    });
    const text = wrapper.text();
    expect(text).toContain("bullish");          // capitalize(trend)
    expect(text).toContain("5-day high");        // legacy array
    expect(text).toContain("Legacy earnings title");
    expect(text).toContain("Legacy headline");
  });
});
