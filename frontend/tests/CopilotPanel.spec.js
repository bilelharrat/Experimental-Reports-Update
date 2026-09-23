// Ask Warren (CopilotPanel.vue): starters, "Buffetting…" while he answers,
// Stop, the finished answer's actions, and Clear chat.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  copilot: {
    context: vi.fn(),
    ask: vi.fn(),
    attach: vi.fn(),
    threads: vi.fn(),
    startThread: vi.fn(),
    createTask: vi.fn(),
    applyEdit: vi.fn(),
    recordEvent: vi.fn(() => Promise.resolve()),
  },
  uploadResearchFile: vi.fn(),
  generateReport: vi.fn(),
  analyzeResearchFile: vi.fn(),
  decisionRecords: { add: vi.fn() },
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
    m.copilot.threads.mockResolvedValue([]);
    m.copilot.startThread.mockResolvedValue({ session_id: SID, previous_session_id: "" });
    m.copilot.attach.mockResolvedValue({
      session_id: SID,
      name: "term-sheet.pdf",
      stored_name: "abc123.pdf",
    });
    m.uploadResearchFile.mockResolvedValue({ id: "file-9" });
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

  it("starts a new thread on the server, for everyone", async () => {
    m.console.getTurns.mockResolvedValue([
      { id: "t1", role: "user", text: "Old question", ts: "2026-01-01T00:00:00Z" },
      { id: "t1", role: "assistant", text: "Old answer", ts: "2026-01-01T00:00:01Z" },
    ]);
    m.copilot.startThread.mockResolvedValue({
      session_id: "n".repeat(32),
      previous_session_id: SID,
    });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain("Old answer");

    await wrapper.vm.newThread();
    await flushPromises();

    expect(m.copilot.startThread).toHaveBeenCalledWith("acme", { mode: "quick" });
    expect(wrapper.text()).not.toContain("Old answer");
    expect(wrapper.text()).toContain("Ask Warren about Acme Corp");
  });

  it("does not hide a thread behind a stale local marker", async () => {
    // An older release hid turns per browser, which is exactly what the
    // desk complained about: two people, two different conversations.
    window.localStorage.setItem(
      "bsh.warren.cleared",
      JSON.stringify({ acme: { sid: SID, count: 2 } }),
    );
    m.console.getTurns.mockResolvedValue([
      { id: "t1", role: "user", text: "Old question", ts: "2026-01-01T00:00:00Z" },
      { id: "t1", role: "assistant", text: "Old answer", ts: "2026-01-01T00:00:01Z" },
    ]);

    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.text()).toContain("Old answer");
    expect(window.localStorage.getItem("bsh.warren.cleared")).toBeNull();
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
  it("says when Gemini answered because Claude was out of tokens", async () => {
    const limit = "You've hit your weekly limit · resets 5pm (America/Los_Angeles)";
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.find("textarea").setValue("Why did chip stocks soar today?");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    const stream = streams.at(-1);
    // Claude streams its limit message as text before it gives up...
    stream.emit({ type: "claude_action", action: "thinking", text: limit });
    await flushPromises();
    expect(wrapper.text()).toContain(limit);
    // ...and Gemini takes the question over: that text was never the answer.
    stream.emit({ type: "claude_action", action: "fallback", engine: "gemini", reason: limit });
    await flushPromises();
    expect(wrapper.text()).not.toContain(limit);
    expect(wrapper.text()).toContain("Asking Gemini instead…");

    m.console.getTurns.mockResolvedValue([
      { id: "turn-1", role: "user", text: "Why did chip stocks soar today?", ts: new Date().toISOString() },
      {
        id: "turn-1",
        role: "assistant",
        text: "AI demand lifted the whole group.",
        engine: "gemini",
        model: "gemini-3.8-flash",
        fallback_reason: limit,
        ts: new Date().toISOString(),
      },
    ]);
    stream.emit({ type: "done", text: "AI demand lifted the whole group." });
    await flushPromises();

    const answer = wrapper.find('[data-turn-role="assistant"]');
    expect(answer.text()).toContain("AI demand lifted the whole group.");
    expect(answer.find('[data-testid="warren-engine-note"]').text()).toBe(
      `Gemini 3.8 Flash answered · Claude couldn't: ${limit}`,
    );
    expect(answer.find(".warren-error").exists()).toBe(false);
  });

  // A document handed to Warren: staged as it is picked, sent with the
  // question, and kept under the company only when asked.
  async function attachFile(wrapper, file) {
    const input = wrapper.find('input[type="file"]');
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });
    await input.trigger("change");
    await flushPromises();
  }

  const pdf = (name = "term-sheet.pdf") =>
    new File([new Uint8Array([37, 80, 68, 70])], name, { type: "application/pdf" });

  it("stages a picked file and sends it with the question", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    const file = pdf();
    await attachFile(wrapper, file);

    expect(m.copilot.attach).toHaveBeenCalledWith("acme", file, "quick");
    const chip = wrapper.find(".warren-file");
    expect(chip.text()).toContain("term-sheet.pdf");

    await wrapper.find("textarea").setValue("What is unusual in this term sheet?");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(m.copilot.ask).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({
        prompt: "What is unusual in this term sheet?",
        attachments: ["abc123.pdf"],
        attachment_names: { "abc123.pdf": "term-sheet.pdf" },
      }),
    );
    // The question carries it now, so the composer is clear...
    expect(wrapper.findAll(".warren-file").length).toBe(1);
    // ...and the file shows under the question it went with.
    expect(wrapper.find('[data-turn-role="user"] .warren-file').text()).toContain(
      "term-sheet.pdf",
    );
  });

  it("refuses a file Warren cannot read, before the question is sent", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await attachFile(
      wrapper,
      new File(["PK"], "models.zip", { type: "application/zip" }),
    );

    expect(m.copilot.attach).not.toHaveBeenCalled();
    expect(wrapper.find(".warren-file").exists()).toBe(false);
    expect(wrapper.text()).toContain("Attach an image");
  });

  it("says so when staging fails, and leaves the file out of the question", async () => {
    m.copilot.attach.mockRejectedValue(
      Object.assign(new Error("HTTP 400"), {
        detail: { detail: { code: "attachment_too_large" } },
      }),
    );
    const wrapper = mountPanel();
    await flushPromises();

    await attachFile(wrapper, pdf("huge.pdf"));

    const chip = wrapper.find(".warren-file");
    expect(chip.attributes("data-tone")).toBe("warning");

    await wrapper.find("textarea").setValue("Read this");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(m.copilot.ask).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ attachments: [] }),
    );
  });

  it("files an attachment under the company on Save to Files", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const file = pdf();
    await attachFile(wrapper, file);

    const save = wrapper.find(".warren-file-action");
    expect(save.text()).toContain("Save to Files");
    await save.trigger("click");
    await flushPromises();

    expect(m.uploadResearchFile).toHaveBeenCalledWith("acme", file);
    expect(wrapper.find(".warren-file").text()).toContain("In Files");
    expect(wrapper.find(".warren-file-action").exists()).toBe(false);
  });

  it("drops a file from the composer again", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    await attachFile(wrapper, pdf());

    await wrapper.find(".warren-file-clear").trigger("click");

    expect(wrapper.find(".warren-file").exists()).toBe(false);
  });

  it("names a chosen Gemini, and says nothing under a Claude answer", async () => {
    m.console.getTurns.mockResolvedValue([
      { id: "t1", role: "user", text: "Is the moat widening?" },
      { id: "t1", role: "assistant", text: "Yes, slowly.", engine: "claude", model: "claude-sonnet-5" },
      { id: "t2", role: "user", text: "And the margins?" },
      { id: "t2", role: "assistant", text: "Holding up.", engine: "gemini", model: "gemini-3.8-flash" },
    ]);
    const wrapper = mountPanel();
    await flushPromises();

    const notes = wrapper
      .findAll('[data-turn-role="assistant"]')
      .map((answer) => answer.find('[data-testid="warren-engine-note"]'));
    expect(notes[0].exists()).toBe(false);
    expect(notes[1].text()).toBe("Answered by Gemini 3.8 Flash");
  });
});

describe("CopilotPanel — editing a question you already sent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    streams.length = 0;
    copilotMode.value = "quick";
    copilotSelection.value = null;
    copilotAttention.value = null;
    copilotDraftPrompt.value = "";
    window.localStorage.clear();
    m.copilot.context.mockResolvedValue(contextPayload());
    m.copilot.ask.mockResolvedValue({ session_id: SID, turn_id: "turn-2" });
    m.console.getTurns.mockResolvedValue([
      { id: "turn-1", role: "user", text: "whats the mote", ts: "2026-09-23T12:00:00Z" },
      { id: "turn-1", role: "assistant", text: "A moat is…", ts: "2026-09-23T12:00:04Z" },
    ]);
  });

  afterEach(() => {
    for (const wrapper of [...mounted]) unmountPanel(wrapper);
  });

  async function openEditor(wrapper) {
    const edit = wrapper
      .findAll("button")
      .find((b) => b.text().trim() === "Edit");
    await edit.trigger("click");
    await flushPromises();
    return wrapper.find(".ask-edit-input");
  }

  it("re-asks the corrected question and drops the pair it replaces", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.text()).toContain("whats the mote");

    const box = await openEditor(wrapper);
    expect(box.element.value).toBe("whats the mote");
    await box.setValue("what is the moat?");
    await wrapper.find(".ask-edit").trigger("submit");
    await flushPromises();

    expect(m.copilot.ask).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ prompt: "what is the moat?", edits: "turn-1" }),
    );
    // The old question and the answer it drew are gone straight away,
    // without waiting for the next poll.
    expect(wrapper.text()).not.toContain("whats the mote");
    expect(wrapper.text()).not.toContain("A moat is…");
    expect(wrapper.text()).toContain("what is the moat?");
  });

  it("leaves the question alone on Escape", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    const box = await openEditor(wrapper);
    await box.setValue("something else");
    await box.trigger("keydown", { key: "Escape" });
    await flushPromises();

    expect(m.copilot.ask).not.toHaveBeenCalled();
    expect(wrapper.find(".ask-edit-input").exists()).toBe(false);
    expect(wrapper.text()).toContain("whats the mote");
  });

  it("keeps the old question if the edit never lands", async () => {
    m.copilot.ask.mockRejectedValue(new Error("HTTP 500"));
    const wrapper = mountPanel();
    await flushPromises();

    const box = await openEditor(wrapper);
    await box.setValue("what is the moat?");
    await wrapper.find(".ask-edit").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("whats the mote");
  });

  it("signs a question somebody else asked", async () => {
    m.console.getTurns.mockResolvedValue([
      {
        id: "turn-9",
        role: "user",
        text: "Why the write-down?",
        author: { email: "sam@bshventures.com", name: "Sam Ortiz" },
        ts: "2026-09-23T12:00:00Z",
      },
    ]);
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.find(".warren-byline").text()).toContain("Sam Ortiz");
  });

  it("says when a question has been rewritten", async () => {
    m.console.getTurns.mockResolvedValue([
      {
        id: "turn-9",
        role: "user",
        text: "What is the moat?",
        edits: "turn-1",
        ts: "2026-09-23T12:00:00Z",
      },
    ]);
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.find(".warren-byline").text()).toContain("edited");
  });
});

describe("CopilotPanel — the thread history the team shares", () => {
  const OLD_SID = "o".repeat(32);

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
    m.copilot.threads.mockResolvedValue([
      {
        id: SID,
        active: true,
        question_count: 1,
        opening_question: "What is the moat?",
        askers: ["You"],
        last_at: "2026-09-23T12:00:00Z",
      },
      {
        id: OLD_SID,
        active: false,
        question_count: 3,
        opening_question: "Why the write-down?",
        askers: ["Sam Ortiz", "Dana Lee"],
        last_at: "2026-09-19T09:00:00Z",
      },
    ]);
  });

  afterEach(() => {
    for (const wrapper of [...mounted]) unmountPanel(wrapper);
  });

  it("lists earlier threads with who asked in them", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    await wrapper.vm.toggleHistory();
    await flushPromises();

    expect(m.copilot.threads).toHaveBeenCalledWith("acme", "quick");
    const rows = wrapper.findAll(".warren-thread");
    expect(rows).toHaveLength(2);
    expect(rows[0].attributes("data-current")).toBe("true");
    expect(rows[1].text()).toContain("Why the write-down?");
    expect(rows[1].text()).toContain("Sam Ortiz, Dana Lee");
    expect(rows[1].text()).toContain("3 questions");
  });

  it("opens an earlier thread read-only, with the way back", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    await wrapper.vm.toggleHistory();
    await flushPromises();

    m.console.getTurns.mockResolvedValue([
      { id: "t7", role: "user", text: "Why the write-down?", ts: "2026-09-19T09:00:00Z" },
      { id: "t7", role: "assistant", text: "Goodwill from the 2024 deal.", ts: "2026-09-19T09:00:03Z" },
    ]);
    await wrapper.findAll(".warren-thread")[1].trigger("click");
    await flushPromises();

    expect(m.console.getTurns).toHaveBeenCalledWith("acme", OLD_SID);
    expect(wrapper.text()).toContain("Goodwill from the 2024 deal.");
    // No composer while reading history — you cannot add to a closed thread.
    expect(wrapper.find(".ask-composer").exists()).toBe(false);
    expect(wrapper.find(".warren-viewing").text()).toContain("Reading an earlier thread");

    await wrapper.find(".warren-viewing button").trigger("click");
    await flushPromises();
    expect(wrapper.find(".ask-composer").exists()).toBe(true);
  });
});

describe("CopilotPanel — work Warren offers to start", () => {
  function answerOffering(work) {
    return [
      { id: "t1", role: "user", text: "Should we write this up?", ts: "2026-09-23T12:00:00Z" },
      {
        id: "t1",
        role: "assistant",
        text: `I can put the IC packet together.\n\`\`\`json\n${JSON.stringify({ run_work: work })}\n\`\`\``,
        ts: "2026-09-23T12:00:05Z",
      },
    ];
  }

  beforeEach(() => {
    vi.clearAllMocks();
    streams.length = 0;
    copilotMode.value = "quick";
    copilotSelection.value = null;
    copilotAttention.value = null;
    copilotDraftPrompt.value = "";
    window.localStorage.clear();
    m.copilot.context.mockResolvedValue(contextPayload());
    m.copilot.threads.mockResolvedValue([]);
    m.generateReport.mockResolvedValue({ report_id: "r-1" });
    m.analyzeResearchFile.mockResolvedValue({ kind: "analysis" });
    m.decisionRecords.add.mockResolvedValue({ id: "d-1" });
  });

  afterEach(() => {
    for (const wrapper of [...mounted]) unmountPanel(wrapper);
  });

  function confirmButton(wrapper) {
    return wrapper.find(".warren-work button");
  }

  it("runs the report Warren proposed, once it is confirmed", async () => {
    m.console.getTurns.mockResolvedValue(
      answerOffering({
        kind: "report",
        title: "IC packet for Acme",
        why: "The files are staged.",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Partner",
        quality: "balanced",
      }),
    );
    const wrapper = mountPanel();
    await flushPromises();

    const card = wrapper.find(".warren-work");
    expect(card.text()).toContain("IC packet for Acme");
    expect(card.text()).toContain("Investment Memo (Late-Stage)");
    // Nothing has been spent yet.
    expect(m.generateReport).not.toHaveBeenCalled();

    await confirmButton(wrapper).trigger("click");
    await flushPromises();

    expect(m.generateReport).toHaveBeenCalledWith(
      expect.objectContaining({
        company_id: "acme",
        report_type: "Investment Memo (Late-Stage)",
        audience: "Partner",
        quality: "balanced",
      }),
    );
    expect(wrapper.find(".warren-work").text()).toContain("jobs rail");
  });

  it("says so when the run will not start", async () => {
    m.generateReport.mockRejectedValue(new Error("HTTP 409"));
    m.console.getTurns.mockResolvedValue(answerOffering({ kind: "report" }));
    const wrapper = mountPanel();
    await flushPromises();

    await confirmButton(wrapper).trigger("click");
    await flushPromises();

    expect(wrapper.find(".warren-work").text()).toContain("HTTP 409");
    // Still offered, so it can be tried again.
    expect(confirmButton(wrapper).exists()).toBe(true);
  });

  it("reads a document when that is what was offered", async () => {
    m.console.getTurns.mockResolvedValue(
      answerOffering({
        kind: "document_analysis",
        file_id: "file-7",
        file_name: "term-sheet.pdf",
      }),
    );
    const wrapper = mountPanel();
    await flushPromises();

    await confirmButton(wrapper).trigger("click");
    await flushPromises();

    expect(m.analyzeResearchFile).toHaveBeenCalledWith("acme", "file-7");
  });

  it("ignores an offer it cannot act on", async () => {
    m.console.getTurns.mockResolvedValue(
      answerOffering({ kind: "document_analysis", file_name: "mystery.pdf" }),
    );
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.find(".warren-work").exists()).toBe(false);
  });
});
