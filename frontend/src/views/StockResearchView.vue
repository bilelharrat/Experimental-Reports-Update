<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  AlertTriangle,
  Archive,
  Check,
  Database,
  FileText,
  Gauge,
  GitBranch,
  Layers,
  Link,
  ListChecks,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Square,
  Upload,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import StockResearchHomePanel from "../components/stock/StockResearchHomePanel.vue";
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

function fmtDate(value) {
  if (!value) return "n/a";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtConfidence(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "n/a";
  return `${Math.round(n * 100)}%`;
}

function canRetryRun(run) {
  return ["error", "cancelled", "recovered"].includes(run.status);
}

function firstTrace(item) {
  return item?.source_traces?.[0] || null;
}

function sourceState(source) {
  if (source.extraction_status === "missing") return "missing";
  if (source.ocr_needed || source.extraction_status === "ocr_needed") return "ocr needed";
  return source.extraction_status || "metadata";
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

      <section v-else-if="activeTab === 'trackers'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Tracker Registry</h2>
            <p class="text-sm text-ink-muted">
              Single-responsibility trackers with isolated source folders and durable memory.
            </p>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
            :disabled="busy"
            @click="runAction('Imported company trackers', () => api.stockResearch.importCompanyTrackers({ limit: 20 }))"
          >
            <Upload class="h-4 w-4" />
            Import Companies
          </button>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="w-10 px-3 py-2"></th>
                <th class="px-3 py-2">Tracker</th>
                <th class="px-3 py-2">Type</th>
                <th class="px-3 py-2">Status</th>
                <th class="px-3 py-2">Freshness</th>
                <th class="px-3 py-2">Latest Thesis</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="tracker in trackers" :key="tracker.id" class="border-b border-subtle last:border-0">
                <td class="px-3 py-2">
                  <input
                    type="checkbox"
                    class="h-4 w-4 rounded border-subtle"
                    :checked="selectedTrackerIds.includes(tracker.id)"
                    @change="toggleTracker(tracker.id)"
                  />
                </td>
                <td class="px-3 py-2">
                  <div class="font-medium">{{ tracker.display_name }}</div>
                  <div class="text-xs text-ink-muted">{{ tracker.id }}</div>
                </td>
                <td class="px-3 py-2 capitalize">{{ tracker.type }}</td>
                <td class="px-3 py-2">
                  <span class="rounded bg-surface-muted px-2 py-1 text-xs">{{ tracker.status }}</span>
                </td>
                <td class="px-3 py-2 text-xs">
                  <span :class="tracker.is_stale ? 'text-warning-ink' : 'text-success-ink'">
                    {{ tracker.is_stale ? 'stale' : 'fresh' }}
                  </span>
                  <div class="text-ink-muted">{{ fmtDate(tracker.freshness_policy?.next_due_run) }}</div>
                </td>
                <td class="max-w-md px-3 py-2 text-ink-secondary">
                  <div class="line-clamp-2">{{ tracker.latest_thesis || 'No run yet.' }}</div>
                </td>
                <td class="px-3 py-2">
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || tracker.status !== 'active'"
                      title="Run tracker"
                      @click="runTracker(tracker.id)"
                    >
                      <Play class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || tracker.status !== 'active'"
                      title="Disable tracker"
                      @click="runAction('Disabled tracker', () => api.stockResearch.disableTracker(tracker.id))"
                    >
                      <Archive class="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="trackers.length === 0">
                <td colspan="7" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No trackers yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-else-if="activeTab === 'sources'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-[22rem_1fr]">
          <aside class="rounded-lg border border-subtle bg-surface p-4">
            <h2 class="text-sm font-semibold">Assign Source</h2>
            <div class="mt-3 space-y-2">
              <label
                v-for="tracker in trackers"
                :key="tracker.id"
                class="flex items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  class="h-4 w-4 rounded border-subtle"
                  :checked="sourceTrackerIds.includes(tracker.id)"
                  @change="toggleSourceTracker(tracker.id)"
                />
                <span class="truncate">{{ tracker.display_name }}</span>
              </label>
            </div>
            <div class="mt-5 space-y-3">
              <input
                v-model="fileForm.title"
                class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="File title"
              />
              <input
                type="file"
                class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                @change="onFilePicked"
              />
              <button
                type="button"
                class="inline-flex w-full items-center justify-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
                :disabled="busy || !sourceTrackerIds.length || !fileForm.file"
                @click="submitFileSource"
              >
                <Upload class="h-4 w-4" />
                Upload File
              </button>
            </div>
            <div class="mt-5 space-y-3 border-t border-subtle pt-4">
              <input
                v-model="linkForm.title"
                class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="Link title"
              />
              <input
                v-model="linkForm.url"
                class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="https://source.example"
              />
              <textarea
                v-model="linkForm.notes"
                class="min-h-20 w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="Source notes"
              ></textarea>
              <button
                type="button"
                class="inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white focus-ring disabled:opacity-50"
                :disabled="busy || !sourceTrackerIds.length || !linkForm.url"
                @click="submitLinkSource"
              >
                <Link class="h-4 w-4" />
                Attach Link
              </button>
            </div>
            <div class="mt-5 space-y-3 border-t border-subtle pt-4">
              <input
                v-model="noteForm.title"
                class="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="Note title"
              />
              <textarea
                v-model="noteForm.body"
                class="min-h-24 w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
                placeholder="Analyst note"
              ></textarea>
              <button
                type="button"
                class="inline-flex w-full items-center justify-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
                :disabled="busy || !sourceTrackerIds.length || !noteForm.body"
                @click="submitNoteSource"
              >
                <FileText class="h-4 w-4" />
                Add Note
              </button>
            </div>
          </aside>
          <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Source</th>
                  <th class="px-3 py-2">Tracker</th>
                  <th class="px-3 py-2">Type</th>
                  <th class="px-3 py-2">State</th>
                  <th class="px-3 py-2">Relevance</th>
                  <th class="px-3 py-2">Trace Preview</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="source in sources" :key="`${source.tracker_id}:${source.id}`" class="border-b border-subtle last:border-0">
                  <td class="px-3 py-2">
                    <div class="font-medium">{{ source.title || source.filename }}</div>
                    <div class="text-xs text-ink-muted">{{ fmtDate(source.created_at) }}</div>
                  </td>
                  <td class="px-3 py-2">{{ source.tracker_name || source.tracker_id }}</td>
                  <td class="px-3 py-2">{{ source.source_type }}</td>
                  <td class="px-3 py-2">
                    <span
                      class="rounded px-2 py-1 text-xs"
                      :class="source.extraction_status === 'missing' ? 'bg-danger-soft text-danger-ink' : 'bg-surface-muted text-ink-secondary'"
                    >
                      {{ sourceState(source) }}
                    </span>
                  </td>
                  <td class="px-3 py-2">{{ source.relevance }}</td>
                  <td class="max-w-lg px-3 py-2 text-ink-secondary">
                    <div class="line-clamp-2">
                      {{ source.missing_reason || source.chunks?.[0]?.excerpt || source.url || 'No preview.' }}
                    </div>
                  </td>
                </tr>
                <tr v-if="sources.length === 0">
                  <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
                    No tracker-owned sources yet.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'runs'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Run Orchestration</h2>
            <p class="text-sm text-ink-muted">
              Tracker runs write JSONL progress, structured outputs, source manifests, and reports.
            </p>
          </div>
          <div class="flex gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="runAction('Queued aggregate', () => api.stockResearch.runAggregate())"
            >
              <Layers class="h-4 w-4" />
              Run Aggregate
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="runAction('Queued strategy map', () => api.stockResearch.runStrategyMap())"
            >
              <GitBranch class="h-4 w-4" />
              Run Strategy
            </button>
          </div>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="px-3 py-2">Run</th>
                <th class="px-3 py-2">Tracker</th>
                <th class="px-3 py-2">Status</th>
                <th class="px-3 py-2">Sources</th>
                <th class="px-3 py-2">Confidence</th>
                <th class="px-3 py-2">Thesis</th>
                <th class="px-3 py-2">Knowledge</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.run_id" class="border-b border-subtle last:border-0">
                <td class="px-3 py-2">
                  <div class="font-mono text-xs">{{ run.run_id }}</div>
                  <div class="text-xs text-ink-muted">{{ fmtDate(run.created_at) }}</div>
                </td>
                <td class="px-3 py-2">{{ run.tracker_name || run.tracker_id }}</td>
                <td class="px-3 py-2">{{ run.status }}</td>
                <td class="px-3 py-2">{{ run.source_count || 0 }}</td>
                <td class="px-3 py-2">{{ fmtConfidence(run.confidence) }}</td>
                <td class="max-w-lg px-3 py-2 text-ink-secondary">
                  <div class="line-clamp-2">{{ run.thesis || 'No thesis.' }}</div>
                  <div v-if="run.source_traces?.length" class="mt-1 line-clamp-1 text-xs text-ink-muted">
                    {{ run.source_traces[0].source_title }} · {{ run.source_traces[0].locator }}
                  </div>
                </td>
                <td class="max-w-sm px-3 py-2">
                  <div v-if="run.knowledge_updates?.length" class="space-y-2">
                    <div
                      v-for="update in run.knowledge_updates"
                      :key="update.id"
                      class="rounded border border-subtle p-2 text-xs"
                    >
                      <div class="line-clamp-2 text-ink-secondary">{{ update.text }}</div>
                      <div class="mt-2 flex items-center gap-2">
                        <span class="text-ink-muted">{{ update.review_status || 'open' }}</span>
                        <button
                          type="button"
                          class="rounded-md border border-subtle p-1 hover:bg-surface-muted focus-ring disabled:opacity-50"
                          :disabled="busy || update.review_status === 'resolved'"
                          title="Accept knowledge update"
                          @click="reviewKnowledgeUpdate(run, update, 'resolved')"
                        >
                          <Check class="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          class="rounded-md border border-subtle p-1 hover:bg-surface-muted focus-ring disabled:opacity-50"
                          :disabled="busy || update.review_status === 'rejected'"
                          title="Reject knowledge update"
                          @click="reviewKnowledgeUpdate(run, update, 'rejected')"
                        >
                          <X class="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                  <span v-else class="text-xs text-ink-muted">None</span>
                </td>
                <td class="px-3 py-2">
                  <div class="flex items-center gap-2">
                    <button
                      v-if="run.status === 'queued' || run.status === 'running'"
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                      title="Cancel run"
                      @click="cancelRun(run)"
                    >
                      <Square class="h-4 w-4" />
                    </button>
                    <button
                      v-if="canRetryRun(run)"
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                      title="Retry run"
                      @click="retryRun(run)"
                    >
                      <RefreshCw class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                      title="Show run details"
                      @click="selectedRunId = run.run_id"
                    >
                      <FileText class="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="runs.length === 0">
                <td colspan="8" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No tracker runs yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="selectedRun" class="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
          <section class="rounded-lg border border-subtle bg-surface">
            <div class="border-b border-subtle px-4 py-3">
              <h3 class="text-sm font-semibold">Latest Report</h3>
              <div class="mt-1 font-mono text-xs text-ink-muted">{{ selectedRun.run_id }}</div>
            </div>
            <div class="max-h-96 overflow-auto p-4 text-sm">
              <pre class="whitespace-pre-wrap text-xs">{{ selectedRun.report_markdown || selectedRun.thesis || 'No report artifact.' }}</pre>
            </div>
          </section>
          <section class="space-y-4">
            <div class="rounded-lg border border-subtle bg-surface p-4">
              <h3 class="text-sm font-semibold">Source Traces</h3>
              <div v-if="selectedRun.source_traces?.length" class="mt-3 space-y-2">
                <div
                  v-for="trace in selectedRun.source_traces"
                  :key="`${trace.source_id}:${trace.locator}`"
                  class="rounded border border-subtle bg-surface-muted p-3 text-xs"
                >
                  <div class="font-medium text-ink-primary">{{ trace.source_title || trace.source_id }}</div>
                  <div class="mt-1 text-ink-muted">{{ trace.locator }} · {{ fmtConfidence(trace.confidence) }}</div>
                  <div class="mt-2 text-ink-secondary">{{ trace.excerpt }}</div>
                </div>
              </div>
              <div v-else class="mt-3 text-sm text-ink-muted">No source traces captured.</div>
            </div>
            <div class="rounded-lg border border-subtle bg-surface p-4">
              <h3 class="text-sm font-semibold">Current vs Previous</h3>
              <div v-if="selectedRunDiff.length" class="mt-3 space-y-2">
                <div
                  v-for="row in selectedRunDiff"
                  :key="row.field"
                  class="rounded border border-subtle bg-surface-muted p-3 text-xs"
                >
                  <div class="font-medium">{{ row.field }}</div>
                  <div class="mt-1 text-ink-secondary">Current: {{ row.current }}</div>
                  <div class="mt-1 text-ink-muted">Previous: {{ row.previous }}</div>
                </div>
              </div>
              <div v-else class="mt-3 text-sm text-ink-muted">
                No previous run diff available for this tracker.
              </div>
            </div>
          </section>
        </div>
      </section>

      <section v-else-if="activeTab === 'aggregate'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Weekly Aggregate</h2>
            <p class="text-sm text-ink-muted">
              Consumes structured tracker outputs and selected source traces only.
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <select
              v-model="aggregateModuleFilter"
              class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            >
              <option value="all">All Modules</option>
              <option value="macro">Macro</option>
              <option value="industry">Industry</option>
              <option value="company">Company</option>
              <option value="cross_tracker">Cross Tracker</option>
              <option value="watchlist">Watchlist</option>
            </select>
            <select
              v-model="aggregateDirectionFilter"
              class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            >
              <option value="all">All Directions</option>
              <option value="positive">Positive</option>
              <option value="negative">Negative</option>
              <option value="neutral">Neutral</option>
              <option value="watch">Watch</option>
            </select>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="runAction('Queued aggregate', () => api.stockResearch.runAggregate({ force: true }))"
            >
              <Layers class="h-4 w-4" />
              Run Aggregate
            </button>
            <button
              v-if="aggregate"
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="retryAggregate"
            >
              <RefreshCw class="h-4 w-4" />
              Retry
            </button>
            <button
              v-if="aggregate"
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="cancelAggregate"
            >
              <Square class="h-4 w-4" />
              Cancel
            </button>
          </div>
        </div>
        <div v-if="aggregate" class="space-y-4">
          <div class="rounded-lg border border-subtle bg-surface p-4 text-sm">
            <div class="font-medium">{{ aggregate.period_id }}</div>
            <div class="mt-1 text-ink-muted">
              {{ aggregate.included_tracker_run_ids?.length || 0 }} included runs ·
              {{ aggregate.excluded_tracker_warnings?.length || 0 }} stale warnings
            </div>
          </div>
          <div v-if="aggregateWarnings.length" class="rounded-lg border border-warning/40 bg-warning-soft p-4 text-sm text-warning-ink">
            <h3 class="text-sm font-semibold">Warnings</h3>
            <div class="mt-2 grid gap-2 md:grid-cols-2">
              <div
                v-for="warning in aggregateWarnings"
                :key="`${warning.kind}:${warning.tracker_id}:${warning.title}`"
                class="rounded border border-warning/30 bg-surface/50 px-3 py-2"
              >
                <div class="text-xs uppercase">{{ warning.kind }}</div>
                <div class="mt-1 text-ink-primary">{{ warning.tracker_id || 'tracker' }} · {{ warning.title }}</div>
              </div>
            </div>
          </div>
          <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Module</th>
                  <th class="px-3 py-2">Tracker</th>
                  <th class="px-3 py-2">Summary</th>
                  <th class="px-3 py-2">Sources</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in aggregateModuleRows" :key="row.id" class="border-b border-subtle last:border-0">
                  <td class="px-3 py-2">{{ row.module }}</td>
                  <td class="px-3 py-2">{{ row.tracker_id || 'n/a' }}</td>
                  <td class="max-w-xl px-3 py-2 text-ink-secondary">
                    <div class="line-clamp-2">{{ row.title }}</div>
                  </td>
                  <td class="px-3 py-2">{{ row.source_count }}</td>
                </tr>
                <tr v-if="aggregateModuleRows.length === 0">
                  <td colspan="4" class="px-3 py-8 text-center text-sm text-ink-muted">
                    No aggregate modules for this filter.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Signal</th>
                  <th class="px-3 py-2">Tracker</th>
                  <th class="px-3 py-2">Direction</th>
                  <th class="px-3 py-2">Sources</th>
                  <th class="px-3 py-2">Trace Preview</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="signal in filteredAggregateSignals" :key="`${signal.source_tracker_id}:${signal.id}`" class="border-b border-subtle last:border-0">
                  <td class="max-w-xl px-3 py-2">{{ signal.observation }}</td>
                  <td class="px-3 py-2">{{ signal.source_tracker_id }}</td>
                  <td class="px-3 py-2">{{ signal.direction }}</td>
                  <td class="px-3 py-2">{{ signal.source_traces?.length || 0 }}</td>
                  <td class="max-w-md px-3 py-2 text-ink-secondary">
                    <div v-if="firstTrace(signal)" class="line-clamp-2">
                      {{ firstTrace(signal).source_title }} · {{ firstTrace(signal).locator }} ·
                      {{ firstTrace(signal).excerpt }}
                    </div>
                    <span v-else class="text-ink-muted">No trace.</span>
                  </td>
                </tr>
                <tr v-if="filteredAggregateSignals.length === 0">
                  <td colspan="5" class="px-3 py-8 text-center text-sm text-ink-muted">
                    No aggregate signals yet.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <pre class="max-h-96 overflow-auto rounded-lg border border-subtle bg-surface p-4 text-xs whitespace-pre-wrap">{{ aggregate.markdown }}</pre>
          <div v-if="aggregate.html_blocks?.length" class="rounded-lg border border-subtle bg-surface p-4">
            <h3 class="text-sm font-semibold">HTML-Ready Blocks</h3>
            <div class="mt-3 space-y-2 text-sm text-ink-secondary">
              <div
                v-for="(block, index) in aggregate.html_blocks"
                :key="index"
                class="rounded border border-subtle bg-surface-muted p-3"
              >
                <div class="text-xs uppercase text-ink-muted">{{ block.kind || 'block' }}</div>
                <div class="mt-1 whitespace-pre-wrap">{{ block.body || block.markdown || 'No body.' }}</div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="rounded-lg border border-subtle bg-surface p-6 text-sm text-ink-muted">
          No weekly aggregate yet.
        </div>
      </section>

      <section v-else-if="activeTab === 'strategy'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Strategy Map</h2>
            <p class="text-sm text-ink-muted">
              Table-first qualitative map. Research guidance only, not automated trading.
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-md bg-accent px-3 py-2 text-sm font-medium text-white focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="runAction('Queued strategy map', () => api.stockResearch.runStrategyMap({ force: true }))"
            >
              <GitBranch class="h-4 w-4" />
              Run Strategy Map
            </button>
            <button
              v-if="strategyMap"
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="retryStrategyMap"
            >
              <RefreshCw class="h-4 w-4" />
              Retry
            </button>
            <button
              v-if="strategyMap"
              type="button"
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="busy"
              @click="cancelStrategyMap"
            >
              <Square class="h-4 w-4" />
              Cancel
            </button>
          </div>
        </div>
        <div v-if="strategyMap" class="space-y-4">
          <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Node</th>
                  <th class="px-3 py-2">Posture</th>
                  <th class="px-3 py-2">Action</th>
                  <th class="px-3 py-2">Source Traces</th>
                  <th class="px-3 py-2">Trace Preview</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="node in strategyNodes" :key="node.id" class="border-b border-subtle last:border-0">
                  <td class="px-3 py-2 font-medium">{{ node.label }}</td>
                  <td class="px-3 py-2">{{ node.posture }}</td>
                  <td class="px-3 py-2">{{ node.qualitative_action }}</td>
                  <td class="px-3 py-2">{{ node.source_traces?.length || 0 }}</td>
                  <td class="max-w-md px-3 py-2 text-ink-secondary">
                    <div v-if="firstTrace(node)" class="line-clamp-2">
                      {{ firstTrace(node).source_title }} · {{ firstTrace(node).locator }} ·
                      {{ firstTrace(node).excerpt }}
                    </div>
                    <span v-else class="text-ink-muted">No trace.</span>
                  </td>
                </tr>
                <tr v-if="strategyNodes.length === 0">
                  <td colspan="5" class="px-3 py-8 text-center text-sm text-ink-muted">
                    No strategy nodes yet.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
            <div class="border-b border-subtle px-4 py-3">
              <h3 class="text-sm font-semibold">Source Inspector</h3>
            </div>
            <table class="min-w-full text-left text-sm">
              <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Kind</th>
                  <th class="px-3 py-2">Node / Edge</th>
                  <th class="px-3 py-2">Source</th>
                  <th class="px-3 py-2">Locator</th>
                  <th class="px-3 py-2">Excerpt</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in strategySourceRows" :key="row.id" class="border-b border-subtle last:border-0">
                  <td class="px-3 py-2">{{ row.kind }}</td>
                  <td class="px-3 py-2 font-medium">{{ row.label }}</td>
                  <td class="px-3 py-2">{{ row.trace.source_title || row.trace.source_id || 'Source' }}</td>
                  <td class="px-3 py-2">{{ row.trace.locator || 'n/a' }}</td>
                  <td class="max-w-xl px-3 py-2 text-ink-secondary">
                    <div class="line-clamp-2">{{ row.trace.excerpt || 'No excerpt.' }}</div>
                  </td>
                </tr>
                <tr v-if="strategySourceRows.length === 0">
                  <td colspan="5" class="px-3 py-8 text-center text-sm text-ink-muted">
                    No strategy source traces yet.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <h3 class="text-sm font-semibold">Diff Versus Prior Map</h3>
            <div class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="item in strategyMap.diff || []"
                :key="`${item.id}:${item.state}`"
                class="rounded bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
              >
                {{ item.label }} · {{ item.state }}
              </span>
              <span v-if="!strategyMap.diff?.length" class="text-sm text-ink-muted">
                No diff states.
              </span>
            </div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <h3 class="text-sm font-semibold">Unresolved Contradictions</h3>
            <div v-if="strategyContradictions.length" class="mt-3 space-y-2">
              <div
                v-for="item in strategyContradictions"
                :key="item.id || item.description"
                class="rounded border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning-ink"
              >
                <div>{{ item.description || item.claim || 'Contradiction' }}</div>
                <div v-if="item.source_traces?.length" class="mt-1 text-xs">
                  {{ item.source_traces[0].source_title }} · {{ item.source_traces[0].locator }}
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-sm text-ink-muted">No unresolved contradictions.</div>
          </div>
        </div>
        <div v-else class="rounded-lg border border-subtle bg-surface p-6 text-sm text-ink-muted">
          No strategy map yet.
        </div>
      </section>

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

      <section v-else-if="activeTab === 'review'" class="space-y-4">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Review Queue</h2>
            <p class="text-sm text-ink-muted">
              Triage missing sources, failed jobs, strategy changes, and proposed lessons.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select
              v-model="reviewFilter"
              class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            >
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="waived">Waived</option>
              <option value="rejected">Rejected</option>
              <option value="all">All</option>
            </select>
            <select
              v-model="reviewTypeFilter"
              class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
            >
              <option value="all">All Types</option>
              <option v-for="type in reviewTypes" :key="type" :value="type">{{ type }}</option>
            </select>
            <input
              v-model="reviewRationale"
              class="w-64 rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
              placeholder="Review rationale"
            />
          </div>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="px-3 py-2">Item</th>
                <th class="px-3 py-2">Type</th>
                <th class="px-3 py-2">Status</th>
                <th class="px-3 py-2">Artifact</th>
                <th class="px-3 py-2">Sources</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredReviewItems" :key="item.id" class="border-b border-subtle last:border-0">
                <td class="max-w-xl px-3 py-2">
                  <div class="font-medium">{{ item.title }}</div>
                  <div class="text-xs text-ink-muted">
                    {{ item.severity }}
                    <span v-if="item.error"> · {{ item.error }}</span>
                    <span v-else-if="item.rationale"> · {{ item.rationale }}</span>
                  </div>
                </td>
                <td class="px-3 py-2">{{ item.item_type }}</td>
                <td class="px-3 py-2">{{ item.status }}</td>
                <td class="px-3 py-2">{{ item.artifact_id || item.tracker_id || 'n/a' }}</td>
                <td class="max-w-sm px-3 py-2 text-xs text-ink-secondary">
                  <div v-if="item.source_refs?.length" class="line-clamp-2">
                    {{ item.source_refs[0].source_title || item.source_refs[0].source_id || item.source_refs[0].tracker_id || 'Source' }}
                    <span v-if="item.source_refs[0].locator"> · {{ item.source_refs[0].locator }}</span>
                  </div>
                  <span v-else class="text-ink-muted">n/a</span>
                </td>
                <td class="px-3 py-2">
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="item.status !== 'open'"
                      title="Resolve"
                      @click="updateReview(item, 'resolved')"
                    >
                      <Check class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="item.status !== 'open'"
                      title="Waive"
                      @click="updateReview(item, 'waived')"
                    >
                      <Archive class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="item.status !== 'open'"
                      title="Reject"
                      @click="updateReview(item, 'rejected')"
                    >
                      <X class="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="filteredReviewItems.length === 0">
                <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No review items.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-else-if="activeTab === 'evaluation'" class="space-y-4">
        <div class="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Evaluation</h2>
            <p class="text-sm text-ink-muted">
              Run metrics, tracker trends, and lesson review state.
            </p>
          </div>
          <select
            v-model="evaluationTrackerFilter"
            class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          >
            <option value="all">All Trackers</option>
            <option v-for="trackerId in evaluationTrackerIds" :key="trackerId" :value="trackerId">
              {{ trackerId }}
            </option>
          </select>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="px-3 py-2">Tracker</th>
                <th class="px-3 py-2">Runs</th>
                <th class="px-3 py-2">Avg Coverage</th>
                <th class="px-3 py-2">Missing Sources</th>
                <th class="px-3 py-2">Reviewer Avg</th>
                <th class="px-3 py-2">Latest</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in trackerMetricRows" :key="row.tracker_id" class="border-b border-subtle last:border-0">
                <td class="px-3 py-2">{{ row.tracker_name }}</td>
                <td class="px-3 py-2">{{ row.runs }}</td>
                <td class="px-3 py-2">{{ fmtConfidence(row.avg_coverage) }}</td>
                <td class="px-3 py-2">{{ row.missing_total }}</td>
                <td class="px-3 py-2">{{ row.avg_reviewer ?? 'n/a' }}</td>
                <td class="px-3 py-2">{{ fmtDate(row.latest_at) }}</td>
              </tr>
              <tr v-if="trackerMetricRows.length === 0">
                <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No tracker trend rows yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="px-3 py-2">Run</th>
                <th class="px-3 py-2">Tracker</th>
                <th class="px-3 py-2">Duration</th>
                <th class="px-3 py-2">Sources</th>
                <th class="px-3 py-2">Source Quality</th>
                <th class="px-3 py-2">Coverage</th>
                <th class="px-3 py-2">Issues</th>
                <th class="px-3 py-2">Reviewer</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in filteredEvaluationRows" :key="`${row.tracker_id}:${row.run_id}`" class="border-b border-subtle last:border-0">
                <td class="px-3 py-2 font-mono text-xs">{{ row.run_id }}</td>
                <td class="px-3 py-2">{{ row.tracker_name }}</td>
                <td class="px-3 py-2">{{ row.duration_ms || 0 }} ms</td>
                <td class="px-3 py-2">{{ row.source_count || 0 }}</td>
                <td class="px-3 py-2">
                  {{ fmtConfidence(row.source_quality?.average) }}
                  <div
                    v-if="row.fallback_used || row.preserved_previous_artifact || row.failure_reason"
                    class="mt-1 text-[11px] text-ink-muted"
                  >
                    <span v-if="row.fallback_used">fallback</span>
                    <span v-if="row.preserved_previous_artifact">
                      preserved {{ row.preserved_previous_artifact }}
                    </span>
                    <span v-if="row.failure_reason">{{ row.failure_reason }}</span>
                  </div>
                </td>
                <td class="px-3 py-2">{{ fmtConfidence(row.evidence_coverage) }}</td>
                <td class="px-3 py-2">
                  {{ row.contradiction_count || 0 }} contradictions ·
                  {{ row.missing_source_count || 0 }} missing
                </td>
                <td class="min-w-72 px-3 py-2">
                  <div class="text-xs text-ink-muted">
                    Avg: {{ row.reviewer_score ?? 'n/a' }}
                  </div>
                  <div class="mt-2 grid grid-cols-5 gap-1">
                    <label
                      v-for="field in runReviewScoreFields"
                      :key="`${row.tracker_id}:${row.run_id}:${field.id}`"
                      class="block text-[10px] uppercase tracking-wide text-ink-muted"
                    >
                      <span>{{ field.label }}</span>
                      <input
                        type="number"
                        min="0"
                        max="5"
                        step="1"
                        :value="runReviewDraft(row)[field.id]"
                        @input="setRunReviewScore(row, field.id, $event.target.value)"
                        class="mt-1 w-full rounded border border-subtle bg-surface px-1.5 py-1 text-xs text-ink-primary focus-ring"
                      />
                    </label>
                  </div>
                  <input
                    :value="runReviewDraft(row).review_notes"
                    @input="setRunReviewNotes(row, $event.target.value)"
                    class="mt-2 w-full rounded border border-subtle bg-surface px-2 py-1 text-xs text-ink-primary focus-ring"
                    placeholder="Review notes"
                  />
                  <button
                    type="button"
                    class="mt-2 inline-flex items-center gap-1 rounded-md border border-subtle px-2 py-1 text-xs font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
                    :disabled="busy"
                    title="Save run review"
                    @click="saveRunReview(row)"
                  >
                    <Check class="h-3.5 w-3.5" />
                    Save Review
                  </button>
                </td>
              </tr>
              <tr v-if="filteredEvaluationRows.length === 0">
                <td colspan="8" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No evaluation rows yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
          <table class="min-w-full text-left text-sm">
            <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="px-3 py-2">Lesson</th>
                <th class="px-3 py-2">Tracker</th>
                <th class="px-3 py-2">Run</th>
                <th class="px-3 py-2">Review</th>
                <th class="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in knowledgeReviewRows" :key="`${row.tracker_id}:${row.run_id}:${row.id}`" class="border-b border-subtle last:border-0">
                <td class="max-w-xl px-3 py-2">{{ row.text }}</td>
                <td class="px-3 py-2">{{ row.tracker_name }}</td>
                <td class="px-3 py-2 font-mono text-xs">{{ row.run_id }}</td>
                <td class="px-3 py-2">{{ row.review_status || 'open' }}</td>
                <td class="px-3 py-2">
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || row.review_status === 'resolved'"
                      title="Accept lesson"
                      @click="reviewKnowledgeUpdate(row, row, 'resolved')"
                    >
                      <Check class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || row.review_status === 'rejected'"
                      title="Reject lesson"
                      @click="reviewKnowledgeUpdate(row, row, 'rejected')"
                    >
                      <X class="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="knowledgeReviewRows.length === 0">
                <td colspan="5" class="px-3 py-8 text-center text-sm text-ink-muted">
                  No proposed lessons yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
