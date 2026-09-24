import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const mockApi = vi.hoisted(() => ({ getReportDiff: vi.fn() }));

vi.mock("../src/api.js", () => ({
  api: mockApi,
  default: mockApi,
  withApiToken: (path) => path,
}));

import ReportChangesPanel from "../src/components/reports/ReportChangesPanel.vue";
import { setAppLanguage } from "../src/state.js";
import { withReport } from "./fixtures/reportSummaries.js";
import {
  CIENET_DIFF,
  CIENET_LATE_NEW,
  CIENET_LATE_OLD,
  GOOGLE_BUY,
  GOOGLE_DIFF,
  GOOGLE_PASS,
} from "./fixtures/reportReader.js";

let wrapper;

function mountPanel(report, previous, lang = "en") {
  wrapper = mount(ReportChangesPanel, {
    props: { report: withReport(report), previous: withReport(previous), lang },
  });
  return wrapper;
}

describe("ReportChangesPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    setAppLanguage("en");
  });

  it("shows the Buffett call flipping from Buy to Pass, and calls it unstable", async () => {
    mockApi.getReportDiff.mockResolvedValue(JSON.parse(JSON.stringify(GOOGLE_DIFF)));
    mountPanel(GOOGLE_PASS, GOOGLE_BUY);
    await flushPromises();
    expect(mockApi.getReportDiff).toHaveBeenCalledWith(GOOGLE_PASS.id, GOOGLE_BUY.id);

    expect(wrapper.text()).toContain("18 hours apart");
    const verdict = wrapper.get('[data-testid="changes-verdict"]');
    expect(verdict.text()).toContain("Buy");
    expect(verdict.text()).toContain("Pass");
    expect(verdict.get('[data-testid="changes-unstable"]').text()).toBe(
      "The call flipped 18 hours after the previous memo.",
    );
    const headlines = wrapper.get('[data-testid="changes-headlines"]');
    expect(headlines.text()).toContain("I would own this business at today's quote");
    expect(headlines.text()).toContain("I think the core business is one of the finest");
    const buffett = wrapper.get('[data-testid="changes-buffett"]');
    expect(buffett.text()).toContain("Buy price");
    expect(buffett.text()).toContain("Up to about $360 per Alphabet share");
    expect(buffett.text()).toContain("$215 per share or less");
  });

  it("lays late-stage rows side by side and never says added or removed", async () => {
    mockApi.getReportDiff.mockResolvedValue(JSON.parse(JSON.stringify(CIENET_DIFF)));
    mountPanel(CIENET_LATE_NEW, CIENET_LATE_OLD);
    await flushPromises();

    // Neither memo recorded a call: no call section rather than a guess.
    expect(wrapper.find('[data-testid="changes-verdict"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="changes-headlines"]').text()).toContain("We do not recommend participating.");

    const scenarios = wrapper.get('[data-testid="changes-table-scenario_analysis"]');
    expect(scenarios.text()).toContain("Scenarios");
    expect(scenarios.text()).toContain("Bear");
    const matches = wrapper.findAll('[data-testid="changes-match"]').map((m) => m.text());
    expect(matches).toContain("Same scenario");
    expect(matches).toContain("Similar label");
    expect(matches).toContain("No counterpart");

    // A fuzzy risk pair names the earlier label it was paired with.
    const risks = wrapper.get('[data-testid="changes-table-risk_register"]');
    expect(risks.text()).toContain("Structure");
    expect(risks.text()).toContain("Earlier: Deal Structure");

    const sources = wrapper.get('[data-testid="changes-sources"]');
    expect(sources.text()).toContain("1 of this memo's 12 sources have a counterpart among the earlier memo's 9.");
    await sources.get('[data-testid="changes-sources-toggle"]').trigger("click");
    expect(sources.text()).toContain("In this memo, no counterpart earlier");

    expect(wrapper.get('[data-testid="changes-note"]').text()).toBe(
      "Some rows were paired by similar labels; they are shown side by side, not as additions or removals.",
    );
    expect(wrapper.text().toLowerCase()).not.toMatch(/\badded\b|\bremoved\b/);
  });

  it("folds identical rows and reads the Chinese cells in Chinese", async () => {
    const diff = JSON.parse(JSON.stringify(CIENET_DIFF));
    diff.tables[2].rows[0].changed = false;
    mockApi.getReportDiff.mockResolvedValue(diff);
    setAppLanguage("zh");
    mountPanel(CIENET_LATE_NEW, CIENET_LATE_OLD, "zh");
    await flushPromises();
    const metrics = wrapper.get('[data-testid="changes-table-key_metrics_snapshot"]');
    expect(metrics.text()).toContain("关键指标");
    const fold = metrics.get('[data-testid="changes-unchanged-key_metrics_snapshot"]');
    expect(fold.text()).toBe("1 行未变");
    await fold.trigger("click");
    // The identical row shows under this memo's label.
    expect(metrics.text()).toContain("所有权");
    expect(wrapper.get('[data-testid="changes-note"]').text()).toBe(
      "部分行按相近的标签配对，仅并列展示，不代表新增或删除。",
    );
  });

  it("says so when the comparison cannot be loaded", async () => {
    mockApi.getReportDiff.mockRejectedValue(new Error("404"));
    mountPanel(GOOGLE_PASS, GOOGLE_BUY);
    await flushPromises();
    expect(wrapper.text()).toContain("The comparison could not be loaded.");
  });
});
