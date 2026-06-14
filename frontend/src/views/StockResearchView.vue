<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlertTriangle,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  Layers,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Upload,
} from "lucide-vue-next";
import { api } from "../api.js";
import StockAggregatePanel from "../components/stock/StockAggregatePanel.vue";
import StockEvaluationPanel from "../components/stock/StockEvaluationPanel.vue";
import StockHypothesesPanel from "../components/stock/StockHypothesesPanel.vue";
import StockResearchHomePanel from "../components/stock/StockResearchHomePanel.vue";
import StockReviewQueuePanel from "../components/stock/StockReviewQueuePanel.vue";
import StockRunsPanel from "../components/stock/StockRunsPanel.vue";
import StockSourceIntakePanel from "../components/stock/StockSourceIntakePanel.vue";
import StockStrategyMapPanel from "../components/stock/StockStrategyMapPanel.vue";
import StockTrackerRegistryPanel from "../components/stock/StockTrackerRegistryPanel.vue";
import StockWorkProductsPanel from "../components/stock/StockWorkProductsPanel.vue";

const tabs = [
  { id: "home", label: "Home", icon: Gauge },
  { id: "trackers", label: "Trackers", icon: Search },
  { id: "sources", label: "Sources", icon: Upload },
  { id: "runs", label: "Runs", icon: Play },
  { id: "aggregate", label: "Weekly Aggregate", icon: Layers },
  { id: "strategy", label: "Strategy Map", icon: GitBranch },
  { id: "products", label: "Work Products", icon: FileText },
  { id: "review", label: "Review Queue", icon: ListChecks },
  { id: "evaluation", label: "Evaluation", icon: Database },
  { id: "hypotheses", label: "Hypotheses", icon: FlaskConical },
];

const runReviewScoreFields = [
  { id: "factual_accuracy", label: "Fact" },
  { id: "usefulness", label: "Use" },
  { id: "source_quality", label: "Src" },
  { id: "writing_quality", label: "Write" },
  { id: "actionability", label: "Act" },
];

const route = useRoute();
const router = useRouter();
const payload = ref(null);
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const statusMessage = ref("");
const activeTab = ref(route.query.tab || "home");
const selectedTrackerIds = ref([]);
const sourceTrackerIds = ref([]);
const selectedRunId = ref("");
const linkForm = ref({
  title: "",
  url: "",
  notes: "",
  priority: "user_provided",
  relevance: "this_week_input",
});
const noteForm = ref({
  title: "",
  body: "",
  priority: "user_provided",
  relevance: "this_week_input",
});
const fileForm = ref({
  file: null,
  title: "",
  priority: "user_provided",
  relevance: "this_week_input",
});
const aggregateModuleFilter = ref("all");
const aggregateDirectionFilter = ref("all");
const productTypeFilter = ref("all");
const productStatusFilter = ref("all");
const productTrackerFilter = ref("all");
const productPeriodFilter = ref("all");
const reviewFilter = ref("open");
const reviewTypeFilter = ref("all");
const reviewRationale = ref("");
const evaluationTrackerFilter = ref("all");
const runReviewDrafts = ref({});

watch(
  () => route.query.tab,
  (tab) => {
    if (tab && tabs.some((item) => item.id === tab)) activeTab.value = tab;
  },
);

const summary = computed(() => payload.value?.summary || {});
const trackers = computed(() => payload.value?.trackers || []);
const sources = computed(() => payload.value?.sources || []);
const runs = computed(() => payload.value?.runs || []);
const selectedRun = computed(() =>
  runs.value.find((run) => run.run_id === selectedRunId.value) || runs.value[0] || null,
);
const previousRunForSelected = computed(() => {
  if (!selectedRun.value) return null;
  const sameTracker = runs.value.filter((run) => run.tracker_id === selectedRun.value.tracker_id);
  const index = sameTracker.findIndex((run) => run.run_id === selectedRun.value.run_id);
  return index >= 0 ? sameTracker[index + 1] || null : null;
});
const selectedRunDiff = computed(() => {
  if (!selectedRun.value || !previousRunForSelected.value) return [];
  const rows = [];
  if (selectedRun.value.thesis !== previousRunForSelected.value.thesis) {
    rows.push({
      field: "Thesis",
      current: selectedRun.value.thesis || "No thesis.",
      previous: previousRunForSelected.value.thesis || "No thesis.",
    });
  }
  if (selectedRun.value.confidence !== previousRunForSelected.value.confidence) {
    rows.push({
      field: "Confidence",
      current: fmtConfidence(selectedRun.value.confidence),
      previous: fmtConfidence(previousRunForSelected.value.confidence),
    });
  }
  if (selectedRun.value.source_count !== previousRunForSelected.value.source_count) {
    rows.push({
      field: "Sources",
      current: selectedRun.value.source_count || 0,
      previous: previousRunForSelected.value.source_count || 0,
    });
  }
  return rows;
});
const aggregate = computed(() => payload.value?.latest_aggregate || null);
const strategyMap = computed(() => payload.value?.latest_strategy_map || null);
const products = computed(() => payload.value?.work_products || []);
const filteredProducts = computed(() =>
  products.value.filter((product) => {
    if (productTypeFilter.value !== "all" && product.artifact_type !== productTypeFilter.value) {
      return false;
    }
    if (productStatusFilter.value !== "all" && product.status !== productStatusFilter.value) {
      return false;
    }
    if (productTrackerFilter.value !== "all" && product.tracker_id !== productTrackerFilter.value) {
      return false;
    }
    if (productPeriodFilter.value !== "all" && product.period_id !== productPeriodFilter.value) {
      return false;
    }
    return true;
  }),
);
const reviewItems = computed(() => payload.value?.review_items || []);
const filteredReviewItems = computed(() => {
  return reviewItems.value.filter((item) => {
    if (reviewFilter.value !== "all" && item.status !== reviewFilter.value) {
      return false;
    }
    if (reviewTypeFilter.value !== "all" && item.item_type !== reviewTypeFilter.value) {
      return false;
    }
    return true;
  });
});
const evaluationRows = computed(() => payload.value?.evaluation?.runs || []);
const runLedgerRows = computed(() => payload.value?.evaluation?.run_ledger || []);
const hypotheses = computed(() => payload.value?.hypotheses || {});
const filteredEvaluationRows = computed(() =>
  evaluationRows.value.filter((row) =>
    evaluationTrackerFilter.value === "all" || row.tracker_id === evaluationTrackerFilter.value,
  ),
);
const selectedTrackers = computed(() =>
  trackers.value.filter((tracker) => selectedTrackerIds.value.includes(tracker.id)),
);
const activeTrackerIds = computed(() =>
  trackers.value
    .filter((tracker) => tracker.status === "active")
    .map((tracker) => tracker.id),
);
const aggregateSignals = computed(() => aggregate.value?.ranked_signals || []);
const aggregateModuleRows = computed(() => {
  const modules = aggregate.value?.modules || {};
  const rows = [];
  for (const key of ["macro", "industry", "company", "cross_tracker", "watchlist"]) {
    if (aggregateModuleFilter.value !== "all" && aggregateModuleFilter.value !== key) continue;
    for (const [index, item] of (modules[key] || []).entries()) {
      rows.push({
        id: `${key}:${item.tracker_id || item.id || index}`,
        module: key,
        tracker_id: item.tracker_id || item.source_tracker_id || "",
        title: item.thesis || item.observation || item.shared_context?.join(", ") || item.items?.join(", ") || key,
        source_count: item.source_traces?.length || 0,
      });
    }
  }
  return rows;
});
const filteredAggregateSignals = computed(() =>
  aggregateSignals.value.filter((signal) =>
    aggregateDirectionFilter.value === "all" || signal.direction === aggregateDirectionFilter.value,
  ),
);
const aggregateWarnings = computed(() => [
  ...(aggregate.value?.excluded_tracker_warnings || []).map((item) => ({
    kind: "excluded",
    title: item.warning || "Excluded tracker",
    tracker_id: item.tracker_id,
  })),
  ...(aggregate.value?.missing_source_warnings || []).map((item) => ({
    kind: "missing source",
    title: item.description || item.warning || "Missing source",
    tracker_id: item.tracker_id,
  })),
]);
const strategyNodes = computed(() => strategyMap.value?.nodes || []);
const strategyEdges = computed(() => strategyMap.value?.edges || []);
const strategyContradictions = computed(() => strategyMap.value?.contradictions || []);
const strategySourceRows = computed(() => [
  ...strategyNodes.value.flatMap((node) =>
    (node.source_traces || []).map((trace, index) => ({
      id: `node:${node.id}:${index}`,
      kind: "node",
      label: node.label || node.id,
      trace,
    })),
  ),
  ...strategyEdges.value.flatMap((edge) =>
    (edge.source_traces || []).map((trace, index) => ({
      id: `edge:${edge.id || `${edge.from}-${edge.to}`}:${index}`,
      kind: "edge",
      label: edge.label || edge.relationship || `${edge.from || "from"} -> ${edge.to || "to"}`,
      trace,
    })),
  ),
]);
const productTypes = computed(() =>
  Array.from(new Set(products.value.map((product) => product.artifact_type).filter(Boolean))).sort(),
);
const productStatuses = computed(() =>
  Array.from(new Set(products.value.map((product) => product.status).filter(Boolean))).sort(),
);
const productTrackerIds = computed(() =>
  Array.from(new Set(products.value.map((product) => product.tracker_id).filter(Boolean))).sort(),
);
const productPeriods = computed(() =>
  Array.from(new Set(products.value.map((product) => product.period_id).filter(Boolean))).sort(),
);
const reviewTypes = computed(() =>
  Array.from(new Set(reviewItems.value.map((item) => item.item_type).filter(Boolean))).sort(),
);
const evaluationTrackerIds = computed(() =>
  Array.from(new Set(evaluationRows.value.map((row) => row.tracker_id).filter(Boolean))).sort(),
);
const trackerMetricRows = computed(() => {
  const grouped = new Map();
  for (const row of evaluationRows.value) {
    const key = row.tracker_id;
    if (!key) continue;
    const current = grouped.get(key) || {
      tracker_id: key,
      tracker_name: row.tracker_name || key,
      runs: 0,
      coverage_total: 0,
      reviewer_total: 0,
      reviewer_count: 0,
      missing_total: 0,
      latest_at: "",
    };
    current.runs += 1;
    current.coverage_total += Number(row.evidence_coverage || 0);
    current.missing_total += Number(row.missing_source_count || 0);
    if (row.reviewer_score != null) {
      current.reviewer_total += Number(row.reviewer_score || 0);
      current.reviewer_count += 1;
    }
    if (String(row.created_at || "") > current.latest_at) {
      current.latest_at = row.created_at;
    }
    grouped.set(key, current);
  }
  return Array.from(grouped.values()).map((row) => ({
    ...row,
    avg_coverage: row.runs ? row.coverage_total / row.runs : 0,
    avg_reviewer: row.reviewer_count ? row.reviewer_total / row.reviewer_count : null,
  }));
});
const knowledgeReviewRows = computed(() =>
  runs.value.flatMap((run) =>
    (run.knowledge_updates || []).map((update) => ({
      ...update,
      tracker_id: run.tracker_id,
      tracker_name: run.tracker_name || run.tracker_id,
      run_id: run.run_id,
    })),
  ),
);

function setTab(id) {
  activeTab.value = id;
  router.replace({ query: { ...route.query, tab: id } });
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

async function loadDashboard() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.stockResearch.dashboard();
    syncRunReviewDrafts(payload.value?.evaluation?.runs || []);
    if (!sourceTrackerIds.value.length && trackers.value.length) {
      sourceTrackerIds.value = [trackers.value[0].id];
    }
  } catch (e) {
    error.value = e?.message || "Could not load Stock Research.";
  } finally {
    loading.value = false;
  }
}

async function runAction(label, fn) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  statusMessage.value = label;
  try {
    await fn();
    await loadDashboard();
  } catch (e) {
    error.value = e?.message || `${label} failed.`;
  } finally {
    busy.value = false;
  }
}

function toggleTracker(trackerId) {
  const set = new Set(selectedTrackerIds.value);
  if (set.has(trackerId)) set.delete(trackerId);
  else set.add(trackerId);
  selectedTrackerIds.value = Array.from(set);
}

function toggleSourceTracker(trackerId) {
  const set = new Set(sourceTrackerIds.value);
  if (set.has(trackerId)) set.delete(trackerId);
  else set.add(trackerId);
  sourceTrackerIds.value = Array.from(set);
}

async function runSelected() {
  const ids = selectedTrackerIds.value.length
    ? selectedTrackerIds.value
    : activeTrackerIds.value;
  await runAction("Queued selected trackers", () =>
    api.stockResearch.runSelectedTrackers(ids),
  );
}

async function runTracker(trackerId) {
  await runAction("Queued tracker run", () =>
    api.stockResearch.runTracker(trackerId),
  );
}

async function cancelRun(run) {
  await runAction("Cancelling tracker run", () =>
    api.stockResearch.cancelRun(run.tracker_id, run.run_id),
  );
}

async function retryRun(run) {
  await runAction("Retrying tracker run", () =>
    api.stockResearch.retryRun(run.tracker_id, run.run_id),
  );
}

async function cancelAggregate() {
  if (!aggregate.value?.period_id) return;
  await runAction("Cancelling aggregate", () =>
    api.stockResearch.cancelAggregate(aggregate.value.period_id),
  );
}

async function retryAggregate() {
  if (!aggregate.value?.period_id) return;
  await runAction("Retrying aggregate", () =>
    api.stockResearch.retryAggregate(aggregate.value.period_id),
  );
}

async function cancelStrategyMap() {
  if (!strategyMap.value?.period_id) return;
  await runAction("Cancelling strategy map", () =>
    api.stockResearch.cancelStrategyMap(strategyMap.value.period_id),
  );
}

async function retryStrategyMap() {
  if (!strategyMap.value?.period_id) return;
  await runAction("Retrying strategy map", () =>
    api.stockResearch.retryStrategyMap(strategyMap.value.period_id),
  );
}

async function submitLinkSource() {
  await runAction("Saving link source", async () => {
    await api.stockResearch.addLinkSource({
      ...linkForm.value,
      tracker_ids: sourceTrackerIds.value,
    });
    linkForm.value = {
      title: "",
      url: "",
      notes: "",
      priority: "user_provided",
      relevance: "this_week_input",
    };
  });
}

async function submitNoteSource() {
  await runAction("Saving note source", async () => {
    await api.stockResearch.addNoteSource({
      ...noteForm.value,
      tracker_ids: sourceTrackerIds.value,
    });
    noteForm.value = {
      title: "",
      body: "",
      priority: "user_provided",
      relevance: "this_week_input",
    };
  });
}

async function submitFileSource() {
  await runAction("Uploading source file", async () => {
    await api.stockResearch.uploadSource({
      file: fileForm.value.file,
      trackerIds: sourceTrackerIds.value,
      title: fileForm.value.title,
      priority: fileForm.value.priority,
      relevance: fileForm.value.relevance,
    });
    fileForm.value = {
      file: null,
      title: "",
      priority: "user_provided",
      relevance: "this_week_input",
    };
  });
}

function onFilePicked(event) {
  fileForm.value.file = event.target?.files?.[0] || null;
}

async function updateReview(item, status) {
  await runAction("Updating review item", () =>
    api.stockResearch.updateReviewItem(item.id, {
      status,
      rationale: reviewRationale.value,
    }),
  );
}

async function reviewKnowledgeUpdate(run, update, status) {
  await runAction("Updating knowledge review", () =>
    api.stockResearch.reviewKnowledgeUpdate(
      run.tracker_id,
      run.run_id,
      update.id,
      { status, rationale: reviewRationale.value },
    ),
  );
}

async function updateProduct(product, patch) {
  await runAction("Updating work product", () =>
    api.stockResearch.updateWorkProduct(product.artifact_id, patch),
  );
}

function runReviewKey(row) {
  return `${row.tracker_id}:${row.run_id}`;
}

function defaultRunReviewDraft(row) {
  const scores = row.reviewer_scores || {};
  return {
    ...Object.fromEntries(
      runReviewScoreFields.map((field) => [
        field.id,
        scores[field.id] ?? "",
      ]),
    ),
    review_notes: row.review_notes || "",
  };
}

function syncRunReviewDrafts(rows) {
  const next = { ...runReviewDrafts.value };
  for (const row of rows) {
    const key = runReviewKey(row);
    if (!next[key]) next[key] = defaultRunReviewDraft(row);
  }
  runReviewDrafts.value = next;
}

function runReviewDraft(row) {
  return runReviewDrafts.value[runReviewKey(row)] || defaultRunReviewDraft(row);
}

function setRunReviewScore(row, field, value) {
  const key = runReviewKey(row);
  const current = runReviewDraft(row);
  runReviewDrafts.value = {
    ...runReviewDrafts.value,
    [key]: { ...current, [field]: value },
  };
}

function setRunReviewNotes(row, value) {
  const key = runReviewKey(row);
  const current = runReviewDraft(row);
  runReviewDrafts.value = {
    ...runReviewDrafts.value,
    [key]: { ...current, review_notes: value },
  };
}

async function saveRunReview(row) {
  const draft = runReviewDraft(row);
  const patch = {};
  for (const field of runReviewScoreFields) {
    if (draft[field.id] !== "") patch[field.id] = Number(draft[field.id]);
  }
  patch.review_notes = draft.review_notes || "";
  await runAction("Saving run review", () =>
    api.stockResearch.updateRunReview(row.tracker_id, row.run_id, patch),
  );
}

async function createLiveHypotheses(vintageDate) {
  await runAction("Creating live hypotheses", () =>
    api.stockResearch.createHypotheses({ vintageDate }),
  );
}

async function createDebugBackfill(vintageDate) {
  await runAction("Creating debug backfill", () =>
    api.stockResearch.createHypotheses({
      vintageDate,
      allowDebugBackfill: true,
    }),
  );
}

async function evaluateHypothesisVintage(vintageDate) {
  if (!vintageDate) return;
  await runAction("Evaluating hypotheses", () =>
    api.stockResearch.evaluateHypotheses(vintageDate),
  );
}

async function calibrateHypotheses() {
  await runAction("Calibrating hypotheses", () =>
    api.stockResearch.calibrateHypotheses(),
  );
}

function fmtConfidence(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "n/a";
  return `${Math.round(n * 100)}%`;
}

onMounted(loadDashboard);
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink-primary">
    <header class="border-b border-subtle bg-surface px-6 py-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            Public Equity Research
          </div>
          <h1 class="mt-1 font-display text-2xl font-semibold">
            Stock Research
          </h1>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
            :disabled="busy"
            @click="loadDashboard"
          >
            <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
            Refresh
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover focus-ring disabled:opacity-50"
            :disabled="busy || trackers.length === 0"
            @click="runSelected"
          >
            <Play class="h-4 w-4" />
            Run Selected
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
            :disabled="busy"
            @click="runAction('Queued due trackers', () => api.stockResearch.runDueTrackers())"
          >
            <ListChecks class="h-4 w-4" />
            Run Due
          </button>
        </div>
      </div>
      <div
        v-if="error || statusMessage"
        class="mt-3 flex items-center gap-2 text-sm"
        :class="error ? 'text-danger' : 'text-ink-muted'"
      >
        <AlertTriangle v-if="error" class="h-4 w-4" />
        <Loader2 v-else-if="busy" class="h-4 w-4 animate-spin" />
        <span>{{ error || statusMessage }}</span>
      </div>
    </header>

    <nav class="border-b border-subtle bg-surface px-4 py-2">
      <div class="flex gap-1 overflow-x-auto">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="inline-flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium focus-ring"
          :class="
            activeTab === tab.id
              ? 'bg-accent-soft text-accent-ink'
              : 'text-ink-secondary hover:bg-surface-muted'
          "
          @click="setTab(tab.id)"
        >
          <component :is="tab.icon" class="h-4 w-4" />
          {{ tab.label }}
        </button>
      </div>
    </nav>

    <main class="px-6 py-5">
      <div v-if="loading && !payload" class="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 class="h-4 w-4 animate-spin" />
        Loading Stock Research
      </div>

      <StockResearchHomePanel
        v-else-if="activeTab === 'home'"
        :summary="summary"
        :aggregate="aggregate"
        :aggregate-signal-count="aggregateSignals.length"
        :strategy-map="strategyMap"
        :strategy-node-count="strategyNodes.length"
        :strategy-edge-count="strategyEdges.length"
        @open-tab="setTab"
      />

      <StockTrackerRegistryPanel
        v-else-if="activeTab === 'trackers'"
        :trackers="trackers"
        :selected-tracker-ids="selectedTrackerIds"
        :busy="busy"
        @toggle-tracker="toggleTracker"
        @run-tracker="runTracker"
        @disable-tracker="(trackerId) => runAction('Disabled tracker', () => api.stockResearch.disableTracker(trackerId))"
        @import-company-trackers="runAction('Imported company trackers', () => api.stockResearch.importCompanyTrackers({ limit: 20 }))"
      />

      <StockSourceIntakePanel
        v-else-if="activeTab === 'sources'"
        :trackers="trackers"
        :sources="sources"
        :source-tracker-ids="sourceTrackerIds"
        :file-form="fileForm"
        :link-form="linkForm"
        :note-form="noteForm"
        :busy="busy"
        @toggle-source-tracker="toggleSourceTracker"
        @update-file-form="fileForm = $event"
        @update-link-form="linkForm = $event"
        @update-note-form="noteForm = $event"
        @file-picked="onFilePicked"
        @submit-file-source="submitFileSource"
        @submit-link-source="submitLinkSource"
        @submit-note-source="submitNoteSource"
      />

      <StockRunsPanel
        v-else-if="activeTab === 'runs'"
        :runs="runs"
        :run-ledger="runLedgerRows"
        :selected-run="selectedRun"
        :selected-run-diff="selectedRunDiff"
        :busy="busy"
        @run-aggregate="runAction('Queued aggregate', () => api.stockResearch.runAggregate())"
        @run-strategy-map="runAction('Queued strategy map', () => api.stockResearch.runStrategyMap())"
        @review-knowledge-update="reviewKnowledgeUpdate"
        @cancel-run="cancelRun"
        @retry-run="retryRun"
        @select-run="selectedRunId = $event"
      />

      <StockAggregatePanel
        v-else-if="activeTab === 'aggregate'"
        :aggregate="aggregate"
        :aggregate-warnings="aggregateWarnings"
        :aggregate-module-rows="aggregateModuleRows"
        :filtered-aggregate-signals="filteredAggregateSignals"
        :aggregate-module-filter="aggregateModuleFilter"
        :aggregate-direction-filter="aggregateDirectionFilter"
        :busy="busy"
        @update:aggregate-module-filter="aggregateModuleFilter = $event"
        @update:aggregate-direction-filter="aggregateDirectionFilter = $event"
        @run-aggregate="runAction('Queued aggregate', () => api.stockResearch.runAggregate({ force: true }))"
        @retry-aggregate="retryAggregate"
        @cancel-aggregate="cancelAggregate"
      />

      <StockStrategyMapPanel
        v-else-if="activeTab === 'strategy'"
        :strategy-map="strategyMap"
        :strategy-nodes="strategyNodes"
        :strategy-source-rows="strategySourceRows"
        :strategy-contradictions="strategyContradictions"
        :busy="busy"
        @run-strategy-map="runAction('Queued strategy map', () => api.stockResearch.runStrategyMap({ force: true }))"
        @retry-strategy-map="retryStrategyMap"
        @cancel-strategy-map="cancelStrategyMap"
      />

      <StockWorkProductsPanel
        v-else-if="activeTab === 'products'"
        :products="filteredProducts"
        :product-types="productTypes"
        :product-statuses="productStatuses"
        :product-tracker-ids="productTrackerIds"
        :product-periods="productPeriods"
        :type-filter="productTypeFilter"
        :status-filter="productStatusFilter"
        :tracker-filter="productTrackerFilter"
        :period-filter="productPeriodFilter"
        @update:type-filter="productTypeFilter = $event"
        @update:status-filter="productStatusFilter = $event"
        @update:tracker-filter="productTrackerFilter = $event"
        @update:period-filter="productPeriodFilter = $event"
        @update-product="updateProduct"
      />

      <StockReviewQueuePanel
        v-else-if="activeTab === 'review'"
        :items="filteredReviewItems"
        :review-types="reviewTypes"
        :review-filter="reviewFilter"
        :review-type-filter="reviewTypeFilter"
        :review-rationale="reviewRationale"
        @update:review-filter="reviewFilter = $event"
        @update:review-type-filter="reviewTypeFilter = $event"
        @update:review-rationale="reviewRationale = $event"
        @update-review="updateReview"
      />

      <StockEvaluationPanel
        v-else-if="activeTab === 'evaluation'"
        :filtered-evaluation-rows="filteredEvaluationRows"
        :tracker-metric-rows="trackerMetricRows"
        :knowledge-review-rows="knowledgeReviewRows"
        :evaluation-tracker-ids="evaluationTrackerIds"
        :evaluation-tracker-filter="evaluationTrackerFilter"
        :run-review-score-fields="runReviewScoreFields"
        :run-review-draft="runReviewDraft"
        :busy="busy"
        @update:evaluation-tracker-filter="evaluationTrackerFilter = $event"
        @set-run-review-score="setRunReviewScore"
        @set-run-review-notes="setRunReviewNotes"
        @save-run-review="saveRunReview"
        @review-knowledge-update="reviewKnowledgeUpdate"
      />

      <StockHypothesesPanel
        v-else-if="activeTab === 'hypotheses'"
        :hypotheses="hypotheses"
        :busy="busy"
        :default-vintage-date="todayIsoDate()"
        @create-live="createLiveHypotheses"
        @create-debug-backfill="createDebugBackfill"
        @evaluate-vintage="evaluateHypothesisVintage"
        @calibrate="calibrateHypotheses"
      />
    </main>
  </div>
</template>
