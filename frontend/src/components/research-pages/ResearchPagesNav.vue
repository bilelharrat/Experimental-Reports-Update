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
  <nav class="segmented" aria-label="Research pages">
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      class="segmented-item focus-ring inline-flex items-center gap-1.5"
    >
      <component :is="link.icon" class="h-3.5 w-3.5" />
      {{ link.label }}
    </RouterLink>
  </nav>
</template>
