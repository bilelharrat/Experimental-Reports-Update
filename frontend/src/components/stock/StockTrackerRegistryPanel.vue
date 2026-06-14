<script setup>
import { Archive, Play, Upload } from "lucide-vue-next";

defineProps({
  trackers: { type: Array, default: () => [] },
  selectedTrackerIds: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "toggle-tracker",
  "run-tracker",
  "disable-tracker",
  "import-company-trackers",
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
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Tracker Registry</h2>
        <p class="text-sm text-ink-muted">
          Single-responsibility trackers with isolated source folders and durable memory.
        </p>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium hover:bg-surface-muted focus-ring disabled:opacity-50"
        :disabled="busy"
        @click="emit('import-company-trackers')"
      >
        <Upload class="h-4 w-4" />
        Import Companies
      </button>
    </div>
    <div class="overflow-x-auto rounded-lg border border-subtle bg-surface">
      <table class="min-w-full text-left text-sm">
        <thead class="border-b border-subtle bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
          <tr>
            <th class="w-10 px-3 py-2"></th>
            <th class="px-3 py-2">Tracker</th>
            <th class="px-3 py-2">Type</th>
            <th class="px-3 py-2">Status</th>
            <th class="px-3 py-2">Freshness</th>
            <th class="px-3 py-2">Latest Thesis</th>
            <th class="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tracker in trackers" :key="tracker.id" class="border-b border-subtle last:border-0">
            <td class="px-3 py-2">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-subtle"
                :checked="selectedTrackerIds.includes(tracker.id)"
                @change="emit('toggle-tracker', tracker.id)"
              />
            </td>
            <td class="px-3 py-2">
              <div class="font-medium">{{ tracker.display_name }}</div>
              <div class="text-xs text-ink-muted">{{ tracker.id }}</div>
            </td>
            <td class="px-3 py-2 capitalize">{{ tracker.type }}</td>
            <td class="px-3 py-2">
              <span class="rounded bg-surface-muted px-2 py-1 text-xs">{{ tracker.status }}</span>
            </td>
            <td class="px-3 py-2 text-xs">
              <span :class="tracker.is_stale ? 'text-warning-ink' : 'text-success-ink'">
                {{ tracker.is_stale ? "stale" : "fresh" }}
              </span>
              <div class="text-ink-muted">{{ fmtDate(tracker.freshness_policy?.next_due_run) }}</div>
            </td>
            <td class="max-w-md px-3 py-2 text-ink-secondary">
              <div class="line-clamp-2">{{ tracker.latest_thesis || "No run yet." }}</div>
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="busy || tracker.status !== 'active'"
                  title="Run tracker"
                  @click="emit('run-tracker', tracker.id)"
                >
                  <Play class="h-4 w-4" />
                </button>
                <button
                  type="button"
                  class="rounded-md border border-subtle p-2 hover:bg-surface-muted focus-ring disabled:opacity-50"
                  :disabled="busy || tracker.status !== 'active'"
                  title="Disable tracker"
                  @click="emit('disable-tracker', tracker.id)"
                >
                  <Archive class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="trackers.length === 0">
            <td colspan="7" class="px-3 py-8 text-center text-sm text-ink-muted">
              No trackers yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
