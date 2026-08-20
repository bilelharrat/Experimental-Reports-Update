<script setup>
import { computed, inject, ref, unref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { Newspaper, Radar, TrendingDown, TrendingUp } from "lucide-vue-next";
import { useT } from "../i18n.js";
import { latestNewsFor, priceSignal, relatedNews, sortCompanies } from "../companyLists.js";
import { radarAge } from "../marketRadar.js";
import {
  companySort,
  companyViews,
  favoriteCompanyIds,
  toggleTrackedCompany,
  trackedCompanyIds,
} from "../state.js";

const t = useT();
const router = useRouter();
const companies = inject("workspaceCompanies", ref([]));
const news = inject("workspaceNews", ref([]));
const loading = inject("workspaceLoading", ref(false));

const trackedCompanies = computed(() =>
  sortCompanies(
    (unref(companies) || []).filter((company) =>
      trackedCompanyIds.value.has(String(company.id)),
    ),
    {
      sort: companySort.value,
      views: companyViews.value,
      favorites: favoriteCompanyIds.value,
    },
  ),
);

const boardNews = computed(() => relatedNews(news.value, trackedCompanies.value, 8));

function openCompany(company) {
  router.push({ name: "research", params: { companyId: company.id } });
}

function signalLabel(company) {
  const signal = priceSignal(company);
  if (signal.dir === "up") {
    return t("tracking.signal_up", { value: `+${signal.value.toFixed(1)}%` });
  }
  if (signal.dir === "down") {
    return t("tracking.signal_down", { value: `${signal.value.toFixed(1)}%` });
  }
  return t("tracking.signal_flat");
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-8 md:px-8">
    <header class="mb-6">
      <div class="vogue-label">{{ t("nav.section_tracking") }}</div>
      <h1 class="mt-1 font-display text-title3 text-ink-primary">{{ t("tracking.title") }}</h1>
      <p class="mt-1 max-w-xl text-footnote text-ink-muted">{{ t("tracking.subtitle") }}</p>
    </header>

    <p v-if="loading && !companies.length" class="text-callout text-ink-muted">
      {{ t("common.loading") }}
    </p>
    <p
      v-else-if="trackedCompanies.length === 0"
      class="rounded-card bg-surface p-6 text-callout text-ink-muted shadow-card"
    >
      {{ t("tracking.empty") }}
    </p>
    <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <article
        v-for="company in trackedCompanies"
        :key="company.id"
        class="glass-card flex min-h-[12rem] flex-col rounded-glass p-5"
      >
        <div class="flex items-start justify-between gap-3">
          <button
            type="button"
            class="min-w-0 text-left focus-ring rounded-subbox"
            @click="openCompany(company)"
          >
            <h2 class="text-headline font-semibold text-ink-primary">{{ company.name }}</h2>
            <p class="mt-1 text-footnote text-ink-muted">
              {{ t("tracking.status") }} ·
              {{ company.status || company.company_type || t("companies.status_pending") }}
            </p>
          </button>
          <button
            type="button"
            class="icon-btn shrink-0 text-accent-ink"
            :aria-label="t('sidebar.untrack_company')"
            @click="toggleTrackedCompany(company.id)"
          >
            <Radar class="h-4 w-4" />
          </button>
        </div>
        <p class="mt-4 line-clamp-3 text-footnote leading-relaxed text-ink-secondary">
          <span class="font-medium text-ink-primary">{{ t("tracking.news") }} · </span>
          {{ latestNewsFor(unref(news) || [], company)?.title || t("sidebar.no_tracked_news") }}
        </p>
        <div
          class="mt-auto flex items-center gap-1.5 pt-4 text-footnote font-medium"
          :class="
            priceSignal(company).dir === 'up'
              ? 'text-success-ink'
              : priceSignal(company).dir === 'down'
                ? 'text-danger'
                : 'text-ink-muted'
          "
        >
          <TrendingUp v-if="priceSignal(company).dir === 'up'" class="h-4 w-4" />
          <TrendingDown v-else-if="priceSignal(company).dir === 'down'" class="h-4 w-4" />
          {{ t("tracking.signal") }} · {{ signalLabel(company) }}
        </div>
      </article>
    </div>

    <section v-if="trackedCompanies.length" class="mt-10">
      <div class="vogue-label mb-3">{{ t("tracking.news_board") }}</div>
      <p v-if="boardNews.length === 0" class="text-footnote text-ink-muted">
        {{ t("sidebar.no_tracked_news") }}
      </p>
      <div v-else class="space-y-1">
        <RouterLink
          v-for="item in boardNews"
          :key="item.id"
          :to="{ name: 'external-news', params: { id: item.id } }"
          class="source-row focus-ring"
        >
          <Newspaper class="h-4 w-4 shrink-0 text-ink-muted" />
          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium">{{ item.title || t("sidebar.untitled") }}</span>
            <span class="block text-caption1 text-ink-muted">{{ radarAge(item.captured_at, t) }}</span>
          </span>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
