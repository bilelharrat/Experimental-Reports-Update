<script setup>
import { Layers, RefreshCw, Square } from "lucide-vue-next";

defineProps({
  aggregate: { type: Object, default: null },
  aggregateWarnings: { type: Array, default: () => [] },
  aggregateModuleRows: { type: Array, default: () => [] },
  filteredAggregateSignals: { type: Array, default: () => [] },
  aggregateModuleFilter: { type: String, default: "all" },
  aggregateDirectionFilter: { type: String, default: "all" },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:aggregate-module-filter",
  "update:aggregate-direction-filter",
  "run-aggregate",
  "retry-aggregate",
  "cancel-aggregate",
]);

function firstTrace(item) {
  return item?.source_traces?.[0] || null;
}

function qualityLabel(signal) {
  const score = Number(signal?.source_quality_score);
  if (Number.isNaN(score)) return "n/a";
  return score.toFixed(2);
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Weekly Aggregate</h2>
        <p class="text-sm text-ink-muted">
          Consumes structured tracker outputs and selected source traces only.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <select
          :value="aggregateModuleFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:aggregate-module-filter', $event.target.value)"
        >
          <option value="all">All Modules</option>
          <option value="macro">Macro</option>
          <option value="industry">Industry</option>
          <option value="company">Company</option>
          <option value="cross_tracker">Cross Tracker</option>
          <option value="watchlist">Watchlist</option>
        </select>
        <select
          :value="aggregateDirectionFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:aggregate-direction-filter', $event.target.value)"
        >
          <option value="all">All Directions</option>
          <option value="positive">Positive</option>
          <option value="negative">Negative</option>
          <option value="neutral">Neutral</option>
          <option value="watch">Watch</option>
        </select>
        <button
          type="button"
          class="btn-filled focus-ring"
          :disabled="busy"
          @click="emit('run-aggregate')"
        >
          <Layers class="h-4 w-4" />
          Run Aggregate
        </button>
        <button
          v-if="aggregate"
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy"
          @click="emit('retry-aggregate')"
        >
          <RefreshCw class="h-4 w-4" />
          Retry
        </button>
        <button
          v-if="aggregate"
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy"
          @click="emit('cancel-aggregate')"
        >
          <Square class="h-4 w-4" />
          Cancel
        </button>
      </div>
    </div>
    <div v-if="aggregate" class="space-y-4">
      <div class="rounded-card bg-surface shadow-card p-4 text-sm">
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
            <div class="mt-1 text-ink-primary">{{ warning.tracker_id || "tracker" }} · {{ warning.title }}</div>
          </div>
        </div>
      </div>
      <div class="overflow-x-auto rounded-card bg-surface shadow-card">
        <table class="inset-table">
          <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
              <td class="px-3 py-2">{{ row.tracker_id || "n/a" }}</td>
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
      <div class="overflow-x-auto rounded-card bg-surface shadow-card">
        <table class="inset-table">
          <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
            <tr>
              <th class="px-3 py-2">Signal</th>
              <th class="px-3 py-2">Tracker</th>
              <th class="px-3 py-2">Direction</th>
              <th class="px-3 py-2">Quality</th>
              <th class="px-3 py-2">Sources</th>
              <th class="px-3 py-2">Trace Preview</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="signal in filteredAggregateSignals" :key="`${signal.source_tracker_id}:${signal.id}`" class="border-b border-subtle last:border-0">
              <td class="max-w-xl px-3 py-2">{{ signal.observation }}</td>
              <td class="px-3 py-2">{{ signal.source_tracker_id }}</td>
              <td class="px-3 py-2">{{ signal.direction }}</td>
              <td class="min-w-48 px-3 py-2">
                <div class="font-medium">{{ qualityLabel(signal) }}</div>
                <div class="mt-1 text-xs text-ink-muted">
                  {{ signal.source_quality_reason || signal.source_priority || "n/a" }}
                </div>
              </td>
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
              <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
                No aggregate signals yet.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <pre class="max-h-96 overflow-auto rounded-card bg-surface shadow-card p-4 text-xs whitespace-pre-wrap">{{ aggregate.markdown }}</pre>
      <div v-if="aggregate.html_blocks?.length" class="rounded-card bg-surface shadow-card p-4">
        <h3 class="text-sm font-semibold">HTML-Ready Blocks</h3>
        <div class="mt-3 space-y-2 text-sm text-ink-secondary">
          <div
            v-for="(block, index) in aggregate.html_blocks"
            :key="index"
            class="rounded border border-subtle bg-surface-muted p-3"
          >
            <div class="text-xs uppercase text-ink-muted">{{ block.kind || "block" }}</div>
            <div class="mt-1 whitespace-pre-wrap">{{ block.body || block.markdown || "No body." }}</div>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="rounded-card bg-surface shadow-card p-6 text-sm text-ink-muted">
      No weekly aggregate yet.
    </div>
  </section>
</template>
