<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  Activity,
  ArrowUpDown,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  Flame,
  FlaskConical,
  Home,
  PanelLeft,
  PanelLeftClose,
  Radar,
  Star,
} from "lucide-vue-next";
import brandLogoUrl from "../assets/berkeley-summit-house.svg";
import { companyBucket, companyStatusLine, sortCompanies } from "../companyLists.js";
import { useT } from "../i18n.js";
import {
  companySort,
  companyViews,
  favoriteCompanyIds,
  setCompanySort,
  sidebarCollapsed,
  toggleFavoriteCompany,
  toggleSidebar,
  toggleTrackedCompany,
  trackedCompanyIds,
} from "../state.js";

const t = useT();

const props = defineProps({
  companies: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const showAllPortfolio = ref(false);
const showAllTopPlayers = ref(false);
const sortMenuOpen = ref(false);
const VISIBLE_ROWS = 8;

function monogram(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function companyCategory(company) {
  return companyStatusLine(company, t);
}

const activeSortLabel = computed(() => {
  if (companySort.value === "za") return t("sidebar.sort_za_short");
  if (companySort.value === "newest") return t("sidebar.sort_newest_short");
  if (companySort.value === "oldest") return t("sidebar.sort_oldest_short");
  if (companySort.value === "views") return t("sidebar.sort_views_short");
  return t("sidebar.sort_az_short");
});

function isFavorite(id) {
  return favoriteCompanyIds.value.has(String(id));
}

function isTracked(id) {
  return trackedCompanyIds.value.has(String(id));
}

const sortOptions = computed(() => [
  { id: "az", label: t("sidebar.sort_az") },
  { id: "za", label: t("sidebar.sort_za") },
  { id: "newest", label: t("sidebar.sort_newest") },
  { id: "oldest", label: t("sidebar.sort_oldest") },
  { id: "views", label: t("sidebar.sort_views") },
]);

function chooseSort(id) {
  setCompanySort(id);
  sortMenuOpen.value = false;
}

function sortedBucket(bucket) {
  return sortCompanies(
    (props.companies || []).filter((company) => companyBucket(company) === bucket),
    {
      sort: companySort.value,
      views: companyViews.value,
      favorites: favoriteCompanyIds.value,
    },
  );
}

const portfolioCompanies = computed(() => sortedBucket("portfolio"));
const topPlayerCompanies = computed(() => sortedBucket("watchlist"));

const visiblePortfolio = computed(() =>
  sidebarCollapsed.value || showAllPortfolio.value
    ? portfolioCompanies.value
    : portfolioCompanies.value.slice(0, VISIBLE_ROWS),
);
const visibleTopPlayers = computed(() =>
  sidebarCollapsed.value || showAllTopPlayers.value
    ? topPlayerCompanies.value
    : topPlayerCompanies.value.slice(0, VISIBLE_ROWS),
);

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
          <div class="vogue-label">{{ t("sidebar.portfolio") }}</div>
          <div class="flex items-center gap-1">
            <span class="mono-data text-caption1 text-ink-subtle">{{
              loading && companies.length === 0 ? "—" : portfolioCompanies.length
            }}</span>
            <div class="relative">
              <button
                type="button"
                class="inline-flex h-6 items-center gap-1 rounded-pill px-1.5 text-caption1 font-medium text-ink-muted hover:bg-fill-tertiary hover:text-ink-primary focus-ring"
                :aria-label="t('sidebar.sort')"
                :title="t('sidebar.sort')"
                :aria-expanded="sortMenuOpen"
                @click="sortMenuOpen = !sortMenuOpen"
              >
                <ArrowUpDown class="h-3.5 w-3.5" />
                <span>{{ activeSortLabel }}</span>
              </button>
              <div
                v-if="sortMenuOpen"
                class="toolbar-menu min-w-[10.5rem]"
                role="menu"
                :aria-label="t('sidebar.sort')"
              >
                <button
                  v-for="option in sortOptions"
                  :key="option.id"
                  type="button"
                  role="menuitemradio"
                  :aria-checked="companySort === option.id"
                  class="toolbar-menu-item"
                  @click="chooseSort(option.id)"
                >
                  <Check v-if="companySort === option.id" class="h-3.5 w-3.5 shrink-0" />
                  <span v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true"></span>
                  {{ option.label }}
                </button>
              </div>
            </div>
          </div>
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
          v-else-if="portfolioCompanies.length === 0 && !sidebarCollapsed"
          class="rounded-subbox px-2.5 py-1.5 text-footnote text-ink-muted"
        >
          {{ t("sidebar.no_companies") }}
        </div>
        <div v-else class="space-y-0.5">
          <div
            v-for="company in visiblePortfolio"
            :key="company.id"
            class="group relative"
          >
            <RouterLink
              :to="{ name: 'research', params: { companyId: company.id } }"
              class="source-row focus-ring"
              :class="sidebarCollapsed ? '' : 'pr-14'"
              :title="company.name"
            >
              <span
                class="mono-data grid h-6 w-6 shrink-0 place-items-center rounded-chip bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
              >
                {{ monogram(company.name) }}
              </span>
              <span v-if="!sidebarCollapsed" class="min-w-0 flex-1">
                <span class="block truncate font-medium">{{ company.name }}</span>
                <span
                  v-if="companyCategory(company)"
                  class="block truncate text-caption1 text-ink-muted"
                >
                  {{ companyCategory(company) }}
                </span>
              </span>
            </RouterLink>
            <div
              v-if="!sidebarCollapsed"
              class="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center gap-0.5"
            >
              <button
                type="button"
                class="icon-btn h-6 w-6"
                :class="
                  isFavorite(company.id)
                    ? ''
                    : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'
                "
                :aria-label="isFavorite(company.id) ? t('sidebar.unfavorite') : t('sidebar.favorite')"
                :title="isFavorite(company.id) ? t('sidebar.unfavorite') : t('sidebar.favorite')"
                :aria-pressed="isFavorite(company.id)"
                @click.stop.prevent="toggleFavoriteCompany(company.id)"
              >
                <Star
                  class="h-3.5 w-3.5"
                  :class="isFavorite(company.id) ? 'text-warning' : ''"
                  :fill="isFavorite(company.id) ? 'currentColor' : 'none'"
                />
              </button>
              <button
                type="button"
                class="icon-btn h-6 w-6"
                :class="
                  isTracked(company.id)
                    ? ''
                    : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'
                "
                :aria-label="isTracked(company.id) ? t('sidebar.untrack_company') : t('sidebar.track_company')"
                :title="isTracked(company.id) ? t('sidebar.untrack_company') : t('sidebar.track_company')"
                :aria-pressed="isTracked(company.id)"
                @click.stop.prevent="toggleTrackedCompany(company.id)"
              >
                <Radar
                  class="h-3.5 w-3.5"
                  :class="isTracked(company.id) ? 'text-accent-ink' : ''"
                />
              </button>
            </div>
          </div>
          <button
            v-if="!sidebarCollapsed && portfolioCompanies.length > VISIBLE_ROWS"
            type="button"
            @click="showAllPortfolio = !showAllPortfolio"
            class="focus-ring ml-1 inline-flex items-center gap-1 rounded-pill px-2 py-1 text-footnote text-ink-muted hover:bg-fill-tertiary hover:text-ink-primary"
          >
            <ChevronDown v-if="showAllPortfolio" class="h-3 w-3" />
            <ChevronRight v-else class="h-3 w-3" />
            <span>
              {{
                showAllPortfolio
                  ? t("sidebar.show_less")
                  : t("sidebar.show_all", { count: portfolioCompanies.length })
              }}
            </span>
          </button>
        </div>
      </section>

      <section class="mt-4">
        <div v-if="!sidebarCollapsed" class="mb-1 flex items-center justify-between px-2.5">
          <div class="vogue-label">{{ t("sidebar.top_players") }}</div>
          <span class="mono-data text-caption1 text-ink-subtle">{{
            loading && companies.length === 0 ? "—" : topPlayerCompanies.length
          }}</span>
        </div>
        <div
          v-if="topPlayerCompanies.length === 0 && !sidebarCollapsed"
          class="rounded-subbox px-2.5 py-1.5 text-footnote text-ink-muted"
        >
          {{ t("companies.empty") }}
        </div>
        <div v-else-if="topPlayerCompanies.length" class="space-y-0.5">
          <div
            v-for="company in visibleTopPlayers"
            :key="company.id"
            class="group relative"
          >
            <RouterLink
              :to="{ name: 'research', params: { companyId: company.id } }"
              class="source-row focus-ring"
              :class="sidebarCollapsed ? '' : 'pr-14'"
              :title="company.name"
            >
              <span
                class="mono-data grid h-6 w-6 shrink-0 place-items-center rounded-chip bg-fill-tertiary text-caption1 font-semibold text-ink-secondary"
              >
                {{ monogram(company.name) }}
              </span>
              <span v-if="!sidebarCollapsed" class="min-w-0 flex-1">
                <span class="block truncate font-medium">{{ company.name }}</span>
                <span
                  v-if="companyCategory(company)"
                  class="block truncate text-caption1 text-ink-muted"
                >
                  {{ companyCategory(company) }}
                </span>
              </span>
            </RouterLink>
            <div
              v-if="!sidebarCollapsed"
              class="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center gap-0.5"
            >
              <button
                type="button"
                class="icon-btn h-6 w-6"
                :class="
                  isFavorite(company.id)
                    ? ''
                    : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'
                "
                :aria-label="isFavorite(company.id) ? t('sidebar.unfavorite') : t('sidebar.favorite')"
                :aria-pressed="isFavorite(company.id)"
                @click.stop.prevent="toggleFavoriteCompany(company.id)"
              >
                <Star
                  class="h-3.5 w-3.5"
                  :class="isFavorite(company.id) ? 'text-warning' : ''"
                  :fill="isFavorite(company.id) ? 'currentColor' : 'none'"
                />
              </button>
              <button
                type="button"
                class="icon-btn h-6 w-6"
                :class="
                  isTracked(company.id)
                    ? ''
                    : 'opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100'
                "
                :aria-label="isTracked(company.id) ? t('sidebar.untrack_company') : t('sidebar.track_company')"
                :aria-pressed="isTracked(company.id)"
                @click.stop.prevent="toggleTrackedCompany(company.id)"
              >
                <Radar
                  class="h-3.5 w-3.5"
                  :class="isTracked(company.id) ? 'text-accent-ink' : ''"
                />
              </button>
            </div>
          </div>
          <button
            v-if="!sidebarCollapsed && topPlayerCompanies.length > VISIBLE_ROWS"
            type="button"
            @click="showAllTopPlayers = !showAllTopPlayers"
            class="focus-ring ml-1 inline-flex items-center gap-1 rounded-pill px-2 py-1 text-footnote text-ink-muted hover:bg-fill-tertiary hover:text-ink-primary"
          >
            <ChevronDown v-if="showAllTopPlayers" class="h-3 w-3" />
            <ChevronRight v-else class="h-3 w-3" />
            <span>
              {{
                showAllTopPlayers
                  ? t("sidebar.show_less")
                  : t("sidebar.show_all", { count: topPlayerCompanies.length })
              }}
            </span>
          </button>
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
