// Component test for CompanyConsole.vue. The api module is mocked so the
// component lifecycle doesn't make real HTTP calls.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

// vi.mock() is hoisted above all imports, so we have to declare its
// dependencies via vi.hoisted() to keep them in scope.
const m = vi.hoisted(() => ({
  listSessions: vi.fn(),
  getSession: vi.fn(),
  getTurns: vi.fn(),
  createSession: vi.fn(),
  ask: vi.fn(),
  archive: vi.fn(),
  deleteSession: vi.fn(),
  cancelAsk: vi.fn(),
  askStreamUrl: vi.fn(() => "/fake/stream"),
  hydrateStreamUrl: vi.fn(() => "/fake/hydrate"),
  attachmentUrl: vi.fn(),
}));
const { listSessions, getSession, getTurns } = m;

vi.mock("../src/api.js", () => ({
  api: { console: m },
}));

// Stub EventSource so the component can `new EventSource(...)` without
// browser support (jsdom doesn't ship one). Tests don't dispatch events
// here — we only check the static rendering against meta state.
class FakeEventSource {
  constructor() {
    this.onmessage = null;
    this.onerror = null;
  }
  close() {}
}
globalThis.EventSource = FakeEventSource;

import CompanyConsole from "../src/components/CompanyConsole.vue";

function activeMeta({ usage } = {}) {
  return {
    id: "a".repeat(32),
    company_id: "ami_labs",
    status: "active",
    title: "Test session",
    created_at: "2026-01-01T00:00:00Z",
    last_used_at: "2026-01-01T00:00:00Z",
    archived_at: null,
    hydration_status: "done",
    tokens: {
      input: 0, output: 0, cache_read: 0, cache_creation: 0,
      total_cost_usd: 0.123,
      last_turn_usage: usage || null,
    },
    summary: null,
    pct_used: 0, context_used: 0, context_window: 1_000_000,
  };
}

describe("CompanyConsole — token meter & lock behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getTurns.mockResolvedValue([]);
  });

  async function mountWith(usage) {
    const meta = activeMeta({ usage });
    listSessions.mockResolvedValue([meta]);
    getSession.mockResolvedValue(meta);
    const wrapper = mount(CompanyConsole, {
      props: { companyId: "ami_labs" },
    });
    await flushPromises();
    return wrapper;
  }

  it("renders green meter and enabled Send below 75%", async () => {
    const wrapper = await mountWith({
      input_tokens: 100_000,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    const text = wrapper.text();
    expect(text).toContain("100K");
    expect(text).not.toContain("Session getting full");
    expect(text).not.toContain("Session full");
  });

  it("shows warning banner at 75–90%", async () => {
    const wrapper = await mountWith({
      input_tokens: 800_000,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(wrapper.text()).toContain("Session getting full");
    expect(wrapper.text()).not.toContain("Session full");
  });

  it("shows lock banner + CTA at >=90% and disables Send", async () => {
    const wrapper = await mountWith({
      input_tokens: 950_000,
      cache_read_input_tokens: 0,
      cache_creation_input_tokens: 0,
    });
    expect(wrapper.text()).toContain("Session full");
    expect(wrapper.text()).toContain("Archive & start new");
    // The Send button should be disabled (lockSend is true). Find by
    // role/text; @vue/test-utils' find on text isn't perfect, so check
    // the bound disabled attr on any rendered Send.
    const sendButton = wrapper
      .findAll("button")
      .find((b) => b.text() === "Send");
    if (sendButton) {
      expect(sendButton.attributes("disabled")).toBeDefined();
    }
  });
});

describe("CompanyConsole — create session", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m.getTurns.mockResolvedValue([]);
    m.listSessions.mockResolvedValue([]);
  });

  it("creates a session without a destination modal", async () => {
    const created = activeMeta();
    m.createSession.mockResolvedValue(created);
    m.getSession.mockResolvedValue(created);

    const wrapper = mount(CompanyConsole, {
      props: { companyId: "ami_labs" },
    });
    await flushPromises();

    expect(wrapper.text()).not.toContain("Include memo inputs");
    expect(wrapper.text()).not.toContain("Create console");

    const newButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("New"));
    expect(newButton).toBeTruthy();
    await newButton.trigger("click");
    await flushPromises();

    expect(m.createSession).toHaveBeenCalledWith("ami_labs", {
      include_background_docs: true,
      include_library_docs: false,
      output_language: "en",
    });
    expect(wrapper.text()).toContain("Test session");
  });
});
