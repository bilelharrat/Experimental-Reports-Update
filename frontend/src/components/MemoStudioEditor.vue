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
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { formatIsoDate, humanizeStatus } from "../formatters.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import MemoStudioBulletTree from "./memo/MemoStudioBulletTree.vue";

const props = defineProps({
  companyId: { type: String, required: true },
  generateAvailable: { type: Boolean, default: false },
  generating: { type: Boolean, default: false },
  // Bumped by the parent when an investigation seeds fresh cards, so an
  // already-mounted editor reloads instead of showing stale state.
  refreshKey: { type: String, default: "" },
});

const emit = defineEmits(["discuss", "generate"]);
const t = useT();

const editor = ref(null);
const loading = ref(true);
const error = ref("");
const savingId = ref("");
const exportResult = ref(null);
const exportError = ref("");
const exporting = ref(false);
const history = ref({ versions: [], audit_records: [], memo_tasks: [] });
const historyError = ref("");
const errorMessage = computed(() =>
  error.value === "load" ? t("memo.load_error") : t("memo.action_failed"),
);
const historyErrorMessage = computed(() =>
  historyError.value === "load" ? t("memo.history_error") : t("memo.action_failed"),
);
const exportErrorMessage = computed(() => t("memo.export_error"));

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
const memoTasks = computed(() => {
  const rows = history.value?.memo_tasks || editor.value?.memo_tasks || [];
  const seen = new Set();
  return rows.filter((task) => {
    const signature = `${task.title || ""}|${task.description || ""}`
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
    if (!signature || seen.has(signature)) return false;
    seen.add(signature);
    return true;
  });
});
const auditRecords = computed(() => history.value?.audit_records || editor.value?.audit_records || []);
const versions = computed(() => history.value?.versions || []);
const completedSections = computed(() =>
  sectionIds.filter((id) => {
    const status = String(sections.value[id]?.status || "").toLowerCase();
    return ["done", "complete", "completed", "approved", "ready"].includes(status);
  }).length,
);
const progressPct = computed(() =>
  Math.round((completedSections.value / sectionIds.length) * 100),
);

function orderedCards(sectionId) {
  const cards = sections.value[sectionId]?.cards || [];
  const seen = new Set();
  return [...cards]
    .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0))
    .filter((card) => {
      const bulletText = (card.bullets || []).map((bullet) => bullet.text || "").join("|");
      const signature = `${card.title || ""}|${bulletText}`.toLowerCase().replace(/\s+/g, " ").trim();
      if (!signature || seen.has(signature)) return false;
      seen.add(signature);
      return true;
    });
}

const agentRun = computed(() => editor.value?.agent_run || null);
const includedRiskCount = computed(
  () => riskCards.value.filter((card) => card.included).length,
);
const riskCountWarning = computed(
  () => includedRiskCount.value < 4 || includedRiskCount.value > 6,
);

const RATING_OPTIONS = Array.from({ length: 10 }, (_, i) => `${10 - i}/10`);
const LIKELIHOOD_OPTIONS = ["High", "Medium", "Low"];

function severityFromRating(rating) {
  const value = Number.parseInt(String(rating || ""), 10);
  if (!Number.isFinite(value)) return "medium";
  if (value >= 8) return "high";
  if (value >= 5) return "medium";
  return "low";
}

function likelihoodLabel(value) {
  if (value === "High") return t("memo.likelihood_high");
  if (value === "Medium") return t("memo.likelihood_medium");
  if (value === "Low") return t("memo.likelihood_low");
  return value;
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
  return item?.source_class || item?.source_refs?.[0]?.source_class || t("memo.source_pending");
}

function sourceCount(item) {
  return Array.isArray(item?.source_refs) ? item.source_refs.length : 0;
}

function coverageLabel(result) {
  const coverage = result?.source_coverage;
  if (!coverage) return t("memo.coverage_pending");
  return t("memo.source_coverage", { pct: Math.round((coverage.coverage || 0) * 100) });
}

async function load() {
  loading.value = true;
  error.value = "";
  exportResult.value = null;
  try {
    editor.value = await api.memoEditor.get(props.companyId);
    await loadHistory();
  } catch {
    error.value = "load";
  } finally {
    loading.value = false;
  }
}

async function loadHistory() {
  historyError.value = "";
  try {
    history.value = await api.memoEditor.history(props.companyId);
  } catch {
    historyError.value = "load";
    history.value = {
      versions: [],
      audit_records: editor.value?.audit_records || [],
      memo_tasks: editor.value?.memo_tasks || [],
    };
  }
}

onMounted(load);
watch(() => props.companyId, load);
watch(
  () => props.refreshKey,
  () => {
    load();
  },
);

function applyState(state) {
  editor.value = state;
  exportResult.value = null;
  loadHistory();
}

async function patchCard(sectionId, card, patch) {
  savingId.value = `${sectionId}:${card.id}`;
  try {
    applyState(await api.memoEditor.patchCard(props.companyId, sectionId, card.id, patch));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function moveCard(sectionId, card, direction) {
  savingId.value = `${sectionId}:${card.id}:move`;
  try {
    applyState(await api.memoEditor.moveCard(props.companyId, sectionId, card.id, direction));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

const addingSection = ref("");
const newCardTitle = ref("");

function toggleAddCard(sectionId) {
  if (addingSection.value === sectionId) {
    addCard(sectionId);
    return;
  }
  addingSection.value = sectionId;
  newCardTitle.value = "";
}

async function addCard(sectionId) {
  const title = newCardTitle.value.trim();
  if (!title) {
    addingSection.value = "";
    return;
  }
  savingId.value = `add:${sectionId}`;
  try {
    applyState(
      await api.memoEditor.addCard(props.companyId, sectionId, { title }),
    );
    newCardTitle.value = "";
    addingSection.value = "";
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function removeCard(sectionId, card) {
  savingId.value = `remove:${sectionId}:${card.id}`;
  try {
    applyState(
      await api.memoEditor.deleteCard(props.companyId, sectionId, card.id),
    );
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function setRiskRating(card, rating) {
  await patchCard("risks_mitigations", card, {
    agent_rating: rating,
    // Keep the severity tone in sync with the pinned rating.
    severity: severityFromRating(rating),
  });
}

async function setRiskLikelihood(card, likelihood) {
  await patchCard("risks_mitigations", card, { likelihood });
}

async function selectConclusion(option) {
  savingId.value = `conclusion:${option.id}`;
  try {
    applyState(await api.memoEditor.selectConclusion(props.companyId, option.id));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function rerunSection(sectionId) {
  savingId.value = `rerun:${sectionId}`;
  try {
    applyState(await api.memoEditor.rerunSection(props.companyId, sectionId));
  } catch {
    error.value = "action";
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
  } catch {
    error.value = "action";
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
  } catch {
    exportError.value = "export";
  } finally {
    exporting.value = false;
  }
}

async function discuss(context) {
  const taskPayload = {
    action_type: "discuss",
    title: t("memo.discuss_title", { point: context.card_title || context.bullet_text || t("memo.memo_point") }),
    description: context.bullet_text || t("memo.discuss_description"),
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
  } catch {
    historyError.value = "action";
  }
  emit("discuss", taskPayload.context);
}

async function setTaskStatus(task, status) {
  savingId.value = `task:${task.id}`;
  historyError.value = "";
  try {
    await api.memoEditor.updateTask(props.companyId, task.id, { status });
    await loadHistory();
  } catch {
    historyError.value = "action";
  } finally {
    savingId.value = "";
  }
}
</script>

<template>
  <section class="bg-surface border border-subtle rounded-card shadow-card p-6">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="vogue-label">{{ t("memo.eyebrow") }}</div>
        <h2 class="font-display text-xl font-semibold text-ink-primary">
          {{ t("memo.title") }}
        </h2>
        <p class="mt-1 max-w-3xl text-sm text-ink-muted">
          {{ t("memo.subtitle") }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          @click="load"
          class="inline-flex items-center gap-2 rounded-full border border-subtle px-3 py-2 text-xs font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
        >
          <RefreshCw class="h-4 w-4" />
          {{ t("common.refresh") }}
        </button>
        <button
          type="button"
          @click="projectExport"
          :disabled="exporting || loading"
          class="btn-filled rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="exporting" class="h-4 w-4 animate-spin" />
          <Download v-else class="h-4 w-4" />
          {{ t("memo.export") }}
        </button>
        <button
          v-if="generateAvailable"
          type="button"
          @click="emit('generate')"
          :disabled="generating || loading"
          class="btn-filled rounded-full px-4 py-2 text-xs font-semibold disabled:opacity-60 focus-ring"
        >
          <Loader2 v-if="generating" class="h-4 w-4 animate-spin" />
          <Sparkles v-else class="h-4 w-4" />
          {{ t("memo.generate_report") }}
        </button>
      </div>
    </div>

    <div
      v-if="agentRun"
      class="mt-3 rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-secondary"
    >
      {{
        t("memo.seeded_from_run", {
          mode: agentRun.mode,
          date: formatIsoDate(agentRun.seeded_at),
        })
      }}
    </div>
    <div
      v-else-if="!loading && editor"
      class="mt-3 rounded-lg border border-notice/40 bg-notice-soft/40 px-3 py-2 text-xs text-ink-secondary"
    >
      {{ t("memo.no_agent_seed") }}
    </div>

    <div v-if="loading" class="mt-5 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      {{ t("memo.loading") }}
    </div>
    <div v-else-if="error" class="mt-5 rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
      {{ errorMessage }}
    </div>

    <template v-else-if="editor">
      <div class="mt-5 grid gap-3 md:grid-cols-[1fr_auto]">
        <div class="rounded-card bg-surface-muted p-4">
          <div class="flex items-center justify-between gap-3 text-xs text-ink-muted">
            <span>{{ t("memo.readiness", { ready: completedSections, total: sectionIds.length }) }}</span>
            <span class="font-mono">{{ progressPct }}%</span>
          </div>
          <div class="mt-2 h-2 rounded-full bg-surface">
            <div
              class="h-2 rounded-full bg-accent"
              :style="{ width: `${progressPct}%` }"
            />
          </div>
        </div>
        <div class="rounded-card bg-surface-muted p-4 text-xs text-ink-muted">
          <div class="font-semibold text-ink-primary">
            {{ editor.version_id || "v1" }} · {{ humanizeStatus(editor.status, t("memo.draft"), appLanguage) }}
          </div>
          <div class="mono-data mt-1">{{ t("memo.updated") }} {{ formatIsoDate(editor.updated_at, t("memo.pending")) }}</div>
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
                {{ t("memo.export_ready") }}
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
      <div v-if="exportError" class="mt-3 text-sm text-danger">{{ exportErrorMessage }}</div>

      <section class="mt-6">
        <div class="flex flex-wrap items-end justify-between gap-3 border-b border-subtle pb-3">
          <div class="flex items-baseline gap-3">
            <span class="mono-data text-xs font-bold text-accent-ink">01</span>
            <h3 class="font-display text-[22px] font-bold text-ink-primary">{{ t("memo.executive_summary") }}</h3>
          </div>
          <div class="flex flex-wrap items-center gap-2">
              <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
              {{ humanizeStatus(sections.executive_summary?.status, t("memo.not_started"), appLanguage) }}
              </span>
              <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
                {{ sourceLabel(sections.executive_summary) }}
              </span>
              <button
                type="button"
                @click="rerunSection('executive_summary')"
                class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
              >
              {{ t("memo.rerun") }}
              </button>
          </div>
        </div>
        <div class="mt-3 rounded-card border border-subtle border-l-4 border-l-accent bg-surface p-4">
            <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
              {{ sections.executive_summary?.body }}
            </p>
            <div class="mt-3 grid gap-2 text-sm md:grid-cols-3">
              <div class="rounded-card bg-surface shadow-card p-3">
                <div class="vogue-label">{{ t("memo.recommendation") }}</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.recommendation }}</p>
              </div>
              <div class="rounded-card bg-surface shadow-card p-3">
                <div class="vogue-label">{{ t("memo.round") }}</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.round || t("memo.pending") }}</p>
              </div>
              <div class="rounded-card bg-surface shadow-card p-3">
                <div class="vogue-label">{{ t("memo.top_gate") }}</div>
                <p class="mt-1 text-ink-secondary">{{ sections.executive_summary?.top_gate }}</p>
              </div>
            </div>
        </div>
      </section>

      <section class="mt-6">
        <div class="mb-3 flex items-end justify-between gap-3 border-b border-subtle pb-3">
          <div class="flex items-baseline gap-3">
            <span class="mono-data text-xs font-bold text-accent-ink">02</span>
            <h3 class="font-display text-[22px] font-bold text-ink-primary">{{ t("memo.investment_thesis") }}</h3>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-muted">{{ t("memo.card_count", { count: thesisCards.length }) }}</span>
            <input
              v-if="addingSection === 'investment_thesis'"
              v-model="newCardTitle"
              :placeholder="t('memo.new_card_title')"
              class="field focus-ring w-48 px-2 py-1 text-xs"
              @keyup.enter="addCard('investment_thesis')"
            />
            <button
              type="button"
              @click="toggleAddCard('investment_thesis')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              {{ addingSection === 'investment_thesis' ? t("memo.save_card") : t("memo.add_card") }}
            </button>
            <button
              type="button"
              @click="rerunSection('investment_thesis')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              {{ t("memo.rerun") }}
            </button>
          </div>
        </div>
        <div class="space-y-3">
          <article
            v-for="card in thesisCards"
            :key="card.id"
            class="rounded-card border border-subtle border-l-4 bg-surface p-4"
            :class="cardTone('investment_thesis', card)"
          >
            <div class="flex gap-3">
              <div class="flex w-12 shrink-0 flex-col items-center gap-1">
                <input
                  type="checkbox"
                  :checked="card.included"
                  @change="patchCard('investment_thesis', card, { included: $event.target.checked })"
                  class="memo-checkbox focus-ring"
                  :aria-label="t('memo.include_card', { title: card.title })"
                />
                <span class="font-mono text-sm font-semibold text-ink-primary">{{ card.rank }}</span>
                <button
                  type="button"
                  @click="moveCard('investment_thesis', card, 'up')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  :aria-label="t('memo.move_card_up')"
                >
                  <ArrowUp class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="moveCard('investment_thesis', card, 'down')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  :aria-label="t('memo.move_card_down')"
                >
                  <ArrowDown class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="removeCard('investment_thesis', card)"
                  class="rounded-full p-1 text-ink-muted hover:text-danger focus-ring"
                  :aria-label="t('memo.remove_card')"
                >
                  <X class="h-3.5 w-3.5" />
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
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">{{ card.category }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">{{ sourceLabel(card) }}</span>
                      <span class="text-[11px] text-ink-muted">{{ t("memo.source_count", { count: sourceCount(card) }) }}</span>
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
        <div class="mb-3 flex items-end justify-between gap-3 border-b border-subtle pb-3">
          <div class="flex items-baseline gap-3">
            <span class="mono-data text-xs font-bold text-danger-ink">03</span>
            <h3 class="font-display text-[22px] font-bold text-ink-primary">{{ t("memo.risks") }}</h3>
          </div>
          <div class="flex items-center gap-2">
            <span
              v-if="riskCountWarning"
              class="text-xs font-semibold text-warning-ink"
            >
              {{ t("memo.risk_count_hint", { count: includedRiskCount }) }}
            </span>
            <span class="text-xs text-ink-muted">{{ t("memo.card_count", { count: riskCards.length }) }}</span>
            <input
              v-if="addingSection === 'risks_mitigations'"
              v-model="newCardTitle"
              :placeholder="t('memo.new_card_title')"
              class="field focus-ring w-48 px-2 py-1 text-xs"
              @keyup.enter="addCard('risks_mitigations')"
            />
            <button
              type="button"
              @click="toggleAddCard('risks_mitigations')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              {{ addingSection === 'risks_mitigations' ? t("memo.save_card") : t("memo.add_card") }}
            </button>
            <button
              type="button"
              @click="rerunSection('risks_mitigations')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              {{ t("memo.rerun") }}
            </button>
          </div>
        </div>
        <div class="space-y-3">
          <article
            v-for="card in riskCards"
            :key="card.id"
            class="rounded-card border border-subtle border-l-4 bg-surface p-4"
            :class="cardTone('risks_mitigations', card)"
          >
            <div class="flex gap-3">
              <div class="flex w-12 shrink-0 flex-col items-center gap-1">
                <input
                  type="checkbox"
                  :checked="card.included"
                  @change="patchCard('risks_mitigations', card, { included: $event.target.checked })"
                  class="memo-checkbox focus-ring"
                  :aria-label="t('memo.include_card', { title: card.title })"
                />
                <span class="font-mono text-sm font-semibold text-ink-primary">{{ card.rank }}</span>
                <button
                  type="button"
                  @click="moveCard('risks_mitigations', card, 'up')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  :aria-label="t('memo.move_card_up')"
                >
                  <ArrowUp class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="moveCard('risks_mitigations', card, 'down')"
                  class="rounded-full p-1 text-ink-muted hover:bg-surface focus-ring"
                  :aria-label="t('memo.move_card_down')"
                >
                  <ArrowDown class="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  @click="removeCard('risks_mitigations', card)"
                  class="rounded-full p-1 text-ink-muted hover:text-danger focus-ring"
                  :aria-label="t('memo.remove_card')"
                >
                  <X class="h-3.5 w-3.5" />
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
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">{{ card.category }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">{{ card.severity || t("memo.risk") }}</span>
                      <span class="rounded-full border border-subtle bg-surface px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">{{ sourceLabel(card) }}</span>
                    </span>
                  </span>
                  <ChevronDown v-if="card.expanded" class="h-4 w-4 text-ink-muted" />
                  <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
                </button>
                <div class="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
                  <label class="flex items-center gap-1 text-ink-muted">
                    {{ t("memo.rating") }}
                    <select
                      :value="card.agent_rating || ''"
                      @change="setRiskRating(card, $event.target.value)"
                      class="field focus-ring w-20 px-1.5 py-0.5 text-[11px]"
                    >
                      <option value="">—</option>
                      <option v-for="option in RATING_OPTIONS" :key="option" :value="option">
                        {{ option }}
                      </option>
                    </select>
                  </label>
                  <label class="flex items-center gap-1 text-ink-muted">
                    {{ t("memo.likelihood") }}
                    <select
                      :value="card.likelihood || ''"
                      @change="setRiskLikelihood(card, $event.target.value)"
                      class="field focus-ring w-24 px-1.5 py-0.5 text-[11px]"
                    >
                      <option value="">—</option>
                      <option v-for="option in LIKELIHOOD_OPTIONS" :key="option" :value="option">
                        {{ likelihoodLabel(option) }}
                      </option>
                    </select>
                  </label>
                </div>
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

      <section class="mt-6">
        <div class="flex items-end justify-between gap-3 border-b border-subtle pb-3">
          <div class="flex items-baseline gap-3">
            <span class="mono-data text-xs font-bold text-accent-ink">04</span>
            <h3 class="font-display text-[22px] font-bold text-ink-primary">{{ t("memo.conclusion") }}</h3>
          </div>
          <button
            type="button"
            @click="rerunSection('conclusion')"
            class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
          >
            {{ t("memo.rerun") }}
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
            <div class="mt-3 text-[11px] text-footnote font-semibold text-ink-muted">
              {{ sourceLabel(option) }}
            </div>
          </button>
        </div>
      </section>

      <section class="mt-6">
        <div class="flex items-end justify-between gap-3 border-b border-subtle pb-3">
          <div class="flex items-baseline gap-3">
            <span class="mono-data text-xs font-bold text-accent-ink">05</span>
            <h3 class="font-display text-[22px] font-bold text-ink-primary">{{ t("memo.appendix") }}</h3>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-muted">{{ t("memo.collapsed_default") }}</span>
            <button
              type="button"
              @click="rerunSection('appendix')"
              class="rounded-full border border-subtle bg-surface px-2 py-1 text-[11px] font-semibold text-ink-secondary hover:bg-surface-muted focus-ring"
            >
              {{ t("memo.rerun") }}
            </button>
          </div>
        </div>
        <div class="mt-3 divide-y divide-subtle rounded-card bg-surface">
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
                <span class="ml-2 rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
                  {{ humanizeStatus(block.status, t("memo.pending"), appLanguage) }}
                </span>
                <span class="ml-2 rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
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
        <div class="rounded-card bg-surface-muted p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="vogue-label">{{ t("memo.copilot_tasks") }}</div>
              <h3 class="font-display text-title3 text-ink-primary">
                {{ t("memo.action_queue") }}
              </h3>
            </div>
            <span class="mono-data text-xs text-ink-muted">{{ memoTasks.length }}</span>
          </div>
          <div v-if="memoTasks.length === 0" class="mt-3 text-sm text-ink-muted">
            {{ t("memo.action_queue_empty") }}
          </div>
          <div v-else class="mt-3 space-y-2">
            <article
              v-for="task in memoTasks"
              :key="task.id"
              class="rounded-row bg-fill-tertiary p-3"
            >
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="text-sm font-semibold text-ink-primary">{{ task.title }}</div>
                  <p v-if="task.description" class="mt-1 text-xs leading-relaxed text-ink-muted">
                    {{ task.description }}
                  </p>
                </div>
                <span class="rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-caption1 font-semibold text-ink-muted">
                  {{ humanizeStatus(task.status, t("memo.pending"), appLanguage) }}
                </span>
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  @click="setTaskStatus(task, 'accepted')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'accepted'"
                  class="btn-filled btn-sm px-2.5 text-[11px] focus-ring"
                >
                  {{ t("memo.accept") }}
                </button>
                <button
                  type="button"
                  @click="setTaskStatus(task, 'rejected')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'rejected'"
                  class="rounded-full border border-subtle px-2.5 py-1 text-[11px] font-semibold text-ink-secondary disabled:opacity-50 focus-ring"
                >
                  {{ t("memo.reject") }}
                </button>
                <button
                  type="button"
                  @click="setTaskStatus(task, 'completed')"
                  :disabled="savingId === `task:${task.id}` || task.status === 'completed'"
                  class="rounded-full border border-subtle px-2.5 py-1 text-[11px] font-semibold text-ink-secondary disabled:opacity-50 focus-ring"
                >
                  {{ t("memo.complete") }}
                </button>
              </div>
            </article>
          </div>
          <div v-if="historyError" class="mt-3 text-xs text-danger">{{ historyErrorMessage }}</div>
        </div>

        <div class="rounded-card bg-surface-muted p-4">
          <div class="vogue-label">{{ t("memo.audit_versions") }}</div>
          <h3 class="font-display text-title3 text-ink-primary">
            {{ t("memo.recoverable_history") }}
          </h3>
          <div class="mt-3 grid gap-2 sm:grid-cols-2">
            <div class="rounded-row bg-fill-tertiary p-3">
              <div class="vogue-label text-[10px]">{{ t("memo.revisions") }}</div>
              <div class="mono-data mt-1 text-xl font-bold text-ink-primary">
                {{ versions.length }}
              </div>
            </div>
            <div class="rounded-row bg-fill-tertiary p-3">
              <div class="vogue-label text-[10px]">{{ t("memo.audit_events") }}</div>
              <div class="mono-data mt-1 text-xl font-bold text-ink-primary">
                {{ auditRecords.length }}
              </div>
            </div>
          </div>
          <div v-if="versions.length" class="mt-3 max-h-48 overflow-y-auto rounded-row bg-fill-tertiary">
            <div
              v-for="version in versions.slice(0, 6)"
              :key="version.revision_id"
              class="border-b border-subtle px-3 py-2 last:border-0"
            >
              <div class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-ink-primary">{{ version.revision_id }}</span>
                <span class="text-ink-muted">{{ humanizeStatus(version.event, t("memo.pending"), appLanguage) }}</span>
              </div>
              <div class="mono-data mt-0.5 text-[11px] text-ink-muted">{{ formatIsoDate(version.created_at) }}</div>
            </div>
          </div>
          <div v-if="auditRecords.length" class="mt-3 max-h-44 overflow-y-auto space-y-1 text-xs text-ink-muted">
            <div v-for="record in auditRecords.slice(0, 8)" :key="record.id" class="rounded bg-surface px-2 py-1">
              <span class="font-semibold text-ink-secondary">{{ humanizeStatus(record.event, t("memo.pending"), appLanguage) }}</span>
              <span class="mono-data"> · {{ formatIsoDate(record.created_at) }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
