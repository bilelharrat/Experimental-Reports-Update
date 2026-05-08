<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { FileText, Loader2, Home } from "lucide-vue-next";

const props = defineProps({
  reports: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const grouped = computed(() => props.reports);
</script>

<template>
  <aside
    class="w-72 shrink-0 border-r border-subtle bg-surface flex flex-col h-screen sticky top-0"
  >
    <div class="px-5 py-5 border-b border-subtle">
      <RouterLink
        to="/"
        class="flex items-center gap-2 text-ink-primary font-display text-lg font-semibold focus-ring rounded"
      >
        <span
          class="h-8 w-8 rounded-lg bg-accent text-white grid place-items-center font-display font-bold"
          >BSH</span
        >
        <span>Research Center</span>
      </RouterLink>
    </div>

    <RouterLink
      to="/"
      class="mx-3 mt-3 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-ink-secondary hover:bg-surface-muted focus-ring"
    >
      <Home class="h-4 w-4" />
      <span>Home</span>
    </RouterLink>

    <div class="px-5 pt-5 pb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
      Reports
    </div>

    <div class="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
      <div v-if="loading" class="px-3 py-2 text-sm text-ink-muted flex items-center gap-2">
        <Loader2 class="h-4 w-4 animate-spin" /> Loading…
      </div>
      <div v-else-if="error" class="px-3 py-2 text-sm text-danger">
        {{ error }}
      </div>
      <div v-else-if="grouped.length === 0" class="px-3 py-2 text-sm text-ink-muted">
        No reports yet. Search a company to get started.
      </div>
      <RouterLink
        v-for="r in grouped"
        :key="r.id"
        :to="{ name: 'research', params: { companyId: r.company_id }, query: { report: r.id } }"
        class="block px-3 py-2 rounded-lg hover:bg-surface-muted focus-ring"
      >
        <div class="flex items-start gap-2">
          <FileText class="h-4 w-4 mt-0.5 text-ink-muted shrink-0" />
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-ink-primary truncate">
              {{ r.company_name || r.company_id }}
            </div>
            <div class="text-xs text-ink-muted truncate">
              {{ r.report_type }} · {{ r.audience }}
            </div>
            <div class="mt-1 flex items-center gap-2 text-xs">
              <span
                v-if="r.status === 'complete'"
                class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink"
                >Done</span
              >
              <span
                v-else-if="r.status === 'running'"
                class="px-1.5 py-0.5 rounded bg-warning-soft text-warning-ink"
                >{{ r.progress }}%</span
              >
              <span
                v-else
                class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-muted"
                >{{ r.status }}</span
              >
            </div>
          </div>
        </div>
      </RouterLink>
    </div>
  </aside>
</template>
