<script setup>
import { Archive, Check, Pin } from "lucide-vue-next";

defineProps({
  products: { type: Array, default: () => [] },
  productTypes: { type: Array, default: () => [] },
  productStatuses: { type: Array, default: () => [] },
  productTrackerIds: { type: Array, default: () => [] },
  productPeriods: { type: Array, default: () => [] },
  typeFilter: { type: String, default: "all" },
  statusFilter: { type: String, default: "all" },
  trackerFilter: { type: String, default: "all" },
  periodFilter: { type: String, default: "all" },
});

const emit = defineEmits([
  "update:type-filter",
  "update:status-filter",
  "update:tracker-filter",
  "update:period-filter",
  "update-product",
]);

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function fmtConfidence(value) {
  if (value === null || value === undefined || value === "") return "n/a";
  const number = Number(value);
  if (Number.isFinite(number)) return `${Math.round(number * 100)}%`;
  return String(value);
}

function fmtBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "0 B";
  if (number < 1024) return `${number} B`;
  if (number < 1024 * 1024) return `${Math.round(number / 1024)} KB`;
  return `${(number / (1024 * 1024)).toFixed(1)} MB`;
}
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Work Products</h2>
        <p class="text-sm text-ink-muted">
          Cataloged tracker reports, aggregates, strategy maps, and exports.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <select
          :value="typeFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:type-filter', $event.target.value)"
        >
          <option value="all">All Types</option>
          <option v-for="type in productTypes" :key="type" :value="type">{{ type }}</option>
        </select>
        <select
          :value="statusFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:status-filter', $event.target.value)"
        >
          <option value="all">All Statuses</option>
          <option v-for="status in productStatuses" :key="status" :value="status">{{ status }}</option>
        </select>
        <select
          :value="trackerFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:tracker-filter', $event.target.value)"
        >
          <option value="all">All Trackers</option>
          <option v-for="trackerId in productTrackerIds" :key="trackerId" :value="trackerId">{{ trackerId }}</option>
        </select>
        <select
          :value="periodFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:period-filter', $event.target.value)"
        >
          <option value="all">All Periods</option>
          <option v-for="period in productPeriods" :key="period" :value="period">{{ period }}</option>
        </select>
      </div>
    </div>
    <div class="overflow-x-auto rounded-card bg-surface shadow-card">
      <table class="inset-table">
        <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
          <tr>
            <th class="px-3 py-2">Product</th>
            <th class="px-3 py-2">Type</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2">Version</th>
            <th class="px-3 py-2">Coverage</th>
            <th class="px-3 py-2">Exports</th>
            <th class="px-3 py-2">Updated</th>
            <th class="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="product in products" :key="product.artifact_id" class="border-b border-subtle last:border-0">
            <td class="px-3 py-2">
              <div class="font-medium">{{ product.title }}</div>
              <div class="font-mono text-xs text-ink-muted">{{ product.artifact_id }}</div>
              <div v-if="product.period_id || product.tracker_id" class="text-xs text-ink-muted">
                {{ product.tracker_id || product.period_id }}
              </div>
            </td>
            <td class="px-3 py-2">{{ product.artifact_type }}</td>
            <td class="px-3 py-2">{{ product.status }}</td>
            <td class="px-3 py-2">
              <div>v{{ product.version || 1 }}</div>
              <div v-if="product.version_count" class="text-xs text-ink-muted">
                {{ product.version_count }} immutable version{{ product.version_count === 1 ? "" : "s" }}
              </div>
              <div v-if="product.version_id" class="max-w-52 truncate font-mono text-xs text-ink-muted">
                {{ product.version_id }}
              </div>
              <div class="text-xs text-ink-muted">
                {{ product.reviewer || "unassigned" }}
              </div>
              <div v-if="product.latest_review_action" class="text-xs text-ink-muted">
                latest review: {{ product.latest_review_action.action }}
              </div>
              <div v-if="product.version_history?.length" class="text-xs text-ink-muted">
                {{ product.version_history.length }} history events
              </div>
              <div v-if="product.supersedes" class="text-xs text-ink-muted">
                supersedes {{ product.supersedes }}
              </div>
              <div v-if="product.superseded_by" class="text-xs text-ink-muted">
                superseded by {{ product.superseded_by }}
              </div>
            </td>
            <td class="px-3 py-2">
              {{ product.source_trace_count || 0 }} traces · {{ fmtConfidence(product.confidence) }}
            </td>
            <td class="px-3 py-2">
              <div v-if="product.generated_files?.length" class="flex flex-wrap gap-1">
                <span
                  v-for="file in product.generated_files"
                  :key="`${product.artifact_id}:generated:${file.kind}:${file.path}`"
                  class="rounded bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
                  :title="file.sha256 ? `${file.path} · ${file.sha256}` : file.path"
                >
                  {{ file.kind }} · {{ fmtBytes(file.bytes) }}
                </span>
              </div>
              <div v-else-if="product.export_paths" class="flex flex-wrap gap-1">
                <span
                  v-for="(_, name) in product.export_paths"
                  :key="`${product.artifact_id}:${name}`"
                  class="rounded bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
                >
                  {{ name }}
                </span>
              </div>
              <span v-else class="text-xs text-ink-muted">none</span>
            </td>
            <td class="px-3 py-2">{{ fmtDate(product.updated_at) }}</td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                  title="Pin"
                  @click="emit('update-product', product, { pinned: !product.pinned })"
                >
                  <Pin class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                  title="Approve"
                  @click="emit('update-product', product, { status: 'approved', review_state: 'resolved' })"
                >
                  <Check class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring"
                  title="Archive"
                  @click="emit('update-product', product, { archived: true, status: 'archived' })"
                >
                  <Archive class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="products.length === 0">
            <td colspan="8" class="px-3 py-8 text-center text-sm text-ink-muted">
              No work products yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
