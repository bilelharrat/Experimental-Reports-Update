import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import MarketPulseView from "../src/views/MarketPulseView.vue";
import EvidenceMatrixView from "../src/views/EvidenceMatrixView.vue";
import HypothesisLabView from "../src/views/HypothesisLabView.vue";
import { api } from "../src/api.js";

vi.mock("vue-router", () => ({
  RouterLink: {
    props: ["to"],
    template: "<a href='#'><slot /></a>",
  },
  useRoute: () => ({ query: {} }),
}));

vi.mock("../src/api.js", () => ({
  api: {
    jobLog: vi.fn(),
    researchPages: {
      marketPulse: vi.fn(),
      evidenceMatrix: vi.fn(),
      hypothesisLab: vi.fn(),
    },
    stockResearch: {
      listTrackers: vi.fn(),
      runSelectedTrackers: vi.fn(),
      runAggregate: vi.fn(),
      createHypotheses: vi.fn(),
      evaluateHypotheses: vi.fn(),
      calibrateHypotheses: vi.fn(),
    },
  },
}));

function marketPayload() {
  return {
    schema_version: 1,
    page_id: "market_pulse",
    generated_at: "2026-06-17T00:00:00+00:00",
    as_of: "2026-06-14",
    status: "partial",
    summary: {
      period_id: "2026-06-08_to_2026-06-14",
      signal_count: 1,
      primary_source_signal_count: 1,
      weak_or_missing_signal_count: 0,
    },
    source_health: { average_source_quality: 0.9, source_trace_count: 1 },
    doctor_issues: [],
    sections: {
      market_regime: {
        posture: "risk-on",
        breadth: { positive_signals: 1, negative_signals: 0, neutral_signals: 0 },
        volatility: { status: "placeholder" },
      },
      ranked_signals: [
        {
          signal_id: "sig-ai",
          signal: "AI infrastructure demand remains the key signal.",
          direction: "bullish",
          confidence: 0.82,
          source_quality_score: 0.91,
          source_quality_reason: "1 primary source; best source is earnings call transcript.",
          primary_source_count: 1,
          weak_source_count: 0,
          related_tickers: ["NVDA"],
          related_themes: ["AI infrastructure"],
          source_refs: [
            {
              source_id: "src-1",
              source_title: "Q1 transcript",
              source_type: "earnings_call_transcript",
              locator: "p. 4",
              excerpt: "Demand remains resilient.",
              confidence: 0.9,
              source_exists: true,
            },
          ],
        },
      ],
      theme_heatmap: [
        {
          theme: "AI infrastructure",
          signal_count: 1,
          average_quality: 0.91,
          net_direction: 1,
        },
      ],
      changed_since_last_week: {
        new_signals: [],
        fading_signals: [],
        revised_conviction: [],
      },
      catalyst_calendar: [
        {
          event_date: "2026-06-20",
          ticker_or_theme: "NVDA",
          event: "Investor day",
          expected_impact: "medium",
        },
      ],
    },
  };
}

function evidencePayload() {
  const claim = {
    claim_id: "claim-1",
    company_id: "nvda",
    company_name: "NVDA",
    claim: "AI demand remains resilient.",
    claim_type: "market",
    importance: "high",
    status: "needs_review",
    evidence_strength: 0.78,
    source_quality_score: 0.9,
    source_count: 1,
    primary_source_count: 1,
    weak_source_count: 0,
    contradiction_count: 1,
    source_refs: [
      {
        source_id: "src-1",
        source_title: "Transcript",
        source_type: "earnings_call_transcript",
        confidence: 0.9,
      },
    ],
    contradictions: [
      {
        source_id: "src-2",
        source_title: "Supply-chain check",
        source_type: "broker_note",
      },
    ],
    eligible_for_memo: false,
    eligible_for_hypothesis: true,
    memo_eligibility_reason: "Memo blocked because claim status is needs_review.",
    hypothesis_eligibility_reason: "Eligible for hypothesis review.",
  };
  return {
    schema_version: 1,
    page_id: "evidence_matrix",
    generated_at: "2026-06-17T00:00:00+00:00",
    as_of: "2026-06-17",
    status: "partial",
    summary: {
      claim_count: 1,
      unsupported_claim_count: 0,
      contradicted_claim_count: 1,
      memo_eligible_claim_count: 0,
    },
    source_health: { source_trace_count: 1 },
    doctor_issues: [
      {
        severity: "warning",
        type: "evidence_claim_has_unresolved_contradiction",
        message: "Claim has unresolved contradicting evidence.",
      },
    ],
    sections: {
      evidence_strength_matrix: [
        {
          evidence_quality: "high",
          claim_importance: "high",
          status: "contradicted",
          claim_count: 1,
          contradiction_count: 1,
        },
      ],
      claim_table: [claim],
      source_provenance: [
        {
          source_id: "src-1",
          source_title: "Transcript",
          source_type: "earnings_call_transcript",
          trace_count: 1,
          claims_supported: 1,
        },
      ],
      contradictions_lane: [
        {
          claim_id: "claim-1",
          claim: claim.claim,
          contradicting_source: claim.contradictions[0],
          analyst_action: "Start research task.",
        },
      ],
      unsupported_filters: { no_source_trace: 0, weak_source_only: 0, stale_source_only: 0 },
    },
  };
}

function hypothesisPayload() {
  return {
    schema_version: 1,
    page_id: "hypothesis_lab",
    generated_at: "2026-06-17T00:00:00+00:00",
    as_of: "2026-06-17",
    status: "partial",
    summary: {
      hypothesis_count: 2,
      live_hypothesis_count: 1,
      debug_hypothesis_count: 1,
      evaluated_count: 1,
    },
    source_health: { source_trace_count: 1 },
    doctor_issues: [
      {
        severity: "warning",
        type: "missing_current_live_hypothesis_vintage",
        message: "No current forward-live hypothesis vintage exists.",
      },
    ],
    sections: {
      vintage_timeline: [
        {
          vintage_date: "2026-06-14",
          vintage_kind: "forward_live",
          generated_count: 1,
          evaluated_count: 1,
          pending_count: 0,
          training_eligible_count: 1,
          training_eligibility: "eligible_after_evaluation",
        },
        {
          vintage_date: "2026-06-07",
          vintage_kind: "debug_backfill",
          generated_count: 1,
          evaluated_count: 0,
          pending_count: 1,
          training_eligible_count: 0,
          training_eligibility: "ineligible_debug_backfill",
        },
      ],
      hypotheses: [
        {
          hypothesis_id: "hyp-live",
          vintage_date: "2026-06-14",
          vintage_kind: "forward_live",
          training_eligible: true,
          ticker: "NVDA",
          claim: "AI demand remains resilient.",
          direction: "bullish",
          confidence: 0.8,
          source_quality_score: 0.9,
          evaluation_window_start: "2026-06-15",
          evaluation_window_end: "2026-06-21",
          status: "evaluated",
        },
        {
          hypothesis_id: "hyp-debug",
          vintage_date: "2026-06-07",
          vintage_kind: "debug_backfill",
          training_eligible: false,
          ticker: "NVDA",
          claim: "Debug backfill claim.",
          direction: "bullish",
          confidence: 0.7,
          source_quality_score: 0.5,
          evaluation_window_start: "2026-06-08",
          evaluation_window_end: "2026-06-14",
          status: "closed_pending",
        },
      ],
      outcomes: [
        {
          hypothesis_id: "hyp-live",
          ticker: "NVDA",
          absolute_return_pct: 10,
          benchmark_return_pct: 2,
          relative_return_pct: 8,
          directional_result: "hit",
          eligible_for_training: true,
        },
      ],
      calibration: [
        { confidence_bucket: "high", hit_rate: 1, average_relative_return: 8, sample_size: 1 },
      ],
    },
  };
}

describe("research page views", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-17T12:00:00Z"));
    vi.clearAllMocks();
    api.researchPages.marketPulse.mockResolvedValue(marketPayload());
    api.researchPages.evidenceMatrix.mockResolvedValue(evidencePayload());
    api.researchPages.hypothesisLab.mockResolvedValue(hypothesisPayload());
    api.stockResearch.listTrackers.mockResolvedValue([{ id: "us-macro", status: "active" }]);
    api.stockResearch.runSelectedTrackers.mockResolvedValue({
      launched: [{ tracker_id: "us-macro", log_url: "/api/jobs/log?path=stock_tracker:us-macro/run-1" }],
      errors: [],
    });
    api.stockResearch.runAggregate.mockResolvedValue({
      status: "queued",
      period_id: "2026-06-08_to_2026-06-14",
      log_url: "/api/jobs/log?path=stock_aggregate:2026-06-08_to_2026-06-14",
    });
    api.jobLog.mockResolvedValue([{ type: "done" }]);
    api.stockResearch.createHypotheses.mockResolvedValue({});
    api.stockResearch.evaluateHypotheses.mockResolvedValue({});
    api.stockResearch.calibrateHypotheses.mockResolvedValue({});
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders Market Pulse ranked signals and heat map with honest placeholder action", async () => {
    const wrapper = mount(MarketPulseView);
    await flushPromises();

    expect(wrapper.text()).toContain("Ranked Signals");
    expect(wrapper.text()).toContain("AI infrastructure demand remains the key signal.");
    expect(wrapper.text()).toContain("Theme Heat Map");
    expect(wrapper.text()).toContain("AI infrastructure");

    expect(wrapper.find("button[title^='Signal-specific hypothesis drafting']").attributes("disabled")).toBeDefined();

    await wrapper.findAll("button").find((button) => button.text() === "Refresh").trigger("click");
    await flushPromises();

    expect(api.stockResearch.listTrackers).toHaveBeenCalledWith({ includeArchived: false });
    expect(api.stockResearch.runSelectedTrackers).toHaveBeenCalledWith(["us-macro"]);
    expect(api.stockResearch.runAggregate).toHaveBeenCalledWith({ force: true });
    expect(api.jobLog).toHaveBeenCalledWith("/api/jobs/log?path=stock_tracker:us-macro/run-1");
    expect(api.jobLog).toHaveBeenCalledWith(
      "/api/jobs/log?path=stock_aggregate:2026-06-08_to_2026-06-14",
    );
    expect(api.researchPages.marketPulse).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Full refresh complete: ran 1 tracker and rebuilt 1 signal.");
  });

  it("renders Evidence Matrix visuals, filters, provenance, and contradictions", async () => {
    const wrapper = mount(EvidenceMatrixView);
    await flushPromises();

    expect(wrapper.text()).toContain("Evidence Strength Matrix");
    expect(wrapper.text()).toContain("Claim Table");
    expect(wrapper.text()).toContain("AI demand remains resilient.");
    expect(wrapper.text()).toContain("Source Provenance");
    expect(wrapper.text()).toContain("Contradictions Lane");
    expect(wrapper.text()).toContain("Memo blocked because claim status is needs_review.");

    await wrapper.findAll("button").find((button) => button.text() === "contradicted").trigger("click");
    expect(wrapper.text()).toContain("1 shown");
    expect(wrapper.find("button[title='Memo blocked because claim status is needs_review.']").attributes("disabled")).toBeDefined();

    await wrapper.findAll("button").find((button) => button.text() === "Refresh").trigger("click");
    await flushPromises();

    expect(api.stockResearch.listTrackers).toHaveBeenCalledWith({ includeArchived: false });
    expect(api.stockResearch.runSelectedTrackers).toHaveBeenCalledWith(["us-macro"]);
    expect(api.stockResearch.runAggregate).toHaveBeenCalledWith({ force: true });
    expect(api.jobLog).toHaveBeenCalledWith("/api/jobs/log?path=stock_tracker:us-macro/run-1");
    expect(api.jobLog).toHaveBeenCalledWith(
      "/api/jobs/log?path=stock_aggregate:2026-06-08_to_2026-06-14",
    );
    expect(api.researchPages.evidenceMatrix).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Full refresh complete: ran 1 tracker and rebuilt 1 claim.");
  });

  it("renders Hypothesis Lab timeline, tables, calibration, and debug exclusion", async () => {
    const wrapper = mount(HypothesisLabView);
    await flushPromises();

    expect(wrapper.text()).toContain("Vintage Controls");
    expect(wrapper.text()).toContain("Hypothesis Table");
    expect(wrapper.text()).toContain("Outcome Table");
    expect(wrapper.text()).toContain("Calibration Chart");
    expect(wrapper.text()).toContain("debug excluded");
    expect(wrapper.text()).toContain("not eligible");

    await wrapper.findAll("button").find((button) => button.text() === "Refresh").trigger("click");
    await flushPromises();

    expect(api.stockResearch.createHypotheses).toHaveBeenCalledWith({
      vintageDate: "2026-06-17",
      vintageKind: "forward_live",
      allowDebugBackfill: false,
    });
    expect(api.stockResearch.calibrateHypotheses).toHaveBeenCalledOnce();
    expect(api.researchPages.hypothesisLab).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Hypothesis cycle refreshed: current live vintage has 0 hypotheses");

    await wrapper.findAll("button").find((button) => button.text() === "Calibrate").trigger("click");
    await flushPromises();

    expect(api.stockResearch.calibrateHypotheses).toHaveBeenCalledTimes(2);

    const debugInput = wrapper.findAll("input[type='date']")[1];
    await debugInput.setValue("2026-06-17");
    await wrapper.findAll("button").find((button) => button.text() === "Debug Backfill").trigger("click");
    await flushPromises();

    expect(api.stockResearch.createHypotheses).toHaveBeenLastCalledWith({
      vintageDate: "2026-06-17",
      vintageKind: "debug_backfill",
      allowDebugBackfill: true,
    });
  });
});
