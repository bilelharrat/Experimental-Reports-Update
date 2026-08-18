<script setup>
defineProps({
  summary: { type: Object, default: () => ({}) },
  aggregate: { type: Object, default: null },
  aggregateSignalCount: { type: Number, default: 0 },
  strategyMap: { type: Object, default: null },
  strategyNodeCount: { type: Number, default: 0 },
  strategyEdgeCount: { type: Number, default: 0 },
});

const emit = defineEmits(["open-tab"]);

function trackerTypeCount(summary, type) {
  return summary?.tracker_counts_by_type?.[type] || 0;
}
</script>

<template>
  <section class="space-y-5">
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Trackers</div>
        <div class="mt-2 text-2xl font-semibold">{{ summary.tracker_count || 0 }}</div>
        <div class="mt-1 text-xs text-ink-muted">
          {{ trackerTypeCount(summary, "macro") }} macro ·
          {{ trackerTypeCount(summary, "industry") }} industry ·
          {{ trackerTypeCount(summary, "company") }} company
        </div>
      </div>
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Due Or Stale</div>
        <div class="mt-2 text-2xl font-semibold">
          {{ summary.due_count || 0 }} / {{ summary.stale_count || 0 }}
        </div>
        <div class="mt-1 text-xs text-ink-muted">Due trackers / stale trackers</div>
      </div>
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Review Queue</div>
        <div class="mt-2 text-2xl font-semibold">
          {{ summary.open_review_item_count || 0 }}
        </div>
        <div class="mt-1 text-xs text-ink-muted">
          {{ summary.missing_source_warning_count || 0 }} source warnings
        </div>
      </div>
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Work Products</div>
        <div class="mt-2 text-2xl font-semibold">{{ summary.work_product_count || 0 }}</div>
        <div class="mt-1 text-xs text-ink-muted">
          {{ summary.source_count || 0 }} assigned sources
        </div>
      </div>
    </div>

    <div
      v-if="summary.doctor_error_count || summary.doctor_warning_count || summary.run_ledger_count"
      class="grid gap-3 md:grid-cols-3"
    >
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Data Doctor</div>
        <div class="mt-2 text-sm font-semibold">
          {{ summary.doctor_error_count || 0 }} errors · {{ summary.doctor_warning_count || 0 }} warnings
        </div>
      </div>
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Run Ledger</div>
        <div class="mt-2 text-sm font-semibold">{{ summary.run_ledger_count || 0 }} tracked jobs</div>
      </div>
      <div class="rounded-card bg-surface shadow-card p-4">
        <div class="text-footnote font-semibold text-ink-muted">Failed Runs</div>
        <div class="mt-2 text-sm font-semibold">{{ summary.failed_run_count || 0 }}</div>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <section class="rounded-card bg-surface shadow-card">
        <div class="border-b border-subtle px-4 py-3">
          <h2 class="text-sm font-semibold">Latest Weekly Aggregate</h2>
        </div>
        <div class="p-4 text-sm">
          <div v-if="aggregate" class="space-y-2">
            <div class="font-medium">{{ aggregate.period_id }}</div>
            <div class="text-ink-muted">
              {{ aggregateSignalCount }} ranked signals ·
              {{ aggregate.excluded_tracker_warnings?.length || 0 }} stale warnings
            </div>
            <button
              type="button"
              class="btn-bordered btn-sm mt-2 focus-ring"
              @click="emit('open-tab', 'aggregate')"
            >
              Open aggregate
            </button>
          </div>
          <div v-else class="text-ink-muted">
            No aggregate yet. Run trackers, then create a weekly aggregate.
          </div>
        </div>
      </section>
      <section class="rounded-card bg-surface shadow-card">
        <div class="border-b border-subtle px-4 py-3">
          <h2 class="text-sm font-semibold">Latest Strategy Map</h2>
        </div>
        <div class="p-4 text-sm">
          <div v-if="strategyMap" class="space-y-2">
            <div class="font-medium">{{ strategyMap.period_id }}</div>
            <div class="text-ink-muted">
              {{ strategyNodeCount }} nodes · {{ strategyEdgeCount }} edges
            </div>
            <button
              type="button"
              class="btn-bordered btn-sm mt-2 focus-ring"
              @click="emit('open-tab', 'strategy')"
            >
              Open strategy map
            </button>
          </div>
          <div v-else class="text-ink-muted">
            No strategy map yet. Generate one after the weekly aggregate.
          </div>
        </div>
      </section>
    </div>
  </section>
</template>
