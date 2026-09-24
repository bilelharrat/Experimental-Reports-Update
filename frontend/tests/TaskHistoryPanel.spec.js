import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const apiMock = vi.hoisted(() => ({
  listJobHistory: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: { listJobHistory: apiMock.listJobHistory },
  apiFetch: vi.fn(),
  withApiToken: (url) => url,
}));

import TaskHistoryPanel from "../src/components/TaskHistoryPanel.vue";

describe("TaskHistoryPanel", () => {
  let wrapper;

  afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
  });

  it("lists finished tasks with both memo timings and opens the transcript", async () => {
    apiMock.listJobHistory.mockResolvedValue([
      {
        id: "a1",
        kind: "memo",
        title: "Investment memo — Mill",
        subtitle: "Stage-calibrated (auto)",
        terminal_type: "done",
        status: "complete",
        started_at: "2026-09-10T00:16:00+00:00",
        report_ready_at: "2026-09-10T00:32:00+00:00",
        run_finished_at: "2026-09-10T00:36:00+00:00",
        finished_at: "2026-09-10T00:36:00+00:00",
        claude_cost_usd: 12.5,
        log_url: "/api/jobs/log?path=memo:r1",
        primary_route: { name: "reports", query: { id: "r1" } },
      },
      {
        id: "b2",
        kind: "weekly_stocks",
        title: "Weekly stock summary",
        terminal_type: "error",
        error: "claude exited 1",
        started_at: "2026-09-09T10:00:00+00:00",
        finished_at: "2026-09-09T10:05:00+00:00",
        log_url: "/api/jobs/log?path=history:b2",
      },
    ]);

    wrapper = mount(TaskHistoryPanel, {
      global: { stubs: { Teleport: true, JobLogModal: true } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Task history");
    expect(wrapper.text()).toContain("Investment memo — Mill");
    // Both timings: report ready at 16m, whole run at 20m.
    expect(wrapper.text()).toContain("report 16m 0s · total 20m 0s");
    expect(wrapper.text()).toContain("$12.50");
    expect(wrapper.text()).toContain("Done");
    expect(wrapper.text()).toContain("Failed");
    expect(wrapper.text()).toContain("claude exited 1");

    expect(wrapper.find("job-log-modal-stub").exists()).toBe(false);
    await wrapper
      .findAll("li button")
      .at(0)
      .trigger("click");
    expect(wrapper.find("job-log-modal-stub").exists()).toBe(true);
  });

  it("shows the empty state when nothing has finished", async () => {
    apiMock.listJobHistory.mockResolvedValue([]);
    wrapper = mount(TaskHistoryPanel, {
      global: { stubs: { Teleport: true, JobLogModal: true } },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("No finished tasks yet.");
  });
});
