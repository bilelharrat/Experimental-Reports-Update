<script setup>
import { computed, onBeforeUnmount, onMounted, provide, ref, watch, nextTick } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  ChevronsLeft,
  ChevronsRight,
  Command,
  History,
  Loader2,
  Link as LinkIcon,
  PanelLeft,
  PanelRightClose,
  FileUp,
  Plus,
  ScrollText,
  Search,
  SlidersHorizontal,
  SquarePen,
  UploadCloud,
} from "lucide-vue-next";
import { api } from "./api.js";
import {
  COPILOT_DEFAULT_WIDTH,
  COPILOT_MAX_WIDTH,
  COPILOT_MIN_WIDTH,
  COPILOT_WIDE_WIDTH,
  clampCopilotWidth,
  fitCopilotWidth,
  readCopilotWidth,
  writeCopilotWidth,
} from "./copilotWidth.js";
import { currentLanguage, useT } from "./i18n.js";
import AiMark from "./components/AiMark.vue";
import Monogram from "./components/Monogram.vue";
import WarrenMark from "./components/WarrenMark.vue";
import CopilotCompanyPicker from "./components/CopilotCompanyPicker.vue";
import Sidebar from "./components/Sidebar.vue";
import ActiveJobsRail from "./components/ActiveJobsRail.vue";
import TaskHistoryPanel from "./components/TaskHistoryPanel.vue";
import DeckSummaryModal from "./components/DeckSummaryModal.vue";
import ReportCustomizerModal from "./components/ReportCustomizerModal.vue";
import { reportsCompanyFilter } from "./reportStatus.js";
import PitchDeckIntakeModal from "./components/research/PitchDeckIntakeModal.vue";
import CopilotPanel from "./components/CopilotPanel.vue";
import MarketCommandPalette from "./components/MarketCommandPalette.vue";
import WelcomeTour from "./components/WelcomeTour.vue";
import {
  closeWelcomeTour,
  presentWelcomeTourIfNeeded,
  welcomeTourOpen,
} from "./welcomeTour.js";
import {
  parseMarketCommand,
  routeForMarketCommand,
} from "./marketCommands.js";
import { SECTION_LABEL_KEYS, sectionFromQuery } from "./dossierSections.js";
import {
  clearCopilotFocus,
  copilotPendingPrompt,
  copilotCompanyOverride,
  copilotDraftPrompt,
  copilotDragTell,
  mergeCopilotContext,
  syncCopilotFromRoute,
} from "./copilotContext.js";
import { hydrateTrackingWatchlist } from "./trackingWatchlist.js";
import { initDeskSync } from "./deskSync.js";
import { autoObserveLargeTitle, chromeLeftInset, largeTitleVisible } from "./chrome.js";
import { installGlassMotion } from "./glassMotion.js";
import {
  activeSummaryTarget,
  closeSummary,
  companyViews,
  lastCompanyId,
  recordCompanyView,
  setLastCompanyId,
} from "./state.js";
import { isAuthenticated } from "./auth.js";

const news = ref([]);
const externalResearch = ref([]);
const companies = ref([]);
const liveNews = ref([]);
const loading = ref(true);
const error = ref(null);
// Last successful company refresh, shown in the toolbar like the Mac's
// "Synced 10:42 PM".
const lastSyncAt = ref(null);
const route = useRoute();
const router = useRouter();
const copilotOpen = ref(false);
const historyOpen = ref(false);
const copilotReady = ref(false);
const copilotPanelRef = ref(null);
// Reported by the panel: Warren answering, a chat on screen, quick or deep.
const copilotState = ref({ busy: false, hasTurns: false, mode: "quick" });
const headerRef = ref(null);
const addMenuOpen = ref(false);
const jumpQuery = ref("");
const jumpOpen = ref(false);
const commandOpen = ref(false);
const addFileInput = ref(null);
const addUploading = ref(false);
const addUploadError = ref("");
// Below lg the sidebar is a drawer; the toolbar's sidebar button opens it.
const mobileNavOpen = ref(false);
// Once content slides under the toolbar it turns to glass (scroll edge).
const scrolled = ref(false);
// The routed view's wrapper, searched for a large title after navigation.
const viewRef = ref(null);
let autoTitleTimer = null;
const t = useT();

const FILE_ACCEPT =
  ".pdf,.pptx,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/*,text/*";

provide("workspaceCompanies", companies);
provide("workspaceNews", news);
provide("workspaceResearch", externalResearch);
provide("workspaceLiveNews", liveNews);
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
    const bookTickers = [
      ...new Set(
        (companies.value || [])
          .map((company) => String(company?.ticker || "").trim().toUpperCase())
          .filter(Boolean),
      ),
    ].slice(0, 10);
    const [f, c, live] = await Promise.allSettled([
      api.externalFeed(),
      api.listCompanies(),
      api.quotesNews({ tickers: bookTickers, limit: 50 }),
    ]);
    if (f.status === "fulfilled") {
      news.value = f.value.filter((it) => it.kind === "news");
      externalResearch.value = f.value.filter(
        (it) => it.kind === "external_research",
      );
    }
    if (c.status === "fulfilled") {
      companies.value = c.value;
      lastSyncAt.value = new Date();
    }
    if (live.status === "fulfilled") {
      liveNews.value = live.value?.items || [];
    }
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
  liveNews.value = [];
  loading.value = true;
  error.value = null;
  lastSyncAt.value = null;
}

watch(
  () => [isAuthenticated.value, route.name],
  ([signedIn, routeName]) => {
    if (signedIn && routeName !== "login") {
      startPolling();
      presentWelcomeTourIfNeeded();
    } else {
      stopPolling();
    }
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

const reportCustomizerOpen = ref(false);
const reportCustomizerCompanyId = ref(null);

const reportCustomizerMode = ref("");

// `mode: "studio_review"` opens it on Memo Studio review, which is how the
// desk's "Run Deep Investigate" gets there; anything else keeps the default.
//
// With no company named by the caller (⌘N, the app menu, the sidebar), the
// page decides: a company's own page, or the Reports desk filtered to one
// (`/reports?company=`). Anywhere else the dialog opens on no company and
// asks, rather than on whichever company happened to be picked last.
function openReportCustomizer(companyId = null, { mode = "" } = {}) {
  const resolved = typeof companyId === "string" ? companyId : companyId?.companyId || null;
  reportCustomizerCompanyId.value =
    resolved || currentCompany.value?.id || reportsCompanyFilter(route) || null;
  reportCustomizerMode.value = mode;
  reportCustomizerOpen.value = true;
}

provide("openReportCustomizer", openReportCustomizer);

// The pitch-deck drop lived under the research desk's directory column. The
// column is part of the sidebar now, and the sidebar is mounted beside every
// view, so the modal it opens belongs at app level rather than inside one
// desk — same reasoning as the report customizer above.
const deckIntakeOpen = ref(false);
const deckIntakeFile = ref(null);

function openDeckIntake(file = null) {
  deckIntakeFile.value = file || null;
  deckIntakeOpen.value = true;
}

// The intake sheet seeds from a file and has no picker of its own, so the
// menu entry asks for one first. Dragging a deck onto the sidebar is the
// other way in.
const deckPickInput = ref(null);

function pickDeck() {
  if (!deckPickInput.value) return;
  deckPickInput.value.value = "";
  deckPickInput.value.click();
}

function onDeckPicked(event) {
  const file = event.target.files?.[0];
  if (file) openDeckIntake(file);
}

provide("openDeckIntake", openDeckIntake);

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

function openJumpMenu() {
  addMenuOpen.value = false;
  jumpOpen.value = true;
}

function openCommandPalette() {
  closeChromeMenus();
  commandOpen.value = true;
}

// A company's desk, at `/:companyId` (or its /research/ alias) or inside
// the Research Desk at `/research-desk/:companyId`.
const onCompanyPage = computed(
  () =>
    (route.name === "research" || route.name === "research-desk-company") &&
    Boolean(currentCompanyId.value),
);

// Where to send a link into a company's desk. The company already on
// screen keeps its own URL, so the link only moves the desk's tab.
function companyLocation(companyId, query) {
  if (onCompanyPage.value && currentCompanyId.value === companyId) {
    return { path: route.path, query };
  }
  return { name: "research", params: { companyId }, query };
}

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
    // Onto the desk's Files tab, and `files` has it reload the list: the
    // desk is already open, so without both the upload looks like nothing.
    // Already on Files, only the list changes, which is no step for Back.
    const to = companyLocation(companyId, { section: "files", files: String(Date.now()) });
    if (sectionFromQuery(route.query) === "files") await router.replace(to);
    else await router.push(to);
  } catch (err) {
    addUploadError.value = err?.message || t("toolbar.upload_failed");
    addMenuOpen.value = true;
  } finally {
    addUploading.value = false;
  }
}

function onDocPointerDown(event) {
  if (!headerRef.value?.contains(event.target)) {
    addMenuOpen.value = false;
    jumpOpen.value = false;
  }
}

function onChromeKeydown(event) {
  const key = String(event.key || "").toLowerCase();
  const meta = event.metaKey || event.ctrlKey;
  if (meta && key === "k") {
    event.preventDefault();
    addMenuOpen.value = false;
    jumpOpen.value = false;
    commandOpen.value = !commandOpen.value;
    return;
  }
  if (meta && key === "n") {
    event.preventDefault();
    addMenuOpen.value = false;
    jumpOpen.value = false;
    commandOpen.value = false;
    openReportCustomizer();
    return;
  }
  if (event.key !== "Escape") return;
  if (welcomeTourOpen.value) {
    closeWelcomeTour();
    return;
  }
  if (reportCustomizerOpen.value) {
    reportCustomizerOpen.value = false;
    return;
  }
  if (addMenuOpen.value || jumpOpen.value || commandOpen.value) {
    closeChromeMenus();
    return;
  }
  if (mobileNavOpen.value) {
    mobileNavOpen.value = false;
    return;
  }
  if (copilotOpen.value) setCopilotOpen(false);
}

function onWindowScroll() {
  scrolled.value = window.scrollY > 2;
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

let uninstallGlassMotion = () => {};

onMounted(() => {
  autoTitleTimer = setTimeout(() => autoObserveLargeTitle(viewRef.value), 450);
  copilotPreferredWidth.value = readCopilotWidth();
  viewportWidth.value = window.innerWidth;
  window.addEventListener("resize", onWindowResize);
  document.addEventListener("pointerdown", onDocPointerDown);
  document.addEventListener("keydown", onChromeKeydown);
  window.addEventListener("scroll", onWindowScroll, { passive: true });
  onWindowScroll();
  uninstallGlassMotion = installGlassMotion();
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
  clearTimeout(autoTitleTimer);
  window.removeEventListener("resize", onWindowResize);
  stopPolling();
  document.removeEventListener("pointerdown", onDocPointerDown);
  document.removeEventListener("keydown", onChromeKeydown);
  window.removeEventListener("scroll", onWindowScroll);
  uninstallGlassMotion();
});

watch(currentCompanyId, (id) => {
  if (id) {
    setLastCompanyId(id);
    recordCompanyView(id);
    copilotCompanyOverride.value = null;
  }
  syncCopilotFromRoute(route, currentCompany.value);
});

// A memo point or flag handed to Warren belongs to the page it came from;
// leaving the page drops it so later questions aren't scoped to it.
watch(
  () => route.path,
  (next, previous) => {
    if (previous && next !== previous) clearCopilotFocus();
  },
);

// Pages without their own large-title registration still hand their first
// h1 to the toolbar once the route transition has rendered it.
watch(
  () => route.name,
  () => {
    clearTimeout(autoTitleTimer);
    autoTitleTimer = setTimeout(() => autoObserveLargeTitle(viewRef.value), 450);
  },
);

watch(
  () => route.fullPath,
  () => {
    mobileNavOpen.value = false;
    syncCopilotFromRoute(route, currentCompany.value);
    if (route.query?.tab === "console") {
      setCopilotOpen(true);
      mergeCopilotContext({ mode: "deep", tab: "console" });
    }
  },
  { immediate: true },
);

// The desk tab a company URL shows, named as the desk's tab bar names it.
function sectionLabel(query) {
  return t(SECTION_LABEL_KEYS[sectionFromQuery(query) || "overview"]);
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
  if (name === "news-desk") return [root, t("nav.news")];
  if (name === "reports") return [root, t("nav.reports")];
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
    // The desk shows "Company not found" for an id that matches nothing
    // once the list has loaded; the toolbar says the same instead of the
    // raw id over an "Overview" it is not showing.
    if (currentCompanyId.value && lastSyncAt.value && !currentCompany.value) {
      return [root, t("desk.company_not_found_title")];
    }
    return [
      root,
      currentCompany.value?.name || currentCompanyId.value || t("app.company"),
      sectionLabel(route.query),
    ];
  }
  return [root];
});

const syncLabel = computed(() => {
  if (error.value) return t("toolbar.sync_failed");
  if (!lastSyncAt.value) return t("toolbar.syncing");
  const time = lastSyncAt.value.toLocaleTimeString(currentLanguage.value === "zh" ? "zh-CN" : "en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  return t("toolbar.synced", { time });
});

// Company pages keep the tab as a quiet second line under the toolbar title.
const toolbarSubtitle = computed(() => {
  if (route.name !== "research") return "";
  const crumbs = breadcrumbs.value;
  return crumbs.length > 2 ? crumbs[crumbs.length - 1] : "";
});

// Warren reads one company: the one picked in his header, else the company
// page on screen, else the last company opened (as the Mac falls back to
// its selected company).
const copilotCompanyId = computed(() => {
  if (copilotCompanyOverride.value) return copilotCompanyOverride.value;
  if (currentCompanyId.value) return currentCompanyId.value;
  const last = lastCompanyId.value;
  return last && companies.value.some((company) => company.id === last) ? last : "";
});

const copilotCompanyName = computed(
  () => companies.value.find((company) => company.id === copilotCompanyId.value)?.name || "",
);

// The tab Warren can see, only while his company is the page on screen.
const copilotSeesLabel = computed(() => {
  if (route.name !== "research" || copilotCompanyId.value !== currentCompanyId.value) return "";
  return sectionLabel(route.query);
});

const copilotRecentIds = computed(() => {
  const views = companyViews.value || {};
  const last = lastCompanyId.value;
  const known = new Set((companies.value || []).map((company) => company.id));
  return [...new Set([last, ...Object.keys(views)])]
    .filter((id) => id && known.has(id))
    .sort((a, b) => {
      if (a === last) return -1;
      if (b === last) return 1;
      return (Number(views[b]) || 0) - (Number(views[a]) || 0);
    })
    .slice(0, 3);
});

const copilotSuggestedCompanies = computed(() => {
  const rows = companies.value || [];
  const recent = copilotRecentIds.value
    .map((id) => rows.find((company) => company.id === id))
    .filter(Boolean);
  const recentSet = new Set(recent.map((company) => company.id));
  const others = rows
    .filter((company) => company?.id && !recentSet.has(company.id))
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  return [...recent, ...others].slice(0, 6);
});

const copilotPickerValue = computed({
  get: () => copilotCompanyId.value,
  set: (id) => chooseCopilotCompany(id),
});

function chooseCopilotCompany(id) {
  const next = String(id || "");
  copilotCompanyOverride.value = next && next !== currentCompanyId.value ? next : null;
}

function onCopilotState(state) {
  copilotState.value = { ...copilotState.value, ...state };
}

// ---- The rail's width ---------------------------------------------------
// The width lives on the document element, not the panel, because the
// jobs rail and the task history sit beside it and have to move too.
//
// What the analyst chose and what this window can give it are kept
// apart: a narrow window shows a narrower rail without forgetting the
// choice, so widening the window brings it back.
const copilotPreferredWidth = ref(COPILOT_DEFAULT_WIDTH);
const viewportWidth = ref(1440);
const copilotWidth = computed(() =>
  fitCopilotWidth(copilotPreferredWidth.value, viewportWidth.value),
);
const copilotWide = computed(() => copilotWidth.value >= COPILOT_WIDE_WIDTH);
let widthBeforeWide = COPILOT_DEFAULT_WIDTH;
let copilotDrag = null;

watch(
  copilotWidth,
  (width) => {
    document.documentElement.style.setProperty("--copilot-w", `${width}px`);
  },
  { immediate: true },
);

function setCopilotWidth(value, { persist = true } = {}) {
  copilotPreferredWidth.value = clampCopilotWidth(value);
  if (persist) writeCopilotWidth(copilotPreferredWidth.value);
}

function toggleCopilotWide() {
  if (copilotWide.value) {
    setCopilotWidth(widthBeforeWide || COPILOT_DEFAULT_WIDTH);
    return;
  }
  widthBeforeWide = copilotPreferredWidth.value;
  setCopilotWidth(COPILOT_WIDE_WIDTH);
}

function onCopilotResizeStart(event) {
  if (event.button) return;
  copilotDrag = { x: event.clientX, width: copilotWidth.value };
  event.preventDefault();
  event.currentTarget.setPointerCapture?.(event.pointerId);
  document.body.classList.add("is-resizing-copilot");
}

function onCopilotResizeMove(event) {
  if (!copilotDrag) return;
  // The rail is on the right, so dragging left widens it.
  setCopilotWidth(copilotDrag.width + (copilotDrag.x - event.clientX), {
    persist: false,
  });
}

function onCopilotResizeEnd(event) {
  if (!copilotDrag) return;
  copilotDrag = null;
  event.currentTarget?.releasePointerCapture?.(event.pointerId);
  document.body.classList.remove("is-resizing-copilot");
  writeCopilotWidth(copilotPreferredWidth.value);
}

function onCopilotResizeKey(event) {
  const step = event.shiftKey ? 48 : 16;
  if (event.key === "ArrowLeft") setCopilotWidth(copilotWidth.value + step);
  else if (event.key === "ArrowRight") setCopilotWidth(copilotWidth.value - step);
  else if (event.key === "Home") setCopilotWidth(COPILOT_DEFAULT_WIDTH);
  else return;
  event.preventDefault();
}

function onWindowResize() {
  viewportWidth.value = window.innerWidth;
}

function setCopilotOpen(open) {
  if (open) copilotReady.value = true;
  else copilotState.value = { ...copilotState.value, busy: false, hasTurns: false };
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
  if (!payload.prompt) return;
  // A ticker or headline outside the workspace has no company of its own.
  // Rather than send it to whichever company Warren is on, leave it in his
  // composer under that company for the analyst to send or redirect.
  if (payload.companyId || currentCompanyId.value) queueCopilotPrompt(payload.prompt);
  else copilotDraftPrompt.value = String(payload.prompt);
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

// Warren's citations open the file on the desk's Files tab (at the cited
// page), and an edit he applied opens Memo Studio at that point.
function onCopilotNavigate(target) {
  if (!target?.companyId) return;
  if (target.kind === "file") {
    router.push(
      companyLocation(target.companyId, {
        section: "files",
        previewFile: target.file?.id,
        previewPage: target.page || undefined,
      }),
    );
    return;
  }
  if (target.kind === "memo_bullet") {
    router.push(
      companyLocation(target.companyId, {
        section: "memos",
        memoSection: target.sectionId,
        memoBullet: target.bulletId,
      }),
    );
  }
}

provide("copilotNavigate", onCopilotNavigate);
</script>

<template>
  <!-- Unauthenticated or on login route: just the routed view (LoginView).
       No sidebar, no polling, no modals. -->
  <RouterView v-if="route.name === 'login' || !isAuthenticated" />

  <!-- Authenticated: full app chrome. Two floating glass panels (sidebar,
       Ask inspector) frame the content column. -->
  <div v-else class="canvas-wash min-h-screen text-ink-primary lg:flex">
    <Transition name="sheet-scrim">
      <button
        v-if="mobileNavOpen"
        type="button"
        class="sheet-scrim fixed inset-0 z-40 lg:hidden"
        :aria-label="t('sidebar.close')"
        @click="mobileNavOpen = false"
      />
    </Transition>

    <Sidebar
      :companies="companies"
      :loading="loading"
      :error="error"
      :mobile-open="mobileNavOpen"
      @close="mobileNavOpen = false"
      @navigate="mobileNavOpen = false"
    />

    <main class="min-w-0 flex-1">
      <header
        ref="headerRef"
        class="app-toolbar material-bar sticky top-0 z-30"
        :data-scrolled="scrolled ? 'true' : 'false'"
        :style="chromeLeftInset ? { paddingLeft: `${chromeLeftInset}px` } : null"
      >
        <div class="flex h-[52px] items-center gap-2 px-3 md:px-5">
          <button
            type="button"
            class="icon-btn -ml-1 lg:hidden"
            :aria-label="t('sidebar.open')"
            :title="t('sidebar.open')"
            :aria-expanded="mobileNavOpen"
            @click="mobileNavOpen = true"
          >
            <PanelLeft class="h-[18px] w-[18px]" />
          </button>

          <div
            class="toolbar-title min-w-0 flex-1 leading-tight"
            :data-hidden="largeTitleVisible ? 'true' : 'false'"
          >
            <div class="truncate text-headline font-semibold text-ink-primary">
              {{ toolbarTitle }}
            </div>
            <div v-if="toolbarSubtitle" class="truncate text-caption1 text-ink-muted">
              {{ toolbarSubtitle }}
            </div>
          </div>

          <button
            type="button"
            class="sync-status focus-ring max-xl:hidden"
            :data-state="error ? 'error' : lastSyncAt ? 'ok' : 'pending'"
            :title="t('toolbar.sync_retry')"
            @click="refreshAll"
          >
            <span class="status-dot" />
            <span>{{ syncLabel }}</span>
          </button>

          <div
            v-if="route.name !== 'home'"
            class="relative hidden w-[15.5rem] shrink md:block lg:w-[18rem]"
          >
            <Search
              class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
            />
            <input
              v-model="jumpQuery"
              type="search"
              autocomplete="off"
              spellcheck="false"
              class="toolbar-search"
              :placeholder="t('cmd.jump_placeholder')"
              :aria-label="t('cmd.jump_placeholder')"
              @focus="openJumpMenu"
              @keydown.escape.prevent="closeChromeMenus"
              @keydown.enter.prevent="onJumpEnter"
            />
            <button
              type="button"
              class="kbd absolute right-2 top-1/2 -translate-y-1/2 focus-ring"
              :aria-label="t('cmd.open')"
              :title="t('cmd.open')"
              @click="openCommandPalette"
            >
              ⌘K
            </button>
            <div
              v-if="jumpOpen && jumpQuery.trim()"
              class="toolbar-menu left-0 right-auto min-w-[18rem]"
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
                <Monogram :company="company" :size="22" tinted />
                <span class="min-w-0 flex-1 truncate font-medium">{{ company.name }}</span>
                <span
                  v-if="company.ticker || company.industry"
                  class="max-w-[7rem] truncate text-caption1 text-ink-muted"
                >
                  {{ company.ticker || company.industry }}
                </span>
              </button>
              <p
                v-if="jumpHits.length === 0"
                class="px-2.5 py-2 text-footnote text-ink-muted"
              >
                {{ t("toolbar.no_matches") }}
              </p>
              <RouterLink
                :to="{ path: '/', query: jumpQuery.trim() ? { q: jumpQuery.trim() } : {} }"
                class="toolbar-menu-item hairline-t text-accent-ink"
                @click="researchQuery"
              >
                <Search class="h-3.5 w-3.5 shrink-0" />
                <span class="truncate">
                  {{
                    jumpQuery.trim()
                      ? t("toolbar.research_query", { q: jumpQuery.trim() })
                      : t("toolbar.search_all")
                  }}
                </span>
              </RouterLink>
            </div>
          </div>

          <!-- Actions share one capsule of glass, as in a macOS toolbar. -->
          <div class="glass-capsule relative h-9 shrink-0 gap-px px-[3px]">
            <div class="relative">
              <button
                type="button"
                class="icon-btn !h-[30px] !w-[30px]"
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
                  <p class="px-2.5 pb-2 pt-1.5 text-caption1 text-danger">
                    {{ addUploadError }}
                  </p>
                  <button
                    type="button"
                    class="toolbar-menu-item"
                    role="menuitem"
                    @click="openReportCustomizer(currentCompany?.id); closeChromeMenus()"
                  >
                    <AiMark class="h-4 w-4 shrink-0" />
                    {{ t("memo.generate_report") }}
                  </button>
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
                  <button
                    type="button"
                    class="toolbar-menu-item"
                    role="menuitem"
                    data-testid="menu-file-deck"
                    @click="pickDeck(); closeChromeMenus()"
                  >
                    <FileUp class="h-4 w-4 shrink-0 text-ink-muted" />
                    {{ t("sidebar.file_deck") }}
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="toolbar-menu-item"
                    role="menuitem"
                    @click="openReportCustomizer(); closeChromeMenus()"
                  >
                    <AiMark class="h-4 w-4 shrink-0" />
                    {{ t("memo.generate_report") }}
                  </button>
                  <RouterLink
                    :to="{ path: '/', query: { intake: 'link' } }"
                    class="toolbar-menu-item"
                    role="menuitem"
                    @click="closeChromeMenus"
                  >
                    <LinkIcon class="h-4 w-4 shrink-0 text-accent" />
                    {{ t("home.action_link") }}
                  </RouterLink>
                  <RouterLink
                    :to="{ path: '/', query: { intake: 'upload' } }"
                    class="toolbar-menu-item"
                    role="menuitem"
                    @click="closeChromeMenus"
                  >
                    <UploadCloud class="h-4 w-4 shrink-0 text-info" />
                    {{ t("home.action_file") }}
                  </RouterLink>
                  <RouterLink
                    :to="{ path: '/', query: { intake: 'note' } }"
                    class="toolbar-menu-item"
                    role="menuitem"
                    @click="closeChromeMenus"
                  >
                    <ScrollText class="h-4 w-4 shrink-0 text-warning" />
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
              <input
                ref="deckPickInput"
                type="file"
                accept=".pdf,.pptx,.ppt"
                class="hidden"
                @change="onDeckPicked"
              />
            </div>
            <button
              type="button"
              class="icon-btn !h-[30px] !w-[30px]"
              :aria-label="t('cmd.open')"
              :title="t('cmd.open')"
              :aria-pressed="commandOpen"
              @click="commandOpen = !commandOpen"
            >
              <Command class="h-[17px] w-[17px]" />
            </button>
            <button
              type="button"
              class="icon-btn !h-[30px] !w-[30px]"
              :aria-label="t('jobs.history_title')"
              :title="t('jobs.history_title')"
              :aria-pressed="historyOpen"
              data-testid="task-history-toggle"
              @click="historyOpen = !historyOpen"
            >
              <History class="h-[18px] w-[18px]" />
            </button>
          </div>

          <!-- Ask gets its own capsule: the one AI entry point everywhere. -->
          <div class="glass-capsule relative h-9 shrink-0 px-[3px]">
            <button
              type="button"
              class="copilot-toolbar-btn focus-ring !h-[30px] max-sm:!px-1"
              data-tour="warren"
              :aria-label="t('copilot.ask')"
              :title="t('copilot.ask')"
              :aria-pressed="copilotOpen"
              @click="setCopilotOpen(!copilotOpen)"
            >
              <WarrenMark :size="22" :busy="copilotState.busy" />
              <span class="max-sm:hidden">{{ t("copilot.ask") }}</span>
            </button>
          </div>
        </div>
      </header>

      <div ref="viewRef">
        <RouterView v-slot="{ Component }">
          <Transition name="view-fade" mode="out-in">
            <component
              :is="Component"
              @reports-changed="refreshAll"
              @open-copilot="onOpenCopilot"
            />
          </Transition>
        </RouterView>
      </div>
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
        class="app-inspector copilot-sheet glass-panel fixed inset-x-0 bottom-0 z-50 flex max-h-[min(92dvh,900px)] w-full flex-col rounded-t-[22px] xl:sticky xl:inset-auto xl:top-2 xl:z-20 xl:my-2 xl:mr-2 xl:h-[calc(100vh-1rem)] xl:max-h-none xl:shrink-0 xl:rounded-[20px]"
        :aria-label="t('copilot.title')"
      >
        <div
          class="copilot-resize"
          role="separator"
          aria-orientation="vertical"
          tabindex="0"
          :aria-label="t('copilot.resize')"
          :aria-valuenow="copilotWidth"
          :aria-valuemin="COPILOT_MIN_WIDTH"
          :aria-valuemax="COPILOT_MAX_WIDTH"
          :title="t('copilot.resize')"
          @pointerdown="onCopilotResizeStart"
          @pointermove="onCopilotResizeMove"
          @pointerup="onCopilotResizeEnd"
          @pointercancel="onCopilotResizeEnd"
          @dblclick="setCopilotWidth(COPILOT_DEFAULT_WIDTH)"
          @keydown="onCopilotResizeKey"
        />
        <div
          class="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-ink-primary/15 xl:hidden"
          aria-hidden="true"
        />
        <header class="flex items-center gap-2.5 px-4 pb-3 pt-2 xl:pt-3.5">
          <WarrenMark :size="36" :busy="copilotState.busy" />
          <div class="min-w-0 flex-1">
            <div class="text-headline leading-tight text-ink-primary">
              {{ t("copilot.title") }}
            </div>
            <CopilotCompanyPicker
              v-if="companies.length"
              v-model="copilotPickerValue"
              class="-ml-1.5"
              :companies="companies"
              :recent-ids="copilotRecentIds"
            />
            <div v-else class="truncate text-footnote text-ink-muted">
              {{ t("copilot.warren_full_name") }}
            </div>
          </div>
          <button
            v-if="copilotCompanyId && copilotState.mode === 'quick'"
            type="button"
            class="icon-btn"
            :aria-label="t('copilot.history_title')"
            :title="t('copilot.history_title')"
            @click="copilotPanelRef?.toggleHistory()"
          >
            <History class="h-4 w-4" />
          </button>
          <button
            v-if="copilotCompanyId && copilotState.hasTurns && copilotState.mode === 'quick'"
            type="button"
            class="icon-btn"
            :disabled="copilotState.busy"
            :aria-label="t('copilot.new_chat')"
            :title="t('copilot.new_chat')"
            @click="copilotPanelRef?.newThread()"
          >
            <SquarePen class="h-4 w-4" />
          </button>
          <button
            type="button"
            class="icon-btn max-xl:hidden"
            :aria-label="copilotWide ? t('copilot.restore') : t('copilot.expand')"
            :title="copilotWide ? t('copilot.restore') : t('copilot.expand')"
            @click="toggleCopilotWide"
          >
            <ChevronsRight v-if="copilotWide" class="h-4 w-4" />
            <ChevronsLeft v-else class="h-4 w-4" />
          </button>
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
        <div class="mx-4 h-px shrink-0 bg-ink-primary/[0.08]" aria-hidden="true" />
        <div class="flex min-h-0 flex-1 flex-col px-4 pb-3 pt-3">
          <CopilotPanel
            ref="copilotPanelRef"
            :company-id="copilotCompanyId"
            :company-name="copilotCompanyName"
            :context-label="copilotSeesLabel"
            :suggested-companies="copilotSuggestedCompanies"
            @state="onCopilotState"
            @choose-company="chooseCopilotCompany"
            @close="setCopilotOpen(false)"
          />
        </div>
      </aside>
    </Transition>

    <ActiveJobsRail :copilot-open="copilotOpen" />
    <TaskHistoryPanel
      v-if="historyOpen"
      :copilot-open="copilotOpen"
      @close="historyOpen = false"
    />
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
    <ReportCustomizerModal
      :open="reportCustomizerOpen"
      :initial-company-id="reportCustomizerCompanyId"
      :initial-generation-mode="reportCustomizerMode"
      @close="reportCustomizerOpen = false"
      @created="refreshAll"
    />
    <PitchDeckIntakeModal
      :is-open="deckIntakeOpen"
      :initial-file="deckIntakeFile"
      :company-id="currentCompanyId || ''"
      :companies="companies"
      @close="deckIntakeOpen = false"
      @intake-complete="refreshAll"
    />
    <WelcomeTour :open="welcomeTourOpen" @close="closeWelcomeTour" />
  </div>
</template>
