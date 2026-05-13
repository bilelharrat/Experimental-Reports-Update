<script setup>
// Per-company Console (see docs/console-feature.md).
// Tab strip of active sessions, plus the active pane: token meter,
// transcript, and the input row. Archived sessions are listed below
// the strip and open into a read-only ConsoleSessions modal.
//
// Live response streaming uses EventSource against the SSE endpoints
// exposed by server/api.py; the per-turn URL replays from disk so
// reconnects don't lose intermediate events.

import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Loader2, Send, StopCircle, Paperclip, X, Plus, Trash2 } from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import ConsoleSessions from "./ConsoleSessions.vue";
import {
  usageToMeter,
  formatTokens,
  formatCost,
  validateAttachment,
  CONTEXT_WINDOW,
} from "../console.js";

const tr = useT();

const props = defineProps({
  companyId: { type: String, required: true },
});

const sessions = ref([]);
const activeId = ref(null);
const activeMeta = ref(null);
const turns = ref([]);
const loading = ref(false);
const loadError = ref(null);

// Live-streaming state (one in-flight turn at a time per session).
const pendingTurnId = ref(null);
const pendingText = ref("");       // accumulating assistant text
const pendingAction = ref("");     // "tool_use: Read deck.pdf" etc.
const pendingQueuePos = ref(0);

// Turn IDs the user has submitted but that are still waiting in the
// server-side queue (server runs one ask per session at a time). The
// pendingTurnId is the head of the queue; queuedTurns is everything
// behind it.
const queuedTurns = ref([]); // string[] turn_ids

const queuedDisplay = computed(() => {
  // Look up each queued turn id in `turns` so we can show the original
  // prompt text alongside the "queued — position N" badge.
  return queuedTurns.value.map((tid, i) => {
    const userRecord = turns.value.find(
      (t) => t.id === tid && t.role === "user",
    );
    return {
      turn_id: tid,
      position: i + 1, // 1-indexed: position 1 = next up after pending
      prompt: userRecord?.text || "",
    };
  });
});

// Hydration tail (one at a time per active session — we just show the latest
// stage message and switch to "ready" when done).
const hydrationStage = ref("");
const hydrationDone = ref(false);

let askEventSource = null;
let hydrateEventSource = null;

// Input state.
const prompt = ref("");
const stagedFiles = ref([]); // File[]
const attachmentErrors = ref([]);

// Create-console modal.
const showCreate = ref(false);
const includeBg = ref(true);
const includeLib = ref(true);
const creating = ref(false);
const sessionLimitError = ref(null);
const estimate = ref(null);
const estimateLoading = ref(false);
let estimateDebounce = null;

function refreshEstimate() {
  clearTimeout(estimateDebounce);
  estimateDebounce = setTimeout(async () => {
    estimateLoading.value = true;
    try {
      estimate.value = await api.console.estimate(props.companyId, {
        include_background_docs: includeBg.value,
        include_library_docs: includeLib.value,
      });
    } catch {
      estimate.value = null;
    } finally {
      estimateLoading.value = false;
    }
  }, 150);
}

watch([includeBg, includeLib, showCreate], () => {
  if (showCreate.value) refreshEstimate();
});

const activeSessions = computed(() =>
  sessions.value.filter((s) => s.status === "active"),
);
const archivedSessions = computed(() =>
  sessions.value.filter((s) => s.status === "archived"),
);

// Token-meter view-model. Reactive to activeMeta because update_tokens()
// on the backend bumps last_turn_usage after every completed turn.
const meter = computed(() => {
  const usage = activeMeta.value?.tokens?.last_turn_usage || null;
  return usageToMeter(usage);
});

const lockSend = computed(() => meter.value.state === "locked");

const tokensCaption = computed(() =>
  tr("console.token_meter", {
    used: formatTokens(meter.value.used),
    total: formatTokens(CONTEXT_WINDOW),
    pct_free: Math.round(meter.value.pct_free * 100),
    cost: formatCost(activeMeta.value?.tokens?.total_cost_usd || 0),
  }),
);

// ---- Load / refresh ----

async function loadSessions() {
  loading.value = true;
  try {
    sessions.value = await api.console.listSessions(props.companyId);
    if (
      activeId.value &&
      !sessions.value.find((s) => s.id === activeId.value && s.status === "active")
    ) {
      activeId.value = null;
      activeMeta.value = null;
      turns.value = [];
    }
    if (!activeId.value && activeSessions.value.length) {
      await selectSession(activeSessions.value[0].id);
    }
  } catch (e) {
    loadError.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function selectSession(sid) {
  closeStreams();
  activeId.value = sid;
  pendingTurnId.value = null;
  pendingText.value = "";
  pendingAction.value = "";
  hydrationStage.value = "";
  hydrationDone.value = true;
  try {
    activeMeta.value = await api.console.getSession(props.companyId, sid);
    turns.value = await api.console.getTurns(props.companyId, sid);
    // If hydration is still running, tail it.
    if (activeMeta.value?.hydration_status === "in_progress") {
      hydrationDone.value = false;
      openHydrateStream(sid);
    } else if (activeMeta.value?.hydration_status === "error") {
      hydrationDone.value = true;
      hydrationStage.value = tr("console.hydration_failed");
    }
    await nextTick();
    scrollToBottom();
  } catch (e) {
    loadError.value = e.message;
  }
}

watch(
  () => props.companyId,
  async () => {
    sessions.value = [];
    activeId.value = null;
    await loadSessions();
  },
  { immediate: true },
);

onBeforeUnmount(closeStreams);

// ---- Create session ----

function openCreate() {
  sessionLimitError.value = null;
  estimate.value = null;
  showCreate.value = true;
  includeBg.value = true;
  includeLib.value = true;
  refreshEstimate();
}

async function confirmCreate() {
  creating.value = true;
  sessionLimitError.value = null;
  try {
    const meta = await api.console.createSession(props.companyId, {
      include_background_docs: includeBg.value,
      include_library_docs: includeLib.value,
    });
    showCreate.value = false;
    sessions.value = [meta, ...sessions.value];
    activeId.value = meta.id;
    activeMeta.value = meta;
    turns.value = [];
    hydrationDone.value = false;
    hydrationStage.value = tr("console.hydrating");
    openHydrateStream(meta.id);
  } catch (e) {
    if (e.status === 409 && e.detail?.detail?.code === "session_limit_reached") {
      sessionLimitError.value = tr("console.session_limit_reached", {
        limit: e.detail.detail.limit,
      });
    } else {
      loadError.value = e.message;
    }
  } finally {
    creating.value = false;
  }
}

// ---- Streaming: hydration ----

function openHydrateStream(sid) {
  closeHydrateStream();
  const url = api.console.hydrateStreamUrl(props.companyId, sid);
  const es = new EventSource(url);
  hydrateEventSource = es;
  es.onmessage = async (ev) => {
    let entry;
    try { entry = JSON.parse(ev.data); } catch { return; }
    if (entry.type === "stage") {
      hydrationStage.value = entry.message || hydrationStage.value;
    } else if (entry.type === "claude_action" && entry.action === "tool_use") {
      hydrationStage.value = `Reading ${entry.preview || ""}`;
    } else if (entry.type === "done" || entry.type === "error") {
      hydrationDone.value = true;
      hydrationStage.value =
        entry.type === "error" ? tr("console.hydration_failed") : "";
      closeHydrateStream();
      // Refresh meta so token meter and hydration_status update.
      try {
        activeMeta.value = await api.console.getSession(props.companyId, sid);
      } catch { /* ignore */ }
    }
  };
  es.onerror = () => closeHydrateStream();
}

function closeHydrateStream() {
  if (hydrateEventSource) {
    try { hydrateEventSource.close(); } catch { /* */ }
    hydrateEventSource = null;
  }
}

// ---- Streaming: per-turn ask ----

function openAskStream(sid, turnId) {
  closeAskStream();
  const url = api.console.askStreamUrl(props.companyId, sid, turnId);
  const es = new EventSource(url);
  askEventSource = es;
  pendingTurnId.value = turnId;
  pendingText.value = "";
  pendingAction.value = "";
  es.onmessage = async (ev) => {
    let entry;
    try { entry = JSON.parse(ev.data); } catch { return; }
    if (entry.type === "claude_action") {
      if (entry.action === "thinking" && entry.text) {
        pendingText.value += entry.text;
        scrollToBottom();
      } else if (entry.action === "tool_use") {
        pendingAction.value = `${entry.tool}: ${(entry.preview || "").slice(0, 80)}`;
      } else if (entry.action === "interrupted") {
        pendingAction.value = tr("console.cancelled");
      }
    } else if (entry.type === "done" || entry.type === "error") {
      closeAskStream();
      pendingTurnId.value = null;
      pendingText.value = "";
      pendingAction.value = "";
      // Refresh turns + meta — the assistant record landed on disk.
      try {
        turns.value = await api.console.getTurns(props.companyId, sid);
        activeMeta.value = await api.console.getSession(props.companyId, sid);
      } catch { /* ignore */ }
      // If more turns are queued client-side, advance to the next.
      if (queuedTurns.value.length) {
        const next = queuedTurns.value[0];
        queuedTurns.value = queuedTurns.value.slice(1);
        pendingQueuePos.value = 0;
        openAskStream(sid, next);
      }
      scrollToBottom();
    }
  };
  es.onerror = () => closeAskStream();
}

function closeAskStream() {
  if (askEventSource) {
    try { askEventSource.close(); } catch { /* */ }
    askEventSource = null;
  }
}

function closeStreams() {
  closeAskStream();
  closeHydrateStream();
}

// ---- Send / stop ----

function onFilesPicked(ev) {
  const files = Array.from(ev.target?.files || []);
  for (const f of files) addFile(f);
  ev.target.value = "";
}

function addFile(file) {
  const err = validateAttachment(file);
  if (err) {
    attachmentErrors.value.push(tr(err.key));
    return;
  }
  stagedFiles.value.push(file);
}

function removeFile(i) {
  stagedFiles.value.splice(i, 1);
}

function onDrop(ev) {
  ev.preventDefault();
  const files = Array.from(ev.dataTransfer?.files || []);
  for (const f of files) addFile(f);
}

async function send() {
  if (!prompt.value.trim() || !activeId.value || lockSend.value) return;
  attachmentErrors.value = [];
  try {
    const info = await api.console.ask(
      props.companyId,
      activeId.value,
      prompt.value.trim(),
      stagedFiles.value,
    );
    // Optimistically push the user turn so it shows up before the next
    // getTurns refresh.
    turns.value = [
      ...turns.value,
      {
        id: info.turn_id,
        role: "user",
        text: prompt.value.trim(),
        ts: new Date().toISOString(),
        attachments: stagedFiles.value.map((f) => ({ name: f.name })),
      },
    ];
    // Either start streaming this turn now (queue is empty) or enqueue
    // it client-side until the active turn finishes. We don't open SSE
    // for queued items because their progress file doesn't exist yet
    // and the stream endpoint times out after 5s waiting for it.
    if (pendingTurnId.value) {
      queuedTurns.value = [...queuedTurns.value, info.turn_id];
    } else {
      pendingQueuePos.value = info.queue_position;
      openAskStream(activeId.value, info.turn_id);
    }
    prompt.value = "";
    stagedFiles.value = [];
    await nextTick();
    scrollToBottom();
  } catch (e) {
    if (e.status === 400 && e.detail?.detail?.code === "attachment_too_large") {
      attachmentErrors.value.push(tr("console.error_attachment_too_large"));
    } else if (e.status === 400 && e.detail?.detail?.code === "attachment_type_not_allowed") {
      attachmentErrors.value.push(tr("console.error_attachment_type"));
    } else {
      loadError.value = e.message;
    }
  }
}

async function stop() {
  if (!pendingTurnId.value || !activeId.value) return;
  try {
    await api.console.cancelAsk(props.companyId, activeId.value, pendingTurnId.value);
  } catch (e) {
    // Even if cancel races with completion, just close the stream.
  }
}

// ---- Archive / delete ----

async function archive() {
  if (!activeId.value) return;
  if (!confirm(tr("console.archive_confirm"))) return;
  try {
    const m = await api.console.archive(props.companyId, activeId.value);
    // Update local list state.
    sessions.value = sessions.value.map((s) => (s.id === m.id ? m : s));
    activeId.value = null;
    activeMeta.value = null;
    turns.value = [];
    if (activeSessions.value.length) {
      await selectSession(activeSessions.value[0].id);
    }
  } catch (e) {
    loadError.value = e.message;
  }
}

async function destroy() {
  if (!activeId.value) return;
  if (!confirm(tr("console.delete_confirm"))) return;
  try {
    await api.console.deleteSession(props.companyId, activeId.value);
    sessions.value = sessions.value.filter((s) => s.id !== activeId.value);
    activeId.value = null;
    activeMeta.value = null;
    turns.value = [];
    if (activeSessions.value.length) {
      await selectSession(activeSessions.value[0].id);
    }
  } catch (e) {
    loadError.value = e.message;
  }
}

// ---- Scroll behavior ----

const transcriptEl = ref(null);
function scrollToBottom() {
  const el = transcriptEl.value;
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

// ---- Display helpers ----

function turnTime(ts) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function attachmentUrl(turn, att) {
  if (!att?.id || !activeId.value) return null;
  return api.console.attachmentUrl(props.companyId, activeId.value, att.id);
}
</script>

<template>
  <div class="bg-surface border border-subtle rounded-card shadow-card p-4 flex flex-col gap-3"
       style="min-height: 500px;">
    <!-- Tab strip — horizontal scroll handles overflow when many tabs. -->
    <div class="flex items-center gap-2">
      <div class="flex-1 overflow-x-auto">
        <div class="flex items-center gap-2 w-max">
          <button
            v-for="s in activeSessions"
            :key="s.id"
            @click="selectSession(s.id)"
            :class="[
              'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm focus-ring flex-shrink-0',
              activeId === s.id
                ? 'bg-accent text-white'
                : 'bg-surface-muted text-ink-secondary hover:bg-surface',
            ]"
          >
            <span class="h-1.5 w-1.5 rounded-full"
                  :class="activeId === s.id ? 'bg-white' : 'bg-accent'"></span>
            <span class="truncate max-w-[160px]">{{ s.title }}</span>
          </button>
          <button
            @click="openCreate"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-surface-muted text-ink-primary hover:bg-surface border border-subtle focus-ring flex-shrink-0"
          >
            <Plus class="h-3.5 w-3.5" />
            {{ tr("console.new_console") }}
          </button>
        </div>
      </div>
      <div v-if="archivedSessions.length" class="flex-shrink-0">
        <ConsoleSessions :company-id="companyId" :sessions="archivedSessions" />
      </div>
    </div>

    <!-- Empty state — single "+ New" entry point lives in the tab strip
         above; this card is just the help text. -->
    <div
      v-if="!activeId && !loading"
      class="rounded-card border border-dashed border-subtle p-6 text-sm text-ink-secondary"
    >
      <p>{{ tr("console.empty_help") }}</p>
    </div>

    <!-- Active session pane -->
    <template v-if="activeId && activeMeta">
      <!-- Token meter + banner -->
      <div class="flex items-center gap-3 text-xs text-ink-muted">
        <div class="flex-1">
          <div>{{ tokensCaption }}</div>
          <div class="mt-1 h-1.5 w-full rounded-full bg-surface-muted overflow-hidden">
            <div
              :class="[
                'h-full',
                meter.color === 'red' ? 'bg-danger' :
                meter.color === 'yellow' ? 'bg-warning' :
                'bg-accent',
              ]"
              :style="{ width: Math.min(100, meter.pct_used * 100) + '%' }"
            ></div>
          </div>
        </div>
        <button
          @click="archive"
          class="px-2 py-1 rounded hover:bg-surface-muted text-ink-secondary focus-ring"
          :title="tr('console.archive_session')"
        >
          {{ tr("console.end_session") }}
        </button>
        <button
          @click="destroy"
          class="p-1 rounded hover:bg-surface-muted text-ink-muted focus-ring"
          :title="tr('console.delete_session')"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </div>

      <!-- Threshold banner -->
      <div
        v-if="meter.state === 'warning'"
        class="rounded-lg border border-warning bg-warning-soft text-warning-ink px-3 py-2 text-xs"
      >
        {{ tr("console.warning_threshold") }}
      </div>
      <div
        v-else-if="meter.state === 'locked'"
        class="rounded-lg border border-danger/40 bg-danger/10 text-ink-primary px-3 py-2 text-xs flex items-center justify-between gap-3"
      >
        <span>{{ tr("console.lock_threshold") }}</span>
        <button
          @click="archive"
          class="px-3 py-1 rounded bg-accent text-white hover:bg-accent-hover focus-ring text-xs"
        >
          {{ tr("console.session_full_cta") }}
        </button>
      </div>

      <!-- Hydration status -->
      <div
        v-if="!hydrationDone"
        class="rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-muted flex items-center gap-2"
      >
        <Loader2 class="h-3.5 w-3.5 animate-spin" />
        <span>{{ hydrationStage || tr("console.hydrating") }}</span>
      </div>

      <!-- Transcript -->
      <div
        ref="transcriptEl"
        class="flex-1 min-h-0 overflow-y-auto border border-subtle rounded-lg bg-surface-muted p-3 space-y-3 text-sm"
        style="max-height: 480px;"
      >
        <div v-if="turns.length === 0" class="text-ink-muted text-center py-4">
          —
        </div>
        <div v-for="t in turns" :key="t.id + ':' + t.role" class="space-y-1">
          <div class="text-xs uppercase tracking-wide text-ink-muted">
            <template v-if="t.role === 'user'">▶ {{ tr("console.you") }}</template>
            <template v-else>▶ {{ tr("console.claude") }}</template>
            <span class="ml-2 normal-case tracking-normal">{{ turnTime(t.ts) }}</span>
            <span
              v-if="t.role === 'assistant' && t.subtype === 'error'"
              class="ml-2 normal-case tracking-normal text-danger"
            >
              · {{ tr("console.failed") }}
            </span>
          </div>
          <div class="whitespace-pre-wrap text-ink-primary">{{ t.text || t.error || "" }}</div>
          <div v-if="t.attachments?.length" class="flex flex-wrap gap-2 pt-1">
            <a
              v-for="(att, i) in t.attachments"
              :key="i"
              :href="attachmentUrl(t, att) || '#'"
              target="_blank"
              class="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink-primary"
            >
              <Paperclip class="h-3 w-3" />
              <span>{{ att.name }}</span>
            </a>
          </div>
        </div>

        <!-- Live in-flight turn -->
        <div v-if="pendingTurnId" class="space-y-1">
          <div class="text-xs uppercase tracking-wide text-ink-muted flex items-center gap-2">
            <Loader2 class="h-3 w-3 animate-spin" />
            ▶ {{ tr("console.claude") }}
            <span v-if="pendingQueuePos > 0" class="normal-case tracking-normal text-ink-muted">
              ({{ tr("console.queued_position", { n: pendingQueuePos }) }})
            </span>
          </div>
          <div v-if="pendingAction" class="text-xs text-ink-muted italic">{{ pendingAction }}</div>
          <div class="whitespace-pre-wrap text-ink-primary">{{ pendingText }}</div>
        </div>

        <!-- Queued turns (waiting for prior to complete) -->
        <div
          v-for="q in queuedDisplay"
          :key="'q:' + q.turn_id"
          class="space-y-1 opacity-70"
        >
          <div class="text-xs uppercase tracking-wide text-ink-muted">
            ▶ {{ tr("console.claude") }}
            <span class="normal-case tracking-normal">
              ({{ tr("console.queued_position", { n: q.position }) }})
            </span>
          </div>
          <div class="text-xs text-ink-muted italic">⋯</div>
        </div>
      </div>

      <!-- Input -->
      <div
        class="border border-subtle rounded-lg bg-surface p-3 flex flex-col gap-2"
        @dragover.prevent
        @drop="onDrop"
      >
        <textarea
          v-model="prompt"
          rows="2"
          :placeholder="tr('console.input_placeholder')"
          :disabled="lockSend || !!pendingTurnId"
          class="w-full px-2 py-1 bg-transparent text-ink-primary placeholder:text-ink-subtle outline-none resize-y"
          @keydown.enter.exact.prevent="send"
        ></textarea>

        <div v-if="stagedFiles.length" class="flex flex-wrap gap-2">
          <div
            v-for="(f, i) in stagedFiles"
            :key="i"
            class="inline-flex items-center gap-1 px-2 py-1 rounded bg-surface-muted text-xs"
          >
            <Paperclip class="h-3 w-3" />
            <span>{{ f.name }}</span>
            <button @click="removeFile(i)" class="text-ink-muted hover:text-danger focus-ring">
              <X class="h-3 w-3" />
            </button>
          </div>
        </div>

        <div v-if="attachmentErrors.length" class="text-xs text-danger">
          <div v-for="(e, i) in attachmentErrors" :key="i">{{ e }}</div>
        </div>

        <div class="flex items-center gap-2">
          <label class="inline-flex items-center gap-1 px-2 py-1 rounded bg-surface-muted text-xs cursor-pointer hover:bg-surface focus-ring">
            <Paperclip class="h-3.5 w-3.5" />
            <span>{{ tr("console.attach") }}</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              multiple
              @change="onFilesPicked"
              class="hidden"
            />
          </label>
          <div class="flex-1"></div>
          <button
            v-if="pendingTurnId"
            @click="stop"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-danger/10 text-danger border border-danger/40 hover:bg-danger/20 focus-ring text-sm"
          >
            <StopCircle class="h-4 w-4" />
            {{ tr("console.stop") }}
          </button>
          <button
            v-else
            @click="send"
            :disabled="lockSend || !prompt.trim()"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed focus-ring text-sm"
          >
            <Send class="h-4 w-4" />
            {{ tr("console.send") }}
          </button>
        </div>
      </div>
    </template>

    <div v-if="loadError" class="text-xs text-danger">{{ loadError }}</div>

    <!-- Create-console modal -->
    <div
      v-if="showCreate"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      @click.self="showCreate = false"
    >
      <div class="bg-surface rounded-card shadow-card border border-subtle p-6 max-w-lg w-full space-y-4 max-h-[80vh] overflow-y-auto">
        <h3 class="font-display text-lg font-semibold text-ink-primary">
          {{ tr("console.create_console") }}
        </h3>
        <p class="text-sm text-ink-secondary">{{ tr("console.empty_help") }}</p>

        <label class="flex items-center gap-2 text-sm text-ink-primary">
          <input type="checkbox" v-model="includeBg" class="rounded" />
          {{
            tr("console.include_background_docs", {
              count: estimate?.files?.filter((f) => f.kind === "research").length ?? "—",
            })
          }}
        </label>
        <label class="flex items-center gap-2 text-sm text-ink-primary">
          <input type="checkbox" v-model="includeLib" class="rounded" />
          {{
            tr("console.include_library_docs", {
              count: estimate?.files?.filter((f) => f.kind === "library").length ?? "—",
            })
          }}
        </label>

        <!-- File list + cost estimate -->
        <div
          v-if="estimateLoading"
          class="rounded-lg border border-subtle bg-surface-muted p-3 text-xs text-ink-muted"
        >
          {{ tr("console.estimate_loading") }}
        </div>
        <div
          v-else-if="estimate && estimate.files?.length"
          class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2 text-xs"
        >
          <div class="font-medium text-ink-primary uppercase tracking-wide text-[10px]">
            {{ tr("console.estimate_files", { count: estimate.files.length }) }}
          </div>
          <ul class="space-y-0.5 text-ink-secondary max-h-40 overflow-y-auto">
            <li
              v-for="f in estimate.files"
              :key="f.kind + ':' + f.id"
              class="flex items-center justify-between gap-2"
            >
              <span class="truncate">{{ f.filename }}</span>
              <span class="text-ink-muted whitespace-nowrap">{{ Math.round((f.size_bytes || 0) / 1024) }} KB</span>
            </li>
          </ul>
          <div class="border-t border-subtle pt-2 text-ink-secondary">
            {{
              tr("console.estimate_tokens", {
                tokens: formatTokens(estimate.tokens_est || 0),
                seconds: estimate.duration_est_s || 0,
              })
            }}
          </div>
        </div>
        <div
          v-else-if="estimate"
          class="rounded-lg border border-subtle bg-surface-muted p-3 text-xs text-ink-muted"
        >
          {{ tr("console.estimate_zero") }}
        </div>

        <div v-if="sessionLimitError" class="text-xs text-danger">
          {{ sessionLimitError }}
        </div>
        <div class="flex justify-end gap-2">
          <button
            @click="showCreate = false"
            class="px-3 py-1.5 rounded-lg bg-surface-muted text-ink-primary hover:bg-surface focus-ring text-sm"
          >
            {{ tr("common.cancel") }}
          </button>
          <button
            @click="confirmCreate"
            :disabled="creating"
            class="px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50 focus-ring text-sm"
          >
            {{ tr("console.create_console") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
