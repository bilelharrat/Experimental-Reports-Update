<script setup>
import { Check, X } from "lucide-vue-next";

defineProps({
  filteredEvaluationRows: { type: Array, default: () => [] },
  trackerMetricRows: { type: Array, default: () => [] },
  knowledgeReviewRows: { type: Array, default: () => [] },
  evaluationTrackerIds: { type: Array, default: () => [] },
  evaluationTrackerFilter: { type: String, default: "all" },
  runReviewScoreFields: { type: Array, default: () => [] },
  runReviewDraft: {
    type: Function,
    default: () => () => ({ review_notes: "" }),
  },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:evaluation-tracker-filter",
  "set-run-review-score",
  "set-run-review-notes",
  "save-run-review",
  "review-knowledge-update",
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
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Evaluation</h2>
        <p class="text-sm text-ink-muted">
          Run metrics, tracker trends, and lesson review state.
        </p>
      </div>
      <select
        :value="evaluationTrackerFilter"
        class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
        @change="emit('update:evaluation-tracker-filter', $event.target.value)"
      >
        <option value="all">All Trackers</option>
        <option v-for="trackerId in evaluationTrackerIds" :key="trackerId" :value="trackerId">
          {{ trackerId }}
        </option>
      </select>
    </div>
    <div class="overflow-x-auto rounded-card bg-surface shadow-card">
      <table class="inset-table">
        <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
            <td class="px-3 py-2">{{ row.avg_reviewer ?? "n/a" }}</td>
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
    <div class="overflow-x-auto rounded-card bg-surface shadow-card">
      <table class="inset-table">
        <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
                Avg: {{ row.reviewer_score ?? "n/a" }}
              </div>
              <div class="mt-2 grid grid-cols-5 gap-1">
                <label
                  v-for="field in runReviewScoreFields"
                  :key="`${row.tracker_id}:${row.run_id}:${field.id}`"
                  class="block text-caption1 text-ink-muted"
                >
                  <span>{{ field.label }}</span>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    step="1"
                    :value="runReviewDraft(row)[field.id]"
                    class="mt-1 w-full rounded border border-subtle bg-surface px-1.5 py-1 text-xs text-ink-primary focus-ring"
                    @input="emit('set-run-review-score', row, field.id, $event.target.value)"
                  />
                </label>
              </div>
              <input
                :value="runReviewDraft(row).review_notes"
                class="mt-2 w-full rounded border border-subtle bg-surface px-2 py-1 text-xs text-ink-primary focus-ring"
                placeholder="Review notes"
                @input="emit('set-run-review-notes', row, $event.target.value)"
              />
              <button
                type="button"
                class="mt-2 inline-flex items-center gap-1 rounded-md border border-subtle px-2 py-1 text-xs font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
                :disabled="busy"
                title="Save run review"
                @click="emit('save-run-review', row)"
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
    <div class="overflow-x-auto rounded-card bg-surface shadow-card">
      <table class="inset-table">
        <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
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
            <td class="px-3 py-2">{{ row.review_status || "open" }}</td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="busy || row.review_status === 'resolved'"
                  title="Accept lesson"
                  @click="emit('review-knowledge-update', row, row, 'resolved')"
                >
                  <Check class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="busy || row.review_status === 'rejected'"
                  title="Reject lesson"
                  @click="emit('review-knowledge-update', row, row, 'rejected')"
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
</template>
