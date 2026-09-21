<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, unref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Search,
  Loader2,
  ArrowRight,
  Globe,
  Download,
  Brain,
  CheckCircle2,
  ChevronDown,
  Link as LinkIcon,
  Upload,
  ScrollText,
} from "lucide-vue-next";
import { api } from "../api.js";
import AiMark from "../components/AiMark.vue";
import Monogram from "../components/Monogram.vue";
import { useLargeTitle } from "../chrome.js";
import { currentLanguage, useT } from "../i18n.js";
import { buildTickerTape, displayTicker, homeTapeTickers, publicTickers } from "../liveTicker.js";
import { loadPinnedTickers } from "../marketWatchlist.js";
import { DESK_SYNC_EVENT } from "../deskSync.js";
import { companyViews, trackedCompanyIds } from "../state.js";
import { useLiveQuotes } from "../useLiveQuotes.js";
import CompanyBoardCard from "../components/CompanyBoardCard.vue";
import CompanyCard from "../components/CompanyCard.vue";
import LiveTickerTape from "../components/LiveTickerTape.vue";
import SubmitLinkTool from "../components/SubmitLinkTool.vue";
import UploadResearchTool from "../components/UploadResearchTool.vue";
import AddHormuzResearchTool from "../components/AddHormuzResearchTool.vue";

const t = useT();

const router = useRouter();
const heroTitle = ref(null);
useLargeTitle(heroTitle);

// Apple News-style dateline above the title.
const todayLabel = computed(() => {
  try {
    return new Date().toLocaleDateString(currentLanguage.value === "zh" ? "zh-CN" : "en-US", {
      weekday: "long",
      month: "long",
      day: "numeric",
    });
  } catch {
    return "";
  }
});

function suggestionInitials(s) {
  const ticker = String(s?.ticker || "").trim();
  if (/^[A-Za-z]{1,5}$/.test(ticker)) return ticker.slice(0, 2).toUpperCase();
  return "";
}
const route = useRoute();
const query = ref("");

// ?intake=link|upload|note deep-links (and the toolbar Add menu,
// which navigates to those URLs) open the matching Quick Add tool.
const linkOpen = ref(false);
const uploadOpen = ref(false);
const noteOpen = ref(false);
const quickAddEl = ref(null);

watch(
  () => route.query.intake,
  (v) => {
    linkOpen.value = v === "link";
    uploadOpen.value = v === "upload";
    noteOpen.value = v === "note";
    if (v) {
      nextTick(() => {
        quickAddEl.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      });
    }
  },
  { immediate: true },
);

function setIntake(kind) {
  if (kind === "library") {
    router.push({ name: "source-library" });
    return;
  }
  const next = { ...route.query };
  if (next.intake === kind) delete next.intake;
  else next.intake = kind;
  router.replace({ query: next });
}
const suggestions = ref([]);
const showSuggestions = ref(false);
const autocompleting = ref(false);
const error = ref(null);
const errorMessage = computed(() =>
  error.value === "search_stalled" ? t("home.search_stalled") : t("home.search_failed"),
);

const searchResults = ref(null); // { source, matches } | null
const searching = ref(false);

const companies = inject("workspaceCompanies", ref([]));
const workspaceLoading = inject("workspaceLoading", ref(false));
const companyList = computed(() => unref(companies) || []);
const loadingCompanies = computed(() => Boolean(unref(workspaceLoading)));
const recentCompanies = computed(() => {
  const views = companyViews.value || {};
  return [...companyList.value]
    .filter((company) => Number(views[company.id] || 0) > 0)
    .sort((a, b) => Number(views[b.id] || 0) - Number(views[a.id] || 0))
    .slice(0, 8);
});
const trackedCompanies = computed(() => {
  const raw = trackedCompanyIds.value;
  const tracked = new Set(
    raw instanceof Set
      ? [...raw].map(String)
      : Array.isArray(raw)
        ? raw.map(String)
        : [],
  );
  if (!tracked.size) return [];
  return [...companyList.value].filter((company) => tracked.has(String(company.id)));
});
const showRecentCompanies = computed(
  () => !searching.value && !searchResults.value && recentCompanies.value.length > 0,
);
const showTrackedCompanies = computed(
  () => !searching.value && !searchResults.value && trackedCompanies.value.length > 0,
);
const recentExpanded = ref(true);
const trackedExpanded = ref(true);
// The live tape under search. It waits for the workspace list so it doesn't
// flash benchmarks and then swap to the book's own tickers.
const showHomeTape = computed(
  () =>
    !searching.value &&
    !searchResults.value &&
    !(loadingCompanies.value && companyList.value.length === 0),
);
// Market watchlist pins stand in when the workspace has no public names;
// they can arrive from the server after mount, so re-read on desk sync.
const pinnedTickers = ref(loadPinnedTickers());
function refreshPinnedTickers() {
  pinnedTickers.value = loadPinnedTickers();
}
onMounted(() => window.addEventListener(DESK_SYNC_EVENT, refreshPinnedTickers));
onBeforeUnmount(() => window.removeEventListener(DESK_SYNC_EVENT, refreshPinnedTickers));
const tapeFromCompanies = computed(() => publicTickers(companyList.value).length > 0);
const homeTickers = computed(() =>
  showHomeTape.value ? homeTapeTickers(companyList.value, pinnedTickers.value) : [],
);
const { quotes: liveQuotes } = useLiveQuotes(homeTickers);
const tickerTape = computed(() =>
  showHomeTape.value
    ? buildTickerTape(companyList.value, liveQuotes.value, homeTickers.value)
    : [],
);

function quoteFor(company) {
  const ticker = displayTicker(company, companyList.value);
  return ticker ? liveQuotes.value[ticker] || null : null;
}

function openCompany(company) {
  router.push({ name: "research", params: { companyId: company.id } });
}

// A ticker on the tape opens that stock on the Market desk, a workspace
// company's own row included (the sidebar's company launcher is the way to
// its desk). A row without a ticker opens the company.
function openTapeItem(item) {
  if (item?.ticker) {
    router.push({ name: "market-radar", query: { ticker: item.ticker } });
    return;
  }
  if (item?.id) openCompany(item);
}

// Live progress feed during a Claude Code / OpenAI search
const progressEvents = ref([]); // [{type, action, tool, preview, text, ts}]
const currentStage = ref(null); // { stage, message }
const progressFeedRef = ref(null);
// Collapsed by default: header bar shows current step, click to expand the
// full action log.
const progressExpanded = ref(false);
let activeEventSource = null;
let progressIdleTimer = null;
const SEARCH_PROGRESS_IDLE_MS = 150000;

const lastProgressEvent = computed(() => {
  const list = progressEvents.value;
  return list.length ? list[list.length - 1] : null;
});

function toggleProgressExpanded() {
  progressExpanded.value = !progressExpanded.value;
  if (progressExpanded.value) {
    nextTick(() => {
      const el = progressFeedRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }
}

let debounceId = null;
// Monotonic sequence for autocomplete requests: two keystrokes >220ms
// apart issue two requests, and without this guard the slower (older)
// response could resolve last and overwrite fresher suggestions.
let autocompleteSeq = 0;

watch(query, (q) => {
  clearTimeout(debounceId);
  error.value = null;
  if (!q.trim() || q.trim().length < 2) {
    autocompleteSeq += 1; // invalidate any in-flight request
    suggestions.value = [];
    autocompleting.value = false;
    showSuggestions.value = false;
    return;
  }
  autocompleting.value = true;
  showSuggestions.value = true;
  debounceId = setTimeout(async () => {
    const seq = ++autocompleteSeq;
    try {
      const matches = await api.autocompleteCompanies(q.trim());
      if (seq !== autocompleteSeq) return; // stale response
      suggestions.value = matches;
    } catch {
      // A failed background autocomplete isn't a failed search — don't
      // reuse the deep-search error banner for it.
      if (seq !== autocompleteSeq) return;
    } finally {
      if (seq === autocompleteSeq) autocompleting.value = false;
    }
  }, 220);
});

async function pickSuggestion(s) {
  showSuggestions.value = false;
  let id = s.id;
  if (!id) {
    try {
      const upserted = await api.selectCompany({
        name: s.name,
        ticker: s.ticker,
        description: s.description,
        sector: s.sector,
        industry: s.industry,
        exchange: s.exchange,
        status: s.status,
        company_type: s.company_type,
      });
      id = upserted.id;
    } catch {
      error.value = "search_failed";
      return;
    }
  }
  router.push({ name: "research", params: { companyId: id } });
}

function closeProgressStream() {
  if (progressIdleTimer) {
    clearTimeout(progressIdleTimer);
    progressIdleTimer = null;
  }
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
}

function armProgressIdleTimer() {
  if (progressIdleTimer) clearTimeout(progressIdleTimer);
  progressIdleTimer = setTimeout(() => {
    if (!searching.value) return;
    error.value = "search_stalled";
    searching.value = false;
    closeProgressStream();
  }, SEARCH_PROGRESS_IDLE_MS);
}

function handleProgressEvent(entry) {
  if (entry.type === "stage") {
    currentStage.value = {
      stage: entry.stage,
      message: entry.message || entry.stage,
    };
    progressEvents.value.push(entry);
  } else if (entry.type === "claude_action") {
    progressEvents.value.push(entry);
  } else if (entry.type === "done") {
    searchResults.value = {
      source: entry.source,
      matches: entry.matches || [],
      cached_at: entry.cached_at,
      reason: entry.reason,
    };
    searching.value = false;
    closeProgressStream();
  } else if (entry.type === "error") {
    if (Array.isArray(entry.matches)) {
      searchResults.value = {
        source: entry.source,
        matches: entry.matches,
        cached_at: entry.cached_at,
        reason: entry.reason || entry.error,
      };
    } else {
      error.value = "search_failed";
    }
    searching.value = false;
    closeProgressStream();
  }
  if (searching.value) armProgressIdleTimer();
  // Auto-scroll the feed to the latest event.
  nextTick(() => {
    const el = progressFeedRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

async function runDeepSearch({ refresh = false } = {}) {
  if (!query.value.trim()) return;
  showSuggestions.value = false;
  closeProgressStream();
  searching.value = true;
  error.value = null;
  searchResults.value = null;
  progressEvents.value = [];
  currentStage.value = null;
  progressExpanded.value = false;

  try {
    const start = await api.startDeepSearch(query.value.trim(), { refresh });

    // Cache hit — results inline, no progress stream needed.
    if (start.cached) {
      searchResults.value = {
        source: start.source,
        matches: start.matches || [],
        cached_at: start.cached_at,
      };
      searching.value = false;
      return;
    }

    // Open SSE for the running job. Events flow into handleProgressEvent
    // which sets searching=false on `done` or `error`.
    const es = new EventSource(api.searchStreamUrl(start.job_id));
    activeEventSource = es;
    armProgressIdleTimer();
    es.onmessage = (msg) => {
      try {
        const entry = JSON.parse(msg.data);
        handleProgressEvent(entry);
      } catch {
        // ignore malformed lines
      }
    };
    es.onerror = () => {
      // Browser will auto-reconnect; only escalate if we already terminated
      // and the connection just hasn't been closed yet.
      if (!searching.value) closeProgressStream();
    };
  } catch {
    error.value = "search_failed";
    searching.value = false;
  }
}

onBeforeUnmount(closeProgressStream);

watch(
  () => route.query.q,
  (q) => {
    if (typeof q !== "string" || !q.trim()) return;
    if (query.value !== q) query.value = q;
    runDeepSearch();
  },
  { immediate: true },
);

// Display helpers for the progress feed.
function actionIcon(entry) {
  if (entry.type !== "claude_action") return null;
  if (entry.tool === "WebSearch") return Globe;
  if (entry.tool === "WebFetch") return Download;
  if (entry.action === "thinking") return Brain;
  if (entry.action === "result") return CheckCircle2;
  return null;
}

function actionLabel(entry) {
  if (entry.type === "stage") return entry.message || entry.stage;
  if (entry.action === "init")
    return t("jobs.action.claude_initialized");
  if (entry.action === "thinking") return entry.text || t("jobs.action.thinking");
  if (entry.action === "tool_use") {
    if (entry.tool === "WebSearch")
      return `${t("home.progress_web_search")}: ${entry.preview}`;
    if (entry.tool === "WebFetch")
      return `${t("home.progress_fetch")}: ${entry.preview}`;
    return `${entry.tool}: ${entry.preview || ""}`;
  }
  if (entry.action === "tool_result") {
    if (entry.is_error) {
      const reason = (entry.preview || "").trim();
      return reason
        ? `${entry.tool} → ${t("jobs.action.tool_error")}: ${reason.slice(0, 160)}`
        : `${entry.tool} → ${t("jobs.action.tool_error")}`;
    }
    return `${entry.tool} → ${t("jobs.action.tool_ok")}`;
  }
  if (entry.action === "result") {
    const cost = entry.cost_usd
      ? ` ($${Number(entry.cost_usd).toFixed(4)})`
      : "";
    const dur = entry.duration_ms
      ? ` · ${(entry.duration_ms / 1000).toFixed(1)}s`
      : "";
    return `${t("home.progress_done")}${cost}${dur}`;
  }
  if (entry.action === "interrupted") {
    return entry.reason || t("home.search_failed");
  }
  return entry.type;
}

function formatCachedAt(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = Date.now();
  const ageSec = Math.max(0, Math.round((now - d.getTime()) / 1000));
  const ageStr =
    ageSec < 60
      ? t("home.cache_just_now")
      : ageSec < 3600
      ? t("home.cache_minutes_ago", { n: Math.round(ageSec / 60) })
      : ageSec < 86400
      ? t("home.cache_hours_ago", { n: Math.round(ageSec / 3600) })
      : t("home.cache_days_ago", { n: Math.round(ageSec / 86400) });
  return { full: d.toLocaleString(), age: ageStr };
}

function pickResult(match) {
  if (match.id) router.push({ name: "research", params: { companyId: match.id } });
}

function onCardRefreshed(updated) {
  if (!searchResults.value) return;
  const idx = searchResults.value.matches.findIndex((m) => m.id === updated.id);
  if (idx >= 0) {
    searchResults.value.matches.splice(idx, 1, updated);
  }
}

const hasResults = computed(
  () => searchResults.value && searchResults.value.matches.length > 0,
);

function onBlur() {
  // Delay so click on a suggestion can register first.
  setTimeout(() => (showSuggestions.value = false), 150);
}
</script>

<template>
  <div class="relative mx-auto w-full max-w-5xl px-5 pb-16 md:px-8">
    <div class="home-hero-glow" aria-hidden="true" />
    <section class="relative mx-auto max-w-2xl pb-8 pt-10 text-center md:pt-20">
      <p class="home-eyebrow">{{ todayLabel }}</p>
      <h1 ref="heroTitle" class="home-hero-title">{{ t("home.title") }}</h1>
      <p class="mx-auto mt-3 max-w-md text-balance text-[15px] leading-snug text-ink-muted">
        {{ t("home.subtitle") }}
      </p>
    </section>

    <div class="relative z-10 mx-auto w-full max-w-3xl">
      <form
        data-tour="home-search"
        @submit.prevent="runDeepSearch"
        class="material-glass home-search-plate"
      >
        <div class="relative flex items-center">
          <Search
            class="pointer-events-none absolute left-3.5 h-4 w-4 text-ink-muted"
          />
          <input
            v-model="query"
            type="search"
            autofocus
            :placeholder="t('home.search_placeholder')"
            class="home-search-field"
            @focus="suggestions.length && (showSuggestions = true)"
            @blur="onBlur"
          />
          <button
            type="submit"
            :disabled="!query.trim() || searching"
            class="home-search-submit focus-ring"
            :data-ready="query.trim() && !searching ? 'true' : 'false'"
            :aria-label="searching ? t('home.searching') : t('home.search')"
            :title="searching ? t('home.searching') : t('home.search')"
          >
            <Loader2 v-if="searching" class="h-3.5 w-3.5 animate-spin" />
            <ArrowRight v-else class="h-3.5 w-3.5" />
          </button>
        </div>

        <div class="home-intake" role="toolbar" :aria-label="t('toolbar.add')">
          <button
            type="button"
            class="home-action focus-ring"
            data-tone="link"
            :data-selected="linkOpen ? 'true' : 'false'"
            :aria-pressed="linkOpen"
            @click="setIntake('link')"
          >
            <LinkIcon class="h-3.5 w-3.5" />
            {{ t("home.action_link") }}
          </button>
          <button
            type="button"
            class="home-action focus-ring"
            data-tone="file"
            :data-selected="uploadOpen ? 'true' : 'false'"
            :aria-pressed="uploadOpen"
            @click="setIntake('upload')"
          >
            <Upload class="h-3.5 w-3.5" />
            {{ t("home.action_file") }}
          </button>
          <button
            type="button"
            class="home-action focus-ring"
            data-tone="note"
            :data-selected="noteOpen ? 'true' : 'false'"
            :aria-pressed="noteOpen"
            @click="setIntake('note')"
          >
            <ScrollText class="h-3.5 w-3.5" />
            {{ t("home.action_note") }}
          </button>
        </div>
      </form>

      <div
        v-if="showSuggestions && (suggestions.length || autocompleting)"
        class="material-menu absolute left-0 right-0 top-full z-20 mt-2 overflow-hidden rounded-[18px] p-1.5"
      >
        <div
          v-if="autocompleting && suggestions.length === 0"
          class="flex items-center gap-2 px-3 py-2.5 text-callout text-ink-muted"
        >
          <Loader2 class="h-4 w-4 animate-spin" />
          {{ t("home.autocomplete_loading") }}
        </div>
        <button
          v-for="s in suggestions"
          :key="(s.id || '') + (s.ticker || '') + s.name"
          type="button"
          @mousedown.prevent="pickSuggestion(s)"
          class="home-suggestion focus-ring"
        >
          <Monogram :company="s" :name="s.name" :initials="suggestionInitials(s)" :size="32" tinted />
          <div class="min-w-0 flex-1">
            <div class="truncate text-callout font-medium text-ink-primary">
              {{ s.name }}
            </div>
            <div class="truncate text-footnote text-ink-muted">
              <span v-if="s.ticker" class="font-semibold tabular">{{ s.ticker }}</span>
              <span v-if="s.exchange"> · {{ s.exchange }}</span>
              <span v-if="s.category || s.sector"> · {{ s.category || s.sector }}</span>
            </div>
          </div>
          <span
            v-if="s.source === 'local'"
            class="chip bg-notice-soft text-notice-ink"
          >{{ t("home.tag_tracked") }}</span>
          <span
            v-else-if="s.source === 'researched'"
            class="chip bg-success-soft text-success-ink"
            :title="t('home.tag_researched_tooltip')"
          >{{ t("home.tag_researched") }}</span>
          <ArrowRight class="h-3.5 w-3.5 shrink-0 text-ink-subtle" />
        </button>
      </div>
    </div>

    <LiveTickerTape
      v-if="showHomeTape"
      class="relative mx-auto mt-4 w-full max-w-3xl"
      :items="tickerTape"
      :link-to-tracking="tapeFromCompanies"
      @select="openTapeItem"
    />

    <div
      v-if="linkOpen || uploadOpen || noteOpen"
      ref="quickAddEl"
      class="mx-auto mt-4 w-full max-w-3xl scroll-mt-20"
    >
      <div class="grid gap-3">
        <SubmitLinkTool v-model:expanded="linkOpen" />
        <UploadResearchTool v-model:expanded="uploadOpen" />
        <AddHormuzResearchTool v-model:expanded="noteOpen" />
      </div>
    </div>

    <div v-if="error" class="banner-danger mx-auto mt-4 w-full max-w-3xl">{{ errorMessage }}</div>

    <section v-if="showRecentCompanies" class="mt-14">
      <div class="mb-3.5 flex items-end justify-between gap-3">
        <div class="min-w-0">
          <h2 class="text-title3 text-ink-primary">
            {{ t("home.recent_companies") }}
          </h2>
          <p class="mt-0.5 max-w-xl text-footnote text-ink-muted">
            {{ t("home.recent_hint") }}
          </p>
        </div>
        <button
          type="button"
          class="btn-plain btn-sm focus-ring shrink-0"
          :aria-expanded="recentExpanded"
          @click="recentExpanded = !recentExpanded"
        >
          {{ recentExpanded ? t("sidebar.show_less") : t("home.show_more") }}
          <ChevronDown
            class="h-3.5 w-3.5 transition-transform duration-200"
            :class="recentExpanded ? 'rotate-180' : ''"
          />
        </button>
      </div>
      <template v-if="recentExpanded">
        <p v-if="loadingCompanies && companyList.length === 0" class="text-callout text-ink-muted">
          {{ t("common.loading") }}
        </p>
        <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <CompanyBoardCard
            v-for="company in recentCompanies"
            :key="company.id"
            :company="company"
            :quote="quoteFor(company)"
            @select="openCompany"
          />
        </div>
      </template>
    </section>

    <section v-if="showTrackedCompanies" class="mt-12">
      <div class="mb-3.5 flex items-end justify-between gap-3">
        <div class="min-w-0">
          <h2 class="text-title3 text-ink-primary">
            {{ t("home.tracked_companies") }}
          </h2>
          <p class="mt-0.5 max-w-xl text-footnote text-ink-muted">
            {{ t("home.tracked_hint") }}
          </p>
        </div>
        <button
          type="button"
          class="btn-plain btn-sm focus-ring shrink-0"
          :aria-expanded="trackedExpanded"
          @click="trackedExpanded = !trackedExpanded"
        >
          {{ trackedExpanded ? t("sidebar.show_less") : t("home.show_more") }}
          <ChevronDown
            class="h-3.5 w-3.5 transition-transform duration-200"
            :class="trackedExpanded ? 'rotate-180' : ''"
          />
        </button>
      </div>
      <div
        v-if="trackedExpanded"
        class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        <CompanyBoardCard
          v-for="company in trackedCompanies"
          :key="`tracked-${company.id}`"
          :company="company"
          :quote="quoteFor(company)"
          @select="openCompany"
        />
      </div>
    </section>

    <div
      v-if="searching"
      class="desk-card mx-auto mt-10 w-full max-w-3xl overflow-hidden"
    >
      <button
        type="button"
        @click="toggleProgressExpanded"
        class="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-ink-primary/[0.025] focus-ring"
        :aria-expanded="progressExpanded"
      >
        <span class="relative grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent/10">
          <Loader2 class="h-4 w-4 animate-spin text-accent" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-callout font-medium text-ink-primary">
            {{ currentStage?.message || t("home.starting_search") }}
          </span>
          <span
            v-if="lastProgressEvent && !progressExpanded"
            class="block truncate text-footnote text-ink-muted"
            :class="{ 'text-danger': lastProgressEvent.is_error }"
          >
            {{ actionLabel(lastProgressEvent) }}
          </span>
        </span>
        <span
          v-if="currentStage?.stage"
          class="chip shrink-0 bg-ink-primary/[0.06] text-ink-muted"
        >
          {{ currentStage.stage }}
        </span>
        <ChevronDown
          class="h-4 w-4 shrink-0 text-ink-muted transition-transform duration-200"
          :class="progressExpanded ? 'rotate-180' : ''"
        />
      </button>
      <div
        v-show="progressExpanded"
        ref="progressFeedRef"
        class="hairline-t max-h-72 space-y-0.5 overflow-y-auto bg-ink-primary/[0.02] px-3 py-2 font-mono text-[12px] leading-snug"
      >
        <div
          v-if="progressEvents.length === 0"
          class="px-2 py-1 italic text-ink-muted"
        >
          {{ t("home.waiting_for_claude") }}
        </div>
        <div
          v-for="(entry, i) in progressEvents"
          :key="i"
          class="flex items-start gap-2 rounded-[6px] px-2 py-1"
          :class="{ 'bg-accent/[0.07]': entry.type === 'stage', 'text-danger': entry.is_error, }"
        >
          <component
            v-if="actionIcon(entry)"
            :is="actionIcon(entry)"
            class="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted"
          />
          <AiMark
            v-else-if="entry.type === 'stage'"
            class="mt-0.5 h-3.5 w-3.5 shrink-0"
          />
          <span
            v-else
            class="mt-0.5 h-3.5 w-3.5 shrink-0 text-center text-ink-muted"
            >·</span
          >
          <div class="min-w-0 flex-1 break-words text-ink-secondary">
            {{ actionLabel(entry) }}
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="searchResults" class="mx-auto mt-10 w-full max-w-3xl space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="text-title3 text-ink-primary">
          {{
            hasResults
              ? t("home.results_for", { query })
              : t("home.no_matches_for", { query })
          }}
        </h2>
        <div class="flex items-center gap-3">
          <span class="flex items-center gap-1.5 text-footnote text-ink-muted">
            <span>
              {{
                searchResults.source === "claude_code"
                  ? t("home.source_claude_code")
                  : searchResults.source === "openai"
                  ? t("home.source_ai")
                  : searchResults.source === "cache"
                  ? t("home.source_cached")
                  : t("home.source_local")
              }}
            </span>
            <span
              v-if="formatCachedAt(searchResults.cached_at)"
              :title="formatCachedAt(searchResults.cached_at).full"
            >
              · {{ formatCachedAt(searchResults.cached_at).age }}
            </span>
          </span>
          <button
            v-if="searchResults.source !== 'fallback'"
            type="button"
            @click="runDeepSearch({ refresh: true })"
            :disabled="searching"
            class="btn-bordered btn-sm focus-ring"
          >
            {{ t("common.refresh") }}
          </button>
        </div>
      </div>
      <div
        v-if="searchResults.source === 'fallback' && searchResults.reason"
        class="banner-warning"
      >
        {{ t("home.fallback_unavailable", { reason: searchResults.reason }) }}
      </div>
      <CompanyCard
        v-for="m in searchResults.matches"
        :key="m.id"
        :company="m"
        @select="pickResult"
        @refreshed="(updated) => onCardRefreshed(updated)"
      />
    </div>
  </div>
</template>
