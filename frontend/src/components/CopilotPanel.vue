<script setup>
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ArrowUp, Loader2, PanelRightClose, ScrollText } from "lucide-vue-next";
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
  copilotAttention,
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
  contextLabel: { type: String, default: "" },
});

const emit = defineEmits(["close", "navigate"]);

const t = useT();
const router = useRouter();
const copilotNavigate = inject("copilotNavigate", null);

const mode = ref(copilotMode.value || "quick");
const contextPayload = ref(null);
const contextLoading = ref(false);
const contextError = ref(null);
const autoPromptSent = ref(false);

const prompt = ref("");
const sending = ref(false);
const pendingText = ref("");
const pendingTurnId = ref(null);
const localTurns = ref([]);
const taskSaving = ref(false);
const taskSaved = ref(false);
const editSaving = ref(false);
const editApplied = ref(false);
const transcriptEl = ref(null);

let askEventSource = null;
let hydrateEventSource = null;

const actions = computed(() => {
  const client = buildClientContext();
  const rows = contextPayload.value?.actions || [];
  return rows.map((action) =>
    resolveCopilotAction(action, t, {
      selection: client.selection,
      attention: client.attention,
      job: client.job,
      workspace: contextPayload.value?.workspace,
      company_name: contextPayload.value?.label?.split(" · ")[0],
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
      return { ...row, label: action.label, prompt: action.prompt };
    })
    .filter(Boolean);
});

const contextChip = computed(
  () => contextPayload.value?.label || props.contextLabel || t("copilot.context_aware"),
);

const hydrationNote = computed(() => {
  const status = contextPayload.value?.session?.hydration_status;
  if (!status || status === "done" || status === "skipped") return "";
  if (status === "in_progress") return t("copilot.hydrating");
  if (status === "error") return t("copilot.hydration_failed");
  return "";
});

const lastAssistant = computed(() =>
  [...localTurns.value].reverse().find((row) => row.role === "assistant"),
);

const structuredOutputs = computed(() =>
  lastAssistant.value ? parseStructuredOutputs(lastAssistant.value.text) : {},
);

const proposedTask = computed(() => structuredOutputs.value.research_task || null);
const suggestedEdit = computed(() => structuredOutputs.value.suggested_edit || null);
const nextRoute = computed(() => structuredOutputs.value.next_route || null);
const contradiction = computed(() => structuredOutputs.value.contradiction || null);

const displayAssistantHtml = computed(() => {
  if (!lastAssistant.value?.text) return "";
  return renderMarkdown(stripStructuredBlocks(lastAssistant.value.text));
});

const lastCitations = computed(() =>
  lastAssistant.value ? extractCitations(lastAssistant.value.text) : [],
);

const followUps = computed(() => followUpChips(structuredOutputs.value, t));

const indexedFiles = computed(() => contextPayload.value?.files || []);
const provenance = computed(() => contextPayload.value?.provenance || null);

const provenanceSources = computed(() => provenance.value?.sources || []);
const provenanceGaps = computed(() => provenance.value?.gaps || []);
const provenanceContradictions = computed(() => provenance.value?.contradictions || []);

function recordEvent(event, payload = {}) {
  if (!props.companyId) return;
  api.copilot.recordEvent(props.companyId, { event, payload }).catch(() => {});
}

function scrollToBottom() {
  nextTick(() => {
    const el = transcriptEl.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

async function loadContext({ triggerAuto = false } = {}) {
  if (!props.companyId) {
    contextPayload.value = null;
    return;
  }
  contextLoading.value = true;
  contextError.value = null;
  try {
    contextPayload.value = await api.copilot.context(
      props.companyId,
      buildClientContext(),
    );
    if (contextPayload.value?.session?.id) {
      await loadSessionTurns(contextPayload.value.session.id);
    }
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
  if (!auto || autoPromptSent.value || localTurns.value.length > 0 || sending.value) return;
  autoPromptSent.value = true;
  nextTick(() => sendPrompt(auto));
}

async function loadSessionTurns(sessionId) {
  if (!props.companyId || !sessionId) return;
  try {
    const turns = await api.console.getTurns(props.companyId, sessionId);
    localTurns.value = turns.filter((row) => row.role === "user" || row.role === "assistant");
  } catch {
    localTurns.value = [];
  }
}

function closeStreams() {
  if (askEventSource) {
    try {
      askEventSource.close();
    } catch {
      /* */
    }
    askEventSource = null;
  }
  if (hydrateEventSource) {
    try {
      hydrateEventSource.close();
    } catch {
      /* */
    }
    hydrateEventSource = null;
  }
}

function openAskStream(sessionId, turnId) {
  closeStreams();
  pendingTurnId.value = turnId;
  pendingText.value = "";
  const url = api.console.askStreamUrl(props.companyId, sessionId, turnId);
  const es = new EventSource(url);
  askEventSource = es;
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
      }
    } else if (entry.type === "done" || entry.type === "error") {
      closeStreams();
      pendingTurnId.value = null;
      pendingText.value = "";
      await loadSessionTurns(sessionId);
      scrollToBottom();
    }
  };
  es.onerror = () => closeStreams();
}

function openHydrateStream(sessionId) {
  closeStreams();
  const url = api.console.hydrateStreamUrl(props.companyId, sessionId);
  const es = new EventSource(url);
  hydrateEventSource = es;
  es.onmessage = async (ev) => {
    let entry;
    try {
      entry = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (entry.type === "done" || entry.type === "error") {
      closeStreams();
      await loadContext();
    }
  };
  es.onerror = () => closeStreams();
}

async function sendPrompt(text) {
  const value = String(text || prompt.value || "").trim();
  if (!value || !props.companyId || sending.value) return;
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
  prompt.value = "";
  localTurns.value = [
    ...localTurns.value,
    { id: `local-${Date.now()}`, role: "user", text: value },
  ];
  scrollToBottom();
  try {
    const payload = await api.copilot.ask(props.companyId, {
      prompt: value,
      context: buildClientContext(),
      output_language: appLanguage.value === "zh" ? "zh" : "en",
      mode: mode.value,
    });
    if (payload.hydrate_stream_url && payload.hydration_status === "in_progress") {
      openHydrateStream(payload.session_id);
    }
    openAskStream(payload.session_id, payload.turn_id);
  } catch (e) {
    localTurns.value = [
      ...localTurns.value,
      { id: `err-${Date.now()}`, role: "assistant", text: e.message, error: true },
    ];
  } finally {
    sending.value = false;
  }
}

function runAction(action) {
  recordEvent("copilot_action_click", { action_id: action.id });
  sendPrompt(action.prompt);
}

function runProactive(message) {
  recordEvent("copilot_proactive_click", { action_id: message.action_id });
  sendPrompt(message.prompt);
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
      params: { id: companyId },
      query: { tab: "documents", evidence: "1", ...(route.query || {}) },
    });
    return;
  }
  if (route.surface === "jobs") {
    router.push({
      name: "research",
      params: { id: companyId },
      query: { tab: "jobs", ...(route.query || {}) },
    });
    return;
  }
  router.push({
    name: "research",
    params: { id: companyId },
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
    localTurns.value = [];
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

onBeforeUnmount(closeStreams);

defineExpose({
  sendPrompt,
  runAction,
  buildDiscussPrompt,
});
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div
      v-if="companyId"
      class="mb-2 rounded-subbox bg-fill-tertiary px-2.5 py-1.5 text-caption1 text-ink-secondary"
    >
      <span class="font-medium text-ink-primary">{{ contextChip }}</span>
      <span v-if="hydrationNote" class="ml-2 text-ink-muted">· {{ hydrationNote }}</span>
    </div>

    <div v-if="!companyId" class="space-y-3 pt-1">
      <p class="text-callout leading-relaxed text-ink-muted">
        {{ t("copilot.open_company") }}
      </p>
    </div>

    <template v-else>
      <div class="segmented mb-2">
        <button
          type="button"
          class="segmented-item focus-ring"
          :data-selected="mode === 'quick' ? 'true' : 'false'"
          @click="switchMode('quick')"
        >
          {{ t("copilot.mode_quick") }}
        </button>
        <button
          type="button"
          class="segmented-item focus-ring"
          :data-selected="mode === 'deep' ? 'true' : 'false'"
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
          v-if="provenance"
          class="mb-2 rounded-card border border-accent/25 bg-accent-soft/30 p-3"
        >
          <div class="text-footnote font-semibold text-ink-primary">
            {{ t("copilot.provenance_title") }}
          </div>
          <p class="mt-1 text-caption1 text-ink-secondary">{{ provenance.label }}</p>
          <div v-if="provenanceSources.length" class="mt-2 space-y-1">
            <div class="text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
              {{ t("copilot.provenance_sources") }}
            </div>
            <button
              v-for="(source, index) in provenanceSources"
              :key="`${source.file_id || source.filename}-${index}`"
              type="button"
              class="block w-full rounded-subbox border border-subtle bg-surface px-2 py-1.5 text-left text-caption1 text-ink-secondary hover:bg-surface-muted focus-ring"
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
            <div class="text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
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
            <div class="text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
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
          <p v-if="!provenanceSources.length && !provenanceGaps.length" class="mt-2 text-caption1 text-ink-muted">
            {{ t("copilot.provenance_empty") }}
          </p>
        </div>

        <div
          v-if="proactiveMessages.length"
          class="mb-2 space-y-1 rounded-card border border-warning/30 bg-warning-soft/30 p-2"
        >
          <div
            v-for="message in proactiveMessages"
            :key="message.action_id"
            class="flex items-center justify-between gap-2"
          >
            <span class="text-caption1 text-ink-secondary">{{ message.label }}</span>
            <button
              type="button"
              class="btn-filled btn-sm focus-ring"
              :disabled="sending"
              @click="runProactive(message)"
            >
              {{ t("copilot.ask_short") }}
            </button>
          </div>
        </div>

        <div v-if="contextLoading" class="flex items-center gap-2 text-caption1 text-ink-muted">
          <Loader2 class="h-3.5 w-3.5 animate-spin" />
          {{ t("common.loading") }}
        </div>
        <p v-else-if="contextError" class="text-caption1 text-danger">{{ contextError }}</p>

        <div v-if="actions.length" class="mb-2 flex flex-wrap gap-1.5">
          <button
            v-for="action in actions"
            :key="action.id"
            type="button"
            class="focus-ring rounded-pill bg-fill-tertiary px-2.5 py-1 text-caption1 font-medium text-ink-secondary transition hover:bg-fill-secondary hover:text-ink-primary"
            :disabled="sending"
            @click="runAction(action)"
          >
            {{ action.label }}
          </button>
        </div>

        <div
          ref="transcriptEl"
          class="min-h-0 flex-1 space-y-3 overflow-y-auto rounded-card bg-surface-muted/60 p-3"
        >
          <p v-if="localTurns.length === 0" class="text-footnote text-ink-muted">
            {{ t("copilot.task_prompt") }}
          </p>
          <div
            v-for="turn in localTurns"
            :key="turn.id"
            class="text-footnote leading-relaxed"
            :class="turn.role === 'user' ? 'text-ink-primary' : 'text-ink-secondary'"
          >
            <div class="mb-0.5 text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
              {{ turn.role === "user" ? t("copilot.you") : t("copilot.title") }}
            </div>
            <div
              v-if="turn.role === 'assistant' && turn.id === lastAssistant?.id"
              class="copilot-md"
            >
              <div v-if="displayAssistantHtml" v-html="displayAssistantHtml" />
              <div v-else-if="turn.error" class="text-danger">{{ turn.error }}</div>
              <div v-else-if="turn.text" :class="turn.error ? 'text-danger' : ''">
                {{ turn.text }}
              </div>
            </div>
            <div v-else :class="turn.error ? 'text-danger' : ''">
              {{ turn.text || turn.error || "" }}
            </div>
          </div>
          <div v-if="pendingTurnId" class="text-footnote text-ink-secondary">
            <div class="mb-0.5 text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
              {{ t("copilot.title") }}
            </div>
            <div v-if="pendingText" class="copilot-md" v-html="renderMarkdown(pendingText)" />
            <div v-else class="flex items-center gap-2 text-caption1 text-ink-muted">
              <Loader2 class="h-4 w-4 animate-spin" />
              {{ t("copilot.thinking") }}
            </div>
          </div>
        </div>

        <div v-if="lastCitations.length" class="mt-2 flex flex-wrap gap-1.5">
          <button
            v-for="cite in lastCitations"
            :key="cite.label"
            type="button"
            class="focus-ring rounded-pill border border-subtle bg-surface px-2 py-0.5 text-caption1 text-accent-ink hover:bg-accent-soft/40"
            @click="openCitation(cite)"
          >
            {{ cite.label }}
          </button>
        </div>

        <div
          v-if="contradiction"
          class="mt-2 rounded-card border border-warning/30 bg-warning-soft/30 p-3 text-caption1 text-ink-secondary"
        >
          <div class="font-semibold text-ink-primary">{{ t("copilot.contradiction_title") }}</div>
          <p class="mt-1">{{ contradiction.claim }}</p>
          <p v-if="contradiction.resolution" class="mt-1 text-ink-muted">
            {{ contradiction.resolution }}
          </p>
        </div>

        <div
          v-if="suggestedEdit"
          class="mt-2 rounded-card border border-accent/20 bg-accent-soft/40 p-3"
        >
          <div class="text-footnote font-semibold text-ink-primary">
            {{ t("copilot.suggested_edit") }}
          </div>
          <p class="mt-1 text-caption1 text-ink-secondary">{{ suggestedEdit.text }}</p>
          <button
            type="button"
            class="btn-filled btn-sm mt-2 focus-ring"
            :disabled="editSaving || editApplied"
            @click="applySuggestedEdit"
          >
            {{ editApplied ? t("copilot.edit_applied") : t("copilot.apply_edit") }}
          </button>
        </div>

        <div v-if="nextRoute" class="mt-2">
          <button type="button" class="btn-outline btn-sm focus-ring" @click="openNextRoute">
            {{ t("copilot.open_route") }}
          </button>
        </div>

        <div
          v-if="proposedTask"
          class="mt-2 rounded-card border border-accent/20 bg-accent-soft/40 p-3"
        >
          <div class="flex items-start gap-2">
            <ScrollText class="mt-0.5 h-4 w-4 shrink-0 text-accent-ink" />
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

        <div v-if="followUps.length && lastAssistant" class="mt-2 flex flex-wrap gap-1.5">
          <button
            v-for="chip in followUps"
            :key="chip.id"
            type="button"
            class="focus-ring rounded-pill border border-subtle bg-surface px-2.5 py-1 text-caption1 text-ink-secondary hover:bg-surface-muted"
            :disabled="sending"
            @click="sendPrompt(chip.prompt)"
          >
            {{ chip.label }}
          </button>
        </div>

        <form class="mt-3 flex items-end gap-2" @submit.prevent="sendPrompt()">
          <textarea
            v-model="prompt"
            rows="2"
            class="field min-h-[2.75rem] flex-1 resize-none focus-ring"
            :placeholder="t('copilot.input_placeholder')"
            :disabled="sending"
            @keydown.enter.exact.prevent="sendPrompt()"
          />
          <button
            type="submit"
            class="icon-btn shrink-0"
            :disabled="!prompt.trim() || sending"
            :aria-label="t('copilot.send')"
          >
            <Loader2 v-if="sending" class="h-4 w-4 animate-spin" />
            <ArrowUp v-else class="h-4 w-4" />
          </button>
        </form>
      </template>
    </template>
  </div>
</template>

<style scoped>
.copilot-md :deep(p) {
  margin: 0.35rem 0;
}
.copilot-md :deep(p:first-child) {
  margin-top: 0;
}
</style>
