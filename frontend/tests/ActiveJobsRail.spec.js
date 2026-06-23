import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const apiMock = vi.hoisted(() => ({
  listActiveJobs: vi.fn(),
  apiFetch: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    listActiveJobs: apiMock.listActiveJobs,
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
        threads: [
          {
            name: "Pressure tests",
            status: "done",
            event_count: 3,
            elapsed_ms: 4000,
            latest_action: {
              action: "tool_use",
              tool: "Write",
              preview: "analysis/pressure_tests.md",
            },
          },
          {
            name: "Validation log",
            status: "running",
            event_count: 1,
            elapsed_ms: 65000,
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
    expect(wrapper.text()).not.toContain("Pressure tests");

    const toggle = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Parallel flows"));
    expect(toggle).toBeTruthy();
    await toggle.trigger("click");

    expect(wrapper.text()).toContain("Pressure tests");
    expect(wrapper.text()).toContain("3 events");
    expect(wrapper.text()).toContain("4s");
    expect(wrapper.text()).toContain("Validation log");
    expect(wrapper.text()).toContain("1 event");
    expect(wrapper.text()).toContain("1m 5s");
  });
});
