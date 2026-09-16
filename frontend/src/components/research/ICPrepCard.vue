<script setup>
// Web twin of MacICPrepView.swift: readiness gates with progress, approval
// blockers, reviewable areas (with the review/waive sheet), the risk-cards
// disclosure, analysis tools with Run buttons, and the approve-for-memo row.
// Collapsed until asked — loading opens a Memo Studio session on the server.
import { computed, inject, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { formatRelativeTime } from "../../formatters.js";
import {
  ListChecks,
  RotateCw,
  CheckCircle2,
  Circle,
  CircleDashed,
  XCircle,
  MinusCircle,
  AlertTriangle,
  AlertCircle,
  BadgeCheck,
  FilePlus2,
  ChevronDown,
  ChevronRight,
} from "lucide-vue-next";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const openReportCustomizer = inject("openReportCustomizer", () => {});

const analysis = ref(null);
const busy = ref(false);
const loadError = ref(null);
const showRisks = ref(true);
const approving = ref(false);
const runningTools = ref(new Set());

// Review sheet state (MacReadinessReviewSheet)
const reviewArea = ref(null);
const reviewStatus = ref("reviewed");
const reviewRationale = ref("");
const reviewSaving = ref(false);
const reviewError = ref(null);

watch(
  () => props.companyId,
  () => {
    analysis.value = null;
    loadError.value = null;
    reviewArea.value = null;
  },
);

const readiness = computed(() => analysis.value?.readiness ?? null);
const gates = computed(() => readiness.value?.gates ?? []);
const blockers = computed(() => readiness.value?.approval_blockers ?? []);
const areas = computed(() => analysis.value?.additional_areas ?? []);
const tools = computed(() =>
  (analysis.value?.tools ?? []).filter((tool) => tool.visibility !== "hidden" && tool.stage !== "hidden"),
);

const risks = computed(() => analysis.value?.artifacts?.strategic_risks?.risks ?? []);

function riskOpen(risk) {
  return (risk.status ?? "unresearched") !== "researched" && risk.status !== "resolved" && risk.status !== "closed";
}

function severityRank(risk) {
  const s = (risk.severity || "medium").toLowerCase();
  if (s === "high") return 0;
  if (s === "medium") return 1;
  return 2;
}

const rankedRisks = computed(() =>
  [...risks.value].sort((a, b) => {
    if (riskOpen(a) !== riskOpen(b)) return riskOpen(a) ? -1 : 1;
    if (severityRank(a) !== severityRank(b)) return severityRank(a) - severityRank(b);
    return (a.title || "").localeCompare(b.title || "");
  }),
);

async function load() {
  busy.value = true;
  loadError.value = null;
  try {
    analysis.value = await api.memoAnalysis.get(props.companyId);
  } catch (err) {
    if (!analysis.value) loadError.value = err?.message || t("research_desk.icprep_load_failed");
  } finally {
    busy.value = false;
  }
}

async function runTool(tool) {
  if (runningTools.value.has(tool.name)) return;
  runningTools.value = new Set([...runningTools.value, tool.name]);
  try {
    await api.memoAnalysis.runTool(props.companyId, tool.name);
    await load();
  } catch {
    // the reload shows the tool's recorded error
  } finally {
    const next = new Set(runningTools.value);
    next.delete(tool.name);
    runningTools.value = next;
  }
}

function toolByName(name) {
  return (analysis.value?.tools ?? []).find((tool) => tool.name === name) || null;
}

function areaById(id) {
  return areas.value.find((area) => area.id === id) || null;
}

function openReview(area) {
  reviewArea.value = area;
  reviewStatus.value = area.status && area.status !== "open" ? area.status : "reviewed";
  reviewRationale.value = area.rationale || "";
  reviewError.value = null;
}

async function saveReview() {
  if (!reviewArea.value) return;
  const rationale = reviewRationale.value.trim();
  if (reviewStatus.value !== "open" && !rationale) return;
  reviewSaving.value = true;
  reviewError.value = null;
  try {
    await api.memoAnalysis.patchArtifact(props.companyId, "readiness_reviews", {
      items: [{ id: reviewArea.value.id, status: reviewStatus.value, rationale }],
    });
    await load();
    reviewArea.value = null;
  } catch (err) {
    reviewError.value = err?.message || t("research_desk.icprep_review_failed");
  } finally {
    reviewSaving.value = false;
  }
}

async function approve() {
  approving.value = true;
  try {
    await api.memoAnalysis.approve(props.companyId);
    await load();
  } catch {
    // reload shows the truth
  } finally {
    approving.value = false;
  }
}

function toolIcon(tool) {
  if (tool.status === "done") return CheckCircle2;
  if (tool.status === "running" || runningTools.value.has(tool.name)) return CircleDashed;
  if (tool.status === "error") return XCircle;
  return Circle;
}

function toolTint(tool) {
  if (tool.status === "done") return "var(--mac-green)";
  if (tool.status === "error") return "var(--mac-red)";
  return "var(--mac-secondary)";
}

function riskStatusText(risk) {
  return String(risk.status || "unresearched")
    .replaceAll("_", " ")
    .replace(/^./, (ch) => ch.toUpperCase());
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-3">
    <!-- Label("IC prep", checklist) · gates · load/refresh -->
    <div class="flex items-center gap-2">
      <ListChecks class="mac-c-accent h-4 w-4" stroke-width="2.2" />
      <span class="mac-t-headline">{{ t("research_desk.ic_prep_title") }}</span>
      <span
        v-if="readiness"
        class="mac-t-caption10 mac-mono font-semibold"
        :style="{ color: readiness.ready_for_memo ? 'var(--mac-green)' : 'var(--mac-orange)' }"
      >
        {{ t("research_desk.icprep_gates", { score: readiness.score || 0, total: readiness.total || 0 }) }}
      </span>
      <span class="flex-1" />
      <span v-if="busy" class="mac-spinner" />
      <button
        v-if="!analysis"
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="busy"
        @click="load"
      >
        {{ busy ? t("research_desk.loading_ellipsis") : (loadError == null ? t("research_desk.icprep_load") : t("research_desk.retry")) }}
      </button>
      <button
        v-else
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="busy"
        :title="t('research_desk.refresh')"
        @click="load"
      >
        <RotateCw class="h-3 w-3" />
      </button>
    </div>

    <template v-if="analysis">
      <!-- Gates + progress -->
      <div v-if="readiness" class="flex flex-col gap-1.5">
        <div class="h-1 w-full overflow-hidden rounded-full" style="background: color-mix(in srgb, var(--mac-secondary) 15%, transparent)">
          <div
            class="h-full rounded-full transition-all duration-500"
            :style="{
              width: `${Math.round((readiness.pct || 0) * 100)}%`,
              background: readiness.ready_for_memo ? 'var(--mac-green)' : 'var(--mac-orange)',
            }"
          />
        </div>
        <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          <span v-for="gate in gates" :key="gate.id" class="flex items-center gap-1.5">
            <component
              :is="gate.status === 'done' ? CheckCircle2 : Circle"
              class="h-3.5 w-3.5 shrink-0"
              :style="{ color: gate.status === 'done' ? 'var(--mac-green)' : 'var(--mac-secondary)' }"
            />
            <span class="mac-t-caption10 truncate">{{ gate.label || gate.id }}</span>
          </span>
        </div>
      </div>

      <!-- Blocking approval -->
      <div v-if="blockers.length" class="flex flex-col gap-1.5">
        <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icprep_blocking") }}</span>
        <div
          v-for="blocker in blockers"
          :key="blocker.id"
          class="flex items-start gap-2 rounded-md p-2"
          style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
        >
          <component
            :is="blocker.severity === 'high' ? AlertTriangle : AlertCircle"
            class="mt-px h-3.5 w-3.5 shrink-0"
            :style="{ color: blocker.severity === 'high' ? 'var(--mac-red)' : 'var(--mac-orange)' }"
          />
          <span class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="mac-t-caption10 font-medium">{{ blocker.label || blocker.id }}</span>
            <span v-if="blocker.reason" class="mac-t-caption10 mac-c-secondary">{{ blocker.reason }}</span>
          </span>
          <button
            v-if="blocker.tool && toolByName(blocker.tool)"
            type="button"
            class="mac-btn mac-btn--sm shrink-0"
            :disabled="runningTools.has(blocker.tool)"
            :title="toolByName(blocker.tool)?.description || ''"
            @click="runTool(toolByName(blocker.tool))"
          >
            {{ toolByName(blocker.tool)?.status === "done" ? t("research_desk.icprep_rerun") : t("research_desk.icprep_run") }}
          </button>
          <button
            v-else-if="blocker.kind === 'additional_area' && areaById(blocker.id)"
            type="button"
            class="mac-btn mac-btn--sm shrink-0"
            @click="openReview(areaById(blocker.id))"
          >
            {{ t("research_desk.icprep_review") }}
          </button>
        </div>
      </div>

      <!-- Areas to review -->
      <div v-if="areas.length" class="flex flex-col gap-1.5">
        <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icprep_areas") }}</span>
        <div v-for="area in areas" :key="area.id" class="flex items-center gap-2">
          <component
            :is="(area.status ?? 'open') === 'open' ? Circle : area.status === 'waived' ? MinusCircle : CheckCircle2"
            class="h-3.5 w-3.5 shrink-0"
            :style="{
              color:
                (area.status ?? 'open') === 'open'
                  ? 'var(--mac-secondary)'
                  : area.status === 'waived'
                    ? 'var(--mac-orange)'
                    : 'var(--mac-green)',
            }"
          />
          <span class="flex min-w-0 flex-1 flex-col gap-px">
            <span class="mac-t-caption10 font-medium">{{ area.area || area.id }}</span>
            <span v-if="area.why_it_matters" class="mac-t-caption10 mac-c-secondary line-clamp-2">
              {{ area.why_it_matters }}
            </span>
            <span v-if="area.rationale" class="mac-t-caption10 mac-c-tertiary line-clamp-2">
              ↳ {{ area.rationale }}
            </span>
          </span>
          <button type="button" class="mac-btn mac-btn--sm shrink-0" @click="openReview(area)">
            {{ (area.status ?? "open") === "open" ? t("research_desk.icprep_review") : t("research_desk.icprep_edit") }}
          </button>
        </div>
      </div>

      <!-- Risk cards -->
      <div v-if="rankedRisks.length" class="flex flex-col gap-1.5">
        <button
          type="button"
          class="mac-t-caption10 mac-c-secondary flex items-center gap-1 border-none bg-transparent p-0 font-semibold"
          @click="showRisks = !showRisks"
        >
          <component :is="showRisks ? ChevronDown : ChevronRight" class="h-3 w-3" />
          {{ t("research_desk.icprep_risk_cards", { total: risks.length, open: risks.filter(riskOpen).length }) }}
        </button>
        <template v-if="showRisks">
          <div
            v-for="risk in rankedRisks.slice(0, 8)"
            :key="risk.id"
            class="flex items-start gap-2 rounded-md p-1.5"
            style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
          >
            <span
              class="mac-status-pill shrink-0"
              :style="{
                '--tint':
                  risk.severity === 'high'
                    ? 'var(--mac-red)'
                    : risk.severity === 'low'
                      ? 'var(--mac-secondary)'
                      : 'var(--mac-orange)',
              }"
            >
              {{ (risk.severity || "medium").replace(/^./, (c) => c.toUpperCase()) }}
            </span>
            <span class="flex min-w-0 flex-1 flex-col gap-0.5">
              <span class="mac-t-caption10 font-semibold">{{ risk.title || risk.id }}</span>
              <span v-if="risk.why_it_matters || risk.description" class="mac-t-caption10 mac-c-secondary line-clamp-2">
                {{ risk.why_it_matters || risk.description }}
              </span>
            </span>
            <span
              class="mac-t-caption10 shrink-0"
              :style="{ color: riskOpen(risk) ? 'var(--mac-orange)' : 'var(--mac-green)' }"
            >
              {{ riskStatusText(risk) }}
            </span>
          </div>
        </template>
      </div>

      <!-- Analysis tools -->
      <div class="flex flex-col gap-1.5">
        <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icprep_tools") }}</span>
        <div v-for="tool in tools" :key="tool.name" class="flex items-center gap-2">
          <component :is="toolIcon(tool)" class="h-3.5 w-3.5 shrink-0" :style="{ color: toolTint(tool) }" />
          <span class="flex min-w-0 flex-1 flex-col gap-px">
            <span class="flex items-center gap-1">
              <span class="mac-t-caption10 font-medium">{{ tool.label || tool.name }}</span>
              <span v-if="tool.critical" class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.icprep_core") }}</span>
            </span>
            <span
              v-if="tool.error || tool.summary"
              class="mac-t-caption10 truncate"
              :style="tool.error ? { color: 'var(--mac-red)' } : { color: 'var(--mac-secondary)' }"
            >
              {{ tool.error || tool.summary }}
            </span>
          </span>
          <span v-if="tool.status === 'running' || runningTools.has(tool.name)" class="mac-spinner" style="width: 11px; height: 11px" />
          <button
            type="button"
            class="mac-btn mac-btn--sm shrink-0"
            :disabled="tool.status === 'running' || runningTools.has(tool.name)"
            :title="tool.description || ''"
            @click="runTool(tool)"
          >
            {{ tool.status === "done" ? t("research_desk.icprep_rerun") : t("research_desk.icprep_run") }}
          </button>
        </div>
      </div>

      <div class="mac-divider" />

      <!-- Approval → memo -->
      <div class="flex flex-wrap items-center gap-2.5">
        <template v-if="analysis.approved_for_memo">
          <span class="mac-t-caption10 flex items-center gap-1.5 font-semibold" :style="{ color: 'var(--mac-green)' }">
            <BadgeCheck class="h-3.5 w-3.5" />
            {{ t("research_desk.icprep_approved", { when: formatRelativeTime(analysis.approved_at) }) }}
          </span>
          <span class="flex-1" />
          <button type="button" class="mac-btn mac-btn--prominent" @click="openReportCustomizer(companyId)">
            <FilePlus2 class="h-3.5 w-3.5" />
            <span>{{ t("research_desk.icprep_generate") }}</span>
          </button>
        </template>
        <template v-else>
          <span class="mac-t-caption10 mac-c-secondary">
            {{
              readiness?.ready_for_approval
                ? t("research_desk.icprep_ready_hint")
                : t("research_desk.icprep_blocked_hint")
            }}
          </span>
          <span class="flex-1" />
          <button
            type="button"
            class="mac-btn mac-btn--prominent"
            :disabled="approving || readiness?.ready_for_approval !== true"
            @click="approve"
          >
            {{ approving ? t("research_desk.icprep_approving") : t("research_desk.icprep_approve") }}
          </button>
        </template>
      </div>
    </template>

    <span v-else-if="loadError" class="mac-t-caption10" :style="{ color: 'var(--mac-red)' }">{{ loadError }}</span>
    <span v-else-if="!busy" class="mac-t-caption10 mac-c-secondary">
      {{ t("research_desk.icprep_collapsed_hint") }}
    </span>

    <!-- MacReadinessReviewSheet -->
    <div
      v-if="reviewArea"
      class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-4"
      style="background: transparent"
      role="dialog"
      aria-modal="true"
    >
      <div class="fixed inset-0" style="background: rgba(0, 0, 0, 0.28)" @click="reviewArea = null" />
      <div
        class="relative flex w-full max-w-[460px] flex-col gap-3.5 rounded-[12px] p-5"
        style="background: var(--mac-canvas); box-shadow: 0 0 0 1px var(--mac-hairline), 0 24px 60px rgba(0, 0, 0, 0.35)"
      >
        <span class="mac-t-headline-sys">{{ reviewArea.area || reviewArea.id }}</span>
        <span v-if="reviewArea.why_it_matters" class="mac-t-callout mac-c-secondary">
          {{ reviewArea.why_it_matters }}
        </span>

        <div class="flex items-center gap-4">
          <span class="mac-t-body shrink-0">{{ t("research_desk.icprep_status") }}</span>
          <span class="flex-1" />
          <div class="mac-segmented w-[250px]">
            <button
              v-for="opt in ['reviewed', 'waived', 'open']"
              :key="opt"
              type="button"
              class="mac-segment"
              :class="{ 'is-selected': reviewStatus === opt }"
              @click="reviewStatus = opt; reviewError = null"
            >
              {{ t(`research_desk.icprep_status_${opt}`) }}
            </button>
          </div>
        </div>

        <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ t("research_desk.icprep_rationale") }}</span>
        <textarea
          v-model="reviewRationale"
          rows="4"
          class="mac-field w-full resize-y"
          style="min-height: 100px; line-height: 1.4"
          @input="reviewError = null"
        />

        <span v-if="reviewError" class="mac-t-caption" :style="{ color: 'var(--mac-red)' }">{{ reviewError }}</span>

        <div class="flex items-center">
          <button type="button" class="mac-btn" @click="reviewArea = null">
            {{ t("research_desk.cancel") }}
          </button>
          <span class="flex-1" />
          <button
            type="button"
            class="mac-btn mac-btn--prominent"
            :disabled="reviewSaving || (reviewStatus !== 'open' && !reviewRationale.trim())"
            @click="saveReview"
          >
            {{ reviewSaving ? t("research_desk.saving") : t("research_desk.icprep_save") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
