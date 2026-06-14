<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  Search,
  Loader2,
  ArrowRight,
  Sparkles,
  Building2,
  Globe,
  Download,
  Brain,
  CheckCircle2,
  AlertCircle,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Flame,
  RefreshCw,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import CompanyCard from "../components/CompanyCard.vue";
import SubmitLinkTool from "../components/SubmitLinkTool.vue";
import UploadResearchTool from "../components/UploadResearchTool.vue";
import AddHormuzResearchTool from "../components/AddHormuzResearchTool.vue";

const t = useT();

const router = useRouter();
const query = ref("");
const suggestions = ref([]);
const showSuggestions = ref(false);
const autocompleting = ref(false);
const error = ref(null);

const searchResults = ref(null); // { source, matches } | null
const searching = ref(false);
const refreshingStockViews = ref(false);
const stockRefreshMessage = ref(null);
const stockRefreshError = ref(null);
const regeneratingAll = ref(false);
const regenAllMessage = ref(null);
const regenAllError = ref(null);

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

watch(query, (q) => {
  clearTimeout(debounceId);
  error.value = null;
  if (!q.trim() || q.trim().length < 2) {
    suggestions.value = [];
    autocompleting.value = false;
    showSuggestions.value = false;
    return;
  }
  autocompleting.value = true;
  showSuggestions.value = true;
  debounceId = setTimeout(async () => {
    try {
      suggestions.value = await api.autocompleteCompanies(q.trim());
    } catch (e) {
      error.value = e.message;
    } finally {
      autocompleting.value = false;
    }
  }, 220);
});

async function pickSuggestion(s) {
  showSuggestions.value = false;
  let id = s.id;
  if (!id) {
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
    error.value = t("home.search_stalled");
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
    error.value = entry.error || t("home.search_failed");
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
  } catch (e) {
    error.value = e.message;
    searching.value = false;
  }
}

async function refreshAllStockViews() {
  if (refreshingStockViews.value) return;
  refreshingStockViews.value = true;
  stockRefreshMessage.value = null;
  stockRefreshError.value = null;
  try {
    const result = await api.trader.refreshAll();
    const queued = result.queued_count ?? 0;
    const total = result.total_count ?? 0;
    if (!total) {
      stockRefreshMessage.value = t("home.refresh_stock_views_none");
    } else if (result.status === "already_running") {
      stockRefreshMessage.value = t("home.refresh_stock_views_running", {
        total,
      });
    } else {
      stockRefreshMessage.value = t("home.refresh_stock_views_started", {
        queued,
        total,
      });
    }
  } catch (e) {
    stockRefreshError.value =
      e?.message || t("home.refresh_stock_views_failed");
  } finally {
    refreshingStockViews.value = false;
  }
}

async function regenAllCompanies() {
  if (regeneratingAll.value) return;
  regeneratingAll.value = true;
  regenAllMessage.value = null;
  regenAllError.value = null;
  try {
    const result = await api.regenAllCompanies();
    const total = result.total_count ?? 0;
    const publicCount = result.public_trader_count ?? 0;
    if (!total) {
      regenAllMessage.value = t("home.regen_all_none");
    } else if (result.checkpoint_status === "backing_off") {
      regenAllMessage.value = t("home.regen_all_backing_off");
    } else if (result.status === "already_running") {
      regenAllMessage.value = t("home.regen_all_running", { total });
    } else if (result.resumed || result.status === "resumed") {
      regenAllMessage.value = t("home.regen_all_resumed", {
        pending: result.pending_count ?? result.queued_count ?? 0,
        completed: result.completed_count ?? 0,
      });
    } else {
      regenAllMessage.value = t("home.regen_all_started", {
        total,
        public: publicCount,
      });
    }
  } catch (e) {
    regenAllError.value = e?.message || t("home.regen_all_failed");
  } finally {
    regeneratingAll.value = false;
  }
}

onBeforeUnmount(closeProgressStream);

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
    return `${t("jobs.action.claude_initialized")} (${entry.model || "claude"})`;
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
  <div class="max-w-4xl mx-auto px-8 py-12">
    <header class="mb-10 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="min-w-0">
        <div class="text-xs uppercase tracking-wider text-ink-muted mb-2">
          {{ t("home.eyebrow") }}
        </div>
        <h1 class="font-display text-3xl font-semibold text-ink-primary">
          {{ t("home.title") }}
        </h1>
        <p class="mt-2 text-ink-secondary">
          {{ t("home.subtitle") }}
        </p>
      </div>
      <div class="w-full shrink-0 flex flex-col items-stretch gap-2 sm:w-auto sm:items-end">
        <div class="flex w-full items-center gap-2 overflow-x-auto pb-1 sm:w-auto sm:flex-wrap sm:justify-end sm:overflow-visible sm:pb-0">
          <router-link
            :to="{ name: 'weekly-summary' }"
            class="inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-primary shadow-card hover:bg-surface-muted focus-ring"
          >
            <Flame class="h-4 w-4 text-accent" />
            {{ t("home.weekly_summary") }}
          </router-link>
          <router-link
            :to="{ name: 'trader-stats' }"
            class="inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-primary shadow-card hover:bg-surface-muted focus-ring"
          >
            <BarChart3 class="h-4 w-4 text-accent" />
            {{ t("home.trader_stats") }}
          </router-link>
          <button
            type="button"
            :disabled="regeneratingAll"
            @click="regenAllCompanies"
            class="inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-primary shadow-card hover:bg-surface-muted disabled:opacity-60 focus-ring"
          >
            <Loader2
              v-if="regeneratingAll"
              class="h-4 w-4 animate-spin text-accent"
            />
            <Sparkles v-else class="h-4 w-4 text-accent" />
            <span>
              {{
                regeneratingAll
                  ? t("home.regenerating_all")
                  : t("home.regen_all")
              }}
            </span>
          </button>
          <button
            type="button"
            :disabled="refreshingStockViews"
            @click="refreshAllStockViews"
            class="inline-flex shrink-0 whitespace-nowrap items-center justify-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm font-medium text-ink-primary shadow-card hover:bg-surface-muted disabled:opacity-60 focus-ring"
          >
            <Loader2
              v-if="refreshingStockViews"
              class="h-4 w-4 animate-spin text-accent"
            />
            <RefreshCw v-else class="h-4 w-4 text-accent" />
            <span>
              {{
                refreshingStockViews
                  ? t("home.refreshing_stock_views")
                  : t("home.refresh_stock_views")
              }}
            </span>
          </button>
        </div>
        <p
          v-if="stockRefreshMessage"
          class="text-xs text-ink-muted sm:max-w-xs sm:text-right"
        >
          {{ stockRefreshMessage }}
        </p>
        <p
          v-if="stockRefreshError"
          class="text-xs text-danger sm:max-w-xs sm:text-right"
        >
          {{ stockRefreshError }}
        </p>
        <p
          v-if="regenAllMessage"
          class="text-xs text-ink-muted sm:max-w-xs sm:text-right"
        >
          {{ regenAllMessage }}
        </p>
        <p
          v-if="regenAllError"
          class="text-xs text-danger sm:max-w-xs sm:text-right"
        >
          {{ regenAllError }}
        </p>
      </div>
    </header>

    <form @submit.prevent="runDeepSearch" class="relative">
      <Search
        class="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-ink-muted"
      />
      <input
        v-model="query"
        type="search"
        autofocus
        :placeholder="t('home.search_placeholder')"
        class="w-full pl-12 pr-32 py-3 rounded-card border border-subtle bg-surface text-ink-primary placeholder:text-ink-subtle focus-ring shadow-card"
        @focus="suggestions.length && (showSuggestions = true)"
        @blur="onBlur"
      />
      <button
        type="submit"
        :disabled="!query.trim() || searching"
        class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex whitespace-nowrap items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover disabled:opacity-60 focus-ring"
      >
        <Sparkles class="h-3.5 w-3.5" />
        <span>{{ searching ? t("home.searching") : t("home.search") }}</span>
      </button>

      <div
        v-if="showSuggestions && (suggestions.length || autocompleting)"
        class="absolute left-0 right-0 top-full mt-2 bg-surface border border-subtle rounded-card shadow-card-raised z-10 overflow-hidden"
      >
        <div
          v-if="autocompleting && suggestions.length === 0"
          class="px-4 py-3 text-sm text-ink-muted flex items-center gap-2"
        >
          <Loader2 class="h-4 w-4 animate-spin" />
          {{ t("home.autocomplete_loading") }}
        </div>
        <button
          v-for="s in suggestions"
          :key="(s.id || '') + (s.ticker || '') + s.name"
          type="button"
          @mousedown.prevent="pickSuggestion(s)"
          class="w-full text-left px-4 py-2.5 hover:bg-surface-muted focus-ring flex items-center gap-3 border-b border-subtle last:border-b-0"
        >
          <Building2 class="h-4 w-4 text-ink-muted shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ink-primary truncate">
              {{ s.name }}
            </div>
            <div class="text-xs text-ink-muted truncate">
              <span v-if="s.ticker" class="font-mono">{{ s.ticker }}</span>
              <span v-if="s.exchange"> · {{ s.exchange }}</span>
              <span v-if="s.sector"> · {{ s.sector }}</span>
              <span
                v-if="s.source === 'local'"
                class="ml-2 px-1 py-0.5 rounded bg-accent-soft text-accent-ink"
                >{{ t("home.tag_tracked") }}</span
              >
              <span
                v-else-if="s.source === 'researched'"
                class="ml-2 px-1 py-0.5 rounded bg-success-soft text-success-ink"
                :title="t('home.tag_researched_tooltip')"
                >{{ t("home.tag_researched") }}</span
              >
            </div>
          </div>
          <ArrowRight class="h-3.5 w-3.5 text-ink-muted shrink-0" />
        </button>
      </div>
    </form>

    <div v-if="error" class="mt-4 text-sm text-danger">{{ error }}</div>

    <div
      v-if="searching"
      class="mt-10 rounded-card border border-subtle bg-surface shadow-card overflow-hidden"
    >
      <button
        type="button"
        @click="toggleProgressExpanded"
        class="w-full px-4 py-3 border-b border-subtle bg-surface-muted flex items-center gap-2 focus-ring text-left hover:bg-surface"
        :aria-expanded="progressExpanded"
      >
        <Loader2 class="h-4 w-4 animate-spin text-accent shrink-0" />
        <span class="text-sm font-medium text-ink-primary">
          {{ currentStage?.message || t("home.starting_search") }}
        </span>
        <span
          v-if="lastProgressEvent && !progressExpanded"
          class="text-xs text-ink-muted truncate min-w-0 flex-1 font-mono"
          :class="{ 'text-danger': lastProgressEvent.is_error }"
        >
          · {{ actionLabel(lastProgressEvent) }}
        </span>
        <span
          v-if="currentStage?.stage"
          class="ml-auto text-[10px] uppercase tracking-wide text-ink-muted font-mono shrink-0"
        >
          {{ currentStage.stage }}
        </span>
        <ChevronDown
          v-if="progressExpanded"
          class="h-4 w-4 text-ink-muted shrink-0"
        />
        <ChevronRight v-else class="h-4 w-4 text-ink-muted shrink-0" />
      </button>
      <div
        v-show="progressExpanded"
        ref="progressFeedRef"
        class="max-h-72 overflow-y-auto px-3 py-2 space-y-1 font-mono text-[12px] leading-snug bg-canvas"
      >
        <div
          v-if="progressEvents.length === 0"
          class="px-2 py-1 text-ink-muted italic"
        >
          {{ t("home.waiting_for_claude") }}
        </div>
        <div
          v-for="(entry, i) in progressEvents"
          :key="i"
          class="flex items-start gap-2 px-2 py-1 rounded"
          :class="{
            'bg-accent-soft/30': entry.type === 'stage',
            'text-danger': entry.is_error,
          }"
        >
          <component
            v-if="actionIcon(entry)"
            :is="actionIcon(entry)"
            class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted"
          />
          <Sparkles
            v-else-if="entry.type === 'stage'"
            class="h-3.5 w-3.5 mt-0.5 shrink-0 text-accent"
          />
          <span
            v-else
            class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted text-center"
            >·</span
          >
          <div class="min-w-0 flex-1 break-words text-ink-secondary">
            {{ actionLabel(entry) }}
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="searchResults" class="mt-10 space-y-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h2 class="font-display text-lg font-semibold text-ink-primary">
          {{
            hasResults
              ? t("home.results_for", { query })
              : t("home.no_matches_for", { query })
          }}
        </h2>
        <div class="flex items-center gap-3">
          <span class="text-xs text-ink-muted flex items-center gap-1.5">
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
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary focus-ring"
          >
            {{ t("common.refresh") }}
          </button>
        </div>
      </div>
      <div
        v-if="searchResults.source === 'fallback' && searchResults.reason"
        class="text-sm text-warning-ink bg-warning-soft border border-warning/40 rounded-lg px-3 py-2"
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

    <div class="mt-12 space-y-3">
      <h2
        class="text-xs font-semibold uppercase tracking-wide text-ink-muted px-1"
      >
        {{ t("home.quick_add") }}
      </h2>
      <SubmitLinkTool />
      <UploadResearchTool />
      <AddHormuzResearchTool />
      <router-link
        :to="{ name: 'hormuz-library' }"
        class="block w-full text-left px-3 py-2 rounded-card border border-subtle bg-surface hover:bg-surface-muted text-sm text-ink-primary focus-ring"
      >
        {{ t("home.hormuz_library") }}
      </router-link>
    </div>
  </div>
</template>
