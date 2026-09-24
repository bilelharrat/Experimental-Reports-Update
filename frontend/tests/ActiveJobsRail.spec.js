import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const apiMock = vi.hoisted(() => ({
  listActiveJobs: vi.fn(),
  cancelReportRun: vi.fn(),
  getReport: vi.fn(),
  apiFetch: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: {
    listActiveJobs: apiMock.listActiveJobs,
    cancelReportRun: apiMock.cancelReportRun,
    getReport: apiMock.getReport,
  },
  apiFetch: apiMock.apiFetch,
  withApiToken: (url) => url,
}));

import ActiveJobsRail from "../src/components/ActiveJobsRail.vue";
import { activeJobs } from "../src/activeJobs.js";
import { requestJobLog } from "../src/reportStatus.js";
import { KO_BUFFETT, FAILED_DISMISSED, withReport } from "./fixtures/reportSummaries.js";

// The rail's rows link into /reports, so it mounts with a router.
function withRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: { template: "<div />" } },
      { path: "/reports", name: "reports", component: { template: "<div />" } },
    ],
  });
  return router;
}

describe("ActiveJobsRail", () => {
  let wrapper;

  afterEach(() => {
    wrapper?.unmount();
    vi.restoreAllMocks();
    // The poll's result is shared app state; start each test from none.
    activeJobs.value = [];
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
        plugins: [withRouter()],
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
      global: { plugins: [withRouter()], stubs: { Teleport: true } },
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
      global: { plugins: [withRouter()], stubs: { Teleport: true } },
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
        plugins: [withRouter()],
        stubs: { Teleport: true },
      },
    });
    await flushPromises();

    const rail = wrapper.find("aside");
    // Beside whatever width Warren was dragged to (--copilot-w).
    expect(rail.classes()).toContain("rail-beside-copilot");
    expect(rail.classes()).toContain("max-xl:hidden");
  });
  it("links a delivered report from its row while artifacts finish", async () => {
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
      global: { plugins: [withRouter()], stubs: { Teleport: true } },
    });
    await flushPromises();
    const links = wrapper.get('[data-testid="rail-report-ready-links"]').findAll("a");
    expect(links.map((a) => a.text())).toEqual(["Read EN", "阅读中文"]);
    expect(links[1].attributes("href")).toBe("/reports?id=memo-1&lang=zh");
  });

  it("keeps a finished memo as a Ready row until it is opened", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      { kind: "memo", report_id: KO_BUFFETT.id, title: "Buffett memo — Coca Cola Co" },
    ]);
    apiMock.getReport.mockResolvedValue(withReport(KO_BUFFETT));
    const router = withRouter();
    wrapper = mount(ActiveJobsRail, {
      global: { plugins: [router], stubs: { Teleport: true } },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="rail-ready-row"]').exists()).toBe(false);

    // The run leaves the poll: the rail says it is ready instead of vanishing.
    apiMock.listActiveJobs.mockResolvedValue([]);
    activeJobs.value = [];
    await flushPromises();
    expect(apiMock.getReport).toHaveBeenCalledWith(KO_BUFFETT.id);
    const row = wrapper.get('[data-testid="rail-ready-row"]');
    expect(row.text()).toContain("Buffett memo — Coca Cola Co");
    expect(row.text()).toContain("Ready");
    const en = row.get('[data-testid="rail-ready-read-en"]');
    expect(en.attributes("href")).toBe(`/reports?id=${KO_BUFFETT.id}&lang=en`);
    expect(row.get('[data-testid="rail-ready-read-zh"]').text()).toBe("阅读中文");

    await en.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.fullPath).toBe(`/reports?id=${KO_BUFFETT.id}&lang=en`);
    expect(wrapper.find('[data-testid="rail-ready-row"]').exists()).toBe(false);
  });

  it("does not announce a run that failed", async () => {
    apiMock.listActiveJobs.mockResolvedValue([
      { kind: "memo", report_id: FAILED_DISMISSED.id, title: "Investment memo" },
    ]);
    apiMock.getReport.mockResolvedValue(withReport(FAILED_DISMISSED));
    wrapper = mount(ActiveJobsRail, {
      global: { plugins: [withRouter()], stubs: { Teleport: true } },
    });
    await flushPromises();
    apiMock.listActiveJobs.mockResolvedValue([]);
    activeJobs.value = [];
    await flushPromises();
    expect(wrapper.find('[data-testid="rail-ready-row"]').exists()).toBe(false);
  });

  it("opens its transcript modal when a report viewer asks for a job's log", async () => {
    apiMock.listActiveJobs.mockResolvedValue([]);
    wrapper = mount(ActiveJobsRail, {
      global: {
        plugins: [withRouter()],
        stubs: {
          Teleport: true,
          JobLogModal: { props: ["job"], template: '<div data-testid="job-log">{{ job.report_id }}</div>' },
        },
      },
    });
    await flushPromises();
    requestJobLog({ kind: "memo", report_id: "memo-9", log_url: "/api/jobs/log?path=memo:memo-9" });
    await flushPromises();
    expect(wrapper.get('[data-testid="job-log"]').text()).toBe("memo-9");
  });
});
