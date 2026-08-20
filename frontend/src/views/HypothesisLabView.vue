<script setup>
import { computed, onMounted, ref } from "vue";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Play,
  RefreshCw,
  Timer,
} from "lucide-vue-next";
import { api } from "../api.js";
import ResearchPagesNav from "../components/research-pages/ResearchPagesNav.vue";

const payload = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const busy = ref(false);
const actionMessage = ref("");
const liveVintageDate = ref(new Date().toISOString().slice(0, 10));
const debugVintageDate = ref("");

const summary = computed(() => payload.value?.summary || {});
const sections = computed(() => payload.value?.sections || {});
const health = computed(() => payload.value?.source_health || {});
const issues = computed(() => payload.value?.doctor_issues || []);
const timeline = computed(() => sections.value.vintage_timeline || []);
const hypotheses = computed(() => sections.value.hypotheses || []);
const outcomes = computed(() => sections.value.outcomes || []);
const calibration = computed(() => sections.value.calibration || []);

async function load({ showLoading = true } = {}) {
  if (showLoading) loading.value = true;
  error.value = "";
  try {
    payload.value = await api.researchPages.hypothesisLab();
  } catch (e) {
    error.value = e.message || "Could not load Hypothesis Lab.";
  } finally {
    loading.value = false;
  }
}

async function refreshPage() {
  if (refreshing.value || loading.value) return;
  refreshing.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    actionMessage.value = "Creating current live vintage, evaluating closed vintages, and recalibrating.";
    const today = new Date().toISOString().slice(0, 10);
    const createResult = await api.stockResearch.createHypotheses({
      vintageDate: today,
      vintageKind: "forward_live",
      allowDebugBackfill: false,
    });
    const closedDates = closedPendingForwardLiveVintageDates();
    let evaluatedCount = 0;
    let evaluationErrorCount = 0;
    for (const vintageDate of closedDates) {
      try {
        const result = await api.stockResearch.evaluateHypotheses(vintageDate, {});
        evaluatedCount += Number(result?.evaluated_count || 0);
      } catch {
        evaluationErrorCount += 1;
      }
    }
    const calibrationResult = await api.stockResearch.calibrateHypotheses();
    await load({ showLoading: false });
    actionMessage.value = hypothesisRefreshMessage({
      createdCount: Number(createResult?.created_count || 0),
      evaluatedVintageCount: closedDates.length,
      evaluatedCount,
      evaluationErrorCount,
      eligibleOutcomeCount: Number(calibrationResult?.eligible_outcome_count || 0),
    });
  } catch (e) {
    error.value = e.message || "Could not refresh Hypothesis Lab.";
  } finally {
    refreshing.value = false;
  }
}

function closedPendingForwardLiveVintageDates() {
  const dates = new Set();
  for (const row of hypotheses.value) {
    if (row.vintage_kind === "forward_live" && row.status === "closed_pending" && row.vintage_date) {
      dates.add(row.vintage_date);
    }
  }
  return Array.from(dates).sort();
}

function plural(count, singular, pluralText = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralText}`;
}

function hypothesisRefreshMessage(result) {
  const parts = [`current live vintage has ${plural(result.createdCount, "hypothesis", "hypotheses")}`];
  if (result.evaluatedVintageCount) {
    parts.push(`evaluated ${plural(result.evaluatedVintageCount, "closed vintage")} (${plural(result.evaluatedCount, "outcome")})`);
  } else {
    parts.push("no closed forward-live vintages needed evaluation");
  }
  if (result.evaluationErrorCount) {
    parts.push(`${plural(result.evaluationErrorCount, "evaluation")} failed`);
  }
  parts.push(`calibration has ${plural(result.eligibleOutcomeCount, "eligible outcome")}`);
  return `Hypothesis cycle refreshed: ${parts.join("; ")}.`;
}

async function runAction(label, fn) {
  if (busy.value) return;
  busy.value = true;
  actionMessage.value = "";
  try {
    await fn();
    actionMessage.value = label;
    await load();
  } catch (e) {
    error.value = e.message || "Hypothesis action failed.";
  } finally {
    busy.value = false;
  }
}

function fmtDateTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function createLive() {
  return runAction(`Created live vintage ${liveVintageDate.value}.`, () =>
    api.stockResearch.createHypotheses({
      vintageDate: liveVintageDate.value,
      vintageKind: "forward_live",
      allowDebugBackfill: false,
    }),
  );
}

function createDebug() {
  return runAction(`Created debug backfill ${debugVintageDate.value}.`, () =>
    api.stockResearch.createHypotheses({
      vintageDate: debugVintageDate.value,
      vintageKind: "debug_backfill",
      allowDebugBackfill: true,
    }),
  );
}

function evaluateVintage(vintageDate) {
  return runAction(`Evaluated vintage ${vintageDate}.`, () =>
    api.stockResearch.evaluateHypotheses(vintageDate, {}),
  );
}

function calibrate() {
  return runAction("Generated calibration summary.", () =>
    api.stockResearch.calibrateHypotheses(),
  );
}

function fmtPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${Math.round(number * 100)}%`;
}

function fmtReturn(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${number.toFixed(1)}%`;
}

function issueClass(severity) {
  if (severity === "error") return "border-danger/30 bg-danger-soft text-danger-ink";
  if (severity === "warning") return "border-warning/30 bg-warning-soft text-warning-ink";
  return "border-subtle bg-surface-muted text-ink-secondary";
}

function kindClass(kind) {
  if (kind === "debug_backfill") return "bg-warning-soft text-warning-ink";
  return "bg-success-soft text-success-ink";
}

function statusClass(status) {
  if (status === "evaluated") return "bg-success-soft text-success-ink";
  if (status === "closed_pending") return "bg-danger-soft text-danger-ink";
  return "bg-surface-muted text-ink-muted";
}

function barStyle(value) {
  const pct = Math.max(0, Math.min(100, Number(value) * 100 || 0));
  return { width: `${pct}%` };
}

onMounted(load);
</script>

<template>
  <div>
    <div>
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div class="vogue-label">
              Research Pages
            </div>
            <h1 class="font-display text-large-title text-ink-primary">
              Hypothesis Lab
            </h1>
            <div class="mt-1 text-sm text-ink-muted">
              {{ payload?.as_of || "No as-of date" }} · {{ payload?.status || "loading" }}
              <span v-if="payload?.generated_at"> · Generated {{ fmtDateTime(payload.generated_at) }}</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <ResearchPagesNav />
            <button
              type="button"
              class="btn-bordered focus-ring"
              :disabled="loading || refreshing || busy"
              @click="refreshPage"
            >
              <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
              <RefreshCw v-else class="h-4 w-4" />
              {{ refreshing ? "Refreshing" : "Refresh" }}
            </button>
          </div>
        </div>
        <div
          v-if="actionMessage"
          class="rounded-md border border-success/30 bg-success-soft px-3 py-2 text-sm text-success-ink"
        >
          {{ actionMessage }}
        </div>
      </div>
    </div>

    <div class="mx-auto max-w-7xl px-5 py-6">
      <div v-if="loading" class="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 class="h-4 w-4 animate-spin" />
        Loading Hypothesis Lab
      </div>
      <div v-else-if="error" class="rounded-md border border-danger/30 bg-danger-soft p-4 text-sm text-danger-ink">
        {{ error }}
      </div>
      <div v-else class="space-y-6">
        <div class="grid gap-3 md:grid-cols-5">
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Hypotheses</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.hypothesis_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Live</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.live_hypothesis_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Debug</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.debug_hypothesis_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Evaluated</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.evaluated_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Source traces</div>
            <div class="mt-2 text-2xl font-semibold">{{ health.source_trace_count || 0 }}</div>
          </div>
        </div>

        <section class="rounded-card bg-surface shadow-card">
          <div class="flex flex-wrap items-end justify-between gap-3 border-b border-subtle px-4 py-3">
            <div>
              <h2 class="font-display text-title3">Vintage Controls</h2>
              <div class="mt-1 text-sm text-ink-muted">
                Debug backfills remain ineligible for training.
              </div>
            </div>
            <div class="flex flex-wrap items-end gap-2">
              <label class="text-xs font-medium text-ink-muted">
                Live vintage
                <input
                  v-model="liveVintageDate"
                  type="date"
                  class="mt-1 block rounded-md border border-subtle bg-surface px-2 py-1 text-sm text-ink-primary focus-ring"
                />
              </label>
              <button
                type="button"
                class="btn-filled focus-ring"
                :disabled="busy || !liveVintageDate"
                @click="createLive"
              >
                <Play class="h-4 w-4" />
                Create Live
              </button>
              <label class="text-xs font-medium text-ink-muted">
                Debug vintage
                <input
                  v-model="debugVintageDate"
                  type="date"
                  class="mt-1 block rounded-md border border-subtle bg-surface px-2 py-1 text-sm text-ink-primary focus-ring"
                />
              </label>
              <button
                type="button"
                class="btn-bordered focus-ring"
                :disabled="busy || !debugVintageDate"
                @click="createDebug"
              >
                <FlaskConical class="h-4 w-4" />
                Debug Backfill
              </button>
              <button
                type="button"
                class="btn-bordered focus-ring"
                :disabled="busy"
                @click="calibrate"
              >
                <BadgeCheck class="h-4 w-4" />
                Calibrate
              </button>
            </div>
          </div>

          <div v-if="timeline.length === 0" class="p-6 text-sm text-ink-muted">
            No hypothesis vintages yet. Create a current live vintage with POST /api/stock-research/hypotheses/create.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Vintage</th>
                  <th class="px-3 py-2">Kind</th>
                  <th class="px-3 py-2 text-right">Generated</th>
                  <th class="px-3 py-2 text-right">Evaluated</th>
                  <th class="px-3 py-2 text-right">Pending</th>
                  <th class="px-3 py-2">Training eligibility</th>
                  <th class="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="vintage in timeline"
                  :key="`${vintage.vintage_date}-${vintage.vintage_kind}`"
                  class="border-b border-subtle last:border-0"
                >
                  <td class="px-3 py-3 font-medium">{{ vintage.vintage_date }}</td>
                  <td class="px-3 py-3">
                    <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="kindClass(vintage.vintage_kind)">
                      {{ vintage.vintage_kind }}
                    </span>
                  </td>
                  <td class="px-3 py-3 text-right">{{ vintage.generated_count }}</td>
                  <td class="px-3 py-3 text-right">{{ vintage.evaluated_count }}</td>
                  <td class="px-3 py-3 text-right">{{ vintage.pending_count }}</td>
                  <td class="px-3 py-3 text-xs text-ink-secondary">{{ vintage.training_eligibility }}</td>
                  <td class="px-3 py-3 text-right">
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 rounded-md border border-subtle px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy"
                      @click="evaluateVintage(vintage.vintage_date)"
                    >
                      <RefreshCw class="h-3.5 w-3.5" />
                      Evaluate
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="overflow-hidden rounded-card bg-surface shadow-card">
          <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
            <Timer class="h-4 w-4 text-ink-muted" />
            <h2 class="font-display text-title3">Hypothesis Table</h2>
          </div>
          <div v-if="hypotheses.length === 0" class="p-6 text-sm text-ink-muted">
            No hypotheses are available.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Claim</th>
                  <th class="px-3 py-2">Ticker</th>
                  <th class="px-3 py-2">Direction</th>
                  <th class="px-3 py-2 text-right">Confidence</th>
                  <th class="px-3 py-2 text-right">Quality</th>
                  <th class="px-3 py-2">Window</th>
                  <th class="px-3 py-2">Status</th>
                  <th class="px-3 py-2">Training</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in hypotheses" :key="row.hypothesis_id" class="border-b border-subtle align-top last:border-0">
                  <td class="max-w-2xl px-3 py-3">
                    <div class="font-medium text-ink-primary">{{ row.claim }}</div>
                    <div class="mt-1 text-xs text-ink-muted">{{ row.hypothesis_id }} · {{ row.vintage_date }}</div>
                    <div v-if="row.source_refs?.length" class="mt-2 space-y-1">
                      <div
                        v-for="sourceRef in row.source_refs.slice(0, 2)"
                        :key="`${row.hypothesis_id}-${sourceRef.source_id || sourceRef.source_title}-${sourceRef.locator}`"
                        class="rounded border border-subtle bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
                      >
                        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span class="font-medium text-ink-primary">{{ sourceRef.source_title || "Source" }}</span>
                          <span>{{ sourceRef.source_type || "unknown" }}</span>
                          <span>{{ sourceRef.published_at || "date unknown" }}</span>
                          <span>{{ fmtPct(sourceRef.confidence) }}</span>
                        </div>
                        <div class="mt-1 line-clamp-2">{{ sourceRef.excerpt || sourceRef.locator || "No excerpt provided." }}</div>
                      </div>
                    </div>
                    <div v-else class="mt-2 rounded border border-warning/30 bg-warning-soft px-2 py-1 text-xs text-warning-ink">
                      No source trace captured.
                    </div>
                  </td>
                  <td class="px-3 py-3">{{ row.ticker || "n/a" }}</td>
                  <td class="px-3 py-3">{{ row.direction }}</td>
                  <td class="px-3 py-3 text-right">{{ fmtPct(row.confidence) }}</td>
                  <td class="px-3 py-3 text-right">{{ fmtPct(row.source_quality_score) }}</td>
                  <td class="px-3 py-3 text-xs text-ink-secondary">
                    {{ row.evaluation_window_start }} to {{ row.evaluation_window_end }}
                  </td>
                  <td class="px-3 py-3">
                    <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="statusClass(row.status)">
                      {{ row.status }}
                    </span>
                  </td>
                  <td class="px-3 py-3">
                    <span
                      class="rounded-full px-2 py-0.5 text-xs font-medium"
                      :class="row.training_eligible ? 'bg-success-soft text-success-ink' : 'bg-surface-muted text-ink-muted'"
                    >
                      {{ row.training_eligible ? "eligible" : "not eligible" }}
                    </span>
                    <div v-if="row.vintage_kind === 'debug_backfill'" class="mt-1 text-xs text-warning-ink">
                      debug excluded
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(20rem,0.8fr)]">
          <section class="rounded-card bg-surface shadow-card">
            <div class="border-b border-subtle px-4 py-3">
              <h2 class="font-display text-title3">Outcome Table</h2>
            </div>
            <div v-if="outcomes.length === 0" class="p-4 text-sm text-ink-muted">
              No evaluated outcomes yet.
            </div>
            <div v-else class="overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
                  <tr>
                    <th class="px-3 py-2">Ticker</th>
                    <th class="px-3 py-2 text-right">Abs</th>
                    <th class="px-3 py-2 text-right">Bench</th>
                    <th class="px-3 py-2 text-right">Rel</th>
                    <th class="px-3 py-2">Result</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in outcomes" :key="row.hypothesis_id" class="border-b border-subtle last:border-0">
                    <td class="px-3 py-2">{{ row.ticker || "n/a" }}</td>
                    <td class="px-3 py-2 text-right">{{ fmtReturn(row.absolute_return_pct) }}</td>
                    <td class="px-3 py-2 text-right">{{ fmtReturn(row.benchmark_return_pct) }}</td>
                    <td class="px-3 py-2 text-right">{{ fmtReturn(row.relative_return_pct) }}</td>
                    <td class="px-3 py-2">{{ row.directional_result }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="rounded-card bg-surface shadow-card">
            <div class="border-b border-subtle px-4 py-3">
              <h2 class="font-display text-title3">Calibration Chart</h2>
            </div>
            <div v-if="calibration.length === 0" class="p-4 text-sm text-ink-muted">
              No calibration summary yet.
            </div>
            <div v-else class="space-y-4 p-4">
              <div v-for="row in calibration" :key="row.confidence_bucket" class="space-y-1">
                <div class="flex items-center justify-between gap-3 text-sm">
                  <span class="font-medium capitalize">{{ row.confidence_bucket }}</span>
                  <span class="text-ink-muted">{{ fmtPct(row.hit_rate) }} · n={{ row.sample_size }}</span>
                </div>
                <div class="h-2 overflow-hidden rounded bg-surface-muted">
                  <div class="h-full rounded bg-accent" :style="barStyle(row.hit_rate)" />
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-card bg-surface shadow-card">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <AlertTriangle class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-title3">Leakage Doctor</h2>
            </div>
            <div v-if="issues.length === 0" class="flex items-center gap-2 p-4 text-sm text-success-ink">
              <CheckCircle2 class="h-4 w-4" />
              No hypothesis doctor issues.
            </div>
            <div v-else class="space-y-2 p-4">
              <div
                v-for="issue in issues"
                :key="`${issue.type}-${issue.artifact_id || issue.message}`"
                class="rounded-md border px-3 py-2 text-sm"
                :class="issueClass(issue.severity)"
              >
                <div class="font-medium">{{ issue.type }}</div>
                <div class="mt-1">{{ issue.message }}</div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
