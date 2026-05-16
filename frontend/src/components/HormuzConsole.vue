<script setup>
// Hormuz Console — free-form Q&A grounded in the two most recent days of
// Hormuz source reports + their V3 appendices. Reuses the generic,
// company-agnostic console endpoints with the fixed scope id "hormuz";
// only session-create is Hormuz-specific (api.hormuzConsole.createSession).
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Loader2, Send, StopCircle, Plus, Trash2, Archive } from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import { renderMarkdown } from "../markdown.js";
import { usageToMeter, formatTokens, formatCost, CONTEXT_WINDOW } from "../console.js";

const SCOPE = api.hormuzConsole.SCOPE; // "hormuz"
const tr = useT();

const sessions = ref([]);
const activeId = ref(null);
const activeMeta = ref(null);
const turns = ref([]);
const loadError = ref(null);
const ctx = ref(null); // {dates, file_count, files}

const pendingTurnId = ref(null);
const pendingText = ref("");
const pendingAction = ref("");
const pendingQueuePos = ref(0);
const queuedTurns = ref([]);

const hydrationStage = ref("");
const hydrationDone = ref(true);

let askEventSource = null;
let hydrateEventSource = null;

const prompt = ref("");
const creating = ref(false);

// New-session language picker. "New session" opens this; the session is
// only created once the user confirms a language (default = app lang).
const showCreate = ref(false);
// Hormuz reports are Chinese-source; default the console to Chinese
// regardless of the global app language (user can switch per session).
const newLang = ref("zh");

function openCreate() {
  newLang.value = "zh";
  loadError.value = null;
  showCreate.value = true;
}

const activeSessions = computed(() =>
  sessions.value.filter((s) => s.status === "active"),
);
const archivedSessions = computed(() =>
  sessions.value.filter((s) => s.status === "archived"),
);

const meter = computed(() =>
  usageToMeter(activeMeta.value?.tokens?.last_turn_usage || null),
);
const lockSend = computed(() => meter.value.state === "locked");
const tokensCaption = computed(() =>
  tr("console.token_meter", {
    used: formatTokens(meter.value.used),
    total: formatTokens(CONTEXT_WINDOW),
    pct_free: Math.round(meter.value.pct_free * 100),
    cost: formatCost(activeMeta.value?.tokens?.total_cost_usd || 0),
  }),
);
const sessionActive = computed(
  () => activeMeta.value?.status === "active",
);

const queuedDisplay = computed(() =>
  queuedTurns.value.map((tid, i) => {
    const u = turns.value.find((t) => t.id === tid && t.role === "user");
    return { turn_id: tid, position: i + 1, prompt: u?.text || "" };
  }),
);

async function loadSessions() {
  try {
    sessions.value = await api.console.listSessions(SCOPE);
    if (!activeId.value && activeSessions.value.length) {
      await selectSession(activeSessions.value[0].id);
    }
  } catch (e) {
    loadError.value = e.message;
  }
}

async function loadContext() {
  try {
    ctx.value = await api.hormuzConsole.context();
  } catch {
    ctx.value = null;
  }
}

async function selectSession(sid) {
  closeStreams();
  activeId.value = sid;
  pendingTurnId.value = null;
  pendingText.value = "";
  pendingAction.value = "";
  hydrationDone.value = true;
  try {
    activeMeta.value = await api.console.getSession(SCOPE, sid);
    turns.value = await api.console.getTurns(SCOPE, sid);
    if (activeMeta.value?.hydration_status === "in_progress") {
      hydrationDone.value = false;
      openHydrateStream(sid);
    } else if (activeMeta.value?.hydration_status === "error") {
      hydrationStage.value = tr("console.hydration_failed");
    }
    await nextTick();
    scrollToBottom();
  } catch (e) {
    loadError.value = e.message;
  }
}

onMounted(async () => {
  await loadContext();
  await loadSessions();
});
onBeforeUnmount(closeStreams);

async function createSession() {
  creating.value = true;
  loadError.value = null;
  try {
    const meta = await api.hormuzConsole.createSession({
      output_language: newLang.value === "zh" ? "zh" : "en",
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
    if (e.status === 400 && e.detail?.detail?.message) {
      loadError.value = e.detail.detail.message;
    } else if (
      e.status === 409 &&
      e.detail?.detail?.code === "session_limit_reached"
    ) {
      loadError.value = tr("console.session_limit_reached", {
        limit: e.detail.detail.limit,
      });
    } else {
      loadError.value = e.message;
    }
  } finally {
    creating.value = false;
  }
}

function openHydrateStream(sid) {
  closeHydrateStream();
  const es = new EventSource(api.console.hydrateStreamUrl(SCOPE, sid));
  hydrateEventSource = es;
  es.onmessage = async (ev) => {
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (entry.type === "stage") {
      hydrationStage.value = entry.message || hydrationStage.value;
    } else if (entry.type === "claude_action" && entry.action === "tool_use") {
      hydrationStage.value = `Reading ${entry.preview || ""}`;
    } else if (entry.type === "done" || entry.type === "error") {
      hydrationDone.value = true;
      hydrationStage.value =
        entry.type === "error" ? tr("console.hydration_failed") : "";
      closeHydrateStream();
      try {
        activeMeta.value = await api.console.getSession(SCOPE, sid);
      } catch {
        /* ignore */
      }
    }
  };
  es.onerror = () => closeHydrateStream();
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

function openAskStream(sid, turnId) {
  closeAskStream();
  const es = new EventSource(api.console.askStreamUrl(SCOPE, sid, turnId));
  askEventSource = es;
  pendingTurnId.value = turnId;
  pendingText.value = "";
  pendingAction.value = "";
  es.onmessage = async (ev) => {
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
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
      try {
        turns.value = await api.console.getTurns(SCOPE, sid);
        activeMeta.value = await api.console.getSession(SCOPE, sid);
      } catch {
        /* ignore */
      }
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
    try {
      askEventSource.close();
    } catch {
      /* */
    }
    askEventSource = null;
  }
}

function closeStreams() {
  closeAskStream();
  closeHydrateStream();
}

async function send() {
  if (!prompt.value.trim() || !activeId.value || lockSend.value) return;
  if (!sessionActive.value) return;
  const text = prompt.value.trim();
  try {
    const info = await api.console.ask(SCOPE, activeId.value, text, []);
    turns.value = [
      ...turns.value,
      { id: info.turn_id, role: "user", text, ts: new Date().toISOString() },
    ];
    if (pendingTurnId.value) {
      queuedTurns.value = [...queuedTurns.value, info.turn_id];
    } else {
      pendingQueuePos.value = info.queue_position;
      openAskStream(activeId.value, info.turn_id);
    }
    prompt.value = "";
    await nextTick();
    scrollToBottom();
  } catch (e) {
    loadError.value = e.message;
  }
}

async function stop() {
  if (!pendingTurnId.value || !activeId.value) return;
  try {
    await api.console.cancelAsk(SCOPE, activeId.value, pendingTurnId.value);
  } catch {
    /* close handled by stream */
  }
}

async function archive() {
  if (!activeId.value || !confirm(tr("console.archive_confirm"))) return;
  try {
    const m = await api.console.archive(SCOPE, activeId.value);
    sessions.value = sessions.value.map((s) => (s.id === m.id ? m : s));
    activeId.value = null;
    activeMeta.value = null;
    turns.value = [];
    if (activeSessions.value.length)
      await selectSession(activeSessions.value[0].id);
  } catch (e) {
    loadError.value = e.message;
  }
}

async function destroy() {
  if (!activeId.value || !confirm(tr("console.delete_confirm"))) return;
  try {
    await api.console.deleteSession(SCOPE, activeId.value);
    sessions.value = sessions.value.filter((s) => s.id !== activeId.value);
    activeId.value = null;
    activeMeta.value = null;
    turns.value = [];
    if (activeSessions.value.length)
      await selectSession(activeSessions.value[0].id);
  } catch (e) {
    loadError.value = e.message;
  }
}

const transcriptEl = ref(null);
function scrollToBottom() {
  const el = transcriptEl.value;
  if (el) el.scrollTop = el.scrollHeight;
}
function turnTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}
</script>

<template>
  <div
    class="bg-surface border border-subtle rounded-card shadow-card p-4 flex flex-col gap-3"
    style="min-height: 520px;"
  >
    <!-- Context banner -->
    <div
      v-if="ctx"
      class="text-xs text-ink-muted bg-surface-muted border border-subtle rounded-lg px-3 py-2"
    >
      <span class="font-medium text-ink-secondary">Context:</span>
      <span v-if="ctx.dates?.length">
        last {{ ctx.dates.length }} day(s) — {{ ctx.dates.join(", ") }} ·
        {{ ctx.file_count }} document(s)
      </span>
      <span v-else>No source reports yet — upload reports in the Library tab.</span>
    </div>

    <!-- Session tabs -->
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
            <span
              class="h-1.5 w-1.5 rounded-full"
              :class="activeId === s.id ? 'bg-white' : 'bg-accent'"
            ></span>
            <span class="truncate max-w-[160px]">{{ s.title }}</span>
          </button>
          <button
            @click="openCreate"
            :disabled="creating || !(ctx && ctx.file_count)"
            class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-surface-muted text-ink-primary hover:bg-surface border border-subtle focus-ring flex-shrink-0 disabled:opacity-50"
          >
            <Loader2 v-if="creating" class="h-3.5 w-3.5 animate-spin" />
            <Plus v-else class="h-3.5 w-3.5" />
            {{ tr("console.new_console") }}
          </button>
        </div>
      </div>
      <div v-if="activeId" class="flex items-center gap-1 flex-shrink-0">
        <button
          @click="archive"
          class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring"
          title="Archive session"
        >
          <Archive class="h-4 w-4" />
        </button>
        <button
          @click="destroy"
          class="p-1.5 rounded hover:bg-danger-soft text-ink-muted hover:text-danger-ink focus-ring"
          title="Delete session"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </div>
    </div>

    <select
      v-if="archivedSessions.length"
      class="text-xs px-2 py-1 rounded border border-subtle bg-surface-muted text-ink-secondary focus-ring max-w-[260px]"
      @change="(e) => e.target.value && selectSession(e.target.value)"
    >
      <option value="">
        {{ tr("console.archived_label", { count: archivedSessions.length }) }}
      </option>
      <option v-for="s in archivedSessions" :key="s.id" :value="s.id">
        {{ s.title }}
      </option>
    </select>

    <div v-if="loadError" class="text-sm text-danger">{{ loadError }}</div>

    <div
      v-if="!hydrationDone"
      class="rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-muted flex items-center gap-2"
    >
      <Loader2 class="h-3.5 w-3.5 animate-spin" />
      <span>{{ hydrationStage || tr("console.hydrating") }}</span>
    </div>

    <!-- Transcript -->
    <div
      v-if="activeId"
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
        <div
          v-if="t.role === 'assistant' && t.subtype !== 'error' && t.text"
          class="md-body text-ink-primary"
          v-html="renderMarkdown(t.text)"
        ></div>
        <div v-else class="whitespace-pre-wrap text-ink-primary">
          {{ t.text || t.error || "" }}
        </div>
      </div>

      <div v-if="pendingTurnId" class="space-y-1">
        <div
          class="text-xs uppercase tracking-wide text-ink-muted flex items-center gap-2"
        >
          <Loader2 class="h-3 w-3 animate-spin" />
          ▶ {{ tr("console.claude") }}
          <span
            v-if="pendingQueuePos > 0"
            class="normal-case tracking-normal text-ink-muted"
          >
            ({{ tr("console.queued_position", { n: pendingQueuePos }) }})
          </span>
        </div>
        <div v-if="pendingAction" class="text-xs text-ink-muted italic">
          {{ pendingAction }}
        </div>
        <div
          v-if="pendingText"
          class="md-body text-ink-primary"
          v-html="renderMarkdown(pendingText)"
        ></div>
      </div>

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

    <div
      v-else
      class="flex-1 grid place-items-center text-sm text-ink-muted py-10"
    >
      Start a session to ask questions grounded in the latest reports.
    </div>

    <!-- Input -->
    <div v-if="activeId" class="space-y-1">
      <div class="flex items-end gap-2">
        <textarea
          v-model="prompt"
          rows="2"
          :placeholder="tr('console.input_placeholder')"
          :disabled="!sessionActive || lockSend"
          class="flex-1 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm resize-none disabled:opacity-50"
          @keydown.enter.exact.prevent="send"
        ></textarea>
        <button
          v-if="pendingTurnId"
          @click="stop"
          class="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm bg-surface-muted text-ink-primary hover:bg-surface border border-subtle focus-ring"
        >
          <StopCircle class="h-4 w-4" /> Stop
        </button>
        <button
          v-else
          @click="send"
          :disabled="!prompt.trim() || !sessionActive || lockSend"
          class="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm bg-accent text-white hover:bg-accent-hover focus-ring disabled:opacity-50"
        >
          <Send class="h-4 w-4" /> {{ tr("console.send") }}
        </button>
      </div>
      <div class="flex items-center justify-between text-[11px] text-ink-muted">
        <span>{{ tokensCaption }}</span>
        <span v-if="!sessionActive" class="text-warning-ink">
          {{ tr("console.read_only_transcript") }}
        </span>
      </div>
    </div>

    <!-- New-session language picker -->
    <Teleport to="body">
      <div
        v-if="showCreate"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        @click.self="showCreate = false"
      >
        <div
          class="bg-surface rounded-card shadow-card-raised border border-subtle w-full max-w-md p-5 space-y-4"
        >
          <div>
            <div class="font-display text-base font-semibold text-ink-primary">
              New Hormuz console session
            </div>
            <p class="mt-1 text-xs text-ink-muted">
              <template v-if="ctx && ctx.dates?.length">
                Loads the last {{ ctx.dates.length }} day(s)
                ({{ ctx.dates.join(", ") }}) — {{ ctx.file_count }}
                document(s) into context.
              </template>
              <template v-else>
                No source reports yet — upload reports in the Library tab.
              </template>
            </p>
          </div>

          <div>
            <div
              class="text-[11px] uppercase tracking-wide text-ink-muted mb-1.5"
            >
              Response language
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                @click="newLang = 'en'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-sm border focus-ring',
                  newLang === 'en'
                    ? 'bg-accent text-white border-accent'
                    : 'bg-surface-muted text-ink-secondary border-subtle hover:bg-surface',
                ]"
              >
                English
              </button>
              <button
                type="button"
                @click="newLang = 'zh'"
                :class="[
                  'px-3 py-1.5 rounded-lg text-sm border focus-ring',
                  newLang === 'zh'
                    ? 'bg-accent text-white border-accent'
                    : 'bg-surface-muted text-ink-secondary border-subtle hover:bg-surface',
                ]"
              >
                中文
              </button>
            </div>
          </div>

          <div class="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              @click="showCreate = false"
              :disabled="creating"
              class="px-3 py-1.5 rounded-lg text-sm border border-subtle text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="createSession"
              :disabled="creating || !(ctx && ctx.file_count)"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-accent text-white hover:bg-accent-hover focus-ring disabled:opacity-50"
            >
              <Loader2 v-if="creating" class="h-4 w-4 animate-spin" />
              <Plus v-else class="h-4 w-4" />
              Start session
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
