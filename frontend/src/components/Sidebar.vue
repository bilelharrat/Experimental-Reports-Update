<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  Activity,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Flame,
  FlaskConical,
  Home,
  PanelLeft,
  PanelLeftClose,
} from "lucide-vue-next";
import brandLogoUrl from "../assets/berkeley-summit-house.svg";
import { useT } from "../i18n.js";
import { sidebarCollapsed, toggleSidebar } from "../state.js";

const t = useT();

const props = defineProps({
  companies: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const expandedBuckets = ref(new Set());

function monogram(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function bucketFor(company) {
  const explicit = String(
    company.investment_bucket || company.bucket || company.pipeline_stage || "",
  ).toLowerCase();
  if (explicit.includes("pipeline") || explicit.includes("review")) return "pipeline";
  if (explicit.includes("watch") || explicit.includes("top")) return "watchlist";
  if (explicit.includes("portfolio")) return "portfolio";
  if (company.company_type === "public" || company.status === "public") return "watchlist";
  return "portfolio";
}

const companyBuckets = computed(() => {
  const buckets = {
    portfolio: [],
    pipeline: [],
    watchlist: [],
  };
  for (const company of props.companies || []) {
    if (!company?.id) continue;
    const key = bucketFor(company);
    buckets[key].push(company);
  }
  for (const key of Object.keys(buckets)) {
    buckets[key].sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }
  return [
    { id: "portfolio", label: t("sidebar.portfolio"), items: buckets.portfolio },
    { id: "pipeline", label: t("sidebar.pipeline"), items: buckets.pipeline },
    { id: "watchlist", label: t("sidebar.top_players"), items: buckets.watchlist },
  ];
});

const populatedBuckets = computed(() =>
  companyBuckets.value.filter((bucket) => bucket.items.length > 0),
);

function visibleCompanies(bucket) {
  if (sidebarCollapsed.value || expandedBuckets.value.has(bucket.id)) return bucket.items;
  return bucket.items.slice(0, 4);
}

function toggleBucket(id) {
  const next = new Set(expandedBuckets.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedBuckets.value = next;
}

function companyCategory(company) {
  const translated = company.translation || {};
  return (
    translated.industry ||
    translated.sector ||
    company.industry ||
    company.sector ||
    t("sidebar.tracked")
  );
}

const collapseLabel = computed(() =>
  sidebarCollapsed.value ? t("sidebar.expand") : t("sidebar.collapse"),
);
</script>

<template>
  <aside
    class="rail-gradient flex w-full shrink-0 flex-col overflow-hidden transition-[width,max-height] duration-200 ease-standard lg:sticky lg:top-0 lg:h-screen lg:max-h-none"
    :class="sidebarCollapsed ? 'max-h-14 lg:w-[56px]' : 'max-h-[26rem] lg:w-[260px]'"
    :data-collapsed="sidebarCollapsed ? 'true' : 'false'"
  >
    <div
      class="flex items-center gap-1"
      :class="sidebarCollapsed ? 'justify-center px-1 py-2' : 'px-2.5 py-2'"
    >
      <RouterLink
        v-if="!sidebarCollapsed"
        to="/"
        class="focus-ring flex min-w-0 flex-1 items-center gap-2 rounded-subbox px-1 py-0.5"
        :title="t('nav.research_center')"
      >
        <img
          :src="brandLogoUrl"
          alt="Berkeley Summit House"
          class="h-7 w-7 shrink-0 object-contain"
        />
        <span class="truncate text-footnote font-semibold text-ink-primary">
          {{ t("nav.research_center") }}
        </span>
      </RouterLink>
      <button
        type="button"
        class="icon-btn shrink-0"
        :aria-label="collapseLabel"
        :title="collapseLabel"
        :aria-expanded="!sidebarCollapsed"
        @click="toggleSidebar"
      >
        <PanelLeft v-if="sidebarCollapsed" class="h-[18px] w-[18px]" />
        <PanelLeftClose v-else class="h-[18px] w-[18px]" />
      </button>
    </div>

    <div
      class="flex-1 overflow-y-auto pb-4"
      :class="sidebarCollapsed ? 'hidden px-1 lg:block' : 'px-2.5'"
    >
      <RouterLink
        :to="{ name: 'home' }"
        class="source-row focus-ring mb-1"
        active-class=""
        :title="t('nav.home')"
      >
        <Home class="h-[18px] w-[18px] shrink-0" />
        <span v-if="!sidebarCollapsed">{{ t("nav.home") }}</span>
      </RouterLink>

      <section class="mt-4">
        <div v-if="!sidebarCollapsed" class="mb-1 flex items-center justify-between px-2.5">
          <div class="vogue-label">{{ t("sidebar.companies") }}</div>
          <span class="mono-data text-caption1 text-ink-subtle">{{
            loading && companies.length === 0 ? "—" : companies.length
          }}</span>
        </div>
        <div
          v-if="loading && companies.length === 0 && !sidebarCollapsed"
          class="px-2.5 py-1.5 text-callout text-ink-muted"
        >
          {{ t("common.loading") }}
        </div>
        <div v-else-if="error && !sidebarCollapsed" class="px-2.5 py-1.5 text-callout text-danger">
          {{ t("sidebar.load_error") }}
        </div>
        <div
          v-else-if="populatedBuckets.length === 0 && !sidebarCollapsed"
          class="rounded-subbox px-2.5 py-1.5 text-footnote text-ink-muted"
        >
          {{ t("sidebar.no_companies") }}
        </div>
        <div v-else class="space-y-3">
          <div v-for="bucket in populatedBuckets" :key="bucket.id">
            <div v-if="!sidebarCollapsed" class="mb-0.5 flex items-center justify-between px-2.5">
              <div class="text-footnote font-semibold text-ink-secondary">{{ bucket.label }}</div>
              <span class="mono-data text-caption1 text-ink-subtle">
                {{ bucket.items.length }}
              </span>
            </div>
            <div class="space-y-0.5">
              <RouterLink
                v-for="company in visibleCompanies(bucket)"
                :key="company.id"
                :to="{ name: 'research', params: { companyId: company.id } }"
                class="source-row focus-ring"
                :title="company.name"
              >
                <span
                  class="mono-data grid h-6 w-6 shrink-0 place-items-center rounded-chip bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
                >
                  {{ monogram(company.name) }}
                </span>
                <span v-if="!sidebarCollapsed" class="min-w-0 flex-1">
                  <span class="block truncate font-medium">{{ company.name }}</span>
                  <span class="block truncate text-caption1 text-ink-muted">
                    {{ companyCategory(company) }}
                  </span>
                </span>
              </RouterLink>
              <button
                v-if="!sidebarCollapsed && bucket.items.length > 4"
                type="button"
                @click="toggleBucket(bucket.id)"
                class="focus-ring ml-1 inline-flex items-center gap-1 rounded-pill px-2 py-1 text-footnote text-ink-muted hover:bg-fill-tertiary hover:text-ink-primary"
              >
                <ChevronDown v-if="expandedBuckets.has(bucket.id)" class="h-3 w-3" />
                <ChevronRight v-else class="h-3 w-3" />
                <span>
                  {{
                    expandedBuckets.has(bucket.id)
                      ? t("sidebar.show_less")
                      : t("sidebar.show_all", { count: bucket.items.length })
                  }}
                </span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-4 space-y-0.5">
        <RouterLink
          :to="{ name: 'weekly-summary' }"
          class="source-row focus-ring"
          :title="t('app.weekly_summary')"
        >
          <Flame class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("app.weekly_summary") }}</span>
        </RouterLink>
        <RouterLink
          :to="{ name: 'stock-research' }"
          class="source-row focus-ring"
          :title="t('sidebar.stock')"
        >
          <Activity class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("sidebar.stock") }}</span>
        </RouterLink>
        <RouterLink
          :to="{ name: 'trader-stats' }"
          class="source-row focus-ring"
          :title="t('app.stats')"
        >
          <BarChart3 class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("app.stats") }}</span>
        </RouterLink>
      </section>

      <section class="mt-5">
        <RouterLink
          :to="{ name: 'innovation-lab' }"
          class="source-row focus-ring text-ink-muted"
          :title="t('sidebar.innovation_lab')"
        >
          <FlaskConical class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("sidebar.innovation_lab") }}</span>
        </RouterLink>
      </section>
    </div>
  </aside>
</template>
