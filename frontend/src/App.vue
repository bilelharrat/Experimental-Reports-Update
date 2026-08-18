<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Bell,
  Bot,
  Library,
  Link as LinkIcon,
  LogOut,
  PanelRightClose,
  Plus,
  ScrollText,
  Search,
  Settings,
  UploadCloud,
} from "lucide-vue-next";
import { api } from "./api.js";
import { useT } from "./i18n.js";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import CompanyConsole from "./components/CompanyConsole.vue";
import { marketRadarItems, radarAge, radarRoute } from "./marketRadar.js";
import { activeSummaryTarget, closeSummary, setLastCompanyId } from "./state.js";
import { isAuthenticated, sessionEmail, signOut } from "./auth.js";

const news = ref([]);
const externalResearch = ref([]);
const companies = ref([]);
const loading = ref(true);
const error = ref(null);
const route = useRoute();
const router = useRouter();
const copilotOpen = ref(false);
const copilotReady = ref(false);
const companyConsoleRef = ref(null);
const headerRef = ref(null);
const addMenuOpen = ref(false);
const radarMenuOpen = ref(false);
const accountMenuOpen = ref(false);
const jumpQuery = ref("");
const jumpOpen = ref(false);
const signingOut = ref(false);
const t = useT();

// This feeds the toolbar radar and sidebar company list. Poll slowly;
// user actions refresh it immediately via @reports-changed.
const POLL_INTERVAL_MS = 20000;
let refreshing = false;

async function refreshAll() {
  // In-flight guard: /api/companies can take longer than the interval, so
  // without this the timer would stack overlapping refreshes.
  if (refreshing) return;
  refreshing = true;
  try {
    // allSettled, not all: one slow/failed endpoint must not blank the whole
    // sidebar (previously a single rejection dropped every assignment).
    const [f, c] = await Promise.allSettled([
      api.externalFeed(),
      api.listCompanies(),
    ]);
    if (f.status === "fulfilled") {
      news.value = f.value.filter((it) => it.kind === "news");
      externalResearch.value = f.value.filter(
        (it) => it.kind === "external_research",
      );
    }
    if (c.status === "fulfilled") companies.value = c.value;
    // A 401 means auth.js already tore down the session and is redirecting —
    // don't surface it. Show any other failure.
    const failure = [f, c].find(
      (x) => x.status === "rejected" && x.reason?.status !== 401,
    );
    error.value = failure ? failure.reason?.message || "Load failed" : null;
  } finally {
    loading.value = false;
    refreshing = false;
  }
}

// Drive the sidebar polling off the auth state: start when we log in,
// stop when we log out. Avoids the login page making /api/* calls that
// would 401 and dispatch the unauthorized event in a loop.
let pollTimer = null;

function pollTick() {
  // Skip work while the tab is hidden; refresh once on return (below).
  if (typeof document !== "undefined" && document.hidden) return;
  refreshAll();
}

function onVisibilityChange() {
  if (typeof document !== "undefined" && !document.hidden) refreshAll();
}

function startPolling() {
  if (pollTimer != null) return;
  refreshAll();
  pollTimer = window.setInterval(pollTick, POLL_INTERVAL_MS);
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisibilityChange);
  }
}
function stopPolling() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  if (typeof document !== "undefined") {
    document.removeEventListener("visibilitychange", onVisibilityChange);
  }
  news.value = [];
  externalResearch.value = [];
  companies.value = [];
  loading.value = true;
  error.value = null;
}

watch(
  isAuthenticated,
  (signedIn) => {
    if (signedIn) startPolling();
    else stopPolling();
  },
  { immediate: true },
);

const summaryCompanyId = computed(() => activeSummaryTarget.value?.companyId);
const summaryFile = computed(() => activeSummaryTarget.value?.file ?? null);

const currentCompanyId = computed(() => {
  const id = route.params?.companyId;
  return typeof id === "string" ? id : null;
});

const currentCompany = computed(() =>
  companies.value.find((c) => c.id === currentCompanyId.value) || null,
);

const radarItems = computed(() => marketRadarItems(news.value, externalResearch.value));

const jumpHits = computed(() => {
  const q = jumpQuery.value.trim().toLowerCase();
  if (!q) return [];
  return companies.value
    .filter((company) => {
      const hay = `${company.name || ""} ${company.ticker || ""} ${company.industry || ""}`.toLowerCase();
      return hay.includes(q);
    })
    .slice(0, 8);
});

function closeChromeMenus() {
  addMenuOpen.value = false;
  radarMenuOpen.value = false;
  accountMenuOpen.value = false;
  jumpOpen.value = false;
}

function toggleAddMenu() {
  const next = !addMenuOpen.value;
  closeChromeMenus();
  addMenuOpen.value = next;
}

function toggleRadarMenu() {
  const next = !radarMenuOpen.value;
  closeChromeMenus();
  radarMenuOpen.value = next;
}

function toggleAccountMenu() {
  const next = !accountMenuOpen.value;
  closeChromeMenus();
  accountMenuOpen.value = next;
}

function openJumpMenu() {
  addMenuOpen.value = false;
  radarMenuOpen.value = false;
  accountMenuOpen.value = false;
  jumpOpen.value = true;
}

function onDocPointerDown(event) {
  if (!headerRef.value?.contains(event.target)) closeChromeMenus();
}

function onChromeKeydown(event) {
  if (event.key !== "Escape") return;
  if (addMenuOpen.value || radarMenuOpen.value || accountMenuOpen.value || jumpOpen.value) {
    closeChromeMenus();
    return;
  }
  if (copilotOpen.value) setCopilotOpen(false);
}

function goToCompany(company) {
  closeChromeMenus();
  jumpQuery.value = "";
  router.push({ name: "research", params: { companyId: company.id } });
}

function researchQuery() {
  const q = jumpQuery.value.trim();
  closeChromeMenus();
  jumpQuery.value = "";
  router.push(q ? { path: "/", query: { q } } : { name: "home" });
}

function onJumpEnter() {
  if (jumpHits.value[0]) goToCompany(jumpHits.value[0]);
  else researchQuery();
}

async function onSignOut() {
  if (signingOut.value) return;
  signingOut.value = true;
  closeChromeMenus();
  try {
    await signOut();
  } finally {
    signingOut.value = false;
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocPointerDown);
  document.addEventListener("keydown", onChromeKeydown);
});

onBeforeUnmount(() => {
  stopPolling();
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onChromeKeydown);
});

watch(currentCompanyId, (id) => {
  if (id) setLastCompanyId(id);
});

function tabLabel(tab) {
  if (tab === "documents") return t("research.tab_documents");
  if (tab === "memo" || tab === "analysis") return t("research.tab_memo");
  if (tab === "news") return t("research.tab_news");
  if (tab === "industry") return t("research.tab_industry");
  if (tab === "console") return t("research.tab_console");
  return t("research.tab_overview");
}

const toolbarTitle = computed(() => {
  const crumbs = breadcrumbs.value;
  const name = String(route.name || "");
  if (name === "research") {
    return crumbs[1] || crumbs[crumbs.length - 1];
  }
  return crumbs[crumbs.length - 1] || t("nav.research_center");
});

const breadcrumbs = computed(() => {
  const name = String(route.name || "");
  const root = t("nav.research_center");
  if (name === "home") return [root, t("nav.home")];
  if (name === "stock-research") return [root, t("app.stock")];
  if (name === "settings") return [root, t("app.settings")];
  if (name === "user-center") return [root, t("app.user_center")];
  if (name === "source-library") {
    return [root, t("app.source_library")];
  }
  if (name === "competitor-detail") {
    return [
      root,
      currentCompany.value?.name || route.params?.companyId || t("app.company"),
      t("app.competitor_detail"),
    ];
  }
  if (name === "innovation-lab") return [root, t("app.innovation_lab")];
  if (name.startsWith("research-page-") || name.startsWith("innovation-")) {
    return [root, t("app.innovation_lab")];
  }
  if (name === "hormuz-library" || name === "hormuz-research") {
    return [root, t("app.innovation_lab"), t("app.hormuz")];
  }
  if (name === "external-news") return [root, t("app.market_radar")];
  if (name === "external-research") return [root, t("app.external_research")];
  if (name === "weekly-summary") return [root, t("app.weekly_summary")];
  if (name === "trader-stats") return [root, t("app.stats")];
  if (name === "research") {
    return [
      root,
      currentCompany.value?.name || currentCompanyId.value || t("app.company"),
      tabLabel(route.query?.report ? route.query.tab || "memo" : route.query?.tab),
    ];
  }
  return [root];
});

const copilotContext = computed(() => {
  if (currentCompany.value?.name) {
    return `${currentCompany.value.name} · ${tabLabel(route.query?.tab)}`;
  }
  return breadcrumbs.value.slice(1).join(" · ") || t("nav.breadcrumb_root");
});

const copilotQuickActions = computed(() => [
  t("copilot.quick_evidence"),
  t("copilot.quick_thesis"),
  t("copilot.quick_update"),
]);

function prefillCopilot(prompt) {
  companyConsoleRef.value?.prefillPrompt(prompt);
}

function setCopilotOpen(open) {
  if (open) copilotReady.value = true;
  copilotOpen.value = open;
}

watch(
  () => route.fullPath,
  () => {
    if (route.query?.tab === "console") setCopilotOpen(true);
  },
  { immediate: true },
);
</script>

<template>
  <!-- Unauthenticated: just the routed view (LoginView). No sidebar,
       no polling, no modals. -->
  <RouterView v-if="!isAuthenticated" />

  <!-- Authenticated: full app chrome. -->
  <div v-else class="canvas-wash min-h-screen bg-canvas text-ink-primary lg:flex">
    <Sidebar
      :companies="companies"
      :loading="loading"
      :error="error"
    />
    <main class="min-w-0 flex-1">
      <header
        ref="headerRef"
        class="material-bar sticky top-0 z-30 px-3 py-1.5 md:px-5"
      >
        <div class="flex items-center gap-2">
          <div class="min-w-0 flex-1 truncate text-headline font-semibold tracking-tight text-ink-primary">
            {{ toolbarTitle }}
          </div>

          <div
            v-if="route.name !== 'home'"
            class="relative hidden min-w-[11.5rem] max-w-[17rem] flex-[0.8] md:block"
          >
            <Search
              class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-subtle"
            />
            <input
              v-model="jumpQuery"
              type="search"
              autocomplete="off"
              class="field h-8 w-full rounded-subbox !py-0 !pl-8 !pr-2 text-footnote"
              :placeholder="t('toolbar.search_companies')"
              :aria-label="t('toolbar.search_companies')"
              @focus="openJumpMenu"
              @keydown.escape.prevent="closeChromeMenus"
              @keydown.enter.prevent="onJumpEnter"
            />
            <div
              v-if="jumpOpen && jumpQuery.trim()"
              class="toolbar-menu left-0 right-auto min-w-[17rem]"
              role="listbox"
            >
              <button
                v-for="company in jumpHits"
                :key="company.id"
                type="button"
                class="toolbar-menu-item"
                role="option"
                @click="goToCompany(company)"
              >
                <span class="truncate font-medium">{{ company.name }}</span>
                <span
                  v-if="company.ticker || company.industry"
                  class="truncate text-caption1 text-ink-muted"
                >
                  {{ company.ticker || company.industry }}
                </span>
              </button>
              <p
                v-if="jumpHits.length === 0"
                class="px-3 py-2.5 text-footnote text-ink-muted"
              >
                {{ t("toolbar.no_matches") }}
              </p>
              <RouterLink
                :to="{ path: '/', query: jumpQuery.trim() ? { q: jumpQuery.trim() } : {} }"
                class="toolbar-menu-item hairline-t text-accent-ink"
                @click="researchQuery"
              >
                {{
                  jumpQuery.trim()
                    ? t("toolbar.research_query", { q: jumpQuery.trim() })
                    : t("toolbar.search_all")
                }}
              </RouterLink>
            </div>
          </div>

          <div class="relative">
            <button
              type="button"
              class="icon-btn"
              :aria-label="t('toolbar.add')"
              :title="t('toolbar.add')"
              :aria-expanded="addMenuOpen"
              @click="toggleAddMenu"
            >
              <Plus class="h-[18px] w-[18px]" />
            </button>
            <div v-if="addMenuOpen" class="toolbar-menu" role="menu">
              <RouterLink
                :to="{ path: '/', query: { intake: 'link' } }"
                class="toolbar-menu-item"
                role="menuitem"
                @click="closeChromeMenus"
              >
                <LinkIcon class="h-4 w-4 shrink-0 text-ink-muted" />
                {{ t("sidebar.submit_link") }}
              </RouterLink>
              <RouterLink
                :to="{ path: '/', query: { intake: 'upload' } }"
                class="toolbar-menu-item"
                role="menuitem"
                @click="closeChromeMenus"
              >
                <UploadCloud class="h-4 w-4 shrink-0 text-ink-muted" />
                {{ t("sidebar.upload_research") }}
              </RouterLink>
              <RouterLink
                :to="{ path: '/', query: { intake: 'note' } }"
                class="toolbar-menu-item"
                role="menuitem"
                @click="closeChromeMenus"
              >
                <ScrollText class="h-4 w-4 shrink-0 text-ink-muted" />
                {{ t("sidebar.add_note") }}
              </RouterLink>
              <RouterLink
                :to="{ name: 'source-library' }"
                class="toolbar-menu-item"
                role="menuitem"
                @click="closeChromeMenus"
              >
                <Library class="h-4 w-4 shrink-0 text-ink-muted" />
                {{ t("home.source_library") }}
              </RouterLink>
            </div>
          </div>

          <div class="relative">
            <button
              type="button"
              class="icon-btn relative"
              :aria-label="t('toolbar.radar')"
              :title="t('toolbar.radar')"
              :aria-expanded="radarMenuOpen"
              @click="toggleRadarMenu"
            >
              <Bell class="h-[18px] w-[18px]" />
              <span
                v-if="radarItems.length"
                class="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-accent"
                aria-hidden="true"
              />
            </button>
            <div v-if="radarMenuOpen" class="toolbar-menu w-[22rem]" role="menu">
              <div class="px-3 pb-1 pt-2.5 text-caption1 font-semibold uppercase tracking-wide text-ink-subtle">
                {{ t("toolbar.radar") }}
              </div>
              <RouterLink
                v-for="item in radarItems"
                :key="item.id"
                :to="radarRoute(item)"
                class="toolbar-menu-item items-start"
                role="menuitem"
                @click="closeChromeMenus"
              >
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-medium">{{
                    item.title || t("sidebar.untitled")
                  }}</span>
                  <span class="block truncate text-caption1 text-ink-muted">{{
                    radarAge(item.captured_at, t)
                  }}</span>
                </span>
              </RouterLink>
              <p
                v-if="radarItems.length === 0"
                class="px-3 py-3 text-footnote text-ink-muted"
              >
                {{ t("toolbar.radar_empty") }}
              </p>
            </div>
          </div>

          <button
            type="button"
            class="icon-btn"
            :aria-label="t('copilot.ask')"
            :title="t('copilot.ask')"
            :aria-pressed="copilotOpen"
            @click="setCopilotOpen(!copilotOpen)"
          >
            <Bot class="h-[18px] w-[18px]" />
          </button>

          <RouterLink
            :to="{ name: 'settings' }"
            class="icon-btn"
            :aria-label="t('app.settings')"
            :title="t('app.settings')"
          >
            <Settings class="h-[18px] w-[18px]" />
          </RouterLink>

          <div class="relative">
            <button
              type="button"
              class="icon-btn overflow-hidden p-0"
              :aria-label="t('toolbar.account')"
              :title="sessionEmail || t('toolbar.account')"
              :aria-expanded="accountMenuOpen"
              @click="toggleAccountMenu"
            >
              <span
                class="grid h-7 w-7 place-items-center rounded-subbox bg-accent text-caption1 font-semibold uppercase text-white"
                aria-hidden="true"
              >
                {{ (sessionEmail || "?").charAt(0) }}
              </span>
            </button>
            <div v-if="accountMenuOpen" class="toolbar-menu" role="menu">
              <p
                v-if="sessionEmail"
                class="truncate px-3 pb-1 pt-2.5 text-caption1 text-ink-muted"
              >
                {{ sessionEmail }}
              </p>
              <RouterLink
                :to="{ name: 'settings' }"
                class="toolbar-menu-item"
                role="menuitem"
                @click="closeChromeMenus"
              >
                {{ t("app.settings") }}
              </RouterLink>
              <button
                type="button"
                class="toolbar-menu-item text-danger"
                role="menuitem"
                :disabled="signingOut"
                @click="onSignOut"
              >
                <LogOut class="h-4 w-4 shrink-0" />
                {{ t("auth.sign_out") }}
              </button>
            </div>
          </div>
        </div>
      </header>

      <RouterView v-slot="{ Component }">
        <Transition name="view-fade" mode="out-in">
          <component
            :is="Component"
            @reports-changed="refreshAll"
            @open-copilot="setCopilotOpen(true)"
          />
        </Transition>
      </RouterView>
    </main>

    <aside
      v-if="copilotReady"
      v-show="copilotOpen"
      class="fixed inset-y-0 right-0 z-50 flex w-full max-w-[320px] flex-col bg-surface hairline-l lg:sticky lg:top-0 lg:z-20 lg:h-screen lg:w-[320px] lg:shrink-0"
      :aria-label="t('copilot.title')"
    >
        <header class="flex items-center gap-3 px-4 py-3 hairline-b">
          <div class="min-w-0 flex-1">
            <div class="text-headline text-ink-primary">{{ t("copilot.title") }}</div>
            <div class="truncate text-footnote text-ink-muted">
              {{ copilotContext }}
            </div>
          </div>
          <button
            type="button"
            @click="setCopilotOpen(false)"
            class="icon-btn"
            :aria-label="t('copilot.collapse')"
            :title="t('copilot.collapse')"
          >
            <PanelRightClose class="h-4 w-4" />
          </button>
        </header>
        <div class="flex min-h-0 flex-1 flex-col gap-3 px-4 py-3">
          <p v-if="currentCompanyId" class="text-caption1 leading-relaxed text-ink-muted">
            {{ t("copilot.task_prompt") }}
          </p>
          <CompanyConsole
            v-if="currentCompanyId"
            ref="companyConsoleRef"
            class="min-h-0 flex-1"
            :company-id="currentCompanyId"
          />
          <div v-else class="space-y-3 pt-1">
            <p class="text-callout leading-relaxed text-ink-muted">
              {{ t("copilot.open_company") }}
            </p>
            <p class="text-footnote text-ink-subtle">{{ t("copilot.sample_user") }}</p>
          </div>
          <div v-if="currentCompanyId" class="flex flex-wrap gap-1.5 pt-1">
            <button
              v-for="action in copilotQuickActions"
              :key="action"
              type="button"
              @click="prefillCopilot(action)"
              class="focus-ring rounded-pill bg-fill-tertiary px-2.5 py-1 text-caption1 font-medium text-ink-secondary transition hover:bg-fill-secondary hover:text-ink-primary"
            >
              {{ action }}
            </button>
          </div>
        </div>
    </aside>

    <ActiveJobsRail />
    <DeckSummaryModal
      v-if="summaryCompanyId"
      :company-id="summaryCompanyId"
      :file="summaryFile"
      @close="closeSummary"
    />
  </div>
</template>
