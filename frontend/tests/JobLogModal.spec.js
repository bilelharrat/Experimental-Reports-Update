import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const apiMock = vi.hoisted(() => ({
  apiFetch: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  apiFetch: apiMock.apiFetch,
  withApiToken: (url) => url,
}));

import JobLogModal from "../src/components/JobLogModal.vue";

class FakeEventSource {
  constructor(url) {
    this.url = url;
  }

  close() {}
}

function mountModal(events) {
  apiMock.apiFetch.mockResolvedValue({
    ok: true,
    json: async () => events,
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }],
  });
  return mount(JobLogModal, {
    props: {
      job: {
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
        subtitle: "Late-stage / pre-IPO",
        log_url: "/api/jobs/log/zainar",
        stream_url: "/api/jobs/stream/zainar",
      },
    },
    global: {
      plugins: [router],
      stubs: {
        Teleport: true,
      },
    },
  });
}

describe("JobLogModal", () => {
  let originalEventSource;
  let wrapper;

  beforeEach(() => {
    apiMock.apiFetch.mockReset();
    originalEventSource = global.EventSource;
    global.EventSource = FakeEventSource;
  });

  afterEach(() => {
    wrapper?.unmount();
    global.EventSource = originalEventSource;
  });

  it("settles memo subtask rows after a successful in-thread tool result", async () => {
    wrapper = mountModal([
      {
        type: "job_init",
        ts: "2026-06-22T00:00:00.000Z",
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
      },
      {
        type: "stage",
        ts: "2026-06-22T00:00:01.000Z",
        stage: "analysis_starting",
        message: "Running investment-memo skill (analysis + translation)",
      },
      {
        type: "thread_started",
        ts: "2026-06-22T00:00:02.000Z",
        thread: "Arithmetic / pressure tests",
        title: "Arithmetic / pressure tests",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:03.000Z",
        action: "tool_use",
        tool: "Write",
        thread: "Arithmetic / pressure tests",
        preview: "analysis/arithmetic_pressure_tests.md",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:04.000Z",
        action: "tool_result",
        tool: "Write",
        thread: "Arithmetic / pressure tests",
        is_error: false,
        preview: "File created successfully.",
      },
    ]);

    await flushPromises();

    const row = wrapper
      .findAll("section")
      .find((section) => section.text().includes("Arithmetic / pressure tests"));

    expect(row).toBeTruthy();
    expect(row.find("svg").classes()).toContain("text-success-ink");
    expect(row.find("svg").classes()).not.toContain("animate-spin");
  });

  it("shows renderer contract failure details in the event log", async () => {
    wrapper = mountModal([
      {
        type: "job_init",
        ts: "2026-06-22T00:00:00.000Z",
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
      },
      {
        type: "stage",
        ts: "2026-06-22T00:00:01.000Z",
        stage: "rendering_docx",
        message: "Rendering memo DOCX from structured package",
      },
      {
        type: "error",
        ts: "2026-06-22T00:00:02.000Z",
        error: "Renderer contract failed: memo_package missing",
        phase: "renderer_contract",
        contract_errors: ["memo_package missing"],
        expected_files: [
          {
            label: "memo_package",
            path: "data/memos/zainar/logs/memo_package.json",
            exists: false,
          },
        ],
      },
    ]);

    await flushPromises();

    expect(wrapper.text()).toContain(
      "Renderer contract failed: memo_package missing",
    );
    expect(wrapper.text()).toContain("check: memo_package missing");
    expect(wrapper.text()).toContain("memo_package: missing");
    expect(wrapper.text()).toContain("data/memos/zainar/logs/memo_package.json");
  });
});
