<script setup>
defineProps({
  rows: { type: Array, default: () => [] },
  title: { type: String, default: "Run Ledger" },
  description: { type: String, default: "" },
  emptyText: { type: String, default: "No run ledger rows yet." },
});

function fmtDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuration(value) {
  const ms = Number(value);
  if (!Number.isFinite(ms) || ms <= 0) return "--";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`;
}

function fmtPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${Math.round(number * 100)}%`;
}

function fmtCost(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "--";
  return `$${number.toFixed(number < 0.01 ? 4 : 2)}`;
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (["done", "complete", "completed", "published", "success"].includes(normalized)) {
    return "bg-success-soft text-success-ink";
  }
  if (["running", "queued"].includes(normalized)) {
    return "bg-accent-soft text-accent-ink";
  }
  if (["error", "failed", "cancelled", "recovered"].includes(normalized)) {
    return "bg-danger-soft text-danger";
  }
  return "bg-surface-muted text-ink-muted";
}

function label(value, fallback = "--") {
  const text = String(value || "").trim();
  return text || fallback;
}

function workspaceLabel(row) {
  return label(row.workspace).replaceAll("_", " ");
}

function jobLabel(row) {
  return label(row.job_kind).replaceAll("_", " ");
}

function targetLabel(row) {
  return (
    row.tracker_id ||
    row.company_id ||
    row.session_id ||
    row.artifact_id ||
    row.period_id ||
    "--"
  );
}
</script>

<template>
  <section class="rounded-card bg-surface shadow-card">
    <div class="flex items-start justify-between gap-3 border-b border-subtle px-4 py-3">
      <div>
        <h3 class="text-sm font-semibold text-ink-primary">{{ title }}</h3>
        <p v-if="description" class="mt-1 text-xs text-ink-muted">
          {{ description }}
        </p>
      </div>
      <span class="rounded bg-surface-muted px-2 py-1 font-mono text-xs text-ink-muted">
        {{ rows.length }}
      </span>
    </div>
    <div class="overflow-x-auto">
      <table class="inset-table">
        <thead>
          <tr>
            <th class="px-3 py-2">Job</th>
            <th class="px-3 py-2">Target</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2">Evidence</th>
            <th class="px-3 py-2">Runtime</th>
            <th class="px-3 py-2">Cost</th>
            <th class="px-3 py-2">Updated</th>
            <th class="px-3 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.ledger_id || row.run_id"
            class="border-t border-subtle align-top"
          >
            <td class="px-3 py-2">
              <div class="font-medium capitalize text-ink-primary">{{ jobLabel(row) }}</div>
              <div class="mt-0.5 text-[11px] text-footnote font-semibold text-ink-muted">
                {{ workspaceLabel(row) }}
              </div>
              <div class="mt-1 max-w-64 truncate font-mono text-[11px] text-ink-muted">
                {{ label(row.run_id) }}
              </div>
            </td>
            <td class="px-3 py-2">
              <div class="font-mono text-xs text-ink-secondary">{{ targetLabel(row) }}</div>
              <div v-if="row.artifact_id" class="mt-1 max-w-52 truncate text-[11px] text-ink-muted">
                {{ row.artifact_id }}
              </div>
            </td>
            <td class="px-3 py-2">
              <span
                :class="[ 'rounded px-1.5 py-0.5 text-caption1', statusClass(row.status), ]"
              >
                {{ label(row.status, "unknown") }}
              </span>
              <div v-if="row.fallback_used" class="mt-1 text-[11px] text-warning-ink">
                fallback
              </div>
            </td>
            <td class="px-3 py-2 text-xs text-ink-secondary">
              <div>{{ row.source_count || 0 }} sources</div>
              <div class="mt-1 text-ink-muted">
                coverage {{ fmtPercent(row.evidence_coverage) }}
              </div>
            </td>
            <td class="px-3 py-2 font-mono text-xs text-ink-secondary">
              {{ fmtDuration(row.duration_ms) }}
            </td>
            <td class="px-3 py-2 font-mono text-xs text-ink-secondary">
              {{ fmtCost(row.estimated_cost_usd) }}
            </td>
            <td class="px-3 py-2 text-xs text-ink-muted">
              {{ fmtDate(row.updated_at || row.created_at) }}
            </td>
            <td class="max-w-sm px-3 py-2 text-xs text-ink-muted">
              <div v-if="row.failure_reason" class="line-clamp-2">
                {{ row.failure_reason }}
              </div>
              <div v-else-if="row.cancellation_reason" class="line-clamp-2">
                {{ row.cancellation_reason }}
              </div>
              <div v-else-if="row.preserved_previous_artifact">
                preserved {{ row.preserved_previous_artifact }}
              </div>
              <span v-else>--</span>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td colspan="8" class="px-3 py-8 text-center text-sm text-ink-muted">
              {{ emptyText }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
