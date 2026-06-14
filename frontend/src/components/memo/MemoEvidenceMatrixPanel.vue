<script setup>
defineProps({
  evidenceMatrix: { type: Object, default: null },
  evidenceMatrixError: { type: String, default: null },
  evidenceRows: { type: Array, default: () => [] },
  evidenceStatusFilter: { type: String, default: "all" },
});

const emit = defineEmits(["update:evidence-status-filter"]);

function statusClass(status) {
  if (status === "done" || status === "supported") return "bg-success-soft text-success-ink";
  if (status === "error" || status === "contradicted") return "bg-danger/10 text-danger";
  if (status === "mixed" || status === "partial") return "bg-warning-soft text-warning-ink";
  if (status === "missing" || status === "not_started") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function evidenceLabel(item) {
  const locator = item?.locator || item?.filename || item?.file_id;
  return locator || "Source trace";
}

function coverageCount(row, key) {
  return row?.source_coverage?.[key] ?? 0;
}

function topEvidence(row) {
  return listItems(row?.supporting_evidence)[0] || listItems(row?.contradicting_evidence)[0] || null;
}
</script>

<template>
  <section class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h3 class="font-display text-lg font-semibold text-ink-primary">
          Evidence Matrix
        </h3>
        <div v-if="evidenceMatrix" class="mt-1 text-xs text-ink-muted">
          {{ evidenceMatrix.claim_count || 0 }} claims
        </div>
      </div>
      <div class="flex items-center gap-1 rounded-lg border border-subtle bg-surface-muted p-1">
        <button
          v-for="status in ['all', 'mixed', 'contradicted', 'missing']"
          :key="status"
          type="button"
          @click="emit('update:evidence-status-filter', status)"
          :class="[
            'px-2 py-1 rounded-md text-xs focus-ring',
            evidenceStatusFilter === status
              ? 'bg-surface text-ink-primary shadow-sm'
              : 'text-ink-muted hover:text-ink-primary',
          ]"
        >
          {{ status }}
        </button>
      </div>
    </div>
    <div v-if="evidenceMatrixError" class="mt-3 text-sm text-danger">
      {{ evidenceMatrixError }}
    </div>
    <div v-else-if="!evidenceMatrix || evidenceRows.length === 0" class="mt-3 text-sm text-ink-muted">
      No evidence matrix claims yet.
    </div>
    <div v-else class="mt-4 overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead class="text-xs uppercase tracking-wide text-ink-muted">
          <tr class="border-b border-subtle">
            <th class="text-left py-2 pr-3">Claim</th>
            <th class="text-left py-2 pr-3">Status</th>
            <th class="text-left py-2 pr-3">Counts</th>
            <th class="text-left py-2 pr-3">Confidence</th>
            <th class="text-left py-2 pr-3">Top Source</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in evidenceRows"
            :key="row.claim"
            class="border-b border-subtle/70 align-top"
          >
            <td class="py-2 pr-3 text-ink-primary max-w-sm">
              {{ row.claim }}
            </td>
            <td class="py-2 pr-3">
              <span
                :class="[
                  'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                  statusClass(row.status),
                ]"
              >
                {{ row.status }}
              </span>
            </td>
            <td class="py-2 pr-3 text-ink-secondary font-mono">
              +{{ coverageCount(row, 'supporting_count') }}
              / -{{ coverageCount(row, 'contradicting_count') }}
              / ?{{ coverageCount(row, 'missing_count') }}
            </td>
            <td class="py-2 pr-3 text-ink-secondary">
              {{ row.confidence }}
            </td>
            <td class="py-2 pr-3 text-ink-secondary max-w-md">
              <template v-if="topEvidence(row)">
                <div class="text-[11px] text-ink-muted">
                  {{ evidenceLabel(topEvidence(row)) }}
                  <a
                    v-if="topEvidence(row).task_id"
                    :href="`#memo-task-${topEvidence(row).task_id}`"
                    class="ml-2 text-accent hover:underline"
                  >
                    {{ topEvidence(row).task_title || topEvidence(row).task_id }}
                  </a>
                </div>
                <div>{{ topEvidence(row).excerpt }}</div>
              </template>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
