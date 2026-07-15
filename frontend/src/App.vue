<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Bot, Languages, Settings, User, X } from "lucide-vue-next";
import { api } from "./api.js";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import CompanyConsole from "./components/CompanyConsole.vue";
import { activeSummaryTarget, closeSummary } from "./state.js";
import { appLanguage, setAppLanguage } from "./state.js";
import { isAuthenticated, sessionEmail } from "./auth.js";
import { useT } from "./i18n.js";

const t = useT();

const reports = ref([]);
const news = ref([]);
const externalResearch = ref([]);
const hormuz = ref([]);
const companies = ref([]);
const loading = ref(true);
const error = ref(null);
const route = useRoute();
const copilotOpen = ref(false);

// This feeds the sidebar nav — background data, not a live view. Poll slowly;
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
    const [r, f, h, c] = await Promise.allSettled([
      api.listReports(),
      api.externalFeed(),
      api.listHormuz(),
      api.listCompanies(),
    ]);
    if (r.status === "fulfilled") reports.value = r.value;
    if (f.status === "fulfilled") {
      news.value = f.value.filter((it) => it.kind === "news");
      externalResearch.value = f.value.filter(
        (it) => it.kind === "external_research",
      );
    }
    if (h.status === "fulfilled") hormuz.value = h.value;
    if (c.status === "fulfilled") companies.value = c.value;
    // A 401 means auth.js already tore down the session and is redirecting —
    // don't surface it. Show any other failure.
    const failure = [r, f, h, c].find(
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
  reports.value = [];
  news.value = [];
  externalResearch.value = [];
  hormuz.value = [];
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

onBeforeUnmount(stopPolling);

const summaryCompanyId = computed(() => activeSummaryTarget.value?.companyId);
const summaryFile = computed(() => activeSummaryTarget.value?.file ?? null);

const currentCompanyId = computed(() => {
  const id = route.params?.companyId;
  return typeof id === "string" ? id : null;
});

const currentCompany = computed(() =>
  companies.value.find((c) => c.id === currentCompanyId.value) || null,
);

function tabLabel(tab) {
  // The dictionary already carries research.tab_* in both languages —
  // ResearchView's tab strip uses them; this header copy must too.
  if (tab === "documents") return t("research.tab_documents");
  if (tab === "memo" || tab === "analysis") return t("research.tab_memo");
  if (tab === "news") return t("research.tab_news");
  if (tab === "industry") return t("research.tab_industry");
  if (tab === "console") return t("research.tab_console");
  return t("research.tab_overview");
}

const breadcrumbs = computed(() => {
  const name = String(route.name || "");
  const root = t("nav.breadcrumb_root");
  if (name === "home") return [root, t("nav.home")];
  if (name === "stock-research") return [root, t("sidebar.stock")];
  if (name === "settings") return [root, t("sidebar.settings")];
  if (name === "user-center") return [root, t("nav.user_center")];
  if (name === "source-library") {
    return [root, t("nav.source_library")];
  }
  if (name === "competitor-detail") {
    return [
      root,
      currentCompany.value?.name || route.params?.companyId || t("nav.company"),
      t("nav.competitor_detail"),
    ];
  }
  if (name === "innovation-lab") return [root, t("sidebar.innovation_lab")];
  if (name.startsWith("research-page-") || name.startsWith("innovation-")) {
    return [root, t("sidebar.innovation_lab")];
  }
  if (name === "hormuz-library" || name === "hormuz-research") {
    return [root, t("sidebar.innovation_lab"), "Hormuz"];
  }
  if (name === "external-news") return [root, t("sidebar.market_radar")];
  if (name === "external-research") return [root, t("nav.external_research")];
  if (name === "weekly-summary") return [root, t("nav.weekly_summary")];
  if (name === "trader-stats") return [root, t("nav.stats")];
  if (name === "research") {
    return [
      root,
      currentCompany.value?.name || currentCompanyId.value || t("nav.company"),
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

watch(
  () => route.fullPath,
  () => {
    if (route.query?.tab === "console") copilotOpen.value = true;
  },
  { immediate: true },
);
</script>

<template>
  <!-- Unauthenticated: just the routed view (LoginView). No sidebar,
       no polling, no modals. -->
  <RouterView v-if="!isAuthenticated" />

  <!-- Authenticated: full app chrome. -->
  <div v-else class="min-h-screen bg-canvas text-ink-primary lg:flex">
    <Sidebar
      :reports="reports"
      :news="news"
      :external-research="externalResearch"
      :hormuz="hormuz"
      :companies="companies"
      :loading="loading"
      :error="error"
    />
    <main class="flex-1 min-w-0">
      <header
        class="sticky top-0 z-30 border-b border-subtle bg-canvas/90 px-4 py-3 backdrop-blur md:px-8"
      >
        <div class="flex flex-wrap items-center gap-3">
          <nav
            class="min-w-0 basis-full text-xs text-ink-muted sm:flex-1 sm:basis-auto"
            :aria-label="t('nav.breadcrumb_label')"
          >
            <ol class="hidden min-w-0 items-center gap-1.5 sm:flex">
              <li
                v-for="(crumb, index) in breadcrumbs"
                :key="`${crumb}-${index}`"
                class="min-w-0"
              >
                <span
                  class="truncate"
                  :class="index === breadcrumbs.length - 1 ? 'text-ink-primary font-medium' : ''"
                >
                  {{ crumb }}
                </span>
                <span
                  v-if="index !== breadcrumbs.length - 1"
                  class="ml-1.5 text-ink-subtle"
                >
                  &gt;
                </span>
              </li>
            </ol>
            <div class="truncate font-medium text-ink-primary sm:hidden">
              {{ breadcrumbs[breadcrumbs.length - 1] || t("nav.breadcrumb_root") }}
            </div>
          </nav>

          <div
            class="inline-flex overflow-hidden rounded-full border border-subtle bg-surface text-xs"
            role="group"
            :aria-label="t('nav.app_language_label')"
          >
            <button
              type="button"
              @click="setAppLanguage('en')"
              :class="[
                'inline-flex items-center gap-1 px-3 py-1.5 focus-ring',
                appLanguage === 'en'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
              :aria-pressed="appLanguage === 'en'"
            >
              <Languages class="h-3.5 w-3.5" />
              EN
            </button>
            <button
              type="button"
              @click="setAppLanguage('zh')"
              :class="[
                'border-l border-subtle px-3 py-1.5 focus-ring',
                appLanguage === 'zh'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
              :aria-pressed="appLanguage === 'zh'"
            >
              中
            </button>
          </div>

          <RouterLink
            :to="{ name: 'settings' }"
            class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-subtle bg-surface text-ink-muted hover:text-ink-primary focus-ring"
            :aria-label="t('sidebar.settings')"
          >
            <Settings class="h-4 w-4" />
          </RouterLink>
          <RouterLink
            :to="{ name: 'user-center' }"
            class="inline-flex items-center gap-2 rounded-full border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:text-ink-primary focus-ring"
          >
            <User class="h-4 w-4 text-ink-muted" />
            <span class="hidden max-w-36 truncate sm:inline">{{ sessionEmail || t("sidebar.profile") }}</span>
          </RouterLink>
        </div>
      </header>

      <RouterView v-slot="{ Component }">
        <component
          :is="Component"
          @reports-changed="refreshAll"
          @open-copilot="copilotOpen = true"
        />
      </RouterView>
    </main>

    <button
      v-if="!copilotOpen"
      type="button"
      @click="copilotOpen = true"
      class="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-full bg-ink-primary p-3 text-sm font-semibold text-white shadow-card-raised hover:-translate-y-0.5 focus-ring sm:bottom-5 sm:right-5 sm:px-4"
      :aria-label="t('copilot.ask')"
    >
      <Bot class="h-4 w-4 text-accent-soft" />
      <span class="hidden sm:inline">{{ t("copilot.ask") }}</span>
    </button>

    <Teleport to="body">
      <aside
        v-if="copilotOpen"
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-[372px] flex-col border-l border-subtle bg-surface shadow-card-raised"
        :aria-label="t('copilot.title')"
      >
        <header class="flex items-start gap-3 border-b border-subtle px-4 py-4">
          <div
            class="mt-0.5 grid h-9 w-9 place-items-center rounded-full bg-accent-soft text-accent-ink"
          >
            <Bot class="h-4 w-4" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="vogue-label">{{ t("copilot.title") }}</div>
            <div class="truncate text-sm font-semibold text-ink-primary">
              {{ copilotContext }}
            </div>
          </div>
          <button
            type="button"
            @click="copilotOpen = false"
            class="rounded-full p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink-primary focus-ring"
            :aria-label="t('copilot.close')"
          >
            <X class="h-4 w-4" />
          </button>
        </header>
        <div class="flex-1 overflow-y-auto p-4">
          <CompanyConsole
            v-if="currentCompanyId"
            :company-id="currentCompanyId"
          />
          <div v-else class="space-y-4">
            <div class="rounded-card border border-subtle bg-surface-muted p-4">
              <div class="text-sm font-semibold text-ink-primary">
                {{ t("copilot.empty_title") }}
              </div>
              <p class="mt-1 text-sm leading-relaxed text-ink-muted">
                {{ t("copilot.empty_body") }}
              </p>
            </div>
            <div class="ml-auto max-w-[85%] rounded-l-card rounded-br-card bg-ink-primary px-3 py-2 text-sm text-white">
              {{ t("copilot.demo_user") }}
            </div>
            <div class="max-w-[85%] rounded-card bg-surface-muted px-3 py-2 text-sm text-ink-secondary">
              {{ t("copilot.demo_reply") }}
            </div>
          </div>
        </div>
      </aside>
    </Teleport>

    <ActiveJobsRail />
    <DeckSummaryModal
      v-if="summaryCompanyId"
      :company-id="summaryCompanyId"
      :file="summaryFile"
      @close="closeSummary"
    />
  </div>
</template>
