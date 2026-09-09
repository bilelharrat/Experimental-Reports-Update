<script setup>
import { RouterLink } from "vue-router";
import { Activity, FlaskConical, Table2 } from "lucide-vue-next";
import { useT } from "../../i18n.js";

const t = useT();

const links = [
  { to: "/research-pages/market-pulse", labelKey: "labs.pulse_title", icon: Activity },
  { to: "/research-pages/evidence-matrix", labelKey: "labs.matrix_title", icon: Table2 },
  { to: "/research-pages/hypothesis-lab", labelKey: "labs.hypothesis_title", icon: FlaskConical },
];
</script>

<template>
  <nav class="segmented" :aria-label="t('labs.title')">
    <RouterLink
      v-for="link in links"
      :key="link.to"
      :to="link.to"
      class="segmented-item focus-ring inline-flex items-center gap-1.5"
    >
      <component :is="link.icon" class="h-3.5 w-3.5" />
      {{ t(link.labelKey) }}
    </RouterLink>
  </nav>
</template>
