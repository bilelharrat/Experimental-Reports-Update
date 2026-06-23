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

  it("shows generated output pieces with started time and phase", async () => {
    wrapper = mountModal([
      {
        type: "job_init",
        ts: "2026-06-22T00:00:00.000Z",
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
      },
      {
        type: "thread_started",
        ts: "2026-06-22T00:00:01.000Z",
        thread: "Claim register",
        title: "Claim register",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:02.000Z",
        action: "tool_use",
        tool: "Write",
        thread: "Claim register",
        preview: "analysis/claim_register.md  (42 chars)",
      },
      {
        type: "output_piece",
        ts: "2026-06-22T00:00:02.500Z",
        started_at: "2026-06-22T00:00:02.000Z",
        thread: "Claim register",
        phase: "Phase 3 - Synthesis and decision questions",
        filename: "claim_register.md",
        path: "analysis/claim_register.md",
        content: "# Claim Register\n\n- Claim A: source-backed.",
        content_chars: 42,
        truncated: false,
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:03.000Z",
        action: "tool_result",
        tool: "Write",
        thread: "Claim register",
        is_error: false,
        preview: "File created successfully.",
      },
      {
        type: "thread_finished",
        ts: "2026-06-22T00:00:04.000Z",
        thread: "Claim register",
      },
    ]);

    await flushPromises();

    const toggle = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Claim register"));
    expect(toggle).toBeTruthy();
    await toggle.trigger("click");

    expect(wrapper.text()).toContain("Output");
    expect(wrapper.text()).toContain("Started 2026-06-22");
    expect(wrapper.text()).toContain(
      "Phase: Phase 3 - Synthesis and decision questions",
    );
    expect(wrapper.text()).toContain("claim_register.md");
    expect(wrapper.text()).toContain("Claim A: source-backed.");
  });

  it("shows only friendly reset time for provider usage windows", async () => {
    wrapper = mountModal([
      {
        type: "job_init",
        ts: "2026-06-22T00:00:00.000Z",
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:01.000Z",
        action: "rate_limit",
        thread: "Phase 4 - Memo package and bilingual final memo",
        rate_limit_status: "allowed",
        rate_limit_type: "five_hour",
        overage_status: "rejected",
        overage_disabled_reason: "org_level_disabled",
        is_using_overage: false,
        resets_at: 1782211800,
      },
    ]);

    await flushPromises();
    const toggle = wrapper
      .findAll("button")
      .find((button) =>
        button.text().includes("Phase 4 - Memo package and bilingual final memo"),
      );
    expect(toggle).toBeTruthy();
    await toggle.trigger("click");

    const text = wrapper.text();
    expect(text).toContain("Usage window resets");
    expect(text).toContain("2026");
    expect(text).not.toContain("five_hour");
    expect(text).not.toContain("rejected");
    expect(text).not.toContain("org_level_disabled");
    expect(text).not.toContain("1782211800");
  });

  it("shows planned memo phases as expandable not-started rows", async () => {
    wrapper = mountModal([
      {
        type: "job_init",
        ts: "2026-06-22T00:00:00.000Z",
        kind: "memo",
        title: "Investment memo — ZaiNar, Inc.",
      },
      {
        type: "thread_planned",
        ts: "2026-06-22T00:00:01.000Z",
        thread: "Phase 1 - Intake and setup",
        title: "Phase 1 - Intake and setup",
        phase_index: 1,
        estimate_ms: 150000,
        description: "Setup usually takes about 2m 30s.",
      },
      {
        type: "thread_planned",
        ts: "2026-06-22T00:00:02.000Z",
        thread: "Phase 3 - Synthesis and decision questions",
        title: "Phase 3 - Synthesis and decision questions",
        phase_index: 3,
      },
      {
        type: "thread_planned",
        ts: "2026-06-22T00:00:02.500Z",
        thread: "Phase 2 - Parallel analysis passes",
        title: "Phase 2 - Parallel analysis passes",
        phase_index: 2,
      },
      {
        type: "thread_started",
        ts: "2026-06-22T00:00:03.000Z",
        thread: "Phase 1 - Intake and setup",
        title: "Phase 1 - Intake and setup",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:04.000Z",
        action: "tool_use",
        tool: "Read",
        thread: "Phase 1 - Intake and setup",
        preview: "data/settings/serena_background.md",
      },
      {
        type: "claude_action",
        ts: "2026-06-22T00:00:05.000Z",
        action: "tool_result",
        tool: "Read",
        thread: "Phase 1 - Intake and setup",
        is_error: false,
        preview: "ok",
      },
    ]);

    await flushPromises();

    expect(wrapper.text()).toContain("Phase 1 - Intake and setup");
    expect(wrapper.text()).toContain("expected ~2m 30s");
    expect(wrapper.text()).toContain("Phase 2 - Parallel analysis passes");
    expect(wrapper.text()).toContain("Phase 3 - Synthesis and decision questions");
    expect(wrapper.text()).toContain("not started");
    expect(wrapper.text()).not.toContain("Complete");
    expect(wrapper.text().indexOf("Phase 2 - Parallel analysis passes")).toBeLessThan(
      wrapper.text().indexOf("Phase 3 - Synthesis and decision questions"),
    );
  });
});
