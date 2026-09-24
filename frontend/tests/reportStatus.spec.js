import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { t } from "../src/i18n.js";
import { setAppLanguage } from "../src/state.js";
import {
  buyPriceAmount,
  cleanDisplayName,
  factCheckChip,
  factCheckTiers,
  gateLabel,
  qualityMetricsLine,
  reportCanOpen,
  reportFreshness,
  reportHeadline,
  reportIsDocless,
  reportIsPaused,
  reportListStatus,
  reportState,
  reportStatusLabel,
  reportWarnings,
  reviewActions,
  reviewChip,
  reviewRenderNote,
  sourceLabel,
  sourceLanguage,
  spanLabel,
  verdictChip,
  versionInfo,
} from "../src/reportStatus.js";
import { ANTHROPIC_COMPLETE, KO_BUFFETT, ZAINAR_WARNINGS, pausedReport, withReport } from "./fixtures/reportSummaries.js";
import {
  CIENET_LATE_NEW,
  GOOGLE_BUY,
  GOOGLE_PASS,
  OXY_PASS,
  PLACEHOLDER_FINANCIAL,
} from "./fixtures/reportReader.js";

const ALL = [
  "admin:read",
  "memo:approve",
  "memo:edit",
  "memo:export",
  "tasks:action",
];

describe("company names", () => {
  it("drops EDGAR suffix tokens the way server/company_names does", () => {
    expect(cleanDisplayName("Occidental Petroleum Corp /De/")).toBe("Occidental Petroleum Corp");
    expect(cleanDisplayName("OCCIDENTAL PETROLEUM CORP /DE/")).toBe("OCCIDENTAL PETROLEUM CORP");
    expect(cleanDisplayName("WELLS FARGO & COMPANY/MN")).toBe("WELLS FARGO & COMPANY");
    expect(cleanDisplayName("Some Holdings Corp /DE/ /NEW/")).toBe("Some Holdings Corp");
    expect(cleanDisplayName("Taiwan Semiconductor /ADR/")).toBe("Taiwan Semiconductor");
    expect(cleanDisplayName("Some Bank /MD/")).toBe("Some Bank");
  });

  it("leaves ordinary names alone and never strips a name to nothing", () => {
    expect(cleanDisplayName("Apple Inc.")).toBe("Apple Inc.");
    expect(cleanDisplayName("  Coca   Cola Co ")).toBe("Coca Cola Co");
    expect(cleanDisplayName("中经网数据有限公司")).toBe("中经网数据有限公司");
    expect(cleanDisplayName("AC/DC Holdings")).toBe("AC-DC Holdings");
    expect(cleanDisplayName("/DE/")).toBe("DE");
    expect(cleanDisplayName("")).toBe("");
    expect(cleanDisplayName(null)).toBe("");
  });
});

describe("the call", () => {
  beforeEach(() => setAppLanguage("en"));

  it("reads a Buffett Pass with a buy price as a price-conditional pass", () => {
    const chip = verdictChip(withReport(GOOGLE_PASS), t, "en");
    expect(chip.label).toBe("Pass · buy ≤ $215");
    expect(chip.tone).toBe("notice");
    expect(chip.title).toContain("Buy price: $215 per share or less");

    setAppLanguage("zh");
    const zh = verdictChip(withReport(GOOGLE_PASS), t, "zh");
    expect(zh.label).toBe("暂不买入 · 买入价 ≤ $215");
  });

  it("reads Buy with its ceiling, Too Hard and the business Pass", () => {
    expect(verdictChip(withReport(GOOGLE_BUY), t, "en").label).toBe("Buy · up to $360");
    expect(verdictChip(withReport(GOOGLE_BUY), t, "en").tone).toBe("success");
    expect(verdictChip(withReport(OXY_PASS), t, "en").label).toBe("Pass · buy ≤ $45");
    const tooHard = withReport(GOOGLE_PASS, { decision: "Too Hard", buy_price: "No bid today." });
    expect(verdictChip(tooHard, t, "en").label).toBe("Too Hard");
    const business = withReport(GOOGLE_PASS, { pass_kind: "business", buy_price: null, reader: {} });
    expect(verdictChip(business, t, "en").label).toBe("Pass · not at any price");
    setAppLanguage("zh");
    expect(verdictChip(tooHard, t, "zh").label).toBe("超出能力圈");
    expect(verdictChip(business, t, "zh").label).toBe("放弃");
  });

  it("prefers the structured buy price, and shows the server's call label as the tooltip", () => {
    const report = withReport(GOOGLE_PASS, {
      pass_kind: "price",
      buy_price_value: 114,
      currency: "USD",
      call_label: {
        en: "Pass at today's price — buy at or below $114",
        zh: "暂不买入（买入价 ≤ 114 美元）",
      },
    });
    const chip = verdictChip(report, t, "en");
    expect(chip.label).toBe("Pass · buy ≤ $114");
    expect(chip.title.split("\n")[0]).toBe("Pass at today's price — buy at or below $114");
    setAppLanguage("zh");
    expect(verdictChip(report, t, "zh").full).toBe("暂不买入（买入价 ≤ 114 美元）");
    expect(buyPriceAmount(withReport(report, { buffett_valuation: { value_basis: "company" }, buy_price_value: 13500 })))
      .toBe("$13.5 billion");
  });

  it("finds the amount in legacy free-text buy prices", () => {
    expect(buyPriceAmount({ buy_price: "No more than about US$220 per ADR" })).toBe("US$220");
    expect(buyPriceAmount({ buy_price: "Up to about $75 million for the whole company" })).toBe("$75 million");
    expect(buyPriceAmount({ buy_price: "About $70 per share (enthusiastic below $60)" })).toBe("$70");
    expect(buyPriceAmount({ buy_price: "No bid today." })).toBe("");
  });

  it("reads a late-stage verdict from the reader block, and nothing when no call is recorded", () => {
    expect(verdictChip(withReport(CIENET_LATE_NEW), t, "en")).toBeNull();
    const v2 = withReport(CIENET_LATE_NEW, { reader: { ...CIENET_LATE_NEW.reader, decision: "Watch" } });
    expect(verdictChip(v2, t, "en").label).toBe("Watch");
    setAppLanguage("zh");
    expect(verdictChip(v2, t, "zh").label).toBe("观察名单");
    const pass = withReport(CIENET_LATE_NEW, { decision: "Pass" });
    expect(verdictChip(pass, t, "zh").label).toBe("不建议投资");
  });

  it("gives the headline in the UI language, falling back to the other", () => {
    expect(reportHeadline(GOOGLE_PASS, "en")).toMatch(/^I think the core business/);
    expect(reportHeadline(GOOGLE_PASS, "zh")).toMatch(/^我认为核心业务/);
    const englishOnly = withReport(GOOGLE_PASS, { reader: { headline: { en: "Only English.", zh: null } } });
    expect(reportHeadline(englishOnly, "zh")).toBe("Only English.");
    expect(reportHeadline(PLACEHOLDER_FINANCIAL, "en")).toBe("");
  });
});

describe("freshness", () => {
  const at = (iso) => new Date(iso).getTime();

  it("says when a memo was written and how long ago", () => {
    const report = withReport(GOOGLE_PASS);
    const fresh = reportFreshness(report, t, "en", at("2026-09-22T12:00:00"));
    expect(fresh.text).toBe("Written Aug 25 · 28 days ago");
    expect(fresh.stale).toBe(false);
    expect(fresh.showSource).toBe(false);
  });

  it("names the latest source only when it is more than two weeks older, and turns amber after 30 days", () => {
    const zainar = withReport(ZAINAR_WARNINGS, {
      reader: { memo_as_of: "2026-08-31", evidence_latest: "2026-06-13", sources_dated: 10, sources_total: 10 },
    });
    const fresh = reportFreshness(zainar, t, "en", at("2026-09-22T12:00:00"));
    expect(fresh.text).toBe("Written Aug 31 · 22 days ago · latest source Jun 13");
    expect(fresh.stale).toBe(false);
    expect(fresh.title).toContain("79 days older than the memo");

    const recent = withReport(ZAINAR_WARNINGS, {
      reader: { memo_as_of: "2026-08-31", evidence_latest: "2026-08-20" },
    });
    expect(reportFreshness(recent, t, "en", at("2026-09-22T12:00:00")).showSource).toBe(false);

    const old = reportFreshness(zainar, t, "en", at("2026-10-05T12:00:00"));
    expect(old.stale).toBe(true);
    expect(old.text).toContain("35 days ago");

    expect(reportFreshness(zainar, t, "en", at("2026-08-31T18:00:00")).text).toContain("today");
    expect(reportFreshness(zainar, t, "en", at("2026-09-01T18:00:00")).text).toContain("yesterday");
    setAppLanguage("zh");
    expect(reportFreshness(zainar, t, "zh", at("2026-09-22T12:00:00")).text).toBe(
      "撰写于 8月31日 · 22 天前 · 最新来源 6月13日",
    );
    setAppLanguage("en");
  });

  it("is only for finished memos", () => {
    expect(reportFreshness(withReport(PLACEHOLDER_FINANCIAL), t, "en")).toBeNull();
    expect(reportFreshness(withReport(GOOGLE_PASS, { status: "analyzing" }), t, "en")).toBeNull();
  });
});

describe("honest fact-check labels", () => {
  it("says checks were not run when the record has none, rather than a percentage", () => {
    const chip = factCheckChip(withReport(ANTHROPIC_COMPLETE), t);
    expect(chip.state).toBe("not_run");
    expect(chip.label).toBe("Checks not run");
    expect(chip.title).toContain("predate the check");
    expect(factCheckChip(withReport(ANTHROPIC_COMPLETE, { memo_fact_check: { status: "not_run" } }), t).label).toBe(
      "Checks not run",
    );
  });

  it("calls a thin corpus not checkable, never 0%", () => {
    const chip = factCheckChip(
      withReport(ZAINAR_WARNINGS, {
        memo_fact_check: { status: "not_checkable", checked: 254, thin_corpus: true, coverage_pct: null, registry_only: 64 },
      }),
      t,
    );
    expect(chip.label).toBe("Not checkable: no sources on file");
    expect(chip.label).not.toMatch(/%/);
  });

  it("shows verified and not-traced counts with every tier in the tooltip", () => {
    const summary = {
      status: "warn",
      checked: 40,
      verified: 12,
      found_elsewhere: 20,
      derived: 3,
      company_reported: 1,
      registry_only: 1,
      not_traced: 3,
      unsupported: 2,
      coverage_pct: 90,
      thin_corpus: false,
      basis: "tiered",
    };
    const chip = factCheckChip(withReport(ANTHROPIC_COMPLETE, { memo_fact_check: summary }), t);
    expect(chip.label).toBe("12 of 40 verified · 3 not traced");
    expect(chip.flagged).toBe(true);
    expect(chip.title).toContain("Verified in sources on file: 12");
    expect(chip.title).toContain("Found elsewhere in sources on file: 20");
    expect(chip.title).toContain("Derived in a calculation: 3");
    expect(chip.title).toContain("Matches registry, not evidence: 1");
    expect(chip.title).toContain("Not traced: 3");
    expect(chip.title).not.toMatch(/traced to a source/);
    expect(factCheckTiers(summary, t).map((tier) => tier.key)).toEqual([
      "verified",
      "found_elsewhere",
      "derived",
      "company_reported",
      "registry_only",
      "not_traced",
    ]);
  });

  it("marks an older check's basis, and has nothing for non-memos or running ones", () => {
    const legacy = factCheckChip(
      withReport(ANTHROPIC_COMPLETE, {
        memo_fact_check: { status: "pass", checked: 10, verified: 4, found_elsewhere: 6, not_traced: 0, basis: "legacy" },
      }),
      t,
    );
    expect(legacy.label).toBe("4 of 10 verified");
    expect(legacy.title).toContain("An older check");
    expect(factCheckChip(withReport(PLACEHOLDER_FINANCIAL), t)).toBeNull();
    expect(factCheckChip(withReport(ANTHROPIC_COMPLETE, { status: "analyzing" }), t)).toBeNull();
  });
});

describe("review", () => {
  it("labels each state and names the approver", () => {
    expect(reviewChip(withReport(GOOGLE_PASS), t, "en")).toMatchObject({ state: "draft", label: "Draft" });
    expect(reviewChip(withReport(GOOGLE_PASS, { review_state: "in_review" }), t, "en").label).toBe("In review");
    const approved = reviewChip(
      withReport(GOOGLE_PASS, {
        review_state: "approved",
        reviewer_name: "Bilel Harrat",
        reviewed_at: "2026-09-22T10:00:00+00:00",
        review_note: "Numbers checked.",
      }),
      t,
      "en",
    );
    expect(approved.label).toBe("Approved by Bilel Harrat");
    expect(approved.tone).toBe("success");
    expect(approved.title).toContain("Numbers checked.");
    expect(reviewChip(withReport(GOOGLE_PASS, { review_state: "withdrawn" }), t, "en").label).toBe("Withdrawn");
    expect(reviewChip(withReport(PLACEHOLDER_FINANCIAL), t, "en")).toBeNull();
  });

  it("offers the moves a role may make", () => {
    const draft = withReport(GOOGLE_PASS);
    expect(reviewActions(draft, ALL)).toEqual(["in_review", "approved", "withdrawn"]);
    expect(reviewActions(draft, ["memo:edit"])).toEqual(["in_review"]);
    expect(reviewActions(draft, ["memo:export"])).toEqual([]);
    expect(reviewActions(draft, null)).toEqual([]);
    const approved = withReport(GOOGLE_PASS, { review_state: "approved" });
    expect(reviewActions(approved, ALL)).toEqual(["draft", "withdrawn"]);
    expect(reviewActions(approved, ["memo:edit"])).toEqual([]);
    const running = withReport(GOOGLE_PASS, { status: "analyzing" });
    expect(reviewActions(running, ALL)).toEqual(["withdrawn"]);
  });

  it("explains documents that could not be re-stamped", () => {
    expect(reviewRenderNote(withReport(GOOGLE_PASS, { review_render_status: "failed" }), t)).toContain(
      "could not be re-stamped",
    );
    expect(reviewRenderNote(withReport(GOOGLE_PASS, { review_render_status: "rendered" }), t)).toBe("");
  });
});

describe("versions, documents and warnings", () => {
  it("reads the version fields and says spans in hours or days", () => {
    expect(versionInfo(GOOGLE_PASS)).toMatchObject({
      grouped: true,
      isLatest: true,
      index: 2,
      count: 2,
      previousId: "37acb580ef1e",
      changedFrom: "Buy",
      unstable: true,
      flipDays: 0.76,
    });
    expect(versionInfo(PLACEHOLDER_FINANCIAL).grouped).toBe(false);
    expect(spanLabel(0.76, t)).toBe("18 hours");
    expect(spanLabel(0.02, t)).toBe("1 hour");
    expect(spanLabel(3.4, t)).toBe("3 days");
    expect(spanLabel(null, t)).toBe("");
  });

  it("says a finished record without a document has none", () => {
    expect(reportCanOpen(PLACEHOLDER_FINANCIAL)).toBe(false);
    expect(reportIsDocless(PLACEHOLDER_FINANCIAL)).toBe(true);
    expect(reportIsDocless(GOOGLE_PASS)).toBe(false);
    expect(reportCanOpen(withReport(GOOGLE_PASS, { has_document: false }))).toBe(false);
  });

  it("labels the IC memo and its languages", () => {
    expect(sourceLabel("internal", ["en", "zh", "internal"], t)).toBe("IC memo");
    expect(sourceLabel("INTERNAL", ["EN", "ZH", "INTERNAL", "INTERNAL_ZH"], t)).toBe("IC memo · EN");
    expect(sourceLabel("internal_zh", ["internal", "internal_zh"], t)).toBe("IC memo · 中文");
    expect(sourceLabel("zh", ["en", "zh"], t)).toBe("ZH");
    expect(sourceLanguage("INTERNAL")).toBe("en");
    expect(sourceLanguage("internal_zh")).toBe("zh");
    setAppLanguage("zh");
    expect(sourceLabel("internal", ["internal"], t)).toBe("投委会备忘录");
    setAppLanguage("en");
  });

  it("reads the Chinese warnings in the Chinese UI", () => {
    const report = withReport(ZAINAR_WARNINGS, {
      memo_chinese_parity: null,
      quality_warnings_zh: ["中文备忘录一致性检查发现 1 个 P0 问题。详见 logs/memo_chinese_parity.md。"],
    });
    const zh = reportWarnings(report, t, "zh");
    expect(zh[0].summary).toBe("中文备忘录一致性检查发现 1 个 P0 问题。");
    expect(zh[0].gate).toBe("chinese_parity");
    expect(reportWarnings(report, t, "en")[0].summary).toBe("Chinese memo parity gate found 1 P0 finding.");
  });
});

describe("a run paused after its English memo", () => {
  afterEach(() => setAppLanguage("en"));

  it("is its own state: not running, not complete, filed under Attention", () => {
    const paused = pausedReport();
    expect(reportState(paused)).toBe("paused");
    expect(reportIsPaused(paused)).toBe(true);
    expect(reportListStatus(paused)).toBe("needs_attention");
    expect(reportCanOpen(paused)).toBe(true);
    expect(reportIsDocless(paused)).toBe(false);
    expect(reportStatusLabel(paused, t)).toBe("English ready — paused");
    setAppLanguage("zh");
    expect(reportStatusLabel(paused, t)).toBe("英文版已就绪——已暂停");
    // The statuses around it keep their buckets.
    expect(reportState(withReport(paused, { status: "resuming" }))).toBe("running");
    expect(reportState(withReport(paused, { status: "complete_with_warnings" }))).toBe("warnings");
  });

  it("carries the English gates' warnings, with the new gates named", () => {
    const items = reportWarnings(pausedReport(), t, "en");
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ gate: "length", gateLabel: "Length over target", language: "EN", code: "section_over_cap" });
    expect(items[0].summary).toBe("Risks runs 5,319 words against a 5,200-word cap.");
    expect(reportWarnings(pausedReport(), t, "zh")[0].summary).toBe("风险章节 5,319 词，超出 5,200 词上限。");
  });
});

describe("warning gate labels", () => {
  afterEach(() => setAppLanguage("en"));

  it("names every gate memo_analysis writes, in both languages", () => {
    const en = {
      quality: "Quality review",
      chinese_parity: "Chinese parity",
      fact_check: "Fact check",
      chinese_package: "Chinese package",
      ic_memo: "IC memo",
      private_diligence: "Private diligence",
      boundary: "Sandbox boundary",
      returns: "Returns math",
      signposts: "Signposts",
      risk_cards: "Risk cards",
      length: "Length over target",
      claims: "Unverified quotes",
      consistency: "Conflicting figures",
      red_team: "Open challenges",
      cost: "Spend ceiling reached",
    };
    for (const [gate, label] of Object.entries(en)) expect(gateLabel(gate, t)).toBe(label);
    // An unknown gate still reads as words, never as a key.
    expect(gateLabel("some_new_gate", t)).toBe("Some new gate");

    setAppLanguage("zh");
    expect(gateLabel("length", t)).toBe("篇幅超出目标");
    expect(gateLabel("claims", t)).toBe("引文未核实");
    expect(gateLabel("consistency", t)).toBe("数字前后不一致");
    expect(gateLabel("red_team", t)).toBe("未回应的质疑");
    expect(gateLabel("cost", t)).toBe("已达支出上限");
  });

  it("labels the new gates on a delivered memo's warning items", () => {
    const report = withReport(ZAINAR_WARNINGS, {
      quality_warning_items: [
        { gate: "cost", language: "en", section: "", severity: "", code: "cost_ceiling", summary_en: "Stopped before the Chinese: $61.20 of a $60 ceiling.", summary_zh: "" },
        { gate: "consistency", language: "en", section: "key_metrics", severity: "P1", code: "metric_conflict", summary_en: "ARR reads $24M and $18M.", summary_zh: "" },
      ],
    });
    const labels = reportWarnings(report, t, "en").map((item) => item.gateLabel);
    expect(labels).toEqual(["Spend ceiling reached", "Conflicting figures"]);
  });
});

describe("quality metrics", () => {
  afterEach(() => setAppLanguage("en"));

  it("reads memo_quality_metrics into one compact line with a hint per figure", () => {
    const line = qualityMetricsLine(pausedReport(), t);
    expect(line.map((item) => item.label)).toEqual(["72% traced", "1 over cap", "0 conflicting", "4% repeated"]);
    expect(line[0].title).toBe("The share of the memo's figures traced to a source on file or on the web.");
    expect(line[1].title).toBe("Sections that run past their word cap.");
    expect(line[2].title).toBe("Metrics given different values in different places of the memo.");
    expect(line[3].title).toBe("The share of sentences that repeat another sentence of the memo.");

    setAppLanguage("zh");
    expect(qualityMetricsLine(pausedReport(), t).map((item) => item.label)).toEqual([
      "72% 可溯源",
      "1 节超篇幅",
      "0 处数字冲突",
      "4% 重复",
    ]);
  });

  it("takes counts the server already took, a percentage repetition index, and nothing without metrics", () => {
    const report = pausedReport({
      quality_metrics: {
        traced_pct: 51.6,
        over_cap_sections: 2,
        metric_conflicts: [{ metric: "ARR", values: ["$24M", "$18M"] }, { metric: "runway" }],
        repetition_index: 12,
      },
    });
    expect(qualityMetricsLine(report, t).map((item) => item.label)).toEqual(["52% traced", "2 over cap", "2 conflicting", "12% repeated"]);
    expect(qualityMetricsLine(pausedReport({ quality_metrics: null }), t)).toBeNull();
    expect(qualityMetricsLine(ANTHROPIC_COMPLETE, t)).toBeNull();
    expect(qualityMetricsLine(pausedReport({ quality_metrics: {} }), t)).toBeNull();
  });
});

describe("with a pinned clock", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-22T12:00:00"));
  });
  afterEach(() => vi.useRealTimers());

  it("defaults to now", () => {
    expect(reportFreshness(withReport(KO_BUFFETT, { reader: { memo_as_of: "2026-08-25" } }), t, "en").text).toBe(
      "Written Aug 25 · 28 days ago",
    );
  });
});
