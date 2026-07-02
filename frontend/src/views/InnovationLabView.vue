<script setup>
import {
  Activity,
  ArrowRight,
  FlaskConical,
  ScrollText,
  Table2,
} from "lucide-vue-next";

const labs = [
  {
    title: "Hormuz Source Library",
    status: "Incubated",
    purpose: "Daily source library, Hormuz console, and bilingual V3 appendix workflow.",
    route: { name: "hormuz-library" },
    sourceStores: "data/external/hormuz",
    icon: ScrollText,
  },
  {
    title: "Market Pulse",
    status: "Experiment",
    purpose: "Weekly market-regime and signal heatmap research page.",
    route: { name: "research-page-market-pulse" },
    sourceStores: "stock research tracker outputs",
    icon: Activity,
  },
  {
    title: "Evidence Matrix",
    status: "Experiment",
    purpose: "Claim, contradiction, and source-provenance review surface.",
    route: { name: "research-page-evidence-matrix" },
    sourceStores: "research page evidence artifacts",
    icon: Table2,
  },
  {
    title: "Hypothesis Lab",
    status: "Experiment",
    purpose: "Forward-live and backfill hypothesis generation/evaluation loop.",
    route: { name: "research-page-hypothesis-lab" },
    sourceStores: "hypothesis store",
    icon: FlaskConical,
  },
];
</script>

<template>
  <div class="mx-auto max-w-6xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">Incubated workflows</div>
      <h1 class="mt-2 font-display text-3xl font-bold text-ink-primary">
        Innovation Lab
      </h1>
      <p class="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
        Experimental research tools live here until they are promoted into the
        PRD workspace, retired, or folded into a core workflow. This area stays
        separate from the PRD Source Library, Memo Appendix, and Background
        Documents model.
      </p>
    </header>

    <div class="grid gap-4 md:grid-cols-2">
      <RouterLink
        v-for="lab in labs"
        :key="lab.title"
        :to="lab.route"
        class="group rounded-card border border-subtle bg-surface p-5 shadow-card hover:-translate-y-0.5 hover:shadow-card-raised focus-ring"
      >
        <div class="flex items-start gap-4">
          <div
            class="grid h-10 w-10 shrink-0 place-items-center rounded-subbox bg-accent-soft text-accent-ink"
          >
            <component :is="lab.icon" class="h-5 w-5" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <h2 class="font-display text-lg font-bold text-ink-primary">
                {{ lab.title }}
              </h2>
              <span
                class="rounded-full border border-subtle bg-surface-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted"
              >
                {{ lab.status }}
              </span>
            </div>
            <p class="mt-2 text-sm leading-relaxed text-ink-secondary">
              {{ lab.purpose }}
            </p>
            <div class="mt-3 flex items-center gap-2 text-xs text-ink-muted">
              <span class="font-mono">{{ lab.sourceStores }}</span>
              <ArrowRight class="ml-auto h-4 w-4 text-accent transition group-hover:translate-x-0.5" />
            </div>
          </div>
        </div>
      </RouterLink>
    </div>
  </div>
</template>
