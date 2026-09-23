import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const apiMock = vi.hoisted(() => ({
  listActiveJobs: vi.fn(),
  cancelReportRun: vi.fn(),
  apiFetch: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    listActiveJobs: apiMock.listActiveJobs,
    cancelReportRun: apiMock.cancelReportRun,
  },
  apiFetch: apiMock.apiFetch,
  withApiToken: (url) => url,
}));

import ActiveJobsRail from "../src/components/ActiveJobsRail.vue";

describe("ActiveJobsRail", () => {
  let wrapper;

  afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
  });

  it("expands parallel flow rows with event counts and elapsed time", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      {
        kind: "memo",
        report_id: "memo-1",
        title: "Investment memo — ZaiNar, Inc.",
        subtitle: "Late-stage / pre-IPO",
        latest_stage: "Running investment-memo skill",
        thread_count: 2,
        thread_done_count: 1,
        thread_failed_count: 0,
        open_thread_count: 1,
        elapsed_ms: 65000,
        threads: [
          {
            name: "Phase 1 - Intake and setup",
            status: "done",
            event_count: 3,
            elapsed_ms: 4000,
            estimate_ms: 150000,
            latest_action: {
              action: "tool_use",
              tool: "Read",
              preview: "data/settings/serena_background.md",
            },
          },
          {
            name: "Phase 2 - Parallel analysis passes",
            status: "not_started",
            event_count: 0,
          },
        ],
      },
    ]);

    wrapper = mount(ActiveJobsRail, {
      global: {
        stubs: { Teleport: true },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Parallel flows");
    expect(wrapper.text()).toContain("1/2 subtasks");
    expect(wrapper.text()).toContain("elapsed 1m 5s");
    expect(wrapper.text()).toContain("Phase 1 - Intake and setup");
    expect(wrapper.text()).toContain("3 events");
    expect(wrapper.text()).toContain("4s");
    expect(wrapper.text()).toContain("expected ~2m 30s");
    expect(wrapper.text()).toContain("actual 4s");
    expect(wrapper.text()).toContain("Phase 2 - Parallel analysis passes");
    expect(wrapper.text()).toContain("not started");

    const toggle = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Parallel flows"));
    expect(toggle).toBeTruthy();
    await toggle.trigger("click");
    expect(wrapper.text()).not.toContain("Phase 1 - Intake and setup");
  });

  it("cancels a memo run after a two-step confirmation", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      {
        kind: "memo",
        report_id: "memo-1",
        title: "Investment memo — ZaiNar, Inc.",
        latest_stage: "Running investment-memo skill",
      },
    ]);
    apiMock.cancelReportRun.mockResolvedValue({ status: "failed_during_analysis" });

    wrapper = mount(ActiveJobsRail, {
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    const cancel = wrapper
      .findAll("button")
      .find((button) => button.text() === "Cancel run");
    expect(cancel).toBeTruthy();

    // First click only arms the confirmation — nothing is cancelled yet.
    await cancel.trigger("click");
    expect(apiMock.cancelReportRun).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Click again to confirm");

    await cancel.trigger("click");
    await flushPromises();
    expect(apiMock.cancelReportRun).toHaveBeenCalledWith("memo-1");
  });

  it("shows Done + finalizing artifacts instead of cancel once the report is ready", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      {
        kind: "memo",
        report_id: "memo-1",
        title: "Investment memo — ZaiNar, Inc.",
        latest_stage: "Finalizing private analysis artifacts",
        report_ready: true,
      },
    ]);

    wrapper = mount(ActiveJobsRail, {
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Done");
    expect(wrapper.text()).toContain(
      "Finalizing artifacts — the report is ready to view.",
    );
    // The raw stage line is replaced by the finalizing banner…
    expect(wrapper.text()).not.toContain("Finalizing private analysis artifacts");
    // …and a delivered report can no longer be cancelled from the rail.
    const cancel = wrapper
      .findAll("button")
      .find((button) => button.text() === "Cancel run");
    expect(cancel).toBeUndefined();
  });

  it("shifts left of the copilot panel when copilot is open", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      {
        kind: "memo",
        report_id: "memo-1",
        title: "Investment memo — ZaiNar, Inc.",
        latest_stage: "Running investment-memo skill",
      },
    ]);

    wrapper = mount(ActiveJobsRail, {
      props: { copilotOpen: true },
      global: {
        stubs: { Teleport: true },
      },
    });
    await flushPromises();

    const rail = wrapper.find("aside");
    // Beside whatever width Warren was dragged to (--copilot-w).
    expect(rail.classes()).toContain("rail-beside-copilot");
    expect(rail.classes()).toContain("max-xl:hidden");
  });
});
