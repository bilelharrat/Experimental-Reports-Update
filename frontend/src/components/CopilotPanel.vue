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
  FolderInput,
  Loader2,
  MessageSquareText,
  Paperclip,
  Pencil,
  Play,
  RotateCcw,
  ScrollText,
  Sparkles,
  Square,
  X,
} from "lucide-vue-next";
import WarrenMark from "./WarrenMark.vue";
import Monogram from "./Monogram.vue";
import { api } from "../api.js";
import { sessionEmail } from "../auth.js";
import { refreshActiveJobs } from "../activeJobs.js";
import { toggleTrackedCompany, trackedCompanyIds } from "../state.js";
import {
  buildDiscussPrompt,
  extractCitations,
  followUpChips,
  normalizeWork,
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
import { ATTACHMENT_ACCEPT, validateAttachment } from "../console.js";
import { renderMarkdown } from "../markdown.js";
import { formatModelName } from "../formatters.js";
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
// The customizer is mounted at app level; the panel just asks for it.
const openReportCustomizer = inject("openReportCustomizer", null);

// A thread belongs to the company, not to a browser. An older release
// hid turns behind this key, which meant two people on the same desk saw
// two different conversations; it is cleared on sight now.
const LEGACY_CLEARED_KEY = "bsh.warren.cleared";
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
// Earlier threads: the list, and the one being read if it isn't the
// current one.
const historyOpen = ref(false);
const threads = ref([]);
const threadsLoading = ref(false);
const threadError = ref("");
const startingThread = ref(false);
const viewingThreadId = ref("");
const viewingTurns = ref([]);
const copiedKey = ref("");
// Long handed-over questions (a market packet) open collapsed.
const expandedKeys = ref(new Set());
const taskSaving = ref(false);
const taskSaved = ref(false);
const editSaving = ref(false);
const editApplied = ref(false);
const transcriptEl = ref(null);
const composerEl = ref(null);

// Files going with the next question. Each is staged beside Warren's session
// as it is picked, so one he cannot open is refused while the analyst is
// still at the composer rather than after they press send.
const attachments = ref([]);
const attachInput = ref(null);
const attachError = ref("");
const fileDragOver = ref(false);
let attachSeq = 0;

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

const viewingThread = computed(
  () => threads.value.find((row) => row.id === viewingThreadId.value) || null,
);

function formatTime(ts) {
  if (!ts) return "";
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// Who answered, when it was not the usual Claude: a stand-in names itself and
// says why the first engine could not answer, so it never passes for Claude.
function engineNote(turn) {
  const engine = String(turn.engine || "");
  if (!engine || (engine === "claude" && !turn.fallback_reason)) return "";
  const model = formatModelName(turn.model) || t(`copilot.engine_${engine}`);
  if (!turn.fallback_reason) return t("copilot.answered_by", { model });
  const other = engine === "gemini" ? "claude" : "gemini";
  return t("copilot.answered_instead", {
    model,
    other: t(`copilot.engine_${other}`),
    reason: turn.fallback_reason,
  });
}

function viewTurn(turn, index) {
  const role = turn.role === "user" ? "user" : "assistant";
  const key = `${role}-${turn.id || "row"}-${index}`;
  if (role === "user") {
    const text = String(turn.text || "");
    // The thread is shared, so a question asked by someone else is
    // signed. Your own needs no byline — you were there.
    const author = turn.author && typeof turn.author === "object" ? turn.author : null;
    const email = String(author?.email || "");
    const mine = !email || email === (sessionEmail.value || "");
    return {
      key,
      role,
      id: turn.id,
      text,
      author: mine ? "" : String(author?.name || "") || email.split("@")[0],
      edited: Boolean(turn.edits),
      files: (turn.attachments || []).map((item) => String(item?.name || "")).filter(Boolean),
      long: text.length > 320 || text.split("\n").length > 6,
    };
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
    engineNote: engineNote(turn),
    time: formatTime(turn.ts),
  };
}

const visibleTurns = computed(() => {
  if (viewingThreadId.value) return viewingTurns.value.map(viewTurn);
  const rows = serverTurns.value.filter(
    (row) => !supersededIds.value.has(row.id),
  );
  const question = pendingQuestion.value;
  const recorded =
    question?.turnId && rows.some((row) => row.role === "user" && row.id === question.turnId);
  const extra =
    question && !recorded
      ? [
          {
            role: "user",
            id: "pending",
            text: question.text,
            attachments: (question.files || []).map((name) => ({ name })),
          },
        ]
      : [];
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
// Work Warren has offered to start. He proposes; the analyst confirms.
const proposedWork = computed(() => normalizeWork(structuredOutputs.value.run_work));
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

function forgetLegacyClearedChats() {
  try {
    window.localStorage.removeItem(LEGACY_CLEARED_KEY);
  } catch {
    // Private windows refuse storage; nothing was hidden there anyway.
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
      } else if (entry.action === "fallback") {
        // The first engine could not answer; what it streamed was its own
        // error ("You've hit your weekly limit…"), not the answer.
        pendingText.value = "";
        pendingActivity.value = t("copilot.activity_fallback", {
          engine: t(`copilot.engine_${entry.engine === "claude" ? "claude" : "gemini"}`),
        });
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

// ---- Files attached to a question --------------------------------------

// Ready to send: staged on the server and not refused.
const readyAttachments = computed(() =>
  attachments.value.filter((item) => item.storedName && !item.error),
);
const attachBusy = computed(() => attachments.value.some((item) => item.staging));

function attachMessage(error) {
  const code = error?.detail?.detail?.code;
  if (code === "attachment_too_large") return t("console.error_attachment_too_large");
  if (code === "attachment_type_not_allowed") return t("console.error_attachment_type");
  if (code === "attachment_unreadable")
    return error?.detail?.detail?.message || t("console.error_attachment_unreadable");
  return error?.message || t("copilot.attach_failed");
}

function pickFiles() {
  attachError.value = "";
  attachInput.value?.click();
}

function onFilesPicked(event) {
  const files = Array.from(event.target?.files || []);
  if (event.target) event.target.value = "";
  for (const file of files) stageFile(file);
}

async function stageFile(file) {
  if (!props.companyId) {
    attachError.value = t("copilot.attach_needs_company");
    return;
  }
  const problem = validateAttachment(file);
  if (problem) {
    attachError.value = t(problem.key);
    return;
  }
  attachError.value = "";
  attachments.value.push({
    key: `attachment-${++attachSeq}`,
    name: file.name,
    file,
    storedName: "",
    staging: true,
    saving: false,
    savedId: "",
    error: "",
  });
  // Through the array, so mutations below reach the template.
  const entry = attachments.value[attachments.value.length - 1];
  const companyId = props.companyId;
  try {
    const record = await api.copilot.attach(companyId, file, mode.value);
    if (companyId !== props.companyId) return;
    entry.storedName = record.stored_name;
  } catch (e) {
    entry.error = attachMessage(e);
  } finally {
    entry.staging = false;
  }
}

function removeAttachment(key) {
  attachments.value = attachments.value.filter((item) => item.key !== key);
  attachError.value = "";
}

// The chat copy is Warren's to read for this session. Saving files it under
// the company, where the Files tab lists it and a memo run can read it.
async function saveAttachmentToFiles(entry) {
  if (!props.companyId || entry.saving || entry.savedId) return;
  entry.saving = true;
  entry.error = "";
  try {
    const record = await api.uploadResearchFile(props.companyId, entry.file);
    entry.savedId = String(record?.id || "saved");
    recordEvent("copilot_attachment_saved", { name: entry.name });
  } catch (e) {
    entry.error = attachMessage(e);
  } finally {
    entry.saving = false;
  }
}

function onComposerDragOver(event) {
  // Only for files; the drag-tell lens carries its own MIME.
  if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
  event.preventDefault();
  fileDragOver.value = true;
}

function onComposerDrop(event) {
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length) return;
  event.preventDefault();
  fileDragOver.value = false;
  for (const file of files) stageFile(file);
}

async function sendPrompt(text, { edits = "" } = {}) {
  const value = String(text || prompt.value || "").trim();
  if (!value || !props.companyId || busy.value || attachBusy.value) return;
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
  workState.value = "";
  workError.value = "";
  workNote.value = "";
  localRows.value = [];
  if (!text || value === prompt.value.trim()) prompt.value = "";
  nextTick(autoGrow);
  const files = readyAttachments.value;
  const fileNames = files.map((item) => item.name);
  pendingQuestion.value = { text: value, turnId: null, files: fileNames };
  scrollToBottom({ force: true });
  try {
    const payload = await api.copilot.ask(companyId, {
      prompt: value,
      context: buildClientContext(),
      output_language: appLanguage.value === "zh" ? "zh" : "en",
      mode: mode.value,
      attachments: files.map((item) => item.storedName),
      attachment_names: Object.fromEntries(
        files.map((item) => [item.storedName, item.name]),
      ),
      ...(edits ? { edits } : {}),
    });
    if (companyId !== props.companyId) return;
    // The turn carries them now; the composer starts clean.
    attachments.value = [];
    attachError.value = "";
    sessionId.value = payload.session_id;
    pendingQuestion.value = { text: value, turnId: payload.turn_id, files: fileNames };
    if (payload.hydrate_stream_url && payload.hydration_status === "in_progress") {
      openHydrateStream(payload.session_id);
    }
    openAskStream(payload.session_id, payload.turn_id);
  } catch (e) {
    pendingQuestion.value = null;
    if (edits) {
      const back = new Set(supersededIds.value);
      back.delete(edits);
      supersededIds.value = back;
    }
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

// ---- Editing a question already sent ----------------------------------
// Re-asking with a pointer to what it replaces: the server drops the old
// question and its answer from the thread everyone reads, so the team
// does not work from a version that has been corrected.

const editingKey = ref("");
const editDraft = ref("");
const editEl = ref(null);
// Hidden here the moment the edit is sent, so the old pair does not
// linger until the next poll catches up with the server.
const supersededIds = ref(new Set());

// The textarea lives inside the v-for, so Vue hands back an array even
// though only the row being edited renders one.
function editBox() {
  const el = editEl.value;
  return Array.isArray(el) ? el[0] : el;
}

function startEdit(turn) {
  if (busy.value || !turn.id || turn.id === "pending") return;
  editingKey.value = turn.key;
  editDraft.value = turn.text;
  nextTick(() => {
    const el = editBox();
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
    growEdit();
  });
}

function cancelEdit() {
  editingKey.value = "";
  editDraft.value = "";
}

function growEdit() {
  const el = editBox();
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
}

function saveEdit(turn) {
  const next = editDraft.value.trim();
  if (!next || next === String(turn.text || "").trim()) {
    cancelEdit();
    return;
  }
  const replaced = turn.id;
  cancelEdit();
  recordEvent("copilot_edit_question", {});
  supersededIds.value = new Set([...supersededIds.value, replaced]);
  sendPrompt(next, { edits: replaced });
}

function onEditKey(event, turn) {
  if (event.key === "Escape") {
    event.preventDefault();
    cancelEdit();
    return;
  }
  // Same contract as the composer: Enter sends, Shift+Enter breaks a line.
  if (event.key === "Enter" && !event.shiftKey) {
    if (event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    saveEdit(turn);
  }
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

// ---- Threads ----------------------------------------------------------

async function newThread() {
  if (busy.value || startingThread.value || !props.companyId) return;
  const companyId = props.companyId;
  startingThread.value = true;
  threadError.value = "";
  try {
    const payload = await api.copilot.startThread(companyId, { mode: mode.value });
    if (companyId !== props.companyId) return;
    sessionId.value = payload.session_id;
    serverTurns.value = [];
    localRows.value = [];
    supersededIds.value = new Set();
    threads.value = [];
    viewingThreadId.value = "";
    viewingTurns.value = [];
    historyOpen.value = false;
    taskSaved.value = false;
    editApplied.value = false;
    recordEvent("copilot_new_thread", {});
    nextTick(() => composerEl.value?.focus());
  } catch (e) {
    threadError.value = e?.message || t("copilot.thread_failed");
  } finally {
    startingThread.value = false;
  }
}

async function loadThreads() {
  if (!props.companyId) return;
  const companyId = props.companyId;
  threadsLoading.value = true;
  threadError.value = "";
  try {
    const rows = await api.copilot.threads(companyId, mode.value);
    if (companyId !== props.companyId) return;
    threads.value = Array.isArray(rows) ? rows : [];
  } catch (e) {
    threads.value = [];
    threadError.value = e?.message || t("copilot.thread_failed");
  } finally {
    threadsLoading.value = false;
  }
}

function toggleHistory() {
  if (!props.companyId) return;
  historyOpen.value = !historyOpen.value;
  if (historyOpen.value) {
    recordEvent("copilot_history_open", {});
    loadThreads();
  }
}

async function openThread(thread) {
  historyOpen.value = false;
  if (!thread || thread.active) {
    backToCurrentThread();
    return;
  }
  const companyId = props.companyId;
  viewingThreadId.value = thread.id;
  viewingTurns.value = [];
  recordEvent("copilot_history_open_thread", {});
  try {
    const rows = await api.console.getTurns(companyId, thread.id);
    if (companyId !== props.companyId || viewingThreadId.value !== thread.id) return;
    viewingTurns.value = Array.isArray(rows) ? rows : [];
  } catch (e) {
    threadError.value = e?.message || t("copilot.thread_failed");
  }
}

function backToCurrentThread() {
  viewingThreadId.value = "";
  viewingTurns.value = [];
  historyOpen.value = false;
}

function threadWhen(thread) {
  const stamp = thread?.last_at || thread?.started_at;
  if (!stamp) return "";
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
  });
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
  // The desk's Files tab is where the evidence lives.
  if (route.surface === "evidence") {
    router.push({
      name: "research",
      params: { companyId },
      query: { section: "files", ...(route.query || {}) },
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
  // His tab names (memo, documents…) are the ones the desk maps; a section
  // he names opens Memo Studio there.
  router.push({
    name: "research",
    params: { companyId },
    query: {
      tab: route.tab || "memo",
      ...(route.section_id ? { memoSection: route.section_id } : {}),
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

// ---- Starting work Warren offered -------------------------------------

const workState = ref("");      // "" | "running" | "started"
const workError = ref("");
const workNote = ref("");

async function confirmWork() {
  const work = proposedWork.value;
  if (!work || !props.companyId || workState.value) return;
  const companyId = props.companyId;
  workState.value = "running";
  workError.value = "";
  workNote.value = "";
  try {
    if (work.kind === "report") {
      const job = await api.generateReport({
        company_id: companyId,
        ...work.options,
        // An empty engine means "whatever Settings says".
        ...(work.options.engine ? {} : { engine: undefined }),
      });
      workNote.value = t("copilot.work_report_started", {
        type: work.options.report_type,
      });
      if (job?.report_id) refreshActiveJobs();
    } else if (work.kind === "document_analysis") {
      await api.analyzeResearchFile(companyId, work.options.file_id);
      workNote.value = t("copilot.work_analysis_started", {
        file: work.options.file_name || work.title,
      });
      refreshActiveJobs();
    } else if (work.kind === "decision") {
      await api.decisionRecords.add(companyId, {
        verdict: work.options.verdict,
        explanation: work.options.explanation,
      });
      workNote.value = t("copilot.work_decision_recorded");
    } else if (work.kind === "follow") {
      // Idempotent: confirming twice should not unfollow.
      if (!trackedCompanyIds.value.has(String(companyId))) {
        toggleTrackedCompany(companyId);
      }
      workNote.value = t("copilot.work_following", {
        company: props.companyName || companyId,
      });
    }
    workState.value = "started";
    recordEvent("copilot_work_started", { kind: work.kind });
  } catch (e) {
    workState.value = "";
    workError.value = e?.message || t("copilot.work_failed");
  }
}

function openWorkOptions() {
  const work = proposedWork.value;
  if (!work || work.kind !== "report") return;
  recordEvent("copilot_work_options", { kind: work.kind });
  // The customizer opens on this company; Warren's choices are a
  // starting point, not a lock-in.
  openReportCustomizer?.(props.companyId);
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
    forgetLegacyClearedChats();
    threads.value = [];
    historyOpen.value = false;
    viewingThreadId.value = "";
    viewingTurns.value = [];
    supersededIds.value = new Set();
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
  newThread,
  toggleHistory,
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
        <!-- Earlier threads, in place of the transcript while open. -->
        <div v-if="historyOpen" class="-mx-2 min-h-0 flex-1 overflow-y-auto px-2">
          <div class="flex items-center justify-between px-1 pb-2 pt-1">
            <div class="text-footnote font-semibold text-ink-primary">
              {{ t("copilot.history_title") }}
            </div>
            <button type="button" class="warren-action" @click="toggleHistory">
              <X class="h-3 w-3" />
              {{ t("copilot.history_close") }}
            </button>
          </div>
          <p class="px-1 pb-2 text-caption1 text-ink-muted">
            {{ t("copilot.history_shared") }}
          </p>
          <p v-if="threadsLoading" class="px-1 py-3 text-caption1 text-ink-muted">
            {{ t("common.loading") }}
          </p>
          <p v-else-if="!threads.length" class="px-1 py-3 text-caption1 text-ink-muted">
            {{ t("copilot.history_empty") }}
          </p>
          <div v-else class="space-y-1">
            <button
              v-for="thread in threads"
              :key="thread.id"
              type="button"
              class="warren-thread focus-ring"
              :data-current="thread.active ? 'true' : 'false'"
              @click="openThread(thread)"
            >
              <div class="flex items-baseline justify-between gap-2">
                <span class="truncate text-footnote text-ink-primary">
                  {{ thread.opening_question || t("copilot.history_no_questions") }}
                </span>
                <span class="shrink-0 text-caption2 text-ink-subtle">{{ threadWhen(thread) }}</span>
              </div>
              <div class="mt-0.5 flex items-center gap-1.5 text-caption2 text-ink-subtle">
                <span v-if="thread.active" class="text-accent-ink">{{ t("copilot.history_current") }}</span>
                <span>{{ t("copilot.history_questions", { count: thread.question_count }) }}</span>
                <span v-if="thread.askers?.length" class="truncate">· {{ thread.askers.join(", ") }}</span>
              </div>
            </button>
          </div>
          <p v-if="threadError" class="px-1 pt-2 text-caption1 text-danger">{{ threadError }}</p>
        </div>
        <div
          v-show="!historyOpen"
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
            <div
              v-if="turn.role === 'user'"
              class="warren-question flex flex-col items-end pl-10"
              data-turn-role="user"
            >
              <!-- Rewriting a question in place, where it was asked. -->
              <form
                v-if="editingKey === turn.key"
                class="ask-edit"
                @submit.prevent="saveEdit(turn)"
              >
                <textarea
                  ref="editEl"
                  v-model="editDraft"
                  rows="2"
                  class="ask-edit-input"
                  :aria-label="t('copilot.edit_question')"
                  @input="growEdit"
                  @keydown="onEditKey($event, turn)"
                />
                <div class="mt-1.5 flex items-center justify-end gap-1">
                  <button type="button" class="warren-action" @click="cancelEdit">
                    {{ t("common.cancel") }}
                  </button>
                  <button
                    type="submit"
                    class="btn-filled btn-sm focus-ring"
                    :disabled="!editDraft.trim()"
                  >
                    {{ t("copilot.save_and_ask") }}
                  </button>
                </div>
              </form>
              <template v-else>
                <div class="ask-bubble">
                  <!-- Clamp inside the padding so a cut line never peeks out. -->
                  <div :class="turn.long && !expandedKeys.has(turn.key) ? 'line-clamp-6' : ''">{{ turn.text }}</div>
                  <div v-if="turn.files?.length" class="mt-1.5 flex flex-wrap justify-end gap-1">
                    <span v-for="name in turn.files" :key="name" class="warren-file" :title="name">
                      <Paperclip class="h-2.5 w-2.5 shrink-0" />
                      <span class="truncate">{{ name }}</span>
                    </span>
                  </div>
                </div>
                <div v-if="turn.author || turn.edited" class="warren-byline">
                  <span v-if="turn.author">{{ turn.author }}</span>
                  <span v-if="turn.author && turn.edited" aria-hidden="true">·</span>
                  <span v-if="turn.edited">{{ t("copilot.edited") }}</span>
                </div>
                <button
                  v-if="turn.long"
                  type="button"
                  class="warren-action mt-0.5"
                  @click="toggleExpanded(turn.key)"
                >
                  {{ expandedKeys.has(turn.key) ? t("copilot.show_less") : t("copilot.show_more") }}
                </button>
                <div class="warren-question-actions">
                  <button
                    v-if="turn.id && turn.id !== 'pending' && !busy"
                    type="button"
                    class="warren-action"
                    @click="startEdit(turn)"
                  >
                    <Pencil class="h-3 w-3" />
                    {{ t("copilot.edit_question") }}
                  </button>
                  <button
                    v-if="turn.key === latestTurn?.key && !busy"
                    type="button"
                    class="warren-action"
                    @click="retryFrom(turn)"
                  >
                    <RotateCcw class="h-3 w-3" />
                    {{ t("copilot.retry") }}
                  </button>
                </div>
              </template>
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
                <p
                  v-if="turn.engineNote && !turn.failed"
                  class="mt-1.5 text-caption1 text-ink-muted"
                  data-testid="warren-engine-note"
                >
                  {{ turn.engineNote }}
                </p>
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

                  <!-- Work Warren offered to start. He never starts it
                       himself: this is where the analyst spends the money. -->
                  <div v-if="proposedWork" class="warren-card warren-work mt-2.5">
                    <div class="flex items-start gap-2">
                      <Play class="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-ink" />
                      <div class="min-w-0 flex-1">
                        <div class="text-footnote font-semibold text-ink-primary">
                          {{ proposedWork.title }}
                        </div>
                        <p v-if="proposedWork.why" class="mt-1 text-caption1 text-ink-muted">
                          {{ proposedWork.why }}
                        </p>
                        <p
                          v-if="proposedWork.kind === 'report'"
                          class="mt-1 text-caption2 text-ink-subtle"
                        >
                          {{ proposedWork.options.report_type }} ·
                          {{ proposedWork.options.audience }} ·
                          {{ t(`copilot.work_quality_${proposedWork.options.quality}`) }}
                        </p>
                      </div>
                    </div>
                    <p v-if="workNote" class="mt-2 text-caption1 text-ink-secondary">{{ workNote }}</p>
                    <p v-else-if="workError" class="mt-2 text-caption1 text-danger">{{ workError }}</p>
                    <div v-if="workState !== 'started'" class="mt-2 flex items-center gap-1.5">
                      <button
                        type="button"
                        class="btn-filled btn-sm focus-ring"
                        :disabled="workState === 'running'"
                        @click="confirmWork"
                      >
                        <Loader2 v-if="workState === 'running'" class="h-3 w-3 animate-spin" />
                        {{ t(`copilot.work_confirm_${proposedWork.kind}`) }}
                      </button>
                      <button
                        v-if="proposedWork.kind === 'report' && openReportCustomizer"
                        type="button"
                        class="btn-bordered btn-sm focus-ring"
                        @click="openWorkOptions"
                      >
                        {{ t("copilot.work_options") }}
                      </button>
                    </div>
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

        <div
          class="shrink-0 pt-2.5"
          :data-file-drag="fileDragOver ? 'true' : 'false'"
          @dragover="onComposerDragOver"
          @dragleave="fileDragOver = false"
          @drop="onComposerDrop"
        >
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
          <!-- Files going with the next question. Warren reads the chat copy;
               Save files it under the company, where a memo run can read it. -->
          <div v-if="attachments.length" class="mb-2 flex flex-wrap gap-1.5 px-0.5">
            <span
              v-for="item in attachments"
              :key="item.key"
              class="warren-file"
              :data-tone="item.error ? 'warning' : null"
              :title="item.error || item.name"
            >
              <Loader2 v-if="item.staging || item.saving" class="h-2.5 w-2.5 shrink-0 animate-spin" />
              <Paperclip v-else class="h-2.5 w-2.5 shrink-0" />
              <span class="max-w-[9rem] truncate">{{ item.name }}</span>
              <button
                v-if="item.storedName && !item.savedId"
                type="button"
                class="warren-file-action focus-ring"
                :disabled="item.saving"
                :title="t('copilot.save_to_files_hint')"
                @click="saveAttachmentToFiles(item)"
              >
                <FolderInput class="h-2.5 w-2.5" />
                {{ t("copilot.save_to_files") }}
              </button>
              <span v-else-if="item.savedId" class="text-ink-muted">{{ t("copilot.saved_to_files") }}</span>
              <button
                type="button"
                class="warren-file-clear focus-ring"
                :aria-label="t('copilot.remove_attachment')"
                :title="t('copilot.remove_attachment')"
                @click="removeAttachment(item.key)"
              >
                <X class="h-2.5 w-2.5" />
              </button>
            </span>
          </div>
          <p v-if="attachError" class="mb-1.5 px-1 text-caption1 text-danger">{{ attachError }}</p>
          <div v-if="viewingThreadId" class="warren-viewing">
            <span class="truncate">
              {{ t("copilot.viewing_earlier") }}
              <template v-if="viewingThread?.askers?.length">
                · {{ viewingThread.askers.join(", ") }}
              </template>
            </span>
            <button type="button" class="warren-action shrink-0" @click="backToCurrentThread">
              {{ t("copilot.back_to_current") }}
            </button>
          </div>
          <form v-else class="ask-composer" @submit.prevent="sendPrompt()">
            <input
              ref="attachInput"
              type="file"
              multiple
              :accept="ATTACHMENT_ACCEPT"
              class="hidden"
              @change="onFilesPicked"
            />
            <button
              type="button"
              class="ask-attach focus-ring"
              :aria-label="t('copilot.attach')"
              :title="t('copilot.attach_hint')"
              @click="pickFiles"
            >
              <Paperclip class="h-4 w-4" />
            </button>
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
              :data-ready="prompt.trim() && !attachBusy ? 'true' : 'false'"
              :disabled="!prompt.trim() || attachBusy"
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
