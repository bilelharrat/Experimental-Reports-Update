import { describe, expect, it, vi } from "vitest";
import {
  TARGET_KINDS,
  activateCopilotTarget,
  buildDragTellPrompt,
  buildSelection,
} from "../src/copilotTargets.js";

describe("copilotTargets", () => {
  it("builds provenance-first prompts by target kind", () => {
    const prompt = buildDragTellPrompt(
      buildSelection(TARGET_KINDS.METRIC, {
        metric_label: "ARR",
        metric_value: "$12M",
      }),
    );
    expect(prompt).toContain("ARR");
    expect(prompt).toContain("$12M");
    expect(prompt.toLowerCase()).toContain("trace");
  });

  it("activates copilot with drag-tell context", () => {
    const openCopilot = vi.fn();
    activateCopilotTarget(openCopilot, {
      companyId: "zainar-inc",
      surface: "overview",
      tab: "overview",
      selection: buildSelection(TARGET_KINDS.METRIC, {
        metric_label: "ARR",
        metric_value: "$12M",
      }),
    });
    expect(openCopilot).toHaveBeenCalledWith(
      expect.objectContaining({
        companyId: "zainar-inc",
        dragTell: true,
        mode: "quick",
        context: expect.objectContaining({
          surface: "overview",
          selection: expect.objectContaining({ target_kind: TARGET_KINDS.METRIC }),
        }),
      }),
    );
  });
});
