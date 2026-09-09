<script setup>
import { computed, onBeforeUnmount, onMounted, provide, ref, watch, nextTick } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Loader2,
  Link as LinkIcon,
  LogOut,
  PanelRightClose,
  Plus,
  ScrollText,
  Search,
  UploadCloud,
} from "lucide-vue-next";
import { api } from "./api.js";
import { useT } from "./i18n.js";
import AiMark from "./components/AiMark.vue";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import CopilotPanel from "./components/CopilotPanel.vue";
import MarketCommandPalette from "./components/MarketCommandPalette.vue";
import {
  parseMarketCommand,
  routeForMarketCommand,
} from "./marketCommands.js";
import {
  copilotPendingPrompt,
  copilotCompanyOverride,
  copilotDragTell,
  mergeCopilotContext,
  syncCopilotFromRoute,
} from "./copilotContext.js";
import { hydrateTrackingWatchlist } from "./trackingWatchlist.js";
import { initDeskSync } from "./deskSync.js";
import {
  activeSummaryTarget,
  closeSummary,
  companyViews,
  lastCompanyId,
  recordCompanyView,
  setLastCompanyId,
} from "./state.js";
import { isAuthenticated, sessionEmail, sessionInitials, sessionName, signOut } from "./auth.js";

const news = ref([]);
const externalResearch = ref([]);
const companies = ref([]);
const loading = ref(true);
const error = ref(null);
const route = useRoute();
const router = useRouter();
const copilotOpen = ref(false);
const copilotReady = ref(false);
const copilotPanelRef = ref(null);
const headerRef = ref(null);
const addMenuOpen = ref(false);
const accountMenuOpen = ref(false);
const jumpQuery = ref("");
const jumpOpen = ref(false);
const commandOpen = ref(false);
const signingOut = ref(false);
const addFileInput = ref(null);
const addUploading = ref(false);
const addUploadError = ref("");
const t = useT();

const FILE_ACCEPT =
  ".pdf,.pptx,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*,text/*";

provide("workspaceCompanies", companies);
provide("workspaceNews", news);
provide("workspaceResearch", externalResearch);
provide("workspaceLoading", loading);

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
  accountMenuOpen.value = false;
  jumpOpen.value = false;
  commandOpen.value = false;
}

function toggleAddMenu() {
  if (onCompanyPage.value) {
    addUploadError.value = "";
    closeChromeMenus();
    addFileInput.value?.click();
    return;
  }
  const next = !addMenuOpen.value;
  closeChromeMenus();
  addMenuOpen.value = next;
  if (!next) addUploadError.value = "";
}

function toggleAccountMenu() {
  const next = !accountMenuOpen.value;
  closeChromeMenus();
  accountMenuOpen.value = next;
}

function openJumpMenu() {
  addMenuOpen.value = false;
  accountMenuOpen.value = false;
  jumpOpen.value = true;
}

const onCompanyPage = computed(
  () => route.name === "research" && Boolean(currentCompanyId.value),
);

async function onCompanyAddFiles(event) {
  const input = event.target;
  const files = Array.from(input?.files || []);
  if (input) input.value = "";
  const companyId = currentCompanyId.value;
  if (!companyId || !files.length) return;

  addUploading.value = true;
  addUploadError.value = "";
  closeChromeMenus();
  try {
    for (const file of files) {
      await api.uploadResearchFile(companyId, file);
    }
    await router.push({
      name: "research",
      params: { companyId },
      query: {
        ...route.query,
        tab: "documents",
        files: String(Date.now()),
      },
    });
  } catch (err) {
    addUploadError.value = err?.message || t("toolbar.upload_failed");
    addMenuOpen.value = true;
  } finally {
    addUploading.value = false;
  }
}

function onDocPointerDown(event) {
  if (!headerRef.value?.contains(event.target)) closeChromeMenus();
}

function onChromeKeydown(event) {
  const key = String(event.key || "").toLowerCase();
  const meta = event.metaKey || event.ctrlKey;
  if (meta && key === "k") {
    event.preventDefault();
    addMenuOpen.value = false;
    accountMenuOpen.value = false;
    jumpOpen.value = false;
    commandOpen.value = !commandOpen.value;
    return;
  }
  if (event.key !== "Escape") return;
  if (addMenuOpen.value || accountMenuOpen.value || jumpOpen.value || commandOpen.value) {
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
  const raw = jumpQuery.value.trim();
  const cmd = parseMarketCommand(raw);
  const target = routeForMarketCommand(cmd);
  if (target && cmd?.action !== "search") {
    closeChromeMenus();
    jumpQuery.value = "";
    router.push(target);
    return;
  }
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
  hydrateTrackingWatchlist();
  if (isAuthenticated.value) {
    // Pull the server desk-state copy (watchlists, rules, lots…), then
    // evaluate alert rules server-side so "fired while away" lands in
    // history even before the Market desk is opened.
    initDeskSync();
    api.runAlertCheck().catch(() => {});
  }
});

onBeforeUnmount(() => {
  stopPolling();
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onChromeKeydown);
});

watch(currentCompanyId, (id) => {
  if (id) {
    setLastCompanyId(id);
    recordCompanyView(id);
    copilotCompanyOverride.value = null;
  }
  syncCopilotFromRoute(route, currentCompany.value);
});

watch(
  () => route.fullPath,
  () => {
    syncCopilotFromRoute(route, currentCompany.value);
    if (route.query?.tab === "console") {
      setCopilotOpen(true);
      mergeCopilotContext({ mode: "deep", tab: "console" });
    }
  },
  { immediate: true },
);

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
  if (name === "home") return [root, t("companies.section_title")];
  if (name === "news-desk") return [root, t("nav.news")];
  if (name === "tracking") return [root, t("sidebar.tracking")];
  if (name === "market-radar") return [root, t("sidebar.market")];
  if (name === "stock-research") return [root, t("nav.markets"), t("sidebar.markets_workbench")];
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
  if (name === "innovation-lab") return [root, t("nav.markets"), t("sidebar.markets_labs")];
  if (name.startsWith("research-page-") || name.startsWith("innovation-")) {
    return [root, t("nav.markets"), t("sidebar.markets_labs")];
  }
  if (name === "hormuz-library" || name === "hormuz-research") {
    return [root, t("nav.markets"), t("sidebar.markets_labs"), t("app.hormuz")];
  }
  if (name === "external-news") return [root, t("nav.markets"), t("sidebar.markets_radar")];
  if (name === "external-research") return [root, t("app.external_research")];
  if (name === "weekly-summary") return [root, t("pulse.title")];
  if (name === "trader-stats") return [root, t("nav.markets"), t("sidebar.markets_stats")];
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
  if (route.name === "news-desk") return t("nav.news");
  if (route.name === "tracking") return t("sidebar.tracking");
  return breadcrumbs.value.slice(1).join(" · ") || t("nav.breadcrumb_root");
});

const copilotCompanyId = computed(
  () => copilotCompanyOverride.value || currentCompanyId.value || "",
);

// Co-Pilot stays in the header everywhere in the app shell. On Home (no
// company id) the drawer shows a pick-a-company prompt + recents.
const showCopilotButton = computed(() => true);

const copilotRecentCompanies = computed(() => {
  const views = companyViews.value || {};
  const last = lastCompanyId.value;
  return [...(companies.value || [])]
    .filter((company) => company?.id)
    .sort((a, b) => {
      if (a.id === last) return -1;
      if (b.id === last) return 1;
      return (Number(views[b.id]) || 0) - (Number(views[a.id]) || 0);
    })
    .slice(0, 3);
});

const accountTitle = computed(() => {
  const name = sessionName.value?.trim();
  const email = sessionEmail.value?.trim();
  if (name && email && name.toLowerCase() !== email.toLowerCase()) {
    return `${name} · ${email}`;
  }
  return name || email || t("toolbar.account");
});

function setCopilotOpen(open) {
  if (open) copilotReady.value = true;
  copilotOpen.value = open;
}

function onOpenCopilot(payload) {
  setCopilotOpen(true);
  if (typeof payload === "string") {
    queueCopilotPrompt(payload);
    return;
  }
  if (!payload || typeof payload !== "object") return;
  if (payload.companyId) copilotCompanyOverride.value = payload.companyId;
  if (payload.context) mergeCopilotContext(payload.context);
  if (payload.mode) mergeCopilotContext({ mode: payload.mode });
  if (payload.dragTell) copilotDragTell.value = true;
  if (payload.dragTell && payload.companyId) {
    api.copilot.recordEvent(payload.companyId, {
      event: "copilot_drag_tell_drop",
      payload: {
        target_kind: payload.context?.selection?.target_kind,
        surface: payload.context?.surface,
      },
    }).catch(() => {});
  }
  if (payload.prompt) queueCopilotPrompt(payload.prompt);
}

function queueCopilotPrompt(prompt) {
  const value = String(prompt || "").trim();
  if (!value) return;
  copilotPendingPrompt.value = value;
  const attempt = (tries = 0) => {
    nextTick(() => {
      if (copilotPanelRef.value?.sendPrompt && copilotCompanyId.value) {
        copilotPanelRef.value.sendPrompt(value);
        copilotPendingPrompt.value = "";
        return;
      }
      if (tries < 6) attempt(tries + 1);
    });
  };
  attempt();
}

provide("openCopilot", onOpenCopilot);

function onCopilotNavigate(target) {
  if (!target?.companyId) return;
  if (target.kind === "file") {
    router.push({
      name: "research",
      params: { id: target.companyId },
      query: {
        tab: "documents",
        previewFile: target.file?.id,
        previewPage: target.page || undefined,
      },
    });
    return;
  }
  if (target.kind === "memo_bullet") {
    router.push({
      name: "research",
      params: { id: target.companyId },
      query: {
        tab: "memo",
        memoStage: "edit",
        memoSection: target.sectionId,
        memoBullet: target.bulletId,
      },
    });
  }
}

provide("copilotNavigate", onCopilotNavigate);
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
              :placeholder="t('cmd.jump_placeholder')"
              :aria-label="t('cmd.jump_placeholder')"
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
              :aria-label="
                onCompanyPage
                  ? t('toolbar.add_to_company', {
                      name: currentCompany?.name || t('app.company'),
                    })
                  : t('toolbar.add')
              "
              :title="
                onCompanyPage
                  ? t('toolbar.add_to_company', {
                      name: currentCompany?.name || t('app.company'),
                    })
                  : t('toolbar.add')
              "
              :aria-expanded="addMenuOpen"
              :disabled="addUploading"
              @click="toggleAddMenu"
            >
              <Loader2 v-if="addUploading" class="h-[18px] w-[18px] animate-spin" />
              <Plus v-else class="h-[18px] w-[18px]" />
            </button>
            <div v-if="addMenuOpen" class="toolbar-menu" role="menu">
              <template v-if="onCompanyPage">
                <p class="px-3 pb-2.5 pt-2.5 text-caption1 text-danger">
                  {{ addUploadError }}
                </p>
                <button
                  type="button"
                  class="toolbar-menu-item"
                  role="menuitem"
                  :disabled="addUploading"
                  @click="addFileInput?.click()"
                >
                  <UploadCloud class="h-4 w-4 shrink-0 text-ink-muted" />
                  {{ t("documents.add_file") }}
                </button>
              </template>
              <template v-else>
                <RouterLink
                  :to="{ path: '/', query: { intake: 'link' } }"
                  class="toolbar-menu-item"
                  role="menuitem"
                  @click="closeChromeMenus"
                >
                  <LinkIcon class="h-4 w-4 shrink-0 text-ink-muted" />
                  {{ t("home.action_link") }}
                </RouterLink>
                <RouterLink
                  :to="{ path: '/', query: { intake: 'upload' } }"
                  class="toolbar-menu-item"
                  role="menuitem"
                  @click="closeChromeMenus"
                >
                  <UploadCloud class="h-4 w-4 shrink-0 text-ink-muted" />
                  {{ t("home.action_file") }}
                </RouterLink>
                <RouterLink
                  :to="{ path: '/', query: { intake: 'note' } }"
                  class="toolbar-menu-item"
                  role="menuitem"
                  @click="closeChromeMenus"
                >
                  <ScrollText class="h-4 w-4 shrink-0 text-ink-muted" />
                  {{ t("home.action_note") }}
                </RouterLink>
              </template>
            </div>
            <input
              ref="addFileInput"
              type="file"
              multiple
              :accept="FILE_ACCEPT"
              class="hidden"
              @change="onCompanyAddFiles"
            />
          </div>

          <div class="inline-flex shrink-0 items-center gap-1">
            <button
              type="button"
              class="icon-btn"
              :aria-label="t('cmd.open')"
              :title="t('cmd.open')"
              :aria-pressed="commandOpen"
              @click="commandOpen = !commandOpen"
            >
              <Search class="h-[18px] w-[18px]" />
            </button>
          </div>

          <div v-if="showCopilotButton" class="inline-flex shrink-0 items-center gap-1">
            <button
              type="button"
              class="copilot-toolbar-btn focus-ring"
              :aria-label="t('copilot.ask')"
              :title="t('copilot.ask')"
              :aria-pressed="copilotOpen"
              @click="setCopilotOpen(!copilotOpen)"
            >
              <AiMark class="h-[18px] w-[18px] shrink-0" />
              <span class="text-caption1 font-medium">{{ t("copilot.title") }}</span>
            </button>
          </div>

          <div class="relative">
            <button
              type="button"
              class="icon-btn overflow-hidden p-0"
              :aria-label="t('toolbar.account')"
              :title="accountTitle"
              :aria-expanded="accountMenuOpen"
              @click="toggleAccountMenu"
            >
              <span
                class="grid h-7 w-7 place-items-center rounded-subbox bg-fill-tertiary text-[11px] font-semibold tracking-tight text-ink-secondary"
                aria-hidden="true"
              >
                {{ sessionInitials }}
              </span>
            </button>
            <div v-if="accountMenuOpen" class="toolbar-menu" role="menu">
              <p
                v-if="sessionName || sessionEmail"
                class="truncate px-3 pb-0.5 pt-2.5 text-caption1 font-medium text-ink-primary"
              >
                {{ sessionName || sessionEmail }}
              </p>
              <p
                v-if="sessionName && sessionEmail"
                class="truncate px-3 pb-1 text-caption1 text-ink-muted"
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
            @open-copilot="onOpenCopilot"
          />
        </Transition>
      </RouterView>
    </main>

    <Transition name="sheet-scrim">
      <button
        v-if="copilotOpen"
        type="button"
        class="sheet-scrim fixed inset-0 z-40 xl:hidden"
        :aria-label="t('copilot.collapse')"
        @click="setCopilotOpen(false)"
      />
    </Transition>
    <Transition name="copilot-drawer">
      <aside
        v-if="copilotOpen && copilotReady"
        class="fixed inset-y-0 right-0 z-50 flex w-full max-w-[400px] flex-col bg-surface hairline-l xl:sticky xl:top-0 xl:z-20 xl:h-screen xl:w-[400px] xl:shrink-0"
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
        <div class="flex min-h-0 flex-1 flex-col px-4 py-3">
          <CopilotPanel
            ref="copilotPanelRef"
            :company-id="copilotCompanyId"
            :context-label="copilotContext"
            @close="setCopilotOpen(false)"
          />
          <div
            v-if="!copilotCompanyId && copilotRecentCompanies.length"
            class="mt-3 space-y-0.5"
          >
            <div class="vogue-label px-0.5">{{ t("copilot.recent") }}</div>
            <button
              v-for="company in copilotRecentCompanies"
              :key="company.id"
              type="button"
              class="toolbar-menu-item w-full text-left"
              @click="goToCompany(company)"
            >
              <span class="truncate font-medium">{{ company.name }}</span>
            </button>
          </div>
        </div>
      </aside>
    </Transition>

    <ActiveJobsRail :copilot-open="copilotOpen" />
    <MarketCommandPalette
      :open="commandOpen"
      :companies="companies"
      @close="commandOpen = false"
    />
    <DeckSummaryModal
      v-if="summaryCompanyId"
      :company-id="summaryCompanyId"
      :file="summaryFile"
      @close="closeSummary"
    />
  </div>
</template>
