<script setup>
import { computed, onMounted, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  RefreshCw,
} from "lucide-vue-next";
import { api } from "../api.js";
import MemoStudioBulletTree from "./memo/MemoStudioBulletTree.vue";

const props = defineProps({
  companyId: { type: String, required: true },
});

const emit = defineEmits(["discuss"]);

const editor = ref(null);
const loading = ref(true);
const error = ref("");
const savingId = ref("");
const exportResult = ref(null);
const exportError = ref("");
const exporting = ref(false);
const history = ref({ versions: [], audit_records: [], memo_tasks: [] });
const historyError = ref("");

const sectionIds = [
  "executive_summary",
  "investment_thesis",
  "risks_mitigations",
  "conclusion",
  "appendix",
];

const sections = computed(() => editor.value?.sections || {});
const thesisCards = computed(() => orderedCards("investment_thesis"));
const riskCards = computed(() => orderedCards("risks_mitigations"));
const conclusion = computed(() => sections.value.conclusion || {});
const appendixBlocks = computed(() => sections.value.appendix?.blocks || []);
const memoTasks = computed(() => history.value?.memo_tasks || editor.value?.memo_tasks || []);
const auditRecords = computed(() => history.value?.audit_records || editor.value?.audit_records || []);
const versions = computed(() => history.value?.versions || []);
const completedSections = computed(() =>
  sectionIds.filter((id) => {
    const status = sections.value[id]?.status || "";
    return status === "done" || status === "ready_for_input";
  }).length,
);
const progressPct = computed(() =>
  Math.round((completedSections.value / sectionIds.length) * 100),
);

function orderedCards(sectionId) {
  const cards = sections.value[sectionId]?.cards || [];
  return [...cards].sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
}

function cardTone(sectionId, card) {
  if (sectionId === "risks_mitigations") {
    if (card.severity === "high") return "border-l-danger";
    if (card.severity === "medium") return "border-l-warning";
    return "border-l-ink-muted";
  }
  return "border-l-accent";
}

function sourceLabel(item) {
  return item?.source_class || item?.source_refs?.[0]?.source_class || "unknown/pending";
}

function sourceCount(item) {
  return Array.isArray(item?.source_refs) ? item.source_refs.length : 0;
}

function coverageLabel(result) {
  const coverage = result?.source_coverage;
  if (!coverage) return "coverage pending";
  return `${Math.round((coverage.coverage || 0) * 100)}% source coverage`;
}

async function load() {
  loading.value = true;
  error.value = "";
  exportResult.value = null;
  try {
    editor.value = await api.memoEditor.get(props.companyId);
    await loadHistory();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

async function loadHistory() {
  historyError.value = "";
  try {
    history.value = await api.memoEditor.history(props.companyId);
  } catch (e) {
    historyError.value = e?.message || String(e);
    history.value = {
      versions: [],
      audit_records: editor.value?.audit_records || [],
      memo_tasks: editor.value?.memo_tasks || [],
    };
  }
}

onMounted(load);
watch(() => props.companyId, load);

function applyState(state) {
  editor.value = state;
  exportResult.value = null;
  loadHistory();
}

async function patchCard(sectionId, card, patch) {
  savingId.value = `${sectionId}:${card.id}`;
  try {
    applyState(await api.memoEditor.patchCard(props.companyId, sectionId, card.id, patch));
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}

async function moveCard(sectionId, card, direction) {
  savingId.value = `${sectionId}:${card.id}:move`;
  try {
    applyState(await api.memoEditor.moveCard(props.companyId, sectionId, card.id, direction));
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}

async function selectConclusion(option) {
  savingId.value = `conclusion:${option.id}`;
  try {
    applyState(await api.memoEditor.selectConclusion(props.companyId, option.id));
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}

async function rerunSection(sectionId) {
  savingId.value = `rerun:${sectionId}`;
  try {
    applyState(await api.memoEditor.rerunSection(props.companyId, sectionId));
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}

async function toggleAppendix(block) {
  savingId.value = `appendix:${block.id}`;
  try {
    applyState(
      await api.memoEditor.patchAppendixBlock(props.companyId, block.id, {
        expanded: !block.expanded,
      }),
    );
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}

async function projectExport() {
  exporting.value = true;
  exportError.value = "";
  try {
    exportResult.value = await api.memoEditor.exportProjection(props.companyId, {
      record: true,
    });
    await loadHistory();
  } catch (e) {
    exportError.value = e?.message || String(e);
  } finally {
    exporting.value = false;
  }
}

async function discuss(context) {
  const taskPayload = {
    action_type: "discuss",
    title: `Discuss: ${context.card_title || context.bullet_text || "memo point"}`,
    description: context.bullet_text || "Review this memo point in the co-pilot.",
    context: {
      ...context,
      company_id: props.companyId,
      memo_version_id: editor.value?.version_id,
    },
    status: "proposed",
  };
  try {
    await api.memoEditor.createTask(props.companyId, taskPayload);
    await loadHistory();
  } catch (e) {
    historyError.value = e?.message || String(e);
  }
  emit("discuss", taskPayload.context);
}

async function setTaskStatus(task, status) {
  savingId.value = `task:${task.id}`;
  historyError.value = "";
  try {
    await api.memoEditor.updateTask(props.companyId, task.id, { status });
    await loadHistory();
  } catch (e) {
    historyError.value = e?.message || String(e);
  } finally {
    savingId.value = "";
  }
}
</script>

<template>
  <section class="bg-surface border border-subtle rounded-card shadow-card p-6">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="vogue-label">Memo Studio</div>
        <h2 class="font-display text-xl font-semibold text-ink-primary">
          PRD memo editor
        </h2>
        <p class="mt-1 max-w-3xl text-sm text-ink-muted">
          Curate the five-section memo from durable editor state. Export is
          blocked until key figures have source or source-class coverage.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          @click="load"
          class="inline-flex items-center gap-2 rounded-full border border-subtle px-3 py-2 text-xs font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
        >
          <RefreshCw class="h-4 w-4" />
          Refresh
        </button>
        <button
          type="button"
          @click="projectExport"
          :disabled="exporting || loading"
          class="inline-flex items-center gap-2 rounded-full bg-ink-primary px-4 py-2 text-xs font-semibold text-white disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="exporting" class="h-4 w-4 animate-spin" />
          <Download v-else class="h-4 w-4" />
          Export Memo
        </button>
      </div>
    </div>

    <div v-if="loading" class="mt-5 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading memo editor…
    </div>
    <div v-else-if="error" class="mt-5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
      {{ error }}
    </div>

    <template v-else-if="editor">
      <div class="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
        <div class="rounded-card border border-subtle bg-surface-muted p-4">
          <div class="flex items-center justify-between gap-3 text-xs text-ink-muted">
            <span>Section {{ completedSections }} of 5 ready</span>
            <span class="font-mono">{{ progressPct }}%</span>
          </div>
          <div class="mt-2 h-2 rounded-full bg-surface">
            <div
              class="h-2 rounded-full bg-accent"
              :style="{ width: `${progressPct}%` }"
            />
          </div>
        </div>
        <div class="rounded-card border border-subtle bg-surface-muted p-4 text-xs text-ink-muted">
          <div class="font-semibold text-ink-primary">
            {{ editor.version_id || "v1" }} · {{ editor.status || "draft" }}
          </div>
          <div class="mt-1">Updated {{ editor.updated_at || "pending" }}</div>
        </div>
      </div>

      <div
        v-if="exportResult"
        class="mt-5 rounded-card border p-4"
        :class="exportResult.blocked ? 'border-warning bg-warning-soft text-warning-ink' : 'border-accent/30 bg-accent-soft/30 text-ink-primary'"
      >
        <div class="flex items-start gap-3">
          <AlertTriangle v-if="exportResult.blocked" class="mt-0.5 h-5 w-5 shrink-0" />
          <CheckCircle2 v-else class="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div>
            <div class="text-sm font-semibold">
              <template v-if="exportResult.blocked">
                {{ exportResult.block_reason }}
              </template>
              <template v-else>
                Export projection ready
              </template>
            </div>
            <p class="mt-1 text-xs opacity-80">
              {{ coverageLabel(exportResult) }}
            </p>
            <ul v-if="exportResult.blocked" class="mt-2 space-y-1 text-xs">
              <li
                v-for="item in exportResult.missing_sources"
                :key="`${item.location}-${item.text}`"
              >
                <span class="font-semibold">{{ item.location }}:</span>
                {{ item.terms.join(", ") }}
              </li>
            </ul>
          </div>
        </div>
      </div>
      <div v-if="exportError" class="mt-3 text-sm text-danger">{{ exportError }}</div>

      <section class="mt-6 rounded-card border border-subtle bg-surface-muted p-4">
        <div class="flex items-start gap-3">
          <FileText class="mt-1 h-5 w-5 text-accent" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-display text-lg font-semibold text-ink-primary">
                Executive Summary
              </h3>
              <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">
                {{ sections.executive_summary?.status || "not started" }}
              </span>
              <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">
                {{ sourceLabel(sections.executive_summary) }}
              </span>
              <button
                type="button"
                @click="rerunSection('executive_summary')"
                class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
              >
                Rerun
              </button>
            </div>
            <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
              {{ sections.executive_summary?.body }}
            </p>
            <div class="mt-3 grid gap-2 text-sm md:grid-cols-3">
              <div class="rounded-lg border border-subtle bg-surface p-3">
                <div class="vogue-label">Recommendation</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.recommendation }}</p>
              </div>
              <div class="rounded-lg border border-subtle bg-surface p-3">
                <div class="vogue-label">Round</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.round || "Pending" }}</p>
              </div>
              <div class="rounded-lg border border-subtle bg-surface p-3">
                <div class="vogue-label">Top Gate</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.top_gate }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-6">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Investment Thesis
          </h3>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-muted">{{ thesisCards.length }} cards</span>
            <button
              type="button"
              @click="rerunSection('investment_thesis')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              Rerun
            </button>
          </div>
        </div>
        <div class="space-y-3">
          <article
            v-for="card in thesisCards"
            :key="card.id"
            class="rounded-card border border-subtle border-l-4 bg-surface-muted p-4"
            :class="cardTone('investment_thesis', card)"
          >
            <div class="flex gap-3">
              <div class="flex w-12 shrink-0 flex-col items-center gap-1">
                <input
                  type="checkbox"
                  :checked="card.included"
                  @change="patchCard('investment_thesis', card, { included: $event.target.checked })"
                  class="h-4 w-4 rounded border-subtle text-accent focus-ring"
                  :aria-label="`Include ${card.title}`"
                />
                <span class="font-mono text-sm font-semibold text-ink-primary">{{ card.rank }}</span>
                <button
                  type="button"
                  @click="moveCard('investment_thesis', card, 'up')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  aria-label="Move thesis card up"
                >
                  <ArrowUp class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="moveCard('investment_thesis', card, 'down')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  aria-label="Move thesis card down"
                >
                  <ArrowDown class="h-3.5 w-3.5" />
                </button>
              </div>
              <div class="min-w-0 flex-1">
                <button
                  type="button"
                  @click="patchCard('investment_thesis', card, { expanded: !card.expanded })"
                  class="flex w-full items-start justify-between gap-3 text-left focus-ring"
                >
                  <span>
                    <span class="block text-base font-semibold text-ink-primary">{{ card.title }}</span>
                    <span class="mt-1 flex flex-wrap items-center gap-2">
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">{{ card.category }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">{{ sourceLabel(card) }}</span>
                      <span class="text-[11px] text-ink-muted">{{ sourceCount(card) }} sources</span>
                    </span>
                  </span>
                  <ChevronDown v-if="card.expanded" class="h-4 w-4 text-ink-muted" />
                  <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
                </button>
                <MemoStudioBulletTree
                  v-if="card.expanded"
                  class="mt-3"
                  :company-id="companyId"
                  section-id="investment_thesis"
                  :card-id="card.id"
                  :card-title="card.title"
                  :bullets="card.bullets || []"
                  @updated="applyState"
                  @discuss="discuss"
                />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="mt-6">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Risks and Mitigations
          </h3>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-muted">{{ riskCards.length }} cards</span>
            <button
              type="button"
              @click="rerunSection('risks_mitigations')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              Rerun
            </button>
          </div>
        </div>
        <div class="space-y-3">
          <article
            v-for="card in riskCards"
            :key="card.id"
            class="rounded-card border border-subtle border-l-4 bg-surface-muted p-4"
            :class="cardTone('risks_mitigations', card)"
          >
            <div class="flex gap-3">
              <div class="flex w-12 shrink-0 flex-col items-center gap-1">
                <input
                  type="checkbox"
                  :checked="card.included"
                  @change="patchCard('risks_mitigations', card, { included: $event.target.checked })"
                  class="h-4 w-4 rounded border-subtle text-accent focus-ring"
                  :aria-label="`Include ${card.title}`"
                />
                <span class="font-mono text-sm font-semibold text-ink-primary">{{ card.rank }}</span>
                <button
                  type="button"
                  @click="moveCard('risks_mitigations', card, 'up')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  aria-label="Move risk card up"
                >
                  <ArrowUp class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="moveCard('risks_mitigations', card, 'down')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  aria-label="Move risk card down"
                >
                  <ArrowDown class="h-3.5 w-3.5" />
                </button>
              </div>
              <div class="min-w-0 flex-1">
                <button
                  type="button"
                  @click="patchCard('risks_mitigations', card, { expanded: !card.expanded })"
                  class="flex w-full items-start justify-between gap-3 text-left focus-ring"
                >
                  <span>
                    <span class="block text-base font-semibold text-ink-primary">{{ card.title }}</span>
                    <span class="mt-1 flex flex-wrap items-center gap-2">
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">{{ card.category }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">{{ card.severity || "risk" }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">{{ sourceLabel(card) }}</span>
                    </span>
                  </span>
                  <ChevronDown v-if="card.expanded" class="h-4 w-4 text-ink-muted" />
                  <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
                </button>
                <MemoStudioBulletTree
                  v-if="card.expanded"
                  class="mt-3"
                  :company-id="companyId"
                  section-id="risks_mitigations"
                  :card-id="card.id"
                  :card-title="card.title"
                  :bullets="card.bullets || []"
                  @updated="applyState"
                  @discuss="discuss"
                />
              </div>
            </div>
          </article>
        </div>
      </section>

      <section class="mt-6 rounded-card border border-subtle bg-surface-muted p-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="font-display text-lg font-semibold text-ink-primary">Conclusion</h3>
          <button
            type="button"
            @click="rerunSection('conclusion')"
            class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            Rerun
          </button>
        </div>
        <div class="mt-3 grid gap-3 md:grid-cols-3">
          <button
            v-for="option in conclusion.options || []"
            :key="option.id"
            type="button"
            @click="selectConclusion(option)"
            class="rounded-card border p-4 text-left focus-ring"
            :class="conclusion.selected_option_id === option.id ? 'border-accent bg-accent-soft/40' : 'border-subtle bg-surface hover:border-strong'"
          >
            <div class="text-sm font-semibold text-ink-primary">{{ option.label }}</div>
            <p class="mt-2 text-sm leading-relaxed text-ink-muted">{{ option.text }}</p>
            <div class="mt-3 text-[11px] uppercase tracking-wide text-ink-muted">
              {{ sourceLabel(option) }}
            </div>
          </button>
        </div>
      </section>

      <section class="mt-6 rounded-card border border-subtle bg-surface-muted p-4">
        <div class="flex items-center justify-between">
          <h3 class="font-display text-lg font-semibold text-ink-primary">Appendix</h3>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-muted">Collapsed by default</span>
            <button
              type="button"
              @click="rerunSection('appendix')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              Rerun
            </button>
          </div>
        </div>
        <div class="mt-3 divide-y divide-subtle rounded-card border border-subtle bg-surface">
          <div
            v-for="block in appendixBlocks"
            :key="block.id"
            class="p-3"
          >
            <button
              type="button"
              @click="toggleAppendix(block)"
              class="flex w-full items-center justify-between gap-3 text-left focus-ring"
            >
              <span>
                <span class="font-semibold text-ink-primary">{{ block.title }}</span>
                <span class="ml-2 rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">
                  {{ block.status || "pending" }}
                </span>
                <span class="ml-2 rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] uppercase tracking-wide text-ink-muted">
                  {{ sourceLabel(block) }}
                </span>
              </span>
              <ChevronDown v-if="block.expanded" class="h-4 w-4 text-ink-muted" />
              <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
            </button>
            <ul v-if="block.expanded" class="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-secondary">
              <li v-for="fact in block.facts || []" :key="fact">{{ fact }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section class="mt-6 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div class="rounded-card border border-subtle bg-surface-muted p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="vogue-label">Co-pilot Tasks</div>
              <h3 class="font-display text-lg font-semibold text-ink-primary">
                Action queue
              </h3>
            </div>
            <span class="mono-data text-xs text-ink-muted">{{ memoTasks.length }}</span>
          </div>
          <div v-if="memoTasks.length === 0" class="mt-3 text-sm text-ink-muted">
            Discuss and Dive Deeper actions will create durable memo tasks here.
          </div>
          <div v-else class="mt-3 space-y-2">
            <article
              v-for="task in memoTasks"
              :key="task.id"
              class="rounded-row border border-subtle bg-surface p-3"
            >
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm font-semibold text-ink-primary">{{ task.title }}</div>
                  <p v-if="task.description" class="mt-1 text-xs leading-relaxed text-ink-muted">
                    {{ task.description }}
                  </p>
                </div>
                <span class="rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
                  {{ task.status }}
                </span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  @click="setTaskStatus(task, 'accepted')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'accepted'"
                  class="rounded-full bg-accent px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-50 focus-ring"
                >
                  Accept
                </button>
                <button
                  type="button"
                  @click="setTaskStatus(task, 'rejected')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'rejected'"
                  class="rounded-full border border-subtle px-2.5 py-1 text-[11px] font-semibold text-ink-secondary disabled:opacity-50 focus-ring"
                >
                  Reject
                </button>
                <button
                  type="button"
                  @click="setTaskStatus(task, 'completed')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'completed'"
                  class="rounded-full border border-subtle px-2.5 py-1 text-[11px] font-semibold text-ink-secondary disabled:opacity-50 focus-ring"
                >
                  Complete
                </button>
              </div>
            </article>
          </div>
          <div v-if="historyError" class="mt-3 text-xs text-danger">{{ historyError }}</div>
        </div>

        <div class="rounded-card border border-subtle bg-surface-muted p-4">
          <div class="vogue-label">Audit & Versions</div>
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Recoverable history
          </h3>
          <div class="mt-3 grid gap-2 sm:grid-cols-2">
            <div class="rounded-row border border-subtle bg-surface p-3">
              <div class="vogue-label text-[10px]">Revisions</div>
              <div class="mono-data mt-1 text-xl font-bold text-ink-primary">
                {{ versions.length }}
              </div>
            </div>
            <div class="rounded-row border border-subtle bg-surface p-3">
              <div class="vogue-label text-[10px]">Audit events</div>
              <div class="mono-data mt-1 text-xl font-bold text-ink-primary">
                {{ auditRecords.length }}
              </div>
            </div>
          </div>
          <div v-if="versions.length" class="mt-3 max-h-48 overflow-y-auto rounded-row border border-subtle bg-surface">
            <div
              v-for="version in versions.slice(0, 6)"
              :key="version.revision_id"
              class="border-b border-subtle px-3 py-2 last:border-0"
            >
              <div class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-ink-primary">{{ version.revision_id }}</span>
                <span class="text-ink-muted">{{ version.event }}</span>
              </div>
              <div class="mt-0.5 text-[11px] text-ink-muted">{{ version.created_at }}</div>
            </div>
          </div>
          <div v-if="auditRecords.length" class="mt-3 max-h-44 overflow-y-auto space-y-1 text-xs text-ink-muted">
            <div v-for="record in auditRecords.slice(0, 8)" :key="record.id" class="rounded bg-surface px-2 py-1">
              <span class="font-semibold text-ink-secondary">{{ record.event }}</span>
              <span> · {{ record.created_at }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
