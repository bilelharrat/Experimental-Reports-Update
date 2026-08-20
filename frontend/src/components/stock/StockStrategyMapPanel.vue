<script setup>
import { GitBranch, RefreshCw, Square } from "lucide-vue-next";

defineProps({
  strategyMap: { type: Object, default: null },
  strategyNodes: { type: Array, default: () => [] },
  strategySourceRows: { type: Array, default: () => [] },
  strategyContradictions: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "run-strategy-map",
  "retry-strategy-map",
  "cancel-strategy-map",
]);

function firstTrace(item) {
  return item?.source_traces?.[0] || null;
}
</script>

<template>
  <section class="space-y-4">
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
          class="btn-filled focus-ring"
          :disabled="busy"
          @click="emit('run-strategy-map')"
        >
          <GitBranch class="h-4 w-4" />
          Run Strategy Map
        </button>
        <button
          v-if="strategyMap"
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy"
          @click="emit('retry-strategy-map')"
        >
          <RefreshCw class="h-4 w-4" />
          Retry
        </button>
        <button
          v-if="strategyMap"
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy"
          @click="emit('cancel-strategy-map')"
        >
          <Square class="h-4 w-4" />
          Cancel
        </button>
      </div>
    </div>
    <div v-if="strategyMap" class="space-y-4">
      <div class="overflow-x-auto rounded-card bg-surface shadow-card">
        <table class="inset-table">
          <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
      <div class="overflow-x-auto rounded-card bg-surface shadow-card">
        <div class="border-b border-subtle px-4 py-3">
          <h3 class="text-sm font-semibold">Source Inspector</h3>
        </div>
        <table class="inset-table">
          <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
              <td class="px-3 py-2">{{ row.trace.source_title || row.trace.source_id || "Source" }}</td>
              <td class="px-3 py-2">{{ row.trace.locator || "n/a" }}</td>
              <td class="max-w-xl px-3 py-2 text-ink-secondary">
                <div class="line-clamp-2">{{ row.trace.excerpt || "No excerpt." }}</div>
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
      <div class="rounded-card bg-surface shadow-card p-4">
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
      <div class="rounded-card bg-surface shadow-card p-4">
        <h3 class="text-sm font-semibold">Unresolved Contradictions</h3>
        <div v-if="strategyContradictions.length" class="mt-3 space-y-2">
          <div
            v-for="item in strategyContradictions"
            :key="item.id || item.description"
            class="rounded border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning-ink"
          >
            <div>{{ item.description || item.claim || "Contradiction" }}</div>
            <div v-if="item.source_traces?.length" class="mt-1 text-xs">
              {{ item.source_traces[0].source_title }} · {{ item.source_traces[0].locator }}
            </div>
          </div>
        </div>
        <div v-else class="mt-3 text-sm text-ink-muted">No unresolved contradictions.</div>
      </div>
    </div>
    <div v-else class="rounded-card bg-surface shadow-card p-6 text-sm text-ink-muted">
      No strategy map yet.
    </div>
  </section>
</template>
