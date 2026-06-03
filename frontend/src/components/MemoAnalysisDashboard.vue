<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Gauge,
  Loader2,
  Play,
  Save,
  ShieldAlert,
  Sparkles,
} from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
});

const emit = defineEmits(["generate-memo"]);

const session = ref(null);
const loading = ref(false);
const error = ref(null);
const runningTool = ref(null);
const runningTask = ref(null);
const approving = ref(false);
const savingArtifact = ref(null);
const thesisDraft = ref(null);
const chartSpecsDraft = ref([]);
const narrativeDraft = ref(null);
const riskPriorityDraft = ref([]);
let taskPollId = null;
let taskPolling = false;

const artifacts = computed(() => session.value?.artifacts || {});
const risks = computed(() => artifacts.value.strategic_risks?.risks || []);
const riskPriorities = computed(() => {
  const priorities = artifacts.value.risk_priorities?.priorities;
  return Array.isArray(priorities) ? priorities : [];
});
const tasks = computed(() => artifacts.value.research_tasks?.tasks || []);
const hasRunningTasks = computed(() =>
  tasks.value.some((task) => task?.status === "running"),
);
const thesis = computed(() => artifacts.value.thesis_spine || null);
const chartSpecs = computed(() => artifacts.value.chart_specs?.specs || []);
const narrativeHooks = computed(() => artifacts.value.narrative_hooks || null);
const benchmark = computed(() => artifacts.value.benchmark_dashboard || null);
const readiness = computed(() => session.value?.readiness || { score: 0, total: 0, pct: 0, gates: [] });
const additionalAreas = computed(() => session.value?.additional_areas || []);
const approved = computed(() => Boolean(session.value?.approved_for_memo));
const thesisApproved = computed(() => Boolean(thesis.value?.approved));
const canGenerateMemo = computed(() => approved.value && thesisApproved.value);
const readinessPct = computed(() => Math.round((readiness.value.pct || 0) * 100));
const riskPriorityMap = computed(() => {
  const map = new Map();
  for (const row of riskPriorityDraft.value || []) {
    if (row?.risk_id) map.set(row.risk_id, row);
  }
  return map;
});
const prioritizedRisks = computed(() => {
  const sourceIndex = new Map(risks.value.map((risk, index) => [risk.id, index]));
  return [...risks.value].sort((a, b) => {
    const aRow = riskPriorityMap.value.get(a.id);
    const bRow = riskPriorityMap.value.get(b.id);
    const aRank = aRow?.rank ?? (sourceIndex.get(a.id) ?? 0) + 1;
    const bRank = bRow?.rank ?? (sourceIndex.get(b.id) ?? 0) + 1;
    return aRank - bRank || (sourceIndex.get(a.id) ?? 0) - (sourceIndex.get(b.id) ?? 0);
  });
});

function clone(value) {
  return value == null ? null : JSON.parse(JSON.stringify(value));
}

function toRank(value, fallback) {
  const rank = Number.parseInt(value, 10);
  return Number.isFinite(rank) && rank > 0 ? rank : fallback;
}

function normalizedRiskRows(rows) {
  return rows.map((row, index) => ({
    risk_id: row.risk_id,
    rank: index + 1,
    selected: Boolean(row.selected),
    rationale: row.rationale || "",
  }));
}

function buildRiskPriorityDraft() {
  const riskById = new Map(risks.value.map((risk) => [risk.id, risk]));
  const provided = [];
  const seen = new Set();
  for (const [index, row] of riskPriorities.value.entries()) {
    const riskId = row?.risk_id;
    if (!riskId || !riskById.has(riskId) || seen.has(riskId)) continue;
    seen.add(riskId);
    provided.push({
      risk_id: riskId,
      rank: toRank(row.rank, index + 1),
      selected: Boolean(row.selected),
      rationale: row.rationale || "",
      sourceIndex: index,
    });
  }
  provided.sort((a, b) => a.rank - b.rank || a.sourceIndex - b.sourceIndex);
  const missing = risks.value
    .filter((risk) => !seen.has(risk.id))
    .map((risk) => ({
      risk_id: risk.id,
      selected: false,
      rationale: "",
    }));
  return normalizedRiskRows([...provided, ...missing]);
}

function setRiskSelected(riskId, selected) {
  const row = riskPriorityMap.value.get(riskId);
  if (row) row.selected = selected;
}

function riskMoveIndex(riskId) {
  return riskPriorityDraft.value.findIndex((row) => row.risk_id === riskId);
}

function canMoveRisk(riskId, direction) {
  const index = riskMoveIndex(riskId);
  const nextIndex = index + direction;
  return index >= 0 && nextIndex >= 0 && nextIndex < riskPriorityDraft.value.length;
}

function moveRiskPriority(riskId, direction) {
  if (!canMoveRisk(riskId, direction)) return;
  const rows = [...riskPriorityDraft.value].sort((a, b) => a.rank - b.rank);
  const index = rows.findIndex((row) => row.risk_id === riskId);
  const nextIndex = index + direction;
  [rows[index], rows[nextIndex]] = [rows[nextIndex], rows[index]];
  riskPriorityDraft.value = normalizedRiskRows(rows);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.get(props.companyId);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loading.value = false;
  }
}

function clearTaskPolling() {
  if (taskPollId) {
    clearInterval(taskPollId);
    taskPollId = null;
  }
}

async function refreshRunningTasks() {
  if (taskPolling) return;
  if (!hasRunningTasks.value) {
    clearTaskPolling();
    return;
  }
  taskPolling = true;
  try {
    session.value = await api.memoAnalysis.get(props.companyId);
  } catch {
    // Keep the current session visible; the AI Tasks rail still shows logs.
  } finally {
    taskPolling = false;
    if (!hasRunningTasks.value) clearTaskPolling();
  }
}

function ensureTaskPolling() {
  if (taskPollId) return;
  taskPollId = setInterval(refreshRunningTasks, 4000);
}

async function runTool(toolName) {
  if (runningTool.value) return;
  runningTool.value = toolName;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.runTool(props.companyId, toolName);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    runningTool.value = null;
  }
}

async function runResearchTask(taskId) {
  if (runningTask.value) return;
  runningTask.value = taskId;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.runTask(props.companyId, taskId);
    if (hasRunningTasks.value) ensureTaskPolling();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    runningTask.value = null;
  }
}

async function patchArtifact(artifactName, patch) {
  if (savingArtifact.value) return;
  savingArtifact.value = artifactName;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.patchArtifact(
      props.companyId,
      artifactName,
      patch,
    );
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    savingArtifact.value = null;
  }
}

async function saveThesisDraft() {
  if (!thesisDraft.value) return;
  await patchArtifact("thesis_spine", {
    ...thesisDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function saveChartSpecsDraft() {
  await patchArtifact("chart_specs", {
    ...(artifacts.value.chart_specs || {}),
    specs: chartSpecsDraft.value || [],
    updated_at: new Date().toISOString(),
  });
}

async function saveNarrativeDraft() {
  if (!narrativeDraft.value) return;
  await patchArtifact("narrative_hooks", {
    selected_opening_id: narrativeDraft.value.selected_opening_id,
    selected_ending_id: narrativeDraft.value.selected_ending_id,
    updated_at: new Date().toISOString(),
  });
}

async function saveRiskPrioritiesDraft() {
  if (!riskPriorityDraft.value.length) return;
  await patchArtifact("risk_priorities", {
    priorities: riskPriorityDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function approve() {
  approving.value = true;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.approve(props.companyId);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    approving.value = false;
  }
}

function generateFromAnalysis() {
  if (!session.value?.id) return;
  emit("generate-memo", session.value.id);
}

function statusClass(status) {
  if (status === "done") return "bg-success-soft text-success-ink";
  if (status === "error") return "bg-danger/10 text-danger";
  if (status === "missing" || status === "not_started") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function statusLabel(status) {
  return (status || "not_started").replaceAll("_", " ");
}

function severityClass(severity) {
  if (severity === "high") return "bg-danger/10 text-danger border-danger/30";
  return "bg-warning-soft text-warning-ink border-warning/40";
}

function toolIcon(name) {
  if (name.includes("risk")) return ShieldAlert;
  if (name.includes("chart") || name.includes("benchmark")) return BarChart3;
  if (name.includes("readiness")) return Gauge;
  if (name.includes("grader")) return ClipboardCheck;
  return Sparkles;
}

function fmtDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

onMounted(load);
onBeforeUnmount(clearTaskPolling);
watch(() => props.companyId, () => {
  clearTaskPolling();
  load();
});
watch(hasRunningTasks, (running) => {
  if (running) ensureTaskPolling();
  else clearTaskPolling();
});
watch(thesis, (value) => {
  thesisDraft.value = clone(value);
}, { immediate: true });
watch(chartSpecs, (value) => {
  chartSpecsDraft.value = clone(value) || [];
}, { immediate: true });
watch(narrativeHooks, (value) => {
  narrativeDraft.value = clone(value);
}, { immediate: true });
watch([risks, riskPriorities], () => {
  riskPriorityDraft.value = buildRiskPriorityDraft();
}, { immediate: true });
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="font-display text-xl font-semibold text-ink-primary">
          Memo Studio
        </h2>
        <div v-if="session" class="mt-1 text-xs text-ink-muted font-mono">
          {{ session.id }} · {{ session.status }}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          @click="approve"
          :disabled="approving || loading"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-sm"
        >
          <Loader2 v-if="approving" class="h-4 w-4 animate-spin" />
          <CheckCircle2 v-else class="h-4 w-4" />
          <span>{{ approved ? "Approved" : "Approve analysis" }}</span>
        </button>
        <button
          type="button"
          @click="generateFromAnalysis"
          :disabled="!canGenerateMemo"
          :title="canGenerateMemo ? 'Generate memo' : 'Approve analysis and thesis spine first'"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed focus-ring text-sm"
        >
          <FileText class="h-4 w-4" />
          <span>Generate memo</span>
        </button>
      </div>
    </div>

    <div
      v-if="error"
      class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger flex items-start gap-2"
    >
      <AlertTriangle class="h-4 w-4 mt-0.5 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div
      v-if="loading"
      class="text-sm text-ink-muted inline-flex items-center gap-2"
    >
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading memo analysis
    </div>

    <template v-if="session && !loading">
      <section class="border border-subtle bg-surface rounded-card p-5">
        <div class="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div class="text-xs uppercase tracking-wide text-ink-muted">
              Readiness
            </div>
            <div class="mt-1 text-2xl font-semibold text-ink-primary">
              {{ readiness.score }} / {{ readiness.total }}
            </div>
          </div>
          <div class="w-full sm:w-64">
            <div class="h-2 rounded-full bg-surface-muted overflow-hidden">
              <div
                class="h-full bg-accent transition-all"
                :style="{ width: readinessPct + '%' }"
              ></div>
            </div>
            <div class="mt-1 text-xs text-ink-muted text-right">
              {{ readinessPct }}%
            </div>
          </div>
        </div>
        <div class="mt-4 grid md:grid-cols-3 gap-2">
          <div
            v-for="gate in readiness.gates"
            :key="gate.id"
            class="flex items-center gap-2 rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm"
          >
            <CheckCircle2
              v-if="gate.status === 'done'"
              class="h-4 w-4 text-success shrink-0"
            />
            <AlertTriangle
              v-else
              class="h-4 w-4 text-warning-ink shrink-0"
            />
            <span class="text-ink-primary">{{ gate.label }}</span>
          </div>
        </div>
      </section>

      <section>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Tools
          </h3>
        </div>
        <div class="grid lg:grid-cols-2 gap-3">
          <div
            v-for="tool in session.tools"
            :key="tool.name"
            class="rounded-card border border-subtle bg-surface p-4"
          >
            <div class="flex items-start gap-3">
              <component
                :is="toolIcon(tool.name)"
                class="h-5 w-5 text-accent mt-0.5 shrink-0"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <div class="font-medium text-ink-primary">{{ tool.label }}</div>
                  <span
                    :class="[
                      'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                      statusClass(tool.status),
                    ]"
                  >
                    {{ tool.status.replace('_', ' ') }}
                  </span>
                </div>
                <p class="mt-1 text-sm text-ink-secondary">
                  {{ tool.description }}
                </p>
                <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
                  {{ tool.summary }}
                </div>
                <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
                  {{ fmtDate(tool.last_run_at) }}
                </div>
              </div>
              <button
                type="button"
                @click="runTool(tool.name)"
                :disabled="Boolean(runningTool)"
                class="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring"
                :title="`Run ${tool.label}`"
              >
                <Loader2
                  v-if="runningTool === tool.name"
                  class="h-4 w-4 animate-spin"
                />
                <Play v-else class="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="additionalAreas.length"
        class="border border-subtle bg-surface rounded-card p-5"
      >
        <h3 class="font-display text-lg font-semibold text-ink-primary">
          Additional Areas Needed
        </h3>
        <div class="mt-3 grid md:grid-cols-2 gap-3">
          <div
            v-for="area in additionalAreas"
            :key="area.id"
            :class="[
              'rounded-lg border px-3 py-2',
              severityClass(area.severity),
            ]"
          >
            <div class="text-sm font-medium">{{ area.area }}</div>
            <div class="mt-1 text-xs opacity-80">{{ area.why_it_matters }}</div>
          </div>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Strategic Risk Board
            </h3>
            <button
              v-if="riskPriorityDraft.length"
              type="button"
              @click="saveRiskPrioritiesDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'risk_priorities'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save priorities</span>
            </button>
          </div>
          <div v-if="risks.length === 0" class="mt-3 text-sm text-ink-muted">
            No risks generated yet.
          </div>
          <div v-else class="mt-3 space-y-3">
            <div
              v-for="risk in prioritizedRisks"
              :key="risk.id"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-start gap-3">
                <div class="flex w-8 shrink-0 flex-col items-center gap-1">
                  <button
                    type="button"
                    @click="moveRiskPriority(risk.id, -1)"
                    :disabled="!canMoveRisk(risk.id, -1) || Boolean(savingArtifact)"
                    class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
                    title="Move risk up"
                  >
                    <ArrowUp class="h-3.5 w-3.5" />
                  </button>
                  <div class="text-[11px] font-mono text-ink-muted">
                    #{{ riskPriorityMap.get(risk.id)?.rank || "—" }}
                  </div>
                  <button
                    type="button"
                    @click="moveRiskPriority(risk.id, 1)"
                    :disabled="!canMoveRisk(risk.id, 1) || Boolean(savingArtifact)"
                    class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
                    title="Move risk down"
                  >
                    <ArrowDown class="h-3.5 w-3.5" />
                  </button>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-3">
                    <div class="font-medium text-ink-primary">{{ risk.title }}</div>
                    <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                      {{ risk.status }}
                    </span>
                  </div>
                  <div class="mt-1 text-sm text-ink-secondary">
                    {{ risk.decision_question }}
                  </div>
                  <div class="mt-2 text-xs text-ink-muted">
                    {{ risk.why_it_matters }}
                  </div>
                </div>
                <label class="shrink-0 inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
                  <input
                    type="checkbox"
                    :checked="Boolean(riskPriorityMap.get(risk.id)?.selected)"
                    @change="setRiskSelected(risk.id, $event.target.checked)"
                    :disabled="Boolean(savingArtifact)"
                    class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
                  />
                  <span>Research</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Investment Highlights & Risks
            </h3>
            <button
              v-if="thesisDraft"
              type="button"
              @click="saveThesisDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'thesis_spine'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save thesis</span>
            </button>
          </div>
          <div v-if="!thesisDraft" class="mt-3 text-sm text-ink-muted">
            No thesis spine drafted yet.
          </div>
          <template v-else>
            <div class="mt-3 text-xs uppercase tracking-wide text-ink-muted">
              Highlights
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(item, index) in thesisDraft.investment_highlights"
                :key="item.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`highlight-claim-${item.id || index}`"
                >
                  Claim {{ index + 1 }}
                </label>
                <input
                  :id="`highlight-claim-${item.id || index}`"
                  v-model="item.claim"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring"
                />
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`highlight-detail-${item.id || index}`"
                >
                  Detail
                </label>
                <textarea
                  :id="`highlight-detail-${item.id || index}`"
                  v-model="item.detail"
                  rows="3"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Risks
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(item, index) in thesisDraft.investment_risks"
                :key="item.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`risk-claim-${item.id || index}`"
                >
                  Claim {{ index + 1 }}
                </label>
                <input
                  :id="`risk-claim-${item.id || index}`"
                  v-model="item.claim"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring"
                />
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`risk-detail-${item.id || index}`"
                >
                  Detail
                </label>
                <textarea
                  :id="`risk-detail-${item.id || index}`"
                  v-model="item.detail"
                  rows="3"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Top Gating Questions
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(gate, index) in thesisDraft.top_gating_questions"
                :key="gate.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`gate-question-${gate.id || index}`"
                >
                  Question {{ index + 1 }}
                </label>
                <textarea
                  :id="`gate-question-${gate.id || index}`"
                  v-model="gate.question"
                  rows="2"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`gate-why-${gate.id || index}`"
                >
                  Why It Matters
                </label>
                <textarea
                  :id="`gate-why-${gate.id || index}`"
                  v-model="gate.why_it_matters"
                  rows="2"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Research Task Queue
          </h3>
          <div v-if="tasks.length === 0" class="mt-3 text-sm text-ink-muted">
            No research tasks yet.
          </div>
          <div v-else class="mt-3 space-y-2">
            <div
              v-for="task in tasks"
              :key="task.id"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <div class="text-sm font-medium text-ink-primary">{{ task.title }}</div>
                    <span class="text-[10px] rounded bg-surface px-1.5 py-0.5 text-ink-muted uppercase">
                      {{ task.priority }}
                    </span>
                    <span
                      :class="[
                        'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                        statusClass(task.status),
                      ]"
                    >
                      {{ statusLabel(task.status) }}
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-ink-muted">{{ task.source_type }}</div>
                  <div class="mt-2 text-xs text-ink-secondary">{{ task.prompt }}</div>
                </div>
                <button
                  type="button"
                  @click="runResearchTask(task.id)"
                  :disabled="Boolean(runningTask) || task.status === 'running'"
                  class="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring shrink-0"
                  :title="task.status === 'running' ? 'Task running' : task.status === 'done' ? 'Run task again' : 'Run task'"
                >
                  <Loader2
                    v-if="runningTask === task.id || task.status === 'running'"
                    class="h-4 w-4 animate-spin"
                  />
                  <Play v-else class="h-4 w-4" />
                </button>
              </div>
              <div
                v-if="task.result_summary"
                class="mt-3 rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-secondary"
              >
                {{ task.result_summary }}
                <div
                  v-if="task.completed_at || task.last_run_at"
                  class="mt-1 text-[11px] text-ink-subtle"
                >
                  {{ fmtDate(task.completed_at || task.last_run_at) }}
                  <span v-if="task.result_generated_by">
                    · {{ task.result_generated_by.replaceAll('_', ' ') }}
                  </span>
                </div>
              </div>
              <div v-if="task.error" class="mt-2 text-xs text-danger">
                {{ task.error }}
              </div>
            </div>
          </div>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Chart & Table Plan
            </h3>
            <button
              v-if="chartSpecsDraft.length"
              type="button"
              @click="saveChartSpecsDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'chart_specs'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save charts</span>
            </button>
          </div>
          <div v-if="chartSpecsDraft.length === 0" class="mt-3 text-sm text-ink-muted">
            No chart specs yet.
          </div>
          <div v-else class="mt-3 space-y-2">
            <div
              v-for="spec in chartSpecsDraft"
              :key="spec.id"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-ink-primary">{{ spec.title }}</div>
                <div class="flex items-center gap-2 shrink-0">
                  <label class="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
                    <input
                      v-model="spec.include_in_final_memo"
                      type="checkbox"
                      class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
                    />
                    <span>Final memo</span>
                  </label>
                  <span
                    :class="[
                      'text-[10px] rounded px-1.5 py-0.5 uppercase',
                      spec.data_availability === 'missing'
                        ? 'bg-warning-soft text-warning-ink'
                        : 'bg-success-soft text-success-ink',
                    ]"
                  >
                    {{ spec.data_availability }}
                  </span>
                </div>
              </div>
              <div class="mt-1 text-xs text-ink-secondary">{{ spec.takeaway }}</div>
            </div>
          </div>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Narrative Hooks
            </h3>
            <button
              v-if="narrativeDraft"
              type="button"
              @click="saveNarrativeDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'narrative_hooks'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save hooks</span>
            </button>
          </div>
          <div v-if="!narrativeDraft" class="mt-3 text-sm text-ink-muted">
            No openings or endings yet.
          </div>
          <template v-else>
            <div class="mt-3 text-xs uppercase tracking-wide text-ink-muted">
              Openings
            </div>
            <div class="mt-2 space-y-2">
              <label
                v-for="opening in narrativeDraft.openings"
                :key="opening.id"
                :class="[
                  'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
                  narrativeDraft.selected_opening_id === opening.id
                    ? 'border-accent bg-accent-soft/40 text-accent-ink'
                    : 'border-subtle bg-surface-muted text-ink-primary',
                ]"
              >
                <input
                  v-model="narrativeDraft.selected_opening_id"
                  type="radio"
                  :name="`opening-${session.id}`"
                  :value="opening.id"
                  class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
                />
                <span>{{ opening.text }}</span>
              </label>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Endings
            </div>
            <div class="mt-2 space-y-2">
              <label
                v-for="ending in narrativeDraft.endings"
                :key="ending.id"
                :class="[
                  'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
                  narrativeDraft.selected_ending_id === ending.id
                    ? 'border-accent bg-accent-soft/40 text-accent-ink'
                    : 'border-subtle bg-surface-muted text-ink-primary',
                ]"
              >
                <input
                  v-model="narrativeDraft.selected_ending_id"
                  type="radio"
                  :name="`ending-${session.id}`"
                  :value="ending.id"
                  class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
                />
                <span>{{ ending.text }}</span>
              </label>
            </div>
          </template>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Benchmark Dashboard
          </h3>
          <div v-if="!benchmark" class="mt-3 text-sm text-ink-muted">
            No benchmark dashboard yet.
          </div>
          <template v-else>
            <div class="mt-2 text-sm text-ink-secondary">{{ benchmark.summary }}</div>
            <div class="mt-3 overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead class="text-xs uppercase tracking-wide text-ink-muted">
                  <tr class="border-b border-subtle">
                    <th class="text-left py-2 pr-3">Company</th>
                    <th class="text-left py-2 pr-3">Ticker</th>
                    <th class="text-left py-2 pr-3">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="comp in benchmark.public_comps"
                    :key="comp.id"
                    class="border-b border-subtle/70"
                  >
                    <td class="py-2 pr-3 text-ink-primary">{{ comp.company }}</td>
                    <td class="py-2 pr-3 text-ink-secondary font-mono">{{ comp.ticker || "—" }}</td>
                    <td class="py-2 pr-3 text-ink-secondary">{{ comp.confidence }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>
