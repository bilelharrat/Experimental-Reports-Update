<script setup>
import { ArrowRight, FlaskConical } from "lucide-vue-next";

const labs = [
  {
    title: "Daily source reports",
    purpose: "Upload daily reports, ask questions, and generate the bilingual appendix.",
    route: { name: "hormuz-library" },
  },
  {
    title: "Market Pulse",
    purpose: "Weekly market-regime and signal heatmap.",
    route: { name: "research-page-market-pulse" },
  },
  {
    title: "Evidence Matrix",
    purpose: "Claim, contradiction, and source-provenance review.",
    route: { name: "research-page-evidence-matrix" },
  },
  {
    title: "Hypothesis Lab",
    purpose: "Forward-live and backfill hypothesis evaluation.",
    route: { name: "research-page-hypothesis-lab" },
  },
];
</script>

<template>
  <div class="mx-auto max-w-3xl px-6 py-8 md:px-8">
    <header class="mb-5">
      <h1 class="font-display text-title3 text-ink-primary">Innovation Lab</h1>
      <p class="mt-1 max-w-xl text-footnote leading-relaxed text-ink-muted">
        Experiments stay here until they earn a place in the main workspace.
      </p>
    </header>

    <div class="group-card overflow-hidden">
      <RouterLink
        v-for="lab in labs"
        :key="lab.title"
        :to="lab.route"
        class="flex items-center gap-4 px-4 py-3.5 hairline-b last:shadow-none hover:bg-fill-tertiary focus-ring"
      >
        <FlaskConical class="h-4 w-4 shrink-0 text-ink-muted" />
        <div class="min-w-0 flex-1">
          <div class="font-medium text-ink-primary">{{ lab.title }}</div>
          <p class="mt-0.5 text-footnote text-ink-muted">{{ lab.purpose }}</p>
        </div>
        <ArrowRight class="h-4 w-4 shrink-0 text-ink-subtle" />
      </RouterLink>
    </div>
  </div>
</template>
