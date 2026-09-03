<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  ArrowUpDown,
  Check,
  Flame,
  Gauge,
  Home,
  Newspaper,
  PanelLeft,
  PanelLeftClose,
  Radar,
} from "lucide-vue-next";
import brandLogoUrl from "../assets/berkeley-summit-house.svg";
import { companyStatusLine, sortCompanies } from "../companyLists.js";
import { companyInitials } from "../formatters.js";
import { useT } from "../i18n.js";
import CompanyFollowButton from "./CompanyFollowButton.vue";
import {
  companySort,
  companyViews,
  setCompanySort,
  sidebarCollapsed,
  toggleSidebar,
  trackedCompanyIds,
} from "../state.js";

const t = useT();

const props = defineProps({
  companies: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const sortMenuOpen = ref(false);

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

function chooseSort(id) {
  setCompanySort(id);
  sortMenuOpen.value = false;
}

const sortOptions = computed(() => [
  { id: "az", label: t("sidebar.sort_az") },
  { id: "za", label: t("sidebar.sort_za") },
  { id: "newest", label: t("sidebar.sort_newest") },
  { id: "oldest", label: t("sidebar.sort_oldest") },
  { id: "views", label: t("sidebar.sort_views") },
]);

const listedCompanies = computed(() =>
  sortCompanies(props.companies || [], {
    sort: companySort.value,
    views: companyViews.value,
    favorites: trackedCompanyIds.value,
  }),
);

const trackedCount = computed(
  () =>
    (props.companies || []).filter((company) =>
      trackedCompanyIds.value.has(String(company.id)),
    ).length,
);

const collapseLabel = computed(() =>
  sidebarCollapsed.value ? t("sidebar.expand") : t("sidebar.collapse"),
);
</script>

<template>
  <aside
    class="rail-gradient flex w-full shrink-0 flex-col overflow-hidden transition-[width,max-height] duration-300 ease-standard lg:sticky lg:top-0 lg:h-screen lg:max-h-none"
    :class="sidebarCollapsed ? 'max-h-14 lg:w-[56px]' : 'max-h-[26rem] lg:w-[260px]'"
    :data-collapsed="sidebarCollapsed ? 'true' : 'false'"
  >
    <div
      class="flex items-center gap-1"
      :class="sidebarCollapsed ? 'justify-center px-1 py-2' : 'px-2.5 py-2.5'"
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
          class="h-5 w-auto max-w-[84px] shrink-0 object-contain object-left"
        />
        <span class="brand-mark min-w-0">
          <span class="brand-mark-depth" aria-hidden="true">{{ t("nav.brand_product") }}</span>
          <span class="brand-mark-fill">{{ t("nav.brand_product") }}</span>
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
      class="flex min-h-0 flex-1 flex-col overflow-y-auto lg:overflow-hidden"
      :class="sidebarCollapsed ? 'hidden px-1 lg:flex' : 'px-2.5'"
    >
      <div class="shrink-0 space-y-0.5 border-b border-subtle/60 pb-2">
        <RouterLink
          :to="{ name: 'home' }"
          class="source-row focus-ring"
          active-class=""
          :title="t('nav.home')"
        >
          <Home class="h-[18px] w-[18px] shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("nav.home") }}</span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'news-desk' }"
          class="source-row focus-ring"
          active-class=""
          :title="t('nav.news')"
        >
          <Newspaper class="h-[18px] w-[18px] shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("nav.news") }}</span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'tracking' }"
          class="source-row focus-ring"
          active-class=""
          :title="t('sidebar.tracking')"
        >
          <Gauge class="h-[18px] w-[18px] shrink-0" />
          <span v-if="!sidebarCollapsed" class="min-w-0 flex-1 truncate">{{
            t("sidebar.tracking")
          }}</span>
          <span
            v-if="!sidebarCollapsed && trackedCount > 0"
            class="mono-data text-caption1 text-ink-subtle"
          >
            {{ trackedCount }}
          </span>
        </RouterLink>
      </div>

      <div class="flex min-h-0 flex-1 flex-col overflow-hidden pb-2 pt-2">
        <section class="flex min-h-0 flex-1 flex-col">
          <div v-if="!sidebarCollapsed" class="mb-1 flex shrink-0 items-center justify-between px-2.5">
            <div class="vogue-label">{{ t("sidebar.companies") }}</div>
            <div class="flex items-center gap-1">
              <span class="mono-data text-caption1 text-ink-subtle">{{
                loading && companies.length === 0 ? "—" : listedCompanies.length
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
            v-else-if="listedCompanies.length === 0 && !sidebarCollapsed"
            class="rounded-subbox px-2.5 py-1.5 text-footnote text-ink-muted"
          >
            {{ t("sidebar.no_companies") }}
          </div>
          <div v-else class="min-h-0 flex-1 space-y-0.5 overflow-y-auto">
            <div
              v-for="company in listedCompanies"
              :key="company.id"
              class="group relative"
            >
              <RouterLink
                :to="{ name: 'research', params: { companyId: company.id } }"
                class="source-row company-source-row focus-ring"
                :class="sidebarCollapsed ? 'company-rail-link' : 'gap-2'"
                :title="company.name"
              >
                <span
                  v-if="sidebarCollapsed"
                  class="company-rail-mark"
                  aria-hidden="true"
                >
                  {{ companyInitials(company) }}
                </span>
                <template v-else>
                  <CompanyFollowButton :company-id="company.id" />
                  <span class="min-w-0 flex-1">
                    <span class="block truncate font-medium">{{ company.name }}</span>
                    <span
                      v-if="companyCategory(company)"
                      class="block truncate text-caption1 text-ink-muted"
                    >
                      {{ companyCategory(company) }}
                    </span>
                  </span>
                </template>
              </RouterLink>
            </div>
          </div>
        </section>
      </div>

      <section class="shrink-0 space-y-0.5 border-t border-subtle/60 pt-2 pb-3">
        <div v-if="!sidebarCollapsed" class="mb-1 px-2.5">
          <div class="vogue-label">{{ t("sidebar.markets") }}</div>
        </div>
        <RouterLink
          :to="{ name: 'market-radar' }"
          class="source-row focus-ring"
          :title="t('sidebar.markets_radar')"
        >
          <Radar class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("sidebar.markets_radar") }}</span>
        </RouterLink>
        <RouterLink
          :to="{ name: 'weekly-summary' }"
          class="source-row focus-ring"
          :title="t('sidebar.markets_pulse')"
        >
          <Flame class="h-4 w-4 shrink-0" />
          <span v-if="!sidebarCollapsed">{{ t("sidebar.markets_pulse") }}</span>
        </RouterLink>
      </section>
    </div>
  </aside>
</template>
