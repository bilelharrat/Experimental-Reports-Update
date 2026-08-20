<script setup>
import { computed, inject, ref, unref } from "vue";
import { RouterLink } from "vue-router";
import { Newspaper } from "lucide-vue-next";
import { useT } from "../i18n.js";
import { marketRadarItems, radarAge, radarRoute } from "../marketRadar.js";

const t = useT();
const news = inject("workspaceNews", ref([]));
const research = inject("workspaceResearch", ref([]));
const loading = inject("workspaceLoading", ref(false));

const items = computed(() =>
  marketRadarItems(unref(news) || [], unref(research) || [], 24),
);
</script>

<template>
  <div class="mx-auto max-w-3xl px-6 py-8 md:px-8">
    <header class="mb-6">
      <div class="vogue-label">{{ t("nav.section_radar") }}</div>
      <h1 class="mt-1 font-display text-title3 text-ink-primary">{{ t("radar.page_title") }}</h1>
      <p class="mt-1 text-footnote text-ink-muted">{{ t("radar.page_subtitle") }}</p>
    </header>

    <p v-if="loading && !items.length" class="text-callout text-ink-muted">
      {{ t("common.loading") }}
    </p>
    <p
      v-else-if="items.length === 0"
      class="rounded-card bg-surface p-6 text-callout text-ink-muted shadow-card"
    >
      {{ t("toolbar.radar_empty") }}
    </p>
    <div v-else class="space-y-1">
      <RouterLink
        v-for="item in items"
        :key="item.id"
        :to="radarRoute(item)"
        class="source-row focus-ring"
      >
        <Newspaper class="h-4 w-4 shrink-0 text-ink-muted" />
        <span class="min-w-0 flex-1">
          <span class="block truncate font-medium">{{ item.title || t("sidebar.untitled") }}</span>
          <span class="block text-caption1 text-ink-muted">{{ radarAge(item.captured_at, t) }}</span>
        </span>
      </RouterLink>
    </div>
  </div>
</template>
