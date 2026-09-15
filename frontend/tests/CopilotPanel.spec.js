// Ask Warren (CopilotPanel.vue): starters, "Buffetting…" while he answers,
// Stop, the finished answer's actions, and Clear chat.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  copilot: {
    context: vi.fn(),
    ask: vi.fn(),
    createTask: vi.fn(),
    applyEdit: vi.fn(),
    recordEvent: vi.fn(() => Promise.resolve()),
  },
  console: {
    getTurns: vi.fn(),
    cancelAsk: vi.fn(() => Promise.resolve(true)),
    askStreamUrl: vi.fn(() => "/fake/ask-stream"),
    hydrateStreamUrl: vi.fn(() => "/fake/hydrate-stream"),
  },
}));

vi.mock("../src/api.js", () => ({ api: m }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const streams = [];
class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.onmessage = null;
    this.onerror = null;
    this.closed = false;
    streams.push(this);
  }
  emit(entry) {
    this.onmessage?.({ data: JSON.stringify(entry) });
  }
  close() {
    this.closed = true;
  }
}
globalThis.EventSource = FakeEventSource;

import CopilotPanel from "../src/components/CopilotPanel.vue";
import {
  copilotAttention,
  copilotDraftPrompt,
  copilotMode,
  copilotSelection,
} from "../src/copilotContext.js";

const SID = "s".repeat(32);

function contextPayload({ session = { id: SID, hydration_status: "skipped" } } = {}) {
  return {
    company_id: "acme",
    label: "Acme Corp",
    actions: [
      {
        id: "evidence_gaps",
        label_key: "copilot.action_evidence_gaps",
        prompt_key: "copilot.prompt_evidence_gaps",
      },
    ],
    proactive: [],
    files: [],
    provenance: null,
    auto_prompt: null,
    session,
  };
}

// Panels share module-level context refs, so a panel left mounted would react
// to the next test's changes. Unmount every panel after each test.
const mounted = new Set();

const copilotNavigate = vi.fn();

function mountPanel(props = {}) {
  const wrapper = mount(CopilotPanel, {
    props: { companyId: "acme", companyName: "Acme Corp", ...props },
    global: { stubs: { CompanyConsole: true }, provide: { copilotNavigate } },
  });
  mounted.add(wrapper);
  return wrapper;
}

function unmountPanel(wrapper) {
  mounted.delete(wrapper);
  wrapper.unmount();
}

describe("CopilotPanel — Ask Warren", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    streams.length = 0;
    copilotMode.value = "quick";
    copilotSelection.value = null;
    copilotAttention.value = null;
    copilotDraftPrompt.value = "";
    window.localStorage.clear();
    m.copilot.context.mockResolvedValue(contextPayload());
    m.console.getTurns.mockResolvedValue([]);
    m.copilot.ask.mockResolvedValue({ session_id: SID, turn_id: "turn-1" });
  });

  afterEach(() => {
    mounted.forEach((wrapper) => unmountPanel(wrapper));
  });

  it("opens with Warren's hero and starters written about the company", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.text()).toContain("Ask Warren about Acme Corp");
    expect(wrapper.find(".warren-hero .warren-mark img").exists()).toBe(true);
    const starter = wrapper
      .findAll(".ask-suggestion")
      .find((row) => row.text().includes("Does Acme Corp have a durable moat?"));
    expect(starter).toBeTruthy();
    expect(wrapper.find("textarea").attributes("placeholder")).toBe("Ask Warren about Acme Corp…");

    await starter.trigger("click");
    await flushPromises();

    expect(m.copilot.ask).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({
        prompt: "Does Acme Corp have a durable moat? What could erode it?",
        mode: "quick",
      }),
    );
  });

  it("says Buffetting… while Warren answers, and Stop cancels the turn", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.find("textarea").setValue("Is the moat widening?");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(wrapper.find(".ask-bubble").text()).toBe("Is the moat widening?");
    expect(wrapper.find(".warren-status").text()).toBe("Buffetting…");
    expect(wrapper.text()).not.toContain("Thinking");
    expect(wrapper.emitted("state").at(-1)[0]).toMatchObject({ busy: true });

    const stream = streams.at(-1);
    stream.emit({ type: "claude_action", action: "tool_use", tool: "Read", preview: "docs/10-K.pdf  (pages=3)" });
    await flushPromises();
    expect(wrapper.text()).toContain("Reading 10-K.pdf");

    const stop = wrapper.find('[aria-label="Stop"]');
    expect(stop.exists()).toBe(true);
    await stop.trigger("click");
    await flushPromises();
    expect(m.console.cancelAsk).toHaveBeenCalledWith("acme", SID, "turn-1");
    expect(wrapper.find(".warren-status").text()).toBe("Stopping…");

    m.console.getTurns.mockResolvedValue([
      { id: "turn-1", role: "user", text: "Is the moat widening?", ts: new Date().toISOString() },
      {
        id: "turn-1",
        role: "assistant",
        text: "The brand still",
        error: "Interrupted (user_cancelled)",
        interrupt_reason: "user_cancelled",
      },
    ]);
    stream.emit({ type: "error", error: "Interrupted (user_cancelled)" });
    await flushPromises();

    expect(wrapper.find(".warren-status").exists()).toBe(false);
    expect(wrapper.text()).toContain("Stopped before Warren finished.");
    expect(wrapper.text()).toContain("The brand still");
    expect(wrapper.find(".warren-error").exists()).toBe(false);
  });

  it("shows the finished answer with Copy, Ask again and Warren's follow-ups", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.find("textarea").setValue("What is it worth?");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    m.console.getTurns.mockResolvedValue([
      { id: "turn-1", role: "user", text: "What is it worth?", ts: new Date().toISOString() },
      { id: "turn-1", role: "assistant", text: "Roughly **$40** a share.", ts: new Date().toISOString() },
    ]);
    streams.at(-1).emit({ type: "done" });
    await flushPromises();

    const answer = wrapper.find('[data-turn-role="assistant"]');
    expect(answer.find(".warren-md").html()).toContain("<strong>$40</strong>");
    expect(answer.text()).toContain("Copy");
    expect(answer.text()).toContain("Ask again");
    const chips = wrapper.findAll(".ask-chip").map((chip) => chip.text());
    expect(chips).toContain("What would change your mind?");
    expect(chips).toContain("Summarize that in three bullets");
    expect(wrapper.emitted("state").at(-1)[0]).toMatchObject({ busy: false, hasTurns: true });

    m.copilot.ask.mockResolvedValue({ session_id: SID, turn_id: "turn-2" });
    await answer.findAll(".warren-action").find((b) => b.text().includes("Ask again")).trigger("click");
    await flushPromises();
    expect(m.copilot.ask).toHaveBeenLastCalledWith(
      "acme",
      expect.objectContaining({ prompt: "What is it worth?" }),
    );
  });

  it("opens a cited file from the answer", async () => {
    m.copilot.context.mockResolvedValue({
      ...contextPayload(),
      files: [{ id: "file-7", filename: "deck.pdf" }],
    });
    m.console.getTurns.mockResolvedValue([
      { id: "t1", role: "user", text: "Where is revenue?", ts: "2026-01-01T00:00:00Z" },
      { id: "t1", role: "assistant", text: "Page four (deck.pdf p.4).", ts: "2026-01-01T00:00:01Z" },
    ]);
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.find(".warren-cite").trigger("click");
    expect(copilotNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "file", companyId: "acme", page: "4" }),
    );
  });

  it("blocks a second question while Warren is still answering", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.find("textarea").setValue("First question");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    await wrapper.find("textarea").setValue("Second question");
    await wrapper.find("textarea").trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(m.copilot.ask).toHaveBeenCalledTimes(1);
    // The draft waits in the composer for the answer to finish.
    expect(wrapper.find("textarea").element.value).toBe("Second question");
  });

  it("picks an unanswered question back up when the panel reopens", async () => {
    m.console.getTurns.mockResolvedValue([
      { id: "turn-9", role: "user", text: "Still going?", ts: new Date().toISOString() },
    ]);
    const wrapper = mountPanel();
    await flushPromises();

    expect(streams.at(-1)?.url).toBe("/fake/ask-stream");
    expect(m.console.askStreamUrl).toHaveBeenCalledWith("acme", SID, "turn-9");
    expect(wrapper.find(".warren-status").text()).toBe("Buffetting…");
  });

  it("clears the chat from view and remembers it", async () => {
    m.console.getTurns.mockResolvedValue([
      { id: "t1", role: "user", text: "Old question", ts: "2026-01-01T00:00:00Z" },
      { id: "t1", role: "assistant", text: "Old answer", ts: "2026-01-01T00:00:01Z" },
    ]);
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain("Old answer");

    wrapper.vm.clearChat();
    await flushPromises();
    expect(wrapper.text()).not.toContain("Old answer");
    expect(wrapper.text()).toContain("Ask Warren about Acme Corp");

    unmountPanel(wrapper);
    const again = mountPanel();
    await flushPromises();
    expect(again.text()).not.toContain("Old answer");
  });

  it("puts a handed-over question in the composer without sending it", async () => {
    copilotDraftPrompt.value = "Why is NVDA moving?";
    copilotSelection.value = { ticker: "nvda", name: "NVIDIA" };
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.find("textarea").element.value).toBe("Why is NVDA moving?");
    expect(copilotDraftPrompt.value).toBe("");
    expect(m.copilot.ask).not.toHaveBeenCalled();
    // The chip says what came with it, and can be dropped.
    expect(wrapper.find(".warren-context").text()).toContain("NVDA · NVIDIA");
    await wrapper.find('[aria-label="Ask without this context"]').trigger("click");
    await flushPromises();
    expect(copilotSelection.value).toBeNull();
    expect(wrapper.find(".warren-context").exists()).toBe(false);
  });

  it("asks for a company when none is chosen", async () => {
    const wrapper = mountPanel({
      companyId: "",
      companyName: "",
      suggestedCompanies: [{ id: "acme", name: "Acme Corp", ticker: "ACME" }],
    });
    await flushPromises();

    expect(m.copilot.context).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Pick one to start.");
    await wrapper.find(".ask-suggestion").trigger("click");
    expect(wrapper.emitted("choose-company")[0]).toEqual(["acme"]);
  });
});
