import { describe, expect, it } from "vitest";

import { normalizeWork, parseStructuredOutputs } from "../src/copilotActions.js";

describe("work Warren offers to start", () => {
  it("fills a report proposal in with what the server accepts", () => {
    const work = normalizeWork({
      kind: "report",
      title: "IC packet for Acme",
      why: "The files are staged and you asked for Thursday.",
      report_type: "Investment Memo (Late-Stage)",
      audience: "Partner",
      quality: "balanced",
    });

    expect(work.kind).toBe("report");
    expect(work.options).toEqual({
      report_type: "Investment Memo (Late-Stage)",
      audience: "Partner",
      language: "en",
      report_mode: "full",
      quality: "balanced",
      engine: "",
    });
  });

  it("falls back rather than offering something the server would refuse", () => {
    const work = normalizeWork({
      kind: "report",
      report_type: "Market Analysis", // retired: no pipeline behind it
      audience: "Board",
      quality: "turbo",
    });

    expect(work.options.report_type).toBe("Investment Report (Auto)");
    expect(work.options.audience).toBe("Partner");
    expect(work.options.quality).toBe("best");
  });

  it("drops a proposal that cannot be acted on", () => {
    expect(normalizeWork(null)).toBeNull();
    expect(normalizeWork({ kind: "delete_everything" })).toBeNull();
    // An analysis with no file; a decision without a verdict the log
    // accepts, or without a reason.
    expect(normalizeWork({ kind: "document_analysis" })).toBeNull();
    expect(normalizeWork({ kind: "decision", explanation: "because" })).toBeNull();
    expect(normalizeWork({ kind: "decision", verdict: "maybe", explanation: "x" })).toBeNull();
    expect(normalizeWork({ kind: "decision", verdict: "pass" })).toBeNull();
  });

  it("carries a document analysis and a decision through", () => {
    expect(normalizeWork({
      kind: "document_analysis",
      file_id: "f-1",
      file_name: "term-sheet.pdf",
    })).toMatchObject({
      kind: "document_analysis",
      title: "term-sheet.pdf",
      options: { file_id: "f-1", file_name: "term-sheet.pdf" },
    });

    // The body the decision log takes (server/api.py DecisionCreate).
    expect(normalizeWork({
      kind: "decision",
      title: "Pass for now",
      verdict: "Pass",
      explanation: "Valuation is ahead of the traction.",
    })).toMatchObject({
      kind: "decision",
      options: { verdict: "pass", explanation: "Valuation is ahead of the traction." },
    });
  });

  it("reads the block out of an answer", () => {
    const answer = [
      "I can put the IC packet together.",
      "```json",
      '{"run_work": {"kind": "report", "report_type": "Buffett Investment Memo"}}',
      "```",
    ].join("\n");

    expect(parseStructuredOutputs(answer).run_work).toEqual({
      kind: "report",
      report_type: "Buffett Investment Memo",
    });
  });
});
