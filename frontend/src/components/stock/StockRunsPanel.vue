<script setup>
import { Check, FileText, GitBranch, Layers, RefreshCw, Square, X } from "lucide-vue-next";
import RunLedgerTable from "../RunLedgerTable.vue";

defineProps({
  runs: { type: Array, default: () => [] },
  runLedger: { type: Array, default: () => [] },
  selectedRun: { type: Object, default: null },
  selectedRunDiff: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "run-aggregate",
  "run-strategy-map",
  "review-knowledge-update",
  "cancel-run",
  "retry-run",
  "select-run",
]);

function fmtDate(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtConfidence(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${Math.round(number * 100)}%`;
}

function canRetryRun(run) {
  return ["error", "cancelled", "recovered"].includes(run.status);
}
</script>

<template>
  <section class="space-y-4">
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
          @click="emit('run-aggregate')"
        >
          <Layers class="h-4 w-4" />
          Run Aggregate
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
          :disabled="busy"
          @click="emit('run-strategy-map')"
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
              <div class="line-clamp-2">{{ run.thesis || "No thesis." }}</div>
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
                    <span class="text-ink-muted">{{ update.review_status || "open" }}</span>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-1 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || update.review_status === 'resolved'"
                      title="Accept knowledge update"
                      @click="emit('review-knowledge-update', run, update, 'resolved')"
                    >
                      <Check class="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      class="rounded-md border border-subtle p-1 hover:bg-surface-muted focus-ring disabled:opacity-50"
                      :disabled="busy || update.review_status === 'rejected'"
                      title="Reject knowledge update"
                      @click="emit('review-knowledge-update', run, update, 'rejected')"
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
                  @click="emit('cancel-run', run)"
                >
                  <Square class="h-4 w-4" />
                </button>
                <button
                  v-if="canRetryRun(run)"
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                  title="Retry run"
                  @click="emit('retry-run', run)"
                >
                  <RefreshCw class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                  title="Show run details"
                  @click="emit('select-run', run.run_id)"
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
    <RunLedgerTable
      :rows="runLedger"
      title="Normalized Run Ledger"
      description="Cross-workspace shape for tracker jobs, aggregate jobs, strategy jobs, and future Memo Tools rows."
      empty-text="No normalized Stock Research run rows yet."
    />
    <div v-if="selectedRun" class="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
      <section class="rounded-lg border border-subtle bg-surface">
        <div class="border-b border-subtle px-4 py-3">
          <h3 class="text-sm font-semibold">Latest Report</h3>
          <div class="mt-1 font-mono text-xs text-ink-muted">{{ selectedRun.run_id }}</div>
        </div>
        <div class="max-h-96 overflow-auto p-4 text-sm">
          <pre class="whitespace-pre-wrap text-xs">{{ selectedRun.report_markdown || selectedRun.thesis || "No report artifact." }}</pre>
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
</template>
