<script setup>
import { computed, h, inject, nextTick, onBeforeUnmount, onMounted, ref, unref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  ArrowUpDown,
  Building2,
  Check,
  ChevronDown,
  ChevronsUpDown,
  Upload,
  Sparkle,
  Sparkles,
  FileText,
  Gauge,
  Home,
  LogIn,
  LogOut,
  Newspaper,
  PanelLeft,
  PanelLeftClose,
  Search,
  Settings,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { companyStatusLine, sortCompanies } from "../companyLists.js";
import { companyHeadlines, companyReports, useTickerNewsFeed } from "../companyPages.js";
import { useT } from "../i18n.js";
import {
  isAnonDev,
  isSignedIn,
  sessionEmail,
  sessionInitials,
  sessionName,
  signInRoute,
  signOut,
} from "../auth.js";
import { useMediaQuery } from "../chrome.js";
import { prefersReducedMotion, useGlider } from "../glassMotion.js";
import AiMark from "./AiMark.vue";
import BrandMark from "./BrandMark.vue";
import CompanyFollowButton from "./CompanyFollowButton.vue";
import Monogram from "./Monogram.vue";
import PulseECGIcon from "./PulseECGIcon.vue";

import {
  ALL_SECTORS,
  companySort,
  deskDiffsOnly,
  deskSector,
  isCompanyModified,
  setDeskSector,
  toggleDeskDiffsOnly,
  companyViews,
  setCompanySort,
  sidebarCollapsed,
  toggleSidebar,
  trackedCompanyIds,
} from "../state.js";

const t = useT();

const openReportCustomizer = inject("openReportCustomizer", () => {});
// The deck drop moved here with the rest of the directory column; the modal
// it opens is mounted once, at app level.
const openDeckIntake = inject("openDeckIntake", () => {});
const deckDragOver = ref(false);

const DECK_SUFFIXES = [".pdf", ".pptx", ".ppt"];

function isDeck(file) {
  const name = String(file?.name || "").toLowerCase();
  return DECK_SUFFIXES.some((suffix) => name.endsWith(suffix));
}

function onDeckDragOver(event) {
  // only light up for a file drag, not for text or a dragged link
  if (!Array.from(event.dataTransfer?.types || []).includes("Files")) return;
  deckDragOver.value = true;
}

function onDeckDragLeave() {
  deckDragOver.value = false;
}

function onDeckDrop(event) {
  deckDragOver.value = false;
  const file = event.dataTransfer?.files?.[0];
  if (file && isDeck(file)) openDeckIntake(file);
}


function onGenerateReport() {
  openReportCustomizer();
  if (props.mobileOpen) emit("close");
}

const props = defineProps({
  companies: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
  // Below lg the sidebar is an off-canvas drawer the toolbar opens.
  mobileOpen: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "navigate"]);

const router = useRouter();
const route = useRoute();

const isDesktop = useMediaQuery("(min-width: 1024px)");
// The icon rail is a desktop affordance; the mobile drawer always shows labels.
const collapsed = computed(() => sidebarCollapsed.value && isDesktop.value);

// chart.line.uptrend.xyaxis, the Mac Market Radar symbol.
const MarketIcon = (iconProps) =>
  h(
    "svg",
    {
      width: iconProps.size || 18,
      height: iconProps.size || 18,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 1.75,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
      "aria-hidden": "true",
    },
    [
      h("path", { d: "M3 3v16a2 2 0 0 0 2 2h16" }),
      h("path", { d: "m7 15 3-3 2 3 7-7" }),
      h("path", { d: "M15 8h4v4" }),
    ],
  );
MarketIcon.props = ["size"];

const trackedCount = computed(
  () =>
    (props.companies || []).filter((company) =>
      trackedCompanyIds.value.has(String(company.id)),
    ).length,
);

const navItems = computed(() => [
  { id: "home", to: { name: "home" }, label: t("nav.home"), icon: Home },
  { id: "reports", to: { name: "reports" }, label: t("sidebar.reports"), icon: FileText },
  { id: "research-desk", to: { name: "research-desk" }, label: t("sidebar.research_desk"), icon: Building2 },
  { id: "news", to: { name: "news-desk" }, label: t("nav.news"), icon: Newspaper },
  { id: "pulse", to: { name: "weekly-summary" }, label: t("sidebar.markets_pulse"), icon: PulseECGIcon },
  { id: "market", to: { name: "market-radar" }, label: t("sidebar.markets_radar"), icon: MarketIcon },
  {
    id: "tracking",
    to: { name: "tracking" },
    label: t("sidebar.tracking"),
    icon: Gauge,
    count: trackedCount.value,
  },
]);

const sortMenuOpen = ref(false);
const accountMenuOpen = ref(false);
const sortAnchor = ref(null);
const accountAnchor = ref(null);
const signingOut = ref(false);
const filterQuery = ref("");

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

// A filter field earns its place once the list outgrows a glance.
const showFilter = computed(() => (props.companies || []).length > 8);

// Sectors the loaded companies actually have. "All" first, the rest sorted;
// the row is hidden entirely when every company shares one sector, because a
// dropdown with a single real choice is furniture.
const sectors = computed(() => {
  const set = new Set();
  for (const company of props.companies || []) {
    const sector = String(company?.sector || "").trim();
    if (sector) set.add(sector);
  }
  return [ALL_SECTORS, ...Array.from(set).sort()];
});

const showSectorFilter = computed(() => sectors.value.length > 2);

const visibleCompanies = computed(() => {
  const q = filterQuery.value.trim().toLowerCase();
  const sector = deskSector.value;
  return listedCompanies.value.filter((company) => {
    if (deskDiffsOnly.value && !isCompanyModified(company)) return false;
    if (
      showSectorFilter.value &&
      sector !== ALL_SECTORS &&
      company.sector !== sector
    ) {
      return false;
    }
    if (!q || !showFilter.value) return true;
    return `${company.name || ""} ${company.ticker || ""} ${companyCategory(company)}`
      .toLowerCase()
      .includes(q);
  });
});

const collapseLabel = computed(() =>
  collapsed.value ? t("sidebar.expand") : t("sidebar.collapse"),
);

const accountLabel = computed(
  () => sessionName.value?.trim() || sessionEmail.value?.trim() || t("toolbar.account"),
);

const accountDetail = computed(() => {
  const email = sessionEmail.value?.trim();
  if (email && email.toLowerCase() !== accountLabel.value.toLowerCase()) return email;
  return isAnonDev() ? t("sidebar.local_dev") : "";
});

// One levitating glass pill per list, gliding to the selected row.
const navRef = ref(null);
const companyListRef = ref(null);
const {
  style: navGliderStyle,
  visible: navGliderVisible,
  instant: navGliderInstant,
  moveTo: moveNavGlider,
} = useGlider(navRef, ".source-row.router-link-exact-active");
const {
  style: companyGliderStyle,
  visible: companyGliderVisible,
  instant: companyGliderInstant,
  moveTo: moveCompanyGlider,
} = useGlider(companyListRef, ".source-row.router-link-active", {
  enabled: computed(() => !collapsed.value),
});

function onNavRowClick(event) {
  moveNavGlider(event.currentTarget);
  onNavigate();
}

// Clicking a company opens it in place, like a folder: its reports, its news
// and its Research Desk, one row each, with how many reports and headlines
// the first two hold. One company is open at a time; clicking it again closes
// it. A modified click (new tab, etc.) keeps the row's plain link to the desk.
const openCompanyId = ref(null);

// The company page on screen, if any: whose, and which of its three.
const routePage = computed(() => {
  const name = String(route?.name || "");
  if (name === "research" || name === "research-desk-company") {
    const id = String(route.params?.companyId || "");
    return id ? { companyId: id, kind: "desk" } : null;
  }
  const id = String(route?.query?.company || "");
  if (!id || id === "all") return null;
  if (name === "reports") return { companyId: id, kind: "reports" };
  if (name === "news-desk") return { companyId: id, kind: "news" };
  return null;
});

// However a company's page was reached (search, ⌘K, a link), the company
// opens here too, with that page marked.
watch(
  () => routePage.value?.companyId,
  (id) => {
    if (id) openCompanyId.value = id;
  },
  { immediate: true },
);

function isOpen(company) {
  return openCompanyId.value === company.id;
}

function isCurrent(company) {
  return routePage.value?.companyId === company.id;
}

// The row holds the selection when its company's page is on screen and the
// folder is shut; open, the page row under it does. The rail has no glider,
// so there the logo keeps its ring either way.
function rowSelected(company) {
  return isCurrent(company) && (collapsed.value || !isOpen(company));
}

function isPageActive(company, kind) {
  return isCurrent(company) && routePage.value.kind === kind;
}

// With a company's page on screen, the list holds the selection, so the desk
// row above it (Reports, News) doesn't hold a second one.
const companyHoldsSelection = computed(() => {
  const id = routePage.value?.companyId;
  return Boolean(id && visibleCompanies.value.some((company) => company.id === id));
});

function onCompanyRowClick(event, company) {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
    return;
  }
  event.preventDefault();
  closeMenus();
  if (isOpen(company)) openCompanyId.value = null;
  else openFolder(company);
}

// A company opened near the bottom of the list scrolls its pages into view.
function openFolder(company) {
  openCompanyId.value = company.id;
  nextTick(() => {
    document.getElementById(`company-pages-${company.id}`)?.scrollIntoView?.({
      block: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  });
}

function closeFolder(company) {
  if (isOpen(company)) openCompanyId.value = null;
}

function onPageClick(event) {
  moveCompanyGlider(event.currentTarget);
  onNavigate();
}

// Polling replaces the company objects; count against the fresh one.
const openCompany = computed(
  () => (props.companies || []).find((company) => company.id === openCompanyId.value) || null,
);

// Reports: the whole list, read when a company opens and again on each move
// between desks, so a report generated a moment ago is already counted. Until
// the first read lands there is no count rather than a wrong 0.
const allReports = ref(null);
let reportsRequest = 0;

async function loadReports() {
  const id = ++reportsRequest;
  try {
    const list = await api.listReports();
    if (id === reportsRequest) allReports.value = Array.isArray(list) ? list : [];
  } catch {
    // Keep the last count; the Reports page says what went wrong.
  }
}

watch(
  () => [openCompanyId.value, route?.name],
  ([id]) => {
    if (id) loadReports();
  },
  { immediate: true },
);

const reportsCount = computed(() => {
  if (!openCompany.value || !allReports.value) return null;
  return companyReports(allReports.value, openCompany.value.id).length;
});

// News: the headlines the News desk shows for the company, its own ticker's
// wire included.
const workspaceNews = inject("workspaceNews", ref([]));
const workspaceResearch = inject("workspaceResearch", ref([]));
const workspaceLiveNews = inject("workspaceLiveNews", ref([]));
const openTicker = computed(() => openCompany.value?.ticker || "");
const tickerNews = useTickerNewsFeed(openTicker);

const newsCount = computed(() => {
  if (!openCompany.value || !tickerNews.settled.value) return null;
  return companyHeadlines({
    feed: [...(unref(workspaceNews) || []), ...(unref(workspaceResearch) || [])],
    companies: props.companies,
    live: [...tickerNews.items.value, ...(unref(workspaceLiveNews) || [])],
    companyId: openCompany.value.id,
  }).length;
});

const companyPages = computed(() => {
  const id = openCompany.value?.id;
  if (!id) return [];
  return [
    {
      kind: "reports",
      label: t("sidebar.reports"),
      icon: FileText,
      to: { name: "reports", query: { company: id } },
      count: reportsCount.value,
    },
    {
      kind: "news",
      label: t("nav.news"),
      icon: Newspaper,
      to: { name: "news-desk", query: { company: id } },
      count: newsCount.value,
    },
    {
      kind: "desk",
      label: t("sidebar.research_desk"),
      icon: Building2,
      to: { name: "research", params: { companyId: id } },
      count: null,
    },
  ];
});

function closeMenus() {
  sortMenuOpen.value = false;
  accountMenuOpen.value = false;
}

function toggleSortMenu() {
  const next = !sortMenuOpen.value;
  closeMenus();
  sortMenuOpen.value = next;
}

function toggleAccountMenu() {
  const next = !accountMenuOpen.value;
  closeMenus();
  accountMenuOpen.value = next;
}

function onNavigate() {
  closeMenus();
  emit("navigate");
}

async function onSignOut() {
  if (signingOut.value) return;
  signingOut.value = true;
  closeMenus();
  try {
    await signOut();
    // To the sign-in form even on an anon-dev server, whose login route
    // would otherwise bounce straight back into the app.
    router?.push(signInRoute());
  } finally {
    signingOut.value = false;
  }
}

function onDocPointerDown(event) {
  const target = event.target;
  if (sortMenuOpen.value && !sortAnchor.value?.contains(target)) sortMenuOpen.value = false;
  if (accountMenuOpen.value && !accountAnchor.value?.contains(target)) {
    accountMenuOpen.value = false;
  }
}

function onKeydown(event) {
  if (event.key !== "Escape") return;
  if (sortMenuOpen.value || accountMenuOpen.value) {
    closeMenus();
    return;
  }
  if (props.mobileOpen) emit("close");
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown);
  document.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <aside
    class="fixed inset-y-0 left-0 z-50 flex w-[292px] max-w-[88vw] p-2 transition-[transform,width] duration-300 ease-emphasized lg:sticky lg:top-0 lg:z-20 lg:h-screen lg:max-w-none lg:translate-x-0"
    :class="[
      collapsed ? 'lg:w-[76px]' : 'lg:w-[268px]',
      mobileOpen ? 'translate-x-0' : '-translate-x-[108%]',
    ]"
    :data-collapsed="collapsed ? 'true' : 'false'"
    :inert="(!isDesktop && !mobileOpen) || undefined"
  >
    <div class="glass-panel relative flex h-full w-full min-w-0 flex-col rounded-[20px]">
      <!-- Brand -->
      <div
        class="flex shrink-0 items-center gap-1.5"
        :class="collapsed ? 'flex-col px-2 pb-1 pt-3' : 'px-2.5 pb-2 pt-2.5'"
      >
        <RouterLink
          :to="{ name: 'home' }"
          class="focus-ring flex min-w-0 flex-1 items-center gap-2.5 rounded-[11px] p-1"
          :class="collapsed ? 'justify-center' : ''"
          :title="t('nav.research_center')"
          @click="onNavigate"
        >
          <span class="brand-tile">
            <BrandMark :size="19" />
          </span>
          <span v-if="!collapsed" class="min-w-0 leading-tight">
            <span class="block truncate text-[13px] font-semibold tracking-[-0.01em] text-ink-primary">
              {{ t("nav.brand_product") }}
            </span>
            <span class="block truncate text-caption1 text-ink-muted">Berkeley Summit House</span>
          </span>
        </RouterLink>
        <button
          type="button"
          class="icon-btn max-lg:hidden"
          :aria-label="collapseLabel"
          :title="collapseLabel"
          :aria-expanded="!collapsed"
          @click="toggleSidebar"
        >
          <PanelLeft v-if="collapsed" class="h-[18px] w-[18px]" />
          <PanelLeftClose v-else class="h-[18px] w-[18px]" />
        </button>
        <button
          type="button"
          class="icon-btn lg:hidden"
          :aria-label="t('sidebar.close')"
          :title="t('sidebar.close')"
          @click="emit('close')"
        >
          <X class="h-[18px] w-[18px]" />
        </button>
      </div>

      <!-- Quick Action: Generate Report -->
      <div
        class="shrink-0"
        :class="collapsed ? 'flex justify-center px-2 py-1' : 'px-2.5 py-1'"
      >
        <button
          v-if="!collapsed"
          type="button"
          class="focus-ring flex w-full items-center gap-2 rounded-xl border border-accent/20 bg-accent/10 px-3 py-2 text-[13px] font-semibold text-accent-ink hover:bg-accent/15 transition-all active:scale-[0.98] shadow-sm"
          :title="`${t('memo.generate_report')} (⌘N)`"
          @click="onGenerateReport"
        >
          <AiMark class="h-4 w-4 shrink-0" />
          <span class="flex-1 truncate text-left">{{ t("memo.generate_report") }}</span>
          <kbd class="hidden font-mono text-[10px] text-ink-muted/80 sm:inline-block">⌘N</kbd>
        </button>
        <button
          v-else
          type="button"
          class="icon-btn !h-9 !w-9 rounded-xl border border-accent/20 bg-accent/10 text-accent hover:bg-accent/20 focus-ring"
          :aria-label="`${t('memo.generate_report')} (⌘N)`"
          :title="`${t('memo.generate_report')} (⌘N)`"
          @click="onGenerateReport"
        >
          <AiMark class="h-4 w-4 shrink-0" />
        </button>
      </div>

      <!-- Desks -->
      <nav class="shrink-0 px-2" :aria-label="t('sidebar.desks')">
        <div v-if="!collapsed" class="vogue-label px-2.5 pb-1 pt-1">
          {{ t("sidebar.desks") }}
        </div>
        <div
          ref="navRef"
          class="relative space-y-px"
          :data-glider="navGliderVisible ? 'on' : 'off'"
        >
          <div
            class="nav-glider glass-pill"
            :style="navGliderStyle"
            :data-visible="navGliderVisible ? 'true' : 'false'"
            :data-instant="navGliderInstant ? 'true' : 'false'"
            aria-hidden="true"
          />
          <RouterLink
            v-for="item in navItems"
            :key="item.id"
            :to="item.to"
            class="source-row focus-ring"
            active-class=""
            :exact-active-class="companyHoldsSelection ? '' : 'router-link-exact-active'"
            :title="item.label"
            :data-tour="`nav-${item.id}`"
            @click="onNavRowClick"
          >
            <component :is="item.icon" :size="18" class="source-row-icon shrink-0" />
            <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ item.label }}</span>
            <span
              v-if="!collapsed && item.count"
              class="mono-data text-caption1 text-ink-subtle"
            >
              {{ item.count }}
            </span>
          </RouterLink>
        </div>
      </nav>

      <div class="mx-4 my-2.5 h-px shrink-0 bg-ink-primary/[0.07]" aria-hidden="true" />

      <!-- Companies -->
      <section
        class="flex min-h-0 flex-1 flex-col"
        data-tour="companies"
        @dragover.prevent="onDeckDragOver"
        @dragleave="onDeckDragLeave"
        @drop.prevent="onDeckDrop"
      >
        <div
          v-if="!collapsed"
          class="mb-1 flex shrink-0 items-center justify-between gap-2 pl-[1.125rem] pr-2.5"
        >
          <div class="vogue-label">{{ t("sidebar.companies") }}</div>
          <div class="flex items-center gap-1">
            <span class="mono-data text-caption1 text-ink-subtle">{{
              loading && companies.length === 0 ? "—" : listedCompanies.length
            }}</span>
            <div ref="sortAnchor" class="relative">
              <button
                type="button"
                class="inline-flex h-6 items-center gap-1 rounded-pill px-1.5 text-caption1 font-medium text-ink-muted transition-colors hover:bg-ink-primary/[0.06] hover:text-ink-primary focus-ring"
                :aria-label="t('sidebar.sort')"
                :title="t('sidebar.sort')"
                :aria-expanded="sortMenuOpen"
                @click="toggleSortMenu"
              >
                <ArrowUpDown class="h-3.5 w-3.5" />
                <span>{{ activeSortLabel }}</span>
              </button>
              <div
                v-if="sortMenuOpen"
                class="toolbar-menu !min-w-[11rem]"
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

        <div v-if="!collapsed && showFilter" class="shrink-0 px-2.5 pb-1.5">
          <div class="relative">
            <Search
              class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle"
            />
            <input
              v-model="filterQuery"
              type="search"
              autocomplete="off"
              class="sidebar-filter"
              :placeholder="t('sidebar.filter_companies')"
              :aria-label="t('sidebar.filter_companies')"
              @keydown.escape.stop="filterQuery = ''"
            />
          </div>
        </div>

        <!-- Sector and Diffs: the two filters the desk's directory column
             carried, now that the column is this list. -->
        <div
          v-if="!collapsed && (showSectorFilter || listedCompanies.length)"
          class="flex shrink-0 items-center gap-1.5 px-2.5 pb-1.5"
        >
          <div v-if="showSectorFilter" class="mac-popup min-w-0 flex-1">
            <select
              :value="deskSector"
              :aria-label="t('sidebar.sector')"
              @change="setDeskSector($event.target.value)"
            >
              <option v-for="sector in sectors" :key="sector" :value="sector">
                {{ sector === ALL_SECTORS ? t("sidebar.all_sectors") : sector }}
              </option>
            </select>
            <ChevronsUpDown class="mac-popup-chevron h-2.5 w-2.5" />
          </div>
          <button
            type="button"
            class="mac-btn mac-btn--mini shrink-0"
            :class="deskDiffsOnly ? 'mac-btn--tint' : ''"
            :title="t('sidebar.diffs_help')"
            :aria-pressed="deskDiffsOnly"
            data-testid="sidebar-diffs-toggle"
            @click="toggleDeskDiffsOnly()"
          >
            <component :is="deskDiffsOnly ? Sparkle : Sparkles" class="h-3 w-3" />
            <span>{{ t("sidebar.diffs") }}</span>
          </button>
        </div>

        <!-- Only while a deck is actually over the list: a permanent
             drop box cost three lines of the rail to say something the
             reader already knows how to do. -->
        <div
          v-if="deckDragOver && !collapsed"
          class="sidebar-deck-overlay"
          data-testid="sidebar-deck-overlay"
        >
          <Upload class="h-4 w-4 shrink-0" />
          <span>{{ t("sidebar.drop_deck_release") }}</span>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-1">
          <div
            v-if="loading && companies.length === 0 && !collapsed"
            class="px-2.5 py-1.5 text-footnote text-ink-muted"
          >
            {{ t("common.loading") }}
          </div>
          <div v-else-if="error && !collapsed" class="px-2.5 py-1.5 text-footnote text-danger">
            {{ t("sidebar.load_error") }}
          </div>
          <div
            v-else-if="visibleCompanies.length === 0 && !collapsed"
            class="px-2.5 py-1.5 text-footnote text-ink-muted"
          >
            {{ filterQuery.trim() ? t("sidebar.no_filter_matches") : t("sidebar.no_companies") }}
          </div>
          <div
            v-else
            ref="companyListRef"
            class="relative space-y-px"
            :data-glider="companyGliderVisible ? 'on' : 'off'"
          >
            <div
              v-if="!collapsed"
              class="nav-glider glass-pill"
              :style="companyGliderStyle"
              :data-visible="companyGliderVisible ? 'true' : 'false'"
              :data-instant="companyGliderInstant ? 'true' : 'false'"
              aria-hidden="true"
            />
            <template v-for="company in visibleCompanies" :key="company.id">
            <div class="group relative">
              <!-- `custom`: RouterLink's own click handler would navigate
                   before ours could open the company, so the anchor is ours
                   and only a modified click falls through to the plain link. -->
              <RouterLink
                v-slot="{ href }"
                :to="{ name: 'research', params: { companyId: company.id } }"
                custom
              >
              <a
                :href="href"
                class="source-row company-source-row focus-ring"
                :class="[
                  collapsed ? 'company-rail-link' : '!py-[5px] !pl-2',
                  { 'router-link-active': rowSelected(company) },
                ]"
                :aria-current="
                  isPageActive(company, 'desk') && !isOpen(company) ? 'page' : undefined
                "
                :title="company.name"
                :aria-expanded="isOpen(company) ? 'true' : 'false'"
                :aria-controls="isOpen(company) ? `company-pages-${company.id}` : undefined"
                @click="onCompanyRowClick($event, company)"
                @keydown.right.prevent="openFolder(company)"
                @keydown.left.prevent="closeFolder(company)"
              >
                <Monogram
                  :company="company"
                  :size="collapsed ? 30 : 26"
                  tinted
                  class="company-rail-mark"
                  aria-hidden="true"
                />
                <template v-if="!collapsed">
                  <span class="min-w-0 flex-1 leading-tight">
                    <span class="block truncate">{{ company.name }}</span>
                    <span
                      v-if="companyCategory(company)"
                      class="block truncate text-caption1 font-normal text-ink-muted"
                    >
                      {{ companyCategory(company) }}
                    </span>
                  </span>
                  <CompanyFollowButton :company-id="company.id" hide-until-hover />
                  <ChevronDown
                    v-if="isOpen(company)"
                    class="company-disclosure h-3.5 w-3.5 shrink-0"
                    aria-hidden="true"
                  />
                </template>
              </a>
              </RouterLink>
            </div>
            <!-- The open company's pages, indented under its logo. Outside the
                 row's hover group, so pointing at them doesn't wake its star. -->
            <div
              v-if="isOpen(company)"
              :id="`company-pages-${company.id}`"
              class="company-pages"
              role="group"
              :aria-label="company.name"
              data-testid="company-pages"
            >
              <RouterLink
                v-for="page in companyPages"
                :key="page.kind"
                :to="page.to"
                class="source-row company-page-row focus-ring"
                :class="{ 'router-link-active': isPageActive(company, page.kind) }"
                active-class=""
                exact-active-class=""
                :aria-current="isPageActive(company, page.kind) ? 'page' : undefined"
                :title="page.label"
                :data-kind="page.kind"
                :data-testid="`company-page-${page.kind}`"
                @click="onPageClick"
              >
                <component :is="page.icon" :size="15" class="company-page-icon shrink-0" />
                <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ page.label }}</span>
                <span
                  v-if="!collapsed && page.count != null"
                  class="mono-data text-caption1 text-ink-subtle"
                  data-testid="company-page-count"
                >
                  {{ page.count }}
                </span>
              </RouterLink>
            </div>
            </template>
          </div>
        </div>
</section>

      <!-- Account -->
      <div ref="accountAnchor" class="relative shrink-0 px-2 pb-2">
        <div class="mx-2 mb-1.5 h-px bg-ink-primary/[0.07]" aria-hidden="true" />
        <button
          type="button"
          class="account-row focus-ring"
          :class="collapsed ? 'justify-center !px-0' : ''"
          :aria-label="t('toolbar.account')"
          :title="accountLabel"
          :aria-expanded="accountMenuOpen"
          @click="toggleAccountMenu"
        >
          <Monogram
            :name="accountLabel"
            :initials="sessionInitials"
            :size="collapsed ? 32 : 28"
            tinted
            round
          />
          <span v-if="!collapsed" class="min-w-0 flex-1 text-left leading-tight">
            <span class="block truncate text-[13px] font-medium text-ink-primary">
              {{ accountLabel }}
            </span>
            <span v-if="accountDetail" class="block truncate text-caption1 text-ink-muted">
              {{ accountDetail }}
            </span>
          </span>
          <ChevronsUpDown v-if="!collapsed" class="h-3.5 w-3.5 shrink-0 text-ink-subtle" />
        </button>
        <div
          v-if="accountMenuOpen"
          class="toolbar-menu account-menu"
          :data-rail="collapsed ? 'true' : 'false'"
          role="menu"
        >
          <RouterLink
            :to="{ name: 'settings' }"
            class="toolbar-menu-item"
            role="menuitem"
            @click="onNavigate"
          >
            <Settings class="h-4 w-4 shrink-0 text-ink-muted" />
            {{ t("app.settings") }}
          </RouterLink>
          <button
            v-if="isSignedIn"
            type="button"
            class="toolbar-menu-item hairline-t"
            role="menuitem"
            :disabled="signingOut"
            @click="onSignOut"
          >
            <LogOut class="h-4 w-4 shrink-0 text-ink-muted" />
            {{ t("auth.sign_out") }}
          </button>
          <!-- Nobody is signed in: the desk is open through the local
               anon-dev bypass, so there is nothing to sign out of. -->
          <RouterLink
            v-else
            :to="signInRoute(route?.fullPath)"
            class="toolbar-menu-item hairline-t"
            role="menuitem"
            @click="onNavigate"
          >
            <LogIn class="h-4 w-4 shrink-0 text-ink-muted" />
            {{ t("auth.sign_in") }}
          </RouterLink>
        </div>
      </div>
    </div>
  </aside>
</template>
