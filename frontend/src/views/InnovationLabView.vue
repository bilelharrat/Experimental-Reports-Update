<script setup>
import { ArrowRight, FlaskConical } from "lucide-vue-next";
import { useT } from "../i18n.js";

const t = useT();

const labs = [
  {
    titleKey: "labs.hormuz_title",
    purposeKey: "labs.hormuz_purpose",
    route: { name: "hormuz-library" },
  },
  {
    titleKey: "labs.pulse_title",
    purposeKey: "labs.pulse_purpose",
    route: { name: "research-page-market-pulse" },
  },
  {
    titleKey: "labs.matrix_title",
    purposeKey: "labs.matrix_purpose",
    route: { name: "research-page-evidence-matrix" },
  },
  {
    titleKey: "labs.hypothesis_title",
    purposeKey: "labs.hypothesis_purpose",
    route: { name: "research-page-hypothesis-lab" },
  },
];
</script>

<template>
  <div class="mx-auto max-w-3xl px-6 py-8 md:px-8">
    <header class="mb-5">
      <h1 class="font-display text-title3 text-ink-primary">{{ t("labs.title") }}</h1>
      <p class="mt-1 max-w-xl text-footnote leading-relaxed text-ink-muted">
        {{ t("labs.subtitle") }}
      </p>
    </header>

    <div class="group-card overflow-hidden">
      <RouterLink
        v-for="lab in labs"
        :key="lab.titleKey"
        :to="lab.route"
        class="flex items-center gap-4 px-4 py-3.5 hairline-b last:shadow-none hover:bg-fill-tertiary focus-ring"
      >
        <FlaskConical class="h-4 w-4 shrink-0 text-ink-muted" />
        <div class="min-w-0 flex-1">
          <div class="font-medium text-ink-primary">{{ t(lab.titleKey) }}</div>
          <p class="mt-0.5 text-footnote text-ink-muted">{{ t(lab.purposeKey) }}</p>
        </div>
        <ArrowRight class="h-4 w-4 shrink-0 text-ink-subtle" />
      </RouterLink>
    </div>
  </div>
</template>
