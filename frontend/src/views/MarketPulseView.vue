<script setup>
import { computed, onMounted, ref } from "vue";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ExternalLink,
  FlaskConical,
  Loader2,
  RefreshCw,
  TableProperties,
  TrendingDown,
  TrendingUp,
} from "lucide-vue-next";
import { api } from "../api.js";
import ResearchPagesNav from "../components/research-pages/ResearchPagesNav.vue";
import { runFullStockResearchRefresh } from "../researchPageJobs.js";

const payload = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const actionMessage = ref("");
const selectedSignal = ref(null);

const summary = computed(() => payload.value?.summary || {});
const sections = computed(() => payload.value?.sections || {});
const health = computed(() => payload.value?.source_health || {});
const issues = computed(() => payload.value?.doctor_issues || []);
const regime = computed(() => sections.value.market_regime || {});
const signals = computed(() => sections.value.ranked_signals || []);
const heatmap = computed(() => sections.value.theme_heatmap || []);
const diff = computed(() => sections.value.changed_since_last_week || {});
const catalysts = computed(() => sections.value.catalyst_calendar || []);
const nextSteps = computed(() => sections.value.next_steps || []);

async function load({ showLoading = true } = {}) {
  if (showLoading) loading.value = true;
  error.value = "";
  try {
    payload.value = await api.researchPages.marketPulse();
    selectedSignal.value = payload.value?.sections?.ranked_signals?.[0] || null;
  } catch (e) {
    error.value = e.message || "Could not load Market Pulse.";
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
    actionMessage.value = "Running active trackers, then rebuilding the weekly aggregate.";
    const result = await runFullStockResearchRefresh();
    await load({ showLoading: false });
    actionMessage.value = marketRefreshMessage(result);
  } catch (e) {
    error.value = e.message || "Could not refresh Market Pulse.";
  } finally {
    refreshing.value = false;
  }
}

function plural(count, singular, pluralText = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralText}`;
}

function sourceTraceGapText(count, singular) {
  if (count === 1) return `1 ${singular} still lacks source traces`;
  return `${count} ${singular}s still need source traces`;
}

function marketRefreshMessage(result) {
  const trackerText = plural(result.activeTrackerCount, "tracker");
  if (!result.activeTrackerCount) {
    return "No active trackers are configured; rebuilt the weekly aggregate from existing outputs.";
  }
  if (result.trackerErrorCount) {
    return `Full refresh ran ${trackerText}, but ${plural(result.trackerErrorCount, "tracker")} had errors. Review Stock Research runs.`;
  }
  if (!result.aggregateCompleted) {
    return `Full refresh ran ${trackerText}; the aggregate is still running. Results will update after it completes.`;
  }
  if (!summary.value.signal_count) {
    return `Full refresh ran ${trackerText} and rebuilt the aggregate, but no ranked signals were produced. Add tracker sources or review tracker outputs.`;
  }
  if (health.value.missing_trace_count || summary.value.weak_or_missing_signal_count) {
    return `Full refresh ran ${trackerText} and rebuilt ${plural(summary.value.signal_count, "signal")}, but ${sourceTraceGapText(summary.value.weak_or_missing_signal_count || health.value.missing_trace_count, "signal")}.`;
  }
  return `Full refresh complete: ran ${trackerText} and rebuilt ${plural(summary.value.signal_count, "signal")}.`;
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

function fmtPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${Math.round(number * 100)}%`;
}

function directionClass(direction) {
  const text = String(direction || "").toLowerCase();
  if (["bullish", "positive", "risk_on", "up"].includes(text)) {
    return "bg-success-soft text-success-ink";
  }
  if (["bearish", "negative", "risk_off", "down"].includes(text)) {
    return "bg-danger-soft text-danger-ink";
  }
  return "bg-surface-muted text-ink-muted";
}

function issueClass(severity) {
  if (severity === "error") return "border-danger/30 bg-danger-soft text-danger-ink";
  if (severity === "warning") return "border-warning/30 bg-warning-soft text-warning-ink";
  return "border-subtle bg-surface-muted text-ink-secondary";
}

function heatStyle(row) {
  const quality = Math.max(0.08, Math.min(1, Number(row.average_quality) || 0));
  if ((row.net_direction || 0) > 0) return { opacity: quality };
  if ((row.net_direction || 0) < 0) return { opacity: quality };
  return { opacity: Math.max(0.3, quality) };
}

function heatClass(row) {
  if ((row.net_direction || 0) > 0) return "bg-success";
  if ((row.net_direction || 0) < 0) return "bg-danger";
  return "bg-accent";
}

function sourceClass(sourceRef) {
  if (sourceRef?.source_id && sourceRef?.source_exists === false) {
    return "border-danger/30 bg-danger-soft text-danger-ink";
  }
  return "border-subtle";
}

onMounted(load);
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <div class="border-b border-subtle bg-surface">
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Research Pages
            </div>
            <h1 class="font-display text-2xl font-semibold text-ink-primary">
              Market Pulse
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
              class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
              :disabled="loading || refreshing"
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
        Loading Market Pulse
      </div>
      <div v-else-if="error" class="rounded-md border border-danger/30 bg-danger-soft p-4 text-sm text-danger-ink">
        {{ error }}
      </div>
      <div v-else class="space-y-6">
        <div class="grid gap-3 md:grid-cols-4">
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <div class="text-xs uppercase tracking-wide text-ink-muted">Signals</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.signal_count || 0 }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <div class="text-xs uppercase tracking-wide text-ink-muted">Primary sourced</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.primary_source_signal_count || 0 }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <div class="text-xs uppercase tracking-wide text-ink-muted">Weak or missing</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.weak_or_missing_signal_count || 0 }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface p-4">
            <div class="text-xs uppercase tracking-wide text-ink-muted">Avg source quality</div>
            <div class="mt-2 text-2xl font-semibold">{{ fmtPct(health.average_source_quality) }}</div>
          </div>
        </div>

        <section
          v-if="summary.empty_state || nextSteps.length"
          class="rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm text-warning-ink"
        >
          <div class="font-semibold">{{ summary.empty_state || "Market Pulse needs source data." }}</div>
          <div v-if="nextSteps.length" class="mt-3 grid gap-2 md:grid-cols-2">
            <div
              v-for="step in nextSteps"
              :key="`${step.method}-${step.endpoint}`"
              class="rounded-md border border-warning/30 bg-surface/70 p-3"
            >
              <div class="font-medium">{{ step.label }}</div>
              <div class="mt-1 font-mono text-xs">{{ step.method }} {{ step.endpoint }}</div>
              <div class="mt-1 text-xs">{{ step.requires }}</div>
            </div>
          </div>
        </section>

        <section class="rounded-lg border border-subtle bg-surface">
          <div class="border-b border-subtle px-4 py-3">
            <h2 class="font-display text-lg font-semibold">Market Regime</h2>
          </div>
          <div class="grid gap-3 p-4 lg:grid-cols-5">
            <div class="rounded-md border border-subtle bg-surface-muted p-3">
              <div class="text-xs uppercase tracking-wide text-ink-muted">Posture</div>
              <div class="mt-2 text-lg font-semibold capitalize">{{ regime.posture || "empty" }}</div>
            </div>
            <div class="rounded-md border border-subtle bg-surface-muted p-3">
              <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-ink-muted">
                <TrendingUp class="h-3.5 w-3.5" />
                Positive
              </div>
              <div class="mt-2 text-lg font-semibold">{{ regime.breadth?.positive_signals || 0 }}</div>
            </div>
            <div class="rounded-md border border-subtle bg-surface-muted p-3">
              <div class="flex items-center gap-2 text-xs uppercase tracking-wide text-ink-muted">
                <TrendingDown class="h-3.5 w-3.5" />
                Negative
              </div>
              <div class="mt-2 text-lg font-semibold">{{ regime.breadth?.negative_signals || 0 }}</div>
            </div>
            <div class="rounded-md border border-subtle bg-surface-muted p-3">
              <div class="text-xs uppercase tracking-wide text-ink-muted">Volatility</div>
              <div class="mt-2 text-sm text-ink-secondary">{{ regime.volatility?.status || "placeholder" }}</div>
            </div>
            <div class="rounded-md border border-subtle bg-surface-muted p-3">
              <div class="text-xs uppercase tracking-wide text-ink-muted">Rates and liquidity</div>
              <div class="mt-2 text-sm text-ink-secondary">Pending data foundation</div>
            </div>
          </div>
        </section>

        <div class="grid gap-6 xl:grid-cols-[minmax(0,1.8fr)_minmax(20rem,0.9fr)]">
          <section class="overflow-hidden rounded-lg border border-subtle bg-surface">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-subtle px-4 py-3">
              <h2 class="font-display text-lg font-semibold">Ranked Signals</h2>
              <div class="flex items-center gap-2 text-xs text-ink-muted">
                <TableProperties class="h-4 w-4" />
                {{ summary.period_id || "No aggregate" }}
              </div>
            </div>
            <div v-if="signals.length === 0" class="p-6 text-sm text-ink-muted">
              {{ summary.empty_state || "No ranked signals. Run a weekly aggregate after tracker runs complete." }}
            </div>
            <div v-else class="overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead class="bg-surface-muted text-left text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th class="px-3 py-2">Signal</th>
                    <th class="px-3 py-2">Direction</th>
                    <th class="px-3 py-2 text-right">Confidence</th>
                    <th class="px-3 py-2 text-right">Quality</th>
                    <th class="px-3 py-2 text-right">Primary</th>
                    <th class="px-3 py-2 text-right">Weak</th>
                    <th class="px-3 py-2">Related</th>
                    <th class="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="signal in signals"
                    :key="signal.signal_id"
                    class="border-b border-subtle align-top last:border-0"
                  >
                    <td class="max-w-xl px-3 py-3">
                      <button
                        type="button"
                        class="text-left font-medium text-ink-primary hover:text-accent focus-ring"
                        @click="selectedSignal = signal"
                      >
                        {{ signal.signal }}
                      </button>
                      <div class="mt-1 text-xs text-ink-muted">
                        {{ signal.signal_id }} · {{ signal.source_quality_reason || "source review pending" }}
                      </div>
                    </td>
                    <td class="px-3 py-3">
                      <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="directionClass(signal.direction)">
                        {{ signal.direction }}
                      </span>
                    </td>
                    <td class="px-3 py-3 text-right">{{ fmtPct(signal.confidence) }}</td>
                    <td class="px-3 py-3 text-right">{{ fmtPct(signal.source_quality_score) }}</td>
                    <td class="px-3 py-3 text-right">{{ signal.primary_source_count }}</td>
                    <td class="px-3 py-3 text-right">{{ signal.weak_source_count }}</td>
                    <td class="px-3 py-3 text-xs text-ink-secondary">
                      <div class="flex max-w-xs flex-wrap gap-1">
                        <span
                          v-for="tag in [...(signal.related_tickers || []), ...(signal.related_themes || [])].slice(0, 4)"
                          :key="tag"
                          class="rounded bg-surface-muted px-1.5 py-0.5"
                        >
                          {{ tag }}
                        </span>
                      </div>
                    </td>
                    <td class="px-3 py-3 text-right">
                      <div class="inline-flex items-center gap-1">
                        <button
                          type="button"
                          class="rounded-md border border-subtle p-1.5 text-ink-muted opacity-60 focus-ring disabled:cursor-not-allowed"
                          title="Signal-specific hypothesis drafting is planned; use Hypothesis Lab to create a dated vintage."
                          disabled
                        >
                          <FlaskConical class="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          class="rounded-md border border-subtle p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
                          title="Open source traces"
                          @click="selectedSignal = signal"
                        >
                          <ExternalLink class="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <aside class="space-y-6">
            <section class="rounded-lg border border-subtle bg-surface">
              <div class="border-b border-subtle px-4 py-3">
                <h2 class="font-display text-lg font-semibold">Theme Heat Map</h2>
              </div>
              <div v-if="heatmap.length === 0" class="p-4 text-sm text-ink-muted">
                No sector or theme groupings are available.
              </div>
              <div v-else class="grid grid-cols-2 gap-2 p-4">
                <div
                  v-for="row in heatmap"
                  :key="row.theme"
                  class="min-h-24 rounded-md border border-subtle p-3 text-white"
                  :class="heatClass(row)"
                  :style="heatStyle(row)"
                >
                  <div class="line-clamp-2 text-sm font-semibold">{{ row.theme }}</div>
                  <div class="mt-3 text-xs">{{ row.signal_count }} signals · {{ fmtPct(row.average_quality) }}</div>
                </div>
              </div>
            </section>

            <section class="rounded-lg border border-subtle bg-surface">
              <div class="border-b border-subtle px-4 py-3">
                <h2 class="font-display text-lg font-semibold">Source Traces</h2>
              </div>
              <div v-if="!selectedSignal" class="p-4 text-sm text-ink-muted">
                Select a signal to inspect source traces.
              </div>
              <div v-else class="space-y-3 p-4">
                <div class="text-sm font-semibold">{{ selectedSignal.signal }}</div>
                <div v-if="!selectedSignal.source_refs?.length" class="rounded-md border border-danger/30 bg-danger-soft p-3 text-sm text-danger-ink">
                  Missing source trace.
                </div>
                <div
                  v-for="sourceRef in selectedSignal.source_refs"
                  :key="`${selectedSignal.signal_id}-${sourceRef.source_id}-${sourceRef.locator}`"
                  class="rounded-md border p-3"
                  :class="sourceClass(sourceRef)"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="truncate text-sm font-medium">{{ sourceRef.source_title }}</div>
                      <div class="mt-1 text-xs text-ink-muted">
                        {{ sourceRef.source_type }} · {{ sourceRef.locator }} · {{ sourceRef.published_at || "date unknown" }}
                      </div>
                    </div>
                    <span class="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-xs text-ink-muted">
                      {{ fmtPct(sourceRef.confidence) }}
                    </span>
                  </div>
                  <div class="mt-2 line-clamp-3 text-sm text-ink-secondary">
                    {{ sourceRef.excerpt || "No excerpt provided." }}
                  </div>
                </div>
              </div>
            </section>
          </aside>
        </div>

        <div class="grid gap-6 lg:grid-cols-3">
          <section class="rounded-lg border border-subtle bg-surface">
            <div class="border-b border-subtle px-4 py-3">
              <h2 class="font-display text-lg font-semibold">Changed Since Last Week</h2>
            </div>
            <div class="grid gap-3 p-4 text-sm">
              <div>
                <div class="font-medium">New signals</div>
                <div class="mt-1 text-ink-muted">{{ diff.new_signals?.length || 0 }}</div>
              </div>
              <div>
                <div class="font-medium">Fading signals</div>
                <div class="mt-1 text-ink-muted">{{ diff.fading_signals?.length || 0 }}</div>
              </div>
              <div>
                <div class="font-medium">Revised conviction</div>
                <div class="mt-1 text-ink-muted">{{ diff.revised_conviction?.length || 0 }}</div>
              </div>
            </div>
          </section>

          <section class="rounded-lg border border-subtle bg-surface">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <CalendarDays class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-lg font-semibold">Catalyst Preview</h2>
            </div>
            <div v-if="catalysts.length === 0" class="p-4 text-sm text-ink-muted">
              No catalyst calendar rows are available.
            </div>
            <div v-else class="divide-y divide-subtle">
              <div v-for="event in catalysts" :key="`${event.event_date}-${event.event}`" class="p-4 text-sm">
                <div class="font-medium">{{ event.event }}</div>
                <div class="mt-1 text-xs text-ink-muted">
                  {{ event.event_date || "date missing" }} · {{ event.ticker_or_theme }} · {{ event.expected_impact }}
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-lg border border-subtle bg-surface">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <AlertTriangle class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-lg font-semibold">Doctor Issues</h2>
            </div>
            <div v-if="issues.length === 0" class="flex items-center gap-2 p-4 text-sm text-success-ink">
              <CheckCircle2 class="h-4 w-4" />
              No Market Pulse issues.
            </div>
            <div v-else class="space-y-2 p-4">
              <div
                v-for="issue in issues"
                :key="`${issue.type}-${issue.artifact_id || issue.source_ref || issue.message}`"
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
