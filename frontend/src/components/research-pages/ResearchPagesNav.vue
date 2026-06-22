<script setup>
import { RouterLink } from "vue-router";
import { Activity, FlaskConical, Table2 } from "lucide-vue-next";

const links = [
  { to: "/research-pages/market-pulse", label: "Market Pulse", icon: Activity },
  { to: "/research-pages/evidence-matrix", label: "Evidence Matrix", icon: Table2 },
  { to: "/research-pages/hypothesis-lab", label: "Hypothesis Lab", icon: FlaskConical },
];
</script>

<template>
  <nav class="flex flex-wrap items-center gap-2" aria-label="Research pages">
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      class="inline-flex items-center gap-2 rounded-md border border-subtle px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-muted focus-ring"
      active-class="border-accent/40 bg-accent-soft text-accent-ink"
    >
      <component :is="link.icon" class="h-4 w-4" />
      {{ link.label }}
    </RouterLink>
  </nav>
</template>
