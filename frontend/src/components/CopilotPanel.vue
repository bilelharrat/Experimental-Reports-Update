<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  AlertTriangle,
  ArrowUp,
  ArrowUpRight,
  Check,
  Copy,
  Crosshair,
  FileText,
  MessageSquareText,
  RotateCcw,
  ScrollText,
  Sparkles,
  Square,
  X,
} from "lucide-vue-next";
import WarrenMark from "./WarrenMark.vue";
import Monogram from "./Monogram.vue";
import { api } from "../api.js";
import {
  buildDiscussPrompt,
  extractCitations,
  followUpChips,
  parseStructuredOutputs,
  resolveCopilotAction,
  resolveCitationTarget,
  stripStructuredBlocks,
} from "../copilotActions.js";
import {
  buildClientContext,
  clearCopilotFocus,
  copilotAttention,
  copilotDraftPrompt,
  copilotDragTell,
  copilotJob,
  copilotMode,
  copilotPendingPrompt,
  copilotSelection,
  copilotSurface,
  copilotTab,
} from "../copilotContext.js";
import CompanyConsole from "./CompanyConsole.vue";
import { renderMarkdown } from "../markdown.js";
import { appLanguage } from "../state.js";
import { useT } from "../i18n.js";

const props = defineProps({
  companyId: { type: String, default: "" },
  companyName: { type: String, default: "" },
  // What Warren sees beyond the company ("Memo"); empty when the company
  // isn't the page on screen.
  contextLabel: { type: String, default: "" },
  // Offered when no company is chosen yet, most recent first.
  suggestedCompanies: { type: Array, default: () => [] },
});

const emit = defineEmits(["close", "navigate", "state", "choose-company"]);

const t = useT();
const router = useRouter();
const copilotNavigate = inject("copilotNavigate", null);

// "Clear chat" hides the turns so far; the server session (and Warren's
// memory of it) carries on, as on the Mac.
const CLEARED_KEY = "bsh.warren.cleared";
// A question still unanswered this long after it was asked is picked back up
// when the panel reopens; older ones are treated as lost.
const RESUME_WINDOW_MS = 15 * 60 * 1000;

const mode = ref(copilotMode.value || "quick");
const contextPayload = ref(null);
const contextLoading = ref(false);
const contextError = ref(null);
const autoPromptSent = ref(false);

const prompt = ref("");
const sending = ref(false);
const sessionId = ref("");
const serverTurns = ref([]);
// Rows the server never recorded (a failed submit).
const localRows = ref([]);
// The question just asked, shown until the server's copy of it arrives.
const pendingQuestion = ref(null);
const pendingTurnId = ref(null);
const pendingText = ref("");
const pendingActivity = ref("");
const stopping = ref(false);
const clearedMarker = ref(null);
const copiedKey = ref("");
// Long handed-over questions (a market packet) open collapsed.
const expandedKeys = ref(new Set());
const taskSaving = ref(false);
const taskSaved = ref(false);
const editSaving = ref(false);
const editApplied = ref(false);
const transcriptEl = ref(null);
const composerEl = ref(null);

let askEventSource = null;
let hydrateEventSource = null;
let recoverTimer = null;
let stopTimer = null;
let copiedTimer = null;

const busy = computed(() => sending.value || Boolean(pendingTurnId.value));

const companyLabel = computed(
  () =>
    props.companyName ||
    String(contextPayload.value?.label || "").split(" · ")[0] ||
    t("app.company"),
);

const actions = computed(() => {
  const client = buildClientContext();
  const rows = contextPayload.value?.actions || [];
  return rows.map((action) =>
    resolveCopilotAction(action, t, {
      selection: client.selection,
      attention: client.attention,
      job: client.job,
      workspace: contextPayload.value?.workspace,
      company_name: companyLabel.value,
    }),
  );
});

const proactiveMessages = computed(() => {
  const rows = contextPayload.value?.proactive || [];
  const actionMap = Object.fromEntries(actions.value.map((row) => [row.id, row]));
  return rows
    .map((row) => {
      const action = actionMap[row.action_id];
      if (!action) return null;
      return {
        ...row,
        label: row.label_key ? t(row.label_key) : action.label,
        prompt: action.prompt,
      };
    })
    .filter(Boolean);
});

function clip(text, limit) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

// What a page handed Warren: a memo point, claim, ticker or headline.
const selectionLabel = computed(() => {
  const selection = copilotSelection.value;
  if (!selection || typeof selection !== "object") return "";
  const ticker = selection.ticker ? String(selection.ticker).toUpperCase() : "";
  const direct =
    selection.section_title ||
    selection.card_title ||
    selection.bullet_text ||
    selection.claim ||
    selection.metric_label ||
    selection.label ||
    selection.title ||
    (ticker ? [ticker, selection.name].filter(Boolean).join(" · ") : "");
  if (direct) return clip(direct, 64);
  if (!selection.target_kind) return "";
  // Dragged targets are named server-side (the provenance label).
  const parts = String(contextPayload.value?.label || "").split(" · ");
  return parts.length > 1 ? clip(parts.slice(1).join(" · "), 64) : "";
});

// A flag or failed job Warren was asked about.
const focusLabel = computed(
  () =>
    selectionLabel.value ||
    clip(copilotAttention.value?.label || copilotJob.value?.title || "", 64),
);

const seesLabel = computed(() => focusLabel.value || props.contextLabel || "");

const hydrationNote = computed(() => {
  const status = contextPayload.value?.session?.hydration_status;
  if (status === "in_progress") return t("copilot.hydrating");
  if (status === "error") return t("copilot.hydration_failed");
  return "";
});

const starters = computed(() => {
  const company = companyLabel.value;
  return ["moat", "capital", "value", "ten_years"].map((id) => ({
    id,
    prompt: t(`copilot.starter_${id}`, { company }),
  }));
});

const provenance = computed(() => contextPayload.value?.provenance || null);
const provenanceSources = computed(() => provenance.value?.sources || []);
const provenanceGaps = computed(() => provenance.value?.gaps || []);
const provenanceContradictions = computed(() => provenance.value?.contradictions || []);
const indexedFiles = computed(() => contextPayload.value?.files || []);

const hiddenCount = computed(() => {
  const marker = clearedMarker.value;
  if (!marker || !sessionId.value || marker.sid !== sessionId.value) return 0;
  return Math.min(Number(marker.count) || 0, serverTurns.value.length);
});

function formatTime(ts) {
  if (!ts) return "";
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function viewTurn(turn, index) {
  const role = turn.role === "user" ? "user" : "assistant";
  const key = `${role}-${turn.id || "row"}-${index}`;
  if (role === "user") {
    const text = String(turn.text || "");
    return { key, role, id: turn.id, text, long: text.length > 320 || text.split("\n").length > 6 };
  }
  const stopped = turn.interrupt_reason === "user_cancelled";
  let error = turn.error ? String(turn.error) : "";
  let body = String(turn.text || "");
  // The server copies the error into text when nothing came back.
  if (error && body.trim() === error.trim()) body = "";
  if (turn.interrupt_reason && !stopped) error = t("copilot.no_answer");
  body = stripStructuredBlocks(body);
  return {
    key,
    role,
    id: turn.id,
    raw: String(turn.text || ""),
    body,
    html: body ? renderMarkdown(body) : "",
    stopped,
    failed: Boolean(error) && !stopped,
    error,
    time: formatTime(turn.ts),
  };
}

const visibleTurns = computed(() => {
  const rows = serverTurns.value.slice(hiddenCount.value);
  const question = pendingQuestion.value;
  const recorded =
    question?.turnId && rows.some((row) => row.role === "user" && row.id === question.turnId);
  const extra = question && !recorded ? [{ role: "user", id: "pending", text: question.text }] : [];
  return [...rows, ...localRows.value, ...extra].map(viewTurn);
});

const latestTurn = computed(() => visibleTurns.value[visibleTurns.value.length - 1] || null);
const latestAnswer = computed(() =>
  latestTurn.value?.role === "assistant" ? latestTurn.value : null,
);

const structuredOutputs = computed(() =>
  latestAnswer.value && !latestAnswer.value.failed
    ? parseStructuredOutputs(latestAnswer.value.raw)
    : {},
);
const proposedTask = computed(() => structuredOutputs.value.research_task || null);
const suggestedEdit = computed(() => structuredOutputs.value.suggested_edit || null);
const nextRoute = computed(() => structuredOutputs.value.next_route || null);
const contradiction = computed(() => structuredOutputs.value.contradiction || null);
const latestCitations = computed(() =>
  latestAnswer.value?.body ? extractCitations(latestAnswer.value.body) : [],
);

const WARREN_FOLLOW_UPS = ["three_bullets", "change_mind", "biggest_risk", "evidence_basis"];

// What to ask next, offered under the latest answer.
const nextChips = computed(() => {
  const answer = latestAnswer.value;
  if (!answer || busy.value || answer.failed || answer.stopped || !answer.body) return [];
  const chips = [];
  const alert = proactiveMessages.value[0];
  if (alert) chips.push({ id: `alert-${alert.action_id}`, label: alert.label, prompt: alert.prompt, tone: "warning" });
  for (const chip of followUpChips(structuredOutputs.value, t)) {
    if (chip.id !== "evidence_next") chips.push(chip);
  }
  for (const id of WARREN_FOLLOW_UPS) {
    const label = t(`copilot.followup_${id}`);
    chips.push({ id, label, prompt: label });
  }
  return chips.slice(0, 4);
});

// The first context load decides between the hero and a transcript; show
// neither until it lands so one doesn't flash into the other.
const firstLoad = computed(() => contextLoading.value && !contextPayload.value);

const showHero = computed(
  () =>
    mode.value === "quick" &&
    !firstLoad.value &&
    visibleTurns.value.length === 0 &&
    !busy.value,
);

const pendingHtml = computed(() => {
  let body = stripStructuredBlocks(pendingText.value);
  // Hide a structured block that is still being written.
  const open = body.lastIndexOf("```json");
  if (open >= 0 && !body.slice(open + 7).includes("```")) body = body.slice(0, open);
  body = body.trim();
  return body ? renderMarkdown(body) : "";
});

const placeholder = computed(() =>
  props.companyId
    ? t("copilot.input_placeholder_company", {
        // "ZaiNar, Inc." shouldn't end up as "Inc.…".
        company: companyLabel.value.replace(/[.。]\s*$/, ""),
      })
    : t("copilot.input_placeholder"),
);

function readClearedMarker(companyId) {
  if (!companyId) return null;
  try {
    const all = JSON.parse(window.localStorage.getItem(CLEARED_KEY) || "{}");
    const marker = all?.[companyId];
    return marker && typeof marker === "object" ? marker : null;
  } catch {
    return null;
  }
}

function writeClearedMarker(companyId, marker) {
  try {
    const all = JSON.parse(window.localStorage.getItem(CLEARED_KEY) || "{}") || {};
    all[companyId] = marker;
    window.localStorage.setItem(CLEARED_KEY, JSON.stringify(all));
  } catch {
    // Private windows can refuse storage; the chat just stays cleared for now.
  }
}

function recordEvent(event, payload = {}) {
  if (!props.companyId) return;
  api.copilot.recordEvent(props.companyId, { event, payload }).catch(() => {});
}

function prefersReducedMotion() {
  return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

function isNearBottom() {
  const el = transcriptEl.value;
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 96;
}

// Follow the conversation only while the reader is already at the bottom.
function scrollToBottom({ force = false } = {}) {
  const follow = force || isNearBottom();
  nextTick(() => {
    const el = transcriptEl.value;
    if (el && follow) el.scrollTop = el.scrollHeight;
  });
}

// When an answer lands, bring its start (and the question) into view rather
// than dropping the reader at the end of a long answer.
function revealLatestAnswer() {
  nextTick(() => {
    const el = transcriptEl.value;
    if (!el) return;
    const answers = el.querySelectorAll('[data-turn-role="assistant"]');
    const answer = answers[answers.length - 1];
    if (!answer) return;
    const question = answer.previousElementSibling;
    const anchor =
      question?.dataset?.turnRole === "user" && question.offsetHeight < el.clientHeight / 3
        ? question
        : answer;
    const top = Math.min(Math.max(anchor.offsetTop - 8, 0), el.scrollHeight - el.clientHeight);
    if (typeof el.scrollTo !== "function") {
      el.scrollTop = top;
      return;
    }
    el.scrollTo({ top, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  });
}

async function loadContext({ triggerAuto = false } = {}) {
  if (!props.companyId) {
    contextPayload.value = null;
    return;
  }
  const companyId = props.companyId;
  contextLoading.value = true;
  contextError.value = null;
  try {
    const payload = await api.copilot.context(companyId, buildClientContext());
    if (companyId !== props.companyId) return;
    const sid = payload?.session?.id;
    if (sid && !busy.value) await loadSessionTurns(sid, { resume: true });
    if (companyId !== props.companyId) return;
    contextPayload.value = payload;
    if (triggerAuto) maybeAutoPrompt();
  } catch (e) {
    contextError.value = e.message;
  } finally {
    contextLoading.value = false;
  }
}

function maybeAutoPrompt() {
  if (copilotDragTell.value) {
    copilotDragTell.value = false;
    return;
  }
  if (contextPayload.value?.provenance) return;
  const auto = contextPayload.value?.auto_prompt;
  if (!auto || autoPromptSent.value || visibleTurns.value.length > 0 || busy.value) return;
  autoPromptSent.value = true;
  nextTick(() => sendPrompt(auto));
}

async function loadSessionTurns(sid, { resume = false } = {}) {
  if (!props.companyId || !sid) return;
  const companyId = props.companyId;
  try {
    const turns = await api.console.getTurns(companyId, sid);
    if (companyId !== props.companyId) return;
    sessionId.value = sid;
    serverTurns.value = (turns || []).filter(
      (row) => row.role === "user" || row.role === "assistant",
    );
  } catch {
    return;
  }
  if (resume) resumeUnanswered(sid);
}

// Warren keeps answering on the server when the panel closes; pick the
// answer back up instead of showing an orphaned question.
function resumeUnanswered(sid) {
  if (busy.value || mode.value !== "quick") return;
  const last = serverTurns.value[serverTurns.value.length - 1];
  if (!last || last.role !== "user" || !last.id) return;
  const askedAt = new Date(last.ts || 0).getTime();
  if (!askedAt || Date.now() - askedAt > RESUME_WINDOW_MS) return;
  openAskStream(sid, last.id);
}

function closeAskStream() {
  if (askEventSource) {
    try {
      askEventSource.close();
    } catch {
      /* */
    }
    askEventSource = null;
  }
}

function closeHydrateStream() {
  if (hydrateEventSource) {
    try {
      hydrateEventSource.close();
    } catch {
      /* */
    }
    hydrateEventSource = null;
  }
}

function finishPending() {
  clearTimeout(recoverTimer);
  clearTimeout(stopTimer);
  pendingTurnId.value = null;
  pendingText.value = "";
  pendingActivity.value = "";
  pendingQuestion.value = null;
  stopping.value = false;
}

function activityFor(entry) {
  const tool = String(entry.tool || "");
  if (tool === "Read") {
    const path = String(entry.preview || "").split("  (")[0];
    const name = path.split("/").pop();
    return name ? t("copilot.activity_reading", { name: clip(name, 48) }) : t("copilot.activity_working");
  }
  if (tool === "Grep" || tool === "Glob") return t("copilot.activity_searching");
  if (tool === "WebSearch" || tool === "WebFetch") return t("copilot.activity_web");
  return t("copilot.activity_working");
}

async function completeAnswer(sid, turnId) {
  closeAskStream();
  if (pendingTurnId.value !== turnId) return;
  await loadSessionTurns(sid);
  if (pendingTurnId.value !== turnId) return;
  finishPending();
  revealLatestAnswer();
}

function openAskStream(sid, turnId, attempt = 0) {
  closeAskStream();
  clearTimeout(recoverTimer);
  pendingTurnId.value = turnId;
  pendingText.value = "";
  pendingActivity.value = "";
  const companyId = props.companyId;
  const es = new EventSource(api.console.askStreamUrl(companyId, sid, turnId));
  askEventSource = es;
  es.onmessage = (ev) => {
    // A replaced stream can still deliver a last event; ignore it.
    if (askEventSource !== es) return;
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (entry.type === "stage" && entry.status === "queued") {
      pendingActivity.value = t("copilot.activity_queued");
    } else if (entry.type === "claude_action") {
      if (entry.action === "thinking" && entry.text) {
        // Each event is a whole text block; keep blocks apart.
        pendingText.value = pendingText.value
          ? `${pendingText.value}\n\n${entry.text}`
          : entry.text;
        pendingActivity.value = "";
        scrollToBottom();
      } else if (entry.action === "tool_use") {
        pendingActivity.value = activityFor(entry);
      }
    } else if (entry.type === "done" || entry.type === "error") {
      completeAnswer(sid, turnId);
    }
  };
  es.onerror = () => {
    if (askEventSource !== es) return;
    closeAskStream();
    recoverAsk(sid, turnId, attempt);
  };
}

// The stream dropped before the answer finished: check whether it landed,
// otherwise reconnect a few times before giving up.
async function recoverAsk(sid, turnId, attempt) {
  if (pendingTurnId.value !== turnId) return;
  await loadSessionTurns(sid);
  if (pendingTurnId.value !== turnId) return;
  const answered = serverTurns.value.some(
    (row) => row.role === "assistant" && row.id === turnId,
  );
  if (answered || attempt >= 3) {
    finishPending();
    if (answered) revealLatestAnswer();
    return;
  }
  recoverTimer = setTimeout(() => {
    if (pendingTurnId.value === turnId) openAskStream(sid, turnId, attempt + 1);
  }, 1500 * (attempt + 1));
}

function openHydrateStream(sid) {
  closeHydrateStream();
  const es = new EventSource(api.console.hydrateStreamUrl(props.companyId, sid));
  hydrateEventSource = es;
  es.onmessage = async (ev) => {
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (entry.type === "done" || entry.type === "error") {
      closeHydrateStream();
      await loadContext();
    }
  };
  es.onerror = () => closeHydrateStream();
}

function autoGrow() {
  const el = composerEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

async function sendPrompt(text) {
  const value = String(text || prompt.value || "").trim();
  if (!value || !props.companyId || busy.value) return;
  const companyId = props.companyId;
  const selection = buildClientContext().selection || {};
  if (selection.target_kind) {
    recordEvent("copilot_drag_tell_ask", {
      target_kind: selection.target_kind,
      label: selection.bullet_text || selection.claim || selection.metric_label,
    });
  }
  sending.value = true;
  taskSaved.value = false;
  editApplied.value = false;
  localRows.value = [];
  if (!text || value === prompt.value.trim()) prompt.value = "";
  nextTick(autoGrow);
  pendingQuestion.value = { text: value, turnId: null };
  scrollToBottom({ force: true });
  try {
    const payload = await api.copilot.ask(companyId, {
      prompt: value,
      context: buildClientContext(),
      output_language: appLanguage.value === "zh" ? "zh" : "en",
      mode: mode.value,
    });
    if (companyId !== props.companyId) return;
    sessionId.value = payload.session_id;
    pendingQuestion.value = { text: value, turnId: payload.turn_id };
    if (payload.hydrate_stream_url && payload.hydration_status === "in_progress") {
      openHydrateStream(payload.session_id);
    }
    openAskStream(payload.session_id, payload.turn_id);
  } catch (e) {
    pendingQuestion.value = null;
    localRows.value = [
      { id: "local-question", role: "user", text: value },
      { id: "local-error", role: "assistant", text: "", error: e.message || t("copilot.no_answer") },
    ];
    revealLatestAnswer();
  } finally {
    sending.value = false;
  }
}

async function stopAnswer() {
  const turnId = pendingTurnId.value;
  const sid = sessionId.value;
  if (!turnId || !sid || stopping.value) return;
  stopping.value = true;
  recordEvent("copilot_stop", {});
  try {
    await api.console.cancelAsk(props.companyId, sid, turnId);
  } catch {
    // It may already be finishing; the stream will say.
  }
  // Cancelling waits on the CLI to exit. Stop waiting if the stream doesn't
  // close on its own.
  clearTimeout(stopTimer);
  stopTimer = setTimeout(() => {
    if (pendingTurnId.value === turnId) completeAnswer(sid, turnId);
  }, 8000);
}

function onComposerEnter(event) {
  // Leave Enter alone while an IME is composing (Chinese input).
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  sendPrompt();
}

function retryFrom(turn) {
  const turns = visibleTurns.value;
  const index = turns.findIndex((row) => row.key === turn.key);
  for (let i = index - (turn.role === "user" ? 0 : 1); i >= 0; i -= 1) {
    if (turns[i].role === "user" && turns[i].text) {
      recordEvent("copilot_retry", {});
      sendPrompt(turns[i].text);
      return;
    }
  }
}

function toggleExpanded(key) {
  const next = new Set(expandedKeys.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedKeys.value = next;
}

async function copyAnswer(turn) {
  try {
    await navigator.clipboard.writeText(turn.body);
    copiedKey.value = turn.key;
    clearTimeout(copiedTimer);
    copiedTimer = setTimeout(() => (copiedKey.value = ""), 1600);
  } catch {
    // Clipboard access can be refused; the text stays selectable.
  }
}

function clearChat() {
  if (busy.value || !props.companyId) return;
  localRows.value = [];
  if (sessionId.value) {
    const marker = { sid: sessionId.value, count: serverTurns.value.length };
    clearedMarker.value = marker;
    writeClearedMarker(props.companyId, marker);
  }
  taskSaved.value = false;
  editApplied.value = false;
  recordEvent("copilot_clear_chat", {});
  nextTick(() => composerEl.value?.focus());
}

function clearFocus() {
  clearCopilotFocus();
}

// Leave a handed-over question in the composer, unsent.
function applyDraft() {
  const value = copilotDraftPrompt.value;
  if (!value || !props.companyId) return;
  prompt.value = value;
  copilotDraftPrompt.value = "";
  nextTick(() => {
    autoGrow();
    composerEl.value?.focus({ preventScroll: true });
  });
}

function runAction(action) {
  recordEvent("copilot_action_click", { action_id: action.id });
  sendPrompt(action.prompt);
}

function runProactive(message) {
  recordEvent("copilot_proactive_click", { action_id: message.action_id });
  sendPrompt(message.prompt);
}

function runStarter(starter) {
  recordEvent("copilot_starter_click", { starter: starter.id });
  sendPrompt(starter.prompt);
}

function runChip(chip) {
  recordEvent("copilot_followup_click", { chip: chip.id });
  sendPrompt(chip.prompt);
}

function openCitation(citation) {
  const target = resolveCitationTarget(citation, indexedFiles.value);
  recordEvent("copilot_citation_click", {
    filename: citation.file,
    page: citation.page,
    resolved: target?.kind || "missing",
  });
  if (target?.kind === "file" && copilotNavigate) {
    copilotNavigate({
      kind: "file",
      companyId: props.companyId,
      file: target.file,
      page: target.page,
    });
    return;
  }
  emit("navigate", { kind: "citation_missing", filename: citation.file });
}

async function applySuggestedEdit() {
  const edit = suggestedEdit.value;
  if (!edit || !props.companyId) return;
  editSaving.value = true;
  try {
    await api.copilot.applyEdit(props.companyId, {
      section_id: edit.section_id,
      card_id: edit.card_id,
      bullet_id: edit.bullet_id,
      text: edit.text,
    });
    editApplied.value = true;
    recordEvent("copilot_edit_applied", { bullet_id: edit.bullet_id });
    if (copilotNavigate) {
      copilotNavigate({
        kind: "memo_bullet",
        companyId: props.companyId,
        sectionId: edit.section_id,
        cardId: edit.card_id,
        bulletId: edit.bullet_id,
      });
    }
  } finally {
    editSaving.value = false;
  }
}

function openNextRoute() {
  const route = nextRoute.value;
  if (!route) return;
  recordEvent("copilot_route_click", { surface: route.surface, tab: route.tab });
  const companyId = props.companyId;
  if (route.surface === "evidence") {
    router.push({
      name: "research",
      params: { companyId },
      query: { tab: "documents", evidence: "1", ...(route.query || {}) },
    });
    return;
  }
  if (route.surface === "jobs") {
    router.push({
      name: "research",
      params: { companyId },
      query: { tab: "jobs", ...(route.query || {}) },
    });
    return;
  }
  router.push({
    name: "research",
    params: { companyId },
    query: {
      tab: route.tab || "memo",
      memoStage: route.memo_stage || "edit",
      ...(route.query || {}),
    },
  });
}

async function acceptProposedTask() {
  const task = proposedTask.value;
  if (!task || !props.companyId) return;
  taskSaving.value = true;
  try {
    await api.copilot.createTask(props.companyId, {
      title: task.title,
      description: task.description || "",
      action_type: task.action_type || "discuss",
      context: {
        ...buildClientContext(),
        ...(task.context || {}),
      },
    });
    taskSaved.value = true;
    recordEvent("copilot_task_accepted", { title: task.title });
  } finally {
    taskSaving.value = false;
  }
}

function switchMode(next) {
  mode.value = next;
  copilotMode.value = next;
}

watch(
  () => props.companyId,
  () => {
    closeAskStream();
    closeHydrateStream();
    finishPending();
    sessionId.value = "";
    serverTurns.value = [];
    localRows.value = [];
    contextPayload.value = null;
    clearedMarker.value = readClearedMarker(props.companyId);
    autoPromptSent.value = false;
    loadContext({ triggerAuto: true });
    if (props.companyId) {
      recordEvent("copilot_inspect_open", { mode: mode.value });
    }
  },
  { immediate: true },
);

watch(
  () => [
    copilotSurface.value,
    copilotTab.value,
    copilotSelection.value,
    copilotAttention.value,
    copilotJob.value,
  ],
  () => {
    if (props.companyId) loadContext();
  },
  { deep: true },
);

watch(
  () => copilotPendingPrompt.value,
  (value) => {
    if (!value) return;
    prompt.value = value;
    copilotPendingPrompt.value = "";
    if (props.companyId && mode.value === "quick") {
      nextTick(() => sendPrompt(value));
    }
  },
);

watch(() => [copilotDraftPrompt.value, props.companyId], applyDraft);

watch(
  () => copilotMode.value,
  (value) => {
    if (value && value !== mode.value) mode.value = value;
  },
);

watch(
  [busy, () => visibleTurns.value.length, mode],
  ([isBusy, count, currentMode]) => {
    emit("state", { busy: isBusy, hasTurns: count > 0, mode: currentMode });
  },
  { immediate: true },
);

onMounted(() => {
  // Ready to type on desktop; phones keep the keyboard down until asked.
  if (props.companyId && window.matchMedia?.("(pointer: fine)").matches) {
    composerEl.value?.focus({ preventScroll: true });
  }
  applyDraft();
});

onBeforeUnmount(() => {
  closeAskStream();
  closeHydrateStream();
  clearTimeout(recoverTimer);
  clearTimeout(stopTimer);
  clearTimeout(copiedTimer);
});

defineExpose({
  sendPrompt,
  runAction,
  buildDiscussPrompt,
  clearChat,
});
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <!-- No company yet: Warren needs one to read. -->
    <div v-if="!companyId" class="min-h-0 flex-1 overflow-y-auto">
      <div class="warren-hero">
        <WarrenMark :size="56" />
        <h3 class="mt-3 text-headline text-ink-primary">{{ t("copilot.title") }}</h3>
        <p class="mx-auto mt-1 max-w-[18rem] text-footnote leading-relaxed text-ink-muted">
          {{ suggestedCompanies.length ? t("copilot.choose_company_body") : t("copilot.no_companies") }}
        </p>
      </div>
      <div v-if="suggestedCompanies.length" class="mt-5 space-y-1.5">
        <div class="vogue-label px-1">{{ t("copilot.choose_company") }}</div>
        <button
          v-for="company in suggestedCompanies"
          :key="company.id"
          type="button"
          class="ask-suggestion focus-ring"
          @click="emit('choose-company', company.id)"
        >
          <Monogram :company="company" :size="24" tinted />
          <span class="min-w-0 flex-1 truncate text-subheadline font-medium text-ink-primary">
            {{ company.name }}
          </span>
          <span
            v-if="company.ticker"
            class="shrink-0 text-caption1 font-medium text-ink-muted"
          >
            {{ company.ticker }}
          </span>
        </button>
      </div>
    </div>

    <template v-else>
      <div class="segmented mb-3 w-full shrink-0">
        <button
          type="button"
          class="segmented-item focus-ring flex-1"
          :data-selected="mode === 'quick' ? 'true' : 'false'"
          :title="t('copilot.mode_quick_hint')"
          @click="switchMode('quick')"
        >
          {{ t("copilot.mode_quick") }}
        </button>
        <button
          type="button"
          class="segmented-item focus-ring flex-1"
          :data-selected="mode === 'deep' ? 'true' : 'false'"
          :title="t('copilot.mode_deep_hint')"
          @click="switchMode('deep')"
        >
          {{ t("copilot.mode_deep") }}
        </button>
      </div>

      <div v-if="mode === 'deep'" class="min-h-0 flex-1">
        <CompanyConsole :company-id="companyId" class="min-h-0 flex-1" />
      </div>

      <template v-else>
        <div
          ref="transcriptEl"
          class="ask-transcript relative -mx-2 min-h-0 flex-1 space-y-5 overflow-y-auto px-2"
        >
          <!-- Source trail for a claim dragged onto Warren. -->
          <div v-if="provenance" class="warren-card">
            <div class="text-footnote font-semibold text-ink-primary">
              {{ t("copilot.provenance_title") }}
            </div>
            <p class="mt-0.5 text-caption1 text-ink-muted">{{ provenance.label }}</p>
            <div v-if="provenanceSources.length" class="mt-2 space-y-1">
              <div class="text-caption1 font-semibold text-ink-muted">
                {{ t("copilot.provenance_sources") }}
              </div>
              <button
                v-for="(source, index) in provenanceSources"
                :key="`${source.file_id || source.filename}-${index}`"
                type="button"
                class="block w-full rounded-[9px] px-2 py-1.5 text-left text-caption1 text-ink-secondary hover:bg-ink-primary/[0.05] focus-ring"
                @click="openCitation({ file: source.filename, page: source.locator || '1' })"
              >
                <span class="font-medium text-ink-primary">
                  {{ source.filename || source.file_id || t("copilot.provenance_source") }}
                </span>
                <span v-if="source.locator" class="ml-1 text-ink-muted">· {{ source.locator }}</span>
                <span v-if="source.excerpt" class="mt-0.5 block line-clamp-2">{{ source.excerpt }}</span>
              </button>
            </div>
            <div v-if="provenanceContradictions.length" class="mt-2 space-y-1">
              <div class="text-caption1 font-semibold text-ink-muted">
                {{ t("copilot.provenance_contradictions") }}
              </div>
              <p
                v-for="(row, index) in provenanceContradictions"
                :key="`contra-${index}`"
                class="text-caption1 text-warning-ink"
              >
                {{ row.excerpt || row.filename || row.locator }}
              </p>
            </div>
            <div v-if="provenanceGaps.length" class="mt-2 space-y-1">
              <div class="text-caption1 font-semibold text-ink-muted">
                {{ t("copilot.provenance_gaps") }}
              </div>
              <p
                v-for="(gap, index) in provenanceGaps"
                :key="`gap-${index}`"
                class="text-caption1 text-ink-muted"
              >
                {{ gap }}
              </p>
            </div>
            <p
              v-if="!provenanceSources.length && !provenanceGaps.length"
              class="mt-2 text-caption1 text-ink-muted"
            >
              {{ t("copilot.provenance_empty") }}
            </p>
          </div>

          <!-- Empty chat: who Warren is and what to ask him. -->
          <div v-if="showHero" class="pb-2">
            <div class="warren-hero">
              <WarrenMark :size="56" />
              <h3 class="mt-3 text-headline text-ink-primary">
                {{ t("copilot.hero_title", { company: companyLabel }) }}
              </h3>
              <p class="mx-auto mt-1 max-w-[19rem] text-footnote leading-relaxed text-ink-muted">
                {{ t("copilot.hero_subtitle") }}
              </p>
            </div>

            <div v-if="proactiveMessages.length" class="mt-5 space-y-1.5">
              <button
                v-for="message in proactiveMessages"
                :key="message.action_id"
                type="button"
                class="ask-suggestion focus-ring"
                data-tone="warning"
                @click="runProactive(message)"
              >
                <AlertTriangle class="h-3.5 w-3.5 shrink-0 text-warning" />
                <span class="min-w-0 flex-1 text-subheadline text-ink-primary">{{ message.label }}</span>
                <ArrowUpRight class="h-3.5 w-3.5 shrink-0 text-ink-subtle" />
              </button>
            </div>

            <section v-if="focusLabel && actions.length" class="mt-5 space-y-1.5">
              <div class="vogue-label truncate px-1">
                {{ t("copilot.section_about", { label: focusLabel }) }}
              </div>
              <button
                v-for="action in actions"
                :key="action.id"
                type="button"
                class="ask-suggestion focus-ring"
                @click="runAction(action)"
              >
                <Sparkles class="h-3.5 w-3.5 shrink-0 text-accent" />
                <span class="min-w-0 flex-1 text-subheadline text-ink-primary">{{ action.label }}</span>
                <ArrowUpRight class="h-3.5 w-3.5 shrink-0 text-ink-subtle" />
              </button>
            </section>

            <section class="mt-5 space-y-1.5">
              <div class="vogue-label px-1">{{ t("copilot.suggested") }}</div>
              <button
                v-for="starter in starters"
                :key="starter.id"
                type="button"
                class="ask-suggestion focus-ring"
                @click="runStarter(starter)"
              >
                <MessageSquareText class="h-3.5 w-3.5 shrink-0 text-accent" />
                <span class="min-w-0 flex-1 text-subheadline text-ink-primary">{{ starter.prompt }}</span>
              </button>
            </section>

            <section v-if="!focusLabel && actions.length" class="mt-5">
              <div class="vogue-label px-1">{{ t("copilot.section_desk") }}</div>
              <div class="mt-1.5 flex flex-wrap gap-1.5">
                <button
                  v-for="action in actions"
                  :key="action.id"
                  type="button"
                  class="ask-chip focus-ring"
                  @click="runAction(action)"
                >
                  {{ action.label }}
                </button>
              </div>
            </section>

            <p v-if="contextError" class="mt-4 px-1 text-caption1 text-danger">{{ contextError }}</p>
          </div>

          <template v-for="turn in visibleTurns" :key="turn.key">
            <!-- The analyst asks in a tinted bubble on the right... -->
            <div v-if="turn.role === 'user'" class="flex flex-col items-end pl-10" data-turn-role="user">
              <div class="ask-bubble">
                <!-- Clamp inside the padding so a cut line never peeks out. -->
                <div :class="turn.long && !expandedKeys.has(turn.key) ? 'line-clamp-6' : ''">{{ turn.text }}</div>
              </div>
              <button
                v-if="turn.long"
                type="button"
                class="warren-action mt-0.5"
                @click="toggleExpanded(turn.key)"
              >
                {{ expandedKeys.has(turn.key) ? t("copilot.show_less") : t("copilot.show_more") }}
              </button>
              <button
                v-if="turn.key === latestTurn?.key && !busy"
                type="button"
                class="warren-action mt-1"
                @click="retryFrom(turn)"
              >
                <RotateCcw class="h-3 w-3" />
                {{ t("copilot.retry") }}
              </button>
            </div>

            <!-- ...and Warren answers as a page on the left, under his portrait. -->
            <article
              v-else
              class="warren-answer"
              data-turn-role="assistant"
              :data-latest="turn.key === latestAnswer?.key ? 'true' : 'false'"
            >
              <header class="flex items-center gap-2">
                <WarrenMark :size="22" />
                <span class="text-footnote font-semibold text-ink-primary">{{ t("copilot.ask_short") }}</span>
                <span v-if="turn.time" class="text-caption1 text-ink-subtle">{{ turn.time }}</span>
              </header>
              <div class="pl-[30px]">
                <div v-if="turn.html" class="warren-md md-body mt-1" v-html="turn.html" />
                <p v-if="turn.stopped" class="mt-1 text-caption1 text-ink-muted">
                  {{ t("copilot.stopped") }}
                </p>
                <div v-else-if="turn.failed" class="warren-error mt-1.5">
                  <AlertTriangle class="mt-px h-3.5 w-3.5 shrink-0 text-warning" />
                  <span class="min-w-0 flex-1 break-words">{{ turn.error }}</span>
                </div>

                <template v-if="turn.key === latestAnswer?.key && !turn.failed">
                  <div v-if="latestCitations.length" class="mt-2.5 flex flex-wrap gap-1.5">
                    <button
                      v-for="cite in latestCitations"
                      :key="cite.label"
                      type="button"
                      class="warren-cite focus-ring"
                      @click="openCitation(cite)"
                    >
                      <FileText class="h-3 w-3 shrink-0" />
                      <span class="truncate">{{ cite.label }}</span>
                    </button>
                  </div>

                  <div v-if="contradiction" class="warren-card mt-2.5" data-tone="warning">
                    <div class="text-footnote font-semibold text-ink-primary">
                      {{ t("copilot.contradiction_title") }}
                    </div>
                    <p class="mt-1 text-caption1 leading-relaxed text-ink-secondary">{{ contradiction.claim }}</p>
                    <p v-if="contradiction.resolution" class="mt-1 text-caption1 text-ink-muted">
                      {{ contradiction.resolution }}
                    </p>
                  </div>

                  <div v-if="suggestedEdit" class="warren-card mt-2.5">
                    <div class="text-footnote font-semibold text-ink-primary">
                      {{ t("copilot.suggested_edit") }}
                    </div>
                    <p class="mt-1 text-caption1 leading-relaxed text-ink-secondary">{{ suggestedEdit.text }}</p>
                    <button
                      type="button"
                      class="btn-filled btn-sm mt-2 focus-ring"
                      :disabled="editSaving || editApplied"
                      @click="applySuggestedEdit"
                    >
                      {{ editApplied ? t("copilot.edit_applied") : t("copilot.apply_edit") }}
                    </button>
                  </div>

                  <div v-if="proposedTask" class="warren-card mt-2.5">
                    <div class="flex items-start gap-2">
                      <ScrollText class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-ink" />
                      <div class="min-w-0 flex-1">
                        <div class="text-footnote font-semibold text-ink-primary">{{ proposedTask.title }}</div>
                        <p v-if="proposedTask.description" class="mt-1 text-caption1 text-ink-muted">
                          {{ proposedTask.description }}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      class="btn-filled btn-sm mt-2 focus-ring"
                      :disabled="taskSaving || taskSaved"
                      @click="acceptProposedTask"
                    >
                      {{ taskSaved ? t("copilot.task_added") : t("copilot.add_task") }}
                    </button>
                  </div>

                  <button
                    v-if="nextRoute"
                    type="button"
                    class="btn-bordered btn-sm mt-2.5 focus-ring"
                    @click="openNextRoute"
                  >
                    {{ t("copilot.open_route") }}
                  </button>
                </template>

                <div class="warren-answer-actions">
                  <button
                    v-if="turn.body"
                    type="button"
                    class="warren-action focus-ring"
                    @click="copyAnswer(turn)"
                  >
                    <Check v-if="copiedKey === turn.key" class="h-3 w-3" />
                    <Copy v-else class="h-3 w-3" />
                    {{ copiedKey === turn.key ? t("copilot.copied") : t("copilot.copy") }}
                  </button>
                  <button
                    v-if="turn.key === latestAnswer?.key && !busy"
                    type="button"
                    class="warren-action focus-ring"
                    @click="retryFrom(turn)"
                  >
                    <RotateCcw class="h-3 w-3" />
                    {{ t("copilot.retry") }}
                  </button>
                </div>
              </div>
            </article>
          </template>

          <!-- Warren at work: "Buffetting…" until the answer lands. -->
          <article v-if="busy" class="warren-answer" data-turn-role="pending">
            <header class="flex items-center gap-2">
              <WarrenMark :size="22" busy />
              <span class="text-footnote font-semibold text-ink-primary">{{ t("copilot.ask_short") }}</span>
              <span class="warren-status" role="status">
                {{ stopping ? t("copilot.stopping") : t("copilot.thinking") }}
              </span>
            </header>
            <div class="pl-[30px]">
              <div v-if="pendingHtml" class="warren-md md-body mt-1" v-html="pendingHtml" />
              <p v-if="pendingActivity" class="mt-1 truncate text-caption1 text-ink-muted">
                {{ pendingActivity }}
              </p>
            </div>
          </article>

          <div v-if="nextChips.length" class="flex flex-wrap gap-1.5 pl-[30px]">
            <button
              v-for="chip in nextChips"
              :key="chip.id"
              type="button"
              class="ask-chip focus-ring"
              :data-tone="chip.tone || undefined"
              @click="runChip(chip)"
            >
              {{ chip.label }}
            </button>
          </div>
        </div>

        <div class="shrink-0 pt-2.5">
          <div
            v-if="seesLabel || hydrationNote"
            class="mb-2 flex min-w-0 items-center gap-2 px-0.5"
          >
            <span v-if="seesLabel" class="warren-context" :title="t('copilot.context_aware')">
              <Crosshair class="h-3 w-3 shrink-0" />
              <span class="truncate">{{ seesLabel }}</span>
              <button
                v-if="focusLabel"
                type="button"
                class="warren-context-clear focus-ring"
                :aria-label="t('copilot.clear_context')"
                :title="t('copilot.clear_context')"
                @click="clearFocus"
              >
                <X class="h-2.5 w-2.5" />
              </button>
            </span>
            <span v-if="hydrationNote" class="truncate text-caption1 text-ink-muted">{{ hydrationNote }}</span>
          </div>
          <form class="ask-composer" @submit.prevent="sendPrompt()">
            <textarea
              ref="composerEl"
              v-model="prompt"
              rows="1"
              class="ask-composer-input"
              :placeholder="placeholder"
              :aria-label="t('copilot.input_placeholder')"
              @input="autoGrow"
              @keydown.enter.exact="onComposerEnter"
            />
            <button
              v-if="busy"
              type="button"
              class="ask-send focus-ring"
              data-stop="true"
              :disabled="!pendingTurnId || stopping"
              :aria-label="t('copilot.stop')"
              :title="t('copilot.stop')"
              @click="stopAnswer"
            >
              <Square class="h-3 w-3 fill-current" />
            </button>
            <button
              v-else
              type="submit"
              class="ask-send focus-ring"
              :data-ready="prompt.trim() ? 'true' : 'false'"
              :disabled="!prompt.trim()"
              :aria-label="t('copilot.send')"
              :title="t('copilot.send')"
            >
              <ArrowUp class="h-4 w-4" />
            </button>
          </form>
          <p class="mt-1.5 px-1 text-caption2 text-ink-subtle max-sm:hidden">
            {{ t("copilot.enter_hint") }}
          </p>
        </div>
      </template>
    </template>
  </div>
</template>
