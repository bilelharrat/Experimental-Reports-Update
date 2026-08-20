<script setup>
import { Archive, Check, X } from "lucide-vue-next";

defineProps({
  items: { type: Array, default: () => [] },
  reviewTypes: { type: Array, default: () => [] },
  reviewFilter: { type: String, default: "open" },
  reviewTypeFilter: { type: String, default: "all" },
  reviewRationale: { type: String, default: "" },
});

const emit = defineEmits([
  "update:review-filter",
  "update:review-type-filter",
  "update:review-rationale",
  "update-review",
]);
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Review Queue</h2>
        <p class="text-sm text-ink-muted">
          Triage missing sources, failed jobs, strategy changes, and proposed lessons.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select
          :value="reviewFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:review-filter', $event.target.value)"
        >
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
          <option value="waived">Waived</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
        <select
          :value="reviewTypeFilter"
          class="rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          @change="emit('update:review-type-filter', $event.target.value)"
        >
          <option value="all">All Types</option>
          <option v-for="type in reviewTypes" :key="type" :value="type">{{ type }}</option>
        </select>
        <input
          :value="reviewRationale"
          class="w-64 rounded-md border border-subtle bg-surface px-3 py-2 text-sm focus-ring"
          placeholder="Review rationale"
          @input="emit('update:review-rationale', $event.target.value)"
        />
      </div>
    </div>
    <div class="overflow-x-auto rounded-card bg-surface shadow-card">
      <table class="inset-table">
        <thead class="border-b border-subtle bg-surface-muted text-footnote font-semibold text-ink-muted">
          <tr>
            <th class="px-3 py-2">Item</th>
            <th class="px-3 py-2">Type</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2">Artifact</th>
            <th class="px-3 py-2">Sources</th>
            <th class="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id" class="border-b border-subtle last:border-0">
            <td class="max-w-xl px-3 py-2">
              <div class="font-medium">{{ item.title }}</div>
              <div class="text-xs text-ink-muted">
                {{ item.severity }}
                <span v-if="item.error"> · {{ item.error }}</span>
                <span v-else-if="item.rationale"> · {{ item.rationale }}</span>
              </div>
            </td>
            <td class="px-3 py-2">{{ item.item_type }}</td>
            <td class="px-3 py-2">{{ item.status }}</td>
            <td class="px-3 py-2">{{ item.artifact_id || item.tracker_id || "n/a" }}</td>
            <td class="max-w-sm px-3 py-2 text-xs text-ink-secondary">
              <div v-if="item.source_refs?.length" class="line-clamp-2">
                {{ item.source_refs[0].source_title || item.source_refs[0].source_id || item.source_refs[0].tracker_id || "Source" }}
                <span v-if="item.source_refs[0].locator"> · {{ item.source_refs[0].locator }}</span>
              </div>
              <span v-else class="text-ink-muted">n/a</span>
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="item.status !== 'open'"
                  title="Resolve"
                  @click="emit('update-review', item, 'resolved')"
                >
                  <Check class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="item.status !== 'open'"
                  title="Waive"
                  @click="emit('update-review', item, 'waived')"
                >
                  <Archive class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="item.status !== 'open'"
                  title="Reject"
                  @click="emit('update-review', item, 'rejected')"
                >
                  <X class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="items.length === 0">
            <td colspan="6" class="px-3 py-8 text-center text-sm text-ink-muted">
              No review items.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
